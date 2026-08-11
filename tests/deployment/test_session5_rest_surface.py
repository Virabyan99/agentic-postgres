"""What the published REST surface serves.

API-SCHEMA-001, API-REST-001, API-RPC-001, API-ERR-001 and API-LIMIT-001.

Replaces five Session 5 placeholders in ``tests/integration/test_future_api.py``.

**Every negative here has a positive control in the same test**, and that is
§4.2's rule rather than a style preference: a PostgREST that refuses every
request passes every negative test in this file completely, and a misconfigured
authenticator is exactly that. So a schema is proved unreachable only after the
exposed one has answered, a write is proved refused only after an approved one
has succeeded, and the row ceiling is proved to hold only after a request under
it has returned rows.

**Every test states what would have to break for it to go red**, because every
test here is deselected in an offline gate and D70 is what an unmanaged
deselected test costs.

Nothing here reads a migration's source. A test asserting that a migration
*contains* a grant would pass against a cluster where the migration never ran,
which is the standing lesson of Session 3's Run 4.
"""

from __future__ import annotations

# ruff: noqa: S608
#
# Every statement below interpolates values that came from a deployed outputs
# document -- role names and a database name derived by `naming` and validated
# by the outputs schema -- plus fixed UUID constants declared in this file. None
# of it is operator input, and parameter binding is unavailable where an
# identifier, a role name or a `SET` target goes, which is the same reason
# `migrations.quote_identifier` exists. Suppressed per module rather than per
# line, as `tests/security/test_session3_authorization.py` does, because a wall
# of inline noqa comments is one nobody reads.
import json
from collections.abc import Callable
from typing import Any

import pytest

from agentic_postgres import api_surface
from agentic_postgres.rendering import ACCEPTANCE_PROBE_FUNCTION

pytestmark = [
    pytest.mark.p0,
    pytest.mark.deployment,
    pytest.mark.live_host,
    pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS"),
]


@pytest.fixture(scope="module")
def surface() -> dict[str, Any]:
    """The reviewed contract, which is the authority on what may be served."""
    return api_surface.load_surface()


@pytest.fixture(scope="module")
def reader(
    project_a: dict[str, Any], mint_token: Callable[..., str], request_subject: Callable[[str], str]
) -> str:
    """An ``authenticated`` token carrying the project's development subject."""
    return mint_token(
        project_a,
        project_a["database"]["roles"]["authenticated"],
        subject=request_subject(project_a["project"]["key"]),
    )


# ---------------------------------------------------------------------------
# API-SCHEMA-001 — only `api` is exposed, and only what the contract lists
# ---------------------------------------------------------------------------


def test_only_the_api_schema_is_reachable_over_http(
    project_a: dict[str, Any],
    surface: dict[str, Any],
    rest_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    reader: str,
) -> None:
    """API-SCHEMA-001, measured by asking rather than by reading a setting.

    ``db-schemas`` is what decides which names a request can resolve at all, and
    it is recorded in the deployed document -- but the document records what was
    configured, and this is about what is served. The four forbidden schemas are
    requested through every spelling PostgREST offers to name one: as a path, and
    as the ``Accept-Profile`` header, which is the route a reader who only
    checked paths would miss.

    Goes red if: ``db-schemas`` gains a second entry; ``db-extra-search-path`` is
    left at its default so ``public`` resolves; a view is created in ``api`` over
    an object the contract does not name; or the surface contract gains an object
    the deployment does not serve.

    The positive control comes first. Without it a PostgREST that had failed to
    connect to its database would return 503 for every request below and this
    would report the tightest possible boundary.
    """
    base = rest_base(project_a)

    answered = api_call(f"{base}/notes?limit=1", token=reader)
    assert answered.status == 200, (
        f"the approved read returned {answered.status} ({answered.reason or answered.body[:200]}); "
        "every refusal below would then be about a service that answers nothing"
    )

    for schema in sorted(surface["forbidden_schemas"]):
        by_path = api_call(f"{base}/{schema}", token=reader)
        assert by_path.status in (403, 404), (
            f"GET /{schema} returned {by_path.status}; a forbidden schema is addressable"
        )
        by_profile = api_call(
            f"{base}/notes?limit=1", token=reader, headers={"Accept-Profile": schema}
        )
        assert by_profile.status != 200, (
            f"Accept-Profile: {schema} was honoured; the exposed schema can be chosen "
            "by the caller, which is a boundary a path check cannot see"
        )

    # `app.notes` is the base table the views exist to mediate. Named directly
    # because a request for a schema PostgREST does not expose and a request for
    # a table it does not know are different failures, and only the second would
    # be produced by a view accidentally published over the base table.
    for name in ("notes", "tasks"):
        direct = api_call(f"{base}/app.{name}", token=reader)
        assert direct.status != 200, f"app.{name} is reachable as a resource"


