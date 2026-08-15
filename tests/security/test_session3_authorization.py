"""The database authorization boundary, measured against a running cluster.

These replace the seven Session 3 placeholders that lived in
``test_future_security_boundaries.py``. They need a host, and they say so with
``requires_environment`` rather than with ``future`` -- the distinction
``test_environment_gates.py`` holds: ``future`` means nobody wrote this, and
these are written.

**What these prove and what they do not.** Session 3 does not authenticate.
Request identity is a transaction-local claim the database trusts and cannot
verify (ADR 0029), so `SEC-RLS-001` proves that *given a claim*, rows are
isolated by owner. It does not prove the claim is authentic; anything holding a
database credential can assert any value. Session 6 makes it authentic by
changing who sets the GUC, and the policies do not move.

Every assertion reads the catalog or measures a real query result. None reads
the migration source: a test asserting that a migration *contains* `FORCE ROW
LEVEL SECURITY` would pass against a cluster where the migration never ran, and
`ALTER DEFAULT PRIVILEGES` in Run 4 is the standing reminder that a statement
can be present, report success, and establish nothing.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

# ruff: noqa: S608
#
# Every statement below interpolates values that came from the rendered
# outputs document -- role names and a database name derived by `naming` and
# validated by the outputs schema -- plus two hard-coded uuid constants. None
# of it is operator input, and parameter binding is unavailable where an
# identifier or a role name goes, which is the same reason
# `migrations.quote_identifier` exists. Suppressed per module rather than per
# line because the rule fires on nearly every assertion here and a wall of
# inline noqa comments is one nobody reads.

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.database,
    pytest.mark.live_host,
    pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS"),
]

#: Two arbitrary owner identities. Constants rather than generated values so a
#: failure names the same uuid every time and a stray row is attributable.
OWNER_A = "11111111-1111-1111-1111-111111111111"
OWNER_B = "22222222-2222-2222-2222-222222222222"


@pytest.fixture(scope="module")
def project_a() -> dict[str, Any]:
    return json.loads(Path(os.environ["APG_PROJECT_A_OUTPUTS"]).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def roles(project_a: dict[str, Any]) -> dict[str, str]:
    return project_a["database"]["roles"]


def sql(document: dict[str, Any], statement: str) -> str:
    """Run one statement over the container socket and return its output.

    `docker exec -i`, and the `-i` matters: without it stdin is not forwarded,
    psql reads nothing, and the command exits 0 having executed nothing -- a
    silent success indistinguishable from a real one.
    """
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            document["database"]["container"],
            "psql",
            "-U",
            "postgres",
            "-d",
            document["database"]["name"],
            "-X",
            "-qtA",
            "-c",
            statement,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if result.returncode != 0:
        return f"ERROR: {result.stderr.strip()}"
    return result.stdout.strip()


def as_role(document: dict[str, Any], role: str, statement: str, claim: str | None = None) -> str:
    """Run a statement as a role, optionally under a request-identity claim."""
    prelude = f'SET ROLE "{role}"; '
    if claim is not None:
        prelude += f"SET app.user_id = '{claim}'; "
    return sql(document, prelude + statement)


@pytest.fixture(scope="module", autouse=True)
def _seed(project_a: dict[str, Any], roles: dict[str, str]) -> None:
    """One note per owner, created through the RPC as the RPC's caller.

    Seeded through `api.create_note` rather than by a direct INSERT so the
    fixture exercises the same path the assertions describe. A fixture that
    inserted as the owner would prove isolation over rows no caller could have
    produced.
    """
    for owner in (OWNER_A, OWNER_B):
        as_role(
            project_a,
            roles["authenticated"],
            f"SELECT (api.create_note('seed-{owner[:8]}')).owner_id;",
            claim=owner,
        )


# ---------------------------------------------------------------------------
# SEC-RLS-001 — owner-scoped rows are isolated by owner under forced RLS
# ---------------------------------------------------------------------------


def test_user_a_cannot_read_user_b_rows(project_a: dict[str, Any], roles: dict[str, str]) -> None:
    visible = as_role(
        project_a, roles["authenticated"], "SELECT string_agg(title, ',') FROM api.notes;", OWNER_A
    )
    assert f"seed-{OWNER_A[:8]}" in visible
    assert f"seed-{OWNER_B[:8]}" not in visible, "A can see B's rows"


def test_user_b_cannot_read_user_a_rows(project_a: dict[str, Any], roles: dict[str, str]) -> None:
    visible = as_role(
        project_a, roles["authenticated"], "SELECT string_agg(title, ',') FROM api.notes;", OWNER_B
    )
    assert f"seed-{OWNER_B[:8]}" in visible
    assert f"seed-{OWNER_A[:8]}" not in visible, "B can see A's rows"


def test_a_missing_claim_sees_no_rows(project_a: dict[str, Any], roles: dict[str, str]) -> None:
    """The policies deny by default rather than falling back to anything.

    `current_setting(..., true)` is NULL when unset and `owner_id = NULL` is
    never true, so an absent claim is not an anonymous read -- it is no read.
    """
    visible = as_role(project_a, roles["authenticated"], "SELECT count(*) FROM api.notes;")
    assert visible == "0", f"a caller with no claim saw {visible} rows"


def test_forced_rls_applies_to_the_object_owner(
    project_a: dict[str, Any], roles: dict[str, str]
) -> None:
    """FORCE, not merely ENABLE. This is the assertion that distinguishes them.

    With ENABLE alone every statement run by the table's owner -- which is what
    a migration and any maintenance script runs as -- bypasses every policy
    silently. "RLS is on" is true in both cases and means much less in one.
    """
    unclaimed = as_role(project_a, roles["object_owner"], "SELECT count(*) FROM app.notes;")
    assert unclaimed == "0", f"the owner saw {unclaimed} rows with no claim; FORCE is not in effect"

    claimed = as_role(
        project_a, roles["object_owner"], "SELECT string_agg(title, ',') FROM app.notes;", OWNER_A
    )
    assert f"seed-{OWNER_A[:8]}" in claimed
    assert f"seed-{OWNER_B[:8]}" not in claimed


def test_the_catalog_records_forced_row_level_security(project_a: dict[str, Any]) -> None:
    """Read from pg_class, not from the migration text."""
    observed = sql(
        project_a,
        "SELECT string_agg(c.relname || '=' || c.relrowsecurity || '/' || "
        "c.relforcerowsecurity, ' ' ORDER BY c.relname) FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'app' AND c.relkind = 'r';",
    )
    # `true`, not `t`. `boolean || text` yields the full word; `t` is what psql
    # *prints* in a table, and this concatenates rather than prints. The
    # expectation was written from the printed form by a run that had no cluster
    # to check it against, and would have failed on first contact with any
    # cluster (D63). The property being asserted was right all along.
    assert observed == "notes=true/true tasks=true/true", observed


def test_a_caller_cannot_update_a_row_into_another_owner(
    project_a: dict[str, Any], roles: dict[str, str]
) -> None:
    """USING governs visibility, WITH CHECK governs writes. Both are needed.

    With USING alone a caller could UPDATE a row it can see into one owned by
    somebody else, and the row would vanish from its own view -- which reads as
    a delete and is a write into another tenant.
    """
    result = as_role(
        project_a,
        roles["authenticated"],
        f"UPDATE app.notes SET owner_id = '{OWNER_B}' WHERE owner_id = '{OWNER_A}';",
        claim=OWNER_A,
    )
    assert "ERROR" in result, f"a caller reassigned ownership: {result}"


# ---------------------------------------------------------------------------
# SEC-VIEW-001 — security-invoker views expose only caller-visible rows
# ---------------------------------------------------------------------------


def test_the_api_views_are_security_invoker(project_a: dict[str, Any]) -> None:
    observed = sql(
        project_a,
        "SELECT string_agg(c.relname || '=' || "
        "(c.reloptions::text LIKE '%security_invoker=true%')::text, ' ' ORDER BY c.relname) "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'api' AND c.relkind = 'v';",
    )
    assert observed == "notes=true tasks=true", observed


def test_the_view_returns_the_callers_rows_not_the_owners(
    project_a: dict[str, Any], roles: dict[str, str]
) -> None:
    """The reloption is not the proof. A view can be correct in the catalog and
    wrong in what it returns if the underlying table lost FORCE, so this
    compares two callers' actual results."""
    seen_by_a = as_role(
        project_a, roles["authenticated"], "SELECT count(*) FROM api.notes;", OWNER_A
    )
    seen_by_b = as_role(
        project_a, roles["authenticated"], "SELECT count(*) FROM api.notes;", OWNER_B
    )
    total = sql(project_a, "SELECT count(*) FROM app.notes;")

    # Compared against what each owner actually has, not against the literal 1.
    # The seed adds a row per run, so a fixed count is a test that passes once
    # on a virgin cluster and fails on every re-run -- including the second gate
    # of a convergence check and every run after a reboot (D63). What is being
    # proved is that a caller sees its own rows and only those, and that there
    # are rows it cannot see; both survive re-seeding.
    owned_by_a = sql(project_a, f"SELECT count(*) FROM app.notes WHERE owner_id = '{OWNER_A}';")
    owned_by_b = sql(project_a, f"SELECT count(*) FROM app.notes WHERE owner_id = '{OWNER_B}';")

    assert seen_by_a == owned_by_a, f"A saw {seen_by_a} of its {owned_by_a} rows"
    assert seen_by_b == owned_by_b, f"B saw {seen_by_b} of its {owned_by_b} rows"
    assert int(owned_by_a) >= 1 and int(owned_by_b) >= 1, "the seed produced no rows"
    assert int(total) > int(seen_by_a), "there are no rows A is being kept from"


