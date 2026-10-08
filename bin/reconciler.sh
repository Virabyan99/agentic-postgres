#!/usr/bin/env bash
#
# The reconciler (ADR 0256): executes the control plane's operations on this
# host, as root, one at a time. The unit agentic-postgres-reconciler.service
# runs `run`; an operator runs `once`, `status` and `install`.
#
# It opens no socket and binds no port: it pulls from the control project's
# database through its container, as bin/control.sh does, and runs the existing
# bin/ commands as argv lists, stdin /dev/null, output to
# /var/log/agentic-postgres/reconciler/<operation>-<step>.log (0600).
#
# Root, because every command an operation runs is root's. Its children act for
# the operator who owns this checkout (SUDO_UID/SUDO_GID, D2153); a root-owned
# checkout is refused. An operator's sheet that deploys, retires or restores a
# project stops the unit first and starts it after (D2178).
#
# Exit codes (runbook section 2 convention):
#   0  done
#   2  invalid operator input
#   3  missing local prerequisite: not root, a root-owned checkout, no host.yaml,
#      no deployed control project, or no docker
#   5  two deployed projects enable the control facility (D2168)
#   6  something could not be read, or the control database stopped answering

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  sudo bin/reconciler.sh run        (the unit's verb)
  sudo bin/reconciler.sh once
  sudo bin/reconciler.sh status
  sudo bin/reconciler.sh install

  run      Finish every operation an earlier run left running as failed
           (interrupted -- never resumed; an interrupted creation quarantines
           its slot), record the slots, then claim and execute one operation
           at a time, polling every 5 seconds.
  once     The same, for at most one operation, then exit.
  status   "idle", "working on <id> (<type>, step <step>)", or "stopped (...)".
  install  Install agentic-postgres-reconciler.service and
           /etc/agentic-postgres/reconciler.env (naming this checkout), create
           the log and export directories, daemon-reload, enable --now.

The control project is found, never named: the one deployed document under
/etc/agentic-postgres/projects/ that records the control facility enabled. The
host manifest is this checkout's host.yaml; operations refuse to run when the
checkout's HEAD moves or its tree is dirty (D2179).
USAGE
}

die() {
  local code="$1"
  shift
  printf 'reconciler: %s\n' "$*" >&2
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
    die 2 "a verb is required: run, once, status or install."
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
    run | once)
      command -v docker >/dev/null 2>&1 || die 3 "docker is not installed."
      ;;
    status | install) ;;
    *) die 2 "unknown verb: $1. One of: run once status install" ;;
  esac
  cd "${ROOT_DIR}"
  exec "$(python_bin)" "${ROOT_DIR}/bin/reconciler.py" "$@"
}

main "$@"
