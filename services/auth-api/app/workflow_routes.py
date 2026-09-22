"""Three routes, behind a second authenticator, for AGENT tokens (ADR 0229).

**ADR 0114 said this API is human-only, and this amends it by naming the
exception rather than by loosening a check.** `authenticate` still refuses an
agent token -- `test_authenticate_still_refuses_an_agent_token` is the control
-- and these three routes call `authenticate_agent`, which refuses an access
token. The two `token_use` constants are disjoint, so which surface a token
reaches is decided by the claim it was minted with and not by which handler
happened to be mounted.

**Every authority is the database's.** This module holds no ownership rule and
no scope arithmetic: `workflow_enqueue` compares the definition's
`required_scopes` against the AGENT'S STORED scopes, and `workflow_cancel` and
`workflow_run_status` match on `agent_id` and raise the same `PT404` for a
missing run and for another agent's. What is here is the translation of those
refusals into HTTP, and nothing else -- which is what makes the rules
unbypassable by this code rather than merely unbypassed by it.

**No error body carries an argument, a result or a definition name.** A 404
says `no_such_workflow` and a 403 says `scope_not_held`, both of them fixed
documents. A message naming the definition the caller asked for would make a
404 an existence oracle for definitions installed on a deployment the caller
cannot otherwise read (ADR 0141's rule for a denial, applied to a run).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import psycopg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from app import errors, openapi_docs
from app.models import (
    NoSuchWorkflowResponse,
    ScopeNotHeldResponse,
    WorkflowRunRequest,
    WorkflowRunResponse,
)
from app.routes import _body, _guard, _service

router = APIRouter()

#: The errcode the substrate raises for *no such definition*, *no such run* and
#: *another agent's run*. One code, one answer.
NOT_FOUND_SQLSTATE = "PT404"

#: The errcode for a refusal of authority. The substrate raises it for a
#: revoked agent AND for one whose scopes do not cover the definition, and the
#: two are told apart by the message the function itself chose -- which is the
#: only place the distinction exists.
FORBIDDEN_SQLSTATE = "PT403"

#: The word `workflow_enqueue` raises when the agent's stored scopes do not
#: cover the definition's. One of `mcp_errors.DENIAL_REASONS`' nine boundaries,
#: so the caller reads vocabulary it has seen before.
SCOPE_NOT_HELD_MARKER = "scope_not_held"

DOC_START_RUN = openapi_docs.described(
    summary="Start a run of an installed workflow definition",
    description=(
        "Requires an AGENT token, not an access token. The run is started as that agent "
        "and the agent's STORED scopes are what authorise it -- not the token's -- so an "
        "agent narrowed since its token was minted is refused. A definition this "
        "deployment has not installed is `no_such_workflow`."
    ),
    request_model=WorkflowRunRequest,
)
RESP_START_RUN = {
    201: openapi_docs.created("The run was enqueued.", WorkflowRunResponse),
    400: openapi_docs.MALFORMED,
    401: openapi_docs.UNAUTHENTICATED,
    403: {
        "model": ScopeNotHeldResponse,
        "description": (
            "The agent's record does not carry every scope the definition's steps "
            "require. Checked against the record, never against the token."
        ),
    },
    404: {
        "model": NoSuchWorkflowResponse,
        "description": ("No definition of that name and version is installed on this deployment."),
    },
}

DOC_READ_RUN = openapi_docs.described(
    summary="Read one run and every step of it",
    description=(
        "The agent's own run, whole: its status, the definition and version it is a run "
        "of, the lock digest `validate` compiled against, and each step's position, name, "
        "status, attempt, outcome and request id. Another agent's run is the same 404 a "
        "missing one gets."
    ),
)
RESP_READ_RUN = {
    200: openapi_docs.ok("The run and its steps."),
    401: openapi_docs.UNAUTHENTICATED,
    404: {
        "model": NoSuchWorkflowResponse,
        "description": "No such run, or a run belonging to another agent. One answer.",
    },
}

DOC_CANCEL_RUN = openapi_docs.described(
    summary="Ask for a run to stop at its next step boundary",
    description=(
        "A queued run is cancelled at once; a running one records an intent the next "
        "claim honours, because a tool call already upstream cannot be recalled. A run "
        "that has already finished is returned unchanged rather than refused."
    ),
)
RESP_CANCEL_RUN = {
    200: openapi_docs.ok("The run's status after the request.", WorkflowRunResponse),
    401: openapi_docs.UNAUTHENTICATED,
    404: {
        "model": NoSuchWorkflowResponse,
        "description": "No such run, or a run belonging to another agent. One answer.",
    },
}


def _workflows(request: Request) -> Any:
    """The workflow repository this application built at startup."""
    return request.app.state.workflows


def _translate(exc: psycopg.Error) -> None:
    """The substrate's errcode, translated -- never relayed (ADR 0139, D433).

    Anything this does not recognise is re-raised, so an unexpected database
    error reaches the application's own handler as a 500 rather than being
    reported to an agent as a 404 about its own run.
    """
    sqlstate = getattr(exc.diag, "sqlstate", None)
    if sqlstate == NOT_FOUND_SQLSTATE:
        raise errors.NoSuchWorkflow from exc
    if sqlstate == FORBIDDEN_SQLSTATE:
        # The message is the FUNCTION's own, written in the migration, and is
        # read here for one word. It never reaches the caller: the response is
        # a fixed document either way, and this only decides which of the two.
        if SCOPE_NOT_HELD_MARKER in str(exc):
            raise errors.ScopeNotHeld from exc
        raise errors.AuthenticationFailed("the agent is no longer active") from exc
    raise exc


async def _agent(request: Request) -> Any:
    return await _service(request).authenticate_agent(request.headers.get("authorization"))


async def _workflow_guard(handler: Any) -> Response:
    """`_guard`'s two workflow outcomes, wrapped around `_guard`'s own.

    Layered rather than merged into `routes._guard`, because the two surfaces
    answer different questions: `no_such_workflow` has no meaning on
    `/auth/login`, and a route that could return it there would be a route
    whose error vocabulary is wider than its subject.
    """

    async def run() -> Response:
        try:
            return await handler()
        except errors.NoSuchWorkflow:
            return errors.no_such_workflow()
        except errors.ScopeNotHeld:
            return errors.scope_not_held()

    return await _guard(run)


@router.post("/workflows/runs", openapi_extra=DOC_START_RUN, responses=RESP_START_RUN)
async def start_run(request: Request) -> Response:
    """WF-ROUTE-001. Enqueue a run as the token's agent."""

    async def run() -> Response:
        payload = await _body(request, WorkflowRunRequest)
        assert isinstance(payload, WorkflowRunRequest)
        principal = await _agent(request)
        try:
            run_id = await _workflows(request).enqueue(
                agent_id=principal.agent_id,
                name=payload.name,
                version=payload.version,
                # Serialised HERE rather than in the repository, so there is one
                # serializer for a document that crosses the boundary as jsonb.
                run_input=json.dumps(payload.input, default=str),
                dry_run=payload.dry_run,
            )
        except psycopg.Error as exc:
            _translate(exc)
            raise  # pragma: no cover -- `_translate` always raises
        return JSONResponse(
            {"run_id": str(run_id), "status": "queued"},
            status_code=201,
            headers={"Cache-Control": "no-store"},
        )

    return await _workflow_guard(run)


