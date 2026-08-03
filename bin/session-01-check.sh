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

export APG_ACCEPTANCE_SESSION=1

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
shellcheck deploy.sh bin/*.sh
python -m ruff check src bin tests
python -m ruff format --check src bin tests
bin/lock-dev-deps.sh --check
bin/lock-versions.sh --check

# ---------------------------------------------------------------------------
step "3. Render both fixtures"
# ---------------------------------------------------------------------------
./deploy.sh \
  --project project.example.yaml \
  --capabilities capabilities.example.yaml \
  --render-only >/dev/null

./deploy.sh \
  --project project.second.example.yaml \
  --capabilities capabilities.example.yaml \
  --render-only >/dev/null

printf 'rendered fixture-alpha-dev and fixture-alpine-dev\n'

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
# Project keys are discovered from what step 3 actually rendered rather than
# written here. Hard-coding them would put fixture identities into deployable
# source, which §9 forbids and tests/contract/test_repository_contract.py
# enforces -- and it would silently stop checking anything if a fixture were
# renamed.
rendered_count=0
for project_dir in .generated/*/; do
  [ -f "${project_dir}compose.env" ] || continue
  bin/compose.sh "${project_dir%/}" --profile contract config >/dev/null
  running="$(bin/compose.sh "${project_dir%/}" ps --quiet)"
  if [ -n "${running}" ]; then
    printf 'containers are running for %s:\n%s\n' "${project_dir}" "${running}" >&2
    exit 1
  fi
  rendered_count=$((rendered_count + 1))
done

if [ "${rendered_count}" -lt 2 ]; then
  printf 'expected at least 2 rendered projects, found %d\n' "${rendered_count}" >&2
  exit 1
fi
printf '%d models render; no container is running\n' "${rendered_count}"

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
