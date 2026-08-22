#!/usr/bin/env bash
#
# The Session 9 gate: agent WRITES, the durable audit record, and revocation. It
# does not replace bin/session-01-check.sh, which must still exit 0, nor the
# Session 2-8 gates, which still own their own sessions' verdicts.
#
# Three modes, and the shape is Session 5's deliberately (D221). Five sessions
# of runbooks have proposed a gate that takes manifests and five gates have
# implemented one that takes deployed documents: a gate over manifests measures
# what was asked for, and a gate over deployed documents measures what happened.
#
#   --mode offline    a checkout: contracts, schemas, models, the reviewed API
#                     surfaces, the compiled capability contract, and the
#                     write, audit and revocation contract suites.
#   --mode host       the deployment host: an agent WRITING through the plane,
#                     the two records one write leaves, a write failing closed
#                     on its audit record, and a revoked token failing its next
#                     read, write and direct request.
#   --mode external   a different network: what a stranger reaches. Session 9
#                     adds no external claim of its own -- and it still needs
#                     this mode, which was checked rather than assumed.
#
# **Session 9's own five claims are all `host`.** The gate still has three modes
# because `claims_through_session(9)` is CUMULATIVE: a Session 9 document must
# answer for five external claims inherited from Sessions 4-8, including
# `public_agent_boundary`, and the writer refuses a document silent about a
# claim. A two-mode gate here would have written one, quietly. Run both, merge.
#
# **D404 is this gate's shape rather than a note in a runbook.** The runbook
# proposed `--project project.yaml --peer-project ...`, which is a gate over
# manifests and does not exist here -- and that is the SECOND time the runbook
# family has proposed the wrong invocation (D316). Every flag a claim depends on
# is written INTO the documented command below, not mentioned underneath it:
# D213 recorded thirteen secret proofs gated on a flag that was not passed once
# all session, one of which had been checking one consumer of thirteen while
# reporting success.
#
# **Three things must be true of the deployment before host mode means anything**,
# and they are checked rather than assumed:
#
#   1. `routes.mcp` must be `ready`. D326's two-stage convergence means the
#      FIRST deploy that starts an MCP container publishes `unavailable` and the
#      redeploy publishes `ready`. **Deploy twice.**
#   2. The deployed document must be at the current outputs version. The
#      previous trip found both hosts a version behind while the tree had moved
#      on, and `evidence.py` refuses a deployed document that is not current --
#      so the redeploy is a prerequisite of the gate, not a consequence of it.
#      This session does NOT move the version: `tool_count` 4 -> 6 is a value,
#      not a shape (D485), and nothing else in the document moved.
#   3. **Migrations 0019 AND 0020 must be applied**, and this is Session 9's own
#      precondition. Both are released here and were applied on no cluster at the
#      end of Run 7. Without them every write, audit and revocation proof fails
#      on `relation "app_private.agent_audit" does not exist` or on `permission
#      denied for function`, and the operator reads thirteen tracebacks to learn
#      one thing -- which is the reason check 1 exists and the same reason this
#      one does.
#
# The outputs version is NOT this session's; it is checked because a stale
# document makes every other check measure the wrong deployment.
#
# It VERIFIES. It does not deploy. A gate that deploys the system it measures
# cannot be re-run to confirm a fix, and its result depends on whether it was
# the first run (D20).
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

readonly SESSION=9
# Derived from SESSION rather than written out, and defined AFTER it. Session
# 5's copy of this file carries the reason: every other `session-04` in it was
# renamed when it was copied, and these two were built by concatenating a
# literal prefix onto a variable, so the rename did not match them and the gate
# would have written the previous session's filenames while its own --help named
# files it never writes. A number that appears once cannot be left behind.
EVIDENCE_PREFIX="$(printf 'session-%02d' "${SESSION}")"
readonly EVIDENCE_PREFIX

