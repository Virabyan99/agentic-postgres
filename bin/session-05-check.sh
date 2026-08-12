#!/usr/bin/env bash
#
# The Session 5 gate. It does not replace bin/session-01-check.sh, which must
# still exit 0, nor the Session 2, 3 and 4 gates, which still own their own
# sessions' verdicts.
#
# Three modes, and the third one's return is a decision (D82):
#
#   --mode offline    a checkout: contracts, schemas, models, the API surface
#                     allowlist, the reviewed OpenAPI snapshot.
#   --mode host       the deployment host: the REST plane, the documentation
#                     route, the authorization boundaries, the restart matrix
#                     and whatever rotations this window performed.
#   --mode external   a different network: what a stranger can reach of an API
#                     plane that now carries authorization.
#
# External mode is emphatically not vacuous here (D132). Session 5 is the first
# session whose public surface carries authorization, so what a stranger can
# reach is a first-class measurement rather than a structural inference: the
# REST route answers, and answers 401; the documentation route refuses with a
# challenge; and neither serves a byte of credential to an unauthenticated
# caller. A boundary that is only argued from the inside is an argument.
#
# The claims this gate is answerable for are cumulative: Sessions 2, 3 and 4's
# are proved here too, because the product did not stop making those promises
# when it grew an HTTP surface (ADR 0039).
#
# **Session 5's evidence has two halves and cannot be written from one.** Three
# of its claims are measured from off-host, and the writer refuses a session
# document that is silent about a claim. Run both modes, then merge.
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

readonly SESSION=5
# Derived from SESSION rather than written out, and defined AFTER it, and that is not tidiness. Every
# other `session-04` in this file was renamed when it was copied; these were
# built by concatenating a literal prefix onto a variable, so the rename did not
# match them and the gate would have written the previous session's filenames
# while its own --help named files it never writes. A number that appears once
# cannot be left behind.
EVIDENCE_PREFIX="$(printf 'session-%02d' "${SESSION}")"
readonly EVIDENCE_PREFIX

MODE=""
HOST_MANIFEST=""
PROJECT_A_OUTPUTS=""
PROJECT_B_OUTPUTS=""
SENTINEL_FILE=""
ROTATED_FROM_FILE=""
ROTATED_AUTHENTICATOR_FROM_FILE=""
ROTATED_DOCS_FROM_FILE=""
ROTATED_JWT_FROM_FILE=""
PUBLIC_IPV4=""
PUBLIC_IPV6=""
SSH_DESTINATION=""
AFTER_REBOOT=0
KEYWORD=""

