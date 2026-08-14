"""The scope ceiling per role (ADR 0079), in the build context that needs it.

**This module holds the mapping and nothing else.** The *vocabulary* it maps
onto is `schemas/capabilities.schema.json`, which ADR 0006 makes the sole
authority and which this file may not read -- the schema is not in the image's
build context, and dragging it in would drag `config.py` with it.

So the division is: this file says which scopes a role's token may carry, and
`agentic_postgres.scope_registry` -- which can read the schema -- checks that
every name here is one the schema admits, on the way out. A name added here that
the schema does not know is an error the moment the repository reads the
registry, which is before any deployment could carry it.

Standard library only (ADR 0084).
"""

from __future__ import annotations

__all__ = ["ROLE_SCOPES", "ceiling"]

#: Role suffix -> the largest scope set a token naming that role may carry.
#:
#: Keys are suffixes from `naming.ROLE_SUFFIXES`, not derived role names: the
#: mapping is a property of the *kind* of identity, and a per-project role name
#: would make this a per-project authorization model -- which ADR 0006 rejected
#: by name.
#:
#: This decides the CEILING. It does not decide what any particular subject
#: holds, which comes from a server-side record and is the whole point of
#: `API-ADMIN-001`: an administrator without the scope is refused, so the role
#: never implies the scope.
ROLE_SCOPES: dict[str, frozenset[str]] = {
    # No scopes at all. An anonymous caller's authority is its grants, and a
    # scope claim on an anonymous token would be a claim about a subject there
    # is no record of.
    "anon": frozenset(),
    # A human user of the application. A given token carries whatever the
    # server-side record says; this is the ceiling.
    "authenticated": frozenset({"notes:read", "notes:write", "tasks:read", "tasks:write"}),
    # Exactly introspection, and ADR 0049's reasoning is unchanged: reading the
    # shape of the API and none of its data.
    "api_documentation": frozenset({"meta:read"}),
    # Agents, whose ceiling is deliberately narrower than the human's on the
    # write side. Session 9 activates the role memberships; until then a token
    # naming one is refused at role switching, which is a tested property.
    "agent_reader": frozenset({"notes:read", "tasks:read", "meta:read"}),
    "agent_writer": frozenset({"notes:read", "notes:write", "tasks:read", "tasks:write"}),
    # An administrator is also a user, so the ceiling is the union rather than
    # the administrative class alone. The role does not imply any of it.
    "project_admin": frozenset(
        {
            "notes:read",
            "notes:write",
            "tasks:read",
            "tasks:write",
            "admin_users:read",
            "admin_users:write",
            "admin_agents:read",
            "admin_agents:write",
        }
    ),
}

#: The scope an administrative write requires. Named here so that the endpoint,
#: the registry and the test read one string: `API-ADMIN-001` is precisely the
#: claim that a `project_admin` **without this scope** is refused, so a route
#: that checked the role instead would pass every test that only ever issued
#: tokens to real administrators.
ADMIN_USERS_WRITE = "admin_users:write"
ADMIN_USERS_READ = "admin_users:read"
ADMIN_AGENTS_WRITE = "admin_agents:write"
ADMIN_AGENTS_READ = "admin_agents:read"


def ceiling(role_suffix: str) -> frozenset[str] | None:
    """The ceiling for one role, or None when no token may name it.

    Returns rather than raises, because the two callers want different things:
    the repository raises with a message naming both authorities, and the
    service refuses the request.
    """
    return ROLE_SCOPES.get(role_suffix)
