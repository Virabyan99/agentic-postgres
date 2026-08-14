"""Password hashing: the frozen profile, applied and then checked.

Five things live here, and each one exists because of something measured in
Run 7 rather than because a checklist named it.

**Normalization.** `"Ame\\u0301lie"` and `"Am\\u00e9lie"` render identically and
are different byte strings. Measured: a hash of the NFC form refuses the
decomposed form with `VerifyMismatchError`. Without normalization the same
password typed on macOS and on Linux is two passwords, and the user who set it
on one cannot log in from the other -- a bug that looks exactly like a wrong
password and is untraceable from a log that redacts the value.

**The blocklist.** Small and honest about it (see `_BLOCKLIST`).

**The frozen profile check.** `PasswordHasher.verify()` returns True for a hash
produced with a weaker profile -- measured, argon2-cffi 25.1.0. So the profile
is enforced on the way *in*, by reading the stored hash's own parameters before
the password is ever checked against it. ADR 0081.

**Dummy verification.** Measured: a verification that misses costs 127.9 ms and
one that hits costs 126.3 ms. That is only true because the miss does the same
Argon2 work, against a hash of a password nobody has. Returning early on an
unknown subject would publish the user list through a stopwatch.

**The bounded executor.** Argon2 releases the GIL -- measured at a 1.90x speedup
across four threads on eight cores -- so hashing genuinely runs off the event
loop. It also allocates `memory_cost` per concurrent hash, measured linear:
67.1 MiB at concurrency 1, 131.1 at 2, 259.0 at 4. The semaphore is what turns
that from an unbounded claim on the container's memory into ADR 0082's relation.
"""

from __future__ import annotations

import asyncio
import itertools
import os
import unicodedata
from typing import Final

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type

from app.profile import FROZEN, HASH_CONCURRENCY, Argon2Profile, parse_encoded

#: Bytes, not characters, and applied after normalization. Argon2 has no
#: practical input limit, so this is not a cryptographic bound -- it is a bound
#: on what one request may ask the executor to hold. Deliberately generous: a
#: passphrase is the credential this service most wants people to use.
MAX_PASSWORD_BYTES: Final = 1024

#: The floor, in characters, counted after normalization. Length is the only
#: property of a password that reliably predicts its strength, and a composition
#: rule ("one digit, one symbol") reliably predicts `Password1!`.
MIN_PASSWORD_CHARACTERS: Final = 12

#: A floor, and stated as one rather than as a corpus.
#:
#: This is not a leaked-password corpus and does not pretend to be. A real one
#: is hundreds of megabytes, has a licence, and would arrive in this repository
#: with no provenance anybody could check -- which is the failure this project
#: keeps producing, one level up. What is here are the passwords that a
#: deployment of *this* product plausibly attracts, plus the handful that top
#: every published list.
#:
#: The defence against a guessed password is Argon2 at the frozen profile plus
#: the rate limit at the edge. This list exists so that the very worst choices
#: are refused at the moment they are made rather than surviving until somebody
#: audits them, and `_is_structurally_weak` does more work than the list does.
_BLOCKLIST: Final = frozenset(
    {
        "123456",
        "123456789",
        "12345678",
        "1234567890",
        "qwerty",
        "qwertyuiop",
        "password",
        "password1",
        "password123",
        "passw0rd",
        "letmein",
        "welcome",
        "welcome1",
        "admin",
        "administrator",
        "root",
        "toor",
        "changeme",
        "secret",
        "iloveyou",
        "monkey",
        "dragon",
        "sunshine",
        "princess",
        "football",
        "baseball",
        "trustno1",
        "abc123",
        "111111",
        "000000",
        "654321",
        "superman",
        "starwars",
        "whatever",
        "zaq12wsx",
        "1q2w3e4r",
        "qazwsx",
        # This product's own vocabulary. A deployment's first administrator
        # reaches for the words in front of them, and these are the words this
        # repository puts in front of them.
        "postgres",
        "postgresql",
        "agentic",
        "agenticpostgres",
        "apgadmin",
        "supabase",
        "traefik",
        "postgrest",
        "pgbouncer",
        "dbmate",
        "infisical",
    }
)


class PasswordRejected(ValueError):
    """A password refused before it was hashed.

    A distinct type because the caller must be able to tell "this password may
    not be used" from "hashing failed", and must never report the two the same
    way to a client: the first is the user's to fix and the second is not.
    """


class StoredHashRejected(ValueError):
    """A stored hash whose parameters are not the frozen profile (ADR 0081).

    Raised *instead of* attempting verification, so that a credential written
    under a profile this service does not produce can never authenticate --
    which `PasswordHasher.verify` on its own would happily let it do.
    """


