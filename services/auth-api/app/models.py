"""Request and response shapes. Every one of them closed.

**`extra="forbid"` on every request model, and it is measured rather than
assumed.** Without it, pydantic accepts and *discards* an unknown member:
`Loose(username="a", role="admin")` validates and the model has no `role`, so a
client's attempt to name its own authority leaves no trace at all. With it, the
same request is refused with `extra_forbidden`.

**No request model has a `role` or a `scope` field on the login path**, and that
is the design rather than an omission: a client never submits either. The
administrative models do carry them, because an administrator setting another
subject's authority is exactly what those endpoints are for -- and what bounds
them is `scope_registry`'s ceiling, checked in `service.py`, not the model.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: Bounds on the strings a client may send. These are not the password policy --
#: that is `hashing.assess`, which runs after normalization and says why it
#: refused. These stop a 16 KiB body being turned into 16 KiB of Argon2 input
#: before anything has looked at it.
USERNAME_MAX = 128
DISPLAY_NAME_MAX = 256
PASSWORD_MAX = 1024


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class LoginRequest(_Strict):
    """Two fields, and there is deliberately no third.

    Whitespace is NOT stripped. `str_strip_whitespace` would silently change a
    password whose first character is a space into a different password, and the
    subject who set it that way could never log in again.
    """

    username: str = Field(min_length=1, max_length=USERNAME_MAX)
    password: str = Field(min_length=1, max_length=PASSWORD_MAX)


class CreateUserRequest(_Strict):
    """`role` is a SUFFIX, never a derived role name.

    A client naming `apg_alpha_dev_project_admin` would be a client that had to
    know how this deployment derives names -- and one that could name a role
    from another project. The suffix is mapped to a derived name by the service,
    against `naming.ROLE_SUFFIXES`, which is the single authority (ADR 0002).
    """

    username: str = Field(min_length=1, max_length=USERNAME_MAX)
    display_name: str = Field(min_length=1, max_length=DISPLAY_NAME_MAX)
    role: str = Field(min_length=1, max_length=64)
    scopes: list[str] = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=PASSWORD_MAX)


class UpdateUserRequest(_Strict):
    """Every field optional, and at least one required -- checked in the route.

    Three separate concerns in one model, because they are three separate
    version bumps: authorization moves `authz_version`, status moves it too, and
    a password moves `credential_version`. The route applies whichever are
    present, each through its own function.
    """

    role: str | None = Field(default=None, min_length=1, max_length=64)
    scopes: list[str] | None = Field(default=None, min_length=1, max_length=32)
    status: Literal["active", "disabled"] | None = None
    password: str | None = Field(default=None, min_length=1, max_length=PASSWORD_MAX)


class TokenResponse(BaseModel):
    """What a successful login returns.

    `expires_at` as an absolute epoch second rather than `expires_in`: a
    duration is relative to a moment the client has to guess at, and the token's
    own `exp` is absolute. Two representations of one deadline is how they come
    to disagree.
    """

    access_token: str
    # (S105 matches on the field name. `Bearer` is RFC 6750's scheme name, sent
    # in every response this model describes; it is not a credential.)
    token_type: Literal["Bearer"] = "Bearer"  # noqa: S105
    expires_at: int
    token_use: str


class SubjectResponse(BaseModel):
    """What `/auth/me` reflects. Current state, never the token's copy of it."""

    user_id: str
    username: str
    display_name: str
    role: str
    scopes: list[str]
    status: str
    credential_version: int
    authz_version: int
    last_login_at: str | None


# The four failure bodies, as schemas.
#
# **A model docstring becomes a `description` in the published document**, so
# these are written for whoever reads the reference rather than for whoever
# maintains this file -- measured by reading the captured snapshot back, where
# the first draft explained why a schema lives here at all and named two ADRs.
# The reasoning that belongs to this repository stays in comments like this one.
#
# They are response shapes in a file of mostly request shapes because
# `errors.py` returns literals, and a schema written beside the document instead
# of beside the values would be a second authority on what a caller receives.


class AuthenticationFailedResponse(BaseModel):
    """Returned when no usable credential was presented.

    The same body for every cause: unknown subject, wrong password, disabled
    subject. Do not branch on it -- there is nothing else to read.
    """

    error: Literal["authentication_failed"]


class AuthorizationFailedResponse(BaseModel):
    """Returned when the caller is known and does not hold the required scope.

    Distinct from an authentication failure on purpose: the caller has already
    proved who it is, so telling it that its token is valid and insufficient
    leaks nothing it does not know.
    """

    error: Literal["authorization_failed"]


class MalformedRequestResponse(BaseModel):
    """Returned when the request was refused before any domain logic ran.

    An oversized body, a duplicate JSON member, a non-object root, an unknown
    field, or a field outside its bounds. Which one is not reported.
    """

    error: Literal["malformed_request"]


class InvalidRequestResponse(BaseModel):
    """Returned when the request is well formed and jointly refused.

    A scope outside the role's ceiling, a username already taken. `message`
    says which, because the caller is an authenticated administrator.
    """

    error: Literal["invalid_request"]
    message: str


class AgentTokenRequest(_Strict):
    """An agent presents an id and the secret it was shown once.

    Two fields, like a login, and for the same reason: there is no third. An
    agent cannot ask for a role or a scope any more than a person can.
    """

    agent_id: str = Field(min_length=1, max_length=64)
    secret: str = Field(min_length=1, max_length=PASSWORD_MAX)


class CreateAgentRequest(_Strict):
    """`role` is a suffix, and only an agent role will be accepted.

    The model does not enforce which: the ceiling in `scopes.ROLE_SCOPES` does,
    and putting a second list here would be two authorities for one vocabulary.
    """

    name: str = Field(min_length=1, max_length=USERNAME_MAX)
    description: str = Field(default="", max_length=DISPLAY_NAME_MAX)
    role: str = Field(min_length=1, max_length=64)
    scopes: list[str] = Field(min_length=1, max_length=32)


class UpdateAgentRequest(_Strict):
    """No `secret` field. Rotation is its own endpoint.

    A `PATCH` carrying a secret would be a request whose body sometimes holds a
    credential, which is exactly the shape that makes redaction a per-field
    decision somebody has to remember.
    """

    role: str | None = Field(default=None, min_length=1, max_length=64)
    scopes: list[str] | None = Field(default=None, min_length=1, max_length=32)
    status: Literal["active", "revoked"] | None = None