MODE=""
HOST_MANIFEST=""
PROJECT_A_OUTPUTS=""
PROJECT_B_OUTPUTS=""
SENTINEL_FILE=""
ADMIN_PASSWORD_FILE=""
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
Usage: bin/session-09-check.sh --mode offline
       sudo bin/session-09-check.sh --mode host --host host.yaml \
            --project-a-outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json \
            --project-b-outputs /etc/agentic-postgres/projects/beta-dev/outputs.json \
            --admin-password-file /root/alpha-dev-administrator \
            --sentinel-file "$(sudo python3 -c "
import json
from pathlib import Path
root = Path('/var/lib/agentic-postgres/secrets/alpha-dev')
gen = json.loads((root / 'active-secret-generation.json').read_text())['generation_id']
print(root / 'generations' / gen / 'secret-check' / 'session2_sentinel')
")" \
            [--rotated-authenticator-from-file FILE] \
            [--rotated-docs-from-file FILE] [--rotated-jwt-from-file FILE] \
            [--after-reboot] [-k EXPRESSION]

  DERIVE the sentinel path, never type it: the generation directory changes on
  every start, so a hard-coded one silently names a superseded generation and
  the scan then fails to find what it planted.
       bin/session-09-check.sh --mode external --public-ipv4 ADDR \
            --project-a-outputs FILE --ssh-destination op@HOST \
            [--public-ipv6 ADDR] [--project-b-outputs FILE] [-k EXPRESSION]

  --mode offline   Contracts, schemas, models, the reviewed API surfaces, the
                   compiled capability contract, and the agent plane's own
                   contract suite. No host.
  --mode host      The agent plane as it is served: one published path, a
                   private health surface, the tokens it accepts, what its
                   container holds, and what an agent can read. Needs root: it
                   reads root-only state -- the secret generations, the signing
                   keys, the edge's dynamic directory.
  --mode external  What the public internet reaches of the agent plane. MUST run
                   from a network that is not the deployment host: a scan run on
                   the host measures its own routing table, and the health
                   routes answer 200 there.

  --project-b-outputs   Required in host mode. `project_isolation` is a claim
                        about two projects' identity planes, and one project
                        cannot be isolated from nothing. It is also what makes
                        the agent plane's cross-project refusal a refusal of a
                        REAL peer rather than of a string. Optional in external
                        mode, where no test reads it and the merge compares
                        which deployment each half described.
  --sentinel-file       The planted secret value, from the ACTIVE generation.
                        It is in the command above rather than described below
                        it, because a flag mentioned under a command is a flag
                        that does not get passed (D213). Without it the secret
                        leakage proofs skip and the claim reports unproved.
  --admin-password-file The project administrator's password, as written when
                        `bin/auth-admin.sh bootstrap` created it. It cannot be
                        recovered from the host -- only an Argon2id hash is
                        stored, which is what SEC-CRED-001 asserts -- so the
                        proofs that need an administrator session have to be
                        given one. Without it they skip, and four claims report
                        `not_run` rather than passing on a subset.
  --ssh-destination     Required in external mode, and it is `op@HOST`. D466:
                        the access broker grants ONE enumerated account, and
                        `apg-agent@` -- the read-only diagnosis account, and the
                        intuitive choice -- is refused. Without a destination
                        the two connection-tooling proofs skip, and a skip is
                        not a pass.
  --rotated-authenticator-from-file FILE
                        The authenticator password this window replaced.
  --rotated-docs-from-file FILE
                        The documentation Basic Auth password this window
                        replaced.
  --rotated-jwt-from-file FILE
                        The retired signing key's public material, as JSON.
                        There are FOUR verifiers now (ADR 0113, ADR 0122): the
                        agent plane reads the same rendered jwks.json PostgREST
                        and storage do, and every one is RECREATED rather than
                        restarted after the published set changes (ADR 0088).
  --after-reboot        Declare that the host has just rebooted, which admits
                        the proof that the clusters came back by themselves.
                        Wait for the units to reach `active` first.
  -k EXPRESSION         Restrict to matching tests. Writes no evidence: a run
                        that selected a subset cannot support a claim about the
                        whole.

