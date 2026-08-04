#!/usr/bin/env bash
#
# The Session 1 gate. CI runs this exact script; there is no second, divergent
# definition of "passing".
#
# It never calls `docker compose up`, `run`, or `start`. Session 1 renders
# configuration and starts nothing.
#
# Exit codes: 0 on success; the first failing step's status otherwise.

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR
cd "$ROOT_DIR"

# Derived from the package, never written here as a literal (ADR 0014). A
# hard-coded value made the registry policy and the tree's own CURRENT_SESSION
# disagree the moment Session 2 activated its requirements, and no ordering of
# two commits kept both green. tests/contract/test_gate_contract.py asserts that
# no session number is written into this file.
APG_ACCEPTANCE_SESSION="$(
  PYTHONPATH="${ROOT_DIR}/src" python -c \
    'from agentic_postgres import CURRENT_SESSION; print(CURRENT_SESSION)'
)"
export APG_ACCEPTANCE_SESSION
readonly APG_ACCEPTANCE_SESSION

ALLOW_DIRTY=0

usage() {
  cat <<'USAGE'
Usage: bin/session-01-check.sh [--allow-dirty] [--help]

Runs every Session 1 exit criterion in order and writes session evidence.

  --allow-dirty  Skip the clean-tree requirement. For iterative local use only.
                 NOT accepted for session completion or in CI: evidence must
                 describe a committed state, so a dirty run writes none.
USAGE
}

step() {
  printf '\n\033[1m==> %s\033[0m\n' "$*"
}

case "${1-}" in
  --help) usage; exit 0 ;;
  --allow-dirty) ALLOW_DIRTY=1 ;;
  "") ;;
  *) usage >&2; printf 'session-01-check: unknown argument: %s\n' "$1" >&2; exit 2 ;;
esac

# ---------------------------------------------------------------------------
step "1. Clean tracked source tree"
# ---------------------------------------------------------------------------
# Ignored .generated/ and evidence/ artifacts are excluded by --exclude-standard,
# so the renders and evidence this gate produces do not make it fail.
if [ "${ALLOW_DIRTY}" -eq 1 ]; then
  printf 'skipped (--allow-dirty); evidence will not be written\n'
else
  git diff --quiet || { printf 'unstaged changes present\n' >&2; exit 1; }
  git diff --cached --quiet || { printf 'staged changes present\n' >&2; exit 1; }
  if [ -n "$(git ls-files --others --exclude-standard)" ]; then
    printf 'untracked files present:\n%s\n' "$(git ls-files --others --exclude-standard)" >&2
    exit 1
  fi
  printf 'clean\n'
fi

# ---------------------------------------------------------------------------
step "2. Static quality and lock checks"
# ---------------------------------------------------------------------------
# libexec/* is named explicitly: those launchers are extensionless, so the
# bin/*.sh glob misses them, and they are the scripts systemd runs as root.
shellcheck deploy.sh bin/*.sh libexec/*
python -m ruff check src bin tests
python -m ruff format --check src bin tests
bin/lock-dev-deps.sh --check
bin/lock-versions.sh --check

# ---------------------------------------------------------------------------
step "3. Render both fixtures"
# ---------------------------------------------------------------------------
# The directories published here are recorded, and step 7 checks exactly these
# (ADR 0014). Rediscovering them by globbing .generated/ would sweep in any
# Session 2 project deployed on this machine, whose containers are running by
# design -- so the Session 1 gate would fail on a Session 2 success.
#
# The list is data this run produced, never a literal: hard-coding a fixture
# name would put a fixture identity into deployable source, which §9 forbids and
# tests/contract/test_repository_contract.py enforces, and it would silently
# stop checking anything if a fixture were renamed.
FIXTURES=(project.example.yaml project.second.example.yaml)

for fixture in "${FIXTURES[@]}"; do
  ./deploy.sh \
    --project "${fixture}" \
    --capabilities capabilities.example.yaml \
    --render-only >/dev/null
done

# Each directory is identified by the manifest digest its own outputs.json
# records, not by re-deriving a name here. outputs.inputs.project_sha256 is
# already contract (CFG-005), so this asks "which directory did this manifest
# produce" using the answer the renderer itself published.
mapfile -t RENDERED_DIRS < <(
  PYTHONPATH="${ROOT_DIR}/src" python - "${FIXTURES[@]}" <<'PYTHON'
import hashlib
import json
import sys
from pathlib import Path

manifests = sys.argv[1:]
by_digest = {hashlib.sha256(Path(m).read_bytes()).hexdigest(): m for m in manifests}

found: dict[str, str] = {}
for outputs in sorted(Path(".generated").glob("*/outputs.json")):
    document = json.loads(outputs.read_text(encoding="utf-8"))
    manifest = by_digest.get(document["inputs"]["project_sha256"])
    if manifest is not None and (outputs.parent / "compose.env").is_file():
        found[manifest] = str(outputs.parent)

