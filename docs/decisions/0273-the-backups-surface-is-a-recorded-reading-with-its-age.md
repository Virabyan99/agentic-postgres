# 0273 — The backups surface is a recorded reading with its age

- **Status:** Accepted
- **Date:** 2026-10-14
- **Session:** 40, Run 1 (`docs/plans/session-40-implementation-plan.md`, D2435,
  and Run 1's rows D2456, D2457)
- **Affects:** `src/agentic_postgres/backup_report.py` (`summarise` gains the
  oldest kept set's stop time, Run 2); the control set's `0006`
  (`app.control_backup_readings`, `app.control_record_backups`, Run 4);
  `GET /v1/projects/{key}/backups` (`control_routes.py`, Run 4);
  `bin/reconciler.py` (`BACKUP_RECORD_SECONDS`, Run 5); `apg project backups`
  (Run 6). Requirement `BR-BACKUP-001`.
- **Related:** ADR 0195 (three outcomes; a report may not fold the third), ADR
  0256 (the reconciler is the only host actor the control plane has), ADR 0271
  (a branch at a point), D1963 (*"the backups surface is the doctor's three
  readings served through `/api/v1`, with the restore window computed from
  `pgbackrest info` — never declared"*), D2182 (a sleeping project's backups are
  unread).

## Context

A customer choosing a point for a branch needs to know which points exist. The
doctor already reads the repository, the archiver and the mirror, each with
three outcomes (`diagnosis.repository/archiver/mirror`), but only as root on
the host; the control plane cannot reach the host, and the reconciler is the
one host actor it has, already recording slots every 120 s. `bin/backup.sh
info --json` reads pgBackRest through the live container and costs repository
requests; its `latest_recoverable_time` is the newest backup's stop time — a
floor, not the archive's end (`backup_report.py:118-130`).

## Measured

Rig 40a (2026-10-14; ADR 0271 has the rig):

- **The lower bound is the oldest set's STOP time.** A target before the only
  full backup was refused `[075]: unable to find backup set with stop time less
  than '<target>'` (D2457). The plan had named the set's start.
- **The upper bound is the last archived COMMIT.** A target after the last
  commit — even one inside WAL that is archived — makes recovery end with
  `FATAL: recovery ended before configured recovery target was reached`, after
  logging *"last completed transaction was at log time <t>"* (D2456).
  `pg_stat_archiver.last_archived_time` is when the newest segment was archived;
  the newest commit in it is earlier by up to the gap between commits. A live
  project's auth worker commits a heartbeat every 5 s (`workflow_worker.py:96`),
  so the gap is seconds; a sleeping project commits nothing.

## Decision

1. **The reconciler records** each live managed project's backups reading
   every **`BACKUP_RECORD_SECONDS = 900`** into **`app.control_backup_readings`**
   (`project_key`, `observed_at`, `repository_status`, `archiver_status`,
   `mirror_status`, `earliest`, `latest`, `last_full_at`) through
   **`app.control_record_backups`** — `SECURITY INVOKER`, granted to nobody,
   reached through `container_exec` like `control_record_slots`. The three
   statuses are the doctor's own classifiers' verdicts, computed from the same
   probes — the mirror's from `probe_mirror`'s read of the copy record on disk,
   **never** from `backup.sh info --json`'s `mirror` member, which is a
   deploy-time placeholder: on 2026-10-14 (Sheet E0) it said `not_observed` for
   `slot3-prod` while the copy record said `last copied 04:41:38Z` (D2461).
2. **`earliest`** = the oldest kept backup set's **stop** time (`pgbackrest
   info`'s backup list; `summarise` gains it). **`latest`** =
   `pg_stat_archiver.last_archived_time` (the doctor's archiver query). Both are
   readings; neither is declared.
3. **`GET /v1/projects/{key}/backups`** serves the newest reading with its
   `observed_at`. **A reading older than 2 × 900 s, or any status the
   classifiers read `UNKNOWN`, is served as `could_not_determine` with its
   reason — never as a window.** A sleeping project reads *"the project sleeps;
   its archiver is stopped (its last archived point: …)"*. The text says the
   window's top is approximate by the seconds between commits, and that a
   point after the newest change is refused by the restore itself (ADR 0271,
   exit 7, naming the newest change).
4. **No test-restore operation** (D2432): the surface's text says *"to test a
   restore, create a branch at a point in its window"*.

## Consequences

- Every number the customer sees has an age and a third outcome. A window that
  is fifteen minutes old is shown as fifteen minutes old.
- The reconciler spends a few repository requests per slot every 900 s —
  `pgbackrest info` through the live container. Priced when slots multiply
  (Session 41 inherits it).
- The window is checked before a restore (ADR 0271); the restore's own
  refusals remain the second line, and they name the bound they met.
