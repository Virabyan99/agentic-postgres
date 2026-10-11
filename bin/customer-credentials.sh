#!/usr/bin/env bash
#
# The customer poolers' userlists, regenerated from the cluster (ADR 0269).
#
# One verb. `sync` reads both customer roles' SCRAM verifiers from pg_authid --
# the one source, so a restore or a branch carries the credential with the
# data -- writes one userlist per pooler under
# /etc/agentic-postgres/projects/<key>/customer-poolers/, and SIGHUPs both
# poolers. The control plane's credential.rotate calls it after setting a
# verifier; a deploy calls it at step 6f. It never prints a verifier, and no
# customer password exists on the host to print.
#
# Root, because the userlists are root-owned, the verifiers are read through
# the database container as its superuser, and the poolers are signalled
# through Docker.
#
# Exit codes (runbook section 2 convention):
#   0  synced, or the project has no public endpoints (nothing to sync)
#   2  invalid operator input
#   3  missing local prerequisite, not root, or no outputs document
#   6  the cluster could not be read, or a pooler could not be signalled --
#      reported, never read as success

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  sudo bin/customer-credentials.sh sync --outputs FILE

  sync      Read customer_app's and customer_admin's verifiers from the
            cluster, write pool.userlist (customer_app only) and
            direct.userlist (customer_admin only), and tell both customer
            poolers to re-read them. A role with no credential yet gets an
            empty list: its pooler refuses every login.
            --outputs  the project's outputs.json (rendered or deployed); the
                       container, the database and the two roles are read from
                       it, never typed.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'customer-credentials: %s\n' "$*" >&2
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
    die 2 "a verb is required: sync."
  fi
  # --help anywhere is a read: no root, no docker, no document.
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
    sync) ;;
    *) die 2 "unknown verb: $1. One of: sync" ;;
  esac
  command -v docker >/dev/null 2>&1 || die 3 "docker is not installed."
  exec "$(python_bin)" "${ROOT_DIR}/bin/customer-credentials.py" "$@"
}

main "$@"
