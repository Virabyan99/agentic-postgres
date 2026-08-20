"""A request carrying an `Origin` header is refused (ADR 0128).

**Not an allowlist. Any `Origin` at all.**

The agent plane is an agent API. No legitimate client is a browser, and `Origin`
is a header browsers attach and other clients do not — so its presence is itself
the signal, and refusing on presence is stricter than any list while needing no
configuration and having nothing to drift from.

**Why this exists as our own code.** FastMCP grew `host_origin_protection`,
`allowed_hosts` and `allowed_origins` after the version this repository pins.
Measured at **3.4.0** — ADR 0121's ceiling, because 3.4.1 cannot share a process
with this repository's FastAPI:

    http_app parameters: path, middleware, json_response, stateless_http,
                         transport, event_store, retry_interval

and all three are absent. Measured on the running server at that pin, a
cross-origin request is **processed and answered 200**; what a browser cannot do
is *read* the answer, because no `Access-Control-Allow-Origin` comes back. A
preflight gets **405**. So the practical protection today is the absence of a
CORS middleware, which is a property of the edge configuration rather than of
this runtime — and a protection that lives somewhere else is one this process
cannot state.

**Host is deliberately not checked here.** The router's `Host()` clause decides
which requests reach this container, derived from the project's domain, which
`naming.py` owns. Checking it again inside the image would need the domain as a
setting, and the failure mode of a wrong setting is a container that refuses
every request while looking configured.
"""

from __future__ import annotations

from typing import Any

#: The header whose presence is the refusal.
ORIGIN_HEADER = b"origin"

#: What a refused caller receives. `403`, not `401`: this is not an
#: authentication problem and offering a challenge would invite a browser to
#: retry with credentials, which is the flow being refused.
ORIGIN_REFUSED_STATUS = 403

#: The body. Short, fixed, and saying nothing about the surface behind it — a
#: caller that reached this check has not established it may learn anything
#: (ADR 0097).
ORIGIN_REFUSED_BODY = b'{"error":"origin_not_permitted"}'


class RefuseBrowserOrigins:
    """ASGI middleware. Refuses any HTTP request carrying `Origin`.

    Plain ASGI rather than a Starlette `BaseHTTPMiddleware` subclass, because
    this has to run **before** anything reads the body or builds a request
    object: the whole point is that a refused request costs nothing and reaches
    nothing.

    Non-HTTP scopes pass through untouched. There is no websocket surface here
    today, and a middleware that swallowed a lifespan message would break
    startup rather than protect anything.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        for name, _ in scope.get("headers") or ():
            if name.lower() == ORIGIN_HEADER:
                await _refuse(send)
                return

        await self.app(scope, receive, send)


async def _refuse(send: Any) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": ORIGIN_REFUSED_STATUS,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(ORIGIN_REFUSED_BODY)).encode("ascii")),
                # No `Access-Control-Allow-Origin`, deliberately. Echoing one
                # here would tell a browser the refusal is readable, which is
                # both untrue and the opposite of the intent.
            ],
        }
    )
    await send({"type": "http.response.body", "body": ORIGIN_REFUSED_BODY})
