#!/bin/sh
#
# Client compatibility fixture: psql.
#
# First of the four, because it is the client with no framework between it and
# the boundary. Whatever the drivers do differently, this is what the protocol
# actually offers, and a failure here is a failure of the database or the pooler
# rather than of a library.
#
# WHAT IT PROVES, and each of these is a count that can come out wrong:
#
#   1. a connection authenticates over the transport named by APG_TRANSPORT and
#      reports its application_name to the server;
#   2. a write through api.create_note lands under the *transaction-local*
#      claim, set with set_config(..., is_local => true);
#   3. user A sees exactly its own rows and user B's are absent;
#   4. a transaction that sets no claim sees nothing at all -- deny by default,
#      which is the property FORCE row-level security plus a NULL claim gives;
#   5. app.notes is not addressable, and api.notes is.
#
# PARAMETERS ARE BOUND, NOT INTERPOLATED. `\bind` sends the query and its
# parameter values as a protocol-level extended-query exchange -- the values
# never enter the SQL text. The `:'name'` forms interpolate a psql variable into
# the *parameter list*, not into the statement, which is the distinction that
# makes this a parameterized query rather than a string built carefully.
# `\bind` needs psql 16 or newer; the base image was measured at 17.5 in Run 1,
# and the check below fails loudly rather than silently falling back to
# interpolation.
#
# `:user_a`, NOT `:'user_a'`. The quoted form is psql's SQL-LITERAL quoting,
# which is right for interpolating into statement text and wrong here: psql
# parses a meta-command's arguments before expanding variables, so the quotes
# it adds are never stripped and arrive as part of the parameter. Run 9
# measured the result -- `invalid input syntax for type uuid:
# "'3f6c2a10-...'"` -- which is the fixture using the boundary it exists to
# demonstrate incorrectly. A value passed to `\bind` is a value, not SQL.
#
# Exit codes: 0 every check passed, 2 bad input, 3 missing prerequisite,
# 6 a check failed, 8 the credential could not be prepared.

set -eu

fail() {
    code="$1"
    shift
    printf 'client-psql: %s\n' "$*" >&2
    exit "${code}"
}

: "${PGHOST:?PGHOST is required}"
: "${PGPORT:?PGPORT is required}"
: "${PGUSER:?PGUSER is required}"
: "${PGDATABASE:?PGDATABASE is required}"
: "${APG_TRANSPORT:?APG_TRANSPORT is required (pooled or direct)}"
: "${APG_USER_A:?APG_USER_A is required}"
: "${APG_USER_B:?APG_USER_B is required}"

case "${APG_TRANSPORT}" in
    pooled|direct) ;;
    *) fail 2 "APG_TRANSPORT must be pooled or direct, not ${APG_TRANSPORT}" ;;
esac

# The application name is set here rather than left to the caller, because it is
# what makes a pooled server connection attributable in pg_stat_activity. A
# fixture that could not be told apart from an application is one whose rows
# nobody can explain later.
APG_APPLICATION_NAME="apg-client-psql-${APG_TRANSPORT}"
export PGAPPNAME="${APG_APPLICATION_NAME}"

# The credential arrives as a file and stays one. If the caller already has a
# pgpass -- which is what `bin/connect.sh exec` provides -- it is used as is;
# otherwise one is written from the mounted secret under `umask 077`, into a
# tmpfs, exactly as the pooler's own entrypoint does. The value is never an
# environment variable and never an argument.
if [ -z "${PGPASSFILE:-}" ]; then
    secret="/run/secrets/app_runtime_password"
    [ -r "${secret}" ] || fail 8 "no PGPASSFILE and ${secret} is not readable"
    PGPASSFILE=/tmp/.pgpass
    export PGPASSFILE
    (
        umask 077
        password="$(cat "${secret}")"
        # A colon or a backslash in the value is a field separator or an escape
        # to libpq. Unescaped, the line parses into different fields and the
        # failure is "no password supplied" -- which sends the reader to the
        # wrong file.
        escaped="$(printf '%s' "${password}" | sed -e 's/\\/\\\\/g' -e 's/:/\\:/g')"
        printf '%s:%s:%s:%s:%s\n' \
            "${PGHOST}" "${PGPORT}" "${PGDATABASE}" "${PGUSER}" "${escaped}" > "${PGPASSFILE}"
    ) || fail 8 "the credential file could not be written"
fi

command -v psql >/dev/null 2>&1 || fail 3 "psql is not installed"

major="$(psql --version | awk '{print $3}' | cut -d. -f1)"
case "${major}" in
    ''|*[!0-9]*) fail 3 "could not read the psql major version" ;;
esac
[ "${major}" -ge 16 ] \
    || fail 3 "psql ${major} has no \\bind; this fixture will not fall back to interpolating values into SQL"

# -X so no user's .psqlrc changes what runs. -w so a missing credential fails
# instead of prompting into a pipe. -qtA for one bare value per line, which is
# what the comparisons below expect. ON_ERROR_STOP so a failed statement is a
# failed run rather than a later count that happens to look right.
query() {
    psql -X -w -q -t -A -v ON_ERROR_STOP=1 \
        -v user_a="${APG_USER_A}" -v user_b="${APG_USER_B}" \
        -f - 2>&1
}

