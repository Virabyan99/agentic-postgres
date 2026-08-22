"""Migrations 0007, 0008 and 0009: the surface they leave, and the rules they follow.

Offline, against the template text and against the reviewed contract. None of it
needs a cluster, and that is the point: the drift ADR 0048 records survived two
sessions because every test that could have caught it was written *from the
code*, so the code always agreed with itself. These read the contract on one
side and the SQL on the other.

The SQL side is a deliberately small interpreter -- `CREATE VIEW`, `DROP VIEW`,
`CREATE FUNCTION`, `DROP FUNCTION`, `CREATE TYPE … AS ENUM`, applied in manifest
order -- and `test_the_reader_is_not_vacuous` asserts it found something before
anything else compares against it. A parser that silently matched nothing would
make every comparison below pass.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, api_surface, migrations

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.database]

TEMPLATES = REPO_ROOT / "migrations" / "templates"

#: The three Session 5 migrations, by template name.
CONVERGENCE = "templates/0007-api-surface-convergence.sql"
REQUEST_PLANE = "templates/0008-http-request-plane.sql"
DOCUMENTATION_ROLE = "templates/0009-documentation-role.sql"
STATEMENT_TIMEOUT = "templates/0010-request-statement-timeout.sql"
#: Session 6 Run 9. The fourth migration to define the hook: it adds the
#: comparison against current state.
AGENT_PLANE = "templates/0013-agent-plane-and-current-state-hook.sql"

#: Session 8 Run 2. The FIFTH migration to define the hook, and therefore the
#: effective one: it adds the `token_use` branch that establishes an agent's
#: owner (ADR 0117). Written from 0013's body rather than from memory of it
#: (D270) -- `test_the_agent_branch_is_0013s_body_plus_a_branch` is what holds
#: that, mechanically, rather than the comment claiming it.
AGENT_READ_PLANE = "templates/0018-agent-read-plane.sql"

_CREATE_VIEW = re.compile(r"CREATE VIEW api\.(\w+)\b.*?AS\s+SELECT\s+(.*?)\s+FROM\b", re.DOTALL)
_DROP_VIEW = re.compile(r"DROP VIEW api\.(\w+)")
_CREATE_FUNCTION = re.compile(
    r"CREATE (?:OR REPLACE )?FUNCTION api\.(\w+)\s*\((.*?)\)\s*\n\s*RETURNS", re.DOTALL
)
_DROP_FUNCTION = re.compile(r"DROP FUNCTION api\.(\w+)")
_CREATE_ENUM = re.compile(r"CREATE TYPE api\.(\w+) AS ENUM \((.*?)\)", re.DOTALL)

#: A `RAISE EXCEPTION` and everything up to the statement terminator, so the
#: `USING` clause that follows it is part of the match.
_RAISE = re.compile(r"RAISE EXCEPTION\s+(.*?);", re.DOTALL)


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    return migrations.load_manifest()


@pytest.fixture(scope="module")
def surface() -> dict[str, Any]:
    return api_surface.load_surface()


def template_text(name: str) -> str:
    return (REPO_ROOT / "migrations" / name).read_text(encoding="utf-8")


#: The declaration every hook test has to be written against.
#:
#: The `()` is load-bearing and was added after a mutation stayed green: without
#: it this is a *prefix*, so renaming the function to `postgrest_pre_request_v2`
#: still matched and the migration that no longer defines the hook still counted
#: as defining it. D162's shape -- a prefix standing in for an exact match --
#: one file over (D200).
HOOK_DEFINITION = "CREATE OR REPLACE FUNCTION app_private.postgrest_pre_request()"


def effective_hook_template(manifest: dict[str, Any]) -> str:
    """The template whose body is the hook that actually runs.

    Read out of the manifest in applied order rather than named as a constant,
    because `CREATE OR REPLACE` means the *last* migration to define the
    function is the only one whose body a request ever executes.

    This exists because of what Run 7 nearly shipped. Migration 0009 replaces
    the hook, and every test below was written against 0008 -- so they would all
    have stayed green while describing a function no request runs. That is this
    repository's signature defect with the green test on the wrong side of it,
    and the repair is not to update a constant but to stop having one.
    """
    defining = [
        entry["template"]
        for entry in manifest["migrations"]
        if HOOK_DEFINITION in sql_only(up_section(template_text(entry["template"])))
    ]
    assert defining, "no migration defines the pre-request hook"
    return defining[-1]


def up_section(text: str) -> str:
    """Only the applied half. A `migrate:down` block is unreachable SQL."""
    return text.split("-- migrate:down")[0]


def sql_only(text: str) -> str:
    """The statements, with the reasoning stripped out.

    Needed because these files argue with themselves: the comment above the
    pre-request hook explains that `pg_catalog.nullif` is the spelling that
    broke, so a test forbidding that string matched the sentence forbidding it.
    That is Session 2 Run 7's defect exactly -- a substitution that also matched
    the comment documenting the substitution -- and the fix is the same one.

    Line comments only. None of these templates has a `--` inside a string
    literal, and a test that quietly stopped working if one appeared would be
    worse than one that never handled the case: `test_the_reader_is_not_vacuous`
    and the positive assertions below both fail if this strips too much.
    """
    return "\n".join(line.split("--")[0] for line in text.splitlines())


def statements(name: str) -> str:
    """One template's applied statements, with its reasoning removed."""
    return sql_only(up_section(template_text(name)))


@pytest.fixture(scope="module")
def final_surface(manifest: dict[str, Any]) -> dict[str, Any]:
    """What `api` holds after every released migration has been applied, in order."""
    views: dict[str, list[str]] = {}
    functions: dict[str, list[str]] = {}
    enums: dict[str, list[str]] = {}

    for entry in manifest["migrations"]:
        body = statements(entry["template"])

        for name in _DROP_VIEW.findall(body):
            views.pop(name, None)
        for name in _DROP_FUNCTION.findall(body):
            functions.pop(name, None)

        for name, columns in _CREATE_VIEW.findall(body):
            views[name] = [column.strip() for column in columns.replace("\n", " ").split(",")]
        for name, arguments in _CREATE_FUNCTION.findall(body):
            # Parameter names only: the wire format is the name, and the type is
            # what the contract deliberately does not carry.
            functions[name] = [
                argument.strip().split()[0]
                for argument in arguments.replace("\n", " ").split(",")
                if argument.strip()
            ]
        for name, values in _CREATE_ENUM.findall(body):
            enums[name] = [value.strip().strip("'") for value in values.split(",")]

    return {"views": views, "functions": functions, "enums": enums}


