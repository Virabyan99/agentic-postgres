"""The tools the deployed lock carries, registered by kind and shape (ADR 0200).

Until Session 21 this module registered six named tools and nothing else, and
`mcp_lock` refused any lock that was not exactly those six. Now `register()`
walks the lock: the two `metadata` tools are the runtime's own and every lock
carries exactly them; a `read` is registered with the query shape when it
selects among relations and with no caller input when it runs one RPC; a
`write` is registered with the lock's own argument list. What keeps the surface
reviewed is no longer a number: the compiler signs the tool list it wrote and
`mcp_lock` refuses a list it did not sign.

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
import inspect
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
#: lock's own `kind`, checked by shape at load (ADR 0200) -- and each
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
    """The resources this caller can query, the scope each one needs, and WHICH
    LOCK THIS PROCESS LOADED.

    Filtered by the caller's scopes, so the list does not advertise what it
    would refuse (D421). Reads the lock and nothing else.

    **`lock` answers a question no other reader in this product can** (D1201,
    ADR 0204). On the Session 21 trip a deploy whose only change was the lock
    recreated neither container, so beta served six tools for eight minutes
    while the deployed document said seven (D1152) -- and the document, the
    doctor's capability-drift check and `mcp.tool_count` all read the lock
    *file*, so all three agreed with each other and none of them with the
    plane (D1153). A process cannot be wrong about which lock it loaded, so
    this member settles the question from the side that cannot lie, and a
    generated client compares it to the digest it was generated from before it
    calls anything.

    **The digest is the one the lock CARRIED, never a recomputation.** Hashing
    `lock.tools` here would produce a string for every lock, including one that
    carries no digest at all -- a pre-schema-4 lock would then report a value
    it never had, and a caller could not tell a missing digest from a matching
    one. `tools_sha256` is `str | None` and there is no `schema_version` field
    on `CapabilityLock` (D1215), so `None` -- rendered `null` -- IS the answer
    for a lock below schema 4, and it is a distinct answer rather than an
    absent one (ADR 0195).
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
        "lock": {"tools_sha256": lock.tools_sha256, "tool_count": lock.tool_count},
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
    # The resource-selecting read this call goes through. Registration always
    # passes the lock's name; the default is the release's, for the callers
    # that predate a lock with more than one (ADR 0200).
    tool: str = "query_resource",
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
    found = _resource_for(lock, tool, resource)
    parsed = [_filter(entry) for entry in filters or []]

    try:
        request = build_request(
            found,
            timeout_ms=lock.tool(tool).timeout_ms,
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
        _byte_ceiling(lock.tool(tool).max_response_bytes),
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
    lock: CapabilityLock,
    *,
    base_url: str,
    token: str,
    request_id: str,
    # The rpc read this call goes through; the default is the release's (ADR 0200).
    tool: str = "run_report",
) -> dict[str, Any]:
    """The caller's own activity, counted under the caller's own RLS.

    One named RPC, chosen from the lock and not by the caller: this tool takes no
    resource argument at all, because there is exactly one thing it runs.

    **SECURITY INVOKER on the database side** (migration 0018), which is what
    makes AGT-READ-001 meaningful: the same RLS that constrains a row constrains
    a count of rows, so an agent and its owner get identical numbers because they
    run the identical query under the identical claim.
    """
    entry = lock.tool(tool)
    if len(entry.resources) != 1:
        raise ToolRefusal(STRUCTURAL_REFUSAL, CONTRACT_DRIFT)
    found = _resource_for(lock, tool, entry.resources[0].name)

    try:
        request = build_request(found, timeout_ms=entry.timeout_ms)
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
    return _within_byte_budget(rows[0], _byte_ceiling(entry.max_response_bytes))


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
    approval: dict[str, str] | None = None,
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
    # **Still terminal for every caller without a matching claim.** Since
    # Session 33 a workflow's approval gate is the ONE path that carries one
    # (ADR 0231): a step token the signer minted from a human's recorded
    # decision, naming this tool and this idempotency key. It authorises ONE
    # write -- a replay of that key is re-read (ADR 0181), and any other write
    # the token could make is refused here as before. The refusal's text is
    # unchanged byte for byte, because a caller holding no claim is exactly
    # the caller it has always been said to.
    #
    # **An approved call is never rehearsed** (D1722): a capability may declare
    # a dry run its SQL does not keep, and until now the refusal above made that
    # unreachable. Any claim with `dry_run` is refused before anything is sent.
    if entry.requires_approval:
        if approval is not None and dry_run:
            raise AgentVisible(
                INPUT_NOT_PERMITTED,
                "an approved call is not rehearsed",
                NOT_IN_ALLOWLIST,
            )
        if approval is None or (approval.get("tool"), approval.get("key")) != (
            tool,
            idempotency_key,
        ):
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
    """Register every tool the lock carries, by kind and shape, and return their names.

    The names are returned rather than assumed so a test can compare them with
    the lock's -- which is now the definition rather than a check against one
    (ADR 0200): a lock the compiler signed is what this deployment serves.

    Each closure reads the caller's token from the context resolved for this
    request. Nothing here holds a token between requests: `current_agent_context`
    is backed by a `ContextVar` that is reset in a `finally` (ADR 0125).
    """
    from app.mcp_authorization import current_approval, current_request_id, current_token

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
        already checked by shape at load (ADR 0200).

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

    # **By kind and shape, never by name** (ADR 0200). `name=` on every one:
    # without it the framework names a tool after its Python function, and
    # the closures below are built from the lock's names precisely so the
    # registered name is the reviewed one.
    #
    # Rig 21a measured how the pinned framework takes a tool whose parameters
    # are DATA: a constructed `inspect.Signature` alone is refused at
    # registration (pydantic reads `__annotations__`); with the annotations set
    # as well, `tools/list` carries exactly the derived names, an undeclared
    # argument is refused before the handler, a missing one too, and the
    # per-tool timeout fires. A `FunctionTool` given an explicit `parameters`
    # schema advertises the same shape and enforces none of it -- so nothing
    # here builds a schema by hand (D1140).

    def described(entry: Any, closure: Any, name: str, sentence: str) -> Any:
        """Name the closure for the framework and give it the lock's prose."""
        closure.__name__ = name
        closure.__qualname__ = name
        closure.__doc__ = " ".join(part for part in (*entry.descriptions, sentence) if part)
        return server.tool(name=name, timeout=seconds(name))(closure)

    def register_metadata(entry: Any) -> None:
        if entry.name == "list_resources":

            async def _list_resources() -> dict[str, Any]:
                return await bounded(
                    entry.name,
                    None,
                    lambda: list_resources(lock),
                    kind=KIND_METADATA,
                    arguments={},
                )

            described(entry, _list_resources, entry.name, "Reads the deployed lock.")
            return

        async def _describe_resource(tool: str, resource: str) -> dict[str, Any]:
            return await bounded(
                entry.name,
                None,
                lambda: describe_resource(lock, tool=tool, resource=resource),
                kind=KIND_METADATA,
                arguments={"tool": tool, "resource": resource},
            )

        described(entry, _describe_resource, entry.name, "Reads the deployed lock.")

    def register_relation_read(entry: Any) -> None:
        """The query shape: the caller's own rows, filtered and ordered within
        frozen bounds. `order_by` is an INDEX into the orderings
        `describe_resource` returns, not an order string."""
        name = entry.name

        async def _query(
            resource: str,
            columns: list[str] | None = None,
            filters: list[dict[str, Any]] | None = None,
            order_by: int | None = None,
            limit: int | None = None,
        ) -> dict[str, Any]:
            return await bounded(
                name,
                resource,
                lambda: query_resource(
                    lock,
                    base_url=base_url,
                    token=current_token(),
                    request_id=current_request_id(),
                    tool=name,
                    resource=resource,
                    columns=columns,
                    filters=filters,
                    order_by=order_by,
                    limit=limit,
                ),
                kind=KIND_READ,
                # **The audit record carries what telemetry deliberately does
                # not** (ADR 0141): a filter operand is a caller value,
                # forbidden in a telemetry line and exactly what a
                # record-keeper needs.
                arguments={
                    "resource": resource,
                    "columns": columns,
                    "filters": filters,
                    "order_by": order_by,
                    "limit": limit,
                },
            )

        described(
            entry,
            _query,
            name,
            "`order_by` is an index into the orderings `describe_resource` returns.",
        )

    def register_rpc_read(entry: Any) -> None:
        """The report shape: one named RPC, chosen from the lock, no caller input."""
        name = entry.name
        resource_name = entry.resources[0].name if entry.resources else None

        async def _report() -> dict[str, Any]:
            return await bounded(
                name,
                resource_name,
                lambda: run_report(
                    lock,
                    base_url=base_url,
                    token=current_token(),
                    request_id=current_request_id(),
                    tool=name,
                ),
                kind=KIND_READ,
                arguments={},
            )

        described(entry, _report, name, "")

    def register_write(entry: Any) -> None:
        """A write's parameters are the lock's declared argument names --
        the reviewed function's parameter names, in PostgreSQL order -- plus
        `idempotency_key` and `dry_run`, and every one is required.

        A caller supplies a value for every declared argument, because
        PostgREST resolves a function by the names supplied and a missing one
        is a `404 PGRST202` (ADR 0139). `idempotency_key` is a tool parameter
        and NOT one of the lock's `arguments` (ADR 0181): it travels as a
        header, never in the request body.
        """
        name = entry.name
        arguments = tuple(entry.write.arguments)
        extras = ("idempotency_key", "dry_run")

        async def _write(**kwargs: Any) -> dict[str, Any]:
            unknown = sorted(set(kwargs) - set(arguments) - set(extras))
            missing = sorted(set(arguments) - set(kwargs)) + [e for e in extras if e not in kwargs]
            if unknown or missing:
                # The framework refuses both before this runs (rig 21a); this
                # is the same refusal for a caller that reached the closure
                # some other way, and it names the lock's list rather than the
                # caller's.
                raise as_tool_error(
                    AgentVisible(
                        INPUT_NOT_PERMITTED,
                        f"this tool takes exactly {list(arguments)} plus {list(extras)}",
                        INPUT_MALFORMED,
                    )
                )
            values = {argument: kwargs[argument] for argument in arguments}
            return await bounded(
                name,
                None,
                lambda: invoke_write(
                    lock,
                    base_url=base_url,
                    token=current_token(),
                    request_id=current_request_id(),
                    tool=name,
                    arguments=values,
                    idempotency_key=kwargs["idempotency_key"],
                    dry_run=kwargs["dry_run"],
                    # From the VERIFIED claims, never from an argument (ADR
                    # 0231); `None` for every token but an approved step's.
                    approval=current_approval(),
                ),
                kind=KIND_WRITE,
                # The idempotency key is absent here on purpose. It is a caller
                # value, and an agent record carries none (ADR 0130); where it
                # legitimately lives is `app_private.agent_idempotency`.
                arguments=values,
            )

        parameters = [
            inspect.Parameter(argument, inspect.Parameter.KEYWORD_ONLY, annotation=str)
            for argument in arguments
        ]
        parameters.append(
            inspect.Parameter("idempotency_key", inspect.Parameter.KEYWORD_ONLY, annotation=str)
        )
        parameters.append(
            inspect.Parameter("dry_run", inspect.Parameter.KEYWORD_ONLY, annotation=bool)
        )
        _write.__signature__ = inspect.Signature(parameters, return_annotation=dict[str, Any])  # type: ignore[attr-defined]
        _write.__annotations__ = {
            **{argument: str for argument in arguments},
            "idempotency_key": str,
            "dry_run": bool,
            "return": dict[str, Any],
        }
        described(
            entry,
            _write,
            name,
            "Bounded to the lock's affected-row limit; the owner is the caller's, never an "
            "argument. Send the same `idempotency_key` to retry safely and a fresh one for "
            "a new operation; `dry_run: true` rehearses the write and rolls it back.",
        )

    registered: list[str] = []
    for entry in sorted(lock.tools, key=lambda tool: tool.name):
        if entry.kind == KIND_METADATA:
            register_metadata(entry)
        elif entry.kind == KIND_READ and entry.read_shape == "relation":
            register_relation_read(entry)
        elif entry.kind == KIND_READ:
            register_rpc_read(entry)
        else:
            register_write(entry)
        registered.append(entry.name)

    return tuple(registered)
