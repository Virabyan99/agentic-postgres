"""The six tools, the adapter, and AGT-SQL-001 (Session 8 Run 6; Session 9 Runs 4-5).

**This module carries four of the five Session 8 `AGT-*` requirements** that
pointed at placeholders in `tests/integration/test_future_mcp.py` until then
(D414), and the placeholders are gone with them. Session 9 added the write half:
the lock's write shape and the write request in Run 4, and the two write TOOLS
plus name-level discovery filtering in Run 5 — which is `AGT-WRITE-001`'s
offline arm, both of its halves, at the bottom of this file. **Run 8 repointed
the registry at them and deleted `test_future_mcp.py` entirely**: every marker
left in it was Session 9's, so activating the three emptied the module.

The construction rule these tests enforce was **measured against a live
PostgREST on the locked digest**, twice, because the obvious answers were wrong:

* percent-encoding a caller value defeats parameter injection -- proved with a
  control that CAN fail (`title=neq.zzz&limit=1` returns 3 rows encoded and 1
  unencoded, so the arms differ);
* percent-encoding a comma inside `in.(…)` does **not** work, because PostgREST
  decodes before it parses the list -- the member has to be quoted;
* an embedded quote inside a quoted member needs a **backslash**, not the
  doubled quote SQL uses.

Both wrong answers fail by matching nothing, which reads as an empty result
rather than an error. That is why these are tests and not comments.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app import mcp_authorization, mcp_tools
from app.mcp_audit import AuditRefusal
from app.mcp_errors import ROW_NOT_FOUND, WRITE_CONFLICT, WRITE_REJECTED, AgentVisible
from app.mcp_lock import (
    EXPECTED_TOOL_NAMES,
    METADATA_TOOLS,
    READ_TOOLS,
    SUPPORTED_SCHEMA_VERSIONS,
    WRITE_TOOLS,
    CapabilityLock,
    LockError,
    Operation,
    Resource,
    WriteSpec,
    load_lock,
)
from app.mcp_query import (
    Filter,
    QueryRefusal,
    build_request,
    build_write_request,
    quote_list_member,
)
from app.mcp_tools import ToolRefusal, describe_resource, list_resources, query_resource
from app.mcp_upstream import AgentContext, UpstreamRefusal, execute_write

pytestmark = [pytest.mark.contract, pytest.mark.p0]

BASE = "http://postgrest:3000"
OWNER = "aaaaaaaa-0000-4000-8000-000000000001"

#: The id the agent plane would have minted for this request (ADR 0141).
#:
#: A fixed value in tests, and `uuid4()` in production. Fixed here so an
#: assertion can name it: a test that generated its own could only assert "some
#: id was forwarded", which is satisfied by forwarding the wrong one.
REQUEST_ID = "7f3a1c20-0000-4000-8000-0000000000aa"

NOTES = Resource(
    name="notes",
    capability="query_notes",
    columns=("id", "owner_id", "title", "content", "created_at"),
    filters={
        "id": ("eq", "in"),
        "title": ("eq", "neq", "in"),
        "created_at": ("gt", "gte", "lt", "lte"),
        "note_id": ("is_null",),
    },
    order_by=(("created_at", "desc"), ("title", "asc")),
    max_rows=200,
    required_scopes=("notes:read",),
    operation=Operation(method="get", path="/notes", operation_id="notes.get"),
)


CREATE_SPEC = WriteSpec(
    operation=Operation(
        method="post", path="/rpc/create_note", operation_id="rpc.create_note.post"
    ),
    arguments=("p_title", "p_content"),
    required_scopes=("notes:write",),
    max_affected_rows=1,
    idempotent=False,
)

UPDATE_SPEC = WriteSpec(
    operation=Operation(
        method="post",
        path="/rpc/update_task_status",
        operation_id="rpc.update_task_status.post",
    ),
    arguments=("p_task_id", "p_expected_status", "p_new_status"),
    required_scopes=("tasks:write",),
    max_affected_rows=1,
    idempotent=True,
)


def _lock(*resources: Resource) -> CapabilityLock:
    """A lock carrying the six required tools, with `resources` under query.

    Six since Session 9 Run 5, because `register()` registers six and a fixture
    short of one would make every registration test fail for the fixture rather
    than for the thing it measures.
    """
    from app.mcp_lock import Tool

    return CapabilityLock(
        contract_id="notes-tasks-agent-v1",
        project_key="probe-dev",
        upstream="https://probe.test/api/rest",
        canonical_sha256="a" * 64,
        tool_count=6,
        capability_count=7,
        tools=(
            Tool(
                "create_note",
                "write",
                "postgrest",
                5000,
                (("notes:write",),),
                (),
                (),
                write=CREATE_SPEC,
                audit_redact=("p_content",),
            ),
            Tool(
                "update_task_status",
                "write",
                "postgrest",
                5000,
                (("tasks:write",),),
                (),
                (),
                write=UPDATE_SPEC,
            ),
            Tool("describe_resource", "metadata", "lock", 1000, (("meta:read",),), (), ()),
            Tool("list_resources", "metadata", "lock", 1000, (("meta:read",),), (), ()),
            Tool(
                "query_resource",
                "read",
                "postgrest",
                5000,
                (("notes:read",),),
                (),
                resources or (NOTES,),
            ),
            Tool(
                "run_report",
                "read",
                "postgrest",
                5000,
                (("notes:read", "tasks:read"),),
                (),
                (
                    Resource(
                        name="owner_activity_report",
                        capability="run_report",
                        columns=("notes_total",),
                        filters={},
                        order_by=(),
                        max_rows=1,
                        required_scopes=("notes:read", "tasks:read"),
                        operation=Operation(
                            method="post",
                            path="/rpc/owner_activity_report",
                            operation_id="rpc.owner_activity_report.post",
                        ),
                    ),
                ),
            ),
        ),
    )


def _with_scopes(monkeypatch: Any, *scopes: str) -> None:
    monkeypatch.setattr(
        mcp_tools,
        "current_agent_context",
        lambda: AgentContext(
            agent_id="agent-1",
            role_name="apg_probe_dev_agent_reader",
            scopes=tuple(scopes),
            authz_version=1,
            owner_id=OWNER,
        ),
    )


# ---------------------------------------------------------------------------
# AGT-SQL-001 -- no input is syntax
# ---------------------------------------------------------------------------


def test_no_tool_input_accepts_sql_a_fragment_or_a_query_string() -> None:
    """**AGT-SQL-001.** Every hostile string is a VALUE and never syntax.

    The assertion is on the built target, so this checks what would go on the
    wire rather than what a stub was willing to accept. Each payload is the kind
    a caller would actually try: a second parameter, a SQL tail, a column
    reference, a projection wildcard.
    """
    payloads = [
        "zzz&limit=1",
        "'; DROP TABLE app.notes; --",
        "1 OR 1=1",
        "*",
        "owner_id",
        "eq.alpha",
        "notes?select=*",
        "a,b",
        'quote"inside',
    ]
    for payload in payloads:
        request = build_request(
            NOTES, timeout_ms=5000, columns=["title"], filters=[Filter("title", "eq", payload)]
        )
        target = request.target
        # One `?`, and every subsequent `&` introduces a parameter this code
        # emitted -- never one the payload smuggled in.
        assert target.count("?") == 1
        parameters = [pair.split("=", 1)[0] for pair in target.split("?", 1)[1].split("&")]
        assert parameters == ["select", "title", "order", "limit"], (
            f"{payload!r} changed the parameter list to {parameters}"
        )
        assert "'" not in target and " " not in target


def test_the_path_and_method_come_from_the_lock_and_never_from_a_caller() -> None:
    """No runtime-selected operation. A caller names a RESOURCE, not an address."""
    request = build_request(NOTES, timeout_ms=5000)

    assert request.path == NOTES.operation.path
    assert request.method == NOTES.operation.method

    parameters = set(build_request.__code__.co_varnames[: build_request.__code__.co_argcount])
    assert not parameters & {"path", "method", "url", "query", "operation_id"}


@pytest.mark.parametrize(
    ("entry", "why"),
    [
        (Filter("secret", "eq", "x"), "a column the lock does not list"),
        (Filter("title", "like", "x"), "an operator the lock does not permit on it"),
        (Filter("created_at", "eq", "x"), "an operator not permitted on THIS column"),
        (Filter("title", "in", "notalist"), "an in-list that is not a list"),
        (Filter("title", "in", []), "an empty in-list"),
        (Filter("note_id", "is_null", "x"), "is_null with an operand"),
        (Filter("title", "eq", None), "a scalar operator with no operand"),
        (Filter("title", "eq", {"a": 1}), "a value that is not a scalar"),
    ],
)
def test_a_filter_the_lock_does_not_permit_is_refused(entry: Filter, why: str) -> None:
    """Refused HERE, before a request is built.

    A 400 from PostgREST would mean the caller's string reached the query -- and
    its message names the table, which is not a caller's to receive (ADR 0097).
    """
    with pytest.raises(QueryRefusal):
        build_request(NOTES, timeout_ms=5000, filters=[entry])


def test_the_permitted_filters_are_accepted_by_the_same_function() -> None:
    """**The control for the refusals above.**

    Without it a `build_request` that refused everything would pass all eight.
    """
    request = build_request(
        NOTES,
        timeout_ms=5000,
        filters=[
            Filter("title", "eq", "alpha"),
            Filter("id", "in", ["a", "b"]),
            Filter("note_id", "is_null"),
            Filter("created_at", "gt", "2020-01-01"),
        ],
    )

    assert "title=eq.alpha" in request.target
    assert "note_id=is.null" in request.target


def test_the_in_list_escape_is_the_measured_one_and_not_the_sql_one() -> None:
    """A backslash escape, and a quoted member. Both measured; both non-obvious.

    Doubling the quote is the SQL convention and matches **zero rows** against
    the locked PostgREST. Percent-encoding the comma also matches zero, because
    the server decodes before it parses the list.
    """
    assert quote_list_member("plain") == '"plain"'
    assert quote_list_member("we,ird") == '"we,ird"'
    assert quote_list_member('say "hi"') == '"say \\"hi\\""'
    assert quote_list_member("back\\slash") == '"back\\\\slash"'

    # The wrong answers, named so a change to them fails here.
    assert quote_list_member('say "hi"') != '"say ""hi"""'
    assert "%2C" not in quote_list_member("we,ird")