missing = [m for m in manifests if m not in found]
if missing:
    sys.exit(f"no rendered directory records the digest of: {missing}")

for manifest in manifests:
    print(found[manifest])
PYTHON
)

[ "${#RENDERED_DIRS[@]}" -eq "${#FIXTURES[@]}" ] || {
  printf 'expected %d rendered directories, resolved %d\n' \
    "${#FIXTURES[@]}" "${#RENDERED_DIRS[@]}" >&2
  exit 1
}

printf 'rendered:%s\n' "$(printf ' %s' "${RENDERED_DIRS[@]##*/}")"

# ---------------------------------------------------------------------------
step "4. Active contract tests, with machine-readable output"
# ---------------------------------------------------------------------------
mkdir -p .generated/session-01
python -m pytest -q -m "contract and not future" \
  --junitxml=.generated/session-01/contract-tests.xml

# ---------------------------------------------------------------------------
step "5. Full P0 inventory and registry policy"
# ---------------------------------------------------------------------------
python -m pytest --collect-only -q -m p0 \
  > .generated/session-01/p0-collection.txt
python -m pytest -q tests/contract/test_acceptance_registry.py
python -m pytest -q tests/contract/test_future_marker_policy.py

# ---------------------------------------------------------------------------
step "6. Generated documentation is current"
# ---------------------------------------------------------------------------
# --check only. This gate demanded a clean tree in step 1, so a generator that
# self-healed here would dirty the tree it just required be clean.
python bin/render-acceptance-matrix.py --check
python bin/render-config.py --bounds-doc --check

# ---------------------------------------------------------------------------
step "7. Compose validates and no project container is running"
# ---------------------------------------------------------------------------
# Exactly the directories step 3 published, never a glob over .generated/
# (ADR 0014). A glob would sweep in any Session 2 project deployed on this
# machine, whose containers run by design, and the Session 1 gate would fail on
# a Session 2 success. The claim this step makes is precise: the fixtures this
# gate rendered have no container running. Any broader claim about the host
# belongs to bin/session-02-check.sh, which enumerates the deployment.
#
# The identities still come from what step 3 produced rather than from a literal
# here, so no fixture name enters deployable source (§9).
#
# `ps` needs the Docker daemon; `config` does not. On the deployment host the
# operator account cannot reach the daemon -- it is deliberately not in the
# docker group, which is root-equivalent -- so `ps` there is a question this
# account is not permitted to ask, and its refusal is not evidence that a
# container is running. ADR 0018: say which of the two happened.
#
# The models are still validated either way, and the running-container claim is
# proved on the host by bin/session-02-check.sh --mode host, as root.
daemon_reachable=1
for project_dir in "${RENDERED_DIRS[@]}"; do
  bin/compose.sh "${project_dir}" --profile contract config >/dev/null

  if running="$(bin/compose.sh "${project_dir}" ps --quiet 2>/dev/null)"; then
    if [ -n "${running}" ]; then
      printf 'containers are running for %s:\n%s\n' "${project_dir}" "${running}" >&2
      exit 1
    fi
  else
    daemon_reachable=0
  fi
done

if [ "${#RENDERED_DIRS[@]}" -lt 2 ]; then
  printf 'expected at least 2 rendered projects, found %d\n' "${#RENDERED_DIRS[@]}" >&2
  exit 1
fi

if [ "${daemon_reachable}" -eq 1 ]; then
  printf '%d models render; no container is running\n' "${#RENDERED_DIRS[@]}"
else
  printf '%d models render; the Docker daemon is unreachable from this account, so\n' \
    "${#RENDERED_DIRS[@]}"
  printf 'whether a container is running was not determined here (ADR 0018).\n'
  printf 'It is proved by: sudo bin/session-02-check.sh --mode host\n'
fi

# ---------------------------------------------------------------------------
step "8. Session evidence"
# ---------------------------------------------------------------------------
if [ "${ALLOW_DIRTY}" -eq 1 ]; then
  printf 'skipped (--allow-dirty): evidence must describe a committed state\n'
  printf '\nsession-01-check: checks passed, but this was not a completion run.\n'
  exit 0
fi

python bin/write-session-evidence.py --session 1

printf '\n\033[1msession-01-check: PASSED\033[0m\n'
printf 'Session 1 deployed no infrastructure service and started no container.\n'
