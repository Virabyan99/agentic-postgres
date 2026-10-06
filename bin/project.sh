#!/usr/bin/env bash
#
# Projects on the management API (ADR 0251): the registry records of the
# caller's organisations -- what the operator adopted from each project's
# deployed document. A record, not a state: nothing here reads a project's
# health, and nothing creates one (POST /v1/projects is not available, D2067).
#
# Exit codes (runbook section 2 convention):
#   0  done
#   2  invalid input
#   3  no context, no project chosen, no credential, or an unusable file
#   5  refused by the server (its error word is printed)
#   6  the server could not be reached or answered something unreadable

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  bin/project.sh list [--organization ID] [--json]
  bin/project.sh use --project-key KEY
  bin/project.sh show [--project-key KEY] [--json]

  list    The projects of the context's organisation (or --organization's;
          every organisation's when the context names none).
  use     Make a project the context's, and its organisation with it.
  show    One project's registry record: key, organisation, slug,
          environment, domain, template version, source commit, adoption time.

KEY is a project key such as alpha-dev. The endpoint and the credential come
from the context (bin/login.sh).
USAGE
}

die() {
  local code="$1"
  shift
  printf 'project: %s\n' "$*" >&2
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
    die 2 "a verb is required: list, use or show."
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
    list | use | show) ;;
    *) die 2 "unknown verb: $1. One of: list use show" ;;
  esac
  exec "$(python_bin)" "${ROOT_DIR}/bin/cloud.py" project "$@"
}

main "$@"
