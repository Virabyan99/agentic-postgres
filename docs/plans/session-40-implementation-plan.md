# Session 40 — Branches and restore to a branch

**Status: EXECUTING since 2026-10-14. Run 1 in progress** (rigs 40a–40d done,
ADRs 0271–0273 written, the threat list made specific; Sheet E0 with the
operator). Rows **D2422–D2453** at planning, **D2454–D2460** added by Run 1;
ADRs **0271–0273** written. **NEXT FREE: D2461, ADR 0274.**

The fifth session of Stage 5 (`docs/plans/stage-5-plan.md` §3, §5 *Session 40*).
Eleven runs and **two sittings on two days**: the release on the four projects
(the customer's `slot3-prod` moved by a product verb for the first time), a new
slot `slot4-prod` prepared, and the whole trip verified writing nothing (day 1);
then, from the workstation with no SSH, **the re-earning** — `slot4-prod`
created, credentialed, connected, rotated, slept, woken, resized, exported and
deleted — then **the branches** — `slot3-prod` read for its restore window, a
deliberate change made around a recorded instant, a branch that expires by
itself, a branch restored to the instant before the change, migrated over its
own direct name, reset, kept through a reboot and the sweep, then deleted — then
external, merge, tag (day 2).

**Brief:** `docs/plans/stage-5-plan.md` §5 *Session 40* (`:706-745`: Builds /
Already true / Must not / Measures / Closes) and its rows **D1961** (a branch is
a child deployment restored from the parent's repository, re-keyed), **D1962**
(promotion cut), **D1963** (the backups surface; in-place restore not a
customer's), **D1978** (threat rows first), **D1979** (the Ledger), **D1980**
(no snapshot storage), **D1983** (branch time measured on the host); §8's row *"A
branch starts re-keyed and cannot write its parent's repository"* (`:916`); §9's
stop *"a branch would open its endpoint before the re-key, or write to its
parent's repository"* (`:951-952`). `docs/scope-closure.md` **§32** (`:1472-1530`,
*"What Session 40 inherits, in order"* `:1518-1529`); Session 39's plan §10
*"Created, and named so Session 40 does not inherit them silently"*
(`docs/plans/session-39-implementation-plan.md:1627-1640`) and its rows
**D2405–D2421** (`:493-509`). ADRs **0151** (the drill, disposable by
construction), **0186** (*"Expiry is a fact an operator reads, never a trigger"*,
`:74-83`; *"this ADR is the one it supersedes"* `:99-100`), **0187**, **0189**,
**0192** (D1010: `restore_command` carries `--config`), **0256**–**0261**,
**0268**, **0269** (`:134-136`: *"Session 40's re-key must rotate both customer
roles before a branch's names open"*). `docs/threat-model.md` hosted items **#1**
(`:191-195`), **#4** (`:209-214`), **#6** (`:219-222`). `docs/reality-ledger.yaml`
rows `branches` (`:486-503`), `restore_to_branch` (`:505-518`),
`in_place_restore` (`:520-537`), `branch_promotion` (`:539-556`),
`backups_and_pitr` (`:850-867`), the six managed-project rows (`:185-381`),
`pooled_endpoint` (`:403-431`), `direct_endpoint` (`:433-462`), `postgresql`
(`:811-830`). **And the operator's four answers of 2026-10-14** (§1 D2428,
D2430, D2432, D2433).

**Shape:** eleven runs. **Run 1** is documentation — four rigs, one host reading
sheet (E0, which also times a restore drill of `slot3-prod`), the threat list
made specific, three ADRs — and reads **no** CI verdict. **Runs 2–6** change
code: each pushes and reads that commit's own CI verdict by full SHA (`gh api
"repos/Virabyan99/agentic-postgres/actions/runs?head_sha=<40 chars>" --jq
'.workflow_runs[] | [.name, .status, .conclusion] | @tsv'` from Git Bash, judged
on HTTP status, three buckets — success / failure / not registered; an empty list
is not a verdict, D1057). **Run 7** writes the trip's instruments and rehearses
them offline, committing nothing but its `**Done.**`. **Run 8** is the bump.
**Runs 9–10** are the sittings. **Run 11** is the close (Ledger rows and envelope
rows are code: it gates once and reads CI). **Push only after the previous
commit's CI lands** — `ci.yml` cancels in-progress runs on `main`.

**Product version at close:** `CURRENT_SESSION` **40**; `template_version`
**`1.18.0`** — predicted *minor* (**no** project-manifest or outputs schema
change, no new secret, no released migration; four operation types accepted,
eight `/v1` routes added, the control set's own sixth migration) and **read from
`upgrade plan` on the host with `--also api_operation_added`, never chosen**
(D1624's rig in Run 8). The released migration count stays **39**. **No new
published port, no new service in any project's compose file; one new compose
file for a branch (three services), one new root command
(`bin/branch-runtime.sh`), one new customer command (`bin/branch.sh`), one new
operator verb (`bin/slot.sh redeploy`), four operation types accepted.** A
`major` is §9's stop.

**Written for whoever picks this up cold, and it will be a different model than
the one that planned it.** Every path below was read from the tree on 2026-10-14
at `23e3d92` — four explore passes over `src/agentic_postgres/`, `bin/`,
`services/auth-api/`, `projects/control/`, `schemas/`, `compose.yaml`,
`migrations/templates/`, `tests/`, `docs/` and every Stage 5 plan, plus direct
reads of `projects/control/migrations/templates/0003-control-registry.sql:29-47`,
`0005-control-endpoints.sql:111-130`, `src/agentic_postgres/reality_ledger.py:165-194`,
`tests/external/test_session38_public_lifecycle.py:76-103`,
`tests/external/test_session39_public_lifecycle.py:66-72` and
`bin/edge-network.sh:170-215` — **and three readings taken at planning** (§0).
Every path is cited `path:line`. **Read CLAUDE.md §1 in the launch folder before
the first command, then this plan's §1, then the appendix.** If a step here and
the tree disagree, **the tree wins and the disagreement is a divergence row**
(next free `D` after §1's table), never a silent reconciliation. **When this plan
names a line number, open the file at that line and read the surrounding twenty
lines before editing** — the numbers were right on 2026-10-14 and `ruff format`
moves them.

**The nine sentences the executor most needs, in case nothing else is read:**

1. **A branch is not a deploy** (D2422). A restored volume carries the parent's
   `app_private.project_identity`, and `bin/postgres-bootstrap.py` exits **11**
   for a volume whose identity names another key (`:953-997`); a deploy also
   needs the key's own Infisical project (secrets are materialized per key,
   `naming.py:1293`). **A branch is its own compose project of three services —
   `postgres`, `customer-pool`, `customer-direct` — run by a new root command,
   `bin/branch-runtime.sh`, holding no secret of its own.** No auth, REST,
   storage, MCP, docs, metrics or backup in a branch; the Ledger says so.
2. **The restore is the drill's, made persistent** (D2424): pgBackRest restores
   the parent's repository into the branch's own volume through a one-shot
   container that inherits the parent's repository mounts **read-only** on the
   parent's backup network (ADR 0151 §2); a **recovery instance** replays WAL with
   `archive_mode=off` until it promotes; then it is removed and the branch's
   **persistent** `postgres` starts from the same volume with **no repository
   mount, no backup network, `archive_mode=off`, `archive_command=/bin/false`**.
   A branch cannot write its parent's repository because it has neither the path
   nor the credential (rig 40a measures the repository's object count unchanged).
3. **The re-key runs before any door exists** (D2427): every platform login role
   `NOLOGIN PASSWORD NULL`, the superuser's password `NULL` (local socket only),
   both customer roles given **the branch's own verifiers** (generated on the
   workstation by `bin/branch.sh`, sent as verifiers — ADR 0269's shape), every
   refresh family revoked and every agent credential expired. **Only then** do the
   two customer poolers start and the edge attach. Rig 40a's control: the
   parent's customer password connects to the restored instance BEFORE the
   re-key and is refused AFTER it.
4. **Names: `apg-<key>_<branch>`** (D2423). A project key never holds `_`
   (`config.py:842-843`), so a branch stem can never equal a project stem or a
   restore drill's (`apg-<key>-restore-<id>`). A branch name is
   `^[a-z][a-z0-9]{1,11}$`; `main` is refused (it is the project).
5. **Branch hostnames: `<branch>.pool.<domain>` and `<branch>.direct.<domain>`**,
   reached through **two grey wildcard records per slot** the operator creates
   once (`*.pool.slot3.…`, `*.direct.slot3.…` — **the operator, 2026-10-14**,
   D2428). Measured at planning: every name below `slot3.agenticpostgresql.com`
   is **NXDOMAIN** today — the proxied `*.agenticpostgresql.com` no longer
   reaches below an existing node. One HTTP-01 certificate per branch.
6. **One live branch per project** (**the operator, 2026-10-14**, D2430): a second
   `branch.create` is refused `409 branch_limit_reached` before an operation row
   exists. The parent must be awake; a project with a live branch cannot be
   deleted.
7. **Branch expiry is a trigger** (**the operator, 2026-10-14**, D2433): an
   optional `expires_at` (at most 7 days ahead); the reconciler's idle loop asks
   the control database to request the `branch.delete` itself, on behalf of the
   member who set the expiry. **ADR 0272 supersedes ADR 0186 for branches only.**
   No separate test-restore operation (D2432): a branch at a point IS the test.
8. **The re-earning is at ONE commit** (D2442, D2448): `slot4-prod` prepared on
   day 1; on day 2 its lifecycle, the branches, the sweep and the external half at
   the deployed commit, and the tag there. **Day 1 runs the whole sweep and the
   whole external half with `-k`, writing nothing, BEFORE `slot4-prod` is
   consumed** — Session 39 lost its lifecycle to a commit move a dry run would
   have found (D2413, D2415). A commit move after `slot4-prod`'s deletion is §9's
   stop: there is no fifth slot.
9. **Eleven Ledger rows go to `trial` in the bump**: the six managed-project rows
   (evidence `lifecycle_reearned_live`), `pooled_endpoint` and `direct_endpoint`
   (`endpoints_reearned_live`), `branches`, `restore_to_branch` and
   `backups_and_pitr` (`branch_live`) — every one a claim Session 40 introduces
   (ADR 0261, `reality_ledger.py:165-194`). `ACCEPTED_TYPES` becomes the seven plus
   `branch.create`, `branch.reset`, `branch.delete`, `restore.create`.

---

## 0. Where the session starts

```
HEAD            23e3d92 on main, local = origin ("Session 39 Run 12 Done: the
                close -- SL4, K4, scope closure §32, Status COMPLETE"), tree
                clean. Code: ea90b2a (CI 38300269973 success). Deployed: b0249ce
                (1.17.0, tag object fd5e734) on all four projects. main is past
                the tag with the close's code (the Ledger, ACCEPTED_TYPES empty,
                the D2405/D2409/D2416/D2420 repairs) -- NOT deployed.
VERSION         1.17.0. CURRENT_SESSION 39 (src/agentic_postgres/__init__.py:1090;
                Session 39's paragraph :1029-1089; template_version() :1098-1104
                reads VERSION). README.md:7 "Session 39 implemented". Outputs
                schema 22 (deployed_output.py:40). Project manifest 1-11
                (config.py:64; PUBLIC_ENDPOINTS_FROM = 11 :100). host.yaml schema
                2|3|4. 39 released migrations; the control set 5
                (projects/control/migrations/released.lock.json schema 3; 0005
                control_endpoints 20261011120005); three committed proposals
                (projects/control/proposals/14699bf6…, d82e2831…, f0dabad8…).
REGISTRY        346 requirements (tests/acceptance-registry.yaml, 7,162 content
                lines; Session 39's block :6854-7162 under `# Session 39 (ADR
                0268-0270)`). ID regex tests/contract/test_acceptance_registry.py:121
                (ends `...|OPN|LIFE|EP)-...`); family comments :43-120 (EP
                :118-120). 253 claims (evidence_claims.py CLAIMS :458-1331,
                Session 39's :808-828); 101 declared offline (OFFLINE_CLAIMS
                :106-411, Session 39's :384-409). CLAIM_INTRODUCED_IN
                tests/contract/test_evidence_claims.py:953-1294 (Session 39's
                :1240-1256). 270 ADRs (docs/decisions/README.md last row :336).
                NEXT FREE: D2422, ADR 0271.
EVIDENCE        evidence/session-39.json (WSL, gitignored): 253 claims, 248
                passed, 5 failed -- documented_path (D1935);
                lifecycle_operations_live, lifecycle_project_door_live,
                lifecycle_retrial_live (D2415); public_endpoints_live (D2416).
                restore_isolation PASSED (evidence/session-39-host.json:1561-1573).
LEDGER          The six managed-project rows, pooled_endpoint, direct_endpoint,
                postgresql: planned, target 40. branches, restore_to_branch,
                backups_and_pitr: planned, target 40. in_place_restore,
                branch_promotion: not_offered. ACCEPTED_TYPES = frozenset()
                (services/auth-api/app/operations.py:83).
HOST            15.204.231.45, OVH VPS US-East, apg-ovh-01: 4 vCPU, 7,746 MiB,
                no swap. Read at planning (2026-10-14 ~07:10Z, apg-diag + op):
                ~op/agentic-postgres = b0249ce, clean; 42 containers healthy
                (alpha-dev, beta-dev, control-prod x10; slot3-prod x12 with its
                two customer poolers), up 42 h since B2's reboot; listeners 22,
                80, 443, 5432 (+ the resolver's loopback 53); `free -m`
                available 5,048 MiB; `/` 72 G, 11 G used; reconciler, edge and
                the four project units active, NRestarts 0. slot3-prod's backup
                timers: full Sun 02:00 (last: its creation's, Mon 2026-10-12
                10:39Z), incr daily ~03:38Z, mirror daily ~04:35Z. No restore
                drill container or volume. slot1/slot2 CONSUMED and revoked: NO
                SLOT IS FREE.
DNS (planning)  slot3. and pool.slot3.agenticpostgresql.com -> 15.204.231.45, no
                AAAA. dev.slot3., pool.dev.slot3., pool-dev.slot3. -> NXDOMAIN
                (Resolve-DnsName at 1.1.1.1). nosuchname.agenticpostgresql.com ->
                Cloudflare (188.114.96.12/97.12 + AAAA). The proxied wildcard
                answers only where no closer node exists (RFC 4592's closest
                encloser): Session 39 §0's "nested names included" was read
                before any slot name existed.
OPERATOR        2026-10-14: two grey wildcards per slot for branch names; one
                live branch per project; no separate test-restore operation;
                branch expiry built (D2428, D2430, D2432, D2433).
```

**What exists, measured at `23e3d92`, and the session builds on:**

- **The restore drill** (ADR 0151). `bin/restore-test.sh` (exit codes `:27-33`: 0
  verified, 2 input, 3 prerequisite/not root, 5 refused, 6 did not verify, 7
  unsafe plan; usage `--target-time ISO8601 --project-dir DIR` `:45`; a 0600 state
  file and `trap teardown_from_state` `:168-170`; `teardown_from_state` refuses
  `drill_volume == live_volume` `:124-129`) → `bin/restore-test.py` (`drill()`
  `:821-932`: the live container by Compose labels `:181-207`; `drill_id` UTC
  minute + 4 hex `:268-276`; `refuse_a_leftover` `:307-327`; `read_repository`
  through the live container `:223-260`; `run_restore` = `docker run -u 999:999
  --rm … --network <backup> --entrypoint pgbackrest <image> <argv>` `:359-384`;
  `start_instance` `:387-394`; `wait_for_promotion` `:421-455`;
  `observe_restored_instance` `:458-566`; `smoke_checks` `:631-771`; teardown in
  `finally` `:902-905`; evidence `evidence/restore-drill-<key>-<id>.json`
  `:953-960`; timeouts `:95-97`: promotion 900 s, restore 7,200 s) →
  `src/agentic_postgres/restore_drill.py`: `inherited_mounts` (`:298-329`, the
  parent's `/etc/pgbackrest/pgbackrest.conf` and the three `conf.d` credential
  files, forced read-only), `inherited_environment` (`:332-351`), `build_plan`
  (`:354`), `assert_disposable` (`:414-478`), **`restore_arguments`** (`:481-500`:
  `--stanza=<s> --log-level-console=info restore --type=time --target=<T>
  --target-action=promote`; `--delta` in `FORBIDDEN_RESTORE_FLAGS` `:125`),
  **`instance_command`** (`:503-516`: `postgres -c archive_mode=off`), the image =
  the live container's image id (`:394`), the network = the parent's backup
  network (`:409`), `failure_detail` (`:585-614`), `drill_verdict` (`:729-783`).
  **ADR 0151 §5 says `assert_disposable` checks `archive_mode=off`; the code does
  not** (`:414-478`) — the check lives in `tests/contract/test_restore_test_command.py:327`
  (D2447). Callers: `bin/restore-test.py`, `bin/restore.py`,
  `src/agentic_postgres/node_restore.py:45-50,269`, three contract modules.
  `naming.restore_drill_names` (`naming.py:899-948`, `_DRILL_ID` `:882`, the
  stem `apg-<key>-restore-<id>`).
- **Restore onto a replacement host** — `bin/restore.sh`/`restore.py`/
  `node_restore.py`: the project's OWN volume, refused when mounted or holding
  `PG_VERSION`; the config mounted at `/etc/pgbackrest/restore.conf`
  (`node_restore.py:81,212-234`); measured on OVH 2026-10-09: **469–564 s** per
  project from US-East against EU buckets (`docs/plans/session-38-migration-plan.md:680,698,710`).
  **No envelope row measures a restore** (`capacity.py` prose only, `:11,
  :247-248`).
- **pgBackRest.** `rendering.build_pgbackrest_conf` (`rendering.py:1199-1288`):
  `repo1-type=s3`, `repo1-path=/<prefix>`, `repo1-cipher-type=aes-256-cbc`,
  `repo1-retention-full=<retain_full>` (default 2, `config.py:408`), no credential
  in the file; stanza = the key, prefix `pgbackrest/<key>/` (`naming.py:1296-1301`);
  `archive_timeout` 60 s (`config.py:399`); archiving by `-c` flags
  (`compose.yaml:256-267`, `_archive_settings` `rendering.py:1817-1842`); timers
  full `Sun 02:00`, incr `03:30`, mirror `04:30`. **No `process-max`, no
  `archive-async`.** `bin/backup.sh info --json` (`backup.py:451-497`) →
  `backup_report.backup_state` (`:319-357`: `status`, `stanza_created`,
  `last_full_backup_label`, `last_full_backup_at`, `latest_recoverable_time` — the
  newest backup's stop time, a floor `:118-130` — `wal_archived_count`,
  `wal_failed_count`, `mirror`); `summarise` (`:73`).
- **The doctor's three backup readings** (`bin/doctor.py` probes `:416-504`;
  `src/agentic_postgres/diagnosis.py` `repository()` `:266-302`, `archiver()`
  `:305-323`, `mirror()` `:334-374`, `MIRROR_STALE_AFTER_DAYS = 2` `:331`).
