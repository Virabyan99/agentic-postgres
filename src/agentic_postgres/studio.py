"""Studio's decisions, with no I/O in any of them (ADR 0205).

`bin/studio.py` is the process: it binds the socket, holds the human's token,
reads the deployed document and makes every upstream request. This module is
everything that process DECIDES -- which address to use, whether the served
surface is the one the IR describes, what a structured query becomes as a URL,
which requests are refused and with what status, which session was Studio's own,
and what may be written to a log.

**The split is not tidiness; it is what makes the refusals reachable by a
test.** `request_checks` is one function returning a status or `None`, so a
battery can drive all eleven of its branches without a socket, and the handler
above it cannot answer a request without having called it. The same argument
gives `rest_query` its shape: the browser sends structure, this function turns
structure into exactly one PostgREST `GET`, and every refusal in it happens
before `bin/studio.py` has opened a connection.

**What is not here, by decision** (ADR 0205): SQL in any form; a path that
composes a URL from something a page sent; a JWT verifier; a reader of the
deployed document for anything but an address (ADR 0158); a second canonical
form for an OpenAPI document -- `openapi_normalize` is the one this repository
has and Studio uses it exactly as the capture does.

**The module imports the standard library and `agentic_postgres`, and nothing
else** (ADR 0093, HOST_PACKAGES), because `bin/studio.py` is an operator command
and runs where the host's Python is.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass
from typing import Any

from agentic_postgres import REPO_ROOT, openapi_normalize
from agentic_postgres.client_ir import IR

__all__ = [
    "ASSET_ROOT",
    "AUDIT_PAGE_LIMIT",
    "BIND_ADDRESS",
    "CONTENT_SECURITY_POLICY",
    "CUSTOM_HEADER",
    "IS_NULL_OPERAND",
    "LAUNCH_COOKIE",
    "LOOPBACK_HOSTS",
    "OPERATOR_WIRE_FORMS",
    "SECURITY_HEADERS",
    "STUDIO_MAX_ROWS",
    "STUDIO_REFRESH_BEFORE_SECONDS",
    "SURFACE_ANSWERS",
    "AddressBook",
    "ForwarderOperation",
    "StudioError",
    "SurfaceAnswer",
    "address_book",
    "audit_view_header",
    "forwarder_table",
    "own_session",
    "redact_for_log",
    "request_checks",
    "rest_query",
    "revoke_request",
    "schema_view",
    "surface_answer",
]

# ---------------------------------------------------------------------------
# Constants that are decisions
# ---------------------------------------------------------------------------

#: The three first-party files the page is made of, and the one place their
#: directory is named.
#:
#: Here rather than in `bin/studio.py` for a guard's reason and a rule's. The
#: guard: `test_no_operator_command_puts_a_service_directory_on_the_path` flags
#: any `bin/*.py` holding both `"services"` and `sys.path`, which is the shape
#: `bin/auth-admin.py` had when it made an image-only package importable in a
#: checkout and nowhere else (D292) -- and a command that merely READS three
#: files from `services/` is not that, but the scan cannot tell and should not
#: have to. The rule: a derived path is derived once (ADR 0002).
#:
#: `services/studio/` is not a service. It builds no image and no deploy runs
#: it; it is three files an operator command hands to a browser on loopback.
ASSET_ROOT = REPO_ROOT / "services" / "studio"

#: The only address Studio binds, and there is deliberately no flag for another
#: one (ADR 0205, D1245). Binding elsewhere would need TLS that the edge cannot
#: give a workstation process, its own CSP origin, and a threat model for a
#: token-holding process on a LAN -- none of which this session builds. A person
#: who wants that edits this line, which is where `bin/dev-token.sh` puts the
#: same kind of refusal: *"adding one would be a change to the security
#: posture."* A refusal with a switch is a decision deferred to whoever finds
#: the switch (D694).
BIND_ADDRESS = "127.0.0.1"

#: The ceiling on a query builder page. A human reading a table is not an
#: agent spending a budget, so this is not the lock's `max_rows` and must not
#: drift into being read as it.
STUDIO_MAX_ROWS = 1000

#: What the audit view asks the endpoint for, which is the endpoint's own
#: documented maximum. The page is fetched whole and rendered whole; a view
#: filter hides rows in the browser and the header says so (D1248).
AUDIT_PAGE_LIMIT = 500

#: How close to expiry the access token may get before Studio refreshes it. The
#: token lives `claims.MAX_TTL_SECONDS` (900 s), so this is a margin and not a
#: schedule: Studio refreshes when a request finds the token near expiry.
STUDIO_REFRESH_BEFORE_SECONDS = 120

#: The cookie the browser holds INSTEAD of the token (ADR 0205). Its value is a
#: per-launch key, it is `HttpOnly` so no script can read it and `SameSite=Strict`
#: so no other site can cause it to be sent.
LAUNCH_COOKIE = "apg_studio"

#: The header every forwarded call must carry. It is not a CORS-simple header,
#: so a cross-origin page cannot set it without a preflight -- and `OPTIONS` is
#: refused, so no preflight succeeds.
CUSTOM_HEADER = "X-Apg-Studio"

#: Hosts that may be reached over plain `http`, and the reason is one sentence:
#: loopback never leaves the machine. It is the same reason Studio itself serves
#: plain HTTP on `127.0.0.1`. Any other host must be `https` (D1254).
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1", "[::1]")

#: Stricter than `services/docs`'s, and the difference is deliberate: that page
#: carries `'unsafe-inline'` in `style-src` because Scalar writes styles at
#: runtime. Nothing here does, so nothing here allows it. `default-src 'none'`
#: first, so anything not named is refused rather than inherited.
CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'none'",
        "script-src 'self'",
        "style-src 'self'",
        "connect-src 'self'",
        "img-src 'self'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
    )
)

#: On every response, including refusals and redirects. A response without the
#: policy is a response that opted out of it, which is the note
#: `services/docs/serve.py` wrote for its own redirect.
SECURITY_HEADERS: dict[str, str] = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    # Every page here is rendered from a token-holding process's answers. None
    # of it may be stored by anything between this process and the browser --
    # and there is nothing between them, which is the point.
    "Cache-Control": "no-store",
}

#: The four answers a launch can end in, copied from a generated client's
#: `init()` (ADR 0204) because the question is the same one: is the surface this
#: artefact describes the surface being served? Three outcomes plus the answer,
#: which is ADR 0195 -- `unreachable` and `unreadable` are two different *I
#: could not determine it*s and neither is `stale_contract`.
SURFACE_ANSWERS = ("ok", "stale_contract", "unreachable", "unreadable")

#: How each contract operator is spelled on the wire, and how many operands it
#: takes.
#:
#: **A second copy of `app.mcp_query.OPERATORS`, and a compared pair** (D486).
#: That table lives in the auth service, which this module may not import: an
#: operator command reaches only the standard library and `agentic_postgres`
#: (ADR 0093). `test_the_operator_wire_forms_are_the_runtimes` compares the two
#: so neither becomes a second authority -- the alternative, moving the table
#: into this package, is an edit to a released service module for a reason that
#: is not that module's.
#:
#: `is_null` is the one whose wire form is not its name, and the one that takes
#: no operand from the caller.
OPERATOR_WIRE_FORMS: dict[str, tuple[str, str]] = {
    "eq": ("eq", "scalar"),
    "neq": ("neq", "scalar"),
    "gt": ("gt", "scalar"),
    "gte": ("gte", "scalar"),
    "lt": ("lt", "scalar"),
    "lte": ("lte", "scalar"),
    "in": ("in", "list"),
    "is_null": ("is", "none"),
}

#: What `is_null` sends. A constant because it is the one operand this module
#: emits that did not come from a caller, and it must not look like one.
IS_NULL_OPERAND = "null"

_UUID = re.compile(
    r"\A[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z"
)

#: The refusal statuses, each answering a different question about a request.
_MISDIRECTED = 421
_UNAUTHENTICATED = 401
_FORBIDDEN = 403
_METHOD_NOT_ALLOWED = 405
_UNPROCESSABLE = 422


class StudioError(ValueError):
    """A refusal with the process exit code it would end the command with.

    A `ValueError` because every one of them is about a value -- a document, a
    relation, an operator, a confirmation -- and because the callers in
    `bin/studio.py` translate it into either an exit code (before the server
    starts) or an HTTP status (after it does). One class with a code rather than
    two hierarchies: the code is the only thing the two callers need.
    """

    def __init__(self, exit_code: int, message: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code


# ---------------------------------------------------------------------------
# The address book (ADR 0158)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AddressBook:
    """Where this deployment is, and how its REST document spells itself.

    `expected_host` and `expected_base_path` are derived HERE, from the same
    `routes.rest.url` the fetch uses, because ADR 0050 requires the real address
    to be validated before it is substituted -- a document naming another host
    must be refused rather than normalized into agreement. Deriving them once,
    beside the URL they belong to, is ADR 0002 applied to a pair that has been
    re-derived in two other places in this repository already.
    """

    rest_url: str
    app_url: str
    expected_host: str
    expected_base_path: str


def _published_address(url: str) -> tuple[str, str]:
    """`(host, basePath)` as the served document will spell them.

    `bin/api-contract.py`'s `published_address()`, over a URL rather than a
    document. The `:443` is measured rather than assumed: given a proxy URI of
    `https://alpha.example.test/api/rest` the locked PostgREST publishes
    `host: "alpha.example.test:443"`, so a derivation that dropped the default
    port would refuse every correct capture.
    """
    split = urllib.parse.urlsplit(url)
    default = 443 if split.scheme == "https" else 80
    return f"{split.hostname}:{split.port or default}", (split.path.rstrip("/") or "/")


def _route(document: dict[str, Any], name: str) -> str:
    routes = (document.get("routes") or {}).get(name) or {}
    if routes.get("status") != "ready" or not routes.get("url"):
        raise StudioError(
            5,
            f"the deployed document publishes no ready {name} route. Studio is a client of "
            "a deployment: deploy the project, or point --outputs at a document from one "
            "that was.",
        )
    url = str(routes["url"]).rstrip("/")
    split = urllib.parse.urlsplit(url)
    if split.scheme != "https" and (split.hostname or "") not in LOOPBACK_HOSTS:
        # The scheme and the host, never the URL: a route URL can carry a query
        # or userinfo, and a refusal is not a place to print either (D105).
        raise StudioError(
            5,
            f"routes.{name}.url is {split.scheme!r} to host {split.hostname!r}. Studio "
            "requires https to anything but loopback: a token crossing a network in "
            "cleartext is the one thing this tool exists to avoid.",
        )
    return url


def address_book(document: dict[str, Any]) -> AddressBook:
    """The two routes Studio uses, and the address the REST document publishes.

    A deployed document and not a rendered one, for `bin/api.py`'s reason: a
    render says what was asked for, and a route is an observation of what
    happened (D132).
    """
    if document.get("document_kind") != "deployed":
        raise StudioError(2, "that is a rendered document; the REST route is an observation")
    rest_url = _route(document, "rest")
    app_url = _route(document, "app")
    expected_host, expected_base_path = _published_address(rest_url)
    return AddressBook(
        rest_url=rest_url,
        app_url=app_url,
        expected_host=expected_host,
        expected_base_path=expected_base_path,
    )


# ---------------------------------------------------------------------------
# The surface answer (ADR 0204, copied for a UI)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SurfaceAnswer:
    answer: str
    expected_sha256: str
    served_sha256: str | None = None
    reason: str | None = None


def surface_answer(
    ir: IR,
    fetched: bytes | None,
    error: str | None,
    *,
    expected_host: str,
    expected_base_path: str,
) -> SurfaceAnswer:
    """What a generated client's `init()` answers, in Python, for a UI.

    Four answers, and the two failures are kept apart: `unreachable` is *the
    deployment did not answer*, `unreadable` is *it answered with something this
    cannot read*. Folding either into `stale_contract` would report a contract
    disagreement that was never observed, which is ADR 0195's whole subject.

    **`expected_host` and `expected_base_path` are arguments** (D1260). The
    committed snapshot is already in the project-neutral form, so the comparison
    is `fingerprint(normalize(served, ...))` and not `fingerprint(served)` -- the
    raw served document has a different digest for the same bytes, and a version
    of this function without these parameters would report `stale_contract`
    against every correct deployment. They come from `address_book`, derived from
    the same `routes.rest.url` the fetch used, so a served document naming
    another host is REFUSED here rather than substituted into agreement
    (ADR 0050) -- and that refusal surfaces as `unreadable` with the
    normalizer's own sentence, which names both hosts.
    """
    expected = ir.digests.rest_openapi_sha256
    if error is not None or fetched is None:
        return SurfaceAnswer(
            answer="unreachable", expected_sha256=expected, reason=error or "no response"
        )
    try:
        document = json.loads(fetched.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as failure:
        return SurfaceAnswer(
            answer="unreadable", expected_sha256=expected, reason=f"not JSON: {failure}"
        )
    if not isinstance(document, dict):
        return SurfaceAnswer(
            answer="unreadable",
            expected_sha256=expected,
            reason="the served document is not an object",
        )
    try:
        neutral = openapi_normalize.normalize(
            document, expected_host=expected_host, expected_base_path=expected_base_path
        )
    except openapi_normalize.NormalizationError as failure:
        return SurfaceAnswer(answer="unreadable", expected_sha256=expected, reason=str(failure))

    served = openapi_normalize.fingerprint(neutral)
    if served != expected:
        return SurfaceAnswer(
            answer="stale_contract", expected_sha256=expected, served_sha256=served
        )
    return SurfaceAnswer(answer="ok", expected_sha256=expected, served_sha256=served)


# ---------------------------------------------------------------------------
# The schema view
# ---------------------------------------------------------------------------


def schema_view(ir: IR) -> dict[str, Any]:
    """The IR, as the page renders it, and nothing the IR does not carry.

    Served only when the surface answered `ok`, which is what makes it honest:
    the IR is a checkout's belief about a surface, and the page may show it only
    after the deployment has confirmed it (ADR 0204).

    No digest of the human's, no row, no count -- this is a description of a
    contract and every value in it came from `client_ir.build`.
    """
    return {
        "relations": [
            {
                "name": relation.name,
                "methods": list(relation.methods),
                "columns": [
                    {
                        "name": column.name,
                        "type": column.ts_type,
                        "format": column.format,
                        "nullable": column.nullable,
                    }
                    for column in relation.columns
                ],
            }
            for relation in ir.relations
        ],
        "rpcs": [
            {
                "name": rpc.name,
                "path": rpc.path,
                "arguments": [
                    {"name": argument.name, "type": argument.ts_type, "required": argument.required}
                    for argument in rpc.arguments
                ],
            }
            for rpc in ir.rpcs
        ],
        "tools": [
            {
                "name": tool.name,
                "kind": tool.kind,
                "arguments": [
                    {"name": argument.name, "type": argument.ts_type, "required": argument.required}
                    for argument in tool.arguments
                ],
                "scopes": [list(scopes) for scopes in tool.discovery_scope_sets],
                "resources": list(tool.resources),
            }
            for tool in ir.tools
        ],
        "enums": {name: list(members) for name, members in ir.enums.items()},
        "filter_operators": list(ir.filter_operators),
        "digests": {
            "rest_openapi_sha256": ir.digests.rest_openapi_sha256,
            "tools_sha256": ir.digests.tools_sha256,
            "merged_surface_sha256": ir.digests.merged_surface_sha256,
        },
    }


# ---------------------------------------------------------------------------
# The query builder (D1250)
# ---------------------------------------------------------------------------


def rest_query(
    ir: IR,
    *,
    relation: str,
    select: tuple[str, ...] | list[str],
    filters: tuple[tuple[str, str, Any], ...] | list[tuple[str, str, Any]],
    order: tuple[str, str] | None,
    limit: int,
) -> str:
    """One PostgREST `GET` path, built by this process from validated parts.

    The browser sends structure -- a relation, columns, `[column, operator,
    value]` triples -- and never a URL. A URL a page composed would be trusted
    input; a URL built here is a query the reviewed surface permits, because
    every name in it was checked against the IR and every operator against the
    capability schema's closed set (D1210, which is the operator set for humans
    too).

    **A value is a value.** Each is percent-encoded with no safe characters, so
    `,` `.` `(` `)` and `&` reach PostgREST as characters rather than as syntax.
    The proof sends `a,b)or(1=1` as a value and gets zero rows, with the control
    that the same string stored in a row is found by `eq`.

    Reads only. There is no write anywhere in `forwarder_table()`'s REST half,
    so this function has no method parameter to get wrong.
    """
    relations = {item.name: item for item in ir.relations}
    if relation not in relations:
        raise StudioError(
            _UNPROCESSABLE,
            f"{relation!r} is not a relation this surface names. The surface has "
            f"{sorted(relations)}.",
        )
    columns = {column.name for column in relations[relation].columns}

    def check(name: str, where: str) -> None:
        if name not in columns:
            raise StudioError(
                _UNPROCESSABLE,
                f"{name!r} is not a column of {relation!r} ({where}). {relation!r} has "
                f"{sorted(columns)}.",
            )

    parts: list[str] = []

    chosen = list(select)
    for name in chosen:
        check(name, "select")
    if chosen:
        parts.append(f"select={','.join(chosen)}")

    allowed = set(ir.filter_operators)
    for column, operator, value in filters:
        check(column, "filter")
        if operator not in allowed:
            raise StudioError(
                _UNPROCESSABLE,
                f"{operator!r} is not an operator this contract names. The set is "
                f"{sorted(allowed)}.",
            )
        wire, operands = OPERATOR_WIRE_FORMS[operator]
        if operands == "none":
            parts.append(f"{column}={wire}.{IS_NULL_OPERAND}")
        elif operands == "list":
            members = value if isinstance(value, (list, tuple)) else [value]
            quoted = ",".join(urllib.parse.quote(str(member), safe="") for member in members)
            parts.append(f"{column}={wire}.({quoted})")
        else:
            parts.append(f"{column}={wire}.{urllib.parse.quote(str(value), safe='')}")

    if order is not None:
        column, direction = order
        check(column, "order")
        if direction not in ("asc", "desc"):
            raise StudioError(
                _UNPROCESSABLE, f"{direction!r} is not an order direction; asc or desc."
            )
        parts.append(f"order={column}.{direction}")

    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= STUDIO_MAX_ROWS:
        raise StudioError(
            _UNPROCESSABLE,
            f"limit {limit!r} is outside 1..{STUDIO_MAX_ROWS} (STUDIO_MAX_ROWS). A human's "
            "page is not an agent's budget, and this bound is Studio's own.",
        )
    parts.append(f"limit={limit}")

    return f"/{relation}?{'&'.join(parts)}"


# ---------------------------------------------------------------------------
# The forwarder's table
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ForwarderOperation:
    """One operation the process will make upstream, and nothing else it may.

    `upstream` is `"rest"` or `"app"`, which is what makes
    `test_the_forwarder_table_has_no_rest_write` answerable as a property rather
    than as a list somebody maintains.
    """

    method: str
    upstream: str
    path: str
    scope_hint: str
    body_allowed: bool


def forwarder_table() -> dict[str, ForwarderOperation]:
    """Every upstream request Studio can make, enumerated (ADR 0205).

    A table and not a proxy: a proxy forwards what it is given, and a table
    forwards what it was written to forward. `bin/api.py`'s shape, with the
    operations a human's own token can already perform through the endpoints
    this deployment publishes.

    A function rather than a module constant, so a caller cannot mutate the
    table another caller will read -- the dataclasses are frozen and this
    returns a fresh mapping of them.

    `path` for `query` is a placeholder: that operation's path comes from
    `rest_query`, which is the only thing allowed to build one.
    """
    return {
        "surface": ForwarderOperation("GET", "rest", "/", "", False),
        "query": ForwarderOperation("GET", "rest", "", "", False),
        "me": ForwarderOperation("GET", "app", "/auth/me", "", False),
        "sessions": ForwarderOperation("GET", "app", "/auth/sessions", "", False),
        "agents": ForwarderOperation("GET", "app", "/admin/agents", "admin_agents:read", False),
        "audit": ForwarderOperation("GET", "app", "/admin/audit", "admin_audit:read", False),
        "revoke_agent": ForwarderOperation(
            "PATCH", "app", "/admin/agents/{agent_id}", "admin_agents:write", True
        ),
    }


def revoke_request(agent_id: str, confirm: str) -> tuple[str, dict[str, str]]:
    """The path and body of a revocation, or a refusal the page cannot skip.

    `--confirm` in this repository means *the value must equal the identity of
    the thing acted on* (`bin/edge.sh`, `bin/bootstrap-providers.sh`), and a
    mismatch says what was expected and that nothing changed. That is the shape
    a shell gives an operator and it is the shape a click gets here.

    **Checked in the process, before any upstream request** (ADR 0140). A
    confirmation the page checks and the process does not is a hidden control:
    whoever drives the process is not necessarily the page.

    The id is checked for shape first, so a confirmation that matches a
    non-identifier is still refused -- `confirm == agent_id` is true for two
    equal pieces of nonsense.
    """
    if not _UUID.match(agent_id or ""):
        raise StudioError(_UNPROCESSABLE, "agent_id is not a uuid. Nothing was changed.")
    if confirm != agent_id:
        raise StudioError(
            _UNPROCESSABLE,
            f"--confirm said {confirm!r} but this agent is {agent_id!r}. Nothing was changed.",
        )
    return f"/admin/agents/{agent_id}", {"status": "revoked"}


# ---------------------------------------------------------------------------
# The five checks (ADR 0205)
# ---------------------------------------------------------------------------


def request_checks(
    *,
    method: str,
    path: str,
    host: str | None,
    bound: str,
    cookie: str | None,
    expected_cookie: str,
    origin: str | None,
    own_origin: str,
    custom_header: str | None,
) -> int | None:
    """The status to refuse this request with, or `None` to serve it.

    One function, called first on every request, so that a battery can reach
    every branch without a socket and so the handler above it cannot answer
    without having asked. Each status answers a different question:

    * **405** -- `OPTIONS`. Refusing it is what makes the custom header a
      boundary: a cross-origin page cannot set `X-Apg-Studio` without a
      preflight, and no preflight can succeed.
    * **421** -- the `Host` is not the address this process bound. Misdirected,
      which is what a DNS-rebinding attempt looks like from in here.
    * **403** -- an `Origin` that is present and is not this page's. Absent is
      not foreign: same-origin navigations send none.
    * **401** -- no launch cookie. The one path exempt is `/open/<key>`, which
      is where the cookie is issued.
    * **403** -- a `/__apg/` call without the custom header.

    `path` is a parameter (and the plan's signature did not have one) because
    two of the five checks are about which path is being asked for, and the
    alternative -- the handler deciding which checks apply -- puts policy back
    where a battery cannot reach it (D1265).
    """
    if method == "OPTIONS":
        return _METHOD_NOT_ALLOWED
    if host != bound:
        return _MISDIRECTED
    if origin is not None and origin != own_origin:
        return _FORBIDDEN
    if path.startswith("/open/"):
        return None
    if not cookie or expected_cookie not in _cookie_values(cookie):
        return _UNAUTHENTICATED
    if path.startswith("/__apg/") and custom_header != "1":
        return _FORBIDDEN
    return None


def _cookie_values(header: str) -> set[str]:
    """The values of `LAUNCH_COOKIE` in a `Cookie` header, as sent.

    Parsed rather than substring-matched: `apg_studio=x` is a prefix of
    `apg_studio=xy`, and a browser may send more than one cookie.
    """
    found: set[str] = set()
    for item in header.split(";"):
        name, _, value = item.strip().partition("=")
        if name == LAUNCH_COOKIE:
            found.add(value)
    return found


# ---------------------------------------------------------------------------
# The session Studio opened (D1252, ADR 0171, ADR 0195)
# ---------------------------------------------------------------------------


def own_session(rows: list[dict[str, Any]], since: str) -> str | None:
    """Which live session is the one this launch created, or `None`.

    `POST /auth/login` returns no session id, so it is inferred: the live row
    whose `created_at` is newest and strictly after the instant recorded before
    the login. `created_at` was measured at MICROSECOND resolution in rig 24b --
    three logins inside 0.68 s produced three distinct values -- so a tie is
    practically unreachable, which is exactly why the tie branch needs a unit
    proof rather than a rig.

    **`None` on a tie, and the caller says so** (ADR 0195). A tool that guessed
    which session to close might close the one a human is using from another
    window. The third outcome is reported: *Studio could not determine which
    session was its own and ended none.*
    """
    live = [
        row
        for row in rows
        if row.get("revoked_at") is None
        and isinstance(row.get("created_at"), str)
        and row["created_at"] > since
    ]
    if not live:
        return None
    newest = max(row["created_at"] for row in live)
    candidates = [row for row in live if row["created_at"] == newest]
    if len(candidates) != 1:
        return None
    session_id = candidates[0].get("session_id")
    return str(session_id) if session_id else None


# ---------------------------------------------------------------------------
# What the viewer says, and what the log says
# ---------------------------------------------------------------------------


def audit_view_header(shown: int, total: int) -> str:
    """The sentence above the audit table, always visible (D1248).

    *No summarisation that hides denials* is satisfied by rendering the page
    whole and saying what the page is -- never by a filter that could let a
    viewer ask for `outcome=served` and never learn there were refusals. The
    count beside the filter is what makes a hidden row visible as a number.
    """
    return (
        f"showing {shown} of {total} rows on this page; the page is the newest {AUDIT_PAGE_LIMIT}"
    )


def redact_for_log(method: str, path: str) -> str:
    """One log line: a method, a path without its query, and nothing else (D1256).

    `http.server`'s default logger writes the request line, which carries the
    query string -- so a query builder's values, an audit filter and the launch
    key would all be written to stderr by a logger nobody chose. The launch key
    is replaced rather than trimmed, because a path is the one place in this
    process where a credential-shaped value appears by design.
    """
    bare = path.split("?", 1)[0]
    if bare.startswith("/open/"):
        bare = "/open/<key>"
    return f"{method} {bare}"
