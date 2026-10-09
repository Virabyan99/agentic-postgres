#!/bin/sh
# The mirror copy (ADR 0188; the client since ADR 0264 is rclone). Runs inside
# the backup-mirror container on the project's backup egress network, as uid
# 65532, with four secret files mounted under /run/secrets and five
# identifiers in the environment.
#
# The credential never touches argv or disk here: rclone reads each remote from
# RCLONE_CONFIG_<REMOTE>_* in the environment, which is built from the mounted
# files and exported to the client alone, and RCLONE_CONFIG=/dev/null means no
# config file is read or written (measured on the pinned image: nothing lands
# in /tmp either). Nothing is printed but what rclone prints.
#
#   mirror.sh           copy the source bucket to the mirror bucket
#   mirror.sh count     print the mirror bucket's object count as JSON
#                       (`rclone size --json`), for the host to read
set -eu

read_secret() {
  # A single line, the trailing newline stripped; an empty file is refused
  # because an empty key is a credential that authenticates to nothing.
  value="$(cat "/run/secrets/$1")"
  [ -n "${value}" ] || { echo "backup-mirror: secret $1 is empty" >&2; exit 3; }
  printf '%s' "${value}"
}

[ "${BACKUP_MIRROR_ENABLED:-false}" = "true" ] || { echo "backup-mirror: no mirror is configured for this project" >&2; exit 6; }
for required in BACKUP_MIRROR_SOURCE_ENDPOINT BACKUP_MIRROR_SOURCE_BUCKET BACKUP_MIRROR_ENDPOINT BACKUP_MIRROR_BUCKET; do
  eval "value=\${${required}:-}"
  [ -n "${value}" ] || { echo "backup-mirror: ${required} is empty" >&2; exit 2; }
done

# Both sides over S3, so both publish an MD5 for a single-part object and
# `--checksum` can compare them (a native B2 remote would offer SHA-1 only).
# The source is the primary, at Cloudflare R2; the mirror is any S3 endpoint.
# `no_check_bucket`: each key is restricted to its own bucket and may not
# create or probe one (ADR 0110), so rclone is told the bucket exists.
RCLONE_CONFIG=/dev/null
RCLONE_CONFIG_SOURCE_TYPE=s3
RCLONE_CONFIG_SOURCE_PROVIDER=Cloudflare
RCLONE_CONFIG_SOURCE_ENDPOINT="https://${BACKUP_MIRROR_SOURCE_ENDPOINT}"
RCLONE_CONFIG_SOURCE_ACCESS_KEY_ID="$(read_secret source-s3-access-key-id)"
RCLONE_CONFIG_SOURCE_SECRET_ACCESS_KEY="$(read_secret source-s3-secret-access-key)"
RCLONE_CONFIG_SOURCE_NO_CHECK_BUCKET=true
RCLONE_CONFIG_MIRROR_TYPE=s3
RCLONE_CONFIG_MIRROR_PROVIDER=Other
RCLONE_CONFIG_MIRROR_ENDPOINT="https://${BACKUP_MIRROR_ENDPOINT}"
RCLONE_CONFIG_MIRROR_ACCESS_KEY_ID="$(read_secret mirror-s3-access-key-id)"
RCLONE_CONFIG_MIRROR_SECRET_ACCESS_KEY="$(read_secret mirror-s3-secret-access-key)"
RCLONE_CONFIG_MIRROR_NO_CHECK_BUCKET=true
# A regional endpoint (`s3.<region>.<provider domain>`, Backblaze's shape)
# names the region its signatures must carry.
case "${BACKUP_MIRROR_ENDPOINT}" in
  s3.*.*.*) RCLONE_CONFIG_MIRROR_REGION="$(printf '%s' "${BACKUP_MIRROR_ENDPOINT}" | cut -d. -f2)"; export RCLONE_CONFIG_MIRROR_REGION ;;
esac
export RCLONE_CONFIG \
  RCLONE_CONFIG_SOURCE_TYPE RCLONE_CONFIG_SOURCE_PROVIDER RCLONE_CONFIG_SOURCE_ENDPOINT \
  RCLONE_CONFIG_SOURCE_ACCESS_KEY_ID RCLONE_CONFIG_SOURCE_SECRET_ACCESS_KEY RCLONE_CONFIG_SOURCE_NO_CHECK_BUCKET \
  RCLONE_CONFIG_MIRROR_TYPE RCLONE_CONFIG_MIRROR_PROVIDER RCLONE_CONFIG_MIRROR_ENDPOINT \
  RCLONE_CONFIG_MIRROR_ACCESS_KEY_ID RCLONE_CONFIG_MIRROR_SECRET_ACCESS_KEY RCLONE_CONFIG_MIRROR_NO_CHECK_BUCKET

case "${1:-copy}" in
  copy)
    # `sync`: a changed object (pgBackRest rewrites backup.info on every
    # backup) is copied again, and an object the primary expired is removed
    # at the mirror, so retention is the primary's (D1000) -- what
    # `mc mirror --overwrite --remove` did. `--checksum`: size and MD5, never
    # a modification time the two providers do not share. `--retries 1`: one
    # invocation is ONE pass, so the verb's single extra pass stays the verb's
    # (ADR 0220); rclone's per-request retries are left on. A pass that exits
    # non-zero has left objects behind and the next pass completes it (D1001).
    exec rclone sync --checksum --fast-list --retries 1 \
      "source:${BACKUP_MIRROR_SOURCE_BUCKET}" "mirror:${BACKUP_MIRROR_BUCKET}"
    ;;
  count)
    exec rclone size --json --fast-list "mirror:${BACKUP_MIRROR_BUCKET}"
    ;;
  *)
    echo "backup-mirror: unknown action ${1}" >&2
    exit 2
    ;;
esac