# ---------------------------------------------------------------------------
# SEC-DB-002 — the schema boundaries
# ---------------------------------------------------------------------------


def test_api_roles_cannot_address_the_app_schema(
    project_a: dict[str, Any], roles: dict[str, str]
) -> None:
    """Both halves are asserted separately (D58).

    The API roles hold SELECT on the base tables -- a security_invoker view
    needs it -- and deliberately no USAGE on the schema, so the view works and
    direct access does not. Inferring either from the other is how one of them
    silently stops being true.
    """
    for role in ("authenticated", "agent_reader", "anon"):
        observed = sql(
            project_a,
            f"SELECT has_schema_privilege('{roles[role]}', 'app', 'USAGE');",
        )
        assert observed == "f", f"{role} holds USAGE on app"


def test_a_role_that_makes_no_request_cannot_address_the_private_schema(
    project_a: dict[str, Any], roles: dict[str, str]
) -> None:
    """Migration 0008 opened `app_private` to the roles PostgREST impersonates,
    and to those only (ADR 0052).

    The agent roles are Session 9's. They are not granted to the authenticator,
    so no token can name them, and a USAGE grant to a role that can never make a
    request would widen the private schema to buy nothing. This is the half of
    the old assertion that is unchanged, and it is what keeps the grant bounded
    rather than general.
    """
    for role in ("agent_reader", "agent_writer"):
        observed = sql(
            project_a,
            f"SELECT has_schema_privilege('{roles[role]}', 'app_private', 'USAGE');",
        )
        assert observed == "f", f"{role} holds USAGE on app_private"


