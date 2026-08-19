#!/usr/bin/env python3
"""The bootstrap plane's SQL, generated and executed over the container socket.

Invoked only by ``bin/postgres-bootstrap.sh``, which owns the operator surface
and the privilege gate. Split out for the same reason
``bin/bootstrap-providers.py`` is: the shell script is the contract and the
Python is the work, and building SQL in bash is how quoting mistakes become
injection.

**Statements are generated here and never taken from a file.** Every identifier
comes from the rendered ``outputs.json``, which is the single authority for
derived names, and is quoted through ``migrations.quote_identifier`` -- the same
function the migration renderer uses, so an identifier that would be refused
there is refused here. There is no path that takes SQL from an argument, from
stdin, or from a manifest.

**What it deliberately does not do.** It applies no migration, and it removes
nothing. A volume whose recorded identity does not match stops the run with
exit 11 and is never adopted (ADR 0030).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_postgres import migrations, secrets_contract
from agentic_postgres.secrets_contract import SECRET_ROOT

EXIT_CONTRACT = 5
EXIT_CHECK_FAILED = 6
EXIT_UNREACHABLE = 9
EXIT_IDENTITY_MISMATCH = 11


#: Compared on a mismatch. Deliberately only the immutable fields: the source
#: commit, manifest checksum and template version all change on a legitimate
#: redeploy, and a check that fires on a valid volume is one operators learn to
#: override (ADR 0030).
IDENTITY_FIELDS = ("project_key", "database_name", "compose_project_name", "instance_uuid")

#: The request roles the API authenticator may become, by document key.
#:
#: A module constant rather than a literal inside `role_statements`, so that the
#: proof asserting "the memberships are exactly the activated set" can read the
#: enumeration instead of restating it. It restated it, and Session 6 added
#: `project_admin` here in Run 9 (D266) without moving the copy -- so the first
#: host gate to run afterwards reported the product's own deliberate grant as a
#: violation (D301, ADR 0096).
#:
#: The membership carries `ADMIN FALSE, INHERIT FALSE, SET TRUE` in every case;
#: see `role_statements` for what each option is load-bearing for.
#:
#: `agent_reader` joined in Session 8 Run 2 (ADR 0116). It is the membership that
#: makes an agent token assumable at all: without it PostgREST's `SET ROLE` fails
#: and every agent request is refused before the hook it would have run. Adding
#: it is the whole of "activating the role" -- migration 0018 grants the
#: privileges, and this decides whether any token can name it.
#:
#: **`agent_writer` is still absent, and its absence is now DERIVED rather than
#: listed.** `check_violations` reads this tuple and refuses every project role
#: outside it, so Session 9's activation moves one line here and a *fourth*
#: unexpected membership still fails.
AUTHENTICATOR_REQUEST_ROLES = (
    "anon",
    "authenticated",
    "api_documentation",
    "project_admin",
    "agent_reader",
)


def await_cluster(container: str, database: str, *, attempts: int = 60, delay: float = 2.0) -> None:
    """Wait for the cluster, not for the port.

    The image runs a *temporary* server on the Unix socket during
    initialisation, and `pg_isready` answers on it. So does the healthcheck
    Compose waits for, which means `up --wait` can return while initdb is still
    running its bootstrap scripts -- and the first statement after it fails with
    "the database system is starting up", or worse, succeeds against a server
    that is about to be shut down and restarted.

    Two consecutive successful queries, not one. A single success is exactly
    what the temporary server produces.
    """
    consecutive = 0
    for _ in range(attempts):
        probe = subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                container,
                "psql",
                "-U",
                "postgres",
                "-d",
                database,
                "-X",
                "-qtA",
                "-c",
                "SELECT 1;",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if probe.returncode == 0 and probe.stdout.strip() == "1":
            consecutive += 1
            if consecutive == 2:
                return
        else:
            consecutive = 0
        time.sleep(delay)

    print(
        f"postgres-bootstrap: {container} never answered two consecutive queries; "
        "the cluster is not accepting connections.",
        file=sys.stderr,
    )
    raise SystemExit(EXIT_UNREACHABLE)


def psql(container: str, database: str, sql: str, *, read_only: bool = False) -> str:
    """Run SQL over the container's Unix socket as the OS postgres user.

    `docker exec -i`, and the `-i` is load-bearing: without it stdin is not
    forwarded, psql reads nothing, and the command exits 0 having executed
    nothing at all. That failure is silent and looks exactly like success.
    """
    command = ["docker", "exec", "-i", container, "psql", "-U", "postgres", "-d", database, "-X"]
    command += ["-v", "ON_ERROR_STOP=1", "-qtA"]
    if read_only:
        command += ["-c", sql]
        stdin = None
    else:
        stdin = sql
        command += ["-f", "-"]

    result = subprocess.run(
        command, input=stdin, capture_output=True, text=True, check=False, timeout=300
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip().splitlines()
        raise SystemExit(
            f"postgres-bootstrap: the cluster refused a statement: "
            f"{message[0] if message else 'no output'}"
        )
    return result.stdout.strip()


def query(container: str, database: str, sql: str) -> str:
    return psql(container, database, sql, read_only=True)


def build_statements(document: dict[str, Any], instance_uuid: str) -> list[str]:
    """Every statement the bootstrap plane issues, in order.

    Returned as a list rather than executed inline so that ``--check`` can
    report what would run without a second code path deciding what that is.
    """
    database = document["database"]
    roles = database["roles"]
    q = migrations.quote_identifier
    db = q(database["name"])

    statements: list[str] = []

    # The thirteen roles. NOLOGIN and NOINHERIT, with a null password verifier:
    # migration_user is the only one Session 3 activates, and it is activated by
    # the secret flow rather than here. Bootstrap clears an unexpected verifier
    # rather than tolerating it -- a role that acquired a password outside the
    # generation flow is a credential nobody can rotate.
    for name in roles.values():
        # S608 is suppressed here and at the sentinel INSERT below, and only
        # there. Every interpolated value is a derived identity from
        # outputs.json passed through `quote_identifier` or `quote_literal`,
        # which validate before quoting and raise on anything that is not
        # already a bare lowercase identifier or a plain string -- so a value
        # that could change the statement's shape never reaches the f-string.
        # Parameter binding is not available: PostgreSQL does not accept a
        # parameter where an identifier goes, which is the whole reason
        # `quote_identifier` exists.
        literal = migrations.quote_literal(name)
        create_role = (
            "DO $$ BEGIN "  # noqa: S608
            f"IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {literal}) "
            f"THEN CREATE ROLE {q(name)} NOLOGIN NOINHERIT; END IF; END $$;"
        )
        statements.append(create_role)
        statements.append(
            f"ALTER ROLE {q(name)} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;"
        )

    # The migration plane reaches owner authority only by assuming it: SET TRUE
    # so it can, INHERIT FALSE so it does not hold it merely by connecting,
    # ADMIN FALSE so it cannot grant the membership onward. The catalog tests
    # read these three columns directly; inferring them from the role's own
    # rolinherit would pass for the wrong reason (ADR 0026).
    statements.append(
        f"GRANT {q(roles['object_owner'])} TO {q(roles['migration_user'])} "
        f"WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;"
    )

    # Database-level posture. PUBLIC loses everything first, so a grant below is
    # the only way any role holds anything.
    statements.append(f"REVOKE ALL ON DATABASE {db} FROM PUBLIC;")
    statements.append(
        f"GRANT CREATE, CONNECT, TEMPORARY ON DATABASE {db} TO {q(roles['object_owner'])};"
    )
    # Every role that opens a connection of its own, and the list is exhaustive
    # rather than growing: `REVOKE ALL ... FROM PUBLIC` above means a role absent
    # here cannot connect at all, however correct its password is.
    #
    # `auth_service` joined this line after the first host deploy, which failed
    # with `FATAL: permission denied for database` and `DETAIL: User does not
    # have CONNECT privilege` (D291) -- the third defect in a row from the same
    # cause, which is that adding a service means touching every list that
    # enumerates roles, and nothing enumerated the lists.
    #
    # `storage_service` joins in Session 7 Run 4 -- in the run that ACTIVATES the
    # role, not the run that starts a container. Run 3 met the same class one
    # layer up and offline: the role held EXECUTE on all seven storage functions
    # and no USAGE on the schema, so every grant reached nothing (D337). Two
    # instances of one cause in two runs is the argument for adding a role to
    # every list at once rather than to the list in front of you.
    statements.append(
        f"GRANT CONNECT ON DATABASE {db} TO "
        f"{q(roles['migration_user'])}, {q(roles['app_runtime'])}, "
        f"{q(roles['postgrest_authenticator'])}, {q(roles['auth_service'])}, "
        f"{q(roles['storage_service'])};"
    )

    # CONNECT only, for the application runtime role. CREATE and TEMPORARY are
    # deliberately absent and are not an oversight to be tidied up later: CREATE
    # on the database is the authority to make a schema, and TEMPORARY is a way
    # to materialize data outside every policy this system writes.
    #
    # Session 4 adds the membership that gives it everything it does have. The
    # three options are each load-bearing and each read directly from the
    # catalog by the authorization tests, never inferred from the role's own
    # rolinherit (ADR 0026's lesson, applied to a second role):
    #
    #   INHERIT TRUE  an application must not have to SET ROLE to do its job;
    #   SET FALSE     so it cannot deliberately *become* `authenticated` and
    #                 escape whatever a later session attaches to its own
    #                 identity -- Session 6 makes the request claim authentic,
    #                 and a role that could shed its own identity would shed
    #                 that with it;
    #   ADMIN FALSE   so it cannot grant this membership onward.
    statements.append(
        f"GRANT {q(roles['authenticated'])} TO {q(roles['app_runtime'])} "
        f"WITH ADMIN FALSE, INHERIT TRUE, SET FALSE;"
    )

    # The API's request roles, and the exact inverse of the options above.
    #
    # This is the whole of SEC-ROLE-001's positive half: PostgREST impersonates a
    # role by issuing `SET ROLE` as the authenticator, so the set of roles a
    # token can name is the set granted here and nothing else. Measured against
    # a real deploy: a token naming `agent_writer` -- deliberately absent from
    # this list -- comes back **403 `permission denied to set role`**, and one
    # naming a role that does not exist comes back 401.
    #
    #   INHERIT FALSE  the authenticator must not hold `authenticated`'s reach
    #                  merely by connecting. It holds it only while it has
    #                  deliberately become that role, for one request.
    #   SET TRUE       which is the grant that makes impersonation work at all.
    #   ADMIN FALSE    so a compromised authenticator cannot hand the membership
    #                  to anything else.
    #
    # The two agent roles are Session 9's and are STILL not granted, in the run
    # that builds the agent lifecycle. That is the design and not an oversight:
    # an agent token names an agent role, PostgREST fails at `SET ROLE` before
    # `db-pre-request` ever runs, and the refusal is a property of the cluster
    # rather than of a check the hook performs. Measured on the locked image:
    # `SET ROLE <agent_reader>` as the authenticator is
    # `permission denied to set role`. It is also why no agent-specific
    # pre-request error code exists -- there is no path on which the hook could
    # emit one.
    #
    # `api_documentation` joins them in Session 5 Run 7 (D158). It is a request
    # role like the other two -- reached by SET ROLE, holding no credential of
    # its own -- and it needs the membership for the same reason: without it the
    # capture cannot fetch the document the role exists to be shown. What makes
    # it safe to grant is not this list but migration 0009's hook clause, which
    # refuses it a request identity, so every object it can name is guarded by a
    # policy that denies. Measured: a bare documentation token calling
    # `create_note` comes back 403 "new row violates row-level security policy",
    # and one carrying a subject comes back 401 before it reaches anything.
    # `project_admin` joins them in Session 6 Run 9, and it arrives HERE rather
    # than in a migration (D266). The plan put it in migration 0013; `GRANT role
    # TO role` needs authority the migration plane does not hold (D102), and the
    # three roles above already carry exactly these options from this loop. A
    # fourth granted somewhere else would be a second authority for role
    # membership, checked by nothing.
    #
    # What makes it safe to grant is the same thing that made `api_documentation`
    # safe: the membership lets the authenticator BECOME the role, and every
    # object that role can name is still guarded. `project_admin` reaches the API
    # surface as a subject like any other -- what it may do administratively is
    # decided by the scope in its token, not by the role name (API-ADMIN-001),
    # and the auth service is a separate process that does not use this
    # membership at all.
    for request_role in AUTHENTICATOR_REQUEST_ROLES:
        statements.append(
            f"GRANT {q(roles[request_role])} TO {q(roles['postgrest_authenticator'])} "
            f"WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;"
        )

    # Role-level settings, here rather than in the migration that revokes the
    # runtime role's direct reach. `ALTER ROLE ... SET` on *another* role needs
    # authority the migration plane does not hold, and the migration plane is
    # deliberately not a superuser -- so this is the plane that can do it (D102).
    #
    # A search_path of exactly `api`: the runtime role reaches data through the
    # api surface, and a path that included `app` would let an unqualified name
    # resolve to a base table it no longer has rights on, turning a permission
    # error into a confusing one. `pg_temp` is last on purpose -- first, it lets
    # a temporary object shadow a real one.
    statements.append(f"ALTER ROLE {q(roles['app_runtime'])} SET search_path = api, pg_temp;")
    # Every declared statement_timeout, from the document, keyed by the derived
    # role name (ADR 0067).
    #
    # This used to be one hard-coded `'30s'` on `app_runtime` and nothing else,
    # so the manifest's `api.rest.statement_timeouts` -- which `config`
    # validates -- reached no role at all, and a 30-second request ran to
    # completion under a manifest that said 5s (D197). The platform's default
    # for `app_runtime` still exists; it now lives in
    # `rendering.DEFAULT_APP_RUNTIME_STATEMENT_TIMEOUT` and arrives here as data,
    # so this plane applies what it was given rather than holding an opinion of
    # its own.
    #
    # Sorted so that two renders of one document produce one statement list; a
    # dict's iteration order is not a contract. What was applied is checked by
    # `check_violations` reading `pg_roles.rolconfig` -- not against this list,
    # which would only prove this program agrees with itself. The duration is
    # written through
    # `quote_literal` rather than interpolated bare: the schema's pattern is why
    # it cannot carry a quote, which is a reason to write it safely rather than a
    # reason not to bother.
    for role_name, timeout in sorted(document["database"]["statement_timeouts"].items()):
        statements.append(
            f"ALTER ROLE {q(role_name)} SET statement_timeout = "
            f"{migrations.quote_literal(timeout)};"
        )
    statements.append(
        f"ALTER ROLE {q(roles['app_runtime'])} SET idle_in_transaction_session_timeout = '60s';"
    )

    # Superuser work, and the reason this plane exists. pgvector is untrusted,
    # so CREATE EXTENSION requires superuser -- measured, not assumed. The
    # schema is created AUTHORIZATION the owner so that a later migration can
    # GRANT USAGE on it without needing this authority again.
    statements.append(
        f"CREATE SCHEMA IF NOT EXISTS extensions AUTHORIZATION {q(roles['object_owner'])};"
    )
    statements.append("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;")

    # app_private has to exist before the sentinel can live in it, and the
    # sentinel has to exist before any migration runs -- so neither can wait for
    # migration 0002. Creating it here idempotently means 0002 finds it present.
    statements.append(
        f"CREATE SCHEMA IF NOT EXISTS app_private AUTHORIZATION {q(roles['object_owner'])};"
    )

    # dbmate's own ledger, and the narrowest grants that let dbmate keep it.
    # This is a bootstrap-plane object (plan §6.1) because dbmate creates it
    # *itself*, before any migration runs and therefore before anything can
    # `SET ROLE` -- so without this, `migrate up` fails on the first statement
    # it issues with "permission denied for schema app_private", which is what
    # Run 7 measured. Created here, owned by the object owner, and reachable by
    # the migration plane through three grants and no more.
    #
    # Shape taken from dbmate 2.34.1: one varchar(255) primary key called
    # `version`. `CREATE TABLE IF NOT EXISTS` on the dbmate side then finds it
    # present and proceeds.
    # USAGE *and* CREATE. Measured: dbmate issues `CREATE TABLE IF NOT EXISTS`
    # on every run, and PostgreSQL checks CREATE on the schema before the
    # IF NOT EXISTS short-circuits -- so a role that can read and write the
    # ledger but not create in its schema fails on a table that already exists,
    # with "permission denied for schema app_private" and no mention of the
    # table it was not going to create.
    #
    # This concedes nothing the membership did not already imply: migration_user
    # can SET ROLE to the schema's owner, so anything it could create with this
    # grant it could already create by assuming that role. What the grant buys
    # is that dbmate's own bookkeeping needs no SET ROLE, which dbmate has no
    # way to issue.
    statements.append(f"GRANT USAGE, CREATE ON SCHEMA app_private TO {q(roles['migration_user'])};")
    statements.append(
        "CREATE TABLE IF NOT EXISTS app_private.schema_migrations "
        "(version varchar(255) NOT NULL PRIMARY KEY);"
    )
    statements.append(
        f"ALTER TABLE app_private.schema_migrations OWNER TO {q(roles['object_owner'])};"
    )
    statements.append(
        "GRANT SELECT, INSERT, DELETE ON app_private.schema_migrations "
        f"TO {q(roles['migration_user'])};"
    )
    statements.append(
        "CREATE TABLE IF NOT EXISTS app_private.project_identity ("
        "singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton), "
        "project_key text NOT NULL, database_name text NOT NULL, "
        "compose_project_name text NOT NULL, instance_uuid uuid NOT NULL, "
        "bound_at timestamptz NOT NULL DEFAULT now());"
    )
    # Two creators, one table, and until Run 7 they disagreed about who owns it.
    # This statement runs as the superuser, so the table it creates is owned by
    # `postgres`; migration 0002 creates the same table IF NOT EXISTS under
    # `SET LOCAL ROLE object_owner` and then COMMENTs on it -- which failed with
    # "must be owner of table project_identity" on a cluster where bootstrap got
    # there first, which is every cluster. Ownership is stated rather than left
    # to whichever plane created it.
    statements.append(
        f"ALTER TABLE app_private.project_identity OWNER TO {q(roles['object_owner'])};"
    )
    # Same rule as the role loop above: every value is quoted through
    # `quote_literal`, which raises on anything that is not a plain string.
    identity_values = ", ".join(
        migrations.quote_literal(value)
        for value in (
            document["project"]["key"],
            database["name"],
            document["compose"]["project_name"],
            instance_uuid,
        )
    )
    bind_identity = (
        "INSERT INTO app_private.project_identity "  # noqa: S608
        "(project_key, database_name, compose_project_name, instance_uuid) "
        f"VALUES ({identity_values}) ON CONFLICT (singleton) DO NOTHING;"
    )
    statements.append(bind_identity)
    return statements


def check_violations(container: str, database: str, document: dict[str, Any]) -> list[str]:
    """What is wrong with this cluster, read from the catalog.

    `--check` used to print how many statements *would* run and return 0. It
    could not fail: `EXIT_CHECK_FAILED` was defined, documented in the script's
    header, and never raised. A check that cannot go red is a green light
    measuring nothing, and it was the first command Run 7 was going to run
    against a real cluster (D61).

    Every question below is asked of `pg_roles`, `pg_auth_members`,
    `pg_namespace`, `pg_extension` or `has_database_privilege` -- never of the
    statement list this program would have run, which would only prove that
    this program agrees with itself.
    """
    database_block = document["database"]
    roles = database_block["roles"]
    literal = migrations.quote_literal
    violations: list[str] = []

    # One query per fact, and each returns a value that is false when the fact
    # is absent -- rather than one big query whose empty result would be read
    # as "nothing wrong".
    declared = sorted(roles.values())
    present = set(
        query(
            container,
            database,
            f"SELECT rolname FROM pg_roles WHERE rolname IN "  # noqa: S608
            f"({', '.join(literal(name) for name in declared)});",
        ).splitlines()
    )
    violations += [f"role {name} does not exist" for name in declared if name not in present]

    over_privileged = query(
        container,
        database,
        "SELECT rolname FROM pg_roles WHERE rolname IN "  # noqa: S608
        f"({', '.join(literal(name) for name in declared)}) AND (rolsuper OR rolcreatedb "
        "OR rolcreaterole OR rolreplication OR rolbypassrls);",
    ).splitlines()
    violations += [
        f"role {name} holds an attribute it must not" for name in over_privileged if name
    ]

    # The three membership options, read as three columns. Inferring them from
    # the member role's own rolinherit is the reading that passes for the wrong
    # reason (ADR 0026).
    #
    # `boolean || text` yields 'true'/'false', not the 't'/'f' psql prints in a
    # table. Measured, not assumed -- the first version of this expected 'f f t'
    # and reported a violation against a cluster that was correct, which is the
    # same defect in the other direction.
    owner_literal = literal(roles["object_owner"])
    member_literal = literal(roles["migration_user"])
    membership = query(
        container,
        database,
        "SELECT coalesce(string_agg(m.admin_option || ' ' || m.inherit_option "  # noqa: S608
        "|| ' ' || m.set_option, ','), 'absent') FROM pg_auth_members m "
        f"JOIN pg_roles owner ON owner.oid = m.roleid AND owner.rolname = {owner_literal} "
        f"JOIN pg_roles member ON member.oid = m.member AND member.rolname = {member_literal};",
    )
    if membership != "false false true":
        violations.append(
            f"{roles['migration_user']} membership of {roles['object_owner']} is "
            f"'{membership}', expected 'false false true' (admin, inherit, set)"
        )

    # The request roles, read the same way and for the same reason. Until Run 9
    # this checked one membership out of five, so the three the authenticator
    # depends on were granted by a line nobody verified -- and `INHERIT FALSE`
    # is not cosmetic: measured on the locked image, a plain `GRANT` records
    # `inherit_option = true`, which would give the authenticator every request
    # role's reach merely by connecting.
    #
    # Every role NOT in that tuple is checked for ABSENCE in the same pass, as a
    # set difference rather than as a list. That refusal is what makes a token
    # naming an unactivated role fail at role switching, and a membership added
    # by accident would turn a tested property into a silently open path.
    #
    # **Both loops read `AUTHENTICATOR_REQUEST_ROLES`, and until Session 8 Run 2
    # neither did.** The constant was created in Session 6 Run 9 for exactly this
    # -- its own docstring says so, and says that the copy was what reported the
    # product's deliberate `project_admin` grant as a violation on the first host
    # gate (D301, ADR 0096). The fix reached `role_statements`, which grants, and
    # never reached `check_violations`, which verifies. **A decision implemented
    # everywhere except the place that consumes it** -- CLAUDE.md section 6,
    # question 5, in the file that records the last time it was asked here.
    #
    # The absence half was a two-name literal, `("agent_reader", "agent_writer")`.
    # Activating one of them would have left the other as the only forbidden
    # role, and a *third* accidental membership -- `app_runtime`, `auth_service`,
    # `storage_service`, `object_owner` -- was never forbidden by anything.
    authenticator_literal = literal(roles["postgrest_authenticator"])
    for request_role in AUTHENTICATOR_REQUEST_ROLES:
        granted = query(
            container,
            database,
            "SELECT coalesce(string_agg(m.admin_option || ' ' || m.inherit_option "  # noqa: S608
            "|| ' ' || m.set_option, ','), 'absent') FROM pg_auth_members m "
            f"JOIN pg_roles granted ON granted.oid = m.roleid "
            f"AND granted.rolname = {literal(roles[request_role])} "
            "JOIN pg_roles member ON member.oid = m.member "
            f"AND member.rolname = {authenticator_literal};",
        )
        if granted != "false false true":
            violations.append(
                f"{roles['postgrest_authenticator']} membership of {roles[request_role]} "
                f"is '{granted}', expected 'false false true' (admin, inherit, set)"
            )

    # The complement, derived from the project's own role set. `object_owner` is
    # excluded because `migration_user`'s membership of it is a different
    # relation, checked above; every other declared role must be unreachable to
    # the authenticator, whether or not anybody thought to name it.
    forbidden = sorted(
        key
        for key in roles
        if key not in AUTHENTICATOR_REQUEST_ROLES
        and key not in {"postgrest_authenticator", "object_owner"}
    )
    for role_key in forbidden:
        granted = query(
            container,
            database,
            "SELECT coalesce(string_agg('present', ','), 'absent') "  # noqa: S608
            "FROM pg_auth_members m "
            f"JOIN pg_roles granted ON granted.oid = m.roleid "
            f"AND granted.rolname = {literal(roles[role_key])} "
            "JOIN pg_roles member ON member.oid = m.member "
            f"AND member.rolname = {authenticator_literal};",
        )
        if granted != "absent":
            violations.append(
                f"{roles['postgrest_authenticator']} holds a membership of "
                f"{roles[role_key]}, which this release does not activate: a token "
                "naming it must fail at role switching"
            )

    # The migration plane cannot connect without both. A role with LOGIN and a
    # null verifier authenticates against nothing and fails at dbmate.
    credential = query(
        container,
        database,
        "SELECT rolcanlogin::text || ' ' || (rolpassword IS NOT NULL)::text "  # noqa: S608
        f"FROM pg_authid WHERE rolname = {member_literal};",
    )
    if credential != "true true":
        violations.append(
            f"{roles['migration_user']} is not able to log in "
            f"(canlogin/verifier: '{credential or 'absent'}')"
        )

    for schema in ("extensions", "app_private"):
        exists = query(
            container,
            database,
            f"SELECT count(*)::text FROM pg_namespace WHERE nspname = {literal(schema)};",  # noqa: S608
        )
        if exists != "1":
            violations.append(f"schema {schema} does not exist")

    vector = query(
        container, database, "SELECT count(*)::text FROM pg_extension WHERE extname = 'vector';"
    )
    if vector != "1":
        violations.append("extension vector is not installed")

    public_connect = query(
        container,
        database,
        f"SELECT has_database_privilege('public', {literal(database_block['name'])}, "
        "'CONNECT')::text;",
    )
    if public_connect != "false":
        violations.append(f"PUBLIC still holds CONNECT on {database_block['name']}")

    # Guarded by existence. `has_database_privilege` raises on a role that does
    # not exist, and an unhandled raise here aborts the whole check with exit 1
    # -- so `--check` against a fresh cluster reported a crash instead of the
    # thirteen missing roles it was looking at. A check must be able to describe
    # the state it is most often run against.
    if roles["object_owner"] in present:
        owner_create = query(
            container,
            database,
            f"SELECT has_database_privilege({literal(roles['object_owner'])}, "
            f"{literal(database_block['name'])}, 'CREATE')::text;",
        )
        if owner_create != "true":
            violations.append(f"{roles['object_owner']} does not hold CREATE on the database")

    # The far side of ADR 0067's plane boundary, and the reason this block is
    # here rather than left implied. Before version 7 the manifest declared
    # these, `config` validated them, and the render dropped them -- so the
    # setting was declared, validated and applied to nothing, and every check in
    # this file agreed with the cluster while it happened (D197).
    #
    # Read from `pg_roles.rolconfig`, which is what `ALTER ROLE ... SET` writes,
    # rather than from the statement list this program would have issued. The
    # latter would only prove the program agrees with itself, which is the
    # standing rule for this whole function.
    #
    # Guarded by `present` for the reason the CREATE check above is: a query
    # against a role that does not exist returns nothing, and reporting "the
    # timeout is absent" on a cluster whose roles are all missing buries the
    # thirteen violations that actually matter under fourteen that repeat them.
    wanted = {
        role: timeout
        for role, timeout in database_block.get("statement_timeouts", {}).items()
        if role in present
    }
    if wanted:
        applied = dict(
            line.split(" ", 1)
            for line in query(
                container,
                database,
                "SELECT r.rolname || ' ' || coalesce("  # noqa: S608
                "(SELECT split_part(c, '=', 2) FROM unnest(r.rolconfig) AS c "
                "WHERE c LIKE 'statement_timeout=%'), 'absent') "
                "FROM pg_roles r WHERE r.rolname IN "
                f"({', '.join(literal(name) for name in sorted(wanted))});",
            ).splitlines()
            if line
        )
        for role, timeout in sorted(wanted.items()):
            observed = applied.get(role, "absent")
            if observed != timeout:
                violations.append(
                    f"{role} has statement_timeout '{observed}', the document says '{timeout}'"
                )

    return violations


def apply_credential(
    container: str, database: str, role: str, password: str, *, connection_limit: int | None = None
) -> None:
    """Give a role its verifier. Never printed, never in argv.

    Kept out of `build_statements` on purpose: that list is what `--check`
    describes and what an operator may be shown, and a password does not belong
    in something whose whole value is that it can be read.

    The password reaches the server over the container-local socket, inside one
    statement, through `quote_literal`. It is not an argument to anything: the
    SQL goes to psql's stdin, which is why `psql()` takes a string rather than
    building a command line.

    `connection_limit` is applied in the same statement as `LOGIN`, so a role
    never exists in a state where it can log in without a bound. The two as
    separate statements would leave a window -- short, and long enough for an
    application that reconnects in a loop.
    """
    limit = "" if connection_limit is None else f" CONNECTION LIMIT {int(connection_limit)}"
    statement = (
        f"ALTER ROLE {migrations.quote_identifier(role)} "
        f"LOGIN{limit} PASSWORD {migrations.quote_literal(password)};"
    )
    psql(container, database, statement)


def apply_connection_limit(container: str, database: str, role: str, limit: int) -> None:
    """Bound a role that has no credential yet.

    `apply_credential` sets `LOGIN`, the limit and the password in one statement,
    because a role must never exist in a state where it can log in without a
    bound. This is the other half of that rule: a role that cannot log in *may*
    carry its bound early, and carrying it early is what leaves no window when
    the credential arrives.

    Deliberately does not touch `LOGIN` or the password. `ALTER ROLE ...
    CONNECTION LIMIT` on a NOLOGIN role is a catalog change and nothing else,
    which is what makes this safe to run on every deploy of a project whose auth
    service does not exist yet.
    """
    statement = f"ALTER ROLE {migrations.quote_identifier(role)} CONNECTION LIMIT {int(limit)};"
    psql(container, database, statement)


def read_secret(project_key: str, consumer: str, name: str) -> str:
    """One materialized value, from the generation the project points at.

    Read from the filesystem here rather than granted to the bootstrap plane as
    a container: this plane is root on the host, and a second declared consumer
    would materialize a second copy of one credential -- two files for a
    rotation to reach instead of one.
    """
    pointer = Path(SECRET_ROOT) / project_key / "active-secret-generation.json"
    if not pointer.is_file():
        print(
            f"postgres-bootstrap: no active secret generation for {project_key}; "
            "run bin/materialize-secrets.sh first.",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_CONTRACT)

    generation = json.loads(pointer.read_text(encoding="utf-8"))["generation_id"]
    path = Path(SECRET_ROOT) / project_key / "generations" / generation / consumer / name
    if not path.is_file():
        print(
            f"postgres-bootstrap: generation {generation} has no {name} at {path}.",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_CONTRACT)

    # Trailing newlines only. Every container that reads one of these files does
    # it with `$(cat ...)`, which strips exactly that and nothing else; a
    # `.strip()` here would also take leading whitespace and set the role to a
    # value the container does not present.
    value = path.read_text(encoding="utf-8").rstrip("\n")
    if not value:
        print(f"postgres-bootstrap: {name} is empty.", file=sys.stderr)
        raise SystemExit(EXIT_CONTRACT)
    return value


#: Sessions the connection budget must leave room for besides the application:
#: the migration plane, the bootstrap plane itself, and an operator holding a
#: psql open while something is wrong. Small, and deliberately not zero -- a
#: budget with no slack is one where the first thing to fail is the tool you
#: would use to find out why.
OPERATIONAL_CONNECTION_HEADROOM = 5


def connection_budget(container: str, database: str) -> tuple[int, int]:
    """Ask the server, rather than the manifest, what it will actually allow.

    D94's rule. `max_connections` is in the manifest too, and the manifest is
    what *asked* for it -- but the running server is what enforces it, and the
    two differ the moment a container is started with an override or an older
    generation of the model. A budget computed from the file would be right
    until the day it mattered.
    """
    maximum = int(query(container, database, "SHOW max_connections").strip())
    reserved = int(query(container, database, "SHOW superuser_reserved_connections").strip())
    return maximum, reserved


def connection_limits(
    maximum: int,
    reserved: int,
    api_budget: int,
    auth_budget: int,
    storage_budget: int,
    pooler_pool_size: int,
) -> tuple[int, int, int, int]:
    """Every ceiling, computed together (D161, ADR 0070; D327, ADR 0099).

    Together is the whole point. `app_runtime` used to be given
    `maximum - reserved - headroom` -- everything -- and the authenticator was
    given nothing, because a ceiling for the API on top of *everything* is two
    limits that sum past what the server will hand out. A budget that looks
    computed and is not.

    So the division is: each service takes the commitment the manifest was
    checked against, the operational headroom is held back, and **the
    application gets what is left**. That last part is deliberate rather than a
    leftover. The application role serves both the pooler's server-side pool and
    the direct access profile, so a ceiling of `database.pool_size` would refuse
    a developer's direct session whenever the pooler was busy -- and any
    allowance added on top would be a number nobody measured.

    **The remainder is checked against the pooler's pool, and that check is
    D327.** Two arithmetics exist over this budget: the manifest charges
    `database.pool_size` for the application, and this charges the remainder.
    Nothing compared them until ADR 0099, and they agreed only by coincidence --
    23 against 20, with 3 to spare. `default_pool_size` is per (user, database)
    and `app_runtime` is the pooler's only application user, so a remainder
    below it is a pool the pooler cannot fill: PostgreSQL refuses the backend
    with `too many connections for role`, PgBouncer hands that to the client,
    and the message names the role rather than the number that caused it.

    Returned rather than applied so the arithmetic is testable without a
    cluster. Every failure raises rather than producing a value PostgreSQL reads
    as something else: a negative limit is "unlimited" and 0 is "refuse every
    login", so an error here is the only honest failure.
    """
    available = maximum - reserved
    application = (
        available - api_budget - auth_budget - storage_budget - OPERATIONAL_CONNECTION_HEADROOM
    )
    if application < 1:
        raise ValueError(
            f"max_connections={maximum} with {reserved} reserved leaves {available} usable; "
            f"the API commits {api_budget}, the auth service {auth_budget}, the storage "
            f"service {storage_budget}, and {OPERATIONAL_CONNECTION_HEADROOM} are held for "
            f"operations, so the application would be left with {application}. Raise "
            "database.max_connections or lower a pool_size; do not remove the headroom, "
            "because it is what leaves a psql available when this is wrong"
        )
    if application < pooler_pool_size:
        sufficient = (
            pooler_pool_size
            + api_budget
            + auth_budget
            + storage_budget
            + OPERATIONAL_CONNECTION_HEADROOM
            + reserved
        )
        raise ValueError(
            f"max_connections={maximum} with {reserved} reserved leaves the application "
            f"{application} connections, below the pooler's server-side pool of "
            f"{pooler_pool_size}. `default_pool_size` is per (user, database) and this role "
            "is the pooler's only application user, so the pool could not fill: PostgreSQL "
            "would refuse the backend with `too many connections for role` and PgBouncer "
            "would hand that to the client, naming the role rather than this arithmetic. "
            f"Raise database.max_connections to at least {sufficient}, "
            "or lower database.pool_size"
        )
    return application, api_budget, auth_budget, storage_budget


def app_runtime_password_available(project_key: str) -> bool:
    """Is the runtime credential in the generation this project points at?

    A project materialized through session 3 has no such file, and this program
    has to keep working on exactly those projects — they are what the
    convergence path is for. So the absence is a fact to report, not an error to
    raise, and the role stays NOLOGIN until a session-4 materialization gives it
    something to be.
    """
    pointer = Path(SECRET_ROOT) / project_key / "active-secret-generation.json"
    if not pointer.is_file():
        return False
    generation = json.loads(pointer.read_text(encoding="utf-8"))["generation_id"]
    path = (
        Path(SECRET_ROOT)
        / project_key
        / "generations"
        / generation
        / "pgbouncer"
        / "app_runtime_password"
    )
    return path.is_file()


#: Where the API's authenticator credential is materialized, and in what shape.
#: The file is a pgpass line rather than a bare value because the service that
#: mounts it is distroless and has no shell to wrap one (ADR 0056), so this
#: plane reads it back through the contract's own reader.
POSTGREST_CONSUMER = {
    "plane": "compose",
    "service": "postgrest",
    "target_file": "postgrest_authenticator_pgpass",
    "format": "pgpass",
}

#: The auth service's, in the same shape and for the same reason (D288).
#:
#: Must match `secrets.required.yaml`'s declaration of `auth_service_password`
#: exactly -- `recover_secret` reads the file according to the consumer it is
#: handed, so a `target_file` that disagreed would look for a file that is not
#: there and report the credential absent, leaving the role NOLOGIN with no
#: error. `test_the_bootstrap_consumers_match_the_secret_contract` compares the
#: two rather than trusting this copy.
AUTH_SERVICE_CONSUMER = {
    "plane": "compose",
    "service": "auth",
    "target_file": "auth_service_pgpass",
    "format": "pgpass",
}

#: The storage runtime's, in the same shape and for the same reasons.
#:
#: Session 7 Run 4. Must match `secrets.required.yaml`'s declaration of
#: `storage_service_password` exactly, and
#: `test_the_bootstrap_consumers_match_the_secret_contract` compares the two --
#: which is why the secret was declared in Run 2 rather than left until a
#: container needed it. The bootstrap plane reads the credential back out of the
#: consumer's own materialized file, so the consumer has to exist before the
#: role can be activated at all.
STORAGE_SERVICE_CONSUMER = {
    "plane": "compose",
    "service": "storage",
    "target_file": "storage_service_pgpass",
    "format": "pgpass",
}


def activate_storage_service(
    container: str, database: str, project_key: str, role: str, limit: int
) -> bool:
    """Give the storage role its credential and its ceiling. True if credentialed.

    **Extracted so it can be driven by a test** (Session 7 Run 4). The mutation
    battery is why: with this logic inline, a mutation that never applied the
    credential at all left every test green, because the reach test called
    `apply_credential` itself. That is D288/D289/D291's mistake occurring inside
    the module written to avoid it -- a rig that reaches the right end state by a
    route the product does not take proves the end state is reachable, not that
    the product reaches it (ADR 0065/0066).

    The decision is the part worth testing, not the ALTER ROLE: *does the active
    generation carry this consumer's file?* If it does, the role gets the
    credential and the bound together; if it does not, the role keeps its bound
    and stays NOLOGIN, and the caller says so. `storage_service_password` is
    `origin: generated`, so `--apply` creates it -- an absent credential here
    means the generation predates session 7, not that an operator missed a step
    at Cloudflare.
    """
    secret = materialized_secret_path(project_key, STORAGE_SERVICE_CONSUMER)
    if secret is None:
        apply_connection_limit(container, database, role, limit)
        print(
            "  storage service credential absent from this generation; role left NOLOGIN, "
            f"CONNECTION LIMIT {limit}"
        )
        return False

    apply_credential(
        container,
        database,
        role,
        read_pgpass_password(secret, STORAGE_SERVICE_CONSUMER, "storage service"),
        connection_limit=limit,
    )
    print(f"  storage service credential set, CONNECTION LIMIT {limit}")
    return True


def materialized_secret_path(project_key: str, consumer: dict[str, Any]) -> Path | None:
    """The file this consumer's secret lands in, in the active generation.

    Returns None when the project points at no generation or the generation has
    no such file. Absence is a fact to report rather than an error to raise: a
    project materialized through an earlier session genuinely has none, and
    those are the projects the convergence path exists for.
    """
    pointer = Path(SECRET_ROOT) / project_key / "active-secret-generation.json"
    if not pointer.is_file():
        return None
    generation = json.loads(pointer.read_text(encoding="utf-8"))["generation_id"]
    path = Path(secrets_contract.secret_source_path(project_key, generation, consumer))
    return path if path.is_file() else None


def read_pgpass_password(path: Path, consumer: dict[str, Any], label: str) -> str:
    """A role's password, out of the pgpass line that carries it.

    Through `secrets_contract.recover_secret` rather than a `split(':')` here.
    A second reader of that format would be a second opinion about what the file
    means, and the one that lives beside the writer is the one a round-trip test
    covers.

    Takes the consumer rather than closing over one: two roles now read their
    credential this way (D288), and a copy of this function per role is a second
    place for the pgpass format to be misunderstood. `label` is only for the
    message, which an operator reads at the worst possible moment.
    """
    value = secrets_contract.recover_secret(path.read_text(encoding="utf-8"), consumer)
    if not value:
        print(f"postgres-bootstrap: the {label} credential is empty.", file=sys.stderr)
        raise SystemExit(EXIT_CONTRACT)
    return value


def read_postgrest_password(path: Path) -> str:
    """The API authenticator's password. See `read_pgpass_password`."""
    return read_pgpass_password(path, POSTGREST_CONSUMER, "API authenticator")


