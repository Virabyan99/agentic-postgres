"""The management API's behaviour (Session 37, ADR 0251-0253).

**Built on `AuthService`, never beside it.** The control mode is the control
project's own `auth` process: the same issuer, the same key, the same pool and
the same identity registry. A control account IS a registry user (role
`api_documentation`, scopes `["meta:read"]`, D2049/D2078) -- so a login here is
`AuthService.login` with one hook, a refresh is `AuthService.refresh`, and
every bearer is verified by `AuthService.authenticate`, current-state
comparison included. What this module adds is what the release does not have:
the second factor, organisations and their roles, and invitations.

**The second factor** (D2050, ADR 0252): checked inside `login` after the
password and the status, before anything is issued. Who must hold one is
`control_roles.factor_required`; such a person without one reaches only
`control_roles.ENROLMENT_ROUTES` (`factor_gate`). Confirming a factor ends
every session the person had (D2080).

**Organisations**: every role check is `control_roles.MATRIX`, read by the
routes' one guard through `require_role`; the definer functions check again.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app import control_roles, errors, one_time_tokens, refresh_sessions, totp
from app import scopes as scope_map
from app.control_repository import ControlRepository
from app.hashing import normalize
from app.service import AuthService, IssuedToken, Principal

#: The role and scopes every control account is created with (D2049, D2078):
#: the narrowest authority the identity registry can describe, reading no row
#: of the control project's own data plane.
ACCOUNT_ROLE_SUFFIX = "api_documentation"
ACCOUNT_SCOPES = [scope_map.INTROSPECTION_SCOPE]

#: An invitation's lifetime, in hours (D2051). The table CHECKs the maximum too.
INVITATION_DEFAULT_HOURS = 72
INVITATION_MAX_HOURS = 168


@dataclass(frozen=True, slots=True)
class ControlPrincipal:
    """A person whose access token verified, with what the control plane knows
    about them read inside this request: their organisations and their factor."""

    principal: Principal
    roles: dict[str, str]
    factor_enabled: bool

    @property
    def user_id(self) -> UUID:
        return self.principal.user_id

    @property
    def must_enrol(self) -> bool:
        return (
            control_roles.factor_required(self.roles, self.principal.scopes)
            and not self.factor_enabled
        )


def invitation_deadline(hours: int | None) -> datetime:
    """When an invitation minted now stops being accepted. Out of bounds is a
    refusal, never a clamp -- `agent_secret_deadline`'s rule."""
    chosen = INVITATION_DEFAULT_HOURS if hours is None else hours
    if not 1 <= chosen <= INVITATION_MAX_HOURS:
        raise errors.InvalidRequest(
            f"expires_in_hours must be between 1 and {INVITATION_MAX_HOURS}"
        )
    return datetime.now(UTC) + timedelta(hours=chosen)