def test_a_request_role_reaches_one_private_function_and_no_private_data(
    project_a: dict[str, Any], roles: dict[str, str]
) -> None:
    """The catalog half of ADR 0052, and the reason the old assertion moved.

    `anon` and `authenticated` now hold `USAGE ON SCHEMA app_private`, because
    PostgREST runs `db-pre-request` **after** the role switch and `EXECUTE`
    requires schema `USAGE`. The blanket assertion is therefore false by design,
    and replacing it with nothing would leave the largest authorization change
    in this session unchecked.

    What replaces it is stricter rather than weaker: the schema is nameable, and
    every object in it is enumerated and refused by name. `has_table_privilege`
    is deliberately not the whole proof -- D103 measured it returning true for
    objects a role cannot read -- so this asserts the ACLs and `SEC-PRIV-001`
    attempts the reads.
    """
    for role in ("anon", "authenticated"):
        usage = sql(
            project_a,
            f"SELECT has_schema_privilege('{roles[role]}', 'app_private', 'USAGE');",
        )
        assert usage == "t", f"{role} cannot resolve the pre-request hook"

        hook = sql(
            project_a,
            f"SELECT has_function_privilege('{roles[role]}', "
            "'app_private.postgrest_pre_request()', 'EXECUTE');",
        )
        assert hook == "t", f"{role} cannot execute the pre-request hook"

        # TWO functions are reachable, not one, and the second arrived
        # with migration 0013 (ADR 0096). `postgrest_pre_request` is
        # SECURITY INVOKER -- deliberately, so it can do nothing the caller
        # could not -- and it calls `auth_claims_are_current`, so the request
        # role needs EXECUTE on that too or every request fails.
        #
        # It is safe for the reason 0013 states beside the grant: the helper
        # takes the whole claim tuple and returns a BOOLEAN. It does not answer
        # "what are subject X's scopes", so a caller cannot enumerate another
        # subject's authority through it -- a probe costs a correct guess of all
        # five values.
        #
        # Still an allowlist, and still enumerated by name: a third function
        # appearing in `app_private` under open default privileges fails here,
        # which is what this assertion is for.
        reachable = sql(
            project_a,
            "SELECT coalesce(string_agg(p.proname, ',' ORDER BY p.proname), '') "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'app_private' AND "
            f"has_function_privilege('{roles[role]}', p.oid, 'EXECUTE');",
        )
        assert reachable == "auth_claims_are_current,postgrest_pre_request", (
            f"{role} can execute {reachable!r} in app_private, where the hook and "
            "its comparison helper are the only two it may reach"
        )

        tables = sql(
            project_a,
            "SELECT coalesce(string_agg(c.relname || ':' || m, ','), '') FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace, "
            "unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE']) AS m "
            "WHERE n.nspname = 'app_private' AND c.relkind IN ('r','v','m') "
            f"AND has_table_privilege('{roles[role]}', c.oid, m);",
        )
        assert tables == "", f"{role} holds {tables} in app_private"


