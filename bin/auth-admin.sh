#!/usr/bin/env bash
#
# The first administrator, and the state of every subject after it.
#
# Two operations, and one of them cannot be undone.
#
#   bootstrap  Create the first administrator. One-time, local, at a terminal.
#              The password is read from the TTY or from a file descriptor the
#              caller opened -- there is deliberately no `--password`, because an
#              argument is visible in `ps`, in `/proc/<pid>/cmdline`, in the
#              shell's history file and in any audit rule watching execve.
#   list       Show every subject and its state. This is the documented recovery
#              when a bootstrap's output is lost, and it is the ONLY one: a
#              second bootstrap is refused, and re-running it with a new password
#              until something works is how a project ends up with an
#              administrator nobody meant to create.
#
# Why this is a command and not an endpoint. Whoever the first administrator is
# decides who every later one is, so a public bootstrap route means the first
# caller to reach a freshly deployed project becomes its administrator. §4 lists
# this among the four operations a re-run cannot undo. `routes.app.status` stays
# `unavailable` until an administrator exists (D230), which is how the deployment
# expresses "not yet public" in the vocabulary it already has rather than by
# inventing a fifth deployment state.
#
# Why root, and why a TTY. The connection is `docker exec` into the project's
# own PostgreSQL container -- no TCP, no pooler, no network path. That is the
# standing rule for anything privileged that MUTATES, and here it is also load
# bearing: the bootstrap takes a project-scoped transaction advisory lock, and a
# session lock taken through a transaction-mode pooler is stranded on whichever
# backend happened to run the statement (measured, Run 8).
#
# Exit codes (runbook §2 convention):
#   0  the administrator was created, or state was listed
#   2  invalid operator input
#   3  missing local prerequisite, or not root
#   5  the deployment or the database refused the operation

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  bin/auth-admin.sh --outputs <outputs.json> bootstrap \
      --username <name> --display-name <name> [--password-fd <n>]
  bin/auth-admin.sh --outputs <outputs.json> list
  bin/auth-admin.sh --help

The password is never an argument. With no --password-fd it is read from the
terminal, twice, and the two entries must match -- this value cannot be
recovered and cannot be re-bootstrapped, so a typo costs a redeployment.

If the output of a bootstrap is lost, run `list` and look. Do not bootstrap
again: the second attempt is refused (AP409), and it is refused on purpose.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'auth-admin: %s\n' "$*" >&2
  exit "$code"
}

# `python3`, never a bare `python`. Ubuntu ships no `python`, and D184 is the
# record of a `#!/usr/bin/env python` shebang that worked until something ran
# the file directly instead of through its wrapper.
python_bin() {
  if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
    printf '%s\n' "${ROOT_DIR}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    die 3 "no Python interpreter found (looked for .venv/bin/python, python3)."
  fi
}

main() {
  if [ "$#" -eq 0 ]; then
    usage >&2
    die 2 "no arguments."
  fi
  case "$1" in
    --help | -h)
      usage
      return 0
      ;;
  esac

  command -v docker >/dev/null 2>&1 || die 3 "docker is not installed."

  # Arguments are forwarded verbatim, and the interpreter is resolved here
  # rather than by a shebang. Nothing in this wrapper reads or writes the
  # password: it is read by the Python process, from the terminal this shell is
  # attached to, or from a descriptor the caller opened and this shell passes
  # through untouched.
  exec "$(python_bin)" "${ROOT_DIR}/bin/auth-admin.py" "$@"
}

main "$@"
