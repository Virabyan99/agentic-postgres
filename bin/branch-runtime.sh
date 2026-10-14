#!/usr/bin/env bash
# A managed project's branch on this host -- create, reset, delete, start, status
# (Session 40, ADR 0271).
#
# Root, because a branch's volume, containers and state directory are root's
# and its restore reads the parent's repository mounts out of the parent's
# running database container. The reconciler runs every verb but `status` for
# an operation; an operator reads `status`. No customer runs this: a customer's
# command is `apg branch` (bin/branch.sh), through /api/v1.
#
# Exit codes:
#   0  done; or every branch's state determined
#   2  invalid input
#   3  a prerequisite is missing: root, a file, the parent's document or container
#   5  refused: the branch exists or does not, the parent cannot have one now,
#      a name does not resolve here, or pgBackRest or Docker refused
#   6  could not determine: a reading failed, a branch did not come back
#   7  refused as unsafe, or the point is outside the restore window
#   12 admission: the branch does not fit on this node

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  sudo bin/branch-runtime.sh create --parent-outputs FILE --branch NAME --verifiers-stdin --operation ID [--target-time T] [--expires-at T --expires-for MEMBER] [--host FILE]
  sudo bin/branch-runtime.sh reset --parent-outputs FILE --branch NAME --verifiers-stdin --operation ID [--target-time T] [--host FILE]
  sudo bin/branch-runtime.sh delete --parent-key KEY --branch NAME
  sudo bin/branch-runtime.sh start --all
  sudo bin/branch-runtime.sh status [--json]

  create   Restore the parent's repository into the branch's own volume -- to
           --target-time, or with none to the end of the archive -- through a
           recovery instance with archiving off; start the branch's postgres
           with no repository and no backup network; re-key it (every platform
           role NOLOGIN, the branch's own two verifiers, read as JSON on stdin);
           only then start its two doors, <branch>.pool.<domain> and
           <branch>.direct.<domain>, and attach the edge. Refused when the
           parent sleeps, the names do not resolve here, the point is outside
           the parent's restore window (exit 7), or the branch does not fit
           (exit 12).
  reset    The same restore again, into a fresh volume, keeping the names and
           the certificate. A branch's data since its creation is lost.
  delete   Remove exactly what the branch's names derive -- its containers,
           networks, volume and state directory. Nothing of the parent.
  start    Bring every recorded branch back (the reconciler, after a boot). A
           branch that does not come back is recorded stopped.
  status   Every branch on this host, its point, its timeline and its
           containers. Exit 6 when any record cannot be read.

NAME is a branch name: a lowercase letter then 1-11 letters or digits; `main`
is the project itself. FILE for --parent-outputs is the parent's deployed
document, /etc/agentic-postgres/projects/<key>/outputs.json; --host defaults to
/etc/agentic-postgres/host.yaml. A branch is not backed up.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'branch-runtime: %s\n' "$*" >&2
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
    die 2 "a verb is required: create, reset, delete, start or status."
  fi
  # --help anywhere is a read: no root, no parent, no Docker.
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
    create | reset | delete | start | status) ;;
    *) die 2 "unknown verb: $1. One of: create reset delete start status" ;;
  esac
  exec "$(python_bin)" "${ROOT_DIR}/bin/branch-runtime.py" "$@"
}

main "$@"
