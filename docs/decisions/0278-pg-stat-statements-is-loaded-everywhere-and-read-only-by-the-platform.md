# 0278 — `pg_stat_statements` is loaded everywhere and read only by the platform; Query Insights is a recorded sample with no advice

- **Status:** Accepted
- **Date:** 2026-10-18
- **Session:** 42, Run 1 (`docs/plans/session-42-implementation-plan.md`,
  D2566–D2571, D2597; rig 42b)
- **Affects:** `compose.yaml` `postgres` `command` and
  `branch_plan.persistent_command()` (Run 3); `bootstrap_statements.build_statements()`
  and `bin/postgres-bootstrap.py` `check_violations` (Run 3); the control set's
  `0009` (`app.control_insight_samples`, `app.control_record_insights`,
  `app.control_project_insights`, `db_time_ms` on `app.control_usage_samples`,
  Run 6); `bin/reconciler.py`'s usage pass (Run 6);
  `GET /v1/projects/{key}/insights` and `apg insights show` (Run 7).
  Requirements `INS-PGSS-001`, `INS-READ-001`, `INS-API-001`, `USE-DBTIME-001`,
  `INS-HOST-002`, `INS-LIVE-001`.
- **Amends:** **ADR 0275** — DB time is metered (its *"Not metered in Session
  41: DB time"* sentence is withdrawn; D2570).
- **Related:** ADR 0195, ADR 0243 (proposals), ADR 0246 (no product surface
  runs SQL), ADR 0249 (the request lines), ADR 0269 (the customer roles),
  D553 (a cumulative counter answers no point-in-time question), D1535,
  D1965.

## Context

D1965 asks for Query Insights — the customer's statements, their calls and
time — and the stage plan forbids the two ways it goes wrong: a literal of the
customer's data or a platform password in a stored statement, and *advice*
(a recommendation with a confidence, D1535's value that looks measured). The
control plane can reach neither a project's database nor ClickHouse (ADR
0246); the reconciler already reads every slot through the container every
300 s (ADR 0275).

## Measured

Rig 42b (2026-10-18, WSL `~/s42/run1/rig42/rig42b.sh`, transcript
`rig42b.txt`; the pinned `pgvector/pgvector:pg18@sha256:69167330…`,
`PostgreSQL 18.4 (Debian 18.4-1.pgdg12+1)`; the fixture render's sizes:
`mem_limit` 768m, `shm_size` 256m, `shared_buffers` 128MB,
`max_connections` 56):

- **The five flags take**: `SHOW` reads `pg_stat_statements` /
  `1000` / `top` / `off` / `off`. The extension is version **1.12**.
- **`PUBLIC` holds `SELECT` on both views by default** (`\dp`: `=r/postgres`
  on `pg_stat_statements` and `pg_stat_statements_info`), and a non-superuser
  role read six rows before any revocation. `pg_stat_statements_reset(oid,
  oid, bigint, boolean)` is already revoked from `PUBLIC` by the extension
  (`{postgres=X/postgres}`; the customer's call: *permission denied*).
- **Revoking the two VIEWS is not enough** (D2597): after `REVOKE ALL ON
  extensions.pg_stat_statements, extensions.pg_stat_statements_info FROM
  PUBLIC`, the customer role read **8 rows by calling the function under the
  view**, `extensions.pg_stat_statements(true)`, and one from
  `extensions.pg_stat_statements_info()` — both functions carry no ACL, so
  `PUBLIC` holds `EXECUTE`. After revoking the two functions as well: *permission
  denied for function pg_stat_statements*. **Control:** `postgres` reads it.
- **The role a statement records under is the role current at execution**:
  one PostgREST `GET` as `anon` and one with an `authenticated` token recorded
  under `anon` and `authenticated`, never `postgrest_authenticator` — which
  records only its own schema-cache query. **Control:** `customer_app` over a
  direct connection recorded as itself, and `auth_service` (a platform role)
  as itself.
- **The canary**: as `customer_app`, two `SELECT … = '<canary>'` and a `DO`
  block holding it; as `postgres`, `ALTER ROLE customer_app PASSWORD
  '<canary>'`. Rows holding the canary: **0**; holding `password`: 0; a `DO`
  row: 0; the two `SELECT`s present as `… WHERE name = $1` and `… relname =
  $1`. **Control:** the same `ALTER ROLE` with `track_utility` set `on` for
  the session → **1** row holding the canary.
- **The restart**: a changed `command` recreates the container. Unavailability
  (first refused connection → first `SELECT 1`, probed every 0.1 s from the
  network): off→on **1.29, 1.43, 1.13 s**; on→off 4.26, 4.30 s; **control**
  (two forced recreates with no change) 1.27, 1.31 s. `docker compose up -d
  --wait` 6.5–6.9 s in every case. A rig's database is small; the host's
  windows are probed at the release's deploy (D2567) and recorded in the
  envelope.
- **Memory**: at rest 23.0–25.4 MiB with the extension against 22.5–23.0
  without (control: 22.5/22.6 across the two unchanged recreates);
  `pg_shmem_allocations` holds 2,944 + 128 bytes for it at `max=1000`. Far
  below ADR 0244's 32 MiB rounding: **the database budget does not move.**
- **The restore paths**: a cluster holding the extension started with
  `postgres -c archive_mode=off` only starts; a `SELECT` from the view answers
  *pg_stat_statements must be loaded via "shared_preload_libraries"*; `pg_dump
  --schema=app --schema=api --schema=public` is **byte-identical** loaded,
  unloaded and with the extension dropped (no mention of it).

## Decision

1. **Loaded on every project's database and every branch** by five `-c`
   flags on the `postgres` command: `shared_preload_libraries=pg_stat_statements`,
   `pg_stat_statements.max=1000`, `pg_stat_statements.track=top`,
   `pg_stat_statements.track_utility=off`, `pg_stat_statements.track_planning=off`.
   `track_utility = off` is what keeps an `ALTER ROLE … PASSWORD` out of it;
   `track = top` keeps a function's inner statements (a `DO` block's literal)
   out. The restore paths (a drill, a node restore) keep their command: they
   end, and a restored project's first deploy loads it again.
2. **Created by the bootstrap plane** in `extensions` after `vector`, then
   **revoked from `PUBLIC` on all four objects**: the two views AND the two
   functions under them (`extensions.pg_stat_statements(boolean)`,
   `extensions.pg_stat_statements_info()`) AND
   `extensions.pg_stat_statements_reset(oid, oid, bigint, boolean)` (the
   signature read on 18.4). **No role is granted**: the reader is `postgres`
   through the container. `check_violations` reads the extension, the preload
   and **`has_table_privilege` and `has_function_privilege` false for
   `customer_app`** on the view and its function.
3. **Only the customer-facing roles' statements are kept**: `userid` in
   `customer_app`, `customer_admin`, `anon`, `authenticated`, `agent_reader`,
   `agent_writer` — names derived by `naming.database_roles(key)`, never typed.
   The text is the extension's normalised text, cut to 2,000 characters.
4. **History lives in the control database**, sampled by the reconciler in its
   usage pass: `app.control_insight_samples`, written only by
   `app.control_record_insights(p_samples jsonb)` (INVOKER, granted to nobody,
   a key whitelist), the top 50 by cumulative `total_exec_time`, **counters as
   read** with the extension's `stats_reset`, and the writer deletes the key's
   samples older than **7 days** (`INSIGHT_KEEP_DAYS`). ClickHouse never holds
   a customer's statement.
5. **DB time is metered**: `db_time_ms` and `statements_reset` on the usage
   samples; the usage document's `db_time` is the sum of increases of the
   customer-facing roles' `sum(total_exec_time)`, a decrease or a moved reset
   read as a reset (D553); an unread extension names `db_time` in `unread`.
6. **The insights document states numbers and gives no advice**: per statement
   the increase over the window of calls, total and mean time, rows,
   rows per call, shared blocks read per call and the cache hit ratio; the
   window, samples expected and present, resets; **no `finding`,
   `recommendation`, `confidence` or `severity` member**; one fixed `tuning`
   sentence naming `apg migrate propose`. A window with no sample is
   `could_not_determine`, never an empty list (ADR 0195). A foreign and a
   missing project answer alike.
7. **The restart is said**: 1.20.0 restarts each project's database once, at
   the release; the window is probed per project and recorded.

## Consequences

- A customer cannot read another tenant's text — there is one tenant per
  cluster — nor the platform's own statements, nor the extension at all.
- A statement inside a customer's function is not seen (`track = top`): the
  calling statement carries the time. Widening to `all` would re-open the
  literal question for function bodies and is a decision, not a setting.
- A branch loads the extension and is not sampled (the reconciler samples
  slots); a branch's insights are `planned`.
- Insight samples are kept 7 days and usage samples forever; both are the
  operator's to revisit when slots multiply.
