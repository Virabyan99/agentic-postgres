"""Migration 0019's audit plane, against a cluster the way a deploy builds one.

Every migration is applied as `migration_user` over TCP -- dbmate's route, not
`psql -U postgres` -- because a superuser bypasses the ownership check that let
0012 pass four sessions of green proofs while being unappliable (D285). Every
request is made by `SET ROLE` into the role that would make it, because a
privilege result measured as a superuser measures nothing (ADR 0065/0066).

**A grant question reads the catalog; a reach question sets the role and tries
it** (ADR 0134). `has_function_privilege` reports privileges held by way of
membership, so it answers `true` for a `NOINHERIT` role that appears in no ACL
entry at all -- which is how a Session 8 assertion flagged a role migration 0006
had correctly revoked. The two kinds of question are kept apart below and each
is asked with the instrument that can answer it.

**What this module does not test.** The pre-request hook is not involved: there
is no PostgREST here, so the GUCs are set directly, exactly as the hook sets
them. That the hook sets them from a token is migration 0018's property and is
asserted in its own module. What is measured here is what the schema does *given*
those GUCs.
"""

from __future__ import annotations

# ruff: noqa: S608
#
# Every interpolated value below is a role or database name read from a rendered
# outputs document this repository produced, validated by the outputs schema.
# None of it is caller input, and a role name cannot be bound as a parameter --
# the same judgement tests/deployment/conftest.py records.
import importlib.util
import json
import secrets
import subprocess
import time
import uuid
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, migrations

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

FIXTURE = REPO_ROOT / ".generated" / "fixture-alpha-dev"

#: The two functions 0019 adds to `api`, with the argument lists their ACLs are
#: keyed by. Written out rather than scraped: this is the list the assertions
#: below compare against, so deriving it from the same file they are checking
#: would let an empty scrape agree with an empty expectation.
AUDIT_FUNCTIONS = ("agent_audit_begin", "agent_audit_complete")

#: The roles 0019 grants the audit functions to, and the only ones. An exact
#: set, re-derived rather than relaxed when it moves (ADR 0096, D300): a subset
#: check would pass the next accidental grant forever.
AUDIT_GRANTEES = ("agent_reader", "agent_writer")


def _docker(*args: str, stdin: str | None = None, timeout: int = 240):
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=False, input=stdin, timeout=timeout
    )


def _bootstrap() -> Any:
    specification = importlib.util.spec_from_file_location(
        "apg_postgres_bootstrap", REPO_ROOT / "bin" / "postgres-bootstrap.py"
    )
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _bootstrap_module() -> Any:
    """`bin/postgres-bootstrap.py`, loaded by path.

    `AUTHENTICATOR_REQUEST_ROLES` is the single authority for which roles a token
    may name. Reading it rather than restating it is what D301, D416 and D492 are
    all about, and restating it is the habit that has now produced five copies
    across four sessions.
    """
    specification = importlib.util.spec_from_file_location(
        "apg_postgres_bootstrap_audit_plane", REPO_ROOT / "bin" / "postgres-bootstrap.py"
    )
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _locked_image() -> str:
    for line in (REPO_ROOT / "versions.env").read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "POSTGRES_IMAGE":
            return value.strip()
    pytest.fail("POSTGRES_IMAGE is absent from versions.env")


