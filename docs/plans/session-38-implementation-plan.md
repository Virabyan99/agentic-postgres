# Session 38 — Managed projects

**Status: PLANNED 2026-10-07 at `87b80bf`. NOT STARTED: the next chat executes it from Run 1.**
The third session of Stage 5 (`docs/plans/stage-5-plan.md` §3). Thirteen runs
and **two sittings on two days**: the release on the three projects, the
reconciler installed and one customer slot prepared (day 1); then, from the
workstation with no SSH, a project created into the slot, its first
administrator claimed, slept, woken, resized, refused a resize by capacity,
exported, deleted, and a second creation refused for want of a slot — then a
reboot, the one sweep, external, merge, tag (day 2). The plan spends
**D2145–D2188** and **ADR 0256–0261**; rows the runs add start at **D2189**.
**NEXT FREE after this plan: D2189, ADR 0262.**

**Brief:** `docs/plans/stage-5-plan.md` §5 *Session 38* whole (Builds / Already
true / Must not / Measures / Closes) and its rows **D1953** (operations, the
reconciler, slots), **D1954** (two refusals, two codes — 38 owns the capacity
half), **D1955** (compute profiles), **D1956** (sleep and wake), **D1957**
(region), **D1969** (the creator as the project's first admin), **D1972**
(delete and export), **D1976** (the resize message quotes a measured window),
**D1978** (threat rows first), **D1979** (the Ledger), **D1983** (provisioning
and deletion time measured), §7–§10; `docs/scope-closure.md` **§30** (what
Session 37 hands 38: managed projects, D2137/D2144, D2140/D2141/D2142, the
walk's friction, the rescale); Session 37's plan (its rows D2073–D2144, its
sheets, its §10); `docs/reality-ledger.yaml` (rows `projects_self_service`
`:161-179`, `project_deletion` `:181-194`, `export` `:196-209`, `region`
`:211-225`, `compute_profiles` `:227-244`, `sleep` `:246-260`);
`docs/threat-model.md` hosted items #4 (`:196-200`), #7 (`:209-214`), #8
(`:215-218`), #12 (`:238-241`); ADRs **0110, 0185, 0186, 0187, 0195, 0218,
0221, 0222, 0243, 0246, 0247, 0251, 0253, 0254**; and **the operator's four
answers of 2026-10-07** (§1 D2145–D2148).

**Shape:** thirteen runs. **Run 1** is documentation — six rigs, one host
reading sheet (E0, reads only), the threat list made specific, six ADRs — and
reads **no** CI verdict. **Runs 2–8** change code: each pushes and reads that
commit's own CI verdict by full SHA (`gh api
"repos/Virabyan99/agentic-postgres/actions/runs?head_sha=<40 chars>" --jq
'.workflow_runs[] | [.name, .status, .conclusion] | @tsv'` from Git Bash,
judged on HTTP status, three buckets — success / failure / not registered; an
empty list is not a verdict, D1057). **Run 9** writes the trip's instruments
and rehearses them offline, committing nothing but its `**Done.**`. **Run 10**
is the bump. **Runs 11–12** are the sittings. **Run 13** is the close (the
Ledger's rows, the envelope's rows and one constant are code: it gates once and
reads CI).

**Product version at close:** `CURRENT_SESSION` **38**; `template_version`
**`1.16.0`** — predicted *minor* (manifest schema 10, host schema 4 and outputs
schema 21, each migratable; new `/v1` operations; **no released migration**)
and **read from `upgrade plan` on the host, never chosen** (§1 D2186). The
released migration count stays **39**: the control plane's new tables and
functions are the control project's OWN set (`projects/control/`, its fourth
migration), and the first-admin handoff uses a function every project already
has (§1 D2163). **One new standing root actor** (the reconciler and its unit),
**one new operator command** (`bin/slot.sh`), **two new customer commands**
(`bin/compute.sh`, `bin/operation.sh`), **new verbs on `bin/project.sh`**, **two
new verbs on `bin/project-runtime.sh`** (`stop`, `start`), **one new retirement
mode** (`--defer-provider`). A `major` is §9's stop.

**Written for whoever picks this up cold, and it will be a different model than
the one that planned it.** Every path below was read from the tree on
2026-10-07 at `87b80bf` — four explore passes over `services/auth-api/app/`,
`projects/control/`, `src/agentic_postgres/`, `bin/`, `libexec/`, `systemd/`,
`schemas/`, `tests/`, `docs/` and every plan, plus direct reads of
`migrations/templates/0026-password-reset-plane.sql:83-250`,
`services/auth-api/app/routes.py:617-700`, `bin/deploy-project.py:338-362`,
`bin/bootstrap-providers.py:860-961`, `src/agentic_postgres/retirement.py:140-160`
and `host.example.yaml:105-125`. Every path is cited `path:line`. **Read
CLAUDE.md §1 in the launch folder before the first command, then this plan's §1,
then the appendix.** If a step here and the tree disagree, **the tree wins and
the disagreement is a divergence row** (next free `D` after §1's table), never a
silent reconciliation. **When this plan names a line number, open the file at
that line and read the surrounding twenty lines before editing** — the numbers
were right on 2026-10-07 and `ruff format` moves them.

**The eight sentences the executor most needs, in case nothing else is read:**

1. **The host stays the CX23, with ONE customer slot** (§1 D2145, the
   operator, 2026-10-07). 1,624 MiB available, 912 of 1,600 MiB committed. The
   slot is created at the `small` profile; **stop if `available` falls below
   1,024 MiB** after its creation. The rescale or a move is owed before
   Session 41 (ClickStack), the operator's to schedule.
2. **The reconciler is a root systemd unit with no listener, and it reaches the
   control plane exactly the way `bin/control.sh` does** — `docker exec … psql
   -U postgres` into the control project's database through
   `container_exec.run` (`bin/control.py:209-213`), calling functions **granted
   to nobody** (D2093's shape). It claims ONE operation at a time, dispatches it
   through a closed table to the EXISTING `bin/` commands by argv, and writes the
   outcome. **An operation found `running` when the reconciler starts is marked
   `failed` with `interrupted` and its slot `quarantined` — never run twice**
   (§1 D2152).
3. **A slot is a project the operator prepared in advance and that no customer
   has yet**: declared in `host.yaml` (schema 4), its manifest written by `sudo
   bin/slot.sh prepare`, its providers made by the existing `bootstrap-providers
   --apply` with the operator's credential on a sheet, its secrets
   materialized. **Creation consumes nothing at a provider**, so *"No resources
   were created"* is true by construction. **A slot is single-use**: deletion
   writes a tombstone no command removes (§1 D2150, D2158).
4. **The control plane holds nothing that opens a project's data or admin
   plane — and the first-admin handoff keeps it that way by hash** (§1 D2163).
   The member's CLI generates a 256-bit token `T` locally and sends only
   `sha256(T)`; the reconciler bootstraps the project's administrator with a
   random password it never keeps, then registers `sha256(T)` as that
   administrator's password-reset token with the existing
   `app_private.auth_open_password_reset` (`0026:118`); the member presents `T`
   at the project's own `/auth/reset-password` (`routes.py:661-685`) and chooses
   the password. **`T` never leaves the workstation except to the project.**
5. **Two refusals, one code, two readers in 38**: `capacity_exhausted` with
   `reason: admission` (the reconciler maps `bin/admit.sh`'s exit 12) and with
   `reason: no_slot` (the API, before an operation row exists). **No
   entitlement code exists in 38** (`plan_limit_reached` is Session 41's); a
   test holds that nothing in 38 can produce one (§1 D2160).
6. **Sleep is `compose stop`, wake is `compose start`** — containers and volumes
   kept, no secret re-read, the unit and the backup timers disabled while it
   sleeps (§1 D2155). **A caller of a sleeping project gets Traefik's own
   `404 page not found`** (measured: D271, rig 35d — a stopped container's label
   router disappears); no fallback body is built, and `/v1` says `sleeping`.
7. **D2137/D2144 is paid in Run 2**: `api.rest.enabled: false` withholds the
   PostgREST router and the deploy records `api` unpublished without trying to
   read it; alpha's and beta's renders are byte-identical (they enable REST).
8. **The six Ledger rows move to a new status `trial` in the bump, not to
   `beta`** (§1 D2170, ADR 0261): an operation type must be ACCEPTED on the
   deployed commit for the trip to measure it, while the guard forbids a `beta`
   row whose evidence has not passed. `trial` is accepted, says *being verified*
   in its customer text, is legal only in the session that introduced its
   claims, and the close moves each row to `beta` (claims passed) or back to
   `planned` (they did not).

---

## 0. Where the session starts

```
HEAD            87b80bf on main, local = origin ("Session 37 Run 12: the gate
                passed and CI is green on d0936a2 (record)"). Deployed: c3eec1d
                (1.15.0) on all three projects; the tag 1.15.0 names c3eec1d.
                `git diff --name-only 1.15.0..HEAD` filtered to src/ bin/
                services/ migrations/ templates/ schemas/ compose.yaml names ONE
                file: src/agentic_postgres/capacity.py (Session 37's envelope
                rows, d0936a2) -- records only.
VERSION         1.15.0. CURRENT_SESSION 37 (src/agentic_postgres/__init__.py:960;
                Session 37's paragraph :893-959). Outputs schema 20
                (deployed_output.py:40; READABLE_PREVIOUS_VERSION = SCHEMA_VERSION
                - 1 :823; output_migrations.CURRENT_VERSION :104, last step
                migrate_v19_to_v20 :1428-1463). Project manifest 1-9
                (config.py:64; schema enum schemas/project.schema.json:16-29; v9 =
                `control`, gate :1011-1030; PROJECT_CONTROL_FROM = 9 config.py:88).
                host.yaml schema 2|3 (schemas/host.schema.json:9-23). Capability
                manifest 4, lock 4, project lock 3, api-surface 2. 39 released
                migrations; the control set 3 (20261004120001-3).
REGISTRY        312 requirements (tests/acceptance-registry.yaml, 6,385 lines;
                Session 37's block :6125-6385 under `# Session 37 (ADR
                0251-0254)`). 219 claims (evidence_claims.py CLAIMS :396-1219,
                Session 37's :698-716), 74 declared offline (OFFLINE_CLAIMS
                :106-349, Session 37's :325-347); mode split 137 host / 74
                offline / 8 external. CLAIM_INTRODUCED_IN
                tests/contract/test_evidence_claims.py:953-1253 (== CLAIMS at
                :1403). ID regex tests/contract/test_acceptance_registry.py:114
                (ends `...|LEDGER|CTL|KEY)-...`; family comments :43-113, CTL/KEY
                :111-113); five keys :190; target_session <= CURRENT_SESSION
                :200. 255 ADRs. NEXT FREE: D2145, ADR 0256.
EVIDENCE        evidence/session-37.json (gitignored): 219 claims, 217 passed,
                1 not_run (replacement_host_restore, D1028), 1 failed
                (documented_path, D1935). Copies in WSL ~/s37/run11/evidence/.
HOST            62.238.99.122, Hetzner CX23 (3,814 MiB, 2 vCPU, 38 GB, no swap),
                booted 2026-10-07 08:40:02Z, checkout ~op/agentic-postgres =
                c3eec1d. alpha-dev, beta-dev, control-prod at 1.15.0. doctor
                capacity 912 MiB committed of 1,600; 1,624 MiB available. Four
                units enabled (edge + three projects). Infisical free plan: FOUR
                machine identities, all used (Session 37 Run 10's Done).
                *.agenticpostgresql.com is a PROXIED wildcard (D2083).
OPERATOR        2026-10-07: stay on the CX23, one customer slot, the rescale or
                a move owed before Session 41 (D2145); upgrade the Infisical plan
                (D2146); idle sleep deferred to Session 41 (D2147); an explicit
                grey A record per slot (D2148).
```

**What exists, measured at `87b80bf`, and the session builds on:**

- **The operation table Session 37 left empty.** `services/auth-api/app/operations.py`
  (standard library only): `OPERATION_TYPES` `:29-41` maps eleven types to
  Ledger rows (`project.create` → `projects_self_service`, `project.delete` →
  `project_deletion`, `project.sleep`/`project.wake` → `sleep`,
  `project.resize` → `compute_profiles`, `project.export` → `export`, three
  `branch.*` → `branches`, `restore.create` → `restore_to_branch`,
  `credential.rotate` → `direct_endpoint`); **`ACCEPTED_TYPES = frozenset()`
  `:45`**, written by hand because the image cannot read the Ledger (`:9-18`);
  `is_accepted` `:48-50`. `src/agentic_postgres/operations.py` loads it through
  `service_source.load` (`:20`), `ACCEPTING_STATUSES = {"available","beta"}`
  `:26`, `row_status` `:31-38`, `accepted` `:41-43`. The guard
  `tests/contract/test_reality_ledger.py:141-174` holds `ACCEPTED_TYPES` equal to
  the Ledger's answer and the control set's CHECK list equal to the table.
- **The control set** (`projects/control/migrations/templates/0001-0003`, each
  `SET LOCAL ROLE {{object_owner}}`, an `AP900` down). **`app.control_operations`**
  (0003 `:29-47`): `id uuid PK`, `organization_id uuid NOT NULL REFERENCES
  control_organizations`, `project_key text NULL` (no FK), `type` CHECK of the
  eleven (`:34-38`), `status` CHECK `pending|running|succeeded|failed|cancelled`
  (`:39`, no default), `progress integer 0-100 DEFAULT 0`, `requested_by uuid
  NOT NULL` (no FK), `arguments jsonb NOT NULL`, `error_code text NULL`,
  `created_at`, `started_at`, `finished_at`; **no claimant, lease, attempt,
  step or result column; no index but the PK; no `SKIP LOCKED` anywhere.**
  **`app.control_projects`** (0003 `:17-27`): `key` PK with CHECK
  `^[a-z][a-z0-9-]{2,30}-[a-z][a-z0-9-]{1,15}$`, `organization_id`, `slug`,
  `environment`, `domain`, `template_version`, `source_commit`, `adopted_at`,
  `adopted_from` CHECK `= 'deployed_document'`. Both FORCE RLS (`:49-52`) with
  SELECT policies only (`:57-72`); *"No function inserts an operation"*
  (`:10-14`). Functions: the read pair `control_list_operations`/`control_get_operation`
  (`:115-154`, granted to `auth_service`), `control_adopt_project` (`:161-182`,
  INVOKER, granted to nobody, upsert refreshing `adopted_at`) and
  `control_registry_rows` (`:186-201`, INVOKER, nobody). The project lock
  `projects/control/migrations/released.lock.json` (`follows_release_version
  20261003120039`, schema 3); the committed proposal
  `projects/control/proposals/14699bf6…json` (D2136 — **a new control-set
  version needs a new committed proposal**, ADR 0243).
- **The management API** (`services/auth-api/app/control_routes.py`,
  `APIRouter(prefix="/v1")` `:53`; one `_guard` `:119-134`, `no-store` on
  every answer). **`POST /v1/projects`** (`:671-690`) never reads its body and
  calls `ControlService.create_project` (`control_service.py:549-563`), which
  raises `ControlRefused(NOT_AVAILABLE, ledger_row=…)` → **`409
  {"error":"not_available","ledger_row":"projects_self_service"}`**
  (`errors.py:221`, `:235`, `:239-256`; `models.NotAvailableResponse`
  `:620-624`); a key gets `403 human_session_required` first (`control_service.py:241-243`).
  `GET /v1/operations?organization=` (`:710-729`, organisation required) and
  `GET /v1/operations/{operation}` (`:732-746`), `viewer`, key scope
  `operations:read`. **Roles** (`control_roles.py`): `MATRIX` `:45-78` keyed by
  handler name; `KEY_VOCABULARY` = `members:read, operations:read,
  organizations:read, projects:read` (`:83-88`); **`ROLE_SCOPES` uniform
  `:94`** — *"Session 38 gives `member` `projects:write`"* (`:90-93`, D2109);
  `KEY_SCOPES` `:100-108`. The keys table's CHECK `scopes <@ ARRAY[…the four…]`
  (0002 `:31-34`) — *"each later session widens this CHECK"* (`:29-30`). The
  contract `contracts/control-openapi.canonical.json` has 20 paths (`/v1/projects`
  get+post `:1512`, `/v1/operations` `:628`, `/v1/operations/{operation}` `:697`).
- **`bin/control.sh|py`** (root): `adopt`, `registry`, `totp-reset`; the control
  project found by `document["control"]["enabled"]` (`find_control`
  `control.py:154-176`; exit 5 for two, 6 unreadable, 3 none); psql through
  `container_exec.run(container, "psql", "-U", "postgres", "-d", db, "-X",
  "-qtA", "-v", "ON_ERROR_STOP=1", -v vars…, "-f", "-", input=sql,
  timeout=120)` (`:209-213`); `FIELDS = (slug, environment, domain,
  template_version, source_commit)` `:62`; `registry` outcomes `agrees`,
  `differs`, `not_in_registry`, `no_deployed_document`, `undetermined`
  (`:80-86`, `:304-326`), exit 6 > 5 > 0 (`:346-349`). **A deleted project's
  row would read `no_deployed_document` — a difference (exit 5)** (§1 D2167).
- **The deploy path** (`deploy.sh` → `bin/deploy-project.py` `main()` `:2247-3173`).
  Step 0 preflight (`:2285-2301`) then **admission** (`:2303-2336`,
  `capacity_probe.read(..., exclude=key)` → `capacity_reading.decide`, refuse
  **exit 12** `EXIT_ADMISSION_REFUSED`, `capacity_reading.py:89`, before
  anything is rendered); steps 1–7, 6b–6e (`:2338-3173`); exit codes 0 2 3 4 5
  11 12, plus an **uncaught `ReleaseError` → exit 1 on a dirty checkout**
  (`installed_release.py:101-112`, `deploy-project.py:2367`). **The TTY guard**
  (`bin/lib/tty-guard.sh:34-39`) refuses only *stdin a terminal AND stdout or
  stderr not*; **a process with stdin at `/dev/null` passes** (`deploy.sh:269-270`).
  The first deploy reads ports and `routes.app` `unavailable` (D326:
  `_live_allocation` `:2103-2152`; `observe_active_administrator` `:1439-1513`);
  `--render-runtime-only` (`:2155-2244`) PRINTS `sudo bin/database-ports.sh
  verify --host … --instance-uuid …` (`:2240-2243`), which needs no prompt
  (`database-ports.py:263-316`), and a further deploy publishes the ports.
  `observe_served_document` (`:3375-3428`) fetches PostgREST's document through
  `routes.rest` with certificate verification, retried 90 s
  (`observation.py:30,33`); `observe_api` (`:3431-3477`). **Ownership hand-back
  reads `SUDO_UID`/`SUDO_GID`** (`deploy-project.py:345`) and does nothing
  without them — a systemd-started root process has neither (§1 D2153).
- **The first administrator.** `bin/auth-admin.py bootstrap` reads the password
  from a TTY twice, or from **`--password-fd N`** (`read_password` `:140-167`);
  root; the `auth` container running; `AP409` on a second run → exit 5
  (`:348-354`). **The reset plane every project already has**:
  `app_private.password_resets` (`0026:83-105`, `token_hash ~ '^[0-9a-f]{64}$'`,
  one live reset per user), **`auth_open_password_reset(p_user_id uuid,
  p_issued_by uuid, p_token_hash text, p_expires_at timestamptz) RETURNS uuid`**
  (`0026:118-`, SECURITY DEFINER, granted to `{{auth_service}}` `:245-246`) —
  **it takes the HASH**; `auth_consume_password_reset(text, text)` (`:171-229`);
  the unauthenticated `POST /auth/reset-password {reset_token, password}`
  (`routes.py:661-685`, *"The SUBJECT chooses the password"*).
- **Providers and secrets.** `bin/bootstrap-providers.py --apply`
  (`:878-1014`): logs in with the two-line operator credential
  (`/root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential`,
  `deploy-project.py:839-842`), creates the Infisical project `key`, the
  identity **`{key}-runtime`** (`:885` — the free plan's limit, D1045's class),
  every generated secret, the credential files under
  `/etc/agentic-postgres/credentials/<key>/` (0400) and
  `/etc/agentic-postgres/projects/<key>/bootstrap-state.json` (0600); the
  Infisical organisation is the HOST's (`host.example.yaml:110-123`,
  `infisical.organization_id`). Operator-supplied: the storage pair at `/storage`
  (folder by hand), the backup pair at `/backup`, the mirror pair
  (`secrets.required.yaml:655-776`, `:983-1017`). **`--apply` does not shred the
  credential** (D2061). `bin/materialize-secrets.py` exits 8 on any missing
  required value (`:249-252`) and has **no last-known-good fallback** although
  the unit's comment says so (`systemd/agentic-postgres-project@.service:17-23`,
  §10).
- **Runtime verbs.** `bin/project-runtime.sh up|down|status|resume` (`:141`) —
  **no `stop`/`start`**; `up` materializes first (`:234-238`); `down` detaches
  the edge then `compose down` without `-v` (`:356-374`). The unit
  `agentic-postgres-project@.service` (`Type=oneshot`, `RemainAfterExit`,
  `ExecStart` materialize + up `:33-34`, `ExecStartPost` attach + edge reconcile
  `:35-36`, `ExecStop` detach `:41`, `ExecStopPost` down `:42`,
  `WantedBy=multi-user.target` `:55`); **no command enables it** (D2060). The
  backup timers' services `BindsTo=` the project unit
  (`systemd/agentic-postgres-backup-full@.service:9,11`). `bin/backup.sh
  … schedule enable|disable` (`:60-61`; enable refuses until a full backup
  exists, `backup_schedule.py:87-92`).
- **Retirement.** `bin/project-retire.sh --host --project KEY --confirm KEY
  --record PATH [--permanent|--before-expiry] [--destroy-data]
  [--operator-credential-file F]` (root, no TTY; `retirement.py:199-300`):
  record → down → disable-units → release-ports → edge-files →
  **provider-destroy** (needs the operator credential whenever
  `bootstrap-state.json` exists, `project-retire.py:219-224`) →
  remove-directories (state, secrets, rendered: `retirement.py:285-288`) →
  remove-volumes (only `--destroy-data`). **Never** the backup repository, the
  bucket, the stanza, the cipher pass, the Infisical project, DNS or the
  certificate (ADR 0187).
- **Admission and the profile's raw material.** `config.DATABASE_BUDGET_DEFAULTS`
  `:224-241` (shared_buffers 128, max_connections 56, work_mem 4, maintenance 64,
  memory_limit 768, shm 256); `unreclaimable_mb()` `:761-774` = shared_buffers +
  maintenance + max_connections × 2 (304 at the defaults);
  `SERVICE_RESOURCE_DEFAULTS` `:705-715` (pids/cpus, **no manifest override**);
  `SERVICE_MEMORY_LIMITS_MB` `:740-745`; `HOST_MEMORY_GUARDRAIL_MB = 1600`
  `:665` (a per-project database check); validators `_validate_memory_budget`
  `:1347-1382`, `_validate_auth_memory` `:1443-1470`, `_validate_connection_budget`
  `:1473-`. Manifest-overridable today: `database.{shared_buffers_mb,
  max_connections, work_mem_mb, maintenance_work_mem_mb, memory_limit_mb,
  shm_size_mb}` (schema `:194-235`), `api.app.{memory_limit_mb, pool_size}`,
  `api.rest.pool_size`, `storage.{memory_limit_mb, pool_size}`. Rendered into
  `compose.env` by `build_compose_env` (`rendering.py:1767-1776`, pids/cpus
  `:1855-1863`). `bin/admit.sh --host --project [--json]`, root, exits 0/2/3/12
  (`:20-24`). `capacity_probe.read` sums every project directory's
  `database.budget.unreclaimable_mb` (`capacity_reading.py:274-306`).
- **What the API layer already says about states.** Nothing: no state field
  exists on a project record; `control_projects` has none.
- **The REST flag (D2137/D2144).** `api.rest.enabled`'s ONLY reader is
  `config._validate_rest_service` (`:1542-1578`); `build_override` emits the
  PostgREST labels unconditionally (`runtime_override.py:743-749`,
  `_rest_labels` `:1574-1638`); the deploy observes REST whenever
  `through_session >= REST_PLANE_SESSION` (`deploy-project.py:2809`);
  `deployed_output.API_NOT_PUBLISHED` (`:76-86`); coherence: `api` ready needs
  `routes.rest` ready (`:906-914`); **`bin/doctor.py` and `diagnosis.py` read
  neither `api.status` nor the flag.** ADR 0062 (`:83`) refused making the
  postgrest SERVICE conditional on the flag — the container is not what moves
  here.
- **Isolation and the leaf classifier.** `evidence.ISOLATED_FIELDS` (`:37-71`,
  18 pointers); `test_every_leaf_is_classified`
  (`tests/deployment/test_session12_isolation_matrix.py:412-439`) is
  **`live_host` only**; categories `MUST_DIFFER` `:81`, `MUST_MATCH` `:134`,
  `RELEASE_STATE` `:171`, `NOT_AUTHORITY_PREFIXES` `:191`; **no offline test
  classifies every leaf** (D2142's class, three times).
- **Export's raw material.** No `pg_dump` caller anywhere (`bin/`, `src/`,
  `services/`, `libexec/`, `infra/`). Presigning exists ONLY in the storage
  service: `R2Adapter.presign_put` / **`presign_get`**
  (`services/auth-api/app/storage_client.py:294`, `:323`), with the project's
  own bucket and `/storage` credential; measured against R2 in Session 7
  (D344, D346; an expired presigned URL is refused `ExpiredRequest` 403, D362,
  boundary unmeasured).
- **Sleeping's raw material, measured.** A stopped container's LABEL router
  disappears and the edge answers its own **`404 page not found`, 19 bytes**,
  byte-identical to an unrouted host (D271, ADR 0085 `:30-45`); a FILE-provider
  service resolving a shared Compose name served project A to B's router 10 of
  10 (ADR 0085 `:62-80`) — **routes stay on labels**. Rig 35d: `docker stop` →
  2× 502, 1 timeout, then 404; `start` → 1.3 s of 404 then 200 (D1897).
- **The gate to derive from.** `bin/session-37-check.sh` (1,834 lines; header
  `:2-100`, `readonly SESSION=37` `:109`, `CONTROL_OUTPUTS`/`CONTROL_PROBE_FILE`
  `:166-167`, `usage` `:171-632`, `parse_arguments` `:668-872`, `mode_offline`
  `:1316-1533`, `mode_host` `:1535-1741` exporting `APG_CONTROL_OUTPUTS` `:1652`,
  `mode_external` `:1743-1823`, requiring `--ssh-destination` `:1748-1749`).
  `tests/contract/test_session_thirty_seven_gate_modes.py` (1,027 lines; `SESSION
  = 37` `:58`, `SESSION_PREVIOUS_NUMBER = 36` `:73`, claims table `:86-104`,
  offline-set assertion `:662-720`, control variables `:929-950`, usage-per-flag
  `:994-1027`). The environment roster `tests/conftest.py:86-199` (closed;
  Session 37's two at `:197-198`). `test_cli_contract.py`: `SHELL_COMMANDS`
  `:42-238`, `PYTHON_COMMANDS` `:240-312`, `COMMANDS_WITH_VERBS` `:496-530`, the
  secret-flag regex `:1136`.
- **The live modules to extend.** `tests/deployment/test_session37_control.py`
  (186 lines; `pytestmark` `:29-38`; the registry proof `:67`, the reboot proof
  `:150` with its own `APG_AFTER_REBOOT` marker `:143-149`);
  `tests/external/test_session37_public_control.py` (362 lines; three variables
  `:46-53`; `test_a_key_lists_projects_and_opens_no_project` `:281`).
- **What a slot does NOT have yet: anything.** `slot` in the project-slot sense
  has 0 hits outside `stage-5-plan.md` (`:263`, `:597-601`, `:902`, `:940`,
  `:999`).

**A stale citation, recorded so the executor does not chase it:** the
WORKSTATION checkout's untracked `host.yaml` is schema 2 (`host.yaml:15`), so an
admission run against it on the workstation refuses every new project — the
HOST checkout's copy is schema 3 (D2025, admission admitted control-prod in
Session 37). Rehearsals use `host.example.yaml`.

---

## 1. The divergence table

Six columns. Each row is a **measured fact about the tree at `87b80bf`** (or
about the host as Session 37's records left it) set against what the brief
says, with the decision this plan takes. **Next free number after this table is
D2189.** Rows the runs add go in a second table below it, in execution order.

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D2145** | Stage plan §5: *"Ends on the new host"*; scope-closure §30 item 5: *"The rescale (D2032), before 38's slots re-derive the reserve (D1992)"*; CLAUDE.md §3.0: *"ask before planning around a size"*. | CX23, 3,814 MiB, no swap; **1,624 MiB available, 912 of 1,600 committed** (capacity.ENVELOPE Session 37 row `:1146`). A project at the defaults is charged 304 and added ~521 MiB resident (2,145 → 1,624, the control project). CX33 is out of stock in `hel1` (D2032); a regular-plan CX33 costs the operator four times the cost-optimised one. | **The operator decided on 2026-10-07: plan Session 38 on the CX23 with ONE customer slot; the rescale or a move is owed before Session 41** (ClickStack), the operator's to schedule — a move is a recovery-path move of its own sitting (and the first chance to run `replacement_host_restore` to its end). The slot is created at the `small` profile (D2156); **stop if `s38-free.sh` reads available < 1,024 MiB after creation** (D2042's floor, kept). `reserve_memory_mb` stays 2,214 (D1992 is re-derived only when the size moves). | One slot proves the lifecycle; capacity is shown by admission refusing a larger profile (D2160). A second slot would push the machine under the floor admission does not read (D767). | 0221, 0222 |
| **D2146** | D1953: *"buckets, mirror bucket, Infisical project and secrets made by the existing bootstrap path"*. | `--apply` creates `{key}-runtime` (`bootstrap-providers.py:885`); the free plan's four machine identities are all used (alpha, beta, control-prod runtimes and the control-plane identity — Session 37 Run 10's Done); a fifth fails `POST /api/v1/identities` HTTP 400 after the Infisical project was made (D1046's orphan). | **The operator upgrades the Infisical plan before Sheet SL1 (operator, 2026-10-07)** — one identity per project, isolation kept. E0 records the plan change as the operator's statement; **SL1's `--apply` failing on the identity is a stop** (§9), never retried until the output is read (D1046). A second Infisical organisation and a shared identity are rejected (ADR 0257). | A shared runtime identity would let one customer's secrets be read with another's credential; a second organisation is code for a billing problem. | **0257** |
| **D2147** | Stage plan §5: *"Idle sleep as a per-project setting the reconciler acts on"*. | Idleness has never been measured as a signal (`pg_stat_activity` used only for connection counts, Session 10/32; `traefik_service_requests_total` read by `doctor usage`, Session 31, and absent until traffic, D769). | **Deferred to Session 41 (the operator, 2026-10-07)**, which builds the sampler that reads the same counters. A new Ledger row **`idle_sleep`** (`planned`, `target_session: 41`, `controls: []`) is written in Run 4; the `sleep` row's text says suspension is by request only. | A trigger reading two unmeasured counters is the session's riskiest reader; the sampler that owns them is 41's. | 0254 |
| **D2148** | D1953: slots *"recorded in `host.yaml`"*; D2083: the proxied wildcard. | No code creates DNS (`fleet-operations.md:125-127`, `:145-147`); HTTP-01 needs a grey record at the host. | **An explicit A record per slot, DNS only, made by hand at the slot's provisioning (the operator, 2026-10-07)**: `slot1.agenticpostgresql.com → 62.238.99.122`, no AAAA. `bin/slot.sh status` reads it (A = the host's `host.public_ipv4`, AAAA empty, from the host with `dig @1.1.1.1`; no `dig` → `could not determine`) and a slot is `ready` only with it. The wildcard is untouched. | The same check Session 37's C1 gate used (D2083), now a product reader. | **0257** |
| **D2149** | D1953 (c): *"a customer project is created into a slot … recorded in `host.yaml`"*; §5: *"host schema 4 (`region`, `slots: [{key, state}]`)"*. | `host.yaml` is the operator's input (`host_config.load_host_manifest` `:75-81`, schema `[2,3]`); TWO copies are read (`/etc/agentic-postgres/host.yaml` by materialize and the launcher, the checkout's by admission and doctor — D2020/D2025). A state field in an operator file would be written by root at runtime. | **Host schema 4 adds `region` (D2161) and `slots`: a list of `{key, domain}` declarations plus `slots.defaults` (the provider facts a slot manifest copies — named in Run 3 from the project schema's required `storage`/`backup`/`mirror` members, the way `s37-controlyaml.py` copied them, D2123/D2124).** **No state in `host.yaml`.** A slot's state is DERIVED by `slot.state()` from four readings, each with three outcomes: declared in `host.yaml`; prepared (`/etc/agentic-postgres/slots/<key>/manifest.yaml` + the project's `bootstrap-state.json` + an active secret generation); occupied (a deployed document, or an allocation row the reconciler wrote); **consumed** (the tombstone `/etc/agentic-postgres/slots/<key>/consumed`, 0600, written by deletion, removed by no command). States: `declared`, `prepared`, `ready` (prepared + DNS), `allocated`, `quarantined` (an interrupted creation, D2152), `consumed`, `undetermined`. Schema 4 is migratable (absent `slots` = none); both copies move on Sheet H1, diffed (D2020). | A state derived from what exists cannot drift from it; a field root rewrites in an operator's file is a second source of truth. | **0257** |
| **D2150** | §5: *"`bin/slot.sh provision --key sN` (the operator's, root, wrapping `bootstrap-providers` and the bucket steps a human does today)"*. | `bootstrap-providers --apply` needs the operator credential on disk (`:251-268`) and prints the operator-supplied list (`:228-239`); the buckets, tokens and DNS are console work (ADR 0110). A wrapper cannot do the console half. | **`bin/slot.sh` (root) has three verbs, none of which holds a provider credential beyond the one `bootstrap-providers` already reads**: `prepare --host F --slot KEY` writes `/etc/agentic-postgres/slots/<key>/manifest.yaml` (0600) from `slots.defaults` + the declaration + profile `small` + the host's region, through `config.load_project_manifest` (refuses a slot already prepared, consumed or undeclared); `status [--json]` prints every declared slot's derived state with its reason (exit 0 all determined, 6 any undetermined); `revoke --slot KEY --operator-credential-file F --confirm KEY` runs `bootstrap-providers --destroy` against the KEPT bootstrap state of a consumed slot (D2158). **Provisioning is a sheet** (SL1–SL3): the consoles, `prepare`, `bootstrap-providers --plan/--apply` with the slot's manifest, the shred, the pastes, `materialize-secrets`, `status` → `ready`. | The bootstrap path is the one that already exists and is measured; a wrapper that pretended to do the console half would be the first fake-complete command. | **0257**, 0110 |
| **D2151** | D1953 (b): *"claims one operation at a time through a definer function reached by `container_exec.run` … no network listener"*. | `bin/control.py` already reaches the control database exactly this way (`:209-213`) with functions granted to nobody and executed by the superuser (D2093: INVOKER, because a DEFINER owned by `object_owner` is bound by FORCE RLS with no caller to scope by). | **`bin/reconciler.py` + `bin/reconciler.sh run|once|status|install`**, root; the unit **`systemd/agentic-postgres-reconciler.service`** (`Type=simple`, `Restart=on-failure`, `RestartSec=30`, `WorkingDirectory=` the checkout, `StandardInput=null`, `After=`/`Wants=` docker + the control project's unit; installed and enabled by `reconciler.sh install` on Sheet RC1 — `provision-host.sh` is not edited). It finds the control project with `bin/control.py`'s `find_control` (moved into `src/agentic_postgres/control_registry.py`, both commands importing it — ADR 0093). **Four new functions in the control set's `0004`, INVOKER, granted to nobody**: `control_claim_operation(p_worker text)` (`UPDATE … SET status='running', started_at=now(), claimed_by=p_worker, attempt=attempt+1 WHERE id = (SELECT id … WHERE status='pending' ORDER BY created_at, id FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING …`), `control_advance_operation(p_id, p_step, p_progress)`, `control_finish_operation(p_id, p_status, p_error_code, p_result jsonb)` (refuses a terminal row, refuses `p_result` keys outside the type's declared result members), `control_interrupted_operations()`. Poll every 5 s; one operation at a time host-wide. **No socket, no port**: OPN-LIVE-001 reads the unit's process tree for listeners (`ss -lntup` filtered by its pids) and requires none. | The control plane's own data is reached by the one path already reviewed for it; a listener would be a second door into a root process. | **0256**, 0218 |
| **D2152** | §5 *Measures*: *"the reconciler killed mid-operation and restarted (the operation resumes or fails with its reason, never runs twice)"*. | A creation is NOT idempotent end to end: `auth-admin bootstrap` refuses a second run (`AP409`, `auth-admin.py:348-354`); a half-made deploy leaves a state directory admission then reads (D2135). | **Never resume.** At start, before its first claim, the reconciler reads `control_interrupted_operations()` (status `running`) and finishes each as **`failed`, `error_code interrupted`, `result {"step": <last step>}`**; a `project.create` so interrupted marks its slot **`quarantined`** (a file `/etc/agentic-postgres/slots/<key>/quarantined` with the operation id) — not free, never reissued without the operator (`slot.sh status` names it; §10). Every other type interrupted leaves the project as it is and its state reads `unknown` (D2159). Rig 38f measures it: two concurrent claimers get distinct rows (SKIP LOCKED); a reconciler killed between claim and finish, restarted, finishes the row `interrupted` and claims nothing twice (control: an uninterrupted one `succeeded`, attempt 1). | Running a creation twice is the failure the brief names; failing closed and saying where is ADR 0195's decision half. | **0256**, 0195 |
| **D2153** | — | `deploy-project.py`'s ownership hand-back reads `SUDO_UID`/`SUDO_GID` (`:345`) and silently skips without them; a systemd-started root deploy would leave `.generated/<key>` and git's index root-owned (D1110), breaking `op`'s next render and bundle fetch. | **The reconciler's child environment carries `SUDO_UID`/`SUDO_GID` = the checkout directory's owner** (`os.stat(checkout).st_uid/st_gid`, refused if that is root) — named in `reconciler.py` with this row's number — and Run 6's proof reads that a recorded deploy argv ran with them. Rig 38a reads, on the workstation, that `deploy.sh --render-only` run as root with the two variables set hands `.generated/<key>` back (control: without them it stays root-owned). | The hand-back exists and is keyed to the operator who owns the checkout; the reconciler is acting for that operator. | **0256** |
| **D2154** | D1953 (a): *"a typed `arguments` object validated by a JSON Schema per type"*; §5 *Must not*: *"Accept a free-form command, path or shell fragment in any operation's arguments"*. | `arguments jsonb NOT NULL` (0003) with no schema; nothing validates it. | **`schemas/operation-arguments.schema.json`**, one `oneOf` branch per accepted type, `additionalProperties: false` everywhere, every string a pattern: `project.create {name ^[A-Za-z0-9 ._-]{1,48}$, profile enum, admin_username ^[a-z][a-z0-9_.-]{2,62}$, handoff_sha256 ^[0-9a-f]{64}$}`; `project.resize {profile enum}`; `project.sleep|wake|export|delete {}` (the project is the row's `project_key`). **Validated twice**: by the control mode before the row is written (pydantic, `extra="forbid"`), and by the reconciler before dispatch with the same schema file — a row that fails is finished `failed`, `invalid_request`, nothing run. The dispatch table (`src/agentic_postgres/reconciler_dispatch.py`) maps each accepted type to ONE function building an argv LIST; an AST guard refuses `shell=True`, `os.system`, `os.popen`, string `subprocess` calls and any argv element formatted from `arguments` except the validated `profile`/`admin_username` values (a recorder test reads every argv built). | The agent plane's lesson moved to root: no input accepts a command (ADR 0050, 0178). | **0256** |
| **D2155** | D1956: *"sleep stops the project's data-plane containers (`docker compose stop`, volumes and containers kept)"*; *"what a caller sees while it sleeps is measured"*. | `project-runtime.sh` has no `stop`/`start` (`:141`); the unit's stop path is `down` (containers REMOVED) and its start path materializes from Infisical (`:33-42`), which has no fallback (§0). The backup services `BindsTo=` the project unit, so a timer firing starts the project (systemd's semantics — a sleeping project would wake at 02:00 Sunday). The measured caller's view: Traefik's 404 (D271, D1897). | **`project-runtime.sh stop`** = `edge-network.sh detach` then `compose.sh … stop` (containers kept) and **`start`** = `compose.sh … start` + the health wait the `--wait` of `up` gives + `edge-network.sh attach` — **no materialize, no build, no recreate**. `project.sleep` = `backup.sh … schedule disable`, `systemctl disable agentic-postgres-project@KEY` (no `--now`: the unit stays active), `project-runtime.sh stop`; `project.wake` = `start`, `systemctl enable`, `schedule enable`. **No fallback body**: the caller gets the edge's 404; `/v1/projects/{key}` says `sleeping` (D2159); the Ledger's `sleep` row says both and that **a sleeping project's archiver is stopped, so its last restore point is its sleep time**. Rig 38b measures it (below). A reboot while asleep: the unit is disabled, so the project stays stopped — OPN-LIVE-001 reads nothing about it (§10). | Stop/start is the brief's own bonsai; re-reading secrets on wake would make wake depend on the provider's rate limit (D2139) for no reason. | **0259** |
| **D2156** | D1955: *"A profile is a named, versioned set of the values a manifest can already carry plus pids and cpus … the numbers are derived on the new host in Session 38's Run 1 … absent = today's defaults, which become profile `standard`"*; manifest schema 9 → 10 (D2044). | The values a manifest carries (§0) and validators that bound them; pids/cpus not overridable. | **`services/auth-api/app/compute_profiles.py`** (standard library; the image needs the names for validation — D2110's pattern) loaded by **`src/agentic_postgres/compute_profiles.py`** through `service_source.load`; three profiles **`small`, `standard`, `large`**, each the database budget members, `api.app.memory_limit_mb`, `storage.memory_limit_mb`, the three pool sizes, and a pids/cpus map over `SERVICE_RESOURCE_ORDER`. **`standard` = today's defaults exactly** (a test: a manifest with `compute: {profile: standard}` renders byte-identically to one with no `compute`). **`small` and `large` are derived in Run 1 (rig 38c) from E0's `docker stats` of the three running projects** with these rules, written into ADR 0258 with the readings: `small`'s charge (`unreclaimable_mb`) ≤ 200 and its sum of memory CAPS plus the three projects' resident leaves `available` ≥ 1,024; `large`'s charge > 688 (what admission has left on this host after the three) and ≤ `HOST_MEMORY_GUARDRAIL_MB`; every profile passes `_validate_memory_budget`, `_validate_auth_memory` and `_validate_connection_budget` (a test renders each). **Manifest schema 10 adds `compute: {profile}`** (optional, forbidden below 10 — the `:1011-1030` shape; `PROJECT_COMPUTE_FROM = 10`); **a manifest naming `compute` may not also set a member the profile owns** (refused by name). `rendering.build_compose_env` reads the profile for the pids/cpus members. **Storage reservation is not a field** (the Ledger: no per-project disk quota exists). | Every value in a profile is a value a deploy already enforces; numbers from the specification would be values that look measured. | **0258** |
| **D2157** | D1976: *"the resize message quotes the class windows measured"*; §5 *Must not*: *"Print a restart window nobody measured"*. | A profile change moves `POSTGRES_MEMORY_LIMIT` (`rendering.py:1847`) and the app/storage limits, so the deploy recreates postgres and its dependents — a window never measured (the envelope's database row `:794` is an INDUCED restart, 3.1 s at REST). | **`compute_profiles.RESIZE_WINDOW_SECONDS = None`** until a measured envelope row exists; the `202` body and `bin/compute.sh set` print *"Resizing restarts the database and the services that use it; the restart has not been measured on this server yet."* while it is `None`, and the measured sentence once it is set. **Run 13 sets it from the trip's resize row** and a test holds the constant equal to that row's value (or `None` with no row). The deployed 1.16.0 prints the unmeasured sentence; Session 39's release carries the number. | The honest sentence exists before the number does. | **0258** |
| **D2158** | D1972: *"`project.delete` runs `project-retire.sh --destroy-data` against the project's slot and then marks the slot consumed"*; §5 *Must not*: *"Give the reconciler … a provider-administering credential"*. | `provider-destroy` needs the Infisical org-admin credential whenever bootstrap state exists (`project-retire.py:219-224`); the docs shred it after use (D2061); `remove-directories` deletes the state directory, which holds `bootstrap-state.json` (`retirement.py:285-288`), so a later revocation could not find the identity. | **`project-retire.sh --defer-provider`**: every step but `provider-destroy`; **before `remove-directories`, `bootstrap-state.json` is moved to `/etc/agentic-postgres/slots/<key>/retired-bootstrap-state.json` (0600)** and the local credential files under `/etc/agentic-postgres/credentials/<key>/` are removed; the record says *"provider resources deferred to `bin/slot.sh revoke`"*. `--defer-provider` and `--operator-credential-file` are mutually exclusive. `project.delete` = `--permanent --destroy-data --defer-provider`, then the tombstone `consumed`. **The operator revokes later** on Sheet SL4 (`slot.sh revoke`, the credential placed and shredded). The Infisical project, the buckets, the backup repository and the DNS record stay (ADR 0187); the identity stays until SL4. | The reconciler never holds the org-admin credential; the one act that needs it is the operator's, deferred and named. | **0257**, 0187 |
| **D2159** | D1953: *"Resource states are derived from the operation history plus the deployed document plus the doctor's readings, three outcomes each"*; spec §46's nine states. | No state exists; the control plane can read no doctor (it holds no credential to the node, ADR 0246). | **The state is derived in the control mode from the project's operation history alone**, by one pure function `control_states.project_state(ops)`: latest operation running — create → `creating`; sleep running → `suspending`; wake running → `starting`; resize running → `updating`; export running → `ready` (export does not interrupt); delete running → `deleting`; latest terminal succeeded: create/wake/resize/export → `ready`, sleep → `sleeping`, delete → `deleted`; latest failed `capacity_exhausted` or `invalid_request` → the state before it; **latest failed `interrupted` or `could_not_determine` → `unknown`** (the third outcome); a project adopted with no operation (alpha, beta, control) → `ready (operator-managed)`. `degraded` and the doctor's readings are **not** built (Session 42's support bundle reads the doctor); the Ledger says so. | The operation history is the one record the control plane owns; reading the doctor would need the credential the boundary forbids. | **0256**, 0195 |
| **D2160** | D1954: *"the reconciler runs `bin/admit.sh` for the slot's rendered profile and maps exit 12 to `capacity_exhausted` with 'No resources were created' … Neither code may be produced by the other's reader"*; §10: *"`capacity_exhausted` with the reason *no prepared slot*"*. | No entitlement exists (41). Slot stock is host-side; the control plane cannot read `host.yaml`. | **One code, two readers, both named in the body**: `capacity_exhausted {reason: "no_slot"}` from the API **before any operation row is written**, when `app.control_slots` (written by the reconciler from `slot.state()` at start and after every operation: `key`, `state`, `observed_at`) holds no `ready` slot; and `capacity_exhausted {reason: "admission"}` as an operation's `error_code` + `result {"refusal": <admission's printed reason>}` when `admit.sh` exits 12 — **checked before anything is rendered or allocated**, so the slot returns to `ready` and the message is *"No resources were created."* A stale slot reading (older than 10 minutes) refuses with `capacity_exhausted {reason: "no_slot"}` and the body says the reading was stale. **`plan_limit_reached` does not exist in 38**; a test asserts no string in `services/`, `src/` or `bin/` produces it. | Two refusals that a customer cannot tell apart would be one more surface claiming less than the node knows; a stale reading is not a slot. | **0256**, 0221 |
| **D2161** | D1957: *"One region object, declared by the operator in `host.yaml` (`region: {id, display_name, provider, location}`, host schema 4) … carried into every project's deployed document and the control plane's `regions` table, and read — never typed"*. | `host.yaml` names no region; the Ledger `region` row (`:211-225`) says one location. | **Host schema 4's `region: {id, display_name, provider, location}`, required at 4**; the operator's values on Sheet H1: `id eu-hel-1`, `display_name "Helsinki, Finland"`, `provider Hetzner`, `location hel1` — read from the Hetzner console and confirmed by the operator, never inferred. **Outputs schema 21 carries `region` (the four members) and `compute.profile`** (D2162) in every deployed document; `migrate_v20_to_v21` (`region: null`, `compute: {profile: "standard"}` for an archived document — a null region is an *unknown*, refused by every reader that needs it). `control_projects` gains `region_id` and `profile`, written by the reconciler from the deployed document and by `control.sh adopt`; `control_slots` carries the region of each slot for a creation's answer; **no `regions` table** (one host, one region — a table of one row nobody else writes would be a declared field with no second reader). | A region is real exactly when it is the operator's declaration of where the machine is. | **0257**, 0158, 0241 |
| **D2162** | Stage plan §7 item 3: *"Every new deployed-document field is classified in the isolation matrix in the session that adds it"*; scope-closure §30 item 3: *"an offline leaf-classification check (D2142)"*. | `test_every_leaf_is_classified` is live-only (`test_session12_isolation_matrix.py:412-439`); three facility flags reached a sweep unclassified (D1029, D1853, D2142). | **Run 2 moves the four category tables into `src/agentic_postgres/isolation_matrix.py`** (the live module imports them, unchanged in substance) **and adds `tests/contract/test_isolation_leaves_offline.py::test_every_leaf_of_a_built_deployed_document_is_classified`**: a deployed document built by `deployed_output.build_deployed_document` from each of the four fixture renders with every route `ready` and every optional block present, every leaf classified (control: a planted unknown leaf fails it). Run 3's `region.*` (MUST_MATCH — one host) and `compute.profile` (NOT_AUTHORITY) are classified by it the day they are added. | A guard that runs only live finds its new case one trip late, every time (D2142's sentence). | 0251 |
| **D2163** | D1969: *"at `project.create` the reconciler bootstraps the creating member as the project's first `project_admin` … the one-time secret is shown once to that member"*; ADR 0246: *"the control plane holds nothing that opens a project's data or admin plane"*. | Showing a secret to the member through `/v1` means it transits the control database (the reconciler is pull-based), which would make the control plane a holder of a credential to the project's admin plane, however briefly. **`auth_open_password_reset` takes a HASH** (`0026:118`); `/auth/reset-password` lets the subject choose the password (`routes.py:661-685`). | **The handoff by hash.** `bin/project.sh create` generates `T = secrets.token_urlsafe(32)` (43 characters, the `one_time_tokens` shape), writes it to `$XDG_CONFIG_HOME/apg/handoffs/<operation-id>` (0600; the D2066 state rules) and sends only `handoff_sha256 = sha256(T)`. The reconciler, after the first deploy: `auth-admin.sh bootstrap --username <admin_username> --password-fd N` with a random 32-byte password it writes to a pipe and never stores; reads the new user's id; calls, as the superuser in the PROJECT's database, `SELECT app_private.auth_open_password_reset(:'user', :'user', :'hash', now() + interval '24 hours')`; the random password is now useless to anyone (nobody holds it). **`bin/project.sh claim --project KEY`** presents `T` to the project's `{routes.app}/auth/reset-password` with a new password from `--password-file` or a TTY, then deletes the handoff file. Rig 38c measures it end to end on a Docker cluster with the release set (control: a wrong `T` → refused; a second consume → refused; a reset opened with the hash of `T` is consumable only with `T`). **`T` reaches the control plane never; `sha256(T)` opens nothing.** | The control plane holds a hash of a 256-bit secret, which is what it already stores for keys and invitations (ADR 0253); the stage plan's *"shown once"* becomes *"never shown to the control plane at all"*. | **0260**, 0246 |
| **D2164** | D1972: *"`project.export` runs `pg_dump -Fc` of the customer's schemas (never `app_private`) … writes the archive into the project's own storage bucket, and returns a presigned URL valid 15 minutes"*. | Presigning exists only inside the storage service with the project's own `/storage` credential (`storage_client.py:294-336`). A presigned URL is a bearer credential to the object (D358). The reconciler is pull-based, so the URL transits the control database. | **Export in three steps, no credential leaving its container**: (1) `container_exec.run(<db container>, "pg_dump", "-U", "postgres", "-Fc", "-n", "app", "-n", "api", "--no-owner", "--no-privileges", "-d", <db>)` with stdout written to `/var/lib/agentic-postgres/exports/<operation-id>.dump` (root 0600; the directory 0700, made by `reconciler.sh install`); (2) the file streamed into the project's **storage container** to a new module **`app/export_upload.py`** (`python -m app.export_upload --key exports/<operation-id>.dump`, stdin = the archive) which puts it with the container's own `R2Adapter` and prints ONE line: a presigned GET valid **900 s**; (3) the local file removed. The URL goes into the operation's `result.download_url` and **`GET /v1/operations/{id}` returns it ONCE to the requesting member and erases it in the same transaction** (`control_take_result_secret`, granted to `auth_service`); it is never logged (the request log prints route templates, ADR 0253) and never in a list answer. **This is the one credential-shaped value that crosses the control plane, bounded to ≤ 900 s, to one object, read-only, and erased on first read** — ADR 0259 states the residual (the value is in the control database's WAL and backup until the URL expires). Rig 38d measures `pg_dump -n app -n api` (control: without `-n` the archive lists `app_private`); the presign and the expiry are measured on the host on day 2 (Run 12, control: a URL past 900 s → 403). | The customer asked for the archive; the bound is the expiry, which is the provider's and was measured (D362). The alternative — the export downloaded through the project's own storage API as its admin — needs an object-ownership path that does not exist and is priced at Session 40 with the backups surface (§10). | **0259**, 0246 |
| **D2165** | D2052: *"Credential-minting routes are human-session only"*; D2109: *"Session 38 gives `member` `projects:write`"*. | `KEY_SCOPES` reaches seven read routes (`control_roles.py:100-108`); `projects:write` exists only in comments and one negative test. | **The 38 vocabulary adds `projects:write`** (keys' CHECK widened in `0004`). `ROLE_SCOPES`: `viewer` reads only; `member`, `admin`, `owner` + `projects:write`. Routes: `POST /v1/projects` (create) — member+, **human session only** (it starts the admin handoff); `POST /v1/projects/{key}/sleep\|wake` and `PUT /v1/projects/{key}/compute` (resize) — member+, **a key with `projects:write` allowed**; `POST /v1/projects/{key}/export` — member+, human session only (it yields a download URL); `DELETE /v1/projects/{key}` — **admin+**, human session only; `POST /v1/operations/{id}/cancel` — the requester or admin+, only while `pending` (D2067's owed route). **D2109's test now sees a real difference** (`viewer` vs `member`), and its uniformity assertion is replaced by the exact table. | A key that can stop and start a project is an automation key; a key that can create a project or download its data is a door. | **0256**, 0253 |
| **D2166** | ADR 0246 / scope-closure §30: *"No rate limit on `/v1/sessions` or invitation acceptance … ADR 0246's scope sentence puts rate limits on the creation paths (38)"*; threat item #4. | Nothing rate-limits anything in `/v1`. | **The creation path is bounded by stock and by serialisation, not by a time window**: at most ONE non-terminal operation per project (a second → `409 conflict {"operation": id}`), at most ONE non-terminal `project.create` per organisation (`409 conflict`), and the slot stock (D2160). **No time-window rate limit is built** (none exists in the tree; ADR 0256 says the stock is the bound and that `/v1/sessions` stays unthrottled — §10). | A beta with one slot cannot be exhausted faster than its stock; a rate limiter nobody measured is a control that looks complete. | **0256** |
| **D2167** | D2141: *"Whether a deploy should refresh its own row is Session 38's (`project.*` operations own the registry there)"*. | `adopt` is root's and a row is a snapshot (D2141); `registry` reads a deleted project's row as `no_deployed_document` → exit 5 (`control.py:304-326`), which would turn `CTL-REG-002` red the day a project is deleted. | **The reconciler refreshes its project's row after the LAST deploy of every operation** (the same `control_adopt_project`, extended in `0004` with `p_region`, `p_profile`, `p_slot`) and **`project.delete` sets `deleted_at`** (`control_mark_deleted(p_key)`, INVOKER, nobody). `registry` gains one outcome: a row with `deleted_at` and no deployed document and a `consumed` tombstone **`agrees (deleted)`**; with a deployed document still present → `differs: deleted`. Alpha, beta and control-prod stay operator-adopted (Sheet A1 re-run after the release deploys, D2141). | The registry is the control plane's own record of what exists; deletion is part of what exists. | **0256**, 0251 |
| **D2168** | Stage plan §10: *"Only one control project per host … Session 38's reconciler will need the same rule"*. | `find_control` refuses two (exit 5, `control.py:154-176`). | **The reconciler uses `find_control` (moved to `src/agentic_postgres/control_registry.py`) and exits 5 at start with two**; the unit's `Restart=on-failure` then retries every 30 s and `reconciler.sh status` says why. | One rule, one implementation. | 0251 |
| **D2169** | §5: *"`apg project create\|delete\|sleep\|wake\|export`, `apg compute get\|set`, all over `/api/v1`"*. | `bin/project.sh` has `list\|use\|show` (Session 37); the CLI's state rules (D2066, D2120, D2121) are in `src/agentic_postgres/control_client.py` and `bin/cloud.py`. | **`bin/project.sh` gains `create --name N --profile P --admin-username U`, `claim --project KEY [--password-file F]`, `sleep`, `wake`, `export --output FILE`, `delete --project KEY --confirm KEY`, `status --project KEY`**; **`bin/compute.sh get|set --project KEY [--profile P]`**; **`bin/operation.sh show|list|wait|cancel`** (`wait --timeout S` polls `GET /v1/operations/{id}` every 5 s and exits 0 succeeded, 5 failed — printing `error_code` and the reason —, 6 when it could not determine, 7 on its own timeout). `export --output` downloads the one-time URL with `urllib`, no redirect followed (D2121's `_NoRedirect`), writes 0600, and prints the archive's sha256. Every verb `--json`. `test_cli_contract` gains two commands and the verbs. | The customer's door is the CLI the stage plan names; `operation` is the verb every async answer needs. | 0253 |
| **D2170** | ADR 0254: a type is accepted iff its row is `available` or `beta`; D2055/ADR 0254 amended: *"a row's STATUS moves in the run whose evidence makes it true"*; `test_available_and_beta_rows_name_evidence_that_resolves` (`test_reality_ledger.py:69-83`). | For the trip to measure `project.create`, the type must be ACCEPTED on the deployed commit — so its row must be `available`/`beta` there — while the guard requires a `beta` row's evidence to be `passed` in the newest evidence document, which for this session's claims exists only after the trip. Session 37 never met it (no type was accepted). | **A sixth Ledger status, `trial`** (`schemas/reality-ledger.schema.json` enum widened; `reality_ledger.STATUSES`; `operations.ACCEPTING_STATUSES` = `{available, beta, trial}`): *built in the current session and reachable while its evidence is collected*. The guard gains three rules: **a `trial` row's `evidence` must name only claims whose `CLAIM_INTRODUCED_IN` equals `CURRENT_SESSION`**, its `target_session` must equal `CURRENT_SESSION`, and its `customer_text` must contain *"being verified"*; **a `trial` row from an earlier session fails** (so a session cannot leave one behind). Run 10 (the bump) moves the six rows to `trial`; **Run 13 moves each to `beta` if every named claim reads `passed` in `evidence/session-38.json`, else back to `planned` with its operation types removed from `ACCEPTED_TYPES`**. ADR 0261 amends ADR 0254 and says the guard was widened by one status with three rules, never loosened for `beta`. | Accepting a type before its evidence is the only way to obtain the evidence; naming that state, bounding it to one session and making the close resolve it is the guard made stricter about the gap rather than blind to it. | **0261**, 0254, 0247 |
| **D2171** | §5 *Measures*: *"provisioning and deletion time (D1983)"*; *"the sleep/wake caller's view and cold start; the resize window per class"*. | None measured; the envelope's Session 37 rows are the model (`capacity.py:1136-1260`). | **Run 12's instrument `s38-lifecycle.py` times each operation from `202` to terminal** (the operation's own `created_at`/`started_at`/`finished_at`, read through `/v1`) and runs the probe (`s37-probe-start.sh` derived) across sleep, wake and resize; Run 13 writes **six envelope rows**: provisioning (create, end to end, with its steps' times from `result.steps`), deletion, sleep (time to the edge's first 404), wake (time to the first 200 — the cold start), resize `small → standard` per class (the window `RESIZE_WINDOW_SECONDS` takes, D2157), export (size and time); plus **memory with the slot** (`free -m` before and after creation). | Every number a customer is told is a row with its conditions. | 0244 |
| **D2172** | D2137/D2144: *"`api.rest.enabled: false` withholds the REST router … the repair reaches the deploy's served-document read, `api.status`, the doctor and the schema, and only a deploy measures it"*. | The readers (§0): `build_override` `:743-749`; the deploy's REST observation gated on the session only (`deploy-project.py:2809`); `API_NOT_PUBLISHED` `:76-86`; coherence `:906-914`; the doctor reads neither; ADR 0062 kept the SERVICE unconditional. | **Run 2**: `build_override(..., rest_enabled: bool)` (REQUIRED, the D2087 rule for a status-like argument) omits the PostgREST router labels when false — **the container still runs** (ADR 0062 stands); the deploy reads the flag from the rendered `compose.env` (new key `API_REST_ENABLED`, so the labels and the observation cannot disagree, D2087's pattern), and with it false **skips `observe_served_document` and records `routes.rest: unavailable` and `api: API_NOT_PUBLISHED`** with no wait; `deployed_output` gains a coherence rule refusing `routes.rest: ready` with the flag off. Proofs: a render with the flag off has no router whose service is postgrest (and the same render with it on does — the control); the fixtures (both REST-enabled) render byte-identically to `c3eec1d`'s. **Measured on control-prod's 1.16.0 deploy** (R2c): `/api/rest/` answers Traefik's 404, the document reads `routes.rest unavailable`, the deploy took no 90 s wait. **`storage.enabled: false` still emits storage's router** (D2144's second half) — §10, not this session's. | The flag gains its reader, and the reader is the one place both the router and the observation read. | **0251** (amended: §6 gains the paragraph), 0062 |
| **D2173** | Stage plan §5 *Measures*: *"the slot rig above"* — *"a pre-bootstrapped slot deployed by a non-interactive root process on the new host with stdin at `/dev/null` … every human dependency named with file:line"*. | Read at planning (§0, sixteen points): the TTY guard passes stdin `/dev/null`; `auth-admin` takes `--password-fd`; materialize, admit, verify, retire take no prompt; **what needs a human is the provider half (buckets, tokens, DNS, the Infisical credential, the pastes) and three hand acts after a deploy (the port `verify` line, enabling the unit, the first full backup)**. | **The provider half is the slot's provisioning sheet (D2150); the three hand acts become reconciler steps**: after deploy 1 → bootstrap + handoff (D2163) → `--render-runtime-only` → parse its printed `verify` argv **from the deployed document instead** (`--instance-uuid` read with `container_exec` the way `deploy-project.py:2064-2100` reads it — never a printed string executed) → `database-ports.sh verify` → deploy 2 → `systemctl enable agentic-postgres-project@KEY` → `backup.sh … backup --type full` → `schedule enable` → `mirror` → refresh the registry row → `succeeded`. Each step is a named `result.steps[]` entry with its seconds. **The live half of the rig is the first creation itself** (Run 12): every step recorded, any human act it still needed is a stop. | The rig the brief names is the creation; reading the code first is what lets the reconciler be written before the host is touched. | **0256** |
| **D2174** | — | The external half requires `--ssh-destination` (`session-37-check.sh:1748-1749`) for Session 4's two proofs; Session 37's customer proofs prove they never use it (D2058, D2133's scan). | **The 38 customer proofs read only `routes.control` and the slot's `routes.app` (from the lifecycle record), and D2133's scan is extended to the new module** with exactly these variables allowed: `APG_CONTROL_OUTPUTS`, `APG_CONTROL_PROBE_FILE`, `APG_LIFECYCLE_RECORD_FILE`, `PATH`. | The customer's door is the absence of the SSH path, proved statically and by a recording opener. | 0246 |
| **D2175** | — | **A slot is single-use, so a live proof that creates a project can run once per slot** — and there is one slot. A sweep that re-ran creation would consume nothing (no slot) and read `no_slot`. | **The lifecycle is driven ONCE, by the agent, through the product's own commands** (`s38-lifecycle.py` calling `bin/project.sh`, `bin/compute.sh`, `bin/operation.sh` with the probe owner's session — D1114), and it writes **`~/s38/lifecycle.json`** (0600): each operation's id, the observations the instrument took (probe samples, the downloaded archive's sha256 and `pg_restore --list` member schemas, the claimed administrator's `GET /auth/me` status) and the deleted slot's deployed document (copied on Sheet K2 before deletion). **The live proofs READ it and re-read what still exists through the product**: the operation history through `/v1` (status, codes, order, timestamps), the slot's routes now answering 404, the registry `agrees (deleted)`, the tombstone, the volumes absent, the backup repository present. The gate passes it as `--lifecycle-record-file` (host and external) — the `--restore-evidence-file` / `--dx-record-file` shape. | A declaration read by proofs is the house shape for an act a sweep cannot repeat (Sessions 26, 30); the operation rows are the product's own record and are read live. | 0163, 0202 |
| **D2176** | D2140: *"The class -- a sweep that destroys the state a later proof in it reads -- is an open item for Session 38's plan."* | The post-reboot systemd reading (`InactiveExitTimestampMonotonic` < `multi-user.target`'s `ActiveEnterTimestampMonotonic`) is an instrument (`~/s37/run11/after-reboot.sh`); the sweep restarts alpha's and beta's units before its reboot proof. | **Kept as an instrument, read after B1 and before S1, now also over the reconciler's unit**; `s38-after-reboot.sh` is derived from 37's by diff and its output is written in Run 12's Done. A proof is not written: the suite's order cannot guarantee it runs before the proofs that restart units, and a proof that is false inside the sweep is not strict (D2140's reason). | The class is named in §10 again with the same answer; no new mechanism for a reading that works. | — |
| **D2177** | Scope-closure §30 item 4: *"the TOTP sheets owe the QR route (`totp-enroll --output` + a QR), `--password-file`, and *do not paste the QR*"*. | Session 38's walk is the agent's (the probe owner's seed in `~/s37/probe.json`); no new factor is enrolled. | **No TOTP sheet in 38.** If the operator wants their own account to create a project they hold no slot for one (D2145); the operator's guide §(control plane) is corrected in Run 10 with the QR route and the warning, and Session 42's walk inherits it. | The friction is fixed where a person will next meet it. | 0252 |
| **D2178** | — | Two writers can deploy one host: the reconciler and an operator's sheet. `deploy-project.py` takes no host-wide deploy lock (only `database-ports` takes the host lock). | **The reconciler takes `/run/agentic-postgres/reconciler.lock` (flock) for each operation, and every operator sheet that deploys, retires or restores a project in 38 is preceded by `sudo systemctl stop agentic-postgres-reconciler`** and followed by `start`; `reconciler.sh status` prints *idle*, *working on <id> (<type>, step <s>)* or *stopped*. The sweep's launch script refuses while `status` reads *working*. A host-wide deploy lock is §10. | The cheapest serialisation that is true on the day; a lock in `deploy-project.py` would move every deploy's behaviour in a session about something else. | **0256** |
| **D2179** | D1953: *"runs the matching existing `bin/` command"*. | The deploy requires a CLEAN checkout and refuses with an uncaught exit 1 otherwise (`installed_release.py:101-112`); the reconciler's working directory is the operator's checkout. | **The reconciler records `git rev-parse HEAD` and `git status --porcelain` at start and refuses every operation (finishing it `failed`, `could_not_determine`, result `{"reason": "checkout moved"}`) when HEAD differs or the tree is dirty**; it never runs `git`. A ship moves HEAD only with the reconciler stopped (D2178) and restarts it after. | A root actor that deploys whatever the checkout holds at that moment would deploy a half-shipped tree. | **0256** |
| **D2180** | §5: *"The slot … `bin/slot.sh provision --key sN`"*; naming. | Slug `^[a-z][a-z0-9-]{2,30}$`, environment `^[a-z][a-z0-9-]{1,15}$` (`project.schema.json:39-48`); the key is `slug-environment` (`naming.py:924-926`); `control_projects.key`'s CHECK matches. | **Slot keys are `slot<n>-prod`** (slug `slot<n>`, environment `prod`): the first is **`slot1-prod`**, domain `slot1.agenticpostgresql.com`, buckets `apg-slot1-prod` / `apg-slot1-prod-backup`, mirror `apg-slot1-prod-backup-mirror` unless the operator's B2 names differ (D2124 — the sheet asks), Infisical project `slot1-prod`, identity `slot1-prod-runtime`. **The customer's project NAME is a display name in `control_projects.display_name`**, never a key, a role or a host. | A key the customer chose would be a customer-controlled input to every derived identity (ADR 0002). | **0257** |
| **D2181** | D1972: *"its backup repository is kept for the deletion policy's window and then destroyed by the operator"*. | ADR 0187 keeps backups forever; no policy window exists. | **No window is chosen in 38**: the repository is kept, the Ledger's `project_deletion` row says *"your backups are kept by the operator after deletion; this beta has no automatic removal"*, and §10 carries the policy. | A window nothing enforces would be a promise; keeping is what the code does. | 0187 |
| **D2182** | D1956: *"Backups: a sleeping project's archiver is stopped"*. | `archive_timeout 60 s`; a stopped database archives nothing; `doctor`'s `wal archiver` check would read stale on a sleeping project. | **A sleeping project's doctor is not read by anything in 38**; the Ledger states the restore-point sentence; the slot is awake for the sweep (it is deleted before it). §10 carries *the doctor on a sleeping project* to Session 42's support bundle. | No reader is changed for a state the trip holds for minutes. | 0259 |
| **D2183** | — | The control set's new version needs a committed proposal (ADR 0243, D2136), written by `bin/migrate.py propose` from the committed example. | **Run 4 writes and commits the `0004` proposal** with the product's own `propose` against `project.control.example.yaml` (lint passed, applied from empty, surface empty) — the D2136 shape. | A deploy of control-prod at 1.16.0 refuses without it, on the day, at step 6. | 0243 |
| **D2184** | D1983: the provisioning time measured; §5: *"the creator bootstrapped as the project's first `project_admin`"*. | A creation is ~3 deploys and a full backup: Session 37's control bring-up took 183 + 5 + 172 s plus 5 min 32 s for the first full backup (`capacity.py:1173`). | **The `project.create` reconciler step timeout is 30 min** (each subprocess its own timeout: deploy 600 s, backup 900 s, others 120 s); `operation.sh wait --timeout 2400` in the instrument; `progress` moves at each step (10 deploy 1, 30 admin, 40 ports, 60 deploy 2, 70 unit, 90 backup, 100 done). | A creation of ~12 minutes needs a wait the customer can read. | **0256** |
| **D2185** | §5 *Must not*: *"Delete a backup repository from an operation"*. | `project-retire.sh` never removes it (ADR 0187); `--destroy-data` removes the postgres and store volumes only (`project-retire.py:123-132`). | **`project.delete` passes `--destroy-data`** (a customer's delete means the data goes) **and nothing that reaches the repository**; `backup.sh info` cannot run after deletion (the outputs are gone), so **the operator reads the repository's survival on Sheet SL4 from the R2 console's listing**, recorded in Run 12's Done; the live proof asserts only that the retirement record names the repository as kept. | The repository's survival is ADR 0187's, read by the person who can see the bucket. | 0187 |
| **D2186** | Stage plan §2.2: *"Session 38 adds manifest schema 9 (`compute`, migratable: a minor) and host schema 4 (`region`, slots: migratable)"*. | 9 is `control`, so `compute` is 10 (D2044); outputs 20 → 21; new `/v1` operations; no released migration (D2163 uses `0026`). | **`1.16.0`, predicted minor**: Run 10 reads `upgrade plan` offline with the declarations **`--also document_schema_migratable --also api_operation_added`** (D2131's pair; no `migration_added`) and Sheet R1 on the host; a `major` is a stop. | The version is read, never chosen (D704). | 0162 |
| **D2187** | — | `port_allocation` passes only on a sweep declaring `--after-reboot`; the rotation trio only with the four `--rotated-*` files (D2072). | **Sitting 2 reboots before the sweep (Sheet B1)** — also the reconciler's reboot proof — and `s38-sweep.sh` is derived from `s37-sweep.sh` by diff, keeping every declaration and adding `--lifecycle-record-file` and `--slot-outputs`. | Two claims kept passing by declaring what is still true. | — |
| **D2188** | §5: *"ends on the new host … a third creation refused by capacity with nothing created"*. | One slot (D2145). | **The capacity end state is two refusals on one slot**: a `project.resize` to `large` refused `capacity_exhausted {reason: admission}` with the project still at `standard` and running (read through `/v1` and the deployed document), and — after deletion — a second `project.create` refused `capacity_exhausted {reason: no_slot}` with **no operation row written**. | Both readers measured, with nothing created by either. | 0256 |

**Rows the runs add** (D2189 onward), in execution order:

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D2189** | D2153: *"the reconciler's child environment carries `SUDO_UID`/`SUDO_GID` … a root render hands `.generated/<key>` back"*. | **Rig 38a, pass 1** (Run 1): a root render that FAILED (staged Compose validation, rc 5) with both variables set left `.generated/.locks/<key>.lock` **root:root** — `restore_checkout_ownership` runs only after a successful render (`rendering.py:2813`). The successful pass handed everything back (0 root-owned files); its control without the variables left 3. | **Run 2 hands the lock back on the failure path too**: `render_project` calls the hand-back for the lock in a `finally` (the rendered directory is untouched on failure — the previous valid render stands), with a test that a render failing after the lock is taken under `SUDO_UID` leaves the lock owned by that uid (control: without the variables it stays root's). The product, not the reconciler, gets the fix: an operator's failed `sudo` deploy has the same defect. | A reconciler deploy that fails would otherwise break `op`'s next render of that project (D65's class). | 0256 |
| **D2190** | D2164: *"`app/export_upload.py` … puts it with the container's own `R2Adapter` and prints ONE line: a presigned GET valid 900 s"*; Run 7: *"`R2Adapter.presign_get` takes `expires_in` if rig 38e found it does not"*. | **Rig 38e** (offline): `presign_get(key)` takes NO expiry and signs `download_url_ttl_seconds` (X-Amz-Expires 300 at the default; the schema allows 60–3600). **The adapter has four public operations — `delete_object`, `head_object`, `presign_get`, `presign_put` — and no upload of bytes**; its boto client has `put_object`. Control: the adapter's client with `ExpiresIn=900` signs 900. | **Run 7: `presign_get(key, *, expires_in: int \| None = None)`** (absent → the configured TTL, as today; a value above 900 refused) and **one fifth adapter operation `put_object(key, body)`, first-write-only** (`IfNoneMatch: "*"`, `presign_put`'s rule); the adapter's docstring's *"four operations"* becomes five, still no list. `export_upload` uses only the adapter. ADR 0124's allowlist is not widened. | The export needs exactly one write and one bounded read; reaching past the adapter to its client would be a second provider path. | 0259 |
| **D2191** | D2151 / Run 4 battery M2: *"`SKIP LOCKED` removed → `test_two_claimers_get_distinct_rows` FAILED (run 20×)"*. | **Rig 38f** (Run 1), deterministic overlap (A holds its claim 2.0 s, B starts +0.3 s), 10 rounds each: with `SKIP LOCKED` distinct 10/10, B 0.13–0.17 s; **without `SKIP LOCKED` distinct 10/10 too**, B 1.84–1.87 s (blocked); with neither the row lock nor the outer `status = 'pending'` recheck, **the same row 10/10**, 10 rows at attempt 2. | **M2 as written is an uninformative mutation (D493).** Run 4 writes two tests and two mutations: `test_two_claimers_get_distinct_rows`, killed by removing `FOR UPDATE` AND the outer recheck; and **`test_a_claimer_does_not_wait_for_an_open_claim`** (B returns in under 1 s while A holds its claim 2 s), killed by removing `SKIP LOCKED`. Run 10 registers the second node id under `OPN-CLAIM-001`. | A mutation is evidence only when it can turn its test red; the property `SKIP LOCKED` adds is not-waiting. | 0256 |
| **D2192** | D2155 / Run 5 item 1: *"`compose start` has no `--wait` — measured in rig 38b: if it does not, `start` polls `docker inspect` health"*. | **Rig 38b**: Compose **v5.1.3** (the workstation's) lists `--wait` and `--wait-timeout` under `docker compose start --help`. Also measured: Traefik routes a container only once its healthcheck reads healthy (first 200 at +4.64 s with a 1 s healthcheck; `start` itself returned at 2.16 s), and a route read right after `up --wait` returned was still 404. | **Decided from E0**: the host runs **Docker Compose v5.4.0**, and `docker compose start --help` there lists `--wait` and `--wait-timeout` (read as `op` over SSH, 2026-10-07). **`project-runtime.sh start` runs `compose start --wait --wait-timeout 120`**; no poll is written. The wake window a customer sees is measured as the first 200 (D2171), never as `start` returning. | The tree's pinned minimum (`COMPOSE_MINIMUM_VERSION` 2.24.0) is not the host's version; the host's is what runs. | 0259 |
| **D2193** | D2156: *"`small`'s charge (`unreclaimable_mb`) ≤ 200 and its sum of memory CAPS plus the three projects' resident leaves `available` ≥ 1,024"*. | **Sheet E0** (2026-10-07 20:28Z): 1,725 MiB available, 912 of 1,600 committed; a project's memory caps sum to **2,880 MiB** (`docker inspect`), more than is available, so no profile satisfies the caps rule; control-prod's resident set is **620–631 MiB** over three samples, ~50 of it the database — the rest is seven processes no profile member moves. | **The rule is read on RESIDENT memory and on the charge, never the caps** (D767): `small` charges 192 (≤ 200) and lowers no cap below today's; the predicted available after a creation is 1,725 − ~631 ≈ 1,094 (or 1,725 − 521 ≈ 1,204 by Session 37's arrival measurement) — above 1,024, read on the day by `s38-free.sh`. Rig 38c′ validated `small` (192), `standard` (304) and `large` (840) through the three validators and `load_project_manifest` (control: `memory_limit_mb` equal to the charge refused by both). | A rule over ceilings decides nothing resident memory does; ADR 0258 records the table. | 0258 |
| **D2194** | §0 / D2149 / Sheet H1: *"both copies move on Sheet H1, diffed"*; H1's install line `-m 0644`; D2025: *"the HOST checkout's copy is schema 3"*. | **Sheet E0**: `/etc/agentic-postgres/host.yaml` is **schema 2**, `root:root 0600`, 3,579 bytes — it has no `capacity` block; the checkout's `host.yaml` is schema 3, `op:op 0600`, 5,618 bytes; the diff is exactly the schema line and the `capacity` block. Schema 2 is still accepted (`[2, 3]`), which is why nothing has refused it. | **Sheet H1 writes ONE schema-4 document and installs it at both paths**: `s38-hostyaml.py` writes the candidate from the CHECKOUT's copy (schema 3 → 4, + `region`, + `slots`), the diff against both current copies is read, and the `/etc` copy is installed **`root:root 0600`** (its current mode — the sheet's 0644 was a guess) so the two copies are byte-identical after H1. The class (two copies, D2020) stays in §10. | One document at two paths cannot drift on the day it is written; a schema-2 `/etc` copy beside a schema-4 checkout copy would be a third shape. | 0257 |
| **D2195** | D2162 / Run 2 item 4: *"`src/agentic_postgres/isolation_matrix.py` holds `MUST_DIFFER`, `MUST_MATCH`, `RELEASE_STATE`, `NOT_AUTHORITY_PREFIXES`, `_matches`, `_classify` … the live module imports them"*. | `test_repository_contract.py::test_no_module_is_imported_only_by_its_own_tests` (D204) refuses a `src/agentic_postgres` module whose only importers are tests — Session 37 Run 5 went CI-red on exactly that (`operations.py`, D2110). Nothing in the product classifies isolation leaves; only proofs do. `tests/deployment/` already shares a plain helper module (`oversized_request.py`, imported by a live proof). | **The tables and the classifier move VERBATIM to `tests/deployment/isolation_matrix.py`** (public `matches`/`classify`; the live module keeps `_matches = matches`, `_classify = classify`), imported by the live module and by `tests/contract/test_isolation_leaves_offline.py`. The live module's five node ids are unchanged (`--collect-only`). | A product module whose only reader is a test is the class D204 guards; the helper is honest about who reads it. | — |
| **D2196** | Run 2: *"Both fixtures' `.generated` renders must be byte-identical to before (REST enabled on both)"*; item 1: *"`rendering.build_compose_env` emits `API_REST_ENABLED`"*. | Re-rendered with `./deploy.sh --render-only` (Run 2): `diff -r` against the copy taken before the run shows **exactly one difference per fixture — `compose.env` gains `API_REST_ENABLED=true`** (line 81); `outputs.json`, `pgbackrest.conf` and every other rendered file are byte-identical. No `compose.yaml` line interpolates the key, and `compose.env` is not mounted, so no container's definition or mount digest moves with it (ADR 0155). | **The byte-identity holds for everything but the one line item 1 adds**, and that line is the reader the run exists to give the flag. The host's alpha and beta renders gain the same line (`true`), control-prod's `false`. | The plan's two sentences cannot both be literally true; the difference is the intended one and is measured, not assumed. | 0251 |
| **D2197** | D2161 / Run 3 item 4: *"Outputs schema 21 carries `region` … in the rendered and deployed documents … the render takes the region from the host manifest (`render-config.py` already loads it, `:186`, `:211`)"*. | `bin/render-config.py`'s project render (`--render`) takes NO host manifest; `:186` and `:211` are `--edge-env` and `--edge-static`, the shared edge's paths. `./deploy.sh --render-only` must keep working with no host (CLAUDE.md §6). The deploy loads the host manifest at step 0. | **`region` is a DEPLOYED-document member only**: `build_deployed_document(region=…)` (REQUIRED, the deploy passes `host_config.region(host).as_document()` or `None` from a host manifest below 4); the rendered branch carries `compute` alone, and `migrate_v20_to_v21` (rendered documents) adds only `compute: {profile: standard}`. A deployed document is read by version, never migrated (ADR 0241), so no step writes a region into an archived one. | A render that needed a host to know where it will run would end the hostless render; the deploy is the one step that knows both the project and the machine. | 0257 |
| **D2198** | D2156: *"`config.compute_profile(manifest)` … the merged budget used everywhere — `database_budget()`, the auth/storage memory and the pools — takes the profile's values when `compute` is present (grep every reader …)"*; *"a manifest with `compute: {profile: standard}` renders byte-identically to one with no `compute`"*. | The budget readers are many (`database_budget`, the three connection-budget functions, `build_compose_env`, the validators) and all read the LOADED manifest. Measured in Run 3: the example manifest itself sets `api.rest.pool_size` and `storage.pool_size`, and declares no `api.app` block; and `outputs.json` records `inputs.project_sha256`, the digest of the manifest's BYTES. | **The profile is applied in ONE place — `config.apply_compute_profile`, called by `load_project_manifest` after the schema and before every semantic rule** — so every reader sees the values as if written and the existing validators bound them; no reader changed. A profile writes only into blocks the manifest DECLARES (creating `api.app`/`storage` would change what is enabled; an absent block is charged at its defaults, as today; a slot manifest carries every block). The byte-identity holds for every rendered file and for `outputs.json` with `inputs.project_sha256` set aside — the one leaf that must differ, since the manifests' bytes differ (`test_standard_is_todays_defaults`). | One application point cannot miss a reader; a reader-by-reader merge is the D979 class. | 0258 |
| **D2199** | D2154: *"`schemas/operation-arguments.schema.json` … every string a pattern … validated twice … with the same schema file"*; *"a test holds the two equal on every example"*. | `jsonschema` validates `pattern` with Python's `re.search`, where `$` also matches **before a final newline**: `^[a-z][a-z0-9_.-]{2,62}$` accepts `"shop.admin\n"` (the class `installed_release.py:51` and `compatibility.py:55` record). Pydantic's default engine (Rust `regex`) treats `$` as the end of input and refuses it. The two validators would disagree on exactly the input that matters, since `admin_username` reaches an argv. | **The schema ends every pattern in `(?![\s\S])`** — end of input in ECMA-262 and in Python alike — and says why in its `description`; the models keep `$` (correct in their engine). `test_operation_types.py::test_the_schema_and_the_models_agree` judges 24 examples by both, the trailing-newline cases among them. | Two validators of one input must agree on its hardest case, not only its easy ones. | 0256 |
| **D2200** | Run 4 item 1: *"`control_adopt_project` re-created with the new members … `bin/control.py`'s `ADOPT_SQL` passes the new members as NULL for an operator adoption"*; D2167: *"extended in `0004` with `p_region`, `p_profile`, `p_slot`"*; Run 8: *"`control_projects` gains `app_route text` in `0004` — add it in Run 4 if this run finds it missing"*. | `ADOPT_SQL` passes seven positional members (`control.py:67-70`), and five tests call the seven-argument form; a 1.16.0 `control.py` adopting into a control project still at `0003` (before its deploy) must not fail on a signature that does not exist yet. | **The new parameters — `p_region`, `p_profile`, `p_slot`, `p_app_route`, `p_display_name` — default to NULL**, so `ADOPT_SQL` and every seven-argument caller are UNCHANGED and resolve to the new function (the old one is dropped in `0004`). `adopted_from` is derived (`reconciler` when `p_slot` is given, else `deployed_document`) and never rewritten on re-adoption; a re-adoption `coalesce`s the five (never erases what it does not name) and **refuses a deleted row** (`AP409: deleted`) — a consumed slot is never revived. `app_route` added now (Run 8's ask). `control_registry_rows` re-created returning the new members and `deleted_at` (D2167's reader is Run 6's). | One signature serving both writers, with no caller edited, cannot drift between them. | 0256, 0251 |
| **D2201** | D2151: *"`control_advance_operation(p_id, p_step, p_progress)`, `control_finish_operation(p_id, p_status, p_error_code, p_result jsonb)` (refuses a terminal row …)"*; D2164: *"The URL goes into the operation's `result.download_url`"*. | A creation's row has no `project_key` until its slot is chosen (the request cannot know it); the result secret must never sit in `result` (a list answer returns `result`). | **`control_advance_operation` takes `p_project_key DEFAULT NULL`**, set once and never changed (a different key is `AP409`); **`control_finish_operation` takes `p_result_secret DEFAULT NULL`** into the `result_secret` column, and the table CHECKs that only a succeeded `project.export` holds one. Finish refuses any row not `running` — a terminal one and an unclaimed `pending` one alike — a failure without a code and a success with one (`AP422: invalid_outcome`), and a result member outside `app.control_result_members(type)` (`AP422: undeclared_result`), which a test holds equal to `operations.RESULT_MEMBERS`. `error_code` CHECKs the five operation outcomes (`errors.OPERATION_ERROR_CODES`). | The secret's one exit is the take; a key set later than the claim needs a writer, and only the reconciler knows it. | 0256, 0259 |
| **D2202** | Run 4 item 1: *"`control_ready_slot_count()` → the API's `no_slot` reading with `observed_at`"*; *"SELECT policy to `object_owner` for any authenticated caller"*; D2159: the state *"from the project's operation history"*. | A DEFINER function bound by FORCE RLS needs a caller for the policy to name; and the four readers' `RETURNS TABLE` must widen (`display_name`, `region`, `profile`, `app_route`, `deleted_at`; `requested_by`, `step`, `result`), which a `CREATE OR REPLACE` cannot do. | **`control_ready_slot_count(p_user)`** (the policy reads `app.current_user_id() IS NOT NULL`), returning `(ready_slots, observed)`, `observed` NULL when nothing was recorded — which refuses as `no_slot`. **`control_project_operations(p_user, p_key DEFAULT NULL)`** (DEFINER, granted) returns the history `control_states` derives from. The four readers are **dropped and re-created** in `0004`, grants re-made; `test_control_set`'s GRANTED/OPERATOR/HELPERS sets move with them. | A function that answers "anyone" with no caller is the shape design G refuses; a state with no history to read would be a guess. | 0256, 0251 |
| **D2203** | D2159: *"export running → `ready` … a project adopted with no operation → `ready (operator-managed)`"*; the failure codes listed are `capacity_exhausted`/`invalid_request` → before, `interrupted`/`could_not_determine` → `unknown`. | A sleeping project can be exported (the plan does not forbid it); `operation_failed` and `cancelled` are not ruled; a state word with a parenthesis is not a value a client can switch on. | **A running export leaves the state as it was** (`ready` in the plan's case, `sleeping` for a sleeping project); **`operation_failed` → `unknown`** (it may have stopped part way); **`cancelled` and `pending` → the state before** (nothing ran); an unreadable history → `unknown`. **`ready (operator-managed)` is two members**: `state: ready`, `managed_by: operator` (`reconciler` once any operation decided the state). | Each rule is the third outcome where a guess would be the only alternative. | 0256, 0195 |
| **D2204** | Run 4 battery M1: *"the partial index dropped → `test_one_operation_at_a_time` FAILED"*; D2165: the writes' roles; ADR 0254: `not_available` before anything is recorded. | `control_request_operation` reads for a non-terminal row BEFORE inserting (so it can answer `conflict` with the id), so dropping the index leaves the sequential API answer unchanged — the index is what holds under a RACE. Session 37's `POST /v1/projects` authenticates before refusing (`test_project_creation_is_refused_as_not_available`'s control: an unauthenticated call is 401). | **`test_one_operation_at_a_time` also inserts a second non-terminal row as the superuser, bypassing the function**, and requires `duplicate key` — that half is what M1 kills. **Every write authenticates, THEN answers `not_available` while its type is not accepted, THEN reads its body** (Session 37's order, kept). The writes are `ACCOUNT` entries in `MATRIX` (the organisation comes from the body or the project row, as `get_project`'s does), with their role in `control_roles.PROJECT_WRITES` applied by the handler and again in SQL. `ACCEPTED_TYPES` stays empty; the proofs accept the six types for their own duration. | A mutation is evidence only when it can turn its test red (D493); the race the index exists for is reached directly. | 0256, 0254 |
| **D2205** | Run 5 item 2 / D2158: *"`project-retire.sh --defer-provider` … `bootstrap-state.json` is moved to `/etc/agentic-postgres/slots/<key>/retired-bootstrap-state.json` (0600) and the local credential files … removed"*; Tests: *"`test_project_retirement.py::test_defer_provider_keeps_the_state_for_revocation`"*. | The module is `tests/contract/test_project_retire.py`. `retirement.steps` and `retirement.record` take no word for a deferral; `Step` can run commands or remove paths, not move a file. A non-slot project (alpha, beta) deferring would keep a state that `bin/slot.sh revoke` -- which acts on declared slots only -- can never revoke. | **`DEFERRED_STEP_ORDER`** (`provider-destroy` replaced in place by `keep-bootstrap-state`); `steps(…, retired_state)` and `record(…, retired_state)` take it **REQUIRED** (D2087: None for a retirement that revokes now); `Step.moves`; the move is a new 0600 file (`O_EXCL|O_NOFOLLOW`, fsynced) in a 0700 directory, then the source unlinked -- never over an existing kept state; the project's whole credential directory is removed; the record gains `provider {deferred, kept_bootstrap_state, note}` naming `bin/slot.sh revoke`. **Refused before anything changes**: beside `--operator-credential-file` (2), for a key that is not a slot key (2), over an existing kept state (2), with no bootstrap state to keep (3). The tests live in the tree's module (two added). | A deferral nobody can complete is a revocation lost; refusing it costs a sentence. | 0257, 0187 |
| **D2206** | D2150 / Run 5 item 3: *"`prepare` writes … from `slots.defaults` + the declaration + profile `small` + the host's region"*; *"lifecycle `permanent`; storage, REST, app, backup with mirror enabled; connectors off; no `migrations`; `compute: {profile: small}`"*; D2149: occupied = *"a deployed document, or an allocation row the reconciler wrote"*. | The project manifest has no region member -- the region is the host's, carried into the DEPLOYED document only (D2197). The loader refuses an `mcp` block without `profile` and a REST block whose CORS list omits the project's own origin; a profile-owned member beside `compute` is refused by name (D2198). `slot.py` reads the host's files, not the control database. | **The slot manifest carries no region** (the deploy adds it from the host); `mcp.profile: {}` (stated, narrowing nothing); `api.rest.allowed_cors_origins: [https://<domain>]`; no memory or pool member (the profile writes them); `database.pool_size 16`. Built by `slot.slot_manifest`, written by `prepare` to a temporary in the slot's 0700 directory, **loaded by `config.load_project_manifest` before it is renamed into place**. **Occupancy is read from files**: a deployed document, or an `allocated` marker in the slot's directory that the reconciler writes when it takes the slot (Run 6) -- the control plane's row is the reconciler's to write after, not a reading root's command could take. | A reading of the host by the host's own files cannot disagree with what is on the host; a second source would. | 0257, 0258 |
| **D2207** | D2150: *"`revoke --slot KEY --operator-credential-file F --confirm KEY` runs `bootstrap-providers --destroy` against the KEPT bootstrap state of a consumed slot"*. | `bootstrap-providers --destroy` reads the state only at `/etc/agentic-postgres/projects/<key>/bootstrap-state.json` (`state_path`, read at `bootstrap-providers.py:1261`) -- which the retirement removed -- and **with no state there it prints "Nothing is owned; nothing done" and exits 0** (`:1020-1022`): run as-is against a retired slot it would report success and revoke nothing. | **`revoke` puts a COPY of the kept state back at `state_path(key)`** (refusing if a state is already there: a project holds the key), runs the product's own `bootstrap-providers.sh --host F --project <slot manifest> --destroy --confirm KEY --operator-credential-file F` (stdin `/dev/null`, 300 s), and succeeds only on exit 0 **with the copy consumed**; otherwise the copy is removed and it exits 6. A `revoked` marker (0600) records the identity; the kept file is never removed. Refused before anything: a `--confirm` that differs (2), a slot not consumed, already revoked, or with no kept state (5). | The exit-0-for-nothing branch is the reassuring direction of the wrong premise (D930's class). | 0257 |
| **D2208** | D2148: *"`slot.sh status` reads it (A = the host's `host.public_ipv4`, AAAA empty, from the host with `dig @1.1.1.1`; no `dig` → `could not determine`)"*. | The host manifest's field is `host.expected_public_ipv4` (`host_config.py:485`); it may be null (an IPv6-only host). A schema-2 or -3 host manifest -- the host's today -- declares no slots. | **The A record must be exactly `[expected_public_ipv4]` and there must be no AAAA; a null address, a missing `dig`, a non-zero `dig` or a timeout is `undetermined`** (exit 6), never `prepared` and never `ready`. A host manifest with no `slots` makes every verb exit 3 (*"declares no slots"*) -- the trip's Sheet H1 moves it to schema 4 first. | A reading that could not be taken is the third outcome, here as everywhere (ADR 0195). | 0257, 0195 |
| **D2209** | D2179: *"The reconciler records `git rev-parse HEAD` and `git status --porcelain` at start … it never runs `git`"*; D2153: the children carry `SUDO_UID`/`SUDO_GID` so a deploy hands `.generated/<key>` back. | **Rig 38g** (Run 6, `python:3.12`, git 2.47.3): root running `git status` on a checkout another uid owns exits **128, `detected dubious ownership`**; with `SUDO_UID` = the owner it answers (and `rev-parse HEAD` too); control: `SUDO_UID` naming a different uid → 128 again. Under systemd there is no `SUDO_UID`, so the deploy's own clean-checkout read (`installed_release.assert_clean`, a `git status`) would refuse every reconciler deploy without D2153's environment. | **The reconciler runs read-only git** -- `rev-parse HEAD` and `status --porcelain`, as `checkout_reading`, with the same `SUDO_UID`/`SUDO_GID` its children carry -- and never a git command that changes anything ("never runs git" read as never moves the checkout). D2153's environment is therefore what lets BOTH the hand-back and git's ownership check work for a systemd-started root process; its proof (`test_children_act_for_the_checkout_owner_with_stdin_closed`) reads it on every child. | A root process acting on another user's checkout is exactly what git's check exists to refuse; the variable that names the owner is the one sudo sets for an operator. | 0256 |
| **D2210** | D2163/D2173: *"`auth-admin.sh … bootstrap --username U --password-fd N`; the user's id read with `auth-admin.sh list --json` or a `psql` read"*; *"`backup.sh … backup --type full` → `schedule enable` → `mirror`"*. | `auth-admin.py`'s parser requires `--outputs` (the deployed document) before the verb and `--display-name` on `bootstrap` (`:405-412`); `list` has no `--json` and prints a table. `backup.py` requires `--outputs` (`:793-799`). The display name a customer typed may reach no argv (D2154). | **`auth-admin.sh --outputs <deployed outputs.json> bootstrap --username U --display-name U --password-fd N`** -- the administrator's display name is their username; the project's display name stays in `control_projects` alone. **The user's id is read by `psql` as the superuser** (`reconciler_dispatch.ADMIN_ID_SQL`: `app_private.users` by username, `status = 'active'`), never parsed from the command's output. Every `backup.sh` call carries `--outputs`. `test_admin_handoff.py` runs the reconciler's own `database_call` with `ADMIN_ID_SQL` and `OPEN_HANDOFF_SQL` against a project cluster with the release set (rig 38c as a proof). | The tree's commands, called the way they parse; a value read from the database is the identity, a printed line is a report. | 0260, 0256 |
| **D2211** | Run 6 item 2: *"Every `deploy.sh` call: … `--through-session 38`"*. | `deploy-project.py` refuses a `--through-session` above `CURRENT_SESSION` (`:2288-2293`), which is **37** until Run 10's registry move; a typed 38 would refuse every deploy of the commit that ships it before Run 10, and a typed number would fall behind Session 39's. | **`THROUGH_SESSION = agentic_postgres.CURRENT_SESSION`** -- the release's own session, read, never typed (D704/D2186's rule); 38 once Run 10 moves the registry. | The deploy decides what a session number may be; the reconciler passes the release's. | 0256 |
| **D2212** | D2160: the reconciler writes `app.control_slots` *"at start and after every operation"*; the control mode refuses a reading older than ten minutes. | An idle host runs no operation: ten minutes after the last one every creation would be refused `no_slot (stale)` although a slot is ready. | **The reading is also re-recorded every 120 s while idle** (`RECORD_SECONDS`), so it is stale only when the reconciler is not running -- which is when a creation should be refused. A failed recording is reported on the journal and leaves the reading to go stale (fails closed). | The staleness rule exists to detect a stopped reconciler, not an idle one. | 0256 |
| **D2213** | D2154: *"only `profile` and `admin_username` may appear in an argv"*; `bin/control.py` passes every value as `psql -v name=value` (`:150-154`). | `-v` puts the value on the `docker exec` argv -- for the reconciler that would be the display name, the handoff hash, the organisation and every result. | **The reconciler sets every value with `\set name '…'` on psql's STDIN** (`reconciler_dispatch.psql_input`: a backslash and a quote escaped as psql unescapes them, a newline as `\n`); its SQL reads `:'name'` as before. Measured round trip against the control cluster (`test_a_result_reaches_the_control_database_unaltered`: a quote, a backslash, a colon and a newline arrive unaltered); `test_every_argv_is_built_from_validated_members` reads every argv, `docker exec` included. `bin/control.py` is unchanged (its values are an operator's). | A value a customer chose stays out of every process argument, not only the commands'. | 0256 |
| **D2214** | D2151: the unit has *"`WorkingDirectory=` the checkout … `After=`/`Wants=` docker + the control project's unit; installed and enabled by `reconciler.sh install`"*. | `provision-host.sh`'s `install_units` installs EVERY `systemd/*.service` and `--check` reports any not installed (`:369-384`, `:828-838`, one glob, D970) -- a unit with the checkout's path written in, or a placeholder, would be installed broken by the next `--apply`. The control project's unit is `agentic-postgres-project@control-prod`, a key the reconciler finds and never names (D2168). | **The unit is installed verbatim**: `EnvironmentFile=/etc/agentic-postgres/reconciler.env` (`APG_CHECKOUT=`, written by `install` and refused for a path with anything but `[A-Za-z0-9._/-]`), `ExecStart=/bin/bash ${APG_CHECKOUT}/bin/reconciler.sh run` (the wrapper `cd`s to the checkout), `Environment=HOME=/root`, `StandardInput=null`, `Restart=on-failure`, `RestartSec=30`; `After=` docker and the edge. A reconciler that starts before the control database answers exits 6 and is retried in 30 s. `install` also creates `/var/log/agentic-postgres/reconciler` and `/var/lib/agentic-postgres/exports` (0700) and runs `enable --now`. **Until Sheet RC1, `provision-host.sh --check` reports the unit not installed** -- RC1 precedes the day-2 sweep. | A unit file that is correct wherever the glob puts it; the order systemd cannot know is covered by the restart that exists anyway. | 0256 |
| **D2215** | D2167: *"`registry` gains one outcome: a row with `deleted_at` and no deployed document and a `consumed` tombstone **`agrees (deleted)`**; with a deployed document still present → `differs: deleted`"*. | A deleted row with no document and NO tombstone, and a tombstone that cannot be read, are not ruled. | **`differs: tombstone`** (exit 5) for no tombstone; **`could not determine`** (exit 6) for an unreadable one; a key that is not a slot's has no tombstone. `control.py` reads it under `SLOT_ROOT/<key>/consumed`; `test_a_deleted_project_agrees_only_with_its_tombstone` (control: the same row without `deleted_at` agrees). | Agreement is claimed only when both halves of a deletion are present. | 0256, 0195 |
| **D2216** | D2160: an admission refusal returns the slot to `ready`; D2152: an interruption quarantines it. | A step that FAILS (an exit code, a timeout) is not ruled. | **Before the first deploy** (no ready slot, admission refused or failed, the manifest refused) **the slot is returned**: its prepared manifest restored byte for byte, its `allocated` marker removed. **From the first deploy on, a failure leaves the marker**: the slot reads `allocated` and is never reissued; the operation is `operation_failed` (or `could_not_determine` for a child that outlived its bound) naming the step, and the project's state reads `unknown` (D2203). Clearing such a slot is the operator's (§10). | Once something was rendered or deployed, returning the slot would reissue a half-made project. | 0256, 0195 |
| **D2217** | ADR 0256: a closed table over the six executed types. | Run 6 builds `project.create`; Run 7 builds the other five. | **`reconciler_dispatch.STEPS` and `bin/reconciler.py`'s `HANDLERS` hold `project.create` only**, a test holding the two equal and within `EXECUTED_TYPES`; a claimed row of any other type is finished `failed invalid_request {"reason": "this release does not execute <type>"}` with nothing run. No such row can exist before Run 10 (`ACCEPTED_TYPES` is empty). Also: **`slot.dns_reading` and `slot.observe`** moved from `bin/slot.py` into `agentic_postgres.slot` -- one walk over the declared slots that `slot.sh status` prints and the reconciler records (a `bin/` command imports no other, ADR 0093). | The table is closed at every commit, not only at the session's end. | 0256, 0093 |
| **D2218** | Run 7 item 1: the handlers act on *"the row's `project_key`"* (D2154); D2165: sleep, wake, resize, export and delete are `projects:write` (delete `admin`+) over the caller's organisation. | `control_service.write_project` accepts any registry project of the caller's organisation that is not deleted -- and alpha, beta and control-prod are adopted into the operator's organisation (Sheet A1, D2141). A member there could ask the reconciler to stop, resize, export or retire the control plane itself. | **The reconciler acts only on DECLARED SLOTS**: every operation but a creation is refused before anything runs -- `failed invalid_request {"reason": "the reconciler acts on slot projects only; this one is operator-managed"}` -- when its `project_key` is not one of `host.yaml`'s declared slots; a slot with no deployed document is `could_not_determine`. The control mode is unchanged (an `invalid_request` leaves the derived state as it was, D2203). `test_an_operator_managed_project_is_refused` (alpha-dev, control-prod). | The reconciler retires only what it created; an operator-managed project's lifecycle is the operator's sheets'. | 0256 |
| **D2219** | D2203: *"A running export leaves the state as it was (`ready` in the plan's case, `sleeping` for a sleeping project)"*. | A sleeping project's database container is stopped: `pg_dump` through `docker exec` cannot run, and a resize's deploy would start the containers behind a disabled unit and disabled timers. | **Export and resize read whether the database container runs first** (`docker inspect --format {{.State.Running}}`, argv built by `reconciler_dispatch.running_argv`): `false` → `failed invalid_request {"reason": "the project is sleeping; wake it first"}` with nothing dumped, admitted or deployed (the state stays `sleeping`); no answer → `could_not_determine` (`unknown`). Two `docker` READS join `COMMANDS` (this and the storage container's lookup); every `docker exec` stays `container_exec.run`. `test_a_sleeping_project_is_neither_exported_nor_resized`. | A sleeping project woken as a side effect of another request is the surprise the derived state would then misreport. | 0259, 0195 |
| **D2220** | Run 7 item 1: *"resize (admit with the own key excluded → `capacity_exhausted {admission}` with nothing rendered; else re-write the manifest's `compute`, one deploy, the registry refresh)"*. | `admit.sh` charges the profile of the manifest it is handed; admitting the slot's manifest BEFORE re-writing it would charge the profile being left. | **A candidate manifest**: the slot's with the new profile, written `.candidate.<operation>.yaml` (0600, exclusive) beside it, loaded by the product, then admitted (the key it derives is the slot's own, so admission's `already_deployed_here` excludes the project's current charge); **renamed over the manifest only when admitted**, removed in every other case. Then one deploy at `THROUGH_SESSION` and the registry row refreshed -- `ADOPT_SQL` now passes an empty display name or slot as NULL, so a refresh never erases them (the re-adoption `coalesce`s, D2200). `test_resize_admits_a_candidate_before_anything_changes` (refused: the manifest byte for byte, no candidate left, nothing deployed; control: admitted). | Admission reads what will be deployed, and nothing is changed before it says yes. | 0258, 0221 |
| **D2221** | D2164: *"`python -m app.export_upload --key exports/<operation-id>.dump`, stdin = the archive … puts it with the container's own `R2Adapter`"*; D2190: `put_object` first-write-only, `presign_get(…, expires_in)` bounded at 900. | The storage container's objects live under the deployed prefix (`APG_STORAGE_PREFIX`, one authority, ADR 0102); a key the reconciler typed would be a second derivation of it. `container_exec.run` captures output and feeds input whole. | **`--operation <uuid>`**: the container builds `<prefix>exports/<uuid>.dump` itself; the reconciler passes no path. The adapter's `put_object` is NOT added to `BoundedR2` (the storage API's path), so the served API still writes no bytes; a named expiry outside 1–900 s is refused before anything is signed, absent = the configured TTL (the API's path unchanged). `export_upload` refuses outside `APP_MODE=storage` (3), an empty archive (2), and reports the provider's 412 as 5 with no URL. **The archive passes through the reconciler's memory** (`pg_dump`'s captured stdout, then the upload's input): bounded by a slot's database, which Session 38's profiles keep small; a streamed export is §10. `test_export_upload.py` (5, Stubber). | The prefix has one authority; the bounded URL is the only new exit. | 0259, 0124 |
| **D2222** | D2158 / ADR 0256 §6: `project.delete` runs `project-retire.sh … --permanent --destroy-data --defer-provider`. | ADR 0186 (*"No unit, timer, cron or deploy step reads `expires_at` and acts"*; D951, every removal path a human's) is guarded by `test_project_retire.py::test_no_unit_timer_or_command_names_the_retirement_verb`, which refuses any unit or `bin/` command but the verb itself naming `project-retire` -- Run 7's targeted run found `bin/reconciler.py` (1 failed, 1,538 passed). The plan read ADR 0186 and did not price its guard. | **ADR 0256 amended** (§ *Amendment, Run 7*): the reconciler is the one command besides the verb that may name it -- for a `project.delete` a PERSON requested (human-session only, `admin`+, D2165) on a slot it created (D2218), with `--permanent` and never `--before-expiry`, never reading a project's `expires_at`. **The guard widens by exactly `bin/reconciler.py` and gains three assertions** that keep the exception honest: the reconciler still names the verb (drop the exception otherwise), it never READS `expires_at` (subscript or `.get`) nor names `lifecycle` or `--before-expiry`, and `retire_argv` carries `--permanent` and no `before-expiry`. Battery M8 (the reconciler reading `expires_at`) → the guard FAILED, control `test_volume_removal_lives_in_exactly_two_commands` PASSED. | Widening an allowlist to the measured set, with the property it protects asserted where the exception is, is not weakening it; no timer acts on expiry still holds. | 0256, 0186 |

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

**Two new families, `LIFE` and `OPN`** (the stage plan's proposal, D691): the
regex at `tests/contract/test_acceptance_registry.py:114` gains `LIFE` and
`OPN`, and the family comments gain one sentence: *Session 38 (ADR 0256-0261)
adds `OPN` for the reconciler and the operations it executes, and `LIFE` for a
managed project's lifecycle — slots, profiles, region, sleep, export, deletion
and the first-admin handoff.* **Eighteen requirements, eighteen claims, all
`target_session: 38`, all P0 — fifteen offline, two external, one host.**
Node ids below are **proposed; Run 10 writes what the runs actually wrote**, read
out of the tree with `pytest --collect-only -q` (D1236, D2129). Registry entries
are committed by Run 10 with the constant (D690), under **`# Session 38 (ADR
0256-0261)`**.

| Requirement | What it states | Offline node ids (proposed) | Live half |
|---|---|---|---|
| `OPN-CLAIM-001` | The claim functions are granted to nobody; two concurrent claimers get distinct rows; a terminal row cannot be finished again; a result key outside the type's members is refused; an operation `running` at start is finished `interrupted` with its step and never claimed again; an interrupted create quarantines its slot | `tests/contract/test_reconciler_claim.py::test_the_claim_functions_are_executable_by_no_role`, `::test_two_claimers_get_distinct_rows`, `::test_a_terminal_operation_cannot_be_finished_again`, `::test_an_undeclared_result_member_is_refused`, `::test_an_interrupted_operation_fails_and_is_never_reclaimed`, `::test_an_interrupted_creation_quarantines_its_slot` | — (`reconciler_claim`) |
| `OPN-DISPATCH-001` | Every accepted type has exactly one handler; arguments are validated against `schemas/operation-arguments.schema.json` before dispatch; every argv is a list built from validated members; no shell, no string command; every container exec goes through `container_exec.run`; the reconciler opens no socket | `tests/contract/test_reconciler_dispatch.py::test_every_accepted_type_has_one_handler`, `::test_an_invalid_argument_runs_nothing`, `::test_every_argv_is_built_from_validated_members`, `::test_no_shell_and_no_string_command`, `::test_every_exec_goes_through_container_exec`, `::test_the_reconciler_opens_no_socket` | — (`reconciler_dispatch`) |
| `OPN-API-001` | `POST /v1/projects` and the project operation routes answer `202` with an operation for an accepted type, `409 not_available` for one that is not, `409 conflict` for a second non-terminal operation; the role × route matrix with `projects:write`; create, export and delete are human-session only; the closed error enum; the control snapshot matches | `tests/contract/test_control_projects.py::test_an_accepted_type_returns_an_operation`, `::test_a_type_not_accepted_is_not_available`, `::test_one_operation_at_a_time`, `::test_every_route_and_role_answers_as_the_matrix_says`, `::test_a_key_cannot_create_export_or_delete`, `::test_every_refusal_word_is_in_the_closed_enum`, `tests/contract/test_app_contract_aggregate.py::test_the_control_snapshot_is_what_this_checkout_generates` | — (`control_project_operations`) |
| `OPN-STATE-001` | A project's state is a pure function of its operation history, with `unknown` for an interrupted or undetermined latest operation and `ready (operator-managed)` for an adopted project | `tests/contract/test_control_states.py::test_every_history_maps_to_one_state`, `::test_an_interrupted_operation_reads_unknown`, `::test_an_adopted_project_is_operator_managed` | — (`project_states`) |
| `OPN-REG-001` | The reconciler refreshes its project's registry row after the last deploy; `registry` reads a deleted project with its tombstone as `agrees (deleted)` and one with a document still present as `differs: deleted` | `tests/contract/test_control_command.py::test_a_deleted_project_with_its_tombstone_agrees`, `::test_a_deleted_project_with_a_document_differs`, `tests/contract/test_reconciler_dispatch.py::test_the_registry_row_is_refreshed_after_the_last_deploy` | — (`registry_after_operations`) |
| `LIFE-PROFILE-001` | Three profiles; `standard` renders byte-identically to no `compute`; every profile passes the budget validators; a manifest naming `compute` and a profile-owned member is refused; manifest 10 below 10 is refused; pids/cpus come from the profile | `tests/contract/test_compute_profiles.py::test_standard_is_todays_defaults`, `::test_every_profile_passes_the_budget_validators`, `::test_a_profile_and_an_owned_member_are_refused_together`, `::test_compute_is_refused_below_schema_ten`, `::test_pids_and_cpus_come_from_the_profile` | — (`compute_profiles`) |
| `LIFE-RESIZE-001` | A resize is admitted against the other projects (own key excluded) and refused at exit 12 with nothing rendered; the message is the unmeasured sentence while `RESIZE_WINDOW_SECONDS` is `None` and equals the envelope row otherwise | `tests/contract/test_reconciler_dispatch.py::test_a_refused_resize_changes_nothing`, `tests/contract/test_compute_profiles.py::test_the_resize_message_names_only_a_measured_window` | — (`resize_message`) |
| `LIFE-REGION-001` | Host schema 4 requires `region` and accepts `slots`; outputs 21 carries `region` and `compute.profile`; `migrate_v20_to_v21`; every leaf of a built deployed document is classified offline | `tests/contract/test_host_manifest.py::test_schema_four_requires_a_region`, `tests/contract/test_output_migrations.py::test_v21_adds_region_and_profile`, `tests/contract/test_isolation_leaves_offline.py::test_every_leaf_of_a_built_deployed_document_is_classified` | — (`region_and_document`) |
| `LIFE-REST-001` | `api.rest.enabled: false` renders no PostgREST router and the deploy records REST unpublished without observing it; enabled renders it; a `ready` REST route with the flag off is refused by the document | `tests/contract/test_rest_flag.py::test_a_disabled_rest_service_has_no_router`, `::test_the_deploy_records_rest_unpublished_without_reading_it`, `::test_a_ready_rest_route_with_the_flag_off_is_refused` | — (`rest_flag`) |
| `LIFE-SLOT-001` | `slot.sh prepare` writes a valid manifest only for a declared, unprepared, unconsumed slot; `status` derives every state with its reason and exits 6 on any undetermined; a consumed or quarantined slot is never `ready`; no command removes a tombstone; `revoke` needs the credential, the confirmation and a consumed slot | `tests/contract/test_slot_command.py::test_prepare_writes_a_valid_manifest_once`, `::test_every_state_is_derived_with_its_reason`, `::test_a_consumed_or_quarantined_slot_is_never_ready`, `::test_nothing_removes_a_tombstone`, `::test_revoke_needs_a_consumed_slot_and_its_confirmation` | — (`slots`) |
| `LIFE-CAP-001` | Admission's exit 12 maps to `capacity_exhausted {reason: admission}` before anything is rendered; no ready slot maps to `capacity_exhausted {reason: no_slot}` before a row is written; a stale slot reading is `no_slot`; nothing in 38 produces `plan_limit_reached` | `tests/contract/test_reconciler_dispatch.py::test_admission_refusal_is_capacity_exhausted_and_creates_nothing`, `tests/contract/test_control_projects.py::test_no_ready_slot_refuses_before_a_row`, `::test_a_stale_slot_reading_is_no_slot`, `::test_nothing_produces_an_entitlement_refusal` | — (`capacity_refusals`) |
| `LIFE-SLEEP-001` | `project-runtime.sh stop` keeps containers and detaches the edge; `start` re-reads no secret and recreates nothing; sleep disables the unit and the timers, wake re-enables them | `tests/contract/test_project_runtime_stop_start.py::test_stop_keeps_containers_and_detaches`, `::test_start_reads_no_secret_and_recreates_nothing`, `tests/contract/test_reconciler_dispatch.py::test_sleep_and_wake_move_the_unit_and_the_timers` | — (`sleep_wake`) |
| `LIFE-EXPORT-001` | The dump names `app` and `api` only; the archive goes through the storage container and never to a file the reconciler keeps; the URL is ≤ 900 s, returned once and erased; never in a list answer or a log line | `tests/contract/test_reconciler_dispatch.py::test_the_export_names_only_the_customer_schemas`, `::test_the_archive_is_removed_after_upload`, `tests/contract/test_export_upload.py::test_the_presigned_url_lives_at_most_900_seconds`, `tests/contract/test_control_projects.py::test_the_download_url_is_returned_once`, `::test_no_download_url_reaches_a_list_or_a_log` | — (`export`) |
| `LIFE-HANDOFF-001` | The control plane stores only `sha256(T)`; the reconciler registers it with `auth_open_password_reset` after bootstrapping with a password it does not keep; `T` opens the reset once; the CLI keeps `T` 0600 and deletes it after the claim | `tests/contract/test_admin_handoff.py::test_only_the_hash_reaches_the_control_plane`, `::test_the_reset_opens_once_with_the_token`, `::test_the_bootstrap_password_is_never_stored`, `tests/contract/test_control_cli.py::test_the_handoff_token_is_private_and_removed_after_claim` | — (`admin_handoff`) |
| `LIFE-DELETE-001` | `--defer-provider` runs every step but provider-destroy, keeps the bootstrap state under the slot, removes the credential files; deletion writes the tombstone; the record names the repository as kept | `tests/contract/test_project_retirement.py::test_defer_provider_keeps_the_state_for_revocation`, `tests/contract/test_reconciler_dispatch.py::test_delete_consumes_the_slot` | — (`deletion`) |
| `LIFE-LIVE-001` | On the deployment, through `routes.control` only: the lifecycle's operations read through `/v1` — create, sleep, wake, resize `standard` succeeded; resize `large` failed `capacity_exhausted`/`admission` with the profile unchanged; export succeeded and its URL was not readable a second time; delete succeeded; a second create refused `no_slot` with no row | — | `tests/external/test_session38_public_lifecycle.py::test_the_operations_read_as_the_lifecycle_ran`, `::test_the_refused_resize_changed_nothing`, `::test_the_second_creation_was_refused_without_a_row` (external `lifecycle_operations_live`) |
| `LIFE-LIVE-002` | On the deployment, through the slot's own door: the claimed administrator's `/auth/me` answered 200 during the lifecycle; the slot's routes answered the edge's 404 while asleep and answer it now; the archive's member schemas are `app` and `api` only | — | `tests/external/test_session38_public_lifecycle.py::test_the_creator_claimed_the_project`, `::test_a_sleeping_and_a_deleted_project_answer_the_edges_404`, `::test_the_export_holds_only_the_customer_schemas` (external `lifecycle_project_door_live`) |
| `OPN-LIVE-001` | On the deployment: the reconciler's unit is enabled, came back after the reboot and holds no listener; the slot is `consumed` with its tombstone; the registry reads `agrees` × 3 and `agrees (deleted)` for the slot; the slot's volumes are absent; the slot's document shared no `ISOLATED_FIELDS` value with A, B or the control project; control-prod's REST route is withheld and its document reads REST unpublished | — | `tests/deployment/test_session38_reconciler.py::test_the_reconciler_is_enabled_and_listens_nowhere`, `::test_the_slot_was_consumed_and_its_volumes_removed`, `::test_the_registry_agrees_including_the_deletion`, `::test_the_slot_was_isolated_from_every_project`, `::test_the_control_projects_rest_route_is_withheld` (host `reconciler_live`) |

**Expected counts** — Run 10 counts them from the tuples, never from this prose
(D1628): requirements **312 → 330**, `CLAIMS` **219 → 237**, `OFFLINE_CLAIMS`
**74 → 89**, ADRs **255 → 261**.

**Claims** (`src/agentic_postgres/evidence_claims.py` `CLAIMS`, a block commented
*Session 38 (ADR 0256-0261)*): offline — `reconciler_claim`,
`reconciler_dispatch`, `control_project_operations`, `project_states`,
`registry_after_operations`, `compute_profiles`, `resize_message`,
`region_and_document`, `rest_flag`, `slots`, `capacity_refusals`, `sleep_wake`,
`export`, `admin_handoff`, `deletion` — **these fifteen in `OFFLINE_CLAIMS`**,
with the per-session assertion in `test_session_thirty_eight_gate_modes.py`
(D1237: assert THESE are in the set, never its size). External —
`lifecycle_operations_live`, `lifecycle_project_door_live`. Host —
`reconciler_live`. `CLAIM_INTRODUCED_IN` gains a row at 38 for each.

**Existing entries that move** (each a passing proof made stricter, never
weakened — CLAUDE.md §6):

- **`KEY-MINT-001`'s `test_a_demotion_narrows_a_key`** and the role half of
  `test_scopes_are_bounded_by_the_vocabulary_and_the_role` stop patching
  `ROLE_SCOPES` (D2109): the real table now differs, and the uniformity
  assertion is replaced by the exact table (D2165).
- **`CTL-OPS-001`**: `test_project_creation_is_refused_as_not_available`
  (`test_operation_types.py:72-87`) is REPLACED by its exact-set form — the
  eight types that stay refused are each refused `not_available`, and the five
  accepted ones are proved by `OPN-API-001`. `test_every_operation_type_names_a_ledger_row_and_none_is_accepted_while_planned`
  is renamed `…_and_is_accepted_iff_its_row_is_reachable` (the `trial` rules,
  D2170); its registry node id moves in the same commit.
- **`LEDGER-001`**: the schema test reads six statuses.
- **`CTL-REG-001`**: `test_registry_reports_three_outcomes` gains the deleted
  outcome's two cases (OPN-REG-001 holds them; the old node id stays).
- **`THR-*` table rows**: five added in Run 10 (§5 Run 1 item 3); none removed.
- **`port_allocation`, the rotation trio**: re-declared by the sweep (D2187).

**New environment gates: two**, in `tests/conftest.py`'s roster:
`APG_LIFECYCLE_RECORD_FILE` (host and external) and `APG_SLOT_OUTPUTS` (host —
the deleted slot's deployed document, copied on Sheet K2); the reconciler proofs
read the host directly. **The Session 38 gate accepts exactly
the Session 37 gate's flags plus `--lifecycle-record-file FILE` and
`--slot-outputs FILE`** (the derivation diff proves it, D1133).

---

## 4. Irreversible operations

| Operation | Where | What makes it safe |
|---|---|---|
| The control set's `0004` frozen into `projects/control/migrations/released.lock.json`, and its proposal committed | Run 4 | `bin/migrate.sh --project project.control.example.yaml freeze-lock`; the proofs apply the release set then the control set's four as `migration_user` before the freeze; `AP900` down; the proposal by the product's own `propose` (D2183); no released migration (D912) |
| `CURRENT_SESSION` 37 → 38; `VERSION` 1.15.0 → 1.16.0; six Ledger rows → `trial` | Run 10 | All-or-nothing (D690); `README.md:7`; every `--session 37` / `--through-session 37` literal on the documented path moved and counted per file (D678/D1484); the `trial` rules (D2170) |
| `bin/session-38-check.sh` | Run 10 | Derived from 37's by diff (D1482); header and usage rewritten whole (D1488); exactly two flags added; `SHELL_COMMANDS`; `chmod 755` before `git add` |
| **host.yaml → schema 4, both copies** | Sheet H1 | The agent writes the candidate as `op` (`s38-hostyaml.py`, a backup of each copy first), `diff` read; the operator installs `/etc/agentic-postgres/host.yaml` (root); `load_host_manifest` reads both before the first deploy |
| **The reconciler installed and enabled** | Sheet RC1 | `reconciler.sh install` writes the unit and `/var/lib/agentic-postgres/exports` (0700); `status` → *idle*; a stop is one `systemctl stop` |
| **Provider resources for `slot1-prod`** (an Infisical project and identity, two R2 buckets and tokens, a B2 bucket and key, a DNS record) | Sheets P1, SL1 | By hand and by `bootstrap-providers --apply` as for control-prod (D2061: shred by hand); the Infisical plan upgraded first (D2146); `--plan` read before `--apply` |
| **A production certificate for `slot1.agenticpostgresql.com`** | Run 12, the creation's first deploy | `slot.sh status` reads the record `ready` (A only, D2148) before the type is used; one attempt; a failed issuance finishes the operation `failed` and is a stop |
| **The slot created, slept, woken, resized, exported and deleted** | Run 12 | Through `/v1` only; one operation at a time; the probe running; a failure at any step is read before the next is sent (D1510) |
| **`slot1-prod` consumed** | Run 12 | The tombstone; no command removes it (LIFE-SLOT-001); the backup repository kept (ADR 0187) |
| The slot's Infisical identity revoked | Sheet SL4 (after the tag) | `slot.sh revoke` with the operator's credential, shredded after |
| The reboot | Sheet B1 | After the lifecycle and A1's `agrees`; the four project units and the reconciler read before the sweep |
| Tag `1.16.0` on the deployed commit | Run 12 | After the merge exits 5 for the expected reasons only (§7); from the WORKSTATION (D2041) |

---

## 5. Build order, run by run

Each run ends with a `**Done.**` paragraph written by the executor: what was
measured, the numbers, the rows it added, and — for a code run — the CI verdict
by full SHA. The targeted modules run ONCE at the run's close and only a failing
module is re-run. `ruff format && ruff check` before every commit; `chmod 755
bin/*.sh bin/*.py deploy.sh` before every `git add`; messages from a file with
`-F`, ending with the attribution line the session's system reminder gives.
**Grep the plans for every third party before measuring it.** **A run that
renames, adds or removes a test function runs `test_acceptance_registry` and
`test_evidence_claims`** (D1119); **a run that adds a module under
`src/agentic_postgres/` runs `test_repository_contract`** (D2114); **a run that
adds a top-level deployed-document member runs `test_doctor_redaction`** (D2091)
and the new offline leaf test; **a run that changes rendering re-renders BOTH
example projects and the control example** (`./deploy.sh --project
project.example.yaml --capabilities capabilities.example.yaml --render-only`, the
same for `project.second.example.yaml` and `project.control.example.yaml`; delete
what each publishes under `.generated/` except the two fixture renders the gate
reads, D1507); **a run that adds or removes a `bin/` command runs
`test_cli_contract` and `git add`s it first** (D1014); **a run that touches a
documentation page runs `test_documentation_index` and
`test_session12_documented_path`**; **every new test module carries
`pytestmark` before its first test** (D1240) and the sweep-selector guard
(D1242) joins the targeted list. **The Docker-backed modules share Session 37's
`tests/contract/control_cluster.py`** (`docker rm -fv`, D2098); the reconciler's
Docker-backed tests use it plus a second throwaway PROJECT cluster for the
handoff (rig 38c's code, kept as a fixture).

### Run 1 — the rigs, Sheet E0, the threat list, and ADRs 0256–0261

**Documentation only. Push, say it is pushed, read NO CI verdict** — except
that, because `docs/threat-model.md` and `docs/decisions/README.md` are parsed
by contract tests, run `test_acceptance_registry`, `test_decision_index` (or
whatever indexes the ADRs — grep `decisions/README` in `tests/contract/`) and
`test_documentation_index` once before the push.

Rigs live in WSL `~/s38/run1/rig38/` and are copied to the scratchpad. **Each
names its control and is recorded with what it printed.**

1. **Rig 38a — the root render's hand-back** (D2153): `sudo -E env
   SUDO_UID=$(id -u) SUDO_GID=$(id -g) ./deploy.sh --project
   project.example.yaml --capabilities capabilities.example.yaml --render-only`
   vs the same with `env -u SUDO_UID -u SUDO_GID` — read `stat -c %U` of
   `.generated/fixture-alpha-dev` after each (control: the second is root-owned;
   restore with `sudo chown -R`). **Note:** `--render-only` may not need root;
   read `deploy.sh:292` first and, if the render path never chowns, read the
   hand-back from `bin/deploy-project.py:318-362` and record that the live half
   is Run 11's first reconciler deploy.
2. **Rig 38b — stop/start under the pinned Compose and Traefik** (D2155): a
   throwaway Compose project of two services (the pinned PostgREST and Postgres
   images from `versions.env`) with a label router on a throwaway Traefik at the pinned
   digest (Session 37's rig 37d is the template, `~/s37/run1/rig37/`). Read:
   container ids and `StartedAt` before `compose stop`, after `stop` (state
   `exited`, ids unchanged), after `start` (ids unchanged, `StartedAt` moved);
   the route sampled at 0.1 s through stop and start (expected: the edge's 404
   while stopped, 200 after start, the gap timed); **control**: `compose up -d
   --force-recreate` moves the ids. Also read `docker compose stop` then a
   `compose up -d --wait` (what the reboot path would do) — ids unchanged or
   not, recorded.
3. **Rig 38c — the handoff by hash** (D2163): a container from
   `POSTGRES_IMAGE` with the release set applied (`tests/contract/test_auth_endpoints.py:119-271`'s
   fixture is the model), the auth app in-process (`create_app("auth")`, the
   `drive` helper's shape), the administrator created with
   `auth_bootstrap_administrator` as the superuser with a random password,
   `auth_open_password_reset(user, user, sha256(T), now()+24h)` as the superuser,
   then `POST /auth/reset-password {reset_token: T, password}` → 200 and `POST
   /auth/login` with the new password → 200. **Controls**: a wrong `T` → the
   route's refusal; `T` a second time → refused; the bootstrap password →
   `/auth/login` 401 after the reset (it was rotated by the consume). Also
   **rig 38c'** — the profile numbers (D2156): from E0's `docker stats` (below),
   compute each service's resident memory for control-prod (the idlest) and
   alpha, choose `small` and `large` by the D2156 rules, and run each through
   `config.load_project_manifest` on a copy of `project.example.yaml` at schema
   10 (the schema change is Run 3's, so the rig validates the MEMBERS through the
   validators on a schema-9 manifest carrying the profile's values explicitly).
4. **Rig 38d — the dump** (D2164): `pg_dump -U postgres -Fc -n app -n api
   --no-owner --no-privileges` of the rig 38c database, `pg_restore --list` →
   schemas named; **control**: the same without `-n` lists `app_private`.
   Record the archive size with the release domain's seed rows.
5. **Rig 38e — the presign path offline** (D2164): `R2Adapter.presign_get`
   called with botocore's `Stubber` or a dummy endpoint — read the `X-Amz-Expires`
   the adapter writes and whether it takes an expiry argument
   (`storage_client.py:323-336`); if it does not, Run 7 adds one with a bound of
   900 (recorded). The LIVE presign and expiry are Run 12's (control: a URL past
   900 s → 403, D362).
6. **Rig 38f — claim, kill, restart** (D2152): the control cluster with a draft
   `0004` applied by hand in the rig (not the tree's); two `psql` sessions
   claiming concurrently with `SKIP LOCKED` (distinct rows, measured 20 times);
   a claimer killed (`docker exec … kill` of its backend, or the Python
   process) between claim and finish, then `control_interrupted_operations()` →
   the row, finished `interrupted`; **control**: an uninterrupted claim/finish
   → `succeeded`, attempt 1.

**Sheet E0** (the operator; reads only — `s38-e0.sh` written by the agent, shipped
to `/home/op`, sha256 printed):
`free -m`; `docker stats --no-stream --format '{{.Name}} {{.MemUsage}}'` (all
containers); `diff` of `/etc/agentic-postgres/host.yaml` and the checkout's
(D2020); `systemctl is-enabled` of the four units; `sudo ls -la
/root/.config/agentic-postgres/bootstrap/` (expected empty, D2084); `grep -n
'storage:\|backup:\|mirror:\|account_id\|endpoint\|region\|bucket'` of
`/home/op/agentic-postgres/project.alpha.yaml` (the provider facts `slots.defaults`
copies — no secret is in a manifest, ADR 0093's sensitive-key check); `dig +short
A slot1.agenticpostgresql.com @1.1.1.1` and `AAAA` (expected today: the
wildcard's Cloudflare addresses, D2083); `df -h /var/lib/docker`. **The operator
states on the sheet that the Infisical plan is upgraded** (D2146) — or that it is
not yet, which does not block Runs 2–10.

**The threat list made specific** (D1978): the four hosted items naming 38
(`docs/threat-model.md` #4 `:196-200`, #7's 38 half `:209-214`, #8 `:215-218`,
#12 `:238-241`) rewritten with the negative test each owes BY NODE ID (§2), plus
**two new items**: *the reconciler as a standing root actor* (OPN-DISPATCH-001,
OPN-CLAIM-001, OPN-LIVE-001) and *slot confusion* (LIFE-SLOT-001,
LIFE-DELETE-001). They stay list items until Run 10 moves them into the table
(D2056's order) as `THR-LIFE-EXHAUSTION`, `THR-LIFE-PLANE-CONFUSION`,
`THR-LIFE-DELETION`, `THR-LIFE-STORAGE`, `THR-OPN-RECONCILER`,
`THR-LIFE-SLOT` — **no `|` inside a cell** (the parser drops the row silently).
Storage exhaustion's control in 38 is admission's disk floor and the Ledger's
*no quota* sentence; its residual says so.

**ADRs** (each indexed in `docs/decisions/README.md`):
**0256** the reconciler and the operations it executes (D2151–D2154,
D2159–D2160, D2165–D2168, D2173, D2178–D2179, D2184, D2188); **0257** slots,
region and the Infisical identity (D2146, D2148–D2150, D2158, D2161, D2180);
**0258** compute profiles and resize (D2156–D2157); **0259** sleep, wake and
export (D2155, D2164, D2182); **0260** the first-admin handoff by hash (D2163);
**0261** the `trial` status (D2170, amending 0254). **ADR 0251 §6 is amended**
for D2172 (one paragraph: the REST flag's reader).

**Done.** 2026-10-07/08, documentation only, no CI read. Six rigs run with
their controls, scripts and transcripts in WSL `~/s38/run1/` (`NOTES.md` the
record) and the scratchpad's `s38/run1/`. **38a** (D2153): a root render (uid 0
in a container over a copy of the checkout — WSL `sudo` asks for a password)
WITH `SUDO_UID`/`SUDO_GID` left 0 root-owned files; the control without them
left 3 (directory and lock `root:root`, `outputs.json` unreadable); **pass 1,
a render that failed on Compose validation with both variables set, left the
lock `root:root`** → D2189. **38b** (D2155): `compose stop` 0.71 s, route 200 →
502 → timeout → Traefik's `404 page not found` (19 bytes), ids kept; `compose
start` 2.16 s, first 200 at +4.64 s (Traefik routes only a HEALTHY container),
ids unchanged; controls: `--force-recreate` moved the ids, `stop` + `up -d
--wait` did not; Compose v5.1.3's `start` has `--wait` → D2192. **38c**
(D2163): the handoff by hash end to end on the release set — `T` → 200, the
chosen password logs in; a wrong `T`, `sha256(T)` presented as the token, `T`
twice and the bootstrap password afterwards → 401 each. **38c′** (D2156): the
profiles from E0 — `small` 192, `standard` 304, `large` 840 MiB charged,
accepted by the three validators and by `load_project_manifest`, the control
refused by both; the caps rule unsatisfiable → D2193, ADR 0258's table.
**38d** (D2164): `-n app -n api` 45,391 bytes with no `app_private`; control
without `-n` 318,442 bytes with it; the release seeds no rows. **38e**:
`presign_get` takes no expiry (signs the project's 300 s TTL) and the adapter
has no upload of bytes → D2190; control: `ExpiresIn=900` on its client signs
900. **38f** (D2151–D2152): claims distinct with `SKIP LOCKED` (B 0.13–0.17 s)
AND without it (B blocked 1.84–1.87 s); the same row 10/10 only with neither
the row lock nor the status recheck → D2191 rewrites Run 4's M2; a claimer
SIGKILLed mid-step was read back `running step=deploy-1`, finished `failed
interrupted`, never reclaimed (control: `succeeded`, attempt 1). **Sheet E0**
(2026-10-07 20:28Z, `/home/op/s38-e0.txt`): 1,725 MiB available, 912 of 1,600
committed, doctor capacity 5 ok; control-prod resident 620–631 MiB; caps 2,880
per project; four units enabled and active; the bootstrap directory empty;
`dig` present, `slot1` resolves to the proxied wildcard (104.21.4.166,
172.67.132.69 and two AAAA); 20 GiB free; flock, systemctl, dig, ss present;
**Docker Compose v5.4.0** with `start --wait` (D2192 decided); **the `/etc`
host.yaml is schema 2, `root:root 0600`** → D2194 corrects Sheet H1. The
operator did not state the Infisical plan's status on the sheet (D2146) — owed
before Sheet SL1, not blocking Runs 2–10. **The threat list**: items #4, #7,
#8, #12 rewritten with their negative tests by node id, items #14 (the
reconciler as a standing root actor) and #15 (slot confusion) added. **ADRs
0256–0261** written and indexed; **0251** (item 6, the REST flag's reader) and
**0254** (by 0261) amended. Rows **D2189–D2194** added. NEXT FREE: D2195, ADR
0262.

### Run 2 — the debts: the REST flag's reader (D2172) and the offline leaf classifier (D2162)

**Code.** CI read by full SHA.

1. **`runtime_override.build_override(..., rest_enabled: bool)`** — required;
   every caller passes it (grep `build_override(` and `render_override(` in
   `src/`, `bin/`, `tests/`: `bin/deploy-project.py:2215`, `:2400`, and ~25 test
   call sites — D2087 counted them; each test passes `rest_enabled=True`
   unless it is about the flag). With `False`, the `REST_SERVICE` entry carries
   **no `traefik.*` label** (`:743-749`). `rendering.build_compose_env` emits
   `API_REST_ENABLED=true|false` from the merged `rest` block
   (`rendering.py:1814`), and `COMPOSE_ENV_KEYS` gains it.
2. **`bin/deploy-project.py`**: `_override_rest_enabled` reads
   `API_REST_ENABLED` from the rendered `compose.env` the way `_override_control`
   reads `AUTH_APP_MODE` (D2087); with it false, the REST observation block
   (`:2768-2868`) is skipped: `rest_status = "unavailable"`, `api_block =
   API_NOT_PUBLISHED`, one printed line *"REST disabled by the manifest
   (api.rest.enabled: false): not observed"*.
3. **`deployed_output`**: a coherence rule — `build_deployed_document` takes
   `rest_enabled` (required) and refuses `rest_status == "ready"` with it false.
   **The document records no new member in this run** (outputs 21 is Run 3's,
   and `deployedApi`, `outputs.schema.json:1151`, is not widened for a flag the
   rendered `compose.env` already carries); if the run finds a reader that needs
   the flag in the document, that is a row.
4. **The leaf classifier offline** (D2162): `src/agentic_postgres/isolation_matrix.py`
   holds `MUST_DIFFER`, `MUST_MATCH`, `RELEASE_STATE`, `NOT_AUTHORITY_PREFIXES`,
   `_matches`, `_classify` moved verbatim from
   `tests/deployment/test_session12_isolation_matrix.py:81-300`; the live module
   imports them (its proofs unchanged — run `--collect-only` to prove the node
   ids). `tests/contract/test_isolation_leaves_offline.py` builds a deployed
   document per fixture render with `build_deployed_document` (the kwargs
   `tests/contract/test_deployed_output.py` uses) and classifies every leaf.
   Control: a planted leaf `zz.unclassified` fails it.

**Tests**: `tests/contract/test_rest_flag.py` (three, §2), the offline leaf
test, and every existing `build_override` test re-run. **Battery** (§1 of
CLAUDE.md): M1 the label omission removed (the router present with the flag
off) → `test_a_disabled_rest_service_has_no_router` FAILED; M2 the deploy's skip
removed → the deploy test FAILED; M3 the coherence rule removed → FAILED; M4 a
new leaf added to a fixture's built document → the offline test FAILED; control
for each: the same module on the unmutated tree, green, in the same invocation.
**Targeted**: `test_rest_flag`, `test_isolation_leaves_offline`,
`test_runtime_override*` (grep), `test_deployed_output`, `test_observation`,
`test_doctor_redaction`, `test_repository_contract`,
`tests/deployment/test_session12_isolation_matrix.py --collect-only`,
`test_render_isolation`, the three example re-renders. **Both fixtures'
`.generated` renders must be byte-identical to before** (REST enabled on both) —
`diff -r` against a copy taken before the run.

**Done.** 2026-10-08 (scripts and notes in WSL `~/s38/run2/`). **The flag's
reader (D2172):** `build_override`/`render_override` take a REQUIRED
`rest_enabled`; off, PostgREST's override entry carries no `labels` (its JWKS
mount stays; the base model gives it only `apg.traefik.scope` and
`traefik.docker.network`, and the edge exposes nothing by default).
`compose.env` gains `API_REST_ENABLED` (`true`/`false` from the merged `rest`
block — the default is `false`; all six manifests read: both fixtures, alpha and
beta `true`, the control example and `/home/op/control.yaml` `false`). The
deploy reads it once through `_rest_enabled` (anything but `true`/`false`
refused), passes it to both override renders, and puts the served-document read
and `observe_api` in the `else` of `if not rest_enabled:`, printing *"REST
disabled by the manifest (api.rest.enabled: false): not observed"*.
`build_deployed_document` takes a REQUIRED `rest_enabled` and refuses `ready`
beside it false. 6 test builders and 29 of 29 test override calls pass
`rest_enabled=True`. **D2189**: `render_project` hands the lock back on its
failure path (`restore_lock_ownership`), with
`test_render_atomicity.py::test_a_failed_render_under_sudo_hands_the_lock_back`.
**The offline leaf classifier (D2162, D2195)**: the four tables and the
classifier moved verbatim (201 + 21 lines) to `tests/deployment/isolation_matrix.py`
— not `src/`, D204 — and the live module's five node ids are unchanged;
`tests/contract/test_isolation_leaves_offline.py` classifies every leaf of a
deployed document built from each of the three example renders (statuses from
each project's own manifest) AND every one of the 189 leaves the deployed branch
of `outputs.schema.json` declares (`control.enabled`, `connectors.enabled`,
`migrations.project_set` among them); its first run reported
`project.lifecycle`, a walker defect (an `allOf` `if/then/else` read as a
scalar), fixed in the walker. **Re-render (D2196)**: the only difference per
fixture is `compose.env` line 81, `API_REST_ENABLED=true`. **Targeted** (60
modules, once): **2,490 passed**. **Battery 5/5 killed**, each control PASSED
in the same invocation: M1 the label omission removed →
`test_a_disabled_rest_service_has_no_router` FAILED; M2 the deploy's skip
removed → `test_the_deploy_records_rest_unpublished_without_reading_it`
FAILED; M3 the coherence rule removed →
`test_a_ready_rest_route_with_the_flag_off_is_refused` FAILED; M4
`control.enabled` dropped from the classifier → the offline leaf test FAILED; M5
the failed render's lock hand-back removed → its test FAILED. Rows **D2195,
D2196**. CI: recorded in Run 3's commit.

### Run 3 — the schemas: host 4 (region, slots), manifest 10 (compute), outputs 21, the profile table

**Code.** CI read by full SHA.

1. **`schemas/host.schema.json`**: enum `[2, 3, 4]`; at 4 `capacity` AND
   `region` required (`region: {id ^[a-z][a-z0-9-]{2,31}$, display_name
   1-64 printable, provider 1-32, location ^[a-z0-9-]{2,16}$}`,
   `additionalProperties: false`); `slots` optional at 4 and forbidden below
   (`{defaults: {…}, declared: [{key, domain}]}` — `defaults`' members are
   exactly the provider facts the slot manifest needs, read from
   `project.schema.json`'s `storage`, `backup`, `backup.mirror` required members
   and E0's grep of alpha's manifest; **no secret**, the sensitive-key check
   covers it). `host_config.py`: `region()` and `declared_slots()` beside
   `declared_capacity()` (`:114-141`), each the documented sole reader.
   `host.example.yaml` → 4 with a region and one example slot
   (`slot1-dev`, `slot1.example.test`). Every reader of `load_host_manifest`
   (§0's list of eleven) re-read: none branches on the version (they key on
   presence), so schema 4 needs no reader change except the two new functions —
   the run records that it checked each.
2. **`services/auth-api/app/compute_profiles.py`** + **`src/agentic_postgres/compute_profiles.py`**
   (D2156) with rig 38c's numbers; `RESIZE_WINDOW_SECONDS = None` (D2157);
   `resize_message()`. `test_auth_service_shape.SHARED_MODULES` gains it.
3. **Manifest schema 10**: `schemas/project.schema.json` enum + `compute:
   {profile: enum[small, standard, large]}` + the `:1011-1030`-shape gate with
   `maximum: 9`; `config.SUPPORTED_PROJECT_SCHEMA_VERSIONS` gains 10,
   `PROJECT_COMPUTE_FROM = 10`; `config.compute_profile(manifest)` (absent →
   `standard`); `validate_project_semantics` refuses a profile-owned member
   beside `compute`; **the merged budget used everywhere** — `database_budget()`
   (`:777-789`), the auth/storage memory and the pools — takes the profile's
   values when `compute` is present (grep every reader of
   `DATABASE_BUDGET_DEFAULTS`, `API_APP_DEFAULTS`, `storage.memory_limit_mb`,
   `SERVICE_RESOURCE_DEFAULTS` in `src/` and `bin/` before changing one, D979).
   **The examples**: `project.example.yaml`, `project.second.example.yaml` and
   `project.control.example.yaml` move to schema 10 WITHOUT `compute` (D2085's
   rule: fixtures at the newest version); every pin naming 9 moves (§0's list:
   `test_project_manifest.py:823`, `:847`, `test_project_manifest_control.py:46`,
   `:108`, `test_connector_facility.py:77`, `test_deploy_connectors.py:390`,
   `test_project_agent_surface.py:547`).
4. **Outputs schema 21** (D2161): `region` (the four members, or the whole
   member `null` from an archived document) and `compute: {profile}` in the
   rendered and deployed documents; `deployed_output.SCHEMA_VERSION = 21`;
   `outputs.schema.json` enum; `output_migrations.migrate_v20_to_v21`
   (`CURRENT_VERSION` 21; the guard at `:267` and the chain `:333-336` extended
   the way `migrate_v19_to_v20` was added); the render takes the region from the
   host manifest (`render-config.py` already loads it, `:186`, `:211`);
   `bin/control.py` `CONTROL_SINCE_VERSION` unchanged; `test_doctor_redaction`'s
   `PRINTABLE_BLOCKS` gains `region` and `compute` (neither is a credential —
   D2091's reasoning); `isolation_matrix`: `region.*` MUST_MATCH, `compute.profile`
   NOT_AUTHORITY. **ADR 0241's bound** reads 21 and 20; `test_disaster_kit.py::_previous_version`
   subtracts the two members (D2085's precedent).

**Tests**: `test_compute_profiles.py` (§2's five plus the resize message),
`test_host_manifest.py::test_schema_four_requires_a_region` (+ the slot shape),
`test_output_migrations.py::test_v21_adds_region_and_profile`, and the offline
leaf test now covering the two members. **Battery**: M1 `standard` with one value
off by one → `test_standard_is_todays_defaults` FAILED; M2 the owned-member
refusal removed → FAILED; M3 pids from the defaults instead of the profile →
FAILED; M4 `region` dropped from the classifier → the offline leaf test FAILED;
M5 the v21 step leaving `compute` out → FAILED; controls green. **Targeted**:
the new modules, `test_project_manifest*`, `test_host_manifest`,
`test_output_migrations`, `test_deployed_output`, `test_disaster_kit`,
`test_doctor_redaction`, `test_capability_compiler::test_each_schema_version_constant_matches_its_schemas_enum`,
`test_render_isolation`, `test_isolation_leaves_offline`, `test_repository_contract`,
`test_auth_service_shape`, the three re-renders (alpha's and beta's renders on
the host move only `schema_version`, `template_version` later, `region`,
`compute` — four leaves; recorded for R1).

**Done.** 2026-10-08/09 (paused overnight at the operator's request, resumed;
scripts and notes in WSL `~/s38/run3/`). **Run 2's CI: run 37686087243
(`contract`) completed `success` on `8f4fcf0`.** **Host schema 4** (D2149,
D2161): enum `[2, 3, 4]`; at 4 `capacity` and `region` required, `region` and
`slots` forbidden below 4; `slots.defaults` carries exactly the non-derived
provider facts (`storage {account_id, jurisdiction}`, `backup {account_id,
jurisdiction, mirror {endpoint, region}}`, patterns copied from the project
schema) and `slots.declared[{key, domain, mirror_bucket?}]`; `host_config`
gains `region()`, `declared_slots()`, `slot_defaults()` (each the sole reader)
and a refusal of a repeated slot key or domain; `host.example.yaml` at 4 with
`eu-example-1` and `slot1-dev`. **All eleven readers of `load_host_manifest`
(nine in `bin/`, two in `src/`) were read: none branches on the version.**
**Profiles** (D2156, ADR 0258's table): `services/auth-api/app/compute_profiles.py`
(standard library; `RESIZE_WINDOW_SECONDS = None`) loaded by
`src/agentic_postgres/compute_profiles.py`; `SHARED_MODULES` gains it.
**Manifest 10**: `compute: {profile}` with the version-10 gate;
`config.compute_profile()` and **`config.apply_compute_profile()`, called once
in `load_project_manifest`** (D2198); `build_compose_env(compute_profile=…)`
REQUIRED, merging the profile's resource overrides; the three examples at 10
without `compute`, seven pins moved. **Outputs 21** (D2197): `compute` on both
branches, `region` on the deployed branch only (`build_deployed_document(region=…)`
REQUIRED, the deploy passes the host manifest's), `migrate_v20_to_v21` adds
`compute: standard` only; `outputs_chain` step 20; `test_disaster_kit`'s
previous-version helper at 21; `isolation_matrix`: `region`/`region.*`
MUST_MATCH, `compute.` not authority; `PRINTABLE_BLOCKS` gains both. **Tests**:
`test_compute_profiles.py` (8), `test_host_manifest.py` (4 made stricter under
their names, 2 added), `test_output_migrations.py` (`v20` fixture; the chain
test renamed `…_at_version_21_…` with its registry node id; two v21 tests),
the offline leaf test now builds documents with a region. **Re-render**: each
fixture's `outputs.json` gains `compute: standard`, `schema_version` 21 and a
new `inputs.project_sha256` (the manifest's bytes moved 9 → 10);
`compose.env` unchanged. First runs found two TEST defects, not product ones:
the example sets two profile-owned members (refused by name, as designed) and
declares no `api.app`. **Targeted** (127 modules, once): 4,544 passed, 3
skipped; the 3 failures and 9 errors were version pins (`test_admission`'s host
fixture, `test_connector_facility`'s outputs pin) and the not-yet-regenerated
acceptance matrix — fixed, matrix regenerated, the four modules re-run: 107
passed. **Battery 6/6 killed**, each control PASSED: M1 `standard`'s
`shared_buffers_mb` 129 → `test_standard_is_todays_defaults` FAILED; M2 the
owned-member refusal removed → FAILED; M3 resources from the defaults → 
`test_pids_and_cpus_come_from_the_profile` FAILED; M4 `region.*` dropped from
the classifier → the offline leaf test FAILED; M5 the v21 step leaving
`compute` out → `test_v21_adds_region_and_profile` FAILED; M6 `region` not
required at host 4 → `test_schema_four_requires_a_region` FAILED. Rows
**D2197, D2198**. NEXT FREE D2199. CI: recorded in Run 4's commit.

### Run 4 — the control plane's half: `0004`, the routes, the roles, the states, the slot readings

**Code.** CI read by full SHA.

1. **`projects/control/migrations/templates/0004-control-operations.sql`**
   (manifest entry `20261007120004`, D912 — the three released ones untouched):
   `control_operations` gains `claimed_by text NULL`, `attempt integer NOT NULL
   DEFAULT 0`, `step text NULL`, `result jsonb NULL`, `result_secret text NULL`
   (the export URL, D2164); **a partial unique index** `ON (organization_id) WHERE type = 'project.create' AND status IN
   ('pending','running')` and one `ON (project_key) WHERE status IN
   ('pending','running')` (D2166); `status` gets `DEFAULT 'pending'`.
   `control_projects` gains `display_name text`, `slot text NULL`, `region_id
   text NULL`, `profile text NULL`, `deleted_at timestamptz NULL`; `adopted_from`'s
   CHECK widened to `('deployed_document','reconciler')`. New table
   **`app.control_slots`** (`key` PK, `state` CHECK of D2149's seven,
   `region_id`, `observed_at`; FORCE RLS; SELECT policy to `object_owner` for
   any authenticated caller — slot names are not secret; no write policy).
   Functions: `control_request_operation(p_user, p_org, p_project, p_type,
   p_arguments)` (DEFINER, `auth_service`; checks the caller's role per D2165 in
   SQL as well — the D2106 two-layer rule — and inserts `pending`);
   `control_cancel_operation(p_user, p_id)` (DEFINER, `auth_service`, pending
   only); `control_take_result_secret(p_user, p_id)` (DEFINER, `auth_service`,
   returns and NULLs `result_secret` for the requester only);
   `control_ready_slot_count()` → the API's `no_slot` reading with
   `observed_at` (DEFINER, `auth_service`); and the reconciler's, **INVOKER,
   granted to nobody** (D2093): `control_claim_operation`,
   `control_advance_operation`, `control_finish_operation`,
   `control_interrupted_operations`, `control_record_slots(jsonb)`,
   `control_mark_deleted`, and `control_adopt_project` re-created with the new
   members (a `CREATE OR REPLACE` with a wider signature is a new function —
   drop the old one in `0004` and grant nothing; `bin/control.py`'s
   `ADOPT_SQL` passes the new members as NULL for an operator adoption). The keys
   CHECK widened to five scopes. **`0004` then frozen; the proposal committed**
   (D2183): `bin/migrate.sh --project project.control.example.yaml freeze-lock`,
   then `bin/migrate.py propose` exactly as D2136 recorded.
2. **`operations.py`** (service): `ACCEPTED_TYPES` stays EMPTY in this run (the
   rows are `planned` until Run 10 — the guard holds them equal); a
   `RESULT_MEMBERS` map per type (D2151's refusal); `ARGUMENT_SCHEMA_PATH`.
   **`schemas/operation-arguments.schema.json`** (D2154) and pydantic models in
   `models.py` mirroring it (a test holds the two equal on every example).
3. **Routes** (`control_routes.py` + `control_service.py` + `control_repository.py`):
   `POST /v1/projects` reads `{organization, name, profile, admin_username,
   handoff_sha256}` → `202 {operation}` when accepted (`not_available` else, as
   today); `POST /v1/projects/{key}/sleep|wake`, `PUT /v1/projects/{key}/compute
   {profile}` (`202` + the resize message, D2157), `POST
   /v1/projects/{key}/export`, `DELETE /v1/projects/{key}`, `POST
   /v1/operations/{id}/cancel`; `GET /v1/operations/{id}` returns
   `download_url` once (D2164); `GET /v1/projects[/{key}]` gain `state`
   (D2159), `display_name`, `region`, `profile`; `GET /v1/slots` is **not**
   built (the count is internal). `no_slot` before the row (D2160). The closed
   error enum (`errors.py`): `capacity_exhausted`, `conflict`, `invalid_request`,
   `not_found`, `not_available`, `operation_failed`, `interrupted`,
   `could_not_determine`, plus Session 37's words. `control_roles.py`: the
   vocabulary, `ROLE_SCOPES` (D2165), `KEY_SCOPES` + the three key-allowed
   routes, `MATRIX` entries.
4. **`services/auth-api/app/control_states.py`** (D2159) — pure.
5. **The Ledger** (text only, the rows stay `planned`): the six rows'
   `stage5_reality`/`today` corrected to what was built; **`idle_sleep`**
   (D2147) added. `bin/render-reality-ledger.py --write`.
6. **`app-contract.sh --update --snapshot control`**; `--check`.

**Tests**: `test_control_projects.py`, `test_control_states.py`,
`test_reconciler_claim.py` (the SQL half, on `control_cluster`), the reworked
`test_operation_types.py` and `test_control_keys.py` (D2165), and the
contract. **Battery**: M1 the partial index dropped → `test_one_operation_at_a_time`
FAILED; M2 `SKIP LOCKED` removed → `test_two_claimers_get_distinct_rows` FAILED
(run 20× — a race test needs repetitions, recorded) — **superseded by D2191**:
M2a the row lock and the outer recheck removed → `test_two_claimers_get_distinct_rows`
FAILED, M2b `SKIP LOCKED` removed → `test_a_claimer_does_not_wait_for_an_open_claim`
FAILED; M3 `control_take_result_secret`
not NULLing → `test_the_download_url_is_returned_once` FAILED; M4 a key allowed
on create → FAILED; M5 `no_slot` checked after the insert → `test_no_ready_slot_refuses_before_a_row`
FAILED; M6 an interrupted state read as `ready` → FAILED; M7 the claim granted
to `auth_service` → `test_the_claim_functions_are_executable_by_no_role`
FAILED; controls green. **Targeted**: the control modules (Docker-backed, once),
`test_reality_ledger`, `test_app_contract_aggregate`, `test_project_migration_sets`,
`test_control_set`, `test_auth_service_shape`, `test_acceptance_registry`,
`test_evidence_claims`, `test_repository_contract`.

**Done.** 2026-10-08 (scripts and notes in WSL `~/s38/run4/`). **Run 3's CI:
run 37743818180 (`contract`) completed `success` on `806008c`.**
**`0004-control-operations.sql`** (manifest `20261007120004`; `0001`–`0003`
untouched): `control_operations` widened (`claimed_by`, `attempt`, `step`,
`result`, `result_secret`; `status DEFAULT 'pending'`; CHECKs: arguments an
object, `error_code` the five outcomes, a failure carries a code, a secret only
on a succeeded export), the two partial unique indexes (D2166), an INSERT and an
UPDATE policy; `control_projects` widened (`display_name`, `slot`, `region_id`,
`profile`, `app_route`, `deleted_at`; `adopted_from` CHECK widened);
**`app.control_slots`** (FORCE RLS, read by any caller with a user, no write
policy). Granted to `auth_service`: `control_request_operation` (D2165's ranks
in SQL), `control_cancel_operation`, `control_take_result_secret`,
`control_ready_slot_count`, `control_project_operations`, and the four readers
dropped and re-created wider. **Granted to nobody, INVOKER**: claim, advance
(with the creation's key, once), finish (refuses a row not running, an outcome
without its code, an undeclared result member), interrupted, record_slots
(replaced whole), mark_deleted, `control_adopt_project` (re-created, the five new
members DEFAULT NULL, D2200) and `control_registry_rows`; `control_result_members`
a helper. Keys CHECK widened to five scopes. **Frozen and proposed** (D2183):
`freeze-lock --project project.control.example.yaml` (4 migrations, follows
20261003120039 computed, the release lock untouched); `propose --by
"claude-opus-5-5 Session 38 executor"` → `projects/control/proposals/d82e2831…json`:
lint passed, 43 applied from empty as `migration_user` in 11.6 s, surface empty,
**five destructive findings, each intended** (the two dropped CHECKs re-added
wider, the two dropped functions re-created, the `DELETE` inside
`control_record_slots`); the render removed after. **Service**: `operations.py`
(`ACCEPTED_TYPES` still empty, `EXECUTED_TYPES`, `RESULT_MEMBERS`,
`ARGUMENT_SCHEMA_PATH`; `src/agentic_postgres/operations.py` re-exports them);
**`schemas/operation-arguments.schema.json`** (D2154, patterns ended
`(?![\s\S])`, D2199) and `models.py`'s `CreateProjectRequest` /
`ResizeProjectRequest`; `errors.py` (`capacity_exhausted`, `conflict`,
`OPERATION_ERROR_CODES`); **`control_states.py`** (D2159, D2203);
`control_roles.py` (`projects:write`, `ROLE_SCOPES` now differing,
`KEY_SCOPES` + sleep/wake/resize, `PROJECT_WRITES`, `OPERATION_OF_ROUTE`);
routes `POST /v1/projects` (202), `POST …/{key}/sleep|wake|export`, `PUT
…/{key}/compute` (202 + the unmeasured resize sentence), `DELETE /v1/projects/{key}`,
`POST /v1/operations/{id}/cancel`; `GET /v1/operations/{id}` hands the export
URL once to the person who asked, never to a key; projects gain `state`,
`managed_by`, `display_name`, `region`, `profile`, `app_route`, `deleted_at`;
`main.control_paths()` gains the six paths; no `/v1/slots`. **Ledger**: the six
rows' `today`/`stage5_reality` rewritten to what is built (all still
`planned`), **`idle_sleep`** added (`planned`, 38 → 41); `reality-ledger.md`
re-rendered. **Control snapshot** re-captured (+604/−8), `--check` both match.
**Tests**: `test_control_states.py` (22), `test_reconciler_claim.py` (7),
`test_control_projects.py` (10), `test_operation_types.py` (+27: every write
`not_available` while planned, the schema's branches, the error codes, 24
schema/model examples), `test_control_keys.py` (the exact table; the viewer
refused `projects:write`; the demotion proof on the product's own table — two
tests reworked under their names, D2109's monkeypatches gone),
`test_control_set.py` (the new table and the three function sets, count 4).
First pass of the seven: 86 passed. **Targeted** (29 modules, once): 1,384
passed, 2 failed — `main.control_paths()` did not yet list the new paths (the
declared-paths guard doing its job); fixed, the two modules re-run: 61 passed.
**Battery 8/8 killed**, each control PASSED, the tree byte-identical after: M1
the per-project index dropped → `test_one_operation_at_a_time` FAILED (its
superuser insert half, D2204); M2a the row lock and the recheck removed →
`test_two_claimers_get_distinct_rows` FAILED; M2b `SKIP LOCKED` removed →
`test_a_claimer_does_not_wait_for_an_open_claim` FAILED (D2191's pair, 3 rounds
each); M3 the take not NULLing → `test_the_download_url_is_returned_once`
FAILED; M4 a key allowed on create → `test_the_roles_decide_who_writes` FAILED;
M5 the slot read after the insert → `test_no_ready_slot_refuses_before_a_row`
FAILED; M6 an interrupted operation read as the state before it → FAILED; M7
the claim granted to `auth_service` →
`test_the_claim_functions_are_executable_by_no_role` FAILED. Rows **D2199–D2204**.
NEXT FREE D2205. CI: recorded in Run 5's commit.

### Run 5 — the host's half: `stop|start`, `--defer-provider`, `bin/slot.sh`

**Code.** CI read by full SHA.

1. **`bin/project-runtime.sh stop|start`** (D2155) — usage, exit codes, root;
   `stop`: `edge-network.sh detach` then `compose.sh … --runtime --profile …
   stop`; `start`: `compose.sh … start` then the same `--wait` health reading
   `up` uses (read `:295-297` for how `--wait` is passed; `compose start` has no
   `--wait` — measured in rig 38b: if it does not, `start` polls `docker
   inspect` health for every service with a healthcheck, 120 s) then `attach`.
   **D2192 decided it: the host's Compose v5.4.0 has `start --wait`, so
   `start` runs `compose start --wait --wait-timeout 120` and no poll is
   written.**
   **Neither runs `materialize-secrets`, `render-secret-override` or
   `render-mount-digests`.**
2. **`project-retire.sh --defer-provider`** (D2158) in `retirement.py` (a step
   list variant: `provider-destroy` replaced by `keep-bootstrap-state`) and
   `project-retire.py`'s argument rules.
3. **`bin/slot.sh` + `bin/slot.py`** (D2149, D2150, D2148): `prepare`, `status`,
   `revoke`; `src/agentic_postgres/slot.py` for `state()` and the manifest
   builder (`slot_manifest(host, slot)` → a dict `config.load_project_manifest`
   validates; lifecycle `permanent`; storage, REST, app, backup with mirror
   enabled; connectors off; no `migrations`; `compute: {profile: small}`;
   `schema_version: 10`). `status`'s DNS reading uses `dig` (absent →
   `could not determine`). Exit codes 0/2/3/5/6.

**Tests**: `test_project_runtime_stop_start.py` (the `test_record_command`
recorder pattern for the commands' argv, plus the shellcheck guard),
`test_project_retirement.py::test_defer_provider_keeps_the_state_for_revocation`,
`test_slot_command.py` (five). **Battery**: M1 `start` materializes → FAILED; M2
`stop` runs `down` → FAILED; M3 `--defer-provider` deleting the bootstrap state
→ FAILED; M4 a tombstone removed by `prepare` → `test_nothing_removes_a_tombstone`
FAILED; M5 `status` folding an unreadable DNS reading into `ready` → FAILED.
**Targeted**: the three modules, `test_cli_contract`, `test_operator_commands_run_on_the_host`,
`test_shellcheck*` (grep), `test_project_retirement*`, `test_repository_contract`.

**Done.** 2026-10-08 (scripts and notes in WSL `~/s38/run5/`). **Run 4's CI:
run 37756302129 (`contract`) completed `success` on `1e6c040`.**
**`bin/project-runtime.sh stop|start`** (D2155, D2192): `stop` = `edge-network.sh
detach` then `compose.sh … --runtime --profile session2…N stop` (containers,
networks and volumes kept); `start` = `compose.sh … start --wait --wait-timeout
120` then `attach` -- no `materialize-secrets`, no renderer, no `--build`, no
`up`; both root, both need `--through-session`, `--defer` refused on them; usage
and header rewritten; shellcheck clean. **`project-retire.sh --defer-provider`**
(D2158, D2205): `retirement.DEFERRED_STEP_ORDER` (`keep-bootstrap-state` in
`provider-destroy`'s place), `steps`/`record` take `retired_state` REQUIRED,
`Step.moves`; the command moves the state to
`/etc/agentic-postgres/slots/<key>/retired-bootstrap-state.json` (0600 in 0700),
removes `/etc/agentic-postgres/credentials/<key>/`, records `provider.deferred`;
refused beside the credential file, for a non-slot key, over a kept state, or
with no state. **`bin/slot.sh` + `bin/slot.py`** (D2149, D2150, D2148) and
**`src/agentic_postgres/slot.py`** (`SLOT_KEY`, `STATES`, `slot_manifest`,
`Readings`, pure `state()`, file-only `read()`): `prepare` (the manifest built,
loaded by the product, renamed into place; D2206), `status [--json]` (exit 6 on
any `undetermined`; DNS by `dig @1.1.1.1`, D2208), `revoke` (the kept state put
back where `bootstrap-providers` reads it, D2207). `test_cli_contract` lists
both commands and `slot.sh`'s verbs. **Tests**: `test_project_runtime_stop_start.py`
(4: the script run for real from a copy whose `bin/` holds recorders, its two
host roots moved by count-asserted replacements), `test_project_retire.py` (+2,
a slot's deployed document built in memory from `slot_manifest`; the five
existing `steps`/`record` calls pass `retired_state=None`), `test_slot_command.py`
(6: prepare, the derived states, the unreadable DNS, the tombstone with an AST
scan of `bin/` and `src/`, revoke, and one vocabulary across `slot.py`, the host
schema and the control set's CHECKs). Every new test passed on its first run --
so the battery is the evidence they bite. **Targeted** (18 modules, once): 1,356
passed, 2 skipped. **Battery 5/5 killed**, each control PASSED, the tree
unchanged after: M1 `start` materializes → `test_start_waits_then_attaches_and_materializes_nothing`
FAILED; M2 `stop` runs `down` → `test_stop_detaches_first_then_stops_and_keeps_the_containers`
FAILED; M3 `--defer-provider` deleting the state → `test_defer_provider_keeps_the_state_for_revocation`
FAILED; M4 `prepare` removing the tombstone → `test_nothing_removes_a_tombstone`
FAILED; M5 an unreadable DNS reading folded into `ready` →
`test_an_unreadable_dns_reading_is_undetermined_never_ready` FAILED. Rows
**D2205–D2208**. NEXT FREE D2209. CI: recorded in Run 6's commit.

### Run 6 — the reconciler, part one: the loop, the claim, the crash rule, `project.create`

**Code.** CI read by full SHA.

1. **`bin/reconciler.py` + `bin/reconciler.sh run|once|status|install`**
   (D2151, D2152, D2153, D2168, D2178, D2179); `systemd/agentic-postgres-reconciler.service`;
   `src/agentic_postgres/control_registry.py` (`find_control`, moved; `bin/control.py`
   imports it — its tests unchanged); `src/agentic_postgres/reconciler_dispatch.py`
   (the closed table, the argv builders, `RESULT_MEMBERS` read from the service
   module through `service_source`).
2. **`project.create`** (D2173): steps `allocate` (a `ready` slot from
   `slot.state()`, its manifest re-written with the requested profile and the
   display name in nothing but `control_projects`) → `admit` (`admit.sh --host
   <checkout host.yaml> --project <slot manifest> --json`; 12 →
   `capacity_exhausted {reason: admission}`, the slot back to `ready`, D2160) →
   `deploy-1` → `admin` (D2163; `auth-admin.sh … bootstrap --username U
   --password-fd N`; the user's id read with `auth-admin.sh list --json` or a
   `psql` read through `container_exec`; then the reset row) → `ports`
   (`--render-runtime-only`, the instance uuid read the way
   `deploy-project.py:2064-2100` reads it, `database-ports.sh verify` argv built
   — never the printed line) → `deploy-2` → `unit` (`systemctl enable`) →
   `backup` (full, then `schedule enable`, then `mirror`) → `registry` (the
   refresh, D2167) → `succeeded`. Every `deploy.sh` call: `--host host.yaml
   --project <slot manifest> --capabilities capabilities.yaml --through-session
   38`, stdin `/dev/null`, stdout/stderr to `/var/log/agentic-postgres/reconciler/<op>-<step>.log`
   (0600; a log line names steps and exit codes, never an argument value but
   the key and the profile).

**Tests** (`test_reconciler_claim.py` Python half, `test_reconciler_dispatch.py`):
the recorder pattern (`container_exec.run` and `subprocess.run` replaced by
recorders that answer from a script — D2115) for every step's argv and its
failure path; the crash rule against `control_cluster` with a dispatch that
raises mid-step; `test_admin_handoff.py` on rig 38c's project cluster.
**Battery**: M1 resume instead of fail on an interrupted create → FAILED; M2 the
admission step after `deploy-1` → `test_admission_refusal_is_capacity_exhausted_and_creates_nothing`
FAILED; M3 the bootstrap password written to the log → `test_the_bootstrap_password_is_never_stored`
FAILED; M4 `SUDO_UID` omitted → FAILED; M5 the printed `verify` line executed →
`test_every_argv_is_built_from_validated_members` FAILED; M6 a dirty checkout
not refused → FAILED. **Targeted**: the reconciler modules, `test_control_command`,
`test_cli_contract`, `test_operator_commands_run_on_the_host`,
`test_container_exec`, `test_repository_contract`, `test_acceptance_registry`.

**Done.** 2026-10-08 (scripts and notes in WSL `~/s38/run6/`). **Run 5's CI:
run 37759782793 (`contract`) completed `success` on `4b64e38`.**
**`src/agentic_postgres/control_registry.py`** (D2168): `find_control`,
`read_one`/`read_all` (the root a parameter), `enables_control`, `target`,
`document_fields`, `OperatorError`, moved out of `bin/control.py`, which imports
them and keeps its own `STATE_ROOT` -- `test_control_command.py`'s six proofs
unchanged and green; `registry` gains the deleted outcome (D2167, D2215).
**`src/agentic_postgres/reconciler_dispatch.py`** (D2154): the closed table
(`STEPS`, `project.create`'s nine steps with their progress 10/10/30/40/60/60/70/90/90,
100 at the finish), `COMMANDS`, `invalid()` against the schema file (a reason that
never echoes a value), `result()` refusing an undeclared member, the argv builders
(admit, deploy, `--render-runtime-only`, bootstrap, verify, `systemctl enable`,
backup ×3), the SQL, and `psql_input` (D2213). **`bin/reconciler.py` +
`bin/reconciler.sh run|once|status|install`** and
**`systemd/agentic-postgres-reconciler.service`** (D2151, D2152, D2153, D2178,
D2179, D2209, D2214): recovery before the first claim (interrupted → `failed
interrupted {"step"}`, a creation's slot quarantined by the id its `allocated`
marker carries), the slot reading at start, after every operation and every 120 s
idle (D2212), one operation at a time under `/run/agentic-postgres/reconciler.lock`,
the checkout read at start and before every operation, `project.create`
(allocate → admit → deploy-1 → admin → ports → deploy-2 → unit → backup ×3 →
registry; D2173, D2210, D2211, D2216); children with stdin `/dev/null`,
`SUDO_UID`/`SUDO_GID` = the checkout's owner, output to
`/var/log/agentic-postgres/reconciler/<op>-<step>.log` (0600 in 0700); the
bootstrap password through an inherited pipe and nowhere else. `slot.dns_reading`
and `slot.observe` moved into the library (D2217). **Rig 38g** (D2209): git 2.47.3
as root on another uid's checkout → 128 without `SUDO_UID`, 0 with it, 128 with a
different uid. **Tests**: `test_reconciler_dispatch.py` (18, the recorder pattern:
every step's argv and failure path, the argv guard, the AST guard, the unit file,
`install`, `status`, two control projects → 5), `test_reconciler_claim.py` (+2
Python half on `control_cluster`: a creation killed in `deploy-1` and restarted --
`failed interrupted`, attempt 1, the slot quarantined and recorded so, nothing
run again; a quote/backslash/colon/newline round trip), `test_admin_handoff.py`
(1, rig 38c as a proof: the reconciler's `database_call` with `ADMIN_ID_SQL` and
`OPEN_HANDOFF_SQL` on the release set -- T → 200, the chosen password logs in; a
wrong T, the hash as the token, T twice and the bootstrap password after → 401
each), `test_control_command.py` (+1, D2215). `test_cli_contract` lists both
commands and `reconciler.sh`'s verbs. One test-side defect found on first run:
replacing `subprocess.run` on the module replaced it for `container_exec` too, so
the claim proof's recorder passes `docker` through. **Targeted** (19 modules,
once): 1,302 passed, 2 skipped (the tests own skips). **Battery 7/7 killed**, each control PASSED, the tree
unchanged after: M1 an interrupted creation resumed → `test_an_interrupted_creation_fails_and_quarantines_its_slot_never_resumed`
FAILED; M2 admission after `deploy-1` → `test_admission_refusal_is_capacity_exhausted_and_creates_nothing`
FAILED; M3 the bootstrap password written to the log → `test_the_bootstrap_password_is_never_stored`
FAILED; M4 `SUDO_UID` omitted → `test_children_act_for_the_checkout_owner_with_stdin_closed`
FAILED; M5 the printed `verify` line executed → `test_every_argv_is_built_from_validated_members`
FAILED; M6 a dirty checkout not refused → `test_a_moved_or_dirty_checkout_refuses_every_operation`
FAILED; M7 a deleted row agreeing without its tombstone → `test_a_deleted_project_agrees_only_with_its_tombstone`
FAILED. (M2's first control, `test_a_creation_runs_every_step_in_order`, reads the
order and so was reachable; the password proof is its control.) Rows
**D2209–D2217**. NEXT FREE D2218. CI: recorded in Run 7's commit.

### Run 7 — the reconciler, part two: sleep, wake, resize, export, delete

**Code.** CI read by full SHA.

1. Handlers: **sleep** / **wake** (D2155: schedule, unit, `stop`/`start`);
   **resize** (admit with the own key excluded → `capacity_exhausted
   {admission}` with nothing rendered; else re-write the manifest's `compute`,
   one deploy, the registry refresh); **export** (D2164; the storage container
   found by its Compose labels as `auth-admin.py:230-266` finds `auth`); **delete**
   (D2158: `project-retire.sh --host host.yaml --project KEY --confirm KEY
   --record /etc/agentic-postgres/slots/<key>/retirement.json --permanent
   --destroy-data --defer-provider`, then the tombstone, `control_mark_deleted`,
   `control_record_slots`).
2. **`services/auth-api/app/export_upload.py`** (storage mode only; reads the
   storage settings the storage lifespan reads; stdin → `put_object` under
   `exports/`; prints one presigned GET with `ExpiresIn=900`); the transport
   allowlist (ADR 0124) is NOT widened — it uses the adapter's existing client.
   `R2Adapter.presign_get` takes `expires_in` if rig 38e found it does not.

**Tests**: the dispatch tests for each (§2), `test_export_upload.py` with the
Stubber. **Battery**: M1 `-n app_private` added → `test_the_export_names_only_the_customer_schemas`
FAILED; M2 the archive kept → FAILED; M3 `ExpiresIn=3600` → FAILED; M4 delete
without the tombstone → `test_delete_consumes_the_slot` FAILED; M5 sleep without
disabling the timers → FAILED; M6 resize rendering before admission → FAILED.
**Targeted**: as Run 6 plus `test_storage_*` (grep) and `test_auth_service_shape`.

**Done.** 2026-10-08 (scripts and notes in WSL `~/s38/run7/`). **Run 6's CI:
run 37765394786 (`contract`) completed `success` on `6f59524`.** **The closed
table is whole**: `reconciler_dispatch.STEPS` and `bin/reconciler.py`'s
`HANDLERS` equal `EXECUTED_TYPES` (a test). **sleep** (D2155): `backup.sh …
schedule disable` → `systemctl disable agentic-postgres-project@KEY` (not
`--now`) → `project-runtime.sh … --through-session <the document's
deployed_through_session> stop`; **wake**: `start` → `systemctl enable` →
`schedule enable`. **resize** (D2220): a candidate manifest admitted, renamed
into place only when admitted, one deploy, the registry refreshed (empty name
and slot passed as NULL). **export** (D2164, D2221): `pg_dump -U postgres -Fc
-n app -n api --no-owner --no-privileges` through `container_exec.run` into
`/var/lib/agentic-postgres/exports/<op>.dump` (0600, exclusive), the storage
container found by its Compose labels (`docker ps --filter
label=apg.project.key=KEY --filter label=com.docker.compose.service=storage`),
the archive streamed to `python -m app.export_upload --operation <op>`, the one
URL finished into `result_secret` (`FINISH_SQL` gains `nullif(:'secret', '')`)
with `sha256`, `size_bytes`, `expires_at` in the result, the archive removed in
every case. **delete** (D2158): `project-retire.sh --host host.yaml --project
KEY --confirm KEY --record /etc/agentic-postgres/slots/KEY/retirement.json
--permanent --destroy-data --defer-provider` → the `consumed` tombstone (0600,
the operation's id) → `control_mark_deleted`; the slot reading after it reads
`consumed`. Every handler but create acts only on a declared slot (D2218);
export and resize refuse a sleeping project (D2219). **`services/auth-api/app/export_upload.py`**
(storage mode only) and the adapter's **`put_object`** (first-write-only) and
**`presign_get(…, expires_in)`** (1–900 s, D2190); `BoundedR2` unchanged. Botocore
in the image is the venv's (1.43.72), so the Stubber's parameter check is the
image's. **Tests**: `test_reconciler_dispatch.py` (+8, 26: sleep, wake, resize
refused and admitted, the dump's argv, the URL as secret and the archive removed
-- a failed upload too --, a sleeping project, delete, operator-managed refused;
Run 6's `test_an_unexecuted_type_runs_nothing` replaced by
`test_the_closed_table_is_the_executed_types`), `test_export_upload.py` (5,
Stubber: one first-write-only PUT of the archive, one line signed 900 s, the
expiry bound, the 412, the mode/empty/id refusals, the two constants equal).
**Targeted** (30 modules, once): 1,538 passed, 1 failed, 2 skipped (the tests own skips) -- the failure ADR 0186's guard
refusing `bin/reconciler.py` naming the retirement verb (D2222: ADR 0256 amended,
the guard widened by exactly that file with three assertions keeping the
exception honest); after the fix `test_project_retire.py` alone 18 passed, and
`test_documentation_index` + `test_acceptance_registry` 71 passed. **Battery 8/8
killed** (M8, below, run after the fix), each
control PASSED, the tree unchanged after: M1 `-n app_private` added →
`test_the_export_names_only_the_customer_schemas` FAILED; M2 the archive kept →
`test_the_export_url_is_the_operations_secret_and_the_archive_is_removed` FAILED;
M3 the URL signed 3600 s past the adapter → `test_the_export_is_written_once_and_signed_for_900_seconds`
FAILED; M4 delete without the tombstone → `test_delete_consumes_the_slot` FAILED;
M5 sleep without disabling the timers → `test_sleep_disables_the_timers_and_the_unit_then_stops`
FAILED; M6 resize deploying before admission → `test_resize_admits_a_candidate_before_anything_changes`
FAILED; M7 an operator-managed project not refused → `test_an_operator_managed_project_is_refused`
FAILED; M8 the reconciler reading a project's `expires_at` →
`test_no_unit_timer_or_command_names_the_retirement_verb` FAILED. Rows
**D2218–D2222**. NEXT FREE D2223. CI: recorded in Run 8's commit.

### Run 8 — the CLI: `project.sh` verbs, `compute.sh`, `operation.sh`

**Code.** CI read by full SHA. D2169 and D2163's client half, in
`src/agentic_postgres/control_client.py` / `bin/cloud.py`, every Session 37
state rule kept (0700/0600, `O_NOFOLLOW`, https except loopback, no redirect,
one refresh per command). `claim` presents `T` to `{routes.app}/auth/reset-password`
— **the project's address is read from `GET /v1/projects/{key}`**, which
returns `routes.app` from the registry row (the reconciler copies it from the
deployed document; `control_projects` gains `app_route text` in `0004` — add it
in Run 4 if this run finds it missing, and record the row).

**Tests**: `test_control_cli.py` gains the verbs as subprocesses against
`control_cluster.served_app` (Session 37's harness), including
`test_the_handoff_token_is_private_and_removed_after_claim`. **Battery**: M1 the
handoff file 0644 → FAILED; M2 `T` sent to `/v1` → `test_only_the_hash_reaches_the_control_plane`
FAILED; M3 `export` following a redirect → FAILED; M4 `operation.sh wait`
reading a 5xx as succeeded → FAILED. **Targeted**: `test_control_cli`,
`test_cli_contract`, `test_completion_command`, `test_operator_commands_run_on_the_host`.

**Done.** *(the executor writes it)*

### Run 9 — the trip's instruments, written and rehearsed offline

**No product code.** Commit only the `**Done.**`. Scripts in WSL `~/s38/run9/`
and the scratchpad; host copies in `/home/op` with sha256 printed. **Derived by
diff from Session 37's** (`~/s37/run8`, `~/s37/run10`, `~/s37/run11`) where one
exists: `s38-units.sh` (five units: edge, three projects, the reconciler),
`s38-free.sh` (the 1,024 floor), `s38-probe-start.sh`/`-stop.sh` (alpha, beta,
control and — once it exists — `slot1-prod`), `s38-sweep.sh` (+ the two
flags), `s38-launch.sh`, `s38-external.sh` (+ `--lifecycle-record-file`),
`s38-after-reboot.sh` (+ the reconciler unit, D2176), `s38-v1.sh`. New:
**`s38-hostyaml.py`** (writes the schema-4 candidate from the checkout's copy +
the region and the slot — backup first, the product's loader run on the result,
the diff printed); **`s38-lifecycle.py`** (D2175: the probe owner's session from
`~/s37/probe.json`, codes computed from its seed, each step sent only after the
previous one's terminal status was read; pauses for Sheet K2 before the delete;
writes `~/s38/lifecycle.json` 0600 — never a password, key, token or URL); 
**`s38-dns.sh`** (from `s37-dns.sh`, the slot's name). **Rehearsals**: every
script against the fixtures and `control_cluster.served_app` on the workstation
with a fake reconciler finishing operations by hand through the superuser
functions (the lifecycle instrument end to end in ~2 minutes), and against a
copy of `host.example.yaml`.

**Done.** *(the executor writes it)*

### Run 10 — the bump, the registry, the gate, the threat rows, the Ledger to `trial`, the documents

**Code.** CI read by full SHA. `CURRENT_SESSION = 38`, `VERSION 1.16.0`, the
Session 38 paragraph in `__init__.py`; the registry block (§2, node ids from
`--collect-only`); `CLAIMS`, `OFFLINE_CLAIMS`, `CLAIM_INTRODUCED_IN`; the
regex; `bin/session-38-check.sh` derived by diff (two flags; usage whole);
`tests/contract/test_session_thirty_eight_gate_modes.py` derived from 37's
(`SESSION = 38`, `SESSION_PREVIOUS_NUMBER = 37`); the conftest roster's two
variables; the live modules `tests/deployment/test_session38_reconciler.py` and
`tests/external/test_session38_public_lifecycle.py` (each `pytestmark` first;
D2174's scan extended); the threat table's six rows (§5 Run 1); **the Ledger**:
`projects_self_service`, `project_deletion`, `export`, `region`,
`compute_profiles`, `sleep` → **`trial`** with their claims as `evidence`,
`controls` naming the operation types and CLI verbs, `customer_text` containing
*"being verified"*; `operations.ACCEPTED_TYPES` = the six types' five-plus-one
(`project.create`, `.delete`, `.sleep`, `.wake`, `.resize`, `.export`);
`bin/render-reality-ledger.py --write`. **`upgrade plan` offline** (a worktree at
`c3eec1d` against this tree, Session 37 Run 9's method) with D2186's two
declarations → expected `bump minor`, `requires minor`; the leaves listed.
**Documents**: `docs/managed-projects.md` (new: the customer's lifecycle, the
states, the refusals, what sleeping means for backups, the handoff, the export's
900 s, what deletion keeps), `docs/operator-guide.md` (the slot provisioning
sheet's form, the reconciler's start/stop rule D2178, `slot.sh revoke`, the TOTP
QR route D2177), `docs/control-plane.md` (the new routes), the upgrade guide's
`1.16.0` row, `README.md:7`. Every `--session 37` / `--through-session 37` on
the documented path moved and counted per file. **Gates on the commit**:
`bin/session-38-check.sh --mode offline` and `bin/session-01-check.sh`, once each,
on the clean tree (the operator's terminal if the harness reaps them — Session
35's precedent), then CI by full SHA. **`pytest --setup-plan`** for both live
modules with the variables set (D671).

**Done.** *(the executor writes it)*

### Run 11 — sitting 1 (day 1): the release, the host's schema, the reconciler, the slot prepared

**Before the day**: CI green on Run 10's commit by full SHA; Sheet P1 done by the
operator (any day before) and the Infisical plan upgraded (D2146).

**In order** (agent steps over SSH as `op`; the operator's are the sheets):

1. Ship (`git bundle create /tmp/apg-<sha>.bundle c3eec1d..main`, `scp`, `git
   fetch`, `git checkout --detach FETCH_HEAD`, `git rev-parse HEAD` == Run 10's
   SHA, `uv sync`, `git status --short` empty).
2. **`s38-hostyaml.py`** writes the schema-4 candidate for the checkout copy and,
   after Sheet H1's first line hands the agent an op-readable copy of `/etc`'s,
   for that copy; both diffs read.
3. **Sheet H1** — host.yaml schema 4, both copies.
4. Renders as `op`: alpha, beta, control (`/home/op/control.yaml` stays at
   schema 9 — a supported version; no operator manifest is edited), the two
   fixtures — rc 0 each.
5. **Sheet R1** — `upgrade plan` × 3 with D2186's declarations; `major` → stop.
6. Probe started (alpha, beta, control).
7. **Sheets R2a / R2b / R2c** — alpha, beta, control-prod at `--through-session
   38`. Probe stopped; windows read. **R2c is D2172's measurement**: control's
   `/api/rest/` → Traefik's 404 (curl from the workstation), its document
   `routes.rest unavailable`, the deploy's transcript has no 90 s wait.
8. **Sheet A1** — `control.sh adopt` × 3 into the operator's organisation (D2141:
   after the LAST deploy), `registry` → agrees × 3.
9. **Sheet RC1** — `sudo bin/reconciler.sh install`; `status` → *idle*;
   `journalctl -u agentic-postgres-reconciler -n 20` read (it found the control
   project, recorded the slots — none prepared yet).
10. **Sheets SL1 / SL2 / SL3** — the slot: `prepare`, `bootstrap-providers
    --plan`/`--apply` (the credential placed and shredded), the pastes,
    `materialize-secrets`, `s38-dns.sh` exit 0, `slot.sh status` → `slot1-prod
    ready`. The reconciler's next pass writes `control_slots`; Sheet V1's
    script reads the row as the superuser.
11. **Sheet K1** — the DR kit (three projects; the slot is not a project yet)
    and the op copies.
12. **Sheet V1** — `-k "(session38 and not lifecycle and not slot) or
    session37 or session4_transports"` (the lifecycle proofs need the record,
    D2138's shape); writes nothing.

**Done.** *(the executor writes it)*

### Run 12 — sitting 2 (day 2): the lifecycle, the reboot, the sweep, the tag

1. **The lifecycle** (the agent, from WSL, `s38-lifecycle.py`, the probe owner's
   session; the probe running on alpha, beta, control and — after creation —
   the slot): create `small` → wait (≤ 40 min) → `claim` → the slot's
   `/auth/me` with the new password → **`s38-free.sh` (FITS ≥ 1,024 or STOP,
   D2145)** → sleep → 60 s of samples (expected 404) → wake → time to 200 →
   resize `standard` → wait (windows) → resize `large` → `failed
   capacity_exhausted/admission`, profile still `standard` → export → download
   once (a second `GET /v1/operations/{id}` has no URL) → sha256 + `pg_restore
   --list` → **900 s later the URL refused 403** (the expiry control, D2164) →
   pause.
2. **Sheet K2** — the slot's deployed document copied op-readable
   (`/home/op/slot1-prod-outputs.json`); the agent copies it to WSL.
3. The lifecycle continues: delete → wait → the slot's routes 404 → second create
   → `409 capacity_exhausted {reason: no_slot}`, no row (read
   `GET /v1/operations?organization=`).
4. **Sheet A1'** — `control.sh registry` → agrees × 3 + `agrees (deleted)`.
5. **Sheet B1** — the reboot; `s38-after-reboot.sh` (five units, each left
   `inactive` before `multi-user.target`).
6. **Sheet S1** — the op copies, the sweep launched (`--lifecycle-record-file`,
   `--slot-outputs`, every Session 37 declaration).
7. External (`s38-external.sh`), the merge (`bin/write-session-evidence.py` over
   CI's offline artifact for the deployed SHA, the host and external halves) →
   **exit 5 for `documented_path` and `replacement_host_restore` only** (§7).
8. **The tag from the workstation** (`git tag -a 1.16.0 <sha> -F <file>`, push,
   `ls-remote`).
9. **Sheet SL4** — `slot.sh revoke --slot slot1-prod` (the credential placed and
   shredded); the operator reads the slot's backup bucket listing at the R2
   console and states it is non-empty (D2185).

**Done.** *(the executor writes it)*

### Run 13 — the close

**Code** — `bin/session-01-check.sh` once and CI.

- **The Ledger** (D2170): each `trial` row → `beta` if every named claim reads
  `passed` in `evidence/session-38.json`, else → `planned` with its types
  removed from `ACCEPTED_TYPES` and the Done saying why; `customer_text`
  without *"being verified"* for a `beta` row; `--write`.
- **`capacity.ENVELOPE`**: D2171's rows by `~/s38/run13/s38-envelope.py`
  (Session 37's `s37-envelope.py` the model), each naming the CX23.
- **`compute_profiles.RESIZE_WINDOW_SECONDS`** set from the resize row (D2157)
  with its test.
- `docs/scope-closure.md` **§31**; the stage plan's Status block; CLAUDE.md §2
  rewritten for Session 39's planner (copy it to the scratchpad first); this
  plan's `Status:` COMPLETE with the rows each run added.

**Done.** *(the executor writes it)*

---

## 7. Evidence and claims

**Expected at the merge** (Run 12): **237 claims. Passed: everything that passed
at Session 37** — `port_allocation` (declared after B1), the rotation trio (the
four files re-declared, D2187), the thirteen Session 37 claims (the probe
organisation still exists; KEY-USE-001's list now includes the deleted slot's
row only if `/v1/projects` lists deleted rows — **Run 4 decides that it does
not by default**, so the 37 proof is unchanged) — **plus the eighteen new ones.
`failed` 1: `documented_path`** (D1935). **`not_run` 1:
`replacement_host_restore`** (D1028). Predictions, each moved only by the
evidence. Exit 5 for those two and no other reason.

**The three modes.** Offline: CI's artifact for the deployed SHA (89 claims).
Host: S1 with `--lifecycle-record-file` and `--slot-outputs`. External: from WSL,
with `--control-outputs`, `--control-probe-file` and `--lifecycle-record-file` —
the customer proofs reach only `routes.control` and the slot's recorded
`routes.app` (D2174). Deploy every project fully, THEN run the lifecycle, THEN
sweep: the lifecycle's operations are named in the record by commit (the
deployed SHA read from control-prod's document), and a record naming another
commit is refused by the proofs.

---

## 8. Security invariants this session touches

| Invariant | How this session keeps it |
|---|---|
| **The control plane holds nothing that opens a project's data or admin plane** | The handoff by hash (D2163, LIFE-HANDOFF-001); the reconciler is not the control plane and the control plane reaches no project; **the export URL is the one bounded exception** (≤ 900 s, one object, read once and erased, ADR 0259) |
| **The reconciler runs only a closed set of typed operations** | The type table, the arguments schema twice, argv lists only, the AST guard, no listener (OPN-DISPATCH-001, OPN-LIVE-001) |
| **The reconciler holds no provider-administering credential** | `--defer-provider`; `slot.sh revoke` is the operator's (D2158) |
| **A capacity refusal and an entitlement refusal are different codes from different readers** | `capacity_exhausted` from admission and the slot stock; no `plan_limit_reached` anywhere (LIFE-CAP-001) |
| **A slot is never reused** | The tombstone; no command removes it; `consumed` and `quarantined` never `ready` (LIFE-SLOT-001) |
| **A project's identities are derived once, in `naming`** | Slot keys are ordinary keys; the customer's name is a display name (D2180) |
| **A credential shown to a customer is shown once and stored hashed** | `T` never stored but on the customer's disk; the bootstrap password never stored; the download URL erased on first read |
| **No URL, key, token or caller value in a log line** | The reconciler's logs name steps and exit codes; `T`, the bootstrap password and the URL are asserted absent (LIFE-HANDOFF-001, LIFE-EXPORT-001) |
| **Nothing `planned` has a control** | `trial` bounded to this session and resolved at the close (D2170) |
| **Projects share no project-scoped value** | The slot's document compared with A, B and the control project (OPN-LIVE-001); the offline leaf classifier (D2162) |
| **A report may not substitute an answer for a failure to determine one** | `unknown` state; `slot.sh status` exit 6; `could_not_determine` as an operation code; `operation.sh wait` exit 6 |
| **A deploy over a broken archiver fails** | Unchanged; a sleeping project's archiver is stopped by design and the Ledger says so (D2182) |
| **There is no public Postgres endpoint** | Still true: a slot's transports are the SSH forward's like every project's (Session 39 opens the endpoint) |

---

## 9. Stop conditions

Stop and ask the operator, without improvising, when:

- `s38-free.sh` reads available < 1,024 MiB after the slot's creation, or
  admission refuses the slot at `small` (D2145);
- SL1's `--apply` fails on the machine identity, or on anything after creating
  the Infisical project (D2146, D1046);
- the slot's certificate is not issued on the creation's first deploy, or
  `s38-dns.sh` is not exit 0 before it;
- the reconciler would need a provider-administering credential, a listener, a
  shell string, or an argument value in an argv beyond D2154's two;
- the handoff would need `T`, a password or a project token in the control
  database, or the export would need a URL living longer than 900 s or listed;
- a slot would be reused, a tombstone removed, or an operation would reach a
  backup repository;
- a capacity refusal would need an entitlement code, or the reverse;
- a creation needs a human act the reconciler cannot perform (D2173's live half);
- `upgrade plan` prices 1.16.0 at `major`, or for a reason this plan did not name;
- a `trial` row would outlive the close, or a row would move to `beta` without
  its claims `passed`;
- the sweep would run while `reconciler.sh status` reads *working*, without
  `--after-reboot` after B1, or after a code commit past the deployed one;
- a currently-passing test would be weakened to make a new one pass;
- `--render-only` stops working with no host and no root.

---

## 10. Open items this session carries and creates

**Carried, untouched, each still true:** the rescale or move (D2032/D2145) —
**owed before Session 41**; beta's three rotations (D1995); D1936/D2005; D1547;
D2020/D2025 (two `host.yaml` copies — schema 4 moved both by hand, the class
remains); D2031; D1642, D1798, D1869, D1871, D1722/D1806, D1784, D1792, ADR
0241's bound; D1045; D1375; D976; D688; D771; D340; D466; D540; D942; D1203;
D1205; D1211; the 24 unclaimed requirements; `process-max` 1 (D593) — **now a
customer's export and restore time**; `documented_path` (D1935);
`replacement_host_restore` (D1028); accounts never deleted (D2065, D1986); TOTP
seeds plaintext (ADR 0252); `/v1/sessions` unthrottled (D2166).

**Created, and named so Session 39 does not inherit them silently:**

- **Slots are a stock of one on this host**; a second needs the rescale or a
  move (D2145). `quarantined` has no command that clears it — an interrupted
  creation is the operator's to retire with `project-retire.sh` by hand and
  then mark consumed (§ the operator guide's sentence, Run 10).
- **The reconciler and the operator are serialised by a rule, not a lock**
  (D2178): a host-wide deploy lock is owed.
- **The slot's Infisical project, buckets, DNS record and repository outlive
  it** (ADR 0187, D2181): no deletion policy window exists.
- **The export URL crosses the control database** (≤ 900 s, ADR 0259); a
  download through the project's own storage API as its admin is Session 40's
  question.
- **`storage.enabled: false` still emits storage's router** (D2144's second
  half).
- **A sleeping project's doctor and backups are unread** (D2182); a reboot
  while asleep keeps it asleep, unproved.
- **`materialize-secrets` has no last-known-good fallback** despite the unit's
  comment (§0) — wake avoids it; a boot does not.
- **The resize window ships unmeasured in 1.16.0** and measured from 39's
  release (D2157).
- **A sweep that destroys the state a later proof reads** (D2140, D2176) — the
  instrument stands.
- **Idle sleep** — Session 41 (D2147).

---

## Appendix — what to consult, how a run is executed here, and the sheets

**Consult, in this order:** CLAUDE.md §1 (the shell traps); this plan's §0, §1 and
the run's own text; the reads its run names. **The tree wins.**

**How a run is executed here**: CLAUDE.md §5. Every `sudo` line is the
operator's, on a sheet, under `script -q -e -c '…' /home/op/s38-<sheet>.txt`
when it execs into a container or deploys (D972, D1501), never piped or
redirected; `sudo -v` in the foreground first (D1376). Every `op` line is the
agent's over SSH; remote loops in a script file with `PATH="$HOME/.local/bin:$PATH"`
exported. **`<sha>` is never typed on a sheet**: the agent fills it from `git
rev-parse HEAD` on the host before handing the sheet. **Before any sheet that
deploys, retires or restores: `sudo systemctl stop agentic-postgres-reconciler`
once the reconciler exists, and `start` after** (D2178).

### Sheet E0 — readings before anything is built (Run 1; reads only)

```
sudo -v
sudo bash /home/op/s38-e0.sh      # tees /home/op/s38-e0.txt; changes nothing
#   YOU: say whether the Infisical plan is upgraded yet (D2146).
```

### Sheet P1 — the consoles (any day before Run 11)

1. **Infisical**: upgrade the plan so a fifth machine identity can be created
   (D2146).
2. **Cloudflare DNS**: `A slot1.agenticpostgresql.com → 62.238.99.122`, **DNS
   only**, no AAAA (D2148).
3. **Cloudflare R2**: buckets `apg-slot1-prod` and `apg-slot1-prod-backup`, in
   alpha's location; two Account API tokens, *Object Read & Write*, one scoped to
   each bucket. Keep the four values for SL1's paste. **Never paste them into the
   conversation.**
4. **Backblaze B2**: the mirror bucket (`apg-slot1-prod-backup-mirror`, or tell
   the agent the name you used — D2124) and an application key scoped to it.
5. Tell the agent 1–4 are done and the mirror bucket's name.

### Sheet H1 — host.yaml schema 4 (Run 11, day 1)

```
sudo install -o op -g op -m 0600 /etc/agentic-postgres/host.yaml /home/op/etc-host.yaml
#   the agent runs s38-hostyaml.py on both copies and prints the two diffs; read them, then:
sudo install -o root -g root -m 0600 /home/op/etc-host.yaml.schema4 /etc/agentic-postgres/host.yaml
#   (E0 read the /etc copy root:root 0600 at schema 2; the candidate is the CHECKOUT's schema-3
#    copy moved to 4, so both paths hold one byte-identical document after this line -- D2194)
```

### Sheet R1 — the release priced (Run 11, day 1)

```
sudo bin/upgrade.sh plan --project alpha-dev    --candidate .generated/alpha-dev/outputs.json    --also document_schema_migratable --also api_operation_added --json
sudo bin/upgrade.sh plan --project beta-dev     --candidate .generated/beta-dev/outputs.json     --also document_schema_migratable --also api_operation_added --json
sudo bin/upgrade.sh plan --project control-prod --candidate .generated/control-prod/outputs.json --also document_schema_migratable --also api_operation_added --json
```

(Read `bin/upgrade.sh --help` before handing this sheet and correct the lines
to it — Session 37's R1 used `check` then `plan`.)

### Sheets R2a / R2b / R2c — 1.16.0 deployed (Run 11, day 1)

```
script -q -e -c 'sudo ./deploy.sh --host host.yaml --project project.alpha.yaml   --capabilities capabilities.yaml --through-session 38' /home/op/s38-r2-alpha.txt
script -q -e -c 'sudo ./deploy.sh --host host.yaml --project project.beta.yaml    --capabilities capabilities.yaml --through-session 38' /home/op/s38-r2-beta.txt
script -q -e -c 'sudo ./deploy.sh --host host.yaml --project /home/op/control.yaml --capabilities capabilities.yaml --through-session 38' /home/op/s38-r2-control.txt
```

### Sheet A1 — the registry after the last deploy (Run 11, day 1)

```
sudo bin/control.sh adopt --project alpha-dev    --organization 10234b92-b2d7-4573-bebb-f012ce5c8f02 --confirm control-prod
sudo bin/control.sh adopt --project beta-dev     --organization 10234b92-b2d7-4573-bebb-f012ce5c8f02 --confirm control-prod
sudo bin/control.sh adopt --project control-prod --organization 10234b92-b2d7-4573-bebb-f012ce5c8f02 --confirm control-prod
sudo bin/control.sh registry                     # agrees x3, exit 0
```

### Sheet RC1 — the reconciler (Run 11, day 1)

```
sudo bin/reconciler.sh install
sudo bin/reconciler.sh status                    # idle
systemctl is-enabled agentic-postgres-reconciler # enabled
```

### Sheet SL1 — the slot's providers (Run 11, day 1)

```
sudo bin/slot.sh prepare --host host.yaml --slot slot1-prod
bin/bootstrap-providers.sh --host host.yaml --project /etc/agentic-postgres/slots/slot1-prod/manifest.yaml --plan
#   (if --plan cannot read the root-only manifest as op, run it with sudo -- the agent reads --help first)
#   YOU: place the control-plane credential (two lines: client id, client secret):
sudo install -d -m 0700 /root/.config/agentic-postgres/bootstrap
sudo nano /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo chmod 0600 /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo bin/bootstrap-providers.sh --host host.yaml --project /etc/agentic-postgres/slots/slot1-prod/manifest.yaml --apply \
     --operator-credential-file /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo shred -u /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo ls -la /root/.config/agentic-postgres/bootstrap/      # empty, no nano .save copy (D2061)
#   YOU: in Infisical, project `slot1-prod`, environment `dev` (host.yaml's environment_slug, D2040):
#   the storage pair at /storage (create the folder), the backup pair at /backup,
#   the mirror pair at /backup -- each into the EXISTING key if --apply made it, else a new key.
```

### Sheet SL2 — materialized (Run 11, day 1)

```
sudo bin/materialize-secrets.sh --project /etc/agentic-postgres/slots/slot1-prod/manifest.yaml --requirements secrets.required.yaml --session 38
```

### Sheet SL3 — the slot read (Run 11, day 1)

```
#   the agent has run s38-dns.sh: exit 0
sudo bin/slot.sh status                          # slot1-prod ready
```

### Sheet K1 — the kit and the copies (Run 11, day 1)

```
sudo bin/dr-kit.sh export --host host.yaml --capabilities capabilities.yaml \
     --project project.alpha.yaml --project project.beta.yaml --project /home/op/control.yaml \
     --output /home/op/kit-<today>-s38
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/alpha-dev/outputs.json    /home/op/alpha-dev-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/beta-dev/outputs.json     /home/op/beta-dev-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/control-prod/outputs.json /home/op/control-prod-outputs.json
```

### Sheet V1 — the day verified, writing nothing (Run 11, day 1)

```
sudo bash /home/op/s38-v1.sh       # the sweep's declarations without --after-reboot and the lifecycle flags; -k as Run 11 step 12
```

### Sheet K2 — the slot's document, before its deletion (Run 12, day 2)

```
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/slot1-prod/outputs.json /home/op/slot1-prod-outputs.json
```

### Sheet A1' — the registry after the lifecycle (Run 12, day 2)

```
sudo bin/control.sh registry                     # agrees x3, slot1-prod agrees (deleted); exit 0
```

### Sheet B1 — the reboot (Run 12, day 2)

```
sudo systemctl reboot
```

### Sheet S1 — the one sweep (Run 12, day 2)

```
sudo -v
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/alpha-dev/outputs.json    /home/op/alpha-dev-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/beta-dev/outputs.json     /home/op/beta-dev-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/control-prod/outputs.json /home/op/control-prod-outputs.json
sudo bash /home/op/s38-launch.sh      # refuses while the reconciler is working; detaches s38-sweep.sh
```

### Sheet SL4 — the slot's identity revoked (Run 12, day 2, after the tag)

```
#   YOU: place the control-plane credential as on SL1, then:
sudo bin/slot.sh revoke --slot slot1-prod --operator-credential-file /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential --confirm slot1-prod
sudo shred -u /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo ls -la /root/.config/agentic-postgres/bootstrap/      # empty
#   YOU: open the R2 console, bucket apg-slot1-prod-backup: say whether it lists objects (D2185).
```
