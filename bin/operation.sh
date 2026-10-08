#!/usr/bin/env bash
#
# Operations on the management API (ADR 0256): every write on a project answers
# 202 with one, and the host's reconciler executes it. Read one, list an
# organisation's, wait for one to finish, or cancel one still pending.
#
# An export's download URL is handed out once, to the person who asked; a read
# here that receives it prints a notice and discards it -- bin/project.sh export
# is what fetches the archive.
#
# Exit codes (runbook section 2 convention):
#   0  done; for wait, the operation succeeded
#   2  invalid input
#   3  no context, no credential, or an unusable file
#   5  refused by the server; for wait, the operation failed or was cancelled
#      (its error code and reason are printed)
#   6  the server could not be reached or answered something unreadable --
#      for wait, the outcome could not be determined
#   7  wait stopped at its own --timeout (the operation continues)

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  bin/operation.sh show --operation ID [--json]
  bin/operation.sh list [--organization ID] [--json]
  bin/operation.sh wait --operation ID [--timeout S] [--interval S] [--json]
  bin/operation.sh cancel --operation ID [--json]

  show    One operation: its type, project, status, step, progress, result.
  list    The context's organisation's operations (or --organization's), newest first.
  wait    Read the operation every --interval seconds (5) until it is finished,
          for at most --timeout seconds (2400).
  cancel  Cancel an operation still pending: its requester, or an admin or owner.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'operation: %s\n' "$*" >&2
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
    die 2 "a verb is required: show, list, wait or cancel."
  fi
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
    show | list | wait | cancel) ;;
    *) die 2 "unknown verb: $1. One of: show list wait cancel" ;;
  esac
  exec "$(python_bin)" "${ROOT_DIR}/bin/cloud.py" operation "$@"
}

main "$@"
