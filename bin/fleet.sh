#!/usr/bin/env bash
#
# The fleet inventory: every deployed project on this host, in one report.
#
#   sudo bin/fleet.sh [--json] [--window HOURS]
#
# An operator's read over the deployed documents already on this host's disk,
# with live health from the doctor, the backup timers' state, and refusals by
# reason from each project's audit table (ADR 0185). It has no route, no
# service, no credential and no reader, and it writes nothing.
#
# Needs root: the deployed documents are 0600 root and the doctor's probes
# reach containers. Resolves an interpreter the way doctor.sh does, because
# sudo's secure_path hides an activated venv.
#
# Exit codes: 0 (every project read; verdicts are in the report), 2 (bad
# input), 3 (not root, or no interpreter), 4 (nothing has been deployed here).

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: sudo bin/fleet.sh [--json] [--window HOURS] [--help]

Every deployed project on this host, one block each:

  identity   key, domain, environment, and the release it runs
  health     bin/doctor.sh --project KEY --json, composed: the worst verdict,
             the counts, and each check's verdict -- live, never the deployed
             document's status blocks (ADR 0158)
  backups    the two backup timers' unit-file state (enabled, disabled, or
             absent when the units were never installed), and the age of the
             last full backup as the doctor's repository probe read it
  denials    refusals by boundary over a window, counted from
             app_private.agent_audit (ADR 0178). Counts, not a rate.

  --json           The same report as a JSON document, sorted by key.
  --window HOURS   The denial window. Default 24.

Reads the deployed documents as root, runs the doctor per project, asks
systemd about two units and the cluster about one table. Holds no credential,
serves nothing, is read by nothing, and writes nothing (FLEET-INV-002).
USAGE
}

python_bin() {
  if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
    printf '%s' "${ROOT_DIR}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    printf 'fleet: no Python interpreter found (looked for .venv/bin/python, python3).\n' >&2
    exit 3
  fi
}

main() {
  local -a passthrough=()
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help) usage; return 0 ;;
      --json) passthrough+=("--json"); shift ;;
      --window)
        [ "$#" -ge 2 ] || { printf 'fleet: --window requires a value.\n' >&2; exit 2; }
        passthrough+=("--window" "$2"); shift 2 ;;
      --window=*) passthrough+=("--window" "${1#--window=}"); shift ;;
      --root)
        [ "$#" -ge 2 ] || { printf 'fleet: --root requires a value.\n' >&2; exit 2; }
        passthrough+=("--root" "$2"); shift 2 ;;
      *) usage >&2; printf 'fleet: unknown argument: %s\n' "$1" >&2; exit 2 ;;
    esac
  done

  [ "$(id -u)" -eq 0 ] || {
    printf 'fleet: needs root: the deployed documents are 0600 root.\n' >&2
    exit 3
  }
  exec "$(python_bin)" "${ROOT_DIR}/bin/fleet.py" "${passthrough[@]}"
}

main "$@"
