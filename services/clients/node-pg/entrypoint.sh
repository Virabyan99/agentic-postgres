#!/bin/sh
#
# Materialize the credential as a file, then run the probe.
#
# The same shape as the pooler's own entrypoint and for the same reason: the
# value is read from a mounted file inside the container and never becomes an
# environment variable, a Compose interpolation, or an argument. `docker
# inspect` on this container shows identifiers and nothing else.
#
# If PGPASSFILE is already set the file is used as it stands -- that is the
# `bin/connect.sh exec` path, where the helper has already written a 0600 file
# and will remove it. This script does not overwrite one it did not create.

set -eu

# The connection variables are checked BEFORE the credential, and the order was
# chosen after watching the other one: with nothing set at all, a credential
# check that ran first reported "no PGPASSFILE" -- a message about the last
# thing missing rather than the first, which sends the reader to the secret
# plane when the actual fault is an unset environment.
for name in PGHOST PGPORT PGUSER PGDATABASE APG_TRANSPORT APG_USER_A APG_USER_B; do
    eval "value=\${${name}:-}"
    if [ -z "${value}" ]; then
        printf 'client-node-pg: %s is required\n' "${name}" >&2
        exit 2
    fi
done

if [ -z "${PGPASSFILE:-}" ]; then
    secret="/run/secrets/app_runtime_password"
    if [ ! -r "${secret}" ]; then
        printf 'client-node-pg: no PGPASSFILE and %s is not readable\n' "${secret}" >&2
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

exec node /app/probe.mjs "$@"
