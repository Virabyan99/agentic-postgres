"""The four tools, the adapter, and AGT-SQL-001 (Session 8, Run 6).

**This module carries four of the five `AGT-*` requirements** that pointed at
placeholders in `tests/integration/test_future_mcp.py` until now (D414), and the
placeholders are gone with them.

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
from app.mcp_errors import ROW_NOT_FOUND, WRITE_CONFLICT, AgentVisible
from app.mcp_lock import (
    EXPECTED_TOOL_NAMES,
    METADATA_TOOLS,
    READ_TOOLS,
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


def _lock(*resources: Resource) -> CapabilityLock:
    """A lock carrying the four required tools, with `resources` under query."""
    from app.mcp_lock import Tool

    return CapabilityLock(
        contract_id="notes-tasks-agent-v1",
        project_key="probe-dev",
        upstream="https://probe.test/api/rest",
        canonical_sha256="a" * 64,
        tool_count=4,
        capability_count=5,
        tools=(
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


def test_a_metadata_tool_takes_no_concurrency_slot_and_a_read_does(monkeypatch: Any) -> None:
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
    """
    import asyncio

    from app.mcp_budgets import ReadSlots

    lock = _lock(NOTES)
    slots = ReadSlots(2)
    seen: dict[str, int] = {}

    _with_scopes(monkeypatch, "meta:read", "notes:read")
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

    registry = _Registry()
    assert mcp_tools.register(registry, lock, base_url=BASE, slots=slots) == mcp_tools.TOOL_NAMES
    assert set(registry.tools) == set(mcp_tools.TOOL_NAMES)

    asyncio.run(registry.tools["list_resources"]())
    assert seen["meta"] == slots.limit, "a metadata tool must not queue behind a read"

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
        query_resource(lock, base_url=BASE, token="t", resource="notes")  # noqa: S106


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
        query_resource(lock, base_url=BASE, token="t", resource="notes")  # noqa: S106


def test_a_result_inside_both_budgets_is_returned(monkeypatch: Any) -> None:
    """**The control.** Without it, a budget check that refused everything passes."""
    lock = _lock()
    _with_scopes(monkeypatch, "notes:read")
    monkeypatch.setattr(mcp_tools, "execute", lambda *_, **__: [{"title": "alpha"}])

    result = query_resource(lock, base_url=BASE, token="t", resource="notes")  # noqa: S106

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
        query_resource(lock, base_url=BASE, token="t", resource="notes")  # noqa: S106


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

    result = query_resource(lock, base_url=BASE, token="t", resource="notes")  # noqa: S106

    assert result["rows"] == upstream_rows
    assert result["row_count"] == len(upstream_rows)


def test_the_caller_token_is_what_the_adapter_forwards(monkeypatch: Any) -> None:
    """No service identity between the caller and the database (ADR 0125)."""
    lock = _lock()
    _with_scopes(monkeypatch, "notes:read")
    seen: dict[str, Any] = {}

    def capture(base_url: str, token: str, request: Any) -> list[dict[str, Any]]:
        seen["base_url"] = base_url
        seen["token"] = token
        return []

    monkeypatch.setattr(mcp_tools, "execute", capture)
    query_resource(lock, base_url=BASE, token="the.caller.token", resource="notes")  # noqa: S106

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


def test_the_roster_is_six_and_the_registered_gap_is_exactly_the_writes() -> None:
    """**Replaced the equality with an exact-gap statement, for one run (D486).**

    Until Run 4 this asserted `mcp_tools.TOOL_NAMES == EXPECTED_TOOL_NAMES`.
    Run 4 widened the lock's roster to six; Run 5 registers the two writes and
    restores the equality. In between, the honest assertion is that the gap
    between what `register()` serves and what the lock demands is EXACTLY the
    write tools — an exact set, never a subset (D300), so a seventh name or a
    renamed read still fails here.
    """
    assert EXPECTED_TOOL_NAMES == tuple(sorted((*METADATA_TOOLS, *READ_TOOLS, *WRITE_TOOLS)))
    assert len(EXPECTED_TOOL_NAMES) == 6
    assert set(EXPECTED_TOOL_NAMES) - set(mcp_tools.TOOL_NAMES) == set(WRITE_TOOLS)
    assert set(mcp_tools.TOOL_NAMES) == set(METADATA_TOOLS) | set(READ_TOOLS)


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
    reviewed against this code."""
    path = tmp_path / "lock.json"
    path.write_text(json.dumps({"schema_version": 2, "tools": []}), encoding="utf-8")

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

CREATE_WRITE = WriteSpec(
    operation=Operation(
        method="post", path="/rpc/create_note", operation_id="rpc.create_note.post"
    ),
    arguments=("p_title", "p_content"),
    required_scopes=("notes:write",),
    max_affected_rows=1,
    idempotent=False,
)


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

    rows = execute_write(BASE, "tok", _write_request(), max_affected_rows=1)
    assert rows == [{"id": "x", "title": "t"}]


def test_the_bound_is_checked_against_the_response_never_trusted(monkeypatch: Any) -> None:
    """D487: both writes return exactly one row, so this firing means the
    function's shape changed underneath the lock — a loud fault, not a clamp."""
    _upstream_answers(monkeypatch, 200, b'[{"id": "1"}, {"id": "2"}]')

    with pytest.raises(UpstreamRefusal, match="underneath the lock"):
        execute_write(BASE, "tok", _write_request(), max_affected_rows=1)


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
        execute_write(BASE, "tok", _write_request(), max_affected_rows=1)
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
        execute_write(BASE, "tok", _write_request(), max_affected_rows=1)
    assert caught.value.token == ROW_NOT_FOUND

    _upstream_answers(monkeypatch, 404, b'{"code":"PGRST202","message":"Could not find"}')
    with pytest.raises(UpstreamRefusal):
        execute_write(BASE, "tok", _write_request(), max_affected_rows=1)


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
        execute_write(BASE, "tok", _write_request(), max_affected_rows=1)
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
    execute_write(BASE, "tok", request, max_affected_rows=1)

    assert seen["data"] == request.body
    assert seen["content_type"] == "application/json"
