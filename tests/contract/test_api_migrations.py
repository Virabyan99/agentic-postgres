"""Migrations 0007 and 0008: the surface they leave, and the rules they follow.

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

#: The two Session 5 migrations, by template name.
CONVERGENCE = "templates/0007-api-surface-convergence.sql"
REQUEST_PLANE = "templates/0008-http-request-plane.sql"

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
    assert set(final_surface["functions"]) == {"create_note", "update_task_status"}
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
    """
    assert set(final_surface["functions"]) == set(surface["rpcs"])
    assert "create_task" not in final_surface["functions"]


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


@pytest.mark.parametrize("template", [CONVERGENCE, REQUEST_PLANE])
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


@pytest.mark.parametrize("template", [CONVERGENCE, REQUEST_PLANE])
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
    final_surface: dict[str, Any],
) -> None:
    """What actually carries SEC-DEFAULT-001 on the locked image (D57).

    And Run 5 measured a second consequence: `openapi-mode = follow-privileges`
    follows a PUBLIC grant too, so a function left with PostgreSQL's default
    EXECUTE is advertised in the document an anonymous caller receives.
    """
    body = statements(CONVERGENCE)
    for name in final_surface["functions"]:
        revoke = body.index(f"REVOKE ALL ON FUNCTION api.{name}")
        grant = body.index(f"GRANT EXECUTE ON FUNCTION api.{name}")
        assert revoke < grant, name


@pytest.mark.parametrize("template", [CONVERGENCE, REQUEST_PLANE])
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


def test_the_hook_writes_nothing() -> None:
    """PostgREST runs it inside the request transaction, read-only on a GET.

    Measured: an early version kept an audit row, and every read of the API came
    back **405 "cannot execute INSERT in a read-only transaction"** -- a write
    hidden in a hook turning the whole read surface off.
    """
    body = statements(REQUEST_PLANE)
    function = body[body.index("CREATE OR REPLACE FUNCTION app_private.postgrest_pre_request") :]
    function = function[: function.index("$fn$;")]
    for statement in ("INSERT", "UPDATE", "DELETE", "CREATE TABLE", "COPY"):
        assert statement not in function, f"the pre-request hook contains {statement}"


def test_the_hook_pins_its_search_path_and_stays_invoker() -> None:
    body = statements(REQUEST_PLANE)
    assert "SECURITY INVOKER" in body
    assert "SET search_path = pg_catalog, pg_temp" in body


def test_the_hook_does_not_qualify_the_one_name_that_cannot_be_qualified() -> None:
    """`nullif` is a SQL construct the parser rewrites into a CASE.

    Measured, and it took the whole API down: `pg_catalog.nullif(text, unknown)
    does not exist`, raised by the hook, on every request, while the service
    stayed healthy and the schema cache stayed warm. Being a construct is also
    why it needs no qualification -- nothing on a search_path can shadow it.
    """
    body = statements(REQUEST_PLANE)
    assert "pg_catalog.nullif" not in body
    assert "nullif(" in body
    # The functions that *are* real lookups stay qualified.
    assert "pg_catalog.current_setting" in body
    assert "pg_catalog.set_config" in body


def test_the_hook_refuses_a_subject_that_is_not_a_uuid() -> None:
    """Measured: `"sub": "not-a-uuid"` reached the row policy and came back as
    **400 `invalid input syntax for type uuid`** -- a raw cast error, produced by
    a policy, on every request. Refused here it is one 401 from one place.
    """
    body = statements(REQUEST_PLANE)
    assert "[0-9a-fA-F]{8}-" in body
    assert body.index("[0-9a-fA-F]{8}-") < body.index("set_config('app.user_id'")


def test_the_claim_is_transaction_local() -> None:
    """`set_config(..., true)` is `SET LOCAL`.

    Without the `true`, one request's asserted identity outlives it on a pooled
    connection and becomes the next request's -- the single most dangerous
    failure available in this design, and the one the pooler's
    `server_reset_query_always` exists to prevent from the other side.
    """
    body = statements(REQUEST_PLANE)
    assert "set_config('app.user_id', subject, true)" in body


def test_malformed_claims_fail_closed() -> None:
    """ "Unreadable" and "absent" look identical one line later and mean
    opposite things about who is asking."""
    body = statements(REQUEST_PLANE)
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
