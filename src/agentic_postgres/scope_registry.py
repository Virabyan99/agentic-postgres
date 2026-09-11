"""The scope vocabulary, derived, and the role ceiling over it (ADR 0079, ADR 0200).

**The data class is a function of a reviewed surface** (ADR 0200):
`<relation>:read` and `<relation>:write` for every relation the surface
publishes, plus `meta:read` for schema introspection. The storage and
administrative classes stay ENUMERATED in `schemas/capabilities.schema.json`,
exactly as ADR 0100 left them. The schema is still the sole authority for what
it enumerates and for the *shape* of the third class (ADR 0006); the reviewed
surface -- `contracts/postgrest-api-surface.yaml`, merged with a project's own
under ADR 0198 -- is the authority for the third class's members, and it
changes on a reviewed edit and on nothing else (D1135).

**This is a mapping, not a vocabulary.** The role ceiling says which CLASSES a
token naming a role may carry (`ROLE_CLASSES`, the one declaration, in the
service's build context); the ceiling itself is computed from the vocabulary of
a deployment, never written out. No data-scope literal survives outside the
schema and the example manifest, and a test says so.

**Where the vocabulary reaches the issuer.** The service cannot read the
schema or the surface (ADR 0084), so the compiler writes the vocabulary into
the lock (`vocabulary_block`) and the auth container mounts the lock (D1126).
This module is the half that needs the schema and the surface; the service's
`scopes.py` is the half that turns a vocabulary into a ceiling.

**A role that no token may name is absent, and asking about one raises.**
`bin/dev-token.py` makes the same choice for the same reason, in its own words:
"a command that offers the option invites somebody to find out."
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from agentic_postgres import api_surface, config, service_source
from agentic_postgres.config import ManifestError

_scopes = service_source.load("scopes")

__all__ = [
    "ROLE_CLASSES",
    "administrative_scopes",
    "agent_requestable_scopes",
    "approved_scopes",
    "assert_classes_partition_the_vocabulary",
    "assert_scopes_permitted",
    "enumerated_agent_scopes",
    "permitted_scopes",
    "storage_scopes",
    "vocabulary",
    "vocabulary_block",
]


def vocabulary(surface: dict[str, Any]) -> frozenset[str]:
    """The data class a reviewed surface derives (ADR 0200).

    Pure over its argument: a surface document, never a path, a URL or a
    served OpenAPI document (D1135). `merged_surface(release, project)` is what
    a project's deployment passes; the release surface alone is what every
    other reader passes.
    """
    names = {_scopes.INTROSPECTION_SCOPE}
    for relation in surface["relations"]:
        names.add(f"{relation}:read")
        names.add(f"{relation}:write")
    return frozenset(names)


@lru_cache(maxsize=1)
def _release_surface() -> dict[str, Any]:
    return api_surface.load_surface()


def _surface(surface: dict[str, Any] | None) -> dict[str, Any]:
    # The RELEASE surface is the default, and it means "the release's
    # relations": every reader that wants a deployment's vocabulary passes the
    # merged surface explicitly (ADR 0198's rule for a kept default).
    return _release_surface() if surface is None else surface


@lru_cache(maxsize=1)
def enumerated_agent_scopes() -> frozenset[str]:
    """`$defs/agent_scope`: the data class a manifest at capability schema 3 or
    below may name. A subset of every derived vocabulary, because the release's
    relations always exist; asserted in :func:`assert_classes_partition_the_vocabulary`."""
    return frozenset(config.load_schema("capabilities.schema.json")["$defs"]["agent_scope"]["enum"])


@lru_cache(maxsize=1)
def storage_scopes() -> frozenset[str]:
    """The object-storage class (ADR 0100). Enumerated in the schema, never derived."""
    return frozenset(
        config.load_schema("capabilities.schema.json")["$defs"]["storage_scope"]["enum"]
    )


@lru_cache(maxsize=1)
def administrative_scopes() -> frozenset[str]:
    """The class a capability manifest may not request (ADR 0079, ADR 0100).

    Read from the schema, not derived, and that is ADR 0100's correction to
    ADR 0079: a complement is correct for exactly two classes and silently
    wrong for three. :func:`assert_classes_partition_the_vocabulary` is what
    makes the enumeration safe.
    """
    return frozenset(
        config.load_schema("capabilities.schema.json")["$defs"]["administrative_scope"]["enum"]
    )


def agent_requestable_scopes(surface: dict[str, Any] | None = None) -> frozenset[str]:
    """The data class for a surface: what a manifest may declare in ``required_scopes``."""
    return vocabulary(_surface(surface))


def approved_scopes(surface: dict[str, Any] | None = None) -> frozenset[str]:
    """Every name a deployment on `surface` admits: the three classes' union."""
    return agent_requestable_scopes(surface) | storage_scopes() | administrative_scopes()


