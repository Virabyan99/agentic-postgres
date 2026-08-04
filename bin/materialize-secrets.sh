#!/usr/bin/env bash
#
# Fetch declared secrets and write them as individual files in a new immutable
# generation (ADR 0010).
#
# This is the script that holds real secret values, so its rules are stricter
# than anything else here:
#
#   * No secret value is ever an argument, an environment variable, or a log
#     line. Values move from the API into Python memory and out to a file.
#   * Tracing is off for the whole run. `set -x` here would print the Python
#     invocation, and while that carries no value today, a future edit that put
#     one on the command line would leak silently rather than loudly.
#   * A generation is written complete, fsynced, and then made active by an
#     atomic rename. A container can never observe a half-written generation.
#   * Files are owned by the consuming UID and mode 0400 before Compose mounts
#     them. Compose's own uid/gid/mode fields are not relied upon (§4.9).
#
# Exit codes:
#   0  success
#   2  invalid operator input
#   3  missing prerequisite, or not root
#   8  a secret could not be fetched or written

# First executable line, deliberately. A caller can export SHELLOPTS=xtrace and
# bash honours it from startup, so anything above this point would be traced to
# stderr -- and in a script that handles credentials, "anything" is too much.
set +x
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

PROJECT_MANIFEST=""
REQUIREMENTS=""
SESSION=""
DRY_RUN=0

usage() {
  cat <<'USAGE'
Usage: sudo bin/materialize-secrets.sh --project FILE --requirements FILE --session N
       bin/materialize-secrets.sh --project FILE --requirements FILE --session N --plan

  --project FILE       The project manifest.
  --requirements FILE  The secret contract (secrets.required.yaml).
  --session N          Materialize secrets introduced at or before session N.
  --plan               Report which secrets would be written, and where, without
                       contacting the provider or writing anything.

No credential is accepted as an argument. The provider credential is read from
/etc/agentic-postgres/credentials/<project-key>/, root-only, which is where
bin/bootstrap-providers.sh --apply put it.

Each run writes a new generation directory and then makes it active with an
atomic rename, so a container never sees a partially written set. Previous
generations are left in place; they are what a rollback restores.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'materialize-secrets: %s\n' "$*" >&2
  exit "$code"
}

parse_arguments() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help|-h) usage; exit 0 ;;
      --project)
        [ "$#" -ge 2 ] || die 2 "--project requires a value."
        PROJECT_MANIFEST="$2"
        shift 2
        ;;
      --requirements)
        [ "$#" -ge 2 ] || die 2 "--requirements requires a value."
        REQUIREMENTS="$2"
        shift 2
        ;;
      --session)
        [ "$#" -ge 2 ] || die 2 "--session requires a value."
        SESSION="$2"
        shift 2
        ;;
      --plan) DRY_RUN=1; shift ;;
      *) usage >&2; die 2 "unknown argument: $1" ;;
    esac
  done

  [ -n "${PROJECT_MANIFEST}" ] || die 2 "--project is required."
  [ -n "${REQUIREMENTS}" ] || die 2 "--requirements is required."
  [ -n "${SESSION}" ] || die 2 "--session is required."

  case "${SESSION}" in
    ''|*[!0-9]*) die 2 "--session must be a positive integer: ${SESSION}" ;;
  esac

  [ -f "${PROJECT_MANIFEST}" ] || die 2 "project manifest not found: ${PROJECT_MANIFEST}"
  [ -f "${REQUIREMENTS}" ] || die 2 "secret contract not found: ${REQUIREMENTS}"
}

# Interpreter resolution, in this order and for these reasons:
#
#   1. the repository's own venv, because sudo resets PATH to secure_path and a
#      venv the operator activated is therefore invisible to this script;
#   2. python3, because Ubuntu ships no bare `python` and has not for years;
#   3. python, for a machine where the venv is already on PATH.
#
# Assuming a bare `python` is a standing trap this repository documents, and
# five Session 2 scripts walked into it. It fails only on a host, only under
# sudo, and reports `python: command not found` from inside a heredoc.
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
  parse_arguments "$@"

  if [ "${DRY_RUN}" -eq 0 ]; then
    [ "$(id -u)" -eq 0 ] || die 3 \
      "must run as root: secret files are owned by their consuming UID and written under /var/lib."
  fi

  cd "${ROOT_DIR}"

  # The work is one transaction -- fetch every value, write the whole
  # generation, fsync, rename -- so it belongs in one process. Splitting it
  # across shell and Python would put the rollback boundary between the write
  # and the activation, which is the one place it must not be.
  local -a arguments=(
    --project "${PROJECT_MANIFEST}"
    --requirements "${REQUIREMENTS}"
    --session "${SESSION}"
  )
  [ "${DRY_RUN}" -eq 1 ] && arguments+=(--plan)

  PYTHONPATH="${ROOT_DIR}/src" exec "$(python_bin)" \
    "${ROOT_DIR}/bin/materialize-secrets.py" "${arguments[@]}"
}

main "$@"
