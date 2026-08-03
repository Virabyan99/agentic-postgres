#!/usr/bin/env bash
#
# Database connection helper. Documents modes only; opens no connection.
#
# Exit codes: 0 (--help), 2 (bad input), 10 (unavailable this session).

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: bin/connect.sh --help

Future behavior (Session 4 onward): open a connection to a rendered project's
database using one of three modes.

  --mode tunnel   Establish the operator tunnel and hold it open.
  --mode psql     Interactive psql against the direct endpoint.
  --mode prisma   Print the Prisma datasource pair (pooled + direct).

  --project-dir DIR  Generated project directory to read identities from.

Session 1 renders endpoint metadata as status "unavailable" with null host,
port, URL, and secret reference, because no tunnel host or bound port exists
yet. There is nothing to connect to and this command will not pretend
otherwise. Session 4 activates real endpoint metadata.

Credentials are resolved from the secret namespace at call time. They are
never accepted as arguments and never printed.
USAGE
}

main() {
  case "${1-}" in
    --help) usage; return 0 ;;
    "") ;;
    *) usage >&2; printf 'connect: unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac

  cd "${ROOT_DIR}"
  printf 'connect: database endpoints are unavailable until Session 4. No connection was opened.\n' >&2
  exit 10
}

main "$@"