def assert_classes_partition_the_vocabulary(surface: dict[str, Any] | None = None) -> None:
    """The three classes are disjoint and cover exactly what they should.

    Two relations, and both are kept (ADR 0100, ADR 0200):

    1. **The schema's own enums partition `$defs/scope`** -- the ≤3 data class,
       the storage class and the administrative class are disjoint and their
       union is exactly the enumerated union. A name added to `$defs/scope` and
       to no class **fails here**, with a message naming it, instead of being
       absorbed into whichever class was derived by subtraction.
    2. **The derived data class for this surface** is disjoint from the two
       enumerated classes -- `api_surface` refuses a reserved relation name at
       load and at merge, and this is the check behind that refusal -- and, for
       the release surface, still contains every name the ≤3 enum lets an older
       manifest declare, so nothing a deployed manifest names has stopped
       existing under it.

    Raises rather than reporting: the callers are the issuer and the
    repository's own registry reads, and a vocabulary whose classes do not
    partition it is not a condition to carry forward.
    """
    enumerated = frozenset(config.load_schema("capabilities.schema.json")["$defs"]["scope"]["enum"])
    classes = {
        "$defs/agent_scope": enumerated_agent_scopes(),
        "$defs/storage_scope": storage_scopes(),
        "$defs/administrative_scope": administrative_scopes(),
    }

    for name, members in classes.items():
        outside = members - enumerated
        if outside:
            raise ManifestError(
                f"{name} names {sorted(outside)}, which $defs/scope does not admit. "
                "The union is the sole authority (ADR 0006) and a class is a subset of "
                "it, never an extension"
            )

    names = sorted(classes)
    for index, first in enumerate(names):
        for second in names[index + 1 :]:
            overlap = classes[first] & classes[second]
            if overlap:
                raise ManifestError(
                    f"{sorted(overlap)} are in both {first} and {second}. The classes are "
                    "disjoint by ADR 0100: a scope belongs to one class, and a name in two "
                    "of them means one of the two decisions was never made"
                )

    unclassified = enumerated - set().union(*classes.values())
    if unclassified:
        raise ManifestError(
            f"$defs/scope admits {sorted(unclassified)} and no class claims them. Before "
            "ADR 0100 they would have been classified ADMINISTRATIVE by complement -- a "
            "decision arithmetic made rather than one anybody wrote down. Add each name "
            "to the class it belongs to, and if that class does not exist yet, it needs "
            "an ADR before it needs an enum"
        )

    derived = vocabulary(_surface(surface))
    for name, members in (
        ("$defs/storage_scope", storage_scopes()),
        ("$defs/administrative_scope", administrative_scopes()),
    ):
        overlap = derived & members
        if overlap:
            raise ManifestError(
                f"the reviewed surface derives {sorted(overlap)}, which {name} already names. "
                "A relation may not be named for a storage or administrative resource; "
                "api_surface refuses one at load and at merge, and this is the check behind "
                "that refusal (ADR 0200)"
            )
    if surface is None:
        missing = enumerated_agent_scopes() - derived
        if missing:
            raise ManifestError(
                f"the release surface no longer derives {sorted(missing)}, which a manifest "
                "at capability schema 3 or below may still name. The release's relations "
                "are the floor of every vocabulary (ADR 0200)"
            )


