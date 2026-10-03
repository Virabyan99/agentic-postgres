# 0248 — Retention extends ADR 0213 to the Stage 4 record, by aggregate, with a verb

- **Status:** Accepted
- **Date:** 2026-10-03
- **Session:** 36, Run 1 (D1985–D1989, D2002; rigs 36a, 36b, 36d)
- **Affects:** `OPS-RETAIN-001`, `OPS-RETAIN-002`, `OPS-RETAIN-003` (registered
  by Run 8). Migrations `0038-approval-withdrawn` and `0039-record-retention`
  (Run 2), `services/auth-api/app/workflow_worker.py` (the idle withdrawal),
  `bin/record.sh` and `bin/record.py` (Run 3).
- **Related:** ADR 0213 (the agent record is pruned by an operator who states a
  horizon, and by nothing else — kept, and extended here), ADR 0135, ADR 0142,
  ADR 0195 (three outcomes), ADR 0218 (a container exec goes through
  `container_exec.run`), ADR 0226–0239 (the workflow and connector planes whose
  tables these are), D1700, D1775, D1798, D1886.

## Context

Stage 4 added ten `app_private` tables (migrations 0034–0036) and nothing that
removes a row from any of them. Every foreign key among them is `NO ACTION`
(`0034:39`: *"No trigger, no schedule, no `ON DELETE`"*). Beta, at Session 35's
close: 133 runs, 372 steps, 327 attempts, 29 approvals, 9 events, 9
deliveries, 10 receipts, 83 revoked probe agents (a run pins its agent, D1700)
and 7 approvals `pending` forever on runs that had ended (D1775: nothing writes
an approval but `workflow_expire_approval`, which needs a live claim, and
`workflow_decide_approval`, which refuses a run that is not running). From
Session 37 strangers write these rows.

ADR 0213 decided the rule for the two Stage 3 tables: **retention is an act an
operator performs, on a horizon the operator states, with the counts in front
of them; nothing deletes a record on its own.** Its prunes are granted to
nobody and called by *"a human at a TTY"* through a hand-typed `psql`. That
rule is kept. What it lacked is a verb — the removal is a root `psql` with
container and database names typed by hand — and a shape for tables that
reference each other.

### What was measured (Run 1, against PostgreSQL 18.4 and dbmate 2.34.1)

- **Rig 36a — a new enum value cannot be used in the transaction that adds
  it.** `ALTER TYPE t ADD VALUE 'c'; UPDATE … SET v = 'c'` in one transaction
  fails with `unsafe use of new value "c" of enum type t` (SQLSTATE 55P04,
  hint *"New enum values must be committed before they can be used"*); the same
  two statements in two transactions succeed (the control). As **two dbmate
  migration files**, `up --strict` applies both; as **one file**, dbmate prints
  `Applied: … in 2.4ms` **and then** the 55P04 error, exits 2, and records no
  ledger row — D941's class (*read the ledger, never the migrator's line*) again.
  `psql -1 -f` per file, as `apg dev up` applies them, succeeds.
- **Rig 36b — the deletion order is load-bearing.** On a cluster with 0001–0037
  applied, runs in every status with steps, attempts, approvals and receipts,
  outbound deliveries in every status, and agents active, revoked, revoked and
  referenced by a run, and revoked and bound to a connector: the run prune as
  sequential `DELETE … WHERE … = ANY (victims)` in the order attempts →
  approvals → receipts → steps → runs removed exactly the four ended runs and
  their children and left `queued`, `running`, `compensating` and a run ended
  one minute before the horizon; **the control — runs deleted first — failed
  with `23503 … workflow_step_run_id_fkey`**. The bound counted roots (2 of 4,
  then 2 more). `LIMIT NULL` is no limit. The delivery prune removed the four
  ended old deliveries and the one event left with no delivery, and kept the
  pending delivery, the recent one, and an event a parked step awaits; the
  agent prune removed the two revoked agents no run and no connector named
  (their credentials and quota by `ON DELETE CASCADE`) and kept the active one
  and the connector's.
- **D1989 — an event never serves a wait parked after it.** `0036:877-878`:
  *"An event emitted before the park does not serve it: a wait waits for what
  happens after it began"*; `app.emit_event` serves waits at emission
  (`:230-241`) and `workflow_await_event` clears the payload when it parks
  (`:899-902`). The only other readers of `connector_event` join it through a
  delivery (`:453`, `:823`). So the prune's guard on awaited events is
  belt-and-braces, kept because it costs one `NOT EXISTS`. A step's
  `await_event` holds `name@version`; the guard compares
  `e.name || '@' || e.version`.
- **Rig 36d — the withdrawal is cheap enough for an idle loop.** 10,000
  approvals across 2,000 runs, half ended, 2,000 pending: the first call
  withdrew 1,000 in 82.7 ms; every later call found nothing in **0.8–1.4 ms**,
  served by the existing `workflow_approval_status_requested_idx`. No new index.

## Decision

**ADR 0213's rule is kept and extended to the Stage 4 record.** Retention
remains an act an operator performs with a stated horizon; nothing prunes on
its own; every prune is granted to nobody.

**1. Three prunes, by aggregate, never per table** (D1986). Each deletes its
children in foreign-key order inside one `SECURITY DEFINER` function, takes
`(p_before timestamptz, p_limit integer DEFAULT NULL)`, returns the number of
**roots** it removed, and bounds the roots, not the children:

