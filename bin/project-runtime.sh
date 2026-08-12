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
#   4  missing runtime state or rendered output (the project was never deployed
#      here). Configuration lives under /etc/agentic-postgres/projects/<key>/;
#      generated output under /var/lib/agentic-postgres/rendered/<key>/ (ADR 0020).
#   8  secrets could not be materialized
#   9  the edge attachment failed
#
# The session this project was deployed through arrives as `--through-session`
# and is never assumed. It selects three things that must agree: which secrets
# are materialized, which Compose profiles start, and therefore which services
# exist to receive a grant. Hard-coding `2` in all three -- which is what this
# script did until Session 3 -- is correct for exactly as long as 2 is the only
# value anyone passes, and then it silently deploys the wrong release. The
# caller that has no operator to ask (the systemd launcher) reads it back from
# the project's own deployed document; see D59.

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

readonly PROJECT_STATE_ROOT="/etc/agentic-postgres/projects"
readonly PROJECT_RENDERED_ROOT="/var/lib/agentic-postgres/rendered"
readonly PROJECT_KEY_PATTERN='^[a-z][a-z0-9-]{4,47}$'

ACTION=""
PROJECT_KEY=""
HOST_MANIFEST=""
THROUGH_SESSION=""
DEFERRED=""
HELD_BACK=""

usage() {
  cat <<'USAGE'
Usage: bin/project-runtime.sh --host FILE --project-key KEY \
         --through-session N [--defer SERVICE,...] <up|down|status|resume>

  up      Materialize secrets, start the project, then attach the edge.
  resume  Start whatever `up --defer` held back, then attach. Materializes
          nothing.
  down    Detach the edge, then stop the project. Volumes are preserved.
  status  Report container state. Changes nothing, needs no root.

  --host FILE           The host manifest.
  --project-key KEY     The project key. Validated before use as a path component.
  --through-session N   The session this project is deployed through. Required
                        for up, resume and down; it selects the secret set and
                        the Compose profiles, which must be the same N.
  --defer SERVICE,...   Start everything except these, and do not attach the
                        edge. `resume` completes it.

Ordering is not configurable. Attach happens after the containers are healthy
so a route never points at something that is not serving; detach happens before
teardown so Compose can remove a network that still has no endpoint on it.

`--defer` exists for one reason (ADR 0063): a service that authenticates as a
project role cannot start until the bootstrap plane has activated that role, and
the bootstrap plane needs the cluster the same command starts. The deploy runs
`up --defer`, bootstraps, then `resume`.

`resume` does NOT re-materialize, and that is the point of it being a separate
action rather than a second `up`. `up` writes a new secret generation every time
and repoints the project at it; a second `up` here would set a role's password
from one generation and mount another into the container.
USAGE
}

# The profiles that make up a deployment through session N, cumulative. A
# session-3 project runs the session-2 services too; `migration` is deliberately
# absent, because dbmate is a one-shot the migration plane runs, not a service
# `up` starts.
session_profiles() {
  local session="$1" n
  local -a profiles=()
  for n in $(seq 2 "${session}"); do
    profiles+=(--profile "session${n}")
  done
  printf '%s\n' "${profiles[@]}"
}

die() {
  local code="$1"
  shift
  printf 'project-runtime: %s\n' "$*" >&2
  exit "$code"
}

# Ubuntu ships no bare `python`, and systemd starts this with no venv on PATH.
python_bin() {
  if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then printf '%s\n' "${ROOT_DIR}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then command -v python3
  elif command -v python >/dev/null 2>&1; then command -v python
  else die 3 "no Python interpreter found (looked for .venv/bin/python, python3, python)."
  fi
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
      --through-session)
        [ "$#" -ge 2 ] || die 2 "--through-session requires a value."
        THROUGH_SESSION="$2"
        shift 2
        ;;
      --defer)
        [ "$#" -ge 2 ] || die 2 "--defer requires a comma-separated service list."
        DEFERRED="$2"
        shift 2
        ;;
      up|down|status|resume)
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

    # Required, not defaulted. A default here would be the hard-coded 2 this
    # flag exists to remove: a caller that forgot to pass it would start a
    # subset of the deployment and report success.
    [ -n "${THROUGH_SESSION}" ] || die 2 "--through-session is required for ${ACTION}."
    case "${THROUGH_SESSION}" in
      ''|*[!0-9]*) die 2 "--through-session takes a session number, got: ${THROUGH_SESSION}" ;;
    esac
    [ "${THROUGH_SESSION}" -ge 2 ] \
      || die 2 "--through-session must be at least 2; sessions before that start nothing."
  fi

  # `--defer` is meaningless on anything but `up`, and accepting it silently
  # elsewhere would let a caller believe `resume --defer x` held something back.
  if [ -n "${DEFERRED}" ] && [ "${ACTION}" != "up" ]; then
    die 2 "--defer applies to up, not to ${ACTION}."
  fi
}

