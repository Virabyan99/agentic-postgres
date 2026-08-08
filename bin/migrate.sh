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
RUNTIME=0

die() { local code="$1"; shift; printf 'migrate: %s\n' "$*" >&2; exit "${code}"; }

usage() {
  cat <<'USAGE'
Usage: bin/migrate.sh --project FILE [--runtime] <subcommand>

Subcommands:
  status        List applied and pending migrations. Reads only.
  up            Apply every pending migration, in order, transactionally.
  render        Render the migration set for this project and report digests.
  freeze-lock   Write migrations/released.lock.json from a clean tree.
  verify-lock   Check the committed lock against the manifest and templates.

  --project FILE  Path to a project manifest (non-secret).
  --runtime       Read the installed rendered document under /var/lib.
  --help          Show this message.

`render` and `verify-lock` need no root and no cluster: they report what this
release would apply. `status` and `up` both run dbmate in a container against
the cluster, so both need root and a running project.

There is no `down`. Released platform migrations are fix-forward only: every
down block raises AP900, and the remedy for a mistake is a new migration.

freeze-lock is the only command that writes the lock. The gate verifies it and
never creates it, so a lock that is missing is a review that did not happen.

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
      status|up|render|freeze-lock|verify-lock)
        [ -z "${SUBCOMMAND}" ] || die 2 "one subcommand at a time."
        SUBCOMMAND="$1"; shift ;;
      down|rollback)
        die 2 "there is no '$1'. Released platform migrations are fix-forward only; write a new migration." ;;
      *) usage >&2; die 2 "unknown argument: $1" ;;
    esac
  done

  [ -n "${SUBCOMMAND}" ] || die 2 "a subcommand is required."

  # freeze-lock and verify-lock operate on the committed set, which is not a
  # property of any one project. Requiring --project there would invite an
  # operator to believe the lock is per project, which is exactly what it is
  # not (ADR 0028).
  case "${SUBCOMMAND}" in
    freeze-lock|verify-lock) : ;;
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
      "$(python_bin)" "${ROOT_DIR}/bin/migrate.py" --mode freeze-lock ;;
    verify-lock)
      "$(python_bin)" "${ROOT_DIR}/bin/migrate.py" --mode verify-lock ;;
    render|status|up)
      local key rendered_dir document
      key="$(project_key)"
      if [ "${RUNTIME}" -eq 1 ]; then
        rendered_dir="${RENDERED_ROOT}/${key}"
      else
        rendered_dir="${ROOT_DIR}/.generated/${key}"
      fi
      document="${rendered_dir}/outputs.json"
      [ -f "${document}" ] \
        || die 4 "no rendered document for ${key} at ${document}; the project was never deployed here."

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
