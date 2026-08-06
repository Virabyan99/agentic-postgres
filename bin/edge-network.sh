#!/usr/bin/env bash
#
# Attach and detach Traefik from one project's edge network.
#
# The shared edge plane has to reach each project's edge network, and those
# networks are created and destroyed with the projects. Compose cannot express
# that: the edge stack is written before any project exists, and adding a
# project would mean editing and restarting the edge, which drops every other
# project's ingress for the duration.
#
# So attachment is a separate, idempotent operation. agentic-postgres-edge.service
# reconciles all attachments after every start, and each project's unit attaches
# itself before starting and detaches after stopping.
#
# Order matters and is the reason detach exists at all. Removing a network that
# still has an endpoint fails, so a project that goes down without detaching
# leaves a network Docker will not delete and a stale endpoint on Traefik.
#
# Exit codes:
#   0  success (including "already in the desired state")
#   2  invalid operator input
#   3  missing prerequisite
#   9  the attachment could not be reconciled

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

readonly PROJECT_RENDERED_ROOT="/var/lib/agentic-postgres/rendered"

# Same shape as schemas/outputs.schema.json's projectKey. Validated before it is
# used as a path component or a Docker object name.
readonly PROJECT_KEY_PATTERN='^[a-z][a-z0-9-]{4,47}$'

ACTION=""
PROJECT_KEY=""

usage() {
  cat <<'USAGE'
Usage: bin/edge-network.sh <attach|detach|status|reconcile> [--project-key KEY]

  attach     Connect the edge proxy to this project's edge network.
  detach     Disconnect it. Run before removing the network, never after.
  status     Report whether the proxy is attached. Changes nothing.
  reconcile  Attach the proxy to every deployed project's edge network.

  --project-key KEY  Required for attach, detach and status.

Every action is idempotent. Attaching twice succeeds, and so does detaching
something that is already detached: these run from systemd on every start and
stop, where "already done" is the common case rather than an error.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'edge-network: %s\n' "$*" >&2
  exit "$code"
}

edge_container() {
  # Resolved by Compose label rather than by name. A container name is a
  # formatting convention that changes between Compose versions; the label is
  # part of the model.
  docker ps --filter 'label=com.docker.compose.project=apg-edge' \
            --filter 'label=com.docker.compose.service=traefik' \
            --format '{{.Names}}' | head -n 1
}

project_edge_network() {
  local key="$1" state="${PROJECT_RENDERED_ROOT}/$1/compose.env"
  [ -f "${state}" ] || die 3 "no runtime state for ${key}: ${state}"

  # Read as a key/value file, never sourced. Sourcing an env file executes it,
  # and this one is written by another process.
  local value
  value="$(grep -m1 '^EDGE_NETWORK_NAME=' "${state}" | cut -d= -f2- || true)"
  [ -n "${value}" ] || die 3 "${state} declares no EDGE_NETWORK_NAME."
  printf '%s' "${value}"
}

is_attached() {
  local container="$1" network="$2"
  docker inspect --format '{{json .NetworkSettings.Networks}}' "${container}" 2>/dev/null \
    | grep -q "\"${network}\""
}

parse_arguments() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help|-h) usage; exit 0 ;;
      attach|detach|status|reconcile)
        [ -z "${ACTION}" ] || die 2 "only one action may be given."
        ACTION="$1"
        shift
        ;;
      --project-key)
        [ "$#" -ge 2 ] || die 2 "--project-key requires a value."
        PROJECT_KEY="$2"
        shift 2
        ;;
      *) usage >&2; die 2 "unknown argument: $1" ;;
    esac
  done

  [ -n "${ACTION}" ] || { usage >&2; die 2 "an action is required."; }

  if [ "${ACTION}" != "reconcile" ]; then
    [ -n "${PROJECT_KEY}" ] || die 2 "${ACTION} requires --project-key."
    printf '%s' "${PROJECT_KEY}" | grep -Eq "${PROJECT_KEY_PATTERN}" \
      || die 2 "not a valid project key: ${PROJECT_KEY}"
  fi
}

main() {
  parse_arguments "$@"

  # §8.5: every command works when invoked from anywhere.
  cd "${ROOT_DIR}"

  command -v docker >/dev/null 2>&1 || die 3 "docker is not installed."

  local container
  container="$(edge_container)"
  [ -n "${container}" ] || die 3 "the edge proxy is not running; start it with bin/edge.sh up."

  case "${ACTION}" in
    status)
      local network
      network="$(project_edge_network "${PROJECT_KEY}")"
      if is_attached "${container}" "${network}"; then
        printf 'attached %s -> %s\n' "${container}" "${network}"
      else
        printf 'detached %s -> %s\n' "${container}" "${network}"
      fi
      ;;

    attach)
      [ "$(id -u)" -eq 0 ] || die 3 "must run as root."
      local network
      network="$(project_edge_network "${PROJECT_KEY}")"
      docker network inspect "${network}" >/dev/null 2>&1 \
        || die 9 "edge network does not exist: ${network}. Start the project first."

      if is_attached "${container}" "${network}"; then
        printf 'edge-network: already attached to %s\n' "${network}"
        return 0
      fi
      docker network connect "${network}" "${container}" \
        || die 9 "could not attach ${container} to ${network}"
      printf 'edge-network: attached to %s\n' "${network}"
      ;;

    detach)
      [ "$(id -u)" -eq 0 ] || die 3 "must run as root."
      local network
      network="$(project_edge_network "${PROJECT_KEY}")"
      if ! is_attached "${container}" "${network}"; then
        printf 'edge-network: already detached from %s\n' "${network}"
        return 0
      fi
      docker network disconnect "${network}" "${container}" \
        || die 9 "could not detach ${container} from ${network}"
      printf 'edge-network: detached from %s\n' "${network}"
      ;;

    reconcile)
      [ "$(id -u)" -eq 0 ] || die 3 "must run as root."
      # Runs after every edge start. A restarted proxy comes back attached only
      # to the networks its own Compose model names, which is none of the
      # projects', so without this every project loses ingress on an edge
      # restart and nothing reports it.
      local attached=0 skipped=0 directory key network
      for directory in "${PROJECT_RENDERED_ROOT}"/*/; do
        [ -d "${directory}" ] || continue
        key="$(basename "${directory}")"
        printf '%s' "${key}" | grep -Eq "${PROJECT_KEY_PATTERN}" || continue
        [ -f "${directory}compose.env" ] || continue

        network="$(grep -m1 '^EDGE_NETWORK_NAME=' "${directory}compose.env" | cut -d= -f2- || true)"
        [ -n "${network}" ] || continue

        if ! docker network inspect "${network}" >/dev/null 2>&1; then
          skipped=$((skipped + 1))
          continue
        fi
        if is_attached "${container}" "${network}"; then
          continue
        fi
        docker network connect "${network}" "${container}" \
          || die 9 "could not attach ${container} to ${network}"
        attached=$((attached + 1))
      done
      printf 'edge-network: reconciled; %d newly attached, %d not running\n' \
        "${attached}" "${skipped}"
      ;;
  esac
}

main "$@"
