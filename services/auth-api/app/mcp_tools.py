"""The six tools, and there are exactly six.

`docs/capability-plan.md` has named them since Session 1: `list_resources`,
`describe_resource`, `query_resource`, `run_report`, and — since Session 9 —
`create_note` and `update_task_status`. This module registers them and nothing
else. A seventh is refused by `mcp_lock` before registration is reached, and the
registered names are asserted against the lock's roster.

**Two of them reach nothing.** `list_resources` and `describe_resource` answer
from the loaded lock: no OpenAPI request, no database, no upstream call at all
(ADR 0127). Discovery therefore describes what a human approved, which is a
different question from what a service happens to be exposing.

**Two of them read PostgREST, as the caller.** `query_resource` and `run_report`
build their request from the lock with `mcp_query` and send it with the caller's
own token (ADR 0125). They never resolve the caller's context themselves: it is
resolved once per HTTP request by `AgentContextMiddleware` and read with
`current_agent_context()`, so there is one resolution per request and one place
that decides what a refusal is.

**Two of them write it, one-to-one with a reviewed operation.** A write selects
among no resources (D486): it names one operation from the lock, supplies a
value for every argument the lock declares and no others, and is bounded to
`max_affected_rows` — checked against the response rather than trusted (D487).
The argument NAMES a caller uses are the lock's own, which are the reviewed
function's parameter names, because translating them here would be a second
naming authority for a list the contract already froze.

**Scope is checked here as well as by the database**, and the two are different
questions. The lock says which scopes a capability requires; the database says
which rows this owner may see. A caller holding `notes:read` and asking for
tasks is refused by the first without troubling the second — and a caller
holding both still sees only its owner's rows, because RLS does not consult a
scope.

**And the check here is the boundary, not the roster.**
`ToolVisibilityMiddleware` hides a name a caller could not use, but a hidden
tool is still callable by name — measured (ADR 0140, rig5 M2). So
`_resource_for` and `_write_for` refuse at call time, and discovery filtering is
disclosure control on top of that, never instead of it.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from app.mcp_authorization import current_agent_context
from app.mcp_budgets import DEFAULT_MAX_CONCURRENT_READS, ReadSlots
from app.mcp_errors import (
    BUDGET_EXCEEDED,
    INPUT_NOT_PERMITTED,
    RESOURCE_UNKNOWN,
    SCOPE_NOT_HELD,
    STRUCTURAL_REFUSAL,
    AgentVisible,
    as_tool_error,
)
from app.mcp_lock import CapabilityLock, LockError, Resource, WriteSpec
from app.mcp_query import Filter, QueryRefusal, build_request, build_write_request
from app.mcp_telemetry import Timed
from app.mcp_upstream import UpstreamRefusal, execute, execute_write

#: The names `register()` registers, written out rather than imported from
#: `mcp_lock`.
#:
#: **Two lists that must agree, not one list read twice** (D486). A test asserts
#: `TOOL_NAMES == EXPECTED_TOOL_NAMES`; aliasing the constant would make that
#: test compare a value with itself, which is the shape §6 names -- a test
#: between two constants is not testing the thing between them. Run 4 widened the
#: lock's roster to six and this list stayed at four for one run, with the gap
#: asserted exactly; Run 5 registers the writes and restores the equality.
TOOL_NAMES = (
    "create_note",
    "describe_resource",
    "list_resources",
    "query_resource",
    "run_report",
    "update_task_status",
)

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
    """A STRUCTURAL refusal: the caller is told nothing (ADR 0097, ADR 0130).

    Raised as a plain exception on purpose. `mask_error_details=True` replaces
    its message with the framework's opaque string, which is the right amount
    for an upstream refusal whose three measured causes -- a bad signature, a
    stale identity, a missing privilege -- are indistinguishable by status
    (D433). Relaying one would be a guess dressed as a diagnosis.

    **A refusal the caller may ACT on is `AgentVisible` instead**, and it reaches
    them because `ToolError` bypasses the mask. Run 6 raised everything through
    this type, so its carefully-worded input messages were replaced before they
    left the process -- written, reviewed, tested, and invisible (D448).
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
        # `list_resources`. Safe to relay, and useful to.
        raise AgentVisible(RESOURCE_UNKNOWN, str(error)) from error

    held = _scopes()
    missing = [scope for scope in resource.required_scopes if scope not in held]
    if missing:
        # The scopes it NEEDS, not the ones it holds. The first is a fact about
        # this surface the caller could read from `describe_resource`; the second
        # would be this process telling a caller about its own token, which it
        # already has and which a log should not repeat back.
        raise AgentVisible(
            SCOPE_NOT_HELD, f"this resource requires {sorted(resource.required_scopes)}"
        )
    return resource