BEFORE host mode, deploy TWICE. The first deploy that starts an MCP container
publishes `routes.mcp: unavailable` -- two-stage convergence, D326 -- and the
redeploy publishes `ready`. The gate refuses a document that is not ready rather
than measuring a closed port twelve proofs deep.

Each mode writes one evidence half. Session 9 needs BOTH -- `public_agent_boundary`
is measured from off-host -- so merge them with:
  python bin/write-session-evidence.py --session 9 \
    --host-input evidence/session-09-host.json \
    --external-input evidence/session-09-external.json \
    --output evidence/session-09.json

This command verifies and never deploys. Use ./deploy.sh --through-session 9
to deploy, then run this to find out whether it worked.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'session-09-check: %s\n' "$*" >&2
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
# the operator who has to read the verdict and commit the evidence cannot.
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
      --admin-password-file)
        [ "$#" -ge 2 ] || die 2 "--admin-password-file requires a value."
        ADMIN_PASSWORD_FILE="$2"
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
      --admin-password-file=*|--rotated-from-file=*|--public-ipv4=*|--public-ipv6=*)
        die 2 "use a space, not '=': ${1%%=*} VALUE"
        ;;
      --ssh-destination=*)
        die 2 "use a space, not '=': ${1%%=*} VALUE"
        ;;
      # The runbook's shapes for this gate, named rather than swept into
      # "unknown argument". An operator reading the runbook is asking a
      # reasonable question, and the answer is a different flag rather than a
      # usage error.
      --project|--project=*)
        die 2 "there is no --project: the gate takes DEPLOYED documents, not manifests. A gate over manifests measures what was asked for. See --help."
        ;;
      --peer-project|--peer-project=*)
        # D404, and D316 is the same refusal from Session 7. The runbook family
        # has now proposed this invocation twice.
        die 2 "there is no --peer-project: use --project-b-outputs, which names the peer's DEPLOYED document rather than its manifest. See --help."
        ;;
      --capabilities|--capabilities=*)
        die 2 "there is no --capabilities: the gate takes deployed documents, not operator inputs. The compiled capability contract is checked in offline mode by bin/mcp-contract.sh. See --help."
        ;;
      --capability-lock|--capability-lock=*)
        # The lock the runtime obeys is the DEPLOYED one, mounted into the
        # container. A gate handed a lock would be measuring the file somebody
        # typed rather than the file the plane reads (ADR 0126).
        die 2 "there is no --capability-lock: the plane obeys the lock mounted into its container, and that is what host mode measures. See --help."
        ;;
      --agent-token|--agent-token=*)
        # The suite creates its own agent through the product's own
        # `auth_create_agent` and obtains a token from the deployment. A gate
        # given one would prove that somebody can hold a token.
        die 2 "there is no --agent-token: the suite creates an agent through the product's own auth_create_agent and obtains a token from the deployment. See --help."
        ;;
      --baseline-only)
        die 2 "--baseline-only belongs to bin/session-02-check.sh; Session 8 measures a deployed agent plane."
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
#
# Session 8 has more of these than any session before it. ADR 0132 is why: four
# of its requirements were proved offline first and gained live proofs rather
# than twins, so each carries both halves.
claim_static_nodeids() {
  PYTHONPATH="${ROOT_DIR}/src" "$(python_bin)" - "$1" "$2" <<'PYTHON'
import sys

from agentic_postgres.evidence_claims import static_nodeids_for_mode

for nodeid in static_nodeids_for_mode(sys.argv[1], int(sys.argv[2])):
    print(nodeid)
PYTHON
}

# Writes ${junit} only if this mode has environment-free proofs to run. An empty
# list is legitimate and does NOT mean the mode carries no claim. It must never
# be read as "run everything": `pytest` with no arguments collects the whole
# suite, which is the most expensive possible way to measure nothing.
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

