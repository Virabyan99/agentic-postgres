"""The agent plane's authorization path (Session 8, Run 5).

ADR 0125. Three properties, and each is here because something measured says it
would otherwise be assumed:

1. **The caller's own token goes upstream, unchanged, and nothing else does.**
   No re-signing, no service token, no header naming a role, a subject or an
   owner. Asserted on the request this code actually builds.

2. **Exactly one row is a context.** Zero rows is a refusal, not an empty
   context -- measured against a live PostgREST, where the pre-request hook
   refuses a stale agent with `AP401` before the function is entered, so the
   zero-row branch the migration's comment describes is unreachable and a 200
   with no rows would mean something else entirely.

3. **The context cannot outlive its request.** Measured: a `ContextVar` reset in
   a `finally` leaked 0 of 12 concurrent requests, and a module-level dict
   leaked 11 of 12 -- while being correct on every sequential one. The
   concurrency arm below is the one that distinguishes them.
"""

from __future__ import annotations

import asyncio
import io
import json
import urllib.error
from typing import Any

import pytest

from app import mcp_authorization, mcp_upstream
from app import settings as settings_module
from app.mcp_authorization import (
    AgentContextMiddleware,
    current_agent_context,
    fingerprint,
)
from app.mcp_upstream import AgentContext, UpstreamRefusal, parse_agent_context

pytestmark = [pytest.mark.contract, pytest.mark.p0]

BASE = "http://postgrest:3000"
OWNER = "aaaaaaaa-0000-4000-8000-000000000001"
AGENT = "cbd44ca3-853c-4de4-8f49-a78658c73b69"


def _row(**overrides: Any) -> dict[str, Any]:
    """One row, shaped exactly as the live PostgREST returned it (Rig L, M1)."""
    row = {
        "agent_id": AGENT,
        "role_name": "apg_fixture_alpha_dev_agent_reader",
        "scopes": ["meta:read", "notes:read", "tasks:read"],
        "authz_version": 1,
        "owner_id": OWNER,
    }
    row.update(overrides)
    return row


def _body(*rows: dict[str, Any]) -> bytes:
    return json.dumps(list(rows)).encode("utf-8")


# ---------------------------------------------------------------------------
# the response contract
# ---------------------------------------------------------------------------


def test_one_row_is_a_context() -> None:
    """The shape the live service returns, parsed into the shape ADR 0117 needs."""
    context = parse_agent_context(200, _body(_row()))

    assert context == AgentContext(
        agent_id=AGENT,
        role_name="apg_fixture_alpha_dev_agent_reader",
        scopes=("meta:read", "notes:read", "tasks:read"),
        authz_version=1,
        owner_id=OWNER,
    )


@pytest.mark.parametrize(
    ("status", "body", "why"),
    [
        (
            200,
            _body(),
            "zero rows: the hook refuses a stale agent first, so this is not 'no agent'",
        ),
        (200, _body(_row(), _row()), "two rows cannot be one caller's context"),
        (200, b"{}", "an object is not the array PostgREST returns"),
        (200, b"not json", "a body that is not JSON at all"),
        (401, _body(_row()), "a refusal, even carrying a plausible body"),
        (403, b"", "the human-token refusal measured at 403 with 42501"),
        (500, b"", "an upstream fault"),
    ],
)
def test_everything_that_is_not_exactly_one_row_is_a_refusal(
    status: int, body: bytes, why: str
) -> None:
    """No branch produces an empty or partial context.

    The 200-with-zero-rows arm is the one that matters. It would be the easy
    thing to treat as "not an agent" and continue -- which would hand a tool an
    agent with no scopes and no owner, from a state the product does not
    actually produce.
    """
    with pytest.raises(UpstreamRefusal):
        parse_agent_context(status, body)


def test_a_good_response_is_accepted_by_the_same_function() -> None:
    """**The control for the refusals above.**

    Without it, a `parse_agent_context` that raised unconditionally would pass
    all seven.
    """
    assert parse_agent_context(200, _body(_row())).owner_id == OWNER