usage() {
  cat <<'USAGE'
Usage: bin/session-05-check.sh --mode offline
       sudo bin/session-05-check.sh --mode host --host FILE \
            --project-a-outputs FILE --project-b-outputs FILE \
            [--sentinel-file FILE] [--rotated-from-file FILE] \
            [--rotated-authenticator-from-file FILE] \
            [--rotated-docs-from-file FILE] \
            [--rotated-jwt-from-file FILE] \
            [--after-reboot] [-k EXPRESSION]
       bin/session-05-check.sh --mode external --public-ipv4 ADDR \
            --project-a-outputs FILE --ssh-destination USER@HOST \
            [--public-ipv6 ADDR] [--project-b-outputs FILE] [-k EXPRESSION]

  --mode offline   Contracts, schemas, models, the reviewed API surface and the
                   committed OpenAPI snapshot. No host.
  --mode host      Everything measurable on the deployment host: the REST plane,
                   the documentation route, the authorization boundaries, the
                   restart matrix, and whatever rotations this window performed.
                   Needs root: it reads root-only state -- the secret
                   generations, the edge's dynamic directory, systemd.
  --mode external  What the public internet can reach of an API plane that now
                   carries authorization. MUST run from a network that is not
                   the deployment host: a scan run on the host measures its own
                   routing table.

  --project-b-outputs   Required in host mode. Session 4's isolation claim is
                        about two projects' transports, and one project cannot
                        be isolated from nothing. Optional in external mode,
                        where no test reads it and the merge compares which
                        deployment each half described.
  --ssh-destination     Required in external mode. DX-DB-001 and DX-DB-002 are
                        about a developer's helper reaching the host; without a
                        destination both skip, and a skip is not a pass.
  --sentinel-file       The planted secret value, from the ACTIVE generation.
                        Without it the secret-leakage proofs skip and the run
                        reports that claim unproved.
  --rotated-from-file   The credential from BEFORE a rotation. Supplied only in
                        the maintenance window that rotated it; without it the
                        rotation proof skips, which is honest -- no rotation
                        happened in this run.
  --rotated-authenticator-from-file FILE
                        The authenticator password this window replaced, so the
                        proof that the cluster no longer accepts it can run. Its
                        absence skips that proof rather than passing it.
  --rotated-docs-from-file FILE
                        The documentation Basic Auth password this window
                        replaced. The proof it admits asserts the NEW one opens
                        the page as well as that the old one does not: a
                        rotation Traefik never reloaded refuses both.
  --rotated-jwt-from-file FILE
                        The retired signing key's public material, as JSON. The
                        proof it admits is of the second phase only -- the
                        intermediate state accepts both keys by design, and a
                        check run there would pass whether or not the retirement
                        ever happened.
  --after-reboot        Declare that the host has just rebooted, which admits
                        the proof that the clusters came back by themselves.
                        Wait for the units to reach `active` first: a check run
                        at `up 0 min` reports failures that all mean "still
                        booting".
  -k EXPRESSION         Restrict to matching tests. Writes no evidence: a run
                        that selected a subset cannot support a claim about the
                        whole.

Each mode writes one evidence half. Session 4 needs BOTH -- two of its claims
are measured from off-host -- so merge them with:
  python bin/write-session-evidence.py --session 5 \
    --host-input evidence/session-05-host.json \
    --external-input evidence/session-05-external.json \
    --output evidence/session-05.json

This command verifies and never deploys. Use ./deploy.sh --through-session 5
to deploy, then run this to find out whether it worked.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'session-05-check: %s\n' "$*" >&2
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

# Host mode runs under sudo, so everything written below lands root:root -- and
# the operator who has to read the verdict and commit the evidence cannot. That
# is D194's remainder: the deploy learned to hand its checkout back, and the
# gate never learned to hand its evidence back.
#
# A no-op without SUDO_UID, because outside sudo there is no operator to hand
# anything to and guessing an owner is worse than doing nothing. Failures are
# ignored deliberately: this runs after the verdict, and a chown that cannot
# proceed must not turn a passing gate into a failing one.
restore_evidence_ownership() {
  [ -n "${SUDO_UID:-}" ] && [ -n "${SUDO_GID:-}" ] || return 0
  chown -R "${SUDO_UID}:${SUDO_GID}" "${EVIDENCE_DIR}" 2>/dev/null || true
}

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
      --rotated-authenticator-from-file)
        [ "$#" -ge 2 ] || die 2 "--rotated-authenticator-from-file requires a value."
        ROTATED_AUTHENTICATOR_FROM_FILE="$2"
        shift 2
        ;;
      --rotated-docs-from-file)
        [ "$#" -ge 2 ] || die 2 "--rotated-docs-from-file requires a value."
        ROTATED_DOCS_FROM_FILE="$2"
        shift 2
        ;;
      --rotated-jwt-from-file)
        [ "$#" -ge 2 ] || die 2 "--rotated-jwt-from-file requires a value."
        ROTATED_JWT_FROM_FILE="$2"
        shift 2
        ;;
      --rotated-from-file)
        [ "$#" -ge 2 ] || die 2 "--rotated-from-file requires a value."
        ROTATED_FROM_FILE="$2"
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
      --ssh-destination)
        [ "$#" -ge 2 ] || die 2 "--ssh-destination requires a value."
        SSH_DESTINATION="$2"
        shift 2
        ;;
      --after-reboot)
        AFTER_REBOOT=1
        shift
        ;;
      -k)
        [ "$#" -ge 2 ] || die 2 "-k requires an expression."
        KEYWORD="$2"
        shift 2
        ;;
      --mode=*|--host=*|--project-a-outputs=*|--project-b-outputs=*|--sentinel-file=*)
        die 2 "use a space, not '=': ${1%%=*} VALUE"
        ;;
      --rotated-from-file=*|--public-ipv4=*|--public-ipv6=*|--ssh-destination=*)
        die 2 "use a space, not '=': ${1%%=*} VALUE"
        ;;
      --baseline-only)
        die 2 "--baseline-only belongs to bin/session-02-check.sh; Session 4 measures deployed transports."
        ;;
      # The runbook's shape for this gate (D82). Named rather than swept into
      # "unknown argument", because an operator reading the runbook is asking a
      # reasonable question and the answer is a different flag, not a typo.
      --capabilities)
        die 2 "there is no --capabilities: the gate takes deployed documents, not operator inputs. See --help."
        ;;
      --external-probe)
        die 2 "there is no --external-probe: external mode takes --public-ipv4 and runs from off-host. See --help."
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

