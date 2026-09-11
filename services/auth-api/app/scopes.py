"""Which CLASSES of scope a role's token may carry, and the ceiling over a
deployment's vocabulary (ADR 0079, ADR 0200), in the build context that needs it.

**This module holds the mapping and nothing else.** It names no data scope.
The data class is derived from the reviewed surface by
`agentic_postgres.scope_registry` and written into the capability lock by the
compiler; this container mounts the lock and reads the vocabulary out of it at
startup (D1126). The schema and the surface are not in the image's build
context, and dragging either in would drag `config.py` with it.

So the division is: `ROLE_CLASSES` says which classes a role's token may carry,
`load_vocabulary` reads what the classes contain for THIS deployment, and
`ceiling` computes the largest set a token naming a role may hold. What a
subject actually holds comes from a server-side record, which is the whole
point of `API-ADMIN-001`: an administrator without the scope is refused, so the
role never implies the scope.

Standard library only (ADR 0084).
"""

from __future__ import annotations

import json
from pathlib import Path

__all__ = [
    "ADMINISTRATIVE",
    "DATA",
    "DATA_READ",
    "INTROSPECTION",
    "INTROSPECTION_SCOPE",
    "ROLE_CLASSES",
    "STORAGE",
    "VOCABULARY_CLASSES",
    "VocabularyError",
    "ceiling",
    "load_vocabulary",
]

#: The three lists a lock's `vocabulary` block carries (the compiler writes
#: them; `scope_registry.vocabulary_block` is the writer's half).
DATA = "data"
STORAGE = "storage"
ADMINISTRATIVE = "administrative"
VOCABULARY_CLASSES: tuple[str, ...] = (DATA, STORAGE, ADMINISTRATIVE)

#: Two views over the data list that a role may be granted instead of the
#: whole of it: the `:read` half, and introspection alone.
DATA_READ = "data_read"
INTROSPECTION = "introspection"

#: The one data scope that is not derived from a relation: schema
#: introspection, which `list_resources` and `describe_resource` require. It is
#: in every derived data class and in no human's ceiling.
INTROSPECTION_SCOPE = "meta:read"

