#!/usr/bin/env bash
#
# The documentation route: where it is, and whether it is refusing correctly.
#
# Two operations, and neither of them hands you the credential.
#
#   url    Print the documentation URL. No credential is read and none is
#          needed; this is the operation an operator actually wants most of the
#          time, and it deliberately requires no privilege at all.
#   check  Request the route WITHOUT a credential and report the status. A 401
#          carrying a Basic challenge is the correct answer, and it is the one
#          this deployment's whole documentation posture rests on.
#
# There is no operation that authenticates, and that is the design rather than a
# gap. The credential is a Basic Auth password materialized into the root plane
# for Traefik to hash (D140, ADR 0054); the documentation container never
# receives it, which is the entire point of stripping the Authorization header
# before the request reaches it. A `docs.sh open` that logged you in would have
# to read that password and put it somewhere -- a URL, an argument, a browser's
# history -- and every one of those places is worse than typing it into a prompt.
#
# What `check` proves is the negative half of SEC-DOCS-001: the route answers,
# and it refuses. An operator wanting the positive half opens the URL in a
# browser and is asked for a password, which is the same proof with a human in
# it and no credential on disk.
#
# Exit codes (runbook §2 convention):
#   0  success -- and for `check`, the route refused as it should
#   2  invalid operator input
#   3  missing local prerequisite
#   5  the deployed document is unusable
#   6  the route did not refuse: it answered without a credential

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: bin/docs.sh --project-outputs FILE (url | check)

  url     Print the documentation route's URL. Reads no credential.
  check   Request the route with no credential and report what came back. A 401
          with a Basic challenge is success; a 200 is a failure, because it
          means the route is serving the documentation to anyone.

  --project-outputs FILE  The project's deployed outputs document. The route
                          comes from routes.docs.url.

There is no operation that authenticates and no flag that prints the
documentation password. The credential lives in the root plane for the edge to
hash; the documentation container never receives it, and neither does this
command. To read the documentation, open the URL and let the browser ask.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'docs: %s\n' "$*" >&2
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

  local outputs="" operation=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help|-h)
        usage
        exit 0
        ;;
      --project-outputs)
        [ "$#" -ge 2 ] || die 2 "--project-outputs requires a file."
        outputs="$2"
        shift 2
        ;;
      url|check)
        [ -z "${operation}" ] || die 2 "only one operation may be given."
        operation="$1"
        shift
        ;;
      *)
        usage >&2
        die 2 "unknown argument: $1"
        ;;
    esac
  done

  [ -n "${outputs}" ] || die 2 "--project-outputs is required."
  [ -n "${operation}" ] || die 2 "an operation is required: url or check."
  [ -f "${outputs}" ] || die 2 "deployed document not found: ${outputs}"

  exec "$(python_bin)" "${ROOT_DIR}/bin/docs.py" \
    --project-outputs "${outputs}" "${operation}"
}

main "$@"
