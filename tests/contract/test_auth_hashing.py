"""The frozen Argon2id profile, and the four behaviours around it.

`SEC-CRED-002`. The profile is read back **from the encoded hash**, not from
the constructor's arguments, and not by asking argon2 what argon2 just did:
`app.profile.parse_encoded` reads the PHC string with `str.split`, so the
answer comes from a different place than the one that produced it.

The measurement that makes this a requirement rather than a formality (Run 7,
argon2-cffi 25.1.0): `PasswordHasher.verify()` returns **True** for a hash
produced with a weaker profile. `check_needs_rehash` reports the mismatch and
nothing acts on it. A credential stored at `m=8192,t=1,p=2` would keep
authenticating for as long as it existed.
"""

from __future__ import annotations

import asyncio
import time

import argon2
import pytest
from argon2 import PasswordHasher
from argon2.low_level import Type

from agentic_postgres import auth_profile
from app import profile as profile_module
from app.hashing import (
    MIN_PASSWORD_CHARACTERS,
    BoundedHasher,
    Hasher,
    PasswordRejected,
    StoredHashRejected,
    assess,
    normalize,
)

pytestmark = [pytest.mark.contract, pytest.mark.security, pytest.mark.p0]

# (S105 is bandit's hardcoded-password rule. This is a test fixture whose whole
# purpose is to be hashed and verified in a file that is about hashing; there is
# no deployment in which it is a credential.)
PASSPHRASE = "a-correct-horse-battery-staple"  # noqa: S105


# ---------------------------------------------------------------------------
# The profile, read back from the hash
# ---------------------------------------------------------------------------


def test_the_encoded_hash_records_the_frozen_profile() -> None:
    """SEC-CRED-002, from the artefact rather than from the request.

    Every field of the frozen profile is present in the string the service
    stores, and this reads them with the standard library. Asking
    `argon2.extract_parameters` instead would be the same authority twice.
    """
    encoded = Hasher().hash(PASSPHRASE)
    recorded = profile_module.parse_encoded(encoded)

    assert recorded == auth_profile.FROZEN, (
        f"the stored hash records {recorded}, not the frozen profile {auth_profile.FROZEN}"
    )
    assert encoded.startswith("$argon2id$v=19$m=65536,t=3,p=1$")


def test_the_hand_written_parser_agrees_with_the_library_it_does_not_use() -> None:
    """Two readers, one string, and they must say the same thing.

    This is the only test that lets `argon2.extract_parameters` near the
    profile, and its job is to show that the hand-written parser is not simply
    wrong in a way that happens to match the frozen constant. A parser that
    returned `FROZEN` unconditionally would pass the test above and fail this
    one, because the profiles below are deliberately not frozen.
    """
    for memory, time_cost, parallelism in ((65536, 3, 1), (8192, 1, 2), (32768, 2, 4)):
        encoded = PasswordHasher(
            type=Type.ID, memory_cost=memory, time_cost=time_cost, parallelism=parallelism
        ).hash("x")
        mine = profile_module.parse_encoded(encoded)
        theirs = argon2.extract_parameters(encoded)

        assert mine.memory_cost_kib == theirs.memory_cost
        assert mine.time_cost == theirs.time_cost
        assert mine.parallelism == theirs.parallelism
        assert mine.hash_len == theirs.hash_len, "the base64 field width is not the byte length"
        assert mine.salt_len == theirs.salt_len
        assert mine.version == theirs.version


def test_a_stored_hash_at_another_profile_cannot_authenticate() -> None:
    """ADR 0081, and the measurement it exists for.

    argon2's own `verify` accepts this hash -- asserted here, so that the test
    fails if that ever stops being true and this guard becomes unnecessary. The
    service refuses it, and refuses it *before* checking the password, so a
    credential written by something other than this service can never
    authenticate rather than merely being flagged for rehash.
    """
    weak = PasswordHasher(type=Type.ID, memory_cost=8192, time_cost=1, parallelism=2)
    stored = weak.hash(PASSPHRASE)

    # The library's own answer, which is the reason the guard is needed.
    assert weak.verify(stored, PASSPHRASE) is True
    assert PasswordHasher().check_needs_rehash(stored) is True

    with pytest.raises(StoredHashRejected, match="frozen Argon2id profile"):
        Hasher().verify(stored, PASSPHRASE)