def test_the_reader_is_not_vacuous(final_surface: dict[str, Any]) -> None:
    """Before any comparison: the interpreter above found real objects.

    A regex that matched nothing would make every equality below hold against
    two empty sets, which is the failure mode of every contract comparison and
    the one this file exists to avoid producing itself.
    """
    assert set(final_surface["views"]) == {"notes", "tasks"}, final_surface["views"]
    # Six functions in `api` since Session 9 Run 1: the two published write
    # RPCs, the two agent-plane read functions migration 0018 adds (ADR 0118),
    # and the two audit functions 0019 adds (ADR 0135, ADR 0136). Written out
    # rather than read from the contract, deliberately -- this is the test that
    # proves the reader found something, so comparing it against the document
    # every other test compares against would let an empty scrape agree with an
    # empty contract.
    assert set(final_surface["functions"]) == {
        "create_note",
        "update_task_status",
        "mcp_agent_context",
        "owner_activity_report",
        "agent_audit_begin",
        "agent_audit_complete",
    }
    assert set(final_surface["enums"]) == {"task_status"}
    assert all(final_surface["views"].values())
    assert final_surface["enums"]["task_status"]


# ---------------------------------------------------------------------------
# The migrations against the reviewed contract (ADR 0048, ADR 0050)
# ---------------------------------------------------------------------------


def test_the_published_relations_are_the_reviewed_ones(
    final_surface: dict[str, Any], surface: dict[str, Any]
) -> None:
    assert set(final_surface["views"]) == set(surface["relations"])


def test_every_published_column_is_the_reviewed_column_list(
    final_surface: dict[str, Any], surface: dict[str, Any]
) -> None:
    """Order included. The view's `SELECT` order is the document's column order."""
    for name, relation in surface["relations"].items():
        assert final_surface["views"][name] == relation["columns"], name


def test_the_write_surface_is_the_reviewed_rpcs(
    final_surface: dict[str, Any], surface: dict[str, Any]
) -> None:
    """`create_task` is the one that matters.

    ADR 0003 argued at length that operation 4 is a narrow status transition
    rather than a second create, and Session 3 shipped a second create. This is
    the assertion that would have failed for two sessions.

    **Three sections, since Session 9 Run 1.** The migrations create six
    functions in `api`, and ADR 0050's invariant is that the reviewed contract
    names every one of them -- the two published RPCs under `rpcs`, the two
    agent-plane reads under `agent_rpcs` (ADR 0118), and the two audit functions
    under `agent_write_rpcs` (ADR 0136), which is a section of its own because
    they write and therefore take arguments. The union is what the catalog
    holds; the split is which of them the document may advertise, and
    `test_no_agent_plane_function_is_published` is where that half is asserted.
    A comparison against `rpcs` alone would now fail for a correct release,
    and the repair for that is always to loosen the comparison.
    """
    reviewed = set(surface["rpcs"]) | set(surface["agent_rpcs"]) | set(surface["agent_write_rpcs"])
    assert set(final_surface["functions"]) == reviewed
    assert "create_task" not in final_surface["functions"]

    # Pairwise disjoint, stated as three comparisons rather than one over a
    # union, so a name in two sections says WHICH two. A function in both
    # `agent_rpcs` and `agent_write_rpcs` would be claiming at once that it
    # takes nothing and that it takes arguments.
    sections = {
        "rpcs": set(surface["rpcs"]),
        "agent_rpcs": set(surface["agent_rpcs"]),
        "agent_write_rpcs": set(surface["agent_write_rpcs"]),
    }
    for left, right in (
        ("rpcs", "agent_rpcs"),
        ("rpcs", "agent_write_rpcs"),
        ("agent_rpcs", "agent_write_rpcs"),
    ):
        assert not sections[left] & sections[right], (
            f"a function is named in both {left} and {right}; the sections differ in "
            "what may be advertised and in what may reach a query string, so a name "
            "in two of them is a contradiction"
        )


def test_every_rpc_parameter_is_the_reviewed_parameter(
    final_surface: dict[str, Any], surface: dict[str, Any]
) -> None:
    """These strings are the wire format, not labels for it (D149).

    PostgREST maps JSON body keys straight onto PostgreSQL parameter names, so a
    contract naming `p_body` against a function taking `p_content` describes a
    request no caller can send.
    """
    for name, rpc in surface["rpcs"].items():
        assert final_surface["functions"][name] == rpc["arguments"], name


def test_the_enum_values_are_the_reviewed_ones_in_order(
    final_surface: dict[str, Any], surface: dict[str, Any]
) -> None:
    """ADR 0003's four values, given the executable form ADR 0058 requires.

    Compared as a sequence: `enumsortorder` decides the order the generated
    OpenAPI document lists them in, and a set comparison would let a reordering
    through while changing what every generated client shows first.
    """
    for name, declared in surface["enums"].items():
        assert final_surface["enums"][name] == declared["values"], name


def test_the_status_type_lives_in_the_schema_that_is_published(
    surface: dict[str, Any],
) -> None:
    """The published `format` string is the type's schema-qualified name.

    Measured on the locked PostgREST: a column of `app.task_status` publishes
    the literal `app.task_status` in the served document, naming a schema this
    contract's `forbidden_schemas` exists to keep unaddressable (ADR 0058).
    """
    body = statements(CONVERGENCE)
    assert "CREATE TYPE api.task_status" in body
    for forbidden in surface["forbidden_schemas"]:
        assert f"CREATE TYPE {forbidden}.task_status" not in body


def test_the_declared_type_is_a_declared_object(surface: dict[str, Any]) -> None:
    """`api.task_status` is reachable through the module's own accessor.

    Kept separate from `declared_objects` because the two are compared against
    different catalogs, and a single set would report a missing type and a
    missing view identically.
    """
    assert api_surface.declared_types(surface) == {"api.task_status"}
    assert not api_surface.declared_types(surface) & api_surface.declared_objects(surface)


