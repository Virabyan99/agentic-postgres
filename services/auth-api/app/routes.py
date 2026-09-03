"""The human endpoints, and the administrative lifecycle.

**Every request body is parsed by `strict_json` before pydantic sees it.**
Measured: Starlette's `Request.json` is `json.loads(await self.body())` with no
hook, so `{"username": "alice", "username": "root"}` reaches a model as `root`
and the duplicate is gone by the time anything could notice. A route that used
FastAPI's own body binding would inherit that, which is why none of these
declare a body parameter.

**No route returns a reason for an authentication failure**, and the four causes
cost the same (see `errors.py`). The administrative routes do return reasons,
because their caller has already proved who it is.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app import errors, openapi_docs, strict_query
from app import scopes as scope_map
from app.models import (
    AgentTokenRequest,
    ConsumePasswordResetRequest,
    CreateAgentRequest,
    CreateUserRequest,
    LoginRequest,
    PasswordResetResponse,
    RefreshRequest,
    SessionResponse,
    SessionTokenResponse,
    SubjectResponse,
    TokenResponse,
    UpdateAgentRequest,
    UpdateUserRequest,
)
from app.service import PASSWORD_RESET_TTL_SECONDS, AuthService
from app.strict_json import MalformedBody, parse_object

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

router = APIRouter()

# ---------------------------------------------------------------------------
# The published reference (D226, ADR 0087)
#
# Two mechanisms, because they behave differently and the difference is
# measured: `responses=` REPLACES what FastAPI generated, `openapi_extra` is
# deep-merged into it. So every response goes through the first and only the
# request body -- which the first cannot express without binding it -- goes
# through the second. `openapi_docs.py` has the measurement.
#
# Neither wires anything. A declared body parameter would hand parsing to
# FastAPI, whose binding is `json.loads` with no duplicate hook, which is the
# exact defect `strict_json` exists for.
#
# Without all of this, the generated document is nine paths with no request
# bodies and one `200` apiece. Measured before it was written.
# ---------------------------------------------------------------------------

DOC_LOGIN = openapi_docs.described(
    summary="Exchange a username and password for a short-lived token",
    description=(
        "Decides whether these credentials match, and what the server already says this "
        "subject's role and scopes are. It never decides the role or the scopes."
    ),
    request_model=LoginRequest,
)
RESP_LOGIN = {
    200: openapi_docs.ok(
        "A signed access token and the session's first refresh token.",
        SessionTokenResponse,
    ),
    400: openapi_docs.MALFORMED,
    401: openapi_docs.UNAUTHENTICATED,
    422: openapi_docs.INVALID,
}

DOC_REFRESH = openapi_docs.described(
    summary="Exchange a refresh token for a new access token and its successor",
    description=(
        "Single-use. The presented token is consumed by this exchange and is refused "
        "from that moment, so the successor returned here is the client's only way to "
        "refresh again. Presenting a consumed token ends the whole session: the server "
        "cannot tell a replay by its owner from a replay by a thief, so it assumes the "
        "chain leaked. Every refusal answers identically."
    ),
    request_model=RefreshRequest,
)
RESP_REFRESH = {
    200: openapi_docs.ok("A new access token and its successor.", SessionTokenResponse),
    400: openapi_docs.MALFORMED,
    401: openapi_docs.UNAUTHENTICATED,
}

DOC_LIST_SESSIONS = openapi_docs.described(
    summary="List this subject's sessions",
    description=(
        "Live and ended alike. A session carries no device, address or user agent "
        "because none is stored, so it is identified by its id and its times."
    ),
)
RESP_LIST_SESSIONS = {
    200: openapi_docs.ok("Every session this subject has.", SessionResponse),
    401: openapi_docs.UNAUTHENTICATED,
}

DOC_END_SESSION = openapi_docs.described(
    summary="End one of this subject's sessions",
    description=(
        "Scoped to the caller. An unknown session, another subject's session and one "
        "already ended are one answer, because distinguishing them would say whether a "
        "guessed id belongs to somebody."
    ),
)
RESP_END_SESSION = {
    204: {"description": "The session is ended, or was already."},
    401: openapi_docs.UNAUTHENTICATED,
    422: openapi_docs.INVALID,
}

DOC_OPEN_RESET = openapi_docs.described(
    summary="Issue a one-time password reset for a subject",
    description=(
        "Requires the `admin:users` scope. Returns a token the administrator conveys to "
        "the subject, who chooses the password when they spend it -- so the administrator "
        "never learns the resulting credential. Issuing changes no credential and ends no "
        "session; an administrator who needs the subject out now disables the account, "
        "which is a different act with a different record. A second reset supersedes the "
        "first."
    ),
)
RESP_OPEN_RESET = {
    201: openapi_docs.ok("A one-time reset token, shown once.", PasswordResetResponse),
    401: openapi_docs.UNAUTHENTICATED,
    403: openapi_docs.UNAUTHORIZED,
    404: {"description": "No such subject."},
}

DOC_CONSUME_RESET = openapi_docs.described(
    summary="Spend a reset token and choose a new password",
    description=(
        "Unauthenticated: the token IS the credential, and requiring a live session to "
        "recover from a lost password would only work for callers who did not need it. "
        "Single use. On success `credential_version` moves, so every token issued before "
        "the reset is refused, and every refresh session the subject had is ended. Every "
        "refusal answers identically."
    ),
    request_model=ConsumePasswordResetRequest,
)
RESP_CONSUME_RESET = {
    200: openapi_docs.ok("The password is set and the subject's sessions are ended."),
    400: openapi_docs.MALFORMED,
    401: openapi_docs.UNAUTHENTICATED,
    422: openapi_docs.INVALID,
}

DOC_ME = openapi_docs.described(
    summary="The bearer's current state",
    description=(
        "Read from the registry inside this request, not from the token. A token whose "
        "subject has changed underneath it is refused rather than reflected."
    ),
)
RESP_ME = {
    200: openapi_docs.ok("The subject as it is now.", SubjectResponse),
    401: openapi_docs.UNAUTHENTICATED,
}

DOC_JWKS = openapi_docs.described(
    summary="The verification key set",
    description=(
        "Public material only, derived from the signing key rather than stored beside it. "
        "This endpoint decides nothing and requires no credential."
    ),
)
RESP_JWKS = {200: openapi_docs.ok("An RFC 7517 JWK Set of public keys.")}

DOC_LIST_USERS = openapi_docs.described(
    summary="List the registered subjects",
    description="Requires the `admin:users` scope. A role name does not grant it.",
)
RESP_LIST_USERS = {
    200: openapi_docs.ok("Every registered subject, without credential material."),
    401: openapi_docs.UNAUTHENTICATED,
    403: openapi_docs.UNAUTHORIZED,
}

DOC_CREATE_USER = openapi_docs.described(
    summary="Register a subject",
    description=(
        "`role` is a SUFFIX, mapped to a derived role name by the service. A client naming "
        "a derived role would be a client that had to know how this deployment derives "
        "names -- and one that could name another project's."
    ),
    request_model=CreateUserRequest,
)
RESP_CREATE_USER = {
    200: openapi_docs.ok("The subject as created.", SubjectResponse),
    400: openapi_docs.MALFORMED,
    401: openapi_docs.UNAUTHENTICATED,
    403: openapi_docs.UNAUTHORIZED,
    422: openapi_docs.INVALID,
}

DOC_UPDATE_USER = openapi_docs.described(
    summary="Change a subject's authority, status or password",
    description=(
        "Three concerns and three version bumps: role and scopes move `authz_version`, "
        "status moves it too, and a password moves `credential_version`. Any token issued "
        "before the change stops being accepted."
    ),
    request_model=UpdateUserRequest,
)
RESP_UPDATE_USER = {
    200: openapi_docs.ok("The subject after the change.", SubjectResponse),
    400: openapi_docs.MALFORMED,
    401: openapi_docs.UNAUTHENTICATED,
    403: openapi_docs.UNAUTHORIZED,
    422: openapi_docs.INVALID,
}

DOC_AGENT_TOKEN = openapi_docs.described(
    summary="Exchange an agent id and secret for a short-lived token",
    description=(
        "Decides whether this credential is current. The agent's authority comes from the "
        "registry, and an agent cannot ask for a role or a scope any more than a person can."
    ),
    request_model=AgentTokenRequest,
)
RESP_AGENT_TOKEN = {
    200: openapi_docs.ok("A signed access token.", TokenResponse),
    400: openapi_docs.MALFORMED,
    401: openapi_docs.UNAUTHENTICATED,
    422: openapi_docs.INVALID,
}

DOC_LIST_AGENTS = openapi_docs.described(
    summary="List the registered agents",
    description=(
        "Requires the `admin:agents` scope. No response from this service ever returns an "
        "agent secret; there is no endpoint that can."
    ),
)
RESP_LIST_AGENTS = {
    200: openapi_docs.ok("Every registered agent, without secret material."),
    401: openapi_docs.UNAUTHENTICATED,
    403: openapi_docs.UNAUTHORIZED,
}

DOC_CREATE_AGENT = openapi_docs.described(
    summary="Register an agent and show its secret once",
    description=(
        "The secret is 256 bits from the OS and is returned by THIS response and no other. "
        "If it is lost, the recovery is to rotate it -- which is why rotation exists and "
        "why no retrieval endpoint does."
    ),
    request_model=CreateAgentRequest,
)
RESP_CREATE_AGENT = {
    200: openapi_docs.ok("The agent, and its secret, once."),
    400: openapi_docs.MALFORMED,
    401: openapi_docs.UNAUTHENTICATED,
    403: openapi_docs.UNAUTHORIZED,
    422: openapi_docs.INVALID,
}

DOC_ROTATE_SECRET = openapi_docs.described(
    summary="Replace an agent's secret and show the new one once",
    description=(
        "Moves `authz_version`, so tokens issued against the replaced secret stop working. "
        "That is what makes rotating again a recovery rather than a way to accumulate "
        "credentials."
    ),
)
RESP_ROTATE_SECRET = {
    200: openapi_docs.ok("The agent, and its new secret, once."),
    401: openapi_docs.UNAUTHENTICATED,
    403: openapi_docs.UNAUTHORIZED,
    422: openapi_docs.INVALID,
}

DOC_UPDATE_AGENT = openapi_docs.described(
    summary="Change an agent's authority or status",
    description=(
        "No `secret` field: rotation is its own endpoint, so no PATCH body ever carries a "
        "credential."
    ),
    request_model=UpdateAgentRequest,
)
RESP_UPDATE_AGENT = {
    200: openapi_docs.ok("The agent after the change."),
    400: openapi_docs.MALFORMED,
    401: openapi_docs.UNAUTHENTICATED,
    403: openapi_docs.UNAUTHORIZED,
    422: openapi_docs.INVALID,
}

#: `GET /admin/audit`'s parameter names, in one place (ADR 0142).
#:
#: **The route parses against this tuple and the document is generated from it**
#: -- one authority, not a docstring and an allowlist that agree today. An
#: endpoint whose document names a filter the parser rejects is D274's shape: a
#: claim living in an artifact nobody dereferences.
AUDIT_QUERY_PARAMETERS: tuple[str, ...] = ("agent_id", "owner_id", "limit")

#: The bound on `limit`, and the ONE place it is stated. Migration 0020's reader
#: takes `p_limit` and applies it without clamping, deliberately: a second bound
#: in the database would be a second authority over one rule, and the two drift
#: the moment either moves (D495, D463). Out of range is a 422 naming the range,
#: never a silent clamp -- a clamp answers a question the caller did not ask and
#: says nothing about having done so.
AUDIT_LIMIT_MIN = 1
AUDIT_LIMIT_MAX = 500
AUDIT_LIMIT_DEFAULT = 100

DOC_LIST_AUDIT = openapi_docs.described(
    summary="Read the agent audit record",
    description=(
        "Requires the `admin_audit:read` scope, which is in `project_admin`'s ceiling and in "
        "no other -- an agent cannot be authorized to read the record that attributes it. "
        "Rows come back most recent first. Each carries a `source`: `agent_plane` is what an "
        "agent ATTEMPTED, including calls refused for a missing scope that never reached the "
        "database, and `database` is what actually CHANGED, including a write that reached "
        "PostgREST without going near the agent plane. The two answer different questions and "
        "a single agent write produces one of each. A repeated query parameter is refused "
        "rather than resolved to its last value."
    ),
    query_parameters=[
        openapi_docs.query_parameter(
            "agent_id",
            schema={"type": "string", "format": "uuid"},
            description="Narrow to one agent. Absent means every agent.",
        ),
        openapi_docs.query_parameter(
            "owner_id",
            schema={"type": "string", "format": "uuid"},
            description="Narrow to one owner. Absent means every owner.",
        ),
        openapi_docs.query_parameter(
            "limit",
            schema={
                "type": "integer",
                "minimum": AUDIT_LIMIT_MIN,
                "maximum": AUDIT_LIMIT_MAX,
                "default": AUDIT_LIMIT_DEFAULT,
            },
            description=(
                f"Rows to return, {AUDIT_LIMIT_MIN}-{AUDIT_LIMIT_MAX}. A value outside the "
                "range is refused with 422; it is never clamped."
            ),
        ),
    ],
)
RESP_LIST_AUDIT = {
    200: openapi_docs.ok("Audit rows, most recent first."),
    401: openapi_docs.UNAUTHENTICATED,
    403: openapi_docs.UNAUTHORIZED,
    422: openapi_docs.INVALID,
}


def _service(request: Request) -> AuthService:
    return request.app.state.service


async def _body(request: Request, model: type) -> object:
    """Read, bound, parse strictly, then validate. In that order.

    The size bound is applied to the raw bytes by `parse_object` before the
    document is built, because a parser that has already allocated the body has
    already paid for it.

    **The read is not bounded here, and Run 10 measured how far that goes.**
    `request.body()` accumulates every byte the client sent before
    `parse_object` looks at the length: an 8 MiB body is read in full and then
    refused against a 16 KiB limit, with a 108-byte body as the control. What
    bounds the *process* is the Traefik buffering middleware one hop earlier,
    carrying the same number from the same declaration (`auth_limits.py`).
    """
    # Both refusals are `MalformedRequest` -- 400, carrying no message to the
    # caller (ADR 0097). They were `InvalidRequest`, which is 422 with the reason
    # in the body, and that is the shape reserved for an authenticated
    # administrator; `/auth/login` has no caller identity at all. Measured on the
    # host: a duplicate member in a login body came back
    # `422 {"error":"invalid_request","message":"duplicate JSON member: 'username'"}`,
    # which tells an unauthenticated caller which field it duplicated.
    try:
        document = parse_object(await request.body())
    except MalformedBody as exc:
        raise errors.MalformedRequest(str(exc)) from exc
    try:
        return model(**document)
    except ValidationError as exc:
        # The first error's type, never its input value: a validation error
        # renders the offending value, and the offending value can be a password.
        kinds = sorted({item["type"] for item in exc.errors()})
        raise errors.MalformedRequest(f"request body is not valid: {kinds}") from exc


async def _guard(handler: Callable[[], Awaitable[Response]]) -> Response:
    """One place the exception types become responses.

    A decorator rather than per-route `try` blocks, so a route added later
    cannot forget one and answer 500 with a traceback -- which for the login
    path would be a traceback naming the subject.
    """
    try:
        return await handler()
    except errors.AuthenticationFailed:
        return errors.unauthenticated()
    except errors.AuthorizationFailed:
        return errors.unauthorized()
    except errors.MalformedRequest:
        # The reason is deliberately not passed on. `malformed()` takes no
        # argument for the same reason `unauthenticated()` does not (ADR 0097).
        return errors.malformed()
    except errors.InvalidRequest as exc:
        return errors.invalid(str(exc))


# ---------------------------------------------------------------------------
# Human endpoints
# ---------------------------------------------------------------------------


@router.post("/auth/login", openapi_extra=DOC_LOGIN, responses=RESP_LOGIN)
async def login(request: Request) -> Response:
    """API-AUTH-001. Issues a short-lived token, or fails identically four ways."""

    async def run() -> Response:
        payload = await _body(request, LoginRequest)
        assert isinstance(payload, LoginRequest)
        issued, refresh = await _service(request).login(payload.username, payload.password)
        return JSONResponse(
            {
                "access_token": issued.token,
                "token_type": "Bearer",
                "expires_at": issued.expires_at,
                "token_use": issued.token_use,
                "refresh_token": refresh,
            },
            # No-store on every response carrying a token. A token in a shared
            # cache is a token issued to whoever the cache serves next.
            headers={"Cache-Control": "no-store"},
        )

    return await _guard(run)


@router.post("/auth/refresh", openapi_extra=DOC_REFRESH, responses=RESP_REFRESH)
async def refresh(request: Request) -> Response:
    """IDN-SESSION-001. Rotates, or refuses identically four ways.

    The refusal path is the subject. An unknown token, a replayed one, a
    revoked family and an expired token all answer 401 with the same bytes,
    and the reason reaches the log alone -- which is `login`'s shape and the
    same argument: telling whoever presented a guess whether it named something
    real is the whole thing being withheld.

    **Nothing here relays a status** (D433). There is no upstream to relay one
    from; the outcome is computed from facts this deployment holds, and the
    refusal is this product's own.
    """

    async def run() -> Response:
        payload = await _body(request, RefreshRequest)
        assert isinstance(payload, RefreshRequest)
        issued, successor = await _service(request).refresh(payload.refresh_token)
        return JSONResponse(
            {
                "access_token": issued.token,
                "token_type": "Bearer",
                "expires_at": issued.expires_at,
                "token_use": issued.token_use,
                "refresh_token": successor,
            },
            headers={"Cache-Control": "no-store"},
        )

    return await _guard(run)


@router.get("/auth/sessions", openapi_extra=DOC_LIST_SESSIONS, responses=RESP_LIST_SESSIONS)
async def list_sessions(request: Request) -> Response:
    """IDN-SESSION-002. This subject's sessions, live and ended."""

    async def run() -> Response:
        principal = await _service(request).authenticate(request.headers.get("authorization"))
        return JSONResponse(
            await _service(request).list_sessions(principal),
            headers={"Cache-Control": "no-store"},
        )

    return await _guard(run)


