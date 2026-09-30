# Session 34 — Governed connectivity

**Status: PLANNED 2026-09-29 at `be439ed`. Not started.** Eleven runs, all on
`main` directly. This plan spends **D1778–D1811** in §1 and **ADR 0235–0239**.
**NEXT FREE AFTER THIS PLAN: D1812, ADR 0240.** Rows the runs add go in §1's
second table, below D1811, in execution order; the header's *Status*
paragraph is rewritten at the close to say which run added which.

**Brief:** `docs/plans/stage-4-plan.md` §5 *Session 34* whole (Builds / Already
true / Must not / Measures / Closes, `:568-611`), its rows **D1522** (the
outbox, delivery, inbound, event-triggered runs, scheduled connectors, `apg
connector init|validate|status|enable|disable`, *"the inbound route is the one
new surface Stage 4 exposes to an unauthenticated third party and it gets its
`THR-*` rows before code"*), **D1525** (34 owes the rehearsal
`delivery-retry-storm`), **D1527** (`THR-CONNECTOR-INPUT`,
`THR-WEBHOOK-REPLAY`, `THR-DELIVERY` before code), **D1529** (a restore-test
row for an undelivered event), §2.2 (one minor per session unless `upgrade
plan` prices major; *"Session 34 adds a route (a deployed-document field,
migratable)"*), §7's row for 34 (`EVT-*` / `CONN-*`; schema validation offline;
the inbound refusal and delivery live), §8 whole (the rows marked 34: *a
connector identity only narrows*; *the outbox is written in the caller's
transaction by a reviewed function, never by a trigger on a base table*; *an
inbound request is signature-checked before any database is touched*; *an
agent record carries no URL, key, token or caller value* — the delivery
record; *a workstation holds no production secret* — a connector's shared
secret is materialised on the host; *a report may not substitute an answer* —
`connector status`), §9's stop conditions (the outbox by a trigger; a change
feed; the inbound route touching the database before the signature), §10's
*"a connector's shared secret is a secret with an outside holder, and its
rotation is a provider replacement … Session 34 owns saying so in the operator
guide"*, and §11. Plus `docs/scope-closure.md` §26 *What Session 34 inherits,
in order* (`:1111-1127`: the `wait` step's `event` refused by name;
`workflow_gate_state` the one gate read; the compensation mechanism an
outbound delivery *may* reuse; the approval claim as the pattern for a signed
single-write authority; `admin_workflows:approve` as the precedent for a
connector's administrative scope), §26's *What it left* rows (D1721, D1722,
D1711, D1775, D1700, D1642, D1581/D1713, D1547, the edge's unbounded
containers), and `docs/plans/session-33-implementation-plan.md` §10 (the items
33 created) and its Run 9 sheets C1–C6 (the trip's shape).

**Shape:** eleven runs. Run 1 is documentation (rigs, three `THR-*` rows, five
ADRs) and **reads no CI verdict**. Runs 2–9 change code: each pushes and reads
that commit's own CI verdict by full SHA (`gh api "repos/Virabyan99/
agentic-postgres/actions/runs?head_sha=<40 chars>" --jq '.workflow_runs[] |
[.name, .status, .conclusion] | @tsv'`, judged on HTTP status, three buckets —
success / failure / not registered; an empty list is not a verdict, D1057).
Run 10 is the trip. Run 11 is the close and — **D1644** — commits, gates and
reads CI only if it touches `src/` (the envelope); a documentation-only close
reads none.

**Product version at close:** `CURRENT_SESSION` **34**; `template_version`
**`1.12.0`** — **migration 0036** (`connectivity`: four new `app_private`
tables, two new enums, four new columns on `workflow_step`, one definer
function in `app` granted to nobody, eleven new `app_private` definer functions
of which two are granted to nobody, two 0035 functions — `workflow_gate_state`
and `workflow_counts` — replaced in place with unchanged signatures), **one new project migration in the example set**
(`0003-note-embedding-events.sql`: `api.set_note_embedding` replaced with its
signature unchanged, now emitting `note_embedding.set@1`), **a stricter project
lint** (a project set may not create, replace, alter or drop a function the
release creates in `api` or `app`), **a new facility** (`connectors`, ADR
0188's third state beside required and optional) with **one facility-gated
generated secret** (`connector_signing_key`), **project manifest schema 7**
(`connectors: {enabled, endpoints}`), **outputs schema 19** (`connectors:
{enabled}` on both branches, migratable from 18), **a new definition file kind**
(`projects/<slug>/connectors/<name>.yaml`, `schemas/connector.schema.json`),
**the `wait` step's `event`** (compiled at last, with `match`), **two new
administrative scopes** (`admin_connectors:read`, `admin_connectors:write`),
**four new routes on the auth service** (`POST /connectors/{name}` with NO
bearer, `GET /admin/connectors`, `POST /admin/connectors/{name}/enable`,
`POST /admin/connectors/{name}/disable`), **a second and third pass inside
the one worker loop** (delivery; scheduled fire), **a new command**
`bin/connector.sh` / `bin/connector.py` (`init`, `validate`, `status`,
`enable`, `disable`, `key`), **a new rehearsal** `delivery-retry-storm`, the
restore drill's `workflow_runs` member widened with deliveries, the doctor's
twelfth check widened with deliveries (still twelve checks), a new page
`docs/connectors.md`, and **operator guide §18**. **No new container, role,
network, route PREFIX or Traefik router** (§1 D1788). ADR 0162: a released
migration, new API operations and a migratable document schema are each
*minor*; `upgrade plan` reads them only when declared (D1703), so Run 9 declares
`--also migration_added --also api_operation_added --also
document_schema_migratable` and the release paragraph says the floor is minor
**by declaration**. The new secret is facility-gated, so NO project whose
manifest leaves the facility off gains a required secret — measured in Run 9,
and a `secret_required_added` on the example renders is §9's stop.

**Written for whoever picks this up cold, and it will be a different model
than the one that planned it.** Every path below was read from the tree on
2026-09-29 at `be439ed` — four explore passes over `migrations/`,
`services/auth-api/`, `src/`, `bin/`, `schemas/`, `tests/` and `docs/`, plus
direct reads of `workflow_worker.py`, `compatibility.py`, `upgrade_plan.py`,
`secrets.required.yaml`, `deploy-project.py:750-830`, `rendering.py:340-470`,
`contracts/postgrest-api-surface.yaml` and the example project's migrations —
and is cited by `path:line`. Every third-party or product claim is measured in
Run 1's rigs with a control, or is marked as the measurement a run owes —
never assumed. **Read CLAUDE.md §1 in the launch folder before the first
command, then this plan's §1, then the appendix.** If a step here and the tree
disagree, **the tree wins and the disagreement is a divergence row** (next free
`D` after §1's table), never a silent reconciliation. **When this plan names a
line number, open the file at that line and read the surrounding twenty lines
before editing** — the numbers were right on 2026-09-29 and `ruff format`
moves them.

**The six sentences the executor most needs, in case nothing else is read:**

1. **An event is written by a reviewed function inside its caller's
   transaction, and the function lives in `app`, not `api`** (§1 D1779, ADR
   0235). `app.emit_event(p_name, p_version, p_payload)` is SECURITY DEFINER,
   owned by the object owner, **granted to nobody**: only a definer function
   that already runs as the owner — the release's or a project set's reviewed
   RPC — can call it. PostgREST cannot address it (`app` is a forbidden
   schema), so no agent or human can forge an event over HTTP. It reads the
   caller's identity from the GUCs the pre-request hook set, never from a
   parameter. **No trigger writes an event, anywhere.**
2. **An event is recorded only when something listens** (§1 D1782). The
   emitter serves any parked `wait` step of the same OWNER whose `match` the
   payload contains, and inserts one delivery per ENABLED outbound connector
   subscribed to `name@version`. If neither exists it records nothing and
   returns `NULL`. A dry run that rolls back rolls the event back with it.
3. **The inbound route checks the signature before it reads anything else**
   (§1 D1789, ADR 0237). Raw bytes → size → `X-Apg-Signature` over
   `<t>.<delivery-id>.<body>` with a key DERIVED from the facility's one
   secret and the connector's name, with a ±300 s window → only then JSON,
   and only then the database. A bad signature produces a fixed 401, no
   database call, no audit row, no receipt.
4. **A connector starts a RUN of a named, installed workflow definition as the
   agent an administrator bound to it, and that agent holds EXACTLY the
   definition's scopes** (§1 D1783, ADR 0236). There is no per-agent profile
   in this tree and a profile cannot remove a tool, so "an identity that names
   one tool" is enforced where it can be: `connector_enable` refuses an agent
   whose stored scopes differ from the definition's `required_scopes`, and
   `connector_accept` / `connector_fire_due` refuse again if the agent was
   widened later. **The worker keeps ONE path to a tool: a step.**
5. **Outbound delivery is the worker's second claim in the SAME loop** (§1
   D1790, ADR 0238): at-least-once, signed the same way the inbound route
   verifies, a fixed backoff, every non-2xx retried until `retry.max`, then
   `dead` — visible in `apg connector status` with a fixed error token and
   NEVER the payload, the URL or the key. A redirect is never followed.
6. **The secret is facility-gated, so the release stays minor** (§1 D1784,
   D1785). `connector_signing_key` is owed only by a project whose manifest
   (schema 7) sets `connectors.enabled: true`; the rendered and deployed
   documents (schema 19) carry that one boolean because three existing callers
   decide facilities from a document. **On the trip, beta's facility is a
   manifest change deployed as its own operation, AFTER the release deploy**
   (§1 D1807) — `upgrade plan` refuses a plan whose operator inputs moved.

---

## 0. Where the session starts

```
HEAD            be439ed on main, local = origin, clean (read 2026-09-29 in
                WSL). Deployed: 02ffbbd (1.11.0) on both projects.
                `git diff --name-only 1.11.0..HEAD` filtered to src/ bin/
                services/ migrations/ templates/ schemas/ compose.yaml
                deploy.sh VERSION is expected to name ONE file,
                src/agentic_postgres/capacity.py (24d0e13, the UNMEASURED
                row's text) -- re-run it in Run 1 and write the answer in its
                Done. The host CHECKOUT is at e087bca (one test module past
                the deployment).
VERSION         1.11.0 (the repo-root file VERSION; read by
                template_version() at src/agentic_postgres/__init__.py:
                698-704). CURRENT_SESSION 33 (:690; Session 33's paragraph
                :624-689). Outputs schema 18 (deployed_output.py:40). host.yaml
                schema 3. Capability manifest schema 4. Lock schema 4. Project
                lock 3. Project manifest 6 (schemas/project.schema.json:16-27).
                api-surface 2. Workflow definition schema_version 1.
                35 released migrations (0035 = 20260917120035 workflow_gates,
                migrations/manifest.json:423-432).
REGISTRY        265 requirements (tests/acceptance-registry.yaml, 5,436 lines;
                Session 33's block :5111-5436). 172 claims (CLAIMS
                src/agentic_postgres/evidence_claims.py:307-1057, Session 33's
                block :533-554), 42 declared offline (OFFLINE_CLAIMS :106-260,
                Session 33's :232-258). CLAIM_INTRODUCED_IN at
                tests/contract/test_evidence_claims.py:953, Session 33's rows
                :1140-1156. ID families (tests/contract/
                test_acceptance_registry.py:98): DEP CFG DBX SEC API AGT STO
                REC OPS DX REL CAP IDN EVAL FLEET TEN DEV EVD GEN STU NODE WF;
                the WF paragraph :84-93 and Session 33's sentence :94-97.
                234 ADRs (index docs/decisions/README.md:65-300). NEXT FREE:
                D1778, ADR 0235.
EVIDENCE        evidence/session-33.json: 172 claims, 166 passed, 5 not_run,
                1 failed (documented_path by decision). not_run:
                api_authorization, bootstrap_identity,
                credential_rotation_planes (the rotation trio -- four
                rotations needed), port_allocation (no reboot),
                replacement_host_restore (D1028). Suites: offline 6585/0/3,
                host 1058/1/7, external 25/0/8.
HOST            62.238.99.122. Both projects at 1.11.0, source_commit
                02ffbbd, deployed_through_session 33, doctor 12 ok each,
                ledgers 35 / 35+2. host.yaml schema 3: 3814 MiB / 2214 reserve
                / 37 GiB / 8 GiB reserve. Beta carries 28 revoked probe agents
                and 10 probe humans (D1700) and 3 `pending` approvals on ended
                runs (D1775). Current host script set: s33-r9-*, s33-r9b-*,
                s33-r9k-* in /home/op and WSL ~/s33r9/ (with
                s33-r9-external.sh), backed up in Session 33's scratchpad; the
                deriver model is s33r9-derive.py. OP-OWNED document copies
                /home/op/<key>-dev-outputs.json at 02ffbbd. Kits through
                kit-2026-09-28-post (host + WSL ~/dr-kits). The gate's
                --kit-dir stays on kit-2026-09-11 (D1282).
```

**What exists, measured at `be439ed`, and the session builds on:**

- **The substrate** is migrations 0034 and 0035. `0034-workflow-substrate.sql`
  (`SET LOCAL ROLE {{object_owner}}` `:104`, `RESET ROLE` `:1058`; *"Nothing
  here is in `api`"* `:43-46`): three enums (`:119-140`), four tables —
  `workflow_definition` (`:158-168`, name CHECK `^[a-z][a-z0-9-]{0,62}$`),
  `workflow_run` (`:196-210`, `agent_id` FK `app_private.agents`,
  `timeout_seconds` 1..3600), `workflow_step` (`:250-272`, **`resume_after`**,
  `idempotency_key` CHECK `^[\x21-\x7e]{8,255}$`, index `(status,
  resume_after)` `:277-278`), `workflow_worker` (`:304-309`) — and nine
  definer functions, eight granted to `{{auth_service}}` (`:1045-1056`),
  `workflow_install_definition` to nobody (`:1019-1022`, `:1031`).
  `0035-workflow-gates.sql` (`:55`/`:1449`): `workflow_run_status` gained
  `compensating` (`:57`; used only inside plpgsql bodies, `:46-54` says why —
  a DEFAULT naming it is `55P04`); `workflow_approval_status` (`:59-60`);
  `workflow_step.phase`/`compensates` (`:72-76`); `workflow_run.
  compensation_cause`/`compensation_outcome` (`:78-81`); `workflow_approval`
  (`:98-113`); `workflow_attempt` (`:134-143`, `event` CHECK IN
  (`finished`,`parked`,`approval_requested`) `:137`); the audit index
  (`:160-161`); and the functions — `workflow_begin_compensation`
  (`:185-247`, nobody), `workflow_claim_step` replaced (`:282-429`; the
  resume test `(s.status = 'parked' AND s.resume_after <= pg_catalog.now())`
  at `:353`, `resume_after = NULL` on claim at `:391`),
  `workflow_finish_step` (`:462-579`), `workflow_park` (`:598-629`),
  `workflow_run_status` (`:646-714`), **`workflow_counts` (`:726-774`)**,
  `workflow_request_approval` (`:792-860`), **`workflow_gate_state`
  (`:871-905`; returns `{"approval": null|{id,status,expires_at}, "waited":
  bool}`; `waited` is an EXISTS over `workflow_attempt` with `event =
  'parked' AND reason = 'waiting'` `:902-904`; refuses `AP404` unless the
  caller holds the claimed step `:883-887`)**, `workflow_expire_approval`
  (`:912-937`), `workflow_decide_approval` (`:960-1021`),
  `workflow_pending_approvals` (`:1034-1072`), `workflow_approval_for_token`
  (`:1088-1106`), `workflow_provenance` (`:1127-1248`), the audit reader at
  nine arguments (`:1277-1336`) and `auth_count_agent_audit` (`:1353-1390`).
  GRANTs `:1433-1447`; down `AP900` `:1451-1455`.
- **The migration scheme.** Version = authoring date + `120` + three-digit
  sequence (`migrations/manifest.json:62-424`); rendered filename
  `f"{version}_{name}.sql"` (`rendering.py:2456`); release ledger
  `app_private.schema_migrations`, project ledger
  `app_private.project_schema_migrations` (`rendering.py:1005`, `:1020`).
  Manifest rules `migrations.py:284-327` (ascending, every placeholder declared
  globally AND per entry, declared-but-unused refused). `bin/migrate.sh
  freeze-lock` is the only writer of `migrations/released.lock.json`
  (`verify_lock` `migrations.py:602-647`). **Nothing named `120036` or
  `0036-` exists.**
- **The project lint** `migrations.lint_project_set` (`src/agentic_postgres/
  migrations.py:740-860`): the placeholder allowlist
  `PROJECT_PLACEHOLDER_SOURCES` (`:88-98`: `object_owner`, `authenticated`,
  `anon`, `agent_reader`, `agent_writer`, `api_documentation`,
  `database.name`); `FORBIDDEN_STATEMENTS` (`:142-159`) matched over the
  comment-stripped up section (`:795-805`) — **`\bapp_private\b` (`:143`)
  anywhere, including function bodies**, role/schema/extension DDL, default
  privileges, security labels, rules, publications, subscriptions, `COPY …
  FROM PROGRAM`; only `PROJECT_ROLE_PREAMBLE = "SET LOCAL ROLE
  {{object_owner}}"` (`:125`, check `:807-814`); **`DROP VIEW|FUNCTION
  api.<name>` where the release publishes `<name>` (`:816-825`) — DROP only,
  not `CREATE OR REPLACE`**; FORCE RLS on every `app` table (`:827-846`); a
  down with `AP900` (`:848-860`). `SECURITY DEFINER` is allowed (the example
  uses it). **Calling `api.*` or `app.*` from a project body is not refused.**
  Callers: `rendering.py:2448`, `bin/migrate.py:416` (`freeze_project_lock`),
  `:442` (`verify_project_lock`); `dev_environment.py:712`, `:732`, `:744`
  (`lint_seed` reuses the tables); tests `test_project_migration_sets.py:417,
  437, 640-712, 733-767`, `test_dev_environment.py:879, 908, 936`.
- **The `api` contract** is `contracts/postgrest-api-surface.yaml` (sections
  `rpcs` `:56-80`, `agent_rpcs` `:98-110`, `agent_write_rpcs` `:131-137`,
  `forbidden_schemas` `:144-148` = public, app, app_private, extensions;
  *"nothing exists in `api` which this file does not name"* `:82-85`,
  `:112-115`). PostgREST exposes exactly `api` (`rendering.py:951`,
  `compose.yaml:766`), pre-request `app_private.postgrest_pre_request`
  (`compose.yaml:801`), `PGRST_OPENAPI_MODE: follow-privileges` (`:822`).
  **Pins an `api` function would move**: `tests/contract/
  test_api_migrations.py:206-218` (the exact seven), `:277-278` (functions =
  rpcs ∪ agent_rpcs ∪ agent_write_rpcs), **`:494-544` — every `api` function
  must be GRANTed by some migration; `:541-544` calls an ungranted one *"exists
  in the exposed schema and no role can call it"***;
  `test_api_surface_contract.py:147-178`, `:321-353`, `:538`;
  `tests/security/test_session3_authorization.py:687-690` (the live `pg_proc`
  list). **`app.current_user_id()`** (`0003-owner-scoped-tables-and-forced-
  rls.sql:13-27`, SECURITY INVOKER, reads the GUC `app.user_id`) is the
  release's one function in `app` today. The pre-request hook sets
  `app.user_id` to a human's subject (`0018:270`) or, for an agent, to the
  agent's OWNER, and `app.agent_id` to the agent (`0018:249-250`).
- **The example project** `projects/example/`: `capabilities.yaml`,
  `evaluation-cases.yaml`, `clients/typescript/*`, `contracts/*` (its own
  `postgrest-api-surface.yaml` with `rpcs: set_note_embedding [p_note_id,
  p_embedding]`), `docs/mcp-tool-catalog.md`, `migrations/{manifest.json,
  released.lock.json, templates/0001-note-embeddings.sql, templates/
  0002-agent-grants.sql}` (versions `20260914120001`, `20260914120002`;
  lock `follows_release_version: "20260912120031"`, schema 3), `seeds/*`,
  `workflows/{notes-retry, notes-roundtrip, tasks-approval,
  tasks-compensate}.yaml`. **`api.set_note_embedding(p_note_id uuid,
  p_embedding extensions.vector)` is the ONLY project-owned RPC**
  (`0001:75-107`, SECURITY DEFINER, `SET search_path = pg_catalog, pg_temp`
  `:78-79`; grants `:113-127` to `authenticated` and `api_documentation`,
  `0002:27-28` to `agent_writer`; `NOTIFY pgrst` `:134`); its capability says
  `requires_approval: true`, `supports_dry_run: true`, scope
  `note_embeddings:write` (`capabilities.yaml:46-68`). `api.create_note`,
  `api.create_task` and `api.update_task_status` are RELEASE-owned
  (`0030:128-235`, `0031:34-69`, `0030:237-`); **`create_task` is not a
  capability** (not in `contracts/snapshots/mcp/mcp-capabilities.canonical.
  json`).
- **The loop** `services/auth-api/app/workflow_worker.py` (762 lines):
  `POLL_SECONDS = 5` (`:96`), `SHUTDOWN_GRACE_SECONDS = 10` (`:107`),
  `RETRYABLE_TOKENS` (`:113`), `APPROVAL_REQUIRED_TOKEN` (`:117`), `WAIT`
  (`:121`), the plane's address three constants (`:135-137`) bound by
  `test_the_planes_address_is_the_one_the_deploy_publishes`
  (`tests/contract/test_workflow_worker.py:835-855`), `REFERENCE` (`:161`),
  `lease_margin_seconds()` = `2 * mcp_upstream.UPSTREAM_TIMEOUT_SECONDS`
  (`:169-184`; `mcp_upstream.py:72` = 10), `worker_identity()` (`:187-201`),
  `resolve`/`_lookup` (`:213-256`), **`_send` (`:264-291`, `urllib.request.
  Request` with the plane's Bearer/SSE headers — *"the ONE place this module
  reaches a network"*)**, `classify` (`:328-366`), `tool_value` (`:369-390`),
  `call_arguments` (`:417-436`), **`process` (`:439-632`; `WAIT` →
  `_wait` at `:457-459`)**, **`_wait` (`:635-659`: `gate_state` →
  `waited` finishes `succeeded`/`waited`, else `park(reason="waiting",
  resume_after=now+seconds)`)**, `_close_gate` (`:662-684`), **`run_forever`
  (`:692-738`: heartbeat → claim → `sleep(POLL_SECONDS)` when idle; `once`
  for proofs)**, `supervise` (`:741-762`). **There is no abstraction for a
  second kind of work** — and `test_the_loop_starts_in_auth_mode_only`
  (`test_workflow_worker.py:805-832`) asserts EXACTLY ONE `create_task` in
  `main.py` (`:821`) under `mode == "auth"`.
- **The repository** `services/auth-api/app/workflow_repository.py`: every
  method one autocommit `SELECT app_private.<fn>(%s, …)` (`:24-28`);
  `auth_service` holds no table privilege (`:9-16`); `gate_state` at
  `:288-292`; *"`workflow_begin_compensation` is the one 0035 function with NO
  method here"* (`:268-270`); D1680's rule stated at `:36-42` (a grant ships
  with its caller).
- **The auth service** `services/auth-api/app/main.py` (490 lines): the
  lifespan `:91-213` starts ONE task in `auth` mode (`:190-200`); routers
  `:296-310` (`routes.router`, `workflow_routes.router` `:305`,
  `workflow_admin_routes.router` `:310`); middleware `StructuredRequestLog`
  `:341`, `StampRequestId` `:342`; **no body-size, rate-limit or CORS
  middleware in the app**; `public_paths()` `:416-480` (the workflow paths
  `:441-444`, `:477-479`), guarded by EQUALITY in `tests/contract/
  test_auth_service_shape.py:889`. `routes._body` (`routes.py:460-491`:
  `parse_object(await request.body())` then the pydantic model),
  `routes._guard` (`:494-512`: 401/403/400/422). `strict_json.MAX_BODY_BYTES
  = 16 * 1024` (`strict_json.py:47`), checked AFTER the whole body is read
  (`:75-104`). `POST /workflows/runs` parses its body BEFORE authenticating
  (`workflow_routes.py:179-181`) — the inbound route must NOT copy that order.
- **Two authenticators and the signer** (`service.py`, 1,040 lines):
  `issue` (`:225-310`; `extra_claims` may not collide with a required claim
  `:275-277`), `authenticate` (`:314-401`, `access` only), `require_scope`
  (`:403-412`), `step_token(agent_id, *, approval_id=None)` (`:542-597`),
  `authenticate_agent` (`:599-676`, `agent` only), `create_agent`
  (`:772-802`). `POST /admin/agents` `routes.py:919-962`
  (`CreateAgentRequest` `models.py:275-296`: `name, description, role,
  scopes (1..32), secret_ttl_seconds` — **no `profile` and no `tools`**);
  `PATCH /admin/agents/{id}` `:998-1035`. The agents table
  `0011-identity-registry.sql:174-187` (`scopes text[] NOT NULL`, `owner_id
  NOT NULL REFERENCES users`) — **no profile or tool column exists**.
- **Profiles are per deployment**, `mcp.profile` in the project manifest
  (`schemas/project.schema.json:287-300`: *"a profile cannot remove a tool,
  narrow a column list, or touch a per-capability declaration"*;
  `capability_compiler.PROFILE_FIELDS` `:111-119`, `apply_profile`
  `:706-782`). The plane loads one lock per deployment. **An agent can be
  narrowed to one tool only through its stored scopes**, and only when no
  other tool shares the scope (write tools check `spec.required_scopes`,
  `mcp_tools._write_for` `:225-257`; `ToolVisibilityMiddleware`
  `mcp_authorization.py:251-295` hides and is *"not a boundary"*).
- **Scopes.** `schemas/capabilities.schema.json` `$defs/scope` (`:236-250`,
  13 names) and `$defs/administrative_scope` (`:272-283`: `admin_users:read`,
  `admin_users:write`, `admin_agents:read`, `admin_agents:write`,
  `admin_audit:read`, `admin_workflows:approve`); `scope_registry.
  administrative_scopes()` reads the schema (`:98-109`); `services/auth-api/
  app/scopes.py` `ROLE_CLASSES` `:63-107` (only `project_admin` carries
  `ADMINISTRATIVE`, `:106`), constants `:114-137`
  (`ADMIN_WORKFLOWS_APPROVE` `:137`). A bootstrapped administrator gets
  `sorted(permitted_scopes("project_admin"))` (`bin/auth-admin.py:321`);
  **existing administrators do not gain a new scope**.
- **The transport guards** (`tests/contract/test_auth_service_shape.py`):
  `TRANSPORT_NAMES` `:683-685` (`urllib, httpx, requests, aiohttp, socket,
  boto3, botocore, http`); `TRANSPORT_ALLOWLIST` `:691-717` — the
  `workflow_worker.py` row `:708-716` reads *"the loop reaches exactly one
  address, built from three constants a proof binds to the deploy's own.
  `socket` is deliberately NOT granted"*; `test_every_transport_in_the_
  service_is_declared_with_a_reason` `:774-794`; `test_the_allowlist_
  describes_modules_that_exist_and_use_what_they_declare` `:797-830` with
  **`senders = {"app/mcp_upstream.py", "app/mcp_health.py",
  "app/workflow_worker.py"}` at `:823`**.
- **No HMAC, no JSON-schema validator in the image.** `hmac`,
  `compare_digest`: 0 hits under `services/`, `src/`, `bin/`. The auth image's
  dependencies are pinned in `services/auth-api/Dockerfile` from
  `versions.env` (FastAPI 0.121.2, Pydantic 2.13.4, fastmcp 3.4.0 …);
  `jsonschema` is only a transitive, unpinned dependency of `mcp`
  (`requirements-dev.txt:590-595`), and `test_the_dockerfile_names_no_
  version_of_its_own` (`test_auth_service_shape.py:648`) means a new pinned
  dependency is a `versions.env` entry. The HOST side has `jsonschema`
  (`config.py:32`, `Draft202012Validator`).
- **Routing.** One prefix router for the whole auth app, built in
  `runtime_override._app_labels` (`:1251-1310`): rule `Host(…) &&
  (Path(`{path}`) || PathPrefix(`{path}/`))` (`:1292-1293`), middlewares
  `${BASELINE_MIDDLEWARE_CHAIN},<buffering>,<stripprefix>` (`:1297-1299`),
  buffering `maxrequestbodybytes`/`memrequestbodybytes` =
  `${AUTH_REQUEST_BODY_MAX_BYTES}` (`:1307-1308`, from
  `strict_json.MAX_BODY_BYTES` via `auth_limits.py:28-31`). The baseline chain
  `apg-baseline@file` includes `apg-rate-limit: {average: 20, burst: 40,
  period: 1s}` per source (`infra/edge/dynamic/baseline.yaml:42-46`,
  `:77-82`). Sessions 32 and 33 added `/workflows/*` and `/admin/workflows/*`
  with NO router change. **`POST https://<domain>/api/app/connectors/<name>`
  reaches auth as `/connectors/<name>` with no routing change.**
- **Secrets.** `secrets.required.yaml` (committed; identifiers only): each
  entry `name, provider_key, provider_path, introduced_in_session, required,
  origin (generated|operator_supplied), value_kind (random_hex|
  rsa_private_pem), consumers[{plane, service, target_file, uid, gid, mode,
  format}], redaction, rotate_by_replacement, must_refresh_on_start,
  one_time_initialization`, optionally `facility` (ADR 0188; the four
  `backup_mirror` entries at `:750`, `:786`, `:982`, `:1010`). The auth
  service consumes `auth_service_password` (`:490-508`, pgpass, uid/gid
  65532, 0400) and `auth_jwt_signing_key` (`:524-542`).
  `secrets_contract.FACILITIES = (FACILITY_BACKUP_MIRROR,)` (`:89-90`), the
  comment `:83-88` (*"the third state beside required and optional, because
  an optional secret cannot reach a container (Compose refuses a missing mount
  source)"*); `enabled_facilities(document)` (`:193-209`) reads
  `config.backup_mirror_enabled` (`config.py:419-430`) — *"read from its
  manifest or its rendered document -- both carry `backup.mirror.enabled` at
  the same place"*; `_validate_facility` (`:623-`: a facility-gated secret is
  required by construction). **`enabled_facilities` is called with a MANIFEST
  by `rendering.py:356`, `dr_kit.py:185`, `bin/bootstrap-providers.py:1264`,
  `bin/materialize-secrets.py:352`, and with a RENDERED OR DEPLOYED DOCUMENT
  by `bin/deploy-project.py:2168`, `bin/render-secret-override.py:79`,
  `node_restore.py:246`.** `required_secret_names` in a rendered document is
  filtered by the project's facilities (`rendering.py:348-357`). Deploy step 0
  refuses a project whose provider lacks a required generated secret and names
  the command (`deploy-project.py:754-820`: *"Run: sudo
  bin/bootstrap-providers.sh --host host.yaml --project <manifest> --apply
  --operator-credential-file …"*). `settings.FORBIDDEN_VARIABLES`
  (`services/auth-api/app/settings.py:524-544`), `REQUIRED_VARIABLES` for
  auth (`:453-457`); compose's auth block `compose.yaml:1182-1334`
  (`APG_DATABASE_PASSFILE` `:1293`, `APG_SIGNING_KEY_FILE` `:1295`; networks
  `internal` and `edge` `:1332-1334`; `internal` is `internal: true`
  `:1795-1799`).
- **Change classes** (`src/agentic_postgres/compatibility.py:89-105`):
  `migration_added`, `api_operation_added`, `capability_added`,
  `secret_optional_added`, `document_schema_migratable` MINOR;
  **`secret_required_added` MAJOR**, auto-classified whenever a rendered
  document's `secrets.required_names` gains a member (`upgrade_plan.py:
  243-248`). `bin/upgrade.py` `DECLARABLE` (`:129-138`) includes
  `document_schema_migratable`. `build_plan` (`upgrade_plan.py:291-366`)
  **BLOCKS when an operator digest moved**: *"An upgrade changes the release,
  not the manifests you supply; … deploy the manifest change as its own
  operation."*
- **Outputs.** `deployed_output.SCHEMA_VERSION = 18` (`:40`); the schema enum
  at `schemas/outputs.schema.json:36-41` (rendered) and `:327-332`
  (deployed); `mirrorSettings` `:2069-2074`; the migrator chain ends at
  `output_migrations.migrate_v17_to_v18` (`:1338`); `evidence.py:229-238`
  refuses a document at another version. `evidence.ISOLATED_FIELDS`
  (`:37-68`, 18 pointers) — a boolean facility flag is not a project-scoped
  identity and joins no pointer (D1785).
- **Definitions and their installers.** `src/agentic_postgres/
  workflow_definition.py` (1,018 lines): `WORKFLOWS_SUBDIR = "workflows"`
  (`:71`), `REFERENCE` (`:77`), wait bounds (`:123-126`), `NOT_ON_A_WAIT`
  (`:132`), `definitions_of` (`:481-491`), `load` (`:494-510`),
  `source_digest` (`:513-521`), `_check_references` (`:625-659`),
  **`_compile_wait` (`:782-824`) with the refusal at `:793-798`: *"a wait on
  an event arrives in Session 34 with the events that resume it; this release
  waits on a time only"***, `compile` (`:827-897`), `lock_view_for_project`
  (`:937-985`). `schemas/workflow.schema.json` (255 lines): the step `oneOf`
  (`:64-114`), `wait` (`:171-187`: `seconds` 1..3600, `event` a string,
  `additionalProperties: false`, *"`event` is admitted by this schema only so
  that the compiler can refuse it"* `:175`). The refusal's proof:
  `tests/contract/test_workflow_definition.py:739-742`
  (`test_a_wait_on_an_event_is_refused_naming_session_thirty_four`),
  registered under WF-DEF-002 (`tests/acceptance-registry.yaml:5206`,
  `:5223`). **Deploy step 6d** `bin/deploy-project.py:2452-2459` (inside step
  6's guard, before 6b at `:2462`) calls `install_workflow_definitions`
  (`:868-943`: the INSTALLED manifest; `no workflow definitions (the project
  declares no migration set)` `:896`; `… (the project declares none)` `:901`;
  `LockView.from_json` of the lock this deploy wrote `:905`; a compile failure
  exits 5 `:921`; `container_exec.run(container, "psql", "-U", "postgres",
  "-d", database, *statement.argv, input=statement.stdin, timeout=60)`
  `:922-933`; the line printed `:943`), through
  `src/agentic_postgres/workflow_install.py` (`INSTALL_SQL` `:41-45`,
  `PSQL_FLAGS` `:51`, `statements()` `:82-110`: `-v` variables and `-f -`,
  D1684). `bin/dev.py` installs the same way (`:445-460`, `:467-518`);
  `tests/contract/test_dev_environment_cluster.py:186-249` asserts
  `workflows   4 definition(s) installed`.
- **The command pattern.** `bin/workflow.py` (561 lines; exit codes
  `:40-43` 0/2/3/5; `ROUTES` `:53-57`; `TOKEN_VARIABLE = "APG_AGENT_TOKEN"`
  `:63`; `ADMIN_ROUTES` `:72-77`; `HUMAN_TOKEN_VARIABLE = "APG_API_TOKEN"`
  `:83`; `_app_base` `:334-359` reads `routes.app` from `--project-outputs`;
  `command_human` checks `--confirm` == `--run` `:483-522`) and
  `bin/workflow.sh` (348 lines: `usage()` `:46-110`, `verb_usage()`
  `:112-265`, `main()` `:290-346`). `tests/contract/test_cli_contract.py`
  (`SHELL_COMMANDS` `:42-205`, `PYTHON_COMMANDS` `:207-267`,
  `COMMANDS_WITH_VERBS` `:451-472`, the index-mode check `:332-346`, the
  no-credential-flag check `:1069-1082`, `test_every_command_in_bin_is_
  covered_by_this_module` `:1032-1066`); ADR 0093's import guard
  `tests/contract/test_operator_commands_run_on_the_host.py`
  (`HOST_PACKAGES = {"agentic_postgres", "yaml"}` `:47`). `bin/apg.sh --list`
  derives verbs from `bin/*.sh` (`:154-164`) — `apg connector` resolves with
  no edit. `tests/contract/test_workflow_command.py` is the model for a
  command's proofs (`:237-275` routes, `:278` token from environment, `:324`
  no SQL, `:388` every verb's help without a project, `:639` no own address).
- **The readers.** The doctor's twelve checks (`bin/doctor.py` `diagnose()`
  `:1144-1168`; `WORKFLOW_QUERY` `:752`; `probe_workflow` `:801-885` with the
  approvals lines `:863-877`); `diagnosis.workflow_record`
  (`src/agentic_postgres/diagnosis.py:583-678`, OK or UNKNOWN, never a
  threshold, the detail `:672-677`). `rehearsal.SCENARIOS` (`rehearsal.py:
  81-100`, ten: … `admission-refused` `:94`, `worker-restart` `:99`),
  `WORKER_SERVICE = "auth"` (`:112`), `DEPLOYED_DOCTOR_CHECKS` (`:117-126`),
  `BOUNDS` (`:132-140`), `refuse_without_a_reading` (`:317-342`),
  `_worker_restart` (`:886-976`), `_PLANNERS` (`:979-990`), `verdict`
  (`:1133-1253`); `bin/rehearse.py` (`gather_facts` `:192-293`, `observe`
  `:538-585`, `rehearse` `:711-789`, `build_parser` `:853-869`);
  `bin/rehearse.sh` (hand-written list in `usage()` `:33-84`);
  `docs/recovery-operations.md` §4 table `:107-118`;
  `tests/contract/test_rehearsal.py` (`:131`, `:704` parametrised over
  `SCENARIOS`; worker-restart `:1370-`). The drill:
  `bin/restore-test.py` `observe_restored_instance` (`:458-541`;
  `workflow_runs` `:496-512`; `approvals` nested `:514-538`,
  `APPROVALS_BY_STATUS` `:545-550`), `restore_drill.evidence_document`
  (`:604-692`, `workflow_runs` passed through `:689`),
  `tests/recovery/test_session32_workflow_restore.py` (141 lines, REC-WF-001),
  the stubs in `tests/contract/test_restore_test_command.py:543`, `:728-763`,
  `:1075-1132`.
- **The gate and the live module to derive from.** `bin/session-33-check.sh`
  (1,644 lines, mode 755): header `:1-108`, `readonly SESSION=33` `:117`,
  `usage()` `:174-477`, `parse_arguments()` `:513-707` (24 flags + `--mode` +
  `-k`), `mode_offline()` `:1151-1368` (the `apg dev` round trip `:1278-1284`),
  `mode_host()` `:1370-1566`, `mode_external()` `:1568-1633`;
  `tests/contract/test_session_thirty_three_gate_modes.py` (917 lines;
  `SESSION_THIRTY_THREE_CLAIMS` `:93-112`; the no-gap test `:244`;
  `test_exactly_this_sessions_declared_claims_are_offline` `:670`).
  `tests/deployment/test_session33_gates.py` (901 lines; `pytestmark`
  `:50-58`; `SWEEP` `:76`; `_create_subject` `:107`, `_login` `:131`,
  `ProbeAgent` `:139`, `_create_agent` `:168` (name `apg-s33-{label}-{SWEEP}`),
  `_revoke` `:193`, `_until` `:394`, `_audit` `:428`; fixtures `gate_owner`
  `:213-242` (reads beta's deployed lock vocabulary FIRST), `approver`
  `:245-274`, `gate_agents` `:302-336`). `tests/deployment/conftest.py`
  (2,101 lines): `as_root` `:92-104`, `project_a` `:129-132`, `project_b`
  `:134-137`, `api_call` `:897-898`, `psql` `:959-960`, `app_base`
  `:1233-1234`.
- **Documentation.** `docs/threat-model.md` (171 lines): table header `:19`,
  rows `:21-37`, **`THR-APPROVAL` the last row at `:37`**; no row for events,
  delivery or inbound. `docs/workflows.md` (325 lines): `### Wait` `:149`,
  `## What is not here yet` `:310-319` (*"Events — a run started by
  something other than a call, and `wait: {event}` | Session 34"*,
  *"Outbound delivery and inbound connectors | Session 34"*).
  `docs/operator-guide.md` (1,496 lines; release line `:22`; §16 `:1146`; §17
  *Workflows, on a deployment* `:1279-1496`, its *If something goes wrong*
  `:1472`; **no §18**). `docs/README.md` (161 lines; Workflows row `:63`;
  every `docs/*.md` indexed exactly once, `test_documentation_index.py:
  455-486`). `docs/upgrade-guide.md` (847 lines; release table header `:79`,
  1.11.0 row `:100`; the 1.9.0/1.8.0 rows out of order at `:97-98` — leave
  them). `README.md:7` (*"Status: Session 33 implemented"*, guarded by
  `test_documentation_index.py:170`, `:199`). `docs/capacity-envelope.md`
  (generated from `capacity.py`; `ENVELOPE` `:113`, 21 rows; `UNMEASURED`
  `:611`, 6 rows).

---
## 1. The divergence table

Six columns. Each row is a **measured fact about the tree at `be439ed`** set
against what the brief (the stage plan's §5 *Session 34*, its §1 rows, §8, §10,
scope-closure §26 and CLAUDE.md §9) says, with the decision this plan takes.
**Next free number after this table is D1812.** Rows the runs add go in the
second table below, in execution order.

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D1778** | Stage plan §5: *"Migration 0035: `app_private.outbox` and `api.emit_event(…)`"* (`stage-4-plan.md:571`). | 0035 is `workflow_gates`, applied on both projects 2026-09-28 (`migrations/manifest.json:423-432`). Nothing named `120036` or `0036-` exists. | **Migration 0036, `migrations/templates/0036-connectivity.sql`, manifest name `connectivity`, version `2026MMDD120036` with the date the executor writes it** (it must sort above `20260917120035`; on 2026-09-29 it is `20260929120036`). The outbox tables are named for what they hold: `connector_event` (the event) and `connector_delivery` (one row per subscriber — the outbox proper). | A stage plan's migration number is a prediction; the manifest is the fact. `outbox` names a pattern, not a table a reader can find. | — |
| **D1779** | Stage plan §5: *"`api.emit_event(name, version, payload)` (SECURITY DEFINER, writing the caller's row inside the caller's transaction, granted to the request roles like the audit functions)"*; D1522: *"a function under a schema the lint allows (`api.emit_event`…)"*. | **Two things refuse that shape.** (1) A function in `api` granted to the request roles is addressable as `POST /rpc/emit_event` by every agent and every signed-in human (PostgREST exposes `api`, `rendering.py:951`; the audit functions ARE reachable that way — `test_session9_agent_writes.py:693` is the control), so any caller could forge any event with any payload. (2) A function in `api` granted to NOBODY is refused by `test_api_migrations.py:494-544` (*"exists in the exposed schema and no role can call it"*, `:541-544`), and any `api` function moves five exact pins (`test_api_migrations.py:206-218`, `:277-278`; `test_api_surface_contract.py:147-178`, `:321-353`; `test_session3_authorization.py:687-690`). The lint refuses `app_private` anywhere in a project body (`migrations.py:143`), so a project cannot call a helper there. **`app` is already a forbidden PostgREST schema (`postgrest-api-surface.yaml:144-148`) and already holds one release function, `app.current_user_id()` (`0003:13-27`).** Project RPCs are SECURITY DEFINER running as `object_owner` (`0001:75-79`), the role that owns every release object. | **`app.emit_event(p_name text, p_version integer, p_payload jsonb) RETURNS uuid`, SECURITY DEFINER, `SET search_path = pg_catalog, pg_temp`, created as `object_owner`, `REVOKE ALL … FROM PUBLIC`, granted to NOBODY.** Only a function already running as the owner can call it: the release's own definer functions and a project set's reviewed definer RPCs. No request role can execute it, PostgREST cannot address it, and the `api` contract does not move. Identity from `app.current_user_id()` and the GUC `app.agent_id` (`0018:249-250`, `:270`) — never a parameter (SEC-PARAM-001's rule). | The brief's own invariant — *"written in the caller's transaction by a reviewed function"* — is what `app` gives; `api` would give it plus a forgeable HTTP door, or a guard to weaken. A grant to nobody is the tightest grant this tree has (0034's install function). | **0235** |
| **D1780** | Stage plan §5: *"measured first in a rig that the lint still refuses a project migration naming `app_private` (the control) while one calling `api.emit_event` passes"*. | The lint refuses `DROP VIEW\|FUNCTION api.<release name>` (`migrations.py:816-825`) **and nothing else about a release function.** A project set runs as `object_owner`, which OWNS `api.create_note`, `app.current_user_id` and (after 0036) `app.emit_event`, so a project template containing `CREATE OR REPLACE FUNCTION api.create_note(...)` passes the lint and would replace the release's audited, idempotent write with anything — **read from the code; rig 34a measures both halves.** The same hole would let a project replace `app.emit_event` itself. | **The lint gains one rule: a project set may not `CREATE [OR REPLACE]`, `ALTER` or `DROP` a FUNCTION that the release creates in `api` or `app`.** The set of names is DERIVED from the release templates by `sql_surface` (never typed; D1677 — read the call as written), and the existing DROP rule is folded into it. Rig 34a: the control (a project body naming `app_private` refused), the positive (a project definer RPC calling `app.emit_event` passes and executes), and the new refusal (`CREATE OR REPLACE FUNCTION api.create_note` refused; `app.emit_event` refused). | A stricter lint, not a weaker one (CLAUDE.md §6). The emitter is only as trustworthy as the rule that nobody but the release defines it; the rule's absence for `api.create_note` is older than this session and is closed in the same stroke. | **0235** |
| **D1781** | Stage plan §5: *"A project's reviewed RPC calls `api.emit_event`"*; *"Ends on a host: an inbound request signed correctly creating a TASK on the example project"*. | **`api.set_note_embedding` is the ONLY project-owned RPC** (`projects/example/migrations/templates/0001:75-107`). `api.create_task` exists (`0031:34-69`) but is **not a capability** (absent from the release lock), so no tool, no step and no connector can reach it. `create_note` IS a lock tool (`create_note@1.0.0`, write, `notes:write`). | **The example set gains `projects/example/migrations/templates/0003-note-embedding-events.sql`**: `CREATE OR REPLACE FUNCTION api.set_note_embedding(p_note_id uuid, p_embedding extensions.vector)` with its signature, grants and body UNCHANGED plus one line after the upsert, `PERFORM app.emit_event('note_embedding.set', 1, pg_catalog.jsonb_build_object('note_id', p_note_id));` — the payload names the note and NEVER carries the embedding (768 floats the capability redacts). **The inbound proof creates a NOTE** (through `create_note`), not a task. | Adding `create_task` to the release lock is a capability change (`capability_added`) nobody asked for; the host proof's point is *a signed request reaching one governed write*, which `create_note` is. The payload rule is `audit.redact`'s, applied to an event. | 0235 |
| **D1782** | D1522: *"versioned domain events on a transactional outbox"*; the specification's *"durable, at-least-once, … replayable"*. | Nothing exists (`outbox`, `emit_event`, `delivery`: 0 hits). The substrate's retention story is already owed twice (D1700, D1775). | **An event is recorded only when something listens.** Inside the caller's transaction the emitter (1) serves every parked `wait` step awaiting `name@version` whose run's agent has the caller's OWNER and whose resolved `match` the payload contains (`@>`), and (2) if at least one ENABLED outbound connector subscribes to `name@version` and has an endpoint, inserts ONE `connector_event` row and ONE `connector_delivery` row per such connector. It returns the event's id, or `NULL` when no delivery was recorded. Name `^[a-z][a-z0-9_]{0,62}(\.[a-z][a-z0-9_]{0,62}){0,3}$`, version 1..999, payload a JSON object of at most 8,192 bytes (`octet_length(p_payload::text)`), else `PT422`; no owner identity → `PT401`. | A log of events nobody reads is a retention problem with no reader (ADR 0213's shape); a subscriber enabled later sees later events, which is what *"enabled"* means. The size bound keeps a delivery inside the 16 KiB the edge and the app accept (D1788). | 0235 |
| **D1783** | Stage plan §5: *"then exactly one allowlisted tool invoked as the connector's agent identity (created like any agent, under a profile that names one tool)"*; *"Scheduled: … invoking one tool"*; §8: *"A connector identity only narrows — ADR 0183; a profile naming one tool"*. | **There is no per-agent profile.** `mcp.profile` is per DEPLOYMENT (`project.schema.json:287-300`) and *"cannot remove a tool"* (`:299`); the agents table has no profile or tool column (`0011:174-187`); `CreateAgentRequest` takes `name, description, role, scopes, secret_ttl_seconds` (`models.py:275-296`). An agent is narrowed only by its stored scopes, and a scope may serve several tools. The worker has exactly one way to call a tool: a step (`workflow_worker.process`). | **An inbound or scheduled connector names an installed workflow DEFINITION (`workflow: name@version`) and starts a RUN of it as the agent an administrator BINDS to the connector.** `app_private.connector_enable` refuses an agent that is not `active` (`agent_not_active`), is bound to another connector (`agent_already_bound`), or whose stored scopes are not EXACTLY the definition's `required_scopes` — plus `meta:read` if and only if rig 34c shows the plane needs it for a `tools/call` (`agent_scopes_differ`, naming the difference). `connector_accept` and `connector_fire_due` re-check the equality and refuse `agent_scopes_differ` if the agent was widened after binding. A one-tool connector is a one-step definition. | The brief's intent — the connector holds the least authority that lets it do its one thing — is kept, at the only place this tree can enforce it; a per-agent profile would be a second permission model (the stage's §9 failure mode). Starting a run inherits the scope check, the per-step token, the budgets, the audit and the idempotency key with no new code path to a tool. | **0236** |
| **D1784** | Stage plan §5: *"a secret name the deploy materialises"*; §10: *"a connector's shared secret is a secret with an outside holder, and its rotation is a provider replacement"*; §2.2: *"a worker that needs a new secret with no default is `secret_required_added`, a major"*. | Secrets are STATIC per release (`secrets.required.yaml`; no per-connector mechanism). A new `required: true` secret moves every rendered document's `secrets.required_names` and is auto-classified `secret_required_added` → **major** (`upgrade_plan.py:243-248`). An optional secret cannot reach a container (`secrets_contract.py:83-88`). **A facility-gated secret is owed only by a project with the facility and is required there by construction** (ADR 0188; `FACILITIES` `:89-90`; `rendering.py:348-357` filters `required_names` by facility). | **One new secret, `connector_signing_key`**: `provider_key: APG_CONNECTOR_SIGNING_KEY`, `provider_path: /auth`, `introduced_in_session: 34`, `required: true`, `origin: generated`, `value_kind: random_hex`, **`facility: connectors`**, one consumer `{plane: compose, service: auth, target_file: connector_signing_key, uid: 65532, gid: 65532, mode: "0400", format: raw}`, `redaction: full`, `rotate_by_replacement: true`, `must_refresh_on_start: false`, `one_time_initialization: false`. `secrets_contract.FACILITY_CONNECTORS = "connectors"` joins `FACILITIES`. **Each connector's key is DERIVED, never stored**: `hmac.new(bytes.fromhex(master), b"apg-connector-key-v1\x00" + name.encode("ascii"), hashlib.sha256).hexdigest()`. The derivation is written twice — `src/agentic_postgres/connector_keys.py` (for `bin/connector.py key`) and `services/auth-api/app/connector_signature.py` (the route and the loop), because `bin/` may not import a service module (ADR 0093) — and **a proof holds the two together** on fixed vectors (D1682's pattern). | A project that declares no connectors owes nothing new, so the release stays minor. One master per project means one provider value, one materialisation, and a rotation that is the other three rotations' shape (a provider replacement plus a redeploy) — which the operator guide says, with its consequence: every connector of the project changes key at once. | **0237** |
| **D1785** | Stage plan §7: *"Every new deployed-document field is classified in the isolation matrix in the session that adds it … 34's connector route"*. | `enabled_facilities` is called with a RENDERED OR DEPLOYED DOCUMENT by `bin/deploy-project.py:2168` (step 0's bootstrap check), `bin/render-secret-override.py:79` (the mounts) and `node_restore.py:246`, and with a MANIFEST by four others — *"both carry `backup.mirror.enabled` at the same place"* (`secrets_contract.py:193-209`). A connector facility known only to the manifest would be invisible to three readers. **The route needs no document field** (D1788). | **Project manifest schema 7** adds optional `connectors: {enabled: boolean (default false), endpoints: {<connector-name>: <url>}}`, forbidden below 7 (the file's own rule, `project.schema.json:26`); `config.PROJECT_CONNECTORS_FROM = 7`; **`config.connectors_enabled(document)` is the ONE reader** (the `backup_mirror_enabled` shape, `config.py:419-430`). **Outputs schema 19** adds `connectors: {enabled: boolean}` to BOTH branches, `output_migrations.migrate_v18_to_v19` defaulting `false`, `deployed_output.SCHEMA_VERSION = 19`. `endpoints` is NOT copied into any document (D1786). The boolean joins no `ISOLATED_FIELDS` pointer — two projects may both enable it — and the isolation proofs are re-read, not widened. | ADR 0002: one reader of a fact, readable from every document a caller holds. The migratable document move is `document_schema_migratable` (minor, declared). | 0237 |
| **D1786** | Stage plan §5: *"a connector of kind `outbound-webhook` declared in `projects/<slug>/connectors/<name>.yaml` (event, URL, a secret name the deploy materialises)"*. | A committed connector file is shared by EVERY deployment of its set: `projects/example` is rendered by beta AND by the two fixtures (`project.example.yaml`, which fixture-alpha is, names it). One URL in the file would send fixture and production events to one place. | **The file declares WHAT (event, retry, the definition to start, the body shape); the manifest declares WHERE: `connectors.endpoints.<name>` in `project.<key>.yaml`**, read by step 6e from the INSTALLED manifest and stored in the connector's row. An endpoint is `http://` or `https://`, a host, an optional port and path, **no userinfo, no query, no fragment** (so it cannot carry a credential); `validate` and 6e refuse anything else, naming the connector and the reason, never the value. **The URL appears in no document, no delivery record, no status, no log line and no error** — the worker holds it in memory for one attempt. An enabled outbound connector with no endpoint is refused at `enable` (`no_endpoint`). | *"Never log a URL"* (CLAUDE.md §6) is easiest to keep for a value that never enters a record. A per-deployment value belongs in the per-deployment input, like `backup.mirror.endpoint`. | 0238 |
| **D1787** | Stage plan §5: *"JSON-schema validation from the connector's file"*. | **No JSON-schema library is declared in the auth image** (`jsonschema` is a transitive, unpinned dependency of `mcp`, `requirements-dev.txt:590-595`; `test_auth_service_shape.py:648` requires any new pinned dependency to come from `versions.env`). The host has `jsonschema` (`config.py:32`). Pydantic 2.13.4 is in the image. | **An inbound connector declares its body in a CLOSED SUBSET, not arbitrary JSON Schema**: `body: {members: {<name>: {type: string\|integer\|boolean, required: bool, max_length: 1..8192 (string), minimum/maximum (integer)}}}`, at most 16 members, names `^[a-z][a-z0-9_]{0,62}$`, no nesting, no extra members accepted. `schemas/connector.schema.json` validates the FILE on the host; the service validates a BODY against the compiled declaration with ~60 lines in `services/auth-api/app/connector_body.py`, refusing `body_not_permitted` naming the member (never its value). A proof feeds the same twelve cases to the host compiler's reference validator (`src/agentic_postgres/connector_definition.py` `check_body`) and the service's, and asserts identical verdicts. | A webhook body that becomes a run's `input` needs names and bounds, not a general schema language; a pinned dependency added to the verifier for a subset is weight with no reader. The two-reader proof is D1682's pattern. | 0237 |
| **D1788** | Stage plan §8: *"An inbound request is signature-checked before any database is touched"*; §5: *"`POST /connectors/<name>` on the auth service behind the project's router"*; §7: *"34's connector route"* as a document field. | **One prefix router for the whole auth app** (`runtime_override._app_labels:1251-1310`); `/workflows/*` and `/admin/workflows/*` arrived with NO router change (last touch of `naming.py`/`runtime_override.py` is Session 31's `eb35f38`). The baseline chain applies `apg-rate-limit` 20/s average, burst 40 per source (`infra/edge/dynamic/baseline.yaml:42-46`) and the buffering middleware caps the body at 16 KiB (`:1307-1308`); the app re-checks 16 KiB after reading (`strict_json.py:47`, `:75-104`). `public_paths()` is guarded by EQUALITY (`test_auth_service_shape.py:889`). | **No router, no route prefix, no deployed-document field.** The route is `POST /connectors/{name}` in a new module `services/auth-api/app/connector_routes.py`, mounted in `auth` mode beside the workflow routers, added to `public_paths()`, published in `contracts/app-openapi.canonical.json` (an `api_operation_added`). A sender reaches it at `https://<project domain>/api/app/connectors/<name>`. The edge's rate limit and body cap apply to a sender like any caller, and `docs/connectors.md` says so (a sender that bursts past 40 sees 429). | The router exists; a second one would be a second name in the isolation matrix for nothing. Documenting the edge's limits is cheaper and truer than a connector-specific limit nobody measured. | 0237 |
| **D1789** | Stage plan §5: *"signature over a shared secret, a replay window keyed on the delivery id"*; *"an HMAC over the body"* outbound. | No HMAC anywhere (0 hits). `routes._body` parses then validates (`routes.py:460-491`); Starlette caches `request.body()`, so bytes can be verified before parsing. | **One scheme, both directions** (`services/auth-api/app/connector_signature.py`): headers `X-Apg-Delivery: <uuid>`, `X-Apg-Event: <name>@<version>` (outbound only), `X-Apg-Signature: t=<unix seconds>,v1=<64 lowercase hex>`; the signed bytes are `f"{t}.{delivery_id}.".encode("ascii") + body`; HMAC-SHA256 under the connector's derived key; compared with `hmac.compare_digest`; `TIMESTAMP_TOLERANCE_SECONDS = 300` either side. **The route's order is fixed and proved**: (1) the name matches `^[a-z][a-z0-9-]{0,62}$`, else 404; (2) the key file is present, else 404 (the facility is off: there are no connectors to name); (3) the raw body is at most 16 KiB, else 413; (4) both headers parse, the timestamp is inside the window and the HMAC matches, else ONE fixed 401 `{"error": "signature_invalid"}` for every cause; (5) only now `strict_json.parse_object`, else 400; (6) only now the database. A proof drives the route with a repository fake that raises on ANY call and asserts no call for eight bad-signature cases (control: a good signature makes exactly the expected calls). **Rig 34b** measures the Python HMAC against `openssl dgst -sha256 -mac HMAC -macopt hexkey:…` over the same bytes (the independent signer). | Signing the delivery id stops a captured body from being replayed under a fresh id inside the window; one 401 for every cause tells a prober nothing. The fake-that-raises is the only proof of *before any database* that cannot pass vacuously. | **0237** |
| **D1790** | Stage plan §5: *"delivered by the worker"*; D1522: *"the outbox, the delivery and the trigger are one worker's three loops"*. | **The loop has ONE task and one kind of work** (`run_forever` `:692-738`), and `test_the_loop_starts_in_auth_mode_only` (`test_workflow_worker.py:805-832`) asserts exactly one `create_task` in `main.py`. | **Delivery and the schedule are PASSES inside `run_forever`, never a second task**: each iteration heartbeats, claims and processes at most ONE step, claims and delivers at most ONE delivery, and calls `connector_fire_due` once; it sleeps `POLL_SECONDS` only when the iteration did nothing. So a retry storm cannot starve steps (one delivery per iteration, and a delivery is claimed only when its `next_attempt_at` has passed), and the one-task proof stays true unchanged. | ADR 0226's reason for one loop — a worker that cannot take the verifier down — applies to every pass; three tasks would triple the supervision surface for no measured need. | **0238** |
| **D1791** | Stage plan §5: outbound *"HMAC-signed, at-least-once"*. | The worker's transport row says *"the loop reaches exactly one address, built from three constants a proof binds to the deploy's own"* (`test_auth_service_shape.py:708-716`); a delivery to an operator's URL would make that sentence false. `senders` is a closed set at `:823`. `urllib`'s default opener follows redirects. | **A new module `services/auth-api/app/connector_delivery.py`** owns the one outbound POST (`_post(url, headers, body, *, timeout) -> (status, error_token)`) with its OWN `TRANSPORT_ALLOWLIST` row (`{urllib}`, reason: *"delivers one signed body to the endpoint an operator declared for one connector; follows no redirect; `socket` is not granted"*) and joins `senders` — **a reviewed widening of a closed set, not a weakening**. The opener is built with a redirect handler that refuses (a 3xx is the attempt's result, `http_3xx`). `workflow_worker.py`'s row and its sentence stay exactly as they are. Rig 34b measures the default opener following a 307 and the refusing one not. | A guard whose reason stops being true is a guard nobody can rely on; a module per destination keeps each reason literal. A redirect could carry a signed body to an address nobody declared. | 0238 |
| **D1792** | §8 / D1527: `THR-DELIVERY` — *"an outbound endpoint learning more than its payload"*. | `auth` is on `internal` (`internal: true`, no egress) and `edge` (`compose.yaml:1332-1334`, `:1795-1799`); nothing restricts which address a process on `edge` may reach; there is no SSRF or allowlist code anywhere. | **The endpoint is operator-declared in a root-owned manifest and never caller-supplied**; that is the control. `THR-DELIVERY` states the residual plainly: an endpoint naming an internal service (`postgrest:3000`, `mcp:8080`) would receive the signed body — and nothing else: no bearer, no cookie, no project credential; the key never leaves the process. Rig 34d measures that a sink on the project's `internal` network is reachable from `auth` by a network alias (the trip's sink) and that a container on `edge` alone cannot resolve it (the control). | A resolver-level allowlist is a policy with no measured threat in an appliance whose only writer of the manifest is root; the residual is written down instead of hidden. | 0238 |
| **D1793** | Scope-closure §26 item 1: *"The `wait` step's `event` is refused by name … Session 34 adds the event that resumes it"*; item 2: *"`workflow_gate_state` is the one gate read. An event gate is a new state in it"*. Stage plan: *"a `wait` step in 33 resumes on `name@version`"*. | The compiler refuses `event` (`workflow_definition.py:793-798`) and a PROOF pins the refusal (`test_workflow_definition.py:739-742`, WF-DEF-002). The schema's `event` is a bare string (`workflow.schema.json:182-185`). Nothing says WHICH event resumes WHICH run: an event carries no run id, and two owners' runs may wait on one name. | **`wait: {event: "<name>@<version>", match: {<member>: <literal or whole reference>}, seconds: N}`** — `seconds` is the maximum wait (the existing bound, `< timeout_seconds`), `match` at most 8 members whose values are literals or WHOLE `{{input.k}}`/`{{steps.<earlier>.<field>}}` references. The worker resolves `match` once and parks with `workflow_await_event(…)` (reason `awaiting_event`, `resume_after = now + seconds`). **An event resumes a waiting step only when the run's agent's OWNER is the emitter's owner and the payload contains the resolved match** (D1782). `workflow_gate_state` gains `"event": null \| {"served": bool}`; a reclaim finishes `succeeded`/`event_received` with result `{"event": "<name>@<v>", "payload": {…}}` when served, or `failed`/`event_timeout` when not (compensation then runs by the existing path). **`test_a_wait_on_an_event_is_refused_naming_session_thirty_four` is REPLACED** by stricter proofs of the feature and of every refusal (ADR 0239 authorises the replacement; WF-DEF-002's node ids move in Run 5, as D1750's did). | The owner is the only correlation this tree already enforces everywhere (RLS); a match on payload members is the least a definition needs to say *this note*. Replacing a passing proof needs an ADR (CLAUDE.md §6) — the refusal it pinned was a promise this session keeps. | **0239** |
| **D1794** | Scope-closure §26 item 3: *"The compensation mechanism … An outbound delivery that fails terminally may reuse it."* | Compensation is reverse-ordered WRITE STEPS of a run (0035 `workflow_begin_compensation`); a delivery is not a step, calls no tool, and belongs to no run. | **Not reused.** A dead delivery is terminal and visible (`dead`, `last_error`, `attempts` in `apg connector status`); nothing is undone, because a delivery changed nothing in the database. A workflow that must react to a failed delivery is not expressible in Stage 4. | *"May"* in the inheritance list, measured: the mechanism has no subject here. | 0238 |
| **D1795** | Scope-closure §26 item 4: *"The approval claim as the pattern for any other signed, single-write authority"*. | A connector's run is an ordinary run of its bound agent: every step is minted by `step_token(agent_id)` with the agent's stored scopes; no step needs an authority the agent lacks. | **No new token claim.** The pattern that IS reused is its discipline: authority built only by the signer from the database (the binding row), checked at the point of use (`connector_accept`/`connector_fire_due` re-check the scopes). | A claim with nothing to authorise would be a second authority path to keep honest for nothing. | 0236 |
| **D1796** | Scope-closure §26 item 5: *"`admin_workflows:approve` as the precedent for a connector's administrative scope. It is held by `project_admin` alone, NO existing administrator gains it on upgrade"*. | The administrative enum (`capabilities.schema.json:272-283`) holds six; every scope is `resource:verb` (`test_scope_registry.py:91`); `api_surface.reserved_resource_names()` reserves the part before `:` (`api_surface.py:247-262`). | **Two scopes: `admin_connectors:read` (`GET /admin/connectors`) and `admin_connectors:write` (enable, disable)**, both in the administrative enum AND `$defs/scope`, constants in `scopes.py` beside `:137`; `project_admin`'s ceiling carries them by class; **no existing administrator gains either on upgrade** (the operator grants them by `PATCH /admin/users`, stated in the release row and operator guide §18). The pinning proofs Session 33 moved (`test_scope_registry.py:68-87`, `:308-346`, `:381-388`, `test_scope_vocabulary.py:321-339`, `test_auth_endpoints.py:59-65`, `test_studio_runtime.py:84`) move again to the new EXACT sets. The vocabulary moves every compiled lock's bytes (not `tools_sha256`), so `auth` and `mcp` are recreated on deploy (ADR 0200 §2) — the image moves anyway. | A read twin exists here because a status is a read an auditor may need without the power to enable; an enable is a write. | 0236 |
| **D1797** | Stage plan §5: *"`apg connector init\|validate\|status\|enable\|disable`; `test` is `dry-run`"*. | A dry run of a WORKFLOW exists (`workflow run --dry-run`); an inbound sender cannot ask for one, and an outbound dry run would have to POST (and so is not dry). | **Six verbs: `init`, `validate`, `status`, `enable`, `disable`, `key`.** No `test` verb: `validate` compiles offline, `workflow dry-run` rehearses the definition a connector starts, and the operator guide's first-delivery check is a real signed request. `key --output FILE` (root, on the host) writes ONE connector's derived key to a new 0600 file and never to stdout (D1804). | A verb named `test` that performs a real delivery would be a lie in the vocabulary; one that does not would test nothing. | 0236 |
| **D1798** | D1522: delivery *"replayable … with dead-letter visibility"*. | — | **Visible, not replayable, in Stage 4.** `status` lists up to 20 dead letters per connector (`delivery_id`, `event`, `attempts`, `last_error`, `dead_at`). Re-delivering a dead letter is §10's: it is a write to the outbox by a human, which needs its own scope and its own audit story. | The brief's CLI list does not include it; a half-built redelivery is worse than an honest *not built*. | — |
| **D1799** | Stage plan §5: *"Scheduled: a connector of kind `scheduled` with an interval, run by the worker's interval table, invoking one tool."* | No schedule, interval table or cron exists (0 hits; D1515 forbids `pg_cron`). | **`kind: scheduled`, `schedule: {every_seconds: 60..86400}`, `workflow: name@version`, `input: {…literals…}`.** The interval table is the connector row's own `next_fire_at`; `connector_fire_due(p_holder)` enqueues ONE run per enabled scheduled connector whose `next_fire_at <= now()` and sets `next_fire_at = now() + every_seconds` — **missed fires coalesce to one** (a worker that was down fires once, not a backlog). Enabling sets `next_fire_at = now()`; disabling sets it `NULL`. | The substrate already has the only durable clock this product needs (`resume_after`); a coalescing interval is the behaviour that cannot storm after an outage. | 0236 |
| **D1800** | Stage plan §5 Measures: *"an outbound endpoint returning 500 producing exactly `max` attempts with the declared backoff and then a dead letter (control: a 200 producing one)"*. | — | **`retry: {max: 0..10, backoff_seconds: 1..3600}` (fixed backoff, the workflow's shape); attempts = `max + 1`; EVERY non-2xx and every transport failure is retried until then; `dead` after the last.** Error tokens, fixed and never a message: `http_<3-digit code>`, `timeout`, `connect_failed`, `tls_failed`, `dns_failed`, `unknown`. A 2xx is `delivered`. `DELIVERY_TIMEOUT_SECONDS = 10`; the lease is `10 + lease_margin_seconds()`. | A 4xx that "cannot succeed" often does after the receiver is fixed; retrying a bounded number of times costs little, and the brief's own control is a 500. Fixed backoff matches the workflow retry and the brief's word *declared*. | 0238 |
| **D1801** | D1525: *"34 `delivery-retry-storm` (an unreachable endpoint produces bounded retries and a visible dead letter, never a hot loop)"*. | Ten scenarios (`rehearsal.py:81-100`); `worker-restart` is the sibling (`:886-976`). A rehearsal may not depend on an operator's endpoint being down. | **`delivery-retry-storm`**: requires the facility and one installed outbound connector (else refused before anything, `refuse_without_a_reading`'s shape); induces ONE delivery through `app_private.connector_rehearse_delivery(p_connector)` (granted to nobody; run as `postgres` through `container_exec.run`) flagged `rehearsal = true`, `max_attempts 3`, `backoff_seconds 2`, **which the worker sends to `http://127.0.0.1:9/` instead of the endpoint** (connection refused inside `auth`, measured in rig 34b); observes exactly 3 attempts at ≥ 2 s spacing, status `dead`, `last_error connect_failed`, and the worker heartbeat moving throughout; reverses nothing (the dead row is the record, counted); verifies the doctor's `workflow` check is `ok`. `BOUNDS["delivery-retry-storm"] = 60`. | The discard port inside the container is the one unreachable endpoint every deployment has; the rehearsal measures the product's retry discipline, not a receiver. | 0238 |
| **D1802** | D1529: *"Session 34 the same [restore-test row] for an undelivered event"*. | The drill's `workflow_runs` member nests `approvals` (`restore-test.py:514-538`); `REC-WF-001`'s proof compares a live count at a target with the drill's (`test_session32_workflow_restore.py:76-141`). | **The member nests `deliveries` by status** (`jsonb_object_agg(status, total)` over `app_private.connector_delivery`), absent with a reason naming migration 0036 when the function or table is missing; a new live proof `tests/recovery/test_session34_delivery_restore.py` (REC-EVT-001) asserts the drill's `pending + dead` equals the live count at the target. | The same claim Session 32 made for runs, for the one new durable state a restore must carry. | — |
| **D1803** | Stage plan §8: *"a report may not substitute an answer … `connector status`"*. | The doctor has twelve checks; the twelfth, `workflow`, reads `workflow_counts()` with no threshold (`diagnosis.py:583-678`). | **Still twelve checks.** `workflow_counts` (replaced in 0036, same signature) adds `deliveries_pending`, `deliveries_dead`, `oldest_pending_delivery_age_seconds`, `connectors_enabled`; the `workflow` line gains *"deliveries pending N (oldest Ns), dead N; connectors enabled N"* or *"deliveries not read (the substrate predates 1.12.0)"* — never zero for *unread* (ADR 0195). No threshold (ADR 0213). | A delivery is the worker's work; a thirteenth check would move a count in every sheet and page for a line the twelfth can carry. | 0238 |
| **D1804** | Stage plan §8: *"A workstation holds no production secret … A connector's shared secret is materialised on the host, never in the file"*; §10: *"Session 34 owns saying so in the operator guide"*. | `bootstrap-providers.sh` prints no value and takes no credential argument (its own help). `test_cli_contract.py:1069-1082` refuses a `--token\|--secret\|--password\|--api-key` flag. | **`sudo bin/connector.sh key --project FILE --name N --output FILE`** derives the ONE connector's key from the active generation's master (path derived from `active-secret-generation.json`, never typed) and writes it to a NEW file, mode 0600, owner root, refusing an existing path; the operator hands it to the sender out of band. Operator guide §18 states: the key has an outside holder; rotating it is replacing `APG_CONNECTOR_SIGNING_KEY` at the provider and redeploying, **which changes EVERY connector's key of that project at once**; the other three rotations Session 30 did not perform are unchanged. | A value an outside party must hold has to be handed over somehow; a root-only file is the tree's existing shape for a credential (`--operator-credential-file`), and stdout is where a secret ends up in a transcript. | 0237 |
| **D1805** | CLAUDE.md §9: *"`test_a_live_tunnel_is_reported_live` races fork against exec (D1777) … Owed: wait until `ps -o args=` reads `sleep 300`, in a run with a battery."* | `tests/contract/test_connect_command.py`'s `sleeper` fixture is `Popen(["sleep","300"])` read at once by `process_identity`; CI failed once on `24d0e13`. | **Run 2 repairs the FIXTURE** (poll `ps -o args= -p <pid>` until it reads `sleep 300`, bounded 5 s, failing with the last reading) with a battery: the mutation that removes the wait must be killed *by making the race observable* (a `PATH` shim `sleep` that sleeps 0.2 s before `exec`), control: the product unchanged. | A known flake in CI is a verdict nobody can read (D1057's cousin); it is small and the session touches the neighbourhood. | — |
| **D1806** | CLAUDE.md §9 / §26: D1775 (an undecided approval stays `pending` when its run ends), D1700 (probe identities), D1721 (approval is a plane control only), D1722 (no dry-run branch in `set_note_embedding`), D1547 (`delete_note`), D1642 (a kit names the checkout). | Each is still true (§26's left table). 0036 replaces `set_note_embedding` (D1781), which is where D1722's missing branch lives. | **None is taken here, and each is re-stated in §10 with this session's reading.** D1722 specifically: 0003 keeps the body BYTE-IDENTICAL apart from the emit line, so a dry run through the plane still cannot reach it (the approval gate refuses first, and an approved claim refuses `dry_run`, ADR 0231) — and the new emit inherits the same belts: **an event can only be emitted by a committed `set_note_embedding`**. A project function honouring `Dry-Run` needs a release helper the lint allows; §10 prices it (`app.request_is_dry_run()`). | **The operator decided on 2026-09-29, after reading this plan, that D1721's database half is Session 35's**, not 34's (Session 33's §10 left the choice open); this session builds nothing toward it. Scope in §1, not in Run 6 (the user's standing request). | — |
| **D1807** | Stage plan §5: *"Ends on a host"*; the deploy, the sweep and the tag on one commit (D1425). | `build_plan` BLOCKS when an operator digest moved (`upgrade_plan.py:337-351`: *"deploy the manifest change as its own operation"*); step 0 refuses a project whose provider lacks a required generated secret and names `bootstrap-providers.sh --apply` (`deploy-project.py:783-820`). | **The trip deploys the release to alpha and to beta with their manifests UNCHANGED (upgrade plan `minor`, OK), and THEN, as its own operation, enables beta's facility**: the agent edits `project.beta.yaml` as `op` with a backup (schema 7, `connectors.enabled: true`, two endpoints), the operator runs `bootstrap-providers.sh --apply` for beta (creates `APG_CONNECTOR_SIGNING_KEY`), then redeploys beta (step 6e installs four connectors; auth recreated with the new mount). Alpha never gains the facility — it is the control (the route answers 404; nothing is owed). One sheet per outcome (D1510). | The product's own rule about operator inputs, followed rather than routed around; and the second beta deploy is `deployment_convergence`'s redeploy, declared. | — |
| **D1808** | — | `apg dev up` installs the example set's definitions (`bin/dev.py:445-460`, `:467-518`) and a proof pins `workflows   4 definition(s) installed` (`test_dev_environment_cluster.py:186-249`). The example manifests are schema 6 with no facility. | **`apg dev up` installs the set's connectors ONLY when the manifest enables the facility** (the example manifests do not, so it prints `connectors  not enabled (the manifest's connectors.enabled is false)`), and installs the three new definitions — the pinned line becomes `workflows   7 definition(s) installed` (a stricter equality at a new number, not a loosening). A contract proof covers the enabled path with a throwaway schema-7 manifest in `tmp_path`. | The dev loop is the database alone (ADR 0203); a facility nobody enabled installs nothing, and says so. | — |
| **D1809** | Stage plan §5: *"one outbound delivery to a sink and one dead-lettered"*. | No sink exists; auth's `internal` network has no egress; a URL committed in the set would be every deployment's (D1786). | **Beta's endpoints point at a sink the live proof RUNS**: `http://apg-s34-sink:8080/ok` and `http://apg-s34-sink:8080/fail`. The module fixture `sink` starts, as root, `docker run -d --rm --name apg-s34-sink-<SWEEP> --network <beta's compose.networks.internal> --network-alias apg-s34-sink <auth image digest> python3 -c <a 40-line server>` (the auth image already carries Python; no image is pulled), which answers `/ok` 200 and `/fail` 500 and prints one JSON line per request (method, path, the three `X-Apg-*` headers, the body) to stdout; the proof reads `docker logs`. **Every connector is installed DISABLED and the module enables each around its proofs and disables it in `finally`**, so outside the sweep's window no event is recorded and nothing is sent. | A sink under the proof's control is the only way to assert *exactly N attempts* and to verify the signature independently; the auth image is already on the host and pinned by digest. | 0238 |
| **D1810** | Stage plan §7: *"34 | new `EVT-*` / `CONN-*` claims (schema validation offline; the inbound refusal and delivery live)"*. | ID families at `test_acceptance_registry.py:98` do not include either. | **Two new families, `EVT` (the emitter, the lint rule, the event wait) and `CONN` (the connector file, the facility, delivery, inbound, binding, schedule, the command, the rehearsal)**, plus one `REC` id; the paragraph above `ID_PATTERN` gains a Session 34 sentence. Sixteen requirements, sixteen claims (§2). | The stage plan proposed them; an event is not a connector (a wait consumes one with no connector at all). | — |
| **D1811** | Stage plan §2.2: *"Session 34 adds a route (a deployed-document field, migratable)"*. | The route needs no document field (D1788); the FACILITY does (D1785); the secret is facility-gated (D1784). | **`template_version` 1.12.0, minor, by declaration**: Run 9 reads `upgrade plan` with `--also migration_added --also api_operation_added --also document_schema_migratable` and expects `bump minor`, `requires minor`, verdict OK, and **no `secret_required_added`** on the example renders; without the flags it expects `requires patch`. Every differing leaf is listed in the Done; the predicted ones are `template_version`, `migrations.release_lock_sha256`, `inputs.secrets_contract_sha256`, `schema_version` and the new `connectors` member. A `major` is §9's stop. | The third release in a row whose price the command cannot fully see (D1561, D1703); declaring is the mechanism built for it. | 0162 |

**Rows the runs added, in execution order** (the executor appends here; six
columns: `# | Run | Plan says | Tree does / measured | Decision | ADR`):

| # | Run | Plan says | Tree does / measured | Decision | ADR |
|---|---|---|---|---|---|
| **D1812** | 1 | D1791 / rig 34b: *"`urllib`'s default opener follows redirects"*; *"the DEFAULT `urllib` opener → record whether it re-POSTs (and to where)"*. | **Rig 34b, inside the auth image built from this checkout** (`sha256:4a7a337e…`), a POST with a JSON body: the default opener follows **301, 302 and 303 as a GET with NO body** to the `Location` and returns the Location's **200 as the response**; it **refuses 307 and 308** with `HTTPError(307/308)` and never follows them. It never re-POSTs the body. **The follow-up (`bis.py`) measured that the followed GET still carries `X-Apg-Signature`** (custom headers survive; only `Content-Type` is dropped). The refusing opener (`redirect_request` → `None`) surfaces all five as `HTTPError(<code>)`. | **The refusing handler stays, for a sharper reason than the plan gave**: the default opener would record a 301/302/303 as *delivered* (a 200 from an address nobody declared) after sending the signature header there. A 3xx is `http_3xx` and is retried like any non-2xx. Run 6's proof uses a 302 (the case the default FOLLOWS), not only a 307, so the mutation that drops the handler is killed. | 0238 |
| **D1813** | 1 | D1800: error tokens `timeout`, `connect_failed`, `tls_failed`, `dns_failed` mapped *"from MEASURED exception types"*. | **Rig 34b + `bis.py`**: refused → `URLError(.reason=ConnectionRefusedError, errno 111)`; connect timeout → `URLError(.reason=TimeoutError)`; unresolvable → `URLError(.reason=socket.gaierror, errno -2)` (-5 on a network with no resolver entry, 34d's control); self-signed → `URLError(.reason=ssl.SSLCertVerificationError ⊂ ssl.SSLError ⊂ OSError, ValueError)`; **a READ timeout (the server accepts, never answers) → a BARE `TimeoutError`, not a `URLError`** (2.0 s at `timeout=2`). | **The classifier reads `.reason` when the exception is a `URLError` that is not an `HTTPError`, and the exception itself otherwise**, in this order: `HTTPError` → `http_<code>`; `ssl.SSLError` → `tls_failed`; `TimeoutError` → `timeout`; `socket.gaierror` → `dns_failed`; `ConnectionError` → `connect_failed`; anything else → `unknown`. `ssl.SSLError` is checked before the `OSError` family because it IS one. Run 6's proof drives each of the five cases, the bare read timeout included. | 0238 |
| **D1814** | 1 | §2 EVT-EMIT-001: *"a request role and `auth_service` are refused `42501`"*. | **Rig 34a**: `authenticated`, `agent_writer`, `auth_service` and `anon` each get **`42501 permission denied for schema app`** — the SCHEMA's refusal (none holds `USAGE` on `app`) — and `has_function_privilege(role, 'app.emit_event(text,integer,jsonb)', 'EXECUTE')` is **false** for all four. PostgREST answers `POST /rpc/emit_event` **404 `PGRST202`** for a human and an agent token (control `POST /rpc/create_note` 200). Through a definer RPC the row carries the GUC's owner; through PostgREST with an agent token it carries the agent's owner AND the agent's id. A rolled-back caller left 3 rows at 3. | **The prediction holds, and the proof must measure the function's grant, not only the schema's**: a proof asserting only `42501` passes vacuously while `app` stays closed, and would still pass if 0036 granted the function to PUBLIC. `test_emit_event_is_executable_by_no_role` asserts `has_function_privilege` false for every login and request role AND the `42501`. | 0235 |
| **D1815** | 1 | D1780: the hole is *"`CREATE OR REPLACE FUNCTION api.create_note(...)`"* and *"the same hole would let a project replace `app.emit_event`"*. | **Rig 34a, `lint_project_set` over a scratch set**: PASSED `CREATE OR REPLACE FUNCTION api.create_note(…)`, `CREATE OR REPLACE FUNCTION app.emit_event(…)`, `ALTER FUNCTION api.create_note(text, text) SECURITY INVOKER`, and **`CREATE OR REPLACE FUNCTION app.current_user_id()` — the function every row policy in `app` reads**. Applied as the owner, `api.create_note`'s `pg_get_functiondef` md5 moved `c0cdcc57…` → `0d4f9729…`. Controls: a body naming `app_private` refused; `DROP FUNCTION api.create_note` refused; a project RPC calling `app.emit_event` passed. | **The hole is wider than the row named and its worst member is `app.current_user_id()`** (a project could make every policy answer for any owner). Run 2's rule is as planned — `CREATE [OR REPLACE]`, `ALTER` or `DROP` of any FUNCTION the release creates in `api` or `app` — and its proofs include the `ALTER` case and `app.current_user_id()` by name, beside the two the plan lists. The names are derived from the release templates; **if `sql_surface` derives only `api` names today, Run 2 widens the derivation to `app`, and the proof `test_the_release_function_names_are_derived_from_the_templates` asserts `current_user_id` is among them.** | 0235 |
| **D1816** | 1 | §5 Run 1: the three `THR-*` rows cite `CONN-IN-001`, `CONN-IN-002`, `CONN-ADMIN-001`, `CONN-OUT-001`, `CONN-OUT-002`, `CONN-STORM-001` and proposed node ids. | `test_acceptance_registry.py::test_threat_model_requirement_ids_exist_in_the_registry` and `::test_threat_model_node_ids_are_collectible` read EVERY threat row; none of those requirements exists until Run 9 lands the registry (D690), and none of the node ids collects — D1742's shape exactly. | **The rows land in Run 1 with the prevention, detection and residual cells whole and cite what holds TODAY**: `THR-CONNECTOR-INPUT` → `API-AUTH-002` (the strict input the route reuses after the signature) + `test_auth_strict_json.py::test_an_oversized_body_is_refused_before_it_is_parsed` + `test_auth_service_shape.py::test_the_application_serves_exactly_the_declared_paths` (no connector path is served yet); `THR-WEBHOOK-REPLAY` → `AGT-IDEM-001` + `test_agent_audit_plane.py::test_a_replayed_write_performs_the_work_once_and_returns_the_same_row` + the path equality; `THR-DELIVERY` → `WF-WORK-001` + `test_auth_service_shape.py::test_every_transport_in_the_service_is_declared_with_a_reason` + `test_workflow_worker.py::test_the_loop_starts_in_auth_mode_only`. Each residual cell says so. **Run 9 rewrites the two ID cells of all three rows** with the §2 requirements and their collected node ids. | — |
| **D1817** | 2 | §5 Run 2 battery: *"a `PATH` shim `sleep` that sleeps 0.2 s before `exec`"* makes the race observable. | **With a 0.2 s shim the mutation (the wait removed) SURVIVED**: the whole proof ran in 0.10 s, so the record AND `connect.sh status` both read the pre-exec args (`/bin/bash …/sleep 300`) and agreed. CI's failure is the other ordering — the `exec` lands BETWEEN the recorded read and `status`. A **0.03 s** shim (`exec -a sleep /usr/bin/sleep "$@"`, so the post-exec args read exactly `sleep 300`) reproduces it: the mutation FAILED on the stale-record assertion, the fixed fixture PASSED under the same shim. | **The battery's shim window is 0.03 s**, and the instrument's first result is recorded rather than tuned away: a race is observable only when the window falls between the two reads the proof compares, not merely when it is long. | — |
| **D1818** | 2 | §5 Run 2 step 2: *"a function `release_functions(release_templates_dir)`"*; the rule's regex `(CREATE(\s+OR\s+REPLACE)?\|ALTER\|DROP)\s+FUNCTION\s+(api\|app)\.<name>\b`; *"Every reader of `lint_project_set` … passes the release directory it already has"*. | `lint_project_set(project, release: MigrationSet \| None = None)` ALREADY takes the release as a `MigrationSet` (`release_set()` by default), and its three callers (`rendering.py:2448`, `bin/migrate.py:416`, `:442`) pass none — the default is the one they want. PostgreSQL also accepts `PROCEDURE`/`ROUTINE`, `IF EXISTS`, a quoted or spaced schema and name, an argument-less name, and an UNQUALIFIED name after a `search_path` move — each a spelling the planned regex would not see. | **`release_functions(release: MigrationSet)`** derives from the set the lint already holds (manifest order: `CREATE` adds, `DROP` removes; the exact set is the plan's eight). No caller changed. **`FUNCTION_DDL` matches every one of those spellings, and an unqualified definition of a release function's NAME is refused too**; proofs are arms of `test_a_project_set_may_not_replace_a_release_function` (quoted-and-spaced, `ALTER ROUTINE` without arguments, unqualified). The DROP half of the old rule is folded in with its message kept (`drops api.<name>`), so the existing `drops_a_release_function` arm passes unchanged. | 0235 |
| **D1819** | 3 | §5 Run 3 item 12: *"`connector_fire_due(p_holder text) RETURNS integer`"*. | Nothing in the function records a holder: no column, no attempt row, no heartbeat (the heartbeat is `workflow_heartbeat`'s, written by the loop anyway). A parameter nothing reads is a declared field with no reader — the D816 class. | **`app_private.connector_fire_due()` takes no argument**; `ConnectorRepository.fire_due()` calls it bare; Run 6's loop calls it once per iteration. | 0236 |
| **D1820** | 3 | §5 Run 3 *Read first*: *"ADR 0175's arity guard over `api` and `app_private` — decide whether it must learn `app`, and if it must, that is a stricter guard, stated"*. | `test_database_function_signatures.py:61` `SCHEMAS = ("app_private", "api")`. 0036 puts `app.emit_event` in `app`, and the project RPC, the proofs and 0003 all reach it as `app.emit_event(name, version, payload)`; a wrong-arity call would fail only inside a cluster. | **The guard learns `app`** — `SCHEMAS = ("app_private", "api", "app")` (`app_private` first so the alternation never reads it as `app`) and a third witness `("app", "emit_event")` beside the two that keep the schema list from shrinking silently (D887). Stricter; every call in the tree passes it. | 0235 |
| **D1821** | 3 | §5 Run 3 item 9: `connector_install` with thirteen parameters, laid out like 0034/0035's aligned declarations. | **Measured on first run**: `test_every_sql_signature_names_a_declaration_that_is_live_at_that_point` reported both `connector_install(...)` references (the `COMMENT` and the `REVOKE`) as naming *"no declaration"*. `_arguments` reads an argument list within **400 characters** of its paren (D1450's bound against runaway parses), and the column-aligned thirteen-parameter list was longer, so the walk skipped the DECLARATION and then called every reference stale. | **The declaration is written unaligned**, four lines, with a comment saying why; the bound is not widened (it exists for D1450's reason, and every other declaration fits). A function with a longer parameter list than this would meet the same wall — the comment in 0036 names the bound so the next one is not a surprise. | — |
| **D1822** | 3 | §5 Run 3 items 2, 3, 8, 9, 10, 16. | Four places where the plan's sketch was silent or looser than the tree allows: (1) `workflow_run.owner_id` exists (0034:196-210) and is COPIED from the agent at enqueue (0034:443) — the owner a wait belongs to is on the run itself; (2) a higher-version install that changes the connector's EVENT or its definition's REQUIRED SCOPES changes what the bound agent was bound to, as a changed kind or definition does; (3) a delivery whose lease expires on its LAST attempt is excluded by `attempts < max_attempts` and would stay `pending` forever; (4) the rehearsal's event has no owner, and `connector_event.owner_id NOT NULL` would force a nil uuid that looks measured (D600). | (1) **The emitter matches `r.owner_id = caller`** — the same owner, without a join through `agents`. (2) **`connector_install` returns `replaced_disabled` (disabled, unbound) when the kind, event, definition name or version, or required scopes change.** (3) **The claim first retires such a delivery as `dead`** (`last_error` kept, else `unknown`) before it leases anything. (4) **`owner_id` is nullable with `CHECK (owner_id IS NOT NULL OR name = 'apg.rehearsal')`.** `connector_status` also carries `endpoint_declared` (a boolean, never the value), `enabled_by/at`, `disabled_by/at`, and binding values `not_applicable` (outbound) and `agent_not_active` beside the plan's three. | 0236, 0238 |
| **D1823** | 3 | §5 Run 3 battery: *"make `connector_accept` insert the receipt AFTER the enqueue without the single transaction"*. | A plpgsql function body IS one transaction; there is no way to write "not one transaction" inside it. The failure the mutation stands for is a refused enqueue that leaves a receipt behind. | **The mutation is written as the expressible form of that failure**: the enqueue wrapped in `BEGIN … EXCEPTION WHEN OTHERS THEN RETURN NULL; END`, which keeps the receipt and swallows the refusal. `test_a_refused_enqueue_leaves_no_receipt` must FAIL on it. | — |
| **D1824** | 4 | D1808: *"The example manifests are schema 6 with no facility"*; §5 Run 4 item 1 widens the schema to 7 and says nothing of the fixtures. | `tests/contract/test_project_manifest.py::test_example_manifest_is_valid` asserts both example manifests are at `max(SUPPORTED_PROJECT_SCHEMA_VERSIONS)` (ADR 0183: the shipped fixtures exercise the newest shape, D927's lesson). | **`project.example.yaml` and `project.second.example.yaml` move to schema 7, both WITHOUT `connectors`** (the facility off — the measurement that keeps the release minor), each with a comment saying so; `downgrade_to_five` and `downgrade_to_two` in `test_project_manifest.py` pop `connectors`. Both renders are re-rendered; no document carries the facility. | 0237 |
| **D1825** | 4 | D1784: *"A new `required: true` secret moves every rendered document's `secrets.required_names` and is auto-classified `secret_required_added` → major"*; §2 CONN-FAC-001: *"its rendered `required_names` is unchanged"*; D1811: *"no `secret_required_added` on the example renders"*. | **`rendering.RENDER_SESSION = 2`** (`rendering.py:51`): the rendered `secrets.required_names` is computed from `active_secrets(contract, RENDER_SESSION, …)`, so it lists ONLY secrets introduced by Session 2 — no secret declared since (metrics, the prepared key, the mirror's, this one) can ever appear there, gated or not. The premise that a required secret would move it is FALSE; `upgrade plan`'s auto-classification cannot see ANY post-Session-2 secret. Where the requirement actually bites is deploy step 0 (`_secrets_the_provider_is_missing(state, through_session, enabled_facilities(rendered))`, `deploy-project.py:754-780`), the bootstrap and the materializer/override. | **The facility gating stays — for the reason that holds**: without it, every deploy `--through-session 34` (alpha's included) would demand `bootstrap-providers --apply` at step 0 and materialize a key nothing reads. The proofs measure the project's view where it bites — step 0's selection at session 34 with and without the facility, and the secret override's mounts — plus the rendered `required_names` for both examples. Run 9's *"no `secret_required_added`"* will hold, and its Done must say it holds because `RENDER_SESSION` is 2, not because of the gate. **§10 gains the blind spot**: `upgrade plan` cannot price a secret added after Session 2. | 0237, 0162 |
| **D1826** | 4 | §5 Run 4 item 3: append the secret to `secrets.required.yaml`. | `schemas/secret-contract.schema.json` caps `introduced_in_session` at **18** — *"it tracks the newest declaration, not CURRENT_SESSION"* — so `introduced_in_session: 34` failed the contract's own validation and took 35 `test_secret_contract` proofs to `ERROR` at setup. | **The cap moves to 34** with a sentence in the description, the schema's own rule; the facility enum gains `connectors` at the secret level (the consumer-level enum is unmoved — no consumer of another secret is gated by it). | 0237 |
| **D1827** | 4 | §5 Run 4 item 4: *"`connector_key_file: Path \| None` from `APG_CONNECTOR_KEY_FILE` (OPTIONAL — absent on a deployment without the facility)"*. | `test_auth_service_shape.py::test_the_auth_mode_reads_no_new_variable` (WF-WORK-001) asserts the compose auth environment EQUALS `REQUIRED_VARIABLES ∪ {APP_MODE}`; an optional variable set in `compose.yaml` would break the equality, and one set only by an override would be a setting no document declares. The secret override mounts each secret per FILE, and a facility-gated secret only for a project with the facility (**item 4's measurement**: rendered with the facility on, `connector_signing_key` is mounted into `auth` and no other service; off, nowhere — `test_a_project_with_the_facility_requires_the_key`). | **The PATH is required, the FILE is optional**: `APG_CONNECTOR_KEY_FILE` joins `REQUIRED_VARIABLES`, `compose.yaml` sets it to `/run/secrets/connector_signing_key` for every project, `Settings.connector_key_file` is that path in auth mode, and the file's absence is how the service reads *no connectors* (the route's step (2), 404; no delivery pass). Storage refuses the variable; `FORBIDDEN_VARIABLES["mcp"]` gains it. | 0237 |
| **D1828** | 4 | §5 Run 4 item 5: `src/agentic_postgres/connector_keys.py` in Run 4 and `test_the_two_key_derivations_agree`. | `test_repository_contract.py::test_no_module_is_imported_only_by_its_own_tests` (D204) refused it: *"a module with no caller is a feature that does not exist"* — its one caller, `bin/connector.py key`, is Run 7's. | **The host copy ships in Run 7 with its caller**, and the two-copy agreement proof with it. Run 4 proves the image's derivation against an HMAC the test writes itself on ten vectors (`test_the_key_derivation_matches_an_independent_hmac`) and `sign` against rig 34b's openssl-measured vector; the battery's label mutation is killed there. | 0237 |
| **D1829** | 4 | — | Moving outputs to 19 made three pins of the version name the wrong one: `test_the_chain_ends_at_version_18_with_nothing_of_a_projects_own` (registered, `acceptance-registry.yaml:2886`), `test_a_current_version_document_is_not_migrated_again` (`already version 18`), and `test_v17_to_v18_…`'s schema validation (the current schema is 19's). | **Renamed to `…_at_version_19_…` with its registry node id moved in the same commit** (D1757's precedent; a name saying 18 over an assertion of 19 is a proof that reads as measuring what it does not); the no-op pin reads 19; the v17→v18 proof validates its output after the last step. A `v18` fixture is derived from the chain (`v17` now derives from it), and the v18→v19 step gets its four proofs. `docs/acceptance-matrix.md` regenerated. | — |
| **D1830** | 4 | §5 Run 4's targeted list (grep-derived). | **CI RED on `5005c37`** (`contract`, run 36623650516), seven modules the list did not name — D1486's class again, a targeted list derived from a diff cannot see a reader the diff does not touch: `test_auth_endpoints` (176 setup errors) and `test_studio_runtime` (34) build the AUTH environment by hand and lacked the now-required `APG_CONNECTOR_KEY_FILE` (D1827's variable, missed in its fixtures); and five guards each asking for a deliberate extension — `test_backup_mirror` (the facility-bound set and `FACILITIES`), `test_bootstrap_state` (the bootstrap may record only what its enum names), `test_disaster_kit` (`_previous_version` moves with the outputs version), `test_doctor_redaction` (every schema block classified), `test_project_agent_surface` (the fixtures "at six"). | **Repaired at the next commit**: both builders set the path to a file that does not exist (the facility off, which every proof there is); the facility-bound set gains `connector_signing_key` and `FACILITIES` both names; `bootstrap-state.schema.json` gains `connector_signing_key` with a sentence (generated, so destroyable, and what destroying it costs); the kit helper subtracts `connectors` at 19; `connectors` is a PRINTABLE block (one boolean); the fixture proof is renamed `…_are_at_the_newest_version_and_one_names_capabilities` (unregistered; its old name was untrue) and asserts `max(SUPPORTED) == 7`. The seven modules re-run alone: **258 + 42 passed**. The production DR-kit reader needed nothing: `verify_deployed_document` is version-generic (D1141). | — |
| **D1831** | 5 | §5 Run 5 item 4: `connectors/notes-inbox.yaml`'s body *"`content: {type: string, required: false, max_length: 4000}`"*; item 2: *"an inbound body declaring a member the definition's steps never reference … refused"* (both directions). | The worker fails a step whose run input lacks a referenced key (`workflow_worker.resolve` → `input_unresolved`, `services/auth-api/app/workflow_worker.py:248`), and item 2 makes every declared member a referenced one. So an OPTIONAL member is one a request may omit and the run then fails on its first step -- after the route answered 202. | **The compiler refuses a body member declared `required: false`** (every member is read, and the worker has no default to resolve an absent key to), naming D1831; the schema keeps `required` as ADR 0237 states it, and the service validator honours it, so a future worker with defaults has nothing to migrate. The example's `content` is `required: true`. A scheduled `input` is checked in BOTH directions too (missing AND unread keys), the body's rule, where the plan said only *"covers"*. | 0237 |
| **D1832** | 5 | §5 Run 5 item 4: `notes-await-embedding.yaml` -- *"`create` (`create_note@1.0.0` from `{{input.title}}`), `embedded` (`wait: {event: note_embedding.set@1, match: {note_id: "{{steps.create.row.id}}"}, seconds: 300}`)"*. | **`{{steps.create.row.id}}` is not a reference.** The grammar reaches ONE field of a step's result (`REFERENCE`, `workflow_definition.py:77`, the worker's the same), so the compiler refuses the trailing `.id` as a typo (D1679). A write step records `{row: {...}}` (D1724, rig 33c), so `{{steps.create.row}}` is the whole row -- which a `{note_id}` payload never contains. | **The definition waits on `{{input.note_id}}`**: `embedded` (the event wait) first, then `record` (`create_note@1.0.0`, a note saying it arrived). The host proof creates the note, starts the run with its id, then writes the embedding -- EVT-WAIT-002's *"a run waiting … for its own note"* is unchanged. Widening the grammar would move the worker's resolver and D1724's contract for one example. | 0239 |
| **D1833** | 5 | §5 Run 5 item 4: *"`bin/migrate.sh freeze-lock --project project.example.yaml`"*; *"name the version `0003` took and the rule that decided it"*. | **Measured: the freeze exits 5.** Without `--follows` it records this checkout's newest release version, `20260929120036` (0036), and the set's `20260914120001`/`…002` sort below it. `test_project_migration_sets.py::test_the_project_lock_is_frozen_and_verified_apart_from_the_release_lock` pinned the committed record as `computed`. | **Frozen with `--follows 20260912120031`** -- the value the set's last computed freeze recorded -- so the lock says `declared` (ADR 0210's remedy, the refusal's own advice); the proof is replaced by a stricter one: `declared`, the exact value, AND the release's newest above the set's oldest (the condition that makes the declaration necessary). **`0003` is `20260930120003`**: after the set's own newest (ADR 0206, the only ordering a set has), in its `YYYYMMDD12000N` convention; nothing orders it against 0036 and nothing needs to -- a PL/pgSQL body resolves `app.emit_event` when it runs. | **0240** |
| **D1834** | 5 | §5 Run 5 item 7: *"`test_project_migration_sets.py::test_the_example_sets_third_migration_keeps_the_signature` (… `CREATE OR REPLACE` keeps `has_function_privilege` for `authenticated` and `agent_writer` -- under the cluster fixture)"*. | `test_project_migration_sets.py` has no cluster fixture; the one cluster that applies the example set is the one `apg dev up` builds (`test_dev_environment_cluster.py`'s `environment`). | **Two proofs**: `test_the_example_sets_third_migration_keeps_the_signature` (offline: the lint passes, the function is 0001's byte for byte but `OR REPLACE` and the one emit directly after the upsert, the payload carries no vector, `object_owner` alone, no GRANT restated) and `test_dev_environment_cluster.py::test_the_example_sets_third_migration_kept_its_grants` (EXECUTE held by `authenticated`, `agent_writer`, `api_documentation`, not `anon` -- the control; 0001's comment kept; the running body emits; the project ledger ends at `20260930120003`), through the product's own command (D1114). Run 9 registers both under EVT-LINT-001. | — |
| **D1835** | 5 | §2: *"The registry entries cannot be committed before Run 9"*; *"WF-DEF-002 … leaves its node ids"* (listed as Run 9's). | Deleting `test_a_wait_on_an_event_is_refused_naming_session_thirty_four` in Run 5 (ADR 0239) leaves a registry node id with no test, which `test_acceptance_registry` refuses; and three proofs pinned the example set's COUNTS -- two by name (`…two_migrations_in_order`, `…four_definitions_compile`) and one by a `notes-` prefix filter that the new `notes-*` definitions entered. | **Moved in Run 5, not Run 9**: WF-DEF-002 loses the deleted node id and its sentence becomes *"since Session 34 a wait may name an event (EVT-WAIT-001, ADR 0239)"*; the two count-named proofs are renamed (`test_the_example_lock_records_its_migrations_in_order`, 3 versions; `test_the_example_projects_seven_definitions_compile`, 7 files) with their node ids moved in AGT-TENANT-002, WF-DEF-001 and WF-DEF-002 and WF-DEF-001's *"four since Session 33"* now seven; the byte-for-byte proof names its two files instead of a prefix (same two digests). No NEW entry is committed -- `CURRENT_SESSION` still moves in Run 9 alone (D690). | 0239 |
| **D1836** | 5 | §5 Run 5 item 5: step 6e's three reasons and the missing-endpoint line; §2 CONN-DEF-001's `test_the_init_skeletons_validate`. | The plan names no case for an endpoint in the manifest that belongs to NO outbound connector (a typo, or an endpoint given to an inbound one, which the table's CHECK would refuse at psql); and `init` is `bin/connector.sh`'s verb, which Run 7 writes. | **6e reports each such endpoint** (*"endpoint for <name>: names no outbound connector of this set; installed nowhere"*) and sends it nowhere -- a report, like the missing endpoint (ADR 0195); `connector_install.statements` refuses an endpoint for a non-outbound connector before psql could. **No line prints an endpoint** (proved). `test_the_init_skeletons_validate` moves to Run 7 with `init`. The dev path's enabled arm is a contract proof over a recording `docker` (`test_deploy_connectors.py::test_dev_up_installs_connectors_only_with_the_facility`, a tmp schema-7 manifest), D1808's disabled sentence read off the real `up`. | — |
| **D1837** | 6 | §5 Run 6 item 2: *"absent → `None`, and a single INFO line \"connectors: no key file (the project has not enabled the facility)\""*. | **Rig 34f's control read the auth log for the line and found nothing.** The application configures no logging (no `basicConfig`, `dictConfig` or `setLevel` under `services/auth-api/app/`), so under uvicorn's defaults an `app.*` INFO record reaches no handler -- Python's last-resort handler prints WARNING and above. | The line is written as the plan says and recorded as INVISIBLE, never as a reader of the facility: an operator reads the facility from the deployed document's `connectors.enabled` and from Run 8's doctor line. A WARNING would sound on every start of every project without the facility (alpha) about a state that is correct. | — |
| **D1838** | 6 | §5 Run 6 item 4 (ii): *"exactly 3 POSTs at ≥ 2 s spacing"*; D1801's rehearsal *"3 attempts at ≥ 2 s spacing"*; §2 CONN-OUT-002 *"attempted exactly `max + 1` times at the backoff"*. | **Rig 34f (ii): 3 POSTs 5.06 s and 5.09 s apart with `backoff_seconds: 2`.** A delivery is claimable once its backoff passes, but an iteration that found nothing sleeps `POLL_SECONDS` (5) -- the loop sleeps only then (D1790) -- so on an idle deployment the spacing is `max(backoff, POLL_SECONDS)`. | Correct, and now measured: bounded below by the backoff, never hot. **Run 8's rehearsal and Run 9's host proof assert spacing `≥ backoff` and exactly `max + 1` attempts, never a spacing near the backoff**, and their time bounds allow `(max + 1) × POLL_SECONDS` plus one poll. | 0238 |
| **D1839** | 7 | §5 Run 7 item 7: *"parse the body before the signature (the no-call proof FAILS — the fake raises)"*. | Parsing makes no repository call, and every bad-signature case the proofs were written with carried a VALID body -- so a route that parsed first changed neither a status nor a call. **Measured: with the new arm removed, M1 PASSED both `test_every_signature_failure_is_one_fixed_document` and `test_no_database_call_precedes_the_signature`.** | The case table both proofs iterate gains `unsigned_non_json` -- a non-JSON body under a wrong key -- which a route that parsed first answers 400, telling a prober its body was read. With it, M1 is killed by both. | 0237 |
| **D1840** | 7 | §5 Run 7 item 3: *"`agent_not_active`, `agent_already_bound`, `agent_scopes_differ`, `no_endpoint`, `agent_not_needed`, `agent_required` 409"*; item 2: *"`PT403 scope_not_held` → 409 `agent_scopes_differ`"*. | `connector_enable` (0036) raises no `agent_required`: an inbound or scheduled connector enabled with a NULL agent finds no agent row and raises `agent_not_active`. `agent_not_needed` is `PT422`, not `PT409`. `connector_accept` reaches `workflow_enqueue`, whose `PT403` carries TWO words (0034: `scope_not_held`, and *"this operation requires an active agent identity"*), and `connector_scopes_match` reads scopes, not status -- so a revoked agent whose scopes still equal reaches the second. | The routes answer the functions' words: no `agent_required` (a missing agent is `agent_not_active`, and the 409's description says so); **`agent_not_needed` is a 422**, the function's own class -- input an outbound connector cannot take; the inbound route maps `PT403 scope_not_held` → 409 `agent_scopes_differ` and any other `PT403` → 409 `agent_not_active`, the status document's word for that binding. An unrecognised error is re-raised, never reported as a refusal (proved). | 0236 |
| **D1841** | 7 | §5 Run 7 item 6: *"`test_auth_service_shape.py::test_the_application_serves_exactly_the_declared_paths` (unchanged text, new set)"*. | A second pin in the same module, `test_the_admin_surface_is_reachable_only_under_admin`, requires every published path under THREE prefixes (`/auth/`, `/admin/`, `/workflows/`) and failed on `/connectors/{name}` in the targeted run. | Widened to the measured set -- FOUR prefixes -- and made stricter in the same edit: `/connectors/` admits exactly `["/connectors/{name}"]`, so a second path under it fails (CLAUDE.md §6: widening to a measured set is not weakening). | 0237 |
| **D1842** | 7 | §5 Run 7 item 1: *"regenerate every committed lock the tests compare (`bin/mcp-contract.sh lock` / `check`)"*; items 2-5 name no further refusal. | No committed file carries the administrative vocabulary (`admin_audit:read` is in no committed lock; Session 33's `admin_workflows:approve` commit regenerated none). **`bin/mcp-contract.sh check` and `check --project project.example.yaml` exit 0 after the enums moved.** The route and the command needed four decisions the plan does not name. | No lock regenerated -- `check` is the evidence. Decided: `X-Apg-Delivery` must be a CANONICAL lowercase uuid (it is inside the signed bytes as sent and the receipt's key as parsed; two spellings would be two signatures over one receipt), any other form being the 401; the 401 carries `WWW-Authenticate: APG-Signature` (RFC 9110) and nothing about why; `disable` refuses a non-empty body (400) rather than ignoring it; `key` refuses before asking for root when the manifest does not enable the facility or the set does not declare the name (exit 5), and `connector_keys.master_path` re-roots the contract's path at a module attribute a proof can move and nothing on the command line can. | 0237 |
| **D1843** | 8 | §5 Run 8 item 3: *"a `Facts` member `outbound_connectors` … gathered … from `connector_status` through the doctor's evidence or a root `psql` … the induce through `container_exec.run` as `postgres`; observe: poll the delivery row every 1 s … and the heartbeat"*; *"`verdict`'s branch: PASS only if …"*. | `connector_rehearse_delivery` returns the delivery id to an induce whose output `rehearse()` discards, so the observer must FIND the row; the newest `rehearsal` row is an older storm's dead row whenever the induce did not land -- dead, 3 attempts, `connect_failed`, a storm that would read as passed. The doctor carries no connector names and runs twelve checks per call, too slow to poll each second. `bin/rehearse.py`'s tests intercept the module's own `run`, not `container_exec.run`. The verdict vocabulary is `read`/`unread`, never PASS. | `Facts` gains `connectors_enabled` and `database_name` (document facts, free under `--plan`) and `outbound_connectors` and **`rehearsal_deliveries_before`** (READINGS, taken only when the storm will induce, D1694); the observer counts a row as the storm's only when the count is one MORE than before, and the verdict requires `after == before + 1`. One statement per poll (`rehearsal.STORM_READING`: the count, the newest row, `workflow_worker.seen_at`); every argv built by `container_exec.exec_argv` (no `-i`) and run through `rehearse.run` (stdin closed, bounded) -- ADR 0218's rule kept, and the recorded runner sees each call. The facility is refused by the PLANNER (free) and a missing connector or count by `refuse_without_a_reading`. The doctor's clause reads *"deliveries: not read (…)"*, the approvals clause's own colon, where the plan wrote it without one. | 0238 |
| **D1844** | 9 | §5 Run 9 item 6: *"the installed side a worktree at `02ffbbd`, the candidate a `tar`-piped copy … both rendered as `project.example.yaml`"* → expect verdict `ok`. | **Measured: each tree rendering its OWN `project.example.yaml` reads verdict `blocked`**, reason *"the operator's own inputs moved: project_sha256"* -- the example manifest moved to schema 7 in Run 4 (D1824), and the recipe compared two different operator inputs. An operator's manifest does not move with a release. | The candidate renders the INSTALLED tree's manifest (copied in as `project.installed.yaml`): `bump minor`, `requires minor`, verdict `ok`, `operator_digests_moved []`, no `secret_required_added`; undeclared `requires patch`. Seven leaves, not D1811's five: the example set's own `migrations.project_set.count` 2 → 3 and `.lock_sha256` (its `0003`) are the two it did not name. Run 10's host reading uses each project's INSTALLED manifest, which is this rig's shape. | 0162 |
| **D1845** | 9 | §5 Run 9 item 3: *"`inbox` … scopes EXACTLY `notes-inbox`'s required scopes as the status document reports them — read them from `GET /admin/connectors`"*; EVT-WAIT-002: *"read the note id from the `create` step's result"*. | `connector_status` carries NO `required_scopes` (0036: name, kind, binding, counts, dead letters); `notes-await-embedding` has no `create` step -- its wait comes first, on `{{input.note_id}}` (D1832). `ApiResponse` is frozen. | The agents' scopes are read from `app_private.connector.required_scopes` and `workflow_definition.required_scopes` as the superuser -- read, never typed, which was the plan's point; the waiting run's note is created by the proof and passed as its input; `inbound()` returns `(answer, delivery id)`. | — |
| **D1846** | 9 | §5 Run 9 item 3: REC-EVT-001 compares *"`pending + dead` from `connector_delivery WHERE created_at <= target` with the drill's `workflow_runs.value.deliveries`"*. | The drill nests `deliveries` BESIDE `value`, not inside it (`restore-test.py`, Run 8); and a delivery pending at the target may be delivered or dead when the live cluster is read -- comparing today's statuses would race the loop. | The live side is rebuilt AS OF the target from each row's own times (pending: neither `delivered_at` nor `dead_at` by then; dead: `dead_at` by then) and compared per status with `workflow_runs.deliveries.value`; the floor (at least one undelivered row) is kept. | 0238 |
| **D1847** | 9 | §2: CONN-FAC-001's *"`tests/contract/test_secret_contract.py` (whole — both directions)"*, CONN-CMD-001's *"`tests/contract/test_cli_contract.py` (whole, D1014)"*, CONN-STORM-001's proposed `test_every_scenario_has_induce_observe_reverse_and_a_reader` and `test_plan_mutates_nothing`. | No registry entry names a whole module; the two storm sweeps exist under their Session 18 names. **The gate's first run on `7161a19` stopped at step 2** (E501 in the Session 34 paragraph, left by an edit made after the pre-commit ruff pass). | The cells name specific tests (four secret-contract proofs, four CLI-contract guards) and the storm sweeps' real names; repaired forward in `0299500`, and the gate's second run is the record. | — |
| **D1848** | 10 | §9: *"Admission would refuse alpha's or beta's OWN redeploy: stop before the deploy"* -- written as a stop, never predicted. Sheet D1 expected `fleet` to list both projects and `dr-kit export` to write the PRE kit. | **Measured on Sheet D1 (reads only, nothing deployed): `fleet` read both documents as *"does not validate against the outputs schema"*; `dr-kit export` exit 2, no PRE kit.** `outputs.schema.json` admits 19 only, and four readers -- `capacity_probe.read` (deploy step 0, `admit`, `doctor capacity`), `fleet`, `dr-kit export`, `project-retire` -- ran the WRITER's `validate_deployed_document` on a document that already existed. A workstation rig on beta's REAL version 18 document: unreadable, `decide` refused; the same document plus only `connectors: {enabled: false}` at 19: read. So alpha's deploy would have refused at step 0 on beta's document and beta's on alpha's, every order, no override. 1.12.0 is the first outputs bump since admission shipped (v18 Session 21, `cfb1e93`; admission Session 31, `56096d3`). | **Run 10a**, ADR 0241: `deployed_output.read_deployed_document` reads an EXISTING document by version (D1122's kit rule for every reader): current validates fully; the previous version must be `deployed`, with no sensitive key and no placeholder, and is returned as found; anything else is `UnreadableVersion`, reported in its own words. No migration (ADR 0012). The four readers and `dr-kit verify`'s current branch use it; a class guard refuses any call of the writer's validator outside `deployed_output`. The deploy, the sweep and the tag move to Run 10a's commit (nothing had been deployed). | 0241 |
| **D1849** | 10 | §5 Run 10, the facility script: *"assert the rendered document says `connectors.enabled: true` and `secrets.required_names` gained exactly `connector_signing_key`"*. | `secrets.required_names` is the render's PLANNED surface at `RENDER_SESSION = 2` (`rendering.py:51`) and never names a Session 34 secret: the workstation rig measured it unchanged with the facility on. | `s34-r10-facility.py` asserts with the contract's own reader: `active_secrets(contract, CURRENT_SESSION, facilities=enabled_facilities(manifest))` before and after -- 18 → 19, gained exactly `connector_signing_key`. `s34-r10-after-facility.sh` reads where, if anywhere, the deployed document names it rather than predicting it. | — |
| **D1850** | 10 | Sheet D9: *"expect four rows, all `disabled` or `already_disabled`"*. | `app_private.connector_disable` returns `'disabled'` for every row it updates and raises `PT404` for none (0036:727-743); it has no `already_disabled` word. | The cleanup expects four `disabled`. | — |
| **D1851** | 10 | §5 Run 10: *"a Python deriver modelled on `s33r9-derive.py`"*; the facility edit: *"load it with `yaml.safe_load` … write it back preserving key order … assert it touches exactly those lines"*. | `s33r9-derive.py` is on neither the workstation nor the host (it lived in a lost scratchpad). A `safe_dump` of beta's manifest would reflow the file, so the plan's own diff assertion could not hold. | `~/s34r10/s34r10-derive.py` written in its described shape (named substitutions, every count asserted, headers replaced whole to an anchor, parent tokens refused in code): ten scripts, first time; the gate's declaration block 15 tokens in, 15 out. The facility edit is TEXT -- the one `schema_version: 6` line and an appended block -- checked by parse equality and key order; a rig proved control-refused / 1+6 lines / second-run-refused. | — |
| **D1852** | 10 | §5 Run 10, the facility script: *"copy `/home/op/agentic-postgres/project.beta.yaml` to `project.beta.yaml.pre-s34`"* -- beside it, in the checkout. | **Measured: Sheet D5's first run refused at step 3**, *"the checkout has uncommitted changes"*: the backup is an UNTRACKED file (only `project.beta.yaml` is gitignored) -- D971's class. Steps 0–2 read and rendered only; nothing was installed. The workstation rig could not see it: it ran in a `git archive` copy with no `.git`. | The backup moved to `/home/op/project.beta.yaml.pre-s34` (the checkout clean again, the edited manifest in place) and `s34-r10-facility.py`'s `BACKUP` is `CHECKOUT.parent`; D5 re-run: exit 0. | — |
| **D1853** | 10 | §5 Run 9 item 3's live module and the older live proofs, expected to pass on the first 1.12.0 sweep. | **The first sweep on `14b1b9d` (2026-09-30, 35 min 36 s): 1,068 passed, 6 failed, 7 skipped, 2 errors; exit 5.** `connector_inbound_live` and `connector_schedule_live` PASSED on first execution; every Session 30–33 claim held. Five INSTRUMENT defects, no product one: (1) the `sink` fixture read `project_b["compose"]` -- a RENDERED-only member; the deployed document names the network at `edge.project_internal_network` (measured equal, `apg-beta-dev-internal`) -- so both delivery proofs ERRORED at setup, no dead letter was left, and REC-EVT-001's floor failed (`delivery_restore`); (2) the event wait RESUMED (`reason: event_received`, the event's payload) and the proof read `outcome` for the reason; (3) outputs 19's leaf `connectors.enabled` was unclassified in the isolation matrix (`isolation_matrix`, and `agent_tenant_surface`, which carries that node); (4) `test_materialized_files_are_read_only_and_owned_by_the_declared_consumer` and (5) `test_the_rotation_surface_describes_this_deployments_generation` asked for `connector_signing_key` in ALPHA's generation -- alpha has no facility; both projects had the mirror, so no live project had lacked a facility until now. `rotation.plan_all` is the contract's DECLARED view by design (`bin/rotate-secret.py` names no project). | Run 10b repairs the five instruments (tests only; the deployable diff from `14b1b9d` is empty, D1641's method): the network from the deployed document; `outcome == succeeded` AND `reason == event_received`; `connectors.enabled` classified beside `backup.mirror.enabled`; both secret proofs filtered by `enabled_facilities(project_a)`. A `-k` iteration, then a second sweep; the deployment stays on `14b1b9d` and the tag says so. | — |
| **D1854** | 10 | The second sweep (Run 10b), expected to leave `documented_path` the only failure. | **Measured: the second sweep on the unchanged `14b1b9d` deployment (instruments `5b8f641`, 44 min 40 s): 1,074 passed, 2 failed, 7 skipped, 0 errors; ALL FIVE Session 34 host claims PASSED, and every claim the first sweep lost to D1853 passed.** The second failure was `test_project_bs_route_refuses_project_as_administrator` (`project_isolation`, which passed in the first sweep): project A answered its OWN administrator's token 401 `authentication_failed`. `admin_session` is SESSION-scoped and logged in once; the deployment issues 900-second tokens (`claims.MAX_TTL_SECONDS`, 30 s skew), and the JUnit times put that proof **933 s** after the first proof that requested the session. Session 34's connectivity module (121 s, which ERRORED at setup in the first sweep) now sits between them. The product was right to refuse an expired token; the fixture held one past its deadline. | **Run 10c** (tests only; the deployable diff from `14b1b9d` stays empty): `AdminSession.token` is a property that logs in again through the same published route, confirmed by `/auth/me` for the same user, once the token is within `ADMIN_TOKEN_RENEW_MARGIN_SECONDS` (120) of `expires_at`; the token is kept out of the dataclass's `repr` (the failing sweep's log printed part of one). `tests/contract/test_admin_session_renewal.py` (new): the offline half; battery 5/5 beside a green control. A third sweep, by the operator's decision. | — |
| **D1855** | 10 | Sheet D8: *"the plan names `note-embedded` (the first outbound by name) and `127.0.0.1:9`"*. | `bin/rehearse.sh delivery-retry-storm --plan` printed the placeholder *"<the first outbound connector by name, read before inducing>"*: `--plan` reads no cluster, and the connector is read before INDUCING (`storm_facts`). The run itself named `note-embedded`. | Recorded; the plan output is what `_delivery_retry_storm` promises when no connector was read (Run 8's design). No change. | — |
| **D1856** | 10 | `dr-kit export`'s own line: *"the kit is owned by op; modes are unchanged (0700/0600)"*. | Every kit's `projects/` subdirectory is `755` on the host -- `kit-2026-09-30-pre`, `-post` and Session 33's `kit-2026-09-28-post` alike (the kit root is `700`, so nothing is reachable through it). A long-standing inaccuracy in the message, not a new exposure. | Recorded for the session that next moves `dr_kit.py`; the WSL copies were set 0700/0600. | — |

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

**Two new families, `EVT` and `CONN`** (D1810): the regex at
`tests/contract/test_acceptance_registry.py:98` gains `EVT|CONN`, and the
paragraph above it (after Session 33's sentence at `:94-97`) gains one
sentence: *Session 34 (ADR 0235-0239) adds `EVT` for what an event is and who
may write or wait on one, and `CONN` for what a connector is, how it is bound,
delivered and started; the restore row is `REC`'s.* **Sixteen requirements,
sixteen claims, all `target_session: 34`, all P0 — eleven offline, five
host.** Every requirement belongs to a claim (D697); a new requirement gets a
claim of its own (ADR 0089, D1150). **Node ids below are proposed; Run 9 writes
what the runs actually wrote, read out of the tree with `pytest --collect-only
-q`** (D1236, D1762). The registry entries cannot be committed before Run 9
moves `CURRENT_SESSION` (D690): the runs write the proofs and this table; Run 9
lands the YAML.

| Requirement | What it states | Offline node ids (proposed) | Live half |
|---|---|---|---|
| `EVT-EMIT-001` | Migration 0036 creates `connector`, `connector_event`, `connector_delivery` and `connector_receipt` with no grant to any role; `app.emit_event` is SECURITY DEFINER, owned by the object owner and executable by NO role (a request role and `auth_service` are refused `42501`); called from a definer function it serves a parked wait of the same owner whose match the payload contains, records one event and one delivery per enabled subscribed connector with an endpoint, and returns `NULL` when nothing listens; it refuses no identity (`PT401`) and a bad name, version or payload (`PT422`); a rolled-back caller leaves nothing | `tests/contract/test_connectivity_substrate.py::test_the_four_tables_grant_nothing_to_any_role`, `::test_emit_event_is_executable_by_no_role`, `::test_a_definer_function_emits_inside_its_own_transaction`, `::test_nothing_is_recorded_when_nothing_listens`, `::test_one_delivery_per_enabled_subscriber_with_an_endpoint`, `::test_a_disabled_connector_receives_no_delivery`, `::test_a_wait_is_served_only_for_the_same_owner_and_a_contained_match`, `::test_emit_refuses_without_an_identity`, `::test_emit_refuses_a_bad_name_version_or_payload`, `::test_a_rolled_back_caller_leaves_no_event`, `::test_the_payload_bound_is_eight_kilobytes` | — (offline claim `event_emitter`) |
| `EVT-LINT-001` | A project set may not create, replace, alter or drop a function the release creates in `api` or `app` (the names derived from the release templates); a project definer RPC calling `app.emit_event` passes; naming `app_private` is still refused; the example set's `0003` passes and replaces `set_note_embedding` with its signature unchanged | `tests/contract/test_project_migration_sets.py::test_a_project_set_may_not_replace_a_release_function`, `::test_a_project_set_may_not_replace_the_emitter`, `::test_the_release_function_names_are_derived_from_the_templates`, `::test_a_project_rpc_calling_the_emitter_passes`, `::test_naming_app_private_is_still_refused` (control), `::test_the_example_sets_third_migration_keeps_the_signature` | — (offline claim `event_lint`) |
| `EVT-WAIT-001` | A definition may declare `wait: {event: name@version, match, seconds}`; `match` members are literals or whole references to the input or earlier steps; the loop resolves the match once, parks `awaiting_event` until `seconds`, finishes `event_received` with the payload when served and `event_timeout` when not, and mints no token; `workflow_gate_state` reports the event state; the Session 34 refusal is gone | `tests/contract/test_workflow_definition.py::test_a_wait_on_an_event_compiles_with_its_match`, `::test_a_match_may_reference_only_the_input_or_an_earlier_step`, `::test_a_match_value_must_be_a_literal_or_a_whole_reference`, `::test_an_event_reference_must_name_a_version`, `tests/contract/test_workflow_worker.py::test_an_event_wait_parks_once_with_its_resolved_match`, `::test_a_served_event_finishes_the_step_with_its_payload`, `::test_an_unserved_event_wait_fails_event_timeout`, `::test_an_event_wait_mints_no_token`, `tests/contract/test_connectivity_substrate.py::test_gate_state_reports_the_event` | — (offline claim `event_wait`) |
| `CONN-DEF-001` | A connector file compiles in three kinds (`outbound`, `inbound`, `scheduled`) against the project's lock and definitions; an outbound names `event: name@version`; an inbound and a scheduled name an installed-to-be definition `workflow: name@version` whose required scopes it records; an inbound body is the closed subset; the host and service body validators agree on every case; `init`'s three skeletons validate; the example set's four connectors compile; step 6e and `apg dev` install them only with the facility, saying which reason otherwise; an uninstallable connector exits 5 | `tests/contract/test_connector_definition.py::test_the_three_kinds_compile`, `::test_an_outbound_connector_names_a_versioned_event`, `::test_an_inbound_connector_names_a_definition_and_records_its_scopes`, `::test_a_scheduled_interval_is_bounded`, `::test_the_body_subset_refuses_what_it_does_not_name`, `::test_the_two_body_validators_agree`, `::test_the_init_skeletons_validate`, `::test_the_example_sets_four_connectors_compile`, `tests/contract/test_deploy_connectors.py::test_nothing_is_installed_without_the_facility_saying_which_reason`, `::test_an_uninstallable_connector_refuses_at_exit_five`, `tests/contract/test_dev_environment_cluster.py::test_dev_up_installs_the_example_projects_definitions` (made stricter: 7) | — (offline claim `connector_definition`) |
| `CONN-FAC-001` | Project manifest schema 7 adds `connectors {enabled, endpoints}`, forbidden below 7; an endpoint carries no userinfo, query or fragment; outputs schema 19 carries `connectors.enabled` on both branches and v18 migrates with `false`; `connector_signing_key` is gated by the `connectors` facility, so a project without it owes nothing and its rendered `required_names` is unchanged; the two key derivations agree on fixed vectors | `tests/contract/test_connector_facility.py::test_schema_seven_admits_connectors_and_six_forbids_them`, `::test_an_endpoint_may_not_carry_a_credential`, `::test_one_reader_decides_the_facility`, `::test_a_project_without_the_facility_requires_nothing_new`, `::test_a_project_with_the_facility_requires_the_key`, `::test_the_two_key_derivations_agree`, `tests/contract/test_output_migrations.py::test_v18_to_v19_adds_connectors_disabled`, `tests/contract/test_secret_contract.py` (whole — both directions) | — (offline claim `connector_facility`) |
| `CONN-OUT-001` | The loop claims at most one due delivery per iteration and never starves a step; it POSTs the canonical body with the three headers and a signature an independent HMAC verifies; a 2xx is `delivered`; any other status or transport failure is retried after the fixed backoff until `max + 1` attempts and then `dead` with a fixed token; a redirect is not followed; a lost lease re-delivers (at-least-once); no record, status or log carries the URL, the payload or the key | `tests/contract/test_connector_delivery.py::test_one_delivery_per_iteration_and_a_step_is_not_starved`, `::test_the_body_and_headers_are_canonical`, `::test_the_signature_verifies_independently`, `::test_a_two_hundred_is_delivered_once`, `::test_a_five_hundred_is_retried_to_max_then_dead`, `::test_every_failure_is_a_fixed_token`, `::test_a_redirect_is_not_followed`, `::test_a_lost_lease_redelivers`, `::test_no_record_carries_the_url_the_payload_or_the_key`, `tests/contract/test_auth_service_shape.py::test_the_allowlist_describes_modules_that_exist_and_use_what_they_declare` (widened by one reviewed row) | — (offline claim `connector_delivery`) |
| `CONN-IN-001` | `POST /connectors/{name}` answers 404 for a bad name or with no key file, 413 above 16 KiB, ONE fixed 401 for every signature failure (missing, malformed, stale, wrong key, wrong delivery id, wrong body), and makes NO repository call before the signature holds; then 400 for a non-object, 422 naming the member for a body outside the declaration, 409 `delivery_replayed`, 409 `connector_disabled`, 409 `agent_scopes_differ`, 404 `no_such_connector`; 202 `{run_id, status}` enqueues a run of the definition as the bound agent with the body as input | `tests/contract/test_connector_routes.py::test_a_bad_name_or_no_key_is_not_found`, `::test_an_oversized_body_is_refused`, `::test_every_signature_failure_is_one_fixed_document`, `::test_no_database_call_precedes_the_signature`, `::test_a_signed_non_object_is_malformed`, `::test_a_body_outside_the_declaration_names_the_member`, `::test_a_replayed_delivery_is_refused`, `::test_a_disabled_connector_refuses_after_the_signature`, `::test_a_widened_agent_is_refused`, `::test_a_signed_request_enqueues_a_run_as_the_bound_agent`, `tests/contract/test_auth_service_shape.py::test_the_application_serves_exactly_the_declared_paths` | — (offline claim `connector_inbound`) |
| `CONN-ADMIN-001` | `admin_connectors:read` and `:write` are administrative and `project_admin`'s alone; `GET /admin/connectors` lists every connector with counts, the last error token and up to 20 dead letters and NO endpoint, payload or key; enable binds an active agent whose stored scopes equal the definition's, refuses `agent_not_active`, `agent_already_bound`, `agent_scopes_differ`, `no_endpoint`, and records who enabled it; disable clears the schedule; an agent token is refused by every admin connector route | `tests/contract/test_connector_admin_routes.py::test_the_three_routes_are_mounted_and_named_by_the_openapi_document`, `::test_status_carries_no_endpoint_payload_or_key`, `::test_enable_binds_an_agent_with_exactly_the_definitions_scopes`, `::test_each_binding_refusal_is_a_fixed_document`, `::test_disable_clears_the_schedule`, `::test_an_agent_token_is_refused_by_every_admin_connector_route`, `tests/contract/test_scope_registry.py::test_the_administrative_class_is_one_per_identity_resource_and_verb` (made stricter) | — (offline claim `connector_admin`) |
| `CONN-SCHED-001` | `connector_fire_due` enqueues one run per due enabled scheduled connector as its bound agent, advances `next_fire_at` by `every_seconds` from now, coalesces missed fires to one, and fires nothing disabled or unbound | `tests/contract/test_connectivity_substrate.py::test_a_due_schedule_fires_once_and_advances`, `::test_missed_fires_coalesce_to_one`, `::test_a_disabled_or_unbound_schedule_fires_nothing`, `tests/contract/test_workflow_worker.py::test_the_loop_fires_due_schedules_each_iteration` | — (offline claim `connector_schedule`) |
| `CONN-CMD-001` | `bin/connector.sh` has six verbs; `status`, `enable`, `disable` call the three admin routes and nothing else with the token from `APG_API_TOKEN`; `enable` and `disable` refuse (exit 2) unless `--confirm` equals `--name`; `key` writes a new 0600 file and never stdout, refuses an existing path, and derives its path from the active generation; `init` and `validate` need no host; the command holds no SQL | `tests/contract/test_connector_command.py::test_the_three_http_verbs_call_the_enumerated_routes_and_nothing_else`, `::test_the_http_verbs_take_the_api_token`, `::test_enable_and_disable_refuse_without_a_matching_confirm`, `::test_key_writes_a_new_private_file_and_never_stdout`, `::test_key_derives_the_generation_path`, `::test_every_verbs_help_needs_no_project`, `::test_the_command_holds_no_sql`, `tests/contract/test_cli_contract.py` (whole, D1014) | — (offline claim `connector_command`) |
| `CONN-STORM-001` | `delivery-retry-storm` is the eleventh scenario: refused without the facility or an outbound connector; its plan induces one rehearsal delivery through a function granted to nobody, observes exactly three attempts at the backoff and `dead`/`connect_failed` with the heartbeat moving, reverses nothing and verifies the `workflow` check; `--plan` mutates nothing | `tests/contract/test_rehearsal.py::test_every_scenario_has_induce_observe_reverse_and_a_reader` (parametrised, now eleven), `::test_plan_mutates_nothing` (parametrised), `::test_the_storm_is_refused_without_the_facility_or_a_connector`, `::test_the_storm_observes_three_attempts_and_a_dead_letter`, `::test_the_storm_verdict_needs_the_heartbeat_to_move` | — (offline claim `delivery_storm_rehearsal`) |
| `CONN-IN-002` | On the deployment: a correctly signed request to beta starts a run as the bound agent that creates ONE note; a wrongly signed one is refused 401 with no receipt and no run; a replay is refused 409 with one receipt and one run; a stale timestamp is refused; a disabled connector refuses after the signature; an over-scoped agent cannot be bound; alpha, without the facility, answers 404 | — | `tests/deployment/test_session34_connectivity.py::test_a_signed_request_creates_one_note_as_the_bound_agent`, `::test_a_wrongly_signed_request_leaves_no_receipt_and_no_run`, `::test_a_replayed_delivery_is_refused_once`, `::test_a_stale_timestamp_is_refused`, `::test_a_disabled_connector_refuses_after_the_signature`, `::test_an_over_scoped_agent_cannot_be_bound`, `::test_the_project_without_the_facility_has_no_connector` (host claim `connector_inbound_live`) |
| `CONN-OUT-002` | On the deployment: an owner's direct write of an embedding emits one event delivered ONCE to the sink with a signature the proof verifies itself; a connector whose endpoint answers 500 is attempted exactly `max + 1` times at the backoff and dead-lettered `http_500`, and `apg connector status` shows it with no URL and no payload; with both outbound connectors disabled the same write records no event | — | `tests/deployment/test_session34_connectivity.py::test_an_owners_write_is_delivered_once_and_signed`, `::test_a_failing_endpoint_is_retried_to_max_then_dead_lettered`, `::test_nothing_is_recorded_when_nothing_listens_on_the_deployment` (host claim `connector_delivery_live`) |
| `EVT-WAIT-002` | On the deployment: a run waiting on `note_embedding.set@1` for its own note resumes when the owner writes that note's embedding, and the wait step's result carries the note id; an embedding written for ANOTHER note leaves it parked | — | `tests/deployment/test_session34_connectivity.py::test_a_waiting_run_resumes_on_its_owners_matching_write`, `::test_an_event_that_does_not_match_leaves_the_run_parked` (host claim `event_wait_live`) |
| `CONN-SCHED-002` | On the deployment: an enabled scheduled connector starts a run of its definition as its bound agent within `every_seconds + 2 × POLL_SECONDS`; disabling clears `next_fire_at` | — | `tests/deployment/test_session34_connectivity.py::test_an_enabled_schedule_starts_a_run_and_disable_stops_it` (host claim `connector_schedule_live`) |
| `REC-EVT-001` | A restored drill carries the undelivered deliveries (pending + dead) the live cluster held at the target | — | `tests/recovery/test_session34_delivery_restore.py::test_a_restored_drill_carries_the_undelivered_deliveries` (host claim `delivery_restore`) |

**Expected counts** — Run 9 counts them from the tuples, never from this
prose (D1628): requirements **265 → 281**, `CLAIMS` **172 → 188**,
`OFFLINE_CLAIMS` **42 → 53**, ADRs **234 → 239**.

**Claims** (`src/agentic_postgres/evidence_claims.py` `CLAIMS`, in a block
commented *Session 34 (ADR 0235-0239)*): offline — `event_emitter:
("EVT-EMIT-001",)`, `event_lint: ("EVT-LINT-001",)`, `event_wait:
("EVT-WAIT-001",)`, `connector_definition: ("CONN-DEF-001",)`,
`connector_facility: ("CONN-FAC-001",)`, `connector_delivery:
("CONN-OUT-001",)`, `connector_inbound: ("CONN-IN-001",)`, `connector_admin:
("CONN-ADMIN-001",)`, `connector_schedule: ("CONN-SCHED-001",)`,
`connector_command: ("CONN-CMD-001",)`, `delivery_storm_rehearsal:
("CONN-STORM-001",)` — **these eleven in `OFFLINE_CLAIMS`**, with the
per-session assertion in `test_session_thirty_four_gate_modes.py` (D1237:
assert THESE eleven are in the set, never the set's size). Host —
`connector_inbound_live: ("CONN-IN-002",)`, `connector_delivery_live:
("CONN-OUT-002",)`, `event_wait_live: ("EVT-WAIT-002",)`,
`connector_schedule_live: ("CONN-SCHED-002",)`, `delivery_restore:
("REC-EVT-001",)` — not declared. `CLAIM_INTRODUCED_IN`
(`tests/contract/test_evidence_claims.py:953`, after Session 33's rows
`:1140-1156`) gains sixteen rows at 34.

**Existing entries that move** (each a passing proof made stricter or a
sentence corrected, never weakened — CLAUDE.md §6):

- **WF-DEF-002** (`tests/acceptance-registry.yaml:5189-5227`):
  `test_a_wait_on_an_event_is_refused_naming_session_thirty_four` leaves its
  node ids (ADR 0239 authorises the replacement, D1793) and the description's
  *"`wait: {event}` is refused naming Session 34"* becomes *"since Session 34
  a wait may name an event (EVT-WAIT-001)"*. The four EVT-WAIT-001 compiler
  proofs are NEW ids under EVT-WAIT-001, not WF-DEF-002.
- **The live proof that pins the definitions installed** —
  `test_dev_environment_cluster.py::test_dev_up_installs_the_example_projects_
  definitions` joins CONN-DEF-001 at the new number (7) and stays in whatever
  entry holds it today (grep its node id; if WF-INSTALL-001, it is listed in
  both, which the registry allows — read `test_acceptance_registry.py` for the
  duplicate rule first, and if duplicates are refused, it stays in its entry
  and CONN-DEF-001 names the new cluster proof `test_dev_up_says_why_it_
  installed_no_connectors` instead).
- **The six scope pins** (D1796) move to the new exact sets — each a larger
  equality, never a subset check.
- **`test_the_loop_starts_in_auth_mode_only`** is unchanged and must stay
  green (D1790) — it is the proof that the delivery pass is not a second task.
- **AGT-APPROVE-001 / THR-APPROVAL** unchanged.

**New environment gates: none.** Every live proof creates its own humans,
agents, notes and runs on `project_b` from `APG_PROJECT_B_OUTPUTS`, reads the
connector key through the product's own `bin/connector.sh key` as root (the
sweep runs as root), and uses `APG_PROJECT_A_OUTPUTS` for alpha's control;
both are in the roster (`tests/conftest.py`). **The Session 34 gate therefore
accepts exactly the flags the Session 33 gate accepts — the derivation diff
proves it (D1133).**

---

## 4. Irreversible operations

| Operation | Where | What makes it safe |
|---|---|---|
| Migration **0036** written and frozen into `migrations/released.lock.json` | Run 3 | `bin/migrate.sh freeze-lock` is the only writer; the proofs apply every released migration as `migration_user` on a fresh container before the freeze; its down is `AP900`; **once applied on the host it is the floor** (ADR 0162 §3), and **0034 and 0035 are never amended** (D912) — `workflow_gate_state` and `workflow_counts` are `CREATE OR REPLACE` in 0036 with the SAME signature and return type (`jsonb`), and a rig reads `pg_get_function_identity_arguments` before and after |
| New enums `app_private.connector_kind`, `app_private.delivery_status` | Run 3 | CREATED (not `ADD VALUE`) in 0036, so using them in a DEFAULT or CHECK in the same migration is safe — rig 33e's `55P04` applies only to a value ADDED to an existing enum |
| Four new columns on `app_private.workflow_step` (`await_event text`, `await_match jsonb`, `await_payload jsonb`, `await_served_at timestamptz`) | Run 3 | All nullable, no default rewrite; existing rows untouched; a `CHECK (await_event IS NULL OR await_event ~ '<name>@<version>')` |
| The example set's migration **0003** frozen into `projects/example/migrations/released.lock.json` | Run 5 | `bin/migrate.sh freeze-lock --project project.example.yaml` (read `--help` for the exact spelling); the version sorts after `20260914120002` AND after the release's newest at freeze (`follows_release_version` — read `docs/migrations.md`'s ordering section and ADR 0206 first, D1098's measured refusal); applied on beta's second deploy only if the project ledger shows it pending |
| The lint's new rule | Run 2 | Stricter only; every existing project set in the tree (the example) passes it — a proof runs the lint over every `projects/*/migrations` before and after |
| Project manifest schema 7; outputs schema 19 with a migrator | Run 4 | Versions 1–6 still load (`project.alpha.yaml`/`project.beta.yaml` live only on the host); `migrate_v18_to_v19` is additive and its proofs copy `migrate_v17_to_v18`'s; the host's installed v18 documents migrate on the next deploy by the existing chain (grep every caller of `migrate_v17_to_v18` and add the step beside it) |
| A new facility-gated secret in `secrets.required.yaml` | Run 4 | A project without the facility owes nothing (a proof over the three example manifests); `test_secret_contract.py` both directions; `redaction: full` |
| Two new administrative scopes | Run 7 | ADR 0236 first; the six pinning proofs updated to the new exact sets in one commit; no existing administrator gains them (a proof over `bin/auth-admin.py`'s bootstrap and the upgrade row's sentence) |
| An unauthenticated route on the auth service | Run 7 | `THR-CONNECTOR-INPUT` and `THR-WEBHOOK-REPLAY` first (Run 1); the order proof with a repository that raises; `bin/app-contract.sh --update` then `--check`; **the example client regenerated (D1690)** and `test_client_typescript`, `test_generate_command`, `test_studio_command`, `test_client_ir` run |
| An outbound POST to an operator's URL from the auth process | Run 6 | `THR-DELIVERY` first; its own module and allowlist row; no redirect; a URL never recorded |
| `CURRENT_SESSION` 33 → 34; `VERSION` 1.11.0 → 1.12.0 | Run 9 | All-or-nothing (D690); every `target_session: 34` entry in the same commit; `docs/upgrade-guide.md` gains a `1.12.0` row; `README.md:7` moves; the `--session`/`--through-session 33` literals on the documented path moved (eighteen measured at planning in five current-path files plus the plan itself — grep them, D678/D1484) |
| `bin/session-34-check.sh` | Run 9 | Derived from 33's by diff (D1482); header and usage rewritten whole (D1488); `SHELL_COMMANDS` gains it and `chmod 755` before `git add` (D1014, D1188); the verbatim `run_suite` selector kept (D1242); the flag diff empty |
| Deploy `--through-session 34` on alpha, then beta, then beta's facility | Run 10 | `upgrade plan` OK first; alpha first; one sheet per outcome (D1510); under `script(1)`; **0036 applied** (ledger 35 → 36; beta 36 + 3 after its project migration); `auth`, `storage`, `mcp`, `docs` recreated (image, lock and app contract moved); `doctor` 12 ok after each |
| `bootstrap-providers.sh --apply` for beta | Run 10 | Creates ONE provider value (`APG_CONNECTOR_SIGNING_KEY`) and records it in beta's `managed_resources`; `--plan` first names exactly that one; it reaches Infisical (D976: an intermittent hang is retried by the client three times — if it hangs longer, STOP and read, never re-run in a loop) |
| Humans, agents, notes, runs, receipts, events and deliveries written on beta by the proofs | Run 10 | Humans deleted at teardown where no FK refuses; agents revoked (D1700); notes deleted by canary title; runs, receipts, events and deliveries left as the substrate's record and counted in the Done; every connector DISABLED in `finally` |
| Tag `1.12.0` on the deployed commit | Run 10 | After the merge exits 0 or 5 for the expected reasons only (§7); `release-reading --ref <deployed sha>` first; D1641's method stated in the tag if an instrument moves |

---
## 5. Build order, run by run

Each run ends with a `**Done.**` paragraph written by the executor: what was
measured, the numbers, the rows it added, and — for a code run — the CI
verdict by full SHA. A run that changes code pushes and reads CI; the targeted
modules run ONCE at the run's close and only the failing module is re-run
(the user has asked thirteen times). `ruff format && ruff check` before every
commit; `chmod 755 bin/*.sh bin/*.py deploy.sh` before every `git add`; commit
messages from a file with `-F`, ending with the attribution line the session's
system reminder gives. **Grep the plans for every third party before
measuring it** (`grep -rn -i '<term>' docs/plans/*.md docs/decisions/*.md`).
**A run that renames, adds or removes a test function runs
`test_acceptance_registry` and `test_evidence_claims`** (D1119, D1674); **a
run that adds a `GRANT` ships its caller in the same commit** (D1680); **a run
that adds a migration re-renders BOTH example projects** before its targeted
list (D1678: `bin/render-config.py --render-only` over `project.example.yaml`
and `project.second.example.yaml` — read `--help` for the exact spelling);
**a run that moves the app OpenAPI document regenerates the example client**
(D1690); **a run that adds or removes a `bin/` command runs
`test_cli_contract` and `git add`s the command first** (D1014, D1188); **a run
that touches a documentation page runs `test_documentation_index` and
`test_session12_documented_path`**; **every new test module carries
`pytestmark` before its first test** (D1240) and the sweep-selector guard
(D1242) is in the targeted list of any run that adds one.

**The Docker-backed modules are the slow ones** (~3 min each: they build a
real cluster). Keep two lists per run: the fast modules after each edit, the
Docker-backed ones ONCE just before the commit (the user's standing request,
CLAUDE.md memory *working agreements*).

### Run 1 — the measurements, three `THR-*` rows, and ADRs 0235–0239

**Documentation only. Push, say it is pushed, read NO CI verdict.**

**Reads first** (agent, no edits): `migrations/templates/0034-workflow-
substrate.sql:1-120` and `:320-520`; `0035-workflow-gates.sql:1-60`,
`:590-630`, `:720-910`; `0003-owner-scoped-tables-and-forced-rls.sql:1-30`;
`0018-agent-read-plane.sql:230-275` (how `app.user_id` and `app.agent_id` are
set); `projects/example/migrations/templates/0001-note-embeddings.sql` whole;
`src/agentic_postgres/migrations.py:80-170` and `:740-860`;
`src/agentic_postgres/sql_surface.py` whole; `contracts/postgrest-api-surface.
yaml` whole; `services/auth-api/app/workflow_worker.py:160-300` and
`:630-762`; `main.py:91-213` and `:405-490`; `secrets.required.yaml:1-40`,
`:470-575`, `:930-1015`; `src/agentic_postgres/secrets_contract.py:60-215`;
`bin/deploy-project.py:750-830`; `src/agentic_postgres/upgrade_plan.py:
215-370`; `runtime_override.py:1251-1310`; `infra/edge/dynamic/baseline.yaml`
whole; `docs/decisions/0188-*.md`, `0226-*.md`, `0228-*.md`, `0233-*.md`;
this plan's §1. Then re-run the deployable-diff filter named in §0 and write
its answer.

**The rigs.** Each is a script written with the Write tool to
`\\wsl$\Ubuntu\tmp\rig34x.sh` (or `.py`) and copied to the scratchpad, each
names its images by digest (read `versions.lock.json` / `bin/lock-versions.sh
--help` for the reader), each has a control, and each prints its own exit
status from inside. **Session 33 ran its rigs as ONE script on ONE stack**
(`apg dev up --project project.example.yaml` + the pinned PostgREST verifying
the auth application's JWKS + both application modes run from the checkout as
subprocesses with the image's own entrypoint, each environment built from
nothing — its Run 1 `**Done.**`); copy that method and say so. Any Python that
imports `agentic_postgres` needs `PYTHONPATH=src`.

| Rig | Subject | Method | Control | Owes |
|---|---|---|---|---|
| **34a** | The emitter's grant and the lint's hole | On the `apg dev` cluster (35 release + 2 project migrations): as `postgres`, `SET ROLE <object_owner>` and create a PROTOTYPE `app.emit_event(p_name text, p_version integer, p_payload jsonb) RETURNS uuid` (SECURITY DEFINER, search_path pinned, inserting into a scratch table `app_private.rig_event` and returning its id), `REVOKE ALL … FROM PUBLIC`; then a prototype project function `api.rig_emit()` SECURITY DEFINER as the owner calling it. (i) `SET ROLE <authenticated>` with `app.user_id` set: `SELECT app.emit_event(…)` → record the SQLSTATE; the same for `<agent_writer>` and `<auth_service>`; (ii) `SET ROLE <authenticated>`: `SELECT api.rig_emit()` (grant it EXECUTE for the rig) → a row, carrying the GUC's owner; (iii) PostgREST `POST /rpc/emit_event` with a human token → record status and body; (iv) a rolled-back caller (`BEGIN; SELECT api.rig_emit(); ROLLBACK;`) → 0 rows; (v) **the hole**: `migrations.lint_project_set` (with `PYTHONPATH=src`) over a scratch project template containing `CREATE OR REPLACE FUNCTION api.create_note(p_title text, p_content text DEFAULT '') RETURNS … AS $$ SELECT … $$` under the preamble → record whether it passes; then apply that text as the owner on the cluster → record whether it replaces the release function (`pg_get_functiondef` before/after) | (i)'s refusal vs (ii)'s success is the grant's measurement; (iii) vs `POST /rpc/create_note` → 200 (PostgREST can address `api`, not `app`); (v) vs the same template naming `app_private` → refused by the lint (the existing rule) | D1779's refusal SQLSTATE and PostgREST status; D1780 *measured* (both halves); the rolled-back event (D1782) |
| **34b** | The signature and the transport, from inside the auth image | `docker run --rm -i <auth image digest> python3 - <<'PY'` is FORBIDDEN in `wsl bash -lc "…"` (CLAUDE.md §1 — heredocs) — write the Python to a file, mount it read-only, run it: (i) `hmac.new(bytes.fromhex(K), b"1727600000.<uuid>." + body, sha256).hexdigest()` for a fixed 32-byte `K` and a fixed body file; the same bytes through `openssl dgst -sha256 -mac HMAC -macopt hexkey:K` on the workstation → equal; (ii) a throwaway local server (a second container on a rig network) answering `307 Location: /elsewhere`: the DEFAULT `urllib` opener → record whether it re-POSTs (and to where); an opener built with a redirect handler whose `redirect_request` returns `None` → record that the 307 surfaces as `HTTPError(307)`; (iii) `POST http://127.0.0.1:9/` from inside the container with `timeout=3` → record the exception type and `errno` (connection refused); `POST http://10.255.255.1/` with `timeout=3` → record the type (timeout); `POST http://apg-no-such-host.invalid/` → record the type (DNS); `POST https://self-signed.badssl.com/` ONLY if the rig host has egress — else record *not measured* and keep `tls_failed` mapped from `ssl.SSLError` by type | (i) a one-byte change in the body → different hex (both tools); (ii) the default opener's behaviour IS the control for the refusing one | D1789's scheme against an independent signer; D1791's redirect refusal; D1800's four error tokens mapped from MEASURED exception types (write the mapping table in the Done) |
| **34c** | Does a `tools/call` need `meta:read`? | Session 33's stack: an `agent_writer` agent with stored scopes EXACTLY `["notes:write"]`; mint its token (`/auth/agent-token`); `tools/call create_note` through the plane (the SSE framing rig 32b measured) → record served/refused and the refusal text | the same with `["meta:read", "notes:write"]` | D1783's exact-scope rule: whether `meta:read` joins the equality. Write the answer as ONE sentence in the Done and in ADR 0236 |
| **34d** | A sink the proof runs, reachable from `auth` by an alias | Create two rig networks: `rig34-internal` with `--internal` and `rig34-edge`; start the sink (`<auth image digest>`, `python3 -c <the 40-line server>`) on `rig34-internal` with `--network-alias apg-s34-sink`; start a client container on BOTH networks (auth's shape) and `POST http://apg-s34-sink:8080/ok` and `/fail` → record 200 and 500 and the sink's stdout line | a client on `rig34-edge` ONLY → record the resolution failure; the sink's stdout carries the three `X-Apg-*` headers exactly as sent | D1792/D1809: the trip's sink works on an `internal: true` network; the server's text is the one Run 9 commits |

**Third-party facts already measured, cited and not re-run:** the plane's
transport and SSE framing (rig 32b, D1672); the plane mints its own request id
(ADR 0160, D1696); a replay is re-read (rig 32c, ADR 0181); definer functions
over a no-grant table (rig 32d, D1647); `psql -c` does not interpolate `-v`
(D1684) — **every install statement goes through `-f -`**; `ALTER TYPE … ADD
VALUE` then use in a DEFAULT is `55P04` (rig 33e); an extra claim survives
every verifier (rig 33a); `structuredContent` is the tool's value (rig 33c).

**The three `THR-*` rows, before any code** (D1527). Appended to
`docs/threat-model.md` after `THR-APPROVAL` (`:37`), in the table's nine
columns (header `:19`):

- **`THR-CONNECTOR-INPUT`**. *Attacker capability*: anyone on the internet who
  can reach the project's domain and does not hold a connector's key; a sender
  who holds it and sends a body the connector did not declare. *Protected
  asset*: the project's database, the connector's bound agent's authority,
  every tenant's rows. *Prevention*: the route reads nothing but the raw bytes
  and two headers until an HMAC-SHA256 under the connector's DERIVED key
  verifies over `<t>.<delivery-id>.<body>` inside ±300 s; one fixed 401 for
  every failure; no database call before it (a proof with a repository that
  raises); then a closed body declaration (names, types, bounds, no extras);
  then a run of ONE installed definition as an agent whose stored scopes EQUAL
  the definition's, re-checked at acceptance; the body becomes the run's
  `input` and reaches a tool only through a compiled argument reference; the
  edge's 16 KiB cap and 20/s rate limit apply (ADR 0237, 0236). *Detection*:
  the auth service's structured request log (path and status; no body, no
  header value); `connector_receipt` for every accepted delivery; the run and
  its audit rows; `apg connector status`. *Residual risk*: a key holder can
  start as many runs as the edge's rate limit allows, each bounded by the
  agent's budgets and quota; refused requests are not in the database (by
  design — a refusal that wrote a row would be a write an unauthenticated
  caller could cause) and the auth service's log is not readable by
  `apg-diag` (D380); the key's compromise is the connector's authority,
  exactly. *Acceptance requirement IDs*: `CONN-IN-001`, `CONN-IN-002`,
  `CONN-ADMIN-001`. *Acceptance test node IDs*: `tests/contract/
  test_connector_routes.py::test_no_database_call_precedes_the_signature`,
  `tests/deployment/test_session34_connectivity.py::test_a_wrongly_signed_
  request_leaves_no_receipt_and_no_run` (Run 9 reads the final names out of
  the tree). *Target session*: 34.
- **`THR-WEBHOOK-REPLAY`**. *Attacker capability*: a party that captured one
  correctly signed request (a proxy log, a misconfigured sender) and sends it
  again, now or later, with or without a new delivery id. *Protected asset*:
  exactly-once acceptance of each delivery. *Prevention*: the delivery id is
  INSIDE the signed bytes, so a new id breaks the signature; the same id is
  refused 409 `delivery_replayed` by `connector_receipt`'s primary key
  `(connector_id, delivery_id)`, recorded in the same transaction that
  enqueues the run; a request older than 300 s fails the signature window
  whatever its id. *Detection*: one receipt per delivery id; the 409 in the
  request log. *Residual risk*: receipts are never pruned in Stage 4 (the
  retention story, D1700's); a sender that re-uses ids across distinct events
  loses the second (documented in `docs/connectors.md`). *Acceptance
  requirement IDs*: `CONN-IN-001`, `CONN-IN-002`. *Test node IDs*:
  `…test_connector_routes.py::test_a_replayed_delivery_is_refused`,
  `…test_session34_connectivity.py::test_a_replayed_delivery_is_refused_once`.
  *Target session*: 34.
- **`THR-DELIVERY`**. *Attacker capability*: an outbound endpoint (or anyone
  who can read its logs) learning more than the event it was sent; a receiver
  redirecting the worker elsewhere; a flood of failing deliveries starving
  the worker. *Protected asset*: the project's credentials, other events,
  other connectors' keys, the worker's availability. *Prevention*: a delivery
  carries the event's name, version, id, time and payload — a payload the
  project's reviewed SQL chose (the example sends a note id, never the
  embedding) — and a signature under THAT connector's derived key; no bearer,
  no cookie, no project credential is sent; the endpoint is read from a
  root-owned manifest, may carry no userinfo, query or fragment, and appears
  in no record, status or log; a redirect is never followed; at most one
  delivery per loop iteration and only when due, so a failing endpoint costs
  `max + 1` attempts and a dead letter, never a hot loop (ADR 0238, the
  `delivery-retry-storm` rehearsal). *Detection*: `apg connector status`
  (counts, oldest pending age, the last error token, dead letters without
  payloads); the doctor's `workflow` line. *Residual risk*: the endpoint is
  whatever the operator declares — an internal service name would receive the
  signed body (rig 34d measured that `auth` reaches its `internal` network);
  the payload is visible to the receiver by design; at-least-once means a
  receiver MUST de-duplicate on `X-Apg-Delivery`. *Acceptance requirement IDs*:
  `CONN-OUT-001`, `CONN-OUT-002`, `CONN-STORM-001`. *Test node IDs*:
  `…test_connector_delivery.py::test_no_record_carries_the_url_the_payload_or_
  the_key`, `…test_session34_connectivity.py::test_a_failing_endpoint_is_
  retried_to_max_then_dead_lettered`. *Target session*: 34.

**ADRs written after the rigs, before any code**, each indexed in
`docs/decisions/README.md` after `0234` (`:300`) as `| [NNNN](file.md) | Title |
34 | Accepted |`, each file `docs/decisions/NNNN-kebab-title.md` with H1
`# NNNN — <Title>` and the house header (Status, Date, Session, Affects,
Related):

- **0235 — An event is written by a reviewed definer function in its caller's
  transaction, lives in `app`, and is recorded only when something listens.**
  Context: D1779–D1782, rig 34a. Decision: `app.emit_event`, granted to nobody,
  identity from the GUCs; the recording rule; the payload bound; the lint rule
  that no project set may define a release function; the example's `0003`.
  Alternatives: `api.emit_event` granted to the request roles (rejected: a
  forgeable `POST /rpc/emit_event`); `api.emit_event` granted to nobody
  (rejected: an `api` function no role can call is refused by
  `test_api_migrations.py:541-544`, and five exact pins move for nothing); a
  trigger on a base table (refused by the stage plan: every write an event
  nobody reviewed); an event log that records everything (rejected: retention
  with no reader).
- **0236 — A connector is a project artefact installed by the deploy, enabled by
  an administrator, and bound to an agent that holds exactly its definition's
  scopes; inbound and scheduled connectors start runs.** Context: D1783,
  D1795–D1799, rig 34c. Decision: the three kinds; installed DISABLED;
  `admin_connectors:read|write`; the equality rule and its re-check; the
  coalescing interval; six verbs, no `test`, no redelivery. Alternatives: a
  per-agent profile (rejected: a second permission model, stage §9); calling a
  tool directly from the route (rejected: a second path to a tool, a request
  held open across the plane's timeout); binding by agent NAME in the file
  (rejected: an agent id is per deployment and an agent is created by a
  person).
- **0237 — The inbound route verifies a signature over the delivery before it
  reads anything else, and every connector key is derived from one
  facility-gated secret.** Context: D1784–D1789, D1804, rig 34b. Decision: the
  scheme; the order; the facility (manifest 7, outputs 19, the one reader); the
  derivation written twice and held together; the closed body subset and its
  two validators; `key --output`; the rotation's consequence. Alternatives: a
  secret per connector declared in `secrets.required.yaml` (rejected: secrets
  are static per release); a required secret (rejected: prices the release at
  major); keys in the database (rejected: a plaintext credential in every
  backup, and a database read before the signature); JSON Schema in the image
  (rejected: an unpinned transitive dependency for a subset).
- **0238 — Outbound delivery is the worker's second pass: signed, at-least-once,
  fixed backoff, dead-lettered, never redirected, and it records no URL,
  payload or key.** Context: D1786, D1790–D1794, D1800–D1803, D1809, rigs
  34b/34d. Decision: the pass order inside `run_forever`; the module and its
  allowlist row; the body and headers; the error tokens; the lease; the
  rehearsal; the doctor line; the drill member. Alternatives: a second asyncio
  task (rejected: D1790's proof and ADR 0226's reason); exponential backoff
  (rejected: the brief says *declared*); treating 4xx as terminal (rejected:
  the brief's control; bounded anyway); reusing compensation (rejected: no
  subject, D1794).
- **0239 — A wait on an event resumes on its run owner's matching event, and the
  Session 34 refusal is replaced.** Context: D1793. Decision: the definition
  shape; resolution at park; the emitter serves the wait in the caller's
  transaction; `workflow_gate_state`'s new member; `event_received` /
  `event_timeout`; **this ADR authorises replacing
  `test_a_wait_on_an_event_is_refused_naming_session_thirty_four` with the
  EVT-WAIT-001 proofs** (CLAUDE.md §6: a passing test may be replaced by a
  stricter one when an ADR authorises it). Alternatives: a run id in the event
  (rejected: the emitter's caller knows no run); first-come across owners
  (rejected: a cross-tenant resume); a separate event table the worker polls
  (rejected: a second reader of one fact, and a delay the emitter need not
  add).

Run `pytest tests/contract/test_acceptance_registry.py tests/contract/
test_documentation_index.py -q -p no:randomly` (the ADR index proofs and the
page index). Commit (`Session 34 Run 1: the rigs, three THR rows, and ADRs
0235-0239`), push. **No CI read** — documentation only.

**Done.** 2026-09-29. **The deployable-diff filter at `5523873`** (§0's list
plus `deploy.sh` and `VERSION`) names ONE file, `src/agentic_postgres/
capacity.py` — as §0 predicted. **The rigs ran as ONE script** (`/tmp/rig34/
rig34.py`, rig 33's method: `apg dev up --project project.example.yaml` in
20.5 s, PostgreSQL **18.4**, 35 release + 2 project migrations, 4 definitions;
PostgREST from the pinned `v14.16` digest verifying the auth application's own
JWKS; both application modes from the checkout as subprocesses with the image's
entrypoint, each environment built from nothing), **exit 0**, plus one
follow-up `bis.py` (exit 0). 34b and 34d ran INSIDE an auth image built from
this checkout with all fifteen build arguments read from `versions.env`
(`apg-rig34-auth:local`, `sha256:4a7a337ee3d5…`, 37 s). Scripts, transcripts
and `report.json` are in the session scratchpad (`rig34/`). **34a** — as
`authenticated`, `agent_writer`, `auth_service` and `anon`: **`42501 permission
denied for schema app`**, `has_function_privilege` false for all four (D1814:
the schema refuses first; the proof must read the function's grant too);
through a definer RPC one row carrying the GUC's owner; through PostgREST with
an agent token one row carrying the agent's OWNER and the agent's id;
`POST /rpc/emit_event` **404 `PGRST202`** for a human and an agent token
(control `/rpc/create_note` **200**); a rolled-back caller **3 → 3**. **The
lint's hole, both halves**: `CREATE OR REPLACE` of `api.create_note`,
`app.emit_event` and **`app.current_user_id()`**, and `ALTER FUNCTION
api.create_note … SECURITY INVOKER`, all PASSED; applied as the owner,
`api.create_note`'s definition changed (md5 `c0cdcc57…` → `0d4f9729…`);
controls refused (`app_private`, `DROP`), the emitter-calling RPC passed
(D1815). **34b** — HMAC-SHA256 over `1727600000.<uuid>.<body>`: image Python,
workstation Python and `openssl dgst -mac HMAC` all `3c87822a…`; a one-byte
change `0c80f3a0…` from all three. Redirects: the DEFAULT opener follows
301/302/303 as a bodiless GET that still carries `X-Apg-Signature` and returns
the Location's 200, and refuses 307/308 — it never re-POSTs (D1812); the
refusing opener surfaces all five as `HTTPError`. **The error-token table**
(D1813):

| Case (measured) | Exception | Token |
|---|---|---|
| 500 from the endpoint (34d `/fail`) | `HTTPError(500)` | `http_500` |
| 3xx with the refusing opener | `HTTPError(3xx)` | `http_3xx` |
| `127.0.0.1:9` refused | `URLError`, `.reason` `ConnectionRefusedError` (errno 111) | `connect_failed` |
| `10.255.255.1` connect timeout | `URLError`, `.reason` `TimeoutError` | `timeout` |
| accepts, never answers (read timeout) | bare `TimeoutError` (no `URLError`) | `timeout` |
| `apg-no-such-host.invalid` | `URLError`, `.reason` `socket.gaierror` (errno −2; −5 in 34d's control) | `dns_failed` |
| `self-signed.badssl.com` | `URLError`, `.reason` `ssl.SSLCertVerificationError` ⊂ `ssl.SSLError` | `tls_failed` |
| anything else | — | `unknown` |

**34c** — an `agent_writer` agent whose stored scopes are exactly
`["notes:write"]` was SERVED `tools/call create_note` (200, `isError: false`,
one note, audit `served` + `committed`) and its `tools/list` named
`create_note` alone; control `["meta:read", "notes:write"]` served the same
and listed two metadata tools more. **One sentence: a tool call needs only the
tool's own scope, so `meta:read` does not join the equality** (ADR 0236).
**34d** — a sink from the auth image on an `internal: true` network with alias
`apg-s34-sink` answered `/ok` **200** and `/fail` **500** to a client on that
network and a second one, and printed the three `X-Apg-*` headers exactly as
sent; control, a client on the second network alone: `gaierror`. `sink.py`
(the 30-line server) is the text Run 9 commits. **The three `THR-*` rows** are
appended after `THR-APPROVAL`, citing what holds today (D1816, D1742's shape);
Run 9 rewrites their ID cells. **ADRs 0235–0239** written and indexed (239
rows). Rows **D1812–D1816**. One environment note: the image build briefly
made WSL unreachable from the Bash tool (`Wsl/Service/0x8007274c`) while the
rig itself ran on; a second call 20 s later reached it. **NEXT FREE: D1817,
ADR 0240.**

### Run 2 — the carried-in defect and the lint's missing rule: D1805, D1780

**Code. Push, read CI by full SHA.**

**Read first:** `tests/contract/test_connect_command.py` (the `sleeper`
fixture `:119-134` — `spawn()` is `Popen(["sleep", "300"])` returned at once;
the helper at `:82-90` that reads `lstart` and `args` *"exactly the way the
helper reads them"*; `test_a_live_tunnel_is_reported_live` `:349`) and the
reader it imitates, `bin/connect.sh:299` and `:445` (`ps -p <pid> -o
lstart=`);
`src/agentic_postgres/migrations.py:740-860`; `src/agentic_postgres/
sql_surface.py` whole (`CREATE_FUNCTION` `:50-52` requires `)\s*\n\s*RETURNS`
— a reader of `CREATE OR REPLACE FUNCTION app.x(` must not depend on that
layout; D1677: a call is read AS WRITTEN); `tests/contract/
test_project_migration_sets.py:400-460` and `:630-770`.

1. **D1805.** In the `sleeper` fixture's `spawn()`, after `Popen(["sleep",
   "300"])`, poll
   `ps -o args= -p <pid>` every 0.05 s until it reads `sleep 300`, bounded at
   5 s; on timeout `pytest.fail` with the last reading. **Battery**: a `PATH`
   shim directory whose `sleep` is a script that sleeps 0.2 s and then `exec`s
   the real `sleep "$@"` — with the fix, the proof passes (control); with the
   poll removed (the mutation), it FAILS on the stale-record assertion
   (assert `FAILED`, not `ERROR`, D386). Run the pair in one invocation.
2. **D1780 — the lint rule.** In `migrations.py`: a function
   `release_functions(release_templates_dir) -> frozenset[tuple[str, str]]`
   returning `(schema, name)` for every function a release template CREATES in
   `api` or `app` (read with `sql_surface`'s tokenizer, or a regex over the
   comment-stripped text that accepts any whitespace between the name and
   `(`; never a typed list), and in `lint_project_set` ONE rule, replacing the
   DROP-only check at `:816-825`: a statement matching `(CREATE(\s+OR\s+
   REPLACE)?|ALTER|DROP)\s+FUNCTION\s+(api|app)\.<name>\b` for a name in that
   set refuses with *"defines the release's function `<schema>.<name>`; a
   project set may call it and may never define it"*. Keep the `DROP VIEW
   api.<release view>` half of the old rule (views are not functions). Every
   reader of `lint_project_set` (§0: `rendering.py:2448`, `bin/migrate.py:416`,
   `:442`) passes the release directory it already has — grep, never assume
   (D979).
3. **Proofs** in `test_project_migration_sets.py` (EVT-LINT-001):
   `test_a_project_set_may_not_replace_a_release_function` (parametrised over
   `CREATE OR REPLACE FUNCTION api.create_note`, `ALTER FUNCTION
   api.update_task_status`, `DROP FUNCTION api.create_task`, `CREATE FUNCTION
   app.current_user_id`), `test_a_project_set_may_not_replace_the_emitter`
   (`app.emit_event` — the name is not yet in any template, so this proof
   builds a scratch release dir containing a one-line `CREATE FUNCTION
   app.emit_event(` and asserts refusal; Run 3 adds the real template and a
   second arm reading it), `test_the_release_function_names_are_derived_from_
   the_templates` (the set equals `{api.create_note, api.create_task,
   api.update_task_status, api.mcp_agent_context, api.owner_activity_report,
   api.agent_audit_begin, api.agent_audit_complete, app.current_user_id}` —
   an EXACT equality, moved by Run 3 to include `app.emit_event`),
   `test_a_project_rpc_calling_the_emitter_passes` (a definer project function
   whose body is `PERFORM app.emit_event('x.y', 1, '{}'::jsonb);` passes),
   `test_naming_app_private_is_still_refused` (the control). And one proof
   that EVERY committed project set (`projects/*/migrations`) still passes.
4. **Battery** (CLAUDE.md §1's discipline): anchors pre-flighted to match once;
   mutations — delete the rule (the replace proofs must FAIL), narrow the
   regex to `CREATE FUNCTION` only (the `OR REPLACE` arm must FAIL), type the
   set by hand minus `app.current_user_id` (the derivation proof must FAIL);
   control — the unchanged tree green in the same invocation; restore by copy
   and `cmp`.

Targeted: `test_project_migration_sets`, `test_connect_command`,
`test_dev_environment` (`lint_seed` shares the tables), `test_rendered_
migrations`, `test_acceptance_registry`, `test_evidence_claims`. Commit
(`Session 34 Run 2: the tunnel fixture waits for exec; a project set may not
define a release function`), push, CI by full SHA.

**Done.** 2026-09-29. **D1805**: `sleeper.spawn()` polls `ps -o args= -p
<pid>` every 0.05 s until it reads `sleep 300`, bounded 5 s, failing with the
last reading. **D1780**: `migrations.FUNCTION_DDL` + `RELEASE_FUNCTION_SCHEMAS`
+ `release_functions(release)` (derived, manifest order, exactly the plan's
eight: `api.{agent_audit_begin, agent_audit_complete, create_note,
create_task, mcp_agent_context, owner_activity_report, update_task_status}` +
`app.current_user_id`) and ONE rule in `lint_project_set` refusing `defines` /
`alters` / `drops <schema>.<name>, which is the release's function`; the
`DROP VIEW` half kept; the example set passes. Proofs (EVT-LINT-001, in
`test_project_migration_sets.py`): `test_a_project_set_may_not_replace_a_
release_function` (seven arms — the plan's four plus quoted-and-spaced,
`ALTER ROUTINE` without arguments, unqualified; D1818),
`test_a_project_set_may_not_replace_the_emitter` (a scratch release with one
more migration; asserts the derived set picked `app.emit_event` up before the
refusal), `test_the_release_function_names_are_derived_from_the_templates`
(EXACT), `test_a_project_rpc_calling_the_emitter_passes`,
`test_naming_app_private_is_still_refused`,
`test_every_committed_project_set_still_passes`. **Battery 4/4 kills, 0
errors**, control green before and after in the same invocation, restored by
copy and `cmp`: M1 the exec wait removed (killed under a 0.03 s `sleep` shim —
a 0.2 s shim let it SURVIVE, D1817), M2 the rule deleted, M3 narrowed to
`CREATE FUNCTION`, M4 the set typed minus `app.current_user_id`. Targeted,
once: `test_project_migration_sets`, `test_connect_command`,
`test_dev_environment`, `test_rendered_migrations`,
`test_acceptance_registry`, `test_evidence_claims`, `test_api_migrations`,
`test_migrations` — **314 passed**. Rows D1817–D1818. Commit `428bec2`; CI
by full SHA `428bec2ceb6a5946c2ea114de1797d5cf9fb11cb`: `contract` **success**
(run 36618603298).

### Run 3 — migration 0036: the emitter, the outbox, connectors, receipts, the event wait, under a real cluster

**Code. Push, read CI by full SHA.**

**Read first:** `migrations/templates/0035-workflow-gates.sql` WHOLE (the
template this one copies: preamble, comments' voice, `REVOKE`/`GRANT` blocks,
the down block); `0034:320-520`; `migrations/manifest.json:400-432`;
`tests/contract/test_workflow_gates.py:1-200` (the cluster fixture — copy it,
do not import it); `tests/contract/test_migrations.py` (grep
`test_every_granted_function_has_a_caller` — D1680's guard — and the enum
blind spot Session 32 recorded); `tests/contract/test_database_function_
signatures.py:560-640` (ADR 0175's arity guard over `api` and `app_private`
— decide whether it must learn `app`, and if it must, that is a stricter
guard, stated); `services/auth-api/app/workflow_repository.py` whole.

**`migrations/templates/0036-connectivity.sql`**, manifest entry `{version:
"2026MMDD120036", name: "connectivity", template:
"templates/0036-connectivity.sql", placeholders: ["object_owner",
"auth_service"], description: <one paragraph in the house voice naming ADR
0235-0239>}`. `SET LOCAL ROLE {{object_owner}};` … `RESET ROLE;`, down `AP900`.
In order:

1. **Types**: `CREATE TYPE app_private.connector_kind AS ENUM ('outbound',
   'inbound', 'scheduled');` `CREATE TYPE app_private.delivery_status AS ENUM
   ('pending', 'delivered', 'dead');`
2. **`app_private.connector`**: `id uuid PK DEFAULT gen_random_uuid()`, `name
   text NOT NULL UNIQUE CHECK (name ~ '^[a-z][a-z0-9-]{0,62}$')`, `version
   integer NOT NULL CHECK (version BETWEEN 1 AND 9999)`, `kind
   app_private.connector_kind NOT NULL`, `body jsonb NOT NULL` (the compiled
   file, never an endpoint), `source_sha256 text NOT NULL CHECK (source_sha256
   ~ '^[0-9a-f]{64}$')`, `event text CHECK (event IS NULL OR event ~
   '^[a-z][a-z0-9_.]{0,254}@[0-9]{1,3}$')` (outbound), `endpoint text`
   (outbound; per deployment; NEVER returned by any function but the claim),
   `definition_name text`, `definition_version integer` (inbound, scheduled),
   `required_scopes text[] NOT NULL DEFAULT '{}'`, `every_seconds integer
   CHECK (every_seconds IS NULL OR every_seconds BETWEEN 60 AND 86400)`,
   `retry_max integer`, `backoff_seconds integer` (outbound; the D1800
   bounds), `enabled boolean NOT NULL DEFAULT false`, `agent_id uuid
   REFERENCES app_private.agents (id)`, `enabled_by uuid REFERENCES
   app_private.users (id)`, `enabled_at timestamptz`, `next_fire_at
   timestamptz`, `installed_at timestamptz NOT NULL DEFAULT now()`; a CHECK
   tying each kind to its members; a UNIQUE index on `agent_id` WHERE
   `agent_id IS NOT NULL` (one agent, one connector — `agent_already_bound`).
3. **`app_private.connector_event`**: `id`, `name`, `version`, `owner_id uuid
   NOT NULL`, `agent_id uuid` (no FK — the audit's convention, 0019), `payload
   jsonb NOT NULL`, `emitted_at timestamptz NOT NULL DEFAULT now()`.
4. **`app_private.connector_delivery`**: `id`, `event_id uuid NOT NULL
   REFERENCES connector_event`, `connector_id uuid NOT NULL REFERENCES
   connector`, `status app_private.delivery_status NOT NULL DEFAULT 'pending'`,
   `attempts integer NOT NULL DEFAULT 0`, `max_attempts integer NOT NULL CHECK
   (max_attempts BETWEEN 1 AND 11)`, `backoff_seconds integer NOT NULL`,
   `next_attempt_at timestamptz NOT NULL DEFAULT now()`, `claimed_by text`,
   `lease_until timestamptz`, `last_status integer`, `last_error text CHECK
   (last_error IS NULL OR last_error ~ '^(http_[0-9]{3}|timeout|
   connect_failed|tls_failed|dns_failed|unknown)$')`, `rehearsal boolean NOT
   NULL DEFAULT false`, `created_at`, `delivered_at`, `dead_at`; index
   `(status, next_attempt_at)`.
5. **`app_private.connector_receipt`**: `connector_id uuid REFERENCES
   connector`, `delivery_id uuid`, `received_at timestamptz DEFAULT now()`,
   `run_id uuid REFERENCES app_private.workflow_run (id)`, PK `(connector_id,
   delivery_id)`.
6. **`workflow_step`** gains `await_event text CHECK (…same pattern…)`,
   `await_match jsonb`, `await_payload jsonb`, `await_served_at timestamptz`.
7. **No RLS and no grant on the four tables** (ADR 0227's rule, D1647's
   measured reason).
8. **`app.emit_event(p_name text, p_version integer, p_payload jsonb) RETURNS
   uuid`** — D1782's body: `owner := app.current_user_id()`; NULL →
   `RAISE EXCEPTION 'PT401: an event needs an identity' USING ERRCODE =
   'PT401'` (read how 0030/0031 raise their `PT` codes and copy the form
   exactly); name/version/payload checks → `PT422` naming which; `agent :=
   nullif(current_setting('app.agent_id', true), '')::uuid`; the wait UPDATE
   (`SET await_payload = p_payload, await_served_at = now(), resume_after =
   now()` over parked steps with `await_event = p_name || '@' || p_version`,
   `await_served_at IS NULL`, the run `running`, the run's agent's
   `owner_id = owner`, and `p_payload @> await_match`); then the subscribers
   (`enabled AND kind = 'outbound' AND event = … AND endpoint IS NOT NULL`):
   none → `RETURN NULL`; else insert the event and one delivery per
   subscriber (`max_attempts = retry_max + 1`, `backoff_seconds`), return the
   event id. `REVOKE ALL ON FUNCTION app.emit_event(text, integer, jsonb) FROM
   PUBLIC;` and **no GRANT**.
9. **`app_private.connector_install(p_name, p_version, p_kind, p_body,
   p_source_sha256, p_event, p_endpoint, p_definition_name,
   p_definition_version, p_required_scopes, p_every_seconds, p_retry_max,
   p_backoff_seconds) RETURNS text`** — granted to NOBODY (the deploy runs it
   as `postgres`, like `workflow_install_definition`): a new name inserts
   (DISABLED); the same `(name, version, source_sha256)` updates ONLY the
   endpoint and returns `unchanged` or `endpoint_updated`; the same version
   with a different digest raises `PT409` (*publish a new version*); a higher
   version replaces the body, keeps `enabled` FALSE if the kind or the
   definition changed (returns `replaced_disabled`) and otherwise keeps it
   (`replaced`); a lower version raises `PT409`.
10. **`app_private.connector_claim_delivery(p_holder text,
    p_lease_seconds integer)`** → `TABLE(delivery_id uuid, connector_name
    text, endpoint text, rehearsal boolean, event_id uuid, event_name text,
    event_version integer, emitted_at timestamptz, payload jsonb, attempt
    integer, max_attempts integer)`: the oldest `pending` with
    `next_attempt_at <= now()` whose connector is enabled (or `rehearsal`),
    OR a `pending` whose lease expired, `FOR UPDATE OF d SKIP LOCKED LIMIT 1`;
    sets `claimed_by`, `lease_until`, `attempts = attempts + 1`.
11. **`connector_finish_delivery(p_delivery uuid, p_holder text, p_delivered
    boolean, p_status integer, p_error text) RETURNS text`**: `lease_lost`
    unless the holder holds it; delivered → `delivered`; else `attempts >=
    max_attempts` → `dead` (`dead_at`), else `pending` with `next_attempt_at
    = now() + backoff`; clears the lease; returns the new status.
12. **`connector_fire_due(p_holder text) RETURNS integer`**: for each enabled
    scheduled connector with an agent and `next_fire_at <= now()`, `FOR
    UPDATE SKIP LOCKED`: if the agent's stored scopes differ from
    `required_scopes` (D1783's rule, the same comparison `connector_enable`
    makes — ONE helper `app_private.connector_scopes_match(p_agent,
    p_required)` STABLE, called by both, granted to nobody) → set
    `next_fire_at = now() + every_seconds` and enqueue nothing (no row is
    written for the skip; `connector_status` computes `binding:
    "agent_scopes_differ"` on read, so the refusal is reported where an
    operator looks); else
    `app_private.workflow_enqueue(agent, definition_name,
    definition_version, <the compiled input>, false)` and advance. Returns
    the number enqueued.
13. **`connector_inbound(p_name text) RETURNS jsonb`**: `{connector_id,
    body_declaration}` for an installed INBOUND connector, else `PT404:
    no_such_connector`.
14. **`connector_accept(p_name text, p_delivery uuid, p_input jsonb) RETURNS
    uuid`** (the run id): `PT404 no_such_connector`; `PT409
    connector_disabled` (not enabled or no agent); `PT409
    agent_scopes_differ`; `INSERT INTO connector_receipt … ON CONFLICT DO
    NOTHING` and on no row inserted `PT409 delivery_replayed`; then
    `workflow_enqueue(agent, …, p_input, false)` (its own `PT403
    scope_not_held` / `PT404` propagate), and the receipt's `run_id` set —
    all in ONE transaction, so a refused enqueue leaves no receipt.
15. **`connector_enable(p_name text, p_agent uuid, p_user uuid) RETURNS
    text`** and **`connector_disable(p_name text, p_user uuid) RETURNS
    text`**: the refusals of D1783 and D1786 (`no_such_connector`,
    `agent_not_active`, `agent_already_bound`, `agent_scopes_differ`,
    `no_endpoint`, `agent_not_needed` for an outbound given an agent),
    `enabled_by`, `enabled_at`, `next_fire_at = now()` for a schedule; disable
    clears `enabled`, `agent_id`, `next_fire_at`, records `disabled_by`
    (a new nullable column `disabled_by uuid REFERENCES users`, and
    `disabled_at`) and leaves pending deliveries in place (held, not sent —
    the claim requires `enabled`). **`connector_disable` accepts a NULL
    `p_user`** so the trip's cleanup can disable as `postgres` (Run 10); the
    status document reads a NULL `disabled_by` as *"disabled by the
    operator"*.
16. **`connector_status(p_dead_limit integer) RETURNS jsonb`**: per connector
    `{name, version, kind, enabled, agent_id, event, definition, every_seconds,
    next_fire_at, deliveries: {pending, delivered, dead}, oldest_pending_age_
    seconds, last_error, receipts, binding: "ok"|"agent_scopes_differ"|
    "unbound", dead_letters: [{delivery_id, event, attempts, last_error,
    dead_at}] (≤ p_dead_limit, 1..20)}` — **never `endpoint`, `payload` or
    `body`**.
17. **`connector_rehearse_delivery(p_connector text) RETURNS uuid`** — granted
    to NOBODY: one event `apg.rehearsal@1` with payload `{"rehearsal": true}`
    and one delivery `rehearsal = true`, `max_attempts 3`, `backoff_seconds 2`
    for the named installed outbound connector.
18. **`workflow_await_event(p_step uuid, p_holder text, p_event text,
    p_match jsonb, p_resume_after timestamptz) RETURNS text`**: holder check
    (`lease_lost`); sets `await_event`, `await_match`, parks with reason
    `awaiting_event` (appending the `parked` attempt row exactly as
    `workflow_park` does — call it, do not copy it).
19. **Replaced in place, signatures unchanged**: `workflow_gate_state`
    (0035's body + `"event": CASE WHEN s.await_event IS NULL THEN NULL ELSE
    jsonb_build_object('served', s.await_served_at IS NOT NULL, 'payload',
    s.await_payload) END`), `workflow_counts` (0035's body +
    `deliveries_pending`, `deliveries_dead`, `oldest_pending_delivery_age_
    seconds`, `connectors_enabled`). A rig step (below) reads
    `pg_get_function_identity_arguments` and `pg_get_function_result` for both
    before and after.
20. **Grants**: `REVOKE ALL … FROM PUBLIC` on every new function; `GRANT
    EXECUTE` to `{{auth_service}}` on `connector_claim_delivery`,
    `connector_finish_delivery`, `connector_fire_due`, `connector_inbound`,
    `connector_accept`, `connector_enable`, `connector_disable`,
    `connector_status`, `workflow_await_event`; to NOBODY on
    `app.emit_event`, `connector_install`, `connector_rehearse_delivery`,
    `connector_scopes_match`.

**D1680 — every granted function ships its caller in THIS commit.** A new
`services/auth-api/app/connector_repository.py` (`ConnectorRepository(pool)`,
one method per granted connector function, each ONE autocommit `SELECT
app_private.<fn>(%s, …)` with parameters, the shape of
`workflow_repository.py:24-28`), and `WorkflowRepository.await_event(...)`
beside `park`. `test_every_granted_function_has_a_caller` is the guard; run it.

**The rig inside the run** (`/tmp/rig34e.sh`): apply 35 migrations, read the
two replaced functions' identity arguments and result types, apply 0036,
read again → equal (paste both in the Done).

**Proofs** — a new module `tests/contract/test_connectivity_substrate.py`
(`pytestmark` first: `[pytest.mark.p0, pytest.mark.requires_docker]` — copy
`test_workflow_gates.py`'s exact list), fixture copied from
`test_workflow_gates.py`, with a helper that runs a statement as a named role
with `app.user_id`/`app.agent_id` set (`SET LOCAL ROLE …; SELECT set_config(
'app.user_id', …, true)`), and a scratch definer RPC created as the owner that
calls the emitter (the project's shape): EVT-EMIT-001's eleven, EVT-WAIT-001's
`test_gate_state_reports_the_event`, CONN-SCHED-001's three
(`test_a_due_schedule_fires_once_and_advances`, `test_missed_fires_coalesce_
to_one` — set `next_fire_at` 10 × `every_seconds` in the past, fire once, one
run; `test_a_disabled_or_unbound_schedule_fires_nothing`), plus the substrate
halves of CONN-IN-001 and CONN-ADMIN-001 (accept's four refusals and its one
transaction; enable's six refusals; status carries no `endpoint`, `payload` or
`body` key at any depth — a recursive key walk). `test_migrations.py`'s 0036
arms (the grant list, `REVOKE` before `GRANT`, the down). Update
`test_project_migration_sets.py::test_the_release_function_names_are_derived_
from_the_templates` to include `app.emit_event` (a larger exact set) and add
the emitter arm that reads the real template.

**Battery** (≥ 8 mutations, each with a control in the same invocation):
grant `app.emit_event` to `{{auth_service}}` (the no-role proof FAILS); drop
the owner condition from the wait UPDATE (the same-owner proof FAILS); drop
`enabled` from the subscriber query (the disabled proof FAILS); return an id
when nothing listens (the NULL proof FAILS); make `connector_accept` insert
the receipt AFTER the enqueue without the single transaction (the
refused-enqueue-leaves-no-receipt proof FAILS); remove coalescing (the
coalesce proof FAILS); add `endpoint` to `connector_status` (the key-walk
FAILS); remove the scope equality from `connector_fire_due` (a widened-agent
proof FAILS). Assert each FAILED, not ERROR.

Re-render both example projects (D1678), `bin/migrate.sh freeze-lock`
(`bin/migrate.sh --help` for the exact form), commit the lock.
Targeted (fast): `test_migrations`, `test_rendered_migrations`,
`test_project_migration_sets`, `test_database_function_signatures`,
`test_acceptance_registry`, `test_evidence_claims`; (Docker, once):
`test_connectivity_substrate`, `test_workflow_gates`,
`test_migrations_apply_as_the_migration_user`, `test_agent_audit_plane`.
Commit (`Session 34 Run 3: migration 0036 -- the emitter, the outbox,
connectors, receipts and the event wait`), push, CI.

**Done.** 2026-09-29. **Migration 0036** (`20260929120036_connectivity`,
`migrations/templates/0036-connectivity.sql`), frozen by `bin/migrate.sh
freeze-lock` (36 migrations): two enums, the four tables (no grant, no RLS),
four nullable `workflow_step` columns and a partial index on unserved waits,
`app.emit_event` (granted to nobody), eleven `app_private` definer functions —
nine granted to `auth_service` (`connector_claim_delivery`,
`connector_finish_delivery`, `connector_fire_due`, `connector_inbound`,
`connector_accept`, `connector_enable`, `connector_disable`,
`connector_status`, `workflow_await_event`), and `connector_install`,
`connector_rehearse_delivery`, `connector_scopes_match` to nobody — and
`workflow_gate_state` / `workflow_counts` replaced in place. Rows D1819–D1823
(`fire_due` takes no holder; the arity guard learns `app`; the 400-character
bound met by an aligned declaration; four tightenings of the sketch; the
battery's M5 in its expressible form). **Rig 34e** (`/tmp/rig34e.py`, the
locked image, 35 migrations then 0036 as `migration_user`): before
`workflow_counts() -> jsonb`, `workflow_gate_state(p_step uuid, p_holder
text) -> jsonb`; after — **identical** (`equal: true`). **Callers shipped
with the grants (D1680)**: `services/auth-api/app/connector_repository.py`
(eight methods, `ClaimedDelivery`) and `WorkflowRepository.await_event`;
`test_every_granted_function_has_a_caller` green. **Proofs**:
`tests/contract/test_connectivity_substrate.py` (NEW, `pytestmark` first) —
**30 passed on the second execution**; the first execution's one failure was
the PROOF's (an unsorted scope array the agents table's `is_scope_set` CHECK
refuses), not the product's. EVT-EMIT-001's eleven (the emitter's
`has_function_privilege` false for eight roles AND its ACL naming the owner
alone AND `42501` for four — D1814), `test_gate_state_reports_the_event`,
CONN-SCHED-001's three, accept's refusals + one transaction + the bound agent,
enable's six refusals + the named scope difference, disable, the status key
walk with three canaries, and the delivery lease (retry to max then dead,
`lease_lost`, the fixed token, a rehearsal's claim never returning the
endpoint). `tests/contract/test_connector_repository.py` (NEW): the nine
grants each called by a named repository, the four nobody-functions reached by
no statement, no formatted statement, placeholders equal to the declarations,
the claim's mapping. `test_migrations.py::test_0036_grants_what_it_names_
and_revokes_every_new_function_first`; `RELEASE_FUNCTIONS` moved to nine with
`app.emit_event` and the emitter proof's real-template arm;
`test_database_function_signatures.py` reads `app`. **Three older exact pins
moved to the new exact shapes** (each a larger equality, found by the targeted
run — question 5): `test_workflow_substrate.py` 35 → 36 applied versions and
the counts key set +4, `test_workflow_gates.py`'s gate-state equality `+
"event": None`. **Battery 10/10 kills, 0 errors**, control green before and
after in the same invocation, restored by copy and `cmp`: the emitter granted
to `auth_service`; the owner condition dropped; `enabled` dropped from the
subscriber INSERT; an id returned when nothing listens; accept's enqueue
swallowed (D1823); no coalescing; `endpoint` in the status; the scope equality
dropped from `fire_due`; and from `accept`; a rehearsal's claim returning the
endpoint. Both example projects re-rendered (D1678). Targeted, once:
`test_migrations`, `test_rendered_migrations`, `test_project_migration_sets`,
`test_database_function_signatures`, `test_acceptance_registry`,
`test_evidence_claims`, `test_workflow_repository`,
`test_connector_repository`, `test_auth_service_shape`,
`test_connectivity_substrate`, `test_workflow_gates`,
`test_workflow_substrate`, `test_migration_ledger`, `test_agent_audit_plane` —
408 passed, 3 failed (the three pins above); the two failing modules re-run
alone: **56 passed**. Commit `455835d`; CI by full SHA
`455835d82807431f1f5c204796b9dc6fae78a94a`: `contract` **success** (run
36622046896).

### Run 4 — the facility: manifest 7, outputs 19, the secret, the two key derivations

**Code. Push, read CI by full SHA.**

**Read first:** `schemas/project.schema.json:1-40` and `:760-918` (the
version gates — copy the v6 gate at `:894-917` for v7);
`src/agentic_postgres/config.py:55-90`, `:410-440`, `:1059-1190`;
`secrets.required.yaml:930-1015` (the facility's existing entries and the
comment at `:942` on why a facility and not `required: false`);
`secrets_contract.py:60-215`, `:600-660`; `bin/render-secret-override.py`
whole; `output_migrations.py:1288-1380` (`migrate_v16_to_v17`,
`migrate_v17_to_v18`) and every caller of `migrate_v17_to_v18` (grep it — the
new step goes beside it in each); `deployed_output.py:30-60`;
`schemas/outputs.schema.json:30-45`, `:320-335`, `:2060-2080`;
`rendering.py:340-470`; `compose.yaml:1182-1334` (auth's environment and
volumes — find the container path the auth consumer directory is mounted at:
CLAUDE.md §2 says beta's auth mounts `/secrets/beta-dev/generations/<gen>/
auth/`); `services/auth-api/app/settings.py:440-560`;
`tests/contract/test_secret_contract.py` (both directions),
`test_output_migrations.py:540-660`, `test_render_isolation.py:87-300`.

1. **Manifest schema 7**: `schema_version` enum 1..7; the property
   `connectors: {type: object, additionalProperties: false, properties:
   {enabled: {type: boolean}, endpoints: {type: object, propertyNames:
   {pattern: "^[a-z][a-z0-9-]{0,62}$"}, additionalProperties: {type: string,
   pattern: "^https?://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~/-]*)?$",
   maxLength: 512}}}}` with a description in the file's voice; the allOf gate
   *forbidden below 7*; `config.PROJECT_CONNECTORS_FROM = 7` beside `:71`;
   `SUPPORTED_PROJECT_SCHEMA_VERSIONS` widened; **`config.connectors_enabled(
   document) -> bool`** (the one reader; a manifest and a document carry the
   block at the same place) and `config.connector_endpoints(manifest) ->
   dict[str, str]` (manifest only — the document never carries endpoints).
2. **Outputs 19**: both branches gain `connectors: {type: object,
   additionalProperties: false, required: [enabled], properties: {enabled:
   {type: boolean}}}`, required at 19; `deployed_output.SCHEMA_VERSION = 19`;
   the renderer writes `{"enabled": config.connectors_enabled(project)}`;
   `output_migrations.migrate_v18_to_v19(document)` adds `{"enabled": False}`
   to whichever branch the document is, copying `migrate_v17_to_v18`'s shape
   and proofs; every caller of the chain gains the step. **Re-render every
   committed fixture document the tests read** (grep `"schema_version": 18` in
   `tests/fixtures/` and `contracts/`; each is either re-rendered by its own
   command or migrated by a proof — read before touching).
3. **The facility**: `secrets_contract.FACILITY_CONNECTORS = "connectors"`,
   `FACILITIES = (FACILITY_BACKUP_MIRROR, FACILITY_CONNECTORS)`;
   `enabled_facilities` adds it when `config.connectors_enabled(document)`;
   the secret entry of D1784 appended to `secrets.required.yaml` under a
   comment block in the file's voice (Session 34; why a facility; why derived
   keys; who holds a derived key; the rotation's consequence).
4. **The service's reader**: `settings.py` gains `connector_key_file:
   Path | None` from `APG_CONNECTOR_KEY_FILE` (OPTIONAL — absent on a
   deployment without the facility), in `auth` mode only;
   `FORBIDDEN_VARIABLES` gains it for `storage` and `mcp` (the plane holds no
   credential); `compose.yaml`'s auth environment gains
   `APG_CONNECTOR_KEY_FILE: <the consumer directory's container path>/
   connector_signing_key`. `render-secret-override.py` already mounts the
   whole consumer directory — **measure, do not assume**: render beta-shaped
   with the facility on and off (a tmp schema-7 manifest) and diff the
   override; if the mount is per FILE, the facility-gated consumer must be
   emitted only with the facility (ADR 0188's consumer gating, `secrets_
   contract.py:175-190`).
5. **The two derivations**: `src/agentic_postgres/connector_keys.py`
   (`derive(master_hex: str, name: str) -> str`, `CONNECTOR_KEY_LABEL =
   b"apg-connector-key-v1\x00"`, `NAME = re.compile(r"^[a-z][a-z0-9-]{0,62}$")`,
   refuses a bad name or a master that is not 64+ lowercase hex) and
   `services/auth-api/app/connector_signature.py` (`derive` — the same text;
   `sign(key_hex, t, delivery_id, body) -> str`; `header(t, digest) -> str`;
   `parse(header_value) -> (t, digest) | None`; `verify(key_hex, header_value,
   delivery_id, body, *, now) -> bool` with `TIMESTAMP_TOLERANCE_SECONDS =
   300` and `hmac.compare_digest`). `connector_signature.py` imports `hmac`
   and `hashlib` — NOT transports; `test_every_transport_in_the_service_is_
   declared_with_a_reason` must stay green without a row for it.
6. **Proofs** — `tests/contract/test_connector_facility.py` (CONN-FAC-001's
   six) and `test_output_migrations.py::test_v18_to_v19_adds_connectors_
   disabled`; `test_the_two_key_derivations_agree` loads the service module
   with `service_source.load("connector_signature")` (the tree's way to import
   a service module in a proof — grep it) and compares both on ten fixed
   vectors AND on rig 34b's vector; `test_a_project_without_the_facility_
   requires_nothing_new` renders `project.example.yaml` and
   `project.second.example.yaml` and asserts `required_names` has no
   `connector_signing_key`; `test_a_project_with_the_facility_requires_the_
   key` renders a tmp schema-7 manifest.
7. **Battery**: gate the secret on nothing (`facility` removed — the without
   proof FAILS); read the facility from the manifest only (a document-reading
   caller's proof FAILS — write one that calls `enabled_facilities` on a
   rendered v19 document); change one byte of the label in ONE derivation (the
   agreement FAILS); widen the endpoint pattern to admit `?` (the credential
   proof FAILS).

Targeted (fast): `test_connector_facility`, `test_output_migrations`,
`test_secret_contract`, `test_render_isolation`, `test_evidence_collisions`,
`test_project_manifest*` (grep), `test_auth_service_shape`,
`test_rendered_migrations`, `test_upgrade_plan` (grep), `test_node_restore`
(grep), `test_dr_kit` (grep); re-render both examples. Commit (`Session 34
Run 4: the connectors facility -- manifest 7, outputs 19, one gated secret,
two derivations held together`), push, CI.

**Done.** 2026-09-30. **Project manifest schema 7** (`connectors: {enabled,
endpoints}`, endpoints `^https?://host(:port)?(/path)?$` — no userinfo, query
or fragment; the version-7 gate forbids the block below 7);
`config.PROJECT_CONNECTORS_FROM = 7`, `SUPPORTED_PROJECT_SCHEMA_VERSIONS`
1..7, **`config.connectors_enabled(document)`** (the one reader, manifest and
document at the same place) and `config.connector_endpoints(manifest)`. Both
example manifests at 7 without the facility (D1824). **Outputs 19**:
`connectors: {enabled}` on both branches (`$defs/connectorsFacility`),
written by the renderer from the manifest and carried whole to the deployed
document; `deployed_output.SCHEMA_VERSION = 19`, `CURRENT_VERSION = 19`,
`output_migrations.migrate_v18_to_v19` (`{"enabled": false}`, no argument,
`NO_CONNECTORS`) chained in `migrate_rendered` and `outputs_chain.STEPS`.
**The facility**: `secrets_contract.FACILITY_CONNECTORS`, `enabled_facilities`
reads it through `connectors_enabled`; `connector_signing_key` appended to
`secrets.required.yaml` with its comment block (why a facility, who holds a
derived key, the rotation's consequence); the contract schema's
`introduced_in_session` cap 18 → 34 (D1826). **The service's reader**:
`APG_CONNECTOR_KEY_FILE` required as a path, optional as a file (D1827);
**item 4's measurement** — the override mounts `connector_signing_key` per
file, into `auth` ALONE with the facility and nowhere without it.
**`services/auth-api/app/connector_signature.py`** (`derive`, `signed_bytes`,
`sign`, `header`, `parse`, `verify`, `TIMESTAMP_TOLERANCE_SECONDS = 300`,
`hmac.compare_digest`; no transport); the host copy moved to Run 7 with its
caller (D1828). **Measured: `RENDER_SESSION = 2`**, so no post-Session-2
secret ever reaches a rendered `required_names` — D1784's pricing premise was
false and the gate matters at deploy step 0 instead (D1825). **Proofs**:
`tests/contract/test_connector_facility.py` (NEW, `pytestmark` first) — schema
7 admits / 6 forbids, six endpoint refusals with the sink's address as the
control, the one reader over a manifest and a v19 rendered document, nothing
owed without the facility (both renders' `required_names` AND step 0's set at
34), exactly `connector_signing_key` owed with it and mounted into `auth`
alone, the derivation against an independent HMAC on ten vectors and `sign`
against rig 34b's `3c87822a…`, and the refusals carrying no value;
`test_output_migrations.py` gains a `v18` fixture and four v19 proofs; three
version pins moved (D1829). **Battery 4/4 kills**, control green before and
after: the secret gated on nothing; the facility read from a manifest only;
one byte of the label in the image's derivation; the endpoint pattern
admitting a query. Targeted, once: `test_connector_facility`,
`test_output_migrations`, `test_project_manifest`, `test_secret_contract`,
`test_auth_service_shape` (504 passed after D1826/D1829's repairs), then
`test_render_isolation`, `test_evidence_*`, `test_upgrade_plan*`,
`test_node_restore*`, `test_dr_kit*`, `test_rendered_migrations`,
`test_acceptance_registry`, `test_evidence_claims`, `test_secret_origin`,
`test_secret_generation_manifest`, `test_repository_contract`,
`test_capability_compiler`, `test_backup_plane`, `test_deploy_project*`,
`test_workflow_worker` and others — 616 passed, 2 failed (the matrix, the
orphan module); the three modules re-run after the repairs: **274 passed**.
Bounds doc unchanged. Rows D1824–D1830. **CI on `5005c37…` (`5005c37576f1dd040e7eecaba309123e729eee40`): `contract` FAILURE** (run 36623650516) — seven modules outside the targeted list (D1830), repaired in the next commit, `0e5335a`; CI by full SHA
`0e5335a756bf5163bc643aa34b401d7e3f329bad`: `contract` **success** (run
36626102633). **Run 4 is done. NEXT FREE: D1831, ADR 0240.** The executor
stopped here at the operator's request (2026-09-30); Run 5 starts from its
*Read first* list.

### Run 5 — the definitions: connector files, the event wait, the example set, step 6e and `apg dev`

**Code. Push, read CI by full SHA.**

**Read first:** `src/agentic_postgres/workflow_definition.py` whole (1,018
lines — the compiler this run copies and widens); `schemas/workflow.schema.
json` whole; `src/agentic_postgres/workflow_install.py` whole;
`bin/deploy-project.py:860-945` and `:2440-2470`; `bin/dev.py:430-520`;
`projects/example/workflows/*.yaml`; `projects/example/migrations/manifest.
json` and `released.lock.json`; `docs/migrations.md` (the project-set order,
ADR 0206 — the version rule for `0003`); `tests/contract/
test_workflow_definition.py:700-760`; `test_dev_environment_cluster.py:
180-250`.

1. **The event wait** (`workflow_definition.py`, `workflow.schema.json`):
   `wait` gains `match: {type: object, maxProperties: 8, additionalProperties:
   {oneOf: [string, integer, boolean]}}`; `event` gains a pattern
   `^[a-z][a-z0-9_]{0,62}(\.[a-z][a-z0-9_]{0,62}){0,3}@[1-9][0-9]{0,2}$`; the
   `:175` description rewritten (Session 34; ADR 0239). `_compile_wait`: the
   refusal at `:793-798` is REMOVED; an event wait requires `seconds` (the
   maximum wait, same bounds) and compiles to `{name, kind: "wait", seconds,
   event, match, timeout_seconds: 5, retry: {0, 1}}`; a `match` value that is
   a string containing `{{` must be ONE whole reference to `input.<k>` or an
   EARLIER step (reuse `_check_references`'s rules at `:625-659`); `match`
   without `event` is refused. **Delete `test_a_wait_on_an_event_is_refused_
   naming_session_thirty_four`** (ADR 0239) and add EVT-WAIT-001's four
   compiler proofs.
2. **The connector compiler** — `schemas/connector.schema.json` and
   `src/agentic_postgres/connector_definition.py` (`CONNECTORS_SUBDIR =
   "connectors"`, `connectors_of(project_set_root)`, `load`, `compile(
   document, lock, definitions, *, source_sha256)`, `check_body(declaration,
   body) -> str | None` (the host's reference validator, D1787),
   `CompiledConnector` with `as_install()`), the file shape:

   ```yaml
   schema_version: 1
   name: note-embedded            # ^[a-z][a-z0-9-]{0,62}$
   version: 1
   description: "…"
   kind: outbound                 # outbound | inbound | scheduled
   event: note_embedding.set@1    # outbound only
   retry: {max: 3, backoff_seconds: 5}   # outbound only; max 0..10, backoff 1..3600
   # inbound:   workflow: notes-inbox@1
   #            body: {members: {title: {type: string, required: true, max_length: 200},
   #                             content: {type: string, required: false, max_length: 4000}}}
   # scheduled: workflow: notes-digest@1
   #            schedule: {every_seconds: 3600}
   #            input: {limit: 1}            # literals only
   ```

   Refusals, each naming the file and the member: an unknown kind; a member
   of another kind; an event without a version; a `workflow` that names no
   definition in the SAME set's `workflows/` at that version; an inbound body
   declaring a member the definition's steps never reference as `{{input.<m>}}`
   and a definition referencing an `input.<k>` the body does not declare
   (both directions — the body IS the run's input); a scheduled `input` that
   is not literals or does not cover the definition's input references; more
   than 16 body members. The compiled form records the definition's
   `required_scopes` (compile the definition with the workflow compiler; never
   re-derive scopes).
3. **The service's validator** — `services/auth-api/app/connector_body.py`
   (`check(declaration: dict, body: dict) -> str | None`, ~60 lines, no
   dependency beyond the standard library) and the two-reader proof
   `test_the_two_body_validators_agree` over twelve cases (missing required,
   extra member, wrong type ×3, string too long, integer out of range, bool
   given as `"true"`, empty body with nothing required, nested object, list,
   exactly at the bound).
4. **The example set** (`projects/example/`):
   - `migrations/templates/0003-note-embedding-events.sql` (D1781): the
     preamble, `CREATE OR REPLACE FUNCTION api.set_note_embedding(p_note_id
     uuid, p_embedding extensions.vector)` with 0001's body copied
     BYTE-FOR-BYTE and the one `PERFORM app.emit_event(…)` line after the
     upsert, the same `SET search_path`, the grants re-stated only if
     `CREATE OR REPLACE` drops them (it does not — measure with
     `has_function_privilege` in the proof, never assume), `NOTIFY pgrst`,
     the down `AP900`. Manifest entry (version: the rule in `docs/
     migrations.md`), placeholders `["object_owner"]` only if nothing else is
     named. `bin/migrate.sh freeze-lock --project project.example.yaml`.
     The project's `contracts/postgrest-api-surface.yaml` and its OpenAPI
     snapshot do NOT move (same signature) — `bin/api-contract.sh --check
     --project …` proves it.
   - `workflows/notes-inbox.yaml` — one step `create` calling
     `create_note@1.0.0` with `p_title: "{{input.title}}"`, `p_content:
     "{{input.content}}"`.
   - `workflows/notes-digest.yaml` — one read step over `query_notes@1.0.0`
     (`columns: [id]`, `limit: "{{input.limit}}"` — or a literal if a relation
     read's `limit` cannot take a reference; the compiler decides, say which).
   - `workflows/notes-await-embedding.yaml` — `create` (`create_note@1.0.0`
     from `{{input.title}}`), `embedded` (`wait: {event: note_embedding.set@1,
     match: {note_id: "{{steps.create.row.id}}"}, seconds: 300}`), `timeout_
     seconds: 600`.
   - `connectors/note-embedded.yaml` (outbound, `note_embedding.set@1`,
     `retry {max: 2, backoff_seconds: 2}`), `connectors/notes-deadletter.yaml`
     (outbound, same event, the same retry — its endpoint is the sink's
     `/fail`), `connectors/notes-inbox.yaml` (inbound, `notes-inbox@1`, the
     body of item 2), `connectors/notes-digest.yaml` (scheduled,
     `notes-digest@1`, `every_seconds: 60`, `input: {limit: 1}`).
5. **Step 6e** in `bin/deploy-project.py`, directly after 6d (`:2452-2459`),
   inside step 6's guard, `step("6e. Install the project's connectors")`, a
   function `install_connectors(*, release, manifest_path, lock_path,
   database)` in 6d's exact shape: the INSTALLED manifest; *"no connectors
   (the project declares no migration set)"*; *"no connectors (the manifest's
   connectors.enabled is false)"*; *"no connectors (the project declares
   none)"*; compile each against the lock this deploy wrote and the set's
   definitions (a failure exits 5 naming the file); an outbound connector
   whose endpoint is missing from the manifest installs WITHOUT one and the
   line says *"no endpoint in the manifest; `enable` will refuse it"* (a
   report, not a refusal — ADR 0195's decision/report split); each install
   through `container_exec.run(container, "psql", "-U", "postgres", "-d",
   database, *argv, input=INSTALL_SQL, timeout=60)` with `-v` variables and
   `-f -` (a new `connector_install.statements(compiled, endpoint)` beside
   `workflow_install.statements`); the printed line `f"  {path.name:<28}
   {name} v{version}  {kind}  {result}"` where `result` is the function's
   return word. `WORKFLOW_SESSION`'s sibling `CONNECTOR_SESSION = 34`.
6. **`apg dev`**: `bin/dev.py` installs connectors after definitions when
   `config.connectors_enabled(manifest)`, else prints D1808's line; the
   pinned `workflows   4 definition(s) installed` becomes `7`.
7. **Proofs**: `tests/contract/test_connector_definition.py` (CONN-DEF-001's
   eight), `tests/contract/test_deploy_connectors.py` (the reasons and the
   exit 5, over a fake `container_exec` — copy the D1705 proofs' shape from
   Session 33 Run 2; grep `nothing_to_install` in `tests/contract/`),
   `test_workflow_definition.py`'s four, `test_project_migration_sets.py::
   test_the_example_sets_third_migration_keeps_the_signature` (the lint passes
   0003; `CREATE OR REPLACE` keeps `has_function_privilege` for
   `authenticated` and `agent_writer` — under the cluster fixture), the dev
   proof at 7.
8. **Battery**: re-admit the old refusal (the compile proof FAILS); allow a
   later-step reference in `match` (FAILS); let the body declare a member no
   step references (FAILS); drop the facility check in 6e (the reason proof
   FAILS); make the service validator accept an extra member (the agreement
   FAILS).

Targeted (fast): `test_workflow_definition`, `test_connector_definition`,
`test_deploy_connectors`, `test_deploy_project*` (grep), `test_project_
migration_sets`, `test_rendered_migrations`, `test_api_contract*` (grep),
`test_workflow_command` (the example definitions), `test_acceptance_registry`,
`test_evidence_claims`, `test_cli_contract`; (Docker, once):
`test_dev_environment_cluster`, `test_connectivity_substrate`,
`test_project_migration_sets` (its cluster arm). Commit (`Session 34 Run 5:
connector files, the event wait, the example set's events, step 6e`), push,
CI.

**Done.** 2026-09-30. **The event wait** (`workflow_definition.py`,
`workflow.schema.json`): the Session 33 refusal is gone (ADR 0239); `wait:
{event, match, seconds}` compiles to the time wait's body plus `event` and
`match` (a time wait's body is byte-identical to Session 33's); `event` is
`EVENT_REFERENCE` (the emitter's name rule and a version 1..999, schema and
compiler both); `match` holds at most 8 members, each a literal or ONE whole
reference under a step argument's rules; `match` without `event` is refused;
`input_references(compiled)` reads every `{{input.<k>}}` off a compiled
definition (arguments, compensations, matches). **The connector compiler**
(`schemas/connector.schema.json`, `src/agentic_postgres/connector_definition.py`:
`connectors_of`, `load`, `definitions_for`, `compile`, `compile_file`,
`check_body`, `CompiledConnector.body()`/`as_install()`): three kinds, a member
of another kind refused by name, the definition compiled with the workflow
compiler and its `required_scopes` COPIED, definitions from another lock
refused, the body checked in both directions and no optional member (D1831), a
scheduled input literal and exact. **The service's validator**
`services/auth-api/app/connector_body.py` (standard library only) and
`connector_install.py` (one constant statement, thirteen psql variables, a NULL
as an empty variable under `NULLIF`, an endpoint refused for a non-outbound
connector). **The example set**: `0003-note-embedding-events.sql` — **version
`20260930120003`, by ADR 0206's rule: after the set's own newest
(`20260914120002`), in the set's `YYYYMMDD12000N` convention; nothing orders it
against release 0036 and nothing needs to** — 0001's function byte for byte but
`OR REPLACE` and one `PERFORM app.emit_event('note_embedding.set', 1,
{note_id})` directly after the upsert, `object_owner` alone, no grant restated.
**Measured: `freeze-lock --project` without `--follows` exits 5** (0036 sorts
above the set's first two), so the lock is frozen with `--follows
20260912120031` and records `declared` (D1833, **ADR 0240**; the `computed` pin
replaced by a stricter one). `bin/api-contract.sh --check --project
project.example.yaml` exit 0 (*"the committed snapshot matches the reviewed
surface (7 objects)"*) — the project's surface did not move. Three definitions
(`notes-inbox`, `notes-digest` — `limit: "{{input.limit}}"`, which the compiler
ADMITS, the worker resolving it to the integer — and `notes-await-embedding`,
which waits on `{{input.note_id}}` because `{{steps.create.row.id}}` is not a
reference, D1832); `bin/workflow.sh validate --project project.example.yaml`:
7 definitions compile. Four connectors (`note-embedded`, `notes-deadletter`,
`notes-inbox`, `notes-digest`), no endpoint in any file. **Step 6e**
(`install_connectors`, `CONNECTOR_SESSION = 34`, between 6d and 6b): the
facility read before the directory, three reasons, exit 5 naming the file
before any connector reaches the cluster, a missing endpoint and an endpoint
naming no outbound connector each REPORTED, no endpoint printed (D1836).
**`apg dev`** prints `connectors  not enabled (the manifest's
connectors.enabled is false)` for both examples and installs the four,
disabled, with the facility on (D1808). **Proofs**: `test_connector_definition.py`
(NEW, 10) and `test_deploy_connectors.py` (NEW, 7), `pytestmark` first;
`test_workflow_definition.py` loses the Session 34 refusal and gains
EVT-WAIT-001's four; the third-migration proof in two halves (D1834); the
registry moves and renames of D1835; the matrix regenerated. **Battery 5/5
kills, 0 errors**, control green before and after in the same invocation,
restored by copy and `cmp`: the old refusal re-admitted; a later-step
reference allowed in `match`; the body declaring a member no step reads; the
facility check dropped from 6e; the service validator accepting an extra
member. Targeted, once: the five modules the run wrote into — 131 passed —
then `test_workflow_command`, `test_rendered_migrations`, `test_api_*`,
`test_acceptance_registry`, `test_evidence_claims`, `test_cli_contract`,
`test_auth_service_shape`, `test_deploy_project*`, `test_workflow_worker`,
`test_migrations`, `test_documentation_index`, `test_session12_documented_path`
and eleven more: **1383 passed**. Both examples re-rendered (the rendered
document's `project_set.count` is 3). Rows D1831–D1836. `test_the_init_
skeletons_validate` is Run 7's (D1836). (Docker, once): `test_dev_environment_cluster` (10, the grants proof among
them), `test_migrations_apply_as_the_migration_user` (3, the example set now
with `0003` applied as `migration_user`), `test_connectivity_substrate` (30),
`test_deployment_module_shape` and `test_printed_commands` (the D1242 guard) —
**49 passed, 0 skipped**. Commit `f5966cb`; CI by full SHA
`f5966cbf46f25be30916c820837c809e2ee73175`: `contract` **success** (run
36631298892).

### Run 6 — the loop: the delivery pass, the schedule pass, the event wait

**Code. Push, read CI by full SHA.**

**Read first:** `services/auth-api/app/workflow_worker.py` WHOLE (762 lines);
`main.py:91-213`; `workflow_repository.py` whole and Run 3's
`connector_repository.py`; `tests/contract/test_workflow_worker.py` (the fake
repository and fake plane, `:1-200`; `test_the_loop_starts_in_auth_mode_only`
`:805-832`; `test_the_planes_address_is_the_one_the_deploy_publishes`
`:835-855`; `test_a_wait_step_parks_once_then_finishes_and_mints_nothing` —
grep); `tests/contract/test_auth_service_shape.py:680-830`; Run 1's rig 34b
mapping table (the error tokens by MEASURED exception type).

1. **`services/auth-api/app/connector_delivery.py`** (new; its own
   `TRANSPORT_ALLOWLIST` row `{urllib}` with D1791's reason, and joins
   `senders` at `:823`):
   - `DELIVERY_TIMEOUT_SECONDS = 10`; `REHEARSAL_ENDPOINT =
     "http://127.0.0.1:9/"` (D1801); `USER_AGENT =
     "agentic-postgres-connector/1"`.
   - `body(delivery) -> bytes`: `json.dumps({"delivery_id": …, "event": name,
     "version": v, "event_id": …, "emitted_at": iso, "payload": payload},
     sort_keys=True, separators=(",", ":")).encode("utf-8")`.
   - `headers(delivery, key_hex, *, now) -> dict[str, str]`: `Content-Type:
     application/json`, `User-Agent`, `X-Apg-Delivery`, `X-Apg-Event:
     <name>@<version>`, `X-Apg-Signature` from `connector_signature.sign`.
   - `class _Refuse(urllib.request.HTTPRedirectHandler)` whose
     `redirect_request` returns `None`; `_OPENER =
     urllib.request.build_opener(_Refuse)`.
   - `_post(url, headers, body, *, timeout) -> tuple[int | None, str | None]`:
     `(status, None)` on any HTTP response (2xx included), `(None, token)` on
     a transport failure — the token from rig 34b's table, `unknown` for
     anything else. **The ONE place this module reaches a network.** No
     exception text is ever returned, logged or stored.
   - `async def deliver(delivery, *, repository, key_master_hex, holder)`:
     derive the connector's key (`connector_signature.derive`), build body and
     headers, `await asyncio.to_thread(_post, <REHEARSAL_ENDPOINT if
     delivery.rehearsal else delivery.endpoint>, …,
     timeout=DELIVERY_TIMEOUT_SECONDS)`, then `repository.finish_delivery(
     delivery_id, holder, delivered = 200 <= status < 300, status, error)`
     where a non-2xx's error is `f"http_{status:03d}"`. The endpoint is held
     in a local and deleted in a `finally` (the `del token` discipline,
     `workflow_worker.py:560`), and **no log line names it**.
2. **`run_forever`** gains keyword parameters `connectors: Any = None` and
   `connector_key: str | None = None`. Each iteration, in this order:
   heartbeat; claim ONE step and `process` it if any; **if `connectors` and
   `connector_key` are both set**: claim ONE delivery (`lease_seconds =
   DELIVERY_TIMEOUT_SECONDS + lease_margin_seconds()`) and `deliver` it if
   any, then `await connectors.fire_due(holder)`; sleep `POLL_SECONDS` only
   if neither a step nor a delivery was found. Each pass's exceptions are
   caught and logged by pass name inside the iteration so one pass cannot
   stop the other (the supervisor still restarts on anything that escapes).
   `supervise` passes both through. `main.py`'s lifespan builds
   `ConnectorRepository(pool)` and reads the key file ONCE
   (`settings.connector_key_file`; absent → `None`, and a single INFO line
   *"connectors: no key file (the project has not enabled the facility)"*).
   **Still exactly one `create_task`** — `test_the_loop_starts_in_auth_mode_
   only` must pass UNCHANGED.
3. **The event wait** in `_wait` (`:635-659`): if `step.step` has `event`:
   in a dry run finish `dry_run`/*"event waits are not rehearsed"* (the
   approval step's rule); else read `gate_state`; `event` null → resolve
   `match` with `resolve(…, run_input=step.input, prior=step.prior)`
   (`Unresolvable` → finish `failed`/`unresolvable`) and
   `repository.await_event(step_id, holder, event, match, resume_after=now +
   seconds)`; `event.served` → finish `succeeded`, reason `event_received`,
   result `{"event": <name@v>, "payload": <payload>}`; not served (the
   timeout fired the claim) → finish `failed`, reason `event_timeout`. No
   token is minted on any path. The time-only wait is unchanged.
4. **Rig 34f — the loop's first end-to-end connectivity, before a host**
   (`/tmp/rig34f.py`, Session 33's stack + migration 0036 + the example set's
   `0003` + Run 5's definitions and connectors installed through the
   product's own install statements, with a local sink on a rig network):
   (i) enable `note-embedded` (outbound → the sink's `/ok`) by calling
   `connector_enable` as the auth service; a human (an `authenticated` owner
   with `note_embeddings:write`) calls `POST /rpc/set_note_embedding`
   DIRECTLY to PostgREST for a note it owns → the loop (the checkout's `auth`
   mode) delivers ONE POST; the rig verifies its signature with `openssl` over
   the recorded bytes; (ii) `notes-deadletter` → `/fail` → exactly 3 POSTs at
   ≥ 2 s spacing, then `dead`/`http_500`; (iii) a run of
   `notes-await-embedding` as an agent of that owner parks `awaiting_event`;
   the owner's write for THAT note resumes it (`event_received`); control: a
   write for another note leaves it parked; (iv) `notes-digest` enabled with
   a `notes:read`-exact agent (rig 34c's answer applied) fires once within
   `60 + 2 × 5` s; (v) `connector_rehearse_delivery('note-embedded')` →
   3 attempts to `127.0.0.1:9`, `connect_failed`, `dead`, and the heartbeat
   moved throughout. **Control for the whole rig**: with the key file absent
   the loop claims no delivery and fires nothing, and step processing is
   unaffected.
5. **Proofs**: `tests/contract/test_connector_delivery.py` (CONN-OUT-001's
   nine: a local `http.server` thread per proof answering programmed
   statuses; the signature verified by the proof's OWN `hmac` over the
   received bytes; the redirect proof with a 307 server; the lease proof with
   a fake repository that returns the same delivery twice), EVT-WAIT-001's
   four worker proofs and `test_the_loop_fires_due_schedules_each_iteration`
   in `test_workflow_worker.py`, and the allowlist row.
6. **Battery**: follow redirects (the redirect proof FAILS); claim two
   deliveries per iteration (the starvation proof FAILS); store the exception
   text as `last_error` (the token proof FAILS); log the endpoint (the
   no-record proof's log capture FAILS); mint a token for an event wait (the
   no-token proof FAILS); make the event wait ignore `served` (FAILS).

Targeted (fast): `test_workflow_worker`, `test_connector_delivery`,
`test_auth_service_shape`, `test_workflow_repository` (grep),
`test_acceptance_registry`, `test_evidence_claims`. Commit (`Session 34 Run
6: the loop delivers, fires and resumes on an event`), push, CI.

**Done.** 2026-09-30. **`services/auth-api/app/connector_delivery.py`**
(NEW; `DELIVERY_TIMEOUT_SECONDS = 10`, `REHEARSAL_ENDPOINT`, `USER_AGENT`,
`body`, `headers`, `error_token`, `_post`, `deliver`): the canonical body, the
three `X-Apg-*` headers signed by `connector_signature`, an opener whose
`_Refuse` handler follows no redirect, only `http(s)` opened, D1813's table as
written (a DNS failure recognised by its class NAME, `gaierror`, because
`socket` is a transport this service does not grant), the endpoint deleted in
a `finally`, no exception text leaving `_post`. Its own `TRANSPORT_ALLOWLIST`
row and a place among the senders, now four (D1791). **The loop**:
`run_forever(…, connectors, connector_key)` -- per iteration one step, then
(only with both) one delivery and one `fire_due`, sleeping only when neither a
step nor a delivery was found; each connector pass logged by its NAME and
exception TYPE only; `supervise` passes both; `main.py` builds
`ConnectorRepository` and reads the key ONCE through
`connector_signature.read_master` (no file → `None`; a present malformed file
fails the start naming no value) -- **still one `create_task`**. **The event
wait** (`_await_event`): a rehearsal finishes `dry_run`; nothing parked → the
match resolved once (`Unresolvable` → `failed`) and `await_event` until
`seconds`; served → `succeeded`/`event_received` with `{event, payload}`;
otherwise `failed`/`event_timeout`; no token on any path. **Rig 34f**
(`/tmp/rig34f/rig34f.py`, derived from rig34.py's stack: `apg dev up` -- 36
release migrations, the set's three, 7 definitions -- the four connectors
installed through `connector_install.statements` with the outbound endpoints
on a sink the rig serves, PostgREST from the pinned digest, the auth
application from the checkout; exit 0): **control** (no key file) -- after 12 s
the sink had received 0 requests, both deliveries `pending` at 0 attempts, 0
`notes-digest` runs, and a `notes-await-embedding` run's wait step still
parked `awaiting_event` (steps unaffected); the INFO line was not in the log
(D1837). **With the key** (a restart): **(i)** ONE POST to `/ok`, `delivered`
at attempt 1 status 200, its signature verified by `openssl dgst -sha256 -mac
HMAC` over the received bytes under a key the rig derived itself, and no line
of the auth log carried the sink's URL; **(ii)** `/fail` received exactly 3
POSTs under one delivery id, **5.06 s and 5.09 s apart** (D1838), then `dead`,
3 attempts, `last_status` 500, `http_500`; **(iii)** a write for ANOTHER note
left the run parked (`awaiting_event` after 12 s); the owner's write for its
own note finished the wait **2.0 s later** `succeeded`/`event_received` with
`{event: note_embedding.set@1, payload: {note_id: <that note>}}` (the run then
failed at its `record` step, `transport: URLError` -- the rig starts no plane,
by design); **(iv)** `notes-digest`, bound to a `notes:read`-exact agent (rig
34c's answer), fired ONE run as that agent 0.05 s after the new worker
started and set `next_fire_at` 60 s on; **(v)**
`connector_rehearse_delivery('note-embedded')` → 3 attempts, `connect_failed`,
`dead`, the heartbeat's `seen_at` moving 21:19:30 → 21:19:45 throughout.
**Proofs**: `tests/contract/test_connector_delivery.py` (NEW, 10, a real
`http.server` per proof; the signature verified by the proof's own HMAC; every
redirect code; a real refused port and a real read timeout),
`test_workflow_worker.py` gains EVT-WAIT-001's four and
`test_the_loop_fires_due_schedules_each_iteration`, the allowlist row.
**Battery 6/6 kills, 0 errors**, control green before and after: redirects
followed; two deliveries per iteration; the exception text stored; the
exception logged; a token minted for a wait; `served` ignored. **The battery's
first reading was wrong and the reader was:** `-rA` prints the no-record
proof's captured `ERROR` log line, which the outcome regex counted as a
seventh node; the regex now requires `::` and the re-run is the record.
Targeted, once: `test_workflow_worker`, `test_connector_delivery`,
`test_auth_service_shape` (89), then with `test_workflow_repository`,
`test_connector_repository`, `test_acceptance_registry`,
`test_evidence_claims`, `test_auth_endpoints`, `test_studio_runtime`,
`test_connector_facility`, `test_workflow_routes`,
`test_workflow_admin_routes` and the D1242 guards: **346 passed**. Rows
D1837–D1838. Commit `ca75ad0`; CI by full SHA
`ca75ad05585fb7293a0fb90a51048c4ff0fc7e69`: `contract` **success** (run
36704677704). **Run 6 is done. NEXT FREE: D1839, ADR 0241.** The executor
stopped here at the operator's request (2026-09-30); Run 7 starts from its
*Read first* list.

### Run 7 — the routes, the scopes and the command

**Code. Push, read CI by full SHA.**

**Read first:** `services/auth-api/app/workflow_admin_routes.py` whole (the
model for the admin routes: `_admin` `:189-193`, `_translate` `:174-186`,
`_admin_guard` `:196-211`); `workflow_routes.py:120-201` (the translation of
`PT` codes — and the ORDER the inbound route must NOT copy, `:179-181`);
`routes.py:300-330`, `:456-512`; `strict_json.py` whole; `main.py:296-310`,
`:405-490`; `scopes.py` whole; `schemas/capabilities.schema.json:230-290`;
`tests/contract/test_workflow_admin_routes.py` (the real-`AuthService`
proof shape Session 33 used); `bin/workflow.py` and `bin/workflow.sh` whole;
`tests/contract/test_workflow_command.py` whole.

1. **Scopes** (D1796): `admin_connectors:read` and `admin_connectors:write`
   appended to BOTH enums in `capabilities.schema.json` (the description's
   last sentence extended: *"… `admin_connectors:read|write` joined in Session
   34 (ADR 0236)"*); `ADMIN_CONNECTORS_READ`/`ADMIN_CONNECTORS_WRITE` in
   `scopes.py`; the six pinning proofs moved to the new exact sets;
   `capability_compiler`'s vocabulary picks them up from the schema (read,
   do not assume — `scope_registry.administrative_scopes()` `:98-109`);
   regenerate every committed lock the tests compare (`bin/mcp-contract.sh
   lock` / `check` — `--help` first).
2. **`services/auth-api/app/connector_routes.py`** — `router =
   APIRouter()`, `POST /connectors/{name}`, `status_code=202`, **no
   `Depends` on an authenticator**, body read as `raw = await
   request.body()`, the order of D1789 exactly, each refusal a fixed
   `JSONResponse` (`{"error": "<word>"}` plus `"member"` for
   `body_not_permitted`), the key master read from `request.app.state` (set
   by the lifespan from Run 6's read — the SAME value the loop holds), the
   declaration from `ConnectorRepository.inbound(name)` (`PT404` →
   404 `no_such_connector`), `connector_body.check` → 422, then
   `ConnectorRepository.accept(name, delivery_id, body)` → 202 `{"run_id":
   …, "status": "queued"}`, `PT409` words mapped by the function's own
   message to 409 `delivery_replayed` / `connector_disabled` /
   `agent_scopes_differ`, `PT403 scope_not_held` → 409 `agent_scopes_differ`
   (the agent lost a scope after binding). The route writes ONE structured
   log line per request through the existing `StructuredRequestLog` only (no
   body, no header value) — read that middleware to confirm what it records.
   OpenAPI: `include_in_schema=True` with a request body described as
   `application/json` object and the 202/400/401/404/409/413/422 responses
   (read `openapi_docs.prune_unreachable_validation_errors`, `main.py:
   322-327`, for what it prunes).
3. **`services/auth-api/app/connector_admin_routes.py`** — `GET
   /admin/connectors` (`admin_connectors:read`, query `dead_limit` 1..20
   default 20 through `strict_query`), `POST /admin/connectors/{name}/enable`
   (`admin_connectors:write`, body `{"agent_id": uuid | null}`) and
   `POST /admin/connectors/{name}/disable` (`admin_connectors:write`, empty
   body), each `authenticate` + `require_scope` BEFORE the body is parsed,
   `user_id=principal.user_id` passed to the definer; refusals as fixed
   documents (`no_such_connector` 404; `agent_not_active`,
   `agent_already_bound`, `agent_scopes_differ`, `no_endpoint`,
   `agent_not_needed`, `agent_required` 409).
4. **Mounting**: both routers in `main.py`'s `auth` branch beside `:305`,
   `:310`; `public_paths()` gains `/admin/connectors`,
   `/admin/connectors/{name}/disable`, `/admin/connectors/{name}/enable`,
   `/connectors/{name}` in its sorted order; `bin/app-contract.sh --update`
   then `--check`; **`bin/apg.sh generate --project project.example.yaml`**
   and `--check` (D1690), then `test_client_typescript`,
   `test_generate_command`, `test_studio_command`, `test_client_ir`. Studio
   forwards NONE of the new routes (its seven are closed — `bin/studio.py`;
   a proof that the forwarder's set is unchanged already exists, run it).
5. **`bin/connector.py` + `bin/connector.sh`** (ADR 0093: imports only
   `agentic_postgres` and `yaml`; `git add` both BEFORE running
   `test_cli_contract`, D1188), copying `bin/workflow.*`'s shape: exit codes
   0/2/3/5 (+ 4 for `key` when not root or no generation — read how other
   root-only commands exit, e.g. `bin/doctor.py` `EXIT_STATE`); `HTTP_VERBS =
   ("status", "enable", "disable")` with `ROUTES`; `TOKEN_VARIABLE =
   "APG_API_TOKEN"`; `enable`/`disable` require `--name N --confirm N` (exit 2
   on mismatch) and `enable` takes `--agent UUID` (inbound, scheduled);
   `status` prints the document whole (no summary — ADR 0195) and exits 5 on
   a status ≥ 400 with the service's `error` word; `init --kind
   outbound|inbound|scheduled` prints a skeleton that validates; `validate
   --project FILE [--file PATH]` compiles every `connectors/*.yaml` of the
   set against the offline lock (`workflow_definition.lock_view_for_project`)
   and the set's definitions, holding the report until all compile (D1403),
   printing `N connector(s) compile against this project's lock and
   definitions`; `key --project FILE --name N --output FILE` (root; D1804).
   `SHELL_COMMANDS`, `PYTHON_COMMANDS`, `COMMANDS_WITH_VERBS` gain them.
6. **Proofs**: `tests/contract/test_connector_routes.py` (CONN-IN-001's ten
   over `create_app("auth")` with a fake `ConnectorRepository` that RAISES on
   any call in the eight bad-signature cases), `tests/contract/
   test_connector_admin_routes.py` (CONN-ADMIN-001's six, the real
   `AuthService` over the fake repository the way Session 33's admin proofs
   did), `tests/contract/test_connector_command.py` (CONN-CMD-001's seven),
   `test_auth_service_shape.py::test_the_application_serves_exactly_the_
   declared_paths` (unchanged text, new set).
7. **Battery**: parse the body before the signature (the no-call proof FAILS
   — the fake raises); distinguish *stale* from *wrong key* in the 401 (the
   one-document proof FAILS); accept a replay (FAILS); let an agent token
   through an admin route (FAILS); print the key to stdout (FAILS); let `key`
   overwrite an existing path (FAILS).

Targeted (fast): `test_connector_routes`, `test_connector_admin_routes`,
`test_connector_command`, `test_auth_service_shape`, `test_scope_registry`,
`test_scope_vocabulary`, `test_auth_endpoints`, `test_studio_runtime`,
`test_studio_server`, `test_app_contract` (grep), `test_client_typescript`,
`test_generate_command`, `test_studio_command`, `test_client_ir`,
`test_cli_contract`, `test_operator_commands_run_on_the_host`,
`test_apg_dispatcher`, `test_acceptance_registry`, `test_evidence_claims`.
Commit (`Session 34 Run 7: the inbound route, three admin routes, two scopes,
bin/connector.sh`), push, CI.

**Done.** 2026-09-30. **Scopes** (D1796): `admin_connectors:read` and
`admin_connectors:write` appended to BOTH enums of
`schemas/capabilities.schema.json` with the description's sentence;
`ADMIN_CONNECTORS_READ`/`ADMIN_CONNECTORS_WRITE` in `scopes.py`;
`api_surface.reserved_resource_names`' docstring; the six pins moved to the
EIGHT-member exact sets (`test_scope_registry.py` three places plus an
`admin_connectors:approve` absence, `test_scope_vocabulary.py`'s reserved
names, `ADMIN_SCOPES` in `test_auth_endpoints.py` and `test_studio_runtime.py`);
no lock regenerated -- `bin/mcp-contract.sh check`, both forms, exit 0 (D1842).
**`services/auth-api/app/connector_routes.py`** (NEW): `POST /connectors/{name}`,
no authenticator, ADR 0237's order exactly -- the name pattern → 404
`no_such_connector`; `app.state.connector_key` `None` → 404; the raw body above
`strict_json.MAX_BODY_BYTES` → 413 `body_too_large`; a canonical
`X-Apg-Delivery` and `connector_signature.verify` under `derive(master, name)`
→ ONE 401 `signature_invalid` (`WWW-Authenticate: APG-Signature`, `no-store`);
`parse_object` → 400; only then `inbound`, `connector_body.check` → 422
`body_not_permitted` `{reason, member}` (a DECLARED member only), `accept` →
202 `{run_id, status: queued}`; the database's refusals as fixed words (D1840).
**`connector_admin_routes.py`** (NEW): `GET /admin/connectors` (`:read`,
`dead_limit` 1..20, default 20, through `strict_query`; the database's document
plus `dead_limit`), `POST .../enable` (`:write`, `ConnectorEnableRequest
{agent_id: uuid | null}`, required and closed) and `POST .../disable`
(`:write`, a body refused) -- each Session 33's `_admin` before any parse,
`user_id=principal.user_id`; refusals through `errors.ConnectorRefused` /
`connector_refused`, a DETAIL never relayed. Nine models in `models.py`.
**Mounted** in the `auth` branch; `public_paths()` gains the four;
`contracts/app-openapi.canonical.json` recaptured (`--check` exit 0); `apg
generate` moved `appOpenapiSha256` alone (client 1.0.0, `--check` exit 0);
Studio forwards none (its proofs green, unchanged). **`src/agentic_postgres/
connector_keys.py`** (NEW, D1828) ships with its caller, **`bin/connector.py` +
`bin/connector.sh`** (six verbs, exits 0/2/3/4/5): `init --kind` derives an
inbound or scheduled skeleton from the set's first definition (an inbound one:
the first that reads an input) and each compiles as printed; `validate` holds
its report (D1403); `status`/`enable`/`disable` over `ROUTES` with
`APG_API_TOKEN`, `--confirm` = `--name` or exit 2 before the token is looked
for; `key` refuses input (2), then a project without the facility or a name its
set does not declare (5), then asks for root (4), reads the master from the
ACTIVE generation's `auth/connector_signing_key` (the pointer plus the
contract's consumer, never typed) and writes a NEW 0600 file with
`O_CREAT|O_EXCL|O_NOFOLLOW`, never stdout. Listed in `test_cli_contract.py`'s
three lists. **Proofs**: `test_connector_routes.py` (NEW, 10; twelve bad
signatures against an `Untouchable` repository, the control a `Recording` one
making exactly `inbound, accept`; every signature this module's OWN HMAC),
`test_connector_admin_routes.py` (NEW, 6; a REAL `AuthService` over the example
lock's vocabulary, three humans holding one scope each, an agent token 401 on
all three), `test_connector_command.py` (NEW, 8 functions, 13 cases; the
loopback recorder; `key` in-process with `geteuid` → 0 and `SECRET_ROOT` in a
tmp tree of two generations, the non-root exit 4 through the real command),
`test_connector_definition.py::test_the_init_skeletons_validate` (D1836),
`test_connector_facility.py::test_the_two_key_derivations_agree` (D1828), and
`test_auth_service_shape.py::test_the_admin_surface_is_reachable_only_under_admin`
widened and made stricter (D1841). **Battery 10/10 killed, each run beside
`test_connector_definition.py::test_the_three_kinds_compile` PASSED, the targets
green before and after**: the body parsed before the signature; the declaration
read before it; stale told from a wrong key; a replay accepted; an agent token
through status; the key printed; `key` overwriting (both guards removed); the
host copy's label drifting; the first generation read instead of the active
one; enable relaying the database's message. **M1 survived the proofs as the
plan named them** -- with the `unsigned_non_json` arm removed it PASSED both
(D1839). **Targeted, once:** the plan's nineteen modules (`test_app_contract`
is `test_app_contract_aggregate.py`) plus `test_connector_definition`,
`test_connector_facility`, `test_repository_contract`, `test_workflow_routes`,
`test_workflow_admin_routes`, `test_workflow_command`,
`test_deployment_module_shape`, `test_printed_commands`: **1377 passed, 2
failed** -- the prefix pin (D1841) and `test_commands_are_executable_in_the_git_index`
(`bin/connector.*` not yet `git add`ed: D1188's order, missed); both modules
re-run green (`test_cli_contract` beside the shape module, then the shape
module's 43). Its `ruff check` had also failed (E501 in the scheduled template,
S105 on a secret's NAME) and was read only afterwards; fixed, clean, and the
six modules the fixes touch re-run: 328 passed. Rows D1839–D1842. Commit
`cd158ff`; CI by full SHA `cd158ff8546e9af372841954d9a434503b0cd13d`:
`contract` **success** (run 36708948571).

### Run 8 — the readers and the pages: the doctor, the drill, the rehearsal, `docs/connectors.md`, operator guide §18

**Code. Push, read CI by full SHA.**

**Read first:** `bin/doctor.py:740-890`; `diagnosis.py:583-678`;
`bin/restore-test.py:458-560`; `restore_drill.py:600-700`;
`rehearsal.py` whole (1,299 lines — `SCENARIOS`, `BOUNDS`, `Facts`,
`refuse_without_a_reading`, `_worker_restart`, `_PLANNERS`, `verdict`);
`bin/rehearse.py:180-300`, `:530-660`, `:700-800`; `bin/rehearse.sh:30-90`;
`docs/recovery-operations.md:90-145`; `docs/workflows.md:140-325`;
`docs/operator-guide.md:1-40` and `:1279-1496`; `docs/README.md:55-70`.

1. **The doctor** (D1803): `probe_workflow` reads the four new members;
   `diagnosis.workflow_record` gains `deliveries_pending`, `deliveries_dead`,
   `oldest_pending_delivery_age_seconds`, `connectors_enabled`,
   `deliveries_detail="the substrate predates 1.12.0"` (the approvals
   precedent, `:863-877`); the OK line gains *"; deliveries pending N (oldest
   Ns), dead N; connectors enabled N"*; still no threshold; the evidence
   pairs gain the four; `test_doctor_redaction` runs over the new line.
2. **The drill** (D1802): `restore-test.py` nests `deliveries` (a
   `DELIVERIES_BY_STATUS` query beside `APPROVALS_BY_STATUS`, `:545-550`),
   absent with *"app_private.connector_delivery is not present in the
   restored cluster; the backup predates migration 0036"*; the stubs in
   `test_restore_test_command.py` answer `*connector_delivery*` from a new
   `APG_CONNECTOR_DELIVERIES` variable.
3. **The rehearsal** (D1801): `delivery-retry-storm` as the eleventh
   `SCENARIOS` member, `BOUNDS` 60, a `Facts` member
   `outbound_connectors: tuple[str, ...] | None` gathered (only for this
   scenario and not under `--plan`) from `connector_status` through the
   doctor's evidence or a root `psql` (read how `workflow_heartbeat` is
   gathered, `bin/rehearse.py:226-245`, and copy it), `refuse_without_a_
   reading` refusing *"the project has not enabled the connectors facility, or
   declares no outbound connector"*; the planner `_delivery_retry_storm`
   (induce: `SELECT app_private.connector_rehearse_delivery('<first outbound
   by name>')` through `container_exec.run` as `postgres`; observe: poll the
   delivery row every 1 s up to the bound for `attempts`, `status`,
   `last_error` and the three attempt times — a new `rehearsal_attempts`
   observer — and the heartbeat; reverse: none, stated; verify: the
   `workflow` check `ok`); `verdict`'s branch: PASS only if attempts == 3,
   status `dead`, `last_error = connect_failed`, spacing ≥ 2 s each, and the
   heartbeat moved. `bin/rehearse.sh`'s usage list gains the scenario;
   `docs/recovery-operations.md` §4's table gains the row.
4. **The pages**: **new `docs/connectors.md`** (indexed in `docs/README.md`
   beside Workflows, `:63`): what a connector is (three kinds), the file
   (every member, the closed body subset), the manifest block (schema 7,
   `enabled`, `endpoints`, what an endpoint may not contain), the signature
   scheme exactly (headers, signed bytes, the window — enough for a sender to
   implement it; a worked `openssl` example over a sample body, the rig 34b
   form), at-least-once and de-duplicating on `X-Apg-Delivery`, the edge's
   16 KiB and 20/s, the status document, what is not here (redelivery, a
   `test` verb, events beyond the project's own SQL). `docs/workflows.md`:
   `### Wait` gains the event form; *What is not here yet* loses both rows
   and names D1798/§10's. **`docs/operator-guide.md` §18 *Connectors, on a
   deployment*** after §17: enabling the facility (the manifest edit, then
   `bootstrap-providers.sh --plan` / `--apply`, then a redeploy — *a manifest
   change is its own operation*); binding an agent (create it with EXACTLY the
   definition's scopes — the status document names them); handing a key over
   (`sudo bin/connector.sh key … --output …`, never stdout, never a
   workstation); **rotating it** (replace `APG_CONNECTOR_SIGNING_KEY` and
   redeploy — every connector of the project changes key at once; the other
   three rotations are unchanged); the doctor's new clause; the rehearsal; the
   drill's member; *If something goes wrong* (a sender sees 401: the key or
   the clock; 409 `agent_scopes_differ`: the agent was widened; deliveries
   pending and not moving: the key file is absent or the connector disabled).
   No `--session`/`--through-session` literal is added (D678/D1484).
5. **Proofs**: `test_diagnosis.py` / `test_doctor*.py` (grep) for the new
   clause at every magnitude and the *predates* reason; `test_restore_test_
   command.py` for the member; `test_rehearsal.py`'s three storm proofs plus
   the parametrised pair now over eleven; `test_documentation_index`,
   `test_session12_documented_path`.
6. **Battery**: report `0` for an absent member (the predates proof FAILS);
   PASS the storm verdict with 2 attempts (FAILS); drop the heartbeat
   condition (FAILS).

Targeted (fast): `test_diagnosis`, `test_doctor*` (grep), `test_doctor_
redaction`, `test_restore_test_command`, `test_rehearsal`,
`test_rehearse_command` (grep), `test_documentation_index`,
`test_session12_documented_path`, `test_acceptance_registry`,
`test_evidence_claims`. Commit (`Session 34 Run 8: the readers -- deliveries
in the doctor and the drill, the delivery-retry-storm rehearsal, the
connector pages`), push, CI.

**Done.** 2026-09-30. **The doctor** (D1803): `diagnosis.workflow_record`
takes `deliveries_pending`, `deliveries_dead`, `oldest_pending_delivery_age_seconds`,
`connectors_enabled` and `deliveries_detail` (default *"the substrate predates
1.12.0"*); the OK sentence gains *"deliveries pending N (oldest Ns), dead N;
connectors enabled N"* -- or *"deliveries: not read (…)"* when ANY of the three
counts is `None` -- and the four join the evidence; still no threshold;
`bin/doctor.py`'s `probe_workflow` reads 0036's four keys, ABSENT → *predates*,
present and malformed → *the reading did not arrive in the shape*. **The drill**
(D1802): `bin/restore-test.py`'s `DELIVERIES_BY_STATUS` beside
`APPROVALS_BY_STATUS`, nested as `workflow_runs.deliveries`, absent → *"…
connector_delivery is not present in the restored cluster; the backup predates
migration 0036"*; `restore_drill` passes the member whole (comment only).
**The rehearsal** (D1801, D1843): `delivery-retry-storm` is the eleventh
`SCENARIOS` member, `BOUNDS` 60; `_delivery_retry_storm` induces ONE
`connector_rehearse_delivery('<first outbound by name>')` as `postgres` and
observes `STORM_READING` every second (`STORM_POLL_SECONDS` 1.0) until the row
leaves `pending` AND the heartbeat moved, or the bound; reverses nothing; verifies
the doctor's `workflow` check `ok`; `_storm_verdict` is `read` only with one
more rehearsal delivery than before, exactly 3 attempts, `dead`,
`connect_failed`, three observed attempt times each ≥ 2 s apart (D1838's lower
bound) and the heartbeat moved. `bin/rehearse.sh`'s usage and
`docs/recovery-operations.md` §4 gain the row. **The pages**: NEW
`docs/connectors.md` (indexed in `docs/README.md` beside Workflows) -- the three
kinds, the file and the closed body, the manifest block, the scheme exactly with
a worked `openssl` example **executed here: `3c87822a…8a257aba`, OpenSSL
3.5.5, the digest `test_connector_facility.py` pins**, the inbound answers in
their order, at-least-once and de-duplicating on `X-Apg-Delivery`, the edge's
16 KiB and 20/s (burst 40, read from `infra/edge/dynamic/baseline.yaml`), the
status document, what is not here; two claims were checked against the tree
and corrected before commit (the body carries `event_id` too; an endpoint
naming no outbound connector is REPORTED, not refused). `docs/workflows.md`:
`### Wait` gains the event form and *What is not here yet* names D1798, pruning
and foreign events. **`docs/operator-guide.md` §18**: enabling the facility as
its own operation (`bootstrap-providers.sh --plan`/`--apply`, flags read from
its own `--help`), the scopes and binding, the key (never stdout), rotating it
(every connector at once), the doctor's clause, the rehearsal, the drill's
member, *If something goes wrong*. No `--session` literal. **Proofs**:
`test_diagnosis.py` (`test_the_workflow_check_reports_deliveries_with_no_threshold`
over 27 magnitudes, `test_an_unread_delivery_count_is_said_as_not_read_and_never_as_zero`),
`test_doctor_redaction.py` (the poisoned document gains 0036's keys with the
canary in the age; `test_a_pre_connectivity_substrate_is_reported_not_zeroed`),
`test_restore_test_command.py` (the stub's `APG_CONNECTOR_DELIVERIES`;
`test_the_drill_evidence_carries_deliveries_or_null_with_a_reason`),
`test_rehearsal.py` (the recorded runner answers the storm from a small state
-- four OLD rehearsal rows, the newest dead at 3 attempts; the parametrised
sweeps now over eleven: `test_every_scenario_plans_three_phases_and_prints_every_command`
and `test_plan_reads_the_facts_and_runs_writes_and_moves_nothing`, the names
§2 proposed as `…has_induce_observe_reverse_and_a_reader` and
`test_plan_mutates_nothing`; the verdict table's storm row; four new:
`test_the_storm_is_refused_without_the_facility_or_a_connector`,
`test_the_storm_induces_one_rehearsal_delivery_through_the_first_outbound_connector`,
`test_the_storm_observes_three_attempts_and_a_dead_letter`,
`test_the_storm_verdict_needs_the_heartbeat_to_move`). **Battery 7/7 killed,
each beside `test_connector_definition.py::test_the_three_kinds_compile`
PASSED, the targets green before and after**: an absent member reported as zero;
the storm read with two attempts; the heartbeat condition dropped; the drill
writing `{}`; the facility check dropped; a retry sooner than the backoff
accepted; the clause losing its deliveries line. **Targeted, once**:
`test_diagnosis`, `test_doctor_readings`, `test_doctor_redaction`,
`test_restore_test_command`, `test_rehearsal`, `test_documentation_index`,
`test_session12_documented_path`, `test_acceptance_registry`,
`test_evidence_claims`, `test_cli_contract`,
`test_operator_commands_run_on_the_host`, `test_deployment_module_shape`,
`test_printed_commands`, `test_repository_contract`: **1255 passed**, ruff clean
(an earlier doc-guard run failed on `bin/rehearse.sh`'s executable bit, stripped
by the `\\wsl$` write -- `chmod`, re-run green). Row D1843. Commit `5fc5c7a`;
CI by full SHA `5fc5c7a1d4cfe12769d09096c7f361a92e81024d`: `contract`
**success** (run 36710438609).

### Run 9 — the bump, the registry, the gate, and the trip's proofs

**Read first:** `src/agentic_postgres/__init__.py:624-690` (33's paragraph and
`CURRENT_SESSION`); `bin/session-33-check.sh` whole — **yes, whole: 1,644
lines, and D1199 says the last ones are the least executed**;
`tests/contract/test_session_thirty_three_gate_modes.py` whole;
`bin/upgrade.py:100-140`; `docs/upgrade-guide.md:72-100`; `README.md:1-40`;
`tests/deployment/test_session33_gates.py` whole (the shape the trip's proofs
copy); `tests/recovery/test_session32_workflow_restore.py` whole;
`tests/deployment/conftest.py:85-140`, `:890-970`, `:1225-1240`.

1. **The registry**: `EVT|CONN` in the ID regex and the Session 34 sentence
   (§2); the sixteen entries of §2 with node ids read from `pytest
   --collect-only -q` over every module the runs touched (D1236, D1762), plus
   the moved entries (WF-DEF-002's sentence and node ids; the dev proof; the
   scope pins); `evidence_claims.py`'s sixteen claims, eleven in
   `OFFLINE_CLAIMS`, sixteen rows in `CLAIM_INTRODUCED_IN`; the three `THR-*`
   rows' test-node cells rewritten from the collected names;
   `bin/render-acceptance-matrix.py --write`; `bin/render-config.py
   --bounds-doc --write`.
2. **`CURRENT_SESSION = 34`**; the Session 34 paragraph in `__init__.py` in
   33's shape: what moved (this plan's header inventory, as BUILT), the
   `upgrade plan` reading with the three declared classes and its verdict
   (item 6), the MINOR argument (no required secret for a project without the
   facility — measured), `OFFLINE_CLAIMS` 42 → 53 and `CLAIMS` 172 → 188
   *counted from the tuples*, and **the pricing paragraph LAST** (D1629).
   `VERSION` → `1.12.0`; `README.md:7`; `docs/upgrade-guide.md`'s release
   table gains the `1.12.0` row after `:100` (applies migration 0036; outputs
   v19; project manifest 1–7; **two scopes an existing administrator must be
   GRANTED**; **the connectors facility is OFF until a manifest turns it on,
   and turning it on is a separate operation that needs `bootstrap-providers.sh
   --apply`**; a rollback by image is not possible past 0036 — ADR 0162 §3);
   both release pages' release line (`docs/operator-guide.md:22`, the upgrade
   guide's `:17`); **every `--session 33` / `--through-session 33` literal on
   the documented path moved** (eighteen hits at planning across
   `docs/pool-operations.md`, `docs/upgrade-guide.md`, `docs/api-operations.md`,
   `docs/operator-guide.md`, `README.md` and Session 33's own plan — the plan
   is NOT moved; each file's count asserted before and after, D678/D1484);
   `bin/apg.sh generate --project project.example.yaml` and `--check`.
3. **The trip's proofs — `tests/deployment/test_session34_connectivity.py`**,
   `pytestmark = [pytest.mark.p0, pytest.mark.live_host,
   pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS",
   "APG_PROJECT_B_OUTPUTS")]` before the first test. Helpers COPIED from
   `test_session33_gates.py` (`_create_subject` `:107`, `_login` `:131`,
   `ProbeAgent` `:139`, `_create_agent` `:168` with names `apg-s34-{label}-
   {SWEEP}` and a `scopes` parameter, `_revoke` `:193`, `_until` `:394`,
   `_audit` `:428`), `SWEEP = secrets.token_hex(4)` in every name and title.
   Module fixtures, each tearing down in `finally`:
   - `facility_on` — reads beta's DEPLOYED document (`APG_PROJECT_B_OUTPUTS`)
     and fails with a message naming the missing facility unless
     `connectors.enabled` is true; reads alpha's and requires it false.
   - `connectors_admin` — `project_admin` with `admin_connectors:read`,
     `admin_connectors:write`, `admin_agents:read`, `admin_agents:write`,
     logged in over HTTP (the `approver` shape, `:245-274`); left at teardown
     if an FK refuses its delete (D1700's shape), said so.
   - `event_owner` — `authenticated`, scopes `notes:read, notes:write,
     note_embeddings:read, note_embeddings:write` (**read beta's deployed
     lock's `vocabulary.data` first**, the `gate_owner` rule `:213-242`).
   - `agents` — owned by `event_owner`: `inbox` (`agent_writer`, scopes
     EXACTLY `notes-inbox`'s required scopes as the status document reports
     them — read them from `GET /admin/connectors`, never type them),
     `digest` (`agent_reader`, exactly `notes-digest`'s), `waiter`
     (`agent_writer`, `notes-await-embedding`'s — read from the definition
     row), `wide` (`agent_writer`, `notes-inbox`'s scopes PLUS
     `tasks:write`); revoked at teardown.
   - `key_file` — as root, `bin/connector.sh key --project <beta's manifest
     path from the deployed document or the host's checkout> --name
     notes-inbox --output <tmp>/notes-inbox.key` (THE PRODUCT'S COMMAND,
     D1114), read, and the file deleted in `finally`; another for
     `note-embedded` (the proof verifies deliveries with it).
   - `sink` — D1809's container: `docker run -d --rm --name
     apg-s34-sink-{SWEEP} --network <beta compose.networks.internal>
     --network-alias apg-s34-sink <beta's auth image, read from `docker
     inspect` of beta's running auth container> python3 -c <SINK_SERVER>`
     where `SINK_SERVER` is the 40-line server rig 34d measured, committed
     as a module constant; stopped in `finally`. **Every docker call goes
     through `container_exec.run` or the conftest's existing docker helper —
     grep before writing one.**
   - `enabled(name, agent=None)` — a context manager that enables through
     `bin/connector.sh enable` (the product's command, `APG_API_TOKEN` =
     `connectors_admin`'s token) and disables in `finally`.

   The proofs (§2): **CONN-IN-002** (seven — the signed request builds its
   headers with the proof's OWN `hmac` over the key file's value, posts to
   `routes.app` + `/connectors/notes-inbox`, and asserts: 202, the run
   `succeeded` within 60 s as `inbox`, ONE note with the canary title owned by
   `event_owner`; the wrong key → 401, `SELECT count(*) FROM
   app_private.connector_receipt WHERE delivery_id = …` = 0 and no run; the
   replay → 409 and still one receipt, one run; `t = now - 600` → 401; with
   the connector disabled → 409 `connector_disabled` AFTER a good signature;
   `enable` with `wide` → 409 `agent_scopes_differ`; alpha's
   `/connectors/notes-inbox` → 404), **CONN-OUT-002** (three — with
   `note-embedded` enabled, `event_owner` calls `POST /rpc/set_note_embedding`
   DIRECTLY through PostgREST with its own token and the rig 33b vector
   literal; the sink's log shows ONE POST to `/ok` whose signature the proof
   verifies over the logged body with the `note-embedded` key file, and whose
   payload is `{"note_id": <that note>}`; `notes-deadletter` enabled → exactly
   3 POSTs to `/fail`, spacing ≥ 2 s, then `bin/connector.sh status` shows the
   delivery `dead`/`http_500` and its output contains neither `apg-s34-sink`
   nor the note id; with both disabled, the same write → no
   `connector_event` row whose payload names that note), **EVT-WAIT-002**
   (two — `waiter` starts `notes-await-embedding` with a canary title; poll to
   the wait step `parked`; `event_owner` writes the embedding of the run's
   OWN note (read the note id from the `create` step's result) → the run
   `succeeded` and the wait step's result names that note; the control: an
   embedding for ANOTHER note of the owner leaves it `parked` for 15 s, then
   the proof cancels it), **CONN-SCHED-002** (one — enable `notes-digest`
   with `digest`; a run of `notes-digest` by `digest` `succeeded` within
   `60 + 10` s; disable; `next_fire_at IS NULL`).
   **`tests/recovery/test_session34_delivery_restore.py`** (REC-EVT-001),
   copying `test_session32_workflow_restore.py` whole (`_wal_switch`, the
   marker note, the target, the drill command, the newest evidence file) and
   comparing `pending + dead` from `connector_delivery WHERE created_at <=
   target` with the drill's `workflow_runs.value.deliveries` — **it requires
   at least one such row and fails naming why if there is none** (the
   dead-letter proof leaves one; the recovery module runs after the
   deployment module in the sweep — read the sweep's module order in
   `mode_host` and say so in the Done).
4. **`pytest --setup-plan`** for both new modules with `APG_LIVE_HOST=1
   APG_PROJECT_A_OUTPUTS=<op-owned copy> APG_PROJECT_B_OUTPUTS=<…>` set
   (D671, D676) — and with none set (every proof SKIP, 0 errors); both
   outputs kept in the scratchpad and counted in the Done.
5. **`bin/session-34-check.sh`** derived from 33's with every substitution
   count-asserted (`SESSION=33` → `34`, `session-33` → `session-34`,
   `thirty_three` → `thirty_four`, the evidence prefix, the ADR range in the
   header, the offline sentence's counts *ten* → *eleven* and *forty-two* →
   *fifty-three*), the header and usage rewritten whole and read line by line
   (D1488); `run_suite "p0 and not future and not live_host and not
   external"` kept verbatim (D1242); **no flag added or removed** — `diff
   <(grep -o -- '--[a-z-]*' bin/session-33-check.sh | sort -u) <(grep -o --
   '--[a-z-]*' bin/session-34-check.sh | sort -u)` is EMPTY and pasted in the
   Done (write it in a script file — process substitution inside `wsl bash -lc
   "…"` is the quoting CLAUDE.md §1 forbids); `SHELL_COMMANDS` gains it;
   `chmod 755`; `git add`; `tests/contract/test_session_thirty_four_gate_
   modes.py` from thirty-three's with the no-gap test carried (33 → 34) and
   `test_exactly_this_sessions_declared_claims_are_offline` naming the eleven.
6. **`upgrade plan` offline** (D1624's recipe, derived from Session 33's
   `s33r8-upgrade.sh` — find it in the scratchpad backups or re-derive from
   Session 33's Run 8 Done): the installed side a worktree at `02ffbbd`, the
   candidate a `tar`-piped copy of the working tree at `/tmp/apg-candidate`
   with `.generated/` excluded, both rendered as `project.example.yaml`;
   `bin/upgrade.sh plan … --json --also migration_added --also
   api_operation_added --also document_schema_migratable` → expect `bump
   minor`, `requires minor`, verdict `ok`, **and `secret_required_added`
   ABSENT from `changes`**; list every differing leaf (D1811's prediction);
   without the flags → `requires patch`. If the installed v18 and candidate
   v19 documents make the plan `UNDETERMINED`, that is §9's stop, not a
   workaround.
7. **The gates**: `bin/session-01-check.sh` once on the clean tree (commit,
   gate, repair, commit, gate again; every first-run failure a row), run
   DETACHED with its exit code written from inside (CLAUDE.md §1);
   `bin/session-34-check.sh --mode offline` → `evidence/session-34-offline.
   json` with the eleven new offline claims plus the 42 inherited, every one
   `passed` (the count read from the file). Push; CI by full SHA.

Commit (`Session 34 Run 9: the bump to 1.12.0, the registry, the gate, the
trip's proofs`), push, read CI. **Nothing goes to the host until this commit's
CI is green by full SHA.**

**Done.** 2026-09-30. **The registry**: `EVT|CONN` in the ID regex with the
Session 34 sentence; sixteen entries, every node id checked against `pytest
--collect-only` over the modules §2 names (all offline ids present but the
two storm sweeps, which exist under their own names; the whole-module cells
named as tests, D1847); `evidence_claims.py` sixteen claims, eleven in
`OFFLINE_CLAIMS` -- **188 and 53, read from the tuples** -- and sixteen
`CLAIM_INTRODUCED_IN` rows at 34; the three `THR-*` rows cite `CONN-IN-001/002`,
`CONN-OUT-001/002`, `CONN-STORM-001` and collected node ids, the *until Run 9*
sentences gone; the matrix regenerated (281 requirements). **The bump**:
`CURRENT_SESSION = 34`, `VERSION` 1.12.0, the Session 34 paragraph ending on
its price (`test_release_contract` asked for `1.12.0` in backticks, one
*prices it a MINOR* sentence and a *schema moves* sentence -- this release's
two are migratable, and it says so); README's status line; both release pages'
release line and the operator guide's first table (36 migrations, outputs v19,
manifest 1–7); the upgrade guide's `1.12.0` row; **every `--session 33` /
`--through-session 33` moved, counted per file: README 1+1, pool-operations 1,
upgrade-guide 1+1, api-operations 1+3, operator-guide 3+4** (the first pass
stopped at the operator guide's four, and its earlier files were counted done
before the second); `apg generate` moved the client's version fields,
`--check` exit 0. **The trip's proofs**: `tests/deployment/test_session34_connectivity.py`
(NEW, thirteen, `pytestmark` before the first test; fixtures `facility_on`,
`connectors_admin`, `event_owner` -- beta's deployed lock read first --
`agents` with scopes READ from the rows (D1845), `key_file` through `sudo`-run
`bin/connector.sh key` against the host checkout's `project.beta.yaml`, its
project key checked against beta's document, `sink` from beta's own auth
image on `compose.networks.internal` under the alias `apg-s34-sink`, rig 34d's
server with an arrival time added; `enabled()` through `bin/connector.sh`,
disabling in `finally`) and `tests/recovery/test_session34_delivery_restore.py`
(NEW, D1846). **The sweep collects `tests/deployment` before `tests/recovery`**
(`testpaths = tests`, no randomising plugin installed), so the dead letter
the deployment module leaves is there for REC-EVT-001. **`--setup-plan` with
`APG_LIVE_HOST=1` and two rendered documents: 14 proofs planned, 0 errors;
with none set, run: 14 skipped** (outputs in the scratchpad). **None of the
fourteen has executed.** **`bin/session-34-check.sh`**: derived from 33's by
a count-asserted script, the header and the three mode paragraphs rewritten
whole; **the flag sets are EQUAL -- 59 and 59, `diff` empty** (the first
derivation's header named `bootstrap-providers.sh --apply` in prose and the
token diff caught `--apply`; reworded); the body differs from 33's by `readonly
SESSION=34` alone; `SHELL_COMMANDS` gains it; `test_session_thirty_four_gate_modes.py`
derived (the no-gap test at 33 → 34, the eleven offline names). **`upgrade
plan` offline** (D1844): declared `bump minor`, **`requires minor`**, verdict
`ok`, `changes [api_operation_added, document_schema_migratable,
implementation, migration_added]`, `reasons []`, **no `secret_required_added`**;
undeclared `requires patch`; seven leaves -- `template_version`,
`schema_version` 18 → 19, `connectors.enabled` absent → false,
`migrations.release_lock_sha256`, `inputs.secrets_contract_sha256`,
`migrations.project_set.count` 2 → 3, `migrations.project_set.lock_sha256`;
5,949 → 5,993 bytes. **The gates, on the clean tree**: `bin/session-01-check.sh`
on `7161a19` **FAILED at step 2** (E501, D1847) → repair `0299500` → **PASSED**:
6,768 contract tests passed, 0 failed, 3 skipped, 7,197 P0 collected, 281
requirements current, 0 collisions; `bin/session-34-check.sh --mode offline`
on `0299500` **PASSED on its first run**: 6,777 passed, 0 failed, 3 skipped,
and `evidence/session-34-offline.json` carries **53 claims, 53 `passed`**
(counted from the file), the eleven new ones among them. Rows D1844–D1847.
**CI:** `02995006dd19075fb9fe599e63cd951b20aa67fb` → `contract` **success** (run
36716092054) -- the condition for anything going to the host is met.

### Run 10 — the trip: the release on both projects, then beta's facility as its own operation, one sweep, the tag

**Before the day** (agent, offline): read Session 33's Run 9 and Sheets C1–C6
(`session-33-implementation-plan.md` §5 Run 9 and the appendix) and
`docs/operator-guide.md` §17 *If something goes wrong* (D977); **derive the
host scripts `s34-r10-*` from `s33-r9-*`** (`checkout, renders, c1, sentinel,
after, readings, gate, launch, cleanup`) by named substitution with every
count asserted — a Python deriver modelled on `s33r9-derive.py` (`s33-r9` →
`s34-r10`, `33` → `34` only where it is a session literal, the bundle's sha)
— and **diff each derived script against its parent: the gate script's
declaration block fifteen tokens (14 flags + `--mode`) in, fifteen out**
(D1133); write the NEW scripts: `s34-r10-facility.py` (op side — below),
`s34-r10-after-facility.sh` (root reads after beta's second deploy) and
`s34-r10-rehearse.sh`; the external script in WSL `~/s34r10/
s34-r10-external.sh` from `~/s33r9/s33-r9-external.sh` WITH D1640's
`ssh-agent` block; copy every script to the scratchpad; CI green on Run 9's
commit by full SHA; **WSL's outbound TCP probed with a timed `/dev/tcp`
connect read inside a script** (CLAUDE.md §1 — a Windows reboot early if it
is dead); the two op-owned document copies' `source_commit` read. The reads
scripts TEE their own transcript — hand them as `sudo bash <script>`, never
inside `script(1)` naming the same file (D1771); the deploys, the sentinel,
the bootstrap and the cleanup go in `script(1)`.

**The op side, run by the agent over SSH** (`ssh -i ~/.ssh/agentic_postgres_
ed25519 op@62.238.99.122 'bash -s' < /tmp/x.sh`): `git bundle create
/tmp/apg-<sha>.bundle e087bca..main` locally, `scp`, `git fetch` the bundle on
the host, `git rev-parse FETCH_HEAD` equal to Run 9's sha, `git checkout
<sha>`, the dependency diff printed and `uv sync` only if it moved (D1766),
the four fixtures and the two projects rendered `--render-only` as `op` —
**both at outputs v19, `connectors.enabled` false on all four** —
`pytest --setup-plan` for the two new live modules with the variables set,
pointing at the op-owned copies.

**The operator's sheets are in the appendix: D1 → D9, one outcome each, each
read by the agent before the next is issued (D1510).** Every `sudo` line has
nothing after it — no pipe, no redirect, no `$(`, no `&` (D1505); a transcript
comes from `script(1)` or the script's own tee, and the agent reads it over
SSH as `op`.

**Between D3 and D4 — the facility, op side** (`s34-r10-facility.py`, run by
the agent as `op`, PATH exported): copy `/home/op/agentic-postgres/
project.beta.yaml` to `project.beta.yaml.pre-s34` (refusing if the backup
exists); load it with `yaml.safe_load`; **refuse unless** its `schema_version`
is 6 and it has no `connectors` key; set `schema_version: 7` and `connectors:
{enabled: true, endpoints: {note-embedded: "http://apg-s34-sink:8080/ok",
notes-deadletter: "http://apg-s34-sink:8080/fail"}}`; write it back
preserving key order; print a unified diff and assert it touches exactly
those lines (the file is gitignored operator input — never committed, D971);
re-render beta `--render-only` as `op` and assert the rendered document says
`connectors.enabled: true` and `secrets.required_names` gained exactly
`connector_signing_key`. **If beta's manifest is not schema 6 today, STOP**
and write a row: the edit is re-planned against what is there.

**Then, from the workstation, after the sweep:** `bin/session-34-check.sh
--mode external` through `~/s34r10/s34-r10-external.sh` (ephemeral
`ssh-agent`, `--ssh-destination op@62.238.99.122`, D466); fetch
`evidence/session-34-host.json` from the host (`scp` as `op`);
`write-session-evidence` merges the three halves → `evidence/session-34.json`,
exit 5 for the expected reasons only (§7) — **every half must name Run 9's
deployed commit** (Session 29's rule; D1641's method if an instrument had to
move, stated in the tag). `release-reading --ref <deployed sha>`; `git tag -a
1.12.0 <deployed sha> -F /tmp/tag-msg.txt`; push the tag.

**If something goes wrong** (read before the day): 0036 fails at step 6 on
alpha → **STOP, never amend it** (D912); read the ledger (`migrate.sh
--runtime status` prints it since D1707's repair); a fix-forward 0037 is a
new run and a new deploy. Beta's project migration `0003` refused as
out-of-order (D1098's `up --strict`) → STOP; the version rule was misread in
Run 5; a row, a new project migration with a correct version, a new deploy.
`bootstrap-providers.sh --apply` hangs → Infisical (D976); wait for the
client's three retries, then STOP and read — never loop it. Step 0 of beta's
second deploy still refuses the missing secret after `--apply` → read
`bootstrap-state.json`'s `managed_resources` as root; a row. The sink cannot
resolve from `auth` → the network name was read from the wrong document (the
DEPLOYED one names it); a `-k` iteration after the repair, never a second
sweep for a fixture (one sweep per trip; a second only for a defect). A
connector left ENABLED after a failed module → the cleanup sheet disables
every connector by name (`bin/connector.sh disable` needs a human token the
cleanup does not hold, so the cleanup script runs `SELECT
app_private.connector_disable(name, NULL)` as `postgres` through
`container_exec.run` for each of the four; **`connector_disable` accepts a
NULL `p_user`** — Run 3 builds it so, the route never passes NULL (a proof in
`test_connector_admin_routes.py` asserts the route passes `principal.user_id`),
and a NULL `disabled_by` reads *"disabled by the operator"* in the status
document).
`auth` does not come back after a deploy → `docker start` (ADR 0193's
fallback), a row, and the sweep waits for `doctor` 12 ok.

**Done** records: all three deploys' step 0 lines, step 6's migrator line AND
the ledger (36 / 36 + 3), step 6d's lines (alpha *no set*, beta seven),
step 6e's lines (alpha *no set*; beta's first *not enabled*; beta's second
four installs with their words), the bootstrap `--plan` and `--apply` lines
(names only), the materialized generation's new file (name and mode only,
read as root by the after-facility script — never the value), the doctor's
`workflow` line before and after, the sweep's JUnit counts, every new claim's
status, the merged document's totals, the rehearsal's verdict and its three
attempt times, the connectors' final state (all disabled), the probe agents
and humans left on beta, the tag and its message.

**Done.** 2026-09-30. **Deployed, swept and tagged on `14b1b9d`** (Run 10a's
commit; D1848 moved it from Run 9's `d32dc09` before anything was deployed).
**Prep**: WSL TCP to the host 0.33 s; `s33r9-derive.py` was on neither machine,
so `~/s34r10/s34r10-derive.py` was written in its shape (D1851) -- ten scripts,
every count asserted, the gate's declaration block **15 tokens in, 15 out**;
the facility script, `after-facility` and `rehearse` new; a facility rig
(control refused, 1+6 lines, second run refused) found D1849. **Sheet D1
(first)** found D1848 -- `fleet` and `dr-kit export` could not read the v18
documents, and a rig showed step 0 would refuse every deploy; **Run 10a**
repaired it; **D1 (second)**: `upgrade check` rc 0 twice; doctor 11 ok +
`migrations` PROBLEM (35 of 36, 37 of 39) and *"deliveries: not read (the
substrate predates 1.12.0)"*; `fleet` both at `02ffbbd`; `upgrade plan` WITH
the three classes `bump minor`, `requires minor`, `ok` (alpha 5 leaves, beta 7),
WITHOUT them `requires patch`; the PRE kit `kit-2026-09-30-pre` export 0,
verify 0 (copied to `~/dr-kits`). **D2a**: the sentinel
`s34-redeploy-sentinel-2026-09-30`, generation `7b54c4f4386098c4`, count 1.
**D2b alpha**: step 0 `admitted` **reading beta's v18 document** (committed
`beta-dev 304`) -- ADR 0241 live; step 6 `Applying: 20260929120036_connectivity`
(86.9 ms), ledger **36**, `Pending: 0`; 6d/6e *"no … (the project declares no
migration set)"*; exit 0; auth, storage, mcp, docs recreated; doctor **12 ok**,
*"deliveries pending 0, dead 0; connectors enabled 0"*. **D3 beta**: admitted;
0036 (89.6 ms) then the set's `0003_note_embedding_events` (13.3 ms), ledger
**36 + 3**, `Pending: 0` twice; 6d **seven** definitions (new:
`notes-await-embedding`, `notes-digest`, `notes-inbox`); 6e *"no connectors (the
manifest's connectors.enabled is false)"*; exit 0; doctor 12 ok. **The
facility** (op): diff 1 removed + 6 added; the render `connectors {"enabled":
true}`; the contract's reader owes 20 → 21, gained exactly
`connector_signing_key` (D1849). **D4a** `--plan`: exactly *"create secret
value connector_signing_key"*; **D4b** `--apply`: *"created
connector_signing_key for beta-dev"*, recorded, no value printed. **D5**: the
first run refused at step 3 on the facility backup left in the checkout
(D1852) -- nothing installed; moved out; second run exit 0, no migration, 6e
**four installed** (two outbound, one scheduled, one inbound), `auth` and `mcp`
recreated; the deployed document names `connector_signing_key` in
`secrets.required_names`; the key file `generations/a7dae74036d88ebf/auth/
connector_signing_key`, owner uid 65532 (no host name), mode `400`, under
`auth` alone -- never read; four rows all disabled, the two outbound
`has_endpoint t`; doctor 12 ok, connectors enabled 0. **D6**: ceilings 4,480
MiB unchanged, 608 committed; doctor 12 ok (BEFORE: deliveries 0/0, enabled
0); `usage` rc 6; both op copies v19 at `14b1b9d`. **The sweeps**: FIRST
(`14b1b9d`, 35m36s) 1,068/6/7/2 -- `connector_inbound_live` and
`connector_schedule_live` passed on first execution, five instrument defects
(D1853); `-k` on `5b8f641` 17/0; SECOND (`5b8f641`, 44m40s) 1,074/2/7/0 -- all
five new host claims passed, `project_isolation` lost to an expired fixture
token (D1854); `-k` on `8d655b5` 22/0; **THIRD (`8d655b5`, 45m57s) 1,075
passed, 1 failed (`documented_path`), 7 skipped, 0 errors** -- the host half.
**Every new claim**: `connector_inbound_live`, `connector_delivery_live`,
`event_wait_live`, `connector_schedule_live`, `delivery_restore` **passed**; the
eleven offline passed at the gate. **D8** `delivery-retry-storm`: verdict
`read`, rc 0; one rehearsal delivery through `note-embedded`, attempts at
**3.8, 8.5, 14.3 s** ([4.7, 5.8] s apart), `dead`, `connect_failed`; heartbeat
18:33:08.849 → 18:33:23.989; the doctor's workflow check ok (the `--plan`
placeholder, D1855). **D9**: the sentinel `DELETE 1`; all four connectors
`disabled` (D1850's word), unbound, by the operator; doctor AFTER 12 ok, runs
succeeded 50 / cancelled 16 / failed 13 / stopped 13, **deliveries pending 0,
dead 4** (three dead letters and one rehearsal), **connectors enabled 0**;
left on beta: 16 revoked `apg-s34-*` agents and 8 probe humans, 6 `pending`
approvals on ended runs (D1775's class); the POST kit `kit-2026-09-30-post`
export 0, verify 0, copied to `~/dr-kits` (D1856). **External** (WSL,
ephemeral agent, no-`-i` control rc 0): PASSED 25/0/8. **The merge**:
`evidence/session-34.json` **188 claims -- 182 passed, 5 not_run, 1 failed**,
the plan's prediction exactly; every half names `14b1b9d`. `release-reading
--ref 14b1b9d`: `tag_is_owed`, 21 commits, 138 files, migrations 35 → 36, ADRs
234 → 241. **Tagged `1.12.0` on `14b1b9d` and pushed**, the message stating
D1641's method (the host half's instruments from `8d655b5`; the diff
`14b1b9d..8d655b5` tests and the plan only, asserted on the host).

### Run 10a — the repair Sheet D1 forced: an existing deployed document is read by version (D1848)

**Why.** Sheet D1 (reads only) found that the new checkout could not read
either project's outputs-18 document: `fleet` and `dr-kit export` refused them,
and a workstation rig on beta's real document showed deploy step 0 would refuse
every deploy of the release (D1848, §9's stop). Nothing had been deployed.

**What.** ADR 0241: `deployed_output.read_deployed_document` (+
`UnreadableVersion`, `READABLE_PREVIOUS_VERSION`); `capacity_probe.read_deployed`,
`bin/fleet.py`, `dr_kit.plan_export` and `verify_deployed_document`'s current
branch, `bin/project-retire.py` moved onto it. Six tests in
`tests/contract/test_disaster_kit.py`: the previous version read exactly as
found (and still refused by the writer's validator); two other versions named
as unreadable; the previous version still checked for kind, sensitive keys and
placeholders, the current one refused as before; admission CHARGES a
previous-version neighbour and refuses one two versions behind by name; fleet,
retire and the kit read it and the kit stores it as found; and the class guard.

**Done.** 2026-09-30. Targeted modules (`test_disaster_kit`, `test_fleet`,
`test_capacity_reading`, `test_output_migrations`, `test_project_retire`): **286
passed**. **Battery: 9 of 9 killed, each beside a green control it cannot
reach** (`test_the_command_writes_owner_only_refuses_an_existing_directory_and_verifies`),
every file restored and `cmp`-equal: any older version accepted; the kind check
dropped; the sensitive-key check dropped; the reader carrying `connectors`
forward; admission, fleet, the kit and retire each put back on the writer's
validator; an unreadable version folded into *does not validate*. The rig on
beta's REAL version 18 document, re-run on the repaired tree: **unreadable {}**.
**CI:** `14b1b9de1267298352285b62067baea7e9708eba` → `contract` **success** (run
36722250463). Run 10b (`5b8f641`, D1853) → success, run 36740526676; Run 10c
(`8d655b5`, D1854) → success, run 36750791298. Both tests only.

### Run 11 — the close

**Documentation only unless Run 10 found something for `src/`** (D1644): if
a measurement belongs in `capacity.ENVELOPE` (none is planned — this session
measures no memory; D1711 stays `UNMEASURED` with its reason), commit it,
run `bin/session-01-check.sh` once (detached), push and read CI; otherwise
push, say it is pushed, and read no CI.

Then the records: this plan's header rewritten (COMPLETE, the dates, the rows
each run added, NEXT FREE); **`docs/scope-closure.md` §27** — what 34 closed
(D1522 as far as the proofs reach, D1525's scenario, D1527's three rows,
D1529's row, D1780's lint hole, D1777's fixture), what it left (§10), and
**what Session 35 inherits** (the noisy-neighbour measurement now has a
second workload — the worker's delivery pass; the third reader walks a path
that now includes connectors; the edge's unbounded containers; the retention
story, now four tables longer; **the D1721 database half, assigned to 35 by the operator on 2026-09-29**);
`docs/plans/stage-4-plan.md`'s Status block (`CURRENT_SESSION 34`, 1.12.0,
the evidence totals, NEXT FREE); CLAUDE.md §2/§8/§9 in the launch folder
rewritten compactly (**copy it to the scratchpad first** — it is not in git)
and the project memory updated. Documentation commit(s): push, no CI read.

---
## 7. Evidence and claims

Unchanged rules (ADR 0163, 0202; D1237; D1543). **Sixteen claims land with
the constant** (D690): eleven declared offline — each a property of a
checkout (a migration under a real cluster the gate requires Docker for, a
lint over committed text, a compiler over committed files and locks, a loop
and a route over fakes whose bytes a rig measured, a command's closed tables,
a reader over canned inputs, a rehearsal's plan) — and five host, undeclared,
first executed on the trip. **Session 34 is the session whose second
principal is OUTSIDE the deployment**, and its claims say so:
`connector_inbound_live` is proved by a request that crossed the public edge
carrying a signature the product's own `key` command's output produced, never
by a row written as superuser; `connector_delivery_live` by bytes a sink
received and the proof verified with its own HMAC.

| Claim | Mode | Moves on |
|---|---|---|
| `event_emitter`, `event_lint`, `event_wait`, `connector_definition`, `connector_facility`, `connector_delivery`, `connector_inbound`, `connector_admin`, `connector_schedule`, `connector_command`, `delivery_storm_rehearsal` | offline | Run 9's gate |
| `connector_inbound_live`, `connector_delivery_live`, `event_wait_live`, `connector_schedule_live`, `delivery_restore` | host | Run 10's sweep — their proofs' **first execution anywhere** |
| every Session 32 and 33 workflow claim (`workflow_resume`, `workflow_revocation`, `workflow_approval_live`, `workflow_compensation_live`, …) | host | Run 10 — **the replaced `workflow_gate_state` and `workflow_counts` are under them**, and the approval proofs' `set_note_embedding` now emits (into nothing: every connector is disabled outside Session 34's module), so their passing again is part of this session's evidence |
| `deployment_convergence` | host | Run 10, `--redeploy-before-file` declared (beta is redeployed twice) |
| the rotation trio, `replacement_host_restore`, `port_allocation` | — | `not_run`, unchanged; `documented_path` `failed` by decision |

**Expected merged document**: 188 claims — 182 passed, 5 not_run, 1 failed —
if every new claim passes. Any other figure is read before the tag.

---

## 8. Security invariants this session touches

| Invariant | Where 34 puts it at risk | Control |
|---|---|---|
| **A connector holds nothing an agent identity does not hold** (stage plan §8, ADR 0217) | The inbound route; the scheduled fire | A connector starts a RUN as a bound agent; every step is minted per attempt with the agent's STORED scopes, under the plane's scope check, audit, budgets, quota and idempotency key; binding requires the agent's scopes to EQUAL the definition's and acceptance re-checks it (D1783) |
| **A connector identity only narrows** | Binding | Exact scope equality at `enable`, `accept` and `fire_due`; one agent, one connector (a unique index); no per-agent profile is invented |
| **The outbox is written in the caller's transaction by a reviewed function, never by a trigger on a base table** | The emitter | `app.emit_event` granted to NOBODY, reachable only from a definer function running as the owner; no `CREATE TRIGGER` in 0036 or 0003 (a proof greps both); the lint forbids a project from defining it (D1780) |
| **An inbound request is signature-checked before any database is touched** | The route | D1789's order; the proof with a repository that RAISES on any call; one fixed 401; the delivery id inside the signed bytes |
| PostgreSQL is the final authorization authority | A run started by a connector | `workflow_enqueue` checks the agent's stored scopes against `required_scopes` (0034); the tool call goes through PostgREST under RLS as ever |
| An agent cannot run SQL | A connector's body | The body is a run's `input`; it reaches a tool only through a compiled `{{input.<k>}}` argument reference; the closed body subset admits scalars only |
| **An agent record carries no URL, key, token or caller value** | The delivery record; the status; the logs | The endpoint is never stored outside the connector row, never returned but by the claim, never logged; `last_error` is a CHECKed token; `connector_status` never returns `endpoint`, `payload` or `body` (a recursive key walk); the key is derived in memory |
| **A workstation holds no production secret** | The connector key | `key --output` on the host as root, 0600, never stdout (D1804); the rig's key is a throwaway |
| **A report may not substitute an answer for a failure to determine one** (ADR 0195) | `connector status`, the doctor's clause, the drill member, 6e's lines | *"deliveries not read (the substrate predates 1.12.0)"*; `binding: agent_scopes_differ` computed on read; 6e says which of three reasons installed nothing; an outbound with no endpoint is REPORTED at install and REFUSED at enable (a decision may fail closed, a report may not) |
| One service cannot read another's credential | The new secret | One consumer, `auth`; `APG_CONNECTOR_KEY_FILE` forbidden in `storage` and `mcp` |
| The MCP runtime holds no credential | The key | `FORBIDDEN_VARIABLES` for `mcp` gains it; the plane never sees a connector |
| Projects share no project-scoped value | Connectors, events, keys | Rows in each project's own database; one master per project at its own provider path; alpha without the facility answers 404 (a live proof) |
| A human cannot run SQL through a product surface | `bin/connector.sh` | The command holds no SQL (a proof); every route calls a definer function with parameters |
| **There is no public Postgres endpoint** (ADR 0216) | An unauthenticated HTTP route | The route is under the existing `/api/app` router; no port, no listener, no router |
| `--render-only` keeps working with no host and no root | The facility, 6e | A render reads the manifest; 6e is not reached by a render; the four fixtures render at v19 with the facility off |
| A restore never overwrites the active volume | The drill member | Unchanged path; REC-EVT-001 reads a drill volume |
| The deploy, the sweep and the tag land on one commit (D1425) | Run 10 | The sheets' order; beta's facility deploy is the SAME commit; D1641's method if an instrument moves |
| Never grant `op` the docker group | The sink; the key | Both are root's, inside the sweep and the `key` command |

---

## 9. Stop conditions

- **Rig 34a**: a request role CAN execute `app.emit_event` without a grant,
  or PostgREST CAN address a function in `app`: stop; D1779's premise is
  false and ADR 0235 is rewritten before Run 3.
- **Rig 34a**: `CREATE OR REPLACE FUNCTION api.create_note` from a project
  set is REFUSED by something other than the lint (e.g. ownership): rewrite
  D1780 to say what refused it and keep the lint rule anyway (a second belt);
  continue.
- **Rig 34b**: Python's HMAC and `openssl`'s disagree on the same bytes:
  stop; the scheme is not what the page will tell a sender.
- **Rig 34c**: a `tools/call` needs a scope OTHER than the tool's own and
  `meta:read`: stop; D1783's equality rule cannot be stated as written.
- **Rig 34d**: a container on an `internal: true` network cannot be reached
  by a container on it and another network: stop; the trip's sink is
  re-planned (and D1792's residual is re-measured).
- A `CREATE OR REPLACE` of `workflow_gate_state` or `workflow_counts` would
  need a DIFFERENT signature or return type: stop; that is a `DROP`, and every
  caller of a Session 33 function moves.
- `test_the_loop_starts_in_auth_mode_only` cannot stay green unchanged:
  stop — the delivery pass has become a second task (D1790).
- The inbound route cannot be written without a database call before the
  signature (e.g. the connector's existence must be read first): stop — the
  stage plan's invariant is the contract.
- Run 9's `upgrade plan` prices `1.12.0` at **major**, shows
  `secret_required_added` on the example renders, or reads `UNDETERMINED`
  across outputs 18 → 19: stop; a row; the operator's decision.
- A passing test would be weakened — including any scope-set equality (it
  becomes a larger equality, never a subset check), `test_the_application_
  serves_exactly_the_declared_paths`, `test_every_transport_in_the_service_
  is_declared_with_a_reason` (a new ROW, never a relaxed rule),
  `test_api_migrations.py:494-544`, the twelve-check proof, or
  `test_one_token_per_step_attempt_and_none_outlives_the_step`. The ONE
  replacement this plan authorises is D1793's, under ADR 0239.
- A step, a compensation or a connector would invoke anything that is not a
  tool the project's lock compiles; a connector would call a tool except
  through a run; the worker would cache a token across steps or mint one for
  a wait (stage plan §9).
- The outbox would be written by a trigger, or a change feed exposed (stage
  plan §9).
- A port, a new router, a route to a store, a non-loopback bind, or a
  connector-specific listener, for any reason (ADR 0216).
- Admission would refuse alpha's or beta's OWN redeploy: stop before the
  deploy.
- Migration 0036 fails on alpha at step 6: stop; **never amend it** (D912);
  the ledger is read; a fix-forward 0037 is a new run and a new deploy.
- Beta's manifest is not schema 6 on the day, or the facility edit's diff
  touches anything but `schema_version` and `connectors`: stop; a row.
- The sweep's new host claims read `not_run`: `skipped_node_ids` first; a
  missing gate variable is the gate's defect; never re-run the deploy.
- CI red on a code commit: stop and read the failed job's log by id; a
  cancelled run is not a failed one (D1059); re-run only the module that
  failed, locally.
- WSL has lost outbound TCP on trip day: CLAUDE.md §1; a Windows reboot early.
- Any run finds itself building toward D1721's database half (a release
  `api.require_approval`, a gated-function lint rule, a change to a gated
  project RPC beyond `0003`'s one emit line): stop — **the operator assigned
  it to Session 35 on 2026-09-29**.

---

## 10. Open items this session carries and creates

**Carried in, untouched, each still true:** D1045; `replacement_host_restore`
(D1028); D1375; the 21 unclaimed requirements; D976, D688, D771, D340, D466,
D540, D942, D1203, D1205, D1211; the Infisical control-plane identity's org
admin; `process-max` 1 (D593); `documented_path` failed until a person walks it
(35); the three rotations Session 30 did not perform, and the retired JWKs on
the host unread by any sweep; the mirror's upstream flake (D1546); `apg-diag`'s
standing account (D1528) and its allowlist (D380 — **the connector route's
refusals live in the auth service's log, which `apg-diag` still cannot read**;
widening it is a one-service allowlist change with a test, not taken here);
ADR 0162's missing row for an option (D1561); **D1642** (`dr-kit.py` untouched);
**D1547** (`delete_note` — this session moves the `app` contract and the
example project's set, not the release's `api` contract); **D1581/D1713**; the
edge's unbounded `traefik` and `docker-socket-proxy` (35); the three unbounded
services (pgbouncer, postgrest, docs); the noisy-neighbour measurement (35 —
it now has a second workload, the delivery pass); **D1711** (no memory figure
under a run: this session takes no memory reading; the sub-second sampler is
still owed); the out-of-order 1.9.0/1.8.0 rows in the upgrade guide's table.

**Created or left here:**

| Item | Note |
|---|---|
| **Approval is enforced by the plane, not the database** (D1721) | Unchanged, and now visible from a new side: `set_note_embedding` EMITS on every committed write, including a direct PostgREST call that met no approval. The priced repair (Session 33's §10: `api.require_approval`) is unchanged. **Assigned to Session 35 by the operator on 2026-09-29.** |
| **A project function cannot honour `Dry-Run`** (D1722, D1806) | `0003` copied the body byte-for-byte. A release helper the lint allows — `app.request_is_dry_run() RETURNS boolean` reading `request.headers` — would let a project RPC roll back its own dry run (and its event). Priced, not built. |
| **Dead letters cannot be redelivered** (D1798) | A redelivery is a human write to the outbox: a route, a scope (`admin_connectors:write` would do), an audit story. |
| **Receipts, events and deliveries are never pruned** | Four more tables in D1700's retention story, beside runs, approvals and probe identities. An operator horizon (ADR 0213's shape) is the answer when one is priced. |
| **One master key per project** (D1784) | Rotating it rotates every connector's key at once; a per-connector rotation needs a per-connector secret, which the static contract cannot hold. Said in operator guide §18. |
| **The endpoint is trusted because the manifest is root's** (D1792) | No resolver allowlist; an internal service name would receive the signed body. If a threat appears, an ADR adds a deny-list of the project's own service names at `validate` and 6e. |
| **An event reaches only its own project** | No cross-project events, by the isolation matrix's design; a Stage 5 hosted reading would have to decide whether it wants any. |
| **A sender's clock matters** | ±300 s. A sender with a drifting clock is refused with the same 401 as a forger; the page says so, the log does not distinguish (by design). |
| **The auth service's log is the only record of a refused inbound request** | Not in the database, not in `apg-diag`'s reach (D380). |

---

## Appendix — what to consult, how a run is executed here, the rigs, and the sheets

**Consult, in this order:** this plan's §1 and §5. The stage plan's §5
*Session 34*, §8, §9, §11. `docs/plans/session-33-implementation-plan.md` §1
(D1742–D1777 — what executing 33 found), §5 Runs 3, 5, 6, 8 and 9, §10, and its
Sheets C1–C6. `docs/plans/session-32-implementation-plan.md` §1 D1668–D1672
(the worker's transport and refusal facts). ADR **0195** before any reader;
**0135** (the definer-function grant shape); **0050** (nothing in `api` the
contract does not name — why the emitter is in `app`); **0093** (a `bin/`
command imports only `agentic_postgres` and `yaml`); **0155** (a deploy
recreates what changed); **0160** (the request id flows outward); **0162**
(what a bump permits); **0175** (the arity guard); **0181/0182** (the key; the
dry run); **0183** (a profile only narrows — and is per deployment); **0188**
(a facility); **0190/0193** (rehearsals; a signal, never `docker kill`);
**0198/0206** (a project set and its order); **0200** (the vocabulary in the
lock); **0213** (a reading with no threshold); **0216/0217** (no public
endpoint; a second principal is a scope set the verifier checks); **0218**
(`container_exec`); **0225** (a secret's value checked against its kind);
**0226–0234** (the substrate, the loop, the gates).

**How a run is executed here** (CLAUDE.md §1 and §5, the parts that bite): the
Bash tool is Git Bash; every WSL command is `wsl bash -lc "cd
~/projects/agentic-postgres && . .venv/bin/activate && …"`; anything with a
loop, a nested quote, a `$`, a heredoc or a process substitution goes in a
script file written with the Write tool to `\\wsl$\Ubuntu\tmp\` and run with
its output redirected to a file that is `rm`'d first; **never pipe a gate into
`tail`**; a long gate runs detached with its exit code written from inside;
`chmod 755 bin/*.sh bin/*.py deploy.sh` before every `git add`; commit messages
from a file with `-F`; `PYTHONDONTWRITEBYTECODE=1` and `__pycache__` cleared
before a battery; restore by copy and `cmp`, never `git checkout --`; every
anchor pre-flighted to match exactly once and a miss fatal; a mutation is
evidence only beside a control it cannot reach, in the same invocation; assert
HOW each mutation failed; `--setup-plan` with the variables SET before a trip.
**Any Python that imports `agentic_postgres` outside pytest needs
`PYTHONPATH=src`.** **Every `service_source.load(...)` proof reads the
service's module from `services/auth-api/app/`, not `src/`.** **A `sudo` line
on any sheet has nothing after it**, and every sheet is grepped for `|`, `>`,
`$(` and `&` on every `sudo` product line before it is handed over (D1505).
**`docker run … python - <<'PY'` needs `-i`** and is a heredoc — write the
Python to a file and mount it instead.

**The rigs, summarised** (Run 1, plus 34e in Run 3 and 34f in Run 6; each a
script, each with a control, each naming its images by digest):

| Rig | Subject | Control | Owes |
|---|---|---|---|
| 34a | the emitter's grant; PostgREST cannot address `app`; a rolled-back event; the lint's hole | request roles refused; `/rpc/create_note` 200; a template naming `app_private` refused | D1779, D1780, D1782 |
| 34b | HMAC against `openssl`; the default opener's redirect; four transport failures by type | a one-byte change; the default opener | D1789, D1791, D1800's token table |
| 34c | a `tools/call` with exactly the tool's scope | the same with `meta:read` | D1783's equality |
| 34d | a sink on an `internal` network by alias | a client on the other network only | D1792, D1809 |
| 34e | the two replaced functions' signatures before and after 0036 | — (equality is the reading) | §4's first row |
| 34f | the loop's first end-to-end delivery, dead letter, event wait, schedule and rehearsal delivery | no key file: nothing claimed, steps unaffected | Run 6's integration, before a host |

### Sheet D1 — the reads (all `sudo`; the script tees its own transcript)

The agent stages `/home/op/s34-r10-c1.sh` (derived from `s33-r9-c1.sh`: every
child with stdin `/dev/null`) containing: `bin/upgrade.sh check --project
alpha-dev` and `beta-dev` → `verdict OK`; `bin/doctor.sh --project alpha-dev`
and `beta-dev` → **11 ok + `migrations` PROBLEM (35 of 36; beta 37 of 39) and
deliveries *not read*** — the NEW doctor over the OLD substrate, expected
exactly as D1770 recorded it for 33; `bin/fleet.sh` → 2 projects at `02ffbbd`;
`bin/backup.sh --outputs /etc/agentic-postgres/projects/<key>/outputs.json
info` for both → a full exists; `bin/upgrade.sh plan --project <key>
--candidate /home/op/agentic-postgres/.generated/<key>/outputs.json --json
--also migration_added --also api_operation_added --also
document_schema_migratable` for both → `bump minor`, `requires minor`, `OK`
(manifests UNCHANGED at this point — the facility edit comes after D3);
`bin/dr-kit.sh export … --output /home/op/kit-<date>-pre` (the exact line from
`--help`, printed on the sheet by the agent). The operator runs, at a
terminal, nothing after it:

    sudo bash /home/op/s34-r10-c1.sh

### Sheet D2 — the sentinel, then alpha (`sudo`)

1. **D2a** — the sentinel, `/home/op/s34-r10-sentinel.sh` (derived from
   `s33-r9-sentinel.sh`: the LAST line is the value; count before write; the
   secret path DERIVED from `active-secret-generation.json`), title
   `s34-redeploy-sentinel-<YYYY-MM-DD>`, before-file
   `/root/s34-redeploy-before.json`:

       script -q -e -c "sudo bash /home/op/s34-r10-sentinel.sh" /home/op/s34-r10-sentinel.txt

2. **D2b** — the deploy, at the terminal, nothing after this line:

       script -q -e -c "sudo ./deploy.sh --host host.yaml --project project.alpha.yaml --capabilities capabilities.yaml --through-session 34" /home/op/s34-deploy-alpha.txt

   → exit 0. Step 0 `admitted`. **Step 6 applies ONE migration** — the
   ledger is what is read (D941). Step 6d prints alpha's *no set* line; 6e
   prints *no connectors (the project declares no migration set)*. `auth`,
   `storage`, `mcp`, `docs` recreated. If step 6 fails: **STOP** (§9). Then
   the reads:

       sudo bash /home/op/s34-r10-after.sh alpha

   → `migrate.sh --runtime status` 36 `[X]` lines, `Pending: 0`;
   `doctor` **12 ok**, the `workflow` line reading *deliveries pending 0
   …, dead 0; connectors enabled 0*.

### Sheet D3 — beta, the release (`sudo`)

    script -q -e -c "sudo ./deploy.sh --host host.yaml --project project.beta.yaml --capabilities capabilities.yaml --through-session 34" /home/op/s34-deploy-beta.txt

→ exit 0; 0036 applied AND the project set's `0003` (ledger **36 + 3**,
`Pending: 0` twice); 6d installs **seven** definitions (three new — read the
lines, do not predict their order); 6e *no connectors (the manifest's
connectors.enabled is false)*. Then `sudo bash /home/op/s34-r10-after.sh beta`
→ doctor 12 ok.

### Sheet D4 — beta's facility at the provider (`sudo`, two sheets)

The agent has run `s34-r10-facility.py` as `op` (Run 10's text) and read its
diff and the re-render. **D4a**, the plan:

    script -q -e -c "sudo bin/bootstrap-providers.sh --host host.yaml --project project.beta.yaml --plan" /home/op/s34-r10-bootstrap-plan.txt

→ names exactly ONE thing to create, `connector_signing_key`. Only then
**D4b**, the apply:

    script -q -e -c "sudo bin/bootstrap-providers.sh --host host.yaml --project project.beta.yaml --apply --operator-credential-file /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential" /home/op/s34-r10-bootstrap-apply.txt

→ *created connector_signing_key for beta-dev*; no value printed.

### Sheet D5 — beta, the facility (`sudo`)

    script -q -e -c "sudo ./deploy.sh --host host.yaml --project project.beta.yaml --capabilities capabilities.yaml --through-session 34" /home/op/s34-deploy-beta-facility.txt

→ exit 0; step 0's bootstrap check passes; a new generation materialised with
`connector_signing_key`; no migration pending; 6e installs **four**
connectors (`installed` each; the two outbound WITH an endpoint); `auth`
recreated (its mounted content moved, ADR 0155). Then:

    sudo bash /home/op/s34-r10-after-facility.sh

→ the doctor 12 ok, *connectors enabled 0*; as `postgres`, `SELECT name,
kind, enabled, endpoint IS NOT NULL AS has_endpoint FROM
app_private.connector ORDER BY name` (four rows, all disabled, two with an
endpoint); the key file's NAME, owner and mode in the active generation
(`stat -c '%n %U %a'`, never its content).

### Sheet D6 — the pre-sweep readings (`sudo`)

    sudo bash /home/op/s34-r10-readings.sh

(from `s33-r9-readings.sh`): `doctor capacity --host host.yaml` (ceilings
unchanged — nothing moved a cap); `doctor --project beta-dev` (the BEFORE
counts); `doctor usage --project beta-dev` (exit 6 expected, D1712's wording);
then, LAST, the two op-owned copies installed (`install -o op -g op -m 0600
…`, D1767) — **the agent confirms both name Run 9's `source_commit` AND are
outputs v19 before D7**.

### Sheet D7 — the sweep (`sudo`)

    sudo bash /home/op/s34-r10-launch.sh

It detaches the sweep and returns at once; ~40 min; the agent reads
`/home/op/s34-r10-host.code` (0 or 5) and `/home/op/s34-r10-host-summary.txt`.

### Sheet D8 — the rehearsal (`sudo`)

    script -q -e -c "sudo bash /home/op/s34-r10-rehearse.sh" /home/op/s34-r10-rehearse.txt

(the agent writes the exact `bin/rehearse.sh` lines from its `--help`:
`--plan` first, then the scenario itself on `beta-dev`) → the plan names
`note-embedded` (the first outbound by name) and `127.0.0.1:9`; the
rehearsal's verdict PASS with three attempt times ≥ 2 s apart, `dead`,
`connect_failed`, the heartbeat moved; the evidence file's path.

### Sheet D9 — the cleanup (`sudo`)

    script -q -e -c "sudo bash /home/op/s34-r10-cleanup.sh" /home/op/s34-r10-cleanup.txt

(from `s33-r9-cleanup.sh`): the sentinel removed (the container, database and
title DERIVED from the deployed document and the before-file; expect `DELETE
1` — D1547 still makes this a root `psql`); **every connector disabled** with
`SELECT app_private.connector_disable(name, NULL) FROM app_private.connector`
as `postgres` (expect four rows, all `disabled` or `already_disabled`);
`doctor --project beta-dev` (the AFTER counts: runs by status, deliveries
pending/dead, connectors enabled 0); `bin/dr-kit.sh export … --output
/home/op/kit-<date>-post`. The agent then fetches the deploy transcripts, the
sweep's evidence half and the rehearsal evidence by `scp` as `op`, and copies
the two new kits off-host to `~/dr-kits/` in WSL (verified there, 0700/0600
kept on ext4).