# ---------------------------------------------------------------------------
# ADR 0057 — the public error contract
# ---------------------------------------------------------------------------


def raises_in(name: str) -> list[str]:
    return [match.strip() for match in _RAISE.findall(statements(name))]


@pytest.mark.parametrize(
    "template", [CONVERGENCE, REQUEST_PLANE, DOCUMENTATION_ROLE, STATEMENT_TIMEOUT]
)
def test_no_caller_reachable_raise_publishes_a_hint_or_a_detail(template: str) -> None:
    """Measured: PostgREST publishes `HINT` and `DETAIL` to the caller verbatim.

    0005 raised `AP401` with `HINT = 'SET LOCAL app.user_id before calling this
    function.'` -- written for a developer at a psql prompt in a session where
    nothing served HTTP, and on its way to becoming a public sentence naming an
    internal GUC in answer to an unauthenticated request.

    The exemption is `AP900`, which only a `migrate:down` block and the
    derivation guard raise. Neither is reachable over HTTP, and both are read by
    an operator holding a terminal, for whom the hint is the useful part.
    """
    for raise_statement in raises_in(template):
        if "AP900" in raise_statement:
            continue
        assert "HINT" not in raise_statement, raise_statement
        assert "DETAIL" not in raise_statement, raise_statement


@pytest.mark.parametrize(
    "template", [CONVERGENCE, REQUEST_PLANE, DOCUMENTATION_ROLE, STATEMENT_TIMEOUT]
)
def test_every_caller_reachable_raise_names_its_status(template: str) -> None:
    """A bare `RAISE EXCEPTION` leaves the SQLSTATE at `P0001`, which is 400.

    Which is the wrong answer for every code this surface raises -- most sharply
    for "no request identity", where 400 tells a client nothing about needing to
    authenticate and carries no `WWW-Authenticate` challenge.
    """
    for raise_statement in raises_in(template):
        if "AP900" in raise_statement:
            continue
        assert "ERRCODE = 'PT" in raise_statement, raise_statement


def test_the_status_codes_are_the_measured_ones() -> None:
    """Each `PT` code, once, against the status it was measured to produce."""
    measured = {
        "PT401": "AP401",
        "PT404": "AP404",
        "PT409": "AP409",
        "PT422": "AP422",
    }
    body = statements(CONVERGENCE) + statements(REQUEST_PLANE)
    for sqlstate in measured:
        assert f"ERRCODE = '{sqlstate}'" in body, f"{sqlstate} is measured and never raised"

    for raise_statement in raises_in(CONVERGENCE) + raises_in(REQUEST_PLANE):
        if "AP900" in raise_statement:
            continue
        sqlstate = re.search(r"ERRCODE = '(PT\d+)'", raise_statement)
        assert sqlstate is not None, raise_statement
        assert measured[sqlstate.group(1)] in raise_statement, (
            f"{raise_statement} raises {sqlstate.group(1)} under a different "
            "application code than the one it was measured with"
        )


# ---------------------------------------------------------------------------
# Migration 0007's traps
# ---------------------------------------------------------------------------


def test_the_views_are_dropped_and_recreated_rather_than_replaced() -> None:
    """A view keeps its own output column names across a base-column rename.

    A view stores references by attribute number, so `RENAME COLUMN body TO
    content` leaves `api.notes` working and still publishing a column called
    `body`. `CREATE OR REPLACE VIEW` cannot rename an output column either. Both
    roads lead to a read surface that looks migrated and is not.
    """
    body = statements(CONVERGENCE)
    assert "RENAME COLUMN body TO content" in body
    assert "DROP VIEW api.notes" in body
    assert "CREATE OR REPLACE VIEW" not in body


def test_the_write_rpc_is_dropped_rather_than_replaced() -> None:
    """`CREATE OR REPLACE FUNCTION` cannot rename a parameter (D149)."""
    body = statements(CONVERGENCE)
    assert "DROP FUNCTION api.create_note(text, text)" in body
    assert "CREATE OR REPLACE FUNCTION api." not in body


def test_the_derivation_restores_forced_row_level_security_and_reads_it_back() -> None:
    """The dangerous three lines of this migration.

    The row policies key on `app.current_user_id()`, which is NULL inside a
    migration, so an `UPDATE` under FORCE matches **zero rows and reports
    success**. The derivation therefore runs with FORCE off -- and a migration
    that failed to put it back would leave every SECURITY DEFINER write in this
    schema able to write any row, silently.
    """
    body = statements(CONVERGENCE)
    assert body.count("ALTER TABLE app.tasks NO FORCE ROW LEVEL SECURITY;") == 1
    assert body.count("ALTER TABLE app.tasks FORCE ROW LEVEL SECURITY;") == 1
    assert body.index("NO FORCE ROW LEVEL SECURITY") < body.index("UPDATE app.tasks"), (
        "the derivation runs before FORCE is lifted, so it updates nothing"
    )
    assert body.index("UPDATE app.tasks") < body.index(
        "ALTER TABLE app.tasks FORCE ROW LEVEL SECURITY;"
    )
    assert "relforcerowsecurity" in body, "the restoration is claimed and never read back"


def test_the_derivation_is_total_or_the_migration_fails() -> None:
    """ADR 0048 requires every existing row to map, and says so in SQL."""
    body = statements(CONVERGENCE)
    assert "WHERE status IS NULL" in body
    assert "AP900" in body
    assert body.index("status IS NULL") < body.index("ALTER COLUMN status SET NOT NULL")


def test_the_retired_function_loses_its_grants_before_it_is_dropped() -> None:
    """ADR 0048 retires `create_task` by revoking and then dropping it."""
    body = statements(CONVERGENCE)
    assert body.index("REVOKE ALL ON FUNCTION api.create_task") < body.index(
        "DROP FUNCTION api.create_task"
    )