def test_the_runtime_role_inherits_the_private_schema_grant_and_nothing_in_it(
    project_a: dict[str, Any], roles: dict[str, str]
) -> None:
    """A consequence nothing anticipated, measured rather than reasoned about.

    `app_runtime` is a member of `authenticated` with `INHERIT TRUE`, so
    migration 0008's grant reaches it -- and migration 0006 removed exactly that
    `USAGE` one session ago. The reach is real and it is empty: `USAGE` alone
    resolves names and confers nothing, and `app_runtime` holds no privilege on
    any object in the schema.

    Asserted rather than left implicit, because "empty today" is the whole risk.
    A later migration granting a private table to `authenticated` would reach
    the application runtime by a path nobody wrote down, and this is where that
    shows up. See D159.
    """
    usage = sql(
        project_a,
        f"SELECT has_schema_privilege('{roles['app_runtime']}', 'app_private', 'USAGE');",
    )
    assert usage == "t", (
        "the inheritance this test documents no longer happens; that is a change to "
        "D159, not an assertion to delete"
    )

    tables = sql(
        project_a,
        "SELECT coalesce(string_agg(c.relname || ':' || m, ','), '') FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace, "
        "unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE']) AS m "
        "WHERE n.nspname = 'app_private' AND c.relkind IN ('r','v','m') "
        f"AND has_table_privilege('{roles['app_runtime']}', c.oid, m);",
    )
    assert tables == "", f"the application runtime role holds {tables} in app_private"


