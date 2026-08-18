# 0111 — An object is collectable only once nothing can still write to its key

Status: accepted
Date: 2026-08-18
Session: 7, Run 8
Affects: ADR 0104, ADR 0091, D348, `migrations/templates/0014`,
`migrations/templates/0016`, `services/auth-api/app/storage_cleanup.py`

## Context

Migration 0014 released the cleanup plane in Run 3. Its claim collects any
tombstone with no live lease and no `cleanup_completed_at`:

```sql
WHERE c.state = 'tombstoned'
  AND c.cleanup_completed_at IS NULL
  AND (c.cleanup_lease_expires_at IS NULL OR c.cleanup_lease_expires_at < now())
```

Run 8 wrote the first caller those functions have ever had, and the gap was
immediately visible.

`storage_tombstone` moves a **pending** object, deliberately — its own comment
says so, because an abandoned intent has to be collectable without ever having
been completed. But a pending object carries a presigned PUT minted for
`intent_expires_at`, and **a tombstone does not revoke it**. A presigned URL is a
bearer credential with a short life; nothing in this system can withdraw one, and
`storage_service.download_url` already says so in as many words about the GET
side.

So:

```
T+0    intent created; upload URL valid until T+900
T+10   DELETE /objects/{id}        -> state = tombstoned
T+11   cleanup claims it, DELETEs an absent key at R2 (204), finishes
T+20   the holder PUTs to the still-valid URL -> 200, first write, bytes land
```

The row now reads `tombstoned` with `cleanup_completed_at` set, so the claim will
never return it again. And section 4 of the session plan **forbids an orphan
scan**, on the explicit ground that a reconciler which lists and deletes
untracked objects can delete data a human put there to recover something. So
nothing in this system would ever find those bytes. They are billed forever.

## What was measured

Against the locked `pgvector/pgvector:pg18` digest, all fifteen released
migrations applied **as `migration_user`** (D285), through the product's own
`build_statements` pre-state:

| object | claimed by `storage_claim_cleanup_batch`? |
|---|---|
| pending, `intent_expires_at` an hour away, tombstoned one statement earlier | **yes** — the defect |
| pending, `intent_expires_at` a minute in the past, tombstoned | yes — control |
| completed to `available`, then tombstoned | yes — control |

Both controls came out the other way from what the defect arm needed, so the rig
could distinguish a claim that collects from one that does not. Without them the
first row would pass for a claim that had simply stopped working.

## Decision

**An object is collectable only once nothing can still write to its key.**
Migration **0016** adds the predicate, as a disjunction whose two sides are
different arguments:

```sql
AND (c.completed_at IS NOT NULL
     OR c.intent_expires_at < now() - make_interval(secs => p_write_grace_seconds))
```

*`completed_at IS NOT NULL`* — the object reached `available`, so its key already
holds bytes. Every upload URL this service mints carries `If-None-Match: *`,
measured in Run 5 to return **412 PreconditionFailed** on the second write, with
the arm that matters being a caller who **omits** the header and gets **403
SignatureDoesNotMatch** rather than an unconditional write. The condition is
cryptographic rather than cooperative, so no replayed PUT can reach a completed
key, and making an ordinary delete wait out the whole upload TTL would buy
nothing.

*`intent_expires_at < now() - grace`* — the object never completed, so its key is
empty and its presigned PUT would be a **first** write, which succeeds. The only
thing that stops it is the URL's own expiry, and that is `intent_expires_at` by
construction: the service presigns with the same TTL it writes into the row.

**Both halves of ADR 0104 are unchanged.** The lease predicate is still the
correctness mechanism and `FOR UPDATE SKIP LOCKED` is still throughput and
nothing else. This adds a clause; it does not revisit either.

## The grace is a parameter, and a negative one is refused

`p_write_grace_seconds` is the claim's fourth argument rather than a constant in
the migration. The right value is a fact about **the provider's** tolerance for a
signature whose expiry has just passed, and that belongs beside the adapter that
measures such things, not baked into a released migration a migration away from
its evidence — where changing it would need another migration.

The question is not hypothetical. **PostgREST allows thirty seconds of leeway on
`exp` and `nbf` where its documentation implies none** (D241, bisected: 30s
served, 31s refused, symmetrically). A validator that did the same would make a
bare `< now()` wrong.

A negative grace is **refused with `AP422`, not clamped**. `greatest(x, 0)` would
turn a caller's bug into silence, and the bug it would hide is precisely this
defect reintroduced through the argument that closes it.

## The three-argument form is dropped, not overloaded

Two functions answering "which objects are collectable" would be two authorities
for one rule, and the three-argument one is the version with the defect — so
leaving it callable would leave the defect callable by a caller that simply
passed fewer arguments. The `DROP` takes `storage_service`'s EXECUTE with it,
which is what makes the removal total rather than advisory, and a contract test
calls the old signature and requires the call to fail.

## Why 0016 and not an edit to 0014

ADR 0091's three conditions, checked rather than assumed, exactly as 0015 checked
them. Condition 1 holds — no cluster has 0014, both deployed projects being on
13. **Condition 2 fails**: 0014 applies perfectly well. ADR 0091 says in as many
words that *"a migration that merely did the wrong thing does not qualify"*, and
this is the second time in one session that its own answer has been a new file.

## Alternatives rejected

**Filter in the worker instead.** It cannot: the claim returns `(id, object_key,
attempts)` and no timestamps, so the worker has nothing to filter on. Adding the
timestamps to the return type so the worker could discard rows would also mean
the claim had already **leased** them and incremented `cleanup_attempts` — which
is the counter an operator reads to find an object that keeps killing its worker,
now inflated by objects nobody tried to delete.

**Refuse to tombstone a pending object.** This is where the reasoning started and
it is worse. An abandoned intent would then be uncollectable, which is the
accumulation `storage_expire_intents` exists to prevent, and DELETE would stop
being idempotent for an owner who calls it before uploading.

**Wait out the upload TTL for every object.** Correct and needlessly expensive:
an ordinary delete of a completed object would sit uncollected for the whole
upload TTL although its key is already unwritable. The disjunction costs one
clause and avoids it.

**Add an orphan scan as a backstop.** Refused by section 4 before this defect
existed, and the reason is unchanged: a reconciler that lists the bucket and
deletes what the database does not know about can delete data a human put there
to recover something. The absence of that backstop is exactly why this predicate
has to be right.

## Consequences

`storage_cleanup.WRITE_GRACE_SECONDS` is **60**, and it is **reasoned rather than
measured** — twice the largest signature leeway this project has measured in any
validator. R2's own tolerance is unmeasured: Run 5 established that an expired
presigned URL is refused (`ExpiredRequest`, 403) but not where the boundary sits.
The constant says so at its definition, and a contract test refuses a value at or
below thirty so that a later reduction is a deliberate act rather than a tidy-up.

The asymmetry is why an unmeasured value errs high: being generous costs a delay
before bytes stop being billed, and being wrong the other way orphans an object
nothing will ever find.

Four contract tests in `test_storage_plane.py` had their **fixtures** changed
from a default-TTL intent to `ttl=-60`, because a default-TTL pending object is
now correctly refused by the claim. Their assertions are unchanged and no weaker;
each says so in its docstring. That is a fixture following a narrowed definition,
not a currently-passing test being weakened to admit a new one.
