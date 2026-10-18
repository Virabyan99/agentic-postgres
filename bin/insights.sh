#!/usr/bin/env bash
#
# A project's statements, as the server sampled them (ADR 0278): every five
# minutes the statements your database roles and the API's request roles ran,
# the text normalised by PostgreSQL (no literal is kept), counted across resets.
# Numbers only -- nothing here tells you what to change; to change a query plan,
# write a migration in your project's set and run `apg migrate propose`. A
# window with fewer than two samples could not be determined, and says so with
# exit 6.
#
# Exit codes (runbook section 2 convention):
#   0  done
#   2  invalid input
#   3  no context, no project chosen, or no credential
#   5  refused by the server (its error word is printed)
#   6  the server could not be reached, answered something unreadable, or the
#      insights could not be determined (fewer than two samples in the window)

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  bin/insights.sh show [--project-key KEY] [--hours N] [--limit M] [--json]

  show  Your statements over the last N hours (1 to 168, default 24), the M
        that took the most time (1 to 50, default 20): calls, total and mean
        time, rows, rows per call, shared blocks read per call and the cache
        hit ratio, each counted across resets, with the normalised text and
        the role that ran it. How many samples were expected and recorded is
        said; fewer than two is "could not be determined" and exit 6.

KEY is a project key such as slot1-prod; without --project-key, the context's
project (bin/project.sh use). Accepts a person's session or a key holding
projects:read.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'insights: %s\n' "$*" >&2
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
  exec "$(python_bin)" "${ROOT_DIR}/bin/cloud.py" insights "$@"
}

main "$@"
