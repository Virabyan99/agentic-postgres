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
            "SELECT agent_id, role_name, scopes, status, authz_version, secret_hash "
            "FROM app_private.auth_lookup_agent(%s)",
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
    ) -> UUID:
        row = await self._one(
            "SELECT app_private.auth_create_agent(%s, %s, %s, %s, %s, %s) AS agent_id",
            (name, description, role_name, scopes, owner_id, secret_hash),
        )
        assert row is not None
        return row["agent_id"]

    async def rotate_agent_secret(self, agent_id: UUID, secret_hash: str) -> int | None:
        row = await self._one(
            "SELECT app_private.auth_rotate_agent_secret(%s, %s) AS version",
            (agent_id, secret_hash),
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