def test_an_unordered_page_is_not_reachable() -> None:
    """A page without an order is a different page each time."""
    assert "order=" in build_request(NOTES, timeout_ms=5000).target

    with pytest.raises(QueryRefusal):
        build_request(NOTES, timeout_ms=5000, order_by=99)
    with pytest.raises(QueryRefusal):
        build_request(NOTES, timeout_ms=5000, order_by="created_at.desc")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# AGT-SCOPE-001 -- discovery is filtered by the caller's scopes
# ---------------------------------------------------------------------------


def test_discovery_shows_only_what_the_callers_scopes_permit(monkeypatch: Any) -> None:
    """**AGT-SCOPE-001.** A tool list that advertises what it will refuse lies."""
    lock = _lock()

    _with_scopes(monkeypatch, "meta:read", "notes:read", "tasks:read")
    everything = {entry["resource"] for entry in list_resources(lock)["resources"]}
    assert everything == {"notes", "owner_activity_report"}

    _with_scopes(monkeypatch, "meta:read", "notes:read")
    partial = {entry["resource"] for entry in list_resources(lock)["resources"]}
    assert partial == {"notes"}, "the report needs both scopes and must not be listed"

    _with_scopes(monkeypatch, "meta:read")
    assert list_resources(lock)["resources"] == []


class _Registry:
    """The least a `register()` call needs: a decorator that keeps the function.

    Standing in for the framework's server on purpose. The real one is exercised
    by `test_mcp_route`, which asserts the registered NAMES; what is needed here
    is the registered *callable*, and reaching it through the framework's tool
    manager would test the framework's accessors rather than this repository's
    registration.
    """

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self, *, name: str, timeout: float | None = None) -> Any:
        def keep(function: Any) -> Any:
            self.tools[name] = function
            return function

        return keep


def test_a_metadata_tool_takes_no_slot_and_a_read_and_a_write_both_do(
    monkeypatch: Any,
) -> None:
    """**ADR 0129**, asserted through `register()` rather than around it (D454).

    The rule -- the two metadata tools answer from the lock and take no slot --
    lived in `bounded`'s docstring and in nothing else, because **no test in this
    repository had ever called `register()`**. Every tool test calls the module
    function the registration wraps, so the wrapper was the seam nobody crossed:
    D444 and D450's family, found this time by a surviving mutation rather than
    by a start.

    **The control is the second half**, and it is what makes the first half a
    measurement: the same rig, the same semaphore, a tool that DOES reach
    upstream, and it must be seen holding a slot. Without it, an assertion that
    the metadata path leaves the semaphore full is satisfied by a semaphore
    nothing ever touches.

    **A write is the third arm, and it is D495's proof.** `bounded` used to
    infer "reaches upstream" from `resource is not None`, and a write has NO
    resource -- it is one-to-one with its operation -- while reaching PostgREST.
    Under the old inference both writes would have run unbounded on the event
    loop, which is D451 restored by accident. The arm below is what fails if the
    inference comes back.
    """
    import asyncio

    from app.mcp_budgets import ReadSlots

    lock = _lock(NOTES)
    slots = ReadSlots(2)
    seen: dict[str, int] = {}

    _with_scopes(monkeypatch, "meta:read", "notes:read", "notes:write")
    monkeypatch.setattr(mcp_authorization, "current_token", lambda: "t")

    def watching(label: str, payload: dict[str, Any]) -> Any:
        def work(*_: Any, **__: Any) -> dict[str, Any]:
            seen[label] = slots.available
            return payload

        return work

    monkeypatch.setattr(mcp_tools, "list_resources", watching("meta", {"resources": []}))
    monkeypatch.setattr(
        mcp_tools,
        "query_resource",
        watching("read", {"resource": "notes", "row_count": 0, "rows": []}),
    )
    monkeypatch.setattr(
        mcp_tools,
        "invoke_write",
        watching("write", {"tool": "create_note", "row_count": 1, "row": {}}),
    )

    # Since Run 6 an audited tool opens a record before its work, and a write
    # whose record cannot be opened does not happen (ADR 0141). Stubbed, so the
    # slot assertions below measure the semaphore rather than the audit path.
    monkeypatch.setattr(mcp_authorization, "current_request_id", lambda: REQUEST_ID)
    monkeypatch.setattr(mcp_tools, "audit_begin", lambda *_, **__: "audit-1")
    monkeypatch.setattr(mcp_tools, "audit_complete", lambda *_, **__: True)

    registry = _Registry()
    assert mcp_tools.register(registry, lock, base_url=BASE, slots=slots) == mcp_tools.TOOL_NAMES
    assert set(registry.tools) == set(mcp_tools.TOOL_NAMES)

    asyncio.run(registry.tools["list_resources"]())
    assert seen["meta"] == slots.limit, "a metadata tool must not queue behind a read"

    asyncio.run(registry.tools["create_note"](p_title="t", p_content="c"))
    assert seen["write"] == slots.limit - 1, (
        "a write reaches upstream and must hold a slot; it names no resource, so "
        "inferring that from `resource is None` puts it on the event loop (D495)"
    )

    asyncio.run(registry.tools["query_resource"](resource="notes"))
    assert seen["read"] == slots.limit - 1, "the CONTROL: a read must be seen holding a slot"


def test_a_resource_the_caller_cannot_reach_is_refused_not_merely_hidden(
    monkeypatch: Any,
) -> None:
    """Hiding it in discovery is not the boundary; refusing the call is."""
    lock = _lock()
    _with_scopes(monkeypatch, "meta:read")

    # AgentVisible now: a scope refusal is something the caller can act on,
    # so it reaches them through ToolError rather than being masked (ADR 0130).
    with pytest.raises(AgentVisible, match="requires"):
        describe_resource(lock, tool="query_resource", resource="notes")
    with pytest.raises(AgentVisible, match="requires"):
        query_resource(lock, base_url=BASE, token="t", request_id=REQUEST_ID, resource="notes")  # noqa: S106


def test_the_scope_sets_are_a_disjunction_of_conjunctions() -> None:
    """D421: a flat list cannot tell "any of" from "all of"."""
    lock = _lock()
    report = lock.tool("run_report")
    query = lock.tool("query_resource")

    assert report.discoverable_by(frozenset({"notes:read", "tasks:read"}))
    assert not report.discoverable_by(frozenset({"notes:read"}))
    assert query.discoverable_by(frozenset({"notes:read"}))


# ---------------------------------------------------------------------------
# AGT-BUDGET-001 -- server-side, regardless of client input
# ---------------------------------------------------------------------------


def test_the_row_ceiling_is_the_locks_and_a_caller_can_only_lower_it() -> None:
    """**AGT-BUDGET-001**, the row half."""
    assert "limit=200" in build_request(NOTES, timeout_ms=5000).target
    assert "limit=10" in build_request(NOTES, timeout_ms=5000, limit=10).target
    # Above the ceiling is clamped, not honoured.
    assert "limit=200" in build_request(NOTES, timeout_ms=5000, limit=100000).target

    for bad in (0, -1, "5", True):
        with pytest.raises(QueryRefusal):
            build_request(NOTES, timeout_ms=5000, limit=bad)  # type: ignore[arg-type]


def test_the_byte_ceiling_is_independent_of_the_row_ceiling(monkeypatch: Any) -> None:
    """**AGT-BUDGET-001**, the size half, and why it is a separate number.

    `max_rows` bounds how many rows come back and nothing about their size.
    Two rows of a megabyte each are inside every row budget in the lock.
    """
    lock = _lock()
    _with_scopes(monkeypatch, "notes:read")
    monkeypatch.setattr(
        mcp_tools,
        "execute",
        lambda *_, **__: [{"content": "x" * 900_000} for _ in range(2)],
    )

    # Caller-visible: this is the one budget a caller can stay inside by
    # asking differently, so the advice is worth relaying (ADR 0130).
    with pytest.raises(AgentVisible, match="ceiling"):
        query_resource(lock, base_url=BASE, token="t", request_id=REQUEST_ID, resource="notes")  # noqa: S106


def test_a_result_inside_both_budgets_is_returned(monkeypatch: Any) -> None:
    """**The control.** Without it, a budget check that refused everything passes."""
    lock = _lock()
    _with_scopes(monkeypatch, "notes:read")
    monkeypatch.setattr(mcp_tools, "execute", lambda *_, **__: [{"title": "alpha"}])

    result = query_resource(lock, base_url=BASE, token="t", request_id=REQUEST_ID, resource="notes")  # noqa: S106

    assert result == {"resource": "notes", "row_count": 1, "rows": [{"title": "alpha"}]}


def test_more_rows_than_the_ceiling_are_refused_rather_than_truncated(
    monkeypatch: Any,
) -> None:
    """A truncated page that does not say so is a wrong answer."""
    lock = _lock()
    _with_scopes(monkeypatch, "notes:read")
    monkeypatch.setattr(mcp_tools, "execute", lambda *_, **__: [{"t": 1}] * 201)

    # STRUCTURAL: the upstream returned more than the lock permits, which is a
    # fault in the deployment rather than in the request. Nothing the caller did
    # produced it, so it is masked (ADR 0130).
    with pytest.raises(ToolRefusal):
        query_resource(lock, base_url=BASE, token="t", request_id=REQUEST_ID, resource="notes")  # noqa: S106


# ---------------------------------------------------------------------------
# AGT-READ-001 -- the adapter adds no filtering of its own
# ---------------------------------------------------------------------------


