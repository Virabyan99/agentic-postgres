#!/usr/bin/env bash
#
# A project's monitoring signals (ADR 0279): a short list of readings the server
# already records -- the newest usage sample, the last hour's usage, the last
# backups reading, the newest insight sample -- each with when it was read and
# where it comes from, or "not read" with the reason. No threshold and no alert:
# the reading and its age.
#
# Exit codes (runbook section 2 convention):
#   0  done
#   2  invalid input
#   3  no context, no project chosen, or no credential
#   5  refused by the server (its error word is printed)
#   6  the server could not be reached or answered something unreadable

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  bin/monitoring.sh show [--project-key KEY] [--json]

  show  Each signal -- state, database bytes, backup repository bytes,
        customer connections, the last hour's requests and DB time, the
        backups' status, the newest recoverable moment, the newest full
        backup, when insights were last sampled -- with its reading and when
        it was read, or why it was not read, and the table it comes from.

KEY is a project key such as slot1-prod; without --project-key, the context's
project (bin/project.sh use). Accepts a person's session or a key holding
projects:read.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'monitoring: %s\n' "$*" >&2
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
    die 2 "a verb is required: show."
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
    show) ;;
    *) die 2 "unknown verb: $1. One of: show" ;;
  esac
  exec "$(python_bin)" "${ROOT_DIR}/bin/cloud.py" monitoring "$@"
}

main "$@"