def read_migration_password(project_key: str) -> str:
    """The materialized value, from the generation the project points at.

    Read here rather than granted to a container: the bootstrap plane is root on
    the host, and a second declared consumer would materialize a second copy of
    one credential -- two files for a rotation to reach instead of one.
    """
    pointer = Path(SECRET_ROOT) / project_key / "active-secret-generation.json"
    if not pointer.is_file():
        print(
            f"postgres-bootstrap: no active secret generation for {project_key}; "
            "run bin/materialize-secrets.sh first.",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_CONTRACT)

    generation = json.loads(pointer.read_text(encoding="utf-8"))["generation_id"]
    path = (
        Path(SECRET_ROOT)
        / project_key
        / "generations"
        / generation
        / "dbmate"
        / "migration_user_password"
    )
    if not path.is_file():
        print(
            f"postgres-bootstrap: generation {generation} has no migration credential at {path}.",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_CONTRACT)

    # Trailing newlines only. The dbmate entrypoint reads the same file with
    # `$(cat ...)`, which strips exactly that and nothing else; a `.strip()`
    # here would also take leading whitespace and set the role to a value the
    # container does not present.
    value = path.read_text(encoding="utf-8").rstrip("\n")
    if not value:
        print("postgres-bootstrap: the migration credential is empty.", file=sys.stderr)
        raise SystemExit(EXIT_CONTRACT)
    return value


