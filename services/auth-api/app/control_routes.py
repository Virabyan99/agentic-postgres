"""The management API, `/v1` (Session 37, ADR 0251-0253).

Served only in `APP_MODE=control`, by the control project's own `auth`
container, behind its `apg-<key>-control` router (`{api}/v1` stripped to
`/v1`). `routes.py`'s rules hold here unchanged: every body is parsed by
`strict_json` and validated by a closed model before anything else; no
authentication failure says why; every response is `no-store`.

**One guard** (`_guard`) turns the exception types into responses, and **one
table** (`control_roles.MATRIX`) says what each route needs: every handler
names nothing but its own route, and `_caller` / `_member` read the table by
the route's name. A non-member of an organisation gets the `404` a missing
organisation gets, and so does an id that is not a uuid (D2053).

Run 5 added the keys, projects and operations routes: a management key
(`apg_…`) reaches only `control_roles.KEY_SCOPES`' routes, and `POST
/v1/projects` is refused as `not_available` while its ledger row is not
offered (ADR 0254).

Session 38 added the project writes -- create, sleep, wake, resize, export,
delete -- and the cancel (ADR 0256, D2165). Each answers `202` with the
operation it recorded; the work is the reconciler's, followed at
`GET /v1/operations/{id}`. Each is `not_available` while its type is not
accepted, before its body is read.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app import control_roles, errors, openapi_docs, refresh_sessions, strict_query
from app.control_service import KEY_PREFIX, ControlPrincipal, ControlService
from app.models import (
    AcceptInvitationRequest,
    BranchLimitReachedResponse,
    CapacityExhaustedResponse,
    ConfirmFactorRequest,
    ConflictResponse,
    ControlLoginRequest,
    ControlRefusedResponse,
    CreateBranchRequest,
    CreateOrganizationRequest,
    CreateProjectRequest,
    CreateRestoreRequest,
    FactorEnrolmentResponse,
    IdleSleepRequest,
    InvitationResponse,
    KeyResponse,
    LogoutRequest,
    MintInvitationRequest,
    MintKeyRequest,
    NotAvailableResponse,
    OperationAcceptedResponse,
    PlanInterestRequest,
    RefreshRequest,
    ResetBranchRequest,
    ResizeProjectRequest,
    RotateCredentialRequest,
    SessionTokenResponse,
    SetMemberRoleRequest,
)
from app.routes import _body

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

router = APIRouter(prefix="/v1")

#: Every management response is `no-store`: a token, a seed, an invitation, a
#: member list -- nothing this surface answers belongs in a shared cache.
NO_STORE = {"Cache-Control": "no-store"}

#: Session 43 (ADR 0281). The console's session: two `__Host-` cookies --
#: `HttpOnly; Secure; SameSite=Strict; Path=/`, no `Domain` -- set by the
#: session routes when a request carries `X-Apg-Console: 1`, and honoured only
#: with that header (which no other origin can send without a preflight that no
#: route answers) and, on a write, only with the console's own `Origin`. A
#: request with `Authorization` is bearer mode and ignores cookies: the CLI and
#: management keys are unchanged.
ACCESS_COOKIE = "__Host-apg_access"
REFRESH_COOKIE = "__Host-apg_refresh"
CONSOLE_HEADER = "x-apg-console"
_READS = frozenset({"GET", "HEAD"})


def _refused(description: str) -> dict[str, Any]:
    return {"model": ControlRefusedResponse, "description": description}


NOT_A_MEMBER = _refused(
    "`not_found`: the organisation does not exist, or the caller is not a member of it -- "
    "one answer for both, so an id says nothing about whether it exists."
)
KEY_REFUSED = _refused(
    "`human_session_required`: a management key cannot reach this route -- every route that "
    "mints a credential, and oneself, needs a person's session."
)
FACTOR_GATE = _refused(
    "`authorization_failed`: the caller's role is below what the route needs; or "
    "`second_factor_required`: the caller holds owner or admin somewhere, or the registry "
    "administrator's scope, and has not enrolled a second factor."
)


def _service(request: Request) -> ControlService:
    return request.app.state.control


def _route(request: Request) -> str:
    """The matched route's name, which is the key `control_roles.MATRIX` uses."""
    return request.scope["route"].name


def _console(request: Request) -> bool:
    """The request says it is the console's (ADR 0281)."""
    return request.headers.get(CONSOLE_HEADER) == "1"


def _from_console_origin(request: Request) -> bool:
    """`Origin` is the console's own, byte for byte."""
    return request.headers.get("origin") == request.app.state.console_origin


def _bearer(request: Request) -> str | None:
    """The credential this request presents, as an `Authorization` value.

    `Authorization` wins and cookies are then ignored. Otherwise the access
    cookie, but only with the console's header and -- for anything but a read --
    the console's `Origin`; a cookie without them is no credential at all. A
    key never rides a cookie (ADR 0281 item 2)."""
    authorization = request.headers.get("authorization")
    if authorization is not None:
        return authorization
    cookie = request.cookies.get(ACCESS_COOKIE)
    if cookie is None or not _console(request):
        return None
    if cookie.startswith(KEY_PREFIX):
        raise errors.AuthenticationFailed("a management key in a cookie")
    if request.method not in _READS and not _from_console_origin(request):
        return None
    return f"Bearer {cookie}"


def _console_session_request(request: Request) -> bool:
    """For the three session routes: whether this is the console's request.

    A login, a refresh and a logout are writes, so in console mode each needs
    the console's `Origin`; one from anywhere else is refused as unauthenticated
    before its body is read."""
    if not _console(request):
        return False
    if not _from_console_origin(request):
        raise errors.AuthenticationFailed("a console session request from another origin")
    return True


async def _caller(request: Request) -> ControlPrincipal:
    """The bearer, verified, with the factor gate applied for this route."""
    return await _service(request).authenticate(_bearer(request), _route(request))


def _query(request: Request, allowed: tuple[str, ...]) -> dict[str, str]:
    """The query string, each parameter at most once and every name allowed."""
    try:
        return strict_query.parse(request.query_params.multi_items(), allowed)
    except strict_query.InvalidQuery as exc:
        raise errors.InvalidRequest(str(exc)) from exc


def _uuid(value: str) -> UUID:
    """A path id, or `not_found`: a malformed id names nothing that exists."""
    try:
        return UUID(value)
    except ValueError as exc:
        raise errors.ControlRefused(errors.NOT_FOUND) from exc


async def _member(request: Request, organization: str) -> tuple[ControlPrincipal, UUID]:
    """The caller, holding at least the route's role in `organization`."""
    caller = await _caller(request)
    org = _uuid(organization)
    ControlService.require_role(caller, org, control_roles.MATRIX[_route(request)])
    return caller, org


async def _guard(handler: Callable[[], Awaitable[Response]]) -> Response:
    """`routes._guard`'s shape, with the management API's refusals added."""
    try:
        response = await handler()
    except errors.ControlRefused as refusal:
        return errors.control_refused(refusal)
    except errors.AuthenticationFailed:
        response = errors.unauthenticated()
    except errors.AuthorizationFailed:
        response = errors.unauthorized()
    except errors.MalformedRequest:
        response = errors.malformed()
    except errors.InvalidRequest as exc:
        response = errors.invalid(str(exc))
    response.headers.update(NO_STORE)
    return response


def _session_cookie(response: Response, key: str, value: str, max_age: int) -> None:
    response.set_cookie(
        key, value, max_age=max_age, path="/", secure=True, httponly=True, samesite="strict"
    )