@router.delete(
    "/auth/sessions/{session_id}",
    openapi_extra=DOC_END_SESSION,
    responses=RESP_END_SESSION,
    status_code=204,
)
async def end_session(request: Request, session_id: str) -> Response:
    """IDN-SESSION-002. Ends one session, and answers the same either way.

    204 whether or not a row moved. The alternative -- 404 for a family that is
    not this subject's -- would confirm which ids exist, and the caller's
    intent is satisfied identically in both cases: that session is not usable.
    """

    async def run() -> Response:
        principal = await _service(request).authenticate(request.headers.get("authorization"))
        try:
            family = UUID(session_id)
        except ValueError as exc:
            raise errors.InvalidRequest("session_id is not a uuid") from exc
        await _service(request).terminate_session(principal, family)
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    return await _guard(run)


@router.post(
    "/admin/users/{user_id}/reset-password",
    openapi_extra=DOC_OPEN_RESET,
    responses=RESP_OPEN_RESET,
    status_code=201,
)
async def open_password_reset(request: Request, user_id: str) -> Response:
    """IDN-RESET-001. The administrator arranges a recovery and learns no password.

    Contrast `PATCH /admin/users/{user_id}` with a `password` member, which has
    existed since Session 6 and is the right operation for PROVISIONING: somebody
    has to set the first password. It is the wrong one for recovery, because the
    ordinary case of "this person cannot get in" should not end with an operator
    holding a credential that opens somebody else's account.
    """

    async def run() -> Response:
        service = _service(request)
        principal = await service.authenticate(request.headers.get("authorization"))
        AuthService.require_scope(principal, scope_map.ADMIN_USERS_WRITE)
        try:
            target = UUID(user_id)
        except ValueError as exc:
            raise errors.InvalidRequest("user_id is not a uuid") from exc

        token = await service.open_password_reset(target, principal.user_id)
        if token is None:
            return JSONResponse({"error": "not_found"}, status_code=404)

        return JSONResponse(
            {
                "user_id": user_id,
                "reset_token": token,
                "expires_at": (
                    datetime.now(UTC) + timedelta(seconds=PASSWORD_RESET_TTL_SECONDS)
                ).isoformat(),
            },
            status_code=201,
            headers={"Cache-Control": "no-store"},
        )

    return await _guard(run)


