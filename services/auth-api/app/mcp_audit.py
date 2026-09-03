"""The durable record: begin before the work, complete after (ADR 0141).

**Not telemetry, and the distinction is the decision** (ADR 0130, ADR 0135).
Telemetry answers "what happened" for an operator watching a running deployment,
lives in the journal, and may carry no caller value at all. This record answers
"what happened" for a record-keeper months later, lives in `app_private` where
nobody holds a grant, and carries the caller's parameters **on purpose** —
redacted per the lock, which is what `audit.redact` was validated for and
consumed by nothing until now (D479).

**The runtime holds no database credential and never will** (D407, D473). Both
calls go over PostgREST as the caller, exactly as the context lookup does, to
two `SECURITY DEFINER` functions that take **no principal**: the agent and its
owner come from the GUCs the pre-request hook set. That is what makes
`SEC-PARAM-001` structural rather than validated — there is no argument for a
caller to lie in.

**The wire shapes are measured** (rig6, PostgREST v14.16), and the composite
findings of Run 4's rig are not evidence for them:

    RETURNS uuid    (non-SETOF)  ->  a bare JSON STRING   "c8c13a67-…"
    RETURNS SETOF uuid           ->  an ARRAY             ["fa15e1b7-…"]
    RETURNS boolean (non-SETOF)  ->  a bare JSON true / false
    closing a closed record      ->  200 false, never an error
    an outcome of `committed`    ->  422 / PT422
    no agent identity            ->  403 / PT403

**A `started` row survives the request that wrote it.** Each RPC call is its own
transaction and commits before the next runs — measured, three rows still
`started` at the end of the rig — which is the whole reason an `agent_plane`
record can describe a write that failed, where the `database` row can only
describe one that committed (D489).
"""

from __future__ import annotations

import json
from typing import Any

from app.mcp_query import UpstreamRequest
from app.mcp_upstream import UpstreamRefusal, _dial

#: The two operations, as module constants.
#:
#: Named here rather than read from the lock because they are not tools: no
#: caller selects them, no capability names them, and they appear in the
#: reviewed surface under `agent_write_rpcs` (ADR 0136) rather than among the
#: six. `AGENT_CONTEXT_PATH` next door is a constant for the same reason -- there
#: is no code path in this module that takes a path from anybody.
AUDIT_BEGIN_PATH = "/rpc/agent_audit_begin"
AUDIT_COMPLETE_PATH = "/rpc/agent_audit_complete"

#: How long the plane waits for one audit call, in milliseconds.
#:
#: The same order as the context lookup, and deliberately not a per-tool budget
#: from the lock: a tool's `timeout_ms` bounds the tool's own work, and spending
#: all of it on bookkeeping would let the audit path consume the budget the work
#: needs. A write that waits this long twice has already blown its own timeout,
#: which is the outer bound that actually protects the caller (ADR 0129).
AUDIT_TIMEOUT_MS = 5000

#: What replaces a redacted parameter's value.
#:
#: A constant string rather than removing the key, because absence and
#: redaction are different facts: a record showing `p_content: "[redacted]"`
#: says the caller supplied one, and a record with no `p_content` says nothing
#: at all. The record-keeper needs the first.
REDACTED = "[redacted]"


class AuditRefusal(Exception):
    """The record could not be opened or closed.

    Structural, and masked (ADR 0130). An unauditable call is this deployment's
    fault rather than the caller's, and telling a caller that the audit table is
    unreachable describes internal state to somebody who has not established
    they may ask about it.

    **What this exception means depends on the tool's kind, and that is
    ADR 0141**: a write raising it does not happen; a read raising it proceeds
    and the failure becomes telemetry.
    """


def redact(arguments: dict[str, Any], redacted: tuple[str, ...]) -> dict[str, Any]:
    """The parameter document as the record should carry it (D479).

    The lock's `audit_redact` names the parameters whose VALUES may not be
    stored -- `create_note`'s is `["p_content"]`, because a note's body is the
    thing an agent was asked to write and not something a record needs to
    repeat. The key stays; only the value is replaced.

    **A name in the redaction list that the caller did not supply is not
    invented.** A record must not imply an argument was passed when it was not,
    and adding the key would do exactly that.
    """
    return {name: (REDACTED if name in redacted else value) for name, value in arguments.items()}


