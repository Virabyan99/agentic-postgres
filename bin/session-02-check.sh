#!/usr/bin/env bash
#
# The Session 2 gate. It does not replace bin/session-01-check.sh, which must
# still exit 0; it adds the claims Session 1 could not make.
#
# Session 1's single-gate model does not survive Session 2, and this does not
# pretend otherwise. There are three execution environments and they cannot be
# one command:
#
#   --mode offline   a checkout: contracts, schemas, models. Runs in CI.
#   --mode host      the deployment host: SSH, firewall, Docker, secrets, TLS.
#   --mode external  a different network: what the public internet can reach.
#
# The external mode is not a formality. A port scan run on the host traverses
# loopback and the host's own routing table, so it can report "closed" for a
# port the world can reach. Only a scan from somewhere else is about the public
# boundary.
#
# It VERIFIES. It does not deploy. The runbook's §11 has the host-side gate
# deploy both projects as one of its steps; this refuses to, because a gate that
# deploys the system it measures cannot be re-run to confirm a fix, and its
# result depends on whether it was the first run (plan divergence D20).
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

MODE=""
HOST_MANIFEST=""
PROJECT_A_OUTPUTS=""
PROJECT_B_OUTPUTS=""
SENTINEL_FILE=""
PUBLIC_IPV4=""
PUBLIC_IPV6=""
KEYWORD=""
BASELINE_ONLY=0

usage() {
  cat <<'USAGE'
Usage: bin/session-02-check.sh --mode offline
       sudo bin/session-02-check.sh --mode host --host FILE \
            --project-a-outputs FILE [--project-b-outputs FILE] \
            [--sentinel-file FILE]
       sudo bin/session-02-check.sh --mode host --host FILE --baseline-only
       bin/session-02-check.sh --mode external --public-ipv4 ADDR \
            --project-a-outputs FILE [--public-ipv6 ADDR]

  --mode offline   Contracts, schemas and models. No host, no network.
  --mode host      Everything measurable on the deployment host. Needs root.
  --mode external  What the public internet can reach. MUST run from a network
                   that is not the host: a scan from the host itself measures
                   its own routing table, not the boundary.

  -k EXPRESSION    Restrict to matching tests. For iterating on one failure.
  --baseline-only  Host mode before anything is deployed: verify the host
                   baseline and skip every test that needs a project. Writes no
                   evidence, because a run where those tests never executed
                   cannot support a verdict about a deployment.

This command verifies and never deploys. Use ./deploy.sh --through-session 2
to deploy, then run this to find out whether it worked.

Host and external modes each write an evidence file. Merge them with:
  python bin/write-session-evidence.py --session 2 \
    --host-input evidence/session-02-host.json \
    --external-input evidence/session-02-external.json \
    --output evidence/session-02.json
USAGE
}

die() {
  local code="$1"
  shift
  printf 'session-02-check: %s\n' "$*" >&2
  exit "$code"
}

# Interpreter resolution, in this order and for these reasons:
#
#   1. the repository's own venv, because sudo resets PATH to secure_path and a
#      venv the operator activated is therefore invisible to this script;
#   2. python3, because Ubuntu ships no bare `python` and has not for years;
#   3. python, for a machine where the venv is already on PATH.
#
# Assuming a bare `python` is a standing trap this repository documents, and
# five Session 2 scripts walked into it. It fails only on a host, only under
# sudo, and reports `python: command not found` from inside a heredoc.
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
      --baseline-only) BASELINE_ONLY=1; shift ;;
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
      --public-ipv4)
        [ "$#" -ge 2 ] || die 2 "--public-ipv4 requires a value."
        PUBLIC_IPV4="$2"
        shift 2
        ;;
      --public-ipv6)
        [ "$#" -ge 2 ] || die 2 "--public-ipv6 requires a value."
        PUBLIC_IPV6="$2"
        shift 2
        ;;
      -k)
        [ "$#" -ge 2 ] || die 2 "-k requires an expression."
        KEYWORD="$2"
        shift 2
        ;;
      *) usage >&2; die 2 "unknown argument: $1" ;;
    esac
  done

  case "${MODE}" in
    offline|host|external) ;;
    "") usage >&2; die 2 "--mode is required." ;;
    *) die 2 "unknown mode: ${MODE}. Expected offline, host or external." ;;
  esac
}

# Every mode runs pytest with the same selector shape. Building it here keeps
# the three modes from drifting into three different definitions of passing.
run_suite() {
  local marker="$1" junit="$2"
  local -a arguments=(-q -m "${marker}")
  [ -n "${KEYWORD}" ] && arguments+=(-k "${KEYWORD}")
  [ -n "${junit}" ] && arguments+=(--junitxml="${junit}")

  "$(python_bin)" -m pytest "${arguments[@]}"
}

