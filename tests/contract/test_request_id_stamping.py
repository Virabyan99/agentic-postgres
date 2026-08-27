"""`OPS-LOG-001` — one id per HTTP request, flowing outward (ADR 0160).

**Behavioural, over a real ASGI transport.** D444's family is the standing
warning here: `AgentContextMiddleware` was a plain class for two runs and raised
`'AgentContextMiddleware' object is not callable` the first time a request
reached it, because every test had called `on_request` directly. So these drive
the middleware as ASGI — scope in, messages out — rather than calling its
methods.

`asyncio.run` in a sync test, which is this suite's convention
(`test_auth_hashing.py`, `test_mcp_authorization.py`). No async plugin is
installed and `--strict-markers` would refuse one's marker.

**D498 is closed here.** Session 9 proved the id propagates and never proved it
was *unique*: every offline test arranged a fixed id, so a mutation replacing
`uuid4()` with a constant left the whole suite green. Two tests below now fail.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

SERVICE = Path(__file__).resolve().parents[2] / "services" / "auth-api"
if str(SERVICE) not in sys.path:
    sys.path.insert(0, str(SERVICE))

from app.request_id import (  # noqa: E402
    HEADER,
    StampRequestId,
    current_request_id,
    mint,
)

pytestmark = [pytest.mark.contract, pytest.mark.p0]


def drive(app: Any, *, headers: list[tuple[bytes, bytes]] | None = None) -> dict[str, Any]:
    """One HTTP request through an ASGI app, returning what it sent."""

    async def run() -> dict[str, Any]:
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        scope = {"type": "http", "method": "GET", "path": "/", "headers": headers or []}
        await app(scope, receive, send)
        return {"start": next(m for m in sent if m["type"] == "http.response.start")}

    return asyncio.run(run())


def response_ids(start: dict[str, Any]) -> list[str]:
    return [
        value.decode("latin-1")
        for name, value in start.get("headers", [])
        if name.decode("latin-1").lower() == HEADER.lower()
    ]


def echo_app(seen: list[str | None]) -> Any:
    """An app that records the id visible to it, then answers 200."""

    async def app(scope: Any, receive: Any, send: Any) -> None:
        seen.append(current_request_id())
        await send({"type": "http.response.start", "status": 200, "headers": [(b"x-a", b"1")]})
        await send({"type": "http.response.body", "body": b"{}"})

    return app


# ---------------------------------------------------------------------------
# The outward flow
# ---------------------------------------------------------------------------


def test_the_response_carries_the_request_id() -> None:
    """The ingress leg, and the whole of what closes it.

    Measured against the locked Traefik in rig E: the shipped access-log policy
    keeps `downstream_X-Request-Id`, so a response header is sufficient and the
    edge needs no change at all.
    """
    seen: list[str | None] = []
    result = drive(StampRequestId(echo_app(seen)))
    ids = response_ids(result["start"])
    assert len(ids) == 1, f"expected exactly one {HEADER} on the response, got {ids}"
    assert ids[0] == seen[0], "the response header and the id the app saw are different values"


def test_the_application_can_read_the_id_that_will_be_stamped() -> None:
    """The id must exist *before* the app runs, or the audit row and the response
    header are two different values for one request."""
    seen: list[str | None] = []
    drive(StampRequestId(echo_app(seen)))
    assert seen and seen[0], "the app saw no request id"


def test_the_headers_the_application_set_are_preserved() -> None:
    """Appended, not assigned into. Replacing the list would drop whatever the
    application set — including `Content-Type`."""
    result = drive(StampRequestId(echo_app([])))
    names = {name.decode("latin-1") for name, _ in result["start"]["headers"]}
    assert "x-a" in names, "the stamp replaced the application's own headers"


# ---------------------------------------------------------------------------
# No caller value is trusted
# ---------------------------------------------------------------------------


def test_an_inbound_request_id_is_ignored_entirely() -> None:
    """ADR 0160, and the reason is in `_Held`'s own docstring: an id a caller
    chose would let one agent stamp its actions with another agent's, so an
    operator reading the trail by request would see the second agent's writes
    inside the first agent's request.

    D633 measured the other half of this family one run earlier: a
    caller-supplied `X-Request-Id` reaching an unguarded cast rolled the caller's
    own write back to zero rows.
    """
    chosen = "11111111-1111-1111-1111-111111111111"
    seen: list[str | None] = []
    result = drive(
        StampRequestId(echo_app(seen)),
        headers=[(HEADER.lower().encode(), chosen.encode())],
    )
    assert seen[0] != chosen, "the runtime adopted a caller's request id"
    assert response_ids(result["start"]) != [chosen], "a caller's id reached the response"


def test_a_hostile_inbound_value_changes_nothing() -> None:
    """Not a uuid, and not short. The runtime does not validate-then-adopt: it
    never reads the header, so there is nothing to validate and nothing to get
    wrong."""
    seen: list[str | None] = []
    drive(
        StampRequestId(echo_app(seen)),
        headers=[(HEADER.lower().encode(), b"'; DROP TABLE agent_audit; --" * 20)],
    )
    assert seen[0] and len(seen[0]) == 36, "the stamped id is not a plain uuid4"


# ---------------------------------------------------------------------------
# D498 — uniqueness, which Session 9 proved for nothing
# ---------------------------------------------------------------------------


def test_two_requests_get_two_different_ids() -> None:
    """**D498.** *"The id's propagation was proved and its uniqueness was not,
    because every offline test arranges a fixed id — a mutation replacing
    `uuid4()` with a constant left the whole suite green."*

    Two agents whose records share a request id are two agents an operator
    cannot tell apart, which is the same harm a caller-chosen id would do,
    arriving from inside instead of from outside.
    """
    seen: list[str | None] = []
    app = StampRequestId(echo_app(seen))
    drive(app)
    drive(app)
    assert seen[0] != seen[1], "two HTTP requests were given the same request id"


def test_minting_twice_gives_two_values() -> None:
    """The narrow form of the same claim, so a constant-returning `mint` fails
    even if the ASGI arms are ever removed."""
    assert mint() != mint()


# ---------------------------------------------------------------------------
# Lifetime
# ---------------------------------------------------------------------------


def test_the_id_does_not_survive_the_request() -> None:
    """`reset`, not `set(None)`. An id outliving its request is an id the next
    request would correlate itself with.

    **Observed inside the same context that set it**, and the first version of
    this test was not. It called `drive(...)` and then asserted
    `current_request_id() is None` from the test's own frame — but `asyncio.run`
    builds a fresh `Context` per call, so that assertion read a variable nothing
    had ever set. It passed whether or not the reset happened, and the Run 5
    battery caught it as a **survivor**: D374's shape, a test checking a string
    its target cannot affect.
    """
    after: list[str | None] = []

    async def run() -> None:
        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict[str, Any]) -> None:
            return None

        scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
        await StampRequestId(echo_app([]))(scope, receive, send)
        # Same coroutine, same context, immediately after the middleware
        # returned. This is the only vantage point from which the reset is
        # observable at all.
        after.append(current_request_id())

    asyncio.run(run())
    assert after == [None], f"the id outlived its request: {after}"


def test_a_non_http_scope_passes_through_untouched() -> None:
    """`RefuseBrowserOrigins`'s rule: a middleware that swallowed a lifespan
    message would break startup rather than protect anything."""
    delivered: list[Any] = []

    async def app(scope: Any, receive: Any, send: Any) -> None:
        delivered.append(scope["type"])

    async def run() -> None:
        async def receive() -> dict[str, Any]:
            return {"type": "lifespan.startup"}

        async def send(message: dict[str, Any]) -> None:
            return None

        await StampRequestId(app)({"type": "lifespan"}, receive, send)

    asyncio.run(run())
    assert delivered == ["lifespan"]


# ---------------------------------------------------------------------------
# Through the real applications, not just the middleware
# ---------------------------------------------------------------------------


def test_the_auth_application_stamps_a_real_response() -> None:
    """The middleware is wired, not merely written.

    D444's family is why this exists: `AgentContextMiddleware` was correct in
    isolation and uncallable in the pipeline for two runs, because every test
    called its method directly. So this drives `create_app` itself.

    An unmatched path answers 404 without touching the pool, which is what lets
    this run with no database and still exercise the real middleware stack.
    """
    from app import main as main_module

    result = drive(main_module.create_app("auth"))
    assert result["start"]["status"] == 404, "expected an unmatched path to 404"
    assert len(response_ids(result["start"])) == 1, "the auth app stamped no request id"


def test_the_storage_application_stamps_a_real_response() -> None:
    """The other mode of the same image (ADR 0101). One image, two modes, and a
    middleware added to one branch of an if/else would be a plane that logs and
    a plane that does not."""
    from app import main as main_module

    result = drive(main_module.create_app("storage"))
    assert len(response_ids(result["start"])) == 1, "the storage app stamped no request id"


def test_the_agent_plane_uses_the_id_the_response_will_carry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The correlation claim itself**, and the only test that joins the two ends.

    `OPS-LOG-001` is one id across ingress, API, agent and audit. Everything else
    here proves the response carries an id; this proves the agent plane records
    *that* id rather than a second one of its own. Without it, both halves could
    be individually correct and name different requests — which is exactly the
    state Session 9 shipped, with the audit row and the edge log uncorrelated.
    """
    from app import mcp_authorization

    monkeypatch.setattr(
        mcp_authorization, "resolve_agent_context", lambda base_url, token, request_id: request_id
    )

    resolved: list[str] = []

    async def app(scope: Any, receive: Any, send: Any) -> None:
        held = mcp_authorization._resolve("http://upstream", "token")
        resolved.append(held.request_id)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    result = drive(StampRequestId(app))
    assert resolved, "the agent plane resolved nothing"
    assert response_ids(result["start"]) == resolved, (
        "the agent plane minted its own id instead of using the one stamped for "
        "this request, so the audit row and Traefik's downstream_X-Request-Id "
        "name different requests"
    )


def test_create_app_still_returns_a_fastapi_application() -> None:
    """The first attempt at this run wrapped the app in plain ASGI and changed
    what `create_app` IS. `bin/app-contract.py` calls `.openapi()` on the result
    and six test modules read `.routes`; the compiled application contract is
    generated from the first."""
    from app import main as main_module

    application = main_module.create_app("auth")
    assert callable(getattr(application, "openapi", None)), "create_app no longer returns a FastAPI"
    assert getattr(application, "routes", None), "create_app's result has no routes"


def test_the_context_is_cleared_when_the_application_raises() -> None:
    """A failing request is the one somebody correlates. Nothing can be stamped
    on a response that was never started — but the ContextVar must still be
    reset, or the next request inherits an id that names a failure."""

    async def boom(scope: Any, receive: Any, send: Any) -> None:
        raise RuntimeError("boom")

    after: list[str | None] = []

    async def run() -> None:
        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict[str, Any]) -> None:
            return None

        scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
        with pytest.raises(RuntimeError):
            await StampRequestId(boom)(scope, receive, send)
        after.append(current_request_id())

    asyncio.run(run())
    assert after == [None], "the id outlived a failed request"
