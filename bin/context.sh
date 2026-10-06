#!/usr/bin/env bash
#
# What the management API client is pointed at (D2066): the endpoint, which
# credential is held (a session, a key file's path, or none), the organisation
# and the project. A local read: no server is asked, and no secret is printed --
# a key context shows the key FILE, never the key.
#
# Exit codes (runbook section 2 convention):
#   0  shown
#   2  invalid input
#   3  no context, or an unusable local file

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  bin/context.sh show [--json]

  show    The endpoint, the credential held, the organisation and the project,
          read from ${XDG_CONFIG_HOME:-$HOME/.config}/apg/context.json.
          --json prints the same as a document.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'context: %s\n' "$*" >&2
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
  exec "$(python_bin)" "${ROOT_DIR}/bin/cloud.py" context "$@"
}

main "$@"
