# 0279 — Monitoring is a list of readings that each name their source

- **Status:** Accepted
- **Date:** 2026-10-18
- **Session:** 42, Run 1 (`docs/plans/session-42-implementation-plan.md`, D2572)
- **Affects:** `services/auth-api/app/signals.py` (`SIGNALS`, Run 7);
  `app.control_project_monitoring` in the control set's `0009` (Run 6);
  `GET /v1/projects/{key}/monitoring` and `apg monitoring show` (Run 7).
  Requirements `INS-SIGNAL-001`, `INS-LIVE-001`.
- **Related:** ADR 0195 (three outcomes), ADR 0273 (the backups reading), ADR
  0275 (the usage samples), ADR 0277 (the operator's half: ClickStack), ADR
  0278 (the insight samples), D704 (one source per customer-visible metric),
  D1535 (a value that looks measured).

## Context

The stage plan asks for *"a curated signal list, each naming its source"*; the
Ledger's `monitoring` row says the same. Every figure a customer could be shown
about a project's health is already recorded in the control database by a
reader that exists: the registry's state, ADR 0275's usage samples (and, after
ADR 0278, DB time), ADR 0273's backups reading, ADR 0278's insight samples.
Nothing lists them, and a monitoring page that read anything else would be a
second answer to a question one of those already answers.

## Decision

1. **A release table**, `signals.SIGNALS`: each `Signal(name, unit, source,
   column)` — ten at most: `state` (the registry), `database_bytes`,
   `repository_bytes`, `customer_connections`, `requests_last_hour`,
   `db_time_last_hour` (usage samples), `backup_status`,
   `latest_recoverable_time`, `last_full_backup_at` (the backups reading),
   `insights_sampled_at` (the insight samples).
2. **One route serves it**: `GET /v1/projects/{key}/monitoring` (viewer and
   above, keys with `projects:read`) through `app.control_project_monitoring`
   (DEFINER, membership-checked; a foreign and a missing project answer
   alike), each signal with `value`, `observed_at` and `source` — or `unread`
   with the reason it could not be read. **No new reader, no new sample**: the
   function reads only the tables the signals name.
3. **Guards**: every signal names a column that exists in the control set's
   migrations; no two signals read one column; the function reads no table
   outside the named set.
4. **No alerting, no threshold, no colour.** A reading is shown with its age;
   whether it is bad is the customer's judgement or a later decision (the
   Ledger's `eventual`). The operator's half is ClickStack (ADR 0277) and the
   existing `doctor` verbs.

## Consequences

- Every number on the page can be checked against the table it names.
- A figure the control database does not hold cannot appear on the page; it
  needs a sampler first, which is a decision of its own.
- A reading that went stale shows its `observed_at`; the page never presents
  an old value as current (ADR 0195's report may not fail closed).
