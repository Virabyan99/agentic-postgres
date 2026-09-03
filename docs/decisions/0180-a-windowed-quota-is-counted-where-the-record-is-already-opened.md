# 0180 — A windowed quota is counted where the record is already opened

- **Status:** accepted
- **Date:** 2026-09-04
- **Session:** 16, Run 5 (`AGT-QUOTA-001`, D865, D902–D905)
- **Related:** **ADR 0129** (four budgets, independent by decision — read first,
  per the stage plan's *Must not*), **ADR 0179** (a capability narrows a budget
  and may never widen one), **ADR 0141** (`begin` runs before the scope check,
  so a denial is audited), **ADR 0171** (measure at `read committed`, with a
  control, and read the outcome from the row count), ADR 0135 (the audit record
  is written by SECURITY DEFINER functions as the caller), **D407** (the agent
  plane holds no database credential), ADR 0070, ADR 0002.

## Context

D865 is right that this is the **fifth** budget and the first one that is
genuinely different: its state outlives a request, two processes contend on it,
and it can be wrong after a restart. ADR 0129's four are none of those — rows,
bytes and elapsed time are decided inside one call, and concurrency is a
semaphore in one process.

Run 4 finished the per-capability half of ADR 0129's table (D898). This is the
first bound that needs a table.

### The constraint that decides the mechanism

**The agent plane holds no database credential** (D407). Every database
interaction is an upstream PostgREST request made as the caller, and a write is
already **four** of them — context, `agent_audit_begin`, the write,
`agent_audit_complete` — while a read is three. Each holds a connection from a
pool shared with human callers, and **none of it has ever been timed against the
deployment** (§9, standing since Session 8).

A quota checked in its own request would make that five and four: a 25–33%
increase in round trips, on a path whose latency nobody knows.

### What was measured

**The race, at the level the deployment runs** (ADR 0171's pattern — two
overlapping transactions, and a control proving the race is real):

| arm | result |
|---|---|
| two `INSERT … ON CONFLICT DO UPDATE … RETURNING`, same window | final count **2**, both exit 0 |
| the loser's wait | **blocked** until the winner committed — 0.94 s against a 0.75 s hold |
| CONTROL — the same two as a plain `INSERT` | the loser raises `23505` |

So there is **no lost update** at `read committed`, and the outcome is read from
the returned count rather than from an error — the same shape ADR 0171 fixed for
the refresh plane.

**The growth, because the plan asserted the opposite** (D903). Run 5's text says
the table's growth is *"a latency problem before it is a disk one"*:

| rows | upsert | on disk |
|---|---|---|
| 100 | 0.0093 ms | 64 kB |
| 10,000 | 0.0097 ms | 1.2 MB |
| 200,000 | **0.0084 ms** | 22 MB |

Flat across a 2000× growth, and the control — the same lookup with no index —
costs **5.56 ms at 200,000 rows, 659× the indexed upsert**, so the rig can
plainly see a slow lookup when there is one. Every access is a primary-key hit.
**Growth costs disk, not latency.**

## Decision

**The quota is counted inside `api.agent_audit_begin`, which already runs on
every audited call.** Zero extra round trips. The function returns the record id
as it does today and additionally reports the window's count, and the runtime
refuses when the count exceeds the bound — closing the record it just opened as
`refused` with `budget_exceeded`, through the path Run 3 built.

This is not a convenience. ADR 0141 already established that `begin` runs
**before** the scope check so that a denial is audited; a quota refusal is a
denial, and counting it anywhere else would either add a request or leave the
refusal unrecorded.

### One row per agent per window

```sql
CREATE TABLE app_private.agent_quota (
  agent_id     uuid        NOT NULL,
  window_start timestamptz NOT NULL,
  calls        integer     NOT NULL,
  PRIMARY KEY (agent_id, window_start)
);
```

`INSERT … ON CONFLICT (agent_id, window_start) DO UPDATE SET calls = calls + 1
RETURNING calls` — measured above, correct under concurrency, and the verdict is
the returned number.

### A refused call consumes its quota

Deliberate, and the opposite is the tempting answer. `begin` runs before the
scope check, so the count is taken before anything knows whether the call will
succeed — and that is the correct order rather than an accident of it: **a caller
hammering a capability it may not use is exactly what a rate limit is for.** A
quota that only counted successes would be no bound at all on the traffic that
matters most.

### Retention is lazy and off the request path

Because growth costs disk and not latency (D903), pruning does **not** belong in
the upsert. A row per agent per window at one-hour windows is 24 rows per agent
per day — 22 MB at 200,000 rows, which is roughly twenty-three years of a single
agent. Deleting windows older than a retention horizon is a maintenance verb, not
a request-path cost.

**Contrast with `agent_audit`, which the plan drew the wrong lesson from.** That
table grows without bound *and nothing prunes it* (§9). This one is bounded in
shape — one row per agent per live window — and pruning it is cheap because
nothing on the request path reads more than one row of it.

## Alternatives rejected

**A separate quota RPC.** The honest cost is a fifth upstream request per write
on a plane whose round trip has never been timed, to enforce a bound that can be
enforced in a call already being made.

**Counting rows in `agent_audit` instead of keeping a counter.** It needs no new
table and it is the wrong shape: `agent_audit` grows without bound, so the count
would scan a growing range on every request — which is the latency problem the
plan feared, created by the design that avoids the table.

**Serializable isolation for the counter.** ADR 0171's measurement applies: at
`repeatable read` the loser gets `40001`, and the ordinary response to a
serialization failure is a retry. Retrying a quota increment is how a caller
exceeds its quota. `read committed` with an upsert is measured, and the block is
short.

**Pruning in the upsert.** Solves a latency problem that does not exist, on the
one path where latency is paid.

## Consequences

- `api.agent_audit_begin` changes signature again — the second time this session.
  ADR 0175's guard reads `api` since Run 3 (D887), so every stale call site is
  caught offline rather than at a host gate.
- **An agent's concurrent calls serialise briefly on their own counter row.** The
  block was measured and is short, but it interacts with ADR 0179's
  per-capability concurrency: a capability permitted two in flight will have
  those two queue at the counter. Small, real, and stated rather than discovered.
- **The bound lives on `app_private.agents`, not in the capability manifest**
  (D906). An earlier draft of this ADR said the opposite and it was wrong:
  `AGT-QUOTA-001` bounds *an agent* across requests, not a capability. A
  per-capability bound is ADR 0179's shape and is decided by the manifest; this
  one is decided by whoever issued the agent, and it belongs beside the scopes
  and the status already decided there. **It is therefore not a
  `schema_version` question at all**, which is what makes D892's two-formats
  arithmetic hold rather than needing a v4.
- Both columns are nullable and NULL means **unbounded**. Not a default: this
  deployment has agents today with no quota, and giving them a number nobody
  chose would be inventing a policy — ADR 0177's rule about a capability's
  lifecycle, applied to an identity.
- **The signature does not change.** A refusal is a `NULL` return, because a
  `RAISE` would roll back the audit row written in the same transaction (D489)
  and leave the denial unrecorded — the one thing ADR 0141 put `begin` before
  the scope check to prevent.
- `AGT-QUOTA-001` needs a live half: a bound crossed across two requests, proved
  against a real cluster, and surviving a restart.