@router.post(
    "/auth/reset-password",
    openapi_extra=DOC_CONSUME_RESET,
    responses=RESP_CONSUME_RESET,
)
async def consume_password_reset(request: Request) -> Response:
    """IDN-RESET-001's other half. The SUBJECT chooses the password.

    Unauthenticated, and that is the point: a recovery that required a live
    session would work only for callers who did not need it -- the same argument
    `/auth/refresh` makes (D834). The token is the credential.
    """

    async def run() -> Response:
        payload = await _body(request, ConsumePasswordResetRequest)
        assert isinstance(payload, ConsumePasswordResetRequest)
        version = await _service(request).consume_password_reset(
            payload.reset_token, payload.password
        )
        return JSONResponse(
            {"credential_version": version},
            headers={"Cache-Control": "no-store"},
        )

    return await _guard(run)


@router.get("/auth/me", openapi_extra=DOC_ME, responses=RESP_ME)
async def me(request: Request) -> Response:
    """Reflects CURRENT state, not the token's copy of it.

    A token whose subject has changed underneath it is refused rather than
    answered with stale values -- `authenticate` compares both version claims
    against the record inside this request, which is what makes a disable take
    effect on the next call rather than at the next expiry.
    """

    async def run() -> Response:
        principal = await _service(request).authenticate(request.headers.get("authorization"))
        state = principal.state
        return JSONResponse(
            {
                "user_id": str(principal.user_id),
                "username": state.username,
                "display_name": state.display_name,
                "role": state.role_name,
                "scopes": sorted(state.scopes),
                "status": state.status,
                "credential_version": state.credential_version,
                "authz_version": state.authz_version,
                "last_login_at": state.last_login_at.isoformat() if state.last_login_at else None,
            },
            headers={"Cache-Control": "no-store"},
        )

    return await _guard(run)