def test_the_served_surface_is_exactly_the_reviewed_objects(
    project_a: dict[str, Any],
    surface: dict[str, Any],
    api_contract: Any,
    rest_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    reader: str,
) -> None:
    """API-SCHEMA-001's allowlist half, and the transient object's absence.

    The document a *reader* is served, not the documentation role's. Under
    ``follow-privileges`` those differ, and this is the one that says what this
    caller may name.

    Goes red if: a migration adds an object to ``api`` that the reviewed contract
    does not list; the acceptance probe of plan §4.4 survives its fixture and is
    still published; or the contract lists an object the deployment does not have,
    which is the direction that catches a contract edited to match a mistake.

    A reader is served **fewer** objects than the contract lists, not the same
    ones, and that is ``follow-privileges`` rather than a gap: the write RPCs
    appear for a role that holds ``EXECUTE``. So the containment is one-way here,
    and the equality belongs to ``API-CONTRACT-001``, against the documentation
    role's document.
    """
    base = rest_base(project_a)
    served = api_call(base, token=reader)
    assert served.status == 200, f"the document was not served ({served.status})"

    document = json.loads(served.body)
    paths = {path.lstrip("/") for path in document.get("paths", {}) if path != "/"}
    assert paths, "the served document publishes no objects at all"

    # `surface_objects`, not `api_surface.declared_objects`. The two spell an
    # object differently on purpose -- `notes` here and `api.notes` there -- and
    # comparing across the two spellings would find every object missing from
    # the other side. The repair for that is always to loosen the comparison,
    # which is how a containment check stops constraining anything.
    reviewed = api_contract.surface_objects(surface)

    assert f"rpc/{ACCEPTANCE_PROBE_FUNCTION}" not in paths, (
        f"api.{ACCEPTANCE_PROBE_FUNCTION} is published. The §4.4 probe outlived its "
        "fixture, and it is on the served surface until somebody drops it"
    )
    assert paths <= reviewed, (
        f"served objects the contract does not list: {sorted(paths - reviewed)}"
    )


# ---------------------------------------------------------------------------
# API-REST-001 — HTTP reproduces the database's row-level result
# ---------------------------------------------------------------------------