class ControlService:
    """Everything the control routes call."""

    def __init__(self, *, auth: AuthService, repository: ControlRepository) -> None:
        self.auth = auth
        self.repository = repository

    # -- the session plane ----------------------------------------------------

    async def login(
        self, username: str, password: str, code: str | None
    ) -> tuple[IssuedToken, str]:
        """`AuthService.login`, with the second factor as its hook.

        The hook runs only once the password and the status have passed, so a
        refused code costs what a refused password costs and reveals only what
        D2050 accepts it reveals: that the password was right. On success the
        person's display row is written (`control_record_account`).
        """

        async def second_factor(user: UUID) -> None:
            factor = await self.repository.totp_seed(user)
            if factor is not None and factor["enabled"]:
                if code is None:
                    raise errors.ControlRefused(errors.SECOND_FACTOR_REQUIRED, status=401)
                step = totp.verify(
                    bytes(factor["seed"]), code, int(time.time()), factor["last_step"]
                )
                if step is None or not await self.repository.totp_accept_step(user, step):
                    raise errors.ControlRefused(errors.SECOND_FACTOR_INVALID)
            state = await self.auth.repository.state(user)
            if state is None:
                raise errors.AuthenticationFailed("the subject vanished during login")
            await self.repository.record_account(user, state.username, state.display_name)

        return await self.auth.login(username, password, second_factor=second_factor)

    async def refresh(self, presented: str) -> tuple[IssuedToken, str]:
        return await self.auth.refresh(presented)

    async def logout(self, presented: str) -> None:
        """End the session a refresh token names. Answers nothing either way.

        The CLI holds a refresh token and never an access token (D2066), so
        the session is found from the refresh token alone: presenting it is
        the proof, and the family it names is then revoked. Presenting it
        consumes it -- the successor minted by that exchange is discarded with
        its family -- and presenting a token that was already consumed ends
        the family inside the exchange (reuse detection), which is the outcome
        a logout wanted anyway.
        """
        if not refresh_sessions.is_wellformed(presented):
            raise errors.MalformedRequest("malformed refresh token")
        _, digest = refresh_sessions.mint()
        expires_at = datetime.now(UTC) + timedelta(seconds=refresh_sessions.REFRESH_TTL_SECONDS)
        attempt = await self.auth.repository.consume_refresh_token(
            refresh_sessions.hash_token(presented), digest, expires_at
        )
        if attempt.family_id is not None and attempt.user_id is not None:
            await self.auth.repository.revoke_session(
                attempt.user_id,
                attempt.family_id,
                refresh_sessions.RevocationReason.LOGGED_OUT.value,
            )

    # -- who is asking ----------------------------------------------------------

    async def authenticate(self, authorization: str | None, route: str) -> ControlPrincipal:
        """Verify the bearer, read the person's organisations and factor, and
        apply the factor gate for `route`."""
        principal = await self.auth.authenticate(authorization)
        roles = await self.repository.caller_roles(principal.user_id)
        factor = await self.repository.totp_seed(principal.user_id)
        caller = ControlPrincipal(
            principal=principal,
            roles=roles,
            factor_enabled=bool(factor and factor["enabled"]),
        )
        self.factor_gate(caller, route)
        return caller

    @staticmethod
    def factor_gate(caller: ControlPrincipal, route: str) -> None:
        """403 `second_factor_required` outside enrolment for a person who must
        hold a factor and has none (D2050)."""
        if caller.must_enrol and route not in control_roles.ENROLMENT_ROUTES:
            raise errors.ControlRefused(errors.SECOND_FACTOR_REQUIRED)

    @staticmethod
    def require_role(caller: ControlPrincipal, organization: UUID, minimum: str) -> str:
        """The caller's role in `organization`, if at least `minimum`.

        A non-member gets `not_found` -- the answer a missing organisation gets
        -- so an organisation id says nothing about whether it exists (D2053).
        """
        role = caller.roles.get(str(organization))
        if role is None:
            raise errors.ControlRefused(errors.NOT_FOUND)
        if control_roles.rank(role) < control_roles.rank(minimum):
            raise errors.AuthorizationFailed(f"{minimum} in the organisation")
        return role

    async def me(self, caller: ControlPrincipal) -> dict[str, Any]:
        state = caller.principal.state
        return {
            "user_id": str(caller.user_id),
            "username": state.username,
            "display_name": state.display_name,
            "second_factor": {
                "enabled": caller.factor_enabled,
                "required": control_roles.factor_required(caller.roles, caller.principal.scopes),
            },
            "organizations": [
                {"id": org, "role": role} for org, role in sorted(caller.roles.items())
            ],
        }

    # -- the second factor ------------------------------------------------------

    async def begin_factor(self, caller: ControlPrincipal) -> dict[str, str]:
        """A new seed, stored unconfirmed, returned ONCE as base32 and a URI."""
        seed = totp.new_seed()
        await self.repository.totp_begin(caller.user_id, seed)
        return {
            "secret": base64.b32encode(seed).decode("ascii").rstrip("="),
            "otpauth_uri": totp.provisioning_uri(caller.principal.state.username, seed),
        }

    async def confirm_factor(self, caller: ControlPrincipal, code: str) -> int:
        """Enable the factor with a current code; end every session (D2080).

        Returns how many sessions ended. The token used to confirm stays valid
        until it expires (at most 930 s): only the refresh families end here,
        because the two granted functions that would move `authz_version` --
        `auth_set_status` and `auth_set_authorization` -- would also overwrite
        an administrator's concurrent change (D2101).
        """
        factor = await self.repository.totp_seed(caller.user_id)
        if factor is not None and factor["enabled"]:
            raise errors.ControlRefused(errors.FACTOR_ENABLED)
        step = (
            totp.verify(bytes(factor["seed"]), code, int(time.time()), factor["last_step"])
            if factor is not None
            else None
        )
        ended = (
            await self.repository.confirm_factor(
                caller.user_id, step, refresh_sessions.RevocationReason.CREDENTIAL_CHANGED.value
            )
            if step is not None
            else None
        )
        if ended is None:
            raise errors.ControlRefused(errors.SECOND_FACTOR_INVALID, status=422)
        return ended

    # -- invitations --------------------------------------------------------------

    async def mint_invitation(
        self,
        caller: ControlPrincipal,
        *,
        organization: UUID | None,
        role: str | None,
        expires_in_hours: int | None,
    ) -> dict[str, Any]:
        """Mint an invitation; the token is returned here and never again.

        A membership invitation (an organisation and a role) needs `admin` in
        that organisation and a role the minter may grant; an account
        invitation (neither) needs the registry administrator's scope -- and,
        through the factor gate, an enabled factor (D2051, D2099).
        """
        if (organization is None) != (role is None):
            raise errors.InvalidRequest("organization_id and role are given together or not at all")
        if organization is None:
            AuthService.require_scope(caller.principal, control_roles.ACCOUNT_INVITATION_SCOPE)
        else:
            assert role is not None
            mine = self.require_role(caller, organization, control_roles.MEMBERSHIP_INVITATION)
            if not control_roles.may_grant(mine, role):
                raise errors.AuthorizationFailed("owner in the organisation")
        expires_at = invitation_deadline(expires_in_hours)
        token, digest = one_time_tokens.mint()
        invitation = await self.repository.mint_invitation(
            caller.user_id, organization, role, digest, expires_at
        )
        return {
            "id": str(invitation),
            "invitation_token": token,
            "organization_id": None if organization is None else str(organization),
            "role": role,
            "expires_at": expires_at.isoformat(),
        }

    async def accept_invitation(
        self,
        presented: str,
        *,
        caller: ControlPrincipal | None,
        username: str | None,
        display_name: str | None,
        password: str | None,
    ) -> dict[str, Any]:
        """Spend an invitation: as the signed-in caller, or creating an account.

        Every token that cannot be spent -- used, expired, revoked, unknown, or
        not even well formed -- is ONE answer, `invitation_invalid` (D2051).
        The password is screened BEFORE the token is spent, so a weak one never
        costs the invitation; a taken username is answered only after the token
        validated, and leaves it unspent.
        """
        if not one_time_tokens.is_wellformed(presented):
            raise errors.ControlRefused(errors.INVITATION_INVALID)
        digest = one_time_tokens.hash_token(presented)
        if caller is not None:
            if username is not None or display_name is not None or password is not None:
                raise errors.InvalidRequest("a signed-in caller accepts with the token alone")
            state = caller.principal.state
            accepted = await self.repository.accept_as_existing(
                digest, caller.user_id, state.username, state.display_name
            )
        else:
            if username is None or display_name is None or password is None:
                raise errors.InvalidRequest(
                    "username, display_name and password are required to create the account"
                )
            role_name = self.auth._role_name(ACCOUNT_ROLE_SUFFIX)
            scopes = self.auth._check_scopes(ACCOUNT_ROLE_SUFFIX, ACCOUNT_SCOPES)
            hashed = await self.auth._hash(password, forbidden=(username, display_name))
            accepted = await self.repository.accept_as_new(
                digest,
                username=normalize(username),
                display_name=normalize(display_name),
                role_name=role_name,
                scopes=scopes,
                password_hash=hashed,
            )
        org = accepted["organization_id"]
        return {
            "user_id": str(accepted["user_id"]),
            "organization_id": None if org is None else str(org),
            "role": None if accepted["role"] is None else str(accepted["role"]),
        }

    async def list_invitations(self, caller: ControlPrincipal, organization: UUID) -> list[Any]:
        rows = await self.repository.list_invitations(caller.user_id, organization)
        return [
            {
                "id": str(row["id"]),
                "role": str(row["role"]),
                "issued_by": str(row["issued_by"]),
                "issued_at": row["issued_at"].isoformat(),
                "expires_at": row["expires_at"].isoformat(),
                "accepted_at": _iso(row["accepted_at"]),
                "revoked_at": _iso(row["revoked_at"]),
            }
            for row in rows
        ]

    async def revoke_invitation(
        self, caller: ControlPrincipal, organization: UUID, invitation: UUID
    ) -> None:
        await self.repository.revoke_invitation(caller.user_id, organization, invitation)

    # -- organisations and members ------------------------------------------------

    async def create_organization(self, caller: ControlPrincipal, name: str) -> dict[str, Any]:
        org = await self.repository.create_organization(caller.user_id, name)
        return {"id": str(org), "name": name, "role": "owner"}

    async def list_organizations(self, caller: ControlPrincipal) -> list[dict[str, Any]]:
        return [
            _organization(row) for row in await self.repository.list_organizations(caller.user_id)
        ]

    async def get_organization(self, caller: ControlPrincipal, org: UUID) -> dict[str, Any]:
        row = await self.repository.get_organization(caller.user_id, org)
        if row is None:
            raise errors.ControlRefused(errors.NOT_FOUND)
        return _organization(row)

    async def list_members(self, caller: ControlPrincipal, org: UUID) -> list[dict[str, Any]]:
        return [
            {
                "user_id": str(row["user_id"]),
                "username": row["username"],
                "display_name": row["display_name"],
                "role": str(row["role"]),
                "created_at": row["created_at"].isoformat(),
            }
            for row in await self.repository.list_members(caller.user_id, org)
        ]

    async def set_member_role(
        self, caller: ControlPrincipal, org: UUID, target: UUID, role: str
    ) -> None:
        mine = caller.roles[str(org)]
        if not control_roles.may_grant(mine, role):
            raise errors.AuthorizationFailed("owner in the organisation")
        await self.repository.set_member_role(caller.user_id, org, target, role)

    async def remove_member(self, caller: ControlPrincipal, org: UUID, target: UUID) -> None:
        await self.repository.remove_member(caller.user_id, org, target)


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _organization(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "role": str(row["role"]),
        "created_at": row["created_at"].isoformat(),
    }