def test_every_new_function_revokes_public_before_it_grants(
    final_surface: dict[str, Any], manifest: dict[str, Any]
) -> None:
    """What actually carries SEC-DEFAULT-001 on the locked image (D57).

    And Run 5 measured a second consequence: `openapi-mode = follow-privileges`
    follows a PUBLIC grant too, so a function left with PostgreSQL's default
    EXECUTE is advertised in the document an anonymous caller receives.

    **Over every migration, in applied order, since Session 8 Run 2.** It used
    to read migration 0007 alone while looping over every function in `api` --
    which held only while 0007 happened to be where all of them were granted.
    Migration 0018 adds two more and the loop raised `ValueError: substring not
    found`: a test failing because its subject moved rather than because the
    property did.

    The property is an ORDERING, and it spans files. PUBLIC must lose `EXECUTE`
    **no later than the first grant of that function**, wherever each happens.
    A later migration that adds a grantee needs no revoke of its own -- 0009
    grants `create_note` to the documentation role and 0007 already owns that
    revoke, which is D337's reasoning -- and demanding one would have failed a
    correct release. What is refused is a grant that arrives while PUBLIC still
    holds `EXECUTE`, which is the window an anonymous caller could use and the
    window `follow-privileges` would advertise.

    Strictly stronger than the single-file form: it now sees a function granted
    in one migration and revoked in a later one, which is the same defect spread
    across two files and was invisible before.
    """
    revoked: set[str] = set()
    granted: set[str] = set()
    for entry in manifest["migrations"]:
        body = statements(entry["template"])
        for name in final_surface["functions"]:
            revoke = body.find(f"REVOKE ALL ON FUNCTION api.{name}")
            grant = body.find(f"GRANT EXECUTE ON FUNCTION api.{name}")
            if grant != -1:
                within = revoke != -1 and revoke < grant
                assert name in revoked or within, (
                    f"{entry['template']} grants api.{name} while PUBLIC still holds "
                    "EXECUTE. A function is EXECUTABLE BY PUBLIC the moment it exists "
                    "(D57), and follow-privileges advertises it to an anonymous caller"
                )
                granted.add(name)
            if revoke != -1:
                revoked.add(name)

    assert granted == set(final_surface["functions"]), (
        f"no migration grants EXECUTE on {sorted(set(final_surface['functions']) - granted)}, "
        "so it exists in the exposed schema and no role can call it"
    )


@pytest.mark.parametrize(
    "template", [CONVERGENCE, REQUEST_PLANE, DOCUMENTATION_ROLE, STATEMENT_TIMEOUT]
)
def test_a_migration_that_touches_the_api_notifies_the_schema_cache(template: str) -> None:
    """The cache is a copy, and a stale one serves the previous surface.

    After `RESET ROLE`, so the notification is issued by the migration plane
    rather than by a role it assumed -- and at the end, so a failure earlier in
    the migration cannot leave a reload announced for a change that rolled back.
    """
    body = statements(template)
    assert "NOTIFY pgrst, 'reload schema';" in body
    assert body.index("RESET ROLE;") < body.index("NOTIFY pgrst")


# ---------------------------------------------------------------------------
# Migration 0008 — the pre-request hook and the one grant
# ---------------------------------------------------------------------------


def test_the_hook_writes_nothing(manifest: dict[str, Any]) -> None:
    """PostgREST runs it inside the request transaction, read-only on a GET.

    Measured: an early version kept an audit row, and every read of the API came
    back **405 "cannot execute INSERT in a read-only transaction"** -- a write
    hidden in a hook turning the whole read surface off.
    """
    body = statements(effective_hook_template(manifest))
    function = body[body.index(HOOK_DEFINITION) :]
    function = function[: function.index("$fn$;")]
    for statement in ("INSERT", "UPDATE", "DELETE", "CREATE TABLE", "COPY"):
        assert statement not in function, f"the pre-request hook contains {statement}"


def test_the_hook_pins_its_search_path_and_stays_invoker(manifest: dict[str, Any]) -> None:
    body = statements(effective_hook_template(manifest))
    assert "SECURITY INVOKER" in body
    assert "SET search_path = pg_catalog, pg_temp" in body


def test_the_hook_does_not_qualify_the_one_name_that_cannot_be_qualified(
    manifest: dict[str, Any],
) -> None:
    """`nullif` is a SQL construct the parser rewrites into a CASE.

    Measured, and it took the whole API down: `pg_catalog.nullif(text, unknown)
    does not exist`, raised by the hook, on every request, while the service
    stayed healthy and the schema cache stayed warm. Being a construct is also
    why it needs no qualification -- nothing on a search_path can shadow it.
    """
    body = statements(effective_hook_template(manifest))
    assert "pg_catalog.nullif" not in body
    assert "nullif(" in body
    # The functions that *are* real lookups stay qualified.
    assert "pg_catalog.current_setting" in body
    assert "pg_catalog.set_config" in body


def test_the_hook_refuses_a_subject_that_is_not_a_uuid(manifest: dict[str, Any]) -> None:
    """Measured: `"sub": "not-a-uuid"` reached the row policy and came back as
    **400 `invalid input syntax for type uuid`** -- a raw cast error, produced by
    a policy, on every request. Refused here it is one 401 from one place.
    """
    body = statements(effective_hook_template(manifest))
    assert "[0-9a-fA-F]{8}-" in body
    assert body.index("[0-9a-fA-F]{8}-") < body.index("set_config('app.user_id'")


def test_the_claim_is_transaction_local(manifest: dict[str, Any]) -> None:
    """`set_config(..., true)` is `SET LOCAL`.

    Without the `true`, one request's asserted identity outlives it on a pooled
    connection and becomes the next request's -- the single most dangerous
    failure available in this design, and the one the pooler's
    `server_reset_query_always` exists to prevent from the other side.
    """
    body = statements(effective_hook_template(manifest))
    assert "set_config('app.user_id', subject, true)" in body


def test_malformed_claims_fail_closed(manifest: dict[str, Any]) -> None:
    """ "Unreadable" and "absent" look identical one line later and mean
    opposite things about who is asking."""
    body = statements(effective_hook_template(manifest))
    handler = body[body.index("EXCEPTION WHEN others THEN") :]
    assert "RAISE EXCEPTION" in handler[:400]
    assert "PT401" in handler[:400]


