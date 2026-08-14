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

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app import errors
from app import scopes as scope_map
from app.models import CreateUserRequest, LoginRequest, UpdateUserRequest
from app.service import AuthService
from app.strict_json import MalformedBody, parse_object

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

router = APIRouter()


def _service(request: Request) -> AuthService:
    return request.app.state.service


async def _body(request: Request, model: type) -> object:
    """Read, bound, parse strictly, then validate. In that order.

    The size bound is applied to the raw bytes by `parse_object` before the
    document is built, because a parser that has already allocated the body has
    already paid for it.
    """
    try:
        document = parse_object(await request.body())
    except MalformedBody as exc:
        raise errors.InvalidRequest(str(exc)) from exc
    try:
        return model(**document)
    except ValidationError as exc:
        # The first error's type, never its input value: a validation error
        # renders the offending value, and the offending value can be a password.
        kinds = sorted({item["type"] for item in exc.errors()})
        raise errors.InvalidRequest(f"request body is not valid: {kinds}") from exc


async def _guard(handler: Callable[[], Awaitable[Response]]) -> Response:
    """One place the four exception types become responses.

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
    except errors.InvalidRequest as exc:
        return errors.invalid(str(exc))


# ---------------------------------------------------------------------------
# Human endpoints
# ---------------------------------------------------------------------------


@router.post("/auth/login")
async def login(request: Request) -> Response:
    """API-AUTH-001. Issues a short-lived token, or fails identically four ways."""

    async def run() -> Response:
        payload = await _body(request, LoginRequest)
        assert isinstance(payload, LoginRequest)
        issued = await _service(request).login(payload.username, payload.password)
        return JSONResponse(
            {
                "access_token": issued.token,
                "token_type": "Bearer",
                "expires_at": issued.expires_at,
                "token_use": issued.token_use,
            },
            # No-store on every response carrying a token. A token in a shared
            # cache is a token issued to whoever the cache serves next.
            headers={"Cache-Control": "no-store"},
        )

    return await _guard(run)


@router.get("/auth/me")
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


@router.get("/auth/jwks.json")
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


@router.get("/admin/users")
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


@router.post("/admin/users")
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


@router.patch("/admin/users/{user_id}")
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