# Every service this deployment runs, one per line, from the resolved model.
#
# Read out of the model rather than listed here: the set changes with the session
# and with the profiles, and a second list would be the one that went stale.
#
# **This function only reads.** The filtering that used to live here set a global
# and was called as `mapfile < <(...)`, which runs it in a **subshell** -- so the
# global was set in a child and lost, and the caller could not tell that anything
# had been held back. Measured, with a control: a variable assigned inside a
# function called through process substitution does not survive into the parent.
# The consequence was not a crash: the right services started, and the edge
# attached one step early, which is exactly the ordering ADR 0063 exists to
# deliver. So the filtering is in the caller now, where its results are in scope.
model_services() {
  local rendered="$1"
  shift
  local -a profiles=("$@")
  "${ROOT_DIR}/bin/compose.sh" "${rendered}" --runtime "${profiles[@]}" config --services | sort
}

# `printf` stays last on purpose. Under `set -e` a bare `[ -L x ] && die` as the
# final command of a function returns 1 when the path is not a symlink, and the
# function would fail exactly when the check passes.
resolved_directory() {
  local directory="$1" label="$2"
  [ -d "${directory}" ] || die 4 "no ${label} for ${PROJECT_KEY}: ${directory}"
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
    up|down|resume) [ "$(id -u)" -eq 0 ] || die 3 "${ACTION} requires root." ;;
  esac

  local state rendered

  case "${ACTION}" in
    status)
      rendered="$(resolved_directory "${PROJECT_RENDERED_ROOT}/${PROJECT_KEY}" "rendered output")"
      "${ROOT_DIR}/bin/compose.sh" "${rendered}" ps
      ;;

    up)
      state="$(resolved_directory "${PROJECT_STATE_ROOT}/${PROJECT_KEY}" "runtime state")"
      rendered="$(resolved_directory "${PROJECT_RENDERED_ROOT}/${PROJECT_KEY}" "rendered output")"

      # Before the containers, not after. A container that starts and then finds
      # its secret missing fails in its own way, at its own time, and reports it
      # as an application error.
      "${ROOT_DIR}/bin/materialize-secrets.sh" \
        --project "${state}/manifest.yaml" \
        --requirements "${state}/secrets.required.yaml" \
        --session "${THROUGH_SESSION}" \
        || die 8 "secrets could not be materialized for ${PROJECT_KEY}."

      # Between materialization and start, and in that order for a reason that
      # is not stylistic: materialization has just written a *new* generation
      # and repointed the project at it, so a grant surface rendered before
      # this line names the directory the previous start used. Compose would
      # mount a file that still exists, from a generation nothing refreshes --
      # and the failure would appear at the next rotation, not here.
      "$(python_bin)" "${ROOT_DIR}/bin/render-secret-override.py" \
        --project-key "${PROJECT_KEY}" \
        --requirements "${state}/secrets.required.yaml" \
        --session "${THROUGH_SESSION}" \
        --rendered-dir "${rendered}" \
        || die 8 "the secret grant surface could not be rendered for ${PROJECT_KEY}."

      # --build, because Compose only builds an image that is missing. Without
      # it a project started once kept its first image for good: a new immutable
      # release could change a service's source and the running container would
      # never see it, while the deploy reported success. Layer caching makes
      # this near-free when nothing changed, and a release is meant to be what
      # is actually running.
      local -a profiles=()
      mapfile -t profiles < <(session_profiles "${THROUGH_SESSION}")

      # Filtered here, in the parent, so HELD_BACK is in scope below. See
      # model_services for what putting it in the function cost.
      local -a all=() services=()
      local service deferred matched
      mapfile -t all < <(model_services "${rendered}" "${profiles[@]}")
      [ "${#all[@]}" -gt 0 ] || die 9 "the resolved model names no services."

      HELD_BACK=""
      for service in "${all[@]}"; do
        matched=0
        for deferred in ${DEFERRED//,/ }; do
          if [ "${service}" = "${deferred}" ]; then
            matched=1
            HELD_BACK="${HELD_BACK:+${HELD_BACK},}${service}"
          fi
        done
        [ "${matched}" -eq 0 ] && services+=("${service}")
      done

      [ "${#services[@]}" -gt 0 ] \
        || die 2 "--defer would hold back every service this deployment runs."

      "${ROOT_DIR}/bin/compose.sh" "${rendered}" --runtime "${profiles[@]}" \
        up -d --build --wait "${services[@]}" \
        || die 9 "the project did not become healthy."

      # Services actually held back mean the deployment is not finished, so the
      # edge is not attached: a route pointing at a plane that has not started
      # is worse than no route (ADR 0063, §4.1).
      #
      # `HELD_BACK` rather than `DEFERRED`, because they differ: the caller
      # passes the same list at every session and a service the session does not
      # run is held back from nothing. A session-4 deploy asked to defer
      # `postgrest` has deferred nothing and should attach here, as it always
      # did.
      if [ -n "${HELD_BACK}" ]; then
        printf 'project-runtime: %s is up without %s. Run resume to finish.\n' \
          "${PROJECT_KEY}" "${HELD_BACK}"
        exit 0
      fi

      # Last, and only now that --wait has returned.
      "${ROOT_DIR}/bin/edge-network.sh" attach --project-key "${PROJECT_KEY}" \
        || die 9 "the project is running but has no ingress."

      printf 'project-runtime: %s is up and attached.\n' "${PROJECT_KEY}"
      ;;

    resume)
      rendered="$(resolved_directory "${PROJECT_RENDERED_ROOT}/${PROJECT_KEY}" "rendered output")"

      # No materialization and no override render, deliberately. `up` writes a
      # new generation and repoints the project at it; doing that again here
      # would mount a generation the bootstrap plane did not set a password
      # from, which is the failure this whole ordering exists to prevent
      # (ADR 0063).
      local -a profiles=()
      mapfile -t profiles < <(session_profiles "${THROUGH_SESSION}")

      "${ROOT_DIR}/bin/compose.sh" "${rendered}" --runtime "${profiles[@]}" up -d --build --wait \
        || die 9 "the deferred services did not become healthy."

      "${ROOT_DIR}/bin/edge-network.sh" attach --project-key "${PROJECT_KEY}" \
        || die 9 "the project is running but has no ingress."

      printf 'project-runtime: %s is up and attached.\n' "${PROJECT_KEY}"
      ;;

    down)
      rendered="$(resolved_directory "${PROJECT_RENDERED_ROOT}/${PROJECT_KEY}" "rendered output")"

      # First. Compose cannot remove a network that still has an endpoint on it,
      # and the failure is reported as a network error rather than as the
      # missing detach it actually is.
      "${ROOT_DIR}/bin/edge-network.sh" detach --project-key "${PROJECT_KEY}" \
        || die 9 "could not detach the edge; refusing to tear down underneath it."

      # No -v. The Postgres volume outlives the project by design; removing it
      # here would make `systemctl restart` a data-loss command.
      local -a profiles=()
      mapfile -t profiles < <(session_profiles "${THROUGH_SESSION}")

      "${ROOT_DIR}/bin/compose.sh" "${rendered}" --runtime "${profiles[@]}" down \
        || die 9 "the project did not stop cleanly."

      printf 'project-runtime: %s is down. Volumes are preserved.\n' "${PROJECT_KEY}"
      ;;
  esac
}

main "$@"
