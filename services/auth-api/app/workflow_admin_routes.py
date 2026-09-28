"""Four routes for HUMAN administrators over the workflow plane (ADR 0230-0234).

**The other side of `workflow_routes`.** Those three take an AGENT token through
`authenticate_agent`; these four take an ACCESS token through `authenticate`,
which refuses an agent token before any scope is read. So the agent whose run
waits on an approval cannot decide it however it is authorised: it cannot hold
a human token at all (ADR 0232's first control).

* `GET /admin/workflows/approvals` -- what waits for a human, oldest first,
  under `admin_workflows:approve`. **No argument value, no input, no result**
  (D1720): the database builds the document and it carries none of them.
* `POST /admin/workflows/runs/{run_id}/approve` and `.../reject` -- one decision
  on the step the BODY names, under `admin_workflows:approve`. The database
  refuses the run's owner, a decided approval and an expired one before any
  write, and those three words become three fixed documents here.
* `GET /admin/workflows/runs/{run_id}` -- one run's provenance under
  `admin_audit:read`, the audit's own scope: it is the audit record, joined
  by request id (ADR 0234).

**Every authority is the database's** (`workflow_routes`' rule): this module
holds no ownership rule and no state machine, and translates refusals into
HTTP. A message the database chose is read for one word and never relayed.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from app import errors, openapi_docs, strict_query
from app import scopes as scope_map
from app.models import (
    ApprovalConflictResponse,
    ApproverIsOwnerResponse,
    NoSuchWorkflowResponse,
    WorkflowDecisionRequest,
    WorkflowDecisionResponse,
)
from app.routes import _body, _guard, _service
from app.service import AuthService
from app.workflow_routes import NOT_FOUND_SQLSTATE, _workflows, jsonable

router = APIRouter()

#: The errcodes `workflow_decide_approval` raises, and the ONE word of its
#: message each is read for. The function writes nothing before any of them.
FORBIDDEN_SQLSTATE = "PT403"
CONFLICT_SQLSTATE = "PT409"
APPROVER_IS_OWNER_MARKER = "approver_is_owner"
ALREADY_DECIDED_MARKER = "approval_already_decided"
EXPIRED_MARKER = "approval_expired"

#: `GET /admin/workflows/approvals`' one parameter and its bound -- the
#: function's own 1..100, restated here as the route's refusal so a caller is
#: told the range rather than handed a translated PT422.
APPROVALS_QUERY_PARAMETERS: tuple[str, ...] = ("limit",)
APPROVALS_LIMIT_MIN = 1
APPROVALS_LIMIT_MAX = 100
APPROVALS_LIMIT_DEFAULT = 50

#: The two decisions, as the path spells them and as the function takes them.
DECISIONS = {"approve": "approve", "reject": "reject"}

DOC_LIST_APPROVALS = openapi_docs.described(
    summary="List the approvals waiting for a human",
    description=(
        "Requires `admin_workflows:approve` and an ACCESS token; an agent token is refused "
        "before the scope is read. Pending, unexpired approvals on running runs, oldest "
        "first: the run, the definition and its version, the step and its position, the "
        "capability and tool, the agent and its owner, when approval was requested and when "
        "it expires. **Never an argument value, the run's input or a result** -- what the "
        "step does is in the reviewed definition."
    ),
    query_parameters=[
        openapi_docs.query_parameter(
            "limit",
            schema={
                "type": "integer",
                "minimum": APPROVALS_LIMIT_MIN,
                "maximum": APPROVALS_LIMIT_MAX,
                "default": APPROVALS_LIMIT_DEFAULT,
            },
            description=(
                f"Approvals to return, {APPROVALS_LIMIT_MIN}-{APPROVALS_LIMIT_MAX}. Outside "
                "the range is refused with 422; it is never clamped."
            ),
        )
    ],
)
RESP_LIST_APPROVALS = {
    200: openapi_docs.ok("Pending approvals, oldest first."),
    401: openapi_docs.UNAUTHENTICATED,
    403: openapi_docs.UNAUTHORIZED,
    422: openapi_docs.INVALID,
}

_DECISION_REFUSALS = {
    400: openapi_docs.MALFORMED,
    401: openapi_docs.UNAUTHENTICATED,
    403: {
        "model": ApproverIsOwnerResponse,
        "description": (
            "Either the token lacks `admin_workflows:approve` (`authorization_failed`) or the "
            "approver owns the agent whose run this is (`approver_is_owner`): holding the "
            "scope is not enough to decide your own agent's run."
        ),
    },
    404: {
        "model": NoSuchWorkflowResponse,
        "description": (
            "No approval for that step of that run, or a run that is no longer running. One "
            "answer, as the agent surface gives."
        ),
    },
    409: {
        "model": ApprovalConflictResponse,
        "description": (
            "`approval_already_decided` -- a decision is final -- or `approval_expired`: the "
            "window closed before anyone decided, and the run fails at its next claim."
        ),
    },
}

DOC_APPROVE = openapi_docs.described(
    summary="Approve one parked step of a run",
    description=(
        "Requires `admin_workflows:approve`. The step is named in the body and must be the "
        "one the approval is for. Approving makes it claimable at once, and the call it "
        "retries carries the decision as a signed claim, so the plane serves that one write."
    ),
    request_model=WorkflowDecisionRequest,
)
RESP_APPROVE = {
    200: openapi_docs.ok("The decision was recorded.", WorkflowDecisionResponse),
    **_DECISION_REFUSALS,
}

DOC_REJECT = openapi_docs.described(
    summary="Reject one parked step of a run",
    description=(
        "Requires `admin_workflows:approve`. **A rejection is a cancel**: the run's cancel "
        "is requested, the next claim applies it, and the steps that succeeded and declare "
        "a compensation are undone in reverse."
    ),
    request_model=WorkflowDecisionRequest,
)
RESP_REJECT = {
    200: openapi_docs.ok("The decision was recorded.", WorkflowDecisionResponse),
    **_DECISION_REFUSALS,
}

DOC_PROVENANCE = openapi_docs.described(
    summary="Read one run's provenance",
    description=(
        "Requires `admin_audit:read`. The run, every step with every attempt joined to its "
        "audit rows by request id, and every approval with the human who decided it. It "
        "answers for ANY agent's run -- a revoked agent's stopped run included -- because "
        "this is the audit's reader, not the agent's. The run's input is reported by its "
        "keys only, and no field carries an argument value or a result."
    ),
)
RESP_PROVENANCE = {
    200: openapi_docs.ok("The run's provenance."),
    401: openapi_docs.UNAUTHENTICATED,
    403: openapi_docs.UNAUTHORIZED,
    404: {"model": NoSuchWorkflowResponse, "description": "No such run."},
}


def _translate(exc: psycopg.Error) -> None:
    """The decision's refusals, translated -- never relayed (ADR 0139, D433)."""
    sqlstate = getattr(exc.diag, "sqlstate", None)
    message = str(exc)
    if sqlstate == NOT_FOUND_SQLSTATE:
        raise errors.NoSuchWorkflow from exc
    if sqlstate == FORBIDDEN_SQLSTATE and APPROVER_IS_OWNER_MARKER in message:
        raise errors.ApproverIsOwner from exc
    if sqlstate == CONFLICT_SQLSTATE and ALREADY_DECIDED_MARKER in message:
        raise errors.ApprovalAlreadyDecided from exc
    if sqlstate == CONFLICT_SQLSTATE and EXPIRED_MARKER in message:
        raise errors.ApprovalExpired from exc
    raise exc


