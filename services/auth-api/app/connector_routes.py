"""The inbound connector route: a signature over the delivery before anything else.

`POST /connectors/{name}` (ADR 0237). **No authenticator**: the caller is an
outside system holding ONE connector's derived key, not a subject of this
service, so there is no token to read and no scope to require. What stands in
for both is the signature, and the whole of this module is the ORDER in which
it is checked:

1. the name matches the column's own pattern, else 404 `no_such_connector`;
2. the connector master was read at start, else 404 -- a deployment without
   the facility has no connectors to name;
3. the raw body is at most `strict_json.MAX_BODY_BYTES`, else 413;
4. `X-Apg-Delivery` is a canonical uuid, `X-Apg-Signature` parses, its time is
   inside the window and its HMAC -- under the key derived for THIS name, over
   the time, the delivery id and the raw bytes -- matches, else ONE 401
   `signature_invalid` for every cause;
5. only now is the body parsed, strictly, else 400;
6. only now is the database reached: the declaration (`connector_inbound`), the
   body checked against it (422, naming a declared member), and the one
   transaction that records the receipt and enqueues the run
   (`connector_accept`).

**Nothing before step 6 touches the repository**, and a proof drives the route
with one that raises on any call. A signature checked after a read would make
every unauthenticated request a database round trip, and a body parsed before
it would make every unauthenticated request a parse.

**Every authority after the signature is the database's** (`workflow_routes`'
rule): which connector is enabled, which agent it is bound to, whether that
agent still holds exactly the definition's scopes, and whether this delivery id
was accepted before. The module translates those refusals into fixed words and
relays nothing the database said. The run starts as the BOUND agent; the
request names no identity at all.

The one log line per request is `StructuredRequestLog`'s: the route template,
the status and the time -- never the path's name, a header or the body.
"""

from __future__ import annotations

import time
from uuid import UUID

import psycopg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from app import connector_body, connector_signature, errors, strict_json
from app.models import (
    BodyNotPermittedResponse,
    BodyTooLargeResponse,
    ConnectorAcceptedResponse,
    DeliveryRefusedResponse,
    MalformedRequestResponse,
    NoSuchConnectorResponse,
    SignatureInvalidResponse,
)

router = APIRouter()

DELIVERY_HEADER = "X-Apg-Delivery"
SIGNATURE_HEADER = "X-Apg-Signature"

NOT_FOUND_SQLSTATE = "PT404"
FORBIDDEN_SQLSTATE = "PT403"
CONFLICT_SQLSTATE = "PT409"

#: The words `connector_accept` raises under PT409, each read from the
#: function's own message and answered as itself.
ACCEPT_CONFLICTS = ("delivery_replayed", "connector_disabled", "agent_scopes_differ")

#: `workflow_enqueue`'s PT403 word when the bound agent's scopes no longer
#: cover the definition -- the agent lost a scope after it was bound. The
#: sender is told what the status document would say: `agent_scopes_differ`.
SCOPE_NOT_HELD_MARKER = "scope_not_held"

DOC_ACCEPT = {
    "summary": "Deliver one signed request to an inbound connector",
    "description": (
        "No bearer token: the request is authenticated by `X-Apg-Signature`, an HMAC-SHA256 "
        "under the connector's own key over `<t>.<delivery id>.<raw body>`, inside 300 "
        "seconds of `t` (ADR 0237). Every signature failure is the same 401. Only after the "
        "signature holds is the body parsed and checked against the connector's closed "
        "declaration, and a run of its definition started as the agent an administrator "
        "bound to it, with the body as the run's input. A delivery id is accepted once: a "
        "retry of the same id is `delivery_replayed` and starts nothing."
    ),
    "parameters": [
        {
            "name": DELIVERY_HEADER,
            "in": "header",
            "required": True,
            "schema": {"type": "string", "format": "uuid"},
            "description": "The sender's id for this delivery, canonical lowercase. Signed.",
        },
        {
            "name": SIGNATURE_HEADER,
            "in": "header",
            "required": True,
            "schema": {"type": "string", "pattern": "^t=[0-9]{1,12},v1=[0-9a-f]{64}$"},
            "description": "`t=<unix seconds>,v1=<64 lowercase hex>`.",
        },
    ],
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "description": (
                        "The connector's declared members and nothing else, at most 16 "
                        "KiB. Becomes the run's input."
                    ),
                }
            }
        },
    },
}
RESP_ACCEPT = {
    202: {"model": ConnectorAcceptedResponse, "description": "The run was enqueued."},
    400: {
        "model": MalformedRequestResponse,
        "description": "Signed, and not a JSON object: refused before the database.",
    },
    401: {
        "model": SignatureInvalidResponse,
        "description": "Any signature failure. One answer for every cause.",
    },
    404: {
        "model": NoSuchConnectorResponse,
        "description": "No inbound connector of that name, or no connectors on this deployment.",
    },
    409: {
        "model": DeliveryRefusedResponse,
        "description": "Signed and refused: replayed, disabled, or the bound agent changed.",
    },
    413: {"model": BodyTooLargeResponse, "description": "The body is above 16 KiB."},
    422: {
        "model": BodyNotPermittedResponse,
        "description": "Outside the connector's declaration, naming the declared member.",
    },
}


