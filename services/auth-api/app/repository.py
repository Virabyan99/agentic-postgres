"""Every statement this service sends, in one place.

**Fifteen function calls and no table names.** `auth_service` holds schema
USAGE on `app_private` and nothing else -- measured against the applied
migrations: `SELECT` on `app_private.users` is `permission denied for table
users`, and the granted functions answer. So a query written here that named a table would
fail at run time rather than review, and this module is the whole surface a
reviewer has to read to know what the service can reach.

The fifteenth is `auth_list_agent_audit`, added by migration 0020 (ADR 0142).
The count is in this sentence because it is the sentence a reviewer reads to
know the surface, and a count that stops being maintained is a count that stops
being read -- Session 9 Run 7 found migration 0019 having built two indexes for
a reader nobody created (D501), which is the same failure in the other file.

Two of the functions 0012 creates are deliberately absent:
`auth_bootstrap_administrator` and `auth_bootstrap_lock_key` are not granted to
this role, because a service that could call them is the public bootstrap
endpoint §4 says does not exist. Measured: both refuse with `permission denied
for function`.

**Every parameter is bound, never interpolated.** psycopg's `%s` is a protocol
parameter, not a string substitution, and the arrays go through as arrays -- a
comma-joined string would be a second serialisation of a value the database
already has a type for.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


@dataclass(frozen=True, slots=True)
class Credential:
    """What a login needs: the subject, its authority, and its verifier."""

    user_id: UUID
    role_name: str
    scopes: list[str]
    status: str
    credential_version: int
    authz_version: int
    password_hash: str | None


@dataclass(frozen=True, slots=True)
class AgentCredential:
    """What an agent token exchange needs.

    No `credential_version`: an agent has no password to change, so a rotated
    secret moves `authz_version` and there is nothing a second counter would
    distinguish (0011).
    """

    agent_id: UUID
    role_name: str
    scopes: list[str]
    status: str
    authz_version: int
    secret_hash: str | None
    #: Computed by the DATABASE against its own clock (ADR 0172), never a
    #: timestamp this process compares. One clock in the decision, no skew.
    secret_expired: bool = False


@dataclass(frozen=True, slots=True)
class RefreshAttempt:
    """What `auth_consume_refresh_token` reports: facts, never a verdict.

    `rotated` says whether the transition happened. The rest describe the row
    for a caller that did not win, and `app.refresh_sessions.classify` is what
    turns them into one of five outcomes -- the precedence lives there and in no
    other place (ADR 0171).

    `family_id` and `user_id` are NULL when nothing carries the presented
    digest, which is the one case where no session exists to name.
    """

    rotated: bool
    found: bool
    was_consumed: bool
    family_revoked: bool
    expires_at: Any
    family_id: UUID | None
    user_id: UUID | None


@dataclass(frozen=True, slots=True)
class ResetAttempt:
    """What `auth_consume_password_reset` reports: facts, never a verdict.

    `consumed` says whether the password actually changed. The rest describe the
    row for a caller that did not spend it, and the service names the outcome --
    the same division `RefreshAttempt` has, and for the same reason.
    """

    consumed: bool
    found: bool
    was_consumed: bool
    expires_at: Any
    user_id: UUID | None
    credential_version: int | None
    sessions_ended: int | None


@dataclass(frozen=True, slots=True)
class SubjectState:
    """What `/auth/me` reflects, and what a token is checked against."""

    username: str
    display_name: str
    role_name: str
    scopes: list[str]
    status: str
    credential_version: int
    authz_version: int
    last_login_at: Any


class Repository:
    """The pool, and the eight calls. Holds no state of its own."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def _one(self, statement: str, parameters: tuple[Any, ...]) -> dict[str, Any] | None:
        async with self._pool.connection() as connection:
            cursor = connection.cursor(row_factory=dict_row)
            await cursor.execute(statement, parameters)
            return await cursor.fetchone()

    async def _all(self, statement: str, parameters: tuple[Any, ...]) -> list[dict[str, Any]]:
        async with self._pool.connection() as connection:
            cursor = connection.cursor(row_factory=dict_row)
            await cursor.execute(statement, parameters)
            return await cursor.fetchall()

    # -- reading -----------------------------------------------------------

    async def lookup(self, username: str) -> Credential | None:
        """At most one row, and None for an unknown username.

        None rather than an exception, matching the function's own contract:
        a raise here would make "no such user" distinguishable from "wrong
        password" by the shape of the failure, which is the whole thing
        `errors.py` exists to prevent.
        """
        row = await self._one(
            "SELECT user_id, role_name, scopes, status, credential_version, "
            "authz_version, password_hash FROM app_private.auth_lookup_user(%s)",
            (username,),
        )
        if row is None:
            return None
        return Credential(
            user_id=row["user_id"],
            role_name=row["role_name"],
            scopes=list(row["scopes"]),
            status=row["status"],
            credential_version=row["credential_version"],
            authz_version=row["authz_version"],
            password_hash=row["password_hash"],
        )

    async def state(self, user_id: UUID) -> SubjectState | None:
        row = await self._one(
            "SELECT username, display_name, role_name, scopes, status, "
            "credential_version, authz_version, last_login_at "
            "FROM app_private.auth_user_state(%s)",
            (user_id,),
        )
        if row is None:
            return None
        return SubjectState(
            username=row["username"],
            display_name=row["display_name"],
            role_name=row["role_name"],
            scopes=list(row["scopes"]),
            status=row["status"],
            credential_version=row["credential_version"],
            authz_version=row["authz_version"],
            last_login_at=row["last_login_at"],
        )

    async def list_users(self) -> list[dict[str, Any]]:
        return await self._all("SELECT * FROM app_private.auth_list_users()", ())

    # -- writing -----------------------------------------------------------

    async def record_login(self, user_id: UUID) -> None:
        await self._one("SELECT app_private.auth_record_login(%s)", (user_id,))

    async def create_user(
        self,
        *,
        username: str,
        display_name: str,
        role_name: str,
        scopes: list[str],
        password_hash: str,
    ) -> UUID:
        row = await self._one(
            "SELECT app_private.auth_create_user(%s, %s, %s, %s, %s) AS user_id",
            (username, display_name, role_name, scopes, password_hash),
        )
        assert row is not None  # the function returns a row or raises
        return row["user_id"]

    async def set_authorization(
        self, user_id: UUID, *, role_name: str, scopes: list[str]
    ) -> int | None:
        """Returns the new `authz_version`, or None when there is no such subject.

        None is how "no such subject" arrives, because the SQL `UPDATE ...
        RETURNING` yields no value when it matched nothing. The caller turns
        that into a 404; it is not an error the database should raise, since a
        concurrent deletion is a normal outcome rather than a fault.
        """
        row = await self._one(
            "SELECT app_private.auth_set_authorization(%s, %s, %s) AS version",
            (user_id, role_name, scopes),
        )
        return None if row is None else row["version"]

    async def set_status(self, user_id: UUID, status: str) -> int | None:
        row = await self._one(
            "SELECT app_private.auth_set_status(%s, %s) AS version", (user_id, status)
        )
        return None if row is None else row["version"]

    async def set_password(self, user_id: UUID, password_hash: str) -> int | None:
        row = await self._one(
            "SELECT app_private.auth_set_password(%s, %s) AS version",
            (user_id, password_hash),
        )
        return None if row is None else row["version"]

    # -- agents ------------------------------------------------------------

    async def lookup_agent(self, agent_id: UUID) -> AgentCredential | None:
        """By id. None for an unknown one, never an exception.

        An agent presents an identifier it was given rather than a name, so
        there is no normalisation here and no guessable half of the credential.
        """
        row = await self._one(
            "SELECT agent_id, role_name, scopes, status, authz_version, secret_hash, "
            "secret_expired FROM app_private.auth_lookup_agent(%s)",
            (agent_id,),
        )
        if row is None:
            return None
        return AgentCredential(
            agent_id=row["agent_id"],
            role_name=row["role_name"],
            scopes=list(row["scopes"]),
            status=row["status"],
            authz_version=row["authz_version"],
            secret_hash=row["secret_hash"],
            secret_expired=bool(row["secret_expired"]),
        )

    async def list_agents(self) -> list[dict[str, Any]]:
        return await self._all("SELECT * FROM app_private.auth_list_agents()", ())

    async def create_agent(
        self,
        *,
        name: str,
        description: str,
        role_name: str,
        scopes: list[str],
        owner_id: UUID,
        secret_hash: str,
        expires_at: datetime | None,
    ) -> UUID:
        row = await self._one(
            "SELECT app_private.auth_create_agent(%s, %s, %s, %s, %s, %s, %s) AS agent_id",
            (name, description, role_name, scopes, owner_id, secret_hash, expires_at),
        )
        assert row is not None
        return row["agent_id"]

    async def rotate_agent_secret(
        self, agent_id: UUID, secret_hash: str, expires_at: datetime | None
    ) -> int | None:
        """A new secret, its deadline, and the revocation cleared (ADR 0172).

        Clearing the revocation here is what makes refusing `revoked -> active`
        safe: without it an agent revoked by mistake would be permanently dead
        (D839).
        """
        row = await self._one(
            "SELECT app_private.auth_rotate_agent_secret(%s, %s, %s) AS version",
            (agent_id, secret_hash, expires_at),
        )
        return None if row is None else row["version"]

    async def set_agent_authorization(
        self, agent_id: UUID, *, role_name: str, scopes: list[str]
    ) -> int | None:
        row = await self._one(
            "SELECT app_private.auth_set_agent_authorization(%s, %s, %s) AS version",
            (agent_id, role_name, scopes),
        )
        return None if row is None else row["version"]

    async def set_agent_status(self, agent_id: UUID, status: str) -> int | None:
        row = await self._one(
            "SELECT app_private.auth_set_agent_status(%s, %s) AS version", (agent_id, status)
        )
        return None if row is None else row["version"]

    async def list_agent_audit(
        self, *, agent_id: UUID | None, owner_id: UUID | None, limit: int
    ) -> list[dict[str, Any]]:
        """The audit record, most recent first (migration 0020, ADR 0142).

        The fifteenth function call, and still no table name: `auth_service`
        holds no `SELECT` on `app_private.agent_audit` and reads it through
        `auth_list_agent_audit`, a definer function granted to this role alone.
        A statement here that named the table would fail at run time rather than
        at review, which is this module's whole arrangement.

        **Both filters go through as `NULL` when absent**, which the function
        reads as "do not filter". A caller-side branch building one of four
        statements would be four statements to review instead of one, and the
        `IS NULL OR` form is what lets the planner still use 0019's
        `(agent_id, started_at DESC)` and `(owner_id, started_at DESC)` indexes
        when a filter is supplied.

        `limit` is bounded by the route, which answers 422 outside its range. It
        is re-bounded neither here nor in the function: two bounds over one rule
        drift the moment either moves (D495, D463).
        """
        return await self._all(
            "SELECT * FROM app_private.auth_list_agent_audit(%s, %s, %s)",
            (agent_id, owner_id, limit),
        )

    # -- the session plane (Session 15 Run 3, ADR 0171) ---------------------

    async def open_session(self, user_id: UUID, token_hash: str, expires_at: datetime) -> UUID:
        """Create a session and its first refresh token. Returns the family id."""
        row = await self._one(
            "SELECT app_private.auth_open_session(%s, %s, %s) AS family_id",
            (user_id, token_hash, expires_at),
        )
        assert row is not None
        return row["family_id"]

    async def consume_refresh_token(
        self, token_hash: str, new_hash: str, expires_at: datetime
    ) -> RefreshAttempt:
        """Present a refresh token. Returns FACTS; `classify` names the outcome.

        The three-condition guard inside the function is what makes this atomic,
        and `rotated` is the whole race outcome: under `read committed` the
        loser of two concurrent presentations blocks until the winner commits
        and then matches nothing, which was measured with a control (D826).
        Nothing here retries, and that is deliberate -- a retry would present
        the same token a second time, which is what a replay looks like.
        """
        row = await self._one(
            "SELECT rotated, found, was_consumed, family_revoked, expires_at, "
            "family_id, user_id "
            "FROM app_private.auth_consume_refresh_token(%s, %s, %s)",
            (token_hash, new_hash, expires_at),
        )
        assert row is not None
        return RefreshAttempt(
            rotated=row["rotated"],
            found=row["found"],
            was_consumed=row["was_consumed"],
            family_revoked=row["family_revoked"],
            expires_at=row["expires_at"],
            family_id=row["family_id"],
            user_id=row["user_id"],
        )

    async def list_sessions(self, user_id: UUID) -> list[dict[str, Any]]:
        return await self._all("SELECT * FROM app_private.auth_list_sessions(%s)", (user_id,))

    async def revoke_session(self, user_id: UUID, family_id: UUID, reason: str) -> bool:
        """End one session, scoped to its owner.

        False for an unknown family, another subject's family, and one already
        ended. Three cases and one answer, because distinguishing them would
        tell a caller whether a family id it guessed belongs to somebody.
        """
        row = await self._one(
            "SELECT app_private.auth_revoke_session(%s, %s, %s) AS ended",
            (user_id, family_id, reason),
        )
        assert row is not None
        return bool(row["ended"])

    # -- the password-reset plane (Session 15 Run 5, ADR 0173) --------------

    async def open_password_reset(
        self, user_id: UUID, issued_by: UUID, token_hash: str, expires_at: datetime
    ) -> UUID | None:
        """Issue a one-time reset. None for an unknown subject, never an exception."""
        row = await self._one(
            "SELECT app_private.auth_open_password_reset(%s, %s, %s, %s) AS reset_id",
            (user_id, issued_by, token_hash, expires_at),
        )
        assert row is not None
        return row["reset_id"]

    async def consume_password_reset(self, token_hash: str, password_hash: str) -> ResetAttempt:
        """Spend a reset: the password, its version, and the subject's sessions.

        One call, because the three are one transaction in SQL. A service that
        set the password and then ended the sessions would leave an interval in
        which a chain obtained with the old password still minted access tokens.
        """
        row = await self._one(
            "SELECT consumed, found, was_consumed, expires_at, user_id, "
            "credential_version, sessions_ended "
            "FROM app_private.auth_consume_password_reset(%s, %s)",
            (token_hash, password_hash),
        )
        assert row is not None
        return ResetAttempt(
            consumed=row["consumed"],
            found=row["found"],
            was_consumed=row["was_consumed"],
            expires_at=row["expires_at"],
            user_id=row["user_id"],
            credential_version=row["credential_version"],
            sessions_ended=row["sessions_ended"],
        )
