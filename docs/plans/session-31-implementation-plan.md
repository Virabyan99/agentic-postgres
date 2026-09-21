# Session 31 — The node as a finite resource

**Status: COMPLETE.** Planned 2026-09-19 at `ae2c0dc` (Session 30's close);
Runs 1–6 executed 2026-09-19; **Run 7, the trip, 2026-09-20 (the deploy) and
2026-09-21 (the second sweep, the merge and the tag)**; Run 8 closed
2026-09-21. Eight runs, all on `main` directly.

**`1.9.0` is deployed on both projects at `4344a1f`, swept, merged and
tagged**, in that order and on that commit (D1425, with D1641's one stated
exception). The merged evidence reads **145 claims: 139 passed, 5 not_run,
1 failed** — ten claims more than Session 30, and the ten new ones all passed.

**The divergence table is this document's point, and it holds 62 rows:**
twenty written at planning (D1582–D1601) and **forty-two measured during
execution** —

| Run | Rows | What they mostly are |
|---|---|---|
| 1 (the rigs) | D1602–D1609, eight | third-party behaviour measured with controls before anything was built on it |
| 3 | D1610–D1613, four | the admission decision's own shape |
| 4 | D1614, one | CI's three failures |
| 5 | D1615–D1622, eight | the carried-in items, and what repairing one revealed about another |
| 6 | D1623–D1629, seven | the bump, the registry, the gate |
| 7 (preparation) | D1630–D1632, three | sheets naming files and flags that were not there |
| 7 (the trip) | D1634–D1641, eight | what only a deployment could say |
| 8 (the close) | D1642–D1644, three | a kit naming the wrong release; a reading that refuses to infer; a close the plan called documentation |

**`D1633` was never issued.** It is a gap in the numbering and not a lost row;
recorded here so a later session does not go looking for it. **Next free:
D1645, ADR 0226.**

**Seven of this session's defects were the instrument rather than the
product**, and the product's own refusals diagnosed two of them in one line
each. That is the sentence this plan would most want a later reader to take:
every one was a value that looked measured and was not, and every one was
caught by running the check against the real thing instead of the expected
thing.
**Brief:** `docs/plans/stage-4-plan.md` §5 *Session 31* whole (Builds /
Already true / Must not / Measures / Closes), its rows **D1519** (keep the
collector and Prometheus, bound them, read them), **D1520** (capacity, admission,
`pids_limit`/`cpus`), **D1526** (`doctor usage`), **D1527** (`THR-NOISY-
NEIGHBOUR`), **D1535** (`doctor capacity` is a reading, not `apg tune`); §3's
ordering rule *31 before 32* (the worker is a seventh claimant and must be
charged against a declared capacity); §7's row for Session 31 (a reading and a
decision are two claims); §8 whole (the row *Admission refuses; a capacity
reading reports*); §9's stop conditions for 31; §11. Plus
`docs/scope-closure.md` §23 *What Session 31 inherits, in order* (seven items:
D1580, D1572, D1578, D1581, D1542, D1441's number, two stale facts), CLAUDE.md
§9 (the same items as rows), and `docs/plans/session-30-implementation-plan.md`
§10 (what 30 created for 31) and its Sheets A1–A4 (the trip's shape).
**Shape:** eight runs on `main` directly. Every run that changes code pushes
and reads that commit's CI verdict by full SHA; Run 8 is documentation only
and reads none.
**Product version at close:** `CURRENT_SESSION` **31**; `template_version`
**`1.9.0`** — `host.yaml` schema 3 (additive; schema 2 still validates),
`pids_limit` on every project service and `cpus` on the nine long-running
ones, one new command (`bin/admit.sh`), two new doctor readings, one new
rehearsal, one new exit code (12), the collector consumed for the first time;
**no migration, no outputs/capability/lock/secret schema move, no new
deployed-document field** (D1592). ADR 0162: `upgrade plan` will read the
change as `implementation` and require `patch`; the minor is chosen above that
floor by the stage rule (D1081, D1561), and a `major` is §9's stop.
**Written for whoever picks this up cold, and it will be a different model
than the one that planned it.** Every path below was read from the tree on
2026-09-19 at `ae2c0dc` by four explore passes over `src/`, `bin/`, `services/`,
`compose.yaml`, `schemas/`, `tests/` and `docs/`, and each is cited by
`path:line`. Every third-party claim is measured in Run 1's rigs with a control
or is marked as the measurement Run 1 owes — never assumed. **Read CLAUDE.md §1
in the launch folder before the first command, then this plan's §1, then the
appendix.** If a step here and the tree disagree, **the tree wins and the
disagreement is a divergence row** (next free `D` after §1's table), never a
silent reconciliation.

---

## 0. Where the session starts

```
HEAD            ae2c0dc on main, local = origin, clean. Deployed: be987cf
                (1.8.0) on both projects, seven documentation commits behind.
VERSION         1.8.0. CURRENT_SESSION 30. Outputs schema 18. host.yaml schema 2.
REGISTRY        228 requirements. 135 claims (19 declared offline). 220 ADRs.
                ID families: DEP CFG DBX SEC API AGT STO REC OPS DX REL CAP IDN
                EVAL FLEET TEN DEV EVD GEN STU (test_acceptance_registry.py:79).
                NEXT FREE: D1582, ADR 0221. This plan uses D1582-D1601 in §1.
                NEXT FREE AFTER THIS PLAN: D1602.
EVIDENCE        evidence/session-30.json: 135 claims, 128 passed, 5 not_run,
                2 failed (documented_path by decision; studio_tenant_read, the
                instrument this session repairs).
HOST            3814 MiB, no swap, 2 vCPU (docs/database.md:74; D52). host.yaml
                :13-14 records "38 G disk, 3.7 GiB RAM" AS A COMMENT, read by
                nothing. Kernel 7.0.0-31. 22 containers across two projects
                and the edge (D960). Measured anon 348/351 MB per project, edge
                31 MB, 1982 MB available of 3814 (D959, 2026-09-04).
```

**What exists, measured at `ae2c0dc`, and the session builds on:**

- **The memory budget is per project and compile-time.** `config.py:207-223`
  `DATABASE_BUDGET_DEFAULTS` (shared_buffers 128, max_connections 56,
  maintenance_work_mem 64, memory_limit 768, shm 256); `:615-628`
  `unreclaimable_mb(budget)` = shared_buffers + maintenance_work_mem +
  max_connections × `PER_BACKEND_ANON_MB` (2) = **304** at the defaults;
  `:612` `HOST_MEMORY_GUARDRAIL_MB = 1600`; `:1175-1207`
  `_validate_memory_budget` refuses a project whose unreclaimable exceeds the
  guardrail. **The guardrail is checked per project and never summed across
  projects.** `unreclaimable_mb` is published in the document on BOTH branches
  (`schemas/outputs.schema.json:695-716` rendered, `:754-776` deployed —
  `database.budget` is a required member of `database`).
- **`mem_limit` is on six services and no service has `pids_limit` or `cpus`.**
  `compose.yaml:180` postgres `${POSTGRES_MEMORY_LIMIT:?required}`, `:1153`
  auth, `:1450` storage, `:1582` mcp, and two literals `:965` metrics `128m`,
  `:1053` store `192m`. The values come from `rendering.build_compose_env`
  (`rendering.py:1668-1992`, the memory lines at `:1741`, `:1855-1857`, `:1885`,
  `:1901`) and every key is listed in `COMPOSE_ENV_KEYS` (`:625ff`). **The
  six caps sum to 2240 MiB per project, 4480 for two, against a 3814 MiB host
  — the caps are ceilings and were never a reservation (D767).** `pids_limit`,
  `cpus`, `cpu_quota`, `ulimits`, `nproc`: **0 hits** under `src/ bin/
  services/ compose.yaml infra/edge/compose.yaml deploy.sh tests/`. `compose.
  yaml` has **20 services** and no per-service render loop (§1 D1586).
- **Nothing reads the host.** `/proc/meminfo`, `shutil.disk_usage`,
  `os.statvfs`, `free`: 0 hits in `src/` and `bin/`. The only `df` is the
  doctor's, inside the postgres container (`bin/doctor.py:528`); the only
  cgroup read is the deploy's `memory.stat` inside the container
  (`bin/deploy-project.py:849-854`, parsed by `database_observation.
  parse_memory_stat:83-93`). Per-container `pids.current`/`pids.max`/`pids.
  peak` sit beside `memory.stat` under `/sys/fs/cgroup/system.slice/docker-*.
  scope/` and are **world-readable, read as `op` with no root** (D765).
- **`host.yaml` is schema 2 with a single-value enum.** `schemas/host.schema.
  json:10-14` `"enum": [2]` — *"both directions fail closed"*; loader
  `host_config.load_host_manifest:74-80`; **no host-manifest migrator exists**
  (the outputs document has `output_migrations.py`; the host manifest has an
  operator edit). `host.example.yaml` at the root is read by `tests/contract/
  test_host_manifest.py:29,433` and eleven other modules (§1 D1584).
- **The doctor is two files and four verdicts.** `bin/doctor.py` probes (root,
  live, *"nothing in it is testable behaviourally"*, `:1-14`) and
  `src/agentic_postgres/diagnosis.py` verdicts (pure). Eleven checks assembled
  imperatively at `bin/doctor.py:739-759`; verdicts `OK/WARN/PROBLEM/UNKNOWN`
  (`diagnosis.py:80-88`); `Check(name, verdict, detail, evidence)`
  (`:102-121`); text at `:597-616`, `--json` at `:619-650`; exit 0 for ok/warn,
  6 for problem/unknown (`:586-594`). `agent record` (`:527-578`) is the
  template for a reading with no threshold: **two outcomes, `OK` with numbers
  or `UNKNOWN` with the reason** (ADR 0213, D1441). The doctor takes
  `--project KEY` and no verb; `bin/apg.sh` holds no verb table (`:9-15`,
  `:136-151`) so `apg doctor capacity` reaches `bin/doctor.sh` with `capacity`
  as `$1`, which today falls to `usage >&2; exit 3` (`bin/doctor.sh:232`).
  `bin/doctor.py` and `bin/fleet.py` build `docker exec -i` argv by hand with
  `stdin=DEVNULL` (`bin/doctor.py:67-94`, `bin/fleet.py:63-78`) and do not
  call `container_exec` (§1 D1593).
- **Rehearsals.** `rehearsal.SCENARIOS` (`rehearsal.py:79-88`, eight names);
  `Facts` `:146-195`, `Action` `:198-220`, `Observation` `:223-234`, `Plan`
  `:237-246`; `_doctor(facts, *extra)` `:259-260`; planners `_PLANNERS`
  `:754-763`; `verdict()` `:884-959` **raises `RehearsalError` for a scenario
  with no arm**; `disk-threshold` (`:650-692`) is the model — *the reader is
  rehearsed by moving the threshold, never by filling the disk* (ADR 0190).
  `bin/rehearse.py`: `execute` `:272-302`, `observe` `:336-475` (the
  disk-threshold arm `:445-458`), parser `:727-736` (`scenario` positional,
  `--outputs`, `--plan`, `--evidence-dir`, `--state-root`, `--rendered-root`,
  `--registry`), exit codes `:58-62` (2, 3, 5 refused, 6 unread, 7 unreversed),
  the record `rehearsal.record:976-1005` written to
  `evidence/rehearsal-<key>-<scenario>-<id>.json` (`bin/rehearse.py:575-582`).
- **The collector and the store.** Both configs are **built in Python**, not
  files under `services/`: `rendering.build_otel_config(router_names, domain)`
  `:1211-1344` (receivers `otlp` 4317/4318 and a `prometheus` receiver scraping
  `apg-edge-proxy:8089` with a per-project keep-regex; processors
  `memory_limiter` 96 MiB + `batch`; exporter `prometheus` on 8889 with
  `metric_expiration: 60s`; written at `:2529-2541`) and
  `build_prometheus_config()` `:1347-1406` (*"It takes no project, and unlike
  `build_otel_config` it stays that way"*, one target `metrics:8889`,
  `honor_labels: true`, written `:2552-2556`). Constants in `runtime_override.
  py`: `OTEL_EXPORTER_PORT = 8889` `:228`, `OTEL_OTLP_GRPC_PORT = 4317` `:229`,
  `OTEL_OTLP_HTTP_PORT = 4318` `:230`, `STORE_SERVICE = "store"` `:261`,
  `STORE_PORT = 9090` `:262`, `STORE_MEMORY_LIMIT_MIB = 192` `:287`,
  `OTEL_MEMORY_LIMIT_MIB = 96` `:319`, `METRICS_MEMORY_LIMIT_MB = 128` `:326`.
  **Both are on `edge` only** (`compose.yaml:988-995`, `:1070-1081` — the store's
  block says *"ADR 0164 section 3 says 'the project's internal network', and
  this is a deliberate divergence"*). Retention is a bare literal
  `--storage.tsdb.retention.time=14d` at `compose.yaml:1022` with **no constant
  and no test** (`14d|retention.time`: 0 hits under `tests/ src/ bin/`).
  Traefik's metrics entrypoint `apgmetrics` on 8089 IS enabled and IS scraped
  (`infra/edge/traefik.yaml:29-70`; `host_config.EDGE_PROXY_ALIAS:135`,
  `EDGE_METRICS_PORT:148`). Images: `otel/opentelemetry-collector-contrib
  0.159.0` and `prom/prometheus v3.7.3` (`versions.env:17,21`).
- **The two instruments exist and nothing exports them.** `services/auth-api/
  app/mcp_metrics.py` (NOT under `src/`): `configure(*, endpoint, service_name,
  tool_names, outcomes) -> bool` `:114-176` (returns `False` and clears the
  instruments when `endpoint` is falsy; else an OTLP **http** exporter,
  `PeriodicExportingMetricReader` every `METRIC_EXPORT_INTERVAL_SECONDS` 15,
  counter `agent.tool_calls` and histogram `agent.tool_call.duration`);
  `METRIC_LABELS = ("outcome", "tool")` `:48-56`; the canary at `:205-207`
  raises on an undeclared label. `mcp_tracing.configure` `:166` carries the
  paragraph *"NOTHING IN THIS PRODUCT CALLS THIS, AND THAT IS A STANDING
  DECISION"* (`:177-202`, D1413/D1444) and `tests/contract/test_mcp_tracing.py:
  283-322` is a text scan that enumerates every module calling `configure(`.
  `MCP_VARIABLES` (`settings.py:439-455`) has no collector-endpoint variable;
  the mcp container's environment is `compose.yaml:1583-1633`; the mcp service
  is on `internal` AND `edge` (`:~1658`), so it reaches its own project's
  collector by the service name `metrics` and no other's. The insertion point
  is `mcp_runtime.create_mcp_app()` `:437-463`, after `lock = load_lock(...)`
  `:453` (the tool names come from the lock).
- **The deploy's preflight already has the three-outcome vocabulary.**
  `src/agentic_postgres/preflight.py` (`PRESENT/ABSENT/UNDETERMINED` `:46-48`,
  `KIND_PREREQUISITE/KIND_PRECONDITION` `:51-53`, `report` `:270`, `exit_kind`
  `:257`), consumed at `bin/deploy-project.py:482-556` and `:1970-1974`. Step
  0 is `:1963` and **the comment at `:1960-1962` is the admission check's
  insertion point**: *"everything above this line reads. The render below
  writes `.generated/<key>`"* (D614). Exit codes `:86-89` (`EXIT_INPUT 2`,
  `EXIT_PREREQUISITE 3`, `EXIT_PRECONDITION 4`, `EXIT_VALIDATION 5`); the
  repo-wide convention table is `docs/session-02-operator-guide.md:259-276`,
  codes 0–11, and its `:275-276` says a new code belongs in that table and not
  a second one. `tests/contract/test_cli_contract.py` pins **no** exit-code
  table; the header-documents-its-codes precedent is `tests/contract/
  test_dev_command.py:234`.
- **The evidence model.** Registry entry shape `tests/acceptance-registry.
  yaml:4091-4109`; `ID_PATTERN` `test_acceptance_registry.py:79`;
  `target_session <= CURRENT_SESSION` at `:163` (so every `target_session: 31`
  entry lands with the bump, D690); `CLAIMS` `evidence_claims.py:224-890`
  (Session 30's block `:370-387`), `OFFLINE_CLAIMS` `:106-177` (19 members);
  `CLAIM_INTRODUCED_IN` `tests/contract/test_evidence_claims.py:949-1105`;
  `ENVIRONMENT_VARIABLES` `tests/conftest.py:82-167` (26 names, closed);
  `KNOWN_UNREGISTERED` `tests/contract/test_deployment_suite_shape.py:116-150`
  (**22** node ids, compared for equality); the gate `bin/session-30-check.sh`
  (1669 lines; header `:1-229`, usage `:294-556`, flags `:571-747`, offline
  `:1201-1400`, host `:1467-1600`, external `:1615-1660`) and
  `tests/contract/test_session_thirty_gate_modes.py` (24 tests,
  `SESSION_PREVIOUS_NUMBER = 28` at `:80`).
- **The carried-in items, located.** D1572: `tests/deployment/test_session24_
  studio.py:689-788`, subjects created with `project_a["database"]["roles"]
  ["project_admin"]` at `:727` (and the `auditor` fixture at `:243-251`), the
  write at `:756-768` is `POST /rpc/create_note`, granted only to
  `{{authenticated}}, {{agent_writer}}` (`migrations/templates/0007-api-surface-
  convergence.sql:261-271`; `api_documentation` at `0009:33-34`) and never to
  `project_admin`. D1580: `jwt_keys.retire_rotation:464-492` (the early
  refusal `:480-485`, unreachable because `bin/deploy-project.py:2885-2890`
  sets `retire_after = None` when the rendered set holds one kid, and
  `FOLLOW_UP["promote"]` (`bin/rotate-signing-key.py:459-468`) tells the
  operator to clear the prepared key and redeploy). D1578: the only PEM
  delimiter check is `bin/bootstrap-providers.py:159-165` over the key the
  product generated; `bin/render-jwks.py:140-149` suppresses openssl's stderr
  by design; `value_kind` is an enum `["random_hex", "rsa_private_pem"]`
  (`schemas/secret-contract.schema.json:92-98`) whose only runtime reader is
  `secrets_contract.py:543-546` (the pgpass cross-check); `bin/materialize-
  secrets.py:219-235`'s loop never reads it. D1581: `runtime_override.
  mounted_paths_by_service:960-981` reads `services.*.volumes` of
  `runtime-compose.override.yaml`; the secret mounts are `secrets.<name>.file`
  in `secrets-compose.override.yaml` (`secret_override.py:56,93-137`).

---

## 1. The divergence table

Six columns. Each row is a **measured fact about the tree at `ae2c0dc`** set
against what the brief (the stage plan's §5 *Session 31*, its §1 rows, and
CLAUDE.md §9) says, with the decision this plan takes. **Next free number
after this table was D1602 at planning time; Run 1 measured eight more
(D1602-D1609, added 2026-09-19), Run 3 four more (D1610-D1613) and Run 4 one
(D1614), Run 5 eight (D1615-D1622) and Run 6 seven (D1623-D1629) and Run 7's
preparation three (D1630-D1632) and the trip's first deploy two
(D1634-D1637), the trip's first sweep two (D1638-D1639), its second two (D1640-D1641) and Run 8's cleanup, readings and close three (D1642-D1644), so the next free number is **D1645**. **`D1633` was never issued** -- a gap in the numbering, not a lost row.**

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D1582** | *"Publish Prometheus on a route (it stays unrouted; the doctor reads it over the internal network)"* — stage plan §5, Must not. | **The store is on `edge` only**, not `internal` (`compose.yaml:1070-1081`, a recorded divergence from ADR 0164 §3). The Session 14 proof reaches it **through the container**: `docker exec <store> wget -q -Y off -O - http://127.0.0.1:9090/api/v1/query?query=…` (`tests/deployment/test_session14_observability.py:234-261`); the image has `wget` and no shell (`compose.yaml:1062-1065`). | **The doctor reads the store the way the proof does**, through `container_exec.run(container, "wget", …)` on the container named `apg-<key>-store-1`, over 127.0.0.1 inside it. No network is added to the store; nothing is routed. | The store stays unrouted and joins no new network (ADR 0168, stage plan §9); the reader that already works is the one to copy (D1114: a proof calls the product's own path, and here the product's path is created from the proof's). | 0223 |
| **D1583** | D1520: *"`deploy` REFUSES a new project when the sum of every deployed project's `mem_limit`s plus this one's plus the reserve exceeds the declared memory"*. | **The `mem_limit`s of one project sum to 2240 MiB (768+384+384+384+128+192), 4480 for the two deployed, against 3814 MiB** — D767 measured in Session 14 that *"the caps in aggregate already exceed the machine's RAM, so they were never a reservation"*. A rule over `Σ mem_limit` refuses **today's own deployment**. What the schema computes and the document publishes as *what the host must actually find* is `database.budget.unreclaimable_mb` (`outputs.schema.json:918`), **304** per project at the defaults, checked per project against `HOST_MEMORY_GUARDRAIL_MB` 1600 and never summed. | **Admission charges the UNRECLAIMABLE claim, not the ceiling**: `Σ_deployed unreclaimable_mb (other projects) + candidate's unreclaimable_mb + reserve_memory_mb ≤ memory_mb`. `host.example.yaml` declares `memory_mb: 3814` and `reserve_memory_mb: 2214`, so `memory_mb − reserve_memory_mb == HOST_MEMORY_GUARDRAIL_MB`, asserted by a test — the guardrail becomes a host-level, cross-project number without moving. The reading reports `Σ mem_limit` on its own line as *ceilings, not reservations (D767)*. | A decision that refuses the deployment it is protecting is the stop condition §9 names; the reserve is where the sidecars' anon (D959: 348 MB measured against 304 claimed), the edge (31 MB) and the OS live. | 0221 |
| **D1584** | *"`host.yaml` schema 3 … migratable from schema 2 with defaults equal to today's prose"*. | **There is no host-manifest migration mechanism.** `schemas/host.schema.json:10-14` is `"enum": [2]` by design — *"both directions fail closed"* — and the outputs migrator chain (`output_migrations.py`) has no host counterpart. `host.yaml:13-14` carries the prose (*38 G disk, 3.7 GiB RAM*) as a comment nothing reads. | **The enum widens to `[2, 3]`; schema 3 REQUIRES a `capacity` object with four integer members (`memory_mb`, `reserve_memory_mb`, `disk_gb`, `reserve_disk_gb`), schema 2 stays valid and reports `capacity` absent.** No migrator. With no declaration, admission **refuses a project with no deployed document and admits a redeploy** (D1592) — so no operator action precedes the upgrade and the change is not `operator_manifest_invalidated`. `host.example.yaml` moves to schema 3 with the four numbers and their derivations in comments. The trip's Sheet A2 moves the host's `host.yaml` (op-owned, gitignored) with a backup copy first. | A default that is *measured at first read* is a reading standing in for a declaration — the exact fold ADR 0195 forbids; a declaration is typed by the operator or absent, and *absent* is reported. A required edit before an upgrade would price the release `major` (ADR 0162) for four numbers. | 0221 |
| **D1585** | *"exiting with a new code the CLI contract names"*. | `test_cli_contract.py` pins no exit-code table; the convention table is `docs/session-02-operator-guide.md:259-276` (0–11; 6 is *a host or gate check failed*, 10 is forbidden to new commands by `test_no_command_reports_an_unavailable_capability:815`) and each command's `# Exit codes` header (`deploy.sh:11-16`, `bin/deploy-project.py:86-89`). | **Exit code 12: *admission refused — the declared capacity cannot hold this project*.** A row in the convention table; `EXIT_ADMISSION_REFUSED = 12` in `capacity_reading.py`, imported by `bin/admit.py` and `bin/deploy-project.py`; the header blocks of `deploy.sh`, `bin/deploy-project.py`, `bin/admit.sh` and `bin/admit.py` name it; a test in `test_admission.py` reads the four headers for the literal (the `test_dev_command.py:234` shape). | An admission refusal is neither a precondition the operator creates (4) nor a check that failed (6): it is a decision against a declaration, and an operator reading `$?` must be able to tell the three apart. | 0221 |
| **D1586** | *"`pids_limit` and `cpus` on every service, defaults in `config.py` beside the memory defaults and rendered like `mem_limit`"*. | `compose.yaml` has **20 services** and **no per-service render loop**: four `mem_limit`s are `${…:?required}` interpolations and two are literals; eleven services are one-shots, probes or clients (`contract-probe`, `edge-probe`, `unlabeled-probe`, `secret-check`, `backup-mirror`, `dbmate`, `dbmate-project`, `client-psql`, `client-node-pg`, `client-psycopg`, `client-prisma`); the edge plane (`infra/edge/compose.yaml`) is shared, not a project's. | **The nine long-running services** (postgres, pgbouncer, postgrest, docs, metrics, store, auth, storage, mcp) get `pids_limit: ${<SERVICE>_PIDS_LIMIT:?required}` and `cpus: ${<SERVICE>_CPUS:?required}` from `config.SERVICE_RESOURCE_DEFAULTS` through `COMPOSE_ENV_KEYS` and `build_compose_env`; **the eleven short-lived services** get the literal `pids_limit: 64` (`config.SHORT_LIVED_PIDS_LIMIT`) and no `cpus`; **the edge plane is untouched** (§10). A contract test walks every service in `compose.yaml` and asserts the split by name. | Twenty hand edits are the tree's shape and a loop would be a second renderer (ADR 0133's argument in the other direction); a one-shot's `cpus` would throttle a migration nobody measured; recreating Traefik on a trip is its own act. | 0222 |
| **D1587** | `apg doctor capacity` and `apg doctor usage` as verbs; stage plan §7: *a capacity reading may report `unknown`*. | The doctor has **four** verdicts (`WARN` is an advisory tier, `diagnosis.py:16-22,80-88`), **no verb** (`--project KEY` is the mode switch, `bin/doctor.sh:243-245`), and `bin/doctor.py`'s parser is flat (`:763-780`); `bin/fleet.py:102-133` and `rehearsal._doctor:259-260` invoke `bin/doctor.py --project KEY --json` and must keep working. `bin/apg-diag.sh:60,355-374` is the verb-dispatch shape. | **`bin/doctor.sh capacity --host host.yaml [--project KEY] [--json]` and `bin/doctor.sh usage --project KEY [--json]`**: the shell maps the verb word to `bin/doctor.py --reading capacity|usage …`; with no verb the eleven checks run exactly as before. Both readings use **two outcomes only, `OK` with numbers or `UNKNOWN` with the reason** — `agent_record`'s shape — never `WARN`, never `PROBLEM`. `bin/doctor.sh` joins `COMMANDS_WITH_VERBS` (`test_cli_contract.py:413`). | A reading with a threshold in the one command that runs as root on production could fail a host that works (D1441); the verb is a word the dispatcher already passes through (`bin/apg.sh:266-269`), so nothing in `apg.sh` moves. | 0221 |
| **D1588** | *"`mcp_metrics.configure()` called from the service's startup so the two instruments exist"*; §8: *no span leaves a process*. | `mcp_metrics.py` and `mcp_tracing.py` live under `services/auth-api/app/`, not `src/`. `configure()` needs an `endpoint` and **no setting carries one** (`MCP_VARIABLES`, `settings.py:439-455`); `tests/contract/test_mcp_tracing.py:283-322` **enumerates the callers of `configure(`** and asserts the no-caller docstring; `mcp_tracing.py:177-202` says the standing decision is nobody's oversight. | **Metrics only.** A new `APG_OTLP_ENDPOINT` in `MCP_VARIABLES`, set in `compose.yaml`'s mcp environment to `http://metrics:4318/v1/metrics` (a test derives it from `METRICS_SERVICE` and `OTEL_OTLP_HTTP_PORT`); `create_mcp_app` calls `mcp_metrics.configure(...)` after `load_lock` with the lock's tool names and the telemetry outcome vocabulary; **`mcp_tracing.configure` stays uncalled** and its paragraph stays true. The scan test's expectation moves from *no module calls `configure(`* to *exactly `mcp_runtime` calls `mcp_metrics.configure` and nothing calls `mcp_tracing.configure`* — a contract test changed under ADR 0223. | D1519's decision was the two instruments in production with a reader; tracing has no reader and a span carries request-shaped values a metric does not. | 0223 |
| **D1589** | *"the 14 d retention asserted by a test rather than a flag nobody reads"*. | `--storage.tsdb.retention.time=14d` is a literal at `compose.yaml:1022` with no constant; the store's `mem_limit` literal has a constant and a test (`STORE_MEMORY_LIMIT_MIB`, `test_alert_rules.py:281-287`). | `runtime_override.STORE_RETENTION_DAYS = 14`; the literal stays; `test_alert_rules.py` gains `test_the_store_keeps_exactly_the_declared_retention` asserting the compose command carries `--storage.tsdb.retention.time={STORE_RETENTION_DAYS}d` and no second retention flag (`retention.size`). | The house pattern for a literal in compose is a constant beside it and a test that the two agree (D600: a declared value with no reader is unverified). | 0223 |
| **D1590** | *"a `project` label on every scraped series"*. | `build_prometheus_config()` takes no project **by its own docstring's decision** (`rendering.py:1348-1350`); Prometheus `external_labels` are attached on federation, remote write and alerts and **not** to locally queried series; every scraped series passes through the collector's `prometheus` exporter, which supports `const_labels`. | **`const_labels: {project: <key>}` on the collector's `prometheus` exporter**, so every series on the exposition surface — OTLP-pushed and edge-scraped alike — carries `project="<key>"`, the store scrapes it, and the metrics route serves it. `build_otel_config` gains a `project_key` parameter (it already takes the project's routers and domain); `build_prometheus_config()` stays parameterless. **Measured in rig 31c with a control before the code is written.** | The label's reader is `doctor usage`, which asserts every series it gets back names the project it asked (question 3 of CLAUDE.md §7: are we reading the right store); the collector is per project already, so the label costs one series-set no cardinality. | 0223 |
| **D1591** | Stage plan §7 item 3: *"Every new deployed-document field is classified in the isolation matrix in the session that adds it: 31's capacity"*. | Capacity is a **host** declaration in `host.yaml`; the per-project claim admission charges is `database.budget.unreclaimable_mb`, already on both branches of the document and already an `ISOLATED_FIELDS` pointer's neighbour (`test_render_isolation.py:137`). | **No deployed-document field is added; outputs stays v18; the matrix is unchanged.** The stage plan's expectation is recorded as unmet for a reason: there is nothing per-project to classify. | A field added so that a matrix row can be written is D816's shape (a declared field with no reader). | — |
| **D1592** | *"`deploy.sh` for a project whose document does not yet exist refuses when …"*. | A new project is distinguished from a redeploy only by the presence of `/etc/agentic-postgres/projects/<key>/outputs.json` (`bin/deploy-project.py:1852-1858`, `:2838-2839`); a redeploy can raise `shared_buffers_mb` and move the same sum; a rehearsal needs a deployed subject (`rehearse.py` takes `--outputs`). | **Admission runs on EVERY deploy, at step 0, with the candidate's own key excluded from the committed sum.** A new project charges its manifest's claim against the others; a redeploy charges its new claim against the others. With no declaration: a new project is refused, a redeploy admitted (D1584). A refusal at step 0 changes nothing on the host (`:1960-1962`). | A raised budget is the same decision as a new project; the stage plan's stop condition *"admission would degrade a running project instead of refusing a new one"* is honoured because a refused redeploy leaves the running project running. | 0221 |
| **D1593** | CLAUDE.md §2: *"Every container exec in `bin/` and `src/` goes through `container_exec` … the AST scan reads 0 unguarded sites."* | `bin/doctor.py:67-94` and `bin/fleet.py:63-78` build `docker exec -i …` argv by hand with `stdin=subprocess.DEVNULL` (D673). The scan (`test_container_exec.py::test_the_scan_finds_no_docker_or_compose_subprocess_outside_the_helper`) guards **inherited stdin**, which these do not have, so they pass it. The sentence overstates: the CLASS is guarded at 0; the HELPER has callers it does not have. | **Every probe this session adds to `bin/doctor.py` calls `container_exec.run`** (the rule for new code); the existing hand-built sites are left where they are and named here. CLAUDE.md's sentence is corrected in Run 8's handoff. | Rewriting eleven working probes to make a sentence true is the shape this project refuses (D1564's second half); a new probe has no reason not to use the helper. | — |
| **D1594** | CLAUDE.md §9: *"an operator can write a sentinel row and cannot remove one … Session 31's, if the claim is to be routine."* | `bin/api.py:49-60` `OPERATIONS` is a closed set of six with no `delete-*`; `api.create_note` is a reviewed RPC granted by migration 0007; a `delete_note` RPC is a migration plus an `api` contract move plus a client regeneration (`apg generate`, ADR 0204). | **Not built here.** `deployment_convergence` is re-taken on this trip with the Sheet A2 recipe from Session 30 (it worked), and the sentinel is removed by the root line on Sheet A6. A `delete_note` operation belongs to a session that moves the `api` contract anyway (32 adds the worker's functions; 34 adds `emit_event`). | A migration written so a sheet loses one line is a contract move nobody reviewed; the claim IS routine now that the recipe is written. | — |
| **D1595** | The tree's own prose. | Five stale statements: `tests/contract/test_cli_contract.py:161` says 30's offline mode reports *FOUR* claims (five); `evidence_claims.py:370-371` and `tests/contract/test_evidence_claims.py:1096` say *five claims, four offline* (six, five); `runtime_override.py:42`'s D587 comment names six services carrying `apg.project.key` where eight do (scope-closure §23 item 7); `APG_ADMIN_PASSWORD_FILE` is exported by `bin/session-30-check.sh:1502` and is **absent from `tests/conftest.py`'s closed `ENVIRONMENT_VARIABLES`** — D687's shape in the other direction (a variable the gate exports that no proof gates on, or one a proof reads by `os.environ` outside the roster). | Run 5 corrects the four comments and **measures the fifth**: `git grep -n APG_ADMIN_PASSWORD_FILE -- tests/` — if any proof reads it, it joins the tuple with a `requires_environment` mark; if none does, the gate's export line gains a comment saying which fixture consumes it or is deleted, and the row says which. | The direction nobody chases (D954), and the roster is the one place a gate variable is allowed to be closed. | — |
| **D1596** | *"or the disk equivalent"* of the memory sum. | No per-project **disk** declaration exists anywhere: the manifest has no disk field, the document's `disk` reading is the doctor's copies-of-PGDATA rule (`diagnosis.disk_headroom:388-434`), and a candidate's PGDATA is unknown before it runs. | **Disk admission is a FLOOR, not a sum**: refused when `free_gb at the Docker root − reserve_disk_gb < 0`, i.e. the operator's declared reserve is what a new project may not eat into. `disk_gb` is declared for the reading to compare against `df`'s total (a declaration that disagrees with the measurement by more than 5 % is reported as such, not refused). | A number for a candidate's disk would be invented (D267); a floor is a decision the operator can state. | 0221 |
| **D1597** | CLAUDE.md §9: *"22 orphaned deployment proofs … Session 31 triages."* | `KNOWN_UNREGISTERED` holds 22 node ids clustered 5× `test_session2_host.py`, 5× `test_session2_isolation.py`, 4× `test_session2_edge.py`, 3× `test_session9_agent_writes.py`, 1 each in modules 8, 11, 12, 14, 20 (`test_deployment_suite_shape.py:116-150`); no per-id comment names an owner. Other proofs in each of those modules ARE registered, so the requirement families exist. | **Triage by the rule in Run 5, item 6**: each orphan is attached as a node id to the EXISTING requirement whose description already states the property it proves (the requirement's description gains at most one sentence), or, when no requirement states it, gets a new requirement in the module's family. A proof that proves nothing a requirement should state is deleted with the reason. The tuple ends **empty** or names each survivor with the owning session. The count of each outcome is in the Done. | Attaching a proof to the requirement it establishes makes an existing claim stricter, which CLAUDE.md §6 permits; a new requirement per orphan would be the *list made shorter* the docstring warns against. | — |
| **D1598** | CLAUDE.md §9: *"Nothing validates an operator-supplied PEM … A `value_kind: rsa_private_pem` checked at materialization."* | `value_kind` is declared on every secret (`secrets.required.yaml:392,530,564` are `rsa_private_pem`) and has **one** runtime reader, the pgpass cross-check (`secrets_contract.py:543-546`); `bin/materialize-secrets.py:219-235` writes whatever the provider returns. | `secrets_contract.check_value_kind(kind, value) -> str | None` — a reason that **names no byte of the value** — called in the materialize loop before the write; `rsa_private_pem` requires both PKCS#8 delimiters and a body of at least 1,000 characters; `random_hex` requires lowercase hex. A failing check exits 8 (*a secret could not be fetched or written*) naming the secret's NAME and the kind. The *mistyped name vs deliberately absent* half is **not** built (§10). | The check belongs where the value first lands on disk; `render-jwks` cannot say why it failed without printing the path, and the bootstrap check only ever sees the product's own key. | 0225 |
| **D1599** | CLAUDE.md §9: *"An ADR is owed for a refusal that cannot fire … Session 31, ADR before code."* | Step 6 of the rotation (the `promote` follow-up, `bin/rotate-signing-key.py:459-468`) clears the prepared key and redeploys; the deploy's `observe_jwt` sets `retire_after = None` when the rendered set holds one kid (`bin/deploy-project.py:2885-2890`); `retire_rotation` then refuses with *no rotation is in flight* (`jwt_keys.py:476-477`) and the early refusal `:480-485` is unreachable. **The overlap window therefore closes at step 6's deploy**, measured on both projects (D1580, D1581). | **ADR 0224: the window is closed by the operator's step-6 deploy, and `retire` records that it was.** The operator guide §15 and Appendix R's step 6 are rewritten so that the deploy is taken **only after `retire_after` has passed** (the sheet reads the document's `retire_after` and waits); `FOLLOW_UP["promote"]` says so; `retire_rotation` with `retire_after is None` and one published kid **reports** *retired by the deploy that published one key* (exit 0) instead of refusing; the early refusal stays for a document a future deploy could write and keeps its test. Whether `render-jwks` should read `verification_kids` so the deploy carries the retiring key is **§10's item for the session that performs the other three rotations**. | Reordering a sheet costs nothing and makes the refusal's premise true; rewriting `render-jwks` in a credential path is a rig and a rotation to prove it, and this session has neither. | 0224 |
| **D1600** | *"`pids_limit` on the auth container measured by forking past it in a throwaway container"*; defaults *"in `config.py`"*. | No number for any service's process count exists. Per-container `pids.current` and `pids.max` (and `pids.peak` on this kernel — Run 1 reads whether the file exists) are world-readable on the host as `op` (D765's method). | **Run 1 reads `pids.current`/`pids.peak` for all 22 containers as `op` over SSH, no root**; each service's default is **the larger of 64 and four times its measured peak, rounded up to a power of two**; postgres's default is additionally at least `max_connections + 32`. `cpus`: postgres `"2.0"` (the host's count; a bigger host does not silently give it more), every other long-running service `"1.0"` (no sidecar may take both cores). The provisional numbers in Run 3 are replaced by the reading and the Done prints both. | A limit typed from a guess is the class §7 names; a limit four times a measured peak stops a fork storm without touching a working service. | 0222 |
| **D1601** | D1526: `doctor usage` reads *"storage object count from the existing listing"*. | The listing is the storage service's own S3 list through the credential only the storage container holds (`storage_cleanup.py:166-255`); no other process reaches the bucket, and *one service cannot read another's credential* is an invariant (stage plan §8). | **`storage_objects` is NOT a member of the usage reading.** The seven that are: database bytes (`pg_database_size`), PGDATA KiB, `pg_wal` KiB, the backup repository's bytes (a new `repository_bytes` member of `backup_report.summarise`, summed from each backup's `info.repository.delta`), audit rows, idempotency claims, request count and agent tool-call count from the store. A count route on the storage service is Session 34's if a reader wants it. | A member reported `unknown` forever is a field with no reader (D816); a second holder of the bucket credential is the stage's failure mode. | 0221 |
| **D1602** | §0: *"`pids_limit`, `cpus`, `cpu_quota`, `ulimits`, `nproc`: **0 hits**"*; D1600: *"No number for any service's process count exists."* Both read as *nothing bounds a container's processes*. | **Measured, rig 31b (host, as `op`, no root): every one of the 22 scopes reads `pids.max = 3647`** — systemd's `DefaultTasksMax` (`systemctl show -p DefaultTasksMax` = 3647; `docker.service` and `containerd.service` are both `TasksMax=infinity`; `kernel.pid_max` = 4194304). The compose files set nothing, and the containers are still bounded. | **The session NARROWS an existing ceiling nobody chose for these services, rather than creating the first one.** ADR 0222 says so in its Context; the numbers and the decision are unchanged. | A premise wrong in the reassuring direction survives longest (D930, D957) — and this one is wrong in the *alarming* direction, which would have made the ADR overstate what it achieves. The honest claim is 3647 → 128/64, not ∞ → 128/64. | 0222 |
| **D1603** | Run 1's rig 31a text: *"`unlimited` reaches 20 sleeps … and `PidsLimit` is `0`"*. | **`docker inspect --format '{{.HostConfig.PidsLimit}}'` prints `<nil>`, not `0`**, when no limit is set (Docker 29.5.2; the field is a nil `*int64`). Everything else the rig predicted held: `pids.max` reads `max`, all 20 sleeps spawn, `pids.current` 23. | Any proof that reads `HostConfig.PidsLimit` asserts on **the absence of a number**, not on `0`. The offline fork proof asserts the cgroup file and the fork-failure text instead, which are stable across Docker versions. | A test written to the plan's literal would have failed on first execution — the fifteenth instance of §7 question 2. | 0222 |
| **D1604** | D1590: *"Expect every non-`#` line of the subject's exposition to carry `project=\"rig31c\"` — **including `target_info`**."* | **False, measured three ways in rig 31c.** With `const_labels` and a `prometheus` receiver scraping a separate target (the production shape), **six of seven series carry the label and `target_info` does not**: `up`, `scrape_duration_seconds`, `scrape_samples_scraped`, `scrape_samples_post_metric_relabeling` and `scrape_series_added` all carry it. `target_info` is synthesised by the exporter from the resource and `const_labels` are not applied to it. The control without the option carried nothing on any line. | **`target_info` is a named exception in the contract test**, asserted as an exception (`target_info` carries no `project`), never folded into *every series*. `doctor usage`'s check that every series names its project excludes `target_info` by name and says why. | Folding a measured exception into a universal claim is the reassuring-direction premise §7 warns about; naming it costs one assertion and keeps the claim true. | 0223 |
| **D1605** | Nothing in the brief. | **A scraped series that already carries a `project` label is DROPPED by the exporter**, silently on the exposition surface: rig 31c's self-scraping arm logged `failed to convert metric up: duplicate label names in constant and variable labels for metric "up"` and the series vanished. Only the collector's log says why. Traefik's metrics (`apgmetrics` on 8089) carry no `project` label today, so the decision is safe. | **ADR 0223 names the hazard** and the offline proof covers it: a scrape target that emits `project` loses those series. The keep-regex the collector already applies is what bounds which of the edge's series arrive at all. | A silent drop whose only evidence is a container log is the class §7 exists for; it is cheap to know about now and expensive to discover on a trip. | 0223 |
| **D1606** | §1 D1592 and §4 assume admission can read *"every deployed project's"* document; Sheet A2 is `op`, and only A5 is `sudo`. | **`/etc/agentic-postgres/projects/<key>/` is `drwx------ root root`** (measured on both projects as `op`): `op` **cannot read a deployed document at all** — `Permission denied` on `outputs.json`. The op-owned copies at `/home/op/<key>-dev-outputs.json` are a reading aid and are stale (D1575), so they are not a substitute. | **The committed sum is root-readable only.** `bin/admit.sh` and `doctor capacity` are **root** commands; an unprivileged run reports the committed figure `unknown` and **fails closed** rather than summing zero. Sheet A5 stays `sudo`; no sheet may run `admit.sh` as `op`. | A reader that quietly summed zero deployed projects would admit everything — the decision that looks measured and is not. ADR 0195's third outcome is the whole defence here. | 0221 |
| **D1607** | §4: *"a failing export is logged by the SDK and never raises into a tool call (the SDK's reader runs on its own thread — rig 31d confirms with the collector stopped)"*. | **Confirmed, and it costs the process its exit.** Rig 31d: nothing raised, exit 0 — but the container's wall clock went from **1 s** (collector reachable) to **18 s** (name does not resolve) and **11 s** (connect succeeds, read times out at the exporter's 10 s default). **mcp's `stop_grace_period` is 15s**, so a stop while the collector is down is a **SIGKILL**. | **Run 4 sets the OTLP exporter's timeout explicitly and raises mcp's `stop_grace_period` above the worst case**, with a proof. ADR 0223 §3 records the requirement. | The rig answered what it owed and found the thing beside it; a deploy that SIGKILLs mcp on every collector outage would have looked like an unrelated flake for sessions. | 0223 |
| **D1608** | Run 1's rig 31e text and §4: the third manifest's budget is *"`shared_buffers_mb: 896`"*, one member. | **Three members must move, measured against `config._validate_memory_budget` itself.** `shared_buffers_mb: 896` alone is refused for `shm_size_mb` (256 < 896); with `shm_size_mb: 896` it is refused again for `memory_limit_mb` (768 ≤ 1072). Only `{shared_buffers_mb: 896, shm_size_mb: 896, memory_limit_mb: 1280}` is **ACCEPTED** per project — and its `unreclaimable_mb` is **1072**, against a safe available of **992**. | **Sheet A5's third manifest declares all three.** The control is exactly this: the per-project guardrail accepts it, so the live refusal is the cross-project decision (D1583) and nothing else. | A candidate refused by the per-project validator would have produced a green-looking refusal that proved the opposite of the claim — a proof that passes for the wrong reason. | 0221 |
| **D1609** | `mcp_metrics.configure`'s docstring: *"every resource attribute is served verbatim on the exposition surface as a label of a synthesised `target_info` series"*. | **Partially superseded, measured in rig 31d.** The prometheus exporter promotes `service.name` → `job` and the SDK's auto-generated `service.instance.id` → `instance` onto **every series**, not only onto `target_info`. `instance` is a fresh UUID per process, so **each mcp restart mints a new series set**, bounded only by `metric_expiration: 60s`. | **`doctor usage` aggregates across `instance`** rather than reading one series, and says so. The docstring gains the measured correction in Run 4. | A counter read from one `instance` would silently undercount after any restart — a cumulative counter answering a point-in-time question in a new disguise (D553). | 0223 |
| **D1610** | Run 3 §5.2: *"the probe's three `docker` reads are **re-spelled in `deploy-project.py`** through its own `run()` … one parser, two probes"*. | **Three commands need the reading, not two**: `doctor capacity` reports it, `bin/admit.py` decides on it, and the deploy decides on it at step 0. ADR 0093 bars a `bin/`-to-`bin/` import, so the plan's shape is three copies of six probes. §7 question 5 is exactly this: a repair to the ceiling parser that reached the doctor and not the deploy is invisible until a deploy admits what the doctor refused. | **One probe in the library — `src/agentic_postgres/capacity_probe.py` — and each command passes ITS OWN runner.** The runner is the part that genuinely differs: `bin/doctor.py`'s is bounded with `stdin=DEVNULL` (D673), `bin/admit.py`'s the same, and the deploy's general `run()` **has no timeout at all**, so step 0 got a bounded `_probe_run` rather than borrowing it. `container_exec` is the precedent for a subprocess-running module under `src/`. | The doctor/deploy split ADR 0157 draws is about *who decides what*, not about who may parse a number; duplicating the parse to honour it would trade a real invariant for a spelling. | 0221 |
| **D1611** | §2 `NODE-ADMIT-001`: *"an undetermined reading refuses (fails closed) naming the figure"*, applied to the disk figure read with `shutil.disk_usage(docker_root)`. | **The disk figure is undeterminable unprivileged, so the rule was unsatisfiable.** `/var/lib/docker` **does not exist** on this workstation — Docker Desktop's daemon reports a path inside its own VM, and `disk_usage` raises `FileNotFoundError`; on a CI runner the same path is 0710 root and it raises `PermissionError`. `decide` then refused EVERY admission for a reason with nothing to do with capacity. Measured: `/var/lib`, `/var` and `/` all stat cleanly and share `st_dev` with the checkout. | **`capacity_probe.disk_usage_near` measures the same filesystem from the deepest readable ancestor and REPORTS the path it measured** (`Reading.docker_root_measured_at`, printed as a `disk measured at` line). `statvfs` answers identically from any point on one filesystem; where the Docker root is its own mount an ancestor would describe a different disk, and then an operator reads the path rather than a plausible number. | A rule nothing can satisfy is not a rule — and this one would have been discovered on the host, mid-trip, with every deploy refused. Reporting the measured path is ADR 0195's move; substituting a number would have been the fold. | 0221 |
| **D1612** | §5.4: the `admission-refused` record's *"`induced: false`"*. | **In the tree `induced=False` means *recorded, not exercised*.** `provider-loss` is its only member and `verdict()` returns the literal `"recorded"` for it (D976). **`disk-threshold` changes nothing either** — it injects a threshold into the doctor's argv — and is `induced=True`, because it exercises the reader. `test_every_scenario_plans_three_phases_and_prints_every_command` asserts `(plan.induced is False) == (scenario == "provider-loss")`. | **`admission-refused` keeps `induced=True`**, disk-threshold's flag, because it is disk-threshold's shape exactly: a threshold injected into a reader's argv, nothing changed, nothing to undo. The existing parametrised assertion stands unedited. | Marking it False would have put it in provider-loss's class, whose verdict is `"recorded"` rather than `"read"` — quietly downgrading what the rehearsal claims to have proved, which is the opposite of what a rehearsal is for. | 0190 |
| **D1613** | §5.5: *"If `dev_environment.py` carries a `mem_limit`, it carries `pids_limit` from the same default"*; §2 `NODE-LIMIT-001`: *"`apg dev`'s cluster definition carries the same `pids_limit` if it carries a `mem_limit`"*. | **It carries no memory limit at all.** `dev_environment.run_arguments` is a deliberately minimal `docker run` whose docstring says *"Nothing is in this list by accident"*: no `--network`, no `-v`, no `-c`, one `-p`, and no `--memory`. `grep mem_limit src/ bin/` finds it in no cluster definition. | **Nothing is added to the dev cluster**, and the proof is written as the INVARIANT the conditional states — if that argv ever bounds memory, it bounds processes in the same change — rather than deleted for being vacuously true. | A `--pids-limit` there would be the first resource cap on a developer's throwaway cluster and one nobody asked for. Keeping the test as an invariant is what catches the person who bounds its memory later, who is exactly the person who will not think about its processes. | 0222 |
| **D1614** | Run 4 §5.4: *"the repository through `bin/backup.sh --outputs … info --json` exactly as `probe_repository` does, reading the new `repository_bytes` member that `backup_report.summarise` gains"*. | **`info --json` is not a report -- it is the deployed document's `backup_state` block**, and `bin/deploy-project.py:1390` consumes exactly it: *"`summary` here is what `bin/backup.sh info --json` printed, and that command prints an already-computed state block"*. A member added there travels into `outputs.json` and is refused by the outputs schema -- a schema move this session explicitly does not take (D1591). | **`summarise` gains `repository_bytes` as planned, and a NEW VERB serves it**: `bin/backup.sh usage [--json]`. The published block stays byte-for-byte what it was, and a proof asserts `backup_state` does not carry the member. `doctor usage` calls the new verb. | The figure genuinely belongs to the command that holds the backup credential; what it cannot do is ride along on the one output whose whole contract is *this is the document*. A new verb is reviewable; a widened document is a schema bump nobody planned. | 0221 |
| **D1615** | Run 5 §5.2: *"a reason → `OperatorError(8, f"{secret['name']}: {reason}")` (the module's error class and exit-8 constant -- read `:1-60`)"*. | `bin/materialize-secrets.py` has no `OperatorError`. Its class is `MaterializeError` and **nothing raises it in the fetch loop**: every failure goes through `fail(code, message)` (`:57-60`), which prints `materialize-secrets: <message>` to stderr and raises `SystemExit(code)`. The exit-8 constant is `EXIT_SECRET`. The plan told the executor to read `:1-60` for exactly this reason. | The tree's own shape: `fail(EXIT_SECRET, f"{secret['name']}: {reason}")`, one line below the `could not read {name}` failure it sits beside. No new error class. | A second way to fail in a forty-line loop is a second message format an operator has to recognise, and the one already there is the one this failure is a sibling of. | 0225 |
| **D1616** | Run 5 §2: *"`test_materialize_secrets.py::test_the_loop_checks_the_kind_before_it_writes` (an AST/text scan: `check_value_kind` precedes the write in the loop)"*. | There is no `test_materialize_secrets.py` (the plan anticipated this and named the grep). And the scan's premise is wrong: `bin/materialize-secrets.py` holds **two** `for secret in active_secrets(...)` loops, at `:145` and `:223`. The first is `plan()`'s -- it prints what would be written, contacts no provider and **holds no value**, so it has nothing to check a kind against. | The proofs land in **`tests/contract/test_optional_secrets.py`**, which is the module that already scans this loop for a declared field it did not read (D276/D283 -- the same defect class, in the same file). `_fetch_loop()` selects the loop **by the presence of a `write_secret_file` call** and asserts exactly one loop has one, rather than by position. | A scan that picks its subject by position picks the wrong one eventually, and this one had a 50% chance on the day it was written. Picking it by what it does is also what the scan is about. | 0225 |
| **D1617** | ADR 0224's decision 3: with the three conditions met, `retire` *"**reports** retired by the deploy that published one key"*. | **The document cannot support that sentence.** `bin/deploy-project.py:2963-2964` writes BOTH `retire_after` and `verifier_acknowledgements` as null whenever the rendered key set holds one kid -- which is member-for-member the state `jwt_keys.initial_key_state` gives a project that has **never rotated at all**. Measured against both op-owned document copies and asserted by a new proof. A completed rotation and a virgin project are indistinguishable here. | The ARM is implemented exactly as decided -- the answer is the same for both histories, because there is nothing to retire either way. **The sentence is not.** It reads *nothing to retire: one key is published, no deadline is set, and no verifier acknowledgement is outstanding*, then says that if a rotation was just completed the deploy is what closed the window, then says the document cannot tell the two apart. ADR 0225's amendment records the same kind of correction. | ADR 0195 applied to the ADR that cites it: the refusal was replaced because it said something false to an operator, and a report that claimed a rotation had happened would be the same defect facing the other way. | 0224 |
| **D1618** | ADR 0225, *Alternatives considered*: *"The delimiter-and-length pair catches every malformation actually observed."* | **Measured against the four shapes of 2026-09-19: it catches ONE.** The body pasted without delimiters is refused. The delimiters JOINED to the body (1701 bytes, longest line 91) is **accepted** -- `in value` is a substring test and a joined boundary is still a substring -- and that is precisely the malformation that reaches `bin/render-jwks` mid-deploy, where openssl's stderr is suppressed by design. The byte-identical re-read is a well-formed key. The mistyped provider key NAME never reaches the function at all. | The rule is **stricter than decided**: each delimiter must be an encapsulation boundary **on a line of its own** (RFC 7468, and what `openssl rsa` enforces), which takes it to two of four. The body's wrapping is deliberately NOT constrained -- a key wrapped at 76 rather than 64 is legitimate and a false refusal mid-window is the worst moment for one. ADR 0225 gains an **Amendment** section carrying the four-row table and naming the two that are out of reach of any check of this kind. | A claim about four measured shapes is cheap to test and was not tested. Two of the four are staleness and a naming mistake, neither of which is a question about a value's shape, and saying so is better than a check that implies it covers the class. | 0225 |
| **D1619** | D1595's fifth statement: *"if any proof reads it, it joins the tuple with a `requires_environment` mark"* for `APG_ADMIN_PASSWORD_FILE`. | **It cannot join the tuple.** `test_every_registered_variable_is_used` calls an entry used when a test module declares it on a marker or names it as an `ast.Constant`, and `all_test_modules()` is `TESTS_ROOT.rglob("test_*.py")` -- **conftests are not walked**. The only AST constant naming this variable is `tests/deployment/conftest.py:1230`. Adding it to the roster reads as unused on the day it is added. D1278 had already decided it stays out. What IS wrong is the gates' own prose: `bin/session-30-check.sh:1522` says it is *"in the roster and exported here"*, and seven gates carry that sentence. | The plan's second branch: the export line gains a comment naming the **fixture** that consumes it (`admin_password`, which SKIPS with the variable's name), why it cannot join the roster, and what widening `all_test_modules()` would cost. The false sentence in `session-30-check.sh` is corrected; §10 carries the scan-widening question. The roster is untouched. | The direction nobody chases (D954), found in the reassuring direction: a reader checking whether the variable was covered would have read that it was. | -- |
| **D1620** | D1595's fourth: `runtime_override.py:42`'s comment *"names six services carrying `apg.project.key` where eight do (scope-closure §23 item 7)"*. | **Nine do**, measured from `compose.yaml` at Session 30's close commit `ae2c0dc` and at this one: `auth`, `backup-mirror`, `docs`, `edge-probe`, `mcp`, `metrics`, `postgrest`, `storage`, `store`. The comment said six and the plan said eight. The three the comment omits -- `metrics`, `store`, `backup-mirror` -- are also the three that are **not edge-facing**, so the sentence was teaching the wrong shape as well as the wrong number. | The comment names all nine, marks which six are edge-facing, and says the count was measured and by whom it was got wrong twice. The property the comment exists for -- that `postgres` does NOT carry the label, which is the whole of D587 -- is unchanged. | A count stated in prose is a count that was right once; a count restated from a stale source is the same error with a citation. | -- |
| **D1621** | Run 5 §5.5: *"`test_acceptance_registry` checks the row's referential integrity, so this lands green only in Run 6 with the entries -- write it now, run the registry test in Run 6."* | Written and **measured**: `test_threat_model_requirement_ids_exist_in_the_registry` fails naming both IDs, and CI is the full check read per commit. Landing the row in Run 5 pushes a **red `main`** and keeps it red until Run 6 -- which is the state this session has just spent a commit getting out of. | `THR-NOISY-NEIGHBOUR` is **reverted from Run 5 and lands in Run 6** beside `NODE-LIMIT-001` and `NODE-ADMIT-001`. Nothing is lost: the row's full text is in Run 5's **Done**, ready to paste. | The plan's instruction and the project's own rule about CI are in conflict, and the rule wins for the cheaper reason: the row costs nothing to move and a red `main` across two runs costs a verdict nobody can read. | -- |
| **D1622** | Run 5 §5.6: *"When the proof proves nothing a requirement should state (the run expects this for `test_the_classifier_can_tell_the_categories_apart` if it is a self-test of a test helper -- read it), delete it and say why."* | Read: it is the anti-vacuity control for `_classify`, which drives the other three proofs of `DEP-ISO-001`'s isolation matrix. A classifier returning `not_authority` for everything would make the matrix *report a clean bill of health forever* and `test_every_leaf_is_classified` *pass most loudly of all* (D374). **Deleting it removes the only thing that makes the other three mean anything.** | **Registered under `DEP-ISO-001`, not deleted**, with one sentence added to that requirement. A control belongs to the claim it protects: if it fails, the matrix is unmeasured and the claim should say so. Of the twenty-two, twenty went to requirements that already stated their property; the two that stay are ADR 0136's category (a writing rpc is ineffective over GET), which no entry states -- they need a new `target_session: 31` entry and that is Run 6's (D690). | *A requirement written to make a list shorter is a requirement nobody reviewed* -- and so is a deletion taken to make one shorter. The count was never twenty-two unstated properties; it was twenty-two proofs nothing had connected to the requirement they were written for. | -- |
| **D1623** | Run 6 §5: the eight live proofs, among them *"the `free -m` / `df -Pk` controls are the proof's own reads on the host (root), compared within 5 % for MemTotal and exactly for the Docker root's total KiB"*. | **`df` has to be pointed at a path, and `apg doctor capacity` did not report one.** `decide` prints `disk measured at <path>` because the probe walks up from the Docker data root to the nearest point it can stat (D1611) and an ancestor can be a different mount -- but `diagnosis.capacity_report` reported the same two figures and named no subject, so the READING handed an operator a number they had no way to check. The only alternative for the control was hardcoding `/var/lib/docker`, which is the assumption D1611 removed from the product. | `capacity_report`'s `disk` check gains `measured_at` in its evidence, empty-path excluded (a path invented for a reading that measured nothing would be worse than none). One offline proof for both arms; the live control points `df` at whatever the reading printed. | Found by writing the control, which is the only reason it was found at all: every offline proof feeds the reporter a `Reading` it built, and a reader who already knows which path was measured never notices that the report does not say. | 0221 |
| **D1624** | Run 6 §5, the price: *"render `project.example.yaml` from `be987cf` in a throwaway worktree `/tmp/apg-be987cf` (D1485: never the checkout's own `.generated/fixture-alpha-dev`) and from the bump commit"*. | **`project.example.yaml` renders AS `fixture-alpha-dev`** (`project.name: fixture_alpha_dev`). The parenthesis warns about the installed side and the candidate side has the same problem: rendering it in the checkout overwrites one of the four renders the gate compares for collisions (D1507), and CLAUDE.md's rule is that anything calling `render_project` must delete what it published. | **Neither side renders in the checkout.** The installed side is a git worktree at `be987cf`; the candidate side is a `tar`-piped copy of the working tree at `/tmp/apg-candidate`, which is byte-for-byte what the bump commit contains. `.generated/` is excluded from the copy so the candidate renders into an empty one. | A copy rather than a second worktree because a worktree carries the committed tree and the reading is wanted BEFORE the commit -- the verdict goes into the release paragraph, and a number written before the command ran is D267. | -- |
| **D1625** | Run 6 §5: *"the leaves are `template_version` and whatever the compose env's new keys show as (if the rendered document publishes them -- read the output and list every leaf in the Done)"*. | **The rendered document publishes none of them.** `upgrade plan` reports exactly ONE leaf: `template_version`, 1.8.0 -> 1.9.0. `pids_limit` and `cpus` are written into `compose.env`, and `outputs.json` is not that file. Both documents are 5,948 bytes. `changes []`, `reasons []`, `operator_digests_moved []`, `verdict ok`, `bump minor`, `requires patch`. | The Done lists the single leaf, and the release paragraph says which file the eighteen keys actually live in. Nothing changes in the product: this closes a question the plan left open. | The same shape 1.8.0's reading produced (D1561), and for a different reason -- that release moved nothing a document shows, this one moves eighteen keys into a file `upgrade plan` does not compare. | 0162 |
| **D1626** | ADR 0162 prices an **operator manifest bump** at a minor, and Run 6 asks the product's own command what this release costs. | **The command cannot see the row this release hits.** `host.yaml` moves from schema 2 to schema 3 -- an operator manifest bump -- and `upgrade plan` compares two RENDERED DOCUMENTS. `host.yaml` is an operator INPUT and appears in neither, so `requires` comes back `patch`: a floor computed without the field that would have raised it. The reading is not wrong; it is answering a question about documents. | **Reported, not folded** (ADR 0195). The release paragraph states the minor is chosen above the floor for 1.8.0's reason AND for one 1.8.0 did not have, and names the row the command could not see. No change to `upgrade`: teaching it to read an operator input would make it a second reader of `host.yaml` beside `host_config` (D816, ADR 0002). | 1.8.0 was the first release where the price was a judgement rather than a reading (D1561). This is the first where the reading is INCOMPLETE in a way the table can name -- worth a number, because the next session to bump a manifest schema will run the same command and get the same floor. | 0162 |
| **D1627** | Run 6 §5: *"`test_no_gate_exists_for_the_session_that_took_the_trip` **deleted** (there is no skipped session between 30 and 31 -- the docstring says so)"*. | Deleting it is right and leaves the module with **no assertion about the derivation chain at all**. That test carried two: that the gap is real, and -- in its second half -- that the gate this session derived FROM exists, which is the anti-vacuity guard for every `SESSION_PREVIOUS` assertion in the file. Session 30's copy needed the first half; this session still needs the second. | Replaced rather than deleted, by `test_the_previous_gate_is_the_one_before_this_one_with_no_gap`: the previous gate is a file, `SESSION_PREVIOUS_NUMBER == SESSION - 1` (**true again for the first time since 24 -> 25**), and the gate holds `readonly SESSION=31`. Its docstring says why the literal is kept anyway -- `SESSION - 1` was right for six consecutive derivations before 26 broke it, which is exactly how it came to be trusted (D719). | A test deleted because its subject went away is correct; a test deleted without asking what else it was holding up is how an anti-vacuity guard disappears quietly. | -- |
| **D1628** | Run 6 §5: *"`bin/session-31-check.sh --mode offline` writes `evidence/session-31-offline.json` carrying the six new offline claims plus the **nineteen** inherited, every one `passed`"*. | **Eighteen are inherited, not nineteen.** Measured from `OFFLINE_CLAIMS` and `CLAIM_INTRODUCED_IN` rather than counted by hand: the tuple held 18 before this session and holds **24** after it. `CLAIMS` goes 135 -> 145. | The Done and the gate's own prose say 24 and say where the number came from. Nothing in the product moves -- the gate derives the list, it does not carry one. | The fourth stale count this session has corrected against a measurement (D1595's four were the first three plus the label count). A number in a plan is a number that was right when the plan was written, and this one was one short before Run 5 declared six rather than five. | 0202 |
| **D1629** | Run 6 §5: *"`bin/session-01-check.sh` runs once, on a clean tree (commit, gate, repair, commit, gate again)"* -- and the plan asks for the gate's first-run defects as rows. | **Three failures of 6,225, all in the release paragraph and none in the product.** `test_release_contract` reads the LAST `#:` paragraph above `CURRENT_SESSION`, because the convention its own docstring states is that the version-and-class sentence CLOSES the block -- so an older paragraph naming an older version can never satisfy it. The measured-verdict addendum was appended AFTER the pricing sentence, which left the final paragraph naming neither `1.9.0` nor a class: two tests, one mistake. The third, `test_deployable_source_does_not_hardcode_a_fixture_identity`, refused `src/agentic_postgres/__init__.py` because the rig description named the fixture the example project renders as. | The pricing paragraph goes last again and carries all four things its two readers take from it, **verified by reproducing the reader's own splitting logic rather than by eye** -- the repair was made from Windows with WSL's command channel down, so neither `ruff` nor pytest could be run until the machine came back. The fixture identity is replaced by the PROPERTY that mattered: *the same key as one of the four fixtures the gate compares*. | Both guards are right and both are about the same thing -- a paragraph that describes the release before, and a source file that names a fixture. The gate is the only instrument that reads either, which is why it runs before the push and why a run that skipped it would have shipped a release paragraph describing 1.8.0. | 0162 |
| **D1630** | Sheet A6: *"`setsid nohup bash /home/op/g31-host.sh > /dev/null 2>&1 < /dev/null &` … `cat /home/op/g31-host.exit`"*. | **Neither file exists and neither name is this trip's.** `g25-host.sh` is two conventions old; Session 30 -- the last host sweep that actually ran -- used `s30-r7-gate.sh` with a separate `s30-r7-launch.sh`, wrote its log to `s30-r7-host.txt`, its exit to `s30-r7-host.code` and a reading to `s30-r7-host-summary.txt`. Deriving from the newest working script is D1482's rule and it lands on that shape, not on the planned one. | The staged scripts are `s31-r7-{checkout,renders,gate,launch}.sh`, derived from Session 30's by named substitution with every count asserted, and **Sheet A6 names the launcher rather than the gate**: `sudo bash /home/op/s31-r7-launch.sh` detaches the sweep itself, so the sheet no longer carries a `setsid nohup` line for an operator to retype. | A sheet naming a file that is not there is a failed line in the middle of a fifteen-minute window, and the failure is indistinguishable at a glance from a sweep that refused. | -- |
| **D1631** | Sheet A6: *"`sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/alpha-dev/outputs.json /home/op/alpha-dev-dev-outputs.json`"*. | **The host's op-owned copies are `/home/op/alpha-dev-outputs.json` and `/home/op/beta-dev-outputs.json`** -- read 2026-09-20, both written 2026-09-19 09:38. The doubled `-dev-` names nothing. `install` would CREATE it, the agent's confirmation that the copy carries the new `source_commit` would then read a file nothing else uses, and the real pair would sit stale beside it looking installed. | The sheet names the two paths that exist. (The bare `/home/op/alpha-outputs.json` pair, 2026-08-23, is older still and is a third thing again -- CLAUDE.md already warns never to point a WRITING command at either.) | **D1575's shape**: a sheet pointing a command at the wrong copy of the deployed document. That one cost a window; this one was caught by listing the directory before the day rather than by a command failing during it. | -- |
| **D1632** | Sheet A1: *"`df -Pk /var/lib/docker` → the 1K-blocks and Available columns"*, whose number becomes `capacity.disk_gb` on Sheet A2. | **`/var/lib/docker` is the default and is not the contract.** `capacity_probe.read_docker_root` asks `docker info --format '{{.DockerRootDir}}'` for exactly this reason -- *a host that had moved it would otherwise be measured at the wrong filesystem, and the number would look perfectly plausible*. The sheet assumed the path the product refuses to assume. `op` cannot ask: no Docker socket, by decision (D1375), and `/var/lib/docker` is `drwx--x--- root root`. | Sheet A1 gains `sudo docker info --format '{{.DockerRootDir}}'` and runs `df -Pk` **at that path**. It stays on A1 rather than A2 because A1 is the `sudo` sheet and A2 is `op`'s. | The declaration is the thing every admission decision rests on, and a `disk_gb` describing a different filesystem is the defect this session spent D1611 and D1623 removing from the product -- reintroduced in the sheet that produces the number. | 0221 |
| **D1634** | ADR 0225 and §2 `SEC-KIND-001`: a secret's value is checked against its declared `value_kind` at materialization, with the enum's two kinds -- `random_hex` and `rsa_private_pem` -- taken as sufficient. | **The enum could not describe a credential a third party issued, and the FIRST PRODUCTION RUN of the check found out.** Alpha's deploy was refused at step 5: *`mirror_s3_secret_access_key: declared random_hex and the value is not lowercase hexadecimal from end to end`*. The check was right and **the contract was wrong** -- it is a Backblaze B2 application key, 31 characters in a base64url alphabet, declared `random_hex` since Session 18 added the mirror. Nothing could tell, because until ADR 0225 nothing read the field. Its sibling `mirror_s3_access_key_id` is mis-declared identically and **PASSED**, because a B2 key id happens to fall inside `[0-9a-f]`. | **`opaque` joins the enum** -- a credential a third party issued whose shape this product does not define and must not constrain -- and both mirror secrets take it. `check_value_kind` returns `None` for it through an EXPLICIT branch, because an unknown kind must keep failing closed and this one means the opposite. Cloudflare's four R2 secrets stay `random_hex`: for them it is TRUE, the secret access key being the SHA-256 of the token. A new proof pairs the two silent kinds, and a new AUDIT compares every operator-supplied secret against the issuer that produces it. | **This ADR's own thesis, arriving from the other side.** It argued that a declared field with no reader is an unverified field; the first reader found the declaration false. What it cost was a deploy stopped before anything was written, with both projects serving throughout -- the check failing in the direction it was built to fail. What it should have cost is five minutes: **a reader was given to a field without walking the declarations it would read**, and that walk is now a test. | 0225 |
| **D1635** | Sheet A3 step 2, the sentinel script this run wrote: `psql -At -c "SET ROLE …; SET app.user_id = …; SELECT (api.create_note(…)).owner_id;"`, with the result compared against the owner uuid. | **`psql` prints one line PER STATEMENT.** The output is `SET`, `SET`, then the uuid, and the script compared that three-line blob against the uuid. It refused -- correctly by its own lights, for the wrong reason -- **after the row had already been written**, so the before-file was absent while the row existed. A multi-line output compared as if it were a value, in the instrument rather than the product. | The answer is the **last** line, and the row is **counted before it is written** so a re-run reuses what is there rather than creating a duplicate the proof would count as 2. Both changes are in `/home/op/s31-r7-sentinel.sh`; the row from the first run is reused. | The shape D1570 recorded one session earlier -- a sentinel recipe that failed on its first execution -- repeating in the repair for it. The recipe was right this time and the CHECK around it was wrong, which is why the row survived and the file did not. | -- |
| **D1636** | Sheet A5 item 4: *"`ceilings` naming 2240 per key and the three `unbounded` services"*, and `diagnosis.capacity_report`'s own line, *"N MiB of mem_limit across N project(s) -- ceilings, not reservations (D767)"*. | **The ceilings figure EXCLUDES THE DATABASE, which is the largest cap of all.** Production read **2944 MiB** where the compose model sums to 2240 *per project*. 2944 is 2 x 1472 -- both projects, with `postgres` (768 MiB) and `pgbouncer` missing from each. `read_ceilings` groups containers by `apg.project.key`, and **that label is not applied to `postgres`, `pgbouncer` or `dbmate`** -- D587, the same blind spot that made `bin/backup.py` select the cluster and match zero containers on a healthy deployment. | **Reported here, not folded, and not repaired mid-trip.** The figure decides nothing -- `decide` charges `unreclaimable_mb`, never the caps -- so nothing red follows from it and no live proof asserts it. What it costs is the sentence it exists for: D767's whole point is that *the caps in aggregate already exceed the machine's RAM*, and 4480 > 3814 while the reported 2944 < 3814. **The number under-reports in the reassuring direction.** The repair is to group by Compose's own labels, as `runtime_override` already does for the database selector, and it is Session 32's or a follow-up's. | The third time D587's label gap has produced a wrong reading, and the first where the wrong reading is a capacity figure. Run 5 corrected the comment that undercounted the label's services (six to nine, D1620) and did not ask what ELSE reads that label -- which is §7's question 5 exactly: when a decision is implemented, which of its callers got it. | 0221 |
| **D1637** | Run 6 §5, `test_session31_capacity.py`: the rehearsal proof asserts `record["verdict"] == "refused"` and `record.get("induced") is False`. | **The harness produces neither, and the rehearsal it would have failed did exactly what it should.** Measured from the record `rehearse.sh admission-refused` wrote on production: `"verdict": "read"` -- the harness's word for a scenario that READS rather than one that passes or fails -- and `"induced": true`, because the induce PHASE ran, which is not the same as something having been broken. Both values were assumed from the plan's prose rather than measured, and a sweep would have reported `admission_live` FAILED for an instrument error. | The proof asserts the record's **readings** instead, which are stronger than either field: `admission_refused` is `refused` at exit **12**, `admission_as_declared` is `admitted` at exit **0**, `control_declaration_injected` is `false`, and the scenario reversed. Every one was then RUN against the record the host actually wrote, here, before the sweep runs it there. | **The fourth time this session the instrument was wrong rather than the product** -- after the fork control's environment-specific literal (Run 4), the flag scan that read its own header's prose (Run 7 preparation), and the sentinel comparing three lines of `psql` output against one value (D1635). Each was a value that looked measured and was not, and each was caught by running the check against the real thing instead of the expected thing. | 0190 |
| **D1638** | Run 5 §5 and `test_session24_studio.py`'s `auditor` docstring, written this session: *"the request role is `authenticated`, not `project_admin` (D1572) — what a subject may do administratively is decided by the scope in its token and not by the role name"*. | **False, and the running auth service says so in one sentence.** The sweep's three Studio proofs ERRORED at setup with `422 {"error":"invalid_request","message":"the stored record grants ['admin_agents:read', 'admin_agents:write', 'admin_audit:read'], which a authenticated token may not carry"}`. `issue()` validates the stored scopes against `permitted_scopes(role_suffix)` before signing and **refuses rather than truncating**. Measured over all six roles a token may name: `project_admin` is the ONLY one whose ceiling contains the three admin scopes, and its ceiling also contains `notes:*`. So there are two rules, not one — the token ceiling admits admin scopes to `project_admin` alone, and migrations 0004/0007 grant the notes SELECT and the `create_note` EXECUTE to `authenticated`/`agent_writer`/`agent_reader` alone. **No single account satisfies both**, and Session 24's auditor was asked to. | **The subject is split.** The `auditor` returns to `project_admin` with `AUDITOR_SCOPES` — it reads `/admin/audit`, lists and revokes through `/admin/agents`, and `reader_agent` registers through it, all of which need the admin half. A new `note_owner` fixture holds `authenticated` + `notes:read,notes:write` and owns the row `STU-QUERY-002` reads. `launched_studio` becomes two launches over one `_launch_studio(username, password_file)` helper, because **Studio takes its subject once at start-up and forwards that token for the life of the process** (ADR 0205), so the tenant proof has to reach a Studio holding the tenant's token. | **D1572 fixed the side that was visible and the offline suite could not see the other.** The notes grants are readable in a migration; the ceiling is enforced by the auth service when it mints a token, and nothing offline mints one — so a repair measured against the source passed every gate and errored on the next trip. §7's question 4 exactly (*when a defect class was fixed, which side got the fix*) with a second answer nobody looked for. **The sixth time this session the instrument was wrong rather than the product**, and the product's refusal named its own reason precisely enough to diagnose from one grep. | — |
| **D1639** | Run 6 §5, `test_session31_capacity.py`: the live refusal proof asserts `labels[:6] == ["declared", "reserved", "committed", "requested", "safe available", "suggested action"]`. | **The renderer's first label is `declared memory`.** `capacity_reading.decide` emits `("declared memory", f"{declared.memory_mb} MiB")` — there is a `declared disk` line further down and the two are distinguished by name. The operator's own `admit.sh` output on Sheet A5 printed it, and the sweep failed on `At index 0 diff: 'declared memory' != 'declared'` **after** passing every reading that mattered: outcome `refused`, exit 12, `declaration_injected False`, `already_deployed_here False`. | The live proof asserts the six labels the renderer emits. **The guard against a repeat is already there and was not used**: `test_capacity_reading.py:447` pins the same five labels against the module, so a renderer that renamed one goes red offline first — the live proof hand-typed a list instead of failing behind it. | A label asserted from memory of the plan's prose rather than from the renderer, in a proof whose every substantive reading was correct. Same shape as D1637 four rows up, in the same module, written in the same run: **the assertions around the measurement were the unmeasured part.** | — |
| **D1640** | CLAUDE.md §5: *"External mode runs from this workstation with an ephemeral `ssh-agent` and `--ssh-destination op@62.238.99.122`"*, and this run's staged step-8 script, which passed `--ssh-destination` and started no agent. | **Both `connection_tooling` proofs failed with `op@62.238.99.122: Permission denied (publickey)`.** There is no `~/.ssh/config` in this WSL, so `ssh op@host` with no `-i` and no agent has no identity to offer -- every other SSH this session carried `-i ~/.ssh/agentic_postgres_ed25519` explicitly and worked, which is exactly why the gap was invisible. The gate's own `ssh` calls cannot carry `-i`: the destination is a flag and the key is not. | **Re-run with `eval "$(ssh-agent -s)"`, `ssh-add` and a `trap … EXIT` that kills the agent on every path**, plus a control that reaches the host with NO `-i` flag before the gate is invoked. External mode then PASSED, 25 passed / 0 failed, and `connection_tooling` went from `failed` to `passed`. | **The proofs failed on their POSITIVE CONTROL, which is why this cost twenty minutes and not a release.** `test_the_access_broker_returns_nothing_to_an_unauthorized_caller` asks a granted profile first, precisely so that a broker refusing everything -- a missing policy, an unreachable trampoline, or this -- cannot satisfy its refusals. Without that control the run would have reported a security property PASSED on a connection that was never made. D173/D509's shape, paying for itself. **The seventh instrument defect of the session**, and the second in step 8's own scripts. | -- |
| **D1641** | D1425: *"the deploy, the sweep and the tag land on ONE commit, in that order"*, and the trip deployed `4344a1f`. | **The first sweep failed two proofs and the repair had to land before the second sweep could run**, so the sweep's instruments came from `05fdfe9` while the deployment stayed on `4344a1f`. Measured rather than assumed: `git diff --name-only 4344a1f..05fdfe9` filtered to `src/ bin/ services/ migrations/ templates/ schemas/ compose.yaml deploy.sh VERSION` is **empty** -- two test modules, one registry description and three documents. | **The tag goes on `4344a1f`, the deployed and measured commit**, and the exception is written into the tag's own message rather than left for a reader to notice. The merged evidence carries both: `source_commit 4344a1f` and `offline_checkout_commit 05fdfe9`, and `write-session-evidence` PRINTS the difference rather than folding it -- which is the behaviour ADR 0195 asks for, found already built. | Session 30's precedent decides it: HEAD was seven documentation commits past the deployed `be987cf` and the tag went on `be987cf`, because **a tag names what runs**. The narrower question this trip adds is whether a test-only commit between deploy and sweep breaks D1425, and the answer taken here is that it does not, PROVIDED the deployable diff is measured empty and the gap is stated. Anything in `src/` or `bin/` would have required a second deploy. | 0214 |
| **D1642** | Sheet A6's post kit, and ADR 0189/0192: a DR kit is what a replacement host is built from. | **The kit names the CHECKOUT's commit as its release, not the one the host runs.** `dr-kit: /home/op/kit-2026-09-21-post verifies: 10 artifacts for alpha-dev, beta-dev, exported 2026-09-21T16:15:28Z from release `05fdfe94c9f8``. The deployment is `4344a1f`. Harmless here and only here, because D1641 measured the deployable diff between those two commits EMPTY -- but the field is read from the tree the export runs in, not from the deployed document beside it in the same kit, and the kit carries BOTH (`projects/<key>/outputs.json` names `4344a1f`). | **Reported, not repaired.** Nothing is wrong with this kit: a replacement built from it would check out `05fdfe9` and deploy bytes identical to what runs. What is unguarded is the general case -- a checkout that has drifted from the deployment would produce a kit whose `release` names code the host does not run, and the two fields inside the kit would disagree with nothing to notice it. The repair is for `export` to compare the two and refuse, or say so; it belongs to a session that is in `dr-kit.py` anyway. | The `release`/`source_commit` pair that D1641 handled by STATING the gap, met again one artefact later in a place that states nothing. A value that looks measured -- and it is measured, just not of the thing a reader will assume. | 0189 |
| **D1643** | Run 8's readings: `doctor usage` on both projects, expecting *eight figures each, `ok`* (§5 Run 8, Sheet A5 item 5). | **Beta reads `3 ok, 0 warning, 0 problem, 1 UNKNOWN` and exits 6**: `traffic -- tool_calls_total could not be read: the store holds no such series yet`. Alpha reads four `ok` and exits 0, with `traffic -- 285 requests, 21 calls` -- the sweep's own traffic, which is exactly what Sheet A5 predicted would turn a 0 into a positive number. **Both readings are correct.** A Prometheus counter has no series until it is first incremented, and no agent tool call has ever been made on beta -- corroborated by beta's own agent record in the line above it, `44 rows, 0 rows`, read from the audit table by a different path entirely. | **Nothing to repair, and the exit code is the point.** `diagnosis.exit_code` returns 6 for `UNKNOWN` as well as `PROBLEM`, and says why: *a check that could not run is not a healthy check, and a caller that treated it as one would be back at D600*. The product refused to fold *no series* into *zero calls*, which is the one thing that would have made this reading a lie. **Recorded so the next operator is not surprised:** `doctor usage` will exit 6 on beta until an agent tool call is made there, and that is the reading working. The default `doctor` is unaffected -- it is a separate verb and still reads 11 ok / 0 problem on both. | **The first production instance of ADR 0195's third outcome in a reading this session built**, and it arrived on the first run after the trip. Two independent readers -- the store and the audit table -- agree that beta has made no tool call, and the product still declines to state the number it could have inferred. That is the discipline the whole session is about, and it cost one exit code to keep. | 0195 |
| **D1644** | §5 Run 8: *"Documentation only, no CI read"*, and the header: *"Run 8 is documentation only and reads none."* | **Run 8 changes source.** The envelope's figures are not in `docs/capacity-envelope.md` -- that file is GENERATED -- they are `Measurement` and `Unmeasured` dataclasses in `src/agentic_postgres/capacity.py`, and the row Run 8 was written to replace lives there. `render-capacity-envelope.py --write` regenerates the page FROM the module, so the plan's own instruction to run it presupposes the module was edited first. | **Run 8 commits, gates and reads CI like any other run that changes code**, and the plan's two sentences are corrected here rather than honoured. `capacity.py` also validates at construction -- a `Measurement` with no stated conditions raises -- so the edit is checked the moment the module imports, before any gate. | The same shape as D1557 one session earlier, where a row implied an edit to a GENERATED file and the next render would have undone it. Here the direction is reversed: the plan called a source edit documentation because the artefact a reader sees is a document. **What a change IS follows from where it lands, not from what it looks like when rendered.** | -- |

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

**One new family, `NODE`**, added to `ID_PATTERN` at
`tests/contract/test_acceptance_registry.py:79` with a comment naming this
session (the way `STU` names 24). **Nine requirements, nine claims, all
`target_session: 31`, all P0** — six offline, three host. Every requirement
belongs to a claim (D697); a new requirement gets a claim of its own (ADR
0089, D1150). **Node ids below are proposed; Run 6 writes what the runs
actually wrote, read out of the tree with `pytest --collect-only -q`**
(D1236). The registry entries cannot be committed before Run 6 moves
`CURRENT_SESSION` (`:163`, D690) — the runs write the proofs and this table;
Run 6 lands the YAML.

| Requirement | What it states | Offline node ids (proposed) | Live half |
|---|---|---|---|
| `NODE-CAP-001` | `host.yaml` schema 3 declares `capacity` with exactly four positive-integer members; schema 2 still validates and reports the declaration absent; `host.example.yaml` is schema 3 and its `memory_mb − reserve_memory_mb` equals `HOST_MEMORY_GUARDRAIL_MB`; a schema-3 document missing any member, or carrying a fifth, is refused naming it | `test_host_manifest.py::test_schema_three_requires_the_four_capacity_members`, `::test_a_schema_two_manifest_still_loads_and_declares_nothing`, `::test_the_example_declares_the_guardrail_as_memory_minus_reserve`, `::test_a_fifth_capacity_member_is_refused_naming_it` | — (offline claim `capacity_declared`) |
| `NODE-READ-001` | The capacity reading has three outcomes per figure: `/proc/meminfo` parsed to MemTotal/MemAvailable/SwapTotal in MiB or `unknown` with the reason; `disk_usage` at the Docker root and at each project's data volume or `unknown`; committed unreclaimable per deployed project from the documents; `Σ mem_limit` from `docker inspect` reported as ceilings; `doctor capacity` prints `OK` with every figure or `UNKNOWN` naming the one it could not read, never `WARN` or `PROBLEM`, and its `--json` carries every figure as a number or `null` with a `reason` | `test_capacity_reading.py::test_meminfo_is_parsed_to_mebibytes`, `::test_a_meminfo_missing_memavailable_is_unknown_not_zero`, `::test_committed_memory_sums_unreclaimable_across_documents_and_excludes_the_candidate`, `::test_ceilings_sum_hostconfig_memory_and_ignore_unbounded_containers`, `test_doctor_readings.py::test_the_capacity_report_has_two_verdicts_only`, `::test_an_unreadable_figure_is_unknown_and_names_itself`, `::test_doctor_sh_maps_the_capacity_word_to_the_reading`, `::test_doctor_with_no_verb_runs_the_eleven_checks_unchanged` | — (offline claim `capacity_reading`) |
| `NODE-ADMIT-001` | Admission decides: refused (exit 12) when committed + requested + reserve exceeds declared memory or free disk is below the disk reserve, admitted (exit 0) otherwise; the candidate's own key is excluded from the committed sum; with no declaration a candidate with no deployed document is refused and one with a document is admitted; an undetermined reading refuses (fails closed) naming the figure; the refusal prints six labelled lines (declared, reserved, committed, requested, safe available, suggested action) and `--json` the same six; the deploy calls the same function at step 0 before any render; the four headers name exit 12 | `test_admission.py::test_a_candidate_that_does_not_fit_is_refused_with_exit_twelve`, `::test_a_candidate_that_fits_is_admitted` (control), `::test_a_redeploy_charges_only_the_other_projects`, `::test_no_declaration_refuses_a_new_project_and_admits_a_redeploy`, `::test_an_unknown_figure_fails_closed_naming_it`, `::test_the_refusal_prints_the_six_lines`, `::test_the_deploy_decides_admission_before_it_renders` (an AST scan of `bin/deploy-project.py`: the call to `capacity_reading.decide` precedes `step("1. Render`), `::test_every_header_names_exit_twelve`, `test_rehearsal.py::test_admission_refused_moves_the_reserve_and_reads_a_refusal`, `::test_admission_refused_has_a_verdict_arm` | — (offline claim `admission_decision`) |
| `NODE-ADMIT-002` | On the deployment, a third project's manifest whose unreclaimable claim exceeds the safe available is refused by `bin/admit.sh` with exit 12 and the six lines; the same manifest at the release's default budget is admitted (control); the rehearsal `admission-refused` on a deployed project records `refused` with the reserve injected and the host's own answer as control | — | `test_session31_capacity.py::test_a_third_project_that_does_not_fit_is_refused_on_this_host`, `::test_the_same_project_at_the_default_budget_is_admitted`, `::test_the_admission_rehearsal_recorded_a_refusal_and_a_control` (host claim `admission_live`) |
| `NODE-LIMIT-001` | Every service in `compose.yaml` carries `pids_limit`; the nine long-running services take theirs and `cpus` from `SERVICE_RESOURCE_DEFAULTS` through the compose environment; the eleven short-lived carry the literal; every default is a power of two ≥ 64 and postgres's ≥ `max_connections + 32`; `cpus` is `2.0` for postgres and `1.0` otherwise; a container under `pids_limit` cannot fork past it and the same fork succeeds with no limit (control); `apg dev`'s cluster definition carries the same `pids_limit` if it carries a `mem_limit` | `test_process_limits.py::test_every_service_carries_a_pids_limit`, `::test_the_nine_take_theirs_from_the_environment_and_the_eleven_the_literal`, `::test_every_default_is_a_power_of_two_at_least_sixty_four`, `::test_postgres_can_hold_its_connections_and_its_workers`, `::test_cpus_is_two_for_postgres_and_one_for_every_sidecar`, `::test_a_container_cannot_fork_past_its_pids_limit` (`@requires_docker`), `::test_the_same_fork_succeeds_with_no_limit` (`@requires_docker`, control), `::test_the_dev_cluster_carries_the_same_limit_as_the_release` | — (offline claim `process_limits`) |
| `OPS-TELEMETRY-001` | The collector's exporter carries `const_labels` with `project` equal to the project key and nothing else; the store's retention is the declared constant; the mcp environment names the collector endpoint derived from the service name and the OTLP http port and the endpoint is in `MCP_VARIABLES`; `create_mcp_app` calls `mcp_metrics.configure` once, after the lock is loaded, with the lock's tool names; `mcp_tracing.configure` has no caller; `configure` with the endpoint set returns `True` and the two instruments record; metrics and store carry `pids_limit` | `test_metrics_surface.py::test_every_exported_series_carries_the_project_as_a_const_label`, `::test_the_const_label_is_the_project_key_and_nothing_else`, `test_alert_rules.py::test_the_store_keeps_exactly_the_declared_retention`, `test_mcp_runtime.py::test_the_runtime_names_its_collector_endpoint`, `::test_the_endpoint_is_derived_from_the_service_name_and_port`, `test_mcp_tracing.py::test_exactly_one_module_configures_metrics_and_none_configures_tracing` (replaces the enumeration at `:283-322`), `test_metrics_surface.py::test_configure_with_an_endpoint_creates_both_instruments` | — (offline claim `telemetry_bounded`) |
| `OPS-TELEMETRY-002` | On the deployment, `doctor usage` returns a request count and an agent tool-call count read from the project's store, every series returned carries `project="<key>"`, and the metrics route serves `agent_tool_calls_total` for the first time | — | `test_session31_capacity.py::test_usage_reads_request_counts_from_this_projects_store`, `::test_every_series_the_store_returns_names_this_project`, `::test_the_metrics_route_now_serves_the_agent_instrument` (host claim `telemetry_read`) |
| `NODE-USAGE-001` | `doctor usage` reports seven figures per project (database bytes, PGDATA KiB, WAL KiB, repository bytes, audit rows, idempotency claims, request count, tool-call count — eight with the two from the store) with `OK` or `UNKNOWN` naming the figure it could not read; no figure is thresholded; `backup_report.summarise` exposes `repository_bytes` summed from the deltas; every value printed is an integer this program produced | `test_doctor_readings.py::test_the_usage_report_has_two_verdicts_only`, `::test_no_usage_figure_carries_a_threshold`, `::test_doctor_sh_maps_the_usage_word_to_the_reading`, `test_backup_report.py::test_repository_bytes_is_the_sum_of_deltas`, `::test_repository_bytes_is_none_when_a_backup_carries_no_delta` | `test_session31_capacity.py::test_capacity_agrees_with_free_and_df_on_this_host`, `::test_usage_returns_every_figure_on_both_projects` (host claim `usage_read`) |
| `SEC-KIND-001` | A secret's value is checked against its declared `value_kind` at materialization before it is written; an `rsa_private_pem` without both PKCS#8 delimiters or shorter than 1,000 characters is refused with exit 8 naming the secret's name and kind and no byte of the value; a `random_hex` that is not lowercase hex is refused the same way; a value that passes is written unchanged | `test_secret_contract.py::test_a_pem_without_delimiters_is_refused_naming_the_secret_not_the_value`, `::test_a_truncated_pem_is_refused`, `::test_a_hex_with_an_uppercase_character_is_refused`, `::test_a_valid_value_of_each_kind_passes` (control), `test_materialize_secrets.py::test_the_loop_checks_the_kind_before_it_writes` (an AST/text scan: `check_value_kind` precedes the write in the loop) | — (offline claim `secret_kind_checked`) |

**Claims** (`src/agentic_postgres/evidence_claims.py` `CLAIMS`, each in a
block commented *Session 31 (ADR 0221-0225)*): `capacity_declared:
("NODE-CAP-001",)`, `capacity_reading: ("NODE-READ-001",)`,
`admission_decision: ("NODE-ADMIT-001",)`, `process_limits:
("NODE-LIMIT-001",)`, `telemetry_bounded: ("OPS-TELEMETRY-001",)`,
`secret_kind_checked: ("SEC-KIND-001",)` — **these six in `OFFLINE_CLAIMS`**,
with the per-session assertion in `test_session_thirty_one_gate_modes.py`
(D1237: assert THESE six are in the set, never the set's size).
`admission_live: ("NODE-ADMIT-002",)`, `telemetry_read: ("OPS-TELEMETRY-
002",)`, `usage_read: ("NODE-USAGE-001",)` are **host** claims and are not
declared. `CLAIM_INTRODUCED_IN` gains nine rows at 31.

**Existing entries that move:** `STU-QUERY-002` keeps its node id (the
fixture is repaired, the proof is not renamed). The orphan triage (Run 5,
D1597) adds node ids to existing entries and possibly new entries in existing
families; each is listed in Run 5's Done and pasted in Run 6. `IDN-ROTATE`'s
next free number (read from the registry in Run 5) gains one entry for ADR
0224's report path if Run 5 writes a proof for it; otherwise the ADR's change
is covered by the existing rotation module's edited test and no entry is added
— **Run 5's Done says which.**

**New environment gates** (`tests/conftest.py` `ENVIRONMENT_VARIABLES`, and
exported by the Session 31 gate's host mode): `APG_CANDIDATE_MANIFEST` (the
path of the third project's manifest, `/home/op/s31-third.yaml`), `APG_HOST_
MANIFEST` (the path of the host's `host.yaml`, needed by `admit.sh` and
`doctor capacity`). Both are declared with a `#:` comment naming this session
and D687. The gate's flags are `--candidate-manifest FILE` and `--host FILE`
(the latter already exists, `bin/session-30-check.sh:576`, and is now also
exported).

---

## 4. Irreversible operations

| Operation | Where | What makes it safe |
|---|---|---|
| `host.example.yaml` moved to schema 3; the schema enum widened | Run 2 | Schema 2 still validates (a test); the twelve readers of the example (`test_host_manifest.py:29,433`, `test_bootstrap_state.py:295`, `test_printed_commands.py:115`, `test_project_state_roots.py:235`, `test_edge_config.py:314`, `test_deploy_command.py:40,319,338`, `test_repository_contract.py:32,376,851`, `test_cli_contract.py:965`, the session 3–7 gate-mode modules) run whole |
| `compose.yaml`: twenty services gain `pids_limit`, nine gain `cpus` | Run 3 | A contract test walks every service; `bin/compose.sh … config` in the gate's step 5 validates the interpolation; rig 31a measured the keys' semantics first; **on the trip every container of both projects is recreated by Compose, including the database** (Sheet A3 says so and reads the ledger after) |
| `deploy.sh` and `bin/deploy-project.py` gain exit 12 and an admission call at step 0 | Run 3 | The call precedes the render (an AST proof); a refusal changes nothing on the host; `--render-only` keeps working with no host and no root (the gate's step 2 renders four fixtures) |
| `build_otel_config` gains a parameter; the mcp environment gains a variable; `test_mcp_tracing.py:283-322` replaced | Run 4 | ADR 0223 first; every caller of `build_otel_config` grepped (`rendering.py:2529`, the tests) and edited in the same commit (D979); the replacement is stricter (names the one caller); `FORBIDDEN_VARIABLES` unchanged and its guards run |
| `mcp_metrics.configure` called in production for the first time | Run 4 | Rig 31d measured the exporter's memory and the series' arrival with a control; `MCP_MEMORY_LIMIT_MB` 384 against the measured cost recorded in the Done; a failing export is logged by the SDK and never raises into a tool call (the SDK's reader runs on its own thread — rig 31d confirms with the collector stopped) |
| `bin/materialize-secrets.py` refuses a value it used to write | Run 5 | ADR 0225 first; the check names no byte of the value (a test plants a sentinel and greps the output); both projects' provider values are the product's own PEMs (D1578's four malformations were all repaired on trip day), so the trip's deploy is the live control |
| `retire_rotation` reports where it refused | Run 5 | ADR 0224 first; the early refusal keeps its test; the new outcome is exit 0 only when `retire_after is None` AND exactly one kid is published AND `verifier_acknowledgements` is `None` |
| Five orphan proofs' registration; `KNOWN_UNREGISTERED` emptied or shrunk | Run 5/6 | Equality guard; `test_acceptance_registry` (D1119); each attachment is one line in the Done with the requirement it joined |
| `CURRENT_SESSION` 30 → 31; `VERSION` 1.8.0 → 1.9.0 | Run 6 | All-or-nothing (D690); every `target_session: 31` entry in the same commit; the client regenerated (D1238); both release pages gain a `1.9.0` row (ADR 0209); `upgrade plan` on the host confirms `bump minor` or §9 stops |
| `bin/session-31-check.sh` | Run 6 | Derived from 30's by diff (D1482); header and usage rewritten whole (D1488); `SHELL_COMMANDS` gains it and `chmod 755` before `git add` (D1014, D1188); `test_session_thirty_one_gate_modes.py` copied from thirty's |
| The host's `host.yaml` moved to schema 3 | Run 7, Sheet A2 (op) | `cp host.yaml /home/op/host.yaml.pre-s31` first; the four numbers come from Sheet A1's `free -m` and `df` readings and the derivation in `host.example.yaml`; `bin/apg.sh generate --check` is unaffected (host.yaml is not a client input); the render as `op` validates it before any `sudo` line |
| Deploy `--through-session 31` on alpha, then beta | Run 7 | `upgrade plan` OK first (§9); alpha first; at a terminal under `script(1)`; **every container recreated** (the compose keys moved) — the ledgers read after and expected unchanged (33; 33 + 2); `doctor` 11 ok after each |
| `bin/admit.sh` run against a third manifest on production | Run 7, Sheet A5 | It renders nothing and writes nothing (a contract test: no `.generated` entry and no file under `/etc` or `/var` after a run — the `--root` fixture proof asserts the fixture root's mtime set is unchanged); the manifest lives at `/home/op/s31-third.yaml`, never in the checkout (D971) |
| Rehearsal `admission-refused` on alpha | Run 7 | Induces nothing (the reserve is injected into `admit.py`'s argv); `reverse` is a no-op; the record's `induced: false` |
| One sentinel row on alpha before the redeploy | Run 7 | Session 30's recipe verbatim (Sheet A3); deleted on Sheet A6 by the root line; `count 0` read after |
| Tag `1.9.0` on the deployed commit | Run 7 | After the merge exits 0 or 5 for the expected reasons only (§7); `release-reading --ref <deployed sha>` first; `git ls-tree` of both release pages |

---

## 5. Build order, run by run

Each offline run ends with: `ruff format && ruff check` (its **exit code**
printed), the targeted modules (named, each checked for existence — D1104),
derived documents regenerated where a generator's input moved, `chmod 755
bin/*.sh bin/*.py deploy.sh`, one commit with a message written to a file and
passed with `-F`, a push, and **that commit's CI verdict read by full SHA with
three buckets** (D1059) — code commits only. A run that writes a test runs its
battery (appendix). Mark the run **Done.** with what it measured. **A targeted
list is derived from the tree** (D1146, D1149, D1184, D1187): a run that moves
a definition greps every reader of the name AND of the distinctive text and
runs every module found, whole.

**Docker is required for Runs 1, 3, 4 and 6** (rigs 31a/31c/31d, the fork
proof, the gate). **Root over SSH is required for Run 7 only** and is typed by
the operator. **Run 1 has one `op` step over SSH with no root** (the pids
reading). **No network is required by Runs 2–6** beyond what the tree pins.

### Run 1 — the measurements, and ADRs 0221–0225

**Read first:** stage plan §5 *Session 31* and D1519/D1520/D1526; this plan's
§1; `docs/decisions/0195-…md` whole; `docs/decisions/0165-…md:55-68` (`anon`
is the figure a limit is chosen against, never `memory.current`) and ADR
0169 (`CONFIGURATION` vs `MACHINE`); `docs/plans/session-14-implementation-
plan.md:99-104` (D765 the cgroup method, D767, D770); `docs/plans/session-17-
implementation-plan.md:86` (D959); `docs/decisions/0220-…md:1-15` (the ADR
header shape) and `docs/decisions/README.md:283-286` (the index line);
`tests/contract/test_image_contracts.py:1495-1535` (how a throwaway
`otelcol.yaml` is run); `services/auth-api/app/mcp_metrics.py:114-176`;
`bin/rehearse.py:272-302`, `:336-475`; `rehearsal.py:650-692`.

**Every rig is a script written with the Write tool to
`\\wsl$\Ubuntu\tmp\rig31<x>.sh`, run with `wsl bash -lc "bash /tmp/rig31x.sh
> /tmp/rig31x.txt 2>&1"`, its exit statuses printed from inside, and its
output pasted into the Done.** Every rig has a control. Each names the image
it ran by digest (`versions.env`). Copy each script to the scratchpad when it
is green (WSL's `/tmp` dies).

1. **Rig 31a — `pids_limit` and `cpus` through Compose, on this workstation.**
   A throwaway directory with a `compose.yaml` of three services on
   `${POSTGRES_IMAGE}` (it has `bash`): `limited` with `pids_limit: 8`,
   `unlimited` with no key, `capped` with `cpus: "1.0"` (a **quoted string**,
   because that is what `${X_CPUS:?required}` interpolation yields — measured
   here, not assumed; if Compose refuses the string, the row records it and
   the fallback is `deploy.resources.limits.cpus`, which Compose v2 honours
   outside swarm). Command for the first two: `bash -c 'for i in $(seq 1 20);
   do sleep 60 & done; wait'`. Expect: `limited` logs *Resource temporarily
   unavailable* or `fork: retry` and `docker inspect --format
   '{{.HostConfig.PidsLimit}}'` prints `8` and `cat
   /sys/fs/cgroup/pids.max` inside prints `8`; `unlimited` reaches 20 sleeps
   (`cat /sys/fs/cgroup/pids.current` ≥ 21) and `PidsLimit` is `0`. For
   `capped`: two busy loops (`bash -c 'while :; do :; done & while :; do :;
   done & sleep 5; cat /sys/fs/cgroup/cpu.stat'`) — `usage_usec` over the 5 s
   ≤ ~5.5 s under the cap; the control (no `cpus`, `nproc` ≥ 2) reads ≈ 10 s;
   `cat /sys/fs/cgroup/cpu.max` inside prints `100000 100000`. Also run
   `docker compose config` and quote how `cpus: "1.0"` is rendered.
   **Owes:** whether a quoted `cpus` is accepted; the exact fork-failure text
   (the offline proof asserts it); `pids.max` read-back.
2. **Rig 31b — the host's process counts, as `op`, no root** (D765's method,
   the only host step before the trip). Script `s31-pids.sh` scp'd to
   `/home/op`, run over SSH: for every `/sys/fs/cgroup/system.slice/docker-*.
   scope`, print the container id, `pids.current`, `pids.max`, and
   `pids.peak` **if the file exists** (say `absent` otherwise — the reader
   has three outcomes), then map ids to names with `apg-diag containers`
   (the agent account, ADR 0071) — 22 scopes expected (D960). Also
   `cat /proc/meminfo | head -5`, `free -m`, `df -Pk /var/lib/docker /` and
   `nproc` — the first program-readable copies of the host's numbers.
   **If WSL has no outbound TCP, use Git's ssh from Windows (CLAUDE.md §1).**
   **Owes:** the per-service peaks that set `SERVICE_RESOURCE_DEFAULTS`
   (D1600); MemTotal/MemAvailable/SwapTotal; the Docker root's free space.
3. **Rig 31c — `const_labels` on the collector's exporter.** Two throwaway
   `otelcol.yaml`s in the shape `test_image_contracts.py:1495-1535` runs
   (the `otlp` receiver, the `prometheus` exporter on 8889), one with
   `exporters.prometheus.const_labels: {project: rig31c}` and one without
   (control), each run for 20 s with a `hostmetrics`-free pipeline fed by one
   OTLP http POST from `curl` (a minimal `ExportMetricsServiceRequest` JSON
   with one sum metric — write it to a file). `wget -O - :8889/metrics` from
   the collector's own container (it is `read_only`, `cap_drop ALL`; use the
   image's own binary via a second `docker run --network container:<id>
   ${POSTGRES_IMAGE} bash -c 'curl …'` if the collector image lacks `wget`
   — the rig finds out). Expect every non-`#` line of the subject's
   exposition to carry `project="rig31c"` — including `target_info` — and no
   line of the control's to. **Owes:** whether `const_labels` reaches every
   series including the synthesised ones; the option's exact spelling on
   0.159.0.
4. **Rig 31d — `mcp_metrics.configure` against a real collector.** A docker
   network; the collector from rig 31c (with `const_labels`); a container of
   the auth-api image (`versions.env`'s pin; the exporter package is in the
   image, `mcp_tracing.py:192-193`) running `python - <<'PY'` **with `-i`**
   (CLAUDE.md §1): `from app import mcp_metrics; import resource; before =
   resource.getrusage(...).ru_maxrss; ok = mcp_metrics.configure(endpoint=
   "http://<collector>:4318/v1/metrics", service_name="apg-mcp", tool_names=
   ("list_resources",), outcomes=("ok",)); mcp_metrics.record(...)` per the
   `record()` signature at `:179-213`; sleep 20; print `ok`, the RSS delta,
   and exit. Then `wget :8889/metrics` → `agent_tool_calls_total{outcome=
   "ok",project="rig31d",tool="list_resources"} 1`. **Control:** the same
   with `endpoint=None` → `configure` returns `False`, nothing on 8889.
   **Second control:** the collector stopped before `record()` — the process
   exits 0 in under 30 s and prints the SDK's export failure on stderr
   (nothing raises into the caller). **Owes:** the endpoint's exact path
   (`/v1/metrics` on the http exporter); the memory cost of the provider and
   reader (expect single-digit MiB; recorded against `MCP_MEMORY_LIMIT_MB`);
   whether `service_name` becomes a label (`target_info` only, per
   `mcp_metrics.py:155-160`'s measurement — confirm).
5. **Rig 31e — the admission arithmetic, pure, against the fixtures.** No
   container. A Python script with `PYTHONPATH=src` reading
   `tests/fixtures/outputs-v10.json` (`unreclaimable_mb` 292) and the two
   op-owned copies if present in the scratchpad from Session 30 (304 each):
   compute `committed`, `requested` at the default budget (304) and at
   `shared_buffers_mb: 896` (896 + 64 + 112 = **1072**), `safe available` =
   3814 − 2214 − 608 = **992**. Expect: 304 admitted, 1072 refused, and
   `config._validate_memory_budget` **accepts** 1072 (≤ 1600) — so the
   refusal on the trip is the cross-project decision and not the per-project
   guardrail (the control that makes the live proof mean something).
   **Owes:** the third manifest's budget for Sheet A5 (`shared_buffers_mb:
   896`), and the confirmation that `database.budget.unreclaimable_mb` is
   read off the DEPLOYED document by name (`deployed_output.deployed_path`),
   not the rendered one.
6. **The five ADRs**, each Accepted, indexed in `docs/decisions/README.md`:
   - **0221 — Capacity is declared, admission decides, a reading reports.**
     The four members and their units; the arithmetic of D1583 (unreclaimable,
     not ceilings) and D1596 (the disk floor); undeclared → new refused /
     redeploy admitted (D1584); admission on every deploy with self excluded
     (D1592); exit 12 (D1585); the two doctor readings with two outcomes
     (D1587); what is NOT built (§7.4's shedding, `apg tune`, a per-project
     disk declaration, `storage_objects` — D1601). Alternatives: `Σ mem_limit`
     (refuses the deployment), a default measured at first read (a fold), a
     thirteenth ADR 0162 class (nothing rendered establishes it).
   - **0222 — Every project service is bounded in processes, and the
     long-running nine in CPU.** The split (D1586), the rule for the numbers
     (D1600), the edge plane excluded, `cpus` 2.0/1.0 and why a cap below
     the machine's count on a one-shot would be a throttle nobody measured.
   - **0223 — The collector is consumed: the runtime exports its two
     instruments, the store stays unrouted and is read by exec, and every
     series names its project.** D1582, D1588, D1589, D1590; tracing stays
     unconfigured; the contract tests it changes by name.
   - **0224 — The rotation's overlap window is closed by the operator's
     step-6 deploy, and `retire` reports that it was.** D1599, D1580,
     D1581; the guide's reorder; the `render-jwks`/`verification_kids`
     question deferred by name.
   - **0225 — A secret's value is checked against its declared kind at
     materialization.** D1598; the two kinds' rules; the reason names no
     byte; the mistyped-name half deferred by name.

**Targeted:** nothing runs (no code changed); `bin/session-01-check.sh` is
NOT run (no generated artefact moved except the ADR index — run
`python bin/render-acceptance-matrix.py --check` only if it reads the ADR
index; otherwise nothing). Commit (ADRs + index), push, **no CI read** (docs).

**Done.** 2026-09-19. Five rigs, each with its control in the same
invocation; five ADRs written and indexed; **eight new divergence rows,
D1602-D1609**, added to §1 in place. Next free is **D1610**, ADR **0226**.
Nothing in `src/` or `bin/` changed, so no targeted module ran and no CI
verdict was read. `test_acceptance_registry.py -k 'adr or decision or README'`
(3 passed) and `test_documentation_index.py` (47 passed) ran because the ADR
index moved.

**Rig 31a — `pids_limit` and `cpus` through Compose** (`${POSTGRES_IMAGE}` =
`pgvector/pgvector:pg18@sha256:691673...b62`, five services, subject and
control in one `docker compose up`). Everything the rig owed:

- **A quoted `cpus` string is accepted.** `cpus: "1.0"` and the product's own
  shape `cpus: ${RIG_CPUS:?required}` (which yields a *string*) both render:
  `docker compose config` normalises both to `cpus: 1`, and
  `HostConfig.NanoCpus` reads `1000000000`. **The
  `deploy.resources.limits.cpus` fallback is not needed.**
- **`pids_limit: ${RIG_PIDS_LIMIT:?required}` interpolates too**:
  `HostConfig.PidsLimit=8`, `/sys/fs/cgroup/pids.max` inside reads `8`.
- **The fork-failure text, verbatim** (this is what the offline proof
  asserts): `fork: retry: Resource temporarily unavailable` four times, then
  `fork: Resource temporarily unavailable`. The script exits 254.
- **Controls held.** No `pids_limit` → `pids.max` reads `max`, all 20 sleeps
  spawn, `pids.current` 23. No `cpus` → `cpu.max` reads `max 100000`.
- **The CPU cap is real**: over a 5 s two-thread burn the capped container used
  **5.06 s** of CPU (`cpu.max` `100000 100000`), the uncapped control
  **9.95 s**, on an 8-core workstation.
- **D1603**: `HostConfig.PidsLimit` prints `<nil>`, not `0`, when unset.

**Rig 31b — the host's counts, as `op` over SSH, no root** (WSL's outbound TCP
was alive; a timed `/dev/tcp` connect to `:22` and to `pypi.org:443` both
returned 0 before anything was run). **22 scopes** as D960 expects, and
**`pids.peak` exists on this kernel**. Container ids mapped to processes
rootlessly through `/proc/<pid>/cgroup` and `/proc/<pid>/cmdline`, because
`apg-diag containers` prints names and no ids.

| Service | `pids.peak` (alpha, beta) | `pids_limit` by the rule |
|---|---|---|
| postgres | 28, 29 | **128** (4x29=116, and >= `max_connections`+32 = 88) |
| postgrest | 18, 18 | **128** |
| metrics (otelcol-contrib) | 16, 16 | **64** |
| store (prometheus) | 16, 16 | **64** |
| auth / storage / mcp (uvicorn) | 9-12 | **64** |
| docs, pgbouncer, edge-probe | 9, 9 | **64** |
| traefik 17, haproxy 11 | **edge — excluded** | — |

The host's numbers, first program-readable copies, **for Sheet A2's
declaration**: `MemTotal` 3906280 kB = **3814 MiB**, `MemAvailable` 2234652 kB
= 2182 MiB, **`SwapTotal` 0**, `nproc` **2**, kernel 7.0.0-31. `df -Pk /` and
`/var/lib/docker` are the same filesystem `/dev/sda1`: **39027964 KiB total
(37.2 GiB)**, 23640416 KiB available (**22.5 GiB**), 37 % used. **D1602**: every
scope already reads `pids.max = 3647`, systemd's `DefaultTasksMax`.

**Rig 31c — `const_labels` on otelcol-contrib 0.159.0**, three arms. The
spelling is `exporters.prometheus.const_labels` as a map. Arm 1 (OTLP only):
the subject's series carried `project="rig31c"`, the control's carried
nothing. Arm 2 self-scraped and produced the **D1605** hazard. **Arm 3 is the
production shape** — a `prometheus` receiver scraping a *separate* collector,
as the deployment scrapes `apg-edge-proxy:8089`: **6 of 7 series carried the
label**, `up` / `scrape_duration_seconds` / `scrape_samples_scraped` /
`scrape_samples_post_metric_relabeling` / `scrape_series_added` among them,
and **`target_info` did not** (**D1604**). No duplicate-label error in this
arm — the arm-2 error was the self-scrape.

**Rig 31d — `mcp_metrics.configure` against a real collector.** The cached
`apg-prebuild-auth:latest` **could not answer this**: it predates the OTel SDK
(no `opentelemetry` module, no `app.mcp_metrics`), so the auth-api image was
built at the tree's pins (`apg-rig31d-auth:local`, SDK 1.44.0). Three arms, all
green:

- **Subject** (endpoint set, collector up): `configure` → `True`, `record`
  raised nothing, and after one 15 s export interval the collector served
  `agent_tool_calls_total{...,outcome="ok",project="rig31c",tool="list_resources"} 1`
  plus the 16-bucket histogram. **The endpoint path is `/v1/metrics`** on the
  http exporter. **RSS delta 25756 KiB = 25.2 MiB** for provider + reader +
  exporter, against `MCP_MEMORY_LIMIT` 384 MiB (6.6 %).
- **Control** (`endpoint=None`): `configure` → `False`, **RSS delta 0 KiB**,
  nothing on 8889.
- **Control** (collector stopped): `configure` → `True`, **`record` raised
  nothing**, process **exited 0**, the SDK printed its export failure on
  stderr. `service_name` becomes `job=`, confirming the docstring — and
  `service.instance.id` becomes `instance=` on every series too (**D1609**).
- **The fourth arm, added because the third's wall clock was wrong**: 1 s
  reachable, **18 s** when the name does not resolve, 11 s when the connect
  succeeds and the read times out at the exporter's 10 s default. Against
  mcp's `stop_grace_period: 15s` that is a SIGKILL (**D1607**).

**Rig 31e — the admission arithmetic, pure, against the real functions.**
`HOST_MEMORY_GUARDRAIL_MB` 1600, `PER_BACKEND_ANON_MB` 2, unreclaimable at the
defaults **304**. `outputs-v10.json`'s `database.budget.unreclaimable_mb` is
**292** and recomputes to 292 from its own members, so the document's figure is
read by name and agrees with the function. `memory_mb 3814 − reserve_memory_mb
2214 = 1600 = HOST_MEMORY_GUARDRAIL_MB` exactly. Committed **608**, safe
available **992**; the candidate at the defaults (304) **admitted**, at 1072
**refused**. **The control did not hold as written and produced D1608**: the
Sheet A5 manifest needs `shared_buffers_mb: 896`, `shm_size_mb: 896` **and**
`memory_limit_mb: 1280` before `_validate_memory_budget` accepts it.

**And one precondition the plan did not state**, measured because Run 3
depends on it: `/etc/agentic-postgres/projects/<key>/` is `drwx------ root
root` and **`op` cannot read a deployed document** (**D1606**). Admission and
`doctor capacity` are root readers; an unprivileged run must report `unknown`
and fail closed.

**The five ADRs** are written, Accepted, and indexed: **0221** (capacity is
declared, admission decides, a reading reports), **0222** (every project
service bounded in processes, the long-running nine in CPU), **0223** (the
collector consumed, every series names its project), **0224** (the rotation's
window is closed by the step-6 deploy and `retire` reports it), **0225** (a
secret's value is checked against its declared kind at materialization).
Each carries the rig numbers above in its Context rather than a summary of
them. Every rig script and output is in the scratchpad (`rigs/`), because
WSL's `/tmp` does not survive a shutdown.

### Run 2 — capacity declared and read: schema 3, the reader, `doctor capacity`

**Read first:** `schemas/host.schema.json` whole; `src/agentic_postgres/
host_config.py:74-80,252-263`; `host.example.yaml` whole; `tests/contract/
test_host_manifest.py` whole; `src/agentic_postgres/diagnosis.py:80-124,
375-434,527-578,586-650`; `bin/doctor.py:1-120,498-546,682-780`;
`bin/doctor.sh:200-245`; `src/agentic_postgres/container_exec.py:88-120`;
`src/agentic_postgres/database_observation.py:83-93` (the parse-then-pass
shape, ADR 0159); `tests/contract/test_container_selectors.py:243-335`
(`bin/doctor.py` is a `DEPLOYED_DOCUMENT_READERS` member: a parsed blob that
is not the deployed document **must not be named `document`**, D1184);
`bin/fleet.py:84-99` (`read_document` validates the deployed document).

1. **`schemas/host.schema.json`**: `schema_version` enum `[2, 3]`; a
   `capacity` object (`additionalProperties: false`; four `integer`
   members, `minimum: 1`, all required) that is **required when
   `schema_version` is 3** (a `oneOf`/`if-then` in the schema — the run
   reads how `config.validate_against_schema` reports a failure and asserts
   the message names `capacity`). `host_config.load_host_manifest` unchanged
   in signature; `host_config.declared_capacity(manifest) -> Declared | None`
   (a frozen dataclass `Declared(memory_mb, reserve_memory_mb, disk_gb,
   reserve_disk_gb)`; `None` for schema 2) — the ONE reader of the four
   fields (D816). `host.example.yaml` → `schema_version: 3` and:
   ```yaml
   capacity:
     # Declared, never measured into this file. `apg doctor capacity` reports
     # what the host says and this block says what the operator promises.
     memory_mb: 3814          # `free -m` total on 2026-09-19 (D52, D959)
     reserve_memory_mb: 2214  # 3814 - 1600: the release's guardrail is what
                              # projects may claim in unreclaimable memory
                              # across the host; the reserve holds the OS, the
                              # edge (31 MB), page cache and each sidecar's
                              # anon above its claim (D959: 348 MB against 304)
     disk_gb: 38              # `df -BG` at the Docker root on 2026-09-19
     reserve_disk_gb: 8       # below this much free at the Docker root no new
                              # project is admitted; twice the larger cluster's
                              # PGDATA rounded up (doctor: disk headroom)
   ```
   `test_host_manifest.py` gains the four proofs §2 names; the existing
   `:433` walk of documented field paths must still resolve (add the four to
   whatever document it walks — read `:400-440` first).
2. **`src/agentic_postgres/capacity_reading.py`** (new, pure; `__all__`
   explicit; module docstring citing ADR 0221 and ADR 0195's two halves):
   - `MEMINFO_PATH = "/proc/meminfo"`; `parse_meminfo(text: str) ->
     dict[str, int] | None` — MiB for `MemTotal`, `MemAvailable`, `SwapTotal`
     (kB // 1024); `None` when any of the three is absent (rig 31b's text
     is the fixture).
   - `Figure` — `value: int | None`, `reason: str` (empty when measured);
     `Reading(declared: Declared | None, mem_total, mem_available, swap_total,
     docker_root_free_gb, docker_root_total_gb, volumes: dict[str, Figure],
     committed: dict[str, int], ceilings: dict[str, int])` all `Figure`s
     except the two dicts.
   - `committed_from_documents(documents: dict[str, dict], *, exclude:
     str | None) -> dict[str, int]` — `database.budget.unreclaimable_mb` per
     key; a document missing the member is **omitted with its key returned
     in a second tuple** so the caller reports it (never counted as 0).
   - `ceilings_from_inspect(payload: str) -> dict[str, int]` — parses
     `docker inspect` JSON of every container labelled `apg.project.key`
     (`HostConfig.Memory` bytes → MiB; `0` means unbounded and is **listed
     under `unbounded`, not summed**), grouped by the label's value.
   - `decide(reading: Reading, *, candidate_key: str, candidate_unreclaimable_
     mb: int, candidate_is_deployed: bool) -> Decision` — `Decision(outcome:
     "admitted" | "refused", lines: tuple[tuple[str, str], ...], reason:
     str)`; the six lines in the order **declared, reserved, committed,
     requested, safe available, suggested action** for memory and a second
     six for disk (declared, reserved, free, requested `n/a — no per-project
     disk claim (D1596)`, safe available, suggested action); rules as §1
     D1583/D1584/D1592/D1596; **any `Figure.value is None` that the rule
     needs → `refused` with the figure's reason** (fails closed).
   - `render_decision(decision) -> str` — the text `bin/admit.py` and the
     deploy print; `EXIT_ADMISSION_REFUSED = 12`.
   - `SUGGESTED_ACTION_MEMORY` — one sentence naming the three manifest
     fields that move `unreclaimable_mb`, *retire a project*, and *raise
     `capacity.memory_mb` only after `doctor capacity` shows the host has
     it*.
   `tests/contract/test_capacity_reading.py` — the proofs §2 names plus a
   synthetic-document control.
3. **`diagnosis.capacity_report(reading: Reading) -> tuple[Check, ...]`** —
   one `Check` per figure group (`declared`, `memory`, `disk`, `committed`,
   `ceilings`), each `OK` with `_pairs(...)` evidence or `UNKNOWN` with the
   figure's reason; **`WARN` and `PROBLEM` never** (a test greps the function
   body for the two names). `bin/doctor.py`: `--reading {capacity,usage}` and
   `--host FILE` (required with `capacity`; refused with the eleven checks,
   exit 2); `probe_capacity(host_manifest, root) -> Reading` reads
   `/proc/meminfo` (**directly, no exec**), `shutil.disk_usage(docker_root)`
   with the root from `docker info --format '{{.DockerRootDir}}'`. **Which
   runner for which command:** `docker info`, `docker inspect` and `docker
   volume inspect` are not execs into a container and go through the
   module's own bounded `run()` `:67-94`; anything that runs INSIDE a
   container goes through `container_exec.run` (D1593); every deployed document
   under `--root` loaded with `bin/fleet.py:84-99`'s `read_document` shape
   (copy the validation, name the loop variable `deployed`, not `document`).
   Text output through `diagnosis.report(...)` unchanged; `--json` through
   `diagnosis.document(...)` unchanged. `bin/doctor.sh`: verb arms
   `capacity)`/`usage)` before the flag loop, mapping to `--reading`; usage
   block gains the two lines; `--help` with a verb exits 0 without root
   (`test_a_verbs_help_is_a_read_and_needs_nothing`, `test_cli_contract.py:
   459`). `COMMANDS_WITH_VERBS` gains `bin/doctor.sh`.
4. **`tests/contract/test_doctor_readings.py`** (new; `pytestmark` before
   the first test, D1240): the four proofs §2 names for `capacity`; the
   `usage` ones land in Run 4 and the module says so.
5. **Battery (≥6)**: `parse_meminfo` returning 0 for a missing MemAvailable
   (killed by the unknown-not-zero proof); `committed_from_documents`
   counting a document without the member as 0 (killed); `decide` charging
   the candidate twice on a redeploy (killed by the redeploy proof written in
   Run 3 — **this mutation is recorded as owed to Run 3**); `capacity_report`
   emitting `WARN` when available < 10 % (killed by the two-verdicts proof);
   the schema enum back to `[2]` (killed by the example's load); the example's
   `reserve_memory_mb` off by one (killed by the guardrail-equality proof).

**Targeted:** `test_host_manifest`, `test_capacity_reading`,
`test_doctor_readings`, `test_diagnosis`, `test_doctor_redaction`,
`test_container_selectors`, `test_cli_contract` (a verb-taking command
joined the control), `test_apg_dispatcher`, `test_fleet` (it runs the
doctor), `test_honest_readers`, the twelve readers of `host.example.yaml`
(§4). `python bin/render-config.py --bounds-doc --check` (if `CROSS_FIELD_
RELATIONS` gained a line for the guardrail equality, `--write`). Push; read
CI.

**Done.** 2026-09-19. `host.yaml` schema 3, `capacity_reading.py`,
`diagnosis.capacity_report` and the `capacity` verb. **Battery 9/9 killed**,
every control green in the same invocation, every file restored byte-identical
to its snapshot. Targeted: **32 modules, 1749 passed, 2 skipped** (both
documented skips in `test_root_script_policy`). `ruff check` exit 0;
`shellcheck bin/doctor.sh` clean. The bounds doc was **not** regenerated:
`bin/render-config.py:44` calls `config.bounds_table()` with its default, which
is `project.schema.json`, so no generator reads the host schema's new minimums.

**The reading, on this workstation, against a root it cannot list:**

```
(node): 3 ok, 0 warning, 0 problem, 2 unknown
  ok       declared — 3814 MiB RAM and 38 GiB disk declared, 1600 MiB claimable
  ok       memory — 6635 MiB available of 7786 MiB, 2048 MiB swap
  UNKNOWN  disk — docker_root_free_gb, docker_root_total_gb could not be read:
           the Docker data root could not be stat'd
  UNKNOWN  committed — the claim of <project state root> could not be read,
           so the committed total is not a total
  ok       ceilings — 0 MiB of mem_limit across 0 project(s) -- ceilings, not
           reservations (D767)
```

**Which figure read `unknown` here, and why.** *Disk*: `docker info` reports a
data root inside the Docker Desktop VM, which WSL cannot `stat` — the right
answer, arrived at honestly, and it is why the figure is a `Figure` and not an
`int`. *Committed*: the `--root` given does not exist. **That second one was a
defect when the run began.** The first version swallowed `project_keys`'
`OSError` into an empty list and reported `committed 0 MiB across 0 projects`
with verdict `ok` — and `decide` would then have handed a candidate the entire
declared budget on the strength of a directory it failed to open. Found by
running the command rather than by a test, repaired with
`PROJECT_ROOT_UNREADABLE`, and now the ninth mutation in the battery.

**Exit codes, every one read from inside WSL** (`$?` after `wsl bash -lc` reads
Git Bash's status, and it printed a confident `EXIT=0` over a run that exited 6
before this was caught): unreadable root **6**; `--reading capacity` with no
`--host` **2**; `usage` **2** (Run 4 builds it — refused rather than answered,
because a reading that returns `OK` having measured nothing is this session's
own defect class in this session's own code); `--host` without a verb **2**; no
`--project` and no verb **2**; `doctor.sh capacity --help` **0 without root**;
`doctor.sh capacity --host …` as a non-root user **3**.

**Two things the plan did not anticipate, both caught by a contract that was
already there:**

1. **`bin/doctor.py` may not read the inventory.** The first version imported
   `bin/fleet.py` by path to reuse its `read_document`, and
   `test_fleet.py::test_nothing_in_the_release_reads_the_inventory` refused it
   — ADR 0185 and FLEET-INV-002: the inventory is the end of a chain, never a
   link in one. Replaced by `read_deployed`, a **non-fatal sibling of
   `load_document`** standing on the same two library primitives
   (`deployed_path`, `validate_deployed_document`). The difference between the
   two is the point: `load_document` answers *diagnose THIS project* and exits
   on a missing document; `read_deployed` answers *what has this node
   committed* and carries the reason back, because stopping would turn a
   partial answer into no answer. **The scan strips `#` comments, not
   docstrings**, so the replacement's docstring had to stop spelling the path
   as well — the scan cannot tell a mention from a use and is not meant to.
2. **`test_the_manifest_is_version_two` had to move.** Replaced, not relaxed:
   the new test pins the example at 3 **and** pins the accepted enum to exactly
   `[2, 3]`, so an enum widened without the example moving, or an example moved
   without the enum, both fail here. That is stricter than what it replaced,
   which is what CLAUDE.md §6 permits under an ADR (0221).

**And one test of mine was weak.** `test_a_redeploy_charges_only_the_other_
projects` asked for 900 MiB, which fits whether or not the candidate is
excluded — so it passed against a `committed_from_documents` that ignored
`exclude` entirely. Found while writing the battery, not while writing the
test. It now asks for **1200**, which straddles the two answers (1296 available
excluded, 992 double-charged), and asserts both sides.

**Also added beyond the plan**, because the schema's own policy is that both
directions fail closed: **a schema 2 manifest carrying a `capacity` block is
refused** rather than ignored. Ignoring it would leave four numbers an operator
typed, believed they had declared, and that `declared_capacity` returns `None`
for — D816 in the file whose whole job is to be read. Nine proofs in
`test_host_manifest.py`, including a scan asserting `declared_capacity` is the
**only** reader of the four fields.

**Owed to Run 3**, as the plan says: the deploy's step-0 call, `bin/admit.sh`,
and the `admission-refused` rehearsal arm. `--reading usage` refuses until Run
4. Registry entries land in Run 6 with `CURRENT_SESSION` (D690).

### Run 3 — admission at the deploy, `bin/admit.sh`, the rehearsal, and the limits

**Read first:** `bin/deploy-project.py:86-89,176-182,482-556,1922-1995`;
`deploy.sh:11-16,200-295`; `src/agentic_postgres/preflight.py` whole (the
voice); `bin/fleet.py:84-133` and `tests/contract/test_fleet.py` (a `bin/`
command driven against a fixture `--root` — the shape `test_admission.py`
copies); `tests/contract/test_deploy_command.py`; `src/agentic_postgres/
config.py:207-335,594-643`; `src/agentic_postgres/rendering.py:625-660,
1668-1760,1850-1905`; `compose.yaml` — every `services:` entry (the twenty
lines §0 lists) and `:154-180`; `src/agentic_postgres/dev_environment.py`
(grep `mem_limit`; if the dev cluster carries one it carries the new key
too, D979); `rehearsal.py:79-107,137-139,259-271,650-692,754-763,884-959`;
`bin/rehearse.py:124,272-302,336-475,727-736`; `bin/rehearse.sh`'s usage
block; `tests/contract/test_rehearsal.py:1-80` and its `disk-threshold`
proofs; `tests/contract/test_container_exec.py:38,144-170` (`requires_docker`
imported from `test_image_contracts`); rig 31a's and 31b's outputs.

1. **`bin/admit.py`** (new; imports only `agentic_postgres` and `yaml`, ADR
   0093; header block naming exit codes 0, 2, 3, **12**): `--host FILE`
   (required), `--project FILE` (required), `--root DIR` (default
   `deployed_output.PROJECT_STATE_ROOT`), `--json`, and the four injections
   `--declared-memory-mb N`, `--reserve-memory-mb N`, `--declared-disk-gb
   N`, `--reserve-disk-gb N` (each overrides the declaration for this run
   and is printed on the `declared`/`reserved` line as `(injected)` so a
   rehearsal's reading cannot be mistaken for the host's — the
   `disk_headroom` evidence pattern). The candidate's key and claim come from
   `config.load_project_manifest` → `naming` (the key) and
   `config.database_budget(manifest["database"])["unreclaimable_mb"]`;
   **nothing is rendered and nothing under `.generated` is touched** (a
   proof asserts it). `candidate_is_deployed = (root / key /
   "outputs.json").is_file()`. Prints `render_decision`, exits 0 or 12.
   **`bin/admit.sh`**: the `bin/doctor.sh` preamble shape (root required
   for a real run because `docker inspect` needs the socket; `--help` free),
   forwards verbatim. Both `chmod 755` and `git add`ed before the suite
   (D1188); `SHELL_COMMANDS` and `PYTHON_COMMANDS` gain them.
2. **The deploy**: `bin/deploy-project.py` imports `EXIT_ADMISSION_REFUSED`
   and, **inside step 0 after the preflight report and before `step("1.
   Render`**, builds the `Reading` with the same probe the doctor uses
   (move `probe_capacity` into a small `bin/lib`-free shape: the probe
   functions live in `bin/doctor.py` today; the deploy imports nothing from
   `bin/` (ADR 0093 bars `bin`-to-`bin` imports — check `test_repository_
   contract.py`), so the probe's three `docker` reads are **re-spelled in
   `deploy-project.py` through its own `run()`** and the parsing stays in
   `capacity_reading` — one parser, two probes, the doctor/deploy split ADR
   0157 already draws); calls `decide`; on `refused`, prints the six lines
   and `fail(EXIT_ADMISSION_REFUSED, …)`. `deploy.sh:11-16` gains the `12`
   line. `docs/session-02-operator-guide.md:259-276` gains the row. The
   `--render-only` path never reaches step 0's admission (it does not run
   `deploy-project.py`'s main deploy — confirm by reading `deploy.sh:200-
   295` and say so in the Done).
3. **`tests/contract/test_admission.py`** (new): a fixture `--root` with
   two synthetic deployed documents (built from `tests/fixtures/outputs-
   v10.json` with the keys and `unreclaimable_mb` rewritten — validate each
   with `deployed_output.validate_deployed_document` so the fixture shares
   the code's belief, question 6), a `host.yaml` at schema 3 in `tmp_path`,
   a candidate manifest from `project.example.yaml` with `shared_buffers_mb`
   raised. **`docker inspect` is not available in the suite, and no hidden
   fixture switch is added for it** (a switch only a test sets is D1509's
   shape). `ceilings` are a REPORT line and never a rule input, so
   `admit.py` treats a failed `docker inspect` as `ceilings: unknown` and
   still decides; the proof runs with no Docker and asserts the `ceilings`
   line reads `unknown (docker inspect: …)`. The nine proofs §2 names, each
   driving `bin/admit.py` as a subprocess (D1114).
4. **Rehearsal `admission-refused`**: `SCENARIOS` gains the name;
   `Facts` gains `host_manifest: str | None` and `project_manifest: str |
   None`; `bin/rehearse.py` gains `--host FILE` and `--manifest FILE`
   (refused with exit 2 when the scenario is `admission-refused` and either
   is absent; ignored otherwise); planner `_admission_refused(facts)`:
   `induce=(Action(what="nothing is changed: the reserve is injected into
   admit with --reserve-memory-mb"),)`, `observe=(Observation("admission_as_
   declared", argv=(admit_py, "--host", …, "--project", …, "--json"),
   expect="the host's own decision, whatever it is", control=True),
   Observation("admission_refused", argv=(… "--reserve-memory-mb",
   f"{INJECTED_RESERVE_MB}"), expect="refused"))` with
   `INJECTED_RESERVE_MB = 1_000_000_000` beside the disk constants;
   `reverse=(Action(what="nothing was changed; nothing to undo"),)`;
   `verdict()` gains the arm (the injected reading's `outcome == "refused"`,
   the control's outcome in `{"admitted", "refused"}` and its `declared`
   line **not** marked injected); `observe()` in `bin/rehearse.py` gains the
   arm (runs the argv, parses `--json`, stashes both decisions as
   `admission_evidence`); `bin/rehearse.sh`'s usage lists the ninth scenario
   and its two flags; `DEPLOYED_DOCTOR_CHECKS` unchanged (the reader is
   `admit`, not the doctor). `test_rehearsal.py` gains the two proofs §2
   names (the recorded-runner shape the module already uses).
5. **The limits**: `config.SERVICE_RESOURCE_DEFAULTS: dict[str, dict[str,
   int | str]]` for the nine, **values from rig 31b by D1600's rule** (the
   provisional table below is replaced and the Done prints
   measured-peak → default for each), `config.SHORT_LIVED_PIDS_LIMIT = 64`;
   `rendering.COMPOSE_ENV_KEYS` gains `<SERVICE>_PIDS_LIMIT` and
   `<SERVICE>_CPUS` for the nine (`POSTGRES_`, `PGBOUNCER_`, `POSTGREST_`,
   `DOCS_`, `METRICS_`, `STORE_`, `AUTH_`, `STORAGE_`, `MCP_`);
   `build_compose_env` emits them beside the memory lines; `compose.yaml`:
   `pids_limit: ${<SERVICE>_PIDS_LIMIT:?required}` and `cpus:
   ${<SERVICE>_CPUS:?required}` on the nine (each beside its `mem_limit` or,
   for the three that have none, beside `read_only`/`cap_drop`, with a
   one-line comment citing ADR 0222), `pids_limit: 64` on the eleven; the
   metrics and store literals stay as `mem_limit` is. If
   `dev_environment.py` carries a `mem_limit`, it carries `pids_limit` from
   the same default. `tests/contract/test_process_limits.py` (new): the
   eight proofs §2 names; the fork proof runs `${POSTGRES_IMAGE}` by digest
   with `--pids-limit 8` and asserts rig 31a's failure text, its control
   with no flag.

   | Service | provisional `pids_limit` | `cpus` |
   |---|---|---|
   | postgres | 256 (≥ 56 + 32) | "2.0" |
   | pgbouncer | 64 | "1.0" |
   | postgrest | 128 | "1.0" |
   | docs | 64 | "1.0" |
   | metrics | 128 | "1.0" |
   | store | 128 | "1.0" |
   | auth | 256 | "1.0" |
   | storage | 128 | "1.0" |
   | mcp | 128 | "1.0" |

6. **Battery (≥8)**: `decide` ignoring `candidate_is_deployed` (killed by
   the redeploy proof); the disk rule inverted (killed); exit 12 → 4 in
   `admit.py` (killed by the exit proof and the header proof); the admission
   call moved below `step("1. Render` (killed by the AST proof); `verdict()`
   arm removed (killed); the injected `reserve` not echoed as `(injected)`
   (killed by the rehearsal proof asserting the control's line is not
   marked); `pids_limit` removed from `docs` in `compose.yaml` (killed by the
   every-service walk); `SHORT_LIVED_PIDS_LIMIT` 64 → 63 (killed by the
   power-of-two proof); the fork proof's expected text loosened to `""`
   (killed by the control, which would then also match).

**Targeted:** `test_admission`, `test_capacity_reading`, `test_process_
limits`, `test_rehearsal`, `test_deploy_command`, `test_printed_commands`,
`test_compose_contract`, `test_auth_service_shape` (it reads every
service's env references, `:403`), `test_secret_origin`, `test_alert_rules`,
`test_metrics_surface`, `test_runtime_override`, `test_cli_contract`,
`test_repository_contract`, `test_dev_command` and `test_dev_environment`
(if `dev_environment.py` moved), `test_capacity_envelope`, `test_render_
isolation`, `test_project_manifest`, plus `git grep -ln "COMPOSE_ENV_KEYS\|
build_compose_env" -- tests/contract`. `bin/apg.sh generate --check --project
project.example.yaml` (the compose env is not a client input; confirm exit
0). `python bin/render-config.py --bounds-doc --check`. Push; read CI.

**Done.** 2026-09-19. Admission decides at the deploy's step 0 and on its
own through `bin/admit.sh`; twenty services are bounded in processes and nine
in CPU; the ninth rehearsal scenario exists. **Battery 11/11 killed**, every
control green in the same invocation, every file restored byte-identical.
Targeted: **37 modules, 2192 passed, 2 documented skips**. `ruff check` 0,
`shellcheck` clean on both new scripts. Derived artefacts all current:
`--bounds-doc --check` 0, `apg generate --check` 0, `render-acceptance-matrix
--check` 0, `app-contract --check` 0, `mcp-contract check` 0.

**The measured-peak → default table** (rig 31b's `pids.peak`, both projects,
the rule being *the larger of 64 and four times the peak, rounded up to a
power of two*, postgres additionally ≥ `max_connections + 32`):

| service | peak | 4 × peak | `pids_limit` | `cpus` |
|---|---|---|---|---|
| postgres | 28, 29 | 116 | **128** (≥ 88) | `"2.0"` |
| postgrest | 18, 18 | 72 | **128** | `"1.0"` |
| metrics | 16, 16 | 64 | **64** | `"1.0"` |
| store | 16, 16 | 64 | **64** | `"1.0"` |
| auth / storage / mcp | ≤ 12 | ≤ 48 | **64** | `"1.0"` |
| docs, pgbouncer | 9, 9 | 36 | **64** | `"1.0"` |
| the eleven short-lived | ≤ 9 | — | **64** literal | none |

**The fork text, verbatim**, asserted by the proof: `fork: retry: Resource
temporarily unavailable` then `fork: Resource temporarily unavailable`; the
control reaches `spawned=20` and reads `pids.max` = `max`.

**`cpus` as a string IS accepted**, so no `deploy.resources.limits.cpus`
fallback was needed. Validated against real Compose rather than inferred: all
fourteen profiles selected, **20 of 20 services resolved**, `cpus` normalising
to an int (`postgres` 2, every sidecar 1) and `pids_limit` to 128/64 exactly as
the table says. The first two attempts at that check exited 0 and 1 over
`services: {}` and a dependency error — a check that cannot fail is worse than
no check, and both would have passed for the wrong reason had the exit code
been the whole of what was read.

**`--render-only` never reaches admission**, read out of `deploy.sh`: the
branch `exec`s `bin/render-config.py` directly (`deploy.sh:289-292`) and never
`bin/deploy-project.py`, so step 0 does not exist on that path. `--render-only`
keeps working with no host and no root, unchanged.

**Five things the run found rather than assumed:**

1. **The probe is in the library, not spelled three times.** The plan said the
   deploy would re-spell the three `docker` reads through its own `run()`,
   because ADR 0093 bars a `bin/`-to-`bin/` import. That would have been three
   copies of one reading across `doctor`, `admit` and the deploy — §7 question
   5 exactly, where a repair reaching one caller is invisible in the others
   until a deploy admits what the doctor refused. `capacity_probe.read` is the
   one reading; each command still passes **its own runner**, which is the part
   that genuinely differs (the deploy's general `run` has no timeout at all, so
   step 0 got a bounded `_probe_run` — an unbounded `docker` call there could
   hang a deploy before anything had happened). **D1610.**
2. **The disk figure was undeterminable unprivileged, and the rule was
   therefore unsatisfiable.** `shutil.disk_usage(docker_root)` raises ENOENT on
   this workstation (`/var/lib/docker` **does not exist** — Docker Desktop's
   daemon reports a path inside its own VM) and EACCES on a CI runner (0710
   root). `decide` fails closed on an undetermined disk figure, correctly — so
   **every admission would have been refused for a reason that has nothing to
   do with capacity**, and it would have been found on the host, mid-trip. The
   figure is now measured from the nearest readable ancestor and **the path is
   reported**: the same filesystem answers `statvfs` identically, and where it
   would not, an operator reads the path rather than a plausible number.
   **D1611.**
3. **`induced=False` was wrong, and the tree said so.** §4 asks for
   `induced: false` on the rehearsal record. In the tree `induced=False` means
   *recorded, not exercised* — provider-loss is its only member and `verdict()`
   returns the literal `"recorded"` for it. `disk-threshold` changes nothing
   either, injects a threshold into its reader's argv, and is `induced=True`.
   `admission-refused` is disk-threshold's shape exactly, so it takes
   disk-threshold's flag; marking it False would have quietly downgraded what
   the rehearsal claims to have proved. **D1612.**
4. **D1184 fired, from the guard that exists for it.** The observe arm parsed
   `admit --json` into a local called `document`, and
   `test_container_selectors` reported `outcome` and `declaration_injected` as
   members a `bin/` command invents off a deployed document. The guard is
   right — in a `bin/` command that name means the deployed document — and the
   local is now `decision`.
5. **`apg dev` carries no memory limit at all**, so ADR 0222's rule does not
   reach it: `run_arguments` is a deliberately minimal `docker run`
   (*"Nothing is in this list by accident"*) with no `--memory` and no `-c`. The
   proof is written as the **invariant** rather than deleted — if that argv ever
   bounds memory it bounds processes in the same change — because the next
   person to cap the dev cluster's memory is exactly the person who will not
   think about its processes. **D1613.**

**Also:** the two committed fixtures were re-rendered, because
`.generated/fixture-alpine-dev` predated the eighteen new compose keys and
`test_compose_contract::test_model_renders` failed on it — correctly. Both now
carry 18 resource keys each.

### Run 4 — the collector consumed: the label, the retention, the endpoint, `doctor usage`

**Read first:** `src/agentic_postgres/rendering.py:1190-1406,2529-2561`;
`.generated/fixture-alpha-dev/otelcol.yaml` and `prometheus.yaml` (the
rendered shapes); `src/agentic_postgres/runtime_override.py:225-330`;
`services/auth-api/app/mcp_metrics.py` whole; `mcp_tracing.py:160-205`;
`mcp_telemetry.py:180-200`; `mcp_runtime.py:437-465`; `settings.py:250-260,
439-480`; `compose.yaml:937-1081,1543-1660`; `tests/contract/
test_metrics_surface.py:200-270,390-490`; `test_alert_rules.py:55-70,
240-310`; `test_mcp_tracing.py:270-330`; `test_mcp_runtime.py:330-350`;
`test_auth_service_shape.py:330-350,395-410`; `tests/deployment/
test_session14_observability.py:234-261` (the `store_query` shape);
`bin/backup.py:238-260,314-336`; `src/agentic_postgres/backup_report.py:
73-134`; `bin/doctor.py:356-404,661-711` (the ledger read and
`AGENT_RECORD_QUERY`); `bin/fleet.py:53-58` (a statement with an integer this
program validated and no caller text); rigs 31c and 31d.

1. **`build_otel_config(router_names, domain, project_key)`**: the
   `prometheus` exporter gains `const_labels:\n      project: <key>` (rig
   31c's spelling); the docstring's *"reversal is the scrape filter and
   nothing else"* sentence (`:1214-1216`) is rewritten to name the second
   reversal; **every caller edited** (`rendering.py:2529-2541` passes
   `identity.key`; grep `build_otel_config` under `tests/`); the two rendered
   fixtures regenerated by the gate's step 2 (`.generated/fixture-*` are
   committed — read `bin/session-01-check.sh`'s step 2 for the command that
   regenerates them and run it). `test_metrics_surface.py` gains the two
   label proofs. `runtime_override.STORE_RETENTION_DAYS = 14` and
   `test_alert_rules.py`'s retention proof (D1589). `pids_limit` on
   `metrics` and `store` landed in Run 3.
2. **The endpoint**: `settings.py` `MCP_VARIABLES` gains `APG_OTLP_ENDPOINT`
   (optional; `load_mcp()` exposes it as `otlp_endpoint: str | None`; **a
   value that is not `http://` + a hostname of the compose service name +
   `:4318/v1/metrics` is refused at load** — the runtime may not be pointed
   off the project's network by an environment line, and the check names
   the expected shape, not the value); `compose.yaml`'s mcp environment
   gains `APG_OTLP_ENDPOINT: http://metrics:4318/v1/metrics`;
   `test_mcp_runtime.py` and `test_auth_service_shape.py` gain the two
   proofs §2 names; `FORBIDDEN_VARIABLES` unchanged (a URL is not a
   credential; the guards at `test_mcp_runtime.py:343` and
   `test_auth_service_shape.py:340` run).
3. **The call**: `mcp_runtime.create_mcp_app()` after `lock = load_lock(...)`
   `:453`: `mcp_metrics.configure(endpoint=settings.otlp_endpoint,
   service_name="apg-mcp", tool_names=<the lock's tool names, in the shape
   `build_server` reads them>, outcomes=<the outcome vocabulary
   `mcp_telemetry` passes to `record()` at `:194-197`>)`; its `bool` is
   logged at `warn` level when `False` with the sentence *metrics are not
   exported: no APG_OTLP_ENDPOINT* (the tracing docstring's voice). The
   `mcp_metrics.py` module docstring, if it says nothing calls `configure`,
   is rewritten; `mcp_tracing.py:177-202` stays. `test_mcp_tracing.py:283-
   322`'s enumeration is **replaced** by `test_exactly_one_module_configures_
   metrics_and_none_configures_tracing` (ADR 0223; D1119 applies if the
   replaced test is a registry node id — check with `git grep -n
   "test_mcp_tracing.py::" tests/acceptance-registry.yaml` and move the id
   in the same commit). `test_metrics_surface.py::test_configure_with_an_
   endpoint_creates_both_instruments` uses an in-process OTLP http endpoint
   that cannot connect (`http://127.0.0.1:9/v1/metrics`) and asserts
   `configure` returned `True` and both instruments are non-`None` — the
   export failure is the SDK's and rig 31d showed it never raises.
4. **`doctor usage`**: `diagnosis.usage_report(figures: UsageFigures) ->
   tuple[Check, ...]` (`UsageFigures` in `capacity_reading.py` — eight
   `Figure`s: `database_bytes`, `pgdata_kb`, `wal_kb`, `repository_bytes`,
   `audit_rows`, `idempotency_rows`, `requests_total`, `tool_calls_total`),
   two verdicts only. `bin/doctor.py` `probe_usage(document) ->
   UsageFigures`: `pg_database_size(current_database())`, `du -sk` of
   PGDATA and of `PGDATA/pg_wal`, all through `container_exec.run(container,
   "psql"/"du", …, user=…)` with `.stdout` parsed to `int` **before** any
   `diagnosis.*` call (ADR 0159); the repository through `bin/backup.sh
   --outputs … info --json` exactly as `probe_repository` `:407-426` does,
   reading the new `repository_bytes` member that `backup_report.summarise`
   gains (`sum(backup["info"]["repository"]["delta"] …)`, `None` when any
   backup lacks it — `test_backup_report.py` gains two proofs against the
   module's existing captured-JSON fixture); audit and idempotency counts
   through `AGENT_RECORD_QUERY` unchanged; the two store figures through
   `container_exec.run(f"apg-{key}-store-1", "wget", "-q", "-Y", "off",
   "-O", "-", f"http://127.0.0.1:{STORE_PORT}/api/v1/query?query=…")` with
   `sum(traefik_service_requests_total)` and `sum(agent_tool_calls_total)`
   (URL-quoted; the container name derived from `document["project"]["key"]`
   and `STORE_SERVICE` — a **derived** name, ADR 0002), the JSON's
   `data.result[0].value[1]` parsed to `int`, **and every result series'
   `metric.project` asserted equal to the key before the figure is accepted**
   — a mismatch is `unknown` with the reason *the store answered for
   another project*. `bin/doctor.sh usage --project KEY [--json]`.
   `test_doctor_readings.py` gains the three `usage` proofs; the module's
   docstring records that the probes are proved on the trip
   (`test_session31_capacity.py`, Run 6).
5. **Battery (≥6)**: `const_labels` value → the domain (killed by the
   key-only proof); retention `14d` → `15d` in compose (killed); the
   endpoint check accepting any `http://` (killed by a proof planting
   `http://example.com/`); `configure` called before `load_lock` (killed by
   the ordering proof's AST read); `usage_report` returning `WARN` above a
   size (killed); `repository_bytes` summing `size` instead of `delta`
   (killed by the fixture proof, whose two numbers differ).

**Targeted:** `test_metrics_surface`, `test_alert_rules`, `test_runtime_
override`, `test_rendered_migrations`, `test_image_contracts` (it runs the
collector), `test_mcp_runtime`, `test_mcp_tracing`, `test_mcp_telemetry`,
`test_mcp_budgets`, `test_auth_service_shape`, `test_doctor_readings`,
`test_diagnosis`, `test_doctor_redaction`, `test_backup_report`,
`test_backup_command`, `test_container_selectors`, `test_acceptance_registry`
(if a node id moved), plus `git grep -ln "build_otel_config\|MCP_VARIABLES\|
summarise(" -- tests/contract`. Push; read CI.

**Done.** 2026-09-19. The collector is consumed: every series it exports
names its project, the store's retention has a constant and a test, the mcp
runtime configures its two instruments for the first time in production, and
`doctor usage` answers. **Battery 11/11 killed**, controls green, every file
restored byte-identical. Targeted: **34 modules, 1481 passed, 0 skipped**.
`ruff check` 0; `shellcheck` clean on both scripts.

**The rendered `otelcol.yaml` diff** (both fixtures regenerated):

```
 exporters:
   prometheus:
     endpoint: 0.0.0.0:8889
+    const_labels:
+      project: fixture-alpha-dev
     metric_expiration: 60s
```

Six of seven series carry it and **`target_info` does not** (D1604), which the
contract test names as an exception rather than folding away.

**Rig 31d's memory number against the limit**: the provider, reader and
exporter cost **25.2 MiB RSS** (25756 KiB, measured) against `MCP_MEMORY_LIMIT`
**384 MiB** — **6.6 %**. The `endpoint=None` control cost **0 KiB**, so the
figure is the instruments' and not the interpreter's.

**The store query's exact URL**, derived and quoted rather than typed:

```
http://127.0.0.1:9090/api/v1/query?query=sum%28agent_tool_calls_total%29
```

`sum(...)` and not a bare selector, because the exporter promotes the SDK's
`service.instance.id` to an `instance` label and that id is a fresh UUID per
process — every restart of the mcp container mints a new series, and reading
one would undercount silently afterwards (D1609). It is fetched with
`container_exec.run(f"apg-{key}-store-1", "wget", …)` because the store is
routed nowhere, the container name is derived (ADR 0002), and **every series
returned must carry `project=<key>`** or the figure is `unknown` with *the
store answered for another project*.

**The finding that moved the design (D1614).** The plan had `doctor usage`
read a new `repository_bytes` member off `bin/backup.sh info --json`. **That
output is not a report — it is the deployed document's `backup_state` block,
and `bin/deploy-project.py:1390` consumes exactly it.** A member added there
would have travelled into `outputs.json` and been refused by the outputs
schema — a schema move this session explicitly does not take (D1591). So
`summarise` gains the figure as planned and a **new verb** serves it,
`bin/backup.sh usage [--json]`; a proof asserts `backup_state` still does not
carry it. Found by reading the consumer, not by the deploy failing.

**`repository_bytes` sums `delta`, never `size`**, and the captured fixture
tells them apart: over `info-full-and-incr.json` the deltas total **4,245,284**
and the sizes **8,153,434**, because an incremental's `size` counts the bytes
of the full it references. Summing `size` would report a repository larger
than the provider has ever held. `None` when any backup lacks the member —
never a partial sum, which would read as a smaller repository rather than an
unread one.

**The endpoint is narrow on purpose.** `APG_OTLP_ENDPOINT` is refused unless
it is exactly `http://metrics:4318/v1/metrics`, derived in the test from
`COLLECTOR_SERVICE` and `COLLECTOR_OTLP_HTTP_PORT` rather than retyped, and
**the refusal never echoes the address it was given** — a proof plants a
sentinel hostname and greps the message for it. A metric exporter that cannot
reach its endpoint logs and carries on (rig 31d), so a wrong address would
move a project's telemetry somewhere nobody reviewed, silently.

**Two tests moved, neither weakened.** `test_span_has_a_product_caller_and_
configure_deliberately_does_not` became
`test_exactly_one_module_configures_metrics_and_none_configures_tracing`,
which asserts everything it did **and** that exactly `mcp_runtime` configures
metrics — two callers would mean two meter providers exporting the same
instruments under one service name (ADR 0223 authorises it; the replaced test
is not a registry node id, checked). Run 2's
`test_the_usage_verb_is_refused_until_it_answers` was replaced by a proof of
what the verb now does, including that it prints nothing for a project it
never found.

**Owed, and the reason is environmental:** the five derived-artefact checks
(`--bounds-doc --check`, `apg generate --check`, `render-acceptance-matrix
--check`, `app-contract --check`, `mcp-contract check`) were run green at Run
3's close and **were not re-run at Run 4's**, because WSL's command channel
stopped answering (`Wsl/Service/0x8007274c`) after the targeted suite passed —
the VM and its filesystem stayed reachable over `\\wsl$`, only `wsl.exe -e`
did not. Nothing Run 4 touched is an input to any of those five generators
(the registry, the ADR index, the project schema and the api contract are all
unchanged), and CI runs the full check on the push. **Run 5 re-runs them
first.**

### Run 5 — the carried-in items: the fixture, the kind check, the rotation's report, the triage, the counts, the threat row

**Read first:** `tests/deployment/test_session24_studio.py:230-260,689-
838`; `migrations/templates/0007-api-surface-convergence.sql:255-275`;
`src/agentic_postgres/bootstrap_statements.py:250-269`; `tests/deployment/
conftest.py` (grep `authenticated` — how other live proofs mint a token for
that role; `dev-token.sh --role authenticated` is the operator's path and
the fixture should share the code's belief, question 6); `src/agentic_
postgres/secrets_contract.py:530-560`; `bin/materialize-secrets.py:150-260`;
`tests/contract/test_secret_contract.py:100-140,360-395`; `src/agentic_
postgres/jwt_keys.py:440-510,560-575`; `bin/rotate-signing-key.py:180-210,
440-480`; `tests/contract/test_jwt_keys.py` or wherever `retire_rotation`
is proved (`git grep -ln retire_rotation -- tests/`); `docs/operator-guide.md:
791-1055`; `docs/plans/session-28-implementation-plan.md` Appendix R;
`tests/contract/test_deployment_suite_shape.py:100-230`; each of the 22
orphans' docstrings; `docs/threat-model.md:13-34,150-160`; `docs/scope-
closure.md:907-913`; `tests/conftest.py:82-167`.

1. **D1572, the fixture**: `two_owners_one_relation` and `auditor` create
   their subjects with the **`authenticated`** role name
   (`project_a["database"]["roles"]["authenticated"]` — confirm the key in
   the document's `roles` map) so the `POST /rpc/create_note` each performs
   is one migration 0007 grants; the docstring says why (`0007:261-271`)
   and that `project_admin`'s administrative power is its token's scope,
   not its role (`bootstrap_statements.py:255-263`). `pytest --setup-plan
   tests/deployment/test_session24_studio.py -k query_view` with
   `APG_LIVE_HOST=1 APG_PROJECT_A_OUTPUTS=<an op-owned copy in the
   scratchpad>` set: planned, not skipped. **The trip is its second
   execution; §7 says so.** Grep every reader of the two fixtures
   (`auditor`, `two_owners_one_relation`) in the module and confirm none
   asserts the `project_admin` role name.
2. **D1578 / ADR 0225**: `secrets_contract.check_value_kind(kind: str,
   value: str) -> str | None` — `rsa_private_pem`: both `-----BEGIN PRIVATE
   KEY-----` and `-----END PRIVATE KEY-----` present, `len(value) >= 1000`;
   `random_hex`: `re.fullmatch(r"[0-9a-f]+", value)`; an unknown kind →
   the reason names the kind (the schema forbids it, but the function is
   the one reader); **the returned reason is built from `kind`, the
   delimiter names and the length threshold only**. `bin/materialize-
   secrets.py:219-235`'s loop calls it after `read_secret` and before the
   write; a reason → `OperatorError(8, f"{secret['name']}: {reason}")` (the
   module's error class and exit-8 constant — read `:1-60`). The five proofs
   §2 names; the sentinel proof plants `SENTINEL-DO-NOT-PRINT` inside a bad
   value and asserts it appears in neither stream.
3. **D1599 / ADR 0224**: `jwt_keys.retire_rotation` — when `state["retire_
   after"] is None` **and** `len(state["verification_kids"]) == 1` **and**
   `state.get("verifier_acknowledgements") is None`, return the state
   **unchanged** (**no new document member** — a `retired_by` note would be
   a schema move for a sentence) and let `bin/rotate-signing-key.py`'s
   `retire` print *the rotation was retired by the deploy that published one
   key; nothing to do* and exit 0; the *no rotation is in flight* refusal
   stays for a two-key state with no deadline (validate_key_state refuses
   that anyway, `:567-569` — read it and say which branch is reachable).
   `FOLLOW_UP["promote"]` gains the sentence *take this deploy only after the
   document's `retire_after` has passed; the deploy closes the window*.
   `docs/operator-guide.md` §15 *The seven steps*: step 6 gains the wait
   (read `retire_after` from the deployed document with the
   `rendered-document`/`python3 -c` line the section already uses for the
   `jwt` member; wait until it has passed; then deploy), and *What this
   rotation does not close* names the `render-jwks`/`verification_kids`
   question. Appendix R of the Session 28 plan is **not edited** (a released
   record); §15 is the operator form. The existing `retire_rotation` proofs
   run unchanged; one new proof for the reported outcome.
4. **D1595, the counts**: the four comment edits; `git grep -n
   APG_ADMIN_PASSWORD_FILE -- tests/ bin/session-30-check.sh` and the
   measured outcome written into the Done and the row.
5. **D1527, the threat row**: `docs/threat-model.md` gains
   `THR-NOISY-NEIGHBOUR` in the table's nine-column shape — *Attacker
   capability*: a project's own workload (an agent's tool calls, a
   connection storm, a fork storm) run without malice; *Protected asset*:
   the neighbouring project's latency and the host's stability; *Prevention*:
   per-service `mem_limit`, `pids_limit`, `cpus`, `max_connections` per
   cluster, admission against a declared capacity; *Detection*: `doctor
   capacity|usage`, the store's series per project; *Residual risk*: **the
   effect of one project's load on the other has not been measured** —
   Session 35's noisy-neighbour measurement (stage plan §5 *Session 35*),
   and disk I/O is unbounded; *Acceptance requirement IDs*: `NODE-LIMIT-001`,
   `NODE-ADMIT-001`; *node IDs*: the fork proof and the refusal proof;
   *Target session*: 31. The `## Scope` sentence at `:159-160` gains *a
   neighbour's load is bounded, not a claim about availability*.
   `test_acceptance_registry` checks the row's referential integrity
   (`threat-model.md:3-15`), so this lands green only in Run 6 with the
   entries — write it now, run the registry test in Run 6.
6. **D1597, the triage.** For each of the 22 in `KNOWN_UNREGISTERED`: read
   its docstring and assertions; `git grep -n "<module>::" tests/acceptance-
   registry.yaml` to see which requirements that module already feeds; pick
   the requirement whose `description` states the property (e.g. the four
   `test_session2_edge.py` proofs → the `DEP-EDGE`/`SEC` entries that name
   HSTS, ACME, the health route; the five `test_session2_host.py` proofs →
   the `SEC-HOST`/`DEP-HOST` entries that name ufw, sshd, the daemon
   configuration; the five `test_session2_isolation.py` → `DEP-ISO-001`/
   `-002`; the three `test_session9_agent_writes.py` and the `test_session8`
   one → the `AGT-*` denial/revocation entries; `test_session11` → the
   `API-*` request-id entry; `test_session12` → `EVD-`/`DEP-ISO-` (the
   classifier's control); `test_session14` → the `OPS-`/`DEP-` metrics-route
   entry; `test_session20` → the `TEN-*` entry). Append the node id;
   extend the description by one sentence only if the property is not
   already stated. **When no entry states it**, write a new entry in that
   module's family (`target_session: 31`, listed in §2's addendum in the
   Done, its claim added to `CLAIMS` — host, undeclared). **When the proof
   proves nothing a requirement should state** (the run expects this for
   `test_the_classifier_can_tell_the_categories_apart` if it is a self-test
   of a test helper — read it), delete it and say why. The tuple ends empty
   or names each survivor with the session that owes it. The table of 22
   decisions is in the Done. `test_deployment_suite_shape`'s equality guard
   and `test_acceptance_registry` (D1119) run — the latter green only in
   Run 6 for any `target_session: 31` entry (D1555's shape; say which).
7. **The envelope**: `capacity.UNMEASURED` gains `Unmeasured(subject="apg
   doctor capacity and usage, on the deployment", reason="the readings are
   host reads and store queries under root; nothing here has a host",
   unblocked_by="the Session 31 trip (Sheet A5)")`; `MEASURED_AGAINST`
   is **not** widened (the readings' cost is a claim about the doctor, not
   about the collector image — D1519's note in the observability report
   stands as a §10 item). `python bin/render-capacity-envelope.py --write`.
8. **Battery (≥5)**: the fixture's role back to `project_admin` (**recorded
   as unreachable offline**, D493 — the trip is the proof); `check_value_
   kind` accepting a PEM with one delimiter (killed); the reason carrying
   `value[:20]` (killed by the sentinel proof); the materialize call moved
   after the write (killed by the ordering scan); `retire`'s new outcome
   returned when two kids are published (killed by the new proof's control);
   one orphan left in the tuple that is now registered (killed by the
   equality guard).

**Targeted:** `test_secret_contract`, `test_secret_origin`,
`test_materialize_secrets` (or the module that drives `bin/materialize-
secrets.py` — `git grep -ln materialize-secrets -- tests/contract`),
`test_jwt_keys`/the rotation modules found by grep, `test_rotate_signing_key`
if it exists, `test_documentation_index`, `test_session12_documented_path`
(the guide moved), `test_deployment_suite_shape`, `test_deployment_module_
shape`, `test_suite_shape`, `test_capacity_envelope`, `test_environment_
gates`, `test_evidence_claims`, `test_cli_contract` (the comment moved),
`test_runtime_override` (the comment moved); `test_acceptance_registry` per
item 6. Push; read CI.

**Done.** 2026-09-19. The carried-in items are closed: the Studio fixture
creates its subjects in the role that holds the grants they need, a secret's
value is checked against its declared kind before it is written, `retire`
reports instead of refusing for the wrong reason, four stale counts are
corrected against a measurement, the fifth is measured, and **twenty of the
twenty-two orphans are node ids of a requirement**. **Battery 8/8 killed**,
every control green, all six files restored byte-identically; one mutation
recorded as unreachable offline (D493). Targeted: **33 modules, 1575 passed,
6 skipped** (each legitimate: one chown needing privilege, two shell scripts
that run no Python, three Studio proofs with no host). `ruff format --check`
and `ruff check` 0; `shellcheck` clean. Eight divergence rows, **D1615-D1622**.

**The `--setup-plan` line**, with the environment SET (D671, D676):

```
APG_LIVE_HOST=1 APG_PROJECT_A_OUTPUTS=/home/gmpar/apg-deployed-docs/alpha-dev-outputs.json \
  python -m pytest --setup-plan -q -p no:randomly \
  tests/deployment/test_session24_studio.py -k query_view
```

**Planned, not skipped**, and the whole chain plans: `auditor` →
`launched_studio` → `two_owners_one_relation` →
`test_the_query_view_shows_the_human_their_own_rows_and_not_anothers`. The
document's roles map answers `authenticated` → `apg_alpha_dev_authenticated`.
**The trip is its second execution**, and §7 says so.

**D1572's cause is larger than the plan stated, and the product is right
twice.** The plan said the fixtures write through an API only `authenticated`
may write to. They also READ through one: migration 0007 grants `EXECUTE` on
`api.create_note` to `{{authenticated}}, {{agent_writer}}` after revoking it
from `PUBLIC`, **and migration 0004 grants `SELECT` on `app.notes` to those
two and `{{agent_reader}}`**. `project_admin` is on neither list. So the RLS
proof this module exists for could not have run even if the seeding had
worked — the read would have been refused before `notes_owner_select` was
consulted. Both fixtures now take `authenticated`, which is also what
`tests/deployment/conftest.py`'s `_registered_subject` takes for every other
live subject in the suite, and what the subject holds administratively is its
token's scopes (`bootstrap_statements.py:258-263`, `API-ADMIN-001`). Nothing in
the module asserts the `project_admin` role name — grepped, four mentions
remain and all four are prose.

**The `APG_ADMIN_PASSWORD_FILE` reading (D1595's fifth, now D1619).**

| Question | Measured |
|---|---|
| Does any proof read it? | A **fixture** does — `admin_password` in `tests/deployment/conftest.py`, which SKIPS with the variable's name when it is unset. No test module names it as a constant. |
| Is it in `tests/conftest.py`'s roster? | **No**, and D1278 decided that deliberately. |
| Can it join? | **No.** `test_every_registered_variable_is_used` counts an entry used when a test declares it on a marker or names it as an `ast.Constant`, and `all_test_modules()` is `TESTS_ROOT.rglob("test_*.py")` — **conftests are not walked**. It would read as unused on the day it was added. |
| What was actually wrong? | `bin/session-30-check.sh:1522` says it is *"in the roster and exported here"*. **It is not in the roster**, and seven gates carry that sentence. |

Corrected in `session-30-check.sh` (the gate Run 6 derives 31's from), with the
export line now naming the fixture that consumes it. Widening
`all_test_modules()` to conftests is a change to a scan several guards share
and is §10's.

**The other four counts, measured rather than recounted:** Session 30 has
**six** claims, **five** offline and one host (`contract_compile_output`,
`exec_discipline`, `mirror_retry`, `release_reading_ref`, `suite_shape`; host
`studio_tenant_read`) — `test_cli_contract.py` said FOUR, `evidence_claims.py`
said five/four, `test_evidence_claims.py` said four/one. And
`apg.project.key` is carried by **nine** services, not the comment's six nor
the plan's eight (D1620).

**The 22-row triage (D1597).** Twenty went to a requirement that **already
stated their property** — which is what the count was really measuring: not
twenty-two unstated properties, but twenty-two proofs nothing had connected to
the requirement they were written for. Ten requirements gained one sentence;
three named it already and the node id joined in silence.

| # | Proof | → | Sentence added |
|---|---|---|---|
| 1 | `test_session11_operations::test_a_malformed_request_id_header_does_not_destroy_the_write` | `OPS-LOG-001` | yes |
| 2 | `test_session12_isolation_matrix::test_the_classifier_can_tell_the_categories_apart` | `DEP-ISO-001` | yes |
| 3 | `test_session14_observability::test_the_deployed_document_reports_the_metrics_route_it_observed` | `OPS-READ-002` | no — *a status carried over rather than observed* is its own words |
| 4 | `test_session20_tenant::test_alpha_declares_no_set_and_holds_none_of_betas_objects` | `TEN-SET-001` | yes |
| 5 | `test_session2_edge::test_the_deployed_document_agrees_with_the_live_route` | `OPS-HEALTH-001` | yes |
| 6 | `test_session2_edge::test_hsts_is_present_on_the_https_response` | `SEC-TLS-001` | yes |
| 7 | `test_session2_edge::test_the_acme_state_file_matches_the_recorded_environment` | `SEC-TLS-001` | (same sentence) |
| 8 | `test_session2_edge::test_the_health_route_is_reachable_only_through_the_edge` | `OPS-HEALTH-001` | (same sentence) |
| 9 | `test_session2_host::test_sshd_limits_authentication_attempts` | `SEC-HOST-001` | yes |
| 10 | `test_session2_host::test_the_edge_publishes_exactly_eighty_and_four_four_three` | `SEC-NET-002` | (same sentence) |
| 11 | `test_session2_host::test_the_docker_user_chain_is_reachable_from_forward` | `SEC-NET-002` | yes |
| 12 | `test_session2_host::test_ufw_denies_incoming_by_default` | `SEC-HOST-001` | (same sentence) |
| 13 | `test_session2_host::test_the_daemon_runs_the_configuration_we_installed` | `SEC-DOCKER-001` | yes |
| 14 | `test_session2_isolation::test_the_two_projects_are_actually_distinct` | `DEP-ISO-002` | yes |
| 15 | `test_session2_isolation::test_an_unknown_hostname_is_not_served` | `DEP-ISO-002` | (same sentence) |
| 16 | `test_session2_isolation::test_the_recorded_networks_are_project_scoped` | `DEP-ISO-002` | (same sentence) |
| 17 | `test_session2_isolation::test_neither_project_joins_the_others_network` | `DEP-ISO-002` | (same sentence) |
| 18 | `test_session2_isolation::test_each_project_holds_only_its_own_secret_generation` | `DEP-ISO-001` | (same sentence) |
| 19 | `test_session8_agent_plane::test_a_read_only_agent_can_neither_discover_nor_invoke_a_write_on_the_deployment` | `AGT-WRITE-001` | no — the docstring already names it |
| 20 | `test_session9_agent_writes::test_a_revoked_token_fails_its_next_read_write_and_direct_request` | `SEC-REV-001` | no — the docstring already names it |
| 21 | `test_session9_agent_writes::test_a_get_against_the_deployed_audit_rpc_is_refused` | **stays** | a NEW entry, Run 6 |
| 22 | `test_session9_agent_writes::test_the_get_that_was_refused_wrote_nothing` | **stays** | a NEW entry, Run 6 |

**21 and 22 are the reason the triage was worth taking.** ADR 0136's category
— that an rpc which WRITES is ineffective over GET, because PostgREST runs a
GET in a **read-only transaction** and `25006` surfaces as 405, while
volatility protects nothing (D490, both predictions wrong in opposite
directions) — is stated by **no requirement in the file**. A property measured
that carefully and registered nowhere is exactly what the scan exists to
surface. `KNOWN_UNREGISTERED` is **22 → 2**; Run 6 writes the entry and empties
it.

**Number 2 was not deleted, and the plan expected it might be** (D1622). It is
the anti-vacuity control for `_classify`, which drives `DEP-ISO-001`'s other
three proofs; a classifier answering `not_authority` for everything would make
the matrix report a clean bill of health forever. A control belongs to the
claim it protects.

**ADR 0224's outcome is registered without a new entry.** The plan named
`IDN-ROTATE`'s next free number; **there is no `IDN-ROTATE` family**.
`SEC-KEY-002` — *"Prepare, acknowledge, promote, retire"* — is the rotation's
requirement, and the three new proofs joined it with one sentence. No
`target_session: 31` entry, so nothing here waits on Run 6.

**ADR 0225's own claim was wrong and is amended (D1618).** *"The
delimiter-and-length pair catches every malformation actually observed"* —
measured against the four shapes of 2026-09-19, it catches **one**. The rule
implemented is stricter than the one decided: each delimiter must be an
encapsulation boundary **on a line of its own** (RFC 7468, and what `openssl
rsa` enforces), which takes it to **two of four**. The other two are not shape
questions and no check of this kind reaches them — a byte-identical re-read is
a well-formed key, just the previous one, and a mistyped provider key NAME
means no value is fetched at all. The ADR carries the four-row table. The
body's wrapping is deliberately unconstrained: a key wrapped at 76 rather than
64 is legitimate, and a false refusal mid-window is the worst possible one.

**The battery found three weak proofs of mine, not three weak products**, and
each is worth the row:

* dropping `PEM_END` from the check **survived**, because every
  footer-missing value in the test was also shorter than
  `PEM_MINIMUM_LENGTH` — the length floor was doing the work and the footer
  requirement was never proved. Every case is now long enough to clear the
  floor, and asserts that it is;
* leaking `value[:20]` **survived**, because the planted sentinel sat at
  offset 64. A sentinel says *this exact string did not appear*; it says
  nothing about a leak that misses its position. There is now a
  position-independent check: no twelve-character window of the value may
  occur in the reason;
* dropping `len(verification_kids) == 1` from `retire`'s new arm **survived**,
  because `prepare_rotation` leaves the acknowledgements at `{}` and the
  acknowledgement condition refused the two-key state on its own. A two-key
  state with `None` acknowledgements is reachable —
  `bin/deploy-project.py:2964` carries the previous value forward when the set
  holds two keys — and it now has its own arm.

All three were then killed.

**The threat row is Run 6's (D1621)**, measured: it fails
`test_threat_model_requirement_ids_exist_in_the_registry` naming
`NODE-LIMIT-001` and `NODE-ADMIT-001`, and landing it here would push a red
`main` and hold it there until Run 6. **The row, ready to paste:**

```
| `THR-NOISY-NEIGHBOUR` | A project's own workload, run without malice: an agent's tool calls, a connection storm, a fork storm, a runaway query | The neighbouring project's latency, and the host's stability | Per-service `mem_limit` and `pids_limit` on every service, `cpus` on the nine long-running ones, `max_connections` summed across six claimants per cluster, and admission against a capacity the host declares -- a deploy that would not fit is refused before it renders | `apg doctor capacity` and `apg doctor usage` on each project; the store's series, every one of which names its project | **The effect of one project's load on the other has not been measured.** Every control here is a ceiling declared per service, and nothing yet says what a neighbour actually feels when one of them is reached -- Session 35's noisy-neighbour measurement. Disk I/O is bounded by nothing at all: there is no `blkio` limit, and a project writing continuously shares one device with the other's WAL | `NODE-LIMIT-001`, `NODE-ADMIT-001` | `tests/contract/test_process_limits.py::test_a_container_cannot_fork_past_its_pids_limit`, `tests/contract/test_admission.py::test_a_candidate_that_does_not_fit_is_refused_with_exit_twelve` | 31 |
```

The `## Scope` sentence it owes is also Run 6's: *a neighbour's load is
bounded, not a claim about availability*.

**Run 4's three CI failures were repaired first**, in their own commit
(`f9c6eb5`, CI **success**), before any of this: a `ruff format` diff the
run could not produce because WSL's command channel was down; a compose-model
subscript the environment-gate scanner reads as a variable consumption, met
the way `test_client_fixtures.py` and `test_completion_command.py` already
meet it; and a hand-rolled `McpSettings` stub that did not grow the setting
Run 4 gave the runtime to read, so `create_mcp_app` threw `AttributeError`
inside the try/except and the failure surfaced two assertions later as
`KeyError: 'lock'`. All three were invisible to Run 4's targeted list and
visible to the gate — §7's question 5, in its usual shape. **The five
derived-artefact checks Run 4 owed all exit 0**, and were re-run again at this
close.

### Run 6 — the bump, the registry, the gate, and the trip's proofs

`VERSION` **1.9.0** and `CURRENT_SESSION` **31**, in one commit with
everything the bump owes (Session 30 Run 6's shape, `session-30-
implementation-plan.md:1339-1400`):

- **`src/agentic_postgres/__init__.py`**: `CURRENT_SESSION = 31` and a `#:`
  paragraph naming the nine requirements, the nine claims, the five ADRs,
  that `host.yaml` schema 3 is additive, that no outputs schema moved, and
  that the minor is a judgement above `requires patch` (D1561).
- **The registry**: every §2 entry and every Run 5 triage entry, node ids
  from `pytest --collect-only -q` (D1236); `ID_PATTERN` gains `NODE`;
  `CLAIMS`, `OFFLINE_CLAIMS` (six), `CLAIM_INTRODUCED_IN` (nine + Run 5's);
  `KNOWN_UNREGISTERED` as Run 5 left it; `python bin/render-acceptance-
  matrix.py --write`.
- **`tests/deployment/test_session31_capacity.py`** (new; `pytestmark`
  with `live_host`, `p0`, and `requires_environment("APG_LIVE_HOST",
  "APG_HOST_MANIFEST", "APG_CANDIDATE_MANIFEST", "APG_PROJECT_A_OUTPUTS",
  "APG_PROJECT_B_OUTPUTS", "APG_REHEARSAL_EVIDENCE_DIR")` — every name in
  `ENVIRONMENT_VARIABLES`, D687): the eight live proofs §2 names. Each calls
  the product's command (`bin/admit.sh`, `bin/doctor.sh capacity|usage
  --json`) as a subprocess (D1114); the `free -m` / `df -Pk` controls are
  the proof's own reads on the host (root), compared within 5 % for
  MemTotal and exactly for the Docker root's total KiB; the admitted control
  copies the candidate manifest to `tmp_path` with `database.shared_buffers_
  mb` reset to the default and runs `admit.sh` again; the rehearsal proof
  reads the newest `rehearsal-<key>-admission-refused-*.json` under
  `APG_REHEARSAL_EVIDENCE_DIR` (written on Sheet A5 BEFORE the sweep) and
  asserts `verdict`, `induced: false`, and the control's `declared` line
  unmarked. `pytest --setup-plan` with the six variables set: **eight
  planned, none skipped** (D671).
- **`tests/conftest.py`** gains `APG_HOST_MANIFEST` and
  `APG_CANDIDATE_MANIFEST` (D687 comment).
- **`apg generate` regenerated and committed** (D1238): `templateVersion`
  `1.9.0`; `generate --check` exit 0.
- **Both release pages gain a `1.9.0` row** (`docs/upgrade-guide.md:79-97`'s
  table and `:17`; `docs/operator-guide.md:22,29`; `README.md:7`). The
  row's text: *capacity declared in `host.yaml` (schema 3, additive) and
  admission at every deploy (exit 12; ADR 0221); `pids_limit` on every
  project service and `cpus` on nine (ADR 0222); the collector consumed —
  the runtime's two instruments exported, a `project` label on every
  series, retention a constant (ADR 0223); `apg doctor capacity|usage`;
  `bin/admit.sh`; rehearsal `admission-refused`; the rotation's window
  closed by the deploy (ADR 0224); a secret's kind checked at
  materialization (ADR 0225); no migration; **this deploy recreates every
  container, the database included, because its definition moved**.*
  `docs/operator-guide.md` gains **§16 *The node as a finite resource***:
  the four numbers and how to choose them, `doctor capacity|usage`, what a
  refusal prints and the three things it suggests, `admit.sh` as the
  decision printed and not taken; §5 *Every day, every week* gains the two
  readings; §12 gains *the deploy was refused with exit 12*.
  `docs/fleet-operations.md` §6 (the new-project steps) gains *`admit.sh`
  before the first deploy*. `test_documentation_index` and
  `test_session12_documented_path` run.
- **`bin/session-31-check.sh`**, derived from `bin/session-30-check.sh` by
  diff (D1482, D1488): `readonly SESSION=31`; the header and usage block
  **rewritten whole** (the usage block is a heredoc and its lines are
  script lines — no data-scope literal in it, D1563); `--mode offline`
  names the six offline claims and writes `evidence/session-31-offline.
  json`; `--mode host` names the three host claims, gains `--candidate-
  manifest FILE` (exported as `APG_CANDIDATE_MANIFEST`, readable-file
  precheck like `--kit-dir`'s) and exports `--host`'s path as
  `APG_HOST_MANIFEST`; `--redeploy-before-file` given on THIS trip
  (deployment_convergence re-taken); the `--kit-dir` paragraph still says
  `kit-2026-09-11` (D1282); `run_suite "p0 and not future and not live_host
  and not external"` verbatim (D1242); the `--rotated-from-file` usage line
  added (Session 30 §10's item); step 1 carries `bin/lib/*.sh` (D1564);
  `SHELL_COMMANDS` gains it; `chmod 755` before `git add`. **`tests/
  contract/test_session_thirty_one_gate_modes.py`** copied from thirty's:
  `SESSION = 31`, `SESSION_PREVIOUS_NUMBER = 30`, the six offline claims,
  `test_no_gate_exists_for_the_session_that_took_the_trip` **deleted**
  (there is no skipped session between 30 and 31 — the docstring says so),
  a new `test_host_mode_exports_the_two_new_gates` (`APG_HOST_MANIFEST`,
  `APG_CANDIDATE_MANIFEST` in the export block).
- Derived documents: `render-acceptance-matrix.py --write`, `render-config.
  py --bounds-doc --write`, `render-mcp-catalog.py --write`, `render-
  evaluation-report.py --write`, `render-capacity-envelope.py --write`,
  `bin/app-contract.sh --check`, `bin/mcp-contract.sh check`, `bin/apg.sh
  generate --check --project project.example.yaml`. No `freeze-lock`.
- **The price, read not chosen** (D704): render `project.example.yaml` from
  `be987cf` in a throwaway worktree `/tmp/apg-be987cf` (D1485: never the
  checkout's own `.generated/fixture-alpha-dev`) and from the bump commit;
  `bin/upgrade.sh plan --project <fixture> --candidate … --json` → expect
  `bump minor`, `requires patch`, `OK`, `reasons []`; the leaves are
  `template_version` and whatever the compose env's new keys show as (if
  the rendered document publishes them — read the output and list every
  leaf in the Done). A `major` is §9's stop.
- `bin/apg.sh release-reading` on the bump commit, quoted (expect
  `tag_is_owed`, `1.9.0`, last tag `1.8.0`, ADRs 220 → 225).

**`bin/session-01-check.sh` runs once, on a clean tree** (commit, gate,
repair, commit, gate again), then **`bin/session-31-check.sh --mode
offline`** writes `evidence/session-31-offline.json` carrying the six new
offline claims plus the nineteen inherited, every one `passed`. Then `git
diff --stat` against this run's list, one line each, **before** the push
(D1116). Then CI by full SHA. **And then nothing** — no tag (D1425).

**Done.** 2026-09-19. The bump landed all-or-nothing (D690): `VERSION`
**1.9.0**, `CURRENT_SESSION` **31**, **ten requirements and ten claims** --
six declared offline, one more than any session has declared, and four host.
`NODE` joined `ID_PATTERN`. **`KNOWN_UNREGISTERED` is empty**, 22 -> 2 -> 0.
Seven divergence rows, **D1623-D1629**.

**`bin/session-01-check.sh`: PASSED at `33d82e0`** -- `6225 passed, 0 failed,
3 skipped, 0 errors`, P0 collected 6615, 0 future placeholders, two rendered
projects, **0 identity collisions, 0 floating image refs**. Its FIRST run, at
`02f8b22`, exited 1 on three failures, and D1629 is the row: all three were
the release paragraph and none was the product.

**`bin/session-31-check.sh --mode offline`** wrote `evidence/session-31-
offline.json`: **24 claims, 24 passed**.
The six this session declares -- `capacity_declared`, `capacity_reading`,
`admission_decision`, `process_limits`, `telemetry_bounded`,
`secret_kind_checked` -- are all `passed`. **Eighteen were inherited, not the
nineteen the plan predicted** (D1628), measured from `OFFLINE_CLAIMS` and
`CLAIM_INTRODUCED_IN` rather than counted: `CLAIMS` goes 135 -> 145.

**The plan's verdict and its leaves** (D704, and the rig is D1624's):

```
bump                      minor
requires                  patch
verdict                   ok
reasons                   []
changes                   []
operator_digests_moved    []
differences               ONE -- template_version, 1.8.0 -> 1.9.0
```

**Every leaf, listed: there is one.** Both documents are 5,948 bytes. The
compose environment's eighteen new keys do NOT appear, which this run's plan
left open and this reading closes (D1625): `pids_limit` and `cpus` are written
into `compose.env`, and `outputs.json` is not that file.

**Neither side rendered in the checkout** (D1624). The plan's parenthesis
warns about the installed side; the candidate side has the same problem,
because `project.example.yaml` renders under the key of one of the four
fixtures the gate compares for collisions. The installed side is a git
worktree at `be987cf`; the candidate is a `tar`-piped copy of the working
tree, which is byte-for-byte what the bump commit contains.

**And the one row of ADR 0162 this release hits is invisible to that command**
(D1626). `host.yaml` goes schema 2 -> 3, an operator manifest bump the table
prices at a minor, and `host.yaml` is an operator INPUT that appears in no
rendered document -- so `requires patch` is a floor computed without the field
that would have raised it. Reported rather than folded, and `upgrade` is left
alone: teaching it to read an operator input would make it a second reader of
`host.yaml` beside `host_config` (ADR 0002, D816).

**`apg release-reading`**: `tag_is_owed`, `VERSION 1.9.0`, no tag on HEAD, last
tag `1.8.0` at `be987cf9632d`, **ADRs 220 -> 225 moved**, 14 commits and 67
files since. **No tag here** -- the deploy, the sweep and the tag land on one
commit in that order, and that is Run 7 (D1425).

**The eight live proofs plan and do not skip** (D671, D676). With the six
variables set, `--setup-plan` lists all eight and the fixture chain under
them; with none set, eight SKIP and none errors, which is what a gate variable
in the closed roster buys (D687). `APG_HOST_MANIFEST` and
`APG_CANDIDATE_MANIFEST` joined that roster and the gate exports both --
`--host` has existed since Session 2 and was never exported, because until
this release nothing in the suite read the HOST's manifest.

**The gate was derived by diff and its header and usage block rewritten
whole** (D1482, D1488, D853, D858). One `session-30` reference survives on
purpose: the line recording what it was derived from.
`test_no_gate_exists_for_the_session_that_took_the_trip` was not merely
deleted but REPLACED (D1627) -- it carried a second assertion, that the gate
this session derived FROM exists, which is the anti-vacuity guard under every
`SESSION_PREVIOUS` assertion in the module. **30 -> 31 is the first
consecutive pair since 24 -> 25.**

**One product change came out of writing a live proof** (D1623). `apg doctor
capacity` reported the disk figures and never said WHICH filesystem it
measured -- only `decide` did. The probe walks up to the nearest readable
ancestor and an ancestor can be a different mount, so the reading was handing
an operator a number they had no way to check against `df`; the alternative
for the control was hardcoding `/var/lib/docker`, which is the assumption
D1611 took out of the product. The reading names the path now.

**Carried in from Run 5, both measured there and deferred:**
`THR-NOISY-NEIGHBOUR` and its `## Scope` sentence, which
`test_acceptance_registry` refused until `NODE-LIMIT-001` and
`NODE-ADMIT-001` existed (D1621); and the last two orphans, now
`AGT-METHOD-001`.

**Targeted:** 34 modules, **1575 passed, 13 skipped** (all legitimate: two
shell scripts that run no Python, eight Session 31 live proofs and three
Studio proofs with no host). The sweep-selector guard collects 6237/6699
(D1242). `ruff format --check` and `ruff check` 0; `shellcheck` clean over
`deploy.sh`, `bin/*.sh`, `bin/lib/*.sh` and `libexec/*`. `apg generate
--check`, `app-contract --check` and `mcp-contract check` all exit 0; the
acceptance matrix, the bounds table, the mcp catalog, the evaluation report
and the capacity envelope are current. **No `freeze-lock`** -- no migration
moved.

### Run 7 — the trip: the host declares, both projects redeploy, a third is refused, one sweep, the tag

**Before the day** (agent, offline): read Session 30's Run 7 and Sheets
A1–A4 (`session-30-implementation-plan.md:1566-1707,2112-2213`),
`docs/upgrade-guide.md` §3, `docs/operator-guide.md` §12 (D977);
`pytest --setup-plan` for `test_session31_capacity.py`, `test_session24_
studio.py -k query_view`, `test_session11_operations.py` (with
`APG_REDEPLOY_BEFORE_FILE` pointing at a two-field JSON in the scratchpad)
and `test_session14_observability.py` with the variables set (D671, D676),
outputs kept; CI green on the bump commit by full SHA; host scripts staged
under `/home/op` derived from `s30-*.sh` (read each first; `EXPECTED=`,
the session number, the gate name; the renders script renders all FOUR —
D1507); the third manifest `/home/op/s31-third.yaml` written from
`project.example.yaml` with `project.name` `third` (a key that collides with
no render, checked against `naming` offline), `database.shared_buffers_mb:
896`, and every provider/domain field the host's `project.alpha.yaml` has
(read it over SSH as `op`; **no secret value lives in a manifest**);
the external script in WSL derived from Session 30's (D466); WSL's outbound
TCP probed on the day (CLAUDE.md §1).

**The day, in order.** `op` steps are the agent's over SSH; **`sudo` steps
are the operator's**, on Sheets A1–A6 in the appendix, **one sheet per
outcome, read before the next is issued** (D1510):

1. *(op)* Transport: bundle, `scp`, `git bundle verify`, `git fetch`, **`git
   rev-parse FETCH_HEAD` equal to the pushed SHA**, `git checkout -B main
   FETCH_HEAD`, `cat VERSION` → `1.9.0`, porcelain 0; `uv pip sync` only if
   `requirements-dev.*`/`.python-version` moved since `be987cf` (D1491).
2. *(Sheet A1, sudo)* the reads: `upgrade.sh check` both; `doctor.sh` both
   (11 ok); `fleet.sh`; `backup.sh … info` alpha; `free -m`; `df -Pk
   /var/lib/docker`; `nproc`; `dr-kit.sh export … /home/op/kit-<date>-pre`.
   **Every number written on the sheet.**
3. *(op)* **Sheet A2 — the declaration**: `cp host.yaml
   /home/op/host.yaml.pre-s31`; edit `host.yaml` to `schema_version: 3` with
   the `capacity` block from `host.example.yaml`, `memory_mb` and `disk_gb`
   from Sheet A1's readings, `reserve_memory_mb: memory_mb − 1600`,
   `reserve_disk_gb` twice the larger PGDATA from the doctors' `disk
   headroom` evidence rounded up to a whole GiB; **then the four renders as
   `op`** (`--render-only`, which loads `host.yaml` and validates schema 3
   before anything with `sudo` is issued); `bin/upgrade.sh plan` both as
   `op`? — no, `plan` reads root paths: it is Sheet A3's first line.
4. *(Sheet A3, sudo)* `upgrade.sh plan` both (`bump minor`, `OK`); then
   **the sentinel recipe** (Session 30 Sheet A2 steps 1–5 verbatim with
   `s31-` in the title and `/root/s31-redeploy-before.json`); then alpha's
   deploy under `script(1)`, nothing after it. Expect exit 0; step 0 prints
   the admission decision **`admitted`** with its six lines (the first
   admission decision on production — write the six numbers on the sheet);
   step 6 applies nothing (ledger 33); **every container recreated** (their
   definitions moved — `docker ps` ages all younger than the deploy); step
   7's document `deployed_through_session 31`; `doctor.sh --project
   alpha-dev` 11 ok; `migrate.sh … status` 33 `[X]`, `Pending: 0`.
5. *(Sheet A4, sudo)* beta the same (ledger 33 + 2).
6. *(Sheet A5, sudo)* **the session's own proofs, before the sweep**:
   `bin/admit.sh --host host.yaml --project /home/op/s31-third.yaml` →
   **exit 12**, six lines, `requested 1072`, `safe available 992`; the
   control: `sed 's/shared_buffers_mb: 896/shared_buffers_mb: 128/'
   /home/op/s31-third.yaml > /home/op/s31-third-default.yaml` (op, before
   the sheet) and `admit.sh` on it → **exit 0, `admitted`**;
   `bin/rehearse.sh admission-refused --outputs <alpha> --host host.yaml
   --manifest project.alpha.yaml` → the record under `evidence/`, verdict
   `passed`, then `rehearse.sh reverse` (a no-op that clears the in-progress
   file); `bin/doctor.sh capacity --host host.yaml` and `--project` each;
   `bin/doctor.sh usage --project alpha-dev` and `beta-dev` — **the first
   Prometheus query anyone has run on this deployment**; every line written
   on the sheet; `time` on each doctor line for the envelope.
7. *(op, then Sheet A6)* op-owned copies installed (`install -o op -g op -m
   0600 … /home/op/<key>-dev-outputs.json`, both, sudo); the agent confirms
   both name the new `source_commit` before the sweep line is issued
   (D1510). **The one sweep**: `setsid nohup bash /home/op/g31-host.sh
   > /dev/null 2>&1 < /dev/null &` holding the full `session-31-check.sh
   --mode host` line — every declaration Session 30's sweep passed, plus
   `--host host.yaml` (already there), `--candidate-manifest /home/op/s31-
   third.yaml`, `--rehearsal-evidence-dir` pointing where Sheet A5's record
   landed, `--redeploy-before-file /root/s31-redeploy-before.json`; the
   `--rotated-*` three, `--dx-record-file` and `--after-reboot` NOT given.
   ~15 min. Expected: the three host claims `passed`; `studio_tenant_read`
   **passed** (the repaired fixture's first execution); `deployment_
   convergence` passed; every inherited host claim unchanged. A failing
   proof: an instrument repaired in the window and re-run with `-k`; a
   product defect recorded and left.
8. *(op, then the workstation)* the host half to WSL; `--mode external`
   from WSL; the merge into `evidence/session-31.json`. Expected: **144
   claims** (135 + 9; more if Run 5 registered new entries — the Done says
   the number); `not_run` 4 (the rotation trio, `replacement_host_restore`);
   `failed` 1 (`documented_path`); exit 5 for those reasons and no other.
9. **The tag**: `bin/apg.sh release-reading --ref <the deployed SHA>`
   quoted; `git tag -a 1.9.0 <sha>`; `git push origin 1.9.0`; `git ls-tree`
   of both release pages.
10. The sentinel swept (Sheet A6's last lines); `host.yaml.pre-s31` kept on
    the host; the post kit exported; D rows for what the day found; this
    run **Done.** with the claim table, the two `upgrade plan` verdicts,
    the two ledgers, the admission's six numbers on production, the
    refused third's six, `doctor capacity`'s figures against `free -m` and
    `df`, `doctor usage`'s eight figures per project, and the two
    `time`s.

**Done.** 2026-09-20 (the trip) and 2026-09-21 (the second sweep and the
tag). **1.9.0 is deployed on both projects at `4344a1f`, swept, merged and
tagged**, in that order and on that commit (D1425, with D1641's one stated
exception).

*The deploy refused before it wrote anything.* Step 5 on alpha stopped at
`mirror_s3_secret_access_key: declared random_hex and the value is not
lowercase hexadecimal`. The CHECK was right and the CONTRACT was wrong -- a
Backblaze B2 key is base64url, and it had been declared `random_hex` since
Session 18. Nothing was damaged: both projects stayed 10/10 healthy, routes
200, the document unmoved at 1.8.0/`be987cf`, the generation unmoved. An audit
of all 21 secrets found exactly two mis-declared, and `mirror_s3_access_key_id`
was passing BY COINCIDENCE -- a declaration that is false and sometimes
satisfied is worse than one that is simply false. `opaque` is the third kind
(D1634); the four R2 secrets were deliberately left alone.

*The trip's readings.* `host.yaml` at schema 3 (3814/2214/37/8). Both projects
deployed through session 31, `doctor` **11 ok / 0 problem** each, every
container recreated as this release requires, ledgers 33 and 35 unmoved. A
third project was offered to the host and **REFUSED at exit 12**, and the same
project against the host's own declaration was **ADMITTED at exit 0** -- the
control without which the refusal proves nothing.

*Two sweeps, because the first found two defects in this run's own
instruments.* The first: 1026 passed, 2 failed, 3 errors. `admission_live`
asserted a label typed from the plan's prose where the renderer emits
`"declared memory"` (D1639); three Studio proofs errored because Run 5 moved
the auditor's role and left its scopes, which the running auth service refuses
at issuance (D1638). Both repaired at `05fdfe9`, CI green, and the second sweep
returned **1030 passed / 1 failed / 0 errors**.

*Step 8 found a third.* `--mode external` ran with no `ssh-agent` and both
`connection_tooling` proofs failed on their POSITIVE CONTROL -- which is why it
cost twenty minutes and not a release (D1640). Re-run with an ephemeral agent:
25 passed, 0 failed.

*The merged evidence: **145 claims, 139 passed, 5 not_run, 1 failed**.* Ten
claims more than Session 30, and the ten new ones all passed.
`telemetry_read` is the one worth naming: **the project's own Prometheus
answered on production for the first time in this product's life**, and every
series it returned named its project. `usage_read`, `admission_live` and
`agent_write_method` passed with it, none having executed anywhere before.
`studio_tenant_read` passed, which it had never done. `documented_path` stays
`failed` by decision until a person walks the path; `port_allocation` stays
`not_run` because this trip performed no reboot and the flag declaring one
would not have been true.

*What the trip reported and did not repair.* `ceilings` excludes the database
and under-reports by the largest cap on the host, because D587's missing
`apg.project.key` label hides `postgres` and `pgbouncer`. It decides nothing --
`decide` charges `unreclaimable_mb`, never the caps -- and it under-reports in
the REASSURING direction, which is why it is written down rather than folded
(D1636, ADR 0195).

*The count that matters.* **Seven of this session's defects were the
instrument rather than the product**, and the product's own refusals diagnosed
two of them in one line each. Each was a value that looked measured and was
not; each was caught by running the check against the real thing instead of the
expected thing.

### Run 8 — the close

Documentation only, no CI read: this plan's header rewritten (COMPLETE,
the dates, the rows each run added, NEXT FREE); `docs/scope-closure.md`
**§24** (what 31 closed, what it left, what 32 inherits — the worker's
claim against the declared capacity first); `docs/plans/stage-4-plan.md`'s
Status block (`CURRENT_SESSION 31`, `1.9.0`, the count of ADRs, next free
`D`); the envelope's `Unmeasured` row replaced by a `MACHINE` `Measurement`
naming the host with Sheet A5's two `time`s (`render-capacity-envelope.py
--write`); CLAUDE.md in the launch folder: §2's block (STAGE 4, RELEASE,
EVIDENCE, CURRENT_SESSION, HOST, DR KITS), §8's two sentences that this
session made false (*"Nothing sets `pids_limit` or `cpus`, and host RAM is
never read"*; the `container_exec` sentence per D1593), §9's rows removed
or rewritten; the memory file. Commit, push, done.

---

## 7. Evidence and claims

Unchanged rules (ADR 0163, 0202; D1237; D1543). **Nine claims land with the
constant** (D690): six declared offline — each a property of a checkout
(a schema, a parser, a decision driven against a fixture root, a compose
file walked, a config built, a materialize loop scanned) — and three host,
undeclared, first executed on the trip. **Session 31 is the session the
stage plan's item 2 names**: a capacity reading (`capacity_reading`,
`usage_read`) and an admission decision (`admission_decision`,
`admission_live`) are separate claims, and only the reading may report
`unknown`.

| Claim | Mode | Moves on |
|---|---|---|
| `capacity_declared`, `capacity_reading`, `admission_decision`, `process_limits`, `telemetry_bounded`, `secret_kind_checked` | offline | Run 6's gate |
| `admission_live`, `telemetry_read`, `usage_read` | host | Run 7's sweep — their proofs' **first execution anywhere** |
| `studio_tenant_read` | host | Run 7 — from `failed` to `passed` if the fixture repair is right; **a second `failed` is recorded and left** (the product was right the first time; the run reads the error one layer down again) |
| `deployment_convergence` | host | Run 7, `--redeploy-before-file` declared |
| the rotation trio, `replacement_host_restore` | — | `not_run`, unchanged; `documented_path` `failed` by decision |

**No claim is added for the orphan attachments** (Run 5's item 6): a node
id joining an existing requirement makes that requirement's claim stricter
and moves no count. New entries Run 5 writes get their own host claims and
the Done names them.

**Environment gates this session adds:** `APG_HOST_MANIFEST`,
`APG_CANDIDATE_MANIFEST` — both in the roster, both exported by the gate's
host mode, both read only through `requires_environment` (D687).

---

## 8. Security invariants this session touches

| Invariant | Where 31 puts it at risk | Control |
|---|---|---|
| **Admission refuses; a capacity reading reports** (stage plan §8) | `decide` and `capacity_report` in one module | Two functions with two vocabularies; a grep proof that `capacity_report` and `usage_report` never emit `WARN`/`PROBLEM`; a proof that `decide` refuses on `unknown` |
| A report may not substitute an answer for a failure to determine one (ADR 0195) | Every figure in both readings | `Figure(value=None, reason=…)`; `null` + `reason` in `--json`; a missing `MemAvailable` is `unknown`, never 0 |
| An agent record carries no URL, key, token or caller value | The store's series (a `project` label) | The label is the project key, a derived constant; `doctor usage` prints integers it parsed and nothing from the store's body; `test_doctor_redaction` runs over the new readings |
| The MCP runtime holds no credential | `APG_OTLP_ENDPOINT` | A URL of a fixed shape on the project's own network; refused at load if it names another host; `FORBIDDEN_VARIABLES` unchanged and its guards run |
| One service cannot read another's credential | `storage_objects` | Not read (D1601) |
| Projects share no project-scoped value | `const_labels` | The label's value is the key; the isolation proof for the metrics route (`test_session14_observability.py:180-202`) gains a positive control |
| A workstation holds no production secret | `check_value_kind`'s reason | Built from the kind and the rule, never the value; a sentinel proof |
| There is no public Postgres endpoint (ADR 0216) | Nothing here touches a port or a network | The store joins no network (D1582) |
| `--render-only` keeps working with no host and no root | Admission at step 0 | `--render-only` does not reach step 0's admission (Run 3's reading); the gate's step 2 renders four fixtures |
| A deploy over a broken archiver fails | Unchanged | Step 6c unchanged |
| The deploy, the sweep and the tag land on one commit | Run 7 | D1425's order on the sheets |
| A human cannot run SQL through a product surface | `doctor usage`'s SQL | Statements are constants in `bin/doctor.py` with no caller text (the `DENIALS_SQL` shape, `bin/fleet.py:50-58`) |
| Never grant `op` the docker group | `admit.sh`, `doctor capacity` | Both require root for a real run; `--help` is free |

---

## 9. Stop conditions

- Rig 31a: Compose refuses `cpus` as an interpolated string AND
  `deploy.resources.limits.cpus` is not honoured by the pinned Compose:
  stop; the row says which; `cpus` becomes an ADR 0222 alternative not
  taken and `pids_limit` lands alone.
- Rig 31b: any container's `pids.peak` is within 2× of a proposed default,
  or `pids.peak` is absent AND `pids.current` exceeds half a proposed
  default: raise that default to the rule's value and say so; **never** set
  a default below a measured peak.
- Rig 31c: `const_labels` does not reach the synthesised series (`up`,
  `target_info`): the doctor's per-series assertion excludes them by name
  and the row records it; if it reaches none, stop — the label moves to the
  store's scrape config after all and `build_prometheus_config` takes a
  project (D1590 rewritten).
- Rig 31d: `configure` raises into `record()` when the collector is down,
  or the memory cost exceeds 32 MiB: stop; the call is not made from
  `create_mcp_app` until ADR 0223 is rewritten.
- Rig 31e: the third manifest at `shared_buffers_mb: 896` is refused by
  `_validate_memory_budget` (the per-project guardrail): the live proof
  would measure the wrong decision; choose a budget the guardrail admits
  and admission refuses, and rewrite Sheet A5.
- Admission would refuse alpha's or beta's OWN redeploy on the trip (Sheet
  A3's step 0): **stop before the deploy**; do not edit `host.yaml` to make
  it admit; the arithmetic is wrong or the declaration is, and the row says
  which.
- Admission would degrade a running project instead of refusing (stage
  plan §9) — anything in `decide` that stops, scales or restarts a
  container: there is no such path; if one is proposed, stop.
- A capacity reading would refuse anything: stop.
- A port, a route, a published store or a non-loopback bind for any reason
  (ADR 0216).
- Run 6's `upgrade plan` prices `1.9.0` at **major**: stop; a row; the
  operator's decision.
- A passing test would be weakened — including `test_the_store_is_routed_
  nowhere`, `test_the_store_holds_no_credential`, any `FORBIDDEN_VARIABLES`
  guard, or `test_mcp_tracing`'s no-caller assertion for TRACING.
- `studio_tenant_read` fails a second time on the trip: read the error;
  the product is presumed right; the instrument is recorded and left
  (D1572's rule); no fixture edited in the window unless the error is in
  the fixture's own arithmetic.
- The sweep's `admission_live` reads `not_run`: `skipped_node_ids` first;
  a missing gate variable is the gate's defect, repaired and re-run with
  `-k`; never re-run the deploy.
- The orphan triage would register more than three NEW requirements: stop
  and ask; the count is the operator's decision (Session 30 §9's rule).
- CI red on a code commit: stop and read; a cancelled run is not a failed
  one (D1059).
- WSL has lost outbound TCP on trip day: CLAUDE.md §1; a Windows reboot
  early.

---

## 10. Open items this session carries and creates

**Carried in, untouched, each still true:** D1045; `replacement_host_
restore` (D1028); D1375; the 21 unclaimed requirements; D976, D688, D771,
D340, D466, D540, D942, D1203, D1205, D1211; the Infisical control-plane
identity's org admin; `process-max` 1 (D593); `documented_path` failed until
a person walks it (35); the three rotations 30 did not perform; the retired
JWKs on the host unread by any sweep; the mirror's upstream flake (D1546);
`apg-diag`'s standing account (D1528) and its allowlist (D380); ADR 0162's
missing row for an option (D1561).

**Created or left here:**

| Item | Note |
|---|---|
| **The edge plane carries no `pids_limit` or `cpus`** | D1586: Traefik and the socket proxy are shared and their recreation is its own act. Session 35's hardening run, with the deploy-downtime measurement it already owes (D1524). |
| **Three long-running services carry no `mem_limit`** | pgbouncer, postgrest, docs (`config.py:262-275` has no `memory_limit_mb` for `api.rest`). The reading lists them under `unbounded`. Bounding them is a measurement first (D770's rule: a limit chosen against `anon`, on the host). |
| **`render-jwks` reads three files and never `verification_kids`** | ADR 0224 closes the window at the deploy and defers this. The session that performs the other three rotations owns whether the deploy should carry the retiring key until `retire_after`. |
| **`materialize-secrets` cannot tell *deliberately absent* from *a name I do not read*** | D1578's second half; the first is closed by ADR 0225. |
| **`delete_note` does not exist** | D1594; a session that moves the `api` contract. |
| **`storage_objects` is not a usage figure** | D1601; a count route on the storage service, Session 34's if wanted. |
| **The noisy-neighbour effect is unmeasured** | `THR-NOISY-NEIGHBOUR`'s residual; Session 35 measures both ways. |
| **The envelope is pinned to three images and the collector is not one of them** | `capacity.MEASURED_AGAINST`; if a collector or store number is ever recorded there, the pin list must widen first. |
| **A worker is a seventh claimant** | Session 32 charges its `unreclaimable` (or its measured `anon`, on the host) and its connections against `capacity` and `max_connections` **before** it is built — the ordering rule 31-before-32. `decide` takes the candidate's claim as an integer; a worker's claim is one more line in the candidate's document. |
| **Why `auth` was recreated by Session 30 Run 7's deploy and not Run 8's stays UNDETERMINED** (D1581) | This trip cannot observe it: every container is recreated because its definition moved (D1586), so a generation-only redeploy is not on any sheet. The observation belongs to the first trip whose deploy moves a secret generation and nothing else — Session 32's, if its deploy is such a one. The candidate repair (`build_mount_override` reading `secrets-compose.override.yaml`'s `secrets.<name>.file` beside `runtime-compose.override.yaml`'s volumes) is written only after the observation, not before (ADR 0195). |
| **`KNOWN_UNREGISTERED`** | As Run 5 left it; the tuple shrinks only. |
| **`host.yaml.pre-s31` on the host** | The schema-2 copy; kept until 32's trip, then removed on that sheet. |

---

## Appendix — what to consult, how a run is executed here, the rigs, and the sheets

**Consult, in this order:** this plan's §1 and §5. The stage plan's §5
*Session 31*, §8, §9, §11. `docs/plans/session-30-implementation-plan.md`
§5 Runs 6–7 and Sheets A1–A4 (the trip's shape, the sentinel recipe, the
detached sweep), §10 (what 30 created for 31). ADR 0195 before any reader;
0157/0158 (the doctor/deploy split, the document as address book); 0159
(no `.stdout` in a `diagnosis.*` call); 0165/0169 (`anon`, CONFIGURATION vs
MACHINE); 0190/0193 (a rehearsal moves a threshold); 0213 (a reading with
no threshold); 0218 (`container_exec`); 0093 (a `bin/` command imports only
`agentic_postgres` and `yaml`); 0002 (a container name is derived).

**How a run is executed here** (CLAUDE.md §1 and §5, the parts that bite):
the Bash tool is Git Bash; every WSL command is `wsl bash -lc "cd
~/projects/agentic-postgres && . .venv/bin/activate && …"`; anything with a
loop, a nested quote or a `$` goes in a script file written with the Write
tool to `\\wsl$\Ubuntu\tmp\` and run with its output redirected to a file
that is `rm`'d first; **never pipe a gate into `tail`**; a long gate runs
detached with its exit code written from inside; `chmod 755 bin/*.sh
bin/*.py deploy.sh` before every `git add`; commit messages from a file with
`-F`; `PYTHONDONTWRITEBYTECODE=1` and `__pycache__` cleared before a battery;
restore by copy and `cmp`, never `git checkout --`; every anchor pre-flighted
to match exactly once and a miss fatal; a mutation is evidence only beside a
control it cannot reach, in the same invocation; assert HOW each mutation
failed; `--setup-plan` with the variables SET before a trip. **A `sudo` line
on any sheet has nothing after it**, and every sheet is grepped for `|`,
`>`, `$(` and `&` on every `sudo` product line before it is handed over
(D1505; `deploy.sh` refuses the mixed shape by design, ADR 0218).

**The rigs, summarised** (Run 1; each a script, each with a control, each
naming its image by digest):

| Rig | Subject | Control | Owes |
|---|---|---|---|
| 31a | `pids_limit: 8` and `cpus: "1.0"` through Compose on `${POSTGRES_IMAGE}` | the same services with no key | fork-failure text; string `cpus` accepted or the fallback; `pids.max`/`cpu.max` read-back |
| 31b | `pids.current`/`pids.max`/`pids.peak` for 22 scopes, `/proc/meminfo`, `free -m`, `df -Pk`, `nproc` on the host as `op` | none needed (a reading); `apg-diag containers` maps ids | every default in `SERVICE_RESOURCE_DEFAULTS`; the host's numbers for Sheet A2 |
| 31c | `const_labels: {project: rig31c}` on otelcol-contrib 0.159.0's `prometheus` exporter | the same config without it | reaches every series incl. `up`/`target_info`; the option's spelling |
| 31d | `mcp_metrics.configure` from the auth-api image against 31c's collector | `endpoint=None`; the collector stopped | endpoint path; RSS delta; nothing raises |
| 31e | `decide` over the fixture documents at 304 / 1072 | `_validate_memory_budget` accepts 1072 | Sheet A5's third manifest budget |

### Sheet A1 — the reads (all `sudo`; write each reading down)

`bin/upgrade.sh check --project alpha-dev` and `beta-dev` → installed
versions, `verdict OK`. `bin/doctor.sh --project alpha-dev` and `beta-dev`
→ 11 ok; **write down the `disk headroom` line's `cluster_kb` for each**.
`bin/fleet.sh` → 2 projects. `bin/backup.sh --outputs
/etc/agentic-postgres/projects/alpha-dev/outputs.json info` → a full
exists. `free -m` → the `total` and `available` columns. **`sudo docker info
--format '{{.DockerRootDir}}'` → the Docker data root, and `df -Pk` at THAT
path** → the 1K-blocks and Available columns. `nproc` → 2.

**Ask the daemon; do not assume `/var/lib/docker`** (D1632). It is the
default and it is not the contract: a host that had moved it would be
measured at the wrong filesystem and `disk_gb` would describe a different
disk, which is exactly the class D1611 removed from the product and D1623
made the reading report. `op` cannot ask — it has no Docker socket by
decision (D1375) — so this line is `sudo` and belongs here rather than on
Sheet A2, where the number is used.
`bin/dr-kit.sh export … --output /home/op/kit-<date>-pre` (the exact line
from `--help`, printed on the sheet by the agent).

### Sheet A2 — the declaration (`op`, no `sudo`)

The agent, over SSH as `op`: `cp host.yaml /home/op/host.yaml.pre-s31`;
`schema_version: 3`; the `capacity` block with `memory_mb` = Sheet A1's
`total`, `reserve_memory_mb` = `memory_mb − 1600`, `disk_gb` = Sheet A1's
1K-blocks ÷ 1048576 rounded down, `reserve_disk_gb` = 2 × the larger
`cluster_kb` ÷ 1048576 rounded **up**, each with its comment from
`host.example.yaml`; then the four renders `--render-only` (`project.
alpha.yaml`, `project.beta.yaml`, `project.example.yaml`, `project.second.
example.yaml`) — each exits 0, which is the schema's acceptance. **If a
render refuses `host.yaml`, STOP: the declaration is edited until it
validates, and nothing with `sudo` is issued.**

### Sheet A3 — the sentinel, then alpha (`sudo`)

1. `bin/upgrade.sh plan --project alpha-dev --candidate
   /home/op/agentic-postgres/.generated/alpha-dev/outputs.json --json` →
   `bump minor`, `OK`; the same for `beta-dev`.
2. The sentinel, Session 30 Sheet A2 steps 1–5 with `s31-redeploy-sentinel-
   <YYYY-MM-DD>` and `/root/s31-redeploy-before.json`; step 5's read-back
   must print both fields.
3. **The deploy**, at the terminal, nothing after this line:

       script -q -e -c "sudo ./deploy.sh --host host.yaml --project project.alpha.yaml --capabilities capabilities.yaml --through-session 31" /home/op/s31-deploy-alpha.txt

   → exit 0. **Step 0 prints the admission decision**: `admitted`, six
   lines — write the six numbers on the sheet. If it prints `refused` and
   exits 12: **STOP** (§9); nothing has changed on the host.

Then the reads: `sudo bin/migrate.sh --project project.alpha.yaml --runtime
status` at the terminal, nothing after it → 33 `[X]`, `Pending: 0`
(**unchanged**); `sudo docker ps --format '{{.Names}} {{.Status}}' --filter
label=apg.project.key=alpha-dev` → **every container younger than the
deploy** (the definitions moved; the database restarted); `sudo docker
inspect --format '{{.Name}} {{.HostConfig.PidsLimit}} {{.HostConfig.
NanoCpus}}' $(sudo docker ps -q --filter label=apg.project.key=alpha-dev)`
→ the nine limits and `1000000000`/`2000000000`; `sudo bin/doctor.sh
--project alpha-dev` → 11 ok.

### Sheet A4 — beta (`sudo`)

The same with `project.beta.yaml`; ledger 33 + 2, `Pending: 0` twice.

### Sheet A5 — the session's proofs (`sudo`; each line's output written down)

1. `sudo bin/admit.sh --host host.yaml --project /home/op/s31-third.yaml`
   → **exit 12**, `refused`, the six lines with `requested 1072` and `safe
   available 992` (if Sheet A1's `total` was not 3814, the numbers move
   with it and the agent recomputes them on the sheet beforehand).
2. `sudo bin/admit.sh --host host.yaml --project /home/op/s31-third-
   default.yaml` → **exit 0**, `admitted`.
3. `sudo bin/rehearse.sh admission-refused --outputs /etc/agentic-postgres/
   projects/alpha-dev/outputs.json --host host.yaml --manifest
   project.alpha.yaml` → `verdict passed`, the record's path printed; then
   `sudo bin/rehearse.sh reverse` → exit 0.
4. `time sudo bin/doctor.sh capacity --host host.yaml` and `time sudo
   bin/doctor.sh capacity --host host.yaml --project alpha-dev` → every
   group `ok`; `mem_total_mb` equal to Sheet A1's `total`; `committed`
   naming both keys at 304; `ceilings` naming 2240 per key and the three
   `unbounded` services.
5. `time sudo bin/doctor.sh usage --project alpha-dev` and `beta-dev` →
   eight figures each, `ok`. `requests_total` may read **0** here: the
   doctor lines above are not requests through the edge, the sweep's are,
   and the sweep has not run yet. A 0 is honest; the proof asserts ≥ 0, and
   the same line re-run after Sheet A6 is where a positive number is
   expected. `tool_calls_total` ≥ 0 for the same reason.

### Sheet A6 — the sweep, then the cleanup (`sudo`)

`sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/alpha-dev/
outputs.json /home/op/alpha-dev-outputs.json` and beta (D1506's pair);

**`alpha-dev-outputs.json`, not `alpha-dev-dev-outputs.json`** (D1631). The
host's op-owned copies are `/home/op/alpha-dev-outputs.json` and
`/home/op/beta-dev-outputs.json` — read on 2026-09-20, both written
2026-09-19 09:38. The doubled `-dev-` would `install` a NEW file beside the
real one, and the agent's confirmation that the copy names the new
`source_commit` would then read a file nothing else uses while the stale
pair sat untouched. **D1575's shape**: a sheet pointing a command at the
wrong copy. (The bare `/home/op/alpha-outputs.json` pair is older still —
2026-08-23 — and is not this.)
the agent confirms both name the new `source_commit` **before** this line:
`sudo bash /home/op/s31-r7-launch.sh` — which detaches the sweep itself and
returns at once, so an SSH drop cannot kill it; ~15 min; `cat
/home/op/s31-r7-host.code` → 0 or 5, and `/home/op/s31-r7-host-summary.txt`
is the reading.

**The names are `s31-r7-*`, not `g31-host.*`** (D1630). The planned names
follow `g25-host.sh`, which is two conventions old; the scripts staged for
this trip are derived from Session 30's `s30-r7-gate.sh` and
`s30-r7-launch.sh` — the last host sweep that actually ran — and carry that
shape. A sheet naming a file that is not there is a failed line in the
middle of a window. Then the sentinel removed, exactly Session 30 Sheet A4's two lines with
the `s31-` title (no `-i`; expect `DELETE 1`). Then `bin/dr-kit.sh export …
--output /home/op/kit-<date>-post`.
