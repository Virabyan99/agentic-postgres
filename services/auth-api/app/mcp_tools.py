"""The four tools, and there are exactly four.

`docs/capability-plan.md` has named them since Session 1 and Run 3 compiled them:
`list_resources`, `describe_resource`, `query_resource`, `run_report`. This
module registers them and nothing else. A fifth is refused by `mcp_lock` before
registration is reached, and the registered names are asserted lexicographically
against the lock.

**Two of them reach nothing.** `list_resources` and `describe_resource` answer
from the loaded lock: no OpenAPI request, no database, no upstream call at all
(ADR 0127). Discovery therefore describes what a human approved, which is a
different question from what a service happens to be exposing.

**Two of them reach PostgREST, as the caller.** `query_resource` and
`run_report` build their request from the lock with `mcp_query` and send it with
the caller's own token (ADR 0125). They never resolve the caller's context
themselves: it is resolved once per HTTP request by
`AgentContextMiddleware` and read with `current_agent_context()`, so there is one
resolution per request and one place that decides what a refusal is.

**Scope is checked here as well as by the database**, and the two are different
questions. The lock says which scopes a capability requires; the database says
which rows this owner may see. A caller holding `notes:read` and asking for
tasks is refused by the first without troubling the second — and a caller
holding both still sees only its owner's rows, because RLS does not consult a
scope.
"""

from __future__ import annotations

import json
from typing import Any

from app.mcp_authorization import current_agent_context
from app.mcp_lock import CapabilityLock, LockError, Resource
from app.mcp_query import Filter, QueryRefusal, build_request
from app.mcp_upstream import UpstreamRefusal, execute

#: The names, in the order `mcp_lock.EXPECTED_TOOL_NAMES` asserts.
TOOL_NAMES = ("describe_resource", "list_resources", "query_resource", "run_report")

#: The ceiling on one tool result, serialized, in bytes.
#:
#: **Independent of the row budget, and that is the point** (AGT-BUDGET-001).
#: `max_rows` bounds how many rows come back; it bounds nothing about their size,
#: and `content` is an unbounded `text` column. Two hundred rows of one megabyte
#: each is within every row budget in the lock.
#:
#: Enforced **after** the upstream read and before anything is returned, because
#: this process cannot know a row's size until it has one. That makes it a
#: response bound rather than a request bound, and the distinction is honest: it
#: does not stop the database doing the work, it stops an unbounded result
#: reaching a caller. Bounding the work is Run 8's, along with elapsed time and
#: concurrency.
#:
#: 1 MiB, chosen not measured, and said so where it is defined.
MAX_SERIALIZED_BYTES = 1048576


class ToolRefusal(Exception):
    """The caller may not do this, and the message names the INPUT.

    Never the schema, never the upstream's status, never a row count it did not
    receive (ADR 0097). "you do not hold tasks:read" is a statement about the
    request; "column notes.secret does not exist" is a statement about the
    database.
    """


def _scopes() -> frozenset[str]:
    """The calling agent's scopes, from the context resolved for this request."""
    return frozenset(current_agent_context().scopes)


def _resource_for(lock: CapabilityLock, tool: str, name: str) -> Resource:
    try:
        resource = lock.resource(tool, name)
    except LockError as error:
        # The lock's own message names tools and resources, which are public
        # facts about this surface -- the caller could have got them from
        # `list_resources`. It is safe to relay and useful to.
        raise ToolRefusal(str(error)) from error

    held = _scopes()
    missing = [scope for scope in resource.required_scopes if scope not in held]
    if missing:
        raise ToolRefusal(f"this resource requires {sorted(resource.required_scopes)}")
    return resource


def list_resources(lock: CapabilityLock) -> dict[str, Any]:
    """The resources this caller can query, and the scope each one needs.

    Filtered by the caller's scopes, so the list does not advertise what it
    would refuse (D421). Reads the lock and nothing else.
    """
    held = _scopes()
    resources = [
        {
            "tool": tool.name,
            "resource": resource.name,
            "required_scopes": list(resource.required_scopes),
            "max_rows": resource.max_rows,
        }
        for tool in lock.tools
        for resource in tool.resources
        if set(resource.required_scopes) <= held
    ]
    return {
        "contract_id": lock.contract_id,
        "resources": sorted(resources, key=lambda entry: (entry["tool"], entry["resource"])),
    }