async def _admin(request: Request, scope: str) -> Any:
    """An ACCESS token holding `scope`. An agent token never gets this far."""
    principal = await _service(request).authenticate(request.headers.get("authorization"))
    AuthService.require_scope(principal, scope)
    return principal


async def _admin_guard(handler: Any) -> Response:
    """`_guard`, with the workflow plane's four outcomes around it."""

    async def run() -> Response:
        try:
            return await handler()
        except errors.NoSuchWorkflow:
            return errors.no_such_workflow()
        except errors.ApproverIsOwner:
            return errors.approver_is_owner()
        except errors.ApprovalAlreadyDecided:
            return errors.approval_already_decided()
        except errors.ApprovalExpired:
            return errors.approval_expired()

    return await _guard(run)


def _run_id(value: str) -> UUID:
    """A malformed id is the same 404 a missing run gets (`workflow_routes`' reason)."""
    try:
        return UUID(value)
    except ValueError as exc:
        raise errors.NoSuchWorkflow from exc


@router.get(
    "/admin/workflows/approvals", openapi_extra=DOC_LIST_APPROVALS, responses=RESP_LIST_APPROVALS
)
async def list_approvals(request: Request) -> Response:
    """WF-ADMIN-001. Authenticate, require the scope, THEN parse the query."""

    async def run() -> Response:
        await _admin(request, scope_map.ADMIN_WORKFLOWS_APPROVE)
        try:
            supplied = strict_query.parse(
                request.query_params.multi_items(), APPROVALS_QUERY_PARAMETERS
            )
            limit = (
                strict_query.as_bounded_int(
                    "limit",
                    supplied["limit"],
                    minimum=APPROVALS_LIMIT_MIN,
                    maximum=APPROVALS_LIMIT_MAX,
                )
                if "limit" in supplied
                else APPROVALS_LIMIT_DEFAULT
            )
        except strict_query.InvalidQuery as exc:
            raise errors.InvalidRequest(str(exc)) from exc
        approvals = await _workflows(request).pending_approvals(limit=limit)
        return JSONResponse(
            {"approvals": jsonable(approvals), "limit": limit},
            headers={"Cache-Control": "no-store"},
        )

    return await _admin_guard(run)


