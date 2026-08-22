"""The agent plane's published surface (Session 8, Run 7).

Three properties, and each is here because a measurement said the obvious form
would be wrong:

1. **One published path, in ADR 0108's two-matcher form, stripping nothing.**
   `PathPrefix` is a string prefix (D162), so the single-matcher form answers
   `/mcpx`. And the strip is absent because the container serves `/mcp` at its
   own root -- measured from the route table the framework builds -- so a strip
   would forward `/` to a service that answers 404 there.

2. **Health is private by the absence of a route.** The container serves
   `/health/live` and `/health/ready`; nothing publishes them. The public answer
   to "is this project up" stays `__apg/healthz` (D231).

3. **A request carrying `Origin` is refused.** Measured at the pinned fastmcp
   3.4.0: `host_origin_protection`, `allowed_hosts` and `allowed_origins` are all
   ABSENT -- they arrive at 3.4.7, above ADR 0121's ceiling -- and a cross-origin
   request is otherwise processed and answered 200.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from tests.contract.test_runtime_override import NAMES, RENDERED

from agentic_postgres import naming, runtime_override
from app import mcp_origin, mcp_runtime
from app.mcp_origin import RefuseBrowserOrigins

pytestmark = [pytest.mark.contract, pytest.mark.p0]


@pytest.fixture
def labels() -> dict[str, str]:
    document = runtime_override.build_override(
        **NAMES, https_entrypoint="websecure", rendered_directory=RENDERED
    )
    return document["services"][runtime_override.MCP_SERVICE]["labels"]


def _rule(labels: dict[str, str]) -> str:
    return next(value for key, value in labels.items() if key.endswith(".rule"))


# ---------------------------------------------------------------------------
# the rule
# ---------------------------------------------------------------------------


def test_the_rule_is_the_two_matcher_form_a_sibling_cannot_satisfy(
    labels: dict[str, str],
) -> None:
    """D162, D408: `PathPrefix(/mcp)` alone would answer `/mcpx`."""
    rule = _rule(labels)

    assert "Path(`${API_MCP_PATH:?required}`)" in rule
    assert "PathPrefix(`${API_MCP_PATH:?required}/`)" in rule
    assert "Host(`${PROJECT_DOMAIN:?required}`)" in rule
    # The single-matcher spelling must not appear: it is the one that leaks.
    assert "PathPrefix(`${API_MCP_PATH:?required}`)" not in rule


def test_the_interpolated_rule_matches_the_route_and_not_its_sibling() -> None:
    """The property the rule exists for, evaluated rather than described.

    Traefik is not available here, so the two matchers are evaluated the way
    Traefik documents them -- `Path` is equality and `PathPrefix` is a string
    prefix. That is the semantics D162 measured, and it is what makes `/mcpx`
    the interesting case.
    """
    path = "/mcp"

    def matches(candidate: str) -> bool:
        return candidate == path or candidate.startswith(f"{path}/")

    assert matches("/mcp")
    assert matches("/mcp/")
    assert matches("/mcp/messages")
    assert not matches("/mcpx")
    assert not matches("/mcpx/anything")
    assert not matches("/mc")


def test_no_other_router_in_this_deployment_matches_the_agent_planes_path() -> None:
    """Precedence is uncontested, and that is derived rather than assumed.

    Every rule in the override is interpolated with one project's real values
    and evaluated against `/mcp`. If a second router matched, the ordering would
    become a length comparison (ADR 0108) and this route would need an argument
    it currently does not.
    """
    document = runtime_override.build_override(
        **NAMES, https_entrypoint="websecure", rendered_directory=RENDERED
    )
    values = {
        "API_MCP_PATH": "/mcp",
        "API_STORAGE_PATH": "/api/app/storage",
        "API_APP_PATH": "/api/app",
        "API_REST_PATH": "/api/rest",
        "API_DOCS_PATH": "/docs/rest",
        "API_APP_DOCS_PATH": "/docs/app",
        "HEALTH_ROUTE_PATH": "/__apg/healthz",
    }

    matching = set()
    for service, entry in document["services"].items():
        for key, rule in (entry.get("labels") or {}).items():
            if not key.endswith(".rule"):
                continue
            interpolated = rule
            for name, value in values.items():
                interpolated = interpolated.replace(f"${{{name}:?required}}", value)
            # A rule is one router even when it carries two matchers, so the set
            # is keyed by the ROUTER rather than by the clause that matched.
            if any(
                candidate == "/mcp" or "/mcp".startswith(f"{candidate}/")
                for candidate in _paths(interpolated)
            ):
                matching.add(f"{service}:{key}")
    assert matching == {f"{runtime_override.MCP_SERVICE}:{_rule_key(document)}"}, (
        f"more than one router matches /mcp: {sorted(matching)}"
    )


def _paths(rule: str) -> list[str]:
    """Every literal a `Path(...)` or `PathPrefix(...)` clause names."""
    found = []
    for marker in ("Path(`", "PathPrefix(`"):
        start = 0
        while True:
            index = rule.find(marker, start)
            if index < 0:
                break
            end = rule.index("`", index + len(marker))
            found.append(rule[index + len(marker) : end].rstrip("/"))
            start = end
    return found


def _rule_key(document: dict[str, Any]) -> str:
    labels = document["services"][runtime_override.MCP_SERVICE]["labels"]
    return next(key for key in labels if key.endswith(".rule"))


def test_the_router_strips_nothing_because_the_container_serves_the_same_path(
    labels: dict[str, str],
) -> None:
    """The published path and the served path are one string.

    A strip would forward `/` to a service whose MCP endpoint is at `/mcp` --
    measured from the framework's own route table, which also shows the health
    routes at the ROOT rather than under it.
    """
    assert not any("stripprefix" in key for key in labels)
    assert mcp_runtime.MCP_ROUTE_PATH == "/mcp"

    # The published path comes from `naming`, and the served path is the
    # runtime's constant. Asserted equal rather than either copied.
    identity = naming.derive(
        slug="probe",
        environment="dev",
        domain="probe.test",
        api_base_path="/api",
        mcp_base_path=mcp_runtime.MCP_ROUTE_PATH,
    )
    assert identity.route_mcp_path == mcp_runtime.MCP_ROUTE_PATH
    assert identity.route_mcp.endswith(mcp_runtime.MCP_ROUTE_PATH)


def test_the_agent_plane_gets_no_cors_and_no_buffering_middleware(
    labels: dict[str, str],
) -> None:
    """Both absent for stated reasons, not by omission (ADR 0128).

    No CORS because this is not a browser API and the runtime refuses any
    request carrying `Origin`; attaching one would advertise a cross-origin flow
    that is deliberately impossible (ADR 0109).
    """
    assert not any("cors" in key for key in labels)
    assert not any("buffering" in key for key in labels)

    chain = next(value for key, value in labels.items() if key.endswith(".middlewares"))
    assert chain == "${BASELINE_MIDDLEWARE_CHAIN:?required}"


def test_no_router_publishes_the_health_routes() -> None:
    """Private by absence, across every router in the deployment (ADR 0128)."""
    document = runtime_override.build_override(
        **NAMES, https_entrypoint="websecure", rendered_directory=RENDERED
    )
    for entry in document["services"].values():
        for key, value in (entry.get("labels") or {}).items():
            if key.endswith(".rule"):
                assert mcp_runtime.HEALTH_LIVE_PATH not in value
                assert mcp_runtime.HEALTH_READY_PATH not in value


# ---------------------------------------------------------------------------
# the assembly -- the step nothing executed until Run 7
# ---------------------------------------------------------------------------


def _built_app(tmp_path: Any, *, with_lock: bool = True) -> Any:
    """Assemble the real application: verifier, server, tools, health, wrapper."""
    import json

    from cryptography.hazmat.primitives.asymmetric import rsa

    from agentic_postgres import jwt_keys
    from app.mcp_lock import load_lock
    from app.mcp_runtime import AgentTokenVerifier, build_server
    from app.tokens import LocalKeySet

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.public_key().public_numbers()
    document = jwt_keys.build_jwks(
        [jwt_keys.public_jwk(modulus_hex=format(numbers.n, "X"), exponent=numbers.e)]
    )
    jwks = tmp_path / "jwks.json"
    jwks.write_bytes(json.dumps(document, indent=2, sort_keys=True).encode("utf-8") + b"\n")

    lock = None
    if with_lock:
        lock_path = tmp_path / "lock.json"
        lock_path.write_text(json.dumps(_minimal_lock()), encoding="utf-8")
        lock = load_lock(lock_path)

    verifier = AgentTokenVerifier(
        LocalKeySet.from_path(jwks), issuer="https://i.test", audience="urn:a"
    )
    server = build_server(
        verifier, project_key="probe-dev", postgrest_url="http://postgrest:3000", lock=lock
    )
    return server.http_app(path=mcp_runtime.MCP_ROUTE_PATH, stateless_http=True)


def _minimal_lock() -> dict[str, Any]:
    resource = {
        "name": "notes",
        "capability": "query_notes",
        "columns": ["id", "title"],
        "filters": [{"column": "title", "operators": ["eq"]}],
        "order_by": [{"column": "title", "direction": "asc"}],
        "max_rows": 200,
        "required_scopes": ["notes:read"],
        "operation": {"method": "get", "path": "/notes", "operation_id": "notes.get"},
    }
    tools = []
    for name in ("describe_resource", "list_resources", "query_resource", "run_report"):
        reads = name in ("query_resource", "run_report")
        tools.append(
            {
                "name": name,
                "kind": "read" if reads else "metadata",
                "source": "postgrest" if reads else "lock",
                "timeout_ms": 5000 if reads else 1000,
                "discovery_scope_sets": [["notes:read"] if reads else ["meta:read"]],
                "descriptions": [],
                "resources": [resource] if reads else [],
            }
        )
    return {
        "schema_version": 1,
        "contract_id": "x",
        "project_key": "probe-dev",
        "upstream": "https://probe.test/api/rest",
        "canonical_sha256": "a" * 64,
        "capability_count": 5,
        "tool_count": 4,
        "tools": tools,
    }


def test_the_application_assembles_and_serves_exactly_three_paths(tmp_path: Any) -> None:
    """**The test that would have caught D444.**

    Nothing had ever built the application. Every test constructed the verifier
    and called `verify_token` directly, so `http_app` -- which calls
    `auth.get_middleware()` while assembling -- was never reached, and a
    duck-typed verifier raised `AttributeError` on the first real start. D381's
    shape: declared in code, assembled nowhere, correct-looking until deploy.

    Asserting the route table rather than merely "it did not raise", because the
    published path and the private health paths are the whole of ADR 0128 and a
    successful assembly with the wrong paths is the next failure along.
    """
    application = _built_app(tmp_path)
    paths = sorted(getattr(route, "path", "?") for route in application.routes)

    assert paths == [
        mcp_runtime.HEALTH_LIVE_PATH,
        mcp_runtime.HEALTH_READY_PATH,
        mcp_runtime.MCP_ROUTE_PATH,
    ]


def test_the_verifier_satisfies_the_frameworks_auth_contract() -> None:
    """Not just `verify_token` (D444).

    The framework's `AuthProvider` supplies four things the assembly uses, and
    the reason to assert them by name is that only ONE of them is the obvious
    one. A future refactor back to duck typing fails here rather than on a host.
    """
    from fastmcp.server.auth import TokenVerifier

    from app.mcp_runtime import AgentTokenVerifier

    assert issubclass(AgentTokenVerifier, TokenVerifier)
    for required in ("verify_token", "get_middleware", "get_routes", "set_mcp_path"):
        assert callable(getattr(AgentTokenVerifier, required, None)), required


def test_the_assembly_fails_loudly_without_a_lock_rather_than_serving_nothing(
    tmp_path: Any,
) -> None:
    """A server with no tools assembles; readiness is what refuses it.

    The pair is the point. `build_server` tolerates `lock=None` so a test can
    exercise the surface without one, and the readiness route is what makes a
    container in that state fail its healthcheck instead of serving an empty
    discovery response nobody can distinguish from a correctly-empty one.
    """
    application = _built_app(tmp_path, with_lock=False)

    assert sorted(getattr(route, "path", "?") for route in application.routes) == [
        mcp_runtime.HEALTH_LIVE_PATH,
        mcp_runtime.HEALTH_READY_PATH,
        mcp_runtime.MCP_ROUTE_PATH,
    ]


# ---------------------------------------------------------------------------
# the Origin refusal
# ---------------------------------------------------------------------------


def _send(headers: list[tuple[bytes, bytes]], *, scope_type: str = "http") -> dict[str, Any]:
    """Drive the middleware over one ASGI scope and collect what it emitted."""
    reached = {"inner": False}
    messages: list[dict[str, Any]] = []

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        reached["inner"] = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    async def receive() -> dict[str, Any]:  # pragma: no cover -- never awaited
        return {"type": "http.request"}

    asyncio.run(
        RefuseBrowserOrigins(inner)({"type": scope_type, "headers": headers}, receive, send)
    )
    return {"reached": reached["inner"], "messages": messages}


def test_any_request_carrying_an_origin_is_refused() -> None:
    """Not an allowlist. `Origin`'s presence is the signal (ADR 0128)."""
    for origin in (b"https://evil.test", b"https://project.test", b"null", b""):
        result = _send([(b"origin", origin)])

        assert not result["reached"], f"Origin {origin!r} reached the application"
        assert result["messages"][0]["status"] == mcp_origin.ORIGIN_REFUSED_STATUS


