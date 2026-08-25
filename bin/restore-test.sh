#!/usr/bin/env bash
#
# The disposable restore rehearsal.
#
# ADR 0017's lifecycle, fourth and final application: this command was a stub
# that documented its own contract and returned 10, and Session 10 Run 8
# implements it. The contract paragraph in `usage` below is the one Session 1
# wrote, unchanged, because it was already the right one.
#
# **The whole command is defined against one name it must never touch**: the
# project's live postgres data volume. Nothing here derives that name -- it is
# read out of the deployed document, handed to `bin/restore-test.py`, and
# compared against every mount the drill would make BEFORE any container starts
# (ADR 0151). The `trap` below is the second layer: it removes only the
# resources the Python side recorded in its state file, and it refuses outright
# to remove anything matching the live volume recorded in that same file.
#
# That refusal is not decoration. A teardown is the one part of a drill that
# runs when everything else has gone wrong, which is exactly when a widened
# search looks reasonable -- and §4.5 of the session plan requires that a
# teardown which cannot find its target exits non-zero rather than widening it.
#
# Root, because the deployed document is root-owned and the drill creates a
# volume and two containers over the local Docker socket. A human at a TTY: `op`
# cannot reach the Docker daemon, so this is not a command that runs over SSH.
#
# Exit codes (runbook section 2 convention):
#   0  the drill ran and the restore verified
#   2  invalid operator input
#   3  missing local prerequisite, or not root
#   5  the deployment or the repository refused the operation
#   6  the drill ran and its answer is "no" -- the restore did not verify
#   7  the plan was refused as unsafe; nothing was started

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

STATE_FILE=""

usage() {
  cat <<'USAGE'
Usage:
  sudo bin/restore-test.sh --target-time ISO8601 --project-dir DIR

  --target-time ISO8601  Point-in-time recovery target.
  --project-dir DIR      Generated project directory to read the stanza from.

Contract, and the reason this command exists separately from any restore
that touches production:
  - The restore target is always a disposable instance. This command must
    never be able to overwrite a live data directory.
  - Success means the restored instance was queried and answered correctly,
    not merely that pgBackRest exited zero.
  - A restore that cannot be verified is a failed restore.

What the drill does, and what it costs:
  1. Reads the deployed document and the running database container. The
     archiver's credential, cipher pass and configuration are INHERITED from
     that container rather than re-derived -- the active secret generation
     changes on every deploy, so any path into it is derived, never typed.
  2. Restores into a volume named for this drill alone, starts a cluster on it
     with archiving OFF, waits for it to promote, and queries it.
  3. Writes evidence/restore-drill-<project>-<id>.json and removes everything
     it created, pass or fail.

  It materialises a SECOND copy of the cluster on disk for the duration. Check
  free space before the first drill of any deployment; nothing here does.

Choosing --target-time:
  It must be LATER than the newest backup's stop time -- `bin/backup.sh info`
  prints that as the latest recoverable time. An earlier target is refused by
  pgBackRest before anything is written. A target in the future restores and
  then fails to promote, which this command reports as a failed drill.

What no flag here does: name a stanza, a bucket, a repository prefix, a backup
set, or the volume to restore into. All of them are decided once and published
(ADR 0002), and the last one is derived so that it cannot be typed.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'restore-test: %s\n' "$*" >&2
  exit "$code"
}

# The second layer of the teardown, and the only one that runs if the Python
# side is killed outright.
#
# It removes what the state file names and nothing else. It cannot find a
# resource by pattern, by label or by age, because every one of those is a
# search that could widen onto the live volume -- and this function runs at the
# moment when widening it would look like helpfulness.
teardown_from_state() {
  local state="${STATE_FILE}"
  [ -n "${state}" ] && [ -f "${state}" ] || return 0

  local live_volume="" drill_volume="" drill_container="" drill_restore_container=""
  local key value
  while IFS='=' read -r key value; do
    case "${key}" in
      live_volume) live_volume="${value}" ;;
      drill_volume) drill_volume="${value}" ;;
      drill_container) drill_container="${value}" ;;
      drill_restore_container) drill_restore_container="${value}" ;;
    esac
  done <"${state}"

  local name
  for name in "${drill_container}" "${drill_restore_container}"; do
    [ -n "${name}" ] || continue
    docker inspect "${name}" >/dev/null 2>&1 || continue
    docker stop -t 10 "${name}" >/dev/null 2>&1 || true
    docker rm "${name}" >/dev/null 2>&1 ||
      printf 'restore-test: TEARDOWN could not remove container %s\n' "${name}" >&2
  done

  if [ -n "${drill_volume}" ]; then
    # The refusal. `live_volume` is in the state file precisely so that this
    # comparison exists; this function never derives either name.
    if [ "${drill_volume}" = "${live_volume}" ]; then
      printf 'restore-test: TEARDOWN REFUSED -- the recorded drill volume is the live volume (%s). Removing nothing.\n' \
        "${live_volume}" >&2
      rm -f "${state}"
      return 1
    fi
    if docker volume inspect "${drill_volume}" >/dev/null 2>&1; then
      # No `-f`: a forced removal exits 0 for a volume that does not exist, so
      # it cannot tell "removed" from "was never there" (measured, rig 8 arm J).
      docker volume rm "${drill_volume}" >/dev/null 2>&1 ||
        printf 'restore-test: TEARDOWN could not remove volume %s\n' "${drill_volume}" >&2
    fi
  fi

  rm -f "${state}"
}

# `python3`, never a bare `python`: Ubuntu ships no such binary, sudo resets
# PATH to secure_path (D80), and D184 is the record of a `#!/usr/bin/env python`
# shebang that worked until something ran the file directly.
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
    die 2 "--target-time and --project-dir are required."
  fi
  case "$1" in
    --help | -h)
      usage
      return 0
      ;;
  esac

  command -v docker >/dev/null 2>&1 || die 3 "docker is not installed."

  STATE_FILE="$(mktemp -t apg-restore-drill.XXXXXXXX)"
  chmod 0600 "${STATE_FILE}"
  trap 'teardown_from_state' EXIT INT TERM

  # Every argument is forwarded verbatim. This wrapper parses none of them: the
  # Python side owns the contract, and a flag validated in two places is a flag
  # whose two validations drift.
  "$(python_bin)" "${ROOT_DIR}/bin/restore-test.py" --state-file "${STATE_FILE}" "$@"
}

main "$@"