def describe_resource(lock: CapabilityLock, *, tool: str, resource: str) -> dict[str, Any]:
    """One resource's frozen columns, filters and orderings, from the lock.

    The orderings are returned **with their indices**, because that is how a
    caller selects one: `query_resource` takes an index into this list, not an
    order string. A caller cannot know which index to send without this, which
    is why describe is a tool rather than documentation.
    """
    found = _resource_for(lock, tool, resource)
    return {
        "tool": tool,
        "resource": found.name,
        "columns": list(found.columns),
        "filters": [
            {"column": column, "operators": list(operators)}
            for column, operators in sorted(found.filters.items())
        ],
        "order_by": [
            {"index": index, "column": column, "direction": direction}
            for index, (column, direction) in enumerate(found.order_by)
        ],
        "max_rows": found.max_rows,
        "required_scopes": list(found.required_scopes),
    }


def query_resource(
    lock: CapabilityLock,
    *,
    base_url: str,
    token: str,
    resource: str,
    columns: list[str] | None = None,
    filters: list[dict[str, Any]] | None = None,
    order_by: int | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """The caller's own rows, within the bounds the lock froze.

    Every input is checked against the lock before a request is built, so an
    invalid call costs no upstream request and the refusal describes the input
    rather than the schema.
    """
    found = _resource_for(lock, "query_resource", resource)
    parsed = [_filter(entry) for entry in filters or []]

    try:
        request = build_request(
            found,
            timeout_ms=lock.tool("query_resource").timeout_ms,
            columns=columns,
            filters=parsed,
            order_by=order_by,
            limit=limit,
        )
    except QueryRefusal as error:
        raise ToolRefusal(str(error)) from error

    try:
        rows = execute(base_url, token, request)
    except UpstreamRefusal as error:
        raise ToolRefusal("the read could not be completed") from error

    result = {"resource": found.name, "row_count": len(rows), "rows": rows}
    return _within_budget(result, found.max_rows)


def _within_budget(result: dict[str, Any], max_rows: int) -> dict[str, Any]:
    """Both budgets, checked on the way out (AGT-BUDGET-001).

    **Server-side regardless of client input**: the row ceiling is the lock's and
    a caller's `limit` can only lower it, and the byte ceiling is not expressible
    by a caller at all. A result that exceeds either is refused rather than
    truncated -- a truncated page that does not say so is a wrong answer, and a
    caller cannot tell it from a complete one.
    """
    rows = result["rows"]
    if len(rows) > max_rows:
        raise ToolRefusal(f"the upstream returned {len(rows)} rows above the {max_rows} ceiling")

    serialized = len(json.dumps(result, separators=(",", ":")).encode("utf-8"))
    if serialized > MAX_SERIALIZED_BYTES:
        raise ToolRefusal(
            f"the result is {serialized} bytes, above the {MAX_SERIALIZED_BYTES} ceiling; "
            "ask for fewer columns or fewer rows"
        )
    return result


def run_report(lock: CapabilityLock, *, base_url: str, token: str) -> dict[str, Any]:
    """The caller's own activity, counted under the caller's own RLS.

    One named RPC, chosen from the lock and not by the caller: this tool takes no
    resource argument at all, because there is exactly one thing it runs.

    **SECURITY INVOKER on the database side** (migration 0018), which is what
    makes AGT-READ-001 meaningful: the same RLS that constrains a row constrains
    a count of rows, so an agent and its owner get identical numbers because they
    run the identical query under the identical claim.
    """
    tool = lock.tool("run_report")
    if len(tool.resources) != 1:
        raise ToolRefusal("the lock does not name exactly one report")
    found = _resource_for(lock, "run_report", tool.resources[0].name)

    try:
        request = build_request(found, timeout_ms=tool.timeout_ms)
    except QueryRefusal as error:
        raise ToolRefusal(str(error)) from error

    try:
        rows = execute(base_url, token, request)
    except UpstreamRefusal as error:
        raise ToolRefusal("the report could not be completed") from error

    if len(rows) != 1:
        # The report is one row by construction. Anything else is a surface that
        # has changed underneath the lock, and reporting the first row would be
        # reporting a number nobody bounded.
        raise ToolRefusal("the report did not return exactly one row")
    return rows[0]


def _filter(entry: Any) -> Filter:
    """One caller filter object, shaped before it is checked.

    `value` is absent for `is_null` and required for everything else, and both
    are the caller's to get wrong -- so the shape check is here and the
    permission check is `build_filter`'s, against the lock.
    """
    if not isinstance(entry, dict):
        raise ToolRefusal("a filter is an object with column, operator and value")
    for required in ("column", "operator"):
        if not isinstance(entry.get(required), str) or not entry[required]:
            raise ToolRefusal(f"a filter needs a non-empty {required}")
    unknown = set(entry) - {"column", "operator", "value"}
    if unknown:
        raise ToolRefusal(f"a filter has no {sorted(unknown)} member")
    return Filter(column=entry["column"], operator=entry["operator"], value=entry.get("value"))


def register(server: Any, lock: CapabilityLock, *, base_url: str) -> tuple[str, ...]:
    """Register exactly the four tools and return their names.

    The names are returned rather than assumed so a test can compare them with
    the lock's, which is the check that a fifth tool -- or a renamed one --
    fails offline rather than on a cluster.

    Each closure reads the caller's token from the context resolved for this
    request. Nothing here holds a token between requests: `current_agent_context`
    is backed by a `ContextVar` that is reset in a `finally` (ADR 0125).
    """
    from app.mcp_authorization import current_token

    def seconds(name: str) -> float:
        """The lock's per-tool timeout, in the unit the framework takes.

        Measured: `@server.tool` accepts `timeout` in SECONDS and the lock
        carries `timeout_ms`. Converting at the boundary rather than storing two
        units is what stops a 5000-second timeout from looking plausible.
        """
        return max(lock.tool(name).timeout_ms, 1) / 1000

    # `name=` on every one. Without it the framework names a tool after its
    # Python function, and these functions cannot be called `list_resources`
    # because the module-level pure functions already are -- so the registered
    # names would silently become `list_resources_tool` and the contract would
    # be wrong in the one place a client reads it.
    @server.tool(name="list_resources", timeout=seconds("list_resources"))
    def _list_resources() -> dict[str, Any]:
        """The resources this deployment's agent surface can query, and the
        scope each one needs. Read from the deployed lock; reaches no database."""
        return list_resources(lock)

    @server.tool(name="describe_resource", timeout=seconds("describe_resource"))
    def _describe_resource(tool: str, resource: str) -> dict[str, Any]:
        """One resource's frozen columns, permitted filters and permitted
        ordering, exactly as the lock froze them. Read from the deployed lock."""
        return describe_resource(lock, tool=tool, resource=resource)

    @server.tool(name="query_resource", timeout=seconds("query_resource"))
    def _query_resource(
        resource: str,
        columns: list[str] | None = None,
        filters: list[dict[str, Any]] | None = None,
        order_by: int | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """The caller's own rows, filtered and ordered within frozen bounds.

        `order_by` is an INDEX into the orderings `describe_resource` returns,
        not an order string: the permitted orderings are frozen, and choosing
        one by index is not the same feature as writing one.
        """
        return query_resource(
            lock,
            base_url=base_url,
            token=current_token(),
            resource=resource,
            columns=columns,
            filters=filters,
            order_by=order_by,
            limit=limit,
        )

    @server.tool(name="run_report", timeout=seconds("run_report"))
    def _run_report() -> dict[str, Any]:
        """The caller's own activity, counted under the caller's own RLS: notes
        and tasks totals, tasks by status, and the two most recent update times."""
        return run_report(lock, base_url=base_url, token=current_token())

    return TOOL_NAMES
