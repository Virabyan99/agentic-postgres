#!/usr/bin/env bash
#
# The database migration plane (ADR 0026, ADR 0028).
#
# dbmate runs as `migration_user` over the project-internal network. That role
# has LOGIN and NOINHERIT and none of SUPERUSER, CREATEDB, CREATEROLE,
# REPLICATION or BYPASSRLS; it reaches owner authority only through a membership
# it must deliberately SET into. This script never connects as a superuser and
# never applies a statement the bootstrap plane owns.
#
# The credential never becomes a process argument. dbmate is given `--env
# APG_MIGRATION_DATABASE_URL`, a variable the runtime override fills from a
# secret file, so no connection string appears in argv, in compose.env, or in
# `docker inspect`.
#
# Flag positions are measured, not guessed (tests/contract/test_image_contracts.py):
# in dbmate 2.34.1 `--migrations-dir`, `--migrations-table`, `--no-dump-schema`
# and `--env-file` are GLOBAL and must precede the subcommand, while `--strict`
# is subcommand-only and exists on `up` and `migrate` but not on `status`.
#
# Exit codes:
#   0   success
#   2   invalid operator input
#   3   missing prerequisite, or not root
#   4   the project has no rendered state here
#   5   manifest, lock, or checksum disagreement
#   9   the cluster could not be reached
#
# This command removes nothing and rolls nothing back. Released platform
# migrations are fix-forward only; every `down` block raises AP900.

# First executable line: this handles a connection string carrying a password.
set +x
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

readonly RENDERED_ROOT="/var/lib/agentic-postgres/rendered"

SUBCOMMAND=""
PROJECT_MANIFEST=""
DECLARED_FOLLOWS=""
RUNTIME=0

die() { local code="$1"; shift; printf 'migrate: %s\n' "$*" >&2; exit "${code}"; }

usage() {
  cat <<'USAGE'
Usage: bin/migrate.sh --project FILE [--runtime] <subcommand>

Subcommands:
  status        List applied and pending migrations. Reads only.
  up            Apply every pending migration, in order, transactionally.
  render        Render the migration set for this project and report digests.
  freeze-lock   Write a released lock from a clean tree. Without --project,
                the RELEASE's: migrations/released.lock.json. With --project,
                that project's own: projects/<slug>/migrations/
                released.lock.json, and the release's is not touched.
                --follows VERSION declares which release the set was frozen
                against, instead of computing it from this checkout.
  verify-lock   Check the release's committed lock against the manifest and
                templates. With --project, check that project's own lock too,
                and lint the set -- the release's is always checked, because a
                project verb that could leave it unverified would be the one
                way to render an unlocked platform migration.

  --project FILE   Path to a project manifest (non-secret).
  --follows VERSION  With `freeze-lock --project` only: the 14-digit release
                   migration version this set was frozen against. Checked
                   against this release's own manifest, which lists every
                   release version this product has shipped.
  --runtime        Read the installed rendered document under /var/lib.
  --help           Show this message.

`render` and `verify-lock` need no root and no cluster: they report what this
release would apply. `status` and `up` both run dbmate in a container against
the cluster, so both need root and a running project.

There is no `down`. Released platform migrations are fix-forward only: every
down block raises AP900, and the remedy for a mistake is a new migration.

freeze-lock is the only command that writes a lock. The gate verifies and
never creates one, so a lock that is missing is a review that did not happen.

There are two locks when a project declares a migration set (ADR 0198): the
release's, covering the platform's own migrations, and the project's, covering
the SQL under projects/<slug>/. A project lock additionally records
follows_release_version, the release version its migrations must all sort after.

That rule was written when both sets rendered into one directory and applied
through one dbmate invocation against one migrations table. There, a project
version below an applied release version was an `up --strict` refusal on a
deployed cluster and a silent apply on a fresh one -- the same set producing two
different schemas. Since ADR 0206 each set has its own directory and its own
table and is ordered against its own applied set only, so
follows_release_version no longer prevents anything a cluster would refuse: it
RECORDS which release the set was reviewed against, and freeze-lock refuses a
set that disagrees with its own record.

Without --follows the record is COMPUTED from this checkout's newest release
version, which is right for a set authored against the release in hand. A set
authored against an EARLIER release cannot produce the truth that way -- the
freeze runs on the later checkout by construction -- so --follows DECLARES it
(ADR 0210). The lock records which of the two it holds, in
follows_release_version_source, so a reader can tell a computed record from an
asserted one. Declaring changes no refusal and no ordering: the value is a
record, and a wrong one produces a wrong record and no wrong SQL.

A fork whose domain was inside the release's own files converts by the
procedure in docs/on-ramp.md (ADR 0212), and this flag is its fifth step.

Never pass a secret value as a command-line argument.
USAGE
}

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help) usage; exit 0 ;;
      --runtime) RUNTIME=1; shift ;;
      --project)
        [ "$#" -ge 2 ] || die 2 "--project requires a value."
        PROJECT_MANIFEST="$2"; shift 2 ;;
      --follows)
        [ "$#" -ge 2 ] || die 2 "--follows requires a value."
        DECLARED_FOLLOWS="$2"; shift 2 ;;
      status|up|render|freeze-lock|verify-lock)
        [ -z "${SUBCOMMAND}" ] || die 2 "one subcommand at a time."
        SUBCOMMAND="$1"; shift ;;
      down|rollback)
        die 2 "there is no '$1'. Released platform migrations are fix-forward only; write a new migration." ;;
      *) usage >&2; die 2 "unknown argument: $1" ;;
    esac
  done

  [ -n "${SUBCOMMAND}" ] || die 2 "a subcommand is required."

  # freeze-lock and verify-lock default to the RELEASE's lock, which is not a
  # property of any one project (ADR 0028) -- so --project stays optional there
  # rather than required, and its absence still means the release's.
  #
  # ADR 0198 gives the flag a meaning it did not have: with it, these two verbs
  # act on the lock of the set that project declares. The comment this replaces
  # said requiring --project "would invite an operator to believe the lock is
  # per project, which is exactly what it is not". That is still true of the
  # release's lock and no longer true of every lock, which is why the flag is
  # optional and its two meanings are spelled out in the usage above.
  # --follows declares a PROJECT set's ordering record, so it means nothing
  # without a set and nothing on any other verb. Refused rather than ignored: a
  # flag silently dropped is how an operator comes to believe a record was
  # written that was not (ADR 0210).
  if [ -n "${DECLARED_FOLLOWS}" ]; then
    [ "${SUBCOMMAND}" = "freeze-lock" ] || \
      die 2 "--follows is only meaningful with freeze-lock; '${SUBCOMMAND}' writes no lock."
    [ -n "${PROJECT_MANIFEST}" ] || \
      die 2 "--follows declares the release a PROJECT set was frozen against, so it needs --project. The release's own lock has no such record."
  fi

  case "${SUBCOMMAND}" in
    freeze-lock|verify-lock)
      # Optional, but not unchecked: a path that does not exist must not read
      # as "the release's lock, then".
      if [ -n "${PROJECT_MANIFEST}" ] && [ ! -f "${PROJECT_MANIFEST}" ]; then
        die 2 "project manifest not found: ${PROJECT_MANIFEST}"
      fi ;;
    *)
      [ -n "${PROJECT_MANIFEST}" ] || die 2 "--project is required."
      [ -f "${PROJECT_MANIFEST}" ] || die 2 "project manifest not found: ${PROJECT_MANIFEST}" ;;
  esac
}

