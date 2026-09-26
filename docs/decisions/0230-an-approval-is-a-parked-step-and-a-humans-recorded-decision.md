# 0230 — An approval is a parked step and a human's recorded decision; a rejection is a cancel

- **Status:** Accepted
- **Date:** 2026-09-26
- **Session:** 33, Run 1 (D1714, D1716, D1719, D1720, D1736)
- **Affects:** migration 0035 (`app_private.workflow_approval`, the
  `workflow_approval_status` enum, `workflow_request_approval`,
  `workflow_gate_state`, `workflow_expire_approval`,
  `workflow_decide_approval`, `workflow_pending_approvals`),
  `services/auth-api/app/workflow_worker.py`, `workflow_repository.py`, a new
  `workflow_admin_routes.py`, `schemas/workflow.schema.json`
  (`approval: {expires_after_seconds}`), `bin/workflow.py`
  (`approvals`, `approve`, `reject`).
- **Related:** ADR 0179 (approval as a declaration and a named refusal — what
  this extends), ADR 0135 (the audit is the agent's record), ADR 0226–0229 (the
  substrate and the loop), ADR 0231 (how an approved call reaches the plane),
  ADR 0232 (who may decide), ADR 0217 (a second principal holds nothing the
  identity it acts for does not).

## Context

Since Session 16 a capability that declares `requires_approval` is refused by
the agent plane before anything is dialled, audited `refused` with
`denial_reason = approval_required` (ADR 0179). The refusal was the guarantee
(D870) because the product had no durable pending state, no second principal and
no place a decision could be recorded. Session 32 built the first of those: a
run, its steps, and a park with a time (`workflow_park`, 0034:773-801). The
workflow compiler still refused every approval-requiring capability, *"a worker
that ran it would be an approval gate nobody passed"*.

The question is where the gate lives. The loop could decide what needs
approval from the compiled definition; or the plane — which already enforces
the lock on every call — could go on deciding, and the loop could react to its
answer.

## Decision

**The plane decides whether a call needs approval; the loop reacts to the
plane's refusal.** An approval step's FIRST attempt is an ordinary call. The
plane refuses it with `approval_required` and audits the refusal — so the
audit carries the request for approval with no new write path. When the
refusal's token is `approval_required` AND the compiled step declares
`approval:`, the loop calls `workflow_request_approval(step, holder,
request_id, expires_after_seconds)`, which inserts a PENDING row carrying the
plane's request id of the refused call, and parks the step with
`resume_after = expires_at`. **The expiry is the park's time**, so no timer is
added. If the plane unexpectedly SERVES the first call (the lock no longer
requires approval), the step succeeds: the plane is the authority, never the
loop.

**A decision is its own append-only record, `app_private.workflow_approval`**,
because the decider is a human (`users`) and every row of `agent_audit` names an
agent (`agent_id uuid NOT NULL`, ADR 0135). One table per principal is how the
tree already separates `users` from `agents`. No role holds a privilege on the
table; every write is a definer function; a decided row is never updated (the
decide function's predicate is `status = 'pending'`).

**`workflow_decide_approval(run, step, user, 'approve'|'reject')`** checks
everything before its first write, so a refusal changes nothing: the run's
owner is refused (`approver_is_owner`, ADR 0232), a decided approval is refused
(`approval_already_decided`), an expired one is refused (`approval_expired`).
**Approve** records the decider and sets the step's `resume_after = now()`, so
the next claim takes it at once. **Reject is a cancel**: it records the decider
and sets the run's `cancel_requested_at`, and the next claim applies the cancel
through the one path cancels already take (0034:551-559) — compensation follows
(ADR 0233).

**At the gate the loop reads ONE thing, `workflow_gate_state`** (approval
`none | pending | approved | expired`, and whether a wait was served). Approved
→ mint with the approval (ADR 0231) and call. Pending at a claim means the
expiry fired → `workflow_expire_approval`, then the step fails
`approval_expired`. Rejected never reaches a claim.

**An approval waits at most `expires_after_seconds` (60..3600), strictly less
than the run's `timeout_seconds`.** No CHECK is widened.

**What an approver sees** (`GET /admin/workflows/approvals`): who (agent,
owner), which run, definition and step, which capability and tool, and until
when — **no argument value**. A capability's `audit.redact` would otherwise be
bypassed, and D1638 keeps an administrator out of tenant rows; the reviewed
definition in the checkout says what the step does.

**There is no notification plane.** `apg workflow approvals` is the poll
(the stage plan's Must-not, D1736).

## Consequences

* The stage plan's *"parks with `approval_required` in the audit"* is met
  literally, by the plane's existing refusal.
* A run parked on an approval is `running` and holds no lease: a restart of
  `auth` loses nothing (D1735 — no rehearsal scenario is owed).
* An approval that must outlive an hour needs a migration and a compiler bound;
  priced when an operator asks (§10 of the Session 33 plan).
* A human approver cannot be deleted while a decision names them
  (`decided_by REFERENCES users`) — D1700's retention question, now for humans.

## Alternatives rejected

* **An `approval` step kind with no tool call.** Rejected: the loop would decide
  what needs approval, a second authority beside the lock the plane enforces.
* **A decision row in `agent_audit`.** Rejected: a nullable identity in the
  agent record, which ADR 0135 refused.
* **An unbounded wait.** Rejected: the run timeout already bounds the park;
  widening the CHECK is a later decision.
* **Showing argument values to the approver.** Rejected: it makes the listing a
  tenant-data reader and bypasses every capability's redaction.
