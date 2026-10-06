"""Every statement the control mode sends, in one place (ADR 0251).

`repository.py`'s arrangement, for the control project's own set: **function
calls and no table names.** `auth_service` holds USAGE on `app` and EXECUTE on
the `app.control_*` functions the set grants it, and no privilege on any
table, so a statement here that named one would fail at run time rather than
at review.

**Every transaction begins with `SELECT set_config('app.user_id', %s, true)`.**
Each control function also sets the caller itself from its own `p_user`
(`app.control_enter`, which resets every scope first, D2074); setting it here
too means a statement added later that reached a policy without going through
a function would still be scoped to the caller rather than to nobody's guess.
One request, one transaction: every method below opens and commits its own.

**Refusals come back as words.** A definer function raises `APnnn: <word>`;
`_refusal` turns exactly those into the control mode's exceptions and lets
anything else propagate unchanged. No database message reaches a caller.

Two methods compose a transaction across both schemas, on ONE connection:
`accept_as_new` (`app_private.auth_create_user`, `app.control_record_account`,
`app.control_accept_invitation`) and `confirm_factor`
(`app.control_totp_confirm`, then every live session ended through
`app_private.auth_list_sessions` and `auth_revoke_session`, D2080). The set
never names `app_private`; the composition lives here (D2046).
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg import errors as pg_errors
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app import errors

#: What a control function's refusal looks like: `AP` + a status + a word.
_REFUSAL = re.compile(r"^AP(\d{3}): ([a-z_]+)$")


def _refusal(exc: psycopg.Error) -> Exception | None:
    """The control mode's exception for an `APnnn: <word>` raise, or None."""
    message = getattr(exc.diag, "message_primary", None) or ""
    match = _REFUSAL.match(message)
    if match is None:
        return None
    word = match.group(2)
    if word == "authorization_failed":
        return errors.AuthorizationFailed("an organisation role")
    if word in errors.CONTROL_STATUS:
        return errors.ControlRefused(word)
    return None


