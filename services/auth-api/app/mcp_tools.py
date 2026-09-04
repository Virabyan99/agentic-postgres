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
import contextlib
import json
import re
from typing import Any, Final

from app import mcp_tracing
from app.mcp_audit import AuditRefusal
from app.mcp_audit import begin as audit_begin
from app.mcp_audit import complete as audit_complete
from app.mcp_audit import redact as audit_redact
from app.mcp_authorization import current_agent_context
from app.mcp_budgets import DEFAULT_MAX_CONCURRENT_READS, ReadSlots
from app.mcp_errors import (
    APPROVAL_REQUIRED,
    APPROVAL_REQUIRED_REASON,
    AUDIT_UNAVAILABLE,
    BUDGET_EXCEEDED,
    BUDGET_EXCEEDED_REASON,
    CONTRACT_DRIFT,
    INPUT_MALFORMED,
    INPUT_NOT_PERMITTED,
    NOT_IN_ALLOWLIST,
    RESOURCE_UNKNOWN,
    SCOPE_NOT_HELD,
    SCOPE_NOT_HELD_REASON,
    STRUCTURAL_REFUSAL,
    UPSTREAM_REFUSED,
    AgentVisible,
    as_tool_error,
    denial_reason,
)
from app.mcp_lock import CapabilityLock, LockError, Resource, WriteSpec
from app.mcp_query import Filter, QueryRefusal, build_request, build_write_request
from app.mcp_telemetry import (
    LOGGER,
    OUTCOME_FAILED,
    OUTCOME_REFUSED,
    OUTCOME_SERVED,
    Timed,
)
from app.mcp_upstream import UpstreamRefusal, execute, execute_write

#: The three tool kinds, and what each one implies. **One vocabulary, three
#: named consequences** (ADR 0141).
#:
#: **This is deliberately not D495's mistake repeated.** There, one value
#: (`resource is None`) was carrying two ideas by ACCIDENT of representation,
#: and they agreed only until the first tool separated them. Here the
#: classification is the one the reviewed contract already makes -- it is the
#: lock's own `kind`, checked against `EXPECTED_KINDS` at load -- and each
#: consequence is written down beside its reason rather than inferred from a
#: shape that happens to correlate.
KIND_METADATA = "metadata"
KIND_READ = "read"
KIND_WRITE = "write"

#: Which kinds reach PostgREST, and therefore take a concurrency slot and a
#: thread (ADR 0129, D451, D495). Metadata answers from the lock in memory.
UPSTREAM_KINDS = (KIND_READ, KIND_WRITE)

#: Which kinds are audited (ADR 0141). **The same two, and it is a decision
#: rather than a consequence**: auditing the metadata tools would turn a
#: dictionary lookup into two network round trips and make discovery depend on
#: the audit table's availability, undoing the reason they take no slot.
AUDITED_KINDS = (KIND_READ, KIND_WRITE)

#: Which kinds do not happen when their record cannot be opened (ADR 0141,
#: D483). **A write only.** Failing a read closed would couple every agent
#: read's availability to the audit table and add a mandatory round trip to a
#: path that already pays one for its context.
FAIL_CLOSED_KINDS = (KIND_WRITE,)

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


def _sole_capability_version(lock: CapabilityLock, tool: str) -> str | None:
    """The version of this tool's capability, when it has exactly one.

    **`None` when the tool is backed by several**, and that is the honest
    answer rather than a shortcut: `query_resource` is `query_notes` and
    `query_tasks` (ADR 0120), they version independently, and the record is
    opened before the arguments have selected between them. Writing either
    version would name a capability this call may not have used.

    `None` also when the deployed lock is schema version 1, where a capability
    declares no version at all (ADR 0177). The two Nones are different facts and
    the column cannot tell them apart -- which is a limit of this run, stated
    here rather than discovered later, and it is the reason `contract_hash` is
    recorded beside it: the hash names the compiled contract, and the contract
    says which case this deployment is in.
    """
    declared = lock.tool(tool).capabilities
    return declared[0].version if len(declared) == 1 else None