@pytest.mark.parametrize(
    ("override", "why"),
    [
        (
            {"owner_id": None},
            "None reaches ADR 0117's identity decision and compares equal to nothing",
        ),
        ({"owner_id": "  "}, "blank is not an identity"),
        ({"agent_id": 7}, "not a string"),
        ({"role_name": ""}, "empty role"),
        ({"scopes": "meta:read"}, "a string is not an array of scopes"),
        ({"scopes": [1, 2]}, "not strings"),
        ({"authz_version": "1"}, "not an integer"),
        ({"authz_version": True}, "bool is an int in Python and would compare equal to 1"),
    ],
)
def test_a_malformed_row_is_refused(override: dict[str, Any], why: str) -> None:
    with pytest.raises(UpstreamRefusal):
        parse_agent_context(200, _body(_row(**override)))


def test_a_row_missing_a_member_is_refused() -> None:
    row = _row()
    del row["owner_id"]

    with pytest.raises(UpstreamRefusal, match="missing"):
        parse_agent_context(200, _body(row))


# ---------------------------------------------------------------------------
# no confused deputy
# ---------------------------------------------------------------------------


class _Recorder:
    """Captures the request this code builds, without a socket.

    **A 4xx or 5xx is RAISED, not returned**, because that is what `urlopen`
    does. The first version of this class returned a 403 as an ordinary response,
    which urllib never produces -- so `resolve_agent_context`'s `HTTPError`
    branch, the one every real refusal takes, was never executed by any test.
    Run 5's mutation battery found it: a mutation that relayed PostgREST's error
    text to the caller SURVIVED, because the test reaching that assertion went
    down a path the product does not use. D211-D214's family, in a fixture.
    """

    def __init__(self, status: int = 200, body: bytes | None = None) -> None:
        self.status = status
        self.body = body if body is not None else _body(_row())
        self.request: Any = None

    def __call__(self, request: Any, timeout: float | None = None) -> Any:
        self.request = request
        self.timeout = timeout
        recorder = self

        if self.status >= 400:
            raise urllib.error.HTTPError(
                url=request.full_url,
                code=self.status,
                msg="refused",
                hdrs=None,  # type: ignore[arg-type]
                fp=io.BytesIO(self.body),
            )

        class _Response:
            status = recorder.status

            def read(self) -> bytes:
                return recorder.body

            def __enter__(self) -> Any:
                return self

            def __exit__(self, *_: Any) -> None:
                return None

        return _Response()


def test_the_callers_own_token_is_what_goes_upstream(monkeypatch: Any) -> None:
    """ADR 0125's first clause, asserted on the request rather than described.

    The token is placed in `Authorization` verbatim -- not re-signed, not
    exchanged, not wrapped. This runtime holds no signing key, so there is
    nothing else it could send, and this test is what says so out loud.
    """
    recorder = _Recorder()
    monkeypatch.setattr(mcp_upstream.urllib.request, "urlopen", recorder)

    mcp_upstream.resolve_agent_context(BASE, "the.original.token")

    assert recorder.request.get_header("Authorization") == "Bearer the.original.token"


def test_no_header_names_a_principal(monkeypatch: Any) -> None:
    """The confused deputy, refused by construction.

    A role, a subject, an owner, or `request.jwt.claims` supplied as a header
    would let this runtime's opinion decide what the lookup sees. The headers
    are enumerated rather than spot-checked, so a new one has to be added here
    deliberately.
    """
    recorder = _Recorder()
    monkeypatch.setattr(mcp_upstream.urllib.request, "urlopen", recorder)

    mcp_upstream.resolve_agent_context(BASE, "t")

    sent = {name.lower() for name in recorder.request.headers}
    assert sent == {"authorization", "content-type", "accept"}

    forbidden = {"role", "x-role", "sub", "subject", "owner", "x-postgrest-role", "prefer"}
    assert not sent & forbidden


def test_the_request_goes_to_the_one_rpc_and_names_no_other_path(monkeypatch: Any) -> None:
    """`mcp_upstream` is not a general PostgREST client and must not become one."""
    recorder = _Recorder()
    monkeypatch.setattr(mcp_upstream.urllib.request, "urlopen", recorder)

    mcp_upstream.resolve_agent_context(BASE, "t")

    assert recorder.request.full_url == f"{BASE}/rpc/mcp_agent_context"
    assert recorder.request.get_method() == "POST"