- **The identity sentinel.** `bootstrap_statements` writes
  `app_private.project_identity` (`project_key`, `database_name`,
  `compose_project_name`, `instance_uuid`) once (`:380-414`, `IDENTITY_FIELDS`
  `:34`); `bin/postgres-bootstrap.py` `read_identity` / `assert_identity_matches`
  (`:953-997`) → **`EXIT_IDENTITY_MISMATCH = 11`** (`:69`).
- **Which login role holds which secret** (`bin/postgres-bootstrap.py`):
  `migration_user` (`:1065-1070`), `app_runtime` (`:1104-1116`),
  `postgrest_authenticator` (`:1124-1135`), `auth_service` (`:1151-1166`),
  `storage_service` (`:828+`), `backup_user` (`:790+`); `customer_app` /
  `customer_admin` **never** a password from the bootstrap (`:433-469`,
  `:1208-1212`, D2354); the superuser's from `postgres_init_superuser_password`
  at initdb only. `ROLE_SUFFIXES` (`naming.py:167-197`, sixteen). The
  credential tables: `app_private.user_credentials` (`0011:153`),
  `agent_credentials` (`0011:198`, `expires_at` `0025:52`), `refresh_families`
  (`0023:72`, `revoked_at`/`revoked_reason`), `refresh_tokens` (`0023:124`),
  `password_resets` (`0026:83`). **No function revokes every family or every
  agent at once** (`auth_revoke_user_sessions` is per user, `0026:46-63`).
- **The customer doors** (ADR 0268/0269). `compose.yaml` `customer-pool` (`:739`)
  and `customer-direct` (`:822`), profile `public-endpoints`, image
  `${PGBOUNCER_IMAGE}` (`:743`, `:826`), networks `internal` + `edge`, userlist
  bind `/run/apg/customer`. Labels in the runtime override:
  `_customer_tcp_labels` (`runtime_override.py:1033-1059`: entrypoint `postgres`,
  `HostSNI`, `tls.options=postgres@file`, `tls.certresolver`, `tls.domains[0]`
  main = pool host, sans = direct host, port 6432), `_customer_pooler_services`
  (`:1062-1076`). `naming.endpoint_hosts(domain)` (`:529-544`, a host over 253
  characters refused), `customer_pooler_containers` (`:560-572`).
  `bin/customer-credentials.py` (`VERIFIER_QUERY` from `pg_authid`,
  `customer_credentials.py:36-39`; files root:70 0640; SIGHUP both poolers
  `.py:138-180`). `CUSTOMER_CONNECTIONS` small 2/2 (`compute_profiles.py:91-95`).
- **The edge's attach is keyed by project.** `bin/edge-network.sh attach`
  (`:187-212`) derives the network with `project_edge_network "${PROJECT_KEY}"`
  and connects Traefik with `--alias apg-edge-proxy` — no other network can be
  named.
- **The control plane.** `services/auth-api/app/operations.py`: `OPERATION_TYPES`
  (`:50-62`; **`branch.create|reset|delete` → `branches`, `restore.create` →
  `restore_to_branch`** already named), `EXECUTED_TYPES` (`:66-76`, seven),
  `ACCEPTED_TYPES` (`:83`, empty), `RESULT_MEMBERS` (`:96-108`, no branch entry).
  `schemas/operation-arguments.schema.json` (`oneOf`, no `branch.*` branch;
  `$defs.profile` `:64-67`; every pattern ends `(?![\s\S])`, D2199).
  `app.control_operations` (`0003:29-47`: the type CHECK already lists the eleven,
  `:34-38`; **`requested_by uuid NOT NULL`** `:41`); 0004 `:40-59` (`error_code`
  CHECK five values, `secret_only_on_export`), unique partial indexes `:63-68`
  (one non-terminal operation per `project_key`); `control_request_operation`'s
  allow-list (`0005:121-125`) — **seven types, no `branch.*`**;
  `control_record_slots` (`0004:513`) the model for a reconciler-recorded table;
  key scopes CHECK (`0004:625-630`). `services/auth-api/app/errors.py:234`
  `OPERATION_ERROR_CODES`. `control_routes.py` (prefix `/v1`; project writes
  `:769-881`, `_offered()` `:706-711` → `require_accepted` → `409 not_available`
  naming the row; `/connections` `:912`). `control_roles.py` (`MATRIX` `:48-93`,
  `PROJECT_WRITES` `:100-110`, `OPERATION_OF_ROUTE` `:113-121`, `KEY_VOCABULARY`
  `:126-132`, `KEY_SCOPES` `:156-171`) — **no `branches:*`, `backups:read` or
  `restores:write`.**
- **The reconciler.** `bin/reconciler.py`: `HANDLERS` (`:912-920`, seven),
  `slot_project` refuses a non-slot key (`:640-652`), `Operation.child()`
  (`:369-409`: stdin `/dev/null`, a 0600 log per step, `CHILD_SECONDS`
  `:130-142`), `OPERATION_SECONDS = 30 * 60` (`:129`), `handle()` (`:1072-1116`),
  `record_slots` (`:1000`, every `RECORD_SECONDS = 120` `:117`, `:1188`),
  `start()` (`:1151`; `load_host()` once, D2411), `recover()` (`:1019-1027`).
  `src/agentic_postgres/reconciler_dispatch.py`: `STEPS` (`:79-106`; its comment
  `:77-78` still says *"six"*, D2447), `ARGV_MEMBERS` (`:113`), `COMMANDS`
  (`:119-133`), the SQL constants (`:166-212`), `invalid()` (`:244`), the argv
  builders (`:286-455`).
- **The customer CLI.** `bin/cloud.py` families `login`, `logout`, `context`,
  `org`, `project` (`list|use|show|create|claim|status|sleep|wake|delete|export`),
  `compute`, `endpoint`, `operation` (`:1008-1172`). **`bin/backup.sh` and
  `bin/restore.sh` are root operator verbs** — `apg backup` and `apg restore` are
  taken (D2437).
- **Capacity.** `capacity_probe.read` (`:244-357`) walks
  `/etc/agentic-postgres/projects`; a prepared declared slot commits nothing
  (`:100-121`, `:327`); `capacity_reading` sums each document's
  `database.budget.unreclaimable_mb` (`:279-311`) = `shared_buffers_mb +
  maintenance_work_mem_mb + 2 × max_connections` (`config.py:806-819`): **small
  192**, standard 304, large 840 MiB. **A branch is in none of it.**
- **Slots.** `src/agentic_postgres/slot.py` (`SLOT_KEY` `:69`, `STATES` `:84-92`,
  `slot_manifest` `:112-185`, `state()` `:203-249`, `dns_reading` `:301-331`,
  `slot_dns` three names `:334-353`); `bin/slot.py` (`prepare` `:124-184`,
  `status` `:192-207`, `revoke` `:233-329` — removes the directory it made since
  `ea90b2a`, D2405).
- **The project's restart policy.** `postgres` is `restart: "on-failure:5"`
  (`compose.yaml:206`): Docker restarts it after a crash, **not after a reboot**;
  a project comes back at boot by its unit (ADR 0265). A branch has no unit
  (D2439).
