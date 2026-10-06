"""The organisation role matrix, in one place (D2053, ADR 0252).

**Every management route is named here with what it needs**, and the control
routes' one guard reads this table -- no handler checks a role of its own,
which is the D600 shape this file exists to avoid. The control set's definer
functions check the same ranks again in the database
(`app.control_require_role`), so a route this table forgot is still refused
there; `test_every_route_and_role_answers_as_the_matrix_says` enumerates every
`/v1` route against this table in both directions.

What an entry means:

* `PUBLIC` -- no bearer: logging in, refreshing, logging out, and accepting an
  invitation (the token in the body is the credential).
* `ACCOUNT` -- any authenticated control-plane account, whatever it belongs to:
  reading itself, enrolling a factor, listing and creating organisations, and
  minting an invitation (whose organisation, if any, is in the body and is
  checked against this table by the handler, `MEMBERSHIP_INVITATION`).
* a role -- the caller must hold at least that role in the organisation the
  path names; a non-member gets the same `404` as a missing organisation.

Run 5 adds the keys, projects and operations routes to this table.
"""

from __future__ import annotations

from typing import Final

from app import scopes as scope_map

#: The four roles, lowest first -- `app.control_role_rank`'s order.
ROLES: Final[tuple[str, ...]] = ("viewer", "member", "admin", "owner")

PUBLIC: Final = "public"
ACCOUNT: Final = "account"


def rank(role: str) -> int:
    """`app.control_role_rank`, in Python: viewer 1 ... owner 4."""
    return ROLES.index(role) + 1


#: route name (the handler's function name, which FastAPI uses as the route's
#: `name`) -> what it needs.
MATRIX: Final[dict[str, str]] = {
    # The session plane and acceptance: no bearer.
    "create_session": PUBLIC,
    "refresh_session": PUBLIC,
    "end_session": PUBLIC,
    "accept_invitation": PUBLIC,
    # Oneself.
    "me": ACCOUNT,
    "begin_factor": ACCOUNT,
    "confirm_factor": ACCOUNT,
    # Organisations.
    "list_organizations": ACCOUNT,
    "create_organization": ACCOUNT,
    "mint_invitation": ACCOUNT,
    "get_organization": "viewer",
    "list_members": "viewer",
    "set_member_role": "admin",
    "remove_member": "admin",
    "list_invitations": "admin",
    "revoke_invitation": "admin",
    # Run 5: keys -- any member manages their own; an admin or owner revokes
    # any of the organisation's (the definer functions decide which rows).
    "list_keys": "viewer",
    "mint_key": "viewer",
    "revoke_key": "viewer",
    # Run 5: the registry and its operations. The organisation, when there is
    # one, is a query parameter or is read from the row, and the handler
    # applies `viewer` to it; a foreign one is the same 404 as a missing one.
    "list_projects": ACCOUNT,
    "get_project": ACCOUNT,
    "create_project": ACCOUNT,
    "list_operations": ACCOUNT,
    "get_operation": ACCOUNT,
}

#: Session 37's key vocabulary: exactly the scopes a Session 37 route checks
#: (D2052) -- the control set's `control_keys.scopes` CHECK lists the same
#: four. Each later session adds its own with its route (`projects:write`, 38).
KEY_VOCABULARY: Final[tuple[str, ...]] = (
    "members:read",
    "operations:read",
    "organizations:read",
    "projects:read",
)

#: What each role grants a KEY its member holds. **Identical for every role in
#: Session 37** -- D2053 gives viewer and member the same reads and admin and
#: owner add only human acts -- so the intersection below narrows nothing yet;
#: Session 38 gives `member` `projects:write` and it starts to (D2109).
ROLE_SCOPES: Final[dict[str, frozenset[str]]] = {role: frozenset(KEY_VOCABULARY) for role in ROLES}

#: The routes a key may reach, and the scope each needs. **A route absent here
#: is human-session only** (`403 human_session_required`): every credential-
#: minting route -- keys, invitations, the second factor, role changes -- and
#: oneself (D2052). So a leaked key cannot mint its own successor.
KEY_SCOPES: Final[dict[str, str]] = {
    "list_organizations": "organizations:read",
    "get_organization": "organizations:read",
    "list_members": "members:read",
    "list_projects": "projects:read",
    "get_project": "projects:read",
    "list_operations": "operations:read",
    "get_operation": "operations:read",
}


def effective_scopes(key_scopes: list[str], role: str | None) -> frozenset[str]:
    """A key's scopes as they are NOW: its own, intersected with what its
    owner's CURRENT role grants. Empty for an owner who left (D2052)."""
    if role is None:
        return frozenset()
    return frozenset(key_scopes) & ROLE_SCOPES[role]


#: A membership invitation is minted by an `admin` or `owner` of the
#: organisation it names, for a role at or below their own -- only an `owner`
#: invites an `owner` (D2051). The body names the organisation, so the
#: handler applies this rank rather than the guard.
MEMBERSHIP_INVITATION: Final = "admin"

#: An ACCOUNT invitation (no organisation) is minted by the control project's
#: registry administrator: the scope, never a role name (API-ADMIN-001's rule),
#: and -- because it is in `factor_required`'s list -- only with an enabled
#: second factor (D2051, D2099).
ACCOUNT_INVITATION_SCOPE: Final = scope_map.ADMIN_USERS_WRITE

#: The routes a person who must hold a second factor and has not enrolled one
#: may still reach (D2050): themselves and enrolment. Every other
#: authenticated route answers `403 second_factor_required`.
ENROLMENT_ROUTES: Final[frozenset[str]] = frozenset({"me", "begin_factor", "confirm_factor"})

#: Who must hold a second factor: anyone holding one of these roles in ANY
#: organisation, or the registry administrator's scope (D2050).
FACTOR_ROLES: Final[frozenset[str]] = frozenset({"owner", "admin"})


def factor_required(roles: dict[str, str], scopes: list[str]) -> bool:
    """Whether this person must have an enabled factor to use the plane."""
    return bool(FACTOR_ROLES & set(roles.values())) or ACCOUNT_INVITATION_SCOPE in scopes


def may_grant(minter: str, role: str) -> bool:
    """Whether a member holding `minter` may invite someone as, or set someone
    to, `role`: an admin up to admin, only an owner to owner (D2053)."""
    if role == "owner":
        return minter == "owner"
    return rank(minter) >= rank(MEMBERSHIP_INVITATION)
