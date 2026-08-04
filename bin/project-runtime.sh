#!/usr/bin/env bash
#
# Start and stop one project's containers.
#
# Invoked by /usr/local/libexec/agentic-postgres/project, which
# agentic-postgres-project@<key>.service runs. Not normally run by hand.
#
# The ordering here is the whole point, and it is asymmetric:
#
#   up:    materialize secrets -> compose up -> attach the edge
#   down:  detach the edge     -> compose down
#
# Attaching last means a route never points at a container that is not yet
# serving. Detaching first means the edge network has no endpoint when Compose
# tries to remove it -- otherwise the removal fails, the network survives, and
# the next start finds a network it did not create and cannot reconcile.
#
# Exit codes:
#   0  success
#   2  invalid operator input
#   3  missing prerequisite
#   4  missing runtime state (the project was never deployed here)
#   8  secrets could not be materialized
#   9  the edge attachment failed

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

readonly PROJECT_STATE_ROOT="/var/lib/agentic-postgres/projects"
readonly PROJECT_KEY_PATTERN='^[a-z][a-z0-9-]{4,47}$'

ACTION=""
PROJECT_KEY=""
HOST_MANIFEST=""

usage() {
  cat <<'USAGE'
Usage: bin/project-runtime.sh --host FILE --project-key KEY <up|down|status>

  up      Materialize secrets, start the project, then attach the edge.
  down    Detach the edge, then stop the project. Volumes are preserved.
  status  Report container state. Changes nothing, needs no root.

  --host FILE        The host manifest.
  --project-key KEY  The project key. Validated before use as a path component.

Ordering is not configurable. Attach happens after the containers are healthy
so a route never points at something that is not serving; detach happens before
teardown so Compose can remove a network that still has no endpoint on it.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'project-runtime: %s\n' "$*" >&2
  exit "$code"
}

parse_arguments() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help|-h) usage; exit 0 ;;
      --host)
        [ "$#" -ge 2 ] || die 2 "--host requires a value."
        HOST_MANIFEST="$2"
        shift 2
        ;;
      --project-key)
        [ "$#" -ge 2 ] || die 2 "--project-key requires a value."
        PROJECT_KEY="$2"
        shift 2
        ;;
      up|down|status)
        [ -z "${ACTION}" ] || die 2 "only one action may be given."
        ACTION="$1"
        shift
        ;;
      *) usage >&2; die 2 "unknown argument: $1" ;;
    esac
  done

  [ -n "${ACTION}" ] || { usage >&2; die 2 "an action is required."; }
  [ -n "${PROJECT_KEY}" ] || die 2 "--project-key is required."
  printf '%s' "${PROJECT_KEY}" | grep -Eq "${PROJECT_KEY_PATTERN}" \
    || die 2 "not a valid project key: ${PROJECT_KEY}"

  if [ "${ACTION}" != "status" ]; then
    [ -n "${HOST_MANIFEST}" ] || die 2 "--host is required for ${ACTION}."
    [ -f "${HOST_MANIFEST}" ] || die 2 "host manifest not found: ${HOST_MANIFEST}"
  fi
}

state_directory() {
  local directory="${PROJECT_STATE_ROOT}/${PROJECT_KEY}"
  [ -d "${directory}" ] || die 4 "no runtime state for ${PROJECT_KEY}: ${directory}"
  [ -L "${directory}" ] && die 2 "${directory} is a symlink, which is not accepted."
  printf '%s' "${directory}"
}

main() {
  parse_arguments "$@"
  cd "${ROOT_DIR}"

  # Privilege first, before any state is read. A command that got as far as
  # "no deployment state for this project" and only then discovered it needed
  # root reports the wrong problem: the operator fixes the state, re-runs, and
  # hits the refusal they could have been told about immediately.
  case "${ACTION}" in
    up|down) [ "$(id -u)" -eq 0 ] || die 3 "${ACTION} requires root." ;;
  esac

  local state
  state="$(state_directory)"

  case "${ACTION}" in
    status)
      "${ROOT_DIR}/bin/compose.sh" "${state}" ps
      ;;

    up)
      # Before the containers, not after. A container that starts and then finds
      # its secret missing fails in its own way, at its own time, and reports it
      # as an application error.
      "${ROOT_DIR}/bin/materialize-secrets.sh" \
        --project "${state}/manifest.yaml" \
        --requirements "${state}/secrets.required.yaml" \
        --session 2 \
        || die 8 "secrets could not be materialized for ${PROJECT_KEY}."

      "${ROOT_DIR}/bin/compose.sh" "${state}" --runtime --profile session2 up -d --wait \
        || die 9 "the project did not become healthy."

      # Last, and only now that --wait has returned.
      "${ROOT_DIR}/bin/edge-network.sh" attach --project-key "${PROJECT_KEY}" \
        || die 9 "the project is running but has no ingress."

      printf 'project-runtime: %s is up and attached.\n' "${PROJECT_KEY}"
      ;;

    down)
      # First. Compose cannot remove a network that still has an endpoint on it,
      # and the failure is reported as a network error rather than as the
      # missing detach it actually is.
      "${ROOT_DIR}/bin/edge-network.sh" detach --project-key "${PROJECT_KEY}" \
        || die 9 "could not detach the edge; refusing to tear down underneath it."

      # No -v. The Postgres volume outlives the project by design; removing it
      # here would make `systemctl restart` a data-loss command.
      "${ROOT_DIR}/bin/compose.sh" "${state}" --runtime --profile session2 down \
        || die 9 "the project did not stop cleanly."

      printf 'project-runtime: %s is down. Volumes are preserved.\n' "${PROJECT_KEY}"
      ;;
  esac
}

main "$@"
