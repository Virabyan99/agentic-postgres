# 0104 — The lease is the correctness mechanism, and the row lock is not

Status: accepted
Date: 2026-08-16
Session: 7, Run 3
Affects: STO-COMPLETE-001

## Context

Migration 0014 needs a cleanup queue. A tombstoned object has to be deleted from
R2 and then marked done, and two workers must not delete the same object twice
or leave one uncollected forever.

The obvious mechanism is `FOR UPDATE SKIP LOCKED`. The obvious alternative is a
lease column pair — `cleanup_lease_holder`, `cleanup_lease_expires_at` — claimed
by a compare-and-set update. Neither had been measured in this repository:
nothing under `docs/`, `migrations/`, `src/` or `tests/` mentioned SKIP LOCKED at
all, so the plan's "the lease claim under concurrency" rested on nothing.

**Both were measured on the locked `pgvector/pgvector:pg18` digest (server 18.4),
each with a control that had to come out the other way.**

*Row locks* — two concurrent claimants with `FOR UPDATE SKIP LOCKED` took
**different rows** (1 and 2) and neither blocked; with one row available the
second got **nothing** rather than blocking. The control is what makes that
evidence: the identical query **without** `SKIP LOCKED` left the second claimant
blocked until it was killed by `lock_timeout`. So Arm 1 measured lock skipping
rather than row ordering.

*CAS lease* — two concurrent claims against one expired lease produced **exactly
one winner**, the loser updating zero rows: READ COMMITTED re-evaluates the
`WHERE` against the new row version after the block clears, and the refreshed
`lease_expires_at` no longer satisfies it. An expired lease was reclaimable; a
live one was not stealable. Control: the same two claims run *sequentially* with
the lease free both won, so the loss in Arm 1 was contention and not a broken
predicate.

*(The CAS rig's first version wrote `UPDATE … RETURNING` as a scalar subquery,
which is a syntax error, and every arm came back false. Control A is what said
the rig was broken rather than the design — it must be true whatever the
concurrency does. Recorded because an all-false result reads like a finding.)*

## Decision

**Both, and they are not substitutes.**

- **The lease pair is the correctness mechanism.** The work a cleanup worker
  does is a `DeleteObject` against R2 — a network call to a third party, which
  cannot happen inside the database transaction. So the claim has to survive the
  transaction that made it, and a row lock by definition does not: it is released
  at COMMIT, and released at crash. Only a value in a column outlives the
  connection that wrote it.

- **`FOR UPDATE SKIP LOCKED` is the throughput mechanism.** It is what stops two
  workers claiming a *batch* from serialising on each other. Measured: without
  it the second claimant blocks; with it, it takes the next row.

The claim is therefore one statement — an `UPDATE` whose target rows come from a
`SELECT … FOR UPDATE SKIP LOCKED` subquery — and its predicate names the lease,
not the lock:

```sql
WHERE state = 'tombstoned'
  AND (cleanup_lease_expires_at IS NULL OR cleanup_lease_expires_at < now())
```

**A worker that crashes loses its lease by expiry, not by disconnection.** That
is the property the whole design turns on and it is why the expiry is a stored
timestamp rather than a session fact.

## Consequences

**A crashed worker's object is retried, not stranded**, after at most one lease
period. `cleanup_attempts` is incremented on claim rather than on success, so an
object that kills its worker repeatedly is visible rather than invisible.

**Deletion must be idempotent at the provider**, because the lease guarantees
*at least once*, never exactly once. A worker can delete the object, crash before
recording it, and have a second worker delete it again. S3-compatible
`DeleteObject` is idempotent on an absent key, which is what makes that
acceptable — and it is a property to re-measure against R2 in Run 5 rather than
inherit from the S3 documentation.

**Removing either half breaks something different, and only one of them loudly.**
Drop the lease and keep the lock: every test still passes offline, because no
offline test spans two transactions with a network call between them, and
production strands every object whose worker dies mid-delete. Drop the lock and
keep the lease: correctness holds and throughput collapses to one worker. The
first is the dangerous one, and the migration's comment says so where the
predicate is written.

## Alternatives considered

**A session-level advisory lock per object.** Rejected on a measurement this
repository already owns: Session 6 Run 8 found that a *session* advisory lock
survives `COMMIT`, so through a transaction-mode pooler it is stranded on a
connection the next caller may not get. The transaction-scoped form does not
survive the commit, which is exactly the property the provider call needs. Both
forms fail, for opposite reasons.

**`SKIP LOCKED` alone, with the work inside the transaction.** Rejected because
it requires the R2 delete to happen inside a database transaction. Holding a
transaction open across a third-party network call ties a connection — out of a
budget ADR 0099 divides to the last unit — to a remote service's latency and
timeouts.

**A lease with no row lock.** Correct, and measured to be correct. Rejected for
batch claiming only: with `LIMIT n > 1` two workers contend row by row and the
second blocks on each. It stays the fallback if the `SKIP LOCKED` subquery ever
has to go, and the correctness argument does not change if it does.

**A separate queue table.** Rejected as a second authority for an object's state.
The state column already says whether an object is tombstoned; a queue row that
could disagree with it is a row that eventually will.
