# 0099 — The budget is divided four ways, and the remainder must cover the pooler's pool

Status: accepted
Date: 2026-08-15
Session: 7, Run 1
Settles: D309, D327
Extends: [0070](0070-the-connection-budget-is-divided-not-granted-twice.md)

## Context

Session 7 adds a fourth claimant on `max_connections`. ADR 0070 divides the
budget between three — the API, the auth service and the application — and the
plan's D309 recorded that the division is exact with no slack:

    available   = 50 − 3 = 47
    api         = 13   (rest pool 10 + 3 reserved)
    auth        =  6   (app pool 4 + 2 reserved)
    headroom    =  5
    application = 23   (the remainder)

**Measured before deciding, with the current tree as the control.** The rig ran
both arithmetics that exist over this budget — `config._validate_connection_budget`
on the manifest side and `postgres-bootstrap.connection_limits` on the bootstrap
side — for storage pools 0 through 8, against the example manifest:

| storage | manifest sum | fits ≤ 50 | application remainder | ≥ pooler pool 20 |
|---|---|---|---|---|
| **control (none)** | 44 | yes | **23** | **yes** |
| pool 1 | 47 | yes | 20 | yes (exactly) |
| pool 2 | 48 | yes | 19 | **no** |
| pool 4 | 50 | yes | 17 | **no** |
| pool 6 | 52 | **no** | 15 | no |

The control passes on both sides, so the rig can tell success from failure.

**Two findings, and the second is the one that outranks the session.**

**The budget cannot absorb a fourth claimant at 50.** A storage pool of 4 — the
same size the auth service was given for the same kind of work — puts the
manifest sum at exactly the ceiling and the application's remainder at 17.

**Nothing compares the two arithmetics, and they are not the same arithmetic.**
The manifest check charges `database.pool_size` (20) for the application; the
bootstrap plane grants the application whatever is *left*. They agree today by
coincidence — 23 ≥ 20, with 3 to spare — and no code asserts it. The bootstrap's
only guard is `application < 1`.

That gap is what a fourth claimant walks into. `default_pool_size` is per
`(user, database)` and `app_runtime` is the only application user in the
pooler's userlist, so the pooler alone can hold `database.pool_size` server
connections. Give `app_runtime` a `CONNECTION LIMIT` below that and the pooler
cannot fill its own pool: the 21st backend is refused by PostgreSQL with *too
many connections for role*, and PgBouncer reports it to the client. **The
failure names the role, so it reads as a credential or a capacity problem at the
pooler, and the number that caused it was computed in a different file.**

This is D327, and it is not a Session 7 defect. It is a latent one that Session 7
is the first change large enough to reach.

## Decision

**Four claimants, one division, and the remainder is checked against the pool.**

    available   = max_connections − superuser_reserved_connections   (live, queried)
    api         = database.api_connection_budget                     (published)
    auth        = database.auth_connection_budget                    (published)
    storage     = database.storage_connection_budget                 (published, new)
    application = available − api − auth − storage − OPERATIONAL_CONNECTION_HEADROOM

    REFUSE when application < database.pooler_pool_size

`storage.pool_size` defaults to **4** and is charged `STORAGE_RESERVED_CONNECTIONS
= 2`, the auth service's reservation and for the auth service's stated reason: it
holds no `LISTEN` connection, so what is charged beyond the pool is the
startup-and-recovery overlap. The section is `storage:`, which already exists and
is already this service's section — the precedent is `api.rest.pool_size` and
`api.app.pool_size` living with the services they bound.

**`database.max_connections` rises from 50 to 56**, which is what keeps the
application's remainder at exactly 23. The storage claimant is paid for by
raising the ceiling rather than by taking from another claimant, and the
arithmetic that says so is the point:

    56 − 3 = 53 usable
    53 − 13 − 6 − 6 − 5 = 23        unchanged from before this session

**The memory cost was measured, not assumed.** `unreclaimable_mb` moves from 292
to 304 MiB per project — 608 MiB for two projects against a 1600 MiB host
guardrail. Raising `max_connections` costs `PER_BACKEND_ANON_MB` × 6 = 12 MiB per
cluster, and the guardrail has over a gigabyte unspoken for.

**The invariant is checked in the bootstrap plane, not the manifest**, and that
requires v11 to publish `database.pooler_pool_size`. ADR 0070's third property is
why: the application's figure depends on what the *live* server reports, so the
plane that can ask the server is the plane that does the subtraction — and it is
therefore the only plane that can compare the result to anything. A manifest-side
check would compare a rendered guess about `superuser_reserved_connections`
against a live number, which is the shape D94 refused.

The manifest check keeps its own sum, unchanged in shape and extended by one
term. It catches the same class earlier and cheaper, and it does not need to be
right about the live server to be useful.

## Alternatives

**Take storage's six out of `api.rest.pool_size` (10 → 4).** Fits at 50 with no
cluster restart and no schema default change. Rejected: it makes a measured,
deployed, proved surface pay for a service that has not been built yet, and the
regression would land on two live projects before any storage code exists to
justify it. If the ceiling has to rise eventually, raising it before the
regression is cheaper than after.

**Give storage `pool_size: 1`.** The only size that fits at 50 while leaving the
remainder at the pooler's pool exactly. Rejected twice over: the application gets
zero direct sessions the moment the pooler is busy — the exact failure ADR 0070
refused when it declined to cap `app_runtime` at `database.pool_size` — and a
one-connection pool for an HTTP service is a queue with a pool's interface.

**Take it from `OPERATIONAL_CONNECTION_HEADROOM`.** Rejected, and the plan named
this as a stop condition before the measurement was run. The headroom is what
leaves a `psql` available when this arithmetic is wrong, and this ADR is evidence
that it can be wrong.

**Publish the application's ceiling in the document so the manifest can check
it.** Rejected on ADR 0070's third property, which is still the correct one: a
rendered document naming the application's ceiling would be publishing a guess
about a server nobody has queried (D94).

**Leave the pooler invariant unchecked and simply pick numbers that satisfy it.**
Rejected. That is the state this ADR found — the numbers satisfied it by
coincidence and nothing said so — and the next claimant would rediscover it. The
value of the check is not this session's arithmetic; it is that the arithmetic
cannot silently stop being true.

## Consequences

- **Outputs v11 carries two new fields**, `database.storage_connection_budget`
  and `database.pooler_pool_size`. Documents at v10 stop validating until each
  project is redeployed, the cost every version bump since v2 has imposed and
  ADR 0053 anticipated.
- **`connection_limits` returns four limits and takes one more argument.** As in
  ADR 0070, together is the point: a claimant that could be applied without the
  others having been computed is the failure D161 describes.
- **The clusters need a restart to take `max_connections` 56.** It is not a
  reload-able setting. This lands in the Run 10 host trip's sequence and in the
  operator guide, and until it happens a redeployed project renders v11 and the
  bootstrap reads a live `max_connections` of 50 — where `connection_limits`
  now **refuses**, with a message naming the restart, rather than handing out a
  remainder of 17 that nothing would have questioned.
- **A cluster whose live `max_connections` has not caught up fails loudly at
  bootstrap.** That is the intended behaviour and the reason the check is
  bootstrap-side: the alternative is a pooler that half works.
- D309 is closed. **D327 is closed by the check rather than by the numbers**, and
  the numbers that hid it are recorded above so the next claimant can see what
  the spare 3 was.
