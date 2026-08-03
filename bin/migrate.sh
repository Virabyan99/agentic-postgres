#!/usr/bin/env bash
#
# Migration runner. Documents the dbmate contract only; executes no migration.
#
# Exit codes: 0 (--help), 2 (bad input), 10 (unavailable this session).

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: bin/migrate.sh --help

Future behavior (Session 3 onward): run dbmate against a project's DIRECT
database endpoint.

  up            Apply all pending migrations.
  down          Roll back the most recent migration.
  status        List applied and pending migrations.
  new NAME      Create a timestamped migration file under migrations/.

  --project-dir DIR  Generated project directory to read identities from.

Contract:
  - dbmate is the platform migration engine from Session 3 onward.
  - Migrations always use the DIRECT endpoint, never the pooled endpoint;
    PgBouncer transaction pooling breaks DDL and advisory-lock semantics.
  - The migration role is the project-scoped migration_user, not a superuser
    and not the object owner.

Session 1 owns migrations/ as an empty, tracked directory only.
USAGE
}

main() {
  case "${1-}" in
    --help) usage; return 0 ;;
    "") ;;
    *) usage >&2; printf 'migrate: unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac

  cd "${ROOT_DIR}"
  printf 'migrate: migrations begin in Session 3. No migration was executed.\n' >&2
  exit 10
}

main "$@"
