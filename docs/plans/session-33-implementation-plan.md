# Session 33 — Gates, compensation and provenance

**Status: IN EXECUTION since 2026-09-26 — Runs 1–4 done (D1742–D1751 added;
NEXT FREE D1752). Run 5 is next.** Planned 2026-09-26 at `7b0d308`. Ten runs, all on
`main` directly. This plan spends **D1714–D1741** in §1 and **ADR 0230–0234**.
**NEXT FREE AFTER THIS PLAN: D1742, ADR 0235.** Rows the runs add go in §1's
second table, below D1741, in execution order; the header's *Status*
paragraph is rewritten at the close to say which run added which.

**Brief:** `docs/plans/stage-4-plan.md` §5 *Session 33* whole (Builds / Already
true / Must not / Measures / Closes), its rows **D1521** (the second half:
approval steps, `wait` steps, compensation, `apg workflow inspect` as
provenance, `pause|resume` not built), **D1527** (`THR-APPROVAL` before code),
**D1525** (33 owes NO rehearsal scenario — 31, 32 and 34 do), §2.3's row for
**D1248** (the audit filters, *"because the provenance reader needs a window,
an outcome filter and a cursor"*), §7's row for 33 (`WF-*` extended;
`audit_boundary_reported` re-run because the audit reader changes), §8 whole
(the rows marked 33: *a step is a tool call under the same scope check* —
compensation; *a revoked token stops on its next request*; *an agent record
carries no URL, key, token or caller value* — provenance; *a report may not
substitute an answer* — `workflow status|inspect`), §9's stop conditions, §10's
*"a second principal is a second set of scopes to keep honest. Session 33 owns
`workflow_approve`'s place in the derived vocabulary (ADR 0200) and the proof
that the requester cannot hold it for its own run"*, and §11. Plus
`docs/scope-closure.md` §25 *What Session 33 inherits, in order* (five items:
the substrate's nine functions by name; `approval_required` still a terminal
refusal; the `wait` park already built; D1248 for `inspect`; the second
principal's scope — *it approves, it may not act*, with D1638 and D1704 as the
two places the product already met the question), §25's *What it left* rows
(D1707, D1711, D1712, D1713, D1705, D1704, D1700, D1642, D1547), and
`docs/plans/session-32-implementation-plan.md` §10 (the items 32 created for
33) and its Run 8 sheets B1–B6 (the trip's shape).

**Shape:** ten runs. Run 1 is documentation (rigs, `THR-APPROVAL`, five ADRs)
and **reads no CI verdict**. Runs 2–8 change code: each pushes and reads that
commit's own CI verdict by full SHA (`gh api "repos/Virabyan99/agentic-postgres/
actions/runs?head_sha=<40 chars>" --jq '.workflow_runs[] | [.name, .status,
.conclusion] | @tsv'`, judged on HTTP status, three buckets — success / failure
/ not registered; an empty list is not a verdict, D1057). Run 9 is the trip.
Run 10 is the close and — **D1644** — commits, gates and reads CI if it
touches `src/` (it will: the envelope).

**Product version at close:** `CURRENT_SESSION` **33**; `template_version`
**`1.11.0`** — **migration 0035** (two new `app_private` tables, one new
enum and one new value on an existing enum, four new columns on the step and
run tables, nine new definer functions of which one is granted to nobody,
five 0034 functions replaced in place with unchanged signatures, the audit
reader re-created at a new arity, one index), **one new administrative scope** (`admin_workflows:approve`, in
`schemas/capabilities.schema.json`'s administrative enum — it moves every
compiled lock's `vocabulary.administrative` member and therefore recreates
`auth` and `mcp` on deploy, ADR 0200 §2), **four new routes on the auth
service** for HUMAN access tokens (`GET /admin/workflows/approvals`, `POST
/admin/workflows/runs/{run_id}/approve`, `POST /admin/workflows/runs/{run_id}/
reject`, `GET /admin/workflows/runs/{run_id}`), **three new query parameters
and a cursor on `GET /admin/audit`**, **one optional token claim**
(`apg_approval`, minted only on a step token), **four new verbs on
`bin/workflow.sh`** (`approvals`, `approve`, `reject`, `inspect`), **two new
definition keys and one new step kind** (`approval`, `compensation`, `wait`),
**two new example definitions** (`tasks-approval`, `tasks-compensate`), and
**the three carried-in defects** D1707, D1712, D1705. **No outputs, capability
manifest, lock, secret or host schema moves; no new deployed-document field; no
new container, role or secret; no new rehearsal scenario** (§1 D1737). ADR
0162: a new released migration and new API operations are each *minor*;
`upgrade plan` reads them only when declared (D1703), so Run 8 declares
`--also migration_added --also api_operation_added` and the release paragraph
says the floor is minor **by declaration**. A `major` is §9's stop.

