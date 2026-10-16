# Session 41 — The repairs, the third re-earning, plans, usage, notifications and idle sleep

**Status: EXECUTING — Runs 1–5 DONE 2026-10-16 (Runs 4 and 5 pushed together).**
Rows **D2510–D2535** at planning; the runs add theirs after them (Run 1:
D2536–D2539; Run 2: D2540–D2541; Run 3: D2542; Run 4: D2543–D2544; Run 5:
D2545). ADRs **0274–0276** written. **NEXT FREE: D2546, ADR 0277.**

The sixth session of Stage 5 — **and the first one the operator split**
(D2510): the stage plan's *Session 41* brief (`docs/plans/stage-5-plan.md`
§5 *Session 41*) was telemetry, insights, usage and plans; on 2026-10-16 the
operator moved **ClickStack, `pg_stat_statements`, Query Insights and
monitoring** to a new Session 42 (with the OVH upgrade as its first sitting,
D2511) and the console, the journey and the Stage 5 release to Session 43. So
Session 41 is: **the two product repairs Session 40 shipped** (D2501, D2504),
the proof and instrument defects beside them, **the re-earning a third time on
a NEW `slot5-prod`**, and the control-plane half of the brief — **plans and
entitlements, usage, in-app notifications and idle sleep** — all of it re-earned
at ONE commit on the host.

Twelve runs and **two sittings on two days**: the release on the four projects
(`slot3-prod` moved by `slot.sh redeploy`), `slot5-prod` prepared, and the whole
trip verified writing nothing (day 1); then, from the workstation with no SSH,
**the probe organisation's second project refused `plan_limit_reached` while a
slot is ready**, `slot5-prod` created in a NEW organisation and taken through
its whole lifecycle — including **an idle sleep the reconciler requested by
itself** — its usage and notifications read, **its organisation's second
project refused `capacity_exhausted` after the deletion**; the branches on
`slot3-prod` with the backups surface reading a window; the reboot **with the
branch coming back by itself**; the sweep, external, merge, tag (day 2).

**Brief:** `docs/plans/stage-5-plan.md` §5 *Session 41* (`:752-792`) **as
amended by D2510** — of its *Builds*, this session takes plans and entitlements
(D1967, D1954's entitlement half), usage (D1966), notifications (D1968), the
`THR-*` rows for plan-limit bypass and usage tampering, and idle sleep (D1956's
trigger half, deferred here by D2147); **not** ClickStack (D1964),
`pg_stat_statements` / Query Insights (D1965) or monitoring. Its *Must not*
applies whole: *"Enforce a limit nothing can enforce. Add a checkout, an invoice
or a card field. Let one store answer a question the other already answers. Put
a caller value, a key, a URL … in a series, a log line or an insight."*
`docs/scope-closure.md` **§33** (`:1531-1589`, *"What Session 41 inherits, in
order"* `:1578-1588`); Session 40's plan §10 (*"Created …"*, both lists,
`docs/plans/session-40-implementation-plan.md:1551-1581`) and its rows
**D2492–D2509** (`:468-485`). ADRs **0186** (expiry is never a trigger,
`:74-83`), **0195**, **0246** (`:72-73`: sleep *"triggered by its owner or by
idleness"*), **0256**, **0259** (sleep), **0261** (trial), **0271**, **0272**
(the reconciler's one requested kind, `:67-89`, `:108-109`), **0273** (the
backups surface). `docs/threat-model.md` hosted items **#4** (`:212-218`, the
entitlement half), **#5** (`:219-222`), **#10** (`:247-255`). `docs/reality-ledger.yaml`
rows `projects_self_service` … `sleep` (`:193-380`), `idle_sleep` (`:382-397`),
`branches` (`:494-525`), `restore_to_branch` (`:527-548`), `usage` (`:623-638`),
`plan_free` (`:655-668`), `plan_premium` (`:670-683`), `notifications`
(`:685-696`), `backups_and_pitr` (`:880-907`). **And the operator's four
answers of 2026-10-16** (§1 D2510, D2511, D2519, D2525).

**Shape:** twelve runs. **Run 1** is documentation — three rigs, one host
reading sheet (E0, which also captures `slot3-prod`'s real backup readings and
times its idle signals), the threat list made specific, three ADRs, the stage
plan amended for the split — and reads **no** CI verdict. **Runs 2–7** change
code: each pushes and reads that commit's own CI verdict by full SHA (`gh api
"repos/Virabyan99/agentic-postgres/actions/runs?head_sha=<40 chars>" --jq
'.workflow_runs[] | [.name, .status, .conclusion] | @tsv'` from Git Bash, judged
on HTTP status, three buckets — success / failure / not registered; an empty
list is not a verdict, D1057). **Run 8** writes the trip's instruments and
rehearses them offline, committing nothing but its `**Done.**`. **Run 9** is the
bump. **Runs 10–11** are the sittings. **Run 12** is the close (Ledger rows and
envelope rows are code: it gates once and reads CI). **Push only after the
previous commit's CI lands** — `ci.yml` cancels in-progress runs on `main`.

**Product version at close:** `CURRENT_SESSION` **41**; `template_version`
**`1.19.0`** — predicted *minor* (**no** project-manifest, outputs or host
schema change, no new secret, no released migration; the control set's eighth
migration; new `/v1` routes; eleven operation types accepted again) and **read
from `upgrade plan` on the host with `--also api_operation_added`, never
chosen** (`bin/upgrade.py --also` accepts it, `:241-247`; `compatibility.py:89-105`).
The released migration count stays **39**; the control set goes **7 → 8**. **No
new published port, no new service in any compose file, no new root command;
three new customer commands (`bin/plan.sh`, `bin/usage.sh`,
`bin/notifications.sh`) and one new `project` verb (`idle-sleep`).** A `major`
is §9's stop.

**Written for whoever picks this up cold, and it will be a different model than
the one that planned it.** Every path below was read from the tree on 2026-10-16
at `e89ac85` — four explore passes over `bin/`, `src/agentic_postgres/`,
`services/auth-api/`, `projects/control/`, `infra/`, `compose.yaml`, `tests/`,
`docs/` and the Stage 5 plans, plus direct reads of
`services/auth-api/app/control_service.py:636-670`,
`projects/control/migrations/templates/0004-control-operations.sql:454-470`,
`tests/contract/test_control_projects.py:393-398`, `docs/threat-model.md:205-250`
and `services/edge-probe/probe.py:1-40` — **and the readings taken at planning**
(§0). Every path is cited `path:line`. **Read CLAUDE.md §1 in the launch folder
before the first command, then this plan's §1, then the appendix.** If a step
here and the tree disagree, **the tree wins and the disagreement is a divergence
row** (next free `D` after §1's table), never a silent reconciliation. **When
this plan names a line number, open the file at that line and read the
surrounding twenty lines before editing** — the numbers were right on
2026-10-16 and `ruff format` moves them.

**The ten sentences the executor most needs, in case nothing else is read:**

1. **The repairs come first and each is proved against the producer's REAL
   output** (D2512, D2513). D2501: `backup_report.backup_state` — what `bin/backup.sh
   info --json` prints — gains `oldest_backup_stop` and `repository_bytes`, and
   a proof feeds `reconciler_dispatch.backups_reading` the output of the
   producer's own functions over **`slot3-prod`'s real `pgbackrest info`**
   (captured by Sheet E0), never a hand-shaped dict. D2504: a branch's database
   image is **resolved every time the branch starts**, from the parent's tag
   and the content digest recorded at creation — never pinned as an id.
2. **The third re-earning is at ONE commit on a NEW slot, `slot5-prod`**
   (D2518). Day 1 ends with the whole host suite and the whole external half
   run with `-k`, writing nothing, before `slot5-prod` exists as a project
   (D2448). A commit move after `slot5-prod`'s deletion is §9's stop.
3. **Free is one project per organisation, every profile, one branch per
   project** (the operator, 2026-10-16, D2519). Enforced at the control plane
   **before an operation row exists**, by the service AND by
   `app.control_request_operation` under a lock on the organisation's row
   (D2521). Premium is defined and unavailable; *Notify me* records interest.
   **`storage_gb` and `agent_calls_per_day` are read, never enforced** — the
   control plane holds no path to a project's agents (D2520).
4. **`plan_limit_reached` and `capacity_exhausted` come from different readers
   in a fixed order** (D1954, D2521): the entitlement first, then the slot
   reading. On the trip: the probe organisation (which holds `slot3-prod`) asks
   for a second project **while `slot5-prod` is `ready`** → `plan_limit_reached`,
   capacity green; the lifecycle's NEW organisation asks for a second project
   **after `slot5-prod` is deleted** → `capacity_exhausted {reason: no_slot}`,
   entitlement green. No override verb is built.
5. **Usage is a sample the reconciler records every 300 s** (D2523), read
   through the same container reads `doctor usage` makes, into the control
   project's `app.control_usage_samples` by a function granted to nobody. Each
   figure is the reading or `NULL` with the reason — never a zero standing in
   for *not read* (ADR 0195).
6. **Idle sleep is opt-in, default never, 15 / 30 / 60 minutes** (the operator,
   2026-10-16, D2525). The control database decides from the recorded samples
   (no HTTP request answered below 400 and no customer-role activity across the
   whole window, every sample present); the reconciler only asks
   (`app.control_request_idle_sleep`, granted to nobody) and the row it inserts
   is `project.sleep` with **`origin = 'idle'`**, attributed to the member who
   set the setting. A missing or unreadable sample means *not idle*. Wake stays
   by request (`wake_on_connect` is `planned`).
7. **Notifications are in-app only** (D1968, D2526): a row written **inside
   `control_finish_operation`'s own transaction** from a fixed template — never
   a result member, a URL or a caller value — plus *limit approaching* rows from
   the sampler. Listed per organisation. No email.
8. **One control migration, `0008`**, carries every table and function this
   session adds (Run 4); its lock is frozen and its proposal written by the
   product's own `bin/migrate.sh` (ADR 0243).
9. **Sixteen Ledger rows move to `trial` in the bump** (Run 9): the six
   managed-project rows, `branches`, `restore_to_branch`, `backups_and_pitr`,
   `idle_sleep`, `usage`, `notifications`, `plan_free`, `plan_premium` — each
   naming only claims this session introduces (ADR 0261) — and
   `ACCEPTED_TYPES` becomes the eleven again. `query_insights` and
   `monitoring` move to target 42, `console` to 43.
10. **Every sheet is a sheet** (D2494, D2530): Sheet RA (the admission
    rehearsal) after the last deploy, Sheet M1 (the host's memory with a branch
    live, D2509), Sheet PV (`apg-diag` reinstalled) — each has a heading and its
    command lines in the appendix, not a sentence in a row.

---

## 0. Where the session starts

```
HEAD            e89ac85 on main, local = origin ("docs(session-40): Run 11 done
                -- Session 40 closed"), tree clean. Code: 7c2078d (CI
                38878437973 success). Deployed AND TAGGED: 8cc3440 (1.18.0, tag
                object 122e573) on all four projects. main is past the tag with
                the close's code (the Ledger, ACCEPTED_TYPES {credential.rotate},
                the envelope) -- NOT deployed: the host's 1.18.0 still accepts
                the eleven types (no slot is free, so a create is no_slot).