class ControlRepository:
    """The pool, and the control set's calls. Holds no state of its own."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def _rows(
        self, user: UUID | None, statement: str, parameters: tuple[Any, ...]
    ) -> list[dict[str, Any]]:
        """One transaction: the caller set, then one statement, its rows read."""
        try:
            async with self._pool.connection() as connection:
                cursor = connection.cursor(row_factory=dict_row)
                await cursor.execute(
                    "SELECT set_config('app.user_id', %s, true)",
                    ("" if user is None else str(user),),
                )
                await cursor.execute(statement, parameters)
                return await cursor.fetchall() if cursor.description else []
        except psycopg.Error as exc:
            refused = _refusal(exc)
            if refused is None:
                raise
            raise refused from exc

    async def _one(
        self, user: UUID | None, statement: str, parameters: tuple[Any, ...]
    ) -> dict[str, Any] | None:
        rows = await self._rows(user, statement, parameters)
        return rows[0] if rows else None

    # -- accounts and the second factor -------------------------------------

    async def record_account(self, user: UUID, username: str, display_name: str) -> None:
        await self._rows(
            user, "SELECT app.control_record_account(%s, %s, %s)", (user, username, display_name)
        )

    async def caller_roles(self, user: UUID) -> dict[str, str]:
        """Every organisation the caller belongs to -> their role in it."""
        rows = await self._rows(
            user, "SELECT organization_id, role FROM app.control_caller_roles(%s)", (user,)
        )
        return {str(row["organization_id"]): str(row["role"]) for row in rows}

    async def totp_seed(self, user: UUID) -> dict[str, Any] | None:
        """The caller's seed, whether it is enabled, and the last accepted step."""
        return await self._one(
            user, "SELECT seed, enabled, last_step FROM app.control_totp_seed(%s)", (user,)
        )

    async def totp_begin(self, user: UUID, seed: bytes) -> None:
        await self._rows(user, "SELECT app.control_totp_begin(%s, %s)", (user, seed))

    async def totp_accept_step(self, user: UUID, step: int) -> bool:
        row = await self._one(
            user, "SELECT app.control_totp_accept_step(%s, %s) AS accepted", (user, step)
        )
        return bool(row and row["accepted"])

    async def confirm_factor(self, user: UUID, step: int, reason: str) -> int | None:
        """Enable the factor at `step` and end every live session, atomically.

        None when nothing was confirmed (no unconfirmed seed, or the step is
        not after the last accepted) -- and then no session is touched. Else
        the number of sessions ended (D2080: the two granted functions, in the
        confirming transaction, rather than the ungranted
        `auth_revoke_user_sessions`).
        """
        try:
            async with self._pool.connection() as connection:
                cursor = connection.cursor(row_factory=dict_row)
                await cursor.execute("SELECT set_config('app.user_id', %s, true)", (str(user),))
                await cursor.execute(
                    "SELECT app.control_totp_confirm(%s, %s) AS confirmed", (user, step)
                )
                confirmed = await cursor.fetchone()
                if not (confirmed and confirmed["confirmed"]):
                    return None
                await cursor.execute(
                    "SELECT family_id, revoked_at FROM app_private.auth_list_sessions(%s)",
                    (user,),
                )
                live = [
                    row["family_id"] for row in await cursor.fetchall() if not row["revoked_at"]
                ]
                for family in live:
                    await cursor.execute(
                        "SELECT app_private.auth_revoke_session(%s, %s, %s)",
                        (user, family, reason),
                    )
                return len(live)
        except psycopg.Error as exc:
            refused = _refusal(exc)
            if refused is None:
                raise
            raise refused from exc

    # -- organisations and members -------------------------------------------

    async def create_organization(self, user: UUID, name: str) -> UUID:
        row = await self._one(
            user, "SELECT app.control_create_organization(%s, %s) AS id", (user, name)
        )
        assert row is not None
        return row["id"]

    async def list_organizations(self, user: UUID) -> list[dict[str, Any]]:
        return await self._rows(
            user,
            "SELECT id, name, role, created_at FROM app.control_list_organizations(%s)",
            (user,),
        )

    async def get_organization(self, user: UUID, org: UUID) -> dict[str, Any] | None:
        return await self._one(
            user,
            "SELECT id, name, role, created_at FROM app.control_get_organization(%s, %s)",
            (user, org),
        )

    async def list_members(self, user: UUID, org: UUID) -> list[dict[str, Any]]:
        return await self._rows(
            user,
            "SELECT user_id, username, display_name, role, created_at "
            "FROM app.control_list_members(%s, %s)",
            (user, org),
        )

    async def set_member_role(self, user: UUID, org: UUID, target: UUID, role: str) -> None:
        await self._rows(
            user,
            "SELECT app.control_set_member_role(%s, %s, %s, %s::app.control_role)",
            (user, org, target, role),
        )

    async def remove_member(self, user: UUID, org: UUID, target: UUID) -> None:
        await self._rows(user, "SELECT app.control_remove_member(%s, %s, %s)", (user, org, target))

    # -- invitations -----------------------------------------------------------

    async def mint_invitation(
        self,
        user: UUID,
        org: UUID | None,
        role: str | None,
        token_hash: str,
        expires_at: datetime,
    ) -> UUID:
        row = await self._one(
            user,
            "SELECT app.control_mint_invitation(%s, %s, %s::app.control_role, %s, %s) AS id",
            (user, org, role, token_hash, expires_at),
        )
        assert row is not None
        return row["id"]

    async def list_invitations(self, user: UUID, org: UUID) -> list[dict[str, Any]]:
        return await self._rows(
            user,
            "SELECT id, role, issued_by, issued_at, expires_at, accepted_at, revoked_at "
            "FROM app.control_list_invitations(%s, %s)",
            (user, org),
        )

    async def revoke_invitation(self, user: UUID, org: UUID, invitation: UUID) -> bool:
        row = await self._one(
            user,
            "SELECT app.control_revoke_invitation(%s, %s, %s) AS revoked",
            (user, org, invitation),
        )
        return bool(row and row["revoked"])

    async def accept_as_existing(
        self, token_hash: str, user: UUID, username: str, display_name: str
    ) -> dict[str, Any]:
        """An existing account accepts: its display row, then the spend."""
        try:
            async with self._pool.connection() as connection:
                cursor = connection.cursor(row_factory=dict_row)
                await cursor.execute("SELECT set_config('app.user_id', %s, true)", (str(user),))
                await cursor.execute(
                    "SELECT app.control_record_account(%s, %s, %s)", (user, username, display_name)
                )
                await cursor.execute(
                    "SELECT organization_id, role FROM app.control_accept_invitation(%s, %s)",
                    (token_hash, user),
                )
                accepted = await cursor.fetchone()
                assert accepted is not None
                return {"user_id": user, **accepted}
        except psycopg.Error as exc:
            refused = _refusal(exc)
            if refused is None:
                raise
            raise refused from exc

    async def accept_as_new(
        self,
        token_hash: str,
        *,
        username: str,
        display_name: str,
        role_name: str,
        scopes: list[str],
        password_hash: str,
    ) -> dict[str, Any]:
        """Create the account and spend the invitation in ONE transaction (D2051).

        The registry user, its display row and the spend commit together or
        not at all: any failure rolls back the user `auth_create_user` made.

        **A taken username is answered only after the token validated**, and
        the token is left unspent. The user insert runs in a savepoint; if the
        name is taken, the spend is still attempted -- for a throwaway id no
        account carries -- purely to learn whether the token is good, and the
        whole transaction is then rolled back by raising: `invitation_invalid`
        if the spend refused, `username_taken` if it would have succeeded (a
        membership invitation then fails its insert on the account's foreign
        key, which is the spend having matched). Either way nothing commits.
        """
        try:
            async with self._pool.connection() as connection:
                cursor = connection.cursor(row_factory=dict_row)
                # A statement BEFORE the savepoint: psycopg opens a block on
                # an idle connection with BEGIN and closes it with COMMIT, which
                # would commit the new user on its own. Inside the implicit
                # transaction this statement starts, the block is a SAVEPOINT.
                await cursor.execute("SELECT set_config('app.user_id', '', true)")
                taken = False
                try:
                    async with connection.transaction():
                        await cursor.execute(
                            "SELECT app_private.auth_create_user(%s, %s, %s, %s, %s) AS user_id",
                            (username, display_name, role_name, scopes, password_hash),
                        )
                        created = await cursor.fetchone()
                except pg_errors.UniqueViolation:
                    taken = True
                user = uuid.uuid4() if taken else created["user_id"]  # type: ignore[index]
                await cursor.execute("SELECT set_config('app.user_id', %s, true)", (str(user),))
                if not taken:
                    await cursor.execute(
                        "SELECT app.control_record_account(%s, %s, %s)",
                        (user, username, display_name),
                    )
                try:
                    await cursor.execute(
                        "SELECT organization_id, role FROM app.control_accept_invitation(%s, %s)",
                        (token_hash, user),
                    )
                    accepted = await cursor.fetchone()
                except pg_errors.ForeignKeyViolation as exc:
                    if taken:
                        raise errors.ControlRefused(errors.USERNAME_TAKEN) from exc
                    raise
                if taken:
                    raise errors.ControlRefused(errors.USERNAME_TAKEN)
                assert accepted is not None
                return {"user_id": user, **accepted}
        except psycopg.Error as exc:
            refused = _refusal(exc)
            if refused is None:
                raise
            raise refused from exc
