# 0169 — An envelope number declares whether it transfers, and the document is pinned to what it measured

- **Status:** accepted
- **Date:** 2026-09-02
- **Session:** 14, Run 6 (`CAP-ENV-001`, D790–D796)
- **Related:** **D790** (the pooler reports a capacity failure as a protocol
  violation), **D791** (PostgREST reports the same failure honestly), **D792**
  (the limit is connection-seconds, not requests), **D793** (the two saturation
  paths are independent), **D794** (a measurement's kind decides whether it
  transfers), **D795** (an envelope must be pinned or it floats), **D796** (three
  of the plan's four scenarios need a host), ADR 0065/0066 (a result reached by a
  route the product does not take), ADR 0070/0099/0148 (the claimants on
  `max_connections`), D593/D603 (a number is a sample from a band), D770 (a
  component sizes itself from the machine it lands on), D700 (a status computed
  twice), D145 (a signal that describes something else).

## Context

§7 of the session plan names `CAP-ENV-001` **the claim most at risk of being
reported dishonestly**: *"An envelope is a document, and a claim over a document
can go green because the document exists."*

That is the whole design problem. Every other claim in this repository is proved
by something happening — a request answered, a row refused, a container
recreated. This one is proved by a document being true, and a document is true in
a way nothing executes.

Two facts constrain what the document may say.

**Nothing is deployed.** The host still runs Session 12's release, so every
number available to this run was measured off-host, against the pinned images at
the rendered settings, on an 8 GB development machine — not the 3,814 MB host
with no swap and eighteen containers.

**The plan anticipated this** and said so in Run 1: *"an envelope measured by an
off-host load generator is still `CAP-ENV-001`."* What it did not say is which
numbers survive the move.

## Decision

### 1. Every measurement declares whether it transfers

This is the distinction the envelope turns on, and it is the one an envelope
usually gets wrong.

- **`CONFIGURATION`** — follows from `pool_size`, `max_client_conn`,
  `query_wait_timeout` and their kin. *Which* error a caller gets, and at what
  client count. These hold wherever the deployment runs.
- **`MACHINE`** — throughput and milliseconds. These describe the machine the rig
  ran on.

**D770 is why this is a type rather than a caution.** A store measured 63 MB and
rising on a 7.8 GB rig and 45.6 MB under a real cap, because an unbounded
component sizes itself from the machine it lands on. A number measured off-host
and quoted for the host describes the wrong machine, and prose cannot be relied
on to stop that — a reader quotes the figure, not the paragraph around it.

**A `MACHINE` measurement must name its machine among its conditions and a
`CONFIGURATION` one must not.** That is structural and cannot be satisfied by
wording. It replaced a scan over the measurement's prose, which could not tell a
*stipulated* duration ("each request holds a connection for 500 ms" — an input)
from an *observed* latency ("p50 476 ms" — an output): D464's shape, a text scan
standing in for a construct.

### 2. A measurement with no conditions cannot be constructed

Not a review rule — a constructor invariant. D593 and D603 are the standing
instance: `process-max` is 1, so a restore is ~1,330 serialised S3 round trips
and any RTO figure is a sample from a band. A conditionless number is refused
where it is written, so it cannot reach the document and be caught later by a
test somebody skipped.

### 3. The document is pinned to the images it measured, and to nothing else

`--check` fails when one of them has moved, **naming which**. *"The envelope is
stale"* sends a reader looking; *"POSTGREST_IMAGE moved"* sends them to the
measurement that is now a claim about a previous version.

Three images, not the whole lock. An envelope that went stale when an unrelated
image moved would cry wolf — and this is not hypothetical in either direction:
`traefik:v3.7` moved **twice inside Session 14**, three days apart (D787), while
none of the three measured images moved at all.

**A missing digest counts as stale, not as unchanged.** That is D600's shape: a
`null` that looks measured is worse than an absent field, and `or {}` turning a
missing block into a value wrote `null` into every drill document.