def test_the_agent_plane_still_holds_no_credential_to_be_a_deputy_with() -> None:
    """The structural half, and the reason the clauses above are enforceable.

    A runtime with a signing key or a database role could act on a caller's
    behalf under its own authority. `McpSettings` has neither, and `load_mcp`
    refuses to start if handed one -- so the deputy is unconstructible rather
    than merely unwritten.
    """
    fields = set(settings_module.McpSettings.__dataclass_fields__)

    assert "postgrest_url" in fields
    assert not fields & {"signing_key_file", "database_role", "passfile", "pool_size"}
    assert "APG_SIGNING_KEY_FILE" in settings_module.FORBIDDEN_VARIABLES["mcp"]
    assert "APG_DATABASE_ROLE" in settings_module.FORBIDDEN_VARIABLES["mcp"]


def test_the_upstream_url_is_an_address_and_never_a_credential() -> None:
    """`PGRST_DB_URI` is a `postgres://` URL with a role in it and sits in the
    same file. Confusing the two would be a request against the wrong thing."""
    base = {
        "APG_PROJECT_KEY": "example-dev",
        "APG_PROJECT_ENVIRONMENT": "dev",
        "APG_JWT_ISSUER": "https://example.test/api/app/auth",
        "APG_JWT_AUDIENCE": "urn:agentic-postgres:example:dev",
        "APG_JWKS_FILE": "/etc/mcp/jwks.json",
        "APG_LISTEN_PORT": "8080",
        "APG_POSTGREST_URL": "http://postgrest:3000",
        "APG_MCP_LOCK_FILE": "/etc/mcp/capability-lock.json",
    }

    assert settings_module.load_mcp(base).postgrest_url == "http://postgrest:3000"

    for bad in (
        # No userinfo, so ONLY the scheme rule can refuse it. The battery found
        # this gap: with `postgres://apg_authenticator@...` alone, a mutation
        # that admitted the `postgres://` scheme survived, because the userinfo
        # rule caught that string on the way past. Each rule needs a case only
        # it can refuse.
        "postgres://postgres:5432/db",
        "postgres://apg_authenticator@postgres:5432/db",
        "http://user:secret@postgrest:3000",
        "postgrest:3000",
        "http://",
    ):
        with pytest.raises(settings_module.MissingSetting):
            settings_module.load_mcp({**base, "APG_POSTGREST_URL": bad})


def test_an_unreachable_upstream_is_a_refusal_and_not_a_degraded_mode(monkeypatch: Any) -> None:
    """There is no cached identity to fall back to, deliberately (ADR 0125)."""

    def refuse(*_: Any, **__: Any) -> Any:
        raise ConnectionRefusedError

    monkeypatch.setattr(mcp_upstream.urllib.request, "urlopen", refuse)

    with pytest.raises(UpstreamRefusal, match="unreachable"):
        mcp_upstream.resolve_agent_context(BASE, "t")


def test_a_refusal_carries_no_upstream_detail(monkeypatch: Any) -> None:
    """ADR 0097: a structural refusal tells the caller nothing about state.

    PostgREST's error bodies name functions, SQLSTATEs and hints -- `42501
    permission denied for function mcp_agent_context` is the measured one. None
    of that may travel out of this module.
    """
    recorder = _Recorder(
        status=403,
        body=b'{"code":"42501","message":"permission denied for function mcp_agent_context"}',
    )
    monkeypatch.setattr(mcp_upstream.urllib.request, "urlopen", recorder)

    with pytest.raises(UpstreamRefusal) as raised:
        mcp_upstream.resolve_agent_context(BASE, "t")

    assert "42501" not in raised.value.reason
    assert "mcp_agent_context" not in raised.value.reason
    assert "permission denied" not in raised.value.reason


# ---------------------------------------------------------------------------
# one request, one context
# ---------------------------------------------------------------------------


def test_the_fingerprint_is_not_the_token() -> None:
    """Non-reversible, stable, and different for different tokens."""
    one = fingerprint("token-a")
    again = fingerprint("token-a")
    other = fingerprint("token-b")

    assert one == again
    assert one != other
    assert len(one) == 64 and all(c in "0123456789abcdef" for c in one)
    assert "token-a" not in one


def test_there_is_no_context_outside_a_request() -> None:
    """`None` would be an invitation to a tool that carries on with no owner."""
    with pytest.raises(UpstreamRefusal):
        current_agent_context()


class _FakeToken:
    def __init__(self, token: str) -> None:
        self.token = token


