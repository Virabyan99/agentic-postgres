"""The cleanup sweep: the first caller migration 0014's cleanup plane ever had.

**Writing this is what found the defect migration 0016 fixes.** Run 3 released
the lease, the claim and the finish; Run 6 released the endpoints; nothing called
any of the three cleanup functions until now, and their only exercise was SQL
written inside two test modules. The moment a caller existed, the missing
predicate was obvious: the claim collected objects whose presigned upload URL was
still live. That is D348's rule arriving a second time in one session -- *a plane
is complete when a caller can be written against it, not when its tests pass.*

**Three orderings here are correctness, and none of them is arithmetic.**

*Delete before finish.* `cleanup_completed_at` is set only after the provider has
been asked to delete. The reverse order loses objects permanently: a worker that
recorded completion and then died would leave bytes nothing will ever look at
again, and there is no orphan scan by design (section 4 of the session plan --
a reconciler that lists and deletes untracked objects can delete data a human put
there to recover something). So deletion is **at least once**, which is safe only
because `DeleteObject` on an absent key was measured at 204 in Run 5 rather than
inherited from the S3 documentation.

*Expire before claim.* An intent past its deadline becomes a tombstone, and a
tombstone is what the claim looks for. Running them the other way round would
leave every newly expired intent waiting a whole sweep.

*Stop before the lease does.* The worker abandons the rest of its batch when the
lease has nearly run out, rather than deleting objects it may no longer hold.
Nothing breaks if it does not -- a second worker's DELETE is a no-op and
`finish_cleanup` returns False -- but the work is wasted and the double claim
inflates `cleanup_attempts`, which is the signal an operator reads to find an
object that keeps killing its worker.

**Nothing here logs an object key.** A key is the unguessable half of a bearer
credential; `STO-URL-001` is a canary scan across every sink. The report carries
counts and object ids, and object ids are already the caller's own and travel in
their URLs.
"""

from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field
from secrets import token_hex
from typing import Any

from app.storage_client import StorageError

#: How far past `intent_expires_at` an uncompleted object must be before its key
#: is collectable (migration 0016's fourth argument, ADR 0111).
#:
#: **This number is REASONED, not measured, and the distinction is the point.**
#: The right value is R2's tolerance for a presigned URL whose `X-Amz-Expires`
#: has just passed, and that has never been measured -- Run 5 measured expiry
#: rejection as a real outcome (`ExpiredRequest`, 403) but not where the boundary
#: sits. Sixty seconds is twice the largest leeway this project has ever measured
#: in any signature validator: PostgREST allows **thirty** on `exp` and `nbf`
#: where its documentation implies none, which is D241 and is why the question
#: gets asked of R2 at all rather than assumed away.
#:
#: What it costs to be generous is a delay before bytes stop being billed. What
#: it costs to be wrong in the other direction is an orphaned object nothing will
#: ever find, because there is no orphan scan by design. The asymmetry is why the
#: unmeasured value errs high.
#:
#: **Replace this with the measurement, not with a smaller guess.** The rig is a
#: presign with a short `ExpiresIn`, a PUT at increasing delays past it, and the
#: control is the same PUT before expiry returning 200.
WRITE_GRACE_SECONDS = 60


def lease_margin_seconds() -> int:
    """How long before the lease expires the worker stops taking on more deletes.

    Not a tuning knob: it is one provider call's worst case, which is exactly
    what the worker is about to spend if it starts another one. Derived from the
    adapter's own measured constants rather than restated here -- two numbers
    with one true relationship between them is D234's shape, and it is a
    function rather than a module constant so that a change to
    `TOTAL_ATTEMPTS` cannot leave a stale copy behind.
    """
    from app import storage_client

    return storage_client.TOTAL_ATTEMPTS * (
        storage_client.CONNECT_TIMEOUT_SECONDS + storage_client.READ_TIMEOUT_SECONDS
    )


@dataclass(frozen=True, slots=True)
class SweepReport:
    """What one sweep did. Counts, and the ids of what it could not finish.

    Deliberately not "succeeded / failed": five of these are different outcomes
    an operator acts on differently, and collapsing them would hide the two that
    matter. `lease_lost` is not a failure and `failed` is not a lost object.
    """

    #: Pending intents past their deadline, moved to `tombstoned` this sweep.
    expired: int = 0
    #: Tombstones leased by this worker.
    claimed: int = 0
    #: Provider DELETEs that returned. Includes absent keys, which return 204.
    deleted: int = 0
    #: Rows this worker marked collected.
    finished: int = 0
    #: Deletes that succeeded but whose `finish` found the lease gone. Not an
    #: error: the object IS deleted, and a second worker holds the row.
    lease_lost: int = 0
    #: Provider calls that raised. The lease is deliberately left to expire so
    #: the object is retried, rather than being finished on a failed delete.
    failed: int = 0
    #: Claimed objects the worker did not reach before its lease ran short.
    abandoned: int = 0
    #: Ids only, never keys. An object that keeps failing is the thing an
    #: operator needs to name; its key is a credential half.
    failed_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def worker_identity() -> str:
    """A holder string unique to this process, and the uniqueness is load bearing.

    The lease's entire safety rests on two workers never sharing a holder: the
    finish is `WHERE cleanup_lease_holder = p_holder`, so if a second process
    used the same string it could mark collected an object the first is still
    deleting. Host and pid alone are not enough -- pids are reused, and two
    containers can share a hostname on different hosts -- so a random component
    is included rather than assumed unnecessary.

    **`os.uname()` rather than `socket.gethostname()`**, and that is not a style
    choice. `test_the_service_never_constructs_a_network_jwks_client` refuses any
    reference to a network-capable module anywhere under this service, because a
    verifier able to fetch its own keys has whatever answered the request as its
    trust anchor. `socket` is on that list and it tripped on the first run of
    this module.

    The right response was to drop the capability, not to find another spelling
    of it: `os.uname().nodename` is the same fact from a call that cannot open a
    connection, whereas `socket` is a module that can. `storage_client.redact`
    makes the same choice for the same reason and says so -- buying an exemption
    for the safe half of a network module is how the unsafe half arrives.

    Bounded at a length a human can read in a report. `cleanup_lease_holder` is
    unbounded `text` with a non-empty CHECK, so nothing else enforces this.
    """
    host = os.uname().nodename[:40] or "unknown"
    return f"{host}:{os.getpid()}:{token_hex(4)}"


