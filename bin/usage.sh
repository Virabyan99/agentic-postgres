#!/usr/bin/env bash
#
# A project's usage, as the server recorded it (ADR 0275): one sample every
# five minutes per project, each figure read or named as not read -- never a
# zero standing in for a reading that could not be made (ADR 0195). A window
# with no sample could not be determined, and says so with exit 6.
#
# This is the CUSTOMER's usage, read through the management API. The
# operator's reading of how much of the node one project uses is a different
# command with a different meaning: `sudo bin/doctor.sh usage --project KEY`
# (D2528).
#
# Exit codes (runbook section 2 convention):
#   0  done
#   2  invalid input
#   3  no context, no project or organisation chosen, or no credential
#   5  refused by the server (its error word is printed)
#   6  the server could not be reached, answered something unreadable, or a
#      project's usage could not be determined (no sample in the window)

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  bin/usage.sh show [--project-key KEY | --organization ID] [--hours N] [--json]

  show  Usage over the last N hours (1 to 720, default 24): how many samples
        were expected and recorded, each figure's newest reading and the
        window's maximum (database bytes, backup repository bytes, branches,
        branch bytes, customer connections), the requests answered below 400
        counted across counter resets, agent calls and workflow runs, the
        seconds active and asleep, and the plan's shown limits beside the
        figures they are read against. A figure not read is said, never
        printed as zero. --organization reads every project of the
        organisation, a deleted one for the part of the window it lived.

KEY is a project key such as slot1-prod; without --project-key or
--organization, the context's project (bin/project.sh use). Accepts a
person's session or a key holding projects:read.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'usage: %s\n' "$*" >&2
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
    die 2 "a verb is required: show."
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
    show) ;;
    *) die 2 "unknown verb: $1. One of: show" ;;
  esac
  exec "$(python_bin)" "${ROOT_DIR}/bin/cloud.py" usage "$@"
}

main "$@"
