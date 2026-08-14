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