# Every mode runs pytest with the same selector shape, so none can drift into its
# own definition of passing.
run_suite() {
  local marker="$1" junit="$2"
  local -a arguments=(-q -m "${marker}")
  [ -n "${KEYWORD}" ] && arguments+=(-k "${KEYWORD}")
  [ -n "${junit}" ] && arguments+=(--junitxml="${junit}")

  "$(python_bin)" -m pytest "${arguments[@]}"
}

# A claim's proofs are not all environment-gated: some also name contract tests
# that run anywhere, which `-m live_host` therefore never collects. They are run
# explicitly rather than by widening the selector, which would drag the whole
# contract suite into a deployment run. The node IDs come from the acceptance
# registry, so a requirement that gains a test gains it here without anyone
# editing this script.
claim_static_nodeids() {
  PYTHONPATH="${ROOT_DIR}/src" "$(python_bin)" - "$1" "$2" <<'PYTHON'
import sys

from agentic_postgres.evidence_claims import static_nodeids_for_mode

for nodeid in static_nodeids_for_mode(sys.argv[1], int(sys.argv[2])):
    print(nodeid)
PYTHON
}

# Writes ${junit} only if this mode has environment-free proofs to run. An empty
# list is legitimate and does NOT mean the mode carries no claim: Session 4's
# two external claims are proved entirely by tests marked `external`, every one
# of which the suite above already collected (ADR 0045). It must never be read
# as "run everything" -- `pytest` with no arguments collects the whole suite,
# which is the most expensive possible way to measure nothing.
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
    printf 'Every proof of this mode'"'"'s claims carries its own marker; the suite above ran them all.\n'
    return 0
  fi

  "$(python_bin)" -m pytest -q --junitxml="${junit}" "${nodeids[@]}"
}

# One writer invocation for both evidence-writing modes. Two copies drifted
# apart once already in Session 2 -- the host branch gained --project-b-outputs
# and the external one did not, which the merge then reported as two different
# deployments.
write_evidence() {
  local mode="$1"
  local suite_junit="${EVIDENCE_DIR}/${EVIDENCE_PREFIX}-${mode}-tests.xml"
  local claims_junit="${EVIDENCE_DIR}/${EVIDENCE_PREFIX}-${mode}-claims.xml"

  local -a arguments=(
    --session "${SESSION}" --mode "${mode}"
    --project-a-outputs "${PROJECT_A_OUTPUTS}"
    --junit "${suite_junit}"
    --output "${EVIDENCE_DIR}/${EVIDENCE_PREFIX}-${mode}.json"
  )
  [ -f "${claims_junit}" ] && arguments+=(--junit "${claims_junit}")
  [ -n "${PROJECT_B_OUTPUTS}" ] && arguments+=(--project-b-outputs "${PROJECT_B_OUTPUTS}")

  "$(python_bin)" bin/write-session-evidence.py "${arguments[@]}"
}

# Evidence is written only by a run that selected everything. -k is for iterating
# on one failure, and an evidence file produced from a filtered run would report
# a claim on the strength of whichever tests the expression happened to match.
evidence_is_supportable() {
  [ -z "${KEYWORD}" ]
}

announce_no_evidence() {
  printf '\nNo evidence written: -k selected a subset of the suite, so this run\n'
  printf 'cannot support a claim about the whole.\n'
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

  printf '\n\033[1msession-05-check: offline PASSED\033[0m\n'
}