def test_the_adapter_returns_what_the_upstream_returned(monkeypatch: Any) -> None:
    """**AGT-READ-001.** The same identity gets the same RLS-constrained rows.

    The property that makes that true is that this process adds **no filtering
    of its own** between PostgREST and the caller: the rows come back as sent.
    Anything else would be a second opinion about which rows an owner may see,
    and it would disagree with the database's the moment a policy changed.

    Measured live in Run 6's rig, where the adapter's own request returned the
    owner's three notes and the other owner's agent returned one -- the two
    counts differing is what makes each meaningful.
    """
    lock = _lock()
    _with_scopes(monkeypatch, "notes:read")
    upstream_rows = [{"title": "alpha"}, {"title": "beta"}, {"title": "weird,title"}]
    monkeypatch.setattr(mcp_tools, "execute", lambda *_, **__: list(upstream_rows))

    result = query_resource(lock, base_url=BASE, token="t", request_id=REQUEST_ID, resource="notes")  # noqa: S106

    assert result["rows"] == upstream_rows
    assert result["row_count"] == len(upstream_rows)


def test_the_caller_token_is_what_the_adapter_forwards(monkeypatch: Any) -> None:
    """No service identity between the caller and the database (ADR 0125)."""
    lock = _lock()
    _with_scopes(monkeypatch, "notes:read")
    seen: dict[str, Any] = {}

    def capture(
        base_url: str, token: str, request: Any, *, request_id: str
    ) -> list[dict[str, Any]]:
        seen["base_url"] = base_url
        seen["token"] = token
        seen["request_id"] = request_id
        return []

    monkeypatch.setattr(mcp_tools, "execute", capture)
    query_resource(
        lock,
        base_url=BASE,
        token="the.caller.token",  # noqa: S106
        request_id=REQUEST_ID,
        resource="notes",
    )

    assert seen["token"] == "the.caller.token"  # noqa: S105 -- the forwarded value, asserted
    assert seen["base_url"] == BASE


def test_nothing_dials_the_locks_published_upstream() -> None:
    """ADR 0126. `upstream` is the surface's public identity, not a dial string.

    Both are correct-looking URLs and only one resolves from the internal
    network, so the separation has to be asserted rather than remembered.
    """
    service = Path(mcp_tools.__file__).parent
    offenders = []
    for path in sorted(service.glob("mcp_*.py")):
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"'):
                continue
            if ".upstream" in stripped:
                offenders.append(f"{path.name}:{number} {stripped}")
    assert not offenders, f"the lock's published upstream is being used: {offenders}"


# ---------------------------------------------------------------------------
# exactly six tools, from the lock (four until Session 9 Run 4 — D486)
# ---------------------------------------------------------------------------


def test_the_registered_roster_is_the_locks_roster_and_it_is_six() -> None:
    """**The equality, restored (D486).**

    Run 4 widened the lock's roster to six and left `register()` at four, and for
    exactly one run this asserted the gap was EXACTLY `WRITE_TOOLS` — an exact
    set, never a subset (D300). Run 5 registers the two writes, so the gap is
    empty and the honest assertion is equality again.

    **Two lists, not one read twice.** `mcp_tools.TOOL_NAMES` is written out in
    that module rather than imported from `mcp_lock`; aliasing the constant would
    make this line compare a value with itself, which is §6's *"a test comparing
    two constants is not testing the thing between them"* with only one constant
    left to compare.
    """
    assert EXPECTED_TOOL_NAMES == tuple(sorted((*METADATA_TOOLS, *READ_TOOLS, *WRITE_TOOLS)))
    assert len(EXPECTED_TOOL_NAMES) == 6
    assert mcp_tools.TOOL_NAMES == EXPECTED_TOOL_NAMES
    assert set(WRITE_TOOLS) <= set(mcp_tools.TOOL_NAMES)


def _write_tool_entry(name: str) -> dict[str, Any]:
    """One structurally valid write tool for a lock document (Run 4's shape)."""
    scope = "notes:write" if name == "create_note" else "tasks:write"
    arguments = (
        ["p_title", "p_content"]
        if name == "create_note"
        else ["p_task_id", "p_expected_status", "p_new_status"]
    )
    return {
        "name": name,
        "kind": "write",
        "source": "postgrest",
        "timeout_ms": 5000,
        "discovery_scope_sets": [[scope]],
        "descriptions": [],
        "resources": [],
        "operation": {
            "method": "post",
            "path": f"/rpc/{name}",
            "operation_id": f"rpc.{name}.post",
        },
        "arguments": arguments,
        "required_scopes": [scope],
        "max_affected_rows": 1,
        "idempotent": name == "update_task_status",
        "audit_redact": ["p_content"] if name == "create_note" else [],
    }


def _lock_document(*names: str) -> dict[str, Any]:
    """A structurally VALID lock document carrying exactly `names`.

    Valid in every other respect on purpose: a fixture that was also malformed
    would be refused for the wrong reason, and the test would pass while proving
    nothing about the tool set. That is what the first draft of this did.
    """
    resource = {
        "name": "notes",
        "capability": "query_notes",
        "columns": ["id", "title"],
        "filters": [{"column": "title", "operators": ["eq"]}],
        "order_by": [{"column": "title", "direction": "asc"}],
        "max_rows": 200,
        "required_scopes": ["notes:read"],
        "operation": {"method": "get", "path": "/notes", "operation_id": "notes.get"},
    }
    tools = []
    for name in names:
        if name in WRITE_TOOLS:
            tools.append(_write_tool_entry(name))
            continue
        reads = name in ("query_resource", "run_report")
        tools.append(
            {
                "name": name,
                "kind": "read" if reads else "metadata",
                "source": "postgrest" if reads else "lock",
                "timeout_ms": 5000 if reads else 1000,
                "discovery_scope_sets": [["notes:read"] if reads else ["meta:read"]],
                "descriptions": [],
                "resources": [resource] if reads else [],
            }
        )
    return {
        "schema_version": 1,
        "contract_id": "x",
        "project_key": "p",
        "upstream": "https://p.test/api/rest",
        "canonical_sha256": "a" * 64,
        "capability_count": 7,
        "tool_count": len(tools),
        "tools": tools,
    }


def test_a_valid_six_tool_lock_loads(tmp_path: Path) -> None:
    """**The control** for the refusals below: the fixture is otherwise good."""
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(_lock_document(*EXPECTED_TOOL_NAMES)), encoding="utf-8")

    assert tuple(tool.name for tool in load_lock(path).tools) == EXPECTED_TOOL_NAMES


def test_a_lock_with_a_seventh_tool_is_refused(tmp_path: Path) -> None:
    """Offline, at load, rather than on a cluster — asserted AFTER the roster
    widened, not only before (D486): the property is that the surface is
    enumerated, and the number moving must not have loosened it."""
    path = tmp_path / "lock.json"
    document = _lock_document(*EXPECTED_TOOL_NAMES, "delete_everything")
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(LockError, match="delete_everything"):
        load_lock(path)


def test_a_lock_missing_one_of_the_six_is_refused(tmp_path: Path) -> None:
    """The other direction: a subset is not the contract either."""
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(_lock_document(*EXPECTED_TOOL_NAMES[:5])), encoding="utf-8")

    with pytest.raises(LockError):
        load_lock(path)


def test_a_lock_from_an_unknown_schema_version_is_refused(tmp_path: Path) -> None:
    """A surface from a schema this code has not seen is a surface nobody
    reviewed against this code.

    **The example of "unknown" is DERIVED, and it used to be the literal 2**
    (D883). Session 16 Run 2 made 2 known, so this stopped testing an unknown
    version and started testing a known one -- and it then failed on the tool
    roster instead, which reads like the parser having lost its version check
    entirely. Exactly the shape of the CI step that asserted
    `CURRENT_SESSION == 2`: a literal correct when written, wrong once the
    constant moved, and misleading in between.
    """
    unknown = max(SUPPORTED_SCHEMA_VERSIONS) + 1
    assert unknown not in SUPPORTED_SCHEMA_VERSIONS

    path = tmp_path / "lock.json"
    path.write_text(json.dumps({"schema_version": unknown, "tools": []}), encoding="utf-8")

    with pytest.raises(LockError, match="schema_version"):
        load_lock(path)


def test_a_metadata_tool_may_not_name_a_backend_resource(tmp_path: Path) -> None:
    """`list_resources` reaching a backend would make discovery depend on it."""
    lock = _lock()
    for name in ("describe_resource", "list_resources"):
        assert lock.tool(name).resources == ()
        assert lock.tool(name).source == "lock"


def test_the_context_is_read_and_never_resolved_by_a_tool() -> None:
    """One resolution per request (ADR 0125), so one place decides refusals."""
    text = Path(mcp_tools.__file__).read_text(encoding="utf-8")

    assert "resolve_agent_context" not in text
    assert "current_agent_context" in text
    assert hasattr(mcp_authorization, "current_agent_context")


# ---------------------------------------------------------------------------
# the write half of the lock (Session 9 Run 4 — D486, D470)
# ---------------------------------------------------------------------------


def _loaded(tmp_path: Path, document: dict[str, Any]) -> Any:
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return load_lock(path)


def test_the_write_spec_is_parsed_in_full(tmp_path: Path) -> None:
    """Every member of the write shape decides what a caller can do, so every
    member is read strictly — arguments in PARAMETER ORDER, never sorted."""
    lock = _loaded(tmp_path, _lock_document(*EXPECTED_TOOL_NAMES))

    create = lock.tool("create_note")
    assert create.write is not None
    assert create.write.arguments == ("p_title", "p_content")
    assert create.write.max_affected_rows == 1
    assert create.write.idempotent is False
    assert create.write.required_scopes == ("notes:write",)
    assert create.write.operation.method == "post"
    assert create.write.operation.path == "/rpc/create_note"
    assert create.audit_redact == ("p_content",)
    assert create.resources == ()

    update = lock.tool("update_task_status")
    assert update.write is not None
    assert update.write.idempotent is True
    assert update.write.arguments == ("p_task_id", "p_expected_status", "p_new_status")
    assert update.audit_redact == ()

    for name in (*METADATA_TOOLS, *READ_TOOLS):
        assert lock.tool(name).write is None


