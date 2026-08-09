#!/usr/bin/env bash
#
# Manage the policy that decides which local account may obtain which database
# access profile of which project (ADR 0043).
#
# This is the operator half. The broker half -- `endpoint` and `password` -- is
# not reachable here on purpose: it is reached through
# /usr/local/libexec/agentic-postgres/database-access, the installed trampoline
# named in the sudoers rule, so that the one privileged entry point an
# unprivileged account can invoke is a path that never changes and holds no
# policy of its own.
#
# `check` needs no root and no host, so a policy can be reviewed before it is
# anywhere near a machine that would act on it. `publish` needs root and writes
# atomically; `show` needs root because the published file is 0600.
#
# Exit codes:
#   0  success
#   2  invalid operator input
#   3  missing prerequisite, or not root
#   5  the policy is invalid

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: bin/database-access.sh check --policy FILE
       sudo bin/database-access.sh publish --policy FILE [--plan]
       sudo bin/database-access.sh show

  check    Validate a candidate policy document. No root, no host, no state.
  publish  Install it at /etc/agentic-postgres/database-access-policy.json,
           root-owned, mode 0600, written beside and renamed.
  show     Print the published policy.

  --policy FILE  The candidate document. This is the only path this command
                 accepts; the published location is derived, never given.
  --plan         Report what would change without writing anything.

A policy grants one account an enumerated set of profiles for one named
project. There is no wildcard in any of the three fields: a grant matching
every project would silently cover projects deployed months later, and a grant
matching every profile would hand out migration authority as a side effect of
asking for runtime access.

No secret is accepted as an argument, and none is printed.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'database-access: %s\n' "$*" >&2
  exit "$code"
}

# Ubuntu ships no bare `python`, and sudo resets PATH to secure_path, so a venv
# the operator activated is invisible here (D80).
python_bin() {
  if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
    printf '%s' "${ROOT_DIR}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  elif command -v python >/dev/null 2>&1; then
    command -v python
  else
    die 3 "no Python interpreter found (looked for .venv/bin/python, python3, python)."
  fi
}

main() {
  if [ "$#" -eq 0 ]; then
    usage >&2
    die 2 "a subcommand is required."
  fi

  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    check|publish|show) ;;
    endpoint|password)
      usage >&2
      die 2 "$1 is a broker operation, not an operator one. It is reached through /usr/local/libexec/agentic-postgres/database-access."
      ;;
    *)
      usage >&2
      die 2 "unknown subcommand: $1"
      ;;
  esac

  cd "${ROOT_DIR}"

  PYTHONPATH="${ROOT_DIR}/src" exec "$(python_bin)" "${ROOT_DIR}/bin/database-access.py" "$@"
}

main "$@"
