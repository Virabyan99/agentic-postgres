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
    # write side. Both memberships are activated as of Session 9 Run 2
    # (ADR 0116, ADR 0137).
    #
    # No `objects:*`, and this is the second of the two places Session 7's
    # human-only property is written -- the schema's $ref being the first. An
    # agent's ceiling not containing a scope and a manifest being unable to
    # request it are different guarantees, and the storage surface wants both.
    #
    # **`meta:read` is in BOTH agent ceilings** (ADR 0138). It was absent from
    # the writer's until Session 9 Run 2, which would have left a write-capable
    # agent unable to call either metadata tool -- so it could be authorized to
    # change rows and unable to ask which rows it may change. Introspection is a
    # scope precisely so it is granted per subject rather than implied by being
    # an agent; leaving it out of the ceiling made it unrequestable instead,
    # which is a different thing from withholding it.
    "agent_reader": frozenset({"notes:read", "tasks:read", "meta:read"}),
    "agent_writer": frozenset(
        {"notes:read", "notes:write", "tasks:read", "tasks:write", "meta:read"}
    ),
    # An administrator is also a user, so the ceiling is the union rather than
    # the administrative class alone. The role does not imply any of it.
    #
    # **`admin_audit:read` is in THIS ceiling and in no other** (ADR 0142). It
    # is not in either agent ceiling, and that is the same kind of statement as
    # `objects:*` being human-only: an agent must not read the record that
    # exists to attribute it. ADR 0135's stated residual threat is that an agent
    # can add noise to its own record under a true identity; reading the record
    # back is not part of that threat and must not become part of it by way of a
    # ceiling that would admit the scope.
    #
    # There is no `admin_audit:write` twin. `app_private.agent_audit` is
    # append-only -- its own COMMENT says no role holds INSERT, UPDATE, DELETE
    # or SELECT on it and the definer functions are the only paths in -- so a
    # write scope here would name an authority nothing can exercise.
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
            "admin_audit:read",
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

#: Session 9's administrative scope (ADR 0142), gating `GET /admin/audit`.
#:
#: A separate name from `ADMIN_AGENTS_READ` rather than a reuse of it, and the
#: two are not the same authority: `admin_agents:read` lists WHICH agents exist
#: and what they may do, and this one reads WHAT THEY DID -- parameters
#: included, redacted by the capability lock rather than by this service. An
#: operator who should see the roster is not thereby an operator who should see
#: every audited call, and a reuse would have made that one decision taken once,
#: by whoever first granted the roster scope.
ADMIN_AUDIT_READ = "admin_audit:read"

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