#: Re-exported from the service's build context, which is the one
#: declaration (ADR 0084). Assigned rather than restated: a copy here would
#: be two authorities for one authorization model, and D175 records that a
#: test comparing two constants goes green again the moment somebody
#: regenerates the copy. Values are CLASS names, never scope names.
ROLE_CLASSES: dict[str, frozenset[str]] = _scopes.ROLE_CLASSES


def vocabulary_block(surface: dict[str, Any] | None = None) -> dict[str, list[str]]:
    """The block the compiler writes into a lock and the issuer reads out of it.

    Three sorted lists under the three class names. The data list INCLUDES
    `meta:read`, because it is what a manifest may request; the service's
    `ceiling` is what keeps introspection out of a human's ceiling.
    """
    return {
        _scopes.DATA: sorted(agent_requestable_scopes(surface)),
        _scopes.STORAGE: sorted(storage_scopes()),
        _scopes.ADMINISTRATIVE: sorted(administrative_scopes()),
    }


def permitted_scopes(role_suffix: str, surface: dict[str, Any] | None = None) -> frozenset[str]:
    """The ceiling for one role over a surface's vocabulary.

    The partition check runs first, and before the role lookup, because it is
    a statement about the vocabulary rather than about this call: a vocabulary
    whose classes do not partition it is wrong for every role, and answering
    one question correctly out of a broken vocabulary is how the
    misclassification ADR 0100 describes stayed invisible.
    """
    assert_classes_partition_the_vocabulary(surface)

    if role_suffix not in ROLE_CLASSES:
        raise ManifestError(
            f"no token may name the role {role_suffix!r}. The roles a token may name are "
            f"{sorted(ROLE_CLASSES)}; the rest are service identities, and offering one as "
            "an option invites somebody to find out what it can do"
        )

    block = {name: frozenset(members) for name, members in vocabulary_block(surface).items()}
    scopes = _scopes.ceiling(role_suffix, block)
    if scopes is None:  # pragma: no cover -- the membership test above refuses first
        raise ManifestError(f"no token may name the role {role_suffix!r}")
    unapproved = scopes - approved_scopes(surface)
    if unapproved:  # pragma: no cover -- a ceiling is computed from the classes it names
        raise ManifestError(
            f"the ceiling for {role_suffix} names {sorted(unapproved)}, which the vocabulary "
            "does not admit"
        )
    return scopes


def assert_scopes_permitted(
    role_suffix: str, scopes: list[str], surface: dict[str, Any] | None = None
) -> frozenset[str]:
    """The check an issuer runs before signing. Returns the set it validated.

    Refuses an empty list as well as an over-wide one. A token with no scopes for
    a role that has a ceiling is not a safe default -- it is a token whose
    authority nothing described, and `verify_claims` requires the claim to be
    present.
    """
    ceiling = permitted_scopes(role_suffix, surface)

    if not isinstance(scopes, list) or not all(isinstance(item, str) for item in scopes):
        raise ManifestError("scopes must be a list of strings")

    requested = frozenset(scopes)
    if len(requested) != len(scopes):
        raise ManifestError(f"the requested scopes repeat an entry: {scopes}")

    if not ceiling:
        if requested:
            raise ManifestError(
                f"a token naming {role_suffix} may carry no scopes, and {sorted(requested)} "
                "were requested"
            )
        return requested

    if not requested:
        raise ManifestError(
            f"a token naming {role_suffix} must carry at least one scope; its authority "
            "would otherwise be described by nothing"
        )

    excess = requested - ceiling
    if excess:
        raise ManifestError(
            f"a token naming {role_suffix} may not carry {sorted(excess)}; its ceiling is "
            f"{sorted(ceiling)}"
        )
    return requested
