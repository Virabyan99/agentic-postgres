"""One request id per HTTP request, minted here and stamped on the way out.

`OPS-LOG-001`, and ADR 0160 is the decision: **the id flows outward, and no
caller value is ever trusted.** Nothing in this module reads an inbound
`X-Request-Id`. An id a caller chose would let one agent stamp its actions with
another agent's id, and an operator reading the audit trail by request would see
a second agent's writes inside a first agent's request.

What closes the ingress leg instead is the *response*. Measured against the
locked `traefik:v3.7` digest (rig E, Session 11 Run 5), Traefik's access log
emits three namespaces and the shipped policy keeps two of them:

    request_X-Request-Id      the client's, if it sent one   -- used for nothing
    origin_X-Request-Id       the response, as the origin sent it
    downstream_X-Request-Id   the response, as sent to the client

So stamping the response is sufficient, and the edge needs no change. D141
deferred that measurement in Session 5 and nothing had made it since.

**Plain ASGI, not `BaseHTTPMiddleware`**, for `RefuseBrowserOrigins`'s reason:
this has to wrap the finished application at the transport boundary, which is the
only layer that corresponds one-to-one with an HTTP request. FastMCP's own
middleware list runs per MCP *message*, which is the wrong unit.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Any

__all__ = ["HEADER", "StampRequestId", "current_request_id", "mint"]

#: The wire spelling. Traefik matches header names case-insensitively -- its
#: config says `X-Request-ID` and it logged `X-Request-Id` -- measured rather
#: than assumed, because a name written one way and matched another is exactly
#: how a log field goes quietly missing.
HEADER = "X-Request-Id"

_CURRENT: ContextVar[str | None] = ContextVar("apg_request_id", default=None)


def mint() -> str:
    """A fresh id.

    `uuid4` and nothing derived from the request: two requests arriving in the
    same microsecond from the same caller must not collide, and anything derived
    from caller-visible state is something a caller can aim at.
    """
    return str(uuid.uuid4())


def current_request_id() -> str | None:
    """The id stamped for this HTTP request, or None outside one.

    `None` rather than minting on read. A caller that mints here would produce a
    *second* id for the same request and correlate nothing -- which is the
    failure this module exists to prevent, arriving through its own front door.
    """
    return _CURRENT.get()


class StampRequestId:
    """Mint one id per HTTP request; put it on the response.

    Non-HTTP scopes pass through untouched, for `RefuseBrowserOrigins`'s reason:
    a middleware that swallowed a lifespan message would break startup rather
    than protect anything.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request_id = mint()
        reset = _CURRENT.set(request_id)
        encoded = request_id.encode("latin-1")

        async def send_with_id(message: Any) -> None:
            if message.get("type") == "http.response.start":
                # Appended rather than assigned into: the headers list is the
                # application's, and replacing it would drop whatever it set.
                # A duplicate cannot arise -- nothing else in this process emits
                # this header, and the id is not read from the request.
                message.setdefault("headers", [])
                message["headers"].append((HEADER.lower().encode("latin-1"), encoded))
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            # `reset`, not `set(None)`: reset restores whatever this context had
            # before, which is the only correct answer under nesting -- and it is
            # what makes "never across requests" a property of the mechanism
            # rather than of this function remembering to clear up.
            _CURRENT.reset(reset)
