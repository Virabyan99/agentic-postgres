# Session 37 — The control plane

**Status: PLANNED 2026-10-04 at `56879a1`. Not started.** The second session
of Stage 5 (`docs/plans/stage-5-plan.md` §3). Twelve runs and **two sittings
on two days** — the release deployed on alpha and beta and the control project
brought up beside them (day 1), then a person invited, an organisation, a key,
the projects adopted into the registry, a reboot and the one sweep (day 2). The
plan spends **D2042–D2072** and **ADR 0251–0254**; rows the runs add start at
**D2073**. **NEXT FREE after this plan: D2073, ADR 0255.**

**Brief:** `docs/plans/stage-5-plan.md` §5 *Session 37* whole (Builds / Already
true / Must not / Measures / Closes), its rows **D1950** (the control plane is a
project the product deploys; a fourth `APP_MODE`; ADR 0185 superseded for the
control plane by an authoritative `projects` table), **D1951** (invite-only;
organisation roles; TOTP for `owner` and `admin`; no email), **D1952** (`/api/v1`
frozen as a fifth contract; management API keys; the CLI as clients of
`/api/v1`), **D1953 (a)** (operations are rows; no executor yet), **D1978**
(the threat rows), **D1979** (the Reality Ledger's operation-type guard),
§7 (*"External mode becomes the customer's mode"*), §8–§9, §10 (*"The control
project is the platform's single point of failure"*), §11. Plus
`docs/scope-closure.md` **§29** (what Session 36 hands 37), Session 36's plan
`docs/plans/session-36-implementation-plan.md` (its §1 rows D2006–D2041, its
sheets, its §10), `docs/reality-ledger.yaml` (rows `accounts`, `organizations`,
`api_keys`, `management_api`, `cli_remote`, `email`, `passkeys`),
`docs/threat-model.md` §*Hosted threats, written before their controls*
(`:157-244`), ADRs **0246** and **0247**, and the operator's three answers of
2026-10-04 (§1 D2042, D2071).

**Shape:** twelve runs. **Run 1** is documentation — five rigs, one host
reading sheet (E0, reads only), the threat list made specific, four ADRs — and
reads **no** CI verdict. **Runs 2–7** change code: each pushes and reads that
commit's own CI verdict by full SHA (`gh api
"repos/Virabyan99/agentic-postgres/actions/runs?head_sha=<40 chars>" --jq
'.workflow_runs[] | [.name, .status, .conclusion] | @tsv'`, judged on HTTP
status, three buckets — success / failure / not registered; an empty list is
not a verdict, D1057). **Run 8** writes the trip's instruments and rehearses
them offline, committing nothing but its `**Done.**`. **Run 9** is the bump.
**Runs 10–11** are the sittings. **Run 12** is the close (the Ledger's rows and
the envelope's are code-adjacent: it gates once and reads CI).

**Product version at close:** `CURRENT_SESSION` **37**; `template_version`
**`1.15.0`** — predicted *minor* (a migratable manifest schema 9, outputs
schema 20 with one new route member, a fourth application mode, no released
migration) and **read from `upgrade plan` on the host, never chosen** (§1
D2070). **No released migration** (the count stays 39): every control-plane
table is the control project's OWN set under `projects/control/`. **One new
manifest field** (`control.enabled`, schema 9), **one new route** (`routes.control`,
outputs 20), **one new app mode** (`control`, run by the control project's
existing `auth` container — no new container, role, network, secret or
volume), **one new project on the host** (`control-prod`), **six new `bin/`
commands** (`control`, `login`, `logout`, `context`, `org`, `project`), **one
new contract** (`contracts/control-openapi.canonical.json`). A `major` is §9's
stop.

**Written for whoever picks this up cold, and it will be a different model
than the one that planned it.** Every path below was read from the tree on
2026-10-04 at `56879a1` — four explore passes over `services/auth-api/app/`,
`src/agentic_postgres/`, `bin/`, `schemas/`, `migrations/templates/`,
`projects/example/`, `tests/`, `docs/` and `systemd/`, plus direct reads of
`schemas/project.schema.json`, `src/agentic_postgres/rendering.py:425-470`,
`services/auth-api/app/claims.py:52-100`, `services/auth-api/app/scopes.py:55-150`,
`services/auth-api/app/service.py:450-500`, `migrations/templates/0012-auth-access-plane.sql:400-420`,
`bin/migrate.py:770-810` and `evidence/session-36.json`. Every path is cited by
`path:line`. Every third-party or product claim is measured in Run 1's rigs
with a control, or is marked as the measurement a run owes — never assumed.
**Read CLAUDE.md §1 in the launch folder before the first command, then this
plan's §1, then the appendix.** If a step here and the tree disagree, **the
tree wins and the disagreement is a divergence row** (next free `D` after §1's
table), never a silent reconciliation. **When this plan names a line number,
open the file at that line and read the surrounding twenty lines before
editing** — the numbers were right on 2026-10-04 and `ruff format` moves them.

**The seven sentences the executor most needs, in case nothing else is read:**

1. **The control plane is the `control-prod` project, and `/api/v1` is served
   by that project's own `auth` container running `APP_MODE=control`** (§1
   D2043). Nothing new runs beside it: same image, same role (`auth_service`),
   same pool, same signing key. In `control` mode the container serves the
   health routes, the probes the deploy and the doctor read (Run 1's 37e names
   them), and `/v1/*` — **and nothing else**: no `/auth/login`, no `/admin/*`,
   no workflow or connector route, no worker. `alpha-dev` and `beta-dev` keep
   `APP_MODE=auth` byte for byte.
2. **The control tables are the control project's own migration set**
   (`projects/control/migrations/`), linted like every set — nothing in
   `app_private`, FORCE RLS on every `app` table — **with one widening**: a set
   whose manifest enables the `control` facility may grant `EXECUTE` to
   `{{auth_service}}` (§1 D2046, ADR 0251), because accepting an invitation
   creates an identity-registry user (`app_private.auth_create_user`, granted to
   `auth_service` alone, `0012:409`) and a membership in ONE transaction, and
   only `auth_service` can do both.
3. **The control plane holds no credential that opens any project's data or
   admin plane** (ADR 0246's boundary sentence). It reads alpha's and beta's
   *deployed documents* only, through a root operator verb (`sudo bin/control.sh
   adopt|registry`), never their databases, routes or tokens. A management key
   presented to alpha is refused there, and a live proof says so (§2
   `KEY-USE-001`).
4. **No operation is accepted in this session** (§1 D2054). The `operations`
   table exists and `GET /v1/operations` reads it; **`POST /v1/projects`
   answers `409 not_available` naming the Ledger row `projects_self_service`**,
   because the Ledger's own guard (ADR 0247) forbids a control acting on a
   `planned` concept. The stage plan's *"a `project.create` operation recorded
   and listed"* is replaced by this refusal, measured live.
5. **Secrets are shown once and stored hashed — by SHA-256, not Argon2id, for
   anything with 256 bits of entropy** (§1 D2051, D2052): invitation tokens
   reuse `one_time_tokens` (`services/auth-api/app/one_time_tokens.py:31-63`);
   API keys are `apg_<16 hex id>_<43 url-safe>` with the secret's SHA-256 stored.
   Argon2id stays for passwords. **TOTP seeds are the one stored secret that
   must be readable** (HMAC needs the key); they live in the control set's
   `app.control_totp`, reachable only through definer functions granted to
   `auth_service`, and ADR 0252 states that residual risk.
6. **Ledger rows move to `beta` in the CLOSE run, not the building runs** (§1
   D2055): the guard requires an `available`/`beta` row's evidence to be
   `passed` in the newest evidence document, which for a live claim exists only
   after the merge. ADR 0247 is amended to say a row moves *in the run whose
   evidence makes it true*.
7. **Two sittings, and the sheets are one outcome each** (D1510). Day 1: the
   1.15.0 release on alpha and beta, then the control project's bring-up — the
   providers, three deploys (D326's first-pass shape), the first administrator,
   the unit enabled (§1 D2060 — no command enables it), a full backup and its
   schedule (§1 D2062), the DR kit with three projects. Day 2: the person's
   path from the workstation (the operator's phone holds the TOTP), the
   registry adopted, a reboot, the sweep with `--after-reboot`, external, merge,
   tag.

---

## 0. Where the session starts

```
HEAD            56879a1 on main, local = origin ("Session 36 Run 11: Done, and
                the plan COMPLETE (plan only)"). Deployed: 2538ac0 (1.14.0) on
                both projects; the tag 1.14.0 names 2538ac0. `git diff
                --name-only 1.14.0..HEAD` filtered to src/ bin/ services/
                migrations/ templates/ schemas/ compose.yaml names records only
                (src/agentic_postgres/capacity.py's Session 36 envelope rows,
                34dd8c2) -- re-measure before Run 2.
VERSION         1.14.0. CURRENT_SESSION 36 (src/agentic_postgres/__init__.py:892;
                Session 36's paragraph :835-891). Outputs schema 19
                (src/agentic_postgres/deployed_output.py:40). Project manifest
                1-8 (config.py:64 SUPPORTED_PROJECT_SCHEMA_VERSIONS; schema
                enum schemas/project.schema.json:16-28). host.yaml schema 3.
                Capability manifest 4, lock 4, project lock 3, api-surface 2.
                39 released migrations (the last 20261003120039
                record_retention).
REGISTRY        299 requirements (tests/acceptance-registry.yaml, 6,123 lines;
                Session 36's block ends with LEDGER-001 :6066-6089). 206 claims
                (evidence_claims.py CLAIMS :373-1177; Session 36's block
                :661-675), 65 declared offline (OFFLINE_CLAIMS :106-326;
                Session 36's :308-324). CLAIM_INTRODUCED_IN
                tests/contract/test_evidence_claims.py:953-1238 (asserted ==
                CLAIMS at :1388). ID regex tests/contract/
                test_acceptance_registry.py:111 (ends `…|GOV|LEDGER)-…`;
                family comments :50-110). An entry's keys are exactly five
                (:187) and its target_session <= CURRENT_SESSION (:197).
                250 ADRs. NEXT FREE: D2042, ADR 0251.
EVIDENCE        evidence/session-36.json: 206 claims, 204 passed, 1 not_run
                (replacement_host_restore, D1028), 1 failed (documented_path,
                D1935). port_allocation and the rotation trio PASSED -- they
                pass again only if this trip's sweep declares --after-reboot
                and the four --rotated-* files (§1 D2072).
HOST            62.238.99.122, Hetzner CX23 (3,814 MiB, 2 vCPU Skylake, 38 GB,
                no swap), kernel 7.0.0-34 (booted 2026-10-04 10:26:50Z).
                ~op/agentic-postgres at 2538ac0. Both projects 1.14.0, doctor
                12 ok each, ledgers 39 / 39+4. host.yaml capacity 3814 / 2214
                reserve / 37 disk / 8 reserve (the CHECKOUT's copy is what
                admission reads, D2025). doctor capacity: 608 MiB committed of
                1,600 claimable (304 per project). Domains:
                alpha-db.agenticpostgresql.com and beta's (read from
                /home/op/beta-dev-outputs.json in E0). ACME is on PRODUCTION
                (promoted in Session 2). Session 36's script set s36-* in
                /home/op and WSL ~/s36/run7 (THE MODEL for this trip's).
OPERATOR        2026-10-04: stay on the CX23 (D2042); the control project is
                `control-prod` at control.agenticpostgresql.com with a B2
                mirror (D2071).
```

**What exists, measured at `56879a1`, and the session builds on:**

- **The auth service and its three modes.** `services/auth-api/app/main.py`:
  `configure_logging()` first (`:261`), `resolved = mode if mode is not None
  else os.environ.get("APP_MODE", "")` (`:262`); `APP_MODES =
  frozenset({"auth", "storage", "mcp"})` (`settings.py:34`); an unknown mode
  raises `MissingSetting` (`main.py:263-266`); `mcp` returns early with
  `create_mcp_app()` (`:268-275`); `FastAPI(title="Agentic Postgres auth",
  lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)`
  (`:277-288`); health routes `/health/live`, `/health/ready` (`:290-309`);
  `application.state.mode = resolved` (`:314`) and **the router choice**
  (`:315-339`: storage → `storage_routes.router`; otherwise `routes.router`,
  `workflow_routes.router`, `workflow_admin_routes.router`,
  `connector_routes.router`, `connector_admin_routes.router`; the comment at
  `:311-313` says a third mode is added as a change to this if/else);
  middlewares `StructuredRequestLog` then `StampRequestId` (`:370-371`); the
  OpenAPI override (`:351-356`); the declared path lists `health_paths()`
  (`:434-442`), `public_paths()` (`:445-520`), `route_paths()` (`:523-530`).
  **The lifespan** (`:96-231`): `settings_module.load(mode=mode)` (`:107`; it
  refuses `mcp`, `settings.py:365-374`), the signing key (`:122-127`),
  `BoundedHasher(concurrency=HASH_CONCURRENCY)` (`:129`), the pool
  (`:132-134`), the key set (`:152-160`), `AuthService(...)` with the lock's
  vocabulary (`:162-179`), storage only `_build_storage` (`:180-181`), **auth
  only** the workflow and connector repositories, the connector master key and
  the worker task (`:196-216`), shutdown (`:220-231`). Environment per mode:
  `SHARED_VARIABLES` (`settings.py:455-468`), auth's `REQUIRED_VARIABLES`
  (`:474-481`: + `APG_SIGNING_KEY_FILE`, `APG_MCP_LOCK_FILE`,
  `APG_CONNECTOR_KEY_FILE`), `FORBIDDEN_VARIABLES` (`:548-570`).
  `tests/contract/test_auth_service_shape.py:293-345` requires the compose
  service's environment to equal the declared list plus `APP_MODE`.
- **Login, tokens, verification.** `AuthService.login` (`service.py:184-221`:
  normalize, lookup, verify with a dummy hash for an unknown user, status,
  `issue(token_use="access")`, `record_login`, `open_session`); `issue`
  (`:225-310`: RS256, claims `iss aud sub role scope token_use jti iat nbf exp
  credential_version authz_version`, self-verified before signing);
  `TOKEN_TTL_SECONDS = 900` for human AND agent tokens (`service.py:37`,
  `claims.py:84` — the stage plan's *"agent tokens live 900 s"* is true of
  every token); refresh 30 days (`refresh_sessions.py:77`);
  `authenticate` (`service.py:314-401`) re-reads the user's state and compares
  status, `credential_version`, `authz_version`, role and scope **on every
  request**; `require_scope` (`:403-412`). **There is no FastAPI `Depends` for
  the caller** — every handler calls `service.authenticate(...)` itself.
  An extra claim passes this verifier, the plane's, PostgREST and the
  pre-request hook (rig 33a, `claims.py:86-94`). Error bodies: 401
  `{"error":"authentication_failed"}` + `WWW-Authenticate: Bearer`, 403
  `authorization_failed`, 400 `malformed_request`, 422 `invalid_request`
  (`errors.py:40-56`, `:262-286`); the exception mapping is `routes._guard`
  (`routes.py:494-512`); bodies are parsed strictly (`strict_json.py:47`,
  16 KiB; pydantic `extra="forbid"`, `models.py:32-33`).
- **Secrets the service already mints.** `one_time_tokens.py`:
  `secrets.token_urlsafe(32)` (43 characters, `:31`, `:51`), pattern
  `^[A-Za-z0-9_-]{43}$` (`:37`), stored as unsalted `sha256(token).hexdigest()`
  *on purpose* (`:14-18`, `:55-63`) — used by refresh and password-reset
  tokens. **Passwords** are Argon2id at the frozen profile
  (`profile.py:98-106`: 64 MiB, t=3, p=1) behind `BoundedHasher` with
  `HASH_CONCURRENCY = 2` (`profile.py:114`; `hashing.py:321-401`). An agent
  secret is `token_urlsafe(32)` hashed with Argon2id (`service.py:853-862`)
  and exchanged ONCE per 900 s at `/auth/agent-token`. The password-reset
  shape (*shown once, handed over out of band*): `routes.py:617-658`,
  `service.py:993-1040`, table `app_private.password_resets`
  (`0026-password-reset-plane.sql:83-105`), `auth_consume_password_reset`
  (`:171-229`).
- **The identity registry.** `app_private.users` (`0011-identity-registry.sql:
  109-123`: `role_name`, `scopes text[]` non-empty, `status`,
  `credential_version`, `authz_version`); `auth_create_user(text, text, text,
  text[], text)`, `auth_set_authorization`, `auth_set_status`,
  `auth_set_password`, `auth_list_users` granted to `{{auth_service}}`
  (`0012:406-416`); `auth_bootstrap_administrator` deliberately NOT
  (`0012:418-`, `repository.py:16-20`). `Repository` calls only definer
  functions (`repository.py:126-142`). Role ceilings (`scopes.py:63-107`):
  `api_documentation` → exactly the introspection class (`meta:read`,
  `INTROSPECTION_SCOPE`, `scopes.py:55`); `authenticated` → data + storage;
  `project_admin` → data + storage + administrative. `_role_name` accepts any
  suffix the deployment derives (`service.py:458-462`); `_check_scopes`
  refuses an empty set or one beyond the ceiling (`:478-499`). **No audit row
  is written for a user change** (`0012:170-260`); the only audit table is
  `app_private.agent_audit`.
- **Mounting.** Traefik strips `/api/app` and the service serves at its root
  (`naming.py:119` `APP_PATH_SUFFIX = "/app"`; `:394-402` the strip
  middleware's name; `:1134-1135` `route_app`; `:1168` `jwt_issuer`).
  Router labels are rendered by `runtime_override._app_labels`
  (`runtime_override.py:1251-1310`: rule ``Host(...) && (Path(`{path}`) ||
  PathPrefix(`{path}/`))`` `:1292-1294`; middlewares `:1297-1300`; strip
  `:1309`). Compose's `auth:` service (`compose.yaml:1195`) carries `APP_MODE:
  auth` as a literal (`:1271`), `APG_DATABASE_ROLE: ${AUTH_SERVICE_ROLE_NAME}`
  (`:1305`), the passfile (`:1306`), the signing key (`:1308`). Rendered
  variables `API_APP_PATH` (`rendering.py:1930`),
  `APP_STRIPPREFIX_MIDDLEWARE_NAME` (`:1933`), `JWT_ISSUER` (`:1947`),
  `AUTH_SERVICE_ROLE_NAME` (`:1948`). The outputs `routes` block
  (`rendering.py:437-458`) names every route **whether or not its service is
  enabled** — storage's comment at `:449-452`: *"the readiness claim lives on
  the deployed branch (D326)"*.
- **The tenant extension point.** A set lives at `projects/<slug>/`
  (`docs/decisions/0198-…md:57-67`; `migrations.py:77`, `:233-238`,
  `:268-269`), named by the manifest's `migrations.set` (schema ≥ 5,
  `schemas/project.schema.json:104-116`; `config.py:89-92`; the render refuses
  a missing directory or manifest, `config.py:1225-1240`). **The lint**
  (`migrations.lint_project_set`, `migrations.py:795-938`): placeholders only
  from `PROJECT_PLACEHOLDER_SOURCES` (`:88-98` — `object_owner`,
  `authenticated`, `anon`, `agent_reader`, `agent_writer`,
  `api_documentation`, the database name; **not** `auth_service`);
  `FORBIDDEN_STATEMENTS` (`:142-159`: `\bapp_private\b`, role/schema/extension
  DDL, default privileges, labels, rules, publications, subscriptions, `COPY …
  FROM PROGRAM`); `SET ROLE` only as `SET LOCAL ROLE {{object_owner}}`
  (`:125`, `:864-871`); no drop of a release view (`:873-880`); no DDL on the
  ten release functions (`:882-903`, `:187-196`); FORCE RLS on every `CREATE
  TABLE app.X` (`:905-924`, `:163-171`); an `AP900` down (`:926-938`, `:131`).
  It does NOT refuse `SECURITY DEFINER`, new `api`/`app` functions, `CREATE
  TYPE`, sequences, triggers or grants to the allowed placeholders. The set is
  applied at deploy step 6 (`bin/deploy-project.py:2556-2585` →
  `bin/migrate.py:305-352`) by the `dbmate-project` service as
  `migration_user` (`runtime_override.py:470`, `:477`; `bin/migrate.py:157`,
  `:182`) into `app_private.project_schema_migrations` (`rendering.py:1034`).
  The project lock: `PROJECT_LOCK_SCHEMA_VERSION = 3` (`migrations.py:100-104`),
  frozen by `bin/migrate.sh --project <manifest> freeze-lock`. The release set
  is applied first, so the control database will carry the release domain
  (`notes`, `tasks`, …) too (`migrations.py:286-287`). `RELEASE_FUNCTIONS`
  (`tests/contract/test_project_migration_sets.py:919-932`, exact equality at
  `:1076`); `test_every_committed_project_set_still_passes` (`:1111`) globs
  `projects/*/migrations/manifest.json`, so `projects/control` is linted by
  construction. RLS reads the caller through `app.current_user_id()` =
  `nullif(current_setting('app.user_id', true), '')::uuid`
  (`0003-owner-scoped-tables-and-forced-rls.sql:13-20`). PostgREST exposes
  only `api` (`rendering.py:962-965`). **A project's PostgREST contract**
  (`projects/<slug>/contracts/postgrest-api-surface.yaml`, schema 2) is
  required by `bin/migrate.py`'s propose path (`:795-800`) and validated by
  `api_surface.load_project_surface` (`api_surface.py:158-192`), which refuses
  a contract naming nothing (`:206-211`); whether the RENDER and the DEPLOY
  require it for a set that publishes nothing in `api` is **Run 1's 37e**.
- **The manifest's optional surfaces.** `storage.enabled` (required boolean,
  `schemas/project.schema.json:318-330`), `api.rest` (`restService.enabled`,
  `:626-`), `api.app` (`appService.enabled`, `:597-`), `backup.enabled`
  (`:438-450`), `backup.mirror` (schema 4). **`mcp` has no `enabled`**
  (`:272-284`: `public_base_path` required). The operator-supplied R2 storage
  pair (`r2_access_key_id`, `r2_secret_access_key`, `secrets.required.yaml:
  655-690`) carries **no facility**, so whether a storage-disabled project
  still owes it is **Run 1's 37e** (facilities: `secrets_contract.py:83-95`,
  `:181-193`).
- **A third project on this host** was brought up once: `gamma-dev`,
  ephemeral, Session 17, 2026-09-04, retired 2026-09-05
  (`docs/plans/session-17-implementation-plan.md:419-446`: *"two days … three
  gates and eleven repairs"*; D971 manifest in the checkout, D972 a redirected
  deploy hung, D974 no admin observed, D975 a placeholder file in the
  checkout). The measured order is `docs/fleet-operations.md` §6 (`:133-188`)
  and `docs/operator-guide.md` §3 (`:129-251`): two R2 buckets and two tokens,
  a grey-cloud A record, for a mirror a B2 bucket and key pair — all by hand
  (ADR 0110); `sudo bin/bootstrap-providers.sh … --plan` then `--apply` with
  the hand-placed `/root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential`
  (`bin/bootstrap-providers.py:1291-1292`; it creates the Infisical project,
  the `{key}-runtime` identity and every GENERATED secret, `:880-915`, and
  lists the operator-supplied ones, `:228-239`); paste the operator-supplied
  values by hand (`/storage` must be created by hand, `/backup` exists after
  `--apply`, `fleet-operations.md:153-154`); `materialize-secrets.sh`; deploy
  (first pass: ports and the app route `unavailable`, D326); `auth-admin.sh
  bootstrap` (root, TTY, the password typed twice, never printed,
  `bin/auth-admin.py:122-167`, `:336-363`; a second run is `AP409`);
  `--render-runtime-only` + the printed `bin/database-ports.sh verify` line
  (`bin/deploy-project.py:2127-2193`); deploy again; first full backup and
  `backup.sh … schedule enable` (`docs/backup-operations.md:103-142`;
  `bin/backup.py:552-633`). `observe_app` curls `{url}/auth/me`
  (`bin/deploy-project.py:1499-1540`) and reports `unavailable` while no
  administrator exists (`:1512-1514`).
- **Admission.** `EXIT_ADMISSION_REFUSED = 12` (`capacity_reading.py:89`);
  a project is charged `unreclaimable_mb` = `shared_buffers_mb +
  maintenance_work_mem_mb + max_connections × 2` = 304 at the defaults
  (`config.py:742-755`, `:258`); `safe_available = memory_mb −
  reserve_memory_mb − committed` (`capacity_reading.py:432-458`); the
  candidate's own key is excluded from `committed`
  (`bin/deploy-project.py:2259-2265`). With `control-prod` at the defaults:
  **912 committed of 1,600, 688 left** — admission will admit; whether the
  MACHINE has the memory is E0's reading (§1 D2042).
- **What finds a new project by itself, and what does not.** `fleet.sh`
  (`bin/fleet.py:78-82`) and `doctor capacity`/admission
  (`capacity_probe.py:280`) enumerate `/etc/agentic-postgres/projects/`;
  `dr-kit.sh export` enumerates NOTHING (`bin/dr-kit.py:205`, one `--project`
  each); **no command enables `agentic-postgres-project@<key>.service`**
  (`bin/provision-host.sh:845-850`: *"The edge and project units are NOT
  enabled"*; the unit is `WantedBy=multi-user.target`,
  `systemd/agentic-postgres-project@.service:54-55`). `evidence.load_rendered`
  reads EVERY `.generated/<key>/outputs.json` (`evidence.py:186-246`) and
  `collision_count` compares all pairs (`:256-287`); the LIVE isolation
  matrix compares A and B only (`tests/deployment/conftest.py:123-136`,
  `test_session12_isolation_matrix.py:305-435`);
  `test_every_permanent_project_is_scheduled`
  (`tests/deployment/test_session17_fleet.py:176-180`) requires every
  permanent project's backups `SCHEDULED`.
- **The CLI.** `bin/apg.sh` holds no verb list (`:9`, `:14`): verb `X` is
  `bin/X.sh` (`:136-151`, pattern `:78`), `deploy` the one special case;
  `APG_PROJECT` is appended only for a verb whose `--help` has a line
  starting `--project FILE` (`:199-216`, `:263-266`). **No `login`, `logout`,
  `context`, `org`, `project` or `control` command exists.** Every HTTP client
  in `bin/` uses `urllib` and reads its base URL from a document
  (`bin/workflow.py:334-359`, `bin/connector.py:427-441`, `bin/api.py`
  `rest_base` refuses non-https); a token is held in the environment or in
  memory, never in argv or a file (`bin/workflow.py:63`, `:84`,
  `:362-382`; `bin/studio.py:233-276` — a password from a 0600 file whose
  mode is checked, or `getpass` at a TTY). **No config or context file exists
  anywhere** (no `.config/apg`, `XDG_CONFIG_HOME`); the closest precedents are
  `bin/connect.sh:229-258` (a 0700 state directory, symlinks and foreign
  owners refused) and `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW, 0o600` writes
  (`bin/connector.py:403`). ADR 0093's guard
  (`tests/contract/test_operator_commands_run_on_the_host.py:47`, `:161-186`:
  stdlib + `agentic_postgres` + `yaml`; `CHECKOUT_ONLY = {"app-contract.py"}`
  `:60-65`). `tests/contract/test_cli_contract.py`: `SHELL_COMMANDS` `:42-225`,
  `PYTHON_COMMANDS` `:227-293`, both directions (`:1063-1097`);
  `COMMANDS_WITH_VERBS` `:477-503` and `verbs_documented_by` `:506-531`
  (equality, `:577-594`); git-index mode 100755 (`:358-372`); preamble
  (`:396-403`); `--help` > 40 characters (`:466-470`), each verb's `--help`
  without root, argument or host (`:538-574`); **a `--help` may not name
  `--password`, `--secret`, `--token`, `--api-key`, `--access-key` or
  `--private-key`** (`:1100-1113`; `--password-file` passes the regex's
  `(?![a-z-])`). The completion script may name no verb
  (`test_completion_command.py:138-157`).
- **The Reality Ledger** (`docs/reality-ledger.yaml`, 738 lines, schema
  `schemas/reality-ledger.schema.json`): the five rows this session builds are
  `accounts` (`:24-42`), `organizations` (`:44-59`), `api_keys` (`:61-78`),
  `management_api` (`:80-95`), `cli_remote` (`:97-114`), each `planned`,
  `target_session: 37`; `email` (`:474-489`) and `passkeys` (`:491-504`, which
  promises *"a password and a one-time code"*) stay `planned`. **There is no
  row for operations or the project registry**; `projects_self_service`
  (`:136-154`, target 38) carries `project.create` in its `stage5_reality`.
  `tests/contract/test_reality_ledger.py:140-158`
  `test_the_sets_the_guard_will_read_are_empty_today` asserts that
  `src/agentic_postgres/operations.py` and `services/console/` do not exist
  (*"Session 37's guard … must replace this assertion"*);
  `test_a_planned_row_has_no_control` (`:115-118`); the passed-evidence half
  (`:57-82`) is outside `LEDGER-001`'s node ids since D2030.
- **The threat model.** The hosted list (`docs/threat-model.md:157-244`):
  items naming Session 37 — invitation abuse and enumeration (`:176-180`),
  API-key compromise and replay (`:181-185`), organisation privilege
  escalation (`:186-190`), project and branch enumeration, 37's half
  (`:191-194`), control-plane / data-plane credential confusion, 37's half
  (`:218-222`), cross-project leakage (`:237-240`). The table header (`:19`,
  nine columns); `parse_threat_table` keeps a row only if its cell count
  equals the header's — **a literal `|` inside a cell silently drops the row**
  (`test_acceptance_registry.py:430-446`); every row names a registered
  requirement (`:489-493`).
- **The gate to derive from.** `bin/session-36-check.sh` (1,757 lines: header
  `:2-100`, `readonly SESSION=36` `:109`, usage `:166-576`, parser `:612-806`,
  `check_rendered_fixtures` `:916-945`, `mode_offline` `:1250-1467` with the
  contract checks `:1320-1352`, `mode_host` `:1469-1672` with its exports
  `:1548-1618`, `mode_external` `:1674-1746` — it REQUIRES `--ssh-destination`
  `:1679-1680`). `tests/contract/test_session_thirty_six_gate_modes.py` (999
  lines; `SESSION = 36` `:53`; the claims table `:87-100`; the offline-set
  assertion `:658-716`; one usage entry per parser flag `:966-999`). The
  external modules' `pytestmark` needs only `APG_PUBLIC_IPV4` and
  `APG_PROJECT_A_OUTPUTS` (e.g. `tests/external/test_session5_public_api.py:39`);
  only two proofs need `APG_SSH_DESTINATION`
  (`test_session4_public_transports.py:193`, `:241`). The environment roster
  is the closed tuple `tests/conftest.py:86-189`.
- **The contract command.** `bin/app-contract.py` (`CHECKOUT_ONLY`) builds
  `create_app("auth").openapi()` and `create_app("storage").openapi()`, merges
  them (`:85-160`) into `contracts/app-openapi.canonical.json` (`:66`) and
  compares byte for byte with `--check` (`:212-224`); its guard is
  `tests/contract/test_app_contract_aggregate.py:236-255`; the gate runs
  `bin/app-contract.sh --check` in `mode_offline` (`session-36-check.sh:1322`).

**A stale citation, recorded so the executor does not chase it:** the stage
plan's `main.py:258-335` (D1950) is now `main.py:261-339`.

---

## 1. The divergence table

Six columns. Each row is a **measured fact about the tree at `56879a1`** (or
about the host as Session 36's records left it) set against what the brief
says, with the decision this plan takes. **Next free number after this table
is D2073.** Rows the runs add go in a second table below it, in execution
order.

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D2042** | Stage plan §5 *Session 37*: *"Ends on the new host"*; §11 item 1: *"from Session 37 on, against the new host"*; CLAUDE.md §3 item 0: *"ask before planning around a size"*. | The server is still the **CX23** (3,814 MiB, 2 vCPU, no swap): CX33 was out of stock in `hel1` on 2026-10-04 (D2032). Two projects commit 608 of 1,600 claimable MiB; the control project at the defaults is charged 304 (`config.py:742-755`) → 912 committed, 688 left. Session 17 put a third project on this same size (*"~350 MB per project, 1982 MB available — the third project fits"*, `session-17-implementation-plan.md:188-189`). | **The operator decided on 2026-10-04 to plan Session 37 on the CX23 as it is.** Sheet E0 reads `free -m` and `docker stats --no-stream` with two projects, and `sudo bin/admit.sh` against the draft control manifest; Run 10 reads `free -m` again after the control project is up. **Stop and ask** (§9) if admission refuses, or if `available` after the control project's second deploy is below **1,024 MiB** — the margin a sweep, the probe and a deploy of a neighbour need together (Session 35 measured a saturated neighbour at ~480 req/s on this machine). The rescale stays owed before Session 38 (D2032). | The control plane is small (a handful of tables, one person) and admission is the product's own answer to *does it fit*; the machine's free memory is the second reading admission does not take (D767), so both are read. | 0221, 0222 |
| **D2043** | D1950: *"its management API is a fourth `APP_MODE` (`control`) of the same image"*; §5: *"A fourth `APP_MODE`, `control`, in `services/auth-api/app/main.py`, serving `/api/v1` behind the control project's router"*. | Three modes from one image (`settings.py:34`); each mode is a separate CONTAINER of the project (`auth`, `storage`, `mcp`). A new mode in a new container would need the signing key to mint a login token (a second issuer) or would leave login in the `auth` container — where TOTP would then have to live, changing every project's login. Accepting an invitation needs `auth_create_user` (granted to `auth_service` alone, `0012:409`). | **The control project's existing `auth` container runs `APP_MODE=control`** (rendered from the manifest's `control` facility, D2044; `compose.yaml:1271`'s literal becomes `${AUTH_APP_MODE:?required}`, `auth` for every other project). **`control` mode = the health routes + the probes the deploy and the doctor read (37e names them; expected `/auth/me` and `/auth/jwks.json`) + `/v1/*` — and nothing else**: no `/auth/login` (the login is `POST /v1/sessions`, which enforces TOTP, D2050), no `/admin/*`, no workflow or connector route, **no worker** (the lifespan's auth-only branch `main.py:196-216` is not taken). Its environment is auth's exactly (`REQUIRED_VARIABLES`), so the compose definition stays one. `public_paths()` gains a `control` arm, and `test_the_application_serves_exactly_the_declared_paths` (`test_auth_service_shape.py:904-924`) a third case. | One process is the issuer, the verifier and the control plane: no second holder of the private key, no second pool, no new role or secret, and TOTP lives where the login is. Serving the release's admin and agent routes from the control plane would be surface a customer can reach and nobody reviewed for that reader. | **0251** |
| **D2044** | §5: *"The `control` project: a manifest … with `lifecycle: permanent`"*; stage plan §2.2: *"Session 38 adds manifest schema 9 (`compute`)"*. | Nothing in a manifest says a project is the control plane; the precedent for a per-project switch is the connectors facility (schema 7, `schemas/project.schema.json:593-615`, gate `:952-971`; absent = off). | **Project manifest schema 9 adds `control: {enabled: boolean}`** — optional, forbidden below 9 (the `if/then` gate shape of `:952-995`), absent = off; `config.py` `SUPPORTED_PROJECT_SCHEMA_VERSIONS` gains 9 and a `PROJECT_CONTROL_FROM = 9` beside `PROJECT_APPROVALS_FROM` (`:80-82`). **At most one control project per host** is NOT enforced in 37 (a second would be a second, separate control plane; §10). **Session 38's `compute` becomes schema 10**, recorded in the stage plan's Status block at the close. | A facility is the house shape for *this deployment has a capability the others do not*, and a migratable optional field is a minor (ADR 0162). Deriving *control* from the slug would be a name doing a manifest's job. | **0251** |
| **D2045** | D1952: the CLI reads *"the endpoint"*; ADR 0158: the deployed document is the address book. | `routes` (`rendering.py:437-458`) names every route whether or not its service is enabled, the readiness living on the deployed branch (D326). | **Outputs schema 20 adds `routes.control`** = `https://{domain}{api.public_base_path}/v1` (`naming.CONTROL_PATH_SUFFIX = "/v1"`, `route_control` beside `route_app`, `naming.py:1134-1137`), **named for every project**; the deployed branch observes it `ready` only where the facility is on and `unavailable` elsewhere — the same honesty storage already has. The document also records `control: {enabled}` beside `storage.enabled`, so a reader of the deployed document finds the control project without a manifest (D2068). Every reader of `routes.` is grepped (`grep -rn "routes\]\|\"routes\"\|routes\." src bin tests --include=*.py`) and each one that enumerates the members gains `control`. `deployed_output.SCHEMA_VERSION` 19 → 20; ADR 0241's bound reads 20 and 19. | The control endpoint is read, never typed: `apg login` is given the URL by a person, but every proof and the registry read it from the document. | **0251**, 0158, 0241 |
| **D2046** | D1950: *"its own migration set under `projects/control/`, linted like any set"*. | The lint's placeholders exclude `auth_service` (`migrations.py:88-98`), and it refuses the word `app_private` (`:143`). The control mode connects as `auth_service` (`compose.yaml:1305`); invitation acceptance must call `app_private.auth_create_user` AND write a membership in one transaction. | **A set whose project enables the `control` facility may use `{{auth_service}}` — in `GRANT EXECUTE ON FUNCTION … TO {{auth_service}}` and nowhere else**; every other set is refused it exactly as today. `lint_project_set` gains a keyword argument (`control: bool = False`), passed from the manifest at every caller (grep `lint_project_set(` in `src/` and `bin/` — the render `rendering.py:2509-2527`, `bin/migrate.py:771`, and any test), and a statement naming `{{auth_service}}` outside a function grant is refused even then. **The set still never names `app_private`**: the transaction is composed in Python on one `auth_service` connection — `auth_create_user(...)`, then `app.control_accept_invitation(...)`. | The widening is one role, one statement form, one facility; it gives a role MORE to execute, never a caller more to reach, and the role is the identity service the control plane already is. Re-implementing the identity registry inside the set would be a second account system (D1517's objection). | **0251** |
| **D2047** | §5: *"organisations, memberships …, invitations, API keys, projects, operations, regions, notifications; FORCE RLS on every `app` table"*; stage plan §8: *"PostgreSQL is the final authorization authority … at risk: the control project's tables (37)"*. | FORCE RLS binds the table OWNER too, so a definer function owned by `{{object_owner}}` is filtered by the policies; a policy on `memberships` that reads `memberships` is the textbook *"infinite recursion detected in policy"*. Nothing in 37 reads a region (host schema 4 is 38's, D1957) or writes a notification (41's, D1968). | **Tables in 37: `app.control_accounts`, `app.control_organizations`, `app.control_memberships`, `app.control_invitations`, `app.control_totp`, `app.control_keys`, `app.control_projects`, `app.control_operations` — all in `app`, all FORCE RLS, all reached ONLY through `app.control_*` definer functions granted to `{{auth_service}}` (never to a request role, never in `api`, so PostgREST publishes nothing and the agent vocabulary gains nothing).** The policies are `TO {{object_owner}}` and scope by the caller: `app.current_user_id()` (set by the control mode with `set_config('app.user_id', …, true)` at the top of each transaction) and, for rows of an organisation, `app.control_org_scope()` — a GUC the definer function sets ONLY after it has read the caller's own membership row. **Rig 37b decides between this design (G) and owner-wide policies with every check in the function bodies (T)**: G if the recursion control fails as expected and G's four measurements hold; T otherwise, with the reason in ADR 0251. **`regions` → Session 38; `notifications` → Session 41.** | A table nobody reads is a declared field with no reader (D816). Keeping the functions out of `api` keeps the control project's own PostgREST from becoming a second door to the control plane. | **0251** |
| **D2048** | ADR 0198: a set carries `contracts/postgrest-api-surface.yaml` and its canonical snapshot. | `api_surface.validate_project_surface` refuses a contract naming nothing (`api_surface.py:206-211`); `bin/migrate.py:795-800` requires the file for `propose`; whether the RENDER and the DEPLOY need it for a set that publishes nothing in `api` was not read. | **Rig 37e renders a throwaway copy of the tree with a draft `projects/control` that has no `contracts/` directory** and reads which command refuses. **Rule**: if nothing on the render/deploy path refuses, the control set ships no PostgREST contract and `approvals_required` stays absent (no proposal); if something refuses, the run that hits it widens that one reader to accept *a set that creates no `api` object* — an ADR 0251 sentence and a stricter test (*a set with an `api` object and no contract is still refused*) — never a fake contract naming a decoy object. | A contract that names something only so it is not empty would be a reviewed surface describing nothing real. | **0251** |
| **D2049** | D1950: *"its accounts are the auth service's users of that project"*; §5: its capability manifest names *"**no** agent tools beyond the release's defaults"*. | A user needs a `role_name` and a non-empty `scopes` set within the role's ceiling (`0011:109-123`, `service.py:478-499`). `api_documentation`'s ceiling is exactly introspection (`scopes.py:55`, `:63-107`). The control project's PostgREST, storage and agent plane would serve the release domain to anyone holding a control token. `mcp` has no `enabled` flag (`schemas/project.schema.json:272-284`); `api.rest.enabled` and `storage.enabled` exist. | **A control account is an identity-registry user with role `api_documentation` and scopes `["meta:read"]`** — the narrowest authority the registry can describe, reading no row of the control project's own data plane — **if rig 37e shows `_check_scopes` accepts it against the control project's compiled vocabulary**; otherwise `authenticated` with the single narrowest data-read scope the vocabulary names, and the row records which. **The control manifest sets `api.rest.enabled: false` and `storage.enabled: false`** and omits `mcp.capabilities` (`project.second.example.yaml:20-26` is the form); `mcp` stays rendered (it has no switch) with no agent created on the control project, and `docs/control-plane.md` says so. **The R2 storage pair**: 37e reads whether a storage-disabled project still owes it (`secrets.required.yaml:655-690` has no facility); if it does, the operator creates the bucket and its token anyway (Sheet P1 says why) — adding a `storage` facility would move every project's secret contract and is not this session's. | The control plane's people need an identity, not a data plane; every surface the control project serves beyond `/v1` is one more thing to explain. | **0251** |
| **D2050** | D1951: *"TOTP (RFC 6238) is required for `owner` and `admin`, implemented over the standard library's `hmac` with no new dependency, measured against the RFC's test vectors (control: a wrong-step code refused)"*; §5: *"required for `owner` and `admin` at login"*. | No TOTP anywhere (`totp`, `hotp`, `pyotp`: 0 code hits). Login is `AuthService.login` (`service.py:184-221`). A seed must be readable to compute an HMAC; nothing in the tree stores a readable secret in a table. | **`services/auth-api/app/totp.py`**: RFC 4226 HOTP + RFC 6238 TOTP (SHA-1, 30 s, **6 digits** in the product, 8 for the RFC vectors), `hmac.compare_digest`, a window of **±1 step**, **replay refused** (`app.control_totp.last_step`: a code is accepted only for a step `>` the last accepted, updated atomically in the same statement). Seeds: 20 random bytes, stored in `app.control_totp` (FORCE RLS; reached only through `app.control_totp_*` definer functions granted to `{{auth_service}}`), base32 in an `otpauth://totp/agentic-postgres:<username>?secret=…&issuer=agentic-postgres&period=30&digits=6&algorithm=SHA1` URI **shown once** at enrolment. **Login** (`POST /v1/sessions`): password first (the existing path, dummy hash for an unknown user), then — if the user has an ENABLED factor — the code is required (`401 second_factor_required` without one, `401 second_factor_invalid` with a wrong or replayed one). **Who must have it**: anyone who holds `owner` or `admin` in any organisation, or `admin_users:write` in the control project's registry; such a person WITHOUT an enabled factor can log in and reach only `/v1/me`, `/v1/me/totp*` and `/v1/sessions*` — every other `/v1` route answers `403 second_factor_required`. **Confirming** a factor revokes every session of the user (the refresh families, through the existing revocation function — 37e greps its name and grant), so no token minted without the code outlives enrolment. **A lost device** is the operator's: `sudo bin/control.sh totp-reset --username NAME --confirm control-prod` (D2068). The plaintext seed in the database, carried by the (encrypted) backups, is ADR 0252's stated residual risk; encrypting it at rest is `planned`. | The RFC's own vectors are the independent implementation; storing a seed readable by the one service that verifies it is how every TOTP server works, and saying so is cheaper than a key-management scheme nobody asked for. Refusing an un-enrolled owner everything but enrolment is what makes *"required"* true without locking a new owner out of the only route that lets them comply. | **0252** |
| **D2051** | D1951: *"An invitation is a single-use, expiring token minted by an organisation owner or admin and shown once to the inviter … accepting it creates the account and the membership in one transaction"*; §5's end state: *"the operator invited by the bootstrap admin"*. | Nobody can mint an invitation before an organisation exists, and an organisation needs an owner. The bootstrap administrator (`auth-admin.sh bootstrap`) holds `admin_users:write` and no organisation. `one_time_tokens` is the house token (`:31-63`). | **Two kinds of invitation, one table** (`app.control_invitations.organization_id` NULL or not): an **account invitation** (no organisation) is minted by a caller holding `admin_users:write` in the control project's registry (the operator's bootstrap administrator, TOTP enabled); accepting it creates the account only, and the account may then `POST /v1/organizations` (becoming its `owner`). A **membership invitation** is minted by an `owner` or `admin` of that organisation for a role at or below their own (`admin` may invite `admin`, `member`, `viewer`; only `owner` invites `owner`); accepting it creates the account if the caller has none, and the membership — **in one transaction**. Token: `one_time_tokens.mint()`, its SHA-256 stored, shown once in the `201` body; **lifetime 72 h by default, at most 168 h**. **Acceptance is one `UPDATE … SET accepted_at = now(), accepted_by = … WHERE token_hash = $1 AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at > now() RETURNING …`** — single use under concurrency by construction (rig 37b measures two concurrent accepts). **A used, expired, revoked or unknown token gets ONE answer**: `401 {"error":"invitation_invalid"}`, byte-identical. A username already taken is refused only AFTER the token validated, with the token left unspent (the transaction rolls back). | One table keeps one acceptance path and one set of refusals; the account invitation is the invite-only door for the first person of each organisation, held by the operator who holds root anyway. | **0252** |
| **D2052** | D1952: *"API keys: `apg_` + 32 random bytes, Argon2id-hashed like an agent secret, shown once, scoped from a closed vocabulary (`projects:read\|write`, `branches:read\|write`, `backups:read`, `restores:write`, `compute:write`, `usage:read`, `members:write`, `keys:write`), owned by a member and revoked with them"*. | An agent secret is Argon2id-verified ONCE per 900 s token exchange; a management key is presented on EVERY request. The frozen profile costs 64 MiB per verify and the service runs at most `HASH_CONCURRENCY = 2` at once (`profile.py:98-114`) — so Argon2id per request would cap the whole control plane at two key-authenticated requests in flight and make every request a 64 MiB allocation. The tree already stores 256-bit tokens as SHA-256, *"unsalted and deterministic on purpose"* (`one_time_tokens.py:14-18`). Of the brief's ten scopes, only reads have a route in 37. | **A key is `apg_<key_id>_<secret>`**: `key_id` 16 lowercase hex (8 random bytes, the lookup), `secret` `token_urlsafe(32)` (43 characters, 256 bits); `app.control_keys` stores `key_id`, `sha256(secret)` hex, the owning member, the organisation, `scopes text[]`, `created_at`, `last_used_at`, `revoked_at`; **compared with `hmac.compare_digest` after a SHA-256 — never Argon2id** (rig 37c measures both on the CX23-class workstation and records the per-request cost). **The 37 vocabulary is exactly the scopes a 37 route checks**: `organizations:read`, `members:read`, `projects:read`, `operations:read`; each later session adds its own with its route (`projects:write` in 38, …). **Credential-minting routes are human-session only** (keys, invitations, TOTP, role changes): a key gets `403 human_session_required` there, so a leaked key cannot mint its own successor. **Effective scopes are computed per request**: the key's scopes ∩ what its owner's CURRENT role grants; a member removed or the key revoked → `401 authentication_failed` on the next request (no cache). | A fast hash is the right hash for a high-entropy random secret, and the tree says so in its own words; a slow hash per request is a denial of service the product would hand itself. Minting nothing from a key is the smallest rule that makes *a key's scopes never exceed its minter's* true across time. | **0253** |
| **D2053** | D1951: *"Organisation roles `owner \| admin \| member \| viewer`, mapped onto control-plane scopes"*; threat item `:186-190`: *"each role refused every operation above it"*. | No roles exist. | **The matrix, in one table in `services/auth-api/app/control_roles.py`**: `viewer` and `member` — read the organisation, its members, its projects and operations, and manage their OWN keys (37: identical; 38 gives `member` `projects:write`); `admin` — + invite and remove `admin`/`member`/`viewer`, change those roles, revoke any key in the organisation; `owner` — + all of that for `owner`. **The last `owner` cannot be removed or demoted** (`409 last_owner`). Every route names the role it needs; a test enumerates every `/v1` route × every role (the CTL-ROLE-001 matrix). | A matrix in one place is one thing to review; a role checked in each handler is the D600 shape. | **0252** |
| **D2054** | §5: *"`POST /api/v1/projects` returns an operation that stays `pending`, and the Ledger says `planned` for its execution … a `project.create` operation recorded and listed"*; D1979 guard (2): *"an entry `planned` has no operation type and no enabled control (the fake-complete guard)"*. | `project.create` acts on `projects_self_service`, `planned` until 38 (`reality-ledger.yaml:136-154`). A request accepted into a row that nothing will ever execute is a control acting on a planned concept — what the guard forbids — and a `pending` that never moves is a status that claims a future. `test_the_sets_the_guard_will_read_are_empty_today` asserts `operations.py` absent (`test_reality_ledger.py:151`). | **No operation type is accepted in Session 37.** `src/agentic_postgres/operations.py` holds the CLOSED type table (`project.create\|delete\|sleep\|wake\|resize\|export`, `branch.create\|reset\|delete`, `restore.create`, `credential.rotate` — stage plan D1953), each mapped to the Ledger row it acts on, and `accepted(type)` is TRUE exactly when that row is `available` or `beta`. `POST /v1/projects` answers **`409 {"error":"not_available","ledger_row":"projects_self_service"}`** and writes no row. `app.control_operations` exists (the shape 38 fills) and `GET /v1/operations[/{id}]` read it (empty). **The guard replaces the operations half of `test_the_sets_the_guard_will_read_are_empty_today`**: every type names an existing row; a type is accepted iff its row is `available`/`beta`; the console half stays as written. The live end state reads the refusal instead of a pending row. | The Ledger's guard is the control for this stage's failure mode; building the first exception to it in the session that wrote it would teach every later session that a plan sentence outranks the guard. | **0254**, 0247 |
| **D2055** | Stage plan §11: *"The Reality Ledger moved in the run that builds the thing, never at the close"*. | The guard's passed half (`test_reality_ledger.py:57-82`) requires an `available`/`beta` row's `evidence` to be `passed` in the NEWEST `evidence/session-*.json`; a live claim first passes in this session's merged document, which exists only after Run 11. Moving a row earlier fails every workstation gate until then (D2021's shape). | **`accounts`, `organizations`, `api_keys`, `management_api` and `cli_remote` move to `beta` in Run 12**, each naming the claims §2 registers as `evidence`, after `evidence/session-37.json` reads them `passed`. The building runs edit only their `stage5_reality` sentences if the build changed what they say (e.g. D2052's hash). **ADR 0247 is amended**: a row's STATUS moves in the run whose evidence makes it true; its TEXT moves with the build. | The rule's purpose — a row checked against the run that built the thing — is kept by the text; the status needs the evidence the guard reads. | **0254**, 0247 |
| **D2056** | Stage plan §5: *"First run: the `THR-*` rows"*. | A threat row must name a registered requirement (`test_acceptance_registry.py:489-493`), and a requirement's `target_session` may not exceed `CURRENT_SESSION` (`:197`) — so a 37 row cannot exist before the bump (D1999's reason). | **Run 1 rewrites the six list items** naming 37 with the negative test each owes BY NODE ID (proposed). **Run 9 moves them into the table** as `THR-CTL-INVITATION`, `THR-CTL-KEY`, `THR-CTL-ESCALATION`, `THR-CTL-ENUMERATION`, `THR-CTL-PLANE-CONFUSION` with §2's requirements — no `\|` inside a cell (the parser drops such a row silently). Enumeration's branch half (40) and confusion's 38/39 halves stay in the list. | The order the guard enforces. | 0246 |
| **D2057** | §5: *"frozen as `contracts/control-openapi.canonical.json` with `bin/control-contract.sh --check`"*. | `bin/app-contract.py` already turns the auth service's app objects into a frozen snapshot and is the ONE `CHECKOUT_ONLY` command ADR 0093's guard permits (`test_operator_commands_run_on_the_host.py:60-65`); a second checkout-only command would widen that allowlist. | **`bin/app-contract.sh` writes and checks TWO snapshots**: `contracts/app-openapi.canonical.json` (unchanged: `auth` + `storage`) and **`contracts/control-openapi.canonical.json`** (`create_app("control").openapi()`, the `/v1` paths only, title *"Agentic Postgres management API"*). `--update` gains `--snapshot app\|control` (default `app`, so every existing caller is unchanged); `--check` checks both. `test_app_contract_aggregate.py` gains the control half. **No new command.** | One reader of the service's surface, one allowlist entry, one place the gate already calls (`session-36-check.sh:1322`). | **0253** |
| **D2058** | Stage plan §7: *"a proof that a customer can do something runs in external mode **with no SSH destination** (the absence asserted by the proof)"*. | The gate's external mode REQUIRES `--ssh-destination` (`session-36-check.sh:1679-1680`) because two Session 4 proofs need it (`test_session4_public_transports.py:193`, `:241`); asserting the variable unset would skip them and move `port_allocation`-class claims to `not_run`. | **The customer proofs prove they never USE the SSH path, statically and at run time**: the new external module reads only `APG_CONTROL_OUTPUTS`'s `routes.control` and `APG_CONTROL_PROBE_FILE`; `test_session37_customer_proofs_reach_only_the_public_endpoint` (offline) AST-scans `tests/external/test_session37_control.py` for any `APG_SSH_DESTINATION`, `ssh`, `subprocess` naming `ssh`, or a URL not derived from `routes.control`, and fails on one; at run time each proof asserts every request it made went to `routes.control`'s host over https (a recording opener). The gate keeps `--ssh-destination` for Session 4's proofs. | The property the stage plan wants is *the customer's door*, which a scan and a recorded host prove; an unset variable would prove only that a different proof did not run. | 0246 |
| **D2059** | §5: *"serving `/api/v1` behind the control project's router"*. | The app router strips `/api/app` and forwards any path below it (`runtime_override.py:1292-1309`), so a `/v1/organizations` route in the container is ALSO reachable as `/api/app/v1/organizations` — the same handler, a second address. | **The control project's app router rule gains `&& !PathPrefix(`{api}/app/v1`)`**, rendered only where the facility is on; **a new router `apg-<key>-control`** (`naming.control_router_name`, `control_stripprefix_middleware_name`) with ``Host(…) && PathPrefix(`{api}/v1`)`` and a strip of `{api}` (so the app sees `/v1/…`), the baseline chain and the buffering middleware the app router uses. **Rig 37d measures Traefik v3.7's negation** with the pinned image: `/api/app/v1/x` → Traefik's 404 with the negation, the backend's answer without it (the control). | A second address for the management API is one more thing a reviewer must notice; Traefik v3 supports `!` in rules, but a rule is a third-party claim (D267). | **0251** |
| **D2060** | Session 36's D1993: *"`provision-host.sh` installed and enabled `agentic-postgres-project@<key>.service`"*. | **`provision-host.sh` enables no project unit** (`:845-850`: *"The edge and project units are NOT enabled … Run 6 starts them"*), no other command enables one (grep of `bin/`, `libexec/`, `src/`, `deploy.sh`), and no document shows the command. Alpha's and beta's units read `enabled` (Session 36's E0) — enabled by hand at some point nothing records. | **Sheet E0 reads `systemctl is-enabled` for both units and `grep -rn "systemctl enable" docs/plans/session-0[2-9]*.md docs/plans/session-1[0-7]*.md`** for where it happened; **Sheet C5 enables `agentic-postgres-project@control-prod.service`** (no `--now`: the deploy already runs it), and the reboot on day 2 is its proof (§2 `CTL-REG-002`'s node *the unit is enabled and every container came back*). Run 9 corrects `docs/operator-guide.md` §3 and `docs/fleet-operations.md` §6 with the line, and Session 36's D1993 is corrected by this row (its plan is history and is not edited). | A project that does not come back after a reboot is the control plane's single point of failure failing silently the first night. | — |
| **D2061** | `docs/operator-guide.md:192-194` and `docs/fleet-operations.md:150-151`: *"`--apply` … shreds the credential file"*. | **The code does not shred it**: the only `unlink`s are in `--destroy` (`bin/bootstrap-providers.py:1055`, `:1057`); `docs/provider-bootstrap.md:99-109` tells the operator to `sudo shred -u` by hand and to look for an editor's `.save` copy. | **Sheet P2 shreds by hand** (`sudo shred -u <file>` and `sudo ls -la /root/.config/agentic-postgres/bootstrap/` reading empty); **Run 9 corrects the two sentences** to say the operator shreds it (provider-bootstrap.md's wording). The code is not changed. | A guide that says a credential is gone when it is not is the worst direction for a sentence to be wrong (D930). | 0110 |
| **D2062** | — | `test_every_permanent_project_is_scheduled` (`tests/deployment/test_session17_fleet.py:176-180`) requires every permanent project in the fleet inventory to read backups `SCHEDULED`; `fleet.sh` finds `control-prod` by itself (`bin/fleet.py:78-82`). `schedule enable` refuses until a full backup exists (`bin/backup.py:552-633`). | **Sheet C6 takes the control project's first full backup and enables its schedule (with the mirror's third timer) on day 1**, before any sweep. | Otherwise the sweep turns `FLEET-BACKUP-001` red with a correct verdict about a defect the plan created. | 0188 |
| **D2063** | Stage plan §7 item 3: *"Every new deployed-document field is classified in the isolation matrix in the session that adds it"*; §8: *"Projects share no project-scoped value"*. | Offline, `evidence.collision_count` compares ALL rendered pairs (`evidence.py:256-287`), so the control render on the host is in the gate's collision count by construction. Live, the isolation matrix compares A and B only (`tests/deployment/conftest.py:123-136`; `test_session12_isolation_matrix.py:305-435`). | **`routes.control` is classified** (derived from the domain, so in `MUST_DIFFER` by the domain's row — `test_render_isolation.py:58+` is read and the field added if the matrix lists routes). **A new host proof** in `tests/deployment/test_session37_control.py` reads `APG_CONTROL_OUTPUTS` with A's and B's documents and asserts every `evidence.ISOLATED_FIELDS` pointer differs pairwise (A–C, B–C), the role names disjoint. | The third project is the first one that will hold strangers' data about other projects; its isolation is read, not inferred from A–B. | 0002 |
| **D2064** | — | ACME was promoted to PRODUCTION in Session 2 (`bin/edge.sh:295-333` refuses a second promotion); a new hostname's first certificate is a production HTTP-01 issuance with no staging dry run (D33's warning), and failed validations are limited to 5 per hour per hostname. | **Sheet C1 checks the record before the first deploy**: `dig +short control.agenticpostgresql.com @1.1.1.1` must print `62.238.99.122` (grey cloud: a proxied record prints a Cloudflare address), and `curl -sS -o /dev/null -w '%{http_code}' http://control.agenticpostgresql.com/` must reach the edge (a `404` from Traefik is success). **One deploy attempt; a certificate failure is a stop** — no retry until an hour has passed and the cause is read from `apg-diag edge-log`. | Five failures an hour is a budget the plan spends at most once. | — |
| **D2065** | ADR 0246 / D1986: humans are never pruned; scope-closure §29 item 2: *"the identity questions this session parked"*. | Every live run of an invitation proof creates an account. `/admin/users` is not served in `control` mode (D2043), so nothing disables one through a route. | **Session 37 adds no account deletion and no account pruning.** Probe accounts are named `probe-s37-<8 hex>` and the probe's memberships are removed at the end of each proof (the membership is the authority; the account then reaches nothing but `/v1/me`). `docs/control-plane.md` says accounts accumulate and the operator can disable one with the control project's own admin path (Run 1's 37e names it: `bin/auth-admin.sh` verbs, read with `--help`). **Answering D1986 is deferred again** with its cost written in §10. | Deleting an identity is a question about the audit, the sessions and the memberships it joins, and none of those is this session's subject. | 0252 |
| **D2066** | D1952: *"a context file `~/.config/apg/context.json`, 0600, holding the endpoint and a key reference, never a database credential"*. | No context file exists anywhere; `test_cli_contract.py:1100-1113` forbids a `--password`, `--token`, `--api-key` flag in any `--help`; studio's precedent reads a password from a 0600 file whose mode it checks, or a TTY (`bin/studio.py:233-265`). A password login yields a 900-s access token and a 30-day refresh token. | **The CLI's state is `${XDG_CONFIG_HOME:-$HOME/.config}/apg/`**, created 0700 (refused if a symlink, another owner's, or wider), holding `context.json` (0600: `endpoint`, `organization`, `project`, and EITHER `key_file` — the PATH of a 0600 key file, never the key — OR `session: true`) and, for a password login only, `session.json` (0600: the refresh token and its expiry; the access token is never written). Writes are `O_WRONLY\|O_CREAT\|O_TRUNC\|O_NOFOLLOW` to a temporary name then `os.replace`. **Secrets enter only through a 0600 file whose mode is checked (`--password-file`, `--key-file`, `--invitation-file`) or a TTY (`getpass`)**; the TOTP code through `--totp-code-stdin` or a TTY. **https only**, except `http://127.0.0.1`/`localhost` for the tests. `apg logout` revokes the session server-side (`DELETE /v1/sessions/current`) and removes `session.json`; a key context is forgotten, never revoked (`apg org key-revoke` does that). | A refresh token on disk is the standard CLI trade (it is not a database credential, and it is revocable); a key by reference keeps one copy of the key, where the person put it. | **0253** |
| **D2067** | §5: *"`apg project list\|use\|status`"*, *"`operations` (get/list/cancel while `pending`)"*, *"`ledger`"*, the `regions` and `notifications` tables. | A project's resource STATE is derived from the operation history, the deployed document and the doctor (D1953) — Session 38's; nothing can be `pending` (D2054), so nothing can be cancelled; the Ledger's only reader is the console (42), and the ledger file is not in the auth image. | **Not built in 37**: `apg project status` → **`apg project show`** (the registry record, no state); `POST /v1/operations/{id}/cancel` → 38; `GET /v1/ledger` → 42 (with the console that reads it); the two tables → 38 and 41 (D2047); **`apg project create`** — no CLI for a refusal. | Each is a surface with no subject yet; building it would be D709's free property priced as work, or a control on a planned row. | 0254 |
| **D2068** | §5: *"The `projects` registry seeded from the host's deployed documents by an operator verb (`apg control adopt --project KEY`, root) for alpha, beta and the control project itself, and reported against them with three outcomes."* | `/v1/projects` lists a caller's organisations' projects, so an adopted project needs an organisation. `container_exec.run` is the rule for new code that execs into a container (ADR 0218); `bin/record.py` is the closest sibling (root, a key resolved to the deployed document through `deployed_output.read_deployed_document`, `psql -v` variables, exit codes 0/2/3/5/6). | **`bin/control.sh` (root)**: `adopt --project KEY --organization ORG_ID --confirm control-prod` reads KEY's deployed document and writes `app.control_projects` through `app.control_adopt_project(...)` (a definer function **granted to nobody**, called by `docker exec … psql -U postgres` into the control project's database through `container_exec.run`, the arguments as `psql -v` variables); `registry [--json]` compares every registry row with its deployed document (`slug`, `environment`, `domain`, `template_version`, `source_commit`) and every deployed document with a row: **`agrees`, `differs: <field>`, or `could not determine: <reason>`** per project (exit 0 all agree, 5 a difference, 6 any undetermined — ADR 0195); `totp-reset --username NAME --confirm control-prod` disables one factor (D2050). The control project is found by its manifest's facility in the deployed document (`control.enabled`), never by name. **ADR 0185 is superseded FOR THE CONTROL PLANE by the registry, kept for everything else** (`fleet.sh` stays a read). | The registry is the control plane's own record, written by the person who holds root; a route that let a customer adopt a project would be a control plane deciding what exists. | **0251**, 0185, 0218 |
| **D2069** | Stage plan §10: *"the node-loss runbook must restore it **first** (42)"*. | `dr-kit.sh export` takes one `--project` per project and enumerates nothing (`bin/dr-kit.py:205`); the documented command names alpha and beta (`docs/recovery-operations.md:63-65`). | **From Session 37 every kit names three projects**: Sheet K1 exports with `--project /home/op/control.yaml` added; Run 9 adds it to the documented command. **The runbook's restore ORDER stays Session 42's**, with one sentence now: *"the kit carries the control project; restore it like any project"*. | A kit without the single point of failure would be the first thing a node loss discovers. | 0189 |
| **D2070** | Stage plan §2.2: *"Session 37 adds a project (the control plane — no release change by itself)"*. | 37 changes the release: a manifest schema (9, migratable), an outputs schema (20), `compose.yaml`'s `APP_MODE` interpolation (which moves alpha's and beta's `auth` definition, so their `auth` is recreated on deploy — D2034 says a new commit recreates it anyway), the image's code. No released migration. | **`1.15.0`, predicted minor**: Run 9 runs `upgrade plan` offline (a worktree at `2538ac0` against this tree, as Session 36's Run 8 did) and Sheet R1 on the host; the release paragraph quotes the class read. **A `major` is a stop** (§9). | The version is read, never chosen (D704). | 0162 |
| **D2071** | — | The control project's key, domain and backup mirror are the operator's. | **The operator's answers of 2026-10-04**: key **`control-prod`** (slug `control`, environment `prod`; roles `apg_control_prod_*`, Compose project `apg-control-prod`, buckets `apg-control-prod`, `apg-control-prod-backup`, the mirror `apg-control-prod-backup-mirror`, Infisical project `control-prod`); domain **`control.agenticpostgresql.com`** (`/api/v1` at `https://control.agenticpostgresql.com/api/v1`); **a B2 mirror** like alpha's and beta's. Manifest at `/home/op/control.yaml` (never in the checkout, D971; `.gitignore:46-50` would now ignore `project.control.yaml` too, but the stage plan's path stands). | Recorded, not argued. | — |
| **D2072** | — | `port_allocation` passes only on a sweep declaring `--after-reboot` (`test_session4_convergence.py:361-445`), and the rotation trio only with the four `--rotated-*` files (Session 36's S1); without them they read `not_run` and the merge exits 5 for a reason the plan did not name. The files are root 0600 on the host (`/root/s36-prev-*`, `/home/op/s30-retired-alpha-dev-jwk.json`), and a previous value stays refused until the next rotation. | **Sitting 2 reboots before the sweep** (Sheet B1) — which is also D2060's proof that `control-prod` comes back — and **`s37-sweep.sh` is derived from `s36-sweep.sh` by diff**, keeping every declaration Session 36's S1 made (`--after-reboot`, the four `--rotated-*`, `--redeploy-before-file`, `--replacement-bootstrap-state`, `--kit-dir /home/op/kit-2026-09-11`) and adding `--control-outputs`. E0 lists each file. | Two claims that passed are kept passing by declaring what is still true, read again by the proofs; letting them lapse would be a regression produced by omission (D2006's shape). | — |

**Rows the runs add** (D2073 onward), in execution order:

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

**Two new families, `CTL` and `KEY`**: the regex at
`tests/contract/test_acceptance_registry.py:111` gains `CTL` and `KEY`, and the
family comments (`:50-110`) gain one sentence: *Session 37 (ADR 0251-0254)
adds `CTL` for the control plane — the control project, its accounts,
organisations, invitations, TOTP, registry, operations and CLI — and `KEY` for
management API keys.* **Thirteen requirements, thirteen claims, all
`target_session: 37`, all P0 — nine offline, three external, one host.** Every
requirement belongs to a claim (D697); a new requirement gets a claim of its
own (ADR 0089). **Node ids below are proposed; Run 9 writes what the runs
actually wrote, read out of the tree with `pytest --collect-only -q`** (D1236,
D1762). Registry entries are committed by Run 9 with the constant (D690), in a
block under **`# Session 37 (ADR 0251-0254)`**.

| Requirement | What it states | Offline node ids (proposed) | Live half |
|---|---|---|---|
| `CTL-SET-001` | The control set (`projects/control/`) passes the lint with the `control` facility and is refused it without; the lint refuses `{{auth_service}}` in any set without the facility and anywhere but a function grant with it; every control table is in `app` with FORCE RLS; no control function is in `api` or executable by `anon`, `authenticated`, `agent_reader`, `agent_writer`, `api_documentation` or `PUBLIC`; every `app.control_*` function is executable by `auth_service` except `app.control_adopt_project` and `app.control_totp_reset` (nobody); a caller sees only their own organisations' rows; a non-member sees nothing | `tests/contract/test_control_set.py::test_the_set_lints_only_with_the_control_facility`, `::test_auth_service_is_refused_outside_a_function_grant`, `::test_every_control_table_forces_row_level_security`, `::test_no_request_role_can_execute_a_control_function`, `::test_the_operator_functions_are_executable_by_no_role`, `::test_a_caller_sees_only_their_own_organisations`, `::test_a_non_member_sees_nothing`, `tests/contract/test_project_migration_sets.py::test_the_lint_refuses_auth_service_without_the_control_facility` | — (offline claim `control_set`) |
| `CTL-TOTP-001` | `totp.py` reproduces RFC 4226 Appendix D and RFC 6238 Appendix B (SHA-1); accepts the current step and ±1, refuses ±2; refuses a code at or below the last accepted step; the enrolment URI is shown once and the seed never logged; login with an enabled factor requires the code; confirming a factor revokes every session; an owner or admin without a factor reaches only `/v1/me`, `/v1/me/totp*` and `/v1/sessions*` | `tests/contract/test_totp.py::test_rfc_4226_vectors`, `::test_rfc_6238_vectors`, `::test_the_window_is_one_step`, `::test_a_replayed_step_is_refused`, `tests/contract/test_control_sessions.py::test_login_requires_the_code_once_enabled`, `::test_confirming_a_factor_revokes_every_session`, `::test_an_owner_without_a_factor_reaches_only_enrolment`, `::test_no_seed_reaches_a_log_line` | — (offline claim `control_totp`) |
| `CTL-INV-001` | An invitation token is shown once and stored as its SHA-256; an account invitation needs `admin_users:write` and an enabled factor; a membership invitation needs `owner`/`admin` of that organisation for a role at or below the minter's; acceptance creates the account and the membership in one transaction (a failure in the second leaves no account); exactly one of two concurrent acceptances succeeds; a used, expired, revoked and unknown token get byte-identical answers; a taken username leaves the token unspent | `tests/contract/test_control_invitations.py::test_a_token_is_shown_once_and_stored_hashed`, `::test_an_account_invitation_needs_the_registry_administrator_with_a_factor`, `::test_a_membership_invitation_is_bounded_by_the_minters_role`, `::test_acceptance_is_one_transaction`, `::test_one_of_two_concurrent_acceptances_succeeds`, `::test_every_invalid_token_gets_the_same_answer`, `::test_a_taken_username_leaves_the_token_unspent` | — (offline claim `control_invitations`) |
| `CTL-ROLE-001` | Every `/v1` route × every role answers as the role matrix says; the last owner cannot be removed or demoted; an admin cannot grant `owner`; a foreign organisation's id and a missing one return the same `404` | `tests/contract/test_control_roles.py::test_every_route_and_role_answers_as_the_matrix_says`, `::test_the_last_owner_stays`, `::test_an_admin_cannot_make_an_owner`, `::test_a_foreign_id_and_a_missing_id_look_the_same` | — (offline claim `control_roles`) |
| `KEY-MINT-001` | A key is `apg_<16 hex>_<43>`, shown once, stored as `key_id` + SHA-256; its scopes are a subset of the 37 vocabulary and of the minter's role; a key cannot mint a key, an invitation or a factor (`human_session_required`); effective scopes are the key's ∩ the owner's current role; a revoked key, and a key whose owner left, are refused on the next request; a key of organisation A gets `404` on B's resources | `tests/contract/test_control_keys.py::test_a_key_is_shown_once_and_stored_hashed`, `::test_scopes_are_bounded_by_the_vocabulary_and_the_role`, `::test_a_key_mints_nothing`, `::test_a_demotion_narrows_a_key`, `::test_a_revoked_key_and_a_departed_owners_key_are_refused`, `::test_a_key_reaches_no_other_organisation` | — (offline claim `control_keys`) |
| `CTL-API-001` | `create_app("control")` serves exactly the health routes, the named probes and the `/v1` paths of `contracts/control-openapi.canonical.json`, and `bin/app-contract.sh --check` compares both snapshots; `auth` mode serves no `/v1` path; no `/v1` handler holds or reads a credential of another project (no outputs document, no project URL, no `*_password` secret is read in `control` mode) | `tests/contract/test_auth_service_shape.py::test_the_control_mode_serves_exactly_the_declared_paths`, `::test_the_auth_mode_serves_no_management_path`, `tests/contract/test_app_contract_aggregate.py::test_the_control_snapshot_is_what_this_checkout_generates`, `tests/contract/test_control_boundary.py::test_the_control_mode_reads_no_other_projects_credential` | — (offline claim `control_api_contract`) |
| `CTL-OPS-001` | `operations.py`'s type table is closed and every type names an existing Ledger row; a type is accepted iff its row is `available` or `beta`; no type is accepted at Session 37; `POST /v1/projects` answers `409 not_available` naming `projects_self_service` and writes no row | `tests/contract/test_reality_ledger.py::test_every_operation_type_names_a_ledger_row_and_none_is_accepted_while_planned`, `tests/contract/test_operation_types.py::test_the_type_table_is_closed`, `::test_project_creation_is_refused_as_not_available` | — (offline claim `operation_types`) |
| `CTL-REG-001` | `bin/control.sh adopt` refuses without root, without `--confirm control-prod`, with a key that has no deployed document, or when no deployed document enables the control facility; `registry` reports `agrees`, `differs: <field>` or `could not determine` per project and exits 0/5/6 accordingly; `totp-reset` requires the confirmation; every exec goes through `container_exec.run` | `tests/contract/test_control_command.py::test_adopt_requires_root_and_a_confirmation`, `::test_the_control_project_is_found_by_its_facility`, `::test_registry_reports_three_outcomes`, `::test_an_unreadable_document_is_undetermined_not_agreeing`, `::test_totp_reset_requires_the_confirmation` | — (offline claim `control_registry_command`) |
| `CTL-CLI-001` | `bin/login.sh`, `logout.sh`, `context.sh`, `org.sh`, `project.sh` keep their state in a 0700 directory of 0600 files, refuse a symlink or a wider mode, read a secret only from a checked 0600 file or a TTY, never put a secret in argv, `--help` or a log line, refuse plain http except loopback, and exit 0/2/3/5/6 per the runbook | `tests/contract/test_control_cli.py::test_the_state_directory_is_private`, `::test_a_symlinked_or_wide_file_is_refused`, `::test_a_secret_is_read_only_from_a_private_file_or_a_tty`, `::test_plain_http_is_refused_except_loopback`, `::test_logout_revokes_the_session`, `::test_project_list_reads_the_endpoint_from_the_context` | — (offline claim `control_cli`) |
| `CTL-INV-002` | On the deployment, through `routes.control` only: a membership invitation minted by the probe owner is accepted once; a second acceptance and an unknown token get the same answer | — | `tests/external/test_session37_control.py::test_an_invitation_is_accepted_once` (external claim `control_invitations_live`) |
| `CTL-TOTP-002` | On the deployment: the probe owner's login without the code, with a wrong code and with a replayed code is refused; with the current code it is served | — | `tests/external/test_session37_control.py::test_login_enforces_the_second_factor` (external claim `control_totp_live`) |
| `KEY-USE-001` | On the deployment: a member's key lists the organisation's projects through `bin/project.sh list`; the same key is refused by alpha's `/api/app/auth/me` and `/api/rest/`; after the owner removes the member, the key is refused on its next request while a sibling member's key is served | — | `tests/external/test_session37_control.py::test_a_key_lists_projects_and_opens_no_project`, `::test_a_departed_members_key_stops` (external claim `control_keys_live`) |
| `CTL-REG-002` | On the deployment: `bin/control.sh registry` reads `agrees` for alpha, beta and the control project; the control project's document shares no `ISOLATED_FIELDS` value with A's or B's; its `auth` container serves no `/auth/login` and no `/admin/users`; its project unit is enabled and every container came back after the reboot | — | `tests/deployment/test_session37_control.py::test_the_registry_agrees_with_every_deployed_document`, `::test_the_control_project_is_isolated_from_both`, `::test_the_control_mode_serves_no_release_admin_route`, `::test_the_control_project_survives_a_reboot` (host claim `control_plane_live`) |

**Expected counts** — Run 9 counts them from the tuples, never from this prose
(D1628): requirements **299 → 312**, `CLAIMS` **206 → 219**,
`OFFLINE_CLAIMS` **65 → 74**, ADRs **250 → 254**.

**Claims** (`src/agentic_postgres/evidence_claims.py` `CLAIMS`, in a block
commented *Session 37 (ADR 0251-0254)*): offline — `control_set:
("CTL-SET-001",)`, `control_totp: ("CTL-TOTP-001",)`, `control_invitations:
("CTL-INV-001",)`, `control_roles: ("CTL-ROLE-001",)`, `control_keys:
("KEY-MINT-001",)`, `control_api_contract: ("CTL-API-001",)`, `operation_types:
("CTL-OPS-001",)`, `control_registry_command: ("CTL-REG-001",)`, `control_cli:
("CTL-CLI-001",)` — **these nine in `OFFLINE_CLAIMS`**, with the per-session
assertion in `test_session_thirty_seven_gate_modes.py` (D1237: assert THESE are
in the set, never the set's size). External — `control_invitations_live:
("CTL-INV-002",)`, `control_totp_live: ("CTL-TOTP-002",)`, `control_keys_live:
("KEY-USE-001",)`, each carrying the `external` marker (`evidence_claims.py:53`).
Host — `control_plane_live: ("CTL-REG-002",)`. `CLAIM_INTRODUCED_IN`
(`tests/contract/test_evidence_claims.py:953`) gains a row at 37 for each.

**Existing entries that move** (each a passing proof made stricter or a
sentence corrected, never weakened — CLAUDE.md §6):

- **`LEDGER-001`**: its node id `test_the_sets_the_guard_will_read_are_empty_today`
  (`acceptance-registry.yaml:6077`) is REPLACED by
  `test_no_console_exists_yet` (the console half, unchanged in substance);
  the operations half becomes `CTL-OPS-001`'s first node id (D2054).
- **`test_auth_service_shape.py::test_the_application_serves_exactly_the_declared_paths`**
  keeps its `auth` and `storage` cases; the `control` case is a new node id
  (above).
- **`THR-*` table rows**: five added in Run 9 (D2056); none removed.
- **`port_allocation`, the rotation trio**: no entry moves — the sweep
  re-declares them (D2072).

**New environment gates: two**, in `tests/conftest.py`'s roster (`:86-189`):
`APG_CONTROL_OUTPUTS` (the op-readable copy of `control-prod`'s deployed
document; host and external) and `APG_CONTROL_PROBE_FILE` (the probe owner's
0600 credential file on the workstation: username, password-file path, TOTP
seed, organisation id; external only). **The Session 37 gate therefore accepts
exactly the Session 36 gate's flags plus `--control-outputs FILE` and
`--control-probe-file FILE`** — the derivation diff proves it (D1133), and
`test_session_thirty_seven_gate_modes.py`'s one-usage-entry-per-flag guard
(`:966-999` in 36's) reads both.

---

## 4. Irreversible operations

| Operation | Where | What makes it safe |
|---|---|---|
| The control set's three migrations frozen into `projects/control/migrations/released.lock.json` | Run 3 | `bin/migrate.sh --project <manifest> freeze-lock` is the only writer; the proofs apply the release set then the control set as `migration_user` on a fresh container before the freeze; each down is `AP900`; once applied on the host they are the control project's floor; **no released (platform) migration is added or amended** (D912) |
| `CURRENT_SESSION` 36 → 37; `VERSION` 1.14.0 → 1.15.0 | Run 9 | All-or-nothing (D690); every `target_session: 37` entry in the same commit; the upgrade guide gains a `1.15.0` row; `README.md:7` moves; every `--session 36` / `--through-session 36` literal on the documented path moved and counted per file (D678/D1484) |
| `bin/session-37-check.sh` | Run 9 | Derived from 36's by diff (D1482); header and usage rewritten whole (D1488); exactly two flags added (§2); `SHELL_COMMANDS` gains it and `chmod 755` before `git add` (D1014, D1188) |
| **Provider resources for `control-prod`** (an Infisical project and identity, two R2 buckets and tokens, a B2 bucket and key pair, a DNS record) | Sheets P1–P2 | Made by hand and by `bootstrap-providers.sh --apply` exactly as `gamma-dev` was (`docs/fleet-operations.md` §6); nothing in the repository creates or deletes a bucket (ADR 0110); `--plan` read before `--apply`; the operator credential shredded after (D2061) |
| **A production certificate for `control.agenticpostgresql.com`** | Sheet C1 | The DNS record read first (D2064); one attempt; a failure is a stop |
| Deploy `--through-session 37` on alpha, then beta | Sheets R2a/R2b | `upgrade plan` read first (R1); alpha first; under `script(1)`; auth/mcp/storage recreated ~8–14 s each (D2034), the probe running |
| **`control-prod` deployed** (three passes), its first administrator created, its unit enabled, its first full backup taken and scheduled | Sheets C1–C6 | Admission read first (E0, then step 0); the administrator's password typed by the operator and stored root-only (`/root/control-prod-administrator`, 0600) — `AP409` forbids a second bootstrap; nothing in alpha or beta changes |
| **The first accounts and organisation** | Sheets W1–W3 | Created through `/v1` by the operator at the workstation; an account cannot be deleted in 37 (D2065), so the usernames are chosen on the sheet before the first is created |
| Projects adopted into the registry | Sheet A1 | Root, `--confirm control-prod`; a row removed only by a root `psql` DELETE (§10) |
| The reboot | Sheet B1 | After A1's registry reads `agrees`; the three units read `active` before the sweep |
| Tag `1.15.0` on the deployed commit | Run 11 | After the merge exits 0 or 5 for the expected reasons only (§7); from the WORKSTATION (D2041) |

---

## 5. Build order, run by run

Each run ends with a `**Done.**` paragraph written by the executor: what was
measured, the numbers, the rows it added, and — for a code run — the CI verdict
by full SHA. A run that changes code pushes and reads CI; the targeted modules
run ONCE at the run's close and only the failing module is re-run (the user has
asked thirteen times). `ruff format && ruff check` before every commit;
`chmod 755 bin/*.sh bin/*.py deploy.sh` before every `git add`; commit messages
from a file with `-F`, ending with the attribution line the session's system
reminder gives. **Grep the plans for every third party before measuring it**
(`grep -rn -i '<term>' docs/plans/*.md docs/decisions/*.md`). **A run that
renames, adds or removes a test function runs `test_acceptance_registry` and
`test_evidence_claims`** (D1119, D1674); **a run that adds a `GRANT` ships its
caller in the same commit** (D1680 — the control set's grants to
`auth_service` land in Run 3 with a test that calls each, and their service
callers in Runs 4–5; Run 3's test is the caller until then, and the commit
message says so); **a run that changes rendering re-renders BOTH example
projects** before its targeted list (D1678: `./deploy.sh --project
project.example.yaml --capabilities capabilities.example.yaml --render-only` and
the same for `project.second.example.yaml`; delete what each render publishes
under `.generated/` afterwards, CLAUDE.md §1 — **except** the two fixture
renders the gate and `generate` read, D1507: leave `.generated/fixture-alpha-dev`
and `.generated/fixture-alpine-dev` current); **a run that adds or removes a
`bin/` command runs `test_cli_contract` and `git add`s the command first**
(D1014, D1188); **a run that touches a documentation page runs
`test_documentation_index` and `test_session12_documented_path`**; **every new
test module carries `pytestmark` before its first test** (D1240) and the
sweep-selector guard (D1242) is in the targeted list of any run that adds one.

**The Docker-backed modules are the slow ones** (~3 min each:
`test_auth_endpoints`, `test_migrations_apply_as_the_migration_user`,
`test_agent_audit_plane`, and this session's `test_control_set`,
`test_control_sessions`, `test_control_invitations`, `test_control_roles`,
`test_control_keys`, `test_control_cli`). Keep two lists per run: the fast
modules after each edit, the Docker-backed ones ONCE just before the commit.
**The Docker-backed control modules share ONE cluster fixture** written in Run
3 (`tests/contract/control_cluster.py`, imported by each module's
`conftest`-free fixture the way `test_auth_endpoints.py:119-271` builds its
own): a container from `POSTGRES_IMAGE`, the release set then the control set
applied from a render of `project.control.example.yaml` (Run 2), `auth_service`
given LOGIN and a password, a signing key, and the `drive` helper's shape
(`test_auth_endpoints.py:371-414`: `create_app("control")`, its
`lifespan_context`, `httpx.AsyncClient(transport=httpx.ASGITransport(...))`).

### Run 1 — the rigs, Sheet E0, the threat list, and ADRs 0251–0254

**Documentation only. Push, say it is pushed, read NO CI verdict** — except
that, because `docs/threat-model.md` and `docs/decisions/README.md` are parsed
by tests, run `python -m pytest tests/contract/test_acceptance_registry.py
tests/contract/test_documentation_index.py -q -p no:randomly` ONCE locally
before the push and fix what it names.

**Reads first** (agent, no edits): this plan's §0 and §1 whole;
`services/auth-api/app/main.py:90-540`; `settings.py:25-60`, `:360-570`;
`service.py:180-500`, `:840-1040`; `one_time_tokens.py` whole;
`hashing.py:235-401`; `profile.py:90-140`; `claims.py:40-175`;
`repository.py:1-145`, `:480-510`; `errors.py` whole; `routes.py:490-560`,
`:610-720`; `scopes.py:55-240`; `migrations/templates/0011-identity-registry.sql:
100-265`; `0012-auth-access-plane.sql:160-430`;
`0026-password-reset-plane.sql:80-250`; `0003-owner-scoped-tables-and-forced-rls.sql`
whole; `src/agentic_postgres/migrations.py:70-200`, `:740-940`;
`src/agentic_postgres/naming.py:100-140`, `:280-480`, `:880-925`,
`:1080-1190`; `src/agentic_postgres/runtime_override.py:1170-1320`;
`src/agentic_postgres/rendering.py:425-470`, `:950-1045`, `:1900-1960`,
`:2500-2530`; `compose.yaml:1190-1320`; `schemas/project.schema.json:1-130`,
`:590-1000`; `bin/deploy-project.py:1495-1545`, `:2120-2200`;
`bin/auth-admin.sh --help` and `bin/auth-admin.py:100-370`;
`bin/bootstrap-providers.py:220-245`, `:870-1015`;
`docs/fleet-operations.md:133-188`; `docs/operator-guide.md:129-251`;
`docs/provider-bootstrap.md:60-160`; `docs/decisions/0185-*.md`, `0198-*.md`,
`0201-*.md`, `0218-*.md`, `0246-*.md`, `0247-*.md`; `docs/reality-ledger.yaml:
1-115`, `:130-160`, `:470-510`; `docs/threat-model.md` whole;
`tests/contract/test_reality_ledger.py` whole;
`docs/plans/session-17-implementation-plan.md:140-200`, `:400-460` (the only
third-project trip); `docs/plans/stage-5-plan.md` rows D1950–D1953.

**The rigs.** Each is a script written with the Write tool to
`\\wsl$\Ubuntu\tmp\rig37\rig37x.py` (or `.sh`/`.sql`) and copied to the
scratchpad's `rig37/`; each names its image by digest (`versions.env`); each
has a control; each prints its own exit status from inside. Any Python that
imports `agentic_postgres` needs `PYTHONPATH=src`; any that imports the
service needs `PYTHONPATH=src:services/auth-api`. **A heredoc inside `wsl bash
-lc "…"` is forbidden (CLAUDE.md §1)** — every SQL body is a file the script
reads.

- **37a — TOTP against the RFCs.** A scratch `totp.py` (the Run 4 module's
  draft): `hotp(key: bytes, counter: int, digits: int) -> str` (RFC 4226 §5.3:
  HMAC-SHA-1 over the 8-byte big-endian counter, dynamic truncation, `% 10**digits`,
  zero-padded) and `totp(key, unix_time, step=30, digits=6, t0=0)`. **Measure**:
  (i) RFC 4226 Appendix D, key `b"12345678901234567890"`, counters 0–9 →
  `755224 287082 359152 969429 338314 254676 287922 162583 399871 520489`;
  (ii) RFC 6238 Appendix B, SHA-1, 8 digits, the same key: T = 59 →
  `94287082`, 1111111109 → `07081804`, 1111111111 → `14050471`, 1234567890 →
  `89005924`, 2000000000 → `69279037`, 20000000000 → `65353130`; (iii) a
  `verify(key, code, now, last_step, window=1)` returning the matched step or
  `None`: the code for `now` accepted, for `now ± 30` accepted, for `now ± 60`
  refused (**the control**: a wrong-step code refused); the same code twice
  with `last_step` updated → the second refused; (iv) `base64.b32encode(seed)`
  without `=` padding round-trips through `b32decode` with the padding restored.
  If `oathtool` exists in WSL (`command -v oathtool`), cross-check three
  random seeds × three times against it; if not, say so — the RFC vectors are
  the independent implementation.
- **37b — the control set's RLS under FORCE.** `apg dev up --project
  project.second.example.yaml` (the release's 39 migrations as the migration
  user, ~10 s; `bin/dev.py:403-429`); then, as the bootstrap superuser through
  `apg dev psql`, a scratch role `rig_auth` (LOGIN, standing in for
  `auth_service`) and the draft tables `app.control_accounts`,
  `app.control_organizations`, `app.control_memberships` with FORCE RLS,
  created under `SET ROLE <object_owner>`. **Measure**: (i) **the control** —
  a policy on `control_memberships` `USING (org_id IN (SELECT org_id FROM
  app.control_memberships WHERE user_id = app.current_user_id()))` → a SELECT
  through a definer function raises `infinite recursion detected in policy`
  (record the exact text and SQLSTATE); (ii) design **G** — memberships
  `USING (user_id = app.current_user_id() OR org_id::text =
  current_setting('app.control_org', true))`, organisations `USING (id IN
  (SELECT org_id FROM app.control_memberships WHERE user_id =
  app.current_user_id()))`, and a definer function `app.control_list_members(p_org
  uuid)` (owner-owned, `SET search_path = pg_catalog, pg_temp`) that first
  reads the caller's own membership row and only then
  `set_config('app.control_org', p_org::text, true)`: as `rig_auth` with
  `app.user_id` set to a member → the organisation's three members; to a
  non-member → zero rows and no GUC set; (iii) **whether `set_config(…, true)`
  inside a function that has its own `SET search_path` clause survives the
  function's return** for the rest of the transaction (read
  `current_setting('app.control_org', true)` after the call) — the answer
  decides whether G must scope the GUC inside each function; (iv) as the
  `authenticated` role (`SET ROLE`), `SELECT app.control_list_members(…)` →
  `permission denied for function` (no grant); (v) **single use under
  concurrency**: two `psql` sessions each `BEGIN; UPDATE
  app.control_invitations SET accepted_at = now() WHERE token_hash = 'x' AND
  accepted_at IS NULL RETURNING id;` — the second blocks until the first
  commits and then returns 0 rows. **Rule**: design G if (i) recurses and
  (ii)–(iv) hold; otherwise design T (owner-wide `USING (true)` policies,
  every scope check in the function bodies) and ADR 0251 says why.
- **37c — what a per-request key check costs.** In the dev venv (argon2-cffi
  25.1.0 locked in `requirements-dev.txt`), `app.hashing.Hasher` at
  `profile.FROZEN`: 20 `verify` calls of a 43-character secret → median and
  p95 ms and the process's peak RSS (`resource.getrusage`); the same 20 as
  `hmac.compare_digest(hashlib.sha256(s).hexdigest(), stored)` (**the
  control**). Record both and the CPU (`lscpu` model). The decision (D2052)
  stands on `HASH_CONCURRENCY = 2`; this rig puts a number beside it.
- **37d — Traefik's negated rule.** Grep the plans first (`grep -rn -i
  "traefik" docs/plans/*.md | grep -i "rig"` — Sessions 2, 5 and 35 ran
  Traefik rigs; reuse the closest one's shape). The pinned image
  (`versions.env`'s Traefik line, by digest) with a file provider and two
  backends (`python3 -m http.server` variants that echo the request path):
  router `app` ``Host(`rig.test`) && (Path(`/api/app`) || PathPrefix(`/api/app/`))
  && !PathPrefix(`/api/app/v1`)`` with a strip of `/api/app` → backend A;
  router `control` ``Host(`rig.test`) && PathPrefix(`/api/v1`)`` with a strip
  of `/api` → backend B. **Measure** with `curl -H 'Host: rig.test'`:
  `/api/app/auth/me` → A sees `/auth/me`; `/api/v1/organizations` → B sees
  `/v1/organizations`; `/api/app/v1/organizations` → Traefik's `404`.
  **Control**: without the `!PathPrefix` term, `/api/app/v1/organizations`
  reaches A as `/v1/organizations`. Record the rule strings exactly as
  measured — Run 2 renders them.
- **37e — the control project rendered, before any code.** A throwaway copy of
  the tree (`git worktree add /tmp/rig37e HEAD`), never the checkout. In it: a
  draft `projects/control/migrations/` (a `manifest.json` and ONE template
  creating `app.control_accounts` with FORCE RLS, `SET LOCAL ROLE
  {{object_owner}}`, an `AP900` down) **with no `contracts/` directory**, a
  frozen lock (`bin/migrate.sh --project <draft manifest> freeze-lock`), and a
  draft manifest at `/tmp/rig37e-control.yaml` (schema 8: slug `control`,
  environment `prod`, domain `control.agenticpostgresql.com`, `migrations.set:
  projects/control`, `api.rest.enabled: false`, `api.app.enabled: true`,
  `storage.enabled: false`, backup enabled with a mirror block copied from
  `project.example.yaml`'s shape, `lifecycle: {kind: permanent}`).
  **Measure**: (i) `./deploy.sh --project /tmp/rig37e-control.yaml
  --capabilities capabilities.example.yaml --render-only` — rc and, if it
  refuses, the exact message (D2048); (ii) the render's
  `secrets.required_names` — **is `r2_access_key_id` in it with storage
  disabled?** (D2049); (iii) `python - ` under
  `PYTHONPATH=src:services/auth-api` (as a FILE, not a heredoc): load the
  render's capability lock with `app.scope_map.load_vocabulary`, build an
  `AuthService`-equivalent `_check_scopes("api_documentation", ["meta:read"])`
  call (or call `scope_map.ceiling("api_documentation", vocabulary)` and test
  membership) — accepted or the exact refusal (D2049); (iv) read
  `bin/deploy-project.py`'s `observe_app` (`:1499-1545`) and
  `bin/doctor.py`'s app-route check (grep `auth/me\|jwks` in `bin/doctor.py`)
  and write down every path they request — those, plus health, are the
  `control` mode's probe routes (D2043); (v) grep the name and the grant of
  the session-revocation function (`grep -n "revoke_user_sessions"
  migrations/templates/*.sql`) — D2050's confirm calls it, and whether
  `auth_service` may execute it decides whether 0001 of the control set needs
  nothing or the repository reaches it another way; (vi) `bin/auth-admin.sh
  --help`: is there a verb to disable a user or reset a password (D2065)?
  Remove the worktree (`git worktree remove --force /tmp/rig37e`) and say so.

**Sheet E0 — readings before anything is built** (appendix; `sudo`, reads
only, one script that tees its own transcript to `/home/op/s37-e0.txt`). The
agent first writes `/home/op/s37-e0-control.yaml` over SSH as `op` (schema 8:
the 37e draft's values with the alpha manifest's `storage.account_id`,
`backup` and `backup.mirror` shape copied — read `/home/op/agentic-postgres/
project.alpha.yaml` for them — and NO `migrations` block, because the set does
not exist on the host yet; admission charges the database budget only), then
`/home/op/s37-e0.sh`, reads both back, and hands the sheet. It reads: (1)
`free -m`, `docker stats --no-stream --format '{{.Name}} {{.MemUsage}}'`,
`uptime -s`; (2) `systemctl is-enabled is-active
agentic-postgres-project@alpha-dev agentic-postgres-project@beta-dev
agentic-postgres-edge` (D2060); (3) `sudo bin/admit.sh --host host.yaml
--project /home/op/s37-e0-control.yaml` — exit 0 expected, committed 608,
requested 304 (D2042); (4) `ls -l` of every file Session 36's S1 declared
(`/root/s36-prev-*`, `/home/op/s30-retired-alpha-dev-jwk.json`,
`/root/s36-redeploy-before.json`, `/home/op/replacement-bootstrap-state.json`,
`/home/op/kit-2026-09-11`) and `/root/alpha-dev-administrator` (D2072); (5)
`ls -la /root/.config/agentic-postgres/bootstrap/` (expected: empty or absent
— the control-plane credential is placed on day 1, D2061); (6) the edge's ACME
environment (`sudo bin/edge.sh --host host.yaml status` or the line `--help`
names; D2064); (7) `getent hosts control.agenticpostgresql.com` (expected:
nothing yet, unless the operator already made the record). The agent ALSO
reads, without the operator: `grep -rn "systemctl enable
agentic-postgres-project" docs/plans/` (D2060).

**Then the documents.**

- **`docs/threat-model.md`**: the six list items naming Session 37 (`:176-194`,
  `:218-222`, `:237-240`) rewritten to name the control each owes BY ITS
  PROPOSED NODE ID from §2 (still a list, D1999; no `|` in any line), and one
  new item: **TOTP seed disclosure** (*a database dump or a backup read with
  the cipher pass reveals every enrolled seed; owed: seeds reachable only
  through definer functions granted to `auth_service`; residual: plaintext at
  rest, ADR 0252*).
- **ADR 0251** — *The control plane is a project: `control-prod`, its own set,
  and a fourth app mode of its `auth` container.* Decision: D2043 (the mode's
  exact route set, no worker), D2044 (manifest schema 9), D2045 (outputs 20,
  `routes.control`), D2046 (the lint widening, its one statement form), D2047
  (the tables, design G or T per 37b), D2048 (the contract per 37e), D2049
  (accounts as `api_documentation`/`meta:read`; REST and storage off), D2059
  (the control router and the negated app rule, quoting 37d), D2068 (the
  registry: ADR 0185 superseded FOR THE CONTROL PLANE ONLY; `bin/control.sh`).
  Alternatives rejected: a new `control` container (a second issuer or TOTP in
  every project's login); the control tables in `app_private` as release
  migrations (every project would carry the control plane's schema); routes
  in `auth` mode (every project would serve them). Consequences: the control
  project is the platform's single point of failure (stage plan §10); its
  kit, backup and schedule are owed from its first day (D2062, D2069).
- **ADR 0252** — *Accounts by invitation, organisations, roles and TOTP*
  (D2050, D2051, D2053, D2065), with the residual risk of plaintext seeds and
  the deferred account deletion.
- **ADR 0253** — *Management API keys, the `/v1` contract and the CLI's
  state* (D2052 with 37c's numbers, D2057, D2066).
- **ADR 0254** — *An operation type is accepted only when its Ledger row is
  `available` or `beta`; a row's status moves with its evidence* (D2054, D2055,
  D2067); **amends ADR 0247** (its file gains an *Amended by 0254* line and its
  index row `Accepted, amended by 0254` — check
  `test_the_index_status_agrees_with_each_adr`, D2010's lesson: the cell up to
  its first comma must equal the file's first status word).
- All four indexed in `docs/decisions/README.md` after 0250's row, ADR
  template as 0250's (`# NNNN — Title`, `- **Status:** Accepted`, `- **Date:**`,
  `- **Session:** 37, Run 1 (D…)`, `- **Affects:**`, `- **Related:**`, then
  `## Context`, `## Decision`, `## Alternatives rejected`, `## Consequences`).
  ADR 0185's index row becomes `Accepted, superseded in part by 0251` (and its
  file's status line the same).

**Done.** *(the executor writes it: each rig's numbers and its control, E0's
readings, the rows added from D2073)*

### Run 2 — the control facility rendered: manifest 9, outputs 20, the router, the lint

**Code. Push and read CI by full SHA.**

**Reads first**: Run 1's Done (37d's rule strings, 37e's answers);
`schemas/project.schema.json:16-28`, `:593-615`, `:950-1000`;
`src/agentic_postgres/config.py:60-95`, `:1170-1260`;
`src/agentic_postgres/naming.py:100-140`, `:385-480`, `:1080-1190`;
`src/agentic_postgres/runtime_override.py:1170-1320` and every caller of
`_app_labels` (grep); `src/agentic_postgres/rendering.py:425-470`,
`:1900-1960`, `:2500-2530`; `src/agentic_postgres/deployed_output.py:30-60`;
`compose.yaml:1260-1275`; `src/agentic_postgres/migrations.py:85-100`,
`:795-938`; every reader of `SUPPORTED_PROJECT_SCHEMA_VERSIONS`,
`deployed_output.SCHEMA_VERSION` and `PROJECT_APPROVALS_FROM` (grep each in
`src/`, `bin/`, `tests/` — D979); `tests/contract/test_project_migration_sets.py:
640-830`; `tests/contract/test_auth_service_shape.py:280-350`;
`tests/contract/test_render_isolation.py:1-120`.

**Build.**

1. **Manifest schema 9** (D2044): `schemas/project.schema.json` — `9` in the
   version enum (`:16-28`); a top-level `control` object
   (`additionalProperties: false`, `required: ["enabled"]`, `enabled:
   boolean`, a description citing ADR 0251); the gate *forbidden below 9* in
   the shape of the connectors gate (`:952-971`). `config.py`:
   `SUPPORTED_PROJECT_SCHEMA_VERSIONS` gains 9; `PROJECT_CONTROL_FROM = 9`; a
   reader `control_enabled(project) -> bool` (absent → False) beside the
   connectors reader (grep `connectors` in `config.py` for it). A manifest
   with `control.enabled: true` and NO `migrations.set` is refused (*the
   control plane's tables are its set*).
2. **The lint** (D2046): `PROJECT_PLACEHOLDER_SOURCES` unchanged; a second
   constant `CONTROL_PLACEHOLDER_SOURCES = {"auth_service": "database.roles.auth_service"}`
   (read how `:88-98` maps names to sources and follow it); `lint_project_set(
   project_set, *, control: bool = False)`: with `control`, `{{auth_service}}`
   is accepted ONLY inside a statement matching
   `^GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+.+\s+TO\s+\{\{auth_service\}\}\s*$`
   (case-insensitive, one grantee); anywhere else, and in any set without
   `control`, the existing refusal names it. Every caller passes the flag from
   the manifest (grep `lint_project_set(`; the render at
   `rendering.py:2509-2527`; `bin/migrate.py:771`; any other). The rendered
   placeholder resolves to the derived role (`naming.py:166`).
3. **Naming** (D2045, D2059): `CONTROL_PATH_SUFFIX = "/v1"` beside
   `APP_PATH_SUFFIX` (`:119`); `control_router_name(key)` →
   `apg-{key}-control` and `control_stripprefix_middleware_name(key)` →
   `apg-{key}-control-stripprefix` beside the app's (`:391-402`);
   `route_control` = `https://{domain}{api_base_path}{CONTROL_PATH_SUFFIX}`
   and `route_control_path` in `derive` (`:1134-1137`).
4. **Rendering**: `routes.control` in the outputs `routes` block
   (`rendering.py:437-458`) with a comment in the house voice (named whether or
   not the facility is on; D326); compose variables `AUTH_APP_MODE` (`control`
   or `auth`), `API_CONTROL_PATH` (= `{api_base_path}`, the strip),
   `CONTROL_ROUTE_PATH` (= `{api_base_path}/v1`), the two names from item 3.
   `deployed_output.SCHEMA_VERSION = 20`. **The outputs document also records
   the facility** — a top-level `control: {"enabled": <bool>}` beside
   `storage.enabled` — because `bin/control.sh` finds the control project by it
   (D2068) and a reader of the deployed document must not re-read a manifest.
   **The deployed branch observes `routes.control`** at step 7 (beside
   `observe_app`, `bin/deploy-project.py:1499-1545`): where the facility is on,
   `GET {routes.control}/me` with no token, and **`401` reads `ready`** (the
   house shape for an authenticated route: reachable, and refusing the
   anonymous); anything else reads `unavailable` with the status in the
   reason; where the facility is off, `unavailable` without a request. Grep
   every enumerator of route members (D2045's grep) and extend each.
5. **Router labels** (`runtime_override.py`): `_control_labels(...)` beside
   `_app_labels` (`:1251-1310`), rendered ONLY when the facility is on: the
   rule ``Host(`${PROJECT_DOMAIN}`) && PathPrefix(`${CONTROL_ROUTE_PATH}`)``,
   the same baseline chain and buffering middleware, a strip of
   `${API_CONTROL_PATH}`, the same `tls.certresolver`; and `_app_labels`'
   rule gains 37d's `&& !PathPrefix(…/v1)` term when the facility is on — the
   string exactly as 37d measured it. Alpha's and beta's rendered labels stay
   byte-identical (a test).
6. **`compose.yaml:1271`**: `APP_MODE: ${AUTH_APP_MODE:?required}`.
   `tests/contract/test_auth_service_shape.py:293-345` keeps passing (the
   environment's KEYS are unchanged).
7. **`project.control.example.yaml`** (committed; `.gitignore:46-50` keeps
   `!/project.*example.yaml`): schema 9, slug `control`, environment `prod`,
   domain `control.example.test` (an example domain — the operator's real one
   lives only in `/home/op/control.yaml`), `control: {enabled: true}`,
   `migrations: {set: projects/control}`, REST off, storage per 37e (D2049),
   backup with a mirror block, `lifecycle: {kind: permanent}`. **It is not a
   gate fixture** (`rendered_fixtures.FIXTURE_KEYS` unchanged, D1507); the
   control modules render it into a temporary directory. **It cannot render
   until Run 3 creates `projects/control/`**, so Run 2's tests use a temporary
   set (the 37e draft's shape, written by the test into `tmp_path`); Run 3
   adds the render test of the committed example.

**Tests**: `tests/contract/test_project_manifest_control.py` (new;
`pytestmark`): schema 9 accepted with and without `control`; `control` refused
below 9; `control.enabled: true` without `migrations.set` refused;
`control_enabled` absent → False. `test_project_migration_sets.py`:
`test_the_lint_refuses_auth_service_without_the_control_facility`,
`test_the_lint_accepts_auth_service_only_in_a_function_grant` (arms: a table
grant, a `SET ROLE`, a schema grant — each refused with the facility on).
`tests/contract/test_control_routes_rendered.py` (new): a control-facility
render carries `routes.control`, the control router and the negated app rule;
alpha-shaped and the two example renders carry NO control router and an app
rule byte-identical to before (read the old string from a render at
`2538ac0`? — no: assert the exact current rule string as a literal, copied from
`runtime_override.py:1292-1294` before the edit); `AUTH_APP_MODE` is `control`
only there. The outputs schema test that pins 19 (grep `== 19` / `19` beside
`SCHEMA_VERSION` in `tests/`) moves to 20.

**Battery**: (M1) the lint's function-grant regex widened to any statement →
`…only_in_a_function_grant` FAILED (control:
`test_the_lint_refuses_each_forbidden_shape_and_accepts_the_example_set`
PASSED); (M2) the negation term dropped → the render test FAILED; (M3)
`AUTH_APP_MODE` rendered `control` for every project → the alpha-shaped arm
FAILED; (M4) `control` accepted at schema 8 → the manifest test FAILED.

**Targeted once**: `test_project_manifest_control`,
`test_project_migration_sets`, `test_control_routes_rendered`,
`test_render_isolation`, `test_auth_service_shape`, the outputs-schema tests
the grep found, `test_rendered_migrations`, `test_acceptance_registry`,
`test_evidence_claims`; both example projects re-rendered first.

**Done.** *(the executor writes it)*

### Run 3 — the control project's migration set

**Code. Push and read CI.**

**Reads first**: Run 1's rig 37b Done (G or T, and the `set_config`
answer); `projects/example/migrations/manifest.json` and its four templates
(the house shape of a set: header, `SET LOCAL ROLE {{object_owner}}`, one
banner and comment block per object, `REVOKE ALL … FROM PUBLIC`, grants,
`AP900` down); `projects/example/migrations/released.lock.json`;
`migrations/templates/0026-password-reset-plane.sql:80-250` (a single-use
token table and its consumption); `0033-agent-record-retention.sql:126-337` (a
function granted to nobody); `tests/contract/test_auth_endpoints.py:100-420`
(the cluster fixture to generalise).

**Build** — `projects/control/migrations/manifest.json` (versions after the
release's last, `20261004…`; `follows_release_version` per
`projects/example`'s lock) and three templates, design G unless 37b chose T:

1. **`0001-control-identity.sql`**: `CREATE TYPE app.control_role AS ENUM
   ('owner','admin','member','viewer')`; tables (all `app`, all `ENABLE` +
   `FORCE ROW LEVEL SECURITY`, policies `TO {{object_owner}}` per 37b):
   - `control_accounts (user_id uuid PRIMARY KEY, username text NOT NULL,
     display_name text NOT NULL, created_at timestamptz NOT NULL DEFAULT now())`
     — a display copy written at acceptance and at login; the identity
     registry stays the authority.
   - `control_organizations (id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
     name text NOT NULL CHECK (length(name) BETWEEN 1 AND 64), created_by uuid
     NOT NULL, created_at …)`.
   - `control_memberships (organization_id uuid REFERENCES
     control_organizations(id), user_id uuid NOT NULL REFERENCES
     control_accounts(user_id), role app.control_role NOT NULL, created_at …,
     PRIMARY KEY (organization_id, user_id))`.
   - `control_invitations (id uuid PK, token_hash text NOT NULL UNIQUE CHECK
     (token_hash ~ '^[0-9a-f]{64}$'), organization_id uuid NULL REFERENCES …,
     role app.control_role NULL, CHECK ((organization_id IS NULL) = (role IS
     NULL)), issued_by uuid NOT NULL, issued_at, expires_at NOT NULL CHECK
     (expires_at <= issued_at + interval '168 hours'), accepted_at NULL,
     accepted_by uuid NULL, revoked_at NULL)`.
   - `control_totp (user_id uuid PRIMARY KEY REFERENCES control_accounts,
     seed bytea NOT NULL CHECK (length(seed) = 20), enabled_at timestamptz
     NULL, last_step bigint NOT NULL DEFAULT 0, created_at …)`.
   Functions (`SECURITY DEFINER`, `SET search_path = pg_catalog, pg_temp`, each
   with a `COMMENT ON FUNCTION`): `control_record_account(p_user, p_username,
   p_display)` (upsert), `control_caller_roles(p_user) RETURNS TABLE
   (organization_id, role)`, `control_create_organization(p_user, p_name)`
   (inserts the organisation and the `owner` membership), `control_list_organizations(p_user)`,
   `control_get_organization(p_user, p_org)`, `control_list_members(p_user,
   p_org)`, `control_set_member_role(p_user, p_org, p_target, p_role)` and
   `control_remove_member(p_user, p_org, p_target)` (both refuse the last
   owner with `AP409: last_owner`, and the remove also revokes the target's
   keys in the organisation — **0002's table: so `control_remove_member` is
   created in 0002**, after the keys table, and 0001 says so in a comment),
   `control_mint_invitation(p_user, p_org, p_role, p_token_hash, p_expires_at)`,
   `control_list_invitations(p_user, p_org)` (never a hash),
   `control_revoke_invitation(p_user, p_org, p_id)`,
   `control_accept_invitation(p_token_hash, p_user) RETURNS TABLE
   (organization_id, role)` (the ONE `UPDATE … RETURNING` of D2051, then the
   membership insert when the invitation names an organisation; zero rows →
   `AP401: invitation_invalid`), `control_totp_begin(p_user, p_seed)` (replaces
   an un-enabled seed; refuses when one is enabled), `control_totp_seed(p_user)
   RETURNS TABLE (seed, enabled, last_step)`, `control_totp_confirm(p_user,
   p_step)` and `control_totp_accept_step(p_user, p_step) RETURNS boolean` (the
   atomic `UPDATE … SET last_step = p_step WHERE user_id = p_user AND last_step
   < p_step`), `control_totp_reset(p_username text)` (**granted to nobody**).
   Every caller-scoped function takes `p_user` and FIRST does `PERFORM
   set_config('app.user_id', p_user::text, true)` (G) — the control mode also
   sets it at the transaction's top; both are belt and braces of one value.
   **Role checks live in the functions** (`AP403: authorization_failed`), the
   matrix of D2053 written once as `app.control_role_rank(app.control_role)
   RETURNS integer` (viewer 1 … owner 4) so `>=` comparisons read the matrix.
2. **`0002-control-keys.sql`**: `control_keys (key_id text PRIMARY KEY CHECK
   (key_id ~ '^[0-9a-f]{16}$'), secret_sha256 text NOT NULL CHECK (… 64 hex),
   organization_id uuid NOT NULL, user_id uuid NOT NULL, name text NOT NULL,
   scopes text[] NOT NULL CHECK (scopes <@ ARRAY['organizations:read',
   'members:read','projects:read','operations:read'] AND
   array_length(scopes,1) IS NOT NULL), created_at, last_used_at NULL,
   revoked_at NULL, FOREIGN KEY (organization_id, user_id) REFERENCES
   control_memberships ON DELETE NO ACTION)` — **no FK cascade: the removal
   function revokes, then deletes the membership**; functions
   `control_mint_key`, `control_list_keys(p_user, p_org)` (own keys for
   viewer/member, all for admin/owner; never a hash),
   `control_revoke_key(p_user, p_org, p_key_id)`, `control_key_lookup(p_key_id)
   RETURNS TABLE (secret_sha256, organization_id, user_id, scopes, revoked,
   member_role)` (the current role joined, NULL when the member left),
   `control_key_used(p_key_id)` (`last_used_at`, at most once a minute), and
   `control_remove_member` (item 1).
3. **`0003-control-registry.sql`**: `control_projects (key text PRIMARY KEY
   CHECK (key ~ '^[a-z][a-z0-9-]{2,30}-[a-z][a-z0-9-]{1,15}$'), organization_id
   uuid NOT NULL REFERENCES control_organizations, slug, environment, domain,
   template_version, source_commit, adopted_at, adopted_from text NOT NULL
   CHECK (adopted_from = 'deployed_document'))`; `control_operations (id uuid
   PK, organization_id uuid NOT NULL, project_key text NULL, type text NOT
   NULL CHECK (type IN (… the eleven of D2054 …)), status text NOT NULL CHECK
   (status IN ('pending','running','succeeded','failed','cancelled')),
   progress integer NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
   requested_by uuid NOT NULL, arguments jsonb NOT NULL, error_code text NULL,
   created_at, started_at NULL, finished_at NULL)`; functions
   `control_list_projects(p_user, p_org NULL)`, `control_get_project(p_user,
   p_key)`, `control_list_operations(p_user, p_org)`,
   `control_get_operation(p_user, p_id)`, and **granted to nobody**:
   `control_adopt_project(p_key, p_org, p_slug, p_environment, p_domain,
   p_template_version, p_source_commit)` and `control_registry_rows()`.
   **No function inserts an operation** (D2054): 38 adds it with the
   reconciler.
4. Grants at the end of each file: `REVOKE ALL ON ALL FUNCTIONS … FROM PUBLIC`
   style per function, then `GRANT EXECUTE ON FUNCTION app.control_… (…) TO
   {{auth_service}};` for every function but the three granted to nobody, and
   the sentence *"There is no GRANT for `control_adopt_project`,
   `control_registry_rows` or `control_totp_reset`, and that absence is the
   decision (ADR 0251)"*. **No grant to any request role, nothing in `api`,
   so no `NOTIFY pgrst`.**
5. `bin/migrate.sh --project <a render-able control manifest> freeze-lock`
   (read `--help`; the manifest is `project.control.example.yaml`).
6. **`tests/contract/control_cluster.py`** (the shared fixture, §5's preamble)
   and **`tests/contract/test_control_set.py`** (new; `pytestmark`) with §2's
   `CTL-SET-001` names, plus the render test of `project.control.example.yaml`
   (it renders, carries `routes.control`, its secret names per 37e).

**Battery**: (M1) one table's `FORCE` removed → `…forces_row_level_security`
FAILED and the lint refuses (control: `…executable_by_no_role` PASSED); (M2)
`GRANT … TO {{authenticated}}` added on `control_list_members` →
`test_no_request_role_can_execute_a_control_function` FAILED; (M3)
`control_adopt_project` granted to `auth_service` →
`…operator_functions_are_executable_by_no_role` FAILED; (M4) the membership
check removed from `control_list_members` → `…a_non_member_sees_nothing`
FAILED; (M5) the acceptance `UPDATE` without `accepted_at IS NULL` → the
concurrency proof in Run 4 (record as *owed to Run 4* if no Run 3 test reads
it; do not count it as killed).

**Targeted once**: `test_control_set`, `test_project_migration_sets`,
`test_migrations_apply_as_the_migration_user`, `test_rendered_migrations`,
`test_acceptance_registry`, `test_evidence_claims`.

**Done.** *(the executor writes it)*

### Run 4 — the control mode, part one: sessions, TOTP, invitations, organisations, members

**Code. Push and read CI.**

**Reads first**: Runs 1–3's Done; `services/auth-api/app/main.py:90-540`;
`settings.py:25-60`, `:280-570`; `service.py:180-420`, `:840-1040`;
`repository.py` whole; `routes.py:490-720`; `errors.py` whole; `models.py:1-80`;
`one_time_tokens.py`; `tests/contract/test_auth_service_shape.py:880-970`;
`tests/contract/test_auth_endpoints.py:100-420`.

**Build.**

1. `settings.py`: `APP_MODES` gains `"control"`; `load(mode="control")` reads
   EXACTLY auth's variables (`REQUIRED_VARIABLES`) and forbids what auth
   forbids; a test asserts the two sets equal.
2. `main.py`: `create_app("control")` builds the FastAPI app (title
   *"Agentic Postgres management API"*), the health routes, the probe routes
   37e named (mounted from `routes.router`'s handlers by NAME — not a copy of
   the handler code; if `routes.router` cannot be partially included, a tiny
   `control_probe_routes.py` re-exports exactly those handlers), and
   `control_routes.router` (prefix `/v1`); the lifespan's `control` branch =
   auth's MINUS the workflow and connector repositories, the connector key and
   the worker. `public_paths()` gains the `control` arm; a new
   `control_paths()`.
3. **`totp.py`** (37a's module, made the product's): `hotp`, `totp`,
   `verify(seed, code, now, last_step, window=1) -> int | None`, `new_seed()`
   (`secrets.token_bytes(20)`), `provisioning_uri(username, seed)`
   (`urllib.parse.quote` for the label; `issuer=agentic-postgres`). No logging
   of a seed or a code anywhere (`test_no_seed_reaches_a_log_line` plants
   both and greps every captured record and stdout).
4. **`control_repository.py`**: the `Repository` pattern (`repository.py:
   126-142`, `dict_row`, `SELECT … FROM app.control_…(%s, …)`), one method per
   0001–0003 function the control mode calls; every transaction begins with
   `SELECT set_config('app.user_id', %s, true)`.
5. **`control_service.py`**: `login(username, password, code)` through
   `AuthService.login` with a NEW keyword hook `second_factor: Callable[[UUID],
   Awaitable[None]] | None = None`, called after the status check and before
   `issue` (`service.py:184-221`) — the existing callers pass nothing and are
   unchanged (grep `\.login(`); the hook reads `control_totp_seed`, requires
   and verifies the code with `control_totp_accept_step`, and on success
   upserts `control_accounts`. `refresh` and `logout` over the existing
   `AuthService.refresh` / `terminate_session`. `requires_factor(user)`:
   any `owner`/`admin` membership (`control_caller_roles`) or
   `admin_users:write` in the token's scopes; `factor_gate(principal, path)`
   raises `SecondFactorRequired` outside the four enrolment paths. TOTP begin
   and confirm (confirm revokes every session through the function 37e named).
   Invitations: mint (`one_time_tokens.mint()`, the hash stored, `expires_in_hours`
   default 72, max 168), list, revoke, **accept** — on ONE `auth_service`
   connection, one transaction: `auth_create_user(username, display_name,
   role_name('api_documentation'), ['meta:read'], argon2id(password))` (or per
   37e), `control_record_account`, `control_accept_invitation`; any failure
   rolls all back (`username_taken` checked AFTER the token validates).
   Organisations and members per D2053.
6. **`control_routes.py`** (`APIRouter(prefix="/v1")`), every handler through
   one guard in the shape of `routes._guard` (`routes.py:494-512`) and strict
   bodies (`strict_json`, pydantic `extra="forbid"`): `POST /v1/sessions`,
   `POST /v1/sessions/refresh`, `DELETE /v1/sessions/current`, `GET /v1/me`,
   `POST /v1/me/totp`, `POST /v1/me/totp/confirm`, `POST /v1/invitations`,
   `POST /v1/invitations/accept`, `GET|POST /v1/organizations`,
   `GET /v1/organizations/{org}`, `GET /v1/organizations/{org}/members`,
   `PATCH|DELETE /v1/organizations/{org}/members/{user}`,
   `GET /v1/organizations/{org}/invitations`,
   `DELETE /v1/organizations/{org}/invitations/{id}`. Every `201` that carries
   a secret sets `Cache-Control: no-store`. New error codes in `errors.py`:
   `second_factor_required`, `second_factor_invalid`, `invitation_invalid`,
   `username_taken`, `last_owner`, `human_session_required` (Run 5's),
   `not_available` (Run 5's) — each a constant with its HTTP status.
7. **`control_roles.py`**: the matrix (D2053) as one dict
   `route_name → minimum role`, read by the guard.

**Tests** (each `pytestmark`; the Docker-backed ones on `control_cluster`):
`tests/contract/test_totp.py` (37a's vectors and window, no cluster);
`tests/contract/test_control_sessions.py` (§2 `CTL-TOTP-001`'s four
session names); `tests/contract/test_control_invitations.py` (§2
`CTL-INV-001`'s seven — the concurrency proof runs two acceptances on two
event-loop tasks against the cluster and counts one `200`);
`tests/contract/test_control_roles.py` (the matrix for Run 4's routes — Run 5
extends it); `test_auth_service_shape.py`: the `control` path case and
`test_the_auth_mode_serves_no_management_path`.

**Battery**: (M1) the window widened to ±2 → `test_the_window_is_one_step`
FAILED (control: `test_rfc_6238_vectors` PASSED); (M2) `last_step <` turned
`<=` → `test_a_replayed_step_is_refused` FAILED; (M3) the second-factor hook
skipped → `test_login_requires_the_code_once_enabled` FAILED; (M4) confirm no
longer revokes sessions → its proof FAILED; (M5) the expired branch answered
`invitation_expired` → `test_every_invalid_token_gets_the_same_answer` FAILED;
(M6) `auth_create_user` moved after the acceptance and its error swallowed →
`test_acceptance_is_one_transaction` FAILED; (M7) an admin allowed to invite
an owner → the matrix FAILED. Assert each FAILED, never ERROR (D386); restore
by copy, `cmp` each file back.

**Targeted once**: the five above, `test_auth_endpoints` (the login hook
must not move it), `test_request_log` (a `/v1` request still logs one line
with its TEMPLATE), `test_auth_strict_query`, `test_request_id_stamping`,
`test_app_contract_aggregate` (unchanged: it builds `auth` and `storage`),
`test_acceptance_registry`, `test_evidence_claims`.

**Done.** *(the executor writes it)*

### Run 5 — the control mode, part two: keys, projects, operations, the guard, the contract

**Code. Push and read CI.**

**Reads first**: Run 4's Done and its modules; `bin/app-contract.py` whole;
`tests/contract/test_app_contract_aggregate.py` whole;
`tests/contract/test_reality_ledger.py` whole; `docs/reality-ledger.yaml:
130-185`; `src/agentic_postgres/evidence_claims.py:1-60` (how a module in
`src/` is laid out and documented).

**Build.**

1. **Key authentication** in `control_service.py`: an `Authorization: Bearer
   apg_…` header is a key (`^apg_([0-9a-f]{16})_([A-Za-z0-9_-]{43})$`, else
   `401`); `control_key_lookup` → `hmac.compare_digest(sha256(secret).hexdigest(),
   stored)`; refused when revoked, when the member left (`member_role IS
   NULL`), or on mismatch — ONE `401 authentication_failed` for all;
   effective scopes = key scopes ∩ the role's (`control_roles.ROLE_SCOPES`);
   `control_key_used`. A key principal never satisfies a human-session route
   (`403 human_session_required`) and never needs a second factor.
2. **Routes**: `GET|POST /v1/organizations/{org}/keys`, `DELETE
   /v1/organizations/{org}/keys/{key_id}` (the key in the `201` body once,
   `no-store`); `GET /v1/projects` (`?organization=`), `GET
   /v1/projects/{key}`, **`POST /v1/projects` → `409 {"error":"not_available",
   "ledger_row":"projects_self_service"}`**; `GET /v1/operations`
   (`?organization=` required), `GET /v1/operations/{id}`. A foreign or
   missing organisation, project, key or operation → the SAME `404
   {"error":"not_found"}`.
3. **`src/agentic_postgres/operations.py`** (D2054): `OPERATION_TYPES: dict[str,
   str]` type → Ledger row id (`project.create|delete|sleep|wake|resize|export`
   → `projects_self_service`, `project_deletion`, `sleep`, `sleep`,
   `compute_profiles`, `export`; `branch.create|reset|delete` → `branches`;
   `restore.create` → `restore_to_branch`; `credential.rotate` →
   `direct_endpoint`), `accepted(type, ledger) -> bool`, and a loader that
   reads `docs/reality-ledger.yaml` for the TEST only (the service imports the
   table, never the file). `control_routes` imports `operations` and refuses
   any type `accepted` returns False for — today all of them.
4. **The Ledger guard**: in `tests/contract/test_reality_ledger.py`, replace
   `test_the_sets_the_guard_will_read_are_empty_today` with
   `test_every_operation_type_names_a_ledger_row_and_none_is_accepted_while_planned`
   (every type's row exists; `accepted` iff the row is `available`/`beta`;
   the 0003 CHECK list equals `OPERATION_TYPES`' keys) and
   `test_no_console_exists_yet` (the console half, unchanged in substance).
   ADR 0254 authorises the replacement.
5. **The contract** (D2057): `bin/app-contract.py` — `generate_control()` =
   `create_app("control").openapi()` keeping only `/v1` paths (and the
   schemas they reference), title *"Agentic Postgres management API"*;
   `--update` gains `--snapshot app|control` (default `app`); `--check`
   compares both and names the one that differs; `bin/app-contract.sh`'s usage
   says so. Write `contracts/control-openapi.canonical.json` with
   `sudo`-free `bin/app-contract.sh --update --snapshot control >
   contracts/control-openapi.canonical.json` (read `--help` for the exact
   form; the command streams to stdout).
6. **`tests/contract/test_control_boundary.py`** (new): an AST scan of
   `control_*.py` and `totp.py` for any read of `deployed_output`, an outputs
   path, `/etc/agentic-postgres/projects`, `*_password`, `pgpass`, `routes.`
   of another project or an HTTP client import — the control mode reads
   nothing of another project.

**Tests**: `tests/contract/test_control_keys.py` (§2 `KEY-MINT-001`'s six);
`tests/contract/test_operation_types.py` (two); the Ledger guard (above);
`test_app_contract_aggregate.py::test_the_control_snapshot_is_what_this_checkout_generates`;
`test_control_roles.py` completed over every `/v1` route (keys, projects,
operations) and `test_a_foreign_id_and_a_missing_id_look_the_same`.

**Battery**: (M1) `compare_digest` replaced by `==` on a prefix → nothing
should fail functionally — **an uninformative mutation (D493); do not run
it**; instead (M1') a revoked key accepted (the `revoked` check dropped) →
`…revoked_key_and_a_departed_owners_key_are_refused` FAILED (control:
`…shown_once_and_stored_hashed` PASSED); (M2) the scope intersection dropped
(key scopes used alone) → `test_a_demotion_narrows_a_key` FAILED; (M3) a key
allowed on `POST …/keys` → `test_a_key_mints_nothing` FAILED; (M4)
`projects_self_service` set to `beta` in a COPY of the Ledger the test is
pointed at → the guard's accepted-iff half FAILED for `project.create` while
`POST /v1/projects` still refuses (the type table and the route disagree —
the guard reads both); (M5) a `/v1` path added without regenerating the
snapshot → `…control_snapshot…` FAILED; (M6) a foreign organisation answered
`403` → the enumeration proof FAILED.

**Targeted once**: `test_control_keys`, `test_operation_types`,
`test_reality_ledger`, `test_app_contract_aggregate`, `test_control_roles`,
`test_control_boundary`, `test_auth_service_shape`, `test_client_ir`,
`test_generated_client_toolchain`, `test_studio_core` (the three other readers
of the app snapshot, `bin/app-contract.py` changed), `test_acceptance_registry`,
`test_evidence_claims`. **The `LEDGER-001` node id renamed in this run is
registered in Run 9** — between Runs 5 and 9 the registry names a node that
no longer exists: run `test_acceptance_registry` and, if it refuses the
missing node now, move `LEDGER-001`'s node ids IN THIS RUN (an existing
requirement's node ids are not gated by `CURRENT_SESSION`) and say so in the
Done.

**Done.** *(the executor writes it)*

### Run 6 — `bin/control.sh adopt|registry|totp-reset`

**Code. Push and read CI.**

**Reads first**: `bin/record.sh` and `bin/record.py` whole (the sibling:
root, verb-first usage, a key resolved through
`deployed_output.read_deployed_document`, every exec through
`container_exec.run`, `psql -v` variables, exits 0/2/3/5/6);
`src/agentic_postgres/container_exec.py` whole; `bin/fleet.py:70-90`;
`tests/contract/test_record_command.py` whole (the fake-docker pattern);
`tests/contract/test_cli_contract.py:42-300`, `:470-600`.

**Build.** `bin/control.sh` (preamble, `--help` anywhere is a read, root for
every verb) exec'ing `bin/control.py`:

```
Usage: sudo bin/control.sh adopt --project KEY --organization ORG_ID --confirm CONTROL_KEY
       sudo bin/control.sh registry [--json]
       sudo bin/control.sh totp-reset --username NAME --confirm CONTROL_KEY
```

The control project is FOUND, never named: the one directory under
`/etc/agentic-postgres/projects/` whose deployed document carries the control
facility (the deployed document's record of the manifest's `control.enabled`
— Run 2 put it there; if it is not in the document, Run 2's Done says where
it is and this run reads that); none → exit 3 *"no deployed project enables
the control facility"*; two → exit 5 naming both. `--confirm` must equal the
control project's key. `adopt` reads KEY's deployed document
(`slug`, `environment`, `domain`, `template_version`, `source_commit` — the
pointers Run 6 reads from `deployed_output`), refuses a key with no document,
and calls `SELECT app.control_adopt_project(:'key', :'org', …)` as `postgres`
in the control project's database container through `container_exec.run`
(the container and database DERIVED from the control document, D1184).
`registry` reads `control_registry_rows()` the same way and every deployed
document under the root, and prints one line per key — `agrees`, `differs:
<field>[, <field>]`, `not in the registry`, `no deployed document`, or `could
not determine: <reason>`; `--json` the same as objects. Exit 0 all agree; 5
any difference; 6 any undetermined (ADR 0195: a decision may fail closed, a
report may not). `totp-reset` calls `control_totp_reset(:'username')` and
prints whether a factor was removed.

**Tests**: `tests/contract/test_control_command.py` (new; `pytestmark`; a fake
`docker` on `PATH` as `test_record_command.py` does) with §2's `CTL-REG-001`
names. Register `bin/control.sh` in `SHELL_COMMANDS`, `bin/control.py` in
`PYTHON_COMMANDS`, `control` in `COMMANDS_WITH_VERBS`; `git add` first.
Battery: (M1) an unreadable document reported `agrees` → `…undetermined_not_agreeing`
FAILED; (M2) `--confirm` compared case-insensitively → the confirmation proof
FAILED.

**Targeted once**: `test_control_command`, `test_cli_contract`,
`test_operator_commands_run_on_the_host`, `test_container_exec`,
`test_database_commands`, `test_root_script_policy`, `test_repository_contract`,
`test_apg_dispatcher`, `test_completion_command`.

**Done.** *(the executor writes it)*

### Run 7 — the CLI: `apg login|logout|context|org|project`

**Code. Push and read CI.**

**Reads first**: `bin/studio.py:220-370` (a password from a checked 0600 file
or `getpass`; a token held in memory; `ssl.create_default_context()`);
`bin/workflow.py:320-390` (the base URL and the token, read never derived);
`bin/connector.py:395-410` (the `O_EXCL|O_NOFOLLOW` 0600 write);
`bin/connect.sh:225-260` (a private state directory's refusals);
`bin/workflow.sh:1-60`, `:290-345` (usage lines, `--help` before the verb,
positional arguments refused); `tests/contract/test_cli_contract.py:1100-1113`.

**Build.** Pure logic in **`src/agentic_postgres/control_client.py`**: the
state directory (D2066: `${XDG_CONFIG_HOME:-$HOME/.config}/apg`, 0700,
refusals), `read_private_file(path)` (0600 or narrower, a regular file, not a
symlink, owned by the caller), `write_private_file(path, bytes)` (temporary
name, `O_WRONLY|O_CREAT|O_TRUNC|O_NOFOLLOW` 0600, `os.replace`), the context
and session documents, `request(method, url, body, credential)` over
`urllib.request` (https required except `127.0.0.1`/`localhost`; `401` on a
password session → one refresh then one retry; the server's `error` code
mapped to an exit), and the exit codes (0 ok; 2 usage; 3 no context / no
credential / not https; 5 refused by the server; 6 the server could not be
reached or answered something unreadable). **One Python program
`bin/cloud.py`** (stdlib + `agentic_postgres`, ADR 0093) with the family as
its first argument; five thin shells exec it:

```
Usage: bin/login.sh password --endpoint URL --username NAME [--password-file FILE] [--totp-code-stdin]
       bin/login.sh key --endpoint URL --key-file FILE
       bin/login.sh accept --endpoint URL --invitation-file FILE --username NAME [--display-name TEXT] [--password-file FILE]
       bin/login.sh totp-enroll [--output FILE]
       bin/login.sh totp-confirm [--totp-code-stdin]
Usage: bin/logout.sh [--json]
Usage: bin/context.sh show [--json]
Usage: bin/org.sh list [--json]
       bin/org.sh create --name TEXT
       bin/org.sh use --organization ID
       bin/org.sh members [--organization ID] [--json]
       bin/org.sh invite (--account | --role owner|admin|member|viewer) --output FILE [--organization ID] [--expires-hours N]
       bin/org.sh set-role --user ID --role owner|admin|member|viewer [--organization ID]
       bin/org.sh remove --user ID [--organization ID]
       bin/org.sh keys [--organization ID] [--json]
       bin/org.sh key-create --name TEXT --scopes LIST --output FILE [--organization ID]
       bin/org.sh key-revoke --key-id ID [--organization ID]
Usage: bin/project.sh list [--organization ID] [--json]
       bin/project.sh use --project-key KEY
       bin/project.sh show [--project-key KEY] [--json]
```

`--output FILE` is written once, 0600, refused if it exists; the invitation
token, the key and the `otpauth://` URI go there (or, for `totp-enroll`
without `--output`, to the terminal only when stdout is a TTY — refused
otherwise). **No verb prints a secret to a non-TTY stdout.** `--project-key`
(not `--project`) keeps `apg`'s `APG_PROJECT` rule from appending a manifest
path (`bin/apg.sh:199-216` matches `--project FILE` only, but the distinct
name removes the question).

**Tests**: `tests/contract/test_control_cli.py` (new; `pytestmark`; the real
control app served by `uvicorn.Server` in a thread on `127.0.0.1:<free
port>` against `control_cluster` — **the commands are run as subprocesses
against it**, never a fake server, CLAUDE.md §7 question 6) with §2's
`CTL-CLI-001` names; register the six files (`login.sh`, `logout.sh`,
`context.sh`, `org.sh`, `project.sh`, `cloud.py`) and the four verb-bearing
shells in `COMMANDS_WITH_VERBS`; `git add` first. Battery: (M1) the state
directory created 0755 → `…state_directory_is_private` FAILED; (M2) a
symlinked key file followed → `…symlinked_or_wide_file…` FAILED; (M3) http
accepted for a non-loopback host → its proof FAILED; (M4) `logout` not calling
the server → `test_logout_revokes_the_session` FAILED.

**Targeted once**: `test_control_cli`, `test_cli_contract`,
`test_operator_commands_run_on_the_host`, `test_apg_dispatcher`,
`test_completion_command`, `test_repository_contract`, `test_embedded_python`,
`test_documentation_index` (if a page names the verbs yet — Run 9 writes it).

**Done.** *(the executor writes it)*

### Run 8 — the trip's instruments, written and rehearsed offline

**Commits nothing but its `**Done.**`** (no CI). Everything here is a script in
WSL `~/s37/run8/` (backed up to the scratchpad's `s37/run8/`) and, where it
runs on the host, copied to `/home/op` by the agent and read back (sha256 on
both sides into `shipped-sha256.txt`).

**Reads first**: `~/s36/run7/` and its `NOTES.md` (**the model**: Session 36's
`s36-derive.py` derived five trip scripts from Session 35's by named,
count-asserted substitutions); Session 36's Sheets R1–S1 and rows D2031–D2041
(what went wrong on that trip); `docs/fleet-operations.md:133-188`; this
plan's appendix.

**Write**, each with a `--help` and its own transcript (`tee`), each deriving
container, database and volume names from a deployed document and never typing
one (D1184):

1. **`s37-controlyaml.py`** (op) — writes `/home/op/control.yaml` from
   `project.control.example.yaml` with the operator's values (D2071: slug
   `control`, environment `prod`, domain `control.agenticpostgresql.com`) and
   the provider facts copied from `/home/op/agentic-postgres/project.alpha.yaml`
   (`storage.account_id`, the backup and mirror endpoints, regions and
   jurisdictions — the mirror bucket is the DERIVED name
   `apg-control-prod-backup-mirror` unless the operator names another on Sheet
   P1); refuses if the file exists without `--replace`; prints the file.
2. **`s37-dns.sh`** — D2064's two reads; exit 0 only when the A record is
   `62.238.99.122` from `1.1.1.1` and port 80 answers.
3. **`s37-free.sh`** — `free -m`, `docker stats --no-stream`, and the
   `available` figure against D2042's 1,024 MiB (prints `FITS` or `STOP`).
4. **`s37-units.sh`** — derived from `s36-units.sh` with
   `agentic-postgres-project@control-prod` added (four units, three `active`
   readings in a row).
5. **`s37-probe-start.sh` / `s37-probe-stop.sh`** — derived from Session 36's
   (alpha's and beta's five classes during R2a/R2b; the control project is NOT
   probed — it has no traffic to lose on its first deploy).
6. **`s37-sweep.sh` / `s37-launch.sh`** — derived from `s36-sweep.sh` /
   `s36-launch.sh` by diff (D2072): the gate's name, every declaration S1 made,
   **`--control-outputs /home/op/control-prod-outputs.json`** added; the
   preflight requires HEAD to equal all THREE deployed documents'
   `source_commit` and the kernel to have booted after all three `observed_at`s
   (else exit file 95, nothing run).
7. **`s37-external.sh`** (workstation) — derived from `s36-external.sh`:
   `--control-outputs` (the op copy, fetched to WSL) and `--control-probe-file
   ~/s37/probe.json` added; the copies' commit check covers three documents.
8. **`s37-probe-enrol.py`** (workstation) — given an ACCOUNT invitation file
   the operator minted (Sheet PR1), it runs the PRODUCT's commands with
   `XDG_CONFIG_HOME=~/s37/probe-config`: `bin/login.sh accept` (username
   `probe-owner-s37`, a generated password written 0600 to
   `~/s37/probe-password`), `bin/login.sh password`, `bin/login.sh
   totp-enroll --output ~/s37/probe-otpauth` (the seed parsed from the URI),
   `bin/login.sh totp-confirm` (the code computed from the seed with the
   product's `totp.totp`), `bin/login.sh password` again with the code,
   `bin/org.sh create --name probe-s37`; writes `~/s37/probe.json` (0600:
   endpoint, username, password-file path, seed base32, organisation id). It
   never prints the password or the seed.
9. **`s37-walk-notes.md`** — the operator's day-2 walk (Sheets W1–W3) as a
   checklist with the exact commands, for the agent to read beside the
   operator.

**Rehearse offline** (`rehearse-offline.txt`): `s37-controlyaml.py` against a
copy of `project.alpha.yaml` with planted values → the file renders with
`./deploy.sh --render-only` in a worktree (rc 0); `s37-probe-enrol.py`
against the control app served on loopback (Run 7's harness: `control_cluster`
+ uvicorn) with an account invitation minted through `/v1` by a bootstrapped
administrator → `probe.json` written 0600 and a login with the computed code
served; a second run refused (the username taken, the token unspent);
`s37-dns.sh` against `example.com` → exit non-zero (not our address);
`s37-free.sh` → prints a verdict; the derived scripts' token diffs printed (as
D2024 did: every flag of S1 kept, exactly one added).

**Done.** *(the executor writes it)*

### Run 9 — the bump, the registry, the gate, the threat rows, the documents

**Code. Push and read CI.** The shape of Session 36's Run 8 (`55c002c`).

**Build.**

- `src/agentic_postgres/__init__.py`: a `#:` paragraph for Session 37 above the
  constant (the shape of `:835-891`: what the release adds, the pricing,
  **`VERSION` moves to `1.15.0`**), `CURRENT_SESSION = 37`. `VERSION` →
  `1.15.0`.
- `tests/acceptance-registry.yaml`: the block `# Session 37 (ADR 0251-0254)`
  with §2's thirteen entries and the node ids COLLECTED (`pytest
  --collect-only -q` over the new modules); `CTL` and `KEY` in the ID regex
  (`test_acceptance_registry.py:111`) and the family sentence (`:50-110`).
- `evidence_claims.py`: `CLAIMS` and `OFFLINE_CLAIMS` per §2;
  `CLAIM_INTRODUCED_IN` rows at 37.
- `tests/conftest.py`: `APG_CONTROL_OUTPUTS` and `APG_CONTROL_PROBE_FILE` in
  `ENVIRONMENT_VARIABLES` (`:86-189`), each with its comment.
- **The live modules land now** (D2018's lesson: a deployment proof no registry
  entry names fails `test_deployment_suite_shape` on the day it is written):
  `tests/deployment/test_session37_control.py` (`CTL-REG-002`'s four; reads
  `APG_CONTROL_OUTPUTS`, `APG_PROJECT_A_OUTPUTS`, `APG_PROJECT_B_OUTPUTS`; the
  registry proof runs `sudo`-free as the gate's host mode runs as root —
  read how `test_session36_operations.py` calls `bin/record.sh`) and
  `tests/external/test_session37_control.py` (`CTL-INV-002`, `CTL-TOTP-002`,
  `KEY-USE-001`; reads `APG_CONTROL_OUTPUTS` and `APG_CONTROL_PROBE_FILE`
  ONLY, plus `APG_PROJECT_A_OUTPUTS` for alpha's `routes.app`/`routes.rest`
  in `KEY-USE-001`'s refusal half; every request through a recording opener,
  D2058; each proof creates its own `probe-s37-<8 hex>` accounts and removes
  their memberships at the end, D2065), and
  `tests/contract/test_session37_customer_proofs_reach_only_the_public_endpoint.py`
  (D2058's scan; or as a function in `test_control_boundary.py` — one place).
  `pytest --setup-plan` for both live modules with the variables set and
  unset (D671): SETUP with them, skips without.
- **`bin/session-37-check.sh`, derived from 36's by diff** (D1482):
  `readonly SESSION=37`; the header and the usage block REWRITTEN whole
  (D1488) — what 1.15.0 adds, the nine offline claims, the three external, the
  one host; **two flags added** (`--control-outputs FILE`: host and external,
  exported as `APG_CONTROL_OUTPUTS`; `--control-probe-file FILE`: external,
  exported as `APG_CONTROL_PROBE_FILE`), each with one usage entry; the
  offline mode's step 6 still runs `bin/app-contract.sh --check` (now both
  snapshots). `tests/contract/test_session_thirty_seven_gate_modes.py`
  derived from 36's (`SESSION = 37`, `SESSION_PREVIOUS_NUMBER = 36`, the
  claims table with the external column, the offline-set assertion, the
  exports present and in the roster). `SHELL_COMMANDS` gains the gate;
  `chmod 755`.
- **`docs/threat-model.md`**: five `THR-CTL-*` rows in the table (D2056) —
  nine cells each, no `|` in a cell, the requirement ids and node ids from
  §2, target session 37 — and the list items they replace removed (the
  remaining halves of enumeration and confusion kept, naming 38–40).
- **Documents**: **`docs/control-plane.md`** (new; indexed once in
  `docs/README.md`): what the control plane is (one project, `/api/v1`, the
  boundary sentence), accounts and invitations (who mints which), roles, TOTP
  (enrol, confirm, a lost device → the operator), keys (format, scopes,
  human-only minting), the registry (`bin/control.sh`), what is NOT here
  (operations accepted, account deletion, email, passkeys, the console),
  every command with `--help`'s spelling; `docs/operator-guide.md` §3 — the
  control project's bring-up (D2060's `systemctl enable` line, D2061's
  shred) and a sentence that `/home/op/control.yaml` is the third manifest;
  `docs/fleet-operations.md` §6 — step 3's *"shreds the credential file"*
  corrected (D2061), step 8 gains the unit enable (D2060), step 1's
  `.gitignore` sentence corrected (`.gitignore:46-50` ignores
  `/project.*.yaml` since D1034); `docs/recovery-operations.md:63-65` — the
  kit command with `--project /home/op/control.yaml` and D2069's sentence;
  `docs/upgrade-guide.md` a `1.15.0` row (minor, read; manifest schema 9
  optional; outputs 20; a fourth app mode used only by a control-facility
  project); `README.md:7` and the `template_version` phrase; every `--session
  36` / `--through-session 36` literal a reader executes, moved and counted
  per file (D678/D1484); `docs/reality-ledger.yaml` — the `stage5_reality`
  TEXT of `api_keys` (SHA-256, the 37 vocabulary, human-only minting),
  `accounts` (two kinds of invitation) and `cli_remote` (the verbs as built)
  — **status unchanged** (D2055); `bin/render-reality-ledger.py --write`;
  `docs/product-contract.md`'s requirement block regenerated
  (`bin/render-acceptance-matrix.py --write`).
- **`upgrade plan` offline** (Session 36 Run 8's method: a worktree at
  `2538ac0`, the candidate this tree, both rendering `project.example.yaml`):
  the class read; **`major` is a stop** (§9).

**Before the push**: `ruff format && ruff check`; `bin/render-acceptance-
matrix.py --write`, `bin/render-config.py --bounds-doc --write`,
`bin/render-reality-ledger.py --write`, `python bin/render-mcp-catalog.py
--write`, `python bin/render-evaluation-report.py --write`; targeted:
`test_acceptance_registry`, `test_evidence_claims`, `test_cli_contract`,
`test_session_thirty_seven_gate_modes`, `test_documentation_index`,
`test_session12_documented_path`, `test_reality_ledger`,
`test_deployment_suite_shape`, the sweep-selector guard (D1242),
`test_control_boundary`; then commit, then **`bin/session-37-check.sh --mode
offline`** and `bin/session-01-check.sh` on the clean tree, both ONCE, both
detached with their exit codes written to files (CLAUDE.md §1). Push; read
CI by full SHA. **Battery** (Session 36 Run 8's nine, re-aimed): a host claim
declared offline; `control_cli` undeclared; `CLAIM_INTRODUCED_IN` at 36 for
one; a node id renamed; `CTL` out of the regex; `SESSION=36`; the help naming
36's offline half; `--control-probe-file`'s usage entry dropped; `KEY-USE-001`
at 36 — each FAILED, the controls PASSED.

**Done.** *(the executor writes it)*

### Run 10 — sitting 1 (day 1): the release, then the control project brought up

**Before the day** (agent, offline): CI green on Run 9's commit by full SHA;
`pytest --setup-plan` for `tests/deployment/test_session37_control.py` and
`tests/external/test_session37_control.py` with the variables set (D671); the
operator has done **Sheet P1** (the consoles; any day before) and said so.

**On the day, in order** (agent's steps over SSH as `op`; the operator's are
the sheets):

1. Ship the bundle (`git bundle create /tmp/apg-<sha>.bundle 2538ac0..main`),
   `scp` it, `git fetch` it in `~op/agentic-postgres`, `git checkout
   --detach FETCH_HEAD`, `git rev-parse HEAD` == Run 9's full SHA; `uv sync`
   (read Session 36 Run 9's Done for the exact line); `git status --short`
   empty.
2. Renders as `op` (no root): alpha, beta, the two fixtures
   (`--render-only`), and **`/home/op/control.yaml` written by
   `s37-controlyaml.py`** and rendered (`./deploy.sh --project
   /home/op/control.yaml --capabilities capabilities.yaml --render-only`) —
   rc 0 each.
3. `bash /home/op/s37-dns.sh` → exit 0 (D2064). If not, stop: the record is
   the operator's.
4. **Sheet P2** — the control project's providers (the operator; the agent
   reads the transcript): `--plan`, the credential placed, `--apply`, the
   shred, `ls` empty. Then the operator pastes the operator-supplied values
   `--plan` listed (the backup pair at `/backup`; the mirror pair at
   `/backup`; the storage pair at `/storage` **only if** 37e said it is owed —
   create the folder) and says so.
5. **Sheet P3** — materialize `control-prod` → exit 0.
6. **Sheet R1** — `upgrade plan` for alpha and beta against their 1.15.0
   candidates; the class read (§1 D2070). `major` → stop.
7. Start the probe (`s37-probe-start.sh`, alpha's and beta's classes).
8. **Sheets R2a / R2b** — alpha, then beta, at `--through-session 37`. The
   probe stopped after R2b; the windows read (expected per D2034: auth, mcp,
   storage ~8–14 s; rest and docs 0).
9. **Sheet C1** — the control project's first deploy (`/home/op/control.yaml`).
   The first pass reads ports and the app route `unavailable` (D326). Read
   `sudo apg-diag edge-log` for the certificate's issuance (the agent's
   account, `apg-agent@`) — **a failed issuance is a stop** (D2064).
10. **Sheet C2** — the first administrator (`bin/auth-admin.sh … bootstrap
    --username control-admin --display-name "Control administrator"`), the
    password typed by the operator and written by the operator to
    `/root/control-prod-administrator` (0600).
11. **Sheet C3** — `--render-runtime-only`, the printed `verify` line, the
    second deploy. The document now reads ports `available`, `routes.app`
    and `routes.control` `ready`.
12. **Sheet C4** — the unit enabled (D2060), the three doctors (`12 ok` each;
    the control project's doctor may read a check the `control` mode changes
    — the agent reads each line and records it as a row if it is not `ok`),
    `doctor capacity` (committed 912), `s37-free.sh` → `FITS` (D2042; `STOP`
    is §9's).
13. **Sheet C5** — the control project's first full backup, `info`, `schedule
    enable`, `mirror` (D2062).
14. **Sheet K1** — the DR kit with three projects (D2069) and the three
    op-readable document copies; the agent copies the kit to WSL
    `~/dr-kits/` (0700/0600) and runs `bin/dr-kit.sh verify` on the copy.
15. **Sheet V1** — the day verified with `-k "session37 or session4_transports"`
    (writes nothing; a red proof is exit 6 since D2037). A failure here is
    repaired on the workstation and the commit moves (D2038's shape: bundle,
    checkout, renders, every project redeployed at the new commit) BEFORE
    day 2.

**Done.** *(the executor writes it: the windows, the certificate, the free
memory, the admission figures, every row)*

### Run 11 — sitting 2 (day 2): the person's path, the registry, the reboot, the one sweep, the tag

**Before the day**: Run 10's Done; the day-1 commit is still HEAD on the host
and in all three deployed documents.

**In order:**

1. **Sheet W1** — the operator, at the WORKSTATION (WSL, the checkout at the
   deployed commit, `XDG_CONFIG_HOME=~/s37/admin-config`): the control
   administrator logs in with the password from a 0600 file the operator
   copies by hand from `/root/control-prod-administrator` (or types at the
   TTY), enrols TOTP on their phone's authenticator (`bin/login.sh
   totp-enroll` printing the URI to the terminal, typed or scanned — a QR
   code is not produced in 37), confirms with a code, logs in again with a
   code, and mints **one account invitation** (`bin/org.sh invite --account
   --output ~/s37/invite-person`).
2. **Sheet W2** — the operator, `XDG_CONFIG_HOME=~/s37/person-config`:
   `bin/login.sh accept` as their own username (chosen on the sheet), logs in,
   enrols and confirms TOTP **before** creating the organisation (so the
   owner's first request is not `second_factor_required`), logs in again
   with a code, `bin/org.sh create --name <the operator's organisation name>`,
   `bin/org.sh list` (the organisation id, read off for A1).
3. **Sheet A1** — `sudo bin/control.sh adopt` for `alpha-dev`, `beta-dev`
   and `control-prod` into that organisation, then `sudo bin/control.sh
   registry` → `agrees` × 3, exit 0.
4. **Sheet W3** — the operator: `bin/org.sh invite --role member --output
   ~/s37/invite-member`; in `XDG_CONFIG_HOME=~/s37/member-config` the second
   account accepts (`member-s37` or the operator's choice), logs in (no
   factor needed for a member), `bin/org.sh key-create --name walk
   --scopes organizations:read,projects:read --output ~/s37/member-key`,
   `bin/login.sh key --endpoint … --key-file ~/s37/member-key`, **`bin/project.sh
   list`** → the three projects; the agent then reads, with the same key,
   `curl -sS -X POST -H "Authorization: Bearer $(cat ~/s37/member-key)"
   https://control.agenticpostgresql.com/api/v1/projects` → `409
   not_available` naming `projects_self_service` (D2054) — the key read into a
   variable inside a script file, never typed, never echoed.
5. **Sheet PR1** — the administrator (W1's context) mints a second account
   invitation `--output ~/s37/invite-probe`; the agent runs
   `s37-probe-enrol.py` → `~/s37/probe.json` (0600).
6. **Sheet B1** — the reboot; the agent runs `s37-units.sh` (four units
   `active`) and reads the three doctors' first lines through `apg-diag`.
7. **Sheet S1** — the three op copies installed fresh, the sweep launched
   detached (`s37-launch.sh`). The agent waits for the exit file (CLAUDE.md
   §1: no watcher beside it), fetches `evidence/session-37-host.json`.
8. **The external half** from WSL: `s37-external.sh` (an ephemeral
   `ssh-agent`, `--ssh-destination op@62.238.99.122` for Session 4's two
   proofs; the customer proofs reach only `routes.control`, D2058).
9. **The merge**: `bin/write-session-evidence.py` (read its `--help`) over
   the offline half CI wrote for the deployed commit (`gh run download <id>
   -n session-01-evidence`, D2038's method) or `bin/session-37-check.sh
   --mode offline` at the deployed commit, the host half and the external
   half → `evidence/session-37.json`. **Expected: exit 5 for
   `documented_path` and `replacement_host_restore` only** (§7).
10. **The tag, from the workstation** (D2041): `git tag -a 1.15.0 <deployed
    sha> -F <message file>`; `git push origin 1.15.0`; `git ls-remote origin
    refs/tags/1.15.0` read back.

**Done.** *(the executor writes it: every claim's status from the merged
document, the walk's transcript locations, rows)*

### Run 12 — the close

**Code (the Ledger's rows, the envelope's) — `bin/session-01-check.sh` once and
CI.**

- **The Reality Ledger** (D2055): `accounts` → `beta`, evidence
  `[control_invitations, control_invitations_live]`; `organizations` → `beta`,
  `[control_roles, control_totp_live]`; `api_keys` → `beta`, `[control_keys,
  control_keys_live]`; `management_api` → `beta`, `[control_api_contract,
  control_plane_live]`; `cli_remote` → `beta`, `[control_cli,
  control_keys_live]` — **only rows whose every named claim reads `passed` in
  `evidence/session-37.json`**; a row whose claim did not pass stays `planned`
  and the Done says why. `controls` stays `[]` for all five (no operation type
  acts on them). `customer_text` rewritten for each to say what a person can
  do now, without a §59 word (the guard reads it).
  `bin/render-reality-ledger.py --write`.
- **`capacity.ENVELOPE`**: Session 37 rows read from the trip's files by
  `~/s37/s37-envelope.py` (Session 36's `s36-envelope.py` the model — never
  retyped), each naming the CX23 it ran on: **three projects on the CX23**
  (`free -m` before and after the control project, `doctor capacity`
  committed 912 of 1,600); **the control project's bring-up** (the wall time
  of C1–C3 and of the first full backup); **a 1.15.0 deploy per class** (R2's
  probe); **a cold start with three projects** (B1's units). `bin/render-capacity-envelope.py
  --write`.
- `docs/scope-closure.md` **§30** — what Session 37 closed, what it left,
  what Session 38 inherits (the shape of §29).
- `docs/plans/stage-5-plan.md`: the Status block re-read and rewritten
  (Session 37 done; **manifest schema 9 is `control`, so 38's `compute` is
  10**, D2044; next free numbers).
- CLAUDE.md §2 rewritten for Session 38's planner (copy it to the scratchpad
  first): the HOST block with three projects, the control endpoint, the
  script set `s37-*`, the probe and walk contexts in WSL `~/s37/`.
- The plan's header `Status:` set to COMPLETE with the rows each run added.

**Done.** *(the executor writes it)*

---

## 7. Evidence and claims

**Expected at the merge** (Run 11): **219 claims. Passed: everything that
passed at Session 36 — including `port_allocation` (declared after B1) and the
rotation trio (the four files re-declared, D2072) — plus the thirteen new
ones. `failed` 1: `documented_path`**, by decision (D1935; the person's walk
of the product is Session 42's — the day-2 walk here is the OPERATOR's and is
no substitute). **`not_run` 1: `replacement_host_restore`**, by D1028's
decision, unchanged. These are predictions: each claim is moved only by
evidence the sweep and the external half actually produce, and any that does
not is reported with its reason. Exit 5 for `documented_path` and
`replacement_host_restore` and no other reason.

**The three modes.** Offline: `bin/session-37-check.sh --mode offline` at the
deployed commit (74 claims). Host: S1 (`--control-outputs` added). External:
from WSL, with `--control-outputs` and `--control-probe-file` added — **the
first session whose external half carries customer claims**, proved through
`routes.control` only (D2058). Two live halves naming different commits do not
merge — deploy all three projects fully, THEN sweep.

---

## 8. Security invariants this session touches

| Invariant | How this session keeps it |
|---|---|
| **The control plane holds nothing that opens a project's data or admin plane** (ADR 0246) | The control mode reads no other project's document, URL or secret (`test_control_boundary`); the registry is written by a root verb from documents on disk; a key is refused at alpha's app and REST routes (`KEY-USE-001`) |
| **A product surface runs no SQL** | `/v1` takes no SQL, path or command; every body is a pydantic model with `extra="forbid"` |
| **PostgreSQL is the final authorization authority** | FORCE RLS on every control table, scoped by the caller (design G, rig 37b); no control function is executable by a request role (`CTL-SET-001`) |
| **A credential shown to a customer is shown once and stored hashed** | Invitation tokens and keys: SHA-256 of 256-bit secrets, shown once with `no-store`; passwords Argon2id; TOTP seeds the stated exception (ADR 0252) |
| **A revoked token stops on its next request, locally** | Every `/v1` request re-reads the caller's state (`authenticate`) and memberships; a key is looked up per request with its owner's current role |
| **No URL, key, token or caller value in a log line** | The request log prints the route TEMPLATE (`/v1/organizations/{org}/keys`), never a path; `test_no_seed_reaches_a_log_line`; the CLI never prints a secret to a non-TTY |
| **Nothing `planned` has a control** | No operation type accepted (`CTL-OPS-001`); the five rows move only with passed evidence (D2055) |
| **Projects share no project-scoped value** | `control-prod` compared with A and B live (`CTL-REG-002`) and in every offline collision count |
| **A report may not substitute an answer for a failure to determine one** (ADR 0195) | `bin/control.sh registry` reports *could not determine* and exits 6; the CLI exits 6 when the server cannot be read |
| **There is no public Postgres endpoint** | Still true: nothing here opens a port; `/v1` is HTTPS through the existing edge on 443 |

---

## 9. Stop conditions

Stop and ask the operator, without improvising, when:

- admission refuses the control project, or `s37-free.sh` reads `STOP`
  (available below 1,024 MiB) after its second deploy (D2042);
- the control project's certificate is not issued on the first attempt
  (D2064), or the DNS check fails;
- rig 37b shows neither design G nor design T can scope a member's reads
  without granting a request role anything;
- the control mode would need any credential, URL or document of another
  project, or a `/v1` route would need to reach alpha's or beta's plane;
- a widening beyond D2046's one statement form would be needed in the lint;
- `upgrade plan` prices 1.15.0 at `major`, or for a reason this plan did not
  name;
- a Ledger row would move to `beta` without its claims `passed` in the merged
  document, or an operation type would be accepted;
- `bootstrap-providers.sh --apply` fails after creating the Infisical project
  (it prints what it created; nothing is retried until the output is read,
  D1046);
- the sweep would run without `--after-reboot` after B1, or after a code
  commit past the deployed one;
- a currently-passing test would be weakened to make a new one pass;
- `--render-only` stops working with no host and no root.

---

## 10. Open items this session carries and creates

**Carried, untouched, each still true:** D2032 (the rescale — owed before
Session 38's profiles); beta's three rotations (D1995); D1936/D2005; D1547
(D1990); D2020/D2025 (two `host.yaml` copies); D2031; D1642, D1798, D1869,
D1871, D1722/D1806, D1784, D1792, ADR 0241's bound; D1045; D1375; D976; D688;
D771; D340; D466; D540; D942; D1203; D1205; D1211; the 24 unclaimed
requirements; `process-max` 1 (D593); `documented_path` (D1935);
`replacement_host_restore` (D1028).

**Created, and named so Session 38 does not inherit them silently:**

- **Accounts are never deleted or pruned** (D2065, D1986 again) — probe
  accounts accumulate with every sweep; the identity question is still open.
- **TOTP seeds are plaintext at rest** (ADR 0252) — encryption is `planned`.
- **No rate limit on `/v1/sessions` or invitation acceptance** — Argon2id's
  concurrency of two is the only throttle; ADR 0246's scope sentence puts
  rate limits on the creation paths (38).
- **Only one control project per host is assumed and nothing enforces it**
  (D2044) — `bin/control.sh` refuses two (exit 5); Session 38's reconciler
  will need the same rule.
- **Removing a project from the registry is a root `psql` DELETE** (Sheet A1's
  irreversible row) — `bin/control.sh` has no `forget` verb.
- **`/v1/ledger`, the operations' cancel route, `regions`, `notifications`,
  `apg project status`** — 38, 41, 42 (D2067).
- **The node-loss runbook's restore order** — the kit carries the control
  project from now on; *restore it first* is Session 42's sentence (D2069).
- **Manifest schema 9 is `control`** — Session 38's `compute` is schema 10
  (D2044).

---

## Appendix — what to consult, how a run is executed here, and the sheets

**Consult, in this order:** CLAUDE.md §1 (the shell traps — every one of them
has cost a run); this plan's §0, §1 and the run's own text; the reads its run
names. **The tree wins.**

**How a run is executed here**: CLAUDE.md §5. Every `sudo` line is the
operator's, on a sheet, under `script -q -e -c '…' /home/op/s37-<sheet>.txt`
when it execs into a container or deploys (D972, D1501), never piped or
redirected; `sudo -v` in the foreground first (D1376). Every `op` line is the
agent's over SSH. Remote loops go in a script file run with `ssh host 'bash -s'
< script`, which exports `PATH="$HOME/.local/bin:$PATH"`. **The workstation
sheets (W1–W3, PR1) are run by the operator in WSL** from
`~/projects/agentic-postgres` at the deployed commit (`. .venv/bin/activate`
first), each with its own `XDG_CONFIG_HOME`; a code is read off the
operator's phone and typed at the TTY.

**The sheets.** One outcome each; the next is issued only after the previous is
read (D1510). `<sha>` is never typed on a sheet: the agent fills the deployed
commit from `git rev-parse HEAD` on the host before handing it.

### Sheet E0 — readings before anything is built (Run 1; `sudo`; reads only)

```
sudo -v
sudo bash /home/op/s37-e0.sh      # tees /home/op/s37-e0.txt; changes nothing
```

### Sheet P1 — the providers, by hand at the consoles (any day before Run 10)

1. **Cloudflare DNS**: an `A` record `control.agenticpostgresql.com` →
   `62.238.99.122`, **DNS only (grey cloud)**.
2. **Cloudflare R2**: the bucket `apg-control-prod-backup` in the same location
   as alpha's backup bucket; an Account API token, *Object Read & Write*,
   scoped to that bucket only. Keep the key id and secret for Sheet P2's
   paste. **If Run 1's 37e said the storage pair is owed** (D2049): the bucket
   `apg-control-prod` and its own token the same way — nothing will write to
   it.
3. **Backblaze B2**: the bucket `apg-control-prod-backup-mirror` (private) in
   the same region as alpha's mirror, and an application key scoped to it.
4. Tell the agent which of 2's buckets you made and that 1 is saved.

### Sheet P2 — the control project's Infisical project (Run 10, day 1)

```
sudo -v
cd /home/op/agentic-postgres
bin/bootstrap-providers.sh --host host.yaml --project /home/op/control.yaml --plan
#   YOU: place the control-plane credential (two lines: client id, client secret):
sudo install -d -m 0700 /root/.config/agentic-postgres/bootstrap
sudo nano /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo chmod 0600 /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo bin/bootstrap-providers.sh --host host.yaml --project /home/op/control.yaml --apply \
     --operator-credential-file /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo shred -u /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo ls -la /root/.config/agentic-postgres/bootstrap/      # empty: no nano .save copy either (D2061)
#   YOU: in Infisical, project `control-prod`, the environment host.yaml names
#   (infisical.environment_slug -- `dev`, the same as alpha's and beta's, D2040),
#   paste each operator-supplied value `--plan` listed, by its folder and key:
#   the backup pair at /backup, the mirror pair at /backup, and -- only if P1
#   made the storage bucket -- the storage pair at /storage (create that folder).
#   Each value is pasted into the EXISTING key if --apply made it, else a new key.
```

### Sheet P3 — materialized (Run 10, day 1)

```
sudo bin/materialize-secrets.sh --project /home/op/control.yaml --requirements secrets.required.yaml --session 37
```

### Sheet R1 — the release priced (Run 10, day 1)

```
sudo bin/upgrade.sh check --project alpha-dev
sudo bin/upgrade.sh plan --project alpha-dev --candidate .generated/alpha-dev/outputs.json --json
sudo bin/upgrade.sh check --project beta-dev
sudo bin/upgrade.sh plan --project beta-dev --candidate .generated/beta-dev/outputs.json --json
```

### Sheets R2a / R2b — 1.15.0 deployed (Run 10, day 1)

```
script -q -e -c 'sudo ./deploy.sh --host host.yaml --project project.alpha.yaml --capabilities capabilities.yaml --through-session 37' /home/op/s37-r2-alpha.txt
script -q -e -c 'sudo ./deploy.sh --host host.yaml --project project.beta.yaml --capabilities capabilities.yaml --through-session 37' /home/op/s37-r2-beta.txt
```

### Sheet C1 — the control project's first deploy (Run 10, day 1)

```
# the agent has run s37-dns.sh: exit 0
sudo bin/admit.sh --host host.yaml --project /home/op/control.yaml
script -q -e -c 'sudo ./deploy.sh --host host.yaml --project /home/op/control.yaml --capabilities capabilities.yaml --through-session 37' /home/op/s37-c1.txt
```

### Sheet C2 — the first administrator (Run 10, day 1)

```
sudo bin/auth-admin.sh --outputs /etc/agentic-postgres/projects/control-prod/outputs.json \
     bootstrap --username control-admin --display-name "Control administrator"
#   YOU: the password, typed twice; then write the same password to a root-only file:
sudo install -m 0600 /dev/null /root/control-prod-administrator
sudo nano /root/control-prod-administrator
```

### Sheet C3 — ports, then deploy again (Run 10, day 1)

```
script -q -e -c 'sudo ./deploy.sh --host host.yaml --project /home/op/control.yaml --capabilities capabilities.yaml --render-runtime-only' /home/op/s37-c3a.txt
#   run the `sudo bin/database-ports.sh verify …` line it printed, exactly as printed
script -q -e -c 'sudo ./deploy.sh --host host.yaml --project /home/op/control.yaml --capabilities capabilities.yaml --through-session 37' /home/op/s37-c3b.txt
```

### Sheet C4 — enabled, read (Run 10, day 1)

```
sudo systemctl enable agentic-postgres-project@control-prod.service
systemctl is-enabled agentic-postgres-project@control-prod.service       # enabled
sudo bin/doctor.sh --project alpha-dev
sudo bin/doctor.sh --project beta-dev
sudo bin/doctor.sh --project control-prod
sudo bin/doctor.sh capacity --host host.yaml
bash /home/op/s37-free.sh                                                 # FITS
```

### Sheet C5 — the first full backup and the schedule (Run 10, day 1)

```
sudo bin/backup.sh --outputs /etc/agentic-postgres/projects/control-prod/outputs.json backup --type full
sudo bin/backup.sh --outputs /etc/agentic-postgres/projects/control-prod/outputs.json info
sudo bin/backup.sh --outputs /etc/agentic-postgres/projects/control-prod/outputs.json schedule enable
sudo bin/backup.sh --outputs /etc/agentic-postgres/projects/control-prod/outputs.json mirror
```

### Sheet K1 — the kit and the copies (Run 10, day 1)

```
sudo bin/dr-kit.sh export --host host.yaml --capabilities capabilities.yaml \
     --project project.alpha.yaml --project project.beta.yaml --project /home/op/control.yaml \
     --output /home/op/kit-<today>-s37
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/alpha-dev/outputs.json /home/op/alpha-dev-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/beta-dev/outputs.json /home/op/beta-dev-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/control-prod/outputs.json /home/op/control-prod-outputs.json
```

(`--output`'s ownership and mode as the previous kits; read `bin/dr-kit.sh
--help` before handing this sheet and correct the line to it.)

### Sheet V1 — the day verified, writing nothing (Run 10, day 1)

```
sudo bin/session-37-check.sh --mode host <the declarations s37-sweep.sh names, without --after-reboot> -k "session37 or session4_transports"
```

### Sheet W1 — the control administrator (Run 11, day 2; the WORKSTATION)

```
cd ~/projects/agentic-postgres && . .venv/bin/activate
export XDG_CONFIG_HOME=~/s37/admin-config
bin/login.sh password --endpoint https://control.agenticpostgresql.com/api/v1 --username control-admin
bin/login.sh totp-enroll            # the otpauth:// line: add it to your authenticator app
bin/login.sh totp-confirm           # type the 6-digit code
bin/login.sh password --endpoint https://control.agenticpostgresql.com/api/v1 --username control-admin
bin/org.sh invite --account --output ~/s37/invite-person
```

### Sheet W2 — your own account and your organisation (Run 11, day 2; the WORKSTATION)

```
export XDG_CONFIG_HOME=~/s37/person-config
bin/login.sh accept --endpoint https://control.agenticpostgresql.com/api/v1 --invitation-file ~/s37/invite-person --username ________
bin/login.sh password --endpoint https://control.agenticpostgresql.com/api/v1 --username ________
bin/login.sh totp-enroll && bin/login.sh totp-confirm
bin/login.sh password --endpoint https://control.agenticpostgresql.com/api/v1 --username ________
bin/org.sh create --name ________
bin/org.sh list                     # tell the agent the organisation id
```

### Sheet A1 — the registry (Run 11, day 2)

```
sudo bin/control.sh adopt --project alpha-dev    --organization <org id> --confirm control-prod
sudo bin/control.sh adopt --project beta-dev     --organization <org id> --confirm control-prod
sudo bin/control.sh adopt --project control-prod --organization <org id> --confirm control-prod
sudo bin/control.sh registry                     # agrees x3, exit 0
```

### Sheet W3 — a member, a key, the projects (Run 11, day 2; the WORKSTATION)

```
export XDG_CONFIG_HOME=~/s37/person-config
bin/org.sh invite --role member --output ~/s37/invite-member
export XDG_CONFIG_HOME=~/s37/member-config
bin/login.sh accept --endpoint https://control.agenticpostgresql.com/api/v1 --invitation-file ~/s37/invite-member --username ________
bin/login.sh password --endpoint https://control.agenticpostgresql.com/api/v1 --username ________
bin/org.sh key-create --name walk --scopes organizations:read,projects:read --output ~/s37/member-key
bin/login.sh key --endpoint https://control.agenticpostgresql.com/api/v1 --key-file ~/s37/member-key
bin/project.sh list                 # alpha-dev, beta-dev, control-prod
```

### Sheet PR1 — the probe's invitation (Run 11, day 2; the WORKSTATION)

```
export XDG_CONFIG_HOME=~/s37/admin-config
bin/login.sh password --endpoint https://control.agenticpostgresql.com/api/v1 --username control-admin   # with your code
bin/org.sh invite --account --output ~/s37/invite-probe
#   the agent then runs s37-probe-enrol.py, which writes ~/s37/probe.json (0600)
```

### Sheet B1 — the reboot (Run 11, day 2)

```
sudo systemctl reboot
```

### Sheet S1 — the one sweep (Run 11, day 2)

```
sudo -v
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/alpha-dev/outputs.json /home/op/alpha-dev-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/beta-dev/outputs.json /home/op/beta-dev-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/control-prod/outputs.json /home/op/control-prod-outputs.json
sudo bash /home/op/s37-launch.sh      # detaches /home/op/s37-sweep.sh and returns at once
```
