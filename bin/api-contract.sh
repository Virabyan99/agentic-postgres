#!/usr/bin/env bash
#
# Capture or compare the reviewed API surface (ADR 0050).
#
# Two modes with deliberately different trust levels, the same shape
# bin/lock-versions.sh has carried since Session 1:
#
#   --update  privileged. Runs against a deployed release, fetches the live
#             OpenAPI document over the project-internal address with a
#             short-lived documentation token, normalizes it, and STREAMS the
#             candidate to standard output. It writes no file. There is no
#             output-path option and that is the design: the redirect happens in
#             the caller's own shell, so a capture run under sudo lands owned by
#             the unprivileged source owner who has to review and commit it.
#
#   --check   compares, and has no code path that writes either contract file.
#             Offline it compares the committed snapshot against the committed
#             surface contract. Given --project-outputs it also fetches the live
#             document and compares that. The gate runs only this.
#
# The token arrives in APG_DOCS_TOKEN and is never an argument: argv is readable
# by every user on the host through `ps`, and D105's rule is that no command here
# accepts or prints a credential.
#
# Exit codes (runbook §2 convention):
#   0  success
#   2  invalid operator input
#   3  missing local prerequisite
#   5  the contracts are out of sync, or no approved snapshot exists yet
#   6  the live document disagrees with the approved snapshot

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: bin/api-contract.sh --check [--project-outputs FILE]
       sudo bin/api-contract.sh --update --project-outputs FILE > candidate.json

  --check            Compare. Never writes. With no --project-outputs the
                     comparison is offline: the committed snapshot against the
                     committed surface contract. With one, the live document is
                     fetched and compared as well.
  --update           Capture a candidate from the deployed release named by the
                     outputs document and stream it to standard output. Writes
                     no file; redirect it yourself, as yourself.
  --project-outputs FILE
                     The project's deployed outputs document. The published
                     address is read from routes.rest.url -- a deployed document
                     records what happened, where a manifest records what was
                     asked for.
  --help             Show this message.

The documentation token is read from the environment variable APG_DOCS_TOKEN.
It is never accepted as an argument and never printed.

The snapshot is a generated artifact. It cannot be written by hand and this
command will refuse one that has been: re-capture it instead.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'api-contract: %s\n' "$*" >&2
  exit "$code"
}

# Ubuntu ships no bare `python`, and sudo resets PATH to secure_path, so a venv
# the operator activated is invisible to a privileged --update. This is the trap
# five Session 2 scripts walked into and the Session 1 gate walked into again in
# Session 3 (D80).
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
  local outputs=""
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
      --project-outputs)
        [ "$#" -ge 2 ] || die 2 "--project-outputs requires a file."
        outputs="$2"
        shift 2
        ;;
      *)
        usage >&2
        die 2 "unknown argument: $1"
        ;;
    esac
  done

  [ -n "${mode}" ] || die 2 "one of --check or --update is required."

  local -a arguments=("${mode}")
  if [ -n "${outputs}" ]; then
    [ -f "${outputs}" ] || die 2 "deployed document not found: ${outputs}"
    arguments+=(--project-outputs "${outputs}")
  fi

  exec "$(python_bin)" "${ROOT_DIR}/bin/api-contract.py" "${arguments[@]}"
}

main "$@"
