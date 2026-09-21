# 0227 — Durable step state is four tables nobody may read and nine definer functions, and a step is at-least-once with a key that makes it exactly-once

- **Status:** Accepted
- **Date:** 2026-09-21
- **Session:** 32, Run 1 (D1646, D1647, D1652, D1661, D1667, and the row Run 1
  added: D1670, D1671)
- **Affects:** a new `migrations/templates/0034-workflow-substrate.sql`
  (version `20260917120034`), `migrations/manifest.json`,
  `migrations/released.lock.json`, `docs/migrations.md`. **No RLS, no policy,
  no grant to any request role, and nothing in `api` — so no `NOTIFY pgrst`.**
- **Related:** ADR 0181 (the key claimed in the write's own transaction), ADR
  0182 (a dry run is rolled back), ADR 0104/0111 (the lease predicate is the
  correctness mechanism), ADR 0135 (the audit as caller), ADR 0195 (a reader
  reports the third outcome), ADR 0213 (a reading with no threshold), D57,
  D262, D285, D337, D489, D912.

## Context

Stage 4 §5 asked for `workflow_definition`, `workflow_run` and `workflow_step`
**with FORCE RLS**. The tree does not do that anywhere: `FORCE ROW LEVEL
SECURITY` appears only on `app.notes` and `app.tasks` (`0003:57-60`,
`0007:74,90,96`), no `CREATE POLICY` names an `app_private` table, and the
posture every `app_private` table has is *no request role holds any table
privilege* (`0019:99-105`), with access through `SECURITY DEFINER` functions.

FORCE RLS applies to a table's **owner** — the role every definer function
runs as — so a forced table with no policy is unreadable by the very functions
that exist to read it.

## What rig 32d measured

A throwaway `app_private` table owned by `object_owner` with no grants, behind
a definer function granted to `auth_service` alone, on a cluster with all 33
released migrations applied as `migration_user`:

* `auth_service` selecting the table directly → `permission denied for table`.
* `auth_service` calling the function → **succeeds, and reads every row**.
* `agent_writer`, `agent_reader`, `authenticated`, `anon` and
  `storage_service` calling the function → `permission denied for function`,
  every one.
* `has_table_privilege(auth_service, …, 'SELECT')`,
  `has_function_privilege(auth_service, …)`,
  `has_function_privilege(anon, …)` → **`false true false`**.

**The control, and it is the reason the brief's sentence is refused:** the
same table under `FORCE ROW LEVEL SECURITY` with no policy. The definer
function, run as `auth_service`, **returns zero rows and exits 0**. It does
not raise. A forced `app_private` table fails *silently, in the reassuring
direction* — which is the worst shape a security control can have, and it is
what the brief asked for.

Also measured, and it would have failed WF-STATE-001's privilege proofs on
first execution: `psql -qtA` renders `has_*_privilege()::text` as the **words**
`false`/`true`, never as `f`/`t`.

## Decision

**Four tables in `app_private`** — `workflow_definition`, `workflow_run`,
`workflow_step` and the single-row `workflow_worker` heartbeat — owned by
`{{object_owner}}`, **with no grant to any role**, and **no RLS and no
policy**. Every access is a `SECURITY DEFINER` function with `SET search_path
= pg_catalog, pg_temp`, `REVOKE ALL … FROM PUBLIC` beside the `CREATE` (D57,
D262), and the privileges block above `RESET ROLE` (D285). Schema `USAGE` is
not re-granted (D337).

**Nine functions. Eight are granted to `{{auth_service}}` and nothing else**:
`workflow_enqueue`, `workflow_claim_step`, `workflow_finish_step`,
`workflow_park`, `workflow_cancel`, `workflow_run_status`,
`workflow_heartbeat`, `workflow_counts`. **`workflow_install_definition` is
granted to nobody** — `0033:318-326`'s pattern — because a definition-writing
authority behind an identity reachable over HTTP is exactly what a deploy
calling it as the bootstrap superuser avoids.

Refusals reuse the existing errcode vocabulary — `PT403`, `PT404`, `PT409` —
rather than inventing codes. Nothing new is added to `UPSTREAM_WRITE_REFUSALS`:
these functions are called by the loop over psycopg, never through PostgREST,
and `test_the_map_translates_nothing_the_product_never_raises` is a **subset**
check that only grows more permissive as templates add codes.

### The lease

**The lease predicate is the correctness mechanism; `SKIP LOCKED` is
throughput and nothing else** (0016:65-69, re-measured for a step).
`workflow_claim_step` selects the lowest unfinished step whose status is
`queued`, or `parked` with `resume_after <= now()`, or `claimed` with
`lease_until < now()`, `FOR UPDATE OF workflow_step SKIP LOCKED LIMIT 1`, sets
the holder, the lease and `attempt + 1`. `workflow_finish_step` and
`workflow_park` are both `WHERE … AND claimed_by = p_holder AND status =
'claimed'`, and zero rows means **`lease_lost`, which is not an error** — the
`storage_finish_cleanup` rule (`storage_repository.py:216-230`).

**Rig 32e measured all five arms across two concurrent sessions:** a holder
inside an open transaction is skipped; after it commits and while its lease
stands, a second claimant takes **nothing**; once the lease expires the second
claimant takes the row with `attempt` 2 and a new holder; the first holder's
late finish updates **0 rows**. The control — the same statement with the
lease predicate removed — lets the second claimant take a row the first still
holds, thirty seconds into a thirty-second lease.

**`pg_catalog.now()` is the TRANSACTION START time, not the statement time**,
and the rig found this the hard way: a first pass took a 2 s lease and slept
3 s inside the open transaction, so the lease had already expired at commit
and the reclaim was legitimate. The claim and the reclaim predicate read the
same clock, which is what makes work done inside a claim transaction
irrelevant to the lease it just took.

### The key, and what a replay actually is

**The idempotency key is derived from the run and the step, never the
attempt**: `wf-<run uuid>-<step name>`, computed by `workflow_enqueue` and
stored on the step row, so every attempt presents the same bytes. A key per
attempt would make a retry after a crash write a **second** row.

**Rig 32c measured the semantics through the product's own RPC**, on a cluster
with all 33 migrations applied:

* the same key with the same arguments, twice → the second call is **not
  refused**; it returns **the same row id**, `app.notes` holds **one** row,
  `replay_count` is **1**, and the audit reads `committed:1` then
  `replayed:0`;
* the same key with different arguments → `AP412 … used for a different call`
  (the **control** that the fingerprint is checked);
* a fresh key, same arguments → a second row (the control that the first arm
  measured the key and not the arguments);
* no key at all → refused;
* the dry-run header → **no row lands and no key is claimed**, and the RPC
  returns rc 0 with a null id (ADR 0182's rolled-back write).

So `PT412` is the **control, not the proof**. The claim Stage 4 wants — *a
step replayed after a crash is exactly-once at the upstream* — is proved by
the upstream row count, never by a refusal.

### The one thing the loop cannot see, reported rather than folded

**A replay is indistinguishable from a first write in the plane's result.**
`invoke_write` returns `{tool, row_count, row, dry_run}` where `row_count` is
`len(rows)`, and both writes return exactly one composite row
(`mcp_tools.py:632-652`). Rig 32c confirmed the two calls return the same id.
**The word `replayed` exists only in `app_private.agent_audit.outcome` on the
`database`-source row**, which the HTTP result does not carry.

The substrate therefore **does not ask the loop to assign an outcome it cannot
determine** (ADR 0195). `workflow_step_outcome` carries `replayed` as a value
the *substrate* may hold, and the loop finishes a successful call as
`succeeded`; the replay is evidenced by the audit table and by
`agent_idempotency.replay_count`, which is where it actually lives. Surfacing
it through the plane's result would move `mcp_tools.py`'s reviewed result
shape, the MCP catalog and every caller — a contract move to make a sentence
true, which is the shape this project refuses.

### Park is the backoff, and the margin is a function

A retryable failure with attempts left **parks** the step with `resume_after =
now() + backoff_seconds`. Park *is* the backoff and a parked step *is* the
pause; no second sleep exists anywhere. Retryable is a transport error, a
timeout, and `write_conflict` — the three the plane itself calls transient
(`mcp_tools.py:571-573`). Everything else is terminal.

**`lease_margin_seconds()` is a function, never a constant** —
`storage_cleanup.py:86-100`'s discipline. It is derived from the loop's HTTP
client's own timeout by import. **The plan's `2 × (connect + read)` does not
exist to be imported**: `mcp_upstream` uses `urllib`, which takes ONE
`timeout`, and the `CONNECT_TIMEOUT_SECONDS`/`READ_TIMEOUT_SECONDS` pair lives
in `storage_client.py` and belongs to boto3 and R2 (D1670). The margin is
therefore `2 × mcp_upstream.UPSTREAM_TIMEOUT_SECONDS`, imported, so a change
to that constant cannot leave a stale copy behind. The loop stops before its
lease does (`deadline = started + lease - margin`, on a **monotonic** clock)
and abandons a step it cannot start in time rather than starting it late.

### Correlation and the heartbeat

Each step attempt mints a `request_id` (uuid4), stores it on the step row at
claim, and sends it as `X-Request-Id`. Correlation is
`workflow_step.request_id = agent_audit.request_id` — the audit's own key,
which the plane already supports. **No run id enters the audit table**; that
is an audit schema move and it is Session 33's (D1248).

`workflow_heartbeat(p_holder)` upserts the single `workflow_worker` row at
every poll, with `started_at` reset when the holder changes, so **a restart is
visible as a new holder**. `workflow_counts()` reports runs and steps by
status, the oldest claimed lease's age, the heartbeat's age and holder, and
the definition count — integers and a `hostname:pid:tick` string, and nothing
a caller supplied.

## Consequences

* The proof that a crash is survived is **two deterministic instruments**, not
  a timed kill (D1652): the live proof constructs the post-crash state, and
  the `worker-restart` rehearsal signals the process while a run is parked. A
  timing-based kill would pass most days and teach nothing the day it failed.
* Migration 0034 is **fix-forward only** (`AP900`) and, once applied on the
  host, is the floor (ADR 0162 §3). It is never amended (D912).
* A `wait` step is a park with no `resume_after`; the mechanism exists from
  this session and the step *kind* is Session 33's.

## Alternatives rejected

* **FORCE RLS on the four tables**, as the brief asked. Rejected on rig 32d's
  control: the definer functions read zero rows, silently, exit 0.
* **A key per (run, step, attempt)**, as D1521 proposed. Rejected on rig 32c:
  a retry after a crash would write a second row, which is the whole defect
  the key exists to prevent.
* **`LISTEN/NOTIFY` instead of polling.** Rejected: a listener is a connection
  held open for the life of the process, and the auth service's budget is
  `pool_size + AUTH_RESERVED_CONNECTIONS` with the reserve defined as the
  startup-and-recovery overlap (D388's argument, one service over).
* **Storing the outcome of a claim** rather than re-reading the row. Rejected;
  it is `0029`'s own decision and its reason is unchanged.
