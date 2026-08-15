"""Which scopes a token for a given role may carry (ADR 0079).

**This is a mapping, not a vocabulary.** Every name here is checked against
`schemas/capabilities.schema.json`, which ADR 0006 makes the sole authority and
which says of itself that "the code carries no second copy". A name in this file
that the schema does not admit is an error at the moment it is read, not a scope
that quietly works.

ADR 0049 already stated most of this in prose -- a reader token holds a subset of
the `:read` scopes, the documentation role holds exactly `meta:read` -- and prose
is not something a token can be checked against. This is the same statement as
data.

**What this file decides and what it does not.** It decides the *ceiling*: the
largest set a token naming a role may carry. It does not decide what any
particular subject holds, which comes from a server-side record and is the whole
point of `API-ADMIN-001` -- an administrator without the scope is refused, so the
role never implies the scope.

**A role that no token may name is absent, and asking about one raises.**
`bin/dev-token.py` makes the same choice for the same reason, in its own words:
"a command that offers the option invites somebody to find out."

**The mapping itself lives in `services/auth-api/app/scopes.py`** (ADR 0084),
because the issuer needs it and the image's build context cannot reach `src/`.
What stays here is the half that needs the schema: every name the mapping grants
is checked against `capabilities.schema.json` on the way out, so a scope added
to the service that the schema does not admit fails the moment the repository
reads the registry -- which is before any deployment could carry it.
"""

from __future__ import annotations

from functools import lru_cache

from agentic_postgres import config, service_source
from agentic_postgres.config import ManifestError

_scopes = service_source.load("scopes")

__all__ = [
    "ROLE_SCOPES",
    "administrative_scopes",
    "agent_requestable_scopes",
    "approved_scopes",
    "assert_classes_partition_the_vocabulary",
    "assert_scopes_permitted",
    "permitted_scopes",
    "storage_scopes",
]


@lru_cache(maxsize=1)
def approved_scopes() -> frozenset[str]:
    """Every name the schema admits, all three classes. Loaded, never restated."""
    return frozenset(config.load_schema("capabilities.schema.json")["$defs"]["scope"]["enum"])


@lru_cache(maxsize=1)
def agent_requestable_scopes() -> frozenset[str]:
    """The subset a capability manifest may declare in ``required_scopes``."""
    return frozenset(config.load_schema("capabilities.schema.json")["$defs"]["agent_scope"]["enum"])


@lru_cache(maxsize=1)
def storage_scopes() -> frozenset[str]:
    """The object-storage class (ADR 0100).

    Listed in the schema rather than derived, and that asymmetry with
    :func:`administrative_scopes` is the decision rather than an inconsistency.
    Exactly one class can be the complement; a second one derived the same way
    would be indistinguishable from it.
    """
    return frozenset(
        config.load_schema("capabilities.schema.json")["$defs"]["storage_scope"]["enum"]
    )


@lru_cache(maxsize=1)
def administrative_scopes() -> frozenset[str]:
    """The class a capability manifest may not request.

    **Read from the schema, not derived**, and that is ADR 0100's correction to
    ADR 0079. It was `approved_scopes() - agent_requestable_scopes()`, which is
    correct for exactly two classes and silently wrong for three: with
    `objects:read` in the union and in no other class, this function called it
    administrative. Run 1 measured what that looks like -- `authenticated`
    appearing to hold an administrative scope, and the two tests that noticed
    both looking exactly like tests somebody would update when adding a scope.

    ADR 0079 derived it so the four names would be written once. They are now
    written twice, here and in the union, and
    :func:`assert_classes_partition_the_vocabulary` is what makes the second
    copy safe -- it compares the classes against the union exactly, which is a
    stronger relation than "no name is written twice" and the only one that
    catches an *unclassified* name. A complement cannot catch that, because a
    complement has no notion of one.
    """
    return frozenset(
        config.load_schema("capabilities.schema.json")["$defs"]["administrative_scope"]["enum"]
    )


def assert_classes_partition_the_vocabulary() -> None:
    """The three classes are disjoint and their union is exactly `$defs/scope`.

    One relation, checked in three directions, and it replaces the complement
    that used to make it unnecessary to state. What it buys is that a name added
    to the vocabulary and to no class **fails here**, with a message naming it,
    instead of being absorbed into whichever class was derived by subtraction.

    Raises rather than reporting: the callers are the issuer and the
    repository's own registry reads, and a vocabulary whose classes do not
    partition it is not a condition to carry forward.
    """
    approved = approved_scopes()
    classes = {
        "$defs/agent_scope": agent_requestable_scopes(),
        "$defs/storage_scope": storage_scopes(),
        "$defs/administrative_scope": administrative_scopes(),
    }

    for name, members in classes.items():
        outside = members - approved
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

    unclassified = approved - set().union(*classes.values())
    if unclassified:
        raise ManifestError(
            f"$defs/scope admits {sorted(unclassified)} and no class claims them. Before "
            "ADR 0100 they would have been classified ADMINISTRATIVE by complement -- a "
            "decision arithmetic made rather than one anybody wrote down. Add each name "
            "to the class it belongs to, and if that class does not exist yet, it needs "
            "an ADR before it needs an enum"
        )


#: Re-exported from the service's build context, which is the one
#: declaration (ADR 0084). Assigned rather than restated: a copy here would
#: be two authorities for one authorization model, and D175 records that a
#: test comparing two constants goes green again the moment somebody
#: regenerates the copy.
ROLE_SCOPES: dict[str, frozenset[str]] = _scopes.ROLE_SCOPES


def permitted_scopes(role_suffix: str) -> frozenset[str]:
    """The ceiling for one role, validated against the schema on the way out.

    Validation happens here rather than at import so that a schema edit which
    removes a name is caught by whatever reads the registry next, with a message
    naming both sides, rather than by an import error in an unrelated command.

    The partition check runs first, and before the role lookup, because it is a
    statement about the vocabulary rather than about this call: a schema whose
    classes do not partition it is wrong for every role, and answering one
    question correctly out of a broken vocabulary is how the misclassification
    ADR 0100 describes stayed invisible.
    """
    assert_classes_partition_the_vocabulary()

    if role_suffix not in ROLE_SCOPES:
        raise ManifestError(
            f"no token may name the role {role_suffix!r}. The roles a token may name are "
            f"{sorted(ROLE_SCOPES)}; the rest are service identities, and offering one as "
            "an option invites somebody to find out what it can do"
        )

    scopes = ROLE_SCOPES[role_suffix]
    unapproved = scopes - approved_scopes()
    if unapproved:
        raise ManifestError(
            f"the scope registry grants {role_suffix} scopes the capability schema does "
            f"not admit: {sorted(unapproved)}. The schema is the sole authority (ADR 0006) "
            "and this file is a mapping onto it"
        )
    return scopes


def assert_scopes_permitted(role_suffix: str, scopes: list[str]) -> frozenset[str]:
    """The check an issuer runs before signing. Returns the set it validated.

    Refuses an empty list as well as an over-wide one. A token with no scopes for
    a role that has a ceiling is not a safe default -- it is a token whose
    authority nothing described, and `verify_claims` requires the claim to be
    present.
    """
    ceiling = permitted_scopes(role_suffix)

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