@router.get("/auth/jwks.json", openapi_extra=DOC_JWKS, responses=RESP_JWKS)
async def jwks(request: Request) -> Response:
    """Publishes validated public keys and decides nothing.

    The document is built from the private key at startup and asserted public by
    `LocalKeySet.load`, which refuses any RSA private parameter. So "no private
    material is published" is a property of the loader every verifier uses, not
    of this handler remembering to filter.
    """
    service = _service(request)
    return JSONResponse(
        service.signing_key.jwks(),
        headers={
            # Public, cacheable, and bounded well below the shortest rotation
            # step. A JWKS cached longer than the retire deadline is the gap
            # the acknowledgement step exists to close.
            "Cache-Control": "public, max-age=300",
            "Content-Type": "application/json",
        },
    )


# ---------------------------------------------------------------------------
# The administrative lifecycle
# ---------------------------------------------------------------------------


@router.get("/admin/users", openapi_extra=DOC_LIST_USERS, responses=RESP_LIST_USERS)
async def list_users(request: Request) -> Response:
    """API-ADMIN-001: gated on the scope, never on the role name."""

    async def run() -> Response:
        service = _service(request)
        principal = await service.authenticate(request.headers.get("authorization"))
        AuthService.require_scope(principal, scope_map.ADMIN_USERS_READ)
        rows = await service.repository.list_users()
        return JSONResponse(
            {
                "users": [
                    {
                        "user_id": str(row["user_id"]),
                        "username": row["username"],
                        "display_name": row["display_name"],
                        "role": row["role_name"],
                        "scopes": sorted(row["scopes"]),
                        "status": row["status"],
                        "credential_version": row["credential_version"],
                        "authz_version": row["authz_version"],
                    }
                    for row in rows
                ]
            },
            headers={"Cache-Control": "no-store"},
        )

    return await _guard(run)


