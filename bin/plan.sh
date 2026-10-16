#!/usr/bin/env bash
#
# The plans (ADR 0274): what each plan entitles an organisation to, which of
# those entitlements the control plane enforces and which it only shows, the
# organisation's own plan and what it holds of it, and *Notify me* for a plan
# not available during the beta. Every organisation is on Free during the beta;
# nothing here moves an organisation onto a plan, and nothing is charged.
#
# Exit codes (runbook section 2 convention):
#   0  done
#   2  invalid input
#   3  no context, no organisation chosen, or no credential
#   5  refused by the server (its error word is printed)
#   6  the server could not be reached or answered something unreadable

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  bin/plan.sh list [--json]
  bin/plan.sh show [--organization ID] [--json]
  bin/plan.sh notify-me [--organization ID] [--plan premium] [--json]

  list       Both plans and every entitlement: its value, whether this plane
             enforces it (projects_active, branches_total, compute_profiles --
             checked before anything is recorded) or only shows it against
             usage (storage_gb, agent_calls_per_day), and the reader that
             enforces it.
  show       The organisation's plan, its entitlements, the projects it holds
             against projects_active (a sleeping project holds its slot), and
             the plans it asked to be told about.
  notify-me  Record that the organisation wants a plan not available during
             the beta. One record per organisation and plan; asking again
             changes nothing. Nothing is charged, and nothing moves the
             organisation onto the plan.

ID is an organisation id; without it, the context's (bin/org.sh use).
notify-me needs a person's session; list and show also accept a key holding
organizations:read.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'plan: %s\n' "$*" >&2
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
    die 2 "a verb is required: list, show or notify-me."
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
    list | show | notify-me) ;;
    *) die 2 "unknown verb: $1. One of: list show notify-me" ;;
  esac
  exec "$(python_bin)" "${ROOT_DIR}/bin/cloud.py" plan "$@"
}

main "$@"
