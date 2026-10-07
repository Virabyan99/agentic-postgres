# Session 37 — The control plane

**Status: COMPLETE 2026-10-07. Runs 1–3 DONE 2026-10-04, Runs 4–10 DONE 2026-10-06, Runs 11–12 DONE 2026-10-07; 1.15.0 tagged on c3eec1d. Rows D2042–D2072 written at planning and D2073–D2144 by executing it; ADRs 0251–0255. NEXT FREE: D2145, ADR 0256.** The second session
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
| **D2073** | D2046: a control-facility set may use `{{auth_service}}` *"in `GRANT EXECUTE ON FUNCTION … TO {{auth_service}}` and nowhere else"*; §9: *"a widening beyond D2046's one statement form would be needed in the lint"* is a stop. | **Rig 37b: `auth_service` has no `USAGE` on schema `app`** — every call to an `app.control_*` function, granted or not, failed `permission denied for schema app` (`USAGE` per role on the dev cluster: `auth_service` holds `app_private` and `public` only; migration 0001 grants `app` to `app_runtime` alone). The lint refuses `CREATE/ALTER/DROP SCHEMA` but not `GRANT USAGE ON SCHEMA`. With the grant made in the rig, design G worked in full, `auth_service` reading a control table directly was still `permission denied for table control_memberships`, and the only PUBLIC-executable function in `app` is `app.current_user_id()`. | **Stopped and asked (§9). The operator chose on 2026-10-04: a second statement form, `GRANT USAGE ON SCHEMA app TO {{auth_service}}`, permitted exactly and only in a control-facility set**, beside the function grant; every other set is refused both, and a control set naming `{{auth_service}}` in any other statement is refused. Run 2's lint test pins both forms and the refusal of a third. | Without `USAGE` no function in `app` is nameable by the role however it is granted; the alternatives (a released migration on every project; the functions in `public`) moved production or put the control plane in the schema every role can name. | **0251** |
| **D2074** | D2047: design G sets `app.control_org` inside a definer function *"ONLY after it has read the caller's own membership row"*; 37b (iii) asked whether that survives the function's return. | **It does.** `set_config('app.control_org', …, true)` inside a definer function with its own `SET search_path` clause was still readable after the call returned, for the rest of the transaction — and likewise without a clause. Also measured: the recursion control raises `42P17 infinite recursion detected in policy for relation "control_memberships"` at call time from PL/pgSQL and **at `CREATE FUNCTION` time** from a `LANGUAGE sql` body; design G returned 3 members to a member, 0 to a non-member (setting left empty), 0 to a non-member who preset the setting to the foreign organisation, and the caller's own organisation only; the `authenticated` role cannot name the function (schema refused first). | **Design G, with one rule added: every control function's FIRST statement is `PERFORM set_config('app.control_org', '', true)`**, before its membership read, and the control mode runs one transaction per request. Run 3's set test asserts a second call in one transaction by a non-member returns nothing after a member's call set the scope. | A scope that outlives its function is a scope the next function inherits; resetting it on entry makes each function's authority its own reading. | **0251** |
| **D2075** | D2059: the app router gains ``&& !PathPrefix(`{api}/app/v1`)``; the control router is ``Host(…) && PathPrefix(`{api}/v1`)``. | **Rig 37d, Traefik v3.7 at the pinned digest**: with ``!PathPrefix(`/api/app/v1`)``, `/api/app/v1/organizations` and `/api/app/v1` got Traefik's `404 page not found` and `/api/app/auth/me` reached the app as `/auth/me` — but `/api/app/v1x` was hidden too (a string prefix). ``!(Path(`/api/app/v1`) \|\| PathPrefix(`/api/app/v1/`))`` hid exactly `/api/app/v1` and below and passed `/api/app/v1x` to the app. The control (no negation): `/api/app/v1/organizations` reached the app as `/v1/organizations`. | **The rendered negation is ``!(Path(`{api}/app/v1`) \|\| PathPrefix(`{api}/app/v1/`))``, and the control router uses the app router's own shape, ``Host(…) && (Path(`{api}/v1`) \|\| PathPrefix(`{api}/v1/`))``** — the control router's form was not rigged and Run 2's rendered-label test plus Run 10's live probe of `/api/v1x` read it. | A negation wider than the address it removes takes paths nobody reviewed with it. | **0251** |
| **D2076** | Rig 37e's draft manifest: `api.rest.enabled: false`, `storage.enabled: false`, otherwise `project.example.yaml`'s values; D2048: does the render or the deploy require a PostgREST contract for a set that publishes nothing? | **The schema refused the first draft**: a disabled REST block must carry `allowed_cors_origins: []`, and a disabled storage block `account_id: null` and `allowed_cors_origins: []`. With those, `--render-only` exited 0 for a set with **no `contracts/` directory**, and `freeze-lock` wrote the set's lock (computed `follows_release_version 20261003120039`). The project-surface readers are `capability_manifest.py:312` (only with `mcp.capabilities`), `bin/migrate.py:801` (`propose` only), `dev_environment.py:425`, `bin/agent.py:123`, `bin/api-contract.py:416` — none on the deploy path for a project naming no capabilities. | **The control set ships no PostgREST contract** (D2048's first branch); `project.control.example.yaml` (Run 2) and `/home/op/control.yaml` carry the empty lists and the null account id. **The deploy is not read offline**: if Run 10's first deploy refuses for want of the contract, D2048's second branch applies. | The render is the half a rig can run; the deploy's half is named as a reading Run 10 owes. | 0251 |
| **D2077** | D2049: *"37e reads whether a storage-disabled project still owes [the R2 storage pair]"*. | **It does.** Read through `secrets_contract.active_secrets(contract, 36, facilities=enabled_facilities(manifest))` — the render's own `required_names` is `['session2_sentinel']` because `RENDER_SESSION` is 2 (D1825), so it cannot answer — the draft owes 20 secrets, six operator-supplied: `backup_r2_access_key_id`, `backup_r2_secret_access_key`, `mirror_s3_access_key_id`, `mirror_s3_secret_access_key`, **`r2_access_key_id`, `r2_secret_access_key`**. | **Sheet P1 creates the storage bucket `apg-control-prod` and its R2 token** like any project's, and Sheet P2 pastes the pair at `/storage` (D2049's "if it does" branch); adding a `storage` facility would move every project's secret contract and is not this session's. | A secret the contract owes and the provider lacks fails `materialize-secrets`, on the day, at the operator's console. | 0251 |
| **D2078** | D2049: accounts are `api_documentation` with `["meta:read"]` *"if rig 37e shows `_check_scopes` accepts it"*. | **Accepted by construction.** `scopes.ROLE_CLASSES["api_documentation"]` is `{introspection}` and `scopes.ceiling` adds exactly `meta:read` for it; the loader refuses any vocabulary without `meta:read` in `data` (`scopes.py:198-202`). Over the release vocabulary (`scope_registry.vocabulary_block()`, loaded through `scopes.load_vocabulary`) the ceiling read `['meta:read']`. | **D2049's first branch: a control account is an `api_documentation` user holding `["meta:read"]`.** | The narrowest authority the registry describes, and it is the same on every vocabulary a lock can carry. | 0251 |
| **D2079** | D2043: the control mode serves *"the probes the deploy and the doctor read (37e names them; expected `/auth/me` and `/auth/jwks.json`)"*. | **37e (iv)**: the only HTTP path anything in `bin/` or `src/` requests of an auth container is `{routes.app}/auth/me` (`bin/deploy-project.py:1525`, `observe_app`; `bin/studio.py:532` relays it too); `bin/doctor.py` requests none; the verification key set is a FILE written by `bin/render-jwks.py` and read through `/proc/<pid>/root` (ADR 0215), never a route; the container's healthcheck reads the health routes. | **The control mode serves `/health/live`, `/health/ready`, `/auth/me` and `/v1/*` — no `/auth/jwks.json`.** | A route nothing requests is surface nobody reviews. | **0251** |
| **D2080** | D2050: *"Confirming a factor revokes every session of the user (the refresh families, through the existing revocation function — 37e greps its name and grant)"*. | **`app_private.auth_revoke_user_sessions` is granted to nobody** — *"reached only from inside `auth_consume_password_reset`, so it needs no grant"* (0026:240-247). The refresh path re-reads only the subject's status and re-issues with the current versions (`service.py:937-949`), so moving `authz_version` does not end a refresh family. **`app_private.auth_list_sessions(uuid)` and `app_private.auth_revoke_session(uuid, uuid, refresh_revocation)` ARE granted to `auth_service`** (0024:263-270). | **Confirming a factor lists the user's sessions with `auth_list_sessions` and revokes each with `auth_revoke_session`, in the confirming transaction** (Run 4). No grant changes; no released migration. | Two granted functions already do what the ungranted one does; granting it would be a released migration for a loop. | **0252** |
| **D2081** | D2065: *"the operator can disable one with the control project's own admin path (Run 1's 37e names it: `bin/auth-admin.sh` verbs, read with `--help`)"*. | **`bin/auth-admin.sh` has two verbs, `bootstrap` and `list`** — none disables a user or resets a password — and `/admin/users` is not served in `control` mode (D2043). | **No product surface disables a control account in Session 37.** `docs/control-plane.md` (Run 9) says disabling one is a root call to `app_private.auth_set_status` on the control project's database, names derived from its deployed document — D1547's shape — and §10 carries it with D1986. | A sentence naming an admin path that does not exist is a documented step the operator cannot take. | 0252 |
| **D2082** | §1 D2042: Sheet E0 reads memory, the units and admission before anything is built; D2060: *"Sheet E0 reads `systemctl is-enabled` for both units and greps the plans for where it happened"*. | **E0, 2026-10-04 16:23:40Z, checkout `2538ac0`**: `free -m` total 3,814, used 1,594, **available 2,219 MiB**; the two projects' 20 containers plus the edge's two sum to ~1.2 GiB resident (each project ~610 MiB). `bin/admit.sh` against the draft control manifest: **admitted** — committed 608 MiB across 2 projects, requested 304 for `control-prod`, **safe available 992 MiB** (688 after the control project), free disk 20 GiB, 12 GiB above the reserve, ceilings 6,432 MiB. Units: both project units and the edge **enabled and active**; their `multi-user.target.wants` links are dated **Aug 7 06:12 (alpha) and 07:38 (beta)** — Session 2/3's day — and `grep -rn "systemctl enable"` finds no plan or guide that ever recorded it (only this plan's Sheet C5). Every file Session 36's S1 declared is present (`/root/s36-prev-*` ×3 with their `.json`, `/root/s36-redeploy-before.json`, `/root/alpha-dev-administrator`, `/home/op/kit-2026-09-11`, `/home/op/replacement-bootstrap-state.json`, `/home/op/s30-retired-alpha-dev-jwk.json`). Edge: ACME `production`, installed release `2538ac0`. | **No change to the plan's decisions**: D2042 proceeds (the 1,024 MiB floor is read again after the control project's second deploy); D2060 stands — the units were enabled by hand on 2026-08-07 and nothing recorded it; D2072's files exist. | Admission's answer and the machine's free memory were both read, as D2042 asked. | — |
| **D2083** | D2064: *"`dig +short control.agenticpostgresql.com @1.1.1.1` must print `62.238.99.122` … E0 (7) expected: nothing yet"*. | **The name already resolves — through a proxied WILDCARD.** E0's `getent hosts control.agenticpostgresql.com` printed two Cloudflare IPv6 addresses; from the workstation, `control.` AND an invented `zz-nonexistent-s37.` both resolve to `188.114.96.7`/`188.114.97.7` and `2a06:98c1:3120::7`/`2a06:98c1:3121::7` (Cloudflare's proxy), while `alpha-db.` resolves to `62.238.99.122` with no AAAA. So `*.agenticpostgresql.com` is an orange-cloud record. An explicit record for `control.` replaces the wildcard for that name for every type, but until it exists the name reaches Cloudflare over v4 and v6 — and an ACME HTTP-01 validator that prefers IPv6 would meet Cloudflare. `dig` is on the host, not in WSL. | **Sheet P1 creates the explicit `A control → 62.238.99.122`, DNS only, and nothing else; Sheet C1's check (Run 8's `s37-dns.sh`) requires `dig +short A` to print exactly `62.238.99.122` AND `dig +short AAAA` to print nothing**, from the host at `@1.1.1.1`, before the one deploy attempt. Whether the wildcard should exist at all is the operator's (it is outside the product; §10). | The plan's check would have passed on the A record while the wildcard's AAAA — had the explicit record been made as anything but an A-only name — sent a validator to Cloudflare; checking both types is the check that cannot be fooled by the wildcard. | — |
| **D2084** | D2061: E0 (5) expects the bootstrap directory *"empty or absent — the control-plane credential is placed on day 1"*; the docs say `--apply` shreds it. | **`/root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential` is present, 103 bytes, dated 2026-09-05 12:49** — Session 17's `gamma-dev` bring-up, the last `--apply`. It has lain on disk for a month, which is D2061's code reading (nothing shreds it) observed on the host. | **Sheet P2 first runs `--plan` with the EXISTING file**: if Infisical accepts it, no new credential is placed; if it is refused, the operator replaces it with a fresh one. **Either way the operator shreds it after `--apply`** (`sudo shred -u` and an `ls -la` reading empty), and Run 9's correction of the two guide sentences cites this row as the measured consequence. | A credential that outlives its use is the exposure D2061 predicted; the cheapest repair is the shred the guide already promises, done by the hand the code never was. | 0110 |
| **D2085** | Run 2 item 7: the example manifests are untouched; `project.control.example.yaml` is the schema-9 example. | `test_project_manifest.py::test_example_manifest_is_valid` asserts both fixtures are at `max(SUPPORTED_PROJECT_SCHEMA_VERSIONS)` (D927's lesson), so adding 9 forced both to 9; the outputs bump moved every pin that named 19. | **`project.example.yaml` and `project.second.example.yaml` move to schema 9 WITHOUT `control`** (each gains a header paragraph). Pins moved, none weakened: manifest 8→9 in `test_project_manifest.py` (two), `test_connector_facility.py`, `test_deploy_connectors.py`, `test_project_agent_surface.py`; outputs 19→20 in `test_connector_facility.py`, `test_disaster_kit.py::_previous_version` (now subtracts `control` and `routes.control`), `test_output_migrations.py` (`test_the_chain_ends_at_version_19_…` renamed `…_20_…`, its registry node id moved in the same commit, `docs/acceptance-matrix.md` regenerated). Both fixtures re-rendered: outputs 20, `routes.control` named, `control.enabled: false`, `AUTH_APP_MODE=auth`. | A fixture below the newest version stops exercising the shape the compiler reads. | 0251 |
| **D2086** | D2046 item 2: `{{auth_service}}` accepted only in a statement matching `^GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+.+\s+TO\s+\{\{auth_service\}\}\s*$`. | **The lint allowlists placeholder SOURCES, not names** (`migrations.py:815-843`): the name is the adopter's, `database.roles.auth_service` is what reaches the SQL. And the plan's `.+` admits a function in any schema. | **`CONTROL_PLACEHOLDER_SOURCE = "database.roles.auth_service"` is allowed only with `control=True`; every use of a placeholder bound to it must be, as the whole statement between its semicolons, `GRANT EXECUTE ON FUNCTION app.<name>(...) TO {{name}}` or `GRANT USAGE ON SCHEMA app TO {{name}}` (D2073) — sole grantee, no `WITH GRANT OPTION`, `app` only — and a use inside a dollar-quoted body is refused outright.** Without the facility the refusal names it (an adopter who copied the grant learns why). Four callers pass the facility: the render (from the rendered document), `bin/migrate.py` freeze/verify (`_control_facility`, from the manifest) and propose. Eleven refused arms proved, each beside the unmutated set. | A grant to the identity service of a function in `api`, or inside a `format()`, is a door the two forms were chosen to keep shut. | **0251** |
| **D2087** | Run 2 items 4–5: the deployed branch observes `routes.control`; `_control_labels` beside `_app_labels`. | `build_deployed_document` takes every route status as a required keyword (no defaults, by design); `build_override` has ~25 test call sites; `build_compose_env` is handed manifest BLOCKS, not the manifest; a slice of `route_control_path` at a call site would be a second derivation. | **`control_status` is REQUIRED** (six test callers pass `"unavailable"`); a new coherence rule refuses a `ready` `routes.control` while `control.enabled` is false. **`build_override`/`render_override` take `control: bool = False` and the two names defaulting empty** (refused if `control` without both) — the precedent is `project_migrations`; the deploy reads all three from the rendered `compose.env` (`_override_control`: the facility is `AUTH_APP_MODE == control`), so the mode and the labels cannot disagree. `build_compose_env(..., *, control=False)`, passed `config.control_enabled(project)` by the render. `naming.ProjectIdentity.route_control_strip_path` (= the API base path) is what `API_CONTROL_PATH` renders. `observe_control` (401 on an anonymous `GET {routes.control}/me` is `ready`) is NOT gated on an administrator, unlike `observe_app` (D230): the route refuses an anonymous caller whether or not anyone can log in. | Defaults where the house refuses them would be a status nobody observed; required arguments where nothing changes would be churn in 25 files. | 0251 |
| **D2088** | D2045: outputs 20 adds `routes.control`; ADR 0241's reader reads 20 and 19. | The rendered-document migrator must produce `routes.control` for an archived 19 document without inventing a host; `output_migrations` imports nothing from `naming` (it writes `HEALTH_ROUTE_PATH` itself). | **`migrate_v19_to_v20(document)` takes no argument**: `control: {enabled: false}` and `routes.control` = the document's own `routes.app` with `/app` replaced by `/v1`; a `routes.app` not ending in `/app` is refused. Its two suffix constants are tied to `naming.APP_PATH_SUFFIX`/`CONTROL_PATH_SUFFIX` by `test_v20_derives_the_control_route_from_the_app_route`. `READABLE_PREVIOUS_VERSION` moves to 19 by construction. | An archived document already names its host; deriving from it is the one value the step may compute. | 0241 |
| **D2089** | — | Run 2 rendered the control router for the first time; no project in `.generated/` enables the facility, and `projects/control/` does not exist until Run 3, so no RENDER of a control project ran — the labels, the compose variables and the outputs members were proved by calling `build_override`, `build_compose_env` and `build_outputs` directly. | **Run 3 owes the first full render of `project.control.example.yaml`** (with its set) and asserts the rendered `compose.env` and override from the files on disk; Run 10's deploy is the first time Traefik reads them. | A builder proved in isolation and never rendered is question 2 in §7 of CLAUDE.md. | — |
| **D2090** | CLAUDE.md §1: the harness kills background tasks when the laptop is low on memory. | **WSL stopped answering three times in Runs 1–2** (`Wsl/Service/0x8007274c`). Measured: `vmmemWSL` 6.9 GB of 15.7 GB RAM (WSL saw 7.6 GB, 5.3 GB of it page cache); Docker held **4,290 volumes, 206 GB, 99 % reclaimable** — the anonymous data volume every Docker-backed test and rig left behind — plus 20.2 GB of images and 8.7 GB of build cache, in a 176.4 GB `docker_data.vhdx`. | **With the operator's consent, 2026-10-04:** `docker volume prune -f` (205.9 GB; named volumes and the three attached kept), `docker builder prune -f` (4.2 GB), 32 unpinned project images removed (every image `versions.env` pins kept and checked present; other projects' images untouched); the operator compacted the VHDX as administrator (176.4 → 20.7 GB). **`C:\Users\gmpar\.wslconfig`: `memory=6GB`, `swap=4GB`, `autoMemoryReclaim=gradual`** — WSL now reads 5,926 MiB total and 4,096 swap. A later session that sees WSL drop reads `docker system df` first. | The volumes are the cost of every proof that starts a throwaway cluster; nothing in the suite removes them. | — |
| **D2091** | Run 2's targeted list (28 modules, the plan's plus every module the diff touched). | **CI red on `45a2a14`** (run 37224201524; Session 1 gate and Session 2 offline contract, 1 failed each of ~7,030): `test_doctor_redaction.py::test_every_schema_block_is_classified_by_this_file` requires every top-level block of the deployed document in `PRINTABLE_BLOCKS` or `SENSITIVE_BLOCKS`, and outputs 20's `control` was in neither. The module reads the outputs schema and touched nothing in the diff, so a targeted list derived from the diff could not see it (D1486's shape). | **`control` is PRINTABLE** (one boolean, no credential or address -- `connectors`' classification and reason); repaired in the next commit, module re-run locally. **A run that adds a top-level deployed-document member adds `test_doctor_redaction` to its targeted list.** | The guard did its job; the list was the defect. | 0251 |
| **D2092** | Run 2 item 7: `project.control.example.yaml` has slug `control`, environment `prod`, domain `control.example.test`. | That derives the key **`control-prod` -- the real deployment's**. A proof that renders the example publishes `.generated/control-prod` and must delete it (CLAUDE.md §1); on the host, where the operator's `/home/op/control.yaml` renders to the same directory, the cleanup would delete the deployed project's render source. | **The example is slug `fixture-control`, environment `dev` (key `fixture-control-dev`, domain `fixture-control-dev.test`)** -- the fixtures' naming. Still not a gate fixture (`FIXTURE_KEYS` unchanged). | An example that shares a key with production turns every test cleanup into a production edit. | 0251 |
| **D2093** | Run 3 item 1/3: `control_totp_reset`, `control_adopt_project`, `control_registry_rows` are definer functions **granted to nobody**. | Owned by `{{object_owner}}` and SECURITY DEFINER, they would run as the owner, under FORCE row security, with no caller to scope by -- a reset that must find a user by name would read nothing. The bootstrap superuser is the one role row security does not bind. | **The three are SECURITY INVOKER and granted to nobody**: only the superuser (`docker exec … psql -U postgres`, `bin/control.sh`) executes them, and it reads every row by being the superuser. Proved: `test_the_operator_functions_are_executable_by_no_role` (no role, the identity service included, executes them); `test_a_non_member_sees_nothing` adopts a project through `control_adopt_project` as the superuser. | Granting nobody is the control; invoker rights are what make the function usable by the one caller allowed. | 0251 |
| **D2094** | Run 3 item 2: `control_keys` has `FOREIGN KEY (organization_id, user_id) REFERENCES control_memberships ON DELETE NO ACTION`, and *"the removal function revokes, then deletes the membership"*. | A revoked key still references its membership, so NO ACTION refuses the delete -- the two sentences cannot both hold. | **A key references `control_organizations(id)` and `control_accounts(user_id)` separately**; `control_remove_member` revokes the member's keys and then deletes the membership; `control_key_lookup` joins the CURRENT membership and returns `member_role` NULL once the member left, so even an unrevoked key finds no role. Revoked keys remain as history. | A foreign key that forbids the documented removal would have surfaced as an error on the first `DELETE /v1/organizations/{org}/members/{id}`. | 0253 |
| **D2095** | Run 3 item 1: `control_set_member_role` updates the membership's `role`. | **The project lint refused the set**: `SET_ROLE = \bSET\s+(?:LOCAL\s+)?ROLE\b` matched `UPDATE app.control_memberships SET role = p_role` -- a column named `role`, read as a role switch. | **The one statement quotes the column, `SET "role" = p_role`**, with a comment saying why; the lint is not widened (a boundary that refuses a false positive is working). | Loosening the pattern to spare a column name would open a door to the thing it guards. | — |
| **D2096** | Plan §0: *"`test_every_committed_project_set_still_passes` (`:1111`) globs `projects/*/migrations/manifest.json`, so `projects/control` is linted by construction"*. | It lints every set WITHOUT the facility, so the control set -- which passes only with it -- fails it. | **The test now lints each set with the facility of the committed example manifest(s) naming it, and fails a set that no committed manifest names**, and asserts the control set is named by a manifest enabling the facility. Stricter than the glob: a set nobody can render is now a failure. | The facility is read from a manifest at every real caller; the test reads it the same way. | 0251 |
| **D2097** | ADR 0251 item 6 / D2048: if a reader refuses a set with no contract, widen that one reader to accept a set that creates no `api` object, with a stricter test beside it. | **The reader that refused is a test**: `test_the_project_reader_finds_every_object_the_project_contract_names` (TEN-SURF-001) loads every set's `contracts/postgrest-api-surface.yaml`. The render and the deploy path do not (rig 37e, D2076). | **Widened exactly as ADR 0251 says**: `_publishes_nothing_and_carries_no_contract(root, published)` -- a set with no contract must publish nothing in `api` (asserted), and every set with one is compared both ways as before; the loop also asserts at least one set carries a contract. **Stricter half**: `test_a_set_that_publishes_without_a_contract_is_refused` -- the control set copied, one `CREATE VIEW api.control_projects` added, refused by name. | ADR 0050's invariant (nothing in `api` the contract does not name) holds for the control set because it publishes nothing. | 0251, 0050 |
| **D2098** | — | **The existing cluster fixtures remove their container with `docker rm -f` and no `-v`** (`test_auth_endpoints.py:271` and its siblings), leaving the anonymous data volume behind on every run -- the source of D2090's 4,290 volumes. | **`tests/contract/control_cluster.py` removes with `docker rm -fv`**, and Run 3's battery reports `leaked clusters: none`. The older fixtures are not edited in this run (a test-wide change outside Run 3's subject); **§10 carries it**, and a later run that touches a fixture adds `-v`. | The workstation cost of every Docker-backed proof is a volume, until the fixture says otherwise. | — |
| **D2099** | Run 3 item 1: invitations -- an account invitation needs `admin_users:write`. Battery M2: *"`GRANT … TO {{authenticated}}` added on `control_list_members`"*. | The registry administrator's authority is a SCOPE on their token, which the database cannot read; and the control set declares no `authenticated` placeholder, so the plan's M2 would fail to render rather than reach the test. | **`control_mint_invitation` with a NULL organisation records `issued_by` and trusts the control mode to have checked `admin_users:write` and an enabled factor** (Run 4's route proof, CTL-INV-001, owes it; the function's comment says so). **M2 grants `control_list_members` to `PUBLIC`** -- the same class (a request-reachable grant) the test exists to refuse. | A check the database cannot make is named where it is made instead. | 0252 |
| **D2100** | — | **CI red on `89655ed`** (run 37227231821): the Session 1 gate PASSED and the Session 2 offline contract job failed 1 of 7,039 -- `test_auth_endpoints.py::test_a_value_outside_its_contract_is_refused_and_never_clamped[agent_id=not-a-uuid-…]` with `duplicate key … users_username_normalised_key (auditor-73424)`. Pre-existing and unrelated to Run 3: two parametrised tests name their user `auditor-{abs(hash(query)) % 100000}`, and string hashes are randomised per process, so two cases can share a name inside the module's one cluster. | **Both names take a uuid suffix** (`uuid4().hex[:12]`); the assertions are unchanged. The 17 selected cases re-run locally: 17 passed. | A proof that fails one CI run in a few hundred for a reason it does not test teaches a reader to re-run instead of read. | — |
| **D2101** | D2050: *"Confirming a factor revokes every session of the user (the refresh families …), so no token minted without the code outlives enrolment"*; D2080: list and revoke with the two granted functions. | Ending the refresh families ends every SESSION, but an access token minted before enrolment stays valid until its `exp` (at most 930 s). The only granted functions that move `authz_version` are `app_private.auth_set_status` and `auth_set_authorization`, and each writes a whole value: re-writing the caller's status or role would undo an administrator's disable or role change made between the authentication and the write. | **Confirming lists the sessions with `auth_list_sessions` and ends each live one with `auth_revoke_session` (reason `credential_changed`), in the confirming transaction (`ControlRepository.confirm_factor`) -- and moves no version.** The token that confirmed lives out its at most 930 s; `confirm_factor`'s docstring and the route's description say so, and the response tells the client to log in again. | A residual bounded by the token's own lifetime is cheaper than a write that can re-enable a disabled account. | **0252** |
| **D2102** | Run 4 item 3: `provisioning_uri` uses *"`urllib.parse.quote` for the label"*. | `test_every_transport_in_the_service_is_declared_with_a_reason` (ADR 0124) refuses any module of the service that names `urllib` without a row in its transport allowlist -- it FAILED on `app/totp.py` at the first targeted run. | **`totp.py` percent-encodes the label itself** (`_percent_encoded`: RFC 3986's unreserved characters kept, every other byte of the UTF-8 encoding as `%XX`), proved by `test_the_enrolment_uri_carries_the_seed_and_the_fixed_parameters` (a space becomes `%20`). The allowlist is not widened. | A transport row for a module that makes no request would be the guard loosened, not widened (CLAUDE.md §6). | 0124 |
| **D2103** | Run 4 item 6: `DELETE /v1/sessions/current`; D2066: *"`apg logout` revokes the session server-side … and removes `session.json`"*, whose only secret is the refresh token -- *"the access token is never written"*. | An access token names no session (`auth_list_sessions` is keyed by user, a family id travels in no token), and the CLI holds no access token to present. The release has no function that finds a family by its refresh token without consuming it. | **`DELETE /v1/sessions/current` takes `{"refresh_token"}` in its body and no bearer**: the token is presented to `auth_consume_refresh_token` (which returns the family and the user whether or not it rotated) and that family is ended with `auth_revoke_session(..., 'logged_out')`; the successor the exchange minted dies with it. 204 whatever the token named, `end_session`'s rule; a malformed token is `400`. | Presenting the refresh token is the proof of the session; a logout that needed a live access token would fail exactly when the CLI has none. | **0253** |
| **D2104** | D2051: *"A username already taken is refused only AFTER the token validated, with the token left unspent (the transaction rolls back)"*; acceptance in one transaction. | `auth_create_user` is the first statement and raises `unique_violation` before the token is read; no function reads an invitation without spending it. And psycopg opens a `transaction()` block on an IDLE connection with `BEGIN … COMMIT`, not a savepoint -- so a savepoint around the user insert, written first, would have committed the new user on its own. | **`ControlRepository.accept_as_new`**: one statement first (so the block below is a SAVEPOINT inside the request's transaction), the user insert in that savepoint; on a taken name the spend is still attempted for a throwaway id no account carries, purely to learn whether the token is good, and the transaction is rolled back by raising -- `invitation_invalid` if the spend refused, `username_taken` if it matched (a membership invitation then fails its account foreign key, which is the match). Battery M6 removes the first statement and `test_acceptance_is_one_transaction` FAILED (an account left behind by a refused token). | The order D2051 asks for, inside the one transaction D2051 asks for, with the one psycopg behaviour that would have broken it named and killed. | **0252** |
| **D2105** | Run 4 item 6: the new error codes are `second_factor_required`, `second_factor_invalid`, `invitation_invalid`, `username_taken`, `last_owner`, `human_session_required`, `not_available`. | The control set's `control_totp_begin` raises `AP409: factor_enabled` (Run 3); a 404 needs a word (`AP404: not_found`); and confirming a factor is an AUTHENTICATED call, where a `401` would read to a client as *your token is bad*. | **`errors.CONTROL_STATUS` adds `not_found` (404) and `factor_enabled` (409)**; one `ControlRefused(word, status=…)` carries every refusal; **a wrong code at `POST /v1/me/totp/confirm` is `422 second_factor_invalid`** (`401` only at login). `second_factor_required` is 401 at login and 403 at the gate, as D2050 says. An `APnnn: <word>` the table does not name is not translated -- it propagates. | Every word a function can raise has one answer, and no database message is relayed (D433). | **0251** |
| **D2106** | Run 4 battery: *"(M6) `auth_create_user` moved after the acceptance and its error swallowed"*; *"(M7) an admin allowed to invite an owner → the matrix FAILED"*. | M6's shape does not exist in the code (D2104's order is create, then spend). M7 in Python alone cannot be seen through the API: `control_mint_invitation` and `control_set_member_role` refuse an admin granting `owner` in the database as well. | **M6 is D2104's equivalent defect** (the user insert committing on its own) -- KILLED. **M7 is run twice**: M7a, Python only, expected and observed to SURVIVE (the set's own check answers 403); M7b, Python and both SQL checks, KILLED by `test_an_admin_cannot_make_an_owner`. | A survivor that is the second layer working is evidence of the layer (D493); the mutation that removes both is the one the test can see. | **0252** |
| **D2107** | Run 4 item 1: `load(mode="control")` *"forbids what auth forbids"*; item 2: the probe routes *"mounted from `routes.router`'s handlers by NAME"*. | `settings.FORBIDDEN_VARIABLES` is iterated by `test_each_mode_is_denied_the_other_s_credential_settings` as COMPOSE SERVICE names, so a `control` key would look up a service that does not exist. FastAPI's `add_api_route` takes the handler object itself. | **`control` takes `load`'s auth branch** (one branch, so the two cannot drift) and `FORBIDDEN_VARIABLES` gains no key; `test_the_control_mode_reads_exactly_what_auth_reads` proves the parity: equal `Settings` from one environment, every required variable refused by both when absent, every auth-forbidden variable refused by both. **`/auth/me` is `add_api_route("/auth/me", routes.me, include_in_schema=False)`** -- the release's handler, out of the management API's document, which is `/v1` alone (D2057). | A parity proved by behaviour holds whichever list a later session edits. | **0251** |
| **D2108** | D2051: a membership invitation *"creates the account if the caller has none"*; Run 4 item 6: the routes. | A person who already has an account needs to accept a membership invitation without creating a second one; and an invitation id in a revocation path is the same kind of oracle an organisation id is. | **`POST /v1/invitations/accept` has two shapes**: with a bearer, the token alone (`accept_as_existing`: the display row, then the spend; an account invitation accepted this way is spent to no effect); without, the token and the account (`accept_as_new`). **`DELETE …/invitations/{id}` answers 204 whether or not an unspent invitation had that id**, and a path id that is not a uuid is `404 not_found` like a missing one. | One route for the person with an account and the person without; no id in a path says whether it exists. | **0252** |
| **D2109** | Run 5 item 1: *"effective scopes = key scopes ∩ the role's (`control_roles.ROLE_SCOPES`)"*; §2 `KEY-MINT-001`: `test_a_demotion_narrows_a_key`; battery M2 kills it. | D2053 gives viewer and member the same reads and admin and owner only human acts, so in Session 37 every role grants all four key scopes: the intersection narrows nothing a live call can observe, and a demotion through the API leaves a key's reach unchanged. | **`ROLE_SCOPES` grants every role the whole vocabulary (D2053, faithful), and `effective_scopes` intersects anyway, on every request.** `test_a_demotion_narrows_a_key` and the role half of `test_scopes_are_bounded_by_the_vocabulary_and_the_role` patch `ROLE_SCOPES` (viewer, then member, without `members:read`) and drive the real routes against the real cluster; the second test also ASSERTS today's table is uniform, so the day Session 38 differentiates it the module is read again. M2 KILLED. | The mechanism the plan names exists and is proved; inventing a role difference D2053 decided against would be a product change made to give a test something to see. | **0253** |
| **D2110** | Run 5 item 3: *"`src/agentic_postgres/operations.py` … `control_routes` imports `operations`"*; the service *"imports the table, never the file"*. | The auth image is built from `services/auth-api` alone (`COPY app /app/app`); nothing in it can import `src/` (ADR 0084, `service_source.py`). And the image cannot read the ledger file to compute *accepted*. | **The table lives in `services/auth-api/app/operations.py`** (standard library only, with `ACCEPTED_TYPES`, empty) and **`src/agentic_postgres/operations.py` loads it through `service_source.load`**, adding `accepted(type, ledger)` and `row_status`. The guard requires `ACCEPTED_TYPES` to equal the ledger's answer for every type, so a row moved without the service, or the reverse, fails it (M4 KILLED). `test_auth_service_shape.SHARED_MODULES` gains `operations`, which puts it under the standard-library rule. Run 3's frozen comment naming `src/agentic_postgres/operations.py` stays (D912) and is still true -- that module carries the table. | ADR 0084's one file imported by both planes, rather than a copy or a service that reads a document to decide what exists. | **0254**, 0084 |
| **D2111** | Run 5 item 2: the key routes; *"a foreign or missing … key … → the SAME 404"*; D2052: *"credential-minting routes are human-session only"*. | The control set's functions scope by the KEY OWNER's memberships, so a member of two organisations' key would read both through `control_list_organizations` and `control_list_projects`. Listing keys is not minting, but it is the keys surface. Run 4 answers an invitation revoke 204 either way (D2108). | **A key reaches only `control_roles.KEY_SCOPES`' seven read routes**; every other route -- listing keys included -- is `403 human_session_required`. **A key principal's roles are its ONE organisation**, and every list the database returns is filtered to the caller's organisations as the request computed them (`test_a_key_reaches_no_other_organisation`: a member of A and B, a key minted in A sees A alone; the member's session sees both). **`DELETE …/keys/{id}` answers 404** for a key the caller may not revoke, a missing one, an already revoked one and a malformed id, as the plan says -- unlike the invitation revoke's 204 (D2108), which stands; the asymmetry is recorded, not reconciled. | The database's scope is the owner; the key's scope is narrower, and only the service knows which organisation the key was minted in. | **0253** |
| **D2112** | Run 5: *"The `LEDGER-001` node id renamed in this run is registered in Run 9 … if [`test_acceptance_registry`] refuses the missing node now, move `LEDGER-001`'s node ids IN THIS RUN"*; battery M4: *"in a COPY of the Ledger the test is pointed at"*. | `test_every_registered_node_id_is_collectible` refuses a registered node id pytest cannot collect. `reality_ledger.load()` takes a path but the guard reads the module default, and `load` does not validate, so a mutated status reaches the guard. | **`LEDGER-001`'s node `test_the_sets_the_guard_will_read_are_empty_today` is replaced by `test_no_console_exists_yet` in this run**, its description says the operation-type half is a guard of its own, and `docs/acceptance-matrix.md` and `docs/product-contract.md` are regenerated. The new guard's node is CTL-OPS-001's, registered in Run 9. **M4 mutates `docs/reality-ledger.yaml` itself**, snapshotted and restored by copy and `cmp`-checked like every other battery file. | The registry may not name a node that does not exist for four runs; and a restored mutation of the real file is the same evidence as a pointed-at copy. | **0254** |
| **D2113** | Run 5 item 5: *"`--update` gains `--snapshot app/control` (default `app`); `--check` compares both"*. | `bin/app-contract.sh` is the wrapper every gate calls with `--check` alone. | **`--snapshot` is accepted with `--update` only** (the wrapper refuses it beside `--check`, exit 2); `--check` compares both, prints a line per snapshot, and on a difference names the snapshot and the `--update --snapshot NAME` that re-captures it; a missing snapshot is exit 5, a disagreement exit 6. The control document keeps the `/v1` paths and the schemas they reference, to a fixed point; it is ASCII. | Every existing caller is unchanged, and the gate reads the management API's document without learning a new flag. | **0253** |
| **D2114** | Run 5 item 3: `src/agentic_postgres/operations.py` with *"a loader that reads `docs/reality-ledger.yaml` for the TEST only"*. | **CI red on `47c65a0`** (run 37446073568; both jobs, 1 failed each of ~7,070): `test_repository_contract.py::test_no_module_is_imported_only_by_its_own_tests` -- *"['operations'] are imported by nothing outside their own tests. A module with no caller is a feature that does not exist"* (D204). The plan designed a test-only module, which the repository's own guard forbids; the targeted list did not include that module (the diff touched nothing it reads -- D1486's shape again). | **The module gains a real reader**: `reality_ledger.render` writes, under each concept, the `/api/v1` operation types that act on it and whether the control plane accepts them (`ACCEPTED_TYPES`) -- `docs/reality-ledger.md` regenerated, eight concepts now say *refused (`409 not_available`) until this concept is available or in beta*. The guard is not widened. Failing module re-run with its readers: 304 passed. **A run that adds a module under `src/agentic_postgres/` adds `test_repository_contract` to its targeted list.** | The page a reader opens to learn what a concept is now also says which API operations it gates -- a reader the table needed anyway; deleting the module would have left Run 3's frozen comment naming a file that does not exist. | **0254** |
| **D2115** | Run 6 Tests: *"a fake `docker` on `PATH` as `test_record_command.py` does"*. | `test_record_command.py` puts nothing on `PATH`: it loads `bin/record.py` as a module and replaces its one outward edge, `container_exec.run`, with a recorder that answers from a script and keeps every call. | **The tree's pattern**: `test_control_command.py` replaces `container_exec.run` and `require_root` the same way, and `read_deployed_document` with a stand-in that reads versions 19 and 20 and raises for any other, as `UnreadableVersion` does. Root is proved against the real `require_root` with the uid read as a user's. A sixth proof, `test_every_exec_goes_through_container_exec`, scans the command for any other way to start a process (its control: the scan finds `container_exec.run(`); **Run 9 registers it under `CTL-REG-001` beside §2's five.** | A recorder can say what was and was NOT sent; a fake binary on `PATH` would prove the argv `container_exec` builds, which `test_container_exec` already owns. | 0218 |
| **D2116** | Run 6: the control project found as *"the one directory … whose deployed document carries the control facility … none → exit 3 … two → exit 5 naming both"*. | Two cases the plan does not name. **Alpha and beta are at 1.14.0, whose outputs 19 has no `control` member** -- absent, not false. And a document that cannot be read might BE the control project, so *one found* is not *the one*. | **Outputs 19 enables nothing** (`CONTROL_SINCE_VERSION = 20`: a release with no control plane wrote it); a malformed `control` member at any version is unreadable. **An unreadable document stops a decision**: `adopt` and `totp-reset` exit 6 naming it rather than act on a search they could not finish; `registry`, a report, proceeds when exactly one document enables the facility and reports the unreadable one as *could not determine*. None found with something unreadable is 6, not 3. Battery M3 (found by name) and M4 (`adopt` searching as a report) are killed. | ADR 0195: a decision may fail closed, a report may not -- the same search answers both, at the strictness each needs. | 0195, 0251 |
| **D2117** | Run 6: *"Exit 0 all agree; 5 any difference; 6 any undetermined"*; the five outcomes. | The plan does not order 5 and 6 when a reading has both, nor say what a state-root directory with no `outputs.json` and no row is, nor what `adopt` does with a document it cannot read. | **6 wins over 5**: a report with an undetermined line is incomplete, and 5 would claim the differences printed are the only problems. **`no deployed document` is a difference (5)** whether or not a row names the key -- a directory the deploy established with no document is something to look at (`fleet` reports the same directory). **`adopt` refuses an unreadable or incomplete target document with 3** (`record.py`'s precedent for a document it cannot use), and a document whose `project.key` is not its directory's name is unreadable for both verbs. The registry is read as ONE `json_agg` line, not a delimited table. | Each is a choice between two defensible readings; written here so Run 8's sheet and the operator guide state one. | 0195 |
| **D2118** | Run 6: *"`totp-reset` calls `control_totp_reset(:'username')` and prints whether a factor was removed"*. | `control_totp_reset` (`0001-control-identity.sql:614-623`) returns `FOUND` after a `DELETE` keyed by a subquery on the username: **false for an account with no factor and for no account at all** -- the function cannot tell them apart. | **The `false` sentence says both**: *"no second factor is enrolled for NAME (or no account has that name); nothing was removed"*, exit 0. An answer that is neither `t` nor `f` is *whether a factor was removed is not known*, exit 6; a database error is printed verbatim, exit 5. `--username` is any printable name up to 128 characters, passed as a `psql` variable. | Telling the two apart would need a new migration for one sentence (fix forward, D912); an organisation's member list already names every account in it. | 0252 |
| **D2119** | Run 7 usage: *"`bin/login.sh accept --endpoint URL --invitation-file FILE --username NAME [--display-name TEXT] [--password-file FILE]`"*. | `POST /v1/invitations/accept` has two shapes (`control_routes.py:361-396`): signed in, the token alone joins the caller to the organisation; otherwise all four of token, username, display name and password. The plan's usage reaches only the second, so a person who already has an account -- the operator after D2051's account invitation, invited into an organisation -- could not join one from the CLI; and `--display-name` is optional in the usage but required by the server. | **Two forms**: `accept --invitation-file FILE` alone uses the context's person session (a key context is exit 3); with `--username` it creates the account and then **logs in with the same password**, writing the session and the context (the organisation the invitation named). `--display-name` defaults to the username. A new password from a TTY is asked twice. | The route already serves both; a CLI that reaches half of it sends the other half to curl. | 0251 |
| **D2120** | D2066: the state holds *"EITHER `key_file` … OR `session: true`"*; `apg logout` revokes the session; *"a key context is forgotten, never revoked"*. | The plan does not say what a login does while a session is already held -- overwriting `session.json` would drop a live refresh token on the floor, valid for its 30 days -- nor how a key login learns whether the key works, when a key may hold no `organizations:read` and `/me` is human-only. | **A login refuses while a session is held** (exit 2: *end it with `bin/logout.sh` first*); a password login over a key context replaces the context (the key file is untouched). **A key login asks `GET /organizations` once**: 401 refuses and writes nothing; 200 or 403 is a key that authenticated, and the context records its organisation when exactly one is visible. A password login records the organisation when the person belongs to exactly one. Human-session verbs (`org keys`, `invite`, `key-create`, `key-revoke`, `set-role`, `remove`, `create`, `totp-*`) refuse a key context locally, exit 3, rather than send the key to a route that answers `human_session_required`. | A live credential is ended by the verb that ends it, never by being overwritten. | 0253 |
| **D2121** | D2066: *"the access token is never written"*; Run 7: *"`401` on a password session → one refresh then one retry"*. | With no access token on disk, every command starts without one: the refresh exchange is not the 401 path but the first request of every command, and the exchange ROTATES -- the presented token is consumed. And `urllib` follows a redirect carrying the `Authorization` header to whatever host the answer names. | **Each command exchanges once, writes the successor before anything else, and holds the access token in memory**; a 401 on the request is answered by one more exchange and one retry. A refused exchange removes `session.json` and is exit 3 *log in again*: a refresh token used elsewhere (another terminal, a copied file) ends the session -- two commands run at once from one state directory can do that, and the second is told so. **Redirects are never followed** (`_NoRedirect`): a 3xx is exit 6. Battery M6 (the successor not kept) is killed by the next command's exchange. | One exchange per command is the cost of never writing a bearer; the alternative is a 900-s token on disk. | 0253 |
| **D2122** | Run 7 usage: *"`project list [--organization ID]`"*, *"`project use --project-key KEY`"*, `org use`. | The plan does not say whether `project list` without `--organization` is every organisation's or the context's, nor how `use` interacts with the other half of the context. | **`project list` reads the context's organisation** (`--organization` overrides; every organisation's when the context names none, which is what a key context whose key sees no organisation gets); **`project use` sets the project AND its organisation** from the record; **`org use` clears the project.** `org create` makes the new organisation the context's only when none is chosen. | The context is what a person last chose; a list that ignored it would answer a question they did not ask. | 0251 |
| **D2123** | Run 8 item 1: *"the provider facts copied from `/home/op/agentic-postgres/project.alpha.yaml` (`storage.account_id`, the backup and mirror endpoints, regions and jurisdictions …)"*. | The control manifest's storage is DISABLED (D2049), and `config._validate_storage` refuses a disabled block that names `storage.account_id` (*"storage is disabled, so … must be absent or null"*). And Run 8's rehearsal planted an all-digit account id: written unquoted it loads as an INTEGER and the schema refuses it (`backup/account_id: … is not of type 'string'`). | **`storage.account_id` is not copied**: storage stays `enabled: false`, `account_id: null`. Copied, **every value quoted**: `backup.account_id`, `backup.jurisdiction` only when alpha names one (it does not), the mirror's `endpoint` and `region`. `s37-controlyaml.py` asserts the parsed result is the example with exactly those fields changed and runs the product's loader on it. | The example is the shape a disabled block must have (D2076); copying a field the loader refuses would fail at Run 10 step 2 instead of here. | 0251 |
| **D2124** | Run 8 item 1 and Sheet P1 step 3: *"the mirror bucket is the DERIVED name `apg-control-prod-backup-mirror` unless the operator names another"*. | Read on the host 2026-10-06: alpha's and beta's manifests both OVERRIDE the mirror bucket with the bare key (`bucket: alpha-dev`, `bucket: beta-dev`) and state their backup bucket explicitly (`apg-alpha-dev-backup`). The derived mirror name has never been used at B2, whose bucket names are global across every account. | **The derived name stays the default; `s37-controlyaml.py --mirror-bucket NAME` writes the one P1 made.** When the operator hands P1 back they say which name exists; Run 10 step 2 passes it, and the render prints the mirror bucket it will use (rehearsed both ways: derived, and `--mirror-bucket control-prod`). | The operator's existing buckets set the convention the plan did not read; a mirror pointed at a bucket that does not exist fails at the first nightly copy, not at the deploy. | 0188 |
| **D2125** | Run 8 item 8: `accept`, then `bin/login.sh password`, then `totp-enroll`, `totp-confirm`, then `password` again with the code. | `accept` with `--username` already logs in (D2119), and a login refuses while a session is held (D2120): the second command exits 2. And a TOTP step is accepted ONCE (`app.control_totp_accept_step`): the code `totp-confirm` used is refused by the login right after it (`401 second_factor_invalid`, rehearsed). | **`s37-probe-enrol.py` runs `accept` → `totp-enroll --output` → `totp-confirm --totp-code-stdin` → waits for the NEXT 30-s step → `password --totp-code-stdin` → `org create` → `org list --json` → `logout`.** It writes `probe.json` (0600) with exactly seven members -- `endpoint`, `username`, `password_file`, `totp_seed` (base32), `organization_id`, `organization_name`, `enrolled_at` -- which Run 9's external module reads. A refused `accept` removes the unused password file; an existing state root is refused before anything is sent. | The instrument runs the product's commands, so it follows the product's rules; a step order the CLI refuses would fail on the trip. | 0252, 0253 |
| **D2126** | Sheets W2, W3 and PR1 (the appendix). | The same two rules meet the walk three times: W2 and W3 run `login.sh password` straight after `accept` (exit 2: a session is held); W3 runs `login.sh key` over the member's session from `accept` (exit 2); PR1 runs `login.sh password` while W1's session is still held -- it lives 30 days, refreshed per command (exit 2). Each was rehearsed offline in the plan's form (refused) and the corrected form (served). | **The sheets are corrected in place**: no `password` after `accept`; `bin/logout.sh` before `login.sh key`; PR1 reads `bin/context.sh show` first and logs in only when it says `credential none`; every sheet waits for a NEW code after `totp-confirm`. `~/s37/run8/s37-walk-notes.md` is the agent's copy, with what each line prints. | A sheet that exits 2 at a person's terminal on day 2 costs the walk its trust; the rule that refuses it is the right one (D2120). | 0253 |
| **D2127** | Run 11 step 4 / Sheet W3: the agent reads `POST /api/v1/projects` with the member's key → *"`409 not_available` naming `projects_self_service`"*. | Every write route refuses a key before the body is read: the answer is **`403 human_session_required`** (`control_routes.py:69`'s gate; rehearsed). The `409` is reachable only with a person's session, and the only person's credential the agent holds is the probe owner's. | **Two reads, by `s37-projects-read.py`, after PR1**: the member's key → `403 human_session_required` (a key creates nothing); the probe owner's session (a code computed from `probe.json`'s seed) → `409 not_available`, `ledger_row projects_self_service`, then the session ended. Statuses and words printed; never the key, password or code. | Both answers are true and both are worth reading; the plan named the second with the credential of the first. | 0253, 0254 |
| **D2128** | Run 8 item 2 / D2064 / Sheet P1 step 1: the grey-cloud A record. | Read from the host 2026-10-06T12:14Z with `s37-dns.sh`: **`control.agenticpostgresql.com` already resolves from 1.1.1.1 to `172.67.132.69` and `104.21.4.166` (Cloudflare), and port 80 answers `404` with `Server: cloudflare`** -- a proxied record, or a proxied wildcard covering the name, exists before P1. The control reading, `alpha-db.agenticpostgresql.com`, is `62.238.99.122` and `301` from the edge. `dig` is absent in WSL (present on the host). | **`s37-dns.sh` exits 5 today, correctly, and its exit 0 is the gate before Sheet C1.** P1 step 1 makes the record an explicit `A` → `62.238.99.122`, **DNS only** (an explicit record overrides a wildcard); the operator says whether a wildcard exists. The script runs on the host; without `dig` it is exit 6, never a guess. | An HTTP-01 challenge sent to Cloudflare never reaches this host, and C1 spends one of five failures an hour. | — |
| **D2129** | §2: *"Node ids below are proposed; Run 9 writes what the runs actually wrote, read out of the tree with `pytest --collect-only -q`"*. | The tree holds proofs §2 does not name: Run 2's six `test_project_manifest_control.py` and six `test_control_routes_rendered.py` proofs and its six outputs-v20 migration proofs, the lint's parametrised `test_the_lint_accepts_auth_service_only_in_a_function_grant`, Run 3's `test_the_control_example_renders_as_the_control_plane`, three more `test_totp.py` proofs, `test_the_control_mode_reads_exactly_what_auth_reads`, the boundary scan's control `test_the_scan_sees_each_kind_of_offence`, and Run 6's sixth `test_control_command.py` proof. None was registered anywhere. | **Each is registered where its subject is**: the facility's manifest, render, router and outputs move with the set under `CTL-SET-001` (whose text now says so -- every earlier facility registered its `vNN` migration proofs the same way); the three TOTP proofs under `CTL-TOTP-001`; the mode's environment proof, the scan's control and D2058's scan under `CTL-API-001`; `test_every_exec_goes_through_container_exec` under `CTL-REG-001` (Run 6's owed item). **13 requirements, 86 node ids.** | A written proof no requirement names moves no claim (CLAUDE.md §7 question 7); registering it is the claim getting stricter, never weaker. | 0251 |
| **D2130** | §5 Run 9: *"`tests/deployment/test_session37_control.py` … and `tests/external/test_session37_control.py`"*. | Two modules with ONE basename cannot both be collected: the suite has no package `__init__.py`, and pytest's rootdir import refused the second (*"import file mismatch … use a unique basename for your test file modules"*) on the first `--setup-plan`. | **The external module is `tests/external/test_session37_public_control.py`**, the `test_sessionN_public_*` name every external module since Session 2 carries; the registry, the D2058 scan, the threat rows and the derived gate name it so. | The name is a collection key; the plan's pair would have stopped every sweep's collection. | — |
| **D2131** | §5 Run 9: *"`upgrade plan` offline … the class read; **`major` is a stop**"*. | 1.15.0 releases NO migration (the control plane's three are its own set's), so `--also migration_added` -- Session 36's declaration -- would be false. What moved is the outputs schema (19 -> 20, migratable) and a new management API (`contracts/control-openapi.canonical.json`), which `upgrade plan` cannot see in a rendered document and ADR 0162 classes as `document_schema_migratable` and `api_operation_added` (Session 34 declared the same pair, plus its migration). | **Read with those two declarations: `bump minor`, `requires minor`, verdict `ok`, `changes [api_operation_added, document_schema_migratable]`, no reasons, no operator digests**; without them `requires patch`. Four leaves differ (`template_version`, `schema_version`, `control.enabled`, `routes.control`; 5,993 -> 6,090 bytes). **Not major: no stop.** Run 10's Sheet R1 declares the same two on both projects. | A declaration is a statement of what moved; Session 36's would have named a migration this release does not have. | 0162 |
| **D2132** | §2 `KEY-USE-001`: *"a member's key lists the organisation's projects through `bin/project.sh list`"*. | The probe owner's organisation holds NO project: adoption is root's (Sheet A1) into the operator's own organisation, and a registry key belongs to one organisation, so no proof can make the probe's list non-empty without adopting a real project away from the operator. | **The proof asserts the key lists, through `bin/project.sh list`, exactly what the owner's session lists for that organisation -- and none of another organisation's projects** (alpha's key is asserted absent), then reads alpha's record with the key (`404`, a foreign record looking missing) before alpha's own two routes refuse it (`401`). The requirement's text says this. | The property that matters to a customer is that a key sees its organisation and nothing else; an empty organisation measures it as well as a full one, and the `404` is the half an empty list cannot show. | 0253 |
| **D2133** | D2058: *"AST-scans `tests/external/test_session37_control.py` for … a URL not derived from `routes.control`"*; §5 Run 9: `KEY-USE-001`'s refusal half reads *"alpha's `routes.app`/`routes.rest`"*. | The plan's own refusal half sends requests to alpha's routes, which the scan as written would refuse. | **The scan forbids `APG_SSH_DESTINATION`, an `ssh` or `scp` word, any TYPED URL and any environment variable but `APG_CONTROL_OUTPUTS`, `APG_CONTROL_PROBE_FILE`, `APG_PROJECT_A_OUTPUTS` and `PATH`, and holds the module's marker to exactly the three**; every address is read from a deployed document. At run time each proof asserts its recorder's hosts: `routes.control`'s alone, and alpha's two only in the proof that measures the refusal. A planted control proves the scan sees each kind. | The door D2058 protects is the absence of the SSH path and of invented addresses; alpha's routes are read, not typed. | 0246 |
| **D2134** | §2 `CTL-REG-002`: *"its project unit is enabled and every container came back after the reboot"*. | A sweep without `--after-reboot` cannot answer *came back*, and the closest `requires_environment` marker wins (`tests/conftest.py:245`), so a function marker must name every variable. A deployment holds one-shot containers (a `compose run`, or an exited container with no restart policy) that never come back by design. | **The reboot proof carries its own marker naming all five variables, `APG_AFTER_REBOOT` among them**, so a sweep that rebooted nothing reports `control_plane_live` `not_run`, never green; it skips `oneoff` containers and exited ones whose restart policy is `no`, and requires every other container of `apg-control-prod` running with `StartedAt` after the boot. | A declaration is made only when it is true (D2072's rule, read by the proof). | — |
| **D2135** | §5 Run 10's order: Sheets P2 (`bootstrap-providers --apply` for `control-prod`) and P3 BEFORE R2a/R2b (alpha's and beta's 1.15.0 deploys), C1 after. | **R2a refused at step 0, exit 12, nothing rendered** (2026-10-06 19:1xZ): *"committed undetermined: control-prod (no deployed document: the directory exists and outputs.json does not)"*. `--apply` creates `/etc/agentic-postgres/projects/control-prod/` with its bootstrap state; admission reads every project directory (`capacity_probe.py:278-300`) and a claim it cannot read is a decision it may not take -- it fails closed, by design (ADR 0195). The candidate's OWN directory is excluded (`:302`), so the control project's deploy is not blocked. | **C1 moves before R2a/R2b**: the control project's first deploy writes its document, admission then charges its claim, and alpha's and beta's deploys follow. All three still end on one commit (D1425). The refusal is the product being right; the plan's order was the defect -- a third project's providers bootstrapped while its neighbours still owe a deploy blocks every neighbour until the third's first deploy. The probe read the C1 window: nothing down on either neighbour (182 s). | Fleet operations §6 never met it: gamma's bring-up deployed no neighbour between `--apply` and its first deploy. | 0221, 0195 |
| **D2136** | D2048/D2076 and ADR 0251 §6: *"The deploy is not read offline: if Run 10's first deploy refuses for want of the contract, D2048's second branch applies."* | **C1 refused at step 6** (exit 5, after bootstrap and the release's 39): *"migrate: no proposal for this set 14699bf6749efdb9"* -- the proposal gate (ADR 0243) needs a committed proposal for ANY project set with a pending version, whatever `approvals_required` says, and `propose` refused a set with no `contracts/` file. The neighbours were untouched. | **D2048's second branch, as decided**: `bin/migrate.py propose` records an EMPTY surface when the set's final `api` holds no function, view or enum and no contract exists, and still refuses a set that publishes anything without one -- `test_a_set_with_no_api_object_is_proposed_without_a_contract` and the stricter `test_a_set_with_an_api_object_and_no_contract_is_still_refused` (under `CTL-SET-001`); ADR 0251 §6 says it happened. **The control set's proposal is committed** (`projects/control/proposals/14699bf6…json`, written by the product's own `propose` from the committed example: lint passed, 42 applied from empty in 21 s, no destructive finding, surface empty). **The deploy commit moves** before any project is deployed at `0de7404`: ship, checkout, renders, then C1 again (re-runnable: the bootstrap is converged). | The gate guards an ACT on every project set; the set's empty surface is a fact the record now states. | 0251, 0243 |
| **D2137** | D2049: *"The control manifest sets `api.rest.enabled: false` and `storage.enabled: false`"* -- the control plane's people need an identity, not a data plane. | **Measured from the workstation after C1, 2026-10-06**: `https://control.agenticpostgresql.com/api/rest/` answers **200** with PostgREST's OpenAPI document and `/api/rest/notes` answers 401 *inside* PostgREST (`permission denied for view notes`); the deploy records `routes.rest ready`, and `postgrest` and `storage` containers run. **Nothing reads `api.rest.enabled`**: no reader in `src/` or `bin/`, and the deployed document does not carry it (CLAUDE.md §7: a declared field with no reader). Storage IS off at the edge (its route 404, `routes.storage unavailable`). The bootstrap administrator `control-admin` holds the release's full project-admin scopes (`notes:write`, `tasks:write`, ...), so its token reaches the control database's release `api` -- empty tables, nothing of alpha's or beta's. | **Recorded, not fixed on the trip** (the operator chose to continue): what is exposed reads an empty schema behind PostgREST's grants and no other project. **Owed by Run 12**: `api.rest.enabled: false` withholds the REST router (and says so in the document), with a test that guards the flag's reader -- a field with no reader is the class, so the test asserts a render with the flag off publishes no REST router label. Until then the control plane serves a data surface D2049 meant to remove. | A premise wrong in the reassuring direction survives longest (CLAUDE.md §7, D930); the route answering was the only evidence, and it was read. | 0251 |
| **D2138** | Sheet V1: *"`-k \"session37 or session4_transports\"`"*. | Before Sheet A1 (day 2) the control registry holds no row, so `test_the_registry_agrees_with_every_deployed_document` is red BY CONSTRUCTION on day 1, and D2037 makes a red proof under `-k` exit 6. Also: `R2a` was run before the agent started its probe, so alpha's 1.15.0 outage window was NOT measured (beta's was). | **V1's filter names the one exclusion**: `-k \"(session37 and not registry_agrees) or session4_transports\"` (`/home/op/s37-v1.sh`); the day-2 sweep runs the registry proof after A1. Alpha's window is stated unmeasured; beta's stands for the release (the same three services recreated). | A proof that cannot be green until a later sheet is not run before it, and the reason is written where the filter is. | — |
| **D2139** | Run 11 step 6 / Sheet B1: *"the reboot; the agent runs `s37-units.sh` (four units `active`)"* -- three projects come back from a reboot by themselves, as two did in Session 36 (124 s). | **Measured 2026-10-07, the first reboot with THREE projects** (booted 05:32:10Z): alpha, control-prod and the edge `active` by boot+109 s; **beta's unit `failed` at boot+60 s, exit 8**, its journal: `could not read mirror_s3_secret_access_key: GET /api/v3/secrets/raw/APG_MIRROR_S3_SECRET_ACCESS_KEY failed with HTTP 429`. Each unit materializes TWICE before Compose (its `materialize` step, then `project-runtime.sh up`), so a boot of three is ~180 reads in ~20 s against Infisical Cloud's published free-plan 120 secret operations a minute; `infisical_client` retried timeouts and 502/503/504 (D976) and raised a 429 at once. One ordinary provider answer (measured) carries no rate-limit header. The operator started beta by hand at 05:47:38Z (`systemctl start`). | **Stop condition met; the operator chose the repair (option 1) over sweeping with a hand-started beta**: ADR 0255 -- a 429 on an idempotent call waits `Retry-After` (1-60 s, default 20 s) and repeats, at most 6 attempts and 180 s per client, apart from D976's attempts; a limit that does not lift is still an error with status 429. Battery 8/8. Then Run 11 continues on the NEW deploy commit: ship, redeploy all three, B1 again, the units read, the sweep, the tag on that commit (D1425) -- not f58b471. | A host that cannot come back from its own reboot is the availability claim the sweep's `--after-reboot` declares; a boot that converges because an operator typed `start` is not that claim. | 0255 |
| **D2140** | Run 11 step 6 and the sweep's `--after-reboot`: the Session 4 reboot proof (`test_the_reboot_restored_the_projects_from_their_documents`) *"goes red if a unit did not come back"*. | **It cannot see the difference** between a unit the boot started and one an operator started afterwards: it reads `is-active`, a postmaster younger than the boot and an identity row older than it -- a hand-started beta passes all three. **Measured 2026-10-07**: systemd can tell them apart -- `multi-user.target` is ordered After= the units it Wants, so a boot-started unit's `InactiveExitTimestampMonotonic` precedes the target's `ActiveEnterTimestampMonotonic` (alpha 41.6 s, control-prod 41.6 s, edge 16.8 s, target 100.9 s) and beta's hand start did not (884.5 s). But **inside the sweep the proof could not use it**: the sweep's own proofs restart alpha's unit (Sessions 3 and 4) and stop/start beta's (Session 2) before the reboot proof runs, so a stricter proof would go red on every sweep. | **The proof is left as it is** (a stricter one would be false, not strict). The evidence that every unit came back BY ITSELF is read **after B1 and before S1**, with that systemd ordering, and written in Run 11's Done. The class -- a sweep that destroys the state a later proof in it reads -- is an open item for Session 38's plan. | A proof that runs after the evidence it reads was overwritten measures nothing about it (CLAUDE.md §7 question 2). | 0255 |
| **D2141** | Run 11 step 3, Sheet A1 before Sheet B1/S1: *"`sudo bin/control.sh adopt` ... then `registry` → `agrees` × 3"*. | **The first sweep on 00a73f4 (2026-10-07 06:45–07:22Z) failed `test_the_registry_agrees_with_every_deployed_document`**: `registry` exited 5, `differs: source_commit` on all three. A1 adopted the rows at 05:2xZ from documents naming f58b471; D2139's redeploy moved all three documents to 00a73f4 and nothing re-adopted. **The proof was right and the product was right** (`adopt` reads the deployed document; a row is a snapshot until adopted again) -- the executor's sequencing was wrong when the run's order moved. | **A1 is re-run after the LAST deploy before the sweep** (`adopting a key again refreshes its row`), and the sheet says so: the registry agrees with what is deployed only from the last adoption after the last deploy. Whether a deploy should refresh its own row is Session 38's (`project.*` operations own the registry there). | A reordered run re-checks every step whose input the moved step changes (CLAUDE.md §7 question 5, applied to sheets). | 0251 |
| **D2142** | Run 9's document v20 (`control.enabled` in every deployed document, ADR 0251). | **The first sweep on a 1.15.0 document failed `test_every_leaf_is_classified`**: `control.enabled` in no isolation category -- `isolation_matrix` and `agent_tenant_surface` red. **The third time a facility flag reached a sweep unclassified** (D1029 `backup.mirror.*`, D1853 `connectors.enabled`); V1 (D2138) filtered the proof out, so it first ran here. | `control.enabled` joins `NOT_AUTHORITY_PREFIXES` with `connectors.enabled`'s reasoning (a facility, not an identity). Verified offline against the three REAL deployed documents (the proof's own function: original fails on `control.enabled`, repaired passes, and passes for alpha × control-prod too). The class -- a document field added with no offline check that the matrix classifies it -- is an open item for Session 38's plan (an offline proof over a rendered v20 document would have caught all three). | A guard that only runs live finds its new case one trip late, every time. | 0251 |
| **D2143** | `test_removing_one_project_leaves_the_other_whole` (DEP-REMOVE-001): *"the surviving project ... routes"* all `ready`. | **The same sweep failed it: alpha's `routes.control` is `unavailable`** -- by design since 1.15.0, every document carries `routes.control` and a project with the facility off records it so. control-prod's `routes.storage` is `unavailable` the same way (`storage.enabled: false`), so the proof would fail for control-prod as the survivor too. | The proof excludes a route whose facility the SAME document declares `enabled: false` (`control`, `storage`) and holds every other route -- and a declared-on or undeclared one -- to `ready`. Verified offline on the real documents with two controls the repair must not reach (control-prod's SERVED control route set unavailable; alpha's storage route unavailable with storage enabled): both still fail. | A proof that reads 'every X' must be re-read when X gains a member that is absent by design. | — |
| **D2144** | D2137's repair, *"owed by Run 12: `api.rest.enabled: false` withholds the REST router"*. | **Read in Run 12 before writing it: the repair is not a label.** `runtime_override.build_override` emits `postgrest`'s router unconditionally, and so does storage's (control-prod's storage route answers 404 because its storage service holds no bucket -- D2137's *"storage IS off at the edge"* misattributed it). Withholding the REST router reaches `bin/deploy-project.py`'s served-document read (`observe_served_document` fetches the OpenAPI document THROUGH `routes.rest` to record `api.status` and its digests), so control-prod's next deploy would wait out that read's deadline and record `api.status: unavailable` -- which the doctor, the deployed-document schema and the control proofs read. Only a deploy measures that, and 1.15.0 was already tagged with all three projects on `c3eec1d`. | **The operator chose to defer it to Session 38** (2026-10-07, over coding it now or deploying past the tag): Run 12 writes no code for it; Session 38's plan prices it as what it is -- a manifest flag the render, the deploy's API read, `api.status`, the doctor and a contract test must all agree on -- and measures it with 38's own deploy. **Until then control-prod serves the release's empty `api` schema through PostgREST** (its own database, nothing of alpha's or beta's, behind PostgREST's grants and RLS). | A row that prices a repair before reading its readers prices a label; the readers were the cost (D979). | 0251 |

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

**Done.** 2026-10-04 (documentation only; pushed, no CI read). Scripts and
transcripts in WSL `~/s37/run1/` (`rig37/` holds the five rigs, each with its
`.txt`) and the scratchpad's `s37-run1/`.

- **37a** (`rig37a.py`): HOTP/TOTP over `hmac`/`hashlib`/`struct`. All ten
  RFC 4226 Appendix D values (counters 0–9) and all six RFC 6238 Appendix B
  SHA-1 values at 8 digits matched; with a random 20-byte seed and a ±1-step
  window, now / now−30 / now+30 accepted at their own steps; **controls**: now
  ±60 refused, a wrong code refused, the same code again refused once its step
  was recorded, the next step's code then accepted; an unpadded base32 seed (32
  characters) round-trips. `oathtool` is not installed in WSL — the RFC
  vectors are the independent implementation. exit 0.
- **37b** (`rig37b.sh`, `b-*.sql`; dev cluster `fixture-alpine-dev`, 39
  migrations): the recursion control raised `42P17 infinite recursion detected
  in policy for relation "control_memberships"` (call time, PL/pgSQL; and at
  `CREATE FUNCTION` time for a SQL body — the first pass). **`auth_service` has
  no `USAGE` on `app`** (first pass: every call `permission denied for schema
  app`) → **stopped and asked; the operator chose the second lint form**
  (D2073). With the rig-only grant: design G returned 3 members to a member, 0
  to a non-member, 0 to a non-member with the setting preset, the caller's own
  organisation only; direct table read `permission denied for table`;
  `authenticated` refused at the schema. **The setting survives the function's
  return** (D2074). Single use: the second of two concurrent `UPDATE …
  RETURNING` waited **2.3 s** and updated **0** rows. The grant was revoked
  after (`usage now: f`). **Design G chosen.**
- **37c** (`rig37c.py`, i3-1215U): Argon2id at `FROZEN` median **229.8 ms**,
  p95 245.4 ms, peak RSS 20.9 → 85.1 MiB; **control** SHA-256 +
  `compare_digest` median **0.8 µs**. D2052 stands.
- **37d** (`rig37d.sh`, Traefik `sha256:9c3b91d5…dcb2ac`): the negation hides
  `/api/app/v1[/…]` (Traefik `404 page not found`) and keeps
  `/api/app/auth/me` → `/auth/me` and `/api/v1/organizations` →
  `/v1/organizations` on the control backend; **control** without it,
  `/api/app/v1/organizations` reached the app; `!PathPrefix` alone also hid
  `/api/app/v1x` → the precise form (D2075).
- **37e** (`rig37e.sh`, throwaway worktree, removed — `git worktree list`
  shows the checkout alone): render exit 0 with no `contracts/`, after the
  schema refused a disabled block's non-empty origins and non-null account id
  (D2076); the R2 storage pair owed with storage off (D2077); `meta:read`
  accepted for `api_documentation` (D2078); probe routes `/auth/me` + health,
  no JWKS route (D2079); `auth_revoke_user_sessions` granted to nobody, list +
  revoke granted (D2080); `auth-admin.sh` has `bootstrap` and `list` only
  (D2081).
- **Sheet E0** read (D2082–D2084): admitted, safe available 992 MiB,
  available 2,219 MiB; units enabled since 2026-08-07 by an unrecorded hand;
  **a proxied wildcard answers `control.`** (D2083); **the Session 17
  bootstrap credential is still on disk** (D2084).
- **Documents**: `docs/threat-model.md` items 1–4, 10 and 14 name their owed
  tests by proposed node id, item 16 (*TOTP seed disclosure*) added, no `|` in
  any line; **ADRs 0251–0254** written and indexed; 0185's status *superseded
  in part by 0251*, 0247's *amended by 0254*.
  `test_acceptance_registry.py` + `test_documentation_index.py`: **71 passed**.
- **Rows D2073–D2084. NEXT FREE: D2085, ADR 0255.**

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

**Done.** 2026-10-04 (code). **CI: `45a2a14` RED** (run 37224201524, one unclassified document block, D2091) → repair **`cb58e31` CI GREEN** (run 37225177397, all four jobs). Scripts in WSL
`~/s37/run2/` (`r2_*.py` the edits, `r2_battery.py`, `r2-targeted.txt`).

- **Built**: project manifest schema 9 (`control: {enabled}`, the v9 gate,
  `config.PROJECT_CONTROL_FROM`, `config.control_enabled`, refused without
  `migrations.set`); outputs 20 (`routes.control` on both branches,
  `control: {enabled}`, `migrate_v19_to_v20`, `deployed_output.SCHEMA_VERSION
  = 20`, a coherence rule); `naming.CONTROL_PATH_SUFFIX`,
  `control_router_name`, `control_stripprefix_middleware_name`, four identity
  members, the router enumeration; compose variables `AUTH_APP_MODE`,
  `API_CONTROL_PATH`, `CONTROL_ROUTE_PATH`, `CONTROL_ROUTER_NAME`,
  `CONTROL_STRIPPREFIX_MIDDLEWARE_NAME`; `compose.yaml` `APP_MODE:
  ${AUTH_APP_MODE:?required}`; `_control_labels` and the app rule's negation
  exactly as rig 37d measured (D2075); the lint's two forms (D2086); the
  deploy's `observe_control` and `_override_control`.
- **Not built here, by the plan**: `project.control.example.yaml` needs
  `projects/control/`, which is Run 3's — so is the first full render of a
  control project (D2089). `settings.APP_MODES` gains `control` in Run 4.
- **Tests**: `test_project_manifest_control.py` (6, new, `pytestmark`),
  `test_control_routes_rendered.py` (6, new), two lint tests in
  `test_project_migration_sets.py` (one parametrised over 11 refused shapes),
  six `test_output_migrations.py` tests for the v20 step.
- **Battery** (`r2_battery.py`): M1 grant forms widened to any statement, M2
  negation dropped, M3 `AUTH_APP_MODE=control` everywhere, M4 the v9 gate
  disabled — **4/4 KILLED** (target FAILED, paired control PASSED, file
  restored and `cmp`-equal), clean re-run all PASSED.
- **Targeted once** (28 modules, Docker up): **1,160 passed, 1 failed**
  (`test_acceptance_matrix_is_generated_from_the_registry`, the moved node id)
  → `render-acceptance-matrix.py --write` → that module re-run: **24 passed**.
- **Rows D2085–D2091.** NEXT FREE: D2092, ADR 0255.

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

**Done.** 2026-10-04 (code). **CI: `89655ed` RED** (run 37227231821, a pre-existing username collision in `test_auth_endpoints.py`, D2100) → repair `df5ef0e` **CI GREEN** (run 37228178229: the Session 1 gate, the Session 2 offline contract and the P0 inventory all success; recorded in Run 4's commit). Scripts in WSL `~/s37/run3/`.

- **Built**: `projects/control/migrations/` -- `manifest.json` (placeholders
  `object_owner`, `auth_service`), three templates (`20261004120001`
  identity, `…002` keys, `…003` registry), the lock frozen with
  `bin/migrate.sh --project project.control.example.yaml freeze-lock`
  (3 migrations, `follows_release_version 20261003120039` computed;
  `verify-lock` agrees); `project.control.example.yaml` (key
  `fixture-control-dev`, D2092); `tests/contract/control_cluster.py` (the
  shared cluster, removed with `-fv`, D2098); `tests/contract/test_control_set.py`.
- **The set**: 8 tables, all FORCE RLS; design G policies with an
  organisation scope set only after the caller's own membership was read, and
  `app.control_enter` resetting every scope first (D2074); 25 definer
  functions granted to the identity service, 3 helpers and 3 invoker-rights
  operator functions granted to nobody (D2093); `GRANT USAGE ON SCHEMA app`
  (D2073); no `api` object, no PostgREST contract (D2097); keys reference the
  organisation and account (D2094); no function inserts an operation (D2054).
- **First execution**: all 8 `test_control_set.py` tests PASSED on the first
  run against the locked image -- catalog (FORCE on all 8 tables, PUBLIC and
  every request role executing nothing, the identity service executing exactly
  the 25), scoping as the identity service (own organisations only; a member's
  call in one transaction leaves nothing to a non-member -- D2074 proved; a
  non-member gets no row and AP404, a foreign and a missing id alike; the
  service reads no table directly), and **the first full render of a control
  project** (D2089: `routes.control`, `AUTH_APP_MODE=control`, 3 rendered
  project migrations; the directory removed after).
- **Lint**: refused the set once -- `SET role =` read as a role switch
  (D2095, column quoted). Passes with the facility, refused without it.
- **Battery** (`r3_battery.py`): M1 FORCE removed from `control_totp`, M2
  `control_list_members` to PUBLIC (D2099), M3 `control_adopt_project` to the
  identity service, M4 the membership check removed from
  `control_list_members` -- **4/4 KILLED** (target FAILED, control PASSED,
  restored `cmp`-equal), no cluster leaked. **M5 owed to Run 4** (the
  concurrent-acceptance proof), not counted.
- **Targeted once** (13 modules): 431 passed, 1 failed
  (`test_the_project_reader_finds_every_object_the_project_contract_names`,
  D2097) → widened with its stricter half → that module re-run: **69 passed**.
  `test_every_committed_project_set_still_passes` made stricter (D2096).
- **Rows D2092–D2100.** NEXT FREE: D2101, ADR 0255.

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

**Done.** 2026-10-06 (code). **CI: `1348f13` GREEN** (run 37426842820: the Session 1 gate, the Session 2 offline contract and the P0 inventory all success). Scripts in WSL `~/s37/run4/`.

- **Built**: `settings.APP_MODES` gains `control` (auth's branch, D2107); `create_app("control")` -- title *Agentic Postgres management API*, the health routes, `/auth/me` (the release's handler by name, out of the document) and `control_routes.router` (14 `/v1` paths); the lifespan's control branch builds `ControlService` over the same `AuthService` and pool, with no workflow or connector repository and no worker. `public_paths("control")` and `control_paths()`. New modules `totp.py`, `control_repository.py`, `control_service.py`, `control_routes.py`, `control_roles.py`; `AuthService.login(..., second_factor=None)` (one caller, `/auth/login`, unchanged); `errors.CONTROL_STATUS` + `ControlRefused` (D2105); the control request models in `models.py`. `control_cluster.py` gains `control_app` / `ControlDriver`.
- **First execution**: all 15 Docker-backed proofs (`test_control_sessions` 4, `test_control_invitations` 7, `test_control_roles` 4) PASSED on the first run against the locked image -- which is why the battery below was run before anything else was believed. The first targeted run FAILED one guard: `app/totp.py` named `urllib` (D2102).
- **Battery** (`r4_battery.py`, 9 mutations, each beside a control in one invocation, restored `cmp`-equal): M1 window ±2, M2 replay `<=`→`<`, M3 hook skipped, M4 confirm ends no session, M5 an `invitation_expired` answer (SQL + `errors.py`), M6 the account insert committing on its own (D2104), M7b an admin granting owner in Python AND both SQL checks, and **Run 3's owed M5** (acceptance without `accepted_at IS NULL` → `test_one_of_two_concurrent_acceptances_succeeds`) -- **8 KILLED**; M7a (Python only) **SURVIVED as predicted**, the set refusing it (D2106). The pre-flight aborted the first attempt on an anchor `ruff format` had re-wrapped (D269 working). No cluster leaked.
- **Targeted once** (17 modules: the plan's twelve plus `test_control_set`, `test_verifier_key_sets`, `test_mcp_runtime`, `test_workflow_admin_routes`, `test_connector_admin_routes`, each a reader of a moved name): **369 passed**, ruff clean.
- **Not done here, by plan**: the registry entries and claims (Run 9); the control snapshot (Run 5, D2057).
- **Rows D2101–D2108.** NEXT FREE: D2109, ADR 0255.

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

**Done.** 2026-10-06 (code). **CI: `47c65a0` RED** (run 37446073568: a module imported only by tests, D2114) → **repair `65773f2` CI GREEN** (run 37447843761, all three jobs; recorded in Run 6's commit). Scripts in WSL `~/s37/run5/`.

- **Built**: key authentication in `control_service.py` (`apg_<16 hex>_<43>`, looked up by
  id, SHA-256 + `compare_digest`, one `authentication_failed` for unknown, wrong, revoked and
  departed; effective scopes = the key's ∩ `control_roles.ROLE_SCOPES[current role]`, inside
  the key's one organisation; `control_key_used`); `ControlPrincipal` now a person OR a key.
  Routes: `GET|POST /v1/organizations/{org}/keys`, `DELETE …/keys/{key_id}`, `GET /v1/projects`
  (`?organization=`), `GET /v1/projects/{key}`, **`POST /v1/projects` → `409
  {"error":"not_available","ledger_row":"projects_self_service"}`**, `GET /v1/operations`
  (`?organization=` required), `GET /v1/operations/{id}` -- 20 `/v1` paths. A key reaches
  only `KEY_SCOPES`' seven read routes; all else is `human_session_required` (D2111). The
  operation types in `services/auth-api/app/operations.py` (`ACCEPTED_TYPES` empty), loaded by
  `src/agentic_postgres/operations.py` (D2110). The Ledger guard
  `test_every_operation_type_names_a_ledger_row_and_none_is_accepted_while_planned` and
  `test_no_console_exists_yet` replace `test_the_sets_the_guard_will_read_are_empty_today`
  (ADR 0254). `bin/app-contract.py` `generate_control()` + `--snapshot app|control`, `--check`
  compares both (D2113); `contracts/control-openapi.canonical.json` written by
  `bin/app-contract.sh --update --snapshot control` (20 paths, 9 schemas, ASCII).
  `tests/contract/test_control_boundary.py` (AST scan + its control).
- **First execution**: the six key proofs ERRORED at setup on the first run -- the fixture's
  project keys (`a-prod`) failed the registry's key CHECK (a slug of three or more
  characters); renamed `alpha-prod`/`beta-prod`, 6 passed. Operation types 2, roles 4 (now over
  every `/v1` route and every kind of id), boundary 2 passed first time. The first fast run
  FAILED one guard, `test_the_shared_modules_are_the_ones_the_repository_actually_loads`:
  `operations` added to `SHARED_MODULES` (D2110).
- **`LEDGER-001` moved in this run** (`test_every_registered_node_id_is_collectible` refuses a
  node that no longer exists): node → `test_no_console_exists_yet`, description amended, the
  matrix and the product contract regenerated (D2112).
- **Battery** (`r5_battery.py`, M1 not run -- uninformative, as the plan says): M1′ the revoked
  check dropped, M2 the intersection dropped, M3 a key allowed on `POST …/keys`, M4
  `projects_self_service` → `beta` in the ledger, M5 a `/v1` path added without re-capturing,
  M6 a foreign organisation answered 403 -- **6/6 KILLED**, each beside a control, restored
  `cmp`-equal, no cluster leaked.
- **Targeted once** (18 modules: the plan's twelve plus `test_control_sessions`,
  `test_control_invitations`, `test_totp` (the principal refactor), `test_cli_contract`
  (`bin/app-contract.sh`'s usage), `test_documentation_index` and
  `test_session12_documented_path` (the regenerated product contract)): **938 passed**, 0 skipped; ruff,
  shellcheck and `bin/app-contract.sh --check` clean.
- **Rows D2109–D2114.** NEXT FREE: D2115, ADR 0255.

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

**Done.** 2026-10-06 (code). **CI: `52e62e7` GREEN** (run 37452424033, all three jobs; recorded in Run 7's commit). Scripts in WSL `~/s37/run6/`.

- **`bin/control.sh`** (preamble, `--help` anywhere a read, verb-first usage, docker required) exec'ing **`bin/control.py`**: `adopt --project KEY --organization ORG_ID --confirm CONTROL_KEY`, `registry [--json]`, `totp-reset --username NAME --confirm CONTROL_KEY`; root for every verb, input checked before root (a key that is not a key, an organisation that is not a uuid, an empty username: exit 2). The control project is FOUND by `control.enabled` (D2116); the container and database come from its document; every call is `psql -U postgres … -v NAME=VALUE -f -` through `container_exec.run`, the SQL text fixed (`ADOPT_SQL`, `REGISTRY_SQL`, `TOTP_RESET_SQL`) and every value a variable. `adopt` copies `project.slug|environment|domain`, `template_version` and `source_commit` from KEY's document and prints them; a database refusal (an organisation that does not exist is the foreign key's) is printed verbatim, exit 5; no answer is *not known -- read `control.sh registry`*, exit 6. `registry` prints `agrees`, `differs: <fields>`, `not in the registry`, `no deployed document`, `could not determine: <reason>` per key in either the registry or the state root; 6 over 5 over 0 (D2117). `totp-reset` per D2118.
- **Registered**: `bin/control.sh` in `SHELL_COMMANDS` and `COMMANDS_WITH_VERBS`, `bin/control.py` in `PYTHON_COMMANDS`, both `git add`ed first. `apg control` is a verb by derivation (nothing edited).
- **`tests/contract/test_control_command.py`** (new, `pytestmark`): §2's five `CTL-REG-001` names and `test_every_exec_goes_through_container_exec` (D2115; Run 9 registers six). The recorder pattern of `test_record_command.py`, not a fake binary (D2115).
- **Battery 6/6 killed**, each beside a control that passed, every file restored and `cmp`-checked: M1 an unreadable document reported `agrees` → `…undetermined_not_agreeing` FAILED; M2 `--confirm` compared case-insensitively → `test_totp_reset_requires_the_confirmation` FAILED, and M2b the same mutation → `test_adopt_requires_root_and_a_confirmation` FAILED; M3 found by NAME → `…found_by_its_facility` FAILED; M4 `adopt` searching as a report (`decision=False`) → the same FAILED; M5 no field ever differs → `test_registry_reports_three_outcomes` FAILED.
- **Targeted once**: the plan's nine modules plus `test_acceptance_registry`, `test_printed_commands` (the sweep-selector guard, D1242) and `test_documentation_index`: **1206 passed, 2 skipped** (`test_root_script_policy`'s two shell commands that run no Python, by design).
- **Rows D2115–D2118.** NEXT FREE: D2119, ADR 0255.

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

**Done.** 2026-10-06 (code; CI: see Run 8's record). Scripts in WSL `~/s37/run7/`.

- **`src/agentic_postgres/control_client.py`**: `state_directory` (`${XDG_CONFIG_HOME:-$HOME/.config}/apg`), `ensure_state_directory` (created 0700; a symlink, another owner's, or anything wider than 0700 refused, exit 3, never repaired), `read_private_file` (`O_NOFOLLOW`, then `fstat` on the OPEN descriptor: a regular file, the caller's, nothing for group or other), `write_private_file` (`O_WRONLY|O_CREAT|O_TRUNC|O_NOFOLLOW` 0600 to a temporary name, `fsync`, `os.replace`), `write_new_private_file` (`O_EXCL`), the context and session documents, `check_endpoint` (https; http only for 127.0.0.1/localhost; no credentials, query or fragment), `send` over `urllib.request` with `ssl.create_default_context()` and no redirects, `refusal` (a 4xx with an `error` word → exit 5 relaying `error`, `message`, `ledger_row`; anything else → 6), and `Session` (D2121).
- **`bin/cloud.py`** (stdlib + `agentic_postgres`) with five families, and five shells exec'ing it: `bin/login.sh password|key|accept|totp-enroll|totp-confirm`, `bin/logout.sh [--json]`, `bin/context.sh show`, `bin/org.sh list|create|use|members|invite|set-role|remove|keys|key-create|key-revoke`, `bin/project.sh list|use|show` -- the plan's usage, plus the signed-in `accept` (D2119). `--output` is checked before the server mints anything; `totp-enroll` without it refuses a non-TTY stdout BEFORE the seed is stored. `apg login` and the rest are verbs by derivation; `--project-key` keeps apg's `--project FILE` rule out.
- **Registered**: the five shells in `SHELL_COMMANDS`, `bin/cloud.py` in `PYTHON_COMMANDS`, `context|login|org|project.sh` in `COMMANDS_WITH_VERBS` (`logout.sh` documents no verb); `git add`ed first. `tests/contract/control_cluster.py` gains `served_app`: the real control app under `uvicorn.Server` in a thread on `127.0.0.1:<free port>`, its own lifespan in its own loop.
- **`tests/contract/test_control_cli.py`** (new, `pytestmark`): §2's six `CTL-CLI-001` names, every command a subprocess against the served app with a `HOME` of its own. **Its first run found a defect**: `login key` called `Path.resolve()` on the key file, which follows a symlink before `O_NOFOLLOW` sees it -- the symlinked key was accepted. Fixed to `absolute()`; the plan's M2 was a live defect, not a hypothetical.
- **Battery 6/6 killed**, each beside a control that passed, files restored and `cmp`-checked, no cluster leaked: M1 the state directory created 0755 → `…state_directory_is_private` FAILED; M2 `O_NOFOLLOW` dropped → `…symlinked_or_wide_file…` FAILED; M3 http accepted for any host → `test_plain_http_is_refused_except_loopback` FAILED; M4 `logout` not calling the server → `test_logout_revokes_the_session` FAILED; M5 the terminal check for a seed dropped → `…private_file_or_a_tty` FAILED (a seed stored for a pipe); M6 the refresh successor not kept → `test_project_list_reads_the_endpoint_from_the_context` FAILED.
- **Targeted once**: the plan's eight modules plus `test_acceptance_registry`, `test_printed_commands` and `test_control_command`: **1146 passed, 0 skipped**.
- **Rows D2119–D2122.** NEXT FREE: D2123, ADR 0255.

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

**Done.** 2026-10-06 (instruments; no code, so no CI). **Run 7's `fcdca62` CI GREEN** (run 37456258011, all three jobs). Scripts in WSL `~/s37/run8/` and the scratchpad's `s37/run8/`; the host's eight in `/home/op`, **sha256 equal on both sides** (`shipped-sha256.txt` / `host-sha256.txt`).

- **Written**, each with `--help` and a transcript: `s37-controlyaml.py` (D2123, D2124), `s37-dns.sh` (exit 0 go / 5 no / 6 could not determine), `s37-free.sh` (FITS 0 / STOP 5 / 6), and, by `s37-derive.py` from Session 36's parents (their sha256 read equal to `/home/op`'s first) with every substitution named and counted: `s37-units.sh` (control-prod's unit always awaited, D2060), `s37-probe-start.sh` (refuses `control-prod`), `s37-probe-stop.sh`, `s37-sweep.sh` (HEAD == all THREE documents' `source_commit`, booted after all three, and `/home/op/control-prod-outputs.json` byte-equal to control-prod's document, else exit file 95), `s37-launch.sh`, `s37-external.sh` (three copies, the probe file checked 0600 and naming `routes.control`, else 94). Workstation: `s37-probe-enrol.py` (D2125), `s37-projects-read.py` (D2127, an instrument the plan's W3 step implied), `s37-walk-notes.md` (D2126).
- **The flag diffs** (D2024's reading): `s37-sweep.sh`'s gate line keeps all 20 of S1's flag tokens (`--mode` counted) and adds exactly `--control-outputs`; `s37-external.sh` keeps all 5 and adds exactly `--control-outputs` and `--control-probe-file`. Every derived script: `bash -n` and `shellcheck` clean; every Python one `py_compile` and `ruff` clean.
- **Rehearsed offline** (`rehearse-offline.txt`, **42 checks, 0 failed**): `s37-controlyaml.py` on a planted alpha (account, jurisdiction `eu`, another mirror region) → the planted facts copied, alpha's mirror bucket NOT copied, storage disabled; refused without `--replace`, refused inside the checkout (and the checkout left with 0 changes), refused for an alpha with no mirror; **rendered** with `./deploy.sh --render-only` in a worktree, rc 0, `control: {enabled: true}`, `routes.control` `https://control.agenticpostgresql.com/api/v1`. Then on **alpha's real manifest** (fetched read-only, deleted after): rc 0, rendered rc 0, `apg-control-prod`, backup bucket `apg-control-prod-backup`, mirror `apg-control-prod-backup-mirror` at `s3.eu-central-003.backblazeb2.com`. `s37-probe-enrol.py` against the control app on loopback (Run 7's harness) with an account invitation minted through `/v1` by a bootstrapped administrator → exit 0, `probe.json` 0600 with its seven members, neither password nor seed in any output, no session left; a login with the computed code served, without it `401 second_factor_required`; the same state root again → exit 2, nothing sent; a FRESH invitation with the taken username → exit 5, nothing kept, and the same token then enrolled another username (unspent). **The walk W1, W2, A1 (through `app.control_adopt_project`), W3 and PR1 run whole** with password files and computed codes: the plan's three refused forms refused (exit 2 each), the corrected ones served, `project list` with the member's key → the three projects, `s37-projects-read.py` → 403 then 409.
- **What the rehearsal caught in the instruments themselves** (fixed before shipping): an all-digit account id written unquoted loads as an integer (D2123); a refused output inside the checkout still wrote its TRANSCRIPT there, dirtying the release it refused to dirty (the transcript now defaults to `$HOME`); the plan's step orders for the probe and the walk (D2125, D2126); the key's answer (D2127).
- **Rehearsed on the host, as op, reads only** (`rehearse-host.txt`): `s37-dns.sh` → `example.com` exit 5, `alpha-db` exit 0 (the control), **`control.agenticpostgresql.com` exit 5: Cloudflare's addresses** (D2128); `s37-free.sh` → **FITS, 2,145 MiB available** with two projects (`docker stats` not readable as op, said so); `s37-units.sh` → alpha, beta, edge `active` and `control-prod` **`inactive`, not left out**, gave up at 20 s (exit 1); `s37-probe-start.sh control-prod` → exit 2; `s37-sweep.sh` and `s37-launch.sh` as op → refused (not root), no exit file written.
- **Sheets W1, W2, W3 and PR1 corrected in place** (D2126). **Rows D2123–D2128.** NEXT FREE: D2129, ADR 0255.

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

**Done.** 2026-10-06 (code). CI and the two gates: see Run 10's record. Scripts in WSL `~/s37/run9/`.

- **The bump**: `VERSION` `1.15.0`, `CURRENT_SESSION = 37`, the Session 37 paragraph above the constant with the price last; the example client regenerated (template version only, `1.0.0`, no contract change).
- **The registry**: `CTL` and `KEY` in the ID regex with the family sentence; the block `# Session 37 (ADR 0251-0254)`, **13 requirements, 86 node ids** read from `--collect-only` (D2129). **Claims**: 13 (nine in `OFFLINE_CLAIMS`, three external, one host) and 13 `CLAIM_INTRODUCED_IN` rows at 37 -- counted from the tuples: **requirements 299 -> 312, `CLAIMS` 206 -> 219, `OFFLINE_CLAIMS` 65 -> 74**, as §2 predicted. **Roster**: `APG_CONTROL_OUTPUTS`, `APG_CONTROL_PROBE_FILE`.
- **The live modules**: `tests/deployment/test_session37_control.py` (`CTL-REG-002`'s four: the registry through `bin/control.sh registry --json`, isolation over `ISOLATED_FIELDS` and every role with a minimum compared set, the control mode's 404s beside `/v1/me`'s 401, and the unit and containers after the reboot, D2134) and **`tests/external/test_session37_public_control.py`** (D2130; `CTL-INV-002`, `CTL-TOTP-002`, `KEY-USE-001`'s two, every request through a per-proof recorder whose hosts are asserted, a TOTP step never reused, each proof's `probe-s37-*` memberships removed, D2132). `--setup-plan` with the variables set: every fixture SETUP; without: 8 skipped. **D2058's scan** is `test_control_boundary.py::test_session37_customer_proofs_reach_only_the_public_endpoint` (D2133), with a planted control.
- **`bin/session-37-check.sh`** derived from 36's (`derive.py`): the header and the WHOLE usage block rewritten; **flag tokens 59 -> 61, exactly `--control-outputs` and `--control-probe-file`**, parser arms 38 -> 40; outside the two flags' lines the body is unchanged and between the header and the usage only `SESSION=37` and the two variables. `test_session_thirty_seven_gate_modes.py` derived (the claims table with its external column; the offline-set assertion; the host AND external claims held out of `OFFLINE_CLAIMS`; a new `test_the_gate_exports_the_control_variables`). `SHELL_COMMANDS` gains the gate; `100755` in the index.
- **`docs/threat-model.md`**: `THR-CTL-INVITATION`, `THR-CTL-KEY`, `THR-CTL-ESCALATION`, `THR-CTL-ENUMERATION`, `THR-CTL-PLANE-CONFUSION` in the table, nine cells each; list items 1-3 removed, enumeration and confusion keeping the halves of Sessions 40 and 38-39, the list renumbered (13 items). Items 11 (cross-project leakage) and 13 (TOTP seed disclosure) keep their Session 37 halves as list text: §1 D2056 named five rows.
- **Documents**: `docs/control-plane.md` (new, indexed once); the operator guide's release line and table, §3's credential sentence (D2061), the unit-enable paragraph (D2060) and the control project's bring-up, §10 on `bin/session-37-check.sh` with its two flags; fleet operations §6 steps 1, 3 and 8; the recovery runbook's kit command with `--project /home/op/control.yaml` and D2069's sentence; the upgrade guide's release line and `1.15.0` row; `README.md`'s status; **every `--session 36` / `--through-session 36` literal on the documented path moved** (README 1+1, api-operations 1+3, operator guide 3+4, pool-operations 1, upgrade guide 1+1); the Reality Ledger's `stage5_reality` text for `accounts`, `api_keys` and `cli_remote`, **statuses unchanged** (D2055), the page re-rendered; the acceptance matrix and the product contract's table regenerated.
- **`upgrade plan` offline** (D2131): `requires minor` with `document_schema_migratable` and `api_operation_added` declared; **not major**.
- **Targeted once** (24 modules, the plan's ten plus the readers of every page touched): **1,324 passed, 3 failed, 8 skipped** -- the three were the release paragraph itself (the fixture's URL quoted in deployable source; the pricing sentence broken across a line, so `ADR 0162 prices it` read nothing) -- fixed, and the two modules re-run: **237 passed**. Generators all current after the matrix and the ledger page; both contract snapshots match; `ruff` clean.
- **Battery 9/9 killed** (`battery.py`), each target FAILED beside `test_the_scan_sees_each_kind_of_offence` PASSED, files restored and `cmp`-equal: M1 `control_plane_live` declared offline and M2 `control_cli` undeclared -> `…exactly_this_sessions_declared_claims_are_offline`; M3 `control_set` introduced at 36 -> `…resolves_to_the_session_that_introduced_it`; M4 a node id renamed -> `…every_registered_node_id_is_collectible`; M5 `CTL` out of the regex -> `…ids_use_a_registered_prefix`; M6 `SESSION=36` -> `…resolves_claims_for_its_own_session`; M7 the help naming 36's offline half -> `…documents_the_three_half_merge`; M8 `--control-probe-file`'s entry dropped -> `…every_accepted_flag_has_its_own_usage_entry`; M9 `KEY-USE-001` at 36 -> `…every_session_thirty_claim_belongs_to_session_thirty`.
- **Rows D2129–D2134.** NEXT FREE: D2135, ADR 0255.

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

**Done.** 2026-10-06 (the host's day 1; all three projects at 1.15.0 on **`f58b471`**). **Run 9's `0de7404`: both gates PASSED on the clean tree** (`bin/session-37-check.sh --mode offline` exit 0, 7,179 passed / 0 failed / 3 skipped; `bin/session-01-check.sh` PASSED, 0 identity collisions) and **CI GREEN** (run 37474273225). The repair **`f58b471` CI GREEN** (run 37520011735). Scripts and transcripts: WSL `~/s37/run10/`, host `/home/op/s37-*`.

- **Shipped**: bundle `2538ac0..0de7404`, FETCH_HEAD confirmed, clean, no dependency moved; five renders rc 0 (`/home/op/control.yaml` written by `s37-controlyaml.py`, derived mirror bucket); `s37-dns.sh` GO (62.238.99.122, port 80 from the edge). Then, after the repair, `0de7404..f58b471` the same way.
- **P2**: the first `--apply` failed `POST /api/v1/identities` HTTP 400 after creating the Infisical project -- the free plan's FOUR machine identities (D1045's class): the operator deleted the unused `snippets-control-plane` and the empty project, and the retry created 4 resources; `--plan` then read *no changes*; the credential shredded both times (D2061), the directory empty. **P3**: 29 files, generation `e63086f11bcb8c04`, nothing missing. **The operator pasted a B2 application key into the conversation once; it was replaced before P2 and never used.**
- **R1**: both projects `bump minor`, `requires minor`, `ok`, changes `[api_operation_added, document_schema_migratable]` with D2131's two declarations, four leaves -- exactly Run 9's rehearsal.
- **The order moved** (D2135): R2a was refused at step 0 (exit 12, nothing rendered) because P2 had made `control-prod`'s state directory without a document; C1 went first.
- **C1**: the first attempt stopped at step 6 for want of a proposal (D2136) -- repaired by D2048's second branch (`propose` records an empty surface for a set with no `api` object; the stricter test beside it; the control set's proposal committed), CI green, shipped; **C1b `deployed through session 37`**: the release's 39 and the control set's 3 applied (*"proposal 14699bf6749efdb9 admits them"*), **the production certificate issued on the one attempt**, `control ready`, ports and app `unavailable` (D326). Probes across C1 and C1b: **0 down on alpha and beta** (182 s, 561 samples per target).
- **R2a** (alpha) 76 s, admitted (608 MiB committed by the other two), no migration; **window NOT measured** (D2138). **R2b** (beta) 90 s, admitted, no migration; probe: **beta auth 17.1 s (bound 19.6), mcp 13.8 s (16.3), storage 17.1 s (19.6); rest 0, docs 0; alpha 0 on every class**. Alpha's doctor 12 ok.
- **C2**: `control-admin` (`9c6a0351-…`, `apg_control_prod_project_admin`), the password at `/root/control-prod-administrator` (0600). **C3**: ports 15436/15437 reserved and verified; the second deploy: `pooled`/`direct` available, `app` and `control` ready, `storage` unavailable (31 re-probes of a disabled storage route on each control deploy -- cosmetic, noted); probe 0 down (293 s).
- **C4**: the unit **enabled** (D2060); doctors **alpha 12 ok, beta 12 ok, control 10 ok + 2 warnings** (no full backup yet, mirror never copied -- both C5's); `doctor capacity` **912 MiB committed across 3**, 1,582 MiB available; **`s37-free.sh` FITS, 1,624 MiB available** (D2042).
- **C5**: full backup `20261006-202522F` in 5m32s (32.7 MB, set 4.2 MB), status ok; three timers enabled; the mirror's first run failed both passes on ONE object (`ContentLength=3744 with Body length 0` reading R2, D1546's upstream flake), the re-run **complete: 1,459 objects** (first pass retried, ADR 0220).
- **K1**: `kit-2026-10-06-s37`, 14 artifacts, **3 projects** (D2069), owned by op 0700/0600; copied to WSL `~/dr-kits/` and **`verify` rc 0** on the copy; the three op copies refreshed. All three documents: schema 20, 1.15.0, `source_commit f58b471`.
- **V1** (`s37-v1.sh`, the sweep's declarations minus `--after-reboot`, plus `--control-outputs`, the registry proof excluded until A1, D2138): **`V1_EXIT=0`, 12 passed, 1 skipped** (the reboot proof, `APG_AFTER_REBOOT` absent), 45 s.
- **Found and recorded**: D2135 (the order), D2136 (the proposal), **D2137 (`api.rest.enabled` has no reader: the control project publishes REST -- owed by Run 12)**, D2138 (V1's filter; alpha's window). NEXT FREE: D2139, ADR 0255.

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

**Done.** 2026-10-07 (the host's day 2). **1.15.0 TAGGED on `c3eec1d`** (tag object `b081aab`, pushed, read back) -- NOT f58b471: two repairs moved the deploy commit, and the deploy, the sweep and the tag stayed on one commit (D1425). **Merged `evidence/session-37.json`: 219 claims, 217 passed, `documented_path` failed (D1935), `replacement_host_restore` not_run (D1028), exit 5 -- exactly §7's expectation.** Host 1,096 passed / 1 failed / 1 skipped (the replacement-host proof); external 29 / 0 / 8; offline 74 / 74 (CI run 37591064970's artifact, `checkout_commit` c3eec1d). Scripts and transcripts: WSL `~/s37/run11/` (`NOTES.md` the day's log), host `/home/op/s37-*`.

- **W1** (control-admin): logged in, TOTP enrolled and confirmed, invitation minted. It cost ~45 minutes of the operator's time: the sheet was first run in the SSH window; a setup key typed into Apple Passwords by hand did not match (`second_factor_invalid` ×2; host clock NTP-synced, no lockout); the route that worked is `totp-enroll --output FILE` + `qrencode -t ansiutf8` scanned with the phone's camera; a password pasted at the hidden prompt failed `401 authentication_failed`, and `--password-file` (the root file copied by `install -o op` + scp, the host copy shredded) worked. Owed to the sheets: the QR route, `--password-file`, and *do not paste the QR*.
- **W2**: `andranik` (owner) and the organisation **Virabyan** `10234b92-…`. **The operator pasted the QR (the seed) into the conversation**; `bin/control.sh totp-reset` removed that factor and a new one was enrolled by QR (the reset leaves sessions; the re-enrol proves it ran).
- **A1**: adopt × 3, `registry` agrees × 3. **W3**: `member-s37`, key `5505ad978d259996` (organizations:read, projects:read), `project.sh list` → the three. **PR1** + `s37-probe-enrol.py` exit 0 (`probe-owner-s37`, organisation `probe-s37`, `~/s37/probe.json` 0600); `s37-projects-read.py` exit 0: the member's key → 403 `human_session_required` (D2127), the probe owner's session → 409 `not_available` / `projects_self_service` (D2054).
- **B1, the first reboot with three projects: beta FAILED at boot** (exit 8, Infisical HTTP 429) -- **D2139**, the stop condition; the operator started beta by hand and chose the repair: **ADR 0255** (a 429 waited out within a budget), `00a73f4`, battery 8/8, CI green (run 37578677343); shipped; redeployed × 3; **the second reboot: all four units back BY THEMSELVES** (each left `inactive` before `multi-user.target`, NRestarts 0, all active at boot+136 s) -- the systemd reading D2140 names, because the sweep's own proofs restart alpha's and beta's units before its reboot proof.
- **The first sweep** (00a73f4, 06:45–07:22Z): 1,093 / 4 / 1 -- `documented_path` and three new: the registry `differs: source_commit` (A1 predated the redeploy, **D2141**), `control.enabled` unclassified (**D2142**, the third facility flag), the removal proof counting a by-design `unavailable` route (**D2143**). The two proofs repaired in `c3eec1d`, executed offline against the three REAL deployed documents (the originals reproduce the sweep, the repairs pass, two controls still fail), CI green (run 37591064970); shipped; redeployed × 3; **A1 re-run** (agrees × 3 on c3eec1d); the third reboot: all four back by themselves again (boot+136 s).
- **The second sweep** (c3eec1d, 08:43–09:24Z): 1,096 / 1 / 1, only `documented_path` failed; `port_allocation`, `boot_convergence` and `control_plane_live` passed. External (`s37-external.sh`, detached, ephemeral agent) exit 0; the merge exit 5 as expected.
- **Unmeasured**: whether the client actually waited on a 429 during the second and third boots (its waits print nothing; each boot took ~30 s longer than the morning's). The deploy windows of D1/D2 were not probed (D2034's figures stand). Rows D2139–D2143, ADR 0255. NEXT FREE: D2144, ADR 0256.

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

**Done.** 2026-10-07. **The Reality Ledger**: `accounts`, `organizations`, `api_keys`, `management_api` and `cli_remote` → **`beta`**, each because every claim it names reads `passed` in `evidence/session-37.json` (checked by `~/s37/run12/ledger.py` before writing); `customer_text` says what a person can do now, `today` rewritten, `controls` `[]`; the file's header sentence *"never at a session's close"* corrected to ADR 0254's rule; `bin/render-reality-ledger.py --write`; the guard's evidence half read the local merged document (12 passed). **`capacity.ENVELOPE`**: four Session 37 rows by `~/s37/run12/s37-envelope.py` (Session 36's script the model, helpers unchanged): three projects' memory (2,145 → 1,624 MiB available; 912 of 1,600 committed), the control project's bring-up (C1b 183 s, C3b 172 s, the first full backup 5 min 32 s), the 1.15.0 deploy on beta (auth 17.1, mcp 13.8, storage 17.1 s; alpha's unprobed), the cold start with three projects (beta failed at boot+69 s before ADR 0255; 156 s to all four, boot-started, after it); C4's `doctor capacity` and C5's `backup info` existed in no file and were extracted verbatim from the operator's pasted output (`extract.py`); two `UNMEASURED` (alpha's 1.15.0 window, whether a boot meets the rate limit). `docs/scope-closure.md` **§30**; the stage plan's Status block rewritten; CLAUDE.md §2 rewritten for Session 38's planner (the old copy in the scratchpad). **D2137 deferred to Session 38 by the operator** (D2144). The gate and CI are read after the commit (below).

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
- **The older cluster fixtures leak a Docker volume per run** (`docker rm -f`
  without `-v`, D2098) -- `control_cluster.py` does not; the rest are fixed by
  the next run that touches each.

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
bin/login.sh totp-confirm           # type the 6-digit code; then WAIT for a NEW code (a step is used once, D2125)
bin/login.sh password --endpoint https://control.agenticpostgresql.com/api/v1 --username control-admin
bin/org.sh invite --account --output ~/s37/invite-person
```

### Sheet W2 — your own account and your organisation (Run 11, day 2; the WORKSTATION)

```
export XDG_CONFIG_HOME=~/s37/person-config
bin/login.sh accept --endpoint https://control.agenticpostgresql.com/api/v1 --invitation-file ~/s37/invite-person --username ________
#   accept creates the account AND logs in: no `login.sh password` here (D2126)
bin/login.sh totp-enroll && bin/login.sh totp-confirm     # then WAIT for a NEW code
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
#   accept logs in: no `login.sh password` here; a member needs no factor (D2126)
bin/org.sh key-create --name walk --scopes organizations:read,projects:read --output ~/s37/member-key
bin/logout.sh                       # a key login refuses over a held session (D2126)
bin/login.sh key --endpoint https://control.agenticpostgresql.com/api/v1 --key-file ~/s37/member-key
bin/project.sh list                 # alpha-dev, beta-dev, control-prod
```

### Sheet PR1 — the probe's invitation (Run 11, day 2; the WORKSTATION)

```
export XDG_CONFIG_HOME=~/s37/admin-config
bin/context.sh show                 # `credential session`: W1's session is still held -> skip the next line (D2126)
#   only if it says `credential none`:
#   bin/login.sh password --endpoint https://control.agenticpostgresql.com/api/v1 --username control-admin   # with a NEW code
bin/org.sh invite --account --output ~/s37/invite-probe
#   the agent then runs s37-probe-enrol.py, which writes ~/s37/probe.json (0600), and
#   s37-projects-read.py: the member's key -> 403, the probe owner's session -> 409 (D2127)
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
