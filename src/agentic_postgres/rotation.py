"""What rotating a declared secret would actually do (ADR 0174).

Pure: no provider, no filesystem, no deploy. It reads the contract and answers
one question per secret — *if you replaced this value, what would happen* — and
the interesting answers are the refusals.

**The vocabulary is five sessions old and had one reader** (D816).
``rotate_by_replacement``, ``must_refresh_on_start`` and
``one_time_initialization`` are declared on all 19 secrets and were asserted by a
single contract test covering three. Run 6's first act was checking them against
the world rather than against each other, and what that found is recorded in
:data:`MUST_REFRESH_IS_NOT_YET_A_CONTROL`.

**Two of the three flags describe observable behaviour and one does not.**
``one_time_initialization`` and ``rotate_by_replacement`` say what happens when a
value is replaced, and that is measurable — it was measured. ``must_refresh_on_start``
selects between failing closed and starting on a cached last-known-good value,
and **the second behaviour does not exist anywhere in the tree**: the materializer
fails the whole run on any provider error except a 404 for an optional secret.
So a `false` there describes a leniency this deployment does not offer, and this
module refuses to report it as a difference.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "MUST_REFRESH_IS_NOT_YET_A_CONTROL",
    "Verdict",
    "plan_all",
    "plan_for",
]

#: Why `must_refresh_on_start` is not reported as a difference between secrets.
#:
#: The flag chooses between two materializer behaviours. Measured in Run 6:
#: `bin/materialize-secrets.py` has no cache, no fallback and no last-known-good
#: path -- every provider failure except a 404 on an optional secret fails the
#: run. So the "true" behaviour is the only behaviour, six `false` declarations
#: describe leniency that was never built, and a plan that printed them would be
#: describing a choice the deployment cannot make.
#:
#: This is a sentence rather than a silent omission because the flag is not
#: WRONG -- it is unimplemented, and the day somebody builds the fallback it
#: becomes a real difference and this constant is the thing that has to change.
MUST_REFRESH_IS_NOT_YET_A_CONTROL = (
    "must_refresh_on_start is not reported: it selects between failing closed and "
    "starting on a cached last-known-good value, and the materializer has no cache "
    "-- every provider failure except a 404 on an optional secret fails the run. "
    "Six `false` declarations describe leniency that does not exist (D849)."
)


@dataclass(frozen=True, slots=True)
class Verdict:
    """What replacing one secret's value would achieve.

    ``rotates`` is the whole answer. ``reason`` says why not when it is false,
    and ``instead`` names the operation that does work -- because a refusal that
    does not say what to do instead makes an operator guess, and the guess for a
    credential is usually "do it anyway".
    """

    name: str
    rotates: bool
    reason: str
    instead: str | None
    consumers: tuple[str, ...]
    operator_supplied: bool

    def render(self) -> str:
        head = "ROTATES  " if self.rotates else "REFUSED  "
        lines = [f"{head}{self.name}", f"         {self.reason}"]
        if self.instead:
            lines.append(f"         instead: {self.instead}")
        if self.consumers:
            lines.append(f"         reaches: {', '.join(self.consumers)}")
        return "\n".join(lines)


def _consumers(secret: dict[str, Any]) -> tuple[str, ...]:
    names = []
    for consumer in secret["consumers"]:
        service = consumer.get("service")
        names.append(f"{consumer['plane']}:{service}" if service else consumer["plane"])
    return tuple(names)


def plan_for(secret: dict[str, Any]) -> Verdict:
    """One secret's verdict. Reads the declaration, and refuses to over-claim.

    The order matters: ``one_time_initialization`` is checked FIRST, because it
    is the case where every other field reads as though a rotation would work.
    A plan that reported the consumers and the plane for
    ``postgres_init_superuser_password`` would be describing, in detail, a
    rotation that does not happen (D56).
    """
    name = secret["name"]
    consumers = _consumers(secret)

    if secret["one_time_initialization"]:
        return Verdict(
            name=name,
            rotates=False,
            reason=_REFUSAL.get(name, _GENERIC_REFUSAL),
            instead=_INSTEAD.get(name, "a coordinated operation with a different name"),
            consumers=consumers,
            operator_supplied=secret["origin"] == "operator_supplied",
        )

    if not secret["rotate_by_replacement"]:
        return Verdict(
            name=name,
            rotates=False,
            reason="the contract declares that replacement does not rotate this value",
            instead=_INSTEAD.get(name),
            consumers=consumers,
            operator_supplied=secret["origin"] == "operator_supplied",
        )

    if secret["origin"] == "operator_supplied":
        return Verdict(
            name=name,
            rotates=True,
            reason=(
                "replacing this value rotates it -- but the NEW value comes from a "
                "third party and cannot be generated here"
            ),
            instead=None,
            consumers=consumers,
            operator_supplied=True,
        )

    return Verdict(
        name=name,
        rotates=True,
        reason="replacing this value rotates it; every consumer below is re-materialized",
        instead=None,
        consumers=consumers,
        operator_supplied=False,
    )


#: Why replacing each of them achieves nothing, per secret.
#:
#: **The flag covers two different phenomena and only one sentence fits both
#: loosely** (D850). `postgres_init_superuser_password` is read once and nothing
#: is BOUND to it -- the cluster keeps whatever initdb set.
#: `pgbackrest_repo_cipher_pass` is the opposite: the value is bound, to the
#: repository, at `stanza-create`, so replacing it does not leave the system
#: using the old value -- it leaves the reader holding the wrong one.
#:
#: The flag is right about the consequence and imprecise about the mechanism, so
#: the mechanism is spelled per secret. A generic sentence would have been
#: plausible and wrong for one of the two, which is the shape D278 names.
_REFUSAL: dict[str, str] = {
    "postgres_init_superuser_password": (
        "replacing this value achieves nothing: it is read once, when the data "
        "directory is empty, and the running cluster keeps whatever initdb set"
    ),
    "pgbackrest_repo_cipher_pass": (
        "replacing this value achieves nothing GOOD: the cipher is bound to the "
        "repository at stanza-create, so a new value does not re-encrypt anything -- "
        "it leaves the reader holding the wrong pass phrase for every existing backup"
    ),
}

_GENERIC_REFUSAL = (
    "the contract declares this read once at initialization, so replacing it does "
    "not rotate a credential. No mechanism is recorded for it here, which means "
    "nobody has written down what replacing it actually does"
)


#: What actually rotates each value whose replacement does not.
#:
#: Named per secret rather than generated, because the real operation differs in
#: kind: one is a coordinated `ALTER ROLE`, the other is a new repository and a
#: new backup chain. A generic "see the documentation" would be the refusal
#: without the part that helps.
_INSTEAD: dict[str, str] = {
    "postgres_init_superuser_password": (
        "a coordinated ALTER ROLE through the privileged local path -- the cluster's "
        "superuser password is whatever initdb set, and this file is not read again"
    ),
    "pgbackrest_repo_cipher_pass": (
        "a new repository and a new full backup chain. Replacing this in place does "
        "not re-encrypt anything: it orphans every backup ever taken while every "
        "check in this repository passes"
    ),
}


def plan_all(contract: dict[str, Any], session: int) -> list[Verdict]:
    """Every active secret's verdict, in declaration order.

    Takes the session because a secret retired at or before it is not part of
    this release's rotation surface (ADR 0170) -- planning a rotation for a
    credential the deployment no longer issues would name a file nothing writes.
    """
    from agentic_postgres.secrets_contract import active_secrets

    return [plan_for(secret) for secret in active_secrets(contract, session)]
