"""What a caller is told, and what it deliberately is not.

**One failure for four causes.** An unknown username, a wrong password, a
disabled subject and a subject whose credential row is missing all produce the
same status, the same body and the same amount of work. The plan says "unknown,
wrong, disabled and locked all return the same code and the same work class",
and each of the four is a way to learn something about a subject from outside:

* *unknown* leaks the user list;
* *wrong* is the only one a caller is entitled to infer;
* *disabled* tells an attacker their target exists and is worth waiting for;
* a missing credential row tells them an account is mid-repair.

Sameness has three parts and only one of them is the status code. The body is a
fixed string, so a client cannot branch on prose. The work is the same, because
`Hasher.verify` runs a real Argon2 comparison against a dummy for a subject that
does not exist -- measured at 127.9 ms against 126.3 ms for a real miss. And the
*order* is fixed in `service.py`: the password is verified before the status is
consulted, so a disabled subject costs what an active one costs.

**There is no `locked` state** (D265). `app_private.user_status` is `active` or
`disabled`, and an automatic lockout is not added: with Argon2id at the frozen
profile and the edge's rate limit, a per-account counter mostly buys an attacker
a denial of service against a named administrator. An administrator-applied lock
is `disabled`, which this file already treats identically.
"""

from __future__ import annotations

from typing import Any, Final

from fastapi.responses import JSONResponse

#: The body every authentication failure returns, byte for byte.
#:
#: A stable machine-readable token and nothing else. No `message`, no `detail`,
#: no field naming what was wrong: `bin/api-contract.py` learned this the hard
#: way when it compiled a diagnosis into an error message and named the wrong
#: divergence (§6). A caller gets what it is entitled to act on.
AUTHENTICATION_FAILED: Final = {"error": "authentication_failed"}

#: Refused for want of authority rather than identity. Distinct from the above
#: because the caller has already proved who it is: telling it that its token is
#: valid but insufficient leaks nothing it does not already know, and hiding the
#: difference would make every scope mistake look like a broken login.
AUTHORIZATION_FAILED: Final = {"error": "authorization_failed"}

#: A request that was refused before any domain logic ran (API-AUTH-002). One
#: token for nine structural problems, for the reason `MalformedToken` is one
#: type: which of them a bad request had is not information its sender needs.
MALFORMED_REQUEST: Final = {"error": "malformed_request"}

#: A request whose values are individually well formed and jointly refused --
#: a scope outside the role's ceiling, a username already taken. The caller is
#: an authenticated administrator, so a reason is safe and useful.
INVALID_REQUEST: Final = {"error": "invalid_request"}

#: Session 7. The one answer the storage surface gives for an object the caller
#: cannot be told about: absent, another user's, still pending, or tombstoned.
#:
#: **Four causes, one body, and that is STO-OWN-001** rather than a courtesy.
#: Distinguishing "does not exist" from "not yours" turns an object id into an
#: oracle for whether a stranger's object exists, and object ids travel in URLs.
#: The obscuring is not implemented here:
#: `app_private.storage_lookup_for_download` filters on owner AND state in one
#: predicate and returns zero rows for all four, so the service never learns
#: which case it had and cannot leak a difference it does not hold.
#:
#: 404 rather than 403, because a 403 would confirm the object exists.
OBJECT_UNAVAILABLE: Final = {"error": "object_unavailable"}

#: Session 7. A state the OWNER can act on, returned only to them.
#:
#: D314 asked for a parallel `STOR100`-`STOR111` vocabulary, several of whose
#: codes return a message to an unauthenticated caller. ADR 0097 already decided
#: that split, and this extends it rather than restating it: a storage-specific
#: code is admissible only where it names a state the caller can *act on* and
#: the caller is authenticated as the object's owner. Everything structural
#: stays `malformed_request` -- 400, with nothing in it.
#:
#: Reached only after the database has confirmed ownership, because
#: `storage_complete_upload` returns the current state for the owner's row and
#: NULL for every other case. So naming the state tells a caller about their own
#: object and about nobody else's.
OBJECT_STATE_CONFLICT: Final = {"error": "object_state_conflict"}


class AuthenticationFailed(Exception):
    """Any of the four. Carries a reason for the log and never for the caller."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class AuthorizationFailed(Exception):
    """A valid token without the scope the route requires (API-ADMIN-001)."""

    def __init__(self, required: str) -> None:
        super().__init__(f"the token does not carry {required}")
        self.required = required


class MalformedRequest(Exception):
    """Refused on its shape, before any domain logic ran (ADR 0097).

    Distinct from `InvalidRequest` because the two answer different callers.
    This one is raised on an **unauthenticated** path as often as not -- a login
    body that is not an object, that carries a duplicate member, or that names a
    field the model forbids -- and `MALFORMED_REQUEST` is deliberately one token
    for nine structural problems, because which of them a bad request had is not
    information its sender needs.

    The reason travels for the log and never for the caller, which is the shape
    `AuthenticationFailed` already has and for the same reason.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InvalidRequest(Exception):
    """Well-formed and refused. The message is returned to an administrator."""


class ObjectUnavailable(Exception):
    """Absent, another owner's, pending or tombstoned -- and never says which.

    Carries no attributes on purpose. An exception with a `reason` would be a
    place for the four causes to become distinguishable later, one careful
    `if` at a time, and the whole property is that the service does not hold
    the distinction to leak.
    """


class ObjectStateConflict(Exception):
    """The owner's object is not in a state this operation can move it from."""

    def __init__(self, state: str) -> None:
        super().__init__(state)
        self.state = state


def unauthenticated() -> JSONResponse:
    """401, with `WWW-Authenticate` because RFC 9110 requires it on a 401.

    `Bearer` with no `error` parameter: RFC 6750 defines `invalid_token` and
    friends, and each one tells an unauthenticated caller something about why.
    """
    return JSONResponse(
        AUTHENTICATION_FAILED, status_code=401, headers={"WWW-Authenticate": "Bearer"}
    )


def unauthorized() -> JSONResponse:
    """403. The caller is known and may not do this."""
    return JSONResponse(AUTHORIZATION_FAILED, status_code=403)


def malformed() -> JSONResponse:
    """400, before any domain logic ran."""
    return JSONResponse(MALFORMED_REQUEST, status_code=400)


def invalid(message: str) -> JSONResponse:
    """422, with a reason, for an authenticated administrator."""
    body: dict[str, Any] = {**INVALID_REQUEST, "message": message}
    return JSONResponse(body, status_code=422)


def object_unavailable() -> JSONResponse:
    """404, and the same 404 for four different causes (STO-OWN-001).

    `no-store` because a cache that remembered this answer for an id would keep
    answering it after the object became available -- and, worse, could serve
    one user's 404 to another user whose object of that id does exist.
    """
    return JSONResponse(OBJECT_UNAVAILABLE, status_code=404, headers={"Cache-Control": "no-store"})


def object_state_conflict(state: str) -> JSONResponse:
    """409, naming the owner's own object's state.

    Safe because it is unreachable unless the database matched the row on owner
    id: every non-owned case comes back indistinguishable from absent and
    becomes `object_unavailable` instead.
    """
    body: dict[str, Any] = {**OBJECT_STATE_CONFLICT, "state": state}
    return JSONResponse(body, status_code=409, headers={"Cache-Control": "no-store"})
