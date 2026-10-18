#!/usr/bin/env bash
#
# The telemetry plane: ClickStack on the host (Session 42, ADR 0277).
#
# One per host, beside the edge. It holds D1918's lines for the operator --
# ClickHouse (7 days), HyperDX (its own login), MongoDB (HyperDX's state) and a
# gateway that is the projects' own pinned collector -- and nothing a customer
# reads. No published port, no route. A project never depends on it.
#
#   up      Ask admission first: the plane is charged at its CEILINGS and
#           refused with exit 12 when it does not fit (ADR 0221 as amended).
#           Then ensure the three networks (a lost create is read again,
#           D2563), make HyperDX's session secret once (0440 root:1000 -- the
#           image runs as uid 1000), render ClickHouse's users for the real
#           subnet, record the charge in state.json, and start the model.
#   down    Stop it. Volumes are kept (the operator's saved searches and up to
#           7 days of lines) and so are the networks (projects' collectors sit
#           on the ingest one). The charge is removed.
#   status  Each container, its limits and health; HyperDX's address on
#           apg-telemetry-ui for the operator's SSH forward; the charge.
#
# Exit codes:
#   0  success          2  invalid operator input    3  missing prerequisite
#   9  the plane could not be brought to the requested state
#   12 admission refused: the declared capacity cannot hold the plane

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

readonly STATE_DIR="/etc/agentic-postgres/telemetry"
readonly SECRET_FILE="${STATE_DIR}/hyperdx-session"
readonly USERS_FILE="${STATE_DIR}/clickhouse-users.xml"
readonly STATE_FILE="${STATE_DIR}/state.json"
readonly SECRET_GID=1000

# shellcheck source=bin/lib/telemetry-network.sh
. "${ROOT_DIR}/bin/lib/telemetry-network.sh"

ACTION=""
HOST_MANIFEST=""

usage() {
  cat <<'USAGE'
Usage: sudo bin/telemetry.sh --host FILE <up|down|status>

  up      Admit the plane (exit 12 when it does not fit), ensure its networks,
          make HyperDX's session secret once, render ClickHouse's users, record
          the charge and start ClickHouse, MongoDB, the gateway and HyperDX.
  down    Stop it. Volumes and networks are kept; the charge is removed.
  status  Containers, limits and health; HyperDX's address for the SSH forward.

  --host FILE  The host manifest. Required.

HyperDX is reached only by the operator's forward, e.g.
  ssh -L 18080:<address status prints>:8080 op@<host>
then http://localhost:18080 (its cookie is Domain=localhost). It admits ONE
team: register immediately after the first `up`.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'telemetry: %s\n' "$*" >&2
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
      up|down|status)
        [ -z "${ACTION}" ] || die 2 "only one action may be given."
        ACTION="$1"
        shift
        ;;
      *) usage >&2; die 2 "unknown argument: $1" ;;
    esac
  done
  [ -n "${ACTION}" ] || { usage >&2; die 2 "an action is required."; }
  [ -n "${HOST_MANIFEST}" ] || die 2 "--host is required."
  [ -f "${HOST_MANIFEST}" ] || die 2 "host manifest not found: ${HOST_MANIFEST}"
}

# The edge's interpreter order, for the edge's reasons (bin/edge.sh).
python_bin() {
  if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
    printf '%s' "${ROOT_DIR}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    die 3 "no Python interpreter found (looked for .venv/bin/python, python3)."
  fi
}

compose() {
  "${ROOT_DIR}/bin/compose.sh" --telemetry "$@"
}

require_root() {
  [ "$(id -u)" -eq 0 ] || die 3 "$1 requires root."
}

do_up() {
  require_root "up"
  command -v docker >/dev/null 2>&1 || die 3 "docker is not installed."

  # Admission FIRST: nothing below runs for a plane that does not fit.
  local admitted=0
  "$(python_bin)" "${ROOT_DIR}/bin/telemetry.py" admit --host "${HOST_MANIFEST}" < /dev/null \
    || admitted=$?
  [ "${admitted}" -eq 0 ] || exit "${admitted}"

  ensure_telemetry_network apg-telemetry-ingest yes || die 9 "the ingest network could not be ensured."
  ensure_telemetry_network apg-telemetry yes || die 9 "the telemetry network could not be ensured."
  ensure_telemetry_network apg-telemetry-ui no || die 9 "the UI network could not be ensured."

  install -d -m 0755 -o root -g root "${STATE_DIR}"
  if [ ! -f "${SECRET_FILE}" ]; then
    # Made once and kept: a new value would log the operator out of HyperDX.
    # Never printed, never in an argument or the compose file (D2578).
    ( umask 077 && head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' > "${SECRET_FILE}" )
  fi
  chown "root:${SECRET_GID}" "${SECRET_FILE}"
  chmod 0440 "${SECRET_FILE}"

  local subnet
  subnet="$(docker network inspect --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}' apg-telemetry)" \
    || die 9 "the telemetry network's subnet could not be read."
  "$(python_bin)" "${ROOT_DIR}/bin/telemetry.py" render-users --subnet "${subnet}" \
    --out "${USERS_FILE}" < /dev/null || die 9 "ClickHouse's users could not be rendered."
  "$(python_bin)" "${ROOT_DIR}/bin/telemetry.py" write-state --out-dir "${STATE_DIR}" < /dev/null \
    || die 9 "the charge could not be recorded."

  if ! compose --runtime up -d --wait; then
    printf '\n--- why: last lines from each telemetry container ---\n' >&2
    local container
    for container in $(compose --runtime ps --all --quiet 2>/dev/null); do
      printf '\n== %s ==\n' \
        "$(docker inspect "${container}" --format '{{.Name}} {{.State.Status}}' 2>/dev/null)" >&2
      docker logs --tail 15 "${container}" 2>&1 | tail -15 >&2 || true
    done
    die 9 "the telemetry plane did not become healthy."
  fi
  printf 'telemetry: up; HyperDX at %s:8080 on apg-telemetry-ui (the SSH forward)\n' "$(ui_address)"
}

do_down() {
  require_root "down"
  compose --runtime down || die 9 "the telemetry plane did not stop cleanly."
  rm -f "${STATE_FILE}"
  printf 'telemetry: down; volumes and networks kept, the charge removed.\n'
}

ui_address() {
  docker inspect --format '{{(index .NetworkSettings.Networks "apg-telemetry-ui").IPAddress}}' \
    apg-telemetry-hyperdx-1 2>/dev/null || printf 'unknown'
}

do_status() {
  require_root "status"
  local container
  for container in $(compose --runtime ps --all --quiet 2>/dev/null); do
    docker inspect --format \
      '{{.Name}} {{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} mem_limit={{.HostConfig.Memory}} pids_limit={{.HostConfig.PidsLimit}} nanocpus={{.HostConfig.NanoCpus}}' \
      "${container}" 2>/dev/null || printf '%s (could not be read)\n' "${container}"
  done
  printf 'hyperdx (forward) %s:8080 on apg-telemetry-ui\n' "$(ui_address)"
  if [ -f "${STATE_FILE}" ]; then
    printf 'charge            %s\n' "$(grep -o '"charge_mb": [0-9]*' "${STATE_FILE}" || printf 'unreadable')"
  else
    printf 'charge            none (not installed)\n'
  fi
}

main() {
  parse_arguments "$@"
  cd "${ROOT_DIR}"
  case "${ACTION}" in
    up) do_up ;;
    down) do_down ;;
    status) do_status ;;
  esac
}

main "$@"