@router.post("/admin/users", openapi_extra=DOC_CREATE_USER, responses=RESP_CREATE_USER)
async def create_user(request: Request) -> Response:
    async def run() -> Response:
        service = _service(request)
        principal = await service.authenticate(request.headers.get("authorization"))
        AuthService.require_scope(principal, scope_map.ADMIN_USERS_WRITE)

        payload = await _body(request, CreateUserRequest)
        assert isinstance(payload, CreateUserRequest)
        user_id = await service.create_user(
            username=payload.username,
            display_name=payload.display_name,
            role_suffix=payload.role,
            scopes=payload.scopes,
            password=payload.password,
            # The new subject's own names, refused as its password. Passed here
            # rather than baked into the blocklist because they are not
            # constants; a list that tried to hold them would go stale for
            # every project deployed after it was written.
            forbidden=(payload.username, payload.display_name),
        )
        return JSONResponse({"user_id": str(user_id)}, status_code=201)

    return await _guard(run)


@router.patch("/admin/users/{user_id}", openapi_extra=DOC_UPDATE_USER, responses=RESP_UPDATE_USER)
async def update_user(request: Request, user_id: str) -> Response:
    """Three concerns, three version bumps, applied in a fixed order."""

    async def run() -> Response:
        service = _service(request)
        principal = await service.authenticate(request.headers.get("authorization"))
        AuthService.require_scope(principal, scope_map.ADMIN_USERS_WRITE)

        try:
            target = UUID(user_id)
        except ValueError as exc:
            raise errors.InvalidRequest("user_id is not a uuid") from exc

        payload = await _body(request, UpdateUserRequest)
        assert isinstance(payload, UpdateUserRequest)
        if not any((payload.role, payload.scopes, payload.status, payload.password)):
            raise errors.InvalidRequest("no change was requested")
        if (payload.role is None) != (payload.scopes is None):
            # Together or not at all: the ceiling is a property of the role, so
            # changing one without the other would check the new scopes against
            # the old role or the reverse.
            raise errors.InvalidRequest("role and scopes are set together or not at all")

        applied: dict[str, int] = {}
        if payload.role is not None and payload.scopes is not None:
            version = await service.set_authorization(
                target, role_suffix=payload.role, scopes=payload.scopes
            )
            if version is None:
                return JSONResponse({"error": "not_found"}, status_code=404)
            applied["authz_version"] = version
        if payload.status is not None:
            version = await service.set_status(target, payload.status)
            if version is None:
                return JSONResponse({"error": "not_found"}, status_code=404)
            applied["authz_version"] = version
        if payload.password is not None:
            version = await service.set_password(target, payload.password)
            if version is None:
                return JSONResponse({"error": "not_found"}, status_code=404)
            applied["credential_version"] = version

        return JSONResponse({"user_id": user_id, **applied})

    return await _guard(run)


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


