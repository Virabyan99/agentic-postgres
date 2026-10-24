#!/usr/bin/env bash
#
# Projects on the management API (ADR 0251, ADR 0256): the registry records of
# the caller's organisations, and -- since Session 38 -- the operations that
# create, sleep, wake, export and delete a project in a prepared slot, and --
# since Session 40 -- its backups and restore window (ADR 0273), and -- since
# Session 41 -- whether it sleeps after it has been idle (ADR 0276), and --
# since Session 46 -- its support bundle (ADR 0292). A write
# answers 202 with an operation the host's reconciler executes; follow it with
# bin/operation.sh wait. Nothing here reads a project's health.
#
# The project's first administrator is handed over by hash (ADR 0260): `create`
# keeps a token in the private state directory and sends only its SHA-256;
# `claim` presents the token to the PROJECT, never to the control plane -- or,
# with --token-file, the token the console showed once (ADR 0291).
#
# Exit codes (runbook section 2 convention):
#   0  done
#   2  invalid input
#   3  no context, no project chosen, no credential, or an unusable file
#   5  refused by the server (its error word is printed), or the operation failed
#   6  the server could not be reached, answered something unreadable, or an
#      outcome could not be determined (backups: the window could not be;
#      diagnostics: the readings are stale or none was recorded)
#   7  export stopped at its own --timeout (the operation continues)

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  bin/project.sh list [--organization ID] [--json]
  bin/project.sh use --project-key KEY
  bin/project.sh show [--project-key KEY] [--json]
  bin/project.sh status [--project-key KEY] [--json]
  bin/project.sh create --name NAME --profile small|standard|large --admin-username USER [--organization ID] [--json]
  bin/project.sh claim [--project-key KEY] [--token-file FILE] [--password-file FILE]
  bin/project.sh sleep [--project-key KEY] [--json]
  bin/project.sh wake [--project-key KEY] [--json]
  bin/project.sh export [--project-key KEY] --output FILE [--timeout S] [--interval S] [--json]
  bin/project.sh delete --project-key KEY --confirm KEY [--json]
  bin/project.sh backups [--project-key KEY] [--json]
  bin/project.sh diagnostics [--project-key KEY] --output FILE [--json]
  bin/project.sh idle-sleep [--project-key KEY] --minutes 15|30|60|never [--json]

  list    The projects of the context's organisation (or --organization's;
          every organisation's when the context names none).
  use     Make a project the context's, and its organisation with it.
  show    One project's registry record.
  status  Its state (creating, ready, sleeping, ..., unknown), who manages it,
          its compute profile and region.
  create  Create a project in a prepared slot. NAME is a display name; USER is
          its first administrator. The handoff token is kept in
          $XDG_CONFIG_HOME/apg/handoffs/<operation> (0600).
  claim   Once the creation has succeeded: set the administrator's password,
          from FILE (0600) or a prompt, by presenting the handoff token to the
          project itself; the token file is removed when the project accepts it.
          --token-file FILE: the token the console showed once, saved by you
          (0600); the project accepts only its own creation's token, and the
          file is yours, so it is left in place.
  sleep   Stop the project's containers, keeping them and its data.
  wake    Start them again.
  export  Archive the project's own data: waits for the operation, downloads
          the archive once without following a redirect, checks its SHA-256 and
          writes it to FILE (0600, never over an existing file).
  delete  Delete the project, its containers and data; --confirm is its key.
  backups The project's backups as the server last read them: the restore
          window (earliest ... latest) a branch can be restored to with
          bin/branch.sh create --at, or why it could not be read (exit 6).
          A branch is the test that a backup restores.
  diagnostics
          The support bundle: the checks the server last ran on the project's
          node (each verdict, its sentence and its age) and the project's
          operations, written to FILE (0600, never over an existing file).
          Exit 6 when the readings are older than 30 minutes or none was
          recorded -- the file is written either way.
  idle-sleep
          Put the project to sleep after MINUTES with no request answered
          below 400 and no connection by its own database roles, read from
          the server's five-minute samples (a sample missing or unread keeps
          it awake); never turns it off (the default). While it sleeps, its
          backups stop: its last restore point is the moment it went to
          sleep. Wake it with bin/project.sh wake.

KEY is a project key such as slot1-prod. The endpoint and the credential come
from the context (bin/login.sh). create, claim, export, delete and
diagnostics need a person's session; sleep, wake and idle-sleep also accept a key holding
projects:write.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'project: %s\n' "$*" >&2
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
    die 2 "a verb is required: list, use, show, status, create, claim, sleep, wake, export, delete, backups, diagnostics or idle-sleep."
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
    list | use | show | status | create | claim | sleep | wake | export | delete | backups | diagnostics | idle-sleep) ;;
    *) die 2 "unknown verb: $1. One of: list use show status create claim sleep wake export delete backups diagnostics idle-sleep" ;;
  esac
  exec "$(python_bin)" "${ROOT_DIR}/bin/cloud.py" project "$@"
}

main "$@"
