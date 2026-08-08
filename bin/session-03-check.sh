#!/usr/bin/env bash
#
# The Session 3 gate. It does not replace bin/session-01-check.sh, which must
# still exit 0, or bin/session-02-check.sh, which still owns the external mode.
#
# Two modes, not three:
#
#   --mode offline   a checkout: contracts, schemas, models, migrations. CI.
#   --mode host      the deployment host: roles, ACLs, RLS, two clusters.
#
# There is no external mode, and its absence is a decision rather than an
# omission (D45). `SEC-NET-001`'s port scan already includes 5432 and is
# Session 2's to run; Session 3 is simply the first session in which that scan
# is not vacuous, because before it nothing was listening. Nothing new is
# visible from outside a cluster that publishes no port and joins no edge
# network, and a mode that measured nothing would still write evidence saying it
# had.
#
# The claims this gate is answerable for are cumulative: Session 2's `isolation`
# and `secret_leakage` are proved here too, because the product did not stop
# making those promises when it grew a database (ADR 0039).
#
# It VERIFIES. It does not deploy. A gate that deploys the system it measures
# cannot be re-run to confirm a fix, and its result depends on whether it was the
# first run (D20).
#
# Exit codes:
#   0  every check in the selected mode passed
#   2  invalid operator input
#   3  missing prerequisite for the selected mode
#   6  a check failed

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR
cd "${ROOT_DIR}"

readonly EVIDENCE_DIR="${ROOT_DIR}/evidence"
readonly SESSION=3

MODE=""
HOST_MANIFEST=""
PROJECT_A_OUTPUTS=""
PROJECT_B_OUTPUTS=""
SENTINEL_FILE=""
KEYWORD=""

usage() {
  cat <<'USAGE'
Usage: bin/session-03-check.sh --mode offline
       sudo bin/session-03-check.sh --mode host --host FILE \
            --project-a-outputs FILE --project-b-outputs FILE \
            [--sentinel-file FILE] [-k EXPRESSION]

  --mode offline   Contracts, schemas, models and rendered migrations. No host.
  --mode host      Everything measurable on the deployment host, over two live
                   clusters. Needs root: it reads root-only state.

  --project-b-outputs  Required in host mode. Session 3's isolation claim is
                       about two clusters, and one project cannot be isolated
                       from nothing.
  --sentinel-file      The planted secret value, from the ACTIVE generation.
                       Without it the twelve secret-leakage proofs skip, and a
                       skip is not a pass: the run reports the claim unproved.
  -k EXPRESSION        Restrict to matching tests. Writes no evidence: a run
                       that selected a subset cannot support a claim about the
                       whole.

There is no external mode. See the header, and D45.

This command verifies and never deploys. Use ./deploy.sh --through-session 3
to deploy, then run this to find out whether it worked.

Host mode writes evidence/session-03-host.json. Turn it into the session
document with:
  python bin/write-session-evidence.py --session 3 \
    --host-input evidence/session-03-host.json \
    --output evidence/session-03.json
USAGE
}

die() {
  local code="$1"
  shift
  printf 'session-03-check: %s\n' "$*" >&2
  exit "$code"
}

# Interpreter resolution, in this order and for these reasons:
#
#   1. the repository's own venv, because sudo resets PATH to secure_path and a
#      venv the operator activated is therefore invisible to this script;
#   2. python3, because Ubuntu ships no bare `python` and has not for years;
#   3. python, for a machine where the venv is already on PATH.
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

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