def _write_for(lock: CapabilityLock, tool: str) -> WriteSpec:
    """One write tool's operation, with the caller's scopes checked first.

    **`_resource_for`'s twin, and the boundary a hidden name does not replace.**
    `ToolVisibilityMiddleware` keeps `create_note` out of a read-only agent's
    roster, and a caller that knows the name can still send it -- measured
    (ADR 0140, rig5 M2). This is the check that refuses, and `AGT-WRITE-001`
    asserts both halves separately for that reason.

    A write names no resource (D486), so there is no second name to resolve: the
    tool IS the operation, and the only question is whether this caller holds
    what the lock says the operation requires.
    """
    try:
        declared = lock.tool(tool)
    except LockError as error:  # pragma: no cover -- load_lock refuses this first
        raise ToolRefusal(STRUCTURAL_REFUSAL) from error

    spec = declared.write
    if spec is None:  # pragma: no cover -- load_lock requires the write shape
        # Structural rather than caller-visible: a registered write tool whose
        # lock entry carries no write shape is a deployment fault, and nothing
        # the caller did produced it.
        raise ToolRefusal(STRUCTURAL_REFUSAL)

    held = _scopes()
    if [scope for scope in spec.required_scopes if scope not in held]:
        raise AgentVisible(SCOPE_NOT_HELD, f"this tool requires {sorted(spec.required_scopes)}")
    return spec


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
        # An input the lock does not permit. The caller can fix this, and
        # `mcp_query` already writes the message to name the INPUT and never the
        # schema -- so it is exactly what may be relayed.
        raise AgentVisible(INPUT_NOT_PERMITTED, str(error)) from error

    try:
        rows = execute(base_url, token, request)
    except UpstreamRefusal as error:
        raise ToolRefusal(STRUCTURAL_REFUSAL) from error

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
        # Structural: the upstream returned more than the lock permits, which is
        # a fault in the deployment rather than in the request. Nothing the
        # caller did produced it and nothing it can do fixes it.
        raise ToolRefusal(STRUCTURAL_REFUSAL)
    return _within_byte_budget(result)


