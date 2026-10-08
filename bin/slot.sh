#!/usr/bin/env bash
#
# Customer slots on this host (ADR 0257, Session 38).
#
# A slot is a project the operator prepares in advance so that a customer's
# creation consumes nothing at a provider. Slots are DECLARED in the host
# manifest (schema 4, `slots`); a slot's state is never written anywhere -- it
# is derived from what exists on the host (D2149).
#
# Root: a slot's files, its bootstrap state and its secrets are root's.
#
# Exit codes (runbook section 2 convention):
#   0  done; or every slot's state determined
#   2  invalid operator input, or a --confirm that does not match
#   3  missing local prerequisite: root, the host manifest, its slots, a file
#   5  refused: not declared, or not in the state the verb needs
#   6  a slot's state could not be determined; or the revocation failed

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  sudo bin/slot.sh prepare --host FILE --slot KEY
  sudo bin/slot.sh status --host FILE [--json]
  sudo bin/slot.sh revoke --host FILE --slot KEY --operator-credential-file FILE --confirm KEY

  prepare   Write /etc/agentic-postgres/slots/KEY/manifest.yaml (0600) from the
            host manifest's slots.defaults, the slot's declaration and the
            `small` profile, validated by the product's own loader. Refuses a
            slot that is not declared, is already prepared, is occupied, or is
            consumed. The provider half (buckets, tokens, Infisical, DNS,
            secrets) is the operator's provisioning sheet.
  status    Every declared slot's state -- declared, prepared, ready,
            allocated, quarantined, consumed, undetermined -- and why. Ready
            means prepared AND the slot's A record is this host's address with
            no AAAA (dig @1.1.1.1). Exit 6 when any is undetermined.
  revoke    Revoke the Infisical runtime identity of a CONSUMED slot, from the
            bootstrap state its deletion kept, with bin/bootstrap-providers.sh
            --destroy. The credential file is the operator's, placed for this
            and shredded after. The Infisical project, the buckets, the backup
            repository and the DNS record stay.

KEY is a declared slot key (slot1-prod). FILE for --host is the host manifest,
/etc/agentic-postgres/host.yaml on a host.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'slot: %s\n' "$*" >&2
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
    die 2 "a verb is required: prepare, status or revoke."
  fi
  # --help anywhere is a read: no root, no host manifest.
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
    prepare | status | revoke) ;;
    *) die 2 "unknown verb: $1. One of: prepare status revoke" ;;
  esac
  exec "$(python_bin)" "${ROOT_DIR}/bin/slot.py" "$@"
}

main "$@"
