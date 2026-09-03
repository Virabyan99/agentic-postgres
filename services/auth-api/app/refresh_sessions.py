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

from dataclasses import dataclass
from enum import StrEnum

from app.one_time_tokens import (
    TOKEN_ENTROPY_BYTES,
    TOKEN_PATTERN,
    hash_token,
    is_wellformed,
    mint,
)

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

#: The token primitive is `app.one_time_tokens`, re-exported here so every
#: existing caller and test keeps working. It moved in Run 5, when the
#: password-reset plane needed the same three functions: **copying them would
#: have been the second implementation ADR 0002 forbids**, and the second one is
#: always slightly weaker with nothing comparing them.
#:
#: What stayed here is what knows the tokens are SESSION tokens -- the outcome
#: enumeration, the precedence, the revocation reasons. What a presented token
#: means is this module's; what one IS belongs to the primitive.

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