@router.post("/auth/agent-token", openapi_extra=DOC_AGENT_TOKEN, responses=RESP_AGENT_TOKEN)
async def agent_token(request: Request) -> Response:
    """Decides whether this credential is current. Never the agent's authority.

    The scopes in the token are the stored ones, exactly as for a person. An
    agent that could ask for scopes would be an agent that decides what it may
    do, which is what `§6`'s table refuses in one line.
    """

    async def run() -> Response:
        payload = await _body(request, AgentTokenRequest)
        assert isinstance(payload, AgentTokenRequest)
        issued = await _service(request).agent_token(payload.agent_id, payload.secret)
        return JSONResponse(
            {
                "access_token": issued.token,
                "token_type": "Bearer",
                "expires_at": issued.expires_at,
                "token_use": issued.token_use,
            },
            headers={"Cache-Control": "no-store"},
        )

    return await _guard(run)


@router.get("/admin/agents", openapi_extra=DOC_LIST_AGENTS, responses=RESP_LIST_AGENTS)
async def list_agents(request: Request) -> Response:
    async def run() -> Response:
        service = _service(request)
        principal = await service.authenticate(request.headers.get("authorization"))
        AuthService.require_scope(principal, scope_map.ADMIN_AGENTS_READ)
        rows = await service.repository.list_agents()
        return JSONResponse(
            {
                "agents": [
                    {
                        "agent_id": str(row["agent_id"]),
                        "name": row["name"],
                        "description": row["description"],
                        "role": row["role_name"],
                        "scopes": sorted(row["scopes"]),
                        "status": row["status"],
                        "authz_version": row["authz_version"],
                        "owner_id": str(row["owner_id"]),
                        # An expiry an operator cannot see is an outage with a
                        # countdown (ADR 0172). Null for a credential issued
                        # before Session 15, which does not expire.
                        "secret_expires_at": (
                            row["secret_expires_at"].isoformat()
                            if row["secret_expires_at"]
                            else None
                        ),
                    }
                    for row in rows
                ]
            },
            headers={"Cache-Control": "no-store"},
        )

    return await _guard(run)


