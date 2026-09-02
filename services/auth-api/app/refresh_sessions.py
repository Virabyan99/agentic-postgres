"""The session plane's logic, with no database and no HTTP in it (ADR 0171).

**Pure on purpose.** What a presented refresh token *means* is a decision with
five outcomes and a precedence between them, and a decision that can only be
exercised by standing up Postgres and an endpoint is a decision nobody exercises.
Migration 0023 holds the state, Run 3's route and SQL will hold the plumbing, and
this module holds the part that is neither -- so the transitions can be
enumerated in a unit test.

**It lives beside `claims.py` and `tokens.py` rather than in
`src/agentic_postgres/`**, and the placement was corrected by a guard rather than
decided twice (D831). The session plane is read by the auth service and by
nothing else: no operator command, no deploy step, no renderer.
`agentic_postgres` is the package `bin/` and the deploy share, and a module there
that only one service imports is a module in the wrong package --
`test_no_module_is_imported_only_by_its_own_tests` said so the moment it was put
there, because until Run 3 it would have had no caller in that package at all.

**Why the plane exists at all** is D813, and it is a credential-handling defect
rather than a convenience one. ``jwt_claims.MAX_TTL_SECONDS`` is 900 and the auth
service issues at the ceiling, plus 30 s of skew: a token is live for at most 930
seconds and nothing renewed it. So a client staying logged in beyond fifteen
minutes had to retain the **password** and replay it. The short TTL is right --
what was missing is the half that makes keeping it affordable.

Nothing here holds a token value beyond the moment it mints one, and nothing here
logs. ``refresh_token`` is in ``config.SENSITIVE_KEY_DENYLIST``, which until this
session guarded a value that did not exist (D812).
"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "FAMILY_REVOCATION_REASONS",
    "REFRESH_TTL_SECONDS",
    "TOKEN_ENTROPY_BYTES",
    "TOKEN_PATTERN",
    "Outcome",
    "RevocationReason",
    "TokenState",
    "classify",
    "hash_token",
    "is_wellformed",
    "mint",
    "sql_revocation_reasons",
]

#: 32 bytes from the system CSPRNG, rendered by ``secrets.token_urlsafe`` as 43
#: url-safe characters. The size is what makes the stored digest a deterministic
#: SHA-256 rather than an argon2 hash (ADR 0171): a KDF's expense buys resistance
#: to guessing a *low-entropy* secret, and 256 bits is not one.
TOKEN_ENTROPY_BYTES = 32

#: What a minted token looks like, so a value that this plane cannot have issued
#: is refused before it reaches a query. Not a security boundary -- the digest
#: lookup is that -- but a malformed token is a caller error and answering it
#: without a database round trip is the honest shape.
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")

#: How long a single refresh token stays presentable: 30 days.
#:
#: This bounds an **idle** session, because every use mints a successor. It is
#: not an absolute ceiling on a session's life, and ADR 0171 records that as a
#: decision rather than an oversight: a continuously-used family survives
#: indefinitely, which is the ordinary shape of refresh rotation, and adding a
#: ceiling is one column and one comparison whenever somebody can say what the
#: ceiling should be.
REFRESH_TTL_SECONDS = 30 * 24 * 60 * 60


class RevocationReason(StrEnum):
    """Why a family ended. Mirrors ``app_private.refresh_revocation``.

    Tied to the migration by a contract test comparing
    :func:`sql_revocation_reasons` against 0023's ``CREATE TYPE``, the way
    ``jwt_claims.sql_required_claims()`` is tied to 0011's literal. Two spellings
    of one enumeration is how they come to disagree.
    """

    LOGGED_OUT = "logged_out"
    REUSE_DETECTED = "reuse_detected"
    CREDENTIAL_CHANGED = "credential_changed"
    ADMINISTRATIVE = "administrative"


#: Declaration order, which is also the SQL type's order. The tuple exists so the
#: contract test compares a sequence rather than a set: an enum whose members are
#: reordered is a different type to `pg_dump` and to any client that stored an
#: ordinal, so the order is part of what is being pinned.
FAMILY_REVOCATION_REASONS: tuple[str, ...] = tuple(r.value for r in RevocationReason)


def sql_revocation_reasons() -> str:
    """The enum body as 0023 spells it, for the contract test to compare."""
    return ",\n".join(f"  '{value}'" for value in FAMILY_REVOCATION_REASONS)


class Outcome(StrEnum):
    """What presenting a refresh token means.

    Five, and the two that refuse for *different reasons* are the point:
    ``REUSE`` is an alarm and ``REVOKED`` is a lifecycle event, and collapsing
    them into "refused" would lose the only signal that says a chain leaked.
    """

    ROTATE = "rotate"
    REUSE = "reuse"
    REVOKED = "revoked"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class TokenState:
    """A presented token's row, as the database holds it.

    ``found=False`` means no row carries that digest; every other field is then
    meaningless and :func:`classify` reads none of them.
    """

    found: bool
    consumed: bool = False
    family_revoked: bool = False
    expires_at: int = 0


def is_wellformed(token: str) -> bool:
    """Whether this could be a token this plane minted."""
    return bool(TOKEN_PATTERN.match(token))


def mint() -> tuple[str, str]:
    """A new token and the digest to store. **The token is a credential.**

    Returned rather than logged, printed or defaulted anywhere: the caller hands
    it to exactly one HTTP response and keeps the digest.
    """
    token = secrets.token_urlsafe(TOKEN_ENTROPY_BYTES)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    """The value the database stores: a hex SHA-256, never the token.

    **Deterministic, and that is structural rather than a preference** (ADR
    0171). A refresh token is presented *alone* -- unlike an agent secret, which
    arrives beside its ``agent_id``, and unlike a password, which arrives beside
    a username -- so the row has to be found BY this value. A per-row salt makes
    that a full scan with a KDF on every row.

    No constant-time comparison here, and its absence is deliberate: this digest
    is looked up through a unique index, so nothing in this plane compares two
    hashes in Python. A ``compare_digest`` call would imply a comparison that
    does not happen and suggest the timing question had been handled somewhere.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def classify(state: TokenState, *, now: int) -> Outcome:
    """What to do about a presented token. Pure, total, and ordered.

    **The precedence is the decision**, and it is written as a sequence of
    returns rather than a set of conditions so that two of them cannot both be
    true for a reader:

    1. ``UNKNOWN`` -- no row. Nothing else is knowable, and in particular this is
       NOT reuse: a value nobody issued is a guess, not a replay.
    2. ``REUSE`` -- the row is consumed. **Outranks revocation deliberately.** A
       replay arriving at an already-revoked family is a second replay, and it is
       evidence; classifying it as ``REVOKED`` because the family was already
       closed would suppress exactly the alarm this plane exists to raise.
    3. ``REVOKED`` -- the family ended for one of the other three reasons.
    4. ``EXPIRED`` -- live, unconsumed, past its own deadline.
    5. ``ROTATE`` -- consume it and issue the successor.

    ``now`` is a parameter because the authority for it is the database's own
    ``now()``, not this process's clock, and because a state machine that reads a
    clock cannot be enumerated in a test.

    No clock skew is applied, unlike ``jwt_claims``. The 30 seconds there exist
    because an *issuer* and a *verifier* have different clocks; here one server
    compares its own ``now()`` against a timestamp it wrote, so there is no
    second clock to be lenient about -- and 30 seconds of leniency on a 30-day
    deadline would be a number that looked considered and meant nothing.
    """
    if not state.found:
        return Outcome.UNKNOWN
    if state.consumed:
        return Outcome.REUSE
    if state.family_revoked:
        return Outcome.REVOKED
    if state.expires_at <= now:
        return Outcome.EXPIRED
    return Outcome.ROTATE
