#!/usr/bin/env bash
#
# Provision one project's provider resources and record what it owns.
#
# Implemented in Session 2. It was a stub returning 10 through Session 1; ADR
# 0017 records why leaving FUTURE_STUBS is legitimate and what replaced that
# assertion. A bare invocation now returns 2, because it is missing required
# input rather than unavailable.
#
# The rule that shapes everything here is §8.2's: **ownership is recorded by ID,
# never adopted by name.** If a project or identity with the expected name
# already exists but is not in our state file, that is not our resource, and
# adopting it would mean managing -- and eventually destroying -- something
# somebody else created. So the choices are: create it and record the ID, or
# refuse.
#
# Convergence is keyed narrowly on provider_inputs_sha256, over exactly the
# manifest fields that can change a provider resource. A digest over the whole
# manifest would force provider churn on every unrelated edit.
#
# Exit codes:
#   0  success
#   2  invalid operator input, or --destroy without matching confirmation
#   3  missing prerequisite, or --apply/--destroy without root
#   7  the provider rejected an operation, or state disagrees with the provider

# First executable line, deliberately. SHELLOPTS=xtrace is honoured from bash
# startup, so anything above this point would be traced to stderr.
set +x
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

MODE=""
HOST_MANIFEST=""
PROJECT_MANIFEST=""
OPERATOR_CREDENTIAL=""
CONFIRM=""

usage() {
  cat <<'USAGE'
Usage: bin/bootstrap-providers.sh --host FILE --project FILE --plan
       sudo bin/bootstrap-providers.sh --host FILE --project FILE --apply \
            --operator-credential-file FILE
       sudo bin/bootstrap-providers.sh --host FILE --project FILE --destroy \
            --confirm PROJECT_KEY

  --plan     Report what would be created or changed. Contacts the provider
             read-only and writes nothing. Needs no root.
  --apply    Create what is missing and record the resulting identifiers.
  --destroy  Remove the resources this project's state file says we own, by ID.

  --host FILE                      The host manifest.
  --project FILE                   The project manifest.
  --operator-credential-file FILE  Path to the control-plane credential.
                                   Required for --apply. Read from the file;
                                   never accepted as a value.
  --confirm PROJECT_KEY            Required for --destroy, and must match.

Running --plan twice after an --apply reports no changes. That is the property
worth having: convergence, not idempotence by accident.

Nothing here accepts a credential as an argument, and no value is printed.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'bootstrap-providers: %s\n' "$*" >&2
  exit "$code"
}

parse_arguments() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help|-h) usage; exit 0 ;;
      --plan|--apply|--destroy)
        [ -z "${MODE}" ] || die 2 "only one of --plan, --apply or --destroy may be given."
        MODE="${1#--}"
        shift
        ;;
      --host)
        [ "$#" -ge 2 ] || die 2 "--host requires a value."
        HOST_MANIFEST="$2"
        shift 2
        ;;
      --project)
        [ "$#" -ge 2 ] || die 2 "--project requires a value."
        PROJECT_MANIFEST="$2"
        shift 2
        ;;
      --operator-credential-file)
        [ "$#" -ge 2 ] || die 2 "--operator-credential-file requires a value."
        OPERATOR_CREDENTIAL="$2"
        shift 2
        ;;
      --confirm)
        [ "$#" -ge 2 ] || die 2 "--confirm requires a value."
        CONFIRM="$2"
        shift 2
        ;;
      *) usage >&2; die 2 "unknown argument: $1" ;;
    esac
  done

  [ -n "${MODE}" ] || { usage >&2; die 2 "one of --plan, --apply or --destroy is required."; }
  [ -n "${HOST_MANIFEST}" ] || die 2 "--host is required."
  [ -n "${PROJECT_MANIFEST}" ] || die 2 "--project is required."
  [ -f "${HOST_MANIFEST}" ] || die 2 "host manifest not found: ${HOST_MANIFEST}"
  [ -f "${PROJECT_MANIFEST}" ] || die 2 "project manifest not found: ${PROJECT_MANIFEST}"
}

project_key() {
  PYTHONPATH="${ROOT_DIR}/src" python - "${PROJECT_MANIFEST}" <<'PYTHON'
import sys
from pathlib import Path

from agentic_postgres.config import load_project_manifest
from agentic_postgres.naming import project_key

manifest = load_project_manifest(Path(sys.argv[1]))["project"]
print(project_key(manifest["slug"], manifest["environment"]))
PYTHON
}

main() {
  parse_arguments "$@"
  cd "${ROOT_DIR}"

  local key
  key="$(project_key)" || die 2 "could not derive the project key from ${PROJECT_MANIFEST}"

  case "${MODE}" in
    apply)
      [ "$(id -u)" -eq 0 ] || die 3 \
        "--apply requires root: it writes a credential under /etc/agentic-postgres/."
      [ -n "${OPERATOR_CREDENTIAL}" ] || die 2 \
        "--apply requires --operator-credential-file."
      [ -f "${OPERATOR_CREDENTIAL}" ] || die 2 \
        "operator credential file not found: ${OPERATOR_CREDENTIAL}"
      ;;

    destroy)
      [ "$(id -u)" -eq 0 ] || die 3 "--destroy requires root."
      # The project key said back, in full. A --force flag would be typed
      # reflexively; a name that has to match cannot be.
      [ -n "${CONFIRM}" ] || die 2 \
        "--destroy requires --confirm ${key}. Nothing was changed."
      [ "${CONFIRM}" = "${key}" ] || die 2 \
        "--confirm said ${CONFIRM} but this project is ${key}. Nothing was changed."
      ;;
  esac

  local -a arguments=(
    --host "${HOST_MANIFEST}"
    --project "${PROJECT_MANIFEST}"
    --mode "${MODE}"
  )
  [ -n "${OPERATOR_CREDENTIAL}" ] && arguments+=(--operator-credential-file "${OPERATOR_CREDENTIAL}")

  PYTHONPATH="${ROOT_DIR}/src" exec python \
    "${ROOT_DIR}/bin/bootstrap-providers.py" "${arguments[@]}"
}

main "$@"