def test_a_stronger_profile_is_also_refused() -> None:
    """`matches` is equality, not "at least as strong as".

    A stored hash produced with stronger parameters is also not this profile.
    Accepting it would mean the service has two profiles, which is the state
    the frozen profile exists to make unreachable by accident.
    """
    stronger = PasswordHasher(type=Type.ID, memory_cost=131072, time_cost=4, parallelism=1)
    with pytest.raises(StoredHashRejected):
        Hasher().verify(stronger.hash(PASSPHRASE), PASSPHRASE)


def test_an_argon2i_hash_is_refused_though_every_number_matches() -> None:
    """The variant is part of the profile, and a reader that skipped it would pass."""
    other = PasswordHasher(
        type=Type.I,
        memory_cost=auth_profile.FROZEN.memory_cost_kib,
        time_cost=auth_profile.FROZEN.time_cost,
        parallelism=auth_profile.FROZEN.parallelism,
    )
    encoded = other.hash(PASSPHRASE)
    assert encoded.startswith("$argon2i$")
    with pytest.raises(StoredHashRejected):
        Hasher().verify(encoded, PASSPHRASE)


@pytest.mark.parametrize(
    "malformed",
    [
        "",
        "not-a-hash",
        "$argon2id$v=19$m=65536,t=3$salt$hash",
        "$argon2id$m=65536,t=3,p=1$salt$hash",
        "$argon2id$v=19$t=3,m=65536,p=1$c2FsdHNhbHRzYWx0c2E$aGFzaA",
        "$argon2id$v=nineteen$m=65536,t=3,p=1$salt$hash",
    ],
)
def test_a_malformed_stored_hash_is_a_fault_not_a_wrong_password(malformed: str) -> None:
    """It raises rather than returning False.

    Reporting "this hash is unreadable" as "wrong password" would hide an
    operational fault behind thousands of failed logins, which is the failure
    mode that takes longest to notice.
    """
    with pytest.raises(StoredHashRejected):
        Hasher().verify(malformed, PASSPHRASE)


def test_the_parameter_order_is_part_of_the_format() -> None:
    """`m,t,p` is what PHC specifies; a string spelling them otherwise is not ours."""
    with pytest.raises(ValueError, match="expected parameter 'm'"):
        profile_module.parse_encoded("$argon2id$v=19$t=3,m=65536,p=1$c2FsdHNhbHRzYWx0c2E$aGFzaA")


# ---------------------------------------------------------------------------
# Verification, and what a miss costs
# ---------------------------------------------------------------------------


def test_a_correct_password_verifies_and_a_wrong_one_does_not() -> None:
    hasher = Hasher()
    stored = hasher.hash(PASSPHRASE)
    assert hasher.verify(stored, PASSPHRASE) is True
    assert hasher.verify(stored, PASSPHRASE + "!") is False


def test_an_unknown_subject_costs_what_a_known_one_costs() -> None:
    """Dummy verification, timed rather than asserted from the source.

    Measured in Run 7 at 127.9 ms for a miss against 126.3 ms for a hit. The
    bound here is deliberately loose -- a factor of three -- because this runs
    on whatever machine the suite runs on, and the failure it must catch is an
    early `return False` for an unknown subject, which is a difference of two
    orders of magnitude rather than of tens of percent.
    """
    hasher = Hasher()
    stored = hasher.hash(PASSPHRASE)

    # One of each first: the first Argon2 call in a process is several times
    # the steady-state cost, and charging that to whichever branch ran first
    # would make this a measurement of import order.
    hasher.verify(stored, PASSPHRASE)
    hasher.verify(None, PASSPHRASE)

    rounds = 3
    start = time.perf_counter()
    for _ in range(rounds):
        assert hasher.verify(None, PASSPHRASE) is False
    unknown = (time.perf_counter() - start) / rounds

    start = time.perf_counter()
    for _ in range(rounds):
        hasher.verify(stored, "wrong-" + PASSPHRASE)
    known = (time.perf_counter() - start) / rounds

    assert unknown > known / 3, (
        f"an unknown subject cost {unknown * 1000:.1f} ms against {known * 1000:.1f} ms "
        "for a known one; the two must not be distinguishable by a stopwatch"
    )