@pytest.fixture(scope="module")
def cluster() -> Any:
    """A cluster built the way a deploy builds one, with all twenty applied."""
    if not (FIXTURE / "outputs.json").is_file():
        pytest.skip("no rendered fixture; run ./deploy.sh --render-only")
    if _docker("version", "--format", "{{.Server.Version}}", timeout=30).returncode != 0:
        pytest.skip("docker is not available")

    document = json.loads((FIXTURE / "outputs.json").read_text(encoding="utf-8"))
    roles = document["database"]["roles"]
    database = document["database"]["name"]
    name = f"apg-audit-plane-{secrets.token_hex(4)}"
    migration_password = secrets.token_hex(24)

    started = _docker(
        "run", "-d", "--name", name,
        "-e", f"POSTGRES_PASSWORD={secrets.token_hex(24)}",
        _locked_image(),
    )  # fmt: skip
    if started.returncode != 0:
        pytest.skip(f"cannot start the locked cluster: {started.stderr.strip()[:200]}")

    try:
        rounds = 0
        for _ in range(90):
            probe = _docker("exec", name, "pg_isready", "-U", "postgres", timeout=30)
            rounds = rounds + 1 if probe.returncode == 0 else 0
            if rounds >= 2:
                break
            time.sleep(1)
        assert rounds >= 2, "the cluster never became ready"

        def su(sql: str, db: str = "postgres") -> subprocess.CompletedProcess[str]:
            return _docker(
                "exec", "-i", name, "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
                "-U", "postgres", "-d", db, stdin=sql,
            )  # fmt: skip

        setup = [f'CREATE ROLE "{role}" NOLOGIN;' for role in sorted(set(roles.values()))]
        setup += [
            f"ALTER ROLE \"{roles['migration_user']}\" LOGIN PASSWORD '{migration_password}';",
            f'GRANT "{roles["object_owner"]}" TO "{roles["migration_user"]}" '
            "WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;",
            f'CREATE DATABASE "{database}" OWNER "{roles["object_owner"]}";',
        ]
        result = su("\n".join(setup))
        assert result.returncode == 0, result.stderr
        result = su(f'CREATE SCHEMA extensions AUTHORIZATION "{roles["object_owner"]}"', database)
        assert result.returncode == 0, result.stderr

        bootstrap = _bootstrap()
        result = su("\n".join(bootstrap.build_statements(document, str(uuid.uuid4()))), database)
        assert result.returncode == 0, f"the product's bootstrap statements failed: {result.stderr}"

        manifest = migrations.load_manifest()
        applied_names = []
        for entry in manifest["migrations"]:
            payload = migrations.render_migration(entry, manifest, document)
            body = payload.split("-- migrate:down", 1)[0].replace("-- migrate:up", "", 1)
            applied = _docker(
                "exec", "-i", "-e", f"PGPASSWORD={migration_password}", name,
                "psql", "-U", roles["migration_user"], "-h", "127.0.0.1", "-d", database,
                "-qtA", "-v", "ON_ERROR_STOP=1", "-1", "-f", "-",
                stdin=body,
            )  # fmt: skip
            assert applied.returncode == 0, f"{entry['name']}: {applied.stderr[:400]}"
            applied_names.append(entry["name"])

        # The fixture's own control. Every assertion below is about objects 0019
        # creates, and a cluster carrying eighteen migrations would fail them all
        # with "relation does not exist" -- which reads as a broken test rather
        # than a stale rendering. D211-D214 is four ways a proof stays unexecuted;
        # this is the cheap guard against the one that applies here.
        for required in ("agent_write_and_audit_plane", "agent_audit_reader"):
            assert required in applied_names, (
                f"{required} was not applied; the rendered set is {applied_names}. "
                "Re-render: ./deploy.sh --project project.example.yaml "
                "--capabilities capabilities.example.yaml --render-only"
            )

        yield {"name": name, "database": database, "roles": roles, "su": su}
    finally:
        _docker("rm", "-f", name, timeout=60)


def su(cluster: dict[str, Any], sql: str) -> subprocess.CompletedProcess[str]:
    return cluster["su"](sql, cluster["database"])


def as_role(cluster: dict[str, Any], role_key: str, sql: str) -> subprocess.CompletedProcess[str]:
    """One statement as a request role, reached by `SET ROLE`.

    Not by logging in: a request role has no LOGIN attribute. `SET ROLE` is what
    PostgREST's authenticator does, so this exercises the grants that decide a
    real request.
    """
    return su(cluster, f'SET ROLE "{cluster["roles"][role_key]}";\n{sql}')


def as_agent(
    cluster: dict[str, Any],
    role_key: str,
    agent_id: str,
    owner_id: str,
    sql: str,
) -> subprocess.CompletedProcess[str]:
    """A request with the GUCs the pre-request hook would have set.

    One transaction, because `set_config(..., true)` is transaction-local -- each
    `su` call is its own session, so a GUC set in one and read in another would
    be a different measurement entirely (D116/D117 are what that class costs).
    """
    return su(
        cluster,
        f"""
        BEGIN;
        SET LOCAL ROLE "{cluster["roles"][role_key]}";
        SELECT set_config('app.agent_id', '{agent_id}', true);
        SELECT set_config('app.user_id', '{owner_id}', true);
        {sql}
        COMMIT;
        """,
    )


# ---------------------------------------------------------------------------
# The table is reachable only through the functions (ADR 0052, ADR 0135)
# ---------------------------------------------------------------------------


def test_no_role_holds_any_privilege_on_the_audit_table(cluster: dict[str, Any]) -> None:
    """A grant question, so it reads the catalog (ADR 0134).

    `aclexplode(relacl)` names every grantee in an ACL entry. `has_table_privilege`
    would answer for privileges held by way of membership and report roles that
    appear in no entry at all, which is D467 exactly -- and migration 0006 had
    written that trap down for the table twin two sessions before it was walked
    into.
    """
    result = su(
        cluster,
        """
        SELECT coalesce(string_agg(DISTINCT grantee.rolname, ',' ORDER BY grantee.rolname), '')
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'app_private'
        CROSS JOIN LATERAL aclexplode(c.relacl) acl
        JOIN pg_roles grantee ON grantee.oid = acl.grantee
        WHERE c.relname = 'agent_audit'
          AND grantee.rolname <> current_user;
        """,
    )
    assert result.returncode == 0, result.stderr
    holders = [name for name in result.stdout.strip().split(",") if name]
    owner = cluster["roles"]["object_owner"]
    assert set(holders) <= {owner}, (
        f"{sorted(set(holders) - {owner})} hold a privilege on app_private.agent_audit. "
        "The definer functions are the only paths in, which is what makes the record "
        "append-only to every request role"
    )


