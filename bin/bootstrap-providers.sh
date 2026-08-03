#!/usr/bin/env bash
#
# Provider bootstrap. Documents future inputs only; makes no provider call.
#
# Exit codes: 0 (--help), 2 (bad input), 10 (unavailable this session).

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: bin/bootstrap-providers.sh --help

Future behavior (Session 2 onward): validate that every external provider a
project manifest requires has been provisioned, and record the resulting
non-secret references.

Inputs this command will take, none of which is a secret value:
  --project FILE          Project manifest selecting which providers apply.
  --secrets-namespace REF Namespace under which references are stored.
  --dry-run               Report what would be checked and exit.

Secret material is never accepted as a command-line argument and is never
printed. This command reads references, not credentials.

Session 1 makes no provider call of any kind.
USAGE
}

main() {
  case "${1-}" in
    --help) usage; return 0 ;;
    "") ;;
    *) usage >&2; printf 'bootstrap-providers: unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac

  cd "${ROOT_DIR}"
  printf 'bootstrap-providers: provider bootstrap begins in Session 2. No provider was contacted.\n' >&2
  exit 10
}

main "$@"
