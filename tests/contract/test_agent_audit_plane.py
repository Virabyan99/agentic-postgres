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
    """A cluster built the way a deploy builds one, with all nineteen applied."""
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
        assert "agent_write_and_audit_plane" in applied_names, (
            f"0019 was not applied; the rendered set is {applied_names}. "
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