VERSION         1.18.0. CURRENT_SESSION 40 (src/agentic_postgres/__init__.py:1145;
                Session 40's paragraph :1091-1144). README.md:7 "Session 40
                implemented"; README.md:708,710 carry --session 40 /
                --through-session 40. Outputs schema 22 (deployed_output.py:40,
                output_migrations.CURRENT_VERSION :104). Project manifest 1-11
                (config.py:64). host.yaml 2|3|4. 39 released migrations. The
                control set 7 (projects/control/migrations/released.lock.json
                schema 3; manifest.json schema 1; 0007 control_operation_origin);
                five committed proposals (projects/control/proposals/14699bf6…,
                d82e2831…, f0dabad8…, 8f898750…, a7b18e5f…).
REGISTRY        360 requirements (tests/acceptance-registry.yaml ends :7446;
                Session 40's block from :7169). ID regex
                tests/contract/test_acceptance_registry.py:123 (ends
                ...|OPN|LIFE|EP|BR)-...); family comments :50-122 (BR :121-122).
                267 claims (src/agentic_postgres/evidence_claims.py CLAIMS
                :482-1375, Session 40's block :853-876); 111 offline
                (OFFLINE_CLAIMS :106-435, Session 40's :410-434).
                CLAIM_INTRODUCED_IN tests/contract/test_evidence_claims.py:953-1310
                (Session 40's :1257-1272). 273 ADRs (docs/decisions/README.md
                last row :339, 0273). NEXT FREE: D2510, ADR 0274.
EVIDENCE        evidence/session-40.json (WSL, gitignored): 267 claims, 263
                passed, 4 failed -- documented_path (D1935);
                lifecycle_reearned_live (D2500); branch_live (D2501, D2506);
                branch_host_live (D2504, D2505).
LEDGER          projects_self_service, project_deletion, export, region,
                compute_profiles, sleep: planned, target 41. idle_sleep: planned,
                target 41. branches, restore_to_branch, backups_and_pitr:
                planned, target 41. usage, plan_free, plan_premium,
                notifications, query_insights, monitoring: planned, target 41.
                console: planned, target 42. pooled_endpoint, direct_endpoint,
                postgresql: beta. ACCEPTED_TYPES = {credential.rotate}
                (services/auth-api/app/operations.py:110).
HOST            15.204.231.45, OVH VPS US-East, apg-ovh-01: 4 vCPU Haswell,
                7,745 MiB, no swap, Ubuntu 26.04, Docker 29.9.0. Read at
                planning (2026-10-16 09:47Z, apg-diag + op): ~op/agentic-postgres
                = 8cc3440, clean; 42 containers healthy (alpha-dev, beta-dev,
                control-prod x10; slot3-prod x12); listeners 22, 80, 443, 5432
                (+ the resolver's loopback 53); free -m available 5,109 MiB;
                / 72 G, 11 G used; up 11 h 51 min (B1's reboot); edge,
                reconciler and the four project units active, NRestarts 0;
                /etc/agentic-postgres/branches exists and is EMPTY (dev deleted
                after the sweep). slot1-, slot2-, slot4-prod CONSUMED and
                revoked: NO SLOT IS FREE.
ORGANISATIONS   The probe account probe-owner-s37 (~/s37/probe.json) owns
                organisation 31121d7b-1aa3-4206-8f13-d81157c1beaf, which holds
                slot3-prod (the kept customer project). Sessions 38-40's
                lifecycles created their slots in THAT organisation (WSL
                ~/s40/lifecycle.json organization_id = 31121d7b…). The operator's
                projects alpha-dev, beta-dev, control-prod are adopted under
                10234b92-b2d7-4573-bebb-f012ce5c8f02.
OPERATOR        2026-10-16: split (telemetry to a new 42, console/release to
                43); the OVH upgrade before ClickStack's trip (42's first
                sitting); Free = 1 project, every profile, 1 branch; idle sleep
                opt-in, default never (D2510, D2511, D2519, D2525).
```

**What exists, measured at `e89ac85`, and the session builds on:**

- **The backups surface and its defect** (ADR 0273, D2501). `bin/reconciler.py`
  `backups_of` (`:1309-1334`): `_quiet(dispatch.running_argv(container), 60)`
  (`:1314`); a stopped container → `backups_reading(..., sleeping=True)`
  (`:1316`); else `_quiet([bin/backup.sh, --outputs, outputs, info, --json], 300)`
  (`:1318-1320`), `info = json.loads(done.stdout)` **only on return code 0**
  (`:1321-1324` — `bin/backup.py:471` exits `EXIT_REFUSED` when the status is
  `failing`, so a failing repository is folded into *unknown*); the archiver
  through `container_exec.run(... backup_report.ARCHIVER_QUERY ...)`
  (`:1326-1331`); `backups_reading(...)` (`:1332`).
  `src/agentic_postgres/reconciler_dispatch.py` `backups_reading` (`:612-647`):
  the repository from `info.get("status")` / `info.get("last_full_backup_at")`
  (`:626-629`, both present in the printed block); **`earliest =
  backup_report.earliest_point((info or {}).get("oldest_backup_stop"))`
  (`:634`) — a key the printed block never has**; `latest` from the archiver
  (`:635`). `src/agentic_postgres/backup_report.py`: `earliest_point` (`:73-86`,
  stop + 1 s, D2465), `summarise` (`:89-171`; returns `oldest_backup_stop`
  `:153` and `repository_bytes`), **`backup_state` (`:342-380`) returns only
  `status, stanza_created, last_full_backup_label, last_full_backup_at,
  latest_recoverable_time, wal_archived_count, wal_failed_count, mirror`**.
  `bin/backup.py` `verb_info` (`:451-497`): `summary = read_repository(...)`
  (`:461`, which calls `summarise` `:335`), `state = backup_state(summary,
  archiver)` (`:463`), printed (`:470`). `bin/branch-runtime.py` `read_window`
  (`:234-270`) runs `pgbackrest --output=json info` itself and reads
  `summarise(...)["oldest_backup_stop"]` (`:255`, `:261`) — the reader that is
  right. **No test calls `backups_reading` or `backups_of`**; the two that fed the
  surface (`tests/contract/test_backups_surface.py:25-38` `_reading()`;
  `tests/contract/test_control_branches.py:353-375`) hand already-shaped
  readings to `control_service.backups_document` and to
  `app.control_record_backups`. Fixtures `tests/fixtures/pgbackrest/`
  (`info-full-and-incr.json`, `info-two-fulls.json`, `info-no-backups.json`,
  `info-missing-stanza.json`) are real RAW `pgbackrest info` captures; **no
  `backup.sh info --json` sample exists in `tests/`.** Readers of
  `backup_state` (D979): `bin/backup.py:463,599`, every `bin/session-NN-check.sh`
  (e.g. `session-40-check.sh:1362`), `tests/contract/test_wal_archiving_signal.py:275-330`,
  `test_backup_mirror.py:541,1233`, `test_backup_repository_report.py:278-596`,
  `test_backup_plane.py:1074,1096,1126`. The route: `GET
  /v1/projects/{key}/backups` (`services/auth-api/app/control_routes.py:1102-1122`)
  → `control_service.backups` (`:796-807`) → `backups_document` (`:942-997`;
  `earliest is None` → `could_not_determine` *"the window's bounds were not
  read"* `:977-981`). The table `app.control_backup_readings`
  (`projects/control/migrations/templates/0006-control-branches.sql:93-110`),
  writer `app.control_record_backups` (`:403-442`, key whitelist `:416-419`).
  `BACKUP_RECORD_SECONDS = 900` (`bin/reconciler.py:125`;
  `services/auth-api/app/operations.py:102`; `control_service.py:119`
  `BACKUP_READING_MAX_AGE = 2 ×`).
- **A branch's image and its start** (ADR 0271, D2497, D2504).
  `src/agentic_postgres/branch_plan.py` `build` (`:145-240`): `image =
  str(inspect.get("Image"))` (`:171`) for all three phases (`:198`, `:208`,
  `:217`); `compose_environment` (`:243-291`) writes **`BRANCH_POSTGRES_IMAGE:
  plan.image` (`:264`)** and `BRANCH_PGBOUNCER_IMAGE` (`:265`).
  `restore_drill.runnable_image(inspect, docker)` (`restore_drill.py:161-221`):
  own id if it resolves (`:183-184`), else the tag's (`Config.Image`) current
  index id **iff its platform manifest digest equals the container's
  `ImageManifestDescriptor.digest`** (`:185-221`), else `DrillError`. Callers:
  `bin/branch-runtime.py:177` (`runnable()` `:172-179`, used by create `:712`
  and reset `:776`), `bin/restore-test.py:846`. `bin/branch-runtime.py`:
  `write_compose_state` (`:453-466`, `branch.env` 0600); `command_create`
  (`:704-741`: `creating` `:722` → `_build_life` `:689-701` → `ready` `:739`,
  `failed` on exception `:737`); `command_reset` (`:759-804`; from `ready`,
  `stopped` or `failed` `:770`); **`command_start` (`:857-910`)** — for each
  `ready`/`stopped` record, `docker compose -p … --env-file branch.env -f
  COMPOSE_FILE -f compose.override.yaml up -d --wait` (`:873-879`,
  `COMPOSE_SECONDS = 300`), then `attach`; on failure `state: "stopped"`
  (`:885-894`) and `did not come back: {error}` on stdout (`:895`); **never
  re-reads the image**; exit `EXIT_UNKNOWN` if any failed (`:910`);
  `command_status` (`:913-945`). Bounds `:96-99`: `QUICK_SECONDS 60`,
  `COMPOSE_SECONDS 300`, `RESTORE_SECONDS 7200`, `PROMOTION_SECONDS 900`.
  `infra/branch/compose.yaml`: `postgres.image: ${BRANCH_POSTGRES_IMAGE:?required}`
  (`:25`), the poolers `${BRANCH_PGBOUNCER_IMAGE:?required}` (`:77`, `:149`), the
  persistent command `-c archive_mode=off -c archive_command=/bin/false`
  (`:41-56`, `:45-48`). Branch states `("creating","ready","stopped","failed","deleting")`
  (`src/agentic_postgres/branch_record.py:59`, `:53-58`); the root
  `/etc/agentic-postgres/branches/<key>/<branch>/` (`branch_record.py:48`).
- **The reconciler's silent child** (D2504). `_quiet` (`bin/reconciler.py:1299-1306`):
  `capture_output=True`, `None` on `OSError`/`TimeoutExpired`, **the output
  never logged**; used at `:1314`, `:1318`, **`:1422`**. `start()`
  (`:1386-1409`) → `start_branches` (`:1412-1428`): `_quiet(dispatch.branch_start_argv(REPO_ROOT),
  900)`; logs only *"branches started"* or *"a branch did not come back; its
  record says stopped (D2439)"*. Compare `Operation.child` (`:383-426`), which
  appends the child's output to a 0600 step log. `branch_start_argv`
  (`reconciler_dispatch.py:556-558`).
- **`apg-diag` cannot see a branch** (D2504). `bin/apg-diag.sh` `verb_containers`
  (`:196-218`) iterates `/etc/agentic-postgres/projects/*/` (`PROJECT_ROOT`
  `:55`), `compose_project_for` (`:153-163`) reads each `outputs.json`'s
  `database.container` and its compose label; branch stems `apg-<key>_<branch>`
  (`naming.py:1036-1083`) are never enumerated; `SERVICES` (`:70`) lacks
  `customer-pool` / `customer-direct`. Installed as `/usr/local/bin/apg-diag`
  (`infra/host/apg-agent.sudoers:5,72`).
- **The reconciler's loop and bounds.** `bin/reconciler.py`: `POLL_SECONDS 5`
  (`:120`), `RECORD_SECONDS 120` (`:121`), `BACKUP_RECORD_SECONDS 900` (`:125`),
  `CONTROL_WAIT_SECONDS 180` (`:132`), **`OPERATION_SECONDS = 30 * 60` (`:137`)**,
  **`CHILD_SECONDS` (`:138-154`; `branch-runtime.sh` 1200, `backup.sh` 1200,
  `deploy.sh` 900)**, `DATABASE_SECONDS 120` (`:155`); `database_call`
  (`:256-272`: `psql -U postgres` inside the control database container,
  variables on stdin through `dispatch.psql_input`); `Reconciler` (`:1049`):
  `finish` `:1103`, `record_slots` `:1121-1138`, `record_branches` `:1140-1154`,
  `request_expiries` `:1156-1172`, `record_backups` `:1174-1192` (loops
  `host_config.declared_slots`, `_deployed(key)`), `recover` `:1194`, `cycle`
  `:1232-1245`, `handle` `:1247-1291`; `HANDLERS` (`:1029-1041`, eleven,
  `restore.create` → `branch_create`); `run()` (`:1431-1454`; every
  `RECORD_SECONDS` slots + branches + expiries `:1445-1449`, every
  `BACKUP_RECORD_SECONDS` backups `:1450-1452`). SQL strings
  `reconciler_dispatch.py:184-235` (`RECORD_BACKUPS_SQL` `:204`,
  `REQUEST_EXPIRY_SQL` `:205`). Sleep/wake handlers `reconciler.py:697-736`;
  `slot_project` (`:657-669`), `require_running` (`:672-686`); STEPS
  `project.sleep` (`reconciler_dispatch.py:96`), `project.wake` (`:98`).
  Guard `tests/contract/test_restore_promotion_bound.py:101-114`
  (`test_a_branch_promotion_bound_sits_inside_its_reconciler_budget`, AST-reads
  `PROMOTION_SECONDS` < `CHILD_SECONDS["branch-runtime.sh"]`; `DRILL_PROOFS`
  `:40-44`).
- **The control plane.** `services/auth-api/app/operations.py`:
  `OPERATION_TYPES` (`:54-66`), `EXECUTED_TYPES` (`:71-85`, eleven),
  **`BRANCHES_PER_PROJECT: Final = 1` (`:91`; comment `:87-90` *"A constant, not
  a plan: Session 41's entitlements own `branches_total`"*)**, expiry bounds
  (`:96-97`), `ACCEPTED_TYPES` (`:110`), `RESULT_MEMBERS` (`:128-146`). The one
  code reader of the constant: `control_service._branch_write` (`:821-849`,
  `:844`). **`0006-control-branches.sql:271-283` hard-codes the branch rule in
  SQL** (`AP409: branch_limit_reached` at `:275` and `:281`). `errors.py`:
  control words `:213-235`, `OPERATION_ERROR_CODES` (`:241-249`, five; D2469
  keeps the 409 words out), `CONTROL_STATUS` (`:251-267`), `ControlRefused`
  (`:270`). `control_service.create_project` (`:636-670`): role → **the slot
  reading BEFORE the row** (`:654-663`, `no_slot` / stale) → `_request(...,
  "project.create", ...)` (`:670`). `require_accepted` (`:620-634`).
  `control_routes.py` (`APIRouter(prefix="/v1")` `:69`; routes listed by the
  explore pass — projects `:665-1125`, `POST /organizations` `:438`).
  `control_roles.py`: `MATRIX` (`:48-103`; `"create_organization": ACCOUNT`
  `:60`), `PROJECT_WRITES` (`:110-126`), `OPERATION_OF_ROUTE` (`:129-141`),
  `KEY_VOCABULARY` (`:146-152`, five scopes), `KEY_SCOPES` (`:176-200`).
  **The guard that forbids the code this session writes**:
  `tests/contract/test_control_projects.py:393-398`
  `test_no_string_produces_plan_limit_reached` (*"D2160: no entitlement code
  exists in Session 38"*; registered under `LIFE-CAP-001`,
  `tests/acceptance-registry.yaml:6650-6659`). `docs/control-plane.md:211`
  *"No code in 1.16.0 produces `plan_limit_reached`."*
- **The control set.** `projects/control/migrations/templates/`: `0001`
  identity (`app.control_role` `:40`, accounts/organizations/memberships/
  invitations/totp `:63-109`, `control_enter`, `control_require_role` `:237`),
  `0002` keys, `0003` registry (`control_projects` `:17`, `control_operations`
  `:29`), `0004` operations (`control_slots` `:110`, `control_request_operation`
  `:150`, `control_ready_slot_count` `:269`, `control_claim_operation` `:405`,
  **`control_finish_operation` `:454-493`** (INVOKER, `REVOKE` `:649`),
  `control_record_slots` `:513`), `0005` endpoints, `0006` branches
  (`origin` `:45`, `control_branches` `:54`, `control_backup_readings` `:93`,
  `control_request_operation` replaced `:217`, `control_record_branches` `:350`,
  `control_record_backups` `:403`, `control_request_expiry` `:446`), `0007`
  origin on the operation reads. **How one is added** (ADR 0243): a template
  and a `manifest.json` entry → `bin/migrate.sh --project
  project.control.example.yaml freeze-lock` (the only writer of a lock,
  `bin/migrate.sh:114`) → `bin/migrate.sh --project project.control.example.yaml
  propose --by NAME` (writes `projects/control/proposals/<set_digest>.json`,
  refuses while a dev environment exists, `:75-81`); `up` refuses a pending
  version with no committed proposal (exit 5, `:57-62`).
- **Usage today.** `bin/doctor.py` `probe_usage` (`:1081-1128`): `database_bytes`
  (`pg_database_size`), `audit_rows`, `idempotency_rows`, `pgdata_kb`,
  `wal_kb` (`du -sk`), `repository_bytes`, `requests_total` and
  `tool_calls_total` from the project's own Prometheus through `probe_store`
  (`:965-1023`: `wget -q -Y off -O - http://127.0.0.1:9090/api/v1/query?query=…`
  inside `apg-<key>-store-1`, `:985-993`; `sum(traefik_service_requests_total)`,
  `sum(agent_tool_calls_total)` `:944-947`; refuses a series naming another
  project `:1015-1018`); `diagnosis.usage_report` (`diagnosis.py:960-1001`).
  **`agent_tool_calls_total` is per `mcp` process** (D1609, D1643): an instant
  query reads nothing once the process that served the calls is gone. The
  edge's counter carries the project's routers only (`rendering.py:1443-1452`
  keep-regex, `const_labels: project` `:1489-1490`). `services/edge-probe/probe.py`
  is a passive HTTPS target (`:1-40`); a container healthcheck runs inside the
  container and never crosses the edge.
- **The agent quota** (`migrations/templates/0028-agent-windowed-quota.sql`):
  `app_private.agents.quota_calls` / `quota_window_seconds` (`:61-70`, NULL =
  unbounded, window 1..86,400 s), `app_private.agent_quota` (`:101`), enforced
  in `api.agent_audit_begin` (`:135-187`); **no route, CLI or code sets it** —
  only test SQL (`tests/deployment/test_session16_agent_governance.py:386`).
- **The customer CLI.** `bin/cloud.py` families (`parser()` `:1273-1470`):
  `login`, `logout`, `context`, `org` (`:437-547`), `project`
  (`list|use|show|create|claim|status|sleep|wake|delete|export|backups`,
  `:549-800`, parser `:1352-1394`), `compute`, `operation`, `endpoint`,
  `branch` (`:1056-1266`). `bin/apg.sh` holds no verb list: `apg X` →
  `bin/X.sh` (`:269`). Shims modelled on `bin/endpoint.sh` (usage block,
  `python_bin`, a verb whitelist, `exec … bin/cloud.py endpoint "$@"`, `:92-96`).
  `tests/contract/test_cli_contract.py`: `SHELL_COMMANDS` `:42-268` (customer
  shims `:81-113`; `session-40-check.sh` `:250`), `PYTHON_COMMANDS` `:270-351`,
  `COMMANDS_WITH_VERBS` `:535-584`, the backup/restore precedent test
  `:1308-1336`.
- **The re-earning's proofs and what pins them.**
  `tests/external/test_session38_public_lifecycle.py`: **`RECORD_SESSIONS =
  frozenset({38, 39, 40})` (`:82`)**; the `record` fixture (`:160-178`) asserts
  `session in RECORD_SESSIONS` (`:167`), finished, `source_commit ==
  control["source_commit"]` (`:173`). `tests/external/test_session39_public_lifecycle.py`
  **`record39` asserts `record["session"] in (39, 40)` (`:76`)**.
  `tests/external/test_session40_reearning.py` **`record40` asserts `session ==
  40` (`:78`) and `project_key == "slot4-prod"` (`:79`)**; the probe proof
  (`:189-206`). `tests/external/test_session40_branches.py`: the `branches`
  fixture (`:68-89`) asserts `(session, kind) == (40, "branches")` (`:76`),
  `PARENT = "slot3-prod"` (`:61`); the refusal window `started_at..live_at`
  (`:198-221`, `:213`). `tests/deployment/test_session40_branch_host.py`: the
  `record` fixture asserts `(40, "branches")` (`:102`); **`SHOW archive_command
  == "/bin/false"` (`:155-156`)**. The drill proofs
  (`tests/recovery/test_future_pitr.py`, `test_session32_workflow_restore.py`,
  `test_session34_delivery_restore.py`) never check the image first (D2498).
- **The trip's instruments** (WSL, outside the repo): `~/s40/run7/s40-lifecycle.py`
  (967 lines; slot taken from the create's result `:573-574`, **`session: 40`
  hard-coded `:88`**, flags `:914-939`, **the D2500 fix in place `:333-342`**),
  `s40-branches.py` (664; `--project-key slot3-prod` default `:613`; phases
  `--after-reboot|--delete-only|--continue-live|--reset-after-reboot`;
  workarounds for D2501 `:284-287,:370-374`, D2502 `:291-312`, D2503
  `:402-415`, D2504 `:563-584`), `s40-derive.py` (494; derives
  `s40-units/-free/-probe-start/-probe-stop/-launch/-sweep/-v1/-after-reboot/
  -external/-x0/-dns` from `~/s39/run8`; `slot4-prod` literals at `:102,
  :134, :197, :222, :238, :319`), `s40-hostyaml.py`, `s40-dns.sh`. Trip
  scripts `~/s40/run9`, `~/s40/run10`, `~/s40/run11`.
- **The gate to derive from.** `bin/session-40-check.sh` (2,074 lines; header
  `:2-94`, `readonly SESSION=40` `:103`, defaults `:121-177`, `usage()`
  `:179-815`, `parse_arguments()` `:851-1086`, `mode_offline` `:1530-1747`,
  `mode_host` `:1749-1967`, `mode_external` `:1969-2063`).
  `tests/contract/test_session_forty_gate_modes.py` (1,103 lines; `SESSION = 40`
  `:58`, `SESSION_PREVIOUS_NUMBER = 39` `:73`, claims table `:85-104`). Roster
  `tests/conftest.py:86-225` (Session 40's `:217-224`).
- **Capacity.** `capacity_reading.decide` (`safe_available = memory −
  reserve_memory_mb − committed`, `capacity_reading.py:449-450`; branches in
  `committed` since Session 40, `:173-182`); `capacity_probe.read` adds every
  `branch.json` (`capacity_probe.py:354-364`). `capacity.ENVELOPE`'s Session 40
  section (`capacity.py:1782-1954`); `UNMEASURED` (`:1964-`): the pooled-name
  windows (`:1965-1977`, D2500) and the host's memory with a branch live
  (`:1978-1986`, **cited there as D2431; the row that recorded it is D2509**).
  `RESIZE_WINDOW_SECONDS = 84` (`services/auth-api/app/compute_profiles.py:104`).

**Measured at planning** (2026-10-16; no rig was run — every third-party fact
this plan needs is Run 1's, §5):

| # | Reading | Result |
|---|---|---|
| p1 | `apg-diag containers` | 42 containers healthy, four projects; no branch container (and none could be listed, D2504) |
| p2 | `apg-diag listeners` | 22, 80, 443, 5432 (+ loopback 53) |
| p3 | op: checkout, `free -m`, `df -h /`, units, `ls /etc/agentic-postgres` | `8cc3440` clean; available 5,109 MiB; 11 G of 72 G; six units active NRestarts 0; up 11 h 51 min; `branches/` empty |
| p4 | `~/s37/probe.json`, `~/s40/lifecycle.json`, `~/s40/branches.json` (WSL; keys only) | the probe owns `31121d7b…`, which holds `slot3-prod`; Session 40's lifecycle created `slot4-prod` in it |

---

## 1. The divergence table

Six columns. Each row is a **measured fact about the tree at `e89ac85`** (or the
host as the planning readings left it) set against what the brief says, with
the decision this plan takes. **Next free number after this table is D2536.**
Rows the runs add go in a second table below it, in execution order.

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D2510** | Stage plan §3/§5: *"41 — Telemetry, insights, usage and plans … ClickStack bounded; `pg_stat_statements` and Query Insights; curated monitoring; usage sampling; Free/Premium … notifications"*; scope closure §33 adds the two repairs and a third re-earning in front of it. | Session 41's inheritance alone (two product repairs, three proof/instrument defects, a re-earning on a new slot with the lifecycle, the branches, the sweep and the external half at one commit) is Session 40's trip again; the brief adds a new platform stack (ClickHouse, HyperDX, an OTel gateway), a database restart on every project (`shared_preload_libraries`) and five control-plane features. Sessions 39 and 40 each lost their live claims to defects found after the slot was consumed (D2415, D2500-D2506). | **The operator, 2026-10-16: split.** Session 41 = the repairs + the re-earning + plans/entitlements + usage + notifications + idle sleep (all control-plane and reconciler work). **A new Session 42** = ClickStack, `pg_stat_statements`, Query Insights, monitoring, the `THR-*` rows for observability poisoning and ClickStack exhaustion, **with the OVH upgrade as its first sitting** (D2511). **Session 43** = the console, the journey and the Stage 5 release (the old §5 *Session 42*). Stage 5 becomes sessions 36–43. **Run 1 amends `docs/plans/stage-5-plan.md`**: the Status block, §3's table (one row split in two, one renumbered), §5 *Session 41* (an *Amended 2026-10-16 (D2510)* paragraph naming what moved), §5 *Session 42* retitled *Session 43* with its forced ordering *"41 before 42"* restated as *"41 and 42 before 43"*, §7's claims table, and `docs/threat-model.md` item 9 (*Session 42*). Run 9 moves `query_insights` and `monitoring` to target 42 and `console` to 43. | The control-plane half rides the lifecycle the re-earning already runs (a plan refusal beside `no_slot`, `branches_total`, an idle sleep is a `project.sleep`); the telemetry half needs a bigger host and touches every database. One release that does both would put a third re-earning on the largest change yet. | — |
| **D2511** | D2342/D2445: *"The OVH upgrade … owed before Session 41."* | Measured at planning (p3): 5,109 MiB available with four projects; Session 40 read 4,428 MiB *safe* at admission (`capacity.py:1836-1837`). Session 41's peak: `slot5-prod` at `large` (840) + `slot3-prod` (192) + one branch (192) — what Session 40 ran. Nothing this session adds runs a new container. | **The operator, 2026-10-16: the upgrade happens before ClickStack's trip** — Session 42's first sitting, not 41's. This plan's sheets never name it. Sheet M1 reads `free -m` and `doctor capacity` with a branch live (D2509), which is also the baseline 42's upgrade is compared against. | ClickStack is the first thing that does not fit; nothing in 41 changes the node's footprint. | — |
| **D2512** | Scope closure §33 item 1: *"the reconciler reads the window through `backup_report`'s summary, with a proof over `backup.sh info --json`'s real output"* (D2501). | `backups_of` hands `backups_reading` the PRINTED block of `backup.sh info --json` = `backup_state(summary, archiver)` (`backup.py:463,470`), which drops `oldest_backup_stop` (`backup_report.py:342-380`); `backups_reading` reads it (`reconciler_dispatch.py:634`) → `earliest` always `None` → `could_not_determine` (`control_service.py:977-981`). Also: `info --json` exits `EXIT_REFUSED` on `failing` (`backup.py:471`) and `backups_of` parses stdout only on 0 (`reconciler.py:1321-1324`) — a failing repository reads *unknown* instead of *problem* (a second fold, never reached on the trip). No test calls `backups_reading`; the two surface tests hand it the shape it wanted (CLAUDE.md §7 question 6). | **The producer prints what its reader reads**: `backup_state` gains **`oldest_backup_stop`** and **`repository_bytes`** (both from the summary it already holds; usage reads the second, D2523) — additive to a printed block every reader indexes by key (the readers above, D979, re-run). `backups_of` parses stdout on exit 0 **and** `EXIT_REFUSED`, and passes `info=None` only when the output does not parse. **Proof over the producer's real output**: a new `tests/contract/test_backups_reading_from_the_producer.py` runs `summarise(<slot3-prod's real raw info, captured by Sheet E0>)` → `backup_state(...)` → `json.dumps`/`json.loads` (what crosses the pipe) → `backups_reading(...)` and asserts `earliest == oldest stop + 1 s` read from the raw file; **a class guard** (D600): every key `backups_reading` reads from `info` is a key `backup_state` returns (read by AST from the two functions, so a future reader of a dropped key fails here, not on the host). The fixture is committed as `tests/fixtures/pgbackrest/info-slot3-prod-2026-10.json` after Run 2 reads it whole for anything secret (pgBackRest's info carries no cipher pass; recorded). | The repair is where the shape is made, so the next reader of the printed block reads the same keys; the proof cannot share the reader's belief because its input is the producer's output over a real capture. | **0273** amended |
| **D2513** | Scope closure §33: *"the image is resolved when a branch STARTS (`runnable_image`), never pinned as an id"* (D2504). | `branch.env` pins the id `runnable_image` resolved at create (`branch_plan.py:264`); the boot's rebuild of the parent's image moves the tag to a new index and orphans the old one (D2497); `start --all` hands compose an id that no longer resolves and compose tries to PULL it (`branch-runtime.py:873-879`). At boot the parent's container may not be running yet when the reconciler starts branches (both start from units; the order is not fixed). | **`branch.json` records the parent's image TAG** (`Config.Image` of the parent container at create/reset) **and the platform manifest digest** of what the branch was made with (the container's `ImageManifestDescriptor.digest`, as `runnable_image` reads it). **Every start** (`start`, `start --all`, and the persistent phase of `create`/`reset`) resolves the image afresh through a new `restore_drill.image_for(tag, digest, docker)` — the tag's current index id **iff its `--platform` manifest digest equals the recorded digest**; else **refused with a reason** (*"the parent's image changed since this branch was made; reset the branch"*) and the record `stopped` with that reason; an unreadable reading says so (ADR 0195) — then rewrites `branch.env`'s `BRANCH_POSTGRES_IMAGE` with the resolved id before `compose up`. **No longer needs the parent running** (a tag and a digest, not a container). The pooler image is a pulled image by digest (`compose.yaml:743,826`) and keeps resolving; it is recorded as it is. `runnable_image` (the drill's) is unchanged. **Rig 41c** (rig 40f's shape) proves: a branch created, the parent's image rebuilt with unchanged content, the old id orphaned → `start` resolves the new index and the branch runs; **control**: a rebuild with changed content → refused with the reason, nothing started. | A value resolved once goes stale (scope closure §33's sentence); the content digest is the identity that survives a rebuild, the tag is the name that follows it. | **0271** amended |
| **D2514** | D2504: *"the reconciler discards the child's output … and `apg-diag` cannot see a branch's containers"* — an ADR 0195 gap. | `_quiet` (`reconciler.py:1299-1306`) captures and drops; `start_branches` (`:1412-1428`) logs one fixed sentence; `branch.json` has no reason field; `app.control_branches` (`0006:54`) has none; `apg-diag containers` iterates `projects/*/` only (`apg-diag.sh:196-218`). | **The child's output is kept**: `start_branches` runs `branch-runtime.sh start --all` through the same 0600 step-log path `Operation.child` uses (`:383-426`; a log under the reconciler's log directory named `branch-start-<utc>.log`) and logs **the child's last line** — branch-runtime prints no secret (its outputs are names, states and Docker's error text; Run 3 reads every `print` in `bin/branch-runtime.py` to confirm, D2416's rule). `_quiet` stays only for the two reads whose output IS the reading (`:1314`, `:1318`). **`branch.json` gains `reason`** (the last failure's one-line text, cleared on `ready`), recorded by `control_record_branches` into a new `app.control_branches.reason` (0008) and served by `GET …/branches/{b}`. **`apg-diag containers` lists branches**: for each `/etc/agentic-postgres/branches/*/*/branch.json`, a section `-- <key>_<branch> (branch)` listing `label=com.docker.compose.project=<stem>`, the stem read from the record and checked against `^apg-[a-z0-9-]+_[a-z][a-z0-9]{1,11}$` before use; `SERVICES` gains the two customer poolers for the `containers` view only (the `logs` allowlist is unchanged, D380). **Sheet PV** reinstalls `apg-diag` — Run 3 reads which command installs it (`grep -n apg-diag bin/provision-host.sh infra/host/`) and the sheet runs exactly that step. | *"Did not come back"* without the reason is a report that substituted a sentence for a reading. | **0271** amended, 0195 |
| **D2515** | D2503: *"`ready` includes the door, or the door's readiness is said beside it."* | `ready` is written right after `attach` (`branch-runtime.py:739`, `:802`, `:898-908`); nothing reads the edge's certificate; the branch's names answered 4.5 s after `ready` on the trip because the certificate was issued AFTER it. | **`ready` waits for the door**: after `attach`, `branch-runtime` opens a TLS session to the edge on `127.0.0.1:5432` for each branch host — PostgreSQL's `SSLRequest` (8 bytes, expect `S`), then TLS with SNI = the host and ALPN `postgresql`, **verifying the certificate against the system trust store and the host name** — every 5 s for up to **`DOOR_SECONDS = 180`**. Both verified → `ready`, `door: "ready"`. Not within the bound → `ready` with **`door: "pending"`** and the reason (the customer reads it; the route says *"the door's certificate is not issued yet"*). An error the check cannot classify → `door: "unknown"`. `app.control_branches.door` (0008). **Rig 41b** (rig 40b's Pebble shape) measures the handshake from Python against Traefik's Postgres STARTTLS with Pebble's CA: before issuance the default certificate fails verification; after, it verifies; **control**: a name with no router → never verifies. | The state a customer acts on should be the one they can reach; where it cannot be, the third answer is said. | **0271** amended |
| **D2516** | D2495: *"a fresh incremental before a branch, US buckets, or a larger budget — priced for 41."* | `CHILD_SECONDS["branch-runtime.sh"] = 1200` inside `OPERATION_SECONDS = 1800` (`reconciler.py:137-154`); measured: a branch at a point 1,100.0 s, a reset 1,091.0 s (Session 40 Run 10); the drill's promotion bound is 3,600 s (D2492), the branch's 900 s. | **A larger budget for the three branch types only**: `OPERATION_SECONDS_BY_TYPE = {branch.create, restore.create, branch.reset: 3,600}` (every other type keeps 1,800), `CHILD_SECONDS["branch-runtime.sh"] = 3,300`, `branch-runtime.py` `PROMOTION_SECONDS = 2,400`; **grep every reader of `OPERATION_SECONDS` first** (D979) and of the CLI's `--wait` bound in `bin/cloud.py` (Run 3 records both); the guard `test_a_branch_promotion_bound_sits_inside_its_reconciler_budget` gains the outer bound (child < the type's operation bound). **Not taken**: a forced incremental (costs a full R2 round trip on every branch and touches the parent's repository — the one thing a branch must not do) and bucket moves (a provider act). | The budget is the one knob that changes nothing about the parent; the measured margin was 100 s. | **0271** amended |
| **D2517** | Scope closure §33: *"the three proof and instrument defects (D2500, D2505, D2506)"*; D2498: *"a drill proof that asserts its container's image id resolves BEFORE the drill … priced."* | D2505: `test_session40_branch_host.py:155-156` expects `SHOW archive_command` = `/bin/false`; PostgreSQL prints `(disabled)` when archiving is off. D2506: `test_session40_branches.py:213` takes its window from a resumed record's `started_at`. D2500: fixed in `~/s40/run7/s40-lifecycle.py:333-342` (a timed-out sample is a failed sample). D2498: the three drill proofs never check the image. | **D2505**: the host proof reads the branch's **configured** command — `docker inspect` `Args` of the branch's postgres container — and asserts it equals `branch_plan.persistent_command()`'s `archive_mode=off` / `archive_command=/bin/false`, beside `SHOW archive_mode` = `off`; `SHOW archive_command` is asserted to be **`(disabled)`** (the value PostgreSQL prints, D2505 measured) — an expected value read from the thing it describes, made stricter, not weaker. **D2506**: the branch record gains **`window_started_at`** — the first attempt's start, which a resume or a `--continue-live` never moves — and the proof reads its window from it (falling back to `started_at` for a record without it). Both repairs land in the Session 40 modules (they re-run on the Session 41 records, D2518) and in the new Session 41 modules. **D2500**: the Session 41 lifecycle instrument is derived from the repaired one; Run 8's rehearsal kills a pool sample on purpose and reads the thread alive after it. **D2498**: the three drill proofs call `restore_drill.runnable_image` on the live container before the drill and fail with *"the drill's image does not resolve: …"* when it refuses — a refusal reads as the image, not as a failed drill. | Each is a proof made to read the thing it judges; none moves a threshold. | — |
| **D2518** | Scope closure §33 item 2: *"a NEW slot (`slot5-prod`), the nine rows back to `trial` at the bump, the lifecycle, the branches, the sweep and the external half at ONE commit"*. | ADR 0261 (`reality_ledger.py:165-194`): a `trial` row's evidence names only claims introduced in `CURRENT_SESSION`. `RECORD_SESSIONS = {38, 39, 40}` (`test_session38_public_lifecycle.py:82`); `record39` accepts `(39, 40)` (`test_session39_public_lifecycle.py:76`); **`record40` asserts `session == 40` and `project_key == "slot4-prod"` (`test_session40_reearning.py:78-79`)**; the two branch modules assert `(40, "branches")` (`test_session40_branches.py:76`, `test_session40_branch_host.py:102`). | **Session 41 introduces its own live claims** (§2): `lifecycle_third_trial_live` (LIFE-LIVE-005), `branch_retrial_live` (BR-LIVE-003), `branch_host_retrial_live` (BR-LIVE-004), plus the new features' (`plans_live`, `usage_live`, `notifications_live`, `idle_sleep_live`), in new modules `tests/external/test_session41_reearning.py`, `tests/external/test_session41_branches.py`, `tests/deployment/test_session41_branch_host.py`. **The older fixtures widen to read Session 41's records** (the D2442 pattern; each still asserts every member it asserted): `RECORD_SESSIONS` → `{38, 39, 40, 41}`; `record39` → `(39, 40, 41)`; `record40` → `session in (40, 41)` and **`project_key` a slot key that is not `slot3-prod`** (`slot.SLOT_KEY`, the kept project excluded — never a bare string); the branch fixtures → `session in (40, 41)`. So Sessions 38–40's lifecycle, endpoint and branch claims re-run on 41's records and must pass too — but no `trial` row cites them. **The new slot is `slot5-prod`, domain `slot5.agenticpostgresql.com`** (`SLOT_KEY` `slot.py:69` admits it). | The same rule as Session 40, a third time; widening a fixture to a later record of the same shape is not weakening it. | 0261 |
| **D2519** | D1967: *"Plans are a release file (`src/agentic_postgres/plans.py`: `free` active, `premium` `unavailable_during_beta`), every number derived from the new host's readings … Enforced: `projects_active`, `branches_total`, `compute_profiles` … `agent_calls_per_day` … Read but not enforced: `storage_gb` … `backup_retention_days` … a planned Premium difference."* | Nothing (0 hits for `projects_active`, `plans.py`). Compute profiles live in `services/auth-api/app/compute_profiles.py` and are re-exported by `src/agentic_postgres/compute_profiles.py:22-32` — the control plane's image carries only `services/auth-api/`. `BRANCHES_PER_PROJECT = 1` (`operations.py:91`) and its SQL twin (`0006:271-283`). | **The operator, 2026-10-16: Free = `projects_active` 1 per organisation, `branches_total` 1 per project, `compute_profiles` small/standard/large (all three).** **`services/auth-api/app/plans.py`** (the table, like `compute_profiles.py`) re-exported by **`src/agentic_postgres/plans.py`**: `PLANS = {"free": Plan(status="active", ...), "premium": Plan(status="unavailable_during_beta", ...)}`, each entitlement an `Entitlement(value, enforced: bool, reader: str)`. **Free**: `projects_active` 1 (enforced: control plane), `branches_total` 1 (enforced: control plane), `compute_profiles` (small, standard, large) (enforced: control plane — all allowed), `storage_gb` 5 (read, not enforced: no per-project disk quota exists, D1955), `agent_calls_per_day` 10,000 (read, not enforced, D2520), `backup_retention` *"two weekly full backups and the WAL between them"* (text: `repo1-retention-full` 2, `config.py:408`). **Premium** (defined, unavailable): `projects_active` 3, `branches_total` 3, the three profiles, `storage_gb` 20, `agent_calls_per_day` 100,000, retention *planned*. **`projects_active` counts the organisation's projects not deleted — a sleeping project holds its slot and counts**; adopted operator projects count like any other (the operator's organisation is never a creator). **ADR 0274 names every number and its reason**: 1 / 1 because slots are prepared by hand and each project charges 192–840 MiB of a node with ~4.4 GiB safe; 5 GB and 10,000 because they sit at ~10× what a beta project used on this host (Sheet E0 reads `slot3-prod`'s database bytes and its agent rows) and are shown only as context. `branches_total` replaces the constant: `BRANCHES_PER_PROJECT` is deleted and `_branch_write` reads the plan (grep every reader first — one, `control_service.py:844`). | An entitlement nothing enforces is said to be read; the enforced three each sit on a reader that already exists (the registry's projects, the branch count, the profile names). | **0274** |
| **D2520** | D1967: *"`agent_calls_per_day` (as the existing windowed quota written onto each agent the control plane creates)"*. | **The control plane creates no agent**: a project's agents are created by its own admin through the project's auth service (`app_private.agents`); `0028`'s quota is set by no route, CLI or code (only test SQL). The stage plan's own §8 row: *"The control plane holds nothing that opens a project's data or admin plane"* (ADR 0246). | **Read, not enforced, in Session 41** — and said so in `plans.py` (`enforced=False, reader="usage"`), on `/v1/plans`, in `apg plan` and in the `plan_free` row: *"agent calls per day: shown against your usage; not enforced during the beta."* Usage reads a project's agent calls from its audit rows (D2523) so the figure exists; the 80% notification fires as information. **No path from the control plane to a project's `app_private.agents` is built.** | Writing a quota onto a project's agents would hand the control plane a write into the admin plane it describes — the stage's sibling failure mode (stage plan §9). | **0274**, 0246 |
| **D2521** | D1954: *"The control plane checks the entitlement first and refuses with `plan_limit_reached` (or `branch_limit_reached`) before an operation row exists … Neither code may be produced by the other's reader (a test reads both paths with the other held green)."* Stage plan *Ends*: *"a second project refused by the Free plan's `projects_active` … and — with the limit raised for the test — a creation refused by capacity"*. Threat #4: *"a limit enforced under concurrency"*. | `create_project` reads the slot first (`control_service.py:654-663`); `control_request_operation` (`0006:217`) serialises one non-terminal operation per `project_key` — **a `project.create` has no key yet**, so two creates in one organisation are not serialised. `test_no_string_produces_plan_limit_reached` (`test_control_projects.py:393-398`) forbids the word anywhere under `services/`, `src/`, `bin/`. Measured at planning (p4): **the probe organisation already holds `slot3-prod`**. | **Two readers, one order, two codes.** (1) `create_project` checks **the entitlement first** (`repository.plan_check(org, "project.create")` → `409 plan_limit_reached {entitlement: "projects_active", limit: 1, plan: "free"}`, *"this organization's plan allows 1 project; delete one first (Free plan, beta)"*), **then** the slot reading (`capacity_exhausted`, unchanged). (2) **The authoritative check is in SQL**: 0008's `app.control_request_operation` takes `SELECT … FROM app.control_organizations WHERE id = … FOR UPDATE` before counting, for `project.create` (projects not deleted + non-terminal `project.create` rows of the organisation) and for `branch.create`/`restore.create` (the existing rule, its number now read from `app.control_plan_limits`), raising `AP409: plan_limit_reached` / `AP409: branch_limit_reached`; the service maps both. **`branch_limit_reached` keeps its word** (D1954's *"or"*; the 1.18.0 contract) — its number now comes from the plan. A concurrency test fires two creates in one organisation through two connections and reads exactly one row. **The guard is replaced, not deleted** (ADR 0274 authorises it): `test_no_string_produces_plan_limit_reached` → **`test_plan_limit_reached_is_produced_only_by_the_entitlement_readers`** — the word occurs in exactly the named files (`errors.py`, `control_service.py`, `plans.py`, 0008's template, the OpenAPI snapshot, `bin/cloud.py`'s message map, the docs) and nowhere else; registry node id moved in the same commit (D1119). **On the trip, side by side with no override**: the probe organisation's create while `slot5-prod` is `ready` → `plan_limit_reached`, no row (capacity green: a slot was ready); the lifecycle's own new organisation's create after `slot5-prod` is deleted → `capacity_exhausted {reason: no_slot}`, no row (entitlement green: zero projects). **No override verb** — the brief's *"limit raised for the test"* is met by a second organisation, which the product already lets an account create (`"create_organization": ACCOUNT`, `control_roles.py:60`). | The order is the specification's; the SQL lock is what makes a limit a limit under two requests; a second organisation reaches the capacity path without a support tool nobody asked for. | **0274**, 0221 |
| **D2522** | D1967: *"`premium` `unavailable_during_beta` … *Notify me* writes an interest row"*; ADR 0247: *"Nothing `planned` has a control."* | The `plan_premium` row is `planned` with `controls: []` (`reality-ledger.yaml:670-683`); `unreachable_rows_with_controls` (`reality_ledger.py:197-203`) fails a `planned` row that lists a control. *Notify me* is a control. | **`app.control_plan_interest`** (`organization_id`, `plan`, `requested_by`, `requested_at`; primary key `(organization_id, plan)`, an upsert — asking twice is one row) written by `POST /v1/organizations/{org}/plan-interest {plan: "premium"}` (member, human session) through `app.control_register_interest` (DEFINER); `apg plan notify-me`. **`plan_premium` goes to `trial` in the bump** with customer text *"Premium is defined and not available during the beta: its limits are shown, and Notify me records that you asked. Nothing is charged (being verified)."* and the control *Notify me*; at the close `beta` iff its claims passed. The operator reads interest with `sudo bin/control.sh` — **not built**; the rows are read by the operator through `bin/db.sh` on control-prod (a documented query in the operator guide). | The row's status describes what the concept does in the beta — shown and unavailable, with a working request — and the guard keeps a control off a row that does not work. | **0274**, 0247 |
| **D2523** | D1966: *"The reconciler samples each project's readings on an interval into the control project's `usage_samples` (through the same container reads as the doctor) … Metered: database and repository bytes, branch count and bytes, active and sleeping seconds (from the operation history), requests, agent calls, workflow executions, connections (`pg_stat_activity`), DB time (`pg_stat_statements`, after 41) … each sample names its instant."* | `doctor usage` (`doctor.py:1081-1128`) reads eight figures at the moment asked; `agent_tool_calls_total` is per `mcp` process (D1609/D1643) — an instant query loses calls when `mcp` is recreated; `traefik_service_requests_total` is a cumulative counter (D553: a counter cannot answer a point-in-time question). No table. | **`app.control_usage_samples`** (0008): `project_key`, `observed_at`, `state` (`active` \| `sleeping`), `database_bytes bigint`, `repository_bytes bigint`, `branch_count int`, `branch_bytes bigint`, `customer_connections int`, `requests_counter bigint` (the counter AS READ, summed over codes below 400 — D2525), `agent_calls int` and `workflow_runs int` (**rows created since the previous sample**, read from `app_private.agent_audit` and the workflow run table by their creation time — durable, unlike the per-process series), `last_customer_activity timestamptz`, `unread text[]` (the figure names not read) and `reason text`; primary key `(project_key, observed_at)`. **Written every `USAGE_SAMPLE_SECONDS = 300`** by `Reconciler.record_usage` for each declared slot with a deployed document (the `record_backups` loop's set), through `app.control_record_usage(p_samples jsonb)` (INVOKER, **granted to nobody**, key whitelist like `control_record_backups`). Each figure read through `container_exec` as `doctor usage` reads it (`pg_database_size`; the repository bytes from the D2512 reading; `pg_stat_activity` counted for the two customer roles; the project's Prometheus through the store container); **a figure that cannot be read is `NULL` and named in `unread`** (ADR 0195), a sleeping project's sample is `state = sleeping` with every container figure unread (*"the project sleeps"*). **Not metered in 41**: DB time (needs `pg_stat_statements`, Session 42), egress/provider/embedding (`not_metered`). **Active and sleeping seconds are computed at read time from the operation history** (`project.sleep`/`project.wake` finished times, creation, deletion) — never sampled. Samples are kept; nothing prunes them in 41 (§10: ~288 rows per slot per day). | Durable sources for counts, the counter stored as read with its instant, and *not read* as a value — the three ways a usage page lies, closed by construction. | **0275**, 0195 |
| **D2524** | D1966: *"`/api/v1/usage` aggregates per project and per organisation"*; stage plan *Builds*: *"`apg usage`"*. | No route; `KEY_SCOPES` (`control_roles.py:176-200`) gives keys `projects:read` for project reads. | **`GET /v1/projects/{key}/usage?hours=N`** and **`GET /v1/organizations/{org}/usage?hours=N`** (`N` 1..720, default 24), viewer+, keys with `projects:read`, through `app.control_project_usage` / `app.control_org_usage` (DEFINER, membership-checked; a foreign and a missing project answer alike, THR-CTL-ENUMERATION's rule). The document: `window {from, to}`, `samples {expected, present}`, per figure `{latest, latest_at, max, unread_samples}`; counters (`requests`) as **the sum of increases between consecutive samples, a decrease read as a reset** (counted from the lower value, D553), with the reset count; `agent_calls` and `workflow_runs` as sums; `active_seconds` / `sleeping_seconds` from the history; each plan entitlement with its value, `enforced` and the usage figure it is read against. A window with no sample answers `could_not_determine` with the reason — never zeros. `apg usage show --project-key K \| --organization O [--hours N] [--json]`. | The aggregation is defined once, in SQL, over what was recorded; the page states how many samples it is made of. | **0275** |
| **D2525** | D1956: *"Idle sleep (*suspend when inactive*) is a per-project setting the reconciler acts on, reading idleness from the edge's request counter and `pg_stat_activity` — a trigger"*; spec: *Never / 5 / 15 / 30 minutes / 1 hour*; D2147: *"the sampler that owns them is 41's"*. | Nothing measures idleness (0 hits). **The operator, 2026-10-16: opt-in, default never.** The origin CHECK admits `member` and `expiry` only (`0006:45`; ADR 0272 `:71-74`); ADR 0272 `:108-109` warns that a project's expiry may not use its precedent. The workflow worker commits a heartbeat every 5 s (D2456) and PostgREST/auth/mcp hold pooled connections, so *any* backend count is never zero. Internet scanners reach any public name: the edge's counter may move with no customer (unmeasured — Sheet E0). | **A setting**: `app.control_projects.idle_sleep_minutes int NULL CHECK (idle_sleep_minutes IN (15, 30, 60))` (NULL = never, the default) and `idle_sleep_set_by uuid` (the member), set by **`PUT /v1/projects/{key}/idle-sleep {minutes: 15\|30\|60\|null}`** (member, keys with `projects:write`) and `apg project idle-sleep --project-key K --minutes 15\|30\|60\|never`. **The signal** (both from D2523's samples): (a) **no HTTP request answered below 400** — the increase of the project's edge counter restricted to `code < 400` is zero between every pair of samples in the window (scanners' 404s do not keep a project awake; E0 measures what moves the counter at rest and with a control request; **if the counter's sub-400 part moves with no traffic, §9's stop**); (b) **no customer-role activity** — `last_customer_activity` (the latest `backend_start`/`state_change` of any backend whose role is one of the project's two customer roles, or now if one is not `idle`) is older than the window's start. Platform roles are ignored: they are the product's own work. **The decision is the control database's**: the reconciler, after each usage pass, calls **`app.control_request_idle_sleep(p_project text)`** (INVOKER, granted to nobody, like `control_request_expiry`), which inserts ONE `project.sleep` with **`origin = 'idle'`** and `requested_by = idle_sleep_set_by` **only if** the setting is set, the project is awake and its last operation finished at least the window ago (a wake resets the window), no operation of the key is non-terminal, **and every sample the window should hold is present** (`ceil(minutes × 60 / 300)` samples, contiguous within 1.5 × the interval) **with no figure of (a) or (b) unread** — a missing or unread sample means *not idle* (a decision that fails closed). 0008 widens the CHECK: `origin IN ('member', 'expiry', 'idle')` and `(origin = 'member' OR (origin = 'expiry' AND type = 'branch.delete') OR (origin = 'idle' AND type = 'project.sleep'))`. **ADR 0276**: idle sleep is a trigger — a second kind of operation the reconciler requests, supersedes ADR 0186's *"never a trigger"* for this one field only, amends ADR 0272 (*"exactly one kind"* → two) and ADR 0256. Wake stays by request (`wake_on_connect` `planned`). The notification says so. | A trigger reading two unmeasured counters was D2147's reason to wait; the samples now hold them with their instants, and the control database decides from a record anyone can re-read. | **0276**, 0186, 0272, 0256 |
| **D2526** | D1968: *"In-app only: a `notifications` table in the control project written by the reconciler when an operation ends and by the usage sampler when a limit crosses 80%, listed by `/api/v1/notifications` … Project-plane events (approvals, backup health) are read from the readings that already state them, not copied."* | No table, no route. `control_finish_operation` (`0004:454-493`, INVOKER, run by the reconciler) is the one place every operation ends; a `project.export` result carries a secret URL (`secret_only_on_export`, ADR 0259). | **`app.control_notifications`** (0008): `id uuid`, `organization_id`, `project_key NULL`, `kind` (`operation_succeeded` \| `operation_failed` \| `idle_sleep` \| `branch_expired` \| `limit_approaching`), `text varchar(300)`, `created_at`. **Written inside 0008's re-created `control_finish_operation`, in the same transaction**, from a fixed template per kind and type (*"project.sleep on slot5-prod succeeded (requested because it was idle for 15 minutes); wake it with apg project wake"*) — **interpolating only the type, the project key, the origin and the error code, never `p_result`, never a result secret, never a caller value**; the function body otherwise byte-equal to 0004's (a test diffs the two bodies minus the inserted block). `limit_approaching` by the sampler through `app.control_record_limit_notice(p_project, p_entitlement)` (granted to nobody; at most one per entitlement per organisation per UTC day) when a read-not-enforced figure (`storage_gb` against `database_bytes`, `agent_calls_per_day` against the day's sum) crosses 80%. **`GET /v1/organizations/{org}/notifications?limit=N`** (viewer+, human session or `org:read`; newest first, `N` ≤ 200) through `app.control_list_notifications` (DEFINER). No read state, no deletion, no email (D1951). `apg notifications list --organization O`. | The end of an operation is already one transaction in one function; a notification written there cannot disagree with the operation, and a template cannot carry a URL. | **0275** |
| **D2527** | D1978: *"First run: the `THR-*` rows"*; threat items #4 (entitlement half), #5 (plan-limit bypass and usage tampering), #10 (notifications, usage figures). | Items #4's entitlement half, #5 and #10's usage/notification half are prose (`threat-model.md:212-222`, `:247-255`); #9 (observability poisoning, ClickStack exhaustion) is Session 42's now (D2510). | **Run 1 rewrites #4, #5 and #10's new half with the negative test each owes BY NODE ID (§2), and adds one item: *a trigger acts on a stale or forged sample*.** Run 9 moves them into the table as **`THR-PLAN-BYPASS`** (a caller raises its own limit, or two concurrent creates pass one limit — PLAN-ENT-001's concurrency test; no route writes a plan or a limit), **`THR-USE-TAMPER`** (no customer surface writes a sample, an interest row other than its own organisation's, or a notification — the three writers granted to nobody; a member's `idle-sleep` writes only its own project's setting), **`THR-USE-LEAK`** (a foreign organisation's usage and notifications answer `404` like a missing one; no notification text carries a URL, a key or a result member — the canary over the templates), **`THR-USE-IDLE`** (a missing, stale or unread sample never sleeps a project; a sleep requested by idleness is attributed and `origin = idle`). **No `\|` inside a cell** (the parser drops the row silently). | Rows before code. | — |
| **D2528** | Stage plan §5: *"`apg usage`, `apg plan`"*; D2437's lesson: *two meanings of one verb is threat #7's confusion*. | `apg X` → `bin/X.sh` (`apg.sh:269`); `bin/doctor.sh --reading usage` is the operator's (not `apg usage`); no `bin/plan*`, `bin/usage*`, `bin/notif*`. | **Three customer commands**: `bin/plan.sh` (`apg plan show --organization O \| list \| notify-me --organization O`), `bin/usage.sh` (`apg usage show …`), `bin/notifications.sh` (`apg notifications list --organization O`), each a shim of `bin/endpoint.sh`'s shape dispatching into `bin/cloud.py` families `plan`, `usage`, `notifications`; and **`apg project idle-sleep`** in the existing `project` family. `test_cli_contract.py`: `SHELL_COMMANDS`, `COMMANDS_WITH_VERBS`, a test that `apg usage` dispatches to a customer command and `doctor --reading usage` stays the operator's. | The customer's nouns; the operator's reading keeps its name. | **0274**, **0275** |
| **D2529** | ADR 0162: what a bump permits; stage plan §2.2. | 1.18.0 priced `minor` with `--also api_operation_added` (`__init__.py:1129-1143`). Without a declaration the command reads only `patch` (`:1133-1135`). | **1.19.0, predicted minor**: no project-manifest, outputs, host or lock schema moves; no released migration (39 stays); the control set's `0008`; routes added (`api_operation_added`, declared). R1 reads `upgrade plan --also api_operation_added` on the three operator projects; a `major` is §9's stop. `__init__.py` gains a Session 41 paragraph in Session 40's format (`:1091-1144`). | The release adds a control migration and routes; it changes no deployed document. | 0162 |
| **D2530** | D2494: *"A row that says 'a sheet is owed' is not a sheet; the next plan must carry it as one."*; D2509: memory with a branch live UNMEASURED; D2500: the pooled name through the windows. | Session 40's plan carried Sheet RA inside a row (D2494) and no sheet read memory with a branch live (D2509). | **The appendix carries Sheets RA, M1 and PV as headed sheets** with their command lines; Run 10's and Run 11's ordered lists name them. **Sheet M1** (day 2, with `dev` ready): `free -m`, `sudo bin/doctor.sh capacity --host host.yaml` (read `--help` first), `docker stats --no-stream` for the branch's three containers — the envelope's `UNMEASURED` row (`capacity.py:1978-1986`) moves out at the close. The lifecycle instrument's pool probe (D2500's repair) covers every window; the close moves `capacity.py:1965-1977` out if every window reads `covered`. | A measurement nobody scheduled is a measurement nobody took (D2509); a sheet is the schedule. | — |
| **D2531** | ADR 0272 `:67-89`: the reconciler requests exactly one kind of operation. | An idle sleep (D2525) is a second kind; `control_request_expiry` is the model (`0006:446`). | **Same shape, second function**: `app.control_request_idle_sleep` beside `control_request_expiry`; both granted to nobody; both insert at most one row and only with no non-terminal operation for the key; `REQUEST_IDLE_SLEEP_SQL` beside `REQUEST_EXPIRY_SQL` (`reconciler_dispatch.py:205`). The dispatch test's closed set of SQL the reconciler may run widens by exactly the three new calls (`control_record_usage`, `control_request_idle_sleep`, `control_record_limit_notice`). | A closed list of what the root actor may ask for stays closed by being extended by name. | **0276**, 0272 |
| **D2532** | Session 40 Sheet P1 for `slot4-prod`. | A new slot needs three grey A records, two R2 buckets with tokens, a B2 mirror bucket with a key, an Infisical project (bootstrap) — `slot4-prod`'s were made by the agent (R2, at the operator's request, through the Cloudflare API) and the operator (DNS, B2, tokens). Branches run on `slot3-prod`, whose two wildcards exist since Session 40. | **Sheet P1 for `slot5-prod` only**: `A slot5.agenticpostgresql.com`, `A pool.slot5…`, `A direct.slot5…` → `15.204.231.45`, DNS only, no AAAA; R2 `apg-slot5-prod` and `apg-slot5-prod-backup` (EEUR, Standard; the agent may create them through the Cloudflare API **only if the operator asks on the day**, recorded like D2309) with Object R&W tokens; B2 `apg-slot5-prod-backup-mirror` with a key. **No wildcard for `slot5-prod`** (no branch of it is made). | One slot, one lifecycle; the branch parent already has its names. | 0257 |
| **D2533** | Stage plan §8: *"PostgreSQL is the final authorization authority"*; *"no customer surface writes a usage sample or an entitlement"*. | The control set's writers for reconciler state are INVOKER functions granted to nobody, reached as `postgres` through `container_exec` (`control_record_slots` `0004:513`, `control_record_backups` `0006:403`); readers are DEFINER functions granted to the auth service (`0006:143-191`). | **0008 follows the set's two shapes exactly**: writers `control_record_usage`, `control_request_idle_sleep`, `control_record_limit_notice` INVOKER + `REVOKE ALL … FROM PUBLIC` and no grant; readers and the member writes (`control_list_plans`, `control_get_org_plan`, `control_register_interest`, `control_project_usage`, `control_org_usage`, `control_list_notifications`, `control_set_idle_sleep`) DEFINER, granted to the auth service only, each calling `control_require_role`. New tables FORCE RLS with no policy for the auth role (reached only through the functions). `app.control_plan_limits` is seeded by the migration and **held equal to `plans.PLANS` by a test** (the SQL twin of a release table, like `test_branch_runtime`'s compose twin). | The same two doors as every earlier control table; a new table gets no third. | 0251, 0255 |
| **D2534** | ADR 0259: *"a sleeping project's archiver is stopped, so its restore point is its sleep time"*. | An idle sleep stops a customer's archiver without a person asking at that moment. | **Said where the customer sets it**: the `idle-sleep` route's answer, `apg project idle-sleep`'s output, the `idle_sleep` row and the notification each say *"while it sleeps, its backups stop: its last restore point is the moment it went to sleep"*. No change to sleep itself. | A setting that changes the backup guarantee must say so when it is set. | **0276** |
| **D2535** | CLAUDE.md §2: *"M7: Sheets X1/X2 (retire Hetzner) ALLOWED since 2026-10-12 ~21:30Z and NOT YET RUN"*; Session 40 §10's created items. | The old host's three projects stopped (the way back). Session 40 §10 also created: branch certificates accumulate in `acme.json`; the parent's user hashes copied into a branch; the backups recording's R2 requests. | **Not this plan's**: M7's sheets stay in `docs/plans/session-38-migration-plan.md` and may run on any day outside this trip's sittings; this plan's sheets never name the old host. The three Session 40 items are carried in §10 untouched. | Two trips' sheets interleaved is D1510's failure in waiting. | — |

**Rows the runs add** (execution order; next free D2552):

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D2536** | Run 1's Sheet E0 text: *"`sudo bin/doctor.sh --project slot3-prod --reading usage`"*; D2528: *"`bin/doctor.sh --reading usage` is the operator's"*. | `bin/doctor.sh` (at `8cc3440` and `e89ac85`) takes the reading as a VERB in first position — `sudo bin/doctor.sh usage --project <key> [--json]` (`:75`) — and maps it to `bin/doctor.py --reading usage` (`:178-193`); `--reading` is the Python side's flag, not the shell's. | **`s41-e0.py` runs `bin/doctor.sh usage --project slot3-prod`** (read from `--help`, as the appendix requires). D2528's test (`test_the_usage_verb_is_the_customers_and_the_reading_is_the_operators`) names the operator's reading as **`doctor.sh usage`** (the verb) / `doctor.py --reading usage` (the flag) — Run 7 writes it against both spellings. | A sheet line is read from the command's own usage block, never from a plan's paraphrase. | — |
| **D2537** | D2515 / Run 1 rig 41b: *"(1) before the router's certificate is issued → verification fails (Traefik's default certificate)"*; *"An error the check cannot classify → `door: "unknown"`"*. | **Rig 41b** (2026-10-16, WSL `~/s41/run1/rig41/rig41b.sh`, `rig41b.txt`; Pebble and challtestsrv at rig 40b's digests, Traefik `v3.7@sha256:9c3b91d5…`, Python 3.14.4 / OpenSSL 3.5.5): from the containers' creation, both names answered the `SSLRequest` with `S` and then **the edge closed the TLS handshake** (`[SSL: UNEXPECTED_EOF_WHILE_READING]`) — **no default certificate is served under the `postgres` options' `sniStrict: true`**; at **+3.0 s** both names verified against Pebble's issuing root (one order, one certificate). Against the wrong root (minica): `pending … unable to get local issuer certificate`. **Control** (a name with no router): the same EOF for 60 s, never verified. | **After the `S`, an EOF in the handshake and a verification failure both read *pending*** (*"the door's certificate is not issued yet"*) — the edge answered and the door is not open; **`unknown` only when the check could not run** (no connection, no `S`, any other TLS failure). The check cannot tell *no certificate yet* from *no router* (both EOF): for a branch the router is attached before the check starts, so `pending` at the bound is said with that reason. `DOOR_SECONDS = 180` stays (60× the rig's 3.0 s; the trip's 4.5 s, D2503). ADR 0271's amendment says so. | The measured shape of *not yet*, not the expected one; folding it into *unknown* would report a reading as a failure to read. | **0271** amended |
| **D2538** | D2521: *"0008's `app.control_request_operation` takes `SELECT … FROM app.control_organizations WHERE id = … FOR UPDATE` before counting"*. | `0001-control-identity.sql:152-163` gives `app.control_organizations` a SELECT and an INSERT policy (`TO object_owner`) and **no UPDATE policy**; the table FORCEs row level security (`:119-120`). **Rig 41d** (2026-10-16, `~/s41/run1/rig41/rig41d.py`, `rig41d.txt`, control set `0001`–`0007` + a draft `0008`): **without an UPDATE policy the definer's `SELECT … FOR UPDATE` returned NO row** — the draft's `IF NOT FOUND` raised `AP500: the organisation row was not locked` on every request; unchecked, the count would have run unlocked, silently. **With a lock-only policy** (`FOR UPDATE TO object_owner USING (id::text = current_setting('app.control_org', true)) WITH CHECK (false)`): the second of two creations in one organisation **waited 3.2 s** on the row, then `AP409: plan_limit_reached` — one row; **control**: two organisations, two rows, no wait (0.1 s). Also measured: `control_request_idle_sleep` inserted ONE `project.sleep` `origin = idle` `requested_by` the setter over a full quiet window (−840/−540/−240/−10 s), `NULL` with the −540 s sample missing; `idle` on a `project.wake` refused by the CHECK; a finish wrote ONE notification, a rolled-back finish none. | **`0008` adds the lock-only policy** `control_organizations_lock` and the function **raises if the row was not locked** (a decision fails closed, ADR 0195) — Run 4 writes both, with a test that a scoped UPDATE through the policy is refused (`WITH CHECK (false)`, not measured by the rig: its unscoped UPDATE matched no row). **A pending creation counts** toward `projects_active`: with Free's 1, a second creation while the first is open answers `plan_limit_reached` where 1.18.0 answered `409 conflict {operation}` (D2166's unique index stays, the guard under the guard). ADR 0274 records both. | A lock that locks nothing is the fold this project keeps finding — a value that looked enforced and was not; the rig is why it is a policy now and not a surprise on the host. | **0274** |
| **D2539** | D2525's signal (b): *"`last_customer_activity` (the latest `backend_start`/`state_change` of any backend whose role is one of the project's two customer roles …)"*; rig 41d's draft required `last_customer_activity IS NOT NULL` in every sample; Run 1's E0 text: *"ONE `curl` … to `slot3-prod`'s app route"*. | **Sheet E0** (2026-10-16 10:37–11:09Z, `slot3-prod` at `8cc3440`, `/home/op/s41-e0.txt`, copied to WSL `~/s41/e0/` 0600): the edge counter's sub-400 part **8 → 8 → 8** at T0, T0+15 and T0+30 min with no traffic (all eight on `apg-slot3-prod-health@docker`); the customer roles held **no backend** at all three reads. The one `curl` to `/api/app` answered **404** (no root handler), so it could not show a sub-400 request moving the counter: **one more GET, to `/api/rest/`, answered 200**, sent before the fourth read (11:08:06Z). Fourth read: `code=200` 9 (`rest` +1), `code=404` 1 (`app`); one `customer_app` backend, `idle`, `backend_start` 11:07:53.19, `state_change` 11:07:53.20 — the `psql`'s instant, unmoved 97 s later although the transaction-mode pooler kept the server connection (`server_reset_query_always = 1` stamps it at release, `compose.yaml:792-793`; no `min_pool_size`, so no server connection opens without a client). | **No stop** (§9: neither the sub-400 count nor a customer `state_change` moved with no client). **"No customer backend" is quiet, not unread**: a sample records `last_customer_activity` as the latest instant over the customer roles' PRESENT backends, `NULL` when there are none, and only a failed `pg_stat_activity` read puts it in `unread`; `control_request_idle_sleep` treats `NULL`-and-read as older than the window. Rig 41d's `IS NOT NULL` would have kept every idle project awake — Run 4 writes the test (`test_idle_sleep.py`: a window of samples with no customer backend sleeps). **What a sample can miss**: a query whose backend closes before the next sample. PgBouncer's default `server_idle_timeout` (600 s, not set in `compose.yaml`) keeps it beyond the 300 s interval — **not measured here; Run 8's rehearsal reads the backend gone and the sample after it**. A `doctor --project` run's `route health` request crosses the edge as a 200 (the health router's 8 earlier requests are such reads): an operator's doctor keeps a project awake for a window — the safe direction; not excluded. | The two signals measured at rest and moved by a control; the third answer (*not read*) kept separate from *none present*. | **0276** |
| **D2540** | D2512 / Run 2 step 1: *"`backup_state` returns two more keys, `oldest_backup_stop` and `repository_bytes`"*; §2 BR-BACKUP-002: *"every key the reading takes from `info` is a key `backup_state` returns"*. | **`backup.sh info --json` IS the deployed document's `backup_state` block**: the deploy publishes it verbatim (`bin/deploy-project.py:1752-1761`, `with_archiver(summary, …)`), `schemas/outputs.schema.json` `$defs.backupState` is `additionalProperties: false` with eight members, and **`test_backup_repository_report.py::test_repository_bytes_is_not_published_in_the_deployed_document`** (passing) holds `repository_bytes` out of it. `bin/backup.sh:19-23` says so: *"a member added there would land in outputs.json and be refused by the schema"*; `usage --json` exists for exactly that reason and `doctor usage` reads it (`doctor.py:1138-1158`, D1591, D1614). The plan's step would have been an outputs schema bump (§9: no outputs change) or the weakening of a passing test (§9's stop). | **The tree wins: `backup_state` is unchanged.** `usage --json` prints **`backup_report.usage_block(summary, stanza)`** = `{stanza, repository_bytes, oldest_backup_stop}` (one function, so the proof calls the producer and `bin/backup.py verb_usage` prints it); `reconciler_dispatch.backups_reading` gains `usage` and reads `oldest_backup_stop` from it; `backups_of` runs `info --json` (status, last full) **and** `usage --json` (the window) — two children per slot every 900 s, each one `pgbackrest info` (~2 s on E0). `info`'s failing exit is **`backup_report.INFO_FAILING_EXIT = 6`**, used by `verb_info` (both returns) and by the reconciler's parse (`_json_of(…, INFO_FAILING_EXIT)`), never retyped. The class guard holds the keys read from `info` ⊆ `backup_state`'s and from `usage` ⊆ `usage_block`'s, and asserts `oldest_backup_stop` stays out of the deployed block. **Run 9 writes BR-BACKUP-002's text as "every key the reading takes from a printed block is a key its producer returns"** and adds the sleeping proof (D2541). Usage samples (ADR 0275, Run 6) read `repository_bytes` from the same `usage --json`. ADR 0273's amendment and ADR 0275 corrected. | Where the shape is made was the right idea; which shape is the deployed document's is the tree's, and it had already answered. | **0273** amended |
| **D2541** | — (found by Run 2's proof). ADR 0273: *"a sleeping project's reading says `sleeping`"*. | `backups_of`'s sleeping branch calls `backups_reading(…, mirror=None, sleeping=True)` (`bin/reconciler.py:1316` at `e89ac85`); `backups_reading` built its reasons as `[c.detail for c in (repository, archived, mirror) if _status(c) != "ok"]` — `_status(None)` is `"unknown"`, so it took **`None.detail`: `AttributeError`**, raised out of `record_backups` (no `except` for it, `reconciler.py:1174-1192`) and out of `run()` (`:1446-1468`) — **the reconciler process exits on every backups pass while any slot sleeps**. Deployed in 1.18.0. Never reached on a trip: Session 40's sleeps lasted 38.9 s and the pass runs every 900 s (`NRestarts=0` on the host, E0). Session 41's idle sleep (ADR 0276) holds a slot asleep for minutes — it would have killed the reconciler mid-trip, and systemd's restart would have interrupted any running operation (D2152). | **`backups_reading` skips an absent check** (`if c is not None and _status(c) != "ok"`); a sleeping reading's `mirror_status` is `unknown` with no reason line from it. **Proof**: `test_backups_reading_from_the_producer.py::test_a_sleeping_slot_is_read_without_raising` drives `backups_of`'s own branch (the container reads `false`), asserts `sleeping`, no window, `mirror_status` `unknown`, and that no backup child was asked. Battery mutation (d) restores the old line → that test FAILS (and the three window tests with it: they pass no mirror either). | A report that raised instead of saying *unknown* is ADR 0195's failure in its loudest form, and a reconciler loop that dies on a reading is the second principal stopping on its own instrument. | **0273** amended |
| **D2542** | Run 3 steps 1–6: *"`image_for(tag, digest, docker)` … `--platform linux/amd64`"*; *"`branch.json` gains `image_tag`, `image_digest`, `reason`, `door`"*; *"`SERVICES` gains the two customer poolers for the `containers` view only"*; the door's trust is *"the system store"* (unmeasured on the host). | **Measured on the host** (2026-10-16, as `op`, `/home/op/agentic-postgres/.venv/bin/python` = uv CPython **3.12.13 / OpenSSL 3.5.7**, the interpreter `branch-runtime.sh` runs; `ssl.get_default_verify_paths()` → `capath='/etc/ssl/certs'`, `cafile=None`): the draft door check over `127.0.0.1:5432` → `pool.slot3…` and `direct.slot3…` **`ready`** (ALPN `postgresql`, Let's Encrypt chain verified, notAfter 2027-01-10); `nothing.slot3…` (no router) → `[SSL: UNEXPECTED_EOF_WHILE_READING]`; **the committed `branch_door.check` on the host** → `('ready', '')` and `('pending', 'the edge holds no certificate for nothing.slot3.agenticpostgresql.com yet')` — the EOF arrives as `ssl.SSLEOFError` (WSL `~/s41/run3/door-host.py`, `door-host.txt`). `branch_record` was a closed member set at `schema_version` 1 (`_problem`: missing/extra refused). `branch_reading` (`reconciler_dispatch.py:567-596`) names its payload's keys one by one. `containers` never reads `SERVICES` (only `labels`/`logs` do). `bin/cloud.py` `WAIT_SECONDS = 2400` (`:93`), below a 3,600 s branch bound; `bin/operation.sh:37` prints it. A `@dataclass` in `bin/reconciler.py` breaks every test that loads it by path unregistered (`dataclasses` reads `sys.modules[__module__]`). | **(1)** `image_for(tag, digest, platform, docker)` takes the platform the container recorded, so **`branch.json` also records `image_platform`** (`ImageManifestDescriptor.platform` as `os/architecture`) — never a typed `linux/amd64`; `restore_drill.image_identity(inspect)` reads the three from the parent's RAW inspect. **(2)** `branch_record` **schema 2** with five added members (`image_tag`, `image_digest`, `image_platform`, `door`, `reason`); **version 1 is still READ** (its five None) so capacity charges and the reconciler lists a branch 1.18.0 made, and a start refuses it with *"this branch was made before 1.19.0 and records no image identity; reset it"* — reset records the parent's identity afresh. **(3)** `reason`/`door` stay in `branch.json` and the runtime's `status` until Run 4's `0008` adds their columns (the payload names its keys; nothing new reaches `control_record_branches` in Run 3). **(4)** `SERVICES` unchanged (the `containers` view lists by Compose project, not by service); `containers` reads each branch's `COMPOSE_PROJECT_NAME` from its `branch.env` and checks it against `^apg-[a-z0-9-]+_[a-z][a-z0-9]{1,11}$` before use. **(5)** `WAIT_SECONDS = 3900` (and `operation.sh`'s usage line), held above every type bound by `test_a_branch_promotion_bound_sits_inside_its_reconciler_budget`. **(6)** The start log's result is a `NamedTuple`. **(7)** `PROMOTION_SECONDS = 2400 < CHILD_SECONDS["branch-runtime.sh"] = 3300 < OPERATION_SECONDS_BY_TYPE = 3600 < WAIT_SECONDS = 3900`; `RESTORE_SECONDS` 7,200 stays above the child budget as it was (the child's bound binds first; unchanged, recorded). | The trust store and the EOF class were the two third-party facts the door rests on; both read on the host with its own interpreter before the code depended on them. | **0271** amended |
| **D2543** | Run 4: *"`services/auth-api/app/plans.py` and `src/agentic_postgres/plans.py`"*; the battery: *"(a) drop the `FOR UPDATE` → the concurrency test FAILS (two rows); (b) the idle function without the sample-count check → `test_a_missing_sample_is_not_idle` FAILS"*; targeted *"`test_control_operations` (grep its name)"*; 0008 *"the origin CHECK widened"*. | **(1)** `test_repository_contract::test_no_module_is_imported_only_by_its_own_tests` refuses a `src/` module nothing in `bin/` or `src/` imports, and nothing would import `src/agentic_postgres/plans.py` in Run 4. **(2)** D2166's unique index already holds an organisation to ONE open creation: without the lock a second concurrent creation still leaves one row (answered `conflict` with the first's id). **(3)** Battery round 1: `test_the_lock_is_held_across_the_count_by_one_transaction` PASSED with `FOR UPDATE` removed -- its `FOR UPDATE NOWAIT` probe met the `FOR KEY SHARE` lock the operation row's foreign key takes on the organisation. **(4)** The sample-count check is implied by the window's start, end and contiguity checks. **(5)** No `test_control_operations.py` exists; the operations proofs are `test_control_states` and `test_control_connections`. **(6)** 0008's first draft folded `control_operations_expiry_deletes_a_branch` into one combined constraint; two passing proofs read the refusal's constraint NAME (`test_control_branches::test_an_expiry_is_bounded_and_only_an_expiry_requests_without_a_member`, `test_branch_expiry::test_a_project_expiry_is_still_never_a_trigger`). **(7)** Two service proofs in `test_control_projects` (`test_no_ready_slot_refuses_before_a_row`, `test_one_operation_at_a_time`) create in an organisation `_org` gave a project: on Free the plan's limit now answers first, and the service maps `plan_limit_reached` only in Run 5. | **(1)** No `src/agentic_postgres/plans.py` in Run 4: the twin test imports `app.plans` (the control tests' habit); the re-export lands with its first caller, if Run 7's CLI needs one. **(2)** The concurrency proof asserts the CODE (`plan_limit_reached`) and that the second request WAITED (> 2 s), with one row; a third test reads the lock held across the count. **(3)** The probe is `FOR NO KEY UPDATE NOWAIT` (conflicts with `FOR UPDATE`, not with a foreign key's `KEY SHARE`); round 2 kills mutation (a) on both lock tests. **(4)** Mutation (b) as written is recorded as an expected SURVIVOR (a redundant belt, D493); the battery adds (b1) the contiguity check removed, killed by `test_a_missing_sample_is_not_idle`. **(5)** The two modules run in its place. **(6)** Each requested kind keeps its own constraint: `control_operations_expiry_deletes_a_branch` recreated with the same name and meaning (`origin <> 'expiry' OR type = 'branch.delete'`) and `control_operations_idle_sleeps_a_project` beside it. **(7)** **Runs 4 and 5 are pushed together and CI is read at Run 5's SHA** (the plan's own rule, D2463's shape): Run 5 maps the code in the service and gives those two proofs an organisation with no project for the capacity and serialisation paths (D2521: the capacity path is reached by a second organisation, never an override). | A guard that refuses an orphan is the thing to obey, not to route round; a lock proof must name the lock it proves; a refusal's name is part of its contract. | **0274** |
| **D2544** | ADR 0243: the proposal names every destructive statement of the set (`migrations.destructive_findings`, D1862); ADR 0198: the lint reads each template's statements through `sql_surface.statements`. | `sql_surface.statements` strips `--` comments **without regard to string literals**. 0008's first draft held `--` inside six literals (five `COMMENT ON … IS '…'` texts and the idle-sleep notification's template); the stripper cut each one's closing quote, the quote parity flipped, and every later reader read the rest of the file as inside a string: `propose` named **neither of 0008's two `DROP FUNCTION`s** (10 findings where 12 were due, measured: the swallowing literal began at the `control_record_branches` comment and ended inside `control_list_branches`'s body). The lint reads the same text, so its checks over that span read a string too. A parity reading over every template after `statements()` (an ODD count of `'` = a literal the reader may have lost) flags **18 of 51** -- 16 release templates (`0002`, `0008`-`0014`, `0016`, `0017`, `0024`, `0025`, `0027`, `0029`, `0032`, `0034`) and the control set's `0001` and `0006` -- **a heuristic, not a proof that any statement is hidden** (an odd count can come from a legitimate escape). | **0008's literals hold no `--`** (plain punctuation); re-proposed, the reader names all four of 0008's destructive statements. **The reader is not changed in Run 4**: a quote-aware comment stripper is a change to the lint every project set passes through (ADR 0198) and to the release surface reader, and it belongs to its own run with a test that fails on today's reader (a literal holding `--` before a `DROP`) and a pass over the 18 flagged templates. **Recorded in §10 as created; the operator decides when.** | The lint and the destructive findings are the review's eyes on a set; a reader that loses a quote is blind from there to the end of the file, and it said nothing. | 0198, 0243 |
| **D2545** | Run 5 step 3: *"`GET /v1/organizations/{org}/plan` … `PROJECT_WRITES` (`set_idle_sleep` member)"*; *"interest → human only"*; the battery's (c) *"usage readable by a foreign member → `test_a_foreign_and_a_missing_project_answer_alike` FAILS"*; the control *"a change to `branch_limit_reached`'s message text → only the CLI message test fails"*. | The tree names the organisation path parameter `{organization}` (`control_routes.py`, `main.control_paths`). `test_control_projects::test_every_write_route_has_a_role_and_a_type` requires every `PROJECT_WRITES` entry but cancel to request an executed type in `OPERATION_OF_ROUTE`; idle sleep and *Notify me* are settings, no operation row. Its `projects:write` key-scope set is closed at `{sleep, wake, resize}`. A usage read by a foreign member is refused twice: the service's `_live_project` and the SQL definer's `control_require_role(control_project_organization(...))`. `bin/cloud.py` holds no `branch_limit_reached` message (the CLI prints the server's word); the only text is the route's OpenAPI description. The moved node id (D2521's guard) was also cited by `docs/threat-model.md`'s `THR-LIFE-EXHAUSTION` row and by the generated `docs/acceptance-matrix.md` (D1187). `docs/control-plane.md:211` still says *"No code in 1.16.0 produces `plan_limit_reached`"*. | **(1)** Paths use `{organization}`: `/v1/organizations/{organization}/plan`, `/plan-interest`, `/usage`, `/notifications`; `/v1/plans`; `/v1/projects/{key}/usage`, `/idle-sleep`. **(2)** The two settings' roles live in a new `control_roles.SETTING_WRITES` (`register_plan_interest` member, `set_idle_sleep` member), not `PROJECT_WRITES`; `MATRIX` names the seven routes. **(3)** `KEY_SCOPES`: `list_plans`, `get_organization_plan`, `list_notifications` → `organizations:read`; both usage routes → `projects:read`; `set_idle_sleep` → `projects:write` (the closed set widened by exactly that route, recorded in the test); *Notify me* absent (a person asks). **(4)** `/v1/plans` serves the release table with the SQL-enforced numbers read from `control_list_plans` (a real reader of the twin, a missing row served as null, never defaulted). **(5)** No response model for `plan_limit_reached` (nothing would reference it): the create route's 409 description names its members. **(6)** Battery (c) is two mutations: (c1) the SQL reader's role check removed → the SQL-level proof FAILED; (c2) the service's check removed → SURVIVED behind the SQL check, as predicted -- defence in depth, recorded. **(7)** The control mutates the route description (no CLI text exists). **(8)** The threat row and the matrix moved with the node id. **(9)** `docs/control-plane.md:211` is **Run 7's** (the documents). | Each conflict decided by the tree; a guard that refuses a settings route in the operations table is a guard to obey by giving the settings their own table. | **0274**, **0276** |
| **D2546** | Run 5's targeted list (the plan's, with the modules the run touched). | **CI run 38929805106 on `d6558dff93d9f1c7d328806c844c9634ec5e52c3` FAILED** (`contract`, 16:10–16:32Z): `tests/contract/test_control_cli.py::test_only_the_hash_reaches_the_control_plane` (a second creation in one Free organisation, expected `conflict`, answered `plan_limit_reached`) and `::test_the_claim_picks_the_creation_whose_token_is_held` (two creations in an organisation holding `slot1-prod`). Neither module was in the targeted list -- the CLI proofs are Run 7's -- and `test_reconciler_claim` (which also creates) had not run either: a list derived from the run's own modules cannot see a caller the diff does not touch (D1486). | Both organisations put on **Premium** through a `_premium` helper (the D2166 and D2316 behaviours they read are unchanged; Free's refusal is D2521's own proof's). `test_control_cli` and `test_reconciler_claim` run: 23 passed. Pushed as a repair; CI read at its SHA. **Before a change to a shared refusal, grep `tests/` for every caller of the request it refuses** (`project.create`, `"POST", "/v1/projects"`, `"project", "create"`), not only the modules the plan names. | CI is the full check, and it did its job; the lesson is the grep that would have found both before the push. | — |
| **D2547** | Run 6: *"the doctor's read argv shared, not copied"*; *"The closed SQL set (D2531)"* -- *"the dispatch test's closed set of SQL the reconciler may run widens"*; the limit notices against *"a read-not-enforced figure"* of the organisation's plan; *"repository bytes from the D2512 reading"*. | **No closed-SQL-set guard existed** in `test_reconciler_dispatch` (its fake answers statements by marker; nothing held which control functions the root actor calls). The reconciler cannot read an organisation's plan without a fourth control call outside D2531's three. `backup.sh usage --json` already runs once per backups pass (900 s) in `backups_of` (D2540). A project's Prometheus answers an EMPTY result for `sum(traefik_service_requests_total{code=~"[123].."})` until a request below 400 has been answered. The first sample after a start has no `since` (the previous sample's instant). `test_auth_service_shape::SHARED_MODULES` is the closed list of service modules `src/` loads. | **(1)** `src/agentic_postgres/usage_reading.py` holds the doctor's `cluster_int`, `directory_kb` and `store_value` (moved from `bin/doctor.py`, which keeps `_cluster_int`, `_directory_kb`, `probe_store` as aliases so every reader is unchanged, D979) plus the sampler's `cluster_fields`, `activity_sql` (the two derived customer roles, checked) and `durable_counts_sql` (`app_private.agent_audit.started_at` and `app_private.workflow_run.created_at` since the database's own previous `now()`, checked). **(2)** **The guard is built**: `test_reconciler_dispatch::test_the_reconciler_asks_the_control_set_only_these` reads every `app.control_*(` name out of `reconciler_dispatch`'s statements and holds it to the ten of 1.18.0 plus exactly the three. **(3)** The notices use **Free's** numbers (`plans.DEFAULT_PLAN`): Premium is `unavailable_during_beta` and nothing moves an organisation onto it, so every real organisation is Free; a Premium one (root's SQL only) gets Free's informational threshold -- said here, enforced nowhere. **(4)** `repository_bytes` is the backups pass's own `usage --json` block, cached per slot (`usage_sink`), unread when older than two passes -- no second repository read every 300 s. **(5)** An empty store answer is **unread** (`the store holds no request answered below 400`): a slot that has never answered a 2xx is never idle (fails closed; the trip's slot is probed before its idle window). **(6)** The first sample's calls and runs are unread (*counted from the next sample*), never a zero. **(7)** `plans` joins `SHARED_MODULES` (the reconciler is `src/plans.py`'s first caller, D2543 (1)). | Every figure is a reading or a named *not read*; the closed list of what root asks the control database is now a test, not a sentence. | **0275**, **0276** |
| **D2548** | ADR 0247: *"nothing a customer can press acts on a concept that is `planned`"*; ADR 0254: a write is `not_available` while its type is not accepted (`require_accepted`, *"a request accepted into a row nothing will ever execute would be a control acting on a `planned` concept"*); ADR 0276: *"a per-project setting the reconciler acts on"*. | Found writing Run 7's documents. `PUT /v1/projects/{key}/idle-sleep` is a SETTING (`control_roles.SETTING_WRITES`, D2545), so `require_accepted` -- keyed by `OPERATION_OF_ROUTE` -- never ran for it; `app.control_request_idle_sleep` (0008) INSERTs a `project.sleep` from SQL, which cannot read the Ledger; `bin/reconciler.py` reads no `ACCEPTED_TYPES` (0 hits in `bin/`) and executes what is pending. With `sleep` and `idle_sleep` `planned` and `ACCEPTED_TYPES = {credential.rotate}` (main today), a member's 15 minutes would have slept an idle project by a type the Ledger refuses a person. Nothing caught it: the `idle_sleep` row's `controls` is `[]`, so `test_a_planned_row_has_no_control` reads nothing. | **The operator, 2026-10-16: repair both doors in Run 7.** `operations.IDLE_SLEEP_TYPE = "project.sleep"` and `IDLE_SLEEP_ROW = "idle_sleep"` (one authority, re-exported by `src/agentic_postgres/operations.py`). **(1) The route**: `ControlService.require_idle_sleep_offered()` before the body is read -- `409 not_available` naming `idle_sleep` for any value, nothing stored (the OpenAPI gains the 409; `contracts/control-openapi.canonical.json` regenerated). **(2) The actor**: `Reconciler.record_usage` asks the control set for an idle sleep only while `IDLE_SLEEP_TYPE in operations.ACCEPTED_TYPES`; the sample and the notices are unchanged. **(3) The guard**: `test_reality_ledger::test_the_idle_sleep_row_is_reachable_iff_its_sleep_is_accepted` -- the one check both doors make is faithful to the concept only while the row is reachable exactly when the type is accepted; Run 9 moves both together. A stored setting survives a row going back to `planned` and acts again only when the row is re-earned. Proofs: `test_idle_sleep::test_the_setting_is_not_offered_while_the_sleep_is_not_accepted`, `test_reconciler_dispatch::test_no_idle_sleep_is_asked_for_while_the_sleep_is_not_accepted`; the two earlier proofs take an `accepting` fixture (CLAUDE.md D2546: every caller of the route grepped -- `test_idle_sleep`, `test_control_cli`). | A setting whose effect is an operation is gated like the operation, at the surface AND at the actor; a guard that reads a declared field (`controls`) cannot see a door nobody declared (D816). | **0247**, **0254**, **0276** |
| **D2549** | Run 7: *"`docs/operator-guide.md` (reading interest rows through `bin/db.sh` on control-prod …)"*; D2528's test *"written against both spellings"*; *"`project idle-sleep` verb (its output says D2534's sentence)"*. | **`bin/db.sh` executes allowlisted, digest-checked named artifacts only -- never SQL** (`--help`: *"`sql` accepts a NAME, never a path and never SQL"*), so interest rows cannot be read through it; no command of this product reads `app.control_plan_interest` across organisations. `GET /v1/projects/{key}` carries no `idle_sleep_minutes`: a customer reads the setting only by setting it. The usage document's `agent_calls`/`workflow_runs` are `sum()` over the window with no unread count, so a partly-unread window's sum is a lower bound. `tests/acceptance-registry.yaml` `LIFE-CAP-001` still says *"nothing in Session 38 produces `plan_limit_reached`"* (true of Session 38). `docs/control-plane.md` said *"All five keep their state"*. | **(1)** The guide reads interest rows as **root `psql` through the control project's database container, the names derived from its deployed document** (`.database.container`, `.database.name` -- `control_registry.target`'s pointers), the precedent `bin/control.sh`'s *"a registry row is removed only by a root psql DELETE"*; the query was **run verbatim from the page** against a control cluster holding one row (`/tmp/s41-r7-interest-sql.py`: OK). Not run on the host; `jq` on the host is unmeasured -- the trip's sheet reads it first. **(2)** `plan notify-me --plan` choices are derived from `plans.PLANS` (every plan not `active` -- Premium), never typed; a person's session only, as the route. **(3)** `usage show` exits 6 when ANY project's usage is `could_not_determine` (the organisation form too, ADR 0195); `--hours` 1-720 and `--limit` 1-200 are refused before anything is sent. **(4)** `project idle-sleep` prints the ROUTE's note (one authority; the CLI proof holds it equal to `control_service.IDLE_SLEEP_NOTE`). **(5)** `bin/usage.sh`'s help names no `--project FILE|KEY`, so `apg`'s `APG_PROJECT` default never applies to it; its header names `sudo bin/doctor.sh usage --project KEY`. **Owed, the operator's**: the setting readable back (a widening of `GET /v1/projects/{key}`); a per-figure unread count for the two sums (the CLI says *"summed over the samples that counted them"*); `LIFE-CAP-001`'s text (Run 9 writes the registry). **(6)** *"All five"* -> *"Every one of them"*. | A runbook line is read from the command's own usage block (D2536); a sum with no unread count is reported as what it is. | **0274**, **0275** |
| **D2550** | §2: the live half of `LIFE-LIVE-005`, `PLAN-LIVE-001`, `USE-LIVE-001/002/003` (`tests/external/test_session41_reearning.py`), `BR-LIVE-003` (`tests/external/test_session41_branches.py`), `BR-LIVE-004` (`tests/deployment/test_session41_branch_host.py`); *"Session 40's four live claims re-run on Session 41's records"* (§7); D2518: *"`record40` → `(40, 41)` and `project_key` matched by `slot.SLOT_KEY`"*. | **No run writes the three live modules**: Run 8 commits only its Done, Run 9 registers their node ids, Run 11 runs them. The Sessions 38-40 proofs that re-run on Session 41's lifecycle record read exactly ELEVEN member operations (`LIFECYCLE`, D2442) and make their post-delete creation in **`probe["organization_id"]`** (`test_session38_public_lifecycle.py:308`, `test_session40_reearning.py:169`) -- the probe organisation, which holds `slot3-prod` and now answers `plan_limit_reached` (ADR 0274), not `capacity_exhausted`. | **Run 9 writes the three modules** (beside the registry that names them; `pytestmark`, the sweep-selector guard and `test_environment_gates` in its targeted list, D1240/D2381), against the record members Run 8 fixed (D2551). **Run 9 also moves the two post-delete creation proofs to the record's OWN organisation** (`record["organization_id"]`, the lifecycle's since step 1; Session 38-40 records carry the probe's there, so their reading is unchanged) -- stricter, never weaker: the creation asked in the organisation the lifecycle ran in. | A proof registered by no run is a claim that never executes (CLAUDE.md §7 question 7). | **0274**, **0275**, **0276** |
| **D2551** | Run 8: *"the record keeps ... every member the Sessions 38–40 proofs read"*; *"the route and pool probes on slot5-prod paused (the neighbours' probes keep running)"*; *"`ready` must mean the door answers on the first attempt"*; *"against a fake reconciler and a real control cluster with 0008"*; `s41-derive.py` *"exactly as `s40-derive.py` did"*. | The eleven-operation proofs read `record["operations"]` whole. Run 11 step 1 probes *"alpha, beta, control, slot3-prod and the slot"* from the host -- a host probe of the slot is requests answered below 400, which keeps it awake. `control_request_idle_sleep` counts the LAST finished operation (the expiry control's export, ~15 min before the idle step) and every sample of the window. No customer route reads whether a slot is `ready`. The parents' headers name their own scripts, and the new headers name their parents. | **(1)** `s41-lifecycle.py` keeps the eleven in `operations`; **the idle sleep and its wake go to `idle_operations`** (kept members gain `origin`, `requested_by`). **(2)** `--slot-probe-label`: the slot's host probe runs under ITS OWN label and is stopped (`s41-probe-stop.sh`) before the idle window; the instrument's own probes pause and resume after the wake. **(3)** The setting is turned OFF right after the idle sleep, before the wake: a second idle sleep during the K2 pause would be an operation no record names. **(4)** Notifications are listed before the K2 pause AND after the deletion (`notifications_after_delete`). **(5)** *"while slot5-prod is ready"* is evidenced by the next creation, in `lifecycle-s41`, being accepted into it; step 0's record keeps its instant. **(6)** `s41-branches.py`: a door read `pending` after its 180 s is a STOP (the plan's sentence), and `--after-reboot` makes ONE SSH, the agent account's `apg-diag containers` (ADR 0071). **(7)** The rehearsals' rehearsal-only moves, named: the lifecycle's fast-forwarded sampler moves the slot's operation history back 30 minutes and writes four quiet samples, then calls the REAL `control_request_idle_sleep`; a psql wrapper hangs ONE pool sample past the 60 s timeout (D2500); the branches' gateway is published on a loopback port so the runtime's OWN `await_door` (rig CA) and `command_start` run. **(8)** `s41-derive.py` substitutes in the BODY alone (the header split off first, the new one put on after): counted against the old header the renames found 3-5 where the body holds 2-3. | Measured offline, 2026-10-16: the lifecycle rehearsal PASSED (169 s) -- **a deleted project does not count against Free's `projects_active`** (the post-delete creation `capacity_exhausted {no_slot}` on 0008's own SQL), the real request function inserted exactly one `origin = idle` sleep, the pool thread sampled after a hung sample; its control PASSED (exit 4, *"no idle sleep was requested within 20 s"*); the branches rehearsal PASSED, three phases, both doors `ready` on the first attempt, dev back by `command_start` after a cached rebuild (`started from sha256:a76c1114227f, door ready`), `apg-diag`'s three Up. **Not measured**: whether a cached rebuild moves the index id on THIS workstation (D2497 is the host's containerd store) -- B1 is the measurement. | **0271**, **0276** |

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

