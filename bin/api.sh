#!/usr/bin/env bash
#
# Call the published REST surface through enumerated operations.
#
# There is no --url, no --method, no --header and no way to pass an option
# through to a transfer library. Each operation names one path and one method,
# both derived from the deployed document and the reviewed surface contract; the
# caller chooses which operation, never what request.
#
# That is narrower than a debugging tool wants to be, and the narrowness is the
# point. A broker that will issue any request against a project's API is a
# credential holder that will do anything the credential can -- which makes it,
# in an incident, indistinguishable from the thing being investigated.
#
# The token is read from APG_API_TOKEN and never printed. bin/dev-token.sh puts
# it there; this command never mints one and never touches the signing key:
#
#   sudo bin/dev-token.sh --project-outputs FILE --role authenticated -- \
#        bin/api.sh --project-outputs FILE list-notes
#
# Exit codes (runbook §2 convention):
#   0  success
#   2  invalid operator input
#   3  missing local prerequisite
#   5  the deployed document is unusable
#   6  the service refused the request

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: bin/api.sh --project-outputs FILE OPERATION [OPTIONS]

  Operations:
    openapi              GET /       -- the served OpenAPI document
    list-notes           GET /notes
    list-tasks           GET /tasks
    create-note          POST /rpc/create_note        --title T [--content C]
    update-task-status   POST /rpc/update_task_status --task-id U
                                                      --expected-status S
                                                      --new-status S

  --project-outputs FILE  The project's deployed outputs document. The route
                          comes from routes.rest.url -- an observation, not a
                          plan.

  A status must be one of the values contracts/postgrest-api-surface.yaml
  declares for task_status. The list is read from that file rather than written
  here, because a second copy of an enum is a second authority and this one
  would be the permissive half.

  Ownership is never accepted from the caller: the write RPCs derive it from the
  request identity, which is the whole reason they are RPCs and not table writes.

The bearer token is read from the environment variable APG_API_TOKEN. It is
never accepted as an argument and never printed. Run this under
bin/dev-token.sh, which puts one there and exec's this command.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'api: %s\n' "$*" >&2
  exit "$code"
}

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
    die 2 "--project-outputs and an operation are required."
  fi

  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
  esac

  # Every argument is forwarded, and the Python argument parser is what refuses
  # an unknown one -- `choices` on the operation is a closed set, so an
  # operation this file does not list cannot be reached by spelling it here.
  exec "$(python_bin)" "${ROOT_DIR}/bin/api.py" "$@"
}

main "$@"
