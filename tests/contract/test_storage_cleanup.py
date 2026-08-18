"""The cleanup sweep, and the three orderings that are its whole content.

**What this module must not become.** The sweep's arithmetic -- counting seven
deletes -- is the part that is easy to test and the part that does not matter.
What matters is the ORDER: delete before finish, expire before claim, and stop
before the lease does. So the fakes here record a single interleaved transcript
rather than per-method call counts, because a per-method counter cannot tell
`delete, finish` from `finish, delete` and both would satisfy a count.

That is the shape D260's third survivor had: a test comparing environment KEYS
that never looked at what they interpolate. A transcript can fail; a tally
cannot.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest

from app import storage_cleanup
from app.storage_client import StorageError
from app.storage_repository import CleanupClaim

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

HOLDER = "test-host:1:abcd1234"


@dataclass
class Transcript:
    """Every call the sweep made, in the order it made them."""

    events: list[tuple[str, Any]]

    def names(self) -> list[str]:
        return [name for name, _ in self.events]


class FakeRepository:
    def __init__(
        self,
        transcript: Transcript,
        *,
        claims: list[CleanupClaim],
        expired: int = 0,
        finish_returns: dict[UUID, bool] | None = None,
    ) -> None:
        self._transcript = transcript
        self._claims = claims
        self._expired = expired
        self._finish_returns = finish_returns or {}

    async def expire_intents(self, *, limit: int) -> int:
        self._transcript.events.append(("expire_intents", limit))
        return self._expired

    async def claim_cleanup_batch(
        self, *, holder: str, limit: int, lease_seconds: int, write_grace_seconds: int
    ) -> list[CleanupClaim]:
        self._transcript.events.append(
            ("claim", (holder, limit, lease_seconds, write_grace_seconds))
        )
        return self._claims

    async def finish_cleanup(self, *, object_id: UUID, holder: str) -> bool:
        self._transcript.events.append(("finish", (object_id, holder)))
        return self._finish_returns.get(object_id, True)


class FakeProvider:
    def __init__(self, transcript: Transcript, *, raises_on: set[str] | None = None) -> None:
        self._transcript = transcript
        self._raises_on = raises_on or set()

    async def delete_object(self, key: str) -> None:
        self._transcript.events.append(("delete", key))
        if key in self._raises_on:
            raise StorageError("delete_object", "AccessDenied", 403)


def claim(key: str) -> CleanupClaim:
    return CleanupClaim(object_id=uuid4(), object_key=key, attempts=1)


def run(coroutine):
    return asyncio.run(coroutine)


def sweep(repository, provider, **overrides):
    arguments = {
        "holder": HOLDER,
        "limit": 10,
        "lease_seconds": 300,
        "write_grace_seconds": 60,
    }
    arguments.update(overrides)
    return run(storage_cleanup.sweep(repository, provider, **arguments))


# ---------------------------------------------------------------------------
# The orderings
# ---------------------------------------------------------------------------


def test_the_provider_delete_precedes_the_finish_for_every_object():
    """Finish-then-delete loses objects permanently, and nothing would find them.

    `cleanup_completed_at` is the only thing that takes a row out of the claim's
    queue. Set it before the provider has been asked and a worker that dies in
    between leaves bytes no row will ever name again -- and section 4 forbids an
    orphan scan, so there is no second mechanism. Deletion is at least once by
    construction, which is safe only because an absent-key DELETE was MEASURED at
    204 in Run 5 rather than inherited from the S3 documentation.
    """
    transcript = Transcript(events=[])
    first, second = claim("k1"), claim("k2")
    repository = FakeRepository(transcript, claims=[first, second])
    provider = FakeProvider(transcript)

    sweep(repository, provider)

    pairs = [name for name in transcript.names() if name in {"delete", "finish"}]
    assert pairs == ["delete", "finish", "delete", "finish"], (
        f"the sweep did not delete before finishing each object: {pairs}"
    )


def test_intents_are_expired_before_the_claim_looks_for_tombstones():
    """The claim looks for tombstones, and expiry is what makes them.

    Reversed, every intent that expired during the last interval waits a whole
    further sweep. Nothing is incorrect about that and nothing else would notice.
    """
    transcript = Transcript(events=[])
    repository = FakeRepository(transcript, claims=[claim("k1")], expired=3)
    provider = FakeProvider(transcript)

    report = sweep(repository, provider)

    names = transcript.names()
    assert names.index("expire_intents") < names.index("claim")
    assert report.expired == 3


def test_the_worker_stops_claiming_work_when_its_lease_is_nearly_gone():
    """It abandons the tail of the batch rather than deleting what it may not hold.

    The margin is one provider call's worst case, derived from the adapter's own
    timeout constants. Here the clock is driven forward past the deadline after
    the first object, so the second must not be touched.

    Nothing breaks without this -- a second worker's delete is a no-op and the
    finish returns False -- but the double claim inflates `cleanup_attempts`,
    which is the one signal that tells an operator an object keeps killing its
    worker.
    """
    transcript = Transcript(events=[])
    first, second, third = claim("k1"), claim("k2"), claim("k3")
    repository = FakeRepository(transcript, claims=[first, second, third])
    provider = FakeProvider(transcript)

    # A monotonic clock the test drives: 0 at the start, then far past the
    # deadline. `lease_seconds` is 300 and the margin is well under that, so the
    # first object is inside the window and the rest are not.
    ticks = iter([0, 0, 400, 400, 400])

    report = run(
        storage_cleanup.sweep(
            repository,
            provider,
            holder=HOLDER,
            limit=10,
            lease_seconds=300,
            write_grace_seconds=60,
            now=lambda: next(ticks),
        )
    )

    assert [key for name, key in transcript.events if name == "delete"] == ["k1"]
    assert report.deleted == 1
    assert report.abandoned == 2, (
        "the worker either kept deleting past its lease or dropped the tail silently"
    )


def test_a_lease_no_longer_than_one_provider_call_gets_no_work_done():
    """The margin has to be OBSERVABLE, or the test above is only a relationship.

    `test_the_margin_is_derived_from_the_adapter_and_not_restated` asserts the
    arithmetic and cannot see whether the number reaches the loop. So: a lease
    exactly as long as one provider call's worst case leaves no time to make one,
    and every claimed object must be abandoned untouched. With the margin removed
    the deadline moves a whole lease into the future and all three are deleted,
    which is what this goes red on.

    A lease that short is a real configuration mistake rather than a contrivance
    -- `--lease-seconds 60` with the adapter's timeouts is exactly this.
    """
    transcript = Transcript(events=[])
    repository = FakeRepository(transcript, claims=[claim("k1"), claim("k2"), claim("k3")])
    provider = FakeProvider(transcript)

    report = run(
        storage_cleanup.sweep(
            repository,
            provider,
            holder=HOLDER,
            limit=10,
            lease_seconds=storage_cleanup.lease_margin_seconds(),
            write_grace_seconds=60,
            now=lambda: 0,
        )
    )

    assert [name for name, _ in transcript.events if name == "delete"] == [], (
        "the worker started a provider call with less than one call's worth of "
        "lease left, so the margin reaches nothing"
    )
    assert report.abandoned == 3
    assert report.deleted == 0


def test_the_margin_is_derived_from_the_adapter_and_not_restated():
    """Two numbers with one true relationship is D234's shape.

    Asserted against the adapter's constants rather than against a literal: a
    test comparing `60 == 60` is the tautology `hash_memory_budget_mb` was caught
    by, where the expected value was computed from the same three constants the
    code used.
    """
    from app import storage_client

    assert storage_cleanup.lease_margin_seconds() == storage_client.TOTAL_ATTEMPTS * (
        storage_client.CONNECT_TIMEOUT_SECONDS + storage_client.READ_TIMEOUT_SECONDS
    )


# ---------------------------------------------------------------------------
# Failure, which is three different things
# ---------------------------------------------------------------------------


def test_a_provider_failure_leaves_the_object_unfinished_so_the_lease_retries_it():
    """Finishing on a failed delete records a deletion that did not happen.

    There is no orphan scan to catch it later, so the object would be billed
    forever. Leaving the lease to expire is the retry mechanism -- the only one
    the design has.
    """
    transcript = Transcript(events=[])
    doomed, healthy = claim("bad"), claim("good")
    repository = FakeRepository(transcript, claims=[doomed, healthy])
    provider = FakeProvider(transcript, raises_on={"bad"})

    report = sweep(repository, provider)

    # Filtered before destructuring: a comprehension that unpacks every event
    # first tears `("delete", "bad")` into three characters.
    finished = [event[1][0] for event in transcript.events if event[0] == "finish"]
    assert doomed.object_id not in finished, (
        "an object whose provider DELETE raised was marked collected. It will "
        "never be claimed again and nothing else looks for it"
    )
    assert healthy.object_id in finished, (
        "one unreachable key ended the batch; a hundred-object sweep must not "
        "stop at its first failure"
    )
    assert report.failed == 1
    assert report.failed_ids == [str(doomed.object_id)]
    assert report.deleted == 1


def test_a_lost_lease_is_counted_apart_from_a_failure():
    """`finish` returning False is not an error and must not read as one.

    The worker's lease expired while it was working and somebody else claimed the
    row. The object IS deleted -- the work was done -- so reporting it as a
    failure would send an operator looking for a problem that does not exist, and
    folding it into `finished` would hide a worker whose lease is too short.
    """
    transcript = Transcript(events=[])
    lost = claim("k1")
    repository = FakeRepository(transcript, claims=[lost], finish_returns={lost.object_id: False})
    provider = FakeProvider(transcript)

    report = sweep(repository, provider)

    assert report.lease_lost == 1
    assert report.failed == 0
    assert report.finished == 0
    assert report.deleted == 1


def test_the_report_never_carries_an_object_key():
    """A key is the unguessable half of a bearer credential (STO-URL-001).

    The report is printed by an operator command and lands in a terminal, a
    scrollback and possibly a ticket. Ids are the caller's own and travel in
    their URLs already; keys are not.
    """
    transcript = Transcript(events=[])
    doomed = claim("objects/alpha-dev/v1/8f14e45f-ceea-467a-9f16-7b8b1a0a4a55")
    repository = FakeRepository(transcript, claims=[doomed])
    provider = FakeProvider(transcript, raises_on={doomed.object_key})

    report = sweep(repository, provider)

    rendered = repr(report.as_dict())
    assert doomed.object_key not in rendered, "the sweep report carries an object key"
    assert str(doomed.object_id) in rendered, (
        "the report names neither the key nor the id, so a failing object cannot "
        "be identified at all"
    )


# ---------------------------------------------------------------------------
# The arguments the plane depends on
# ---------------------------------------------------------------------------


def test_the_write_grace_reaches_the_claim():
    """0016's fourth argument is the whole of ADR 0111 from this side.

    A sweep that dropped it -- or sent a zero -- would collect objects whose
    presigned upload URL is still live, which is the defect 0016 exists to close.
    The database refuses a negative grace and cannot refuse a wrong one.
    """
    transcript = Transcript(events=[])
    repository = FakeRepository(transcript, claims=[])
    provider = FakeProvider(transcript)

    sweep(repository, provider, write_grace_seconds=77)

    ((_, arguments),) = [event for event in transcript.events if event[0] == "claim"]
    assert arguments == (HOLDER, 10, 300, 77)


def test_a_negative_write_grace_is_refused_before_any_round_trip():
    """Refused here as well as in 0016, and the duplication is deliberate.

    A negative grace moves the deadline earlier, which is the defect
    reintroduced through the argument that closes it. The database raises AP422
    for a caller that gets past this; this gives the operator a message without
    a round trip, and without having expired any intents first.
    """
    transcript = Transcript(events=[])
    repository = FakeRepository(transcript, claims=[])

    with pytest.raises(ValueError, match="write_grace_seconds"):
        sweep(repository, FakeProvider(transcript), write_grace_seconds=-1)

    assert transcript.events == [], (
        "the sweep expired intents before validating its arguments, so a bad "
        "call still mutated the plane"
    )


def test_the_configured_write_grace_errs_high_rather_than_low():
    """The asymmetry is the argument, and it is worth asserting rather than noting.

    Too generous costs a delay before bytes stop being billed. Too small orphans
    an object nothing will ever find. The value is REASONED and not measured --
    twice the largest signature leeway this project has measured anywhere, which
    is PostgREST's thirty seconds on `exp` (D241) -- and this test is what makes a
    later reduction a deliberate act rather than a tidy-up.
    """
    assert storage_cleanup.WRITE_GRACE_SECONDS >= 30, (
        "the write grace is at or below the largest signature leeway this "
        "project has measured in any validator. R2's own tolerance is still "
        "unmeasured, so a value under that has no evidence behind it"
    )


def test_two_workers_never_share_a_holder():
    """The lease's entire safety rests on this, and nothing else enforces it.

    `finish_cleanup` matches on the holder string, so two processes sharing one
    could mark collected an object the other is still deleting.
    `cleanup_lease_holder` is unbounded `text` with only a non-empty CHECK -- the
    database cannot help.
    """
    identities = {storage_cleanup.worker_identity() for _ in range(200)}
    assert len(identities) == 200, (
        "worker_identity repeated itself. Host and pid alone are not unique -- "
        "pids are reused and two containers can share a hostname"
    )


# ---------------------------------------------------------------------------
# The entry point the operator command actually reaches
# ---------------------------------------------------------------------------


def test_the_environment_entry_point_passes_the_configured_grace(monkeypatch):
    """`sweep_from_environment` is the only path production takes, and nothing
    else here touches it.

    Every test above calls `sweep` directly with a grace the test chose, so a
    `sweep_from_environment` that passed `0` -- or dropped the argument, or
    invented a number -- would leave all of them green while collecting objects
    whose upload URL is still live in the one place it matters. That is the gap a
    mutation battery finds by changing a line no test executes, and D342's shape
    from the other side: there a rig made the product's decision itself, here the
    product's own decision sat on a line no test reached.

    The fakes replace the pool, the config and the adapter -- everything that
    needs a cluster or a bucket -- and deliberately do NOT replace `sweep`. What
    is under test is the wiring, so the real `sweep` has to run.
    """
    import contextlib
    import types

    from app import db, storage_cleanup, storage_client
    from app import settings as settings_module
    from app.storage_repository import StorageRepository

    seen: dict[str, object] = {}

    class Sentinel(Exception):
        """Raised from the fake repository, once the arguments are captured."""

    def fake_claim(self, *, holder, limit, lease_seconds, write_grace_seconds):
        seen.update(
            holder=holder,
            limit=limit,
            lease_seconds=lease_seconds,
            write_grace_seconds=write_grace_seconds,
        )
        raise Sentinel

    async def fake_expire(self, *, limit):
        return 0

    monkeypatch.setattr(StorageRepository, "expire_intents", fake_expire)
    monkeypatch.setattr(StorageRepository, "claim_cleanup_batch", fake_claim)

    monkeypatch.setattr(
        settings_module,
        "load",
        lambda *, mode: types.SimpleNamespace(conninfo="host=nowhere", pool_size=2),
    )
    monkeypatch.setattr(
        storage_client,
        "load_config",
        lambda: storage_client.StorageConfig(
            endpoint="https://example.invalid",
            bucket="apg-test",
            prefix="objects/test/",
            access_key_id="a" * 32,
            secret_access_key="b" * 64,
            upload_url_ttl_seconds=900,
            download_url_ttl_seconds=300,
            max_upload_bytes=1024,
        ),
    )
    # No client is built, so no credential chain is consulted and no socket is
    # opened by the adapter's constructor.
    monkeypatch.setattr(storage_client, "build_client", lambda config: object())
    monkeypatch.setattr(db, "build_pool", lambda conninfo, size: object())
    monkeypatch.setattr(db, "pool_lifespan", lambda pool: contextlib.nullcontext())

    with pytest.raises(Sentinel):
        run(storage_cleanup.sweep_from_environment(limit=7, lease_seconds=123))

    assert seen["write_grace_seconds"] == storage_cleanup.WRITE_GRACE_SECONDS, (
        "the production entry point does not pass the configured write grace, so "
        "ADR 0111's predicate is disarmed on the only path that runs"
    )
    assert seen["limit"] == 7
    assert seen["lease_seconds"] == 123
    assert isinstance(seen["holder"], str) and seen["holder"]


def test_the_environment_entry_point_asks_for_storage_mode(monkeypatch):
    """One image runs two modes and only one of them holds an R2 credential.

    `settings.load(mode="auth")` would resolve a signing key path and no storage
    settings -- so a sweep started in the wrong mode would either fail obscurely
    or, worse, succeed against the wrong configuration. ADR 0101 makes the mode a
    required input precisely so it cannot be defaulted, and this asserts the
    entry point supplies the right one.
    """
    import contextlib
    import types

    from app import db, storage_cleanup, storage_client
    from app import settings as settings_module

    modes: list[str] = []

    def record(*, mode):
        modes.append(mode)
        raise RuntimeError("stop here")

    monkeypatch.setattr(settings_module, "load", record)
    monkeypatch.setattr(db, "build_pool", lambda conninfo, size: object())
    monkeypatch.setattr(db, "pool_lifespan", lambda pool: contextlib.nullcontext())
    monkeypatch.setattr(storage_client, "load_config", lambda: types.SimpleNamespace())

    with pytest.raises(RuntimeError, match="stop here"):
        run(storage_cleanup.sweep_from_environment(limit=1, lease_seconds=60))

    assert modes == ["storage"]
