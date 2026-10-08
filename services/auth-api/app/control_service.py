"""The management API's behaviour (Session 37, ADR 0251-0254).

**Built on `AuthService`, never beside it.** The control mode is the control
project's own `auth` process: the same issuer, the same key, the same pool and
the same identity registry. A control account IS a registry user (role
`api_documentation`, scopes `["meta:read"]`, D2049/D2078) -- so a login here is
`AuthService.login` with one hook, a refresh is `AuthService.refresh`, and
every access token is verified by `AuthService.authenticate`, current-state
comparison included. What this module adds is what the release does not have:
the second factor, organisations and their roles, invitations, and keys.

**The second factor** (D2050, ADR 0252): checked inside `login` after the
password and the status, before anything is issued. Who must hold one is
`control_roles.factor_required`; such a person without one reaches only
`control_roles.ENROLMENT_ROUTES` (`factor_gate`). Confirming a factor ends
every session the person had (D2080).

**Keys** (D2052, ADR 0253): a bearer of the form `apg_<16 hex>_<43>` is a
management key, not an access token. It is found by its id, its secret
compared as a SHA-256 with `hmac.compare_digest` -- never Argon2id, which
would cost 64 MiB and ~230 ms per request (rig 37c) -- and it is refused, with
the one `authentication_failed`, when unknown, wrong, revoked, or held by
someone who has left the organisation. Its authority is computed on every
request: its scopes intersected with its owner's CURRENT role, inside its own
organisation only. A key reaches only `control_roles.KEY_SCOPES`' routes;
everything else -- every route that mints a credential -- is
`human_session_required`, so a leaked key cannot mint its successor.

**Organisations**: every role check is `control_roles.MATRIX`, read by the
routes' one guard through `require_role`; the definer functions check again.
Every list the database returns is filtered to the caller's organisations as
this request computed them -- for a key, its one organisation -- so a key held
by a member of two organisations sees only the one it was minted in.

**Operations** (Session 38, ADR 0256): a write is refused `not_available`
while its type is not accepted (ADR 0254) -- before its body is read; then the
body, the role (`control_roles.PROJECT_WRITES`, checked again in SQL), for a
creation the slot reading (`capacity_exhausted {reason: no_slot}` BEFORE any
row, D2160), and only then the row: `202` with the operation, or `409
conflict` naming the operation already holding the project or the
organisation's creation (D2166). A project's `state` is derived from its
operation history alone (`control_states`, D2159). An export's download URL is
handed to the person who requested it, once, by `GET /v1/operations/{id}`, and
erased in the same statement (D2164); a key never receives it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app import (
    compute_profiles,
    control_roles,
    control_states,
    errors,
    one_time_tokens,
    operations,
    refresh_sessions,
    totp,
)
from app import scopes as scope_map
from app.control_repository import ControlRepository
from app.hashing import normalize
from app.repository import SubjectState
from app.service import AuthService, IssuedToken

#: The role and scopes every control account is created with (D2049, D2078):
#: the narrowest authority the identity registry can describe, reading no row
#: of the control project's own data plane.
ACCOUNT_ROLE_SUFFIX = "api_documentation"
ACCOUNT_SCOPES = [scope_map.INTROSPECTION_SCOPE]

#: An invitation's lifetime, in hours (D2051). The table CHECKs the maximum too.
INVITATION_DEFAULT_HOURS = 72
INVITATION_MAX_HOURS = 168

#: A management key (D2052): `apg_`, the 16-hex lookup id, `_`, and a 43-char
#: `token_urlsafe(32)` secret. A bearer starting `apg_` that does not match is
#: refused with the same `authentication_failed` as a wrong key.
KEY_PREFIX = "apg_"
KEY_PATTERN = re.compile(r"^apg_([0-9a-f]{16})_([A-Za-z0-9_-]{43})$")

#: What an unknown key id is compared against, so an unknown id does the same
#: work as a known one with a wrong secret. A constant, and not any key's.
_NO_SUCH_KEY = "0" * 64

#: A slot reading older than this is not a reading (D2160): the reconciler
#: records one at its start and after every operation, so a stale one means it
#: is not running and no creation would be executed.
SLOT_READING_MAX_AGE = timedelta(minutes=10)

#: What `capacity_exhausted {reason: no_slot}` says. Never a value the caller sent.
NO_SLOT_MESSAGE = "No slot is ready on this server. No resources were created."
STALE_SLOT_MESSAGE = (
    "This server's slots were last observed more than ten minutes ago, so none is known "
    "to be ready. No resources were created."
)


def mint_key() -> tuple[str, str, str]:
    """A new key: (the key, its id, the SHA-256 of its secret). **Shown once.**"""
    key_id = secrets.token_hex(8)
    secret = secrets.token_urlsafe(32)
    return f"{KEY_PREFIX}{key_id}_{secret}", key_id, _digest(secret)


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ControlPrincipal:
    """Who is asking, read inside this request.

    A PERSON (an access token): their registry scopes, every organisation they
    belong to, their factor, and their registry state. A KEY: its owner's id,
    its ONE organisation with the owner's current role there, its effective
    scopes, no state and no factor -- a key never needs one, because it never
    reaches a route that would (D2052).
    """

    user_id: UUID
    roles: dict[str, str]
    scopes: list[str]
    factor_enabled: bool
    state: SubjectState | None
    key_id: str | None = None

    @property
    def is_key(self) -> bool:
        return self.key_id is not None

    @property
    def must_enrol(self) -> bool:
        return (
            not self.is_key
            and control_roles.factor_required(self.roles, self.scopes)
            and not self.factor_enabled
        )

    @property
    def person(self) -> SubjectState:
        """The registry state of a PERSON. Only human-session routes read it,
        and a key never reaches one."""
        assert self.state is not None, "a key reached a human-session route"
        return self.state


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
        a logout wanted anyway (D2103).
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
        """Verify the bearer -- an access token or a key -- and apply what
        `route` requires of it: the factor gate for a person, the key scope
        and the human-session rule for a key."""
        token = authorization[len("Bearer ") :].strip() if authorization else ""
        if authorization and authorization.startswith("Bearer ") and token.startswith(KEY_PREFIX):
            return await self._authenticate_key(token, route)
        principal = await self.auth.authenticate(authorization)
        roles = await self.repository.caller_roles(principal.user_id)
        factor = await self.repository.totp_seed(principal.user_id)
        caller = ControlPrincipal(
            user_id=principal.user_id,
            roles=roles,
            scopes=principal.scopes,
            factor_enabled=bool(factor and factor["enabled"]),
            state=principal.state,
        )
        self.factor_gate(caller, route)
        return caller

    async def _authenticate_key(self, presented: str, route: str) -> ControlPrincipal:
        """A management key, checked on THIS request against the stored row and
        its owner's current membership. One refusal for every failure."""
        match = KEY_PATTERN.match(presented)
        if match is None:
            raise errors.AuthenticationFailed("malformed key")
        key_id, secret = match.groups()
        row = await self.repository.key_lookup(key_id)
        stored = row["secret_sha256"] if row is not None else _NO_SUCH_KEY
        matched = hmac.compare_digest(_digest(secret), stored)
        if row is None or not matched:
            raise errors.AuthenticationFailed("no such key, or the secret does not match")
        if row["revoked"]:
            raise errors.AuthenticationFailed("the key is revoked")
        role = None if row["member_role"] is None else str(row["member_role"])
        if role is None:
            raise errors.AuthenticationFailed("the key's owner is no longer a member")
        required = control_roles.KEY_SCOPES.get(route)
        if required is None:
            raise errors.ControlRefused(errors.HUMAN_SESSION_REQUIRED)
        effective = control_roles.effective_scopes(list(row["scopes"]), role)
        if required not in effective:
            raise errors.AuthorizationFailed(required)
        await self.repository.key_used(key_id)
        return ControlPrincipal(
            user_id=row["user_id"],
            roles={str(row["organization_id"]): role},
            scopes=sorted(effective),
            factor_enabled=False,
            state=None,
            key_id=key_id,
        )

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

    @staticmethod
    def _visible(caller: ControlPrincipal, organization: Any) -> bool:
        return str(organization) in caller.roles

    async def me(self, caller: ControlPrincipal) -> dict[str, Any]:
        state = caller.person
        return {
            "user_id": str(caller.user_id),
            "username": state.username,
            "display_name": state.display_name,
            "second_factor": {
                "enabled": caller.factor_enabled,
                "required": control_roles.factor_required(caller.roles, caller.scopes),
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
            "otpauth_uri": totp.provisioning_uri(caller.person.username, seed),
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
            if control_roles.ACCOUNT_INVITATION_SCOPE not in caller.scopes:
                raise errors.AuthorizationFailed(control_roles.ACCOUNT_INVITATION_SCOPE)
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
            state = caller.person
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
        rows = await self.repository.list_organizations(caller.user_id)
        return [_organization(row) for row in rows if self._visible(caller, row["id"])]

    async def get_organization(self, caller: ControlPrincipal, org: UUID) -> dict[str, Any]:
        row = await self.repository.get_organization(caller.user_id, org)
        if row is None or not self._visible(caller, row["id"]):
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

    # -- keys (D2052, ADR 0253) -------------------------------------------------------

    async def mint_key(
        self, caller: ControlPrincipal, org: UUID, name: str, scopes: list[str]
    ) -> dict[str, Any]:
        """A key for the caller in `org`; the key is returned here and never again.

        Its scopes must be in the Session 37 vocabulary AND within what the
        minter's role grants now -- refused, never trimmed.
        """
        requested = sorted(set(scopes))
        unknown = sorted(set(requested) - set(control_roles.KEY_VOCABULARY))
        if unknown:
            vocabulary = list(control_roles.KEY_VOCABULARY)
            raise errors.InvalidRequest(
                f"{unknown} are not key scopes; the vocabulary is {vocabulary}"
            )
        role = caller.roles[str(org)]
        beyond = sorted(set(requested) - control_roles.ROLE_SCOPES[role])
        if beyond:
            raise errors.InvalidRequest(f"a {role} may not give a key {beyond}")
        key, key_id, digest = mint_key()
        await self.repository.mint_key(caller.user_id, org, key_id, digest, name, requested)
        return {"key_id": key_id, "key": key, "name": name, "scopes": requested}

    async def list_keys(self, caller: ControlPrincipal, org: UUID) -> list[dict[str, Any]]:
        return [
            {
                "key_id": row["key_id"],
                "user_id": str(row["user_id"]),
                "name": row["name"],
                "scopes": list(row["scopes"]),
                "created_at": row["created_at"].isoformat(),
                "last_used_at": _iso(row["last_used_at"]),
                "revoked_at": _iso(row["revoked_at"]),
            }
            for row in await self.repository.list_keys(caller.user_id, org)
        ]

    async def revoke_key(self, caller: ControlPrincipal, org: UUID, key_id: str) -> None:
        """Revoke one of the caller's keys, or -- for an admin -- any of the
        organisation's. A key the caller may not revoke, a missing one and one
        already revoked are the same `not_found`."""
        if not re.fullmatch(r"[0-9a-f]{16}", key_id):
            raise errors.ControlRefused(errors.NOT_FOUND)
        if not await self.repository.revoke_key(caller.user_id, org, key_id):
            raise errors.ControlRefused(errors.NOT_FOUND)

    # -- the registry and its operations (ADR 0251, ADR 0254) --------------------------

    async def list_projects(
        self, caller: ControlPrincipal, organization: UUID | None
    ) -> list[dict[str, Any]]:
        if organization is not None:
            self.require_role(caller, organization, "viewer")
        rows = await self.repository.list_projects(caller.user_id, organization)
        history = await self.repository.project_operations(caller.user_id, None)
        return [
            _project(row, [o for o in history if o["project_key"] == row["key"]])
            for row in rows
            if self._visible(caller, row["organization_id"])
        ]

    async def get_project(self, caller: ControlPrincipal, key: str) -> dict[str, Any]:
        row = await self.repository.get_project(caller.user_id, key)
        if row is None or not self._visible(caller, row["organization_id"]):
            raise errors.ControlRefused(errors.NOT_FOUND)
        return _project(row, await self.repository.project_operations(caller.user_id, key))

    @staticmethod
    def require_accepted(route: str) -> None:
        """`not_available`, naming the ledger row, while the route's operation
        type is not accepted (ADR 0254, D2054) -- before the body is read, so
        nothing about a request to a concept that is not offered is examined.

        No row is written: a request accepted into a row nothing will ever
        execute would be a control acting on a `planned` concept, which is what
        ADR 0247's guard forbids.
        """
        operation_type = control_roles.OPERATION_OF_ROUTE[route]
        if not operations.is_accepted(operation_type):
            raise errors.ControlRefused(
                errors.NOT_AVAILABLE, ledger_row=operations.OPERATION_TYPES[operation_type]
            )

    async def create_project(
        self,
        caller: ControlPrincipal,
        *,
        organization: UUID,
        name: str,
        profile: str,
        admin_username: str,
        handoff_sha256: str,
    ) -> dict[str, Any]:
        """Request `project.create` (D2165: member and above, a person only).

        The slot reading is taken BEFORE the row: with no `ready` slot, or a
        reading older than ten minutes, the answer is `capacity_exhausted
        {reason: no_slot}` and nothing is written (D2160). The handoff token
        itself never arrives -- only its SHA-256 (ADR 0260).
        """
        self.require_role(caller, organization, control_roles.PROJECT_WRITES["create_project"])
        reading = await self.repository.ready_slots(caller.user_id)
        observed = reading["observed"]
        if observed is None or reading["ready_slots"] < 1:
            raise errors.ControlRefused(
                errors.CAPACITY_EXHAUSTED, reason="no_slot", message=NO_SLOT_MESSAGE
            )
        if datetime.now(UTC) - observed > SLOT_READING_MAX_AGE:
            raise errors.ControlRefused(
                errors.CAPACITY_EXHAUSTED, reason="no_slot", message=STALE_SLOT_MESSAGE
            )
        arguments = {
            "name": name,
            "profile": profile,
            "admin_username": admin_username,
            "handoff_sha256": handoff_sha256,
        }
        return await self._request(caller, organization, None, "project.create", arguments)

    async def write_project(
        self, caller: ControlPrincipal, route: str, key: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Request sleep, wake, resize, export or delete of one project.

        The project must be one of the caller's organisations' and not deleted
        -- a foreign, missing or deleted project is the one `not_found` -- and
        the caller must hold `PROJECT_WRITES[route]` there.
        """
        row = await self.repository.get_project(caller.user_id, key)
        if row is None or not self._visible(caller, row["organization_id"]):
            raise errors.ControlRefused(errors.NOT_FOUND)
        if row["deleted_at"] is not None:
            raise errors.ControlRefused(errors.NOT_FOUND)
        organization = row["organization_id"]
        self.require_role(caller, organization, control_roles.PROJECT_WRITES[route])
        operation_type = control_roles.OPERATION_OF_ROUTE[route]
        return await self._request(caller, organization, key, operation_type, arguments)

    async def _request(
        self,
        caller: ControlPrincipal,
        organization: UUID,
        key: str | None,
        operation_type: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        operation, created = await self.repository.request_operation(
            caller.user_id, organization, key, operation_type, arguments
        )
        if not created:
            raise errors.ControlRefused(errors.CONFLICT, operation=str(operation))
        row = await self.repository.get_operation(caller.user_id, operation)
        assert row is not None, "the operation just recorded is not readable by its requester"
        return _operation(row)

    @staticmethod
    def resize_message() -> str:
        """The sentence a resize's `202` carries (D2157): the measured window,
        or that none has been measured on this server yet."""
        return compute_profiles.resize_message()

    async def cancel_operation(self, caller: ControlPrincipal, operation: UUID) -> dict[str, Any]:
        """Cancel a PENDING operation: its requester, or an admin or owner of
        its organisation (D2067). A running or finished one is `conflict`."""
        row = await self.repository.get_operation(caller.user_id, operation)
        if row is None or not self._visible(caller, row["organization_id"]):
            raise errors.ControlRefused(errors.NOT_FOUND)
        role = self.require_role(
            caller, row["organization_id"], control_roles.PROJECT_WRITES["cancel_operation"]
        )
        if row["requested_by"] != caller.user_id and control_roles.rank(role) < control_roles.rank(
            "admin"
        ):
            raise errors.AuthorizationFailed("the requester, or admin in the organisation")
        try:
            await self.repository.cancel_operation(caller.user_id, operation)
        except errors.ControlRefused as refused:
            if refused.word != errors.CONFLICT:
                raise
            raise errors.ControlRefused(errors.CONFLICT, operation=str(operation)) from refused
        cancelled = await self.repository.get_operation(caller.user_id, operation)
        assert cancelled is not None
        return _operation(cancelled)

    async def list_operations(
        self, caller: ControlPrincipal, organization: UUID
    ) -> list[dict[str, Any]]:
        self.require_role(caller, organization, "viewer")
        rows = await self.repository.list_operations(caller.user_id, organization)
        return [_operation(row) for row in rows if self._visible(caller, row["organization_id"])]

    async def get_operation(self, caller: ControlPrincipal, operation: UUID) -> dict[str, Any]:
        """One operation; for the PERSON who requested a succeeded export, its
        download URL, once (D2164). The URL is read and erased by one statement
        in the database, so a second read -- by anyone -- answers without it. A
        key never takes it: an export is a person's request (D2165), and a read
        key that could collect its URL would be a door to the data."""
        row = await self.repository.get_operation(caller.user_id, operation)
        if row is None or not self._visible(caller, row["organization_id"]):
            raise errors.ControlRefused(errors.NOT_FOUND)
        answer = _operation(row)
        if (
            not caller.is_key
            and row["requested_by"] == caller.user_id
            and row["type"] == "project.export"
            and row["status"] == "succeeded"
        ):
            secret = await self.repository.take_result_secret(caller.user_id, operation)
            if secret is not None:
                answer["download_url"] = secret
        return answer


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _organization(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "role": str(row["role"]),
        "created_at": row["created_at"].isoformat(),
    }


def _project(row: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    state, managed_by = control_states.project_state(history)
    return {
        "key": row["key"],
        "organization_id": str(row["organization_id"]),
        "display_name": row["display_name"],
        "slug": row["slug"],
        "environment": row["environment"],
        "domain": row["domain"],
        "region": row["region_id"],
        "profile": row["profile"],
        "state": state,
        "managed_by": managed_by,
        "app_route": row["app_route"],
        "template_version": row["template_version"],
        "source_commit": row["source_commit"],
        "adopted_at": row["adopted_at"].isoformat(),
        "deleted_at": _iso(row["deleted_at"]),
    }


def _operation(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "organization_id": str(row["organization_id"]),
        "project_key": row["project_key"],
        "type": row["type"],
        "status": row["status"],
        "progress": row["progress"],
        "error_code": row["error_code"],
        "step": row["step"],
        "result": row["result"],
        "requested_by": str(row["requested_by"]),
        "created_at": row["created_at"].isoformat(),
        "started_at": _iso(row["started_at"]),
        "finished_at": _iso(row["finished_at"]),
    }