def _tokens(issued: Any, refresh: str, *, console: bool = False) -> JSONResponse:
    if not console:
        return JSONResponse(
            {
                "access_token": issued.token,
                "token_type": "Bearer",
                "expires_at": issued.expires_at,
                "token_use": issued.token_use,
                "refresh_token": refresh,
            }
        )
    # The console's answer holds no token: both live in cookies no script can
    # read (ADR 0281), the access cookie expiring with the token it carries.
    response = JSONResponse({"expires_at": issued.expires_at, "token_use": issued.token_use})
    _session_cookie(
        response, ACCESS_COOKIE, issued.token, max(1, issued.expires_at - int(time.time()))
    )
    _session_cookie(response, REFRESH_COOKIE, refresh, refresh_sessions.REFRESH_TTL_SECONDS)
    return response


async def _presented_refresh(request: Request, console: bool, model: type) -> str | None:
    """The refresh token a refresh or a logout names: the body's, or -- in
    console mode, with an empty body -- the refresh cookie's (`None` if the
    console sent neither)."""
    if console and not (await request.body()).strip():
        return request.cookies.get(REFRESH_COOKIE) or None
    payload = await _body(request, model)
    return payload.refresh_token  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# The session plane
# ---------------------------------------------------------------------------


@router.post(
    "/sessions",
    openapi_extra=openapi_docs.described(
        summary="Log in: a password, and the second factor once one is enabled",
        description=(
            "The password is verified first, an unknown username against a dummy hash, so "
            "every password failure is one answer that costs the same. Only then, if the person "
            "has an enabled second factor, is `totp_code` required: `second_factor_required` "
            "without one, `second_factor_invalid` with a wrong one or one already used. "
            "With `X-Apg-Console: 1` and the console's `Origin`, both tokens are set as "
            "`__Host-` cookies (`HttpOnly; Secure; SameSite=Strict`) and the body holds neither."
        ),
        request_model=ControlLoginRequest,
    ),
    responses={
        200: openapi_docs.ok("An access token and the session's first refresh token.",
                             SessionTokenResponse),
        400: openapi_docs.MALFORMED,
        401: _refused("`authentication_failed`, `second_factor_required` or "
                      "`second_factor_invalid`."),
    },
)  # fmt: skip
async def create_session(request: Request) -> Response:
    """D2050. The release's login with the second factor as its hook."""

    async def run() -> Response:
        console = _console_session_request(request)
        payload = await _body(request, ControlLoginRequest)
        assert isinstance(payload, ControlLoginRequest)
        issued, refresh = await _service(request).login(
            payload.username, payload.password, payload.totp_code
        )
        return _tokens(issued, refresh, console=console)

    return await _guard(run)


@router.post(
    "/sessions/refresh",
    openapi_extra=openapi_docs.described(
        summary="Exchange a refresh token for an access token and its successor",
        description=(
            "Single use, and every refusal answers identically -- the release's session "
            "plane, unchanged. Confirming a second factor ends every session opened before it. "
            "With `X-Apg-Console: 1` and the console's `Origin`, an empty body reads the "
            "refresh cookie and both cookies are replaced."
        ),
        request_model=RefreshRequest,
    ),
    responses={
        200: openapi_docs.ok("A new access token and its successor.", SessionTokenResponse),
        400: openapi_docs.MALFORMED,
        401: openapi_docs.UNAUTHENTICATED,
    },
)
async def refresh_session(request: Request) -> Response:
    async def run() -> Response:
        console = _console_session_request(request)
        presented = await _presented_refresh(request, console, RefreshRequest)
        if presented is None:
            raise errors.AuthenticationFailed("no refresh token presented")
        issued, successor = await _service(request).refresh(presented)
        return _tokens(issued, successor, console=console)

    return await _guard(run)


@router.delete(
    "/sessions/current",
    status_code=204,
    openapi_extra=openapi_docs.described(
        summary="Log out: end the session a refresh token names",
        description=(
            "Takes the refresh token, not an access token: the command-line client keeps only "
            "the refresh token. Answers 204 whether or not the token named a live session. "
            "With `X-Apg-Console: 1` and the console's `Origin`, an empty body reads the "
            "refresh cookie, and both cookies are cleared."
        ),
        request_model=LogoutRequest,
    ),
    responses={
        204: openapi_docs.no_content("That session is ended, or was already."),
        400: openapi_docs.MALFORMED,
    },
)
async def end_session(request: Request) -> Response:
    async def run() -> Response:
        console = _console_session_request(request)
        presented = await _presented_refresh(request, console, LogoutRequest)
        if presented is not None:
            await _service(request).logout(presented)
        response = Response(status_code=204)
        if console:
            # Cleared with the attributes they were set with, or a browser keeps them.
            for key in (ACCESS_COOKIE, REFRESH_COOKIE):
                response.delete_cookie(key, path="/", secure=True, httponly=True, samesite="strict")
        return response

    return await _guard(run)


# ---------------------------------------------------------------------------
# Oneself and the second factor
# ---------------------------------------------------------------------------


@router.get(
    "/me",
    openapi_extra=openapi_docs.described(
        summary="The caller, their organisations, and their second factor",
        description="Read inside this request. Reachable before a second factor is enrolled.",
    ),
    responses={200: openapi_docs.ok("The caller as they are now."),
               401: openapi_docs.UNAUTHENTICATED},
)  # fmt: skip
async def me(request: Request) -> Response:
    async def run() -> Response:
        caller = await _caller(request)
        return JSONResponse(await _service(request).me(caller))

    return await _guard(run)


@router.post(
    "/me/totp",
    status_code=201,
    openapi_extra=openapi_docs.described(
        summary="Begin enrolling a second factor; the seed is shown once",
        description=(
            "Stores a new seed, not yet enabled, and returns it as base32 and as an "
            "`otpauth://` URI. Beginning again replaces an unconfirmed seed; an enabled factor "
            "is `factor_enabled` -- a lost device is the operator's to reset."
        ),
    ),
    responses={
        201: openapi_docs.created("The seed, in this response and no other.",
                                  FactorEnrolmentResponse),
        401: openapi_docs.UNAUTHENTICATED,
        409: _refused("`factor_enabled`."),
    },
)  # fmt: skip
async def begin_factor(request: Request) -> Response:
    async def run() -> Response:
        caller = await _caller(request)
        return JSONResponse(await _service(request).begin_factor(caller), status_code=201)

    return await _guard(run)


@router.post(
    "/me/totp/confirm",
    openapi_extra=openapi_docs.described(
        summary="Enable the second factor with a current code",
        description=(
            "Enables the factor and ends every session the caller had, so no session opened "
            "without the code outlives enrolment. The caller logs in again, with a code."
        ),
        request_model=ConfirmFactorRequest,
    ),
    responses={
        200: openapi_docs.ok("The factor is enabled; `sessions_ended` sessions ended."),
        400: openapi_docs.MALFORMED,
        401: openapi_docs.UNAUTHENTICATED,
        409: _refused("`factor_enabled`."),
        422: _refused("`second_factor_invalid`: a wrong code, or nothing to confirm."),
    },
)
async def confirm_factor(request: Request) -> Response:
    async def run() -> Response:
        caller = await _caller(request)
        payload = await _body(request, ConfirmFactorRequest)
        assert isinstance(payload, ConfirmFactorRequest)
        ended = await _service(request).confirm_factor(caller, payload.totp_code)
        return JSONResponse({"enabled": True, "sessions_ended": ended})

    return await _guard(run)


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------


