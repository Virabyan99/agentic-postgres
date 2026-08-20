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

from typing import TYPE_CHECKING, Any

from mcp.types import LATEST_PROTOCOL_VERSION

from app import settings as settings_module
from app.claims import ClaimError, verify_claims
from app.mcp_authorization import AgentContextMiddleware
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

__all__ = [
    "ACCEPTED_TOKEN_USE",
    "AUTHORIZATION_SPEC_CONFORMANT",
    "MINIMUM_AUTHZ_VERSION",
    "PROTOCOL_REVISION",
    "AgentTokenVerifier",
    "build_server",
    "create_mcp_app",
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


class AgentTokenVerifier:
    """FastMCP's `TokenVerifier`, holding the rendered key set and nothing else.

    Structurally typed against the framework rather than subclassing it: the
    protocol is one coroutine, `verify_token(token: str) -> AccessToken | None`,
    measured against the locked version. Constructing this class therefore
    requires no framework import, so the refusal branches are testable without
    one -- and the framework's own object is built only on the accepting path.

    **Every refusal returns `None`**, which the framework renders as a 401 with
    no detail. That is ADR 0097's split applied at the outermost door: a
    structural refusal tells an unauthenticated caller nothing, because anything
    it said would be a claim about state to somebody who has not proved they may
    ask about state.
    """

    def __init__(self, key_set: LocalKeySet, *, issuer: str, audience: str) -> None:
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


def build_server(verifier: AgentTokenVerifier, *, project_key: str, postgrest_url: str) -> Any:
    """The FastMCP server, with no tools registered.

    Run 6 registers exactly four, from the compiled capability lock. Until then
    an agent that authenticates successfully is told there are none, which is
    true -- as against a placeholder, which would be a discovery response that
    lies. D421 is the standing lesson about a tool list that advertises what it
    will refuse.

    **The authorization middleware is here from Run 5, before any tool exists**,
    and that order is deliberate. It resolves the caller's context on the way in
    (ADR 0125), so a tool added in Run 6 cannot be written against a request that
    has no context: there is no such request. A middleware added afterwards would
    have to be remembered by every tool author, which is the shape of D333.
    """
    from fastmcp import FastMCP

    return FastMCP(
        name=f"agentic-postgres/{project_key}",
        auth=verifier,
        middleware=[AgentContextMiddleware(postgrest_url)],
        # Details of an internal failure are not an agent's to read (ADR 0097).
        mask_error_details=True,
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
    server = build_server(
        AgentTokenVerifier(key_set, issuer=settings.issuer, audience=settings.audience),
        project_key=settings.project_key,
        postgrest_url=settings.postgrest_url,
    )
    # `stateless_http`, so one HTTP request is one complete exchange. It is what
    # makes "cached for one HTTP request" a statement about a boundary the
    # transport draws rather than about a session this runtime would have to
    # keep, and a session store is state the agent plane deliberately has none
    # of (ADR 0125).
    return server.http_app(path="/mcp", stateless_http=True)
