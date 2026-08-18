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
    #
    # `objects:*` since Session 7 (ADR 0100). Object storage is human-only, and
    # where that is ENFORCED is `required_scopes`' $ref to $defs/agent_scope --
    # which the storage class is deliberately absent from -- not here. A ceiling
    # says what a token naming this role may carry; it cannot say what a
    # capability manifest may ask for, and ADR 0006's whole argument is that
    # those must not be the same list.
    "authenticated": frozenset(
        {
            "notes:read",
            "notes:write",
            "tasks:read",
            "tasks:write",
            "objects:read",
            "objects:write",
        }
    ),
    # Exactly introspection, and ADR 0049's reasoning is unchanged: reading the
    # shape of the API and none of its data.
    "api_documentation": frozenset({"meta:read"}),
    # Agents, whose ceiling is deliberately narrower than the human's on the
    # write side. Session 9 activates the role memberships; until then a token
    # naming one is refused at role switching, which is a tested property.
    #
    # No `objects:*`, and this is the second of the two places Session 7's
    # human-only property is written -- the schema's $ref being the first. An
    # agent's ceiling not containing a scope and a manifest being unable to
    # request it are different guarantees, and the storage surface wants both.
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
            "objects:read",
            "objects:write",
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

#: Session 7's storage class (ADR 0100), named here for the same reason as the
#: four above: the endpoint, the registry and the test read one string.
#:
#: Both are in the `authenticated` and `project_admin` ceilings above and in
#: **neither agent ceiling**, which is one of the two places object storage's
#: human-only property is written -- the other being `$defs/agent_scope`, which
#: `required_scopes` refs and which the storage class is absent from. A ceiling
#: says what a token may carry; the schema says what a manifest may ask for.
#: Session 7 wants both, so removing either does not silently open the surface.
OBJECTS_READ = "objects:read"
OBJECTS_WRITE = "objects:write"


def ceiling(role_suffix: str) -> frozenset[str] | None:
    """The ceiling for one role, or None when no token may name it.

    Returns rather than raises, because the two callers want different things:
    the repository raises with a message naming both authorities, and the
    service refuses the request.
    """
    return ROLE_SCOPES.get(role_suffix)
