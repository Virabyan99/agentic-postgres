#!/usr/bin/env bash
#
# Session 1 readiness check: repository shape and local tooling.
#
# This command deliberately reports only tool presence, versions, and paths.
# It never prints the environment (runbook §2, §9 check 7) and never reads a
# secret. Runbook §8.6 OPS-001 later extends it to a deployed system.
#
# Exit codes: 0 (ready), 3 (missing local prerequisite).

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

FAILURES=0

usage() {
  cat <<'USAGE'
Usage: bin/doctor.sh [--help]

Checks that this workstation can run the Session 1 gate: required tools are
present at usable versions, and the repository has the paths the contract
expects. Exits 3 if any prerequisite is missing.

Prints no environment variables and reads no secret material.
USAGE
}

ok()   { printf '  ok    %s\n' "$*"; }
bad()  { printf '  MISS  %s\n' "$*" >&2; FAILURES=$((FAILURES + 1)); }

check_command() {
  local binary="$1" purpose="$2"
  if command -v "${binary}" >/dev/null 2>&1; then
    ok "${binary} — ${purpose}"
  else
    bad "${binary} — ${purpose}"
  fi
}

check_path() {
  local relative="$1"
  if [ -e "${ROOT_DIR}/${relative}" ]; then
    ok "${relative}"
  else
    bad "${relative}"
  fi
}

check_python_minor() {
  local expected actual resolved
  if [ ! -f "${ROOT_DIR}/.python-version" ]; then
    bad ".python-version is missing"
    return
  fi
  expected="$(cut -d. -f1,2 < "${ROOT_DIR}/.python-version" | tr -d '[:space:]')"

  if ! resolved="$(command -v python 2>/dev/null)"; then
    bad "python — pinned interpreter ${expected} not on PATH (activate .venv)"
    return
  fi

  # WSL inherits the Windows PATH, so a bare `python` can resolve to a Windows
  # shim (pyenv-win, the Store alias) living under /mnt/. Those are CRLF shell
  # scripts or reparse stubs: executing one fails with "bad interpreter" and
  # would take this script down with it under `set -e`. Reject explicitly —
  # the message is the useful part.
  case "${resolved}" in
    /mnt/*)
      bad "python resolves to a Windows interpreter (${resolved}); activate .venv"
      return
      ;;
  esac

  if ! actual="$(python -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)"; then
    bad "python at ${resolved} is not runnable"
    return
  fi

  if [ "${actual}" = "${expected}" ]; then
    ok "python ${actual} — matches .python-version"
  else
    bad "python ${actual} — .python-version pins ${expected}"
  fi
}

main() {
  case "${1-}" in
    --help) usage; return 0 ;;
    "") ;;
    *) usage >&2; printf 'doctor: unknown argument: %s\n' "$1" >&2; exit 3 ;;
  esac

  printf 'Repository: %s\n\n' "${ROOT_DIR}"

  printf 'Local tools\n'
  check_command git       "source control and the clean-tree gate"
  check_command shellcheck "shell linting in the gate"
  check_command jq        "generated-output inspection"
  check_command docker    "compose model validation"
  check_python_minor

  if command -v docker >/dev/null 2>&1; then
    if docker compose version >/dev/null 2>&1; then
      ok "docker compose — $(docker compose version --short 2>/dev/null || echo present)"
    else
      bad "docker compose v2+ plugin"
    fi
    if docker buildx version >/dev/null 2>&1; then
      ok "docker buildx — image digest resolution"
    else
      bad "docker buildx — required by bin/lock-versions.sh --update"
    fi
  fi

  printf '\nRepository shape\n'
  check_path "deploy.sh"
  check_path "bin"
  check_path "src/agentic_postgres"
  check_path "docs/decisions"
  check_path ".generated/.gitkeep"
  check_path "evidence/.gitkeep"
  check_path "migrations/.gitkeep"
  check_path "requirements-dev.in"
  check_path "pytest.ini"
  check_path "compose.yaml"
  check_path "versions.in.yaml"
  check_path "versions.env"
  check_path "schemas/project.schema.json"
  check_path "schemas/outputs.schema.json"

  printf '\nLocks\n'
  if [ -x "${ROOT_DIR}/bin/lock-versions.sh" ] \
    && "${ROOT_DIR}/bin/lock-versions.sh" --check >/dev/null 2>&1; then
    ok "version lock is current"
  else
    bad "version lock is stale or invalid — run bin/lock-versions.sh --check"
  fi

  printf '\n'
  if [ "${FAILURES}" -ne 0 ]; then
    printf 'doctor: %d prerequisite(s) missing.\n' "${FAILURES}" >&2
    exit 3
  fi

  printf 'doctor: Session 1 prerequisites satisfied.\n'
}

main "$@"