def test_a_direct_read_of_the_private_table_is_denied(
    project_a: dict[str, Any], roles: dict[str, str]
) -> None:
    result = as_role(project_a, roles["authenticated"], "SELECT count(*) FROM app.notes;", OWNER_A)
    assert "ERROR" in result and "permission denied" in result, result


def test_the_four_schemas_exist(project_a: dict[str, Any]) -> None:
    observed = sql(
        project_a,
        "SELECT string_agg(nspname, ',' ORDER BY nspname) FROM pg_namespace "
        "WHERE nspname IN ('api', 'app', 'app_private', 'extensions');",
    )
    assert observed == "api,app,app_private,extensions", observed


def test_pgvector_is_installed_outside_public(project_a: dict[str, Any]) -> None:
    """DBX-PG-001's live half: installed, not merely available.

    `pg_available_extensions` reports what the image ships;
    `pg_extension` reports what this database actually has. The distinction is
    the entire content of the requirement.
    """
    observed = sql(
        project_a,
        "SELECT n.nspname || ' ' || e.extversion FROM pg_extension e "
        "JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'vector';",
    )
    assert observed.startswith("extensions "), observed


# ---------------------------------------------------------------------------
# SEC-FUNC-001 and SEC-DEFAULT-001 — execution is granted, never defaulted
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["anon", "agent_reader"])
def test_an_api_role_cannot_execute_an_ungranted_function(
    project_a: dict[str, Any], roles: dict[str, str], role: str
) -> None:
    observed = sql(
        project_a,
        f"SELECT has_function_privilege('{roles[role]}', 'api.create_note(text,text)', 'EXECUTE');",
    )
    assert observed == "f", f"{role} can execute a write RPC it was never granted"


def test_the_granted_roles_can_execute(project_a: dict[str, Any], roles: dict[str, str]) -> None:
    """The positive case, so the refusals above are not vacuous."""
    for role in ("authenticated", "agent_writer"):
        observed = sql(
            project_a,
            f"SELECT has_function_privilege('{roles[role]}', "
            "'api.create_note(text,text)', 'EXECUTE');",
        )
        assert observed == "t", f"{role} cannot execute a function it was granted"


def test_public_cannot_execute_the_write_rpcs(project_a: dict[str, Any]) -> None:
    """SEC-DEFAULT-001, measured on the functions that exist.

    PostgreSQL grants EXECUTE to PUBLIC on every new function. Run 4 measured
    `ALTER DEFAULT PRIVILEGES` to report success and store nothing on this
    image, so what carries this is the explicit REVOKE beside each CREATE
    FUNCTION -- and this asserts the outcome rather than the statement.

    Run 5 measured a second consequence, which is why this test now enumerates
    the catalog instead of naming two signatures. `openapi-mode =
    follow-privileges` follows a PUBLIC grant too: a function left with
    PostgreSQL's default EXECUTE is advertised in the document an anonymous
    caller receives, whether or not anyone intended to publish it.

    `api.create_task(text,uuid)` used to be named here and is gone (ADR 0048).
    Reading the signatures out of `pg_proc` rather than listing them means the
    next function is covered by existing, and a retired one cannot leave this
    test asserting something about an object that no longer exists.
    """
    signatures = sql(
        project_a,
        "SELECT coalesce(string_agg(p.oid::regprocedure::text, ','), '') FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'api';",
    )
    assert signatures, "no api functions found; this test would pass vacuously"

    leaked = sql(
        project_a,
        "SELECT coalesce(string_agg(p.oid::regprocedure::text, ','), '') FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'api' "
        "AND has_function_privilege('public', p.oid, 'EXECUTE');",
    )
    assert leaked == "", f"PUBLIC can execute {leaked}"