parse_arguments() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help|-h) usage; exit 0 ;;
      --mode)
        [ "$#" -ge 2 ] || die 2 "--mode requires a value."
        MODE="$2"
        shift 2
        ;;
      --host)
        [ "$#" -ge 2 ] || die 2 "--host requires a value."
        HOST_MANIFEST="$2"
        shift 2
        ;;
      --project-a-outputs)
        [ "$#" -ge 2 ] || die 2 "--project-a-outputs requires a value."
        PROJECT_A_OUTPUTS="$2"
        shift 2
        ;;
      --project-b-outputs)
        [ "$#" -ge 2 ] || die 2 "--project-b-outputs requires a value."
        PROJECT_B_OUTPUTS="$2"
        shift 2
        ;;
      --sentinel-file)
        [ "$#" -ge 2 ] || die 2 "--sentinel-file requires a value."
        SENTINEL_FILE="$2"
        shift 2
        ;;
      -k)
        [ "$#" -ge 2 ] || die 2 "-k requires an expression."
        KEYWORD="$2"
        shift 2
        ;;
      --mode=*|--host=*|--project-a-outputs=*|--project-b-outputs=*|--sentinel-file=*)
        die 2 "use a space, not '=': ${1%%=*} VALUE"
        ;;
      --baseline-only)
        die 2 "--baseline-only belongs to bin/session-02-check.sh; Session 3 measures deployed clusters."
        ;;
      --mode-external|--public-ipv4|--public-ipv6)
        die 2 "there is no external mode in Session 3. See bin/session-03-check.sh --help."
        ;;
      *) usage >&2; die 2 "unknown argument: $1" ;;
    esac
  done

  case "${MODE}" in
    offline|host) ;;
    "") usage >&2; die 2 "--mode is required." ;;
    external) die 2 "there is no external mode in Session 3. See --help." ;;
    *) die 2 "unknown mode: ${MODE}. Expected offline or host." ;;
  esac
}

# Both modes run pytest with the same selector shape, so neither can drift into
# its own definition of passing.
run_suite() {
  local marker="$1" junit="$2"
  local -a arguments=(-q -m "${marker}")
  [ -n "${KEYWORD}" ] && arguments+=(-k "${KEYWORD}")
  [ -n "${junit}" ] && arguments+=(--junitxml="${junit}")

  "$(python_bin)" -m pytest "${arguments[@]}"
}

# A claim's proofs are not all environment-gated: each one also names contract
# tests that run anywhere, which `-m live_host` therefore never collects. They
# are run explicitly rather than by widening the selector, which would drag the
# whole contract suite into a deployment run. The node IDs come from the
# acceptance registry, so a requirement that gains a test gains it here without
# anyone editing this script.
claim_static_nodeids() {
  PYTHONPATH="${ROOT_DIR}/src" "$(python_bin)" - "$1" "$2" <<'PYTHON'
import sys

from agentic_postgres.evidence_claims import static_nodeids_for_mode

for nodeid in static_nodeids_for_mode(sys.argv[1], int(sys.argv[2])):
    print(nodeid)
PYTHON
}

# Writes ${junit} only if this mode has static proofs to run. An empty node-ID
# list means this mode carries no claim, and running `pytest` with no arguments
# would collect the whole suite -- the most expensive possible way to measure
# nothing.
run_claim_proofs() {
  local mode="$1" junit="$2"
  local -a nodeids=()
  local listing status line

  rm -f "${junit}"

  # Declared, then assigned on its own line, then the status read on its own
  # line. `local listing="$(...)"` returns the exit status of `local`, so a
  # failed resolver would look like a mode that simply carries no claim -- and
  # this run would then produce evidence asserting nothing.
  listing=""
  listing="$(claim_static_nodeids "${mode}" "${SESSION}")"
  status=$?
  [ "${status}" -eq 0 ] \
    || die 6 "could not resolve the claim proofs for ${mode} mode (exit ${status})."

  while IFS= read -r line; do
    [ -n "${line}" ] && nodeids+=("${line}")
  done <<<"${listing}"

  if [ "${#nodeids[@]}" -eq 0 ]; then
    printf 'No claim is measured in %s mode; there is nothing to run here.\n' "${mode}"
    return 0
  fi

  "$(python_bin)" -m pytest -q --junitxml="${junit}" "${nodeids[@]}"
}

write_evidence() {
  local mode="$1"
  local suite_junit="${EVIDENCE_DIR}/session-03-${mode}-tests.xml"
  local claims_junit="${EVIDENCE_DIR}/session-03-${mode}-claims.xml"

  local -a arguments=(
    --session "${SESSION}" --mode "${mode}"
    --project-a-outputs "${PROJECT_A_OUTPUTS}"
    --project-b-outputs "${PROJECT_B_OUTPUTS}"
    --junit "${suite_junit}"
    --output "${EVIDENCE_DIR}/session-03-${mode}.json"
  )
  [ -f "${claims_junit}" ] && arguments+=(--junit "${claims_junit}")

  "$(python_bin)" bin/write-session-evidence.py "${arguments[@]}"
}