def test_the_private_schema_is_granted_to_the_request_roles_and_no_others(
    manifest: dict[str, Any],
) -> None:
    """ADR 0052 bounds the grant by name; this is the enumeration.

    The two agent roles are Session 9's and are deliberately not granted to the
    authenticator, so PostgREST cannot become either -- and a USAGE grant to a
    role that can never make a request would widen the private schema to buy
    nothing.
    """
    entry = next(e for e in manifest["migrations"] if e["template"] == REQUEST_PLANE)
    assert set(entry["placeholders"]) == {"object_owner", "anon", "authenticated"}

    body = statements(REQUEST_PLANE)
    grant = re.search(r"GRANT USAGE ON SCHEMA app_private TO ([^;]+);", body)
    assert grant is not None
    assert set(re.findall(r"\{\{(\w+)\}\}", grant.group(1))) == {"anon", "authenticated"}


def test_public_keeps_nothing_on_the_hook() -> None:
    """A grant to PUBLIC reaches every role whatever is granted by name after it,
    so the enumeration above is only an enumeration if this runs first."""
    body = statements(REQUEST_PLANE)
    assert body.index("REVOKE ALL ON FUNCTION app_private.postgrest_pre_request() FROM PUBLIC") < (
        body.index("GRANT USAGE ON SCHEMA app_private")
    )


# ---------------------------------------------------------------------------
# Migration 0009 -- the documentation role (D158)
# ---------------------------------------------------------------------------


def test_the_effective_hook_is_the_last_migration_that_defines_it(
    manifest: dict[str, Any],
) -> None:
    """The control for every hook test, and the reason they were repointed.

    Until Run 7 the hook tests read migration 0008 by name. 0009 replaces the
    function, so every one of them would have stayed green while describing a
    body no request executes -- a value that looked measured and was not.

    It went red the day 0010 replaced the hook, which is exactly what it is
    for, and it is repointed rather than relaxed (ADR 0068). Every migration
    that has ever defined the function is listed, in applied order, and the
    effective one is read from the manifest -- so an 0011 fails here too.
    """
    defining = [
        entry["template"]
        for entry in manifest["migrations"]
        if HOOK_DEFINITION in statements(entry["template"])
    ]
    assert defining == [
        REQUEST_PLANE,
        DOCUMENTATION_ROLE,
        STATEMENT_TIMEOUT,
        AGENT_PLANE,
        AGENT_READ_PLANE,
    ]
    assert effective_hook_template(manifest) == AGENT_READ_PLANE


def test_the_documentation_role_is_refused_a_request_identity(
    manifest: dict[str, Any],
) -> None:
    """The clause the whole role depends on (D158).

    Measured on the locked PostgREST before this was written: a documentation
    token carrying a subject, with no such clause, established an identity and
    the role **wrote a row**. With the clause it is 401 `PT401`, and a bare
    documentation token calling the same RPC is 403 `new row violates row-level
    security policy` -- it publishes the write and cannot perform it.

    Read from the *effective* hook rather than from 0009, which is where this
    clause was introduced. Migration 0010 restates the function in full, so
    reading 0009 would assert this clause of a body no request executes.
    """
    body = statements(effective_hook_template(manifest))
    clause = body[body.index("IF current_user::text = {{api_documentation_name}}") :]
    # The second `END IF;`, not the first: the inner one closes the
    # subject-present branch and the outer one closes the role check. Slicing at
    # the first would test half the clause and miss the `RETURN` that is the
    # whole point -- the refusal to establish an identity at all.
    inner = clause.index("END IF;") + len("END IF;")
    clause = clause[: clause.index("END IF;", inner) + len("END IF;")]

    assert "PT401" in clause, "a documentation token carrying a subject must be refused"
    assert "RETURN;" in clause, "and one without a subject must proceed with no identity"
    assert "set_config" not in clause, "the clause must never establish an identity"


def test_the_hook_does_not_qualify_current_user_either(manifest: dict[str, Any]) -> None:
    """Migration 0008's `nullif` lesson, in the one other place it applies.

    `current_user` is a SQL construct the parser rewrites, not a function to look
    up, so `pg_catalog.current_user` is a hook that fails on every request while
    the service stays healthy. Measured both ways; the cast is what works.
    """
    body = statements(effective_hook_template(manifest))
    assert "pg_catalog.current_user" not in body
    assert "current_user::text" in body


def test_the_documentation_role_holds_the_surface_and_the_hook_and_nothing_else() -> None:
    """`follow-privileges` publishes only what the role can reach.

    Measured: a role with view SELECT and no EXECUTE is served a complete
    document with **no write RPC in it at all**, so the EXECUTE grants are what
    make the published document describe the write surface. What makes granting
    them safe is the clause above, not this list.
    """
    body = statements(DOCUMENTATION_ROLE)
    granted = re.findall(r"GRANT ([A-Z ,]+?) ON (?:SCHEMA |FUNCTION )?(\S+)", body)
    subjects = {target.rstrip("(,;") for _, target in granted}
    assert "api.notes," in body and "api.tasks" in body
    assert "api.create_note(text," in subjects or "api.create_note(text," in body
    assert "api.update_task_status(uuid," in body
    assert "app_private.postgrest_pre_request()" in body

    # No write grant on a view, ever. The role is not meant to be able to write,
    # and a grant it does not hold is one fewer thing depending on the hook.
    for statement in re.findall(r"GRANT [^;]+;", body):
        if "api.notes" in statement or "api.tasks" in statement:
            assert "INSERT" not in statement, statement
            assert "UPDATE" not in statement, statement
            assert "DELETE" not in statement, statement


def test_the_documentation_role_gets_the_private_schema_pair(
    manifest: dict[str, Any],
) -> None:
    """ADR 0052's grant, extended by name to the third request role.

    PostgREST runs `db-pre-request` after the role switch, so a role without
    EXECUTE on the hook cannot make a request at all -- including the one that
    fetches the document it exists to be shown.
    """
    entry = next(e for e in manifest["migrations"] if e["template"] == DOCUMENTATION_ROLE)
    assert set(entry["placeholders"]) == {
        "object_owner",
        "api_documentation",
        "api_documentation_name",
    }

    body = statements(DOCUMENTATION_ROLE)
    grant = re.search(r"GRANT USAGE ON SCHEMA app_private TO ([^;]+);", body)
    assert grant is not None
    assert set(re.findall(r"\{\{(\w+)\}\}", grant.group(1))) == {"api_documentation"}


