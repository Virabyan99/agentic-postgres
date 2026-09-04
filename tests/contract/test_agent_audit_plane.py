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

#: The migration BEFORE which the fixture seeds a historical refused row, and
#: the agent that row belongs to (D940). Named by the migration's manifest name
#: rather than its number, so a renumbering cannot silently seed nothing.
HISTORICAL_ROW_BEFORE = "agent_audit_denial_taxonomy"
HISTORICAL_AGENT = "d940d940-0000-4000-8000-000000000940"

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
            # **A historical refused row, written BEFORE the taxonomy exists**
            # (D940). Every cluster this fixture ever built was empty when 0027
            # applied, so no proof met the state the deployment was in -- a
            # `refused` row with no reason column to carry one -- and 0027's
            # validated CHECK was refused by PostgreSQL on the first deploy, at
            # step 6, on both projects' worth of history. Seeded as the
            # superuser, because the row is history and not a request.
            if entry["name"] == HISTORICAL_ROW_BEFORE:
                seeded = su(
                    "INSERT INTO app_private.agent_audit "
                    "(source, agent_id, owner_id, tool, outcome) VALUES "
                    f"('agent_plane', '{HISTORICAL_AGENT}', gen_random_uuid(), "
                    "'historical_refusal', 'refused');",
                    database,
                )
                assert seeded.returncode == 0, seeded.stderr
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
    *,
    idempotency_key: str | None = None,
    dry_run: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """A request with the GUCs the pre-request hook would have set.

    One transaction, because `set_config(..., true)` is transaction-local -- each
    `su` call is its own session, so a GUC set in one and read in another would
    be a different measurement entirely (D116/D117 are what that class costs).

    **`request.headers` is set too, since ADR 0181.** An agent write now requires
    an `Idempotency-Key`, refused in the database rather than only in the runtime
    -- 0019 built these functions so that a caller skipping the agent plane still
    leaves an audit row, and the same reasoning covers the guarantee.

    **The default mints a FRESH key per call**, which is what an `as_agent` call
    honestly is: one request. A shared default would make every proof in this
    module a replay of the one before it, and a `None` default would leave every
    existing write proof refused. A proof that is ABOUT replay passes its own key
    and gets the deduplication it is measuring.

    **`dry_run` is a STRING and defaults to absent, not to `"false"`** (ADR
    0182). The database distinguishes an absent header from a present one, and
    the malformed-value proof needs to send `"1"` and `"TRUE"` -- values a bool
    parameter could not express. Absent is the honest default for every proof
    that is not about rehearsal.
    """
    key = idempotency_key if idempotency_key is not None else f"k-{secrets.token_hex(8)}"
    sent = {"idempotency-key": key}
    if dry_run is not None:
        sent["dry-run"] = dry_run
    headers = json.dumps(sent)
    return su(
        cluster,
        f"""
        BEGIN;
        SET LOCAL ROLE "{cluster["roles"][role_key]}";
        SELECT set_config('app.agent_id', '{agent_id}', true);
        SELECT set_config('app.user_id', '{owner_id}', true);
        SELECT set_config('request.headers', '{headers}', true);
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
        "SELECT api.agent_audit_begin('query_resource', NULL, '{\"a\": 1}'::jsonb, NULL, NULL);",
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
    result = as_role(
        cluster,
        "agent_writer",
        "SELECT api.agent_audit_begin('no_identity', NULL, NULL, NULL, NULL);",
    )
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
        "SELECT api.agent_audit_begin('mine', NULL, NULL, NULL, NULL);",
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
        f"SELECT api.agent_audit_complete('{record}', 'served', 1, 1, NULL);",
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
    opened = as_agent(
        cluster,
        "agent_writer",
        agent,
        owner,
        "SELECT api.agent_audit_begin('c', NULL, NULL, NULL, NULL);",
    )
    assert opened.returncode == 0, opened.stderr
    record = su(
        cluster, "SELECT id::text FROM app_private.agent_audit WHERE tool = 'c';"
    ).stdout.strip()

    result = as_agent(
        cluster,
        "agent_writer",
        agent,
        owner,
        f"SELECT api.agent_audit_complete('{record}', 'committed', NULL, NULL, NULL);",
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
        SELECT api.agent_audit_begin('query_resource', NULL, NULL, NULL, NULL);
        SELECT api.agent_audit_begin('run_report', NULL, NULL, NULL, NULL);
        SELECT api.agent_audit_begin('list_resources', NULL, NULL, NULL, NULL);
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
            cluster,
            "agent_reader",
            agent,
            owner,
            "SELECT api.agent_audit_begin('query_resource', NULL, NULL, NULL, NULL);",
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
    calls = "\n".join(
        [
            "SELECT api.agent_audit_begin('query_resource', NULL, NULL, NULL, NULL);"
            for _ in range(4)
        ]
    )
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


# ---------------------------------------------------------------------------
# Migration 0027: what refused, and which contract said so (ADR 0178)
# ---------------------------------------------------------------------------


def test_the_denial_taxonomy_is_in_the_catalog(cluster: dict[str, Any]) -> None:
    """Every member, in the enum's own order, read from the APPLIED cluster.

    `test_denial_taxonomy.py` compares the runtime tuple against the migration
    TEMPLATES, which is a text comparison. This is the other half: the templates
    were applied and the type exists with those members. A template that parsed
    and did not apply would satisfy the first and fail here.

    **The expected list is the runtime's tuple and was a hardcoded string until
    Session 16 Run 7.** That was the FOURTH reader of this taxonomy encoding
    where its members lived — D918 in Run 6, three more in `test_denial_taxonomy`
    at the start of this run, and this one, which the contract suite found after
    those three were repaired. A literal here is a third copy of a list ADR 0002
    says has one authority; chaining cluster → runtime → templates keeps each
    comparison between two different things.
    """
    from app import mcp_errors

    result = su(
        cluster,
        "SELECT string_agg(enumlabel, ',' ORDER BY enumsortorder) FROM pg_enum "
        "JOIN pg_type ON pg_type.oid = pg_enum.enumtypid "
        "WHERE typname = 'agent_denial_reason';",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ",".join(mcp_errors.DENIAL_REASONS), result.stdout


def test_a_refused_record_carries_a_reason_and_no_other_record_may(
    cluster: dict[str, Any],
) -> None:
    """The equivalence CHECK, in both directions, with the control between them.

    **Written as an equivalence rather than two one-way checks** because a
    `served` row carrying a reason is as wrong as a `refused` row without one,
    and stating it once means neither direction can be relaxed while the other
    still looks guarded.

    The control is the first case: a refused row WITH a reason must insert. A
    constraint that refused every insert would satisfy both refusals and mean
    nothing.
    """
    columns = "source, agent_id, owner_id, tool, outcome"
    values = "'agent_plane', gen_random_uuid(), gen_random_uuid(), 't', "

    cases = [
        ("refused with a reason [the CONTROL]", "refused", "scope_not_held", True),
        ("refused with no reason", "refused", None, False),
        ("served with a reason", "served", "scope_not_held", False),
        ("served with no reason", "served", None, True),
    ]
    for label, outcome, reason, expected in cases:
        if reason is None:
            statement = (
                f"INSERT INTO app_private.agent_audit ({columns}) VALUES ({values}'{outcome}');"
            )
        else:
            statement = (
                f"INSERT INTO app_private.agent_audit ({columns}, denial_reason) "
                f"VALUES ({values}'{outcome}', '{reason}');"
            )
        inserted = su(cluster, statement).returncode == 0
        assert inserted is expected, f"{label}: inserted={inserted}, expected={expected}"


def test_a_refused_row_written_before_the_taxonomy_survives_it_and_new_rows_are_still_checked(
    cluster: dict[str, Any],
) -> None:
    """**D940.** The proof that would have stopped Session 16's first deploy.

    The fixture seeded a `refused` row with no reason BEFORE 0027 applied, which
    is the state every deployment with a history is in and no fixture cluster
    ever was. Three things follow, and the third is the control: the row is
    still there with a NULL reason; the constraint exists and is NOT VALID,
    which is why 0027 applied over it; and it is still enforced -- a new
    refused row without a reason is refused, and VALIDATE CONSTRAINT itself
    is refused by the historical row, which proves the exemption is a real
    row and not an absent one.
    """
    historical = su(
        cluster,
        "SELECT outcome::text, denial_reason IS NULL FROM app_private.agent_audit "
        f"WHERE agent_id = '{HISTORICAL_AGENT}';",
    )
    assert historical.returncode == 0, historical.stderr
    assert historical.stdout.strip() == "refused|t", (
        f"the seeded historical row is {historical.stdout!r}; the fixture did not seed it "
        "before the taxonomy applied, so this proof measures an empty cluster (D940)"
    )

    validated = su(
        cluster,
        "SELECT convalidated FROM pg_constraint WHERE conname = 'agent_audit_reason_iff_refused';",
    )
    assert validated.stdout.strip() == "f", (
        f"convalidated is {validated.stdout.strip()!r}. A validated CHECK cannot be added over "
        "a refused row that predates the reason column, which is what the deployment holds"
    )

    refused = su(
        cluster,
        "INSERT INTO app_private.agent_audit (source, agent_id, owner_id, tool, outcome) "
        "VALUES ('agent_plane', gen_random_uuid(), gen_random_uuid(), 't', 'refused');",
    )
    assert refused.returncode != 0, "a NOT VALID constraint stopped checking new rows"
    assert "agent_audit_reason_iff_refused" in refused.stderr

    # The control: the exemption is a real row. Validating would scan it and fail.
    validate = su(
        cluster,
        "ALTER TABLE app_private.agent_audit VALIDATE CONSTRAINT agent_audit_reason_iff_refused;",
    )
    assert validate.returncode != 0, "VALIDATE succeeded, so no historical row was exempt"
    assert "violated by some row" in validate.stderr, validate.stderr


def test_both_audit_functions_moved_to_their_new_arity_and_left_no_overload(
    cluster: dict[str, Any],
) -> None:
    """0027 DROPs before it CREATEs, so exactly one signature may remain.

    A `CREATE` without the `DROP` is the quiet failure: PostgreSQL would keep
    both, a three-argument call would still resolve to the old one, and the new
    columns would be NULL on every row while every proof passed.
    """
    expected = {
        "agent_audit_begin": (
            "p_tool text, p_request_id uuid, p_parameters jsonb, "
            "p_capability_version text, p_contract_hash text"
        ),
        "agent_audit_complete": (
            "p_audit_id uuid, p_outcome text, p_elapsed_ms integer, "
            "p_row_count integer, p_denial_reason text"
        ),
    }
    for name, signature in expected.items():
        result = su(
            cluster,
            "SELECT string_agg(pg_get_function_identity_arguments(p.oid), ' | ') "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            f"WHERE n.nspname = 'api' AND p.proname = '{name}';",
        )
        assert result.returncode == 0, result.stderr
        got = result.stdout.strip()
        assert "|" not in got, f"{name} has more than one signature live: {got}"
        assert got == signature, f"{name} is {got!r}"


def test_the_grants_survived_the_functions_being_replaced(cluster: dict[str, Any]) -> None:
    """A DROP takes its grants with it, and a plane that cannot audit fails closed.

    So this is not bookkeeping: without the re-GRANT, every agent write refuses
    on its own audit record and every agent read logs a warning, on a deployment
    whose migrations all applied cleanly.
    """
    # The type list is written out at both sites rather than held in a variable,
    # and that is not a style choice. ADR 0175's scanner classifies an occurrence
    # as a SIGNATURE when every argument is a bare identifier, so a written-out
    # type list is excluded -- while the same name given a single interpolated
    # placeholder reads as a CALL taking one argument, and fails the guard
    # (D913). Interpolation is what a static scanner cannot see through, and
    # teaching it to ignore any braced argument would blind it to a real call
    # passing one interpolated variable, which is the arity defect ADR 0175
    # exists to catch. The comment says none of this in code shape for the same
    # reason: the scanner reads comments, and it is right to.
    for role_key in ("agent_reader", "agent_writer"):
        result = su(
            cluster,
            f"SELECT has_function_privilege('{cluster['roles'][role_key]}', "
            "'api.agent_audit_begin(text,uuid,jsonb,text,text)', 'EXECUTE');",
        )
        assert result.stdout.strip() == "t", f"{role_key} may not execute begin"

    # The control, and it is the one ADR 0134 insists on: `has_function_privilege`
    # reports privileges held by way of MEMBERSHIP, so it can answer `true` for a
    # role that appears in no ACL entry. A role that should NOT hold this must
    # come back false, or the four assertions above are measuring the instrument.
    denied = su(
        cluster,
        f"SELECT has_function_privilege('{cluster['roles']['anon']}', "
        "'api.agent_audit_begin(text,uuid,jsonb,text,text)', 'EXECUTE');",
    )
    assert denied.stdout.strip() == "f", "anon may execute an audit function"


def test_a_write_records_the_reason_it_refused(cluster: dict[str, Any]) -> None:
    """The whole point, end to end through the functions rather than the table.

    `begin` then `complete('refused', ...)` with a reason, read back. This is the
    path the runtime takes, so it exercises the argument order, the enum cast and
    the branch that refuses a mismatched pair -- none of which a direct INSERT
    would touch.
    """
    agent, owner = str(uuid.uuid4()), str(uuid.uuid4())
    opened = as_agent(
        cluster,
        "agent_writer",
        agent,
        owner,
        "SELECT api.agent_audit_begin('create_note', NULL, NULL, '1.2.3', repeat('a', 64));",
    )
    assert opened.returncode == 0, opened.stderr
    record = opened.stdout.strip().splitlines()[-1].strip()

    closed = as_agent(
        cluster,
        "agent_writer",
        agent,
        owner,
        f"SELECT api.agent_audit_complete('{record}', 'refused', 5, NULL, 'scope_not_held');",
    )
    assert closed.returncode == 0, closed.stderr
    assert closed.stdout.strip().splitlines()[-1].strip() == "t"

    row = su(
        cluster,
        "SELECT outcome || '|' || denial_reason || '|' || capability_version "
        f"|| '|' || contract_hash FROM app_private.agent_audit WHERE id = '{record}';",
    )
    assert row.stdout.strip() == f"refused|scope_not_held|1.2.3|{'a' * 64}", row.stdout


def test_complete_refuses_a_reason_that_does_not_match_the_outcome(
    cluster: dict[str, Any],
) -> None:
    """Refused BEFORE the UPDATE, with this repository's own errcode.

    ADR 0139's rule about translating a refusal rather than relaying one: the
    table's CHECK would refuse it too, and that arrives as a constraint name
    inside an audit call -- which the write path treats as `audit_unavailable`
    and fails closed on. A misspelled pair would then read as "the audit table
    is broken", which is the wrong diagnosis.
    """
    agent, owner = str(uuid.uuid4()), str(uuid.uuid4())
    opened = as_agent(
        cluster,
        "agent_writer",
        agent,
        owner,
        "SELECT api.agent_audit_begin('create_note', NULL, NULL, NULL, NULL);",
    )
    record = opened.stdout.strip().splitlines()[-1].strip()

    for outcome, reason in (("served", "'scope_not_held'"), ("refused", "NULL")):
        result = as_agent(
            cluster,
            "agent_writer",
            agent,
            owner,
            f"SELECT api.agent_audit_complete('{record}', '{outcome}', 1, 1, {reason});",
        )
        assert result.returncode != 0, f"{outcome} with {reason} was accepted"
        assert "AP422" in result.stderr, result.stderr

    # The control: the matching pair closes it, so the two refusals above are
    # about the pairing and not about the record being unreachable.
    ok = as_agent(
        cluster,
        "agent_writer",
        agent,
        owner,
        f"SELECT api.agent_audit_complete('{record}', 'served', 1, 1, NULL);",
    )
    assert ok.returncode == 0, ok.stderr
    assert ok.stdout.strip().splitlines()[-1].strip() == "t"


# ---------------------------------------------------------------------------
# Migration 0028: the fifth budget (ADR 0180)
# ---------------------------------------------------------------------------


def _returned(result: Any) -> str:
    """The statement's own output from an `as_agent` call.

    `as_agent` sets two GUCs with `set_config(..., true)` inside the transaction,
    and `set_config` RETURNS the value it set -- so the agent id and the owner id
    precede the result on stdout. Reading the whole buffer compares three uuids
    against whatever was expected, which is what the first draft of the quota
    proofs did.
    """
    # **`.strip()` before `.splitlines()` deletes the answer** when the answer
    # is NULL. psql prints an empty line for a NULL scalar; stripping the buffer
    # removes it, and `[-1]` then returns the OWNER ID left behind by the second
    # `set_config` -- a plausible uuid, which is why three proofs reported that a
    # correctly-refusing function had returned a record id (D908).
    #
    # The function was right the whole time: `RAISE NOTICE` inside it read
    # `bound=2 used=3 over=t` on the call this helper described as served.
    lines = result.stdout.splitlines()
    return lines[-1].strip() if lines else ""


def _quota_agent(cluster: dict[str, Any], *, calls: int, window: int) -> tuple[str, str]:
    """One agent with a quota, and its owner. Returns (agent_id, owner_id)."""
    owner = str(uuid.uuid4())
    agent = str(uuid.uuid4())
    su(
        cluster,
        f"INSERT INTO app_private.users "
        f"(id, username, display_name, role_name, scopes, status) VALUES "
        f"('{owner}', 'u{agent[:8]}', 'Quota Owner', 'apg_authenticated', "
        f"ARRAY['notes:read']::text[], 'active');",
    )
    su(
        cluster,
        "INSERT INTO app_private.agents "
        "(id, name, role_name, scopes, owner_id, quota_calls, quota_window_seconds) "
        f"VALUES ('{agent}', 'quota-{agent[:8]}', 'r', ARRAY['notes:read']::text[], "
        f"'{owner}', {calls}, {window});",
    )
    return agent, owner


def test_an_agent_without_a_quota_is_unbounded(cluster: dict[str, Any]) -> None:
    """**The control for every arm below**, and the state the deployment is in.

    Both columns are NULL for every agent that exists today, and NULL means
    unbounded rather than zero -- inventing a number for agents somebody already
    issued would be a policy nobody chose (ADR 0180).
    """
    owner = str(uuid.uuid4())
    agent = str(uuid.uuid4())
    su(
        cluster,
        f"INSERT INTO app_private.users "
        f"(id, username, display_name, role_name, scopes, status) VALUES "
        f"('{owner}', 'u{agent[:8]}', 'Quota Owner', 'apg_authenticated', "
        f"ARRAY['notes:read']::text[], 'active');",
    )
    su(
        cluster,
        "INSERT INTO app_private.agents (id, name, role_name, scopes, owner_id) VALUES "
        f"('{agent}', 'unbounded-{agent[:8]}', 'r', ARRAY['notes:read']::text[], '{owner}');",
    )

    # **The control must verify it built its own condition** (D605). Without
    # this the test passed with no agent row at all: `begin` finds no row, reads
    # no bound, and takes the unbounded path -- so "an agent without a quota is
    # unbounded" was being demonstrated by an agent that did not exist.
    existing = su(cluster, f"SELECT count(*) FROM app_private.agents WHERE id = '{agent}';")
    assert existing.stdout.strip() == "1", "the fixture did not create the agent it tests"

    for _ in range(5):
        opened = as_agent(
            cluster,
            "agent_reader",
            agent,
            owner,
            "SELECT api.agent_audit_begin('query_resource', NULL, NULL, NULL, NULL);",
        )
        assert opened.returncode == 0, opened.stderr
        assert _returned(opened), "an unbounded agent was refused"

    counted = su(
        cluster, f"SELECT count(*) FROM app_private.agent_quota WHERE agent_id = '{agent}';"
    )
    assert counted.stdout.strip() == "0", "an unbounded agent has a counter row"


def test_a_quota_refuses_the_call_after_the_bound_and_records_it(
    cluster: dict[str, Any],
) -> None:
    """The whole of `AGT-QUOTA-001`'s offline half, through the function.

    The refusal is a NULL return rather than a raise, because a RAISE would roll
    back the audit row written in the same transaction (D489) and leave the
    denial unrecorded -- which is the one thing ADR 0141 put `begin` before the
    scope check to prevent.
    """
    agent, owner = _quota_agent(cluster, calls=2, window=3600)

    for attempt in (1, 2):
        opened = as_agent(
            cluster,
            "agent_reader",
            agent,
            owner,
            "SELECT api.agent_audit_begin('query_resource', NULL, NULL, NULL, NULL);",
        )
        assert _returned(opened), f"call {attempt} was refused inside the bound"

    third = as_agent(
        cluster,
        "agent_reader",
        agent,
        owner,
        "SELECT api.agent_audit_begin('query_resource', NULL, NULL, NULL, NULL);",
    )
    assert third.returncode == 0, f"the refusal raised instead of returning NULL: {third.stderr}"
    assert _returned(third) == "", f"the third call returned {_returned(third)!r}, not NULL"

    rows = su(
        cluster,
        "SELECT outcome || '/' || coalesce(denial_reason::text, '-') "
        f"FROM app_private.agent_audit WHERE agent_id = '{agent}' ORDER BY started_at;",
    )
    assert rows.stdout.split() == ["started/-", "started/-", "refused/budget_exceeded"], (
        f"the records read {rows.stdout.split()}"
    )

    closed = su(
        cluster,
        "SELECT count(*) FROM app_private.agent_audit "
        f"WHERE agent_id = '{agent}' AND outcome = 'refused' AND completed_at IS NOT NULL;",
    )
    assert closed.stdout.strip() == "1", (
        "the refused record is not complete, so it reads as a call still in flight"
    )


def test_a_refused_call_consumes_its_quota(cluster: dict[str, Any]) -> None:
    """Deliberate, and the opposite is the tempting answer (ADR 0180).

    `begin` runs before the scope check, so the count is taken before anything
    knows whether the call will succeed -- and a caller hammering a capability it
    may not use is exactly what a rate limit is for. A quota counting only
    successes would be no bound at all on the traffic that matters most.
    """
    agent, owner = _quota_agent(cluster, calls=1, window=3600)

    for _ in range(3):
        as_agent(
            cluster,
            "agent_reader",
            agent,
            owner,
            "SELECT api.agent_audit_begin('query_resource', NULL, NULL, NULL, NULL);",
        )

    counted = su(cluster, f"SELECT calls FROM app_private.agent_quota WHERE agent_id = '{agent}';")
    assert counted.stdout.strip() == "3", (
        f"the counter reads {counted.stdout.strip()}; the two refused calls did not consume it"
    )


def test_the_window_is_fixed_and_a_new_one_starts_clean(cluster: dict[str, Any]) -> None:
    """Windows are epoch-aligned and fixed rather than sliding.

    A sliding window needs the timestamps of individual calls, which is a second
    copy of what `agent_audit` already records.

    **The rig verifies it built its condition** (D605), because it cannot control
    the clock: a call costs roughly 200 ms through `docker exec`, so two calls
    against a short window straddle the boundary often enough to matter, and the
    first version of this failed intermittently for exactly that reason. So the
    two same-window calls are RETRIED until the counter proves they shared a
    window, and the assertion runs only then.
    """
    import time as _time

    agent, owner = _quota_agent(cluster, calls=1, window=2)

    def call() -> Any:
        return as_agent(
            cluster,
            "agent_reader",
            agent,
            owner,
            "SELECT api.agent_audit_begin('query_resource', NULL, NULL, NULL, NULL);",
        )

    for _attempt in range(4):
        call()
        refused = call()
        shared = su(
            cluster, f"SELECT calls FROM app_private.agent_quota WHERE agent_id = '{agent}';"
        ).stdout.strip()
        if shared == "2":
            break
        _time.sleep(2.2)  # the pair straddled a boundary; start again in a fresh one
    else:  # pragma: no cover -- four straddles in a row
        pytest.fail("could not get two calls into one window; the rig cannot construct its case")

    assert _returned(refused) == "", (
        f"the second call in one window was not refused (counter read {shared})"
    )

    _time.sleep(2.2)
    after = as_agent(
        cluster,
        "agent_reader",
        agent,
        owner,
        "SELECT api.agent_audit_begin('query_resource', NULL, NULL, NULL, NULL);",
    )
    assert _returned(after), "a new window did not start clean"

    # **One row, not two** (D910). The boundary RESETS the count rather than
    # adding a row, so the table is bounded by the number of agents and there is
    # nothing to prune -- which is why ADR 0180's retention section describes a
    # question that no longer exists.
    rows = su(
        cluster,
        f"SELECT count(*) FROM app_private.agent_quota WHERE agent_id = '{agent}';",
    )
    assert int(rows.stdout.strip()) == 1, (
        f"{rows.stdout.strip()} row(s) for one agent; the window boundary added a row "
        "instead of resetting, which is the shape that needs a pruner"
    )
    counted = su(cluster, f"SELECT calls FROM app_private.agent_quota WHERE agent_id = '{agent}';")
    assert counted.stdout.strip() == "1", (
        f"the new window carried {counted.stdout.strip()} calls forward; it must start clean"
    )


def test_a_bound_without_a_window_is_refused_by_the_catalog(cluster: dict[str, Any]) -> None:
    """Neither or both. Either alone reads as a quota that is configured."""
    owner = str(uuid.uuid4())
    agent = str(uuid.uuid4())
    su(
        cluster,
        f"INSERT INTO app_private.users "
        f"(id, username, display_name, role_name, scopes, status) VALUES "
        f"('{owner}', 'u{agent[:8]}', 'Quota Owner', 'apg_authenticated', "
        f"ARRAY['notes:read']::text[], 'active');",
    )

    for calls, window in (("5", "NULL"), ("NULL", "60")):
        result = su(
            cluster,
            "INSERT INTO app_private.agents "
            "(id, name, role_name, scopes, owner_id, quota_calls, quota_window_seconds) "
            f"VALUES (gen_random_uuid(), 'half-{agent[:8]}', 'r', "
            f"ARRAY['notes:read']::text[], '{owner}', {calls}, {window});",
        )
        assert result.returncode != 0, f"calls={calls} window={window} was accepted"

    # The control: both together insert, so the two refusals are about the pair
    # and not about the row being unacceptable for some other reason.
    both = su(
        cluster,
        "INSERT INTO app_private.agents "
        "(id, name, role_name, scopes, owner_id, quota_calls, quota_window_seconds) "
        f"VALUES ('{agent}', 'whole-{agent[:8]}', 'r', ARRAY['notes:read']::text[], "
        f"'{owner}', 5, 60);",
    )
    assert both.returncode == 0, both.stderr


def test_no_role_holds_any_privilege_on_the_quota_table(cluster: dict[str, Any]) -> None:
    """0019's rule for `agent_audit`, applied to the counter.

    A counter an agent could read is a counter an agent could reason about
    evading, and the only path in is the definer function.
    """
    for role_key in ("agent_reader", "agent_writer", "authenticated", "anon"):
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            granted = su(
                cluster,
                f"SELECT has_table_privilege('{cluster['roles'][role_key]}', "
                f"'app_private.agent_quota', '{privilege}');",
            )
            assert granted.stdout.strip() == "f", f"{role_key} holds {privilege} on the quota table"


def test_a_spent_quota_survives_a_restart(cluster: dict[str, Any]) -> None:
    """`AGT-QUOTA-001`'s own words: the bound **survives a process restart**.

    This is what makes the fifth budget different from ADR 0129's four. Rows,
    bytes and elapsed time are decided inside one call; concurrency is a
    semaphore in one process and is *gone* when that process dies. A quota that
    reset on restart would be a bound an agent could clear by waiting for a
    deploy.

    The database is restarted rather than the runtime, and that is the stronger
    arm: the state lives in the catalog, so what has to survive is a real
    shutdown and recovery, not a Python object going out of scope.
    """
    agent, owner = _quota_agent(cluster, calls=1, window=3600)

    first = as_agent(
        cluster,
        "agent_reader",
        agent,
        owner,
        "SELECT api.agent_audit_begin('query_resource', NULL, NULL, NULL, NULL);",
    )
    assert _returned(first), "the first call inside the bound was refused"

    # `name` is the container: the fixture yields the name it started, and there
    # is no separate `container` key.
    restarted = _docker("restart", cluster["name"], timeout=120)
    assert restarted.returncode == 0, restarted.stderr
    for _ in range(90):
        if _docker("exec", cluster["name"], "pg_isready", "-U", "postgres").returncode == 0:
            break
        time.sleep(1)
    else:  # pragma: no cover -- the cluster never came back
        pytest.fail("the cluster did not come back after a restart")

    after = as_agent(
        cluster,
        "agent_reader",
        agent,
        owner,
        "SELECT api.agent_audit_begin('query_resource', NULL, NULL, NULL, NULL);",
    )
    assert _returned(after) == "", (
        "the quota was clear after a restart, so an agent can reset its own bound "
        "by waiting for one"
    )

    # The control: the counter is what survived, and it survived at the value the
    # first call left. A test asserting only the refusal would pass against a
    # cluster that had forgotten the agent entirely and refused for that reason.
    counted = su(cluster, f"SELECT calls FROM app_private.agent_quota WHERE agent_id = '{agent}';")
    assert counted.stdout.strip() == "2", (
        f"the counter reads {counted.stdout.strip()!r} after the restart; the refusal "
        "above may not have been about the quota at all"
    )


# ---------------------------------------------------------------------------
# Idempotency keys (Session 16 Run 6 -- ADR 0181, migration 0029)
# ---------------------------------------------------------------------------
#
# Every arm needs a cluster, because the guarantee is atomicity inside the
# write's own transaction and nothing offline can reach it.


def _writing_agent(cluster: dict[str, Any]) -> tuple[str, str]:
    """One agent that may write, and its owner. Returns (agent_id, owner_id)."""
    owner = str(uuid.uuid4())
    agent = str(uuid.uuid4())
    su(
        cluster,
        f"INSERT INTO app_private.users "
        f"(id, username, display_name, role_name, scopes, status) VALUES "
        f"('{owner}', 'w{agent[:8]}', 'Write Owner', 'apg_authenticated', "
        f"ARRAY['notes:write']::text[], 'active');",
    )
    su(
        cluster,
        "INSERT INTO app_private.agents (id, name, role_name, scopes, owner_id) VALUES "
        f"('{agent}', 'write-{agent[:8]}', 'r', ARRAY['notes:write']::text[], '{owner}');",
    )
    return agent, owner


def _note(cluster: dict[str, Any], agent: str, owner: str, key: str, title: str = "t"):
    return as_agent(
        cluster,
        "agent_writer",
        agent,
        owner,
        f"SELECT (api.create_note('{title}', 'body')).id;",
        idempotency_key=key,
    )


def test_no_role_holds_any_privilege_on_the_idempotency_table(cluster: dict[str, Any]) -> None:
    """0019's rule for `agent_audit` and 0028's for `agent_quota`, applied.

    A grant question, so it reads the catalog rather than asking
    `has_table_privilege`, which answers for privileges held by way of
    MEMBERSHIP and would report roles appearing in no ACL entry at all (D467,
    ADR 0134). `aclexplode` also names the OWNER as a grantee, so it is
    subtracted.
    """
    result = su(
        cluster,
        "SELECT coalesce(string_agg(DISTINCT grantee::regrole::text, ','), '') "
        "FROM pg_class c, aclexplode(c.relacl) a "
        "WHERE c.oid = 'app_private.agent_idempotency'::regclass "
        "  AND a.grantee <> c.relowner;",
    )
    assert result.stdout.strip() == "", (
        f"a role holds a privilege on the claim table: {result.stdout.strip()}"
    )


def test_a_replayed_write_performs_the_work_once_and_returns_the_same_row(
    cluster: dict[str, Any],
) -> None:
    """`AGT-IDEM-001`'s first half, end to end through the reviewed function.

    The row's id is asserted equal across the two calls AND the table is counted,
    because either alone is satisfied by a wrong implementation: returning the
    same id proves nothing if a second row was written, and one row proves
    nothing if the replay returned somebody else's.
    """
    agent, owner = _writing_agent(cluster)
    key = "replay-same-key-01"

    first = _returned(_note(cluster, agent, owner, key))
    second = _returned(_note(cluster, agent, owner, key))

    assert first, "the first write returned nothing"
    assert second == first, f"the replay returned {second!r}, not {first!r}"

    written = su(
        cluster, f"SELECT count(*) FROM app.notes WHERE owner_id = '{owner}';"
    ).stdout.strip()
    assert written == "1", f"the replay wrote a second row; the table holds {written}"

    replays = su(
        cluster,
        "SELECT replay_count FROM app_private.agent_idempotency "
        f"WHERE agent_id = '{agent}' AND idempotency_key = '{key}';",
    ).stdout.strip()
    assert replays == "1", f"the claim records {replays} replays, not 1"


def test_a_different_key_with_the_same_body_writes_twice(cluster: dict[str, Any]) -> None:
    """`AGT-IDEM-001`'s second half, and **the control for the arm above.**

    Without it, a `create_note` that had simply stopped writing would satisfy
    every replay assertion in this file. The bodies are identical, so the only
    thing distinguishing these two calls is the key -- which is exactly the claim
    being made.
    """
    agent, owner = _writing_agent(cluster)

    first = _returned(_note(cluster, agent, owner, "distinct-key-aaa"))
    second = _returned(_note(cluster, agent, owner, "distinct-key-bbb"))

    assert first and second and first != second, "two keys produced one row"
    written = su(
        cluster, f"SELECT count(*) FROM app.notes WHERE owner_id = '{owner}';"
    ).stdout.strip()
    assert written == "2", f"two distinct keys wrote {written} rows"


def test_a_replay_is_audited_as_replayed_and_records_no_rows(cluster: dict[str, Any]) -> None:
    """A replay is its own outcome, not `served` with a zero row count (D495).

    The enum member is what makes this readable by an operator without inferring
    anything from arithmetic -- and `ALTER TYPE ... ADD VALUE` committing in the
    same transaction as the plpgsql bodies that name it is measured rather than
    assumed, because a `LANGUAGE sql` body in that position does NOT.
    """
    agent, owner = _writing_agent(cluster)
    key = "audited-replay-01"

    _note(cluster, agent, owner, key)
    _note(cluster, agent, owner, key)

    outcomes = su(
        cluster,
        "SELECT outcome || ':' || coalesce(row_count::text, 'null') "
        "FROM app_private.agent_audit "
        f"WHERE agent_id = '{agent}' AND source = 'database' ORDER BY completed_at;",
    ).stdout.split()
    assert outcomes == ["committed:1", "replayed:0"], outcomes


def test_a_key_reused_for_different_arguments_is_refused(cluster: dict[str, Any]) -> None:
    """The argument fingerprint, and why it is not merely part of the key.

    Making the hash part of the primary key would need no refusal at all -- the
    second call would simply be a different claim and would write. That is wrong
    QUIETLY: a caller retrying with a corrupted body gets a second write and no
    signal, which is the outcome a key was supplied to prevent (ADR 0181).
    """
    agent, owner = _writing_agent(cluster)
    key = "same-key-other-args"

    _note(cluster, agent, owner, key, title="first title")
    refused = _note(cluster, agent, owner, key, title="a different title")

    assert refused.returncode != 0, "a key bound to different arguments wrote anyway"
    assert "AP412" in (refused.stderr or ""), refused.stderr

    written = su(
        cluster, f"SELECT count(*) FROM app.notes WHERE owner_id = '{owner}';"
    ).stdout.strip()
    assert written == "1", f"the refused call still wrote; the table holds {written}"


def test_a_key_reused_for_a_different_tool_is_refused(cluster: dict[str, Any]) -> None:
    """The claim records which tool spent the key, and refuses another one.

    **This proof was measuring the wrong check and a surviving mutation said so.**
    Its first version spent a key on `create_note` and then called
    `update_task_status` through the plane, which is refused -- but removing the
    tool comparison from `agent_idempotency_claim` left it green, because those
    two calls also have different ARGUMENT FINGERPRINTS and the second half of
    the same condition refused them.

    The reason is worth stating rather than patching around: the fingerprint is
    `jsonb_build_object` over each function's own parameter names, and the two
    reviewed writes share none, so **two tools can never produce the same
    fingerprint and the tool comparison cannot currently be the deciding
    clause.** It is kept as the explicit authority -- the claim's `tool` column is
    what an operator reads, and a third write tool sharing another's parameter
    names would make the comparison load-bearing overnight -- but a check that
    cannot fire must be proved at the boundary that can reach it, not through a
    path that reaches it by accident.

    So the plane arm below asserts what the plane actually guarantees, and the
    function arm calls `agent_idempotency_claim` directly with a fingerprint held
    EQUAL across two tool names, which is the only way to isolate the clause.
    """
    agent, owner = _writing_agent(cluster)
    key = "same-key-other-tool"

    _note(cluster, agent, owner, key)

    # The claim names the tool that spent the key. An operator reads this column,
    # so it is asserted rather than assumed.
    spent_on = su(
        cluster,
        "SELECT tool FROM app_private.agent_idempotency "
        f"WHERE agent_id = '{agent}' AND idempotency_key = '{key}';",
    ).stdout.strip()
    assert spent_on == "create_note", spent_on

    # Through the plane: refused, though the fingerprint alone would refuse it.
    refused = as_agent(
        cluster,
        "agent_writer",
        agent,
        owner,
        f"SELECT api.update_task_status('{uuid.uuid4()}', 'pending', 'completed');",
        idempotency_key=key,
    )
    assert refused.returncode != 0, "a key spent on one tool was accepted by another"
    assert "AP412" in (refused.stderr or ""), refused.stderr

    # The clause in isolation: SAME fingerprint, different tool. Only the tool
    # comparison can refuse this, so removing it makes this arm go green.
    fingerprint = "a" * 64
    other = str(uuid.uuid4())
    su(
        cluster,
        "INSERT INTO app_private.agent_idempotency "
        "(agent_id, idempotency_key, tool, arguments_sha256, row_id) VALUES "
        f"('{other}', 'isolated-key-01', 'create_note', '{fingerprint}', '{uuid.uuid4()}');",
    )
    isolated = su(
        cluster,
        "SELECT app_private.agent_idempotency_claim("
        f"'{other}', 'isolated-key-01', 'update_task_status', '{fingerprint}', "
        f"'{uuid.uuid4()}');",
    )
    assert isolated.returncode != 0, (
        "a claim with a matching fingerprint and a DIFFERENT tool was accepted; "
        "the tool comparison is not doing anything"
    )
    assert "AP412" in (isolated.stderr or ""), isolated.stderr

    # THE CONTROL: the same call with the tool ALSO matching is a plain replay.
    # Without it the assertion above is satisfied by a claim function that
    # refuses everything.
    replayed = su(
        cluster,
        "SELECT app_private.agent_idempotency_claim("
        f"'{other}', 'isolated-key-01', 'create_note', '{fingerprint}', "
        f"'{uuid.uuid4()}');",
    )
    assert replayed.returncode == 0, f"a matching claim was refused: {replayed.stderr}"


def test_an_agent_write_without_a_key_is_refused_and_a_human_write_is_not(
    cluster: dict[str, Any],
) -> None:
    """Required in the DATABASE, not only in the runtime -- and the human half.

    0019 built these functions so that a caller skipping the agent plane and
    posting to `/rpc/create_note` directly still leaves an audit row; the same
    reasoning covers the guarantee, because a check living only in the runtime is
    a check an agent can route around.

    **The human arm is the control and it is also the contract.** The claim is
    taken only when `app.agent_id` is set, so a human caller is unaffected --
    same rows, same errors, no key. Without this arm the assertion above would be
    satisfied by a migration that had broken `create_note` for everybody.
    """
    agent, owner = _writing_agent(cluster)

    refused = su(
        cluster,
        f"""
        BEGIN;
        SET LOCAL ROLE "{cluster["roles"]["agent_writer"]}";
        SELECT set_config('app.agent_id', '{agent}', true);
        SELECT set_config('app.user_id', '{owner}', true);
        SELECT (api.create_note('no key', 'body')).id;
        COMMIT;
        """,
    )
    assert refused.returncode != 0, "an agent wrote with no idempotency key"
    assert "AP412" in (refused.stderr or ""), refused.stderr

    human = su(
        cluster,
        f"""
        BEGIN;
        SET LOCAL ROLE "{cluster["roles"]["authenticated"]}";
        SELECT set_config('app.user_id', '{owner}', true);
        SELECT (api.create_note('a human note', 'body')).id;
        COMMIT;
        """,
    )
    assert human.returncode == 0, f"a human write was refused for want of a key: {human.stderr}"


def test_a_malformed_key_raises_rather_than_being_ignored(cluster: dict[str, Any]) -> None:
    """D633, inverted deliberately, and the inversion is the point.

    `agent_request_id()` returns NULL for anything malformed and lets the write
    proceed, because a correlation field must never destroy the operation it
    annotates. Ignoring a malformed idempotency key would instead perform the
    write WITHOUT the guarantee the caller asked for -- a silent downgrade from
    at-most-once to at-least-once. Same mechanism, opposite failure mode.

    The control is a key one character longer than the floor: the refusal must be
    about the shape and not about every key.
    """
    agent, owner = _writing_agent(cluster)

    # **The SENTENCE, not just the errcode.** Both the malformed key and the
    # absent one raise AP412, so asserting the code alone would be satisfied by
    # a reader that quietly returned NULL for anything it could not parse --
    # which is exactly the D633 behaviour this function inverts. A test that
    # cannot tell the two refusals apart is not testing the inversion.
    for bad in ("short", "has a space in it", ""):
        refused = _note(cluster, agent, owner, bad)
        assert refused.returncode != 0, f"the malformed key {bad!r} was accepted"
        assert "must be 8 to 255" in (refused.stderr or ""), refused.stderr

    accepted = _note(cluster, agent, owner, "12345678")
    assert accepted.returncode == 0, f"an eight-character key was refused: {accepted.stderr}"

    written = su(
        cluster, f"SELECT count(*) FROM app.notes WHERE owner_id = '{owner}';"
    ).stdout.strip()
    assert written == "1", f"a malformed key still wrote; the table holds {written}"


def test_a_replayed_transition_returns_the_row_rather_than_a_conflict(
    cluster: dict[str, Any],
) -> None:
    """**Where a key earns its keep**, and why the claim precedes the swap.

    Without it a retried transition fails its own compare-and-swap -- the status
    it expects is the status it already set -- and the caller reads `PT409` for a
    write that had in fact succeeded. That is the exact confusion an idempotency
    key is supplied to remove, so the ordering inside migration 0029 is load
    bearing rather than incidental.

    The control is the same transition WITHOUT a replay: a second call under a
    fresh key must still be refused with `AP409`, or this proof would pass
    against a function that had simply stopped comparing.
    """
    agent, owner = _writing_agent(cluster)
    note = _returned(_note(cluster, agent, owner, "task-owner-key-1"))
    task = str(uuid.uuid4())
    su(
        cluster,
        f"INSERT INTO app.tasks (id, owner_id, note_id, title) "
        f"VALUES ('{task}', '{owner}', '{note}', 'a task');",
    )

    move = f"SELECT (api.update_task_status('{task}', 'pending', 'completed')).status;"
    first = as_agent(cluster, "agent_writer", agent, owner, move, idempotency_key="move-key-0001")
    assert first.returncode == 0, first.stderr
    assert _returned(first) == "completed", _returned(first)

    replay = as_agent(cluster, "agent_writer", agent, owner, move, idempotency_key="move-key-0001")
    assert replay.returncode == 0, f"the replayed transition was refused: {replay.stderr}"
    assert _returned(replay) == "completed", _returned(replay)

    conflict = as_agent(
        cluster, "agent_writer", agent, owner, move, idempotency_key="move-key-0002"
    )
    assert conflict.returncode != 0, "THE CONTROL: a fresh key must still meet the swap"
    assert "AP409" in (conflict.stderr or ""), conflict.stderr


def test_a_failed_write_does_not_burn_its_key(cluster: dict[str, Any]) -> None:
    """D489 as a feature rather than a constraint, for once.

    The claim is written in the transaction the write aborts, so a `RAISE` takes
    it with them both -- and here that is what anyone would want: a key is
    retryable after a failure. The same rule cost ADR 0180 its return type and
    cost 0019 its ability to record a failed write.
    """
    agent, owner = _writing_agent(cluster)
    key = "retried-after-failure"

    failed = as_agent(
        cluster,
        "agent_writer",
        agent,
        owner,
        f"SELECT api.update_task_status('{uuid.uuid4()}', 'pending', 'completed');",
        idempotency_key=key,
    )
    assert failed.returncode != 0 and "AP404" in (failed.stderr or ""), failed.stderr

    claims = su(
        cluster,
        f"SELECT count(*) FROM app_private.agent_idempotency WHERE agent_id = '{agent}';",
    ).stdout.strip()
    assert claims == "0", f"the aborted write left {claims} claims behind"

    # And the key still works -- for a different tool, which the claim would have
    # refused had the failed call left one.
    retried = _note(cluster, agent, owner, key)
    assert retried.returncode == 0, f"the key was burned by a failure: {retried.stderr}"


# ---------------------------------------------------------------------------
# Dry-run (Session 16 Run 7 -- ADR 0182, migration 0030)
# ---------------------------------------------------------------------------
#
# Every arm needs a cluster, because the whole claim is that a dry-run runs the
# PRODUCT's validation -- the CHECK constraints, the policies, the
# compare-and-swap -- and none of that exists offline.


def test_a_dry_run_changes_nothing_and_records_a_dry_run(cluster: dict[str, Any]) -> None:
    """`AGT-DRYRUN-001`, and the id is the half worth reading twice.

    The `RETURNING` variable survives the rollback complete, id included -- and
    that id belongs to a row that does not exist and never will. Publishing it
    would be D600 with a fresh coat: a plausible uuid nothing holds, in the field
    a client is most likely to keep. Nothing was created, so nothing has one.

    The CONTROL is the same call without the header. Without it, a `create_note`
    that had simply stopped working would satisfy every assertion here.
    """
    agent, owner = _writing_agent(cluster)

    rehearsed = as_agent(
        cluster,
        "agent_writer",
        agent,
        owner,
        "SELECT coalesce((api.create_note('rehearsed', 'body')).id::text, 'NULL');",
        dry_run="true",
    )
    assert rehearsed.returncode == 0, rehearsed.stderr
    assert _returned(rehearsed) == "NULL", _returned(rehearsed)

    assert (
        su(cluster, f"SELECT count(*) FROM app.notes WHERE owner_id = '{owner}';").stdout.strip()
        == "0"
    ), "a dry run wrote a row"

    outcomes = su(
        cluster,
        "SELECT outcome || ':' || coalesce(row_count::text, 'null') "
        "FROM app_private.agent_audit "
        f"WHERE agent_id = '{agent}' AND source = 'database';",
    ).stdout.split()
    assert outcomes == ["dry_run:0"], outcomes

    # THE CONTROL: the same call, no header, writes for real.
    real = as_agent(
        cluster,
        "agent_writer",
        agent,
        owner,
        "SELECT (api.create_note('for real', 'body')).id;",
    )
    assert real.returncode == 0, real.stderr
    assert _returned(real) != "NULL"
    assert (
        su(cluster, f"SELECT count(*) FROM app.notes WHERE owner_id = '{owner}';").stdout.strip()
        == "1"
    )


def test_a_dry_run_reports_the_refusal_the_real_call_would_have_produced(
    cluster: dict[str, Any],
) -> None:
    """**Whose validation**, which is the question the run's plan does not answer.

    `length(title) BETWEEN 1 AND 200` is a CHECK on `app.notes`. A dry-run that
    skipped the write would skip it and report success for a title the table
    refuses -- the single thing a caller most wants a dry-run to tell them. So
    the write is ATTEMPTED and rolled back, and the constraint fires.

    The two arms together are the claim: the rehearsal and the real call are
    refused by the SAME constraint, so a dry-run's refusal is the refusal the
    real call would have produced rather than an imitation of it.
    """
    agent, owner = _writing_agent(cluster)
    long_title = "x" * 201

    rehearsed = as_agent(
        cluster,
        "agent_writer",
        agent,
        owner,
        f"SELECT (api.create_note('{long_title}', 'body')).id;",
        dry_run="true",
    )
    assert rehearsed.returncode != 0, "a dry run accepted a title the table refuses"
    assert "notes_title_check" in (rehearsed.stderr or ""), rehearsed.stderr

    real = as_agent(
        cluster,
        "agent_writer",
        agent,
        owner,
        f"SELECT (api.create_note('{long_title}', 'body')).id;",
    )
    assert real.returncode != 0
    assert "notes_title_check" in (real.stderr or ""), real.stderr

    # And neither left anything behind -- the audit row included, because an
    # aborting transaction takes it (D489).
    assert (
        su(
            cluster,
            f"SELECT count(*) FROM app_private.agent_audit WHERE agent_id = '{agent}';",
        ).stdout.strip()
        == "0"
    )


def test_a_dry_run_spends_no_idempotency_key(cluster: dict[str, Any]) -> None:
    """A rehearsal changes nothing, and dedupe state is something (ADR 0182).

    Burning a key on a dry-run would make the real call that follows a replay of
    a write that never happened -- the caller would get a row back and no row
    would exist. The claim is therefore taken AFTER the dry-run branch.

    It is still required, which the second arm asserts: the rule stays "every
    agent write carries a key" with no exception a caller has to remember.
    """
    agent, owner = _writing_agent(cluster)
    key = "rehearse-then-write"

    rehearsed = as_agent(
        cluster,
        "agent_writer",
        agent,
        owner,
        "SELECT (api.create_note('rehearsed', 'body')).id;",
        idempotency_key=key,
        dry_run="true",
    )
    assert rehearsed.returncode == 0, rehearsed.stderr
    assert (
        su(
            cluster,
            f"SELECT count(*) FROM app_private.agent_idempotency WHERE agent_id = '{agent}';",
        ).stdout.strip()
        == "0"
    ), "a dry run claimed the key"

    real = _note(cluster, agent, owner, key)
    assert real.returncode == 0, f"the key was spent by a rehearsal: {real.stderr}"
    assert _returned(real) != "NULL"
    assert (
        su(cluster, f"SELECT count(*) FROM app.notes WHERE owner_id = '{owner}';").stdout.strip()
        == "1"
    )

    # A rehearsal still requires a key, like every other agent write.
    keyless = su(
        cluster,
        f"""
        BEGIN;
        SET LOCAL ROLE "{cluster["roles"]["agent_writer"]}";
        SELECT set_config('app.agent_id', '{agent}', true);
        SELECT set_config('app.user_id', '{owner}', true);
        SELECT set_config('request.headers', '{{"dry-run": "true"}}', true);
        SELECT (api.create_note('no key', 'body')).id;
        COMMIT;
        """,
    )
    assert keyless.returncode != 0, "a rehearsal was accepted with no idempotency key"
    assert "AP412" in (keyless.stderr or ""), keyless.stderr


def test_a_malformed_dry_run_header_raises_rather_than_reading_as_false(
    cluster: dict[str, Any],
) -> None:
    """**The one misreading that costs a row**, so the parse is narrow.

    A caller who asked for a rehearsal and got a live write has no way to find
    out: the call succeeds, the row is created, and the response looks exactly
    like the rehearsal they expected. So anything that is not the literal `true`
    or `false` raises rather than being read as false -- the opposite of the
    forgiving parse a header usually gets.

    The controls are both literals, which must be accepted and must MEAN what
    they say: `false` writes, `true` does not.
    """
    agent, owner = _writing_agent(cluster)

    for bad in ("1", "TRUE", "yes", ""):
        refused = as_agent(
            cluster,
            "agent_writer",
            agent,
            owner,
            "SELECT (api.create_note('ambiguous', 'body')).id;",
            dry_run=bad,
        )
        assert refused.returncode != 0, f"the dry-run header {bad!r} was accepted"
        assert "AP412" in (refused.stderr or ""), refused.stderr

    assert (
        su(cluster, f"SELECT count(*) FROM app.notes WHERE owner_id = '{owner}';").stdout.strip()
        == "0"
    ), "an ambiguous dry-run header wrote a row"

    explicit_false = as_agent(
        cluster,
        "agent_writer",
        agent,
        owner,
        "SELECT (api.create_note('explicitly live', 'body')).id;",
        dry_run="false",
    )
    assert explicit_false.returncode == 0, explicit_false.stderr
    assert _returned(explicit_false) != "NULL"
    assert (
        su(cluster, f"SELECT count(*) FROM app.notes WHERE owner_id = '{owner}';").stdout.strip()
        == "1"
    ), "the literal false did not write"


def test_a_dry_run_of_a_transition_leaves_the_status_alone(cluster: dict[str, Any]) -> None:
    """The rehearsal shows the status it WOULD set, and sets nothing.

    A task's id is the caller's own argument rather than a minted one, so it is
    not nulled: the row it names exists, and what did not happen is the
    transition. `row_count` 0 with outcome `dry_run` is what says so.

    The CONTROL is the real transition afterwards, which must actually move the
    status -- otherwise "the status is unchanged" is satisfied by a function
    that no longer works.
    """
    agent, owner = _writing_agent(cluster)
    note = _returned(_note(cluster, agent, owner, "task-key-dryrun-1"))
    task = str(uuid.uuid4())
    su(
        cluster,
        f"INSERT INTO app.tasks (id, owner_id, note_id, title) "
        f"VALUES ('{task}', '{owner}', '{note}', 'a task');",
    )

    move = f"SELECT (api.update_task_status('{task}', 'pending', 'completed')).status;"
    rehearsed = as_agent(cluster, "agent_writer", agent, owner, move, dry_run="true")
    assert rehearsed.returncode == 0, rehearsed.stderr
    assert _returned(rehearsed) == "completed", "the rehearsal did not show the new status"

    assert (
        su(cluster, f"SELECT status FROM app.tasks WHERE id = '{task}';").stdout.strip()
        == "pending"
    ), "a dry run moved the task"

    real = as_agent(cluster, "agent_writer", agent, owner, move)
    assert real.returncode == 0, real.stderr
    assert (
        su(cluster, f"SELECT status FROM app.tasks WHERE id = '{task}';").stdout.strip()
        == "completed"
    ), "THE CONTROL: the real transition did not move the task either"


def test_a_dry_run_of_a_transition_reports_the_conflict_the_real_call_would(
    cluster: dict[str, Any],
) -> None:
    """The compare-and-swap runs in a rehearsal, which is the point of one.

    A caller asking "would this transition succeed" is asking exactly the
    question the CAS answers, and a dry-run that skipped it would answer yes for
    a task somebody else had already moved.
    """
    agent, owner = _writing_agent(cluster)
    note = _returned(_note(cluster, agent, owner, "task-key-dryrun-2"))
    task = str(uuid.uuid4())
    su(
        cluster,
        f"INSERT INTO app.tasks (id, owner_id, note_id, title, status) "
        f"VALUES ('{task}', '{owner}', '{note}', 'a task', 'completed');",
    )

    rehearsed = as_agent(
        cluster,
        "agent_writer",
        agent,
        owner,
        f"SELECT (api.update_task_status('{task}', 'pending', 'completed')).status;",
        dry_run="true",
    )
    assert rehearsed.returncode != 0, "a rehearsal skipped the compare-and-swap"
    assert "AP409" in (rehearsed.stderr or ""), rehearsed.stderr