mode_host() {
  # Arguments before privilege, deliberately. An operator iterating on a command
  # line should learn they mistyped a flag without first having to obtain root
  # to be told.
  [ -n "${HOST_MANIFEST}" ] || die 2 "--mode host requires --host."
  [ -f "${HOST_MANIFEST}" ] || die 2 "host manifest not found: ${HOST_MANIFEST}"
  [ -n "${PROJECT_A_OUTPUTS}" ] || die 2 "--mode host requires --project-a-outputs."
  [ -f "${PROJECT_A_OUTPUTS}" ] || die 2 "not found: ${PROJECT_A_OUTPUTS}"

  # Required, as in Session 3. `transport_isolation` is a claim about two
  # projects; with one project every proof of it would skip, the claim would come
  # out `not_run`, and the run would report that as a failure anyway -- after
  # doing all the work. Refusing up front says the same thing sooner.
  [ -n "${PROJECT_B_OUTPUTS}" ] \
    || die 2 "--mode host requires --project-b-outputs: the isolation claim is about two projects."
  [ -f "${PROJECT_B_OUTPUTS}" ] || die 2 "not found: ${PROJECT_B_OUTPUTS}"

  [ -z "${ROTATED_FROM_FILE}" ] || [ -f "${ROTATED_FROM_FILE}" ] \
    || die 2 "not found: ${ROTATED_FROM_FILE}"
  # Checked here, before root is demanded and before anything runs. A path with
  # a typo in it is otherwise discovered after `sudo`, in a suite that skips the
  # proof the flag exists to admit -- and a skip is indistinguishable from "no
  # rotation happened in this run", which is the honest reading of the flag's
  # absence and the wrong reading of its misspelling.
  [ -z "${ROTATED_AUTHENTICATOR_FROM_FILE}" ] || [ -f "${ROTATED_AUTHENTICATOR_FROM_FILE}" ] \
    || die 2 "not found: ${ROTATED_AUTHENTICATOR_FROM_FILE}"
  [ -z "${ROTATED_DOCS_FROM_FILE}" ] || [ -f "${ROTATED_DOCS_FROM_FILE}" ] \
    || die 2 "not found: ${ROTATED_DOCS_FROM_FILE}"
  [ -z "${ROTATED_JWT_FROM_FILE}" ] || [ -f "${ROTATED_JWT_FROM_FILE}" ] \
    || die 2 "not found: ${ROTATED_JWT_FROM_FILE}"

  [ "$(id -u)" -eq 0 ] || die 3 "--mode host requires root: it reads root-only host state."

  step "1. Host baseline, unchanged by this run"
  bin/provision-host.sh --host "${HOST_MANIFEST}" --check

  step "2. Host-local acceptance suite, over two projects"
  mkdir -p "${EVIDENCE_DIR}"
  # On EXIT, not after the last step: the evidence is written whether or not
  # the suite passed, and a failing gate is the run whose output an operator
  # most needs to read. Registered after the directory exists so the handback
  # never runs against a path this invocation did not create.
  trap restore_evidence_ownership EXIT
  export APG_LIVE_HOST=1
  export APG_EDGE_DEPLOYED=1
  export APG_PROJECT_A_OUTPUTS="${PROJECT_A_OUTPUTS}"
  export APG_PROJECT_B_OUTPUTS="${PROJECT_B_OUTPUTS}"
  [ -n "${SENTINEL_FILE}" ] && export APG_SECRET_SENTINEL_FILE="${SENTINEL_FILE}"
  [ -n "${ROTATED_FROM_FILE}" ] && export APG_ROTATED_FROM_FILE="${ROTATED_FROM_FILE}"
  # One variable per credential. A window rotates one at a time, and a single
  # flag would admit all three proofs on the strength of whichever was actually
  # rotated -- which is the false declaration each of those tests is written to
  # refuse, arriving through the gate instead of through the operator.
  [ -n "${ROTATED_AUTHENTICATOR_FROM_FILE}" ] &&
    export APG_ROTATED_AUTHENTICATOR_FROM_FILE="${ROTATED_AUTHENTICATOR_FROM_FILE}"
  [ -n "${ROTATED_DOCS_FROM_FILE}" ] && export APG_ROTATED_DOCS_FROM_FILE="${ROTATED_DOCS_FROM_FILE}"
  [ -n "${ROTATED_JWT_FROM_FILE}" ] && export APG_ROTATED_JWT_FROM_FILE="${ROTATED_JWT_FROM_FILE}"
  [ "${AFTER_REBOOT}" -eq 1 ] && export APG_AFTER_REBOOT=1

  run_suite "live_host" "${EVIDENCE_DIR}/${EVIDENCE_PREFIX}-host-tests.xml"

  if ! evidence_is_supportable; then
    announce_no_evidence
    printf '\n\033[1msession-05-check: host PASSED\033[0m\n'
    return 0
  fi

  step "3. Static proofs of the claims this run records"
  run_claim_proofs host "${EVIDENCE_DIR}/${EVIDENCE_PREFIX}-host-claims.xml"

  step "4. Host evidence"
  write_evidence host

  printf '\n\033[1msession-05-check: host PASSED\033[0m\n'
  printf 'This is one half. Session 4 also needs --mode external; see --help.\n'
}