def test_the_two_role_placeholders_read_one_source(manifest: dict[str, Any]) -> None:
    """The identifier and the literal must name the same role.

    They are two placeholders because a `GRANT` needs a quoted identifier and
    `current_user::text = ...` needs a string literal. Resolving both from one
    key in one document is what makes them incapable of disagreeing -- a role
    name written out beside the grant could, and the hook would then refuse an
    identity to a role nothing granted anything to, silently.
    """
    placeholders = manifest["placeholders"]
    assert placeholders["api_documentation"]["type"] == "identifier"
    assert placeholders["api_documentation_name"]["type"] == "literal"
    assert (
        placeholders["api_documentation"]["source"]
        == placeholders["api_documentation_name"]["source"]
        == "database.roles.api_documentation"
    )


def test_the_documentation_role_keeps_the_private_defaults_closed() -> None:
    """0008 closed them for `anon` and `authenticated`; a role added afterwards
    would otherwise inherit whatever a later `CREATE TABLE` in `app_private`
    grants."""
    body = statements(DOCUMENTATION_ROLE)
    for kind in ("TABLES", "SEQUENCES"):
        assert re.search(
            r"ALTER DEFAULT PRIVILEGES FOR ROLE \{\{object_owner\}\} IN SCHEMA app_private\s+"
            r"REVOKE ALL ON " + kind + r" FROM \{\{api_documentation\}\}",
            body,
        ), kind


# ---------------------------------------------------------------------------
# Migration 0010 -- the request's statement timeout (D198, ADR 0068)
# ---------------------------------------------------------------------------


def test_the_hook_carries_the_roles_statement_timeout(manifest: dict[str, Any]) -> None:
    """The whole of ADR 0068, asserted on the body that runs.

    PostgreSQL processes a role's settings only at login and PostgREST reaches
    its request role with `SET LOCAL ROLE`, so a timeout on the role bounded
    nothing until something carried it. Measured before this was written: with
    the hook, a 5-second statement is cancelled at 2.0s; without it, it returns
    200 after 5.0s.
    """
    body = statements(effective_hook_template(manifest))
    assert "pg_db_role_setting" in body, "the hook no longer reads the role's own setting"
    assert "set_config('statement_timeout'" in body


def test_the_carried_timeout_is_transaction_local(manifest: dict[str, Any]) -> None:
    """A session-level set would outlive the request on a pooled connection.

    The same reason `app.user_id` is transaction-local: PgBouncer hands the same
    server connection to the next caller, and a bound left behind is a bound
    applied to whoever is next -- or, worse, a bound *removed* for them.
    """
    body = statements(effective_hook_template(manifest))
    call = body[body.index("set_config('statement_timeout'") :]
    call = call[: call.index(";") + 1]
    assert "true" in call, f"the timeout is not set transaction-locally: {call}"


def test_the_timeout_is_carried_before_every_early_return(manifest: dict[str, Any]) -> None:
    """The documentation role and an anonymous caller return early, and both hold
    a connection while they do.

    A bound applied after those returns would be a bound on exactly the callers
    who authenticated -- which is the half of the surface least in need of it.
    """
    body = statements(effective_hook_template(manifest))
    carried = body.index("set_config('statement_timeout'")
    assert carried < body.index("IF current_user::text = {{api_documentation_name}}")
    assert carried < body.index("IF raw IS NULL THEN")


def test_the_hook_is_not_security_definer(manifest: dict[str, Any]) -> None:
    """Measured: a plain role reads `pg_db_role_setting` directly.

    So a definer function would be a privilege boundary bought for nothing --
    and the first draft of this carrier *was* one, which is why it is worth a
    test rather than a comment. `SECURITY DEFINER` makes `current_user` the
    function's owner, so the lookup asked for the owner's timeout, found none,
    set nothing, and looked exactly like a hook that ran and found nothing to
    do. It measured green as "no bound configured".
    """
    # The FUNCTION, not the file. From 0013 the same template also creates
    # `auth_claims_are_current`, which IS a definer -- deliberately, because the
    # hook runs as the impersonated role and cannot read `app_private.users`.
    # A scan of the whole file would now report the hook as a definer, which is
    # a test measuring the wrong text rather than a change in the hook.
    body = statements(effective_hook_template(manifest))
    start = body.index("CREATE OR REPLACE FUNCTION app_private.postgrest_pre_request()")
    end = body.index("END $fn$;", start)
    hook = body[start:end]

    assert "SECURITY INVOKER" in hook
    assert "SECURITY DEFINER" not in hook, (
        "the pre-request hook is a definer; `current_user` would be the function's "
        "owner and the timeout lookup would ask for the owner's bound, find none, "
        "and look exactly like a hook that ran and found nothing to do"
    )


def test_the_timeout_lookup_matches_the_role_the_request_became(
    manifest: dict[str, Any],
) -> None:
    """`current_user` after the role switch, not `session_user`.

    `session_user` is the authenticator, which every request shares -- so a
    lookup keyed on it would apply one project-wide bound and would be
    indistinguishable from a correct one on any cluster where the authenticator
    happens to carry a setting.
    """
    body = statements(effective_hook_template(manifest))
    lookup = body[body.index("pg_db_role_setting") :]
    lookup = lookup[: lookup.index("LIMIT 1")]
    assert "current_user::text" in lookup
    assert "session_user" not in lookup


# ---------------------------------------------------------------------------
# Migration 0018 -- the agent read plane (Session 8, ADR 0116/0117/0118)
# ---------------------------------------------------------------------------


def _hook_statement_lines(template: str) -> list[str]:
    """The hook definition's STATEMENTS, comments stripped.

    Comments are prose and move legitimately. What must not move is the code,
    so the comparison below is over the lines that execute.
    """
    body = TEMPLATES.joinpath(template.removeprefix("templates/")).read_text("utf-8")
    start = body.index(HOOK_DEFINITION)
    end = body.index("END $fn$;", start) + len("END $fn$;")
    return [
        line.rstrip()
        for line in body[start:end].splitlines()
        if line.strip() and not line.strip().startswith("--")
    ]


