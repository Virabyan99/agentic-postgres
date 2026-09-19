#!/usr/bin/env bash
#
# Does this project fit on this node? (ADR 0221)
#
#   sudo bin/admit.sh --host host.yaml --project project.yaml [--json]
#
# The decision the deploy takes at its step 0, asked on its own and answered
# for free. It reads the node, reads what every other deployed project has
# already claimed, adds this manifest's claim, and compares the total with what
# host.yaml declares.
#
# It renders nothing, writes nothing and starts nothing. Running it before a
# deploy costs an operator a few seconds and can save a deploy that would have
# been refused three steps in.
#
# Needs root for the READING, not for the decision: the deployed documents this
# sums are 0700 root, and a run that could not read them reports every claim
# unknown and REFUSES rather than summing zero.
#
# Exit codes: 0 (admitted), 2 (bad input or manifest), 3 (not root, or no
# interpreter), 12 (admission refused -- the declared capacity cannot hold this
# project). 12 is deliberately neither 4 nor 6: a refusal is not a
# precondition an operator can go and create, and it is not a check that
# failed. It is a decision taken against a declaration.

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: sudo bin/admit.sh --host FILE --project FILE [--json]

  --host FILE      The host manifest. At schema_version 3 it declares
                   capacity; at 2 it declares nothing, and then a project with
                   no deployed document here is REFUSED and a redeploy of one
                   that has a document is admitted.
  --project FILE   The candidate project manifest. Its claim is
                   database.budget.unreclaimable_mb -- what the host must
                   actually find -- and NOT the sum of its services' memory
                   caps, which are ceilings and were never reservations.
  --json           The same decision as a JSON document.

A rehearsal may move any declared figure for one run, and every line of the
printed declaration is then marked (injected) so a rehearsal's reading can
never be mistaken for the host's:

  --declared-memory-mb N   --reserve-memory-mb N
  --declared-disk-gb N     --reserve-disk-gb N

Six labelled lines either way -- declared, reserved, committed, requested,
safe available, suggested action -- so that comparing a refusal with a later
admission is comparing two of the same thing.

Reads /proc/meminfo, the Docker data root's filesystem, every deployed
document under the project state root, and `docker inspect` for the ceilings
line. Renders nothing and writes nothing.
USAGE
}

python_bin() {
  if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
    printf '%s' "${ROOT_DIR}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    printf 'admit: no Python interpreter found (looked for .venv/bin/python, python3).\n' >&2
    exit 3
  fi
}

main() {
  local -a passthrough=()
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help) usage; return 0 ;;
      --json) passthrough+=("--json"); shift ;;
      --host|--project|--root|--declared-memory-mb|--reserve-memory-mb|--declared-disk-gb|--reserve-disk-gb)
        [ "$#" -ge 2 ] || { printf 'admit: %s requires a value.\n' "$1" >&2; exit 2; }
        passthrough+=("$1" "$2"); shift 2 ;;
      --host=*|--project=*|--root=*|--declared-memory-mb=*|--reserve-memory-mb=*|--declared-disk-gb=*|--reserve-disk-gb=*)
        passthrough+=("${1%%=*}" "${1#*=}"); shift ;;
      *) usage >&2; printf 'admit: unknown argument: %s\n' "$1" >&2; exit 2 ;;
    esac
  done

  [ "$(id -u)" -eq 0 ] || {
    printf 'admit: needs root: the deployed documents it sums are 0700 root.\n' >&2
    exit 3
  }
  exec "$(python_bin)" "${ROOT_DIR}/bin/admit.py" "${passthrough[@]}"
}

main "$@"
