#!/usr/bin/env bash
#
# Retire one deployed project from this host (ADR 0187).
#
#   sudo bin/project-retire.sh --host FILE --project KEY --confirm KEY \
#        --record PATH [--plan] [--permanent | --before-expiry] [--destroy-data] \
#        [--operator-credential-file FILE]
#
# Removes what the key derives and the state records, on this host, in one
# fixed order, and never a backup: the repository, the bucket, the cipher pass
# and the Infisical project's secrets outlive a retirement (D957). The plan
# names every resource; the record is written before anything changes.
#
# Needs root: the deployed document is 0600 root and the steps reach systemd,
# Docker and root-owned directories. Resolves an interpreter the way doctor.sh
# does, because sudo's secure_path hides an activated venv.
#
# Exit codes: 0 (retired, or the plan was printed), 2 (bad input, a refusal),
# 3 (not root, or a prerequisite is missing), 4 (never deployed here), 6 (a
# step failed; the steps after it did not run).

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: sudo bin/project-retire.sh --host FILE --project KEY --confirm KEY --record PATH
            [--plan] [--permanent | --before-expiry] [--destroy-data]
            [--operator-credential-file FILE] [--help]

Retires one project from this host, in this order and no other:

  1. record             the retirement record, written before anything changes
  2. down               project-runtime.sh down: detach the edge, stop the stack
  3. disable-units      the project's systemd instance and its two backup timers
  4. release-ports      the port allocation, under the volume's identity
  5. edge-files         this project's files in the edge's dynamic directory
  6. provider-destroy   bootstrap-providers.sh --destroy: the runtime identity
  7. remove-directories the state, secrets and rendered directories
  8. remove-volumes     the two volumes -- only with --destroy-data

  --host FILE                      The host manifest.
  --project KEY                    The project key. Validated before use as a path.
  --confirm KEY                    The same key, said back. There is no --force.
  --record PATH                    Where to write the record. Must not exist.
  --plan                           Print every name and every command; change nothing.
  --permanent                      Required to retire a permanent project.
  --before-expiry                  Required to retire an ephemeral project that has
                                   not reached its expires_at.
  --destroy-data                   Also remove the postgres and store volumes.
                                   Without it they are kept, by name, for a redeploy
                                   of the same key (ADR 0030).
  --operator-credential-file FILE  The control-plane credential bootstrap-providers.sh
                                   --destroy needs to revoke the runtime identity.

Never touched: the backup repository, its bucket, the cipher pass, the
Infisical project's secrets, the DNS record, the certificate. The record says
where the backups still are, because deleting them is a console action.
USAGE
}

python_bin() {
  if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
    printf '%s' "${ROOT_DIR}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    printf 'retire: no Python interpreter found (looked for .venv/bin/python, python3).\n' >&2
    exit 3
  fi
}

main() {
  local -a passthrough=()
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help) usage; return 0 ;;
      --plan|--permanent|--before-expiry|--destroy-data) passthrough+=("$1"); shift ;;
      --host|--project|--confirm|--record|--operator-credential-file|--root)
        [ "$#" -ge 2 ] || { printf 'retire: %s requires a value.\n' "$1" >&2; exit 2; }
        passthrough+=("$1" "$2"); shift 2 ;;
      *) usage >&2; printf 'retire: unknown argument: %s\n' "$1" >&2; exit 2 ;;
    esac
  done

  [ "$(id -u)" -eq 0 ] || {
    printf 'retire: needs root: the deployed document is 0600 root and the steps reach systemd and Docker.\n' >&2
    exit 3
  }
  exec "$(python_bin)" "${ROOT_DIR}/bin/project-retire.py" "${passthrough[@]}"
}

main "$@"
