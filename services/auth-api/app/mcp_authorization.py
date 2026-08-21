"""One agent context per HTTP request, and it cannot outlive the request.

ADR 0125. The agent plane resolves the caller's context **before discovery or
execution**, from PostgREST, using the caller's own token — and holds it for
exactly one request.

**Why a `ContextVar` and not a dictionary**, measured rather than reasoned:
twelve concurrent requests carrying twelve different tokens, against both
implementations at once.

    ContextVar, reset in a `finally`   0 of 12 saw another caller's context
    CONTROL -- a module-level dict    11 of 12 saw another caller's context

And the control's failure mode is why the concurrency arm exists at all: run
**sequentially**, the module-level dict is correct every time. A test written
against sequential requests would have passed the broken implementation, which
is the shape of half the defects in this repository's history.

**Why the value is keyed by a fingerprint** even though the variable is already
per-request: it is belt and braces with a specific job. If a value ever did
outlive its request — a framework change, a task reused, a bug here — a
fingerprint mismatch turns a **leak into a miss**, and a miss resolves again.
Without the key, the same bug would silently serve one agent another's identity.
The fingerprint is a SHA-256 of the token; it is not reversible, and it is never
logged, returned, or put in a tool result.
"""

from __future__ import annotations

import contextvars
import hashlib
from dataclasses import dataclass
from typing import Any

from fastmcp.server.middleware import Middleware as _Middleware

from app.mcp_upstream import AgentContext, UpstreamRefusal, resolve_agent_context

#: The resolved context for the request currently being served, or `None`.
#:
#: Module-level because a `ContextVar` must be, and per-request in fact because
#: that is what a `ContextVar` is: each asyncio task inherits a copy of the
#: context and its writes are invisible to every other task. `None` outside a
#: request is the honest default -- there is no "last caller".
_CURRENT: contextvars.ContextVar[_Held | None] = contextvars.ContextVar(
    "apg_agent_context", default=None
)


@dataclass(frozen=True, slots=True)
class _Held:
    """A context, the token it was resolved for, and that token's fingerprint.

    The token is carried because Run 6's tools forward it: the same compact
    string the caller presented goes upstream for the read, exactly as it did
    for the context lookup (ADR 0125). Holding it here rather than re-reading it
    from the framework inside each tool keeps one answer per request to the
    question "who is calling" -- and the fingerprint beside it is what proves the
    two halves belong together.
    """

    fingerprint: str
    token: str
    context: AgentContext


def fingerprint(token: str) -> str:
    """A non-reversible identifier for one token.

    SHA-256 over the compact token. Used only to check that a held context
    belongs to the token being served; never logged, never returned, never
    compared against anything a caller supplies.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def current_agent_context() -> AgentContext:
    """The calling agent's context, or a refusal.

    What Run 6's tools call. They never resolve a context themselves, so there
    is exactly one resolution per request and exactly one place that decides
    what a refusal is.

    Raises rather than returning `None`, because every caller of this needs a
    context to do anything at all, and an `Optional` return is an invitation to
    a tool that carries on with an owner of `None` -- which compares equal to
    nothing and is refused by every policy in a way that reads as an empty
    result rather than as a fault.
    """
    held = _CURRENT.get()
    if held is None:
        raise UpstreamRefusal("no agent context was resolved for this request")
    return held.context


def current_token() -> str:
    """The compact token this request presented, for forwarding upstream.

    Read from the same held value the context came from, and guarded by the
    fingerprint: a token whose digest does not match the one the context was
    resolved for is refused rather than forwarded, which is the check that turns
    a held value outliving its request into a refusal instead of one caller's
    read running as another.
    """
    held = _CURRENT.get()
    if held is None:
        raise UpstreamRefusal("no agent context was resolved for this request")
    if fingerprint(held.token) != held.fingerprint:  # pragma: no cover -- corruption only
        raise UpstreamRefusal("the held token does not match its fingerprint")
    return held.token


def _resolve(base_url: str, token: str) -> _Held:
    return _Held(
        fingerprint=fingerprint(token),
        token=token,
        context=resolve_agent_context(base_url, token),
    )


class AgentContextMiddleware(_Middleware):
    """Resolves the caller's context once, on the way in.

    **It subclasses the framework's `Middleware`, and Run 5's decision not to
    was wrong** (D450). This docstring used to say it was "structurally typed
    against FastMCP's `Middleware` rather than subclassing it, for the reason
    `AgentTokenVerifier` is" -- and that reason was already wrong when it was
    written: the framework's pipeline does not duck-type a middleware, so a
    plain class raised `'AgentContextMiddleware' object is not callable` the
    first time a request reached it.

    Nothing caught it because nothing had ever run a request through the
    pipeline: every test called `on_request` directly. **That is D444's family,
    and its second instance** -- Run 7 found the verifier and this one survived,
    because the seam nobody crossed was the same seam.

    What survives of the original reasoning is narrower than it claimed: the
    refusal branches here are still reachable without a framework object,
    because `_resolve` and `current_agent_context` are module functions. That is
    a property of how the logic is split, not of how the class is typed.

    **`on_request`, not `on_call_tool`.** Measured: `on_request` fires exactly
    once per HTTP request and before both `on_list_tools` and `on_call_tool`, so
    discovery and execution see the same context and neither can run without
    one. Hooking the two separately would resolve twice for a request that did
    both, and would leave a third method added later with no context at all.

    **Nothing here refuses an unauthenticated caller**, and that is not an
    omission: the framework's auth runs first, and an unauthenticated request is
    answered 401 with no middleware hook reached at all -- measured, with the
    absence of any hook as the observation. ADR 0115's "refused before any
    lookup" is therefore structural rather than something this class enforces.
    """

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self._base_url = base_url

    async def on_request(self, context: Any, call_next: Any) -> Any:
        from fastmcp.server.dependencies import get_access_token

        granted = get_access_token()
        if granted is None:  # pragma: no cover -- the framework 401s before this
            raise UpstreamRefusal("no verified token on an authenticated request")

        held = _resolve(self._base_url, granted.token)
        reset = _CURRENT.set(held)
        try:
            return await call_next(context)
        finally:
            # `reset`, not `set(None)`. Reset restores whatever this context had
            # before, which is the only correct answer under nesting -- and it
            # is what makes "never across requests" a property of the mechanism
            # rather than of this function remembering to clear up.
            _CURRENT.reset(reset)