def test_a_write_tool_naming_a_resource_is_refused(tmp_path: Path) -> None:
    """The third kind arm (D486): a write is one-to-one and selects nothing."""
    document = _lock_document(*EXPECTED_TOOL_NAMES)
    query = next(tool for tool in document["tools"] if tool["name"] == "query_resource")
    create = next(tool for tool in document["tools"] if tool["name"] == "create_note")
    create["resources"] = list(query["resources"])

    with pytest.raises(LockError, match="must name no resource"):
        _loaded(tmp_path, document)


def test_a_tool_whose_kind_disagrees_with_the_roster_is_refused(tmp_path: Path) -> None:
    """A reviewed name with a different kind is a different tool wearing it —
    the lock cannot silently move a name between the dispatch paths."""
    document = _lock_document(*EXPECTED_TOOL_NAMES)
    create = next(tool for tool in document["tools"] if tool["name"] == "create_note")
    create["kind"] = "read"

    with pytest.raises(LockError, match="roster says"):
        _loaded(tmp_path, document)


def test_a_write_over_get_is_refused_at_load(tmp_path: Path) -> None:
    """The compiler refuses this upstream; the lock validates as if it had not,
    because a lock is an input rather than a teammate."""
    document = _lock_document(*EXPECTED_TOOL_NAMES)
    create = next(tool for tool in document["tools"] if tool["name"] == "create_note")
    create["operation"]["method"] = "get"

    with pytest.raises(LockError, match="a write is a POST"):
        _loaded(tmp_path, document)


@pytest.mark.parametrize(
    ("field", "value", "why"),
    [
        ("max_affected_rows", 0, "a write bounded to nothing"),
        ("idempotent", "yes", "not a boolean"),
        ("arguments", [], "declares no arguments"),
    ],
)
def test_a_degenerate_write_member_is_refused(
    tmp_path: Path, field: str, value: Any, why: str
) -> None:
    document = _lock_document(*EXPECTED_TOOL_NAMES)
    create = next(tool for tool in document["tools"] if tool["name"] == "create_note")
    create[field] = value

    with pytest.raises(LockError, match=why):
        _loaded(tmp_path, document)


# ---------------------------------------------------------------------------
# the write request (Session 9 Run 4 — D477, D470, rig4)
# ---------------------------------------------------------------------------

#: The same spec `_lock()` carries, so the request tests and the registration
#: tests cannot drift into describing two different `create_note`s.
CREATE_WRITE = CREATE_SPEC


def test_a_write_request_is_a_body_and_no_query() -> None:
    """D477's resolution: no `select`, no `limit`, no filters — everything the
    caller says travels as the JSON argument document."""
    request = build_write_request(
        CREATE_WRITE, timeout_ms=5000, arguments={"p_title": "t", "p_content": "c"}
    )

    assert request.method == "post"
    assert request.target == "/rpc/create_note"
    assert request.query == ""
    assert json.loads(request.body) == {"p_title": "t", "p_content": "c"}


def test_a_caller_value_that_looks_like_syntax_stays_a_value() -> None:
    """AGT-SQL-001 on the write path. `&limit=1` in a read filter was the
    measured injection (3 rows vs 1); in a write it must land in the BODY as a
    literal, with the query string untouched — there is no query string."""
    request = build_write_request(
        CREATE_WRITE,
        timeout_ms=5000,
        arguments={"p_title": "zzz&limit=1", "p_content": 'a,"b"\\'},
    )

    assert "?" not in request.target
    assert json.loads(request.body)["p_title"] == "zzz&limit=1"
    assert json.loads(request.body)["p_content"] == 'a,"b"\\'


def test_an_argument_name_the_lock_does_not_declare_is_refused() -> None:
    """A caller supplies values, never names (ADR 0127) — and measured (rig4),
    an unknown name upstream is a `404 PGRST202`, the same status as the
    product's own "no such task", so the refusal has to happen HERE."""
    with pytest.raises(QueryRefusal, match="p_owner_id"):
        build_write_request(
            CREATE_WRITE,
            timeout_ms=5000,
            arguments={"p_title": "t", "p_content": "c", "p_owner_id": "x"},
        )


def test_a_missing_argument_is_refused_before_the_dial() -> None:
    with pytest.raises(QueryRefusal, match="p_content"):
        build_write_request(CREATE_WRITE, timeout_ms=5000, arguments={"p_title": "t"})


def test_a_structured_argument_value_is_refused() -> None:
    """Measured: PostgREST coerces a JSON number to text, so a number is honest
    input — an object or array in a value position is not."""
    for bad in ({"nested": 1}, ["a"], None):
        with pytest.raises(QueryRefusal, match="string, a number or a boolean"):
            build_write_request(
                CREATE_WRITE, timeout_ms=5000, arguments={"p_title": bad, "p_content": "c"}
            )
    built = build_write_request(
        CREATE_WRITE, timeout_ms=5000, arguments={"p_title": 7, "p_content": "c"}
    )
    assert json.loads(built.body)["p_title"] == 7


def test_a_read_request_still_carries_its_own_body() -> None:
    """The read half of D477: `execute` sends what was built, so the built
    read must carry what `execute` used to hardcode."""
    posted = build_request(
        Resource(
            name="owner_activity_report",
            capability="run_report",
            columns=("notes_total",),
            filters={},
            order_by=(),
            max_rows=1,
            required_scopes=("notes:read", "tasks:read"),
            operation=Operation(
                method="post",
                path="/rpc/owner_activity_report",
                operation_id="rpc.owner_activity_report.post",
            ),
        ),
        timeout_ms=5000,
    )
    assert posted.body == b"{}"

    fetched = build_request(NOTES, timeout_ms=5000)
    assert fetched.body is None


# ---------------------------------------------------------------------------
# the write executor (Session 9 Run 4 — ADR 0139, D487, rig4)
# ---------------------------------------------------------------------------


class _Response:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: Any) -> None:
        return None


def _upstream_answers(monkeypatch: Any, status: int, body: bytes) -> None:
    import io
    import urllib.error

    from app import mcp_upstream

    def answer(request: Any, timeout: float = 0) -> Any:
        if status == 200:
            return _Response(status, body)
        raise urllib.error.HTTPError(request.full_url, status, "refused", None, io.BytesIO(body))

    monkeypatch.setattr(mcp_upstream.urllib.request, "urlopen", answer)


def _write_request() -> Any:
    return build_write_request(
        CREATE_WRITE, timeout_ms=5000, arguments={"p_title": "t", "p_content": "c"}
    )


def test_a_committed_write_returns_its_one_row(monkeypatch: Any) -> None:
    """Measured (rig4): a non-SETOF composite return is a single JSON OBJECT —
    the SETOF control was an array — so the write parse accepts one object and
    hands back one row."""
    _upstream_answers(monkeypatch, 200, b'{"id": "x", "title": "t"}')

    rows = execute_write(BASE, "tok", _write_request(), max_affected_rows=1, request_id=REQUEST_ID)
    assert rows == [{"id": "x", "title": "t"}]


def test_the_bound_is_checked_against_the_response_never_trusted(monkeypatch: Any) -> None:
    """D487: both writes return exactly one row, so this firing means the
    function's shape changed underneath the lock — a loud fault, not a clamp."""
    _upstream_answers(monkeypatch, 200, b'[{"id": "1"}, {"id": "2"}]')

    with pytest.raises(UpstreamRefusal, match="underneath the lock"):
        execute_write(BASE, "tok", _write_request(), max_affected_rows=1, request_id=REQUEST_ID)


def test_the_cas_conflict_reaches_the_caller_as_a_token(monkeypatch: Any) -> None:
    """ADR 0139. Measured: the product's compare-and-swap branch arrives as
    409/`PT409` — translated to `write_conflict` with THIS repository's
    sentence, never the wire's."""
    _upstream_answers(
        monkeypatch,
        409,
        b'{"code":"PT409","details":null,"hint":null,'
        b'"message":"AP409: the task is not in the expected status"}',
    )

    with pytest.raises(AgentVisible) as caught:
        execute_write(BASE, "tok", _write_request(), max_affected_rows=1, request_id=REQUEST_ID)
    assert caught.value.token == WRITE_CONFLICT
    assert "AP409" not in str(caught.value)
    assert "expected state" in caught.value.detail


def test_a_missing_row_and_a_missing_function_are_not_the_same_404(monkeypatch: Any) -> None:
    """**The measured ambiguity ADR 0139 rests on.** `PT404` (the row this
    write names does not exist) and `PGRST202` (the function the request was
    built for does not exist) are BOTH a 404 — the first is the caller's to
    read, the second is a structural fault and stays masked."""
    _upstream_answers(monkeypatch, 404, b'{"code":"PT404","message":"AP404: no such task"}')
    with pytest.raises(AgentVisible) as caught:
        execute_write(BASE, "tok", _write_request(), max_affected_rows=1, request_id=REQUEST_ID)
    assert caught.value.token == ROW_NOT_FOUND

    _upstream_answers(monkeypatch, 404, b'{"code":"PGRST202","message":"Could not find"}')
    with pytest.raises(UpstreamRefusal):
        execute_write(BASE, "tok", _write_request(), max_affected_rows=1, request_id=REQUEST_ID)


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (400, b'{"code":"22P02","message":"invalid input value for enum task_status"}'),
        (401, b'{"code":"PT401","message":"AP401: no request identity"}'),
        (500, b"not json at all"),
        (403, b'{"no_code": true}'),
    ],
)
def test_every_unmapped_refusal_stays_masked(monkeypatch: Any, status: int, body: bytes) -> None:
    """ADR 0139's boundary from the other side: a 22P02 body NAMES the schema's
    enum type (measured), `PT401` is the authentication plane's business, and a
    body the parser cannot read must not become one it guesses about."""
    _upstream_answers(monkeypatch, status, body)

    with pytest.raises(UpstreamRefusal) as caught:
        execute_write(BASE, "tok", _write_request(), max_affected_rows=1, request_id=REQUEST_ID)
    assert "enum" not in str(caught.value)
    assert "task_status" not in str(caught.value)


