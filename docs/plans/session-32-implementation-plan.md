# Session 32 — The durable step substrate and workflow execution

**Status: PLANNED, not started.** Planned 2026-09-21 at `1948d21` (Session
31's close, one documentation commit past the tagged and deployed `4344a1f`).
Nine runs, all on `main` directly. **Nothing in this document has been
executed.** Every number below was read from the tree at `1948d21` or is
marked as the measurement the run owes.

**Brief:** `docs/plans/stage-4-plan.md` §5 *Session 32* whole (Builds /
Already true / Must not / Measures / Closes), its rows **D1516** (one
substrate, in this session, for pillars III and IV), **D1521** (two sessions:
32 the substrate and execution, 33 the second principal), **D1527**
(`THR-WORKER` before code), **D1529** (the restore-test row); §3's ordering
rule *31 before 32* (a worker is charged against a declared capacity, which
now exists) and *32 before 33 and 34* (both consume the substrate); §7's row
for Session 32 (definition compile offline-declared under `apg dev`,
execution and `worker-restart` live) and its item 1 (*a claim about a worker
is a claim about at-least-once plus an idempotent upstream, proved by
killing the worker*); §8 whole (the rows marked 32: the worker's tables, the
worker's role, a step under the same scope check, a revoked token stopping
on its next request, the audit order the worker must not reorder, the
worker's environment, a worker container's generation, the restore-test row,
`workflow status` as a reader); §9's stop conditions for 32; §11. Plus
`docs/scope-closure.md` §24 *What Session 32 inherits, in order* (five
items: the seventh claimant, **D1636 first**, `storage_cleanup.py`'s lease
discipline, a worker holds nothing an agent identity does not hold, D1248
stays 33's), CLAUDE.md §9 (the same items as rows), and
`docs/plans/session-31-implementation-plan.md` §10 (what 31 created for 32:
*a worker is a seventh claimant*; D1581's observation belongs to the first
deploy that moves a generation and nothing else) and its Sheets A1–A6 (the
trip's shape).

**Shape:** nine runs. Runs 1–7 each push and read that commit's CI verdict
by full SHA (`gh api "repos/Virabyan99/agentic-postgres/actions/runs?head_sha=
<40 chars>"`, three buckets, D1057); Run 8 is the trip; Run 9 is the close
and — **read D1644 before calling it documentation** — commits, gates and
reads CI if it touches `src/`.

**Product version at close:** `CURRENT_SESSION` **32**; `template_version`
**`1.10.0`** — **migration 0034** (three tables, one heartbeat table, nine
definer functions, in `app_private`), **three new routes on the auth
service** (`POST /workflows/runs`, `GET /workflows/runs/{run_id}`, `POST
/workflows/runs/{run_id}/cancel`), **one new command** (`bin/workflow.sh`
with six verbs), **a loop inside the auth process** (no new container, no
new role, no new secret, no new compose service), **a twelfth doctor check**
(`workflow`, no threshold), **one new rehearsal** (`worker-restart`), **one
new evidence member** in the restore drill, **a deploy step 6d**, **one new
documentation page** (`docs/workflows.md`); **no outputs, capability, lock,
secret or host schema move; no new deployed-document field** (§1 D1654).
ADR 0162: a new released migration and a new API operation are each
*minor*; `upgrade plan` reads `migration_added` only when declared (§1
D1666), so the reading in Run 7 declares it and the release paragraph says
so. A `major` — a new required secret, an operator manifest that stops
validating — is §9's stop.

**Written for whoever picks this up cold, and it will be a different model
than the one that planned it.** Every path below was read from the tree on
2026-09-21 at `1948d21` by five explore passes over `src/`, `bin/`,
`services/auth-api/`, `compose.yaml`, `migrations/`, `schemas/`, `tests/`
and `docs/`, and each is cited by `path:line`. Every third-party or product
claim is measured in Run 1's rigs with a control, or is marked as the
measurement a run owes — never assumed. **Read CLAUDE.md §1 in the launch
folder before the first command, then this plan's §1, then the appendix.**
If a step here and the tree disagree, **the tree wins and the disagreement
is a divergence row** (next free `D` after §1's table), never a silent
reconciliation. **When this plan names a line number, open the file at that
line and read the surrounding twenty lines before editing** — the numbers
were right on 2026-09-21 and `ruff format` moves them.

**The four sentences the executor most needs, in case nothing else is read:**

1. **The worker is a loop inside the `auth` container, not a new container**
   (§1 D1645, ADR 0226). It runs as the auth service's own database role,
   uses the auth service's own pool, mints each step's token through the
   auth service's own issuance path, and calls tools over HTTP against the
   `mcp` container the way every live proof already does. It holds nothing
   the auth service did not already hold, and it adds no claimant, no
   secret, no role, no compose service and no document field.
2. **A step's idempotency key is derived from the run and the step — never
   the attempt** (§1 D1646). A replay after a crash gets the same row back
   with outcome `replayed`; that is what makes the step exactly-once at the
   upstream. `PT412` is the *control*, not the proof.
3. **The three tables carry no row-level security and no request role holds
   a privilege on them** (§1 D1647) — the same posture every `app_private`
   table in this tree has. FORCE RLS on an `app_private` table would be a
   new pattern nothing reads.
4. **D1636 is repaired in Run 2, before a single line of the worker**
   (scope-closure §24 item 2). The ceilings reading groups by Compose's own
   project label and stops dropping the database.

---

## 0. Where the session starts

```
HEAD            1948d21 on main, local = origin, clean. Deployed: 4344a1f
                (1.9.0) on both projects, three documentation commits behind
                (git diff --name-only 4344a1f..1948d21 filtered to src/ bin/
                services/ migrations/ templates/ schemas/ compose.yaml
                deploy.sh VERSION is EMPTY except src/agentic_postgres/
                capacity.py -- data, D1641's caveat; re-run the filter in
                Run 1 and write the answer in its Done).
VERSION         1.9.0. CURRENT_SESSION 31. Outputs schema 18. host.yaml
                schema 3. Capability manifest schema 4. Lock schema 4.
                Project manifest schema 6. 33 released migrations
                (0033 = 20260917120033).
REGISTRY        238 requirements. 145 claims (24 declared offline). 225 ADRs.
                ID families: DEP CFG DBX SEC API AGT STO REC OPS DX REL CAP
                IDN EVAL FLEET TEN DEV EVD GEN STU NODE
                (tests/contract/test_acceptance_registry.py:84).
                NEXT FREE: D1645, ADR 0226. This plan uses D1645-D1667 in §1
                and ADR 0226-0229. NEXT FREE AFTER THIS PLAN: D1668, ADR 0230.
EVIDENCE        evidence/session-31.json: 145 claims, 139 passed, 5 not_run,
                1 failed (documented_path by decision). port_allocation
                not_run by choice (D1568); the rotation trio and
                replacement_host_restore not_run.
HOST            62.238.99.122. host.yaml schema 3: 3814 MiB / 2214 reserve /
                37 GiB / 8 GiB reserve. Both projects at 1.9.0, source_commit
                4344a1f, deployed_through_session 31, doctor 11 ok each.
                Beta's manifest names projects/example (project schema 6);
                alpha's is v4 with NO project set (the control). doctor usage
                exits 6 on beta until an agent tool call is made there
                (D1643) -- THIS SESSION'S TRIP MAKES THAT CALL.
                Host scripts: s31-r7b-{checkout,gate,launch,cleanup}.sh and
                s31-r8-readings.sh under /home/op. Retired JWKs at
                /home/op/s30-retired-<key>-jwk.json (unread by any sweep).
                /home/op/host.yaml.pre-s31 is to be removed on this trip's
                cleanup sheet (31's §10).
```

**What exists, measured at `1948d21`, and the session builds on:**

- **The agent plane is the auth service image in a third mode.** There is no
  `src/agentic_postgres/mcp_tools.py`; the plane is `services/auth-api/app/
  mcp_*.py`, run as `APP_MODE: mcp` (`compose.yaml:1702`) from the same
  build context as `auth` (`compose.yaml:1662-1663`, ADR 0121).
  `APP_MODES = frozenset({"auth", "storage", "mcp"})` (`services/auth-api/
  app/settings.py:34`). The image's entrypoint is **one** uvicorn process
  with no `--workers` (`services/auth-api/Dockerfile:118-121`), so a task
  started in the lifespan runs exactly once per container.
- **The write path, in order** (`services/auth-api/app/mcp_tools.py`):
  `bounded()` opens the audit record via `audit_begin` in a thread
  (`:787-815`, fail-closed for a write `:801-808`, the windowed quota's
  `None` → `BUDGET_EXCEEDED` `:834-842`), runs the work under the tool's
  concurrency slot (`:844-870`), closes the record (`:894-938`).
  `invoke_write(lock, *, base_url, token, request_id, tool, arguments,
  idempotency_key, dry_run)` (`:547-652`): scope check `_write_for` (`:225-
  257`, `SCOPE_NOT_HELD` at `:252-256`), `requires_approval` refusal (`:591-
  596` — the sentence *"a workflow needs durable pending state, a second
  principal and a notification plane, none of which exists"* is at `:588-
  590` and again at `mcp_errors.py:51-55`), dry-run permitted (`:603-608`),
  key shape `_idempotency_key` (`:536-544`, pattern `^[\x21-\x7e]{8,255}$`
  at `:518`), request built (`:615`), upstream `execute_write` (`:620-628`),
  row-count shape (`:632-636`), byte budget and return (`:644-652`) — **the
  result carries `row_count`** (`:575-577`). Nine denial boundaries
  `DENIAL_REASONS` (`mcp_errors.py:175-185`); caller-facing tokens
  `CALLER_FACING_TOKENS` (`:63-71`); `PT412` translates to
  `INPUT_NOT_PERMITTED` *"this idempotency key is already bound to a
  different call; use a new key"* (`:103-106`).
- **Idempotency is per (agent, key), and a replay re-reads the row.**
  `app_private.agent_idempotency` (`migrations/templates/0029-agent-
  idempotency-keys.sql:101-112`, PK `(agent_id, idempotency_key)`);
  `agent_idempotency_claim(p_agent, p_key, p_tool, p_fingerprint, p_row_id)`
  returns NULL for *claimed, proceed* and the prior `row_id` for *replay,
  re-read that row* (`:194-241`); `PT412` is raised for a malformed key
  (`:164-166`), a key bound to a different tool or argument fingerprint
  (`:225-229`) and a write with no key at all (`:288-292`, `:373-376`); a
  replay increments `replay_count` (`:230-233`) and the audit outcome is
  `replayed` (`:67`). The header is `Idempotency-Key` (`mcp_query.py:104`),
  sent with `Dry-Run` (`:113`, `:127`; `mcp_upstream.py:384-391`). The
  dry-run branch runs **before** the claim and aborts with `APDRYRUN`
  (`0030-agent-dry-run.sql:118-120`, `:147`, `:158`), outcome `dry_run`.
- **Tokens.** `POST /auth/agent-token` takes exactly `{agent_id, secret}`
  (`services/auth-api/app/models.py:264-272`; `routes.py:772-795`);
  `AuthService.agent_token` (`service.py:449-496`) verifies the hash, then
  refuses a non-`active` status (`:483-484`) and an expired secret (`:485-
  491`), then `self.issue(self._as_credential(credential), token_use=
  "agent")` (`:495`). TTL `TOKEN_TTL_SECONDS = MAX_TTL_SECONDS` (930 s,
  `:35-36`). **`authenticate()` accepts an ACCESS token only** (`service.py:
  260-300`, the comment at `:299`) — every `/admin/*` route calls it then
  `require_scope` (`routes.py:668-669` etc.); an agent token is refused
  there (ADR 0114). `TOKEN_USES = ("access", "agent")` (`claims.py:52`).
  Revocation is `PATCH /admin/agents/{id}` with `{"status": "revoked"}`
  (`routes.py:914-950`); the hook `agent_claims_are_current` (`0018-agent-
  read-plane.sql:60-78`) stops a revoked agent on its **next request**, not
  at expiry (`:80-87`); its exact-tuple match on the sorted scope array
  means a token may carry the agent's stored scopes and nothing narrower.
- **The MCP runtime is a long-running HTTP process** on `APG_LISTEN_PORT`
  8080 (`compose.yaml:1717`), path `/mcp` (`mcp_runtime.py:96`), streamable
  HTTP with `stateless_http=True` (`:509`), bearer verified against the
  mounted JWKS by `AgentTokenVerifier` (`:225-326`, `token_use: agent`
  only), networks `internal` and `edge` (`compose.yaml:1788-1790`). **Every
  live proof calls a tool with one JSON-RPC POST** — `mcp_rpc` at
  `tests/deployment/test_session9_agent_writes.py:139-156`: `api_call(url,
  method="POST", token=token, body={"jsonrpc": "2.0", "id": 1, "method":
  "tools/call", "params": …}, headers={"Accept": MCP_ACCEPT})` with
  `MCP_ACCEPT = "application/json, text/event-stream"` and an SSE-framed
  reply parsed by `sse_result` (`test_session8_agent_plane.py:69`, `:84-
  96`). The runtime holds no pool and no credential (`main.py:160-163`);
  `MCP_VARIABLES` is the closed allowlist (`settings.py:492-518`) and
  `FORBIDDEN_VARIABLES` (`:524-544`) forbids the auth mode `APG_JWKS_FILE`.
- **The auth service** is FastAPI + uvicorn (`main.py:34`), one router per
  mode (`:243-249`), a `lifespan` that loads settings, the signing key, the
  hasher and **a psycopg pool of `min_size == max_size == APG_POOL_SIZE`**
  (`main.py:79-165`; `db.py:76-102`; `AUTH_POOL_SIZE` = `config.API_APP_
  DEFAULTS["pool_size"]` = **4**, `config.py:280-284`), connecting as
  `identity.roles["auth_service"]` (`rendering.py:1927`; `compose.yaml:
  1292`) directly to `postgres:5432` (`compose.yaml:1286-1291`, D289), with
  `mem_limit` 384 MiB, `pids_limit` 64, `cpus` 1.0, `stop_grace_period 15s`,
  `restart: on-failure:5`, `user 65532`, `read_only`, `/tmp` tmpfs
  (`compose.yaml:1182-1334`). **It runs no background task of any kind**
  (0 hits for `create_task`, `BackgroundTasks`, `Thread(` under `services/
  auth-api/app/` other than a comment at `storage_cleanup.py:281`). Its
  process overhead is measured at 61 MiB and charged at 96 (`profile.py:
  116-128`); its connection budget is `pool_size + AUTH_RESERVED_CONNECTIONS`
  = 4 + 2 (`config.py:461-470`, `:541-557`).
- **The lease discipline to copy** is `services/auth-api/app/storage_
  cleanup.py` (303 lines), driven by three definer functions in
  `app_private` (`storage_repository.py:172-230`): `storage_claim_cleanup_
  batch(p_holder, p_limit, p_lease_seconds, p_write_grace_seconds)` sets
  `cleanup_lease_expires_at = now() + make_interval(secs => p_lease_
  seconds)`, increments attempts, selects `FOR UPDATE SKIP LOCKED` ordered
  by expiry NULLS FIRST (`0016-storage-cleanup-write-window.sql:103-144`;
  *the LEASE PREDICATE is the correctness mechanism, SKIP LOCKED is
  throughput* `:65-69`); `storage_finish_cleanup` is `WHERE cleanup_lease_
  holder = p_holder` and `False` means *lease lost*, not an error
  (`storage_repository.py:216-230`); a failure leaves the lease to expire
  (`storage_cleanup.py:225-235`); the deadline is **monotonic** (`:174`,
  `:185-187`) and `deadline = started + lease_seconds - lease_margin_
  seconds()` (`:208-209`) with the margin **derived from the client's
  timeouts as a function, never a constant** (`:86-100`); the three
  orderings are in the module docstring (`:11-31`); **`SWEEP_POOL_SIZE = 1`
  fits inside `STORAGE_RESERVED_CONNECTIONS` rather than being a claimant**
  (`:71-83`; asserted `tests/contract/test_storage_cleanup.py:554,563`).
  It is an operator verb run by `docker exec` inside the storage container
  (`bin/storage-admin.py:284-294`, `:495`), **as the storage service's own
  role and environment** (`sweep_from_environment`, `storage_cleanup.py:
  289-293`). There is no scheduler, timer or loop anywhere (`systemd/` holds
  backup units only).
- **The definer-function pattern in `app_private` with a service role** is
  `0016:103-180`: `LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET
  search_path = pg_catalog, pg_temp`, `REVOKE ALL … FROM PUBLIC`, `GRANT
  EXECUTE … TO {{storage_service}}`, `RESET ROLE` below the privileges
  block (D285); schema USAGE granted once by the migration that first
  granted it (`:172-173`, D337). `0033-agent-record-retention.sql:318-326`
  is the *grant to nobody* pattern (a function only a superuser calls). The
  `api.agent_audit_begin` shape reads identity from GUCs, never arguments
  (`0019:140-141`, `PT403` at `:147-150`). **No `app_private` table has RLS
  or a policy** — `FORCE ROW LEVEL SECURITY` appears only on `app.notes`/
  `app.tasks` (`0003:57-60`, `0007:74,90,96`); `app_private` tables are
  protected by *no request role holds any table privilege* (`0019:99-105`,
  `:372-377`). `lint_project_set`'s FORCE-RLS rule matches `app.` only
  (`migrations.py:827-846`) and forbids `app_private` in a project set
  (`:143`).
- **Migrations.** 33 templates under `migrations/templates/`, `-- migrate:
  up` first, `SET LOCAL ROLE {{object_owner}};` before owner statements,
  `RESET ROLE;` after the privileges block, the `AP900` down block
  (`0033:333-337`). Versions are `20260917120NNN`-shaped (0033 =
  `20260917120033`, `migrations/manifest.json`, last entry); the manifest
  entry carries `version, name, template, placeholders, description`.
  `bin/migrate.sh freeze-lock` is the only writer of `migrations/released.
  lock.json` (`bin/migrate.sh:85-86`); nothing pins the count to a literal
  (`tests/contract/test_rendered_migrations.py:80` derives it; the literal
  *33* lives in `capacity.py` prose at `:260,268,287,313,483` and
  `test_rendered_migrations.py:580`). `tests/contract/test_migrations_apply_
  as_the_migration_user.py:95-163` is the rig that applies every released
  migration **as `migration_user`** against a real container built from the
  product's own `dev_environment.role_statements`; its `privilege()` helper
  (`:394-408`) is the grant-assertion shape. Migrations naming `api` end
  with `NOTIFY pgrst, 'reload schema';` (`0019:384`); 0033 omits it and says
  why (`:328-331`).
- **`apg dev`** (ADR 0203): `bin/dev.sh up|status|down|reset|seed|psql
  --project FILE` → `bin/dev.py` → `src/agentic_postgres/dev_environment.py`;
  the container is `apg-dev-<key>` (`:68`), the port ephemeral on loopback
  (`:301`), the state at `.generated/.dev/<key>/state.json` (`:77-81`).
  **The database only** — no PostgREST, no auth, no token (`bin/dev.sh:20-
  25`). `tests/contract/test_dev_environment_cluster.py:67-107` is the
  module-scoped fixture (`apg dev down`, `up`, read the state, `down` in
  `finally`) and `as_superuser()` the psql helper. The gate exercises the
  round trip at `bin/session-31-check.sh:1268-1274`.
- **The lock.** `capability_compiler.compile_lock` (`src/agentic_postgres/
  capability_compiler.py:800-896`) writes `tools_sha256` over the tools
  after the profile is applied (`:891-895`); `canonical_bytes` at `:899-
  907`. The file is `MCP_LOCK_FILENAME = "mcp-capability-lock.json"`
  (`runtime_override.py:427`) under `deployed_output.rendered_path(key)`
  (`bin/deploy-project.py:2284,2701`; `bin/doctor.py:582`; `bin/rehearse.
  py:222`), mounted at `/etc/mcp/capability-lock.json` and **`/etc/auth/
  capability-lock.json`** (`:428,435,844,903`; `compose.yaml:1301-1308`) —
  **the auth service already loads the lock** (`main.py` lifespan,
  `scope_map.load_vocabulary(settings.capability_lock_file)`). `bin/mcp-
  contract.sh lock --outputs FILE --project FILE` resolves a project's lock
  to stdout (`bin/mcp-contract.sh:31-32`, `:68-81`; `bin/mcp-contract.py:
  303`). The reader in the service is `mcp_lock.load_lock` (`mcp_lock.py:
  293-373`), with `Tool.capabilities` a tuple of `CapabilityRef(name,
  version, lifecycle, risk)` (`:109`, `:186`) and `requires_approval` /
  `supports_dry_run` (`:196-197`). **A step names a CAPABILITY `name@
  version`, and a capability compiles into a tool**: in the release's
  snapshot (`contracts/snapshots/mcp/mcp-capabilities.canonical.json`, six
  tools) `create_note` is backed by capability `create_note@1.0.0`
  (arguments `p_title`, `p_content`, `supports_dry_run`, no approval),
  `query_resource` by `query_notes@1.0.0` and `query_tasks@1.0.0`,
  `update_task_status` by `update_task_status@1.0.0` (`p_task_id`,
  `p_expected_status`, `p_new_status`, `idempotent: true`), and
  `list_resources`/`describe_resource` are metadata. The example project's
  own contract (`projects/example/contracts/mcp-capabilities.canonical.
  json`) compiles two: `query_note_embeddings@1.0.0` (read) and
  `set_note_embedding@1.0.0` (**write, `requires_approval: true`**,
  `projects/example/capabilities.yaml:46-68`). Beta's deployed lock is the
  release's joined with the project's (ADR 0201).
- **Capacity.** `capacity_probe.read_ceilings` (`src/agentic_postgres/
  capacity_probe.py:152-178`) already lists containers by `runtime_override.
  COMPOSE_PROJECT_LABEL` (`:167-168`); **the under-report is entirely in
  `capacity_reading.ceilings_from_inspect` (`capacity_reading.py:288-325`),
  which groups by `Config.Labels["apg.project.key"]` (`:316`) and `continue`s
  a container without it (`:317-318`)** — `postgres`, `pgbouncer`, `dbmate`
  and `dbmate-project` carry no such label (`compose.yaml`; the nine that do
  are at `:96,357,744,945,1017,1115,1217,1546,1685`). `runtime_override.
  database_container_filters` (`runtime_override.py:74-87`) is the Compose-
  label selector (`COMPOSE_PROJECT_LABEL = "com.docker.compose.project"`,
  `COMPOSE_SERVICE_LABEL = "com.docker.compose.service"`, `:70-71`), whose
  value is `naming.compose_project_name(key)` (`:66-69`). Readers of the
  ceilings: `bin/admit.py:196-200`, `diagnosis.py:802-813`, `bin/deploy-
  project.py:2046-2047`; proofs `test_admission.py:345-368`,
  `test_capacity_reading.py:205`, `test_session31_capacity.py:375`. The
  connection budget sums six claimants (`config.py:1407-1414`) enumerated by
  `BUDGET_CLAIMANTS` (`tests/contract/test_agent_plane_contract.py:295-
  304`), whose `_summands_of_the_budget_check()` AST-parses the expression
  (`:307-335`); `max_connections` 56 (`config.py:218`).
- **What a new role, container or document field would cost — and this plan
  spends none of them.** A role: `naming.ROLE_SUFFIXES` (`naming.py:159-
  182`, append only), `schemas/outputs.schema.json:841-904` (`databaseRoles`,
  `additionalProperties: false`), outputs **v19** (`output_migrations.py:104`
  and the v6 precedent at `:590-648`), `bootstrap_statements.py:96-115` and
  `:156-161`, a `*_CONSUMER` + `activate_*` in `bin/postgres-bootstrap.py`,
  a summand and `BUDGET_CLAIMANTS`, `secrets.required.yaml`, the literal
  `13` at `tests/contract/test_naming.py:97`. A compose service: `config.
  SERVICE_RESOURCE_DEFAULTS` (`config.py:652-662`), `rendering.SERVICE_
  RESOURCE_ORDER` (`:627-637`), and `test_process_limits.py:54,89-90`'s
  `20`/`9`/`11`. A document field: v19 plus a `migrate_v18_to_v19`, an
  `outputs_chain._steps` entry and an isolation-matrix classification.
- **The doctor** is eleven checks assembled at `bin/doctor.py:739-759`
  (the count is asserted by `test_doctor_with_no_verb_runs_the_eleven_
  checks_unchanged`, `tests/contract/test_doctor_readings.py`); `agent_
  record` (ADR 0213) is the check with **no threshold** and is the shape to
  copy; the database container is selected at `:144-153` by
  `naming.compose_project_name` and the Compose labels; the store is
  reached through the container at `:784-` and `:802`; statements are
  constants (`DENIALS_SQL`, `bin/fleet.py:50-58`). Verdicts `OK/WARN/
  PROBLEM/UNKNOWN` (`diagnosis.py:80-88`); `exit_code` returns 6 for
  `UNKNOWN` as well as `PROBLEM` (D1643).
- **Rehearsals.** Nine scenarios in `rehearsal.SCENARIOS` (`src/agentic_
  postgres/rehearsal.py:79-93`); a scenario is a planner `_name(facts) ->
  Plan` registered in `_PLANNERS` (`:834-844`) with a `verdict()` arm
  (`:965-`); `bin/rehearse.py` gathers facts (`:192-`), observes (`:343-`),
  takes `scenario` from `choices=(*rehearsal.SCENARIOS, "reverse")`
  (`:763`); `bin/rehearse.sh:33-73` is the usage (its header `:4` still
  says *Eight scenarios*, D1664). **`service-termination`'s induce is
  `kill -KILL <host pid>` of the container's main process from the host's
  PID namespace, never `docker kill`** (`rehearsal.py:293-330`; ADR 0193:
  `docker kill` is never restarted under any policy; a signal to the
  process is, by `on-failure:5`); its observer arm is `bin/rehearse.py:349-
  `. `admission-refused` (`:773-831`) is the newest and the file list it
  touched is §5 Run 6's list. Records land at `evidence/rehearsal-<key>-
  <scenario>-<id>.json` (`bin/rehearse.py:9`, `:612`).
- **The restore drill** `bin/restore-test.sh --target-time ISO8601
  [--project-dir DIR]` (`:44-48`; exit codes `:26-33`) restores into a
  drill volume and **queries it**: `bin/restore-test.py:459-480` is the
  evidence dictionary (`requested_target`, `achieved_recovery_point`,
  `achieved_lsn`, `timeline_id`, `schema_version`, the two ledgers' count),
  `query(plan, sql)` at `:397`, the owner-scoped smoke at `:641-648`.
  `REC-PITR-001`'s proofs are `tests/recovery/test_future_pitr.py`
  (fixtures `tests/recovery/conftest.py:20,31,41`) with offline halves in
  `tests/contract/test_restore_test_command.py`.
- **Evidence and gates.** `OFFLINE_CLAIMS` is `src/agentic_postgres/
  evidence_claims.py:106-205` (24 members; Session 31's six at `:199-205`);
  `CLAIMS` at `:253-` (31's block `:448-457`); `CLAIM_INTRODUCED_IN`.
  `tests/acceptance-registry.yaml` entries carry exactly `{id, priority,
  target_session, test_nodeids, description}` (`test_acceptance_registry.
  py:158-171`); `ID_PATTERN` at `:84`; the sweep-selector guard reads the
  **newest** gate for the verbatim `run_suite "p0 and not future and not
  live_host and not external"` (`:306-333`); every test module carries
  `pytestmark` (`:601-`, D1240). `tests/conftest.py:86-189` is the closed
  `ENVIRONMENT_VARIABLES` tuple (25 names); `APG_ADMIN_PASSWORD_FILE` is
  deliberately outside it (D1619). `bin/session-31-check.sh` (1634 lines):
  header `:1-117`, usage `:182-467` (the derived half `:446-466`), parser
  `:503-697` (27 accepted flags, seven named refusals), modes `:1141-1358`
  / `:1360-1556` / `:1558-1623`, the host export roster `:1439-1509`,
  `write_evidence()` `:768-789`, exit from the writer's status `:1336-
  1338` / `:1545-1547` / `:1612-1614`. `tests/contract/test_cli_contract.
  py`: `SHELL_COMMANDS` `:42-188`, `PYTHON_COMMANDS` `:190-246`,
  `COMMANDS_WITH_VERBS` `:430-445`, the executable bit read from the git
  index `:311-325` (D1188), `test_every_command_in_bin_is_covered_by_this_
  module` `:1005-1039`. `bin/apg.sh` holds no verb list: `apg workflow` is
  `bin/workflow.sh` the moment the file exists (`bin/apg.sh:136-151`), and
  `APG_PROJECT` applies when the verb's own `--help` shows `--project FILE`
  (`:199-216`).
- **Live-proof fixtures** (`tests/deployment/conftest.py`): `project_a`/
  `project_b` from `APG_PROJECT_A_OUTPUTS`/`_B_` (`:129-136`), `api_call`
  (`:897-956`), `app_base` (`:1233-1255`, from `routes.app` when `ready`),
  `psql` (`:959-1029`, `docker exec -i` into the cluster with a role/claim
  prelude), `service_container(project_key, service)` (`:2045-2084`, by
  `apg.project.key` + `com.docker.compose.service`), `as_root` (`:92-105`),
  `sh`/`sh_status` (`:60-90`). **An agent for a proof is created by SQL**
  through `app_private.auth_create_agent(name, description, role, scopes[],
  owner_id, secret_hash, expires_at)` and its token taken from `POST
  {app_base}/auth/agent-token` — `mcp_writer_session` at `test_session9_
  agent_writes.py:158-226` (the hasher from `service_source.load("hashing")`,
  teardown `DELETE FROM app_private.agents`), `mcp_agent_session` at
  `test_session8_agent_plane.py:154-219`, `create_agent` at
  `test_session21_agent.py:144`. Audit rows are read with `psql`, never
  through the admin endpoint (`test_session9_agent_writes.py:236-262`).
- **Documentation guards.** A new page under `docs/` must be linked from
  `docs/README.md` (`tests/contract/test_documentation_index.py:462-473`);
  a bump needs a row in `docs/upgrade-guide.md`'s release table (`:364`)
  and the version at `README.md:7`; `--session N` literals in the current-
  path documents must equal `CURRENT_SESSION` (`test_session12_documented_
  path.py:164-194`). `docs/operator-guide.md` ends at §16 *The node as a
  finite resource* (`:1143`); `docs/threat-model.md`'s table is `:19-35`
  with `THR-NOISY-NEIGHBOUR` at `:35` (nine cells); `docs/decisions/README.
  md` rows are `| [NNNN](file.md) | Title | Session | Status |`.

---

## 1. The divergence table

Six columns. Each row is a **measured fact about the tree at `1948d21`** set
against what the brief (the stage plan's §5 *Session 32*, its §1 rows, §8,
scope-closure §24 and CLAUDE.md §9) says, with the decision this plan takes.
**Next free number after this table is D1668.** Rows the runs add go below
D1667, in execution order, and the header's *Status* paragraph is rewritten
at the close to say which run added which.

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D1645** | Stage plan §5: *"First measurement: the worker as a loop inside the `auth` process versus a new `worker` container — memory, a connection claim, and whether a new container needs a secret with no default; the rig decides and the ADR records."* | **Three facts decide it before a rig runs, and the rig then measures the cost of the decision rather than choosing it.** (1) The one token-minting route takes the agent's SECRET (`models.py:264-272`), which the worker may not hold, so a separate container would need a NEW way to obtain an agent's token — a shared secret with `auth`, or a route that mints for a claimed step — and that is the stage's failure mode in its purest form (§9: *a principal that holds more than the identity it acts for*). (2) The tree's only lease worker runs INSIDE the service whose role it uses (`storage_cleanup.py`, `bin/storage-admin.py:284-294`), fitting inside that service's reserve rather than becoming a claimant (`:71-83`). (3) A new container costs a role (outputs v19, a seventh summand, a secret, a bootstrap activation — §0's list) and a service (`test_process_limits.py:54`'s `20`), for a process whose only job is to poll one table and make one HTTP call at a time. | **The worker is a loop in the `auth` process: an asyncio task started by `lifespan` in `auth` mode only, using `application.state.pool` and `application.state.service`, supervised so an exception in the loop never stops the verifier.** No new container, role, secret, service, summand or document field. Rig 32a (Run 1) measures what this costs the auth image's RSS with the loop idle and under a run, and Run 8 reads the auth container's cgroup `memory.current` on the host before and during the three-step run (D765's method, as `op`). **The flip criteria, written before the rig:** the loop's idle RSS delta exceeds 32 MiB, or its under-load delta exceeds 96 MiB (the container's 384 MiB cap minus the hash budget's four-concurrent figure of 259, `config.py:576-592`), or the image is found to run more than one uvicorn process. Any of the three stops Run 5 and reopens the decision as a row. | The `mcp` mode already proved the image can be more than one thing (ADR 0121); a loop is the storage sweep made resident, which is the pattern §24 item 3 says to copy; and every alternative adds a holder of authority the agent identity does not have. The cost is that a worker restart is an `auth` restart — which is the rehearsal this session builds anyway, and a stronger one: the signer dies mid-run and the run survives. | **0226** |
| **D1646** | D1521: *"the idempotency key per (run, step, attempt) through the existing header"*; §5 Measures: *"a step replayed after a crash refused with `PT412` through the worker (control: a fresh key accepted)"*. | **A replay is NOT refused; it is re-read.** `agent_idempotency_claim` returns the prior `row_id` for the same `(agent, key)` with the same tool and fingerprint and the plane re-reads that row with outcome `replayed` (`0029:194-241`, `:67`; ADR 0181's title says exactly this). `PT412` fires for a malformed key, a key bound to a DIFFERENT tool or fingerprint, or a missing key (`0029:164-166`, `:225-229`, `:288-292`). A key per ATTEMPT would make a retry after a crash write a SECOND row — the defect ADR 0213's rig 28b measured when a claim is deleted. | **The key is derived from the run and the step, never the attempt: `wf-<run uuid>-<step name>`** (52–100 printable ASCII characters, inside `^[\x21-\x7e]{8,255}$`), computed by `workflow_enqueue` and stored on the step row so every attempt presents the same bytes. A step whose call returns outcome `replayed` is finished as `replayed` with the row it got back — that is the at-least-once → exactly-once mechanism. **`PT412` is the CONTROL**: the live proof reuses a step's key with different arguments and expects the refusal, proving the fingerprint is checked. | The plane already implements the semantics the worker needs; a worker that treated `PT412` as *done* would mark a step succeeded that never ran. The claim the stage plan wants — *a step replayed after a crash is exactly-once at the upstream* — is proved by the row count, not by a refusal. | 0181, **0227** |
| **D1647** | Stage plan §5: *"`app_private.workflow_definition`, `workflow_run`, `workflow_step` with FORCE RLS"*; §8: *"The worker's tables (32)"* under *RLS, FORCE, the pre-request hook*. | **No `app_private` table in this tree has RLS.** `FORCE ROW LEVEL SECURITY` appears only on `app.notes` and `app.tasks` (`0003:57-60`, `0007:74,90,96`); no `CREATE POLICY` names an `app_private` table; the posture is *no request role holds any table privilege* (`0019:99-105`, `:372-377`) and access goes through definer functions. FORCE RLS applies to the table's OWNER — the role every definer function runs as — so a forced table with no policy is unreadable by the functions that exist to read it, and a permissive policy for the owner would be a policy nothing else evaluates. | **The three tables and the heartbeat table copy `0019`/`0029`: owned by `{{object_owner}}`, no grant to any role, every access through a `SECURITY DEFINER` function with `SET search_path = pg_catalog, pg_temp`, `REVOKE ALL FROM PUBLIC` and one explicit `GRANT EXECUTE`.** The stage plan's sentence is recorded as unmet for a reason; a contract proof asserts `has_table_privilege` is false for every request role and for `auth_service` on all four tables, and `has_function_privilege` is true for `auth_service` on the eight it may call and false for `agent_reader`, `agent_writer`, `authenticated`, `anon`, `storage_service` (the `anon` control, `test_agent_audit_plane.py:1355`). | Copying the pattern every `app_private` table already has is the only shape whose posture is already measured (rig 28b, ADR 0213: a DELETE by `SET ROLE` into four roles refused). A new pattern in the substrate every later session consumes would be paid for by 33 and 34 without a reader. | **0227** |
| **D1648** | Stage plan §5: *"SECURITY DEFINER functions (`workflow_claim_step`, `workflow_finish_step`, `workflow_park`) granted to the worker's role only"*; §8: *"A project's identities are derived once, in `naming` — the worker's role (32)"*. | The worker has no role of its own (D1645). The role the loop runs as is `auth_service`, which already holds `agent_record_size` (`0033:324`) and the auth plane's functions, and the auth API's routes are the surface a workflow is started and read from. | **Every function the loop or a route calls is granted to `{{auth_service}}` and nothing else** — `workflow_enqueue`, `workflow_claim_step`, `workflow_finish_step`, `workflow_park`, `workflow_cancel`, `workflow_run_status`, `workflow_heartbeat`, `workflow_counts`. **`workflow_install_definition` is granted to NOBODY** (`0033:318-326`'s pattern): the deploy and `apg dev` call it as the bootstrap superuser through the container, and an operator's SQL never enters a product surface. `naming.py` derives nothing new; the §8 row is recorded as *n/a: no new identity*. | A grant to the role an HTTP-reachable process runs as is the smallest set that makes the routes work; an install grant to that same role would put a definition-writing authority behind an identity reachable over HTTP, which is `0020`'s reason for keeping a DELETE out of the audit reader. | **0226**, **0227** |
| **D1649** | Stage plan §5: *"the worker re-mints the agent's token per step through `/auth/agent-token` so revocation lands at the next boundary by the existing path"*; Must not: *"Cache a token across steps."* | `/auth/agent-token` requires the agent's secret (`service.py:449-496`), which is hashed at rest and held by the agent alone. The route's checks AFTER the hash comparison are the ones revocation depends on: `status != "active"` (`:483-484`) and `secret_expired` (`:485-491`), then `issue(…, token_use="agent")` (`:495`). | **The loop mints through the same service method behind that route, minus the hash comparison.** `AuthService.agent_token` is split into `_agent_for_issue(agent_id) -> credential` (the lookup, the status check, the expiry check, in the existing order and with the existing messages) and the hash comparison; `agent_token` calls both; a new `step_token(agent_id)` calls only the first and issues. **One token per step attempt, minted after the claim and dropped at finish** — never stored on the run, never reused across steps, asserted by an AST proof that no attribute or dict key named `token` outlives the step function's frame and by a unit proof counting `step_token` calls against steps. A refused mint (`AuthenticationFailed`) finishes the step as `token_refused` and stops the run with `stopped_reason: agent_not_active`; **no tool call is made**. | The existing path IS the status and expiry check; the secret proves possession, and possession is what a claimed step in the database proves instead. Revocation therefore lands at the next step boundary through exactly the code an agent's own mint would hit, and mid-step through the hook (`agent_claims_are_current`) exactly as any agent call does. | **0226**, **0229** |
| **D1650** | Stage plan §5 Measures: *"a revoked agent's run stopping at the next boundary with `scope_not_held` audited (control: an unrevoked one completing)"*. | An audit row is written BY THE AGENT through `agent_audit_begin` as the caller (ADR 0135); when the mint is refused there is no token, no call and no row. A revocation that lands MID-step is refused by the hook before the audit function runs (`0018:238`, `PT403`), which the plane records as a structural refusal (`AUDIT_UNAVAILABLE` for a write, `mcp_tools.py:801-808`) — not `scope_not_held`. | **The claim is rewritten to what the tree can show: a revoked agent's run stops at the next step boundary with `stopped_reason: agent_not_active`, the step finished `token_refused`, and the audit table holds NO row for that step** (the control run, unrevoked, holds one row per step). The mid-step arm is not separately proved: it is the plane's own revocation proof (`tests/security/test_session9_revocation.py`), unchanged, and the run then fails the step as `upstream_refused` on the next claim — recorded in the ADR, not asserted live. | A proof that asserted `scope_not_held` would fail on first execution (§7 question 2); the property the stage plan cares about — the run stops and nothing is written — is stronger when the audit table is EMPTY for the step than when it holds a denial. | **0229** |
| **D1651** | Stage plan §5: *"`run` enqueues as the invoking agent identity"*; `apg workflow status\|cancel` as the agent's own reading. | The auth API authenticates ACCESS tokens only: `authenticate()` refuses `token_use: agent` by decision (`service.py:299`, ADR 0114), and every `/admin/*` route calls it (`routes.py:668-669, 802-803, 920-921`). An agent holds an AGENT token, minted for PostgREST and the plane; no route on the auth service accepts one today. `AgentTokenVerifier` (`mcp_runtime.py:225-326`) verifies exactly that token use, in the same package. | **Three new routes on the auth service in `auth` mode — `POST /workflows/runs`, `GET /workflows/runs/{run_id}`, `POST /workflows/runs/{run_id}/cancel` — authenticate with a SECOND authenticator, `AuthService.authenticate_agent(authorization)`, which accepts `token_use: agent` only, verifies with the same key set and claim contract as `authenticate`, then loads the agent record and refuses unless `status = 'active'` and the record's `authz_version` equals the token's (the hook's tuple, `0018:60-78`). `authenticate` is unchanged and still refuses an agent token; each authenticator refuses the other's use, asserted in both directions.** The routes are the agent's own: a run is enqueued as the token's agent, and status/cancel refuse a run another agent owns with the same 404 a missing run gets (no existence leak). No new scope: enqueue requires the agent's stored scopes to cover the definition's `required_scopes` union, refused as `scope_not_held` otherwise. | An MCP tool for starting a run would move the compiled contract's `tools_sha256`, every lock and the harness's cases; a human-token route would start a run as the wrong principal. ADR 0114's decision — one token use per API — is amended to *one token use per route set*, and the amendment is the smaller change because it keeps every existing route's refusal byte-for-byte. | **0229** (amends 0114) |
| **D1652** | Stage plan §5: *"Ends on a host: a three-step run …, the worker killed between steps two and three, resumed, and the audit correlated"*; rehearsal `worker-restart`: *"a run parked mid-step survives the worker's death and resumes exactly once, proved by the idempotency table"*. | A kill *between two steps* is a race against a poll interval and a millisecond transaction; nothing in the product lets a test place it, and a hook that did (`--stop-after-step`) would be test code in production. The state a crash leaves is fully described by the substrate: a step `claimed` by a holder that will never finish, an unexpired lease, and — in the worst case — the upstream already committed under the step's key. ADR 0193: the termination rehearsal signals the process from the host's PID namespace and `on-failure:5` restarts it. | **Two deterministic instruments, each proving one half.** (a) The live proof CONSTRUCTS the post-crash state as root: it enqueues a run with the loop unable to see it (the run's agent is created, the run enqueued, then step 2's write is performed through the plane by the proof AS THE AGENT with the step's derived key, and step 1 is left `queued`); the loop then runs step 1, hits step 2's upstream, gets `replayed`, finishes it as such, runs step 3 — and `app.notes` holds exactly one row for step 2's title. (b) The rehearsal `worker-restart` kills the auth process (the termination scenario's induce, `rehearsal.py:293-330`, on `auth` rather than the health service) while a run is PARKED on a retry backoff, and reads the heartbeat (D1667) before and after; the live proof drives it with a run whose first step fails retryably, and asserts the run finishes after the restart with `attempt = 2`. The audit is correlated by the request id each step attempt stores (D1667). | Each instrument is deterministic and each fails for exactly one reason; together they cover the two states a death can leave. A timing-based kill would pass most days and teach nothing the day it failed. | **0227**, 0193 |
| **D1653** | Stage plan §3, §10 and CLAUDE.md: *"a worker is a seventh claimant and must be charged against a DECLARED capacity"*; 31's §10: *"32 charges its `unreclaimable` … and its connections against `capacity` and `max_connections` before it is built"*. | The loop's database work is two transactions per step — a claim and a finish — each milliseconds, on the auth service's existing pool of four (`db.py:76-102`, `min_size == max_size`). The tool call itself holds no database connection in the worker's process: it is an HTTP request to the plane, whose own connection is PostgREST's, already summed. `unreclaimable_mb` is the DATABASE's figure (`config.py:678-691`) and is not where a sidecar's anon is charged; the reserve is (D1583). | **No new summand and no new memory claim: the loop is a client of the auth pool and its anon is the auth container's, measured.** `BUDGET_CLAIMANTS` is unchanged and its AST guard runs. The live proof reads `pg_stat_activity` for the `auth_service` role during the run and asserts the count never exceeds `pool_size + AUTH_RESERVED_CONNECTIONS`. The memory reading is rig 32a offline and the cgroup read on the host (D1645), recorded in the envelope (`capacity.py`, a `MACHINE` `Measurement`) — a number, not a claim in the document. | The seventh claimant turned out to be a user of the sixth's pool; charging it twice would be D767's mistake in reverse. What §24 item 1 asks — that the worker's cost be seen by admission — is met by the cost being INSIDE figures admission already charges. | **0226** |
| **D1654** | Stage plan §7 item 3: *"Every new deployed-document field is classified in the isolation matrix in the session that adds it: 32's worker"*. | Nothing here is per project and absent from the document: the routes hang off `routes.app` (published), the tables live in the project's own database, the loop runs in the project's own `auth` container. Definitions are rows, not files the document points at. | **No deployed-document field is added; outputs stays v18; the matrix and `evidence.ISOLATED_FIELDS` are unchanged.** Recorded as unmet for the same reason as D1591. | A field added so a row can be written is D816's shape. | — |
| **D1655** | Scope-closure §24 item 2: *"The repair is to group by Compose's own labels, as `runtime_override` already does for the database selector."* | `ceilings_from_inspect` groups by `Config.Labels["apg.project.key"]` (`capacity_reading.py:316`) and DROPS a container without it (`:317-318`); `read_ceilings` already filters by `COMPOSE_PROJECT_LABEL` (`capacity_probe.py:167-168`). The Compose label's VALUE is the compose project name (`runtime_override.py:66-69`), which is `naming.compose_project_name(key)` — derived from the key, not equal to it. `Reading.ceilings` is `dict[str, int]` keyed by *project* (`capacity_reading.py:136`) and three printers print the keys (`bin/admit.py:196-200`, `diagnosis.py:802-813`, the deploy). | **`ceilings_from_inspect` groups by `com.docker.compose.project`; a container carrying neither label is reported under the key `"(unlabeled)"` rather than dropped; the dict's keys are compose project names and every printer says so** (*ceilings by compose project*). `capacity_probe.read` maps a compose name back to a project key when a deployed document under `root` publishes that `compose.project_name`, and leaves the compose name otherwise — so production prints `alpha-dev 2240, beta-dev 2240` and a rig prints `apg-rig32 …`. `unbounded` keeps naming pgbouncer, postgrest and docs by container name. The offline proof feeds an inspect payload with a labelled postgres and expects 2240 per key; the live proof expects **4480** on the host. | Grouping by the label Compose applies to every container is the repair `runtime_override.py:41-70` already made for D587's first instance; mapping back through the documents keeps the printers' vocabulary the operator learned on Session 31's sheet. | 0221 |
| **D1656** | Stage plan §5: *"budgets are consumed as that agent"*. | Every budget is applied by the plane per call or per process (`mcp_budgets.py`; the windowed quota inside `agent_audit_begin` as the calling agent, `0028:119-135`). The worker is one more HTTP client of the `mcp` process carrying the agent's token. | **Free, and asserted rather than built**: the live run's audit rows show the quota consumed under the run's agent; a definition with more steps than the agent's `quota_calls` is not special-cased — the step that exceeds the window fails `budget_exceeded`, terminal, and the run fails naming it. | A second budget accounting in the worker would be the *second retry loop in the upstream client* the stage plan forbids, one layer over. | 0129, 0131, 0180 |
| **D1657** | Stage plan §5: *"a three-step run over the example project's tools"*. | The example project's OWN contract compiles two capabilities: `query_note_embeddings@1.0.0` (a read over `note_embeddings`) and `set_note_embedding@1.0.0`, which is **`requires_approval: true`** (`projects/example/capabilities.yaml:58`) and so is refused by `validate` in this session (D1660). Beta's deployed lock JOINS the release's six tools with the project's (ADR 0201), so `create_note@1.0.0` and `query_notes@1.0.0` are in beta's lock. Alpha has no project set and therefore no `projects/<slug>/workflows/` to install from. | **The trip's definition is `projects/example/workflows/notes-roundtrip.yaml`: `create_note@1.0.0` → `query_notes@1.0.0` (a `query_resource` read over `notes`, `limit: 5`) → `create_note@1.0.0`, and the run is performed on BETA.** Alpha is the control the other way: `POST /workflows/runs` naming any definition returns the *no such definition* refusal, because alpha installs none. A second definition, `notes-retry.yaml`, exists for the rehearsal arm (D1652 b): its first step is `update_task_status@1.0.0` with an `p_expected_status` that cannot match, `retry: {max: 1, backoff_seconds: 45}` — a deterministic `write_conflict`, retryable, parked long enough to kill the process under it. | The stage plan's phrase meant *the tools beta serves*, and the release's notes capabilities are the only writes on that lock a workflow may run before Session 33. | **0228** |
| **D1658** | Stage plan §5: *"`dry-run` runs every step under ADR 0182"*; §7: *"definition compile and dry-run offline-declared under `apg dev`"*. | A dry-run is a rolled-back write performed BY THE PLANE (`0030`); `apg dev` is the database alone (`bin/dev.sh:20-25`) — no plane, no PostgREST, no token. Nothing offline can run a step. | **`dry-run` is a run flag, live only.** `workflow_run.dry_run` is set at enqueue; the loop passes `dry_run: true` on every WRITE step and runs reads unchanged; a write's outcome is `dry_run` with `row_count` 0 and no row lands. The offline claims cover the compiler (`validate`) and the substrate (the functions under a real cluster); the dry-run is one live proof on the trip. The stage plan's *offline-declared* is recorded as met for compile and unmet for dry-run. | Declaring a dry-run claim offline would be ADR 0202's rule broken the day it was written. | 0182, 0202 |
| **D1659** | Stage plan §5: `apg workflow init\|validate\|dry-run\|run\|status\|cancel`. | `bin/apg.sh` needs no edit (`:136-151`); `test_cli_contract.py` requires the command in `SHELL_COMMANDS`, the Python in `PYTHON_COMMANDS`, verbs in `COMMANDS_WITH_VERBS` with a per-verb `--help` (`:430-536`); `bin/agent.sh`'s `init` prints to stdout and writes no file (`:1-23`). `bin/api.sh` takes its token from `APG_API_TOKEN` and the base URL from `--project-outputs FILE` (`bin/api.py:31`, `:139`). | **Six verbs, exactly the stage plan's names.** `init` prints a definition skeleton to stdout from the project's lock (the `agent.sh init` shape); `validate` compiles every file under `projects/<slug>/workflows/` against the project's lock and exits 5 naming the first refusal; `run` posts to `{routes.app.url}/workflows/runs` with the token from **`APG_AGENT_TOKEN`** and prints the run id; `dry-run` is `run` with `dry_run: true`; `status` and `cancel` call the other two routes. `--project FILE` on `init`/`validate`, `--project-outputs FILE` on the three HTTP verbs (the `api.sh` shape). The command holds no SQL and no route not in an enumerated table. | The dispatcher's contract (a verb is a script) and the API command's contract (a token from the environment, an enumerated route set) are both kept whole. | **0229** |
| **D1660** | Stage plan §5: *"A definition: `projects/<slug>/workflows/<name>.yaml` naming steps as `tool@capability_version` from the project's lock … compiled and validated against the lock the way `mcp-contract.sh` validates a manifest (a tool the lock does not compile is refused at `validate`)"*. | A CAPABILITY is versioned; a TOOL is not (`Tool.capabilities: tuple[CapabilityRef]`, `mcp_lock.py:186`; `query_resource` is backed by two capabilities). A definition's referent must be the versioned thing. Nothing today stores a definition; the runtime reads its lock from a mounted file the deploy writes (`runtime_override.py:427-435`). | **A step names a capability `name@version`; the compiler resolves it to the tool that serves it (and, for `query_resource`/`run_report`, to the resource), refusing by name: an unknown capability, a version the lock does not carry, a `lifecycle` other than `active`, a capability whose tool is `metadata`, a capability with `requires_approval` (*approval steps arrive in Session 33*), an argument the tool does not declare, a `{{steps.<name>.<field>}}` reference to a later or unknown step, `retry.max` > 5, `backoff_seconds` > 300, a step `timeout_seconds` below the tool's `timeout_ms`/1000 or above 600, a run `timeout_seconds` above 3600. The compiled body carries `required_scopes` (the union), `lock_tools_sha256` and `source_sha256`. **Definitions are ROWS in `workflow_definition`, installed by the deploy at a new step 6d and by `apg dev up`, through `workflow_install_definition` as the bootstrap superuser; a `(name, version)` is immutable and re-installing it with a different `source_sha256` refuses the deploy at exit 5** (D912's rule for a definition). The loop does NOT compare `lock_tools_sha256` at run time: it holds no lock, the PLANE enforces the lock on every call, and the digest is a record of what `validate` compiled against, reported by `status` so a reader can tell whether the lock moved since. | A definition is a project artefact like a migration set: reviewed in the checkout, installed by the deploy, immutable once applied, fixed forward by a new version. A file the loop read at run time would let a parked run resume against a definition that changed under it. | **0228** |
| **D1661** | Stage plan §5: *"`retry: {max, backoff_seconds}` and `timeout_seconds`"*; Must not: *"Build a second retry loop in the upstream client."* | The plane translates every upstream outcome into one of seven caller-facing tokens (`mcp_errors.py:63-71`) and names `write_conflict` as *a retry instruction* (`mcp_tools.py:571-573`); transport failures and timeouts reach a client as an HTTP error or a socket error, not a token. | **Retryable: a transport error, a timeout, and `write_conflict`. Terminal: every other token and any 4xx from the plane.** A retryable failure with attempts left PARKS the step with `resume_after = now() + backoff_seconds` (park IS the backoff, and a parked step IS the pause the stage plan says not to build separately); with none left it fails the step and the run, naming the token. The run's `timeout_seconds` bounds `now() - started_at` at every claim and fails the run as `timed_out` when exceeded. The step's `timeout_seconds` is the HTTP client timeout for its call and the lease's basis (D1667's margin). No retry is attempted inside the call. | The classification is the plane's own vocabulary and the loop adds no judgement of its own to it; three retryable causes are the three the plane itself calls transient. | **0227** |
| **D1662** | D1529: *"Session 32 owes one restore-test row proving a restored cluster carries a parked run and its steps (`restore-test.sh` over a drill volume, ADR 0151)"*. | `bin/restore-test.py:459-480` is a fixed dictionary of readings taken from the drill; nothing reads `app_private` beyond the two ledgers. `REC-PITR-001`'s live proofs are under `tests/recovery/` (root, `tests/recovery/conftest.py:31`). | **The drill's evidence gains one member, `workflow_runs`: `{"count": n, "by_status": {…}, "definitions": n}` read from the drill, or `null` with a `reason` when the table is absent (a drill of a pre-0034 backup, ADR 0195).** A new `REC-WF-001` under `tests/recovery/test_session32_workflow_restore.py` runs `bin/restore-test.sh` with a target time AFTER the trip's runs and asserts the run ids the live cluster holds are in the drill's count; its offline half in `test_restore_test_command.py` asserts the member and its null arm. | A claim that new state is inside the thing already restored is the whole of D1529's argument, and the reading that proves it is one query. | 0151 |
| **D1663** | The rehearsal and the doctor must find the `auth` container and the cluster. | `service_container` in the deployment conftest filters by `apg.project.key` + `com.docker.compose.service` (`:2045-2084`); `bin/doctor.py:144-153` selects the database by `naming.compose_project_name` + the two Compose labels; `bin/rehearse.py` gathers `facts.containers` and `facts.container_pids` per service (`rehearsal.py:293-301`). | The doctor's `workflow` check runs its statements through the cluster the way the eleven checks do; the rehearsal takes `auth` from `facts.containers["auth"]` and its pid from `facts.container_pids["auth"]` exactly as the termination scenario takes the health service's. Nothing new selects a container. | The selectors that survived D587 are the ones to reuse. | — |
| **D1664** | The tree's own prose. | `bin/rehearse.sh:4` says *"Eight scenarios"*; there are nine (`rehearsal.py:79-93`) and ten after this session. `bin/apg-diag.sh:140` says the `apg.project.key` label is on *three of thirteen* services; it is on nine of twenty (D1620). | Run 6 corrects both to a count read from the tuple and from `compose.yaml` and says so in its Done. | D1595's class, third time. | — |
| **D1665** | 31's §10: *"Why `auth` was recreated by Session 30 Run 7's deploy and not Run 8's stays UNDETERMINED (D1581) … the observation belongs to the first trip whose deploy moves a secret generation and nothing else — Session 32's, if its deploy is such a one."* | This session's deploy moves the auth IMAGE (new routes, a new module) and the compose interpolation is unchanged; a generation moves only if a secret is rotated, which nothing here does. `auth` will be recreated because its image changed, which observes nothing about D1581. | **D1581 is NOT observable on this trip either**, and §10 says so rather than implying it was watched. The first generation-only redeploy remains owed. | ADR 0195: an observation not made is not folded into one that was. | — |
| **D1666** | ADR 0162's table: *a new released migration → minor*; §5 Run 7 prices the release with `upgrade plan`. | `upgrade_plan.classify_document_changes` derives only `image_digest`, `implementation`, `secret_required_added`, `capability_added` from two rendered documents (`:222-253`) and says so: *"A function that inferred `migration_added` from a `schema_version` move would be answering a question it cannot see the evidence for."* `migration_added` and the API classes are DECLARED by the caller through `bin/upgrade.py`'s `DECLARABLE` (`:129-138`). | **Run 7's reading declares `migration_added` and `api_operation_added` through the command's own declaration flag (read `bin/upgrade.py:116-138` for its spelling), and the release paragraph says the floor is `minor` BY DECLARATION, not by the document diff.** Without the declaration the reading floors at `patch` (D1625's shape) and would be wrong in the reassuring direction. | The third release in a row whose price the command cannot fully see (D1561, D1626); the declaration mechanism exists for exactly this, and using it is cheaper than teaching the command to read a lock file. | 0162 |
| **D1667** | Stage plan §5: *"the audit correlated"* by run; §8: *"An unauditable write does not happen — the worker must not reorder"*; `storage_cleanup.py`'s margin *derived from the HTTP client's timeouts*. | The plane's audit row carries `request_id` from the `X-Request-Id` header the caller sends (`mcp_query.py:78`, `:94`; `0019:73-97`); it carries no run id and adding one is an audit schema move (33's, D1248). The audit order is the PLANE's (`bounded()`), which the loop cannot reorder because it never touches the audit functions. `lease_margin_seconds()` is a function of the client's timeouts (`storage_cleanup.py:86-100`). | **Each step attempt mints a `request_id` (uuid4), stores it on the step row at claim, and sends it as `X-Request-Id`; correlation is `workflow_step.request_id = agent_audit.request_id`, proved live by a join.** The loop's lease is `step.timeout_seconds + lease_margin_seconds()` where the margin is `2 × (connect + read timeout)` of the loop's HTTP client, a function; the loop stops before its lease does (`deadline = started + lease - margin`, monotonic) and abandons a step it cannot start in time rather than starting it late. **A heartbeat row** (`app_private.workflow_worker`, one row per project: `holder`, `started_at`, `seen_at`) is written by `workflow_heartbeat(p_holder)` at every poll; `holder` is `<hostname>:<pid>:<start monotonic>` so a restart is visible as a NEW holder. The doctor's `workflow` check reports `heartbeat_age_seconds` and the counts and thresholds nothing. | The audit's own key is the correlation the plane already supports; the heartbeat is the reader ADR 0193 says a rehearsal must read; the margin as a function is the discipline §0 quotes. | **0227** |

**Rows the runs added, in execution order.**

| # | Run | Plan says | Tree does / measured | Decision |
|---|---|---|---|---|
| **D1668** | 1 | §5 Run 5: the holder is `f"{socket.gethostname()}:{os.getpid()}:{int(time.monotonic())}"`. | **`socket` is a banned transport name.** `TRANSPORT_NAMES` (`test_auth_service_shape.py:643-645`) holds `socket`, and `test_every_transport_in_the_service_is_declared_with_a_reason` refuses any module under `services/auth-api/app/` that names one without a `TRANSPORT_ALLOWLIST` row. The tree solved this exact problem in Session 7: `storage_cleanup.worker_identity` uses `os.uname().nodename` and says why -- *"the same fact from a call that cannot open a connection, whereas `socket` is a module that can"*, after `socket` tripped the guard on that module's first run. | **`HOLDER = f"{os.uname().nodename[:40] or 'unknown'}:{os.getpid()}:{int(time.monotonic())}"`** -- `worker_identity`'s shape, with `time.monotonic()` in place of its random component because a restart must be visible as a NEW holder and a monotonic tick is what moves across one. No exemption is bought for the safe half of a network module. |
| **D1669** | 1 | §5 Run 5: the loop calls the plane over HTTP with "the SAME client library" as `mcp_upstream`. | That library is `urllib`, and `TRANSPORT_ALLOWLIST` grants it **per module**: `mcp_upstream.py`, `mcp_query.py`, `mcp_health.py`. A new `workflow_worker.py` naming `urllib` fails the guard. | **`TRANSPORT_ALLOWLIST` gains one row, `"app/workflow_worker.py": frozenset({"urllib"})`, with a comment naming ADR 0226 and what the call is** (one request to the project's own `mcp` container carrying the step's token). A row is a reviewed act, and widening an allowlist to a measured set is not weakening (CLAUDE.md §6). |
| **D1670** | 1 | §5 Run 5: `CONNECT_TIMEOUT_SECONDS` and `READ_TIMEOUT_SECONDS` "taken from the plane's client constants by import"; §1 D1667: the margin is `2 x (connect + read timeout)`. | **Those two constants are not the plane's.** `mcp_upstream.py` holds ONE timeout, `UPSTREAM_TIMEOUT_SECONDS = 10` (`:72`), because `urllib.request.urlopen` takes a single `timeout` and has no connect/read split. `CONNECT_TIMEOUT_SECONDS = 5` and `READ_TIMEOUT_SECONDS = 15` live in `storage_client.py:60-61` and are **boto3's, for R2**. Importing them into the loop would make its lease a function of an object-store client it never calls. | **`def lease_margin_seconds() -> int: return 2 * mcp_upstream.UPSTREAM_TIMEOUT_SECONDS`** -- still a FUNCTION over an imported constant, never a literal (`storage_cleanup.py:86-100`'s discipline, which exists so a change to the constant cannot leave a stale copy behind). The proof binds to the constant: mutating `UPSTREAM_TIMEOUT_SECONDS` must move the margin. |
| **D1671** | 1 | §5 Run 5: the loop finishes a step by "reading the plane's outcome word from the result's audit outcome field if present"; §2 `WF-WORK-001`: *"a `replayed` result finishes the step as replayed"*. | **There is no such field, and a replay is indistinguishable from a first write in the plane's result.** `invoke_write` returns exactly `{tool, row_count, row, dry_run}` (`mcp_tools.py:644-652`), `row_count` is `len(rows)`, and both writes return one composite row. **Rig 32c measured it**: the same key twice returns the SAME row id, `app.notes` holds one row, and the word `replayed` appears ONLY in `app_private.agent_audit.outcome` on the `database`-source row (`committed:1` then `replayed:0`), which the HTTP result does not carry. | **The loop finishes a successful call as `succeeded` and does not assign an outcome it cannot determine** (ADR 0195). `replayed` stays in `workflow_step_outcome` as a value the SUBSTRATE may hold. Exactly-once is proved where it actually lives: one `app.notes` row, `agent_idempotency.replay_count = 1`, and one `committed` + one `replayed` audit row. `WF-WORK-001`'s node id becomes `::test_a_successful_call_finishes_the_step_and_the_replay_is_not_the_loops_to_see`. Surfacing it through the result would move `mcp_tools.py`'s reviewed shape, the catalog and every caller -- a contract move to make a sentence true. |
| **D1672** | 1 | §5 Run 5 / §1 D1661: "an error whose token is in `RETRYABLE_TOKENS`"; "Terminal: every other token and **any 4xx from the plane**". | **A tool refusal is not a 4xx and is not a JSON-RPC `error` member. Rig 32b measured both shapes from a sibling container**: a `tools/call` refusal is **HTTP 200** with `result.isError: true` and the reason in `result.content[0].text`; only a protocol-level failure carries `error`. A loop that classified on HTTP status would read **every** tool refusal as a success. | **The classifier reads `result.isError` first, takes its token from `result.content[0].text`, and treats a JSON-RPC `error` member as terminal.** HTTP status is checked only for 401/403 (a refused bearer), which is a `token_refused`-shaped stop rather than a step failure. `test_a_terminal_refusal_fails_the_run_naming_the_boundary` feeds rig 32b's BYTES, not a hand-written envelope. |
| **D1673** | 2 | §5 Run 2 step 2: `capacity_probe.read` maps a compose-name key to a project key "when a document under `root` publishes `compose.project_name` equal to it (`read_deployed` at `:55` already loads them for `committed`)". | **The DEPLOYED document publishes no `compose` block at all.** `naming.compose_project_name`'s own docstring says it: *"The RENDERED document publishes this as `compose.project_name`. The DEPLOYED document does not publish it at all -- it carries `project`, `host`, `routes`, `database` and the rest, and `compose` is not among them"* (`naming.py:704-708`), and `postgres_volume_name`'s repeats it for the volume (D592). `capacity_probe.read` walks the DEPLOYED documents under `/etc/agentic-postgres/projects/<key>/`, so the mapping as specified **would never have fired**, and production would have printed `apg-alpha-dev 2240` instead of `alpha-dev 2240` -- a Sheet B4 line that did not match its own expectation. | **The mapping derives through `naming.compose_project_name(key)` over the keys `read` already listed from `root`, and needs no document field.** That is not a second derivation under ADR 0002: the function *is* the authority and says so (`naming.py:711-714`). A compose project this node runs whose directory could not be listed **keeps its compose name** rather than being mapped to a key that was never established (ADR 0195). The proof's control is exactly that second entry. |
| **D1674** | 2 (repair) | §2: *"`NODE-READ-001` keeps every node id; the proof `test_ceilings_sum_hostconfig_memory_and_ignore_unbounded_containers` is edited to feed a labelled postgres and expect it counted (a passing test made stricter)."* | **Run 2 also REPLACED a proof, and the plan's sentence only anticipated one being edited.** `test_an_unlabelled_container_belongs_to_no_project` asserted the drop, so it could not be made stricter -- it had to become `test_a_container_with_neither_label_is_reported_not_dropped`. `tests/acceptance-registry.yaml` still named the old node id, and **Run 2's targeted list did not include `test_acceptance_registry`** even though CLAUDE.md §5 requires it of *"a run that renames, adds or removes a test function"* (D1119). The four targeted modules passed; **CI went red** on six proofs across `test_acceptance_registry` and `test_evidence_claims`, all naming the same dangling node id. | **`NODE-READ-001` is repointed at the replacement and gains the run's two other new proofs**; `bin/render-acceptance-matrix.py --write` regenerated the matrix. **The rule that failed is the targeted list, not the guard**: D1486's point exactly -- a list derived from a diff cannot see a caller the diff does not touch, and the gate can. Every later run in this session adds `test_acceptance_registry` and `test_evidence_claims` to its targeted list whenever it renames, adds or removes a test function, and Run 3 does so. |
| **D1675** | 3 | §5 Run 3: `workflow_claim_step(...) RETURNS TABLE (step_id uuid, run_id uuid, position integer, name text, ...)`. | **`position` is a `col_name_keyword`**: accepted as a COLUMN name in `CREATE TABLE` and a **syntax error** as a bare OUT parameter in `RETURNS TABLE`, where the parser is in a type-function-name context. Measured: the migration created all four tables and then died with `syntax error at or near "position"` on the claim's signature. | **The claim returns `step_position` and `step_name`.** `name` is renamed beside it although it is legal, so the pair reads as one decision rather than as one workaround, and the `COMMENT ON FUNCTION` says why. `workflow_step.position` and `.name` keep their names -- the table is where an operator reads them. |
| **D1676** | 3 | §5 Run 3: *"`docs/migrations.md` gains 0034's line in whatever table lists the released migrations (read the page)."* | **There is no such table.** The page is conceptual, and its one listing is a heading reading **"The five that exist"** above five versions from Session 1 -- written when there were five, never updated, and wrong by twenty-nine by the time this session opened. | **No table is invented.** The heading becomes *"Which ones exist"* and points at `migrations/manifest.json` with the one-line command that counts it, saying explicitly that the page deliberately keeps no second copy. **D1664's class, fourth instance** (`rehearse.sh`'s *"Eight scenarios"*, `apg-diag.sh`'s *"three of thirteen"*, and now this): a count in prose is a count nothing updates. |
| **D1677** | 3 | §5 Run 3: the proofs are written; nothing anticipated how the proof module's own SPELLING would read to another guard. | **`test_every_call_to_a_released_function_uses_a_released_arity` scans the proofs as well as the product (D887), and it walks the parentheses of the call AS WRITTEN** (D464). Two spellings in the new module defeated it: a signature passed to `has_function_privilege` as `workflow_install_definition({signature})`, whose single f-string placeholder is not a bare identifier so `_is_a_call` could not classify it as a signature (D890); and an `enqueue` call split across two Python literals, whose quoting broke the paren walk so the scan read four arguments where five are passed. | **Both repaired in this module's spelling, never by a row in `DELIBERATE_RETIRED_CALLS`** -- that list is for calls that are SUPPOSED to name a retired parameter, and using it here would have excused a proof from a guard it was not entitled to be excused from. The signature is written out as six literal types; the enqueue call is one expression under the line limit, with its input document a named constant carrying the reason. |
| **D1678** | 3 | §5 Run 3 lists the targeted modules; nothing says a new migration invalidates the rendered fixtures. | **The rendered fixtures are an INPUT to two of them.** `test_rendered_migrations::test_one_file_per_declared_migration` compares `.generated/fixture-alpha-dev/migrations/rendered-manifest.json` against `migrations.sets_for(document)`, and a render taken before 0034 exists is short by one. Re-rendering ONLY alpha then failed `test_project_migration_sets::test_the_rendered_document_records_the_set_it_applied` with *"two projects rendered by one release disagree about the release lock"* -- the second fixture still carried the old digest. | **A run that adds a migration re-renders BOTH example projects** (`project.example.yaml` and `project.second.example.yaml`, `--render-only`) before its targeted list, and says so. The gate reads FOUR renders (D1507); a run that renders one has told itself something the gate will not believe. |
| **D1679** | 3 | §5 Run 3: the template carries prose in the house voice. | **A migration template may not contain `{{` in its COMMENTS.** `migrations.render`'s residue check refuses any `{{...}}` surviving substitution -- *"A marker the substitution pattern did not match is a typo, not a literal"* -- and it fired on a comment describing the compiler's `{{steps.<name>.<field>}}` reference syntax. | **The prose says "a step reference by name" instead.** Recorded because the guard is right and the next writer will hit it: the template language has no escape, and a migration explaining a placeholder syntax must describe it in words. The guard working is the finding; no change to `migrations.py`. |
| **D1680** | 3 (repair) | §5 Run 3 writes migration 0034 **with its grants**; §5 Run 5 writes `workflow_repository.py`, the module that calls them. | **A grant may not ship a run ahead of its caller.** `test_migrations.py::test_every_granted_function_has_a_caller` refuses a `GRANT EXECUTE` on a function no Python and no other migration calls -- *"a grant nobody can audit against a caller that does not exist"*, 0011's rule, guarded as a CLASS since D837 -- and its docstring names this failure shape exactly: *"the shape of a plane half-built one run early."* Run 3's first push went **red in CI** on seven of the eight (`workflow_run_status` escaped only because the identically-named ENUM TYPE appears in the table definitions, which is a blind spot worth knowing and not worth acting on). The targeted list could not see it: `test_migrations.py` was in neither the plan's list nor D1674's addition. | **`services/auth-api/app/workflow_repository.py` ships in Run 3, beside the grants it audits**, with `tests/contract/test_workflow_repository.py`. It is pure plumbing -- eight statements, every value a parameter, no decision in it -- so moving it earlier costs Run 5 nothing but the file. **The alternative was worse in both directions**: splitting the grants into a later migration would put a function's privileges in a different file from the function (and 0034 is a floor once applied, D912), and there is no allowlist in this guard by design. Run 5 now writes the loop, the routes and `step_token` against a repository that already exists and is proved. |
| **D1681** | 4 | §5 Run 4 *Read first*: `src/agentic_postgres/rendering.py:1-120` (**the `{{name}}` substitution helper's name and where it lives**); §5 Run 4 item 2: *"placeholders resolved with the renderer's `{{name}}` substitution"*. | **There is no substitution helper in `rendering.py`.** That module publishes a render transactionally; it interpolates nothing. The tree's one `{{name}}` substituter is `migrations.render` over `PLACEHOLDER = \{\{([a-z][a-z0-9_]*)\}\}` -- and it is SQL's: the pattern cannot match a dotted name like `{{input.title}}`, the `RESIDUE` guard then refuses the whole text for carrying `{{`, every value is `quote_identifier`ed or `quote_literal`ed, and the error is `MigrationError`. Reusing it would mean widening the migration renderer's accepted set so a non-SQL caller could use it. | **`workflow_definition` carries its own `REFERENCE`/`BRACES` pair and its own `DefinitionError`**, with `migrations.render`'s residue DISCIPLINE borrowed rather than its code: a `{{` the reference pattern did not consume is a typo, not a literal (D1679 from the other side). A reference is VALIDATED at compile time and resolved at run time -- `input` arrives at enqueue and a prior step's field arrives in the `prior` object `workflow_claim_step` already returns -- so the compiler refuses only what could never resolve: a step that runs later, and a step that does not exist. | Widening `PLACEHOLDER` to admit a dot is a loosening of a guard D1679 had just proved valuable, for the benefit of a caller that is not SQL. Two patterns, each strict about its own grammar, is the cheaper honesty. | 0228 |
| **D1682** | 4 | §5 Run 4 item 2 and ADR 0228: the compiler refuses *"an argument the tool does not declare"*. | **Only a WRITE declares one.** Measured over the release's approved contract joined with the example project's: a write tool carries `arguments` (`create_note` → `p_title, p_content`), and a read carries none at all. What a read accepts is the signature the runtime REGISTERS its closure with (`mcp_tools.register_relation_read` → `resource, columns, filters, order_by, limit`; `register_rpc_read` → nothing), chosen by `Tool.read_shape`, which is derived from whether every resource behind the tool is reached by `get`. | **The compiler derives the accepted names by SHAPE, the same rule the runtime registers by** (ADR 0200): a write's are the tool's declared list, a relation read's are the runtime's four, an RPC read's are none, and a metadata tool is refused before the question arises. **`resource` is deliberately NOT among the four** -- the compiler derives it from the capability, so an author naming it would be naming something already decided. Because the rule is duplicated across the `src/`-service boundary (ADR 0093 forbids importing `app.mcp_lock` here), a proof parses one real lock with BOTH readers and requires every tool's `read_shape` to agree, with at least one `relation` and one `rpc` present or the comparison proves nothing. | The alternatives were to refuse every argument on a read -- which makes `limit: 5` unwritable, and the trip's own definition needs it -- or to accept anything, which is an unbounded surface reached from a stored artefact. Deriving by the runtime's own rule is the only one of the three that cannot drift from what the plane will accept. | 0228 |
| **D1683** | 4 | §5 Run 4 item 1: `arguments` is an *"object of string/number/boolean/null"*. | That type set cannot express a relation read. `columns` is a list of strings and `filters` is a list of small objects (`{column, op, value}`), which is what the runtime's closure takes. | **A step argument is a scalar, or a LIST of scalars and objects, and nothing deeper.** An argument document the reviewed surface cannot receive is one the compiler would have to guess at, and `filters` -- the one argument with structure -- is checked by the plane against the lock on every call, which is where that check belongs. | 0228 |
| **D1684** | 4 | §5 Run 4 item 3: the statement is `psql -v name=… -v body=… -c "SELECT app_private.workflow_install_definition(:'name', …)"`. | **`-c` does not interpolate a psql variable at all.** Rig 32g, against the locked image with every released migration applied: that exact invocation fails with `ERROR: syntax error at or near ":"` and the `:'body'` reaches the server as text, because a `-c` string is sent without passing through psql's own lexer -- and the lexer is what performs the substitution. Every arm failed, including the function call itself. | **The statement goes to STDIN through `-f -`**, which is the path `postgres-bootstrap.psql` already takes for everything that is not read-only. Re-measured there (rig 32g second pass, every arm green with its control): the value survives a `'`, a `\`, a newline, a `"` and a `$$`; `:'scopes'::text[]` reads back as two elements; the function is idempotent under an identical source, raises `AP409` under a different one and installs a new row under a new version; and -- the property that matters most -- an UNSET variable produces the same syntax error rather than substituting an empty string, so a missing value cannot become a silently installed empty definition. The `-c` spelling is kept as a recorded negative control in the same rig. | `InstallStatement.stdin` is therefore load-bearing rather than decorative, and a proof refuses `-c` in the argv by name. This is §7 question 2 answered before the fact instead of after: the plan's spelling had never been executed anywhere, and it would have failed at step 6d on the host with the cluster already migrated. | 0228 |
| **D1685** | 5 | §5 Run 5: *"the plane's URL is derived: `http://{runtime_override.MCP_SERVICE}:{APG_LISTEN_PORT}{MCP_ROUTE_PATH}`"*. | **Neither authority is importable from inside the image, and the third value is the wrong one.** `runtime_override` is `src/agentic_postgres`, which is NOT in the auth image at all -- `test_the_service_never_imports_the_repository` refuses it by name, and the build context is `services/auth-api` so the import would pass every test and fail at container start. `MCP_ROUTE_PATH` is `app.mcp_runtime`'s (`:96`), and importing that module builds the whole FastMCP server, which `auth` mode never loads. And `APG_LISTEN_PORT` is the AUTH service's own port: it happens to equal the plane's because they are one image, which is a coincidence and not a derivation. | **Three constants in `workflow_worker.py` -- `PLANE_SERVICE`, `PLANE_PORT`, `PLANE_PATH` -- BOUND by a proof.** `test_the_planes_address_is_the_one_the_deploy_publishes` imports `runtime_override.MCP_SERVICE` and `MCP_SERVICE_PORT`, reads `MCP_ROUTE_PATH` out of `mcp_runtime.py` as TEXT (so the framework is never constructed), and requires equality. That is the tree's own pattern for a fact that must hold on both sides of the image boundary: `profile.py`, `scopes.py` and `strict_json.py` each say *two enforcement points, one number* and each is held by a guard. | An environment variable would have been the other answer and D1645 forbids it -- *no new document field* -- and a variable naming the plane would make the loop's target a deployment input rather than a property of the image. | 0226 |
| **D1686** | 5 | §5 Run 5: the call carries `X-Request-Id: <step.request_id>`; §2 `WF-RUN-001`: *"each step's audit row is found by its request id"*. | **`workflow_claim_step` MINTED a `request_id` per attempt and did not RETURN it.** The column's own comment in 0034 calls it *what correlates this row to the plane's audit* (D1667) -- and that only holds if the caller can read it. Written and withheld, the worker would have had to mint a second id of its own, and the two sides of the correlation would have carried different values with nothing to say so. **Found by writing the caller**, which is D348's rule and `storage_cleanup.py`'s own first paragraph: *a plane is complete when a caller can be written against it, not when its tests pass.* | **Migration 0034 amended** -- it is frozen and NOT APPLIED anywhere, so this is a fix and not a fix-forward (D912 governs an APPLIED migration) -- to add `request_id uuid` to the claim's `RETURNS TABLE` and to its `RETURN QUERY`. The lock was re-frozen, both example projects re-rendered (D1678), and two proofs added: the claim returns the id the row holds, and a SECOND attempt mints a different one. `ClaimedStep` and the repository's `SELECT` list moved with it. | **The window was named at Run 3's close and this is it being used.** After the Run 8 deploy applies 0034 on alpha it becomes a floor and the same repair would be a 0035. | 0227 |
| **D1687** | 5 | §5 Run 5: *"claim with `lease = step.timeout_seconds + lease_margin_seconds()`"*. | **The caller cannot compute that sum: `step.timeout_seconds` arrives in the claim's own RESULT.** A worker that must pass an absolute lease can only pass the CEILING -- the schema's 600, plus a margin -- and a worker killed mid-call would then leave its step unclaimable for ten minutes. `WF-RESUME-001`'s first proof (*a run whose worker died after step 2's upstream committed resumes*) would have spent that entire wait inside a fifteen-minute sweep. | **`workflow_claim_step`'s second argument is a MARGIN**, and the lease is `s.timeout_seconds + p_lease_margin_seconds`, computed inside the function where both halves are known. Zero is legal (a proof driving an expiry wants exactly the step's own timeout) and negative is not. `test_the_lease_is_the_steps_own_timeout_plus_the_margin` measures it over two different step timeouts with one margin and requires the DIFFERENCE to be the difference between the timeouts -- a function ignoring the step would produce two equal leases and pass any check that read only one. | The margin is the only half a caller can honestly know before the claim: it is a function of the WORKER's HTTP client, and the timeout is a property of the row. | 0227 |
| **D1688** | 5 | §5 Run 5: *"write it as two helpers, `_agent_record(agent_id)` and `_refuse_unless_issuable(credential)`"*, with the split explicitly required not to reorder. | **The split did not reorder anything and it still broke a contract test** -- `test_every_state_check_happens_after_the_hash_comparison` walks ONE function's AST and asserts that `status` and `secret_expired` are read after every `verify`. Moving those two reads into a helper made them invisible to it, and the failure message was *"agent_token no longer reads status"*: a guard going quiet in the reassuring direction, because the checks were still there, still after the hash, and the proof had simply stopped being able to tell. | **The proof follows ONE named call.** It reads the delegate's body as well, compares a read inside the delegate against the line the delegate is CALLED from, and refuses a function that calls it more than once. Strictly stronger than before: the old version could not have caught a helper invoked before the hash comparison, because there was no helper. The delegate is listed rather than discovered -- a scan following every call would follow `self.issue` into the signer. | This is D1486's shape inside one file: a reader derived from one function cannot see a caller that function does not contain. | 0229 |
| **D1689** | 5 | D1669: *"`workflow_worker.py` still needs its own allowlist row for `urllib`"*. | **The transport scan has a SECOND list and the row alone does not satisfy it.** `test_the_allowlist_describes_modules_that_exist_and_use_what_they_declare` carries `senders = {"app/mcp_upstream.py", "app/mcp_health.py"}` and requires every OTHER allowlisted module to name no `urlopen`, `Request` or `urlretrieve` -- because `urllib` covers both `urllib.parse` (encoding) and `urllib.request` (sending), and the package name cannot tell them apart. A row without a `senders` entry fails with *"allowlisted for encoding and names a sender"*. | **Both lists gained the module**, and the prose that said *only two modules may send* was corrected to three in the same edit: a list that grows while its own sentence still says "two" is how an allowlist stops being read. Both are WIDENINGS to a measured set, which CLAUDE.md §6 distinguishes from weakenings, and ADR 0226 authorises the sender -- the loop makes the tool call itself, which is the whole of what it does that the plane does not. | 0226 |
| **D1690** | 5 (repair) | §5 Run 5 lists the targeted modules; CLAUDE.md §5's table says `bin/apg.sh generate --check --project project.example.yaml` runs *"after any bump or contract move"*. | **Moving the app surface IS a contract move, and the generated client RECORDS its digest.** Run 5 added three operations to the auth service's OpenAPI document and regenerated `contracts/app-openapi.canonical.json`; `projects/example/clients/typescript/contract.ts` and `generated.json` carry `app_openapi_sha256`, and neither was regenerated. **CI went red on five proofs across four modules** -- `test_client_typescript`, `test_generate_command` (three of them), `test_studio_command` -- all one cause, and two of the three in `test_generate_command` failed for a DERIVED reason: they mutate one generated file and expect `--check` to name it, and the already-stale `contract.ts` was named first. The rule was on the page and the run did not apply it. | **`bin/apg.sh generate --project project.example.yaml`**, committed with the run. `generate` reports *"version 1.0.0 (no contract change)"* -- the client's SHAPE did not move, only the digest it records, so ADR 0204 requires no bump. **A run that moves the app OpenAPI document regenerates the example client and runs `test_client_typescript`, `test_generate_command`, `test_studio_command` and `test_client_ir`**; those four are in this session's targeted list from here. | **The third instance of one class in one session** (D1674 a registry row, D1680 a caller, this a derived artefact): a targeted list derived from a diff cannot see something the diff does not touch. D1486 said it; the gate sees it every time and the targeted list has now missed it three ways. |
| **D1691** | 6 | §5 Run 6 item 3: *"`bin/restore-test.py`: the evidence dictionary (`:459-480`) gains `workflow_runs`"*; §4's table names `bin/restore-test.py` and nothing else. | **A member added to `observed` and not to the document is a member nothing reads.** `restore_drill.evidence_document` does not spread `observed`; it selects fields BY NAME (`:649-682`), so `workflow_runs` in the command's reading would never have reached `evidence/restore-<key>-<id>.json`. The plan's line range points at `observe_restored_instance`, which is the READING, and the document is a second file. | **`src/agentic_postgres/restore_drill.py` moved with it** -- one member in `evidence_document`, beside `schema_version`. Recorded rather than done silently because §4's irreversible-operations table names the files a run touches, and this run touched one it does not name. | D816 and D1247's class: a declared field with no reader is an unverified field. The plan priced a reading and the reading needed a writer. | -- |
| **D1692** | 6 | §5 Run 6 item 4: `docs/recovery-operations.md` *"gains the scenario's line beside `admission-refused`'s"*. | **`admission-refused` has no line there.** Session 31 added the ninth scenario to `SCENARIOS`, `bin/rehearse.sh`'s usage and the operator guide, and did NOT add it to the recovery page's table, which still listed eight and opened *"Eight scenarios"*. Nothing checks that table against `rehearsal.SCENARIOS`, so it went stale without failing -- and §5's instruction was written from it. | **Both rows added**, the ninth and the tenth, and the paragraph's count removed the way `bin/rehearse.sh`'s header's was (D1664): the table is the list, and a list cannot go stale without being edited. The page's §5 moved from *eleven* checks to *twelve* in the same pass. | The third site of one class in one run -- `bin/rehearse.sh:4`, `bin/apg-diag.sh:140` and this -- all prose counting something a tuple already counts. What none of them has is a proof, and this run does not write one either: a guard over English prose is D622's denylist wearing a different hat. What it has instead is that the numbers are gone. | -- |
| **D1693** | 6 | §5 Run 6 item 1: the probe returns the JSON *"or `None` with the error text"*; ADR 0159 admits a cluster value only when it looks like what was asked for. | **The first heartbeat-holder guard was an ALPHABET and not a shape, and the redaction rig caught it in the same run.** `^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$` admits any sentence without a space in it, which is most of what a cluster could hand back -- `test_no_subprocess_output_reaches_the_report` went red on the canary in `verbose` and `json`. `_timestamp` (D1441's session) had already made this exact choice correctly, and this run made it wrongly for the second cluster value to reach a report. | **The guard is the shape `worker_identity()` builds**: `^[A-Za-z0-9][A-Za-z0-9._-]{0,39}:[0-9]{1,10}:[0-9a-f]{8}$` -- three parts, the last two fixed. `test_a_heartbeat_holder_that_is_not_one_is_dropped_rather_than_printed` is its own proof with the well-formed value as the discriminating control, and battery m3 kills it by restoring the alphabet. The status-name guard beside it stays a SHAPE deliberately (`^[a-z][a-z_]{0,31}$`) so a status a later migration adds appears on its own rather than being silently dropped. | **The rig found a defect in the product on its first execution**, which is what a leak scan over every rendering is for. Writing the check into the existing scan cost four lines and one fixture arm; finding this on a host would have cost a trip. | -- |
| **D1694** | 6 | §5 Run 6 item 2: *"refuse with `RehearsalError` when the check is `UNKNOWN` -- the reader must read before the kill"*, in `_worker_restart(facts)`. | **`--plan` takes no readings, and `test_plan_reads_the_facts_and_runs_writes_and_moves_nothing` asserts it for every scenario** -- any `doctor.py` call is in its `mutating_calls` set. A refusal inside the planner forces the fact to be gathered before `plan()` is called, which is before the `--plan` branch, so `--plan` would run the doctor. Gathering it only under `--plan`-is-false would instead make `--plan` refuse every deployment. The nine existing planner refusals are all facts `--plan` can check for free -- a container, a pid, a mirror, two manifests -- and a READING is not one. | **The refusal is `rehearsal.refuse_without_a_reading(plan, facts)`**, pure, called from `rehearse()` after the `--plan` return and before the in-progress file, so a refusal leaves the host as it was with nothing to reverse. `worker-restart` is its only subject; `test_worker_restart_refuses_when_the_reader_did_not_read_before_the_kill` asserts every OTHER scenario passes it with no reading at all, which is what keeps it a precondition of one rehearsal rather than a new global one. The holder also leaves the printed plan: it is a host identity, and `--plan` has not read it. | **The tree wins and the disagreement is a row** (CLAUDE.md §"Who does what"). The plan named the right refusal and the wrong place for it, and the place was decided by a proof written three sessions earlier. | -- |
| **D1695** | 6 | §5 Run 6 item 2's verdict arm: *"`read` when the holder changed and no lease is overdue, else not read"*. | **`else not read` is two findings and the first observer wrote one.** The poll recorded `heartbeat_holder_after` only on the iteration where it DIFFERED, so a holder that came back unchanged and a check that read no holder at all both left the field `None` -- and the verdict reported *"the workflow check read no heartbeat holder after the restart"* for a loop that never stopped. Found by driving the rehearsal end to end against a rig whose holder does not move (`test_a_worker_that_comes_back_as_the_same_holder_is_reported_unread`), which failed on its first execution. | **The last holder read is recorded on every poll**; only `seconds_to_holder` and the break are conditional. The verdict has both arms and says which happened. Battery m4 restores the single assignment and the proof dies. | ADR 0195 at the verdict rather than at the reading: a reader has three outcomes and the third is *I could not determine it* -- **and its sibling, that two different determinations must not share one field**. The rehearsal that exists to tell *came back* from *never stopped* was reporting *never read* for both. |

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

**One new family, `WF`**, added to `ID_PATTERN` at
`tests/contract/test_acceptance_registry.py:84` with a paragraph in the
comment block above it naming this session (the way `NODE` names 31), and
named in `src/agentic_postgres/__init__.py`'s Session 32 paragraph.
**Thirteen requirements, thirteen claims, all `target_session: 32`, all P0**
— eight offline, five host. Every requirement belongs to a claim (D697); a
new requirement gets a claim of its own (ADR 0089, D1150). **Node ids below
are proposed; Run 7 writes what the runs actually wrote, read out of the
tree with `pytest --collect-only -q`** (D1236). The registry entries cannot
be committed before Run 7 moves `CURRENT_SESSION` (`:163`, D690) — the runs
write the proofs and this table; Run 7 lands the YAML.

| Requirement | What it states | Offline node ids (proposed) | Live half |
|---|---|---|---|
| `NODE-READ-002` | The ceilings reading groups containers by Compose's own project label, so the database's cap is counted; a container carrying neither label is reported under `(unlabeled)` and never dropped; a compose project name is mapped back to a project key when a deployed document publishes it; every printer of the figure says *by compose project* | `test_capacity_reading.py::test_ceilings_group_by_the_compose_project_label_and_include_the_database`, `::test_a_container_with_neither_label_is_reported_not_dropped`, `::test_a_compose_name_is_mapped_to_its_key_through_the_documents`, `test_doctor_readings.py::test_the_ceilings_line_says_by_compose_project` | — (offline claim `capacity_ceilings`) |
| `NODE-READ-003` | On the deployment, `doctor capacity` reports ceilings of 2240 MiB per project key and 4480 in total, and names pgbouncer, postgrest and docs as unbounded | — | `test_session32_workflows.py::test_the_ceilings_on_this_host_count_the_database` (host claim `ceilings_read`) |
| `WF-DEF-001` | A workflow definition is YAML under `projects/<slug>/workflows/`, validated against `schemas/workflow.schema.json` and compiled against the project's lock: every step names an active capability `name@version` the lock carries, resolved to its tool; a metadata tool, an approval-requiring capability, an undeclared argument, a reference to a later or unknown step, and out-of-bound `retry`/`timeout` values are each refused naming the step; the compiled body carries `required_scopes` as the union, `lock_tools_sha256` and `source_sha256`; the example project's definitions compile | `test_workflow_definition.py::test_a_definition_compiles_against_the_lock_naming_each_steps_tool`, `::test_a_capability_the_lock_does_not_compile_is_refused_by_name`, `::test_a_version_the_lock_does_not_carry_is_refused`, `::test_an_inactive_capability_is_refused`, `::test_an_approval_requiring_capability_is_refused_naming_session_thirty_three`, `::test_a_metadata_tool_is_refused`, `::test_an_argument_the_tool_does_not_declare_is_refused`, `::test_a_reference_to_a_later_or_unknown_step_is_refused`, `::test_retry_and_timeout_bounds_are_enforced_naming_the_bound`, `::test_the_required_scopes_are_the_union_of_the_steps`, `::test_the_example_projects_definitions_compile` (control), `::test_the_compiled_body_carries_both_digests` | — (offline claim `workflow_definition`) |
| `WF-STATE-001` | Migration 0034 creates `workflow_definition`, `workflow_run`, `workflow_step` and `workflow_worker` in `app_private` with no grant to any role, and nine definer functions of which eight are granted to `auth_service` alone and `workflow_install_definition` to nobody; it applies as `migration_user` and its down refuses with `AP900`; `install` refuses a different body under an installed `(name, version)`; `enqueue` refuses an agent missing a required scope and derives one idempotency key per step from the run and the step; `claim` returns the run's lowest unfinished step once, leases it, and reclaims it with the attempt incremented when the lease has expired; `finish` by a holder that lost its lease is refused; `park` defers until `resume_after`; the last step's success succeeds the run and any failure fails it; `cancel` cancels a queued run at once and a running one at its next claim | `test_workflow_substrate.py::test_the_migration_applies_as_the_migration_user_and_its_down_refuses`, `::test_no_role_holds_a_privilege_on_the_four_tables`, `::test_the_eight_functions_are_executable_by_the_auth_service_role_and_nobody_else`, `::test_install_is_executable_by_nobody`, `::test_install_refuses_a_different_body_under_the_same_name_and_version`, `::test_enqueue_refuses_an_agent_missing_a_required_scope_and_admits_one_holding_them`, `::test_enqueue_derives_one_key_per_step_inside_the_pattern`, `::test_claim_returns_the_lowest_unfinished_step_once_and_leases_it`, `::test_an_expired_lease_is_reclaimed_with_the_attempt_incremented`, `::test_finish_by_a_holder_that_lost_its_lease_is_refused`, `::test_park_defers_a_step_until_its_resume_time`, `::test_the_last_step_succeeds_the_run_and_a_failure_fails_it`, `::test_cancel_marks_a_queued_run_cancelled_and_a_running_one_requested`, `::test_a_claim_after_a_cancel_request_cancels_the_run_and_claims_nothing`, `::test_a_run_past_its_timeout_is_failed_at_the_next_claim`, `::test_heartbeat_upserts_the_single_row` | — (offline claim `workflow_substrate`) |
| `WF-WORK-001` | The loop claims, mints, calls and finishes in that order; one token is minted per step attempt and none survives the step; the call carries the step's derived key, the attempt's request id and the agent's token; a `replayed` result finishes the step as replayed; a retryable failure parks with the declared backoff and a final one fails the run naming the token; a terminal refusal fails the run naming the boundary; a refused mint stops the run as `agent_not_active` with no call; a dry-run passes `dry_run` on writes only; the lease margin is a function of the client's timeouts and the loop stops before its lease does; a cancel request is honoured at the next claim; an exception in the loop is logged and the loop restarted without stopping the verifier; the heartbeat is written each poll; the loop starts in `auth` mode only and reads no variable the auth mode does not | `test_workflow_worker.py::test_a_step_is_claimed_then_minted_then_called_then_finished_in_that_order`, `::test_one_token_per_step_attempt_and_none_outlives_the_step`, `::test_the_call_carries_the_key_the_request_id_and_the_token`, `::test_a_replayed_result_finishes_the_step_as_replayed`, `::test_a_retryable_failure_parks_and_a_final_one_fails_the_run`, `::test_a_terminal_refusal_fails_the_run_naming_the_boundary`, `::test_a_refused_mint_stops_the_run_and_makes_no_call`, `::test_a_dry_run_marks_writes_and_leaves_reads_alone`, `::test_the_lease_margin_is_a_function_of_the_client_timeouts`, `::test_the_loop_stops_before_its_lease_does`, `::test_an_exception_in_the_loop_does_not_stop_the_verifier`, `::test_the_heartbeat_is_written_each_poll`, `::test_the_loop_starts_in_auth_mode_only`, `test_auth_service_shape.py::test_the_auth_mode_reads_no_new_variable` | — (offline claim `workflow_worker`) |
| `WF-ROUTE-001` | Three routes on the auth service accept an agent token through `authenticate_agent`, which refuses an access token, a revoked agent and a stale `authz_version`; `authenticate` still refuses an agent token; a run is enqueued as the token's agent and refused as `scope_not_held` when the agent's scopes do not cover the definition's; status and cancel answer the owner and return 404 to any other agent; the OpenAPI document names the three operations; no error echoes an argument or a result | `test_workflow_routes.py::test_the_three_routes_are_mounted_in_auth_mode_and_named_by_the_openapi_document`, `::test_authenticate_agent_accepts_an_agent_token_and_refuses_an_access_token`, `::test_authenticate_still_refuses_an_agent_token` (control), `::test_a_revoked_or_reauthorized_agent_is_refused_at_the_route`, `::test_enqueue_is_as_the_tokens_agent_and_scope_not_held_is_refused`, `::test_status_and_cancel_answer_the_owner_and_404_any_other_agent`, `::test_no_error_body_carries_an_argument_or_a_result_value`, `test_app_contract.py` (the existing `--check` proof over the regenerated canonical document) | — (offline claim `workflow_surface`) |
| `WF-CMD-001` | `bin/workflow.sh` has six verbs; `init` prints a skeleton that validates; `validate` exits 5 naming the first refusal and 0 on the example project; `run`, `dry-run`, `status` and `cancel` call the three enumerated routes and nothing else, with the token from `APG_AGENT_TOKEN` and never an argument; the command holds no SQL | `test_workflow_command.py::test_init_prints_a_definition_that_validates`, `::test_validate_exits_five_naming_the_first_refusal_and_zero_on_the_example`, `::test_the_three_http_verbs_call_the_enumerated_routes_and_nothing_else`, `::test_the_token_comes_from_the_environment_and_never_an_argument`, `::test_dry_run_is_run_with_the_flag_set`, `::test_the_command_holds_no_sql`, `test_cli_contract.py` (whole, D1014) | — (offline claim `workflow_command`) |
| `WF-INSTALL-001` | The deploy installs a project's definitions at step 6d, after the migrations and before the deferred services, passing each body as a psql variable and never interpolated; a project with no `workflows/` directory installs nothing and says so; an uninstallable definition refuses the deploy at exit 5 before step 6b; `apg dev up` installs the same definitions through the same statements | `test_workflow_install.py::test_the_deploy_installs_definitions_after_the_migrations_and_before_step_six_b` (an AST scan of `bin/deploy-project.py`), `::test_install_statements_pass_the_body_as_a_psql_variable`, `::test_a_project_without_a_workflows_directory_installs_nothing_and_says_so`, `::test_an_uninstallable_definition_refuses_at_exit_five`, `test_dev_environment_cluster.py::test_dev_up_installs_the_example_projects_definitions` (`@requires_docker`) | — (offline claim `workflow_install`) |
| `WF-READ-001` | The doctor's twelfth check `workflow` reports run and step counts by status, the oldest claimed lease's age and the heartbeat's age with no threshold, and is `UNKNOWN` naming the table when it is absent; the restore drill's evidence carries `workflow_runs` or `null` with a reason; the rehearsal `worker-restart` signals the auth process, reads the heartbeat before and after, refuses when the heartbeat is unreadable before the kill, and has a verdict arm | `test_doctor_readings.py::test_the_workflow_check_reports_counts_and_ages_with_no_threshold`, `::test_the_workflow_check_is_unknown_naming_the_table_when_absent`, `::test_doctor_with_no_verb_runs_the_twelve_checks_unchanged` (replaces the eleven), `test_restore_test_command.py::test_the_drill_evidence_carries_workflow_runs_or_null_with_a_reason`, `test_rehearsal.py::test_worker_restart_signals_the_auth_process_and_reads_the_heartbeat`, `::test_worker_restart_refuses_when_the_heartbeat_is_unreadable`, `::test_worker_restart_has_a_verdict_arm` | — (offline claim `workflow_reading`) |
| `WF-RUN-001` | On the deployment: a three-step run over beta's lock completes as the invoking agent with every step `succeeded`; each step's audit row is found by its request id and names the agent; the `auth_service` role never holds more connections than its pool and reserve during the run; a dry-run of the same definition records `dry_run` on both writes and lands no row; alpha refuses the same request naming *no such definition* | — | `test_session32_workflows.py::test_a_three_step_run_completes_as_the_invoking_agent`, `::test_every_step_is_correlated_to_one_audit_row_by_request_id`, `::test_the_auth_role_never_exceeded_its_pool_and_reserve`, `::test_a_dry_run_lands_no_row_and_records_dry_run_on_both_writes`, `::test_the_project_without_a_set_refuses_by_name` (host claim `workflow_run`) |
| `WF-RESUME-001` | On the deployment: a run whose worker died after step 2's upstream committed resumes with step 2 `replayed` and exactly one row for it; a reused key with other arguments is refused `PT412` (control); a run parked on a retry survives `worker-restart` and finishes at attempt 2; the rehearsal record shows a new holder and no step lost | — | `test_session32_workflows.py::test_a_run_whose_worker_died_after_the_upstream_committed_resumes_exactly_once`, `::test_a_reused_key_with_other_arguments_is_refused` (control), `::test_a_parked_run_survives_the_worker_restart_rehearsal`, `::test_the_rehearsal_recorded_a_new_holder_and_no_lost_step` (host claim `workflow_resume`) |
| `WF-REVOKE-001` | On the deployment: a revoked agent's queued run stops at its first boundary as `agent_not_active` with no audit row; the same definition as an unrevoked agent completes (control) | — | `test_session32_workflows.py::test_a_revoked_agents_run_stops_at_the_boundary_with_no_call`, `::test_an_unrevoked_agents_identical_run_completes` (host claim `workflow_revocation`) |
| `REC-WF-001` | A restore into a drill volume targeted after the trip's runs carries the runs, their steps and the installed definitions the live cluster holds | — | `tests/recovery/test_session32_workflow_restore.py::test_a_restored_drill_carries_the_runs_the_live_cluster_holds` (host claim `workflow_restore`) |

**Claims** (`src/agentic_postgres/evidence_claims.py` `CLAIMS`, each in a
block commented *Session 32 (ADR 0226-0229)*): `capacity_ceilings:
("NODE-READ-002",)`, `workflow_definition: ("WF-DEF-001",)`,
`workflow_substrate: ("WF-STATE-001",)`, `workflow_worker: ("WF-WORK-
001",)`, `workflow_surface: ("WF-ROUTE-001",)`, `workflow_command: ("WF-
CMD-001",)`, `workflow_install: ("WF-INSTALL-001",)`, `workflow_reading:
("WF-READ-001",)` — **these eight in `OFFLINE_CLAIMS`**, with the per-session
assertion in `test_session_thirty_two_gate_modes.py` (D1237: assert THESE
eight are in the set, never the set's size). `ceilings_read: ("NODE-READ-
003",)`, `workflow_run: ("WF-RUN-001",)`, `workflow_resume: ("WF-RESUME-
001",)`, `workflow_revocation: ("WF-REVOKE-001",)`, `workflow_restore:
("REC-WF-001",)` are **host** claims and are not declared.
`CLAIM_INTRODUCED_IN` gains thirteen rows at 32. `OFFLINE_CLAIMS` goes 24 →
32 and `CLAIMS` 145 → 158 — **counted from the tuples in Run 7, never by
hand** (D1628).

**Existing entries that move:** `NODE-READ-001` keeps every node id; the
proof `test_ceilings_sum_hostconfig_memory_and_ignore_unbounded_containers`
is edited to feed a labelled postgres and expect it counted (a passing test
made stricter, CLAUDE.md §6). `test_doctor_with_no_verb_runs_the_eleven_
checks_unchanged` is **renamed in place** to the twelve-check proof under the
requirement that already owns it (`grep -n eleven_checks tests/acceptance-
registry.yaml` in Run 6 says which), so `test_acceptance_registry` runs
(D1119). `AGT-*`'s revocation entry is
untouched (D1650).

**New environment gates:** none. Every live proof creates its own agents,
runs and rehearsal record from `APG_PROJECT_A_OUTPUTS`, `APG_PROJECT_B_
OUTPUTS` and `APG_REHEARSAL_EVIDENCE_DIR`, all already in the roster
(`tests/conftest.py:86-189`); the recovery proof needs root, which the host
sweep has. **The Session 32 gate therefore accepts exactly the flags the
Session 31 gate accepts — the derivation diff proves it (D1133).**

---

## 4. Irreversible operations

| Operation | Where | What makes it safe |
|---|---|---|
| Migration **0034** written and frozen into `migrations/released.lock.json` | Run 3 | `bin/migrate.sh freeze-lock` is the only writer; the rig in `test_migrations_apply_as_the_migration_user.py` applies it as `migration_user` on a fresh container; its down is `AP900`; **once applied on the host it is the floor** (ADR 0162 §3) — so Run 3's proofs run whole before the freeze and the freeze is one commit |
| `ceilings_from_inspect` changes the meaning of the ceilings dict's keys | Run 2 | Every printer grepped (three) and edited in the same commit (D979); the offline proof feeds both a labelled and an unlabelled payload; the live proof expects 4480 |
| `AuthService.agent_token` split into two methods | Run 5 | The split keeps the order of the four checks and their messages byte-for-byte (a proof compares the refusal messages of the route before and after); `tests/contract/test_auth_service_shape.py` and every `agent_token` proof run whole |
| A second authenticator on the auth service (ADR 0114 amended) | Run 5 | ADR 0229 first; `authenticate` unchanged; both directions of refusal asserted; the `/admin/*` routes' proofs run whole |
| A background task in the auth lifespan | Run 5 | Supervised (`test_an_exception_in_the_loop_does_not_stop_the_verifier`); cancelled at lifespan exit before the pool closes; rig 32a measured the RSS cost first; the flip criteria in D1645 |
| `bin/deploy-project.py` gains step 6d | Run 4 | An AST proof pins its position between the migration step and 6b; a project without definitions is a no-op with a line; `--render-only` never reaches it (the gate's step 2 renders four fixtures) |
| `bin/restore-test.py`'s evidence gains a member | Run 6 | `null` with a reason when the table is absent (ADR 0195); `test_restore_test_command.py` whole |
| `bin/doctor.py` gains a twelfth check | Run 6 | No threshold (D1441); `UNKNOWN` naming the table when absent; `bin/fleet.py:102-133` and `rehearsal._doctor` still invoke `bin/doctor.py --project KEY --json` and are run |
| `bin/rehearse.sh` gains `worker-restart` | Run 6 | The induce is the termination scenario's signal (ADR 0193); the reader is the heartbeat; `test_every_scenario_plans_three_phases_and_prints_every_command` runs whole |
| `CURRENT_SESSION` 31 → 32; `VERSION` 1.9.0 → 1.10.0 | Run 7 | All-or-nothing (D690); every `target_session: 32` entry in the same commit; the client regenerated (D1238); `docs/upgrade-guide.md` gains a `1.10.0` row; `README.md:7` moves; `upgrade plan` on the host confirms `bump minor` with the declared classes or §9 stops |
| `bin/session-32-check.sh` | Run 7 | Derived from 31's by diff (D1482); header and usage rewritten whole (D1488); `SHELL_COMMANDS` gains it and `chmod 755` before `git add` (D1014, D1188); `test_session_thirty_two_gate_modes.py` copied from thirty-one's; the verbatim `run_suite` selector kept (D1242) |
| Deploy `--through-session 32` on alpha, then beta | Run 8 | `upgrade plan` OK first (§9); alpha first; at a terminal under `script(1)`; **0034 applied** (ledger 33 → 34; beta 34 + 2); `auth` recreated (image moved); `doctor` 12 ok after each |
| Agents created, runs enqueued and rows written on beta by the proofs | Run 8 | Every proof deletes its agents and notes in `finally` (the `mcp_writer_session` shape); runs are left as the substrate's record and named in the Done |
| Rehearsal `worker-restart` on beta | Run 8 | The auth process is signalled, not `docker kill`ed; `on-failure:5` restarts it; the verdict reads the heartbeat; `reverse` is the restart policy with `docker start` as the fallback (ADR 0193) |
| Tag `1.10.0` on the deployed commit | Run 8 | After the merge exits 0 or 5 for the expected reasons only (§7); `release-reading --ref <deployed sha>` first |

---

## 5. Build order, run by run

Each run ends with a `**Done.**` paragraph written by the executor: what was
measured, the numbers, the rows it added, the CI verdict by full SHA. A run
that changes code pushes and reads CI; the targeted modules run ONCE at the
run's close and only the failing module is re-run. `ruff format && ruff
check` before every commit; `chmod 755 bin/*.sh bin/*.py deploy.sh` before
every `git add`; commit messages from a file with `-F`. **Grep the plans for
every third party before measuring it** (`grep -rn -i '<term>' docs/plans/
*.md docs/decisions/*.md`).

### Run 1 — the measurements, and ADRs 0226–0229

**Reads first** (agent, no edits): `services/auth-api/app/storage_cleanup.py`
whole; `mcp_tools.py:547-652` and `:720-938`; `service.py:260-300` and
`:449-496`; `main.py:79-165` and `:168-249`; `0016:65-180`, `0019:73-160`
and `:329-379`, `0029:101-241`, `0030:60-160`, `0033:126-326`; `rehearsal.
py:293-330` and `bin/rehearse.py:343-420`; `test_migrations_apply_as_the_
migration_user.py:95-163`; `test_session9_agent_writes.py:139-262`. Then
re-run the deployable-diff filter named in §0 and write its answer.

**The rigs.** Each is a script under `/tmp` written with the Write tool and
copied to the scratchpad, each names its image by digest from `versions.env`
/ `versions.lock.json` (read `bin/lock-versions.sh --help` for the reader),
each has a control, and each prints its own exit status from inside. The
cluster rigs use the `cluster` fixture's recipe from `test_migrations_apply_
as_the_migration_user.py:108-142` (a `docker run -d` of `POSTGRES_IMAGE`,
two consecutive `pg_isready`, the product's own `dev_environment.role_
statements`), **not** `apg dev`, because the rigs need a cluster with the
released migrations applied by a script rather than a state file.

| Rig | Subject | Method | Control | Owes |
|---|---|---|---|---|
| **32a** | The cost of a loop in the auth image | Build `services/auth-api` (the `docker build` the compose file describes at `compose.yaml:1190-1212`, args from `versions.env`); run it once as `APP_MODE: auth` against the rig cluster with a throwaway RSA key (`openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048`), a pgpass and the lock from `.generated/fixture-alpha-dev/…/mcp-capability-lock.json`; read `memory.current` from its cgroup and RSS from `docker stats --no-stream`; then run it a second time with `PYTHONSTARTUP`-free injection of a 5 s polling `asyncio` task via a one-file sidecar module mounted read-only (`-v /tmp/rig32a/loop.py:/app/app/rig_loop.py:ro`) and imported by an env var the rig sets — **if the image's `main.py` cannot import a sidecar without an edit, the second arm is measured after Run 5 instead and this row says so** | the same image with `APP_MODE: mcp` (the known 61 MiB overhead, `profile.py:117-119`) | `WORKFLOW_IDLE_RSS_DELTA_MB` for the ADR and the envelope; D1645's first flip criterion |
| **32b** | A sibling container reaches `http://mcp:8080/mcp` on a user network with a bearer and gets a JSON-RPC answer | Start the built image as `APP_MODE: mcp` on a `docker network create rig32b` with a JWKS from the rig key, the fixture lock, `APG_POSTGREST_URL=http://nowhere:3000`; from a second container (the pinned Python image) POST `tools/list` with a token minted from the rig key (`bin/dev-token.py`'s `mint` for the claim shape — read `tests/deployment/conftest.py:838-857`) and `Accept: application/json, text/event-stream`; then `tools/call` `list_resources`; then `query_resource`, which must reach the upstream and refuse | no bearer → 401; a bearer with `token_use: access` → 401 | the exact headers and body the loop sends; whether `stateless_http` needs a session id (it must not); the SSE parse the loop copies from `sse_result` |
| **32c** | Replay semantics of the idempotency claim | On the rig cluster with all 33 applied: as superuser `SET ROLE <agent_writer>; SET app.agent_id = …; SET request.headers = '{"idempotency-key": "wf-…"}'` (read `0029:139-175` for the header GUC's exact spelling) and `SELECT api.create_note(…)` twice with the same key and arguments → one row in `app.notes`, `replay_count` 1, the second call returns the same row; then the same key with different arguments → `PT412`; then a `dry-run` header set → no claim and `APDRYRUN` | a fresh key → a second row | the wording of the `replayed`/`PT412` outcomes as the loop will see them through the plane's translation (`mcp_errors.py:103-106`) — cross-checked against 32b's `query_resource` refusal shape |
| **32d** | Definer functions over a table with no grants, as `auth_service` | On the rig cluster: a throwaway `app_private.rig32d` table owned by `object_owner` with no grants and a definer function granted to `auth_service`; `SET ROLE auth_service; SELECT` on the table → permission denied; the function → succeeds; `SET ROLE agent_writer;` the function → permission denied | the same table with `FORCE ROW LEVEL SECURITY` and no policy: the definer function as `auth_service` returns **zero rows** (the premise of D1647) | the assertion text for `WF-STATE-001`'s privilege proofs; the D1647 row's *measured* word |
| **32e** | `FOR UPDATE SKIP LOCKED` under a lease predicate reclaims an expired lease and only that | Two `psql` sessions on the rig cluster over a throwaway table shaped like `workflow_step` (`status`, `claimed_by`, `lease_until`, `attempt`): session A claims with a 2 s lease and holds its transaction OPEN; session B's claim skips A's row; A commits; after 3 s B's claim takes the row with `attempt` 2 and a new holder; A's late `finish … WHERE claimed_by = 'A'` updates 0 rows | the same without the lease predicate: B takes the row immediately after A commits | the claim and finish statements of migration 0034, proved to behave before they are written into a template |
| **32f** | A step token minted without a secret carries the same claims as one minted with it | Not a container rig: a unit rig over `service_source.load("service")` with the repository faked (the `test_session9_revocation.py:60-100` fake shape): `agent_token(id, secret)` and a prototype `step_token(id)` produce tokens whose decoded claims differ only in `iat`/`exp`/`jti`; a `revoked` record refuses both with the same message; an expired secret refuses both | an unknown id refuses both | the split in D1649 and the proof's assertion list |

**Third-party facts already measured, cited and not re-run:** `docker
kill` is never restarted and a signal to the process is (ADR 0193, rig 4;
D1015); the auth image's overhead (`profile.py:116-128`); `pids.max` and
`cpu.max` semantics (rig 31a); Compose's project label value
(`runtime_override.py:41-70`).

**ADRs written after the rigs, before any code**, each indexed in
`docs/decisions/README.md` as `| [NNNN](file.md) | Title | 32 | Accepted |`:

- **0226 — The workflow worker is a loop in the auth process, and it holds
  nothing the auth service did not hold.** Context: D1645's three facts.
  Decision: the loop; its pool; its minting through `step_token`; no new
  container, role, secret, summand or field; the supervisor; the flip
  criteria and rig 32a's numbers; a worker restart is an auth restart.
  Alternatives: a `worker` container with its own role and a step-nonce
  exchange route (rejected: a new way to obtain an agent's token); a loop in
  the `mcp` process (rejected: the plane holds no credential and no pool by
  decision, `main.py:160-163`). Consequences: the auth container's memory
  cap now covers the loop (measured); `service-termination` on `auth` is
  `worker-restart`.
- **0227 — Durable step state is four tables nobody may read and nine
  definer functions, and a step is at-least-once with a key that makes it
  exactly-once.** The tables and their columns (Run 3's list); no RLS
  (D1647); the grants (D1648); the lease (claim/finish/park, expiry-based
  reclaim, the monotonic deadline and the margin as a function, D1667); the
  key per (run, step) and the `replayed` outcome (D1646); park is the
  backoff and the pause; the run timeout; the heartbeat; the request id as
  the audit's correlation. Alternatives: FORCE RLS (rejected, rig 32d);
  a key per attempt (rejected, rig 32c); `LISTEN/NOTIFY` (rejected: the auth
  service holds no LISTEN connection by decision, `config.py:461-470`).
- **0228 — A workflow definition is a project artefact compiled against the
  lock and installed by the deploy, immutable per name and version.** The
  YAML shape; the compiler's refusals (D1660); `required_scopes` as the
  union; the two digests; step 6d and `apg dev up`; the install function
  granted to nobody; approval-requiring capabilities refused until 33; a
  definition is fixed forward by a new version. Alternatives: a mounted file
  read by the loop (rejected: a parked run could resume against a changed
  definition); a definition submitted with the run (rejected: an unreviewed
  artefact executed by a second principal).
- **0229 — A run is the agent's: enqueued with its token, authorised by its
  own scopes, minted per step, and stopped by its revocation.** The three
  routes; `authenticate_agent` beside `authenticate` and ADR 0114's
  amendment (D1651); no new scope (the union check); `step_token` (D1649);
  what a revocation does at a boundary and mid-step (D1650); `APG_AGENT_
  TOKEN` and the six verbs (D1659); status/cancel owner-scoped with a 404.
  Alternatives: an MCP tool (rejected: moves every lock's digest); a human
  route (rejected: the wrong principal); a new `workflows:run` scope
  (rejected: the vocabulary is derived from the surface, ADR 0200, and a
  workflow adds no authority).

Run `pytest tests/contract/test_acceptance_registry.py -q -p no:randomly`
(the ADR index proofs at `:493` and `:530`). Commit (`Session 32 Run 1: the
rigs, and ADRs 0226-0229`), push, read CI.

**Done.** Run 1 is complete. Six rigs, each with a control, each printing its
own exit status from inside; all six exit **0**. Scripts and transcripts kept
at `scratchpad/rig32/`.

**The deployable diff.** `git diff --name-only 4344a1f..HEAD` filtered to
`src/ bin/ services/ migrations/ templates/ schemas/ compose.yaml deploy.sh
VERSION` names **exactly one file**, `src/agentic_postgres/capacity.py`, 56
insertions / 18 deletions. Every changed line is a string literal inside a
`Measurement` (`value=`/`conditions=` text: the 0.69 s capacity reading, the
2.92 s usage reading); no `def`, `class`, `import` or expression moved. D1641's
caveat holds: **the deployed commit and HEAD differ by data in the envelope and
by nothing executable.**

**Rig 32a -- the cost of the loop.** The released image, built from
`compose.yaml:1190-1212`'s own build args, as `APP_MODE: auth` against a rig
cluster with all 33 released migrations applied; arm 2 injects a polling task
through `sitecustomize`, so the image measured is byte-for-byte the released
one. **Bare: 53.77 MiB RSS / 54.7 MiB cgroup. With the loop: 61.57 MiB RSS /
62.9 MiB cgroup. Idle delta 7.8 MiB RSS, 8.1 MiB cgroup, against a 32 MiB
criterion** -- cleared four-fold. `docker top` reads **one** process, the
uvicorn entrypoint with no `--workers`. Control: the same image in `mcp` mode
reads 94.88 MiB. **No flip criterion is tripped; Run 5 proceeds.** The injected
task is a conservative OVER-estimate (its own thread, event loop and
connection, where the real loop shares the application's) -- the only direction
in which an approximation may clear a gate. Two rig-side findings recorded in
ADR 0226: a bind-mounted 0600 secret is unreadable by `USER 65532` and the
lifespan dies with `PoolTimeout` naming the pool and never the file (both arms
of the first pass); and the image carries no `ps`, so the third criterion was
skipped by a falsy guard until it was read with `docker top`.

**Rig 32b -- the transport.** A sibling container reaches
`http://mcp:8080/mcp` on a user network with a bearer: **200**. **No session id
is demanded** -- `stateless_http` needs none, so §9's stop condition is not
met. The reply is `event: message\r\ndata: {...}\r\n\r\n` and parses with
`sse_result`'s shape (last `data:` wins). Controls: no bearer -> **401**; a
`token_use: access` bearer -> **401**, both with
`www-authenticate: Bearer error="invalid_token"`. **What the loop sends,
measured:** `POST http://mcp:8080/mcp`, `Authorization: Bearer <per-step
token>`, `Accept: application/json, text/event-stream`, `Content-Type:
application/json`, `X-Request-Id: <the attempt's uuid4>`, body
`{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":<tool>,
"arguments":{...}}}`. **The finding that mattered most is D1672**, the
classifier shape. The tool ROSTER is reported **undetermined** in this rig
rather than folded into a pass: `resolve_agent_context` is *"the FIRST of the
three or four upstream requests one tool call makes"* (`mcp_upstream.py:191-194`)
and runs for `tools/list` too, so with `APG_POSTGREST_URL=http://nowhere:3000`
no call gets past it.

**Rig 32c -- replay.** Verbatim, through `api.create_note` on a 33-migration
cluster: the same key and arguments twice returns **the same row id**, one row
in `app.notes`, `replay_count` **1**, audit `committed:1,replayed:0`. The same
key with different arguments -> `AP412: this idempotency key was used for a
different call` (errcode `PT412`, raised in
`agent_idempotency_claim` line 24). No key at all -> `AP412: an agent write
requires an Idempotency-Key header`. Dry-run header -> **no row, no claim**,
rc 0 with a null id. Control: a fresh key -> a second row. **D1646 is
confirmed and no stop condition fires** -- a replay is re-read, never refused.
D1671 is the row this rig produced.

**Rig 32d -- the posture.** A no-grant `app_private` table behind a definer
function granted to `auth_service`: direct `SELECT` -> `permission denied for
table`; the function -> succeeds, reads every row; `agent_writer`,
`agent_reader`, `authenticated`, `anon` and `storage_service` -> `permission
denied for function`, all five. `has_table_privilege` / `has_function_privilege`
/ anon's -> **`false true false`**. **The control is the decisive one:** the
same table under `FORCE ROW LEVEL SECURITY` with no policy -- the definer
function returns **zero rows and exits 0**, silently, in the reassuring
direction. **D1647's premise is measured**, and the stage plan's FORCE-RLS
sentence stays refused. Also measured: `psql -qtA` prints
`has_*_privilege()::text` as the WORDS, which would have failed WF-STATE-001's
privilege proofs on first execution.

**Rig 32e -- the lease.** Five arms across two concurrent sessions over a
step-shaped table. A holder inside an open transaction is skipped by
`SKIP LOCKED`; after it commits with its lease still standing, the second
claimant takes **nothing**; once the lease expires it takes the row with
`attempt 2` and a new holder; the first holder's late finish updates **0 rows**
and the row stays the second holder's. Control, the same statement with the
lease predicate removed: the second claimant takes the row **thirty seconds
into a thirty-second lease**. 0016:65-69 re-measured for a step. **The rig's
first pass found a third-party fact worth the whole rig: `pg_catalog.now()` is
the TRANSACTION START time**, so a 2 s lease with a 3 s in-transaction sleep
had already expired at commit; the claim and the reclaim predicate read the
same clock. (Three of that pass's four failures were the rig's own
expectation -- `psql -qtA` separates with `|`, not `,`.)

**Rig 32f -- the token split.** Against the real `AuthService` with a faked
repository and hasher, and a vocabulary loaded by the product's own
`scopes.load_vocabulary` from a lock the product's own `bin/mcp-contract.sh
lock` compiled. The two tokens for one active agent **differ in `jti` alone**;
`token_use`, `scope`, `role`, `authz_version`, `credential_version`, `sub`,
`iss` and `aud` are identical. Four refusal pairs are byte-identical: `agent is
revoked`, `agent secret has expired`, `no such agent` (control), `agent id is
not a uuid` (control). `step_token` pays no hash. The one asymmetry is the one
that must exist: a wrong secret is `secret mismatch` for `agent_token` and
`step_token` has no secret to be wrong. **Measured, after a vacuous pass: the
claim is spelled `scope`, not `scopes`** -- the first version of that check
compared two absent keys.

**Rows added: D1668, D1669, D1670, D1671, D1672. NEXT FREE: D1673.**
D1668-D1670 are the three ways the plan's Run 5 sketch does not fit the tree
(a banned module name, a missing allowlist row, two constants that are the
object-store client's); D1671 and D1672 are what the rigs measured about what
the loop can and cannot see in a plane result. None reopens a decision; all
five are carried into ADRs 0226, 0227 and 0229 as written.

**ADRs 0226-0229 written and indexed** in `docs/decisions/README.md` (229
rows). No stop condition in §9 was met.

### Run 2 — D1636 first: the ceilings grouped by Compose's own label

**Before editing:** `grep -rn 'ceilings' src/ bin/ tests/ --include=*.py`
and list every reader in the Done (three printers, three proofs — §0's
list; if a fourth appears, it is edited in this commit, D979).

1. `src/agentic_postgres/capacity_reading.py:288-325` `ceilings_from_
   inspect`: group by `labels.get(runtime_override.COMPOSE_PROJECT_LABEL)`
   (import the constant; do not retype the string); a container with no
   such label goes under the literal key `UNLABELED_CEILINGS_KEY =
   "(unlabeled)"` (a module constant with a `#:` comment naming D1636 and
   D587); the `apg.project.key` read is deleted; the docstring rewritten to
   say the keys are compose project names.
2. `src/agentic_postgres/capacity_probe.py` `read(...)` (`:181-`): after
   `read_ceilings`, translate each compose-name key to a project key when a
   document under `root` publishes `compose.project_name` equal to it
   (`read_deployed` at `:55` already loads them for `committed`); leave the
   name otherwise. `Reading.ceilings`'s field comment (`capacity_reading.
   py:136`) says *keyed by project key when a deployed document names the
   compose project, else by compose project name*.
3. The three printers: `bin/admit.py:196-200` prints `ceilings (by compose
   project, ADR 0221/D1636)`; `diagnosis.py:802-813`'s summary line gains
   the same phrase and keeps *ceilings, not reservations (D767)*;
   `bin/deploy-project.py:2046-2047` unchanged unless it prints keys (read
   it).
4. Proofs: `tests/contract/test_capacity_reading.py::test_ceilings_sum_
   hostconfig_memory_and_ignore_unbounded_containers` gains a labelled
   postgres in its payload and expects it summed (stricter); three new
   proofs from §2 `NODE-READ-002`; `tests/contract/test_doctor_readings.py::
   test_the_ceilings_line_says_by_compose_project`. `tests/contract/test_
   admission.py:345-368` re-run (it reads the dict) and edited only if it
   asserted a key space.
5. `src/agentic_postgres/capacity.py:503-525` — the D1636 `Measurement`
   gains a `repaired_in="Session 32 Run 2"`-style note **only if the
   dataclass has such a field** (read `:1-120`); otherwise its `conditions`
   text gains one sentence and `bin/render-capacity-envelope.py --write`
   regenerates the page (D1644: this is a source edit).

**Mutation battery** (`PYTHONDONTWRITEBYTECODE=1`, `__pycache__` cleared,
anchors pre-flighted to match once, restore by copy + `cmp`): (m1) restore
the `apg.project.key` read → the new labelled-postgres proof FAILS (a kill);
(m2) `continue` on a missing label instead of `(unlabeled)` → the neither-
label proof FAILS; control: `test_a_meminfo_missing_memavailable_is_
unknown_not_zero` stays green in the same invocation (the mutation cannot
reach it).

Targeted: `test_capacity_reading.py`, `test_doctor_readings.py`,
`test_admission.py`, `test_capacity_envelope.py` (if it exists — `ls
tests/contract | grep envelope`). `bin/render-capacity-envelope.py --write`.
Commit (`Session 32 Run 2: the ceilings count the database (D1636)`), push,
read CI.

**Done.** D1636 is repaired in the reading, and the repair is guarded by two
kills and a control it cannot reach.

**Every reader found, and there was no fourth.** `grep -rn 'ceilings' src/ bin/
tests/ --include=*.py` separates into the capacity ceilings and the unrelated
SCOPE ceilings (`capability_compiler.py`, `runtime_override.py:431,837`,
`test_scope_registry.py`, `test_mcp_catalog.py`, `test_auth_endpoints.py`) --
none of which this run touches. The capacity readers are **five**:
`capacity_reading.ceilings_from_inspect` and the `Reading.ceilings` field;
`capacity_probe.read_ceilings` and `read`; and **three printers** --
`diagnosis.py:802-813`, `bin/admit.py:196-200`, and
`bin/deploy-project.py:2046-2047`. **The deploy was read and needs no edit**:
it prints the ceilings *reason* only and never a key. The proofs are
`test_capacity_reading.py`, `test_doctor_readings.py`, `test_admission.py`
(re-run, unedited -- it asserts the "could not read them" line and no key
space) and `test_session31_capacity.py:375` (a set membership, unaffected).

**What changed.** `ceilings_from_inspect` groups by
`runtime_override.COMPOSE_PROJECT_LABEL`, imported inside the function because
`runtime_override` imports from this package and a module-level import would be
a cycle. A container carrying neither label goes under the new module constant
`UNLABELED_CEILINGS_KEY = "(unlabeled)"` instead of being `continue`d.
`capacity_probe.read` then translates compose names back to project keys
through `naming.compose_project_name` over the keys it listed -- **D1673**, the
row this run added, because the deployed document publishes no `compose` block
and the mapping the plan specified would never have fired. Both printers say
**by compose project** and both keep *ceilings, not reservations (D767)*.

**The fixture shared the code's belief, and that is why the defect survived a
green suite** (§7 question 6). `inspect_payload` emitted `apg.project.key` on
every container, so every fixture in the module described a host where the
grouping label was universal. It now emits `com.docker.compose.project` on
everything and `apg.project.key` on everything except `postgres`, `pgbouncer`
and `dbmate` -- production's actual shape (D587, D1620). The existing
`test_ceilings_sum_hostconfig_memory_and_ignore_unbounded_containers` is made
**stricter** under that fixture: the same payload summed to 384 for alpha and 0
for beta before, and is required to read **1152 and 768** now.
`test_an_unlabelled_container_belongs_to_no_project`, which asserted the drop,
is **replaced** by `test_a_container_with_neither_label_is_reported_not_dropped`
(CLAUDE.md §6, under ADR 0221/D1636).

**The keys the proofs now print:** `{"apg-alpha-dev": 1152, "apg-beta-dev":
768}` out of `ceilings_from_inspect`, and `{"alpha-dev": 2240,
"apg-some-other-stack": 512, "(unlabeled)": 256}` out of
`_ceilings_by_project_key` -- the mapped key, the unmapped compose name and the
unlabelled bucket, in one assertion.

**The battery.** `PYTHONDONTWRITEBYTECODE=1`, `__pycache__` cleared before each
arm, both anchors pre-flighted to exactly one match with a miss fatal, restore
by copy with `cmp` verifying each. **m1** — restore the `apg.project.key` read,
which is the defect itself → `test_ceilings_group_by_the_compose_project_label_
and_include_the_database` **FAILED** (a kill, not an ERROR). **m2** — `continue`
on a missing label → `test_a_container_with_neither_label_is_reported_not_
dropped` **FAILED**. **Control, in the same invocation both times:**
`test_a_meminfo_missing_memavailable_is_unknown_not_zero` **PASSED** — a
`/proc/meminfo` parser these mutations cannot reach. After both reverts, all
three green. Battery exit 0.

**The envelope.** `Measurement` has no `repaired_in` field (`capacity.py:77-95`
is `subject, value, kind, conditions, note`), so the plan's conditional applies:
the D1636 row's **conditions** gain the sentence that the reading was taken
before the repair and that the same command now reports 4,480 MiB, and its note
records that this is the last reading of its kind.
`bin/render-capacity-envelope.py --write` regenerated `docs/capacity-envelope.md`.

**Targeted, once at the close:** `test_capacity_reading.py`,
`test_doctor_readings.py`, `test_admission.py`, `test_capacity_envelope.py` —
**86 passed**. `ruff format && ruff check` clean.

**Rows added: D1673, and D1674 at the repair below. NEXT FREE: D1675.**

**Repaired after CI.** Run 2's first push read **failure** on `Session 1 gate`
and `Session 2 offline contract` — six proofs, one cause: the registry named
the proof this run replaced. The four targeted modules could not have seen it,
and that is D1674 and D1486. Repaired in the next commit; CI re-read.

### Run 3 — migration 0034: the substrate, and its proofs under a real cluster

**Read first:** `migrations/manifest.json`'s last entry and `placeholders`
block; `0016-storage-cleanup-write-window.sql` whole; `0029:101-241`;
`0033` whole; `docs/migrations.md`; `tests/contract/test_migrations_apply_
as_the_migration_user.py` whole; `tests/contract/test_database_function_
signatures.py` (it may pin the set of `app_private` functions — read its
docstring and decide whether the nine new ones need registering there;
say which in the Done); `tests/contract/test_rendered_migrations.py:60-
120` and `:570-590` (the literal `33` at `:580`).

**The template `migrations/templates/0034-workflow-substrate.sql`**, version
`20260917120034`, placeholders `object_owner`, `auth_service`, manifest
entry with a description in the house voice (what is here, what is NOT
here, which ADRs). The body, in order:

1. `-- migrate:up`, `SET LOCAL ROLE {{object_owner}};`.
2. **Types**: `app_private.workflow_run_status AS ENUM ('queued', 'running',
   'succeeded', 'failed', 'cancelled', 'stopped')`; `app_private.workflow_
   step_status AS ENUM ('queued', 'claimed', 'parked', 'succeeded',
   'failed')`; `app_private.workflow_step_outcome AS ENUM ('succeeded',
   'replayed', 'dry_run', 'failed', 'refused', 'token_refused',
   'abandoned')`.
3. **Tables** (every `app_private`, owner `{{object_owner}}`, no grants):
   - `workflow_definition(id uuid PK DEFAULT gen_random_uuid(), name text
     NOT NULL CHECK (name ~ '^[a-z][a-z0-9-]{0,62}$'), version integer NOT
     NULL CHECK (version >= 1), body jsonb NOT NULL, source_sha256 text NOT
     NULL CHECK (~ '^[0-9a-f]{64}$'), lock_tools_sha256 text NOT NULL CHECK
     (same), required_scopes text[] NOT NULL, installed_at timestamptz NOT
     NULL DEFAULT now(), UNIQUE (name, version))`.
   - `workflow_run(id uuid PK DEFAULT gen_random_uuid(), definition_id uuid
     NOT NULL REFERENCES app_private.workflow_definition(id), agent_id uuid
     NOT NULL REFERENCES app_private.agents(id), owner_id uuid NOT NULL,
     input jsonb NOT NULL DEFAULT '{}', dry_run boolean NOT NULL DEFAULT
     false, status app_private.workflow_run_status NOT NULL DEFAULT
     'queued', stopped_reason text, timeout_seconds integer NOT NULL,
     cancel_requested_at timestamptz, created_at timestamptz NOT NULL
     DEFAULT now(), started_at timestamptz, finished_at timestamptz)`; index
     on `(status, created_at)`.
   - `workflow_step(id uuid PK DEFAULT gen_random_uuid(), run_id uuid NOT
     NULL REFERENCES app_private.workflow_run(id), position integer NOT
     NULL, name text NOT NULL, status app_private.workflow_step_status NOT
     NULL DEFAULT 'queued', attempt integer NOT NULL DEFAULT 0, retry_max
     integer NOT NULL, backoff_seconds integer NOT NULL, timeout_seconds
     integer NOT NULL, idempotency_key text NOT NULL CHECK
     (idempotency_key ~ '^[\x21-\x7e]{8,255}$'), claimed_by text,
     lease_until timestamptz, resume_after timestamptz, request_id uuid,
     outcome app_private.workflow_step_outcome, reason text, result jsonb,
     started_at timestamptz, finished_at timestamptz, UNIQUE (run_id,
     position), UNIQUE (run_id, name))`; index on `(status, resume_after)`.
     **The `agents` FK column name must be read from `0013`/`0025`** (grep
     `CREATE TABLE app_private.agents`); if the PK is not `id`, the row says
     so.
   - `workflow_worker(singleton boolean PK DEFAULT true CHECK (singleton),
     holder text NOT NULL, started_at timestamptz NOT NULL, seen_at
     timestamptz NOT NULL)`.
4. **Functions**, every one `LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET
   search_path = pg_catalog, pg_temp` (STABLE for the two readers), each
   with a `COMMENT ON FUNCTION`, refusals as `RAISE EXCEPTION 'AP4xx: …'
   USING ERRCODE = 'PT4xx'` in the house shape (read `0019:147-150` and pick
   codes that `grep -rn "'PT4" migrations/templates/` shows unused):
   - `workflow_install_definition(p_name text, p_version integer, p_body
     jsonb, p_source_sha256 text, p_lock_tools_sha256 text, p_required_
     scopes text[]) RETURNS uuid` — insert; on conflict `(name, version)`
     with equal `source_sha256` return the existing id; with a different one
     refuse `AP409`/`PT409` naming name and version.
   - `workflow_enqueue(p_agent uuid, p_name text, p_version integer, p_input
     jsonb, p_dry_run boolean) RETURNS uuid` — the agent must exist and be
     `active` (`PT403`); the definition must exist (`PT404`, message *no
     such definition*); `required_scopes <@ agents.scopes` or `PT403` with
     message `scope_not_held` (the boundary word, so the route can map it);
     insert the run (`owner_id` from the agent row, `timeout_seconds` from
     `body->>'timeout_seconds'`) and one step per `body->'steps'` element
     with `idempotency_key = 'wf-' || run_id || '-' || step name`,
     `retry_max`, `backoff_seconds`, `timeout_seconds` from the element.
   - `workflow_claim_step(p_holder text, p_lease_seconds integer) RETURNS
     TABLE (step_id uuid, run_id uuid, position integer, name text, attempt
     integer, agent_id uuid, dry_run boolean, step jsonb, input jsonb,
     prior jsonb, timeout_seconds integer, idempotency_key text)` — first,
     for every run with `cancel_requested_at IS NOT NULL AND status IN
     ('queued','running')` and no step `claimed` with an unexpired lease:
     set `cancelled`, `finished_at`; then for every `running` run past
     `started_at + timeout_seconds`: `failed`, `stopped_reason 'timed_
     out'`; then select ONE step — the lowest `position` of its run whose
     earlier positions are all `succeeded`, with status `queued`, or
     `parked` and `resume_after <= now()`, or `claimed` and `lease_until <
     now()` — from runs in `('queued','running')`, `ORDER BY run.created_at,
     position`, `FOR UPDATE OF workflow_step SKIP LOCKED LIMIT 1`; set
     `claimed`, `claimed_by`, `lease_until = now() + make_interval(secs =>
     p_lease_seconds)`, `attempt + 1`, `request_id = gen_random_uuid()`,
     `started_at` if null; set the run `running` and its `started_at` if
     null; return the row with `step` = the body element, `prior` = a jsonb
     object of `{name: result}` for the run's succeeded steps.
   - `workflow_finish_step(p_step uuid, p_holder text, p_outcome app_
     private.workflow_step_outcome, p_result jsonb, p_reason text) RETURNS
     text` — `WHERE id = p_step AND claimed_by = p_holder AND status =
     'claimed'`; 0 rows → return `'lease_lost'`; `succeeded`/`replayed`/
     `dry_run` → step `succeeded`, and if no other step of the run is
     unfinished, run `succeeded` with `finished_at`; `failed`/`refused` →
     step `failed`, run `failed`, `stopped_reason = p_reason`; `token_
     refused` → step `failed`, run `stopped`, `stopped_reason 'agent_not_
     active'`; return the run's new status.
   - `workflow_park(p_step uuid, p_holder text, p_reason text, p_resume_
     after timestamptz) RETURNS text` — same predicate; `parked`, `claimed_
     by NULL`, `lease_until NULL`, `resume_after`, `reason`; return
     `'parked'` or `'lease_lost'`.
   - `workflow_cancel(p_run uuid, p_agent uuid) RETURNS text` — the run must
     belong to `p_agent` else `PT404`; `queued` → `cancelled` now;
     `running` → `cancel_requested_at = now()`; terminal → unchanged; return
     the status.
   - `workflow_run_status(p_run uuid, p_agent uuid) RETURNS jsonb` (STABLE)
     — `PT404` unless the run is the agent's; the run row including
     `input` (it is the agent's own) and its steps ordered by position with `status, attempt, outcome, reason,
     request_id, started_at, finished_at` and `result`.
   - `workflow_heartbeat(p_holder text) RETURNS void` — upsert the singleton
     with `seen_at = now()`, `started_at` reset when `holder` changes.
   - `workflow_counts() RETURNS jsonb` (STABLE) — runs by status, steps by
     status, `oldest_claimed_lease_age_seconds`, `heartbeat_age_seconds`,
     `heartbeat_holder`, `definitions`.
5. **Privileges**: `REVOKE ALL ON FUNCTION … FROM PUBLIC` for all nine;
   `GRANT EXECUTE … TO {{auth_service}}` for the eight; nothing for
   `workflow_install_definition`; a comment block in `0016:159-173`'s voice
   on why schema USAGE is not re-granted (D337); `RESET ROLE;`. **No
   `NOTIFY pgrst`** — nothing in `api` moved (`0033:328-331`'s reason).
6. `-- migrate:down` with the `AP900` block verbatim from `0033:333-337`.

**Then** `bin/migrate.sh freeze-lock` (read its usage first; it writes
`migrations/released.lock.json`); `bin/migrate.sh verify-lock`; the
manifest entry; `docs/migrations.md` gains 0034's line in whatever table
lists the released migrations (read the page).

**Proofs** — `tests/contract/test_workflow_substrate.py`, `pytestmark =
[pytest.mark.contract, pytest.mark.p0, pytest.mark.database, pytest.mark.
security]` (D1240), the `cluster` fixture copied from `test_migrations_
apply_as_the_migration_user.py:95-163` with its two skips, migrations
applied as `migration_user` through `_apply_as_migration_user` (`:166`);
every function exercised through `psql -U postgres -c "SET ROLE <auth_
service>; SELECT app_private.…"` (the role name from the fixture's
rendered `outputs.json`); the sixteen node ids of §2 `WF-STATE-001`. The
privilege proofs use `has_table_privilege`/`has_function_privilege` with
the `anon` control (`test_agent_audit_plane.py:1344-1355`). The lease
proof sleeps 3 s over a 2 s lease (rig 32e's timings). The agent rows the
proofs need are created with `app_private.auth_create_agent` exactly as
`test_session9_agent_writes.py:181-190` does, with `service_source.load(
"hashing")`.

**Mutation battery**: (m1) drop `AND claimed_by = p_holder` from `finish`
→ the lost-lease proof FAILS; (m2) `lease_until <= now()` → `<` in the
claim's reclaim predicate: an uninformative mutation, expected to SURVIVE
and recorded as such (D493); (m3) grant `workflow_install_definition` to
`{{auth_service}}` → the nobody proof FAILS; control: `test_the_migration_
applies_as_the_migration_user_and_its_down_refuses` green in the same
invocation.

Targeted: `test_workflow_substrate.py`, `test_migrations_apply_as_the_
migration_user.py`, `test_rendered_migrations.py`, `test_database_function_
signatures.py`, `test_project_migration_sets.py`, `test_acceptance_
registry.py` (new module, D1240/D1242 — the registry entries are not yet
committed, so the sweep-selector proof passes vacuously for it; say so).
Commit (`Session 32 Run 3: migration 0034, the durable step substrate`),
push, read CI.

**Done.** Migration 0034 is written, frozen and proved under a real cluster, as
`migration_user`.

**The four questions §5 asked.** *The agents PK*: `app_private.agents.id`, a
`uuid PRIMARY KEY DEFAULT gen_random_uuid()` (`0011:175`) -- §9's stop condition
is not met, and `auth_create_agent`'s released arity is SEVEN (`0025:216`, with
`p_expires_at`), which is what the proofs call. *The PT codes*: **none is new.**
`grep -rhno "PT[0-9][0-9][0-9]" migrations/templates/*.sql` returns exactly
`PT401 PT403 PT404 PT409 PT412 PT422`, and 0034 reuses `PT403` (inactive agent,
`scope_not_held`), `PT404` (no such definition, no such run), `PT409` (a
definition installed with a different source, a definition with no steps) and
`PT422` (a claim with no holder, a lease under a second). Nothing enters
`mcp_errors.UPSTREAM_WRITE_REFUSALS`: these functions are called by the worker
over psycopg, never through PostgREST, and that map's guard is a **subset**
check over every template (`test_mcp_budgets.py:481-484`), which only grows more
permissive as templates add codes. *Does
`test_database_function_signatures.py` pin the set?* **No.** It is an ARITY
guard that DERIVES the released set from the migrations and scans the product
AND the proofs for call sites -- so the nine new functions join it automatically
and need no registration. It did find two things, and they were this module's
spelling: **D1677**. *The ledger count*: the fixture applies **34**, asserted by
name (`"20260917120034" in applied["versions"]`) and by count.

**The template.** `migrations/templates/0034-workflow-substrate.sql`, version
`20260917120034`, placeholders `object_owner` and `auth_service` -- exactly the
two the manifest entry declares, asserted by a marker scan after **D1679**
removed a `{{...}}` from a comment. Three enums, four tables, nine functions,
`REVOKE ALL FROM PUBLIC` on all nine, `GRANT EXECUTE` to `{{auth_service}}` on
eight, **nothing for `workflow_install_definition`**, schema USAGE not
re-granted (D337, it is 0011's), `RESET ROLE` below the privileges block (D285),
no `NOTIFY pgrst`, and the `AP900` down block verbatim from 0033. The manifest
gained one entry and **every earlier entry is byte-identical**, asserted by a
comparison before the write. `bin/migrate.sh freeze-lock` wrote
`migrations/released.lock.json` (34 migrations) and `verify-lock` agrees with
the manifest and the templates.

**The proofs.** `tests/contract/test_workflow_substrate.py`, `pytestmark =
[contract, p0, database, security]` (D1240), the cluster fixture copied from
`test_migrations_apply_as_the_migration_user.py:95-163` with both its skips, and
**every migration applied as `migration_user` over TCP** -- never as a
superuser, which is the whole of D285 and the reason every offline rig that
applies as `postgres` could report success for a migration that cannot be
applied. **Twenty-two proofs, all passing on their FIRST execution anywhere**,
which is rarer in this tree than it sounds (§7 question 2) and is attributable
to the rigs: 32d gave the privilege assertions their exact expected values --
including that `psql -qtA` renders `has_*_privilege()::text` as the WORDS -- and
32e gave the lease proofs their timings and the reason they sleep past a short
lease rather than holding a transaction open.

**The battery.** `PYTHONDONTWRITEBYTECODE=1`, `__pycache__` cleared before each
arm, four anchors pre-flighted to exactly one match with a miss fatal, restore
by copy with `cmp` verifying each, and the control
`test_the_migration_applies_as_the_migration_user_and_its_down_refuses` in
**every** invocation.

| Mutation | Subject | Read |
|---|---|---|
| m1 — drop `AND s.claimed_by = p_holder` from `finish` | `test_finish_by_a_holder_that_lost_its_lease_is_refused` | **FAILED** (a kill) |
| m2 — `lease_until <= now()` in the reclaim predicate | `test_an_expired_lease_is_reclaimed_with_the_attempt_incremented` | **PASSED — a RECORDED SURVIVOR** (D493) |
| m3 — grant `workflow_install_definition` to `auth_service` | `test_install_is_executable_by_nobody` | **FAILED** (a kill) |
| m4 — drop the earlier-positions-succeeded predicate from the claim | `test_claim_returns_the_lowest_unfinished_step_once_and_leases_it` | **FAILED** (a kill) |

The control read **PASSED** on all four, and every kill is a `FAILED` rather
than an `ERROR` — a broken fixture that never reached its assertion is not a
kill (D386). m2 survived **as the plan predicted**: `<` and `<=` on a lease
boundary differ only for a row whose `lease_until` is exactly `now()`, which no
proof can place and no deployment depends on. It is recorded rather than
converted into a proof, because a test written to kill an uninformative mutation
measures the mutation and not the product. The module is green after every
revert: **22 passed**.

**Targeted, once at the close** — and the list is the plan's plus the two
modules **D1674** bought: `test_workflow_substrate.py`,
`test_migrations_apply_as_the_migration_user.py`,
`test_rendered_migrations.py`, `test_database_function_signatures.py`,
`test_project_migration_sets.py`, `test_acceptance_registry.py`,
`test_evidence_claims.py`, and `test_documentation_index.py` +
`test_session12_documented_path.py` because the run touched a documentation
page. **222 passed.** The first pass read 2 failed and the second 1, both
recorded as **D1677** and **D1678**; neither was a defect in the migration.

**The sweep-selector guard passes vacuously for the new module, and that is
stated rather than relied on** (D1240/D1242): `WF-STATE-001` is not in
`tests/acceptance-registry.yaml` yet — Run 7 lands the registry, because moving
`CURRENT_SESSION` is all-or-nothing (D690) — so
`test_every_offline_claims_proof_is_swept_by_the_gate_that_reports_it` has
nothing to check for it. The module carries its `pytestmark` now so that when
Run 7 registers it the guard has something true to find.

**Repaired after CI.** Run 3's first push (`42672a0`) read **failure** on
`Session 1 gate` and `Session 2 offline contract` -- one proof, one cause:
`test_every_granted_function_has_a_caller`, refusing seven grants whose caller
the plan had scheduled for Run 5. **D1680**, and the repair is to ship the
caller with the grants rather than to except the migration from the guard.
`services/auth-api/app/workflow_repository.py` and
`tests/contract/test_workflow_repository.py` are Run 3's now; the targeted
list gained `test_migrations.py` and `test_auth_service_shape.py` and reads
**256 passed**.

**Rows added: D1675, D1676, D1677, D1678, D1679, and D1680 at the repair.
NEXT FREE: D1681.**

### Run 4 — the definition: schema, compiler, `init`/`validate`, step 6d, `apg dev`

**Read first:** `bin/mcp-contract.py:171-420` (how a project's lock is
resolved and where `apply_profile` runs); `src/agentic_postgres/capability_
manifest.py:80-95` (the project paths); `services/auth-api/app/mcp_lock.py:
293-373` (the reader whose vocabulary the compiler must match — **the
compiler in `src/` reads the lock as JSON with its own small reader, it
does not import the service's module**, ADR 0093's spirit); `bin/agent.py:
280-300` and `bin/agent.sh:1-60` (the `init` shape); `bin/deploy-project.
py:2318-2360` (step 6 → 6b); `bin/dev.py`'s `up` path (grep `def up` /
`migrate` in it); `src/agentic_postgres/rendering.py:1-120` (the `{{name}}`
substitution helper's name and where it lives).

1. **`schemas/workflow.schema.json`** (draft the tree's schemas use — read
   `schemas/capabilities.schema.json:1-20` for the `$schema` line):
   `schema_version: 1`; `name`; `version` (integer ≥ 1); `description`;
   `timeout_seconds` (1–3600, default 600); `steps` (1–32 items), each
   `{name, capability (pattern `^[a-z][a-z0-9_]*@\d+\.\d+\.\d+$`),
   arguments (object of string/number/boolean/null), retry {max 0–5,
   backoff_seconds 1–300}, timeout_seconds 1–600}`; `additionalProperties:
   false` everywhere.
2. **`src/agentic_postgres/workflow_definition.py`** (pure): `load(path) ->
   dict` (YAML, schema-validated with the validator the tree already uses —
   grep `jsonschema` in `src/`); `LockView.from_json(text)` (tools →
   capabilities, kind, arguments, `requires_approval`, `supports_dry_run`,
   `timeout_ms`, resources, `tools_sha256`); `compile(definition, lock:
   LockView) -> Compiled` with the refusal list of D1660, each a
   `DefinitionError(step_name, reason)`; placeholders resolved with the
   renderer's `{{name}}` substitution over a namespace of `input.<key>` and
   `steps.<name>.<field>`, where a reference must name an EARLIER step; the
   `Compiled` body is the JSON the loop reads (`steps[].{name, tool,
   capability, capability_version, resource, kind, arguments, retry,
   timeout_seconds}`, `timeout_seconds`, `required_scopes`, `lock_tools_
   sha256`, `source_sha256` over the YAML bytes); `definitions_of(project_
   set_root) -> list[Path]` over `workflows/*.yaml`.
3. **`src/agentic_postgres/workflow_install.py`**: `statements(compiled) ->
   list[tuple[argv_suffix, stdin]]` producing `psql -v name=… -v version=…
   -v body=… -v source=… -v lock=… -v scopes=… -c "SELECT app_private.
   workflow_install_definition(:'name', :'version'::integer, :'body'::
   jsonb, :'source', :'lock', :'scopes'::text[])"` — **the body as a psql
   variable, never formatted into the SQL** (a proof greps the module for
   `%` and f-strings around `SELECT`).
4. **`bin/deploy-project.py`**: `step("6d. Install the project's workflow
   definitions")` between `observe_database` (`:2349`) and `require_mounts_
   exist(…, "step 6b")` (`:2351`): resolve the project set root the way
   step 6's `migrate.sh … --project` resolves it; if no `workflows/`
   directory, print `no workflow definitions (the project declares none)`
   and continue; else resolve the project's lock exactly as `:2284` does,
   compile each file, and run each statement through `container_exec.run`
   against the database container as `postgres` (the way `bin/postgres-
   bootstrap.py:42` uses the helper) with `stdin` closed; a
   `DefinitionError` or a `PT409` → `fail(EXIT_VALIDATION, …)` naming the
   file and the reason. `--render-only` never reaches step 6.
5. **`bin/dev.py`**: after the project set is applied in `up`, the same
   compile-and-install over the dev container (superuser); print the count.
6. **`bin/workflow.sh` + `bin/workflow.py`** — `init` and `validate` only in
   this run (the HTTP verbs are Run 5's): header in `bin/agent.sh`'s shape
   (six verbs named, exit codes 0/2/3/5), usage with `--project FILE` on
   both verbs and a per-verb `--help`; `init --project FILE --name NAME`
   prints a two-step skeleton naming the lock's first read and first
   non-approval write capability; `validate --project FILE [--file PATH]`
   compiles every definition (or one) and exits 5 on the first refusal
   printing `<file>: step <name>: <reason>`. `chmod 755`, `git add`.
7. **`projects/example/workflows/notes-roundtrip.yaml`** and **`notes-
   retry.yaml`** (D1657), each with a comment header saying what it is for;
   `bin/workflow.sh validate --project project.example.yaml` exits 0.
8. **Registry plumbing for the command** (D1014): `SHELL_COMMANDS` gains
   `bin/workflow.sh`, `PYTHON_COMMANDS` `bin/workflow.py`, `COMMANDS_WITH_
   VERBS` the command with its six verbs. **Every verb's `--help` must exit
   0 with more than forty characters** (`test_cli_contract.py:476-516`), so
   the four HTTP verbs are declared in the usage now, their `--help` is
   real, and their handlers in this run exit 3 with *not yet available in
   this checkout (Session 32 Run 5)* only when invoked WITHOUT `--help`.
   The stub is removed in Run 5, and the Done says so.

**Proofs**: `tests/contract/test_workflow_definition.py` (the twelve of §2,
over `LockView.from_json` of `contracts/snapshots/mcp/mcp-capabilities.
canonical.json` joined with `projects/example/contracts/…` the way `bin/
mcp-contract.py lock` joins them — **call the product's join function, do
not re-implement the join**, D1114); `tests/contract/test_workflow_install.
py` (four; the AST scan finds the `step("6d.` call between `step("6.` and
`step("6b.`); `tests/contract/test_workflow_command.py`'s `init`/`validate`
proofs; `tests/contract/test_dev_environment_cluster.py::test_dev_up_
installs_the_example_projects_definitions` (`@requires_docker`, the
module's `environment` fixture, `as_superuser("SELECT count(*) FROM app_
private.workflow_definition")` = 2).

**Mutation battery**: (m1) delete the `requires_approval` refusal in
`compile` → the approval proof FAILS and `test_the_example_projects_
definitions_compile` stays green (control in the same invocation); (m2) let
a reference name a later step → its proof FAILS; (m3) move `step("6d.`
after `step("6b.` → the AST proof FAILS.

Targeted: the three new modules, `test_dev_environment_cluster.py`,
`test_dev_command.py`, `test_deploy_command.py`, `test_cli_contract.py`,
`test_printed_commands.py`, `test_session12_documented_path.py`. Commit
(`Session 32 Run 4: a workflow definition, compiled against the lock and
installed by the deploy`), push, read CI.

**Done.** Measured, in this order.

**The substitution helper was NOT reused, because there is none** (D1681):
`rendering.py` interpolates nothing and `migrations.render` is SQL's, with a
pattern that cannot match a dotted name and a residue guard that would then
refuse the whole text. `workflow_definition` carries its own `REFERENCE` and
`BRACES` pair and borrows the DISCIPLINE -- a `{{` the pattern did not consume
is a typo, not a literal.

**The join function was called** (D1114): `lock_view_for_project` walks the
same chain `bin/mcp-contract.py lock` walks -- `capability_manifest.project_
inputs` → `compile_joint_contract` → `capability_compiler.compile_lock` --
and both branches are exercised by the two example manifests, the one that
declares capabilities of its own and the one that does not. The one input a
checkout genuinely lacks is the deployment's address, so the lock is compiled
with `UNDEPLOYED_UPSTREAM` and **discarded**, which is what `mcp-contract.sh
check --project` already does with a narrowed contract. A proof compiles the
same contract under two different upstreams and requires one `tools_sha256`,
so the digest a definition RECORDS does not depend on the placeholder.

**The skeleton `init` printed** is derived from that lock and round-trips: a
proof fills only the `TODO`s its own comments ask for and requires the result
to `validate` at exit 0. It never names `set_note_embedding@1.0.0`, because a
scaffold whose first suggestion the compiler refuses is a scaffold that teaches
the wrong thing.

**The two definitions' compiled `required_scopes`:** `notes-roundtrip` →
`notes:read, notes:write` over `create_note@1.0.0` → `query_notes@1.0.0`
(`limit: 5`, resolved to the `notes` resource) → `create_note@1.0.0`;
`notes-retry` → `notes:write, tasks:write`, its first step
`update_task_status@1.0.0` with `retry: {max: 1, backoff_seconds: 45}`. That
step's `p_task_id` is `{{input.task_id}}` and not a literal uuid, because
`api.update_task_status` raises **PT404** for a task that does not exist --
terminal, and the run would end without ever parking -- and **PT409** only for
a task that exists in another status, which is the retryable `write_conflict`
the rehearsal needs. A uuid committed to that file would be right on no
deployment at all.

**The stub arrangement for the four HTTP verbs:** all six verbs are documented
with a real per-verb `--help` answered by the wrapper BEFORE the verb is
dispatched (D1395/D1402/D1405's shape), each exiting 0 with 441-907 characters;
the four exit **3** without `--help`, naming Session 32 Run 5. Exit 3 and never
10: ADR 0017's stub lifecycle is closed and `FUTURE_STUBS` is empty, and a 10
would reopen it. `bin/apg.sh` needed no edit, exactly as D1659 said -- its verb
table is derived from `bin/*.sh` -- and `apg workflow validate --project
project.example.yaml` exits 0.

**Two measurements changed the design** and both are rows. `-c` does not
interpolate a psql variable at all (**D1684**, rig 32g: `syntax error at or
near ":"`, every arm), so the statement goes to stdin through `-f -`; and only
a WRITE declares an argument list, so a read's accepted names are derived by
the runtime's own shape rule (**D1682**), with a proof parsing one real lock
through `ToolView.read_shape` AND `mcp_lock.Tool.read_shape` and requiring
agreement. `compile` takes `source_sha256` as a keyword rather than computing
it, because the plan's own signature takes a parsed document and the digest is
over the FILE's bytes; `compile_file` is the pairing.

**The battery: five mutations, five kills, five controls green, no survivors.**
(m1) the approval refusal deleted → `test_a_capability_that_requires_approval_
is_refused` FAILED while `test_the_example_projects_definitions_compile` stayed
PASSED in the same invocation; (m2) a reference allowed to name a later step →
FAILED, control `..._to_an_earlier_step_compiles` PASSED; (m3) step 6d MOVED
after step 6b in `bin/deploy-project.py` → the AST ordering proof FAILED,
control `..._as_the_superuser_over_the_socket` PASSED; (m4) `resource` added to
`RELATION_READ_ARGUMENTS` → FAILED, control `..._an_rpc_read_takes_no_
arguments_at_all` PASSED; (m5) `-f -` replaced by `-c` → FAILED, control
`..._names_as_many_values_as_the_migration_declares` PASSED. Anchors
pre-flighted to exactly one match, restore by copy with `cmp`, `__pycache__`
cleared before every run, 59 passed after the reverts.

**The install path was EXECUTED, not scanned.** `apg dev up` compiles and
installs both definitions through `workflow_install_definition` on a real
cluster: `test_dev_up_installs_the_example_projects_definitions` reads two rows
back, the body's prose through `:'body'` and the scopes as a two-element array
rather than one element containing a comma. The dev module is 9 passed.

**Targeted:** the three new modules plus `test_workflow_repository`,
`test_dev_environment_cluster`, `test_dev_command`, `test_deploy_command`,
`test_cli_contract`, `test_printed_commands`, `test_session12_documented_path`,
`test_acceptance_registry`, `test_evidence_claims`, `test_container_selectors`,
`test_migrations` and `test_documentation_index` -- the last five carried over
from D1674's and D1680's lessons rather than from this run's diff. **913
passed.**

**Rows added: D1681, D1682, D1683, D1684. NEXT FREE: D1685.**

### Run 5 — the worker loop, the three routes, `step_token`, and the four HTTP verbs

**Read first:** `main.py:79-249` whole; `service.py:188-300` and `:449-540`;
`routes.py:400-436` (`_guard`, `_service`, the response helpers) and
`:772-795`; `repository.py:140-220` (the agent lookup and its row shape);
`mcp_upstream.py:341-431` (`_dial`, the HTTP client the plane uses — the
loop uses the SAME client library and timeout constants, never a second
one); `storage_cleanup.py` whole again; `settings.py:434-456` (`REQUIRED_
VARIABLES` for auth mode — the loop reads NONE beyond these; the plane's
URL is derived: `http://{runtime_override.MCP_SERVICE}:{APG_LISTEN_PORT}
{MCP_ROUTE_PATH}` — read `runtime_override.py:230-280` for `MCP_SERVICE`'s
constant name); `tests/contract/test_auth_service_shape.py:380-420`
(the variable-set proof); `tests/security/test_session9_revocation.py:
60-130` (the fake repository shape); rig 32b's Done.

**The loop — `services/auth-api/app/workflow_worker.py`** (the module
docstring names the three orderings in `storage_cleanup.py:11-31`'s voice
plus the fourth: *mint after claim, drop at finish*):

- Constants with `#:` comments: `POLL_SECONDS = 5`, `SHUTDOWN_GRACE_SECONDS
  = 10` (below `stop_grace_period` 15 s), `CONNECT_TIMEOUT_SECONDS` and
  `READ_TIMEOUT_SECONDS` taken from the plane's client constants by import,
  `def lease_margin_seconds() -> int: return 2 * (CONNECT_TIMEOUT_SECONDS +
  READ_TIMEOUT_SECONDS)` (a function, `storage_cleanup.py:86-100`),
  `RETRYABLE_TOKENS = frozenset({"write_conflict"})`, `HOLDER =
  f"{socket.gethostname()}:{os.getpid()}:{int(time.monotonic())}"`.
- `class WorkflowRepository` in `workflow_repository.py` (the `storage_
  repository.py` shape): `claim(holder, lease_seconds)`, `finish(step_id,
  holder, outcome, result, reason)`, `park(step_id, holder, reason,
  resume_after)`, `heartbeat(holder)`, `enqueue(...)`, `cancel(...)`,
  `status(...)`, each one `SELECT app_private.workflow_…(%s, …)` with
  parameters, nothing formatted.
- `async def run_forever(*, repository, service, plane_url, now=time.
  monotonic, client=None)` — the loop: heartbeat; claim with `lease =
  step.timeout_seconds + lease_margin_seconds()`; nothing claimed → sleep
  `POLL_SECONDS`; else `await process(step)` then loop again without
  sleeping.
- `async def process(step)`: `started = now(); deadline = started + lease
  - lease_margin_seconds()`; **mint** `token = service.step_token(step.
  agent_id)` — `AuthenticationFailed` → `finish(…, "token_refused", None,
  str(exc))` and return; resolve the step's arguments over `input` and
  `prior` (the same substitution the compiler validated; an unresolvable
  reference → `finish(…, "failed", None, "input_unresolved: …")`); if
  `now() >= deadline` → `finish(…, "abandoned", …)` and return (the step is
  reclaimed by the next claim, attempt + 1 — say so in the docstring);
  **call** `POST {plane_url}` with `{"jsonrpc": "2.0", "id": 1, "method":
  "tools/call", "params": {"name": step.tool, "arguments": {…, and for a
  write "idempotency_key": step.idempotency_key, "dry_run": run.dry_run}}}`,
  headers `Authorization: Bearer <token>`, `Accept: application/json,
  text/event-stream`, `X-Request-Id: <step.request_id>`, timeout
  `step.timeout_seconds`; parse the SSE frame the way `sse_result` does
  (rig 32b's shape); classify: a result → `finish("succeeded"|"replayed"|
  "dry_run", result)` reading the plane's outcome word from the result's
  audit outcome field if present, else `succeeded` — **read rig 32c/32b's
  Done for where the word `replayed` appears in a write's result and cite
  it in the code**; an error whose token is in `RETRYABLE_TOKENS`, or a
  transport error, or a timeout → `attempt <= retry_max` ? `park(…,
  reason, now + backoff)` : `finish("failed", None, token)`; any other
  token → `finish("refused", None, token)`. `del token` at the end of every
  path (the AST proof looks for the name surviving the function).
- `async def supervise(app_state)` — the task `lifespan` creates:
  `while True: try: await run_forever(...) except CancelledError: raise
  except Exception: log.exception(...); await asyncio.sleep(POLL_SECONDS)`.
- `lifespan` (`main.py:79-165`): in `auth` mode only, after `application.
  state.service` is built: `task = asyncio.create_task(workflow_worker.
  supervise(application.state))`; on exit, before the pool closes: `task.
  cancel(); await asyncio.wait_for(task, SHUTDOWN_GRACE_SECONDS)` inside a
  `try/except`, in the order the docstring's *pool last* rule requires.

**`AuthService`** (`service.py`): `_agent_for_issue(agent_id) ->
credential` carrying the lookup, the uuid check, the `status` check and
the `secret_expired` check in the existing order with the existing
messages; `agent_token` = `_agent_for_issue` + the hash comparison **in the
existing order** (the hash is compared BEFORE the status is consulted,
`:453` — keep that: the split must not reorder; so `agent_token` does the
lookup, the hash, then calls the status/expiry half; write it as two
helpers, `_agent_record(agent_id)` and `_refuse_unless_issuable(
credential)`, and the Done quotes the before/after message list from a
proof); `step_token(agent_id)` = `_agent_record` + `_refuse_unless_
issuable` + `issue(…, token_use="agent")`. `authenticate_agent(
authorization) -> AgentPrincipal` (D1651): bearer parse and `jwt.decode`
as `authenticate` does (`:277-296`), `verify_claims`, then **require
`token_use == "agent"`**, load the record, refuse unless `active` and
`authz_version` matches; the principal carries `agent_id, owner_id,
scopes, authz_version`.

**Routes — `services/auth-api/app/workflow_routes.py`**, mounted on the
auth router in `auth` mode (`main.py:243-249`): `POST /workflows/runs`
(body model `WorkflowRunRequest {name, version, input: dict = {}, dry_run:
bool = False}`, strict like `AgentTokenRequest`; 201 `{run_id, status}`;
`PT404` → 404 `{"error": "no_such_definition"}`; `PT403 scope_not_held` →
403 `{"error": "scope_not_held"}`), `GET /workflows/runs/{run_id}` (200 the
status document; 404 for another agent's or a missing run — one message),
`POST /workflows/runs/{run_id}/cancel` (200 `{run_id, status}`; 404 the
same). Every handler: `_guard`, `authenticate_agent`, the repository call,
`Cache-Control: no-store`. `openapi_docs.py` gains the three operations'
descriptions the way `DOC_AGENT_TOKEN` is written; `bin/app-contract.sh
--update > contracts/app-openapi.canonical.json` then `--check` (read
`bin/app-contract.sh:1-41` — `--update` streams to stdout).

**`bin/workflow.py`**: `run`, `dry-run`, `status`, `cancel` replace Run 4's
stubs: `--project-outputs FILE` (the `bin/api.py:139` shape, the base from
`routes.app.url`), the token from `APG_AGENT_TOKEN` (`TOKEN_VARIABLE`, a
`# noqa: S105` comment as `bin/api.py:31`), `ROUTES = {"run": ("POST",
"/workflows/runs"), "status": ("GET", "/workflows/runs/{run_id}"),
"cancel": ("POST", "/workflows/runs/{run_id}/cancel")}` as the closed
table; `run --definition NAME@VERSION [--input JSON]` prints `run_id`;
`dry-run` the same with `dry_run: true`; `status --run ID` prints the
document; `cancel --run ID`. Exit codes 0/2/3/5 (5: the route refused,
printing the error word).

**Proofs**: `tests/contract/test_workflow_worker.py` (the fourteen of §2)
over `service_source.load("workflow_worker")` with a fake repository
recording calls in order, a fake service whose `step_token` counts calls
and can raise, and a fake HTTP client returning canned SSE frames (rig
32b's bytes); the AST proof (`no name token outlives process()`); the
supervisor proof raises inside `run_forever` once and asserts a second
call happens and the fake app state is untouched; the mode proof asserts
`create_task` is reached only under `mode == "auth"` (an AST scan of
`main.py`'s lifespan). `tests/contract/test_workflow_routes.py` (the seven
of §2) over `create_app("auth")` with the fakes, using the tree's existing
route-test shape (grep `TestClient` under `tests/contract/test_auth_*`).
`tests/contract/test_auth_service_shape.py::test_the_auth_mode_reads_no_
new_variable` (compare `REQUIRED_VARIABLES` to the compose environment as
`:390-408` already does — this may be an existing proof made stricter by a
sentence; say which). `tests/contract/test_workflow_command.py`'s four HTTP
proofs (the closed table, the environment token, `dry_run: true`, no SQL).
`tests/contract/test_agent_plane_contract.py` whole (`BUDGET_CLAIMANTS`
unchanged, D1653).

**Rig 32a's second arm, if Run 1 deferred it**: the built image with the
real loop, idle against the rig cluster with 0034 applied, RSS after 60 s;
then under a rig run (a definition installed, an agent created, a run
enqueued through the route, the plane from rig 32b answering) — **this is
the first end-to-end execution of the loop anywhere and it is expected to
find something** (§7 question 2); whatever it finds is a row.

**Mutation battery**: (m1) mint once before the loop and reuse → `test_one_
token_per_step_attempt_and_none_outlives_the_step` FAILS; (m2) call before
claim → the order proof FAILS; (m3) treat `scope_not_held` as retryable →
the terminal proof FAILS; (m4) `authenticate_agent` accepting `access` →
its proof FAILS and `test_authenticate_still_refuses_an_agent_token` stays
green (control).

Targeted: the four new/edited modules, `test_auth_service_shape.py`,
`test_auth_service_database_access.py`, every `tests/contract/test_auth_*`
and `tests/security/test_session9_revocation.py`, `test_agent_plane_
contract.py`, `test_cli_contract.py`, `test_app_contract.py` (or whatever
module runs `app-contract.sh --check` — `grep -rln app-contract tests/
contract`). Commit (`Session 32 Run 5: the worker loop in the auth process,
and the run surface`), push, read CI.

**Done.** Measured, in this order.

**The plane's client constant is IMPORTED and the address is not** (D1685).
`lease_margin_seconds()` is `2 * mcp_upstream.UPSTREAM_TIMEOUT_SECONDS`, an
import of the plane's own one constant -- never the `CONNECT_`/`READ_` pair,
which belongs to `storage_client` and to boto3 (D1670), and a proof reads the
module's AST rather than its text to say so, because the docstring NAMES
`storage_client` to explain what it is not reading and the first spelling of
that proof failed on that sentence (D680's shape). The ADDRESS could not be
imported at all: `runtime_override` is not in the image and `mcp_runtime` pulls
in the agent framework, so three constants are spelled in the loop and bound by
a proof to the deploy's own.

**Where `replayed` appears: nowhere the loop can see it** (D1671). A successful
call finishes `succeeded`, and `test_a_successful_call_finishes_the_step_and_
the_replay_is_not_the_loops_to_see` asserts both halves -- the outcome, and
that the string `"replayed"` does not occur in the module. ADR 0195's rule: a
reader that cannot determine something reports that rather than assigning the
likelier answer.

**The message list before and after the split** is identical, and
`_refuse_unless_issuable` is where the two checks LIVE rather than a second
copy written to look like them: `no such agent`, `agent is <status>`, `agent
secret has expired`. `agent_token` keeps its own `None` check in its own place,
because *"no such agent"* has to answer before *"secret mismatch"* -- an
unknown agent has no stored hash, so `matched` is False for it. The one
asymmetry is the one that must exist: `step_token` pays no hash, because there
is no secret to compare.

**Rig 32a's loop delta was Run 1's** (7.8 MiB RSS idle, against a 32 MiB
criterion) and Run 5 owed the second arm: **the loop's first end-to-end
execution anywhere, rig 32j.** The released image in `auth` mode with the real
loop in it, a cluster carrying all 34 migrations, a definition installed, an
agent registered, a run enqueued, and a fake plane answering at
`http://mcp:8080/mcp` in rig 32b's measured shape and recording every request.

**It found nothing, and that is the finding.** Fifteen arms, all green on first
execution: the container starts READY with the loop in it; the heartbeat
reaches the table within four seconds; a three-step run completes with every
step `succeeded`; the plane receives exactly three calls; each carries the
step's OWN `request_id` as `X-Request-Id` (which is D1686's repair, executed);
each write carries the substrate's derived key and the read carries the
compiler's `resource` and neither a key nor a `dry_run`; the third step's
`{{input.title}}` resolves from the run's input; **three calls carry three
distinct bearers**, each decoding as `token_use: agent` for that agent with the
agent's STORED scopes. The control: a REVOKED agent's run stops as `stopped
agent_not_active` with `token_refused` on its first step and **no additional
call to the plane**. §7 question 2 expected a first execution to fail and it
did not -- because Run 1's rigs had already found the three things that would
have broken it (D1668, D1671, D1672) and this run was written against those
measurements rather than against the plan's sketch.

**Two measurements amended migration 0034, which is frozen and unapplied.**
D1686: the claim minted a `request_id` and did not return it, so the two sides
of the correlation would have carried different values. D1687: the claim cannot
take an absolute lease, because the step's timeout arrives in its own result --
it takes a MARGIN now, and the lease is the step's timeout plus it. The lock
was re-frozen and BOTH example projects re-rendered (D1678). After Run 8's
deploy this window closes and the same repair is a 0035.

**The battery: six mutations, five kills, one recorded survivor, every control
green in the same invocation.** (m1) mint once and reuse → the token proof
FAILED; (m2) the `del token` removed → FAILED; (m3) `scope_not_held` made
retryable → the terminal proof FAILED; (m4) `authenticate_agent` widened to
accept an access token → FAILED; (m5) the `isError` branch disabled, which is
D1672's own shape → FAILED; (m6) the route's `agent_id` taken from the request
body → **SURVIVED, and it is informative** (D493): `WorkflowRunRequest` is
`extra="forbid"`, so a body carrying `agent_id` is a 400 before the handler
runs and the fallback is unreachable. The model's closure is what makes the
route's agent id unspoofable, not the route's code.

**Two of those mutations were kills only after the proofs were repaired**, and
the battery is what said so. m1 survived a proof that drove ONE step -- *one
token for one step* and *one token PER step* are different sentences, and only
the second is the property, so it now drives `process` twice. m4 survived a
proof that read the two `token_use` constants and the source; what can see a
widened comparison is a token minted with `token_use="access"` and driven
through the real `AuthService`, so the module now builds one with a generated
key and a fake repository, rig 32f's shape.

**Two smaller notes.** The plan's *"grep `TestClient` under `tests/contract/
test_auth_*`"* finds nothing: this tree drives an application over
`httpx.ASGITransport`, which is what `test_auth_endpoints.py` does, and the
route proofs follow it with the LIFESPAN not run and the two state members set
directly -- stated in the module's docstring rather than hidden, with
`test_the_loop_starts_in_auth_mode_only` as the half that reads the assembly.
And `bin/workflow.sh`'s Run 4 positional argument is replaced by the plan's own
Run 5 spelling, `--definition NAME@VERSION` and `--run RUN_ID`, so no value
this command takes can be swapped by position.

**Targeted:** the four new and edited service modules' proofs, plus
`test_workflow_repository`, `test_auth_service_shape`,
`test_auth_service_database_access`, `test_agent_plane_contract`,
`test_cli_contract`, `test_app_contract_aggregate`, `test_printed_commands`,
`test_acceptance_registry`, `test_evidence_claims`, `test_migrations`,
`test_container_selectors`, `test_documentation_index`,
`test_session12_documented_path` and `tests/security/test_session9_revocation`.
**975 passed.**

**Repaired after CI.** Run 5's first push (`8816d86`) read **failure** on both
code jobs: five proofs across four modules, one cause. The app OpenAPI
document gained three operations and the generated example client records
its digest -- **D1690**, and CLAUDE.md §5's own table names the command that
would have caught it. The client was regenerated (no bump: the shape did not
move), and `test_client_typescript`, `test_generate_command`,
`test_studio_command` and `test_client_ir` joined the targeted list, which
reads **123 passed** over them and the two aggregates.

**Rows added: D1685, D1686, D1687, D1688, D1689, and D1690 at the repair.
NEXT FREE: D1691.**

### Run 6 — the readers: the doctor's twelfth check, `worker-restart`, the restore member, the docs, the threat row

**Read first:** `bin/doctor.py:739-780` and one probe with SQL (`agent_
record`'s, grep `agent_record_size`); `diagnosis.py:560-660` (the check
renderers) and the `agent_record` verdict function; `rehearsal.py:293-330`,
`:773-844`, `:965-1050`; `bin/rehearse.py:192-260`, `:343-480`, `:761-790`;
`bin/rehearse.sh:1-73`; `bin/restore-test.py:455-485`; `docs/operator-
guide.md:1143-1300` (§16's shape); `docs/threat-model.md:19-35`;
`docs/README.md:1-60`; `docs/recovery-operations.md:95-125`.

1. **`bin/doctor.py`**: `probe_workflow(document)` runs `SELECT app_
   private.workflow_counts()` through the cluster the way the `agent_
   record` probe runs its statement (as `postgres`, via `container_exec.
   run`, the statement a module constant `WORKFLOW_SQL`), returning the
   JSON or `None` with the error text when the function is absent (a
   pre-0034 cluster). `diagnosis.workflow_record(counts)`: `OK` with the
   counts and ages as evidence, **no threshold** (D1441's `agent_record`
   shape), `UNKNOWN` naming `app_private.workflow_counts` when `None`. The
   twelfth check appended at `:739-759`; the eleven-check proof renamed to
   twelve (§2). `bin/fleet.py:102-133` and `rehearsal._doctor` re-run.
2. **`worker-restart`** (`rehearsal.py`): `SCENARIOS` gains it (with a
   comment naming this session and ADR 0226); `_worker_restart(facts)`:
   `container = facts.containers.get("auth")`, `pid = facts.container_
   pids.get("auth")`, `heartbeat_before = facts.workflow_heartbeat` (a new
   fact gathered by `bin/rehearse.py` from `doctor --json`'s `workflow`
   check; refuse with `RehearsalError` when the check is `UNKNOWN` — *the
   reader must read before the kill*); `induce = Action(kind="run", argv=
   ("kill", "-KILL", str(pid)), what=…)` in the termination scenario's
   words; `observe = (Observation("state_after_kill", …, control=True),
   Observation("heartbeat_after_restart", argv=doctor --json, expect="a new
   holder within 60 s"), Observation("steps_after_restart", the same
   argv, expect="no step claimed past its lease"))`; `reverse` = the
   restart policy with `docker start` as the fallback (copy the termination
   scenario's); `verify=()`; `induced=True`; `BOUNDS["worker-restart"] =
   120`. The `verdict()` arm: `read` when the holder changed and no lease is
   overdue, else not read. `_PLANNERS` entry; `bin/rehearse.py`'s observer
   arm polls the doctor every 5 s up to the bound for the holder change;
   `bin/rehearse.sh` usage gains the paragraph and **its header's count is
   corrected** (D1664) to a sentence that does not carry a number.
3. **`bin/restore-test.py`**: the evidence dictionary (`:459-480`) gains
   `workflow_runs` from `SELECT app_private.workflow_counts()` on the
   drill, or `{"value": null, "reason": "app_private.workflow_counts is
   not present in the restored cluster"}` when the query fails (ADR 0195).
4. **`docs/workflows.md`** — *Workflows* — the page a developer reads: what
   a definition is, the YAML with the two example files quoted, the six
   verbs with their exact lines, what a run's status document looks like,
   what `replayed`/`parked`/`stopped` mean, what the worker is (one
   paragraph, ADR 0226), what it may not do (the stage plan's *Must not*
   list, as the product's promises), and *what is not here* (approval,
   wait, compensation, inspect — Session 33; events — 34). Linked from
   `docs/README.md` (`| [Workflows](workflows.md) | … |` under *Developer
   loop*). `docs/operator-guide.md` gains **§17 *Workflows, on a
   deployment*** in §16's shape: the doctor's twelfth check read, the
   rehearsal's line, the restore drill's member, `apg workflow status` for
   an agent's own run, and *if something goes wrong* (a stopped run: read
   `stopped_reason`; a parked run: read `resume_after`; a lease overdue:
   the worker is dead, `service-termination`'s recovery). `docs/recovery-
   operations.md` gains the scenario's line beside `admission-refused`'s.
   `docs/session-08-operator-guide.md` and `docs/mcp-tool-catalog.md` are
   NOT edited (the plane did not move).
5. **`THR-WORKER`** in `docs/threat-model.md`'s table, nine cells, Target
   session 32: attacker capability *a compromised auth process, or an
   operator's SQL against the four tables*; asset *every agent's ability to
   act, and the notes and tasks a run may write*; prevention *the loop
   holds the auth service's role and a per-step token minted through the
   same status and expiry checks an agent's own mint passes; the tables
   grant nothing; a step is a plane call under the plane's scope check;
   revocation stops the next step*; detection *the doctor's `workflow`
   check, the heartbeat, `agent_audit` rows correlated by request id*;
   residual *the auth process already holds the signing key, so a
   compromise of it was always total — the loop adds the ability to spend
   an ACTIVE agent's quota on that agent's own capabilities, and nothing
   else; an operator with root can insert a run row by hand, which the
   loop would execute as the named agent — the same operator can already
   mint any token*; requirements `WF-WORK-001`, `WF-STATE-001`, `WF-REVOKE-
   001`; node ids `tests/contract/test_workflow_worker.py::test_one_token_
   per_step_attempt_and_none_outlives_the_step`, `tests/contract/test_
   workflow_substrate.py::test_no_role_holds_a_privilege_on_the_four_
   tables`. **The row lands in Run 7 with the registry entries** (D1621:
   `test_threat_model_requirement_ids_exist_in_the_registry` would go red
   here); its full text is written in this run's Done, ready to paste.
6. `bin/apg-diag.sh:140`'s stale *three of thirteen* corrected (D1664).

**Proofs**: `test_doctor_readings.py` (three of §2 `WF-READ-001`, plus the
redaction proof `test_doctor_redaction` run over the new check — grep for
it); `test_rehearsal.py` (three; the parametrised
`test_every_scenario_plans_three_phases_and_prints_every_command` runs
whole and the `induced` assertion at D1612 stays unedited); `test_restore_
test_command.py` (one); `test_documentation_index.py`, `test_session12_
documented_path.py` whole.

**Mutation battery**: (m1) a threshold in `workflow_record` (`PROBLEM` when
`parked > 0`) → `test_the_workflow_check_reports_counts_and_ages_with_no_
threshold` FAILS; (m2) `docker kill` in the planner's argv → `test_worker_
restart_signals_the_auth_process_and_reads_the_heartbeat` FAILS; control:
`test_admission_refused_has_a_verdict_arm` green in the same invocation.

Targeted: the four modules above, `test_fleet*.py`, `test_cli_contract.
py`. `bin/render-mcp-catalog.py --check` (unchanged, a control). Commit
(`Session 32 Run 6: the readers -- the doctor, the rehearsal, the drill,
the pages`), push, read CI.

**Done.** The readers are built and the tenth rehearsal has been driven end to
end against a rig.

**The twelfth check.** `probe_workflow` is `probe_agent_record`'s shape
exactly -- one `psql` round trip over the container socket as the superuser,
the statement a module constant (`WORKFLOW_QUERY`), the verdict computed by
`diagnosis.workflow_record` from values the probe parsed. Six evidence keys:
`definitions`, `runs` and `steps` as `status=count` strings, and
`oldest_claimed_lease_age_seconds`, `heartbeat_age_seconds`,
`heartbeat_holder`. **No threshold anywhere**, asserted at every magnitude of
both ages and every parked count, with the argument written into the test that
a future edit has to delete. Three `UNKNOWN` paths: no container in the
document, a cluster that did not answer (which is also every deployment below
1.10.0, and the detail says so in this program's words rather than psql's), and
a reply that is not the shape asked for. Appended LAST in `diagnose()`, so
`bin/fleet.py` and `rehearsal._doctor` find the eleven where they were.

**Two cluster values reach the report and both are guarded.** A status NAME
(rendered into `runs` and `steps`) and the heartbeat HOLDER. The holder's guard
was written as an alphabet and **the redaction scan found it in the same run**
-- `^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$` admits any sentence without a space in
it. It is now the shape `worker_identity()` builds, and the status guard is
deliberately still a shape so a status a later migration adds appears rather
than being dropped (**D1693**).

**The tenth rehearsal.** `worker-restart`: SIGKILL to the `auth` container's
main process, never `docker kill` (D1015), bound 120 s, the restart policy as
the reversal with `docker start` as the conditional fallback. **The reading is
the heartbeat's HOLDER and not the check's verdict** -- the check has no
threshold and reads `ok` throughout, so a verdict could not tell a loop that
came back from one that never stopped. The holder is read BEFORE the kill, and
the refusal when it did not come back is `refuse_without_a_reading`, called
after `--plan` has returned rather than inside the planner: `--plan` takes no
readings and a proof three sessions old says so (**D1694**). The observer
records the last holder it read on every poll, so *never changed* and *never
read* are two findings rather than one (**D1695**). The control is the
container's restart count. `BOUNDS["worker-restart"] = 120`; `DEPLOYED_DOCTOR_
CHECKS` gained `workflow`; `rehearsal.doctor_evidence` reads one value out of
one check's evidence and maps the string `"null"` back to `None`.

**Driven end to end against the rig**, not only planned: the process is
signalled, the policy brings it back, the poll reads the holder until it moves,
`verdict` is `read`, the reversal verifies and the in-progress file is gone.
And the failure it exists to catch is driven too -- a rig whose holder does not
move reads `unread` with *"never stopped"*, exit 6.

**The restore drill's member.** `workflow_runs`, counts by status, or
`{"value": null, "reason": ...}` when the restored cluster has no such function
-- a backup taken before 0034 restores one, and that is a fact about the backup
rather than a failed drill (the verdict is untouched either way). It needed
`restore_drill.evidence_document` to move as well, because that function selects
fields by name and a member in the reading alone would have had no reader
(**D1691**).

**The pages.** `docs/workflows.md` is new and indexed under *Developer loop*:
what a definition is with both example files quoted, the six verbs, the run
status document, what `parked`, `stopped`, `cancelled` and `replayed` mean, one
paragraph on the worker, the five things a run may never do, and a table of
what is not here yet with the session that brings each. `docs/operator-guide.md`
gained **§17**, §16's shape: the twelfth check with the two figures to read
together, the rehearsal with *rehearse it when no run is in flight*, the drill's
member, an agent's own run, and five things that go wrong.
`docs/recovery-operations.md` gained the ninth AND tenth rehearsal rows --
`admission-refused` was never added there by Session 31 (**D1692**) -- and its
check count moved to twelve.

**Three stale counts corrected** (D1664, and one more than the plan named):
`bin/rehearse.sh:4`'s *"Eight scenarios"* and `docs/recovery-operations.md:95`'s
both became sentences with no number in them, and `bin/apg-diag.sh:140`'s
*"three of thirteen services"* became **nine of twenty**, measured from
`compose.yaml` -- auth, backup-mirror, docs, edge-probe, mcp, metrics, postgrest,
storage, store, and neither postgres nor pgbouncer. D210's finding never
depended on the number.

**The eleven-check proof was renamed to twelve**, so
`tests/acceptance-registry.yaml`'s node id moved with it and
`docs/acceptance-matrix.md` was regenerated -- D1119, and the fourth chance this
session has had to repeat D1674.

**`THR-WORKER`, ready to paste in Run 7** (it cannot land here:
`test_threat_model_requirement_ids_exist_in_the_registry` would go red against
requirement ids the registry does not carry until Run 7 -- D1621):

> \| `THR-WORKER` \| A compromised `auth` process, or an operator with root
> running SQL against the four `app_private` workflow tables \| Every agent's
> ability to act, and the notes and tasks a run may write \| The loop holds the
> auth service's own role, pool and token issuance and nothing more (ADR 0226);
> a step's token is minted through the same status, expiry and scope checks an
> agent's own mint passes, held for one call and discarded; the four tables
> grant no privilege to any request role; every step is an ordinary plane call
> under the plane's scope check, audit, budget and idempotency claim; a
> definition names capabilities from a closed vocabulary and takes no SQL, path
> or query; revocation stops the run at its next step boundary \| The doctor's
> `workflow` check -- counts by status, the oldest overdue lease and the
> heartbeat's age and holder; the `worker-restart` rehearsal; `agent_audit`
> rows correlated to a step by its `request_id` \| The auth process already
> holds the signing key, so a compromise of it was always total -- what the
> loop adds is the ability to spend an ACTIVE agent's quota on that agent's own
> capabilities, and nothing else. An operator with root can insert a run row by
> hand and the loop will execute it as the named agent; the same operator can
> already mint any token, so this widens no boundary. A step already claimed
> when an agent is revoked is refused at the token, not after the call \|
> `WF-WORK-001`, `WF-STATE-001`, `WF-REVOKE-001` \|
> `tests/contract/test_workflow_worker.py::test_one_token_per_step_attempt_and_none_outlives_the_step`,
> `tests/contract/test_workflow_substrate.py::test_no_role_holds_a_privilege_on_the_four_tables` \|
> 32 \|

**Mutation battery: five kills, no survivors**, each with a control the
mutation cannot reach, green in the same invocation, HOW each failed asserted
(FAILED, never ERROR), anchors pre-flighted to one match with a miss fatal,
restored by copy and `filecmp`, and the ten proofs green again afterwards.
(m1) a `PROBLEM` when a step is parked kills the no-threshold proof; (m2)
`docker kill` in the planner's argv kills the induce proof; (m3) the holder
guard loosened back to an alphabet kills the guard's own proof; (m4) the
observer recording only a CHANGED holder kills the same-holder rehearsal; (m5)
an absent substrate reported as `{"value": {}}` kills the drill's third
outcome. m4's first control was the worker-restart end-to-end proof, which the
mutation runs through -- replaced with `admission-refused`'s, which it cannot
reach (D499).

Targeted, once at the close: `test_diagnosis`, `test_doctor_redaction`,
`test_doctor_readings`, `test_rehearsal`, `test_restore_test_command`,
`test_fleet`, `test_cli_contract`, `test_documentation_index`,
`test_session12_documented_path`, `test_acceptance_registry`,
`test_evidence_claims`. `bin/render-mcp-catalog.py --check` is current, the
control the plan asked for.

**Rows added: D1691, D1692, D1693, D1694, D1695. NEXT FREE: D1696.**


### Run 7 — the bump, the registry, the gate, and the trip's proofs

**Read first:** `src/agentic_postgres/__init__.py:490-560` (31's paragraph
and `CURRENT_SESSION`); `bin/session-31-check.sh` whole — **yes, whole:
1634 lines, and D1199 says the last ones are the least executed**; `tests/
contract/test_session_thirty_one_gate_modes.py`; `bin/upgrade.py:100-140`
and `:380-420`; `docs/upgrade-guide.md`'s release table; `README.md:1-40`;
`tests/deployment/test_session31_capacity.py` whole (the shape the trip's
proofs copy, including its `--setup-plan` history in D1637/D1639);
`tests/recovery/test_future_pitr.py` and `tests/recovery/conftest.py`.

1. **The registry**: `ID_PATTERN` gains `WF` with its paragraph; the
   thirteen entries of §2 with node ids read from `pytest --collect-only
   -q tests/contract/test_workflow_*.py tests/contract/test_capacity_
   reading.py tests/contract/test_doctor_readings.py tests/contract/test_
   rehearsal.py tests/contract/test_restore_test_command.py tests/
   deployment/test_session32_workflows.py tests/recovery/test_session32_
   workflow_restore.py` (D1236); `evidence_claims.py`'s thirteen claims,
   eight in `OFFLINE_CLAIMS`, thirteen in `CLAIM_INTRODUCED_IN`; the
   `THR-WORKER` row pasted from Run 6's Done; `bin/render-acceptance-
   matrix.py --write`; `bin/render-config.py --bounds-doc --write`.
2. **`CURRENT_SESSION = 32`**; the Session 32 paragraph in `__init__.py`
   in 31's shape (`:490-553`): what moved (the inventory in this plan's
   header), the `upgrade plan` reading **with the declared classes** (D1666)
   and its verdict, the MINOR argument, the `WF` family, `OFFLINE_CLAIMS`
   24 → 32 and `CLAIMS` 145 → 158 *counted from the tuples*; **the pricing
   paragraph LAST** (D1629). `VERSION` → `1.10.0`; `README.md:7`;
   `docs/upgrade-guide.md`'s release table gains the `1.10.0` row (what it
   adds, that it applies migration 0034, that a rollback by image is not
   possible past it — ADR 0162 §3); `bin/apg.sh generate --project project.
   example.yaml` regenerates `projects/example/clients/typescript/*`
   (D1238) and `--check` exits 0.
3. **The trip's proofs — `tests/deployment/test_session32_workflows.py`**,
   `pytestmark = [pytest.mark.live_host, pytest.mark.p0, …]` as
   `test_session31_capacity.py` marks itself: fixtures `notes_agent`
   (an `agent_writer` agent on **project_b** with `notes:read, notes:write,
   tasks:write`, created through `auth_create_agent` with the hasher from
   `service_source`, token from `/auth/agent-token`, deleted in `finally`
   together with every `app.notes` row whose title carries the proof's
   canary prefix — the `mcp_writer_session` shape verbatim), `second_
   notes_agent` (the revocation control), `workflow_route(document)`
   (`routes.app.url + "/workflows/runs"`), `run_status(token, run_id)`
   polling every 2 s up to 120 s for a terminal status, `audit_row_for(
   request_id)` via `psql` (the `_audit_rows` shape), `auth_backends()` via
   `psql` reading `pg_stat_activity` for the `auth_service` role name from
   the document, `workflow_step_rows(run_id)` via `psql`. Then the twelve
   proofs of §2 (`NODE-READ-003`, `WF-RUN-001`, `WF-RESUME-001`, `WF-REVOKE-
   001`): the three-step run; the correlation join (`SELECT count(*) FROM
   app_private.agent_audit a JOIN app_private.workflow_step s ON s.request_
   id = a.request_id WHERE s.run_id = …` = 3); the backend ceiling sampled
   every 200 ms during the run (max ≤ 6); the dry-run (two `dry_run`
   outcomes, `app.notes` count unchanged); alpha's 404 with `no_such_
   definition`; **the constructed post-crash state** (D1652 a): enqueue
   `notes-roundtrip` with `input.title` = a canary, immediately perform
   step 2's `create_note` through `mcp_rpc` AS the agent with `idempotency_
   key = "wf-<run>-again"` (read the step's name from the YAML) — the loop
   may or may not have reached step 1 by then and that is fine: what is
   asserted is that when the run is terminal, step `again` has outcome
   `replayed` OR the proof's own call was the replay (the audit shows
   exactly one `committed` and one `replayed` for that key between them)
   and `app.notes` holds ONE row with that title; the `PT412` control
   (the same key with a different `p_content` → `input_not_permitted`);
   the parked run (`notes-retry`, its first step parking on `write_
   conflict` with backoff 45 s — assert `status parked` within 15 s), then
   `bin/rehearse.sh worker-restart --outputs <project_b outputs>` run
   through `as_root` (its record path printed), then the run reaching
   `failed` with `attempt = 2` on step 1 and `stopped_reason` naming
   `write_conflict` (the definition's `retry.max` is 1, so the second
   attempt is the last); the rehearsal record's readings: a new holder,
   `steps_after_restart` with no overdue lease; the revoked run: a revoked agent cannot ENQUEUE (the route's
   `authenticate_agent` and `workflow_enqueue`'s own `PT403` both refuse
   it), so the revocation must land AFTER the enqueue and BEFORE the loop
   mints for a step. The order is: enqueue a `notes-roundtrip` run for
   `notes_agent`, revoke through
   `PATCH /admin/agents/{id}` `{"status": "revoked"}` as the admin session
   (`test_session9_agent_writes.py:1274`'s shape) in the same second, and
   assert the terminal status is `stopped` with `agent_not_active`.
   **This is a race and the proof says so**: if the loop claimed step 1
   before the revocation landed, the run may instead `fail` at step 1 with
   `upstream_refused`, or succeed step 1 and stop at step 2. The proof
   accepts `stopped` at ANY boundary provided NO audit row for the run's
   agent has `started_at` later than the revocation's `updated_at`, and
   prints which boundary it stopped at. The offline proof `test_a_refused_
   mint_stops_the_run_and_makes_no_call` is where the boundary is pinned
   exactly; the live one proves the deployment does what the offline one
   says; the control run for `second_notes_agent` succeeding; and
   `doctor capacity`'s ceilings line read through `bin/doctor.sh capacity
   --host <APG_HOST_MANIFEST> --json` as root: 2240 per key, 4480 total.
   **`tests/recovery/test_session32_workflow_restore.py`** (`REC-WF-001`):
   with `require_root`, run `bin/restore-test.sh --target-time <now>`
   against project_b (the `test_future_pitr.py` shape) and assert the
   evidence's `workflow_runs.count` ≥ the number of runs `psql` counts on
   the live cluster at the target time and `definitions == 2`.
4. **`pytest --setup-plan`** for both new live modules with `APG_LIVE_
   HOST=1 APG_PROJECT_A_OUTPUTS=<the op-owned copy> APG_PROJECT_B_
   OUTPUTS=<…> APG_HOST_MANIFEST=… APG_REHEARSAL_EVIDENCE_DIR=…` set
   (D671, D676), output kept in the scratchpad.
5. **`bin/session-32-check.sh`** derived from 31's by `sed` with every
   substitution count-asserted (`grep -c` before and after: `SESSION=31` →
   `32`, `session-31` → `session-32`, `thirty_one` → `thirty_two`, the
   evidence prefix, the ADR range in the header, the offline claim
   sentence's count *eight* and *thirty-two*), the header and usage
   rewritten whole and read line by line (D1488); `run_suite "p0 and not
   future and not live_host and not external"` kept verbatim (D1242); the
   offline mode's `apg dev` round trip gains nothing (the install is inside
   `up`); **no flag added or removed** — `diff <(grep -o -- '--[a-z-]*'
   bin/session-31-check.sh | sort -u) <(… 32 …)` is EMPTY and pasted in the
   Done; `SHELL_COMMANDS` gains it; `chmod 755`; `git add`; `tests/contract/
   test_session_thirty_two_gate_modes.py` from thirty-one's with D1627's
   `test_the_previous_gate_is_the_one_before_this_one_with_no_gap` kept and
   its literal `31` → `32`.
6. **`upgrade plan` offline** (D1624's recipe): the installed side from a
   worktree at `4344a1f`, the candidate a `tar`-piped copy of the working
   tree at `/tmp/apg-candidate` with `.generated/` excluded, both rendered
   as `project.example.yaml`; `bin/upgrade.sh plan … --json` with the
   declaration flag(s) for `migration_added` and `api_operation_added` →
   expect `bump minor`, `requires minor`, verdict `ok`, leaves
   `template_version` and `migrations.count` (33 → 34) — **list every leaf
   in the Done**.
7. **The gates**: `bin/session-01-check.sh` once on the clean tree (commit,
   gate, repair, commit, gate again; every first-run failure a row);
   `bin/session-32-check.sh --mode offline` → `evidence/session-32-offline.
   json` with the eight new offline claims plus the 24 inherited, every one
   `passed` (the count read from the file). Push; CI by full SHA.

**Done.** *(the collect-only listing; the tuple counts; every leaf of the
upgrade reading; the flag diff (empty); the two gates' first-run defects
as rows; the `--setup-plan` outputs' node counts; CI)*

### Run 8 — the trip: both projects redeploy with 0034, the worker's first run, one sweep, the tag

**Before the day** (agent, offline): read Session 31's Run 7 and Sheets
A1–A6 (`session-31-implementation-plan.md:1796-1968, 2143-2258`) and
`docs/operator-guide.md` §12 (D977); the host scripts staged under
`/home/op` derived from `s31-r7b-{checkout,gate,launch,cleanup}.sh` by
named substitution with every count asserted (D1482, D1630) and **diffed
against their parents: every `--flag` in, every `--flag` out** (D1133);
`s32-r8-readings.sh` from `s31-r8-readings.sh`; CI green on the bump commit
by full SHA; WSL's outbound TCP probed on the day (CLAUDE.md §1); the
external script in WSL derived from 31's WITH the `ssh-agent` block D1640
added; the two op-owned document copies' `source_commit` read before every
sheet that depends on them (D1510, D1631).

**The day, in order.** `op` steps are the agent's over SSH; **`sudo` steps
are the operator's**, on Sheets B1–B6 in the appendix, one sheet per
outcome, read before the next is issued (D1510):

1. *(op)* Transport: bundle, `scp`, `git bundle verify`, `git fetch`, **`git
   rev-parse FETCH_HEAD` equal to the pushed SHA**, `git checkout -B main
   FETCH_HEAD`, `cat VERSION` → `1.10.0`, porcelain 0; `uv pip sync` only if
   `requirements-dev.*`/`.python-version` moved since `4344a1f` (D1491);
   the four renders `--render-only` as `op` (each exits 0; **step 6d is not
   reached by a render**).
2. *(Sheet B1, sudo)* the reads: `upgrade.sh check` both; `doctor.sh` both
   (11 ok — the twelfth arrives with the deploy); `fleet.sh`; `backup.sh …
   info` alpha; **`bin/upgrade.sh plan` both with the declared classes** →
   `bump minor`, `OK`; the auth container's `memory.current` for beta
   (`cat /sys/fs/cgroup/system.slice/docker-<id>.scope/memory.current`,
   the id from `docker ps`) — the BEFORE figure; `dr-kit.sh export …
   /home/op/kit-<date>-pre`. **Every number written on the sheet.**
3. *(Sheet B2, sudo)* **the sentinel** (Session 30 Sheet A2 steps 1–5 with
   `s32-` and `/root/s32-redeploy-before.json`, the D1635 repair — the LAST
   line is the value, count before write), then alpha's deploy under
   `script(1)`, nothing after it. Expect exit 0; step 0 `admitted`; **step
   6 applies 0034 (ledger 34, `Pending: 0`)**; step 6d prints `no workflow
   definitions (the project declares none)`; `auth` recreated (image
   moved), the other containers as Compose decides; `doctor.sh --project
   alpha-dev` → **12 ok** (`workflow` reading zero runs and a heartbeat
   younger than 10 s — the loop's first heartbeat on production).
4. *(Sheet B3, sudo)* beta the same: ledger 34 + 2; step 6d prints
   `installed 2 workflow definitions`; `doctor` 12 ok.
5. *(Sheet B4, sudo)* **the session's own reads before the sweep**:
   `bin/doctor.sh capacity --host host.yaml` → ceilings **4480** by compose
   project, 2240 per key (D1636 closed on production); `bin/rehearse.sh
   worker-restart --outputs <beta>` → verdict `read`, the record's path,
   then `rehearse.sh reverse` (the policy restarted it; `docker start` if
   not); `doctor.sh --project beta-dev` → 12 ok with a NEW holder; beta's
   auth `memory.current` again — the AFTER-IDLE figure; `time` on each.
6. *(op, then Sheet B5)* op-owned copies installed (`install -o op -g op -m
   0600 /etc/agentic-postgres/projects/<key>/outputs.json /home/op/<key>-
   outputs.json`, both — the names D1631 measured); the agent confirms
   both name the new `source_commit`; **the one sweep**: `sudo bash
   /home/op/s32-r8-launch.sh`, ~15 min, holding `session-32-check.sh --mode
   host` with every declaration Session 31's sweep passed (`--host`,
   `--candidate-manifest`, `--rehearsal-evidence-dir`, `--redeploy-before-
   file`, `--admin-password-file`, the kit dir on `kit-2026-09-11`, D1282)
   and the `--rotated-*` three, `--dx-record-file`, `--after-reboot` NOT
   given. Expected: the five host claims `passed` — **their proofs' first
   execution anywhere** — including `workflow_run`, which makes the first
   agent tool call on beta and turns `doctor usage`'s exit 6 into 0 there
   (D1643); every inherited host claim unchanged. While the sweep runs, the
   agent reads beta's auth `memory.current` twice more as `op` — the UNDER-
   RUN figure. A failing proof: an instrument repaired in the window and
   re-run with `-k`; a product defect recorded and left.
7. *(op, then the workstation)* the host half to WSL; `--mode external`
   from WSL with the agent block; the merge into `evidence/session-32.
   json`. Expected: **158 claims**; `not_run` 5 (the rotation trio,
   `replacement_host_restore`, `port_allocation`); `failed` 1 (`documented_
   path`); exit 5 for those reasons and no other.
8. **The tag**: `bin/apg.sh release-reading --ref <the deployed SHA>`
   quoted; `git tag -a 1.10.0 <sha>`; `git push origin 1.10.0`; `git ls-
   tree` of both release pages. If the sweep's instruments came from a
   later commit, D1641's method: measure the deployable diff EMPTY and say
   so in the tag message.
9. *(Sheet B6, sudo)* the sentinel swept; `host.yaml.pre-s31` removed;
   the post kit exported; `doctor usage --project beta-dev` → exit 0 now;
   D rows for what the day found; this run **Done.** with the claim table,
   the two `upgrade plan` verdicts, the two ledgers (34; 34 + 2), the
   ceilings on production, the three `memory.current` figures (before,
   idle, under run) and the rehearsal's holder change.

**Done.** *(the executor writes it)*

### Run 9 — the close

**Not documentation only** (D1644): the envelope gains a `MACHINE`
`Measurement` for the loop's memory from Sheet B1/B4/B5's three figures
(`src/agentic_postgres/capacity.py`, then `bin/render-capacity-envelope.py
--write`), and ADR 0226 gains an *Amendment* section carrying the measured
numbers against the flip criteria — so this run commits, gates
(`bin/session-01-check.sh`), pushes and reads CI.

Then the records: this plan's header rewritten (COMPLETE, the dates, the
rows each run added, NEXT FREE); `docs/scope-closure.md` **§25** (what 32
closed — D1636, D1516, D1521's first half, 61, 62 — what it left, what 33
inherits: the substrate's API by name, `approval_required` still a refusal,
the `wait` step's park already built, D1248 for `inspect`, the second
principal's scope); `docs/plans/stage-4-plan.md`'s Status block (`CURRENT_
SESSION 32`, `1.10.0`, ADR count, next free `D`); CLAUDE.md in the launch
folder: §2's block (STAGE 4, RELEASE, EVIDENCE, CURRENT_SESSION, HOST, DR
KITS), §8's sentence *"There is no worker, queue, outbox, scheduler or
workflow"* rewritten to what exists now, §9's D1636 row removed and the
D1581 row's note updated per D1665; the memory file. Commit, push, done.

---

## 7. Evidence and claims

Unchanged rules (ADR 0163, 0202; D1237; D1543). **Thirteen claims land
with the constant** (D690): eight declared offline — each a property of a
checkout (a schema and compiler over a committed lock, a migration under a
real cluster the gate requires Docker for, a loop over fakes, routes over
`create_app("auth")` with fakes, a command's closed tables, an AST scan of
the deploy, three readers over canned inputs) — and five host, undeclared,
first executed on the trip. **Session 32 is the session the stage plan's
item 1 names**: a claim about a worker is a claim about at-least-once plus
an idempotent upstream, and `workflow_resume` is proved by a constructed
crash state and a signalled process, never by reading a status.

| Claim | Mode | Moves on |
|---|---|---|
| `capacity_ceilings`, `workflow_definition`, `workflow_substrate`, `workflow_worker`, `workflow_surface`, `workflow_command`, `workflow_install`, `workflow_reading` | offline | Run 7's gate |
| `ceilings_read`, `workflow_run`, `workflow_resume`, `workflow_revocation`, `workflow_restore` | host | Run 8's sweep — their proofs' **first execution anywhere** |
| `deployment_convergence` | host | Run 8, `--redeploy-before-file` declared |
| `telemetry_read`, `usage_read` | host | Run 8 — and `usage_read` on beta reads a positive `tool_calls_total` for the first time (D1643 closed by the run, not by a repair) |
| the rotation trio, `replacement_host_restore`, `port_allocation` | — | `not_run`, unchanged; `documented_path` `failed` by decision |

**No claim is added for the printers' wording** (Run 2): `NODE-READ-001`
made stricter moves no count. **No environment gate is added** (§2).

---

## 8. Security invariants this session touches

| Invariant | Where 32 puts it at risk | Control |
|---|---|---|
| **A worker holds nothing an agent identity does not hold** (stage plan §8, §24 item 4) | The loop mints an agent's token without its secret | `step_token` runs the same status and expiry checks as `agent_token` (rig 32f: identical refusals); the loop runs inside the process that could already mint for anyone; one token per step attempt, none outliving it (an AST proof and a counting proof) |
| PostgreSQL is the final authorization authority | The four tables | No grant to any role; nine definer functions with `search_path` pinned; `enqueue` checks the agent's STORED scopes; every step is a plane call under the hook |
| A step is a tool call under the same scope check | The loop calls the plane | The loop sends exactly what `mcp_rpc` sends; it holds no lock and no SQL; `RETRYABLE_TOKENS` is the plane's vocabulary |
| An unauditable write does not happen — the worker must not reorder | — | The loop never touches an audit function; the order is `bounded()`'s; the correlation is the plane's own `request_id` |
| A revoked token stops on its next request, locally | The per-step mint; the route | `step_token` refuses a non-active agent; `authenticate_agent` re-checks status and `authz_version` on every route call; the hook stops a mid-step call |
| The MCP runtime holds no credential | Unchanged: the loop lives in `auth`, not `mcp` | `FORBIDDEN_VARIABLES` unchanged and its guards run; `MCP_VARIABLES` unchanged |
| One service cannot read another's credential | No new consumer | `secrets.required.yaml` unchanged; `test_session2_secret_model.py` runs |
| An agent record carries no URL, key, token or caller value | The doctor's `workflow` check; the run's status document | `workflow_counts` returns integers and a holder string of hostname:pid:tick; `status` returns the agent's own input and results; `test_doctor_redaction` over the new check |
| A human cannot run SQL through a product surface | `bin/workflow.sh`; the doctor's probe; step 6d | The command holds no SQL (a proof); the probe's statement is a constant; step 6d passes the body as a psql variable to a function granted to nobody |
| Projects share no project-scoped value | Definitions | Rows in each project's own database; alpha refuses by name (a live proof) |
| Admission refuses; a capacity reading reports | `ceilings_from_inspect` | The reading changes what it reports, `decide` is untouched (a grep proof that `decide` reads no ceiling) |
| A report may not substitute an answer for a failure to determine one (ADR 0195) | `workflow` check, `workflow_runs` drill member, `status` | `UNKNOWN` naming the function; `null` with a reason; a 404 with one message |
| There is no public Postgres endpoint (ADR 0216) | Nothing here touches a port or a network | The three routes hang off `routes.app`'s existing router |
| `--render-only` keeps working with no host and no root | Step 6d | Not reached by a render; the gate's step 2 renders four fixtures |
| The deploy, the sweep and the tag land on one commit | Run 8 | D1425's order on the sheets; D1641's method if an instrument moves |
| Never grant `op` the docker group | The heartbeat read on the host | `memory.current` is world-readable (D765); the doctor is root; `op` runs `--render-only` only |

---

## 9. Stop conditions

- Rig 32a: the loop's idle RSS delta exceeds 32 MiB, its under-run delta
  exceeds 96 MiB, or the image runs more than one uvicorn process: stop;
  D1645 is reopened as a row; the container arm is priced before Run 5.
- Rig 32b: a sibling container cannot reach `/mcp` over the user network
  with a bearer, or `stateless_http` demands a session: stop; the loop's
  transport is redesigned as a row before Run 5.
- Rig 32c: a replay with the same key and arguments is REFUSED rather than
  re-read: stop; D1646 and ADR 0227 are rewritten before Run 3.
- Rig 32d: a definer function granted to `auth_service` cannot read a
  no-grant `app_private` table: stop; the pattern is wrong and 0034 is not
  written.
- The agents table's PK is not a uuid named `id`, or `auth_create_agent`'s
  signature moved: read the migration, a row, then continue.
- `test_database_function_signatures.py` pins a closed set of `app_private`
  functions and the nine cannot join it without an ADR: stop and ask.
- Run 5's first end-to-end run (rig 32a's second arm) fails for a reason in
  the PLANE rather than the loop: stop; the plane is presumed right; a row.
- `authenticate_agent` cannot be added without changing `authenticate`'s
  behaviour for any existing route: stop; ADR 0229's amendment of 0114 is
  reconsidered.
- Run 7's `upgrade plan` prices `1.10.0` at **major** with the declared
  classes: stop; a row; the operator's decision.
- A passing test would be weakened — including any `FORBIDDEN_VARIABLES`
  guard, `test_the_audit_functions_take_no_identity_argument`, the eleven-
  check proof (renamed, not deleted), or `BUDGET_CLAIMANTS`'s AST guard.
- A workflow step would invoke anything but a lock capability, or the
  worker would need a credential beyond the auth service's role and a
  per-step token, or would cache a token across steps (stage plan §9).
- A port, a route, a published store or a non-loopback bind for any reason
  (ADR 0216).
- Admission would refuse alpha's or beta's OWN redeploy on the trip: stop
  before the deploy; the arithmetic or the declaration is wrong.
- Migration 0034 fails on alpha at step 6: stop; **never amend it** (D912);
  the ledger is read; a fix-forward 0035 is a new run and a new deploy.
- The sweep's `workflow_run` reads `not_run`: `skipped_node_ids` first; a
  missing gate variable is the gate's defect; never re-run the deploy.
- `worker-restart`'s reversal does not restart `auth` within its bound:
  `docker start` (ADR 0193's fallback), a row, and the sweep waits for
  `doctor` 12 ok before it is launched.
- CI red on a code commit: stop and read; a cancelled run is not a failed
  one (D1059).
- WSL has lost outbound TCP on trip day: CLAUDE.md §1; a Windows reboot
  early.

---

## 10. Open items this session carries and creates

**Carried in, untouched, each still true:** D1045; `replacement_host_
restore` (D1028); D1375; the 21 unclaimed requirements; D976, D688, D771,
D340, D466, D540, D942, D1203, D1205, D1211; the Infisical control-plane
identity's org admin; `process-max` 1 (D593); `documented_path` failed
until a person walks it (35); the three rotations 30 did not perform; the
retired JWKs on the host unread by any sweep; the mirror's upstream flake
(D1546); `apg-diag`'s standing account (D1528) and its allowlist (D380);
ADR 0162's missing row for an option (D1561); D1642 (a kit naming the
checkout's commit — still a session in `dr-kit.py`'s); D1547 (`delete_note`
— **this session moves the `app` OpenAPI contract, not the `api` one, so
the RPC is still nobody's**); D1581 (not observable on this trip either,
D1665); the edge plane's missing `pids_limit`/`cpus` (35); the three
unbounded services (pgbouncer, postgrest, docs); `render-jwks` and
`verification_kids`; `materialize-secrets`'s *deliberately absent*;
`storage_objects`; the noisy-neighbour measurement (35); the envelope's
image pins.

**Created or left here:**

| Item | Note |
|---|---|
| **`approval_required` is still a terminal refusal, and a definition naming such a capability is refused at `validate`** | Session 33 turns the refusal into a parked step (`workflow_park` with no `resume_after`, resumed by `apg workflow approve` under a new scope the second principal holds). The park mechanism exists; the second principal does not. |
| **A `wait` step is a park with no `resume_after`** | Built as a mechanism, not as a step kind; Session 33 adds the kind and Session 34 the event that resumes it. |
| **`apg workflow inspect` needs D1248's audit filters** | `status` reads the substrate; provenance from `agent_audit` by request id is a join the reader does not yet make. Session 33. |
| **A definition's `lock_tools_sha256` is recorded and never compared at run time** | The plane enforces the lock on every call; `status` reports the digest so a reader can see the lock moved since `validate`. Whether a moved lock should refuse a RUN is Session 33's, beside compensation. |
| **The revocation proof is a race stated in its docstring** | Run 7 item 3: the boundary the run stops at depends on the poll; the offline proof pins it. A deterministic live form needs the loop to be pausable, which is a hook this session refuses. |
| **The loop's memory is charged inside the auth container's cap, measured three times on one trip** | Recorded in the envelope as a `MACHINE` measurement. A worker under sustained load has not been measured; the container's `mem_limit` is the only bound. |
| **Definitions are installed only by a deploy or `apg dev up`** | A developer who edits a definition must redeploy (a new version) — the migration-set discipline applied to definitions. `apg workflow install` as a separate verb is not built; if Session 33 needs one for approval-gated definitions, it is priced then. |
| **The worker is sequential: one step at a time per project** | The concurrency knob D1520 names is not built; `notes-retry`'s 45 s park blocks nothing because the loop claims other runs' steps while a step is parked. A definition-level `concurrency` field is Session 34's if event-triggered runs need it. |
| **`worker-restart` reads a holder change, not a resumed step** | The resumed-step half is the live proof's (a run parked under the kill). A rehearsal that enqueues its own run would need an agent token, which an operator command may not hold. |

---

## Appendix — what to consult, how a run is executed here, the rigs, and the sheets

**Consult, in this order:** this plan's §1 and §5. The stage plan's §5
*Session 32*, §8, §9, §11. `docs/plans/session-31-implementation-plan.md`
§5 Runs 6–7 and Sheets A1–A6 (the trip's shape, the sentinel recipe with
D1635's repair, the detached sweep, the `ssh-agent` block), §10 (what 31
created for 32). ADR 0195 before any reader; **0135** (the definer-function
grant shape); **0181/0182** (the key claimed in the write's transaction, a
dry-run rolled back); **0193** (a signal to the process, never `docker
kill`); **0201** (the joined lock); **0203** (`apg dev` is the database
alone); **0213** (a reading with no threshold); **0218** (`container_
exec`); **0093** (a `bin/` command imports only `agentic_postgres` and
`yaml`); **0114** (one token use per API — amended by 0229); **0121** (one
image, several modes); **0162** (what a bump permits).

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
failed; `--setup-plan` with the variables SET before a trip. **A `sudo`
line on any sheet has nothing after it**, and every sheet is grepped for
`|`, `>`, `$(` and `&` on every `sudo` product line before it is handed
over (D1505). **Any Python that imports `agentic_postgres` outside pytest
needs `PYTHONPATH=src`.** **Every `service_source.load(...)` proof reads the
service's module from `services/auth-api/app/`, not `src/`** — the plane
and the loop live there.

**The rigs, summarised** (Run 1; each a script, each with a control, each
naming its image by digest):

| Rig | Subject | Control | Owes |
|---|---|---|---|
| 32a | the auth image's RSS with and without the loop | the `mcp` mode's known overhead | the idle delta; the flip criteria |
| 32b | a sibling container's JSON-RPC to `mcp:8080/mcp` with a bearer | no bearer; an access token | the loop's headers, body and SSE parse |
| 32c | replay semantics of `agent_idempotency_claim` under `psql` | a fresh key | the `replayed`/`PT412` words as the loop sees them |
| 32d | a definer function over a no-grant `app_private` table as `auth_service` | the same table under FORCE RLS: zero rows | D1647's *measured* |
| 32e | `SKIP LOCKED` under a lease predicate across two sessions | no predicate | 0034's claim and finish statements |
| 32f | `step_token`'s claims and refusals against `agent_token`'s | an unknown id | D1649's split |

### Sheet B1 — the reads (all `sudo`; write each reading down)

`bin/upgrade.sh check --project alpha-dev` and `beta-dev` → installed
versions, `verdict OK`. `bin/doctor.sh --project alpha-dev` and `beta-dev`
→ **11 ok** (the twelfth check arrives with the deploy). `bin/fleet.sh` →
2 projects. `bin/backup.sh --outputs /etc/agentic-postgres/projects/alpha-
dev/outputs.json info` → a full exists. `bin/upgrade.sh plan --project
alpha-dev --candidate /home/op/agentic-postgres/.generated/alpha-dev/
outputs.json --json` **with the declaration flags Run 7 measured (the agent
prints the exact line on the sheet)** → `bump minor`, `OK`; the same for
`beta-dev`. `docker ps --format '{{.ID}} {{.Names}}' --filter label=com.
docker.compose.service=auth` → beta's auth container id; `cat /sys/fs/
cgroup/system.slice/docker-<id>.scope/memory.current` → the BEFORE figure
in bytes. `bin/dr-kit.sh export … --output /home/op/kit-<date>-pre` (the
exact line from `--help`, printed on the sheet by the agent).

### Sheet B2 — the sentinel, then alpha (`sudo`)

1. The sentinel, Session 30 Sheet A2 steps 1–5 as repaired in `/home/op/
   s31-r7-sentinel.sh` (D1635: the LAST line is the value; count before
   write), with `s32-redeploy-sentinel-<YYYY-MM-DD>` and `/root/s32-
   redeploy-before.json`; step 5's read-back must print both fields.
2. **The deploy**, at the terminal, nothing after this line:

       script -q -e -c "sudo ./deploy.sh --host host.yaml --project project.alpha.yaml --capabilities capabilities.yaml --through-session 32" /home/op/s32-deploy-alpha.txt

   → exit 0. Step 0 `admitted` (six lines, unchanged from Session 31's
   numbers — write them down). **Step 6 applies one migration**: the
   migrator's line says `Applied`, and the ledger is what is read (D941).
   Step 6d prints `no workflow definitions (the project declares none)`.
   If step 6 fails: **STOP** (§9); read the ledger; never amend 0034.

Then the reads: `sudo bin/migrate.sh --project project.alpha.yaml --runtime
status` at the terminal, nothing after it → **34** `[X]`, `Pending: 0`;
`sudo docker ps --format '{{.Names}} {{.Status}}' --filter label=com.
docker.compose.project=<alpha's compose project name, from the document>`
→ `auth` younger than the deploy; `sudo bin/doctor.sh --project alpha-dev`
→ **12 ok**, the `workflow` line reading `0 runs … heartbeat <10 s
(<holder>)` — write the holder down.

### Sheet B3 — beta (`sudo`)

The same with `project.beta.yaml`; step 6d prints `installed 2 workflow
definitions`; ledger **34 + 2**, `Pending: 0` twice; `doctor` 12 ok; the
holder written down.

### Sheet B4 — the session's proofs (`sudo`; each line's output written down)

1. `time sudo bin/doctor.sh capacity --host host.yaml` → `ceilings` **4480
   MiB across 2 project(s), by compose project**, `alpha-dev 2240`,
   `beta-dev 2240`, the three unbounded names (D1636 closed on production).
2. `sudo bin/rehearse.sh worker-restart --outputs /etc/agentic-postgres/
   projects/beta-dev/outputs.json` → `verdict read`, the record's path
   printed, the holder before and after both printed; then `sudo
   bin/rehearse.sh reverse` → exit 0 (if `auth` is not running by then:
   `sudo docker start <beta auth container>` and a row).
3. `sudo bin/doctor.sh --project beta-dev` → 12 ok, a holder DIFFERENT from
   Sheet B3's.
4. `cat /sys/fs/cgroup/system.slice/docker-<new beta auth id>.scope/memory.
   current` → the AFTER-IDLE figure (the id moved with the restart —
   `docker ps` again first).
5. `time sudo bin/doctor.sh usage --project beta-dev` → **still exit 6**
   here (no tool call yet; D1643) — expected, written down, and re-read
   on Sheet B6.

### Sheet B5 — the sweep (`sudo`)

`sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/alpha-dev/
outputs.json /home/op/alpha-dev-outputs.json` and beta (D1631's names);
the agent confirms both name the new `source_commit` **before** this line:
`sudo bash /home/op/s32-r8-launch.sh` — which detaches the sweep itself
and returns at once; ~15 min; `cat /home/op/s32-r8-host.code` → 0 or 5,
and `/home/op/s32-r8-host-summary.txt` is the reading. **While it runs**,
the agent (as `op`, no sudo) reads beta's auth `memory.current` twice, a
minute apart, for the UNDER-RUN figure.

### Sheet B6 — the cleanup (`sudo`)

The sentinel removed, exactly Session 30 Sheet A4's two lines with the
`s32-` title (expect `DELETE 1`). `rm /home/op/host.yaml.pre-s31` (31's
§10: kept until 32's trip). `sudo bin/doctor.sh usage --project beta-dev`
→ **exit 0 now**, `tool_calls_total` positive — the sweep made beta's first
agent tool call. `bin/dr-kit.sh export … --output /home/op/kit-<date>-
post`. The rehearsal record and the two deploy transcripts fetched to the
workstation by the agent (`scp` as `op` of `/home/op/s32-deploy-*.txt` and
the `evidence/rehearsal-beta-dev-worker-restart-*.json` the sweep's
`--rehearsal-evidence-dir` named).