@router.post(
    "/invitations",
    status_code=201,
    openapi_extra=openapi_docs.described(
        summary="Mint an invitation; its token is shown once",
        description=(
            "With `organization_id` and `role`: a membership invitation, minted by an admin or "
            "owner of that organisation for a role at or below their own (only an owner "
            "invites an owner). With neither: an account invitation, minted by the registry "
            "administrator with an enabled second factor. Lives 72 hours unless "
            "`expires_in_hours` (1-168) says otherwise. `accept_url` is the console's link, "
            "the token in its fragment, which no request line or log receives."
        ),
        request_model=MintInvitationRequest,
    ),
    responses={
        201: openapi_docs.created("The invitation and its token, once.", InvitationResponse),
        400: openapi_docs.MALFORMED,
        401: openapi_docs.UNAUTHENTICATED,
        403: FACTOR_GATE,
        404: NOT_A_MEMBER,
        422: openapi_docs.INVALID,
    },
)
async def mint_invitation(request: Request) -> Response:
    async def run() -> Response:
        caller = await _caller(request)
        payload = await _body(request, MintInvitationRequest)
        assert isinstance(payload, MintInvitationRequest)
        minted = await _service(request).mint_invitation(
            caller,
            organization=payload.organization_id,
            role=payload.role,
            expires_in_hours=payload.expires_in_hours,
        )
        # The console's link, the token in its FRAGMENT (ADR 0282): a browser
        # sends no fragment in a request line, a proxy log or a `Referer`.
        token = minted["invitation_token"]
        linked = {
            "id": minted["id"],
            "invitation_token": token,
            "accept_url": f"{request.app.state.console_origin}/accept#{token}",
        }
        return JSONResponse({**linked, **minted}, status_code=201)

    return await _guard(run)


@router.post(
    "/invitations/accept",
    openapi_extra=openapi_docs.described(
        summary="Accept an invitation",
        description=(
            "Signed in: the token alone, and the caller joins the organisation. Otherwise the "
            "token with a username, a display name and a password: the account and any "
            "membership are created in one transaction. A used, expired, revoked or unknown "
            "token is one answer, `invitation_invalid`; a taken username is `username_taken`, "
            "answered only after the token validated, and the token stays unspent."
        ),
        request_model=AcceptInvitationRequest,
    ),
    responses={
        200: openapi_docs.ok("The account, and the organisation and role it joined."),
        400: openapi_docs.MALFORMED,
        401: _refused("`invitation_invalid` (or `authentication_failed` for a bad bearer)."),
        409: _refused("`username_taken`."),
        422: openapi_docs.INVALID,
    },
)
async def accept_invitation(request: Request) -> Response:
    async def run() -> Response:
        payload = await _body(request, AcceptInvitationRequest)
        assert isinstance(payload, AcceptInvitationRequest)
        # Signed in by bearer OR by the console's cookie (ADR 0281): the same
        # rule every other route reads, so a cookie without the console's header
        # and origin is no session here either.
        caller = await _caller(request) if _bearer(request) is not None else None
        accepted = await _service(request).accept_invitation(
            payload.invitation_token,
            caller=caller,
            username=payload.username,
            display_name=payload.display_name,
            password=payload.password,
        )
        return JSONResponse(accepted)

    return await _guard(run)


# ---------------------------------------------------------------------------
# Organisations and members
# ---------------------------------------------------------------------------


@router.get(
    "/organizations",
    openapi_extra=openapi_docs.described(
        summary="The caller's organisations and their role in each",
        description="Only organisations the caller belongs to; there is no other listing.",
    ),
    responses={200: openapi_docs.ok("The caller's organisations."),
               401: openapi_docs.UNAUTHENTICATED, 403: FACTOR_GATE},
)  # fmt: skip
async def list_organizations(request: Request) -> Response:
    async def run() -> Response:
        caller = await _caller(request)
        rows = await _service(request).list_organizations(caller)
        return JSONResponse({"organizations": rows})

    return await _guard(run)


@router.post(
    "/organizations",
    status_code=201,
    openapi_extra=openapi_docs.described(
        summary="Create an organisation; the caller becomes its owner",
        description="An owner must enrol a second factor before using anything but enrolment.",
        request_model=CreateOrganizationRequest,
    ),
    responses={201: openapi_docs.created("The organisation."), 400: openapi_docs.MALFORMED,
               401: openapi_docs.UNAUTHENTICATED, 403: FACTOR_GATE},
)  # fmt: skip
async def create_organization(request: Request) -> Response:
    async def run() -> Response:
        caller = await _caller(request)
        payload = await _body(request, CreateOrganizationRequest)
        assert isinstance(payload, CreateOrganizationRequest)
        created = await _service(request).create_organization(caller, payload.name)
        return JSONResponse(created, status_code=201)

    return await _guard(run)


@router.get(
    "/organizations/{organization}",
    openapi_extra=openapi_docs.described(
        summary="One of the caller's organisations",
        description="Any member. A non-member and a missing organisation get one answer.",
    ),
    responses={200: openapi_docs.ok("The organisation and the caller's role."),
               401: openapi_docs.UNAUTHENTICATED, 403: FACTOR_GATE, 404: NOT_A_MEMBER},
)  # fmt: skip
async def get_organization(request: Request, organization: str) -> Response:
    async def run() -> Response:
        caller, org = await _member(request, organization)
        return JSONResponse(await _service(request).get_organization(caller, org))

    return await _guard(run)


@router.get(
    "/organizations/{organization}/members",
    openapi_extra=openapi_docs.described(
        summary="An organisation's members",
        description="Any member.",
    ),
    responses={200: openapi_docs.ok("The members and their roles."),
               401: openapi_docs.UNAUTHENTICATED, 403: FACTOR_GATE, 404: NOT_A_MEMBER},
)  # fmt: skip
async def list_members(request: Request, organization: str) -> Response:
    async def run() -> Response:
        caller, org = await _member(request, organization)
        return JSONResponse({"members": await _service(request).list_members(caller, org)})

    return await _guard(run)


@router.patch(
    "/organizations/{organization}/members/{user}",
    openapi_extra=openapi_docs.described(
        summary="Change a member's role",
        description=(
            "Admin and above. Only an owner touches or makes an owner, and the last owner "
            "cannot be demoted (`last_owner`)."
        ),
        request_model=SetMemberRoleRequest,
    ),
    responses={200: openapi_docs.ok("The member's new role."), 400: openapi_docs.MALFORMED,
               401: openapi_docs.UNAUTHENTICATED, 403: FACTOR_GATE, 404: NOT_A_MEMBER,
               409: _refused("`last_owner`.")},
)  # fmt: skip
async def set_member_role(request: Request, organization: str, user: str) -> Response:
    async def run() -> Response:
        caller, org = await _member(request, organization)
        target = _uuid(user)
        payload = await _body(request, SetMemberRoleRequest)
        assert isinstance(payload, SetMemberRoleRequest)
        await _service(request).set_member_role(caller, org, target, payload.role)
        return JSONResponse({"user_id": str(target), "role": payload.role})

    return await _guard(run)


