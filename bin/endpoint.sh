#!/usr/bin/env bash
#
# A project's public database doors (ADR 0268, ADR 0269): what they are, a
# credential for each, and a psql through one. The doors are TLS on port 5432,
# chosen by name: pool.<domain> (transaction mode, the application role) and
# direct.<domain> (a session, the administrator role).
#
# The password is made HERE and never leaves this machine: `credential`
# generates it, writes it once to --password-file (0600, never over an existing
# file, written before anything is sent) and sends only its SCRAM-SHA-256
# verifier. `connect` hands it to a local psql through a private, temporary
# PGPASSFILE that is removed when psql ends -- never an argument or the
# environment. Nothing prints it.
#
# Exit codes (runbook section 2 convention):
#   0  done (connect: psql's own exit status)
#   2  invalid input, or a --password-file that already exists (credential)
#   3  no context, no project chosen, no credential, an unusable file, no psql
#   5  refused by the server (its error word is printed), or the operation failed
#   6  the server could not be reached, answered something unreadable, or an
#      outcome could not be determined
#   7  credential --wait stopped at its own --timeout (the operation continues)

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  bin/endpoint.sh show [--project-key KEY] [--json]
  bin/endpoint.sh credential [--project-key KEY] --role app|admin --password-file FILE [--wait] [--timeout S] [--interval S] [--json]
  bin/endpoint.sh connect [--project-key KEY] --role app|admin --password-file FILE [-- PSQL-ARGS...]

  show        The project's two doors -- host, port, user, database -- and a
              connection snippet per client measured through them (psql,
              Prisma, node-postgres, psycopg). Every snippet's password is a
              placeholder: the password is your file.
  credential  A new password for one role: app (the pooled door) or admin
              (the direct door). Generated here, written to FILE (0600, never
              over an existing file) and never sent: only its verifier is.
              The previous password stops working when the operation
              succeeds; --wait waits for that.
  connect     psql through one door, verify-full against this machine's
              certificate authorities, the password from FILE through a
              temporary 0600 PGPASSFILE removed when psql ends. Arguments
              after -- go to psql.

KEY is a project key such as slot1-prod; without it, the context's project
(bin/project.sh use). credential needs a person's session; show and connect
also accept a key holding projects:read.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'endpoint: %s\n' "$*" >&2
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
    die 2 "a verb is required: show, credential or connect."
  fi
  # --help before any `--` is a read: no context, no server. After `--` it is
  # psql's to answer.
  local argument
  for argument in "$@"; do
    case "${argument}" in
      --) break ;;
      --help | -h)
        usage
        return 0
        ;;
    esac
  done
  case "$1" in
    show | credential | connect) ;;
    *) die 2 "unknown verb: $1. One of: show credential connect" ;;
  esac
  exec "$(python_bin)" "${ROOT_DIR}/bin/cloud.py" endpoint "$@"
}

main "$@"
