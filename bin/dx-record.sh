#!/usr/bin/env bash
#
# Read a second walk's record: what it says, and what this checkout says back.
#
#   bin/apg.sh dx-record digest --record FILE   fill in the documents' digests
#   bin/apg.sh dx-record check  --record FILE   the four readings, and a verdict
#
# **A walker runs this before they hand the record over** (ADR 0207 §3). The
# same four functions decide `DX-001` in the host sweep, so a walker who could
# not run them would be marked by a rubric they never saw -- an undocumented
# step inside the claim about undocumented steps.
#
# It reads. It writes exactly one thing, and only when asked: `digest` rewrites
# the record's `documents_read` member in place, because typing four sha256 sums
# by hand is a step nobody performs correctly and a wrong digest reads exactly
# like a document that moved.
#
# Exit codes (runbook §2 convention):
#   0  the record is clean
#   2  invalid operator input, or a record that cannot be read at all
#   3  the record names a document this checkout does not have
#   5  the record is readable and one of the readings has findings

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: bin/apg.sh dx-record digest --record FILE
       bin/apg.sh dx-record check  --record FILE [--project-slug SLUG]

Read the record a second walk writes, the way the sweep will read it.

  digest    Rewrite the record's `documents_read` member from this checkout,
            and print what was digested. Run it in the walk's own clone, at the
            end of the walk, before handing the record over.
  check     Print the four readings -- source edits, commands the documentation
            does not name, documents that moved since the walk, and the shape
            of `followed_by` -- and a verdict. Exit 0 when all four are clean.

  --record FILE       The record. A JSON object; docs/second-walk.md gives its
                      schema and the task statement a walker is handed.
  --project-slug SLUG Override the record's own `project_slug`. For a record
                      written before the field existed; the record's own value
                      is used otherwise, and either way it is validated before
                      it becomes a directory prefix.
  --help              Show this message.

A source edit is decided by PATH: anything under `projects/<slug>/` is the
walker's own, and so are the five operator inputs at the checkout root. Anything
else is a file this repository ships, and editing one forks the template --
which is what DX-001 says a reader does not have to do.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'dx-record: %s\n' "$*" >&2
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
    die 2 "a verb is required: digest or check."
  fi

  case "$1" in
    --help | -h | help)
      usage
      return 0
      ;;
    check | digest) ;;
    *)
      usage >&2
      die 2 "unknown verb: $1 (digest or check)."
      ;;
  esac

  exec "$(python_bin)" "${ROOT_DIR}/bin/dx-record.py" "$@"
}

main "$@"
