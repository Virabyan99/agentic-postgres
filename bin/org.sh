#!/usr/bin/env bash
#
# Organisations on the management API (D2051-D2053): the caller's
# organisations, members, invitations and management keys. Every verb names
# the organisation with --organization or uses the context's (bin/org.sh use).
#
# An invitation token and a key are written to --output FILE -- once, 0600,
# refused if the file exists, checked before the server mints anything -- and
# printed nowhere.
#
# Exit codes (runbook section 2 convention):
#   0  done
#   2  invalid input, or an --output that exists
#   3  no context, no organisation chosen, no credential, or an unusable file
#   5  refused by the server (its error word is printed)
#   6  the server could not be reached or answered something unreadable

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  bin/org.sh list [--json]
  bin/org.sh create --name TEXT
  bin/org.sh use --organization ID
  bin/org.sh members [--organization ID] [--json]
  bin/org.sh invite (--account | --role owner|admin|member|viewer) --output FILE [--organization ID] [--expires-hours N]
  bin/org.sh set-role --user ID --role owner|admin|member|viewer [--organization ID]
  bin/org.sh remove --user ID [--organization ID]
  bin/org.sh keys [--organization ID] [--json]
  bin/org.sh key-create --name TEXT --scopes LIST --output FILE [--organization ID]
  bin/org.sh key-revoke --key-id ID [--organization ID]

  list        The caller's organisations and their role in each.
  create      A new organisation; the caller becomes its owner.
  use         Make an organisation the context's (the project is cleared).
  members     An organisation's members.
  invite      A membership invitation for a role at or below the caller's, or
              (--account, the registry administrator only) an account
              invitation. Lives 72 hours unless --expires-hours (1-168).
  set-role    Change a member's role (admin and above).
  remove      Remove a member; their keys in the organisation are revoked.
  keys        The organisation's keys the caller may see; never a secret.
  key-create  A key for the caller, with scopes from organizations:read,
              members:read, projects:read, operations:read (comma-separated).
  key-revoke  Revoke a key; its next request is refused.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'org: %s\n' "$*" >&2
  exit "$code"
}

python_bin() {
  if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
    printf '%s' "${ROOT_DIR}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    die 3 "no Python interpreter found (looked for .venv/bin/python, python3)."
  fi
}

main() {
  if [ "$#" -eq 0 ]; then
    usage >&2
    die 2 "a verb is required: list, create, use, members, invite, set-role, remove, keys, key-create or key-revoke."
  fi
  local argument
  for argument in "$@"; do
    case "${argument}" in
      --help | -h)
        usage
        return 0
        ;;
    esac
  done
  case "$1" in
    list | create | use | members | invite | set-role | remove | keys | key-create | key-revoke) ;;
    *) die 2 "unknown verb: $1. One of: list create use members invite set-role remove keys key-create key-revoke" ;;
  esac
  exec "$(python_bin)" "${ROOT_DIR}/bin/cloud.py" org "$@"
}

main "$@"
