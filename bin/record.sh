#!/usr/bin/env bash
#
# The record a deployment keeps, and an operator's prune of it (ADR 0248, which
# extends ADR 0213).
#
# Two verbs. `size` reads app_private.record_size(): one line per prunable
# relation -- its rows and its oldest time -- and the pending approvals left on
# ended runs. `prune` calls ONE of five functions the database grants to nobody,
# on a horizon the operator states and a confirmation the operator types.
#
# This is ADR 0213's "human at a TTY" made a command. Nothing in this product
# prunes on its own: no unit, timer or other command calls this file.
#
# Root, because the deployed document is root-owned and the record is read
# through the database container as its superuser.
#
# Exit codes (runbook section 2 convention):
#   0  read, or pruned
#   2  invalid operator input (a missing or future horizon, a wrong --confirm)
#   3  missing local prerequisite, or not root
#   5  the database refused the prune, or the call failed
#   6  the record could not be read -- reported, never read as zero

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  sudo bin/record.sh size --project KEY [--json]
  sudo bin/record.sh prune --project KEY --what WHAT --before ISO8601 [--limit N] --confirm KEY

  size      One line per prunable relation: its rows and its oldest time, and
            the pending approvals left on ended runs (which the workflow worker
            withdraws on its idle polls). --json prints the same as a document.
            "the record could not be read" is the third answer, with exit 6.
  prune     Print the size, call one prune, print the size again.
            --what     runs         ended runs with their steps, attempts,
                                    approvals and receipts (never a queued,
                                    running or compensating run; refuses a
                                    horizon inside the last 600 seconds)
                       deliveries   delivered and dead outbound deliveries, then
                                    the events left with none
                       agents       revoked agents no run and no connector names
                       audit        agent audit rows (migration 0033)
                       idempotency  idempotency claims (0033) -- EVERY CLAIM
                                    REMOVED RE-ARMS ITS KEY
            --before   the horizon: an ISO 8601 time WITH a timezone, in the
                       past (2026-10-01T00:00:00Z). Checked before anything is
                       touched.
            --limit    at most N roots this call; call again until it removes 0.
            --confirm  the project key again, exactly.

KEY is the deployed project key (alpha-dev); its document is read from
/etc/agentic-postgres/projects/KEY/outputs.json, and the container and database
come from it. Humans, workflow definitions, connectors and the worker row are
never pruned (ADR 0248).
USAGE
}

die() {
  local code="$1"
  shift
  printf 'record: %s\n' "$*" >&2
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
    die 2 "a verb is required: size or prune."
  fi
  # --help anywhere is a read: no root, no docker, no document.
  local argument
  for argument in "$@"; do
    case "${argument}" in
      --help | -h)
        usage
        return 0
        ;;
    esac
  done
  case "$1" in
    size | prune) ;;
    *) die 2 "unknown verb: $1. One of: size prune" ;;
  esac
  command -v docker >/dev/null 2>&1 || die 3 "docker is not installed."
  exec "$(python_bin)" "${ROOT_DIR}/bin/record.py" "$@"
}

main "$@"