async def _decide(request: Request, run_id: str, decision: str) -> Response:
    async def run() -> Response:
        principal = await _admin(request, scope_map.ADMIN_WORKFLOWS_APPROVE)
        payload = await _body(request, WorkflowDecisionRequest)
        assert isinstance(payload, WorkflowDecisionRequest)
        identifier = _run_id(run_id)
        try:
            recorded = await _workflows(request).decide(
                run_id=identifier,
                step=payload.step,
                user_id=principal.user_id,
                decision=DECISIONS[decision],
            )
        except psycopg.Error as exc:
            _translate(exc)
            raise  # pragma: no cover -- `_translate` always raises
        return JSONResponse(
            {"run_id": str(identifier), "step": payload.step, "approval": recorded},
            headers={"Cache-Control": "no-store"},
        )

    return await _admin_guard(run)


@router.post(
    "/admin/workflows/runs/{run_id}/approve", openapi_extra=DOC_APPROVE, responses=RESP_APPROVE
)
async def approve(request: Request, run_id: str) -> Response:
    """WF-ADMIN-001. A human releases one parked write."""
    return await _decide(request, run_id, "approve")


@router.post(
    "/admin/workflows/runs/{run_id}/reject", openapi_extra=DOC_REJECT, responses=RESP_REJECT
)
async def reject(request: Request, run_id: str) -> Response:
    """WF-ADMIN-001. A rejection is a cancel (ADR 0230)."""
    return await _decide(request, run_id, "reject")


@router.get(
    "/admin/workflows/runs/{run_id}", openapi_extra=DOC_PROVENANCE, responses=RESP_PROVENANCE
)
async def read_provenance(request: Request, run_id: str) -> Response:
    """WF-PROV-001. The audit's reader for one run, under the audit's scope."""

    async def run() -> Response:
        await _admin(request, scope_map.ADMIN_AUDIT_READ)
        identifier = _run_id(run_id)
        try:
            document = await _workflows(request).provenance(run_id=identifier)
        except psycopg.Error as exc:
            _translate(exc)
            raise  # pragma: no cover -- `_translate` always raises
        return JSONResponse(jsonable(document), headers={"Cache-Control": "no-store"})

    return await _admin_guard(run)