#: Role suffix -> the classes a token naming that role may carry.
#:
#: Keys are suffixes from `naming.ROLE_SUFFIXES`, not derived role names: the
#: mapping is a property of the *kind* of identity, and a per-project role name
#: would make this a per-project authorization model -- which ADR 0006 rejected
#: by name. Values are class names, never scope names (ADR 0200).
ROLE_CLASSES: dict[str, frozenset[str]] = {
    # No scopes at all. An anonymous caller's authority is its grants, and a
    # scope claim on an anonymous token would be a claim about a subject there
    # is no record of.
    "anon": frozenset(),
    # A human user of the application: every data scope the deployment
    # derives, and object storage (ADR 0100). Not introspection -- reading the
    # shape of the API is the documentation role's and the agents'.
    #
    # Object storage is human-only, and where that is ENFORCED is the
    # capability schema's binding of `required_scopes` to the data class --
    # which the storage class is deliberately absent from -- not here. A
    # ceiling says what a token naming this role may carry; it cannot say what
    # a capability manifest may ask for, and ADR 0006's whole argument is that
    # those must not be the same list.
    "authenticated": frozenset({DATA, STORAGE}),
    # Exactly introspection, and ADR 0049's reasoning is unchanged: reading the
    # shape of the API and none of its data.
    "api_documentation": frozenset({INTROSPECTION}),
    # Agents, whose ceiling is deliberately narrower than the human's on the
    # write side. Both memberships are activated as of Session 9 Run 2
    # (ADR 0116, ADR 0137).
    #
    # No storage, and this is the second of the two places Session 7's
    # human-only property is written -- the schema's binding being the first.
    # An agent's ceiling not containing a scope and a manifest being unable to
    # request it are different guarantees, and the storage surface wants both.
    #
    # **Introspection is in BOTH agent ceilings** (ADR 0138). It was absent
    # from the writer's until Session 9 Run 2, which would have left a
    # write-capable agent unable to call either metadata tool -- so it could
    # be authorized to change rows and unable to ask which rows it may change.
    "agent_reader": frozenset({DATA_READ, INTROSPECTION}),
    "agent_writer": frozenset({DATA, INTROSPECTION}),
    # An administrator is also a user, so the ceiling is the union rather than
    # the administrative class alone. The role does not imply any of it.
    #
    # **`admin_audit:read` is in THIS ceiling and in no other** (ADR 0142). It
    # is not in either agent ceiling, and that is the same kind of statement as
    # object storage being human-only: an agent must not read the record that
    # exists to attribute it. There is no `admin_audit:write` twin, because
    # `app_private.agent_audit` is append-only and the definer functions are
    # the only paths in.
    "project_admin": frozenset({DATA, STORAGE, ADMINISTRATIVE}),
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
OBJECTS_READ = "objects:read"
OBJECTS_WRITE = "objects:write"


class VocabularyError(ValueError):
    """The lock carries no vocabulary this issuer can bound a scope with.

    Raised at startup, so an issuer that could not say what a token may carry
    never issues one: a container that started and refused every grant would
    look deployed (ADR 0113's reason, applied to the ceiling).
    """


def load_vocabulary(path: Path | str) -> dict[str, frozenset[str]]:
    """The three classes, read out of the mounted capability lock (D1126).

    Strict, because this decides what a token may carry: each of the three
    lists must be present, be a list of strings, and be sorted and free of
    repeats -- the shape the compiler writes -- and introspection must be in
    the data list, or every agent would be unable to request it.
    """
    try:
        document = json.loads(Path(path).read_bytes())
    except OSError as error:
        raise VocabularyError(f"the capability lock cannot be read: {error}") from error
    except ValueError as error:
        raise VocabularyError(f"the capability lock is not JSON: {error}") from error

    block = document.get("vocabulary") if isinstance(document, dict) else None
    if not isinstance(block, dict):
        raise VocabularyError(
            "the capability lock carries no vocabulary block; this issuer reads its "
            "ceilings from the lock since ADR 0200 and this lock predates it -- redeploy"
        )
    if set(block) != set(VOCABULARY_CLASSES):
        raise VocabularyError(
            f"the lock's vocabulary names {sorted(block)}; the classes are "
            f"{list(VOCABULARY_CLASSES)}"
        )
    classes: dict[str, frozenset[str]] = {}
    for name in VOCABULARY_CLASSES:
        members = block[name]
        if not isinstance(members, list) or not all(isinstance(m, str) for m in members):
            raise VocabularyError(f"the lock's vocabulary.{name} is not a list of strings")
        if members != sorted(set(members)):
            raise VocabularyError(f"the lock's vocabulary.{name} is not sorted and deduplicated")
        classes[name] = frozenset(members)
    if INTROSPECTION_SCOPE not in classes[DATA]:
        raise VocabularyError(
            f"the lock's vocabulary.data lacks {INTROSPECTION_SCOPE}; no agent could then "
            "be granted introspection (ADR 0138)"
        )
    for first, second in ((DATA, STORAGE), (DATA, ADMINISTRATIVE), (STORAGE, ADMINISTRATIVE)):
        overlap = classes[first] & classes[second]
        if overlap:
            raise VocabularyError(
                f"the lock's vocabulary names {sorted(overlap)} in both {first} and {second}"
            )
    return classes


def ceiling(role_suffix: str, vocabulary: dict[str, frozenset[str]]) -> frozenset[str] | None:
    """The ceiling for one role over a vocabulary, or None when no token may name it.

    Returns rather than raises, because the two callers want different things:
    the repository raises with a message naming both authorities, and the
    service refuses the request.
    """
    classes = ROLE_CLASSES.get(role_suffix)
    if classes is None:
        return None
    data = frozenset(vocabulary[DATA]) - {INTROSPECTION_SCOPE}
    names: set[str] = set()
    if DATA in classes:
        names |= data
    if DATA_READ in classes:
        names |= {scope for scope in data if scope.endswith(":read")}
    if INTROSPECTION in classes:
        names.add(INTROSPECTION_SCOPE)
    if STORAGE in classes:
        names |= frozenset(vocabulary[STORAGE])
    if ADMINISTRATIVE in classes:
        names |= frozenset(vocabulary[ADMINISTRATIVE])
    return frozenset(names)