| Function | Roots | Children removed with them |
|---|---|---|
| `workflow_run_prune` | runs `succeeded`, `failed`, `cancelled`, `stopped` with `finished_at < p_before` | their steps' attempts, their approvals, the receipts naming them, their steps |
| `connector_delivery_prune` | deliveries `delivered` or `dead` with `coalesce(delivered_at, dead_at) < p_before` | then events older than the horizon that no delivery and no `parked` step of a run still in flight awaits |
| `agent_prune` | agents `revoked` with `updated_at < p_before` that no run and no connector names | credentials and quota (by their `CASCADE`); audit and idempotency rows keep the id, the audit's convention |

A prune per table would let an operator delete a run's steps and keep the run —
a record no reader can explain. **Never pruned**: workflow definitions and
connectors (installed configuration, deploy steps 6d/6e), the worker singleton,
humans (`users` is referenced from six places, and deleting a person is an
identity question, not a retention one), a run `queued`, `running` or
`compensating`, a `pending` delivery.

**2. Refusals.** All three keep ADR 0213's: a missing horizon, a future one,
and a bound below one row, each `PT422`. **`workflow_run_prune` also refuses a
horizon newer than `now() - 600 s`** (`AP422: a retention horizon inside the
inbound replay window`, D1988): a receipt is an inbound connector's replay
protection, the route refuses a signature outside ±300 s, and a run can end two
seconds after its receipt arrived — so no receipt younger than twice the
signature window is deleted with its run.

**3. A pending approval on an ended run becomes `withdrawn`** (D1987). A new
value of `app_private.workflow_approval_status`, **added by migration 0038
alone**, because rig 36a measured that a value added by `ALTER TYPE … ADD
VALUE` cannot be used in its own transaction and that dbmate applies each file
in one. Migration 0039 adds `workflow_withdraw_ended_approvals() RETURNS
bigint` — pending approvals whose run is `succeeded`, `failed`, `cancelled` or
`stopped` become `withdrawn` — **granted to `auth_service` and called by the
workflow worker on an idle iteration**, immediately before it sleeps, so a
parked approval is withdrawn within one poll of its run ending. *"Cancelled"*
was the stage plan's word and is refused: it already names a run status, and a
run cancelled is not an approval cancelled. **No 0035 function is replaced** —
the four that end a run are hundreds of lines each, and replacing them "byte
for byte plus one statement" is the method's largest risk; the process that
already owns the run lifecycle calls one small function instead. The existing
CHECK (`decided_by` and `decided_at` set exactly for `approved` and `rejected`)
holds for `withdrawn` unchanged, and `workflow_run_prune` deletes withdrawn
approvals with their run.

**4. One reading, `record_size()`, granted to nobody** (D1985): one row per
prunable relation — `relation`, `row_count`, `oldest` — plus one row counting
pending approvals on ended runs. The doctor is unchanged: its twelve checks are
positional and read by position, and its `agent record` sentence keeps saying
*"nothing prunes either unless an operator asks (ADR 0213)"*, which is now true
with a verb to ask.

**5. The verb is `bin/record.sh`** (D2002): `sudo bin/record.sh --project KEY
size [--json]` and `sudo bin/record.sh --project KEY prune --what
runs|deliveries|agents|audit|idempotency --before ISO8601 [--limit N] --confirm
KEY`. Root; the container and database read from the deployed document; the
horizon parsed, timezone required and refused if in the future **before any
container is touched**; `--confirm` equal to the key; the horizon passed as a
`psql` variable, never interpolated; the size printed before and after;
*"could not be read"* with exit 6 when the cluster does not answer (ADR 0195).
**Nothing schedules it** — no unit, no timer, no other command — and a test
greps for a caller.

## Alternatives rejected

**One prune per table** (the stage plan's D1973 wording). Rejected above: the
unit the record means is the run, the delivery, the agent.

**Move ended runs' approvals to `withdrawn` inside the four functions that end
a run.** Rejected: four replacements of large 0035 functions for one statement
each, against one call from the worker that already owns the lifecycle.

**`ON DELETE CASCADE` added to the Stage 4 foreign keys.** Rejected: it would
let a single `DELETE FROM workflow_run` remove a running run's history; the
function's status filter is the guard, and a cascade bypasses it.

**A scheduled prune with a default horizon.** Rejected by ADR 0213 and still:
a horizon chosen by the product is a retention policy nobody stated.

## Consequences

**Makes easy:** an operator bounds the record with one command per aggregate,
reading the counts first; the 7 stuck approvals on beta resolve themselves
after the 1.14.0 deploy.

**Makes hard:** the worker gains a database call on every idle iteration
(measured: about a millisecond); a run cannot be pruned for ten minutes after
it ends.

**A contract test is replaced by a stricter one** (D2015).
`test_agent_audit_plane.py::test_nothing_in_this_release_calls_a_prune`
asserted that nothing in `src/`, `bin/`, `services/` or the templates names
0033's two prunes; `bin/record.py` now names both, by this decision. It asserts
instead that the callers are EXACTLY `bin/record.py`'s two — a second caller
fails, and so does the command losing its call — and
`test_record_command.py::test_nothing_schedules_a_prune` asserts that nothing
calls `record.sh` or `record.py` but themselves. Together they say what the old
test said (nothing prunes on its own) and one thing more (the verb exists and
calls what it says).

**Not closed:** D1798 (a dead letter cannot be redelivered); humans are never
pruned (35 probe humans on beta stay — Session 37's accounts decide what a
person's deletion means).