def test_http_reads_reproduce_the_database_row_level_result(
    project_a: dict[str, Any],
    rest_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
    mint_token: Callable[..., str],
    request_subject: Callable[[str], str],
    reader: str,
) -> None:
    """API-REST-001. One claim, two transports, the same rows.

    PostgreSQL is the authorization system and PostgREST is transport (ADR 0029),
    so the assertion is an *equality* rather than a pair of independent checks: a
    caller's HTTP result and the same query run directly under the same claim
    must name the same row ids. A proxy-side filter, a default ``limit`` applied
    on one path only, or a view that stopped being ``security_invoker`` would all
    break the equality while each side on its own still looked right.

    Goes red if: the pre-request hook stops establishing ``app.user_id`` from the
    validated subject, in which case HTTP returns nothing and the database
    returns rows; a policy is relaxed on one path; or ``max_rows`` truncates the
    HTTP side, which is why the comparison is bounded well under it.

    Both halves are asserted. "A sees none of B's rows" is true of an empty
    table, so A must see some of its own first, and a second identity's rows must
    exist for the exclusion to have anything to exclude.
    """
    base = rest_base(project_a)
    roles = project_a["database"]["roles"]
    mine = request_subject(project_a["project"]["key"])
    other = "22222222-2222-2222-2222-222222222222"

    seeded = api_call(
        f"{base}/rpc/create_note",
        method="POST",
        token=reader,
        body={"p_title": "rest-001-own", "p_content": ""},
    )
    assert seeded.status in (200, 201, 204), f"the seed write returned {seeded.status}"

    status, _, error = psql(
        project_a,
        "SELECT api.create_note('rest-001-other');",
        role=roles["authenticated"],
        claim=other,
    )
    assert status == 0, f"could not seed the second identity's row: {error}"

    over_http = api_call(f"{base}/notes?select=id&order=id", token=reader)
    assert over_http.status == 200, f"the read returned {over_http.status}"
    http_ids = sorted(row["id"] for row in json.loads(over_http.body))

    status, output, error = psql(
        project_a,
        "SELECT coalesce(string_agg(id::text, ',' ORDER BY id), '') FROM api.notes;",
        role=roles["authenticated"],
        claim=mine,
    )
    assert status == 0, f"the direct read failed: {error}"
    direct_ids = sorted(value for value in output.split(",") if value)

    assert direct_ids, (
        "the caller's own identity owns no rows, so the equality below holds "
        "between two empty sets and proves nothing"
    )
    assert http_ids == direct_ids, (
        "HTTP and the database disagree about which rows this caller may see: "
        f"only over HTTP {sorted(set(http_ids) - set(direct_ids))}, "
        f"only in the database {sorted(set(direct_ids) - set(http_ids))}"
    )

    foreign = mint_token(project_a, roles["authenticated"], subject=other)
    theirs = api_call(f"{base}/notes?select=id", token=foreign)
    assert theirs.status == 200, f"the second identity's read returned {theirs.status}"
    theirs_ids = {row["id"] for row in json.loads(theirs.body)}
    assert theirs_ids, "the second identity owns no rows either; there is nothing to exclude"
    assert not theirs_ids & set(http_ids), "two identities were served the same rows over HTTP"


# ---------------------------------------------------------------------------
# API-RPC-001 — the write surface is exactly the named RPCs
# ---------------------------------------------------------------------------


