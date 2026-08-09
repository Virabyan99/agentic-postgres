#!/bin/sh
#
# Materialize the credential as a file, then run the probe. Identical in shape
# to the node-postgres fixture's entrypoint and to the pooler's own: the value
# is read from a mounted file inside the container and never becomes an
# environment variable, a Compose interpolation, or an argument.
#
# If PGPASSFILE is already set the file is used as it stands -- the
# `bin/connect.sh exec` path -- and this script does not overwrite one it did
# not create.

set -eu

# Checked before the credential, for the reason the node fixture's entrypoint
# records: with nothing set at all, a credential check that ran first reported
# "no PGPASSFILE", which is a message about the last missing thing rather than
# the first.
for name in PGHOST PGPORT PGUSER PGDATABASE APG_TRANSPORT APG_USER_A APG_USER_B; do
    eval "value=\${${name}:-}"
    if [ -z "${value}" ]; then
        printf 'client-psycopg: %s is required\n' "${name}" >&2
        exit 2
    fi
done

if [ -z "${PGPASSFILE:-}" ]; then
    secret="/run/secrets/app_runtime_password"
    if [ ! -r "${secret}" ]; then
        printf 'client-psycopg: no PGPASSFILE and %s is not readable\n' "${secret}" >&2
        exit 8
    fi
    PGPASSFILE=/tmp/.pgpass
    export PGPASSFILE
    umask 077
    password="$(cat "${secret}")"
    escaped="$(printf '%s' "${password}" | sed -e 's/\\/\\\\/g' -e 's/:/\\:/g')"
    printf '%s:%s:%s:%s:%s\n' \
        "${PGHOST:?PGHOST is required}" \
        "${PGPORT:?PGPORT is required}" \
        "${PGDATABASE:?PGDATABASE is required}" \
        "${PGUSER:?PGUSER is required}" \
        "${escaped}" > "${PGPASSFILE}"
    unset password escaped
fi

exec python -u /app/probe.py "$@"
