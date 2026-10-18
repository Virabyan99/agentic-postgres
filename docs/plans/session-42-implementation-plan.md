# Session 42 — The OVH upgrade, ClickStack, `pg_stat_statements`, Query Insights, monitoring, and the fourth re-earning

**Status: EXECUTING since 2026-10-18.** Run 1 **in part** (the rigs 42a,
42b, 42c; ADRs 0277, 0278, 0279; the threat list) -- **sitting U blocked: OVH
out of stock in US-EAST-VA-2 (D2598)**; the operator chose to continue the
code runs and retry; U0-U3, E0 and E1 complete Run 1 before Run 10. **Runs 2,
3 and 4 done.** Rows **D2561–D2590** at planning,
**D2591–D2596** added 2026-10-18 (the operator's amendment of Sessions
43–45: web-first, the browser SQL editor, the split, and three of Session
43's choices — recorded here because this plan holds the next free numbers;
none changes a run of this session), **D2597–D2612** by the runs. ADRs
**0277–0279** written (0277's limits re-read by E1).
**NEXT FREE: D2613, ADR 0280.**

The seventh session of Stage 5 and the second half of the operator's split
(D2510): the stage plan's *Session 42* brief (`docs/plans/stage-5-plan.md` §5
*Session 42*, `:818-853`) — **ClickStack bounded on the host, `pg_stat_statements`
loaded on every project, Query Insights through `/v1`, a curated monitoring
list** — preceded by what Session 41 handed it (`docs/scope-closure.md` §34,
*"What Session 42 inherits, in order"*, `:1636-1645`): **D2558's repair** (the
edge's attach race that took beta-dev down at Session 41's boot) and D2559's,
**the OVH upgrade as the first sitting** (D2511), and — the operator's choice of
2026-10-17 (D2561) — **the re-earning a fourth time** on a NEW `slot6-prod`, so
the six managed-project rows, `idle_sleep` and `notifications` can leave
`planned`. And D2544 (the lint's SQL reader), which the operator put in this
session the same day.

Twelve runs and **three sittings on three days**: **sitting U** (Run 1) is the
OVH upgrade alone, at the deployed `601a0ea`, before any code is written — the
new host's numbers are what ClickStack is sized against; **sitting 1** (Run 10)
is the release on the four projects (every database restarted once to load
`pg_stat_statements`, the window probed), the telemetry plane installed,
`slot6-prod` prepared, and the whole trip verified writing nothing; **sitting 2**
(Run 11), from the workstation with no SSH, `slot6-prod` created in a NEW
organisation and taken through its whole lifecycle — **an idle sleep the
reconciler requested, Query Insights read after a known workload, the samples
written as they are taken** — then the reboot (D2558 repaired: every unit back
by itself), the sweep, the external half, merge, tag.

**Brief:** `docs/plans/stage-5-plan.md` §5 *Session 42* (`:818-853`): *Builds* —
the `THR-*` rows (observability poisoning, ClickStack exhaustion) and
ClickStack's footprint measured on the new host with a control load; ClickStack
(D1964: `infra/telemetry/compose.yaml`, images by digest, bounded, unrouted,
TTLs, admission-charged; each collector's logs pipeline and OTLP export to it);
`pg_stat_statements` (D1965: the `-c` flag, the extension in `extensions`, one
restart per project in the session's deploy, the window recorded); Query
Insights through `/api/v1/projects/{id}/insights` with normalised text; *"Create
tuning proposal"* as a pointer to `migrate propose`; monitoring as a curated
signal list, each naming its source. *Must not* — route ClickStack or HyperDX,
or export telemetry off the host; put a caller value, a key, a URL or literal
query constants in a series, a log line or an insight; show a recommendation
with a confidence; let one store answer a question the other already answers.
*Measures* — ClickStack's memory and CPU under the control load; the restart
window per project. Its §1 rows **D1964** (`:297`) and **D1965** (`:298`), §8's
invariants (`:971-1005`), §9's stops (`:1009-1051`). `docs/scope-closure.md` §34
(`:1590-1645`). Session 41's plan §10, both lists
(`docs/plans/session-41-implementation-plan.md:1657-1713`), and its rows
**D2554–D2560** (`:521-527`). ADRs **0164, 0165, 0223** (the per-project
collector and store), **0195**, **0221/0222/0244** (capacity and bounds),
**0243** (proposals), **0246**, **0249** (the request lines), **0261** (trial),
**0275** (usage). `docs/threat-model.md` hosted item **9** (`:271-277`).
`docs/reality-ledger.yaml` rows `query_insights` (`:651-664`) and `monitoring`
(`:666-680`), and the eight `planned` rows named in §2. **And the operator's
four answers of 2026-10-17** (§1 D2561, D2562, D2565, D2579).

**Shape:** twelve runs. **Run 1** is documentation plus sitting U — three rigs,
the upgrade's four sheets, the host readings (E0) and ClickStack's footprint on
the upgraded host (E1), the threat list made specific, three ADRs — and reads
**no** CI verdict. **Runs 2–7** change code: each pushes and reads that commit's
own CI verdict by full SHA (`gh api
"repos/Virabyan99/agentic-postgres/actions/runs?head_sha=<40 chars>" -R
Virabyan99/agentic-postgres --jq '.workflow_runs[] | [.name, .status,
.conclusion] | @tsv'` from Git Bash, never inside `wsl`; judged on HTTP status,
three buckets — success / failure / not registered; an empty list is not a
verdict, D1057). **Run 8** writes the trip's instruments and rehearses them
offline, committing nothing but its `**Done.**`. **Run 9** is the bump. **Runs
10–11** are the sittings. **Run 12** is the close (Ledger rows and envelope
rows are code: it gates once and reads CI). **Push only after the previous
commit's CI lands** — `ci.yml` cancels in-progress runs on `main`.

**Product version at close:** `CURRENT_SESSION` **42**; `template_version`
**`1.20.0`** — predicted *minor* (**no** project-manifest, outputs, host or lock
schema change, no new secret in any manifest, no released migration; the
control set's ninth migration; new `/v1` routes; a changed `postgres` command;
eleven operation types accepted again) and **read from `upgrade plan` on the
host, never chosen** (Run 9 reads `bin/upgrade.py --also` and
`src/agentic_postgres/compatibility.py` for the declaration a changed database
command needs, D2584). Released migrations stay **39**; the control set goes **8
→ 9**. **One new platform compose project (`apg-telemetry`), one new unit
(`agentic-postgres-telemetry.service`), one new root command
(`bin/telemetry.sh`), two new customer commands (`bin/insights.sh`,
`bin/monitoring.sh`). No new published port, no new route on the edge.** A
`major` is §9's stop.

**Written for whoever picks this up cold, and it will be a different model than
the one that planned it.** Every path below was read from the tree on 2026-10-17
at `edf35ac` — three explore passes over `bin/`, `src/agentic_postgres/`,
`services/auth-api/`, `projects/control/`, `infra/`, `systemd/`, `compose.yaml`,
`versions.env`, `tests/` and `docs/`, plus direct reads of
`bin/edge-network.sh:243-336`, `bin/reconciler.py:860-872`,
`src/agentic_postgres/sql_surface.py:79-98`, `versions.env:16,19` and the
Session 41 plan whole — **and the readings taken at planning** (§0). Every path
is cited `path:line`. **Read CLAUDE.md §1 in the launch folder before the first
command, then this plan's §1, then the appendix.** If a step here and the tree
disagree, **the tree wins and the disagreement is a divergence row** (next free
`D` after §1's table), never a silent reconciliation. **When this plan names a
line number, open the file at that line and read the surrounding twenty lines
before editing** — the numbers were right on 2026-10-17 and `ruff format` moves
them.

**The ten sentences the executor most needs, in case nothing else is read:**

1. **The upgrade comes first, at `601a0ea`, before any code** (D2562). It is a
   provider act and a reboot: Sheet U0 reads and backs up, U1 is the operator in
   the OVHcloud manager, U2 reads every unit, doctor and count after, U3
   re-declares `memory_mb` in BOTH `host.yaml` copies. **D2558 is still live at
   that boot**: a unit that loses the edge race is started by hand and recorded
   — the repair is proved at sitting 2's reboot, not here.
2. **The three repairs are Run 2's, each with a failing test first** (D2563,
   D2564, D2565): `edge-network.sh` re-reads the network after a failed connect
   or disconnect (five connects, four disconnects, one helper each); the
   reconciler carries `export_upload`'s one stderr line into the refusal; the
   SQL reader becomes quote-aware, and a class guard holds every template's
   quotes balanced.
3. **`pg_stat_statements` is in the pinned image** (measured at planning, p4)
   and is loaded by `-c` flags in `compose.yaml` and created by the bootstrap
   plane in `extensions`, **with `track_utility = off`** so an `ALTER ROLE …
   PASSWORD` is never recorded, and **`PUBLIC` revoked** from its view and
   functions (D2566, D2568). Changing the command recreates — restarts — every
   project's database at the release's deploy; the window is probed, never
   assumed (D2567).
4. **Insights are sampled by the reconciler into the control database**, like
   usage (D2569): the control plane has no path to a project's database nor to
   ClickHouse. Only statements run by the customer's roles and the API's request
   roles are kept; the text is the extension's normalised text; a literal
   planted by the proof never appears (the canary).
5. **No recommendation, no confidence** (D2571): each statement carries its
   numbers and two ratios; the tuning pointer is a fixed sentence naming `apg
   migrate propose`.
6. **ClickStack is four containers in `apg-telemetry`**: ClickHouse, HyperDX,
   MongoDB (HyperDX's own state — the operator chose its own login, D2579) and a
   gateway that is **the collector image the projects already pin**, with its
   ClickHouse exporter — not ClickStack's OpAMP-supervised collector (D2573). No
   published port, no router label, every service bounded, TTLs, and **charged
   by admission at its ceilings** (D2576, D2577).
7. **A project never depends on the telemetry plane** (D2574): its collector
   joins an internal ingest network that both the project's runtime and the
   plane ensure (with D2563's re-read), stamps `project` over whatever the
   payload says, and exports through a bounded queue; the gateway down changes
   nothing a project serves — rig 42a's case 7 proves it before anything is
   built on it.
8. **The logs are D1918's lines** (ADR 0249), exported over OTLP by the
   services that print them, body = the formatted message only, no traceback
   (D2575). Nothing else is collected.
9. **The fourth re-earning writes each probe sample as it takes it** (D2581):
   the lifecycle instrument appends every sample to a JSONL file beside the
   record and flushes it, so a stop loses nothing that was measured (D2557's
   lesson). Its notifications proof counts the record's finished operations —
   a failed one included — never a fixed eleven.
10. **Ten Ledger rows move to `trial` in the bump** (D2583): the six
    managed-project rows, `idle_sleep`, `notifications`, `query_insights`,
    `monitoring` — each naming only claims this session introduces (ADR 0261) —
    and `ACCEPTED_TYPES` becomes the eleven again.

---

## 0. Where the session starts

```
HEAD            edf35ac on main, local = origin ("Session 41 Run 12 record: the
                gate and CI on 59117b5; the session closed (docs)"), tree clean.
                Code: 59117b5 (CI 39055054912 success). Deployed AND TAGGED:
                601a0ea (1.19.0, tag object 2fc0d01) on all four projects. main
                is past the tag with the close's code (the Ledger, ACCEPTED_TYPES
                = credential.rotate + the four branch types, the envelope) --
                NOT deployed: the host's 1.19.0 accepts the eleven types (no slot
                is free, so a create is no_slot).
VERSION         1.19.0 (VERSION file; read by src/agentic_postgres/__init__.py
                :1217-1220). CURRENT_SESSION 41 (__init__.py:1206; Session 41's
                paragraph :1146-1205). README.md:7 "Session 41 implemented".
                Outputs schema 22, project manifest 1-11, host.yaml 2|3|4. 39
                released migrations. The control set 8 (projects/control/
                migrations/released.lock.json, last 20261016120008
                control_plans_usage; manifest.json:87; six committed proposals,
                newest bba02721...).
REGISTRY        377 requirements (tests/acceptance-registry.yaml, 7,758 lines;
                Session 41's block :7453-7758). ID regex
                tests/contract/test_acceptance_registry.py:125 (prefixes end
                ...|EP|BR|PLAN|USE). 284 claims (src/agentic_postgres/
                evidence_claims.py CLAIMS :506-1422); 121 offline (OFFLINE_CLAIMS
                :106-459). 276 ADRs (docs/decisions/README.md last row 0276).
                NEXT FREE: D2561, ADR 0277.
EVIDENCE        evidence/session-41.json (WSL, gitignored): 284 claims, 280
                passed, 4 failed -- documented_path (D1935);
                lifecycle_reearned_live, lifecycle_third_trial_live,
                notifications_live (D2557).
LEDGER          projects_self_service, project_deletion, export, region,
                compute_profiles, sleep, idle_sleep, notifications: planned,
                target 42. query_insights, monitoring: planned, target 42
                (docs/reality-ledger.yaml:651-680; the section header :649 still
                says "(Session 41)"). console: planned, target 43. Everything
                else Session 36-41 opened: beta. target_session max 43
                (schemas/reality-ledger.schema.json:121-127).
HOST            15.204.231.45, OVH VPS US-East, apg-ovh-01. Read at planning
                (2026-10-17 18:33Z, apg-diag + op; §0's table).
OPERATOR        2026-10-17: carry the re-earning in 42; the upgrade first, at
                601a0ea; D2544 in 42; HyperDX with its own login (D2561, D2562,
                D2565, D2579).
```

**What exists, measured at `edf35ac`, and the session builds on:**

- **The edge's attach** (D2558). `bin/edge-network.sh` (344 lines): exit codes
  in the header (`:1-23`, 0/2/3/9); `edge_container` (`:91-98`), `is_attached`
  (`:112-116`: `docker inspect --format '{{json .NetworkSettings.Networks}}' C |
  grep -q "\"NET\""`), `has_alias` (`:139-144`; its comment sits at `:118-131`,
  above `is_branch_network` `:134-137`), `main` (`:189-342`) with verbs `status`
  `:202-219`, `attach` `:221-246`, `detach` `:248-259`, `attach-network`
  `:261-272`, `detach-network` `:274-286`, `reconcile` `:288-340`. **Five
  `docker network connect --alias` sites, each `die 9` on failure with no
  re-read**: `:243-244` (attach), `:269-270` (attach-network), `:318-319`
  (reconcile, re-alias), `:323-324` (reconcile, project network), `:335-336`
  (reconcile, branch loop over `docker network ls --filter label=…` `:338`). Four
  disconnect sites with `die 9`: `:240-241`, `:256-257`, `:283-284`, `:316-317`.
  (Session 41's row D2558 counted four connect sites; there are five.) Callers:
  `systemd/agentic-postgres-project@.service:35-36` (`ExecStartPost … project %i
  attach`, `… edge reconcile`), `:41-42`; `systemd/agentic-postgres-edge.service:24`
  (`ExecStartPost … reconcile`); `libexec/project-launcher:99-100`;
  `bin/edge.sh:236,349`; `bin/project-runtime.sh:333,368,380,402,430`;
  `bin/branch-runtime.py:98` (`EDGE_NETWORK_SH`). **No test runs the script**:
  `tests/contract/test_metrics_surface.py:494-510` (every connect carries
  `--alias`), `:513-524` (shellcheck); `test_project_runtime_stop_start.py:69-76`
  replaces it with a recorder. **The fake-docker pattern to copy**:
  `tests/contract/test_diagnostic_surface.py:475-526` (a `FAKE_DOCKER` script
  written to `bin_dir/"docker"` 0755, the script under test sourced with `main`
  removed, `env={"PATH": f"{bin_dir}:/usr/bin:/bin"}`).
- **The export's refusal** (D2559). `bin/reconciler.py` `export()` (`:823-886`):
  the upload `container_exec.run(names[0], "python", "-m", "app.export_upload",
  "--operation", operation.id, input=body, …, text=False)` (`:860-866`); on a
  non-zero code `Refused("operation_failed", {"reason": f"the upload exited
  {uploaded.returncode}"})` (`:867-870`); `uploaded.stderr` is never read.
  `container_exec.run` captures both streams (`src/agentic_postgres/container_exec.py:88-120`,
  `:116`). The child `services/auth-api/app/export_upload.py`: exit codes
  `:18-20`; `export_upload: {error}` to stderr and exit 5 on a `StorageError`
  (`:76-80`); other stderr lines `:59, :63, :68, :72`. The test
  `tests/contract/test_reconciler_dispatch.py:912-942` (fake stderr `b""`
  `:166-169`; with `upload_code = 5` `:937` asserts only the code).
- **The lint's SQL reader** (D2544). `src/agentic_postgres/sql_surface.py`:
  `up_section` (`:63-65`, split at `-- migrate:down`), `sql_only` (`:79-93`:
  `"\n".join(line.split("--")[0] for line in text.splitlines())`; its docstring
  `:88-91` asserts no template has `--` in a literal), `statements` (`:96-98`).
  Readers (D979): `sql_surface.final_surface` `:119`, `final_function_bodies`
  `:176`; `migrations.release_functions` (`:793`, call `:808`),
  `lint_project_set` (`:823`, `:905`), `destructive_findings` (`:1164`, `:1181`);
  through `final_surface`: `migrations.py:898`, `bin/migrate.py:807`; through
  `final_function_bodies`: `bin/migrate.py:792`, `bin/mcp-contract.py:173`,
  `rendering.py:2635` (the approval gate); `sql_only` directly:
  `migrations.py:989`, `dev_environment.py:710`,
  `tests/contract/test_project_migration_sets.py:798,804`,
  `test_database_function_signatures.py:388`. Test-local copies (not the
  product's reader): `test_api_migrations.py:131,148`,
  `test_identity_registry.py:46`. The lint's proofs: `TEN-SET-002`
  (`tests/acceptance-registry.yaml:2838-2846`,
  `test_the_lint_reads_statements_and_not_comments` `:2843`).
- **The database's definition.** `compose.yaml` `postgres` (`:185-291`): built
  from `./services/postgres` with `BASE_IMAGE=${POSTGRES_IMAGE}` (`:198-203`) =
  `docker.io/pgvector/pgvector:pg18@sha256:69167330…` (`versions.env:19`);
  `mem_limit` `:211`, `shm_size` `:212`; `command:` (`:223-267`) is `postgres`
  and `-c` flags for `shared_buffers` `:226`, `max_connections` `:228`,
  `work_mem` `:230`, `maintenance_work_mem` `:232`, `listen_addresses=*` `:238`,
  `archive_mode` `:257`, `archive_command` `:259`, `archive_timeout` `:267`;
  healthcheck `:268-273`. **No `shared_preload_libraries` anywhere** (0 hits).
  The branch's command: `infra/branch/compose.yaml:41-56`, generated by
  `src/agentic_postgres/branch_plan.py:119-142` (`persistent_command()`). The
  restore paths' commands: `restore_drill.instance_command()`
  (`restore_drill.py:730-743`; used `bin/restore-test.py:390,861`) and
  `node_restore.instance_arguments()` (`node_restore.py:339-343`; used
  `bin/restore.py:339`) — `("postgres", "-c", "archive_mode=off")` only. **A
  changed `command` recreates the container at the next `compose up -d --build
  --wait`** (`bin/project-runtime.sh:314`; Compose hashes the service
  definition; ADR 0155's label `apg.mounted.sha256`,
  `runtime_override.py:1155,1189-1228`, covers only mounted content).
  `capacity.ENVELOPE`'s restart row (`capacity.py:793-819`: rest 3.1 s, every
  dependent back in 6.9 s) is an **induced `docker restart -t 30` on the old
  host at 1.13.0 — not a recreate**; the closest recreate figure is the resize
  row (`:1373-1403`, 84 s for the whole deploy step).
- **The bootstrap plane.** `src/agentic_postgres/bootstrap_statements.py`
  `build_statements()` (`:78`): `CREATE SCHEMA IF NOT EXISTS extensions
  AUTHORIZATION object_owner` (`:316`), `CREATE EXTENSION IF NOT EXISTS vector
  WITH SCHEMA extensions;` (`:318`), `USAGE` on `extensions` to the customer
  roles (`:458`); the only predefined-role grant `pg_read_all_settings` to
  `backup_user` (`:185-187`, constant `:507`). Executed by
  `bin/postgres-bootstrap.py` `psql()` (`:116-140`, `docker exec -i … psql -U
  postgres`); `check_violations` (`:148`) verifies `vector` (`:310-314`).
  Migrations may not create extensions (`migrations.py:175-176`). Sixteen roles
  (`naming.ROLE_SUFFIXES` `naming.py:167-197`, `database_roles()` `:1171`):
  anon, authenticated, agent_reader, agent_writer, project_admin,
  postgrest_authenticator, auth_service, mcp_audit_service, storage_service,
  migration_user, backup_user, app_runtime, object_owner, api_documentation,
  customer_app, customer_admin.
- **The usage sampler** (Session 41, ADR 0275). `bin/reconciler.py`:
  `USAGE_SAMPLE_SECONDS = 300` (`:134`), `BACKUP_RECORD_SECONDS = 900`
  (`:130`), `record_backups` (`:1205-1223`), `record_usage` (`:1225-1268`),
  `usage_of` (`:1435-1488`), `_branch_usage` (`:1491-1508`), the loop
  (`:1640-1668`); `database_call` (`:267-294`). `src/agentic_postgres/usage_reading.py`:
  `cluster_fields` `:46-62`, `cluster_int` `:65-85`, `directory_kb` `:88-102`,
  `store_value` `:105-163`, `activity_sql` `:166-179`, `durable_counts_sql`
  `:182-203`. `src/agentic_postgres/reconciler_dispatch.py`: control SQL
  `:184-214` (`RECORD_USAGE` `:209`, `REQUEST_IDLE_SLEEP` `:210`,
  `RECORD_LIMIT_NOTICE` `:211`), project-database SQL `:226-243`,
  `USAGE_FIGURES` (`:687-698`), `usage_sample` (`:706-735`). The control set's
  `0008-control-plans-usage.sql`: `app.control_usage_samples` (`:126-155`;
  `unread` CHECK whitelist `:143-147`), `control_record_usage` (INVOKER, granted
  to nobody, `:529-570`, key whitelist `:541-545`), `control_usage_document`
  (`:754-865`), `control_project_usage` (`:867-882`), `control_org_usage`
  (`:884-910`), grants `:938-959`. **DB time is ABSENT** — no column, not in
  `USAGE_FIGURES`, not in the document; Session 41's §10 sentence *"the usage
  document says not read for it"* is not what the tree does (D2570). The guard
  `tests/contract/test_reconciler_dispatch.py:1449-1469` regex-scans the module
  for `app\.(control_[a-z_]+)\(` and asserts the closed set of thirteen names.
- **The control routes.** `services/auth-api/app/control_routes.py` (prefix
  `/v1` `:71`): projects `GET /projects` `:667`, `POST` `:733`, `/{key}/sleep`
  `:777`, `/wake` `:798`, `/compute` `:815`, `/export` `:848`, `DELETE /{key}`
  `:869`, `/credentials` `:889`, `/connections` `:920`, branches `:969-1086`,
  `/backups` `:1107-1127`, `GET /{key}` `:1130`, `/usage` `:1351-1374`,
  `/idle-sleep` `:1377`. Usage: `get_project_usage` → `control_service.project_usage`
  (`control_service.py:891-895`, `_usage` `:1104-1116`) →
  `control_repository.project_usage` (`:372-377`) → `app.control_project_usage`.
  `control_roles.py`: `MATRIX` `:48-113`, `PROJECT_WRITES` `:129`,
  `KEY_VOCABULARY` `:165`, `KEY_SCOPES` `:195-230` (`get_project_usage` `:228` →
  `projects:read`). The OpenAPI snapshot `contracts/control-openapi.canonical.json`,
  regenerated by `bin/app-contract.sh --update --snapshot control >
  contracts/control-openapi.canonical.json` (`bin/app-contract.sh:39`; it
  streams to stdout).
- **The per-project telemetry** (ADRs 0164, 0165, 0223, 0265). `compose.yaml`
  `metrics` (`:1216-1296`): image `${OTEL_COLLECTOR_IMAGE}` =
  `docker.io/otel/opentelemetry-collector-contrib:0.159.0@sha256:1f2c54a3…`
  (`versions.env:16`), `pids_limit`/`cpus` from `METRICS_*` (`:1222-1223`,
  defaults `config.py:744`), `mem_limit: 192m` (`:1255`;
  `runtime_override.METRICS_MEMORY_LIMIT_MB = 192` `:393`), config bind-mounted
  from `{rendered}/otelcol.yaml` (`runtime_override.py:280-281,888-896`),
  healthcheck `/otelcol-contrib --version` (`:1268-1287`), network `edge` only
  (`:1294-1295`). `store` (Prometheus, `:1311-1385`; `versions.env:20`; *"No
  remote write, no exemplars, no OTLP receiver"* `:1329`). The collector's config:
  `src/agentic_postgres/rendering.py` `build_otel_config` (`:1355-1521`):
  receivers `otlp` (grpc 4317, http 4318) and a `prometheus` scrape of the edge
  (`:1414-1452`, keep rule `:1443-1452`); processors `memory_limiter` (96/24 MiB,
  `runtime_override.py:381-382`) and `batch` (`:1454-1464`); exporter
  `prometheus` on :8889 with `const_labels: project` (`:1466-1504`, `:1489-1490`);
  **only a `metrics` pipeline** (`:1515-1518`); *"no exporter to anywhere off the
  host"* (`:1383-1386`). The OTLP receiver's one sender: `mcp`'s metrics,
  `APG_OTLP_ENDPOINT: http://metrics:4318/v1/metrics` (`compose.yaml:2004`;
  `services/auth-api/app/settings.py:82-83`; `mcp_metrics.py:147,162`).
- **D1918's lines** (ADR 0249). `services/auth-api/app/log_setup.py:31-48`:
  `LOGGERS = ("apg", "app.workflow_worker")`, one stdout `StreamHandler` each,
  formatter `%(message)s`, marker `_apg_stdout`, INFO, propagation on; called
  first in `create_app` (`main.py:271-273`). Lines: `apg.http.request {json}`
  (`request_id, method, route, status, elapsed_ms`; `main.py:428,449-463`),
  `apg.mcp.read` (`mcp_telemetry.py:46,170-172`), the worker's (`main.py:218`,
  `workflow_worker.py:90`). Canary: `tests/contract/test_request_log.py:85`
  (`test_a_request_prints_one_line_with_the_template_and_no_caller_value`),
  `:71`, `:115`, `:129`; live `tests/deployment/test_session36_operations.py:102`.
- **The edge and the platform's units.** `infra/edge/compose.yaml` (`name:
  ${EDGE_STACK_NAME}` = `apg-edge`, `host_config.py:275`): `docker-socket-proxy`
  64m/64/"1.0" (`:31-33`), `traefik` 608m/76/"1.0" (`:122-124`), images by
  digest (`versions.env:13,23`), limits as literals. Run by `bin/compose.sh
  --edge` (`:44,275`) and `bin/edge.sh` (`compose --runtime up -d --wait`
  `:219`); unit `systemd/agentic-postgres-edge.service` (`ExecStart …/edge up`
  `:17`, `ExecStartPost … reconcile` `:24`) through `libexec/agentic-postgres-edge`
  (`:75`). `bin/provision-host.sh` installs every `systemd/*.service|*.timer`
  (`:834-840`) and enables only the firewall unit (`:847`); the operator enables
  the edge unit by hand (`docs/operator-guide.md:173-180`). Other units:
  `agentic-postgres-reconciler.service`, `-docker-firewall`, `-project@`, the
  backup services and timers. **No `infra/telemetry/`.** Bound tests:
  `tests/contract/test_process_limits.py` (`:48`, `:62`, `:164`, `:188`
  `test_the_edge_plane_is_bounded`, `:216`, `:234`); live
  `tests/deployment/test_session35_governance.py:627` (the edge) and **`:653`
  `test_no_running_compose_container_is_unbounded` — every running Compose
  container on the host, so it covers `apg-telemetry` without a change**. Claims
  `every_service_bounded` (`NODE-LIMIT-002`) and `every_service_bounded_live`
  (`NODE-LIMIT-003`) (`evidence_claims.py:789,793`; registry `:5931-5951`).
- **Capacity.** `schemas/host.schema.json:30-54` (`capacity`: `memory_mb`,
  `reserve_memory_mb`, `disk_gb`, `reserve_disk_gb`; **no cpus**);
  `host_config.Declared` (`:84-111`; `claimable_memory_mb` `:111`);
  `capacity_reading.decide` (`:386`; `safe_available = memory_mb −
  reserve_memory_mb − committed` `:450`; refusal `:468-476`); `committed_total_mb
  = sum(committed) + sum(branches)` (`:181-182`); `committed` = other projects'
  `database.budget.unreclaimable_mb` (`:291-323`); branches (`:173-178`,
  `capacity_probe.py:382`); `ceilings` and `unbounded` reported, never charged
  (`:151-158`). **Nothing charges a platform component**: the edge sits inside
  `reserve_memory_mb` (`host.example.yaml:40-44`). ADR 0244's rule (`:56-60`):
  memory = max(4 × `memory.peak` rounded up to 32 MiB, 64), pids = max(4 ×
  `pids.peak`, 64), `cpus` "1.0"; *"Admission is unmoved: it charges
  `unreclaimable_mb`, never a cap"* (`:103-104`). `capacity.ENVELOPE` (`:113`),
  Session 41's section `:1955-2106`; `UNMEASURED` `:2115-2231` (ten entries,
  among them *a usage pass's duration* `:2131-2139`, *the rescaled host's
  capacity* `:2156-2166`).
- **The re-earning's proofs and instruments.** Session 41's external modules
  `tests/external/test_session41_reearning.py`, `tests/external/test_session41_branches.py`,
  host `tests/deployment/test_session41_branch_host.py`; the older fixtures that
  widen each session (`RECORD_SESSIONS` in `test_session38_public_lifecycle.py`,
  `record39`, `record40`, the branch fixtures) — **Run 9 greps each for its
  session tuple** (`grep -n "RECORD_SESSIONS\|in (39\|in (40\|== 41\|(41," tests/external tests/deployment`).
  Instruments in WSL `~/s41/run8/` (`s41-lifecycle.py` 1,188 lines,
  `s41-derive.py`, `s41-hostyaml.py`, `rehearse_lifecycle41.py`), the resume
  `~/s41/run11/make-resume41.py`, the shape check `~/s41/run11/s41-r2diag.py`;
  the Session 41 record `~/s41/lifecycle.json`.
- **The gate to derive from.** `bin/session-41-check.sh` (2,126 lines; header
  `:1-94`, `readonly SESSION=41` `:103`, `usage` `:179-`, `parse_arguments`
  `:903`, `run_suite` `:1142`, `mode_offline` `:1582-1799`, `mode_host`
  `:1801-2019`, `mode_external` `:2021-2115`). `tests/contract/test_session_forty_one_gate_modes.py`
  (1,105 lines; `SESSION = 41` `:57`, `SESSION_PREVIOUS_NUMBER = 40` `:72`,
  claims `:84-`). Roster `tests/conftest.py:86-225`. **The gates run in shards**
  (D2554): `~/s41/run9/gate01-steps.sh`, `gate01-shard.sh N` (16,
  `shards01.json`), `gate01-step8.sh`; `gate41-steps.sh A|B`, `gate41-shard.sh N`
  (9), `gate41-step9.sh`.

**Measured at planning** (2026-10-17; no rig was run except p4 — every other
third-party fact this plan needs is Run 1's, §5):

| # | Reading | Result |
|---|---|---|
| p1 | `apg-diag containers` (18:33Z) | exit 0; 42 containers healthy, four projects (alpha-dev, beta-dev, control-prod ×10, slot3-prod ×12); no branch |
| p2 | `apg-diag listeners` | 22, 80, 443, 5432 (+ the resolver's loopback 53, chrony 323, DHCP 68) |
| p3 | op: checkout, `free -m`, `df -h /`, `lsblk`, `uptime`, `nproc`, units | `601a0ea` clean; total 7,746, **available 5,156 MiB**; `/` 72 G, 11 G used (`sda` 75 G, `sda1` 73.9 G); up 3 h 49 min; 4 × Haswell; the reconciler, the edge and the four project units active, `NRestarts` 0; `/etc/agentic-postgres/branches/` empty |
| p4 | `docker run --rm --entrypoint sh <POSTGRES_IMAGE>` (WSL, `versions.env:19`'s digest): `postgres --version`; `ls /usr/share/postgresql/18/extension`; `ls /usr/lib/postgresql/18/lib` | `PostgreSQL 18.4 (Debian 18.4-1.pgdg12+1)`; `pg_stat_statements.control`, `pg_stat_statements--1.4.sql` (+ upgrade scripts), `pg_stat_statements.so` present — **control**: `vector.control`, `vector--0.8.6.sql`, `vector.so` |
| p5 | `/etc/agentic-postgres/00-agentic-postgres-ssh.conf` (op, readable) | `AllowTcpForwarding local`, `GatewayPorts no`, `AllowAgentForwarding no` — a local forward works for every account the file covers |
| p6 | `~op/agentic-postgres/host.yaml` (the checkout's copy) | `schema_version: 4`; `capacity.memory_mb: 7746`, `reserve_memory_mb: 2214`, `disk_gb: 71`, `reserve_disk_gb: 8` |
| p7 | ClickStack's open-source distribution (ClickHouse's documentation, read 2026-10-17; **not measured**) | four images — ClickHouse, HyperDX, an OpenTelemetry collector and MongoDB — under `clickhouse/clickstack-*` (formerly `docker.hyperdx.io/hyperdx/*`); HyperDX asks for a user on first visit; its collector is supervised over OpAMP by HyperDX (port 4320). **Every one of these is Run 1's rig 42a to measure** |

---

## 1. The divergence table

Six columns. Each row is a **measured fact about the tree at `edf35ac`** (or the
host as the planning readings left it) set against what the brief says, with
the decision this plan takes. **Next free number after this table is D2597.**
Rows the runs add go in a second table below it, in execution order.

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D2561** | Scope closure §34 item 4: *"The re-earning, a fourth time, on a NEW `slot6-prod`, **when a session carries it**"*; stage plan §5 *Session 42* names no re-earning. | The six managed-project rows, `idle_sleep` and `notifications` are `planned`, **target 42** (`reality-ledger.yaml`); `main` accepts five types (D2560). Session 41's lifecycle ran every operation at the tagged commit; its claims failed because the instrument held four windows' samples in memory (D2557). | **The operator, 2026-10-17: carry it in 42.** Sitting 2 runs the lifecycle on `slot6-prod` in a NEW organisation `lifecycle-s42`, at the one commit, after the dry run (D2448's order), with the samples written as taken (D2581). The ten rows go `trial` at the bump (D2583). | The product ran; the evidence did not survive the instrument. Session 45 is the release and the walk (D2593); leaving it a re-earning as well would put three things on the last trip. | 0261 |
| **D2562** | Scope closure §34 items 1–2: *"D2558's repair … before the next boot that matters"*, then *"the OVH upgrade (D2511), its first sitting"*; Session 38's plan `:1903`: *"the OVH plan upgrade (12 GB)"*. | The host is the plan bought as *"8 GB / 4 vCore"* (`session-38-migration-plan.md:103`): 7,746 MiB, 4 vCPU, 72 G (p3, p6). Nothing in the tree records the OVHcloud upgrade's mechanics (whether it reboots, keeps the IPv4 and the disk, grows the partition, can be undone). D2558 is unrepaired on the host. Session 36's in-place rescale sheets H1–H4 (`session-36-implementation-plan.md:1832-1869`) are the shape of an in-place change; it was never taken (D2032). | **The operator, 2026-10-17: the upgrade first, at `601a0ea`, before any code.** Sitting U (Run 1): **Sheet U0** (the reconciler stopped, D2178; incremental backups of the four projects; row counts; `free -m`, `nproc`, `lsblk`, `df -h /`, the units; the edge's state file), **Sheet U1** (the operator, in the OVHcloud manager: the 12 GB plan — **its name, vCPU, disk, price, whether it reboots, keeps the IPv4 and can be undone are READ there and recorded on the sheet's transcript, never assumed by this plan**; stop if it says the IPv4 changes), **Sheet U2** (after: `s42-after-upgrade.sh` derived from `~/s37/run11/after-reboot.sh` — every unit's `ActiveEnterTimestampMonotonic` against `multi-user.target`'s (D2140); **a unit that lost D2558's race is started by `sudo systemctl start` and recorded, never retried in a loop**; the four doctors 12 ok; the counts equal U0's; `free -m`, `nproc`, `lsblk`, `df -h /`; the IPv4 still `15.204.231.45`), **Sheet U3** (`memory_mb` from U2's `free -m` total, and `disk_gb` from the reading the doctor takes — **only if it moved** — re-declared in BOTH copies by `s42-hostyaml.py` (derived from `~/s41/run8/s41-hostyaml.py`), `reserve_memory_mb` and `reserve_disk_gb` unchanged (D1992's precedent), the reconciler started (D2411), `sudo bin/doctor.sh capacity --host host.yaml` read). **A partition that did not grow is not grown in this session** (a `growpart` is a root act on the root disk; recorded, carried). | ClickStack is sized against the host it will run on; the upgrade's own reboot is a provider act whose risk is known (D2558, one unit, started by hand at Session 41's boot) and costs nothing a repair would save; the repair is proved where it is needed — the trip's reboot. | 0221 |
| **D2563** | D2558: *"after a failed connect, re-read `is_attached` and `has_alias` and succeed if both hold — a test with a fake docker that attaches between the check and the connect, a battery."* | Five connects and four disconnects `die 9` on Docker's answer with no re-read (§0). The same check-then-act shape will appear twice more in this session: the telemetry ingest network ensured by a project and by the plane (D2574). | **Two helpers in `bin/edge-network.sh`**: `connect_alias NETWORK CONTAINER` (connect; on failure re-read `is_attached` AND `has_alias`; both hold → `0` with one stderr line *"already attached by another unit"*; else `die 9` with Docker's text) and `disconnect_quiet NETWORK CONTAINER` (disconnect; on failure re-read: not attached → `0`; else `die 9`). **All nine sites call them**; a test greps the script for `docker network connect`/`disconnect` outside the two helpers and finds none (the class guard, D600). **Tests** (`tests/contract/test_edge_network_race.py`, the `test_diagnostic_surface.py:475-526` pattern): a fake `docker` whose `network connect` records the attachment in a state file and THEN exits 1 with *"endpoint with name apg-edge-traefik-1 already exists in network …"* (another unit won) → `attach` exits 0; **control**: the connect exits 1 with *"network not found"* and records nothing → exit 9; the same pair for `reconcile` and `attach-network`, and for a disconnect that loses (*"is not connected"* after another unit detached) → 0. **The same helper shape** in `bin/telemetry.sh` and `bin/project-runtime.sh`'s network ensure (D2574): `docker network create` failing *"already exists"* → re-read the network's labels and `internal` flag; equal → 0; different → refuse. | A check-then-act on shared state is a race when two units act; the reader of *already done* must not call it failure (D2558's own sentence). | — |
| **D2564** | D2559: *"the upload's error line carried into the refusal's `reason` (it names no target by construction, ADR 0259)"*. | The reason is `the upload exited N` (`reconciler.py:867-870`); `export_upload` prints `export_upload: <StorageError>` (`export_upload.py:76-80`) and four other stderr lines (`:59-72`). | **Run 2 reads every `print(…, file=sys.stderr)` in `export_upload.py` whole** (D2416's rule) and records what each can hold. The reconciler takes **the last stderr line that starts `export_upload: `**, cut to 200 characters, and appends it: *"the upload exited 5: export_upload: SignatureDoesNotMatch …"*; **refused as text** — the reason stays `the upload exited N` — if the line holds `://`, `X-Amz-` or `Signature=` (a belt; a test plants each). Tests in `test_reconciler_dispatch.py` beside `:912-942`: the fake returns the provider's code on stderr → the reason carries it; **control**: a stderr holding a presigned URL → the bare reason. | A failure whose cause is printed and then dropped is reported as an exit code (ADR 0195). | 0259 |
| **D2565** | D2544: *"A quote-aware reader, with a failing test first, is owed; the operator decides when."* | `sql_only` cuts every line at its first `--` (`sql_surface.py:79-93`); a `--` inside `'…'` drops the closing quote and every later reader reads the rest of the file as a string (Session 41 measured 10 destructive findings where 12 were due). 18 of 51 templates had an odd quote count after the reader (a heuristic). | **The operator, 2026-10-17: in 42.** **Failing test first**: `tests/contract/test_sql_reader_quotes.py::test_a_dash_dash_inside_a_literal_is_kept` (a template with `'a -- b'` followed by a `DROP TABLE`; `destructive_findings` must find the drop). Then `sql_only` becomes a character scanner with three states — code, `'…'` literal (`''` is an escaped quote), `"…"` identifier — that drops `--` to end of line only in code and keeps newlines; dollar-quoted bodies are scanned as code (a function body's `--` is a comment and its `'…'` a literal, the same lexing). **Before and after, over every template the product reads** (release `migrations/templates/*.sql`, `projects/control/migrations/templates/*.sql`, every `projects/*/migrations/templates/*.sql`): the old and new `statements()` output diffed and every difference listed in the run's `**Done.**`; **class guard** `test_every_template_ends_its_scan_outside_a_literal` (the scanner's final state is *code* for every template — the 18-odd heuristic replaced by the reader's own state). **An `E'…'` string or a dollar-quoted DATA string holding a `'`** in any template is measured first (`grep -n "E'" …`; the scanner's end state finds the second) — if either exists, the scanner handles it and a test names the template. **A new lint or destructive finding in an APPLIED release or control migration is §9's stop** (never amend an applied migration, D912). | The reader was right only for files that avoided the one shape it could not read; the guard moves from a promise in a docstring to the reader's own state. | — |
| **D2566** | D1965: *"`pg_stat_statements` is loaded (`-c shared_preload_libraries=pg_stat_statements`, `CREATE EXTENSION` in `extensions` by the bootstrap plane)"*. | 0 hits for `shared_preload_libraries` (§0). The pinned image ships the extension (p4). The bootstrap creates `vector` in `extensions` as `postgres` (`bootstrap_statements.py:316-318`) and `check_violations` verifies it (`postgres-bootstrap.py:310-314`). PostgreSQL grants the view `pg_stat_statements` to `PUBLIC` by default — a non-superuser sees its own statements' text; `pg_stat_statements_reset` is superuser-only (PostgreSQL's documentation; **rig 42b measures both on 18.4**). `extensions` is `USAGE`-granted to the customer roles (`:458`). | **`compose.yaml`'s `postgres` command gains**: `-c shared_preload_libraries=pg_stat_statements`, `-c pg_stat_statements.max=1000`, `-c pg_stat_statements.track=top`, `-c pg_stat_statements.track_utility=off`, `-c pg_stat_statements.track_planning=off` (each a separate `-c` line in the `:223-267` block's style). **`build_statements()` gains** `CREATE EXTENSION IF NOT EXISTS pg_stat_statements WITH SCHEMA extensions;` after `vector`, then **`REVOKE ALL ON extensions.pg_stat_statements, extensions.pg_stat_statements_info FROM PUBLIC;`** and `REVOKE ALL ON FUNCTION extensions.pg_stat_statements_reset(oid, oid, bigint, boolean) FROM PUBLIC;` (the signature read on 18.4 by rig 42b, never typed from memory) — the reader is `postgres` through the container (D2569), so no role is granted. `check_violations` verifies the extension, the preload (`SHOW shared_preload_libraries`) and the revocation (`has_table_privilege('customer_app', 'extensions.pg_stat_statements', 'SELECT')` false). **A branch** (`branch_plan.persistent_command()` `:119-142`) gains the same five flags — its catalogue holds the parent's extension, and a server that holds an extension it cannot serve is a branch that fails its customer's `SELECT` (rig 42b reads the error). **The restore paths stay as they are** (they end: a drill, a node restore); rig 42b proves a cluster holding the extension starts without the preload and `pg_dump --schema=app --schema=api --schema=public` (the export's shape) is unchanged. | Loaded where every project runs, unreadable by anyone but the platform's own reader; the defaults that would record a password are turned off where they are set. | **0278** |
| **D2567** | D1965: *"one database restart per project, scheduled into the session's deploy and measured against the envelope's 3.1 s row"*. | The 3.1 s row is an induced `docker restart` at 1.13.0 on the old host (`capacity.py:793-819`), **not a recreate**; a changed `command` makes `compose up` RECREATE the container (§0). A recreate also re-runs `postgres`'s 60 s `start_period` healthcheck before `--wait` returns (`compose.yaml:268-273`). Shared memory for `pg_stat_statements.max=1000` comes out of the container's `mem_limit` (`:211`). | **No number is assumed.** Rig 42b measures, on the workstation with the pinned image and the project's `mem_limit` and `shm_size`, (a) the recreate's unavailability (first refused connection → first `SELECT 1`) and (b) the backend memory delta with the extension loaded at `max=1000` against the same cluster without it (**control**); if the delta exceeds 32 MiB, the database budget's `unreclaimable_mb` rule is re-read and the row says what moves (ADR 0244's rounding). **On the trip**, `s42-window.py` (Run 8) probes each project's `routes.app` `/api/rest/` and `/api/auth/health` once a second through every R2 sheet and records the window per project; the close writes them into the envelope's Session 42 section. **`slot3-prod`'s customer is told in the release note and in `docs/managed-projects.md`**: *"1.20.0 restarts your database once, at the release."* | A restart message nobody timed is the stage's failure mode (stage plan §9). | — |
| **D2568** | Stage plan *Must not*: *"Put a caller value, a key, a URL or literal query constants … in an insight (the canary)."* | No reader exists. `pg_stat_statements` normalises constants in planned statements by query jumbling; **utility statements are recorded with their text as typed** when `track_utility` is on (PostgreSQL's documentation — an `ALTER ROLE … PASSWORD '…'` from the bootstrap or a credential rotation would be stored); statements inside functions are recorded only with `track = all`. Every platform role runs statements the customer never wrote (the worker's 5-second heartbeat, D2456; auth; storage; the audit). | **Insights are the statements of the project's customer-facing roles only**: `userid` in (`customer_app`, `customer_admin`, `anon`, `authenticated`, `agent_reader`, `agent_writer`) — names derived by `naming.database_roles(key)`, never typed. **Rig 42b measures which role a PostgREST request records under** (`authenticator` then `SET ROLE`: the extension records the role current at execution, or the login role — measured, with a control request as `customer_app` over a direct connection), and the set is narrowed or widened to what the rig shows; the row's `Done.` says which. `track_utility = off` and `track = top` (D2566). The text is the extension's, cut to 2,000 characters. **The canary** (a Docker-backed test, `control_cluster.py`-style, `tests/contract/test_insights_reading.py`): as `customer_app`, `SELECT … WHERE x = 'APG-INSIGHT-CANARY-<uuid>'` and a `DO $$ … $$` holding the canary; as `postgres`, `ALTER ROLE customer_app PASSWORD '<canary>'`; the reading's rows hold none of the three, and the first's normalised text (`$1`) is present — **control**: a query by `auth_service` (a platform role) is absent. | A literal is the customer's data and a password is the platform's; the reader keeps neither by construction, and the canary proves it on a real server rather than on a fixture that shares the reader's belief (CLAUDE.md §7 question 6). | **0278** |
| **D2569** | D1965: *"Query Insights … read through the container the way the doctor reads, **sampled into ClickHouse for history**."* | The control plane holds nothing that opens a project's data (ADR 0246; stage plan §8). The route that serves a customer reads the control database through DEFINER functions (`control_project_usage`, §0); the control project has no network to a telemetry store and no credential for one. The reconciler already reads each slot through `container_exec` every 300 s and records into the control database (ADR 0275). | **The history lives in the control database, not ClickHouse** — the store the route already reads. 0009 adds **`app.control_insight_samples`** (`project_key`, `observed_at`, `queryid bigint`, `role text`, `calls bigint`, `total_exec_ms double precision`, `rows bigint`, `shared_blks_hit bigint`, `shared_blks_read bigint`, `query varchar(2000)`, `stats_reset timestamptz`; primary key `(project_key, observed_at, queryid, role)`), written by **`app.control_record_insights(p_samples jsonb)`** (INVOKER, granted to nobody, a key whitelist, the `control_record_usage` shape) **in the usage pass** (`USAGE_SAMPLE_SECONDS`), one psql per slot: the **top 50 by cumulative `total_exec_time`** of the D2568 roles, **counters as read** with `pg_stat_statements_info.stats_reset` (D553: a cumulative counter answers no point-in-time question; the document computes increases). **The writer deletes the key's samples older than 7 days** in the same statement (`INSIGHT_KEEP_DAYS = 7`, a constant the ADR names — ~4,800 rows per slot per day × 7). **ClickHouse holds D1918's lines** for the operator (D2575); **no question is answered by both** (the brief's *Must not*). **The pass logs its duration** (one line, `usage pass for <key>: <s> s`) — the envelope's `UNMEASURED` *"a usage pass's duration"* (`capacity.py:2131-2139`) is read on the trip and moves out at the close. | A route reads one store; putting a customer's history where the control plane cannot reach would need the control plane to reach it. | **0278**, 0275 |
| **D2570** | ADR 0275 `:75-76`: *"Not metered in Session 41: DB time (needs `pg_stat_statements`, Session 42)"*; Session 41's §10: *"the usage document says not read for it"*. | **DB time is absent**: no column in `control_usage_samples` (`0008:126-155`), not in `USAGE_FIGURES` (`reconciler_dispatch.py:687-698`), not in the document (`0008:754-865`). | **0009 adds `db_time_ms double precision` and `statements_reset timestamptz` to `app.control_usage_samples`**, re-creates `control_record_usage` with the two keys added to its whitelist (the body otherwise byte-equal to 0008's — a test diffs them minus the added keys), and `control_usage_document` gains `db_time` (the **sum of increases** of the cumulative `sum(total_exec_time)` over the D2568 roles between consecutive samples, a decrease or a moved `stats_reset` read as a reset, D553). `unread`'s CHECK whitelist gains `db_time`; a sample whose extension cannot be read names it. `USAGE_FIGURES` gains it. The Session 41 sentence is recorded as wrong (this row). | The figure exists now; *absent* would read as *zero* on a page that sums. | **0275** amended |
| **D2571** | D1965: *"top N by total time with calls, mean, rows and shared-block reads, normalised text only … No recommendation engine: a finding states the evidence (calls, rows scanned vs returned) and never a confidence; 'Create tuning proposal' opens `migrate propose` for a migration the customer writes."* | `pg_stat_statements` has no *rows scanned* (it has rows returned and block counts). `bin/migrate.sh propose` is a workstation verb over a project's own set (`:75-81`, `:273-275`; ADR 0243). | **`GET /v1/projects/{key}/insights?hours=N&limit=M`** (`N` 1..168 default 24, `M` 1..50 default 20), viewer+, keys `projects:read`, through **`app.control_project_insights`** (DEFINER, membership-checked; a foreign and a missing project answer alike, THR-CTL-ENUMERATION's rule). The document: `window {from, to}`, `samples {expected, present}`, `resets`, and per statement `{query, role, calls, total_ms, mean_ms, rows, rows_per_call, shared_blks_read_per_call, cache_hit_ratio}` — **each the increase over the window**, ordered by `total_ms`; **no `finding`, `recommendation`, `confidence` or `severity` member** (a test reads the OpenAPI snapshot for those four words); a fixed member `tuning`: *"To change a query plan, write a migration in your project's set and run apg migrate propose (docs/developer-guide.md)."* A window with no sample → `could_not_determine` with the reason, never an empty list (ADR 0195). **`apg insights show --project-key K [--hours N] [--limit M] [--json]`** (`bin/insights.sh`, a shim of `bin/endpoint.sh`'s shape into `bin/cloud.py`'s new `insights` family). | Numbers the reader can check; a sentence that sounds like advice is the value that looks measured (D1535). | **0278** |
| **D2572** | Stage plan: *"Monitoring: a curated signal list, each naming its source"*; Ledger `monitoring.stage5_reality`: *"A curated signal list, each naming its source, and ClickStack bounded on the host (D1964)."* | Each reading a signal would show already exists in the control database: the usage samples (database and repository bytes, connections, requests, DB time after D2570), the backups readings (`control_backup_readings`), the registry's state. Nothing lists them. | **A release table `services/auth-api/app/signals.py`**: `SIGNALS` — each `Signal(name, unit, source, column)`, ten at most: `state` (registry), `database_bytes`, `repository_bytes`, `customer_connections`, `requests_last_hour`, `db_time_last_hour` (usage samples), `backup_status`, `latest_recoverable_time`, `last_full_backup_at` (backups reading), `insights_sampled_at` (insight samples). **`GET /v1/projects/{key}/monitoring`** serves each with `value`, `observed_at`, `source` — or `unread` with the reason — through **`app.control_project_monitoring`** (DEFINER) reading **only** those tables; **no new reader, no new sample**. Guard `tests/contract/test_signals.py::test_every_signal_names_a_source_that_exists` (the column exists in 0008/0009 or 0006) and `::test_no_two_signals_read_one_column`. **`apg monitoring show --project-key K`** (`bin/monitoring.sh`). The operator's half is ClickStack (D2573) and the existing `doctor`; no alert routing (Ledger `eventual`). | One source per customer-visible metric (D704); a list that names its source can be checked against it. | **0279** |
| **D2573** | D1964: *"A platform compose project (`apg-telemetry`) with ClickHouse, the HyperDX UI and an OTel gateway, every image pinned by digest"*. | p7: ClickStack's open-source distribution is ClickHouse, HyperDX, MongoDB and **its own collector, supervised over OpAMP by HyperDX** — the UI pushes the collector's configuration, and ingestion takes a key minted in the UI. The projects already pin `otel/opentelemetry-collector-contrib:0.159.0` by digest (`versions.env:16`). | **The gateway is the projects' pinned contrib collector** with its `clickhouse` exporter (`create_schema: true`, database `otel`), **not ClickStack's collector**: no UI rewrites the pipeline, no ingestion key exists. ClickHouse, HyperDX and MongoDB are pinned by digest from the ClickStack release Run 1 reads (the release's `docker-compose.yml` and `.env` at its newest tag; each image `docker buildx imagetools inspect`ed for its index digest, recorded in `versions.env` as `CLICKHOUSE_IMAGE`, `HYPERDX_IMAGE`, `MONGO_IMAGE`). **Rig 42a decides it**: the contrib gateway writes `otel.otel_logs`; HyperDX, given a ClickHouse connection and a log source on that table, lists the rows. **Control**: the same record sent through ClickStack's own collector lands in the same table shape. **If HyperDX cannot read the contrib exporter's table**, §9's stop (the choice is the operator's). | A pipeline whose configuration is owned by the UI it feeds is an authority nobody reviewed; one collector image pinned twice is one image to keep. | **0277** |
| **D2574** | D1964: *"Each project's collector gains a logs pipeline and an OTLP exporter to the gateway on a dedicated network"*; stage plan *Must not*: *"export telemetry off the host"*; the Stage 4 invariant: *"observability may lose optional detail under pressure; it may not destabilise the PostgreSQL workloads it exists to observe"*. | The collector joins only `apg-<key>-edge` (`compose.yaml:1294-1295`); a collector's exporter that cannot reach its target retries and queues (contrib's `sending_queue`, `retry_on_failure`) — **unbounded behaviour not measured**. An external network a compose file names must exist before `compose up` or the project does not start. | **Three networks, none with a published port or a router label**: `apg-telemetry-ingest` (**internal**; the gateway and every project's `metrics` collector — only collectors and the gateway are members), `apg-telemetry` (**internal**; gateway, ClickHouse, HyperDX, MongoDB), `apg-telemetry-ui` (a plain bridge with **HyperDX alone**, the host's route for the SSH forward, D2579). **The project's `metrics` service joins `apg-telemetry-ingest` as an external network**, ensured by `bin/project-runtime.sh` before `up` AND by `bin/telemetry.sh up` (D2563's ensure: create `--internal --label apg.network=telemetry-ingest`; *"already exists"* → re-read labels and `Internal`; equal → 0). **Each collector stamps `project`** with a `resource` processor, `action: upsert`, value = the key the render knows — the platform's value replaces any the payload carried. **Bounded export**: `otlphttp` to `http://gateway:4318`, `sending_queue: {queue_size: 1000}`, `retry_on_failure: {max_elapsed_time: 60s}`, the existing `memory_limiter` first in the logs pipeline. **Rig 42a case 7** (before anything is built on it): the gateway stopped, a burst at 10× E0's line rate into a project-shaped collector for 10 minutes → the collector's memory stays under its 192 MiB limit, its metrics pipeline still serves the scrape (**control**: the same scrape with the gateway up), and the sender (a stand-in service) sees no added latency. **If the collector exceeds its limit or the scrape stops**, §9's stop. | A project's telemetry is optional detail; its database and routes are not. Stamping from the render is the platform naming the project, never the payload (threat item 9). | **0277** |
| **D2575** | D1964: *"each collector's logs pipeline (D1918's lines)"*; ADR 0249 `:112,116`: the lines *"become ClickStack's log input"*. | D1918's lines go to stdout only (`log_setup.py:31-48`); the collector has no logs pipeline and receives OTLP only from `mcp`'s metrics (`compose.yaml:2004`). Nothing reads `docker logs` for the product, and the edge's `apg-diag logs` allowlist covers none of auth, storage or mcp (D380). | **The services export the same records over OTLP to their own project's collector**: `log_setup.configure` adds, when `APG_OTLP_LOGS_ENDPOINT` is set, an OpenTelemetry `LoggingHandler` on the same two loggers with a `BatchLogRecordProcessor(max_queue_size=2048, max_export_batch_size=256, export_timeout_millis=2000)` — **the record's body is the formatted message only** (`%(message)s`), **`exc_info` and `stack_info` dropped** before export (a traceback is not a line), no attribute but the logger's name and the level. `compose.yaml` sets `APG_OTLP_LOGS_ENDPOINT: http://metrics:4318/v1/logs` on `auth`, `mcp` and `storage` (each a mode of the auth-api image; Run 5 greps every service that runs `create_app`). **Run 5 reads the image's installed packages first** (`docker run --rm --entrypoint pip <auth image> list`) — if the OpenTelemetry logs SDK and the HTTP exporter are not installed, adding them is a dependency change recorded with its versions. **Nothing else is collected**: no `docker logs`, no PostgreSQL log, no Traefik access log. The canary: `test_request_log.py`'s planted values are absent from the exported record too (a test with an in-memory exporter); **the export never blocks a request** (rig 42a measured it; a test with an exporter that sleeps asserts the handler returns at once). | The lines already pass a canary; exporting the same records keeps one definition of what a line may hold, and the dropped traceback is the one place a value could hide. | **0277**, 0249 amended |
| **D2576** | D1964: *"`mem_limit`/`pids_limit`/`cpus` from day one (ADR 0244's rule), ClickHouse TTLs as the retention"*; stage plan *Measures*: *"ClickStack's memory and CPU under the control load"*. | ADR 0244's rule derives a limit from a measured peak (`:56-60`); no peak exists. ClickHouse's own memory ceiling is `max_server_memory_usage` (a server setting); the contrib exporter's tables carry a TTL from its `ttl` setting. | **Every `apg-telemetry` service is bounded by ADR 0244's rule from rig 42a's peaks under the 10× load**, then **checked on the host by Sheet E1**: the rig compose run by root on the upgraded host for 30 minutes under the same load, `docker stats` every 60 s, `free -m` at start and end (**stop E1 if available falls below 2,000 MiB**), torn down (`down -v`) and read gone. ClickHouse: `max_server_memory_usage` = 80% of its `mem_limit` (a mounted `config.d` file); the logs table's TTL **7 days** (`ttl: 168h`, `ttl_only_drop_parts`). MongoDB: `--wiredTigerCacheSizeGB` 0.25. **Disk**: ClickHouse's and MongoDB's volumes are bounded by the TTL and HyperDX's few documents; E1 and the trip read `du -sh` of both volumes. **No number is written here that E1 did not read.** | The limits follow the rule every other service follows; the host check is what the stage asked for. | **0277**, 0244 amended |
| **D2577** | D1964: *"Its memory is charged by admission like a project."* | Admission charges projects' `unreclaimable_mb` and branches (`capacity_reading.py:181-182`, `:291-323`); the edge lives inside `reserve_memory_mb`; ADR 0244: *"charges `unreclaimable_mb`, never a cap"*. A telemetry store's memory grows with load, so it has no *unreclaimable* figure to declare. | **The plane is charged at its ceilings**: `bin/telemetry.sh up` writes `/etc/agentic-postgres/telemetry/state.json` (0644; `charge_mb` = the sum of the four `mem_limit`s read from the rendered compose, `images`, `started_at`) **only after admission admits it** (`capacity_reading.decide` with the plane as the candidate; `exit 12` when it does not fit, D1954's code); `capacity_probe.read` adds `committed["apg-telemetry"] = charge_mb` when the file exists; `doctor capacity` shows it as its own row; `telemetry.sh down` removes the file. **ADR 0221 amended**: a platform component whose use follows load is charged at its ceiling; a project still at its `unreclaimable_mb`. Tests: `decide` refuses a project that fits without the charge and not with it; **control**: no state file, the same project admitted. | Charging a cap is wrong for a project (D767) and right for a store whose peak is its load's; the charge is what keeps ClickStack from being admitted twice. | **0277**, 0221 amended |
| **D2578** | CLAUDE.md §6: *"No secret value in source, Compose interpolation, process arguments, image layers or logs."* | ClickHouse, HyperDX and MongoDB each read configuration from environment variables in ClickStack's compose (p7); HyperDX needs a session secret (`EXPRESS_SESSION_SECRET`, HyperDX's DEPLOY.md). Prometheus, the per-project store, has no credential: its network is its boundary (ADR 0223). | **No password for ClickHouse or MongoDB**: each listens only on `apg-telemetry` (internal), ClickHouse's two users (`gateway`: `INSERT` on `otel`; `reader`: `SELECT` on `otel`) admitted by `<networks><ip>` = that network's subnet (rig 42a reads it and measures a container on `apg-telemetry-ingest` refused as `reader`). **HyperDX's session secret** is generated by `telemetry.sh up` once into `/etc/agentic-postgres/telemetry/hyperdx-session` (0600 root), bind-mounted read-only, and exported by a two-line entrypoint wrapper (`/bin/sh -c 'EXPRESS_SESSION_SECRET="$(cat /run/apg/hyperdx-session)" exec <the image's entrypoint>'` — the entrypoint read from `docker image inspect` in Run 1) — **never in the compose file, never in `docker inspect`'s `Env`** (a host proof reads `Env` for it). **Rig 42a reads every variable HyperDX requires** from its image and documentation; one that must carry a secret and cannot be read from a file is §9's stop. | The store is reachable by two containers; a password would be a secret with nothing to keep out. The one real secret takes the path every other one takes. | **0277** |
| **D2579** | D1964: *"no route and no published port: the operator reaches HyperDX by the SSH forward (ADR 0043's shape)."* | p5: `AllowTcpForwarding local` for every account in the file — `op` AND `apg-agent`. A container port is reachable from the host's network namespace on a non-internal bridge's address. | **The operator, 2026-10-17: HyperDX with its own login.** MongoDB holds HyperDX's state; **the operator creates the one user at Sheet T2** over `ssh -L 18080:<HyperDX's address on apg-telemetry-ui>:8080 op@15.204.231.45` (the address printed by `sudo bin/telemetry.sh status`), password into the operator's password manager, never into the conversation. HyperDX's ClickHouse connection and its log source are created by the operator in the UI on the same sheet, typed from the sheet (host `clickhouse`, port 8123, user `reader`, no password, table `otel.otel_logs`) — **no `DEFAULT_CONNECTIONS` environment** (D2578). `apg-agent` could open the same forward (the file is global); **it meets the login** — recorded in §10, no sshd change. **The listeners stay 22, 80, 443, 5432** (a host proof, D2586). | A UI behind a forward AND a login is two locks; the operator chose the second. | **0277** |
| **D2580** | D1964: the plane is a platform compose project. | The edge is the precedent: `infra/edge/compose.yaml`, `bin/edge.sh`, `systemd/agentic-postgres-edge.service` through `libexec/agentic-postgres-edge`, installed by `provision-host.sh` (`:834-840`) and enabled by the operator (`operator-guide.md:173-180`). `apg-diag containers` lists projects and branches (`bin/apg-diag.sh`; D2556). | **`infra/telemetry/compose.yaml`** (`name: apg-telemetry`; services `clickhouse`, `gateway`, `hyperdx`, `mongo`), **`bin/telemetry.sh`** (`up`, `down`, `status`; root; refuses without `--host`; reads the images from `versions.env`; the gateway's config rendered by a new `rendering.build_gateway_config()`), **`systemd/agentic-postgres-telemetry.service`** (`After=docker.service`, `Wants=` nothing of a project's; `ExecStart … telemetry up`, `ExecStop … telemetry down`) through **`libexec/agentic-postgres-telemetry`** (the edge launcher's shape), enabled by the operator at Sheet T1. **No project unit orders after it** (a project never waits for telemetry, D2574). `apg-diag containers` gains a `-- apg-telemetry (platform)` section (Sheet PV reinstalls it). `test_cli_contract.py` registers `telemetry.sh` (`SHELL_COMMANDS`, `COMMANDS_WITH_VERBS`). | One more plane, made the way the one before it was. | **0277** |
| **D2581** | Scope closure §34: *"an instrument that writes its probe samples as it takes them"* (D2557). | `~/s41/run8/s41-lifecycle.py` keeps probe samples in memory and writes them at `stop_probes` (D2557); the Session 41 notifications proof counted *"one per finished operation"* against the eleven types and failed on the failed export's notification — the product right. | **`s42-lifecycle.py`** (Run 8, derived from `s41-lifecycle.py` by an anchored script, every anchor counted): **every probe sample appended as one JSON line to `<record>.samples.jsonl` and flushed (`os.fsync`) as it is taken**; the record names the file and its sha256 at each window's end; `--resume-at-export` (Session 41's) re-reads the samples file and loses nothing taken. **The proofs read windows from the samples file** (the record's path, checked against its sha256). **The notifications proof counts the record's finished operations** — every operation the record names, a failed one included — one notification each, by kind (`operation_succeeded` / `operation_failed`) matching the operation's outcome. **Query Insights is read inside the lifecycle** (D2569): while `slot6-prod` is awake, a known workload as `customer_app` over its direct name — 200 × `SELECT count(*) FROM pg_class WHERE relname = 'APG-INSIGHT-CANARY-<uuid>'` — then the instrument awaits two usage passes and records `GET …/insights` and `GET …/monitoring` whole; **no new environment gate or gate flag** (the lifecycle record carries it). New claims (§2): `lifecycle_fourth_trial_live`, `idle_sleep_retrial_live`, `notifications_retrial_live`, `insights_live`. **The older fixtures widen to read Session 42's record** (D2442's pattern; each still asserts every member it asserted): `RECORD_SESSIONS` → `{38, 39, 40, 41, 42}`, `record39` → `(39, 40, 41, 42)`, `record40` → `(40, 41, 42)`, Session 41's `record41` → `(41, 42)` with `project_key` a slot key that is not `slot3-prod` (`slot.SLOT_KEY`). | The lesson of D2557 applied where it was learned; a proof that counts what the record says happened cannot fail on the product being right. | 0261 |
| **D2582** | D2557: *"SL1's `/storage/APG_R2_SECRET_ACCESS_KEY` held the ACCESS KEY ID"*; CLAUDE.md §2: *"CHECK THE SECRET FIELD IS THE SECRET"*. | Session 41 read the mis-entry after the export failed, with `s41-r2shape.py` (yes/no only). Nothing checks the pair's shape before a slot is materialized. | **Sheet SL1b** (between SL1 and SL2): the agent hands `s42-r2shape.py` (derived from `~/s41/run11/`'s, read whole first) for the operator to run as root against `slot6-prod`'s Infisical project; it prints **only** `access key id: 32 hex yes/no`, `secret: 64 hex yes/no`, `the two differ: yes/no` for `/storage` and `/backup` — never a value, never a length beyond those. Any `no` → the operator re-enters the pair before SL2. | The cheapest check against the one input that cost Session 41 four windows. | — |
| **D2583** | ADR 0261: a `trial` row names only claims introduced in `CURRENT_SESSION`. | Ten rows are `planned` target 42: `projects_self_service`, `project_deletion`, `export`, `region`, `compute_profiles`, `sleep`, `idle_sleep`, `notifications`, `query_insights`, `monitoring`. `ACCEPTED_TYPES` = `credential.rotate` + four branch types (`services/auth-api/app/operations.py`). | **The bump (Run 9) moves the ten to `trial`**, each `evidence` naming only Session 42's claims: the six managed-project rows and `sleep` → `lifecycle_fourth_trial_live`; `idle_sleep` → `idle_sleep_retrial_live` (and it follows `sleep`'s verdict at the close, D2560); `notifications` → `notifications_retrial_live`; `query_insights` → `insights_sampler`, `insights_api`, `insights_live`, `pgss_live`; `monitoring` → `monitoring_signals`, `telemetry_live`. **`ACCEPTED_TYPES` becomes the eleven** (`CTL-OPS-001`'s `test_exactly_the_eleven_executed_types_are_accepted` — grep for the name the tree uses now and follow D2560's precedent). The two new rows' customer text: `query_insights` *"Your statements' calls and time over a window, normalised; no recommendations (being verified)."*; `monitoring` *"A short list of readings, each naming where it comes from (being verified)."* The section header `reality-ledger.yaml:649` re-labelled `(Session 42)`. **At the close**: `beta` iff every named claim `passed` in `evidence/session-42.json`, else `planned` target 43; a row that acts through another follows it (D2560). | The rule of three sessions, a fourth time. | 0261, 0247 |
| **D2584** | ADR 0162: what a bump permits. | 1.19.0 priced `minor` with `--also api_operation_added` (Session 41 Run 10). A changed `postgres` command and a new platform plane have never been priced; `compatibility.py:89-105` holds the declarations. | **1.20.0, predicted minor**: no project-manifest, outputs, host or lock schema moves; no released migration; the control set's `0009`; routes added. **Run 9 reads `src/agentic_postgres/compatibility.py` for a declaration that a changed service definition or a restart needs** and Sheet R1 passes exactly what the offline `upgrade plan` asks for; a `major` is §9's stop. `__init__.py` gains a Session 42 paragraph in Session 41's format (`:1146-1205`). | The release adds a plane beside the projects and restarts each database; it changes no deployed document. | 0162 |
| **D2585** | D1978: *"First run: the `THR-*` rows"*; threat item 9 (`threat-model.md:271-277`). | Item 9 is prose; it owes *"every series and line names its project from the platform, not from the payload; ClickStack bounded … and charged by admission."* | **Run 1 rewrites item 9 with the negative test each owes BY NODE ID (§2) and adds two items**: *a statement's text carries a literal or a password into an insight* (INS-READ-001's canary) and *the telemetry UI is reached by someone who is not the operator* (INS-HOST-001's listener read; the login). Run 9 moves them into the table as **`THR-INS-POISON`** (a payload names another project — the collector's upsert, INS-LOGS-001; a customer's text in a line — none, ADR 0249's canary), **`THR-INS-EXHAUST`** (the plane bounded and charged, INS-PLANE-001, INS-ADMIT-001; a project's export bounded, rig 42a case 7 as a standing test with a fake gateway), **`THR-INS-LEAK`** (insights of a foreign project answer like a missing one; `PUBLIC` revoked; `track_utility` off — INS-API-001, INS-PGSS-001, INS-READ-001), **`THR-INS-UI`** (no published port; the listeners unchanged; HyperDX's login — INS-HOST-001). **No `|` inside a cell** (the parser drops the row silently). | Rows before code. | — |
| **D2586** | Stage plan §7: *"`every_service_bounded_live` re-run with ClickStack"*. | `test_no_running_compose_container_is_unbounded` (`test_session35_governance.py:653`) reads every running Compose container on the host; `test_the_edge_plane_is_bounded` (`test_process_limits.py:188`) is the edge's offline twin. | **The live proof needs no change** — it re-runs on the sweep with `apg-telemetry` running and must pass. **Offline**: `test_process_limits.py::test_the_telemetry_plane_is_bounded` (every service in `infra/telemetry/compose.yaml` carries `mem_limit`, `pids_limit`, `cpus`; images by digest; no `ports`; no `traefik.*` label). **Host** (`tests/deployment/test_session42_telemetry_host.py`): the plane's containers bounded and healthy; `apg-diag listeners`-equivalent (`ss -ltnH`) shows 22, 80, 443, 5432 only; HyperDX's `Env` holds no session secret; the state file's `charge_mb` equals the compose's sum; a line sent to beta-dev's collector with `project=alpha-dev` in its resource arrives in `otel.otel_logs` as beta-dev's; every project's `postgres` reads `shared_preload_libraries = pg_stat_statements`, the extension in `extensions`, `customer_app` refused the view. | The live claim already reads the right set; the new plane needs its offline twin and its own host reads. | — |
| **D2587** | D2554: *"re-run the gates in the foreground, in shards"*. | The workstation cannot hold a whole gate in the background; Session 41's shard scripts are in WSL `~/s41/run9/` and `~/s41/run12/`. | **Every gate this session runs is run in shards by Session 41's method**: Run 9 derives `~/s42/run9/gate01-*.sh` and `gate42-*.sh` from `~/s41/run9/` (the shard lists re-packed by measured per-file time from the newest JUnit), each shard under `timeout 570`, the JUnit merged into the gate's one file, the total checked against the selection's collected count, the gate's evidence step run over it. | The operator's accepted method. | — |
| **D2588** | `bin/session-42-check.sh` derived from 41's by diff (D1482, D1488). | Session 41's gate added no flag. Session 42's live modules read the existing `APG_LIFECYCLE_RECORD_FILE`, `APG_CONTROL_OUTPUTS`, `APG_CONTROL_PROBE_FILE`, `APG_LIVE_HOST`, `APG_LIVE_SLOT_OUTPUTS`, `APG_HOST_MANIFEST` (roster `tests/conftest.py:86-225`). | **No flag, no environment gate added** (the samples file is named by the record, D2581). `bin/session-42-check.sh` from 41's by diff — `readonly SESSION=42`, the header and usage rewritten whole, Session 42's live modules in the host and external selections — `tests/contract/test_session_forty_two_gate_modes.py` from 41's (`SESSION = 42`, `SESSION_PREVIOUS_NUMBER = 41`, the claims table). If a run finds it needs a gate, it is a row and a roster line in that run. | — | — |
| **D2589** | Session 41 Sheet P1 for `slot5-prod`. | A new slot needs three grey A records, two R2 buckets with tokens, a B2 mirror bucket with a key, an Infisical project (bootstrap); the agent created `slot5-prod`'s R2 buckets through the Cloudflare API at the operator's request (D2555). `s41-dns.sh` runs after H1 (D2555). | **Sheet P1 for `slot6-prod`**: `A slot6.agenticpostgresql.com`, `A pool.slot6…`, `A direct.slot6…` → `15.204.231.45`, DNS only, no AAAA; R2 `apg-slot6-prod` and `apg-slot6-prod-backup` (EEUR, Standard; the agent creates them through the Cloudflare API **only if the operator asks on the day**, recorded) with Object R&W tokens; B2 `apg-slot6-prod-backup-mirror` with a key. **No wildcard** (no branch of it). Order (D2555): H1 → `s42-dns.sh slot6-prod` → SL1 → SL1b → SL2 → SL3. | One slot, one lifecycle. | 0257 |
| **D2590** | CLAUDE.md §2: *"M7's X1/X2 (retire it) ALLOWED since 2026-10-12 ~21:30Z and NOT YET RUN"*. | The old host's three projects stopped (the way back). | **Not this plan's**: M7's sheets stay in `docs/plans/session-38-migration-plan.md` (`:797-832`) and may run on any day outside this session's three sittings; this plan's sheets never name the old host. | Two trips' sheets interleaved is D1510's failure in waiting. | — |
| **D2591** | Stage plan §5 *Session 43* (`:855-896` before this amendment): *"The console (D1969): static files under `services/console/`, served by the control project's router, calling `/api/v1` only … the pricing page with Premium unavailable and 'Notify me'"* — and nothing a stranger can find. | Measured 2026-10-18: `https://agenticpostgresql.com` does not answer; `www.` and `control.…/` answer 404; the customer documentation is Markdown in the (public) repository beside ~60 operator, audit and session documents (`docs/managed-projects.md`, `docs/control-plane.md`); an invitation is a FILE (`bin/login.sh accept --endpoint URL --invitation-file FILE --username NAME`, `docs/control-plane.md:130`); `apg` is the repository's `bin/` scripts — no installable package (README's setup clones and runs `uv`/`pip -r requirements-dev.txt`, `:242-250`); TOTP is enrolled with a QR drawn in a terminal. Every customer action already has a `/v1` route (the CLI calls nothing else). | **The operator, 2026-10-18: Session 43 is web-first** — (1) a public site on Cloudflare Pages, off the production host: landing, hosted customer docs, quickstart, pricing, *request an invitation* (`mailto:`, no form); (2) customer docs separated from the operator's; (3) the invitation as a console link with the token in the URL fragment; (4) accept, password and TOTP (QR in the page) in the browser; (5) the console with every customer page, the target *a stranger with an invitation link reaches a working connection string in the browser, no terminal*; (6) the customer CLI packaged (`uv tool install` / `pip`), optional. **The stage plan's §5 *Session 43* carries it** (*Builds as amended*), with §3's table, the Status block and §7's table moved. | A product nobody can find, read or start without a terminal is a product only its builder can use; the API already holds every step, so the browser path is surface, not new authority. | — |
| **D2592** | D1969: the SQL tab cut — *"the SQL tab is replaced by the Connect page's direct URL and a `psql` snippet, and the Ledger says 'SQL editor: not available, by decision (ADR 0246)'"*. | ADR 0246 (`docs/decisions/0246-…md:94-99`): *"a product surface runs no SQL … A customer's own client, with the customer's own database credential, may"*; the Ledger's `sql_editor` row (`reality-ledger.yaml:844-857`) is `not_offered`, `target_session: null`, its `eventual` *"A browser SQL editor acting as the person, never a shared credential."* The public Postgres entrypoint with TLS and SNI exists (ADR 0268). | **The operator, 2026-10-18: build the SQL editor in Stage 5, as its own Session 44** — the customer's own client in the browser: the customer's own credential held only in the page, PostgreSQL's protocol over a WebSocket to a relay at the edge that holds no credential and reaches only that project's public names; PostgreSQL's grants, RLS and timeouts decide. ADR 0246's sentence amended by that session's ADR; the `sql_editor` row leaves `not_offered` there. **The Ledger schema's `target_session` maximum (43, `schemas/reality-ledger.schema.json:121-127`) widens to 45** in the first session that targets a row past 43 (D2552's precedent). A SQL editor that runs statements on the platform's side stays cut (§9's stop, amended). | The design the cut was protecting against is the server-side one; the browser-side one is the shape ADR 0246 already permits and the Ledger already names. | 0246 (to be amended by 44) |
| **D2593** | Stage plan §5 *Session 43* (old text): the console AND the support bundle, `apg control status`, the journey, the person's walk, the bump and the Stage 6 report in one session. | With D2591's six points and D2592's editor, one session would carry a public site, a browser onboarding, a console, a packaged CLI, a SQL relay, the journey, the walk and the release. | **The operator, 2026-10-18: split.** Session 43 = the web-first path (D2591); Session 44 = the SQL editor (D2592); **Session 45 = the support bundle, `apg control status` and the node-loss runbook, the executable journey and the person's walk — both starting from the public site and an invitation link — every gate, the release and `docs/stage-6-decision-report.md`.** Stage 5 becomes sessions 36–45; ordering *43 before 44 before 45*. | The walk measures the path a stranger takes, so it comes after that path exists, editor included. | — |
| **D2594** | D2591 point 6: *"Where it is published (PyPI under a name the operator claims, or a wheel on the repository's releases) is the operator's decision in that plan."* | No distribution exists; the customer families live in `bin/cloud.py` beside the operator's commands. The rule *"Never put a GitHub credential on the VPS"* (CLAUDE.md §6). | **The operator, 2026-10-18: PyPI, published from CI.** A distribution holding **only the customer families** (no server code, no operator command), its version the product's `template_version`, installed by `uv tool install <name>` or `pipx install <name>`; **published by a GitHub Actions job using PyPI trusted publishing** (short-lived OIDC credentials — no PyPI token stored anywhere, nothing on the VPS), only from a tagged commit whose CI passed. **The operator claims the name on PyPI before Session 43 runs** (first come, first served; candidates `agentic-postgres`, `agentic-postgres-cli`); Session 43's plan reads which was claimed. | The install a developer expects, an upgrade that works, and a publish path that holds no secret. | ADR (Session 43) |
| **D2595** | D2591 point 4: *"How the console holds its session (memory, or an `HttpOnly`, `SameSite=Strict` cookie with a CSRF rule) is that plan's decision and an ADR."* | The CLI holds a bearer token from `/v1/sessions`; the console does not exist. Session 44's editor will hold a customer's database password in a page (D2592). | **The operator, 2026-10-18: a cookie on the API's own origin.** The console is served from **`control.agenticpostgresql.com`**, the origin of `/v1` (no CORS, no cross-site cookie); the session is an **`HttpOnly`, `Secure`, `SameSite=Strict` cookie** set by the session route for the console, its lifetime the existing session's, login still requiring the TOTP code; **every write also checks `Origin`** (or a header only the console's own pages send) as the CSRF rule. **Not** page memory (a re-login and a TOTP code on every refresh), **not** `localStorage` (readable by any script on the page). The CLI and API keys keep bearer tokens, unchanged. | No script on the page can read the session, which matters most on the page that will hold a database password. | ADR (Session 43) |
| **D2596** | D2591, *Must not (added)*: *"a third-party script or tracker on the site or the console without an operator decision recorded."* | Neither the site nor the console exists. | **The operator, 2026-10-18.** **The console: no third-party script, ever** — no analytics, widget or CDN library; every asset served from our own files under a strict Content-Security-Policy (a test reads the CSP and every `<script src>`). **The public site: no tracker**; traffic read from Cloudflare Pages' own numbers, which need nothing on the page; **Cloudflare Web Analytics** (cookieless, built into Pages) only if the operator later asks for more; fonts and images self-hosted, no external CDN. No Google Analytics, no ad tracker, no cookie banner needed. | The page that holds a customer's password runs only our code; a product sold on care with data does not hand its visitors to a third party. | ADR (Session 43) |

**Rows the runs add** (execution order; **next free D2613**):

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D2597** | D2566: *"`REVOKE ALL ON extensions.pg_stat_statements, extensions.pg_stat_statements_info FROM PUBLIC;` and `REVOKE ALL ON FUNCTION extensions.pg_stat_statements_reset(...) FROM PUBLIC;`"* | Rig 42b (18.4, extension 1.12): after revoking the two VIEWS, `customer_app` read **8 rows through `extensions.pg_stat_statements(true)`** and one through `extensions.pg_stat_statements_info()` -- both functions carry no ACL, so `PUBLIC` holds `EXECUTE`. `pg_stat_statements_reset(oid, oid, bigint, boolean)` is already revoked by the extension (`{postgres=X/postgres}`). | **Revoke all four objects**: the two views AND `extensions.pg_stat_statements(boolean)` and `extensions.pg_stat_statements_info()`, plus the reset function (a no-op belt). `check_violations` reads `has_function_privilege('customer_app', 'extensions.pg_stat_statements(boolean)', 'EXECUTE')` false beside the table privilege. Run 3's Docker-backed test reads the function as well as the view. | A view revoked over a function left open is a view revoked in name only. | 0278 |
| **D2598** | D2562: *"the upgrade first, at `601a0ea`, before any code"*; §9: *"offers a plan other than the 12 GB one"* is a stop. | **2026-10-18 ~05:30Z, the OVHcloud manager**: *"An error has occurred retrieving information to upgrade to the new range. Sorry we are out of stock in region US-EAST-VA-2."* -- for the 12 GB plan and for 24 GB alike. U0 had run (05:11-05:13Z: four incremental backups 20-25 s, row counts, the reconciler stopped); U1 could not be confirmed; nothing changed on the host. | **The operator, 2026-10-18: continue the code runs; retry the upgrade periodically; sitting U, E0 and E1 whenever stock returns, before Run 10.** The reconciler, stopped by U0, is the operator's to start again (`sudo systemctl start agentic-postgres-reconciler`). At the retry U0 runs again (its backups and counts must be fresh), then U1-U3, E0, E1 as written. Runs 2-8 do not depend on the host's size; rig 42a's case 5 ran at the plan's fallback rate (100 lines/s) and is re-run at 10x E0's rate if that is higher. **If no stock by Run 10, the trip is re-planned** (the plane and `slot6-prod` at once on 7,746 MiB is the question). | §9's stop, answered by the operator; the order changes, the content does not. | 0221 |
| **D2599** | Sheet U3: *"`sudo systemctl start agentic-postgres-reconciler`"* after the re-declaration. | U0 read `agentic-postgres-reconciler.service` **enabled**: stopped by U0's sheet, it would start by itself at the upgrade's reboot, reading the OLD `host.yaml` (D2411). | **U3's line is `sudo systemctl restart agentic-postgres-reconciler`** (starts it if stopped, re-reads the declaration if the boot started it). | A start that is a no-op on a running unit leaves the old declaration in memory. | -- |
| **D2600** | D2578: HyperDX's session secret *"generated by `telemetry.sh up` once into `/etc/agentic-postgres/telemetry/hyperdx-session` (0600 root), bind-mounted read-only"*. | Rig 42a: the image `hyperdx/hyperdx:2.41.0` runs as **`node`, uid 1000** (`docker image inspect`: `User=node`; `id`: `uid=1000`), entrypoint `["sh","/etc/local/entry.sh"]`. A 0600 root file is unreadable inside it. The rig's wrapper (`EXPRESS_SESSION_SECRET="$(cat /run/apg/hyperdx-session)" exec sh /etc/local/entry.sh`) worked with a uid-1000 0400 file: `docker inspect` `Env` held no secret; the value is only in the processes' environment. | **The file is `0440 root:1000`** (readable by root and by the container's gid only; on the host gid 1000 is the locked `ubuntu` group, no member) -- Run 4 writes it and a host proof reads its mode and owner. | The secret takes the file path every other one takes; the container's user decides who must read it. | 0277 |
| **D2601** | D2578/D2579: HyperDX's environment; *"no export off the host"*. | ClickStack's compose sets `USAGE_STATS_ENABLED: ${USAGE_STATS_ENABLED:-true}` -- **HyperDX phones home by default** -- and D2574 puts HyperDX on `apg-telemetry-ui`, a plain bridge WITH egress. Its own OTel SDK skips itself without an API key (rig: *"OpenTelemetry SDK initialization skipped"*). `TOKEN_ENCRYPTION_KEY` unset only means Slack/OAuth tokens unencrypted -- neither is used. | **`USAGE_STATS_ENABLED: "false"` and `OTEL_SDK_DISABLED: "true"` in `infra/telemetry/compose.yaml`**, guarded by `test_telemetry_plane.py` (both literals present). | A default that sends anything off the host is a default the plane must name and turn off. | 0277 |
| **D2602** | D2579: the operator creates *"the one user"* at Sheet T2 over `ssh -L 18080:...`. | Rig 42a: **HyperDX admits ONE team**: a second `POST /api/register/password` answered `409 {"error":"teamAlreadyExists"}`. Its session cookie is **`Domain=localhost`** (`connect.sid`, `HttpOnly`, `SameSite=Lax`): a client on `127.0.0.1:18080` logs in (303 to `/`) and is still `401` everywhere. | **Sheet T2 opens `http://localhost:18080`** (never `127.0.0.1`) and the operator registers immediately after T1 -- the first registrant owns the plane. Recorded in ADR 0277: until T2, anyone who reaches the forward could register first; the forward needs `op`'s key. | The one-user property is HyperDX's own, and so is the order it imposes. | 0277 |
| **D2603** | D2578: ClickHouse's `gateway` user *"`INSERT` on `otel`"*. | The contrib exporter's `create_schema: true` creates the database and the table. Rig 42a granted `gateway` `CREATE DATABASE`, `CREATE TABLE`, `INSERT`, `SELECT` on `otel.*` and it created `otel.otel_logs` (TTL 7 days, `ttl_only_drop_parts = 1`, `PARTITION BY toDate(Timestamp)`); whether `INSERT` alone fails was **not measured**. `reader` (`SELECT` on `otel.*`, profile `readonly = 2`): refused from `127.0.0.1` (*AUTHENTICATION_FAILED*), a write answered `403`; a container on the ingest network cannot resolve `clickhouse`. | **Run 4 measures `INSERT`-only first**; if `create_schema` needs more, `gateway` keeps exactly what the measurement shows (the rig's four grants are the ceiling), named in ADR 0277. | A grant written from a sentence is a grant nobody measured. | 0277 |
| **D2604** | D2574: *"`otlphttp` to `http://gateway:4318`"*. | contrib 0.159.0 logs at start: *"`otlphttp` alias is deprecated; use `otlp_http` instead"*. | **The rendered collector names the exporter `otlp_http/gateway`**; a test reads the name. | A config that warns today stops loading in a later pin. | -- |
| **D2605** | D2576: ClickHouse bounded by `max_server_memory_usage` and the logs table's TTL. | ClickHouse's default server config keeps its own system log tables (`query_log`, `trace_log`, `metric_log`, `text_log`, `part_log`, ... ) with no TTL of ours -- disk the plane's TTL does not bound -- and sizes `mark_cache_size` at 5 GiB by default. | **The plane's `config.d` file also removes the system log tables and sets `mark_cache_size` 256 MiB, `index_mark_cache_size` 64 MiB, `uncompressed_cache_size` 0** (rig 42a ran so); `test_telemetry_plane.py::test_the_store_has_a_ceiling_and_a_ttl` reads them. | A store bounded in its customer table and unbounded in its own is not bounded. | 0277 |
| **D2606** | D2565: *"A new lint or destructive finding in an APPLIED release or control migration is §9's stop."* | The quote-aware reader (Run 2) changed `statements()` for **27 of 51 templates** and found **seven real `DROP FUNCTION`s the old reader hid** behind a `--` inside a `COMMENT ON ... IS '...'` literal: release `0025` (`app_private.auth_lookup_agent`, `app_private.auth_rotate_agent_secret`; the cut at its line 57), `0028` (`api.agent_audit_begin`; line 112), control `0004` (`app.control_get_operation`, `app.control_get_project`, `app.control_list_operations`, `app.control_list_projects`; line 144). The lint and the published surface: **unchanged** for the release, control and example sets; the example set's findings unchanged. The only reader of the findings is `bin/migrate.py propose` (a project set's proposal); no test re-derives a committed proposal's list. | **The operator, 2026-10-18: proceed.** Nothing is amended (D912); the six committed control proposals keep the lists they recorded (what their reviewer saw); Run 6's `0009` proposal will name the four `0004` drops its predecessors did not. | A finding that was always true and was hidden by the reader is the defect D2544 named, not a new one. | -- |
| **D2607** | Run 2's battery (e): *"`''` escape handling removed -> the guard FAILED on a template that holds `''`"*. | Closing a literal and reopening it at once reads exactly as an escaped quote does, for a reader that only removes comments -- so the mutation could not fail any test (D493, uninformative). | **The scanner has no `''` case** (its docstring says why); battery (e) became *the identifier state removed* (`test_a_comment_after_a_literal_is_dropped` FAILED). | Untestable code is removed, not kept with a mutation that cannot see it. | -- |
| **D2608** | D2577: *"`capacity_probe.read` adds `committed["apg-telemetry"] = charge_mb` when the file exists"*. | `Reading.committed` is read by every caller as PROJECTS (`len(reading.committed)` "project(s)"); Session 40 put the branches' charge in its own member for exactly that reason (`capacity_reading.py`, *"Kept out of `committed` because every reader of that one counts PROJECTS"*), read from `root.parent / "branches"`. | **The tree's precedent**: `Reading.platform` (keyed `apg-telemetry`), summed into `committed_total_mb`, named on both committed lines (`; apg-telemetry (platform) 3520`, `capacity_reading.decide` and `diagnosis`'s doctor line, JSON pairs too), read from `root.parent / "telemetry" / "state.json"` by `telemetry_plane.read_charge`; `exclude_platform=True` is the plane deciding about itself. | A charge that is not a project's does not change what "N project(s)" counts. | 0277 |
| **D2609** | D2573: the three images *"recorded in `versions.env` as `CLICKHOUSE_IMAGE`, `HYPERDX_IMAGE`, `MONGO_IMAGE`"*. | `versions.env` is GENERATED by `bin/lock-versions.sh --update` from `versions.in.yaml`; a plain `--update` re-resolves every image, and **all four moving tags had moved** since the lock of 2026-10-09 (measured 2026-10-18: `pgvector:pg18`, `traefik:v3.7`, `python:3.12-slim`, `node:22-alpine` -- an unmeasured PostgreSQL among them, D238's hazard). `--packages-only` refuses an image absent from the lock. ClickStack's own compose names `clickhouse-server:26.8-alpine` and HyperDX's major `2` -- both moving. | **`lock-versions.sh --update --add-images`**: carries every locked digest byte for byte and resolves only names the lock does not hold. The three images by EXACT tag: `clickhouse-server:26.8.30.8-alpine` (the same index digest rig 42a ran, `2ad32242…`), `hyperdx:2.41.0`, `mongo:5.0.32-focal`. `versions.env` gained exactly three lines; `--check` current. | A new name has no old digest that could lie; resolving it is the one re-resolve that couples nothing. | 0277, 0083 |
| **D2610** | Run 4: *"`rendering.build_gateway_config()` (the gateway's collector config ... rendered into `/etc/agentic-postgres/telemetry/`)"*. | Nothing in the gateway's configuration varies by host or project (receiver ports, the store's service name, database, user, TTL, queue). | **A committed file, `infra/telemetry/gateway.yaml`**, mounted read-only from the model's directory like ClickHouse's `config.d` file; `test_telemetry_plane.py::test_the_gateway_is_the_pinned_collector` reads it. Only the users file is rendered (the subnet is Docker's). | A render of constants is a second place for the same text. | 0277 |
| **D2611** | Run 4: *"`bin/telemetry.sh` (... `compose up -d --wait` ...)"*. | Every model in the tree is invoked through `bin/compose.sh` (the edge's header: *"Calling `docker compose` directly lets inherited environment variables win over --env-file"*), whose allowlist, root gate and `--volumes` refusal are tested. | **`bin/compose.sh --telemetry`**: the model `infra/telemetry/compose.yaml`, the fixed project `apg-telemetry`, the lock as the only env file; container-starting verbs need `--runtime` and root; **`--volumes` refused** (the operator's saved searches and up to 7 days of lines); `--edge` and `--telemetry` together refused. `telemetry.sh` calls it. | One wrapper for every model is one set of refusals. | 0277 |
| **D2612** | -- (found by Run 4's own test). | The first `test_the_plane_is_refused_when_it_does_not_fit` run on this workstation, where `/etc/agentic-postgres` exists 0700 root: `bin/telemetry.py admit` **crashed with exit 1** -- `Path.exists()` raises `PermissionError` (pathlib swallows only not-found errors) -- instead of refusing. | **`telemetry_plane.read_charge` treats an unreadable state file as UNREADABLE** (`decide` refuses on it) and `admit` treats an unreadable `is_file` as not-installed wording only; an unprivileged `admit` now prints `committed undetermined: ... Permission denied` and refuses. | A decision fails closed; a crash is neither outcome (ADR 0195). | 0195 |

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

**One new family, `INS`** (the stage plan's proposal): the regex at
`tests/contract/test_acceptance_registry.py:125` gains `INS`, and the family
comments gain one sentence after the `PLAN|USE` sentence: *Session 42 (ADR
0277-0279) adds `INS` for the telemetry plane, `pg_stat_statements`, Query
Insights and monitoring.* The three repairs go under the families their
existing proofs live in (`DEP`, `LIFE-EXPORT`, `TEN`) — **Run 9 greps the
registry for the next free number in each and uses it** (the ids below are
proposed). **Eighteen requirements, eighteen claims, all `target_session: 42`,
all P0 — twelve offline, two host, four external.** Node ids below are
**proposed; Run 9 writes what the runs actually wrote**, read out of the tree
with `pytest --collect-only -q` (D1236, D2129). Registry entries are committed
by Run 9 with the constant (D690), under **`# Session 42 (ADR 0277-0279)`**.

| Requirement | What it states | Offline node ids (proposed) | Live half |
|---|---|---|---|
| `DEP-ATTACH-001` | An attach, reconcile or detach that loses a race to another unit reads the network again and succeeds when the wanted state holds; any other failure exits 9; every connect and disconnect goes through the two helpers | `tests/contract/test_edge_network_race.py::test_an_attach_lost_to_another_unit_succeeds`, `::test_a_reconcile_lost_to_another_unit_succeeds`, `::test_a_detach_lost_to_another_unit_succeeds`, `::test_any_other_failure_exits_nine`, `::test_every_connect_goes_through_the_helper` | — (`edge_attach_race`) |
| `LIFE-EXPORT-002` | A failed upload's refusal carries the child's provider line, and never a line holding a URL or a signature | `tests/contract/test_reconciler_dispatch.py::test_the_upload_refusal_names_the_providers_code`, `::test_an_upload_line_with_a_url_is_not_carried` | — (`export_reason`) |
| `TEN-READ-001` | The SQL reader keeps a `--` inside a literal; every template the product reads ends its scan outside a literal | `tests/contract/test_sql_reader_quotes.py::test_a_dash_dash_inside_a_literal_is_kept`, `::test_a_comment_after_a_literal_is_dropped`, `::test_every_template_ends_its_scan_outside_a_literal` | — (`sql_reader_quotes`) |
| `INS-PGSS-001` | Every project's database and every branch load `pg_stat_statements` with `track=top`, `track_utility=off`; the bootstrap creates it in `extensions` and revokes it from `PUBLIC`; `check_violations` reads all three | `tests/contract/test_pg_stat_statements.py::test_the_database_command_loads_the_extension`, `::test_a_branch_loads_it_too`, `::test_the_bootstrap_creates_and_revokes_it`, `::test_the_bootstrap_check_reads_the_preload_and_the_revocation` | — (`pgss_loaded`) |
| `INS-READ-001` | The insights reading keeps only the customer-facing roles' statements, normalised; a literal, a `DO` block and a password never appear (a real server) | `tests/contract/test_insights_reading.py::test_a_literal_is_normalised_away`, `::test_a_utility_statement_is_not_recorded`, `::test_a_platform_roles_statement_is_absent`, `::test_the_text_is_cut_at_two_thousand` | — (`insights_sampler`) |
| `INS-API-001` | The insights document: increases over the window with resets read; samples expected vs present; no finding, recommendation, confidence or severity; the tuning pointer; an empty window `could_not_determine`; a foreign and a missing project answer alike; only `control_record_insights` writes, granted to nobody; 7 days kept | `tests/contract/test_control_insights.py::test_a_reset_is_read_not_subtracted`, `::test_no_member_advises`, `::test_an_empty_window_is_not_an_empty_list`, `::test_a_foreign_and_a_missing_project_answer_alike`, `::test_no_role_but_the_reconciler_writes_a_sample`, `::test_samples_older_than_seven_days_are_removed_by_the_writer` | — (`insights_api`) |
| `USE-DBTIME-001` | Usage gains DB time as a sum of increases over the customer-facing roles; unread named; the writer's body is 0008's plus two keys | `tests/contract/test_control_usage.py::test_db_time_is_a_sum_of_increases`, `::test_db_time_unread_is_named`, `::test_the_usage_writer_is_0008s_plus_two_keys` | — (`usage_db_time`) |
| `INS-CLI-001` | `apg insights show` and `apg monitoring show` are customer commands into `/v1`; `telemetry.sh` is the operator's | `tests/contract/test_control_cli.py::test_insights_and_monitoring_dispatch_to_the_customer_cli`, `tests/contract/test_cli_contract.py::test_telemetry_is_a_root_command` | — (`insights_cli`) |
| `INS-SIGNAL-001` | Every monitoring signal names a source column that exists; no two read one column; the route reads only those tables | `tests/contract/test_signals.py::test_every_signal_names_a_source_that_exists`, `::test_no_two_signals_read_one_column`, `::test_the_monitoring_function_reads_only_the_named_tables` | — (`monitoring_signals`) |
| `INS-PLANE-001` | The telemetry plane: images by digest, every service bounded, no published port, no router label, internal networks but the UI's, the gateway the projects' pinned collector, ClickHouse's ceiling and TTL set, no secret in the compose file | `tests/contract/test_process_limits.py::test_the_telemetry_plane_is_bounded`, `tests/contract/test_telemetry_plane.py::test_no_port_and_no_router`, `::test_the_gateway_is_the_pinned_collector`, `::test_the_store_has_a_ceiling_and_a_ttl`, `::test_no_secret_in_the_compose_file` | — (`telemetry_plane`) |
| `INS-ADMIT-001` | The plane is admitted before it starts and charged at its ceilings; a project that fits without the charge is refused with it | `tests/contract/test_telemetry_admission.py::test_the_plane_is_charged_at_its_ceilings`, `::test_a_project_is_refused_with_the_charge`, `::test_the_plane_is_refused_when_it_does_not_fit` | — (`telemetry_admission`) |
| `INS-LOGS-001` | Each collector's logs pipeline stamps `project` over the payload's and exports through a bounded queue; the ingest network is ensured by the project and the plane alike; the services export D1918's lines with the message only, no traceback, never blocking | `tests/contract/test_metrics_surface.py::test_the_logs_pipeline_stamps_the_project`, `::test_the_export_queue_is_bounded`, `tests/contract/test_request_log.py::test_the_exported_record_is_the_line_and_nothing_else`, `::test_a_slow_exporter_does_not_block_a_request`, `tests/contract/test_telemetry_plane.py::test_the_ingest_network_is_ensured_with_a_reread` | — (`telemetry_logs`) |
| `INS-HOST-001` | On the host: the plane running, bounded and charged; the listeners 22, 80, 443, 5432 only; HyperDX's environment holds no secret; a line sent as another project arrives as its own | — | `tests/deployment/test_session42_telemetry_host.py::test_the_plane_is_bounded_and_charged`, `::test_the_listeners_did_not_change`, `::test_the_ui_holds_no_secret_in_its_environment`, `::test_a_forged_project_is_stamped_over` (host `telemetry_live`) |
| `INS-HOST-002` | On the host: every project's database loads the extension, holds it in `extensions`, and refuses it to `customer_app` | — | `tests/deployment/test_session42_telemetry_host.py::test_every_database_loads_the_extension`, `::test_the_customer_role_cannot_read_it` (host `pgss_live`) |
| `LIFE-LIVE-006` | Session 42's lifecycle on `slot6-prod` at the deployed commit, in a new organisation: every accepted type ran, the resizes decided by their reading, the export holds `app`, `api`, `public`, the slot's own route AND pooled name probed through every window from the samples file, a second creation after the deletion refused `capacity_exhausted {no_slot}` with no row | — | `tests/external/test_session42_reearning.py::test_every_accepted_type_ran_on_the_slot`, `::test_the_resizes_followed_the_admission_reading`, `::test_the_export_holds_the_three_customer_schemas`, `::test_both_routes_were_probed_through_every_window`, `::test_the_second_creation_after_the_deletion_was_refused_by_capacity` (external `lifecycle_fourth_trial_live`) |
| `USE-LIVE-004` | Idle sleep on `slot6-prod`: set to 15, the probes stopped, one `project.sleep` with `origin = idle` attributed to the setter, both names refused while asleep, then woken | — | `tests/external/test_session42_reearning.py::test_the_idle_slot_was_put_to_sleep_by_the_reconciler`, `::test_the_idle_sleep_closed_both_doors` (external `idle_sleep_retrial_live`) |
| `USE-LIVE-005` | The lifecycle organisation's notifications: one per finished operation the record names, its kind matching the outcome; no text holding the export's URL or any result member | — | `tests/external/test_session42_reearning.py::test_every_finished_operation_was_notified_by_its_outcome`, `::test_no_notification_carries_a_secret` (external `notifications_retrial_live`) |
| `INS-LIVE-001` | Through `/v1` with no SSH, on `slot6-prod`: after the known workload, insights hold its normalised statement and not the canary; usage reads DB time; monitoring names every signal's source | — | `tests/external/test_session42_reearning.py::test_the_workload_is_in_the_insights_without_its_literal`, `::test_usage_read_db_time`, `::test_monitoring_named_each_source`, `::test_this_module_uses_no_ssh` (external `insights_live`) |

**Expected counts** — Run 9 counts them from the tuples, never from this prose
(D1628): requirements **377 → 395**, `CLAIMS` **284 → 302**, `OFFLINE_CLAIMS`
**121 → 133**, ADRs **276 → 279**.

**Claims** (`src/agentic_postgres/evidence_claims.py` `CLAIMS`, a block
commented *Session 42 (ADR 0277-0279)*): offline — `edge_attach_race`,
`export_reason`, `sql_reader_quotes`, `pgss_loaded`, `insights_sampler`,
`insights_api`, `usage_db_time`, `insights_cli`, `monitoring_signals`,
`telemetry_plane`, `telemetry_admission`, `telemetry_logs` — **these twelve in
`OFFLINE_CLAIMS`**, with the per-session assertion in
`test_session_forty_two_gate_modes.py` (D1237: assert THESE are in the set,
never its size). Host — `telemetry_live`, `pgss_live`. External —
`lifecycle_fourth_trial_live`, `idle_sleep_retrial_live`,
`notifications_retrial_live`, `insights_live`. `CLAIM_INTRODUCED_IN`
(`tests/contract/test_evidence_claims.py`) gains a row at 42 for each.

**Existing entries that move** (each a passing proof made stricter or widened
to a measured set, never weakened — CLAUDE.md §6, under the ADR named):

- **The lifecycle records** (D2581): the four older fixtures widen to 42; node
  ids unchanged; **Session 41's notifications proof** (`notifications_live`,
  `test_every_finished_operation_was_notified`) is **not** rewritten — it
  re-runs on the Session 42 record as written, and the plan predicts its
  verdict in §7.
- **CTL-OPS-001**: the accepted-types proof back to the eleven at the bump (the
  name the tree uses after Session 41's close; D1119 if renamed).
- **OPN-DISPATCH-001 / BR-DISPATCH-001**: the closed set of control functions
  the reconciler may call (`test_reconciler_dispatch.py:1449-1469`) widens by
  exactly `control_record_insights` (D2569).
- **TEN-SET-002**: `test_the_lint_reads_statements_and_not_comments` stays; the
  new reader must keep it green (D2565).
- **NODE-LIMIT-002**: `test_every_long_running_service_carries_a_memory_limit`
  reads `compose.yaml` only and is unchanged; the plane's twin is new
  (INS-PLANE-001).
- **`THR-*` table rows**: four added in Run 9; none removed.

**New environment gates: none** (D2588).

---

## 4. Irreversible operations

| Operation | Where | What makes it safe |
|---|---|---|
| **The OVHcloud plan upgraded to 12 GB** | Sheet U1 (Run 1) | U0's backups and counts first; the reconciler stopped; whether the plan can be undone, keeps the IPv4 and reboots is READ in the manager and recorded before the click (D2562); a changed IPv4 is §9's stop |
| `memory_mb` (and `disk_gb` if it moved) re-declared in both `host.yaml` copies | Sheet U3 | `s42-hostyaml.py` writes into `/home/op/s42-u3/` and prints diffs; the operator installs; the reserve unchanged; the reconciler restarted (D2411) |
| A throwaway ClickStack on the production host for 30 minutes | Sheet E1 (Run 1) | Bounded by the rig's limits; internal networks only, no port; stopped at 2,000 MiB available; `down -v` and read gone |
| The control set's `0009` frozen into `projects/control/migrations/released.lock.json`, and its proposal committed | Run 6 | `bin/migrate.sh --project project.control.example.yaml freeze-lock`; the proofs apply the release set then the control set's nine as `migration_user` first; `AP900` down; the proposal by `bin/migrate.sh … propose --by NAME` (ADR 0243); no released migration (D912) |
| `CURRENT_SESSION` 41 → 42; `VERSION` 1.19.0 → 1.20.0; ten Ledger rows → `trial`; `ACCEPTED_TYPES` the eleven | Run 9 | All-or-nothing (D690); `README.md:7` and the `--session 41` / `--through-session 41` literals on the documented path moved and counted per file (D678/D1484); ADR 0261 |
| `bin/session-42-check.sh` | Run 9 | Derived from 41's by diff (D1482); header and usage rewritten whole (D1488); no flag added; `SHELL_COMMANDS`; `chmod 755` before `git add` |
| **Every project's database restarted once by the 1.20.0 deploy** (alpha, beta, control-prod, `slot3-prod`) | Sheets R2a–R2d (Run 10) | The reconciler stopped; one project at a time, each window probed (D2567); `slot3-prod`'s customer told in the release note |
| **The telemetry plane installed and its unit enabled; HyperDX's user created** | Sheets T1, T2 (Run 10) | Admitted before it starts (D2577); no port, no route; the user's password in the operator's password manager |
| **Three grey A records for `slot6-prod`; its provider resources** | Sheets P1, SL1 (Run 10) | As for `slot5-prod`; `--plan` before `--apply`; the credential shredded (D2061); SL1b's shape check (D2582) |
| **A new organisation `lifecycle-s42`** | Run 11 | Through `/v1`; kept (organisations are never deleted, D2065) — §10 |
| **`slot6-prod` created, credentialed, worked, slept (by request AND by idleness), woken, resized, exported and deleted; consumed** | Run 11 | Through `/v1` only, after V1 and X0 passed at the same commit (D2448); the tombstone; the repository kept (ADR 0187) |
| `slot6-prod`'s Infisical identity revoked | Sheet SL4 (after the tag) | `slot.sh revoke`; the directory removed by the verb (D2405), read absent |
| The reboot | Sheet B1 | Every unit, the plane and the edge read by `s42-after-reboot.sh` before the sweep (D2140) — D2558 repaired: all back by themselves |
| Tag `1.20.0` on the deployed commit | Run 11 | After the merge exits 5 for `documented_path` only (§7); from the WORKSTATION (D2041) |

---

## 5. Build order, run by run

Each run ends with a `**Done.**` paragraph written by the executor: what was
measured, the numbers, the rows it added, and — for a code run — the CI verdict
by full SHA. The targeted modules run ONCE at the run's close and only a failing
module is re-run. `ruff format && ruff check` before every commit; `chmod 755
bin/*.sh bin/*.py deploy.sh libexec/*` before every `git add` — **and every file
an image executes directly** (D2412); messages from a file with `-F`, ending
with the attribution line the session's system reminder gives. **Grep the plans
for every third party before measuring it.** **A run that renames, adds or
removes a test function runs `test_acceptance_registry` and
`test_evidence_claims`** (D1119); **a run that adds a module under
`src/agentic_postgres/` runs `test_repository_contract`** (D2114); **a run that
adds or removes a `bin/` command runs `test_cli_contract` and `git add`s it
first** (D1014); **a run that adds a `document[...]` read to a `bin/` command
runs `test_container_selectors`** (D1184); **a run that touches a documentation
page runs `test_documentation_index` and `test_session12_documented_path`**;
**every new test module carries `pytestmark` before its first test** (D1240),
and the sweep-selector guard (D1242) AND `test_environment_gates` join the
targeted list of any run that adds a module — **read a model dict with
`.get("APG_…")`, never `x["APG_…"]`** (D2381). **Docker-backed modules reuse
`tests/contract/control_cluster.py`** (`docker rm -fv`, D2098). **Every external
fixture that holds a password, verifier, token or TOTP seed returns
`tests/external/redaction.py`'s `Secret`** (D2420). **Never print a live log's
failure body without filtering it by the secret VALUES** (D2416). **Every
mutation battery** follows CLAUDE.md §1: `PYTHONDONTWRITEBYTECODE=1`, snapshot
to `/tmp` and restore by copy with `cmp`, anchors pre-flighted (a miss fatal),
a control the mutation cannot reach, and *how* each failed (`FAILED` vs
`ERROR`). **Never put `--` inside a SQL string literal in a migration template,
and never backticks in an inline heredoc** (Session 41's two lessons).

### Run 1 — the rigs, sitting U (the OVH upgrade), E0 and E1, the threat list, ADRs 0277–0279

**Documentation plus one sitting. Push, say it is pushed, read NO CI verdict** —
except that, because `docs/threat-model.md`, `docs/decisions/README.md` and
`docs/plans/*.md` are parsed by contract tests, run `test_acceptance_registry`,
the ADR-index test (`grep -rln "decisions/README" tests/contract/`),
`test_documentation_index` and `test_mcp_catalog` once before the push.

**Order on the day: rigs 42a–42c (workstation) → U0 → U1 → U2 → U3 → E0 → E1.**
U before E0/E1 because both read the upgraded host. The rigs may run the day
before.

Rigs live in WSL `~/s42/run1/rig42/` and are copied to the scratchpad. **Each
names its control and is recorded with what it printed.** Each removes what it
made (`docker rm -fv`, `docker network rm`, `docker volume rm`), read back with
`docker ps -a | grep -c rig42` = 0 and `docker volume ls | grep -c rig42` = 0.

1. **Rig 42a — ClickStack bounded, and a project that does not depend on it**
   (D2573–D2579). **Grep the plans first** (`grep -rn "ClickHouse\|HyperDX\|ClickStack" docs/plans/`
   — one Stage 4 refusal, the Stage 5 rows). Read ClickStack's newest release:
   the `hyperdxio/hyperdx` repository's `docker-compose.yml` and `.env` at its
   newest tag (record the tag), and each image's index digest with `docker
   buildx imagetools inspect` (record ClickHouse's, HyperDX's and MongoDB's).
   Read HyperDX's image entrypoint (`docker image inspect --format
   '{{json .Config.Entrypoint}} {{json .Config.Cmd}}'`) and every environment
   variable it requires (its documentation and `docker image inspect
   .Config.Env`). Write `rig42a/compose.yaml` in the shape D2574 names (three
   networks; ClickHouse users by subnet; `max_server_memory_usage`; the gateway =
   `versions.env:16`'s collector with the `clickhouse` exporter, `ttl: 168h`;
   HyperDX's secret through the wrapper; a stand-in project collector built
   from `rendering.build_otel_config`'s output plus the D2574 logs pipeline, with
   192 MiB; a stand-in service printing D1918-shaped lines over OTLP). Cases:
   **(1)** up, healthy, every container's `mem_limit`/`pids_limit`/`cpus` read
   back; **(2)** a record with `project=other` in its resource sent to the
   stand-in collector → the row in `otel.otel_logs` reads the collector's
   project (**control**: a record through the gateway directly, unstamped,
   keeps what it carried — which is why only collectors join the ingest
   network); **(3)** HyperDX: a user created through the UI over a host route to
   its `apg-telemetry-ui` address, a connection (`clickhouse:8123`, `reader`, no
   password) and a log source on `otel.otel_logs` → the rows listed (**control**:
   ClickStack's own collector sending the same record → the same table shape;
   if HyperDX cannot read the contrib table, §9's stop); **(4)** `SHOW CREATE
   TABLE otel.otel_logs` holds the TTL; a container on `apg-telemetry-ingest`
   connecting as `reader` is refused; **(5)** a 30-minute load at 10× E0's line
   rate (or 100 lines/s if E0 has not run — recorded) with `telemetrygen` (pinned
   by digest) → `docker stats` every 30 s; the peaks give each service's limit by
   ADR 0244's rule; ClickHouse not OOM-killed; **(6)** `docker port` empty for
   every container; `docker inspect … Env` of HyperDX holds no secret; **(7)**
   the gateway stopped, the same burst for 10 minutes into the stand-in
   collector → its memory under 192 MiB, its Prometheus exporter still served
   (**control**: the scrape with the gateway up), the stand-in service's request
   time unchanged. **If (7) fails, §9's stop.**
2. **Rig 42b — `pg_stat_statements` on 18.4** (D2566–D2568). The pinned image
   (`versions.env:19`), the project's `mem_limit` and `shm_size` (read from a
   render: `python bin/render-config.py --project project.example.yaml` or the
   `--render-only` path; record which), the five flags. Read: `SHOW` of each
   flag; `\df extensions.pg_stat_statements_reset` (the signature for D2566's
   `REVOKE`); `\dp extensions.pg_stat_statements` (PUBLIC granted by default —
   measured); after the `REVOKE`, `customer_app` → *permission denied*
   (**control**: `postgres` reads it). **The role a PostgREST request records**:
   a PostgREST container (`versions.env`'s pin) logging in as
   `postgrest_authenticator` with `anon` and `authenticated`, one `GET` → the
   `userid` the row carries (**control**: `customer_app` over a direct
   connection records as itself). **The canary**: D2568's three statements; none
   in `query`. **The restart**: a cluster created without the flags, then
   recreated with them (`docker compose up -d` after the command changed) → the
   unavailability from first refused connection to first `SELECT 1`, three
   times; memory: `docker stats` of the backend at rest with and without the
   extension (**control**: two recreates without a change). **The restore
   paths**: a cluster holding the extension started with `postgres -c
   archive_mode=off` only → starts; `SELECT * FROM extensions.pg_stat_statements`
   → the error text recorded; `pg_dump --schema=app --schema=api
   --schema=public` byte-identical to the same dump without the extension.
3. **Rig 42c — the attach race** (D2563). Two containers and one network on
   this workstation's Docker; `docker network connect` the same container
   twice from two shells started together (a `wait`ed pair) → the second's exit
   code and text recorded (**control**: sequentially, the second's text). Then
   the draft `connect_alias` over the same race → exit 0 both. Record Docker's
   exact text for *already exists* and *is not connected*; the tests use them.

**Sheet U0, U1, U2, U3 — the upgrade** (the appendix; D2562). The agent writes
`s42-u0.sh` and `s42-after-upgrade.sh` (from `~/s37/run11/after-reboot.sh`) and
`s42-hostyaml.py` (from `~/s41/run8/s41-hostyaml.py`: `memory_mb` and, only if
given, `disk_gb`; every other byte unchanged; refuses a file whose
`schema_version` is not 4), ships them to `/home/op`, prints their sha256. **U1
is the operator's alone**; the agent waits for *"done"* and the host to answer
`ssh` (polling `ssh -o ConnectTimeout=10 op@15.204.231.45 true` from a script,
at most every 30 s, at most 30 minutes, then asks).

**Sheet E0** (the operator; reads only — `s42-e0.sh` by the agent, shipped,
sha256 printed; writes `/home/op/s42-e0/` 0700): `free -m`; `docker stats
--no-stream --format '{{.Name}} {{.MemUsage}} {{.CPUPerc}}'`; **the line rate,
counts only** — for each project's `auth`, `mcp` and `storage` container, `docker
logs --since 1h <name> 2>&1 | grep -c '^apg\.'` (the count, never a line; D2416);
`sudo bin/doctor.sh capacity --host host.yaml`; `docker system df`. The rate
(lines per second across the four projects) is the control load's unit for
42a(5) and E1.

**Sheet E1 — ClickStack's footprint on the upgraded host** (D2576): the rig
42a compose shipped to `/home/op/rig42/` (the agent prints its sha256), run by
`sudo bash /home/op/s42-e1.sh` — `docker compose -p rig42-telemetry -f
/home/op/rig42/compose.yaml up -d --wait`; `telemetrygen` at 10× E0's rate for
30 minutes into the rig's stand-in collector; every 60 s `docker stats
--no-stream` for the rig's containers and `free -m`; **the script stops the load
and tears down if `free -m`'s available falls below 2,000 MiB**; then `down -v`,
`docker ps -a | grep -c rig42` = 0, `docker volume ls | grep -c rig42` = 0,
`docker network ls | grep -c rig42` = 0. The peaks, the rate and the
neighbours' memory (the four projects' `docker stats` at start and end) are
recorded in the run's `**Done.**`.

**The threat list made specific** (D2585): item 9 rewritten with the negative
test each owes BY NODE ID (§2); two items added (an insight carrying a literal
or a password; the telemetry UI reached by someone not the operator). They stay
list items until Run 9 moves them into the table.

**ADRs** (each indexed in `docs/decisions/README.md`): **0277** the telemetry
plane — ClickStack's four services, the gateway as the pinned collector, the
three networks, the project stamped by the collector, the bounded export and a
project's independence, D1918's lines exported with the message only, bounds
and TTL from the rig, admission at its ceilings, no secret but HyperDX's (a
file), HyperDX's own login behind the SSH forward, the unit (D2573–D2580).
**0278** `pg_stat_statements` and Query Insights — the flags, the revocation,
the roles kept, the canary, the samples in the control database for 7 days,
counters as read, DB time, no recommendation, the tuning pointer, the restart
(D2566–D2571). **0279** monitoring is a list of readings that each name their
source (D2572). **Amended**: ADR 0221 (a platform component charged at its
ceiling, D2577), 0244 (the telemetry plane bounded by its rule, D2576), 0249
(the lines exported over OTLP, D2575), 0275 (DB time metered, D2570).

**The stage plan**: nothing to change. Its Status block already reads *"42
PLANNED"* — written on 2026-10-18 with the operator's amendment of Sessions
43–45 (D2591–D2593). Run 1 reads it and edits nothing in it.

**Done (in part), 2026-10-18.** Rigs in WSL `~/s42/run1/rig42/` (transcripts
beside each; every rig read back `docker ps -a | grep -c rig42` = 0, volumes 0,
networks 0 at its end). **Rig 42c** (Docker 29.5.2): two concurrent `docker
network connect --alias` of one container: the loser exited 1 in **10 of 10**
trials with *"Error response from daemon: endpoint with name rig42c-edge
already exists in network rig42c-net"*; two concurrent disconnects: *"container
<64-hex id> is not connected to network rig42c-net"*, 10 of 10; **control**
(sequential) the same two texts; a missing network: *"network rig42c-missing
not found"*. The draft helpers over the same races: 0/0 in 20 trials; the
draft connect to a missing network: 9. **Rig 42b**: ADR 0278's *Measured*
section is its record (the five flags take; extension 1.12; `PUBLIC` holds
the views AND the functions -- **D2597**; PostgREST records under `anon` /
`authenticated`; the canary 0 rows, control 1; recreate windows 1.13-1.43 s
off→on, control 1.27/1.31 s; memory delta under 3 MiB; restore paths start;
dumps byte-identical). **Rig 42a** (the release `@hyperdx/app@2.41.0`, tag of
2026-10-13; images by index digest: `hyperdx/hyperdx:2.41.0@sha256:00c6d5b7…`
(= `docker.hyperdx.io/hyperdx/hyperdx:2.41.0`), `clickhouse/clickhouse-server:26.8-alpine@sha256:2ad32242…`
(server 26.8.30.8), `mongo:5.0.32-focal@sha256:3b6c281e…`, ClickStack's
collector `clickhouse/clickstack-otel-collector:2.41.0@sha256:04725e89…`
(entrypoint `/opampsupervisor`, confirming p7), `telemetrygen:v0.159.0@sha256:bad7fde3…`;
the gateway the pinned contrib 0.159.0, which carries the `clickhouse`
exporter): **(1)** up healthy in 25 s; idle ClickHouse 114 MiB / 171 pids,
HyperDX 528 MiB / 43, MongoDB 79 MiB / 54, gateway 31 MiB / 7, collector 38 MiB
/ 8. **(2)** 20 records with resource `project=other` through the stand-in
collector → all 20 rows read `beta-dev`; **control** 3 records straight to the
gateway → `other`; the body is the line only. **(3)** HyperDX through the
forward: one user registered (a second answered `409 teamAlreadyExists`), a
connection (`http://clickhouse:8123`, `reader`, no password) and a log source on
`otel.otel_logs` created over its API, and its own `/api/clickhouse-proxy` (the
UI's path) returned the grouped rows -- **HyperDX reads the contrib gateway's
table** (D2573 stands); **control**: ClickStack's own collector, OpAMP-connected
to the rig's HyperDX, created `otel_cs.otel_logs` with **column-for-column
identical** names and types (its receiver refused the unauthenticated test
record, telemetrygen exit 1 -- consistent with p7's ingestion key; not chased).
Cookie `Domain=localhost` (**D2602**). **(4)** `TTL toDateTime(Timestamp) +
toIntervalDay(7)`, `ttl_only_drop_parts = 1`, `PARTITION BY toDate(Timestamp)`;
`reader`/`gateway` refused from `127.0.0.1`; **control** `reader` from HyperDX's
address read the count; `reader`'s `CREATE TABLE` 403; an ingest-only container
cannot resolve `clickhouse` (**D2603**). **(6)** no published port but the
rig-only forwarder's `127.0.0.1:18080`; HyperDX's `Env` holds the secret 0
times (the processes hold it); no traefik label (**D2600**, **D2601**). **(7)**
at 100 lines/s: **control** (gateway up, 120 s) collector 36.6→45.2 MiB, scrape
200 in 11-13 ms, sender's logging call p50 161-224 µs / p99 447-621 µs;
**gateway stopped 600 s** collector 49.2→65.8 MiB (limit 192), 0 restarts, no
OOM, scrape 200 in 11-17 ms every 30 s, sender p50 157-272 µs / p99 552-784 µs --
**a project does not depend on the plane** (§9's stop not met); the cost:
of 60,000 lines sent while it was down, 5,401 arrived after the restart (the
bounded queue drops after `max_elapsed_time` 60 s -- optional detail, by
design). **Sitting U**: Sheet U0 ran 05:11-05:13Z (four incremental backups,
20-25 s each; row counts of 24 `app` tables + `instance_uuid` in
`/home/op/s42-u0/`; host 7,746 MiB, 4 × Haswell, `sda` 75 G / `sda1` 73.9 G, `/`
72 G with 11 G used, booted 2026-10-17 14:44:11; the reconciler enabled,
**D2599**); **U1 refused by OVH: out of stock (D2598)**. The threat list:
item 9 rewritten with its node ids, items 14 and 15 added (D2585). ADRs 0278 and
0279 written and indexed (0275 marked amended). **(5)** at the plan's fallback
100 lines/s for 30 min (E0 not run, D2598), on a stack recreated fresh: 180,000
lines, 28 HyperDX searches through its proxy (median 49 ms, max 75 ms), no OOM,
no restart; `memory.peak` ClickHouse 285 MiB (pids 185, CPU up to 33 %),
HyperDX 420 MiB (54), MongoDB 107 MiB (65); the gateway 52.4 MiB / 8 pids by
`docker stats` (the contrib image has no `cat` for its cgroup); 11.15 MiB on
disk compressed, 66.96 MiB raw; volumes ClickHouse 98 M, MongoDB 302 M. ADR
0244's rule gives ClickHouse 1,152 MiB / 740, HyperDX 1,696 / 216, MongoDB 448 /
260, the gateway 224 / 64 -- **a 3,520 MiB charge**. **ADR 0277** written from
these and indexed (0221, 0244, 0249 marked amended). **Owed before Run 10**:
U0-U3 at the retry, E0 (the real rate; case 5 re-run if 10x it exceeds 100
lines/s), E1 (the limits re-read on the host; ADR 0277's numbers move with it).

### Run 2 — the three repairs: D2558, D2559, D2544 (`bin/`, `src/`)

**Read first**: `bin/edge-network.sh` whole (344 lines); `bin/reconciler.py:823-886`;
`services/auth-api/app/export_upload.py` whole; `src/agentic_postgres/sql_surface.py`
whole; `tests/contract/test_diagnostic_surface.py:475-526`;
`tests/contract/test_reconciler_dispatch.py:150-180, :912-942`; rig 42c's
transcript.

1. **D2563 (D2558).** Write `tests/contract/test_edge_network_race.py` FIRST
   (`pytestmark` first; the fake-docker pattern; Docker's texts from rig 42c);
   run it → the race cases FAIL against the tree (record the failures). Then the
   two helpers and the nine call sites (`connect_alias`, `disconnect_quiet`;
   `die 9` text unchanged for a real failure). Shellcheck (`test_metrics_surface.py:513-524`)
   and `test_every_connect_goes_through_the_helper`.
2. **D2564 (D2559).** The reconciler change at `:867-870` and the two tests.
3. **D2565 (D2544).** `test_sql_reader_quotes.py::test_a_dash_dash_inside_a_literal_is_kept`
   FIRST → FAILS (record). Measure the shapes (`grep -rn "E'" migrations/ projects/*/migrations/`;
   the old reader's per-template quote parity). Then the scanner in `sql_only`
   (its docstring rewritten: what it reads now). **Diff every template's old and
   new `statements()` output** (a throwaway script in `~/s42/run2/`, printing
   only template names and changed line counts) and list each in `**Done.**`.
   Then the guard `test_every_template_ends_its_scan_outside_a_literal`. **Any
   lint or destructive finding that changes for a template in
   `migrations/templates/` or `projects/control/migrations/templates/` is §9's
   stop.**

**Battery** (`~/s42/run2/battery2.py`): (a) the re-read removed from
`connect_alias` → the race tests FAILED; (b) `disconnect_quiet`'s re-read
removed → FAILED; (c) the URL belt removed from D2564 → the URL test FAILED;
(d) the scanner's literal state removed → the literal test FAILED; (e) `''`
escape handling removed → the guard FAILED on a template that holds `''` (find
one first; if none, a fixture); **control** in each invocation:
`test_metrics_surface.py::test_every_connect_carries_the_alias` (or the tree's
name for `:494-510`) green. **Targeted**: `test_edge_network_race`,
`test_metrics_surface`, `test_reconciler_dispatch`, `test_sql_reader_quotes`,
`test_project_migration_sets`, `test_database_function_signatures`,
`test_migration_lint`-family modules (`grep -rln "lint_project_set\|destructive_findings" tests/contract/`),
`test_mcp_contract`, `test_acceptance_registry`, `test_environment_gates`, the
sweep-selector guard. Commit, push, CI by SHA.

**Done, 2026-10-18.** **D2563**: `tests/contract/test_edge_network_race.py`
written first (a fake `docker` keeping attachments in files; rig 42c's texts):
against the tree, the four race cases FAILED on exit 9 (*"could not attach
apg-edge-traefik-1 to apg-beta-dev-edge"* after Docker's *already exists*) and
the class guard FAILED; the five exit-9 controls and the clean path PASSED. Then
`connect_alias` and `disconnect_quiet` in `bin/edge-network.sh` and all nine
call sites (five connects, four disconnects; every `die 9` text unchanged, Docker's
own line printed first): 11/11. **D2564**: `reconciler_dispatch.upload_refusal_reason`
(the child's last `export_upload: ` line, 200 characters, never one holding
`://`, `X-Amz-` or `Signature=`) called from `reconciler.export`; read first:
every stderr line `export_upload.py` prints is fixed text, `StorageError`'s
`<operation> failed: <code> (HTTP <status>)`, or `load_config`'s variable / file
path -- none a value; a traceback's lines never start with the prefix. The new
test FAILED on the bare `the upload exited 5` before, 52/52 after. **D2565**:
`test_sql_reader_quotes.py` FAILED (3) on the old reader; measured: no `E'...'`
string in any of the 51 templates, dollar tags `$$` (268) and `$fn$` (244)
(`$argon2id$` sits inside a literal), and the old reader left 18 templates with
an odd quote count; then `sql_only` became a three-state scanner (`_scan`,
`scan_end_state`), joined as the old one joined lines: 3/3, **every template ends
in code**. Old vs new `statements()` (`~/s42/run2/diff-readers.py`): **27 of 51
templates changed**; the lint and the published surface the SAME for the
release, control and example sets; the example set's destructive findings the
same; **seven hidden `DROP FUNCTION`s now found** in applied release `0025`,
`0028` and control `0004` -- §9's stop, the operator: proceed (**D2606**). The
`''` branch removed as untestable (**D2607**). **Battery** (`~/s42/run2/battery2.py`,
run twice -- the second after the fake was rewrapped for ruff): **5 of 5 killed**
(a) `connect_alias`'s re-read → 3 FAILED, (b) `disconnect_quiet`'s → 1 FAILED,
(c) the URL belt → 3 FAILED, (d) the literal state → 1 FAILED, (e) the
identifier state → 1 FAILED; control
`test_metrics_surface.py::test_the_attachment_registers_the_alias_on_a_proxy_that_predates_it`
PASSED in each; every file restored `cmp`-equal. **Targeted** (once, 21 modules
-- the plan's `test_mcp_contract` does not exist; `test_capability_compiler` and
`test_scope_vocabulary`, which read the MCP contract, ran in its place; the
`test_migration_lint` family is `test_api_migrations`, `test_approval_gate`,
`test_change_proposal`, `test_client_ir`, `test_control_set`,
`test_database_function_signatures`, `test_dev_environment`,
`test_project_migration_sets`, by `grep -rln "lint_project_set\|destructive_findings\|sql_only\|sql_surface"`):
**822 passed**; ruff clean after rewrapping six long lines of the fake; the race
module 11/11 again. (Workstation: `/tmp/pytest-of-gmpar` is root-owned since
2026-10-18 08:24, so every run used `TMPDIR=~/s42/tmp`, `~/s42/pt.sh`.)
Committed with Run 1's documents as **12c4158**; **CI 39101559948 `contract`:
success**.

### Run 3 — `pg_stat_statements` loaded (`compose.yaml`, `src/`, `bin/`)

**Read first**: `compose.yaml:185-291`; `src/agentic_postgres/bootstrap_statements.py:78-520`;
`bin/postgres-bootstrap.py:116-320`; `src/agentic_postgres/branch_plan.py:119-142`;
`infra/branch/compose.yaml:24-66`; `tests/contract/test_branch_*` that read the
persistent command (`grep -rln persistent_command tests/`); rig 42b's transcript.

The five flags (D2566) in `compose.yaml`'s command, one `-c` per line with a
comment naming ADR 0278 and why `track_utility` is off; the three statements in
`build_statements()` with the signature rig 42b read; `check_violations` reads
the preload, the extension's schema and the revocation; `persistent_command()`
gains the five flags (and `infra/branch/compose.yaml`'s generated twin moves
with it — grep how the twin is held equal, D2513's test). **Grep every reader of
the compose command** (`grep -rn "archive_timeout" tests/ src/ bin/` finds the
tests that read the block) and of `build_statements` (`grep -rn "build_statements" tests/ bin/ src/`).
`tests/contract/test_pg_stat_statements.py` (INS-PGSS-001; the last test is
Docker-backed: bootstrap a `control_cluster.py`-style cluster with the release
command and read the three facts).

**Battery**: the preload flag removed → FAILED; the `REVOKE` removed → the
Docker-backed check FAILED; `track_utility=off` changed to `on` → FAILED;
**control**: `test_the_bootstrap_creates_and_revokes_it`'s `vector` assertion
green. **Targeted**: `test_pg_stat_statements`, every module the greps found,
`test_branch_runtime` (and the branch modules), `test_process_limits`,
`test_acceptance_registry`, `test_environment_gates`, the sweep-selector guard.
Commit, push, CI by SHA.

**Done, 2026-10-18.** Measured first (`~/s42/run3/noload.sh`): on a cluster
started WITHOUT the preload -- every Docker-backed fixture's, and `apg dev up`'s --
`CREATE EXTENSION pg_stat_statements WITH SCHEMA extensions` and the four
`REVOKE`s succeed (only `SHOW shared_preload_libraries` is empty), so the
bootstrap list changes no fixture. `check_violations` runs only from
`postgres-bootstrap.py`'s deploy and check paths, where the preload is present.
Then: `bootstrap_statements.PG_STAT_STATEMENTS_SETTINGS` (the five flags),
`PG_STAT_STATEMENTS_TABLES` (two views) and `PG_STAT_STATEMENTS_FUNCTIONS`
(three, signatures from rig 42b); `build_statements` creates the extension after
`vector` and revokes all five objects from `PUBLIC` (D2597); `compose.yaml`'s
`postgres` command and `infra/branch/compose.yaml` carry the five flags (one
`-c` per line, the reasons in a comment); `branch_plan.persistent_command()`
ends with them; `postgres-bootstrap.py`'s new `pg_stat_statements_violations`
reads the preload, the extension's schema, `PUBLIC`'s privileges on all five
objects and each customer role's on the view and its function. **The
implementation was written before `tests/contract/test_pg_stat_statements.py`**
(INS-PGSS-001: three offline readings and one Docker-backed test that starts the
locked image with every literal `-c` of `compose.yaml`'s command, applies
`build_statements`, asks the product's own `check_violations`, and is refused
the view, the function and the info view as each customer role -- `postgres`
reads, the control): 4/4, so the battery is what shows the tests can fail.
**Battery** (`~/s42/run3/battery3.py`): **4 of 4 killed** -- (a) the preload flag
dropped from `compose.yaml` → 2 FAILED (the offline reading and the cluster's
check), (b) the function `REVOKE` dropped → 2 FAILED, (c) `track_utility` on →
1 FAILED, (d) the branch's settings dropped → 1 FAILED; control
`test_bootstrap_statements.py::test_the_bootstrap_still_pairs_the_schema_with_the_extension`
PASSED in each; every file restored `cmp`-equal. **Targeted** (once: every
module that reads `compose.yaml`, a command, `infra/branch`, `build_statements`
or `bootstrap_statements` -- 50 by `grep -rlE` -- plus the registry, claims,
gates and index guards): **1,783 passed, 6 failed** -- five `check_violations`
tests whose fake catalog did not know the new questions (taught a healthy
cluster's answers, before its generic `pg_extension` answer that the schema
question also matches) and the ADR index's status for 0277 (the guard takes
`Accepted, …`, not a parenthesis); the two modules re-run: **58 passed**. ADR
0277 written meanwhile from case 5 (Run 1's `Done`). Committed as **358cd42**;
**CI 39103028583: failure** -- `test_branch_plan.py::test_the_persistent_service_cannot_reach_the_repository`
(1 failed, 7,989 passed): it pins a branch's persistent settings one by one
and reads the plan's `argv`, so the grep for `persistent_command` did not find
it (D979's lesson, again). Fixed forward in **1e975d8** (the exact equality
gains the five settings as literals; 15/15).

### Run 4 — the telemetry plane (`infra/telemetry/`, `bin/`, `systemd/`, `libexec/`, `src/`)

**Read first**: `infra/edge/compose.yaml` whole; `bin/edge.sh`;
`libexec/agentic-postgres-edge`; `systemd/agentic-postgres-edge.service`;
`bin/provision-host.sh:820-850`; `bin/compose.sh:30-60, :260-290`;
`src/agentic_postgres/capacity_reading.py:140-330, :380-480`;
`src/agentic_postgres/capacity_probe.py:340-400`; `bin/apg-diag.sh`
`verb_containers`; `tests/contract/test_process_limits.py:188-215`; rig 42a's
and E1's transcripts (the limits).

`versions.env` gains `CLICKHOUSE_IMAGE`, `HYPERDX_IMAGE`, `MONGO_IMAGE` (and
`TELEMETRYGEN_IMAGE` only if a proof uses it) by digest. `infra/telemetry/compose.yaml`
(D2573–D2578, the limits from E1 by ADR 0244's rule); a ClickHouse `config.d`
and `users.d` under `infra/telemetry/clickhouse/`; `rendering.build_gateway_config()`
(the gateway's collector config: `otlp` http receiver, `memory_limiter`,
`batch`, `clickhouse` exporter with `ttl: 168h`, database `otel`, user `gateway`);
`bin/telemetry.sh` (`up`: admission first — `exit 12` with the reading when it
does not fit; the ingest network ensured with the re-read; the secret file made
once; the gateway config rendered into `/etc/agentic-postgres/telemetry/`;
`compose up -d --wait`; the state file — `down`, `status` printing each
container, its limits and HyperDX's `apg-telemetry-ui` address);
`libexec/agentic-postgres-telemetry`; `systemd/agentic-postgres-telemetry.service`;
`capacity_probe` reads the state file into `committed`; `doctor capacity` shows
it; `apg-diag containers` lists the plane. **`provision-host.sh` installs the
new unit through its existing loop** (read `:834-840` — no change if it globs).
Tests: INS-PLANE-001, INS-ADMIT-001, `test_cli_contract` (`telemetry.sh`),
`test_diagnostic_surface` (the plane's section), `test_host_infrastructure`
(the unit's lines).

**Battery**: a `mem_limit` removed from the plane → FAILED; a `ports:` added →
FAILED; the charge dropped from `capacity_probe` → the admission test FAILED;
the `exit 12` path skipped in `up` → FAILED; **control**:
`test_the_edge_plane_is_bounded` green. **Targeted**: the new modules,
`test_process_limits`, `test_capacity_*` (`grep -rln "decide(" tests/contract/`),
`test_cli_contract`, `test_diagnostic_surface`, `test_host_infrastructure`,
`test_repository_contract` if `src/` gained a module, `test_acceptance_registry`,
`test_environment_gates`, the sweep-selector guard. Commit, push, CI by SHA.

**Done, 2026-10-18 (the limits from rig 42a's case 5; E1 re-reads them --
D2598).** Measured first (`~/s42/run4/grants.sh`, `grants-d.sh`; contrib 0.159.0
against ClickHouse 26.8.30.8): the exporter's `create_schema` issues `CREATE
DATABASE` at every start, so with `INSERT` alone, or `CREATE TABLE` + `INSERT`
over a pre-created database, **the whole gateway exits** (*"cannot start
pipelines: failed to start "clickhouse" exporter: ... necessary to have the
grant CREATE DATABASE ON otel.\*"*); `CREATE DATABASE` + `CREATE TABLE` +
`INSERT` (no `SELECT`) wrote 5/5 rows, as did the four-grant control (**D2603
resolved**: ADR 0277 item 7). Then (`~/s42/run4/drift.sh`): every moving tag had
moved since the lock (**D2609**) -- `lock-versions.sh --update --add-images`
written, the three images added by exact tag, `versions.env` +3 lines, `--check`
current. Built: `infra/telemetry/compose.yaml` (four services, the limits by ADR
0244's rule from case 5, `restart: unless-stopped`, three external networks,
HyperDX's wrapper, `USAGE_STATS_ENABLED "false"`, `OTEL_SDK_DISABLED "true"`),
`infra/telemetry/gateway.yaml` (**D2610**), `infra/telemetry/clickhouse/config.xml`
(`max_server_memory_usage` 966,367,641 = 80 % of 1152m; system logs removed);
`src/agentic_postgres/telemetry_plane.py` (names, `charge_mb` = **3,520**, the
users file, the state file and its reader); `Reading.platform` in
`capacity_reading`, read by `capacity_probe.read`, named by `decide` and the
doctor (**D2608**); `bin/telemetry.py` (`admit`, `render-users`, `write-state`,
`charge`); `bin/telemetry.sh` (`up`: admission first, the three networks through
`bin/lib/telemetry-network.sh`'s ensure-with-re-read, the secret once `0440
root:1000`, the users for the real subnet, the state file, `compose.sh
--telemetry --runtime up -d --wait`; `down` keeps volumes and networks and
removes the charge; `status`); `bin/compose.sh --telemetry` (**D2611**);
`libexec/agentic-postgres-telemetry`; `systemd/agentic-postgres-telemetry.service`
(installed by `provision-host.sh`'s existing globs -- no change); `apg-diag
containers`'s `-- apg-telemetry (platform)` section. Offline checks: the model
renders through `compose.sh --telemetry config` with no `ports`; `-v`, a
two-scope call and an `up` without `--runtime` refused; `up` as non-root exit 3.
Tests: `test_telemetry_plane.py` (7), `test_telemetry_admission.py` (4; the
last runs the real `telemetry.sh up` with a fake `docker` and `id` and reads
exit 12 before any network), `test_process_limits::test_the_telemetry_plane_is_bounded`,
`test_host_infrastructure` (the unit and launcher registered; the unit orders
after nothing of a project's), `test_diagnostic_surface::test_containers_lists_the_telemetry_plane`,
`test_cli_contract` (`telemetry.sh`, `telemetry.py`). The admission test found
**D2612** (an unprivileged `admit` crashed on EACCES; fixed: unreadable, refused).
**Battery** (`~/s42/run4/battery4.py`): **5 of 5 killed** -- (a) a `mem_limit`
dropped, (b) a port added to HyperDX, (c) the charge dropped from
`capacity_probe`, (d) the exit-12 path skipped in `up`, (e) the network re-read
removed -- each target FAILED, control `test_the_edge_plane_is_bounded` PASSED,
every file restored `cmp`-equal. **Targeted** (once; 16 named modules plus every
module that reads `decide(`, `capacity_probe`, `capacity_reading`,
`platform_text` or `committed_total`): **1,769 passed, 2 failed** -- the new
diagnostic test's helper (`mkdir` without `parents`) and
`test_a_stopped_project_does_not_end_the_listing`, which pins the listing's
section headers exactly (now ending with the plane's, a stricter list); ruff's
nine findings fixed (a file name flagged as a password, two `ElementTree` parses
of the repository's own files, a missing import, five long lines); the three
touched modules re-run: **66 passed**.

### Run 5 — the logs: the collectors' pipeline and the services' export

**Read first**: `src/agentic_postgres/rendering.py:1355-1521`;
`src/agentic_postgres/runtime_override.py:260-400`; `compose.yaml:1216-1296`,
`:1960-2010` (`mcp`'s environment); `services/auth-api/app/log_setup.py` whole;
`services/auth-api/app/main.py:260-280`; `services/auth-api/requirements*` or
`pyproject.toml` (whichever the image installs from);
`tests/contract/test_request_log.py` whole; `tests/contract/test_metrics_surface.py`
(the render tests); `bin/project-runtime.sh:290-340`.

**First, measure** (D2575): `docker run --rm --entrypoint pip <the auth-api
image built from the tree> list` → whether `opentelemetry-sdk` and
`opentelemetry-exporter-otlp-proto-http` are installed and at which versions;
a missing one is added at the version the image's existing OpenTelemetry
packages pin, recorded. Then: the logs pipeline in `build_otel_config` (receiver
`otlp`; processors `memory_limiter`, `resource` upsert `project`, `batch`;
exporter `otlphttp/gateway` with the bounded queue) — **the metrics pipeline
untouched** (a test diffs it); `metrics` joins `apg-telemetry-ingest` as an
external network (`compose.yaml`); `project-runtime.sh` ensures the network
before `up` (the D2563 helper shape); `APG_OTLP_LOGS_ENDPOINT` on every service
that runs `create_app` (grep); `log_setup` adds the handler (message only, no
`exc_info`/`stack_info`, bounded batch). **Grep every reader of the rendered
collector config** (`grep -rn "build_otel_config\|otelcol.yaml" src/ bin/ tests/`)
— the mounted-content digest (ADR 0155) moves the collector's recreate with it,
by design.

**Battery**: the `upsert` changed to `insert` → `test_the_logs_pipeline_stamps_the_project`
FAILED; the queue bound removed → FAILED; `exc_info` kept → the canary test
FAILED; the handler made synchronous → `test_a_slow_exporter_does_not_block_a_request`
FAILED; **control**: `test_a_request_prints_one_line_with_the_template_and_no_caller_value`
green. **Targeted**: `test_metrics_surface`, `test_request_log`,
`test_telemetry_plane`, `test_project_runtime_stop_start`, `test_mcp_runtime`,
`test_auth_service_shape`, `test_process_limits`, `test_acceptance_registry`,
`test_environment_gates`, the sweep-selector guard. Commit, push, CI by SHA.

### Run 6 — the control set's `0009`, the reconciler's insights and DB time (`projects/control/`, `bin/`, `src/`)

**Read first**: `projects/control/migrations/templates/0008-control-plans-usage.sql:126-155,
:529-570, :754-959`; `projects/control/migrations/manifest.json`;
`bin/reconciler.py:1225-1268, :1435-1508, :1640-1668`;
`src/agentic_postgres/usage_reading.py` whole;
`src/agentic_postgres/reconciler_dispatch.py:184-243, :687-735`;
`tests/contract/test_reconciler_dispatch.py:1449-1469`; `tests/contract/test_control_usage.py`;
`tests/contract/control_cluster.py`.

`0009-control-insights.sql` (template + manifest entry): `app.control_insight_samples`
(FORCE RLS, no policy for the auth role), `control_record_insights` (INVOKER,
`REVOKE ALL … FROM PUBLIC`, no grant; the whitelist; the 7-day delete),
`control_usage_samples` + `db_time_ms`, `statements_reset`; `unread`'s CHECK
widened by `db_time`; `control_record_usage` and `control_usage_document`
re-created (bodies diffed against 0008's in a test); `control_project_insights`
and `control_project_monitoring` (DEFINER, `control_require_role`, granted to
the auth service only); `AP900` down. **No `--` inside a literal** (and the
Run 2 guard now proves it). `bin/migrate.sh --project project.control.example.yaml
freeze-lock`, then `… propose --by "Session 42 executor"` (refuses while a dev
environment exists — `bin/dev.sh down` first). `usage_reading.insights_sql(roles)`
and `db_time_sql(roles)` (the D2568 roles from `naming.database_roles`);
`reconciler_dispatch.insight_sample`, `RECORD_INSIGHTS_SQL`, `USAGE_FIGURES +=
db_time`; `Reconciler.record_usage` reads both in the same pass (one more psql
per awake slot; a sleeping slot records nothing for insights) and logs the
pass's duration. The guard's closed set widens by `control_record_insights`.

**Battery**: the 7-day delete removed → FAILED; the role filter removed → the
platform-role test FAILED; a reset read as a negative increase → FAILED; `db_time`
dropped from the whitelist → FAILED; **control**: `test_calls_are_counted_from_durable_rows`
green. **Targeted**: `test_control_usage`, `test_control_insights`,
`test_insights_reading`, `test_reconciler_dispatch`, `test_usage_sampler`,
`test_idle_sleep`, `test_notifications`, the control-set modules (`grep -rln
"control_cluster" tests/contract/`), `test_acceptance_registry`,
`test_environment_gates`, the sweep-selector guard. Commit, push, CI by SHA.

### Run 7 — the routes, the CLI, monitoring, the documents (`services/`, `bin/`, `docs/`)

**Read first**: `services/auth-api/app/control_routes.py:1351-1400`;
`control_service.py:891-895, :1104-1116`; `control_repository.py:372-410`;
`control_roles.py:48-230`; `bin/cloud.py` `parser()` and the `usage` family;
`bin/usage.sh`; `tests/contract/test_control_cli.py`; `docs/control-plane.md`,
`docs/managed-projects.md`, `docs/operator-guide.md` (the edge section
`:160-200`).

`GET /v1/projects/{key}/insights` and `/monitoring` (D2571, D2572); `MATRIX` +
`KEY_SCOPES` (`projects:read`); `signals.py`; the OpenAPI snapshot regenerated
(`bin/app-contract.sh --update --snapshot control > contracts/control-openapi.canonical.json`)
and `bin/app-contract.sh --check`; `bin/insights.sh`, `bin/monitoring.sh`
(shims of `bin/usage.sh`'s shape), `cloud.py` families `insights`, `monitoring`.
**Documents**: `docs/monitoring.md` (new — the signal list, each source, what
the operator reads in HyperDX, how to open the forward, what is NOT collected);
`docs/control-plane.md` (the two routes); `docs/managed-projects.md` (insights,
the restart once at 1.20.0, DB time); `docs/operator-guide.md` (the telemetry
plane: `telemetry.sh`, the unit, the forward, the login, `doctor capacity`'s new
row); `docs/developer-guide.md` (the tuning pointer's target section — read it
exists first); the documentation index (`test_documentation_index` reads it).

**Battery**: `projects:read` removed from the insights route's scopes → FAILED;
a `recommendation` member added to the document → `test_no_member_advises`
FAILED; a signal pointing at a missing column → FAILED; **control**:
`test_a_foreign_and_a_missing_project_answer_alike` (usage's) green. **Targeted**:
`test_control_insights`, `test_signals`, `test_control_cli`, `test_cli_contract`,
`test_control_roles`, `test_app_contract` (the snapshot), `test_documentation_index`,
`test_session12_documented_path`, `test_acceptance_registry`,
`test_environment_gates`, the sweep-selector guard. Commit, push, CI by SHA.

### Run 8 — the trip's instruments, written and rehearsed offline

Commits nothing but its `**Done.**` (docs). In WSL `~/s42/run8/` (copied to the
scratchpad):

- **`s42-derive.py`** — from `~/s41/run8/s41-derive.py`: the children
  (`s42-units`, `-free`, `-probe-start/-stop`, `-launch`, `-sweep`, `-v1`,
  `-after-reboot`, `-external`, `-x0`, `-dns`, `-hostyaml`) from Session 41's,
  substitutions on the BODY only (the header split off first — Session 41's
  lesson), every anchor counted; `slot5-prod` → `slot6-prod`, `41` → `42` where
  the anchor says so.
- **`s42-lifecycle.py`** — from `s41-lifecycle.py` by `make-lifecycle42.py`
  (D2581): the samples file appended and fsynced per sample; `session: 42`;
  organisation `lifecycle-s42`; the insights workload and reads; the
  `--resume-at-export` path re-reading the samples file.
- **`s42-window.py`** — the deploy-window probe (D2567): one project's
  `routes.app` `/api/rest/` and `/api/auth/health` once a second, every answer's
  status and time appended to a JSONL file; `--stop-after-quiet 60`.
- **`s42-telemetry.py`** — the agent's host reads after T1: `telemetry.sh
  status` (through the operator's sheet), the forward opened from WSL as `op`
  (`ssh -N -L 18080:<address>:8080`), `curl -s -o /dev/null -w '%{http_code}'
  http://127.0.0.1:18080/` → a login page code, closed.
- **`s42-r2shape.py`** (D2582).
- **Rehearsals** (`rehearse_lifecycle42.py`, from 41's): against a fake `/v1`,
  the instrument killed at the export and resumed → the samples file holds
  every sample taken before the kill, the record names its sha256; a pool sample
  that times out is a failed sample and the thread lives (D2500's repair kept);
  the notifications read compares against the record's operations (a failed
  one included).

### Run 9 — the bump, the registry, the gate, the threat rows, the Ledger to `trial`, the documents

**Gates once, clean tree, in shards** (D2587): `bin/session-01-check.sh` and
`bin/session-42-check.sh --mode offline`. Then:
`CURRENT_SESSION` 42 (`__init__.py:1206`) and its paragraph; `VERSION` 1.20.0;
README and the `--session`/`--through-session` literals (counted per file);
registry +18 (§2, under `# Session 42 (ADR 0277-0279)`, the regex gains `INS`);
`CLAIMS` +18, `OFFLINE_CLAIMS` +12, `CLAIM_INTRODUCED_IN`; the ten Ledger rows
`trial` + `ACCEPTED_TYPES` the eleven (D2583); `bin/render-reality-ledger.py
--write`; the four `THR-*` rows; `bin/session-42-check.sh` and its gate-modes
test (D2588); the live modules `tests/external/test_session42_reearning.py`
and `tests/deployment/test_session42_telemetry_host.py` (each `pytestmark`
first, `test_this_module_uses_no_ssh` in the external one); the older fixtures
widened (D2581); `bin/render-acceptance-matrix.py --write`; `upgrade plan`
offline in a worktree at the commit (D2584); `test_cli_contract` (`session-42-check.sh`
in `SHELL_COMMANDS`). **Battery** (`battery9.py`): a `trial` row citing a
Session 41 claim → FAILED; `INS` removed from the regex → FAILED; a widened
fixture narrowed back → the re-run FAILED on the 42 record fixture; **control**:
`test_the_idle_sleep_row_is_reachable_iff_its_sleep_is_accepted` green.

### Run 10 — sitting 1 (day 1): the release, the plane, `slot6-prod` prepared, the dry run

**Before the day**: CI green on the deploy commit; Sheet P1 done (any day
before); `pytest --setup-plan` of the host and external selections with the
variables set (D671). **Order**: the bundle and checkout over SSH (`git rev-parse
FETCH_HEAD` confirmed), `uv sync`, renders → **R1** → **R2a/R2b/R2c** (one
project at a time, `s42-window.py` running against that project from WSL
through each) → **R2d** (`slot3-prod`, `slot.sh redeploy`, the window probed)
→ **A1** → **T1** (the plane: `telemetry.sh up`, the unit enabled) → the agent's
`s42-telemetry.py` → **T2** (the operator creates HyperDX's user, the connection
and the log source; reads a line from each project in HyperDX — the agent sends
one request to each project's `routes.app` first) → **PV** → **H1** →
`s42-dns.sh slot6-prod` (GO) → **SL1** → **SL1b** → **SL2** → **SL3** → **RC1**
→ **RA** → **K1** → **V1** (`-k "not after_reboot and not lifecycle"`, writing
nothing) and the agent's **X0** (external, `-k`, writing nothing). **If V1 or X0
fails**: repair, move the commit, redeploy all four — **before `slot6-prod`
exists as a project** (D2448).

### Run 11 — sitting 2 (day 2): the re-earning, the insights, the reboot, the sweep, the tag

1. **The lifecycle** from WSL: `s42-lifecycle.py` (the probe organisation's
   `plan_limit_reached` read first while `slot6-prod` is `ready`; then the new
   organisation; create; credentials; the insights workload and reads; sleep;
   wake; idle sleep at 15 with the probes stopped; wake; the two resizes; the
   export; **K2** at the pause; delete; the second creation `no_slot`). Exit 0
   expected; anything else is read, never re-run blind (§9).
2. **A1'** (the registry: slot1/2/4/5/6 agrees (deleted)).
3. **B1** — the reboot; then `s42-after-reboot.sh` BEFORE any sweep: **every
   unit — the four projects', the edge, the reconciler, the telemetry plane —
   active by itself** (D2558 repaired); `apg-diag containers` lists the plane.
4. **S1** — the one sweep (the host half, `--lifecycle-record-file` and
   `--slot-outputs` from K2); **then** the external half from WSL; **then** the
   merge (`write-session-evidence`); **then** the tag `1.20.0` on the deployed
   commit from the workstation.
5. **SL4** (after the tag).

### Run 12 — the close

The Ledger from the TAGGED evidence (D2583's rule, D2560's precedent); the
envelope's Session 42 section (the upgraded host's capacity row replacing
`UNMEASURED` *"the rescaled host's capacity"* if the reading is the same kind;
the plane's footprint at rest and under E1's load; the four deploy windows; the
insights/usage pass duration; the lifecycle's numbers); `docs/scope-closure.md`
**§35**; this plan's Status COMPLETE; the stage plan's Status block re-read and
rewritten; CLAUDE.md §2 rewritten for Session 43's planner (old copy to the
scratchpad first). **Battery** over the Ledger moves (as Session 41's Run 12).
Gate once in shards on the close commit; push; CI by SHA.

---

## 7. Evidence and claims

**Expected at the merge** (Run 11): **302 claims** (133 offline). **`failed` 1:
`documented_path`** (D1935). Everything else **passed** — including Session
41's `lifecycle_third_trial_live`, `lifecycle_reearned_live` and
`notifications_live` re-run on Session 42's record: the first two now read
every window from the samples file and are predicted to **pass**;
`notifications_live`'s proof counts the eleven types and **will fail again if
the Session 42 lifecycle has a failed operation** — a clean run passes it; a
failed one is recorded as D2557 recorded it, and no `trial` row cites it.
**Exit 5 for `documented_path` and no other reason.** Predictions, each moved
only by the evidence.

**The three modes.** Offline: CI's artifact for the deployed SHA (133 claims).
Host: S1 with `--lifecycle-record-file`, `--slot-outputs` (`slot6-prod`, K2) and
`--live-slot-outputs` (`slot3-prod`). External: from WSL, with
`--control-outputs`, `--control-probe-file`, `--lifecycle-record-file`,
`--customer-credential-dir`; **the Session 42 customer proofs reach only
`routes.control`, the slot's recorded `routes.app` and the public names on 5432,
and open no SSH**. **Deploy every project fully, THEN the plane, THEN the dry run
(V1, X0), THEN the lifecycle, THEN the reboot, THEN sweep, THEN external — every
half at one commit.**

---

## 8. Security invariants this session touches

| Invariant | How this session keeps it |
|---|---|
| **A product surface runs no SQL** | Insights show text a statement already ran with; nothing runs it; the tuning pointer is a sentence (D2571) |
| **The control plane holds nothing that opens a project's data or admin plane** | The reconciler (root, the host actor) reads `pg_stat_statements` through the container; the control plane reads only its own samples (D2569); it has no path to ClickHouse |
| **An agent record carries no URL, key, token or caller value — and neither does a log line or an insight** | The exported record is the canary-checked line, no traceback (D2575); `track_utility` off, literals normalised, platform roles excluded, the canary on a real server (D2568); the upload's line refused if it holds a URL (D2564) |
| **No published ClickStack/HyperDX/Prometheus route, no port beyond ADR 0246's list** | No `ports:`, no router label (INS-PLANE-001); the listeners read on the host (INS-HOST-001); HyperDX by the SSH forward and its login (D2579) |
| **Projects share no project-scoped value** | The ingest network holds only collectors and the gateway; `project` stamped by the platform (D2574); insights through the membership check (THR-INS-LEAK) |
| **Observability may lose detail; it may not destabilise the workloads it observes** | Bounded, charged, a project independent of the plane (rig 42a case 7; D2574, D2576, D2577) |
| **No secret in Compose interpolation or `docker inspect`** | ClickHouse and MongoDB have none (network-admitted); HyperDX's from a file through a wrapper (D2578; a host proof reads `Env`) |
| **A report may not substitute an answer for a failure to determine one** | Insights' empty window `could_not_determine`; DB time unread named; the upload's cause kept; a lost race re-read, never assumed (D2563, D2564, D2570, D2571) |
| **Nothing `planned` has a control** | `query_insights` and `monitoring` gain their routes in the bump with their rows at `trial`; resolved at the close |

---

## 9. Stop conditions

Stop and ask the operator, without improvising, when:

- **the OVHcloud manager says the upgrade changes the IPv4**, cannot keep the
  disk, or offers a plan other than the 12 GB one; or after U1 the host does
  not answer within 30 minutes;
- after U2 a project's doctor reads anything but 12 ok, or a row count differs
  from U0's;
- rig 42a: HyperDX cannot read the contrib gateway's table (D2573), HyperDX
  needs a secret that cannot come from a file (D2578), or **case 7 fails** (a
  project's collector or route affected by the plane being down, D2574);
- rig 42b: a utility statement or a literal reaches `query` with the flags set,
  or the extension cannot be revoked from `PUBLIC`;
- Sheet E1 stops at its 2,000 MiB floor, or a neighbour's memory moves by more
  than its own noise during E1;
- Run 2's reader changes a lint or destructive finding of an APPLIED release or
  control migration (D2565);
- a design here would need the control plane to reach a project's database or
  ClickHouse, a route on the edge for the plane, a published port, or a
  recommendation with a confidence;
- `upgrade plan` prices 1.20.0 at `major`, or for a reason this plan did not
  name;
- a deploy's window on any project exceeds 5 minutes, or a project's routes do
  not return after its R2 sheet;
- the telemetry plane is refused by admission on the upgraded host (`exit 12`) —
  the sizes are wrong, not the host;
- **V1 or X0 fails and the repair would move the commit after `slot6-prod` has
  been created**, or any commit move after its deletion — there is no seventh
  slot prepared;
- the probe organisation's create is NOT refused `plan_limit_reached`, or the
  idle sleep fires while a probe was still running against the slot;
- a unit does not come back by itself after B1 (D2558's repair failed: the trip
  continues only by the operator's choice, recorded);
- a `trial` row would outlive the close, or a row would move to `beta` without
  its claims `passed`;
- a currently-passing test would be weakened to make a new one pass;
- `--render-only` stops working with no host and no root.

---

## 10. Open items this session carries and creates

**Carried, untouched, each still true:** M7's X1/X2 (Hetzner), allowed and not
this plan's (D2590); beta's three rotations (D1995); D1936/D2005; D1547;
D2020/D2025; D2031; D1642, D1798, D1869, D1871, D1722/D1806, D1784, D1792, ADR
0241's bound; D1045; D1375; D976; D688; D771; D340; D466; D540; D942; D1203;
D1205; D1211; the 24 unclaimed requirements; `process-max` 1 (D593);
`documented_path` (D1935); accounts and organisations never deleted (D2065,
D1986); TOTP seeds plaintext (ADR 0252); `/v1/sessions` unthrottled (D2166);
the reconciler and the operator serialised by a rule, not a lock (D2178); a
slot's provider resources outlive it (D2181); the export URL crosses the
control database (ADR 0259); `storage.enabled: false` still emits storage's
router (D2144); `materialize-secrets` has no last-known-good fallback;
`secret_required_added` cannot fire (D2331); Postgres sees the gateway's
address and no channel binding (D2325); a plaintext peer holds a socket for the
read deadline (D2326); a branch shares its parent's `system_identifier` and
identity row; a branch is not backed up; the parent's user hashes are copied
into a branch; branch certificates accumulate in `acme.json`; the backups
recording's R2 requests per slot; usage samples never pruned; `storage_gb` and
`agent_calls_per_day` shown, not enforced (D2519, D2520); no override of a plan
limit (D2521); notifications without read state or deletion; idle sleep wakes
only by request; the organisation `lifecycle-s41` remains, empty.

**Created, and named so Session 43 does not inherit them silently:**

- **The telemetry plane is a second store** (Prometheus per project, ClickHouse
  on the host): ADR 0277 names the split — Prometheus answers what `doctor`
  reads, ClickHouse holds D1918's lines, the control database holds every
  customer-visible history. A fourth place for a number is a row.
- **HyperDX's MongoDB and ClickHouse's volumes are not backed up**: losing them
  loses the operator's saved searches and up to 7 days of lines — never a
  customer's data. The node-loss runbook (Session 45, D1984, D2593) says so.
- **`apg-agent` can open the same forward as `op`** (the sshd file is global,
  p5); it meets HyperDX's login. Narrowing forwarding per account is an sshd
  change nobody asked for.
- **Insight samples are kept 7 days, usage samples forever**; both are the
  operator's to revisit when slots multiply.
- **A branch loads `pg_stat_statements` but is not sampled** (the reconciler
  samples slots); a branch's insights are `planned`.
- **The restore paths start without the preload** (a drill, a node restore);
  a restored project's first deploy loads it again.
- **The partition, if U2 found the disk grown and the partition not**, is not
  grown (D2562); `disk_gb` is what the reading says.
- **`slot1-` … `slot6-prod` are consumed** after this trip; the next lifecycle
  needs `slot7-prod`. **The organisation `lifecycle-s42` remains**, empty.
- **Only D1918's lines are collected**: PostgreSQL's log, Traefik's access log
  and PostgREST's are not, by decision (D2575).

---

## Appendix — what to consult, how a run is executed here, and the sheets

**Consult, in this order:** CLAUDE.md §1 (the shell traps); this plan's §0, §1
and the run's own text; the reads its run names. **The tree wins.**

**How a run is executed here**: CLAUDE.md §5. Every `sudo` line is the
operator's, on a sheet, under `script -q -e -c '…' /home/op/s42-<sheet>.txt`
when it execs into a container or deploys (D972, D1501), never piped or
redirected; `sudo -v` in the foreground first (D1376). Every `op` line is the
agent's over SSH; remote loops in a script file with `PATH="$HOME/.local/bin:$PATH"`
exported. **`<sha>` is never typed on a sheet**: the agent fills it from `git
rev-parse HEAD` on the host before handing the sheet. **Before any sheet that
deploys, retires, restores, reboots or recreates the edge: `sudo systemctl stop
agentic-postgres-reconciler`, and `start` after** (D2178); **after any edit to
`host.yaml` or any checkout move: restart it** (D2411, D2179). **Read `--help`
of every command on a sheet before handing it** and correct the line to it —
`bin/telemetry.sh`'s flags are Run 4's, and the T sheets below are written to
them by Run 10. **A sheet may not hand over a command whose precondition is the
previous sheet's success** (D1510): one sheet, one outcome, read before the next.

### Sheet U0 — before the upgrade (Run 1, sitting U)

```
sudo -v
sudo systemctl stop agentic-postgres-reconciler
sudo bash /home/op/s42-u0.sh      # sha256 printed by the agent; incremental backups of the four
                                  # projects (bin/backup.sh, the verb read from its --help by the
                                  # agent when writing the script, one project at a time), row
                                  # counts, free -m, nproc, lsblk, df -h /, the units, the edge's
                                  # state file; writes /home/op/s42-u0/ and /home/op/s42-u0.txt
```

### Sheet U1 — the upgrade (Run 1; the operator alone)

```
OVHcloud manager -> the VPS apg-ovh-01 -> change the model to the 12 GB plan.
BEFORE confirming, write on this sheet's transcript what the manager says:
  the plan's name, vCPU, memory, disk, monthly price;
  whether it reboots; whether the IPv4 15.204.231.45 is kept; whether it can be undone.
If the IPv4 changes: STOP (§9). Confirm. Tell the agent "done".
```

### Sheet U2 — after the upgrade (Run 1)

```
#   the agent runs s42-after-upgrade.sh (units by ActiveEnter vs multi-user.target, D2140;
#   nproc, free -m, lsblk, df -h /, the IPv4) and prints which unit, if any, failed
sudo systemctl start agentic-postgres-project@<the unit that failed>     # ONLY if one did (D2558), once
sudo bin/doctor.sh --project alpha-dev
sudo bin/doctor.sh --project beta-dev
sudo bin/doctor.sh --project control-prod
sudo bin/doctor.sh --project slot3-prod
sudo bash /home/op/s42-u0.sh --counts-only      # equal to U0's
```

### Sheet U3 — the host re-declared (Run 1)

```
sudo install -o op -g op -m 0600 /etc/agentic-postgres/host.yaml /home/op/etc-host.yaml
#   the agent runs s42-hostyaml.py on both copies (memory_mb from U2's free -m total; disk_gb only if
#   the doctor's reading moved) into /home/op/s42-u3/ and prints the diffs; read them, then:
sudo install -o root -g root -m 0600 /home/op/s42-u3/etc-host.yaml /etc/agentic-postgres/host.yaml
#   (the checkout's copy is op's and the agent installs it)
sudo systemctl start agentic-postgres-reconciler
sudo bin/doctor.sh capacity --host host.yaml      # read --help first and correct this line to it
```

### Sheet E0 — readings on the upgraded host (Run 1; reads only)

```
sudo bash /home/op/s42-e0.sh      # sha256 printed; counts of apg.* lines per service per hour, never a line
```

### Sheet E1 — ClickStack's footprint on the upgraded host (Run 1)

```
sudo bash /home/op/s42-e1.sh      # sha256 printed; rig42-telemetry up, 30 min at 10x E0's rate,
                                  # stops below 2,000 MiB available, then down -v and read gone
```

### Sheet P1 — the consoles (any day before Run 10's SL1)

```
Cloudflare DNS, DNS only (grey), no AAAA, each -> 15.204.231.45:
  A slot6.agenticpostgresql.com
  A pool.slot6.agenticpostgresql.com
  A direct.slot6.agenticpostgresql.com
Cloudflare R2 (EEUR, Standard): apg-slot6-prod, apg-slot6-prod-backup, each with an Object R&W token
Backblaze B2: apg-slot6-prod-backup-mirror, with an application key limited to it
```

### Sheet R1 — the release priced (Run 10)

```
sudo bin/upgrade.sh plan --project alpha-dev    --candidate .generated/alpha-dev/outputs.json    --also api_operation_added --json
sudo bin/upgrade.sh plan --project beta-dev     --candidate .generated/beta-dev/outputs.json     --also api_operation_added --json
sudo bin/upgrade.sh plan --project control-prod --candidate .generated/control-prod/outputs.json --also api_operation_added --json
#   Run 9 corrects the --also list to what compatibility.py asks for (D2584)
```

### Sheets R2a / R2b / R2c — 1.20.0 deployed, one database restart each (Run 10)

```
sudo systemctl stop agentic-postgres-reconciler
#   the agent starts s42-window.py against alpha-dev before, and stops it after
script -q -e -c 'sudo ./deploy.sh --host host.yaml --project project.alpha.yaml   --capabilities capabilities.yaml --through-session 42' /home/op/s42-r2-alpha.txt
#   (beta, then control, each its own sheet, each with its own window probe)
script -q -e -c 'sudo ./deploy.sh --host host.yaml --project project.beta.yaml    --capabilities capabilities.yaml --through-session 42' /home/op/s42-r2-beta.txt
script -q -e -c 'sudo ./deploy.sh --host host.yaml --project /home/op/control.yaml --capabilities capabilities.yaml --through-session 42' /home/op/s42-r2-control.txt
```

### Sheet R2d — `slot3-prod` moved by the product's verb (Run 10)

```
script -q -e -c 'sudo bin/slot.sh redeploy --host host.yaml --slot slot3-prod --confirm slot3-prod' /home/op/s42-r2-slot3.txt
```

### Sheet A1 — the registry after the last deploy (Run 10)

```
sudo bin/control.sh adopt --project alpha-dev    --organization 10234b92-b2d7-4573-bebb-f012ce5c8f02 --confirm control-prod
sudo bin/control.sh adopt --project beta-dev     --organization 10234b92-b2d7-4573-bebb-f012ce5c8f02 --confirm control-prod
sudo bin/control.sh adopt --project control-prod --organization 10234b92-b2d7-4573-bebb-f012ce5c8f02 --confirm control-prod
sudo bin/control.sh registry      # agrees x4, slot1/2/4/5 agrees (deleted); exit 0
```

### Sheet T1 — the telemetry plane (Run 10)

```
script -q -e -c 'sudo bin/telemetry.sh up --host host.yaml' /home/op/s42-t1.txt      # admission first; exit 12 = STOP
sudo systemctl enable agentic-postgres-telemetry
sudo bin/telemetry.sh status --host host.yaml      # four containers healthy, the limits, HyperDX's address
sudo bin/doctor.sh capacity --host host.yaml       # the plane's charge as its own row
```

### Sheet T2 — HyperDX's user (Run 10; the operator)

```
#   on YOUR machine (not the agent's): ssh -N -L 18080:<HyperDX's address from T1>:8080 op@15.204.231.45
#   open http://127.0.0.1:18080 ; create the one user; the password into your password manager only
#   Team settings -> a ClickHouse connection: host clickhouse, port 8123, user reader, no password
#   a log source: database otel, table otel_logs (timestamp, body as HyperDX's form names them)
#   read one line from each of alpha-dev, beta-dev, control-prod, slot3-prod (the agent sent one request each)
#   close the forward; say "done" and which projects' lines you saw
```

### Sheet PV — `apg-diag` reinstalled (Run 10)

```
cd /home/op/agentic-postgres
sudo install -m 0755 -o root -g root bin/apg-diag.sh /usr/local/bin/apg-diag
sudo cmp bin/apg-diag.sh /usr/local/bin/apg-diag && echo "apg-diag is the checkout's"
#   then the agent reads, as apg-agent: sudo apg-diag containers   (the -- apg-telemetry (platform) section)
```

### Sheet H1 — `slot6-prod` declared (Run 10)

```
sudo install -o op -g op -m 0600 /etc/agentic-postgres/host.yaml /home/op/etc-host.yaml
#   the agent runs s42-hostyaml.py --add-slot on both copies (slots.declared += slot6-prod=slot6.agenticpostgresql.com=apg-slot6-prod-backup-mirror)
#   into /home/op/s42-h1/ and prints the diffs; read them, then:
sudo install -o root -g root -m 0600 /home/op/s42-h1/etc-host.yaml.slots /etc/agentic-postgres/host.yaml
```

### Sheet SL1 — `slot6-prod`'s providers (Run 10)

```
sudo bin/slot.sh prepare --host host.yaml --slot slot6-prod
sudo bin/bootstrap-providers.sh --host host.yaml --project /etc/agentic-postgres/slots/slot6-prod/manifest.yaml --plan
sudo install -d -m 0700 /root/.config/agentic-postgres/bootstrap
sudo nano /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo chmod 0600 /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo bin/bootstrap-providers.sh --host host.yaml --project /etc/agentic-postgres/slots/slot6-prod/manifest.yaml --apply \
     --operator-credential-file /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo shred -u /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo ls -la /root/.config/agentic-postgres/bootstrap/      # empty, no nano .save copy (D2061)
#   YOU: open 443 on the store host to your address (docs/secret-store.md §1), then in Infisical,
#   project `slot6-prod`, environment `dev`: the storage pair at /storage (create the folder),
#   the backup pair at /backup, the mirror pair at /backup; close 443 again and read it closed.
```

### Sheet SL1b — the pairs' shape, before they are materialized (Run 10)

```
sudo python3 /home/op/s42-r2shape.py --project slot6-prod      # sha256 printed; prints yes/no lines ONLY (D2582)
#   any "no": re-enter that pair in Infisical, then run this sheet again
```

### Sheet SL2 — materialized (Run 10)

```
sudo bin/materialize-secrets.sh --project /etc/agentic-postgres/slots/slot6-prod/manifest.yaml --requirements secrets.required.yaml --session 42
```

### Sheet SL3 — the slot read (Run 10)

```
#   the agent has run s42-dns.sh slot6-prod (three records, exit 0)
sudo bin/slot.sh status --host host.yaml         # slot6-prod ready; slot3-prod allocated; slot1/2/4/5 consumed
sudo bin/control.sh registry                     # ... slot6-prod prepared (slot); exit 0
```

### Sheet RC1 — the reconciler back, reading the new declaration (Run 10)

```
sudo systemctl start agentic-postgres-reconciler
sudo bin/reconciler.sh status       # idle; the journal's slot line names slot6-prod (D2411)
```

### Sheet RA — the admission rehearsal at the deployed commit (Run 10, after the last deploy and T1)

```
sudo bin/rehearse.sh admission-refused --outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json --host host.yaml --manifest /home/op/s31-third.yaml
#   on the upgraded host with the plane charged: read what it admits and refuses; if the third
#   project now FITS, the rehearsal's manifest is re-read against the new numbers (a row), never forced
```

### Sheet K1 — the kit and the copies (Run 10)

```
sudo bin/dr-kit.sh export --host host.yaml --capabilities capabilities.yaml \
     --project project.alpha.yaml --project project.beta.yaml --project /home/op/control.yaml \
     --output /home/op/kit-<today>-s42
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/alpha-dev/outputs.json    /home/op/alpha-dev-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/beta-dev/outputs.json     /home/op/beta-dev-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/control-prod/outputs.json /home/op/control-prod-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/slot3-prod/outputs.json   /home/op/slot3-prod-outputs.json
```

### Sheet V1 — the whole host suite, writing nothing (Run 10; ~45-80 min)

```
sudo bash /home/op/s42-v1.sh       # -k "not after_reboot and not lifecycle" (D2448); X0 is the agent's, from WSL
```

### Sheet K2 — `slot6-prod`'s document, before its deletion (Run 11, at the lifecycle's pause)

```
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/slot6-prod/outputs.json /home/op/slot6-prod-outputs.json
```

### Sheet A1' — the registry after the lifecycle (Run 11)

```
sudo bin/control.sh registry                     # agrees x4, slot1/2/4/5/6 agrees (deleted); exit 0
```

### Sheet B1 — the reboot (Run 11)

```
sudo systemctl stop agentic-postgres-reconciler
sudo systemctl reboot
#   the agent then runs s42-after-reboot.sh (the six units AND agentic-postgres-telemetry, by
#   ActiveEnter vs multi-user.target) BEFORE any sweep (D2140); every one back BY ITSELF (D2558)
```

### Sheet S1 — the one sweep (Run 11)

```
sudo -v
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/alpha-dev/outputs.json    /home/op/alpha-dev-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/beta-dev/outputs.json     /home/op/beta-dev-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/control-prod/outputs.json /home/op/control-prod-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/slot3-prod/outputs.json   /home/op/slot3-prod-outputs.json
sudo bash /home/op/s42-launch.sh      # refuses while the reconciler is working; detaches s42-sweep.sh
```

### Sheet SL4 — `slot6-prod`'s identity revoked (Run 11, after the tag)

```
sudo bin/slot.sh revoke --host host.yaml --slot slot6-prod --operator-credential-file /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential --confirm slot6-prod
sudo shred -u /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo ls -la /root/.config/agentic-postgres/bootstrap/      # empty
sudo ls -la /etc/agentic-postgres/projects/                # no slot6-prod directory (D2405)
```

**If something goes wrong** (read Sessions 40's and 41's first, D977): a unit
that fails at U2's boot → read its journal through the operator (`sudo
journalctl -u <unit> -b --no-pager | tail -40`, filtered by nothing secret —
the edge's lines hold names) BEFORE starting it, and record Docker's text; a
deploy window that does not close → read `apg-diag containers` and the
project's doctor before anything else, never redeploy blind; the plane refused
at T1 (`exit 12`) → read `doctor capacity`: the plane's charge is its four
limits, and the limits came from E1 — the sizes are the question (§9); HyperDX
shows no line from a project → read that project's collector (`apg-diag logs
<key> metrics`, if the allowlist has it; else the operator's `docker logs
--tail 50 apg-<key>-metrics-1`) for the exporter's error before suspecting the
gateway; a WSL TLS blip during an `--wait` → the instrument awaits the
operation by id, never re-sends (D2502); an export that fails → read the
refusal's reason (now carrying the provider's code, D2564) and SL1b's shape
read before anything else; an idle sleep that never fires → read the slot's
samples through `GET …/usage` for a missing or unread figure (the designed
refusal, D2525) before suspecting the trigger.