class ToolRefusal(Exception):
    """A STRUCTURAL refusal: the caller is told nothing (ADR 0097, ADR 0130).

    **It carries a denial reason even though the caller gets none** (ADR
    0178). The two are not in tension: the caller is told nothing because
    a status this plane could not classify must not become a diagnosis,
    and the audit row says which boundary refused because an operator
    reading it later cannot re-derive that. Silence outward, a record
    inward.

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

    def __init__(self, message: str, reason: str) -> None:
        """`reason` is required, and it is not the message.

        The message is `STRUCTURAL_REFUSAL` at every site -- one string, on
        purpose, because it is what a caller would read and D433 refuses to make
        it more. The reason is the BOUNDARY, and it differs site by site: a lock
        the served surface no longer matches, an upstream that refused, an audit
        record that could not be written. Collapsing those three in the audit
        row is exactly what this parameter exists to stop.
        """
        super().__init__(message)
        self.reason = denial_reason(reason)


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
        raise AgentVisible(RESOURCE_UNKNOWN, str(error), NOT_IN_ALLOWLIST) from error

    held = _scopes()
    missing = [scope for scope in resource.required_scopes if scope not in held]
    if missing:
        # The scopes it NEEDS, not the ones it holds. The first is a fact about
        # this surface the caller could read from `describe_resource`; the second
        # would be this process telling a caller about its own token, which it
        # already has and which a log should not repeat back.
        raise AgentVisible(
            SCOPE_NOT_HELD,
            f"this resource requires {sorted(resource.required_scopes)}",
            SCOPE_NOT_HELD_REASON,
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
        raise ToolRefusal(STRUCTURAL_REFUSAL, CONTRACT_DRIFT) from error

    spec = declared.write
    if spec is None:  # pragma: no cover -- load_lock requires the write shape
        # Structural rather than caller-visible: a registered write tool whose
        # lock entry carries no write shape is a deployment fault, and nothing
        # the caller did produced it.
        raise ToolRefusal(STRUCTURAL_REFUSAL, CONTRACT_DRIFT)

    held = _scopes()
    if [scope for scope in spec.required_scopes if scope not in held]:
        raise AgentVisible(
            SCOPE_NOT_HELD,
            f"this tool requires {sorted(spec.required_scopes)}",
            SCOPE_NOT_HELD_REASON,
        )
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
    request_id: str,
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
        raise AgentVisible(INPUT_NOT_PERMITTED, str(error), NOT_IN_ALLOWLIST) from error

    try:
        rows = execute(base_url, token, request, request_id=request_id)
    except UpstreamRefusal as error:
        raise ToolRefusal(STRUCTURAL_REFUSAL, UPSTREAM_REFUSED) from error

    result = {"resource": found.name, "row_count": len(rows), "rows": rows}
    return _within_budget(
        result,
        found.max_rows,
        _byte_ceiling(lock.tool("query_resource").max_response_bytes),
    )


def _within_budget(
    result: dict[str, Any], max_rows: int, ceiling: int = MAX_SERIALIZED_BYTES
) -> dict[str, Any]:
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
        raise ToolRefusal(STRUCTURAL_REFUSAL, CONTRACT_DRIFT)
    return _within_byte_budget(result, ceiling)


def _byte_ceiling(declared: int | None) -> int:
    """This capability's ceiling, which may only NARROW the global (ADR 0179).

    `min` rather than the declared value, and the schema's `maximum` says the
    same thing — deliberately twice. The schema refuses a wider manifest before
    a deployment exists; this refuses a wider LOCK, which is a different input
    and one the runtime is required to distrust ("a lock is an input, not a
    teammate"). A lock compiled by something other than this repository's
    compiler is exactly the case where one of the two is the only one left.

    `None` at lock schema version below 3, where a capability declares none.
    """
    if declared is None:
        return MAX_SERIALIZED_BYTES
    return min(declared, MAX_SERIALIZED_BYTES)


def _within_byte_budget(
    result: dict[str, Any], ceiling: int = MAX_SERIALIZED_BYTES
) -> dict[str, Any]:
    """The byte ceiling alone, on every result this process returns.

    **Split out because the write path is a caller of it** (§6 question 5: when
    a decision is implemented, which of its callers got it?). `MAX_SERIALIZED_BYTES`
    is ADR 0129's response bound, and it was reachable only through the row
    check -- so a write result, which has no row ceiling to check, would have
    been the one path returning an unbounded response. `content` is an unbounded
    `text` column and `create_note` echoes the created row back, so the ceiling
    is not theoretical there.

    `ceiling` defaults to the global so that a caller which has no capability
    bound to hand still gets the bound that always applied. **Measured** before
    the per-capability bound was added: a metadata response is 288-683 bytes, a
    write's is 8-12 KB at 4 KiB of content, and a read over `notes` reaches 1 MiB
    at 42 rows when every column holds 4 KiB -- against a `max_rows` of 200. The
    row budget and the byte budget cross over at roughly 860 bytes per column,
    which is what makes them independent in fact and not only by decision.
    """
    serialized = len(json.dumps(result, separators=(",", ":")).encode("utf-8"))
    if serialized > ceiling:
        # Caller-visible, and the advice is the point: this is the one budget a
        # caller can stay inside by asking differently.
        raise AgentVisible(
            BUDGET_EXCEEDED,
            f"the result is {serialized} bytes, above the {ceiling} ceiling; "
            "ask for fewer columns or fewer rows",
            BUDGET_EXCEEDED_REASON,
        )
    return result


def run_report(
    lock: CapabilityLock, *, base_url: str, token: str, request_id: str
) -> dict[str, Any]:
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
        raise ToolRefusal(STRUCTURAL_REFUSAL, CONTRACT_DRIFT)
    found = _resource_for(lock, "run_report", tool.resources[0].name)

    try:
        request = build_request(found, timeout_ms=tool.timeout_ms)
    except QueryRefusal as error:
        raise AgentVisible(INPUT_NOT_PERMITTED, str(error), NOT_IN_ALLOWLIST) from error

    try:
        rows = execute(base_url, token, request, request_id=request_id)
    except UpstreamRefusal as error:
        raise ToolRefusal(STRUCTURAL_REFUSAL, UPSTREAM_REFUSED) from error

    if len(rows) != 1:
        # The report is one row by construction. Anything else is a surface that
        # has changed underneath the lock, and reporting the first row would be
        # reporting a number nobody bounded. Structural: not the caller's doing.
        raise ToolRefusal(STRUCTURAL_REFUSAL, CONTRACT_DRIFT)
    # **`run_report` returned its row with no byte check at all until D899.**
    #
    # `_within_byte_budget` was split out in Session 9 precisely so the write
    # path would get the ceiling the read path had -- its docstring says so, and
    # cites question 5 by name. This is the THIRD caller, and it was missed by
    # the same split: `query_resource` reaches the check through `_within_budget`
    # and a write reaches it directly, and this one returned `rows[0]`.
    #
    # Not theoretical. Measured at 32,927 bytes for one row when each column
    # holds 4 KiB -- one row, so the row budget can never bind, which is exactly
    # the case a byte ceiling exists for.
    return _within_byte_budget(rows[0], _byte_ceiling(tool.max_response_bytes))


#: What a caller's idempotency key may look like, checked before it is sent.
#:
#: The same shape migration 0029 enforces, and deliberately BOTH (ADR 0181). The
#: database's check is the one that cannot be routed around -- an agent posting
#: to `/rpc/create_note` directly still meets it, which is 0019's own reason for
#: putting the audit row inside the write. This one exists so a caller's mistake
#: is answered by the boundary that received it, rather than arriving as a
#: `PT412` translated from upstream and indistinguishable from the other thing
#: `PT412` means -- a key already bound to a different call.
IDEMPOTENCY_KEY_PATTERN: Final = re.compile(r"^[\x21-\x7e]{8,255}$")

#: Write-tool parameters that are the RUNTIME's rather than the reviewed
#: function's, in the order they follow the lock's arguments (ADR 0181).
#:
#: The lock's `arguments` are the database function's parameters and a caller may
#: supply no other name (D470) -- so a name here is one that never enters the
#: request body. `idempotency_key` travels as a header, which is why both RPC
#: signatures stayed exactly where 0022 left them.
#:
#: **`bin/render-mcp-catalog.py` keeps its own copy and a test compares them**,
#: D486's pattern: a renderer at the repository root importing a service package
#: is the fragile half of the alternative, and a test between two lists is what
#: this repository uses in its place. Aliasing would make that test compare a
#: value with itself.
RESERVED_WRITE_PARAMETERS: Final = ("idempotency_key", "dry_run")


def _idempotency_key(candidate: Any) -> str:
    """One caller-supplied key, shape-checked at the boundary that received it."""
    if not isinstance(candidate, str) or not IDEMPOTENCY_KEY_PATTERN.match(candidate):
        raise AgentVisible(
            INPUT_NOT_PERMITTED,
            "an idempotency key is 8 to 255 printable ASCII characters",
            INPUT_MALFORMED,
        )
    return candidate


def invoke_write(
    lock: CapabilityLock,
    *,
    base_url: str,
    token: str,
    request_id: str,
    tool: str,
    arguments: dict[str, Any],
    idempotency_key: str,
    dry_run: bool,
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
    entry = lock.tool(tool)

    # **Approval, beside the scope check and before anything is dialled** (ADR
    # 0182, D870). The record is already open, so the refusal is audited (ADR
    # 0141), and no upstream request is made for a call that cannot proceed.
    #
    # **Terminal, not pending.** Nothing here implies a request a caller should
    # wait on: approval in this product is a declaration and a named refusal,
    # because a workflow needs durable pending state, a second principal and a
    # notification plane, none of which exists.
    if entry.requires_approval:
        raise AgentVisible(
            APPROVAL_REQUIRED,
            "this capability requires an approval this deployment cannot grant",
            APPROVAL_REQUIRED_REASON,
        )

    # A rehearsal of a write that cannot be rehearsed is an input the lock does
    # not permit -- existing vocabulary, no new concept. `None` is lock schema
    # version 1, where a capability declares neither field: asking for a dry-run
    # against a deployment that never said it supports one is refused for the
    # same reason, and D600 is why the two Nones are not defaulted to false.
    if dry_run and not entry.supports_dry_run:
        raise AgentVisible(
            INPUT_NOT_PERMITTED,
            "this capability does not support a dry run",
            NOT_IN_ALLOWLIST,
        )

    # First, with the other input checks and before anything is built, for this
    # function's stated reason: a refusable call costs no upstream request.
    key = _idempotency_key(idempotency_key)

    try:
        request = build_write_request(spec, timeout_ms=entry.timeout_ms, arguments=arguments)
    except QueryRefusal as error:
        raise AgentVisible(INPUT_NOT_PERMITTED, str(error), NOT_IN_ALLOWLIST) from error

    try:
        rows = execute_write(
            base_url,
            token,
            request,
            max_affected_rows=spec.max_affected_rows,
            request_id=request_id,
            idempotency_key=key,
            dry_run=dry_run,
        )
    except UpstreamRefusal as error:
        raise ToolRefusal(STRUCTURAL_REFUSAL, UPSTREAM_REFUSED) from error

    if len(rows) != 1:
        # Both reviewed writes are `RETURNS <composite>` -- exactly one row
        # (D487). Zero is a shape that changed underneath the lock, and the
        # write has already committed, so this is loud rather than quiet.
        raise ToolRefusal(STRUCTURAL_REFUSAL, CONTRACT_DRIFT)

    # **`row_count` is 0 for a rehearsal, and `dry_run` says so explicitly.**
    # The database returns one composite either way -- a dry-run's is the row it
    # would have written, with a created row's id nulled (ADR 0182) -- so the
    # count is the only thing that can distinguish them, and a caller should not
    # have to infer it from a null field. `bounded()` reads `row_count` for the
    # telemetry record, so a rehearsal is measured as affecting nothing too.
    return _within_byte_budget(
        {
            "tool": tool,
            "row_count": 0 if dry_run else len(rows),
            "row": rows[0],
            "dry_run": dry_run,
        },
        _byte_ceiling(entry.max_response_bytes),
    )


def _filter(entry: Any) -> Filter:
    """One caller filter object, shaped before it is checked.

    `value` is absent for `is_null` and required for everything else, and both
    are the caller's to get wrong -- so the shape check is here and the
    permission check is `build_filter`'s, against the lock.
    """
    if not isinstance(entry, dict):
        raise AgentVisible(
            INPUT_NOT_PERMITTED,
            "a filter is an object with column, operator and value",
            INPUT_MALFORMED,
        )
    for required in ("column", "operator"):
        if not isinstance(entry.get(required), str) or not entry[required]:
            raise AgentVisible(
                INPUT_NOT_PERMITTED, f"a filter needs a non-empty {required}", INPUT_MALFORMED
            )
    unknown = set(entry) - {"column", "operator", "value"}
    if unknown:
        raise AgentVisible(
            INPUT_NOT_PERMITTED, f"a filter has no {sorted(unknown)} member", INPUT_MALFORMED
        )
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
    from app.mcp_authorization import current_request_id, current_token

    read_slots = slots if slots is not None else ReadSlots(DEFAULT_MAX_CONCURRENT_READS)

    # **One semaphore per tool that declares a bound** (ADR 0179), built once at
    # registration rather than per call: a slot created per request bounds
    # nothing, because each caller would get its own.
    #
    # `min(declared, the process-wide limit)` -- a capability may narrow the
    # share and may never widen it. A tool declaring more than the process has
    # is not an error, it is simply not the binding constraint, and clamping
    # here means the two numbers cannot disagree later.
    #
    # A tool with no declared bound (schema version below 3, or a metadata tool)
    # gets a null slot that admits everything, so the global remains its only
    # bound -- which is exactly what it had before this run.
    _per_tool = {
        entry.name: ReadSlots(min(entry.max_concurrent_calls, read_slots.limit))
        for entry in lock.tools
        if entry.max_concurrent_calls is not None
    }

    def tool_slots(name: str) -> Any:
        """This tool's own slot, or a context manager that admits everything."""
        return _per_tool.get(name) or contextlib.nullcontext()

    async def bounded(
        tool: str, resource: str | None, work: Any, *, kind: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """One boundary for every tool call: measure, bound, translate, record.

        **Four jobs in one place**, and the alternative is four decorators every
        future tool author has to remember -- which is D333's shape.

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

        *Record.* Begin before the work, complete after, with the outcome, the
        elapsed milliseconds, the row count and the caller's parameters redacted
        per the lock (ADR 0141, D479).

        **`kind` replaced Run 5's `upstream` boolean**, and it is one vocabulary
        with three NAMED consequences rather than one flag carrying three ideas
        -- `UPSTREAM_KINDS`, `AUDITED_KINDS` and `FAIL_CLOSED_KINDS`, each with
        its reason at the definition. D495's defect was an *accidental*
        correlation (`resource is None`); this is the lock's own classification,
        already checked against `EXPECTED_KINDS` at load.

        **The order is begin, then the work, then complete** -- and the scope
        check lives inside the work, deliberately. A call refused for a missing
        scope has therefore already opened its record, and `complete` closes it
        as `refused`. Checking scopes first would be cheaper and would lose
        exactly the denial record `AGT-AUDIT-001` names.

        **A write whose `begin` fails does not happen; a read's proceeds**
        (ADR 0141). And a failing `complete` never fails the call: the work has
        happened, a committed write cannot be un-committed by a bookkeeping
        failure, and reporting a failure that did not occur would make the
        record less true rather than more.
        """
        # The span wraps the SAME block the telemetry record measures, so the
        # two describe one call rather than two overlapping ones. It carries no
        # request id attribute: on a span the request id IS the trace id
        # (ADR 0166), and writing it twice would put one value in two places
        # that could later disagree.
        #
        # A no-op until a collector is configured, which is why it can sit in
        # the hot path from this run rather than waiting for one.
        with (
            mcp_tracing.span("agent.tool_call", tool=tool, resource=resource),
            Timed(tool, resource=resource) as timed,
        ):
            audit_id: str | None = None
            token: str | None = None
            quota_spent = False
            try:
                context = current_agent_context()
                timed.principal(agent_id=context.agent_id, owner_id=context.owner_id)
                timed.request_id = current_request_id()
                token = current_token()
            except Exception:
                timed.principal(agent_id=None, owner_id=None)

            if kind in AUDITED_KINDS and token is not None and timed.request_id is not None:
                try:
                    opened = await asyncio.to_thread(
                        audit_begin,
                        base_url,
                        token,
                        tool=tool,
                        request_id=timed.request_id,
                        parameters=audit_redact(arguments, lock.tool(tool).audit_redact),
                        capability_version=_sole_capability_version(lock, tool),
                        contract_hash=lock.canonical_sha256,
                    )
                    audit_id = opened
                    quota_spent = opened is None
                except (AuditRefusal, UpstreamRefusal) as error:
                    if kind in FAIL_CLOSED_KINDS:
                        # The record is the point for a write: a change nothing
                        # describes is the one thing this table exists to
                        # prevent. Structural, so the caller is told nothing --
                        # an unauditable write is this deployment's fault.
                        timed.refused()
                        raise ToolRefusal(STRUCTURAL_REFUSAL, AUDIT_UNAVAILABLE) from error
                    # A read carries on. Its availability does not depend on the
                    # audit table, and the failure is not silent -- it lands in
                    # telemetry as the record below.
                    LOGGER.warning(
                        "apg.mcp.audit %s",
                        json.dumps({"tool": tool, "phase": "begin", "error": type(error).__name__}),
                    )

                # **The quota refused, and the record already says so** (ADR
                # 0180). `begin` counted the call, found it over the agent's
                # window and wrote a complete `refused` row in the same
                # transaction, so there is nothing to close.
                #
                # **`quota_spent` is a separate flag and not `audit_id is None`**,
                # which is the same value for two different events: a READ whose
                # `begin` raised also leaves `audit_id` at `None` and carries on
                # by design (ADR 0141), and testing the id would turn every
                # audit-plane outage into a quota refusal for every read. One
                # value, two meanings -- D495's shape, and it was in the first
                # draft of this block.
                #
                # Raised as `AgentVisible` rather than structurally: this is the
                # one budget a caller can act on, by waiting. The other four
                # bound a single call; this one bounds a rate, so "try later" is
                # advice rather than a guess about state.
                if quota_spent:
                    timed.refused()
                    raise as_tool_error(
                        AgentVisible(
                            BUDGET_EXCEEDED,
                            "this agent's call quota for the current window is spent",
                            BUDGET_EXCEEDED_REASON,
                        )
                    )

            try:
                if kind not in UPSTREAM_KINDS:
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
                    # **The tool's own slot, then the process-wide one** (ADR
                    # 0179), and the order is deliberate. The process-wide bound
                    # is a share of PostgREST's pool and is the one that protects
                    # a resource shared with human callers, so it is acquired
                    # LAST and released FIRST -- a task waiting for the global
                    # holds only its own tool's slot, never a share of the pool
                    # it has not been granted.
                    #
                    # Both are counting semaphores over disjoint sets, so there
                    # is no cycle and no deadlock: a task holds at most one of
                    # each and never waits on a tool slot while holding a global
                    # one.
                    async with tool_slots(tool), read_slots:
                        result = await asyncio.to_thread(work)
            except AgentVisible as visible:
                timed.refused()
                await _close(timed, audit_id, token, OUTCOME_REFUSED, None, visible.reason)
                raise as_tool_error(visible) from visible
            except ToolRefusal as refusal:
                timed.refused()
                await _close(timed, audit_id, token, OUTCOME_REFUSED, None, refusal.reason)
                raise
            except Exception:
                # Unclassified: the record says `failed` rather than being left
                # open forever. `Timed` logs the exception TYPE and never its
                # message, which is where a caller's value would be if one ever
                # reached one.
                # `failed`, not `refused`, so it carries no reason -- and the
                # equivalence CHECK in 0027 is what makes that a property.
                await _close(timed, audit_id, token, OUTCOME_FAILED, None, None)
                raise

            row_count = result.get("row_count") if isinstance(result, dict) else None
            timed.served(row_count)
            await _close(timed, audit_id, token, OUTCOME_SERVED, row_count, None)
            return result

    async def _close(
        timed: Timed,
        audit_id: str | None,
        token: str | None,
        outcome: str,
        row_count: int | None,
        reason: str | None,
    ) -> None:
        """Close the record, and never let closing it change the outcome.

        Every failure here is swallowed into telemetry (ADR 0141). The work has
        already happened by the time this runs; raising would report a failure
        that did not occur, and for a write it would report one about a change
        that is already committed.
        """
        if audit_id is None or token is None:
            return
        try:
            closed = await asyncio.to_thread(
                audit_complete,
                base_url,
                token,
                audit_id=audit_id,
                outcome=outcome,
                request_id=timed.request_id or "",
                elapsed_ms=timed.elapsed_ms(),
                row_count=row_count,
                denial_reason=reason,
            )
        except (AuditRefusal, UpstreamRefusal) as error:
            LOGGER.warning(
                "apg.mcp.audit %s",
                json.dumps(
                    {"tool": timed.tool, "phase": "complete", "error": type(error).__name__}
                ),
            )
            return
        if not closed:
            # `false` means no STARTED record of this agent's has that id --
            # already closed, or never opened. A fact worth a line, and not a
            # transport failure (rig6: 200 false, never an error).
            LOGGER.warning(
                "apg.mcp.audit %s",
                json.dumps({"tool": timed.tool, "phase": "complete", "closed": False}),
            )

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
        return await bounded(
            "list_resources",
            None,
            lambda: list_resources(lock),
            kind=KIND_METADATA,
            arguments={},
        )

    @server.tool(name="describe_resource", timeout=seconds("describe_resource"))
    async def _describe_resource(tool: str, resource: str) -> dict[str, Any]:
        """One resource's frozen columns, permitted filters and permitted
        ordering, exactly as the lock froze them. Read from the deployed lock."""
        return await bounded(
            "describe_resource",
            None,
            lambda: describe_resource(lock, tool=tool, resource=resource),
            kind=KIND_METADATA,
            arguments={"tool": tool, "resource": resource},
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
                request_id=current_request_id(),
                resource=resource,
                columns=columns,
                filters=filters,
                order_by=order_by,
                limit=limit,
            ),
            kind=KIND_READ,
            # **The audit record carries what telemetry deliberately does not**
            # (ADR 0141): a filter operand is a caller value, forbidden in a
            # telemetry line and exactly what a record-keeper needs. The two
            # artefacts have different readers and different homes.
            arguments={
                "resource": resource,
                "columns": columns,
                "filters": filters,
                "order_by": order_by,
                "limit": limit,
            },
        )

    @server.tool(name="run_report", timeout=seconds("run_report"))
    async def _run_report() -> dict[str, Any]:
        """The caller's own activity, counted under the caller's own RLS: notes
        and tasks totals, tasks by status, and the two most recent update times."""
        return await bounded(
            "run_report",
            "owner_activity_report",
            lambda: run_report(
                lock,
                base_url=base_url,
                token=current_token(),
                request_id=current_request_id(),
            ),
            kind=KIND_READ,
            arguments={},
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

    # **`idempotency_key` is a tool parameter and NOT one of the lock's
    # `arguments`** (ADR 0181). The lock's list is the database function's
    # parameters in PostgreSQL order, and a name that is not one of them may not
    # be supplied (D470) -- the key never enters the request body. It travels as
    # a header, so both RPC signatures stay exactly where 0022 left them and the
    # human REST surface is untouched.
    #
    # Required, not optional. An unconditional guarantee is worth more than one
    # an agent has to remember to ask for, and it is also what lets the forwarded
    # header rosters stay two exact sets rather than one loose one.

    @server.tool(name="create_note", timeout=seconds("create_note"))
    async def _create_note(
        p_title: str, p_content: str, idempotency_key: str, dry_run: bool
    ) -> dict[str, Any]:
        """Create one note owned by the caller's owner, and return the created
        row. Bounded to one row; the owner is the caller's, never an argument.

        `idempotency_key` is the caller's own token for this operation: send the
        same one to retry safely, and a fresh one for a genuinely new note. The
        same key with different arguments is refused rather than deduplicated.
        """
        return await bounded(
            "create_note",
            None,
            lambda: invoke_write(
                lock,
                base_url=base_url,
                token=current_token(),
                request_id=current_request_id(),
                tool="create_note",
                arguments={"p_title": p_title, "p_content": p_content},
                idempotency_key=idempotency_key,
                dry_run=dry_run,
            ),
            kind=KIND_WRITE,
            # `p_content` is redacted from the record by the lock's
            # `audit_redact` (D479) -- the key stays, the value does not.
            #
            # The idempotency key is absent here on purpose. It is a caller
            # value, and an agent record carries none (ADR 0130); where it
            # legitimately lives is `app_private.agent_idempotency`, which is
            # the dedupe state rather than an annotation of it.
            arguments={"p_title": p_title, "p_content": p_content},
        )

    @server.tool(name="update_task_status", timeout=seconds("update_task_status"))
    async def _update_task_status(
        p_task_id: str,
        p_expected_status: str,
        p_new_status: str,
        idempotency_key: str,
        dry_run: bool,
    ) -> dict[str, Any]:
        """Move one of the caller's owner's tasks from an expected status to a
        new one.

        A compare-and-swap: the write is refused when the expected status no
        longer holds, and that refusal reaches the caller as `write_conflict`
        because its next move is to re-read and retry (ADR 0139).

        **A replay of this one is where a key earns its keep.** Without it, a
        retried transition fails its own compare-and-swap -- the status it
        expects is the status it already set -- and the caller reads
        `write_conflict` for a write that had in fact succeeded. Migration
        0029's claim runs before the swap for exactly that reason.
        """
        return await bounded(
            "update_task_status",
            None,
            lambda: invoke_write(
                lock,
                base_url=base_url,
                token=current_token(),
                request_id=current_request_id(),
                tool="update_task_status",
                arguments={
                    "p_task_id": p_task_id,
                    "p_expected_status": p_expected_status,
                    "p_new_status": p_new_status,
                },
                idempotency_key=idempotency_key,
                dry_run=dry_run,
            ),
            kind=KIND_WRITE,
            # Nothing redacted: a task id and two status literals are the
            # transition itself, which is what the record is for.
            arguments={
                "p_task_id": p_task_id,
                "p_expected_status": p_expected_status,
                "p_new_status": p_new_status,
            },
        )

    return TOOL_NAMES