def test_the_write_body_is_what_the_transport_sends(monkeypatch: Any) -> None:
    """D477 end to end: the bytes `build_write_request` serialized are the
    bytes on the wire, and the read path's old hardcoded `b\"{}\"` is gone."""
    from app import mcp_upstream

    seen: dict[str, Any] = {}

    def record(request: Any, timeout: float = 0) -> Any:
        seen["data"] = request.data
        seen["content_type"] = request.get_header("Content-type")
        return _Response(200, b'{"id": "x"}')

    monkeypatch.setattr(mcp_upstream.urllib.request, "urlopen", record)
    request = _write_request()
    execute_write(BASE, "tok", request, max_affected_rows=1, request_id=REQUEST_ID)

    assert seen["data"] == request.body
    assert seen["content_type"] == "application/json"


# ---------------------------------------------------------------------------
# the two write TOOLS, and AGT-WRITE-001 (Session 9 Run 5 — ADR 0140, D476)
# ---------------------------------------------------------------------------


def _registered(
    monkeypatch: Any, *scopes: str, audit: bool = True
) -> tuple[Any, Any, list[dict[str, Any]]]:
    """`register()` run against the six-tool lock, with a caller holding `scopes`.

    **The audit calls are stubbed by default, and the stub RECORDS** (ADR 0141).
    Since Run 6 every read and write opens a record before its work and closes it
    after, so a rig that left the audit path reaching a fake `base_url` would
    make every write fail closed -- correctly, and for a reason unrelated to what
    each test measures. The returned list is what the record-keeper would have
    been told, in order.

    `audit=False` leaves the real calls in place, which is how the fail-closed
    arms make the audit path fail for real rather than by assertion.
    """
    from app.mcp_budgets import ReadSlots

    lock = _lock(NOTES)
    _with_scopes(monkeypatch, *scopes)
    monkeypatch.setattr(mcp_authorization, "current_token", lambda: "the.callers.token")
    monkeypatch.setattr(mcp_authorization, "current_request_id", lambda: REQUEST_ID)

    recorded: list[dict[str, Any]] = []
    if audit:

        def began(base_url: str, token: str, **kwargs: Any) -> str:
            recorded.append({"phase": "begin", "base_url": base_url, "token": token, **kwargs})
            return "audit-1"

        def completed(base_url: str, token: str, **kwargs: Any) -> bool:
            recorded.append({"phase": "complete", "base_url": base_url, "token": token, **kwargs})
            return True

        monkeypatch.setattr(mcp_tools, "audit_begin", began)
        monkeypatch.setattr(mcp_tools, "audit_complete", completed)

    registry = _Registry()
    mcp_tools.register(registry, lock, base_url=BASE, slots=ReadSlots(2))
    return lock, registry, recorded


def test_a_write_tool_exposes_the_locks_own_argument_names_in_order() -> None:
    """The reviewed contract froze the argument list, so the tool exposes it.

    **A translation layer here would be a second naming authority** for one
    list, and it would fail four steps away: `build_write_request` checks a
    caller's names against the lock in BOTH directions, and PostgREST resolves a
    function by the names supplied -- a renamed parameter is a `404 PGRST202`
    upstream, the same status as the product's own "no such row" with the
    opposite meaning (rig4).

    Asserted against the signature rather than a comment, and in ORDER, because
    parameter order is what the contract carries (D470).
    """
    import inspect

    from app.mcp_budgets import ReadSlots

    registry = _Registry()
    mcp_tools.register(registry, _lock(NOTES), base_url=BASE, slots=ReadSlots(2))

    for name, spec in (("create_note", CREATE_SPEC), ("update_task_status", UPDATE_SPEC)):
        signature = inspect.signature(registry.tools[name])
        assert tuple(signature.parameters) == spec.arguments, (
            f"{name} exposes {tuple(signature.parameters)}, the lock declares {spec.arguments}"
        )
        for parameter in signature.parameters.values():
            assert parameter.default is inspect.Parameter.empty, (
                f"{name}.{parameter.name} has a default; a caller supplies a value for "
                "every declared argument, because a missing one is a PGRST202 upstream"
            )


def test_a_write_reaches_the_operation_the_lock_names_with_the_callers_token(
    monkeypatch: Any,
) -> None:
    """The whole write path through the registered tool, stubbed at the dial.

    **The control for every refusal below.** Without an arm that succeeds, a
    write path that refused everything would pass all of them.
    """
    import asyncio

    _, registry, _recorded = _registered(monkeypatch, "notes:write")
    seen: dict[str, Any] = {}

    def capture(
        base_url: str, token: str, request: Any, *, max_affected_rows: int, request_id: str
    ) -> Any:
        seen.update(
            base_url=base_url,
            token=token,
            target=request.target,
            method=request.method,
            body=json.loads(request.body),
            bound=max_affected_rows,
            request_id=request_id,
        )
        return [{"id": "note-1", "title": "t"}]

    monkeypatch.setattr(mcp_tools, "execute_write", capture)
    result = asyncio.run(registry.tools["create_note"](p_title="t", p_content="c"))

    assert seen["target"] == "/rpc/create_note", "the path comes from the lock, not the caller"
    assert seen["method"] == "post"
    assert seen["body"] == {"p_title": "t", "p_content": "c"}
    assert seen["bound"] == 1, "the lock's max_affected_rows, handed to the executor (D487)"
    assert seen["token"] == "the.callers.token"  # noqa: S105 -- the forwarded value, asserted
    assert seen["base_url"] == BASE
    assert result == {"tool": "create_note", "row_count": 1, "row": {"id": "note-1", "title": "t"}}


def test_a_write_the_caller_holds_no_scope_for_is_refused_before_any_dial(
    monkeypatch: Any,
) -> None:
    """**AGT-WRITE-001**, the invocation half — refused, not merely hidden.

    A read-only agent that knows the name and sends it anyway is refused here,
    and nothing is dialled: the executor is replaced by one that fails the test
    if it is reached, so "refused" cannot be satisfied by an upstream that
    happened to say no.
    """
    import asyncio

    from fastmcp.exceptions import ToolError

    _, registry, _recorded = _registered(monkeypatch, "meta:read", "notes:read", "tasks:read")

    def unreachable(*_: Any, **__: Any) -> Any:
        raise AssertionError("a write was dialled for a caller holding no write scope")

    monkeypatch.setattr(mcp_tools, "execute_write", unreachable)

    with pytest.raises(ToolError, match="notes:write") as created:
        asyncio.run(registry.tools["create_note"](p_title="t", p_content="c"))
    with pytest.raises(ToolError, match="tasks:write"):
        asyncio.run(
            registry.tools["update_task_status"](
                p_task_id="t", p_expected_status="todo", p_new_status="done"
            )
        )

    assert "notes:read" not in str(created.value), (
        "the refusal names the scopes the TOOL needs, never the ones the caller holds -- "
        "the second would be this process repeating a caller's own token back to it"
    )


def test_holding_one_write_scope_does_not_carry_the_other(monkeypatch: Any) -> None:
    """`notes:write` is not `tasks:write`; the two writes are separate grants.

    The control is the first half: the same caller, the same rig, and the tool it
    DOES hold the scope for must go through. Without it this passes against a
    write path that refuses everything.
    """
    import asyncio

    from fastmcp.exceptions import ToolError

    _, registry, _recorded = _registered(monkeypatch, "notes:write")
    monkeypatch.setattr(mcp_tools, "execute_write", lambda *_, **__: [{"id": "x"}])

    served = asyncio.run(registry.tools["create_note"](p_title="t", p_content="c"))
    assert served["row_count"] == 1

    with pytest.raises(ToolError, match="tasks:write"):
        asyncio.run(
            registry.tools["update_task_status"](
                p_task_id="t", p_expected_status="todo", p_new_status="done"
            )
        )


def test_a_write_result_is_byte_bounded_like_a_read(monkeypatch: Any) -> None:
    """§6 question 5: which of `MAX_SERIALIZED_BYTES`' callers got it? (D497)

    The ceiling was reachable only through the ROW check, and a write has no row
    ceiling -- so the write path would have been the one route returning an
    unbounded response. `content` is an unbounded `text` column and `create_note`
    echoes the created row back, so this is not theoretical.

    Caller-visible, because it is the one budget a caller can stay inside by
    asking differently.
    """
    import asyncio

    from fastmcp.exceptions import ToolError

    _, registry, _recorded = _registered(monkeypatch, "notes:write")
    monkeypatch.setattr(mcp_tools, "execute_write", lambda *_, **__: [{"content": "x" * 2_000_000}])

    with pytest.raises(ToolError, match="ceiling"):
        asyncio.run(registry.tools["create_note"](p_title="t", p_content="c"))


def test_a_translated_write_refusal_reaches_the_caller_through_the_tool(
    monkeypatch: Any,
) -> None:
    """ADR 0139 through the registered tool, not only through the executor.

    `invoke_write` catches `UpstreamRefusal` and must NOT catch `AgentVisible`: a
    compare-and-swap conflict is a retry instruction and is the caller's to read.
    The structural arm beside it is the control -- an unmapped refusal stays
    masked, so the first assertion is not satisfied by a path that relays
    everything.
    """
    import asyncio

    from fastmcp.exceptions import ToolError

    _, registry, _recorded = _registered(monkeypatch, "tasks:write")

    def conflicted(*_: Any, **__: Any) -> Any:
        raise AgentVisible(WRITE_CONFLICT, "the row is not in the expected state", WRITE_REJECTED)

    monkeypatch.setattr(mcp_tools, "execute_write", conflicted)
    with pytest.raises(ToolError, match="write_conflict"):
        asyncio.run(
            registry.tools["update_task_status"](
                p_task_id="t", p_expected_status="todo", p_new_status="done"
            )
        )

    def structural(*_: Any, **__: Any) -> Any:
        raise UpstreamRefusal("upstream refused with status 500")

    monkeypatch.setattr(mcp_tools, "execute_write", structural)
    with pytest.raises(ToolRefusal):
        asyncio.run(
            registry.tools["update_task_status"](
                p_task_id="t", p_expected_status="todo", p_new_status="done"
            )
        )