def _agent_branch(body: str) -> str:
    """The agent branch, ending where the human branch begins.

    NOT at the first `END IF;`: that one closes the nested credential_version
    check, and slicing there returns a fragment containing neither the
    comparison call nor the two `set_config` statements -- so every assertion
    below would fail against a correct migration, which is how a test ends up
    loosened to make it pass.
    """
    marker = "IF token_use = 'agent' THEN"
    assert marker in body, (
        "the effective hook has no `token_use` branch. Either the agent plane was removed, "
        "or the discriminator moved -- and if it moved to `current_user` that is D393's "
        "mechanism, a boundary standing on a correlation between the authenticator's "
        "memberships and the two subject registries"
    )
    start = body.index(marker)
    end = body.index("IF NOT app_private.auth_claims_are_current", start)
    return body[start:end]


def _collapsed(name: str) -> str:
    """One template's statements with runs of whitespace collapsed.

    The grant lists wrap across lines, so a search for `GRANT EXECUTE ON
    FUNCTION <name>` finds nothing in the raw text and finds it here. Collapsing
    is safe for these assertions: they look for identifiers and role
    placeholders, none of which contains a newline.
    """
    return " ".join(statements(name).split())


def test_the_agent_branch_is_0013s_body_plus_a_branch() -> None:
    """**D270, asserted mechanically rather than claimed in a comment.**

    `postgrest_pre_request` is defined in five migrations and only the last one
    runs. A redefinition assembled from an older body silently deletes
    everything the versions between added -- here, 0010's statement-timeout
    carry, 0009's documentation-role clause and 0013's current-state comparison.
    All three would still be present in the FILE that introduced them, and every
    test reading that file would stay green while no request executed it.

    So this compares 0018's hook against 0013's, line by line, and asserts that
    **nothing was removed**. A comment saying "written from 0013's body" is
    exactly the kind of claim D267 warns about: the next reader cannot tell it
    from the ones that are true.

    Goes red if: any statement line of 0013's hook is absent from 0018's; or
    0018 stops adding a branch at all, which would make it a pointless
    redefinition of a body that already ran.
    """
    import difflib

    old = _hook_statement_lines(AGENT_PLANE)
    new = _hook_statement_lines(AGENT_READ_PLANE)

    removed = [
        line[1:]
        for line in difflib.unified_diff(old, new, lineterm="", n=0)
        if line.startswith("-") and not line.startswith("---")
    ]
    assert not removed, (
        f"0018's hook drops {len(removed)} statement line(s) 0013's had: {removed[:5]}. "
        "Only the last definition runs, so a line dropped here is a line deleted from "
        "the deployment (D270)"
    )
    assert len(new) > len(old), (
        "0018 redefines the hook and adds nothing, which is a replacement of a body "
        "that already ran"
    )


def test_the_agent_branch_discriminates_on_the_token_use_claim(
    manifest: dict[str, Any],
) -> None:
    """ADR 0117: `token_use`, not the physical role.

    Branching on `current_user` would work today, because the authenticator's
    memberships happen to line up with the two registries -- and **that is the
    mechanism D393 was**, a boundary standing on a correlation that changes
    silently the day it stops holding. `token_use` is the only claim in the
    token minted to discriminate.

    The `credential_version` check is asserted with it because the two are one
    decision: D397 made `0` a value rather than an absence so that "not a human"
    could be READ, and a branch that did not check it would be trusting the
    convention instead.
    """
    body = statements(effective_hook_template(manifest))
    branch = _agent_branch(body)

    assert "claims ->> 'token_use'" in body, "the hook never reads the discriminating claim"
    assert "credential_version <> 0" in branch, (
        "the agent branch does not check the credential_version convention, so a token "
        "claiming to be an agent while carrying a human's version is accepted (D397)"
    )
    assert "agent_claims_are_current" in branch
    assert "current_user" not in branch, (
        "the agent branch reads the physical role. Role and token_use are independent "
        "claims, so a boundary on the role is a boundary on a correlation (D393)"
    )


def test_an_agent_request_establishes_its_owner_and_not_itself(
    manifest: dict[str, Any],
) -> None:
    """ADR 0117, and the assertion the whole read plane rests on.

    Every RLS policy in 0003 keys on `app.user_id`. An agent that established
    its own `sub` there would see nothing -- no note is owned by an agent -- and
    every tool would return zero rows while every test passed. `app.agent_id` is
    set beside it and no policy reads it: it says WHICH principal asked, and is
    deliberately not an authorization input.
    """
    body = statements(effective_hook_template(manifest))
    branch = _agent_branch(body)

    assert "set_config('app.user_id', agent_owner::text, true)" in branch, (
        "the agent branch does not establish the OWNER as app.user_id, so the policies "
        "in 0003 -- which key on exactly that GUC -- return nothing for every agent"
    )
    assert "set_config('app.agent_id', subject, true)" in branch
    assert "set_config('app.user_id', subject, true)" not in branch, (
        "the agent branch establishes the AGENT as the RLS principal. No row is owned "
        "by an agent, so this reads as a working plane that returns nothing"
    )


def test_the_agent_comparison_matches_the_whole_claim_tuple() -> None:
    """0013's rule, applied to the agent helper (ADR 0117).

    A function answering "what are agent X's scopes" would let anything that
    reaches the hook enumerate every agent's authority, and the hook is not
    something a request can decline to run. Matching on the whole tuple makes a
    probe cost a correct guess of all four values.

    `status = 'active'` is asserted separately because it is the one that makes
    a disabled agent stop on its NEXT request rather than at its token's expiry.
    """
    body = statements(AGENT_READ_PLANE)
    start = body.index("CREATE FUNCTION app_private.agent_claims_are_current")
    definition = body[start : body.index("$fn$;", start)]

    for predicate in (
        "a.id            = p_agent_id",
        "a.status        = 'active'",
        "a.role_name     = p_role_name",
        "a.authz_version = p_authz_version",
        "a.scopes        = p_scopes",
    ):
        assert predicate in definition, f"the agent comparison does not match on {predicate!r}"
    assert "SECURITY DEFINER" in definition
    assert "SET search_path = pg_catalog, pg_temp" in definition, (
        "a definer function with an unpinned search_path is shadowable by any caller "
        "that can create a temporary object (D263)"
    )