@router.delete(
    "/organizations/{organization}/members/{user}",
    status_code=204,
    openapi_extra=openapi_docs.described(
        summary="Remove a member, revoking their keys in the organisation",
        description=(
            "Admin and above. Only an owner removes an owner, and the last owner stays "
            "(`last_owner`). The account remains; the membership was its authority here."
        ),
    ),
    responses={204: openapi_docs.no_content("The member is removed."),
               401: openapi_docs.UNAUTHENTICATED, 403: FACTOR_GATE, 404: NOT_A_MEMBER,
               409: _refused("`last_owner`.")},
)  # fmt: skip
async def remove_member(request: Request, organization: str, user: str) -> Response:
    async def run() -> Response:
        caller, org = await _member(request, organization)
        await _service(request).remove_member(caller, org, _uuid(user))
        return Response(status_code=204)

    return await _guard(run)


@router.get(
    "/organizations/{organization}/invitations",
    openapi_extra=openapi_docs.described(
        summary="An organisation's invitations",
        description="Admin and above. Never a token, and never a token's hash.",
    ),
    responses={200: openapi_docs.ok("The invitations, spent and unspent."),
               401: openapi_docs.UNAUTHENTICATED, 403: FACTOR_GATE, 404: NOT_A_MEMBER},
)  # fmt: skip
async def list_invitations(request: Request, organization: str) -> Response:
    async def run() -> Response:
        caller, org = await _member(request, organization)
        rows = await _service(request).list_invitations(caller, org)
        return JSONResponse({"invitations": rows})

    return await _guard(run)


@router.delete(
    "/organizations/{organization}/invitations/{invitation}",
    status_code=204,
    openapi_extra=openapi_docs.described(
        summary="Revoke an unspent invitation",
        description="Admin and above. 204 whether or not an unspent invitation had that id.",
    ),
    responses={204: openapi_docs.no_content("That invitation cannot be accepted."),
               401: openapi_docs.UNAUTHENTICATED, 403: FACTOR_GATE, 404: NOT_A_MEMBER},
)  # fmt: skip
async def revoke_invitation(request: Request, organization: str, invitation: str) -> Response:
    async def run() -> Response:
        caller, org = await _member(request, organization)
        await _service(request).revoke_invitation(caller, org, _uuid(invitation))
        return Response(status_code=204)

    return await _guard(run)


# ---------------------------------------------------------------------------
# Keys (D2052, ADR 0253) -- human sessions only
# ---------------------------------------------------------------------------


@router.get(
    "/organizations/{organization}/keys",
    openapi_extra=openapi_docs.described(
        summary="The organisation's keys the caller may see",
        description="A member sees their own keys; an admin or owner sees all. Never a secret.",
    ),
    responses={200: openapi_docs.ok("The keys."), 401: openapi_docs.UNAUTHENTICATED,
               403: KEY_REFUSED, 404: NOT_A_MEMBER},
)  # fmt: skip
async def list_keys(request: Request, organization: str) -> Response:
    async def run() -> Response:
        caller, org = await _member(request, organization)
        return JSONResponse({"keys": await _service(request).list_keys(caller, org)})

    return await _guard(run)


@router.post(
    "/organizations/{organization}/keys",
    status_code=201,
    openapi_extra=openapi_docs.described(
        summary="Mint a management key; it is shown once",
        description=(
            "`apg_<id>_<secret>`, stored as its id and the SHA-256 of its secret. Its scopes come "
            "from the vocabulary (`organizations:read`, `members:read`, `projects:read`, "
            "`operations:read`, `projects:write`) and must be within the minter's role -- a "
            "viewer's key cannot hold `projects:write`. On every request a key's "
            "authority is its scopes intersected with its owner's current role, in this "
            "organisation only; a revoked key, or one whose owner left, is refused."
        ),
        request_model=MintKeyRequest,
    ),
    responses={201: openapi_docs.created("The key, in this response and no other.", KeyResponse),
               400: openapi_docs.MALFORMED, 401: openapi_docs.UNAUTHENTICATED,
               403: KEY_REFUSED, 404: NOT_A_MEMBER, 422: openapi_docs.INVALID},
)  # fmt: skip
async def mint_key(request: Request, organization: str) -> Response:
    async def run() -> Response:
        caller, org = await _member(request, organization)
        payload = await _body(request, MintKeyRequest)
        assert isinstance(payload, MintKeyRequest)
        minted = await _service(request).mint_key(caller, org, payload.name, payload.scopes)
        return JSONResponse(minted, status_code=201)

    return await _guard(run)


@router.delete(
    "/organizations/{organization}/keys/{key_id}",
    status_code=204,
    openapi_extra=openapi_docs.described(
        summary="Revoke a key",
        description=(
            "The caller's own key, or -- for an admin or owner -- any of the organisation's. A key "
            "the caller may not revoke, a missing one and one already revoked are one `not_found`."
        ),
    ),
    responses={204: openapi_docs.no_content("The key is revoked; its next request is refused."),
               401: openapi_docs.UNAUTHENTICATED, 403: KEY_REFUSED, 404: NOT_A_MEMBER},
)  # fmt: skip
async def revoke_key(request: Request, organization: str, key_id: str) -> Response:
    async def run() -> Response:
        caller, org = await _member(request, organization)
        await _service(request).revoke_key(caller, org, key_id)
        return Response(status_code=204)

    return await _guard(run)


# ---------------------------------------------------------------------------
# The registry and its operations (ADR 0251, ADR 0254)
# ---------------------------------------------------------------------------

ORGANIZATION_QUERY = openapi_docs.query_parameter(
    "organization",
    schema={"type": "string", "format": "uuid"},
    description="One of the caller's organisations. A foreign or missing one is `not_found`.",
)


@router.get(
    "/projects",
    openapi_extra=openapi_docs.described(
        summary="The projects of the caller's organisations",
        description=(
            "The registry: projects the operator adopted from their deployed documents. A key "
            "sees its own organisation's only."
        ),
        query_parameters=[ORGANIZATION_QUERY],
    ),
    responses={200: openapi_docs.ok("The projects."), 401: openapi_docs.UNAUTHENTICATED,
               403: FACTOR_GATE, 404: NOT_A_MEMBER, 422: openapi_docs.INVALID},
)  # fmt: skip
async def list_projects(request: Request) -> Response:
    async def run() -> Response:
        caller = await _caller(request)
        named = _query(request, ("organization",)).get("organization")
        org = None if named is None else _uuid(named)
        return JSONResponse({"projects": await _service(request).list_projects(caller, org)})

    return await _guard(run)


NOT_OFFERED = {
    "model": NotAvailableResponse,
    "description": (
        "`not_available`, with the ledger row that says why: the operation is not offered yet, "
        "and nothing is recorded. Or `conflict` (ConflictResponse), with the id of the "
        "operation already holding the project."
    ),
}
ACCEPTED = openapi_docs.ok(
    "Recorded, `pending`: the reconciler executes it; follow it at `/v1/operations/{id}`.",
    OperationAcceptedResponse,
)
NOT_YOURS = _refused(
    "`not_found`: the project is not one of the caller's organisations', does not exist, or "
    "was deleted -- one answer for each."
)


def _accepted(operation: dict[str, Any], **extra: str) -> JSONResponse:
    return JSONResponse({"operation": operation, **extra}, status_code=202)


async def _offered(request: Request) -> ControlPrincipal:
    """The caller, then -- before any body is read -- `not_available` while
    the route's operation type is not accepted (ADR 0254)."""
    caller = await _caller(request)
    ControlService.require_accepted(_route(request))
    return caller


async def _write(
    request: Request,
    caller: ControlPrincipal,
    key: str,
    arguments: dict[str, Any] | None = None,
    **extra: str,
) -> Response:
    """One of the five writes on an existing project: the project, the role
    and the row."""
    operation = await _service(request).write_project(caller, _route(request), key, arguments or {})
    return _accepted(operation, **extra)