def test_the_dummy_hash_is_not_a_constant() -> None:
    """Two hashers hold different dummies.

    A fixed dummy hash would be a value an attacker could recognise in a
    database dump and use to tell which rows are real.
    """
    assert Hasher()._dummy != Hasher()._dummy


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def test_normalization_is_load_bearing_rather_than_tidy() -> None:
    """The same password, typed on two platforms, is two byte strings.

    Measured: a hash of the NFC form refuses the decomposed form outright. So
    without normalization a user who sets a password on one platform cannot log
    in from the other, and the symptom is indistinguishable from a typo.
    """
    decomposed = "Amélie-passphrase"
    composed = "Amélie-passphrase"
    assert decomposed != composed
    assert normalize(decomposed) == composed

    hasher = Hasher()
    stored = hasher.hash(normalize(composed))
    assert hasher.verify(stored, normalize(decomposed)) is True

    # And the same two, unnormalized, do not verify -- which is what makes the
    # line above a result rather than a tautology.
    assert hasher.verify(hasher.hash(composed), decomposed) is False


def test_normalization_does_not_fold_case_or_strip_space() -> None:
    """Both would make two DIFFERENT passwords the same one."""
    assert normalize("PassPhrase") == "PassPhrase"
    assert normalize("  spaced  ") == "  spaced  "


# ---------------------------------------------------------------------------
# Screening
# ---------------------------------------------------------------------------


def test_a_good_passphrase_is_accepted_and_returned_normalized() -> None:
    assert assess(PASSPHRASE) == PASSPHRASE
    assert assess("Amélie-passphrase-1") == "Amélie-passphrase-1"


@pytest.mark.parametrize(
    ("candidate", "why"),
    [
        ("short", "below the length floor"),
        ("aaaaaaaaaaaaaaaa", "a single repeated character"),
        ("abcabcabcabcabcabc", "a short sequence repeated"),
        ("ababababababababab", "a two-character sequence repeated"),
        ("abcdefghijklmnop", "a consecutive run"),
        ("zyxwvutsrqponmlk", "a descending run"),
        ("password123456789", "a blocklisted word with digits appended"),
        ("postgresql000000", "this product's own vocabulary"),
    ],
)
def test_a_weak_password_is_refused(candidate: str, why: str) -> None:
    with pytest.raises(PasswordRejected):
        assess(candidate)


def test_the_length_floor_is_counted_after_normalization() -> None:
    """Eleven decomposed characters that normalize to fewer is still too short."""
    decomposed = "é" * 6  # 12 code points, 6 characters after NFC
    assert len(decomposed) == 12
    assert len(normalize(decomposed)) == 6
    with pytest.raises(PasswordRejected, match=str(MIN_PASSWORD_CHARACTERS)):
        assess(decomposed)


def test_a_forbidden_value_is_refused_by_equality_not_containment() -> None:
    """A project key of `app` must not refuse every password containing it."""
    with pytest.raises(PasswordRejected, match="this project's own names"):
        assess("alpha-dev-project", forbidden=("Alpha-Dev-Project",))

    # Containment is deliberately fine.
    assert assess("alpha-dev-passphrase", forbidden=("alpha",)) == "alpha-dev-passphrase"


def test_an_oversized_password_is_refused_before_it_is_hashed() -> None:
    with pytest.raises(PasswordRejected, match="bytes"):
        assess("é" * 600)  # 1200 bytes in UTF-8


def test_a_common_word_that_merely_contains_a_blocklisted_one_is_accepted() -> None:
    """`passthrough-the-gate` is not `password`."""
    assert assess("passthrough-the-gate") == "passthrough-the-gate"


# ---------------------------------------------------------------------------
# The bounded executor
# ---------------------------------------------------------------------------


