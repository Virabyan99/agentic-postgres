"""The agent WRITE plane, against the deployment (Session 9 Runs 5-6).

**Its own module, and not a section of `test_session8_agent_plane.py`.** The
Session 8 module's agent is an `agent_reader`; every proof here needs an
`agent_writer`, which Session 9 activated (ADR 0137). The plan also asks for
fixtures to stop landing in `tests/deployment/conftest.py`, which is past 2,100
lines.

**What is here can only be proved on a deployment.** The two records D480 names
— an `agent_plane` row written by the runtime and a `database` row written by
the write RPC in the write's own transaction — do not both exist anywhere else:
one is written by this process, one by PostgreSQL, and the claim is that they
agree. Nothing offline can put them side by side.

**These require migration 0019.** It is released and, until the trip, applied on
no cluster: `api.agent_audit_begin`, `api.agent_audit_complete` and the replaced
write RPCs all arrive with it, and every test here fails without them —
correctly, and loudly, which is what a released-and-unapplied migration should
look like from a gate.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

# ruff: noqa: S608 -- every literal here is this module's own constant, run by an
# operator's psql against a probe project. The same waiver every deployment
# module carries, for the same reason.

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.live_host,
    pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS"),
]

#: What an MCP endpoint requires, measured: naming only `application/json`
#: returns 406 rather than a result.
MCP_ACCEPT = "application/json, text/event-stream"

#: A WRITE agent's scopes. `meta:read` so it can discover the surface it is
#: authorized against (ADR 0138), and both write scopes so one agent can prove
#: both tools.
WRITER_SCOPES = ("meta:read", "notes:read", "notes:write", "tasks:read", "tasks:write")

WRITER_NAME = "apg-acceptance-mcp-writer"
WRITER_SECRET = "mcp-writer-secret-9d41ba07f3c2"  # noqa: S105 -- a probe credential

#: A title this test creates and nothing else does, so a row carrying it is
#: this test's row rather than a coincidence. The same rule Session 7's canary
#: works by, applied to a write.
CANARY_TITLE = "apg-run6-audit-canary-4e19"

#: The note BODY, which the lock's `audit_redact` says must not be stored. A
#: distinctive string, so its presence anywhere in the record is a leak rather
#: than a false positive (D479).
CANARY_BODY = "apg-run6-REDACTION-CANARY-b72f"


def sse_result(body: str) -> dict[str, Any] | None:
    """The JSON-RPC message out of an SSE response (D458).

    The framework frames even a single reply as `event: message` + `data: {...}`,
    so `json.loads(body)` raises on a perfectly good answer.
    """
    payload = None
    for line in body.splitlines():
        if line.startswith("data: "):
            payload = json.loads(line[6:])
    return payload


@pytest.fixture(scope="module")
def mcp_route(project_a: dict[str, Any]) -> str:
    """The published agent-plane URL, out of the DEPLOYED document (D395)."""
    route = (project_a.get("routes") or {}).get("mcp")
    if not isinstance(route, dict) or route.get("status") != "ready" or not route.get("url"):
        pytest.fail(
            f"routes.mcp is {route!r}. The agent plane is not being served, so every proof "
            "below would measure a closed port. D326's two-stage convergence means the "
            "FIRST deploy publishes 'unavailable' -- deploy twice before running this gate"
        )
    return route["url"]


@pytest.fixture(scope="module")
def mcp_rpc(api_call: Callable[..., Any]) -> Callable[..., Any]:
    """One JSON-RPC exchange with the agent plane. Returns, never judges."""

    def call(
        url: str,
        *,
        token: str | None,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        return api_call(
            url,
            method="POST",
            token=token,
            body={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
            headers={"Accept": MCP_ACCEPT},
        )

    return call


@pytest.fixture(scope="module")
def mcp_writer_session(
    project_a: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
    app_probe_subject: Any,
) -> Any:
    """An `agent_writer` agent owned by the ordinary probe subject, and a token.

    **`agent_writer`, and Session 9 is the first session that could ask for
    one** (ADR 0137). Created through `app_private.auth_create_agent`, the same
    function `POST /admin/agents` calls, so a proof about the write plane does
    not become conditional on the endpoint that makes agents.

    Taking the subject as an argument fixes the teardown order: `agents.owner_id`
    is `NO ACTION`, so an agent outliving its owner blocks that owner's deletion
    (D392).
    """
    from agentic_postgres import service_source

    hashing = service_source.load("hashing")
    role_name = project_a["database"]["roles"]["agent_writer"]
    scopes = ", ".join(f"'{scope}'" for scope in sorted(WRITER_SCOPES))

    psql(project_a, f"DELETE FROM app_private.agents WHERE name = '{WRITER_NAME}';")
    code, agent_id, error = psql(
        project_a,
        "SELECT app_private.auth_create_agent("
        f"'{WRITER_NAME}', 'MCP write acceptance probe', '{role_name}', "
        f"ARRAY[{scopes}]::text[], '{app_probe_subject.user_id}', "
        f"'{hashing.Hasher().hash(WRITER_SECRET)}');",
    )
    assert code == 0 and agent_id, f"could not create the probe write agent: {error}"

    try:
        answer = api_call(
            f"{app_base(project_a)}/auth/agent-token",
            method="POST",
            body={"agent_id": agent_id, "secret": WRITER_SECRET},
        )
        assert answer.status == 200, (
            f"the probe write agent could not obtain a token ({answer.status}: "
            f"{answer.body[:200]}). Every refusal below would then be a refusal of a "
            "missing credential rather than of anything this module measures"
        )
        yield {
            "agent_id": agent_id,
            "owner_id": app_probe_subject.user_id,
            "token": json.loads(answer.body)["access_token"],
            "role": role_name,
            "scopes": tuple(sorted(WRITER_SCOPES)),
        }
    finally:
        psql(
            project_a,
            f"DELETE FROM app.notes WHERE title = '{CANARY_TITLE}';",
        )
        psql(project_a, f"DELETE FROM app_private.agents WHERE name = '{WRITER_NAME}';")


def _audit_rows(
    psql: Callable[..., tuple[int, str, str]], project_a: dict[str, Any], agent_id: str
) -> list[dict[str, Any]]:
    """Every audit row this agent produced, newest last, as JSON.

    Read with `psql` rather than through an endpoint on purpose: the admin audit
    query endpoint is Run 7's, and a proof about the RECORD must not become
    conditional on the reader that has not been built.
    """
    code, out, error = psql(
        project_a,
        "SELECT coalesce(json_agg(row_to_json(r) ORDER BY r.started_at), '[]'::json) FROM ("
        "SELECT source::text, tool, request_id::text, parameters, outcome::text, row_count "
        "FROM app_private.agent_audit "
        f"WHERE agent_id = '{agent_id}' ORDER BY started_at) r;",
    )
    assert code == 0, f"could not read the audit record: {error}"
    return json.loads(out)


# ---------------------------------------------------------------------------
# AGT-WRITE-001 -- a write agent can write, and the bound holds
# ---------------------------------------------------------------------------


def test_a_write_agent_creates_one_note_through_the_agent_plane(
    mcp_route: str,
    mcp_rpc: Callable[..., Any],
    mcp_writer_session: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    project_a: dict[str, Any],
) -> None:
    """**AGT-WRITE-001's positive arm, and every proof below depends on it.**

    The row is asserted in the DATABASE and not only in the tool's answer: a
    tool that echoed its own arguments back would satisfy the response check
    while writing nothing. The owner is asserted too, because ADR 0117's whole
    claim is that an agent's write lands under its OWNER's identity and never
    the agent's own.
    """
    answer = mcp_rpc(
        mcp_route,
        token=mcp_writer_session["token"],
        method="tools/call",
        params={
            "name": "create_note",
            "arguments": {"p_title": CANARY_TITLE, "p_content": CANARY_BODY},
        },
    )
    assert answer.status == 200, f"the write failed: {answer.body[:300]}"
    result = sse_result(answer.body)
    assert result is not None and "error" not in result, f"the write was refused: {result}"

    payload = json.loads(result["result"]["content"][0]["text"])
    assert payload["row_count"] == 1, f"a bounded write reported {payload['row_count']} rows"

    code, owner, error = psql(
        project_a,
        f"SELECT owner_id::text FROM app.notes WHERE title = '{CANARY_TITLE}';",
    )
    assert code == 0 and owner, f"the note is not in the database: {error}"
    assert owner == mcp_writer_session["owner_id"], (
        f"the note is owned by {owner!r} and the agent's owner is "
        f"{mcp_writer_session['owner_id']!r}. An agent request runs under its OWNER's "
        "identity (ADR 0117), so a row owned by anything else is the identity decision "
        "not reaching the write path"
    )


# ---------------------------------------------------------------------------
# AGT-AUDIT-001 -- two records, from two routes, and they agree
# ---------------------------------------------------------------------------


def test_one_agent_write_leaves_both_records_and_they_agree(
    mcp_route: str,
    mcp_rpc: Callable[..., Any],
    mcp_writer_session: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    project_a: dict[str, Any],
) -> None:
    """**AGT-AUDIT-001, and D480's whole point.**

    An ordinary MCP write leaves **two** rows and they describe the same change
    from two routes:

    * an `agent_plane` row, written by the runtime around the call, carrying the
      request id, the redacted parameters and the outcome;
    * a `database` row, written by the write RPC **inside the write's own
      transaction**, which is the only kind that can say `committed` (D489).

    Neither is redundant. A denied call never reaches the database and has only
    the first; a caller reaching PostgREST directly never reaches MCP and has
    only the second. This test is the case where both exist, which is the one
    that proves they agree rather than merely that each is written.
    """
    mcp_rpc(
        mcp_route,
        token=mcp_writer_session["token"],
        method="tools/call",
        params={
            "name": "create_note",
            "arguments": {"p_title": CANARY_TITLE, "p_content": CANARY_BODY},
        },
    )

    rows = _audit_rows(psql, project_a, mcp_writer_session["agent_id"])
    creates = [row for row in rows if row["tool"] == "create_note"]
    sources = {row["source"] for row in creates}

    assert sources == {"agent_plane", "database"}, (
        f"one MCP write left rows from {sorted(sources)}. Both routes must record it: the "
        "agent plane's row is the only one that can say `refused`, and the database's is "
        "the only one that can say `committed` (D489)"
    )

    plane = next(row for row in creates if row["source"] == "agent_plane")
    database = next(row for row in creates if row["source"] == "database")

    assert plane["outcome"] == "served", f"the agent-plane row says {plane['outcome']!r}"
    assert database["outcome"] == "committed", (
        f"the database row says {database['outcome']!r}; `committed` is the outcome only a "
        "row written inside the write's own transaction can carry"
    )
    assert plane["row_count"] == database["row_count"] == 1


def test_the_recorded_parameters_are_redacted_per_the_lock(
    mcp_route: str,
    mcp_rpc: Callable[..., Any],
    mcp_writer_session: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    project_a: dict[str, Any],
) -> None:
    """**D479's orphan, on the deployment.** `audit.redact` was validated on the
    way in and consumed by nothing until Run 6.

    Both halves, because either alone is satisfied by the wrong implementation:
    the note's BODY must be absent from the record (`create_note` declares
    `["p_content"]`) and its TITLE must be present (nothing redacts that). A
    redactor that blanked everything would pass the first; one that blanked
    nothing would pass the second.

    The canaries are strings this test invented, so a hit is a leak rather than
    a coincidence.
    """
    mcp_rpc(
        mcp_route,
        token=mcp_writer_session["token"],
        method="tools/call",
        params={
            "name": "create_note",
            "arguments": {"p_title": CANARY_TITLE, "p_content": CANARY_BODY},
        },
    )

    rows = _audit_rows(psql, project_a, mcp_writer_session["agent_id"])
    plane = [row for row in rows if row["source"] == "agent_plane" and row["tool"] == "create_note"]
    assert plane, "no agent_plane row was written for the write"

    written = json.dumps(plane[-1]["parameters"])
    assert CANARY_BODY not in written, (
        f"the note's body reached the audit record: {written[:200]}. `create_note` declares "
        "audit_redact ['p_content'], and a redaction that does not happen is worse than "
        "one that was never declared"
    )
    assert CANARY_TITLE in written, (
        "the note's TITLE is absent from the record too, so the assertion above is "
        "satisfied by a record that stores no parameters at all"
    )
    assert "p_content" in written, (
        "the redacted KEY is missing, not just its value. A record showing p_content "
        "redacted says the caller supplied one; a record with no p_content says nothing"
    )


def test_the_request_id_is_recorded_and_is_this_planes_own_mint(
    mcp_route: str,
    mcp_rpc: Callable[..., Any],
    mcp_writer_session: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    project_a: dict[str, Any],
) -> None:
    """**D477 and D478's scope, on the deployment.**

    Session 9 owns MCP → PostgREST → the audit record; ingress is Session 11's
    (`OPS-LOG-001`) and this proof does not touch it.

    Two calls produce two DIFFERENT ids, which is what makes the id an
    identifier rather than a constant somebody wrote down — and the negative
    control that a single-call assertion cannot provide.

    **The `database` row carries none** (D500), and that is asserted rather than
    left to be discovered: 0019 inserts no `request_id` on that path, so the two
    records correlate by agent, tool and time. Whoever repairs it needs a
    migration 0020.
    """
    for _ in range(2):
        mcp_rpc(
            mcp_route,
            token=mcp_writer_session["token"],
            method="tools/call",
            params={
                "name": "create_note",
                "arguments": {"p_title": CANARY_TITLE, "p_content": CANARY_BODY},
            },
        )

    rows = _audit_rows(psql, project_a, mcp_writer_session["agent_id"])
    plane = [row for row in rows if row["source"] == "agent_plane"]
    ids = [row["request_id"] for row in plane if row["request_id"]]

    assert len(ids) >= 2, f"fewer than two agent-plane rows carry a request id: {plane}"
    assert len(set(ids[-2:])) == 2, (
        f"two separate calls recorded the same request id {ids[-2:]}. An id shared by every "
        "call identifies nothing"
    )

    database = [row for row in rows if row["source"] == "database"]
    assert database, "no database row at all; the assertion below would be vacuous"
    assert all(row["request_id"] is None for row in database), (
        "a database row carries a request id. Migration 0019 does not write one (D500), so "
        "this passing means the migration moved and this test's premise with it"
    )


def test_a_denied_write_is_recorded_and_never_reaches_the_database(
    mcp_route: str,
    mcp_rpc: Callable[..., Any],
    mcp_writer_session: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    project_a: dict[str, Any],
) -> None:
    """**AGT-AUDIT-001's denied arm**, and the reason `begin` runs before the
    scope check (ADR 0141).

    A `tasks:write` call the agent CAN make is not what is measured here; this
    names a task id that does not exist, so the write is refused by the product
    itself after reaching it. The record must say `refused`, and no `database`
    row may appear beside it — a `database` row is written only inside a
    transaction that committed.
    """
    answer = mcp_rpc(
        mcp_route,
        token=mcp_writer_session["token"],
        method="tools/call",
        params={
            "name": "update_task_status",
            "arguments": {
                "p_task_id": "00000000-0000-4000-8000-00000000dead",
                "p_expected_status": "todo",
                "p_new_status": "done",
            },
        },
    )
    assert answer.status == 200, f"the transport failed rather than the write: {answer.body[:200]}"
    result = sse_result(answer.body)
    assert "row_not_found" in json.dumps(result), (
        f"a write naming no such row was not translated to row_not_found: {result}. "
        "PT404 and PGRST202 are both a 404 and only the body's code tells them apart "
        "(ADR 0139)"
    )

    rows = _audit_rows(psql, project_a, mcp_writer_session["agent_id"])
    updates = [row for row in rows if row["tool"] == "update_task_status"]

    assert updates, "the refused write left no record at all"
    assert {row["source"] for row in updates} == {"agent_plane"}, (
        f"a refused write left rows from {sorted({r['source'] for r in updates})}. The "
        "database row is written inside the write's own transaction and a refused write "
        "has none (D489)"
    )
    assert updates[-1]["outcome"] == "refused"


# ---------------------------------------------------------------------------
# SEC-PARAM-001 -- the record's identity is not a parameter
# ---------------------------------------------------------------------------


def test_the_audit_functions_take_no_principal_on_the_deployed_cluster(
    psql: Callable[..., tuple[int, str, str]],
    project_a: dict[str, Any],
) -> None:
    """**SEC-PARAM-001, structurally** (D473, ADR 0135).

    There is no argument for a caller to lie in: the agent and its owner come
    from the GUCs the pre-request hook set. Asserted against the catalog rather
    than the migration text, because the deployed function is the one that
    matters and a template proves only what was written.
    """
    code, out, error = psql(
        project_a,
        "SELECT string_agg(p.proname || '(' || pg_get_function_arguments(p.oid) || ')', ' | ' "
        "ORDER BY p.proname) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'api' AND p.proname LIKE 'agent_audit%';",
    )
    assert code == 0 and out, f"the audit functions are not on this cluster: {error}"

    forbidden = ("agent_id", "owner_id", "user_id", "p_agent", "p_owner", "role")
    named = [name for name in forbidden if name in out]
    assert not named, (
        f"an audit function takes {named} as an argument: {out}. Identity comes from the "
        "GUCs and never from a parameter, which is what makes SEC-PARAM-001 structural "
        "rather than validated"
    )
    assert "agent_audit_begin" in out and "agent_audit_complete" in out, (
        f"migration 0019's audit functions are not both present: {out}"
    )


# ---------------------------------------------------------------------------
# Run 7 -- the 405 ADR 0136 named and did not run, and the admin reader
#
# **ADR 0136 wrote down a proof it could not run, and this is it.** Its own
# consequences section says so: *"The category's safety property -- these
# functions really do write, so GET really is ineffective -- is asserted offline
# only as a contract shape. The property itself is a live-host proof: a GET
# against the deployed endpoint must answer 405, and that belongs with Run 7's
# proofs rather than being assumed here. Until it runs, the 405 is measured on a
# rig and not on the deployment."*
#
# The distinction is not pedantry. Offline, nothing can tell a writing function
# from a reading one by looking at the contract -- so a future entry in
# `agent_write_rpcs` that does NOT write would keep the section's shape and
# silently lose its guarantee. This is the only assertion that would notice.
# ---------------------------------------------------------------------------

ADMIN_AUDIT_USERNAME = "apg-acceptance-audit-admin"
ADMIN_AUDIT_PASSWORD = "apg-audit-admin-6f21c8d4e0b7"  # noqa: S105 -- a probe credential

#: What the audit reader holds, and what it deliberately does not. No
#: `admin_agents:read`: the two are different authorities (ADR 0142), and a
#: subject holding both could not tell which one served the request.
ADMIN_AUDIT_SCOPES = ("admin_audit:read",)


@pytest.fixture(scope="module")
def audit_admin(
    project_a: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
) -> Any:
    """A `project_admin` holding `admin_audit:read` and nothing else administrative.

    Created through `app_private.auth_create_user` -- the same function
    `POST /admin/users` calls -- rather than through the endpoint, for the reason
    `app_probe_subject` gives: a fixture built on an endpoint makes every proof
    below conditional on that endpoint. The token comes from `/auth/login`,
    because obtaining one IS the product's route and there is no function
    underneath it to prefer.
    """
    from agentic_postgres import service_source

    hashing = service_source.load("hashing")
    role_name = project_a["database"]["roles"]["project_admin"]
    scopes = ", ".join(f"'{scope}'" for scope in sorted(ADMIN_AUDIT_SCOPES))

    psql(project_a, f"DELETE FROM app_private.users WHERE username = '{ADMIN_AUDIT_USERNAME}';")
    code, user_id, error = psql(
        project_a,
        "SELECT app_private.auth_create_user("
        f"'{ADMIN_AUDIT_USERNAME}', 'Audit reader probe', '{role_name}', "
        f"ARRAY[{scopes}]::text[], "
        f"'{hashing.Hasher().hash(ADMIN_AUDIT_PASSWORD)}');",
    )
    assert code == 0 and user_id, f"could not create the audit-admin probe subject: {error}"

    try:
        answer = api_call(
            f"{app_base(project_a)}/auth/login",
            method="POST",
            body={"username": ADMIN_AUDIT_USERNAME, "password": ADMIN_AUDIT_PASSWORD},
        )
        assert answer.status == 200, (
            f"the audit-admin probe could not log in ({answer.status}: {answer.body[:200]}). "
            "Every refusal below would then be a refusal of a missing credential"
        )
        yield {"user_id": user_id, "token": json.loads(answer.body)["access_token"]}
    finally:
        psql(project_a, f"DELETE FROM app_private.users WHERE username = '{ADMIN_AUDIT_USERNAME}';")


def test_a_get_against_the_deployed_audit_rpc_is_refused(
    rest_base: Callable[[dict[str, Any]], str],
    project_a: dict[str, Any],
    api_call: Callable[..., Any],
    mcp_writer_session: dict[str, Any],
) -> None:
    """**The proof ADR 0136 named and left unrun.** `agent_write_rpcs`' whole reason.

    Measured on a rig in Run 1, and both predictions going in were wrong in
    opposite directions (D490). PostgREST does **not** refuse GET on a VOLATILE
    function -- it executes it and takes the argument from the query string, so
    volatility protects nothing. What refuses a function that actually **writes**
    is that PostgREST runs a GET in a **read-only transaction**: `25006` surfaced
    as `405`, and the write does not happen. That is D474's mechanism arriving
    from the other side, and it is why `agent_rpcs`' `maxItems: 0` keeps its
    reason while a fourth section exists beside it.

    **The POST control runs first and must succeed.** Without it, a 405 could
    equally mean the function is absent, the route is wrong, or the token is
    refused -- three states that look identical from outside and none of which is
    the property being claimed.

    The guarantee this asserts is narrower than it looks and ADR 0136 says so:
    the 405 prevents the **effect**, not the **disclosure**. The argument is
    already in every log and cache by the time PostgreSQL refuses it, which is
    why the section enumerates its arguments as a review surface and why none of
    them may carry a secret.
    """
    base = rest_base(project_a)
    token = mcp_writer_session["token"]

    control = api_call(
        f"{base}/rpc/agent_audit_begin",
        method="POST",
        token=token,
        body={"p_tool": "query_resource"},
    )
    assert control.status == 200, (
        f"the control failed: POST /rpc/agent_audit_begin answered {control.status} "
        f"({control.body[:200]}). A 405 below would then say nothing about GET"
    )

    refused = api_call(
        f"{base}/rpc/agent_audit_begin?p_tool=leaked",
        method="GET",
        token=token,
    )
    assert refused.status == 405, (
        f"GET /rpc/agent_audit_begin answered {refused.status}, not 405. "
        "ADR 0136's category rests on a writing function being ineffective over GET, "
        f"and nothing offline can tell a writing function from a reading one: {refused.body[:300]}"
    )
    assert "25006" in refused.body or "read-only" in refused.body, (
        "the 405 did not come from the read-only transaction, so it is a different "
        f"refusal than the one this category rests on: {refused.body[:300]}"
    )


def test_the_get_that_was_refused_wrote_nothing(
    rest_base: Callable[[dict[str, Any]], str],
    project_a: dict[str, Any],
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
    mcp_writer_session: dict[str, Any],
) -> None:
    """A refusal that still wrote would be the worst of both.

    Asserted separately from the status, because a status is a claim about the
    response and this is a claim about the table -- and the rig measured them as
    two facts rather than one.
    """
    agent_id = mcp_writer_session["agent_id"]
    tool = "apg-run7-get-canary"

    api_call(
        f"{rest_base(project_a)}/rpc/agent_audit_begin?p_tool={tool}",
        method="GET",
        token=mcp_writer_session["token"],
    )

    code, out, error = psql(
        project_a,
        "SELECT count(*) FROM app_private.agent_audit "
        f"WHERE agent_id = '{agent_id}' AND tool = '{tool}';",
    )
    assert code == 0, error
    assert out.strip() == "0", (
        f"a GET that answered 405 still wrote {out.strip()} rows. The refusal is supposed "
        "to be the read-only transaction rejecting the INSERT, which means no row"
    )


# ---------------------------------------------------------------------------
# Run 7 -- the admin audit endpoint, against the deployment (ADR 0142)
# ---------------------------------------------------------------------------


def test_the_admin_audit_endpoint_serves_what_the_table_holds(
    audit_admin: dict[str, Any],
    mcp_writer_session: dict[str, Any],
    project_a: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
) -> None:
    """The endpoint and the table, side by side -- which is the only way to tell.

    `_audit_rows` above reads the table with `psql` and says why: a proof about
    the RECORD must not become conditional on the reader. This test is the
    other half of that decision -- the one place the two are compared, so a
    reader that filtered, truncated or reordered would be visible.

    **This needs migration 0020**, which is released and, until the trip,
    applied on no cluster. Without it `auth_service` holds schema USAGE on
    `app_private` and nothing else, and this answers 500 rather than 200 --
    correctly and loudly, which is what a released-and-unapplied migration
    should look like from a gate (D501).
    """
    agent_id = mcp_writer_session["agent_id"]
    psql(
        project_a,
        f"SELECT set_config('app.agent_id', '{agent_id}', false);",
    )
    from_table = _audit_rows(psql, project_a, agent_id)
    assert from_table, (
        "the probe agent has no audit rows, so this comparison would hold vacuously. "
        "Run the AGT-AUDIT-001 arms above first"
    )

    answer = api_call(
        f"{app_base(project_a)}/admin/audit?agent_id={agent_id}&limit=500",
        method="GET",
        token=audit_admin["token"],
    )
    assert answer.status == 200, (
        f"GET /admin/audit answered {answer.status} ({answer.body[:300]}). If this is "
        "500, the likely cause is that migration 0020 has not been applied to this "
        "cluster -- auth_service then holds no EXECUTE on auth_list_agent_audit"
    )
    served = json.loads(answer.body)

    assert {row["tool"] for row in served["audit"]} == {row["tool"] for row in from_table}, (
        "the endpoint and the table disagree about which tools this agent used"
    )
    assert len(served["audit"]) == len(from_table), (
        f"the endpoint served {len(served['audit'])} rows and the table holds {len(from_table)}"
    )
    # Newest first, which is the opposite of `_audit_rows`' ordering -- so this
    # also catches a reader that returned the table's natural order.
    started = [row["started_at"] for row in served["audit"]]
    assert started == sorted(started, reverse=True), (
        f"the endpoint did not return the record most recent first: {started}"
    )


def test_the_admin_audit_endpoint_refuses_an_administrator_without_the_scope(
    mcp_writer_session: dict[str, Any],
    project_a: dict[str, Any],
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
) -> None:
    """API-ADMIN-001 on the deployment, and the agent half beside it.

    Two callers who each hold a real, current credential and neither of which
    holds `admin_audit:read`: the write agent, whose ceiling does not admit the
    scope at all, and an anonymous request. An agent must never read the record
    that exists to attribute it, and the ceiling is only one of the two places
    that is enforced -- this is the other.
    """
    url = f"{app_base(project_a)}/admin/audit"

    anonymous = api_call(url, method="GET")
    assert anonymous.status == 401, f"{anonymous.status}: {anonymous.body[:200]}"

    as_agent = api_call(url, method="GET", token=mcp_writer_session["token"])
    assert as_agent.status in {401, 403}, (
        f"an agent token reached the admin audit endpoint ({as_agent.status}): "
        f"{as_agent.body[:300]}"
    )
    for leaked in ("agent_plane", "started", "query_resource"):
        assert leaked not in as_agent.body, (
            f"a refused request carried {leaked!r} out of the audit record"
        )


# ---------------------------------------------------------------------------
# AGT-AUDITFAIL-001 -- a write whose record cannot be opened does not happen
#
# **ADR 0141's central asymmetry, on a real cluster for the first time.** It was
# proved offline in Run 6 with the audit path pointed at a base URL nothing
# answers, and that measures the runtime's branch. It does not measure the
# deployment: a write whose `agent_audit_begin` fails there has to fail closed
# through the real transport, the real function and the real grant.
#
# **The failure is arranged by removing a real privilege**, inside the project
# lock and restored in a `finally`. `test_session5_api_contract.py` sets the
# precedent for privilege DDL against a deployed cluster, and the shape here is
# narrower than that one: no object is created, one grant is withdrawn from one
# role for the length of one request.
#
# The blast radius is stated rather than discovered: while the grant is off,
# every `agent_writer` request's audit begin fails and its write does not happen
# -- which is precisely the behaviour under test. Reads are unaffected, because
# a read does NOT fail closed (D483), and `agent_reader` keeps its own grant.
# ---------------------------------------------------------------------------

AUDITFAIL_TITLE = "apg-run8-auditfail-canary-3b7e"


def test_a_write_whose_audit_record_cannot_be_opened_does_not_happen(
    mcp_route: str,
    mcp_rpc: Callable[..., Any],
    mcp_writer_session: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    project_a: dict[str, Any],
) -> None:
    """**AGT-AUDITFAIL-001**, end to end, and the row is what proves it.

    "Did not happen" is asserted against `app.notes` rather than against the
    shape of the refusal. A tool that returned an error while the write had
    already committed would satisfy any assertion about the response, and that
    is the failure this requirement exists to exclude.

    **The positive control runs first and must write**, in the same test and
    against the same agent. Without it a refusal here could equally be a broken
    token, a wrong route or an agent that never had the scope -- three states
    that look identical from outside and none of which is fail-closed behaviour.

    The grant is restored in a `finally` and the restoration is CHECKED (D391):
    a guard whose result is unchecked is a comment, and leaving this grant off
    would leave the probe project's write plane failing closed for real.
    """
    from agentic_postgres.rendering import project_lock

    owner_role = project_a["database"]["roles"]["object_owner"]
    writer_role = project_a["database"]["roles"]["agent_writer"]
    signature = "api.agent_audit_begin(text, uuid, jsonb)"

    def write(title: str) -> Any:
        return mcp_rpc(
            mcp_route,
            token=mcp_writer_session["token"],
            method="tools/call",
            params={
                "name": "create_note",
                "arguments": {"p_title": title, "p_content": CANARY_BODY},
            },
        )

    def note_count(title: str) -> int:
        code, out, error = psql(
            project_a, f"SELECT count(*) FROM app.notes WHERE title = '{title}';"
        )
        assert code == 0, f"could not count notes: {error}"
        return int(out.strip())

    control_title = f"{AUDITFAIL_TITLE}-control"
    try:
        # The control, with the grant intact. A write that cannot succeed here
        # makes everything below meaningless.
        answer = write(control_title)
        assert answer.status == 200, f"the control write failed: {answer.body[:300]}"
        control = sse_result(answer.body)
        assert control is not None and "error" not in control, (
            f"the control write was refused with the audit grant INTACT: {control}"
        )
        assert note_count(control_title) == 1, "the control write left no row"

        with project_lock(project_a["project"]["key"]):
            code, _, error = psql(
                project_a,
                f'REVOKE EXECUTE ON FUNCTION {signature} FROM "{writer_role}";',
                role=owner_role,
            )
            assert code == 0, f"could not withdraw the audit grant: {error}"
            try:
                refused = write(AUDITFAIL_TITLE)
                # A refusal reaches an MCP caller as a JSON-RPC error inside a
                # 200, so the status alone says nothing (D458's neighbourhood).
                assert refused.status == 200, refused.body[:300]
                result = sse_result(refused.body)
                assert result is not None, f"no JSON-RPC message came back: {refused.body[:300]}"
                assert "error" in result or result.get("result", {}).get("isError"), (
                    "the write was SERVED while its audit record could not be opened: "
                    f"{str(result)[:400]}"
                )
            finally:
                restored, _, restore_error = psql(
                    project_a,
                    f'GRANT EXECUTE ON FUNCTION {signature} TO "{writer_role}";',
                    role=owner_role,
                )
                assert restored == 0, (
                    "THE AUDIT GRANT COULD NOT BE RESTORED and this project's write plane "
                    f"is now failing closed for agent_writer: {restore_error}. Restore it "
                    f'by hand: SET ROLE "{owner_role}"; GRANT EXECUTE ON FUNCTION '
                    f'{signature} TO "{writer_role}";'
                )

        # **The assertion the requirement is actually about.** Not the shape of
        # the refusal -- the absence of the row.
        assert note_count(AUDITFAIL_TITLE) == 0, (
            "an unauditable write REACHED THE DATABASE. ADR 0141: a write whose "
            "agent_audit_begin fails does not happen, and the record is the thing that "
            "makes an agent write attributable at all"
        )

        # And the grant really is back, measured rather than assumed -- the
        # `finally` above asserts the statement succeeded, and this asserts the
        # effect. A write that still fails here would mean the restore ran and
        # did not take.
        recovered = write(f"{AUDITFAIL_TITLE}-recovered")
        assert recovered.status == 200, recovered.body[:300]
        recovered_result = sse_result(recovered.body)
        assert recovered_result is not None and "error" not in recovered_result, (
            f"writes are still failing after the grant was restored: {recovered_result}"
        )
    finally:
        for title in (control_title, AUDITFAIL_TITLE, f"{AUDITFAIL_TITLE}-recovered"):
            psql(project_a, f"DELETE FROM app.notes WHERE title = '{title}';")


def test_a_read_survives_the_same_audit_failure(
    mcp_route: str,
    mcp_rpc: Callable[..., Any],
    mcp_writer_session: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    project_a: dict[str, Any],
) -> None:
    """**The other half of ADR 0141, and the asymmetry is the decision** (D483).

    The same failure, the same cluster, the same agent, the opposite outcome --
    so neither result can be explained by the grant withdrawal simply not
    working. Failing a read closed would couple every agent read's availability
    to the audit table and add a mandatory round trip to a path ADR 0125 already
    pays one for.

    The reader role keeps its own grant throughout; only the writer's is
    withdrawn, and the agent here holds both scopes, so the read and the write
    above travel the same token.
    """
    from agentic_postgres.rendering import project_lock

    owner_role = project_a["database"]["roles"]["object_owner"]
    writer_role = project_a["database"]["roles"]["agent_writer"]
    signature = "api.agent_audit_begin(text, uuid, jsonb)"

    def read() -> Any:
        return mcp_rpc(
            mcp_route,
            token=mcp_writer_session["token"],
            method="tools/call",
            params={"name": "query_resource", "arguments": {"resource": "notes"}},
        )

    answer = read()
    assert answer.status == 200, f"the control read failed: {answer.body[:300]}"
    control = sse_result(answer.body)
    assert control is not None and "error" not in control, (
        f"the control read was refused with the audit grant INTACT: {control}"
    )

    with project_lock(project_a["project"]["key"]):
        code, _, error = psql(
            project_a,
            f'REVOKE EXECUTE ON FUNCTION {signature} FROM "{writer_role}";',
            role=owner_role,
        )
        assert code == 0, f"could not withdraw the audit grant: {error}"
        try:
            answered = read()
            assert answered.status == 200, answered.body[:300]
            result = sse_result(answered.body)
            assert result is not None, f"no JSON-RPC message came back: {answered.body[:300]}"
            assert "error" not in result and not result.get("result", {}).get("isError"), (
                "a READ failed closed on its audit record. ADR 0141 makes the asymmetry "
                f"deliberate: a write does and a read does not: {str(result)[:400]}"
            )
        finally:
            restored, _, restore_error = psql(
                project_a,
                f'GRANT EXECUTE ON FUNCTION {signature} TO "{writer_role}";',
                role=owner_role,
            )
            assert restored == 0, (
                "THE AUDIT GRANT COULD NOT BE RESTORED and this project's write plane "
                f"is now failing closed for agent_writer: {restore_error}. Restore it "
                f'by hand: SET ROLE "{owner_role}"; GRANT EXECUTE ON FUNCTION '
                f'{signature} TO "{writer_role}";'
            )


# ---------------------------------------------------------------------------
# SEC-REV-001 -- one token, three requests, after the product's own PATCH
#
# **Session 9 adds no revocation mechanism and must not appear to** (D471, D472).
# Migration 0018's `agent_claims_are_current` is the authoritative check and its
# own COMMENT states the property; `PATCH /admin/agents/{agent_id}` has revoked
# since Session 6. What was missing is the proof, and specifically the proof of
# the requirement's own sentence: *denied on its next read and write through
# BOTH MCP and PostgREST*.
#
# Run 7 proved the two halves separately -- the hook refusing replayed claims on
# a throwaway cluster, and the agent plane refusing when its context cannot be
# resolved -- and said that the arm carrying one token across all three requests
# was live-host. This is it. It needs a real PostgREST between the two halves,
# which is exactly why it could not be written offline.
#
# **Its own agent**, not `mcp_writer_session`'s: revoking that one would break
# every other proof in this module, and a fixture whose teardown is another
# test's precondition is how a suite becomes order-dependent.
# ---------------------------------------------------------------------------

REVOCABLE_NAME = "apg-acceptance-mcp-revocable"
REVOCABLE_SECRET = "mcp-revocable-secret-1f70c9a4e2d8"  # noqa: S105 -- a probe credential
REVOCATION_ADMIN_USERNAME = "apg-acceptance-agent-admin"
REVOCATION_ADMIN_PASSWORD = "apg-agent-admin-8d21f6b0c4a9"  # noqa: S105 -- a probe credential
REVOKED_TITLE = "apg-run8-revoked-canary-9c2d"


@pytest.fixture(scope="module")
def agent_admin(
    project_a: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
) -> Any:
    """A `project_admin` holding `admin_agents:write`, which is what revokes.

    A separate subject from `audit_admin`: that one holds `admin_audit:read` and
    nothing else administrative, which is what makes ITS refusal arm meaningful.
    One subject holding both scopes would make each of the two tests unable to
    say which scope served it.
    """
    from agentic_postgres import service_source

    hashing = service_source.load("hashing")
    role_name = project_a["database"]["roles"]["project_admin"]

    psql(
        project_a,
        f"DELETE FROM app_private.users WHERE username = '{REVOCATION_ADMIN_USERNAME}';",
    )
    code, user_id, error = psql(
        project_a,
        "SELECT app_private.auth_create_user("
        f"'{REVOCATION_ADMIN_USERNAME}', 'Agent admin probe', '{role_name}', "
        "ARRAY['admin_agents:read', 'admin_agents:write']::text[], "
        f"'{hashing.Hasher().hash(REVOCATION_ADMIN_PASSWORD)}');",
    )
    assert code == 0 and user_id, f"could not create the agent-admin probe: {error}"

    try:
        answer = api_call(
            f"{app_base(project_a)}/auth/login",
            method="POST",
            body={
                "username": REVOCATION_ADMIN_USERNAME,
                "password": REVOCATION_ADMIN_PASSWORD,
            },
        )
        assert answer.status == 200, (
            f"the agent-admin probe could not log in ({answer.status}: {answer.body[:200]})"
        )
        yield {"user_id": user_id, "token": json.loads(answer.body)["access_token"]}
    finally:
        psql(
            project_a,
            f"DELETE FROM app_private.users WHERE username = '{REVOCATION_ADMIN_USERNAME}';",
        )


@pytest.fixture(scope="module")
def revocable_agent(
    project_a: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
    app_probe_subject: Any,
) -> Any:
    """An `agent_writer` created to be revoked, and a token minted before it is."""
    from agentic_postgres import service_source

    hashing = service_source.load("hashing")
    role_name = project_a["database"]["roles"]["agent_writer"]
    scopes = ", ".join(f"'{scope}'" for scope in sorted(WRITER_SCOPES))

    psql(project_a, f"DELETE FROM app_private.agents WHERE name = '{REVOCABLE_NAME}';")
    code, agent_id, error = psql(
        project_a,
        "SELECT app_private.auth_create_agent("
        f"'{REVOCABLE_NAME}', 'MCP revocation acceptance probe', '{role_name}', "
        f"ARRAY[{scopes}]::text[], '{app_probe_subject.user_id}', "
        f"'{hashing.Hasher().hash(REVOCABLE_SECRET)}');",
    )
    assert code == 0 and agent_id, f"could not create the revocable probe agent: {error}"

    try:
        answer = api_call(
            f"{app_base(project_a)}/auth/agent-token",
            method="POST",
            body={"agent_id": agent_id, "secret": REVOCABLE_SECRET},
        )
        assert answer.status == 200, (
            f"the revocable probe could not obtain a token ({answer.status}: "
            f"{answer.body[:200]}). Every refusal below would then be a refusal of a "
            "missing credential rather than of a revocation"
        )
        yield {"agent_id": agent_id, "token": json.loads(answer.body)["access_token"]}
    finally:
        psql(project_a, f"DELETE FROM app.notes WHERE title = '{REVOKED_TITLE}';")
        psql(project_a, f"DELETE FROM app_private.agents WHERE name = '{REVOCABLE_NAME}';")


def test_a_revoked_token_fails_its_next_read_write_and_direct_request(
    mcp_route: str,
    mcp_rpc: Callable[..., Any],
    revocable_agent: dict[str, Any],
    agent_admin: dict[str, Any],
    project_a: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
    rest_base: Callable[[dict[str, Any]], str],
) -> None:
    """**SEC-REV-001**, one token, three requests, across both verifiers.

    The token is minted BEFORE the revocation and never refreshed. Nothing about
    its signature changes and it has not expired -- what changes is the answer to
    *is this still true*, asked inside each request's own transaction. That is
    the whole difference between "this token was issued" and "this token is
    current", and it is why an expiry alone is not a kill switch.

    **All three arms run twice**, before and after, and the before-run must
    succeed. A revoked-only test would pass against an agent that never had the
    scopes, a wrong route, or a plane that refuses everything -- and each of
    those looks identical from outside.

    The revocation goes through `PATCH /admin/agents/{agent_id}`, the product's
    own route (ADR 0065/0066): a proof that reaches the right end state by a
    route the product does not take proves the end state is reachable, not that
    the product reaches it. Session 9 builds no second revocation path (D472).
    """
    token = revocable_agent["token"]

    def mcp_read() -> Any:
        return mcp_rpc(
            mcp_route,
            token=token,
            method="tools/call",
            params={"name": "query_resource", "arguments": {"resource": "notes"}},
        )

    def mcp_write(title: str) -> Any:
        return mcp_rpc(
            mcp_route,
            token=token,
            method="tools/call",
            params={
                "name": "create_note",
                "arguments": {"p_title": title, "p_content": CANARY_BODY},
            },
        )

    def direct() -> Any:
        # PostgREST, with no agent plane in the way. The second verifier, and the
        # route an agent token can take on its own -- which is why the record has
        # a `database` source at all (D480).
        return api_call(f"{rest_base(project_a)}/notes?limit=1", method="GET", token=token)

    # ---- before: all three must work, or nothing below means anything --------
    read_before = mcp_read()
    assert read_before.status == 200, f"the MCP read control failed: {read_before.body[:300]}"
    read_result = sse_result(read_before.body)
    assert read_result is not None and "error" not in read_result, (
        f"the MCP read was refused while the agent was ACTIVE: {read_result}"
    )

    write_before = mcp_write(f"{REVOKED_TITLE}-before")
    assert write_before.status == 200, f"the MCP write control failed: {write_before.body[:300]}"
    write_result = sse_result(write_before.body)
    assert write_result is not None and "error" not in write_result, (
        f"the MCP write was refused while the agent was ACTIVE: {write_result}"
    )

    direct_before = direct()
    assert direct_before.status == 200, (
        f"the direct PostgREST control failed ({direct_before.status}): {direct_before.body[:300]}"
    )

    # ---- the revocation, through the product's own route --------------------
    revoked = api_call(
        f"{app_base(project_a)}/admin/agents/{revocable_agent['agent_id']}",
        method="PATCH",
        token=agent_admin["token"],
        body={"status": "revoked"},
    )
    assert revoked.status == 200, f"the revocation failed: {revoked.body[:300]}"

    # ---- after: the SAME token, unchanged, on all three paths ---------------
    read_after = mcp_read()
    read_after_result = sse_result(read_after.body) if read_after.status == 200 else None
    assert read_after.status != 200 or (
        read_after_result is not None
        and ("error" in read_after_result or read_after_result.get("result", {}).get("isError"))
    ), f"a revoked agent's next MCP READ was served: {read_after.body[:400]}"

    write_after = mcp_write(REVOKED_TITLE)
    write_after_result = sse_result(write_after.body) if write_after.status == 200 else None
    assert write_after.status != 200 or (
        write_after_result is not None
        and ("error" in write_after_result or write_after_result.get("result", {}).get("isError"))
    ), f"a revoked agent's next MCP WRITE was served: {write_after.body[:400]}"

    direct_after = direct()
    assert direct_after.status != 200, (
        f"a revoked agent's next DIRECT PostgREST request was served ({direct_after.status}). "
        "The agent plane is not the boundary -- an agent token reaches PostgREST on its own, "
        "which is why the authoritative check lives in the pre-request hook (D471)"
    )

    # And the write really did not happen. A refusal reported after a commit
    # would satisfy every assertion above, which is the failure this requirement
    # exists to exclude.
    code, out, error = psql(
        project_a, f"SELECT count(*) FROM app.notes WHERE title = '{REVOKED_TITLE}';"
    )
    assert code == 0, f"could not count notes: {error}"
    assert out.strip() == "0", (
        f"a revoked agent's write reached the database ({out.strip()} rows). The refusal "
        "above was reported after the row was committed"
    )