def test_the_retired_write_rpc_is_gone(project_a: dict[str, Any]) -> None:
    """ADR 0048's retirement, asserted as an absence.

    ADR 0003 argued that operation 4 is a narrow status transition rather than a
    second create, and Session 3 shipped a second create. The convergence
    migration drops it, and this is the assertion that the drop happened rather
    than the grant merely being revoked.
    """
    present = sql(
        project_a,
        "SELECT coalesce(string_agg(p.proname, ',' ORDER BY p.proname), '') FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'api';",
    )
    assert present == "create_note,update_task_status", present


def test_the_write_rpc_derives_ownership_from_the_claim(
    project_a: dict[str, Any], roles: dict[str, str]
) -> None:
    """There is no owner parameter, so the claim is the only lever."""
    observed = as_role(
        project_a,
        roles["authenticated"],
        "SELECT (api.create_note('derived')).owner_id;",
        claim=OWNER_A,
    )
    assert observed == OWNER_A, observed


def test_the_write_rpc_refuses_without_a_claim(
    project_a: dict[str, Any], roles: dict[str, str]
) -> None:
    observed = as_role(project_a, roles["authenticated"], "SELECT api.create_note('nobody');")
    assert "AP401" in observed, observed


def test_the_write_rpcs_pin_their_search_path(project_a: dict[str, Any]) -> None:
    """On a SECURITY DEFINER function this is not hygiene, it is the boundary.

    Without a pinned search_path a caller who can create a temporary object
    shadows an unqualified name and has it executed as the owner.
    """
    observed = sql(
        project_a,
        "SELECT string_agg(p.proname || '=' || "
        "coalesce(array_to_string(p.proconfig, ','), 'NONE'), ' ' ORDER BY p.proname) "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'api' AND p.prosecdef;",
    )
    assert (
        "search_path=pg_catalog, pg_temp" in observed
        or "search_path=pg_catalog,pg_temp" in observed
    ), observed


# ---------------------------------------------------------------------------
# SEC-OWNER-001 and SEC-DB-001 — role attributes
# ---------------------------------------------------------------------------


def test_the_object_owner_is_a_non_login_role(
    project_a: dict[str, Any], roles: dict[str, str]
) -> None:
    observed = sql(
        project_a, f"SELECT rolcanlogin FROM pg_roles WHERE rolname = '{roles['object_owner']}';"
    )
    assert observed == "f", "the object owner can log in"


def test_no_runtime_role_holds_a_dangerous_attribute(
    project_a: dict[str, Any], roles: dict[str, str]
) -> None:
    """Read from pg_roles, never inferred from how a role was created."""
    names = "', '".join(sorted(roles.values()))
    observed = sql(
        project_a,
        f"SELECT coalesce(string_agg(rolname, ','), '') FROM pg_roles WHERE rolname IN ('{names}') "
        "AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls);",
    )
    assert observed == "", f"roles hold dangerous attributes: {observed}"


