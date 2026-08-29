#!/usr/bin/env bash
#
# What an upgrade would do, computed before anything is mutated (ADR 0162).
#
#   bin/upgrade.sh check --project <key>    Can this release be compared with
#                                           what is installed? Reads only.
#   bin/upgrade.sh plan  --project <key>    What would change, and may it
#                                           proceed. Reads only.
#   bin/upgrade.sh verify --project <key>   After an upgrade: does the installed
#                                           release match this checkout. Reads only.
#
# **Every verb reads. None of them mutates anything, ever.** That is not a
# convention here, it is the whole point: `deploy.sh --through-session` performs
# the upgrade, and this command exists so that an operator knows what it will do
# first. A verb here that wrote something would make "produce a plan before
# mutating" unenforceable by the thing that produces the plan.
#
# The comparison is `rendered(installed)` against `rendered(candidate)` -- two
# documents of the SAME kind (D732, D733). The deployed document is read only for
# the observation half of `check`, which is ADR 0158's split: it is the address
# book, not the diagnosis.
#
# Reads the installed rendered document under the project state root, which is
# root-owned, so `check` and `plan` need root on a host. In a checkout they run
# unprivileged against `--installed`, which is what makes the refusal half
# provable with no host.
#
# Prints no environment variables and reads no secret material. A rendered
# document holds secret NAMES and no values (`secrets.required_names`), and this
# prints paths and digests, never a generation's contents.
#
# Exit codes: 0 (the plan may proceed), 2 (bad input), 3 (missing local
# prerequisite), 4 (nothing installed for that project here), 6 (the plan is
# blocked or could not be computed).

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: bin/upgrade.sh <verb> --project KEY [--installed FILE] [--candidate FILE]
                      [--json] [--help]

Verbs:
  check      Can a comparison be made at all? Reports what is installed, what
             this release is, and whether the two can be compared. A missing or
             unreadable installed document is `undetermined`, which blocks --
             it is not "no changes detected" (ADR 0162).

  plan       The full comparison: every leaf that differs, the change classes
             they establish, the bump this release proposes, the bump those
             changes require, and whether the first covers the second. Refuses
             before any mutation; performs none itself.

  verify     After `deploy.sh --through-session`: whether the release installed
             for this project is the one this checkout would render.

Options:
  --project KEY     The project to plan for. Required.
  --installed FILE  Read the installed rendered document from here instead of
                    the project state root. For a checkout, and for rehearsal.
  --candidate FILE  Read the candidate rendered document from here instead of
                    rendering one. For a checkout, and for rehearsal.
  --json            Machine-readable output on stdout. Human-readable otherwise.

Reads only. To perform an upgrade, run ./deploy.sh --through-session N after
this reports a plan that may proceed.
USAGE
}

python_bin() {
  if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
    printf '%s' "${ROOT_DIR}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    printf 'upgrade: no Python interpreter found (looked for .venv/bin/python, python3).\n' >&2
    exit 3
  fi
}

main() {
  if [ "$#" -eq 0 ]; then
    usage >&2
    exit 2
  fi

  case "$1" in
    --help | -h | help)
      usage
      exit 0
      ;;
    check | plan | verify) ;;
    *)
      printf 'upgrade: unknown verb %s. Expected check, plan or verify.\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac

  exec "$(python_bin)" "${ROOT_DIR}/bin/upgrade.py" "$@"
}

main "$@"