@router.post("/admin/agents", openapi_extra=DOC_CREATE_AGENT, responses=RESP_CREATE_AGENT)
async def create_agent(request: Request) -> Response:
    """Returns the secret ONCE, and this is the only response that ever carries it.

    If the response is lost the secret is unrecoverable: there is no retrieval
    function in either migration and no field to read it from. The documented
    recovery is `rotate-secret`, which is a different act with a different
    consequence -- it moves `authz_version`, so every token the old secret
    produced stops working.
    """

    async def run() -> Response:
        service = _service(request)
        principal = await service.authenticate(request.headers.get("authorization"))
        AuthService.require_scope(principal, scope_map.ADMIN_AGENTS_WRITE)

        payload = await _body(request, CreateAgentRequest)
        assert isinstance(payload, CreateAgentRequest)
        agent_id, secret = await service.create_agent(
            name=payload.name,
            description=payload.description,
            role_suffix=payload.role,
            scopes=payload.scopes,
            # The administrator who created it. `owner_id` is NOT NULL and a real
            # foreign key (0011): an agent with no owner is an authority nobody
            # is accountable for, and taking the owner from the request would let
            # an administrator create one in somebody else's name.
            owner_id=principal.user_id,
            # Omitted means the deployment's default (ADR 0172). Out of bounds is
            # refused rather than clamped, so a lifetime an administrator asked
            # for is never silently shortened.
            ttl_seconds=payload.secret_ttl_seconds,
        )
        return JSONResponse(
            {
                "agent_id": str(agent_id),
                "secret": secret,
                "shown_once": True,
            },
            status_code=201,
            headers={"Cache-Control": "no-store"},
        )

    return await _guard(run)


@router.post(
    "/admin/agents/{agent_id}/rotate-secret",
    openapi_extra=DOC_ROTATE_SECRET,
    responses=RESP_ROTATE_SECRET,
)
async def rotate_agent_secret(request: Request, agent_id: str) -> Response:
    async def run() -> Response:
        service = _service(request)
        principal = await service.authenticate(request.headers.get("authorization"))
        AuthService.require_scope(principal, scope_map.ADMIN_AGENTS_WRITE)

        try:
            target = UUID(agent_id)
        except ValueError as exc:
            raise errors.InvalidRequest("agent_id is not a uuid") from exc

        rotated = await service.rotate_agent_secret(target)
        if rotated is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        secret, version = rotated
        return JSONResponse(
            {
                "agent_id": agent_id,
                "secret": secret,
                "shown_once": True,
                "authz_version": version,
            },
            headers={"Cache-Control": "no-store"},
        )

    return await _guard(run)


@router.patch(
    "/admin/agents/{agent_id}", openapi_extra=DOC_UPDATE_AGENT, responses=RESP_UPDATE_AGENT
)
async def update_agent(request: Request, agent_id: str) -> Response:
    async def run() -> Response:
        service = _service(request)
        principal = await service.authenticate(request.headers.get("authorization"))
        AuthService.require_scope(principal, scope_map.ADMIN_AGENTS_WRITE)

        try:
            target = UUID(agent_id)
        except ValueError as exc:
            raise errors.InvalidRequest("agent_id is not a uuid") from exc

        payload = await _body(request, UpdateAgentRequest)
        assert isinstance(payload, UpdateAgentRequest)
        if not any((payload.role, payload.scopes, payload.status)):
            raise errors.InvalidRequest("no change was requested")
        if (payload.role is None) != (payload.scopes is None):
            raise errors.InvalidRequest("role and scopes are set together or not at all")

        applied: dict[str, int] = {}
        if payload.role is not None and payload.scopes is not None:
            version = await service.set_agent_authorization(
                target, role_suffix=payload.role, scopes=payload.scopes
            )
            if version is None:
                return JSONResponse({"error": "not_found"}, status_code=404)
            applied["authz_version"] = version
        if payload.status is not None:
            version = await service.set_agent_status(target, payload.status)
            if version is None:
                return JSONResponse({"error": "not_found"}, status_code=404)
            applied["authz_version"] = version

        return JSONResponse({"agent_id": agent_id, **applied})

    return await _guard(run)