mode_external() {
  [ -n "${PUBLIC_IPV4}" ] || die 2 "--mode external requires --public-ipv4."
  [ -n "${PROJECT_A_OUTPUTS}" ] || die 2 "--mode external requires --project-a-outputs."
  [ -f "${PROJECT_A_OUTPUTS}" ] || die 2 "not found: ${PROJECT_A_OUTPUTS}"

  # Required, unlike in Session 2's external mode, and for the reason
  # --project-b-outputs is required on the host: without it the two
  # `connection_tooling` proofs skip, the claim resolves `not_run`, and the run
  # fails after doing the work.
  [ -n "${SSH_DESTINATION}" ] \
    || die 2 "--mode external requires --ssh-destination: the helper and the broker are reached over SSH."

  # Optional, and not exported: no external test reads project B. It is here
  # because the merge compares which deployment each half described, and a half
  # naming one project of a two-project host would read as a different system
  # rather than as the same one measured from outside.
  [ -z "${PROJECT_B_OUTPUTS}" ] || [ -f "${PROJECT_B_OUTPUTS}" ] \
    || die 2 "not found: ${PROJECT_B_OUTPUTS}"

  # Not enforceable from here -- the host could be behind the same NAT as the
  # operator -- so it is stated rather than checked, and the suite carries its
  # own positive control: 443 must answer, or every "closed" result below is a
  # statement about this network rather than about the host.
  printf 'session-05-check: this mode is only meaningful from a network that is\n'
  printf 'not the deployment host. A scan run on the host measures its own\n'
  printf 'routing table.\n'

  step "1. Public-path and helper acceptance suite"
  mkdir -p "${EVIDENCE_DIR}"
  # On EXIT, not after the last step: the evidence is written whether or not
  # the suite passed, and a failing gate is the run whose output an operator
  # most needs to read. Registered after the directory exists so the handback
  # never runs against a path this invocation did not create.
  trap restore_evidence_ownership EXIT
  export APG_PUBLIC_IPV4="${PUBLIC_IPV4}"
  export APG_PROJECT_A_OUTPUTS="${PROJECT_A_OUTPUTS}"
  export APG_SSH_DESTINATION="${SSH_DESTINATION}"
  [ -n "${PUBLIC_IPV6}" ] && export APG_PUBLIC_IPV6="${PUBLIC_IPV6}"

  run_suite "external" "${EVIDENCE_DIR}/${EVIDENCE_PREFIX}-external-tests.xml"

  if ! evidence_is_supportable; then
    announce_no_evidence
    printf '\n\033[1msession-05-check: external PASSED\033[0m\n'
    return 0
  fi

  step "2. Static proofs of the claims this run records"
  run_claim_proofs external "${EVIDENCE_DIR}/${EVIDENCE_PREFIX}-external-claims.xml"

  step "3. External evidence"
  write_evidence external

  printf '\n\033[1msession-05-check: external PASSED\033[0m\n'
  printf 'This is one half. Session 4 also needs --mode host; see --help.\n'
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