python_bin() {
  if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then printf '%s\n' "${ROOT_DIR}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then command -v python3
  elif command -v python >/dev/null 2>&1; then command -v python
  else die 3 "no Python interpreter found (looked for .venv/bin/python, python3, python)."
  fi
}

project_key() {
  "$(python_bin)" -c '
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1] + "/src")
from agentic_postgres import config, naming
document = config.load_project_manifest(Path(sys.argv[2]))
project = document["project"]
print(naming.project_key(project["slug"], project["environment"]))
' "${ROOT_DIR}" "${PROJECT_MANIFEST}" \
    || die 5 "the project manifest is not valid; no identity was derived from it."
}

main() {
  parse_args "$@"

  case "${SUBCOMMAND}" in
    freeze-lock)
      if [ -n "${PROJECT_MANIFEST}" ]; then
        if [ -n "${DECLARED_FOLLOWS}" ]; then
          "$(python_bin)" "${ROOT_DIR}/bin/migrate.py" --mode freeze-lock \
            --project "${PROJECT_MANIFEST}" --follows "${DECLARED_FOLLOWS}"
        else
          "$(python_bin)" "${ROOT_DIR}/bin/migrate.py" --mode freeze-lock \
            --project "${PROJECT_MANIFEST}"
        fi
      else
        "$(python_bin)" "${ROOT_DIR}/bin/migrate.py" --mode freeze-lock
      fi ;;
    verify-lock)
      if [ -n "${PROJECT_MANIFEST}" ]; then
        "$(python_bin)" "${ROOT_DIR}/bin/migrate.py" --mode verify-lock \
          --project "${PROJECT_MANIFEST}"
      else
        "$(python_bin)" "${ROOT_DIR}/bin/migrate.py" --mode verify-lock
      fi ;;
    render|status|up)
      local key rendered_dir document
      key="$(project_key)"
      if [ "${RUNTIME}" -eq 1 ]; then
        rendered_dir="${RENDERED_ROOT}/${key}"
      else
        rendered_dir="${ROOT_DIR}/.generated/${key}"
      fi
      # ADR 0199, D1060. NOT `[ -f "${document}" ]`: that answers false for a
      # missing file AND for one inside a directory this user cannot traverse,
      # so after a root deploy `op` was told the project "was never deployed
      # here" about a project deployed minutes earlier. One reader, in Python,
      # where the errno is available; it prints the path and exits 3 for
      # unreadable, 4 for absent.
      local resolved status
      if [ "${RUNTIME}" -eq 1 ]; then
        resolved="$("$(python_bin)" "${ROOT_DIR}/bin/rendered-document.py" \
          --project-key "${key}" --runtime)" || status=$?
      else
        resolved="$("$(python_bin)" "${ROOT_DIR}/bin/rendered-document.py" \
          --project-key "${key}")" || status=$?
      fi
      if [ -n "${status:-}" ]; then
        exit "${status}"
      fi
      document="${resolved}"

      # `status` reads the ledger, which means it starts a container, which
      # means it needs what any container start needs here. It was cheaper to
      # pretend otherwise while it printed a list and connected to nothing.
      if [ "${SUBCOMMAND}" = "up" ] || [ "${SUBCOMMAND}" = "status" ]; then
        [ "$(id -u)" -eq 0 ] || die 3 "'${SUBCOMMAND}' requires root: it runs a container."
        command -v docker >/dev/null 2>&1 || die 3 "docker is not on PATH."
      fi

      "$(python_bin)" "${ROOT_DIR}/bin/migrate.py" \
        --mode "${SUBCOMMAND}" --outputs "${document}" --rendered-dir "${rendered_dir}" ;;
  esac
}

main "$@"