### 4. What was not measured is listed, with the reason and what unblocks it

An envelope silently missing the scenarios nobody could run reads as an envelope
of the whole system — **the dishonest reporting §7 warns about, arriving as a
document that looks complete rather than as a claim that is false.**

Three of the plan's four scenarios need a host (D796): MCP round trips need the
whole agent plane and a signed token; backup under load needs the R2 repository
and a credential this machine must not hold; and the deployment's own numbers
need the deployment. Each is named by subject, so a reader looking for the MCP
round trip finds the word rather than a general apology.

**A test asserts the list is non-empty**, because the day it is empty is a claim
in itself and must be made deliberately rather than by deletion.

### 5. Nothing was tuned

The plan asks for timeout and pool tuning after the load scenarios. **None was
done, and that is the decision rather than an omission.** Changing `pool_size` or
`query_wait_timeout` on the strength of a development machine's latency would be
tuning the deployment to a measurement that is not about it — ADR 0065/0066's
shape, where a result reached by a route the product does not take proves the end
state is reachable rather than that the product reaches it. Run 5's
`ALERT_ERROR_RATIO` is waiting on the same evidence.

## Consequences

- **The two components report the same failure differently, and one is wrong.**
  pgbouncer reports a queue timeout as `ProtocolViolation: query_wait_timeout`
  (D790) — a capacity condition arriving as a *protocol* error, so a client
  catching `OperationalError` (the usual "connection trouble, retry") does not
  catch it. PostgREST reports the identical failure as **HTTP 504 with
  `PGRST003` and a message naming the cause** (D791). D145's family: the state is
  real and the signal describes something else. Anything that classifies failures
  by exception class will get the pooled path wrong.
- **The same component gets one limit right and the other wrong.** pgbouncer's
  client ceiling refuses the 101st connection with `FATAL: no more connections
  allowed (max_client_conn)` as an `OperationalError` — correct and actionable.
  Only its queue timeout misreports.
- **Capacity is connection-seconds, not requests** (D792). 240 concurrent *fast*
  requests were all served at the same concurrency that refused 130 of the slow
  ones. Neither the HTTP layer nor the caller count is the constraint — what
  saturates is callers *holding* a connection. **So halving a query's duration is
  worth as much as doubling the pool**, which is not what a request-per-second
  figure would have suggested.
- **The two saturation paths are independent** (D793). PostgREST connects
  directly to the cluster, not through the pooler, so a REST caller and a pooled
  client contend for `max_connections` but not for each other's pool. Each has
  its own limit and its own failure, and an operator diagnosing one learns
  nothing about the other.
- **Both paths shed load rather than collapsing.** The plateau is stable at ~110
  served REST requests whether 160 or 240 are offered, and a request immediately
  after saturation returned 200. A limit that leaves wreckage is a different
  property from one that sheds, and this one sheds.
- **The envelope will need re-measuring on the host**, and the pinning makes that
  visible rather than optional. The `CONFIGURATION` numbers should reproduce
  there; if they do not, the difference is the finding.

## Alternatives considered

**Publishing the latency figures as the deployment's.** The obvious shape, and
the one the type system here exists to prevent. They were taken on a machine with
roughly twice the RAM and no competing containers.

**Omitting the unmeasured scenarios.** It would have produced a document that
looked complete, satisfied the claim's node ids, and covered one of the four
scenarios the plan named. That is precisely the failure §7 predicted, which is
why the list is enforced rather than encouraged.

**Tuning on the off-host numbers.** Rejected under ADR 0065/0066. The
measurements are honest about a rig; a setting changed on them would be a change
to the deployment justified by evidence about something else.

**Pinning the envelope to the whole version lock.** It would go stale roughly
weekly on rolling-tag drift the measurements do not depend on (D540, D787), and a
guard that cries wolf is a guard that gets regenerated without reading.
