"""Three routes for HUMAN administrators over the connectors (ADR 0236).

`workflow_admin_routes`' shape: every route calls `authenticate`, which refuses
an agent token before any scope is read, then requires its scope, and only
then reads a query or a body. So no agent -- the one a connector is bound to
among them -- can enable, disable or read a connector however it is
authorised.

* `GET /admin/connectors` under `admin_connectors:read` -- every connector with
  its binding, its counts, its last error token and up to `dead_limit` dead
  letters. **Never an endpoint, a payload or a key**: the database builds the
  document (`connector_status`) and it carries none of them.
* `POST /admin/connectors/{name}/enable` under `admin_connectors:write`, body
  `{"agent_id": uuid | null}` -- an inbound or scheduled connector binds an
  active agent whose stored scopes EQUAL its definition's; an outbound one
  needs an endpoint and no agent. The administrator is recorded as the one who
  enabled it.
* `POST /admin/connectors/{name}/disable` under `admin_connectors:write`, no
  body -- unbinds the agent and clears the schedule; pending deliveries are
  held, not sent.

**Every authority is the database's.** The refusals below are words the
definer functions raise, read from their messages for that one word and never
relayed -- `agent_scopes_differ`'s DETAIL names the scopes, and it stays in the
database's log.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from app import connector_signature, errors, openapi_docs, strict_query
from app import scopes as scope_map
from app.models import (
    AgentNotNeededResponse,
    BindingRefusedResponse,
    ConnectorChangedResponse,
    ConnectorEnableRequest,
    NoSuchConnectorResponse,
)
from app.routes import _body, _guard
from app.workflow_admin_routes import _admin
from app.workflow_routes import jsonable

router = APIRouter()

NOT_FOUND_SQLSTATE = "PT404"
CONFLICT_SQLSTATE = "PT409"
INVALID_SQLSTATE = "PT422"

#: `connector_enable`'s PT409 words, each answered as itself.
BINDING_CONFLICTS = (
    "agent_not_active",
    "agent_already_bound",
    "agent_scopes_differ",
    "no_endpoint",
)

#: `connector_enable`'s one PT422 word: an agent named for an outbound connector.
AGENT_NOT_NEEDED_MARKER = "agent_not_needed"

#: `GET /admin/connectors`' one parameter: `connector_status`'s own 1..20,
#: restated as the route's refusal so a caller is told the range rather than
#: handed a translated PT422.
STATUS_QUERY_PARAMETERS: tuple[str, ...] = ("dead_limit",)
DEAD_LIMIT_MIN = 1
DEAD_LIMIT_MAX = 20
DEAD_LIMIT_DEFAULT = 20

DOC_STATUS = openapi_docs.described(
    summary="List every connector, its binding, its counts and its dead letters",
    description=(
        "Requires `admin_connectors:read` and an ACCESS token; an agent token is refused "
        "before the scope is read. Each connector: its name, version and kind; whether it is "
        "enabled and by whom; the bound agent and the binding as it stands NOW "
        "(`ok`, `unbound`, `agent_not_active`, `agent_scopes_differ`, or `not_applicable` "
        "for an outbound one); `endpoint_declared`; the pending, delivered and dead counts, "
        "the oldest pending delivery's age, the last error token, the receipts, and up to "
        "`dead_limit` dead letters by event and token. **Never an endpoint, a payload or a "
        "key.**"
    ),
    query_parameters=[
        openapi_docs.query_parameter(
            "dead_limit",
            schema={
                "type": "integer",
                "minimum": DEAD_LIMIT_MIN,
                "maximum": DEAD_LIMIT_MAX,
                "default": DEAD_LIMIT_DEFAULT,
            },
            description=(
                f"Dead letters per connector, {DEAD_LIMIT_MIN}-{DEAD_LIMIT_MAX}. Outside the "
                "range is refused with 422; it is never clamped."
            ),
        )
    ],
)
RESP_STATUS = {
    200: openapi_docs.ok("Every connector, by name."),
    401: openapi_docs.UNAUTHENTICATED,
    403: openapi_docs.UNAUTHORIZED,
    422: openapi_docs.INVALID,
}

_CHANGE_REFUSALS: dict[int | str, dict[str, Any]] = {
    401: openapi_docs.UNAUTHENTICATED,
    403: openapi_docs.UNAUTHORIZED,
    404: {"model": NoSuchConnectorResponse, "description": "No connector of that name."},
}

DOC_ENABLE = openapi_docs.described(
    summary="Enable one connector, binding the agent it acts as",
    description=(
        "Requires `admin_connectors:write`. An inbound or scheduled connector starts runs AS "
        "the agent named here, which must be active, bound to no other connector, and hold "
        "EXACTLY its definition's scopes -- no fewer, and no more. An outbound connector acts "
        "as nobody: name no agent, and it must have an endpoint in the project manifest. The "
        "administrator is recorded as the one who enabled it."
    ),
    request_model=ConnectorEnableRequest,
)
RESP_ENABLE = {
    200: openapi_docs.ok("The connector is enabled.", ConnectorChangedResponse),
    400: openapi_docs.MALFORMED,
    **_CHANGE_REFUSALS,
    409: {
        "model": BindingRefusedResponse,
        "description": (
            "`agent_not_active` (no such agent, a revoked one, or none named for a connector "
            "that needs one), `agent_already_bound` (another connector acts as it), "
            "`agent_scopes_differ` (its stored scopes are not exactly the definition's) or "
            "`no_endpoint` (an outbound connector the manifest gives no endpoint)."
        ),
    },
    422: {
        "model": AgentNotNeededResponse,
        "description": "An agent was named for an outbound connector, which acts as nobody.",
    },
}

DOC_DISABLE = openapi_docs.described(
    summary="Disable one connector",
    description=(
        "Requires `admin_connectors:write`. Takes no body. Unbinds the agent and clears the "
        "schedule; deliveries already pending are held, not sent, until it is enabled again."
    ),
)
RESP_DISABLE = {
    200: openapi_docs.ok("The connector is disabled.", ConnectorChangedResponse),
    400: openapi_docs.MALFORMED,
    **_CHANGE_REFUSALS,
}


def _connectors(request: Request) -> Any:
    """The connector repository this application built at startup."""
    return request.app.state.connectors


def _translate(exc: psycopg.Error) -> None:
    """`connector_enable`/`connector_disable`'s refusals, as fixed words."""
    sqlstate = getattr(exc.diag, "sqlstate", None)
    message = str(exc)
    if sqlstate == NOT_FOUND_SQLSTATE:
        raise errors.ConnectorRefused(404, errors.NO_SUCH_CONNECTOR) from exc
    if sqlstate == CONFLICT_SQLSTATE:
        for word in BINDING_CONFLICTS:
            if word in message:
                raise errors.ConnectorRefused(409, word) from exc
    if sqlstate == INVALID_SQLSTATE and AGENT_NOT_NEEDED_MARKER in message:
        raise errors.ConnectorRefused(422, AGENT_NOT_NEEDED_MARKER) from exc
    raise exc


