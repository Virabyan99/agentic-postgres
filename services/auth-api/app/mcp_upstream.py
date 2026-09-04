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

#: The context RPC, named as a constant so no caller can select it.
#:
#: Run 5's note here said this module "is not a general PostgREST client and must
#: not become one", with Run 6's tools reaching the read surface through their
#: own adapter. **Run 6 put the executor here instead**, and the reason is ADR
#: 0124: a second module with a transport would be a third allowlist row, and
#: two places that build HTTP requests to the same upstream are two places to
#: review and one of them will drift. This module is the single transport to
#: PostgREST. What keeps it from being a *general* client is not its size: it is
#: that `execute` accepts an `UpstreamRequest` built by `mcp_query` from the
#: lock, and there is no code path here that takes a path or a method from a
#: caller.
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


def resolve_agent_context(base_url: str, token: str, *, request_id: str) -> AgentContext:
    """Ask PostgREST who the caller is, as the caller.

    `token` is the **original compact token** the caller presented. It is placed
    in `Authorization` and nowhere else, and no other header names a principal:
    no role, no subject, no owner, no `request.jwt.claims`. That is ADR 0125's
    first two clauses, and they are visible in this function in their entirety.

    **The id is carried here too**, because this is the FIRST of the three or
    four upstream requests one tool call makes (ADR 0141). Leaving it off would
    make the one request ADR 0125 pays for on every call the one nothing can
    correlate.
    """
    from app.mcp_query import REQUEST_ID_HEADER

    request = urllib.request.Request(  # noqa: S310 -- a derived internal URL, http on the internal network
        f"{base_url.rstrip('/')}{AGENT_CONTEXT_PATH}",
        data=b"{}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": ARRAY_ACCEPT,
            REQUEST_ID_HEADER: request_id,
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


def execute(base_url: str, token: str, request: Any, *, request_id: str) -> list[dict[str, Any]]:
    """Run one built request and return its rows.

    `request` is an `mcp_query.UpstreamRequest`, whose every member came from the
    lock or was escaped for the position it occupies (ADR 0127). **Nothing here
    accepts a path, a method or a query from a caller** — that is what keeps a
    single transport module from being a general client.

    The headers are `mcp_query.FORWARDED_HEADERS` and nothing else. A caller's
    `Prefer` would change the response shape and cost (`count=exact`,
    `return=representation`); a caller's `Range` would move the window past the
    lock's `max_rows`. None of them is forwarded, and neither is `Accept`.

    The rows are returned as PostgREST sent them, which is the point: the RLS
    that constrains a row constrains this result, and this process adds no
    filtering of its own that could disagree with the database's.
    """
    status, body = _dial(base_url, token, request, request_id=request_id)
    if status != 200:
        # The body is discarded UNREAD for a read (ADR 0097, D433): PostgREST's
        # error documents name functions, codes and hints, and none of that is
        # an agent's to receive.
        raise UpstreamRefusal(f"upstream refused with status {status}")
    return _rows(status, body)


def execute_write(
    base_url: str,
    token: str,
    request: Any,
    *,
    max_affected_rows: int,
    request_id: str,
    idempotency_key: str,
) -> list[dict[str, Any]]:
    """Run one built WRITE request; return its rows or translate its refusal.

    Two ways this differs from `execute`, both measured (rig4, ADR 0139):

    **The response is a single JSON object**, because both write RPCs are
    `RETURNS <composite>` rather than `SETOF` -- PostgREST renders that as one
    object where a set is an array. The object becomes a one-row list here, so
    the bound check below is arithmetic over rows either way.

    **A refused response's body is read for its `code` member and nothing
    else.** The product's own write refusals cross HTTP as `PT` errcodes
    (`409/PT409` for the compare-and-swap, `404/PT404` for a missing row), and
    the STATUS cannot classify them -- a missing argument is `404 PGRST202`,
    the same status as "no such task" with the opposite meaning. An enumerated
    code becomes an `AgentVisible` with this repository's own sentence;
    everything else, message and hint included, is discarded and the refusal
    stays structural.

    `max_affected_rows` is the lock's bound, checked **against the response**
    and never trusted (D487): both current writes return exactly one row, so
    the check firing means the function's shape changed underneath the lock --
    a fault worth failing loudly, after the fact, because the write has already
    committed and pretending otherwise would be a record that lies.
    """
    from app.mcp_errors import write_refusal

    # **Required, with no default**, for `request_id`'s reason (ADR 0141's
    # shape, applied to ADR 0181's guarantee). A default would let a write reach
    # PostgREST with no key and be deduplicated by nothing, silently -- and the
    # database would refuse it, so the failure would arrive as a `PT412` nobody
    # could explain rather than as the type error it is.
    status, body = _dial(
        base_url, token, request, request_id=request_id, idempotency_key=idempotency_key
    )
    if status != 200:
        visible = write_refusal(_refusal_code(body))
        if visible is not None:
            raise visible
        raise UpstreamRefusal(f"upstream refused with status {status}")

    try:
        document = json.loads(body)
    except ValueError as error:
        raise UpstreamRefusal(f"upstream body is not JSON: {error}") from error
    if isinstance(document, dict):
        rows: list[dict[str, Any]] = [document]
    elif isinstance(document, list) and all(isinstance(row, dict) for row in document):
        rows = document
    else:
        raise UpstreamRefusal("upstream body is neither a row nor an array of rows")

    if len(rows) > max_affected_rows:
        raise UpstreamRefusal(
            f"the write affected {len(rows)} rows against a bound of {max_affected_rows}; "
            "the operation's shape has changed underneath the lock"
        )
    return rows


def _refusal_code(body: bytes) -> str:
    """The `code` member of a refused response, or the empty string.

    The one field the write path reads (ADR 0139). Anything malformed is the
    empty string, which maps to nothing and stays masked -- a body this
    function cannot parse must not become a body it guesses about.
    """
    try:
        document = json.loads(body)
    except ValueError:
        return ""
    code = document.get("code") if isinstance(document, dict) else None
    return code if isinstance(code, str) else ""


def _dial(
    base_url: str,
    token: str,
    request: Any,
    *,
    request_id: str,
    idempotency_key: str | None = None,
) -> tuple[int, bytes]:
    """One HTTP exchange with the upstream, status and body, refusals included.

    The transport half every caller shares, so there is still exactly one place
    a request to PostgREST is constructed (ADR 0124). The body sent is the
    request's own (D477) -- built and serialized by `mcp_query`, never composed
    here.

    **`request_id` is a required keyword with no default** (ADR 0141). A default
    would let a caller omit it silently, and "every upstream request this plane
    makes carries an id" is precisely the guarantee -- one that a `None`
    slipping through would break in the quietest way available.

    **`idempotency_key` selects a ROSTER, it does not add an optional header**
    (ADR 0181). Supplying it means this is the write branch and the check below
    is against `WRITE_FORWARDED_HEADERS`; omitting it means the read branch and
    `FORWARDED_HEADERS`. Either way the comparison stays an EQUALITY, which is
    the whole reason the two rosters are separate rather than one loose one --
    a subset check here is D300's shape, and both of Session 8's allowlist
    failures (D468) were right to fail.
    """
    from app.mcp_query import (
        FORWARDED_HEADERS,
        IDEMPOTENCY_KEY_HEADER,
        REQUEST_ID_HEADER,
        WRITE_FORWARDED_HEADERS,
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": ARRAY_ACCEPT,
        REQUEST_ID_HEADER: request_id,
    }
    allowed = FORWARDED_HEADERS
    if idempotency_key is not None:
        headers[IDEMPOTENCY_KEY_HEADER] = idempotency_key
        allowed = WRITE_FORWARDED_HEADERS
    # **This guard moved in the same commit as the allowlist it reads** (D477).
    if set(headers) != set(allowed):  # pragma: no cover -- a guard on the pair
        raise UpstreamRefusal("the forwarded header set and the allowlist disagree")

    built = urllib.request.Request(  # noqa: S310 -- a derived internal URL, path from the lock
        f"{base_url.rstrip('/')}{request.target}",
        data=request.body,
        headers={
            **headers,
            **({"Content-Type": "application/json"} if request.body is not None else {}),
        },
        method=request.method.upper(),
    )
    try:
        with urllib.request.urlopen(  # noqa: S310
            built, timeout=max(request.timeout_ms, 1) / 1000
        ) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as error:
        return int(error.code), error.read()
    except OSError as error:
        raise UpstreamRefusal(f"upstream unreachable: {type(error).__name__}") from error


def _rows(status: int, body: bytes) -> list[dict[str, Any]]:
    """A row array, or a refusal. The same strictness `parse_agent_context` uses.

    A non-200 is a refusal that names no upstream code, for D433's reason: a 401
    here can be a bad signature, a stale identity or a missing privilege, and
    the three are indistinguishable by status.
    """
    if status != 200:
        raise UpstreamRefusal(f"upstream refused with status {status}")
    try:
        document = json.loads(body)
    except ValueError as error:
        raise UpstreamRefusal(f"upstream body is not JSON: {error}") from error
    if not isinstance(document, list) or not all(isinstance(row, dict) for row in document):
        raise UpstreamRefusal("upstream body is not an array of rows")
    return document