def read_identity(container: str, database: str) -> dict[str, str] | None:
    """The sentinel row, or None if the table does not exist yet."""
    exists = query(
        container,
        database,
        "SELECT to_regclass('app_private.project_identity') IS NOT NULL;",
    )
    if exists != "t":
        return None
    row = query(
        container,
        database,
        "SELECT project_key || '|' || database_name || '|' || compose_project_name "
        "|| '|' || instance_uuid FROM app_private.project_identity;",
    )
    if not row:
        return None
    return dict(zip(IDENTITY_FIELDS, row.split("|"), strict=True))


def assert_identity_matches(observed: dict[str, str], document: dict[str, Any]) -> None:
    expected = {
        "project_key": document["project"]["key"],
        "database_name": document["database"]["name"],
        "compose_project_name": document["compose"]["project_name"],
    }
    differing = [
        f"{field}: expected {expected[field]!r}, volume says {observed[field]!r}"
        for field in expected
        if observed[field] != expected[field]
    ]
    if differing:
        # No secret is printed: every field compared is a derived, non-secret
        # identity. The instance UUID is reported because it is what an operator
        # matches against a volume, and it identifies nothing on its own.
        print("postgres-bootstrap: this volume belongs to a different project.", file=sys.stderr)
        for line in differing:
            print(f"  {line}", file=sys.stderr)
        print(f"  volume instance_uuid: {observed['instance_uuid']}", file=sys.stderr)
        print(
            "  Nothing was changed. Bootstrap never adopts a volume: select the correct "
            "one, or write a reviewed migration plan.",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_IDENTITY_MISMATCH)


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--outputs", required=True)
    parser.add_argument("--mode", choices=("check", "apply"), default="check")
    parser.add_argument("--state-root", required=True)
    arguments = parser.parse_args()

    document = json.loads(Path(arguments.outputs).read_text(encoding="utf-8"))
    container = document["database"]["container"]
    database = document["database"]["name"]

    if (
        subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", container],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        != "true"
    ):
        print(
            f"postgres-bootstrap: the container {container} is not running; "
            "the cluster cannot be reached.",
            file=sys.stderr,
        )
        return EXIT_UNREACHABLE

    # Before the first query, not after a failure. `up --wait` returns while the
    # image's temporary init server is still answering, so without this the
    # first statement of a fresh deploy is a race the deploy usually loses.
    await_cluster(container, database)

    observed = read_identity(container, database)
    if observed is not None:
        assert_identity_matches(observed, document)

    # A candidate UUID is generated only when the sentinel does not exist. On a
    # non-empty volume the committed row is authoritative and is recovered, never
    # regenerated -- a fresh UUID against existing data is how a volume stops
    # matching itself (ADR 0030).
    instance_uuid = observed["instance_uuid"] if observed else str(uuid.uuid4())

    statements = build_statements(document, instance_uuid)

    if arguments.mode == "check":
        violations = check_violations(container, database, document)
        print(f"postgres-bootstrap: --check, {len(statements)} statements would converge")
        print(f"  container      {container}")
        print(f"  database       {database}")
        print(f"  identity       {'bound' if observed else 'not yet bound'}")
        print(f"  roles declared {len(document['database']['roles'])}")
        if violations:
            print(f"  violations     {len(violations)}")
            for violation in violations:
                print(f"    - {violation}")
            return EXIT_CHECK_FAILED
        print("  violations     none")
        return 0

    psql(container, database, "\n".join(statements))

    key = document["project"]["key"]
    roles = document["database"]["roles"]

    apply_credential(
        container,
        database,
        roles["migration_user"],
        read_secret(key, "dbmate", "migration_user_password"),
    )
    print(f"postgres-bootstrap: {len(statements)} statements applied to {database}")
    print(f"  identity {instance_uuid}")
    print("  migration credential set")

    # The application runtime role, activated from the pooler's own materialized
    # file. Session 4's addition, and idempotent for the same reason the rest of
    # this program is: a redeploy re-issues it and the catalog ends up where it
    # already was.
    #
    # Skipped, loudly, when the file is not there. A project materialized
    # through an earlier session has no such secret, and refusing outright would
    # make this program unusable on the very projects the convergence path
    # exists for.
    maximum, reserved = connection_budget(container, database)
    api_budget = int(document["database"]["api_connection_budget"])
    auth_budget = int(document["database"]["auth_connection_budget"])
    storage_budget = int(document["database"]["storage_connection_budget"])
    # The pooler's server-side pool, published at v11 for exactly one purpose:
    # so this plane can check that the remainder covers it (D327, ADR 0099).
    # It is the manifest's `database.pool_size`, carried through the document
    # rather than re-read, because the bootstrap plane reads one document (D102).
    pooler_pool_size = int(document["database"]["pooler_pool_size"])
    runtime_limit, api_limit, auth_limit, storage_limit = connection_limits(
        maximum, reserved, api_budget, auth_budget, storage_budget, pooler_pool_size
    )

    if app_runtime_password_available(key):
        limit = runtime_limit
        apply_credential(
            container,
            database,
            roles["app_runtime"],
            read_secret(key, "pgbouncer", "app_runtime_password"),
            connection_limit=limit,
        )
        print(f"  runtime credential set, CONNECTION LIMIT {limit}")
        print(f"    from the server: max_connections {maximum}, reserved {reserved}")
    else:
        print("  runtime credential absent from this generation; role left NOLOGIN")

    # The API's authenticator, with the ceiling that used to have nowhere to
    # come from (D161 closed, ADR 0070). Its figure is the document's, which is
    # the figure `config.postgrest_connection_budget` computed and the manifest
    # was checked against; the application's is what the live server has left
    # after it. Both were computed above, from one query, so neither can be set
    # without the other having been.
    authenticator_secret = materialized_secret_path(key, POSTGREST_CONSUMER)
    if authenticator_secret is not None:
        apply_credential(
            container,
            database,
            roles["postgrest_authenticator"],
            read_postgrest_password(authenticator_secret),
            connection_limit=api_limit,
        )
        print(f"  API authenticator credential set, CONNECTION LIMIT {api_limit}")
    else:
        print("  API authenticator credential absent from this generation; role left NOLOGIN")

    # The auth service's ceiling, the third claimant on one max_connections
    # (ADR 0070) -- and its credential, which nothing set until the first host
    # deploy failed on it (D288).
    #
    # This block used to apply the limit alone and print "role NOLOGIN until
    # session 6". That sentence was written IN session 6, deferring the
    # activation to a run that never came: Run 7 built the service, Run 10
    # published it, and the role reached a host with no password at all. It is
    # D276's shape -- a comment describing work nobody wrote.
    #
    # Now it mirrors `app_runtime` and `postgrest_authenticator` exactly: if the
    # active generation carries the credential, the role gets it and its bound
    # together; if it does not, the role is left NOLOGIN and the run SAYS so
    # rather than implying a version of events.
    auth_secret = materialized_secret_path(key, AUTH_SERVICE_CONSUMER)
    if auth_secret is not None:
        apply_credential(
            container,
            database,
            roles["auth_service"],
            read_pgpass_password(auth_secret, AUTH_SERVICE_CONSUMER, "auth service"),
            connection_limit=auth_limit,
        )
        print(f"  auth service credential set, CONNECTION LIMIT {auth_limit}")
    else:
        apply_connection_limit(container, database, roles["auth_service"], auth_limit)
        print(
            "  auth service credential absent from this generation; role left NOLOGIN, "
            f"CONNECTION LIMIT {auth_limit}"
        )

    # The storage service's ceiling and credential. Session 7 Run 1 computed the
    # division; Run 4 activates the role.
    #
    # Identical in shape to the auth service's block above, and deliberately so.
    # The previous version applied the limit alone and printed a message
    # deferring the activation to this run -- the same shape the auth block once
    # carried, deferring to a session that was already the current one. D288 is
    # what that cost: the role reached a host with no password at all, because a
    # comment deferring work is not the same as a later run doing it. The
    # deferral is discharged in the run that owns it rather than restated.
    #
    # (`test_the_bootstrap_no_longer_defers_the_auth_role_to_a_later_session`
    # scans this file for that phrasing, so it is described here rather than
    # quoted -- a text scan cannot tell a quotation from a directive.)
    #
    # If the active generation carries the credential the role gets it and its
    # bound together; if it does not, the role is left NOLOGIN and the run SAYS
    # so. `storage_service_password` is `origin: generated`, so `--apply`
    # creates it -- an absent credential here means the generation predates
    # session 7, not that an operator forgot something at Cloudflare.
    activate_storage_service(container, database, key, roles["storage_service"], storage_limit)

    # Applied, then read back. The statements above returning 0 says psql
    # accepted them, which is not the same as the catalog holding what they
    # asked for -- Run 4's ALTER DEFAULT PRIVILEGES reported success and stored
    # nothing, and that is the standing reason this function does not trust its
    # own return code.
    remaining = check_violations(container, database, document)
    if remaining:
        print("postgres-bootstrap: applied, but the cluster does not agree:", file=sys.stderr)
        for violation in remaining:
            print(f"  - {violation}", file=sys.stderr)
        return EXIT_CHECK_FAILED
    return 0


if __name__ == "__main__":
    sys.exit(main())