async def _connector_guard(handler: Any) -> Response:
    """`_guard`, with the connector surface's fixed refusals around it."""

    async def run() -> Response:
        try:
            return await handler()
        except errors.ConnectorRefused as refusal:
            return errors.connector_refused(refusal)

    return await _guard(run)


def _name(value: str) -> str:
    """A name the column could not hold is the same 404 a missing one gets."""
    if connector_signature.NAME.fullmatch(value) is None:
        raise errors.ConnectorRefused(404, errors.NO_SUCH_CONNECTOR)
    return value


@router.get("/admin/connectors", openapi_extra=DOC_STATUS, responses=RESP_STATUS)
async def list_connectors(request: Request) -> Response:
    """CONN-ADMIN-001. Authenticate, require the scope, THEN parse the query."""

    async def run() -> Response:
        await _admin(request, scope_map.ADMIN_CONNECTORS_READ)
        try:
            supplied = strict_query.parse(
                request.query_params.multi_items(), STATUS_QUERY_PARAMETERS
            )
            dead_limit = (
                strict_query.as_bounded_int(
                    "dead_limit",
                    supplied["dead_limit"],
                    minimum=DEAD_LIMIT_MIN,
                    maximum=DEAD_LIMIT_MAX,
                )
                if "dead_limit" in supplied
                else DEAD_LIMIT_DEFAULT
            )
        except strict_query.InvalidQuery as exc:
            raise errors.InvalidRequest(str(exc)) from exc
        document = await _connectors(request).status(dead_limit=dead_limit)
        return JSONResponse(
            {**jsonable(document), "dead_limit": dead_limit},
            headers={"Cache-Control": "no-store"},
        )

    return await _connector_guard(run)


@router.post("/admin/connectors/{name}/enable", openapi_extra=DOC_ENABLE, responses=RESP_ENABLE)
async def enable(request: Request, name: str) -> Response:
    """CONN-ADMIN-001. Bind, or refuse with one of the database's words."""

    async def run() -> Response:
        principal = await _admin(request, scope_map.ADMIN_CONNECTORS_WRITE)
        payload = await _body(request, ConnectorEnableRequest)
        assert isinstance(payload, ConnectorEnableRequest)
        connector = _name(name)
        agent_id: UUID | None = payload.agent_id
        try:
            outcome = await _connectors(request).enable(
                name=connector, agent_id=agent_id, user_id=principal.user_id
            )
        except psycopg.Error as exc:
            _translate(exc)
            raise  # pragma: no cover -- `_translate` always raises
        return JSONResponse(
            {"name": connector, "outcome": outcome}, headers={"Cache-Control": "no-store"}
        )

    return await _connector_guard(run)


@router.post("/admin/connectors/{name}/disable", openapi_extra=DOC_DISABLE, responses=RESP_DISABLE)
async def disable(request: Request, name: str) -> Response:
    """CONN-ADMIN-001. Unbind and stop; a body is refused, never ignored."""

    async def run() -> Response:
        principal = await _admin(request, scope_map.ADMIN_CONNECTORS_WRITE)
        if (await request.body()).strip():
            # A body this route would ignore is a request whose sender believes
            # it said something. Refused, in the house's malformed shape.
            raise errors.MalformedRequest("disable takes no body")
        connector = _name(name)
        try:
            outcome = await _connectors(request).disable(name=connector, user_id=principal.user_id)
        except psycopg.Error as exc:
            _translate(exc)
            raise  # pragma: no cover -- `_translate` always raises
        return JSONResponse(
            {"name": connector, "outcome": outcome}, headers={"Cache-Control": "no-store"}
        )

    return await _connector_guard(run)
