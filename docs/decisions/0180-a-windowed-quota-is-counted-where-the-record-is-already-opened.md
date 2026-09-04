# 0180 — A windowed quota is counted where the record is already opened

- **Status:** accepted
- **Date:** 2026-09-04
- **Session:** 16, Run 5 (`AGT-QUOTA-001`, D865, D902–D913)
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

This was measured against the row-per-window shape the design started with. It
is quoted unchanged because it is what makes the *decision below* defensible
rather than lucky: the shape that ships holds one row per agent, so 200,000 rows
is 200,000 agents rather than eight days of one. The measurement says the
counter would have been fast either way, which means the reset was chosen for
the retention argument (D910) and not to rescue a lookup.

## Decision

**The quota is counted inside `api.agent_audit_begin`, which already runs on
every audited call.** Zero extra round trips. The function counts the call, and
when the count exceeds the bound it writes the complete `refused` row itself —
`budget_exceeded`, through the taxonomy Run 3 built — and **returns NULL**. The
signature does not change.

The refusal is written by the function rather than closed by the runtime because
a `RAISE` would roll back the row it is trying to leave behind (D489, D907), and
because the runtime cannot close a record it was never given the id of. `NULL` is
unambiguous: `begin` has never returned one, a caller with no agent identity
being refused with `PT403` instead.

This is not a convenience. ADR 0141 already established that `begin` runs
**before** the scope check so that a denial is audited; a quota refusal is a
denial, and counting it anywhere else would either add a request or leave the
refusal unrecorded.

### One row per agent, and the window boundary is a reset

```sql
CREATE TABLE app_private.agent_quota (
  agent_id     uuid        PRIMARY KEY REFERENCES app_private.agents (id) ON DELETE CASCADE,
  window_start timestamptz NOT NULL,
  calls        integer     NOT NULL CHECK (calls >= 1)
);
```

The upsert conflicts on the **agent**, not on the pair, and the window is a
column it overwrites:

```sql
INSERT INTO app_private.agent_quota (agent_id, window_start, calls)
VALUES (acting_agent, window_at, 1)
ON CONFLICT (agent_id)
DO UPDATE SET
  calls = CASE
            WHEN app_private.agent_quota.window_start = EXCLUDED.window_start
            THEN app_private.agent_quota.calls + 1
            ELSE 1
          END,
  window_start = EXCLUDED.window_start
RETURNING calls
```

Measured above, correct under concurrency, and the verdict is the returned
number. **The `CASE` is the whole retention story** — see below.

### A refused call consumes its quota

Deliberate, and the opposite is the tempting answer. `begin` runs before the
scope check, so the count is taken before anything knows whether the call will
succeed — and that is the correct order rather than an accident of it: **a caller
hammering a capability it may not use is exactly what a rate limit is for.** A
quota that only counted successes would be no bound at all on the traffic that
matters most.

### There is no retention, because there is nothing to retain

**Nothing reads a past window.** The bound is a count within the *current*
window; the previous one is not consulted, reported, or summed. A history the
product never looks at is not history — it is unpruned rows.

So the boundary is a **reset in place** rather than a new row, and the table
holds exactly one row per agent that has ever made an audited call. It is
bounded by the agent count of the deployment, which is a number an operator
chooses, and no `DELETE` exists anywhere in the design (D910).

**This replaces a retention verb, and that is the point.** The earlier shape —
`PRIMARY KEY (agent_id, window_start)`, a row per window — needed a maintenance
command, a horizon somebody had to choose, and a place to run it. All three
disappear when the row is overwritten instead of inserted. The cheapest
retention policy is a schema that does not accumulate.

**Contrast with `agent_audit`, which the plan drew the wrong lesson from.** That
table grows without bound and nothing prunes it (§9) — and it must, because a
denial's record is the thing an auditor reads afterwards. The quota table's rows
have no reader after their window closes, which is precisely why the same
problem does not arise here.

The reset is not free of risk, so it is guarded: the `CASE` comparing
`window_start` is a mutation arm, and removing it leaves a counter that never
resets — a bound that turns into a lifetime cap, which is a *stricter* wrong
answer and therefore one nothing would complain about. It is killed by
`test_the_window_is_fixed_and_a_new_one_starts_clean`.

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

**A row per window, plus a retention verb to delete old ones.** The shape this
ADR started with. It is more faithful to the word *window* and it buys nothing:
no caller, no report and no proof reads a closed window, so every row it keeps
is waiting for a reader that does not exist. The cost is a maintenance command,
a horizon somebody has to choose, and somewhere to run it — three obligations in
exchange for data nothing consumes (D910).

**Pruning inside the upsert.** The version of the above that avoids the
maintenance verb by paying for it on the request path instead: a `DELETE` on
every audited call, solving a latency problem measured not to exist, on the one
path where latency is actually paid.

## Consequences

- **`api.agent_audit_begin` gains behaviour without gaining an argument.** Run 3
  already moved it to five parameters with no defaults; this run changes what it
  does and not how it is called. That is deliberate — see the NULL bullet below —
  and it is why ADR 0175's guard has nothing to say here, although it reads `api`
  since Run 3 (D887) and would have caught it if the arity had moved.
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
- **Nothing in this design deletes a row, and nothing needs to** (D910).
  `app_private.agent_quota` holds one row per agent that has made an audited
  call, and `ON DELETE CASCADE` removes it with the agent. It is therefore the
  first table this session adds that does **not** join `agent_audit` and the
  secret generations in §9's *grows without bound* list.
- **A closed window is unreadable, by construction.** Nobody can ask how many
  calls an agent made in the previous hour — the counter was overwritten. If a
  future session wants that question answered, `agent_audit` is where it is
  answered from, because that table keeps every call with its timestamp. The
  quota table is a bound, not a record.
- **Migration 0028 was committed and frozen in the row-per-window shape, then
  re-shaped and re-frozen** (D912). It has been applied to nothing but throwaway
  test clusters — the host runs Session 15 at `dfc09b3`, which predates 0027 —
  and ADR 0028's immutability attaches to *applied*, which is why `freeze-lock`
  is a legitimate act here and not one after Run 10's trip. The re-freeze is a
  four-digit diff in git rather than a silent edit, which is what
  `verify_lock` exists to guarantee.
- `AGT-QUOTA-001` needs a live half: a bound crossed across two requests, proved
  against a real cluster, and surviving a restart.