@router.post(
    "/projects",
    status_code=202,
    openapi_extra=openapi_docs.described(
        summary="Create a project in a prepared slot",
        description=(
            "Member and above, a person only. `name` is a display name; `profile` the compute "
            "profile; `admin_username` the project's first administrator, who claims the account "
            "with the token whose SHA-256 is `handoff_sha256` -- the token itself never reaches "
            "this plane. With no slot ready the answer is `capacity_exhausted` (`reason: "
            "no_slot`) and nothing is recorded; one creation per organisation is in flight at a "
            "time (`conflict`). Refused `not_available` while `projects_self_service` is not "
            "offered."
        ),
        request_model=CreateProjectRequest,
    ),
    responses={202: ACCEPTED, 400: openapi_docs.MALFORMED, 401: openapi_docs.UNAUTHENTICATED,
               403: FACTOR_GATE, 404: NOT_A_MEMBER,
               409: {"model": CapacityExhaustedResponse,
                     "description": "`plan_limit_reached` (with `entitlement`, `limit`, `plan`, "
                                    "`message`): the "
                                    "organisation's plan allows no further project -- read "
                                    "FIRST; then `capacity_exhausted` with `reason: no_slot`; "
                                    "or `conflict` naming the creation in flight; or "
                                    "`not_available` naming the ledger row."}},
)  # fmt: skip
async def create_project(request: Request) -> Response:
    async def run() -> Response:
        caller = await _offered(request)
        payload = await _body(request, CreateProjectRequest)
        assert isinstance(payload, CreateProjectRequest)
        operation = await _service(request).create_project(
            caller,
            organization=payload.organization,
            name=payload.name,
            profile=payload.profile,
            admin_username=payload.admin_username,
            handoff_sha256=payload.handoff_sha256,
        )
        return _accepted(operation)

    return await _guard(run)


@router.post(
    "/projects/{key}/sleep",
    status_code=202,
    openapi_extra=openapi_docs.described(
        summary="Put a project to sleep",
        description=(
            "Member and above, or a key holding `projects:write`. Its containers are stopped and "
            "kept; while it sleeps a request to it is answered by the edge's 404, and its last "
            "restore point is the moment it went to sleep."
        ),
    ),
    responses={202: ACCEPTED, 401: openapi_docs.UNAUTHENTICATED, 403: FACTOR_GATE,
               404: NOT_YOURS, 409: NOT_OFFERED},
)  # fmt: skip
async def sleep_project(request: Request, key: str) -> Response:
    async def run() -> Response:
        return await _write(request, await _offered(request), key)

    return await _guard(run)


@router.post(
    "/projects/{key}/wake",
    status_code=202,
    openapi_extra=openapi_docs.described(
        summary="Wake a sleeping project",
        description="Member and above, or a key holding `projects:write`.",
    ),
    responses={202: ACCEPTED, 401: openapi_docs.UNAUTHENTICATED, 403: FACTOR_GATE,
               404: NOT_YOURS, 409: NOT_OFFERED},
)  # fmt: skip
async def wake_project(request: Request, key: str) -> Response:
    async def run() -> Response:
        return await _write(request, await _offered(request), key)

    return await _guard(run)


@router.put(
    "/projects/{key}/compute",
    status_code=202,
    openapi_extra=openapi_docs.described(
        summary="Change a project's compute profile",
        description=(
            "Member and above, or a key holding `projects:write`. Resizing restarts the database "
            "and the services that use it; `message` says how long that was measured to take, or "
            "that it has not been measured on this server yet. A profile the server has no room "
            "for fails the operation with `capacity_exhausted` (`reason: admission`), and the "
            "project stays as it was."
        ),
        request_model=ResizeProjectRequest,
    ),
    responses={202: ACCEPTED, 400: openapi_docs.MALFORMED, 401: openapi_docs.UNAUTHENTICATED,
               403: FACTOR_GATE, 404: NOT_YOURS, 409: NOT_OFFERED},
)  # fmt: skip
async def resize_project(request: Request, key: str) -> Response:
    async def run() -> Response:
        caller = await _offered(request)
        payload = await _body(request, ResizeProjectRequest)
        assert isinstance(payload, ResizeProjectRequest)
        return await _write(
            request,
            caller,
            key,
            {"profile": payload.profile},
            message=ControlService.resize_message(),
        )

    return await _guard(run)


@router.post(
    "/projects/{key}/export",
    status_code=202,
    openapi_extra=openapi_docs.described(
        summary="Export a project's data",
        description=(
            "Member and above, a person only. An archive of the project's own schemas; when the "
            "operation succeeds, `GET /v1/operations/{id}` returns its `download_url` -- valid at "
            "most 15 minutes -- ONCE, to the person who asked."
        ),
    ),
    responses={202: ACCEPTED, 401: openapi_docs.UNAUTHENTICATED, 403: FACTOR_GATE,
               404: NOT_YOURS, 409: NOT_OFFERED},
)  # fmt: skip
async def export_project(request: Request, key: str) -> Response:
    async def run() -> Response:
        return await _write(request, await _offered(request), key)

    return await _guard(run)


@router.delete(
    "/projects/{key}",
    status_code=202,
    openapi_extra=openapi_docs.described(
        summary="Delete a project",
        description=(
            "Admin and above, a person only. The project's containers and data are removed; its "
            "backups are kept by the operator. A deleted project is never reissued."
        ),
    ),
    responses={202: ACCEPTED, 401: openapi_docs.UNAUTHENTICATED, 403: FACTOR_GATE,
               404: NOT_YOURS, 409: NOT_OFFERED},
)  # fmt: skip
async def delete_project(request: Request, key: str) -> Response:
    async def run() -> Response:
        return await _write(request, await _offered(request), key)

    return await _guard(run)


@router.post(
    "/projects/{key}/credentials",
    status_code=202,
    openapi_extra=openapi_docs.described(
        summary="Set a customer role's database credential",
        description=(
            "Member and above, a person only. `role` is `customer_app` (the pooled door) or "
            "`customer_admin` (the direct door); `verifier` is the SCRAM-SHA-256 verifier your "
            "CLI computed from a password it wrote to a file on your machine -- the password "
            "itself never reaches this plane, and there is no way to send one. The reconciler "
            "sets it and both doors re-read their lists; the previous credential stops working "
            "then. `not_available` naming `pooled_endpoint` for a project without public doors."
        ),
        request_model=RotateCredentialRequest,
    ),
    responses={202: ACCEPTED, 400: openapi_docs.MALFORMED, 401: openapi_docs.UNAUTHENTICATED,
               403: FACTOR_GATE, 404: NOT_YOURS, 409: NOT_OFFERED},
)  # fmt: skip
async def rotate_credential(request: Request, key: str) -> Response:
    async def run() -> Response:
        caller = await _offered(request)
        payload = await _body(request, RotateCredentialRequest)
        assert isinstance(payload, RotateCredentialRequest)
        operation = await _service(request).rotate_credential(
            caller, key, payload.role, payload.verifier
        )
        return _accepted(operation)

    return await _guard(run)