@router.get("/workflows/runs/{run_id}", openapi_extra=DOC_READ_RUN, responses=RESP_READ_RUN)
async def read_run(request: Request, run_id: str) -> Response:
    """WF-ROUTE-001. The agent's own run, or the one 404."""

    async def run() -> Response:
        principal = await _agent(request)
        try:
            identifier = UUID(run_id)
        except ValueError as exc:
            # A malformed id is the SAME answer a run that does not exist gets.
            # A 400 here would tell a caller that a well-formed id it cannot
            # read is well formed, which is half of an existence oracle.
            raise errors.NoSuchWorkflow from exc
        try:
            document = await _workflows(request).status(
                run_id=identifier, agent_id=principal.agent_id
            )
        except psycopg.Error as exc:
            _translate(exc)
            raise  # pragma: no cover -- `_translate` always raises
        return JSONResponse(jsonable(document), headers={"Cache-Control": "no-store"})

    return await _workflow_guard(run)


@router.post(
    "/workflows/runs/{run_id}/cancel", openapi_extra=DOC_CANCEL_RUN, responses=RESP_CANCEL_RUN
)
async def cancel_run(request: Request, run_id: str) -> Response:
    """WF-ROUTE-001. Record an intent the next claim honours."""

    async def run() -> Response:
        principal = await _agent(request)
        try:
            identifier = UUID(run_id)
        except ValueError as exc:
            raise errors.NoSuchWorkflow from exc
        try:
            status = await _workflows(request).cancel(
                run_id=identifier, agent_id=principal.agent_id
            )
        except psycopg.Error as exc:
            _translate(exc)
            raise  # pragma: no cover -- `_translate` always raises
        return JSONResponse(
            {"run_id": run_id, "status": status}, headers={"Cache-Control": "no-store"}
        )

    return await _workflow_guard(run)


def jsonable(document: Any) -> Any:
    """Render what `jsonb_build_object` produced into what JSONResponse takes.

    psycopg returns `jsonb` as Python objects already, but a `datetime` reaches
    here through no path this module controls -- the document is built by the
    database and its shape is the migration's. `default=str` in one place,
    rather than a converter per field, so a field added to the substrate's
    document does not need a change here to be serialisable.
    """
    return json.loads(json.dumps(document, default=str))
