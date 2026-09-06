#!/usr/bin/env bash
#
# Rehearse one bounded, reversible failure and read the detection that exists
# (ADR 0190, ADR 0193). Eight scenarios; each induces exactly what it names,
# reads the reader that exists for it, reverses, verifies the reversal, and
# writes evidence/rehearsal-<key>-<scenario>-<id>.json. --plan prints the
# three phases and does nothing.
#
# What a rehearsal never does: fill a disk (the threshold is injected into the
# doctor), block archiving to the primary repository (the WAL scenario blocks
# the MIRROR's path, whose loss the archiver does not feel), or induce a second
# scenario while one is un-reversed.
#
# Root: the deployed document is 0600 root and every scenario reaches Docker,
# the doctor or host state. A human at a TTY, one scenario at a time, never
# during a backup (docs/plans/session-18-implementation-plan.md section 4).
#
# Exit codes (runbook section 2 convention):
#   0  the rehearsal ran, the reader read, and the reversal verified
#   2  invalid operator input
#   3  missing local prerequisite, or not root
#   5  refused: a rehearsal is un-reversed, or the scenario has nothing to
#      induce on this deployment
#   6  the rehearsal ran and was reversed, and the reader read nothing
#   7  the reversal did not verify; the in-progress file names what is left

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  sudo bin/rehearse.sh SCENARIO --outputs /etc/agentic-postgres/projects/<key>/outputs.json [--plan]
  sudo bin/rehearse.sh reverse

Scenarios, each with its reader:
  service-termination        SIGKILL to the health route's service; the restart
                             count, the route, and the doctor's containers and
                             route checks. Never `docker kill` (D1015).
  database-restart           docker restart of the cluster; the doctor's database,
                             containers and route checks, every dependent's restart
                             count unchanged, the agent route's 401.
  backup-credential-failure  pgbackrest check with a credential that authenticates
                             to nothing, in one exec's environment; its exit, and
                             the check with the deployed credential as the control.
  wal-archiving-failure      the MIRROR endpoint rejected on the backup network;
                             the mirror copy's exit (the unit's failure) and the
                             doctor's mirror check; the archiver check is the
                             control. Refused for a project without a mirror.
  registry-loss              the port registry moved aside; every database-ports.sh
                             verb refuses with exit 4 and none recreates it.
  disk-threshold             the doctor with --disk-warn-copies and
                             --disk-problem-copies injected; no disk is filled.
  capability-drift           a lock with a foreign hash beside the deployed
                             document; the doctor's capability drift check.
  provider-loss              recorded (D976), not induced; prints the record.

  --plan       Print induce, observe and reverse with every command; run nothing.
  reverse      Replay the reversal an interrupted rehearsal recorded in
               /etc/agentic-postgres/rehearsal-in-progress.json.

Every reading is a value this command produced (an exit code, a verdict parsed
from the doctor's document, a count, seconds); no subprocess's words are printed.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'rehearse: %s\n' "$*" >&2
  exit "$code"
}

python_bin() {
  if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
    printf '%s' "${ROOT_DIR}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    die 3 "no Python interpreter found (looked for .venv/bin/python, python3)."
  fi
}

main() {
  if [ "$#" -eq 0 ]; then
    usage >&2
    die 2 "a scenario is required."
  fi
  case "$1" in
    --help | -h) usage; return 0 ;;
  esac
  command -v docker >/dev/null 2>&1 || die 3 "docker is not installed."
  # Every argument is forwarded verbatim; the Python side owns the contract.
  PYTHONPATH="${ROOT_DIR}/src" exec "$(python_bin)" "${ROOT_DIR}/bin/rehearse.py" "$@"
}

main "$@"