**Written for whoever picks this up cold, and it will be a different model
than the one that planned it.** Every path below was read from the tree on
2026-09-26 at `7b0d308` — four explore passes over `services/auth-api/`,
`src/`, `bin/`, `migrations/`, `schemas/`, `tests/` and `docs/`, plus direct
reads of migration 0034, `workflow_worker.py`, `workflow_routes.py`,
`service.py`, `claims.py` and `mcp_tools.py` — and is cited by `path:line`.
Every third-party or product claim is measured in Run 1's rigs with a control,
or is marked as the measurement a run owes — never assumed. **Read CLAUDE.md §1
in the launch folder before the first command, then this plan's §1, then the
appendix.** If a step here and the tree disagree, **the tree wins and the
disagreement is a divergence row** (next free `D` after §1's table), never a
silent reconciliation. **When this plan names a line number, open the file at
that line and read the surrounding twenty lines before editing** — the numbers
were right on 2026-09-26 and `ruff format` moves them.

**The five sentences the executor most needs, in case nothing else is read:**

1. **An approval step parks on the PLANE's own refusal, and resumes on a
   human's recorded decision** (§1 D1714, ADR 0230). The worker calls the tool
   the first time exactly as it does today; the plane refuses with
   `approval_required` and audits the refusal; the worker records a PENDING
   approval and parks the step with its expiry as `resume_after`. A human with
   `admin_workflows:approve` — who is not the run's owner, and cannot be the
   agent, because an agent token is refused by `authenticate` — approves or
   rejects. **A rejection is a cancel.** Nothing in the loop decides whether a
   capability needs approval; the lock does, through the plane.
2. **An approved call reaches the plane with a signed claim, not a flag**
   (§1 D1715, ADR 0231). `step_token(agent_id, approval_id=…)` reads the
   approved decision from the database and adds `apg_approval: {id, tool,
   key}` to the ONE token it mints for that attempt; the plane accepts a
   `requires_approval` write only when that claim names the tool being called
   and the idempotency key being presented. Nobody but the signer can mint the
   claim, and `/auth/agent-token` never does.
3. **Approval is a control on the GOVERNED path, not in the database** (§1
   D1721). `api.set_note_embedding` is granted to `agent_writer`
   (`projects/example/migrations/templates/0002-agent-grants.sql:27-28`) and
   checks no approval. An agent token presented to PostgREST directly reaches
   it. That is ADR 0179's existing posture; Run 1 MEASURES it (rig 33b), the
   `THR-APPROVAL` row states it as the residual, and §10 prices the database
   half. **This plan does not silently claim more than the plane enforces.**
4. **Compensation is a set of ordinary write steps, appended in reverse when a
   run fails or is cancelled, run as the same agent under the same checks**
   (§1 D1725, ADR 0233). The run's status is `compensating` while they run and
   returns to `failed` or `cancelled` with `compensation_outcome` `complete` or
   `incomplete`. **Never a rollback**: in beta's lock only
   `update_task_status` has an inverse (D1726) — `create_note` has none
   because `delete_note` does not exist (D1547).
5. **The provenance reader is one definer function joined by the plane's
   request id across EVERY attempt, read by a human auditor** (§1 D1728–D1729,
   ADR 0234), and **the audit filters are a separate deliverable that answer
   D1248's own objection** (§1 D1730): a filtered page carries the window's
   counts by outcome, so a viewer asking for `outcome=committed` still sees
   how many refusals the window holds.

---

## 0. Where the session starts

```
HEAD            7b0d308 on main, local = origin, clean. Deployed: 275a19e
                (1.10.0) on both projects; `git diff --name-only 1.10.0..HEAD`
                filtered to src/ bin/ services/ migrations/ templates/ schemas/
                compose.yaml deploy.sh VERSION names ONE file,
                src/agentic_postgres/capacity.py -- the envelope's DATA
                (Run 9 of Session 32; D1641's caveat). Re-run the filter in
                Run 1 and write the answer in its Done.
VERSION         1.10.0. CURRENT_SESSION 32 (src/agentic_postgres/__init__.py:623;
                the Session 32 paragraph :555-622). Outputs schema 18.
                host.yaml schema 3. Capability manifest schema 4. Lock
                schema 4. Project lock 3. Project manifest 6. api-surface 2.
                Workflow definition schema_version 1. 34 released migrations
                (0034 = 20260917120034).
REGISTRY        251 requirements. 158 claims (32 declared offline,
                src/agentic_postgres/evidence_claims.py:106-233; CLAIMS
                :280-1008, Session 32's block :485-504; CLAIM_INTRODUCED_IN
                lives in tests/contract/test_evidence_claims.py:953-1177,
                Session 32's rows :1124-1139). 229 ADRs. ID families
                (tests/contract/test_acceptance_registry.py:94): DEP CFG DBX
                SEC API AGT STO REC OPS DX REL CAP IDN EVAL FLEET TEN DEV EVD
                GEN STU NODE WF. NEXT FREE: D1714, ADR 0230.
EVIDENCE        evidence/session-32.json: 158 claims, 152 passed, 5 not_run,
                1 failed (documented_path by decision). not_run:
                port_allocation (no reboot, D1568), the rotation trio (four
                rotations needed; none performed since Session 30),
                replacement_host_restore (D1028).
HOST            62.238.99.122, measured 2026-09-26 17:50 as op: checkout
                176a7f0 (clean), up 8 days since the 2026-09-17 reboot,
                kernel 7.0.0-31, 3814 MiB total / 2038 available, no swap,
                22 docker scopes. Both projects at 1.10.0, source_commit
                275a19e, deployed_through_session 32 (read from
                /home/op/alpha-dev-outputs.json and beta-dev-outputs.json,
                D1631's names). Doctor 12 ok each (Session 32's close).
                Parent host scripts: /home/op/s32-r8-{checkout,renders,
                sentinel,b1,after,readings,gate,launch,cleanup}.sh and
                s32-r8b-{checkout,gate,launch}.sh; WSL copies in ~/s32r8/
                with s32-r8-external.sh. Retired JWKs
                /home/op/s30-retired-<key>-jwk.json (unread by any sweep).
                Kits through kit-2026-09-26-post.
```

**What exists, measured at `7b0d308`, and the session builds on:**

- **The substrate** is `migrations/templates/0034-workflow-substrate.sql`
  (1,064 lines). Three enums (`:119-140`): run status `queued, running,
  succeeded, failed, cancelled, stopped`; step status `queued, claimed, parked,
  succeeded, failed`; step outcome `succeeded, replayed, dry_run, failed,
  refused, token_refused, abandoned`. Four tables: `workflow_definition`
  (`:158-168`), `workflow_run` (`:196-210`, `timeout_seconds CHECK BETWEEN 1
  AND 3600`), `workflow_step` (`:250-272`, `timeout_seconds CHECK BETWEEN 1 AND
  600`, `idempotency_key` 0029's pattern, `request_id` the PLANE's id for the
  LAST attempt only, `:240-249`), `workflow_worker` (`:304-309`). Nine
  functions: `workflow_install_definition` (`:333-372`, granted to nobody),
  `workflow_enqueue` (`:398-472`, the agent's STORED scopes against
  `required_scopes`, one key per (run, step) `'wf-' || run || '-' || name` at
  `:463`), `workflow_claim_step` (`:509-640` — applies requested cancels
  `:551-559`, fails timed-out RUNNING runs `:561-568`, then claims the lowest
  position whose earlier positions all `succeeded` `:570-587`, `FOR UPDATE OF s
  SKIP LOCKED`; returns `step` as `(d.body -> 'steps') -> (s.position - 1)` at
  `:627` and `prior` as `jsonb_object_agg(name, result)` of succeeded steps at
  `:629-633`), `workflow_finish_step` (`:673-751`, `lease_lost` on a lost
  holder, `token_refused` → run `stopped`/`agent_not_active`, `abandoned` →
  step back to `queued`, anything else → run `failed` with `stopped_reason =
  p_reason`), `workflow_park` (`:773-801` — **a parked step with a NULL
  `resume_after` is never claimed**, because the claim tests `resume_after <=
  now()`, `:577`, and the comment at `:767-772` names this as Session 33's
  `wait`), `workflow_cancel` (`:817-854`), `workflow_run_status` (`:863-916`),
  `workflow_heartbeat` (`:932-955`), `workflow_counts` (`:968-1002`). Eight
  granted to `{{auth_service}}` (`:1045-1056`), `RESET ROLE` below them.
- **The loop** is `services/auth-api/app/workflow_worker.py` (605 lines).
  `RETRYABLE_TOKENS = frozenset({"write_conflict"})` (`:95`); the plane's
  address is three constants bound by a proof (`:109-111`, D1685); `resolve()`
  substitutes `{{input.k}}` and `{{steps.name.field}}` per attempt (`:187-230`;
  a whole-string reference keeps its type, an embedded one interpolates JSON —
  **`docs/workflows.md:78-79` says the opposite**, §1 D1740);
  `classify(status, body)` (`:302-340`) reads 401/403 as `token`, a 200 with
  `result.isError` as a refusal FIRST (D1672), the token being the text before
  `": "` (`:343-359`); `call_arguments(step)` (`:367-386`) adds `resource` for a
  relation read and `idempotency_key`/`dry_run` for a write; `process()`
  (`:389-527`) mints (`service.step_token`, `:407`), resolves, checks the
  monotonic deadline, calls through `_send` (`:238-265`, `urllib`, reads the
  RESPONSE's `X-Request-Id`), classifies, then finishes or parks — **a refusal
  whose token is `approval_required` today falls to the last branch and
  finishes `refused`, failing the run**. `del token` in a `finally` (`:477-480`)
  is asserted by an AST proof. **What the loop stores as a step's result is the
  whole JSON-RPC `result` object** (`:333-340`, `:488`) — the `{content,
  isError, …}` envelope, not the tool's `{tool, row_count, row, dry_run}`
  dictionary; on a real plane `{{steps.x.row}}` therefore cannot resolve (§1
  D1724, inferred from the code and owed a measurement by rig 33c).
- **The repository** `services/auth-api/app/workflow_repository.py` (256
  lines): `ClaimedStep` (`:50`), `WorkflowRepository` (`:82`) with `heartbeat`
  `:94`, `claim` `:103`, `finish` `:145` (`workflow_finish_step(%s, %s, %s,
  %s::jsonb, %s, %s)` at `:171`), `park` `:177`, `enqueue` `:201`, `cancel`
  `:224`, `status` `:239`, `counts` `:248`. Every statement is `SELECT
  app_private.workflow_…(%s, …)` with parameters.
- **The agent routes** `services/auth-api/app/workflow_routes.py` (264 lines):
  three routes behind `authenticate_agent` (`:150-151`), `_translate` mapping
  `PT404` → `no_such_workflow` and `PT403` → `scope_not_held` or 401 by the
  function's own message (`:130-147`), `_workflow_guard` layered over
  `routes._guard` (`:154-171`). Mounted in `main.py:304`; the lifespan starts
  the loop in `auth` mode only (`main.py:177-210`); the published route list at
  `main.py:454-465`.
- **Two authenticators** (`services/auth-api/app/service.py`): `authenticate`
  (`:296-383`) accepts `token_use == "access"` only (`ACCEPTED_TOKEN_USE`,
  `:53`), loads `auth_user_state`, compares status, `credential_version`,
  `authz_version`, role and scopes, returns `Principal(user_id, role_name,
  scopes, state)` (`:78-85`); `authenticate_agent` (`:551-628`) accepts
  `token_use == "agent"` only (`AGENT_TOKEN_USE`, `:68`) and returns
  `AgentPrincipal(agent_id, role_name, scopes, authz_version)` (`:88-106`) —
  **each refuses the other's token use**, so an agent can never reach a route
  guarded by `authenticate` + `require_scope` (`:385-394`, typed to
  `Principal`). `issue()` (`:224-292`) builds the payload from the stored
  record, refuses a stored scope beyond the role's ceiling rather than
  truncating (`:249-258`), and runs `claim_contract.verify_claims` before
  signing (`:284`). `step_token(agent_id)` (`:524-549`) is `_agent_record`
  (`:485`) + `_refuse_unless_issuable` (`:509`) + `issue(…, token_use=
  "agent")`.
- **The claim contract** `services/auth-api/app/claims.py` (155 lines):
  `REQUIRED_CLAIMS` (`:57-70`, twelve names), `TOKEN_USES = ("access",
  "agent")` (`:52`), `verify_claims` (`:83-155`) checks that the required
  claims are PRESENT and well-formed and **says nothing about extra claims** —
  an extra claim passes it (read, not yet measured end to end: rig 33a). The
  database holds the same twelve as a literal in `app_private.
  auth_contract_state` (`0011-identity-registry.sql:226-237`), tied to
  `jwt_claims.sql_required_claims()` by `test_jwt_claims.py:179-186` and
  `test_identity_registry.py:209`.
- **The approval refusal** is `mcp_tools.invoke_write` (`services/auth-api/app/
  mcp_tools.py:547-652`): `_write_for` (the scope check, `:580`, `:225-257`),
  then **`if entry.requires_approval: raise AgentVisible(APPROVAL_REQUIRED,
  "this capability requires an approval this deployment cannot grant",
  APPROVAL_REQUIRED_REASON)`** (`:583-596`), then the dry-run permission
  (`:603-608`), the key (`:612`), the request (`:615`), `execute_write`
  (`:620-628`). The token reaches it as `token=current_token()` from
  `register_write`'s closure (`:1067-1110`); the verified claims are reachable
  through `fastmcp.server.dependencies.get_access_token().claims`
  (`mcp_authorization.py:204-206`; `AgentTokenVerifier` builds the
  `AccessToken(…, claims=verified)` at `mcp_runtime.py:319-325`). The refusal
  is audited `refused` with `denial_reason = approval_required`
  (`mcp_errors.py:56`, `:169`, `:175-185`; the enum value from
  `0030-agent-dry-run.sql:64`), and **nothing is dialled upstream**, so no
  `database`-source row is written.
- **`requires_approval` end to end.** Manifest field
  `schemas/capabilities.schema.json:485-488` (required for a write from v3);
  compiler `capability_compiler.py:93`, `:118` (a profile may ADD approval and
  never remove it), `:600-623` (the tool's value is the OR over its
  capabilities, and each capability entry keeps its own); `apply_profile`
  (`:706-782`) sets **the tool-level field only** (`tool[field] = candidate`,
  `:780`); lock `mcp_lock.py:196-197`, `:668-675`. **The workflow compiler reads
  approval from the CAPABILITY entry** (`workflow_definition.py:227`) and never
  from the tool, so a profile-added approval is invisible to `validate` —
  measured by the explore pass: `project.second.example.yaml:79-80` marks
  `update_task_status` approval-required and the compiler resolved it with
  `requires_approval=False` (§1 D1723).
- **The definition compiler** `src/agentic_postgres/workflow_definition.py`
  (740 lines) and `schemas/workflow.schema.json` (137 lines). Top level
  `schema_version: 1`, `name`, `version`, `description`, `timeout_seconds`
  (1–3600, default 600), `steps` (1–32); step keys `name`, `capability`,
  `arguments`, `retry {max 0-5, backoff_seconds 1-300}`, `timeout_seconds`
  (1–600), `additionalProperties: false` (schema `:57-110`). The approval
  refusal (`:324-329`): *"`{name}@{version}` requires approval, and approval
  steps arrive in Session 33. A worker that ran it would be an approval gate
  nobody passed"*. Reference grammar `:71`. `resolve` `:273-339`, `compile`
  `:554-594`, `_step_timeout` `:511-529`, `_retry` `:537-542`, `load`
  `:428-441`. Example definitions `projects/example/workflows/notes-
  roundtrip.yaml` and `notes-retry.yaml`.
- **The lock's capabilities, measured.** Release (`contracts/snapshots/mcp/
  mcp-capabilities.canonical.json`, from `capabilities.example.yaml`): seven
  capabilities, six tools — `create_note@1.0.0` (write, `p_title`,
  `p_content`, dry-run, no approval), `update_task_status@1.0.0` (write,
  `p_task_id`, `p_expected_status`, `p_new_status`, `idempotent: true`,
  dry-run, no approval), `query_notes@1.0.0`, `query_tasks@1.0.0`,
  `run_report@1.0.0`, and two metadata. Example project
  (`projects/example/capabilities.yaml:46-68`): `query_note_embeddings@1.0.0`
  and **`set_note_embedding@1.0.0` — write, `p_note_id`, `p_embedding`,
  `supports_dry_run: true`, `requires_approval: true`, scope
  `note_embeddings:write`, both arguments redacted**. Its SQL
  (`projects/example/migrations/templates/0001-note-embeddings.sql:75-107`):
  PT401 without an identity, PT404 unless the note is the caller's, then an
  UPSERT over `app.note_embeddings(embedding extensions.vector(768) NOT NULL)`
  — **no dry-run branch and no idempotency branch**, though the capability
  says `supports_dry_run: true` (§1 D1722). **No `delete_note` or
  `delete_task` exists** anywhere (D1547). `api.create_task` exists
  (`0031-create-task.sql:34`) but is not a capability. Task statuses are
  `pending, in_progress, completed, cancelled` (`0007:40`); `update_task_
  status` raises PT409 (`write_conflict`, retryable) when the task is not in
  the expected status, PT404 (`row_not_found`, terminal) for a missing task,
  PT422 (`input_not_permitted`) when the two statuses are equal
  (`0030-agent-dry-run.sql:237-389`).
- **The audit table and its one reader.** `app_private.agent_audit`
  (`0019:73-97`, + `0027:78-84`): `id, source, agent_id (NOT NULL, no FK),
  owner_id, tool, request_id, parameters, outcome, row_count, elapsed_ms,
  started_at, completed_at, capability_version, contract_hash,
  denial_reason`. Outcomes (enum): `started, served, refused, failed,
  committed, replayed, dry_run`; denial reasons: eight + `approval_required`.
  Indexes: `(owner_id, started_at DESC)` and `(agent_id, started_at DESC)`
  only (`0019:109-112`). The reader `app_private.auth_list_agent_audit(p_agent_id
  uuid, p_owner_id uuid, p_limit integer)` (`0032-agent-audit-reader-boundary.
  sql:93-126`, `ORDER BY r.started_at DESC, r.id DESC LIMIT p_limit`, no clamp
  in SQL), granted to `{{auth_service}}` alone (`:146-150`); 0032's own comment
  (`:69-73`) names the filters as *"a fourth, fifth and sixth argument … plus a
  cursor design nobody has priced (D1248)"*, and (`:21-31`) that `CREATE OR
  REPLACE` cannot change a `RETURNS TABLE`. Route `GET /admin/audit`
  (`routes.py:954-1066`): `AUDIT_QUERY_PARAMETERS = ("agent_id", "owner_id",
  "limit")` (`:311`), limit 1..500 default 100 (`:319-321`), scope
  `admin_audit:read` (`:980-981`), `strict_query.parse` (which exports only
  `InvalidQuery, as_bounded_int, as_uuid, parse`, `strict_query.py:54`), the
  response `{"audit": [...], "limit": n}` with no cursor (`:1017-1066`) — and a
  STALE comment at `:1026-1031` saying `request_id` is NULL on every
  `database` row (false since `0022-database-row-request-id.sql`, §1 D1741).
  Repository `repository.py:320-345`. Studio forwards `/admin/audit` with
  `agent_id`/`owner_id` only and REFUSES `outcome`, `since` and the rest with
  400 by D1248's decision (`bin/studio.py:595-634`, `:597`; `studio.py:614-639`,
  `AUDIT_PAGE_LIMIT = 500` `:109`, the header `:778-788`).
- **D1248's original decision** (`docs/plans/session-24-implementation-plan.
  md`, the row after D1247) **argued AGAINST a server outcome filter**: *"No
  summarisation that hides denials … is NOT satisfied by a server filter that
  would let a viewer ask for 'outcome=served' and never see the refusals."*
  This plan builds the filter and must answer that sentence (§1 D1730).
- **Scopes.** Every scope string is enumerated in `schemas/capabilities.
  schema.json` (`$defs/scope` `:234-251`; `$defs/administrative_scope`
  `:271-281`: `admin_users:read`, `admin_users:write`, `admin_agents:read`,
  `admin_agents:write`, `admin_audit:read`); the data class is DERIVED from the
  surface (`src/agentic_postgres/scope_registry.py:55-67`); the partition check
  is `assert_classes_partition_the_vocabulary` (`:122-200`); the lock carries
  `vocabulary: {data, storage, administrative}` (`capability_compiler.py:
  888-889`, schema 4) — **not** inside `tools_sha256` (`:890-895`), so a new
  administrative scope moves no tool digest and no committed snapshot, but does
  move every rendered lock's bytes. Role ceilings are `ROLE_CLASSES` in
  `services/auth-api/app/scopes.py:63-107`: **only `project_admin` carries
  `ADMINISTRATIVE`** (`:106`); `load_vocabulary` reads the lock at startup
  (`:145-190`, called from `main.py:168-172`). Every scope is `resource:verb`
  (`tests/contract/test_scope_registry.py:91`), and `api_surface.
  reserved_resource_names()` takes the part before `:` of every admin scope as
  a relation name no surface may use (`api_surface.py:247-262`). Pinned by
  `test_scope_registry.py:68-87`, `:308-346`, `:381-388`,
  `test_scope_vocabulary.py:321-339`, `test_auth_endpoints.py:59-65`,
  `test_studio_runtime.py:84` (§1 D1717). **A bootstrapped administrator gets
  `sorted(permitted_scopes("project_admin"))`** (`bin/auth-admin.py:321`) —
  existing administrator rows do NOT gain a new scope.
- **A human's agents.** `app_private.agents.owner_id uuid NOT NULL REFERENCES
  app_private.users (id)` (`0011:184`); `POST /admin/agents` sets the owner to
  the creating administrator (`routes.py:858-862`); **D1638**: the token
  ceiling admits admin scopes to `project_admin` alone, and the notes/tasks
  grants go to `authenticated`/`agent_*` alone, so **no single account both
  administers and reads tenant rows**.
- **Live-proof scaffolding** (`tests/deployment/test_session32_workflows.py`,
  1,042 lines): `pytestmark` `:66-76`; `_create_subject` `:144-165` (a human by
  `app_private.auth_create_user` through `psql`, hash from the service's own
  `hashing.Hasher()`); `ProbeAgent` `:168`; `_create_agent` `:204-226`;
  fixtures `beta_owner` `:229-254` (an `authenticated` human nobody can log in
  as), `beta_agents` `:257-286`, **`beta_admin` `:289-322` (a `project_admin`
  created in SQL whose token comes from a real `POST /auth/login` with a random
  password, deleted at teardown)**; helpers `_enqueue` `:330`, `_status`
  `:355`, `_until` `:361`, `_terminal` `:386`, `_audit` `:390`, `_backends`
  `:403`; the recovery proof `tests/recovery/test_session32_workflow_
  restore.py` (141 lines). Conftest fixtures `as_root` `:93`, `project_b`
  `:135`, `api_call` `:898`, `psql` `:960`.
- **The readers.** The doctor's twelve checks are assembled in `diagnose()`
  (`bin/doctor.py:1108-1132`), `probe_workflow` `:801-873` over
  `WORKFLOW_QUERY = "SELECT app_private.workflow_counts()"` (`:752`),
  `diagnosis.workflow_record` (`src/agentic_postgres/diagnosis.py:583-654`,
  no threshold). The restore drill's `workflow_runs` member
  (`bin/restore-test.py:498-509`; `restore_drill.py:686`). `rehearsal.
  SCENARIOS` has ten (`rehearsal.py:81-100`). `doctor usage`'s *"the store
  holds no such series yet"* is `bin/doctor.py:962` (D1712).
- **Carried-in defect sites.** D1707: `bin/migrate.py:137-170` — `run_dbmate`
  calls `container_exec.compose_run(…, text=False)` (`:169`) and returns only
  `result.returncode`, so `status` prints no `[X]` lines. D1705: step 6d is
  `bin/deploy-project.py:864-` (the install helpers) and `:2445-2453` (the
  step). D1712: `bin/doctor.py:962`.
- **The gate and the CLI.** `bin/session-32-check.sh` (1,621 lines): header
  `:2-106`, `readonly SESSION=32` `:115`, `usage()` `:172-454`,
  `parse_arguments()` `:490-684`, `mode_offline()` `:1128-1345` (the `apg dev`
  round trip at `:1255-1261`), `mode_host()` `:1347-1543`, `mode_external()`
  `:1545-1610`; `tests/contract/test_session_thirty_two_gate_modes.py` (916
  lines, the no-gap test at `:244`). `bin/workflow.py` (463 lines): exit codes
  `:33-36`, `HTTP_VERBS` `:39`, `ROUTES` `:46-50`, `TOKEN_VARIABLE =
  "APG_AGENT_TOKEN"` `:56`, `build_parser` `:432`; `bin/workflow.sh` (267
  lines): `usage()` `:38-82`, `verb_usage()` `:84-184`, `main()` `:209-265`.
  `bin/api.py:42` is `TOKEN_VARIABLE = "APG_API_TOKEN"` — the human
  access-token variable.
- **Documentation.** `docs/threat-model.md` table `:19-36`, header `:19`,
  `THR-WORKER` the last row at `:36`. `docs/workflows.md` (201 lines; *What is
  not here yet* `:182-195` names approval, compensation, a provenance reader
  and `wait` as Session 33's at `:186-189`). `docs/operator-guide.md` ends at
  §17 *Workflows, on a deployment* (`:1276-`, subsections `:1286`, `:1321`,
  `:1343`, `:1353`, `:1363`). `docs/README.md:63` indexes workflows.md.
  `docs/upgrade-guide.md` release table `:79-99` (1.10.0 at `:99`; the 1.9.0 and
  1.8.0 rows are out of order at `:97-98` — leave them, not this session's).
  `README.md:7`.

---

## 1. The divergence table

Six columns. Each row is a **measured fact about the tree at `7b0d308`** set
against what the brief (the stage plan's §5 *Session 33*, its §1 rows, §8, §10,
scope-closure §25 and CLAUDE.md §9) says, with the decision this plan takes.
**Next free number after this table is D1742.** Rows the runs add go in the
second table below, in execution order.

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D1714** | Stage plan §5: *"`approval` (the run parks with `approval_required` in the audit; `apg workflow approve\|reject RUN --confirm RUN` by a human …)"*; §25 item 2: *"Session 33 turns the refusal into a parked step resumed by an approval"*. | The refusal is the PLANE's (`mcp_tools.py:591-596`), audited `refused`/`approval_required` before anything is dialled; the loop today classifies it as a terminal refusal and fails the run (`workflow_worker.py:337-339`, `:520-527`). A park with a NULL `resume_after` is never claimed (`0034:577`); a park with a time is claimed when the time passes. There is no record of a pending decision anywhere. | **The worker calls an approval step's tool exactly as it calls any other on its FIRST attempt, and the plane refuses it.** When the refusal token is `approval_required` AND the compiled step declares `approval` (D1723 makes the compiler require it), the worker calls a new `workflow_request_approval(p_step, p_holder, p_request_id, p_expires_after_seconds)`, which inserts a PENDING row in `app_private.workflow_approval` (carrying the plane's request id of the refused call) and parks the step with `resume_after = now() + expires_after_seconds` — **the expiry IS the park's time**. A decision sets `resume_after = now()`, so the next claim takes the step at once. On every later claim the worker reads `workflow_gate_state(p_step, p_holder)`: `approved` → mint with the approval (D1715) and call; `pending` (the claim fired because the expiry passed) → mark the approval `expired` and finish the step `failed`/`approval_expired`; `rejected` never reaches a claim (D1719). If the plane unexpectedly SERVES the first call (the lock no longer requires approval), the step finishes `succeeded`: **the plane is the authority on whether approval is required, never the loop.** | Parking on the plane's own refusal puts `approval_required` in the audit for free (the stage plan's sentence, literally), keeps one authority for *does this need approval* (the lock, enforced by the plane), and reuses 0034's park rather than adding a second waiting mechanism. | **0230** |
| **D1715** | Stage plan §5: the approved run *"resumes"*; §9: *"a workflow … would invoke anything that is not a tool the project's lock compiles"* is a stop. Nothing says HOW the plane learns a call is approved. | The plane refuses `requires_approval` unconditionally (`:591`); it holds no pool and no credential (`main.py:160-163`) and cannot ask the database; it sees the caller's VERIFIED claims through `get_access_token().claims` (`mcp_authorization.py:204-206`, `mcp_runtime.py:319-325`). `verify_claims` checks the twelve required claims and says nothing about extra ones (`claims.py:104-106`); the database's `auth_contract_state` holds the same twelve (`0011:234-237`). Only `auth` signs (ADR 0113); `/auth/agent-token` takes exactly `{agent_id, secret}` (`models.py:264-272`). | **An approved attempt's ONE step token carries an optional claim `apg_approval: {"id": <approval uuid>, "tool": <tool name>, "key": <the step's idempotency key>}`.** `AuthService.step_token(agent_id, *, approval_id=None)` reads the claim's content from the DATABASE through a new `workflow_approval_for_token(p_approval, p_agent)` (approved, not expired, the run's agent equals `p_agent`) — never from the worker's variables — and refuses (`AuthenticationFailed`) otherwise. `issue()` gains a keyword `extra_claims: Mapping[str, Any] \| None = None` that may not name a required claim (refused `InvalidRequest`). `claims.py` gains `APPROVAL_CLAIM = "apg_approval"` and `approval_claim(payload) -> dict \| None` (shape check: three non-empty strings, `id` a uuid; malformed → `ClaimError`). **`invoke_write` gains `approval: Mapping[str, str] \| None`**, read in `register_write` from the verified claims; a `requires_approval` tool proceeds only when `approval["tool"] == tool` and `approval["key"] == idempotency_key`, and **refuses exactly as today otherwise** (same token, same detail, same reason, audited). `/auth/agent-token` and `agent_token` never pass `extra_claims`. **Rig 33a measures that the extra claim passes `verify_claims`, the plane's verifier, PostgREST and the pre-request hook (control: the same token without it; a claim signed by another key is 401).** | The signer is the only party that can mint the claim and the signer mints it only from a decided row; binding the tool and the key means the claim authorises ONE write — a replay of that key is re-read by ADR 0181, not a second write, and any other write inside the token's 930 s life is refused. A flag, a header or an argument would be the agent's to set. | **0231** |
| **D1716** | Stage plan §5: the approval is *"recorded as the second principal's audit row"*. | `app_private.agent_audit.agent_id` is `uuid NOT NULL` and every row is written by the agent plane or a database function AS AN AGENT (ADR 0135; `0019:81`). A human approver is a `users` row, not an agent. Putting a human decision in that table is an audit schema move with a nullable identity — the shape ADR 0135 refused. | **The decision is its own append-only record: `app_private.workflow_approval`** — `id, run_id, step_id UNIQUE, tool, capability, idempotency_key, requested_request_id, requested_at, expires_at, status (pending\|approved\|rejected\|expired), decided_by uuid REFERENCES app_private.users(id), decided_at`. No role holds a table privilege; every write is a definer function; nothing UPDATEs a decided row (the decide function's predicate is `status = 'pending'`, asserted). The provenance reader (D1729) joins it; the audit's `approval_required` row (the refused first call) is joined through `requested_request_id`. The stage plan's *"audit row"* is recorded as met by a record beside the audit, for a reason. | A human's decision has a different accountable identity from an agent's call; one table per principal is how the tree already separates `users` from `agents`. | **0230** |
| **D1717** | Stage plan §5 and §10: *"a new scope `workflow_approve`"*, whose *"place in the derived vocabulary (ADR 0200)"* 33 owns. | Every scope is `resource:verb` (`test_scope_registry.py:91`); the administrative class is an ENUM in `schemas/capabilities.schema.json:271-281`, not derived; only `project_admin` carries it (`scopes.py:106`); `reserved_resource_names()` reserves the part before `:` (`api_surface.py:247-262`). Adding a scope moves every lock's `vocabulary.administrative` (not `tools_sha256`), and four proofs pin the exact sets (`test_scope_registry.py:68-87`, `:308-346`, `:381-388`; `test_scope_vocabulary.py:321-339`) plus two fixture lists (`test_auth_endpoints.py:59-65`, `test_studio_runtime.py:84`). An existing administrator does NOT gain it (`bin/auth-admin.py:321` runs at bootstrap only). | **The scope is `admin_workflows:approve`**, added to `$defs/administrative_scope` and `$defs/scope`, with a named constant `ADMIN_WORKFLOWS_APPROVE` in `scopes.py` beside `ADMIN_AUDIT_READ` (`:128`). It reserves the relation name `admin_workflows`. The four pinning proofs are updated to the new exact sets **in the same commit, under ADR 0232** — a set equality with one more member is a stricter proof, not a weaker one — and the two fixture lists gain it. **The operator grants it** with `PATCH /admin/users/{id}` (role and scopes together, `routes.py:737-741`); the operator guide says so; the trip's approver is created with it. | `workflow_approve` has no colon: it would break the grammar every scope follows and reserve a nonsense relation name. The administrative class is exactly the class a human-only authority belongs to, and its ceiling is already *project_admin alone*. | **0232** |
| **D1718** | Stage plan §5 Must not: *"Let approval be granted by the agent that requested it"*; §10: *"the proof that the requester cannot hold it for its own run"*. | An agent token is refused by `authenticate` (`service.py:354-357`) and `require_scope` is typed to `Principal` (`:385-394`), so an agent structurally cannot reach an `/admin/*` route. The agent's OWNER is a human (`0011:184`), and `POST /admin/agents` makes the creating administrator the owner (`routes.py:858-862`) — so an administrator who created an agent holds a human token that could approve that agent's run. | **Three controls, each proved:** (1) the four new routes call `authenticate` + `require_scope`, so an agent token is 401 (the requester cannot hold the scope for its own run *because it cannot hold a human token at all*); (2) `workflow_decide_approval` refuses `p_user = run.owner_id` with `PT403` message `approver_is_owner`, mapped to 403 `{"error": "approver_is_owner"}`; (3) the scope is `project_admin`-only by ceiling (D1717). The live proof drives all three and the positive: a second `project_admin` holding the scope approves. | The stage plan named the agent; the owner is the same person's authority one step removed, and D1638 already makes owner ≠ administrator on a tenant agent — the rule makes it true for an administrator's own agents too. | **0232** |
| **D1719** | Stage plan §5: *"a rejection is a cancel"*; `wait` *"parked until an event … or `timeout_seconds` elapses"*. Nothing bounds how long an approval may wait. | `workflow_run.timeout_seconds` is `CHECK BETWEEN 1 AND 3600` (`0034:205`) and the claim fails a RUNNING run past it at every claim (`:561-568`) — a run parked on an approval is `running`, so it is failed `timed_out` at the first claim after its hour, by existing code. A requested cancel is applied by the claim when nothing is in flight (`:551-559`). | **An approval's expiry is `approval.expires_after_seconds` (60..3600), which the compiler requires to be strictly less than the run's `timeout_seconds`.** No CHECK is widened: an approval that must wait longer than an hour is a later decision priced then (§10). **A rejection is `workflow_decide_approval(…, 'reject')` setting the approval `rejected` AND the run's `cancel_requested_at`** — the next claim applies the cancel exactly as it applies any other, and compensation follows (D1725). The rejected step stays `parked` and is never claimed again (its run is no longer `queued`/`running`). | Literally a cancel, through the one path cancels already take; and the expiry reuses the park's own time, so no timer is added. | **0230** |
| **D1720** | Stage plan §5: *"`apg workflow approve\|reject`"*; Must not: *"Add a notification plane beyond the parked state"*. Nothing says what an approver SEES. | `set_note_embedding` redacts both its arguments (`capabilities.yaml:68`); the run's `input` is the agent's data, and D1638 means an administrator does not read tenant rows. The audit never stores a redacted value (`audit.redact`). | **`GET /admin/workflows/approvals` lists pending approvals with no argument VALUES**: `run_id, definition, definition_version, step, position, capability, tool, agent_id, owner_id, requested_at, expires_at` — ordered oldest first, `limit` 1..100. The approver reads the REVIEWED definition in the checkout for what the step does; the product shows who, what capability, which run and until when. | Showing values would make the approval listing a tenant-data reader for an identity that D1638 keeps out of tenant rows, and would bypass every capability's `audit.redact`. | **0230** |
| **D1721** | Stage plan §8: *"PostgreSQL is the final authorization authority"*; `THR-APPROVAL`: *"an approval forged or replayed"*. | **Approval is enforced in the plane only.** `api.set_note_embedding` checks no approval and is `GRANT EXECUTE … TO {{agent_writer}}` (`projects/example/migrations/templates/0002-agent-grants.sql:27-28`) and `{{authenticated}}` (`0001:116`); an agent token is FOR PostgREST (`service.py:40-43`), and `routes.rest` is published on `edge`. So an agent holding `note_embeddings:write` and its own token can POST `/rpc/set_note_embedding` directly and never meet the approval. This predates Session 33 (ADR 0179, D870) and is not what workflows change. | **Measured in Run 1 (rig 33b) and recorded, not repaired.** `THR-APPROVAL`'s *Residual risk* cell states it in one sentence; `docs/workflows.md` and the operator guide say *approval governs the agent plane and workflows; the database authority is the SQL grant*; §10 prices the database half (a release-owned `api.require_approval(p_tool)` a project's RPC calls first, reading the `apg_approval` claim from `request.jwt.claims` against `workflow_approval` — a project migration plus a release function). **If rig 33b shows the direct call REFUSED, the row is rewritten to say what refused it.** | A security property claimed beyond what enforces it is the defect class §7 of CLAUDE.md names. Building the database half here would move the example project's SQL, the lint's allowlist and a release function in a session whose subject is the governed path; it is priced so a later session or the operator can take it. | **0231** |
| **D1722** | Stage plan §5: `dry-run` runs every step under ADR 0182 (32's); nothing says what a dry run does at an approval. | `set_note_embedding` declares `supports_dry_run: true` and its SQL has **no dry-run branch** (`0001:75-107`) — a `Dry-Run` header reaching it would WRITE. Today that is unreachable because the approval refusal comes BEFORE the dry-run check (`mcp_tools.py:591` then `:603`). Once an approved claim lets the call through, an approved call with `dry_run: true` would reach the upsert. | **Two belts.** (1) **A dry-run run never requests approval**: the worker finishes an approval step in a `dry_run` run as outcome `dry_run`, reason `approval steps are not rehearsed`, WITHOUT calling the plane. (2) **The plane refuses an approval claim together with `dry_run: true`** (`input_not_permitted`, *"an approved call is not rehearsed"*, `NOT_IN_ALLOWLIST`), before anything is dialled. Rig 33b measures the missing branch (the header set, the row written) so the row's premise is measured, and §10 records the example project's defect for whoever next moves that project's SQL. | The capability's `supports_dry_run: true` is a claim its SQL does not keep; the plan does not make a write reachable through that gap, and it says the gap exists. | **0231** |
| **D1723** | Stage plan §5: *"the definition's `validate` refuses a compensation the lock does not compile"*; 32's compiler refuses an approval-requiring capability (`workflow_definition.py:324-329`). | **A profile-added approval is invisible to the compiler.** `apply_profile` sets the TOOL's `requires_approval` only (`capability_compiler.py:780`) and the workflow compiler reads the CAPABILITY entry's (`workflow_definition.py:227`). Measured by the explore pass over `project.second.example.yaml:79-80`: `update_task_status` is approval-required by profile and resolved with `requires_approval=False`, so a definition using it validates and then fails `refused` at run time. | **The compiler reads the effective approval as `tool.requires_approval OR capability.requires_approval`** — the tool-level field is what the plane enforces (`mcp_tools.py:591` reads `entry.requires_approval`, the tool). A step whose capability is approval-required by EITHER source must declare `approval:`; a step declaring `approval:` whose tool does not require one is refused (*a gate the plane would not enforce is a gate nobody passes*). Proved against `project.second.example.yaml` (the case that was wrong) with `project.example.yaml` as the control. | The compiler must agree with the enforcer; reading the tool is reading what the plane reads. | **0228** (amended) |
| **D1724** | 32's ADR 0228: a step may reference `{{steps.<name>.<field>}}` of an earlier step's result. | **The loop stores the JSON-RPC `result` envelope** (`workflow_worker.py:333-340`, `:488`) — `{content: [...], isError, …}` — not the tool's `{tool, row_count, row, dry_run}` dict. The fakes in `test_workflow_worker.py:135-142` and `:701` store `{"row": …}` directly, so the offline suite believes the documented shape (question 6). On a real plane only `{{steps.x.content}}` could resolve. Inferred from the code; **not yet measured** against the real plane. | **Rig 33c measures what the real plane returns for `create_note` (`result.structuredContent`? `result.content[0].text` as JSON?).** Run 5 then stores **the tool's own return dictionary** as the step result — `structuredContent` when it is an object, else `content[0].text` parsed as a JSON object, else `null` with the step's `reason` saying *the plane's result carried no structured value* (ADR 0195: reported, not guessed) — and replaces the fake's canned result with rig 33c's bytes. The reference grammar is NOT deepened (`test_workflow_worker.py:846-855` still refuses a second level). Rows already stored on production are records and are not rewritten. | A documented feature that cannot work on the real plane, invisible because the fake agreed with the code — Session 32's D1696 shape, found by reading this time rather than on a host. Compensation arguments may reference an earlier step's result, so the reference has to work. | **0228** (amended) |
| **D1725** | Stage plan §5: *"a step may declare `compensation: tool@version`, run by the worker in reverse order for every succeeded step when a later step fails terminally or the run is cancelled, as the same agent, audited as `compensation` — never a rollback"*; Must not: *"Promise rollback. Widen a profile to run a compensation."* | No compensation exists (0 hits for `compensat` in the product). The claim takes a step only when every EARLIER position has `succeeded` (`0034:580-584`) — so a compensation row placed after a failed step could never be claimed by the current predicate. `finish_step`'s failure branch sets the run `failed` and ends it (`:741-747`). The audit has no phase column and the plane cannot know a call is a compensation. Precedent for adding an enum value inside a dbmate migration and using it in functions replaced by the same migration: `0029:69` and `0030:63-64`, both applied on production. | **Compensation is declared per step — `compensation: {capability: name@version, arguments: {…}, retry: {…}}` — must be a WRITE, may not require approval, and its scopes join the definition's `required_scopes`** (so `enqueue` refuses an agent that could not run it, and nothing is ever widened to run it). **Migration 0035**: `ALTER TYPE app_private.workflow_run_status ADD VALUE 'compensating'`; `workflow_step` gains `phase text NOT NULL DEFAULT 'forward' CHECK (phase IN ('forward','compensation'))` and `compensates integer` (the forward position); `workflow_run` gains `compensation_cause app_private.workflow_run_status` and `compensation_outcome text CHECK (compensation_outcome IN ('complete','incomplete'))`. An internal definer function `workflow_begin_compensation(p_run, p_cause)` (granted to NOBODY; called by `finish_step`, `claim_step`'s cancel branch) appends ONE compensation row per SUCCEEDED forward step that declares one, in REVERSE position order, at positions `1000 + n`, named `undo-<forward position>`, keyed `wf-<run>-undo-<forward position>`, and sets the run `compensating` with the cause; if there is nothing to compensate the run takes the cause directly. The replaced claim takes a compensation row when every compensation row BEFORE it is FINISHED (succeeded or failed — each undo is independent and a failed one does not stop the rest) and returns the forward step's `compensation` block as `step`. When the last compensation row finishes the run takes its cause status with `compensation_outcome` `complete` (all succeeded) or `incomplete`. A `token_refused` during compensation stops the run (`stopped`, `agent_not_active`, outcome `incomplete`). **A compensating run is not timed out** (the timeout predicate reads `running` only); each compensation row is bounded by its own retry and step timeout. | Appending rows at failure time keeps enqueue unchanged and makes the compensation plan a record of what was actually compensated, not of what might have been. A distinct run status tells a poller the run is not over; `complete`/`incomplete` tells the reader what happened without the word *rolled back*. | **0233** |
| **D1726** | Stage plan §5: compensation *"never a rollback of the outside world"*. | In beta's lock: `update_task_status` is its own inverse (swap the two statuses; `idempotent: true`); **`create_note` has no inverse** — `delete_note` does not exist (D1547, `scope-closure.md:1031`); `set_note_embedding` upserts and returns no prior value, so its inverse would need a read first and is approval-gated anyway. | **The example definitions compensate `update_task_status` with `update_task_status`, and nothing else.** The compiler does not know what an inverse is and does not try: it checks that a compensation is a write the lock compiles, that its arguments are declared, and that its references point at the run's input or at steps at or before the one it compensates. `docs/workflows.md` says in one sentence that a note cannot be un-created in this release, and why. D1547 is **not** closed and is named in §10. | A compensation is a reviewed forward action the author chose, which is exactly why the word *rollback* is refused. | **0233** |
| **D1727** | Stage plan §5: *"`wait` (parked until an event named by 34 arrives or `timeout_seconds` elapses)"*; §25 item 3: *"Session 33 adds the step kind; Session 34 adds the event."* | The park exists (`0034:773-801`); no event exists. `timeout_seconds` on a step is the HTTP call bound (1..600, `0034:259`). | **`wait: {seconds: N}` — a step with no capability, 1 ≤ N < the run's `timeout_seconds`.** First claim: the worker parks it with `resume_after = now() + N`, reason `waiting`. Next claim: `workflow_gate_state` reports `waited: true` (an attempt row with event `parked`/reason `waiting` exists, D1728) and the worker finishes it `succeeded`, reason `waited` — never a second park, so a reclaim after a crash does not restart the wait. **`wait: {event: …}` is refused by the compiler naming Session 34.** A wait step makes no call and mints no token. | A timer is the half of `wait` that needs no event plane; building the kind now means 34 adds a resume source and not a step kind. Not minting a token for a step that calls nothing is the per-step discipline applied honestly. | **0233** |
| **D1728** | Stage plan §5: `inspect` shows *"each idempotency key, each denial's boundary, budgets consumed"*. | `workflow_step.request_id` holds the LAST attempt's id and a claim clears it (`0034:248-249`, `:603`); an earlier attempt's audit row is reachable only by agent and time. `agent_audit` has no key column; the key lives in `agent_idempotency` (`0029:103-112`). | **Migration 0035 adds `app_private.workflow_attempt(step_id, attempt, event, outcome, request_id, reason, recorded_at, PRIMARY KEY (step_id, attempt, event))`**, `event IN ('finished','parked','approval_requested')`, appended by the replaced `workflow_finish_step` and `workflow_park` and by `workflow_request_approval` — same signatures, `CREATE OR REPLACE`. No role holds a privilege on it. | Provenance that can only see the last attempt would summarise the others away — the one thing the stage plan's Must-not forbids for `inspect`. | **0234** |
| **D1729** | Stage plan §5: *"`apg workflow inspect RUN`: who started it, the agent, the definition digest, each step's tool and capability version, the lock digest the worker loaded, the profile, each approval's principal, each idempotency key, each denial's boundary, budgets consumed, whether compensation ran — read from `agent_audit` correlated by run id"*; §25 D1704: whose read a revoked agent's stopped run is. | `workflow_run_status` answers only the run's own agent (`0034:908`), and `authenticate_agent` refuses a revoked agent (D1704), so no product reader shows a stopped run. The audit carries, per plane call, `capability_version` and `contract_hash` (`0027:78-84`) — the plane's view at call time — plus `outcome`, `denial_reason`, `row_count`, `elapsed_ms`. Nothing records a profile name per call; the lock digest the AUTH process loaded is not the one the plane enforced. | **One definer function `app_private.workflow_provenance(p_run uuid) RETURNS jsonb`, granted to `{{auth_service}}`, read by `GET /admin/workflows/runs/{run_id}` under `admin_audit:read`** — the auditor's scope, so a human auditor reads ANY run, a revoked agent's included (D1704 answered: *an auditor's read*). The document: the run (agent, owner, definition name/version/`source_sha256`/`lock_tools_sha256`, input, status, stopped reason, compensation cause/outcome); every step (phase, name, capability and version and tool from the compiled body, idempotency key) with EVERY attempt from `workflow_attempt`, each joined to its `agent_audit` rows by `request_id` (source, outcome, denial reason, row count, elapsed, capability version, contract hash); every approval (status, requested/decided times, the decider's user id and username, the refused call's request id). **Two things the brief asked for are reported ABSENT with a reason, never filled**: `profile` (*no per-call record names a profile*) and a per-call lock digest other than the audit's `contract_hash`. `apg workflow inspect --run ID` prints the document whole — no summary line, no count that could stand in for a row. | The request id is the correlation proved on production (D1696); the auditor's scope is the one `/admin/audit` already requires, so provenance grants no new read; reporting the two absent fields as absent is ADR 0195. | **0234** |
| **D1730** | Stage plan §5 and §2.3: D1248's filters — *"a time window, an outcome/boundary filter, a cursor: one migration over 0032's reader and one change to `GET /admin/audit`, exposed through Studio's existing `audit` forwarder as well"*; Measures: *"a cursor over 1,000 audit rows returning every row exactly once (control: the unfiltered read's count)"*. | D1248's own row refused a server outcome filter because *"a viewer [could] ask for 'outcome=served' and never see the refusals"*. The reader is `(uuid, uuid, integer)` and `CREATE OR REPLACE` cannot change its `RETURNS TABLE` (`0032:21-31`); the arity guard (ADR 0175, `test_database_function_signatures.py:587`) models a `DROP FUNCTION` + `CREATE` (`:197-220`). No index leads with `started_at`. `strict_query` has no timestamp or enum parser. Studio refuses `outcome`/`since` with 400 (`bin/studio.py:597`), pinned by `test_studio_server.py:605-615` and `test_studio_runtime.py:1184-1196` (STU-AUDIT-001); `test_auth_endpoints.py:1681` uses `cursor` as its example of an UNKNOWN parameter. | **0035 DROPs and re-CREATEs `app_private.auth_list_agent_audit(p_agent_id uuid, p_owner_id uuid, p_since timestamptz, p_until timestamptz, p_outcome text, p_denial_reason text, p_before_started_at timestamptz, p_before_id uuid, p_limit integer)`** (keyset: `(started_at, id) < (p_before_started_at, p_before_id)`, `ORDER BY started_at DESC, id DESC`; an unknown outcome or reason is `PT422`, never an empty page), re-issuing `REVOKE`/`GRANT`, **and adds `app_private.auth_count_agent_audit(p_agent_id, p_owner_id, p_since, p_until) RETURNS jsonb`** — counts by outcome and by denial reason over the WINDOW, ignoring the outcome/reason filters and the cursor — plus an index `agent_audit_started_id_idx ON app_private.agent_audit (started_at DESC, id DESC)`. `GET /admin/audit` accepts `since`, `until`, `outcome`, `denial_reason`, `cursor` (opaque: `<started_at ISO-8601>~<id>`, base64url) and **always** returns `window_counts` beside the page and `next_cursor` (null when the page is short). **D1248's objection is answered, not overruled: a filtered page cannot hide that refusals exist, because the window's refusal count is on the same response.** `strict_query` gains `as_timestamp` and `as_member`. Studio forwards the five and renders `window_counts` in its header. The three refusal proofs are replaced by stricter ones under ADR 0234 (the unknown-parameter proof keeps its property with another name, `?page=abc`). | The window count is the smallest addition that keeps *no summarisation that hides denials* true while letting a reader narrow; the cursor with an id tie-break is the only paging that returns every row once when many rows share a `started_at` (rig 33d plants exactly that). | **0234** |
| **D1731** | Stage plan §2.3: D1248 is Session 33's *"because the provenance reader needs a window, an outcome filter and a cursor over the audit"*. | Provenance for ONE run is an exact join by request id inside one function (D1729); it needs no window, filter or cursor. | **Recorded honestly: provenance does not depend on the filters.** Both are built because the brief closes D1248 in this session and its measurement is listed; they share migration 0035 and a run, and nothing in either depends on the other. | A dependency claimed where none exists would make one deliverable's failure look like the other's. | **0234** |
| **D1732** | Stage plan §5: *"Harness cases for workflows (a step whose scope the agent no longer holds; a replayed approval; a compensation named for a tool that is not a write)"*. | The evaluation harness derives one adversarial case per frozen FIELD of a CAPABILITY contract (`evaluation_harness.py:3-11`, `derive_cases` `:589-615`); `coverage` and `render_report` are keyed per capability (`:714-762`). A workflow is not a capability contract. | **The three cases are proofs where their subject lives, not harness cases:** *a scope the agent no longer holds* — `enqueue` refuses (`WF-STATE-001`, existing) and a step whose scope was narrowed after enqueue is refused `scope_not_held` by the plane and finishes the run `failed` naming it (a new worker proof and a new live assertion); *a replayed approval* — a second decision on a decided approval is `PT409` `approval_already_decided`, and a reused `apg_approval` claim with another key is refused by the plane (substrate + plane proofs); *a compensation that is not a write* — a compiler refusal. `evaluation_harness.py`, `docs/evaluation-report.md` and every project's report are untouched. | Forcing definition-level cases into a per-capability derivation would change what the harness's coverage rule means for every capability; the property is proved either way, at its enforcer. | 0184 |
| **D1733** | Stage plan §5: *"Ends on a host: an approval round trip by a second user on alpha, and the provenance read back complete."* | **Alpha installs no definitions** — it declares no project set (Session 32 Sheet B2: step 6d prints *no workflow definitions (the project declares no migration set)*). The only approval-requiring capability on the deployment is beta's `set_note_embedding@1.0.0`. Live proofs create humans in SQL and log in over HTTP (`beta_admin`, `test_session32_workflows.py:289-322`); no administrator password is recorded for beta. | **The round trip runs on BETA.** Two definitions are added to `projects/example/workflows/`: **`tasks-approval.yaml`** (`start_the_task` update_task_status pending→in_progress with a compensation back; `set_the_embedding` set_note_embedding with `approval: {expires_after_seconds: 900}`; `finish_the_task` in_progress→completed) and **`tasks-compensate.yaml`** (`start_the_task` with its compensation; `pause` `wait: {seconds: 5}`; `touch_a_missing_task` update_task_status over `{{input.missing_task_id}}`, a uuid that names nothing → `row_not_found`, terminal). The proofs create: an `authenticated` owner; an `agent_writer` agent with `meta:read, notes:read, notes:write, tasks:read, tasks:write, note_embeddings:read, note_embeddings:write` owned by it; an APPROVER (`project_admin`, scopes `admin_workflows:approve, admin_audit:read`) and a SCOPELESS administrator (`project_admin`, `admin_agents:read`) — both logged in over HTTP; and, for the owner rule, an agent OWNED BY the approver. Alpha is the control the other way (`/admin/workflows/approvals` answers an empty list). | The stage plan's *alpha* was written before 32 found where definitions live; *a second user* is kept exactly. | — |
| **D1734** | 32's §10: *"Whether a moved lock should refuse a RUN is Session 33's, beside compensation."* | `lock_tools_sha256` is a record (`0034:154-157`); the plane enforces its OWN loaded lock on every call; the audit records each call's `contract_hash`. | **A moved lock does not refuse a run.** Provenance shows the definition's `lock_tools_sha256` beside every call's `contract_hash`, so a reader sees that the lock moved and what each call ran under. | Refusing in the loop would be a second authority over the lock the plane already enforces. | 0228 |
| **D1735** | Stage plan D1525: each building session owes its scenario — *"31 admission-refused; 32 worker-restart; 34 delivery-retry-storm"*. | 33 is not in that list; `rehearsal.SCENARIOS` has ten. A worker restart during an approval park is trivially survived (a parked step holds no lease). | **No rehearsal scenario is added.** The substrate proof `test_an_approval_park_holds_no_lease` records why none is owed. | D1075's shape: a scenario that proves nothing new is not built. | 0190 |
| **D1736** | Stage plan §5 Must not: *"Add a notification plane beyond the parked state (a human polls `status`)"*. | — | **`apg workflow approvals` is the poll**: a human with the scope lists what waits. No email, webhook, push or long poll. | The stage plan's rule, kept. | 0230 |
| **D1737** | Stage plan §2.2: one minor per session unless `upgrade plan` prices major. | `upgrade plan` derives only `image_digest`, `implementation`, `secret_required_added`, `capability_added` from two documents; `migration_added` and the API classes are DECLARED (`bin/upgrade.py:116-138`, D1703). A vocabulary change moves the lock's bytes and recreates `auth` and `mcp` (ADR 0200 §2) but is not a change class and moves no operator manifest. | **No deployed-document field, container, role, secret, host field or operator-manifest change: outputs stays v18, `evidence.ISOLATED_FIELDS` unchanged.** Run 8 reads `upgrade plan` with `--also migration_added --also api_operation_added` → expect `bump minor`, `requires minor`; without them `requires patch` (stated, D1703). The release paragraph lists every leaf. | The third release whose price the command cannot fully see; declaring is the mechanism built for it. | 0162, 0200 |
| **D1738** | Scope-closure §25: D1707 *"owed: the output printed and a proof that the `[X]` lines appear"*; D1705 *"owed by the next run in `bin/deploy-project.py`"*; D1712 *"the reason should name that"*. | D1707: `bin/migrate.py:169` captures and discards dbmate's output. D1705: step 6d's *nothing to install* and *exit 5* arms have no offline proof. D1712: `bin/doctor.py:962` says *"no such series yet"*. | **Run 2 repairs all three before any Session 33 code**: `run_dbmate` prints the captured stdout and stderr (the `status` verb's `[X]` lines reach the operator) with a proof over a fake `compose_run`; two AST/behaviour proofs over step 6d's helpers; the reason becomes *"the store holds no such series in the current `mcp` process (each process mints its own series, D1609)"*. | The trip will read a new ledger (35) and the product's own status verb should be what reads it. | — |
| **D1739** | Scope-closure §25: D1711 (no memory figure under a run), D1700 (probe agents accumulate). | Every sweep recreates services early; `op` can read `memory.current` via `/proc/<pid>/cgroup` + `mountinfo`. Session 32's sweep left 4 revoked agents + 1 subject per sweep on beta. | **D1711**: Run 9's agent (as `op`) samples beta's `auth` `memory.current` every 10 s for the WHOLE sweep, resolving the container by the method in CLAUDE.md §2, and Run 10 records max and median as the under-load figure in `capacity.ENVELOPE` — clearing `capacity.UNMEASURED`'s row only if a sample lands inside a run proof's window (the sweep's JUnit timestamps say which). **D1700**: this session's proofs add agents (revoked, not deletable while their runs reference them) and delete their human approvers; the count per sweep is written in Run 9's Done. The retention story stays owed. | A figure labelled *under a run* must have been taken during one (D1711's own rule). | — |
| **D1740** | `docs/workflows.md:78-79`: *"there is no partial interpolation, and a value is either a literal or one whole reference"*. | The worker interpolates an embedded reference (`workflow_worker.py:211-215`) and a proof asserts it (`test_workflow_worker.py:708-710`). | **The page is corrected to what the code does** (Run 2), with the typed-whole-reference rule stated. | Documentation that contradicts a passing proof is the class D1595 keeps finding. | — |
| **D1741** | The tree's own prose. | `routes.py:1026-1031` says `request_id` is NULL on every `database` row (false since `0022`); `:313` names *"Migration 0020's reader"* (0032's since); AGT-AUDIT-002's description says *"The arity stays `(uuid, uuid, integer)`"* (`tests/acceptance-registry.yaml:3825-3826`); AGT-APPROVE-001 says *"no pending state, no second principal, no notification plane"* (`docs/product-contract.md:230`, `docs/acceptance-matrix.md:269`). | **Each sentence is corrected in the run that makes it false** (Run 3 for the arity, Run 6 for the route comments, Run 8 for the two descriptions), and the Done quotes the before and after. | D1595's class. | — |

**Rows the runs added, in execution order.**

| # | Run | Plan says | Tree does / measured | Decision |
|---|---|---|---|---|
| **D1742** | 1 | §5 Run 1: append `THR-APPROVAL` before any code, its *Acceptance requirement IDs* `AGT-APPROVE-002`, `WF-GATE-001`, `WF-APPROVE-001` and two proposed node ids. | `test_acceptance_registry.py::test_threat_model_requirement_ids_exist_in_the_registry` and `::test_threat_model_node_ids_are_collectible` read EVERY threat row: a requirement id must exist in the registry and a node id must collect. None of the five exists until Run 8 lands the registry (D690), so the row as written would turn two passing proofs red in a documentation run. | **The row lands in Run 1 with the prevention, detection and residual cells whole, and cites what holds TODAY**: `AGT-APPROVE-001` and `test_mcp_tools.py::test_a_capability_requiring_approval_is_refused_before_any_dial` (the refusal without a claim, which ADR 0231 keeps byte-identical). Its residual cell says so. **Run 8 rewrites the two cells** to add the three new requirements and their collected node ids. D1527's *before code* is kept; neither proof is weakened. |
| **D1743** | 2 | §5 Run 2 item 2: `bin/doctor.py:962`'s reason becomes *"the store holds no such series in the current mcp process …"*; *"the proof that reads the reason is made stricter"*. | `probe_store` answers BOTH store figures — `requests_total` (`sum(traefik_service_requests_total)`) and `tool_calls_total` — through one sentence, so the plan's wording would have told an operator that Traefik's request counter lives in an mcp process. **And no proof read the reason at all** (grep: `no such series` appears in `bin/doctor.py:962` and, as a quoted historical output, in `capacity.py:553`, nowhere under `tests/`). | **The empty-series reason is per figure**: `STORE_EMPTY_REASONS` beside `STORE_QUERIES`, `probe_store(…, empty=…)`, the caller passing the figure's own; `requests_total` keeps *"… yet"* (a counter no request has touched yet), `tool_calls_total` gets the mcp-process sentence. A NEW proof (`test_an_empty_tool_call_answer_names_the_current_mcp_process`) reads both. `capacity.py:553` is a record of what Session 32's reading printed and is not rewritten. |
| **D1744** | 3 | §5 Run 3 item 5: the claim's timeout phase calls `workflow_begin_compensation(r.id, 'failed')` *"after setting `stopped_reason = 'timed_out'`"*, under 0034's predicate. | 0034 fails a timed-out RUNNING run **even while one of its steps is claimed under a live lease** — the call is upstream. With compensation that would append the undo rows while a forward write was still in flight, and that write, landing after, would be undone by nothing. And 0034's `finish_step` updated the run with no status guard, so a late forward success could mark a `failed` run `succeeded`. | **The timeout phase skips a run with a call in flight** — the cancel phase's own rule (0034:555-559), extended; the in-flight call's lease bounds the wait. **A forward step finishing on a run no longer queued or running records the step and leaves the run where it is.** Proved: `test_a_timed_out_run_with_a_call_in_flight_waits_for_the_call` (and battery arm m7); 0034's own `test_a_run_past_its_timeout_is_failed_at_the_next_claim` still passes (its step is parked). |
| **D1745** | 3 | §1 D1715 and §5 Run 3: `workflow_approval_for_token` answers *"only when `status 'approved'`, `expires_at > now()` and the run's `agent_id = p_agent`"*. | The expiry bounds how long a HUMAN may take to decide. An approved step that meets a retryable `write_conflict` parks and is claimed again, possibly after the window; re-checking the expiry there would make `step_token` refuse, which the loop classifies `token_refused` and reports as *the agent stopped being able to act* — a false stop. | **Once approved, the decision window is not re-checked; the run must still be RUNNING and the agent the run's own.** What bounds an approved call is the step's own retry and the run's timeout, and the claim binds ONE write through its key. Proved by `test_the_token_lookup_answers_only_an_approved_approval_of_that_agents_running_run` (an approved row past its window still answers; a cancelled run does not). ADR 0231's text is unaffected (it names *approved, and this agent's run*). |
| **D1746** | 3 | §1 D1729: provenance returns the run's `input`; §2 WF-PROV-001: *"no field carries a redacted argument value"*. | A run's input is the agent's data and is what a step's arguments are resolved from — `tasks-approval`'s `embedding` is `set_note_embedding`'s `p_embedding`, which the example capability REDACTS (`capabilities.yaml:68`). Returning the input to an auditor would put back exactly what `audit.redact` kept out of the audit record. | **Provenance carries the input's KEYS (`input_keys`), never its values**, beside no `parameters` and no step `result`. Proved with three canaries (`test_provenance_carries_no_parameters_result_or_input_value`, battery arm m8). The agent's OWN read (`workflow_run_status`) still returns its input, as under 0034. |
| **D1747** | 3 | §5 Run 3: the decide function's refusals are *owner, decided, expired, no such run*; the listing is *"pending, unexpired approvals"*; `workflow_counts` gains *"`approvals_pending` (count)"*. | A run can end while its approval is still `pending` — a timeout, the agent's own cancel — and nothing then waits on the decision. The plan's predicates would list it, count it and let a human approve a run nobody will resume. | **A decidable approval is pending, unexpired, on a RUNNING run.** The listing and `approvals_pending` count only those; a decision on an approval whose run has ended is refused with the same `no such run` a missing run gets (checked AFTER the owner, decided and expired refusals, so those words stay exact). No new refusal word. |
| **D1748** | 3 | §5 Run 3: undo rows are named `undo-<forward position>` and keyed `wf-<run>-undo-<forward position>`; nothing says why that cannot collide with a forward step. | 0034's column CHECK admits `undo-1` (`^[a-z][a-z0-9_-]{0,62}$`), and a forward step so named would share the undo row's name and key, failing `UNIQUE (run_id, name)` inside a finish. **But `schemas/workflow.schema.json:67` admits no hyphen in a STEP name** (`^[a-z][a-z0-9_]{0,62}$`), so no compiled definition can carry one: the collision is impossible by construction. Found by checking the premise before writing the compiler refusal the first draft of this row asked for. | **The hyphen IS the separation, and Run 4 pins it**: a proof that the schema's step-name pattern refuses `undo-1` (so a later widening of that pattern has to look at this). No compiler refusal is added for a name the schema already refuses. |
| **D1749** | 4 | §5 Run 4 item 4: *"`bin/workflow.sh validate --project project.second.example.yaml` (beta's shape) compiles four definitions; the release project (`project.example.yaml`) with no profile is the D1723 control"*. | **The two manifests are the other way round.** `project.example.yaml` (`fixture-alpha`) names `migrations.set: projects/example` -- beta's shape, where the definitions live -- and its profile does not touch `update_task_status`; `project.second.example.yaml` (`fixture-alpine`) names NO set (so `validate --project` on it says there is nothing to validate, exit 0) and is the one whose profile carries `update_task_status: {requires_approval: true}` (`:79-80`). Measured by compiling both locks: the second's `update_task_status` tool entry reads `requires_approval: true` and its capability entry `false`. §1's own D1723 row already had it the right way round. | **The four definitions compile under `project.example.yaml`** (`validate` exit 0, four lines) and **D1723's case is the second lock**: `test_a_profile_added_approval_is_seen` compiles against it, and `validate --project project.second.example.yaml --file projects/example/workflows/tasks-{approval,compensate}.yaml` exits 5 on `start_the_task` with the new sentence -- the defect's repair seen through the product's own command. `test_the_example_project_without_the_profile_is_the_control` is the example manifest. |
| **D1750** | 4 | §2: *"Run 8 lands the YAML"*; its *Existing entries that move* list does not name WF-DEF-001. §5 Run 4 replaces `test_a_capability_that_requires_approval_is_refused` and (by the battery's control name) renames `test_the_example_projects_definitions_compile`. | `test_acceptance_registry.py::test_every_registered_node_id_is_collectible` failed on exactly those two WF-DEF-001 node ids the moment they were renamed. An EXISTING entry's node ids are not `CURRENT_SESSION`'s all-or-nothing move (D690): no new requirement, claim or target session is added. | **WF-DEF-001 moves in Run 4**: its two node ids become `test_an_approval_requiring_step_must_declare_approval` and `test_the_example_projects_four_definitions_compile` (both stricter than what they replace), and its two sentences that became false are corrected (*approval arrives in Session 33*; *two definitions compile*); `docs/acceptance-matrix.md` and `docs/product-contract.md` regenerated. WF-DEF-002 is still Run 8's. |
| **D1751** | 4 | §5 Run 4 item 2: the compiled step carries *"`compensation: {kind: \"write\", tool, capability, version, arguments, retry, timeout_seconds}`"*. | 0035's claim hands the worker an undo row's `step` as the forward element's `compensation` block with the row's `name` merged in, and the worker reads a forward step's `tool`, `capability`, `capability_version`, `resource`, `kind`, `arguments`, `retry`, `timeout_seconds`. A block spelling `version` would make an undo row a step the worker's own reader does not recognise. | **The compensation block uses the forward step's key names exactly -- `capability_version`, and `resource: null` --** so Run 5 reads an undo row with the reader it already has. Three further compiler decisions the plan did not take: `approval` and `compensation` are emitted ONLY when declared (a Session 32 definition compiles to byte-identical JSON); a reference to a WAIT step is refused (*a wait records no result*), since it could never resolve; a compensation's refusals are the forward step's, prefixed *its compensation:*. |

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

**No new family.** `WF` (Session 32) and `AGT` and `OPS` are extended; the
`WF` paragraph above `ID_PATTERN` (`tests/contract/test_acceptance_registry.
py:84-93`) gains one sentence naming Session 33 (*approval, compensation and
provenance are a run's, so they are `WF`; the audit filters and the approval
claim are the agent plane's, so they are `AGT`; the ledger print is an
operator's, so it is `OPS`*). **Fourteen requirements, fourteen claims, all
`target_session: 33`, all P0** — ten offline, four host.
Every requirement belongs to a claim (D697); a new requirement gets a claim of
its own (ADR 0089, D1150). **Node ids below are proposed; Run 8 writes what the
runs actually wrote, read out of the tree with `pytest --collect-only -q`**
(D1236 — Session 32 found 27 of its 84 proposed names had been renamed by the
runs). The registry entries cannot be committed before Run 8 moves
`CURRENT_SESSION` (D690): the runs write the proofs and this table; Run 8 lands
the YAML.

| Requirement | What it states | Offline node ids (proposed) | Live half |
|---|---|---|---|
| `WF-GATE-001` | Migration 0035 creates `workflow_approval` and `workflow_attempt` with no grant to any role; `workflow_request_approval` records a pending approval carrying the refused call's request id and parks the step until its expiry; `workflow_gate_state` reports none/pending/approved/expired and whether a wait has been served; `workflow_decide_approval` approves (the step becomes claimable at once) or rejects (the run's cancel is requested), refuses the run's owner (`approver_is_owner`), refuses a second decision (`approval_already_decided`), refuses an expired approval (`approval_expired`), and changes nothing on a refusal; `workflow_approval_for_token` answers only an approved, unexpired approval of that agent's run; an approval park holds no lease; every attempt is appended to `workflow_attempt` | `test_workflow_gates.py::test_the_two_tables_grant_nothing_to_any_role`, `::test_the_new_functions_are_executable_by_the_auth_service_and_nobody_else`, `::test_begin_compensation_is_executable_by_nobody`, `::test_request_approval_records_pending_and_parks_until_expiry`, `::test_an_approval_park_holds_no_lease`, `::test_approve_makes_the_step_claimable_at_once`, `::test_reject_requests_the_runs_cancel`, `::test_the_runs_owner_cannot_decide`, `::test_a_second_decision_is_refused_and_changes_nothing`, `::test_an_expired_approval_cannot_be_decided`, `::test_the_token_lookup_answers_only_an_approved_unexpired_approval_of_that_agent`, `::test_gate_state_reports_a_served_wait`, `::test_expire_marks_only_a_pending_approval_past_its_expiry`, `::test_the_replaced_substrate_functions_keep_their_signatures`, `::test_every_finish_and_park_appends_an_attempt` | — (offline claim `workflow_gates`) |
| `WF-COMP-001` | A run that fails or is cancelled with succeeded forward steps declaring compensation becomes `compensating` with its cause; one compensation row per such step is appended in reverse order with its own derived key; a compensation row is claimed only when every earlier compensation row is finished; a failed compensation does not stop the rest; the run ends at its cause with `compensation_outcome` `complete` or `incomplete`; a run with nothing to compensate takes its cause directly; a compensating run is not timed out; a refused mint during compensation stops the run `incomplete` | `test_workflow_gates.py::test_a_failure_with_compensable_steps_becomes_compensating_in_reverse`, `::test_a_compensation_row_waits_for_the_one_before_it`, `::test_a_failed_compensation_does_not_stop_the_rest_and_ends_incomplete`, `::test_all_compensations_succeeding_ends_complete_at_the_cause`, `::test_a_cancel_with_nothing_to_compensate_is_cancelled_directly`, `::test_a_compensating_run_is_not_timed_out`, `::test_a_refused_mint_during_compensation_stops_the_run_incomplete`, `::test_the_compensation_key_is_derived_from_the_run_and_the_forward_position` | — (offline claim `workflow_compensation`) |
| `WF-DEF-002` | A definition may declare `approval: {expires_after_seconds}` on a step whose tool OR capability requires approval, and must; a step declaring approval whose tool does not require one is refused; a profile-added approval is seen (the second example project); `compensation` must be a write the lock compiles, must not require approval, takes only declared arguments and references the run's input or steps at or before its own; its scopes join `required_scopes`; `wait: {seconds}` takes no capability, is bounded below the run timeout, and `wait: {event}` is refused naming Session 34; `init`'s skeleton still validates; the example project's four definitions compile | `test_workflow_definition.py::test_an_approval_requiring_step_must_declare_approval`, `::test_a_declared_approval_on_a_step_that_needs_none_is_refused`, `::test_a_profile_added_approval_is_seen`, `::test_the_example_project_without_the_profile_is_the_control`, `::test_the_approval_expiry_is_bounded_below_the_run_timeout`, `::test_a_compensation_must_be_a_write_the_lock_compiles`, `::test_a_compensation_may_not_require_approval`, `::test_a_compensation_takes_only_declared_arguments`, `::test_a_compensation_may_not_reference_a_later_step`, `::test_compensation_scopes_join_the_required_scopes`, `::test_a_wait_takes_no_capability_and_is_bounded`, `::test_a_wait_on_an_event_is_refused_naming_session_thirty_four`, `::test_the_example_projects_four_definitions_compile` | — (offline claim `workflow_definition_gates`) |
| `WF-WORK-002` | The loop parks an approval step on the plane's `approval_required` refusal and records the plane's request id; an approved step is minted WITH the approval and called; a pending step past its expiry fails the run `approval_expired`; a dry run never requests approval and makes no call for an approval step; a wait step is parked once and then finished `waited`, with no token minted; a compensation row is called as a write with its own key; a step's stored result is the tool's own return value measured from the real plane; a scope narrowed after enqueue fails the run naming `scope_not_held` | `test_workflow_worker.py::test_an_approval_step_parks_on_the_planes_refusal_with_its_request_id`, `::test_an_approved_step_is_minted_with_the_approval_and_called`, `::test_a_pending_approval_past_its_expiry_fails_the_run`, `::test_a_dry_run_never_requests_approval`, `::test_a_wait_step_parks_once_then_finishes_and_mints_nothing`, `::test_a_compensation_row_is_called_as_a_write_with_its_own_key`, `::test_the_stored_result_is_the_tools_own_return_value`, `::test_a_scope_narrowed_after_enqueue_fails_the_run_naming_it`, `::test_the_plane_serving_an_approval_step_unasked_finishes_it_succeeded` | — (offline claim `workflow_worker_gates`) |
| `AGT-APPROVE-002` | `step_token` adds `apg_approval` only from an approved decision it reads itself and refuses otherwise; `agent_token` never adds it; `issue` refuses an extra claim that names a required one; the plane serves a `requires_approval` write only when the claim names the tool called and the key presented, refuses a claim for another tool or key and any claim with `dry_run`, with the unchanged refusal text, audited; a token without the claim is refused exactly as before (control) | `test_approval_claim.py::test_step_token_adds_the_claim_only_from_an_approved_decision`, `::test_step_token_refuses_an_undecided_or_foreign_approval`, `::test_agent_token_never_carries_the_claim`, `::test_issue_refuses_an_extra_claim_naming_a_required_one`, `::test_the_plane_serves_an_approved_write_for_its_tool_and_key`, `::test_the_plane_refuses_a_claim_for_another_tool_or_key`, `::test_the_plane_refuses_an_approved_dry_run`, `::test_a_token_without_the_claim_is_refused_as_before` (control), `::test_a_malformed_claim_is_a_claim_error` | — (offline claim `approval_claim`) |
| `AGT-AUDIT-003` | The audit reader takes a window, an outcome, a denial reason and a keyset cursor, orders by `(started_at, id)` descending, refuses an unknown outcome or reason with `PT422`, and is granted to `auth_service` alone; `auth_count_agent_audit` counts the window by outcome and reason ignoring the filters and the cursor; `GET /admin/audit` parses the five parameters strictly, returns `window_counts` on every page and a `next_cursor`; a cursor walks every row exactly once when rows share a `started_at`; Studio forwards the five and shows the window's counts | `test_agent_audit_plane.py::test_the_reader_pages_every_row_exactly_once_across_tied_timestamps`, `::test_the_window_counts_ignore_the_outcome_filter_and_the_cursor`, `::test_an_unknown_outcome_or_reason_is_refused_not_empty`, `::test_the_new_reader_and_the_counter_are_granted_to_the_auth_service_alone`, `test_migrations.py::test_0035_reissues_the_reader_grant_at_its_new_arity`, `test_auth_endpoints.py::test_the_audit_endpoint_returns_window_counts_on_every_page`, `::test_the_cursor_round_trips_and_a_forged_one_is_refused`, `::test_a_timestamp_or_member_outside_its_contract_is_refused`, `test_auth_strict_query.py::test_as_timestamp_and_as_member_refuse_and_never_coerce`, `test_studio_server.py::test_the_audit_view_forwards_the_five_filters_and_nothing_else`, `test_studio_runtime.py::test_the_audit_header_carries_the_windows_counts` | — (offline claim `audit_filters`) |
| `WF-PROV-001` | `workflow_provenance` returns the run, every step with every attempt joined to its audit rows by request id, every approval with its decider, and `profile` reported absent with a reason; `GET /admin/workflows/runs/{id}` serves it under `admin_audit:read` and refuses an agent token and a token without the scope; it answers a revoked agent's stopped run; no field carries a redacted argument value | `test_workflow_gates.py::test_provenance_joins_every_attempt_to_its_audit_rows`, `::test_provenance_names_the_approvals_decider`, `::test_provenance_reports_the_profile_absent_with_a_reason`, `test_workflow_admin_routes.py::test_provenance_is_served_under_the_audit_scope_only`, `::test_an_agent_token_is_refused_by_every_admin_workflow_route`, `::test_provenance_answers_a_revoked_agents_stopped_run`, `::test_no_admin_workflow_response_carries_an_argument_value` | — (offline claim `workflow_provenance`) |
| `WF-ADMIN-001` | The approval routes list pending approvals with no argument values, approve and reject under `admin_workflows:approve`, translate `approver_is_owner`, `approval_already_decided`, `approval_expired` and `no_such_workflow` to fixed documents, bind the decision to the step named in the body, and are named by the OpenAPI document; `admin_workflows:approve` is in the administrative class and `project_admin`'s ceiling alone | `test_workflow_admin_routes.py::test_the_four_routes_are_mounted_in_auth_mode_and_named_by_the_openapi_document`, `::test_approvals_list_pending_with_no_argument_values`, `::test_approve_and_reject_need_the_approve_scope`, `::test_each_refusal_is_a_fixed_document`, `::test_the_decision_is_bound_to_the_named_step`, `test_scope_registry.py::test_the_administrative_class_is_one_per_identity_resource_and_verb` (made stricter), `::test_an_administrative_scope_is_reachable_only_by_the_admin_role` (made stricter) | — (offline claim `workflow_admin`) |
| `WF-CMD-002` | `bin/workflow.sh` has ten verbs; `approvals`, `approve`, `reject` and `inspect` call the four admin routes and nothing else with the token from `APG_API_TOKEN`; `approve` and `reject` refuse (exit 2) unless `--confirm` equals `--run`; `inspect` prints the document whole; the command still holds no SQL | `test_workflow_command.py::test_the_four_human_verbs_call_the_enumerated_admin_routes_and_nothing_else`, `::test_the_human_verbs_take_the_api_token_and_never_the_agent_token`, `::test_approve_and_reject_refuse_without_a_matching_confirm`, `::test_inspect_prints_the_document_whole`, `test_cli_contract.py` (whole, D1014) | — (offline claim `workflow_command_human`) |
| `WF-APPROVE-001` | On the deployment: an approval step parks with ONE `approval_required` row in the audit; an agent token is refused by the approve route; the run's owner is refused `approver_is_owner`; an administrator without the scope is refused and the approval stays pending; a second administrator holding the scope approves and the run completes with ONE committed write under the step's key; alpha lists no approvals | — | `test_session33_gates.py::test_an_approval_step_parks_with_one_refusal_in_the_audit`, `::test_the_requesting_agent_cannot_approve`, `::test_the_runs_owner_cannot_approve`, `::test_an_administrator_without_the_scope_cannot_approve`, `::test_a_second_user_approves_and_the_run_completes_once`, `::test_the_project_without_a_set_lists_no_approvals` (host claim `workflow_approval_live`) |
| `WF-COMP-002` | On the deployment: a rejected run is cancelled and its first step compensated (the task back in `pending`, outcome `complete`); a terminal failure after a served wait compensates in reverse (outcome `complete`, the wait step `waited`) | — | `test_session33_gates.py::test_a_rejection_cancels_the_run_and_compensates`, `::test_a_terminal_failure_after_a_wait_compensates_in_reverse` (host claim `workflow_compensation_live`) |
| `WF-PROV-002` | On the deployment: `apg workflow inspect` reads back an approved run with every attempt joined to its audit rows and the approver named; a revoked agent's stopped run is readable by an auditor (D1704) | — | `test_session33_gates.py::test_inspect_reads_back_the_approved_run_complete`, `::test_an_auditor_reads_a_revoked_agents_stopped_run` (host claim `workflow_provenance_live`) |
| `AGT-AUDIT-004` | On the deployment: a cursor over beta's audit up to a fixed `until` returns every row exactly once against the counter's total; a page filtered to `committed` carries the window's refusal count | — | `test_session33_gates.py::test_a_cursor_pages_the_deployments_audit_once_each`, `::test_a_filtered_page_reports_the_refusals_it_did_not_show` (host claim `audit_filters_live`) |
| `OPS-LEDGER-001` | `bin/migrate.sh --runtime status` prints dbmate's own `[X]` lines and the exit is dbmate's (D1707) | `test_migrate_command.py::test_status_prints_the_ledger_lines_dbmate_wrote`, `::test_the_exit_is_dbmates_and_stderr_is_not_swallowed` | — (offline claim `migrate_status_ledger`) |

**Expected counts** — Run 8 counts them from the tuples, never from this
prose (D1628): requirements **251 → 265**, `CLAIMS` **158 → 172**,
`OFFLINE_CLAIMS` **32 → 42**, ADRs **229 → 234**.

**Claims** (`src/agentic_postgres/evidence_claims.py` `CLAIMS`, each in a block
commented *Session 33 (ADR 0230-0234)*): offline — `workflow_gates:
("WF-GATE-001",)`, `workflow_compensation: ("WF-COMP-001",)`,
`workflow_definition_gates: ("WF-DEF-002",)`, `workflow_worker_gates:
("WF-WORK-002",)`, `approval_claim: ("AGT-APPROVE-002",)`, `audit_filters:
("AGT-AUDIT-003",)`, `workflow_provenance: ("WF-PROV-001",)`,
`workflow_admin: ("WF-ADMIN-001",)`, `workflow_command_human: ("WF-CMD-002",)`,
`migrate_status_ledger: ("OPS-LEDGER-001",)` — **these ten in
`OFFLINE_CLAIMS`**, with the per-session assertion in
`test_session_thirty_three_gate_modes.py` (D1237: assert THESE ten are in the
set, never the set's size). Host — `workflow_approval_live:
("WF-APPROVE-001",)`, `workflow_compensation_live: ("WF-COMP-002",)`,
`workflow_provenance_live: ("WF-PROV-002",)`, `audit_filters_live:
("AGT-AUDIT-004",)` — not declared. `CLAIM_INTRODUCED_IN`
(`tests/contract/test_evidence_claims.py:953-1177`) gains fourteen rows at 33.

**Existing entries that move** (each a passing proof made stricter or a
sentence corrected, never weakened — CLAUDE.md §6):

- **AGT-AUDIT-002** (`tests/acceptance-registry.yaml:3807-3828`): its
  description's *"The arity stays `(uuid, uuid, integer)`"* is replaced by the
  new arity and the reason (D1741); node ids unchanged. `test_migrations.py::
  test_0032_reissues_the_reader_grant` still reads 0032's template and stays;
  a sibling `test_0035_reissues_the_reader_grant_at_its_new_arity` joins
  AGT-AUDIT-003.
- **STU-AUDIT-001** (`:3684-3706`): *"NO other parameter, which the forwarder
  refuses with 400"* becomes *"exactly the endpoint's seven parameters"*; the
  two refusal proofs (`test_studio_server.py:605`, `test_studio_runtime.py:
  1184`) are replaced by stricter ones that assert the five forward, anything
  else is still 400, and the header carries the window counts.
- **AGT-APPROVE-001** (the refusal is the guarantee, D870): its description
  gains *"… for every caller whose token carries no approval claim naming the
  tool and the key (ADR 0231)"*; its proofs are unchanged and stay green — the
  refusal without the claim is byte-identical.
- **WF-INSTALL-001** gains D1705's two node ids (Run 2); **NODE-USAGE**'s
  owning requirement (grep `no_such_series` in the registry in Run 2) keeps its
  node ids with the wording proof made stricter.
- `test_auth_endpoints.py::test_an_unknown_query_parameter_is_refused` keeps
  its node id; its example moves from `cursor` to `page`.

**New environment gates: none.** Every live proof creates its own humans,
agents, tasks and notes on `project_b` from `APG_PROJECT_B_OUTPUTS` and uses
`APG_PROJECT_A_OUTPUTS` for alpha's control; both are in the roster
(`tests/conftest.py`). **The Session 33 gate therefore accepts exactly the
flags the Session 32 gate accepts — the derivation diff proves it (D1133).**

---

## 4. Irreversible operations

| Operation | Where | What makes it safe |
|---|---|---|
| Migration **0035** written and frozen into `migrations/released.lock.json` | Run 3 | `bin/migrate.sh freeze-lock` is the only writer; the proofs apply every released migration as `migration_user` on a fresh container before the freeze; its down is `AP900`; **once applied on the host it is the floor** (ADR 0162 §3), and **0034 is never amended** (D912) — every change to a 0034 function is a `CREATE OR REPLACE` in 0035 with the SAME signature, or a `DROP`+`CREATE` for the audit reader (0032's precedent) |
| `ALTER TYPE app_private.workflow_run_status ADD VALUE 'compensating'` | Run 3 | 0029/0030's precedent (applied on production); rig 33e measures it inside dbmate's transaction first; the value is only USED in function bodies (parsed at execution), never in a DEFAULT or CHECK in the same migration |
| The audit reader re-created at a new arity | Run 3 | ADR 0175's guard finds every call site (`test_database_function_signatures.py:587`); the repository moves in the same commit; `REVOKE`/`GRANT` re-issued and asserted by `test_0035_reissues_the_reader_grant_at_its_new_arity` |
| A new administrative scope | Run 6 | ADR 0232 first; the four pinning proofs updated to the new exact sets in one commit; the lock's `vocabulary` moves on every deploy (both containers recreated — expected, and the trip's readings say so) |
| An optional token claim and `issue(extra_claims=…)` | Run 5 | ADR 0231 first; rig 33a measured PostgREST and the hook; `extra_claims` may not name a required claim (a proof); `agent_token` never passes it (an AST proof) |
| The plane's approval branch | Run 5 | The refusal without a claim is byte-identical (AGT-APPROVE-001's proofs unchanged and run); the claim must name the tool AND the key (two refusal proofs) |
| The step result's stored shape changes | Run 5 | Rig 33c's measured bytes replace the fake's; rows already on production are left as records; `test_workflow_worker.py:846-855` (depth refusal) unchanged |
| Four new admin routes; `GET /admin/audit` widened | Run 6 | Every route `authenticate` + `require_scope`; `bin/app-contract.sh --update` then `--check`; **the example client regenerated (D1690)** and `test_client_typescript`, `test_generate_command`, `test_studio_command`, `test_client_ir` run |
| `bin/deploy-project.py` step 6d unchanged but new definitions install | Run 4 / Run 9 | 6d is idempotent per `(name, version, source_sha256)`; beta installs four (two new); alpha none |
| `CURRENT_SESSION` 32 → 33; `VERSION` 1.10.0 → 1.11.0 | Run 8 | All-or-nothing (D690); every `target_session: 33` entry in the same commit; `docs/upgrade-guide.md` gains a `1.11.0` row; `README.md:7` moves; the `--session`/`--through-session 32` literals on the documented path moved (D678/D1484 — sixteen last time) |
| `bin/session-33-check.sh` | Run 8 | Derived from 32's by diff (D1482); header and usage rewritten whole (D1488); `SHELL_COMMANDS` gains it and `chmod 755` before `git add` (D1014, D1188); the verbatim `run_suite` selector kept (D1242); the flag diff empty |
| Deploy `--through-session 33` on alpha, then beta | Run 9 | `upgrade plan` OK first; alpha first, one sheet per outcome (D1510); under `script(1)`; **0035 applied** (ledger 34 → 35; beta 35 + 2); `auth` and `mcp` recreated (image and lock moved); `doctor` 12 ok after each |
| Humans, agents, tasks, notes, runs and approvals written on beta by the proofs | Run 9 | Humans deleted at teardown; agents revoked (not deletable while runs reference them, D1700); tasks and notes deleted by canary title; runs and approvals left as the substrate's record and counted in the Done |
| Tag `1.11.0` on the deployed commit | Run 9 | After the merge exits 0 or 5 for the expected reasons only (§7); `release-reading --ref <deployed sha>` first; D1641's method stated in the tag if an instrument moves |

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
(D1690); **a run that touches a documentation page runs
`test_documentation_index` and `test_session12_documented_path`**.

### Run 1 — the measurements, `THR-APPROVAL`, and ADRs 0230–0234

**Documentation only. Push, say it is pushed, read NO CI verdict.**

**Reads first** (agent, no edits): `migrations/templates/0034-workflow-
substrate.sql` whole; `services/auth-api/app/workflow_worker.py` whole;
`service.py:224-292`, `:485-628`; `claims.py` whole; `mcp_tools.py:547-652`
and `:1067-1110`; `mcp_authorization.py:190-230`; `mcp_runtime.py:225-326`;
`0019:73-160`, `0027:40-120`, `0029:60-120`, `0030:55-70`, `0032` whole;
`routes.py:300-370` and `:954-1066`; `bin/studio.py:590-640`;
`projects/example/migrations/templates/0001-note-embeddings.sql` and `0002-
agent-grants.sql`; `docs/decisions/0179-*.md`, `0226-*.md` to `0229-*.md`;
Session 32's plan §1 rows D1668–D1672 and D1696 (what its rigs found). Then
re-run the deployable-diff filter named in §0 and write its answer.

**The rigs.** Each is a script written with the Write tool to
`\\wsl$\Ubuntu\tmp\rig33x.sh` and copied to the scratchpad, each names its
image by digest from `versions.env` / `versions.lock.json` (read `bin/lock-
versions.sh --help` for the reader), each has a control, and each prints its
own exit status from inside. The cluster rigs use the recipe of `tests/
contract/test_migrations_apply_as_the_migration_user.py:95-163` (a `docker run
-d` of `POSTGRES_IMAGE`, two consecutive `pg_isready`, the product's own
`dev_environment.role_statements`, every released migration applied as
`migration_user`), and 33b/33c add the example project's set applied through
`bin/migrate.py`'s project path (read `docs/migrations.md` for the order —
release first, then the project's own directory and table, ADR 0206).

| Rig | Subject | Method | Control | Owes |
|---|---|---|---|---|
| **33a** | An extra claim on an agent token | A token minted with the service's own `issue()` shape (a throwaway RSA key, `openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048`) carrying `apg_approval: {"id": <uuid>, "tool": "create_note", "key": "wf-rig-1"}`: (i) `claims.verify_claims` returns it with the extra member intact; (ii) the built image in `APP_MODE: mcp` (rig 32b's recipe) answers `tools/list` for it and `get_access_token().claims` carries the member — read through a one-file sidecar mounted read-only if nothing else exposes it, or deferred to Run 5's rig 33g with this row saying so; (iii) the pinned PostgREST image with the rig JWKS and the rig cluster: `GET /notes` with the token → 200, and the pre-request hook (`agent_claims_are_current`, `0018:60-78`) does not refuse it | the same token without the claim (identical answers); the same claim signed by a SECOND key → 401 at both the plane and PostgREST | D1715's premise; the exact path to the claims inside a tool call |
| **33b** | Approval is a plane control, and `set_note_embedding` has no dry-run branch | The 33a stack plus the example project's set: create an `authenticated` owner, a note it owns and an `agent_writer` agent with `note_embeddings:write` (through `app_private.auth_create_agent`, the hasher from `service_source.load("hashing")`); with the agent's token, `POST /rpc/set_note_embedding` DIRECTLY to PostgREST with a 768-element zero vector as the text literal `'[0,0,…]'` → record status and the row; then the same with header `Prefer`/`Dry-Run` exactly as `mcp_upstream.py:384-391` sends it → record whether a row was written | through the built plane: `tools/call` `set_note_embedding` with the same token → `approval_required`, one `refused` audit row, no row in `app.note_embeddings` | D1721's *measured* word; D1722's *measured* word; that a text vector literal passes PostgREST into a `vector` parameter (the trip's input shape) |
| **33c** | What the real plane returns as `result` for a write | The 33b stack: `tools/call` `create_note` through the built plane with an agent token; record the full SSE body, the parsed `result` object's keys, whether `structuredContent` is present and equals `{tool, row_count, row, dry_run}`, and what `content[0].text` holds | a `query_resource` read through the same plane (its `result` shape recorded beside) | D1724: the bytes Run 5's fake uses and the rule it stores |
| **33d** | A keyset cursor over the audit with tied timestamps | On the rig cluster (all 34 migrations): as superuser insert **1,000** `agent_audit` rows in ONE statement (so all share `started_at = now()`), 50 with `outcome 'refused'`/`denial_reason 'scope_not_held'`; then page with a prototype of 0035's reader (a throwaway function in a scratch schema) at `limit 100` using `(started_at, id) < (cursor)` and `ORDER BY started_at DESC, id DESC`; collect the ids | (1) the unfiltered `count(*)` = 1,000 and the union of pages = 1,000 distinct ids with no repeat; (2) the same paging with the id tie-break REMOVED (`started_at < cursor` only) → returns 100 and stops, proving the tie-break is the mechanism | the reader's predicate and ordering, measured before 0035 is written; `EXPLAIN` with and without the new index recorded (informational) |
| **33e** | `ALTER TYPE … ADD VALUE` inside dbmate's transaction | A scratch migration applied by the pinned dbmate (the `dbmate` service's image, as `migration_user`, `SET LOCAL ROLE object_owner`): `ALTER TYPE app_private.workflow_run_status ADD VALUE 'compensating'` then `CREATE OR REPLACE FUNCTION` whose body assigns `'compensating'` — applies; after commit the function runs and writes the value | the same migration with a `DEFAULT 'compensating'` on a new column in the SAME transaction → *unsafe use of new value* (the failure 0035 must not contain) | 0035's shape for the enum; that 0029/0030's precedent holds on PostgreSQL 18.4 |

**Third-party facts already measured, cited and not re-run:** the plane's
transport and SSE framing (rig 32b, D1672); replay semantics (rig 32c, ADR
0181); definer functions over a no-grant table (rig 32d, D1647); the lease
under `SKIP LOCKED` (rig 32e); `step_token` vs `agent_token` claims (rig 32f);
`psql -c` does not interpolate `-v` (D1684); a signal to the process restarts
under `on-failure:5` and `docker kill` does not (ADR 0193).

**`THR-APPROVAL`, before any code** (D1527). One row appended to
`docs/threat-model.md` after `THR-WORKER` (`:36`), in the table's nine
columns (header `:19`):

- *Threat ID*: `THR-APPROVAL`.
- *Attacker capability*: an agent that wants a gated write to happen without a
  human's decision; a human administrator approving their own agent's work;
  a captured or replayed approval; a stale approval.
- *Protected asset*: every write a capability declares `requires_approval`.
- *Prevention*: the plane refuses a gated write unless the step token carries
  `apg_approval` naming the tool and the idempotency key (ADR 0231); only
  `auth` signs, and it adds the claim only from an approved, unexpired
  decision it reads itself; `/auth/agent-token` never adds it; a decision is
  a human access token holding `admin_workflows:approve` (administrative,
  `project_admin` alone), refused for the run's owner and refused for an agent
  token by `authenticate`; a decision is final (`approval_already_decided`)
  and expires (`approval_expired`); a replayed claim re-reads the one write by
  its key (ADR 0181).
- *Detection*: the refused first call's `approval_required` audit row; the
  `workflow_approval` record (who, when, which run and step); the provenance
  reader; the doctor's pending-approval count and oldest age.
- *Residual risk*: **approval governs the agent plane and workflows, not the
  database** — an agent holding a gated capability's scope and its own token
  can call the RPC through PostgREST directly (rig 33b, D1721); the
  approver sees who and what capability, never the argument values (D1720);
  the signing key's compromise was always total.
- *Acceptance requirement IDs*: `AGT-APPROVE-002`, `WF-GATE-001`,
  `WF-APPROVE-001`.
- *Acceptance test node IDs*: `tests/contract/test_approval_claim.py::test_the_plane_refuses_a_claim_for_another_tool_or_key`,
  `tests/contract/test_workflow_gates.py::test_the_runs_owner_cannot_decide`
  (Run 8 reads the final names out of the tree).
- *Target session*: 33.

**ADRs written after the rigs, before any code**, each indexed in
`docs/decisions/README.md` as `| [NNNN](file.md) | Title | 33 | Accepted |`:

- **0230 — An approval is a parked step and a human's recorded decision; a
  rejection is a cancel.** Context: D1714, D1716, D1719, D1720, D1736. Decision:
  the first attempt meets the plane's refusal; `workflow_request_approval`
  records it and parks until the expiry; `workflow_decide_approval` records a
  decision that is final; approve makes the step claimable at once, reject
  requests the cancel; the approval record is its own table because the
  decider is a human; the listing shows no argument values; there is no
  notification plane. Alternatives: an `approval` step kind with no tool call
  (rejected: the loop would decide what needs approval, a second authority);
  a decision row in `agent_audit` (rejected: a nullable identity in the agent
  record, ADR 0135); an unbounded wait (rejected: the run timeout already
  bounds it; widening the CHECK is a later decision).
- **0231 — An approved call carries a signed claim naming its tool and its key,
  and approval is a control on the governed path.** Context: D1715, D1721,
  D1722, rigs 33a/33b. Decision: `apg_approval {id, tool, key}` on the ONE
  step token of an approved attempt, content read from the database by
  `step_token`; `issue(extra_claims=…)` refuses a required claim's name; the
  plane serves a gated write only for the named tool and key and never with
  `dry_run`; the refusal otherwise is unchanged; the database half is priced,
  not built, and the residual is stated. Alternatives: the plane asking the
  database through a new `api` RPC (rejected: moves the `api` contract and
  every client for a check the signer can make); a header or argument
  (rejected: the agent's to set); enforcing in each project's SQL now
  (rejected for this session: priced in §10).
- **0232 — Approving is an administrative scope, and the owner of a run may not
  approve it.** Context: D1717, D1718, D1638, D1704. Decision:
  `admin_workflows:approve` in the administrative enum; its reserved relation
  name; the four pinning proofs moved to the new exact sets; the operator
  grants it by `PATCH /admin/users`; three controls (token use, owner,
  ceiling). Alternatives: `workflow_approve` as written (rejected: breaks the
  `resource:verb` grammar every scope follows); a data-class scope (rejected:
  an `authenticated` or agent role could then hold it).
- **0233 — Compensation is reverse-ordered forward steps appended when a run
  fails or is cancelled; a wait is a park with a time.** Context: D1725,
  D1726, D1727, rig 33e. Decision: the declaration; must be a write, no
  approval, scopes in the union; the `compensating` status and the two run
  columns; rows appended by `workflow_begin_compensation` at `1000 + n`; each
  undo independent; `complete`/`incomplete`; not timed out; the example uses
  `update_task_status` only; `wait: {seconds}` parks once. Alternatives:
  compensation rows created at enqueue (rejected: the plan of what might be
  undone is not a record of what was); stopping at the first failed undo
  (rejected: undos are independent and a reader needs to know which held);
  calling it rollback (refused by the stage plan).
- **0234 — Provenance is one definer function joined by the plane's request id
  across every attempt, read by an auditor; the audit reader pages with a
  keyset cursor and reports the window it filtered.** Context: D1728–D1731,
  D1248, rig 33d. Decision: `workflow_attempt`; `workflow_provenance`; the
  route under `admin_audit:read` (D1704 answered); `profile` absent with a
  reason; the reader's new arity and `auth_count_agent_audit`; the index;
  `window_counts` on every page; the opaque cursor; Studio's forwarder widened
  and three refusal proofs replaced by stricter ones. Alternatives: a run id
  column in `agent_audit` (rejected: an audit schema move, and the request id
  already correlates); paging by offset (rejected: not stable under inserts);
  a server filter without window counts (rejected: D1248's own objection).
  **Also amends ADR 0228** in a section of its own: D1723 (the compiler reads
  the effective approval) and D1724 (the stored result is the tool's value) —
  or write the amendment into 0228's file under *Amendment, Session 33*, as
  0227 was amended in Session 32; say which in the Done.

Run `pytest tests/contract/test_acceptance_registry.py tests/contract/
test_documentation_index.py -q -p no:randomly` (the ADR index proofs and the
page index). Commit (`Session 33 Run 1: the rigs, THR-APPROVAL, and ADRs
0230-0234`), push. **No CI read** — documentation only.

**Done.** 2026-09-26. **The deployable-diff filter at `2c0e9b1`** (§0's list
plus `deploy.sh` and `VERSION`) names ONE file, `src/agentic_postgres/
capacity.py` — the envelope's data, as §0 said. **The rigs ran as ONE script**
(`/tmp/rig33.py`, copied to the scratchpad with its transcript and JSON
report) on one stack: `apg dev up --project project.example.yaml` (10.8 s,
PostgreSQL **18.4**, 34 release + 2 project migrations, `app.note_embeddings`
present), PostgREST from the pinned `v14.16` digest verifying the auth
application's own JWKS, and **both application modes run from the checkout as
subprocesses** with the image's own entrypoint (`uvicorn --factory
app.main:create_app`), each environment built from nothing so the plane's
forbidden-variable guard saw what a container sees. That is a method choice,
not the plan's *built image*: the claim path is source, and the venv's fastmcp
is the pinned **3.4.0** (read before the rig). The lock was compiled by the
product's own `bin/mcp-contract.sh lock` over the fixture: seven tools,
`set_note_embedding` `requires_approval: true`, vocabulary `data` carrying
`note_embeddings:read|write`. The owner, the agent (`agent_writer`, seven
scopes) and three notes were made through `auth_create_user` /
`auth_create_agent` as the auth service and one superuser `INSERT` each.
**33a** — the agent token's twelve claims, header `RS256` + `kid` + `typ JWT`.
Re-signed with the same key plus `apg_approval {id, tool: create_note, key:
wf-rig-1}`: `claims.verify_claims` keeps the member **true**; the plane's own
`AgentTokenVerifier.verify_token` returns it in `AccessToken.claims` **true**
(control, the same token without it: **no member**); `tools/list` over HTTP
**200 with the same seven tools** for the original, the re-signed plain and
the claim-bearing token; PostgREST + the pre-request hook `GET /notes` **200,
three rows** for all three. The same claim signed by a SECOND key under the
same `kid`: verifier **None**, plane **401** `invalid_token`, PostgREST **401
`PGRST301`**. **§9's 33a stop is not met.** **33b** — with the agent's own
token, `POST /rpc/set_note_embedding` DIRECT to PostgREST with the 768-zero
text literal: **200, the row written** (one row for the note). The same with
`Idempotency-Key` + `Dry-Run: true` + `X-Request-Id`, the plane's exact
headers: **200, the row WRITTEN** — the missing dry-run branch, measured.
Control through the plane: **HTTP 200, `isError: true`, `approval_required:
this capability requires an approval this deployment cannot grant`**, ONE
`agent_plane`/`refused`/`approval_required` audit row, **no row written**. The
audit row's `request_id` is the PLANE's own id, not the caller's
`X-Request-Id` (ADR 0160, D1696 — the loop must keep reading it from the
response). D1721 and D1722 are now *measured*; nothing refused the direct call,
so D1721 stands as written. **33c** — `create_note` through the plane: `result`
keys **`content`, `isError`, `structuredContent`**; `structuredContent` is
`{tool, row_count, row, dry_run}` and **equals** `content[0].text` parsed as
JSON; `query_resource` (control) has the same three keys. D1724's inference is
confirmed and Run 5 takes the `structuredContent` branch; the SSE body is in
the report for the fake. **33d** — 1,000 rows in one statement, **one**
distinct `started_at`: the keyset with the id tie-break walked **11 pages,
1,000 rows, 1,000 distinct** (= the unfiltered count); the control without it
returned **100 and stopped**; `EXPLAIN` a Sort over a Seq Scan without the
index, an **Index Only Scan** with `(started_at DESC, id DESC)`. **33e** — the
first pass failed on the RIG (dbmate's default ledger in `public`, where
`migration_user` may not create) and was re-run with the product's own
`--migrations-table app_private.schema_migrations`: the control (`ADD VALUE
'rig_control'` + a column `DEFAULT 'rig_control'`) **refused `55P04 unsafe use
of new value`, rolled back, the enum unchanged** — and dbmate had printed
`Applied:` for it first (D941, seen again); the positive (`ADD VALUE
'compensating'` + a plpgsql definer function inserting and returning it)
**applied, rc 0**, and after commit the function returned `compensating` and
wrote one row. **No §9 stop condition was met.** **`THR-APPROVAL`** appended
after `THR-WORKER` in nine columns, citing today's refusal (D1742).
**ADRs 0230–0234 written and indexed** (234 rows); **ADR 0228's amendment is in
0228's own file** under *Amendment, Session 33* (D1723, D1724), as 0227 was
amended in Session 32. **Rows added: D1742. NEXT FREE: D1743.**

### Run 2 — the carried-in defects first: D1707, D1712, D1705, D1740

**Read first:** `bin/migrate.py:100-200` (`run_dbmate`, `run_every_set`);
`src/agentic_postgres/container_exec.py` (what `compose_run` returns — a
`CompletedProcess` with `stdout`/`stderr` when captured; read its docstring and
ADR 0218); `tests/contract/test_migrate*.py` (grep `run_dbmate` under `tests/`
for the module that already fakes `compose_run`, and use it); `bin/doctor.py:
930-980`; `bin/deploy-project.py:864-960` and `:2440-2470`;
`tests/contract/test_workflow_install.py` whole; `docs/workflows.md:60-90`.

1. **D1707.** `run_dbmate` writes `result.stdout` and `result.stderr` to its
   own stdout/stderr (decoded with `errors="replace"`, since `text=False`)
   BEFORE returning `result.returncode`. Nothing else changes: the closed
   stdin and `-T` stay (ADR 0218). Proofs (`OPS-LEDGER-001`):
   `test_status_prints_the_ledger_lines_dbmate_wrote` (a fake `compose_run`
   returning stdout `b"[X] 20260917120034_workflow_substrate.sql\n\nApplied: 34\nPending: 0\n"`;
   assert the `[X]` line and `Pending: 0` reach `capsys`) and
   `test_the_exit_is_dbmates_and_stderr_is_not_swallowed` (returncode 1 with
   stderr text → exit 1 and the text on stderr). If the module that fakes
   `compose_run` does not exist, create `tests/contract/test_migrate_command.
   py` with `pytestmark = [pytest.mark.contract, pytest.mark.p0]` before its
   first test (D1240).
2. **D1712.** `bin/doctor.py:962`'s reason becomes *"the store holds no such
   series in the current mcp process (each process mints its own series, and
   a recreated mcp has served no call yet)"*. Grep `no such series` under
   `tests/` and `src/` and move every reader (D979); the proof that reads the
   reason is made stricter to assert the words *current mcp process*.
3. **D1705.** Two proofs in `tests/contract/test_workflow_install.py` over the
   helpers step 6d calls (read `:864-960` for their names): *a project whose
   set declares no `workflows/` directory installs nothing and prints which
   of the two reasons* (no set / a set with no directory — two distinct
   sentences, both asserted), and *a definition that fails to compile refuses
   at exit 5 before step 6b* (the helper's return or the deploy's exit code,
   whichever the code makes reachable without a host — say which in the Done).
   Registered under `WF-INSTALL-001` in Run 8.
4. **D1740.** `docs/workflows.md:78-79` rewritten: *a whole-string reference
   yields the referenced value with its type; a reference inside a longer
   string is interpolated as its JSON rendering* — the two sentences
   `workflow_worker.resolve`'s docstring (`:195-198`) already says.

**Mutation battery** (§1 of CLAUDE.md, every rule): (m1) drop the stdout
write → `test_status_prints_the_ledger_lines_dbmate_wrote` FAILS; (m2) return
0 instead of `result.returncode` → the exit proof FAILS; (m3) the D1705
*nothing to install* branch's two sentences made identical → the new proof
FAILS; control: `test_validate_compiles_the_example_projects_definitions` green
in the same invocation.

**Targeted:** the migrate module, `test_doctor_readings.py`,
`test_doctor_redaction.py`, `test_workflow_install.py`, `test_cli_contract.py`,
`test_documentation_index.py`, `test_session12_documented_path.py`,
`test_acceptance_registry.py`, `test_evidence_claims.py`. Commit (`Session 33
Run 2: the carried-in defects -- the ledger printed, the usage wording, step
6d's two proofs`), push, read CI.

**Done.** 2026-09-26. **D1707**: `run_dbmate` relays the captured stdout and
stderr (decoded `errors="replace"`) before returning dbmate's exit; stdin
closed and `-T` unchanged. Deploy step 6 already printed `migrate.sh`'s stdout
and put its stderr into the failure message, so a deploy's transcript now
carries dbmate's `Applying`/`Applied` lines again and a failed `up` names
dbmate's error. **No module faked `compose_run` for `migrate.py`**, so
`tests/contract/test_migrate_command.py` is NEW (`pytestmark` contract + p0
before the first test, D1240): `test_status_prints_the_ledger_lines_dbmate_
wrote` (the `[X]` line and `Pending: 0` reach stdout; one captured
`text=False` call) and `test_the_exit_is_dbmates_and_stderr_is_not_swallowed`
(exit 1 with dbmate's error on stderr; a non-UTF-8 byte replaced, exit 2
carried). **D1712**: D1743 — the reason is per figure. **D1705**: two proofs in
`test_workflow_install.py` over the helper step 6d calls, reachable offline
through `install_workflow_definitions` itself with `load_project_manifest` and
`container_exec.run` faked: `test_a_project_with_nothing_to_install_says_
which_of_the_two_reasons` (*no migration set* and *declares none*, distinct,
no container reached, the lock never read) and `test_a_definition_that_does_
not_compile_refuses_the_deploy_at_exit_five` (the example lock, the example
definition with one capability renamed → `SystemExit(5)` naming the file,
nothing installed; control in the same test: the unmodified definition is
installed). That the helper runs before 6b is the existing ordering proof.
**D1740**: `docs/workflows.md` now states the compiler's rule (a malformed
marker is refused) and the loop's (a whole reference keeps its type; an
embedded one interpolates its JSON rendering) — the compiler ADMITS an
embedded reference (`_references` consumes every well-formed one and refuses
only the residue), so the page's *"there is no partial interpolation"* was
wrong about the definition too. **Battery 5/5 killed**, each `FAILED`, none
`ERROR`, control `test_validate_compiles_the_example_projects_definitions`
PASSED in every arm, every anchor pre-flighted to one match, restored by copy
and `cmp`: (m1) the stdout relay dropped; (m2) `return 0`; (m3) the two
sentences identical; (m4) an uncompilable definition printed and skipped
rather than refused; (m5) the caller passing the default sentence. **Targeted,
once: 809 passed** (the migrate module, `test_doctor_readings`,
`test_doctor_redaction`, `test_workflow_install`, `test_cli_contract`,
`test_documentation_index`, `test_session12_documented_path`,
`test_acceptance_registry`, `test_evidence_claims`, and the module-shape guard
`test_deployment_module_shape` because a module was added). **For Run 8's
registry**: the two migrate proofs are `OPS-LEDGER-001`'s; the two D1705 proofs
join `WF-INSTALL-001`; the D1712 proof joins the requirement that owns
`doctor usage` (grep `test_the_store_query_sums_across_instances` in the
registry). **Rows added: D1743. NEXT FREE: D1744.** **CI:** `446cf809322a935a32d7eeb16d05e9cd9dc33794`
→ `contract` **success**. (`6bb2139`, pushed before it, carries this run's
plan records under the PLANNING session's message: a stale
`/tmp/s33-commit.sh` from planning ran in place of this run's script. Its
diff is the plan file alone; it is left as pushed and `446cf80`'s message
says so.)

### Run 3 — migration 0035: the gates, compensation, the attempt history, provenance and the audit reader, under a real cluster

**Read first:** `migrations/manifest.json`'s last entry and its `placeholders`
block; 0034 whole again; `0032` whole; `0019:99-160`; `0033:280-337`;
`docs/migrations.md`; `tests/contract/test_workflow_substrate.py` whole (its
cluster fixture and helpers — **copy them, do not import across modules**);
`tests/contract/test_agent_audit_plane.py:770-1180` (the reader's proofs and
`READER`); `tests/contract/test_database_function_signatures.py:60-230` and
`:560-620` (how a `DROP FUNCTION` + `CREATE` is modelled — **if the guard
cannot model a same-name re-creation at a new arity, STOP (§9)**);
`tests/contract/test_migrations.py:150-190` (`test_0032_reissues_the_reader_
grant`) and `test_every_granted_function_has_a_caller` (grep it; D1680);
`services/auth-api/app/workflow_repository.py` whole; `repository.py:300-350`.

**The template `migrations/templates/0035-workflow-gates.sql`**, version
`20260917120035`, placeholders `object_owner` and `auth_service` (exactly
these two, asserted by a marker scan; **no `{{` in a comment**, D1679), a
manifest entry whose description says what is here, what is NOT (no RLS, no
new errcode family beyond 0034's, no `NOTIFY pgrst` — `api` is untouched — no
change to any 0034 signature), and which ADRs. The body, in order, every
function `LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path =
pg_catalog, pg_temp` (STABLE for readers) with a `COMMENT ON FUNCTION`, every
refusal `RAISE EXCEPTION 'APnnn: …' USING ERRCODE = 'PTnnn'` reusing only
`PT403/PT404/PT409/PT422` (grep `PT[0-9]{3}` over the templates first and say
the set in the Done):

1. `-- migrate:up`, the header comment in 0034's voice, `SET LOCAL ROLE
   {{object_owner}};`.
2. **The enum value**: `ALTER TYPE app_private.workflow_run_status ADD VALUE
   'compensating';` (rig 33e; used ONLY inside function bodies below). **A new
   enum** `app_private.workflow_approval_status AS ENUM ('pending',
   'approved', 'rejected', 'expired')`.
3. **Columns**: `ALTER TABLE app_private.workflow_step ADD COLUMN phase text
   NOT NULL DEFAULT 'forward' CHECK (phase IN ('forward', 'compensation')),
   ADD COLUMN compensates integer CHECK (compensates IS NULL OR compensates >=
   1)`; `ALTER TABLE app_private.workflow_run ADD COLUMN compensation_cause
   app_private.workflow_run_status, ADD COLUMN compensation_outcome text CHECK
   (compensation_outcome IS NULL OR compensation_outcome IN ('complete',
   'incomplete'))`. (The `compensation_cause` column's TYPE is the enum, which
   is legal in the same transaction; only a USE of the new VALUE is not.)
4. **Tables**, owner `{{object_owner}}`, no grants:
   - `workflow_approval(id uuid PK DEFAULT gen_random_uuid(), run_id uuid NOT
     NULL REFERENCES app_private.workflow_run(id), step_id uuid NOT NULL
     UNIQUE REFERENCES app_private.workflow_step(id), tool text NOT NULL CHECK
     (tool <> ''), capability text NOT NULL CHECK (capability ~
     '^[a-z][a-z0-9_]*@[0-9]+\.[0-9]+\.[0-9]+$'), idempotency_key text NOT
     NULL, requested_request_id uuid, requested_at timestamptz NOT NULL DEFAULT
     now(), expires_at timestamptz NOT NULL, status app_private.
     workflow_approval_status NOT NULL DEFAULT 'pending', decided_by uuid
     REFERENCES app_private.users(id), decided_at timestamptz, CHECK ((status
     IN ('approved','rejected')) = (decided_by IS NOT NULL AND decided_at IS
     NOT NULL)))`; index on `(status, requested_at)`.
   - `workflow_attempt(step_id uuid NOT NULL REFERENCES app_private.
     workflow_step(id), attempt integer NOT NULL CHECK (attempt >= 1), event
     text NOT NULL CHECK (event IN ('finished', 'parked',
     'approval_requested')), outcome app_private.workflow_step_outcome,
     request_id uuid, reason text, recorded_at timestamptz NOT NULL DEFAULT
     now(), PRIMARY KEY (step_id, attempt, event))`.
   - The index `agent_audit_started_id_idx ON app_private.agent_audit
     (started_at DESC, id DESC)` with a comment citing rig 33d and 0033's
     reason for having added none (a prune is a Seq Scan by choice; a keyset
     page is not a prune).
5. **Replaced in place (`CREATE OR REPLACE`, the SAME signature and return
   type as 0034 — a proof compares `pg_get_function_identity_arguments` and
   `pg_get_function_result` before and after):**
   - `workflow_claim_step(text, integer)`: 0034's three phases, with (a) the
     cancel phase calling `app_private.workflow_begin_compensation(r.id,
     'cancelled')` for each run it cancels instead of setting `cancelled`
     directly; (b) the timeout phase calling it with `'failed'` after setting
     `stopped_reason = 'timed_out'`; (c) the selection taking EITHER a forward
     step under 0034's predicate from runs in `('queued','running')` OR a
     compensation step from runs in `('compensating')` whose earlier
     compensation rows (`phase = 'compensation' AND position < s.position`)
     are all in `('succeeded','failed')`; (d) the returned `step` being, for a
     compensation row, `((d.body -> 'steps') -> (s.compensates - 1)) ->
     'compensation'`; (e) `prior` unchanged (forward succeeded steps only).
   - `workflow_finish_step(uuid, text, workflow_step_outcome, jsonb, text,
     uuid)`: 0034's branches for a FORWARD step, except the failure branch
     (`ELSE`) and `token_refused` both hand the run to `workflow_begin_
     compensation(run, 'failed')` / leave `stopped` respectively; for a
     COMPENSATION step: record the outcome, and when no compensation row of
     the run remains unfinished, set the run to `compensation_cause` with
     `compensation_outcome` = `complete` iff every compensation row
     `succeeded`; a `token_refused` compensation stops the run with
     `compensation_outcome 'incomplete'`. **Every path appends one
     `workflow_attempt` row** (`event 'finished'`).
   - `workflow_park(uuid, text, text, timestamptz, uuid)`: 0034's body plus a
     `workflow_attempt` row (`event 'parked'`).
   - `workflow_run_status(uuid, uuid)`: 0034's document plus `phase`,
     `compensates` per step and `compensation_cause`, `compensation_outcome`
     on the run, and `approval: {status, expires_at}` on a step that has one
     (never the decider — the agent's own read does not name a human).
   - `workflow_counts()`: 0034's document plus `approvals_pending` (count) and
     `oldest_pending_approval_age_seconds` — **no threshold** (D1441).
6. **New functions:**
   - `workflow_begin_compensation(p_run uuid, p_cause app_private.
     workflow_run_status) RETURNS text` — **granted to NOBODY** (called only by
     other definer functions, which run as its owner). Inserts, for each
     SUCCEEDED forward step of the run whose compiled body element carries a
     `compensation` object, ordered by position DESC, a step row: `position =
     1000 + row_number()`, `name = 'undo-' || position`, `phase =
     'compensation'`, `compensates = <forward position>`, `retry_max`,
     `backoff_seconds`, `timeout_seconds` from the compensation object
     (defaults 0/30/the forward step's), `idempotency_key = 'wf-' || run ||
     '-undo-' || <forward position>`. If it inserted any: run `compensating`,
     `compensation_cause = p_cause`, `stopped_reason` kept; else the run takes
     `p_cause` and `finished_at`. Returns the run's new status.
   - `workflow_request_approval(p_step uuid, p_holder text, p_request_id uuid,
     p_expires_after_seconds integer) RETURNS text` — the lease predicate
     (`claimed_by = p_holder AND status = 'claimed'`, else `'lease_lost'`);
     `p_expires_after_seconds` 60..3600 else `PT422`; inserts the approval
     (tool, capability and key from the step's compiled body and row;
     `expires_at = now() + interval`); parks the step with `resume_after =
     expires_at`, reason `approval_required`, `request_id = p_request_id`;
     appends `workflow_attempt` (`event 'approval_requested'`). Returns
     `'parked'`. A second call for a step that already has an approval row is
     `PT409` (`an approval was already requested for this step`).
   - `workflow_gate_state(p_step uuid, p_holder text) RETURNS jsonb` (STABLE)
     — only for a step `claimed_by = p_holder` (else `PT404`); returns
     `{"approval": null | {"id", "status", "expires_at"}, "waited": bool}` where
     `status` reads `expired` when `pending` and `expires_at <= now()`, and
     `waited` is whether a `workflow_attempt` row with `event 'parked'` and
     `reason 'waiting'` exists for the step. The worker's ONE read at a gate.
   - `workflow_expire_approval(p_step uuid, p_holder text) RETURNS text` —
     the lease predicate; sets a pending, past-expiry approval `expired`;
     returns `'expired'` or `'not_expired'`. (Called by the worker before it
     finishes the step `failed`/`approval_expired`.)
   - `workflow_decide_approval(p_run uuid, p_step_name text, p_user uuid,
     p_decision text) RETURNS text` — `p_decision IN ('approve','reject')` else
     `PT422`; the approval of the run's step named `p_step_name` (none →
     `PT404` `no such run`, the same one message); `p_user = run.owner_id` →
     `PT403` `approver_is_owner`; `status <> 'pending'` → `PT409`
     `approval_already_decided`; `expires_at <= now()` → `PT409`
     `approval_expired`; approve → `status 'approved'`, decider, time, step
     `resume_after = now()`; reject → `status 'rejected'`, decider, time, run
     `cancel_requested_at = coalesce(cancel_requested_at, now())`. Returns the
     new approval status. **A refusal changes nothing** (every check before
     the first write; a proof reads the row before and after).
   - `workflow_pending_approvals(p_limit integer) RETURNS jsonb` (STABLE) —
     `p_limit` 1..100 else `PT422`; pending, unexpired approvals oldest first:
     `run_id, definition, definition_version, step, position, capability,
     tool, agent_id, owner_id, requested_at, expires_at`. **No input, no
     argument, no result.**
   - `workflow_approval_for_token(p_approval uuid, p_agent uuid) RETURNS TABLE
     (tool text, idempotency_key text)` (STABLE) — the row only when `status
     'approved'`, `expires_at > now()` and the run's `agent_id = p_agent`;
     otherwise zero rows (the caller refuses on zero).
   - `workflow_provenance(p_run uuid) RETURNS jsonb` (STABLE) — `PT404` for a
     missing run; the document of D1729: run fields including `agent_id`,
     `owner_id`, `input`, the definition's `name`, `version`, `source_sha256`,
     `lock_tools_sha256`; `steps[]` ordered by position, each with `phase`,
     `name`, `compensates`, `capability`/`tool` (from the compiled element or
     its `compensation`), `idempotency_key`, `status`, `outcome`, `reason`, and
     `attempts[]` from `workflow_attempt` ordered by `(attempt, recorded_at)`,
     each with `audit[]` = the `agent_audit` rows whose `request_id` equals the
     attempt's (`source, outcome, denial_reason, row_count, elapsed_ms,
     capability_version, contract_hash, started_at, completed_at` — **never
     `parameters`**); `approvals[]` with `status`, `requested_at`,
     `requested_request_id`, `expires_at`, `decided_by`, the decider's
     `username` (joined from `app_private.users`), `decided_at`; and
     `"profile": {"value": null, "reason": "no per-call record names a
     profile"}`.
   - **The audit reader, re-created**: `DROP FUNCTION app_private.
     auth_list_agent_audit(uuid, uuid, integer);` then `CREATE FUNCTION app_
     private.auth_list_agent_audit(p_agent_id uuid, p_owner_id uuid, p_since
     timestamptz, p_until timestamptz, p_outcome text, p_denial_reason text,
     p_before_started_at timestamptz, p_before_id uuid, p_limit integer)` with
     0032's `RETURNS TABLE` unchanged, `LANGUAGE plpgsql STABLE` (plpgsql so
     an unknown `p_outcome`/`p_denial_reason` is `PT422` — compare against
     `enum_range(NULL::app_private.agent_audit_outcome)::text[]` and the
     denial enum — rather than a cast error), the WHERE of 0032 plus `(p_since
     IS NULL OR r.started_at >= p_since) AND (p_until IS NULL OR r.started_at
     < p_until) AND (p_outcome IS NULL OR r.outcome::text = p_outcome) AND
     (p_denial_reason IS NULL OR r.denial_reason::text = p_denial_reason) AND
     (p_before_started_at IS NULL OR (r.started_at, r.id) <
     (p_before_started_at, p_before_id))`, a half-given cursor (one of the two
     NULL) `PT422`, `ORDER BY r.started_at DESC, r.id DESC LIMIT p_limit`.
   - `auth_count_agent_audit(p_agent_id uuid, p_owner_id uuid, p_since
     timestamptz, p_until timestamptz) RETURNS jsonb` (STABLE) — `{"total": n,
     "by_outcome": {…}, "by_denial_reason": {…}}` over the same agent/owner/
     window predicate and NOTHING else.
7. **Privileges** (as the owner, `RESET ROLE` BELOW, D285): `REVOKE ALL …
   FROM PUBLIC` on every new function and on the re-created reader; `GRANT
   EXECUTE … TO {{auth_service}}` on `workflow_request_approval`,
   `workflow_gate_state`, `workflow_expire_approval`,
   `workflow_decide_approval`, `workflow_pending_approvals`,
   `workflow_approval_for_token`, `workflow_provenance`,
   `auth_list_agent_audit` (new arity), `auth_count_agent_audit`; **nothing**
   for `workflow_begin_compensation`. The replaced 0034 functions KEEP their
   grants (a `CREATE OR REPLACE` does not touch them — asserted). A comment
   block on why schema USAGE is not re-granted (D337). `RESET ROLE;`. **No
   `NOTIFY pgrst`.**
8. `-- migrate:down` with the `AP900` block verbatim from 0034 (`:1060-1064`).

**Then** `bin/migrate.sh freeze-lock` (read its usage; it writes
`migrations/released.lock.json`), `bin/migrate.sh verify-lock`, the manifest
entry (every earlier entry byte-identical — compare before writing),
`docs/migrations.md` gains 0035's line, both example projects re-rendered
(D1678), and the literal `34` wherever a proof or prose pins the count (grep
`\b34\b` in `tests/contract/test_rendered_migrations.py` and
`src/agentic_postgres/capacity.py`; Session 32 found one at
`test_rendered_migrations.py:580`).

**The callers, in the same commit (D1680):** `workflow_repository.py` gains
`request_approval`, `gate_state`, `expire_approval`, `decide`,
`pending_approvals`, `approval_for_token`, `provenance` — each one `SELECT
app_private.workflow_…(%s, …)` with parameters, nothing formatted — and
`repository.py`'s `list_agent_audit` moves to the nine-argument call with a
new `count_agent_audit`. The route keeps passing `None` for the four new
filters until Run 6, so behaviour is unchanged this run; the guard sees a
caller for every grant.

**Proofs** — `tests/contract/test_workflow_gates.py`, `pytestmark =
[pytest.mark.contract, pytest.mark.p0, pytest.mark.database,
pytest.mark.security]` before the first test (D1240), the cluster fixture
copied from `test_workflow_substrate.py` with its skips, every migration
applied as `migration_user`; every function exercised through `psql -U
postgres -c "SET ROLE <auth_service>; SELECT app_private.…"`; the proofs of §2
`WF-GATE-001`, `WF-COMP-001` and the three provenance proofs of `WF-PROV-001`
(audit rows for the join are inserted as superuser with chosen
`request_id`s). Plus, in `test_agent_audit_plane.py`, the four
`AGT-AUDIT-003` reader proofs (the tie-break proof inserts 1,000 rows in one
statement, rig 33d's shape) and the existing reader proofs moved to the new
arity (`READER` unchanged; each `(%s, %s, %s)` call site becomes the
nine-argument form with `NULL`s — **a changed call spelling, not a weakened
assertion**, and the Done lists every edited line); in `test_migrations.py`,
`test_0035_reissues_the_reader_grant_at_its_new_arity`; and a signature proof
`test_the_replaced_substrate_functions_keep_their_signatures`. Expiry proofs
insert an approval with `expires_at` in the past as superuser rather than
sleeping; lease proofs keep rig 32e's 3 s over a 2 s lease.

**Mutation battery**: (m1) drop `p_user = run.owner_id` → `test_the_runs_
owner_cannot_decide` FAILS; (m2) the decide function's `status <> 'pending'`
check removed → `test_a_second_decision_is_refused_and_changes_nothing`
FAILS; (m3) `workflow_approval_for_token` without the `p_agent` predicate →
its proof FAILS; (m4) compensation rows ordered ASC → `test_a_failure_with_
compensable_steps_becomes_compensating_in_reverse` FAILS; (m5) the reader's
id tie-break removed → `test_the_reader_pages_every_row_exactly_once_across_
tied_timestamps` FAILS (rig 33d predicts: stops after one page); (m6) grant
`workflow_begin_compensation` to `{{auth_service}}` → the nobody proof FAILS;
control in EVERY invocation: `test_workflow_substrate.py::test_the_migration_
applies_as_the_migration_user_and_its_down_refuses`. Each kill must read
`FAILED`, never `ERROR` (D386); anchors pre-flighted to exactly one match with
a miss fatal (D269); restore by copy and `cmp`; `PYTHONDONTWRITEBYTECODE=1` and
`__pycache__` cleared before each arm (D1198).

**Targeted**, once at the close: `test_workflow_gates.py`,
`test_workflow_substrate.py`, `test_workflow_repository.py`,
`test_agent_audit_plane.py`, `test_migrations_apply_as_the_migration_user.
py`, `test_rendered_migrations.py`, `test_database_function_signatures.py`,
`test_project_migration_sets.py`, `test_migrations.py`,
`test_auth_service_shape.py`, `test_auth_endpoints.py` (the reader's call
moved), `test_acceptance_registry.py`, `test_evidence_claims.py`,
`test_documentation_index.py`, `test_session12_documented_path.py`. **The
sweep-selector guard passes vacuously for the new module until Run 8 lands the
registry — say so rather than rely on it** (D1240/D1242). Commit (`Session 33
Run 3: migration 0035 -- approvals, compensation, the attempt history,
provenance and the audit reader`), push, read CI. **Until Run 9's deploy, 0035
may be amended in place, re-frozen and both projects re-rendered (Session 32
amended 0034 twice this way, D1686/D1687/D1696); after Run 9 it is the floor.**

**Done.** 2026-09-26. **Migration 0035** (`20260917120035`, `workflow_gates`,
placeholders `object_owner` and `auth_service`) written as §5 describes, with
four decisions the plan did not take, each a row: the timeout phase skips a
run with a call in flight and a late forward finish never moves an ended run
(**D1744**); the signer's lookup does not re-check an APPROVED decision's
window but requires a running run of that agent (**D1745**); provenance
carries the input's KEYS only (**D1746**); a decidable approval is pending,
unexpired, on a running run, for the listing, the count and the decision
(**D1747**). **D1748**'s premise was checked and found false in the
reassuring direction (a step name admits no hyphen, so `undo-<n>` cannot
collide); Run 4 pins it. Refusal errcodes reused: PT403, PT404, PT409, PT422
(no new one). An undo row's claimed `step` is the forward element's
`compensation` block with the row's own `name` merged in; `prior` is
forward results only. Manifest entry appended by a script that asserted the
re-serialisation byte-identical first (34 → 35 entries); `bin/migrate.sh
freeze-lock` appended ONE lock entry (11 insertions) and `verify-lock`
agrees; both example projects re-rendered by the gate's own `./deploy.sh
--render-only` invocation, exit 0 each (D1678). **`docs/migrations.md` lists
no individual migration** (0034 has no line either), so the plan's *"gains
0035's line"* had nothing to attach to; nothing was added. **The arity guard
models the DROP + CREATE at its position** (`released_signatures`), so §9's
stop did not fire. **Callers in the same commit (D1680):**
`workflow_repository.py` gains `request_approval`, `gate_state`,
`expire_approval`, `decide`, `pending_approvals`, `approval_for_token`,
`provenance`; `repository.py`'s `list_agent_audit` sends nine parameters
(the four new filters default to `None`, so the route is unchanged until
Run 6) and gains `count_agent_audit`. **Proofs:** NEW
`tests/contract/test_workflow_gates.py` (`pytestmark` before the first test;
the cluster fixture COPIED from the substrate module), 32 proofs — the §2
WF-GATE-001 and WF-COMP-001 sets (two renamed from the proposal:
`test_the_token_lookup_answers_only_an_approved_approval_of_that_agents_
running_run`, per D1745; `test_pending_approvals_list_no_argument_value_
oldest_first` added), plus `test_a_step_that_declares_no_approval_cannot_
open_a_gate`, `test_a_decision_on_an_unknown_step_or_run_is_the_one_refusal`,
`test_a_timed_out_run_with_a_call_in_flight_waits_for_the_call` (D1744), the
four provenance proofs (`..._joins_every_attempt_to_its_audit_rows`,
`..._names_the_approvals_decider`, `..._reports_the_profile_absent_with_a_
reason`, `..._carries_no_parameters_result_or_input_value`) and
`test_provenance_refuses_a_missing_run`. In `test_agent_audit_plane.py`, the
four AGT-AUDIT-003 proofs; the six existing reader call sites moved to the
nine-argument form through one constant `SIX_NULLS` (lines 908, 936, 985,
1069, 1126, 1175 at the time of the edit — a changed spelling, no assertion
changed); `test_the_audit_read_returns_the_boundary_exactly_on_refused_rows`'s
arity control moved from `"3"` to `"9"` AND now also asserts that
`repository.py` sends nine placeholders (stricter, under ADR 0234). In
`test_migrations.py`, `test_0035_reissues_the_reader_grant_at_its_new_arity`
(the counter held to the same order). In `test_workflow_repository.py`, NEW
`test_every_workflow_function_0035_grants_is_called_by_this_module` (seven,
and `workflow_begin_compensation` NOT called) and the placeholder proof
widened to read 0035's declarations too. **Three existing proofs moved to
the measured sets, none weakened:** the substrate's count pin 34 → 35; its
RLS reading of every `workflow%` table four → six (node id kept); its counts
key set + `approvals_pending`, `oldest_pending_approval_age_seconds`.
**Every proof in both cluster modules passed on first execution (56)**,
which is why the battery mattered: **8/8 killed**, each `FAILED`, none
`ERROR`, control `test_workflow_substrate.py::test_the_migration_applies_as_
the_migration_user_and_its_down_refuses` PASSED in every arm, anchors
pre-flighted, restored by copy and `cmp`: (m1) the owner check removed; (m2)
the already-decided check removed; (m3) the token lookup without its agent
predicate; (m4) undo rows ASC; (m5) the reader's id tie-break removed; (m6)
`workflow_begin_compensation` granted to the auth service; (m7) the D1744
in-flight guard removed; (m8) provenance returning the input. **Targeted,
once: 518 passed** (the fifteen modules of the plan's list plus
`test_auth_service_database_access` and `test_deployment_module_shape`); two
E501s ruff found after it were marked and `test_agent_audit_plane` re-run
alone: 66 passed. **The sweep-selector guard passes vacuously for the new
module until Run 8 lands the registry.** **Rows added: D1744–D1748. NEXT
FREE: D1749.** **CI:** `c369236cb8fbc19e27b1fddf781d13e1c1a54de2` →
`contract` **success**.

### Run 4 — the definition: `approval`, `compensation`, `wait`, the profile fix, the two example definitions

**Read first:** `src/agentic_postgres/workflow_definition.py` whole (740
lines — `LockView` `:204-218`, `CapabilityView` and `:227`, `resolve`
`:273-339`, `_references` `:471-476`, `_accepted_arguments` `:487-505`,
`_step_timeout` `:511-529`, `_retry` `:537-542`, `compile` `:554-594`, the
digests `:388`, `:624`, the vocabulary use `:712`); `schemas/workflow.schema.
json` whole; `src/agentic_postgres/capability_compiler.py:600-623` and
`:706-782`; `project.second.example.yaml:60-90`; `bin/workflow.py:176-260`
(`init` skips approval-requiring writes, `:176-211`); `tests/contract/test_
workflow_definition.py` whole; `tests/contract/test_workflow_command.py:131-
196`; `docs/workflows.md` whole.

1. **The schema** (`schemas/workflow.schema.json`): a step is EITHER a
   capability step (`capability` required) OR a wait step (`wait` required,
   `capability`/`arguments`/`retry`/`timeout_seconds`/`approval`/
   `compensation` forbidden) — `oneOf` with two `required` sets. New
   properties: `approval: {expires_after_seconds: integer 60..3600,
   additionalProperties false}`; `compensation: {capability: <the same
   name@x.y.z pattern>, arguments: <the same shape as a step's>, retry: <the
   same>, timeout_seconds: <the same>, additionalProperties false}`; `wait:
   {seconds: integer 1..3600, event: string}` — `event` is admitted by the
   SCHEMA so the COMPILER can refuse it naming Session 34 with a sentence
   rather than a schema path. **`schema_version` stays 1**: every addition is
   optional, both existing definitions validate byte-for-byte unchanged, and
   their `source_sha256` does not move (a proof re-hashes them).
2. **The compiler** — every refusal a `DefinitionError(step_name, sentence)`
   in the house voice, each proved:
   - **D1723**: the effective approval is `tool.requires_approval or
     capability.requires_approval`; `CapabilityView` gains the tool-level field
     read from the lock's tool entry. A step whose effective approval is true
     and which declares no `approval:` → *"`{cap}` requires approval; declare
     `approval: {expires_after_seconds: N}` on this step, and a human holding
     admin_workflows:approve will decide each run"*. A step declaring
     `approval:` whose effective approval is false → *"`{cap}` does not require
     approval, so the plane would serve the first call and no human would ever
     be asked -- remove `approval:`"*. The Session 32 refusal sentence
     (`:324-329`) is REPLACED by these two; the proof that asserted *"Session
     33"* in it (`test_workflow_definition.py:222-231`) is replaced by
     `test_an_approval_requiring_step_must_declare_approval` (a stricter
     proof: it asserts the new sentence AND that the same step compiles once
     `approval:` is added).
   - `expires_after_seconds >= timeout_seconds` of the run → refused naming
     both numbers (D1719).
   - **Compensation**: resolved exactly as a step's capability (unknown,
     version, inactive, metadata refusals reused); then refused if its tool is
     not `kind: write` (*"a compensation undoes a write with a write; `{cap}`
     is a {kind}"*), if its effective approval is true (*"a compensation may
     not wait for a human; a run that is failing cannot be left half-undone
     until someone answers"*), if an argument is undeclared, if a reference
     names a step AFTER the one it compensates (it may name the run's input,
     the step itself and earlier steps). Declared on a READ step → refused
     (*"a read changed nothing to undo"*). Its scopes join `required_scopes`.
     The compiled step carries `compensation: {kind: "write", tool,
     capability, version, arguments, retry, timeout_seconds}` (the timeout
     through `_step_timeout` against the compensation's own tool floor).
   - **Wait**: compiled `{name, kind: "wait", seconds, timeout_seconds: 5,
     retry: {max: 0, backoff_seconds: 1}}` (the substrate's CHECKs need a step
     timeout and retry; 5 s is the claim-to-park window, stated in a `#:`
     comment); `seconds >= timeout_seconds` of the run → refused; `event:`
     present → *"a wait on an event arrives in Session 34 with the events that
     resume it; this release waits on a time only"*.
   - **Reference grammar unchanged** (`:71`); the embedded-interpolation rule
     is now documented (D1740, Run 2).
3. **`init`** keeps skipping approval-requiring writes in its skeleton
   (`bin/workflow.py:176-211`, `test_the_skeleton_never_names_a_capability_
   that_requires_approval` unchanged) — the skeleton is the smallest
   definition that validates, and it still validates.
4. **The two example definitions** (`projects/example/workflows/`), each with a
   header comment in `notes-retry.yaml`'s voice saying what it is FOR, what it
   takes as input and why the input is not a literal:
   - **`tasks-approval.yaml`**, `schema_version 1`, `version 1`,
     `timeout_seconds 1800`: `start_the_task` — `update_task_status@1.0.0`
     `{p_task_id: "{{input.task_id}}", p_expected_status: pending,
     p_new_status: in_progress}`, `compensation: {capability:
     update_task_status@1.0.0, arguments: {p_task_id: "{{input.task_id}}",
     p_expected_status: in_progress, p_new_status: pending}, retry: {max: 1,
     backoff_seconds: 5}}`; `set_the_embedding` — `set_note_embedding@1.0.0`
     `{p_note_id: "{{input.note_id}}", p_embedding: "{{input.embedding}}"}`,
     `approval: {expires_after_seconds: 900}`; `finish_the_task` —
     `update_task_status@1.0.0` in_progress→completed.
   - **`tasks-compensate.yaml`**, `timeout_seconds 600`: `start_the_task` (the
     same step and compensation); `pause` — `wait: {seconds: 5}`;
     `touch_a_missing_task` — `update_task_status@1.0.0` `{p_task_id:
     "{{input.missing_task_id}}", p_expected_status: pending, p_new_status:
     in_progress}` (a uuid that names nothing → `row_not_found`, terminal —
     `0030-agent-dry-run.sql`'s PT404 branch; the header says so).
   `bin/workflow.sh validate --project project.second.example.yaml`
   (beta's shape) compiles four definitions; **the release project
   (`project.example.yaml`) with no profile is the D1723 control** (read which
   of the two example manifests names `projects/example` and which carries the
   approval profile — `project.second.example.yaml:79-80` — before writing the
   proofs, and say which in the Done).
5. **`docs/workflows.md`**: `## A definition` gains *Approval*, *Compensation*
   and *Wait* subsections (what each key takes, what the compiler refuses, and
   the sentence that a note cannot be un-created in this release, D1726); the
   *What is not here yet* table (`:184-191`) loses its four Session 33 rows and
   keeps 34's; a new `## Approvals` section says who may approve (D1718), what
   the approver sees (D1720), that a rejection is a cancel, and D1721's
   residual in one sentence.

**Mutation battery**: (m1) read `capability.requires_approval` only (the D1723
defect restored) → `test_a_profile_added_approval_is_seen` FAILS and
`test_the_example_project_without_the_profile_is_the_control` stays green;
(m2) admit a read tool as a compensation → its proof FAILS; (m3) drop the
compensation scopes from the union → `test_compensation_scopes_join_the_
required_scopes` FAILS; (m4) allow a reference to a later step in a
compensation → its proof FAILS; control: `test_the_example_projects_four_
definitions_compile` in every invocation.

**Targeted:** `test_workflow_definition.py`, `test_workflow_command.py`,
`test_workflow_install.py`, `test_dev_environment_cluster.py` (`apg dev up`
installs four definitions now — run it; it is Docker-backed, so once),
`test_capability_compiler.py` (untouched, run because `apply_profile`'s reader
moved), `test_documentation_index.py`, `test_session12_documented_path.py`,
`test_acceptance_registry.py`, `test_evidence_claims.py`. Commit (`Session 33
Run 4: the definition gains approval, compensation and wait; the compiler sees
a profile's approval`), push, read CI.

**Done.** 2026-09-26. **The schema** (`schemas/workflow.schema.json`,
`schema_version` still 1): a step is `oneOf` a capability step or a wait step,
the four shared shapes moved to `$defs` (`capability_reference`, `arguments`,
`retry`, `step_timeout`) so `compensation` reuses them, and `approval`,
`compensation`, `wait` added as the plan wrote them. **The compiler**
(`src/agentic_postgres/workflow_definition.py`): `ToolView` gains the TOOL's
`requires_approval` and `Resolved.requires_approval` is the tool's OR the
capability's (**D1723 repaired**); Session 32's refusal sentence removed from
`resolve` and replaced by the plan's two in `_approval`, with D1719's bound
naming both numbers; `_compensation` (every refusal the plan lists, the
scopes joined, the retry and the timeout through `_step_timeout` against the
compensation's own tool); `_compile_wait` (`{name, kind: wait, seconds,
timeout_seconds: 5, retry: {max: 0, backoff_seconds: 1}}`, the 5 s stated
as the claim-to-park window in a `#:` comment; `event` refused naming
Session 34). The compiled compensation block uses the forward step's key
names (**D1751**). **`init`**: `_first_write` reads the effective approval
(the skeleton is unchanged -- `create_note` sorts first on both locks).
**The two example definitions** written as §5 lists; the manifests are the
other way round from the plan's item 4 (**D1749**): four definitions compile
under `project.example.yaml` (`validate` exit 0), and both new definitions
exit 5 under `project.second.example.yaml` at `start_the_task` with the new
sentence. **`docs/workflows.md`**: *Approval*, *Compensation* and *Wait*
subsections, the D1726 sentence (a note cannot be un-created), `## Approvals`
(D1718's three controls, D1720's listing, a rejection is a cancel, D1721 in
one paragraph), `compensating` among the words, the *What is not here yet*
table down to Session 34's one row. **Proofs** (`test_workflow_definition.
py`): `test_a_capability_that_requires_approval_is_refused` REPLACED by
`test_an_approval_requiring_step_must_declare_approval` (asserts the new
sentence AND that the step compiles once `approval:` is added);
`test_the_example_projects_definitions_compile` renamed `..._four_
definitions_compile` and made to assert the compiled approval, the whole
compensation block and the whole wait step; NEW `..._declared_approval_on_a_
step_that_needs_none_is_refused`, `..._profile_added_approval_is_seen`
(premise asserted first: tool `true`, capability `false`), `..._example_
project_without_the_profile_is_the_control`, `..._approval_expiry_is_bounded_
below_the_run_timeout`, `..._compensation_must_be_a_write_the_lock_compiles`,
`..._compensation_on_a_read_step_is_refused`, `..._compensation_may_not_
require_approval` (by the capability AND by a profile), `..._compensation_
takes_only_declared_arguments`, `..._compensation_may_not_reference_a_later_
step`, `test_compensation_scopes_join_the_required_scopes`, `..._wait_takes_
no_capability_and_is_bounded`, `..._wait_on_an_event_is_refused_naming_
session_thirty_four`, `..._reference_to_a_wait_step_is_refused`, `..._
skeleton_skips_a_write_a_profile_made_approval_requiring` (loads `bin/
workflow.py` by path), `test_an_undo_rows_name_can_never_be_a_step_name`
(**D1748 pinned**), `test_the_schema_admits_a_capability_step_or_a_wait_step_
and_never_both`, `test_the_session_32_definitions_are_byte_for_byte_
unchanged` (the digests read at the `1.10.0` tag, which is what both
projects installed). `test_dev_environment_cluster.py`'s install proof moved
from two definitions to four and now reads the compensation's retry, the
approval's expiry and the wait's seconds out of the INSTALLED bodies where
0035 reads them. WF-DEF-001's two node ids and two sentences moved
(**D1750**). **Battery 9/9 killed**, each `FAILED`, none `ERROR`, control
`test_the_example_projects_four_definitions_compile` PASSED in every arm,
anchors pre-flighted, restored by copy and `cmp`: the plan's (m1) D1723
restored, (m2) a read admitted as a compensation, (m3) the compensation
scopes dropped, (m4) a later reference admitted in a compensation, and
(m5) a declared approval where none is required, (m6) D1719's bound at `>`,
(m7) `wait: {event}` admitted, (m8) `init` on the capability's approval,
(m9) a compensation that requires approval. **Targeted, once: 266 passed**
(the plan's nine modules; `test_dev_environment_cluster` ran, Docker-backed).
**Rows added: D1749–D1751. NEXT FREE: D1752.** **CI:**
`6fd8f093c7aa794b7ee277762c19438a5dcf6a1f` → `contract` **success**.

### Run 5 — the plane accepts an approved call, the loop learns gates and compensation

**Read first:** `services/auth-api/app/workflow_worker.py` whole again;
`service.py:224-292` and `:485-549`; `claims.py` whole; `mcp_tools.py:547-652`
and `:1067-1110`; `mcp_authorization.py:140-230` (where the request id and the
token are put in context — the approval is read the same way);
`mcp_runtime.py:225-326`; `tests/contract/test_workflow_worker.py` whole (the
fakes `:120-160`, the AST proof, the depth refusal `:846-855`);
`tests/security/test_session9_revocation.py:60-130` (the fake repository
shape); `tests/contract/test_mcp_tools*.py` (grep `requires_approval` and
`approval_required` under `tests/` — every proof that reads the refusal runs);
rigs 33a–33c's Done.

1. **`claims.py`**: `APPROVAL_CLAIM = "apg_approval"` with a `#:` comment
   (optional, minted only on a step token, ADR 0231) and `approval_claim(
   payload) -> dict[str, str] | None` — `None` when absent; `ClaimError` unless
   it is an object with exactly `id` (a uuid string), `tool` and `key`
   (non-empty strings, `key` inside `^[\x21-\x7e]{8,255}$`). `REQUIRED_CLAIMS`
   is unchanged and `jwt_claims.sql_required_claims()` with it — the
   database's literal does not move (asserted by the existing
   `test_the_sql_literal_lists_exactly_the_required_claims_in_order`).
2. **`service.py`**: `issue(credential, *, token_use, extra_claims=None)` —
   refuses (`InvalidRequest`) an `extra_claims` key that is in
   `REQUIRED_CLAIMS`, merges the rest into the payload BEFORE
   `verify_claims`; `step_token(agent_id, *, approval_id=None)` — when given,
   `await self.repository.approval_for_token(approval_id, agent_id)` (a new
   `Repository` method over `workflow_approval_for_token` — the auth
   service's `Repository` in `repository.py`, beside `list_agent_audit`; the
   loop's `WorkflowRepository` got its own in Run 3, and the service reaches
   the database only through its own repository), zero rows →
   `AuthenticationFailed("the approval is not decided for this agent")`,
   else `extra_claims={APPROVAL_CLAIM: {"id": str(approval_id), "tool":
   row.tool, "key": row.idempotency_key}}`. `agent_token` is untouched and an
   AST proof asserts it never names `extra_claims`.
3. **The plane**: `register_write`'s closure reads the approval from the
   verified claims (the same context path that yields `current_token()` —
   `get_access_token().claims`, validated by `claims.approval_claim`, a
   `ClaimError` becoming the ordinary approval refusal, never a 500) and
   passes `approval=` to `invoke_write`. In `invoke_write`, the `if
   entry.requires_approval:` block becomes: proceed iff `approval is not None
   and approval["tool"] == tool and approval["key"] == idempotency_key and not
   dry_run`; `dry_run` with an approval → `AgentVisible(INPUT_NOT_PERMITTED,
   "an approved call is not rehearsed", NOT_IN_ALLOWLIST)`; everything else →
   the EXISTING `AgentVisible(APPROVAL_REQUIRED, …)` byte-for-byte. **The
   comment at `:583-590` is rewritten**: the refusal is still terminal for
   every caller without a matching claim; a workflow's approval gate is the
   only path that carries one (ADR 0231). `mcp_errors.py:51-55`'s sentence is
   rewritten the same way (grep the sentence — it is also in `0034:5-12`,
   which is a released migration and is NOT edited; its comment stays true of
   the release that shipped it).
4. **The loop** (`workflow_worker.py`), in the module docstring's voice, one
   new ordering stated: *read the gate before minting* —
   - `process()` begins, after the claim, with the compiled step's kind:
     **`wait`** → `state = await repository.gate_state(step_id, holder)`;
     `waited` false → `repository.park(…, reason="waiting", resume_after=
     now_utc + seconds, request_id=None)`; true → `finish(…, "succeeded",
     result=None, reason="waited", request_id=None)`. **No token is minted**
     (a counting proof).
   - A step whose compiled element carries `approval` → read `gate_state`
     FIRST: `approval` null → the ordinary path (mint without approval, call);
     on a refusal whose token is `approval_required`, if `step.dry_run` never
     got here (below), `repository.request_approval(step_id, holder,
     request_id, expires_after)` and return; `status 'approved'` → mint with
     `approval_id=` and call; `status 'expired'` (or `pending` — the claim only
     fires a pending step at its expiry) → `repository.expire_approval(…)`
     then `finish(…, "failed", reason="approval_expired", request_id=None)`.
     **In a `dry_run` run an approval step is finished `dry_run` with reason
     `approval steps are not rehearsed` and NO call** (D1722).
   - The plane serving an approval step's FIRST call (the lock moved) →
     finished `succeeded` like any other (D1714's last sentence), with a
     `log.warning` naming the step and the capability.
   - **Compensation rows** need nothing new: their compiled `step` is the
     compensation block with `kind: "write"`, so `call_arguments` adds the
     row's own key and `dry_run`, and `finish` is the replaced substrate's.
   - **D1724**: a new `tool_value(result) -> tuple[dict | None, str | None]`
     returns `result["structuredContent"]` when it is a dict, else
     `json.loads(result["content"][0]["text"])` when that is a JSON object,
     else `(None, "the plane's result carried no structured value")`; the
     step stores the value (and the reason, when there is one, in `reason`).
     **Which of the two branches the real plane takes is rig 33c's
     measurement, cited in the docstring**; the fakes' `OK_RESULT`
     (`test_workflow_worker.py:135-142`) is replaced by rig 33c's recorded
     bytes so the offline suite stops sharing the code's belief (question 6).
   - `RETRYABLE_TOKENS` unchanged; `del token` on every path, the AST proof
     extended to the approval branch's second name (`approved_token` — or
     keep ONE name `token` for both mints; say which in the Done).
5. **Rig 33g — the loop's first end-to-end gate, offline** (rig 32j's recipe:
   the built image in `auth` mode with the real loop, a cluster with 35
   migrations and the example set, a fake plane in rig 33c's measured shape
   recording every request and REFUSING `set_note_embedding` with
   `approval_required` unless the bearer's decoded claims carry
   `apg_approval` for that tool and key): enqueue `tasks-approval`, see the
   step park with a pending approval, decide it with
   `workflow_decide_approval` as superuser for a user who is not the owner,
   see the second call carry the claim and the run succeed; then a second run
   REJECTED → `compensating` → the compensation call → `cancelled`/`complete`.
   Control: a run whose approval is never decided and whose expiry is forced
   past (superuser `UPDATE … SET expires_at = now() - interval '1 s'`) →
   `failed` `approval_expired`, then compensation. **Expected to find
   something** (§7 question 2); whatever it finds is a row.

**Proofs**: `tests/contract/test_approval_claim.py` (the nine of §2
`AGT-APPROVE-002`; the plane half drives `invoke_write` with a fake
`execute_write` recording whether it was dialled; the service half drives the
real `AuthService` with a generated key and a fake repository, rig 32f's shape;
`pytestmark` before the first test); `tests/contract/test_workflow_worker.py`
gains the nine of `WF-WORK-002` over the existing fakes plus a fake
`gate_state`/`request_approval`/`expire_approval`. **Every existing proof in
both modules stays green unchanged** except the `OK_RESULT` replacement, which
the Done lists.

**Mutation battery**: (m1) the plane checks the tool and not the key →
`test_the_plane_refuses_a_claim_for_another_tool_or_key` FAILS; (m2) the plane
admits `dry_run` with a claim → `test_the_plane_refuses_an_approved_dry_run`
FAILS; (m3) `step_token` builds the claim from its ARGUMENTS instead of the
repository's row → `test_step_token_refuses_an_undecided_or_foreign_approval`
FAILS; (m4) the loop mints for a wait step → the no-token proof FAILS; (m5)
the loop requests approval in a dry run → `test_a_dry_run_never_requests_
approval` FAILS; control: `test_a_token_without_the_claim_is_refused_as_before`
and Session 32's `test_one_token_per_step_attempt_and_none_outlives_the_step`
green in every invocation.

**Targeted:** the two modules, `test_workflow_repository.py`,
`test_auth_service_shape.py` (the transport scan and `TRANSPORT_ALLOWLIST` —
no new transport, D1668/D1689), `test_auth_service_database_access.py`,
`test_jwt_claims.py`, `test_identity_registry.py`, every
`tests/contract/test_mcp_*` module that names `approval` (grep),
`test_agent_plane_contract.py`, `tests/security/test_session9_revocation.py`,
`test_acceptance_registry.py`, `test_evidence_claims.py`. Commit (`Session 33
Run 5: an approved call carries a signed claim; the loop learns approval,
wait and compensation`), push, read CI.

### Run 6 — the human surface: the scope, four admin routes, the audit filters, Studio, the four verbs

**Read first:** `schemas/capabilities.schema.json:230-285`; `src/
agentic_postgres/scope_registry.py` whole; `services/auth-api/app/scopes.py`
whole; `tests/contract/test_scope_registry.py` and `test_scope_vocabulary.py`
whole; `routes.py:300-370`, `:660-770` (the `/admin/users` handlers — the
shape the new routes copy), `:954-1066`; `strict_query.py` whole;
`openapi_docs.py` (grep `DOC_AGENT_TOKEN`, `described`, `created`, `ok`);
`models.py` (the strict request models, `extra="forbid"`); `workflow_routes.py`
whole (the translation and guard shape); `bin/studio.py:470-640`; `src/
agentic_postgres/studio.py:100-120`, `:600-800`; `services/studio/studio.js:
330-360`; `bin/workflow.py` whole; `bin/workflow.sh` whole; `bin/api.py:30-60`;
`bin/app-contract.sh:1-41`; `tests/contract/test_auth_endpoints.py:1396-1850`;
`tests/contract/test_auth_strict_query.py`; `tests/contract/test_studio_server.
py:590-630`; `tests/contract/test_studio_runtime.py:1100-1220`.

1. **The scope** (D1717): `admin_workflows:approve` into
   `$defs/administrative_scope` and `$defs/scope`; the description string of
   the administrative enum gains one sentence for it; `ADMIN_WORKFLOWS_APPROVE
   = "admin_workflows:approve"` in `scopes.py` after `ADMIN_AUDIT_READ`. The
   four pinning proofs move to the new exact sets and the two fixture lists
   gain it — **in this commit, under ADR 0232**, and the Done quotes each
   before/after set. `api_surface.reserved_resource_names()` now reserves
   `admin_workflows` — grep the example projects' surfaces for a relation of
   that name (there is none; say so).
2. **`services/auth-api/app/workflow_admin_routes.py`** (the house shape:
   `openapi_extra`, `responses`, `_guard`, `Cache-Control: no-store`), mounted
   in `auth` mode beside `workflow_routes` (`main.py:304`) and added to the
   published list (`main.py:454-465`):
   - `GET /admin/workflows/approvals?limit=N` — `authenticate`, `require_scope(
     ADMIN_WORKFLOWS_APPROVE)`, `strict_query` (`limit` 1..100, default 50) →
     `{"approvals": [...], "limit": n}`.
   - `POST /admin/workflows/runs/{run_id}/approve` and `…/reject` — body
     `WorkflowDecisionRequest {step: str}` (`extra="forbid"`, the step-name
     pattern); `authenticate`, `require_scope(ADMIN_WORKFLOWS_APPROVE)`; a
     malformed run id is the same `no_such_workflow` 404 (`workflow_routes.py:
     210-216`'s reason); `workflow_decide_approval(run, step, principal.
     user_id, 'approve'|'reject')`; `PT403 approver_is_owner` → 403
     `{"error": "approver_is_owner"}`; `PT409 approval_already_decided` → 409
     `{"error": "approval_already_decided"}`; `PT409 approval_expired` → 409
     `{"error": "approval_expired"}`; `PT404` → 404 `no_such_workflow`; 200
     `{"run_id", "step", "approval": "approved"|"rejected"}`. The messages are
     read for one word, exactly as `_translate` does (`workflow_routes.py:
     130-147`); none reaches the caller.
   - `GET /admin/workflows/runs/{run_id}` — `require_scope(ADMIN_AUDIT_READ)`;
     `workflow_provenance(run)`; `jsonable()`.
   - `errors.py` gains the three fixed documents; `models.py` the request and
     response models; `openapi_docs.py` the four descriptions.
3. **`GET /admin/audit`** (D1730, D1741): `AUDIT_QUERY_PARAMETERS` gains
   `since`, `until`, `outcome`, `denial_reason`, `cursor`; `strict_query`
   gains `as_timestamp(name, value)` (ISO-8601 with an explicit offset, never
   a naive time, never coerced) and `as_member(name, value, members)`; the
   members are the two enums' values as `routes.py` constants, bound by a
   proof to the migration's enum literals (the tree's *two enforcement points,
   one list* pattern); `cursor` is `base64url("<started_at ISO>~<uuid>")`,
   decoded and validated (a forged or truncated one → 422 *"the cursor is not
   one this endpoint issued"*); the response gains `window_counts` (from
   `count_agent_audit`) and `next_cursor` (from the last row when the page is
   full, else `null`). The stale comments at `:313` and `:1026-1031` are
   corrected (D1741). `DOC_LIST_AUDIT` is generated from the constants as
   today.
4. **Studio** (`bin/studio.py:595-634`): the forwarder accepts exactly
   `agent_id`, `owner_id`, `since`, `until`, `outcome`, `denial_reason`,
   `cursor` and still refuses anything else with 400 naming the accepted set;
   `studio.audit_view_header` adds *"… in a window holding T rows (R
   refused)"* from `window_counts`; `studio.js`'s in-view filters stay (they
   filter the fetched page) and the header shows the window counts. The three
   refusal proofs are REPLACED by stricter ones under ADR 0234:
   `test_the_audit_view_forwards_the_five_filters_and_nothing_else` (the five
   reach the fake upstream verbatim; `?color=red` is still 400);
   `test_the_audit_header_carries_the_windows_counts`; and
   `test_an_unknown_query_parameter_is_refused` keeps its node id with
   `?page=abc`.
5. **`bin/workflow.py` / `bin/workflow.sh`** — four verbs: `approvals
   [--limit N] --project-outputs FILE`; `approve --run ID --step NAME
   --confirm ID --project-outputs FILE`; `reject` (the same); `inspect --run
   ID --project-outputs FILE`. `ADMIN_ROUTES` a closed table beside `ROUTES`;
   the token from **`APG_API_TOKEN`** (`HUMAN_TOKEN_VARIABLE`, `bin/api.py:42`'s
   name — never `APG_AGENT_TOKEN` for these four, and never an argument);
   `--confirm` unequal to `--run` → exit 2 before any request (*"--confirm
   must repeat the run id; a decision is final"*); `inspect` prints the JSON
   document with `indent=2` and nothing else; exit codes 0/2/3/5 unchanged,
   5 printing the error word. `verb_usage()` gains four cases;
   `COMMANDS_WITH_VERBS` in `test_cli_contract.py` gains them.
6. **The contract and the client**: `bin/app-contract.sh --update >
   contracts/app-openapi.canonical.json` then `--check`; **`bin/apg.sh
   generate --project project.example.yaml`** (D1690) and `--check`; the
   client's version does not move unless the generator says so.

**Proofs**: `tests/contract/test_workflow_admin_routes.py` (the §2 proofs of
`WF-ADMIN-001` and the three route proofs of `WF-PROV-001`, over
`create_app("auth")` driven with `httpx.ASGITransport` as
`test_auth_endpoints.py` does, lifespan not run and the two state members set
directly — Session 32 Run 5's note — with fakes for the repository and a real
`AuthService` minting both token uses); the audit proofs in
`test_auth_endpoints.py`, `test_auth_strict_query.py`; the Studio proofs; the
four `WF-CMD-002` proofs in `test_workflow_command.py`.

**Mutation battery**: (m1) the approve route checks `ADMIN_AUDIT_READ`
instead of `ADMIN_WORKFLOWS_APPROVE` → `test_approve_and_reject_need_the_
approve_scope` FAILS; (m2) the route calls `authenticate_agent` → `test_an_
agent_token_is_refused_by_every_admin_workflow_route` FAILS; (m3)
`window_counts` computed from the filtered page → `test_the_audit_endpoint_
returns_window_counts_on_every_page` FAILS; (m4) `approve` sends without
checking `--confirm` → its proof FAILS; control: `test_the_audit_endpoint_
needs_its_own_scope_not_the_agent_roster_one` (`test_auth_endpoints.py:1501`)
in every invocation.

**Targeted:** the new route module, `test_auth_endpoints.py`,
`test_auth_strict_query.py`, `tests/security/test_session9_revocation.py`
(`:318`, the forbidden filter names — **`since`/`until`/`outcome`/
`denial_reason`/`cursor` must not name a principal; run it**),
`test_scope_registry.py`, `test_scope_vocabulary.py`, `test_studio_core.py`,
`test_studio_server.py`, `test_studio_runtime.py`, `test_workflow_command.py`,
`test_cli_contract.py`, `test_app_contract_aggregate.py`,
`test_printed_commands.py`, `test_client_typescript.py`,
`test_generate_command.py`, `test_studio_command.py`, `test_client_ir.py`,
`test_auth_service_shape.py`, `test_container_selectors.py`,
`test_acceptance_registry.py`, `test_evidence_claims.py`. Commit (`Session 33
Run 6: the human surface -- admin_workflows:approve, four admin routes, the
audit filters, Studio, four verbs`), push, read CI.

### Run 7 — the readers and the pages: the doctor, the drill, the operator guide

**Read first:** `bin/doctor.py:743-873`; `src/agentic_postgres/diagnosis.py:
583-660`; `bin/restore-test.py:490-515`; `src/agentic_postgres/restore_drill.
py:670-700`; `tests/contract/test_doctor_readings.py` (the workflow proofs);
`tests/contract/test_doctor_redaction.py`; `tests/contract/test_restore_test_
command.py` (the `workflow_runs` proofs); `docs/operator-guide.md:1276-1387`;
`docs/studio.md` (grep `D1248`, `:159`); `docs/operator-guide.md:419` (the
audit sentence); `docs/README.md:55-70`.

1. **The doctor's `workflow` check** reads the two new counts from
   `workflow_counts()` (Run 3) and prints them: *"… approvals pending N
   (oldest Ts)"*, no threshold; `_by_status` accepts `compensating` without a
   code change (D1693: a SHAPE) — **asserted**, not assumed; a document
   without the two keys (a 1.10.0 cluster) is reported as *"approvals: not
   read (the substrate predates 1.11.0)"* rather than zero (ADR 0195).
2. **The drill's `workflow_runs` member** gains `approvals: {by_status}` read
   from the drill, or `null` with a reason when the table is absent (a drill
   of a pre-0035 backup) — the member's shape is `restore_drill.
   evidence_document`'s by name (D1691: both files move).
3. **`docs/operator-guide.md` §17** gains `### Approvals` (granting the scope
   by `PATCH /admin/users` with role and scopes together — the literal
   command; listing, approving and rejecting with `apg workflow`; the owner
   rule; what the approver sees; the expiry; D1721's residual), `###
   Compensation` (what `compensating`, `complete` and `incomplete` mean and
   what an operator does about `incomplete`: read `inspect`, act by hand, the
   product does not retry an undo beyond its declared retry) and `###
   Provenance` (`apg workflow inspect`, the auditor's scope, reading a revoked
   agent's run — D1704). The audit sentence at `:419` and `docs/studio.md:159`
   are rewritten for the filters and the window counts.
4. **`docs/README.md:63`**'s row for workflows.md adds *approvals,
   compensation, `wait` and `inspect`*.

**Proofs**: `test_doctor_readings.py::test_the_workflow_check_reports_pending_
approvals_with_no_threshold`, `::test_a_pre_gate_substrate_is_reported_not_
zeroed`; `test_doctor_redaction.py` over the new line;
`test_restore_test_command.py::test_the_drill_evidence_carries_approvals_or_
null_with_a_reason`. These three join **`WF-GATE-001`** in Run 8 (a reading of
the gate's state), not a new requirement.

**Mutation battery**: (m1) the doctor prints `0` when the keys are absent →
`test_a_pre_gate_substrate_is_reported_not_zeroed` FAILS; (m2) the drill
member drops the null arm's reason → its proof FAILS; control:
`test_doctor_with_no_verb_runs_the_twelve_checks_unchanged`.

**Targeted:** `test_doctor_readings.py`, `test_doctor_redaction.py`,
`test_diagnosis.py`, `test_restore_test_command.py`, `test_fleet_command.py`
(grep: `bin/fleet.py` runs the doctor), `test_documentation_index.py`,
`test_session12_documented_path.py`, `test_acceptance_registry.py`. Commit
(`Session 33 Run 7: the readers -- pending approvals in the doctor, the drill
member, the operator guide`), push, read CI.

### Run 8 — the bump, the registry, the gate, and the trip's proofs

**Read first:** `src/agentic_postgres/__init__.py:555-623` (32's paragraph
and `CURRENT_SESSION`); `bin/session-32-check.sh` whole — **yes, whole: 1,621
lines, and D1199 says the last ones are the least executed**;
`tests/contract/test_session_thirty_two_gate_modes.py` whole; `bin/upgrade.py:
100-140` and `:380-420`; `docs/upgrade-guide.md:72-106`; `README.md:1-40`;
`tests/deployment/test_session32_workflows.py` whole (the shape the trip's
proofs copy — its fixtures, `_until`, `_audit`, its teardown discipline, its
revocation race docstring); `tests/deployment/conftest.py:1230-1400` (the
login helpers).

1. **The registry**: the `WF` paragraph gains its Session 33 sentence (§2);
   the fourteen entries of §2 with node ids read from `pytest --collect-only
   -q` over every module the runs touched (D1236), plus the moved entries
   (AGT-AUDIT-002's sentence, STU-AUDIT-001's description and node ids,
   AGT-APPROVE-001's description, WF-INSTALL-001's two D1705 node ids, the
   usage requirement's wording node id); `evidence_claims.py`'s fourteen
   claims, ten in `OFFLINE_CLAIMS`, fourteen rows in `CLAIM_INTRODUCED_IN`;
   `THR-APPROVAL`'s test-node cell rewritten from the collected names;
   `docs/product-contract.md:230` and `docs/acceptance-matrix.md:269`'s
   AGT-APPROVE-001 sentence (D1741); `bin/render-acceptance-matrix.py
   --write`; `bin/render-config.py --bounds-doc --write`.
2. **`CURRENT_SESSION = 33`**; the Session 33 paragraph in `__init__.py` in
   32's shape: what moved (this plan's header inventory), the `upgrade plan`
   reading **with the declared classes** and its verdict (item 6), the MINOR
   argument, `OFFLINE_CLAIMS` 32 → 42 and `CLAIMS` 158 → 172 *counted from the
   tuples*, and **the pricing paragraph LAST** (D1629). `VERSION` →
   `1.11.0`; `README.md:7`; `docs/upgrade-guide.md`'s release table gains the
   `1.11.0` row (applies migration 0035; adds a scope an existing
   administrator must be GRANTED; a rollback by image is not possible past
   0035 — ADR 0162 §3); **every `--session 32` / `--through-session 32`
   literal on the documented path moved** (grep them — sixteen last time,
   D678/D1484); `bin/apg.sh generate --project project.example.yaml` and
   `--check` (D1238).
3. **The trip's proofs — `tests/deployment/test_session33_gates.py`**,
   `pytestmark = [pytest.mark.p0, pytest.mark.live_host,
   pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS",
   "APG_PROJECT_B_OUTPUTS")]` before the first test. Helpers COPIED from
   `test_session32_workflows.py` (`sse_result` `:125`, `_create_subject`
   `:144-165`, `ProbeAgent` `:168`, `_create_agent` `:204-226`, `_enqueue`
   `:330`, `_status` `:355`, `_until` `:361`, `_terminal` `:386`, `_audit`
   `:390`) with `TERMINAL` extended by nothing (`compensating` is NOT
   terminal — a proof polls through it). A `SWEEP = secrets.token_hex(4)`
   canary in every title. Module fixtures, each tearing down in `finally`:
   - `gate_owner` — `authenticated`, scopes `notes:read, notes:write,
     tasks:read, tasks:write, note_embeddings:read, note_embeddings:write`
     (**read beta's deployed lock's `vocabulary.data` first**, from
     `list_resources` or the rendered lock, and fail with a message naming the
     missing scope if `note_embeddings:*` is not in it), a random password
     never recorded; left at teardown (D1700) with its rows deleted.
   - `gate_agents` — three `agent_writer` agents owned by `gate_owner`
     (`approve`, `reject`, `revocable`) plus one owned by the APPROVER
     (`owned_by_approver`), scopes `meta:read` + the owner's six; revoked at
     teardown.
   - `approver` — `project_admin`, scopes `admin_audit:read,
     admin_workflows:approve`, logged in over HTTP (`beta_admin`'s shape,
     `:289-322`); deleted at teardown **after** its approvals are read (an
     approval's `decided_by` REFERENCES the user — if the delete is refused,
     leave the user and say so in the Done: this is the D1700 shape for
     humans, and the retention story owes it).
   - `scopeless_admin` — `project_admin`, `admin_agents:read,
     admin_agents:write`, logged in; revokes `revocable`; deleted at teardown.
   - `tasks_and_notes` — per run, a task (`pending`) and a note owned by the
     run's agent's OWNER, inserted with `psql` as the tree's proofs do, titles
     carrying the canary; deleted at teardown (the embedding cascades).
   - `embedding` — the text literal of 768 zeros (rig 33b's measured shape).
   - `approved_run` — `tasks-approval` for `approve`: poll to step 2
     `parked` with an approval `pending` (≤ 60 s); read the audit rows for the
     agent (ONE `refused`/`approval_required` for `set_note_embedding`); POST
     approve with the AGENT's token → 401; with `scopeless_admin` → 403 and
     the approval still `pending` (a `psql` read); with `approver` → 200; poll
     to `succeeded` (≤ 120 s).
   - `owner_rule_run` — `tasks-approval` for `owned_by_approver`: poll to
     parked; `approver` approves → 403 `approver_is_owner`; the proof cancels
     it with the agent's own cancel route; poll to `cancelled` (compensation
     `complete` — step 1 succeeded).
   - `rejected_run` — `tasks-approval` for `reject`: parked; `approver`
     rejects → 200; poll through `compensating` to `cancelled`, `compensation_
     outcome complete`, the task back in `pending`, no embedding row.
   - `compensated_run` — `tasks-compensate` for `approve` (a second task)
     with `missing_task_id` a fresh `uuid4()`: poll to `failed`
     (`row_not_found`), compensation `complete`, `pause` finished `waited`,
     the task `pending`.
   - `revoked_run` (D1704) — `tasks-approval` for `revocable`: parked;
     `scopeless_admin` revokes the agent (`PATCH /admin/agents/{id}`
     `{"status": "revoked"}`, `test_session32_workflows.py:973-997`'s shape);
     `approver` approves (the decide function does not consult the agent) →
     the next claim's `step_token` refuses → poll with `psql` (the agent can
     no longer read its own run) to `stopped`/`agent_not_active`. **This is
     deterministic, unlike Session 32's revocation race**: the run cannot move
     past the gate until the approval, and the revocation lands first.

   The proofs (§2): `WF-APPROVE-001` (six — the alpha control creates an
   alpha `project_admin` holding the scope in SQL, logs in, and reads an EMPTY
   approvals list), `WF-COMP-002` (two), `WF-PROV-002` (two — both run
   **`bin/workflow.sh inspect --run ID --project-outputs <beta>`** with
   `APG_API_TOKEN` set to the approver's token, the product's own command,
   D1114: the approved run's approval step has attempt 1 `approval_requested`
   joined to ONE `refused`/`approval_required` audit row and attempt 2
   `finished` joined to a `committed` row; `approvals[0].username` is the
   approver's; `profile.value` is `null` with its reason; the revoked run
   reads `stopped`), `AGT-AUDIT-004` (two — the cursor walk over beta's WHOLE
   audit to a fixed `until` with `limit 500`, ids distinct and equal in number
   to `window_counts.total`; and `?agent_id=<approve>&outcome=committed` whose
   `window_counts.by_outcome.refused >= 1`).
4. **`pytest --setup-plan`** for `test_session33_gates.py` with `APG_LIVE_HOST=1
   APG_PROJECT_A_OUTPUTS=<the op-owned copy> APG_PROJECT_B_OUTPUTS=<…>` set
   (D671, D676) — and with none set (every proof SKIP, 0 errors); both outputs
   kept in the scratchpad and counted in the Done.
5. **`bin/session-33-check.sh`** derived from 32's by `sed` with every
   substitution count-asserted (`grep -c` before and after: `SESSION=32` →
   `33`, `session-32` → `session-33`, `thirty_two` → `thirty_three`, the
   evidence prefix, the ADR range in the header, the offline claim sentence's
   counts *eight*→*ten* and *thirty-two*→*forty-two*), the header and usage
   rewritten whole and read line by line (D1488); `run_suite "p0 and not
   future and not live_host and not external"` kept verbatim (D1242); **no
   flag added or removed** — `diff <(grep -o -- '--[a-z-]*'
   bin/session-32-check.sh | sort -u) <(grep -o -- '--[a-z-]*'
   bin/session-33-check.sh | sort -u)` is EMPTY and pasted in the Done;
   `SHELL_COMMANDS` gains it; `chmod 755`; `git add`;
   `tests/contract/test_session_thirty_three_gate_modes.py` from thirty-two's
   with the no-gap test (`:244`) carried and its literal moved, and
   `test_exactly_this_sessions_declared_claims_are_offline` naming the ten.
6. **`upgrade plan` offline** (D1624's recipe): the installed side from a
   worktree at `275a19e`, the candidate a `tar`-piped copy of the working tree
   at `/tmp/apg-candidate` with `.generated/` excluded, both rendered as
   `project.example.yaml`; `bin/upgrade.sh plan … --json --also
   migration_added --also api_operation_added` → expect `bump minor`,
   `requires minor`, verdict `ok`; **list every leaf in the Done**
   (`template_version` 1.10.0 → 1.11.0 and `migrations.release_lock_sha256`
   expected; anything else is read and explained). Then the same without the
   flags → `requires patch`, recorded.
7. **The gates**: `bin/session-01-check.sh` once on the clean tree (commit,
   gate, repair, commit, gate again; every first-run failure a row), run
   DETACHED with its exit code written from inside (CLAUDE.md §1);
   `bin/session-33-check.sh --mode offline` → `evidence/session-33-offline.
   json` with the ten new offline claims plus the 32 inherited, every one
   `passed` (the count read from the file). Push; CI by full SHA.

Commit (`Session 33 Run 8: the bump to 1.11.0, the registry, the gate, the
trip's proofs`), push, read CI. **Nothing goes to the host until this commit's
CI is green by full SHA.**

### Run 9 — the trip: both projects redeploy with 0035, the first approval by a person-shaped principal, one sweep, the tag

**Before the day** (agent, offline): read Session 32's Run 8 and Sheets B1–B6
(`session-32-implementation-plan.md` §5 Run 8 and the appendix) and
`docs/operator-guide.md` §12 (D977: *if something goes wrong*); stage the host
scripts under `/home/op` derived from `s32-r8-{checkout,renders,sentinel,b1,
after,readings,cleanup}.sh` and `s32-r8b-{gate,launch}.sh` **by named
substitution with every count asserted** (D1482, D1630) — `s32-r8` →
`s33-r9`, `32` → `33` only where it is a session literal, the bundle's sha —
**and diff each derived script against its parent: every `--flag` in, every
`--flag` out** (D1133; fourteen flags in the gate script, fourteen out); the
external script in WSL `~/s33r9/s33-r9-external.sh` derived from
`~/s32r8/s32-r8-external.sh` WITH D1640's `ssh-agent` block; copy every
derived script to the scratchpad (WSL `/tmp` dies on `wsl --shutdown`); CI
green on Run 8's commit by full SHA; **WSL's outbound TCP probed with a timed
`/dev/tcp` connect read inside a script** (CLAUDE.md §1 — a Windows reboot
early if it is dead); the two op-owned document copies' `source_commit` read.

**The op side, run by the agent over SSH** (`ssh -i ~/.ssh/agentic_postgres_
ed25519 op@62.238.99.122 'bash -s' < /tmp/x.sh`): `git bundle create
/tmp/apg-<sha>.bundle <prev>..main` locally, `scp`, `git fetch` the bundle on
the host, `git rev-parse FETCH_HEAD` equal to Run 8's sha, `git checkout
<sha>`, `uv sync` (PATH exported in the script), the two projects rendered
`--render-only` as `op`, `bin/session-33-check.sh --mode offline` NOT run on
the host (D1375 — the workstation's offline half is merged), `pytest
--setup-plan` for the new live module with the variables set, pointing at the
op-owned copies.

**The operator's sheets are in the appendix: C1 → C6, one outcome each, each
read by the agent before the next is issued (D1510).** Every `sudo` line has
nothing after it — no pipe, no redirect, no `$(`, no `&` (D1505); a transcript
comes from `script(1)`, and the agent reads it over SSH as `op`.

**While the sweep runs** (Sheet C5), the agent — as `op`, no sudo — samples
beta's `auth` container's `memory.current` every 10 s into
`/home/op/s33-r9-auth-memory.txt` with a timestamp per line, resolving the
container afresh each minute through `/proc/<pid>/cgroup` + `/proc/<pid>/
mountinfo` (CLAUDE.md §2; every sweep recreates the services early, D1711).
After the sweep the samples are matched against the JUnit timestamps of
`test_a_second_user_approves_and_the_run_completes_once` and
`test_a_rejection_cancels_the_run_and_compensates`.

**Then, from the workstation:** `bin/session-33-check.sh --mode external`
through `~/s33r9/s33-r9-external.sh` (ephemeral `ssh-agent`,
`--ssh-destination op@62.238.99.122`, D466); fetch `evidence/session-33-
host.json` from the host (`scp` as `op`); `write-session-evidence` merges the
three halves → `evidence/session-33.json`, exit 5 for the expected reasons
only (§7) — **every half must name Run 8's deployed commit** (Session 29's
rule; D1641's method if an instrument had to move, stated in the tag).
`release-reading --ref <deployed sha>`; `git tag -a 1.11.0 <deployed sha>
-F /tmp/tag-msg.txt`; push the tag.

**If something goes wrong** (read before the day): 0035 fails at step 6 on
alpha → **STOP, never amend it** (D912); read the ledger through the doctor's
`migrations` check (and, for the first time, `migrate.sh status`'s own lines —
D1707's repair), a fix-forward 0036 is a new run and a new deploy. Admission
refuses a redeploy of alpha or beta → STOP before the deploy (the arithmetic
or the declaration is wrong; nothing here moved a `mem_limit`). A live proof
fails because beta's lock lacks `note_embeddings:*` for an `agent_writer` →
the fixture's message names it; the proof is wrong, not the product — a `-k`
iteration after the repair, never a second sweep for a fixture (one sweep per
trip; a second only for a defect). The approver cannot be deleted at teardown
(FK from `workflow_approval.decided_by`) → expected, written down, not a
failure. `auth` does not come back after a deploy → `docker start`
(ADR 0193's fallback), a row, and the sweep waits for `doctor` 12 ok.

**Done** records: both deploys' step 0 lines, step 6's migrator line AND the
ledger (35 / 35 + 2), step 6d's lines (alpha *no set*, beta four installs),
`migrate.sh status`'s printed `[X]` lines (D1707 closed on production), the
doctor's `workflow` line before and after (approvals pending 0 → 0), the
sweep's JUnit counts, every new claim's status, the merged document's totals,
the memory samples and which fell inside a run proof's window, the probe
agents and humans left on beta, the tag and its message.

### Run 10 — the close

**Not documentation only** (D1644): `src/agentic_postgres/capacity.py`
gains a `MACHINE` `Measurement` for beta's `auth` under a run from Run 9's
samples **only for samples inside a run proof's window** (D1711's rule — a
sample outside one is recorded as idle, never relabelled), and
`capacity.UNMEASURED`'s D1711 row is removed only if such a sample exists;
`bin/render-capacity-envelope.py --write`; ADR 0226 gains an *Amendment,
Session 33* with the figure against its 96 MiB under-load criterion. So this
run commits, runs `bin/session-01-check.sh` once (detached), pushes and reads
CI.

Then the records: this plan's header rewritten (COMPLETE, the dates, the rows
each run added, NEXT FREE); **`docs/scope-closure.md` §26** — what 33 closed
(D1521's second half as far as the proofs reach, D1248, D1704, D1707, D1712,
D1705, D1740, D1741, THR-APPROVAL), what it left (D1721's database half,
D1722's example-project dry-run branch, D1547, D1700 now for humans too,
D1642, D1581/D1713, approvals longer than an hour, the edge's unbounded
containers), and what Session 34 inherits (the `wait` step's `event` refused
by name; `workflow_gate_state` as the one gate read; the compensation
mechanism an outbound delivery may reuse; the approval claim as the pattern
for any other signed, single-write authority; `admin_workflows:approve` as the
precedent for a connector's administrative scope); `docs/plans/stage-4-
plan.md`'s Status block (`CURRENT_SESSION 33`, 1.11.0, the evidence totals,
NEXT FREE); CLAUDE.md §2/§8/§9 in the launch folder rewritten compactly
(**copy it to the scratchpad first** — it is not in git) and the project
memory updated. Documentation commit(s) after the code commit: push, no CI
read.

---

## 7. Evidence and claims

Unchanged rules (ADR 0163, 0202; D1237; D1543). **Fourteen claims land with
the constant** (D690): ten declared offline — each a property of a checkout (a
migration under a real cluster the gate requires Docker for, a compiler over
committed locks, a loop and a plane over fakes whose bytes were measured, routes
over `create_app("auth")`, a command's closed tables, a reader over canned
inputs, a verb over a fake `compose_run`) — and four host, undeclared, first
executed on the trip. **Session 33 is the session whose second principal is a
PERSON-shaped identity**, and its claims say so: `workflow_approval_live` is
proved by an approval a second user makes over HTTP, never by a row written as
superuser.

| Claim | Mode | Moves on |
|---|---|---|
| `workflow_gates`, `workflow_compensation`, `workflow_definition_gates`, `workflow_worker_gates`, `approval_claim`, `audit_filters`, `workflow_provenance`, `workflow_admin`, `workflow_command_human`, `migrate_status_ledger` | offline | Run 8's gate |
| `workflow_approval_live`, `workflow_compensation_live`, `workflow_provenance_live`, `audit_filters_live` | host | Run 9's sweep — their proofs' **first execution anywhere** |
| `audit_boundary_reported` (AGT-AUDIT-002) | host | Run 9 — re-run because the reader's arity moved (stage plan §7, D942); its live proof `test_session24_studio.py::test_the_deployed_audit_read_carries_the_boundary_of_a_real_refusal` goes through Studio's widened forwarder |
| every Session 32 claim, `workflow_resume` and `workflow_revocation` included | host | Run 9 — **the replaced claim, finish and park functions are under them**, so their passing again is part of this session's evidence, not a formality |
| `deployment_convergence` | host | Run 9, `--redeploy-before-file` declared |
| the rotation trio, `replacement_host_restore`, `port_allocation` | — | `not_run`, unchanged; `documented_path` `failed` by decision |

**Expected merged document**: 172 claims — 166 passed, 5 not_run, 1 failed —
if every new claim passes. Any other figure is read before the tag.

---

## 8. Security invariants this session touches

| Invariant | Where 33 puts it at risk | Control |
|---|---|---|
| **A second principal holds nothing an agent identity does not hold** (stage plan §8, ADR 0217) | The approver | The approver can DECIDE, never act: no route lets a human's token call a tool; the approved call is still the AGENT's, minted per step with the agent's stored scopes, under the plane's scope check, audit, budget and idempotency claim |
| **Approval may not be granted by the agent that requested it** (stage plan §5) | The four admin routes | `authenticate` refuses an agent token (401, proved on every route); the owner is refused `approver_is_owner`; the scope is `project_admin`-only by ceiling |
| **A step is a tool call under the same scope check** | Compensation | A compensation is a compiled lock write, its scopes in `required_scopes` so `enqueue` checks the agent's STORED scopes; it is minted and called exactly like a forward step; nothing widens a profile |
| **An approval cannot be forged or replayed** (`THR-APPROVAL`) | The claim | Only `auth` signs; `step_token` reads the decision itself; the claim binds the tool and the key; a key's replay is re-read (ADR 0181); `approval_already_decided`; `approval_expired` |
| PostgreSQL is the final authorization authority | Approval | **Stated, not claimed**: approval is the governed path's control and the SQL grant is the database's (D1721, measured by rig 33b, priced in §10) |
| A revoked token stops on its next request, locally | An approved run of a revoked agent | `step_token` refuses a revoked agent even with an approval in hand (`revoked_run`, deterministic) |
| An unauditable write does not happen | The approved call | The plane's order is unchanged; the approval branch sits where the refusal sat, after `bounded()` opened the record |
| An agent record carries no URL, key, token or caller value | Provenance; the approvals listing; the audit filters | Provenance never returns `parameters`; the listing returns no argument value; `window_counts` are integers; `test_doctor_redaction` over the new doctor line |
| A human cannot run SQL through a product surface | `bin/workflow.sh`'s four verbs; the routes | The command holds no SQL (the existing proof); every route calls a definer function with parameters |
| Projects share no project-scoped value | Approvals | Rows in each project's own database; alpha lists none (a live proof) |
| The MCP runtime holds no credential | The plane reads a claim | The claim is inside the bearer the plane already verifies; `FORBIDDEN_VARIABLES` unchanged and its guards run |
| A report may not substitute an answer for a failure to determine one (ADR 0195) | `inspect`, the doctor's new line, the drill member, the stored result | `profile` absent with a reason; a pre-1.11.0 substrate reported, not zeroed; `null` with a reason; *no structured value* recorded rather than guessed |
| No summarisation that hides denials (D1248) | The audit filters | `window_counts` on every page, independent of the outcome filter and the cursor |
| There is no public Postgres endpoint (ADR 0216) | Nothing here touches a port | The routes hang off `routes.app`'s existing router |
| `--render-only` keeps working with no host and no root | Step 6d installs four definitions on beta | Not reached by a render; the gate's step 2 renders four fixtures |
| The deploy, the sweep and the tag land on one commit (D1425) | Run 9 | The sheets' order; D1641's method if an instrument moves |
| Never grant `op` the docker group | The memory sampling | `memory.current` is readable by `op` (D765); the doctor is root |

---

## 9. Stop conditions

- **Rig 33a**: PostgREST or the pre-request hook REFUSES a token carrying an
  extra claim, or the plane's verifier drops it: stop; D1715 and ADR 0231 are
  rewritten (the alternative is the plane asking the database, which moves
  the `api` contract — the operator's decision) before Run 5.
- **Rig 33b**: the direct PostgREST call is refused by something other than a
  missing grant: rewrite D1721 to say what refused it, then continue. If the
  operator reads D1721 and wants the database half built in THIS session: stop
  and re-plan — it moves the example project's SQL, the project lint's
  allowlist and a release function.
- **Rig 33c**: the real plane's result carries neither `structuredContent`
  nor a JSON `content[0].text`: D1724's rule stores `null` with a reason for
  every step; compensation arguments may then reference only the run's input,
  the compiler says so, and a row records it.
- **Rig 33d**: the keyset with the id tie-break does NOT return every row once
  over tied timestamps: stop; the cursor design is wrong and 0035's reader is
  not written.
- **Rig 33e**: `ADD VALUE` fails inside dbmate's transaction on 18.4: stop;
  the `compensating` status becomes a column (`compensation_outcome
  'running'`) and ADR 0233 says so before Run 3.
- `test_database_function_signatures.py` cannot model the reader's re-creation
  at a new arity under the same name: stop and ask — the alternative is a
  NEW name and the old reader dropped, which changes AGT-AUDIT-001/002's
  vocabulary.
- A `CREATE OR REPLACE` in 0035 would need a DIFFERENT signature or return
  type for a 0034 function (other than the audit reader): stop; that is a
  `DROP`, and every grant and caller of a Session 32 function moves.
- Run 5's rig 33g fails for a reason in the PLANE rather than the loop: stop;
  the plane is presumed right; a row.
- The plane's approval branch cannot be written without changing the refusal
  text or its audit for a call WITHOUT a claim: stop — AGT-APPROVE-001's
  proofs are the contract.
- Run 8's `upgrade plan` prices `1.11.0` at **major** with the declared
  classes, or names an operator-manifest invalidation: stop; a row; the
  operator's decision.
- A passing test would be weakened — including any scope-set equality (it
  becomes a larger equality, never a subset check), `test_the_sql_literal_
  lists_exactly_the_required_claims_in_order`, AGT-APPROVE-001's refusal
  proofs, the unknown-parameter proof, the twelve-check proof, `BUDGET_
  CLAIMANTS`'s AST guard, the depth refusal at `test_workflow_worker.py:
  846-855`, or `test_one_token_per_step_attempt_and_none_outlives_the_step`.
- A step, a compensation or an approval would invoke anything that is not a
  tool the project's lock compiles; the approver's token would be used to call
  a tool; the worker would cache a token across steps or mint one for a wait
  (stage plan §9).
- A port, a route to a store, a non-loopback bind, a notification channel, or
  a second verifier, for any reason (ADR 0216, stage plan §5).
- Admission would refuse alpha's or beta's OWN redeploy: stop before the
  deploy.
- Migration 0035 fails on alpha at step 6: stop; **never amend it** (D912);
  the ledger is read; a fix-forward 0036 is a new run and a new deploy.
- The sweep's new host claims read `not_run`: `skipped_node_ids` first; a
  missing gate variable is the gate's defect; never re-run the deploy.
- CI red on a code commit: stop and read the failed job's log by id; a
  cancelled run is not a failed one (D1059); re-run only the module that
  failed, locally.
- WSL has lost outbound TCP on trip day: CLAUDE.md §1; a Windows reboot early.

---

## 10. Open items this session carries and creates

**Carried in, untouched, each still true:** D1045; `replacement_host_restore`
(D1028); D1375; the 21 unclaimed requirements; D976, D688, D771, D340, D466,
D540, D942, D1203, D1205, D1211; the Infisical control-plane identity's org
admin; `process-max` 1 (D593); `documented_path` failed until a person walks it
(35); the three rotations Session 30 did not perform, and the retired JWKs on
the host unread by any sweep; the mirror's upstream flake (D1546); `apg-diag`'s
standing account (D1528) and its allowlist (D380); ADR 0162's missing row for
an option (D1561); **D1642** (a kit naming the checkout's commit — `dr-kit.py`
is not touched here); **D1547** (`delete_note` — this session moves the `app`
contract, not the `api` one, and compensation for `create_note` is therefore
impossible and said to be, D1726); **D1581/D1713** (this deploy moves the
image, so it observes nothing about a generation-only recreate); the edge's
unbounded `traefik` and `docker-socket-proxy` and its missing `pids_limit`/
`cpus` (35); the three unbounded services (pgbouncer, postgrest, docs); the
noisy-neighbour measurement (35); the out-of-order 1.9.0/1.8.0 rows in the
upgrade guide's table (`:97-98`).

**Created or left here:**

| Item | Note |
|---|---|
| **Approval is enforced by the plane, not the database** (D1721) | Priced: a release-owned `api.require_approval(p_tool text)` (SECURITY DEFINER, reading `request.jwt.claims -> 'apg_approval'` and matching an approved `workflow_approval` row for the calling agent, the tool and the request's `Idempotency-Key` header), called first by every gated project RPC — one release migration, one project migration per gated function, a lint rule that a gated capability's function calls it, and a harness case. Not built; the operator decides whether Session 34 or 35 takes it. |
| **The example project's `set_note_embedding` has no dry-run branch** (D1722) | Its capability says `supports_dry_run: true`. Two belts keep a rehearsal from reaching it; the SQL is wrong for whoever next moves that project's set. A project function cannot use the release's dry-run helper while the lint forbids `app_private` in a project set — measure before promising a repair. |
| **An approval cannot wait longer than its run's timeout (≤ 3600 s)** (D1719) | Widening `workflow_run.timeout_seconds`' CHECK is a migration and a compiler bound; priced when an operator needs an approval that outlives an hour. |
| **The approver sees no argument values** (D1720) | By decision. A reviewed per-capability `approval.show: [arg]` allowlist is the shape if a later session needs one, and it would have to agree with `audit.redact`. |
| **A human approver cannot be deleted while an approval names them** (D1700's shape, now for humans) | `workflow_approval.decided_by` REFERENCES `users`. The retention story for runs is now also a retention story for decisions. |
| **Compensation is only as good as the lock's inverses** (D1726) | `update_task_status` alone in beta's lock. `create_note` has none until `delete_note` exists (D1547). |
| **`wait` waits on a time only** (D1727) | `wait: {event}` is refused naming Session 34, which adds the event that resumes it — through `workflow_gate_state`, the one gate read. |
| **No per-call profile record** (D1729) | Provenance reports it absent with a reason. A profile name in the audit is an audit schema move nobody has asked for. |
| **The workflow harness cases are proofs at their enforcers** (D1732) | If a later session wants them in the evaluation report, `coverage` and `render_report` must learn a non-capability subject first. |
| **D1711's figure is taken only if a sample falls inside a run proof** (D1739) | If none does, the row stays in `capacity.UNMEASURED` for a third trip, and the reason is the sweep's own shape. |

---

## Appendix — what to consult, how a run is executed here, the rigs, and the sheets

**Consult, in this order:** this plan's §1 and §5. The stage plan's §5
*Session 33*, §8, §9, §11. `docs/plans/session-32-implementation-plan.md` §1
(D1668–D1713 — what executing 32 found), §5 Runs 3, 5, 7 and 8, §10, and its
Sheets B1–B6. ADR **0195** before any reader; **0135** (the definer-function
grant shape) and **0142** (the audit has one reader and it is its own scope);
**0160** (the request id flows outward); **0175** (the arity guard); **0178**
(a denial names its boundary); **0179** (approval as a declaration and a named
refusal — what 33 extends); **0181/0182** (the key claimed in the write's
transaction; a dry-run rolled back); **0193** (a signal to the process, never
`docker kill`); **0200** (the vocabulary in the lock); **0205** (Studio);
**0213** (a reading with no threshold); **0217** (a second principal is a scope
set the existing verifier checks); **0218** (`container_exec`); **0093** (a
`bin/` command imports only `agentic_postgres` and `yaml`); **0114/0229** (one
token use per route set); **0226–0229** (the substrate and the loop).

**How a run is executed here** (CLAUDE.md §1 and §5, the parts that bite): the
Bash tool is Git Bash; every WSL command is `wsl bash -lc "cd
~/projects/agentic-postgres && . .venv/bin/activate && …"`; anything with a
loop, a nested quote or a `$` goes in a script file written with the Write
tool to `\\wsl$\Ubuntu\tmp\` and run with its output redirected to a file that
is `rm`'d first; **never pipe a gate into `tail`**; a long gate runs detached
with its exit code written from inside; `chmod 755 bin/*.sh bin/*.py
deploy.sh` before every `git add`; commit messages from a file with `-F`;
`PYTHONDONTWRITEBYTECODE=1` and `__pycache__` cleared before a battery; restore
by copy and `cmp`, never `git checkout --`; every anchor pre-flighted to match
exactly once and a miss fatal; a mutation is evidence only beside a control it
cannot reach, in the same invocation; assert HOW each mutation failed;
`--setup-plan` with the variables SET before a trip. **Any Python that imports
`agentic_postgres` outside pytest needs `PYTHONPATH=src`.** **Every
`service_source.load(...)` proof reads the service's module from
`services/auth-api/app/`, not `src/`** — the plane, the loop and the routes
live there. **A `sudo` line on any sheet has nothing after it**, and every
sheet is grepped for `|`, `>`, `$(` and `&` on every `sudo` product line before
it is handed over (D1505).

**The rigs, summarised** (Run 1, plus 33g in Run 5; each a script, each with a
control, each naming its image by digest):

| Rig | Subject | Control | Owes |
|---|---|---|---|
| 33a | an extra claim through `verify_claims`, the plane's verifier, PostgREST and the hook | the same token without it; a claim signed by a second key (401) | D1715's premise |
| 33b | a direct PostgREST call of the gated RPC; its dry-run header | the same call through the plane (`approval_required`) | D1721, D1722 measured; the vector literal's shape |
| 33c | the real plane's `result` for a write | a read's `result` beside it | D1724's stored value; the fake's bytes |
| 33d | a keyset cursor over 1,000 tied rows | unfiltered count; the tie-break removed | 0035's reader |
| 33e | `ADD VALUE` inside dbmate's transaction | the value used in a DEFAULT in the same transaction | 0035's enum step |
| 33g | the loop's first end-to-end approval, rejection and expiry | an undecided approval forced past its expiry | Run 5's integration, before a host |

### Sheet C1 — the reads (all `sudo`; the agent writes each reading down from the transcript)

The agent stages `/home/op/s33-r9-c1.sh` (derived from `s32-r8-b1.sh`: every
child with stdin `/dev/null`, output tee'd to an op-readable file) containing:
`bin/upgrade.sh check --project alpha-dev` and `beta-dev` → `verdict OK`;
`bin/doctor.sh --project alpha-dev` and `beta-dev` → **12 ok**; `bin/fleet.sh`
→ 2 projects; `bin/backup.sh --outputs /etc/agentic-postgres/projects/<key>/
outputs.json info` for both → a full exists; `bin/upgrade.sh plan --project
<key> --candidate /home/op/agentic-postgres/.generated/<key>/outputs.json
--json --also migration_added --also api_operation_added` for both → `bump
minor`, `requires minor`, `OK`; `bin/dr-kit.sh export … --output
/home/op/kit-<date>-pre` (the exact line from `--help`, printed on the sheet by
the agent). The operator runs, at a terminal, nothing after it:

    script -q -e -c "sudo bash /home/op/s33-r9-c1.sh" /home/op/s33-r9-c1.txt

### Sheet C2 — the sentinel, then alpha (`sudo`)

1. The sentinel, `/home/op/s33-r9-sentinel.sh` (derived from
   `s32-r8-sentinel.sh`, D1635's repair: the LAST line is the value; count
   before write; the secret path DERIVED from `active-secret-generation.json`,
   never remembered), title `s33-redeploy-sentinel-<YYYY-MM-DD>`, before-file
   `/root/s33-redeploy-before.json`; its read-back prints both fields.
2. **The deploy**, at the terminal, nothing after this line:

       script -q -e -c "sudo ./deploy.sh --host host.yaml --project project.alpha.yaml --capabilities capabilities.yaml --through-session 33" /home/op/s33-deploy-alpha.txt

   → exit 0. Step 0 `admitted` with Session 32's numbers (nothing moved a
   `mem_limit`). **Step 6 applies ONE migration** — the ledger is what is read
   (D941). Step 6d prints alpha's *no set* line. `auth` and `mcp` recreated
   (image and lock moved). If step 6 fails: **STOP** (§9).
3. The reads (the agent stages `/home/op/s33-r9-after.sh` from
   `s32-r8-after.sh`): `bin/migrate.sh --project project.alpha.yaml --runtime
   status` → **35 `[X]` lines, `Pending: 0` — the first time this verb has
   printed a ledger since 1.8.0 (D1707)**; `bin/doctor.sh --project alpha-dev`
   → **12 ok**, the `workflow` line reading `approvals pending 0`.

       script -q -e -c "sudo bash /home/op/s33-r9-after.sh alpha" /home/op/s33-r9-after-alpha.txt

### Sheet C3 — beta (`sudo`)

The same two lines with `project.beta.yaml` and `beta`; step 6d installs FOUR
definitions (two new, two re-installed identically — read the exact line from
the transcript, do not predict it); the ledger **35 + 2**, `Pending: 0` twice;
`doctor` 12 ok.

### Sheet C4 — the pre-sweep reading (`sudo`)

`/home/op/s33-r9-readings.sh` (from `s32-r8-readings.sh`): `bin/doctor.sh
capacity --host host.yaml` (ceilings unchanged, 4,480 MiB by compose project
— nothing here moved a cap); `bin/doctor.sh --project beta-dev` (the
`workflow` line's counts written down as the BEFORE); `bin/doctor.sh usage
--project beta-dev` (exit 6 is expected — D1712's wording now says why).

    script -q -e -c "sudo bash /home/op/s33-r9-readings.sh" /home/op/s33-r9-readings.txt

### Sheet C5 — the sweep (`sudo`)

`sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/alpha-dev/
outputs.json /home/op/alpha-dev-outputs.json` and the same for beta (D1631's
names); **the agent confirms both name Run 8's `source_commit` before the next
line**; then `sudo bash /home/op/s33-r9-launch.sh` — which detaches the sweep
itself and returns at once; ~15 min; the agent reads `/home/op/s33-r9-host.code`
(0 or 5) and `/home/op/s33-r9-host-summary.txt`. While it runs, the agent (as
`op`) samples beta's `auth` memory (Run 9's text).

### Sheet C6 — the cleanup (`sudo`)

The sentinel removed by `/home/op/s33-r9-cleanup.sh` (from `s32-r8-
cleanup.sh`: the container, database and title DERIVED from the deployed
document and the before-file; expect `DELETE 1` — D1547 still makes this a
root `psql`); `bin/doctor.sh --project beta-dev` (the AFTER counts: runs by
status including `cancelled` and `failed` with compensation, approvals
pending 0); `bin/dr-kit.sh export … --output /home/op/kit-<date>-post`. The
agent then fetches the deploy transcripts, the sweep's evidence half and the
memory samples by `scp` as `op`, and copies the two new kits off-host to
`~/dr-kits/` in WSL (verified there, 0700/0600 modes kept on ext4 — the step
Sessions 30–31 skipped, found at 32's close).

    script -q -e -c "sudo bash /home/op/s33-r9-cleanup.sh" /home/op/s33-r9-cleanup.txt
