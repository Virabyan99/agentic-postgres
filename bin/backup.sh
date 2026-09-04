#!/usr/bin/env bash
#
# The backup operator surface.
#
# Five verbs, and none of them names a bucket, a stanza, a retention count or a
# credential. All four come from the deployed document and the rendered
# pgbackrest.conf, decided once (ADR 0002) -- so there is no flag here that
# could point a command at a repository the archiver is not writing to.
#
#   stanza-create  Initialise the repository for this project's stanza.
#                  Idempotent, measured: twice in a row exits 0. That is why the
#                  deploy's step 6c runs it unconditionally instead of probing.
#   check          Prove archiving and the repository BOTH work -- it forces a
#                  WAL switch and confirms the segment arrived. The only command
#                  here that tests the archiver end to end.
#   backup         Take one, --type full or --type incr.
#   info           What the repository reports. --json prints the summary the
#                  deployed document is built from.
#   expire         Apply the retention policy. Retention is NOT restated on the
#                  command line: it is repo1-retention-full in the rendered
#                  config, and pgBackRest applies it from there (D495, D463).
#
# **Every verb runs pgBackRest inside the database container** (ADR 0144).
# archive_command is executed by the postmaster, so the binary is in the postgres
# image and the credential is materialized into that container's generation owned
# by uid 999. The host has no pgBackRest and no repository credential, and that
# is what makes "the storage service cannot reach the backup repository" a
# filesystem property rather than a rule somebody keeps (ADR 0145).
#
# Root, because the deployed document is root-owned and every verb reaches a
# container over the local socket. A human at a TTY for anything that MUTATES the
# repository -- which here is `backup` and `expire`.
#
# Exit codes (runbook section 2 convention):
#   0  the verb completed
#   2  invalid operator input
#   3  missing local prerequisite, or not root
#   5  the deployment or the repository refused the operation
#   6  the verb ran and its answer is "no" -- the repository is not healthy

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

usage() {
  cat <<'USAGE'
Usage:
  sudo bin/backup.sh --outputs <outputs.json> stanza-create
  sudo bin/backup.sh --outputs <outputs.json> check
  sudo bin/backup.sh --outputs <outputs.json> backup --type full|incr
  sudo bin/backup.sh --outputs <outputs.json> info [--json]
  sudo bin/backup.sh --outputs <outputs.json> expire
  sudo bin/backup.sh --outputs <outputs.json> schedule status [--json]
  sudo bin/backup.sh --outputs <outputs.json> schedule enable|disable

`schedule` is the two systemd timers (weekly full, nightly incremental).
`status` exits 0 only when both are enabled. `enable` refuses while the unit
files are not installed -- that is provision-host.sh --apply's job -- and while
the repository holds no full backup, because the first one is yours to take.

The repository is created and checked by the deploy itself (step 6c), so the
first two verbs are here for diagnosis rather than for setup. What the deploy
does NOT do is take a backup: the first full backup of any project is an
operator command, because it is the first operation that writes a meaningful
amount to a repository nobody has paid for yet.

  1. Deploy. Step 6c creates the stanza and runs `check`. A check failure fails
     the deploy -- it is the only end-to-end test of the archiver, and a
     converged release over a broken archiver is the failure this session exists
     to prevent.
  2. `backup --type full`, once, by hand. Until this runs the deployed document
     publishes `awaiting_first_backup` and nothing can be restored.
  3. `info` to confirm what the repository holds. From here the timers take over.

`expire` is for reclaiming space after LOWERING backup.retain_full in the
manifest and redeploying. The timers do not need it: pgBackRest expires as part
of every backup.

What no verb here does: create a bucket, issue or revoke a token, or print a
credential. Those are Cloudflare operations performed by a human holding a
Cloudflare API token that no process in this repository has (ADR 0110, ADR 0145).
USAGE
}

die() {
  local code="$1"
  shift
  printf 'backup: %s\n' "$*" >&2
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
      stanza-create | check | backup | info | expire | schedule)
        [ -n "${verb}" ] || verb="${argument}"
        ;;
    esac
  done
  [ -n "${verb}" ] || die 2 "unknown verb. One of: stanza-create check backup info expire schedule"

  # `expire` is the only verb that DESTROYS anything, and what it destroys is a
  # backup chain that may be the only copy of a database. `backup` writes and
  # `stanza-create` is idempotent; neither can lose data.
  #
  # Confirmed by a human who has just been shown what the repository holds --
  # `info` first, deliberately, for the reason `storage-admin` prints status
  # before a cleanup: an operator approving a deletion should be reading what
  # they are deleting. Retention is applied from the config, so what expire
  # removes is decided by a manifest edit made earlier and possibly by someone
  # else.
  #
  # --yes exists for a scheduled sweep. It is a flag rather than the default
  # because no schedule calls this verb today: the timers take backups, and
  # pgBackRest expires as part of each one.
  if [ "${verb}" = "expire" ]; then
    local confirmed="no"
    for argument in "$@"; do
      [ "${argument}" = "--yes" ] && confirmed="yes"
    done
    if [ "${confirmed}" = "no" ]; then
      local forwarded=()
      for argument in "$@"; do
        [ "${argument}" = "expire" ] && continue
        forwarded+=("${argument}")
      done
      "$(python_bin)" "${ROOT_DIR}/bin/backup.py" "${forwarded[@]}" info || true
      printf '\nExpire deletes backup chains beyond backup.retain_full and cannot be undone.\n'
      printf 'Type EXPIRE to continue: '
      local answer=""
      read -r answer || true
      [ "${answer}" = "EXPIRE" ] || die 2 "not confirmed; nothing was expired."
    fi
  fi

  # `--yes` is this wrapper's and the Python side has never heard of it, so it is
  # dropped rather than forwarded into an argparse that would refuse it.
  local passthrough=()
  for argument in "$@"; do
    [ "${argument}" = "--yes" ] && continue
    passthrough+=("${argument}")
  done

  exec "$(python_bin)" "${ROOT_DIR}/bin/backup.py" "${passthrough[@]}"
}

main "$@"
