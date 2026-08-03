#!/usr/bin/env bash
#
# Disposable restore rehearsal. Documents the contract only; restores nothing.
#
# Exit codes: 0 (--help), 2 (bad input), 10 (unavailable this session).

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: bin/restore-test.sh --help

Future behavior (Session 10): prove REC-PITR-001 by restoring a backup to a
timestamp target in a disposable location and verifying the result.

  --target-time ISO8601  Point-in-time recovery target.
  --project-dir DIR      Generated project directory to read the stanza from.

Contract, and the reason this command exists separately from any restore
that touches production:
  - The restore target is always a disposable instance. This command must
    never be able to overwrite a live data directory.
  - Success means the restored instance was queried and answered correctly,
    not merely that pgBackRest exited zero.
  - A restore that cannot be verified is a failed restore.

Session 1 owns only the derived backup stanza and repository prefix.
USAGE
}

main() {
  case "${1-}" in
    --help) usage; return 0 ;;
    "") ;;
    *) usage >&2; printf 'restore-test: unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac

  cd "${ROOT_DIR}"
  printf 'restore-test: restore rehearsal begins in Session 10. Nothing was restored.\n' >&2
  exit 10
}

main "$@"