# The assertion is the LAST statement's value, and the whole output is kept for
# the failure message.
#
# A block here runs several statements: the claim is set, then the thing being
# checked is evaluated, and each `\g` prints a row. Comparing the whole output
# against one expected value failed with `expected t, got t` followed by a
# second `t` on its own line -- true, unreadable, and about the harness rather
# than the property. Taking the last line is right rather than convenient: the
# earlier statements are setup, and `ON_ERROR_STOP=1` already means a failure in
# any of them ends the block before this runs.
expect() {
    label="$1"
    wanted="$2"
    got="$(cat)"
    got="$(printf '%s' "${got}" | tr -d '\r')"
    last="$(printf '%s\n' "${got}" | grep -v '^[[:space:]]*$' | tail -n 1)"
    if [ "${last}" != "${wanted}" ]; then
        printf 'client-psql: %s: expected %s, got %s\n' "${label}" "${wanted}" "${last}" >&2
        printf 'client-psql: full output was:\n%s\n' "${got}" >&2
        exit 6
    fi
    printf '  ok    %s\n' "${label}"
}

printf 'client-psql: %s over the %s transport as %s\n' \
    "${PGDATABASE}" "${APG_TRANSPORT}" "${PGUSER}"

# 1. The server sees the application name this fixture set. Read back from
#    pg_stat_activity rather than from the environment: over the pooled
#    transport the value has to survive the pooler, and that is the thing being
#    proved.
query <<'SQL' | expect "application_name reaches the server" "apg-client-psql-${APG_TRANSPORT}"
SELECT application_name FROM pg_stat_activity WHERE pid = pg_backend_pid();
SQL

# 2. A write under user A's claim, inside one transaction. The claim is set with
#    set_config(..., true) -- the function form of SET LOCAL, and the only form
#    that takes a bound parameter.
#    $1 is the claim and $2 is the title. `create_note` takes no owner
#    parameter -- it derives ownership from the claim -- so the equality below
#    is a check that the derivation happened, not a check that the value was
#    passed through.
query <<'SQL' | expect "user A can write under a transaction-local claim" "t"
BEGIN;
SELECT set_config('app.user_id', $1, true) IS NOT NULL \bind :user_a \g
SELECT (api.create_note($2)).owner_id = $1::uuid \bind :user_a 'psql fixture note (A)' \g
COMMIT;
SQL

# 3. The same for user B, so there is something for A to fail to see.
query <<'SQL' | expect "user B can write under its own claim" "t"
BEGIN;
SELECT set_config('app.user_id', $1, true) IS NOT NULL \bind :user_b \g
SELECT (api.create_note($2)).owner_id = $1::uuid \bind :user_b 'psql fixture note (B)' \g
COMMIT;
SQL

# 4. Isolation, stated as a count rather than as an absence. `count(*) = 0` for
#    the other user's rows AND `count(*) > 0` for one's own: an empty result for
#    both would satisfy "cannot see the other user" while proving nothing.
query <<'SQL' | expect "user A sees its own rows and none of user B's" "t"
BEGIN;
SELECT set_config('app.user_id', $1, true) IS NOT NULL \bind :user_a \g
SELECT count(*) FILTER (WHERE owner_id = $1::uuid) > 0
   AND count(*) FILTER (WHERE owner_id <> $1::uuid) = 0
  FROM api.notes \bind :user_a \g
COMMIT;
SQL

query <<'SQL' | expect "user B sees its own rows and none of user A's" "t"
BEGIN;
SELECT set_config('app.user_id', $1, true) IS NOT NULL \bind :user_b \g
SELECT count(*) FILTER (WHERE owner_id = $1::uuid) > 0
   AND count(*) FILTER (WHERE owner_id <> $1::uuid) = 0
  FROM api.notes \bind :user_b \g
COMMIT;
SQL

# 5. No claim, no rows. This is the check that would still pass if the policies
#    were removed and the table were empty, so it is deliberately run last --
#    after checks 2 and 3 have put rows in the table that this one must not see.
query <<'SQL' | expect "a transaction with no claim sees nothing" "0"
BEGIN;
SELECT count(*) FROM api.notes;
COMMIT;
SQL

# 6. The private schema is not addressable, and the public one is. Both halves,
#    because neither is safe to infer from the other (D103): the role holds
#    SELECT on the base tables through `authenticated` and is stopped by the
#    absence of schema USAGE, so the catalog says yes while the query says no.
query <<'SQL' | expect "the catalog says schema app is not usable" "denied"
SELECT CASE WHEN has_schema_privilege(current_user, 'app', 'USAGE') THEN 'reachable' ELSE 'denied' END;
SQL

# And the attempt itself, which is the half that matters. D103: the catalog
# reports has_table_privilege(..., 'app.notes', 'SELECT') as TRUE, because the
# role inherits that grant through `authenticated` so the security-invoker views
# work. It is the schema that stops the read. A test that asserted the table bit
# would fail while the property held, and the obvious fix for that failure --
# revoking SELECT from `authenticated` -- would silently break every api view.
if psql -X -w -q -t -A -c 'SELECT count(*) FROM app.notes' >/dev/null 2>&1; then
    fail 6 "app.notes was readable through this credential"
fi
printf '  ok    %s\n' "app.notes is not readable, whatever the table privilege says"

printf 'client-psql: every check passed\n'