def test_only_the_activated_roles_may_log_in(
    project_a: dict[str, Any], roles: dict[str, str]
) -> None:
    """The login set is derived from the deployed document, not written down.

    Plan §6.3: every service identity is a NOLOGIN stub **until its owning
    session activates it deliberately**. This test asserted the Session 3 half of
    that sentence — ``observed in ("", migration_user)`` — and never encoded the
    clause. Session 4 activates ``app_runtime`` with a credential, which is the
    entire point of the session (ADR 0041), and this went red the first time the
    whole host suite ran after that happened, five runs later (D124, ADR 0046).

    What replaces it is stricter in three ways rather than looser in one:

    *Equality, not membership.* The old assertion's ``""`` branch accepted a
    cluster where the migration user could not log in at all — a broken
    deployment reported as a passing security property.

    *Derived from ``access_profiles``.* A role that gains LOGIN without being
    published as a profile fails, and a profile published without its role being
    able to log in fails. The catalog and the document have to agree.

    *Still closed.* Any other service identity gaining LOGIN fails, which was the
    original point and is unchanged.

    **Session 5 added a third source, and finding out cost a gate run** (D211,
    ADR 0072). `postgrest_authenticator` is activated with LOGIN because a
    service authenticates as it, and it is not an access profile -- profiles are
    the transports a *developer or an application* reaches the cluster through.
    So the role was activated, correct, and invisible in the document. This test
    is in `tests/security/`, which the deployment sweep does not select, so five
    host runs passed without it executing once.

    The clause is derived like the others: a deployment whose **REST route is
    published** has an authenticator that can log in; one whose route is not,
    does not. Naming the role as an exception would have been the weakening this
    repository forbids -- it would pass on a Session 4 deployment that had
    somehow activated it, which is precisely the case this test exists to catch.
    """
    profiles = project_a["database"]["access_profiles"]
    # `migration_user` is Session 3's own activation and is expected on any
    # deployment this module runs against; the profile roles are whatever the
    # deployed session published. On a Session 3 deployment no profile is
    # available, and the expected set is exactly the one name the old assertion
    # allowed.
    expected = {roles["migration_user"]} | {
        profile["role"] for profile in profiles.values() if profile["status"] == "available"
    }

    # The REST plane's own identity, read from the route the document publishes
    # rather than from the session number: a deployment that serves the surface
    # has a service logging in as this role, and the status is the document's
    # own statement about whether it does.
    if (project_a["routes"].get("rest") or {}).get("status") == "ready":
        expected.add(roles["postgrest_authenticator"])

    # Session 6's identity plane, keyed the same way and for the same reason
    # (ADR 0046, ADR 0096). `auth_service` is activated with LOGIN because the
    # auth container authenticates as it -- and, like the authenticator, it is
    # not an access profile, because a profile is a transport a developer or an
    # application reaches the cluster through.
    #
    # Keyed on the ROUTE rather than on `deployed_through_session >= 6`: a
    # session number is a proxy for the event, and D280 is what a proxy costs
    # when the two come apart. A document that publishes an application route is
    # a deployment that runs the service; one that does not, does not.
    if project_a["routes"].get("app") is not None:
        expected.add(roles["auth_service"])

    names = "', '".join(sorted(roles.values()))
    observed = sql(
        project_a,
        f"SELECT coalesce(string_agg(rolname, ',' ORDER BY rolname), '') FROM pg_roles "
        f"WHERE rolname IN ('{names}') AND rolcanlogin;",
    )
    assert {name for name in observed.split(",") if name} == expected, (
        f"roles with LOGIN are {observed!r}; the deployed document says the "
        f"activated set is {sorted(expected)}"
    )


# ---------------------------------------------------------------------------
# DBX-MIG-001 — the two planes are distinct
# ---------------------------------------------------------------------------


def test_the_migration_membership_options_are_read_from_the_catalog(
    project_a: dict[str, Any], roles: dict[str, str]
) -> None:
    """ADR 0026: the membership option columns, not the role's own rolinherit.

    They are different switches, and PostgreSQL 16 made the per-membership one
    govern. A test reading `rolinherit` would stay green if the membership were
    later granted with INHERIT TRUE, which is the regression it exists to catch.
    """
    observed = sql(
        project_a,
        "SELECT m.admin_option || ' ' || m.inherit_option || ' ' || m.set_option "
        "FROM pg_auth_members m "
        "JOIN pg_roles member ON member.oid = m.member "
        "JOIN pg_roles grantor ON grantor.oid = m.roleid "
        f"WHERE member.rolname = '{roles['migration_user']}' "
        f"AND grantor.rolname = '{roles['object_owner']}';",
    )
    assert observed == "false false true", (
        f"expected admin=false inherit=false set=true, got {observed!r}"
    )