def test_a_write_argument_the_lock_does_not_declare_is_refused(monkeypatch: Any) -> None:
    """The lock's argument list, enforced where a caller reaches it.

    The registered signature already refuses an unknown keyword, so this asserts
    the module function rather than relying on Python's own `TypeError` to be the
    boundary.
    """
    lock, _registry, _recorded = _registered(monkeypatch, "notes:write")

    with pytest.raises(AgentVisible, match="p_owner_id"):
        mcp_tools.invoke_write(
            lock,
            base_url=BASE,
            token="t",  # noqa: S106 -- a placeholder, not a credential
            request_id=REQUEST_ID,
            tool="create_note",
            arguments={"p_title": "t", "p_content": "c", "p_owner_id": "someone-else"},
        )


def test_a_write_whose_response_is_not_one_row_is_a_loud_structural_fault(
    monkeypatch: Any,
) -> None:
    """D487: both writes are `RETURNS <composite>`, so zero rows is a shape that
    changed underneath the lock — and the write has already committed."""
    lock, _registry, _recorded = _registered(monkeypatch, "notes:write")
    monkeypatch.setattr(mcp_tools, "execute_write", lambda *_, **__: [])

    with pytest.raises(ToolRefusal):
        mcp_tools.invoke_write(
            lock,
            base_url=BASE,
            token="t",  # noqa: S106 -- a placeholder, not a credential
            request_id=REQUEST_ID,
            tool="create_note",
            arguments={"p_title": "t", "p_content": "c"},
        )


# ---------------------------------------------------------------------------
# discovery filters NAMES as well as resources (Session 9 Run 5 — ADR 0140, D476)
# ---------------------------------------------------------------------------


class _Listed:
    """The least of a framework tool object the visibility filter reads."""

    def __init__(self, name: str) -> None:
        self.name = name


def _visible_to(
    monkeypatch: Any, lock: Any, *scopes: str, roster: tuple[str, ...] = ()
) -> list[str]:
    """The roster `on_list_tools` returns to a caller holding `scopes`.

    The context is supplied by patching `current_agent_context` in the module the
    middleware reads it from -- which is the same accessor production uses, and
    the same one `AgentContextMiddleware` populates. Nothing here resolves a
    context, exactly as nothing in the middleware does.
    """
    import asyncio

    from app.mcp_authorization import ToolVisibilityMiddleware

    monkeypatch.setattr(
        mcp_authorization,
        "current_agent_context",
        lambda: AgentContext(
            agent_id="agent-1",
            role_name="apg_probe_dev_agent_writer",
            scopes=tuple(scopes),
            authz_version=1,
            owner_id=OWNER,
        ),
    )

    async def call_next(_: Any) -> Any:
        return [_Listed(name) for name in (roster or EXPECTED_TOOL_NAMES)]

    listed = asyncio.run(ToolVisibilityMiddleware(lock).on_list_tools(None, call_next))
    return sorted(tool.name for tool in listed)


def test_a_write_name_is_hidden_from_a_caller_without_its_scope(monkeypatch: Any) -> None:
    """**AGT-WRITE-001**, the discovery half — and `discoverable_by`'s first
    production caller (D476).

    The reader arm and the writer arm together are what make either meaningful: a
    filter that hid everything would pass the first alone, and one that hid
    nothing would pass the second alone.
    """
    lock = _lock(NOTES)

    reader = _visible_to(monkeypatch, lock, "meta:read", "notes:read")
    assert reader == ["describe_resource", "list_resources", "query_resource"], (
        f"a read-only agent was shown {reader}"
    )

    writer = _visible_to(monkeypatch, lock, "meta:read", "notes:write", "tasks:write")
    assert "create_note" in writer and "update_task_status" in writer, (
        "THE CONTROL: an agent holding both write scopes must see both names, or the "
        "exclusion above is satisfied by a filter that hides everything"
    )


def test_hiding_a_name_does_not_refuse_the_call_and_that_is_why_both_exist(
    monkeypatch: Any,
) -> None:
    """**The two levels are distinct, and the framework is why** (ADR 0140).

    Measured on the pinned version (rig5 M2): a tool absent from `tools/list` is
    still callable by name, and it runs. So the roster is disclosure control and
    the scope check at call time is the boundary. A proof that asserted only the
    hiding would describe a control the framework does not provide.
    """
    import asyncio

    from fastmcp.exceptions import ToolError

    lock = _lock(NOTES)
    assert "create_note" not in _visible_to(monkeypatch, lock, "meta:read", "notes:read")

    _, registry, _recorded = _registered(monkeypatch, "meta:read", "notes:read")
    monkeypatch.setattr(
        mcp_tools, "execute_write", lambda *_, **__: pytest.fail("the hidden write was dialled")
    )

    with pytest.raises(ToolError, match="notes:write"):
        asyncio.run(registry.tools["create_note"](p_title="t", p_content="c"))


def test_a_visible_name_can_still_hide_a_resource_behind_it(monkeypatch: Any) -> None:
    """**Both levels, in one caller.** The name filter and the resource filter are
    different mechanisms answering different questions.

    `query_resource`'s NAME is visible to an agent holding `notes:read`; the
    `owner_activity_report` RESOURCE is not, because it needs `notes:read` AND
    `tasks:read`, a conjunction (D421). Session 8 proved the resource half
    against a roster that hid nothing; this proves the pair.
    """
    lock = _lock(NOTES)

    names = _visible_to(monkeypatch, lock, "meta:read", "notes:read")
    assert "query_resource" in names, "the name of a tool the caller CAN use is shown"
    assert "run_report" not in names, "and the name of one it cannot use is not"

    _with_scopes(monkeypatch, "meta:read", "notes:read")
    resources = {entry["resource"] for entry in list_resources(lock)["resources"]}
    assert resources == {"notes"}, (
        f"the resource level is a separate filter and returned {resources}"
    )


def test_a_registered_name_the_lock_does_not_carry_is_hidden(monkeypatch: Any) -> None:
    """Fail closed: a name nobody reviewed is not a name to advertise.

    `load_lock` makes this unreachable in a deployment, which is exactly why the
    branch needs a test — nothing else would ever execute it. The caller holds
    every scope, so it cannot pass by the scope check instead.
    """
    shown = _visible_to(
        monkeypatch,
        _lock(NOTES),
        "meta:read",
        "notes:read",
        "tasks:read",
        "notes:write",
        "tasks:write",
        roster=("list_resources", "delete_everything"),
    )

    assert shown == ["list_resources"], f"a name absent from the lock was advertised: {shown}"


def test_discovery_with_no_resolved_context_refuses_rather_than_listing() -> None:
    """No context, no roster.

    Refused rather than answered with an empty list, because an empty roster is a
    statement about this caller and a refusal is not. `call_next` fails the test
    if it is reached, so the check is proved to happen BEFORE the roster is built.
    """
    import asyncio

    from app.mcp_authorization import ToolVisibilityMiddleware

    async def call_next(_: Any) -> Any:
        raise AssertionError("the roster was built before the context was checked")

    with pytest.raises(UpstreamRefusal):
        asyncio.run(ToolVisibilityMiddleware(_lock(NOTES)).on_list_tools(None, call_next))


def _raising(error: Exception) -> Any:
    """A stub that raises. Named, so a call site reads as an arrangement."""

    def refuse(*_: Any, **__: Any) -> Any:
        raise error

    return refuse


# ---------------------------------------------------------------------------
# the request id, and the audit lifecycle (Session 9 Run 6 — ADR 0141, D477)
# ---------------------------------------------------------------------------


def test_the_request_id_reaches_every_upstream_request_of_one_call(monkeypatch: Any) -> None:
    """**D477's propagation, asserted on the wire rather than described.**

    One tool call is four upstream requests -- context, begin, the write,
    complete -- and this asserts the id on the three the tool itself makes. The
    context lookup's own header is asserted next door in
    `test_no_header_names_a_principal`, which is where the enumerated header set
    lives.

    A FIXED id rather than a generated one, so the assertion can name it: a test
    that minted its own could only say "some id was forwarded", which is
    satisfied by forwarding the wrong one.
    """
    import asyncio

    _, registry, recorded = _registered(monkeypatch, "notes:write")
    dialled: dict[str, Any] = {}

    def capture(base_url: str, token: str, request: Any, **kwargs: Any) -> Any:
        dialled["request_id"] = kwargs["request_id"]
        return [{"id": "note-1"}]

    monkeypatch.setattr(mcp_tools, "execute_write", capture)
    asyncio.run(registry.tools["create_note"](p_title="t", p_content="c"))

    assert dialled["request_id"] == REQUEST_ID, "the write did not carry the request id"
    assert [entry["phase"] for entry in recorded] == ["begin", "complete"]
    assert {entry["request_id"] for entry in recorded} == {REQUEST_ID}, (
        "both audit calls must carry the SAME id as the write, or the record and the "
        "work it describes cannot be joined"
    )


def test_the_forwarded_header_set_and_its_guard_moved_together() -> None:
    """**D477, and the reason this is a test rather than a comment.**

    `FORWARDED_HEADERS` grew from two to three in Run 6 and `_dial`'s equality
    guard reads it. A widened allowlist whose checker did not move is D300's
    shape -- four times paid for now -- and both of Session 8's allowlist
    failures (D468) were RIGHT to fail.

    Asserted as an equality against what `_dial` actually builds, so a fourth
    header added to one side and not the other fails here.
    """
    from app.mcp_query import FORWARDED_HEADERS, REQUEST_ID_HEADER

    assert REQUEST_ID_HEADER in FORWARDED_HEADERS
    assert set(FORWARDED_HEADERS) == {"Authorization", "Accept", "X-Request-Id"}

    guard = Path(mcp_tools.__file__).parent / "mcp_upstream.py"
    text = guard.read_text(encoding="utf-8")
    assert "set(headers) != set(FORWARDED_HEADERS)" in text, (
        "the guard is no longer an equality against the allowlist; a subset check is "
        "exactly the repair D300 forbids"
    )