def normalize(password: str) -> str:
    """NFC, and nothing else.

    Not `casefold`, not whitespace stripping. Both would make two different
    passwords the same password, which is a silent reduction of the keyspace;
    normalization makes two *identical* passwords the same password, which is
    the opposite operation and the only one that is safe here.
    """
    if not isinstance(password, str):
        raise PasswordRejected("a password is text")
    return unicodedata.normalize("NFC", password)


def _is_structurally_weak(candidate: str) -> str | None:
    """Weaknesses a list cannot enumerate. Returns a reason, or None."""
    folded = candidate.casefold()

    if folded in _BLOCKLIST:
        return "this password is one of the most commonly chosen ones"

    # A single repeated character, of any length. `aaaaaaaaaaaaaaaa` clears
    # every length rule ever written.
    if len(set(candidate)) == 1:
        return "this password is a single repeated character"

    # A short unit repeated to length: `abcabcabcabcabc`. Checked for every
    # unit length that divides the password, because checking only the obvious
    # ones is how `ababababababab` gets through a rule aimed at `aaaa`.
    for unit in range(1, len(candidate) // 2 + 1):
        if len(candidate) % unit == 0 and candidate == candidate[:unit] * (len(candidate) // unit):
            return "this password is a short sequence repeated"

    # An ascending or descending run over the whole password: `123456789012`,
    # `abcdefghijkl`. Compared on code points, so it catches digits and letters
    # without a table of either.
    points = [ord(character) for character in candidate]
    deltas = {second - first for first, second in itertools.pairwise(points)}
    if deltas in ({1}, {-1}):
        return "this password is a single run of consecutive characters"

    # A blocklisted word with digits stuck on either end: `password2024`,
    # `2024admin`. The stripped form is checked rather than a substring search,
    # because a substring search refuses `passthrough` for containing `pass`.
    stripped = folded.strip("0123456789!@#$%^&*()_+-=")
    if stripped and stripped in _BLOCKLIST:
        return "this password is a common one with characters added"

    return None


def assess(password: str, *, forbidden: tuple[str, ...] = ()) -> str:
    """Normalize and screen a *new* password. Returns the form to be hashed.

    `forbidden` carries the values a caller knows are bad for this subject --
    the username, the project key, the domain. They are not in `_BLOCKLIST`
    because they are not constants; a list that tried to hold them would be a
    list that goes stale for every project deployed after it was written.

    Raises `PasswordRejected`, whose message is safe to return to the person
    choosing the password and to nobody else. This is the one place in the
    service where a specific reason is the right answer: the subject already
    knows the value, so telling them why it was refused leaks nothing, and
    refusing without a reason produces a user who tries eleven variations of
    the same weak password.
    """
    candidate = normalize(password)

    encoded = candidate.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise PasswordRejected(f"a password may be at most {MAX_PASSWORD_BYTES} bytes")
    if len(candidate) < MIN_PASSWORD_CHARACTERS:
        raise PasswordRejected(f"a password must be at least {MIN_PASSWORD_CHARACTERS} characters")

    reason = _is_structurally_weak(candidate)
    if reason is not None:
        raise PasswordRejected(reason)

    folded = candidate.casefold()
    for value in forbidden:
        if not value:
            continue
        # Equality after folding, not containment: a project key of `app`
        # would otherwise refuse every password containing those three
        # letters, and an administrator would never find out why.
        if folded == normalize(value).casefold():
            raise PasswordRejected("a password may not be one of this project's own names")

    return candidate


class Hasher:
    """The frozen profile, and the two operations that are allowed to use it.

    Constructed once per process. `PasswordHasher` holds no state that a
    request could contaminate, and building one per request would rebuild
    argon2's parameter validation on every login for no reason.
    """

    def __init__(self, profile: Argon2Profile = FROZEN) -> None:
        if profile.type != "argon2id":
            # The constructor takes a `Type`; mapping an arbitrary string to
            # one would mean this class could be asked for argon2i by a typo.
            raise ValueError(f"only argon2id is produced here, not {profile.type!r}")
        self.profile = profile
        self._hasher = PasswordHasher(
            type=Type.ID,
            memory_cost=profile.memory_cost_kib,
            time_cost=profile.time_cost,
            parallelism=profile.parallelism,
            hash_len=profile.hash_len,
            salt_len=profile.salt_len,
        )
        #: A hash of a value nobody holds, produced at the frozen profile at
        #: construction so that a verification against an unknown subject costs
        #: exactly what a real one costs. Built from `os.urandom` rather than
        #: from a constant, so that the dummy hash is not a value an attacker
        #: can recognise in a database dump and use to identify which rows are
        #: real.
        self._dummy = self._hasher.hash(os.urandom(32).hex())

    def hash(self, password: str) -> str:
        """Hash an already-assessed password. Blocking; call it in the executor.

        Deliberately does not call `assess`. A caller that hashed without
        screening would be a caller this signature made look correct, and the
        two operations have different audiences: `assess` answers a person,
        `hash` answers the database.
        """
        return self._hasher.hash(password)

    def verify(self, stored: str | None, password: str) -> bool:
        """Check a password against a stored hash. Blocking.

        `stored` may be None -- an unknown subject, or one with no password set
        -- and the dummy hash is verified instead so the two cost the same.

        The frozen-profile check happens before verification and raises rather
        than returning False, because "this hash was written by something else"
        is an operational fault and reporting it as a wrong password would hide
        a real problem behind thousands of failed logins.
        """
        if stored is None:
            self._verify_dummy(password)
            return False

        try:
            recorded = parse_encoded(stored)
        except ValueError as exc:
            self._verify_dummy(password)
            raise StoredHashRejected(
                f"stored hash is not a PHC-format Argon2 string: {exc}"
            ) from exc

        if not recorded.matches(self.profile):
            # Still pay the cost. An operator-visible fault must not also be a
            # timing signal that distinguishes one stored row from another.
            self._verify_dummy(password)
            raise StoredHashRejected(
                "stored hash does not carry the frozen Argon2id profile "
                f"(recorded {recorded}, frozen {self.profile})"
            )

        try:
            return self._hasher.verify(stored, password)
        except VerifyMismatchError:
            return False
        except (InvalidHashError, VerificationError) as exc:
            raise StoredHashRejected(f"stored hash could not be verified: {exc}") from exc

    def _verify_dummy(self, password: str) -> None:
        try:
            self._hasher.verify(self._dummy, password)
        except VerificationError:
            pass


class BoundedHasher:
    """`Hasher`, off the event loop, with at most `concurrency` in flight.

    **The semaphore is released by the worker, not by the caller**, and that is
    the whole reason this class exists rather than a bare `asyncio.Semaphore`
    around `run_in_executor`. A cancelled `await` -- a client that disconnects
    mid-login, a request that times out -- unwinds an `async with` immediately
    while the thread carrying its 64 MiB is still running. Under a burst of
    cancellations the semaphore would permit `concurrency` *new* hashes while
    `concurrency` old ones were still resident, and the container's memory limit
    is derived on the assumption that cannot happen (ADR 0082).

    **`asyncio.shield` closes the other half, and it is the half the obvious
    reasoning gets backwards.** Cancelling a caller whose hash has already
    started is harmless with or without it: `Future.cancel()` on work a thread
    has begun returns False, the worker runs to completion and its `finally`
    releases. The dangerous case is the *opposite* one -- work submitted to the
    executor and **not yet started**. There, cancellation succeeds, the worker
    never runs, its `finally` never runs, and the permit is leaked for the life
    of the process. Shielded, the inner future is never cancelled, so the job
    stays queued, eventually runs, and releases.

    This docstring said the reverse until a mutation battery removed the shield
    and every test stayed green. The test that now covers it saturates the
    executor deliberately, because with a thread pool larger than `concurrency`
    the queued case cannot otherwise arise.
    """

    def __init__(self, hasher: Hasher | None = None, concurrency: int = HASH_CONCURRENCY) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        self.hasher = hasher if hasher is not None else Hasher()
        self.concurrency = concurrency
        self._semaphore = asyncio.Semaphore(concurrency)
        #: Incremented before the worker starts and decremented in its
        #: `finally`, so it counts threads that are *resident*, not callers
        #: that are waiting. `permits_available` is derived from it rather than
        #: read off the semaphore's private counter, which would report a
        #: permit as free the instant a caller was cancelled.
        self._in_flight = 0

    async def _run(self, function, /, *arguments):
        await self._semaphore.acquire()
        loop = asyncio.get_running_loop()
        self._in_flight += 1

        def worker():
            try:
                return function(*arguments)
            finally:
                # The semaphore belongs to the loop and this runs in a thread,
                # so the release is scheduled onto the loop rather than done
                # here. Releasing from the thread would be a data race on the
                # waiter queue.
                loop.call_soon_threadsafe(self._release)

        future = loop.run_in_executor(None, worker)
        # Shielded so the caller's cancellation cannot reach the future. A
        # thread pool's idea of cancellation is "cancelled if NOT YET STARTED",
        # and that is the leak: a cancelled submission never runs its `finally`,
        # so its permit is never returned and the container's effective
        # concurrency falls by one for the life of the process (ADR 0082).
        return await asyncio.shield(future)

    def _release(self) -> None:
        self._in_flight -= 1
        self._semaphore.release()

    async def hash(self, password: str) -> str:
        return await self._run(self.hasher.hash, password)

    async def verify(self, stored: str | None, password: str) -> bool:
        return await self._run(self.hasher.verify, stored, password)

    def in_flight(self) -> int:
        """How many hashes are resident right now. Diagnostic only."""
        return self._in_flight

    def permits_available(self) -> int:
        """How many hashes could start right now. Diagnostic only."""
        return self.concurrency - self._in_flight