@router.get(
    "/projects/{key}/connections",
    openapi_extra=openapi_docs.described(
        summary="A project's public database doors",
        description=(
            "Viewer and above, or a key holding `projects:read`. The pooled door (transaction "
            "mode, `customer_app`) and the direct door (a session, `customer_admin`) as the "
            "project's deploy recorded them, and a snippet per client measured through them. "
            "Every snippet's password is a placeholder: the password is the file your CLI "
            "wrote, and this plane never held it. `not_available` naming `pooled_endpoint` for "
            "a project without public doors."
        ),
    ),
    responses={200: openapi_docs.ok("The two doors and the snippets."),
               401: openapi_docs.UNAUTHENTICATED, 403: FACTOR_GATE, 404: NOT_YOURS,
               409: {"model": NotAvailableResponse,
                     "description": "`not_available`: the project has no public doors."}},
)  # fmt: skip
async def get_connections(request: Request, key: str) -> Response:
    async def run() -> Response:
        caller = await _caller(request)
        return JSONResponse(await _service(request).connections(caller, key))

    return await _guard(run)


# ---------------------------------------------------------------------------
# Session 40: branches, restores to a branch, and the backups surface
# (ADR 0271, ADR 0272, ADR 0273). Every route resolves the PROJECT first, so a
# foreign project's branch, a missing project's and a missing branch of the
# caller's own project are the one `not_found` (D2451). The writes are a
# person's (D2468): each carries the branch's own credentials.
# ---------------------------------------------------------------------------

BRANCH_LIMIT = {
    "model": BranchLimitReachedResponse,
    "description": (
        "`branch_limit_reached`: the project already has its one branch, or one is being "
        "created; nothing is recorded. Or `not_available` naming the ledger row, or "
        "`conflict` naming the operation already holding the project."
    ),
}


def _arguments(payload: Any) -> dict[str, Any]:
    """A branch request's members as the row's arguments, unset members left out."""
    return {name: value for name, value in payload.model_dump().items() if value is not None}


@router.get(
    "/projects/{key}/branches",
    openapi_extra=openapi_docs.described(
        summary="A project's branches",
        description=(
            "Viewer and above, or a key holding `projects:read`. Each branch's point -- the one "
            "asked for and the one its restore reached --, its timeline, its two names and its "
            "expiry, as the server last recorded them. A branch is not backed up."
        ),
    ),
    responses={200: openapi_docs.ok("The branches."), 401: openapi_docs.UNAUTHENTICATED,
               403: FACTOR_GATE, 404: NOT_YOURS},
)  # fmt: skip
async def list_branches(request: Request, key: str) -> Response:
    async def run() -> Response:
        caller = await _caller(request)
        return JSONResponse(await _service(request).list_branches(caller, key))

    return await _guard(run)


@router.post(
    "/projects/{key}/branches",
    status_code=202,
    openapi_extra=openapi_docs.described(
        summary="Create a branch at the end of the archive",
        description=(
            "Member and above, a person only. A copy of the project's database restored from its "
            "backups to the newest archived moment, its own two credentials -- the verifiers your "
            "CLI computed; the passwords stay on your machine -- and two names, "
            "`<branch>.pool.<domain>` and `<branch>.direct.<domain>`. One branch per project. "
            "`expires_at` (15 minutes to 7 days ahead) deletes it then. A branch is not backed up."
        ),
        request_model=CreateBranchRequest,
    ),
    responses={202: ACCEPTED, 400: openapi_docs.MALFORMED, 401: openapi_docs.UNAUTHENTICATED,
               403: FACTOR_GATE, 404: NOT_YOURS, 409: BRANCH_LIMIT, 422: openapi_docs.INVALID},
)  # fmt: skip
async def create_branch(request: Request, key: str) -> Response:
    async def run() -> Response:
        caller = await _offered(request)
        payload = await _body(request, CreateBranchRequest)
        assert isinstance(payload, CreateBranchRequest)
        return _accepted(await _service(request).create_branch(caller, key, _arguments(payload)))

    return await _guard(run)


@router.post(
    "/projects/{key}/restores",
    status_code=202,
    openapi_extra=openapi_docs.described(
        summary="Restore a project to a point, into a new branch",
        description=(
            "Member and above, a person only. A branch at `target_time`, which must be inside the "
            "window `GET /v1/projects/{key}/backups` serves; otherwise as a branch's creation. "
            "The project itself is never overwritten."
        ),
        request_model=CreateRestoreRequest,
    ),
    responses={202: ACCEPTED, 400: openapi_docs.MALFORMED, 401: openapi_docs.UNAUTHENTICATED,
               403: FACTOR_GATE, 404: NOT_YOURS, 409: BRANCH_LIMIT, 422: openapi_docs.INVALID},
)  # fmt: skip
async def create_restore(request: Request, key: str) -> Response:
    async def run() -> Response:
        caller = await _offered(request)
        payload = await _body(request, CreateRestoreRequest)
        assert isinstance(payload, CreateRestoreRequest)
        return _accepted(await _service(request).create_restore(caller, key, _arguments(payload)))

    return await _guard(run)


@router.get(
    "/projects/{key}/branches/{branch}",
    openapi_extra=openapi_docs.described(
        summary="One branch of a project",
        description="Viewer and above, or a key holding `projects:read`. A missing branch, a "
                    "foreign project's and a missing project's are one `not_found`.",
    ),
    responses={200: openapi_docs.ok("The branch."), 401: openapi_docs.UNAUTHENTICATED,
               403: FACTOR_GATE, 404: NOT_YOURS},
)  # fmt: skip
async def get_branch(request: Request, key: str, branch: str) -> Response:
    async def run() -> Response:
        caller = await _caller(request)
        return JSONResponse(await _service(request).get_branch(caller, key, branch))

    return await _guard(run)


@router.post(
    "/projects/{key}/branches/{branch}/reset",
    status_code=202,
    openapi_extra=openapi_docs.described(
        summary="Restore a branch again",
        description=(
            "Member and above, a person only. The branch is restored again -- to `target_time`, "
            "or to the end of the archive -- with the two new credentials; its names stay. "
            "Everything written to the branch since is lost."
        ),
        request_model=ResetBranchRequest,
    ),
    responses={202: ACCEPTED, 400: openapi_docs.MALFORMED, 401: openapi_docs.UNAUTHENTICATED,
               403: FACTOR_GATE, 404: NOT_YOURS, 409: NOT_OFFERED, 422: openapi_docs.INVALID},
)  # fmt: skip
async def reset_branch(request: Request, key: str, branch: str) -> Response:
    async def run() -> Response:
        caller = await _offered(request)
        payload = await _body(request, ResetBranchRequest)
        assert isinstance(payload, ResetBranchRequest)
        operation = await _service(request).reset_branch(caller, key, branch, _arguments(payload))
        return _accepted(operation)

    return await _guard(run)


@router.delete(
    "/projects/{key}/branches/{branch}",
    status_code=202,
    openapi_extra=openapi_docs.described(
        summary="Delete a branch",
        description=(
            "Admin and above, a person only. The branch's containers, volume and names are "
            "removed; the project is untouched. A branch is not backed up: what it held is gone."
        ),
    ),
    responses={202: ACCEPTED, 401: openapi_docs.UNAUTHENTICATED, 403: FACTOR_GATE,
               404: NOT_YOURS, 409: NOT_OFFERED},
)  # fmt: skip
async def delete_branch(request: Request, key: str, branch: str) -> Response:
    async def run() -> Response:
        caller = await _offered(request)
        return _accepted(await _service(request).delete_branch(caller, key, branch))

    return await _guard(run)