def test_the_dialled_request_actually_carries_the_header(monkeypatch: Any) -> None:
    """The header on the wire, not the constant in the module (D274's lesson).

    `FORWARDED_HEADERS` naming a header proves nothing about what `_dial` sends;
    this reads the built `urllib` request. The negative half is the control: a
    header the allowlist does NOT name must be absent, so a `_dial` that
    forwarded everything would fail here.
    """
    from app import mcp_upstream

    seen: dict[str, Any] = {}

    def record(request: Any, timeout: float = 0) -> Any:
        seen["headers"] = {name.lower() for name in request.headers}
        seen["value"] = request.get_header("X-request-id")
        return _Response(200, b'{"id": "x"}')

    monkeypatch.setattr(mcp_upstream.urllib.request, "urlopen", record)
    execute_write(BASE, "tok", _write_request(), max_affected_rows=1, request_id=REQUEST_ID)

    assert seen["value"] == REQUEST_ID
    assert seen["headers"] == {"authorization", "accept", "x-request-id", "content-type"}
    assert "prefer" not in seen["headers"], (
        "THE CONTROL: a header the allowlist does not name must be absent, or the "
        "assertion above is satisfied by a transport that forwards everything"
    )


def test_a_telemetry_record_carries_the_request_id_and_still_no_caller_value(
    caplog: Any,
) -> None:
    """`RECORD_FIELDS` grew by one, and the canary's list did not (ADR 0141).

    A request id is this process's own mint -- `uuid4`, never read off an
    inbound header -- so it cannot carry a token, a URL or a caller's value. The
    canary constraints are re-asserted here beside the new field rather than
    only in `test_mcp_budgets`, because the field was added in this run.
    """
    import logging

    from app.mcp_telemetry import RECORD_FIELDS, Timed

    assert "request_id" in RECORD_FIELDS
    assert not {"token", "url", "filters", "rows", "value"} & set(RECORD_FIELDS)

    with caplog.at_level(logging.INFO, logger="apg.mcp"):
        with Timed("create_note", request_id=REQUEST_ID) as timed:
            timed.principal(agent_id="agent-1", owner_id=OWNER)
            timed.served(row_count=1)

    emitted = "\n".join(record.getMessage() for record in caplog.records)
    assert REQUEST_ID in emitted
    assert "CANARY" not in emitted


def test_the_record_is_opened_before_the_work_and_closed_after(monkeypatch: Any) -> None:
    """Begin, work, complete — in that order, and the order is the point.

    A record opened after the work could not describe a call that never
    returned, and a record closed before it could not carry the outcome.
    """
    import asyncio

    _, registry, recorded = _registered(monkeypatch, "notes:write")
    order: list[str] = []

    def began(*_: Any, **kwargs: Any) -> str:
        order.append("begin")
        recorded.append({"phase": "begin", **kwargs})
        return "audit-1"

    def worked(*_: Any, **__: Any) -> dict[str, Any]:
        order.append("work")
        return {"tool": "create_note", "row_count": 1, "row": {}}

    def completed(*_: Any, **kwargs: Any) -> bool:
        order.append("complete")
        recorded.append({"phase": "complete", **kwargs})
        return True

    monkeypatch.setattr(mcp_tools, "audit_begin", began)
    monkeypatch.setattr(mcp_tools, "invoke_write", worked)
    monkeypatch.setattr(mcp_tools, "audit_complete", completed)

    asyncio.run(registry.tools["create_note"](p_title="t", p_content="c"))

    assert order == ["begin", "work", "complete"]
    closing = next(entry for entry in recorded if entry["phase"] == "complete")
    assert closing["outcome"] == "served"
    assert closing["row_count"] == 1
    assert closing["audit_id"] == "audit-1"
    assert isinstance(closing["elapsed_ms"], int)


def test_the_records_parameters_are_redacted_per_the_lock(monkeypatch: Any) -> None:
    """**D479's orphan, consumed at last.** `audit.redact` was required by the
    schema, carried by every capability, and read by nothing.

    `create_note` declares `["p_content"]`; `update_task_status` declares
    nothing. **Both arms, because either alone is satisfied by the wrong
    implementation** — a redactor that blanked everything would pass the first,
    and one that blanked nothing would pass the second.

    The KEY survives and only the value is replaced: a record showing
    `p_content: "[redacted]"` says the caller supplied one, and a record with no
    `p_content` says nothing at all.
    """
    import asyncio

    from app.mcp_audit import REDACTED

    _, registry, recorded = _registered(monkeypatch, "notes:write", "tasks:write")
    monkeypatch.setattr(mcp_tools, "invoke_write", lambda *_, **__: {"row_count": 1, "row": {}})

    asyncio.run(registry.tools["create_note"](p_title="the title", p_content="SECRET BODY"))
    written = next(entry for entry in recorded if entry["phase"] == "begin")["parameters"]

    assert written["p_title"] == "the title", "an unredacted parameter is recorded verbatim"
    assert written["p_content"] == REDACTED
    assert "p_content" in written, "the key stays; only the value goes"

    recorded.clear()
    asyncio.run(
        registry.tools["update_task_status"](
            p_task_id="task-1", p_expected_status="todo", p_new_status="done"
        )
    )
    written = next(entry for entry in recorded if entry["phase"] == "begin")["parameters"]

    assert written == {
        "p_task_id": "task-1",
        "p_expected_status": "todo",
        "p_new_status": "done",
    }, "THE CONTROL: this tool redacts nothing, so a blanket redactor fails here"


def test_a_denied_call_is_recorded_as_refused(monkeypatch: Any) -> None:
    """**AGT-AUDIT-001's denied arm**, and why begin comes before the scope check.

    Checking scopes first would be cheaper and would lose exactly this record.
    The call is refused, and the refusal is durable.
    """
    import asyncio

    from fastmcp.exceptions import ToolError

    _, registry, recorded = _registered(monkeypatch, "meta:read", "notes:read")
    monkeypatch.setattr(
        mcp_tools, "execute_write", lambda *_, **__: pytest.fail("a denied write was dialled")
    )

    with pytest.raises(ToolError, match="notes:write"):
        asyncio.run(registry.tools["create_note"](p_title="t", p_content="c"))

    assert [entry["phase"] for entry in recorded] == ["begin", "complete"], (
        "a denied call must open AND close a record; a call refused before begin leaves "
        "no trace of having been attempted"
    )
    assert recorded[-1]["outcome"] == "refused"


def test_a_write_whose_record_cannot_be_opened_does_not_happen(monkeypatch: Any) -> None:
    """**AGT-AUDITFAIL-001**, and half of ADR 0141.

    `audit=False`, so the real audit path runs against a `base_url` nothing
    answers -- the failure is real rather than asserted. The write executor is
    replaced by one that fails the test if it is reached, so "did not happen"
    is proved by the absence of the dial rather than by the shape of the error.
    """
    import asyncio

    _, registry, _recorded = _registered(monkeypatch, "notes:write", audit=False)
    monkeypatch.setattr(
        mcp_tools, "audit_begin", _raising(AuditRefusal("the audit table is unreachable"))
    )
    monkeypatch.setattr(
        mcp_tools,
        "execute_write",
        lambda *_, **__: pytest.fail("an unauditable write reached the database"),
    )

    with pytest.raises(ToolRefusal):
        asyncio.run(registry.tools["create_note"](p_title="t", p_content="c"))


def test_a_read_whose_record_cannot_be_opened_still_answers(monkeypatch: Any) -> None:
    """**The other half of ADR 0141, and the asymmetry is the decision** (D483).

    Failing a read closed would couple every agent read's availability to the
    audit table. This is the CONTROL for the test above in the strongest sense:
    the same failure, the same rig, the opposite outcome — so neither result can
    be explained by the audit stub simply not working.
    """
    import asyncio

    _, registry, _recorded = _registered(monkeypatch, "meta:read", "notes:read", audit=False)
    monkeypatch.setattr(
        mcp_tools, "audit_begin", _raising(AuditRefusal("the audit table is unreachable"))
    )
    monkeypatch.setattr(
        mcp_tools,
        "query_resource",
        lambda *_, **__: {"resource": "notes", "row_count": 0, "rows": []},
    )

    answered = asyncio.run(registry.tools["query_resource"](resource="notes"))

    assert answered["row_count"] == 0, "a read must survive an audit table it cannot reach"


def test_a_failing_complete_never_changes_the_outcome(monkeypatch: Any) -> None:
    """The work has already happened (ADR 0141).

    A committed write cannot be un-committed by a bookkeeping failure, and
    reporting a failure that did not occur would make the record less true. Both
    failure modes are exercised: the call raising, and it returning `false` --
    which rig6 measured as a 200, not an error.
    """
    import asyncio

    _, registry, _recorded = _registered(monkeypatch, "notes:write")
    monkeypatch.setattr(
        mcp_tools,
        "invoke_write",
        lambda *_, **__: {"tool": "create_note", "row_count": 1, "row": {}},
    )

    monkeypatch.setattr(
        mcp_tools, "audit_complete", _raising(AuditRefusal("could not close the record"))
    )
    assert asyncio.run(registry.tools["create_note"](p_title="t", p_content="c"))["row_count"] == 1

    monkeypatch.setattr(mcp_tools, "audit_complete", lambda *_, **__: False)
    assert asyncio.run(registry.tools["create_note"](p_title="t", p_content="c"))["row_count"] == 1


