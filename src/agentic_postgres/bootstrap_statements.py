"""The bootstrap plane's statements, as data.

**The SQL the bootstrap plane issues, separated from the issuing.** `psql`, the
container socket, the credential reads and the privilege gate stay in
`bin/postgres-bootstrap.py`; what moved here is the part that is a pure
function of the rendered document -- which is the part `apg dev` needs, and an
operator command may not import a service or another command (D292, ADR 0093).

**Nothing about it changed.** The bodies below are the bodies that were there,
moved by line span rather than retyped, and `bin/postgres-bootstrap.py`
re-exports every name it used to define -- so the four test modules that load
that file by path see the same names with the same arities (ADR 0175). The
statements an `apg dev` cluster applies are therefore the statements a deploy
applies, not a second implementation of them: F-005 is what the second
implementation cost, and `test_auth_endpoints.py`'s own comment still records
where it stopped a statement short.

Every identifier comes from the rendered `outputs.json`, the single authority
for derived names, and is quoted through `migrations.quote_identifier` -- the
same function the migration renderer uses, so an identifier that would be
refused there is refused here.
"""

from __future__ import annotations

from typing import Any

from agentic_postgres import migrations

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
#: `agent_writer` joined in Session 9 Run 2 (ADR 0137), and **migration 0019 had
#: to land first**: it grants the role `USAGE` on `app_private` and `EXECUTE` on
#: the hook and both comparison helpers, none of which 0018 gave it (D475).
#: Granting the membership first would have produced a request refused by
#: `permission denied for function postgrest_pre_request` rather than by the
#: boundary -- the correct outcome for a false reason, which is D417.
#:
#: **Six now, and the set is still closed by derivation rather than by listing.**
#: `check_violations` reads this tuple and refuses every project role outside it,
#: so a *seventh* unexpected membership still fails without anyone editing a
#: second place. What a derived set cannot do is refuse a bad edit to itself,
#: which is why one name stays written down in the proofs --
#: `test_bootstrap_statements.NEVER_A_REQUEST_ROLE`, which is now a service
#: identity rather than a role some later session is expected to activate.
AUTHENTICATOR_REQUEST_ROLES = (
    "anon",
    "authenticated",
    "api_documentation",
    "project_admin",
    "agent_reader",
    "agent_writer",
)


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
    #
    # `backup_user` joins in Session 10 Run 5, in the run that ACTIVATES it, for
    # the same reason `storage_service` did -- and the two prior instances are
    # the argument for adding a role to every list at once. It is the only role
    # on this line whose connection is opened by pgBackRest rather than by a
    # service: measured (rig 5), one connection per command and two when a
    # `check` overlaps a `backup` (ADR 0148).
    statements.append(
        f"GRANT CONNECT ON DATABASE {db} TO "
        f"{q(roles['migration_user'])}, {q(roles['app_runtime'])}, "
        f"{q(roles['postgrest_authenticator'])}, {q(roles['auth_service'])}, "
        f"{q(roles['storage_service'])}, {q(roles['backup_user'])};"
    )

    # The five privileges an online backup needs, all issued HERE because arm C
    # of rig 5 measured that the migration plane cannot issue any of them
    # (ADR 0148, D102's shape). A non-superuser object owner is refused each
    # function grant with `permission denied for function` and the role grant
    # with `Only roles with the ADMIN option ... may grant this role`, while the
    # same role's grant on a table it owns succeeds -- so it is a plane boundary
    # and not a broken `SET ROLE`.
    #
    # Applied unconditionally, on every deploy, whether or not the role has a
    # credential yet. A privilege granted to a role nothing can assume is inert
    # rather than wrong (CLAUDE.md §7), and the alternative -- granting only on
    # the deploy that happens to carry a secret -- makes the catalog depend on
    # which generation ran, which is the state nobody can reason about.
    #
    # `WITH ADMIN FALSE, INHERIT TRUE, SET FALSE` on the membership: INHERIT is
    # load-bearing and is the opposite of the authenticator's, because pgBackRest
    # issues no `SET ROLE` -- it connects and reads `pg_settings`, so a
    # membership it had to assume would be a membership it never uses. ADMIN
    # FALSE so it cannot pass the reach on; SET FALSE because it has no reason
    # to become the role.
    statements.append(
        f"GRANT {q(BACKUP_SETTINGS_ROLE)} TO {q(roles['backup_user'])} "
        f"WITH ADMIN FALSE, INHERIT TRUE, SET FALSE;"
    )
    for signature in BACKUP_FUNCTION_GRANTS:
        # The signature is a fixed string from a module constant, never a derived
        # or manifest value, so it is interpolated as written; the role is quoted
        # like every other identity in this function.
        statements.append(f"GRANT EXECUTE ON FUNCTION {signature} TO {q(roles['backup_user'])};")

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


#: Every privilege an online backup needs on PG 18, and nothing else.
#:
#: **Measured, one revocation at a time** (rig 5 arm G, ADR 0148). The set is
#: five because `pgbackrest check` needs two that `pgbackrest backup` does not,
#: and the deploy's step 6c and both timers run `check`:
#:
#:   revoked                     check  backup
#:   (all five granted)            0      0
#:   pg_switch_wal                57      0
#:   pg_create_restore_point      57      0
#:   pg_backup_start               0     57
#:   pg_backup_stop                0     57
#:   pg_read_all_settings         27     56
#:   (restored -- the control)     0      0
#:
#: **D541 is why this is a necessity matrix rather than a copy of the pgBackRest
#: documentation.** Granting `pg_create_restore_point` did not make `check` pass;
#: it moved the failure to `pg_switch_wal`, which an earlier arm had recorded as
#: unnecessary because nothing had reached it. One missing privilege masks the
#: next, so only revoke-one-at-a-time measures a set.
#:
#: The function signatures are spelled out because `GRANT EXECUTE ON FUNCTION`
#: needs them and because `pg_backup_stop` is overloaded: naming the wrong arity
#: raises rather than granting silently.
BACKUP_FUNCTION_GRANTS: tuple[str, ...] = (
    "pg_catalog.pg_backup_start(text, boolean)",
    "pg_catalog.pg_backup_stop(boolean)",
    "pg_catalog.pg_create_restore_point(text)",
    "pg_catalog.pg_switch_wal()",
)

#: The one grant that is a role membership rather than a function privilege.
#:
#: Separate from the tuple above because it is issued with different syntax and
#: fails differently: measured, a non-superuser is refused it with
#: `permission denied to grant role "pg_read_all_settings"` / `Only roles with
#: the ADMIN option ... may grant this role`, while the function grants are
#: refused with `permission denied for function`. Both refusals land on the
#: migration plane, which is why every one of the five is issued here (ADR 0148).
#:
#: Its absence does not fail as a permission error. `pg_settings` OMITS a
#: restricted row rather than nulling it, so pgBackRest sees four rows where it
#: asked for five and reports `unable to select some rows from pg_settings` with
#: the hint naming this very role (D542). Loud and total, which is the acceptable
#: half -- `pg1-path` is never silently compared against NULL.
BACKUP_SETTINGS_ROLE = "pg_read_all_settings"