def test_a_request_role_cannot_read_or_write_the_audit_table(cluster: dict[str, Any]) -> None:
    """A reach question, so it sets the role and tries it (ADR 0134).

    The complement of the catalog assertion above, and it is a different claim:
    that one says no ACL entry names these roles, this one says the attempt
    actually fails. Two functions can be wrong in the same direction; an attempt
    that succeeds against an empty ACL cannot.
    """
    for role_key in ("agent_reader", "agent_writer", "authenticated", "anon"):
        read = as_role(cluster, role_key, "SELECT count(*) FROM app_private.agent_audit;")
        assert read.returncode != 0, f"{role_key} read app_private.agent_audit"
        assert "permission denied" in (read.stderr or "").lower(), read.stderr

        write = as_role(
            cluster,
            role_key,
            "INSERT INTO app_private.agent_audit "
            "(source, agent_id, owner_id, tool, outcome) VALUES "
            "('agent_plane', gen_random_uuid(), gen_random_uuid(), 'forged', 'served');",
        )
        assert write.returncode != 0, f"{role_key} wrote to app_private.agent_audit"


# ---------------------------------------------------------------------------
# The functions themselves
# ---------------------------------------------------------------------------


def test_both_audit_functions_are_definers_with_a_pinned_search_path(
    cluster: dict[str, Any],
) -> None:
    """0005's rule, for the two functions 0019 adds.

    A definer whose `search_path` is not pinned executes whatever a caller who
    can create a temporary object put in front of an unqualified name, as the
    owner. Both halves are asserted: `prosecdef`, and the config entry.
    """
    for name in AUDIT_FUNCTIONS:
        result = su(
            cluster,
            f"""
            SELECT p.prosecdef::text || '|' ||
                   coalesce(array_to_string(p.proconfig, ','), '<none>')
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace AND n.nspname = 'api'
            WHERE p.proname = '{name}';
            """,
        )
        assert result.returncode == 0, result.stderr
        secdef, _, config = result.stdout.strip().partition("|")
        assert secdef == "true", f"api.{name} is not SECURITY DEFINER"
        assert "search_path=pg_catalog, pg_temp" in config.replace('"', ""), (
            f"api.{name} does not pin its search_path: {config}"
        )


