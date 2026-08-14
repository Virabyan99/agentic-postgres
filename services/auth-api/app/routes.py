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
from app.models import (
    AgentTokenRequest,
    CreateAgentRequest,
    CreateUserRequest,
    LoginRequest,
    UpdateAgentRequest,
    UpdateUserRequest,
)
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


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


@router.post("/auth/agent-token")
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


@router.get("/admin/agents")
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
                    }
                    for row in rows
                ]
            },
            headers={"Cache-Control": "no-store"},
        )

    return await _guard(run)


@router.post("/admin/agents")
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


@router.post("/admin/agents/{agent_id}/rotate-secret")
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


@router.patch("/admin/agents/{agent_id}")
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