# D212, as a hard failure rather than a skip (ADR 0073).
#
# The state comes from `tests/contract/rendered_fixtures.py`, which is already
# the authority on it, rather than from a second implementation here.
check_rendered_fixtures() {
  local state detail
  local report
  report="$(PYTHONPATH="${ROOT_DIR}/src:${ROOT_DIR}/tests/contract" "$(python_bin)" -c \
    'import rendered_fixtures as f; print(f.STATE); print(f.DETAIL)')" \
    || die 6 "could not determine the rendered fixtures' state."

  state="$(printf '%s' "${report}" | sed -n 1p)"
  detail="$(printf '%s' "${report}" | sed -n 2p)"

  case "${state}" in
    current)
      printf 'rendered fixtures: %s\n' "${detail}"
      ;;
    absent|stale)
      die 6 "rendered fixtures are ${state}: ${detail}

A gate does not skip this. The compose-model proofs read those fixtures, and a
run that never collected them exits 0 having measured less than it reports --
which is D212. Re-render both projects ON THE HOST (D383 -- .generated/ is
gitignored and is never transported):

  ./deploy.sh --project project.example.yaml        --capabilities capabilities.example.yaml --render-only
  ./deploy.sh --project project.second.example.yaml --capabilities capabilities.example.yaml --render-only"
      ;;
    *)
      die 6 "unknown fixture state: ${state}"
      ;;
  esac
}

# The agent plane's own precondition, and the reason it is a gate check rather
# than a note. Every Session 9 host claim measures a served plane; if the route
# is not published, forty proofs fail on a connection error and the operator has
# to read forty tracebacks to learn one thing.
#
# D326's two-stage convergence is the ordinary case, not an error: the deploy
# that FIRST starts an MCP container observes it before it is reachable, so
# `unavailable` is what a correct first deploy publishes. The answer is to
# deploy again.
check_agent_plane_is_published() {
  local document="$1"
  PYTHONPATH="${ROOT_DIR}/src" "$(python_bin)" - "${document}" <<'PYTHON' || exit 6
import json
import sys
from pathlib import Path

document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
route = (document.get("routes") or {}).get("mcp")
mcp = document.get("mcp") or {}

if not isinstance(route, dict):
    sys.exit(
        f"routes.mcp is {route!r}, not a published-route object. Outputs v12 publishes "
        "it as one; a string means this deployment predates the version that carries "
        "the agent plane, and evidence.py refuses a document that is not current -- so "
        "REDEPLOY before running this gate."
    )

if route.get("status") != "ready":
    sys.exit(
        f"routes.mcp is {route.get('status')!r}, not 'ready'. If an MCP container has "
        "just started for the first time, this is D326's two-stage convergence working "
        "as designed: the deploy observed the route before the edge had attached it. "
        "DEPLOY AGAIN and re-run."
    )

if mcp.get("status") != "ready" or not mcp.get("protocol_revision"):
    sys.exit(
        f"the mcp block is {mcp.get('status')!r} with protocol_revision "
        f"{mcp.get('protocol_revision')!r}. The route is served and the block is not, "
        "which is the asymmetry D395 found in the other direction."
    )

print(f"agent plane: {route['url']} at protocol {mcp['protocol_revision']}")
PYTHON
}

