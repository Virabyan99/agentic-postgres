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

# Session 39 (D2350): the TLS input. `disable`, the default, is the platform
# transports' setting -- an `internal: true` network with no route off the host,
# and a cluster that serves no certificate (DBX-001..004 are unchanged).
# `verify-full` is the public door's (ADR 0268): libpq checks the edge's
# certificate against this image's authorities and the name it asked for.
# NOT `sslrootcert=system` (D3020, D3021): psycopg[binary]'s bundled libpq has
# its own OpenSSL, whose OPENSSLDIR is its build directory, so `system` reads
# no authority at all and every verify-full connection is refused. The image's
# own Debian bundle (the base image's ca-certificates) is named by path, which
# that OpenSSL reads as a file; certifi is not installed here, and adding it
# would be a second lock entry for the same roots. Anything else is refused
# rather than passed through.
case "${APG_SSLMODE:-disable}" in
    disable)
        PGSSLMODE=disable
        ;;
    verify-full)
        PGSSLMODE=verify-full
        PGSSLROOTCERT=/etc/ssl/certs/ca-certificates.crt
        export PGSSLROOTCERT
        ;;
    *)
        printf 'client-psycopg: APG_SSLMODE must be disable or verify-full, not %s\n' "${APG_SSLMODE}" >&2
        exit 2
        ;;
esac
export PGSSLMODE

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
