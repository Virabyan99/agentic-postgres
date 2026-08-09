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

APG_TRANSPORT=pooled PGHOST="${APG_POOLED_HOST}" PGPORT="${APG_POOLED_PORT}" \
    /bin/sh /app/probe.sh

APG_TRANSPORT=direct PGHOST="${APG_DIRECT_HOST}" PGPORT="${APG_DIRECT_PORT}" \
    /bin/sh /app/probe.sh

printf 'client-psql: both transports passed\n'
