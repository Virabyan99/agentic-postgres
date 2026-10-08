#!/usr/bin/env bash
# The secret store's backup (ADR 0262, D2258), installed as
# /usr/local/sbin/secret-store-backup and run nightly by
# secret-store-backup.timer, as root.
#
# One pass: `pg_dump --format=custom` inside the database container, piped
# straight into `age --recipient` -- the dump never touches a disk unencrypted
# -- into ${OUT_DIR}/infisical-<utc>.dump.age (umask 077); the newest ${KEEP}
# kept; the new file copied to the B2 bucket by a pinned rclone container
# whose credential is the env file it alone reads; the object's size read back
# and compared. The store host holds only the age RECIPIENT; the identity that
# decrypts is the operator's (D2239), so this host cannot read its own backups.
#
# Exit: 0 copied and verified; 1 any failure (set -e), with a line naming it.
# Prints the object name and size; never a key, a password or a value.
set -euo pipefail
umask 077

COMPOSE_DIR="${SECRET_STORE_DIR:-/home/op/secret-store}"
ETC="${SECRET_STORE_ETC:-/etc/secret-store}"
OUT_DIR="${SECRET_STORE_BACKUPS:-/var/backups/secret-store}"
BUCKET="${SECRET_STORE_BUCKET:-apg-secret-store-backup}"
KEEP=14
RCLONE_IMAGE="docker.io/rclone/rclone:1.75.1@sha256:45401ad7410db1d67ffdb58e19059ad20b0d8e0285a60e38bbec55cc1019c7a5"

fail() {
  printf 'secret-store-backup: %s\n' "$1" >&2
  exit 1
}

recipient="$(tr -d '[:space:]' < "${ETC}/backup.age.pub")"
case "${recipient}" in
  age1*) ;;
  *) fail "${ETC}/backup.age.pub does not hold an age recipient (age1...)" ;;
esac
[ -r "${ETC}/backup.env" ] || fail "${ETC}/backup.env is missing"
install -d -m 0700 "${OUT_DIR}"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="${OUT_DIR}/infisical-${stamp}.dump.age"
partial="${target}.partial"
name="$(basename "${target}")"

docker compose --project-directory "${COMPOSE_DIR}" -p secret-store exec -T db \
  sh -c 'pg_dump --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --format=custom' \
  | age --recipient "${recipient}" > "${partial}"
[ -s "${partial}" ] || fail "the encrypted dump is empty"
mv "${partial}" "${target}"
size="$(stat -c %s "${target}")"

# The newest ${KEEP} stay on this host; older ones are removed.
find "${OUT_DIR}" -maxdepth 1 -name 'infisical-*.dump.age' -printf '%f\n' \
  | sort -r | tail -n "+$((KEEP + 1))" \
  | while read -r old; do rm -f -- "${OUT_DIR}/${old}"; done

docker run --rm --network host --env-file "${ETC}/backup.env" \
  -v "${OUT_DIR}:/backups:ro" "${RCLONE_IMAGE}" \
  copyto "/backups/${name}" "store:${BUCKET}/${name}"
remote="$(docker run --rm --network host --env-file "${ETC}/backup.env" "${RCLONE_IMAGE}" \
  lsf --format s "store:${BUCKET}/${name}")"
[ "${remote}" = "${size}" ] || fail "the copy of ${name} reads ${remote:-nothing} bytes, not ${size}"

printf 'secret-store-backup: %s %s bytes, copied to %s and read back\n' "${name}" "${size}" "${BUCKET}"