@router.get(
    "/projects/{key}/backups",
    openapi_extra=openapi_docs.described(
        summary="A project's backups and its restore window",
        description=(
            "Viewer and above, or a key holding `projects:read`. The newest reading the server "
            "recorded, with its age: `window` (`earliest` ... `latest`), `sleeping`, or "
            "`could_not_determine` with the reason -- a reading never recorded, older than 30 "
            "minutes, or one whose repository, archiver or mirror could not be read is never "
            "served as a window."
        ),
    ),
    responses={200: openapi_docs.ok("The reading."), 401: openapi_docs.UNAUTHENTICATED,
               403: FACTOR_GATE, 404: NOT_YOURS},
)  # fmt: skip
async def get_backups(request: Request, key: str) -> Response:
    async def run() -> Response:
        caller = await _caller(request)
        return JSONResponse(await _service(request).backups(caller, key))

    return await _guard(run)


@router.get(
    "/projects/{key}",
    openapi_extra=openapi_docs.described(
        summary="One project of the caller's organisations",
        description="A foreign project and a missing one are one `not_found`.",
    ),
    responses={200: openapi_docs.ok("The project's registry record."),
               401: openapi_docs.UNAUTHENTICATED, 403: FACTOR_GATE, 404: NOT_A_MEMBER},
)  # fmt: skip
async def get_project(request: Request, key: str) -> Response:
    async def run() -> Response:
        caller = await _caller(request)
        return JSONResponse(await _service(request).get_project(caller, key))

    return await _guard(run)


@router.get(
    "/operations",
    openapi_extra=openapi_docs.described(
        summary="An organisation's operations, newest first",
        description="`organization` is required. Empty while no operation type is accepted.",
        query_parameters=[{**ORGANIZATION_QUERY, "required": True}],
    ),
    responses={200: openapi_docs.ok("The operations."), 401: openapi_docs.UNAUTHENTICATED,
               403: FACTOR_GATE, 404: NOT_A_MEMBER, 422: openapi_docs.INVALID},
)  # fmt: skip
async def list_operations(request: Request) -> Response:
    async def run() -> Response:
        caller = await _caller(request)
        named = _query(request, ("organization",)).get("organization")
        if named is None:
            raise errors.InvalidRequest("organization is required")
        rows = await _service(request).list_operations(caller, _uuid(named))
        return JSONResponse({"operations": rows})

    return await _guard(run)


@router.get(
    "/operations/{operation}",
    openapi_extra=openapi_docs.described(
        summary="One operation of the caller's organisations",
        description="A foreign operation and a missing one are one `not_found`.",
    ),
    responses={200: openapi_docs.ok("The operation."), 401: openapi_docs.UNAUTHENTICATED,
               403: FACTOR_GATE, 404: NOT_A_MEMBER},
)  # fmt: skip
async def get_operation(request: Request, operation: str) -> Response:
    async def run() -> Response:
        caller = await _caller(request)
        return JSONResponse(await _service(request).get_operation(caller, _uuid(operation)))

    return await _guard(run)


@router.post(
    "/operations/{operation}/cancel",
    openapi_extra=openapi_docs.described(
        summary="Cancel a pending operation",
        description=(
            "The person who requested it, or an admin or owner of its organisation. Only a "
            "`pending` operation is cancelled; one already running or finished is `conflict`."
        ),
    ),
    responses={200: openapi_docs.ok("The operation, `cancelled`."),
               401: openapi_docs.UNAUTHENTICATED, 403: FACTOR_GATE, 404: NOT_A_MEMBER,
               409: {"model": ConflictResponse, "description": "`conflict`: not pending."}},
)  # fmt: skip
async def cancel_operation(request: Request, operation: str) -> Response:
    async def run() -> Response:
        caller = await _caller(request)
        cancelled = await _service(request).cancel_operation(caller, _uuid(operation))
        return JSONResponse({"operation": cancelled})

    return await _guard(run)


# ---------------------------------------------------------------------------
# Session 41: plans, usage, notifications and idle sleep (ADR 0274-0276)
# ---------------------------------------------------------------------------

