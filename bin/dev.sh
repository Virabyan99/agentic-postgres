#!/usr/bin/env bash
#
# A disposable local cluster with this release's schema on it (ADR 0203).
#
#   up        Stand a cluster up on the locked PostgreSQL image, apply the
#             product's own bootstrap statements and every rendered migration
#             as the migration user, record both ledgers, activate two roles
#             and register one development subject.
#   status    Report whether the environment is running, stopped, absent, or
#             could not be asked -- four answers, not three.
#   down      Remove the container, its anonymous volume and the state
#             directory. Idempotent, and says which of the two it did.
#   reset     `down` then `up`, the same two functions and no third path.
#
# The environment is the DATABASE. There is no PostgREST here, no auth service
# and no token: a token alone reads no owner's rows, so a REST loop would be
# three containers plus the production key flow -- the production stack minus
# Traefik, as a second Compose model nobody audits (D1157, ADR 0013, ADR 0065).
# Reach it with `apg dev psql`, seed it with `apg dev seed`, or point any
# client at the loopback port `up` prints.
#
# **No root.** `docker` runs as you, the state lives in your checkout under
# `.generated/.dev/`, and nothing here reads /var/lib or /etc.
#
# **No production secret.** The two role passwords are generated per
# environment, live in 0600 files, and belong to a container `down` destroys.
# No repository key, cipher pass, provider token or deployed document from a
# host is ever read.
#
# Exit codes (runbook §2 convention):
#   0  success
#   2  invalid operator input, or an environment that is already up
#   3  a missing local prerequisite, or state this user cannot read
#   4  the project has not been rendered, or has no environment
#   5  a migration, a statement or a seed that did not apply
#   9  the daemon or the cluster could not be reached

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: bin/dev.sh up|status|down|reset --project FILE [--capabilities FILE]

  up                 Build the environment: the locked image, the bootstrap
                     statements, every rendered migration as the migration
                     user, both ledgers, two activated roles and one
                     development subject. Refuses a project this checkout has
                     not rendered, naming the command that renders it.
  status             running | stopped | absent | unknown, with the reason.
  down               Remove the container, its anonymous volume and the state.
                     Exits 0 when there was nothing to remove, and says so.
  reset              down, then up.
  --project FILE     The project manifest. Its derived key names the
                     environment, the container and the state directory.
  --capabilities FILE  Only used to spell out the --render-only command when a
                     project has not been rendered. Default
                     capabilities.example.yaml.
  --help             Show this message.

The environment is a database and nothing else. `apg dev psql` opens a session
as the application role with the development subject asserted; `apg dev seed`
applies a reviewed seed from projects/<slug>/seeds/.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'dev: %s\n' "$*" >&2
  exit "$code"
}

# Ubuntu ships no bare `python`, and sudo resets PATH to secure_path, so a venv
# the operator activated is invisible to a privileged call (D80). This command
# never runs under sudo, but it resolves the interpreter the same way every
# other command here does -- one rule, not a per-command judgement.
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

main() {
  if [ "$#" -eq 0 ]; then
    usage >&2
    die 2 "a verb is required: up, status, down or reset."
  fi

  local command=""
  local -a arguments=()
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help|-h)
        usage
        exit 0
        ;;
      up|status|down|reset)
        [ -z "${command}" ] || die 2 "only one verb at a time."
        command="$1"
        shift
        ;;
      --project|--capabilities)
        [ "$#" -ge 2 ] || die 2 "$1 requires a value."
        if [ "$1" = "--project" ]; then
          [ -f "$2" ] || die 2 "project manifest not found: $2"
        fi
        arguments+=("$1" "$2")
        shift 2
        ;;
      *)
        usage >&2
        die 2 "unknown argument: $1"
        ;;
    esac
  done

  [ -n "${command}" ] || die 2 "a verb is required: up, status, down or reset."

  exec "$(python_bin)" "${ROOT_DIR}/bin/dev.py" "${command}" "${arguments[@]+"${arguments[@]}"}"
}

main "$@"