**Two new families, `PLAN` and `USE`** (the stage plan's proposal, D691; `INS`
is Session 42's): the regex at `tests/contract/test_acceptance_registry.py:123`
gains `PLAN|USE`, and the family comments gain one sentence after `:122`:
*Session 41 (ADR 0274-0276) adds `PLAN` for plans and entitlements and `USE`
for usage samples, notifications and idle sleep.* **Seventeen requirements,
seventeen claims, all `target_session: 41`, all P0 — ten offline, six external,
one host.** Node ids below are **proposed; Run 9 writes what the runs actually
wrote**, read out of the tree with `pytest --collect-only -q` (D1236, D2129).
Registry entries are committed by Run 9 with the constant (D690), under **`#
Session 41 (ADR 0274-0276)`**.

| Requirement | What it states | Offline node ids (proposed) | Live half |
|---|---|---|---|
| `BR-BACKUP-002` | The backups reading is computed from the producer's own printed block over a real `pgbackrest info`: `earliest` = the oldest stop + 1 s; every key the reading takes from `info` is a key `backup_state` returns; a `failing` repository reads `problem`, not unknown | `tests/contract/test_backups_reading_from_the_producer.py::test_the_window_comes_from_the_producers_real_output`, `::test_every_key_the_reading_takes_is_printed`, `::test_a_failing_repository_is_a_problem_not_unknown` | — (`backups_reading_repaired`) |
| `BR-START-001` | A branch's image is resolved at every start from its recorded tag and content digest; an orphaned id is never handed to compose; changed content refuses with a reason and records `stopped`; the reconciler keeps the child's output and the record its reason; `apg-diag containers` lists a branch's containers | `tests/contract/test_branch_start.py::test_a_start_resolves_the_image_from_the_tag_and_digest`, `::test_changed_content_is_refused_with_a_reason`, `::test_the_reason_is_recorded`, `tests/contract/test_reconciler_dispatch.py::test_the_branch_start_keeps_its_output`, `tests/contract/test_apg_diag.py::test_containers_lists_branches` (grep for the existing `apg-diag` test module first; extend it if one exists) | — (`branch_start_repaired`) |
| `BR-DOOR-001` | `ready` is written only after both branch names verify through the edge, or with `door: pending` and the reason after `DOOR_SECONDS`; the branch budget sits inside its type's operation bound | `tests/contract/test_branch_door.py::test_ready_waits_for_both_names`, `::test_a_door_not_issued_in_time_is_pending_with_a_reason`, `tests/contract/test_restore_promotion_bound.py::test_a_branch_promotion_bound_sits_inside_its_reconciler_budget` (existing, made stricter) | — (`branch_door_ready`) |
| `PLAN-ENT-001` | `plans.PLANS` and `app.control_plan_limits` agree; the entitlement is checked before the slot; `plan_limit_reached` and `capacity_exhausted` each produced by its own reader with the other green; two concurrent creates in one organisation leave one row; `branch_limit_reached` reads the plan; the word occurs only in the entitlement readers | `tests/contract/test_plans.py::test_the_sql_limits_are_the_release_table`, `::test_the_entitlement_is_read_before_the_slot`, `::test_each_refusal_comes_from_its_own_reader`, `::test_two_concurrent_creates_leave_one_row`, `::test_the_branch_limit_reads_the_plan`, `tests/contract/test_control_projects.py::test_plan_limit_reached_is_produced_only_by_the_entitlement_readers` (replaces `test_no_string_produces_plan_limit_reached`) | — (`plan_entitlements`) |
| `PLAN-API-001` | `/v1/plans` and `/v1/organizations/{org}/plan` serve both plans with every entitlement, `enforced` and its reader, and the beta sentence; Premium `unavailable_during_beta`; interest recorded once per organisation and plan; no route writes a plan or a limit | `tests/contract/test_plans.py::test_the_plans_route_says_what_is_enforced`, `::test_premium_is_unavailable_and_interest_is_one_row`, `::test_no_route_writes_a_plan_or_a_limit` | — (`plan_api`) |
| `PLAN-CLI-001` | `apg plan show\|list\|notify-me`; `apg usage show`; `apg notifications list`; `apg project idle-sleep`; `apg usage` is a customer command and `doctor --reading usage` stays the operator's | `tests/contract/test_control_cli.py::test_plan_usage_and_notifications_dispatch_to_the_customer_cli`, `::test_idle_sleep_names_the_backup_consequence`, `tests/contract/test_cli_contract.py::test_the_usage_verb_is_the_customers_and_the_reading_is_the_operators` | — (`plan_usage_cli`) |
| `USE-SAMPLE-001` | The sampler reads each figure through the doctor's container reads; a figure not read is `NULL` and named; a sleeping project's sample says so; agent calls and workflow runs are counted from durable rows since the previous sample; only `control_record_usage` writes a sample, granted to nobody | `tests/contract/test_usage_sampler.py::test_each_figure_is_read_or_named_unread`, `::test_a_sleeping_project_is_sampled_as_sleeping`, `::test_calls_are_counted_from_durable_rows`, `tests/contract/test_control_usage.py::test_no_role_but_the_reconciler_writes_a_sample` | — (`usage_sampler`) |
| `USE-API-001` | The usage document: a counter's increases summed with resets read; samples expected vs present; active and sleeping seconds from the history; a window with no sample `could_not_determine`; a foreign and a missing project answer alike | `tests/contract/test_control_usage.py::test_a_counter_reset_is_read_not_subtracted`, `::test_seconds_come_from_the_history`, `::test_an_empty_window_is_not_zero`, `::test_a_foreign_and_a_missing_project_answer_alike` | — (`usage_api`) |
| `USE-IDLE-001` | The setting's values; the request function inserts one `project.sleep` with `origin = idle`, attributed to the setter, only with every sample present and quiet; a missing or unread sample, an open operation or a recent wake defer it; the origin CHECK refuses `idle` on any other type | `tests/contract/test_idle_sleep.py::test_a_quiet_window_requests_one_sleep`, `::test_a_missing_sample_is_not_idle`, `::test_a_recent_wake_restarts_the_window`, `::test_the_request_names_the_member_who_set_it`, `::test_idle_is_only_a_sleep` | — (`idle_trigger`) |
| `USE-NOTIFY-001` | Every finished operation writes one notification in the same transaction; the templates interpolate no result member; the finish body is 0004's plus the insert; a limit notice at most once a day; foreign organisations answer `404` | `tests/contract/test_notifications.py::test_a_finished_operation_writes_one_notification`, `::test_no_template_carries_a_result_member`, `::test_the_finish_body_is_unchanged_but_for_the_insert`, `::test_a_limit_notice_is_daily`, `::test_a_foreign_organization_reads_nothing` | — (`notifications`) |
| `LIFE-LIVE-005` | Session 41's lifecycle on `slot5-prod` at the deployed commit, in a new organisation: every accepted type ran, the resizes decided by their reading, the export holds `app`, `api`, `public`, the slot's own route AND pooled name probed through every window, a second creation in the same organisation after the deletion refused `capacity_exhausted {no_slot}` with no row | — | `tests/external/test_session41_reearning.py::test_every_accepted_type_ran_on_the_slot`, `::test_the_resizes_followed_the_admission_reading`, `::test_the_export_holds_the_three_customer_schemas`, `::test_both_routes_were_probed_through_every_window`, `::test_the_second_creation_after_the_deletion_was_refused_by_capacity` (external `lifecycle_third_trial_live`) |
| `PLAN-LIVE-001` | Through `/v1` with no SSH: both plans read; the probe organisation, holding `slot3-prod`, refused `plan_limit_reached` with no row while a slot was `ready`; Premium's interest recorded once | — | `tests/external/test_session41_reearning.py::test_the_plans_were_read`, `::test_the_second_project_was_refused_by_the_plan_while_a_slot_was_ready`, `::test_interest_was_recorded_once` (external `plans_live`) |
| `USE-LIVE-001` | `slot5-prod`'s and its organisation's usage read while it lived: samples present, its database bytes read, its requests increased under the probe, its unread figures named | — | `tests/external/test_session41_reearning.py::test_the_slots_usage_was_read`, `::test_the_organizations_usage_holds_the_slot` (external `usage_live`) |
| `USE-LIVE-002` | Idle sleep on `slot5-prod`: set to 15, the probes stopped, the reconciler requested one `project.sleep` with `origin = idle` attributed to the setter within the window plus two intervals, both names refused while asleep, then woken | — | `tests/external/test_session41_reearning.py::test_the_idle_slot_was_put_to_sleep_by_the_reconciler`, `::test_the_idle_sleep_closed_both_doors` (external `idle_sleep_live`) |
| `USE-LIVE-003` | The lifecycle organisation's notifications: one per finished operation, the idle sleep's naming its cause, no notification text holding the export's URL or any result member | — | `tests/external/test_session41_reearning.py::test_every_finished_operation_was_notified`, `::test_no_notification_carries_a_secret` (external `notifications_live`) |
| `BR-LIVE-003` | From the workstation with no SSH, on `slot3-prod`: the backups surface reads a window (D2501 repaired); an expiring branch deleted by the trigger; a branch at a point holds the first row and not the second; migrated over its direct name; the parent's password refused; `ready` reached with `door: ready` and the names answering at once (D2503); a second branch refused `branch_limit_reached` within the record's whole window; reset; deleted, names refused | — | `tests/external/test_session41_branches.py::test_the_backups_surface_reads_a_window`, `::test_an_expired_branch_was_deleted_by_the_reconciler`, `::test_the_branch_holds_the_point_before_the_change`, `::test_ready_meant_the_door_answered`, `::test_the_parents_password_opens_no_branch_door`, `::test_the_second_branch_was_refused_before_a_row`, `::test_a_deleted_branch_has_no_door`, `::test_this_module_uses_no_ssh` (external `branch_retrial_live`) |
| `BR-LIVE-004` | On the host: the branch bounded, its configured archive command `/bin/false` with archiving off, charged, the parent untouched, **back by itself after the reboot** with its image resolved at start, listed by `apg-diag containers`, nothing left after the deletion | — | `tests/deployment/test_session41_branch_host.py::test_the_branch_is_bounded_and_configured_not_to_archive`, `::test_the_branch_is_charged`, `::test_the_parent_was_untouched`, `::test_the_branch_came_back_by_itself_after_the_reboot`, `::test_the_diagnosis_account_sees_the_branch`, `::test_a_deleted_branch_left_nothing` (host `branch_host_retrial_live`) |

**Expected counts** — Run 9 counts them from the tuples, never from this prose
(D1628): requirements **360 → 377**, `CLAIMS` **267 → 284**, `OFFLINE_CLAIMS`
**111 → 121**, ADRs **273 → 276**.

**Claims** (`src/agentic_postgres/evidence_claims.py` `CLAIMS`, a block
commented *Session 41 (ADR 0274-0276)*): offline — `backups_reading_repaired`,
`branch_start_repaired`, `branch_door_ready`, `plan_entitlements`, `plan_api`,
`plan_usage_cli`, `usage_sampler`, `usage_api`, `idle_trigger`,
`notifications` — **these ten in `OFFLINE_CLAIMS`**, with the per-session
assertion in `test_session_forty_one_gate_modes.py` (D1237: assert THESE are in
the set, never its size). External — `lifecycle_third_trial_live`, `plans_live`,
`usage_live`, `idle_sleep_live`, `notifications_live`, `branch_retrial_live`.
Host — `branch_host_retrial_live`. `CLAIM_INTRODUCED_IN` gains a row at 41 for
each.

**Existing entries that move** (each a passing proof made stricter or widened
to a measured set, never weakened — CLAUDE.md §6, under the ADR named):

- **The lifecycle and branch records** (D2518): `RECORD_SESSIONS` →
  `{38, 39, 40, 41}`; `record39` → `(39, 40, 41)`; `record40` → `(40, 41)` and
  `project_key` matched by `slot.SLOT_KEY` and not `slot3-prod`; the two branch
  fixtures → `session in (40, 41)`; node ids unchanged. **D2505 and D2506's
  repairs land in the Session 40 modules too** (stricter: a measured expected
  value; a window that cannot start late).
- **CTL-OPS-001**: `test_only_credential_rotate_is_accepted_and_the_eleven_are_executed`
  → **`test_exactly_the_eleven_executed_types_are_accepted`** at the bump (the
  name Session 40 used; the registry's node id moved in the same commit, D1119).
- **LIFE-CAP-001**: `test_no_string_produces_plan_limit_reached` → **replaced**
  by `test_plan_limit_reached_is_produced_only_by_the_entitlement_readers`
  (ADR 0274; listed under PLAN-ENT-001 and kept under LIFE-CAP-001 — the
  registry lists it in both, as it lists shared proofs today; grep the registry
  for a node id listed twice first and follow that precedent, else name it
  under PLAN-ENT-001 only and record the choice).
- **BR-DISPATCH-001 / OPN-DISPATCH-001**: the closed set of SQL the reconciler
  runs widens by the three new calls (D2531).
- **BR-CTL-001**: `test_a_second_branch_is_refused_before_a_row` reads the
  limit from the plan (the value is still 1).
- **The three drill proofs** (D2498): the image pre-check.
- **`THR-*` table rows**: four added in Run 9 (Run 1's list); none removed.

**New environment gates: none.** The live modules read the existing
`APG_CONTROL_OUTPUTS`, `APG_CONTROL_PROBE_FILE`, `APG_LIFECYCLE_RECORD_FILE`,
`APG_BRANCH_RECORD_FILE`, `APG_LIVE_HOST`, `APG_LIVE_SLOT_OUTPUTS`,
`APG_HOST_MANIFEST` (roster `tests/conftest.py:86-225`). If a run finds it needs
one, it is a row and a roster line in that run.

---

## 4. Irreversible operations

| Operation | Where | What makes it safe |
|---|---|---|
| The control set's `0008` frozen into `projects/control/migrations/released.lock.json`, and its proposal committed | Run 4 | `bin/migrate.sh --project project.control.example.yaml freeze-lock`; the proofs apply the release set then the control set's eight as `migration_user` before the freeze; `AP900` down; the proposal by the product's own `propose` (ADR 0243); no released migration (D912) |
| `CURRENT_SESSION` 40 → 41; `VERSION` 1.18.0 → 1.19.0; sixteen Ledger rows → `trial`; three targets moved | Run 9 | All-or-nothing (D690); `README.md:7` and the `--session 40` / `--through-session 40` literals on the documented path moved and counted per file (D678/D1484); the `trial` rules (ADR 0261) |
| `bin/session-41-check.sh` | Run 9 | Derived from 40's by diff (D1482); header and usage rewritten whole (D1488); **no flag added**; `SHELL_COMMANDS`; `chmod 755` before `git add` |
| The stage plan amended for the split | Run 1 | A documentation edit recorded as D2510; the old Session 42 text kept under its new number |
| **Three grey A records for `slot5-prod`; its provider resources** (an Infisical project and identity, two R2 buckets and tokens, one B2 bucket and key) | Sheets P1, SL1 (Run 10) | As for `slot4-prod` (Session 40 SL1); `--plan` read before `--apply`; the credential shredded (D2061) |
| **`slot3-prod` redeployed at 1.19.0 by `slot.sh redeploy`** | Sheet R2d (Run 10) | The verb's fourth run; the reconciler stopped; admission read; the doors' certificate kept |
| **A new organisation created by the probe account** | Run 11 step 1 | Through `/v1` (`POST /v1/organizations`, ACCOUNT); kept after the trip (organisations are never deleted, D2065/D1986) — recorded in §10 |
| **`slot5-prod` created, credentialed, slept (by request AND by idleness), woken, resized, exported and deleted** | Run 11 | Through `/v1` only, after V1 and X0 passed at the same commit (D2448); one operation at a time; the probes running except during the idle window |
| **`slot5-prod` consumed** | Run 11 | The tombstone; the repository kept (ADR 0187) |
| **Branches of `slot3-prod` created, reset, expired and deleted; production certificates for `dev` and `tmp`'s names** (one each if rig 40b's reuse holds) | Run 11 | `slot3-prod`'s doctor read before and after; the parent's volume, `instance_uuid` and timeline read before and after |
| `slot5-prod`'s Infisical identity revoked | Sheet SL4 (after the tag) | `slot.sh revoke` with the operator's credential, shredded after; the directory removed by the verb itself (D2405) — read absent, never `rmdir`ed by hand |
| The reboot | Sheet B1 | With `slot3-prod`'s branch live; every unit, the branch and `apg-diag` read before the sweep |
| Tag `1.19.0` on the deployed commit | Run 11 | After the merge exits 5 for `documented_path` only (§7); from the WORKSTATION (D2041) |

---

## 5. Build order, run by run

Each run ends with a `**Done.**` paragraph written by the executor: what was
measured, the numbers, the rows it added, and — for a code run — the CI verdict
by full SHA. The targeted modules run ONCE at the run's close and only a failing
module is re-run. `ruff format && ruff check` before every commit; `chmod 755
bin/*.sh bin/*.py deploy.sh` before every `git add` — **and every file an image
executes directly** (D2412); messages from a file with `-F`, ending with the
attribution line the session's system reminder gives. **Grep the plans for
every third party before measuring it.** **A run that renames, adds or removes
a test function runs `test_acceptance_registry` and `test_evidence_claims`**
(D1119); **a run that adds a module under `src/agentic_postgres/` runs
`test_repository_contract`** (D2114); **a run that adds or removes a `bin/`
command runs `test_cli_contract` and `git add`s it first** (D1014); **a run that
adds a `document[...]` read to a `bin/` command runs `test_container_selectors`**
(D1184); **a run that touches a documentation page runs
`test_documentation_index` and `test_session12_documented_path`**; **every new
test module carries `pytestmark` before its first test** (D1240), and the
sweep-selector guard (D1242) AND `test_environment_gates` join the targeted list
of any run that adds a module — **read a model dict with `.get("APG_…")`, never
`x["APG_…"]`** (D2381). **Docker-backed modules reuse
`tests/contract/control_cluster.py`** (`docker rm -fv`, D2098). **Every external
fixture that holds a password, verifier, token or TOTP seed returns
`tests/external/redaction.py`'s `Secret`** (D2420). **Never print a live log's
failure body without filtering it by the secret VALUES** (D2416). **Every
mutation battery** follows CLAUDE.md §1: `PYTHONDONTWRITEBYTECODE=1`, snapshot
to `/tmp` and restore by copy with `cmp`, anchors pre-flighted (a miss fatal),
a control the mutation cannot reach, and *how* each failed (`FAILED` vs
`ERROR`).

### Run 1 — the rigs, Sheet E0, the threat list, ADRs 0274–0276, the split

**Documentation only. Push, say it is pushed, read NO CI verdict** — except
that, because `docs/threat-model.md`, `docs/decisions/README.md` and
`docs/plans/*.md` are parsed by contract tests, run `test_acceptance_registry`,
the ADR-index test (`grep -rln "decisions/README" tests/contract/`),
`test_documentation_index` and `test_mcp_catalog` once before the push.

Rigs live in WSL `~/s41/run1/rig41/` and are copied to the scratchpad. **Each
names its control and is recorded with what it printed.** Each removes what it
made (`docker rm -fv`, `docker network rm`, `docker volume rm`), read back with
`docker ps -a | grep -c rig41` = 0 and `docker volume ls | grep -c rig41` = 0.

1. **Rig 41b — the door's readiness** (D2515): Session 40's rig 40b (WSL
   `~/s40/run1/rig40/`, Pebble + `pebble-challtestsrv` + a Docker-provider
   Traefik with the edge's static shape) as the template. A Python function —
   the one Run 3 will put in `bin/branch-runtime.py` — opens `127.0.0.1:<the
   rig's postgres entrypoint>`, sends `SSLRequest` (`struct.pack("!ii", 8,
   80877103)`), expects `b"S"`, wraps with `ssl.SSLContext(PROTOCOL_TLS_CLIENT)`
   loaded with Pebble's root (the host uses the system store), SNI = the name,
   `set_alpn_protocols(["postgresql"])`. Cases: (1) before the router's
   certificate is issued → verification fails (Traefik's default certificate);
   (2) after → verifies, both names; **control** (3) a name with no router →
   never verifies within 60 s. Record the time from router creation to the first
   verified handshake (the number `DOOR_SECONDS = 180` is set against — if it is
   above 60 s, raise the bound to three times it and say so).
2. **Rig 41c — a branch started after a rebuild** (D2513): rig 40f
   (`~/s40/run9/rig40f`) as the template, on this workstation's containerd
   store. Build a stand-in parent image `rig41-parent:latest` from
   `services/postgres/Dockerfile` (the pinned base), create a container from
   it, read its `ImageManifestDescriptor.digest` and `Config.Image`; rebuild
   **unchanged** → the old index id no longer resolves (`docker image inspect
   <old id>` fails), `docker image inspect --platform linux/amd64
   rig41-parent:latest` reads the SAME platform digest → `image_for(tag,
   digest)` (the draft function) returns the new index id and `docker run` of it
   starts. **Control**: rebuild with one changed layer (`RUN true` appended) →
   the platform digest differs → refused. Record the three digests.
3. **Rig 41d — the control set's `0008` draft** (D2521, D2525, D2526): the
   control set `0001–0007` applied to a `control_cluster.py` cluster, then a
   draft `0008` — (a) two `project.create` requests for one organisation from
   two connections, the second blocked on the organisation's row lock, then
   refused `AP409: plan_limit_reached` → one row; **control**: two
   organisations → two rows; (b) `control_request_idle_sleep` with a full quiet
   window → one `project.sleep` row `origin = idle`; **control**: the same
   window with one sample missing → no row; (c) `control_finish_operation` →
   one notification in the same transaction; **control**: a rolled-back finish
   → no notification.

**Sheet E0** (the operator; reads only — `s41-e0.sh` written by the agent,
shipped to `/home/op`, sha256 printed; it writes `/home/op/s41-e0/` 0700 and
`/home/op/s41-e0.txt`): `free -m`; `docker stats --no-stream --format
'{{.Name}} {{.MemUsage}}'`; **the backups producer, both shapes**: `sudo
bin/backup.sh --outputs /etc/agentic-postgres/projects/slot3-prod/outputs.json
info --json > /home/op/s41-e0/backup-info.json` and the raw `pgbackrest
--stanza=slot3-prod --output=json info` run **exactly as `bin/branch-runtime.py`
`read_window` runs it** (`:239-242`; the script copies that argv) into
`/home/op/s41-e0/pgbackrest-info.json`, both `chown op` 0600; **the idle
signals on `slot3-prod`, at rest and with a control**: the store query
`sum by (code) (traefik_service_requests_total)` through the store container
(`probe_store`'s `wget` argv, `doctor.py:985-993`) at T0, T0+15 min and T0+30
min with **no traffic from the workstation**, then ONE `curl -s -o /dev/null
-w '%{http_code}'` to `slot3-prod`'s app route and one `psql` through
`pool.slot3…` by the agent (announced on the sheet), then a fourth read; and at
each read, `SELECT usename, state, backend_start, state_change FROM
pg_stat_activity WHERE usename IN (<the two customer roles, derived by
naming.database_roles("slot3-prod") — the script prints the names it used>)`;
`sudo bin/doctor.sh --project slot3-prod` (twelve checks — read `--help`
first); `sudo bin/doctor.sh --project slot3-prod --reading usage`;
`systemctl show -p NRestarts agentic-postgres-reconciler`; `sudo ls -la
/etc/agentic-postgres/branches/`. **The agent then copies
`/home/op/s41-e0/*.json` to WSL `~/s41/e0/` 0600 and reads both whole** before
Run 2 commits either as a fixture (D2512). **If the counter's sub-400 part moved
between the quiet reads, D2525's signal is wrong: §9's stop.**

**The threat list made specific** (D2527): hosted items #4's entitlement half
(`:212-218`), #5 (`:219-222`) and #10's usage/notification half (`:247-255`)
rewritten with the negative test each owes BY NODE ID (§2), plus **one new
item**: *a trigger acts on a stale or forged sample* (USE-IDLE-001's
`test_a_missing_sample_is_not_idle`, USE-SAMPLE-001's
`test_no_role_but_the_reconciler_writes_a_sample`). Item #9 re-labelled
*(Session 42)*. They stay list items until Run 9 moves them into the table as
`THR-PLAN-BYPASS`, `THR-USE-TAMPER`, `THR-USE-LEAK`, `THR-USE-IDLE`.

**ADRs** (each indexed in `docs/decisions/README.md`): **0274** plans and
entitlements — the release table and its SQL twin, every number with its
reason, what is enforced and by which reader, the order before the slot, the
lock, `branch_limit_reached` reading the plan, *Notify me*, no override verb,
the guard replaced (D2519–D2522). **0275** usage samples and in-app
notifications — the figures and their sources, `NULL` as *not read*, counters
as read, seconds from the history, the aggregation, the notification written in
the finish's transaction from a template, the daily limit notice (D2523,
D2524, D2526). **0276** idle sleep is a trigger — the setting, the signal, the
decision in the control database, fail closed, `origin = idle`, the backup
consequence said, supersedes ADR 0186 for this field and amends ADRs 0272 and
0256 (D2525, D2531, D2534). **Amended**: ADR 0271 (the image resolved at start;
`ready` waits for the door; the reason kept; the budget, D2513–D2516), ADR 0273
(the reading through the producer's printed block, D2512), ADR 0186 (status:
superseded for idle sleep by 0276), ADR 0272 (status: a second requested kind,
0276).

**The split** (D2510): `docs/plans/stage-5-plan.md` amended as D2510 says —
the Status block's `SESSIONS` line (*"36-43 (D1945, D2510) … 41 (the repairs,
the re-earning, plans, usage, notifications, idle sleep) PLANNED; 42
(ClickStack, insights, monitoring; the OVH upgrade first) and 43 (the console,
the journey, the release) unplanned"*), §3's table, §5 *Session 41*'s amended
paragraph, the old *Session 42* retitled *Session 43*, a new *Session 42*
section holding the moved Builds/Must not/Measures/Closes text verbatim from
*Session 41* (ClickStack, `pg_stat_statements`, Query Insights, monitoring, the
observability `THR-*` rows, `every_service_bounded_live` re-run), §7's table.
**Do not rewrite anything else in the stage plan.**

**Done.** 2026-10-16, documentation only (no CI read). Rows **D2536–D2539**.
Rigs in WSL `~/s41/run1/rig41/` (copied to the scratchpad), each cleaned up
(0 `rig41` containers, networks, volumes, images left):
**Rig 41b** (`rig41b.sh`/`rig41b.txt`): both branch names verified through
Traefik's `postgres` entrypoint **3.0 s** after their containers were created;
before issuance the edge **closed the handshake** (`sniStrict`, no default
certificate) — the same EOF as the control's name with no router, which never
verified in 60 s; the wrong root read `unable to get local issuer certificate`
→ EOF-after-`S` reads *pending* (D2537); `DOOR_SECONDS` 180 stays.
**Rig 41c** (`rig41c.py`/`rig41c.txt`, Docker 29.5.2, containerd store, the
real `services/postgres/Dockerfile`): platform digests **1** `sha256:2794179a…`
(the container's, recorded at create), **2** `sha256:2794179a…` (after an
unchanged rebuild: the index id moved `d677c532…` → `82700cbc…`, the old id no
longer resolves), **3** `sha256:7cbc07f1…` (after `RUN true`); the draft
`image_for` chose the new index and `docker run` of it started; the control was
refused *"the parent's image changed since this branch was made … reset the
branch"*. As planned.
**Rig 41d** (`rig41d.py`, `rig41d_0008.sql`, `rig41d.txt`): the organisation
row's `FOR UPDATE` locks NOTHING without an UPDATE policy (D2538); with a
lock-only policy the second creation waited **3.2 s** then `plan_limit_reached`,
one row; control two organisations, two rows, 0.1 s. The idle request: one
`project.sleep` `origin = idle` attributed to the setter; control (a sample
missing) none; `idle` on a `project.wake` refused. The finish: one
notification; control (rolled back) none.
**Sheet E0** (`/home/op/s41-e0.sh` sha256 `6f8c9e79…`, `s41-e0.py`
`48c88f0e…`; transcript and the four JSON files in WSL `~/s41/e0/` 0600, read
whole — pgBackRest prints the cipher's NAME only, no secret): `free -m`
available **5,129 MiB**; `backup.sh info --json` exit 0, 352 bytes, keys
`last_full_backup_at, last_full_backup_label, latest_recoverable_time, mirror,
stanza_created, status, wal_archived_count, wal_failed_count` — **no
`oldest_backup_stop`** (D2501 confirmed on the producer's real output); the raw
`pgbackrest info` (read_window's argv) exit 0, 3,032 bytes, one full
`20261012-102807F` (stop 1791801566 = 2026-10-12T10:39:26Z) and four
incrementals, repository 4,407,456 bytes — Run 2's fixture; the printed block's
`mirror: not_observed` is by design (the reading takes the mirror from the copy
record, D2461). The idle signals (D2539): sub-400 **8/8/8** over 30 quiet
minutes, no customer backend; after the control (`/api/app` 404, `/api/rest/`
200, one `psql`) `200`: 9, `404`: 1, one idle `customer_app` backend stamped at
the query — **no stop**. `doctor --project slot3-prod` **12 ok**; `doctor usage`
3 ok, 1 unknown (`tool_calls_total`, the per-process series, D1643; database
10,548,927 bytes, repository 6,398,256); reconciler active, `NRestarts=0`;
`/etc/agentic-postgres/branches/` empty.
**Documents**: `docs/threat-model.md` items 4, 5 and 10 made specific by node id,
9 re-labelled Session 42, **13** added (a trigger on a stale or forged sample);
**ADRs 0274, 0275, 0276** written and indexed; **0186, 0256, 0271, 0272, 0273**
amended (status lines and index cells); `docs/plans/stage-5-plan.md` split as
D2510 says (Status `SESSIONS`, §3's table and ordering 4, §5 *Session 41*'s
amendment, a new *Session 42*, *Session 43* renumbered, §7's table).

### Run 2 — D2501 repaired: the backups reading from the producer (`src/`, `bin/`)

**Read first**: `src/agentic_postgres/backup_report.py:73-171, :342-380`;
`bin/backup.py:315-337, :451-497`; `bin/reconciler.py:1299-1334`;
`src/agentic_postgres/reconciler_dispatch.py:612-647`;
`services/auth-api/app/control_service.py:942-997`; the readers of
`backup_state` listed in §0 (each re-read: does it index by key, or compare the
whole dict? A whole-dict comparison is a test to update with the two new keys,
recorded).

1. `backup_state` returns two more keys, `oldest_backup_stop` and
   `repository_bytes`, from the summary it already takes.
2. `backups_of` parses stdout on exit 0 **or** `EXIT_REFUSED` (import the
   constant's value from `bin/backup.py`'s source by name — never retype 5 — or
   move it into `src/agentic_postgres/backup_report.py` if it is not importable
   there, recorded); `info=None` only when the output does not parse.
3. The fixture `tests/fixtures/pgbackrest/info-slot3-prod-2026-10.json` (E0's
   raw capture, read whole first) and the new module
   `tests/contract/test_backups_reading_from_the_producer.py` (§2's three
   tests; `pytestmark` first). The class guard reads both functions' ASTs: the
   string keys `backups_reading` reads through `info.get(...)`/`info[...]` ⊆ the
   string keys `backup_state` returns.
4. **D2498**: the three drill proofs call `restore_drill.runnable_image` on the
   live container first.

**Battery** (`~/s41/run2/battery2.py`): (a) remove `oldest_backup_stop` from
`backup_state` → the producer test FAILS on `earliest`; (b) revert
`backups_reading` to read a key `backup_state` does not print (`"oldest_stop"`)
→ the class guard FAILS; (c) restore the return-code-0-only parse → the
`failing` test FAILS; **control**: a mutation of `earliest_point`'s `+1 s` to
`+2 s` → only `test_backup_repository_report`'s existing D2465 test and the
producer test fail (both readers of the rule), the class guard stays green.

**Targeted once**: the new module, `test_backup_repository_report`,
`test_wal_archiving_signal`, `test_backup_mirror`, `test_backup_plane`,
`test_backups_surface`, `test_reconciler_dispatch`, `test_restore_promotion_bound`,
`test_repository_contract`, the sweep-selector guard, `test_environment_gates`,
`test_acceptance_registry`, `test_evidence_claims`. Commit, push, read CI.

**Done.** 2026-10-16. Rows **D2540** (step 1 as written was impossible: `info
--json` is the deployed document's closed block — the window comes from `usage
--json` instead) and **D2541** (a sleeping slot raised out of the reconciler's
loop — found by this run's proof, repaired). Code:
`backup_report.usage_block` + `INFO_FAILING_EXIT`; `bin/backup.py` `verb_usage`
prints the block, `verb_info` returns the named exit;
`reconciler_dispatch.backups_reading(…, usage=…)` reads the oldest stop from
`usage` and skips an absent check; `bin/reconciler.py` `backups_of` runs `info`
and `usage`, parses `info` on 0 or the failing exit (`_json_of`); `bin/backup.sh`'s
header says what `usage --json` now carries. Fixture
`tests/fixtures/pgbackrest/info-slot3-prod-2026-10.json` = E0's raw capture
(read whole: the cipher's NAME only, `system-id` an identifier; oldest stop
1791801566 = 2026-10-12T10:39:26Z). New module
`tests/contract/test_backups_reading_from_the_producer.py` (`pytestmark` first):
`test_the_window_comes_from_the_producers_real_output` (earliest
2026-10-12T10:39:27Z, read from the raw file independently),
`test_every_key_the_reading_takes_is_printed` (AST over `backups_reading`: `info`
⊆ `backup_state`, `usage` ⊆ `usage_block`), `test_a_failing_repository_is_a_problem_not_unknown`
(`[failing-is-a-problem]` and its control `[control-an-unreadable-exit-is-unknown]`,
through `backups_of`), `test_a_sleeping_slot_is_read_without_raising` (D2541).
**D2498**: `tests/recovery/conftest.py::require_a_runnable_image` (the drill's own
`restore_drill.runnable_image` on the live container; `pytest.fail("the drill's
image does not resolve: …")`), called before the drill in `test_future_pitr`,
`test_session32_workflow_restore`, `test_session34_delivery_restore`
(collect-only: 9 collected; they run on the host). **Battery**
`~/s41/run2/battery2.py` (output `battery2.txt`) **6/6, every kill a `FAILED`**:
(a) `usage_block` without the oldest stop → window, guard and both exit tests;
(b) the reading takes `"oldest_stop"` → guard + window; (b2) D2501's original
(the window from `info`) → guard + window; (c) `info` parsed on 0 only → the
failing test alone (its control green); (d) D2541's old line → the sleeping
test; **control** `earliest_point` +2 s → the window test and
`test_backup_repository_report::test_the_window_starts_at_the_oldest_backups_stop`
(D2465) only, the class guard green; files restored byte-equal (`cmp`). One
expectation of mine was wrong at first (mutation (a) also fails the exit
tests, which read the window too) — corrected, nothing in the product moved.
**Targeted once**: the 13 modules above plus `test_cli_contract` — **1,318
passed**. ruff clean. **Code `eab8d9b79404f2e306ea4b9dbcff6c30c8586593`, CI run
38894677679 `contract` SUCCESS** (11:34–11:55Z, read by full SHA).

### Run 3 — D2504 repaired, the door, the budget, the diagnosis (`src/`, `bin/`)

**Read first**: `src/agentic_postgres/branch_plan.py:119-291, :400-405`;
`src/agentic_postgres/restore_drill.py:161-221`; `bin/branch-runtime.py:96-99,
:172-179, :234-270, :453-466, :588-599, :689-945`; `src/agentic_postgres/branch_record.py`
whole; `infra/branch/compose.yaml` whole; `bin/reconciler.py:137-154, :383-426,
:1299-1306, :1386-1428`; `bin/apg-diag.sh` whole; `bin/cloud.py`'s `--wait`
bound for branch verbs (grep `wait` in `:1056-1266`).

1. **`restore_drill.image_for(tag, digest, docker) -> str`** (D2513): the tag's
   current index id iff `docker image inspect --platform linux/amd64 <tag>`'s
   platform manifest digest equals `digest`; else `DrillError` with the reason;
   an unreadable inspect says *could not determine*. `runnable_image` unchanged.
2. **`branch.json` gains `image_tag`, `image_digest`, `reason`, `door`**
   (`branch_record.py`; a record without the first two — written by 1.18.0 — is
   read as *"made before 1.19.0: reset it"* and refused at start with that
   reason, never guessed). `command_create`/`command_reset` record them from the
   parent's container; **`command_start` and the persistent phase resolve
   through `image_for` and rewrite `branch.env` before `compose up`**.
3. **The door** (D2515): `door_ready(host, timeout)` from rig 41b in
   `bin/branch-runtime.py` (or `src/agentic_postgres/branch_door.py` if it is
   pure enough to test without a socket — a module under `src/` runs
   `test_repository_contract`); `create`/`reset`/`start` write `ready` only after
   both names verify or `DOOR_SECONDS` elapse (`door: pending` + reason).
4. **The budget** (D2516): `OPERATION_SECONDS_BY_TYPE`, `CHILD_SECONDS`,
   `PROMOTION_SECONDS`; every reader of `OPERATION_SECONDS` updated (grep, D979);
   the guard reads the type's bound.
5. **The output kept** (D2514): `start_branches` through a 0600 log and the last
   line logged; every `print` in `bin/branch-runtime.py` read for secrets
   (recorded: *"N prints, none carries a secret"*).
6. **`apg-diag containers`** lists branches (D2514); its contract test (grep
   `apg-diag` under `tests/contract/` for the existing module).
7. **D2505/D2506 in the Session 40 modules** (the `(disabled)` value and the
   configured argv; `window_started_at` with the fallback).

**Battery**: (a) `command_start` without the rewrite → `test_a_start_resolves_…`
FAILS; (b) `image_for` comparing the index digest instead of the platform one →
the rig-shaped fake FAILS; (c) `ready` written before the door → `test_ready_waits_…`
FAILS; (d) `_quiet` restored at `start_branches` → `test_the_branch_start_keeps_its_output`
FAILS; **control**: a change to the pooler image's handling → none of the four
fail.

**Targeted once**: `test_branch_start` (new), `test_branch_door` (new),
`test_branch_runtime`, `test_branch_runtime_on_a_cluster`, `test_branch_plan`,
`test_runnable_image`, `test_restore_promotion_bound`, `test_reconciler_dispatch`,
the `apg-diag` module, `test_cli_contract`, `test_repository_contract`, the
sweep-selector guard, `test_environment_gates`, `test_acceptance_registry`,
`test_evidence_claims`. Commit, push, read CI.

**Done.** 2026-10-16. Row **D2542** (measured on the host first: the runtime's
own interpreter — uv CPython 3.12.13, OpenSSL 3.5.7 — finds the system store at
`capath=/etc/ssl/certs`; the draft and then the committed `branch_door.check`
read `pool.slot3…`/`direct.slot3…` `ready` and a no-router name `pending` via
`ssl.SSLEOFError`; the rulings: `image_platform` recorded beside the tag and
digest, `branch_record` schema 2 that still READS version 1, `SERVICES`
unchanged, `WAIT_SECONDS` 3,900, `reason`/`door` held in `branch.json` until
Run 4's columns). Code: `restore_drill.image_identity` + `image_for(tag,
digest, platform, docker)`; `branch_record` schema 2 (`image_tag`,
`image_digest`, `image_platform`, `door`, `reason`; `READABLE_VERSIONS` (1, 2),
`MADE_BEFORE_IMAGE_IDENTITY`, `DOOR_STATES`); new `src/agentic_postgres/branch_door.py`
(`check`, `wait`, `client_context`, `DOOR_SECONDS` 180, interval 5 s);
`bin/branch-runtime.py`: `identity_of`, `pin_image` (before the persistent
phase's and every start's `compose up`), `await_door` after `attach`,
`_failure` → `reason` on `failed`/`stopped`, `command_start` rewritten
(`stopped` + reason on a missing identity, a changed image or a compose
refusal; `ready` + door otherwise), `status` shows door and reason,
`PROMOTION_SECONDS` 2,400; `bin/reconciler.py`: `OPERATION_SECONDS_BY_TYPE`
(the three branch types 3,600), `CHILD_SECONDS["branch-runtime.sh"]` 3,300, the
deadline and its reason per type, `start_branches` through `_logged` (0600
`branch-start-<utc>.log`, the last line journalled); `bin/cloud.py`
`WAIT_SECONDS` 3,900 (+ `bin/operation.sh`'s usage line); `bin/apg-diag.sh`
`containers` lists `-- <key>_<branch> (branch)` by `branch.env`'s checked
Compose project. **D2505/D2506 in the Session 40 modules**:
`test_session40_branch_host.py` reads the configured `-c archive_*` argv
against `branch_plan.persistent_command()` and `SHOW archive_command =
(disabled)`; `test_session40_branches.py`'s refusal window starts at
`window_started_at`, else `started_at` (collect-only: 13 collected).
**Print audit** (step 5): 25 output sites in `bin/branch-runtime.py` — names,
states, instants, digests, admission lines and Docker's text through `_tail`
(verifiers redacted); none carries a secret. **Tests**: new
`tests/contract/test_branch_start.py` (5: the start resolves the new index over
a rig-41c-shaped daemon and `branch.env` names it at `up`; changed content
refused with no compose call; the reason recorded and cleared; a version 1
record read and refused; `image_for`'s answers, never the index descriptor) and
`tests/contract/test_branch_door.py` (8: the five readings, no connection,
`ready` only when both names verify, `pending`/`unknown` at the bound);
`test_branch_runtime.py` stricter (the create order now `… write_compose_state,
pin_image, persist … attach, door, record:ready`; the identity, `door` and the
failure's `reason` asserted); `test_reconciler_dispatch.py::test_the_branch_start_keeps_its_output`;
`test_diagnostic_surface.py::test_containers_lists_branches` (the real
`verb_containers` over a tmp root and a fake `docker`; control: an unchecked
project name is said and never reaches Docker);
`test_restore_promotion_bound` stricter (promotion < child < each type's bound
< the CLI's wait). **Battery** `~/s41/run3/battery3.py` **7/7, every kill a
`FAILED`**: (a) no env rewrite → the start test; (b) `image_for` without
`--platform` (the index digest) → the start and `image_for` tests; (c1) `ready`
without the door → the create-order test; (c2) `wait` on ANY name → the
both-names test; (d) the start's output not logged → the output test; (e) EOF
read as `unknown` → that reading's case; (f) a version 1 record guessed → the
version 1 test; **control** (the pooler image's handling) → all green; files
restored byte-equal. **Targeted once**: the plan's list plus
`test_capacity_probe`, `test_branch_expiry`, `test_container_selectors` and
Run 2's module — **1,290 passed** (3 min 29 s). ruff clean. **Code
`77af733fd984c45238593962069841a54d844f19`, CI run 38904957367 `contract`
SUCCESS** (13:03–13:25Z, read by full SHA).

### Run 4 — plans and the control set's `0008` (`services/`, `projects/control/`)

**Read first**: `projects/control/migrations/templates/0004-control-operations.sql:132-500`;
`0006-control-branches.sql` whole; `projects/control/migrations/manifest.json`;
`services/auth-api/app/compute_profiles.py` and `src/agentic_postgres/compute_profiles.py`
(the release-table pattern); `tests/contract/control_cluster.py`; ADR 0243.

1. **`services/auth-api/app/plans.py`** and **`src/agentic_postgres/plans.py`**
   (D2519): the table exactly as D2519 states it.
2. **`0008-control-plans-usage.sql`** (one template; `manifest.json` entry
   `control_plans_usage`, version `20261016120008` — read 0007's version format
   and follow it), holding: `control_organizations.plan`;
   `control_plan_limits` (seeded); `control_plan_interest`;
   `control_usage_samples`; `control_projects.idle_sleep_minutes` /
   `idle_sleep_set_by`; the origin CHECK widened; `control_branches.reason` /
   `door`; `control_notifications`; **re-created**: `control_request_operation`
   (the entitlement under the organisation's lock), `control_finish_operation`
   (0004's body + the notification insert), `control_record_branches` (the two
   new fields), `control_result_members` only if it must change (read 0006's
   note first); **new**: the three nobody-granted writers and the seven DEFINER
   readers/writers of D2533. Every function's `COMMENT` names its row (the
   set's habit). `AP900` down.
3. Applied by the proofs as `migration_user` after the release set and the
   control set's seven; then **`bin/migrate.sh --project
   project.control.example.yaml freeze-lock`** and **`bin/migrate.sh --project
   project.control.example.yaml propose --by <the executor's model name>`**
   (no dev environment may exist — `bin/dev.sh status` first).
4. Tests: `tests/contract/test_plans.py` (the SQL twin; the concurrency test on
   a real cluster), `tests/contract/test_control_usage.py` (writers granted to
   nobody; the aggregation), `tests/contract/test_idle_sleep.py`,
   `tests/contract/test_notifications.py` (including the body diff against
   0004's).

**Battery**: (a) drop the `FOR UPDATE` → the concurrency test FAILS (two rows);
(b) the idle function without the sample-count check → `test_a_missing_sample_is_not_idle`
FAILS; (c) a template interpolating `p_result` → `test_no_template_carries_a_result_member`
FAILS; (d) the seeded `projects_active` 2 → the twin test FAILS; **control**: a
change to `control_record_slots`' comment → none fail.

**Targeted once**: the four new modules, `test_control_branches`,
`test_control_projects`, `test_control_operations` (grep its name), `test_branch_expiry`,
`test_operation_types`, the control-set lock test (grep `released.lock` under
`tests/contract/`), `test_repository_contract`, the sweep-selector guard,
`test_environment_gates`. **Not pushed alone if** a test couples to Run 5's
routes (D2463's shape) — then push Runs 4+5 together and read CI at Run 5's SHA.

**Done.** 2026-10-16 — **committed, NOT pushed: it couples to Run 5** (D2543
(7)); Runs 4 and 5 go out together and CI is read at Run 5's SHA. Rows
**D2543** (the rulings) and **D2544** (the lint's reader loses a literal that
holds `--`). Commits: `11b86bc` (the code), `4ecf8f4` (lock), `1f534b4` (no
`--` in 0008's literals, D2544), `8af6239` (lock), `ba04673` (proposal
`cbbb1175`), `cbf9ab5` (the expiry constraint kept by name, idle's beside it),
`306342c` (lock re-frozen, 8 migrations, `follows_release_version`
20261003120039 computed, `verify-lock` agrees), `e32e470` (**proposal
`bba02721`**, replacing `cbbb1175`: lint passed, **47 migrations applied from
empty as `migration_user`**, surface empty, 12 destructive findings — 0008's
four: `control_operations_origin_check`, `control_operations_expiry_deletes_a_branch`,
`control_list_branches`, `control_get_branch`). Code:
`services/auth-api/app/plans.py` (D2519's table; `ENFORCED_IN_SQL`,
`BETA_SENTENCE`); `projects/control/migrations/templates/0008-control-plans-usage.sql`
+ its `manifest.json` entry (`20261016120008`, `control_plans_usage`): the
plan column, `control_plan_limits` (seeded 1/1, 3/3), the lock-only
`control_organizations_lock` policy, `control_request_operation` re-created
(the entitlement under the lock, raising `AP500` when it locked nothing),
`control_plan_interest`, `idle_sleep_minutes`/`idle_sleep_set_by` and
`control_projects_idle_sleep`, the origin constraints (one per kind),
`control_branches.reason`/`door`, `control_usage_samples`,
`control_notifications` (+ the daily limit-notice index),
`control_finish_operation` (0004's body + one marked block),
`control_record_branches` re-created, `control_list_branches`/`control_get_branch`
dropped and recreated wider; new: `control_record_usage`,
`control_request_idle_sleep`, `control_record_limit_notice` (granted to
nobody), `control_usage_document` (helper), `control_list_plans`,
`control_get_org_plan`, `control_register_interest`, `control_set_idle_sleep`,
`control_project_usage`, `control_org_usage`, `control_list_notifications`
(definer, granted to the identity service). **Tests** (all against a real
control cluster): `tests/contract/test_plans.py` (8: the twin, refused before
a row, two concurrent creations → one row + `plan_limit_reached` after a
> 2 s wait with a two-organisation control, the lock policy refuses an UPDATE
and a dropped policy is refused, the branch limit from the plan, interest one
row, no writer of a plan, the lock held across the count), `test_idle_sleep.py`
(9: a quiet window, no customer backend is quiet (D2539) with a busy control,
a missing sample, an unread sample, a moved counter, a recent wake, the
member named, idle only a sleep and the setting's values and roles, granted to
nobody), `test_notifications.py` (5: one per finish and none rolled back,
no result member or secret URL in a template (dynamic + static), the body diff
against 0004, the daily limit notice, a foreign organisation), `test_control_usage.py`
(6: granted to nobody, a counter reset, a gauge's newest read value, seconds
from the history, an empty window is not zero, foreign and missing alike);
`test_control_set.py`'s closed lists widened by exactly 0008's four tables and
eleven functions, its rendered-set count 7 → 8. **Battery** `~/s41/run4/battery4.py`
(output `battery4b.txt`) **PASSED round 2**: (a) the lock dropped → both lock
tests FAILED; (b1) no contiguity → the missing-sample test; (b2) no count
check → SURVIVED, as predicted (D2543 (4)); (c) a template with `p_result` →
the template and one-per-finish tests; (d) Free's limit seeded 2 → the twin,
the beyond-the-plan and the concurrency tests; (e) no backend read as busy →
the no-backend, quiet and missing tests; (f) unread ignored → the unread test;
(g) the notification block removed → the template and one-per-finish tests;
**control** (`control_record_slots`' comment in 0004) → all green; files
restored byte-equal. Round 1 found the lock probe weak (D2543 (3)). **Targeted**
(the plan's list with D2543 (5)'s two modules, plus `test_control_set`,
`test_project_migration_sets`, `test_change_proposal`, `test_proposal_gate`,
`test_migrations`, `test_auth_service_shape`, `test_reconciler_dispatch`,
`test_evidence_claims`, `test_acceptance_registry`): 735 passed, 4 failed —
two repaired (D2543 (6)) and re-run green with the lock and proposal modules
(188 passed); **the two left are D2543 (7)'s, Run 5's to repair**. A first
attempt was stopped by the harness for low memory while idle; re-run in the
foreground.

### Run 5 — the routes, the service, the codes (`services/auth-api/`)

**Read first**: `services/auth-api/app/control_service.py:600-1000`;
`control_routes.py:600-1130`; `control_roles.py` whole; `errors.py:200-280`;
`models.py` (the response models; grep `branch_limit_reached` `:729`); the
contract snapshot `contracts/control-openapi.canonical.json` and how it is
regenerated (grep `control-openapi` in `bin/` and `tests/contract/`).

1. `errors.PLAN_LIMIT_REACHED` (409, a control word, NOT in
   `OPERATION_ERROR_CODES`, D2469's rule).
2. `create_project`: the entitlement before the slot (D2521); `_branch_write`
   reads `plans` (the constant deleted).
3. Routes: `GET /v1/plans`; `GET /v1/organizations/{org}/plan`; `POST
   /v1/organizations/{org}/plan-interest`; `GET /v1/projects/{key}/usage`;
   `GET /v1/organizations/{org}/usage`; `GET /v1/organizations/{org}/notifications`;
   `PUT /v1/projects/{key}/idle-sleep`. `MATRIX`, `KEY_SCOPES` (usage →
   `projects:read`; plans, notifications → the scope `get_organization` uses;
   idle-sleep → `projects:write`; interest → human only), `PROJECT_WRITES`
   (`set_idle_sleep` member).
4. The OpenAPI snapshot regenerated by its own command; the replaced guard
   (D2521).

**Battery**: (a) the slot reading moved before the entitlement →
`test_the_entitlement_is_read_before_the_slot` FAILS; (b) `plan_limit_reached`
returned by the capacity path → `test_each_refusal_comes_from_its_own_reader`
FAILS; (c) usage readable by a foreign member → `test_a_foreign_and_a_missing_project_answer_alike`
FAILS; **control**: a change to `branch_limit_reached`'s message text → only
the CLI message test fails.

**Targeted once**: `test_plans`, `test_control_usage`, `test_idle_sleep`,
`test_notifications`, `test_control_roles` (grep), `test_control_projects`,
`test_control_branches`, `test_control_contract` (grep the snapshot test),
`test_operation_types`, `test_reality_ledger`, `test_acceptance_registry`,
`test_evidence_claims`. Commit, push, read CI.

**Done.** 2026-10-16. Row **D2545**. Pushed with Run 4 (D2543 (7)). Code:
`errors.PLAN_LIMIT_REACHED` (409, a control word, not an operation outcome)
and `ControlRefused`'s extras admit an integer; `control_service.create_project`
reads the plan FIRST (`_projects_held`: projects not deleted + open creations
not yet in the registry, as the SQL counts them) and refuses `plan_limit_reached
{entitlement, limit, plan, message}`, then the slot reading; `_branch_write`
reads `branches_total` from the plan (`operations.BRANCHES_PER_PROJECT`
deleted, its one reader moved); branch reads carry `reason` and `door`;
`list_plans`, `organization_plan`, `register_interest`, `set_idle_sleep` (its
answer says the backups stop, D2534), `project_usage`/`organization_usage`
(`could_not_determine` with the reason when no sample, each shown limit with
the figure it is read against and `enforced: false`), `notifications`; the
repository's seven calls; `models.PlanInterestRequest`, `IdleSleepRequest`;
seven routes in `control_routes.py` with their OpenAPI text; `control_roles`
(`MATRIX`, `SETTING_WRITES`, `KEY_SCOPES`); `main.control_paths` 32 → 39;
**`contracts/control-openapi.canonical.json` regenerated by `bin/app-contract.sh
--update --snapshot control`** (seven paths added, `/v1/projects`' 409 text
changed, no other path; `--check` agrees). **Tests**: `test_plans.py` +5 route
proofs (the entitlement before the slot with NO slot ready → the plan's
refusal and its exact body; each refusal from its own reader with the other
green, and a control; `/v1/plans` and the organisation's plan against the
release table; *Notify me* once, member only, no key; no route writes a plan)
over one `drive` (the module's cluster fixture now its cluster);
`test_control_usage.py` +2 (the route's `could_not_determine` and shown
limits; foreign, missing and malformed windows through the route),
`test_notifications.py` +1, `test_idle_sleep.py` +1 (the setting's answer,
its member, its values and roles); `test_control_projects.py`: `_org(...,
project=False)`, `test_no_ready_slot_refuses_before_a_row` on a project-less
organisation (the plan green, the slot answers), `test_one_operation_at_a_time`
on a Premium organisation (D2166's serialisation still read), the closed
`projects:write` set widened by `set_idle_sleep`, and **D2160's guard replaced
by `test_plan_limit_reached_is_produced_only_by_the_entitlement_readers`** (the
word in exactly six files), its registry node id, `docs/threat-model.md`'s
`THR-LIFE-EXHAUSTION` row and `docs/acceptance-matrix.md` (regenerated) moved
with it. **Battery** `~/s41/run5/battery5.py` **PASSED**: (a) the slot read
before the plan → the order proof FAILED; (b) the capacity path answering the
plan's word → the two-readers proof FAILED; (c1) the SQL usage reader without
its role check → the SQL proof FAILED; (c2) the service's check removed →
SURVIVED behind SQL, as predicted (D2545 (6)); **control** (the route
description) → all green; files restored byte-equal. **Targeted** (two parts,
foreground): 78 + 255 passed; the two failures (D1187's: the threat row and
the generated matrix) repaired and their modules re-run, 81 passed. **CI on
`d6558df` (run 38929805106) FAILED** on two `test_control_cli` proofs the list
did not hold (D2546); repaired (two organisations on Premium) with
`test_control_cli` and `test_reconciler_claim` run, 23 passed. **Repair
`281c70165ef397f54390533301258d1075554ffd`, CI run 38933417126 `contract`
SUCCESS** (16:37–17:00Z, read by full SHA): Runs 4 and 5 are green at it.

### Run 6 — the reconciler: the sampler, the idle request, the notices (`bin/`, `src/`)

**Read first**: `bin/reconciler.py:1049-1460`; `src/agentic_postgres/reconciler_dispatch.py:180-240,
:600-660`; `bin/doctor.py:940-1130`; `src/agentic_postgres/diagnosis.py:960-1001`;
`src/agentic_postgres/naming.py` (`database_roles`, the customer role names);
the workflow run table's name and creation column (grep `CREATE TABLE
app_private.workflow` in `migrations/templates/`), `app_private.agent_audit`'s
creation column (`0011`/`0025`).

1. `USAGE_SAMPLE_SECONDS = 300`; `Reconciler.record_usage` (the
   `record_backups` set of slots): one sample per slot through
   `reconciler_dispatch.usage_sample(...)` (pure: takes the raw readings, returns
   the sample with `NULL`s and `unread`) → `control_record_usage`; then
   `control_request_idle_sleep` per slot with a setting; then the limit notices.
   The doctor's read argv shared, not copied (import or move into
   `src/agentic_postgres/` — a move runs `test_repository_contract`; every reader
   of the moved function updated, D979/D1187).
2. `run()` gains the `USAGE_SAMPLE_SECONDS` branch beside `BACKUP_RECORD_SECONDS`
   (`:1450-1452`).
3. The closed SQL set (D2531).

**Battery**: (a) a failed store read written as 0 → `test_each_figure_is_read_or_named_unread`
FAILS; (b) agent calls read from `agent_tool_calls_total` → `test_calls_are_counted_from_durable_rows`
FAILS; (c) the idle request sent for a sleeping slot → the dispatch test FAILS;
**control**: the sample interval 300 → 301 → none fail but the constant's own
test.

**Targeted once**: `test_usage_sampler` (new), `test_reconciler_dispatch`,
`test_idle_sleep`, `test_doctor` (grep the usage reader's tests),
`test_repository_contract`, the sweep-selector guard, `test_environment_gates`.
Commit, push, read CI.

**Done.** 2026-10-16. Row **D2547**. Code: `src/agentic_postgres/usage_reading.py`
(new: the doctor's three reads moved, the sampler's three statements);
`src/agentic_postgres/plans.py` (the re-export, its first caller here);
`bin/doctor.py` aliases; `reconciler_dispatch`: `RECORD_USAGE_SQL`,
`REQUEST_IDLE_SLEEP_SQL`, `RECORD_LIMIT_NOTICE_SQL`, `USAGE_FIGURES`,
`usage_sample` (pure: a value, or NULL named in `unread` -- `None` with no
reason is "none present", quiet and read, D2539), `limit_notices` (80% of
Free's `storage_gb`/`agent_calls_per_day`), and the branch payload's `reason`
and `door` (0008's columns, D2514/D2515); `bin/reconciler.py`:
`USAGE_SAMPLE_SECONDS = 300`, `usage_of` (each figure as the doctor reads it;
a sleeping slot read without a container call), `_branch_usage`,
`Reconciler.record_usage` (samples → `control_record_usage`; the idle request
for AWAKE slots only; the notices), `backups_of(..., usage_sink=)`, and
`run()`'s 300 s branch after the backups pass. **Tests**: new
`tests/contract/test_usage_sampler.py` (8: each figure read or named unread
with the store down; a sleeping project; a customer backend is activity; the
durable counts against the release's own tables on a cluster; the activity
reader's roles; the interval is the one 0008 counts; the 80% notices; the
sampler never asks for `agent_tool_calls_total`); `test_reconciler_dispatch`
+2 (the usage pass asks only for awake slots; the closed set of control
functions); `test_auth_service_shape`'s `SHARED_MODULES` + `plans`.
**Battery** `~/s41/run6/battery6.py` **PASSED**: (a) a failed store read
written as 0 → the figures proof FAILED; (b) agent calls from the per-process
series → the series and figures proofs FAILED; (c) the idle request for a
sleeping slot → the awake proof FAILED; **control** (the interval 300 → 301)
→ only the interval proof FAILED. **Targeted** (two parts): 35 + 554 passed,
one failure (`SHARED_MODULES`, the guard doing its job) widened by `plans` and
re-run, 49 passed.

### Run 7 — the customer CLI and the documents

`bin/plan.sh`, `bin/usage.sh`, `bin/notifications.sh` (shims of
`bin/endpoint.sh:92-96`'s shape), `bin/cloud.py` families `plan`, `usage`,
`notifications` and the `project idle-sleep` verb (its output says D2534's
sentence); `git add` the three shims, then `chmod 755`. Documents:
`docs/managed-projects.md` (Plans, Usage, Notifications, Idle sleep sections;
the branch `door` and `reason`), `docs/control-plane.md` (the routes; `:211`'s
sentence replaced), `docs/operator-guide.md` (reading interest rows through
`bin/db.sh` on control-prod; the reconciler's branch-start log; `apg-diag`'s
branch section), `docs/README.md` index. **Targeted once**: `test_cli_contract`,
`test_control_cli`, `test_documentation_index`, `test_session12_documented_path`,
`test_acceptance_registry`. Commit, push, read CI.

**Done.** 2026-10-16. Rows **D2548** (the operator's repair, found here) and
**D2549**. **Commands**: `bin/plan.sh` (`list|show|notify-me`),
`bin/usage.sh` (`show [--project-key KEY | --organization ID] [--hours N]`),
`bin/notifications.sh` (`list [--limit N]`) -- shims of `bin/endpoint.sh`'s
shape, `git add`ed then `chmod 755`; `bin/project.sh idle-sleep --minutes
15|30|60|never`; `bin/cloud.py` families `plan`, `usage`, `notifications` and
`project_idle_sleep` (a figure not read printed *not read in this window*,
never 0; a window with no sample exit 6). **The repair (D2548)**:
`operations.IDLE_SLEEP_TYPE`/`IDLE_SLEEP_ROW`, `require_idle_sleep_offered`
on the route (409 `not_available` naming `idle_sleep`; the control snapshot
regenerated), the reconciler's idle request only while `project.sleep` is
accepted, and the Ledger guard. **Documents**: `docs/managed-projects.md`
(Idle sleep, Plans, Usage, Notifications; the branch `door`/`reason`; the
plan read before the slot; the refusal table), `docs/control-plane.md` (the
commands; `:211`'s sentence replaced; the seven routes), `docs/operator-guide.md`
(§20's usage samples and *Who asked for Premium*; §22's branch-start log and
`apg-diag containers`' branch sections; the apg-diag paragraph),
`docs/README.md`. **Tests**: `test_control_cli` +2
(`test_plan_usage_and_notifications_dispatch_to_the_customer_cli`,
`test_idle_sleep_names_the_backup_consequence`), `test_cli_contract` +1
(`test_the_usage_verb_is_the_customers_and_the_reading_is_the_operators`,
both spellings) and the three shims in `SHELL_COMMANDS`/`COMMANDS_WITH_VERBS`,
`test_idle_sleep` +1, `test_reconciler_dispatch` +1, `test_reality_ledger` +1.
**Battery** `~/s41/run7/battery7.py`: round 1 **FAILED** -- (a) *a figure not
read printed as 0* SURVIVED (the proof asked for "not read" in the line, and
`0; not read in 1 sample(s)` holds it); the proof now reads the whole reading.
Round 2 **PASSED**: (a)-(f) each FAILED its own proof only (a 0 for an unread
figure; an undetermined usage exiting 0; idle-sleep's own word for the route's
sentence; the route's door removed; the reconciler's door removed; the
`idle_sleep` row moved to `trial` without its type), **control** (the usage
header's pointer to the operator's command) failed only D2528's proof; files
restored byte-equal. **Targeted** (two parts, once): 1,239 + 41 passed.

### Run 8 — the trip's instruments, written and rehearsed offline

WSL `~/s41/run8/` (+ scratchpad copy): **`s41-derive.py`** derives every
`s41-*.sh` from `~/s40/run7/` by named, count-asserted substitutions
(`slot4-prod` → `slot5-prod`, `s40` → `s41`, session numbers), exactly as
`s40-derive.py` did from `~/s39/run8`. **`s41-lifecycle.py`** from
`s40-lifecycle.py` (the D2500 repair kept; `session: 41`): **step 0** the
probe organisation's create refused `plan_limit_reached` while
`slot3-prod` exists and `slot5-prod` is `ready` (operations count before/after,
no file kept); `/v1/plans` read; Premium interest recorded twice → one row;
**step 1** a NEW organisation `lifecycle-s41` created by the probe account;
then the Session 40 lifecycle in it (create `small` → claim → credentials →
both names → rotate → sleep → wake → resize `standard` → resize `large` →
export); **then idle**: `idle-sleep --minutes 15`, the route and pool probes
on `slot5-prod` paused (the neighbours' probes keep running), wait for an
operation with `origin = idle` (bound: 15 min + 2 × 300 s + 120 s), both names
refused, wake; **usage** read for the slot and the organisation (recorded);
**notifications** listed (recorded); **K2** pause; delete; **the second create
in `lifecycle-s41`** refused `capacity_exhausted {no_slot}`, no row. The record
keeps `window_started_at` (D2506) and every member the Sessions 38–40 proofs
read (`observations.administrator`, `deleted_samples`, `wake_first_answer`,
`export_url`, `export.mode`, `export.second_read_handed_a_url`, `doors`).
**`s41-branches.py`** from `s40-branches.py`, **with the D2501/D2503/D2504
workarounds REMOVED** (the product now does each; a workaround kept would hide
a repair that did not work): the backups surface must read a window; `ready`
must mean the door answers on the first attempt; `--after-reboot` reads the
branch `ready` by itself (no reset) and `apg-diag containers` (through the agent
account) listing it. **Rehearsals** (`rehearse_lifecycle41.py`,
`rehearse_branches41.py`, the Session 40 rehearsals as templates, against a
fake reconciler and a real control cluster with 0008): a full pass each, the
idle step reached by a fast-forwarded sampler, a killed pool sample with the
thread alive after it (D2500), and **controls**: a rehearsal with the idle
request suppressed stops at the idle step's bound with *"no idle sleep was
requested"*. Long rehearsals run in the background and are WAITED on in the
foreground (`~/s40/run7/wait-code.sh`). Commit nothing but the **Done.**
(docs, no CI).

**Done.** 2026-10-16. Rows **D2550** (the three live modules are Run 9's, and
two post-delete proofs move to the record's own organisation) and **D2551**
(Run 8's rulings). WSL `~/s41/run8/` (+ the scratchpad's `s41/run8/`):
**`s41-derive.py`** -- twelve children from `~/s40/run7/` (the nine host
parents byte-equal to `/home/op`'s, sha256 read), every body substitution
counted, every changed line an intended rename (`diff` read), shellcheck's
findings the parents' own; `~/s41/host-address` written from `~/s40/`'s.
**`s41-lifecycle.py`** (`make-lifecycle41.py`, every edit counted): step 0
(plans, Premium interest twice → once, the probe organisation refused
`plan_limit_reached` with no row and no file), step 1 (`lifecycle-s41`), the
eleven, the idle step (`--slot-probe-label`, bound 15 min + 2 × 300 s +
120 s), usage, notifications twice; `window_started_at`; the D2500 repair kept.
**`s41-branches.py`** (`make-branches41.py`): the D2501/D2503/D2504
workarounds REMOVED -- a window or a stop, `door_first`, `--after-reboot` with
`apg-diag containers`; `window_started_at` = `--since` or the start (D2506).
**Rehearsals, each on its first execution**: `rehearse_lifecycle41.py`
**PASSED** (169 s; 17 checks), its `--control` **PASSED** (stopped at the idle
step's bound); `rehearse_branches41.py` (`make-rehearse-branches41.py`)
**PASSED** (live 235 s, after-reboot 28 s, delete 35 s; 10 checks; 0 rig
containers left). Committed: this paragraph and the two rows only.


### Run 9 — the bump, the registry, the gate, the threat rows, the Ledger to `trial`, the documents

`CURRENT_SESSION` 41 and a Session 41 paragraph in `__init__.py` (Session 40's
format, `:1091-1144`); `VERSION` `1.19.0`; `README.md:7` and the literals on the
documented path (counted per file); the registry (§2; counted from the tuples);
`CLAIMS`, `OFFLINE_CLAIMS`, `CLAIM_INTRODUCED_IN`; **`bin/session-41-check.sh`
derived from `bin/session-40-check.sh` by diff** (header and usage rewritten
whole; `readonly SESSION=41`; no flag added) and
`tests/contract/test_session_forty_one_gate_modes.py` derived from
`test_session_forty_gate_modes.py` (`SESSION = 41`, `SESSION_PREVIOUS_NUMBER =
40`, the claims table); `SHELL_COMMANDS`; the four `THR-*` rows; **the Ledger**:
the sixteen rows of sentence 9 → `trial` with *"being verified"* and evidence
naming only Session 41 claims — the six managed-project rows
`[lifecycle_third_trial_live]` (`sleep` also `idle_sleep_live`), `idle_sleep`
`[idle_sleep_live, idle_trigger]`, `branches` `[branch_retrial_live,
branch_host_retrial_live, branch_start_repaired, branch_door_ready]`,
`restore_to_branch` `[branch_retrial_live]`, `backups_and_pitr`
`[branch_retrial_live, backups_reading_repaired]`, `usage` `[usage_live,
usage_sampler, usage_api]`, `notifications` `[notifications_live,
notifications]`, `plan_free` `[plans_live, plan_entitlements, plan_api]`,
`plan_premium` `[plans_live, plan_api]`; `query_insights`, `monitoring` →
target 42; `console` → target 43; `ACCEPTED_TYPES` = the eleven
(`test_exactly_the_eleven_executed_types_are_accepted`, D1119);
`bin/render-reality-ledger.py --write`, `bin/render-acceptance-matrix.py
--write`, the ADR index, `bin/render-capacity-envelope.py` if it moved.
**Gates once, clean tree**: `bin/session-01-check.sh` and `bin/session-41-check.sh
--mode offline` (background, exit code written to a file inside WSL); then push
and read CI.

### Run 10 — sitting 1 (day 1): the release, `slot3-prod` moved by the verb, `slot5-prod` prepared, the dry run

The agent: bundle + `scp` + checkout on the host (`git rev-parse FETCH_HEAD`),
`uv sync` if `requirements-dev.txt` moved, renders; then the sheets in order,
**each read before the next**: **P1** (consoles: `slot5-prod`'s three records
and providers) → `s41-dns.sh slot5-prod` (GO) → **R1** → reconciler stopped →
**R2a/b/c** → **R2d** → **A1** → **H1** (`slot5-prod` declared, both copies) →
**RC1** → **SL1** → **SL2** → **SL3** (`slot5-prod ready`) → **PV** → **RA** →
**K1** → **V1** (the whole host suite `-k "not after_reboot and not lifecycle
and not branch"`, writing nothing) → **X0** (the whole external half, same
filter, from WSL). **Stop** if R1 prices `major` or for a reason this plan did
not name, if R2d leaves `slot3-prod`'s doors or certificate different, or if V1
or X0 fails for a reason other than the filtered live proofs' absence — **repair
on day 1, move the commit, redeploy, run RA, V1 and X0 again** (D2448).

### Run 11 — sitting 2 (day 2): the re-earning, the branches, the reboot, the sweep, the tag

1. **The lifecycle** (`s41-lifecycle.py`; probes on alpha, beta, control,
   `slot3-prod` and the slot): steps 0–1 and the lifecycle as Run 8 wrote them;
   **K2** at its pause.
2. **The branches on `slot3-prod`** (`s41-branches.py`): the backups surface
   (a window, D2501); `tmp` expired by the reconciler; the markers; `dev` at
   `T1`; migrate over its direct name; the parent's password refused; `qa`
   refused `branch_limit_reached`; `dev` reset — `ready` meaning the door
   answers (D2503); **Sheet M1** with `dev` ready.
3. **A1'** (agrees ×4 + `slot5-prod agrees (deleted)`) → **B1** (the reboot) →
   the after-reboot read (`s41-after-reboot.sh` for the six units, then
   `s41-branches.py --after-reboot`: `dev` back BY ITSELF, psql through
   `dev.pool.…`, `apg-diag containers` listing it) **before the sweep** (D2140)
   → **S1** (the sweep, `--branch-record-file`) → `s41-branches.py
   --delete-only` → external (`--branch-record-file`, `--lifecycle-record-file`)
   → merge (expected §7) → **tag `1.19.0`** from the workstation → **SL4**
   (`slot5-prod` revoked; its directory read gone).

### Run 12 — the close

**Code** — `bin/session-01-check.sh` once and CI.

- **The Ledger from the TAGGED evidence**: each `trial` row → `beta` if every
  named claim reads `passed` in `evidence/session-41.json`, else → `planned`
  target 42 with its types removed from `ACCEPTED_TYPES` and the Done saying
  why.
- **`capacity.ENVELOPE`**, a *Session 41* section: `slot5-prod`'s lifecycle
  rows; **the windows as the pooled name saw them** (the `UNMEASURED` row
  `capacity.py:1965-1977` out if every window was covered); **the host's memory
  with a branch live** (M1; `:1978-1986` out, its citation corrected to D2509);
  the idle sleep's latency (setting window → the sleep requested → asleep); the
  branch's return after B1 by itself; a usage pass's duration (the reconciler's
  log); the door's time to ready.
- `docs/scope-closure.md` **§34**; the stage plan's Status block; CLAUDE.md §2
  rewritten for Session 42's planner (copy it to the scratchpad first); this
  plan's `Status:` COMPLETE.

---

## 7. Evidence and claims

**Expected at the merge** (Run 11): **284 claims** (121 offline). **`failed` 1:
`documented_path`** (D1935). Everything else **passed** — including Session
40's four live claims re-run on Session 41's records (`lifecycle_reearned_live`
with the repaired pool probe, `branch_live` and `branch_host_live` with D2501,
D2504, D2505, D2506 repaired) and every Session 41 claim. **Exit 5 for
`documented_path` and no other reason.** Predictions, each moved only by the
evidence.

**The three modes.** Offline: CI's artifact for the deployed SHA (121 claims).
Host: S1 with `--lifecycle-record-file`, `--slot-outputs` (`slot5-prod`, K2),
`--live-slot-outputs` (`slot3-prod`) and `--branch-record-file`. External: from
WSL, with `--control-outputs`, `--control-probe-file`, `--lifecycle-record-file`,
`--customer-credential-dir` and `--branch-record-file`; **the Session 41
customer proofs reach only `routes.control`, the slots' recorded `routes.app`
and the public names on 5432, and open no SSH** (`test_this_module_uses_no_ssh`
in each new external module). **Deploy every project fully, THEN the dry run
(V1, X0), THEN the lifecycle and the branches, THEN sweep, THEN external —
every half at one commit.**

---

## 8. Security invariants this session touches

| Invariant | How this session keeps it |
|---|---|
| **A capacity refusal and an entitlement refusal are different codes from different readers** | `plan_limit_reached` from the entitlement (service + SQL under a lock), before the slot reading; `capacity_exhausted` from the slot reading; each proved with the other green, offline and on the trip (PLAN-ENT-001, PLAN-LIVE-001, LIFE-LIVE-005) |
| **The control plane holds nothing that opens a project's data or admin plane** | `agent_calls_per_day` read, not written onto a project's agents (D2520); usage read by the reconciler (root, the host actor), never by the control plane |
| **The reconciler runs only a closed set of typed operations** | It requests two kinds now — an expired branch's deletion and an idle project's sleep — each through a function granted to nobody, the decision in the control database (D2531, USE-IDLE-001) |
| **No customer surface writes a usage sample or an entitlement** | The three writers granted to nobody; no route writes a plan or a limit (PLAN-API-001, USE-SAMPLE-001, THR-USE-TAMPER) |
| **A report may not substitute an answer for a failure to determine one** | Usage `NULL` + `unread`; an empty window `could_not_determine`; a missing sample is not idle; the backups window from the producer; a branch's `reason` and `door: pending\|unknown` (D2512–D2515, D2523–D2525) |
| **Projects share no project-scoped value** | Usage and notifications through the membership check; a foreign organisation answers like a missing one (THR-USE-LEAK) |
| **No URL, key, token or caller value in a log line or a notification** | Templates interpolate the type, key, origin and code only; the canary over every template (USE-NOTIFY-001); the branch-start log holds names and Docker's text |
| **A branch starts re-keyed and cannot write its parent's repository** | Unchanged; its configured archive command read from its argv (D2505) |
| **Nothing `planned` has a control** | Premium's *Notify me* lives on a `trial` row; `trial` resolved at the close |

---

## 9. Stop conditions

Stop and ask the operator, without improvising, when:

- **E0's quiet reads show the edge counter's sub-400 part moving with no
  traffic**, or a customer role's `state_change` moving with no client — the
  idle signal would keep a project awake or sleep a busy one;
- rig 41c shows a rebuild of unchanged content changing the platform digest
  (the branch could never come back by tag + digest), or rig 41b shows the
  handshake verifying before the certificate is issued;
- rig 41d's concurrency case leaves two rows with the lock in place;
- a design here would need the control plane to write into a project
  (`app_private.agents` or any project table), a route that writes a plan or a
  limit, or an override verb;
- a notification would need a result member, a URL or a caller value;
- `upgrade plan` prices 1.19.0 at `major`, or for a reason this plan did not
  name;
- R2d (`slot.sh redeploy`) leaves `slot3-prod`'s doors, certificate or registry
  row different from before;
- **V1 or X0 fails and the repair would move the commit after `slot5-prod` has
  been created** (D2448), or any commit move after its deletion — there is no
  sixth slot prepared;
- the probe organisation's create is NOT refused `plan_limit_reached` (the
  lifecycle must not create a second project in it), or the idle sleep fires
  while a probe was still running against the slot;
- a branch does not come back by itself after B1 (the product repair failed:
  the trip continues only by the operator's choice, recorded);
- the parent's doctor reads anything but twelve ok, or its volume,
  `instance_uuid` or timeline changes, at any point of a branch's life;
- a `trial` row would outlive the close, or a row would move to `beta` without
  its claims `passed`;
- a currently-passing test would be weakened to make a new one pass;
- `--render-only` stops working with no host and no root.

---

## 10. Open items this session carries and creates

**Carried, untouched, each still true:** the OVH upgrade — **Session 42's first
sitting** (D2511); M7's X1/X2 (Hetzner), allowed and not this plan's (D2535);
beta's three rotations (D1995); D1936/D2005; D1547; D2020/D2025; D2031; D1642,
D1798, D1869, D1871, D1722/D1806, D1784, D1792, ADR 0241's bound; D1045; D1375;
D976; D688; D771; D340; D466; D540; D942; D1203; D1205; D1211; the 24 unclaimed
requirements; `process-max` 1 (D593); `documented_path` (D1935); accounts and
organisations never deleted (D2065, D1986); TOTP seeds plaintext (ADR 0252);
`/v1/sessions` unthrottled (D2166); the reconciler and the operator serialised
by a rule, not a lock (D2178); a slot's provider resources outlive it (D2181);
the export URL crosses the control database (ADR 0259); `storage.enabled: false`
still emits storage's router (D2144); `materialize-secrets` has no
last-known-good fallback; `secret_required_added` cannot fire (D2331); Postgres
sees the gateway's address and no channel binding (D2325); a plaintext peer
holds a socket for the read deadline (D2326); a branch shares its parent's
`system_identifier` and identity row; a branch is not backed up; the parent's
user hashes are copied into a branch; branch certificates accumulate in
`acme.json`; the backups recording's R2 requests per slot; the 1.18.0 tag
message's slip (D2506).

**Created, and named so Session 42 does not inherit them silently:**

- **Usage samples are never pruned** (~288 rows per slot per day); a retention
  is an operator-stated horizon (ADR 0213's shape) when slots multiply.
- **DB time is not metered** until `pg_stat_statements` loads (Session 42); the
  usage document says *not read* for it.
- **`storage_gb` and `agent_calls_per_day` are shown, not enforced** (D2519,
  D2520); a project's agents keep no plan ceiling.
- **No override of a plan limit exists**; a beta tester who needs a second
  project is the operator's problem with no tool (D2521).
- **Notifications have no read state and no deletion**; the console (43)
  decides whether it needs either.
- **Idle sleep wakes only by request** (`wake_on_connect` `planned`); a sleeping
  project's archiver is stopped (D2534).
- **The lifecycle's organisation `lifecycle-s41` remains**, empty, owned by the
  probe account.
- **`slot1-`, `slot2-`, `slot4-` and `slot5-prod` are consumed** after this trip;
  the next lifecycle needs `slot6-prod`.
- **The lint's SQL reader loses a literal that holds `--`** (D2544, Run 4):
  `sql_surface.statements` strips comments without regard to quotes, so every
  reader after such a literal -- the lint, the destructive findings, the
  surface -- reads the rest of the file as a string. 0008 avoids it; 18 of 51
  templates have an odd quote count after the reader (a heuristic). A
  quote-aware reader, with a failing test first, is owed; the operator decides
  when.

---

## Appendix — what to consult, how a run is executed here, and the sheets

**Consult, in this order:** CLAUDE.md §1 (the shell traps); this plan's §0, §1
and the run's own text; the reads its run names. **The tree wins.**

**How a run is executed here**: CLAUDE.md §5. Every `sudo` line is the
operator's, on a sheet, under `script -q -e -c '…' /home/op/s41-<sheet>.txt`
when it execs into a container or deploys (D972, D1501), never piped or
redirected; `sudo -v` in the foreground first (D1376). Every `op` line is the
agent's over SSH; remote loops in a script file with `PATH="$HOME/.local/bin:$PATH"`
exported. **`<sha>` is never typed on a sheet**: the agent fills it from `git
rev-parse HEAD` on the host before handing the sheet. **Before any sheet that
deploys, retires, restores or recreates the edge: `sudo systemctl stop
agentic-postgres-reconciler`, and `start` after** (D2178); **after any edit to
`host.yaml` or any checkout move: restart it** (D2411, D2179). **Read `--help`
of every command on a sheet before handing it** and correct the line to it.
**A sheet may not hand over a command whose precondition is the previous
sheet's success** (D1510): one sheet, one outcome, read before the next.

### Sheet E0 — readings before anything is built (Run 1; reads only)

```
sudo -v
sudo bash /home/op/s41-e0.sh      # sha256 printed by the agent; writes /home/op/s41-e0/ and /home/op/s41-e0.txt
#   the script pauses at T0+30 min and prints: "the agent sends ONE request and ONE psql now; press Enter after"
```

### Sheet P1 — the consoles (any day before Run 10's SL1)

```
Cloudflare DNS, DNS only (grey), no AAAA, each -> 15.204.231.45:
  A slot5.agenticpostgresql.com
  A pool.slot5.agenticpostgresql.com
  A direct.slot5.agenticpostgresql.com
Cloudflare R2 (EEUR, Standard): apg-slot5-prod, apg-slot5-prod-backup, each with an Object R&W token
Backblaze B2: apg-slot5-prod-backup-mirror, with an application key limited to it
```

### Sheet R1 — the release priced (Run 10)

```
sudo bin/upgrade.sh plan --project alpha-dev    --candidate .generated/alpha-dev/outputs.json    --also api_operation_added --json
sudo bin/upgrade.sh plan --project beta-dev     --candidate .generated/beta-dev/outputs.json     --also api_operation_added --json
sudo bin/upgrade.sh plan --project control-prod --candidate .generated/control-prod/outputs.json --also api_operation_added --json
```

### Sheets R2a / R2b / R2c — 1.19.0 deployed (Run 10)

```
sudo systemctl stop agentic-postgres-reconciler
script -q -e -c 'sudo ./deploy.sh --host host.yaml --project project.alpha.yaml   --capabilities capabilities.yaml --through-session 41' /home/op/s41-r2-alpha.txt
script -q -e -c 'sudo ./deploy.sh --host host.yaml --project project.beta.yaml    --capabilities capabilities.yaml --through-session 41' /home/op/s41-r2-beta.txt
script -q -e -c 'sudo ./deploy.sh --host host.yaml --project /home/op/control.yaml --capabilities capabilities.yaml --through-session 41' /home/op/s41-r2-control.txt
```

### Sheet R2d — `slot3-prod` moved by the product's verb (Run 10)

```
script -q -e -c 'sudo bin/slot.sh redeploy --host host.yaml --slot slot3-prod --confirm slot3-prod' /home/op/s41-r2-slot3.txt
```

### Sheet A1 — the registry after the last deploy (Run 10)

```
sudo bin/control.sh adopt --project alpha-dev    --organization 10234b92-b2d7-4573-bebb-f012ce5c8f02 --confirm control-prod
sudo bin/control.sh adopt --project beta-dev     --organization 10234b92-b2d7-4573-bebb-f012ce5c8f02 --confirm control-prod
sudo bin/control.sh adopt --project control-prod --organization 10234b92-b2d7-4573-bebb-f012ce5c8f02 --confirm control-prod
sudo bin/control.sh registry      # agrees x4, slot1/2/4 agrees (deleted); exit 0
```

### Sheet H1 — `slot5-prod` declared (Run 10)

```
sudo install -o op -g op -m 0600 /etc/agentic-postgres/host.yaml /home/op/etc-host.yaml
#   the agent runs s41-hostyaml.py on both copies (slots.declared += slot5-prod=slot5.agenticpostgresql.com=apg-slot5-prod-backup-mirror)
#   into /home/op/s41-h1/ and prints the diffs; read them, then:
sudo install -o root -g root -m 0600 /home/op/s41-h1/etc-host.yaml.slots /etc/agentic-postgres/host.yaml
```

### Sheet RC1 — the reconciler back, reading the new declaration (Run 10)

```
sudo systemctl start agentic-postgres-reconciler
sudo bin/reconciler.sh status       # idle; the journal's slot line names slot5-prod (D2411)
```

### Sheet SL1 — `slot5-prod`'s providers (Run 10)

```
sudo bin/slot.sh prepare --host host.yaml --slot slot5-prod
sudo bin/bootstrap-providers.sh --host host.yaml --project /etc/agentic-postgres/slots/slot5-prod/manifest.yaml --plan
sudo install -d -m 0700 /root/.config/agentic-postgres/bootstrap
sudo nano /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo chmod 0600 /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo bin/bootstrap-providers.sh --host host.yaml --project /etc/agentic-postgres/slots/slot5-prod/manifest.yaml --apply \
     --operator-credential-file /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo shred -u /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo ls -la /root/.config/agentic-postgres/bootstrap/      # empty, no nano .save copy (D2061)
#   YOU: open 443 on the store host to your address (docs/secret-store.md §1, D2496), then in Infisical,
#   project `slot5-prod`, environment `dev`: the storage pair at /storage (create the folder),
#   the backup pair at /backup, the mirror pair at /backup; close 443 again and read it closed.
```

### Sheet SL2 — materialized (Run 10)

```
sudo bin/materialize-secrets.sh --project /etc/agentic-postgres/slots/slot5-prod/manifest.yaml --requirements secrets.required.yaml --session 41
```

### Sheet SL3 — the slot read (Run 10)

```
#   the agent has run s41-dns.sh slot5-prod (three records, exit 0)
sudo bin/slot.sh status --host host.yaml         # slot5-prod ready; slot3-prod allocated; slot1/2/4 consumed
sudo bin/control.sh registry                     # ... slot5-prod prepared (slot); exit 0
```

### Sheet PV — `apg-diag` reinstalled (Run 10)

```
cd /home/op/agentic-postgres
sudo install -m 0755 -o root -g root bin/apg-diag.sh /usr/local/bin/apg-diag
#   (read by Run 3 from infra/host/apg-agent.sudoers:5 -- the documented install; nothing
#    else installs it, docs/operator-guide.md:118 "installed by hand", D2514)
sudo cmp bin/apg-diag.sh /usr/local/bin/apg-diag && echo "apg-diag is the checkout's"
#   Then the agent reads, as apg-agent: sudo apg-diag containers   (no branch yet: no branch section)
```

### Sheet RA — the admission rehearsal at the deployed commit (Run 10, after the last deploy; again only if the commit moves)

```
sudo bin/rehearse.sh admission-refused --outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json --host host.yaml --manifest /home/op/s31-third.yaml
```

### Sheet K1 — the kit and the copies (Run 10)

```
sudo bin/dr-kit.sh export --host host.yaml --capabilities capabilities.yaml \
     --project project.alpha.yaml --project project.beta.yaml --project /home/op/control.yaml \
     --output /home/op/kit-<today>-s41
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/alpha-dev/outputs.json    /home/op/alpha-dev-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/beta-dev/outputs.json     /home/op/beta-dev-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/control-prod/outputs.json /home/op/control-prod-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/slot3-prod/outputs.json   /home/op/slot3-prod-outputs.json
```

### Sheet V1 — the whole host suite, writing nothing (Run 10; ~45-80 min)

```
sudo bash /home/op/s41-v1.sh       # -k "not after_reboot and not lifecycle and not branch" (D2448); X0 is the agent's, from WSL
```

### Sheet K2 — `slot5-prod`'s document, before its deletion (Run 11, at the lifecycle's pause)

```
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/slot5-prod/outputs.json /home/op/slot5-prod-outputs.json
```

### Sheet M1 — the host's memory with a branch live (Run 11, with `dev` ready)

```
free -m
sudo bin/doctor.sh capacity --host host.yaml      # read --help first and correct this line to it
sudo docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' | grep slot3-prod_dev
```

### Sheet A1' — the registry after the lifecycle and the branches (Run 11)

```
sudo bin/control.sh registry                     # agrees x4, slot1/2/4/5 agrees (deleted); exit 0
sudo bin/branch-runtime.sh status                # slot3-prod_dev ready, door ready
```

### Sheet B1 — the reboot (Run 11)

```
sudo systemctl reboot
#   the agent then runs s41-after-reboot.sh (units) and s41-branches.py --after-reboot BEFORE any sweep (D2140)
```

### Sheet S1 — the one sweep (Run 11)

```
sudo -v
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/alpha-dev/outputs.json    /home/op/alpha-dev-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/beta-dev/outputs.json     /home/op/beta-dev-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/control-prod/outputs.json /home/op/control-prod-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/slot3-prod/outputs.json   /home/op/slot3-prod-outputs.json
sudo bash /home/op/s41-launch.sh      # refuses while the reconciler is working; detaches s41-sweep.sh
```

### Sheet SL4 — `slot5-prod`'s identity revoked (Run 11, after the tag)

```
sudo bin/slot.sh revoke --host host.yaml --slot slot5-prod --operator-credential-file /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential --confirm slot5-prod
sudo shred -u /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo ls -la /root/.config/agentic-postgres/bootstrap/      # empty
sudo ls -la /etc/agentic-postgres/projects/                # no slot5-prod directory (D2405)
```

**If something goes wrong** (read Sessions 39's and 40's first, D977): a WSL
TLS blip during an `--wait` → the instrument awaits the operation by id, never
re-sends (D2502); a resumed record keeps `window_started_at` (D2506); a branch
near its budget → the type's bound is 3,600 s now (D2516) — still read the
operation's `step`; a branch that does not come back after B1 → read the
reconciler's `branch-start-<utc>.log` and the record's `reason` (D2514) BEFORE
any reset, and record both; an idle sleep that never fires → read the slot's
samples through `GET …/usage` for a missing or unread figure (that is the
designed refusal, D2525) before suspecting the trigger.