# **Session 9's own precondition**, and it is the reason this session has one at
# all. Migrations 0019 (the audit record and the write RPCs' own rows) and 0020
# (the record's one reader) were released in Runs 1 and 7 and applied on NO
# cluster. Every write, audit and revocation proof below needs both.
#
# Without this check the failure is thirteen tracebacks saying `relation
# "app_private.agent_audit" does not exist` and `permission denied for function
# auth_list_agent_audit`, from which an operator has to reconstruct one fact.
# That is exactly what `check_agent_plane_is_published` exists to prevent, one
# session earlier, and this is the same check for this session's own dependency.
#
# It asks the CLUSTER, not the manifest: `bin/migrate.sh status` needs a project
# manifest, which is a gitignored host-only input this gate does not take, and
# the question is what was applied rather than what was asked for.
check_the_audit_plane_is_migrated() {
  local document="$1"
  PYTHONPATH="${ROOT_DIR}/src" "$(python_bin)" - "${document}" <<'PYTHON' || exit 6
import json
import subprocess
import sys
from pathlib import Path

from agentic_postgres import migrations

document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
container = document["database"]["container"]
database = document["database"]["name"]

released = [entry["version"] for entry in migrations.load_manifest()["migrations"]]

probe = subprocess.run(  # noqa: S603
    [
        "docker", "exec", "-i", container,
        "psql", "-U", "postgres", "-d", database, "-X", "-qtA",
        "-v", "ON_ERROR_STOP=1",
        "-c", "SELECT version FROM app_private.schema_migrations ORDER BY version",
    ],
    capture_output=True,
    text=True,
    check=False,
    timeout=60,
)
if probe.returncode != 0:
    sys.exit(
        f"could not read {database}'s migration ledger from {container}: "
        f"{probe.stderr.strip()[:300]}"
    )

applied = {line.strip() for line in probe.stdout.splitlines() if line.strip()}
missing = [version for version in released if version not in applied]

if missing:
    names = {entry["version"]: entry["name"] for entry in migrations.load_manifest()["migrations"]}
    listed = ", ".join(f"{version} ({names[version]})" for version in missing)
    sys.exit(
        f"{len(missing)} released migration(s) are NOT applied to {database}: {listed}.\n"
        "Every write, audit and revocation proof in this gate needs them, and without "
        "this check they would fail as a wall of 'relation does not exist' and "
        "'permission denied for function'.\n"
        "Apply them on the host, as the migration user and never as a superuser "
        "(D285):\n"
        "  bin/migrate.sh --project <project.yaml> up"
    )

print(f"migrations: all {len(released)} released migrations are applied to {database}")
PYTHON
}

