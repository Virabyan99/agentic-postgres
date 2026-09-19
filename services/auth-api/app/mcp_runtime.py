"""The agent plane's runtime: the fourth verifier, and nothing else yet.

Run 4 is "the runtime and the fourth verifier", and that is literal. There are
**no tools here** -- `list_resources`, `describe_resource`, `query_resource` and
`run_report` are Run 6's, served from the deployed capability lock, and
registering a placeholder for them now would put four names in a discovery
response that answer nothing. What exists is the thing they will be built on: a
process that reads its key set from the rendered file, refuses every token that
is not an agent token, and can be asked whether it is alive.

**This runtime holds no credential of any kind.** No signing key, so it is a
verifier and never an issuer (ADR 0098). No database credential, so it takes no
share of ADR 0099's connection budget, and that zero is asserted by a test that
parses the budget arithmetic rather than left to be noticed (D407). No R2
credential. The only secret-adjacent material it touches is the caller's own
bearer token, which it verifies and -- from Run 5 -- forwards unchanged.

**It is the fourth verifier** (ADR 0113, ADR 0122). PostgREST, the auth service
and storage are the other three, and all four read the SAME rendered
`jwks.json`: the same artefact, mounted read-only, not a copy. D381 is what the
alternative costs -- storage was declared the third verifier in four places and
handed no key set, and exited 3 on its first start anywhere while
`LocalKeySet.from_path` existed, was tested, and had no production caller. That
classmethod is called here, at line one of the key path, for that reason.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from fastmcp.server.auth import TokenVerifier as _TokenVerifier
from mcp.types import LATEST_PROTOCOL_VERSION

from app import mcp_metrics, mcp_telemetry
from app import settings as settings_module
from app.claims import ClaimError, verify_claims
from app.mcp_authorization import AgentContextMiddleware, ToolVisibilityMiddleware
from app.mcp_lock import CapabilityLock, load_lock
from app.mcp_origin import RefuseBrowserOrigins
from app.request_id import StampRequestId
from app.tokens import LocalKeySet, MalformedToken, pre_parse

if TYPE_CHECKING:  # pragma: no cover -- import-time typing only
    from starlette.applications import Starlette

#: The one `token_use` this surface accepts (ADR 0115). A single string rather
#: than a subset of `claims.TOKEN_USES`, and the difference is the decision:
#: `access` is what the APPLICATION API accepts (ADR 0114), and the two surfaces
#: are mirror images. A constant computed as "TOKEN_USES minus access" would
#: silently admit a third use the moment one was added.
ACCEPTED_TOKEN_USE = "agent"  # noqa: S105 -- a claim VALUE, not a credential

#: The lowest `authz_version` a real agent can hold.
#:
#: Not a style choice and not a guess: `app.agents.authz_version` is
#: `NOT NULL DEFAULT 1 CHECK (authz_version >= 1)` in migration 0011. A token
#: claiming 0 names a state the schema cannot hold, so it is refusable here --
#: before any lookup, which is ADR 0115's shape -- rather than at the hook.
#:
#: `claims.verify_claims` permits `>= 0` and is NOT changed: it is the shared
#: contract for both planes, and tightening it here rather than there keeps the
#: agent plane's extra rule additive. A currently-passing test is not weakened
#: to make this one pass, and none needed to be.
MINIMUM_AUTHZ_VERSION = 1

#: The MCP protocol revision this runtime implements, read from the framework
#: (ADR 0123, D406). **Never a literal in this repository.**
#:
#: It is the HIGHEST revision the runtime implements, not one it negotiated.
#: Measured with a control that settles it: a server handed an `initialize` for
#: `2025-03-26` answers `2025-03-26`, so a revision read from a handshake is a
#: fact about the client. `DEFAULT_NEGOTIATED_VERSION` is the other trap -- it
#: is what an unversioned caller gets, two revisions below what this speaks.
PROTOCOL_REVISION = LATEST_PROTOCOL_VERSION

#: Whether the bearer profile conforms to the MCP authorization specification.
#:
#: **It does not, and publishing that is the point** (D413). Measured rather
#: than asserted: with a bare `TokenVerifier`, a 401 from this framework carries
#: no `WWW-Authenticate` challenge, which RFC 9728 and the MCP authorization
#: specification both require. This deployment pre-provisions an internal
#: bearer, so the honest record of it belongs in the document every plane reads
#: rather than in prose a runbook nobody diffs. D274 is the precedent: a claim
#: that lives only in prose is a claim nobody checks.
AUTHORIZATION_SPEC_CONFORMANT = False

#: The path this runtime serves the MCP endpoint at, INSIDE the container.
#:
#: The same string the edge publishes, because the router strips nothing (ADR
#: 0128) -- measured, because a `custom_route` mounts at the application root
#: rather than under this path, so `/mcp/health/live` is a 404 and `/health/live`
#: is not. `runtime_override` derives the published path from the manifest and
#: `naming.py` owns it; this constant is what the image serves, and a test
#: asserts the two agree rather than either one being copied.
MCP_ROUTE_PATH = "/mcp"

#: The container-local health paths. Served, and published by nothing.
HEALTH_LIVE_PATH = "/health/live"
HEALTH_READY_PATH = "/health/ready"

#: The lock THIS PROCESS loaded, set once by `create_mcp_app`, read by nothing
#: in the request path.
#:
#: D1152/D1153. It exists so that something outside the container can ask the
#: RUNNING plane which lock it is serving, instead of reading the file on disk
#: and speaking of the plane. A deploy whose only change is the lock recreates
#: no container unless its mount digest moved (ADR 0155), so the file and the
#: process can disagree -- and on 2026-09-11 they did, for eight minutes, with
#: the deployed document publishing seven tools against a plane serving six.
#:
#: `None` before the app is built, which is the honest value in a process that
#: has not loaded one: an importer reading `0` or `""` here would be reading an
#: answer where there is none (ADR 0195).
LOADED_LOCK: CapabilityLock | None = None

#: Where this process RECORDS the lock it loaded, for a reader that is not it.
#:
#: **D1286.** `LOADED_LOCK` above is correct and unreadable from outside: the
#: deploy asks with `docker exec python -c`, which is a FRESH interpreter in the
#: same container, and a fresh import sees `None` because only `create_mcp_app`
#: assigns it. The global answered `null` on every host from the day it was
#: written -- the first deploy ever to run that path was Session 24's, and it
#: could not have worked on any earlier one either.
#:
#: So the signature is written to a file the serving process owns, and the path
#: is a module-level constant: a fresh import can read the constant, and the
#: file carries the state. One authority -- `agent_plane.PROBE` asks the module
#: where to look rather than holding a second copy of this path (D486).
#:
#: `/tmp` is not a convenience: the container is `read_only: true` with exactly
#: one writable mount, `tmpfs /tmp` owned by this uid. Per-container and
#: per-boot is the right lifetime for "what THIS process loaded" -- a record
#: that outlived the process would be the stale-file problem D1152 is about,
#: one directory along.
LOADED_LOCK_RECORD = "/tmp/apg-loaded-lock.json"  # noqa: S108 -- see above:
#: this container is read_only with a PRIVATE tmpfs /tmp at mode 0700 owned by
#: this uid, so the shared-directory races S108 is about cannot arise here, and
#: it is the only writable path the service has.


def record_loaded_lock(lock: CapabilityLock, path: str | None = None) -> None:
    """Write the signature of the lock this process loaded, for an outside reader.

    Best effort by decision: a plane that is serving correctly must not fail to
    start because a diagnostic record could not be written. A caller that cannot
    read the record gets the third outcome it already handles -- `serves_lock`
    returns `None` and the count goes unpublished -- which is the same answer it
    got before this existed, rather than a new failure mode (ADR 0195).
    """
    # Resolved here rather than as a default argument: a default binds at
    # definition and would make `LOADED_LOCK_RECORD` two values -- the one the
    # module names and the one this function captured at import (D486).
    target = path or LOADED_LOCK_RECORD
    try:
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(
                {"tools_sha256": lock.tools_sha256, "tool_count": lock.tool_count},
                handle,
            )
    except OSError:
        pass


__all__ = [
    "ACCEPTED_TOKEN_USE",
    "AUTHORIZATION_SPEC_CONFORMANT",
    "LOADED_LOCK",
    "LOADED_LOCK_RECORD",
    "MINIMUM_AUTHZ_VERSION",
    "PROTOCOL_REVISION",
    "AgentTokenVerifier",
    "build_server",
    "create_mcp_app",
    "record_loaded_lock",
    "verify_agent_claims",
]


def verify_agent_claims(
    payload: Any,
    *,
    issuer: str,
    audience: str,
    now: int,
) -> dict[str, Any]:
    """Everything a valid signature does not establish, for an AGENT token.

    A pure function over its arguments, so the boundary can be exercised without
    a key, a socket or a running server -- which is what lets the refusal
    branches be tested at all. `AgentTokenVerifier` is the thin part that holds
    the key set and calls this.

    The order matters and is ADR 0115's: **`token_use` is refused before any
    lookup**, so an access token presented here is turned away by the surface
    rather than by whatever it would have reached. The shared contract runs
    first because a payload that is not a valid token at all should not be
    reported as the wrong kind of token.
    """
    verified = verify_claims(payload, issuer=issuer, audience=audience, now=now)

    if verified["token_use"] != ACCEPTED_TOKEN_USE:
        raise ClaimError(
            f"this surface accepts only {ACCEPTED_TOKEN_USE!r} tokens (ADR 0115); "
            f"{verified['token_use']!r} is for the application API"
        )

    # `sub` is the AGENT's id here, where on an access token it is the user's.
    # `verify_claims` has already established it is a non-empty string; what is
    # added is that the agent plane reads it as an identity rather than as a
    # label, so an empty-after-strip value is refused rather than carried into
    # an audit record as a subject nobody can resolve.
    if not verified["sub"].strip():
        raise ClaimError("sub is blank; on an agent token it is the agent's id")

    if verified["authz_version"] < MINIMUM_AUTHZ_VERSION:
        raise ClaimError(
            f"authz_version is {verified['authz_version']}, below the schema's own floor of "
            f"{MINIMUM_AUTHZ_VERSION}; no agent row can hold it"
        )

    return verified


class AgentTokenVerifier(_TokenVerifier):
    """FastMCP's `TokenVerifier`, holding the rendered key set and nothing else.

    **It subclasses the framework's class, and Run 4's decision not to was
    wrong** (D444). The docstring here used to say it was "structurally typed
    against the framework rather than subclassing it: the protocol is one
    coroutine". The protocol is not one coroutine. `http_app` calls
    `auth.get_middleware()` while assembling the application, and
    `AuthProvider` also supplies `get_routes`, `get_well_known_routes` and
    `set_mcp_path` -- so a duck-typed object raised `AttributeError` the first
    time anything built the app.

    Nothing caught it, because nothing had ever built the app: every test
    constructed this class and called `verify_token` directly. **That is D381's
    shape** -- a runtime declared in code, assembled nowhere, and correct-looking
    until the first real start. Run 7's rig is what executed the assembly.

    **Every refusal returns `None`**, which the framework renders as a 401 with
    no detail. That is ADR 0097's split applied at the outermost door: a
    structural refusal tells an unauthenticated caller nothing, because anything
    it said would be a claim about state to somebody who has not proved they may
    ask about state.
    """

    def __init__(self, key_set: LocalKeySet, *, issuer: str, audience: str) -> None:
        super().__init__()
        self._key_set = key_set
        self._issuer = issuer
        self._audience = audience

    @property
    def key_set(self) -> LocalKeySet:
        """The set this verifier holds. Read by the readiness answer, not by a route."""
        return self._key_set

    async def verify_token(self, token: str) -> Any:
        """Verify a bearer token, or return `None`.

        Deliberately `AuthService.authenticate`'s preamble, line for line: the
        same `pre_parse`, the same `resolve`, the same `jwt.decode` arguments
        and the same option flags. **The flags are the part to read.** `exp` and
        `nbf` are disabled here and applied by the claim contract with the
        measured 30-second skew, because letting PyJWT apply its own default
        would open a second temporal window -- a narrower one than the locked
        PostgREST's, so a token this plane refused would be one the REST surface
        served.

        `LocalKeySet.resolve` refuses an unknown `kid` rather than trying every
        key, which is what stops a retired key verifying tokens for as long as
        it is still published.

        What this does NOT do is compare against current state. `authenticate`
        does, over a database connection; this runtime has none, and the
        comparison is `mcp_agent_context`'s, called with the caller's own token
        in Run 5. So `credential_version` and `authz_version` are checked here
        for shape and floor only, and the authority on whether they are CURRENT
        stays the hook (ADR 0117).
        """
        import time

        import jwt

        from app import keys as key_module

        try:
            pre_parsed = pre_parse(token)
            key = self._key_set.resolve(pre_parsed)
        except MalformedToken:
            return None

        try:
            payload = jwt.decode(
                token,
                jwt.PyJWK.from_dict(key).key,
                algorithms=[key_module.ALGORITHM],
                audience=self._audience,
                issuer=self._issuer,
                options={"verify_exp": False, "verify_nbf": False},
            )
        except jwt.InvalidTokenError:
            return None

        try:
            verified = verify_agent_claims(
                payload,
                issuer=self._issuer,
                audience=self._audience,
                now=int(time.time()),
            )
        except ClaimError:
            return None

        from fastmcp.server.auth import AccessToken

        return AccessToken(
            token=token,
            client_id=verified["sub"],
            subject=verified["sub"],
            scopes=list(verified["scope"]),
            expires_at=verified["exp"],
            claims=verified,
        )


def build_server(
    verifier: AgentTokenVerifier,
    *,
    project_key: str,
    postgrest_url: str,
    lock: Any | None = None,
    max_concurrent_reads: int | None = None,
) -> Any:
    """The FastMCP server, its six tools, and its private health routes.

    Six tools are registered from the compiled capability lock -- four since
    Session 8 Run 6, and the two writes since Session 9 Run 5. Called without a
    lock -- which only a test does -- the server has none, which is true, as
    against a placeholder that would be a discovery response that lies.

    **The health routes are served here and published nowhere** (ADR 0128).
    Measured against the pinned framework: a `custom_route` mounts at the
    application ROOT rather than under `path=`, and is **not** behind the token
    verifier, with the control that matters alongside it -- `/mcp` still answers
    an unauthenticated caller 401. So "health answered" cannot be read as
    "authentication is off".

    **The authorization middleware is here from Session 8 Run 5, before any tool
    existed**, and that order is deliberate. It resolves the caller's context on
    the way in (ADR 0125), so a tool added later cannot be written against a
    request that has no context: there is no such request. A middleware added
    afterwards would have to be remembered by every tool author, which is the
    shape of D333.

    **The visibility middleware is second, and the order is measured** (ADR
    0140, rig5 M3): it reads in `on_list_tools` the context the first sets in
    `on_request`, so the first must run first. It is added only with a lock,
    because there is nothing to filter without one and a lockless server has no
    roster to hide.
    """
    from fastmcp import FastMCP

    middleware: list[Any] = [AgentContextMiddleware(postgrest_url)]
    if lock is not None:
        middleware.append(ToolVisibilityMiddleware(lock))

    server = FastMCP(
        name=f"agentic-postgres/{project_key}",
        auth=verifier,
        middleware=middleware,
        # Details of an internal failure are not an agent's to read (ADR 0097).
        mask_error_details=True,
    )
    if lock is not None:
        from app.mcp_budgets import DEFAULT_MAX_CONCURRENT_READS, ReadSlots
        from app.mcp_tools import register

        register(
            server,
            lock,
            base_url=postgrest_url,
            slots=ReadSlots(
                max_concurrent_reads
                if max_concurrent_reads is not None
                else DEFAULT_MAX_CONCURRENT_READS
            ),
        )

    _register_health(server, lock=lock, key_set=verifier.key_set)
    return server


def _register_health(server: Any, *, lock: Any, key_set: Any) -> None:
    """Liveness and readiness, container-local and unauthenticated (ADR 0128).

    **Readiness reports only what startup established** and calls nothing. This
    runtime holds no credential and opens no connection, so it has no dependency
    of its own to probe -- and a readiness answer that reached PostgREST would
    take this container out of service for a fault that is not its own. What it
    can honestly say is that the key set and the capability lock are both loaded,
    which is the whole of what this process needs to serve a request.

    Neither route is published. No Traefik router names them, so they are
    reachable only from inside the internal network, and the public answer to
    "is this project up" stays `__apg/healthz` (D231).
    """
    from starlette.responses import JSONResponse

    @server.custom_route("/health/live", methods=["GET"])
    async def live(request: Any) -> Any:
        """The event loop is running. Touches nothing else, on purpose."""
        del request
        return JSONResponse({"status": "live"})

    @server.custom_route("/health/ready", methods=["GET"])
    async def ready(request: Any) -> Any:
        """Both startup artefacts are held. Invents no dependency endpoint."""
        del request
        holdings = {
            "key_set": key_set is not None and bool(getattr(key_set, "keys", None)),
            "capability_lock": lock is not None,
        }
        if all(holdings.values()):
            return JSONResponse({"status": "ready", "holds": sorted(holdings)})
        # 503, and it names WHICH artefact is missing -- this route is private,
        # so the reader is an operator rather than a caller, and ADR 0097's
        # silence is about what an unauthenticated CALLER may learn.
        return JSONResponse(
            {"status": "unready", "missing": sorted(k for k, v in holdings.items() if not v)},
            status_code=503,
        )


def create_mcp_app() -> Starlette:
    """Build the agent plane, or fail the start.

    The order is the one `main.lifespan` uses and for the same reason: settings,
    then key material, each step cheaper to fail than the next. There is no
    third step here, because there is no pool -- which is the whole shape of
    this mode.

    Nothing is served if the key set cannot be read. A fourth verifier that
    started without one would refuse every request with `no key with kid`, and a
    container that starts is a container that looks deployed (D381).
    """
    settings = settings_module.load_mcp()
    key_set = LocalKeySet.from_path(settings.jwks_file)
    # The lock is loaded BEFORE the server is built, so a lock this runtime
    # cannot parse fails the start rather than producing a server with no tools.
    # An agent plane answering discovery with an empty list is a surface nobody
    # can tell from a correctly-empty one.
    lock = load_lock(settings.capability_lock_file)
    # Recorded here and nowhere else: after `load_lock` has accepted it and
    # before a server exists to serve it, so the module-level value and the
    # server's lock are the same object by construction rather than by two
    # assignments agreeing (D1153).
    global LOADED_LOCK
    LOADED_LOCK = lock
    # And written where a SECOND process can read it (D1286). The global above
    # is invisible to `docker exec python -c`, which is how the deploy asks.
    record_loaded_lock(lock)
    # Session 31 (ADR 0223). The two instruments, wired AFTER the lock, because
    # the tool roster is the lock's: configuring before it would have to pass a
    # guess at the tool names, and `mcp_metrics` substitutes `LABEL_OTHER` for
    # any value outside the set it was given -- so every tool call would be
    # counted under `other` and the counter would be useless in exactly the way
    # that looks like it is working.
    #
    # The two closed sets arrive as arguments rather than being imported there,
    # which is `configure`'s own decision: `mcp_tools` owns the roster and
    # imports `mcp_telemetry`, so importing either from `mcp_metrics` would
    # close a real cycle.
    #
    # `mcp_tracing.configure` is NOT called, and that is the standing decision
    # its own module records. Tracing has no reader, and a span carries
    # request-shaped values a metric does not.
    metrics_on = mcp_metrics.configure(
        endpoint=settings.otlp_endpoint,
        service_name="apg-mcp",
        tool_names=tuple(tool.name for tool in lock.tools),
        outcomes=mcp_telemetry.OUTCOMES,
    )
    if not metrics_on:
        # Said rather than inferred, for the reason `configure` returns a bool
        # at all. A deployment with no collector is a decision, and the line an
        # operator needs is the one that distinguishes it from an export that
        # is failing silently.
        mcp_telemetry.LOGGER.warning("metrics are not exported: no APG_OTLP_ENDPOINT")
    server = build_server(
        AgentTokenVerifier(key_set, issuer=settings.issuer, audience=settings.audience),
        project_key=settings.project_key,
        postgrest_url=settings.postgrest_url,
        lock=lock,
        max_concurrent_reads=settings.max_concurrent_reads,
    )
    # `stateless_http`, so one HTTP request is one complete exchange. It is what
    # makes "cached for one HTTP request" a statement about a boundary the
    # transport draws rather than about a session this runtime would have to
    # keep, and a session store is state the agent plane deliberately has none
    # of (ADR 0125).
    #
    # The published path is `/mcp` and the router strips NOTHING (ADR 0128), so
    # the path served here and the path published at the edge are the same
    # string. The health routes mount at the root beside it and no router names
    # them.
    application = server.http_app(path=MCP_ROUTE_PATH, stateless_http=True)

    # Outermost, so a browser request is refused before anything reads a body or
    # builds a request object (ADR 0128). Wrapped around the finished app rather
    # than passed as FastMCP `middleware=`, because that list is the MCP-message
    # middleware chain -- it runs after the transport has already accepted the
    # request, which is too late for a check whose value is that the request
    # costs nothing.
    #
    # `StampRequestId` sits INSIDE the origin refusal, and the order is a
    # decision (ADR 0160): a request refused for carrying `Origin` never reached
    # the application, so there is nothing to correlate and no id worth minting.
    # One id per *served* HTTP request, not per byte that arrived.
    return RefuseBrowserOrigins(StampRequestId(application))
