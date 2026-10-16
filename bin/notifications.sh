#!/usr/bin/env bash
#
# An organisation's notifications (ADR 0275), newest first: one for every
# finished operation -- its type, its project, how it ended and why it was
# requested -- and the daily notice of a shown plan limit passed at 80%.
# In-app only: nothing is mailed, and there is no read state.
#
# Exit codes (runbook section 2 convention):
#   0  done
#   2  invalid input
#   3  no context, no organisation chosen, or no credential
#   5  refused by the server (its error word is printed)
#   6  the server could not be reached or answered something unreadable

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  bin/notifications.sh list [--organization ID] [--limit N] [--json]

  list  The newest N notifications (1 to 200, default 50): when, which
        project, what kind, and its sentence. A notification names an
        operation's type and outcome; it never carries a credential, an
        address or a result value.

ID is an organisation id; without it, the context's (bin/org.sh use).
Accepts a person's session or a key holding organizations:read.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'notifications: %s\n' "$*" >&2
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
    die 2 "a verb is required: list."
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
    list) ;;
    *) die 2 "unknown verb: $1. One of: list" ;;
  esac
  exec "$(python_bin)" "${ROOT_DIR}/bin/cloud.py" notifications "$@"
}

main "$@"