async def sweep(
    repository: Any,
    provider: Any,
    *,
    holder: str,
    limit: int,
    lease_seconds: int,
    write_grace_seconds: int,
    now: Any = time.monotonic,
) -> SweepReport:
    """One pass: expire what is stale, then collect what is collectable.

    `repository` and `provider` are passed in rather than built here so that a
    test can drive the orderings without a cluster or a bucket -- and so that
    this module holds no configuration, which is what lets the operator command
    reach it through the container without reproducing any of the service's
    setup (ADR 0093).

    `now` is injected for the same reason and only for the lease deadline. It is
    a MONOTONIC clock, not a wall clock: the lease margin is a duration, and a
    wall clock that steps backwards during an NTP correction would make the
    worker think it has time it does not.
    """
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if lease_seconds < 1:
        raise ValueError("lease_seconds must be at least 1")
    if write_grace_seconds < 0:
        # Refused here as well as in the database, and the duplication is
        # deliberate: 0016 raises AP422 for a caller that gets past this, and
        # this gives the operator command a message before a round trip.
        raise ValueError("write_grace_seconds must be zero or more")

    expired = await repository.expire_intents(limit=limit)

    claims = await repository.claim_cleanup_batch(
        holder=holder,
        limit=limit,
        lease_seconds=lease_seconds,
        write_grace_seconds=write_grace_seconds,
    )

    started = now()
    deadline = started + lease_seconds - lease_margin_seconds()

    deleted = finished = lease_lost = failed = abandoned = 0
    failed_ids: list[str] = []

    for claim in claims:
        if now() >= deadline:
            # The rest keep their lease until it expires and are re-claimed
            # then. Counted rather than silently dropped, because a sweep that
            # abandons most of its batch every time is a limit set too high for
            # the lease and nothing else would say so.
            abandoned += 1
            continue

        try:
            await provider.delete_object(claim.object_key)
        except StorageError:
            # The lease is NOT released and the row is NOT finished. Letting the
            # lease expire is what retries the object; finishing it here would
            # record a deletion that did not happen, and there is no orphan scan
            # to find it later. The exception carries an operation and a
            # provider code and never a target, so it is safe to count -- but
            # it is not re-raised, because one unreachable key must not end a
            # batch of a hundred.
            failed += 1
            failed_ids.append(str(claim.object_id))
            continue

        deleted += 1
        if await repository.finish_cleanup(object_id=claim.object_id, holder=holder):
            finished += 1
        else:
            lease_lost += 1

    return SweepReport(
        expired=expired,
        claimed=len(claims),
        deleted=deleted,
        finished=finished,
        lease_lost=lease_lost,
        failed=failed,
        abandoned=abandoned,
        failed_ids=failed_ids,
    )


async def sweep_from_environment(*, limit: int, lease_seconds: int) -> SweepReport:
    """Build the plane from the container's own environment and run one sweep.

    This is the entry point the operator command reaches, and everything it
    assembles is assembled the way `main.py` assembles it -- the same
    `load_config`, the same `build_pool`, the same `StorageRepository`. ADR 0093
    is why the command runs this rather than importing anything: the code that
    talks to the cluster and to R2 runs in the process that holds the
    credentials for both, at the versions its own image pins.

    The pool is opened and closed around the single sweep. A cleanup pass is not
    a long-lived service and holding connections from ADR 0099's budget between
    passes would charge the deployment for a worker that is not running.
    """
    from app import db, storage_client
    from app import settings as settings_module
    from app.storage_client import BoundedR2, R2Adapter
    from app.storage_repository import StorageRepository

    settings = settings_module.load(mode="storage")
    config = storage_client.load_config()
    adapter = R2Adapter(config)

    pool = db.build_pool(settings.conninfo, size=settings.pool_size)
    async with db.pool_lifespan(pool):
        return await sweep(
            StorageRepository(pool),
            BoundedR2(adapter),
            holder=worker_identity(),
            limit=limit,
            lease_seconds=lease_seconds,
            write_grace_seconds=WRITE_GRACE_SECONDS,
        )