def _refuse(status: int, word: str, **extra: str | None) -> Response:
    return errors.connector_refused(errors.ConnectorRefused(status, word, **extra))


def _canonical_delivery(value: str | None) -> str | None:
    """The delivery id when it is a uuid in canonical lowercase form, else None.

    Canonical, because the id is inside the signed bytes as sent and is the
    receipt's key as parsed: two spellings of one uuid would be two signatures
    over one receipt.
    """
    if value is None:
        return None
    try:
        parsed = UUID(value)
    except ValueError:
        return None
    return value if str(parsed) == value else None


def _accept_refusal(exc: psycopg.Error) -> Response:
    """`connector_inbound`/`connector_accept`'s refusals, as fixed words."""
    sqlstate = getattr(exc.diag, "sqlstate", None)
    message = str(exc)
    if sqlstate == NOT_FOUND_SQLSTATE:
        return _refuse(404, errors.NO_SUCH_CONNECTOR)
    if sqlstate == CONFLICT_SQLSTATE:
        for word in ACCEPT_CONFLICTS:
            if word in message:
                return _refuse(409, word)
    if sqlstate == FORBIDDEN_SQLSTATE:
        # `workflow_enqueue`'s two refusals of authority: the agent's scopes
        # stopped covering the definition, or the agent is no longer active.
        if SCOPE_NOT_HELD_MARKER in message:
            return _refuse(409, "agent_scopes_differ")
        return _refuse(409, "agent_not_active")
    raise exc


@router.post(
    "/connectors/{name}",
    status_code=202,
    openapi_extra=DOC_ACCEPT,
    responses=RESP_ACCEPT,
)
async def accept(request: Request, name: str) -> Response:
    """CONN-IN-001. The signature, then the body, then the database -- in that order."""
    # (1) and (2): nothing to name, one answer.
    if connector_signature.NAME.fullmatch(name) is None:
        return _refuse(404, errors.NO_SUCH_CONNECTOR)
    master = getattr(request.app.state, "connector_key", None)
    if master is None:
        return _refuse(404, errors.NO_SUCH_CONNECTOR)

    # (3) The bound on the raw bytes, before any HMAC is computed over them.
    raw = await request.body()
    if len(raw) > strict_json.MAX_BODY_BYTES:
        return _refuse(413, "body_too_large")

    # (4) One answer for every cause.
    delivery = _canonical_delivery(request.headers.get(DELIVERY_HEADER))
    if delivery is None or not connector_signature.verify(
        connector_signature.derive(master, name),
        request.headers.get(SIGNATURE_HEADER),
        delivery,
        raw,
        now=int(time.time()),
    ):
        return _refuse(401, errors.SIGNATURE_INVALID)

    # (5) Only a signed body is parsed.
    try:
        body = strict_json.parse_object(raw)
    except strict_json.MalformedBody:
        return errors.malformed()

    # (6) Only a signed, parsed body reaches the database.
    connectors = request.app.state.connectors
    try:
        connector = await connectors.inbound(name=name)
    except psycopg.Error as exc:
        return _accept_refusal(exc)
    verdict = connector_body.check(connector.get("body_declaration") or {}, body)
    if verdict is not None:
        reason, _, member = verdict.partition(":")
        return _refuse(422, "body_not_permitted", reason=reason, member=member or None)
    try:
        run_id = await connectors.accept(name=name, delivery_id=UUID(delivery), body=body)
    except psycopg.Error as exc:
        return _accept_refusal(exc)
    return JSONResponse(
        {"run_id": str(run_id), "status": "queued"},
        status_code=202,
        headers={"Cache-Control": "no-store"},
    )
