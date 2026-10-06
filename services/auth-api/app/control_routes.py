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

Run 5 adds the keys, projects and operations routes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app import control_roles, errors, openapi_docs
from app.control_service import ControlPrincipal, ControlService
from app.models import (
    AcceptInvitationRequest,
    ConfirmFactorRequest,
    ControlLoginRequest,
    ControlRefusedResponse,
    CreateOrganizationRequest,
    FactorEnrolmentResponse,
    InvitationResponse,
    LogoutRequest,
    MintInvitationRequest,
    RefreshRequest,
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


def _refused(description: str) -> dict[str, Any]:
    return {"model": ControlRefusedResponse, "description": description}


NOT_A_MEMBER = _refused(
    "`not_found`: the organisation does not exist, or the caller is not a member of it -- "
    "one answer for both, so an id says nothing about whether it exists."
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


async def _caller(request: Request) -> ControlPrincipal:
    """The bearer, verified, with the factor gate applied for this route."""
    return await _service(request).authenticate(
        request.headers.get("authorization"), _route(request)
    )


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


def _tokens(issued: Any, refresh: str) -> JSONResponse:
    return JSONResponse(
        {
            "access_token": issued.token,
            "token_type": "Bearer",
            "expires_at": issued.expires_at,
            "token_use": issued.token_use,
            "refresh_token": refresh,
        }
    )


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
            "without one, `second_factor_invalid` with a wrong one or one already used."
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
        payload = await _body(request, ControlLoginRequest)
        assert isinstance(payload, ControlLoginRequest)
        issued, refresh = await _service(request).login(
            payload.username, payload.password, payload.totp_code
        )
        return _tokens(issued, refresh)

    return await _guard(run)


@router.post(
    "/sessions/refresh",
    openapi_extra=openapi_docs.described(
        summary="Exchange a refresh token for an access token and its successor",
        description=(
            "Single use, and every refusal answers identically -- the release's session "
            "plane, unchanged. Confirming a second factor ends every session opened before it."
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
        payload = await _body(request, RefreshRequest)
        assert isinstance(payload, RefreshRequest)
        issued, successor = await _service(request).refresh(payload.refresh_token)
        return _tokens(issued, successor)

    return await _guard(run)


@router.delete(
    "/sessions/current",
    status_code=204,
    openapi_extra=openapi_docs.described(
        summary="Log out: end the session a refresh token names",
        description=(
            "Takes the refresh token, not an access token: the command-line client keeps only "
            "the refresh token. Answers 204 whether or not the token named a live session."
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
        payload = await _body(request, LogoutRequest)
        assert isinstance(payload, LogoutRequest)
        await _service(request).logout(payload.refresh_token)
        return Response(status_code=204)

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
            "`expires_in_hours` (1-168) says otherwise."
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
        return JSONResponse(minted, status_code=201)

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
        caller = await _caller(request) if request.headers.get("authorization") else None
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