mode_offline() {
  step "1. Static quality"
  shellcheck deploy.sh bin/*.sh libexec/*
  "$(python_bin)" -m ruff check src bin tests
  "$(python_bin)" -m ruff format --check src bin tests
  bin/lock-versions.sh --check

  step "2. Rendered fixtures are current"
  check_rendered_fixtures

  step "3. Offline contract suite"
  run_suite "p0 and not future and not live_host and not external" ""

  step "4. Environment-gated tests collect and skip"
  # A module that opened a socket at import time would break collection for the
  # whole suite, and this is the cheapest place to find that out. It is also the
  # only offline check that touches this session's new deployment modules.
  run_suite "live_host or external" ""

  step "5. Models resolve"
  bin/compose.sh --edge --host host.example.yaml config >/dev/null
  printf 'edge model resolves\n'

  step "6. The reviewed API surfaces and the capability contract"
  bin/api-contract.sh --check
  bin/app-contract.sh --check
  # Session 9 inherits: the compiled, project-neutral capability contract, and the
  # check path contains no writer (ADR 0119, ADR 0120).
  bin/mcp-contract.sh check

  step "7. Registry and generated documentation"
  "$(python_bin)" -m pytest -q tests/contract/test_acceptance_registry.py
  "$(python_bin)" bin/render-acceptance-matrix.py --check

  printf '\n\033[1msession-09-check: offline PASSED\033[0m\n'
}

mode_host() {
  # Arguments before privilege, deliberately. An operator iterating on a command
  # line should learn they mistyped a flag without first having to obtain root
  # to be told.
  [ -n "${HOST_MANIFEST}" ] || die 2 "--mode host requires --host."
  [ -f "${HOST_MANIFEST}" ] || die 2 "host manifest not found: ${HOST_MANIFEST}"
  [ -n "${PROJECT_A_OUTPUTS}" ] || die 2 "--mode host requires --project-a-outputs."
  [ -f "${PROJECT_A_OUTPUTS}" ] || die 2 "not found: ${PROJECT_A_OUTPUTS}"

  [ -n "${PROJECT_B_OUTPUTS}" ] \
    || die 2 "--mode host requires --project-b-outputs: the isolation claim is about two projects."
  [ -f "${PROJECT_B_OUTPUTS}" ] || die 2 "not found: ${PROJECT_B_OUTPUTS}"

  # Checked here, before root is demanded and before anything runs. A path with
  # a typo in it is otherwise discovered after `sudo`, in a suite that skips the
  # proof the flag exists to admit -- and a skip is indistinguishable from "no
  # rotation happened in this run", which is the honest reading of the flag's
  # absence and the wrong reading of its misspelling.
  local file
  for file in "${SENTINEL_FILE}" "${ADMIN_PASSWORD_FILE}" "${ROTATED_FROM_FILE}" \
              "${ROTATED_AUTHENTICATOR_FROM_FILE}" "${ROTATED_DOCS_FROM_FILE}" \
              "${ROTATED_JWT_FROM_FILE}"; do
    [ -z "${file}" ] || [ -f "${file}" ] || die 2 "not found: ${file}"
  done

  [ "$(id -u)" -eq 0 ] || die 3 "--mode host requires root: it reads root-only host state."

  # Said rather than refused. A window in which the operator does not have the
  # administrator's password to hand is a legitimate run, and the claims it
  # cannot prove will report `not_run` -- which is the evidence model working.
  if [ -z "${ADMIN_PASSWORD_FILE}" ]; then
    printf 'session-09-check: no --admin-password-file, so the proofs needing an\n'
    printf 'administrator session will skip and four claims will report not_run.\n'
  fi

  step "1. Host baseline, unchanged by this run"
  bin/provision-host.sh --host "${HOST_MANIFEST}" --check

  step "2. Rendered fixtures are current"
  check_rendered_fixtures

  step "3. The agent plane is published"
  check_agent_plane_is_published "${PROJECT_A_OUTPUTS}"

  step "4. The audit plane is migrated"
  # Both projects, because the claims are measured over both and a cluster
  # carrying 18 migrations would fail them in a way that reads as a product
  # defect rather than as a missing deploy step.
  check_the_audit_plane_is_migrated "${PROJECT_A_OUTPUTS}"
  check_the_audit_plane_is_migrated "${PROJECT_B_OUTPUTS}"

  step "5. Host-local acceptance suite, over two projects"
  mkdir -p "${EVIDENCE_DIR}"
  # On EXIT, not after the last step: the evidence is written whether or not the
  # suite passed, and a failing gate is the run whose output an operator most
  # needs to read.
  trap restore_evidence_ownership EXIT
  export APG_LIVE_HOST=1
  export APG_EDGE_DEPLOYED=1
  export APG_PROJECT_A_OUTPUTS="${PROJECT_A_OUTPUTS}"
  export APG_PROJECT_B_OUTPUTS="${PROJECT_B_OUTPUTS}"
  [ -n "${SENTINEL_FILE}" ] && export APG_SECRET_SENTINEL_FILE="${SENTINEL_FILE}"
  [ -n "${ADMIN_PASSWORD_FILE}" ] && export APG_ADMIN_PASSWORD_FILE="${ADMIN_PASSWORD_FILE}"
  [ -n "${ROTATED_FROM_FILE}" ] && export APG_ROTATED_FROM_FILE="${ROTATED_FROM_FILE}"
  # One variable per credential. A window rotates one at a time, and a single
  # flag would admit all three proofs on the strength of whichever was actually
  # rotated.
  [ -n "${ROTATED_AUTHENTICATOR_FROM_FILE}" ] &&
    export APG_ROTATED_AUTHENTICATOR_FROM_FILE="${ROTATED_AUTHENTICATOR_FROM_FILE}"
  [ -n "${ROTATED_DOCS_FROM_FILE}" ] && export APG_ROTATED_DOCS_FROM_FILE="${ROTATED_DOCS_FROM_FILE}"
  [ -n "${ROTATED_JWT_FROM_FILE}" ] && export APG_ROTATED_JWT_FROM_FILE="${ROTATED_JWT_FROM_FILE}"
  [ "${AFTER_REBOOT}" -eq 1 ] && export APG_AFTER_REBOOT=1

  # `-m live_host` with NO PATH, and that is D211. The sweep everyone had been
  # using was `pytest tests/deployment -m live_host`, which selects by path --
  # so tests/security/ was a directory it never reached, and five green host
  # runs were five reports about a subset nobody had stated the boundary of.
  run_suite "live_host" "${EVIDENCE_DIR}/${EVIDENCE_PREFIX}-host-tests.xml"

  if ! evidence_is_supportable; then
    announce_no_evidence
    printf '\n\033[1msession-09-check: host PASSED\033[0m\n'
    return 0
  fi

  step "6. Static proofs of the claims this run records"
  run_claim_proofs host "${EVIDENCE_DIR}/${EVIDENCE_PREFIX}-host-claims.xml"

  step "7. Host evidence"
  write_evidence host

  printf '\n\033[1msession-09-check: host PASSED\033[0m\n'
  printf 'This is one half. Session 9 also needs --mode external; see --help.\n'
}

mode_external() {
  [ -n "${PUBLIC_IPV4}" ] || die 2 "--mode external requires --public-ipv4."
  [ -n "${PROJECT_A_OUTPUTS}" ] || die 2 "--mode external requires --project-a-outputs."
  [ -f "${PROJECT_A_OUTPUTS}" ] || die 2 "not found: ${PROJECT_A_OUTPUTS}"

  [ -n "${SSH_DESTINATION}" ] \
    || die 2 "--mode external requires --ssh-destination: the helper and the broker are reached over SSH."

  # Optional, and not exported: no external test reads project B. It is here
  # because the merge compares which deployment each half described.
  [ -z "${PROJECT_B_OUTPUTS}" ] || [ -f "${PROJECT_B_OUTPUTS}" ] \
    || die 2 "not found: ${PROJECT_B_OUTPUTS}"

  # Not enforceable from here -- the host could be behind the same NAT as the
  # operator -- so it is stated rather than checked, and the suite carries its
  # own positive control: 443 must answer, or every "closed" result below is a
  # statement about this network rather than about the host.
  printf 'session-09-check: this mode is only meaningful from a network that is\n'
  printf 'not the deployment host. A scan run on the host measures its own\n'
  printf 'routing table -- and the agent plane'"'"'s health routes answer 200 there,\n'
  printf 'which is exactly the difference this mode exists to observe.\n'

  step "1. The agent plane is published"
  check_agent_plane_is_published "${PROJECT_A_OUTPUTS}"

  step "2. Public-path and helper acceptance suite"
  mkdir -p "${EVIDENCE_DIR}"
  trap restore_evidence_ownership EXIT
  export APG_PUBLIC_IPV4="${PUBLIC_IPV4}"
  export APG_PROJECT_A_OUTPUTS="${PROJECT_A_OUTPUTS}"
  export APG_SSH_DESTINATION="${SSH_DESTINATION}"
  [ -n "${PUBLIC_IPV6}" ] && export APG_PUBLIC_IPV6="${PUBLIC_IPV6}"

  run_suite "external" "${EVIDENCE_DIR}/${EVIDENCE_PREFIX}-external-tests.xml"

  if ! evidence_is_supportable; then
    announce_no_evidence
    printf '\n\033[1msession-09-check: external PASSED\033[0m\n'
    return 0
  fi

  step "3. Static proofs of the claims this run records"
  run_claim_proofs external "${EVIDENCE_DIR}/${EVIDENCE_PREFIX}-external-claims.xml"

  step "4. External evidence"
  write_evidence external

  printf '\n\033[1msession-09-check: external PASSED\033[0m\n'
  printf 'This is one half. Session 9 also needs --mode host; see --help.\n'
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
