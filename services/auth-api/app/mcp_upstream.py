"""The agent plane's one call upstream: the caller's own token, forwarded.

**This module is the second row in ADR 0124's transport allowlist**, and the
reason is here rather than only there: the agent plane resolves an agent's
context by asking PostgREST, as the agent, with the agent's own bearer token.
There is no version of that which does not construct an HTTP client.

**What makes this not a confused deputy is what the runtime does not have.** No
signing key, so it cannot mint a token (ADR 0121). No database credential, so it
cannot open a connection (D407). The only credential in the process is the one
the caller presented, and it goes upstream unchanged — not re-signed, not
exchanged, not accompanied by a header naming a role, a subject or an owner. The
absence of a service identity is what makes the deputy unconstructible rather
than merely unwritten (ADR 0125).

**Exactly one row is a context; everything else is a refusal.** Measured against
a live PostgREST on the locked digest, with all eighteen migrations applied:

    agent token            -> 200, a JSON ARRAY of one object
    no Authorization       -> 401, and the body is `42501 permission denied`
    a human access token   -> 403, `42501 permission denied for function ...`
    an unknown agent       -> 401, `PT401 / AP401 identity is no longer current`
    a forged signature     -> 401, `PGRST301 none of the keys ...`

The fourth of those is why the zero-rows branch is a refusal here and not an
empty context: the migration's comment says the function returns zero rows for a
caller that is not an agent, and over HTTP **the pre-request hook refuses first**,
so that branch is unreachable for a stale or unknown agent. A 200 with no rows
would therefore mean something unexpected, not "no agent" — and treating it as
an empty context would hand a tool an agent with no scopes.

The second is why status alone never becomes a message: a 401 here can be a bad
signature, a stale identity, or a missing privilege, and the runtime is in no
position to tell a caller which (ADR 0097).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

#: The RPC this module calls, and the only one. Named as a constant because
#: `mcp_upstream` is not a general PostgREST client and must not become one:
#: Run 6's tools reach the read surface through their own adapter, with a
#: header allowlist and encoded query construction, and a module that already
#: knew how to POST anywhere would be the obvious place to put them.
AGENT_CONTEXT_PATH = "/rpc/mcp_agent_context"

#: The singular representation. Measured (M2): PostgREST answers a
#: TABLE-returning function with a JSON array by default, and with a single
#: object under this Accept. The ARRAY form is what this module asks for --
#: deliberately, so that "how many rows came back" is a question this code
#: answers rather than one PostgREST answers with a 406 whose meaning would then
#: have to be decoded. One row is a context; zero or two are refusals, and the
#: distinction has to be visible here.
ARRAY_ACCEPT = "application/json"

#: How long the agent plane waits for its own database's front door, in seconds.
#: PostgREST is on the internal network, one hop away. A longer timeout would
#: hold an MCP request open past the point where the caller has given up, and a
#: shorter one would turn a slow schema-cache reload into a refusal.
UPSTREAM_TIMEOUT_SECONDS = 10


class UpstreamRefusal(Exception):
    """The caller may not proceed, and the reason is not the caller's to read.

    Carries a short machine reason for this process's own telemetry -- never for
    a response body. ADR 0097's split: a structural refusal tells an
    unauthenticated or unauthorised caller nothing, because anything it said
    would be a claim about state to somebody who has not established they may
    ask about state.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class AgentContext:
    """One agent's own context, exactly as `api.mcp_agent_context` returns it.

    Frozen, and every field is required. There is no partially-populated form:
    a context is what one row of that function says, or it is a refusal.

    `owner_id` is the field the rest of the agent plane is about — ADR 0117's
    decision that an agent request runs under its **owner's** identity. It is
    carried here so that Run 6's tools can name it without asking again.
    """

    agent_id: str
    role_name: str
    scopes: tuple[str, ...]
    authz_version: int
    owner_id: str

    @classmethod
    def from_row(cls, row: Any) -> AgentContext:
        """Parse one row, strictly, or refuse.

        Strict because this is a security boundary reading a document over the
        network. A row missing `owner_id`, or carrying it as something other
        than a string, would otherwise reach ADR 0117's identity decision as
        `None` -- and `None` is a value that compares equal to nothing and is
        therefore refused by every policy in a way that looks like an empty
        result rather than a fault.
        """
        if not isinstance(row, dict):
            raise UpstreamRefusal("the agent context row is not an object")

        required = ("agent_id", "role_name", "scopes", "authz_version", "owner_id")
        missing = [name for name in required if name not in row]
        if missing:
            raise UpstreamRefusal(f"the agent context row is missing {missing}")

        for name in ("agent_id", "role_name", "owner_id"):
            if not isinstance(row[name], str) or not row[name].strip():
                raise UpstreamRefusal(f"{name} is not a non-empty string")

        scopes = row["scopes"]
        if not isinstance(scopes, list) or not all(isinstance(item, str) for item in scopes):
            raise UpstreamRefusal("scopes is not an array of strings")

        version = row["authz_version"]
        # `bool` is an `int` in Python, and `True` where a version is expected
        # would compare equal to 1 for the rest of this object's life.
        if not isinstance(version, int) or isinstance(version, bool):
            raise UpstreamRefusal("authz_version is not an integer")

        return cls(
            agent_id=row["agent_id"],
            role_name=row["role_name"],
            scopes=tuple(scopes),
            authz_version=version,
            owner_id=row["owner_id"],
        )


