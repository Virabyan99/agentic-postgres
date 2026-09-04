#!/usr/bin/env bash
#
# Two modes, split by argument and never run together (ADR 0158).
#
#   bin/doctor.sh                          workstation: tools, interpreter,
#                                          repository shape, locks. Unprivileged.
#   sudo bin/doctor.sh --project <key>      deployed: seven live checks against
#                                          one project on this host. Needs root.
#
# **The split is what keeps the bare `python` below correct.** Workstation mode
# checks the developer's OWN interpreter against `.python-version`, so it must
# resolve `python` from their PATH. Under `sudo`, `secure_path` makes an
# activated venv invisible and that check would report a false failure on every
# host — so `--project` runs the deployed checks ONLY, and never reaches it.
#
# This command reports tool presence, versions, paths and live health. It never
# prints the environment (runbook §2, §9 check 7) and never reads a secret.
#
# Exit codes: 0 (ready, warnings allowed), 2 (bad input), 3 (missing local
# prerequisite), 4 (the project was never deployed here), 6 (a check failed or
# could not be run).

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

FAILURES=0
VERBOSE=""

usage() {
  cat <<'USAGE'
Usage: bin/doctor.sh [--verbose] [--help]
       sudo bin/doctor.sh --project <project-key> [--verbose]

  (no arguments)     Workstation mode. Checks that this machine can run the
                     gate: required tools at usable versions, the pinned
                     interpreter, the repository's paths, the version lock.
                     Needs no root and no deployment. Exits 3 if anything is
                     missing.

  --project KEY      Deployed mode. Checks one project running on THIS host:
                     containers, the health route, TLS expiry, the cluster and
                     the pooler, migrations, the backup repository, the WAL
                     archiver, and disk headroom for a restore. Needs root,
                     because the deployed document is 0600 root.

  --verbose          Show the values behind each answer: resolved tool paths in
                     workstation mode, the numbers each verdict was computed
                     from in deployed mode.

  --json             Deployed mode only. The same checks as a JSON document --
                     project_key, observed_at, worst, exit_code, and every
                     check with its verdict, detail and evidence -- for the
                     fleet inventory to compose. Not combined with --verbose:
                     the document already carries the evidence.

Deployed mode reads the deployed document for identities only. Every verdict
comes from a live read: that document records what was true when it was
written, and a project whose archiver died yesterday still publishes the
status it had at its last deploy (ADR 0158).

Prints no environment variables and reads no secret material. --verbose adds
resolution, never a third party's bytes: no subprocess output, no environment,
no path under the secret root. Half-redacting a stderr would be worse than
omitting it, so it is omitted (ADR 0159).
USAGE
}

# Ubuntu ships no bare `python`, and sudo resets PATH to secure_path -- so
# deployed mode resolves an interpreter the way deploy.sh does rather than
# trusting the name. Workstation mode deliberately does NOT use this: checking
# the developer's own `python` is the whole point of check_python_minor.
python_bin() {
  if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
    printf '%s' "${ROOT_DIR}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    printf 'doctor: no Python interpreter found (looked for .venv/bin/python, python3).\n' >&2
    exit 3
  fi
}

deployed_mode() {
  local project_key="$1"
  local verbose="${2-}"
  local json="${3-}"
  [ -n "${project_key}" ] || { printf 'doctor: --project requires a project key.\n' >&2; exit 2; }
  if [ -n "${verbose}" ] && [ -n "${json}" ]; then
    printf 'doctor: --json and --verbose are two renderings of one report; choose one.\n' >&2
    exit 2
  fi
  [ "$(id -u)" -eq 0 ] || {
    printf 'doctor: --project needs root: the deployed document is 0600 root.\n' >&2
    exit 3
  }
  if [ -n "${json}" ]; then
    exec "$(python_bin)" "${ROOT_DIR}/bin/doctor.py" --project "${project_key}" --json
  fi
  if [ -n "${verbose}" ]; then
    exec "$(python_bin)" "${ROOT_DIR}/bin/doctor.py" --project "${project_key}" --verbose
  fi
  exec "$(python_bin)" "${ROOT_DIR}/bin/doctor.py" --project "${project_key}"
}

ok()   { printf '  ok    %s\n' "$*"; }
bad()  { printf '  MISS  %s\n' "$*" >&2; FAILURES=$((FAILURES + 1)); }

check_command() {
  local binary="$1" purpose="$2" resolved
  if resolved="$(command -v "${binary}" 2>/dev/null)"; then
    ok "${binary} — ${purpose}"
    # Verbose adds WHERE the tool resolved from, which is the answer to the
    # question a failing gate actually raises: two `docker` on one PATH, or a
    # Windows shim ahead of the Linux one. It adds no environment: the value
    # comes from `command -v`, not from printing what is set.
    #
    # **An `if`, never `[ -n "${VERBOSE}" ] && printf`** (D654). That form was
    # the last statement in this branch, so under `set -e` the function returned
    # 1 whenever VERBOSE was empty -- and the whole script died after its first
    # line. `bin/doctor.sh` with no arguments, which is the README's "confirm the
    # workstation is ready" step, exited **1 after four lines** for an entire
    # run. `--verbose` was fine, because there the test succeeds.
    if [ -n "${VERBOSE}" ]; then
      printf '          path = %s\n' "${resolved}"
    fi
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
  local project="" verbose="" json=""

  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help) usage; return 0 ;;
      --verbose) verbose=1; VERBOSE=1; shift ;;
      --json) json=1; shift ;;
      --project)
        [ "$#" -ge 2 ] || { printf 'doctor: --project requires a project key.\n' >&2; exit 2; }
        project="$2"; shift 2 ;;
      --project=*) project="${1#--project=}"; shift ;;
      *) usage >&2; printf 'doctor: unknown argument: %s\n' "$1" >&2; exit 3 ;;
    esac
  done

  # Dispatched before any workstation check runs, and that ordering is the
  # contract: the two modes never execute together, which is what keeps
  # check_python_minor's deliberate bare `python` off the sudo path (ADR 0158).
  if [ -n "${project}" ]; then
    deployed_mode "${project}" "${verbose}" "${json}"
  fi
  if [ -n "${json}" ]; then
    printf 'doctor: --json is a deployed-mode rendering; it needs --project.\n' >&2
    exit 2
  fi

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
