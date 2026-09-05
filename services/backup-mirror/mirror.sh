#!/bin/sh
# The mirror copy (ADR 0188). Runs inside the backup-mirror container on the
# project's backup egress network, as uid 65532, with four secret files
# mounted under /run/secrets and five identifiers in the environment.
#
# The credential never touches argv or disk here: `mc` reads an alias from
# MC_HOST_<alias> in the environment, which is built from the mounted files
# and exported to the client alone. Nothing is printed but what `mc` prints.
#
#   mirror.sh           copy the source bucket to the mirror bucket
#   mirror.sh count     print the mirror bucket's listing as JSON lines, for
#                       the host to count (this image has no wc)
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

MC_HOST_source="https://$(read_secret source-s3-access-key-id):$(read_secret source-s3-secret-access-key)@${BACKUP_MIRROR_SOURCE_ENDPOINT}"
MC_HOST_mirror="https://$(read_secret mirror-s3-access-key-id):$(read_secret mirror-s3-secret-access-key)@${BACKUP_MIRROR_ENDPOINT}"
export MC_HOST_source MC_HOST_mirror

case "${1:-copy}" in
  copy)
    # --overwrite: a changed object (pgBackRest rewrites backup.info on every
    # backup) is copied again. --remove: an object the primary expired is
    # removed at the mirror, so retention is the primary's (D1000). A pass may
    # exit non-zero with objects behind and the next pass completes it (D1001);
    # the exit code is the whole of what the verb reads.
    exec mc mirror --overwrite --remove "source/${BACKUP_MIRROR_SOURCE_BUCKET}" "mirror/${BACKUP_MIRROR_BUCKET}"
    ;;
  count)
    exec mc ls --recursive --json "mirror/${BACKUP_MIRROR_BUCKET}"
    ;;
  *)
    echo "backup-mirror: unknown action ${1}" >&2
    exit 2
    ;;
esac
