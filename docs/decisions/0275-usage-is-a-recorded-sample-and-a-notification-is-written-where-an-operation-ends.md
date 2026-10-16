# 0275 — Usage is a recorded sample, and a notification is written where an operation ends

- **Status:** Accepted
- **Date:** 2026-10-16
- **Session:** 41, Run 1 (`docs/plans/session-41-implementation-plan.md`,
  D2523, D2524, D2526, D2528, D2533)
- **Affects:** the control set's `0008` (`app.control_usage_samples`,
  `app.control_notifications`, `app.control_record_usage`,
  `app.control_record_limit_notice`, `app.control_project_usage`,
  `app.control_org_usage`, `app.control_list_notifications`,
  `app.control_finish_operation` re-created, Run 4); `bin/reconciler.py`
  `Reconciler.record_usage` (Run 6); `GET /v1/projects/{key}/usage`,
  `GET /v1/organizations/{org}/usage`, `GET /v1/organizations/{org}/notifications`
  (Run 5); `bin/usage.sh`, `bin/notifications.sh` (Run 7). Requirements
  `USE-SAMPLE-001`, `USE-API-001`, `USE-NOTIFY-001`, `USE-LIVE-001`,
  `USE-LIVE-003`.
- **Related:** ADR 0195 (three outcomes), ADR 0224 (the collector consumed by
  `doctor usage`), ADR 0251 (the control set's two doors), ADR 0259 (the export
  URL is a result secret), ADR 0273 (a recorded reading with its age), D553 (a
  cumulative counter cannot answer a point-in-time question), D1609/D1643 (an
  `mcp` process mints its own series), D1966, D1968.

## Context

D1966 asks for usage *"sampled on an interval into the control project's
`usage_samples`, through the same container reads as the doctor"*; D1968 for
notifications *"in-app only … written by the reconciler when an operation ends
and by the usage sampler when a limit crosses 80%"*. Three ways a usage page
lies are already measured in this project:

- `agent_tool_calls_total` is per `mcp` process: an instant query reads
  nothing once the process that served the calls is gone (D1609, D1643).
- `traefik_service_requests_total` is a cumulative counter that resets when the
  edge restarts; subtracting two reads across a reset gives a negative number
  (D553).
- A figure that could not be read is not zero (ADR 0195).

And one way a notification leaks: a `project.export` result carries a secret
URL (ADR 0259), and an operation's `result` is the reconciler's to fill.

## Measured

Rig 41d (2026-10-16, WSL `~/s41/run1/rig41/rig41d.py`): `control_finish_operation`
re-created with the notification insert inside it, over the control set
`0001`–`0007`. A finish committed → ONE row in `app.control_notifications`,
`idle_sleep | project.sleep on rigidle-prod succeeded`, and the operation
`succeeded`. **Control:** the same finish inside a transaction that was rolled
back → the row was visible inside the transaction (count 1) and absent after
(count 0): the notification cannot outlive or precede the operation's end.

Sheet E0 (2026-10-16, `slot3-prod`) read the edge counter by code at rest and
with one control request; its readings are recorded in the plan's Run 1
**Done.** and decide ADR 0276's signal.

## Decision

1. **A sample is a row**, `app.control_usage_samples` (`0008`): `project_key`,
   `observed_at`, `state` (`active` | `sleeping`), `database_bytes`,
   `repository_bytes`, `branch_count`, `branch_bytes`, `customer_connections`,
   `requests_counter` (the edge counter AS READ, summed over codes below 400),
   `agent_calls` and `workflow_runs` (**rows created since the previous
   sample**, from `app_private.agent_audit` and the workflow run table by their
   creation time — durable, unlike the per-process series),
   `last_customer_activity`, `unread text[]` (the figure names not read) and
   `reason`; primary key `(project_key, observed_at)`.
2. **The reconciler writes one per deployed slot every `USAGE_SAMPLE_SECONDS =
   300`**, through `app.control_record_usage(p_samples jsonb)` — `SECURITY
   INVOKER`, **granted to nobody**, a key whitelist like
   `control_record_backups`. Each figure is read through `container_exec` as
   `doctor usage` reads it; the repository bytes from `backup.sh usage
   --json`, the block the backups reading also takes its window from (ADR 0273
   as amended, D2540). **A figure that cannot be read is `NULL` and
   named in `unread`**; a sleeping project's sample is `state = sleeping` with
   every container figure unread, *"the project sleeps"*.
3. **Not metered in Session 41:** DB time (needs `pg_stat_statements`, Session
   42), egress, provider and embedding figures (`not_metered`). **Active and
   sleeping seconds are computed at read time from the operation history**
   (`project.sleep` / `project.wake` finished times, creation, deletion) —
   never sampled.
4. **The usage document** (`GET /v1/projects/{key}/usage?hours=N`,
   `GET /v1/organizations/{org}/usage?hours=N`, `N` 1..720, default 24; viewer
   and above, keys with `projects:read`, through definer functions that check
   membership — a foreign and a missing project answer alike) gives `window
   {from, to}`, `samples {expected, present}`, per figure `{latest, latest_at,
   max, unread_samples}`; a counter as **the sum of increases between
   consecutive samples, a decrease read as a reset** (counted from the lower
   value) with the reset count; `agent_calls` and `workflow_runs` as sums;
   `active_seconds` / `sleeping_seconds` from the history; each plan
   entitlement with its value, `enforced` and the figure it is read against
   (ADR 0274). **A window with no sample answers `could_not_determine` with the
   reason — never zeros.**
5. **A notification is written inside `control_finish_operation`'s own
   transaction**, `0008` re-creating the function with its body otherwise equal
   to `0004`'s (a test diffs the two bodies minus the inserted block).
   `app.control_notifications`: `id`, `organization_id`, `project_key NULL`,
   `kind` (`operation_succeeded` | `operation_failed` | `idle_sleep` |
   `branch_expired` | `limit_approaching`), `text varchar(300)`, `created_at`.
   **The text is a fixed template per kind and type that interpolates only the
   type, the project key, the origin and the error code — never `p_result`,
   never the result secret, never a caller value.**
6. **`limit_approaching`** is written by the sampler through
   `app.control_record_limit_notice(p_project, p_entitlement)` (granted to
   nobody) when a read-not-enforced figure crosses 80% of its entitlement
   (`storage_gb` against `database_bytes`, `agent_calls_per_day` against the
   UTC day's sum), at most once per entitlement per organisation per UTC day.
   It informs; it enforces nothing.
7. **Listed per organisation**: `GET /v1/organizations/{org}/notifications?limit=N`
   (viewer and above, a human session or `org:read`; newest first, `N` ≤ 200).
   No read state, no deletion, no email (D1951).

## Alternatives rejected

- **The per-process series as the call count:** it reads zero after every
  `mcp` recreate (D1643).
- **A counter's difference across the window:** wrong after any edge restart
  (D553); increases between consecutive samples with resets read is the only
  sum that survives one.
- **Notifications written by the reconciler after the finish:** two
  transactions can disagree; one written in the finish cannot.
- **Copying project-plane events (approvals, backup health) into
  notifications:** D1968 forbids it — they are read from the readings that
  already state them.

## Consequences

- Samples are never pruned in Session 41 (~288 rows per slot per day); a
  retention is an operator-stated horizon when slots multiply (ADR 0213's
  shape).
- Every figure on the usage page says how many samples it is made of and how
  many could not read it.
- A notification cannot carry a URL: no template has a place for one.
