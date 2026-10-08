#!/usr/bin/env bash
#
# A project's compute profile on the management API (ADR 0258): read it, or ask
# for another. A change answers 202 with an operation the host's reconciler
# executes -- admission first, so a profile the server has no room for fails
# the operation `capacity_exhausted` and the project stays as it was. Resizing
# restarts the database and the services that use it; the 202 says how long
# that was measured to take, or that it has not been measured yet.
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
  bin/compute.sh get [--project-key KEY] [--json]
  bin/compute.sh set [--project-key KEY] --profile small|standard|large [--json]

  get  The project's compute profile, from its registry record.
  set  Ask for another profile; follow the operation with bin/operation.sh wait.

KEY defaults to the context's project (bin/project.sh use). A person's session,
or a key holding projects:write, may set a profile.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'compute: %s\n' "$*" >&2
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
    die 2 "a verb is required: get or set."
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
    get | set) ;;
    *) die 2 "unknown verb: $1. One of: get set" ;;
  esac
  exec "$(python_bin)" "${ROOT_DIR}/bin/cloud.py" compute "$@"
}

main "$@"