def _within_byte_budget(result: dict[str, Any]) -> dict[str, Any]:
    """The byte ceiling alone, on every result this process returns.

    **Split out because the write path is a caller of it** (§6 question 5: when
    a decision is implemented, which of its callers got it?). `MAX_SERIALIZED_BYTES`
    is ADR 0129's response bound, and it was reachable only through the row
    check -- so a write result, which has no row ceiling to check, would have
    been the one path returning an unbounded response. `content` is an unbounded
    `text` column and `create_note` echoes the created row back, so the ceiling
    is not theoretical there.
    """
    serialized = len(json.dumps(result, separators=(",", ":")).encode("utf-8"))
    if serialized > MAX_SERIALIZED_BYTES:
        # Caller-visible, and the advice is the point: this is the one budget a
        # caller can stay inside by asking differently.
        raise AgentVisible(
            BUDGET_EXCEEDED,
            f"the result is {serialized} bytes, above the {MAX_SERIALIZED_BYTES} ceiling; "
            "ask for fewer columns or fewer rows",
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
        raise ToolRefusal(STRUCTURAL_REFUSAL)
    found = _resource_for(lock, "run_report", tool.resources[0].name)

    try:
        request = build_request(found, timeout_ms=tool.timeout_ms)
    except QueryRefusal as error:
        raise AgentVisible(INPUT_NOT_PERMITTED, str(error)) from error

    try:
        rows = execute(base_url, token, request)
    except UpstreamRefusal as error:
        raise ToolRefusal(STRUCTURAL_REFUSAL) from error

    if len(rows) != 1:
        # The report is one row by construction. Anything else is a surface that
        # has changed underneath the lock, and reporting the first row would be
        # reporting a number nobody bounded. Structural: not the caller's doing.
        raise ToolRefusal(STRUCTURAL_REFUSAL)
    return rows[0]


def invoke_write(
    lock: CapabilityLock,
    *,
    base_url: str,
    token: str,
    tool: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """One reviewed write, as the caller, and the row it committed.

    **The body of both write tools**, parameterised by name rather than written
    twice: the two differ only in which operation the lock names and which
    arguments it declares, and a second copy would be a second place to review.
    The name is `register()`'s, from the roster -- never a caller's, which is
    what keeps this from being the generic dispatcher ADR 0127 forbids.

    The order is the point. Scopes are checked before an argument is looked at,
    arguments are checked against the lock before a request is built, and the
    request is built before anything is dialled -- so a refusable call costs no
    upstream request and every refusal names the input rather than the schema.

    **`execute_write`'s `AgentVisible` passes straight through.** A translated
    `PT` refusal (ADR 0139) is the caller's to read and act on -- a
    compare-and-swap conflict is a retry instruction -- so it is deliberately
    not caught here beside the structural one.

    The result is the one row the operation returned, byte-bounded like a read's
    (ADR 0129). `row_count` is present because `bounded()` reads it for the
    telemetry record, and it is the count of rows this write actually affected.
    """
    spec = _write_for(lock, tool)

    try:
        request = build_write_request(
            spec, timeout_ms=lock.tool(tool).timeout_ms, arguments=arguments
        )
    except QueryRefusal as error:
        raise AgentVisible(INPUT_NOT_PERMITTED, str(error)) from error

    try:
        rows = execute_write(base_url, token, request, max_affected_rows=spec.max_affected_rows)
    except UpstreamRefusal as error:
        raise ToolRefusal(STRUCTURAL_REFUSAL) from error

    if len(rows) != 1:
        # Both reviewed writes are `RETURNS <composite>` -- exactly one row
        # (D487). Zero is a shape that changed underneath the lock, and the
        # write has already committed, so this is loud rather than quiet.
        raise ToolRefusal(STRUCTURAL_REFUSAL)
    return _within_byte_budget({"tool": tool, "row_count": len(rows), "row": rows[0]})


def _filter(entry: Any) -> Filter:
    """One caller filter object, shaped before it is checked.

    `value` is absent for `is_null` and required for everything else, and both
    are the caller's to get wrong -- so the shape check is here and the
    permission check is `build_filter`'s, against the lock.
    """
    if not isinstance(entry, dict):
        raise AgentVisible(
            INPUT_NOT_PERMITTED, "a filter is an object with column, operator and value"
        )
    for required in ("column", "operator"):
        if not isinstance(entry.get(required), str) or not entry[required]:
            raise AgentVisible(INPUT_NOT_PERMITTED, f"a filter needs a non-empty {required}")
    unknown = set(entry) - {"column", "operator", "value"}
    if unknown:
        raise AgentVisible(INPUT_NOT_PERMITTED, f"a filter has no {sorted(unknown)} member")
    return Filter(column=entry["column"], operator=entry["operator"], value=entry.get("value"))


def register(
    server: Any, lock: CapabilityLock, *, base_url: str, slots: ReadSlots | None = None
) -> tuple[str, ...]:
    """Register exactly the six tools and return their names.

    The names are returned rather than assumed so a test can compare them with
    the lock's, which is the check that a seventh tool -- or a renamed one --
    fails offline rather than on a cluster.

    Each closure reads the caller's token from the context resolved for this
    request. Nothing here holds a token between requests: `current_agent_context`
    is backed by a `ContextVar` that is reset in a `finally` (ADR 0125).
    """
    from app.mcp_authorization import current_token

    read_slots = slots if slots is not None else ReadSlots(DEFAULT_MAX_CONCURRENT_READS)

    async def bounded(
        tool: str, resource: str | None, work: Any, *, upstream: bool
    ) -> dict[str, Any]:
        """One boundary for every tool call: measure, bound, translate.

        **Three jobs in one place**, and the alternative is three decorators
        every future tool author has to remember -- which is D333's shape.

        *Measure.* One telemetry record per call, carrying ids and counts and no
        caller values (ADR 0130).

        *Bound.* The concurrency semaphore is held only around work that reaches
        upstream; the two metadata tools answer from the lock and take no slot,
        because a bound that queued them would make discovery contend with reads
        for no reason (ADR 0129).

        *Translate.* `AgentVisible` becomes a `ToolError`, which is the one type
        the framework lets past `mask_error_details`. Everything else stays a
        plain exception and is masked -- so a refusal is silent unless somebody
        chose otherwise.

        **`upstream` is a separate argument, and it used to be `resource is
        None`** (D495). One value was carrying two ideas -- *"names no resource
        in the telemetry record"* and *"does not reach upstream, so takes no
        slot"* -- which agreed for as long as every upstream tool had a resource.
        A write has neither: it is one-to-one with its operation, so there is no
        resource to name, and it reaches PostgREST, so it must take a slot.
        Inferring the second from the first would have registered both writes as
        unbounded work on the event loop, which is D451 restored by accident and
        D463's shape exactly -- one name, two meanings, correct until the day
        they part.
        """
        with Timed(tool, resource=resource) as timed:
            try:
                context = current_agent_context()
                timed.principal(agent_id=context.agent_id, owner_id=context.owner_id)
            except Exception:
                timed.principal(agent_id=None, owner_id=None)

            try:
                if not upstream:
                    # Metadata: the lock is in memory, so this is a dict lookup
                    # and belongs on the loop. No slot, no thread.
                    result = work()
                else:
                    # **A thread, and it is not an optimisation** (D451). The
                    # upstream read is blocking urllib, and calling it on the
                    # event loop serialises the WHOLE process -- every other
                    # request, and the health routes with them. Measured: with
                    # the call on the loop, six overlapping reads peaked at ONE
                    # concurrent, so the semaphore never saw contention and the
                    # bound it appears to apply was unreachable.
                    async with read_slots:
                        result = await asyncio.to_thread(work)
            except AgentVisible as visible:
                timed.refused()
                raise as_tool_error(visible) from visible
            except ToolRefusal:
                timed.refused()
                raise

            timed.served(result.get("row_count") if isinstance(result, dict) else None)
            return result

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
    async def _list_resources() -> dict[str, Any]:
        """The resources this deployment's agent surface can query, and the
        scope each one needs. Read from the deployed lock; reaches no database."""
        return await bounded("list_resources", None, lambda: list_resources(lock), upstream=False)

    @server.tool(name="describe_resource", timeout=seconds("describe_resource"))
    async def _describe_resource(tool: str, resource: str) -> dict[str, Any]:
        """One resource's frozen columns, permitted filters and permitted
        ordering, exactly as the lock froze them. Read from the deployed lock."""
        return await bounded(
            "describe_resource",
            None,
            lambda: describe_resource(lock, tool=tool, resource=resource),
            upstream=False,
        )

    @server.tool(name="query_resource", timeout=seconds("query_resource"))
    async def _query_resource(
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
        return await bounded(
            "query_resource",
            resource,
            lambda: query_resource(
                lock,
                base_url=base_url,
                token=current_token(),
                resource=resource,
                columns=columns,
                filters=filters,
                order_by=order_by,
                limit=limit,
            ),
            upstream=True,
        )

    @server.tool(name="run_report", timeout=seconds("run_report"))
    async def _run_report() -> dict[str, Any]:
        """The caller's own activity, counted under the caller's own RLS: notes
        and tasks totals, tasks by status, and the two most recent update times."""
        return await bounded(
            "run_report",
            "owner_activity_report",
            lambda: run_report(lock, base_url=base_url, token=current_token()),
            upstream=True,
        )

    # The two writes. **Their parameters are the lock's declared argument names**
    # -- `p_title`, `p_task_id` -- rather than friendlier ones mapped here: the
    # reviewed contract froze that list, `build_write_request` checks a caller's
    # names against it in both directions, and a translation layer would be a
    # second naming authority for one list. `docs/mcp-tool-catalog.md` publishes
    # the same names from the same contract, so a caller can read them.
    #
    # **Every argument is required**, including the one the SQL function
    # defaults. A caller supplies a value for every declared argument (Run 4),
    # because PostgREST resolves a function by the names supplied and a missing
    # one is a `404 PGRST202` -- the same status as the product's own "no such
    # row", with the opposite meaning (rig4, ADR 0139).

    @server.tool(name="create_note", timeout=seconds("create_note"))
    async def _create_note(p_title: str, p_content: str) -> dict[str, Any]:
        """Create one note owned by the caller's owner, and return the created
        row. Bounded to one row; the owner is the caller's, never an argument."""
        return await bounded(
            "create_note",
            None,
            lambda: invoke_write(
                lock,
                base_url=base_url,
                token=current_token(),
                tool="create_note",
                arguments={"p_title": p_title, "p_content": p_content},
            ),
            upstream=True,
        )

    @server.tool(name="update_task_status", timeout=seconds("update_task_status"))
    async def _update_task_status(
        p_task_id: str, p_expected_status: str, p_new_status: str
    ) -> dict[str, Any]:
        """Move one of the caller's owner's tasks from an expected status to a
        new one.

        A compare-and-swap: the write is refused when the expected status no
        longer holds, and that refusal reaches the caller as `write_conflict`
        because its next move is to re-read and retry (ADR 0139).
        """
        return await bounded(
            "update_task_status",
            None,
            lambda: invoke_write(
                lock,
                base_url=base_url,
                token=current_token(),
                tool="update_task_status",
                arguments={
                    "p_task_id": p_task_id,
                    "p_expected_status": p_expected_status,
                    "p_new_status": p_new_status,
                },
            ),
            upstream=True,
        )

    return TOOL_NAMES