def test_the_executor_never_exceeds_its_concurrency() -> None:
    """The bound ADR 0082's memory relation is derived from.

    Measured resident cost is linear in concurrency -- 67.1 MiB at one, 131.1
    at two, 259.0 at four -- so a semaphore that permitted more than it says
    would make the container's limit a number about nothing.
    """
    hasher = BoundedHasher(concurrency=2)
    peak = 0

    async def drive() -> None:
        nonlocal peak

        async def one() -> None:
            nonlocal peak
            task = asyncio.create_task(hasher.hash(PASSPHRASE))
            await asyncio.sleep(0)
            peak = max(peak, hasher.in_flight())
            await task

        await asyncio.gather(*(one() for _ in range(6)))

    asyncio.run(drive())
    assert 0 < peak <= 2, f"{peak} hashes were resident at once with a concurrency of 2"


def test_a_cancelled_caller_whose_hash_is_running_keeps_its_permit_until_it_finishes() -> None:
    """The permit follows the thread, not the caller.

    A cancelled `await` unwinds immediately while the thread carrying its
    64 MiB is still running. If the permit went back on cancellation, a burst
    of disconnecting clients would let the container hold `2n` hashes against a
    limit derived for `n` (ADR 0082).
    """
    hasher = BoundedHasher(concurrency=1)

    async def drive() -> tuple[int, int]:
        task = asyncio.create_task(hasher.hash(PASSPHRASE))
        while hasher.in_flight() == 0:  # pragma: no branch
            await asyncio.sleep(0.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        during = hasher.in_flight()

        for _ in range(500):
            if hasher.in_flight() == 0:
                break
            await asyncio.sleep(0.01)
        return during, hasher.in_flight()

    during, after = asyncio.run(drive())
    assert during == 1, "the permit was released while the hash was still resident"
    assert after == 0, "the worker never returned its permit"


def test_a_cancelled_submission_that_never_started_does_not_leak_its_permit() -> None:
    """What `asyncio.shield` is actually for, and the obvious reasoning has it backwards.

    Cancelling a caller whose hash has already begun is harmless either way:
    `Future.cancel()` on started work returns False and the worker's `finally`
    runs. The leak is the *opposite* case -- work submitted to the executor and
    not yet started, where cancellation succeeds, the worker never runs, and
    the permit is never returned. The container's effective concurrency then
    falls by one for the life of the process.

    The test above passes with the shield removed, which is how this gap was
    found: a mutation battery took the shield out and every test stayed green.
    Reaching the queued case needs a thread pool smaller than `concurrency`,
    because the default pool is far larger and nothing ever queues.
    """
    from concurrent.futures import ThreadPoolExecutor

    hasher = BoundedHasher(concurrency=2)

    async def drive() -> int:
        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=1) as single:
            loop.set_default_executor(single)

            running = asyncio.create_task(hasher.hash(PASSPHRASE))
            # The single thread is now occupied by `running`.
            while hasher.in_flight() < 1:  # pragma: no branch
                await asyncio.sleep(0.001)

            # This one takes the second permit and is QUEUED, not started.
            queued = asyncio.create_task(hasher.hash(PASSPHRASE))
            while hasher.in_flight() < 2:  # pragma: no branch
                await asyncio.sleep(0.001)

            queued.cancel()
            with pytest.raises(asyncio.CancelledError):
                await queued
            await running

            # Both workers must eventually run and return their permits.
            for _ in range(500):
                if hasher.in_flight() == 0:
                    break
                await asyncio.sleep(0.01)
            return hasher.in_flight()

    assert asyncio.run(drive()) == 0, (
        "a cancelled submission never ran its release; the permit is leaked and the "
        "container's concurrency is permanently one lower than its memory limit assumes"
    )


def test_the_executor_verifies_and_hashes_through_the_same_bound() -> None:
    hasher = BoundedHasher(concurrency=2)

    async def drive() -> bool:
        stored = await hasher.hash(PASSPHRASE)
        return await hasher.verify(stored, PASSPHRASE)

    assert asyncio.run(drive()) is True


def test_a_concurrency_below_one_is_refused() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        BoundedHasher(concurrency=0)