def test_the_report_is_an_invoker_and_the_context_is_a_definer() -> None:
    """The two functions differ in the one attribute that decides what they see.

    `owner_activity_report` is SECURITY INVOKER, so the caller's own RLS bounds
    the counts and the function needs no policy of its own. A definer report
    would count every owner's rows and hand back totals the caller has no right
    to -- and it would look identical from outside until a second owner existed.

    `mcp_agent_context` is SECURITY DEFINER because `app_private.agents` is
    unreachable by every request role and stays that way (ADR 0052): the agent
    role gets EXECUTE on the function and no privilege on the table behind it.
    """
    body = statements(AGENT_READ_PLANE)

    report_start = body.index("CREATE FUNCTION api.owner_activity_report")
    report = body[report_start : body.index("$fn$;", report_start)]
    assert "SECURITY INVOKER" in report
    assert "SECURITY DEFINER" not in report, (
        "the report is a definer, so it counts every owner's rows regardless of who "
        "asked -- and looks correct until a second owner exists"
    )
    assert "app.notes" not in report and "app.tasks" not in report, (
        "the report reads the base tables, which needs USAGE on schema `app` -- the "
        "grant 0004 withholds so that a security_invoker view works and direct access "
        "does not. Counting rows must not widen that boundary"
    )

    context_start = body.index("CREATE FUNCTION api.mcp_agent_context")
    context = body[context_start : body.index("$fn$;", context_start)]
    assert "SECURITY DEFINER" in context
    assert "mcp_agent_context()" in body, "the context function takes an argument"
    assert "current_setting('app.agent_id', true)" in context, (
        "the context function does not read the request's own agent, so it either "
        "takes a subject from somewhere else or describes nobody"
    )


def test_the_agent_role_gets_what_it_needs_to_run_the_hook() -> None:
    """ADR 0116: activating a role is a grant list, and an incomplete one fails closed.

    `EXECUTE` requires schema `USAGE`, and the hook runs AFTER the role switch
    (measured in 0008), so it runs as the agent role. Without both, every agent
    request fails in `db-pre-request` -- which is D381's shape: a role declared
    a request role in four places and handed no way to run the one function
    every request runs.

    **Both comparison helpers, to all five roles.** `role` and `token_use` are
    independent claims, so every combination of physical role and hook branch is
    reachable by a request. Measured on the locked image: a human token naming
    the agent role was refused with `permission denied for function
    auth_claims_are_current` rather than `AP401` -- correct outcome, false
    reason, which is D393 arriving through a missing grant.
    """
    body = _collapsed(AGENT_READ_PLANE)
    assert "GRANT USAGE ON SCHEMA app_private TO {{agent_reader}}" in body

    for function in (
        "app_private.postgrest_pre_request()",
        "app_private.agent_claims_are_current(uuid, text, text[], integer)",
    ):
        start = body.index(f"GRANT EXECUTE ON FUNCTION {function}")
        grant = body[start : body.index(";", start)]
        for role in ("anon", "authenticated", "api_documentation", "project_admin", "agent_reader"):
            assert f"{{{{{role}}}}}" in grant, (
                f"{function} is not granted to {role}. Every role that runs the hook can "
                "reach both branches, because role and token_use are independent claims"
            )

    human_helper = (
        "GRANT EXECUTE ON FUNCTION "
        "app_private.auth_claims_are_current(uuid, text, text[], integer, integer)"
    )
    start = body.index(human_helper)
    assert "{{agent_reader}}" in body[start : body.index(";", start)], (
        "0013's human comparison helper is not extended to the agent role, so a human "
        "token naming that role is refused by a missing GRANT rather than by the hook"
    )


def test_the_agent_functions_are_not_granted_to_the_documentation_role() -> None:
    """ADR 0118, and it is the grant that decides publication.

    `openapi-mode = follow-privileges` builds the document as
    `api_documentation`, so withholding EXECUTE is the whole mechanism keeping
    the agent plane out of the human REST document. A grant added here would
    publish both functions and nothing else would say so --
    `test_no_agent_plane_function_is_published` is the other half, and it reads
    the generated artefact rather than this file.
    """
    body = _collapsed(AGENT_READ_PLANE)
    for function in ("api.mcp_agent_context()", "api.owner_activity_report()"):
        start = body.index(f"GRANT EXECUTE ON FUNCTION {function}")
        grant = body[start : body.index(";", start)]
        assert "{{api_documentation}}" not in grant, (
            f"{function} is granted to the documentation role, which publishes it in the "
            "document follow-privileges builds as that role (ADR 0118)"
        )
        assert "{{agent_reader}}" in grant

    report_start = body.index("GRANT EXECUTE ON FUNCTION api.owner_activity_report()")
    assert "{{authenticated}}" not in body[report_start : body.index(";", report_start)], (
        "the report is granted to `authenticated`, which makes it a fifth human "
        "operation -- and ADR 0003's example domain is frozen"
    )


def test_the_reset_role_is_below_the_privileges_block() -> None:
    """D285, and it took a live project down in Session 6.

    `REVOKE` and `GRANT EXECUTE ON FUNCTION` both require ownership. A
    `RESET ROLE` above them runs both as the CONNECTED role, which on a host is
    `migration_user` -- and that role owns nothing.

    Every offline rig that applies migrations as `psql -U postgres` misses this,
    because a superuser bypasses the ownership check entirely. This reads the
    text; `test_every_released_migration_applies_as_the_migration_user` is what
    executes it as the right role.
    """
    body = statements(AGENT_READ_PLANE)
    assert body.index("RESET ROLE") > body.index("REVOKE ALL ON FUNCTION")
    assert body.index("RESET ROLE") > body.rindex("GRANT EXECUTE ON FUNCTION")
    assert body.index("SET LOCAL ROLE") < body.index("CREATE FUNCTION")