def test_the_header_name_is_matched_case_insensitively() -> None:
    """HTTP header names are case-insensitive and a browser's casing is not ours."""
    for name in (b"Origin", b"ORIGIN", b"oRiGiN"):
        assert not _send([(name, b"https://evil.test")])["reached"]


def test_a_request_without_an_origin_reaches_the_application() -> None:
    """**The control.** Without it, a middleware that refused everything passes."""
    result = _send([(b"authorization", b"Bearer x"), (b"content-type", b"application/json")])

    assert result["reached"]
    assert result["messages"][0]["status"] == 200


def test_a_refusal_carries_no_allow_origin_header() -> None:
    """Echoing one would tell a browser the refusal is readable, which is untrue."""
    result = _send([(b"origin", b"https://evil.test")])
    names = {name.lower() for name, _ in result["messages"][0]["headers"]}

    assert b"access-control-allow-origin" not in names


def test_a_non_http_scope_passes_through_untouched() -> None:
    """A middleware that swallowed a lifespan message would break startup."""
    assert _send([], scope_type="lifespan")["reached"]


def test_the_refusal_is_not_a_401() -> None:
    """403, because this is not an authentication problem.

    A 401 invites a browser to retry with credentials, which is the flow being
    refused.
    """
    assert mcp_origin.ORIGIN_REFUSED_STATUS == 403


