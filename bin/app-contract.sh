#!/usr/bin/env bash
#
# Capture or compare the application API's reviewed OpenAPI document (D226).
#
# `bin/api-contract.sh`'s sibling, with one difference that shows in the flags:
# there is no --project-outputs and no token. PostgREST's document is generated
# by a running server from the grants it can see, so capturing it means reaching
# a deployment; FastAPI's is generated from this checkout by the same
# `create_app` the container runs, so the candidate is a pure function of the
# source and needs no host, no root and no credential.
#
#   --update  Stream a candidate to standard output. Writes no file: the
#             redirect happens in the caller's own shell, so the artefact is
#             owned by whoever has to review and commit it.
#   --check   Compare the committed snapshot against what this checkout
#             generates. Never writes. The gate runs only this.
#
# Exit codes (runbook §2 convention):
#   0  the committed snapshot matches this checkout
#   2  invalid operator input
#   3  missing local prerequisite
#   5  no approved snapshot exists yet
#   6  the committed snapshot disagrees with this checkout

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: bin/app-contract.sh --check
       bin/app-contract.sh --update > contracts/app-openapi.canonical.json

  --check    Compare. Never writes.
  --update   Stream a candidate to standard output. Redirect it yourself.
  --help     Show this message.

The snapshot is a generated artifact. It cannot be written by hand and --check
will refuse one that has been: re-capture it instead.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'app-contract: %s\n' "$*" >&2
  exit "$code"
}

# Ubuntu ships no bare `python`, and sudo resets PATH to secure_path, so a venv
# the operator activated is invisible to a privileged run. D80, and five Session
# 2 scripts walked into it before the gate did.
python_bin() {
  if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
    printf '%s' "${ROOT_DIR}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  elif command -v python >/dev/null 2>&1; then
    command -v python
  else
    die 3 "no Python interpreter found (looked for .venv/bin/python, python3, python)."
  fi
}

main() {
  if [ "$#" -eq 0 ]; then
    usage >&2
    die 2 "one of --check or --update is required."
  fi

  local mode=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help|-h)
        usage
        exit 0
        ;;
      --check|--update)
        [ -z "${mode}" ] || die 2 "--check and --update are mutually exclusive."
        mode="$1"
        shift
        ;;
      *)
        usage >&2
        die 2 "unknown argument: $1"
        ;;
    esac
  done

  [ -n "${mode}" ] || die 2 "one of --check or --update is required."

  exec "$(python_bin)" "${ROOT_DIR}/bin/app-contract.py" "${mode}"
}

main "$@"
