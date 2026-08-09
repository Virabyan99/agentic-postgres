"""Client compatibility fixture: Psycopg 3.

The same six checks as the psql and node-postgres fixtures, through the third
kind of client: a driver built on libpq. So `PGPASSFILE`, `PGAPPNAME` and the
rest are honoured by the C library rather than reimplemented, and what this
fixture actually tests is whether *its own* layer -- server-side binding,
transaction handling, and the pipeline it may use over the pooler -- behaves
through a transaction pooler.

**Every statement is parameterized, and Psycopg 3 binds server-side.** Psycopg 3
sends parameters over the extended query protocol rather than interpolating them
client-side the way Psycopg 2 did, which is what makes `%s` here a placeholder
rather than a format specifier. A claim is set with `set_config(..., true)`
rather than `SET LOCAL`, because `SET` takes no parameters.

**The transaction is explicit.** `autocommit` stays False and each block is a
`with connection.transaction()`, because the claim is transaction-local: under
autocommit every statement is its own transaction and the claim would be gone
before the insert that depends on it. That is the failure this fixture would see
first if the pooler's mode were changed to `session` and back.

Exit codes: 0 every check passed, 2 bad input, 6 a check failed.
"""

from __future__ import annotations

import os
import sys

import psycopg

TRANSPORTS = ("pooled", "direct")


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"client-psycopg: {name} is required", file=sys.stderr)
        raise SystemExit(2)
    return value


def fail(label: str, expected: object, got: object) -> None:
    print(f"client-psycopg: {label}: expected {expected}, got {got}", file=sys.stderr)
    raise SystemExit(6)


def expect(label: str, expected: object, got: object) -> None:
    if str(got) != str(expected):
        fail(label, expected, got)
    print(f"  ok    {label}")


def main() -> int:
    transport = required("APG_TRANSPORT")
    if transport not in TRANSPORTS:
        print(
            f"client-psycopg: APG_TRANSPORT must be pooled or direct, not {transport}",
            file=sys.stderr,
        )
        return 2

    user_a = required("APG_USER_A")
    user_b = required("APG_USER_B")
    application_name = f"apg-client-psycopg-{transport}"

    # No connection string is built here. libpq reads PGHOST, PGPORT, PGUSER,
    # PGDATABASE and PGPASSFILE from the environment, so there is nothing to
    # assemble and therefore nothing to assemble wrongly -- and no place a
    # credential could end up in a string.
    with psycopg.connect(application_name=application_name, autocommit=False) as connection:
        print(
            f"client-psycopg: {os.environ.get('PGDATABASE')} over the {transport} "
            f"transport as {os.environ.get('PGUSER')}"
        )

        # 1. The application name survives the transport, read back from the
        #    server rather than from the object that set it.
        with connection.transaction():
            row = connection.execute(
                "SELECT application_name FROM pg_stat_activity WHERE pid = pg_backend_pid()"
            ).fetchone()
        expect("application_name reaches the server", application_name, row[0])

        # 2 and 3. A write under each user's claim, inside an explicit
        #          transaction. create_note takes no owner parameter; it derives
        #          ownership from the claim, so the equality is a check that the
        #          derivation happened.
        for label, user_id, title in (
            ("user A", user_a, "psycopg fixture note (A)"),
            ("user B", user_b, "psycopg fixture note (B)"),
        ):
            with connection.transaction():
                connection.execute("SELECT set_config('app.user_id', %s, true)", (user_id,))
                created = connection.execute(
                    "SELECT (api.create_note(%s)).owner_id", (title,)
                ).fetchone()
            expect(f"{label} writes under its own claim", user_id, created[0])

        # 4. Isolation as a pair of counts. Either count alone can be satisfied
        #    by something other than a working policy.
        for label, user_id in (("user A", user_a), ("user B", user_b)):
            with connection.transaction():
                connection.execute("SELECT set_config('app.user_id', %s, true)", (user_id,))
                mine, theirs = connection.execute(
                    "SELECT count(*) FILTER (WHERE owner_id = %(id)s::uuid), "
                    "       count(*) FILTER (WHERE owner_id <> %(id)s::uuid) "
                    "  FROM api.notes",
                    {"id": user_id},
                ).fetchone()
            if mine < 1:
                fail(f"{label} sees its own rows", ">= 1", mine)
            expect(f"{label} sees none of the other user's rows", 0, theirs)

        # 5. No claim, no rows. Last, so the rows written above are what it has
        #    to fail to see.
        with connection.transaction():
            visible = connection.execute("SELECT count(*) FROM api.notes").fetchone()[0]
        expect("a transaction with no claim sees nothing", 0, visible)

        # 6. The private schema is not addressable, proved by attempting the
        #    read. D103: has_table_privilege reports true for app.notes because
        #    the role inherits that grant through `authenticated`, which is what
        #    makes the security-invoker views work; the schema is the boundary.
        reachable = True
        try:
            with connection.transaction():
                connection.execute("SELECT count(*) FROM app.notes")
        except psycopg.errors.InsufficientPrivilege as error:
            reachable = False
            if "schema" not in str(error):
                fail("app is refused for the documented reason", "schema app", str(error))
        if reachable:
            fail("app.notes is not readable", "permission denied", "rows returned")
        print("  ok    app.notes is not readable, whatever the table privilege says")

    print("client-psycopg: every check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