def _post(base_url: str, token: str, path: str, arguments: dict[str, Any], request_id: str) -> Any:
    """One audit RPC, through the one shared transport (ADR 0124).

    Builds an `UpstreamRequest` directly rather than through `mcp_query`: the
    path is a module constant above, there is no query string, no filter, no
    projection and no caller-selected operation, so there is nothing for the
    query builder's rules to apply to. It goes through `_dial` because that is
    the single place this process constructs an HTTP request.
    """
    status, body = _dial(
        base_url,
        token,
        UpstreamRequest(
            method="post",
            path=path,
            query="",
            timeout_ms=AUDIT_TIMEOUT_MS,
            body=json.dumps(arguments, sort_keys=True, ensure_ascii=False).encode("utf-8"),
        ),
        request_id=request_id,
    )
    if status != 200:
        # The body is not read for a code. Unlike a write refusal (ADR 0139),
        # nothing an audit call can say is the caller's to act on: every
        # outcome here is either "the record was kept" or "it was not".
        raise AuditRefusal(f"the audit call to {path} refused with status {status}")
    try:
        return json.loads(body)
    except ValueError as error:
        raise AuditRefusal(f"the audit response is not JSON: {error}") from error


def begin(
    base_url: str,
    token: str,
    *,
    tool: str,
    request_id: str,
    parameters: dict[str, Any],
    capability_version: str | None,
    contract_hash: str | None,
) -> str | None:
    """Open one record and return its id, or refuse.

    Measured: the response is a **bare JSON string**, because `RETURNS uuid` is
    a non-SETOF scalar. Parsed strictly -- anything else means the function's
    shape changed underneath this code, and a record id that is not one would
    close nothing later while looking like it had.
    """
    opened = _post(
        base_url,
        token,
        AUDIT_BEGIN_PATH,
        {
            "p_tool": tool,
            "p_request_id": request_id,
            "p_parameters": parameters,
            # **Sent explicitly, and `None` is a value rather than an omission**
            # (ADR 0178). Migration 0027 gives neither parameter a DEFAULT, so
            # omitting one is a signature mismatch rather than a quiet NULL --
            # which is the point after D857, and is safe now that ADR 0175's
            # guard reads `api` as well as `app_private`.
            "p_capability_version": capability_version,
            "p_contract_hash": contract_hash,
        },
        request_id,
    )
    # **`None` is the quota refusal, and it is the only other thing accepted**
    # (ADR 0180). This function had never returned NULL: a caller with no agent
    # identity is refused with PT403, so the only paths out were a record id or
    # an error.
    #
    # It means the refusal has ALREADY been recorded, complete, by that same
    # transaction -- there is nothing here to close, and closing something would
    # be closing a record this process did not open. Returned rather than raised,
    # because it is a verdict about the CALLER and not a failure of the audit
    # plane -- which is what `AuditRefusal` means to everything upstream, where a
    # read carries on past one and a write fails closed. Both would be wrong.
    if opened is None:
        return None
    if not isinstance(opened, str) or not opened.strip():
        raise AuditRefusal(f"agent_audit_begin returned {type(opened).__name__}, not a record id")
    return opened


def complete(
    base_url: str,
    token: str,
    *,
    audit_id: str,
    outcome: str,
    request_id: str,
    elapsed_ms: int,
    row_count: int | None,
    denial_reason: str | None,
) -> bool:
    """Close one record, and say whether it was actually closed.

    Returns the function's own boolean rather than raising on `false`, because
    the two mean different things: `false` is "no started record of yours has
    that id", which is a fact worth logging and not a transport failure. Both
    are non-fatal by ADR 0141 -- the work has already happened, and a write that
    committed cannot be un-committed by a bookkeeping failure.

    `committed` is not among the outcomes this can send: it belongs to a
    `database` row, which the write RPC writes in the write's own transaction
    and this plane does not (D489). The database refuses it (422 / PT422) and
    the caller of this function has no reason to try.
    """
    closed = _post(
        base_url,
        token,
        AUDIT_COMPLETE_PATH,
        {
            "p_audit_id": audit_id,
            "p_outcome": outcome,
            "p_elapsed_ms": elapsed_ms,
            "p_row_count": row_count,
            # Present exactly when the outcome is `refused`, which 0027 states
            # as an equivalence CHECK and the function refuses before the UPDATE
            # -- so a mismatch here is this repository's own errcode rather than
            # a constraint name arriving inside an audit call.
            "p_denial_reason": denial_reason,
        },
        request_id,
    )
    if not isinstance(closed, bool):
        raise AuditRefusal(f"agent_audit_complete returned {type(closed).__name__}, not a boolean")
    return closed


__all__ = [
    "AUDIT_BEGIN_PATH",
    "AUDIT_COMPLETE_PATH",
    "AUDIT_TIMEOUT_MS",
    "REDACTED",
    "AuditRefusal",
    "UpstreamRefusal",
    "begin",
    "complete",
    "redact",
]