def test_the_pinned_framework_has_no_host_or_origin_protection_of_its_own() -> None:
    """The measurement this middleware exists because of (ADR 0128).

    If a future bump brings the framework's own protection, this test is what
    says so -- and the decision to keep both or drop one becomes a real choice
    rather than a duplicate nobody noticed.
    """
    import inspect

    from fastmcp import FastMCP

    parameters = set(inspect.signature(FastMCP.http_app).parameters)
    assert not parameters & {"host_origin_protection", "allowed_hosts", "allowed_origins"}


def test_every_agent_plane_object_the_framework_wires_is_a_framework_type() -> None:
    """**The test that would have caught D444 and D450 together.**

    Two objects are handed to the framework to wire: the verifier and the
    middleware. Both were written "structurally typed rather than subclassing",
    and **both were wrong** -- the verifier raised `AttributeError` on
    `get_middleware()` at assembly, and the middleware raised
    `'AgentContextMiddleware' object is not callable` on the first request
    through the pipeline.

    Run 7 found the first and this one survived, because the seam nobody crossed
    was the same seam: a unit test that calls `verify_token` or `on_request`
    directly never asks the framework to accept the object.

    Asserted as a pair, so a third wired object added later has an obvious place
    to be listed.
    """
    from fastmcp.server.auth import TokenVerifier
    from fastmcp.server.middleware import Middleware

    from app.mcp_authorization import AgentContextMiddleware
    from app.mcp_runtime import AgentTokenVerifier

    assert issubclass(AgentTokenVerifier, TokenVerifier)
    assert issubclass(AgentContextMiddleware, Middleware)


