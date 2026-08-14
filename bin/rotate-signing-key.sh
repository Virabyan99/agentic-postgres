#!/usr/bin/env bash
#
# The signing-key cutover (ADR 0088).
#
# Four steps and a status, and none of them touches the provider. A rotation is
# PREPARED by putting the new key at APG_AUTH_JWT_PREPARED_KEY by hand and
# redeploying -- D249's rule, unchanged: no command here sets a value at the
# provider. What this owns is the decisions:
#
#   status       what is published, what signs, who has acknowledged
#   acknowledge  read the key set out of each verifier's RUNNING container and
#                record its digest
#   promote      switch signing -- refused unless every verifier has
#                acknowledged the published set
#   retire       drop the retiring key -- refused before the deadline
#   abandon      withdraw a prepared rotation that has not been promoted
#
# Root, because the deployed document and the secret generations are root-owned
# and reading a verifier's key set means reaching its container. A human at a
# TTY, because promote is irreversible.
#
# Exit codes (runbook §2 convention):
#   0  the step completed
#   2  invalid operator input
#   3  missing local prerequisite, or not root
#   5  the deployed state is unusable
#   6  the step was refused by a rule

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  sudo bin/rotate-signing-key.sh --outputs <outputs.json> status
  sudo bin/rotate-signing-key.sh --outputs <outputs.json> acknowledge
  sudo bin/rotate-signing-key.sh --outputs <outputs.json> promote
  sudo bin/rotate-signing-key.sh --outputs <outputs.json> retire
  sudo bin/rotate-signing-key.sh --outputs <outputs.json> abandon

The whole cutover, in order:

  1. Put the new key at APG_AUTH_JWT_PREPARED_KEY at the provider. By hand:
     no command here writes a provider value (D249).
  2. Redeploy. `render-jwks.py` publishes the prepared key's PUBLIC half beside
     the active one; nothing signs with it.
  3. Bring the project down and up so every verifier is RECREATED. A restart is
     not enough: a running PostgREST never re-reads its key set, and after the
     key set file has been replaced a restart is measured to leave the container
     unable to start at all.
  4. `acknowledge`. Records what each verifier actually holds.
  5. `promote`. Refused unless step 4 came back clean.
  6. Move the promoted key to APG_AUTH_JWT_SIGNING_KEY at the provider, clear
     APG_AUTH_JWT_PREPARED_KEY, and redeploy.
  7. After the deadline `status` prints: `retire`, then redeploy and recreate.

`abandon` undoes a prepared rotation, and only a prepared one. After promotion
there is no way back -- the recovery is to complete forward.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'rotate-signing-key: %s\n' "$*" >&2
  exit "$code"
}

# Ubuntu ships no bare `python`, and sudo resets PATH to secure_path (D80).
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
    die 2 "a step is required."
  fi

  local outputs=""
  local step=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help|-h)
        usage
        exit 0
        ;;
      --outputs)
        [ "$#" -ge 2 ] || die 2 "--outputs requires a file."
        outputs="$2"
        shift 2
        ;;
      status|acknowledge|promote|retire|abandon)
        [ -z "${step}" ] || die 2 "only one step at a time."
        step="$1"
        shift
        ;;
      *)
        usage >&2
        die 2 "unknown argument: $1"
        ;;
    esac
  done

  [ -n "${step}" ] || die 2 "a step is required."
  [ -n "${outputs}" ] || die 2 "--outputs is required."
  [ -f "${outputs}" ] || die 2 "deployed document not found: ${outputs}"

  # Promotion is the irreversible one, so it is confirmed by a human who has
  # just been shown the state. `status` first, deliberately: an operator
  # approving a promotion should be reading what they are promoting.
  if [ "${step}" = "promote" ]; then
    "$(python_bin)" "${ROOT_DIR}/bin/rotate-signing-key.py" --outputs "${outputs}" status || true
    printf '\nPromotion is irreversible. Type PROMOTE to continue: '
    local answer=""
    read -r answer || true
    [ "${answer}" = "PROMOTE" ] || die 2 "not confirmed; nothing was changed."
  fi

  exec "$(python_bin)" "${ROOT_DIR}/bin/rotate-signing-key.py" --outputs "${outputs}" "${step}"
}

main "$@"
