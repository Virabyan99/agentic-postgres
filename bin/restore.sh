#!/usr/bin/env bash
#
# Restore a project's stanza into its OWN volume, on a replacement host
# (ADR 0189, ADR 0192). The disposable rehearsal is bin/restore-test.sh; this
# is the other one, and it is defined by the refusal the drill never needs: a
# volume that holds a cluster is never written to, on any host.
#
# The order on a replacement host is adopt, materialize, THIS, deploy (D1008):
# a first `up` on an empty volume runs initdb, and the deploy's stanza-create
# would then meet a repository written by a different cluster. So this runs
# before the project's first start, restores through the project's own image,
# starts the cluster once with archiving OFF to finish recovery, stops it, and
# leaves the volume for deploy.sh to start.
#
# Root: the secret generation is root-owned and the restore reaches Docker.
# A human at a TTY.
#
# Exit codes (runbook section 2 convention):
#   0  the restore ran and verified
#   2  invalid operator input
#   3  missing local prerequisite, or not root
#   5  the deployment or the repository refused the operation
#   6  the restore ran and its answer is "no" -- it did not verify
#   7  the plan was refused as unsafe; nothing was started

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR
STATE_FILE=""

usage() {
  cat <<'USAGE'
Usage:
  sudo bin/restore.sh --outputs KIT/projects/<key>/outputs.json --project project.yaml \
       --rendered-dir .generated/<key> --from primary|mirror (--latest | --target-time ISO8601) [--plan]

  --outputs FILE       The kit's deployed document: the stanza, the buckets, the
                       identity the restore is verified against.
  --project FILE       The manifest deployed on THIS host; must derive the same
                       key and stanza.
  --rendered-dir DIR   The rendered directory (deploy.sh --render-only), which
                       the postgres image is built from.
  --from mirror        Read the mirror bucket with the mirror's key pair (the
                       primary's credential is never mounted); primary reads
                       the primary bucket with the archiver's own includes.
  --latest             Replay every archived segment; --target-time stops at T.
  --plan               Print the plan and start nothing.

Refused, before anything starts: a volume a container mounts; a volume that
holds a cluster; a manifest naming another key or stanza; --from mirror on a
project whose document has no mirror. Never passed: --delta.

Afterwards the volume holds the promoted cluster; run deploy.sh, which starts
it without initdb, and verify by docs/node-loss-runbook.md.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'restore: %s\n' "$*" >&2
  exit "$code"
}

# The trap stops the two containers the state file names and NOTHING else --
# never the volume, which is the point of the command. No search by pattern.
stop_from_state() {
  local state="${STATE_FILE}"
  [ -n "${state}" ] && [ -f "${state}" ] || return 0
  local key value
  while IFS='=' read -r key value; do
    case "${key}" in
      instance_container | restore_container)
        [ -n "${value}" ] || continue
        docker inspect "${value}" >/dev/null 2>&1 || continue
        docker stop -t 30 "${value}" >/dev/null 2>&1 || true
        docker rm "${value}" >/dev/null 2>&1 ||
          printf 'restore: CLEANUP could not remove container %s\n' "${value}" >&2
        ;;
    esac
  done <"${state}"
  rm -f "${state}"
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
    die 2 "--outputs, --project, --rendered-dir and --from are required."
  fi
  case "$1" in
    --help | -h) usage; return 0 ;;
  esac
  command -v docker >/dev/null 2>&1 || die 3 "docker is not installed."
  [ "$(id -u)" -eq 0 ] || die 3 "needs root: the secret generation is root-owned and the restore reaches Docker."

  STATE_FILE="$(mktemp -t apg-restore.XXXXXXXX)"
  chmod 0600 "${STATE_FILE}"
  trap 'stop_from_state' EXIT INT TERM

  # Every argument is forwarded verbatim; the Python side owns the contract.
  "$(python_bin)" "${ROOT_DIR}/bin/restore.py" --state-file "${STATE_FILE}" "$@"
}

main "$@"
