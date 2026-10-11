#!/bin/sh
#
# Run the psql probe once per transport (DBX-003).
#
# Both transports in one container rather than two services, and the reason is
# the secret contract rather than tidiness: every declared consumer materializes
# its own copy of the credential, so a second service would be a second file a
# rotation has to reach — to prove the same thing about the same role over a
# different port.
#
# Each invocation is a separate process with its own PGHOST, PGPORT and
# PGPASSFILE, so nothing carries between them. `set -e` means a failure in the
# first transport stops the second: the interesting output is the first failure,
# and a run that reported both would bury it.

set -eu

: "${APG_POOLED_HOST:?APG_POOLED_HOST is required}"
: "${APG_POOLED_PORT:?APG_POOLED_PORT is required}"
: "${APG_DIRECT_HOST:?APG_DIRECT_HOST is required}"
: "${APG_DIRECT_PORT:?APG_DIRECT_PORT is required}"

# Session 39 (D2350): the TLS input. `disable`, the default, is the platform
# transports' setting -- an `internal: true` network with no route off the host,
# and a cluster that serves no certificate (DBX-001..004 are unchanged).
# `verify-full` is the public door's (ADR 0268): libpq checks the edge's
# certificate against this machine's authorities (`sslrootcert=system`, libpq
# 16 and later) and the name it asked for. Anything else is refused rather than
# passed through.
case "${APG_SSLMODE:-disable}" in
    disable)
        PGSSLMODE=disable
        ;;
    verify-full)
        PGSSLMODE=verify-full
        PGSSLROOTCERT=system
        export PGSSLROOTCERT
        ;;
    *)
        printf 'client-psql: APG_SSLMODE must be disable or verify-full, not %s\n' "${APG_SSLMODE}" >&2
        exit 2
        ;;
esac
export PGSSLMODE

APG_TRANSPORT=pooled PGHOST="${APG_POOLED_HOST}" PGPORT="${APG_POOLED_PORT}" \
    /bin/sh /app/probe.sh

APG_TRANSPORT=direct PGHOST="${APG_DIRECT_HOST}" PGPORT="${APG_DIRECT_PORT}" \
    /bin/sh /app/probe.sh

printf 'client-psql: both transports passed\n'
