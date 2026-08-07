#!/usr/bin/env bash
#
# The cluster bootstrap plane (ADR 0026, plan §6.1).
#
# Root-controlled and container-local. It reaches the cluster over the Unix
# socket inside the container as the OS `postgres` user, and it is reachable by
# no runtime service. It creates or verifies what a migration is not allowed to:
# the thirteen roles and their membership options, the identity sentinel, the
# `extensions` schema and pgvector, and the database-level privilege posture.
#
# Why those and not more. Everything here needs authority the migration plane
# deliberately does not have -- CREATE ROLE, and superuser for an untrusted
# extension. pgvector's CREATE EXTENSION was measured to require superuser, so
# a migration that tried it would fail on a fresh cluster asking for exactly the
# authority ADR 0026 exists to withhold.
#
# This is not a general-purpose SQL endpoint. It executes generated statements
# it built itself; `bin/db.sh sql` is the only path that runs a file, and it
# runs only hash-verified files from an allowlist.
#
# --check is the default and changes nothing, following bin/provision-host.sh.
# Argument errors exit 2 before the privilege check exits 3, so an operator
# learns they mistyped a flag without first obtaining root.
#
# Exit codes:
#   0   success, or --check found everything in policy
#   2   invalid operator input
#   3   missing prerequisite, or not root
#   4   the project has no rendered state here; it was never deployed
#   5   the rendered document is not usable
#   6   --check found a violation
#   9   the cluster could not be reached
#   11  project-identity mismatch against an existing volume (ADR 0031)
#
# Nothing here removes a volume, under any flag. See ADR 0030.

# First executable line. This handles a superuser password and a role
# credential, and `set -x` would print every expanded argument -- including
# them -- to stderr and into any journal collecting it.
set +x
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

readonly STATE_ROOT="/etc/agentic-postgres/projects"
readonly RENDERED_ROOT="/var/lib/agentic-postgres/rendered"

MODE="check"
PROJECT_MANIFEST=""
RUNTIME=0

die() { local code="$1"; shift; printf 'postgres-bootstrap: %s\n' "$*" >&2; exit "${code}"; }

usage() {
  cat <<'USAGE'
Usage: sudo bin/postgres-bootstrap.sh --project FILE [--runtime] [--check|--apply]

  --project FILE  Path to a project manifest (non-secret).
  --runtime       Read the installed rendered document under /var/lib rather
                  than the repository's .generated/ directory.
  --check         Report what differs and change nothing. This is the default.
  --apply         Create or converge the roles, schemas, extension and grants.
  --help          Show this message.

What it does, and does not:

  Creates or verifies the thirteen project roles with their membership
  options, the identity sentinel, the `extensions` schema owned by the object
  owner, pgvector at the locked version, and the database-level CREATE,
  TEMPORARY and CONNECT posture.

  It does NOT apply migrations -- that is bin/migrate.sh, running as
  migration_user over the project network -- and it does not remove a volume
  under any flag.

A project-identity mismatch against an existing volume stops with exit 11 and
is never adopted. The remedy is selecting the correct volume or a reviewed
migration plan; there is no flag that overrides it.

Never pass a secret value as a command-line argument.
USAGE
}

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help) usage; exit 0 ;;
      --check) MODE="check"; shift ;;
      --apply) MODE="apply"; shift ;;
      --runtime) RUNTIME=1; shift ;;
      --project)
        [ "$#" -ge 2 ] || die 2 "--project requires a value."
        PROJECT_MANIFEST="$2"; shift 2 ;;
      *) usage >&2; die 2 "unknown argument: $1" ;;
    esac
  done

  [ -n "${PROJECT_MANIFEST}" ] || die 2 "--project is required."
  [ -f "${PROJECT_MANIFEST}" ] || die 2 "project manifest not found: ${PROJECT_MANIFEST}"
}

python_bin() {
  if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then printf '%s\n' "${ROOT_DIR}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then command -v python3
  elif command -v python >/dev/null 2>&1; then command -v python
  else die 3 "no Python interpreter found (looked for .venv/bin/python, python3, python)."
  fi
}

# The project key is derived once, by the package, from the manifest. Deriving
# it here with a shell expression would be a second derivation path for a name
# (ADR 0002), and the failure that produces is a bootstrap that hardens one
# project's database while reporting another's key.
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

outputs_path() {
  local key="$1"
  if [ "${RUNTIME}" -eq 1 ]; then
    printf '%s/%s/outputs.json\n' "${RENDERED_ROOT}" "${key}"
  else
    printf '%s/.generated/%s/outputs.json\n' "${ROOT_DIR}" "${key}"
  fi
}

main() {
  parse_args "$@"

  # Privilege is checked after argument validation, deliberately. An operator
  # who mistyped a flag should learn that without first being told to obtain
  # root and try again.
  [ "$(id -u)" -eq 0 ] || die 3 "must run as root."

  command -v docker >/dev/null 2>&1 || die 3 "docker is not on PATH."

  local key document
  key="$(project_key)"
  document="$(outputs_path "${key}")"
  [ -f "${document}" ] \
    || die 4 "no rendered document for ${key} at ${document}; the project was never deployed here."

  "$(python_bin)" "${ROOT_DIR}/bin/postgres-bootstrap.py" \
    --outputs "${document}" \
    --mode "${MODE}" \
    --state-root "${STATE_ROOT}"
}

main "$@"
