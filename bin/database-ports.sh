#!/usr/bin/env bash
#
# Allocate, verify, show and release the two host-loopback ports a project's
# database transports are reached through (ADR 0042).
#
# They are the LOCAL end of a developer's tunnel, not a publication. Nothing
# is published: Docker installs no rule and no listener for a container on an
# `internal: true` network, so the tunnel targets the container endpoint on the
# host's own bridge (ADR 0044). Everything this allocator does is unchanged by
# that -- an allocation that moves still breaks every saved tunnel.
#
# The allocation key is the instance UUID the project's data volume carries --
# `app_private.project_identity.instance_uuid`, generated once on the first
# bootstrap of an empty volume and recovered on every bootstrap since. It is the
# only identity in this system bound to the data rather than to the
# configuration that produced it, so a restored volume brings its ports with it.
#
# The project key is recorded so an operator reading the registry knows what
# they are looking at. It is never the match key: two projects can share a key
# across a rebuild, and one project can change it.
#
# Exit codes:
#   0  success
#   2  invalid operator input
#   3  missing prerequisite, or not root
#   4  no allocation for that identity
#   5  the registry is invalid, or the request cannot be satisfied
#   6  a check failed -- an allocation nothing is serving stays reserved

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: sudo bin/database-ports.sh allocate --host FILE --project-key KEY \
            --instance-uuid UUID [--plan]
       sudo bin/database-ports.sh verify --host FILE --instance-uuid UUID [--plan]
       sudo bin/database-ports.sh release --project-key KEY --instance-uuid UUID [--plan]
       bin/database-ports.sh show [--instance-uuid UUID]

  allocate  Reserve two ports, or return the two this identity already holds.
            Reuse is the default: a redeploy gets the same numbers back, because
            they are in somebody's saved tunnel. Both ports are reserved as one
            transaction; a project with one is a state nothing can converge.
  verify    Connect to both container endpoints and, if both answer, promote
            the reservation to active. A reservation nothing serves stays
            reserved, which is what makes a crashed deploy provable rather
            than invisible.
  release   Give up two ports. --project-key must match what the registry
            records, because this is the one operation that can hand a
            developer's port to another project.
  show      Print the registry, or one allocation.

  --host FILE          The host manifest, which declares the loopback address
                       and the allocatable range.
  --instance-uuid UUID app_private.project_identity.instance_uuid.
  --project-key KEY    The project key, recorded and confirmed, never matched on.
  --plan               Report what would change without writing anything.

No secret is accepted as an argument, and none is read.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'database-ports: %s\n' "$*" >&2
  exit "$code"
}

# Ubuntu ships no bare `python`, and sudo resets PATH to secure_path, so a venv
# the operator activated is invisible here. This is the trap five Session 2
# scripts walked into and the Session 1 gate walked into again in Session 3
# (D80): it fails only on a host, only under sudo, and only at the end.
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
    allocate|verify|release|show) ;;
    *)
      usage >&2
      die 2 "unknown subcommand: $1"
      ;;
  esac

  # `show` reads. Everything else writes host state under /etc and takes a lock
  # under /run/lock, so it needs root -- and says so here rather than failing
  # later with a permission error that names a path instead of a cause.
  if [ "$1" != "show" ]; then
    local planning=0
    local argument
    for argument in "$@"; do
      [ "${argument}" = "--plan" ] && planning=1
    done
    if [ "${planning}" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
      die 3 "must run as root: the allocation registry lives under /etc and the lock under /run/lock."
    fi
  fi

  cd "${ROOT_DIR}"

  PYTHONPATH="${ROOT_DIR}/src" exec "$(python_bin)" "${ROOT_DIR}/bin/database-ports.py" "$@"
}

main "$@"
