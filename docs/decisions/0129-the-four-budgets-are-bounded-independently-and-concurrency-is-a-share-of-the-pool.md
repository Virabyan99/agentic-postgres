# 0129 — The four budgets are bounded independently, and concurrency is a share of the pool

Status: accepted
Date: 2026-08-20
Session: 8, Run 8
Affects: ADR 0070, ADR 0082, ADR 0099, ADR 0127, D407, D446, D447, D451,
D454,
`services/auth-api/app/mcp_budgets.py`, `services/auth-api/app/mcp_tools.py`,
`src/agentic_postgres/rendering.py`

## Context

The plan asks for rows, elapsed time, concurrency and serialized bytes bounded
**independently**. Independence is the word that carries the weight: a row
ceiling bounds nothing about a row's size, a byte ceiling bounds nothing about
how long the database spends producing it, and neither bounds how many callers
are doing it at once.

Run 6 delivered two of the four — the lock's `max_rows`, which a caller may only
lower, and `MAX_SERIALIZED_BYTES`, which a caller cannot express at all. It also
wired the lock's `timeout_ms` into `@server.tool(timeout=…)` and into the
upstream socket timeout **without measuring that either bounds anything**.

## What was measured

Against the pinned fastmcp 3.4.0, with a tool that sleeps five seconds under a
one-second timeout, and a control that sleeps well inside it:

| arm | result |
|---|---|
| `@server.tool(timeout=1.0)`, body sleeps 5s | returns at **1.10 s**, `isError=True`, content `"Error calling tool 'slow'"` |
| CONTROL — same server, body sleeps 0.05s | returns at **0.09 s**, `isError=False`, the real result |

**So elapsed time is already bounded**, by the framework, from the lock's
`timeout_ms`. Run 6 wired it correctly and could not have known; this is the
measurement that turns it from a plausible line into a budget.

And the one that was not:

| arm | result |
|---|---|
| eight overlapping calls to a tool that blocks 0.4 s | **peak 8 of 8 concurrent** |

**There is no concurrency bound at all.** Every tool body ran at once.

## Decision

**Four bounds, four mechanisms, and none of them derived from another.**

| budget | bound by | source |
|---|---|---|
| rows | `min(caller limit, resource.max_rows)` | the deployed lock |
| serialized bytes | `MAX_SERIALIZED_BYTES`, checked after the read | a runtime constant |
| elapsed time | `@server.tool(timeout=…)` | the lock's `timeout_ms` |
| **concurrency** | an `asyncio.Semaphore` around the upstream read | **derived from PostgREST's pool** |

**The concurrency bound is a share of PostgREST's connection pool, and that is
what it is for.** The agent plane holds no database credential (D407) and takes
no share of ADR 0099's budget — but every read it makes occupies one of
PostgREST's connections while it runs, and PostgREST's pool is shared with human
callers. An unbounded agent plane cannot exhaust the *cluster*; it can exhaust
the *API*.

So `MCP_MAX_CONCURRENT_READS` is **rendered from `api.rest.pool_size`**, at half,
with a floor of one. A manifest that shrinks the pool shrinks the agent plane's
share with it, which is ADR 0070's rule — a division rather than a set of
independent grants — applied one level out.

**The ratio is a choice and is flagged as one.** Half leaves half the pool for
human callers under full agent load. Nothing measures that half is right; what is
measured is that the two numbers must move together, and deriving is what makes
that true.

**The bound applies in a thread, and that is not an optimisation** (D451).
The upstream read is blocking `urllib`. Awaited on the event loop it serialises
the whole process -- every other request, and the health routes with them -- and
it makes this bound **unreachable**: measured, six overlapping reads against a
bound of two peaked at **one** concurrent, so the semaphore never saw contention
and appeared to work. `asyncio.to_thread` puts the read where a bound on it means
something; re-measured, **2 of 2**. A budget that cannot be reached passes every
test written against it, which is why this sentence is in the decision and not
only in the code.

**The two metadata tools take no slot.** They answer from the deployed lock,
which is in memory, so a bound that queued discovery behind reads would make it
contend for nothing. `bounded()` decides by whether the call names a resource --
and the rule is asserted through `register()` with a control, rather than left in
a docstring, because until Run 8 **nothing in the repository had ever called
`register()`** (D454).

**Saturation queues rather than refuses, and the time bound is what makes that
safe.** A caller that arrives at a full semaphore waits, and the tool's own
timeout fires if the wait is long — so a queued request cannot outlive its
budget. This is the clearest demonstration of independence in the set: the
concurrency bound is survivable *because* a different bound limits how long
waiting can last.

## Alternatives rejected

**A literal concurrency constant.** It would agree with the pool until somebody
changed the pool, which is D264's cost. The relation is the point.

**Refuse when saturated instead of queueing.** It converts a busy moment into an
error for a caller who did nothing wrong, and it needs a refusal vocabulary for a
condition that resolves in milliseconds. The timeout already bounds the wait.

**Bound concurrency at the edge with a Traefik rate limit.** It is a different
quantity — requests per second rather than simultaneous upstream reads — and it
would live where the agent plane cannot state it. It remains available as a
second layer and is not this decision.

**Treat the row ceiling as sufficient.** It is the belief this ADR exists to
refuse: two hundred rows of one megabyte each satisfies every row budget in the
lock, and eight callers doing it at once satisfies all three of the others.

## Consequences

- **The agent plane can no longer starve the REST API**, and the relation is
  visible in one rendered value rather than in two constants that happen to
  agree.
- A saturated agent plane shows up as **slower reads, then timeouts** — never as
  a PostgREST pool exhaustion that a human caller experiences as an outage they
  did not cause.
- The elapsed-time bound is the framework's, so a framework bump is a change to
  a budget. ADR 0121 already pins the version at a measured ceiling, and the
  measurement above is what a bump has to reproduce.
- `MCP_MEMORY_LIMIT_MB` remains **inherited and not measured** (Run 4's flag).
  It is a fifth bound, on a different axis, and ADR 0082's profile-with-a-control
  is still the shape it needs. This ADR does not close it.
