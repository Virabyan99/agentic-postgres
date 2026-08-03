#!/usr/bin/env bash
#
# Delegate to the current session's active tests (runbook §2 command table).
#
# This is intentionally a thin delegator. It must never grow a second,
# divergent definition of "the tests that matter right now" — that definition
# lives in the pytest markers and in bin/session-01-check.sh.
#
# Exit codes: 0 (tests passed), 2 (bad input), 3 (pytest unavailable),
#             plus pytest's own non-zero status on failure.

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: bin/smoke-test.sh [--help]

Runs the active (non-future) contract tests for the current session:

  python -m pytest -q -m "contract and not future"

This is a fast signal, not the session gate. The gate is
bin/session-01-check.sh, which additionally enforces a clean tree, static
analysis, both fixture renders, the P0 inventory, and evidence generation.
USAGE
}

main() {
  case "${1-}" in
    --help) usage; return 0 ;;
    "") ;;
    *) usage >&2; printf 'smoke-test: unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac

  cd "${ROOT_DIR}"

  python -c 'import pytest' >/dev/null 2>&1 \
    || { printf 'smoke-test: pytest is not installed. Run: python -m pip install --require-hashes -r requirements-dev.txt\n' >&2; exit 3; }

  exec python -m pytest -q -m "contract and not future"
}

main "$@"
