#!/usr/bin/env bash
#
# The object-storage operator surface.
#
# Five verbs, and none of them takes a bucket or an object key. The bucket comes
# from the deployed document; the only keys this command handles are ones the
# database already holds, and it passes them to a container rather than printing
# them -- an object key is the unguessable half of a bearer credential.
#
#   status             What the plane holds, by state, plus the cleanup queue.
#   cleanup            One sweep: expire stale intents, then collect tombstones
#                      whose write window has closed.
#   verify-credential  Does the mounted credential reach the bucket? A HeadObject
#                      on a key that does not exist -- nothing is written, so this
#                      is safe against a live project at any time.
#   credential-digest  The sha256 of each mounted credential half. What a
#                      container holds is read FROM the container.
#   confirm-revoked    Poll, within a bounded window, until a retired credential
#                      stops being accepted -- with the live one probed in the
#                      same loop as the control.
#
# **There is no verb that prints a credential** (D105) and none that administers
# the bucket. Creating a bucket, reading its identity back, and issuing or
# revoking a token are Cloudflare REST API operations done by a human holding a
# Cloudflare API token that no process here has (ADR 0110). The runtime's S3
# credential cannot do any of them, measured: CreateBucket 403, ListBuckets 403.
#
# Root, because the deployed document and the secret generations are root-owned
# and every verb reaches a container over the local socket. A human at a TTY for
# anything that MUTATES -- which here is `cleanup` alone.
#
# Exit codes (runbook section 2 convention):
#   0  the verb completed
#   2  invalid operator input
#   3  missing local prerequisite, or not root
#   5  the deployment or the database refused the operation
#   6  the verb ran and its answer is "no"

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  sudo bin/storage-admin.sh --outputs <outputs.json> status
  sudo bin/storage-admin.sh --outputs <outputs.json> cleanup [--limit N] [--lease-seconds N]
  sudo bin/storage-admin.sh --outputs <outputs.json> verify-credential
  sudo bin/storage-admin.sh --outputs <outputs.json> credential-digest
  sudo bin/storage-admin.sh --outputs <outputs.json> confirm-revoked \
      --retired-credential-file <path> [--window-seconds N] [--interval-seconds N]

Rotating the R2 credential, in order. The phases are modelled on
bin/rotate-signing-key.sh; what is missing here is an acknowledgement step,
because a credential has no verifier fleet that must agree before it is safe to
switch -- one container holds it and no issued artefact outlives it.

  1. Issue a new bucket-scoped Object Read & Write token at Cloudflare. By hand:
     no command here sets a value at a provider (D249). Save BOTH halves -- the
     secret is shown exactly once and is never retrievable.
  2. Write the pair being REPLACED to a file now, before you overwrite it:
       {"access_key_id": "...", "secret_access_key": "..."}
     After step 3 it is gone, and step 6 needs it. This is the same shape as the
     APG_ROTATED_*_FROM_FILE inputs the Session 5 rotation proofs take.
  3. Put the new pair at APG_R2_ACCESS_KEY_ID and APG_R2_SECRET_ACCESS_KEY in
     Infisical, by hand.
  4. Bring the project down and up. Not `restart`: materialization writes a NEW
     generation, and what a container holds comes from the live pointer rather
     than from the deployed document (D76, D306, D253).
  5. `credential-digest`, then `verify-credential`. The first says the container
     picked up the new generation; the second says the new credential reaches the
     bucket. Both, in that order -- a container still on the old generation would
     pass the second and mean nothing by it.
  6. Revoke the OLD token at Cloudflare, by hand. Then `confirm-revoked` with the
     file from step 2. R2 permission changes are eventually consistent, so this
     polls within a window and reports what it saw. It will not declare a
     credential revoked without having watched the refusal happen.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'storage-admin: %s\n' "$*" >&2
  exit "$code"
}

# `python3`, never a bare `python`: Ubuntu ships no such binary, sudo resets PATH
# to secure_path (D80), and D184 is the record of a `#!/usr/bin/env python`
# shebang that worked until something ran the file directly rather than through
# its wrapper.
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
    die 2 "a verb is required."
  fi
  case "$1" in
    --help | -h)
      usage
      return 0
      ;;
  esac

  command -v docker >/dev/null 2>&1 || die 3 "docker is not installed."

  # The verb is read here only to decide whether a confirmation is owed. Every
  # argument is forwarded verbatim; this wrapper parses nothing else, so a flag
  # added to the Python side needs no change here.
  local verb=""
  local argument
  for argument in "$@"; do
    case "${argument}" in
      status | cleanup | verify-credential | credential-digest | confirm-revoked)
        [ -n "${verb}" ] || verb="${argument}"
        ;;
    esac
  done
  [ -n "${verb}" ] || die 2 "unknown verb. One of: status cleanup verify-credential credential-digest confirm-revoked"

  # `cleanup` is the only verb that changes anything, and what it changes is at a
  # third party: a provider DELETE cannot be undone and the bytes are not
  # recoverable from here. So it is confirmed by a human who has just been shown
  # the queue -- `status` first, deliberately, for the reason `rotate-signing-key`
  # prints status before a promotion: an operator approving a deletion should be
  # reading what they are deleting.
  #
  # --yes exists for a scheduled sweep, which is what this will eventually be. It
  # is a flag rather than the default because the first sweep on any deployment
  # is run by a person.
  if [ "${verb}" = "cleanup" ]; then
    local confirmed="no"
    for argument in "$@"; do
      [ "${argument}" = "--yes" ] && confirmed="yes"
    done
    if [ "${confirmed}" = "no" ]; then
      local forwarded=()
      for argument in "$@"; do
        [ "${argument}" = "cleanup" ] && continue
        forwarded+=("${argument}")
      done
      "$(python_bin)" "${ROOT_DIR}/bin/storage-admin.py" "${forwarded[@]}" status || true
      printf '\nCleanup deletes objects at the provider and cannot be undone.\n'
      printf 'Type CLEANUP to continue: '
      local answer=""
      read -r answer || true
      [ "${answer}" = "CLEANUP" ] || die 2 "not confirmed; nothing was deleted."
    fi
  fi

  # `--yes` is this wrapper's and the Python side has never heard of it, so it is
  # dropped rather than forwarded into an argparse that would refuse it.
  local passthrough=()
  for argument in "$@"; do
    [ "${argument}" = "--yes" ] && continue
    passthrough+=("${argument}")
  done

  exec "$(python_bin)" "${ROOT_DIR}/bin/storage-admin.py" "${passthrough[@]}"
}

main "$@"