# Evidence is written only by a run that selected everything. -k is for
# iterating on one failure, and an evidence file produced from a filtered run
# would report a claim on the strength of whichever tests the expression
# happened to match.
evidence_is_supportable() {
  [ -z "${KEYWORD}" ]
}

mode_offline() {
  step "1. Static quality"
  shellcheck deploy.sh bin/*.sh libexec/*
  "$(python_bin)" -m ruff check src bin tests
  "$(python_bin)" -m ruff format --check src bin tests
  bin/lock-versions.sh --check

  step "2. Offline contract suite"
  run_suite "p0 and not future and not live_host and not external" ""

  step "3. Environment-gated tests collect and skip"
  # A module that opened a socket at import time would break collection for the
  # whole suite, and this is the cheapest place to find that out.
  run_suite "live_host or external" ""

  step "4. Models resolve"
  bin/compose.sh --edge --host host.example.yaml config >/dev/null
  printf 'edge model resolves\n'

  step "5. Registry and generated documentation"
  "$(python_bin)" -m pytest -q tests/contract/test_acceptance_registry.py
  "$(python_bin)" bin/render-acceptance-matrix.py --check

  printf '\n\033[1msession-03-check: offline PASSED\033[0m\n'
}

mode_host() {
  # Arguments before privilege, deliberately. An operator iterating on a command
  # line should learn they mistyped a flag without first having to obtain root
  # to be told.
  [ -n "${HOST_MANIFEST}" ] || die 2 "--mode host requires --host."
  [ -f "${HOST_MANIFEST}" ] || die 2 "host manifest not found: ${HOST_MANIFEST}"
  [ -n "${PROJECT_A_OUTPUTS}" ] || die 2 "--mode host requires --project-a-outputs."
  [ -f "${PROJECT_A_OUTPUTS}" ] || die 2 "not found: ${PROJECT_A_OUTPUTS}"

  # Required, unlike in Session 2. `database_isolation` is a claim about two
  # clusters; with one project every proof of it would skip, the claim would
  # come out `not_run`, and the run would report that as a failure anyway --
  # after doing all the work. Refusing up front says the same thing sooner.
  [ -n "${PROJECT_B_OUTPUTS}" ] \
    || die 2 "--mode host requires --project-b-outputs: the isolation claim is about two clusters."
  [ -f "${PROJECT_B_OUTPUTS}" ] || die 2 "not found: ${PROJECT_B_OUTPUTS}"

  [ "$(id -u)" -eq 0 ] || die 3 "--mode host requires root: it reads root-only host state."

  step "1. Host baseline, unchanged by this run"
  bin/provision-host.sh --host "${HOST_MANIFEST}" --check

  step "2. Host-local acceptance suite, over two clusters"
  mkdir -p "${EVIDENCE_DIR}"
  export APG_LIVE_HOST=1
  export APG_EDGE_DEPLOYED=1
  export APG_PROJECT_A_OUTPUTS="${PROJECT_A_OUTPUTS}"
  export APG_PROJECT_B_OUTPUTS="${PROJECT_B_OUTPUTS}"
  [ -n "${SENTINEL_FILE}" ] && export APG_SECRET_SENTINEL_FILE="${SENTINEL_FILE}"

  run_suite "live_host" "${EVIDENCE_DIR}/session-03-host-tests.xml"

  if ! evidence_is_supportable; then
    printf '\nNo evidence written: -k selected a subset of the suite, so this run\n'
    printf 'cannot support a claim about the whole.\n'
    printf '\n\033[1msession-03-check: host PASSED\033[0m\n'
    return 0
  fi

  step "3. Static proofs of the claims this run records"
  run_claim_proofs host "${EVIDENCE_DIR}/session-03-host-claims.xml"

  step "4. Host evidence"
  write_evidence host

  printf '\n\033[1msession-03-check: host PASSED\033[0m\n'
}

main() {
  parse_arguments "$@"
  case "${MODE}" in
    offline) mode_offline ;;
    host) mode_host ;;
  esac
}

main "$@"