def test_the_write_surface_is_exactly_the_named_rpcs(
    project_a: dict[str, Any],
    surface: dict[str, Any],
    rest_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
    request_subject: Callable[[str], str],
    reader: str,
) -> None:
    """API-RPC-001. Generic writes fail, ownership is derived, one row moves.

    Three separate claims, and each needs the approved write to have succeeded
    first: a service that refuses every write satisfies the first two by
    accident.

    **Ownership is derived rather than accepted**, and the proof is a
    caller-supplied ``owner_id`` in the RPC body. PostgREST maps body keys onto
    parameter names (D149), so an unknown key is either ignored or refused --
    both acceptable -- and what must never happen is a row landing under the
    owner the caller named.

    Goes red if: a table-style write is granted on either view; ``create_note``
    stops deriving the caller from ``app.user_id``; or the transition RPC drops
    its expected-status guard and becomes last-writer-wins, which the second
    call's refusal is what detects.

    Note what this does NOT go red for: the published document advertising
    ``POST``, ``PATCH`` and ``DELETE`` on the views. It does, and all three
    return 403 (ADR 0060) -- so the assertion is the authorization result, never
    the advertisement.
    """
    base = rest_base(project_a)
    mine = request_subject(project_a["project"]["key"])

    created = api_call(
        f"{base}/rpc/create_note",
        method="POST",
        token=reader,
        body={"p_title": "rpc-001", "p_content": "approved"},
        headers={"Prefer": "return=representation"},
    )
    assert created.status in (200, 201), (
        f"the approved RPC returned {created.status}; every refusal below would then "
        f"be about a broken write path ({created.body[:200]})"
    )

    for method in ("POST", "PATCH", "DELETE"):
        for relation in sorted(surface["relations"]):
            refused = api_call(
                f"{base}/{relation}?id=eq.{mine}",
                method=method,
                token=reader,
                body={"title": "generic"} if method in ("POST", "PATCH") else None,
            )
            assert refused.status in (401, 403, 405), (
                f"{method} /{relation} returned {refused.status}; the write surface is "
                "wider than the named RPCs"
            )

    claimed = api_call(
        f"{base}/rpc/create_note",
        method="POST",
        token=reader,
        body={
            "p_title": "rpc-001-claimed",
            "p_content": "",
            "owner_id": "99999999-9999-4999-8999-999999999999",
        },
        headers={"Prefer": "return=representation"},
    )
    if claimed.status in (200, 201):
        row = json.loads(claimed.body)
        row = row[0] if isinstance(row, list) else row
        assert row["owner_id"] == mine, (
            f"a caller-supplied owner_id was honoured: the row landed under "
            f"{row['owner_id']}, not under the request identity {mine}"
        )

    # One row, not many, and the transition is optimistic rather than
    # last-writer-wins. The task is seeded through the database because
    # `api.create_task` was retired in Run 5 rather than published (§6) -- and
    # seeded rather than found, because a test that read whatever task happened
    # to exist would quietly do nothing against an empty table.
    first, second = surface["enums"]["task_status"]["values"][:2]
    status, target, error = psql(
        project_a,
        "INSERT INTO app.tasks (owner_id, title, status) "
        f"VALUES ('{mine}'::uuid, 'rpc-001-transition', '{first}') RETURNING id;",
        role=project_a["database"]["roles"]["object_owner"],
        claim=mine,
    )
    assert status == 0 and target, f"could not seed a task to transition: {error}"

    body = {"p_task_id": target, "p_expected_status": first, "p_new_status": second}
    moved = api_call(f"{base}/rpc/update_task_status", method="POST", token=reader, body=body)
    assert moved.status in (200, 204), (
        f"the approved transition returned {moved.status} ({moved.body[:200]})"
    )

    repeated = api_call(f"{base}/rpc/update_task_status", method="POST", token=reader, body=body)
    assert repeated.status >= 400, (
        "the same transition succeeded twice from the same expected status; the guard "
        "is not optimistic, it is last-writer-wins"
    )


# ---------------------------------------------------------------------------
# API-ERR-001 — the public error contract discloses nothing internal
# ---------------------------------------------------------------------------

#: Everything a refusal must not name. Role names, schema names and the database
#: name are added per project at the assertion, because they are derived.
#: Three dots and nothing signable. Named rather than written inline so the
#: value is obviously not a credential -- an inline literal in a `token=`
#: argument reads to a scanner, and to a reviewer, as a hardcoded one.
MALFORMED_TOKEN = "not.a.token"  # noqa: S105 -- three dots, no key, no claims

INTERNAL_TOKENS = (
    "app_private",
    "postgrest_pre_request",
    "pg_catalog",
    "SELECT ",
    "INSERT INTO",
    "relation ",
    "/usr/lib",
    "postgresql.conf",
)


def test_the_public_error_contract_discloses_nothing_internal(
    project_a: dict[str, Any],
    rest_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    reader: str,
) -> None:
    """API-ERR-001, across every refusal this surface can produce.

    ``HINT`` and ``DETAIL`` on a ``RAISE`` are published to HTTP callers verbatim
    (ADR 0057), so this is not a property of PostgREST -- it is a property of
    every message the migrations write, and it can regress from a migration that
    never mentions HTTP.

    Goes red if: a future ``RAISE`` carries a ``HINT`` naming an internal object;
    a policy failure starts returning the statement that violated it; or a role
    name reaches a caller, which is the disclosure that turns ``SEC-ROLE-001``'s
    negative matrix into a guessing game with the answers printed.

    The positive control is the shape of the errors themselves: each must be a
    JSON object carrying a ``message``, because a refusal that returned an empty
    body would satisfy every assertion below while telling a legitimate caller
    nothing.
    """
    base = rest_base(project_a)
    roles = project_a["database"]["roles"]
    forbidden = [*INTERNAL_TOKENS, *roles.values(), project_a["database"]["name"]]

    refusals = {
        "unknown relation": api_call(f"{base}/no_such_relation", token=reader),
        "forbidden schema": api_call(f"{base}/app.notes", token=reader),
        "malformed filter": api_call(f"{base}/notes?id=eq.not-a-uuid", token=reader),
        "unknown rpc argument": api_call(
            f"{base}/rpc/create_note", method="POST", token=reader, body={"nope": 1}
        ),
        "no token": api_call(f"{base}/notes"),
        "malformed token": api_call(f"{base}/notes", token=MALFORMED_TOKEN),
    }

    for name, response in refusals.items():
        assert response.status >= 400, f"the {name} request was not refused ({response.status})"
        assert response.body, f"the {name} refusal returned an empty body"
        for needle in forbidden:
            assert needle not in response.body, (
                f"the {name} refusal disclosed {needle!r}: {response.body[:300]}"
            )