- **The gate to derive from.** `bin/session-39-check.sh` (2,011 lines; header
  `:1-101`, `readonly SESSION=39` `:110`, defaults `:128-180`, `usage` `:182-764`,
  `parse_arguments` `:800-1030`, `mode_offline` `:1474-1691`, `mode_host`
  `:1693-1908` (exports `:1774-1854`), `mode_external` `:1910-2000` (exports
  `:1952-1959`)). `tests/contract/test_session_thirty_nine_gate_modes.py` (1,083
  lines; `SESSION = 39` `:59`, `SESSION_PREVIOUS_NUMBER = 38` `:74`, claims table
  `:86-105`). Roster `tests/conftest.py:86-217` (Session 39's two `:215-216`).
  `test_cli_contract.py` `SHELL_COMMANDS` `:42-257`, `PYTHON_COMMANDS` `:259-337`,
  `COMMANDS_WITH_VERBS` `:521-566`.
- **The live modules to extend or read.** `tests/external/test_session38_public_lifecycle.py`
  (384 lines; **`RECORD_SESSIONS = frozenset({38, 39})` `:81`**; the `record`
  fixture `:159-177` pins `source_commit` to the control project's `:172-175`,
  D2415); `tests/external/test_session39_public_lifecycle.py` (215 lines;
  **`record39` asserts `session == 39` `:70`**); `tests/external/test_session39_public_endpoints.py`
  (543 lines; `slot_creds` `:249-261` returns `Secret`s, D2420);
  `tests/deployment/test_session39_endpoints.py` (247 lines);
  `tests/recovery/test_future_pitr.py` (`restore_isolation`, `:259-325`);
  `tests/external/redaction.py` (`Secret` `:19-25`).

**Measured at planning** (2026-10-14; no rig was run — every third-party fact
this plan needs is Run 1's, §5):

| # | Reading | Result |
|---|---|---|
| p1 | `apg-diag containers` | 42 containers healthy, four projects; no `restore` name anywhere |
| p2 | `apg-diag listeners` | 22, 80, 443, 5432 (+ loopback 53) |
| p3 | op: checkout, `free -m`, `df -h /`, units, timers | `b0249ce` clean; available 5,048 MiB; 11 G of 72 G; six units active NRestarts 0; slot3-prod's last full 2026-10-12 10:39Z |
| p4 | DNS at 1.1.1.1 | names below `slot3.` NXDOMAIN; an unknown name at the zone apex's level answers the proxied wildcard (Cloudflare A+AAAA) |

---

## 1. The divergence table

Six columns. Each row is a **measured fact about the tree at `23e3d92`** (or the
host as the planning readings left it) set against what the brief says, with the
decision this plan takes. **Next free number after this table is D2454.** Rows
the runs add go in a second table below it, in execution order.

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D2422** | D1961: *"A branch is a child deployment of its project … capacity is charged at admission like any deploy."* | A deploy bootstraps (step 6) and **exits 11 when the volume's `app_private.project_identity` names another key** (`postgres-bootstrap.py:953-997`); a restored parent volume names the parent. A deploy requires the key's own active secret generation (`deploy-project.py:929-962`), materialized from the key's own Infisical project (`naming.py:1293`) — which only a provider-administering credential creates (D1953). Compose profiles are cumulative by session (`project-runtime.sh:107-117`), so no facility can drop auth, REST, MCP, docs or the collector from a deployed project. | **A branch is its own compose project, not a deploy**: `infra/branch/compose.yaml` with exactly three services — `postgres` (the parent's built image id), `customer-pool`, `customer-direct` (`${PGBOUNCER_IMAGE}`) — on two networks of its own (`edge`, `internal: true`), run by **`bin/branch-runtime.sh`** (root; `create\|reset\|delete\|start\|status`), recorded in **`/etc/agentic-postgres/branches/<key>/<branch>/branch.json`**. **No secret of its own**; the identity sentinel is **kept** (a product bootstrap aimed at a branch volume still exits 11 — a guard, not a defect). Admission is charged by the same `capacity_reading.decide` inside `create` (D2431). | The deploy pipeline's guarantees all assume a project with its own identity and its own secrets; a branch has neither and needs neither. The three services are the only ones a branch's promise (*"a Postgres copy at a point in time"*) uses. | **0271** |
| **D2423** | D1961: *"named by a new `naming.branch_names(key, branch)` with its own stem (ADR 0151's discipline)"*. | Project keys are `slug-env` with hyphens anywhere (`config.py:842-843`): a key `slot3-prod-br-dev` is legal, so a stem `apg-<key>-br-<branch>` could equal another project's. A key never holds `_`; Docker volume, network, container and Compose project names accept `_`. The drill's stem is `apg-<key>-restore-<id>` (`naming.py:899-948`). | **`naming.branch_names(key, branch)` → stem `apg-<key>_<branch>`**: compose project, volume `…-postgres`, networks `…-edge` / `…-internal`, containers `…-postgres-1` / `…-customer-pool-1` / `…-customer-direct-1`, the one-shot `…-pgbackrest` and recovery `…-recovery` containers, TCP routers `…-customer-pool` / `…-customer-direct` — every one through `compose_name` (truncated with a fingerprint, `:220-247`). **Branch name `^[a-z][a-z0-9]{1,11}$`; `main` refused** (the project is `main`). A test holds that no branch stem equals any project stem or drill stem for every legal key (property over generated keys). | A separator a key cannot contain makes the collision impossible by construction rather than unlikely. | **0271**, 0002, 0151 |
| **D2424** | D1961: *"restored from the parent's repository at a target time … through the restore drill's argv made persistent, started with archiving off and no backup stanza of its own"*. | The drill restores with a one-shot container inheriting the parent's repository mounts read-only on the parent's backup network, then starts an instance with the SAME mounts (D1010: pgBackRest writes `--config` into `restore_command`), waits for promotion, and tears everything down (`restore-test.py:359-455`). | **Three phases, in `bin/branch-runtime.py create`**: (1) **restore** — `restore_drill.restore_arguments` + the drill's mounts, into the branch's volume; (2) **recovery** — a `…-recovery` container with the drill's mounts on the parent's backup network, `postgres -c archive_mode=off`, until `pg_is_in_recovery()` is false; then **removed**; (3) **persistent** — `docker compose -p apg-<key>_<branch> -f infra/branch/compose.yaml up -d postgres` with **no repository mount, no backup network**, `-c archive_mode=off -c archive_command=/bin/false`. A new `src/agentic_postgres/branch_plan.py` builds and asserts all three (D2426). **Rig 40a** proves phase 3 starts on the promoted volume with the repository unreachable (`restore_command` still in `postgresql.auto.conf`, harmless without `recovery.signal`). | Recovery needs the repository; a living copy must not have it. Separating the two is the property, and naming the phases makes the assertion checkable. | **0271**, 0151, 0192 |
| **D2425** | D1961: *"at a target time (default: now)"*; D1963: *"Restore to new branch is `branch.create` with a target time."* | The drill always uses `--type=time` (`restore_drill.py:481-500`). PostgreSQL refuses to promote when recovery ends before its target (expected: *"recovery ended before configured recovery target was reached"* — **unmeasured here**); pgBackRest refuses a target before its oldest backup (expected: no backup set qualifies — **unmeasured**). | **`branch.create` with no target restores to the end of the archived WAL (`--type=default`) and records the point it reached** (`pg_last_xact_replay_timestamp()`); **`restore.create` requires `target_time`** (`--type=time --target-action=promote`). **Rig 40a measures both failures and their text**; `branch-runtime` maps each to exit 7 *"the point … is outside this project's restore window (<earliest> … <latest>)"* before anything persists, and the reconciler to `invalid_request`. **The window is checked against the recorded backups reading first** (D2435); the rig's text is the second line of defence. | *"Now"* is not a time a recovery can target on an archive that lags by up to `archive_timeout`; the end of the archive is, and the branch says which instant it reached. | **0271** |
| **D2426** | Stage plan §8: *"A branch starts re-keyed and cannot write its parent's repository"*; §9 stop. | `assert_disposable` (`restore_drill.py:414-478`) refuses the live volume, a writable inherited mount and `--delta`, and **does not check `archive_mode`** although ADR 0151 §5 says it does (D2447). A persistent instance has no assertion at all. | **`branch_plan.assert_branch_safe(plan)`** — refuses: the branch volume equal to or mounted by the parent; any writable inherited mount; `--delta`; a recovery command without `archive_mode=off`; **a persistent service with any mount from the parent's secret generation, any `/etc/pgbackrest` mount, the parent's backup network, or an `archive_mode`/`archive_command` other than `off` / `/bin/false`**. Exit 7 before anything starts. **Rig 40a's control**: the repository's object count (posix repo: `find … \| wc -l`; on the host, `pgbackrest info` + R2 listing through the parent) before and after a branch's whole life — unchanged, while a deliberately mis-built persistent service (archiving on, the mounts present) changes it. | The property *"cannot write the parent's repository"* is a missing path and a missing credential, checked on the argv, with a control that shows the check is the reason. | **0271**, 0151 |
| **D2427** | D1961: *"re-keyed before its endpoint opens — every login role's password regenerated and every agent and refresh credential revoked inside the branch"*; ADR 0269 `:134-136`: *"rotate both customer roles before a branch's names open"*. | A physical restore carries `pg_authid` whole: the six platform login roles' verifiers, the customer roles' verifiers, the superuser's. Nothing rotates every role (no hit). No auth service runs in a branch (D2422), so `app_private`'s credentials open nothing there, and `customer_admin` has no grant on `app_private` (ADR 0269). | **The re-key, one transaction, through `container_exec.run` as `postgres` on the local socket, BEFORE the poolers exist**: every role in `naming.database_roles(key)` except the two customer roles → `ALTER ROLE … NOLOGIN PASSWORD NULL`; the superuser → `PASSWORD NULL` (LOGIN kept, local trust only); `customer_app` / `customer_admin` → `LOGIN CONNECTION LIMIT <small's 2/2> PASSWORD :'verifier'` with **the branch's own verifiers from the operation's arguments** (stdin, never argv — `credential.rotate`'s path); `UPDATE app_private.refresh_families SET revoked_at = now(), revoked_reason = 'branch' WHERE revoked_at IS NULL`; `UPDATE app_private.agent_credentials SET expires_at = now() WHERE expires_at IS NULL OR expires_at > now()`; counts printed. **Not touched**: user password hashes (no auth service reads them in a branch; no customer grant reaches them — stated in ADR 0271). **Rig 40a's control**: the parent's `customer_app` password connects to the restored instance before the re-key and is refused after; the branch's verifier connects after; `migration_user` with the parent's password refused after. | A branch that answers its parent's password is a second door to the parent's data. Doing it before the poolers exist makes *"before the endpoint opens"* an ordering a test can read. | **0271**, 0269 |
| **D2428** | D1958 (3) for a project's names; D1961: *"credentials and routing that differ"*. | Measured at planning (p4): names below `slot3.agenticpostgresql.com` are NXDOMAIN; HTTP-01 needs each name to resolve to the host; no DNS credential on the host (ADR 0268, D2335). | **The operator, 2026-10-14: two grey wildcard records per slot, created once**: `*.pool.<slot domain>` and `*.direct.<slot domain>` → the host's IPv4, DNS only, no AAAA (Sheet P1; `slot3-prod`'s on day 1). **`naming.branch_endpoint_hosts(domain, branch)` → `<branch>.pool.<domain>`, `<branch>.direct.<domain>`** (253-character refusal like `endpoint_hosts`). `branch-runtime create` reads both names with `slot.dns_reading` (exact A, no AAAA) **before admission** and refuses exit 5 *"this project's branch names do not resolve to this server: create the two wildcard records (operator guide §22)"* otherwise. | A per-branch record by hand would make every branch wait on the operator; one wildcard per door per slot is the same discipline as the slot's own records, paid once. | **0271**, 0268 |
| **D2429** | ADR 0268: one HTTP-01 certificate per project; Let's Encrypt: 50 new certificates per registered domain per week (`bin/edge.sh:12-18`), and (**unread here**) a smaller limit on duplicates of one exact set of names. | Rig 39b measured a TCP router's `tls.certresolver` + `tls.domains` issuing one certificate for two names. **Whether Traefik reuses a stored certificate when a router with the same names disappears and returns is unmeasured.** | **One certificate per branch name pair**, by the branch poolers' labels exactly as a project's (`_customer_tcp_labels` with the branch's hosts). **Rig 40b** (Pebble, Session 39's rig 39b as the template): a TCP router created, removed, created again with the same two names → **count Pebble's orders** (expected: one); **control**: two new names → a second order. The duplicate-set limit is read from Let's Encrypt's published rate-limit page on the rig's day and recorded with its date (never from memory, D267). With one live branch per project (D2430) and the measured reuse, a week's branch churn on one slot stays under the duplicate limit; the ADR states the arithmetic. | Every branch create is a production issuance; a limit met mid-trip is an operator-visible failure the customer cannot fix. | **0271**, 0268 |
| **D2430** | Stage plan §5: *"`branches_total` read from a constant until 41"*; threat #4: *"the branch half (Session 40)"*. | Nothing counts branches. `control_request_operation` refuses only a second non-terminal operation for the key (`0004:63-68`). `OPERATION_ERROR_CODES` (`errors.py:234`) is a closed list a test holds (`test_operation_types.py:222`). | **The operator, 2026-10-14: one live branch per project.** `BRANCHES_PER_PROJECT = 1` in `services/auth-api/app/operations.py`; **`409 branch_limit_reached`** (*"this project already has a branch; delete it first (one per project in this beta)"*) from the route AND from `control_request_operation` (0006), **before an operation row exists**, counting recorded live branches plus non-terminal `branch.create`/`restore.create` rows. The closed error list widened by exactly that code under ADR 0271 (the stage plan named it, D1954). **A capacity refusal stays `capacity_exhausted` from the branch's own admission** (D2431); neither reader produces the other's code (a test holds each with the other green). | The limit is the one entitlement this session can enforce honestly; it is also the arithmetic that keeps D2429's certificates and D2431's memory bounded. | **0271**, 0221 |
| **D2431** | D1961: *"capacity is charged at admission like any deploy"*; stage plan *Measures*: *"a branch's capacity charge"*. | `capacity_probe.read` walks project state directories only (`:244-357`); a branch adds a cluster nobody counts; every deploy's admission and `doctor capacity` would read the node as emptier than it is. | **A branch's charge is the `small` profile's database charge, 192 MiB** (`compute_profiles.py:40-80`, `config.py:806-819`) — every branch runs `small`'s database settings whatever the parent's profile, written into `branch.json` as `unreclaimable_mb`. **`capacity_probe.read` gains `branches`**: every readable `branch.json` under `/etc/agentic-postgres/branches/*/*/` adds its charge to `committed` and is named on the committed line (*"slot3-prod_dev (branch) 192"*); **an unreadable `branch.json` is `unreadable`** (decide refuses, ADR 0195). Grep every reader of `capacity_probe.read` and of `Reading.committed` first (D979): `bin/deploy-project.py:2398`, `bin/admit.py`, `bin/doctor.py capacity`, the reconciler's admit step. `branch-runtime create` calls `capacity_reading.decide` with the candidate 192 before the restore and refuses exit 12. **Rig 40c** reads a branch's resident memory (three containers, `docker stats`) to set the poolers' `mem_limit` and to compare with 192. | A cluster admission cannot see is the D767 class at its largest. | **0271**, 0221, 0222 |
| **D2432** | D1963: *"Test restore is a `restore-test` run as an operation."* | `restore-test.sh` exists as the operator's drill; no operation type `restore.test` exists, and the control CHECK (`0003:34-38`) does not name one. | **The operator, 2026-10-14: not built.** A branch created at a point IS a tested restore (the recovery phase promotes or fails); the backups surface's text says so (*"to test a restore, create a branch at a point in its window"*). No Ledger row is added; `backups_and_pitr`'s `stage5_reality` names it. The operator's `restore-test.sh` stays the operator's. | A second operation that does what `restore.create` does and then deletes it would be a feature that adds a code path and no capability. | **0271** |
| **D2433** | Stage plan §5: *"branch TTL as a reconciler trigger (the ADR superseding 0186 for branches only)"*; D1953(a): operations are *"created by `/api/v1` and never by the reconciler"*. | ADR 0186 `:74-83`: *"No unit, timer, cron or deploy step reads `expires_at` and acts"*; `:99-100`: the ADR to supersede. `control_operations.requested_by` is `NOT NULL` (`0003:41`). | **The operator, 2026-10-14: built.** `expires_at` optional on `branch.create` / `restore.create` / `branch.reset` (**at least 15 minutes and at most 7 days** after the request, refused otherwise — the minimum keeps a branch alive past its own creation), recorded in `branch.json` and `app.control_branches`. **The reconciler's idle loop** (every `RECORD_SECONDS`) calls **`app.control_request_expiry(p_project, p_branch)`** — SECURITY INVOKER, **granted to nobody**, reached through `container_exec` like `control_record_slots` — which inserts ONE `branch.delete` **with `requested_by` = the member whose operation set the expiry** and a new column **`origin text NOT NULL DEFAULT 'member' CHECK (origin IN ('member', 'expiry'))`**, `CHECK (origin = 'member' OR type = 'branch.delete')`; a no-op while any operation for the key is non-terminal. **ADR 0272 supersedes ADR 0186 for branches only** and amends ADR 0256 by one sentence (*the reconciler requests exactly one kind of operation: an expired branch's deletion*). | The trigger is bounded to the one object whose expiry the customer set and whose loss is a copy; a project's expiry stays a fact. Keeping `requested_by` a member keeps every row attributable. | **0272**, 0186, 0256 |
| **D2434** | D1963: *"`restore.create` = `branch.create` with a target time."* | `restore.create` → `restore_to_branch` (`operations.py:50-62`); `test_every_operation_type_names_a_ledger_row_and_is_accepted_iff_its_row_is_reachable` (`test_reality_ledger.py:213`) requires a reachable row's types to be accepted, and an accepted type must be executed (`test_operation_types.py`). | **`restore.create` is executed as `branch.create` with `target_time` required**: one handler, two entries in `HANDLERS`; `POST /v1/projects/{key}/restores` → `restore.create`; the CLI's `apg branch create --at T` sends it (D2437). Its result carries `target_time` and the reached point. | One code path, two names the specification and the Ledger already use. | **0271** |
| **D2435** | D1963: *"The backups surface is the doctor's three readings served through `/api/v1`, with the restore window computed from `pgbackrest info` — never declared."* | The control plane cannot reach the host; the reconciler is the only host actor and already records slots every 120 s (`reconciler.py:1188`). `backup.sh info --json` reads pgBackRest through the live container and costs R2 requests per call; `latest_recoverable_time` is the newest backup's stop time — a floor, not the archive's end (`backup_report.py:118-130`). | **The reconciler records each live managed project's backups reading every `BACKUP_RECORD_SECONDS = 900`** into **`app.control_backup_readings`** (key, `observed_at`, `repository_status`, `archiver_status`, `mirror_status`, `earliest`, `latest`, `last_full_at`) via **`app.control_record_backups`** (INVOKER, granted to nobody). **`earliest`** = the oldest kept backup set's start (`pgbackrest info` backup list — `summarise` gains `oldest_backup_start`); **`latest`** = `pg_stat_archiver.last_archived_time` (the archiver query the doctor runs, `doctor.py:438-471`). `GET /v1/projects/{key}/backups` serves it with `observed_at`; **older than 2 × 900 s, or a status the classifiers read `UNKNOWN`, is served as `could_not_determine` with the reason** — never as a window. A sleeping project reads *"the project sleeps; its archiver is stopped (its last archived point: …)"* (D2182). | Every number on the surface exists as a reading with three outcomes today (ADR 0195); the work is recording it where the API can read it, with its age. | **0273**, 0195 |
| **D2436** | D1952: key scopes *"`branches:read\|write`, `backups:read`, `restores:write`"*. | Not built in 37 (`control_roles.py:126-132`; the SQL CHECK `0004:625-630` holds five scopes). | **No new scope.** Branch, restore and backups routes map to `projects:read` (reads) and `projects:write` (writes) in `KEY_SCOPES`; `branch.delete` is **admin** (as `project.delete`, D2165), every other branch write **member**. The Ledger's `api_keys` row text gains one sentence. | Five scopes with three readers each is the vocabulary the keys already use; a scope that differs from `projects:write` in no reader would be a name, not a control. | **0271** |
| **D2437** | Stage plan §5: *"`apg branch create\|list\|inspect\|reset\|delete`, `apg backup status`, `apg restore create`"*. | `apg` dispatches verb X to `bin/X.sh`; **`bin/backup.sh` and `bin/restore.sh` are root operator verbs** (`backup.py`, ADR 0189). D2353's lesson: two meanings of one verb is threat #7's confusion. | **Customer: `bin/branch.sh`** (`apg branch create\|list\|show\|reset\|delete`, dispatched into `bin/cloud.py` like `endpoint.sh`; `create --at T` sends `restore.create`), and **`apg project backups --project-key K`** (a `project` verb). **Root: `bin/branch-runtime.sh`** (the reconciler's child, an operator's read with `status`). No `apg backup` or `apg restore` customer verb. | The operator's two verbs keep their meaning; the customer's live under the nouns they act on. | **0271** |
| **D2438** | §5 *Must not*: *"Write to the parent's repository from a branch … Delete anything a branch's names do not derive"*. | The drill inspects the LIVE parent container for its mounts and image (`restore-test.py:181-207`); a sleeping project's containers are stopped (ADR 0259). `project.delete` → `project-retire.sh --destroy-data` removes `naming.postgres_volume_name(key)` and the state directory only (`retirement.py:221-343`), never a branch's names. | **`branch.create`/`restore.create`/`branch.reset` refuse a sleeping parent** (`invalid_request`, *"wake the project first"*, read as `export` and `resize` read it, D2219). **`project.delete` is refused while the project has a recorded branch** (`409 conflict`, *"delete its branch first"*) at the route and in the handler. `project.sleep` with a live branch is allowed (the branch is its own cluster). `branch-runtime delete` removes exactly `naming.branch_names(key, branch)`'s names and the branch's state directory, refusing any name it did not derive (a test enumerates `docker` argv). | A deletion that orphaned a branch would leave a cluster no reader charges; a restore through a stopped container is a path never measured. | **0271** |
| **D2439** | D1961: a branch is a deployment that lives. | `postgres` is `restart: "on-failure:5"` (`compose.yaml:206`): not restarted by Docker after a reboot; projects return by their units (ADR 0265, measured boot+101 s). A branch has no unit. | **The reconciler brings recorded branches back**: `start()` (after its control-database wait, D2348) runs `branch-runtime.sh start --all`, which `compose up -d --wait`s every `branch.json` and attaches the edge; a failure is logged and **recorded** as the branch's state `stopped` (never retried in a loop). **No new systemd unit.** B1 measures the branch's return time. | The reconciler is already the root actor that starts at boot and owns branches; a unit per branch would be a second lifecycle for the same object. | **0271**, 0265 |
| **D2440** | Spec §18–§20: classes `production\|development\|preview\|temporary`; `main` protected; preview TTL. | Nothing. | **One class.** A branch is a development copy; `main` is the project (the name refused, D2423); *temporary* is a branch with `expires_at` (D2433). Classes and per-class rules are `planned` text in the `branches` row. `branch_promotion` and `in_place_restore` stay `not_offered` (D1962, D1963). | One branch per project (D2430) leaves nothing for a class to distinguish. | **0271** |
| **D2441** | Stage plan §8: *"a branch is not backed up; `main` is"*. | A branch has no stanza (D2424) and no backup network. | **Stated, not built**: the `branches` row and `GET …/branches/{b}` say *"a branch is not backed up; deleting it, or losing the server, loses it"*. `branch.reset` is the way back to a point. | A copy that looked backed up would be the surface claiming more than the node does (§9 of the stage plan). | **0271** |
| **D2442** | §32 item 2: *"the eight rows back to `trial` at the bump, and the lifecycle, the sweep and the external half at ONE commit"*. | ADR 0261 (`reality_ledger.py:165-194`): a `trial` row's evidence names only claims introduced in `CURRENT_SESSION`; `lifecycle_retrial_live` and `public_endpoints_live` are 39's. `record39` asserts `session == 39` (`test_session39_public_lifecycle.py:70`); `RECORD_SESSIONS = {38, 39}` (`test_session38_public_lifecycle.py:81`). | **Session 40 introduces `lifecycle_reearned_live` (LIFE-LIVE-004) and `endpoints_reearned_live` (EP-LIVE-004)**, both external, both read from `slot4-prod`'s Session 40 lifecycle record (`tests/external/test_session40_reearning.py`). **`RECORD_SESSIONS` → `{38, 39, 40}` and `record39` accepts `{39, 40}`** — the same members, read from the newest record (a proof that reads a later record of the same shape is not weakened; each still asserts every member it asserted) — so Sessions 38's and 39's lifecycle claims re-run against 40's record and must pass too, but no `trial` row cites them. | ADR 0261 is right: a row re-trialed in 40 is proved by 40's claims; leaving the older claims unable to read a newer record would hand the merge three `failed` it did not measure. | 0261 |
| **D2443** | §32 item 3, D2418: *"No product verb redeploys a managed project at a new commit."* | Session 39's Sheet D4 ran `reconciler_dispatch.deploy_argv` (`:296-303`) by hand with the slot manifest, then `control.sh adopt` under the project's organisation. | **`sudo bin/slot.sh redeploy --host host.yaml --slot K --confirm K`**: refuses unless the slot is `allocated` with a deployed document, **refuses while `agentic-postgres-reconciler` is active** (*"stop the reconciler first (D2178)"*), runs exactly `deploy_argv` for `/etc/agentic-postgres/slots/<K>/manifest.yaml` with the deployed document's `through_session` replaced by `CURRENT_SESSION`, then `customer-credentials.sh sync`, then adopts with **the organisation read from the control registry's row for K** (`control.py`'s registry read — never typed). Exit 12 from admission is carried. ADR 0256 amended by one paragraph. **First live: Sheet R2d (Run 9).** | A release move the operator types by hand on a customer's project is the step that drifts; one verb with the reconciler's own argv cannot. | 0256 |
| **D2444** | §32 item 2: *"the slot's routes probed before the first resize (D2324)"*. | D2324 / `capacity.UNMEASURED` `:1793`: the resize and sleep windows as the slot's own routes see them — unprobed in 38 and 39. | **`s40-lifecycle.py` probes `slot4-prod`'s app route and its pool name** (psql `select 1` every 2 s) from the claim through the deletion, and records each window per class. Run 11 moves the `UNMEASURED` row into the envelope if both resizes were probed. | The number a customer is told on a resize is the one never measured from the customer's side. | 0258 |
| **D2445** | §32 item 4: *"The OVH upgrade (D2342) … owed before Session 41."* | Available 5,048 MiB with four projects (p3); safe available 4,620 at admission (Session 39); the trip's peak: `slot4-prod` at `large` (840) + `slot3-prod` (192) + one branch (192 + two poolers). | **No upgrade in 40** (the operator's 39 decision stands); the peak is charged and fits by ~3.4 GiB; Sheet E0 re-reads `free -m`. **The upgrade stays owed before 41.** | ClickStack (41) is the first thing that does not fit; branches do. | — |
| **D2446** | CLAUDE.md §2: *"M7: Sheets X1/X2 (retire Hetzner) are ALLOWED NOW … and NOT YET RUN"*. | The old host's three projects stopped, units disabled (the way back). | **Not this plan's.** M7's sheets stay in `docs/plans/session-38-migration-plan.md` and may run on any day outside this trip's sittings; this plan's sheets never name the old host. | Two trips' sheets interleaved is D1510's failure in waiting. | — |
| **D2447** | Citations met while planning. | ADR 0151 §5 (`:166`) says `assert_disposable` checks `archive_mode=off` — it does not (`restore_drill.py:414-478`; the check is `test_restore_test_command.py:327`); `reconciler_dispatch.py:77-78` *"The six executed types"* (seven); `0003:33` cites `src/agentic_postgres/operations.py` (the table is `services/auth-api/app/operations.py`); stage plan D1961 cites the drill's argv as *"persistent"*, but the drill's instance needs the repository mounts to recover (D1010). | **Recorded so the executor does not chase them.** Run 2 adds the `archive_mode` check to `assert_disposable` itself (stricter; the test at `:327` then reads the code), corrects the dispatch comment; ADR 0151 gets a status line; `0003`'s comment is an applied migration's (D912) — not edited, noted in 0006's header. | A citation that looks measured and is not is the class this project keeps producing. | 0151 |
| **D2448** | §32: *"a trip that moves its commit re-reads every reader that pins the commit"* (D2415). | Session 39's sweep and external half first ran AFTER the lifecycle consumed slot2; two defects (D2413 nine restart proofs; D2416 a `KeyError`) moved the commit and stranded the lifecycle's record. **No slot is free after `slot4-prod`.** | **Day 1 ends with V1 = the whole host suite with `-k "not after_reboot and not lifecycle and not branch"` and X0 = the whole external half with the same filter, both writing nothing**, at the deploy commit, before `slot4-prod` exists as a project. A defect they find is repaired and the commit moves on day 1, when moving is free. **A commit move after `slot4-prod`'s deletion is a stop** (§9): the operator chooses between tagging with the lifecycle claims `failed` and preparing `slot5-prod`. | The dry run costs an hour; Session 39's late defects cost a slot and three claims. | 0261 |
| **D2449** | ADR 0269: a customer rotates a credential through `credential.rotate`. | `credential.rotate` acts on a project's roles (`reconciler.py:865-908`). | **A branch's credentials are set at creation and at reset only**: `branch.create`/`restore.create`/`branch.reset` carry `app_verifier` and `admin_verifier` (the `credential.rotate` pattern, `operation-arguments.schema.json:41-57`); `bin/branch.sh create\|reset --password-dir D` writes `D/<key>/<branch>/customer_app` and `…/customer_admin` (0700/0600, `O_EXCL`) and sends only verifiers. No `credential.rotate` on a branch. | A reset already replaces the cluster; a second rotation path for a copy would be a second surface for one secret. | **0271**, 0269 |
| **D2450** | D1961: *"provenance"*; §5 *Ends*: *"its provenance read"*. | Nothing records which point a restore reached except the drill's evidence file. | **`app.control_branches`** (0006): `project_key`, `name`, `state` (`creating\|ready\|stopped\|deleting\|deleted\|undetermined`), `requested_point` (NULL = end of archive), `reached_point`, `timeline`, `parent_commit`, `pool_host`, `direct_host`, `expires_at`, `expires_for` (the member), `created_at`, `observed_at`, `deleted_at` — written by the reconciler (`app.control_record_branches`, INVOKER, granted to nobody) from `branch.json` after each branch operation and every `RECORD_SECONDS`; read by `GET /v1/projects/{key}/branches[/{name}]` (`app.control_list_branches`, DEFINER, viewer+). A state read from a missing or unreadable `branch.json` is `undetermined` (ADR 0195). | The branch's point is the one fact a customer acts on; it belongs where the API reads, with its age. | **0271**, 0195 |
| **D2451** | Threat #1: *"a foreign branch id and a missing one return the same answer"*. | `GET /v1/projects/{key}` answers a foreign and a missing key alike (`THR-CTL-ENUMERATION`, `docs/threat-model.md:45`). | **Every branch route resolves the project first through the same reader**, so a foreign project's branch and a missing project's answer the same `404 not_found` body byte for byte; a missing branch of the caller's own project answers `404 not_found` too. A test compares the three bodies and their status. | The project read is already the enumeration control; branches inherit it rather than re-implementing it. | 0251 |
| **D2452** | Stage plan *Measures*: *"branch creation time against the parent's repository size on the new host"*. | No restore time of `slot3-prod` exists; slot3's repository holds one full (2026-10-12) and its incrementals. | **Sheet E0 runs the drill on `slot3-prod` once** (`sudo bin/restore-test.sh --target-time <E0's time − 10 min> --project-dir /etc/agentic-postgres/projects/slot3-prod`; disposable, ADR 0151) and reads `pgbackrest info` sizes: the restore's time and the repository's size are the baseline the branch's time is compared with (Run 10) and the envelope's row (Run 11). If it exceeds `OPERATION_SECONDS` (1,800 s) less 300 s, **Run 5 raises the bound for the branch types only** and says so. | A branch create that hits the 30-minute bound is finished `failed` with its restore half done — a customer told *"failed"* for a restore that was merely slow, and a volume the delete must clean up. | 0151 |
| **D2453** | — | Both external lifecycle modules read the record through `APG_LIFECYCLE_RECORD_FILE`; the branches have no record and no roster variable. | **One new gate variable, `APG_BRANCH_RECORD_FILE`** (host and external), the branch instrument's record (0600; `session`, `source_commit`, every operation id, the marker instants, the reached points, the doors' checks). **The Session 40 gate accepts exactly Session 39's flags plus `--branch-record-file FILE`.** `--lifecycle-record-file` and `--slot-outputs` are reused for `slot4-prod`; `--live-slot-outputs` and `--customer-credential-dir` for `slot3-prod` and its branch. | One record per instrument, the house shape. | — |

**Rows added by the runs** (in execution order).

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D2454** | D2425: `restore.create` with `--type=time --target=<T>`; `restore-test.py --help`: *"a timestamp PostgreSQL parses (ISO 8601 with an offset)"*. | **Rig 40a, measured:** pgBackRest 2.59.1 refuses the ISO `T` form before writing anything — `ERROR: [029]: automatic backup set selection cannot be performed with provided time '2026-10-14T08:04:56.104356+00:00'`, *"time format must be YYYY-MM-DD HH:MM:SS with optional msec and optional timezone"*, exit 29. Attempt 1 lost every time case to it; Sheet E0's script carried the `T` form too and was corrected before the operator ran it (sha256 `9ed449ac…`). `docs/backup-operations.md:262` already uses the space form. | **The product renders every time target as `YYYY-MM-DD HH:MM:SS.ffffff+00:00`** from a parsed, timezone-aware instant — `branch_plan` for a branch, and the drill too (Run 2: one formatter in `restore_drill`, `restore_arguments` refuses anything else; the drill's `--help` corrected). The API takes RFC 3339 and never passes it through. | A target the CLI accepts and the restore refuses is a failed operation the customer cannot diagnose. | 0271, 0151 |
| **D2455** | D2427: `UPDATE app_private.refresh_families SET revoked_at = now(), revoked_reason = 'branch'`. | `revoked_reason` is `app_private.refresh_revocation`, an enum of `logged_out`, `reuse_detected`, `credential_changed`, `administrative` (`0023:50-55`). **Rig 40a:** `invalid input value for enum app_private.refresh_revocation: "branch"`. | **`revoked_reason = 'administrative'`.** No released migration adds a value (D912, and a branch must not migrate the release schema); ADR 0271 says which value and why. | The only value that means "ended by an operator's act" is the existing one. | 0271 |
| **D2456** | D2425/D2435: the window's top is `pg_stat_archiver.last_archived_time`; a target inside it restores. | **Rig 40a:** a target AFTER the last commit — even inside archived WAL (case c2: a `CHECKPOINT` and a switch after row 2) — makes recovery log *"last completed transaction was at log time <row 2's commit>"* then `FATAL: recovery ended before configured recovery target was reached`; the container exits 1 in 3 s; pgBackRest itself exited 0. A target an hour ahead: the same. A live project's auth worker commits a heartbeat every `POLL_SECONDS = 5` (`services/auth-api/app/workflow_worker.py:96`, `workflow_heartbeat` an `INSERT … ON CONFLICT DO UPDATE`). | **`latest` stays the archiver's reading, served as approximate by the seconds between commits**; `branch-runtime` maps the FATAL to **exit 7** *"the newest change in this project's archive is at <last completed transaction>; your point is after it"* (parsed from the recovery log), removes the volume, and the reconciler finishes `invalid_request`. A live parent meets it only in the archive's last seconds; a sleeping parent is refused before (D2438). | The bound is the last commit, which no reading the doctor has can see; the recovery's own log names it exactly. | 0271, 0273 |
| **D2457** | D2435: *"`earliest` = the oldest kept backup set's start"*. | **Rig 40a:** a target before the only full backup → `ERROR: [075]: unable to find backup set with stop time less than '<T>'`, exit 75, 1.1 s. pgBackRest selects a set whose STOP precedes the target. | **`earliest` = the oldest kept set's STOP time**; `summarise` gains `oldest_backup_stop` (not `_start`); `[075]` maps to exit 7 *"the point is before this project's oldest backup (<stop>)"*. | A window that starts at a set's start offers minutes no restore can reach. | 0273 |
| **D2458** | D2427: *"the superuser → `PASSWORD NULL` (LOGIN kept, local trust only)"*; rig 40a's control: *"the parent's `customer_app` password … refused after"*. | The restored `pg_hba.conf` is the parent's, i.e. the image's initdb: `local all all trust`, `host all all 127.0.0.1/32 trust`, `::1/128 trust`, then `host all all all scram-sha-256`. **Attempt 2 connected over `127.0.0.1` inside the container and read the parent's password as ACCEPTED after the re-key** — trust, not a password. Attempt 3, from a peer container on the branch's network: the parent's `customer_app`, `migration_user` and superuser passwords accepted before and **refused after**; a wrong password refused before (SCRAM decides); loopback still trusts any password. | **Every re-key proof connects from a PEER container on the branch's network, never over loopback**; the loopback reading is kept as the control that would have misled. The superuser's `PASSWORD NULL` leaves the local socket and in-container loopback, which no network peer reaches. ADR 0271 states it. | A proof of a credential that connects where no credential is asked proves nothing; attempt 2 is the record of how close that came to a §9 stop. | 0271 |
| **D2459** | D2424: the persistent phase starts with *"`restore_command` still in `postgresql.auto.conf`, harmless without `recovery.signal`"*. | **Rig 40a (e):** `postgresql.auto.conf` holds `restore_command = 'pgbackrest --stanza=… archive-get %f "%p"'`, `recovery_target_time` and `recovery_target_action = 'promote'`; no signal file; the instance started out of recovery with `archive_command` `(disabled)`. | **The re-key also runs `ALTER SYSTEM RESET restore_command`, `recovery_target_time`, `recovery_target_action`** so a branch's configuration names nothing of its parent's repository. Unmeasured here: Run 3's cluster test measures the file after it. | Inert is not absent; a later `recovery.signal` would make it a path to the repository's name. | 0271 |
| **D2460** | D2427: *"Only then do the two customer poolers start"*. | **Rig 40c:** a userlist holding a SECOND verifier of the same password (a different salt) fails every login through SCRAM passthrough (`password authentication failed`, 0/20 clients); the verifier read back from `pg_authid` → 20/20 pooled clients answered, the direct door admitted the branch's administrator and refused the parent's password (`SASL authentication failed`). | **The branch's userlists are written by the reader `customer-credentials.py` already uses** (`VERIFIER_QUERY`, `customer_credentials.py:36-39`), from the branch's own `pg_authid`, after the re-key — never from the operation's verifier argument. | The pooler's secret must be the server's own; one reader for both doors. | 0271, 0269 |

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

**One new family, `BR`** (the stage plan's proposal, D691): the regex at
`tests/contract/test_acceptance_registry.py:121` gains `BR`, and the family
comments gain one sentence after `:120`: *Session 40 (ADR 0271-0273) adds `BR` for
branches and restore to a branch — the names, the restore plan, the re-key, the
operations, expiry, the backups surface.* **Fourteen requirements, fourteen claims,
all `target_session: 40`, all P0 — ten offline, three external, one host.** Node
ids below are **proposed; Run 8 writes what the runs actually wrote**, read out of
the tree with `pytest --collect-only -q` (D1236, D2129). Registry entries are
committed by Run 8 with the constant (D690), under **`# Session 40 (ADR
0271-0273)`**.

| Requirement | What it states | Offline node ids (proposed) | Live half |
|---|---|---|---|
| `BR-NAME-001` | `branch_names` derives every name from the stem `apg-<key>_<branch>`; no branch stem equals any project or drill stem; the name rule and `main` refused; the branch hosts derive from the domain and refuse > 253 | `tests/contract/test_branch_naming.py::test_every_branch_name_derives_from_one_stem`, `::test_no_branch_stem_equals_a_project_or_drill_stem`, `::test_the_branch_name_rule_refuses_main_and_bad_names`, `::test_the_branch_hosts_derive_from_the_domain` | — (`branch_naming`) |
| `BR-PLAN-001` | The restore and recovery phases inherit only read-only mounts and never `--delta`; the recovery runs `archive_mode=off`; the persistent service has no repository mount, no parent secret path, no backup network, archiving off and `/bin/false`; a wrong plan exits 7 before anything starts; `assert_disposable` now checks `archive_mode` in code | `tests/contract/test_branch_plan.py::test_the_restore_phase_is_the_drills_argv`, `::test_the_persistent_service_cannot_reach_the_repository`, `::test_a_plan_that_could_write_the_parent_is_refused`, `tests/contract/test_restore_test_command.py::test_assert_disposable_refuses_archiving` | — (`branch_restore_plan`) |
| `BR-REKEY-001` | The re-key's statements: every non-customer role `NOLOGIN PASSWORD NULL`, the superuser `PASSWORD NULL`, the customer verifiers through stdin, families revoked, agent credentials expired; on a real cluster restored by pgBackRest, the parent's customer password is accepted before and refused after, the branch's accepted, a platform role refused; the poolers are started only after it | `tests/contract/test_branch_rekey.py::test_the_rekey_names_every_role_once`, `::test_no_verifier_reaches_an_argv`, `tests/contract/test_branch_runtime_on_a_cluster.py::test_the_parents_password_opens_nothing_after_the_rekey`, `::test_a_platform_role_cannot_log_in_to_a_branch`, `tests/contract/test_branch_runtime.py::test_the_poolers_start_after_the_rekey` | — (`branch_rekey`) |
| `BR-CTL-001` | Control set `0006`: `control_branches`, `control_backup_readings`, the `origin` column and its CHECK, the allow-list with the four types, `control_request_expiry` / `control_record_branches` / `control_record_backups` granted to nobody; the routes, the matrix and key scopes; `branch_limit_reached` before a row; a sleeping parent and a branch-holding delete refused; the enumeration answer identical; the contract snapshot | `tests/contract/test_control_branches.py::test_a_second_branch_is_refused_before_a_row`, `::test_a_foreign_and_a_missing_branch_answer_alike`, `::test_a_project_with_a_branch_cannot_be_deleted`, `::test_the_branch_routes_need_a_human_or_a_scoped_key`, `::test_only_an_expiry_may_request_without_a_member_route`, `tests/contract/test_app_contract_aggregate.py::test_the_control_snapshot_is_what_this_checkout_generates` (existing) | — (`branch_control`) |
| `BR-DISPATCH-001` | The four branch types have one handler each (restore.create sharing create's), steps `admit, restore, recover, rekey, doors, record` for create; argv built from typed arguments only; verifiers on stdin; the parent must be a slot and awake; the window checked before the restore | `tests/contract/test_reconciler_dispatch.py::test_every_accepted_type_has_one_handler` (existing, its table widened), `::test_a_branch_create_is_argv_only`, `::test_a_branch_of_a_sleeping_parent_is_refused`, `::test_a_point_outside_the_window_is_refused_before_the_restore` | — (`branch_dispatch`) |
| `BR-TTL-001` | An expiry beyond 7 days is refused; the idle loop requests one `branch.delete` per expired branch, attributed to the member who set it, `origin = expiry`; nothing while an operation is open; a project never expires | `tests/contract/test_branch_expiry.py::test_an_expired_branch_is_deleted_by_one_request`, `::test_the_request_names_the_member_who_set_the_expiry`, `::test_an_open_operation_defers_the_expiry`, `::test_a_project_expiry_is_still_never_a_trigger` | — (`branch_expiry`) |
| `BR-CAP-001` | A branch's charge is `small`'s 192; `capacity_probe` adds every readable `branch.json` and names it; an unreadable one is `unreadable`; a branch's admission refuses exit 12 when the charge does not fit | `tests/contract/test_capacity_probe.py::test_a_branch_is_committed`, `::test_an_unreadable_branch_is_undetermined`, `tests/contract/test_branch_runtime.py::test_a_branch_that_does_not_fit_is_refused` | — (`branch_capacity`) |
| `BR-BACKUP-001` | The recorded reading computes `earliest` from the oldest backup set and `latest` from the archiver; a stale or unknown reading is served `could_not_determine` with its reason; a sleeping project says so | `tests/contract/test_backups_surface.py::test_the_window_is_computed_from_the_readings`, `::test_a_stale_reading_is_not_a_window`, `::test_a_sleeping_project_says_its_archiver_is_stopped` | — (`backups_surface`) |
| `BR-CLI-001` | `apg branch create\|list\|show\|reset\|delete` and `apg project backups`: passwords generated and written 0600 once, only verifiers sent; `--at` sends `restore.create`; no verb named `backup` or `restore` dispatches to a customer command | `tests/contract/test_control_cli.py::test_a_branch_password_never_leaves_the_workstation`, `::test_at_sends_a_restore`, `tests/contract/test_cli_contract.py::test_the_operator_backup_and_restore_verbs_are_not_customer_verbs` | — (`branch_cli`) |
| `LIFE-SLOT-003` | `slot.sh redeploy` runs the reconciler's own deploy argv, refuses while the reconciler is active, syncs the doors and adopts under the registry's organisation | `tests/contract/test_slot_command.py::test_redeploy_runs_the_reconcilers_argv`, `::test_redeploy_refuses_while_the_reconciler_runs`, `::test_redeploy_adopts_under_the_recorded_organisation` | — (`slot_redeploy`) |
| `BR-LIVE-001` | From the workstation with no SSH, on `slot3-prod`: the backups surface read with a window; an expiring branch deleted by the trigger; a branch restored to the instant between two marked rows holds the first and not the second; `main` holds both; a migration applied over the branch's direct name; its provenance read; the parent's password refused at both branch names, the branch's accepted; a reset reaches the second row; the branch deleted, its names refused; a second branch refused `branch_limit_reached` | — | `tests/external/test_session40_branches.py::test_the_backups_surface_reads_a_window`, `::test_an_expired_branch_was_deleted_by_the_reconciler`, `::test_the_branch_holds_the_point_before_the_change`, `::test_a_migration_reached_the_branch_through_its_direct_name`, `::test_the_parents_password_opens_no_branch_door`, `::test_the_second_branch_was_refused_before_a_row`, `::test_a_deleted_branch_has_no_door`, `::test_this_module_uses_no_ssh` (external `branch_live`) |
| `BR-LIVE-002` | On the host, with the branch live: its three containers bounded and placed (no backup network, archiving off), its charge on the committed line, the parent's volume, `instance_uuid`, timeline and postmaster start unchanged across its life, the parent's repository written only by the parent, the branch back after the reboot, nothing of it left after the deletion | — | `tests/deployment/test_session40_branches.py::test_the_branch_is_bounded_and_unreachable_from_the_repository`, `::test_the_branch_is_charged`, `::test_the_parent_was_untouched`, `::test_the_branch_came_back_after_the_reboot`, `::test_a_deleted_branch_left_nothing` (host `branch_host_live`) |
| `LIFE-LIVE-004` | Session 40's lifecycle on `slot4-prod` at the deployed commit: the six types succeeded, the resizes decided by their reading, the export holds `app`, `api`, `public`, a second creation refused `no_slot` with no row; the slot's own route probed through each resize | — | `tests/external/test_session40_reearning.py::test_every_accepted_type_ran_on_the_slot`, `::test_the_resizes_followed_the_admission_reading`, `::test_the_export_holds_the_three_customer_schemas`, `::test_the_second_creation_was_refused_without_a_row`, `::test_the_slots_own_route_was_probed_through_each_resize` (external `lifecycle_reearned_live`) |
| `EP-LIVE-004` | Through `slot4-prod`'s names while it lived: both credentials set, both names reached verify-full, a rotation refused the old password, asleep both names refused, the platform roles refused at both doors | — | `tests/external/test_session40_reearning.py::test_the_slot_was_reached_through_both_names`, `::test_a_rotation_refused_the_old_password`, `::test_a_sleeping_slot_refused_both_names`, `::test_no_platform_role_passed_either_door` (external `endpoints_reearned_live`) |

**Expected counts** — Run 8 counts them from the tuples, never from this prose
(D1628): requirements **346 → 360**, `CLAIMS` **253 → 267**, `OFFLINE_CLAIMS`
**101 → 111**, ADRs **270 → 273**.

**Claims** (`src/agentic_postgres/evidence_claims.py` `CLAIMS`, a block commented
*Session 40 (ADR 0271-0273)*): offline — `branch_naming`, `branch_restore_plan`,
`branch_rekey`, `branch_control`, `branch_dispatch`, `branch_expiry`,
`branch_capacity`, `backups_surface`, `branch_cli`, `slot_redeploy` — **these ten
in `OFFLINE_CLAIMS`**, with the per-session assertion in
`test_session_forty_gate_modes.py` (D1237: assert THESE are in the set, never its
size). External — `branch_live`, `lifecycle_reearned_live`,
`endpoints_reearned_live`. Host — `branch_host_live`. `CLAIM_INTRODUCED_IN` gains
a row at 40 for each.

**Existing entries that move** (each a passing proof made stricter or widened to a
measured set, never weakened — CLAUDE.md §6, under the ADR named):

- **The lifecycle records** (D2442): `RECORD_SESSIONS` → `{38, 39, 40}`;
  `record39` → `{39, 40}`; node ids unchanged.
- **CTL-OPS-001**: `test_no_type_is_accepted_and_the_seven_are_executed`
  (`test_operation_types.py:99`) → **`test_exactly_the_eleven_executed_types_are_accepted`**
  at the bump (the exact set; the registry's node id moved in the same commit,
  D1119); `test_the_argument_schema_has_one_branch_per_executed_type` gains three
  branches (create/restore share one shape with `target_time` required for
  restore); `test_the_error_codes_are_one_closed_list` gains
  `branch_limit_reached` (ADR 0271).
- **OPN-DISPATCH-001**: `test_every_accepted_type_has_one_handler`'s table.
- **REC-SAFE-001** gains `test_assert_disposable_refuses_archiving` (D2447;
  stricter).
- **NODE-ADMIT-*** (grep the registry for `capacity_probe`): the committed line
  names branches — the existing node ids keep their names.
- **`THR-*` table rows**: four added in Run 8 (Run 1's list); none removed.

**New environment gates: one**, `APG_BRANCH_RECORD_FILE`, in `tests/conftest.py`'s
roster after `:216` with a comment naming D2453.

---

## 4. Irreversible operations

| Operation | Where | What makes it safe |
|---|---|---|
| The control set's `0006` frozen into `projects/control/migrations/released.lock.json`, and its proposal committed | Run 4 | `bin/migrate.sh --project project.control.example.yaml freeze-lock`; the proofs apply the release set then the control set's six as `migration_user` before the freeze; `AP900` down; the proposal by the product's own `propose` (D2183); no released migration (D912) |
| `CURRENT_SESSION` 39 → 40; `VERSION` 1.17.0 → 1.18.0; eleven Ledger rows → `trial` | Run 8 | All-or-nothing (D690); `README.md:7`; every `--session 39` / `--through-session 39` literal on the documented path moved and counted per file (D678/D1484); the `trial` rules (ADR 0261) |
| `bin/session-40-check.sh` | Run 8 | Derived from 39's by diff (D1482); header and usage rewritten whole (D1488); exactly one flag added; `SHELL_COMMANDS`; `chmod 755` before `git add` |
| **Two grey wildcard records for `slot3-prod`; three grey A records for `slot4-prod`** | Sheet P1 (Run 9) | By hand at Cloudflare, DNS only, no AAAA; read back by `s40-dns.sh` before any branch or creation |
| **Provider resources for `slot4-prod`** (one Infisical project and identity, two R2 buckets and tokens, one B2 bucket and key) | Sheets P1, SL1 | As for `slot2-prod` (Session 39 SL1); `--plan` read before `--apply`; the credential shredded (D2061) |
| **`slot3-prod` redeployed at 1.18.0 by `slot.sh redeploy`** | Sheet R2d (Run 9) | The verb's first live run; the reconciler stopped; admission read; every route `ready`; the doors' certificate kept; the registry `agrees` after |
| **`slot4-prod` created, credentialed, slept, woken, resized, exported and deleted** | Run 10 | Through `/v1` only, after V1 and X0 passed at the same commit (D2448); one operation at a time; the probe running |
| **`slot4-prod` consumed** | Run 10 | The tombstone; the repository kept (ADR 0187) |
| **Branches of `slot3-prod` created, reset, expired and deleted; two production certificates (or one, if rig 40b's reuse holds)** | Run 10 | `slot3-prod`'s doctor read before and after; the parent's volume, `instance_uuid` and timeline read before and after; the probe on `slot3-prod` throughout |
| `slot4-prod`'s Infisical identity revoked | Sheet SL4 (after the tag) | `slot.sh revoke` with the operator's credential, shredded after; the directory removed by the verb itself since `ea90b2a` (D2405) — read empty-or-absent, never `rmdir`ed by hand |
| The reboot | Sheet B1 | With `slot3-prod`'s branch live; every unit and the branch read before the sweep |
| Tag `1.18.0` on the deployed commit | Run 10 | After the merge exits 5 for `documented_path` only (§7); from the WORKSTATION (D2041) |

---

## 5. Build order, run by run

Each run ends with a `**Done.**` paragraph written by the executor: what was
measured, the numbers, the rows it added, and — for a code run — the CI verdict by
full SHA. The targeted modules run ONCE at the run's close and only a failing
module is re-run. `ruff format && ruff check` before every commit; `chmod 755
bin/*.sh bin/*.py deploy.sh` before every `git add` — **and every file an image
executes directly** (D2412; `test_every_script_an_image_executes_directly_is_executable_in_the_git_index`
holds it); messages from a file with `-F`, ending with the attribution line the
session's system reminder gives. **Grep the plans for every third party before
measuring it.** **A run that renames, adds or removes a test function runs
`test_acceptance_registry` and `test_evidence_claims`** (D1119); **a run that adds
a module under `src/agentic_postgres/` runs `test_repository_contract`** (D2114);
**a run that adds or removes a `bin/` command runs `test_cli_contract` and `git
add`s it first** (D1014); **a run that adds a `document[...]` read to a `bin/`
command runs `test_container_selectors`** (D1184); **a run that touches a
documentation page runs `test_documentation_index` and
`test_session12_documented_path`**; **every new test module carries `pytestmark`
before its first test** (D1240), and the sweep-selector guard (D1242) AND
`test_environment_gates` join the targeted list of any run that adds a module —
**read a model dict with `.get("APG_…")`, never `x["APG_…"]`** (D2381). **Docker-
backed modules reuse Session 37's `tests/contract/control_cluster.py`** (`docker
rm -fv`, D2098) and rig 40a's shape for a cluster with a posix pgBackRest
repository. **Every external fixture that holds a password, verifier, token or
TOTP seed returns `tests/external/redaction.py`'s `Secret`** (D2420; the AST guard
in `test_external_helpers.py` reads new modules too). **Never print a live log's
failure body without filtering it by the secret VALUES** (D2416).

### Run 1 — the rigs, Sheet E0, the threat list, and ADRs 0271–0273

**Documentation only. Push, say it is pushed, read NO CI verdict** — except that,
because `docs/threat-model.md` and `docs/decisions/README.md` are parsed by
contract tests, run `test_acceptance_registry`, the ADR-index test (grep
`decisions/README` in `tests/contract/`) and `test_documentation_index` once
before the push.

Rigs live in WSL `~/s40/run1/rig40/` and are copied to the scratchpad. **Each
names its control and is recorded with what it printed.** Every rig uses the
pinned images from `versions.env` (the project's built postgres image: build it
once with `bin/compose.sh .generated/<example key> --runtime build postgres` from
a `--render-only` of `project.example.yaml`, then delete what the render
published, D1507) and removes what it made (`docker rm -fv`, `docker network rm`,
`docker volume rm`), read back with `docker ps -a | grep -c rig40` = 0 and
`docker volume ls | grep -c rig40` = 0.

1. **Rig 40a — a branch's whole life on a real cluster** (D2424–D2427): a
   "parent" cluster from the project image with archiving to a **posix** pgBackRest
   repository on a named volume (`repo1-type=posix`, cipher on — the only change
   from the product's S3 config, recorded), the release's roles created by
   `bootstrap_statements` (its statements applied through `psql` as the product
   applies them), `customer_app`/`customer_admin` given verifiers (ADR 0269's
   `scram.py`), one full backup. Then: `customer_admin` creates `public.marker`,
   inserts row 1, `select pg_switch_wal()`, notes `T1 = now()`, waits 2 s,
   inserts row 2, switches WAL. Cases: **(a)** restore `--type=time --target=T1
   --target-action=promote` into a second volume through a one-shot container with
   the repository mounted read-only → recovery container (`archive_mode=off`) →
   promoted; **row 1 present, row 2 absent**; **(b)** the same with
   `--type=default` → both rows, `pg_last_xact_replay_timestamp()` recorded;
   **(c)** a target after the last archived WAL → the exact error text and exit;
   **(d)** a target before the full backup's start → pgBackRest's exact error and
   exit; **(e)** the recovery container removed, the persistent container started
   on the same volume with NO repository mount and NO network but an `internal`
   one, `-c archive_mode=off -c archive_command=/bin/false` → it starts (read
   `SHOW archive_mode`, `pg_stat_archiver`), `postgresql.auto.conf`'s
   `restore_command` read and left; **the repository's file count and newest mtime
   unchanged across (a)–(e)**; **control**: a persistent container started WITH
   the repository mount and `archive_mode=on` → the count changes (a timeline
   history or WAL file appears); **(f)** the re-key: BEFORE it, the parent's
   `customer_app` password connects to the restored instance over TCP (**control
   that the re-key is load-bearing**); the re-key's statements (D2427) applied as
   `postgres` over the local socket; AFTER it, the parent's password refused, the
   branch's verifier accepted, `migration_user` with its parent password refused,
   `docker exec … psql -U postgres` still works; the row counts of the two
   `UPDATE`s printed; **(g)** the parent's `timeline_id`, `system_identifier`, and
   its `app_private.project_identity.instance_uuid` read before and after (parent
   unchanged; the branch shares `system_identifier` and the identity row — ADR 0151
   `:188-203`), and the branch's timeline > the parent's.
2. **Rig 40b — a branch's certificate, and its reuse** (D2429): Pebble +
   `pebble-challtestsrv` pinned by digest (read from Docker Hub that day; Session
   39's rig 39b digests are the start), a Docker-provider Traefik with the edge's
   static config shape, two label TCP routers for `dev.pool.a.test` /
   `dev.direct.a.test` (`tls.domains[0]`, `tls.certresolver`, `tls.options:
   postgres@file`). Read Pebble's order count (its logs) after: (1) the routers
   created → one certificate naming both; (2) the containers removed, created
   again with the same labels → **orders unchanged** (expected) and the served
   certificate's serial equal; **control** (3) routers for `qa.pool.a.test` /
   `qa.direct.a.test` → a new order. Then read Let's Encrypt's current rate-limit
   page and record the duplicate-certificate limit with the date.
3. **Rig 40c — a branch's memory** (D2431): the three branch services from rig
   40a's volume with `small`'s database settings (`shared_buffers 64MB`,
   `max_connections 48`, `memory_limit 512m`, `cpus 1.0`) and the two poolers
   (64m, 64 pids): `docker stats --no-stream` idle and after 20 pooled
   connections × 1 query; the resident figure set beside the 192 charge.
4. **Rig 40d — the expiry request on the control set** (D2433): the control set
   `0001–0005` applied to a `control_cluster.py` cluster plus a draft `0006`; an
   operation row inserted for a member with `expires_at` in the past;
   `control_request_expiry` called twice → one `branch.delete` row
   (`origin = expiry`, `requested_by` the member); **control**: an open operation
   for the key → no row.

**Sheet E0** (the operator; reads only, plus one disposable drill — `s40-e0.sh`
written by the agent, shipped to `/home/op`, sha256 printed): `free -m`; `docker
stats --no-stream --format '{{.Name}} {{.MemUsage}}'`; `sudo bin/backup.sh
--outputs /etc/agentic-postgres/projects/slot3-prod/outputs.json info --json`;
`sudo bin/doctor.sh --project slot3-prod` (the twelve checks — read the verb's
`--help` first); **the drill** — `sudo bin/restore-test.sh --target-time <E0's
time − 10 min> --project-dir /etc/agentic-postgres/projects/slot3-prod`, timed,
its exit and its evidence file's achieved point (D2452); `sudo ls -la
/etc/agentic-postgres/` (no `branches/` yet); `systemctl show -p NRestarts
agentic-postgres-reconciler`; `df -h /var/lib/docker`.

**The threat list made specific** (D1978): hosted items #1 (`:191-195`), #4's
branch half (`:209-214`) and #6 (`:219-222`) rewritten with the negative test each
owes BY NODE ID (§2), plus **one new item**: *a branch reaches its parent* — its
repository (BR-PLAN-001, BR-LIVE-002's
`test_the_branch_is_bounded_and_unreachable_from_the_repository`) or its
credentials (BR-REKEY-001, BR-LIVE-001's
`test_the_parents_password_opens_no_branch_door`). They stay list items until Run
8 moves them into the table as `THR-BR-ENUMERATION`, `THR-BR-EXHAUSTION`,
`THR-BR-RESTORE`, `THR-BR-PARENT` — **no `|` inside a cell** (the parser drops
the row silently). The residuals say: a branch shares its parent's
`system_identifier` and identity row (by design, ADR 0151); a branch is not
backed up; the parent's user password hashes are copied into the branch and
reachable by nothing a customer holds.

**ADRs** (each indexed in `docs/decisions/README.md`): **0271** branches — what a
branch is (its own compose project, three services, no secret, no unit), names
(`apg-<key>_<branch>`), the three phases, the re-key, hostnames under two
wildcards, one certificate per name pair, one per project, the charge, the
parent's guards, one class, not backed up, `restore.create` as an alias, no test
restore, no new key scope, the CLI's nouns (D2422–D2432, D2434, D2436–D2441,
D2449–D2451). **0272** a branch's expiry is a trigger — supersedes ADR 0186 for
branches only; the reconciler requests exactly one kind of operation (D2433).
**0273** the backups surface — a recorded reading with its age, the window
computed, stale is unknown (D2435). **Amended**: ADR 0151 (status line: the
`archive_mode` check now in code; a branch's persistent phase is not a drill,
D2447), ADR 0256 (`slot.sh redeploy`; the one operation the reconciler requests,
D2443, D2433), ADR 0186 (status: superseded for branches by 0272).

### Run 2 — names, the plan, the re-key, the record, the charge (`src/`)

**Code.** CI read by full SHA.

- **`src/agentic_postgres/naming.py`**: `BRANCH_NAME = re.compile(r"\A[a-z][a-z0-9]{1,11}\Z")`,
  `RESERVED_BRANCH_NAMES = frozenset({"main"})`, `BranchNames` (frozen dataclass:
  `stem`, `compose_project`, `volume`, `edge_network`, `internal_network`,
  `postgres_container`, `pool_container`, `direct_container`,
  `restore_container`, `recovery_container`, `pool_router`, `direct_router`),
  `branch_names(key, branch)` (every name through `compose_name` with its own
  context string), `branch_endpoint_hosts(domain, branch)`. Beside
  `restore_drill_names` (`:875-948`).
- **`src/agentic_postgres/branch_plan.py`** (new; `test_repository_contract`):
  `BranchPlan` (the three phases' mounts, environment, networks, argv),
  `build(parent_inspect, document, names, *, target_time | None)` reusing
  `restore_drill.inherited_mounts` / `inherited_environment` /
  `restore_arguments` (a `--type=default` sibling when no target), and
  `assert_branch_safe(plan)` (D2426). **`restore_drill.assert_disposable` gains
  the `archive_mode=off` check** (D2447).
- **`src/agentic_postgres/branch_rekey.py`** (new): `statements(key) ->
  tuple[str, ...]` (D2427: role names from `naming.database_roles(key)`, the two
  verifiers as psql variables), `psql_input(verifiers)` (stdin, `\set`, the
  `reconciler_dispatch.psql_input` shape, D2213).
- **`src/agentic_postgres/branch_record.py`** (new): `BRANCH_ROOT =
  Path("/etc/agentic-postgres/branches")`, `write(path, record)` (0600, atomic
  rename), `read(path) -> Record | None` (three outcomes: a record, absent,
  unreadable — ADR 0195), `STATES`.
- **`src/agentic_postgres/capacity_probe.py`**: `read` adds `branches` (D2431);
  `Reading.committed_line` names them. **Grep every reader first** (D979) and
  list them in the Done.
- **`backup_report.summarise`** gains `oldest_backup_start` (D2435).
- Tests: `test_branch_naming.py`, `test_branch_plan.py`, `test_branch_rekey.py`
  (pure), `test_capacity_probe.py` (+2), `test_restore_test_command.py` (+1),
  `test_backup_report.py` (+1). **Battery** (D269/D499/D386): the stem's `_` → `-`
  (the collision property must kill it), the persistent service given the backup
  network, `archive_mode` dropped from the recovery command, the re-key skipping
  `migration_user`, a branch charge 0, `oldest_backup_start` = the newest; each
  with a control the mutation cannot reach.

### Run 3 — `bin/branch-runtime.sh` and the branch's compose file

**Code.** CI read by full SHA.

- **`infra/branch/compose.yaml`**: `name: ${COMPOSE_PROJECT_NAME}`; `postgres`
  (`image: ${BRANCH_POSTGRES_IMAGE}` — the parent's image id; `user: "999:999"`;
  `command: postgres -c archive_mode=off -c archive_command=/bin/false` plus
  `small`'s `-c` settings; `mem_limit`/`pids_limit`/`cpus` from `small` (ADR
  0244's rule); `restart: "on-failure:5"`; volume external
  `${BRANCH_VOLUME_NAME}`; networks `internal` only; healthcheck `pg_isready`);
  `customer-pool` and `customer-direct` exactly as `compose.yaml:739-902` (copy,
  then a test holds the two definitions equal except names and networks), each on
  `edge` + `internal`, the userlists from
  `/etc/agentic-postgres/branches/<key>/<branch>/customer-poolers`, **TCP labels
  from `runtime_override._customer_tcp_labels` with the branch's router names and
  hosts** (rendered into an override file in the branch's state directory, the
  project's pattern); networks `edge` (name `${BRANCH_EDGE_NETWORK}`) and
  `internal` (`internal: true`). No `ports:`. No `backup` network. **Guards**:
  `test_compose_contract.py`-style assertions over this file (no publication, no
  backup network, archiving off, every service bounded).
- **`bin/branch-runtime.py`** + `.sh` (root; `test_cli_contract`; `chmod 755`):
  - `create --parent-outputs F --branch B --verifiers-stdin [--target-time T]
    [--expires-at T] --operation ID`: read the parent's document; refuse a parent
    whose `database.public.enabled` is false; DNS both names (D2428, exit 5);
    **the window check from its own reading** — the runtime has no control
    access, so it reads `backup.sh info --json` and the archiver query itself
    and refuses a `--target-time` outside `[oldest_backup_start,
    last_archived_time]` (exit 7, D2425); admission (exit 12); write
    `branch.json` (`state: creating`) FIRST so a crash leaves a record the
    reconciler reads as `undetermined`; restore (phase 1); recovery (phase 2, the
    drill's `wait_for_promotion`, 900 s); remove the recovery container;
    persistent `up -d --wait postgres`; **the re-key** (stdin verifiers);
    `customer-credentials`' userlist writer for the branch's directory (reuse
    `customer_credentials.py`'s functions with the branch's paths — no copy);
    `up -d --wait customer-pool customer-direct`; **edge attach** — `bin/edge-
    network.sh` gains `attach-network NETWORK` (root, the same alias; the
    project form unchanged; D979: grep its callers); `branch.json` `state:
    ready` with `reached_point`, `timeline`, `parent_commit`, hosts, charge.
    Exit codes: the drill's (0, 2, 3, 5, 6, 7) + 12.
  - `reset --branch B --verifiers-stdin [--target-time T]`: detach, `compose down`
    without `-v`, `docker volume rm` the branch's volume (derived), then create's
    phases from the restore on; the names and certificate kept.
  - `delete --parent-key K --branch B`: detach; `compose -p <branch project>
    down` **without `-v`** (the volume is external and removed by name, never by
    Compose); `docker volume rm` the one derived volume; then the state directory;
    every name from `branch_names` (D2438). Idempotent on an absent branch (exit 0,
    *"nothing of slot3-prod_dev exists"*).
  - `start --all` (D2439), `status [--json]` (every `branch.json`, the
    containers' state, three outcomes per branch).
- Tests: `test_branch_runtime.py` (recorder: the order — DNS, admission, record,
  restore, recover, persistent, re-key, userlists, poolers, attach; `delete`
  touches only derived names), **`test_branch_runtime_on_a_cluster.py`** (Docker:
  rig 40a's posix-repository cluster; create → the parent's password refused, the
  branch's accepted, a platform role refused; reset; delete leaves nothing;
  `docker rm -fv` cleanup). **Battery**: the re-key moved after the poolers (the
  order test must kill it), `delete` removing the parent's volume name (refused
  by the derivation check), the persistent service given the repository mount
  (`assert_branch_safe`), `start --all` skipping the attach.

### Run 4 — the control plane: `0006`, the routes, the codes

**Code.** CI read by full SHA. `bin/app-contract.sh --check` after the routes.

- **`projects/control/migrations/templates/0006-control-branches.sql`**:
  `app.control_branches` (D2450), `app.control_backup_readings` (D2435),
  `control_operations.origin` + its CHECKs (D2433), `control_request_operation`
  replaced: allow-list + `branch.create`, `branch.reset`, `branch.delete`,
  `restore.create`; **`AP409: branch_limit_reached`** for a second branch
  (D2430); `AP409: conflict` for `project.delete` with a recorded branch (D2438);
  delete-branch admin, the rest member; `control_list_branches`,
  `control_get_branch`, `control_get_backups` (DEFINER, viewer+, the project
  resolved first — D2451); `control_record_branches`, `control_record_backups`,
  `control_request_expiry` (INVOKER, **granted to nobody**);
  `control_result_members` gains the branch types (`branch`, `reached_point`,
  `target_time`, `timeline`, `pool_host`, `direct_host`); `AP900` down. Its header
  notes `0003:33`'s stale path (D2447). Freeze-lock; the proposal by `propose`.
- **`services/auth-api/app/operations.py`**: `EXECUTED_TYPES` + the four;
  `RESULT_MEMBERS` entries; `BRANCHES_PER_PROJECT = 1`; `MAX_EXPIRY_SECONDS = 7 *
  86400`. **`ACCEPTED_TYPES` stays empty until Run 8** (the routes answer `409
  not_available` naming `branches` / `restore_to_branch` until then; tests
  monkeypatch it, Session 38's pattern).
- **`schemas/operation-arguments.schema.json`**: `branch.create` / `restore.create`
  (`branch` name pattern, `app_verifier`, `admin_verifier` — the
  `credential.rotate` verifier pattern — `expires_at` optional RFC 3339 Z;
  `restore.create` requires `target_time`), `branch.reset` (`branch`, two
  verifiers, `target_time` optional), `branch.delete` (`branch`). Mirrored in
  `models.py`.
- **`errors.py:234`**: `branch_limit_reached` (ADR 0271).
- **Routes** (`control_routes.py`): `GET/POST /v1/projects/{key}/branches`, `GET/
  DELETE /v1/projects/{key}/branches/{branch}`, `POST
  /v1/projects/{key}/branches/{branch}/reset`, `POST /v1/projects/{key}/restores`,
  `GET /v1/projects/{key}/backups`; `control_roles.py`: `MATRIX`,
  `PROJECT_WRITES` (delete admin, D2436), `OPERATION_OF_ROUTE`, `KEY_SCOPES`
  (`projects:read` / `projects:write`). `bin/app-contract.sh` regenerates the
  control snapshot.
- Tests: `test_control_branches.py` (new), `test_backups_surface.py` (new),
  `test_operation_types.py` (types, schema branches, the error list),
  `test_control_projects.py` (delete refused with a branch). **Battery**: the limit
  counting only rows (not recorded branches), the enumeration body differing for a
  foreign project, `control_request_expiry` granted to the auth role, a stale
  reading served as a window.

### Run 5 — the reconciler: handlers, records, expiry, start; `slot.sh redeploy`

**Code.** CI read by full SHA.

- **`bin/reconciler.py`**: handlers `branch_create` (shared by `restore.create`),
  `branch_reset`, `branch_delete`; each: `slot_project` (D2438), the parent awake
  (`docker inspect`, D2219's reader), then `branch-runtime.sh` with argv from the
  typed arguments and the verifiers on stdin; result members from `branch.json`;
  `record_branches()` after each and every `RECORD_SECONDS`;
  **`record_backups()` every `BACKUP_RECORD_SECONDS = 900`** (`backup.sh info
  --json` + the archiver query, per `allocated` slot with a deployed document);
  **`request_expiries()`** every `RECORD_SECONDS`; **`start()` runs
  `branch-runtime.sh start --all`** after the control wait (D2439);
  `CHILD_SECONDS["branch-runtime.sh"]` = E0's drill time × 2, bounded by
  `OPERATION_SECONDS` (raised for the branch types only if D2452 says so).
- **`src/agentic_postgres/reconciler_dispatch.py`**: `STEPS` for the four types
  (`create`: `admit 10, restore 20, recover 60, rekey 80, doors 90, record 95`;
  the runtime prints `step <name>` lines the handler maps to progress),
  `COMMANDS` + `branch-runtime.sh`, the argv builders, the record/expiry SQL; the
  comment `:77-78` corrected (D2447).
- **`bin/slot.py redeploy`** (D2443) and its usage; `bin/slot.sh` dispatch.
- Tests: `test_reconciler_dispatch.py` (the four types; argv only; verifiers on
  stdin), `test_reconciler_claim.py` (+ expiry requests, a branch's records),
  `test_branch_expiry.py` (new; rig 40d's cases on `control_cluster.py`),
  `test_slot_command.py` (+3). **Battery**: the handler accepting a sleeping parent,
  the expiry request without `origin`, `redeploy` while the reconciler is active,
  `start()` not calling `start --all`.

### Run 6 — the customer CLI and the documents

**Code.** CI read by full SHA.

- **`bin/cloud.py`** family `branch` (`create --project-key K --branch B
  --password-dir D [--at T] [--expires-in HOURS] [--wait]`, `list`, `show`,
  `reset`, `delete [--wait]`) and `project backups`; passwords by
  `secrets.token_urlsafe(32)`, files `O_EXCL` 0600 under 0700 directories (D2417:
  every directory the CLI makes is chmod'ed, not only the leaf), verifiers by
  `agentic_postgres.scram`; **`bin/branch.sh`** (dispatch; `test_cli_contract`;
  `chmod 755`). `bin/endpoint.sh connect` gains `--branch B` (the branch's hosts
  from `GET …/branches/{b}`).
- **Documents**: `docs/managed-projects.md` *Branches* (create, the point, the
  window, reset, expiry, delete, *not backed up*, one per project) and *Backups*
  (the surface, the window, *a branch is the test*); `docs/operator-guide.md`
  **§22 Branches** (the wildcard records per slot, `branch-runtime.sh status`,
  what a reboot does, the charge on the committed line, removing a stuck branch
  by `branch-runtime.sh delete`) and §20 *A release move: `slot.sh redeploy`*;
  `docs/database-connections.md` a branch's names; `docs/control-plane.md` the
  routes.
- Tests: `test_control_cli.py` (+2), `test_cli_contract.py` (+1),
  `test_documentation_index`, `test_session12_documented_path`. **Battery**: the
  password file written 0644, `--at` sending `branch.create`.

### Run 7 — the trip's instruments, written and rehearsed offline

WSL `~/s40/run7/` (backed up to the scratchpad): **`s40-derive.py`** from
`~/s39/run8/s39-derive.py` (every count asserted): `s40-units.sh`, `s40-free.sh`,
`s40-probe-start.sh`/`-stop.sh`, `s40-launch.sh`, `s40-sweep.sh` (+
`--branch-record-file`), `s40-v1.sh` (**the whole host suite, `-k "not
after_reboot and not lifecycle and not branch"`**, D2448), `s40-x0.sh` (**the
whole external half, the same filter**), `s40-after-reboot.sh` (six units +
`slot3-prod_dev`'s three containers), `s40-external.sh` (the merge expecting 267
claims). **`s40-lifecycle.py`** from `~/s39/run8/s39-lifecycle.py` (`session: 40`,
`slot4-prod`, the slot's own route and pool name probed through each resize —
D2444). **`s40-branches.py`** (new, the probe owner's session, through `/v1`
only): read `project backups`; `branch create tmp` with the minimum expiry (15
minutes, D2433) and wait for the reconciler's expiry delete; the markers through `slot3-prod`'s direct name as
`customer_admin` (row 1, `T1`, row 2, waiting until the backups surface's
`latest` passes the second row's instant + 60 s); `branch create dev --at T1` →
row 1 only; Prisma `migrate deploy` over `dev.direct.…`; the parent's password
refused at both branch names; `branch create qa` → `branch_limit_reached`, no
row; `branch reset dev` (no target) → both rows; record `source_commit`; **stop
before the delete** (`--delete-only` later). **`s40-dns.sh`** (the slot's three
names and the two wildcards' probe names). **`s40-hostyaml.py`**, **`s40-e0.sh`**.
Rehearse every instrument against `rehearse_lifecycle.py`'s pattern (the real
control app, a fake reconciler that runs rig 40a's runtime against a posix
repository) — nothing touches the host. Commit only the `**Done.**`.

### Run 8 — the bump, the registry, the gate, the threat rows, the Ledger to `trial`, the documents

**Code.** `bin/session-01-check.sh` once and the new gate `--mode offline` once,
detached (CLAUDE.md §1), then CI.

- **The price** (D1624's rig): a worktree at `b0249ce` against this tree, `upgrade
  plan --also api_operation_added`; the paragraph beside `CURRENT_SESSION` says
  the class and the leaf count.
- `CURRENT_SESSION = 40`, Session 40's paragraph in `__init__.py`; `VERSION`
  1.18.0; `README.md:7`; every `--session 39` / `--through-session 39` literal on
  the documented path (D678/D1484), counted per file.
- The registry block (§2), `CLAIMS`, `OFFLINE_CLAIMS`, `CLAIM_INTRODUCED_IN`, the
  regex and the family comment.
- **`bin/session-40-check.sh`** derived from 39's by diff; one flag
  (`--branch-record-file`); `test_session_forty_gate_modes.py` derived from 39's;
  the roster's one variable.
- **The Ledger**: the six managed-project rows → `trial` (evidence
  `lifecycle_reearned_live`; `customer_text` *"… being verified"*);
  `pooled_endpoint`, `direct_endpoint` → `trial` (`endpoints_reearned_live`);
  `branches`, `restore_to_branch`, `backups_and_pitr` → `trial` (`branch_live`),
  their texts rewritten for ADR 0271–0273 (one per project, not backed up, the
  window computed); `postgresql` stays `planned` until the close;
  **`ACCEPTED_TYPES` = the eleven**; `docs/reality-ledger.md` rendered.
- `THR-BR-*` rows from Run 1's list.
- The live modules: `tests/external/test_session40_branches.py`,
  `tests/external/test_session40_reearning.py`,
  `tests/deployment/test_session40_branches.py` — **`--setup-plan` with every
  variable set: exit 0, no error** (D671); `RECORD_SESSIONS` and `record39`
  (D2442).

### Run 9 — sitting 1 (day 1): the release, `slot3-prod` moved by the verb, `slot4-prod` prepared, the dry run

The agent: bundle + `scp` + checkout on the host (`git rev-parse FETCH_HEAD`),
`uv sync` if `requirements-dev.txt` moved, renders; then the sheets in order,
**each read before the next**: **E0** (if not already run) → **P1** (consoles:
`slot3-prod`'s two wildcards, `slot4-prod`'s three records and providers) →
`s40-dns.sh` (`slot3` wildcards GO) → **R1** → reconciler stopped → **R2a/b/c**
(alpha, beta, control-prod) → **R2d** (`slot.sh redeploy --slot slot3-prod`, the
verb's first live run) → **A1** → **H1** (`slot4-prod` declared, both copies) →
**RC1** (the reconciler started; its journal names `slot4-prod` — D2411) →
**SL1** (one credential placement) → **SL2** → `s40-dns.sh slot4-prod` → **SL3**
(`slot4-prod ready`) → **K1** → **V1** (the whole host suite `-k`, writing
nothing) → **X0** (the whole external half `-k`, writing nothing, from WSL).
**Stop** if R1 prices `major` or for a reason this plan did not name, if R2d
does not leave `slot3-prod`'s doors and certificate as they were, or if V1 or
X0 fails for a reason other than the filtered live proofs' absence — **repair on
day 1, move the commit, redeploy, run V1/X0 again** (D2448).

### Run 10 — sitting 2 (day 2): the re-earning, the branches, the reboot, the sweep, the tag

1. **The lifecycle on `slot4-prod`** (`s40-lifecycle.py`, the probe on alpha,
   beta, control, `slot3-prod` and the slot): create `small` → claim →
   credentials → both names → rotate, old refused → sleep (both refused) → wake →
   resize `standard` → resize `large` (decided by the reading) → export (three
   schemas) → **K2** → delete → second create `409 capacity_exhausted {reason:
   no_slot}`, no row.
2. **The branches on `slot3-prod`** (`s40-branches.py`): the backups surface; the
   `tmp` branch expired and deleted by the reconciler (its operation's `origin`
   `expiry` read); the markers; `dev` at `T1` (row 1 only); migrate over its
   direct name; the parent's password refused; `qa` refused
   `branch_limit_reached`; `dev` reset (both rows) — `slot3-prod`'s doctor and
   `apg-diag containers` read before and after.
3. **A1'** (`agrees` ×4 + `slot4-prod agrees (deleted)`) → **B1** (the reboot; six
   units + the reconciler NRestarts 0 + `slot3-prod_dev`'s three containers back
   by the reconciler's `start --all`; psql through `dev.pool.…` before the sweep)
   → **S1** (the sweep, with `--branch-record-file`) → `s40-branches.py
   --delete-only` (`dev` deleted, its names refused) → external
   (`--branch-record-file`, `--lifecycle-record-file`) → merge (expected §7) →
   **tag `1.18.0`** from the workstation → **SL4** (`slot4-prod` revoked; its
   directory read gone).

### Run 11 — the close

**Code** — `bin/session-01-check.sh` once and CI.

- **The Ledger from the TAGGED evidence**: each `trial` row → `beta` if every
  named claim reads `passed` in `evidence/session-40.json`, else → `planned` with
  its types removed from `ACCEPTED_TYPES` and the Done saying why; `postgresql` →
  `beta` iff `endpoints_reearned_live` passed.
- **`capacity.ENVELOPE`**, a *Session 40* section: E0's drill on `slot3-prod` and
  the repository's size; each branch operation's time (create at a point, create
  at the end, reset, delete, the expiry's latency from `expires_at` to deleted);
  a branch's memory (rig 40c beside the host's reading); the branch's return after
  B1; `slot4-prod`'s lifecycle rows; **the resize and sleep windows as the slot's
  own route saw them** — the `UNMEASURED` row (`capacity.py:1793`) moved out if
  measured (D2444); memory with a branch live.
- `docs/scope-closure.md` **§33**; the stage plan's Status block; CLAUDE.md §2
  rewritten for Session 41's planner (copy it to the scratchpad first); this
  plan's `Status:` COMPLETE.

---

## 7. Evidence and claims

**Expected at the merge** (Run 10): **267 claims** (111 offline). **`failed` 1:
`documented_path`** (D1935). Everything else **passed** — including the four that
failed at Session 39: `lifecycle_operations_live`, `lifecycle_project_door_live`
and `lifecycle_retrial_live` read from `slot4-prod`'s Session 40 record (D2442),
and `public_endpoints_live` with its D2416/D2420 repairs, run in an external half
for the first time. **Exit 5 for `documented_path` and no other reason.**
Predictions, each moved only by the evidence.

**The three modes.** Offline: CI's artifact for the deployed SHA (111 claims).
Host: S1 with `--lifecycle-record-file`, `--slot-outputs` (`slot4-prod`, K2),
`--live-slot-outputs` (`slot3-prod`) and `--branch-record-file`. External: from
WSL, with `--control-outputs`, `--control-probe-file`, `--lifecycle-record-file`,
`--customer-credential-dir` and `--branch-record-file`; **the Session 40 customer
proofs reach only `routes.control`, the slots' recorded `routes.app` and the
public names on 5432, and open no SSH** (`test_this_module_uses_no_ssh` holds the
modules' text). **Deploy every project fully, THEN the dry run (V1, X0), THEN the
lifecycle and the branches, THEN sweep, THEN external — every half at one commit.**

---

## 8. Security invariants this session touches

| Invariant | How this session keeps it |
|---|---|
| **A branch starts re-keyed and cannot write its parent's repository** | The re-key before the poolers exist; no repository mount, no secret path, no backup network, archiving off and `/bin/false` in the persistent phase, asserted on the argv (BR-PLAN-001, BR-REKEY-001, BR-LIVE-002) |
| **A restore never overwrites the active volume** | The branch's own derived volume; `assert_branch_safe` refuses the parent's; the parent's volume, `instance_uuid` and timeline read unchanged (BR-LIVE-002) |
| **The public Postgres port admits only customer roles** | A branch's doors are customer-only poolers like a project's; every platform role `NOLOGIN` inside it (BR-REKEY-001, BR-LIVE-001) |
| **The control plane holds nothing that opens a project's data** | It holds a branch's verifiers, never its passwords; the passwords never leave the workstation (BR-CLI-001) |
| **The reconciler runs only a closed set of typed operations** | Four types, schema-validated twice; argv only; it requests exactly one kind of operation — an expired branch's deletion — through a function granted to nobody (BR-DISPATCH-001, BR-TTL-001) |
| **A capacity refusal and an entitlement refusal are different codes from different readers** | `capacity_exhausted` from the branch's admission; `branch_limit_reached` from the control database before a row (BR-CTL-001, BR-CAP-001) |
| **Projects share no project-scoped value** | Branch names from a stem a key cannot produce (BR-NAME-001); a branch's networks are its own |
| **A report may not substitute an answer for a failure to determine one** | The backups surface serves a stale or unknown reading as `could_not_determine`; a branch whose record cannot be read is `undetermined` (BR-BACKUP-001, D2450) |
| **Nothing `planned` has a control** | Promotion and in-place restore `not_offered`; classes `planned`; `trial` resolved at the close |
| **No URL, key, token or caller value in a log line** | No verifier or password printed by the CLI, the runtime or the reconciler; every new external fixture holding one returns `Secret` |

---

## 9. Stop conditions

Stop and ask the operator, without improvising, when:

- rig 40a contradicts the design: the persistent phase cannot start without the
  repository, the repository changes during a branch's life with the mounts
  absent, or the parent's password still connects after the re-key;
- rig 40b shows Traefik issuing a new certificate for a returning name pair AND
  the published duplicate limit is below a week's planned churn;
- a branch would need a secret of its own, a systemd unit, a published port, or a
  network path to the parent's repository after promotion;
- a branch would open a door before the re-key, or the re-key would need a
  customer password on the host or in the control database;
- `upgrade plan` prices 1.18.0 at `major`, or for a reason this plan did not name;
- R2d (`slot.sh redeploy`) leaves `slot3-prod`'s doors, certificate or registry
  row different from before;
- **V1 or X0 fails and the repair would move the commit after `slot4-prod` has
  been created** (D2448), or any commit move after its deletion;
- a branch's creation exceeds `OPERATION_SECONDS` on the host;
- the parent's doctor reads anything but twelve ok, or its volume, `instance_uuid`
  or timeline changes, at any point of a branch's life;
- a `trial` row would outlive the close, or a row would move to `beta` without its
  claims `passed`;
- a currently-passing test would be weakened to make a new one pass;
- `--render-only` stops working with no host and no root.

---

## 10. Open items this session carries and creates

**Carried, untouched, each still true:** the OVH upgrade — **owed before
Session 41** (D2342, D2445); M7's X1/X2 (Hetzner), allowed and not this plan's
(D2446); beta's three rotations (D1995); D1936/D2005; D1547; D2020/D2025; D2031;
D1642, D1798, D1869, D1871, D1722/D1806, D1784, D1792, ADR 0241's bound; D1045;
D1375; D976; D688; D771; D340; D466; D540; D942; D1203; D1205; D1211; the 24
unclaimed requirements; `process-max` 1 (D593) — **now a branch's creation time**;
`documented_path` (D1935); accounts never deleted (D2065, D1986); TOTP seeds
plaintext (ADR 0252); `/v1/sessions` unthrottled (D2166); the reconciler and the
operator serialised by a rule, not a lock (D2178); a slot's provider resources
outlive it (D2181); the export URL crosses the control database (ADR 0259);
`storage.enabled: false` still emits storage's router (D2144); a sleeping
project's doctor and backups unread (D2182 — the backups surface now says so);
`materialize-secrets` has no last-known-good fallback; `secret_required_added`
cannot fire (D2331); Postgres sees the gateway's address (D2325); no channel
binding (D2325); a plaintext peer holds a socket for the read deadline (D2326).

**Created, and named so Session 41 does not inherit them silently:**

- **A branch shares its parent's `system_identifier` and identity row** (ADR
  0151): any reader that tells clusters apart must use the timeline or the branch
  record, never those two.
- **A branch is not backed up** and lives on one disk; the Ledger says so.
- **The parent's user password hashes are copied into every branch**, reachable
  by no customer grant and read by no service there.
- **Branch certificates accumulate in the edge's `acme.json`** for names whose
  branch is gone; nothing prunes them.
- **One branch per project is a constant**, not a plan: Session 41's entitlements
  own `branches_total`.
- **The reconciler now records backups every 900 s** — R2 requests per slot per
  day the envelope should price when slots multiply.

---

## Appendix — what to consult, how a run is executed here, and the sheets

**Consult, in this order:** CLAUDE.md §1 (the shell traps); this plan's §0, §1
and the run's own text; the reads its run names. **The tree wins.**

**How a run is executed here**: CLAUDE.md §5. Every `sudo` line is the
operator's, on a sheet, under `script -q -e -c '…' /home/op/s40-<sheet>.txt` when
it execs into a container or deploys (D972, D1501), never piped or redirected;
`sudo -v` in the foreground first (D1376). Every `op` line is the agent's over
SSH; remote loops in a script file with `PATH="$HOME/.local/bin:$PATH"` exported.
**`<sha>` is never typed on a sheet**: the agent fills it from `git rev-parse
HEAD` on the host before handing the sheet. **Before any sheet that deploys,
retires, restores or recreates the edge: `sudo systemctl stop
agentic-postgres-reconciler`, and `start` after** (D2178); **after any edit to
`host.yaml` or any checkout move: restart it** (D2411, D2179). **Read `--help` of
every command on a sheet before handing it** and correct the line to it.

### Sheet E0 — readings before anything is built (Run 1; reads, and one disposable drill)

```
sudo -v
sudo bash /home/op/s40-e0.sh      # tees /home/op/s40-e0.txt; the drill removes what it made
```

### Sheet P1 — the consoles (any day before Run 9's SL1)

1. **Cloudflare DNS**, **DNS only**, no AAAA, → `15.204.231.45`:
   `A *.pool.slot3.agenticpostgresql.com`, `A *.direct.slot3.agenticpostgresql.com`
   (D2428); `A slot4.agenticpostgresql.com`, `A pool.slot4.agenticpostgresql.com`,
   `A direct.slot4.agenticpostgresql.com`.
2. **Cloudflare R2**: buckets `apg-slot4-prod`, `apg-slot4-prod-backup`, in
   alpha's location; two Account API tokens, *Object Read & Write*, one per
   bucket. **Never paste them into the conversation.** (If you ask the agent to
   create the buckets through the API, as for slot1–3, say so; tokens stay yours.)
3. **Backblaze B2**: `apg-slot4-prod-backup-mirror`, an application key scoped to
   it.
4. Tell the agent 1–3 are done and the mirror bucket's name.

### Sheet R1 — the release priced (Run 9, day 1)

```
sudo bin/upgrade.sh plan --project alpha-dev    --candidate .generated/alpha-dev/outputs.json    --also api_operation_added --json
sudo bin/upgrade.sh plan --project beta-dev     --candidate .generated/beta-dev/outputs.json     --also api_operation_added --json
sudo bin/upgrade.sh plan --project control-prod --candidate .generated/control-prod/outputs.json --also api_operation_added --json
```

### Sheets R2a / R2b / R2c — 1.18.0 deployed (Run 9, day 1)

```
sudo systemctl stop agentic-postgres-reconciler
script -q -e -c 'sudo ./deploy.sh --host host.yaml --project project.alpha.yaml   --capabilities capabilities.yaml --through-session 40' /home/op/s40-r2-alpha.txt
script -q -e -c 'sudo ./deploy.sh --host host.yaml --project project.beta.yaml    --capabilities capabilities.yaml --through-session 40' /home/op/s40-r2-beta.txt
script -q -e -c 'sudo ./deploy.sh --host host.yaml --project /home/op/control.yaml --capabilities capabilities.yaml --through-session 40' /home/op/s40-r2-control.txt
```

### Sheet R2d — `slot3-prod` moved by the product's verb (Run 9, day 1)

```
script -q -e -c 'sudo bin/slot.sh redeploy --host host.yaml --slot slot3-prod --confirm slot3-prod' /home/op/s40-r2-slot3.txt
```

### Sheet A1 — the registry after the last deploy (Run 9, day 1)

```
sudo bin/control.sh adopt --project alpha-dev    --organization 10234b92-b2d7-4573-bebb-f012ce5c8f02 --confirm control-prod
sudo bin/control.sh adopt --project beta-dev     --organization 10234b92-b2d7-4573-bebb-f012ce5c8f02 --confirm control-prod
sudo bin/control.sh adopt --project control-prod --organization 10234b92-b2d7-4573-bebb-f012ce5c8f02 --confirm control-prod
sudo bin/control.sh registry      # agrees x4 (slot3-prod adopted by R2d), slot1/slot2 agrees (deleted); exit 0
```

### Sheet H1 — `slot4-prod` declared (Run 9, day 1)

```
sudo install -o op -g op -m 0600 /etc/agentic-postgres/host.yaml /home/op/etc-host.yaml
#   the agent runs s40-hostyaml.py on both copies (slots.declared += slot4-prod) and prints the diffs; read them, then:
sudo install -o root -g root -m 0600 /home/op/etc-host.yaml.slots /etc/agentic-postgres/host.yaml
```

### Sheet RC1 — the reconciler back, reading the new declaration (Run 9, day 1)

```
sudo systemctl start agentic-postgres-reconciler
sudo bin/reconciler.sh status       # idle; the journal's slot line names slot4-prod (D2411)
```

### Sheet SL1 — `slot4-prod`'s providers (Run 9, day 1)

```
sudo bin/slot.sh prepare --host host.yaml --slot slot4-prod
sudo bin/bootstrap-providers.sh --host host.yaml --project /etc/agentic-postgres/slots/slot4-prod/manifest.yaml --plan
#   YOU: place the control-plane credential (two lines: client id, client secret):
sudo install -d -m 0700 /root/.config/agentic-postgres/bootstrap
sudo nano /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo chmod 0600 /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo bin/bootstrap-providers.sh --host host.yaml --project /etc/agentic-postgres/slots/slot4-prod/manifest.yaml --apply \
     --operator-credential-file /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo shred -u /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo ls -la /root/.config/agentic-postgres/bootstrap/      # empty, no nano .save copy (D2061)
#   YOU: in Infisical, project `slot4-prod`, environment `dev`: the storage pair at /storage
#   (create the folder), the backup pair at /backup, the mirror pair at /backup.
```

### Sheet SL2 — materialized (Run 9, day 1)

```
sudo bin/materialize-secrets.sh --project /etc/agentic-postgres/slots/slot4-prod/manifest.yaml --requirements secrets.required.yaml --session 40
```

### Sheet SL3 — the slot read (Run 9, day 1)

```
#   the agent has run s40-dns.sh slot4-prod (three records, exit 0) and slot3-prod's wildcards (GO)
sudo bin/slot.sh status --host host.yaml         # slot4-prod ready; slot3-prod allocated; slot1/2 consumed
sudo bin/control.sh registry                     # ... slot4-prod prepared (slot) or ready; exit 0
```

### Sheet K1 — the kit and the copies (Run 9, day 1)

```
sudo bin/dr-kit.sh export --host host.yaml --capabilities capabilities.yaml \
     --project project.alpha.yaml --project project.beta.yaml --project /home/op/control.yaml \
     --output /home/op/kit-<today>-s40
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/alpha-dev/outputs.json    /home/op/alpha-dev-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/beta-dev/outputs.json     /home/op/beta-dev-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/control-prod/outputs.json /home/op/control-prod-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/slot3-prod/outputs.json   /home/op/slot3-prod-outputs.json
```

### Sheet V1 — the whole host suite, writing nothing (Run 9, day 1; ~55 min)

```
sudo bash /home/op/s40-v1.sh       # -k "not after_reboot and not lifecycle and not branch" (D2448)
```

**X0** (the agent, from WSL): `s40-x0.sh` — the whole external half with the same
filter, writing nothing.

### Sheet K2 — `slot4-prod`'s document, before its deletion (Run 10, day 2)

```
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/slot4-prod/outputs.json /home/op/slot4-prod-outputs.json
```

### Sheet A1' — the registry after the lifecycle and the branches (Run 10, day 2)

```
sudo bin/control.sh registry                     # agrees x4, slot1/2/4 agrees (deleted); exit 0
sudo bin/branch-runtime.sh status                # slot3-prod_dev ready
```

### Sheet B1 — the reboot (Run 10, day 2)

```
sudo systemctl reboot
```

### Sheet S1 — the one sweep (Run 10, day 2)

```
sudo -v
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/alpha-dev/outputs.json    /home/op/alpha-dev-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/beta-dev/outputs.json     /home/op/beta-dev-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/control-prod/outputs.json /home/op/control-prod-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/slot3-prod/outputs.json   /home/op/slot3-prod-outputs.json
sudo bash /home/op/s40-launch.sh      # refuses while the reconciler is working; detaches s40-sweep.sh
```

### Sheet SL4 — `slot4-prod`'s identity revoked (Run 10, day 2, after the tag)

```
#   YOU: place the control-plane credential as on SL1, then:
sudo bin/slot.sh revoke --host host.yaml --slot slot4-prod --operator-credential-file /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential --confirm slot4-prod
sudo shred -u /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo ls -la /root/.config/agentic-postgres/bootstrap/      # empty
sudo ls -la /etc/agentic-postgres/projects/                # no slot4-prod directory (D2405's repair, live)
```