mode_offline() {
  step "1. Static quality"
  shellcheck deploy.sh bin/*.sh libexec/*
  "$(python_bin)" -m ruff check src bin tests
  "$(python_bin)" -m ruff format --check src bin tests
  bin/lock-versions.sh --check

  step "2. Offline Session 2 contract suite"
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

  printf '\n\033[1msession-02-check: offline PASSED\033[0m\n'
}

mode_host() {
  # Arguments before privilege, deliberately. An operator iterating on a command
  # line should learn they mistyped a flag without first having to obtain root
  # to be told.
  [ -n "${HOST_MANIFEST}" ] || die 2 "--mode host requires --host."
  [ -f "${HOST_MANIFEST}" ] || die 2 "host manifest not found: ${HOST_MANIFEST}"

  # --baseline-only exists because the host is provisioned one run before any
  # project is deployed, and the baseline is worth verifying at that point. It
  # is an explicit flag rather than an inference from a missing
  # --project-a-outputs: an argument whose absence silently changes what a
  # command means is one typo away from an evidence run that measured nothing.
  if [ "${BASELINE_ONLY}" -eq 1 ]; then
    [ -z "${PROJECT_A_OUTPUTS}" ] \
      || die 2 "--baseline-only and --project-a-outputs contradict each other."
  else
    [ -n "${PROJECT_A_OUTPUTS}" ] \
      || die 2 "--mode host requires --project-a-outputs, or --baseline-only before any deploy."
    [ -f "${PROJECT_A_OUTPUTS}" ] || die 2 "not found: ${PROJECT_A_OUTPUTS}"
  fi

  [ "$(id -u)" -eq 0 ] || die 3 "--mode host requires root: it reads root-only host state."

  step "1. Host baseline, unchanged by this run"
  bin/provision-host.sh --host "${HOST_MANIFEST}" --check

  step "2. Host-local acceptance suite"
  mkdir -p "${EVIDENCE_DIR}"
  export APG_LIVE_HOST=1
  if [ "${BASELINE_ONLY}" -eq 0 ]; then
    export APG_PROJECT_A_OUTPUTS="${PROJECT_A_OUTPUTS}"
    [ -n "${PROJECT_B_OUTPUTS}" ] && export APG_PROJECT_B_OUTPUTS="${PROJECT_B_OUTPUTS}"
    [ -n "${SENTINEL_FILE}" ] && export APG_SECRET_SENTINEL_FILE="${SENTINEL_FILE}"
  fi

  run_suite "live_host" "${EVIDENCE_DIR}/session-02-host-tests.xml"

  # Every test that needs a deployed project is gated on APG_PROJECT_A_OUTPUTS
  # by requires_environment, so under --baseline-only they skip rather than
  # fail. That is also exactly why no evidence is written: a host evidence file
  # produced from a run where the project tests never executed would assert a
  # verdict nobody measured.
  if [ "${BASELINE_ONLY}" -eq 1 ]; then
    printf '\n\033[1msession-02-check: host baseline PASSED\033[0m\n'
    printf 'No evidence written. Every project test was skipped for want of\n'
    printf 'APG_PROJECT_A_OUTPUTS; this run makes no claim about a deployment.\n'
    return 0
  fi

  step "3. Host evidence"
  "$(python_bin)" bin/write-session-evidence.py --session 2 --mode host \
    --project-a-outputs "${PROJECT_A_OUTPUTS}" \
    --output "${EVIDENCE_DIR}/session-02-host.json"

  printf '\n\033[1msession-02-check: host PASSED\033[0m\n'
}

mode_external() {
  [ -n "${PUBLIC_IPV4}" ] || die 2 "--mode external requires --public-ipv4."
  [ -n "${PROJECT_A_OUTPUTS}" ] || die 2 "--mode external requires --project-a-outputs."
  [ -f "${PROJECT_A_OUTPUTS}" ] || die 2 "not found: ${PROJECT_A_OUTPUTS}"

  # Not enforceable from here -- the host could be behind the same NAT as the
  # operator -- so it is stated rather than checked, and the evidence records
  # the address the scan came from.
  printf 'session-02-check: this mode is only meaningful from a network that is\n'
  printf 'not the deployment host. A scan run on the host measures its own\n'
  printf 'routing table.\n'

  step "1. Public-path acceptance suite"
  mkdir -p "${EVIDENCE_DIR}"
  export APG_PUBLIC_IPV4="${PUBLIC_IPV4}"
  export APG_PROJECT_A_OUTPUTS="${PROJECT_A_OUTPUTS}"
  [ -n "${PUBLIC_IPV6}" ] && export APG_PUBLIC_IPV6="${PUBLIC_IPV6}"

  run_suite "external" "${EVIDENCE_DIR}/session-02-external-tests.xml"

  step "2. External evidence"
  "$(python_bin)" bin/write-session-evidence.py --session 2 --mode external \
    --project-a-outputs "${PROJECT_A_OUTPUTS}" \
    --output "${EVIDENCE_DIR}/session-02-external.json"

  printf '\n\033[1msession-02-check: external PASSED\033[0m\n'
}

main() {
  parse_arguments "$@"
  case "${MODE}" in
    offline) mode_offline ;;
    host) mode_host ;;
    external) mode_external ;;
  esac
}

main "$@"