def test_a_metadata_tool_opens_no_record_at_all(monkeypatch: Any) -> None:
    """**ADR 0141's third clause**, and it is a decision rather than an omission.

    Auditing `list_resources` would turn a dictionary lookup into two network
    round trips and make discovery depend on the audit table -- undoing the
    reason ADR 0129 gives them no concurrency slot. The read arm beside it is
    the control: the same rig, an audited kind, and a record does appear.
    """
    import asyncio

    _, registry, recorded = _registered(monkeypatch, "meta:read", "notes:read")
    monkeypatch.setattr(mcp_tools, "list_resources", lambda *_, **__: {"resources": []})
    monkeypatch.setattr(
        mcp_tools,
        "query_resource",
        lambda *_, **__: {"resource": "notes", "row_count": 0, "rows": []},
    )

    asyncio.run(registry.tools["list_resources"]())
    assert recorded == [], f"a metadata tool opened a record: {recorded}"

    asyncio.run(registry.tools["query_resource"](resource="notes"))
    assert [entry["phase"] for entry in recorded] == ["begin", "complete"], (
        "THE CONTROL: a read must be audited, or the assertion above is satisfied by an "
        "audit path that never runs for anything"
    )


def test_the_audit_calls_go_to_the_two_named_rpcs_and_nowhere_else(monkeypatch: Any) -> None:
    """`mcp_audit` names its paths as constants and takes none from a caller.

    The same property `mcp_upstream.AGENT_CONTEXT_PATH` has and for the same
    reason: these are not tools, no capability names them, and there is no code
    path here that could be steered to another function.
    """
    from app import mcp_audit

    seen: list[str] = []

    def dial(base_url: str, token: str, request: Any, *, request_id: str) -> tuple[int, bytes]:
        seen.append(request.target)
        return 200, b'"audit-1"' if request.path == mcp_audit.AUDIT_BEGIN_PATH else b"true"

    monkeypatch.setattr(mcp_audit, "_dial", dial)

    mcp_audit.begin(
        BASE,
        "tok",
        tool="create_note",
        request_id=REQUEST_ID,
        parameters={},
        capability_version=None,
        contract_hash=None,
    )
    mcp_audit.complete(
        BASE,
        "tok",
        audit_id="audit-1",
        outcome="served",
        request_id=REQUEST_ID,
        elapsed_ms=3,
        row_count=1,
        denial_reason=None,
    )

    assert seen == ["/rpc/agent_audit_begin", "/rpc/agent_audit_complete"]

    signature = set(mcp_audit.begin.__code__.co_varnames[: mcp_audit.begin.__code__.co_argcount])
    assert not signature & {"path", "url", "method", "operation_id"}


def test_the_audit_responses_are_parsed_as_the_measured_shapes(monkeypatch: Any) -> None:
    """rig6: a non-SETOF SCALAR renders as a bare JSON scalar, not an object.

    `RETURNS uuid` is a JSON **string** and `RETURNS boolean` is a bare
    `true`/`false`. **Run 4's rig measured composites and is not evidence for
    this** — three return shapes, three renderings — so the parser is asserted
    against the shape that was actually measured, and against the two it was
    not.
    """
    from app import mcp_audit

    def answering(status: int, body: bytes) -> Any:
        def dial(*_: Any, **__: Any) -> tuple[int, bytes]:
            return status, body

        return dial

    monkeypatch.setattr(
        mcp_audit, "_dial", answering(200, b'"c8c13a67-cee5-43e2-b1e7-07b17460215f"')
    )
    assert (
        mcp_audit.begin(
            BASE,
            "t",
            tool="create_note",
            request_id=REQUEST_ID,
            parameters={},
            capability_version=None,
            contract_hash=None,
        )
        == "c8c13a67-cee5-43e2-b1e7-07b17460215f"
    )

    # The two shapes it is NOT. An object is what a composite return renders as
    # and an array is what a SETOF does; both would be a function whose shape
    # changed underneath this code.
    for wrong in (b'{"id": "x"}', b'["c8c13a67-cee5-43e2-b1e7-07b17460215f"]'):
        monkeypatch.setattr(mcp_audit, "_dial", answering(200, wrong))
        with pytest.raises(mcp_audit.AuditRefusal, match="not a record id"):
            mcp_audit.begin(
                BASE,
                "t",
                tool="create_note",
                request_id=REQUEST_ID,
                parameters={},
                capability_version=None,
                contract_hash=None,
            )

    for body, expected in ((b"true", True), (b"false", False)):
        monkeypatch.setattr(mcp_audit, "_dial", answering(200, body))
        assert (
            mcp_audit.complete(
                BASE,
                "t",
                audit_id="a",
                outcome="served",
                request_id=REQUEST_ID,
                elapsed_ms=1,
                row_count=1,
                denial_reason=None,
            )
            is expected
        )


def test_an_audit_refusal_names_no_upstream_code(monkeypatch: Any) -> None:
    """Nothing an audit call says is the caller's to act on (ADR 0141).

    Unlike a write refusal (ADR 0139), there is no vocabulary to translate: every
    outcome here is "the record was kept" or "it was not". The 422 body carries
    `PT422` and the message names the enum's own values; neither may reach a
    caller, and neither does — the exception's text is this module's.
    """
    from app import mcp_audit

    def dial(*_: Any, **__: Any) -> tuple[int, bytes]:
        return 422, b'{"code":"PT422","message":"AP422: an outcome is served, refused or failed"}'

    monkeypatch.setattr(mcp_audit, "_dial", dial)

    with pytest.raises(mcp_audit.AuditRefusal) as caught:
        mcp_audit.complete(
            BASE,
            "t",
            audit_id="a",
            outcome="committed",
            request_id=REQUEST_ID,
            elapsed_ms=1,
            row_count=1,
            denial_reason=None,
        )
    assert "PT422" not in str(caught.value)
    assert "AP422" not in str(caught.value)


def test_redaction_does_not_invent_a_parameter_the_caller_never_sent() -> None:
    """A record must not imply an argument was passed when it was not."""
    from app.mcp_audit import REDACTED, redact

    assert redact({"p_title": "t"}, ("p_content",)) == {"p_title": "t"}
    assert redact({"p_title": "t", "p_content": "body"}, ("p_content",)) == {
        "p_title": "t",
        "p_content": REDACTED,
    }
    assert redact({}, ("p_content",)) == {}


# ---------------------------------------------------------------------------
# Lock schema version 2: risk and the backing capabilities (ADR 0177)
# ---------------------------------------------------------------------------


def _v2_document(*names: str) -> dict[str, Any]:
    """The same lock at schema version 2, every tool classified.

    Built from `_lock_document` rather than beside it, so the two cannot drift:
    a v2 fixture that was independently valid would stop being the v1 fixture
    plus the classification, which is the only difference under test.
    """
    document = _lock_document(*names)
    document["schema_version"] = 2
    for tool in document["tools"]:
        risk = "moderate" if tool["name"] in WRITE_TOOLS else "low"
        tool["risk"] = risk
        tool["capabilities"] = [
            {
                "name": tool["name"],
                "version": "1.0.0",
                "lifecycle": "active",
                "risk": risk,
            }
        ]
    return document


def _load(tmp_path: Path, document: dict[str, Any]) -> CapabilityLock:
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return load_lock(path)


def test_a_version_two_lock_loads_and_carries_the_classification(tmp_path: Path) -> None:
    """**The control** for the refusals below, and the ordering D882 is about.

    The compiler emits schema_version 2 now. If this runtime did not accept it,
    a deploy would recreate the MCP service against a lock it refuses and the
    container would not come up -- at step 6b, in the middle of a convergence.
    """
    lock = _load(tmp_path, _v2_document(*EXPECTED_TOOL_NAMES))

    for tool in lock.tools:
        assert tool.risk in ("low", "moderate", "high"), tool.name
        assert tool.capabilities, f"{tool.name} names no backing capability"
        assert all(reference.version == "1.0.0" for reference in tool.capabilities)

    assert {tool.risk for tool in lock.tools} == {"low", "moderate"}, (
        "the fixture classifies every tool the same way, so this proves nothing"
    )


def test_a_version_one_lock_still_loads_with_the_fields_absent(tmp_path: Path) -> None:
    """`capabilities.yaml` lives only on the host, so v1 has to keep working.

    **Absent, not defaulted.** A deployment that does not classify its
    capabilities must be distinguishable from one that classified them all as
    harmless (D600) -- and in Run 3 that difference becomes an audit row rather
    than a variable.
    """
    lock = _load(tmp_path, _lock_document(*EXPECTED_TOOL_NAMES))

    assert {tool.risk for tool in lock.tools} == {None}
    assert {tool.capabilities for tool in lock.tools} == {()}


@pytest.mark.parametrize("field", ["risk", "capabilities"])
def test_a_version_one_lock_carrying_the_new_fields_is_refused(tmp_path: Path, field: str) -> None:
    """The direction that keeps the version number from being decorative.

    A v1 lock carrying `risk` came from a compiler that disagrees with its own
    declared version. Reading it anyway would mean the number describes nothing,
    which is how a format version stops being a contract and becomes a comment.
    """
    document = _lock_document(*EXPECTED_TOOL_NAMES)
    document["tools"][0][field] = "low" if field == "risk" else []

    with pytest.raises(LockError, match="schema_version 1"):
        _load(tmp_path, document)


def test_a_lock_backed_by_a_retired_capability_is_refused(tmp_path: Path) -> None:
    """The compiler refuses to emit one; the lock is validated as if it had not.

    A lock is an input, not a teammate -- the same rule `_write` states for the
    write shape. The compiler's refusal is the enforcement, and this is the
    check that the enforcement was not simply believed.
    """
    document = _v2_document(*EXPECTED_TOOL_NAMES)
    document["tools"][0]["capabilities"][0]["lifecycle"] = "retired"

    with pytest.raises(LockError, match="retired"):
        _load(tmp_path, document)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ({"risk": "critical"}, "not a classification"),
        ({"capabilities": []}, "names no backing capability"),
    ],
)
def test_a_version_two_lock_is_parsed_as_strictly_as_the_rest_of_it(
    tmp_path: Path, mutation: dict[str, Any], expected: str
) -> None:
    """A lock parsed leniently is a surface nobody bounded."""
    document = _v2_document(*EXPECTED_TOOL_NAMES)
    document["tools"][0].update(mutation)

    with pytest.raises(LockError, match=expected):
        _load(tmp_path, document)