HOURS_QUERY = openapi_docs.query_parameter(
    "hours",
    schema={"type": "integer", "minimum": 1, "maximum": 720, "default": 24},
    description="The window, in hours back from now: 1 to 720 (default 24).",
)
LIMIT_QUERY = openapi_docs.query_parameter(
    "limit",
    schema={"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
    description="How many, newest first: 1 to 200 (default 50).",
)


def _bounded(request: Request, name: str, *, default: int, maximum: int) -> int:
    """One bounded integer from the query string, or its default; nothing else
    may be named (`strict_query`)."""
    named = _query(request, (name,)).get(name)
    if named is None:
        return default
    try:
        return strict_query.as_bounded_int(name, named, minimum=1, maximum=maximum)
    except strict_query.InvalidQuery as exc:
        raise errors.InvalidRequest(str(exc)) from exc


@router.get(
    "/plans",
    openapi_extra=openapi_docs.described(
        summary="The plans and their entitlements",
        description=(
            "Any account, or a key holding `organizations:read`. Free is every organisation's "
            "plan during the beta; Premium is defined and `unavailable_during_beta`. Each "
            "entitlement says whether it is enforced and by which reader: `projects_active`, "
            "`branches_total` and `compute_profiles` by this plane before anything is "
            "recorded; `storage_gb` and `agent_calls_per_day` are shown against usage and not "
            "enforced during the beta."
        ),
    ),
    responses={200: openapi_docs.ok("Both plans."), 401: openapi_docs.UNAUTHENTICATED,
               403: FACTOR_GATE},
)  # fmt: skip
async def list_plans(request: Request) -> Response:
    async def run() -> Response:
        caller = await _caller(request)
        return JSONResponse(await _service(request).list_plans(caller))

    return await _guard(run)


@router.get(
    "/organizations/{organization}/plan",
    openapi_extra=openapi_docs.described(
        summary="An organisation's plan and what it holds of it",
        description=(
            "Any member, or a key holding `organizations:read`: the plan, its entitlements, "
            "the projects held against `projects_active` (a sleeping project holds its slot), "
            "and the plans the organisation asked to be told about."
        ),
    ),
    responses={200: openapi_docs.ok("The plan."), 401: openapi_docs.UNAUTHENTICATED,
               403: FACTOR_GATE, 404: NOT_A_MEMBER},
)  # fmt: skip
async def get_organization_plan(request: Request, organization: str) -> Response:
    async def run() -> Response:
        caller, org = await _member(request, organization)
        return JSONResponse(await _service(request).organization_plan(caller, org))

    return await _guard(run)


@router.post(
    "/organizations/{organization}/plan-interest",
    openapi_extra=openapi_docs.described(
        summary="Notify me: record that the organisation wants a plan not yet available",
        description=(
            "Member and above, a person only. One record per organisation and plan; asking "
            "again changes nothing. Nothing is charged, and nothing moves the organisation onto "
            "the plan."
        ),
        request_model=PlanInterestRequest,
    ),
    responses={200: openapi_docs.ok("Whether this request recorded it."),
               400: openapi_docs.MALFORMED, 401: openapi_docs.UNAUTHENTICATED,
               403: FACTOR_GATE, 404: NOT_A_MEMBER},
)  # fmt: skip
async def register_plan_interest(request: Request, organization: str) -> Response:
    async def run() -> Response:
        caller, org = await _member(request, organization)
        payload = await _body(request, PlanInterestRequest)
        assert isinstance(payload, PlanInterestRequest)
        return JSONResponse(await _service(request).register_interest(caller, org, payload.plan))

    return await _guard(run)


@router.get(
    "/organizations/{organization}/usage",
    openapi_extra=openapi_docs.described(
        summary="An organisation's usage, per project",
        description=(
            "Any member, or a key holding `projects:read`. Each project's document is the "
            "project route's; a deleted project is listed for the part of the window it lived."
        ),
        query_parameters=[HOURS_QUERY],
    ),
    responses={200: openapi_docs.ok("The usage."), 401: openapi_docs.UNAUTHENTICATED,
               403: FACTOR_GATE, 404: NOT_A_MEMBER, 422: openapi_docs.INVALID},
)  # fmt: skip
async def get_organization_usage(request: Request, organization: str) -> Response:
    async def run() -> Response:
        caller, org = await _member(request, organization)
        hours = _bounded(request, "hours", default=24, maximum=720)
        return JSONResponse(await _service(request).organization_usage(caller, org, hours))

    return await _guard(run)


@router.get(
    "/organizations/{organization}/notifications",
    openapi_extra=openapi_docs.described(
        summary="An organisation's notifications, newest first",
        description=(
            "Any member, or a key holding `organizations:read`. One per finished operation -- "
            "its type, its project, how it ended and why it was requested -- and the daily "
            "notice of a shown limit passed at 80%. In-app only; no read state."
        ),
        query_parameters=[LIMIT_QUERY],
    ),
    responses={200: openapi_docs.ok("The notifications."), 401: openapi_docs.UNAUTHENTICATED,
               403: FACTOR_GATE, 404: NOT_A_MEMBER, 422: openapi_docs.INVALID},
)  # fmt: skip
async def list_notifications(request: Request, organization: str) -> Response:
    async def run() -> Response:
        caller, org = await _member(request, organization)
        limit = _bounded(request, "limit", default=50, maximum=200)
        return JSONResponse(await _service(request).notifications(caller, org, limit))

    return await _guard(run)


@router.get(
    "/projects/{key}/usage",
    openapi_extra=openapi_docs.described(
        summary="A project's usage over a window",
        description=(
            "Viewer and above, or a key holding `projects:read`. Computed from the samples "
            "the server recorded every five minutes: how many it expected and found, each "
            "figure's newest reading, the requests counted across resets, agent calls and "
            "workflow runs, active and sleeping seconds from the project's history. A figure "
            "not read is null and counted, never zero; a window with no sample is "
            "`could_not_determine`."
        ),
        query_parameters=[HOURS_QUERY],
    ),
    responses={200: openapi_docs.ok("The usage."), 401: openapi_docs.UNAUTHENTICATED,
               403: FACTOR_GATE, 404: NOT_YOURS, 422: openapi_docs.INVALID},
)  # fmt: skip
async def get_project_usage(request: Request, key: str) -> Response:
    async def run() -> Response:
        caller = await _caller(request)
        hours = _bounded(request, "hours", default=24, maximum=720)
        return JSONResponse(await _service(request).project_usage(caller, key, hours))

    return await _guard(run)


#: Session 42 (ADR 0278): the insights window and how many statements.
INSIGHT_HOURS_QUERY = openapi_docs.query_parameter(
    "hours",
    schema={"type": "integer", "minimum": 1, "maximum": 168, "default": 24},
    description="The window, in hours back from now: 1 to 168 (default 24).",
)
INSIGHT_LIMIT_QUERY = openapi_docs.query_parameter(
    "limit",
    schema={"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
    description="How many statements, the most time first: 1 to 50 (default 20).",
)


def _insight_bounds(request: Request) -> tuple[int, int]:
    """`hours` 1..168 (default 24) and `limit` 1..50 (default 20); nothing else
    may be named."""
    named = _query(request, ("hours", "limit"))
    try:
        hours = (
            strict_query.as_bounded_int("hours", named["hours"], minimum=1, maximum=168)
            if "hours" in named
            else 24
        )
        limit = (
            strict_query.as_bounded_int("limit", named["limit"], minimum=1, maximum=50)
            if "limit" in named
            else 20
        )
    except strict_query.InvalidQuery as exc:
        raise errors.InvalidRequest(str(exc)) from exc
    return hours, limit


@router.get(
    "/projects/{key}/insights",
    openapi_extra=openapi_docs.described(
        summary="A project's statements over a window",
        description=(
            "Viewer and above, or a key holding `projects:read`. Sampled every five minutes "
            "from the statements your database roles and the API's request roles ran, the "
            "text normalised by PostgreSQL (no literal is kept): per statement the calls, "
            "total and mean time, rows, rows per call, shared blocks read per call and the "
            "cache hit ratio over the window, each counted across resets, the most time "
            "first. Numbers only: nothing here tells you what to change. To change a query "
            "plan, write a migration in your project's set and run `apg migrate propose`. "
            "Fewer than two samples in the window is `could_not_determine` with the reason."
        ),
        query_parameters=[INSIGHT_HOURS_QUERY, INSIGHT_LIMIT_QUERY],
    ),
    responses={200: openapi_docs.ok("The statements."), 401: openapi_docs.UNAUTHENTICATED,
               403: FACTOR_GATE, 404: NOT_YOURS, 422: openapi_docs.INVALID},
)  # fmt: skip
async def get_project_insights(request: Request, key: str) -> Response:
    async def run() -> Response:
        caller = await _caller(request)
        hours, limit = _insight_bounds(request)
        return JSONResponse(await _service(request).project_insights(caller, key, hours, limit))

    return await _guard(run)


@router.get(
    "/projects/{key}/monitoring",
    openapi_extra=openapi_docs.described(
        summary="A project's monitoring signals",
        description=(
            "Viewer and above, or a key holding `projects:read`. A short list of readings, "
            "each naming where it comes from -- the newest usage sample, the last hour's "
            "usage, the last backups reading, the newest insight sample -- with when it was "
            "read, or `unread` with the reason. No threshold and no alert: the reading and "
            "its age."
        ),
    ),
    responses={200: openapi_docs.ok("The signals."), 401: openapi_docs.UNAUTHENTICATED,
               403: FACTOR_GATE, 404: NOT_YOURS, 422: openapi_docs.INVALID},
)  # fmt: skip
async def get_project_monitoring(request: Request, key: str) -> Response:
    async def run() -> Response:
        caller = await _caller(request)
        _query(request, ())
        return JSONResponse(await _service(request).project_monitoring(caller, key))

    return await _guard(run)


@router.put(
    "/projects/{key}/idle-sleep",
    openapi_extra=openapi_docs.described(
        summary="Put a project to sleep after it has been idle",
        description=(
            "Member and above, or a key holding `projects:write`. `minutes` 15, 30 or 60, or "
            "null for never (the default). Idle is no request answered below 400 and no "
            "connection by the project's own database roles for the whole window, read from "
            "the samples; a sample missing or unread keeps the project awake. While it "
            "sleeps, its backups stop: its last restore point is the moment it went to sleep. "
            "Wake it by request. Refused `not_available` naming `idle_sleep` while the sleep "
            "it would request is not offered."
        ),
        request_model=IdleSleepRequest,
    ),
    responses={200: openapi_docs.ok("The setting, and what sleeping does to backups."),
               400: openapi_docs.MALFORMED, 401: openapi_docs.UNAUTHENTICATED,
               403: FACTOR_GATE, 404: NOT_YOURS, 409: NOT_OFFERED},
)  # fmt: skip
async def set_idle_sleep(request: Request, key: str) -> Response:
    async def run() -> Response:
        caller = await _caller(request)
        ControlService.require_idle_sleep_offered()
        payload = await _body(request, IdleSleepRequest)
        assert isinstance(payload, IdleSleepRequest)
        return JSONResponse(await _service(request).set_idle_sleep(caller, key, payload.minutes))

    return await _guard(run)
