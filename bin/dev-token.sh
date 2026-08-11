#!/usr/bin/env bash
#
# Mint a short-lived bootstrap token and hand it to a command. Never print one.
#
# There is no flag that emits a token, and that is D105's rule rather than an
# oversight: a flag that prints a credential is a credential in a scrollback
# buffer, a shell history, a screen share and a support ticket. This command
# signs a token, puts it in a child's environment through execve, and becomes
# that child.
#
#   sudo bin/dev-token.sh --project-outputs FILE --role docs -- \
#        bin/api-contract.sh --update --project-outputs FILE > candidate.json
#
# Nothing about the token is chosen by the caller. The role is one of three
# enumerated names resolved through the deployed document, the subject is
# derived from the project rather than supplied, and the lifetime is bounded --
# because a caller who can name a role, a subject and a lifetime can mint any
# credential this issuer is able to sign.
#
# Exit codes (runbook §2 convention):
#   *  the child's own exit code, once it has been exec'd
#   2  invalid operator input
#   3  missing local prerequisite, or not root
#   5  the deployed document or the signing key is unusable

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage: sudo bin/dev-token.sh --project-outputs FILE --role ROLE \
            [--ttl-seconds N] -- COMMAND [ARGS...]

  --project-outputs FILE
                     The project's deployed outputs document. The roles, the
                     issuer, the audience, the active key id and the secret
                     generation all come from it -- a deployed document records
                     what happened, where a manifest records what was asked for.
  --role ROLE        One of: anon, authenticated, docs. An enumeration, not a
                     pass-through: a tool that will ask for any role is a tool
                     that probes for the boundary rather than staying inside it.
  --ttl-seconds N    Token lifetime, 1..900. Default 300.
  --                 Everything after this is the command to run.
  --help             Show this message.

The minted token reaches the command through its environment and through
nothing else -- not an argument, not a file, not standard output. There is no
option that prints it, and adding one would be a change to the security posture
rather than a convenience.

The `docs` role is minted without a subject on purpose. Migration 0009's
pre-request hook refuses a documentation token that carries one, so minting a
subject would produce a credential rejected by design.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'dev-token: %s\n' "$*" >&2
  exit "$code"
}

# sudo resets PATH to secure_path and Ubuntu ships no bare `python`, so a venv
# the operator activated is invisible to this privileged command (D80).
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
    die 2 "--project-outputs, --role and a command are required."
  fi

  local outputs="" role="" ttl="" saw_separator=0
  local -a forwarded=()
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help|-h)
        usage
        exit 0
        ;;
      --project-outputs)
        [ "$#" -ge 2 ] || die 2 "--project-outputs requires a file."
        outputs="$2"
        shift 2
        ;;
      --role)
        [ "$#" -ge 2 ] || die 2 "--role requires one of: anon, authenticated, docs."
        role="$2"
        shift 2
        ;;
      --ttl-seconds)
        [ "$#" -ge 2 ] || die 2 "--ttl-seconds requires a number."
        ttl="$2"
        shift 2
        ;;
      --)
        saw_separator=1
        shift
        forwarded=("$@")
        break
        ;;
      *)
        usage >&2
        die 2 "unknown argument: $1"
        ;;
    esac
  done

  [ -n "${outputs}" ] || die 2 "--project-outputs is required."
  [ -n "${role}" ] || die 2 "--role is required."

  # The enumeration is checked here as well as in the Python, and deliberately
  # before the root check below: an operator who mistyped a role should not have
  # to find sudo to be told so. The Python keeps its own copy because it is the
  # half that resolves the name against the deployed document.
  case "${role}" in
    anon|authenticated|docs) ;;
    *) die 2 "unknown role: ${role}. One of: anon, authenticated, docs." ;;
  esac

  [ -f "${outputs}" ] || die 2 "deployed document not found: ${outputs}"
  [ "${saw_separator}" -eq 1 ] || die 2 "a command is required after --."
  [ "${#forwarded[@]}" -gt 0 ] || die 2 "a command is required after --."

  # Checked here as well as in the Python, so an operator who forgot `sudo`
  # gets the reason rather than a permission error naming a path.
  if [ "$(id -u)" -ne 0 ]; then
    die 3 "must run as root: the bootstrap signing key is 0400 owned by root."
  fi

  local -a arguments=(--project-outputs "${outputs}" --role "${role}")
  if [ -n "${ttl}" ]; then
    arguments+=(--ttl-seconds "${ttl}")
  fi

  exec "$(python_bin)" "${ROOT_DIR}/bin/dev-token.py" "${arguments[@]}" -- "${forwarded[@]}"
}

main "$@"