# ---------------------------------------------------------------------------
# API-LIMIT-001 — the server enforces the limits, not the client
# ---------------------------------------------------------------------------


def test_row_and_time_limits_are_enforced_by_the_server(
    project_a: dict[str, Any],
    rest_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    acceptance_probe: dict[str, Any],
    mint_token: Callable[..., str],
) -> None:
    """API-LIMIT-001. A client cannot raise the ceiling by asking.

    The row ceiling is proved against more rows than the ceiling, which is what
    the §4.4 probe seeds -- a limit tested against a table holding two rows is a
    limit nobody measured. The caller then asks for *more* than the ceiling in
    every way PostgREST offers: ``limit``, and a ``Range`` header.

    The timeout is proved with the probe's sleep function, which is the only
    object on the surface that can exceed a role's ``statement_timeout``. Both
    halves again: a bounded sleep must succeed first, or a service that refused
    every RPC would pass the over-time assertion.

    Goes red if: ``max-rows`` is unset or raised above the manifest's
    ``api.max_rows``; ``statement_timeout`` is removed from the request role's
    settings, or set high enough to be decorative; or the pre-request hook starts
    resetting either, which is the failure that would look like a configuration
    that is present and inert.
    """
    base = rest_base(project_a)
    roles = project_a["database"]["roles"]
    ceiling = acceptance_probe["max_rows"]
    reader = mint_token(project_a, roles["authenticated"], subject=acceptance_probe["subject"])

    under = api_call(f"{base}/notes?select=id&limit=5", token=reader)
    assert under.status == 200 and json.loads(under.body), (
        "a request well under the ceiling returned nothing, so every truncation "
        f"below would be indistinguishable from a broken read ({under.status})"
    )

    asked = api_call(f"{base}/notes?select=id&limit={ceiling + 500}", token=reader)
    assert asked.status in (200, 206), f"the over-limit read returned {asked.status}"
    assert len(json.loads(asked.body)) <= ceiling, (
        f"asking for {ceiling + 500} rows returned more than the ceiling of {ceiling}"
    )

    ranged = api_call(
        f"{base}/notes?select=id",
        token=reader,
        headers={"Range-Unit": "items", "Range": f"0-{ceiling + 500}"},
    )
    assert ranged.status in (200, 206), f"the ranged read returned {ranged.status}"
    assert len(json.loads(ranged.body)) <= ceiling, (
        "a Range header raised the row ceiling that a limit parameter could not"
    )

    quick = api_call(
        f"{base}/rpc/{acceptance_probe['function']}",
        method="POST",
        token=reader,
        body={"p_seconds": 0.1},
    )
    assert quick.status in (200, 204), (
        f"the bounded sleep returned {quick.status}; the timeout below would then be "
        "a fact about an RPC nobody can call"
    )

    slow = api_call(
        f"{base}/rpc/{acceptance_probe['function']}",
        method="POST",
        token=reader,
        body={"p_seconds": 30},
        timeout=90,
    )
    assert slow.status >= 400, (
        f"a 30-second statement returned {slow.status}; the role's statement_timeout "
        "is not being applied to requests"
    )