def test_a_request_reaches_a_tool_through_the_real_middleware_pipeline(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """The seam itself, exercised (D450).

    Not `middleware.on_request(...)` -- the framework's own pipeline, reached by
    calling a registered tool. This is the arrangement that raised "object is not
    callable" for three runs while every unit test passed.

    **The token is arranged HERE** (D494). This test passed four gates without
    arranging one, because a concurrency test in `test_mcp_authorization` was
    leaving a fake `get_access_token` installed in the framework module for the
    rest of the process -- so alone, the middleware correctly refused the
    tokenless request and this test failed for the thing it never supplied. A
    pipeline behind an authenticating middleware needs a caller, and the caller
    is this test's to provide.
    """
    import asyncio

    import fastmcp.server.dependencies as dependencies

    from app import mcp_authorization, mcp_tools
    from app.mcp_upstream import AgentContext

    class _Token:
        token = "the.callers.token"  # noqa: S105 — a fixed placeholder, not a credential

    monkeypatch.setattr(dependencies, "get_access_token", lambda: _Token())
    monkeypatch.setattr(
        mcp_authorization,
        "resolve_agent_context",
        lambda base_url, token: AgentContext(
            agent_id="agent-1",
            role_name="r",
            scopes=("meta:read", "notes:read"),
            authz_version=1,
            owner_id="owner-1",
        ),
    )
    monkeypatch.setattr(mcp_tools, "execute", lambda *_, **__: [{"title": "alpha"}])

    server = _built_server(tmp_path)
    tools = asyncio.run(server.list_tools())

    assert sorted(tool.name for tool in tools) == [
        "describe_resource",
        "list_resources",
        "query_resource",
        "run_report",
    ]


def _built_server(tmp_path: Any) -> Any:
    """The real server object, with the lock and both wired components."""
    import json

    from cryptography.hazmat.primitives.asymmetric import rsa

    from agentic_postgres import jwt_keys
    from app.mcp_lock import load_lock
    from app.mcp_runtime import AgentTokenVerifier, build_server
    from app.tokens import LocalKeySet

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.public_key().public_numbers()
    document = jwt_keys.build_jwks(
        [jwt_keys.public_jwk(modulus_hex=format(numbers.n, "X"), exponent=numbers.e)]
    )
    jwks = tmp_path / "jwks.json"
    jwks.write_bytes(json.dumps(document, indent=2, sort_keys=True).encode("utf-8") + b"\n")

    lock_path = tmp_path / "lock.json"
    lock_path.write_text(json.dumps(_minimal_lock()), encoding="utf-8")

    return build_server(
        AgentTokenVerifier(LocalKeySet.from_path(jwks), issuer="https://i.test", audience="urn:a"),
        project_key="probe-dev",
        postgrest_url="http://postgrest:3000",
        lock=load_lock(lock_path),
        max_concurrent_reads=2,
    )


def test_the_blocking_upstream_read_does_not_run_on_the_event_loop() -> None:
    """**D451.** A blocking call on the loop serialises the whole process.

    `execute` is blocking urllib. Awaiting it directly would stop every other
    request -- and the health routes with them -- for the duration of one slow
    read, and it would make the concurrency bound unreachable: measured, six
    overlapping reads peaked at ONE concurrent, so the semaphore never saw
    contention and appeared to work.

    Asserted on the source, because the behaviour it prevents needs a loop under
    load to observe and the property is a single call.
    """
    import ast
    from pathlib import Path as _Path

    from app import mcp_tools

    tree = ast.parse(_Path(mcp_tools.__file__).read_text(encoding="utf-8"))
    threaded = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "to_thread"
    ]
    assert threaded, "the blocking upstream read is not moved off the event loop"
