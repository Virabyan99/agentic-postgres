#!/usr/bin/env bash
#
# A project's branches (ADR 0271, ADR 0272): a copy of the project's database
# restored from its own backups -- to the newest archived moment, or to a
# point inside the window `bin/project.sh backups` reads -- with its own two
# passwords and its own two names, <branch>.pool.<domain> and
# <branch>.direct.<domain>. One branch per project. A branch is NOT backed up.
#
# The passwords are made HERE and never leave this machine: `create` and
# `reset` generate both, write each once under --password-dir D as
# D/<key>/<branch>/customer_app and customer_admin (0600, never over an
# existing file; every directory made 0700), BEFORE anything is sent, and send
# only their SCRAM-SHA-256 verifiers. `bin/endpoint.sh connect --branch B`
# opens a psql through a branch's door with one of those files.
#
# `create --at T` is the restore to a point: the project itself is never
# overwritten. There is no customer verb named backup or restore -- those are
# the operator's root commands (D2437).
#
# Exit codes (runbook section 2 convention):
#   0  done
#   2  invalid input, a password file that already exists, or --confirm that
#      is not the branch's name
#   3  no context, no project chosen, no credential, or an unusable directory
#   5  refused by the server (its error word is printed: branch_limit_reached,
#      not_found, ...), or the operation failed
#   6  the server could not be reached, answered something unreadable, or an
#      outcome could not be determined
#   7  --wait stopped at its own --timeout (the operation continues)

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  bin/branch.sh create [--project-key KEY] --branch NAME --password-dir DIR [--at INSTANT] [--expires-in DURATION] [--wait] [--timeout S] [--interval S] [--json]
  bin/branch.sh list [--project-key KEY] [--json]
  bin/branch.sh show [--project-key KEY] --branch NAME [--json]
  bin/branch.sh reset [--project-key KEY] --branch NAME --password-dir DIR [--at INSTANT] [--wait] [--timeout S] [--interval S] [--json]
  bin/branch.sh delete [--project-key KEY] --branch NAME --confirm NAME [--wait] [--timeout S] [--interval S] [--json]

  create  A branch at the end of the archive, or -- with --at -- the project
          restored to INSTANT into a new branch. Two passwords are written to
          DIR/KEY/NAME/customer_app and customer_admin (0600) before anything
          is sent; they work once the operation succeeds. --expires-in
          deletes the branch after DURATION (15m to 7d, such as 2h or 3d; a
          bare number is hours).
  list    The project's branches: each one's state, the point it reached, its
          expiry and its names.
  show    One branch.
  reset   Restore the branch again -- to INSTANT or the end of the archive --
          with two new passwords (DIR must not hold the old ones); its names
          stay. Everything written to the branch since is lost.
  delete  Delete the branch, its data and its names; --confirm is its name.
          The project is untouched.

NAME is a lowercase letter then 1-11 lowercase letters or digits, never
`main`. INSTANT is UTC, YYYY-MM-DDTHH:MM:SSZ, inside the window
bin/project.sh backups reads. KEY is a project key such as slot1-prod; without
it, the context's project (bin/project.sh use). create, reset and delete need
a person's session; list and show also accept a key holding projects:read.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'branch: %s\n' "$*" >&2
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
    die 2 "a verb is required: create, list, show, reset or delete."
  fi
  local argument
  for argument in "$@"; do
    case "${argument}" in
      --help | -h)
        usage
        return 0
        ;;
    esac
  done
  case "$1" in
    create | list | show | reset | delete) ;;
    *) die 2 "unknown verb: $1. One of: create list show reset delete" ;;
  esac
  exec "$(python_bin)" "${ROOT_DIR}/bin/cloud.py" branch "$@"
}

main "$@"