@router.get("/admin/audit", openapi_extra=DOC_LIST_AUDIT, responses=RESP_LIST_AUDIT)
async def list_agent_audit(request: Request) -> Response:
    """The one read path to `app_private.agent_audit` (ADR 0142).

    **Four pieces, in this order, and the order is the point**: `_service`,
    `authenticate`, `require_scope`, and only then the query string. A caller
    that has not proved who it is cannot use `strict_query`'s refusals to
    enumerate which filters this endpoint takes -- and by the time any of them
    can fire, the caller is an authenticated administrator, which is the shape
    `errors.invalid` is reserved for (ADR 0097).

    **`admin_audit:read`, not `admin_agents:read`.** Listing which agents exist
    and reading what they did are different authorities, and reusing the roster
    scope would have made that one decision, taken once, by whoever first
    granted the roster.

    **Nothing here filters by the caller.** An administrator holding the scope
    reads the whole record; `agent_id` and `owner_id` narrow a permitted read
    rather than authorize one. That is why they can be parameters at all, and it
    is the opposite of the agent plane's audit functions, which take no identity
    argument precisely because there the parameter WOULD be the authority
    (SEC-PARAM-001, D473).
    """

    async def run() -> Response:
        service = _service(request)
        principal = await service.authenticate(request.headers.get("authorization"))
        AuthService.require_scope(principal, scope_map.ADMIN_AUDIT_READ)

        # `multi_items()` and not the mapping: the mapping is where a repeated
        # parameter has already been resolved to its last value, silently
        # (measured, Run 7). This is the same reason `_body` goes through
        # `strict_json` rather than `request.json()`, one layer earlier.
        try:
            supplied = strict_query.parse(
                request.query_params.multi_items(), AUDIT_QUERY_PARAMETERS
            )
            agent_id = (
                strict_query.as_uuid("agent_id", supplied["agent_id"])
                if "agent_id" in supplied
                else None
            )
            owner_id = (
                strict_query.as_uuid("owner_id", supplied["owner_id"])
                if "owner_id" in supplied
                else None
            )
            limit = (
                strict_query.as_bounded_int(
                    "limit",
                    supplied["limit"],
                    minimum=AUDIT_LIMIT_MIN,
                    maximum=AUDIT_LIMIT_MAX,
                )
                if "limit" in supplied
                else AUDIT_LIMIT_DEFAULT
            )
        except strict_query.InvalidQuery as exc:
            raise errors.InvalidRequest(str(exc)) from exc

        rows = await service.repository.list_agent_audit(
            agent_id=agent_id, owner_id=owner_id, limit=limit
        )
        return JSONResponse(
            {
                "audit": [
                    {
                        "id": str(row["id"]),
                        "source": row["source"],
                        "agent_id": str(row["agent_id"]),
                        "owner_id": str(row["owner_id"]),
                        "tool": row["tool"],
                        # NULL on every `database` row, and that is D500 rather
                        # than a serialization gap: migration 0019's write RPCs
                        # insert no request id, so the two records for one MCP
                        # write join by agent, tool and time. Rendered anyway,
                        # because an absent key and a null one read the same to
                        # a client and only one of them is honest.
                        "request_id": None if row["request_id"] is None else str(row["request_id"]),
                        # Already redacted, by the capability lock's
                        # `audit.redact` and in the runtime (D479). This service
                        # redacts nothing: a second redaction here would be a
                        # second authority over one rule, and the one that is
                        # reviewed is the lock's.
                        "parameters": row["parameters"],
                        "outcome": row["outcome"],
                        "row_count": row["row_count"],
                        "elapsed_ms": row["elapsed_ms"],
                        "started_at": row["started_at"].isoformat(),
                        "completed_at": (
                            None if row["completed_at"] is None else row["completed_at"].isoformat()
                        ),
                    }
                    for row in rows
                ],
                "limit": limit,
            },
            headers={"Cache-Control": "no-store"},
        )

    return await _guard(run)
