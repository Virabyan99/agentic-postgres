#!/usr/bin/env bash
#
# Canonical operator entry point (runbook §2 "Canonical deploy.sh grammar").
#
#   ./deploy.sh --project <project.yaml> --capabilities <capabilities.yaml> --render-only
#
# During Session 1 --render-only is mandatory. Invoking this script without it
# is not a mistake to be corrected silently: deployment genuinely begins in a
# later session, so the script exits 10 and says so.
#
# Exit codes (runbook §2 convention):
#   0   success
#   2   invalid operator input or manifest
#   3   missing local prerequisite
#   5   contract, lock, collision, or generated-output validation failure
#   10  capability intentionally unavailable in the current session

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: ./deploy.sh --project FILE --capabilities FILE --render-only

  --project FILE       Path to a project manifest (non-secret).
  --capabilities FILE  Path to a capability manifest (non-secret).
  --render-only        Required during Session 1. Validates inputs, stages
                       outputs, validates the Compose model, publishes the
                       staged set atomically, and starts no services.
  --help               Show this message.

Session 1 renders configuration only. It starts no container, provisions no
provider, and opens no database connection. Deployment begins in Session 2.

Never pass a secret value as a command-line argument.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'deploy: %s\n' "$*" >&2
  exit "$code"
}

main() {
  local project="" capabilities="" render_only=0

  if [ "$#" -eq 0 ]; then
    usage >&2
    die 2 "no arguments given."
  fi

  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help)
        usage
        return 0
        ;;
      --render-only)
        render_only=1
        shift
        ;;
      --project)
        [ "$#" -ge 2 ] || die 2 "--project requires a file path."
        project="$2"
        shift 2
        ;;
      --capabilities)
        [ "$#" -ge 2 ] || die 2 "--capabilities requires a file path."
        capabilities="$2"
        shift 2
        ;;
      --project=*)
        project="${1#--project=}"
        shift
        ;;
      --capabilities=*)
        capabilities="${1#--capabilities=}"
        shift
        ;;
      *)
        usage >&2
        die 2 "unknown argument: $1"
        ;;
    esac
  done

  [ -n "${project}" ] || die 2 "--project is required."
  [ -n "${capabilities}" ] || die 2 "--capabilities is required."

  # Manifest paths are given relative to the caller's cwd, so absolutize them
  # before changing directory. Everything after this point runs from the
  # repository root regardless of where the operator invoked the script.
  case "${project}" in /*) ;; *) project="${PWD}/${project}" ;; esac
  case "${capabilities}" in /*) ;; *) capabilities="${PWD}/${capabilities}" ;; esac
  cd "${ROOT_DIR}"

  if [ "${render_only}" -ne 1 ]; then
    die 10 "deployment is not available in Session 1; --render-only is mandatory. Deployment begins in Session 2."
  fi

  # Run 1 scope: argument grammar and the exit-10 boundary only. The render
  # pipeline lands in Run 3 and replaces this branch. Per runbook §3.2 a stub
  # must not report success for a capability that does not exist.
  die 10 "the render pipeline is not implemented yet (arrives with Run 3 of the Session 1 plan). No output was written."
}

main "$@"
