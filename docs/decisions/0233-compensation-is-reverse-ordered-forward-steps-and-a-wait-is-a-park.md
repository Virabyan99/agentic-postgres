# 0233 — Compensation is reverse-ordered forward steps appended when a run fails or is cancelled; a wait is a park with a time

- **Status:** Accepted
- **Date:** 2026-09-26
- **Session:** 33, Run 1 (D1725, D1726, D1727; rig 33e)
- **Affects:** migration 0035 (the `compensating` run status, the `phase` and
  `compensates` step columns, the `compensation_cause` and
  `compensation_outcome` run columns, `workflow_begin_compensation`, the
  replaced `workflow_claim_step` and `workflow_finish_step`),
  `schemas/workflow.schema.json` (`compensation`, `wait`),
  `src/agentic_postgres/workflow_definition.py`,
  `services/auth-api/app/workflow_worker.py`, two example definitions.
- **Related:** ADR 0227 (the substrate), ADR 0228 (the definition), ADR 0229 (a
  run is the agent's), ADR 0230 (a rejection is a cancel).

## Context

The stage plan: *"a step may declare `compensation: tool@version`, run by the
worker in reverse order for every succeeded step when a later step fails
terminally or the run is cancelled, as the same agent, audited — never a
rollback"*, and *"`wait` (parked until an event named by 34 arrives or
`timeout_seconds` elapses)"*.

0034's claim takes a step only when every EARLIER position has `succeeded`
(`0034:580-584`), so a compensation row placed after a failed step could never
be claimed by the current predicate. The failure branch of `finish_step` ends
the run. In the example project's lock only `update_task_status` has an inverse
(swap the two statuses); `create_note` has none because `delete_note` does not
exist (D1547).

**Rig 33e measured the enum step** on PostgreSQL 18.4 under the pinned dbmate,
as `migration_user` with `SET LOCAL ROLE object_owner`: `ALTER TYPE
app_private.workflow_run_status ADD VALUE 'compensating'` followed by a plpgsql
`SECURITY DEFINER` function whose body inserts and returns `'compensating'` —
**applied** (rc 0); after commit the function ran and wrote the value. Control:
the same `ADD VALUE` followed by a column `DEFAULT` naming the new value in the
same migration — **refused** `55P04 unsafe use of new value`, the whole
migration rolled back and the enum unchanged. dbmate printed `Applied:` for the
control before it failed (D941, observed again: read the ledger, never the
migrator's line). 0029's and 0030's precedent holds.

## Decision

**A step may declare `compensation: {capability: name@version, arguments,
retry, timeout_seconds}`.** It must be a WRITE the lock compiles, may not
require approval (*a run that is failing cannot be left half-undone until
someone answers*), takes only declared arguments, and may reference the run's
input, the step itself and earlier steps. Its scopes join the definition's
`required_scopes`, so `enqueue` refuses an agent that could not run it, and
nothing is ever widened to run it.

**Rows are appended when the run fails or is cancelled, not at enqueue.** An
internal definer function `workflow_begin_compensation(run, cause)` — granted
to NOBODY, called only by other definer functions — inserts one row per
SUCCEEDED forward step that declares a compensation, in REVERSE position order,
at positions `1000 + n`, named `undo-<forward position>`, keyed
`wf-<run>-undo-<forward position>`, `phase = 'compensation'`, and sets the run
`compensating` with the cause. With nothing to compensate the run takes the
cause directly.

**Each undo is independent.** A compensation row is claimed when every
compensation row before it is FINISHED — succeeded or failed — so one failed
undo does not stop the rest. When the last finishes, the run takes its cause
status with `compensation_outcome` `complete` (every undo succeeded) or
`incomplete`. A refused mint during compensation stops the run `incomplete`.
**A compensating run is not timed out**; each row is bounded by its own retry
and step timeout.

**The word is compensation, never rollback.** The example definitions
compensate `update_task_status` with `update_task_status` and nothing else; a
note cannot be un-created in this release, and the documentation says so.

**A wait is `wait: {seconds: N}`**, a step with no capability, `N` below the
run's timeout. First claim: parked with `resume_after = now() + N`, reason
`waiting`. Next claim: `workflow_gate_state` reports the served park and the
step succeeds `waited` — never a second park, so a reclaim after a crash does
not restart the wait. **No token is minted for a wait.** `wait: {event}` is
refused by the compiler naming Session 34, which adds the event that resumes
it.

## Consequences

* The compensation plan in the database is a record of what was actually
  compensated, not of what might have been.
* A poller reads `compensating` as *not over*; `complete`/`incomplete` tells a
  reader what happened without the word *rolled back*.
* An operator facing `incomplete` reads `apg workflow inspect` and acts by hand;
  the product does not retry an undo beyond its declared retry.

## Alternatives rejected

* **Compensation rows created at enqueue.** Rejected: a plan of what might be
  undone is not a record of what was.
* **Stopping at the first failed undo.** Rejected: undos are independent, and a
  reader needs to know which held.
* **A `compensating` column instead of a status value.** Unneeded: rig 33e
  measured the value is safe when used only in function bodies.
* **Calling it rollback.** Refused by the stage plan.
