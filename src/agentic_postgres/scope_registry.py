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
    "assert_scopes_permitted",
    "permitted_scopes",
]


@lru_cache(maxsize=1)
def approved_scopes() -> frozenset[str]:
    """Every name the schema admits, both classes. Loaded, never restated."""
    return frozenset(config.load_schema("capabilities.schema.json")["$defs"]["scope"]["enum"])


@lru_cache(maxsize=1)
def agent_requestable_scopes() -> frozenset[str]:
    """The subset a capability manifest may declare in ``required_scopes``."""
    return frozenset(config.load_schema("capabilities.schema.json")["$defs"]["agent_scope"]["enum"])


def administrative_scopes() -> frozenset[str]:
    """The class a capability manifest may not request.

    Derived as the complement rather than listed, so there is no third place a
    scope name is written and no way for the two classes to overlap by typo.
    """
    return approved_scopes() - agent_requestable_scopes()


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
    """
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
