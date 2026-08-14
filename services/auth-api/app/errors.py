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


class InvalidRequest(Exception):
    """Well-formed and refused. The message is returned to an administrator."""


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
