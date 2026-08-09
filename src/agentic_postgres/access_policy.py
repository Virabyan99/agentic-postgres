"""Who may obtain which database credential, decided in one place (ADR 0043).

The broker that hands out a password runs as root, on the host, behind a
``sudo -n`` rule. Everything about it is awkward to test: it needs root, a
deployed project, a materialized secret generation and a real caller identity.
So the *decision* does not live there. It lives here — a module that takes a
policy document, a caller name, a project key and a profile name, and returns
yes or no, with no filesystem and no privilege anywhere in it.

What that buys is the case nobody can arrange on a live host: the grant that
names a profile the caller was never meant to have, the duplicate grant where
one of two entries is dead and nobody knows which, the policy file that is
syntactically fine and permits everything. Those are decided here and asserted
offline.

**Three rules the schema cannot state.**

*A duplicate ``(unix_user, project_key)`` pair is refused.* JSON Schema's
``uniqueItems`` compares whole objects, so two grants for one account and one
project that differ only in their profile list both validate — and then one of
them silently loses to whichever the reader happens to hit first. Merging them
would be worse: it would grant the union of two lines an operator wrote as
alternatives.

*A profile name is never used as a lookup key into anything.* The mapping from
profile to secret is :data:`PROFILE_SECRETS` here, enumerated in code. A
document that could name its own secret is a document that can name any secret.

*The transport a profile uses is imported, not restated.* ``output_migrations``
already holds it because the deployed document is built from it, and two
copies of that mapping is one mapping that can disagree with the schema's
``const``.
"""

from __future__ import annotations

from typing import Any

from agentic_postgres import config
from agentic_postgres.config import ManifestError
from agentic_postgres.output_migrations import ACCESS_PROFILE_TRANSPORTS

#: Host-global, root-owned, mode 0600. Beside `database-port-allocations.json`,
#: which is the precedent for host state that is not one project's (ADR 0020).
POLICY_PATH = "/etc/agentic-postgres/database-access-policy.json"

SCHEMA_NAME = "database-access-policy.schema.json"

SCHEMA_VERSION = 1

#: The three profiles, in the order a reader should meet them: least authority
#: first. Derived from the transport map rather than retyped.
PROFILES = tuple(ACCESS_PROFILE_TRANSPORTS)

#: Which materialized secret each profile's password comes from, and which
#: consumer directory holds it. Enumerated here and nowhere else.
#:
#: The deployed document also carries a ``password_secret_ref`` per profile, and
#: the broker cross-checks the two rather than trusting either alone. They are
#: produced by different code at different times: this is what the release
#: believes, that is what the deploy recorded, and a disagreement means one of
#: them is describing a system that no longer exists.
PROFILE_SECRETS: dict[str, tuple[str, str]] = {
    "runtime_pooled": ("app_runtime_password", "pgbouncer"),
    "runtime_direct": ("app_runtime_password", "pgbouncer"),
    "migration_direct": ("migration_user_password", "dbmate"),
}

#: Profiles that carry authority over the schema rather than over rows. Named
#: as a set so that "requires an explicit choice" is one fact, checked by the
#: helper on the developer's machine and by the broker on the host.
PRIVILEGED_PROFILES = frozenset({"migration_direct"})

#: The profile a command uses when the caller did not choose one. The runtime
#: role through the direct transport: the least authority that can still run an
#: ordinary query, and never the migration credential.
DEFAULT_PROFILE = "runtime_direct"

__all__ = [
    "DEFAULT_PROFILE",
    "POLICY_PATH",
    "PRIVILEGED_PROFILES",
    "PROFILES",
    "PROFILE_SECRETS",
    "SCHEMA_NAME",
    "SCHEMA_VERSION",
    "PolicyError",
    "empty_policy",
    "grant_for",
    "permits",
    "profiles_for",
    "secret_for",
    "transport_for",
    "validate",
]


class PolicyError(ValueError):
    """The policy document is not one this module will decide from."""


def empty_policy() -> dict[str, Any]:
    """A host that delegates nothing.

    Written as a file rather than left absent, so that "no file" keeps meaning
    "state was lost" and not "nobody has access". Those need different
    responses, and the broker fails closed on both — but it should say which.
    """
    return {"schema_version": SCHEMA_VERSION, "grants": []}


def validate(policy: Any) -> dict[str, Any]:
    """Schema first, then the relation the schema cannot state."""
    if not isinstance(policy, dict):
        raise PolicyError("the database access policy must be a JSON object")

    try:
        config.validate_against_schema(policy, SCHEMA_NAME)
    except ManifestError as error:
        raise PolicyError(str(error)) from error

    # No secret value, and no key that looks like one. The schema forbids
    # unknown properties, so this cannot currently fire -- which is the point of
    # running it anyway: the day a field is added, it is checked on arrival
    # rather than in review.
    config.assert_no_sensitive_keys(policy)

    seen: dict[tuple[str, str], int] = {}
    for index, grant in enumerate(policy["grants"]):
        pair = (grant["unix_user"], grant["project_key"])
        if pair in seen:
            raise PolicyError(
                f"{pair[0]} appears twice for {pair[1]}, in grants {seen[pair]} and {index}. "
                "One of those two profile lists is the one that takes effect and the "
                "other is dead; merging them would grant the union of two lines that "
                "were written as alternatives"
            )
        seen[pair] = index

    return policy


def grant_for(policy: dict[str, Any], *, unix_user: str, project_key: str) -> dict[str, Any] | None:
    """The single grant for this pair, or ``None``.

    Single because :func:`validate` refused a second one. This function does not
    revalidate: callers validate on load, and a search that quietly tolerated a
    duplicate would be the second reader of a document with two answers.
    """
    for grant in policy["grants"]:
        if grant["unix_user"] == unix_user and grant["project_key"] == project_key:
            return grant
    return None


def profiles_for(policy: dict[str, Any], *, unix_user: str, project_key: str) -> tuple[str, ...]:
    grant = grant_for(policy, unix_user=unix_user, project_key=project_key)
    return tuple(grant["profiles"]) if grant else ()


def permits(policy: dict[str, Any], *, unix_user: str, project_key: str, profile: str) -> bool:
    """The whole decision, and deliberately the only way to reach it.

    An unknown profile name is ``False`` rather than an exception. The broker
    validates the profile name as *input* before it gets here; if that check is
    ever removed, this function must still refuse rather than raise, because a
    traceback and a refusal are the same answer only when someone is reading.
    """
    if profile not in PROFILE_SECRETS:
        return False
    return profile in profiles_for(policy, unix_user=unix_user, project_key=project_key)


def transport_for(profile: str) -> str:
    """``pooled`` or ``direct``, from the one mapping that defines it."""
    try:
        return ACCESS_PROFILE_TRANSPORTS[profile]
    except KeyError:
        raise PolicyError(f"not an access profile: {profile!r}") from None


def secret_for(profile: str) -> tuple[str, str]:
    """``(secret_name, consumer_service)`` for a profile."""
    try:
        return PROFILE_SECRETS[profile]
    except KeyError:
        raise PolicyError(f"not an access profile: {profile!r}") from None
