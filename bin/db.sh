#!/usr/bin/env bash
#
# The narrow SQL door (plan §6.1).
#
# `bin/db.sh sql` executes only generated, hash-verified files from an
# allowlist. That is the whole design. A bootstrap plane with a general SQL
# endpoint is a privilege-escalation primitive that happens to be spelled like
# an operator convenience: it runs as the superuser over the container socket,
# so anything it can be persuaded to execute runs with no policy above it.
#
# Three properties make "hash-verified from an allowlist" mean something:
#
#   * the allowlist is a fixed set of *names*, not a directory glob. A glob
#     executes whatever was dropped in the directory, which is the same door
#     with a lock painted on it.
#   * the digest is compared against the manifest that named the file, so a
#     file edited after it was rendered is refused rather than run.
#   * there is no --force, no --unsafe, and no path that takes SQL from an
#     argument or from stdin. `status` and `identity` read; `sql` runs a named
#     generated artifact; nothing else exists.
#
# Exit codes:
#   0   success
#   2   invalid operator input
#   3   missing prerequisite, or not root
#   4   the project has no rendered state here
#   5   the file is not in the allowlist, or its digest does not match
#   9   the cluster could not be reached
#
# This command removes nothing. See ADR 0030.

# First executable line: this reaches a cluster as the superuser, and tracing
# would print every expanded argument.
set +x
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

readonly RENDERED_ROOT="/var/lib/agentic-postgres/rendered"

# The complete set of files `sql` will execute, by basename. Adding an entry is
# a reviewable diff; there is no wildcard and no directory scan.
readonly ALLOWED_SQL="bootstrap.sql"

SUBCOMMAND=""
PROJECT_MANIFEST=""
RUNTIME=0
SQL_FILE=""

die() { local code="$1"; shift; printf 'db: %s\n' "$*" >&2; exit "${code}"; }

usage() {
  cat <<'USAGE'
Usage: sudo bin/db.sh --project FILE [--runtime] <subcommand>

Subcommands:
  status        Report the cluster's readiness, server version and extensions.
  identity      Print the volume's recorded project identity. Non-secret.
  sql NAME      Execute a generated, allowlisted SQL artifact by name.

  --project FILE  Path to a project manifest (non-secret).
  --runtime       Read the installed rendered document under /var/lib.
  --help          Show this message.

`sql` accepts a NAME, never a path and never SQL. The name must be in this
command's allowlist and the file's digest must match the manifest that
generated it; anything else is refused. There is no flag that relaxes either
check, and no subcommand reads SQL from an argument or from stdin.

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
      status|identity)
        [ -z "${SUBCOMMAND}" ] || die 2 "one subcommand at a time."
        SUBCOMMAND="$1"; shift ;;
      sql)
        [ -z "${SUBCOMMAND}" ] || die 2 "one subcommand at a time."
        SUBCOMMAND="sql"; shift
        [ "$#" -ge 1 ] || die 2 "sql requires the name of an allowlisted artifact."
        SQL_FILE="$1"; shift ;;
      *) usage >&2; die 2 "unknown argument: $1" ;;
    esac
  done

  [ -n "${PROJECT_MANIFEST}" ] || die 2 "--project is required."
  [ -f "${PROJECT_MANIFEST}" ] || die 2 "project manifest not found: ${PROJECT_MANIFEST}"
  [ -n "${SUBCOMMAND}" ] || die 2 "a subcommand is required."

  if [ "${SUBCOMMAND}" = "sql" ]; then
    # Checked as an exact name against the allowlist before anything touches
    # the filesystem. A name containing a separator never becomes a path here,
    # so `../../etc/anything` is refused as "not allowlisted" rather than
    # resolved and then rejected.
    case " ${ALLOWED_SQL} " in
      *" ${SQL_FILE} "*) : ;;
      *) die 5 "'${SQL_FILE}' is not an allowlisted SQL artifact. Allowed: ${ALLOWED_SQL}" ;;
    esac
  fi
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

container_of() {
  "$(python_bin)" -c '
import json, sys
print(json.load(open(sys.argv[1]))["database"]["container"])
' "$1" 2>/dev/null || die 5 "the rendered document does not name a container."
}

database_of() {
  "$(python_bin)" -c '
import json, sys
print(json.load(open(sys.argv[1]))["database"]["name"])
' "$1" 2>/dev/null || die 5 "the rendered document does not name a database."
}

main() {
  parse_args "$@"

  [ "$(id -u)" -eq 0 ] || die 3 "must run as root."
  command -v docker >/dev/null 2>&1 || die 3 "docker is not on PATH."

  local key document
  key="$(project_key)"
  if [ "${RUNTIME}" -eq 1 ]; then
    document="${RENDERED_ROOT}/${key}/outputs.json"
  else
    document="${ROOT_DIR}/.generated/${key}/outputs.json"
  fi
  [ -f "${document}" ] \
    || die 4 "no rendered document for ${key} at ${document}; the project was never deployed here."

  local container database
  container="$(container_of "${document}")"
  database="$(database_of "${document}")"

  [ "$(docker inspect --format '{{.State.Running}}' "${container}" 2>/dev/null)" = "true" ] \
    || die 9 "the container ${container} is not running; the cluster cannot be reached."

  # `docker exec -i`. Without -i stdin is not forwarded, psql reads nothing,
  # and the command exits 0 having executed nothing -- a silent success that
  # looks identical to a real one.
  case "${SUBCOMMAND}" in
    status)
      docker exec -i "${container}" psql -U postgres -d "${database}" -X -qtA \
        -c "SELECT 'server ' || current_setting('server_version');" \
        -c "SELECT 'extension ' || extname || ' ' || extversion FROM pg_extension ORDER BY extname;"
      ;;
    identity)
      docker exec -i "${container}" psql -U postgres -d "${database}" -X -qtA \
        -c "SELECT project_key || ' ' || database_name || ' ' || compose_project_name
              || ' ' || instance_uuid FROM app_private.project_identity;"
      ;;
    sql)
      local artifact
      artifact="$(dirname -- "${document}")/postgres/${SQL_FILE}"
      [ -f "${artifact}" ] || die 4 "the generated artifact is absent: ${artifact}"
      "$(python_bin)" "${ROOT_DIR}/bin/db-verify.py" --artifact "${artifact}" \
        || die 5 "the artifact's digest does not match the manifest that generated it."
      docker exec -i "${container}" psql -U postgres -d "${database}" -X -v ON_ERROR_STOP=1 \
        -qtA -f - < "${artifact}"
      ;;
  esac
}

main "$@"
