#!/usr/bin/env bash
#
# Log out of the management API (D2066). A password session is ended ON THE
# SERVER (DELETE /v1/sessions/current with the refresh token) and only then is
# its file removed; a server that cannot be reached leaves the session held and
# says so. A key context is forgotten, never revoked: bin/org.sh key-revoke
# revokes a key.
#
# Exit codes (runbook section 2 convention):
#   0  ended, forgotten, or nothing was held
#   2  invalid input
#   3  no context, or an unusable local file
#   5  refused by the server
#   6  the server could not be reached or answered something unreadable

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  bin/logout.sh [--json]

  End the session the context holds, on the server and then here; or forget a
  key context (the key stays valid until bin/org.sh key-revoke). --json prints
  what was ended as a document.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'logout: %s\n' "$*" >&2
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
  local argument
  for argument in "$@"; do
    case "${argument}" in
      --help | -h)
        usage
        return 0
        ;;
    esac
  done
  exec "$(python_bin)" "${ROOT_DIR}/bin/cloud.py" logout "$@"
}

main "$@"