def _drive(middleware: AgentContextMiddleware, token: str, body: Any) -> Any:
    """Run one request through the middleware, with `get_access_token` stubbed.

    The framework's own dependency is patched at the point the middleware
    imports it, which is the seam that exists precisely so the refusal branches
    are reachable without a server.
    """
    import fastmcp.server.dependencies as dependencies

    original = dependencies.get_access_token
    dependencies.get_access_token = lambda: _FakeToken(token)  # type: ignore[assignment]
    try:
        return asyncio.run(middleware.on_request(None, body))
    finally:
        dependencies.get_access_token = original  # type: ignore[assignment]


def _middleware(monkeypatch: Any, owner: str = OWNER) -> AgentContextMiddleware:
    monkeypatch.setattr(
        mcp_authorization,
        "resolve_agent_context",
        lambda base_url, token: AgentContext(
            agent_id=AGENT,
            role_name="r",
            scopes=("meta:read",),
            authz_version=1,
            owner_id=f"{owner}:{token}",
        ),
    )
    return AgentContextMiddleware(BASE)


def test_the_context_is_resolved_before_the_request_is_served(monkeypatch: Any) -> None:
    """`on_request`, so discovery and execution both see it and neither can run
    without one."""
    middleware = _middleware(monkeypatch)
    seen: list[str] = []

    async def call_next(_: Any) -> str:
        seen.append(current_agent_context().owner_id)
        return "served"

    assert _drive(middleware, "tok-1", call_next) == "served"
    assert seen == [f"{OWNER}:tok-1"]


def test_the_context_does_not_survive_the_request(monkeypatch: Any) -> None:
    """Reset in a `finally`, so it is a property of the mechanism rather than of
    this code remembering to clear up."""
    middleware = _middleware(monkeypatch)

    async def call_next(_: Any) -> str:
        assert current_agent_context() is not None
        return "served"

    _drive(middleware, "tok-1", call_next)

    with pytest.raises(UpstreamRefusal):
        current_agent_context()


def test_the_context_does_not_survive_a_FAILING_request(monkeypatch: Any) -> None:
    """The `finally` half. A request that raised would otherwise leave a context
    behind for whatever ran next on this task."""
    middleware = _middleware(monkeypatch)

    async def call_next(_: Any) -> str:
        raise RuntimeError("the tool failed")

    with pytest.raises(RuntimeError):
        _drive(middleware, "tok-1", call_next)

    with pytest.raises(UpstreamRefusal):
        current_agent_context()


def test_concurrent_requests_never_see_each_others_context(monkeypatch: Any) -> None:
    """**The test that distinguishes the mechanism from the obvious wrong one.**

    Measured before it was written: a module-level dict leaks 11 of 12 here and
    is correct on every sequential request, so a suite without this arm would
    pass the broken implementation. Twelve requests, twelve tokens, with an
    `await` inside the middleware so the loop genuinely interleaves them.
    """
    middleware = _middleware(monkeypatch)
    observed: dict[str, str] = {}

    async def one(token: str) -> None:
        import fastmcp.server.dependencies as dependencies

        async def call_next(_: Any) -> None:
            await asyncio.sleep(0.01)
            observed[token] = current_agent_context().owner_id

        original = dependencies.get_access_token
        dependencies.get_access_token = lambda: _FakeToken(token)  # type: ignore[assignment]
        try:
            await middleware.on_request(None, call_next)
        finally:
            dependencies.get_access_token = original  # type: ignore[assignment]

    async def all_at_once() -> None:
        await asyncio.gather(*(one(f"tok-{n:02d}") for n in range(12)))

    asyncio.run(all_at_once())

    assert len(observed) == 12
    wrong = {token: seen for token, seen in observed.items() if seen != f"{OWNER}:{token}"}
    assert not wrong, f"a request observed another caller's context: {wrong}"


def test_a_held_context_is_keyed_to_the_token_that_resolved_it(monkeypatch: Any) -> None:
    """Belt and braces, and it has a specific job.

    If a value ever outlived its request, the fingerprint check turns a LEAK
    into a MISS. Asserted on the stored pair, because there is no supported way
    to make the ContextVar misbehave -- which is the point.
    """
    middleware = _middleware(monkeypatch)
    held: list[Any] = []

    async def call_next(_: Any) -> None:
        held.append(mcp_authorization._CURRENT.get())

    _drive(middleware, "tok-9", call_next)

    assert held[0].fingerprint == fingerprint("tok-9")
    assert held[0].fingerprint != fingerprint("tok-8")
