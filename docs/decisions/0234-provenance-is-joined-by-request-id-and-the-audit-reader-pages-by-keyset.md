# 0234 — Provenance is one definer function joined by the plane's request id across every attempt, read by an auditor; the audit reader pages with a keyset cursor and reports the window it filtered

- **Status:** Accepted
- **Date:** 2026-09-26
- **Session:** 33, Run 1 (D1728, D1729, D1730, D1731; D1248; rig 33d)
- **Affects:** migration 0035 (`app_private.workflow_attempt`,
  `workflow_provenance`, the re-created `auth_list_agent_audit` at a new
  arity, `auth_count_agent_audit`, the index `agent_audit_started_id_idx`, the
  replaced `workflow_finish_step`/`workflow_park` appending attempts),
  `services/auth-api/app/routes.py` (`GET /admin/audit`), `strict_query.py`,
  `workflow_admin_routes.py` (`GET /admin/workflows/runs/{run_id}`),
  `bin/studio.py` and `src/agentic_postgres/studio.py`, `bin/workflow.py`
  (`inspect`), and three refusal proofs replaced by stricter ones.
- **Related:** ADR 0142 (the audit has one reader, behind its own scope), ADR
  0160 (the request id flows outward), ADR 0175 (the arity guard), ADR 0195
  (three outcomes), ADR 0205 (Studio), D1696 (the step records the plane's id).

## Context

The stage plan asks `apg workflow inspect RUN` to show who started a run, the
definition digest, each step's tool and capability version, each approval's
principal, each idempotency key, each denial's boundary — *"read from
`agent_audit` correlated by run id"*. `agent_audit` has no run id. A step
records the PLANE's request id (D1696), but only for its LAST attempt, and a
claim clears it.

Separately, D1248 left `GET /admin/audit` with an agent, an owner and a limit,
and its own row argued against a server outcome filter: *"No summarisation that
hides denials … is NOT satisfied by a server filter that would let a viewer ask
for 'outcome=served' and never see the refusals."*

**Rig 33d measured the paging** on the rig cluster: 1,000 audit rows inserted in
one statement share ONE `started_at`. A keyset `(started_at, id) < (cursor)`
with `ORDER BY started_at DESC, id DESC`, 100 per page, walked **11 pages, 1,000
rows, 1,000 distinct** — equal to the unfiltered count. Control: the same walk
with the id tie-break removed (`started_at < cursor`) returned **100 rows and
stopped**. With the index `(started_at DESC, id DESC)` the page is an Index Only
Scan; without it, a Sort over a Seq Scan (informational — 0033 declined an
index for the PRUNE, which is a Seq Scan by choice; a keyset page is not a
prune).

## Decision

**Every attempt is recorded.** `app_private.workflow_attempt(step_id, attempt,
event, outcome, request_id, reason, recorded_at)`, `event IN ('finished',
'parked', 'approval_requested')`, appended by the replaced `finish_step` and
`park` (same signatures) and by `workflow_request_approval`. No role holds a
privilege on it.

**Provenance is one definer function, `workflow_provenance(run) RETURNS
jsonb`**, granted to the auth service and served by
`GET /admin/workflows/runs/{run_id}` under **`admin_audit:read`** — the
auditor's existing scope, so provenance grants no new read, and an auditor reads
ANY run, a revoked agent's included (D1704 answered: *an auditor's read*). The
document: the run (agent, owner, definition name, version, `source_sha256`,
`lock_tools_sha256`, input, status, stopped reason, compensation cause and
outcome); every step in position order with every attempt, each joined to its
`agent_audit` rows by `request_id` (source, outcome, denial reason, row count,
elapsed, capability version, contract hash — **never `parameters`**); every
approval with its decider's id and username. **`profile` is reported absent
with a reason** (*no per-call record names a profile*) — ADR 0195, never filled.
`apg workflow inspect --run ID` prints the document whole.

**A moved lock does not refuse a run** (D1734): provenance shows the
definition's `lock_tools_sha256` beside every call's `contract_hash`, so a
reader sees that it moved and what each call ran under.

**The audit reader takes a window, an outcome, a denial reason and a keyset
cursor.** 0035 DROPs and re-CREATEs `auth_list_agent_audit(p_agent_id,
p_owner_id, p_since, p_until, p_outcome, p_denial_reason, p_before_started_at,
p_before_id, p_limit)` with 0032's `RETURNS TABLE` unchanged, plpgsql so an
unknown outcome or reason is `PT422` rather than an empty page, a half-given
cursor `PT422`, and the `REVOKE`/`GRANT` re-issued. A new
`auth_count_agent_audit(p_agent_id, p_owner_id, p_since, p_until)` counts the
WINDOW by outcome and by denial reason, ignoring the outcome/reason filters and
the cursor. `GET /admin/audit` accepts `since`, `until`, `outcome`,
`denial_reason` and an opaque `cursor`, and **always** returns `window_counts`
beside the page and a `next_cursor`.

**D1248's objection is answered, not overruled**: a filtered page cannot hide
that refusals exist, because the window's refusal count is on the same
response. Studio's forwarder accepts exactly the endpoint's seven parameters and
shows the counts; the three proofs that asserted the refusal of `outcome` and
`since` are replaced by stricter ones (the five forward, anything else is still
400, the header carries the counts).

**Provenance does not depend on the filters** (D1731). Both are built because
this session closes D1248; neither waits on the other.

## Consequences

* A reader of a run sees every attempt, not a summary of the last one.
* The re-created reader is a same-name, new-arity function; ADR 0175's guard
  models the `DROP` + `CREATE` and finds every caller.

## Alternatives rejected

* **A run id column in `agent_audit`.** Rejected: an audit schema move, and the
  request id already correlates.
* **Paging by offset.** Rejected: not stable under inserts.
* **A server filter without window counts.** Rejected: D1248's own objection.

## Amendment of ADR 0228

The amendment is written into ADR 0228's own file under *Amendment, Session 33*
(D1723 — the compiler reads the effective approval; D1724 — the stored result
is the tool's value), as ADR 0227 was amended in Session 32.
