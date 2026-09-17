#!/usr/bin/env bash
#
# The reading before a tag: what is about to be tagged, and what has landed
# since the last tag.
#
#   bin/apg.sh release-reading
#
# **Run it at a session close, in a full clone, before `git tag -a`** (ADR
# 0214). It prints where HEAD stands, the last tag and the VERSION it carries,
# what has landed since, the two counts nobody reconstructs by hand -- released
# migrations and ADRs, at the tag against the tree -- and the bump commit with
# everything that landed after it.
#
# **It decides nothing, and that is measured rather than modest.** Rig 28c
# classified every commit past all five of this repository's tags: release bytes
# land within one to five commits of every one of them, because the next session
# starts, so the defect that cost `1.0.1` and `1.6.2` and the ordinary
# between-releases state are the same shape. What separates them is intent, and
# intent is not in the tree. It ends by printing the three questions it cannot
# answer, which is the checklist D1424 asked about -- kept, but only where the
# facts already are.
#
# It takes no arguments and it is not in the gate: CI's suite job checks out
# without tags, so the reading cannot be taken there and wiring it in would
# print that on every run.
#
# Exit codes (runbook §2 convention):
#   0  the reading was taken, whatever it found
#   2  invalid operator input
#   3  the reading could not be taken -- not a git checkout, or this clone holds
#      no tags at all

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: bin/apg.sh release-reading

Print the reading taken before a tag is cut, from this checkout alone.

  --help  Show this message.

What it prints, in order: where HEAD stands (commit, VERSION, any tag on it);
the last tag, its commit, its date and the VERSION it carries; what has landed
since that tag, as commits, files and paths; released migrations and ADRs at
the tag against the tree; the commit that last moved VERSION, what moved with
it, and what has landed after it; and three questions it does not answer.

It reads. It writes nothing, it cuts no tag, and it makes no judgement about
whether a tag is owed -- that one is yours, and it says so rather than
inventing a verdict on a footing nobody has measured.

Run it in a full clone. A shallow checkout and `git clone --no-tags` both look
exactly like a repository that has never been tagged, so a reading taken in one
would be clean by measuring nothing; it exits 3 there instead.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'release-reading: %s\n' "$*" >&2
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
  # D1395/D1402/D1405: `--help` anywhere in the arguments is answered before
  # anything else is decided, not only in the first position.
  local argument
  for argument in "$@"; do
    case "${argument}" in
      --help | -h | help)
        usage
        return 0
        ;;
    esac
  done

  if [ "$#" -gt 0 ]; then
    usage >&2
    die 2 "this command takes no arguments (got: $*)."
  fi

  exec "$(python_bin)" "${ROOT_DIR}/bin/release-reading.py"
}

main "$@"
