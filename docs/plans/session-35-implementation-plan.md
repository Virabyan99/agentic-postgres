# Session 35 — Change governance, the database half of approval, hardening, and the Stage 4 release

**Status: EXECUTING — Run 1 DONE 2026-10-01** (planned 2026-09-30 at
`a018939`). The last session of Stage 4 (`docs/plans/stage-4-plan.md` §3).
Eleven runs. The plan spends **D1857–D1891** and **ADR 0242–0245**; rows the
runs add start at **D1892**. **NEXT FREE: D1901, ADR 0246.**

**Brief:** `docs/plans/stage-4-plan.md` §5 *Session 35* whole (Builds / Already
true / Must not / Measures / Closes, `:619-657`), its rows **D1523** (the
proposal record, the destructive lint, `approvals_required`, *"the lock-risk
estimate — the one reading nobody has — is not built on a guess"*), **D1524**
(*"Session 35 measures a deploy's downtime per service class (REST, auth,
storage, mcp, the database) into the envelope"*), **D1530** (the rejected
technologies wait on *"Session 35's noisy-neighbour measurement"*), **D1531**
(*"Stage 4's closing measurement is the third reader … arranged in Session 35,
never closed by the author"*), §2.2 (the version is read from `upgrade plan`,
never chosen), §2.4 (`documented_path` arranged, never closed by a session),
§6 (*"Session 35's decision report prices these against measured numbers for
the first time"*), §7's row for 35 (new `GOV-*` claims; `documented_path`;
every Stage 4 claim in every mode), §8 whole (the last row: *a report may not
substitute an answer* — the proposal record), §9 whole, §10's *"Session 35
budgets a second reader if the first records more than the walk before it
did"*, and §11. Plus `docs/scope-closure.md` §27 *What Session 35 inherits, in
order* (`:1195-1210`: **D1721's database half, assigned by the operator on
2026-09-29**; the noisy-neighbour measurement now with a second workload and
D1711's sub-second sampler; the third reader walking a path that now includes
connectors; hardening — the edge's unbounded `traefik` and
`docker-socket-proxy`, `apg-diag`'s allowlist D380; the retention story; ADR
0241's rule for any new reader of an existing deployed document), §27's *What it
left* rows, `docs/plans/session-33-implementation-plan.md:2469` (§10's pricing
of the database half) and ADR 0231 `:59-110`, and
`docs/plans/session-34-implementation-plan.md` §10 and its Run 10 sheets D1–D9
with what went wrong on them (D1848, D1852–D1854).

**Shape:** eleven runs. **Run 1** is documentation — five rigs, one host
reading sheet (E0, reads only), the `THR-*` rows, four ADRs — and **reads no CI
verdict**. **Runs 2–5** change code: each pushes and reads that commit's own CI
verdict by full SHA (`gh api "repos/Virabyan99/agentic-postgres/actions/runs?
head_sha=<40 chars>" --jq '.workflow_runs[] | [.name, .status, .conclusion] |
@tsv'`, judged on HTTP status, three buckets — success / failure / not
registered; an empty list is not a verdict, D1057). **Run 6** is documentation
plus the documentation tests (code-adjacent: it moves `dx_record.DOCUMENT_ROOTS`
and `CURRENT_PATH_DOCUMENTS`, so it reads CI). **Run 7** rehearses the trip's
measuring instruments offline and commits nothing but its `**Done.**` (no CI).
**Run 8** is the operator's approval of the example set's proposal and the
arrangement of the third reader (two sheets, no code). **Run 9** is the bump.
**Run 10** is the trip. **Run 11** is the close: the envelope rows (`src/` — so
it gates and reads CI), the Stage 5 decision report, the ledger.

**Product version at close:** `CURRENT_SESSION` **35**; `template_version`
**`1.13.0`** — predicted *minor by declaration*, read from `upgrade plan` in
Run 9 and never chosen (§1 D1889): **migration 0037** (`approval_gate`: one
function, `app.require_approval(p_tool text)`, SECURITY DEFINER, granted to
nobody — no table, no column, no `api` object, so no `NOTIFY pgrst`), **one new
project migration in the example set** (`0004-approval-in-the-database.sql`:
`api.set_note_embedding` replaced with its signature and grants unchanged and
ONE new first statement, `PERFORM app.require_approval('set_note_embedding');`),
**a new check** joining a project's compiled capability contract to its
migration set (a gated RPC tool whose function does not call the guard first is
refused by `bin/mcp-contract.sh check --project` and by `propose`, and REPORTED
by the render), **a destructive-change reading** (`migrations.
destructive_findings`, named, never refused), **the proposal record**
(`bin/migrate.sh propose` and `approve`, two committed JSON files per proposal
under `projects/<slug>/proposals/`), **the host gate** (`bin/migrate.py`'s
`up` refuses a project set with a pending version whose proposal is absent,
stale or — under `approvals_required: 1` — unapproved), **project manifest
schema 8** (`migrations.approvals_required: 0|1`, default 0, forbidden below 8),
**the edge bounded** (`mem_limit`, `pids_limit`, `cpus` on `traefik` and
`docker-socket-proxy`, values from Sheet E0's readings by ADR 0222's method),
**`mem_limit` on pgbouncer, postgrest and docs** (the three long-running
project services without one), **`apg-diag` reading `auth`, `storage` and
`mcp`** with a JSON-aware redaction, **D1856** (a kit's `projects/` directory
0700), a new page `docs/change-governance.md`, **operator guide §19**, two new
steps on the documented path, the Session 35 gate, and **`docs/stage-5-decision-
report.md`**. **Outputs stay at schema 19** (no deployed-document member moves,
so ADR 0241's two-version bound is not stressed), **no new container, role,
network, route, router, secret, scope or port**. ADR 0162: a released migration
is *minor*; `upgrade plan` reads it only when declared (D1703), so Run 9
declares `--also migration_added` and the release paragraph says the floor is
minor **by declaration**. A `major` is §9's stop.

**Written for whoever picks this up cold, and it will be a different model
than the one that planned it.** Every path below was read from the tree on
2026-09-30 at `a018939` — four explore passes over `migrations/`,
`services/auth-api/`, `src/`, `bin/`, `schemas/`, `infra/`, `tests/` and
`docs/`, plus direct reads of the Stage 4 plan, scope-closure §26–§27, Session
34's plan whole, ADR 0207 and ADR 0231 — and a read of the HOST as `op` the
same evening (checkout `8d655b5`, clean; both op-owned document copies outputs
v19 at `14b1b9d`, beta `connectors.enabled: true`; `project.beta.yaml`
`schema_version: 7`, `project.alpha.yaml` 4; `free -m` 3,814 total / 2,093
available; `/` 38 G, 15 G used). Every path is cited by `path:line`. Every
third-party or product claim is measured in Run 1's rigs with a control, or is
marked as the measurement a run owes — never assumed. **Read CLAUDE.md §1 in
the launch folder before the first command, then this plan's §1, then the
appendix.** If a step here and the tree disagree, **the tree wins and the
disagreement is a divergence row** (next free `D` after §1's table), never a
silent reconciliation. **When this plan names a line number, open the file at
that line and read the surrounding twenty lines before editing** — the numbers
were right on 2026-09-30 and `ruff format` moves them.

**The six sentences the executor most needs, in case nothing else is read:**

1. **Approval is enforced in the database by a function in `app` granted to
   NOBODY, which a gated project RPC calls first** (§1 D1867, ADR 0242).
   `app.require_approval(p_tool text) RETURNS void` passes a HUMAN caller (no
   `app.agent_id` GUC — the principal approvals are made BY), and passes an
   AGENT caller only when `request.jwt.claims` carries `apg_approval` naming
   `p_tool`, the request's `Idempotency-Key` header equals the claim's key, and
   `app_private.workflow_approval` holds that id `approved` on a `running` run
   of that agent. Everything else is `AP403: approval_required` (`PT403` → HTTP
   403) and nothing is written. The plane already forwards the agent's own JWT
   verbatim (`mcp_upstream.py:1`, `:378-391`), so the approved path needs no
   plane change — **rig 35a measures the claim arriving in SQL before a line is
   written**.
2. **A proposal is keyed by the number the render already records**
   (§1 D1857): `sha256` of the set's `released.lock.json` bytes — the
   rendered document's `migrations.project_set.lock_sha256`
   (`rendering.py:2486-2495`). One function computes it for both readers. The
   proposal and its approval are COMMITTED files under
   `projects/<slug>/proposals/`; nothing is ever written into a host checkout
   (D971, D1852).
3. **The host gate refuses only an ACT, never a state** (§1 D1865): `migrate.py
   up` refuses when the project set has a version the project ledger lacks and
   the committed proposal is absent, names another digest, or — under
   `approvals_required: 1` — has no valid approval. A fully applied set (beta
   today, `36 + 3`) needs no proposal, so the upgrade breaks nobody.
4. **Names in a proposal are DECLARED and the records say so** (§1 D1864, ADR
   0243). There is no operator identity in this product (`bin/database-
   access.py:25-28`: *"an identity supplied on a command line is not an
   identity"*), and the host has one operator account. The record guards
   against an unreviewed or altered set reaching a host; it does not
   authenticate a reviewer, and no page may say it does.
5. **Every measurement this session writes into the envelope is taken by a
   trip script with its conditions recorded, below the edge's per-source rate
   limit** (§1 D1873–D1876). `apg-rate-limit` is 20/s average, burst 40, per
   source (`infra/edge/dynamic/baseline.yaml:42-46`): a probe through the edge
   stays at ≤ 8 req/s; a LOAD runs inside the project's own `internal` network,
   where no edge sits. Downtime is what a probe sees (a transport error or an
   edge 404/502/503/504), never a process's start time. **A figure labelled
   *under a run* must have been sampled inside one** (D1711, D1776).
6. **Recreating the edge takes both projects' ingress down at once, and that is
   now a measured act** (§1 D1877, ADR 0244). `test_the_edge_plane_is_untouched`
   (`tests/contract/test_process_limits.py:175-185`) is REPLACED by a stricter
   proof under ADR 0244; the recreation is its own sheet (F4) with the probe
   running on both projects.

---

## 0. Where the session starts

```
HEAD            a018939 on main, local = origin, clean (read 2026-09-30 in
                WSL). Deployed: 14b1b9d (1.12.0) on both projects; the tag
                1.12.0 names 14b1b9d. `git diff --name-only 1.12.0..HEAD`
                filtered to src/ bin/ services/ migrations/ templates/
                schemas/ compose.yaml deploy.sh VERSION names NOTHING
                (measured 2026-09-30; the nine files past the tag are plans,
                scope-closure and tests). The host CHECKOUT is 8d655b5 (tests
                past the deployment), clean.
VERSION         1.12.0 (the repo-root file; template_version() at
                src/agentic_postgres/__init__.py:772-778). CURRENT_SESSION 34
                (:764; Session 34's paragraph :691-763). Outputs schema 19
                (deployed_output.py:40). host.yaml schema 3. Project manifest
                1-7 (schemas/project.schema.json:16-27; config.py:64
                SUPPORTED_PROJECT_SCHEMA_VERSIONS). Capability manifest 4,
                lock 4, project lock 3 (migrations.py:104), api-surface 2.
                36 released migrations (0036 = 20260929120036 connectivity,
                migrations/manifest.json, the last entry). The example set: 3
                (20260914120001, …002, 20260930120003), lock follows
                20260912120031 DECLARED (ADR 0240).
REGISTRY        281 requirements (tests/acceptance-registry.yaml, 5,755 lines;
                Session 34's block :5437-5755, no banner comment). 188 claims
                (evidence_claims.py CLAIMS :335-1109, Session 34 :583-606), 53
                declared offline (OFFLINE_CLAIMS :106-288, Session 34
                :259-286). CLAIM_INTRODUCED_IN tests/contract/
                test_evidence_claims.py:953, Session 34 rows :1157-1175. ID
                regex tests/contract/test_acceptance_registry.py:101 (families
                … NODE WF EVT CONN), the family paragraphs :50-100. 241 ADRs
                (index docs/decisions/README.md, last row :307). NEXT FREE:
                D1857, ADR 0242.
EVIDENCE        evidence/session-34.json: 188 claims, 182 passed, 5 not_run,
                1 failed (documented_path). not_run: the rotation trio
                (api_authorization, bootstrap_identity,
                credential_rotation_planes), port_allocation,
                replacement_host_restore. Host 1075/1/7 (the third sweep),
                external 25/0/8, offline 53/53.
HOST            62.238.99.122, ~op/agentic-postgres at 8d655b5. Both projects
                1.12.0 at 14b1b9d, deployed_through_session 34, doctor 12 ok,
                ledgers 36 / 36+3. host.yaml schema 3: 3814 MiB / 2214 reserve
                / 37 GiB / 8 GiB reserve; 2 vCPU (docs/capacity-envelope.md:
                297 -- re-read on Sheet E0). doctor capacity: 4,480 MiB of
                ceilings, 10 unbounded (D1710: 2 projects x pgbouncer,
                postgrest, docs + the edge's two). Beta: project manifest 7,
                the connectors facility ON, four connectors installed and ALL
                DISABLED; 68 revoked probe agents, 27 probe humans, 6 pending
                approvals on ended runs, 4 dead deliveries. Alpha: manifest 4,
                no set, no facility. OP-OWNED copies /home/op/<key>-dev-
                outputs.json (v19, 14b1b9d). Script set s34-r10-* (and r10b,
                r10c, r10k, r10ck) in /home/op and WSL ~/s34r10/ with the
                deriver ~/s34r10/s34r10-derive.py. Kits through
                kit-2026-09-30-post (host + WSL ~/dr-kits). The gate's
                --kit-dir stays on kit-2026-09-11 (D1282). `op` cannot reach
                the Docker socket (D1375).
```

**What exists, measured at `a018939`, and the session builds on:**

- **The approval path, end to end.** The worker mints a step token with
  `apg_approval {id, tool, key}` only from a decided row (`service.py:542-597`;
  the claim's shape `claims.py:94`, `:176-200`; the row read by
  `repository.py:269-286` through `app_private.workflow_approval_for_token`,
  `0035-workflow-gates.sql:1088-1107`: `a.status = 'approved' AND r.agent_id =
  p_agent AND r.status = 'running'`, expiry not re-checked once decided,
  D1745). The step's key rides in the tool arguments
  (`workflow_worker.py:434`). The plane reads the claim
  (`mcp_authorization.py:138-164`) and checks it
  (`mcp_tools.py:600-615`: an approved call is not rehearsed; the claim's
  `(tool, key)` must equal the call's), then calls `execute_write`
  (`mcp_tools.py:639-647`) **with the SAME token**: the plane *"holds no signing
  key, so it cannot mint a token"* (`mcp_upstream.py:1`, `:9`). `_dial`
  (`mcp_upstream.py:378-391`) sends `Authorization`, `Accept`, `X-Request-Id`,
  and for a write `Idempotency-Key` and `Dry-Run` (`mcp_query.py:78-127`), and
  no `Prefer`. **Unmeasured**: the claim arriving inside
  `current_setting('request.jwt.claims')` in SQL (rig 33a proved it passes the
  verifiers and the pre-request hook; nobody read it in SQL) — rig 35a.
- **What the database already reads from a request.** The pre-request hook
  (`0018-agent-read-plane.sql:107-271`, never redefined later) reads
  `request.jwt.claims` (`:117`, `:177`) for `sub`, `role`, `token_use`,
  `credential_version`, `authz_version`, `scope` only; sets `app.agent_id` and
  `app.user_id` = the agent's OWNER for an agent (`:249-250`), `app.user_id`
  for a human (`:270`). `request.headers` is read by
  `app_private.agent_request_id()` (`0022:98`), **`app_private.
  agent_idempotency_key()`** (`0029:139-169`: `(raw::jsonb) ->>
  'idempotency-key'`, a malformed key `AP412`/`PT412`, not SECURITY DEFINER,
  REVOKEd from PUBLIC) and `app_private.agent_dry_run()` (`0030:75-101`).
- **`app_private.workflow_approval`** (`0035:98-113`): `id`, `run_id` →
  `workflow_run`, `step_id` UNIQUE, `tool`, `capability`, `idempotency_key`
  (`^[\x21-\x7e]{8,255}$`), `expires_at`, `status` (`pending|approved|
  rejected|expired`, `:59-60`), `decided_by` → `users`, `decided_at`. **No agent
  column** — the agent is `workflow_run.agent_id`. No role holds a privilege on
  the table (`:118-123`).
- **The gated function.** `api.set_note_embedding(p_note_id uuid, p_embedding
  extensions.vector)` — `projects/example/migrations/templates/0001-note-
  embeddings.sql:75-107` (plpgsql, SECURITY DEFINER, `SET search_path =
  pg_catalog, pg_temp`; `caller := app.current_user_id()`, PT401, PT404 unless
  the caller owns the note, an upsert), replaced byte for byte plus one emit by
  `0003-note-embedding-events.sql:31-64` (the emit `:61`; no re-grant,
  `:12-19`). Grants: `0001:113` REVOKE, `:116-117` `authenticated`, `:126-127`
  `api_documentation`, `0002-agent-grants.sql:27-28` `agent_writer`. **No
  approval, idempotency or dry-run check** (rig 33b: a direct agent call with
  `Idempotency-Key` + `Dry-Run: true` answered 200 and WROTE, ADR 0231
  `:63-81`). Its capability `projects/example/capabilities.yaml:46-68`:
  `requires_approval: true`, `supports_dry_run: true`, `operation_id:
  rpc.set_note_embedding.post` → `/rpc/set_note_embedding`. **The only other
  approval** is a deployment PROFILE on a RELEASE tool:
  `project.second.example.yaml:83-84` (`update_task_status`), whose function
  (`0030-agent-dry-run.sql:237+`) checks none (§1 D1869).
- **Callers of the gated function in the tests** (each must stay green):
  `tests/deployment/test_session34_connectivity.py:543-557` (`_embed` — the
  OWNER, a human token, direct, asserts 200); `tests/deployment/
  test_session33_gates.py:494-500`, `:552-603` (the approved run through the
  plane: audit `refused` then `served`, one embedding);
  `tests/deployment/test_session21_agent.py:80`, `:380-480` (a writer refused
  by the plane, zero rows); `tests/deployment/test_session22_plane.py:371-377`
  (`psql` as the owner with only `app.user_id` set — the human branch). Pins:
  `test_project_migration_sets.py:1313-1360` (0003 = 0001 + the emit) and
  `:859` (`functions == {"set_note_embedding"}`);
  `test_dev_environment_cluster.py:271-306` (grants; `prosrc` has the emit;
  **the ledger `endswith("20260930120003")`** — moves with 0004);
  `test_migrations_apply_as_the_migration_user.py:425-433`.
- **The project lint** `migrations.lint_project_set` (`src/agentic_postgres/
  migrations.py:795-938`): placeholders `PROJECT_PLACEHOLDER_SOURCES`
  (`:88-98`); `FORBIDDEN_STATEMENTS` (`:142-159`, `\bapp_private\b` first — **a
  project body may not name `app_private`, so the guard must be in `app`**);
  the role preamble (`:864-871`); a release view dropped (`:873-880`); **a
  release function in `api`/`app` created, altered or dropped** (`FUNCTION_DDL`
  `:173-191`, `RELEASE_FUNCTION_SCHEMAS` `:196`, `release_functions()`
  `:765-792` derived from the templates — **a new `app.require_approval` joins
  it with no edit**; applied `:888-903`); FORCE RLS on every `app` table
  (`:905-924`); a down with `AP900` (`:926-938`). It reads no capability
  manifest. Callers: freeze (`bin/migrate.py:416`), verify (`:442`), render
  (`rendering.py:2451-2452`). `docs/migrations.md:174-184`'s refusal table
  omits the release-function rule (§1 D1882).
- **The migration command.** `bin/migrate.sh` (verbs a CASE at `:128`:
  `status|up|render|freeze-lock|verify-lock`; `down|rollback` refused
  `:131-132`; exit codes `:21-27` 0/2/3/4/5/9; `--runtime` `:121`;
  `--follows` only with `freeze-lock --project` `:153-158`; dispatch
  `:194-255`; `up`/`status` need root and docker `:247-250`) and
  `bin/migrate.py` (`main` `:459-466`; `freeze_project_lock` `:373-424`;
  `verify_project_lock` `:427-456`; `run_every_set` `:184-223`:
  `reconcile_project_ledger` `:226-282`, one dbmate run per set, release first,
  `record_ledger` `:285-347`; `run_dbmate` appends `--strict` for `up`
  `:157-161`; `MigrationError` → 5 `:581-583`). **Deploy step 6** is the only
  caller of `up`: `[<release>/bin/migrate.sh, "--project",
  "/etc/agentic-postgres/projects/<key>/manifest.yaml", "--runtime", "up"]`
  (`bin/deploy-project.py:2537-2546`), any non-zero flattened to exit 5
  *"migrations did not apply: …"*. `<release>` is
  `/opt/agentic-postgres/releases/<commit>` (`installed_release.py:34`), a
  `git archive` of the commit (`:15-17`, `:166-167`), so **only committed files
  reach it** — `migrate.py`'s `REPO_ROOT` there is the release
  (`bin/migrate.py:27`). `installed_release.assert_clean` (`:101-112`) refuses
  a checkout with any uncommitted change (D971).
- **What a set's digest is today.** There is none of its own
  (`migrations.digest()` `:446-447` hashes text). The render records
  `migrations.project_set.lock_sha256 = sha256(lock bytes)` and `.count`
  (`rendering.py:2486-2495`, `:606-616`; schema `outputs.schema.json:
  2270-2310`) — *"the lock is … what a reviewer signed off on"*.
- **The readings a proposal can bind, each measured by the explore pass.**
  `apg dev up` (`bin/dev.py:297-470`; renders nothing and exits 4 without a
  render `:123-142`; **an environment already up is exit 2** `:319-325`;
  applies each migration by `psql` as `migration_user`, one transaction each,
  NOT dbmate `--strict` `:403-429`; state `.generated/.dev/<key>/`, gitignored;
  ~10–16 s, `docs/dev-environment.md:172-185`). **`upgrade plan` cannot price a
  project-set change** (the bump is from `template_version` alone,
  `upgrade_plan.py:323-330`; a project-only change is BLOCKED *"not ahead"*
  `:354-359`). **`apg generate --check` cannot see a migration before a
  deploy** (the client is built from the snapshot `api-contract.sh --update`
  captures after one, D1208; `generate.py:314-340` stops at the first differing
  file). The harness records **cases asked, never outcomes**
  (`evaluation_harness.coverage` `:714-762`; the example: 62 derived + 19
  written over 9 capabilities, `projects/example/contracts/evaluation-
  report.md`). The capability contract is COMMITTED at
  `projects/<slug>/contracts/mcp-capabilities.canonical.json` and the deployed
  lock is recompiled every deploy (`deploy-project.py:2482-2499`).
  **Destructive detection: none** (`DROP TABLE`, `ALTER … TYPE`: 0 hits in
  `src/`/`bin/`; the `destructive` pytest marker is declared at `pytest.ini:25`
  and used by 0 tests). **Proposal/approve/reject for migrations: none.**
- **The manifest.** `schemas/project.schema.json`: root
  `additionalProperties: false` (`:7`); version enum 1–7 (`:16-27`; its
  description still opens *"1 to 5"*, §1 D1882); the per-version gates in the
  top-level `allOf` (`:790-962`, v7 `connectors` `:943-962` is the shape a v8
  gate copies); `migrations.set` (`:101-116`). `config.py`:
  `SUPPORTED_PROJECT_SCHEMA_VERSIONS` `:64`, `PROJECT_CONNECTORS_FROM = 7`
  `:77`, `PROJECT_MIGRATION_SET_FROM = 5` `:87`, `config.project_migration_set`
  `:1088-1097`, `validate_project_semantics` `:1127-1132`/`:1228`,
  `load_project_manifest` `:1729-1741`; **no manifest migrator — old versions
  are accepted as they are** (`:58-63`). The schema enum and the constant are
  held together by `test_capability_compiler.py:957-975`.
  `tests/contract/test_project_manifest.py`: `test_example_manifest_is_valid`
  (`:39-45`, both fixtures at `max(SUPPORTED)`), `downgrade_to_two`
  (`:83-96`), `downgrade_to_five` (`:725-736`). `project.example.yaml:52-53`
  is `migrations: {set: projects/example}`; `project.second.example.yaml`
  declares no set.
- **Identity.** The one resolver is `bin/database-access.py:caller_unix_user`
  (`:70-90`, `SUDO_UID` → a name; *"There is no `--as-user`: an identity
  supplied on a command line is not an identity"*, `:25-28`). `getpass` is used
  for passwords only; no `SUDO_USER`, no `os.getlogin`. The two-person prior
  art is DATABASE-side: `workflow_decide_approval` refuses the run's owner
  (`0035:988-1000`, `AP403: approver_is_owner` `:992`).
- **The edge.** `infra/edge/compose.yaml`: `docker-socket-proxy` `:26-111`
  (read-only, `cap_drop ALL`, `no-new-privileges`, env allowlist, network
  `control` only, healthcheck) and `traefik` `:113-151` (`ports 80:8080,
  443:8443` `:127-129`, networks `[control, egress]`, healthcheck). **Neither
  sets `mem_limit`, `pids_limit` or `cpus`** — deliberately:
  `test_the_edge_plane_is_untouched` (`tests/contract/test_process_limits.py:
  175-185`) asserts `"pids_limit" not in` the file, *"so that adding it later is
  a decision somebody takes"* (D1586; deferred to *"Session 35's hardening
  run, with the deploy-downtime measurement it already owes"*,
  `session-31-implementation-plan.md:2088`). Other edge pins:
  `test_compose_contract.py:1173-1220`, `test_edge_config.py:103`, `:205`,
  `:522-650`. **`deploy.sh` never touches the edge** (`deploy.sh:71-75`);
  `bin/edge.sh restart` is `do_down` + `do_up` (`:343-346`; `do_up` renders,
  `compose up -d --wait` `:219`, then `edge-network.sh reconcile` `:236`);
  deploy refuses without a running edge (`deploy-project.py:710-759`).
- **Per-project limits.** `config.SERVICE_RESOURCE_DEFAULTS` (`:681-691`,
  pids and cpus per long-running service; ADR 0222's table `:643-680`: 4× the
  measured `pids.peak`), `SHORT_LIVED_PIDS_LIMIT = 64` (`:704`); rendered by
  `rendering.build_compose_env` (`:1811-1821`; keys `:657-658`). `mem_limit` on
  SIX of twenty: postgres (`compose.yaml:207`, `POSTGRES_MEMORY_LIMIT`
  `rendering.py:1806`), metrics `128m` (`:1035`), store `192m` (`:1130`), auth
  (`:1237`, `rendering.py:1936`), storage (`:1566`, `:1966`), mcp (`:1705`,
  `MCP_MEMORY_LIMIT_MB = 384` `:937`). **Without: pgbouncer (`:558`),
  postgrest (`:717`), docs (`:918`)** and the eleven short-lived services.
  `docs/threat-model.md:35` says *"Per-service `mem_limit` and `pids_limit` on
  every service"* — false for `mem_limit` (§1 D1878). `doctor capacity`'s
  `unbounded` counts every RUNNING compose container with `HostConfig.Memory
  <= 0` (`capacity_probe.py:156-188`, `capacity_reading.py:309-366`,
  `diagnosis.py:939-949`), the edge's included.
- **`apg-diag`** (`bin/apg-diag.sh`, 380 lines, ADR 0071): `VERBS` `:60`;
  **`SERVICES="postgres pgbouncer postgrest docs edge-probe dbmate"` `:65`**, a
  literal nothing pins; `MAX_LOG_LINES=200` `:71`; `redact()` `:178-183`
  (`(password|secret|token|pgpass)([=: ]+)…` — **misses a JSON-quoted key**,
  `"token": "…"`, because the closing `"` precedes the colon; `auth` and `mcp`
  log JSON); installed by hand at `/usr/local/bin/apg-diag`
  (`infra/host/apg-agent.sudoers:5-8`, `:69-72`: *"Re-install the copy when
  bin/apg-diag.sh changes"*). Pins: `tests/contract/test_diagnostic_surface.py`
  (verbs `:30`, `:58-67`; queries `:170-190`; redaction `:224-259`; sudoers
  `:264-350`).
- **Measurement.** `capacity.Measurement` (`capacity.py:76-96`: `subject,
  value, kind` CONFIGURATION|MACHINE, `conditions` non-empty, `note`),
  `Unmeasured` (`:98-104`); `ENVELOPE` 21 rows (`:113-608`; the only latency
  figure is Session 14's pooled p50 `:132`; the auth-with-loop row `:572`,
  *"NOT under a run"* `:586`); `UNMEASURED` 6 rows (`:611-706`; **D1711's row
  `:613-640`** — its `unblocked_by`: *"a sampler whose cadence is well under a
  run's ~5.5 s and whose stamps are sub-second"*). `docs/capacity-envelope.md`
  is rendered by `bin/render-capacity-envelope.py --write|--check`;
  `test_capacity_envelope.py:149-155` forbids `p50|p95|percentile` in a
  CONFIGURATION row. **No load generator, latency percentile or downtime
  instrument exists anywhere in the tree**; Session 14's figures came from an
  off-host rig not in the repo; the only downtime ever measured is the 8 s
  reboot (by hand); **no deploy step is timed** (`deploy-project.py:211-212`
  prints `==> text` only). There is no per-definition concurrency: the loop
  claims at most one step, one delivery and one fire per iteration and sleeps
  `POLL_SECONDS` (5) only when all three were idle
  (`workflow_worker.py:96`, `:766-896`). Traefik exports router histograms
  (`infra/edge/traefik.yaml:29-60`: `addRoutersLabels: true`, no `buckets:` —
  Traefik's defaults) through the collector (`rendering.py:1243-1376`), never
  yet read. `THR-NOISY-NEIGHBOUR` (`docs/threat-model.md:35`): *"The effect of
  one project's load on the other has not been measured … Session 35's
  noisy-neighbour measurement."*
- **Rehearsals** `rehearsal.SCENARIOS` (`rehearsal.py:83-107`, eleven —
  `database-restart` `:85`); `docs/recovery-operations.md` §4 table
  `:107-119`.
- **The third reader.** `documented_path` = `DX-001`
  (`evidence_claims.py:946`; `acceptance-registry.yaml:1825-1834`); its live
  proof `tests/deployment/test_session12_reuse.py:230-266` requires
  `APG_DX_RECORD_FILE` and reads it with `dx_record` (clean = criterion
  reached, no undocumented step, no source edit). `bin/dx-record.sh`
  `digest|check` (exit 0/2/3/5); `src/agentic_postgres/dx_record.py`
  (`REQUIRED_FIELDS` `:53-63`, `FOLLOWED_BY_KINDS = ("agent","person")` `:77`,
  **`DOCUMENT_ROOTS` `:113-132` — no `workflows.md`, no `connectors.md`**).
  The task statement: `docs/second-walk.md:58-157` between
  `<!-- task-statement:begin -->`/`end` (seven goals `:71-83`); *"At most two
  walks per release … There is never a third"* (`:47-50`). ADR 0207 §1:
  *"the only walkers this project can reach are sessions of a model"*
  (`:46-47`), *"A person's walk would be a second and stronger record"*
  (`:85-86`). **Only walk 2's record survives**, gitignored, at
  `evidence/session-25-dx-record.json` and `~/walk/dx-record.json` (eleven
  undocumented steps; `reached_success_criterion: false`); it was handed to
  every sweep since, which is why `documented_path` reads `failed`. The gate's
  flag is `--dx-record-file` (`bin/session-34-check.sh:151`, `:602-606`,
  `:1424`, `:1510`) — **and its usage line is cut in two at `:354-355`** by
  `--induced-alert-file`'s (§1 D1883). `CURRENT_PATH_DOCUMENTS`
  (`tests/contract/test_session12_documented_path.py:33-60`) also lacks both
  pages.
- **Documentation.** `docs/operator-guide.md` (1,660 lines): §16 *The node as
  a finite resource* `:1146`, §17 *Workflows* `:1279` (Approvals `:1371`), §18
  *Connectors* `:1498`; **no §19**; stale: the worked sweep at `:547`/`:563`
  invokes `bin/session-25-check.sh`, and §5's *"Two tables grow without bound
  and nothing prunes them (D1255)"* `:316-321` contradicts `:30`.
  `docs/new-team-member.md` (495 lines, steps 1–14 `:42-416`; **no workflow or
  connector step**). `docs/README.md` (the operator-guide row `:29`; developer
  loop `:59-65`; evidence `:98-107`). `docs/workflows.md:330-336` and
  `docs/connectors.md:229-237` (*what is not here*). `README.md:7` (*"Status:
  Session 34 implemented"*). `docs/stage-4-decision-report.md` (211 lines; §1
  `:19` … §6 `:153`; filled *"from `evidence/session-25.json` and nothing
  else"* by a script that read and asserted each number, `:3-11` — the script
  was never committed). Nothing tests a decision report except the index
  (`test_documentation_index.py:454-472`). No test reads `scope-closure.md`.
- **The gate to derive from.** `bin/session-34-check.sh` (1,670 lines): header
  `:1-111` (*"Derived from bin/session-33-check.sh by diff"* `:12`), `readonly
  SESSION=34` `:120`, `usage()` `:177`, `parse_arguments()` `:539-735` (25
  flags + `-k`; eight refused on purpose `:643`, `:685-721`), `mode_offline`
  `:1177-1394`, `mode_host` `:1396-1592`, `mode_external` `:1594-1659`.
  `tests/contract/test_session_thirty_four_gate_modes.py` (914 lines;
  `SESSION_PREVIOUS` `:51`, `SESSION = 34` `:53`, `SESSION_PREVIOUS_NUMBER`
  `:68`; `SESSION_THIRTY_FOUR_CLAIMS` `:88-116`; the no-gap test `:241`).
- **Retention.** ADR 0213's two prune functions cover the agent record only
  (`0033:148`, `:212`, granted to nobody). Nothing prunes the ten tables
  0034–0036 created (`workflow_definition`, `_run`, `_step`, `_worker`,
  `_approval`, `_attempt`, `connector`, `_event`, `_delivery`, `_receipt`).

---
## 1. The divergence table

Six columns. Each row is a **measured fact about the tree at `a018939`** (or
about the host as `op` read it on 2026-09-30) set against what the brief (the
stage plan's §5 *Session 35*, its §1 rows, §6–§10, scope-closure §27, Session
33's §10 and CLAUDE.md §9) says, with the decision this plan takes. **Next free
number after this table is D1892.** Rows the runs add go in the second table
below, in execution order.

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D1857** | Stage plan §5: *"`apg migrate propose --project M` writing `projects/<slug>/proposals/<set-digest>.json`"*. | **A set has no digest of its own.** `migrations.digest()` (`:446-447`) hashes text; the render records `migrations.project_set.lock_sha256 = sha256(released.lock.json bytes)` (`rendering.py:2486-2495`, *"the lock is … what a reviewer signed off on"*), and the lock carries every migration's `template_sha256` and `canonical_render_sha256` (`build_lock` `:483-545`). | **The set's digest IS `sha256(lock bytes)`, computed by ONE new function `migrations.set_digest(set: MigrationSet) -> str`**, which `rendering.py:2486-2495` is changed to call (ADR 0002: one reader of a derived identity). The proposal is `projects/<slug>/proposals/<digest>.json` (the full 64 hex), its approval `<digest>.approval.json`. A proof holds the proposal's digest, the render's `lock_sha256` and the function equal on the example set. | The lock already binds every template and its canonical render; a second digest over the same bytes in another order would be a second identity for one set. | **0243** |
| **D1858** | D1523: a proposal carries *"`upgrade plan`'s class"*. | **`upgrade plan` cannot price a project-set change**: the bump is from `template_version` alone (`upgrade_plan.py:323-330`); a project-only change is BLOCKED *"candidate is not ahead"* (`:354-359`); the set's `lock_sha256`/`count` appear only as raw leaf differences no class maps. | **Omitted from the record, and the record says why.** The proposal carries `release: {template_version, release_lock_sha256}` and the set's `follows_release_version` (with its source) instead — the facts `upgrade plan` would have read. | A class the command cannot compute would be a value that looks measured (D600). The release's own class stays `upgrade plan`'s, read at Run 9. | 0243 |
| **D1859** | D1523: *"`generate --check`'s diff"* as the client impact. | **A pre-deploy `generate --check` cannot see a migration**: the client is generated from the snapshot `api-contract.sh --update` captures AFTER a deploy (D1208; `generate.sh:15-20`), and `check()` stops at the first differing file (`generate.py:314-340`). | **Replaced by the reading that CAN be taken before a deploy**: the set's final `api` surface — every function and view the set defines or replaces, from `sql_surface.final_surface` over the set — and, for each, whether the project's reviewed `contracts/postgrest-api-surface.yaml` names it (`surface: {functions: [{name, reviewed}], views: [...]}`). The client moves after the deploy by the existing path, and the record says so. | The brief wanted *"what this change does to the callers"*; the reviewed surface is that fact on the workstation, and a check that always reads *no drift* is D1057's empty list. | 0243 |
| **D1860** | D1523: *"the harness's counts"* and *"evaluation results"*. | The harness records **cases asked, never outcomes** (`render-evaluation-report.py:28-34`; `evaluation_harness.coverage` `:714-762`): per capability derived/written positive/adversarial counts, and the contract digest. Outcomes exist only in test runs. | **Recorded as `harness: {contract_sha256, derived, written, capabilities}` and labelled *cases, not results*.** A project whose manifest declares no `mcp.capabilities` records `harness: {"not_applicable": "the manifest declares no capabilities"}` (ADR 0195: said, not zero). | A count of cases dressed as a pass rate is the value that looks measured. | 0243 |
| **D1861** | D1523: *"the dev-cluster apply result"*; *"the shadow result is `apg dev up` with the candidate in the project's set (D1067)"*. | `apg dev up` renders nothing (exit 4 without a render, `bin/dev.py:123-142`), **refuses when an environment is already up (exit 2, `:319-325`)**, applies by `psql` as `migration_user` one transaction per migration — not dbmate `--strict` (`:403-429`) — onto an EMPTY cluster. | **`propose` runs the product's own `bin/dev.sh up --project M`** (D1114), reads its exit and its `migrations applied` line, times it, then runs `bin/dev.sh down --project M`. **It refuses before starting when an environment is up** (exit 2, naming `apg dev down`) — it never downs somebody's environment. The record states the reading's limits verbatim: `from_empty: true`, `applied_by: "psql as migration_user"`, `existing_rows: "none"`. | A reading of a cluster that holds no rows cannot say what an `ALTER … TYPE` does to real data; saying so is the difference between a shadow and a claim. | 0243 |
| **D1862** | Stage plan §5: *"a new destructive lint that NAMES a `DROP`/`ALTER … TYPE` over a project-owned object"*. | **Nothing detects one** (0 hits for `DROP TABLE`/`ALTER … TYPE` in `src/`/`bin/`; the `destructive` marker `pytest.ini:25` is used by 0 tests). `sql_surface` parses only `DROP VIEW`/`DROP FUNCTION` (`sql_surface.py:49`, `:53`). The example set has none (`0001:50-51` is `ALTER TABLE … ENABLE/FORCE ROW LEVEL SECURITY`). | **`migrations.destructive_findings(set) -> tuple[Finding, ...]`** over each migration's comment-stripped UP section (the lint's own stripping, `:795-805`): `DROP TABLE|VIEW|MATERIALIZED VIEW|FUNCTION|PROCEDURE|INDEX|TYPE|SEQUENCE|TRIGGER|POLICY`, `ALTER TABLE … DROP COLUMN|DROP CONSTRAINT`, `ALTER TABLE … ALTER [COLUMN] … [SET DATA] TYPE`, `ALTER TABLE … RENAME`, `TRUNCATE`, and `DELETE FROM` with no `WHERE`; each `Finding(version, kind, object)`. **Named in the record, never refused** — and the lint is untouched by it. `IF EXISTS`, quoted names and schema-qualified names are read (Session 34's D1818 lesson: every spelling PostgreSQL accepts). | *"Named, not refused"* is the brief's word; a reviewer decides, and a destructive change is sometimes the change. | 0243 |
| **D1863** | Stage plan §5: *"`approvals_required` in the project manifest (schema 7, default 0)"*. | **Schema 7 is Session 34's** (`connectors`, `project.schema.json:584-606`, gate `:943-962`); the root forbids unknown members (`:7`); there is no manifest migrator (`config.py:58-63`). | **Project manifest schema 8** adds `migrations.approvals_required` (integer, enum `[0, 1]`, default 0) inside the existing `migrations` block, FORBIDDEN below 8 by a v8 gate in the v7 gate's shape, and meaningful only with `migrations.set` (a manifest naming no set may not carry it — refused by `validate_project_semantics`). `config.PROJECT_APPROVALS_FROM = 8`; **`config.approvals_required(manifest) -> int` is the ONE reader**. `project.example.yaml` moves to 8 WITH `approvals_required: 1` (the example project demonstrates the two-name rule); `project.second.example.yaml` to 8 without it (its control). Host manifests are unchanged (beta 7, alpha 4 — both read as 0). | A stage plan's schema number is a prediction; the schema file is the fact. The field lives beside the set it governs. | 0243 |
| **D1864** | D1523: *"`approve` is a second record naming a second username"*; *"second-person approval configurable by risk"*. | **There is no operator identity.** The one resolver (`bin/database-access.py:caller_unix_user` `:70-90`) resolves `SUDO_UID` to a Unix name and its docstring states the rule: *"an identity supplied on a command line is not an identity"* (`:25-28`). The host has ONE operator account (`op`) and one agent account (`apg-agent`), so a resolved name could not tell two people apart either. Proposals are written on a workstation, where no product credential exists (CLAUDE.md §6). | **Both records carry a DECLARED name and say so**: `declared_by` (never `approved_by` or `author`), from a required `--by NAME` (`^[A-Za-z][A-Za-z0-9 ._'-]{1,63}$`). `approve` refuses a name equal (case- and space-folded) to the proposal's `declared_by`, a missing proposal, and an existing approval. The approval names the PROPOSAL FILE's own sha256, so an edited proposal invalidates it. **ADR 0243 states the record's reach in one sentence every page repeats: it stops an unreviewed or altered set reaching a host; it does not authenticate a reviewer.** *"By risk"* is `approvals_required` per project (0 or 1); the destructive findings are shown to the reviewer, not scored. | A name typed by the person it names is a record of intent, and the tree's own rule forbids calling it an identity. Writing that down is cheaper and truer than inventing an operator login this product's non-goals exclude (`product-contract.md` §5). | **0243** |
| **D1865** | Stage plan §5: *"`migrate --project up` on a host refusing a set whose proposal is absent or whose digest moved"*. | Deploy step 6 is the only caller (`deploy-project.py:2537-2546`, exit flattened to 5); `bin/migrate.py`'s `up` runs `reconcile_project_ledger` then dbmate per set (`:184-282`); an operator may run `sudo bin/migrate.sh --project … --runtime up` by hand. **Every set applied today has no proposal** — beta's `36 + 3` among them. Only committed files reach the release directory `migrate.py` runs from (`installed_release.py:15-17`). | **The gate lives in `bin/migrate.py`'s `up` path, before dbmate, and refuses only an ACT**: when the project set has at least one version the project LEDGER lacks, it requires `<release>/projects/<slug>/proposals/<set_digest>.json` whose `set_digest` equals the set being applied, and — when `config.approvals_required(manifest) == 1` — `<digest>.approval.json` naming that proposal file's sha256 and a `declared_by` different from the proposal's. Else `MigrationError` → exit 5 with one of four fixed sentences (`no proposal for this set <digest16>`; `the proposal names another set`; `approvals_required is 1 and the proposal has no approval`; `the approval does not name this proposal, or names its proposer`). A set with nothing pending needs nothing; the RELEASE set is never gated (it is reviewed by the release's own lock). `status` prints one line: `proposal <digest16>: present, approved by <name>` / `absent` / `not needed (nothing pending)`. | A gate on a STATE would refuse beta's next deploy for a set applied a week ago; a gate on the act is the brief's sentence, and it breaks no upgrading project that adds nothing. | **0243** |
| **D1866** | Stage plan §5: *"The same record over `mcp-contract.sh compile` for a capability change."* | The capability contract is committed (`projects/<slug>/contracts/mcp-capabilities.canonical.json`) and compared byte for byte by `check --project`; the DEPLOYED lock is recompiled at every deploy (`deploy-project.py:2482-2499`). **There is no pending state to gate on.** | **The proposal records `capability_contract_sha256`** (the committed contract's sha256, or `not_applicable` with a reason), and deploy step 6 PRINTS one line after the lock is written: `capability contract <sha16>: named by proposal <digest16>` or `…: named by no proposal of this project` — **a report, never a refusal**. A refusal is priced in §10. | Refusing needs a deployed-lock comparison and a transition rule for every project deployed today; a report gives the operator the fact at no risk to the minor. | 0243 |
| **D1867** | Scope-closure §27 item 1 (the operator, 2026-09-29): *"approval enforced in the database, so a direct PostgREST call on a gated function meets it too"*; Session 33 §10: *"a release-owned `api.require_approval(p_tool text)` (SECURITY DEFINER, reading `request.jwt.claims -> 'apg_approval'` and matching an approved `workflow_approval` row for the calling agent, the tool and the request's `Idempotency-Key` header)"*. | **An `api` function is either forgeable or refused**: granted to a request role it is `POST /rpc/require_approval`; granted to nobody it fails `test_api_migrations.py:494-544` (*"no role can call it"*), and either way it moves five exact pins (`:206-218`, `:277-278`, `test_api_surface_contract.py:538-579`, `test_session3_authorization.py:687-690`) — D1779's finding exactly. A project body may not name `app_private` (`migrations.py:142-159`), so the guard cannot live there. `app.emit_event` (`0036:198-267`, `REVOKE … FROM PUBLIC` `:1039`, no GRANT) is the precedent: callable only by a definer running as the owner. The plane forwards the agent's own JWT (`mcp_upstream.py:1`); the approval row has no agent column (the run does, `0035:98-113`); `app_private.agent_idempotency_key()` reads the header (`0029:139-169`). | **Migration 0037 creates `app.require_approval(p_tool text) RETURNS void`, SECURITY DEFINER, `SET search_path = pg_catalog, pg_temp`, created as the owner, `REVOKE ALL … FROM PUBLIC`, granted to NOBODY.** Body: `agent := nullif(current_setting('app.agent_id', true), '')::uuid`; **NULL → RETURN** (a human's own write — §2 of ADR 0242); else `claim := nullif(current_setting('request.jwt.claims', true), '')::jsonb -> 'apg_approval'`; `key := app_private.agent_idempotency_key()` (its own `PT412` on a malformed header stands); refuse unless `claim` is an object, `claim->>'tool' = p_tool`, `key IS NOT NULL`, `claim->>'key' = key`, `claim->>'id'` is a uuid, and `EXISTS (workflow_approval a JOIN workflow_run r ON r.id = a.run_id WHERE a.id = (claim->>'id')::uuid AND a.status = 'approved' AND a.tool = p_tool AND a.idempotency_key = key AND r.agent_id = agent AND r.status = 'running')` — the signer's own predicate (`0035:1088-1107`) plus the tool and the key. **Every refusal is ONE sentence: `RAISE EXCEPTION 'AP403: approval_required' USING ERRCODE = 'PT403'`** (PostgREST: HTTP 403; the reason never says which member failed). Rig 35a measures the claim and the header arriving in SQL before a line is written. | The operator's decision, taken at the only place a direct call cannot route around; `app` is where D1779 already proved a release function can be reachable by a reviewed definer and by nothing else. | **0242** |
| **D1868** | Session 33 §10: *"a lint rule that a gated capability's function calls it"*. | **The lint reads no capability manifest** (`lint_project_set` `:795-938`); no join exists between a compiled contract and a set's SQL — `surface_operations`' `"qualified"` name (`capability_compiler.py:203`) has no consumer; a write tool compiles to `operation.path` (`:694-705`). Refusing at RENDER would make an upgrading project with an unguarded gated RPC fail to render — an invalidated manifest, a MAJOR class (`compatibility.py:100`). | **A new module `src/agentic_postgres/approval_gate.py`**: `unguarded(contract: dict, final_bodies: dict[str, str]) -> tuple[str, ...]` — for every tool with `requires_approval: true` whose `operation.path` is `/rpc/<name>` and whose function `api.<name>` the project set defines, the function's final body's FIRST statement after `BEGIN` must be exactly `PERFORM app.require_approval('<tool>');` (comments and whitespace ignored). **It REFUSES in `bin/mcp-contract.sh check --project` (exit 5 naming the tool) and in `propose`; it REPORTS at render** (one line, `approval gate: <tool> does not call app.require_approval first (ADR 0242)`), never refusing there. A gated tool whose operation is a RELEASE function is reported as `release_function` and never refused (D1869). | A lint that knew capabilities would be a second reader of the compiled contract inside a module that must not import it; a check at the workstation's compile and at the proposal is where a project author meets it, and the render's line is where an operator does. | 0242 |
| **D1869** | Session 33 §10's pricing assumed every gated function is a project's. | **A deployment PROFILE may add `requires_approval` to a RELEASE tool** (`project.second.example.yaml:83-84`, `update_task_status`; `capability_compiler.py:108-118`), and `api.update_task_status` (`0030:237+`) checks none. The database cannot read a deployment's profile. | **Not covered, and said so**: THR-APPROVAL's residual keeps one sentence — *a profile-added approval on a release tool remains a plane control; the database half covers a project's own gated RPCs.* The render's approval-gate line names such a tool `release_function` (D1868). | Making a release function read a deployment's profile from the database is new construction (a rendered table of gated tools) nobody has priced; the one gated function in any shipped set is the project's. | 0242 |
| **D1870** | D1722 / D1806: *"a project function cannot honour `Dry-Run`"*, priced as `app.request_is_dry_run()`. | Rig 33b: a direct agent call with `Dry-Run: true` WROTE. After 0004 an agent's direct call — dry or not — stops at the guard; an approved call with `dry_run` is refused by the plane (`mcp_tools.py:600-605`). A HUMAN's direct call with a `Dry-Run` header still writes (humans never send it through a product surface; the plane never forwards a human's call). | **D1722's agent exposure closes as a consequence of 0004; `app.request_is_dry_run()` is still not built**, and §10 keeps the human half with this reading. | Building the helper now would move every gated project body a second time for a caller who never sends the header. | 0242 |
| **D1871** | ADR 0231: *"Binding the key means the claim authorises ONE write: a replay of that key is re-read by ADR 0181."* | ADR 0181's replay-read lives in the RELEASE write functions (`agent_idempotency_claim`, `0029:194-236`); **`set_note_embedding` has no idempotency** — a second call with the same approved claim and key writes again (an upsert of the same note: one row either way). The step token is held only by the worker, for at most 900 s + 30 s skew; the agent never receives it. | **Accepted and stated**: the guard binds a call to an approved decision, tool and key; it does not make the project function idempotent. Within the step token's life the worker's own crash replay (D1646) may call twice, and the upsert keeps ONE row. The guard does not consume the approval (a consumed approval would turn that replay into a terminal step failure and a compensation). | The threat D1721 names is an agent's OWN token reaching the RPC; that token can never carry the claim. Consuming the decision would trade a measured-harmless replay for a new failure mode. | 0242 |
| **D1872** | — | Pins that 0037 and 0004 move: `tests/contract/test_project_migration_sets.py:918-931` (`RELEASE_FUNCTIONS`, an exact set with `("app","emit_event")`); `test_database_function_signatures.py:~615` (per-schema witnesses); the grants guard `test_migrations.py:256-257` (`CONNECTIVITY_NOBODY`'s shape); `test_dev_environment_cluster.py:271-306` (the ledger `endswith("20260930120003")`); the example lock's `follows` record (ADR 0240: the freeze exits 5 without `--follows`, D1833). | **Each moves in the run that makes it true, to a larger or stricter equality**: `RELEASE_FUNCTIONS` gains `("app", "require_approval")`; a `GATE_NOBODY` set asserts `has_function_privilege` false for every login and request role (D1814's lesson: the function's grant, not only the schema's `42501`); the ledger pin reads 0004's version; the example lock is frozen `--follows 20260912120031` (declared, ADR 0240). | A pin moved to what the tree now is, never loosened (CLAUDE.md §6). | 0242 |
| **D1873** | Stage plan §5: *"The noisy-neighbour measurement: alpha's worker at its declared concurrency against beta's REST p95, and the reverse"*. | **Alpha installs no workflow definition** (no set; step 6d printed *"no workflow definitions (the project declares no migration set)"* on every 1.10.0–1.12.0 deploy), and **there is no declared concurrency** — the loop claims at most one step per iteration (`workflow_worker.py:766-896`); the only concurrency knobs are per-tool `max_concurrent_calls` (`capabilities.schema.json:481`). No load or percentile instrument exists in the tree. | **Four phases, each 120 s, read by a trip script (`s35-r10-neighbour.py`, Sheet F7):** **A** — idle: both projects' REST probed through the edge; **B** — beta's step pass kept busy by K = 24 runs of `notes-roundtrip` enqueued at once by a probe agent (the loop's whole concurrency is one), against alpha's REST; **C** — alpha's REST loaded from INSIDE alpha's `internal` network (a container on it, concurrency 8, `GET /notes?limit=50` as a probe human), against beta's REST; **D** — the mirror of C. Each phase's figures are p50/p95/p99 and the error count of the NEIGHBOUR's probe, plus the loaded side's achieved rate; the envelope gains one `MACHINE` row per phase with its conditions (Run 11). | *"Alpha's worker"* has nothing to run; the honest reading of the brief is *each project's real workloads against the other's latency*, and the step pass and the REST path are the two this deployment has. A load through the edge would measure the rate limiter (D1874). | — |
| **D1874** | — | **The edge limits each SOURCE**: `apg-rate-limit: {average: 20, burst: 40, period: 1s}` (`infra/edge/dynamic/baseline.yaml:42-46`, `:77-82`) in the baseline chain every router carries. Whether its bucket is shared across the routers of two projects, or kept per router, is **unmeasured**. | **Every probe that crosses the edge stays at ≤ 8 req/s in total from the host**, and rig 35c measures whether the bucket is shared across routers (it decides whether the neighbour script may probe both projects at 4 req/s each at once, or must alternate). A LOAD never crosses the edge (D1873). A 429 in a probe's record is counted and reported separately, never as a latency. | A probe that trips the limiter measures Traefik's policy, not a neighbour. | — |
| **D1875** | D1524: *"a deploy's downtime per service class (REST, auth, storage, mcp, the database) into the envelope, under ADR 0155's conditions"*. | **No deploy step is timed** (`deploy-project.py:211-212`); recreation is Compose's decision on the `apg.mounted.sha256` label (`runtime_override.py:973`, ADR 0155); with Traefik's Docker provider a stopped container's router DISAPPEARS, so a caller sees a 404 from the edge rather than a 502 — **unmeasured here** (rig 35d). The database is recreated only when its mounts change. | **An op-side probe `s35-r10-probe.py`** (no token; one unauthenticated endpoint per class, fixed in Run 1 from rig 35d: REST `GET <rest>/`, auth `GET <app>/auth/jwks.json`, storage and mcp and docs by the endpoint rig 35d finds answers a fixed status without a credential) at **0.5 s per class per project**, each result a JSONL line `{t_mono, t_wall_ms, project, class, status | error, ms}`; **"down" is a transport error or an edge answer 404/502/503/504 carrying Traefik's body**. It runs around each deploy (F2, F3), the edge restart (F4, both projects) and the `database-restart` rehearsal (F7b, alpha — the DATABASE class's only reading, labelled *induced by the rehearsal, not a deploy*). A class the deploy did not recreate reads `0 s (not recreated)`, from the deploy's own `Recreated` lines — never inferred. | Downtime is what a caller sees; a container's start time is not. The rehearsal is the one sanctioned way to restart the database. | — |
| **D1876** | Scope-closure §27 item 2: *"D1711's sub-second sampler is still owed"*; `capacity.UNMEASURED`'s row (`:613-640`). | `op` reads a container's `memory.current` through `/proc/<pid>/cgroup` + `mountinfo` (D1739); Session 33's 10-s, second-stamped sampler put **none of 513 samples wholly inside a ~5.5 s run** (D1776). | **The sampler reads beta's `auth` `memory.current` every 0.1 s with millisecond wall stamps** (`time.time_ns()`), resolved by the D1739 method, for the whole of phase B; **a classifier script (`s35-r10-classify.py`) reads each run's `started_at`/`finished_at` (microseconds, as the superuser, in F7's own transcript) and counts a sample as *under a run* only if its stamp lies inside `[started_at, finished_at]`**. The `UNMEASURED` row is replaced by a `Measurement` ONLY if at least 20 samples lie inside run windows; the row states max and median of those and of the samples outside. | D1711's own rule, with the cadence its `unblocked_by` names. | — |
| **D1877** | Scope-closure §27 item 4: *"the edge's unbounded `traefik` and `docker-socket-proxy`"*; `session-31-implementation-plan.md:2088` (deferred to 35 with the downtime measurement). | `infra/edge/compose.yaml:26-151` sets no `mem_limit`, `pids_limit` or `cpus`; **`test_the_edge_plane_is_untouched` pins the absence** (`test_process_limits.py:175-185`); the edge is recreated only by `bin/edge.sh restart` (`:343-346`), which drops every project's ingress and needs `edge-network.sh reconcile` (`:236`); `doctor capacity` counts both as unbounded (D1710). Their memory and pids have never been read. | **ADR 0244 bounds both containers**: `mem_limit`, `pids_limit`, `cpus` as literals in `infra/edge/compose.yaml`, each from **Sheet E0's reading** by ADR 0222's method (pids = 4 × `pids.peak`, floor 64; memory = 4 × `memory.peak` rounded up to 32 MiB, floor 64 MiB; cpus `"1.0"`). **`test_the_edge_plane_is_untouched` is REPLACED by `test_the_edge_plane_is_bounded`** (the exact values, stricter — ADR 0244 authorises it). The recreation is **Sheet F4**, with the probe on both projects: the EDGE class of D1875. | The ceiling a neighbour cannot exceed has to include the one thing both projects share; recreating it is an act, so it gets a sheet and a number. | **0244** |
| **D1878** | Stage plan §8 / `THR-NOISY-NEIGHBOUR`: *"Per-service `mem_limit` and `pids_limit` on every service"* (`threat-model.md:35`). | **`mem_limit` is on six of twenty services**; pgbouncer (`compose.yaml:558`), postgrest (`:717`) and docs (`:918`) are long-running and unbounded (Session 31 deferred them: *"Bounding them is a measurement first"*, `session-31-implementation-plan.md:2089`); the eleven short-lived services exit. | **The three are bounded in the same run** from Sheet E0's per-container readings by ADR 0244's rule, through `config.SERVICE_MEMORY_LIMITS_MB` (new, beside `SERVICE_RESOURCE_DEFAULTS` `:681-691`) rendered as `PGBOUNCER_MEMORY_LIMIT`, `POSTGREST_MEMORY_LIMIT`, `DOCS_MEMORY_LIMIT` exactly as `AUTH_MEMORY_LIMIT` is (`rendering.py:1936`). **Every reader of `mem_limit` is grepped first** (D979: `capacity_reading`, `capacity_probe`, admission's `decide` — which charges `unreclaimable_mb`, never the caps, D767 — `bin/admit.py:196-207`, the doctor); `doctor capacity`'s ceilings rise by 6 × those values and `unbounded` falls **10 → 0**, both READ on the trip. The threat-model sentence becomes *"on every long-running service"*. | A claim in the threat model that the tree makes false is the defect class §7 names; a measured cap on the three closes the sentence rather than softening it. | 0244 |
| **D1879** | Scope-closure §27 item 4: *"`apg-diag`'s allowlist (D380) now matters for the inbound route"*. | `SERVICES` (`bin/apg-diag.sh:65`) lacks `auth`, `storage`, `mcp` since Session 7 (D380: *"an ADR's shape rather than a one-line allowlist edit"*); **nothing pins it**; `redact()` (`:178-183`) misses a JSON-quoted key; the refused inbound request lives only in the auth log (THR-CONNECTOR-INPUT's residual). The copy on the host is installed by hand (`apg-agent.sudoers:69-71`). | **ADR 0245**: `SERVICES` gains `auth storage mcp`; `redact()` gains one rule for a JSON-quoted key (`"(password|secret|token|pgpass|authorization|api_key)"\s*:\s*"[^"]*"` → the value `<redacted>`) beside the existing three; a proof pins `SERVICES` EXACTLY and feeds JSON lines from the three services' real log shapes (read from `services/auth-api/app/` logging) through `redact`. The host copy is re-installed on **Sheet F4b** (`sudo install -o root -g root -m 0755 bin/apg-diag.sh /usr/local/bin/apg-diag`) and read by the agent as `apg-agent` (`apg-diag logs auth`). | An unprivileged diagnostic account that cannot read the one log that records refusals is a reader with a hole in it; the decision is ADR-shaped because it widens what that account sees, so it gets one. | **0245** |
| **D1880** | Stage plan §5: *"the operator guide gains sections for capacity, workflows, connectors and proposals"*. | **Three exist**: §16 *The node as a finite resource* (`operator-guide.md:1146`), §17 *Workflows* (`:1279`), §18 *Connectors* (`:1498`). | **Only §19 *Change governance, on a deployment* is new**; §17 *Approvals* (`:1371`) gains *In the database*; §16 gains the edge's and the three services' limits. D709's shape — a brief pricing a free property. | The brief was written before 31–34 wrote their sections. | — |
| **D1881** | Stage plan §5: *"`new-team-member.md` gains the workflow and connector steps"*; scope-closure §27 item 3. | `docs/new-team-member.md` steps 1–14 (`:42-416`) name neither; `dx_record.DOCUMENT_ROOTS` (`:113-132`) and `CURRENT_PATH_DOCUMENTS` (`test_session12_documented_path.py:33-60`) include neither page. A connector needs a facility, a deployment and a key (`docs/connectors.md`) — none of which a walker on a workstation has. | **Two steps**: **15 — *Propose your migration set*** (`apg migrate propose`, read the record; `approve` needs a second person and says so) and **16 — *Compose a workflow over your capability*** (`apg workflow init|validate`, then `apg dev up` installs it — all offline). **Connectors are a READ, not a step**: step 16 ends with one paragraph pointing at `docs/connectors.md` for what needs a deployment. `docs/workflows.md`, `docs/connectors.md` and `docs/change-governance.md` join BOTH lists. | A step a walker cannot perform offline would be a guaranteed `undocumented_steps` entry; a page they may read is not. | — |
| **D1882** | — | Stale prose found by the planning read: the operator guide's worked sweep invokes `bin/session-25-check.sh` (`:547`, `:563`); its §5 retention note (`:316-321`) says nothing prunes the agent record, which 0033 does (`:30`); `docs/migrations.md:174-184` omits the release-function rule (ADR 0235); `project.schema.json:26` says *"1 to 5"*; `docs/README.md:29` names none of §15–§18; `threat-model.md:35`'s `mem_limit` sentence (D1878). | **Each corrected in Run 6**, the way D1536 was in Session 30. | The direction nobody chases (D954): prose a program stopped agreeing with. | — |
| **D1883** | — | **`bin/session-34-check.sh`'s usage is broken at `:354-355`**: the `--dx-record-file` description is cut off by `--induced-alert-file`, whose description carries the rest of it; the host synopsis (`:185-199`) omits `--dx-record-file`. The flag that decides `documented_path` is the one a reader cannot read. | **The Session 35 gate's usage is rewritten whole** (D1488), each flag's description on its own lines, and `test_session_thirty_five_gate_modes.py` gains `test_every_accepted_flag_has_its_own_usage_entry` (every token `parse_arguments` accepts appears once in `usage()` at the start of a line; the refused ones never). The 34 gate is left as it is (it is the previous release's record). | A usage block is the only document a gate has. | — |
| **D1884** | Stage plan D1531 / §4: *"a person, holding only the release and the task statement … the record … read by `apg dx-record check`. Arranged in Session 35, never closed by the author."* | **ADR 0207 §1**: *"the only walkers this project can reach are sessions of a model"* (`:46-47`), a person's walk *"a second and stronger record"* (`:85-86`); `followed_by.kind` admits `agent` and `person` (`dx_record.py:77`); **`docs/second-walk.md:47-50`: *"At most two walks per release"*** — 1.13.0 is a new release. Only walk 2's record survives and has been handed to every sweep since 1.6.0. | **The session ARRANGES; the operator DECIDES on Sheet W (Run 8)**: (a) a PERSON who did not build Stage 4 walks the release commit (preferred — the stage plan's word), or (b) a fresh model session under ADR 0207 §1's conditions, or (c) no walk for 1.13.0. The task statement (`second-walk.md:58-157`) gains ONE goal (*"Propose your migration set and read what the proposal says"*) and names release 1.13.0's commit. **A record reaches the sweep only if it exists before Sheet F6**; otherwise the Session 25 record is handed again, `documented_path` stays `failed`, and the Stage 5 report says which of (a)/(b)/(c) happened. A second walk of 1.13.0 is budgeted (§10) if the first records more than eleven steps. | The author may not close it (stage plan §4); who walks is the operator's to arrange, and each branch has an honest outcome written in advance. | 0207 |
| **D1885** | Stage plan §5: *"`session-35-check.sh` derived by diff from 28's"*. | Every gate since 31 was derived from its predecessor (`session-34-check.sh:12`); `test_the_previous_gate_is_the_one_before_this_one_with_no_gap` (`test_session_thirty_four_gate_modes.py:241`) requires `SESSION_PREVIOUS_NUMBER == SESSION - 1`. | **Derived from 34's**, `SESSION_PREVIOUS_NUMBER = 34`. | The no-gap proof is the fact; the stage plan predated 31–34's gates. | — |
| **D1886** | Scope-closure §27 item 5: *"The retention story, now four tables longer (D1700, D1775)"*. | Ten `app_private` tables from 0034–0036 are never pruned; runs reference agents, approvals reference users (`decided_by`), receipts reference runs; ADR 0213's shape is one definer function per table, granted to nobody, taking an operator's horizon. Beta's counts are small (≈ 90 runs, 4 deliveries; §0). | **Not built in Stage 4.** A retention design is ten functions in FK order, a horizon rule per table (an approval's horizon cannot precede its run's) and a doctor reading — a session, not a hardening item. **The trip reads the ten tables' row counts and oldest ages on both projects (Sheet F8) and the Stage 5 report states them as the retention bill.** | *"Scope in §1, not in Run 6"* (the operator's standing request); a pruning plane built in the release session would be built without a reading of what it prunes. | — |
| **D1887** | CLAUDE.md §9: D1642 (a kit names the checkout's commit) and D1856 (a kit's `projects/` is 755); *"both belong to a session already in `dr_kit.py`"*. | D1856 is one directory mode in `dr_kit`'s export (the root 0700, `projects/` 0755 on the host); D1642 is a kit FIELD read by `verify` and the restore path. | **D1856 is fixed in Run 5** (`projects/` created 0700; the export's own sentence then true; a proof over a tmp kit reads every mode). **D1642 is left** — a field change is a kit-format move with readers, and no reader asks for the other commit. | One is a mode that makes a printed sentence false; the other is a format change with no requester. | — |
| **D1888** | Scope-closure §27 item 2: *"the delivery pass shares the `auth` process with the step loop"*. | Every connector is installed DISABLED and enabled only inside the Session 34 proofs (D1809); an enabled outbound connector needs a sink the proof runs. The delivery pass's only reading is `delivery-retry-storm` (Session 34 Sheet D8: attempts 4.7–5.8 s apart, the heartbeat moving). | **Not induced during the neighbour phases**: the loop's step pass is the loaded workload (phase B); the envelope row's conditions say *"delivery pass idle (no connector enabled)"* and cite Sheet D8's reading for the pass itself. | Enabling a connector on production for a measurement adds a receiver nobody operates; the storm already read the pass under failure, which is its worst case. | — |
| **D1889** | Stage plan §2.2: *"the class is read from the plan's output at each session's close and never chosen"*; §5: *"`template_version` as `upgrade plan` prices it"*. | 1.13.0 adds a migration (`migration_added`, minor — declarable only, D1703), a manifest version that leaves every older manifest valid (no class; old versions are accepted, `config.py:58-63`), compose `mem_limit` keys (`implementation`), no document move (outputs stay 19), no secret. **The proposal gate is a new step for a project that ADDS a migration after upgrading** — not an invalidated manifest. | **`1.13.0`, minor by declaration**: Run 9 reads `upgrade plan … --also migration_added` → `bump minor`, `requires minor`, verdict `ok`; without → `requires patch`. Predicted leaves: `template_version`, `migrations.release_lock_sha256`, `migrations.project_set.count` 3 → 4, `.lock_sha256`, and the compose-environment digests of the three bounded services if the document carries them (read, not predicted). The upgrade guide's `1.13.0` row states the new step (*"a project that adds a migration now proposes it first"*). A `major` is §9's stop. | The fourth release in a row whose price the command sees only by declaration (D1561, D1703, D1811). | 0162 |
| **D1890** | Stage plan §5: *"`docs/stage-5-decision-report.md` written from that document"*; *"Must not … write the decision report before the evidence document exists"*. | Stage 4's report was filled *"from `evidence/session-25.json` and nothing else"* by a script that read and asserted each number (`stage-4-decision-report.md:3-11`); the script was never committed. Nothing tests a decision report beyond the index. | **Written in Run 11, after the tag, from `evidence/session-35.json` and `capacity.ENVELOPE`**: every number in it is read by a filler script (`s35-r11-fill.py`, kept in the scratchpad and WSL `~/s35r11/`, its text in Run 11's Done) that asserts each value it writes and refuses a placeholder left behind. Sections copy Stage 4's (§1 what 1.13.0 is; §2 what was measured; §3 what stayed `not_run`/`failed` and why; §4 what Stage 4 built against its specification; §5 **the hosted question priced against the readings Stage 4 produced**; §6 recommendation). Indexed in `docs/README.md`. | D992's rule, applied a third time; a report whose numbers a program read cannot quietly carry the plan's predictions. | — |
| **D1891** | Stage plan §7: *"35 — new `GOV-*` claims"*; §5 *Proposed families: `GOV-*`, `REL-*` extended, `DX-*` extended*. | `GOV` is not in the ID regex (`test_acceptance_registry.py:101`). `AGT-APPROVE-001/002`, `NODE-LIMIT-001` exist; `OPS-DIAG-*` does not. No `REL` or `DX` requirement is needed: the release machinery and the walk are existing claims (`stage_release`, `documented_path`). | **One new family, `GOV`**, and ten requirements with ten claims (§2): `AGT-APPROVE-003/004`, `GOV-LINT-001`, `GOV-PROPOSE-001`, `GOV-APPROVE-001`, `GOV-APPLY-001/002`, `NODE-LIMIT-002/003`, `OPS-DIAG-001`. | The stage plan proposed the family; the other two it named have no new subject. | — |

**Rows the runs added, in execution order** (the executor appends here; six
columns: `# | Run | Plan says | Tree does / measured | Decision | ADR`):

| # | Run | Plan says | Tree does / measured | Decision | ADR |
|---|---|---|---|---|---|
| **D1892** | 1 | Rig 35a owes D1867's premise: the claim and the key header arriving in SQL, the refusal's SQLSTATE and PostgREST status, D1871's replay, the exact 403 body. | **Every premise holds, measured end to end through the REAL loop and plane** (the step token minted by `AuthService.step_token` after the loop parked on the plane's `approval_required` and a second administrator approved): `request.jwt.claims -> 'apg_approval'` arrives as minted, `{id, key, tool}`; the plane's `Idempotency-Key` arrives in `request.headers` equal to the claim's key. The agent's own token on the guarded twin → **403 `{"code":"PT403","details":null,"hint":null,"message":"AP403: approval_required"}`**, 0 rows (with and without a key); control A (ungated twin) → 200 and a row; the owner → 200, `app.agent_id` empty; approved claim + matching key → 200; other key / no key → 403, 0 rows; **a malformed key → 412 `PT412` from `agent_idempotency_key()` before the guard decides**; decision `rejected` / `expired`, run `cancelled` → 403 each, 200 once restored; the run `succeeded` → 403 and `step_token` refuses to mint (*"the approval is not decided for this agent"*). Guard installed first in `api.set_note_embedding` (grants kept): the agent directly → 403, 0 embeddings; the owner → 200; the approved plane call → served, 1 embedding; the loop finished `succeeded`. D1871: the same claim and key twice → served twice (two twin rows; the upsert kept ONE embedding). Control B: no role of seven may execute the prototype (`42501 … schema app`); `POST /rpc/rig_require_approval` → `404 PGRST202`. | **D1867 stands unchanged.** Run 2's proofs and Run 9's live proof assert the 403 body verbatim and a malformed key's `PT412`. | 0242 |
| **D1893** | 1 | Rig 35a (iv): the refusals the guard's predicate makes. | The rig's added arm *"the run belongs to another agent"* was **uninformative**: `UPDATE app_private.workflow_run SET agent_id = <another>` was refused by a constraint (psql rc 3), nothing changed, and the call was served. The guard's `r.agent_id = v_agent` member was therefore NOT exercised on the stack. | **Owed to Run 2's `test_a_pending_rejected_expired_or_foreign_decision_is_refused`**, which sets `request.jwt.claims` and `app.agent_id` in SQL for a SECOND agent holding the first agent's claim (no forged token needed). A proof that cannot see the foreign case is D1773's shape. | 0242 |
| **D1894** | 1 | Rig 35a drives `tasks-approval` with an embedding. | **The plane types `p_embedding` as a STRING** (the vector literal): attempt 2 passed a JSON list, the tool schema refused it `string_type` BEFORE any approval check, and the loop classified that as `unclassified_refusal`, failed the step and compensated the run. Argument validation precedes the gate, so an approval is never asked for an invalid call. | Every proof and trip script passes the embedding as the literal text `"[…]"`, as Session 33's do. No product change. | — |
| **D1895** | 1 | D1861: `apg dev up` ~10–16 s; `propose` reads its `migrations applied` line; it refuses when an environment is up. | Rig 35b: `bin/dev.sh up` exit 0 in **22.5–29.4 s** (three runs); its line is `dev: 39 migrations applied as apg_fixture_alpha_dev_migration_user` — **39 is the whole cluster (36 release + 3 set), not the set**; a second `up` while up → **exit 2**, *"… is already up (since …); `apg dev reset` rebuilds it, `apg dev down` removes it"*; `status` while up → 0; `status` after `down` → **exit 4**, *"no development environment; `apg dev up` creates one"*. `sql_surface.final_surface` over the example set → functions `{set_note_embedding}`, views `{note_embeddings}`. | `propose` checks `bin/dev.sh status` first (0 = up → refuse, exit 2, naming `apg dev down`; 4 = none → proceed); records the dev line verbatim and the SET's count from the set itself, never from the line; the record's `seconds` is measured, never predicted. | 0243 |
| **D1896** | 1 | D1874: whether the edge's per-source bucket is shared across routers is unmeasured. | Rig 35c (the pinned Traefik v3.7, `apg-rate-limit` copied verbatim, two routers, backend `python3 -m http.server` in the pinned **Python runtime image** — the auth image's own base, not the auth image the plan named): 5/s each for 10 s → 0 429s (control); **15/s each (30/s total) → 0 429s on either**; 25/s to `a` alone → 11 429s of 250; 25/s to `a` with 5/s to `b` → `a` 11 429s, `b` 0. **The bucket is per router** (per source within it). | F7's neighbour probe may probe both projects AT ONCE at ≤ 4 req/s each (≤ 8 total from the host) — no alternation. | — |
| **D1897** | 1 | D1875: *down* is a transport error or an edge 404/502/503/504; rig 35d fixes the statuses and bodies. | Rig 35d (Traefik's Docker provider, the socket mounted directly — a rig): a steady 200 for 30 s (control, p50 7.2 ms); on `stop`, **2 × `502 Bad Gateway` and 1 transport timeout (the probe's 1-s timeout), then `404 page not found`** (Traefik's body) until the backend returned; on `start`, 1.3 s of 404 then 200; on `up --force-recreate`, **502 ×3, 1 timeout, 404 ×27, then 200: a 3.1-s gap at 0.1 s, 3.5 s at 0.5 s**. A request for a host NO router matches answers the same `404 page not found`. | The probe's *down* is exactly: a transport error, or 502/503/504, or a 404 whose body is `404 page not found`. Its pre-trip control must read 200 on every class first, so a misspelt host is never read as an outage (the two 404s are identical). Resolution 0.5 s per class loses ≤ 0.5 s per edge of a window; stated in the envelope rows. | — |
| **D1898** | 1 | Rig 35e: *"as a non-root WSL user"*, the sampler resolves the container's cgroup through `/proc/<pid>/cgroup` + `mountinfo`. | **The workstation's Docker is Docker Desktop**: its containers' pids live in the engine VM, and `/proc/<pid>/cgroup` is `No such file` from WSL (first form). Second form: the sampler as **uid 1000, `--cap-drop ALL`, `no-new-privileges`**, in the engine VM's pid namespace. Inside a PRIVATE cgroup namespace `/proc/<pid>/cgroup` reads `0::/../<id>` — relative to the reader's own namespace; with the host's namespace, `/docker/<id>`. Measured: 133 samples, cadence median 100.4 ms, max 100.9 ms, millisecond stamps distinct; base 4.3 MiB, the 100-MiB block seen from the first sample after it was touched (104.5 MiB) and held **2.01 s** (the script's 2 s); `docker stats` 4.23 → 104.4 MiB against the sampler's 4.3 → 104.5. | `s35-r10-sampler.py` runs on the HOST as `op`, never inside a container (so no cgroup namespace makes the path relative), and resolves the file across EVERY cgroup2 mount `/proc/self/mountinfo` lists, recording which held it. D1876's method stands. | — |
| **D1899** | 1 | THR-CHANGE's interim requirement: *"`DBX-…` the release lock's requirement (grep `verify_lock`'s proof)"*. | There is no `DBX` family. The proof that a set's lock is frozen and verified apart from the release's is `test_project_migration_sets.py::test_the_project_lock_is_frozen_and_verified_apart_from_the_release_lock`, held by **`TEN-SET-001`**. | `THR-CHANGE` cites `TEN-SET-001` and that node until Run 9 rewrites the cells to the `GOV-*` ids (D1816's shape). | — |
| **D1900** | 1 | D1878: *"pgbouncer, postgrest and docs are long-running and unbounded … the eleven short-lived services exit"*; `doctor capacity`'s `unbounded` falls **10 → 0** once the three and the edge are bounded; §0 attributes the 10 to *"2 projects x pgbouncer, postgrest, docs + the edge's two"* (D1710). | **Sheet E0: the 10 is 4 per project + the edge's 2** — `pgbouncer`, `postgrest`, `docs` AND **`edge-probe`**, which ADR 0222 classed among the one-shots, probes and clients (`compose.yaml:71-98`: a literal `pids_limit: 64`, no `cpus`, no `mem_limit`) but which is the health route's server (`restart: on-failure:5`) and was RUNNING on both projects (peak 51.51 / 49.42 MiB, 9 pids). §0's *2 × three + 2* sums to 8. Bounding the three and the edge would leave `unbounded` at **2**, and the threat model's sentence false by one service per project. | **`edge-probe` joins Run 5's set**: `config.SERVICE_MEMORY_LIMITS_MB` carries FOUR services (`EDGE_PROBE_MEMORY_LIMIT`, 224m by ADR 0244's rule); its `pids_limit` stays the literal 64, no `cpus`. `test_every_long_running_service_carries_a_memory_limit` reads `edge-probe` as long-running (`restart` other than `"no"`, a profile that a deploy starts), so the proof cannot pass with it left out. `unbounded` 10 → 0 stands as the prediction, READ on the trip. | 0244 |

---
## 2. What the session adds to `tests/acceptance-registry.yaml`

**One new family, `GOV`** (D1891): the regex at
`tests/contract/test_acceptance_registry.py:101` gains `GOV`, and the family
paragraphs (after Session 34's at `:98-100`) gain one sentence: *Session 35
(ADR 0242-0245) adds `GOV` for what a proposed change to a project's set is,
who records its review, and what a host refuses to apply without one; the
database half of approval extends `AGT-APPROVE`, the bounded edge `NODE-LIMIT`,
and the diagnostic account's reach is `OPS-DIAG`.* **Ten requirements, ten
claims, all `target_session: 35`, all P0 — seven offline, three host.** Every
requirement belongs to a claim (D697); a new requirement gets a claim of its
own (ADR 0089, D1150). **Node ids below are proposed; Run 9 writes what the
runs actually wrote, read out of the tree with `pytest --collect-only -q`**
(D1236, D1762). Registry entries cannot be committed before Run 9 moves
`CURRENT_SESSION` (D690): the runs write the proofs and this table; Run 9 lands
the YAML **with a `# Session 35 (ADR 0242-0245)` banner comment** (Session 34's
block has none, `:5437`).

| Requirement | What it states | Offline node ids (proposed) | Live half |
|---|---|---|---|
| `AGT-APPROVE-003` | Migration 0037 creates `app.require_approval(p_tool)`, SECURITY DEFINER, owned by the object owner and executable by NO role; called from a definer function it returns for a caller with no agent identity, and for an agent only when the `apg_approval` claim names the tool, the `Idempotency-Key` header equals the claim's key, and an `approved` decision for that tool and key exists on a `running` run of that agent — otherwise `PT403 approval_required` and the caller's write does not happen; the example set's `0004` makes it `set_note_embedding`'s first statement; `mcp-contract.sh check --project` refuses a gated RPC tool whose function does not call it first | `tests/contract/test_approval_in_database.py::test_require_approval_is_executable_by_no_role`, `::test_a_caller_with_no_agent_identity_passes`, `::test_an_agent_without_a_claim_is_refused_and_nothing_is_written`, `::test_a_claim_for_another_tool_is_refused`, `::test_a_key_that_differs_from_the_header_is_refused`, `::test_a_pending_rejected_expired_or_foreign_decision_is_refused`, `::test_a_decision_on_an_ended_run_is_refused`, `::test_an_approved_claim_on_a_running_run_passes`, `::test_every_refusal_is_one_sentence`, `tests/contract/test_approval_gate.py::test_a_gated_rpc_that_does_not_call_the_guard_first_is_refused`, `::test_a_guard_after_another_statement_is_refused`, `::test_a_gated_release_function_is_reported_never_refused`, `::test_the_render_reports_and_never_refuses`, `::test_the_example_projects_gated_function_calls_the_guard`, `tests/contract/test_project_migration_sets.py::test_the_example_sets_fourth_migration_adds_only_the_guard` | — (offline claim `approval_in_database`) |
| `AGT-APPROVE-004` | On the deployment: an agent holding `note_embeddings:write` that calls `POST /rpc/set_note_embedding` on beta DIRECTLY with its own token is refused 403 and no embedding is written; the note's owner calling it directly is served; an approval workflow's released call is served once (Session 33's `workflow_approval_live` passing again on 1.13.0 is part of this claim's evidence, and the proof reads its audit) | — | `tests/deployment/test_session35_governance.py::test_an_agents_direct_call_to_a_gated_rpc_is_refused_by_the_database`, `::test_the_owners_direct_call_is_served`, `::test_the_approved_call_through_the_plane_is_served_once` (host claim `approval_in_database_live`) |
| `GOV-LINT-001` | `migrations.destructive_findings` names every `DROP` of a table, view, materialized view, function, procedure, index, type, sequence, trigger or policy, every `ALTER TABLE … DROP COLUMN|CONSTRAINT`, `… ALTER COLUMN … TYPE`, `… RENAME`, every `TRUNCATE` and every `DELETE` with no `WHERE`, in an up section, with its migration and object, in every spelling PostgreSQL accepts (`IF EXISTS`, quoted, schema-qualified); a commented statement and a down section are not read; a finding never refuses; the example set has none | `tests/contract/test_change_proposal.py::test_each_destructive_shape_is_named_with_its_object`, `::test_every_accepted_spelling_is_read`, `::test_a_commented_statement_or_a_down_section_is_not_a_finding`, `::test_a_finding_never_refuses_the_lint`, `::test_the_example_set_has_no_destructive_statement` | — (offline claim `destructive_lint`) |
| `GOV-PROPOSE-001` | `bin/migrate.sh propose --project M --by NAME` writes `projects/<slug>/proposals/<set_digest>.json` (the render's `lock_sha256`, one function), naming the set's versions, the lint result, the destructive findings, the dev-cluster apply (exit, migrations applied, seconds, and its limits), the set's final `api` surface against the reviewed contract, the approval-gate check, the harness's cases (never results), the committed capability contract's digest, the release it was proposed against, and `declared_by`; it refuses while a dev environment is up, when the lint or the approval-gate check fails, and when the file exists; everything but its times is deterministic | `tests/contract/test_change_proposal.py::test_the_digest_is_the_renders_lock_sha256`, `::test_propose_records_every_reading_and_its_limits`, `::test_propose_refuses_while_a_dev_environment_is_up`, `::test_propose_refuses_an_unguarded_gated_function`, `::test_propose_refuses_an_existing_proposal`, `::test_a_proposal_is_deterministic_but_for_its_times`, `::test_the_example_sets_committed_proposal_names_its_lock`, `tests/contract/test_dev_environment_cluster.py::test_propose_applies_the_set_from_empty_through_dev_up` | — (offline claim `change_proposal`) |
| `GOV-APPROVE-001` | Project manifest schema 8 admits `migrations.approvals_required: 0|1` beside a `set`, forbidden below 8 and without a set; `bin/migrate.sh approve --project M --proposal DIGEST --by NAME` writes `<digest>.approval.json` naming the proposal file's own sha256 and a declared name, and refuses the proposer's name, a missing proposal and an existing approval | `tests/contract/test_project_manifest.py::test_schema_eight_admits_approvals_required_beside_a_set`, `::test_seven_forbids_approvals_required`, `tests/contract/test_change_proposal.py::test_approve_refuses_the_proposers_own_name`, `::test_approve_names_the_proposal_by_its_bytes`, `::test_approve_refuses_a_missing_proposal_or_an_existing_approval`, `::test_the_records_say_their_names_are_declared` | — (offline claim `proposal_approval`) |
| `GOV-APPLY-001` | `migrate.py up` on a project set with a version the project ledger lacks refuses (exit 5, one of four fixed sentences) without a proposal for the set being applied, with one naming another set, and — under `approvals_required: 1` — without an approval naming that proposal's bytes by another name; a set with nothing pending needs nothing; the release set is never gated; `status` prints the proposal line; deploy step 6 relays the sentence | `tests/contract/test_proposal_gate.py::test_a_pending_set_without_a_proposal_is_refused`, `::test_a_proposal_for_another_set_is_refused`, `::test_an_unapproved_proposal_is_refused_when_approvals_are_required`, `::test_an_approval_by_the_proposer_or_for_other_bytes_is_refused`, `::test_a_set_with_nothing_pending_needs_no_proposal`, `::test_the_release_set_is_never_gated`, `::test_status_prints_the_proposal_line`, `::test_deploy_relays_the_gates_sentence` | — (offline claim `proposal_gate`) |
| `GOV-APPLY-002` | On the deployment: beta's project ledger's newest version is the committed proposal's newest; its deployed document's `migrations.project_set.lock_sha256` equals the proposal's `set_digest`; `migrate.sh --runtime status` prints the proposal line | — | `tests/deployment/test_session35_governance.py::test_the_applied_set_is_the_proposed_one` (host claim `proposed_set_applied`) |
| `NODE-LIMIT-002` | The edge's `traefik` and `docker-socket-proxy` carry `mem_limit`, `pids_limit` and `cpus` at the values ADR 0244 records; pgbouncer, postgrest and docs carry `mem_limit` from `config.SERVICE_MEMORY_LIMITS_MB`; every long-running service in `compose.yaml` carries a `mem_limit` | `tests/contract/test_process_limits.py::test_the_edge_plane_is_bounded` (replaces `test_the_edge_plane_is_untouched`, ADR 0244), `::test_every_long_running_service_carries_a_memory_limit`, `::test_the_three_new_memory_limits_are_rendered_from_config`, `tests/contract/test_compose_contract.py` (the edge pins at `:1173-1220`, unchanged and green) | — (offline claim `every_service_bounded`) |
| `NODE-LIMIT-003` | On the host: both edge containers report a non-zero `HostConfig.Memory`, `PidsLimit` and `NanoCpus`, and `doctor capacity` counts no running compose container unbounded | — | `tests/deployment/test_session35_governance.py::test_the_edge_containers_are_bounded_on_the_host`, `::test_no_running_compose_container_is_unbounded` (host claim `every_service_bounded_live`) |
| `OPS-DIAG-001` | `apg-diag`'s log allowlist is exactly `postgres pgbouncer postgrest docs edge-probe dbmate auth storage mcp`; its redaction masks a JSON-quoted secret key's value as well as the three existing shapes, over lines in the three new services' real log shapes; the 200-line cap stands | `tests/contract/test_diagnostic_surface.py::test_the_log_allowlist_is_exactly_these_services`, `::test_a_json_quoted_secret_is_redacted`, `::test_the_new_services_log_lines_are_redacted`, `::test_the_log_cap_is_two_hundred_lines` | — (offline claim `diagnostic_reach`) |

**Expected counts** — Run 9 counts them from the tuples, never from this prose
(D1628): requirements **281 → 291**, `CLAIMS` **188 → 198**, `OFFLINE_CLAIMS`
**53 → 60**, ADRs **241 → 245**.

**Claims** (`src/agentic_postgres/evidence_claims.py` `CLAIMS`, in a block
commented *Session 35 (ADR 0242-0245)*): offline — `approval_in_database:
("AGT-APPROVE-003",)`, `destructive_lint: ("GOV-LINT-001",)`,
`change_proposal: ("GOV-PROPOSE-001",)`, `proposal_approval:
("GOV-APPROVE-001",)`, `proposal_gate: ("GOV-APPLY-001",)`,
`every_service_bounded: ("NODE-LIMIT-002",)`, `diagnostic_reach:
("OPS-DIAG-001",)` — **these seven in `OFFLINE_CLAIMS`**, with the per-session
assertion in `test_session_thirty_five_gate_modes.py` (D1237: assert THESE
seven are in the set, never the set's size). Host —
`approval_in_database_live: ("AGT-APPROVE-004",)`, `proposed_set_applied:
("GOV-APPLY-002",)`, `every_service_bounded_live: ("NODE-LIMIT-003",)` — not
declared. `CLAIM_INTRODUCED_IN` (`tests/contract/test_evidence_claims.py:953`,
after Session 34's rows `:1157-1175`) gains ten rows at 35.

**Existing entries that move** (each a passing proof made stricter or a
sentence corrected, never weakened — CLAUDE.md §6):

- **The entry that holds `test_the_edge_plane_is_untouched`** (grep its node id
  in `tests/acceptance-registry.yaml` before Run 5; `NODE-LIMIT-001` is the
  likely holder) — the node id is REPLACED by `test_the_edge_plane_is_bounded`
  in Run 5, the commit that deletes the old proof (D1835's precedent: a
  registered node id with no test is refused by `test_acceptance_registry`),
  with ADR 0244 authorising the replacement.
- **`AGT-APPROVE-001`'s and `THR-APPROVAL`'s sentences** — *"approval governs
  the agent plane and workflows, not the database"* becomes *"since 1.13.0 a
  project's gated RPC checks the approval in the database too
  (AGT-APPROVE-003); a profile-added approval on a release tool remains a
  plane control"*. Grep both phrasings in the registry and `docs/` in Run 2.
- **The dev-cluster ledger pin** (`test_dev_environment_cluster.py:271-306`)
  moves to 0004's version in Run 2, in whatever entry holds it today.
- **`DX-001`** is untouched; its record is what moves (Sheet W, D1884).

**New environment gates: none.** Every live proof creates its own humans,
agents, notes and runs on `project_b` from `APG_PROJECT_B_OUTPUTS` and reads
`project_a` for the edge (both in the roster, `tests/conftest.py`). **The
Session 35 gate therefore accepts exactly the flags the Session 34 gate
accepts** — the derivation diff proves it (D1133).

---

## 4. Irreversible operations

| Operation | Where | What makes it safe |
|---|---|---|
| Migration **0037** written and frozen into `migrations/released.lock.json` | Run 2 | `bin/migrate.sh freeze-lock` is the only writer; the proofs apply every released migration as `migration_user` on a fresh container before the freeze; its down is `AP900`; **once applied on the host it is the floor** (ADR 0162 §3), and **0034–0036 are never amended** (D912). It creates ONE function and touches no table, column, enum or `api` object |
| The example set's **0004** frozen into `projects/example/migrations/released.lock.json` | Run 2 | `bin/migrate.sh freeze-lock --project project.example.yaml --follows 20260912120031` (ADR 0240; without `--follows` the freeze exits 5, D1833); the version sorts after `20260930120003`; `CREATE OR REPLACE` with the SAME signature keeps 0001/0002's grants (D1834's two proofs, extended); applied on beta by F3's deploy — **only because a committed proposal names this lock** |
| The proposal and approval files for the example set committed under `projects/example/proposals/` | Run 4 (proposal), Run 8 (the operator's approval) | They are records: nothing reads them but `migrate.py up` and `status`; a later change to the set's lock makes them stale, which the gate refuses — Run 8's commit is the last to touch `projects/example/migrations/` in this session (§9) |
| Project manifest schema 8 | Run 3 | Versions 1–7 still load unchanged (no migrator exists or is needed); `project.alpha.yaml` (4) and `project.beta.yaml` (7) live only on the host and are not edited this session |
| The edge's limits in `infra/edge/compose.yaml` | Run 5 (code), Run 10 Sheet F4 (the recreation) | Values from Sheet E0's readings with a 4× margin; ADR 0244 first; the recreation is `sudo bin/edge.sh --host host.yaml restart` on its own sheet, the probe on both projects, `edge-network.sh reconcile` inside `do_up` (`bin/edge.sh:236`); **if Traefik does not come back healthy, `sudo bin/edge.sh --host host.yaml up`** (the systemd unit's own path) and §9's stop |
| `mem_limit` on pgbouncer, postgrest, docs | Run 5 (code), F2/F3 (the recreations) | 4 × Sheet E0's `memory.peak`, floor 64 MiB; admission unaffected (it charges `unreclaimable_mb`, D767 — re-read in Run 5); the deploys recreate the three and the probe reads what REST callers see |
| `apg-diag` re-installed at `/usr/local/bin/apg-diag` | Run 10 Sheet F4b | ADR 0245 first; the sudoers file is unchanged (`visudo -c` not needed); the agent reads `apg-diag logs auth` as `apg-agent` after |
| `CURRENT_SESSION` 34 → 35; `VERSION` 1.12.0 → 1.13.0 | Run 9 | All-or-nothing (D690); every `target_session: 35` entry in the same commit; the upgrade guide gains a `1.13.0` row; `README.md:7` moves; every `--session 34` / `--through-session 34` literal on the documented path moved and counted per file (D678/D1484) |
| `bin/session-35-check.sh` | Run 9 | Derived from 34's by diff (D1482, D1885); header and usage rewritten whole (D1488, D1883); `SHELL_COMMANDS` gains it and `chmod 755` before `git add` (D1014, D1188); the verbatim `run_suite` selector kept (D1242); the flag diff empty |
| Deploy `--through-session 35` on alpha, then beta | Run 10 | `upgrade plan` OK first; alpha first; one sheet per outcome (D1510); under `script(1)`; **0037 applied** (ledger 36 → 37; beta 37 + 4 after `0004`, which applies only with the proposal) |
| Probe humans, agents, notes and runs written on both projects by the live proofs and the neighbour sitting | Run 10 | Humans deleted where no FK refuses; agents revoked (D1700); notes deleted by canary title in the cleanup (root `psql`, D1547); runs left as the substrate's record and counted in the Done |
| Tag `1.13.0` on the deployed commit | Run 10 | After the merge exits 0 or 5 for the expected reasons only (§7); `release-reading --ref <deployed sha>` first; D1641's method stated in the tag if an instrument moves |

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
caller in the same commit** (D1680 — 0037 grants nothing, and says so); **a run
that adds a migration re-renders BOTH example projects** before its targeted
list (D1678: `./deploy.sh --project project.example.yaml --render-only` and the
same for `project.second.example.yaml` — read `deploy.sh --help` for the exact
spelling); **a run that moves the app OpenAPI document regenerates the example
client** (D1690 — no run here is expected to; if one does, `bin/apg.sh generate
--project project.example.yaml` and `test_client_typescript`,
`test_generate_command`, `test_studio_command`, `test_client_ir`); **a run that
adds or removes a `bin/` command or verb runs `test_cli_contract` and `git
add`s the command first** (D1014, D1188 — `propose`/`approve` are VERBS of an
existing command: `COMMANDS_WITH_VERBS` in `test_cli_contract.py` is read, and
`bin/migrate.sh`'s case at `:128` is where they live); **a run that touches a
documentation page runs `test_documentation_index` and
`test_session12_documented_path`**; **every new test module carries
`pytestmark` before its first test** (D1240) and the sweep-selector guard
(D1242) is in the targeted list of any run that adds one.

**The Docker-backed modules are the slow ones** (~3 min each: they build a real
cluster). Keep two lists per run: the fast modules after each edit, the
Docker-backed ones ONCE just before the commit (the user's standing request).

### Run 1 — the measurements, Sheet E0, the `THR-*` rows, and ADRs 0242–0245

**Documentation only. Push, say it is pushed, read NO CI verdict.**

**Reads first** (agent, no edits): `migrations/templates/0035-workflow-gates.
sql:59-123` and `:780-1110`; `0036-connectivity.sql:1-40`, `:190-270`,
`:1030-1050` (the emitter's shape and grant — the precedent); `0029-agent-
idempotency-keys.sql:130-240`; `0018-agent-read-plane.sql:107-271`;
`projects/example/migrations/templates/0001-note-embeddings.sql` and
`0003-note-embedding-events.sql` whole; `services/auth-api/app/mcp_tools.py:
540-670`, `:1110-1135`; `mcp_upstream.py:1-20`, `:240-415`;
`services/auth-api/app/service.py:540-600`; `src/agentic_postgres/
migrations.py:160-200`, `:440-560`, `:760-940`; `sql_surface.py` whole;
`bin/migrate.py` whole (590 lines) and `bin/migrate.sh` whole;
`bin/dev.py:290-470`; `infra/edge/compose.yaml` whole;
`infra/edge/dynamic/baseline.yaml` whole; `infra/edge/traefik.yaml` whole;
`bin/apg-diag.sh:55-190`; `capacity.py:60-120`, `:560-706`;
`docs/decisions/0071-*.md`, `0155-*.md`, `0207-*.md`, `0213-*.md`, `0222-*.md`,
`0231-*.md`, `0235-*.md`; this plan's §1. Then re-run the deployable-diff filter
named in §0 and write its answer.

**The rigs.** Each is a script written with the Write tool to
`\\wsl$\Ubuntu\tmp\rig35\rig35x.py` (or `.sh`) and copied to the scratchpad;
each names its images by digest (`versions.lock.json`; read
`bin/lock-versions.sh --help` for the reader); each has a control; each prints
its own exit status from inside. **Sessions 33 and 34 ran their rigs as ONE
script on ONE stack** (`apg dev up --project project.example.yaml` + the pinned
PostgREST verifying the auth application's JWKS + both application modes run
from the checkout as subprocesses with the image's own entrypoint, each
environment built from nothing — Session 34 Run 1's `**Done.**`); copy that
method for 35a and 35b and say so. 35c–35e run on the workstation's Docker
beside it. Any Python that imports `agentic_postgres` needs `PYTHONPATH=src`.
**A heredoc inside `wsl bash -lc "…"` is forbidden (CLAUDE.md §1)** — every
Python the rig runs inside a container is a file mounted read-only.

| Rig | Subject | Method | Control | Owes |
|---|---|---|---|---|
| **35a** | The approval claim and the key header ARRIVE in SQL, and the guard's body decides as D1867 says | On the stack: as `postgres`, `SET ROLE <object_owner>`; create a scratch table `app.rig_gate_writes(id bigserial, arrived jsonb)` (FORCE RLS off — a rig) and a PROTOTYPE `app.rig_require_approval(p_tool text)` with D1867's body verbatim, `REVOKE ALL … FROM PUBLIC`; a prototype project function `api.rig_gated(p_note uuid)` SECURITY DEFINER as the owner whose FIRST statement is `PERFORM app.rig_require_approval('set_note_embedding')` and whose second inserts `jsonb_build_object('claims', current_setting('request.jwt.claims', true)::jsonb -> 'apg_approval', 'key', current_setting('request.headers', true)::jsonb ->> 'idempotency-key', 'agent', current_setting('app.agent_id', true))` into the scratch table; `GRANT EXECUTE` to `authenticated` and `agent_writer`; `NOTIFY pgrst, 'reload schema'`. An agent (`agent_writer`, scopes `["note_embeddings:write"]`) and its owner (a human). Arms: **(i)** the agent's OWN token (`/auth/agent-token`) → `POST /rpc/rig_gated` with `Idempotency-Key: rig35-k-0001` → record status, body, SQLSTATE, rows (expect 403 `PT403`, 0 rows); **(ii)** a run + an approval row in the 0035 shape for that agent (`workflow_enqueue` of `tasks-approval`… or rows inserted as the superuser in the exact column set — read `0035:98-113` and say which) set `approved`; a STEP token minted by the application's own `step_token(agent_id, approval_id=…)` in a subprocess with the auth mode's settings; `POST` with header key == the claim's key → record status and the ROW's `arrived` (expect 200, `claims` carrying `{id, tool, key}` exactly, `key` the header, `agent` the agent's id); **(iii)** the same token, a different header key → 403, 0 new rows; **(iv)** the approval set `rejected` → 403; the run set `cancelled` with the approval `approved` → 403; **(v)** the owner's human token → 200 and `agent` empty; **(vi)** through the PLANE (auth app in mcp mode, `tools/call` of a rig tool is not possible — the lock has no such tool): instead drive `set_note_embedding` itself after installing the prototype guard into a scratch copy of `api.set_note_embedding` (as the owner, `CREATE OR REPLACE` with the guard first) and replay Session 33's approved-run flow's final call (step token + `tools/call set_note_embedding` with the claim's key) → record served and one row | **Control A**: `api.rig_ungated` — the same body without the guard — called with the agent's own token → **200 and a row** (rig 33b's reading reproduced on this stack); **Control B**: `has_function_privilege(<role>, 'app.rig_require_approval(text)', 'EXECUTE')` false for `authenticated`, `agent_writer`, `agent_reader`, `anon`, `auth_service`, and `SELECT app.rig_require_approval('x')` as each → `42501` | D1867's premise *measured* (the claim and header in SQL; the refusal's SQLSTATE and PostgREST status); D1871 (a second call with the same claim and key → record: served again, and the row count); the exact error body PostgREST returns for `PT403` (Run 2's live proof asserts it) |
| **35b** | `apg dev up` as the proposal's shadow; the surface reading | `bin/dev.sh up --project project.example.yaml` (after the render): record exit, every line, the exact `migrations applied` line, wall time; a second `up` → record exit 2 and its sentence; `bin/dev.sh status`; `bin/dev.sh down`; `status` again. `PYTHONPATH=src python3 -c` a script FILE calling `sql_surface.final_surface` over the example set's rendered templates → record the functions and views it returns | `status` after `down` reads *not up* | D1861's exit codes and the line `propose` parses; D1859's surface reading on the example set (expected: `set_note_embedding` and the `note_embeddings` view) |
| **35c** | Is the edge's per-source rate limit shared across routers? | The pinned Traefik image (the edge's digest from `versions.lock.json`) with a FILE provider carrying `apg-rate-limit` copied VERBATIM from `infra/edge/dynamic/baseline.yaml`, and two routers (`Host(a.rig)`, `Host(b.rig)`) each with that middleware, to one backend (`python3 -m http.server` in the auth image built from this checkout — Session 34 rig 34b's `apg-rig34-auth:local` method, fifteen build arguments from `versions.env`). A Python driver on the workstation at a fixed schedule: **(i)** 15 req/s to EACH host for 10 s (30/s total) → record 429s per host; **(ii)** 25 req/s to `a.rig` alone → 429s | **(iii)** 5 req/s to each (10/s) → **zero 429s** | D1874: shared or per router — decides whether F7's probe runs both projects at once at 4 req/s each or alternates |
| **35d** | What a caller sees through Traefik's Docker provider when a backend is stopped, started, and recreated; the probe's resolution | The pinned Traefik with the DOCKER provider (socket mounted directly — a rig; production reads it through the proxy, whose semantics for `containers` are the same allowlisted GET) and a labelled backend container on a rig network; the probe loop (the text `s35-r10-probe.py` will carry) at 0.1 s: **(i)** `docker stop` the backend → record every status and body until 30 s; **(ii)** `docker start`; **(iii)** `docker compose up -d --force-recreate` of a one-service compose file → record the gap (first non-200 to first 200 again) | a steady 200 for 30 s with the backend untouched | D1875's definition of *down* (the statuses and Traefik's bodies: `404 page not found`? `502`? `503`?) and the gap's resolution at 0.1 s and at 0.5 s |
| **35e** | A sub-second sampler an unprivileged user can run | As a non-root WSL user: a container running `python3 -c` a FILE that allocates 100 MiB for 2 s then frees it; the sampler (the text `s35-r10-sampler.py` will carry) resolves the container's cgroup through `/proc/<pid>/cgroup` + `/proc/self/mountinfo` (D1739) and reads `memory.current` every 0.1 s with `time.time_ns()` stamps → record the rise's first sample and the fall's | `docker stats --no-stream` before and during agree with the sampler within 5 MiB | D1876: the sampler works unprivileged at 0.1 s and sees a 2-s allocation |

**Third-party facts already measured, cited and not re-run:** the plane's
transport and SSE framing (rig 32b, D1672); the plane mints its own request id
(ADR 0160, D1696); an extra claim survives every verifier (rig 33a); a direct
agent call to the ungated function is served (rig 33b, D1721); `psql -c` does
not interpolate `-v` (D1684) — **every psql statement goes through `-f -`**;
`ALTER TYPE … ADD VALUE` then use in a DEFAULT is `55P04` (rig 33e — 0037 adds
none); `urllib`'s redirect and error shapes (rig 34b, D1812–D1813); the app
schema refuses every request role `42501` (rig 34a, D1814).

**Sheet E0 — the host's readings, before any limit is written** (the operator
runs ONE `sudo` line; reads only; nothing restarts). The agent stages
`/home/op/s35-r1-e0.sh` as `op` over SSH (PATH exported; the script TEES its
own transcript to `/home/op/s35-r1-e0.txt` — hand it as `sudo bash <script>`,
never inside `script(1)`, D1771). It prints, for every RUNNING container
carrying `com.docker.compose.project` (both projects' and the edge's): name,
`State.StartedAt`, `HostConfig.Memory`, `HostConfig.PidsLimit`,
`HostConfig.NanoCpus`, and from its cgroup directory (resolved from
`docker inspect --format '{{.State.Pid}}'` → `/proc/<pid>/cgroup`)
`memory.current`, `memory.peak`, `memory.stat`'s `anon`, `pids.current`,
`pids.peak` — **printing `absent` for a file the kernel does not provide,
never a zero** (ADR 0195); then `nproc`, `uname -r`, `free -m`, `df -h /`,
`sha256sum infra/edge/compose.yaml` in the checkout, and LAST `bin/doctor.sh
capacity --host host.yaml` (its ceilings line and `unbounded` count — the same
script is re-run on Sheet F4b as the after-reading). Every child's stdin is
`/dev/null` (ADR 0218's rule, as `s34-r10-c1.sh` did). The operator runs, at a
terminal, nothing after it:

    sudo bash /home/op/s35-r1-e0.sh

The agent fetches the transcript as `op` and writes the table into this run's
`**Done.**`: for `traefik`, `docker-socket-proxy`, and each project's
`pgbouncer`, `postgrest`, `docs` — `memory.peak`, `pids.peak`, how long the
container has run (the peak's window) — and the **values ADR 0244 records**:
memory = max(4 × `memory.peak` rounded UP to a multiple of 32 MiB, 64 MiB);
pids = max(4 × `pids.peak`, 64); cpus `"1.0"`; one value per service NAME (the
larger of alpha's and beta's). **If `memory.peak` or `pids.peak` reads
`absent`: STOP** (§9) — the limit is re-planned against a sampled reading, not
guessed.

**The `THR-*` rows, before any code** (D1527's rule). In
`docs/threat-model.md`'s nine-column table (header `:19`):

- **`THR-CHANGE`** (new, after `THR-DELIVERY`). *Attacker capability*: a
  contributor or operator — or an accident — applying a project migration set
  nobody reviewed, or one edited after it was reviewed, to a deployment.
  *Protected asset*: the project's data and its reviewed contract. *Prevention*:
  a host applies a project set with a pending version only when a COMMITTED
  proposal names the set's digest (the lock's sha256), and, under
  `approvals_required: 1`, a committed approval names the proposal's bytes by a
  second declared name (ADR 0243); the proposal carries the lint, the
  destructive findings, a from-empty apply, the reviewed-surface reading and the
  approval-gate check. *Detection*: `migrate.sh --runtime status`'s proposal
  line; the deploy's step 6 sentence; the committed history of
  `projects/<slug>/proposals/`. *Residual risk*: **the names are declared, not
  authenticated** — one person can commit both records, and root can do
  anything; a from-empty apply says nothing about existing rows; a
  capability-contract change is reported, not refused (D1866). *Acceptance
  requirement IDs*: until Run 9, `DBX-…` the release lock's requirement (grep
  `verify_lock`'s proof in the registry) — D1816's shape: cite what holds
  today, Run 9 rewrites the ID cells to `GOV-PROPOSE-001`, `GOV-APPROVE-001`,
  `GOV-APPLY-001`, `GOV-APPLY-002`. *Target session*: 35.
- **`THR-APPROVAL`** — *Residual risk* cell: left as it is in Run 1 (it is true
  until 0037 is applied); **Run 2 rewrites it** to *"since 1.13.0 a project's
  gated RPC refuses an agent's direct call in the database (AGT-APPROVE-003/004);
  a profile-added approval on a release tool remains a plane control (D1869);
  the guard binds a call to a decision, a tool and a key, and does not make the
  project function idempotent (D1871)"*, keeping its last two sentences.
- **`THR-NOISY-NEIGHBOUR`** — unchanged in Run 1; **Run 11 rewrites its
  residual cell** with the measured figures (the sentence *"has not been
  measured"* is removed only by a number).

**ADRs written after the rigs, before any code**, each indexed in
`docs/decisions/README.md` after `0241` (`:307`) as `| [NNNN](file.md) | Title
| 35 | Accepted |`, each file `docs/decisions/NNNN-kebab-title.md` with H1
`# NNNN — <Title>` and the house header (Status, Date, Session, Affects,
Related):

- **0242 — Approval is enforced in the database by a guard in `app` that a
  gated project function calls first, and a human's own write passes it.**
  Context: D1721, D1867–D1872, rig 35a. Decision: the function, its grant to
  nobody, its body and its one refusal sentence; the example set's `0004`; the
  approval-gate check (refused at `check --project` and `propose`, reported at
  render); what it does not cover (a profile on a release tool, D1869;
  idempotency, D1871; a human's `Dry-Run`, D1870). Alternatives: `api.
  require_approval` (rejected: forgeable or refused, D1779's measurement);
  withholding the RPC's grant from `agent_writer` (rejected: it would stop the
  approved path too — the plane calls as the agent); consuming the approval
  (rejected: D1871); refusing at render (rejected: an invalidated manifest, a
  major).
- **0243 — A change to a project's migration set is proposed, recorded with
  the readings that exist, and a host applies a pending set only when a
  committed proposal names it; the names in both records are declared.**
  Context: D1523, D1857–D1866, rig 35b. Decision: the digest; the record's
  members and the three readings it cannot take (upgrade class, client drift,
  harness outcomes — each said); `destructive_findings`; manifest 8's
  `approvals_required`; the gate on the act; the capability digest reported;
  the sentence *it stops an unreviewed or altered set reaching a host; it does
  not authenticate a reviewer*. Alternatives: a resolved Unix name (rejected:
  one operator account on this host; the host is not where a set is reviewed);
  records written on the host (rejected: D971/D1852 — a host checkout may not
  gain a file); a gate on the state (rejected: breaks every applied set); a
  lock-risk estimate (rejected: no reading exists — the stage plan's *"not on a
  guess"*).
- **0244 — The edge and every long-running project service are bounded in
  memory, processes and CPU, and recreating the edge is a measured act.**
  Context: D1586, D1710, D1877–D1878, Sheet E0. Decision: the values and their
  rule (ADR 0222's 4× method, memory's floor); `test_the_edge_plane_is_bounded`
  REPLACES `test_the_edge_plane_is_untouched` (CLAUDE.md §6 — authorised here);
  `config.SERVICE_MEMORY_LIMITS_MB` for the three; the recreation's sheet and
  probe. Alternatives: leaving the edge unbounded (rejected: the one shared
  container is the one no ceiling covered); a limit from prose (rejected: D770's
  rule — a measurement first).
- **0245 — The diagnostic account reads the auth, storage and MCP logs, and
  its redaction knows a JSON key.** Context: D380, D1879, THR-CONNECTOR-INPUT's
  residual. Decision: the nine services, pinned; the fourth redaction rule; the
  200-line cap unchanged; the host copy re-installed. Alternatives: a
  connector-only log reader (rejected: a second surface); structured-log parsing
  (rejected: `apg-diag` is a shell reader and stays one).

Run `pytest tests/contract/test_acceptance_registry.py tests/contract/
test_documentation_index.py -q -p no:randomly` (the ADR index and the threat
rows' requirement ids). Commit (`Session 35 Run 1: the rigs, Sheet E0, THR-CHANGE,
and ADRs 0242-0245`), push. **No CI read** — documentation only.

**Done (2026-10-01; rigs and Sheet E0 on 2026-09-30).** The deployable-diff
filter past `1.12.0` names NOTHING (10 files past the tag, none under `src/
bin/ services/ migrations/ templates/ schemas/ compose.yaml deploy.sh
VERSION`). **All five rigs ran, each with its control green**; scripts,
reports and transcripts in WSL `~/s35r1/rig35/` and the scratchpad `rig35/`
(`rig35.py` = 35a+35b on ONE stack, Session 34's method: `bin/dev.sh up` over
`project.example.yaml`, the pinned PostgREST verifying the auth application's
key set, the plane from the checkout, and the REAL loop driven in-process,
rig33g's method; `rig35cde.py` = 35c, 35d; `rig35e2.py` = 35e). **35a**
(D1892, D1893, D1894): D1867's premise holds end to end — the approved step
token's `apg_approval {id, key, tool}` and the plane's `Idempotency-Key` both
arrive in SQL as sent; the guard refuses the agent's own token **403 `PT403`
`AP403: approval_required`, 0 rows**, passes the owner, passes the approved
claim with its key and refuses every other key, no key, a rejected, expired or
cancelled decision, and an ended run (a malformed key is `PT412` first);
installed first in `api.set_note_embedding` the agent's direct call writes no
embedding while the approved plane call writes one and the run finishes
`succeeded`; no role of seven may execute it, PostgREST cannot address it; the
foreign-agent arm was uninformative and is owed to Run 2's proof (D1893); the
plane types `p_embedding` as a string (D1894). Three attempts: the first died
on `APG_CONNECTOR_KEY_FILE` (required since 1.12.0; a path with no file is the
facility off), the second on D1894. **35b** (D1895): `dev up` 0 in 22.5–29.4
s, its line counts the whole cluster (39 = 36 + 3), a second `up` exits 2,
`status` after `down` exits 4; the example set's final surface is
`set_note_embedding` + `note_embeddings`. **35c** (D1896): the edge's rate
limit is kept PER ROUTER — 15/s to each of two routers drew no 429, 25/s to
one drew 11 of 250 while its neighbour at 5/s drew none. **35d** (D1897):
*down* through Traefik is a brief `502 Bad Gateway`/transport timeout, then
`404 page not found` (the same body an unmatched host gets); a force-recreate
was a 3.1-s gap at 0.1 s, 3.5 s at 0.5 s. **35e** (D1898): the workstation is
Docker Desktop, so the sampler ran as uid 1000 with no capabilities in the
engine VM's pid and cgroup namespaces — 133 samples at a median 100.4 ms, the
2-s 100-MiB block seen and held 2.01 s, `docker stats` agreeing within 0.1 MiB;
a reader inside a private cgroup namespace reads a RELATIVE path, so the trip's
sampler runs on the host as `op`, outside any container.

**Sheet E0** (`/home/op/s35-r1-e0.sh`, the operator's one `sudo` line,
2026-09-30T19:57Z, checkout `8d655b5`; transcript `/home/op/s35-r1-e0.txt` and
WSL `~/s35r1/s35-r1-e0.txt`). 2 vCPU, kernel 7.0.0-31-generic, 3,814 MiB /
2,075 available / no swap, `/` 38 G with 21 G free; `doctor capacity` 5 ok,
4,480 MiB of ceilings, **10 unbounded**. No figure `absent`. The edge's two
had run since 2026-09-17 (13 days); the project services since
17:54–17:57Z (~2 h, most of Session 34's third sweep). `memory.peak` /
`pids.peak` and **ADR 0244's values** (rule: max(4 × peak rounded up to 32
MiB, 64 MiB); max(4 × pids, 64); the larger of alpha and beta):

| Service | alpha | beta | → `mem_limit` | → `pids_limit` |
|---|---|---|---|---|
| `traefik` (edge, current 123.02 MiB) | 149.05 MiB / 19 | — | **608m** | **76**, `cpus "1.0"` |
| `docker-socket-proxy` (edge, current 6.86 MiB) | 14.27 MiB / 12 | — | **64m** | **64**, `cpus "1.0"` |
| `pgbouncer` | 9.47 / 9 | 6.92 / 9 | **64m** | unchanged |
| `postgrest` | 26.03 / 20 | 24.52 / 18 | **128m** | unchanged |
| `docs` | 53.80 / 9 | 47.78 / 9 | **224m** | unchanged |
| `edge-probe` (D1900) | 51.51 / 9 | 49.42 / 9 | **224m** | unchanged |

Both edge limits clear 2 × `memory.current` (§9). **D1900**: the tenth
unbounded container is `edge-probe`, not counted by the plan — it joins Run 5.
Written: `THR-CHANGE` (citing `TEN-SET-001` until Run 9, D1899); ADRs **0242,
0243, 0244, 0245**, indexed. Rows **D1892–D1900**; **NEXT FREE D1901, ADR
0246.** Targeted: `test_acceptance_registry` + `test_documentation_index`, once
(result in the commit message).

### Run 2 — the database half of approval: migration 0037, the example set's 0004, the approval-gate check

**Code. Push, read CI by full SHA.**

**Read first:** `migrations/templates/0036-connectivity.sql` WHOLE (the
template this one copies: preamble, voice, the privileges block as the owner
with `RESET ROLE` below it, D285; the down block); `migrations/manifest.json`'s
last entry (the description's voice); `tests/contract/test_connectivity_
substrate.py:1-200` (the cluster fixture — COPY it, do not import it) and
`:451-470` (`test_emit_event_is_executable_by_no_role` — D1814's two-part
assertion); `tests/contract/test_migrations.py` (grep
`test_every_granted_function_has_a_caller` and `CONNECTIVITY_NOBODY`);
`tests/contract/test_database_function_signatures.py:560-640` (ADR 0175's
arity guard; `SCHEMAS` includes `app` since D1820); `tests/contract/
test_project_migration_sets.py:850-935` and `:1300-1365`; `tests/contract/
test_dev_environment_cluster.py:250-310`; `src/agentic_postgres/
capability_compiler.py:150-215`, `:690-710`; `bin/mcp-contract.sh` whole;
`src/agentic_postgres/rendering.py:2440-2500`.

1. **`migrations/templates/0037-approval-gate.sql`**, manifest entry `{version:
   "2026MMDD120037", name: "approval_gate", template:
   "templates/0037-approval-gate.sql", placeholders: ["object_owner"],
   description: <one paragraph in 0036's voice naming ADR 0242, D1867–D1872 and
   rig 35a's readings>}` — the version sorts above `20260929120036`, dated the
   day it is written. `SET LOCAL ROLE {{object_owner}};` … `RESET ROLE;`, down
   `AP900`. Its whole content: the comment block (why `app`, why nobody, why a
   human passes, what it does not cover), **`CREATE FUNCTION
   app.require_approval(p_tool text) RETURNS void LANGUAGE plpgsql STABLE
   SECURITY DEFINER SET search_path = pg_catalog, pg_temp`** with D1867's body
   exactly (`STABLE` only if rig 35a showed `agent_idempotency_key()` is itself
   `STABLE` or `VOLATILE`-safe inside a `STABLE` caller — read its declaration;
   if it is `VOLATILE`, declare the guard `VOLATILE` and say why in the
   comment), `COMMENT ON FUNCTION`, **`REVOKE ALL ON FUNCTION
   app.require_approval(text) FROM PUBLIC;` and NO GRANT**. Read how 0036
   raises and copy the form: `RAISE EXCEPTION 'AP403: approval_required' USING
   ERRCODE = 'PT403';`. No `NOTIFY pgrst` (no `api` object moves). Freeze:
   `bin/migrate.sh freeze-lock`; `bin/migrate.sh verify-lock`.
2. **`projects/example/migrations/templates/0004-approval-in-the-database.sql`**
   and its manifest entry (version `2026MMDD120004`, after `20260930120003`, in
   the set's `YYYYMMDD12000N` convention; placeholders `["object_owner"]`):
   `CREATE OR REPLACE FUNCTION api.set_note_embedding(p_note_id uuid,
   p_embedding extensions.vector)` — **0003's body byte for byte** with ONE
   statement added as the first after `BEGIN`: `PERFORM
   app.require_approval('set_note_embedding');`. No grant restated (the OID's
   grants stand, `0003:12-19`), no `DROP`. A comment above it: why first
   (nothing — not even the ownership check — runs for an unapproved agent), and
   that the tool name is the capability's name. Freeze: `bin/migrate.sh
   freeze-lock --project project.example.yaml --follows 20260912120031` (ADR
   0240; D1833 measured the freeze exiting 5 without it).
3. **`src/agentic_postgres/approval_gate.py`** (D1868): `unguarded(contract:
   dict, bodies: dict[str, str]) -> tuple[Finding, ...]` where `bodies` maps an
   `api` function name to the FINAL body the set gives it (derive it with
   `sql_surface` — read whether `final_surface` returns bodies; if it returns
   names only, add a `final_function_bodies(templates)` beside it that walks the
   up sections in manifest order, `CREATE [OR REPLACE] FUNCTION api.<name>`
   replacing and `DROP FUNCTION` removing — the spellings D1818 measured) and a
   `Finding(tool, function, reason)` with reason `not_first` / `absent` /
   `release_function`. The first-statement test strips comments and
   whitespace, lowercases keywords, and requires `perform
   app.require_approval('<tool>');` immediately after the body's `begin`.
   **Callers**: `bin/mcp-contract.sh check --project` (exit 5, one line per
   finding naming the tool and ADR 0242, `release_function` printed and NOT
   refused); `rendering.py` beside the lint at `:2451-2452` (ONE line per
   finding on stderr, never a refusal — D1868); `propose` (Run 3).
4. **The pins that move** (D1872): `RELEASE_FUNCTIONS` gains `("app",
   "require_approval")`; a `GATE_NOBODY` witness in the grants guard;
   `test_database_function_signatures.py`'s witness list gains
   `("app", "require_approval")` if the guard lists witnesses per function (read
   it); the dev-cluster ledger pin → 0004's version; `test_project_migration_
   sets.py:859`'s `functions == {"set_note_embedding"}` unchanged (0004 adds
   none).
5. **The documents that say *not in the database***: THR-APPROVAL's residual
   (Run 1's text); ADR 0231's *Consequences* gains a dated line *"Session 35:
   the database half is ADR 0242"* (an ADR is amended by a dated note, never
   rewritten); `docs/workflows.md` and operator guide §17 *Approvals* (`:1371`)
   — the sentence *"approval governs the agent plane and workflows; the database
   authority is the SQL grant"* replaced by 0242's; `AGT-APPROVE-001`'s
   description if it carries the old sentence (grep).
6. **Tests.** `tests/contract/test_approval_in_database.py` (NEW,
   `pytestmark` first; the cluster fixture copied from
   `test_connectivity_substrate.py`; a project function `api.rig_gated` created
   in the fixture as the owner, calling the REAL `app.require_approval`; each
   case sets `request.jwt.claims`, `request.headers` and `app.agent_id` with
   `set_config(…, true)` inside ONE transaction as the request role, exactly
   the GUCs rig 35a measured PostgREST setting — **name rig 35a's reading in the
   module docstring**, and assert the ROW COUNT after each refusal, never only
   the SQLSTATE): the nine §2 proofs; `test_every_refusal_is_one_sentence`
   asserts the message is exactly `AP403: approval_required` for all six refusal
   causes. `tests/contract/test_approval_gate.py` (NEW): the five §2 proofs over
   hand-built contracts and bodies, plus the example project through the REAL
   compiled contract. `test_project_migration_sets.py::test_the_example_sets_
   fourth_migration_adds_only_the_guard` (0004 = 0003 + one line, as
   `:1313-1360` does for 0003). `test_dev_environment_cluster.py`: the grants
   proof extended (EXECUTE still `t` for `authenticated`, `agent_writer`,
   `api_documentation`, `f` for `anon`; `prosrc` has the guard FIRST and the
   emit).

**Battery** (`PYTHONDONTWRITEBYTECODE=1`, `__pycache__` cleared, each file
snapshotted to `/tmp` and restored by copy with `cmp`, every anchor
pre-flighted to match exactly once and a miss fatal; each mutation beside a
control it cannot reach, in the same invocation; HOW each failed asserted —
`FAILED` a kill, `ERROR` a broken fixture): **M1** the guard returns for an
agent with no claim (`IF claim IS NULL THEN RETURN`) → `test_an_agent_without_
a_claim_is_refused_and_nothing_is_written` FAILS; **M2** the key comparison
dropped → `test_a_key_that_differs_…` FAILS; **M3** `r.status = 'running'`
dropped → `test_a_decision_on_an_ended_run_is_refused` FAILS; **M4** the tool
comparison against the ROW dropped (claim only) → a proof whose claim names the
tool but whose row names another FAILS (write that arm); **M5** `GRANT EXECUTE
… TO {{authenticated}}` added to 0037 → `test_require_approval_is_executable_
by_no_role` FAILS on `has_function_privilege` (and the schema's `42501` alone
would NOT have caught it — D1814); **M6** `approval_gate` accepts the guard as
the SECOND statement → `test_a_guard_after_another_statement_is_refused` FAILS;
**M7** the render refuses instead of reporting → `test_the_render_reports_and_
never_refuses` FAILS. Control for all: `test_a_caller_with_no_agent_identity_
passes` and `test_the_example_projects_gated_function_calls_the_guard` green in
the same invocation.

**Targeted list** (fast, after each edit): `test_approval_gate`,
`test_project_migration_sets`, `test_migrations`, `test_database_function_
signatures`, `test_rendered_migrations`, `test_acceptance_registry`,
`test_evidence_claims`, `test_documentation_index`, `test_api_migrations`,
`test_api_surface_contract` (these two must be UNMOVED — 0037 is not `api`);
**Docker-backed, once before the commit**: `test_approval_in_database`,
`test_connectivity_substrate`, `test_workflow_gates`,
`test_dev_environment_cluster`, `test_migrations_apply_as_the_migration_user`.
Re-render both example projects first (D1678). Commit (`Session 35 Run 2:
approval in the database -- migration 0037, the example set's 0004, the
approval-gate check`), push, read CI by full SHA.

### Run 3 — the proposal: the set digest, the destructive reading, `propose` and `approve`, manifest 8

**Code. Push, read CI by full SHA.**

**Read first:** `bin/migrate.sh` whole (the case at `:128`, `parse_args`
`:117-171`, `usage` `:48-115`); `bin/migrate.py` whole; `src/agentic_postgres/
migrations.py:440-560`, `:795-940`; `rendering.py:600-620`, `:2480-2500`;
`src/agentic_postgres/evaluation_harness.py:700-815`; `bin/dev.py:120-145`,
`:290-470`; `schemas/project.schema.json:1-30`, `:95-120`, `:780-962`;
`src/agentic_postgres/config.py:55-100`, `:1080-1140`, `:1220-1240`;
`tests/contract/test_project_manifest.py` whole; `tests/contract/
test_cli_contract.py` (grep `migrate` and `COMMANDS_WITH_VERBS`);
`bin/database-access.py:20-95` (the identity rule 0243 cites).

1. **`migrations.set_digest(set: MigrationSet) -> str`** — `sha256` of
   `set.lock_path.read_bytes()`; `rendering.py:2486-2495` calls it (ADR 0002);
   a proof holds the render's `lock_sha256` equal to it on both example
   renders.
2. **`migrations.destructive_findings(set) -> tuple[DestructiveFinding, ...]`**
   (D1862): over each migration's comment-stripped UP section (reuse the lint's
   stripping — read `:795-805` and call the same helper, never a second one),
   one compiled pattern per shape in D1862's list, each accepting `IF EXISTS`,
   `ONLY`, quoted and schema-qualified names and arbitrary whitespace; a
   finding is `(version, kind, object)` with `object` as written (unquoted,
   lowercased). A proof table of thirty statements (every shape × two
   spellings) and ten non-findings (the same words in a comment, in a string
   literal, in a down section, `CREATE TABLE … (drop_date date)`,
   `ALTER TABLE … ENABLE ROW LEVEL SECURITY`).
3. **Project manifest schema 8** (D1863): the enum gains 8 (`:16-27`, and the
   description's *"1 to 5"* corrected, D1882); `migrations` gains
   `approvals_required` (`{"type": "integer", "enum": [0, 1]}`); a v8 gate in
   the top-level `allOf` in the v7 gate's shape (forbidden at `maximum: 7`);
   `validate_project_semantics` refuses `approvals_required` without `set`;
   `config.SUPPORTED_PROJECT_SCHEMA_VERSIONS` gains 8, `PROJECT_APPROVALS_FROM
   = 8`, **`config.approvals_required(manifest) -> int`** (0 below 8 or when
   absent). `project.example.yaml` → 8 with `approvals_required: 1` and a
   comment; `project.second.example.yaml` → 8 without. The downgrade helpers
   (`test_project_manifest.py:83-96`, `:725-736`) pop it. Re-render both.
4. **The proposal record** — `src/agentic_postgres/proposal.py` (pure logic,
   no I/O but `pathlib`): `PROPOSALS_SUBDIR = "proposals"`,
   `RECORD_SCHEMA_VERSION = 1`, `proposal_path(project_root, digest)`,
   `approval_path(...)`, `build_proposal(**readings) -> dict`,
   `build_approval(proposal_bytes, declared_by, at) -> dict`,
   `check_names(proposal, approval)`, `NAME = re.compile(r"^[A-Za-z][A-Za-z0-9
   ._'-]{1,63}$")`, `fold(name)` (casefold, collapse whitespace), and the four
   gate sentences as module constants (Run 4 raises them). The proposal JSON,
   sorted keys, two-space indent, trailing newline:
   `{schema_version: 1, kind: "migration_set_proposal", project_slug,
   set_digest, set: {root, versions: [{version, name}], follows_release_version,
   follows_release_version_source}, release: {template_version,
   release_lock_sha256}, lint: "passed", destructive: [{version, kind,
   object}], dev_apply: {exit, migrations_applied, seconds, from_empty: true,
   applied_by: "psql as migration_user", existing_rows: "none"}, surface:
   {functions: [{name, reviewed}], views: [{name, reviewed}]}, approval_gate:
   [{tool, function, reason}], harness: {contract_sha256, derived, written,
   capabilities} | {not_applicable: "…"}, capability_contract_sha256: <hex> |
   {not_applicable: "…"}, declared_by, declared_at, note: "The names in this
   record are declared, not authenticated (ADR 0243)."}`. The approval:
   `{schema_version: 1, kind: "migration_set_approval", proposal_sha256,
   set_digest, declared_by, declared_at, note: <the same sentence>}`.
5. **The verbs** — `bin/migrate.sh`: the case at `:128` gains `propose` and
   `approve`; `parse_args` gains `--by NAME` (required for both; refused
   elsewhere) and `--proposal DIGEST` (required for `approve`); `usage()` gains
   both verbs and their exit codes (0 written; 2 bad input or a name that is not
   `NAME`; 3 prerequisite missing — no render, a dev environment up; 5 the lint,
   the approval-gate check or a name rule refused; the record exists). Neither
   needs root, docker (except through `dev.sh`), the host or the network.
   `bin/migrate.py --mode propose|approve`: `propose` — loads the manifest
   (`config.load_project_manifest`), requires a set (exit 2 naming it), runs the
   lint (exit 5 on a finding), `destructive_findings`, **`bin/dev.sh status`
   then refuses exit 3 if an environment is up (naming `apg dev down`)**, runs
   `bin/dev.sh up --project M` (stdin closed, output captured, bounded 180 s)
   and parses rig 35b's line, `bin/dev.sh down --project M` in `finally`, the
   surface reading (`sql_surface` over the set against
   `projects/<slug>/contracts/postgrest-api-surface.yaml`'s `rpcs` and
   `relations`), `approval_gate.unguarded` over the committed capability
   contract (exit 5 on any finding but `release_function`, AFTER writing
   nothing), the harness counts through `evaluation_harness.coverage` (read how
   `bin/render-evaluation-report.py:119-136` builds the joint contract and call
   the same functions — a `bin/` command imports `agentic_postgres` only, ADR
   0093), writes the file with `O_EXCL` (exists → exit 5) and prints ONE line:
   `proposal <digest16> written: projects/<slug>/proposals/<digest>.json (N
   destructive finding(s))`. `approve` — reads the proposal (absent → exit 5),
   refuses a folded name equal to `declared_by` (exit 5, *"an approval needs a
   second name (ADR 0243)"*), writes `<digest>.approval.json` with `O_EXCL`.
   **Neither verb commits**: the operator or executor commits the records.
6. **Tests.** `tests/contract/test_change_proposal.py` (NEW, `pytestmark`
   first): the §2 GOV-LINT-001, GOV-PROPOSE-001 (bar the committed-record proof,
   Run 4) and GOV-APPROVE-001 proofs, driving `bin/migrate.py` as a subprocess
   against a tmp copy of a project root (the example set copied into
   `tmp_path/projects/<slug>`; `dev.sh` replaced by a recording stub on `PATH`
   that prints rig 35b's lines — **the stub's text is rig 35b's measured
   output, named in the docstring**, question 6: the fixture does not share the
   code's belief, it carries the measurement); `test_propose_refuses_while_a_
   dev_environment_is_up` uses the stub's `status` answering *up*.
   `test_dev_environment_cluster.py::test_propose_applies_the_set_from_empty_
   through_dev_up` — the REAL `dev.sh`, Docker-backed, the example set, a
   tmp output root (never the tree's `projects/example/proposals/`), asserting
   `dev_apply.exit == 0` and `migrations_applied` equal to the release's plus
   the set's count. `test_project_manifest.py` the two schema proofs.

**Battery**: **M1** `set_digest` hashes the lock's parsed JSON re-serialised →
`test_the_digest_is_the_renders_lock_sha256` FAILS; **M2** the `ALTER COLUMN …
TYPE` pattern loses `SET DATA` → the spelling proof FAILS; **M3** comments not
stripped → the commented-statement proof FAILS; **M4** the name fold drops
casefolding → `test_approve_refuses_the_proposers_own_name` FAILS on `"Ada"`
vs `"ada"`; **M5** `propose` downs a running environment instead of refusing →
the refusal proof FAILS (the stub records a `down` it must never see); **M6**
the approval hashes the proposal's parsed JSON → `test_approve_names_the_
proposal_by_its_bytes` FAILS (write it to edit one whitespace byte). Control:
`test_the_example_set_has_no_destructive_statement` and a clean propose
round-trip green in the same invocation.

**Targeted**: `test_change_proposal`, `test_project_manifest`,
`test_capability_compiler` (the enum pin `:957-975`), `test_cli_contract`,
`test_rendered_migrations`, `test_project_migration_sets`, `test_config` (grep
the module that pins `SUPPORTED_PROJECT_SCHEMA_VERSIONS`),
`test_acceptance_registry`; Docker once: `test_dev_environment_cluster`. **Every
module that reads `project.example.yaml`** (`git grep -l project.example.yaml
-- tests`, ~34 — the trip-discipline memory's rule) runs once at the close,
because both fixtures moved. Commit (`Session 35 Run 3: the proposal record,
the destructive reading, manifest 8`), push, read CI.

### Run 4 — the host gate, the status line, the capability report, and the example set's proposal

**Code. Push, read CI by full SHA.**

**Read first:** `bin/migrate.py:184-347` (`run_every_set`,
`reconcile_project_ledger`, `record_ledger`) and `:525-590`; `bin/deploy-
project.py:2475-2580`; `src/agentic_postgres/installed_release.py:1-60`,
`:95-170`; `tests/contract/test_migrate_command.py` (grep the module that
drives `migrate.py --mode up` with a recording dbmate — read it before writing
a fixture; if none exists, the gate's proofs call the gate FUNCTION and one
proof drives the dispatch with `run_dbmate` monkeypatched to raise if reached).

1. **The gate** — `proposal.gate(project_root: Path, set_digest: str,
   pending: tuple[str, ...], approvals_required: int) -> None`, raising
   `migrations.MigrationError` with one of the four sentences (D1865) or
   returning; **pure** (reads two files). `bin/migrate.py`'s `up`, after
   `reconcile_project_ledger` and **BEFORE THE FIRST dbmate RUN OF EITHER SET**
   (so a refused deploy writes nothing — the release set is never gated, but
   it is not applied ahead of a refusal either): `pending` = the rendered
   project set's versions minus the project ledger's (read how
   `reconcile_project_ledger` already computes the ledger — reuse it, never a
   second query); empty → no gate; else `proposal.gate(REPO_ROOT,
   migrations.set_digest(project_set), pending,
   config.approvals_required(manifest))`. **Read `reconcile_project_ledger`
   first**: if it WRITES (inserts ledger rows for a set applied before the
   ledger existed), write in the Done what it writes and whether a refused run
   leaves that write behind; if it does, the gate moves before it and a row
   says why.
2. **`status`** prints the line of D1865 after the ledger; **deploy step 6**
   relays a refusal's sentence (it already flattens to exit 5 with
   `"migrations did not apply: …"` — assert the sentence survives the
   flattening, `deploy-project.py:2545-2546`).
3. **The capability report** (D1866): after the lock is written
   (`deploy-project.py:2482-2499`), ONE line: `capability contract <sha16>:
   named by proposal <digest16>` / `…: named by no proposal of this project` /
   `no capability contract (the manifest declares none)`. `proposal.
   proposals_naming(project_root, capability_sha) -> tuple[str, ...]`.
4. **The example set's proposal**: on the clean tree after items 1–3 are
   committed locally, run `./deploy.sh --project project.example.yaml
   --render-only`, then `bin/migrate.sh propose --project project.example.yaml
   --by "<the executor's model id>, Session 35 executor"` — **the product's own
   verb writes the committed record** (D1114). Read it whole; its
   `destructive` must be `[]`, its `approval_gate` `[]` (0004 guards the one
   gated tool), `dev_apply.exit` 0. Commit it in this run. **The APPROVAL is not
   written here** — it is the operator's act (Run 8, Sheet A1): the example
   manifest says `approvals_required: 1`, and an approval declared by the
   executor that proposed it would be refused by the verb anyway.
5. **Tests.** `tests/contract/test_proposal_gate.py` (NEW, `pytestmark`
   first): the eight §2 proofs — the gate over tmp roots, the dispatch over a
   recording `run_dbmate` that FAILS the test if it is reached for a refused
   set, `status`'s line, and deploy's relay over `deploy-project.py`'s own
   `fail` (read how `test_deploy_*` modules drive a single step).
   `test_change_proposal.py::test_the_example_sets_committed_proposal_names_
   its_lock` — the committed record's `set_digest` equals
   `migrations.set_digest(release_set's example project set)` and its
   `versions` are the lock's (a later change to the set makes this proof — and
   the host gate — refuse, which is the point).

**Battery**: **M1** the gate reads `pending` as the rendered set (not minus
the ledger) → `test_a_set_with_nothing_pending_needs_no_proposal` FAILS;
**M2** the gate compares the proposal's digest case-insensitively truncated to
16 → `test_a_proposal_for_another_set_is_refused` FAILS (write its two digests
to share sixteen hex); **M3** `approvals_required` read from the RELEASE's
example manifest instead of the INSTALLED manifest → a proof with the installed
manifest at 1 and the tree's at 0 FAILS (write it); **M4** the gate moved after
the project dbmate run → the recording-dbmate proof FAILS. Control: the release
set applied with the project set fully applied, green.

**Targeted**: `test_proposal_gate`, `test_change_proposal`, the `migrate`
command module, the deploy-step module, `test_cli_contract`,
`test_acceptance_registry`, `test_evidence_claims`. Commit (`Session 35 Run 4:
the host applies only a proposed set; the example set's proposal`), push, read
CI.

### Run 5 — hardening: the edge and the three services bounded, `apg-diag`, D1856

**Code. Push, read CI by full SHA.** **Needs Sheet E0's values** (Run 1's
`**Done.**`); without them this run does not start.

**Read first:** `infra/edge/compose.yaml` whole; `tests/contract/
test_process_limits.py` whole; `tests/contract/test_compose_contract.py:
1160-1230`; `tests/contract/test_edge_config.py:95-110`, `:200-210`,
`:515-655`; `src/agentic_postgres/config.py:640-710`, `:930-940`;
`rendering.py:650-660`, `:1800-1830`, `:1930-1990`; `compose.yaml:550-570`,
`:710-730`, `:910-930`, `:1230-1240`; `capacity_reading.py:300-370`;
`capacity_probe.py:150-190`; `diagnosis.py:930-955`; `bin/admit.py:180-210`;
admission's `decide` (grep `def decide` under `src/`); `bin/apg-diag.sh` whole;
`tests/contract/test_diagnostic_surface.py` whole; the auth, storage and mcp
services' logging (grep `logging`, `json.dumps` and `StructuredRequestLog` under
`services/`) — the three log line shapes the redaction proof feeds;
`src/agentic_postgres/dr_kit.py` (grep `mkdir`, `chmod`, `0o7`).

1. **The edge** (D1877): in `infra/edge/compose.yaml`, on `docker-socket-proxy`
   and on `traefik`, `mem_limit: <E0 value>m`, `pids_limit: <E0 value>`, `cpus:
   "1.0"` — literals (the edge has no render keys and gains none), each with a
   one-line comment naming ADR 0244 and Sheet E0's date. **Delete
   `test_the_edge_plane_is_untouched` and write `test_the_edge_plane_is_bounded`**
   (the exact three values per container, read from the file with `yaml`, and
   the ADR number in the docstring); move the registry node id in the same
   commit (§2). The existing edge pins (`test_compose_contract.py:1173-1220`,
   `test_edge_config.py`) stay green unchanged.
2. **The three services** (D1878): `config.SERVICE_MEMORY_LIMITS_MB = {
   "pgbouncer": <E0>, "postgrest": <E0>, "docs": <E0>}` beside
   `SERVICE_RESOURCE_DEFAULTS` with the rule in a comment; `rendering.
   COMPOSE_ENV_KEYS` gains `PGBOUNCER_MEMORY_LIMIT`, `POSTGREST_MEMORY_LIMIT`,
   `DOCS_MEMORY_LIMIT`; `build_compose_env` writes them as `AUTH_MEMORY_LIMIT` is
   written; `compose.yaml` adds `mem_limit: ${PGBOUNCER_MEMORY_LIMIT:?…}` (the
   file's own interpolation form — copy auth's line) to the three. **Grep every
   reader of `mem_limit`, `MEMORY_LIMIT` and `HostConfig.Memory` first** (D979)
   and write each reader's answer in the Done: the ceilings reading (sums them —
   the figure rises), `unbounded` (falls), admission's `decide` (charges
   `unreclaimable_mb` — expected unaffected; if it charges caps, **STOP**, §9),
   the dev cluster (`test_the_dev_cluster_carries_the_same_limit_as_the_release`,
   `test_process_limits.py:188+`, read its condition), the doctor's text.
   `test_every_long_running_service_carries_a_memory_limit` (the nine long-
   running services by the file's own `restart` policy or the set
   `SERVICE_RESOURCE_DEFAULTS` names — read which the pids proof uses and use the
   same) and `test_the_three_new_memory_limits_are_rendered_from_config`.
   `docs/threat-model.md:35`'s sentence corrected (D1878).
3. **`apg-diag`** (D1879): `SERVICES` gains `auth storage mcp` (in that order,
   appended); `redact()` gains the JSON-key rule as a fourth `sed -E`
   expression; `test_the_log_allowlist_is_exactly_these_services` (the exact
   nine, read from the script as `:58-67` reads `VERBS`),
   `test_a_json_quoted_secret_is_redacted`, `test_the_new_services_log_lines_
   are_redacted` (a line in each service's REAL shape, built from the logging
   code read above — a JWT, a 64-hex key, a `"password": "…"` member each
   masked; the non-secret members kept), `test_the_log_cap_is_two_hundred_
   lines`. `infra/host/apg-agent.sudoers` is unchanged.
4. **D1856**: `dr_kit`'s export creates the kit's `projects/` directory `0o700`
   (and every directory beneath it — read the code); a proof exports into a tmp
   directory and walks every directory's and file's mode.

**Battery**: **M1** the edge's `pids_limit` removed → `test_the_edge_plane_is_
bounded` FAILS; **M2** `POSTGREST_MEMORY_LIMIT` not written by
`build_compose_env` → the render proof FAILS and the compose interpolation
refuses (`:?`); **M3** `mcp` removed from `SERVICES` → the exact-set proof
FAILS; **M4** the JSON rule removed → the JSON proof FAILS; **M5** the kit's
`projects/` made `0o755` → the mode walk FAILS. Control: the existing
`test_a_container_cannot_fork_past_its_pids_limit` and the redaction samples at
`:234-259` green in the same invocation.

**Targeted**: `test_process_limits`, `test_compose_contract`,
`test_edge_config`, `test_rendered_compose` (grep the module that pins the
compose env keys), `test_capacity_reading`, `test_admission`,
`test_diagnostic_surface`, `test_disaster_kit`, `test_cli_contract`,
`test_repository_contract`, `test_acceptance_registry`,
`test_documentation_index`. Re-render both examples first. Commit (`Session 35
Run 5: the edge and every long-running service bounded; apg-diag reads auth,
storage and mcp; D1856`), push, read CI.

### Run 6 — the documentation converged, and the documented path extended

**Documentation plus the two lists the documentation tests read
(`dx_record.DOCUMENT_ROOTS` in `src/`, `CURRENT_PATH_DOCUMENTS` in `tests/`) —
so it is a code commit: push and read CI.**

**Read first:** `docs/operator-guide.md` §1 (`:20-91`), §5 (`:268-325`), §10
(`:527-622`), §16–§18 whole (`:1146-1660`); `docs/new-team-member.md` whole;
`docs/second-walk.md` whole; `docs/migrations.md` whole; `docs/workflows.md:
300-349`; `docs/connectors.md:220-240`; `docs/README.md` whole;
`src/agentic_postgres/dx_record.py:100-140`; `tests/contract/
test_documentation_index.py:160-480`, `:690-778`; `tests/contract/
test_session12_documented_path.py` whole (594 lines — every guard it holds
applies to the new steps: no tracked-file edit, every command shipped and
executable, no future-session label, the `--session` literal rule).

1. **`docs/change-governance.md`** (NEW): what a proposal is and what it is
   not (ADR 0243's sentence, verbatim, in the first screen); the digest; each
   member of the record and the three readings it cannot take (D1858–D1860),
   each with its reason; `destructive` (named, never refused — D1862); the
   two verbs with their exit codes; `approvals_required` and the declared-name
   rule; what a host refuses and the four sentences exactly as `proposal.py`
   holds them (a proof in `test_documentation_index.py` or a new
   `test_change_governance_page.py` asserts the page quotes each constant — the
   D1484 class: a sentence a program stopped agreeing with); the capability
   report (D1866); **the database half of approval** (ADR 0242: what a direct
   agent call now meets, what a human's call meets, what a profile on a release
   tool does not get, D1869); *What is not here* (a lock-risk estimate; a
   capability refusal; a proposal for a workflow or a connector; an
   authenticated reviewer). Indexed in `docs/README.md`'s developer-loop table.
2. **Operator guide**: **§19 *Change governance, on a deployment*** (the
   status line; the deploy's step 6 refusal and what to do — propose on the
   workstation, commit, re-deploy; the capability report line; the approval
   file is committed, NEVER written on the host, D971/D1852; *If something goes
   wrong*); §17 *Approvals* gains *In the database* (ADR 0242); §16 gains the
   edge's and the three services' limits and the `unbounded` count's new
   meaning; §10's worked sweep moved from `bin/session-25-check.sh` to the
   newest SHIPPED gate with its current flags (D1882 — in this run that is
   `bin/session-34-check.sh`, because `test_session12_documented_path` refuses
   a command that is not shipped; Run 9 moves it to `session-35-check.sh` with
   the other session literals);
   §5's stale retention paragraph (`:316-321`) rewritten true: 0033's two
   functions prune the agent record by an operator's horizon; the workflow and
   connector tables are not pruned (D1886); `docs/README.md:29`'s row names
   §15–§19.
3. **`docs/new-team-member.md`**: **step 15 *Propose your migration set***
   (after step 10's local database — the order a walker meets it: `apg migrate
   propose --project … --by "<your name>"`, read the record, and one paragraph:
   *approve needs a second person; your project may set `approvals_required: 0`
   while you are alone, and a host refuses a pending set without a proposal*);
   **step 16 *Compose a workflow over your capability*** (`apg workflow init`,
   edit, `apg workflow validate`, `apg dev reset`/`up` installs it, and one
   paragraph pointing at `docs/connectors.md` for everything that needs a
   deployment — D1881). The *What "done" looks like* section (`:442`) gains the
   proposal file. **Every command in both steps is run by the executor on a
   clean tree against a throwaway project root before the page is committed**,
   and the transcript is summarised in the Done (a step nobody ran is the
   D1359 shape).
4. **`docs/second-walk.md`**: the task statement gains goal 8 — *"Propose your
   migration set, and read what the proposal says about it."* — and its release
   line names `1.13.0` (never a commit: the operator hands the commit on Sheet
   W). The *"At most two walks per release"* paragraph gains one sentence: a
   new release opens the count again (D1884).
5. **The two lists**: `dx_record.DOCUMENT_ROOTS` and `CURRENT_PATH_DOCUMENTS`
   gain `docs/workflows.md`, `docs/connectors.md`, `docs/change-governance.md`
   (D1881); every guard in `test_session12_documented_path.py` then reads the
   three pages — expect it to find what they say that it refuses, and repair the
   PAGE, never the guard.
6. **`docs/migrations.md`**: the refusal table (`:174-184`) gains ADR 0235's
   release-function rule (D1882); *Adding one* (`:101-113`) gains *propose it*;
   *A project's set* (`:115`) links `docs/change-governance.md`.
7. **The pages that said *"not in the database"***, re-grepped after Run 2's
   edits (`grep -rn -i 'not the database\|not in the database\|plane control
   only' docs/ README.md`), each now true.

**Targeted**: `test_documentation_index`, `test_session12_documented_path`,
`test_dx_record`, `test_release_contract` (grep what it reads of the pages),
`test_change_governance_page` if written. Commit (`Session 35 Run 6: change
governance documented; the documented path proposes and composes`), push, read
CI.

### Run 7 — the trip's instruments, rehearsed offline before they meet a host

**No product change. The scripts are trip scripts** (the `s34-r10-*` class):
written in WSL `~/s35r10/`, copied to the scratchpad `s35r10/`, staged on the
host in Run 10 — never committed to the tree (a measuring instrument that
lived in `bin/` would be a product verb with a contract; these read, they do
not operate). **Commit only this run's `**Done.**` (documentation, no CI).**
Fifteen never-executed proofs have failed on first execution; an instrument
is a proof of a number, so each runs here first against a local target with a
control.

**Read first:** rigs 35c, 35d and 35e's Done lines; `tests/deployment/
conftest.py` (grep `AdminSession`, `admin_password`, `_create_subject`,
`agent-token`) — the neighbour script creates its probe identities exactly
the way the live suite does, through the product's published routes (D1114);
`s34-r10-gate.sh` in `~/s34r10/` (how the sweep is handed the admin password
file and the outputs); `bin/restore-test.py` (grep `workflow_run`) for the
superuser read's shape; the deployed document's `routes` member (read an op
copy in `~/s34r10/fetched/` or the fixture render).

1. **`s35-r10-probe.py`** (op; stdlib only; no token): `--outputs FILE
   [--outputs FILE]`, `--classes rest,auth,storage,mcp,docs`, `--interval 0.5`,
   `--stop-file PATH`, `--out JSONL`. Each class's URL is DERIVED from the
   deployed document's `routes` (never typed); the endpoint per class is the
   one rig 35d and the tree fixed in Run 1's Done; each request `timeout=2`;
   each line `{t_mono, t_wall_ms, project, class, status | error, ms}`; the
   schedule keeps the TOTAL rate at or under the budget D1874 set, and the
   script refuses to start above it. `s35-r10-gaps.py` reads a JSONL and prints,
   per project and class, every DOWN window (D1875's definition) with its first
   and last stamp and its length, and the count of 429s separately.
2. **`s35-r10-sampler.py`** (op): 35e's text, `--container-name` resolved
   through `/proc` (D1739), `--interval 0.1`, `--out JSONL`, `--stop-file`.
3. **`s35-r10-load.py`** (runs INSIDE the project's auth image on its
   `internal` network, as root's `docker run --rm --network <compose.networks.
   internal from the DEPLOYED document> -v <script>:/load.py:ro --entrypoint
   python3 <that project's auth image digest, read from docker inspect of its
   running auth> /load.py …` — no image pulled): concurrency 8 threads, `GET
   http://postgrest:3000/notes?limit=50` with a probe human's bearer, for
   `--seconds`; prints achieved requests, rate, non-2xx and the achieved
   latency's p50/p95 (the LOAD's own reading, recorded beside the neighbour's).
   **Read the deployed document for the network name and the PostgREST service
   alias** (D1853: a rendered-only member read from a deployed document broke a
   Session 34 fixture).
4. **`s35-r10-neighbour.py`** (root on the host; `PYTHONPATH=src` for the
   deployed-document reader; stdlib otherwise): creates on EACH project one
   probe human `apg-s35-neighbour-<SWEEP>` with `notes:read` (and on beta one
   owner + one agent whose scopes are READ from `workflow_definition`'s
   `notes-roundtrip` row — never typed, D1845), logs them in over the published
   routes, then runs D1873's four phases, each 120 s, each with the probe on the
   NEIGHBOUR (`--classes rest` at the budget) and the sampler on beta's `auth`
   during phase B; phase B enqueues K = 24 runs through `POST
   /api/app/workflows/runs` with the agent's token (`workflow_routes`' own
   route); phases C and D start `s35-r10-load.py` as above. After each phase it
   reads, as `postgres` through `container_exec.run` (the helper — ADR 0218),
   the phase's `workflow_run` rows `(id, status, started_at, finished_at)` with
   microseconds, and writes one JSON document per phase:
   `{phase, window: {start_ms, end_ms}, neighbour: {p50, p95, p99, n, errors,
   status_429}, load: {…}, runs: [...], sampler_file}`. It revokes the agent,
   deletes the humans where no FK refuses, and prints what it left (D1700's
   shape). **It never enables a connector** (D1888).
5. **`s35-r10-classify.py`** (workstation): D1876's rule over the sampler JSONL
   and phase B's `runs` → `{inside: n, max_mb, median_mb}`, `{outside: …}`, and
   the verdict *enough (≥ 20)* or *not enough*.
6. **The rehearsal, each with a control**: the probe and `gaps` against rig
   35d's Traefik with the backend recreated (a DOWN window found; control: no
   recreation → none); the sampler as 35e; the load container against the
   Session 33/34 rig stack's PostgREST on a rig network with the alias
   `postgrest` (achieved rate > 0, errors 0; control: a wrong token → every
   answer 401, counted as non-2xx); the neighbour script's phase logic in a
   `--dry-run` that performs every read and prints every request it WOULD make
   without making one (the op-side part runs against the op copies; its
   root-side part is exercised on the rig stack's cluster through
   `container_exec.run`); the classifier over a synthetic JSONL whose inside and
   outside samples are known (control: shift every stamp by 10 s → 0 inside).

**Done** records each script's sha256, each rehearsal's result and control,
and the budget (req/s) each probe was run at.

### Run 8 — the operator's approval, and the third reader arranged

**Two sheets for the operator, no code. The approval record is committed and
pushed; read CI (it is a file under `projects/`, which the proofs read from Run
9 on).**

**Sheet A1 — the approval (the operator, at the workstation, in WSL; NOT
`sudo`).** The agent prints the proposal's digest and its path, and the
operator reads the proposal file (it is short) and then runs, in their own
terminal, nothing after it:

    cd ~/projects/agentic-postgres && bin/migrate.sh approve --project project.example.yaml --proposal <digest> --by "<your name>"

→ exit 0 and one line naming `<digest>.approval.json`. **The agent never runs
this line.** The agent then reads the file, checks it names the proposal's
bytes (`sha256sum` of the proposal file equals `proposal_sha256`) and a
`declared_by` different from the proposal's, commits it (`Session 35 Run 8:
the example set's proposal approved by <name> (declared, ADR 0243)`), pushes,
and reads CI.

**Sheet W — the third reader (the operator decides; D1884).** The agent hands
the operator three lines to choose from, and records the choice in this run's
Done verbatim:

- **(a) A person** who did not build Stage 4 walks it. The operator gives them
  `docs/second-walk.md`'s task statement (between its markers) and, AFTER Run
  9's CI is green, the commit to clone; they walk on their own machine (Linux
  or WSL; `git clone` inside WSL, never on NTFS — CLAUDE.md's `0600` trap),
  write `~/walk/dx-record.json` with `followed_by.kind: "person"`, run
  `bin/dx-record.sh digest` and `check`, and hand the file to the operator. No
  conversation with the builder during the walk; any exchange is an
  `undocumented_steps` entry by rule (ADR 0207 §1).
- **(b) A fresh model session** under ADR 0207 §1's conditions exactly (a WSL
  clone of the commit in a directory that is not the launch folder, an empty
  memory directory, no transcript, the task statement as its only
  instruction), `followed_by.kind: "agent"`, the operator as `instructed_by`.
- **(c) No walk for 1.13.0.** The Session 25 record is handed to the sweep
  again; `documented_path` stays `failed`; the Stage 5 report says so first.

**Whichever is chosen, the record reaches the sweep only if it exists before
Sheet F6** (the host copy at `/home/op/session-35-dx-record.json`, copied by the
agent as `op`); a record that arrives later is read by `bin/dx-record.sh check`
on the workstation and quoted in the Stage 5 report, and the claim stays what
the sweep read. **A walk on Run 9's commit is a walk of the release only if the
deployed commit is Run 9's**; if the trip forces a repair run (Session 34's
10a), `dx-record check`'s *documents that moved after the walk* reading says
whether the repair touched what the walker read, and the report says so.

### Run 9 — the bump, the registry, the gate, and the trip's proofs

**Read first:** `src/agentic_postgres/__init__.py:691-764` (34's paragraph and
`CURRENT_SESSION`); `bin/session-34-check.sh` whole — **yes, whole: 1,670
lines, and D1199 says the last ones are the least executed**;
`tests/contract/test_session_thirty_four_gate_modes.py` whole;
`bin/upgrade.py:100-140`; `docs/upgrade-guide.md:72-101`; `README.md:1-40`;
`tests/deployment/test_session33_gates.py` whole (the approval fixtures this
session's proofs copy) and `tests/deployment/test_session34_connectivity.py:
1-200`, `:540-560` (`_embed`); `tests/deployment/conftest.py:85-140`,
`:890-970`, `:1225-1240`; `src/agentic_postgres/capacity_probe.py:150-190`.

1. **The registry**: `GOV` in the ID regex and the Session 35 sentence (§2);
   the ten entries of §2 under a `# Session 35 (ADR 0242-0245)` banner, node ids
   read from `pytest --collect-only -q` over every module the runs touched
   (D1236, D1762), plus the moved entries (§2); `evidence_claims.py`'s ten
   claims, seven in `OFFLINE_CLAIMS`, ten rows in `CLAIM_INTRODUCED_IN`;
   `THR-CHANGE`'s two ID cells rewritten from the collected names (D1816's
   shape); **`test_change_proposal.py::test_the_example_sets_approval_names_
   its_proposal`** (NEW — the committed approval names the committed proposal's
   bytes and another name) joined to GOV-APPROVE-001;
   `bin/render-acceptance-matrix.py --write`; `bin/render-config.py
   --bounds-doc --write`.
2. **`CURRENT_SESSION = 35`**; the Session 35 paragraph in `__init__.py` in
   34's shape: what moved (this plan's header inventory, AS BUILT), the
   `upgrade plan` reading with the declared class and its verdict (item 6),
   the MINOR argument (a migration by declaration; manifest 8 leaves 1–7 valid;
   no document, secret or `api` move; the proposal gate a new step for a project
   that ADDS a migration — D1889), `OFFLINE_CLAIMS` 53 → 60 and `CLAIMS` 188 →
   198 *counted from the tuples*, and **the pricing paragraph LAST** (D1629).
   `VERSION` → `1.13.0`; `README.md:7`; `docs/upgrade-guide.md`'s release
   table gains the `1.13.0` row after `:101` (applies migration 0037; the
   example set's 0004 needs its committed proposal; project manifest 1–8; **a
   project that adds a migration now proposes it first — `bin/migrate.sh
   propose`, and a host refuses a pending set without one**; the edge's limits
   need `sudo bin/edge.sh --host host.yaml restart`, which drops every project's
   ingress for the measured interval; `apg-diag`'s copy re-installed; a rollback
   by image is not possible past 0037 — ADR 0162 §3); both release pages'
   release line; **every `--session 34` / `--through-session 34` literal on the
   documented path moved**, counted per file before and after (the plan is NOT
   moved; D678/D1484), and the operator guide §10's worked sweep moved from
   `bin/session-34-check.sh` to `bin/session-35-check.sh` in this commit (the
   gate now exists, Run 6's D1882 edit); `bin/apg.sh generate --project project.example.yaml` and
   `--check` (the client's version fields move).
3. **The trip's proofs — `tests/deployment/test_session35_governance.py`**
   (NEW), `pytestmark = [pytest.mark.p0, pytest.mark.live_host,
   pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS",
   "APG_PROJECT_B_OUTPUTS")]` before the first test. Helpers COPIED from
   `test_session33_gates.py` (`_create_subject`, `_login`, `ProbeAgent`,
   `_create_agent` with names `apg-s35-{label}-{SWEEP}`, `_revoke`, `_until`,
   `_audit`) and `test_session34_connectivity.py`'s `_embed`; `SWEEP =
   secrets.token_hex(4)` in every name and title. **AGT-APPROVE-004** (three —
   an agent with `note_embeddings:write` (beta's deployed lock vocabulary READ
   first, the `gate_owner` rule) owned by a probe human; the owner creates a
   note; the agent's OWN token `POST {rest}/rpc/set_note_embedding` with an
   `Idempotency-Key` → **403**, the body carrying `AP403: approval_required`
   exactly as rig 35a recorded it, and `SELECT count(*) FROM
   app.note_embeddings WHERE note_id = …` = 0 as the superuser; the owner's
   direct call → 200 and one row; the approved call — Session 33's
   `approved_run` flow copied (a second user approves under
   `admin_workflows:approve`) → the run `succeeded`, ONE embedding, the plane's
   audit `refused` then `served`); **GOV-APPLY-002** (one — beta's deployed
   document's `migrations.project_set.lock_sha256` equals the committed
   proposal's `set_digest` (read from the RELEASE directory named by the
   document's `source_commit`, `/opt/agentic-postgres/releases/<commit>/
   projects/example/proposals/`), the project ledger's newest version equals
   the proposal's newest, and `bin/migrate.sh --project <installed manifest>
   --runtime status` (the product's command, as root) prints `proposal
   <digest16>: present, approved by …`); **NODE-LIMIT-003** (two — `docker
   inspect` of the edge's two containers: `Memory`, `PidsLimit`, `NanoCpus`
   equal the committed compose file's values; `capacity_probe.read_ceilings`
   (the product's own reader) → `unbounded` empty). **Every docker call through
   `container_exec.run` or the conftest's existing helper — grep before writing
   one.**
4. **`pytest --setup-plan`** for the new module with `APG_LIVE_HOST=1
   APG_PROJECT_A_OUTPUTS=<an op copy> APG_PROJECT_B_OUTPUTS=<…>` set (D671,
   D676) — and with none set (every proof SKIP, 0 errors); both outputs kept
   in the scratchpad and counted in the Done. **None of them has executed.**
5. **`bin/session-35-check.sh`** derived from 34's by a count-asserted script
   (the `s34r10-derive.py` model: `SESSION=34` → `35`, `session-34` →
   `session-35`, `thirty_four` → `thirty_five`, the evidence prefix, the ADR
   range in the header, the offline sentence's counts *eleven* → *seven* and
   *fifty-three* → *sixty*), **the header and usage rewritten whole and read
   line by line** (D1488) — `--dx-record-file`'s entry whole, on its own lines,
   and named in the host synopsis (D1883); `run_suite "p0 and not future and
   not live_host and not external"` kept verbatim (D1242); **no flag added or
   removed** — the sorted `--flag` token sets of 34's and 35's scripts EQUAL,
   the diff written in a script file (process substitution inside `wsl bash -lc
   "…"` is CLAUDE.md §1's quoting trap) and pasted in the Done; `SHELL_COMMANDS`
   gains it; `chmod 755`; `git add`. `tests/contract/test_session_thirty_five_
   gate_modes.py` derived from thirty-four's (`SESSION_PREVIOUS_NUMBER = 34`,
   the no-gap test carried, `test_exactly_this_sessions_declared_claims_are_
   offline` naming the seven) **plus `test_every_accepted_flag_has_its_own_
   usage_entry`** (D1883).
6. **`upgrade plan` offline** (Session 34 Run 9's recipe, D1844 — the candidate
   renders the INSTALLED tree's manifest): the installed side a worktree at
   `14b1b9d`; the candidate a `tar`-piped copy of the working tree at
   `/tmp/apg-candidate` with `.generated/` excluded; both rendered from the
   INSTALLED tree's `project.example.yaml` (copied in as `project.installed.
   yaml` — schema 7, no `approvals_required`, which is what an operator's
   manifest is on the day); `bin/upgrade.sh plan … --json --also
   migration_added` → expect `bump minor`, `requires minor`, verdict `ok`,
   `operator_digests_moved []`; list every differing leaf (D1889's prediction);
   without the flag → `requires patch`. A `major`, or a leaf D1889 did not
   predict whose class is not `implementation`, is §9's stop.
7. **The gates**: `bin/session-01-check.sh` once on the clean tree (commit,
   gate, repair, commit, gate again; every first-run failure a row), run
   DETACHED with its exit code written from inside (CLAUDE.md §1);
   `bin/session-35-check.sh --mode offline` → `evidence/session-35-offline.
   json` with the seven new offline claims plus the 53 inherited, every one
   `passed` (the count read from the file). Push; CI by full SHA. **Nothing goes
   to the host until this commit's CI is green by full SHA.**

Commit (`Session 35 Run 9: the bump to 1.13.0, the registry, the gate, the
trip's proofs`), push, read CI.

### Run 10 — the trip: the release on both projects with the probe, the edge recreated, one sweep, the neighbour sitting, the tag

**Before the day** (agent, offline): read Session 34's Run 10, 10a–10c and
Sheets D1–D9 (`session-34-implementation-plan.md` §5 and the appendix) and
`docs/operator-guide.md` §17/§18 *If something goes wrong* (D977); **derive the
host scripts `s35-r10-*` from `s34-r10-*`** (`checkout, renders, c1, sentinel,
after, readings, gate, launch, cleanup`) with `~/s34r10/s34r10-derive.py`
copied to `~/s35r10/s35r10-derive.py` and edited (`s34-r10` → `s35-r10`, `34` →
`35` only where it is a session literal, the bundle's sha), **every count
asserted, and the gate script's declaration block fifteen tokens in, fifteen
out** (D1133); the facility script and `after-facility` are NOT derived (no
facility moves); Run 7's instruments copied in; `s35-r10-e0.sh` = Run 1's E0
script re-staged (the F4 after-read); the external script `~/s35r10/
s35-r10-external.sh` from `~/s34r10/s34-r10-external.sh` WITH D1640's
`ssh-agent` block; every script copied to the scratchpad; CI green on Run 9's
commit by full SHA; **WSL's outbound TCP probed with a timed `/dev/tcp`
connect read inside a script** (CLAUDE.md §1 — a Windows reboot early if it is
dead); the two op-owned copies' `source_commit` read. The reads scripts TEE
their own transcript — hand them as `sudo bash <script>`, never inside
`script(1)` (D1771); the deploys, the sentinel, the edge restart, the
rehearsal and the cleanup go in `script(1)`.

**The op side, run by the agent over SSH** (`ssh -i ~/.ssh/agentic_postgres_
ed25519 op@62.238.99.122 'bash -s' < /tmp/x.sh`, PATH exported, no inline
`$HOME`): `git bundle create /tmp/apg-<sha>.bundle 8d655b5..main` locally,
`scp`, `git fetch` the bundle on the host, `git rev-parse FETCH_HEAD` equal to
Run 9's sha, `git checkout <sha>`, the dependency diff printed and `uv sync`
only if it moved (D1766), the four fixtures and the two projects rendered
`--render-only` as `op` (outputs v19 on all four; **the render's approval-gate
line absent for beta** — 0004 guards the one gated tool; alpha has no
capabilities), `pytest --setup-plan` for the new live module with the
variables set, pointing at the op-owned copies; **the probe's own control**:
`s35-r10-probe.py` run for 10 s against both projects BEFORE anything moves →
every class answering its expected status, zero DOWN windows, zero 429s. **If
that control fails, nothing is handed to the operator.**

**The operator's sheets are in the appendix: F1 → F8, one outcome each, each
read by the agent before the next is issued (D1510).** Every `sudo` line has
nothing after it — no pipe, no redirect, no `$(`, no `&` (D1505); a transcript
comes from `script(1)` or the script's own tee, and the agent reads it over
SSH as `op`. **Around F2, F3, F4 and F7b the agent starts the probe as `op`
BEFORE handing the line (detached: `setsid nohup python3 … &` inside a staged
script, its PID and the stop-file path printed) and stops it AFTER reading the
transcript's last line** — the probe is the agent's, the deploy is the
operator's, and the two never share a terminal.

**Then, from the workstation, after the sweep:** `bin/session-35-check.sh
--mode external` through `~/s35r10/s35-r10-external.sh` (ephemeral
`ssh-agent`, `--ssh-destination op@62.238.99.122`, D466); fetch
`evidence/session-35-host.json` (`scp` as `op`); `write-session-evidence`
merges the three halves → `evidence/session-35.json`, exit 5 for the expected
reasons only (§7) — **every half must name Run 9's deployed commit** (D1641's
method if an instrument had to move, stated in the tag). `release-reading --ref
<deployed sha>`; `git tag -a 1.13.0 <deployed sha> -F /tmp/tag-msg.txt`; push
the tag.

**If something goes wrong** (read before the day): 0037 fails at step 6 on
alpha → **STOP, never amend it** (D912); read the ledger; a fix-forward 0038 is
a new run and a new deploy. **Beta's step 6 refuses with a proposal sentence**
→ the release directory lacks the committed proposal or the set's lock moved
after it was proposed: read `/opt/agentic-postgres/releases/<sha>/projects/
example/proposals/` as `op`, compare `set_digest` with the render's
`lock_sha256`; **never write a proposal on the host** (D971, D1852) — a repair
run on the workstation, a new commit, a new deploy. **`edge.sh restart` leaves
Traefik unhealthy** → `sudo bin/edge.sh --host host.yaml up` (the unit's own
path) and read `edge.sh status`; a limit too tight shows as an OOM kill in
`docker inspect`'s `State.OOMKilled` (root) — raise it by a repair run, never by
hand on the host. **A probe window longer than 120 s on a deploy** → the
probe's own control first (an endpoint that never answered is the instrument's
defect, not downtime). **The neighbour script's load container cannot resolve
`postgrest`** → the network or alias was read from the wrong document (the
DEPLOYED one names it, D1853). **`auth` does not come back after a deploy** →
`docker start` (ADR 0193's fallback), a row, and the sweep waits for `doctor`
12 ok. **A sweep proof fails on its instrument** → a `-k` iteration after the
repair, never a second sweep for a fixture (one sweep per trip; a second only
for a defect, or by the operator's explicit choice, D1774).

**Done** records: all deploys' step 0 lines, step 6's migrator line AND the
ledger (37 / 37 + 4), **beta's step 6 proposal line** and `status`'s proposal
line, the capability report line (beta), 6d/6e's lines, each probe window per
class per project with its length and the deploy's own `Recreated` lines, the
edge's window (both projects), Sheet F4's `docker inspect` values and `doctor
capacity`'s ceilings and `unbounded` count, `apg-diag logs auth` read as
`apg-agent`, the sweep's JUnit counts, every new claim's status, the four
neighbour phases' figures and conditions, the classifier's verdict, the
database-restart window, the retention counts (F8), the probe humans and agents
left, the merged document's totals, the tag and its message.

### Run 11 — the close: the envelope, the threat model's number, the Stage 5 decision report, the ledger

**Code (`src/agentic_postgres/capacity.py`) — commit, `bin/session-01-check.sh`
once detached, push, read CI (D1644).** Then documentation commits (no CI).

1. **`capacity.ENVELOPE`** gains, each a `Measurement(kind=MACHINE)` whose
   `conditions` name the host, the release, the commit, the date, the probe's
   budget and cadence, and the phase's loads: **deploy downtime per class**
   (REST, auth, storage, mcp, docs — one row per class with the alpha and beta
   windows; a class the deploy did not recreate says so), **the edge's
   recreation**, **the database restart** (*induced by the `database-restart`
   rehearsal, not a deploy*), and **the four neighbour phases** (the
   neighbour's p50/p95/p99, errors, 429s; the loaded side's achieved rate). The
   D1711 `UNMEASURED` row (`:613-640`) is REPLACED by a `Measurement` only if
   the classifier's verdict was *enough*; otherwise its reason gains Session
   35's reading and stays. `bin/render-capacity-envelope.py --write`;
   `test_capacity_envelope` (a MACHINE row may carry `p95`; a CONFIGURATION row
   may not, `:149-155`). **Every number is copied from the Done's transcript
   by a script** (`s35-r11-envelope.py` prints the Python literals it read, and
   the executor pastes them) — never retyped.
2. **`THR-NOISY-NEIGHBOUR`**'s residual cell: *"has not been measured"* replaced
   by the four phases' figures and their conditions, and the disk-I/O sentence
   kept (nothing bounds `blkio`).
3. **`docs/stage-5-decision-report.md`** (D1890), from `evidence/session-35.
   json` and the envelope ONLY, every number read and asserted by
   `s35-r11-fill.py` (kept in `~/s35r11/` and the scratchpad; its text in the
   Done), which refuses a placeholder left behind: the preamble (the document's
   totals and `source_commit`); **§1 What 1.13.0 is**; **§2 What was measured**
   (a `| Measure | Value | Source |` table: claims, passed, not_run, failed,
   requirements, ADRs, migrations, divergences, offline claims, the walk's
   record and who walked, `upgrade plan` on alpha and beta, the deploy windows,
   the neighbour figures, the host's memory and CPU); **§3 What stayed
   `not_run` or `failed`, and why**; **§4 What Stage 4 built against its
   specification** (the six sessions, each in one paragraph with its claims;
   what was deferred with hosting and what was cut, from the stage plan's
   §3/§6); **§5 The hosted question, priced against Stage 4's readings** (the
   stage plan's §6 precondition list, each item with the measured fact that
   bears on it: the host's declared capacity and what two projects already
   commit; what one project's load does to the other's p95; the edge's
   recreation window as the price of any shared-ingress change; the threat model
   rows a hosted reading would add; the retention bill from F8; the rotation
   performed once of four); **§6 Recommendation** — written by the executor
   from §1–§5 and marked as the executor's reading, which the OPERATOR accepts
   or rewrites before it is committed (the recommendation is a decision, and
   decisions here are the operator's). Indexed in `docs/README.md`'s evidence
   table (`test_documentation_index.py:454-472`).
4. **The records**: this plan's header rewritten (COMPLETE, the dates, the rows
   each run added, NEXT FREE); **`docs/scope-closure.md` §28** — *What Session
   35 closed, what it left, and what Stage 5 inherits* (closed: D1721's
   database half, D1523 as a record, D1524 as a measurement, D1586/D1710's
   unbounded edge, D380, D1856, D1883, D1882's prose; left: §10; inherited by
   Stage 5, in order, from the decision report's §6); `docs/plans/stage-4-
   plan.md`'s Status block rewritten to **STAGE 4 CLOSED** (1.13.0 on the
   deployed commit; the merged totals; `CURRENT_SESSION 35`; ADRs 245;
   migrations 37; requirements 291; claims 198); CLAUDE.md in the launch folder
   (**copy it to the scratchpad first** — it is not in git) rewritten
   compactly for Stage 5's planner; the project memory updated.

---
## 7. Evidence and claims

Unchanged rules (ADR 0163, 0202; D1237; D1543). **Ten claims land with the
constant** (D690): seven declared offline — each a property of a checkout (a
migration and a guard under a real cluster the gate requires Docker for, a
reading over committed text, a command's records over a tmp root, a gate over
files, compose and script text) — and three host, undeclared, first executed on
the trip. **Session 35 is the session whose subject is the ACT of changing a
deployment**, and its claims say so: `approval_in_database_live` is proved by
an agent's own token refused by the DATABASE on production with the row count
read as the superuser, never by a plane refusal; `proposed_set_applied` by the
deployed document's digest and the release directory's committed record, never
by the deploy's exit code alone (D145: an exit code is not a state).

| Claim | Mode | Moves on |
|---|---|---|
| `approval_in_database`, `destructive_lint`, `change_proposal`, `proposal_approval`, `proposal_gate`, `every_service_bounded`, `diagnostic_reach` | offline | Run 9's gate |
| `approval_in_database_live`, `proposed_set_applied`, `every_service_bounded_live` | host | Run 10's sweep — their proofs' **first execution anywhere** |
| every Session 33 approval claim (`workflow_approval_live`, `workflow_compensation_live`, `workflow_provenance_live`) and Session 34's (`event_wait_live`, `connector_delivery_live` — both call `set_note_embedding` as the OWNER, directly) | host | Run 10 — **the guard is now under every one of them**; the owner's calls must pass it (the human branch) and the approved call must pass it (the claim branch), so their passing again IS this session's evidence that the guard admits what it must |
| `deployment_convergence` | host | Run 10, `--redeploy-before-file` declared (the sentinel, as every trip) |
| `documented_path` | host | Run 10 — **whatever record Sheet W produced**: clean → `passed`; unclean or the Session 25 record again → `failed`; the report says which |
| the rotation trio, `replacement_host_restore`, `port_allocation` | — | `not_run`, unchanged |

**Expected merged document**: **198 claims — 192 passed, 5 not_run, 1 failed
(`documented_path`)** if every new claim passes and no clean walk arrives;
**193 passed, 5 not_run, 0 failed** if a clean record reaches the sweep. Any
other figure is read before the tag.

**Measurements are not claims** (the envelope's rule since Session 14): the
downtime windows and the neighbour phases enter `capacity.ENVELOPE` in Run 11
with their conditions, and the Stage 5 report quotes them from there.

---

## 8. Security invariants this session touches

| Invariant | Where 35 puts it at risk | Control |
|---|---|---|
| **PostgreSQL is the final authorization authority** (stage plan §8) | D1721 — an agent's direct call to a gated RPC | `app.require_approval` first in the gated function; granted to nobody; the claim, the header and the decided row all required; the row count after every refusal asserted (AGT-APPROVE-003/004) |
| **A workflow, a connector and a worker hold nothing an agent identity does not hold** | The approved call now meets the database | The guard reads the SAME claim the signer built from a decided row (`workflow_approval_for_token`'s predicate) — it adds a check, never an authority; a human's own write is unchanged |
| An agent cannot run SQL | The proposal; the gate | Neither takes SQL from a caller; `propose` runs the product's own `dev.sh`; the gate reads two files |
| **A human cannot run SQL through a product surface** | `bin/migrate.sh propose|approve` | Both write JSON records on a workstation; neither connects to a deployment |
| **A report may not substitute an answer for a failure to determine one** (ADR 0195) | The proposal's three unreadable readings; the render's gate line; the capability report; E0's `absent`; the probe | Each says *not applicable* or *cannot be read* with a reason (D1858–D1860, D1866); a file the kernel lacks prints `absent`; a probe endpoint that never answered is the instrument's failure, never downtime |
| **A decision may fail closed** | The host gate | It refuses an act with a fixed sentence; it never refuses a state (D1865) |
| No secret value in source, arguments or logs | `apg-diag`'s new reach | The fourth redaction rule; the 200-line cap; the proof over each service's real log shape (ADR 0245) |
| The MCP runtime holds no credential | The guard | Unchanged: the plane forwards the agent's token and holds no key; the guard needs nothing from it |
| One service cannot read another's credential | The edge's limits | Unchanged: limits only; no mount, network or environment moves on the edge |
| Projects share no project-scoped value | The neighbour sitting | Each project's load runs on ITS OWN internal network with its own probe identity; the probe crosses the edge like any caller |
| **There is no public Postgres endpoint** (ADR 0216) | The load container | It joins the project's `internal` network for its run and exits; no port, no listener, no router |
| **A workstation holds no production secret** | The approval | A declared name on a committed file; no credential exists or is created |
| `--render-only` keeps working with no host and no root | The approval-gate line; manifest 8 | The render REPORTS the gate and never refuses; both fixtures render at 8 |
| A restore never overwrites the active volume | The database-restart rehearsal | Unchanged path; it restarts, it does not restore |
| The deploy, the sweep and the tag land on one commit (D1425) | Run 10 | The sheets' order; D1641's method if an instrument moves |
| Never grant `op` the docker group | The probe, the sampler | The probe crosses the edge as any caller; the sampler reads `/proc` (D1739); the load and the neighbour script are root's, on a sheet |

---

## 9. Stop conditions

- **Rig 35a**: `apg_approval` does NOT arrive in `request.jwt.claims`, or the
  `Idempotency-Key` header does not arrive in `request.headers`, on the
  approved path: stop — D1867's premise is false; ADR 0242 is rewritten before
  Run 2 (the alternative is a plane change, priced as its own row).
- **Rig 35a**: a request role CAN execute the prototype guard, or PostgREST can
  address a function in `app`: stop (D1779's premise, re-measured).
- **Rig 35a control A**: the ungated function REFUSES the agent's own token:
  stop — something already enforces what D1721 says nothing does; the row is
  rewritten to say what.
- **Sheet E0**: `memory.peak` or `pids.peak` reads `absent` for any container
  Run 5 bounds: stop; the limit is re-planned against a sampled reading.
- **Run 5**: admission's `decide` charges `mem_limit` caps rather than
  `unreclaimable_mb`: stop before the commit — bounding three services would
  move admission's arithmetic for every project, which is a decision.
- **Run 5**: a proposed edge memory limit is below 2 × the edge container's
  `memory.current` on E0: stop; the peak's window was too short to trust.
- A passing test would be weakened — including `test_api_migrations.py`'s pins
  (0037 is NOT `api`; they must not move), any scope-set equality, the
  twelve-check proof, `test_the_loop_starts_in_auth_mode_only`,
  `test_every_transport_in_the_service_is_declared_with_a_reason`, or any
  `test_session12_documented_path` guard. **The ONE replacement this plan
  authorises is D1877's, under ADR 0244.**
- A proof of the guard asserts a SQLSTATE without the row count (D1773's lesson
  — a proof that cannot go red is a finding): rewrite it before the commit.
- The example set's lock moves after Run 4's proposal is committed: stop —
  either the change is reverted or a new proposal and a new approval (Sheet A1
  again) are made; the host gate would refuse beta's deploy.
- Run 9's `upgrade plan` prices `1.13.0` at **major**, shows
  `operator_digests_moved` non-empty with the installed manifests, or a
  differing leaf D1889 did not predict whose class is not `implementation`:
  stop; a row; the operator's decision.
- **F1**: the new doctor over the old substrate reads anything but 11 ok +
  `migrations` PROBLEM: stop before the deploy (Session 34's D1848 was found
  exactly here — the reads sheet is read whole).
- 0037 fails on alpha at step 6: stop; **never amend it** (D912).
- Beta's step 6 refuses with a proposal sentence: stop; a workstation repair
  and a new commit — never a file written on the host.
- `edge.sh restart` does not bring Traefik back healthy within its `--wait`:
  `sudo bin/edge.sh --host host.yaml up`, then stop and read before anything
  else is handed over.
- The probe's pre-trip control reads a DOWN window or a 429: nothing is handed
  to the operator until the instrument is repaired.
- Any run finds itself building a lock-risk estimate, a retention plane, a
  proposal for workflows or connectors, a capability REFUSAL at deploy, a
  resolver of operator identity, or a change to the plane for D1721: stop — each
  is named in §1 as not this session's.
- A port, a new router, a route to a store, a non-loopback bind, or a published
  load generator, for any reason (ADR 0216).
- CI red on a code commit: stop and read the failed job's log by id; a
  cancelled run is not a failed one (D1059); re-run only the module that
  failed, locally.
- WSL has lost outbound TCP on trip day: CLAUDE.md §1; a Windows reboot early.
- The Stage 5 report would carry a number the filler script did not read from
  the evidence document or the envelope: stop; D1890.

---

## 10. Open items this session carries and creates

**Carried in, untouched, each still true:** D1045; `replacement_host_restore`
(D1028); D1375; the 21 unclaimed requirements; D976, D688, D771, D340, D466,
D540, D942, D1203, D1205, D1211; the Infisical control-plane identity's org
admin; `process-max` 1 (D593); the three rotations Session 30 did not perform
and the retired JWKs; the mirror's upstream flake (D1546); `apg-diag`'s standing
account (D1528 — now reading nine services, still without a lifetime); ADR
0162's missing row for an option (D1561); **D1642** (a kit names the checkout's
commit); **D1547** (`delete_note` — this session moves no `api` contract);
**D1581/D1713** (why a deploy recreates what it does — Run 10's `Recreated`
lines are read beside the probe's windows, and if they identify it, a row says
so); D1722's HUMAN half (D1870); D1798 (redelivery); D1784, D1792, D1855; ADR
0241's two-version bound; the out-of-order 1.9.0/1.8.0 rows in the upgrade
guide's table; `upgrade plan`'s blindness to a post-Session-2 secret (D1825).

**Created or left here:**

| Item | Note |
|---|---|
| **A profile-added approval on a release tool is a plane control only** (D1869) | The database cannot read a deployment's profile; a rendered table of gated tools would be new construction. |
| **The guard does not make a project function idempotent** (D1871) | A replay inside the step token's life writes again; the example's upsert keeps one row. A project that needs exactly-once must use ADR 0181's claim, which a project set cannot reach (`app_private`) — a release helper for projects is priced here, not built. |
| **The proposal's names are declared** (D1864) | No operator identity exists; ADR 0243 says what the record is. A Stage 5 hosted reading with real users would make an authenticated reviewer possible and necessary. |
| **Three readings a proposal cannot take** (D1858–D1860) | A project-set change's upgrade class; the client drift before a deploy; the harness's outcomes. Each is a reader nobody has built. |
| **A capability change is reported, not refused** (D1866) | Refusing needs a deployed-lock comparison and a transition rule. |
| **No proposal for a workflow or connector definition** | Stage plan §6 (`WorkflowProposal` not built); they are installed by 6d/6e from committed files, reviewed only by `validate`. |
| **Retention** (D1886) | Ten tables never pruned; F8's counts are the bill, in the Stage 5 report. |
| **The load and the probe are trip scripts, not product verbs** | A later session that wants a repeatable neighbour reading promotes them with a contract. |
| **A second walk of 1.13.0** | Budgeted (the stage plan's §10) if the first records more than eleven undocumented steps; ADR 0207 allows two per release. |
| **Disk I/O is bounded by nothing** | `THR-NOISY-NEIGHBOUR` keeps the sentence; no `blkio` limit, one device. |

---

## Appendix — what to consult, how a run is executed here, the rigs, and the sheets

**Consult, in this order:** this plan's §1 and §5. The stage plan's §5
*Session 35*, §6, §8, §9, §11. `docs/scope-closure.md` §27.
`docs/plans/session-34-implementation-plan.md` §1 (D1812–D1856 — what executing
34 found), §5 Runs 1, 9, 10, 10a–10c, §10 and Sheets D1–D9.
`docs/plans/session-33-implementation-plan.md:439` (D1721) and `:2469` (§10's
pricing), and its Run 1 rigs 33a/33b. ADR **0195** before any reader; **0231**
(the claim this session's guard reads); **0235** (the `app`-and-nobody
precedent); **0181/0182** (the key; the dry run); **0198/0206/0210/0240** (a
project set, its order, its declared `follows`); **0207** (the walk); **0213**
(a reading with no threshold; a horizon); **0155** (a deploy recreates what
changed); **0162** (what a bump permits); **0071** (`apg-diag`); **0190/0193**
(rehearsals); **0216/0217** (no public endpoint; no hosted trust model); **0218**
(`container_exec`); **0221/0222** (admission; the 4× limit method); **0241** (an
existing deployed document is read by version — any reader this session adds of
an existing document goes through `deployed_output.read_deployed_document`, and
the class guard will say so).

**How a run is executed here** (CLAUDE.md §1 and §5, the parts that bite): the
Bash tool is Git Bash; every WSL command is `wsl bash -lc "cd
~/projects/agentic-postgres && . .venv/bin/activate && …"`; anything with a
loop, a nested quote, a `$`, a heredoc or a process substitution goes in a
script file written with the Write tool to `\\wsl$\Ubuntu\tmp\` and run with its
output redirected to a file that is `rm`'d first; **never pipe a gate into
`tail`**; a long gate runs detached with its exit code written from inside;
`chmod 755 bin/*.sh bin/*.py deploy.sh` before every `git add`; commit messages
from a file with `-F`; `PYTHONDONTWRITEBYTECODE=1` and `__pycache__` cleared
before a battery; restore by copy and `cmp`, never `git checkout --`; every
anchor pre-flighted to match exactly once and a miss fatal; a mutation is
evidence only beside a control it cannot reach, in the same invocation; assert
HOW each mutation failed; `--setup-plan` with the variables SET before a trip.
**Any Python that imports `agentic_postgres` outside pytest needs
`PYTHONPATH=src`.** **Every `service_source.load(...)` proof reads the service's
module from `services/auth-api/app/`, not `src/`.** **A `sudo` line on any sheet
has nothing after it**, and every sheet is grepped for `|`, `>`, `$(` and `&` on
every `sudo` product line before it is handed over (D1505). **`docker run …
python - <<'PY'` needs `-i`** and is a heredoc — write the Python to a file and
mount it instead. **Nothing is ever written into the host checkout** (D1852):
backups and records live in `/home/op/`.

**The rigs, summarised** (Run 1, each a script, each with a control, each naming
its images by digest):

| Rig | Subject | Control | Owes |
|---|---|---|---|
| 35a | the approval claim and key header in SQL; the guard's decisions; the plane's approved path through a guarded function | an ungated twin serves the agent's own token; no role may execute the guard | D1867, D1871, the 403 body |
| 35b | `apg dev up`'s exits and lines; the surface reading | `status` after `down` | D1859, D1861 |
| 35c | the edge's rate limit: shared or per router | 10/s total → no 429 | D1874 |
| 35d | what a caller sees when a backend stops or is recreated behind Traefik's Docker provider | a steady 200 | D1875 |
| 35e | a 0.1-s unprivileged sampler | `docker stats` | D1876 |

### Sheet E0 — the host's readings, before any limit is written (Run 1; `sudo`; the script tees its own transcript)

    sudo bash /home/op/s35-r1-e0.sh

→ one table per running compose container (limits, `memory.current`,
`memory.peak`, `anon`, `pids.current`, `pids.peak`, start time), then `nproc`,
`uname -r`, `free -m`, `df -h /`. Nothing restarts.

### Sheet A1 — the approval (Run 8; the operator at the workstation, NOT `sudo`)

    cd ~/projects/agentic-postgres && bin/migrate.sh approve --project project.example.yaml --proposal <digest> --by "<your name>"

→ one line naming the approval file. The agent commits it.

### Sheet W — the third reader (Run 8; a decision, recorded verbatim)

(a) a person; (b) a fresh model session under ADR 0207 §1; (c) no walk for
1.13.0 — Run 8's text.

### Sheet F1 — the reads (all `sudo`; the script tees its own transcript)

The agent stages `/home/op/s35-r10-c1.sh` (derived from `s34-r10-c1.sh`: every
child with stdin `/dev/null`) containing: `bin/upgrade.sh check --project
alpha-dev` and `beta-dev` → `verdict OK`; `bin/doctor.sh --project alpha-dev`
and `beta-dev` → **11 ok + `migrations` PROBLEM (36 of 37; beta 39 of 41)** —
the NEW doctor over the OLD substrate, as D1770 recorded for 33 and Sheet D1
for 34; `bin/fleet.sh` → 2 projects at `14b1b9d`; `bin/backup.sh --outputs
/etc/agentic-postgres/projects/<key>/outputs.json info` for both → a full
exists; `bin/upgrade.sh plan --project <key> --candidate /home/op/agentic-
postgres/.generated/<key>/outputs.json --json --also migration_added` for both
→ `bump minor`, `requires minor`, `OK`; `bin/dr-kit.sh export … --output
/home/op/kit-<date>-pre` (the exact line from `--help`, printed on the sheet by
the agent). The operator runs, at a terminal, nothing after it:

    sudo bash /home/op/s35-r10-c1.sh

### Sheet F2 — the sentinel, then alpha, with the probe (`sudo`)

1. **F2a** — the sentinel, `/home/op/s35-r10-sentinel.sh` (derived from
   `s34-r10-sentinel.sh`; the secret path DERIVED from
   `active-secret-generation.json`), title `s35-redeploy-sentinel-<YYYY-MM-DD>`,
   before-file `/root/s35-redeploy-before.json`:

       script -q -e -c "sudo bash /home/op/s35-r10-sentinel.sh" /home/op/s35-r10-sentinel.txt

2. **The agent starts the probe on alpha** (all five classes, the budget of
   D1874) and says so. **F2b** — the deploy, at the terminal, nothing after
   this line:

       script -q -e -c "sudo ./deploy.sh --host host.yaml --project project.alpha.yaml --capabilities capabilities.yaml --through-session 35" /home/op/s35-deploy-alpha.txt

   → exit 0. Step 0 `admitted`. **Step 6 applies ONE migration** — the ledger
   is what is read (D941); alpha has no set, so no proposal line. Recreated:
   read the lines, do not predict them (expected: pgbouncer, postgrest, docs for
   their new `mem_limit`; auth, storage, mcp, docs for the image). **The agent
   stops the probe** and reads its windows. Then:

       sudo bash /home/op/s35-r10-after.sh alpha

   → `migrate.sh --runtime status` 37 `[X]` lines, `Pending: 0`; `doctor` **12
   ok**.

### Sheet F3 — beta, with the probe (`sudo`)

The agent starts the probe on beta. Then:

    script -q -e -c "sudo ./deploy.sh --host host.yaml --project project.beta.yaml --capabilities capabilities.yaml --through-session 35" /home/op/s35-deploy-beta.txt

→ exit 0; 0037 applied AND the set's `0004` — **only because the committed
proposal names the set**: step 6's output carries the proposal's digest;
ledger **37 + 4**, `Pending: 0` twice; the capability report line; 6d seven
definitions; 6e four connectors `unchanged` (all still disabled). The agent
stops the probe. Then `sudo bash /home/op/s35-r10-after.sh beta` → `status`'s
line `proposal <digest16>: present, approved by <the operator's declared name>`;
doctor 12 ok.

### Sheet F4a — the edge, recreated, with the probe on both projects (`sudo`)

The agent starts the probe on BOTH projects (`rest` and `auth` each — the
budget holds). Then:

    script -q -e -c "sudo bin/edge.sh --host host.yaml restart" /home/op/s35-r10-edge.txt

→ exit 0; both containers recreated; `reconcile` attached every project
network. The agent stops the probe; the window is the EDGE class for both
projects. If Traefik is not healthy: `sudo bin/edge.sh --host host.yaml up` and
§9.

### Sheet F4b — the edge's limits read, and `apg-diag` re-installed (`sudo`, two lines)

    sudo install -o root -g root -m 0755 bin/apg-diag.sh /usr/local/bin/apg-diag
    sudo bash /home/op/s35-r1-e0.sh

→ the edge's two containers now carry the limits; `doctor capacity` (in the
E0 script's tail) → **0 unbounded**. The agent then reads, as `apg-agent`,
`sudo apg-diag logs auth` (a line count ≤ 40, nothing unredacted).

### Sheet F5 — the pre-sweep readings (`sudo`)

    sudo bash /home/op/s35-r10-readings.sh

(from `s34-r10-readings.sh`): `doctor capacity --host host.yaml` (ceilings
risen by the three services' caps and the edge's); `doctor --project beta-dev`
(the BEFORE counts); `doctor usage --project beta-dev` (exit 6 expected,
D1712); then, LAST, the two op-owned copies installed (`install -o op -g op -m
0600 …`, D1767) — **the agent confirms both name Run 9's `source_commit` before
F6**, and copies the walk record (if Sheet W produced one) to
`/home/op/session-35-dx-record.json`.

### Sheet F6 — the sweep (`sudo`)

    sudo bash /home/op/s35-r10-launch.sh

It detaches the sweep (with `--dx-record-file` naming the new record, or the
Session 25 record under Sheet W's (c)) and returns at once; ~46 min; the agent
reads `/home/op/s35-r10-host.code` (0 or 5) and the summary.

### Sheet F7a — the neighbour sitting (`sudo`)

    script -q -e -c "sudo bash /home/op/s35-r10-neighbour.sh" /home/op/s35-r10-neighbour.txt

(~12 min: four phases of 120 s and their setup; the sampler runs inside phase
B) → four phase documents under `/home/op/s35-r10-neighbour/`, the probe
identities it left, and exit 0. **Never during or before the sweep** — the
sweep recreates services early (D1711).

### Sheet F7b — the database restart, with the probe (`sudo`)

The agent starts the probe on alpha. Then:

    script -q -e -c "sudo bash /home/op/s35-r10-rehearse.sh" /home/op/s35-r10-rehearse.txt

(the agent writes the exact `bin/rehearse.sh` lines from its `--help`:
`--plan` first, then `database-restart` on `alpha-dev`) → the rehearsal's
verdict; the probe's window is the DATABASE class, labelled *induced by the
rehearsal*.

### Sheet F8 — the cleanup and the retention reading (`sudo`)

    script -q -e -c "sudo bash /home/op/s35-r10-cleanup.sh" /home/op/s35-r10-cleanup.txt

(from `s34-r10-cleanup.sh`): the sentinel removed (container, database and
title DERIVED from the deployed document and the before-file; expect `DELETE
1` — D1547); the neighbour sitting's and the proofs' notes removed by their
canary titles (expect the counts the scripts printed); every connector still
disabled (read, never changed — nothing enabled one); **the retention reading**
(D1886): for both projects, each of the ten `app_private` tables' `count(*)`
and oldest timestamp, as `postgres` through `container_exec.run`; `doctor
--project beta-dev` (the AFTER counts); `bin/dr-kit.sh export … --output
/home/op/kit-<date>-post`. The agent then fetches the transcripts, the probe
and sampler files, the sweep's evidence half and the rehearsal evidence by
`scp` as `op`, and copies the two new kits off-host to `~/dr-kits/` in WSL
(verified there, 0700/0600 kept on ext4 — and, after D1856's repair, the
`projects/` directory already 0700 on the host).
