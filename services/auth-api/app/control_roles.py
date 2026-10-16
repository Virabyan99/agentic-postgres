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

Session 37's Run 5 added the keys, projects and operations routes; Session 38
adds the project writes and the cancel (D2165), each an `ACCOUNT` entry here
because the organisation is read from the body or the project row, with the
role it needs in `PROJECT_WRITES`, which the handler applies.
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
    # Session 38 (D2165): the writes. The role each needs is PROJECT_WRITES'.
    "sleep_project": ACCOUNT,
    "wake_project": ACCOUNT,
    "resize_project": ACCOUNT,
    "export_project": ACCOUNT,
    "delete_project": ACCOUNT,
    "cancel_operation": ACCOUNT,
    # Session 39 (ADR 0268, ADR 0269): a project's public doors and its
    # customer credentials. The organisation is read from the project row; the
    # read needs `viewer`, the write PROJECT_WRITES'.
    "get_connections": ACCOUNT,
    "rotate_credential": ACCOUNT,
    # Session 40 (ADR 0271, ADR 0273): a project's branches and its backups.
    # The organisation is read from the project row; the reads need `viewer`,
    # the writes PROJECT_WRITES'.
    "list_branches": ACCOUNT,
    "get_branch": ACCOUNT,
    "get_backups": ACCOUNT,
    "create_branch": ACCOUNT,
    "create_restore": ACCOUNT,
    "reset_branch": ACCOUNT,
    "delete_branch": ACCOUNT,
    # Session 41 (ADR 0274-0276): the plans any account reads; an
    # organisation's plan, usage and notifications any member; *Notify me*
    # and a project's idle-sleep setting member and above (SETTING_WRITES).
    "list_plans": ACCOUNT,
    "get_organization_plan": "viewer",
    "register_plan_interest": "viewer",
    "get_organization_usage": "viewer",
    "list_notifications": "viewer",
    "get_project_usage": ACCOUNT,
    "set_idle_sleep": ACCOUNT,
}

#: Session 41: the two writes that are SETTINGS, not operations -- no row of
#: `control_operations`, so not in PROJECT_WRITES (whose every entry requests
#: an executed type, `test_every_write_route_has_a_role_and_a_type`) -- and the
#: role each needs. The control set checks the same ranks again.
SETTING_WRITES: Final[dict[str, str]] = {
    "register_plan_interest": "member",
    "set_idle_sleep": "member",
}

#: Session 38's writes (D2165, ADR 0256) -> the role they need in the
#: organisation the body names (create) or the project belongs to. The control
#: set's `control_request_operation` checks the same ranks again in SQL.
#: Cancelling needs `viewer` plus being the requester, or `admin` (D2067) --
#: the definer function decides which.
PROJECT_WRITES: Final[dict[str, str]] = {
    "create_project": "member",
    "sleep_project": "member",
    "wake_project": "member",
    "resize_project": "member",
    "export_project": "member",
    "delete_project": "admin",
    "cancel_operation": "viewer",
    # Session 39 (ADR 0269): member and above, as every write but deletion.
    "rotate_credential": "member",
    # Session 40 (ADR 0271, D2436): a branch's deletion is admin, as a
    # project's; its creation, restore and reset member.
    "create_branch": "member",
    "create_restore": "member",
    "reset_branch": "member",
    "delete_branch": "admin",
}

#: Each write route -> the operation type it requests.
OPERATION_OF_ROUTE: Final[dict[str, str]] = {
    "create_project": "project.create",
    "sleep_project": "project.sleep",
    "wake_project": "project.wake",
    "resize_project": "project.resize",
    "export_project": "project.export",
    "delete_project": "project.delete",
    "rotate_credential": "credential.rotate",
    "create_branch": "branch.create",
    "create_restore": "restore.create",
    "reset_branch": "branch.reset",
    "delete_branch": "branch.delete",
}

#: The key vocabulary: exactly the scopes a route checks (D2052) -- the control
#: set's `control_keys.scopes` CHECK lists the same five. Session 38 added
#: `projects:write` with the routes that read it (D2165).
KEY_VOCABULARY: Final[tuple[str, ...]] = (
    "members:read",
    "operations:read",
    "organizations:read",
    "projects:read",
    "projects:write",
)

#: The reads every role grants (D2053).
_READS: Final[frozenset[str]] = frozenset(
    {"members:read", "operations:read", "organizations:read", "projects:read"}
)

#: What each role grants a KEY its member holds: `viewer` reads, `member` and
#: above also write (D2165). Since Session 38 the intersection below narrows:
#: a viewer's key holding `projects:write` holds nothing it can use (D2109).
ROLE_SCOPES: Final[dict[str, frozenset[str]]] = {
    "viewer": _READS,
    "member": _READS | {"projects:write"},
    "admin": _READS | {"projects:write"},
    "owner": _READS | {"projects:write"},
}

#: The routes a key may reach, and the scope each needs. **A route absent here
#: is human-session only** (`403 human_session_required`): every credential-
#: minting route -- keys, invitations, the second factor, role changes -- and
#: oneself (D2052). So a leaked key cannot mint its own successor. Of Session
#: 38's writes a key reaches only sleep, wake and resize: creating a project
#: starts its administrator's handoff, an export yields a download URL, and a
#: deletion destroys -- a person does each (D2165).
KEY_SCOPES: Final[dict[str, str]] = {
    "list_organizations": "organizations:read",
    "get_organization": "organizations:read",
    "list_members": "members:read",
    "list_projects": "projects:read",
    "get_project": "projects:read",
    "list_operations": "operations:read",
    "get_operation": "operations:read",
    "sleep_project": "projects:write",
    "wake_project": "projects:write",
    "resize_project": "projects:write",
    # Session 39: the doors' metadata, which names no secret, is a read. Setting
    # a credential is NOT here: a person does it (ADR 0269), so a leaked key
    # can never replace the customer's database credential with its own.
    "get_connections": "projects:read",
    # Session 40: a project's branches and its backups reading name no secret,
    # so they are reads. NO branch write is here (D2468): a creation, a restore
    # and a reset each carry the branch's own credentials, so a key that could
    # request one could make itself a door to a full copy of the data -- the
    # export case and the credential case at once. A person does each, and a
    # deletion too, as a project's.
    "list_branches": "projects:read",
    "get_branch": "projects:read",
    "get_backups": "projects:read",
    # Session 41 (ADR 0274-0276): plans, an organisation's plan and its
    # notifications are reads of the organisation; usage a read of its
    # projects; the idle-sleep setting a project write -- it changes when a
    # project sleeps, as `sleep_project` does. *Notify me* is NOT here: a
    # person asks.
    "list_plans": "organizations:read",
    "get_organization_plan": "organizations:read",
    "list_notifications": "organizations:read",
    "get_organization_usage": "projects:read",
    "get_project_usage": "projects:read",
    "set_idle_sleep": "projects:write",
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
