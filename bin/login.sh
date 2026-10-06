#!/usr/bin/env bash
#
# Log in to the management API (D2066): a person's password session, a
# management key, an invitation accepted, or a second factor enrolled.
#
# The state is ${XDG_CONFIG_HOME:-$HOME/.config}/apg/, a 0700 directory of 0600
# files; the access token is never written. A secret enters only through a 0600
# file whose mode is checked, or a prompt -- never an argument or the
# environment -- and leaves only through --output FILE or a terminal.
#
# Exit codes (runbook section 2 convention):
#   0  logged in, accepted, enrolled or confirmed
#   2  invalid input, an --output that exists, or a session already held
#   3  no context, no credential, an unusable local file, or not https
#   5  refused by the server (its error word is printed)
#   6  the server could not be reached or answered something unreadable

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  bin/login.sh password --endpoint URL --username NAME [--password-file FILE] [--totp-code-stdin]
  bin/login.sh key --endpoint URL --key-file FILE
  bin/login.sh accept --endpoint URL --invitation-file FILE --username NAME [--display-name TEXT] [--password-file FILE]
  bin/login.sh accept --invitation-file FILE
  bin/login.sh totp-enroll [--output FILE]
  bin/login.sh totp-confirm [--totp-code-stdin]

  password      Open a person's session. The password comes from a 0600 file
                or a prompt. With a second factor enabled, the code comes from
                stdin (--totp-code-stdin) or a prompt.
  key           Use a management key (apg_...) kept in a 0600 file. The
                context records the file's PATH, never the key.
  accept        With --username: create the account an invitation offers, then
                log in as it. Without: join the organisation an invitation
                names, as the person already logged in.
  totp-enroll   Begin a second factor. The otpauth:// URI and seed go to
                --output FILE (written once, 0600) or to a terminal -- never to
                a pipe.
  totp-confirm  Enable it with a current code. Every session ends, this one
                included; log in again with a code.

URL is the control project's routes.control, e.g.
https://control.agenticpostgresql.com/api/v1 (https only; http only for
127.0.0.1 and localhost). A login refuses while a session is held: end it with
bin/logout.sh first.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'login: %s\n' "$*" >&2
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
    die 2 "a verb is required: password, key, accept, totp-enroll or totp-confirm."
  fi
  # --help anywhere is a read: no state, no server.
  local argument
  for argument in "$@"; do
    case "${argument}" in
      --help | -h)
        usage
        return 0
        ;;
    esac
  done
  case "$1" in
    password | key | accept | totp-enroll | totp-confirm) ;;
    *) die 2 "unknown verb: $1. One of: password key accept totp-enroll totp-confirm" ;;
  esac
  exec "$(python_bin)" "${ROOT_DIR}/bin/cloud.py" login "$@"
}

main "$@"
