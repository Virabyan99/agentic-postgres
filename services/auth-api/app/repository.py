"""Every statement this service sends, in one place.

**Eight function calls and no table names.** `auth_service` holds schema USAGE
on `app_private` and nothing else -- measured against the applied migrations:
`SELECT` on `app_private.users` is `permission denied for table users`, and the
eight granted functions answer. So a query written here that named a table would
fail at run time rather than review, and this module is the whole surface a
reviewer has to read to know what the service can reach.

Two of the twelve functions 0012 creates are deliberately absent:
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