def test_no_audit_function_is_executable_by_public(cluster: dict[str, Any]) -> None:
    """A new function is EXECUTABLE BY PUBLIC the moment it exists (D57, D262).

    `anon` holds USAGE on schema `api` since 0001, so a function left with its
    default grant is callable by an unauthenticated request -- and
    `openapi-mode = follow-privileges` follows a PUBLIC grant, which would
    advertise it in the document an anonymous caller receives.
    """
    for name in AUDIT_FUNCTIONS:
        result = su(
            cluster,
            f"""
            SELECT coalesce(string_agg(acl.grantee::regrole::text, ',' ORDER BY
                                       acl.grantee::regrole::text), '')
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace AND n.nspname = 'api'
            CROSS JOIN LATERAL aclexplode(p.proacl) acl
            WHERE p.proname = '{name}' AND acl.grantee = 0;
            """,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "", f"api.{name} is executable by PUBLIC"


def test_the_audit_functions_are_granted_to_exactly_the_two_agent_roles(
    cluster: dict[str, Any],
) -> None:
    """An exact set, and it stays exact when it moves (ADR 0096, D300).

    `authenticated` is the one worth naming: a human operation is not audited
    here, and a grant to `api_documentation` would put an agent-plane function in
    the document that role builds (ADR 0118).
    """
    expected = {cluster["roles"][key] for key in AUDIT_GRANTEES}
    owner = cluster["roles"]["object_owner"]
    for name in AUDIT_FUNCTIONS:
        result = su(
            cluster,
            f"""
            SELECT coalesce(string_agg(DISTINCT grantee.rolname, ',' ORDER BY
                                       grantee.rolname), '')
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace AND n.nspname = 'api'
            CROSS JOIN LATERAL aclexplode(p.proacl) acl
            JOIN pg_roles grantee ON grantee.oid = acl.grantee
            WHERE p.proname = '{name}' AND acl.privilege_type = 'EXECUTE';
            """,
        )
        assert result.returncode == 0, result.stderr
        granted = {n for n in result.stdout.strip().split(",") if n} - {owner}
        assert granted == expected, (
            f"api.{name} is granted EXECUTE to {sorted(granted)}, not {sorted(expected)}"
        )


# ---------------------------------------------------------------------------
# D475 -- the grants agent_writer never received
# ---------------------------------------------------------------------------


def test_agent_writer_can_reach_the_hook_and_both_comparison_helpers(
    cluster: dict[str, Any],
) -> None:
    """A reach question, so it sets the role and tries it (ADR 0134).

    **This is the assertion D475 is about.** `grep -c agent_writer` on migration
    0018 returns zero: the role received no USAGE on `app_private` and no EXECUTE
    on the hook or on either comparison helper, because 0018 named the five
    request roles that existed when it was written. Without 0019's grants, the
    first request naming `agent_writer` is refused by `permission denied for
    function postgrest_pre_request` rather than by the boundary -- D417's shape,
    one session later, in a file whose own text states the rule.

    EXECUTE requires schema USAGE, and the hook runs AFTER the role switch
    (measured in 0008), so it runs as this role.
    """
    hook = as_role(cluster, "agent_writer", "SELECT app_private.postgrest_pre_request();")
    assert hook.returncode == 0, (
        f"agent_writer cannot execute the pre-request hook: {hook.stderr[:300]}"
    )

    agent_helper = as_role(
        cluster,
        "agent_writer",
        "SELECT app_private.agent_claims_are_current("
        "gen_random_uuid(), 'nobody', ARRAY['x']::text[], 1) IS NULL;",
    )
    assert agent_helper.returncode == 0, (
        f"agent_writer cannot execute agent_claims_are_current: {agent_helper.stderr[:300]}"
    )

    human_helper = as_role(
        cluster,
        "agent_writer",
        "SELECT app_private.auth_claims_are_current("
        "gen_random_uuid(), 'nobody', ARRAY['x']::text[], 1, 1) IS NOT NULL;",
    )
    assert human_helper.returncode == 0, (
        f"agent_writer cannot execute auth_claims_are_current: {human_helper.stderr[:300]}"
    )


def test_every_request_role_can_reach_the_hook(cluster: dict[str, Any]) -> None:
    """The rule 0018 states, asserted over the whole set rather than the new one.

    `role` and `token_use` are independent claims, so every combination of
    physical role and hook branch is a reachable request (D417). A role that can
    be named by a token and cannot run the hook is refused with a 42501 that
    reaches the caller as a different failure from every other refusal the hook
    issues.

    **Read from the product's constant, not written down.** The first version of
    this test listed the five roles by hand, which is the copy D301, D416 and
    D492 are all about -- and it was written in the run immediately after D492
    was found, which is how durable that habit is.
    """
    for role_key in _bootstrap_module().AUTHENTICATOR_REQUEST_ROLES:
        result = as_role(cluster, role_key, "SELECT app_private.postgrest_pre_request();")
        assert result.returncode == 0, (
            f"{role_key} cannot execute the pre-request hook: {result.stderr[:200]}"
        )


def test_the_roles_granted_the_hook_are_exactly_the_request_roles(
    cluster: dict[str, Any],
) -> None:
    """The other direction, and it is the one with teeth (D492).

    The test above reads `AUTHENTICATOR_REQUEST_ROLES` and asks whether each of
    those roles can run the hook. A set derived entirely from the product cannot
    refuse a bad edit to the product, so on its own it would stay green if a role
    were dropped from the constant while keeping every grant a request role has.

    This compares the two independent products -- what the **migrations grant**,
    read from the catalog, against what the **bootstrap plane activates** -- and
    requires them equal. Dropping `agent_writer` from the constant now fails
    here, because 0019's grant is still in the catalog and the role is no longer
    in the set; so does granting the hook to a role nothing can assume.

    A grant question, so it reads the catalog rather than asking
    `has_function_privilege`, which would answer for membership (ADR 0134).
    """
    result = su(
        cluster,
        """
        SELECT coalesce(string_agg(DISTINCT grantee.rolname, ',' ORDER BY grantee.rolname), '')
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace AND n.nspname = 'app_private'
        CROSS JOIN LATERAL aclexplode(p.proacl) acl
        JOIN pg_roles grantee ON grantee.oid = acl.grantee
        WHERE p.proname = 'postgrest_pre_request' AND acl.privilege_type = 'EXECUTE';
        """,
    )
    assert result.returncode == 0, result.stderr

    by_name = {name: suffix for suffix, name in cluster["roles"].items()}
    holders = {by_name[name] for name in result.stdout.strip().split(",") if name in by_name}
    # The owner appears in its own function's ACL and is not a request role.
    holders -= {"object_owner"}

    request_roles = set(_bootstrap_module().AUTHENTICATOR_REQUEST_ROLES)
    assert holders == request_roles, (
        f"the roles GRANTED EXECUTE on the pre-request hook are {sorted(holders)}; the "
        f"roles the bootstrap plane activates are {sorted(request_roles)}. A grant to a "
        "role no token can name buys nothing, and a request role without the grant is "
        "refused by permission denied rather than by the boundary (D475, D417)"
    )


# ---------------------------------------------------------------------------
# SEC-PARAM-001's mechanism -- identity is the GUC's, never an argument's
# ---------------------------------------------------------------------------


def test_the_audit_identity_comes_from_the_guc_and_not_from_a_parameter(
    cluster: dict[str, Any],
) -> None:
    """The function's only arguments are a tool name, a request id and a document.

    There is no argument for a caller to put a principal in, so a stored identity
    equal to the GUC is not a validation result -- it is the only thing the
    function could have written.
    """
    agent = str(uuid.uuid4())
    owner = str(uuid.uuid4())
    written = as_agent(
        cluster,
        "agent_writer",
        agent,
        owner,
        "SELECT api.agent_audit_begin('query_resource', NULL, '{\"a\": 1}'::jsonb);",
    )
    assert written.returncode == 0, written.stderr

    stored = su(
        cluster,
        "SELECT agent_id::text || '|' || owner_id::text || '|' || source::text || '|' "
        "|| outcome::text FROM app_private.agent_audit WHERE tool = 'query_resource';",
    )
    assert stored.returncode == 0, stored.stderr
    assert stored.stdout.strip() == f"{agent}|{owner}|agent_plane|started"


def test_a_caller_without_an_agent_identity_is_refused(cluster: dict[str, Any]) -> None:
    """Defence in depth, and it is asserted rather than assumed.

    `authenticated` holds no EXECUTE on either function, so a human token cannot
    reach them at all. This is the second line: with the grant one day widened by
    accident, the function still refuses rather than writing a row whose principal
    is NULL and finding out from a NOT NULL violation.
    """
    result = as_role(cluster, "agent_writer", "SELECT api.agent_audit_begin('no_identity');")
    assert result.returncode != 0, "a caller with no agent identity opened an audit record"
    assert "AP403" in (result.stderr or ""), result.stderr


def test_an_agent_cannot_close_another_agents_record(cluster: dict[str, Any]) -> None:
    """`complete` is scoped to the calling agent's own rows.

    It returns false rather than raising, so the refusal cannot be used to learn
    whether a record id exists -- a raise here would make the function an oracle
    for other agents' ids, which is the shape 0018 refused for
    `mcp_agent_context`.
    """
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    owner = str(uuid.uuid4())
    opened = as_agent(
        cluster,
        "agent_writer",
        first,
        owner,
        "SELECT api.agent_audit_begin('mine');",
    )
    assert opened.returncode == 0, opened.stderr
    record = su(
        cluster, "SELECT id::text FROM app_private.agent_audit WHERE tool = 'mine';"
    ).stdout.strip()
    assert record

    stolen = as_agent(
        cluster,
        "agent_writer",
        second,
        owner,
        f"SELECT api.agent_audit_complete('{record}', 'served', 1, 1);",
    )
    assert stolen.returncode == 0, stolen.stderr
    assert "f" in stolen.stdout.split(), (
        f"a second agent closed the first's record: {stolen.stdout}"
    )

    still_open = su(
        cluster, "SELECT outcome::text FROM app_private.agent_audit WHERE tool = 'mine';"
    )
    assert still_open.stdout.strip() == "started"


def test_complete_refuses_the_committed_outcome(cluster: dict[str, Any]) -> None:
    """`committed` belongs to a `database` row, which this function does not write.

    Accepting it would let the agent plane label its own attempt as a change that
    happened -- and the two records exist precisely because those are different
    claims.
    """
    agent, owner = str(uuid.uuid4()), str(uuid.uuid4())
    opened = as_agent(cluster, "agent_writer", agent, owner, "SELECT api.agent_audit_begin('c');")
    assert opened.returncode == 0, opened.stderr
    record = su(
        cluster, "SELECT id::text FROM app_private.agent_audit WHERE tool = 'c';"
    ).stdout.strip()

    result = as_agent(
        cluster,
        "agent_writer",
        agent,
        owner,
        f"SELECT api.agent_audit_complete('{record}', 'committed');",
    )
    assert result.returncode != 0, "the agent plane closed a record as 'committed'"
    assert "AP422" in (result.stderr or ""), result.stderr


# ---------------------------------------------------------------------------
# D489 -- what a row written inside the transaction it describes can claim
# ---------------------------------------------------------------------------


def test_a_committed_agent_write_leaves_a_database_row(cluster: dict[str, Any]) -> None:
    """The write RPC records its own change, so no route can skip it (D480)."""
    agent, owner = str(uuid.uuid4()), str(uuid.uuid4())
    written = as_agent(
        cluster, "agent_writer", agent, owner, "SELECT api.create_note('audited', 'body');"
    )
    assert written.returncode == 0, written.stderr

    row = su(
        cluster,
        "SELECT source::text || '|' || outcome::text || '|' || agent_id::text "
        "FROM app_private.agent_audit WHERE tool = 'create_note';",
    )
    assert row.stdout.strip() == f"database|committed|{agent}"


def test_a_failed_agent_write_leaves_no_database_row(cluster: dict[str, Any]) -> None:
    """**D489, and it is the finding that shaped the table.**

    The RPC raises, the transaction aborts, and the audit row inserted before the
    raise goes with it. There is no arrangement of exception blocks or
    subtransactions that keeps it -- a handler discards its savepoint just as
    surely. So a `database` row records a committed change and can record nothing
    else, and a failed attempt is recorded by the agent plane's own record alone.

    The paired positive above is what makes this mean something: without it, zero
    rows would also be what a table nothing ever writes to looks like.
    """
    agent, owner = str(uuid.uuid4()), str(uuid.uuid4())
    absent = str(uuid.uuid4())
    failed = as_agent(
        cluster,
        "agent_writer",
        agent,
        owner,
        f"SELECT api.update_task_status('{absent}', 'pending', 'completed');",
    )
    assert failed.returncode != 0, "updating a task that does not exist succeeded"
    assert "AP404" in (failed.stderr or ""), failed.stderr

    rows = su(
        cluster,
        "SELECT count(*) FROM app_private.agent_audit WHERE tool = 'update_task_status';",
    )
    assert rows.stdout.strip() == "0", (
        "a failed write left an audit row. The RAISE aborts the transaction and the "
        "row goes with it (D489); if this is ever non-zero the table is being written "
        "by something outside the transaction it describes"
    )


def test_a_human_write_leaves_no_audit_row(cluster: dict[str, Any]) -> None:
    """The conditional fires on `app.agent_id`, which the hook sets only for an agent.

    A human caller's behaviour is unchanged by 0019 -- same rows, same errors, no
    audit row -- and that is asserted rather than reasoned about, because 0019
    replaced both write RPCs and the whole point of `CREATE OR REPLACE` here was
    that everything except the conditional stays 0007's.
    """
    owner = str(uuid.uuid4())
    written = su(
        cluster,
        f"""
        BEGIN;
        SET LOCAL ROLE "{cluster["roles"]["authenticated"]}";
        SELECT set_config('app.user_id', '{owner}', true);
        SELECT api.create_note('by a human', 'body');
        COMMIT;
        """,
    )
    assert written.returncode == 0, written.stderr

    rows = su(
        cluster,
        "SELECT count(*) FROM app_private.agent_audit WHERE tool = 'create_note' "
        f"AND owner_id = '{owner}';",
    )
    assert rows.stdout.strip() == "0", "a human write left an agent audit row"


# ---------------------------------------------------------------------------
# Migration 0020 -- the one reader, and the grant 0019 did not make (ADR 0142)
#
# **Why this migration exists is D501.** 0019 created the table and two indexes
# whose own comment names their reader -- "The admin query endpoint (Run 7)
# reads by owner and by agent, most recent first. Both indexes exist for that
# one reader; neither is speculative" -- and created neither the reader nor a
# grant. `auth_service` holds schema USAGE on `app_private` and nothing else, so
# `GET /admin/audit` had no statement it was allowed to send. CLAUDE.md section 6
# question 5, asked of 0019: which of this decision's callers got it? The
# indexes did.
#
# Every assertion below keeps the two kinds of question apart (ADR 0134): a
# GRANT question reads `aclexplode`, and a REACH question sets the role and
# tries it.
# ---------------------------------------------------------------------------

READER = "auth_list_agent_audit"


def _reader_acl(cluster: dict[str, Any]) -> list[str]:
    """Every grantee in the reader's ACL, by name, excluding its owner."""
    result = su(
        cluster,
        f"""
        SELECT coalesce(string_agg(DISTINCT grantee.rolname, ',' ORDER BY grantee.rolname), '')
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace AND n.nspname = 'app_private'
        CROSS JOIN LATERAL aclexplode(p.proacl) acl
        JOIN pg_roles grantee ON grantee.oid = acl.grantee
        WHERE p.proname = '{READER}'
          AND grantee.rolname <> current_user;
        """,
    )
    assert result.returncode == 0, result.stderr
    return [name for name in result.stdout.strip().split(",") if name]


def test_the_audit_reader_is_granted_to_the_auth_service_and_to_nobody_else(
    cluster: dict[str, Any],
) -> None:
    """A grant question, so it reads the catalog (ADR 0134).

    The omissions are the design and each has its own reason. Not
    `project_admin`: the scope is checked at the endpoint, and a request role
    holding EXECUTE could reach the record over PostgREST with no scope check at
    all. Not either agent role: ADR 0135's stated residual threat is that an
    agent can add noise to its own record under a true identity, and reading the
    record back is not part of that threat. Not `api_documentation`: the
    function is not in `api` and could not be served, and a grant is the one
    thing that could change that.

    An equality and not a containment. `set(holders) <= {expected}` would pass
    for a function granted to nobody at all, which is a different release.

    **The owner is subtracted rather than expected, and that is a measurement.**
    `aclexplode(proacl)` reports the function's OWNER as a grantee: PostgreSQL
    materialises `owner=X/owner` in the ACL as soon as any explicit grant forces
    one to exist. That entry is not a decision anybody took and asserting it
    would be asserting PostgreSQL's bookkeeping. The table twin above compares
    `<= {owner}` for the same reason.
    """
    owner = cluster["roles"]["object_owner"]
    holders = set(_reader_acl(cluster)) - {owner}
    assert holders == {cluster["roles"]["auth_service"]}, (
        f"app_private.{READER} is granted to {sorted(holders)} besides its owner. "
        "One grantee, and every omission has a reason (ADR 0142)"
    )


def test_the_audit_reader_is_not_executable_by_public(cluster: dict[str, Any]) -> None:
    """D57, re-measured as D262, and again here.

    A newly created function is EXECUTABLE BY PUBLIC the moment it exists, and
    `ALTER DEFAULT PRIVILEGES` -- the form that reads like the fix -- records
    nothing at all for functions. The targeted `REVOKE ... FROM PUBLIC` in 0020
    is what removes it, and this is the assertion that the revoke ran.
    """
    result = su(
        cluster,
        f"""
        SELECT count(*)
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace AND n.nspname = 'app_private'
        CROSS JOIN LATERAL aclexplode(p.proacl) acl
        WHERE p.proname = '{READER}' AND acl.grantee = 0;
        """,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0", f"PUBLIC holds EXECUTE on app_private.{READER}"


def test_the_audit_reader_is_a_stable_definer_with_a_pinned_search_path(
    cluster: dict[str, Any],
) -> None:
    """Three properties of one function, each load-bearing for a different reason.

    SECURITY DEFINER is what lets a role holding no privilege on the table read
    it. The pinned `search_path` is what stops a caller-controlled path from
    resolving `agent_audit` somewhere else -- the standing rule for every
    definer in this schema. And `provolatile = 's'` says it writes nothing,
    which is worth asserting rather than inheriting: ADR 0136's whole category
    exists because PostgREST refuses a WRITING function over GET, and a reader
    that ever became volatile-and-writing would be a second write path to an
    append-only table.
    """
    result = su(
        cluster,
        f"""
        SELECT p.prosecdef, p.provolatile,
               coalesce(array_to_string(p.proconfig, ','), '')
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace AND n.nspname = 'app_private'
        WHERE p.proname = '{READER}';
        """,
    )
    assert result.returncode == 0, result.stderr
    secdef, volatility, config = result.stdout.strip().split("|")
    assert secdef == "t", f"app_private.{READER} is not SECURITY DEFINER"
    assert volatility == "s", (
        f"app_private.{READER} is {volatility!r}, not STABLE. A reader that writes is a "
        "second write path to a table whose own COMMENT says the definer functions are "
        "the only paths in"
    )
    assert config == "search_path=pg_catalog, pg_temp", f"unpinned search_path: {config!r}"


def test_the_auth_service_reads_the_record_only_through_the_reader(
    cluster: dict[str, Any],
) -> None:
    """A reach question, both halves (ADR 0134).

    The negative half alone would pass on a cluster where the function does not
    exist either, and a role that can reach nothing looks identical to a perfect
    boundary. So the positive half runs first and has to succeed.
    """
    reachable = as_role(
        cluster,
        "auth_service",
        f"SELECT count(*) FROM app_private.{READER}(NULL, NULL, 10)",
    )
    assert reachable.returncode == 0, (
        f"auth_service cannot call app_private.{READER}, which is the only statement "
        f"GET /admin/audit is allowed to send: {reachable.stderr[:300]}"
    )

    denied = as_role(cluster, "auth_service", "SELECT count(*) FROM app_private.agent_audit")
    assert denied.returncode != 0, "auth_service can read app_private.agent_audit directly"
    assert "permission denied" in denied.stderr


def test_no_request_role_can_execute_the_audit_reader(cluster: dict[str, Any]) -> None:
    """The refusal that matters most, and it is about the agent roles.

    An agent must not read the record that exists to attribute it. The
    administrative path to it is a scope on a human's token, checked in the auth
    service; a request role holding EXECUTE here would reach the same rows over
    PostgREST with no scope check anywhere.

    Over **every** request role, read from the product's own constant rather
    than restated -- D492 is what a fifth copy of that list costs, and it was
    found in this session.
    """
    request_roles = _bootstrap_module().AUTHENTICATOR_REQUEST_ROLES
    assert request_roles, "no request role to refuse; this test would be vacuous"
    for role_key in request_roles:
        result = as_role(
            cluster, role_key, f"SELECT count(*) FROM app_private.{READER}(NULL, NULL, 10)"
        )
        assert result.returncode != 0, (
            f"{role_key} can execute app_private.{READER}. An agent reading the audit "
            "record is not part of ADR 0135's threat model and must not become part of it"
        )
        assert "permission denied" in result.stderr


def test_the_reader_returns_the_most_recent_first_and_breaks_ties_by_id(
    cluster: dict[str, Any],
) -> None:
    """The tiebreak is not decoration, and this is what would notice its absence.

    `started_at` defaults to `now()`, which is TRANSACTION time, so rows written
    by one transaction share it to the microsecond. Without the `id DESC`
    tiebreak their order under a LIMIT is arbitrary, and an arbitrary order under
    a LIMIT is a row that appears in no page at all. Three rows are written in
    ONE transaction here precisely so they collide.
    """
    agent = str(uuid.uuid4())
    owner = str(uuid.uuid4())
    written = as_agent(
        cluster,
        "agent_reader",
        agent,
        owner,
        """
        SELECT api.agent_audit_begin('query_resource');
        SELECT api.agent_audit_begin('run_report');
        SELECT api.agent_audit_begin('list_resources');
        """,
    )
    assert written.returncode == 0, written.stderr

    collided = su(
        cluster,
        f"SELECT count(DISTINCT started_at) FROM app_private.agent_audit "
        f"WHERE agent_id = '{agent}'",
    )
    assert collided.stdout.strip() == "1", (
        "the three rows did not share a started_at, so this test is not measuring the "
        f"tiebreak it names (distinct values: {collided.stdout.strip()})"
    )

    def page(limit: int) -> list[str]:
        result = as_role(
            cluster,
            "auth_service",
            f"SELECT id::text FROM app_private.{READER}('{agent}', NULL, {limit})",
        )
        assert result.returncode == 0, result.stderr
        return [line for line in result.stdout.strip().splitlines() if line]

    full = page(10)
    assert len(full) == 3, f"expected three rows, got {full}"
    # The behavioural half: every prefix of the full ordering is what a shorter
    # LIMIT returns. **Measured to be insufficient on its own** -- Run 7's
    # battery arm A7 dropped `, r.id DESC` from the migration and this stayed
    # green, because PostgreSQL's sort is deterministic for three rows. It is
    # kept because it catches what the structural half below cannot: a reader
    # that returns rows unordered, or newest-LAST.
    assert page(2) == full[:2]
    assert page(1) == full[:1]

    # The structural half, and it is the one that holds the tiebreak. ADR 0134's
    # division applied to an ordering: what the function IS is a question for the
    # catalog, and what it DOES is a question for calling it. `pg_get_functiondef`
    # returns the deployed definition, so this is not a scan of the template --
    # it is what the cluster actually has.
    definition = su(
        cluster,
        "SELECT pg_get_functiondef(p.oid) FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid = p.pronamespace AND n.nspname = 'app_private' "
        f"WHERE p.proname = '{READER}';",
    )
    assert definition.returncode == 0, definition.stderr
    collapsed = " ".join(definition.stdout.split())
    assert "ORDER BY r.started_at DESC, r.id DESC" in collapsed, (
        "the deployed reader has no id tiebreak. started_at defaults to now(), which is "
        "TRANSACTION time, so two rows written by one transaction share it exactly -- and "
        "an arbitrary order under a LIMIT is a row that appears in no page. The prefix "
        f"assertions above cannot see this (Run 7 battery A7): {collapsed[-300:]}"
    )


def test_the_reader_filters_narrow_and_do_not_authorize(cluster: dict[str, Any]) -> None:
    """Both filters optional, and the unfiltered read is the widest one.

    This is what makes `agent_id` and `owner_id` acceptable as parameters at all
    while the agent plane's own audit functions take no identity argument
    (SEC-PARAM-001, D473). There, a parameter naming a principal WOULD be the
    authority. Here the caller has already been authorized to read the whole
    record by a scope, so a filter can only ever return less.
    """
    mine, other = str(uuid.uuid4()), str(uuid.uuid4())
    owner = str(uuid.uuid4())
    for agent in (mine, other):
        result = as_agent(
            cluster, "agent_reader", agent, owner, "SELECT api.agent_audit_begin('query_resource');"
        )
        assert result.returncode == 0, result.stderr

    def rows(agent_filter: str, owner_filter: str) -> int:
        result = as_role(
            cluster,
            "auth_service",
            f"SELECT count(*) FROM app_private.{READER}({agent_filter}, {owner_filter}, 500)",
        )
        assert result.returncode == 0, result.stderr
        return int(result.stdout.strip())

    unfiltered = rows("NULL", "NULL")
    by_owner = rows("NULL", f"'{owner}'")
    by_agent = rows(f"'{mine}'", "NULL")
    both = rows(f"'{mine}'", f"'{owner}'")

    assert by_agent == 1, f"the agent filter returned {by_agent} rows, not one"
    assert by_owner >= 2, "the owner filter lost a row it should have kept"
    assert both == 1
    assert unfiltered >= by_owner >= both, (
        "a filter returned MORE than the unfiltered read, which would make it a widening "
        f"rather than a narrowing: {unfiltered} / {by_owner} / {both}"
    )
    # The one arrangement that would make the three numbers above meaningless.
    assert rows(f"'{mine}'", f"'{uuid.uuid4()!s}'") == 0, (
        "a filter naming an owner with no rows returned some, so the filters are not "
        "conjunctive and the numbers above prove nothing"
    )


def test_the_reader_applies_the_limit_it_is_given_without_clamping(
    cluster: dict[str, Any],
) -> None:
    """One authority for the bound, and it is the route's (D495, D463).

    The route validates `limit` into its documented range and answers 422
    outside it; this function applies what it is handed. A second clamp here
    would be a second bound over one rule, and the two drift the moment either
    moves. What this asserts is that the second clamp is genuinely absent --
    a clamp at, say, 100 would be invisible until somebody asked for 101.
    """
    agent, owner = str(uuid.uuid4()), str(uuid.uuid4())
    calls = "\n".join(["SELECT api.agent_audit_begin('query_resource');" for _ in range(4)])
    result = as_agent(cluster, "agent_reader", agent, owner, calls)
    assert result.returncode == 0, result.stderr

    def count(limit: int) -> int:
        got = as_role(
            cluster,
            "auth_service",
            f"SELECT count(*) FROM app_private.{READER}('{agent}', NULL, {limit})",
        )
        assert got.returncode == 0, got.stderr
        return int(got.stdout.strip())

    assert count(4) == 4
    assert count(2) == 2, "the limit is not applied"
    assert count(1) == 1