def parse_agent_context(status: int, body: bytes) -> AgentContext:
    """The whole response contract, as a pure function.

    Separated from the request so that every refusal branch is reachable in a
    test without a socket -- which is the only way the branches that matter get
    exercised at all. `resolve_agent_context` is the thin part that has a URL.
    """
    if status != 200:
        # Deliberately not relayed. A 401 here is a bad signature, a stale
        # identity or a missing privilege (measured: all three occur), and this
        # process cannot tell a caller which without describing state.
        raise UpstreamRefusal(f"upstream refused with status {status}")

    try:
        document = json.loads(body)
    except ValueError as error:
        raise UpstreamRefusal(f"upstream body is not JSON: {error}") from error

    if not isinstance(document, list):
        raise UpstreamRefusal("upstream body is not an array of rows")

    if len(document) != 1:
        # Zero is the case worth the sentence. The function's own comment says
        # it returns zero rows for a caller that is not an agent -- and over
        # HTTP the pre-request hook refuses such a caller first (measured, M5),
        # so zero rows here is not "no agent", it is a state the product does
        # not produce. Continuing with an empty context would give a tool an
        # agent with no scopes and no owner.
        raise UpstreamRefusal(f"the agent context is {len(document)} rows, not one")

    return AgentContext.from_row(document[0])


def resolve_agent_context(base_url: str, token: str) -> AgentContext:
    """Ask PostgREST who the caller is, as the caller.

    `token` is the **original compact token** the caller presented. It is placed
    in `Authorization` and nowhere else, and no other header names a principal:
    no role, no subject, no owner, no `request.jwt.claims`. That is ADR 0125's
    first two clauses, and they are visible in this function in their entirety.
    """
    request = urllib.request.Request(  # noqa: S310 -- a derived internal URL, http on the internal network
        f"{base_url.rstrip('/')}{AGENT_CONTEXT_PATH}",
        data=b"{}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": ARRAY_ACCEPT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(  # noqa: S310
            request, timeout=UPSTREAM_TIMEOUT_SECONDS
        ) as response:
            return parse_agent_context(int(response.status), response.read())
    except urllib.error.HTTPError as error:
        # 4xx and 5xx arrive here rather than as a return value. The body is
        # read and discarded: PostgREST's error documents name functions, error
        # codes and hints, and none of that is an agent's to receive.
        error.read()
        raise UpstreamRefusal(f"upstream refused with status {error.code}") from error
    except OSError as error:
        # The upstream is unreachable. A refusal, not a degraded mode: there is
        # no cached identity to fall back to, deliberately (ADR 0125).
        raise UpstreamRefusal(f"upstream unreachable: {type(error).__name__}") from error
