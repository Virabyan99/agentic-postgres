# Session 9 — Agent writes, the audit record, and the kill switch

Two write tools, one-to-one with two operations this repository shipped in
Session 5, a durable audit record with a fail-closed contract, and a revocation
that stops a token on its next request through both surfaces.

**No generic dispatcher. No second authorization system. No new API operation.**

---

## 0. Where Session 9 actually starts

Session 8 closed with `evidence/session-08.json`: **43 claims, 41 passed, 2
failed**, the two red ones Session 5's and blocked on the rotation window. Both
projects run `911a9d3b` with 18 migrations, `max_connections` 56, outputs v12,
and a deployed four-tool agent read plane — 16 containers, `mcp` included.

**There is no Session 9 runbook.** Sessions 1–8 each rewrote one, and §1 of each
plan was the list of places the runbook was wrong. What Session 9 has instead is
`docs/source-specification.md` §17's five-paragraph summary. So **§1's job
changes**: it is now the list of places where the session summary asks for
something this repository already has, or asks for it in a shape this repository
refuses. That list is still the point of this document, and it is longer than it
looks.

Five things are already true and change the shape of the work:

1. **Both write operations exist, are reviewed, and are granted to
   `agent_writer`.** `api.create_note(p_title, p_content)` and
   `api.update_task_status(p_task_id, p_expected_status, p_new_status)` shipped in
   migration 0007; `contracts/postgrest-api-surface.yaml` reviews both under
   `rpcs:`. **No migration adds an operation and ADR 0003's frozen domain does
   not move.**
2. **The two tools are already named**, in `docs/capability-plan.md`, with their
   scopes and the one-to-one rule. Session 9 implements a plan; it does not
   invent one.
3. **`capabilities.schema.json` v1 already carries the write shape** — `kind:
   write`, `max_affected_rows`, `idempotent`, and `audit.redact`. Nothing is
   renamed and nothing is removed, so **no version bump** (D403, second time).
4. **The authoritative active-agent check is already inside every database
   request.** Migration 0018's `agent_claims_are_current` matches `status`,
   `role_name`, `scopes` and `authz_version` and returns the owner. Session 9
   adds no check; it proves the one that is there.
5. **The revocation endpoint already exists** — `PATCH /admin/agents/{agent_id}`
   with `{"status": "revoked"}`, which flips the status *and* bumps
   `authz_version` in one statement.

**So two of the summary's five Build bullets are already deployed**, and what is
left of a third is the audit *query* endpoint alone.

Session 8 was planned as nine runs and took **twelve**; Session 7 was planned as
ten and took **sixteen**, because the trips found seven and eight defects. **Plan
for the same.**

---

## 1. Divergences from the session summary

Six columns, the house shape. The "summary says" column quotes
`docs/source-specification.md` §17. Rows are predictions made at plan time; each
is confirmed, corrected or replaced during implementation, and anything found
*during* implementation is appended with the next free number.

**Next free number after this table is D506.**

| # | Summary says | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D469** | "Two representative project-specific tools should demonstrate the one-tool-to-one-operation pattern." | **Both tools are already named and both operations already exist.** `docs/capability-plan.md` has listed `create_note` (`notes:write`) and `update_task_status` (`tasks:write`) as Session 9's since Session 1, each "Named PostgREST RPC, one-to-one". The operations shipped in migration 0007: `api.create_note(p_title text, p_content text DEFAULT '')` and `api.update_task_status(p_task_id uuid, p_expected_status api.task_status, p_new_status api.task_status)`, both `SECURITY DEFINER`, both reviewed in `contracts/postgrest-api-surface.yaml` under `rpcs:`. `update_task_status` is already an optimistic compare-and-swap raising `AP404`/`AP409`. | **Session 9 writes no SQL for the operations themselves.** It writes two capability entries, two tool closures, and the transport that can carry an argument body. The derived operation ids are `rpc.create_note.post` and `rpc.update_task_status.post` (ADR 0119). | Inventing a "representative" operation here would be a fifth and sixth human operation, and **ADR 0003's example domain is frozen** — amended exactly once, by ADR 0048, for one additive column. D418 is the precedent: when a proof wanted a fifth operation, *the proof moved, not the product*. | — |
| **D470** | "explicit writes … with input validation, required scopes, bounded side effects". | **The schema already expresses all three, and the compiler cannot compile any of them.** `schemas/capabilities.schema.json` `$defs/capability` has `kind` enum `["read","write","metadata"]` and a conditional requiring `max_affected_rows` (1–100) and `idempotent` for a write. But `capability_compiler._compile_tool`'s `resources` comprehension is gated `if kind != "metadata"`, so it runs for a write, and it unconditionally reads `entry["capability"]["resource"]`, `["columns"]` and `["max_rows"]` — three fields the schema does **not** require of a write. A write capability `KeyError`s. `max_affected_rows`, `idempotent` and `audit.redact` are validated on the way in and **emitted into nothing**. | **Extend the compiler; do not touch the schema.** A write compiles to a tool with an operation, an argument contract and a `max_affected_rows`, and no `columns`, `filters`, `order_by` or `max_rows`. The three orphaned fields reach the lock, or the manifest's audit declaration is a comment. | **D403's shape, second time**: a version bump that renames nothing and removes nothing is a migration everyone pays for and nobody needed. And a field that validates but reaches nothing is **D274's shape** — a claim that lives only in a document nobody dereferences. | — |
| **D471** | "PostgREST adds the authoritative active-agent check inside each database request so a previously issued token stops working immediately after revocation." | **Migration 0018 already did this, and its own `COMMENT` states the property.** `app_private.agent_claims_are_current(p_agent_id, p_role_name, p_scopes, p_authz_version)` selects `a.owner_id … WHERE a.id = … AND a.status = 'active' AND a.role_name = … AND a.authz_version = … AND a.scopes = …`; the hook's `token_use = 'agent'` branch raises `AP401`/`PT401` when it returns NULL. The comment: *"A revoked, disabled or re-authorized agent stops on the NEXT request, not at the token's expiry."* | **Session 9 adds no check here and must not appear to.** `SEC-REV-001` becomes a **proof**, not a build: revoke mid-session, then assert the same token fails its next MCP read, its next MCP write, and its next direct PostgREST request. | Building a second check would give one fact two authorities that have to be kept in step — which is D397's shape, and the reason there is no `agent_id` claim beside `sub`. The failure mode a session like this produces is *a control added beside a control that was already there*, after which neither is the one anybody reads. | — |
| **D472** | "Admin audit query **and revocation** endpoint." | **The revocation endpoint exists.** `PATCH /admin/agents/{agent_id}`, gated on `admin_agents:write`, body `{"status": "revoked"}` → `AuthService.set_agent_status` → `app_private.auth_set_agent_status`, which does `SET status = p_status, authz_version = authz_version + 1` and returns the new version. `app_private.agent_status` is a **two-value enum** — `('active','revoked')` — because 0011 decided that *"a user is disabled and can be re-enabled; an agent credential is revoked, which is terminal."* | **Only the audit query endpoint is new.** It sits beside `GET /admin/agents` with a new `admin_audit:read` scope. The kill switch is one PATCH that already works, and the operator guide names it rather than a new verb. | A second revocation path would be a second way to reach a terminal state, and the two would drift on the `authz_version` bump — which is the part that actually stops the token. **`SEC-REV-002` is Session 6's and already green**; this row is what keeps `SEC-REV-001` from re-proving it. | — |
| **D473** | "FastMCP records an audit entry before forwarding a request … and completes the record." | **FastMCP cannot write to the database, by construction and on purpose.** `settings.load_mcp` refuses to start if any of `FORBIDDEN_VARIABLES["mcp"]` is set — `APG_SIGNING_KEY_FILE`, five `APG_DATABASE_*`, `APG_POOL_SIZE` — and `McpSettings` has no `conninfo`, no passfile and no pool size for a later change to fill in. Its zero share of ADR 0099's budget is asserted by a test that parses the arithmetic (D407). | **Two `SECURITY DEFINER` functions in `api`, called over PostgREST with the caller's own token**: `agent_audit_begin` returns an id, `agent_audit_complete` closes it. Identity comes from the `app.agent_id` / `app.user_id` GUCs the hook sets and is **not a parameter**. `mcp_audit_service` stays unactivated. | Handing the runtime a credential reverses D407 and reopens a fully-allocated budget inside a session about writes; routing the write through auth-api gives one service two database roles. The definer route needs neither, and it is the route the runtime **already takes** for `mcp_agent_context` — so it is one more call on a path that is proved, not a new one. **And the GUC identity is what makes `SEC-PARAM-001` structural**: a parameter that could name a principal is the thing that requirement forbids. | **needed** |
| **D474** | The audit entry is recorded "before forwarding a request". | **The pre-request hook cannot be where that happens, and this repository measured it twice.** 0008's header and 0013's both record it: PostgREST runs the hook inside the request transaction, which is **READ ONLY on a GET**, and *"an early version that kept an audit row turned the entire read surface into 405 'cannot execute INSERT in a read-only transaction'."* | **Nothing is written from the hook.** The record is written by an explicit call the runtime makes before it forwards, and closed by a second call after. Two round trips per audited call, on top of the context resolution — stated as a cost in §3 rather than discovered on a cluster. | The tempting design is the cheap one: the hook already runs on every request and already knows who is asking. It is also the one place in this schema that provably cannot write. **A measurement recorded in two migration headers is exactly the kind CLAUDE.md §4 step 2 says to grep for before measuring again** (D57/D262's lesson). | — |
| **D475** | Implied: activating `agent_writer` is adding it to the authenticator's memberships. | **`agent_writer` appears zero times in migration 0018** — verified, `grep -c` returns 0. 0018 granted `USAGE ON SCHEMA app_private`, `EXECUTE` on `postgrest_pre_request`, `EXECUTE` on **both** comparison helpers, and `EXECUTE` on the two read RPCs to `{{anon}}, {{authenticated}}, {{api_documentation}}, {{project_admin}}, {{agent_reader}}` — and to no write role. **An `agent_writer` token today is refused by `permission denied for function postgrest_pre_request`, not by `AP401`.** | **Migration 0019 grants the hook and both helpers to `agent_writer`** before anything activates the membership. The activation itself is one string in `postgres_bootstrap.AUTHENTICATOR_REQUEST_ROLES`. | **This is D417 exactly, one session later.** There, the correct refusal stood on a missing GRANT and reached the caller as a 42501 instead of the hook's own `AP401`, so a client could not treat "your token is stale" as one outcome. 0018's own comment says the rule — *"both comparison helpers, to every role that runs the hook"* — and lists five roles because a sixth did not exist yet. **§6 question 5: which of this decision's callers got it?** | — |
| **D476** | "Scope-gated tool visibility and execution" — and the exit criterion, "a read-only agent cannot **call or discover** unauthorized writes." | **Execution is gated; `tools/list` is not.** `Tool.discoverable_by()` — the disjunction-of-conjunctions ADR 0120 and D421 exist for — is compiled into the lock, asserted by two contract tests, and **has no production caller anywhere**. There is no `on_list_tools` hook; `AgentContextMiddleware` implements `on_request` only. Session 8's filtering is at the **resource** level, inside the `list_resources` payload, and its deployment proof says so in as many words: *"`run_report` must not appear among the resources discovery returns, while the four tool NAMES still do."* | **Session 9 adds the `tools/list` filter and `discoverable_by` gets its first caller.** The two levels stay distinct and both are proved: a name is hidden, and a resource behind a visible name is hidden. | Four read tool names leaking to a reader who would be refused was untidy. **A write tool name leaking to a read-only agent fails `AGT-WRITE-001` on its own words.** This is **D454's family** — the seam nobody crossed, third instance after D444 and D450 — and it is recorded as that rather than repaired quietly, because the class is what predicts the next one. | — |
| **D477** | "propagates a request ID through the downstream stack". | **There is no argument channel at all, let alone a header one.** `UpstreamRequest` is `(method, path, query, timeout_ms)` with no body field, and `mcp_upstream.execute` sends a hardcoded `data=b"{}" if request.method == "post" else None` — enough for the argument-free `run_report` and for nothing else. `execute` also refuses outright when `set(headers) != set(FORWARDED_HEADERS)`, and `FORWARDED_HEADERS` is `("Authorization", "Accept")`. | **`UpstreamRequest` gains a body; `build_request` gains a write branch emitting no `select` and no `limit`; `FORWARDED_HEADERS` gains the request-id header and the guard moves with it in the same commit.** | The guard is a good one and it will fail closed on exactly this change, which is the correct behaviour and the reason to name it here: **a widened allowlist whose checker did not move is D300's shape**, and the repair is never to turn the equality into a subset. Both allowlists that failed on Session 8's trip (D468) were right to fail. | — |
| **D478** | "propagates a request ID through the downstream stack" (the scope of "the stack"). | **`OPS-LOG-001` is Session 11's**, registered as P1, and reads *"One request ID propagates across **ingress**, API, agent, and audit records"*. Nothing in this repository mints a request id today except `services/edge-probe/probe.py`, which is unrelated. | **Session 9 owns exactly MCP → PostgREST → audit record.** Ingress is Session 11's and this plan says so, in §7, so that Session 9's evidence cannot be read as closing `OPS-LOG-001`. | **This is the §7 discipline Sessions 7 and 8 both closed on**, applied forward instead of backward: a session that half-closes another session's requirement and does not say so leaves the next reader unable to tell a proved guarantee from a plausible one. | — |
| **D479** | "completes the record with … redacted parameters." | **`audit.redact` is required by the schema whenever `audit` is present, is carried by all five current capabilities as `redact: []`, and is read by nothing.** It survives `load_capabilities_manifest`, is dropped by `_compile_tool`, and never reaches the lock or the runtime. | **The lock carries `audit.redact` per tool and the runtime obeys it.** At least one write declares a **non-empty** list, so the mechanism has something to prove rather than a redaction of nothing. | An empty redaction list on every capability is indistinguishable from a redaction mechanism that does not exist — which is what it currently is. **D277**: a proof asking whether a name is *mentioned* is satisfied by dead code; assert what the code produces. | — |
| **D480** | "durable attribution" for agent writes. | **An agent token reaches PostgREST directly — that is how MCP forwards it.** The hook's agent branch runs for any request carrying an agent token, so an agent holding `notes:write` can `POST /rpc/create_note` without going near `/mcp`. An MCP-side record would not see that write. | **The two write RPCs append their own audit row, in the same transaction, when `app.agent_id` is set.** Both are already `SECURITY DEFINER` and both run in a POST transaction, so D474's read-only constraint does not apply. A human caller sets no `app.agent_id` and is unaffected. The MCP begin/complete record keeps denials, timing and redaction. | Two records, and the plan says which answers what: **a denied call never reaches the database**, so it has only the MCP record; **a bypassing call never reaches MCP**, so it has only the database record; an ordinary MCP write has both and they agree. Attribution that a caller can route around is attribution the record-keeper cannot rely on, which is the whole difference between this and telemetry. | **needed** |
| **D481** | Implied: a write agent uses the same surface a read agent does. | **`agent_writer`'s ceiling is `{notes:read, notes:write, tasks:read, tasks:write}` — no `meta:read`.** So `scope_registry` would refuse to mint a write token carrying it, `_resource_for` would refuse `describe_resource`, and `list_resources` would return an empty resource list. **A write agent cannot discover the surface it is authorized against.** | **An ADR amends ADR 0079's table** and `agent_writer` gains `meta:read`. It is a ceiling, not a grant: each agent's own scope list still decides what it holds. | The omission reads as deliberate and is not: `meta:read` exists precisely so introspection is a scope rather than a privilege of being an agent, and every other role that can call a tool has it. Leaving it out would make D476's new `tools/list` filter hide discovery from exactly the callers who most need it. | **needed** |
| **D482** | "FastMCP records an audit entry" — with `mcp_audit_service` sitting unactivated since Session 3. | **The role is not merely unactivated, it is unreferenced.** It is in `naming.ROLE_SUFFIXES` and in the bootstrap's `CREATE ROLE` sweep, and in **no** migration template, **no** `migrations/manifest.json` placeholder, and no grant. And `tests/contract/test_mcp_budgets.py::test_nothing_in_the_agent_plane_names_the_audit_role_in_CODE` is an AST scan that fails if the literal string appears in any `services/auth-api/app/mcp_*.py`. | **It stays unactivated, and Session 9 records the reason rather than inheriting the deferral.** No manifest placeholder is added. The AST guard stays exactly as strict. | The handoff says Session 9 *owns deciding*, not inheriting — and the decision is that D473's route needs no service identity at all, so activating one would put a login role in production to write records that something else writes. **A role that exists and is not activated is a promise the next session keeps; keeping it can mean deciding it is not needed.** | **needed** |
| **D483** | "audit initialization fails closed **for writes**". | The summary says writes and is silent on reads, and the asymmetry is load-bearing rather than an omission to tidy. Failing a read closed would couple every agent read's availability to the audit table and add a mandatory round trip to a path ADR 0125 already pays one for. | **A write whose `agent_audit_begin` fails does not happen.** A read whose begin fails is refused too **only if** the record is the point of the read; otherwise it proceeds and the failure is emitted as telemetry with outcome `failed`. **This is an ADR, taken with the measurement in hand**, not a default. | Stating "fails closed" without saying for what is how a guarantee becomes two guarantees, one of which nobody implemented. `AGT-AUDITFAIL-001`'s own description is *"a write fails closed when its audit record cannot be created"* — the requirement is already narrower than the reflex, and the reflex is what needs writing down. | **needed** |
| **D484** | Implied: Session 9's five placeholders are replaced as the code that satisfies them lands. | **They cannot be, one at a time.** `test_every_later_requirement_has_a_placeholder` requires a placeholder for every requirement with `target_session > gate_session`; `test_no_requirement_at_or_before_the_gate_session_remains_future` forbids one at or before it. Exact mirrors, and `gate_session` defaults to `CURRENT_SESSION`, which is **8**. | **One commit** moves `CURRENT_SESSION` 8 → 9 and repoints all five registry entries at real tests, deleting the five placeholder functions. Verified beforehand with `APG_ACCEPTANCE_SESSION=9 pytest tests/contract/test_acceptance_registry.py tests/contract/test_future_marker_policy.py`. | **D439, verbatim, and it is the second session to pay for it.** Session 7 Run 9 and Session 8 Run 6 both did it in one commit for the same reason. Session 9's count is **five** and every one is `target_session: 9` — checked, unlike D414's five which turned out to be six. | — |
| **D485** | — (a consequence of the above, at plan time). | Outputs is **v12** on this tree and both deployed projects. The `mcp` block publishes protocol, `authorization_spec_conformant`, `token_use`, tool count and the two capability digests. Session 9 changes `tool_count` from 4 to 6 — a **value**, not a schema change — and may want the audit plane's readiness published. | **Decide the version once, in Run 1, from the whole session's surface** — not from the run in front of you. If nothing but `tool_count` moves, **there is no bump**. | **D255 and D308 are the same mistake twice**, and D402 is the rule they produced: a version chosen one run early, from the run in front of you, is a version that has to move again. | — |
| **D486** | "no generic dispatcher" — four tools become six. | **"Exactly four" is asserted in five independent places**, which is the design working: `mcp_lock.METADATA_TOOLS`/`READ_TOOLS`/`EXPECTED_TOOL_NAMES` (a fifth tool fails `load_lock` before registration), `mcp_tools.TOOL_NAMES`, two contract tests in `test_mcp_tools.py`, the prose in `docs/mcp-tool-catalog.md`, and `test_mcp_catalog.py` comparing the prose to the contract. | **All of them re-derive to six, in one run**, with `WRITE_TOOLS` added beside the other two tuples so the number stays computed. **A seventh tool must still fail the start, offline**, and a test proves it after the change, not only before. | ADR 0127's "there are exactly four" was never about the number — it was about the surface being enumerated rather than discovered. Widening it by editing one of five copies and leaving four is **D416's shape**, where a constant existed precisely so the proof could read it and three restatements survived anyway. | — |
| **D487** | "bounded side effects". | Both RPCs are `RETURNS api.notes` / `RETURNS api.tasks` — **a single composite row, not `SETOF`**. `max_affected_rows` for each is therefore **1**, and that is the function's actual shape rather than a ceiling chosen to look safe. | `max_affected_rows: 1` on both write capabilities, with the reason at the entry, and the bound checked **against the response** rather than trusted. | This is `run_report`'s `max_rows: 1` argument again, and the manifest already states it: *"the function's actual shape — it returns exactly one row — rather than a bound chosen to look safe."* A bound larger than the operation can produce is a bound that can never fire, which is a control measuring nothing. | — |
| **D488** | — (found at plan time, reading `compose.yaml`). | Moving `CURRENT_SESSION` to 9 arms a `session9` Compose profile. **No service declares one**, because Session 9 adds no container: writes and the audit calls live in the existing `mcp` runtime, and the admin endpoint in the existing auth-api. | **No new service, no new profile, no change to `DEFERRED_SERVICES`.** The plan states it so that an empty profile is not mistaken for a missing one during the trip. | Session 7 Run 9 moved the constant and the next deploy immediately tried to start a storage container that failed closed without its secrets, so the guide had to say so **before** the step. The inverse — a constant that arms nothing — is worth the same sentence, because the operator will look for the container that did not appear. | — |
| **D489** | — (measured during Run 1). D480 says the write RPCs append their own audit row so that a write cannot happen unaudited by any route. | **A row written inside the transaction it describes can record a COMMITTED change and nothing else.** Measured on the pinned image: a write that `RAISE`s aborts the transaction and the audit row inserted before the raise goes with it — 0 rows, against a paired positive that leaves 1. There is no arrangement of exception blocks or subtransactions that keeps it: a handler discards its savepoint just as surely as an aborting transaction does. Recording a failed write durably would need an autonomous transaction, which is a second connection, which is the credential this plane does not hold (D407). | **The table carries a `source` column and the two records are named as different artefacts.** A `database` row records what CHANGED and is the only kind that can say `committed`; an `agent_plane` row records what was ATTEMPTED and is the only kind that can say `refused` or `failed`. `agent_audit_complete` **refuses** the `committed` outcome, so the agent plane cannot label its own attempt as a change that happened. | The plan said the two records "answer different questions" and did not say this, which would have left the next reader expecting failed writes in the database record and finding none. **The paired positive is what makes the negative mean anything**: zero rows is also what a table nothing ever writes to looks like, and that is the shape D269 is about. | 0135 |
| **D490** | Run 1: *"Both reviewed into `contracts/postgrest-api-surface.yaml`'s `agent_rpcs:` block."* | **`agent_rpcs` structurally cannot hold them.** `api_surface.py` refuses any entry declaring arguments and the schema states it as `maxItems: 0`, because *"PostgREST serves a stable function over GET as well as POST, so an argument here reaches the query string."* The audit functions cannot be argument-free — `complete` must name the record it closes. **Measured on PostgREST v14.16, and both predictions were wrong**: a GET on a VOLATILE function is **not** refused (200, argument taken from the query string), so volatility protects nothing; but a function that actually **writes** is refused **405 / `25006 cannot execute INSERT in a read-only transaction`** — D474's mechanism, arriving from the other side. | **A fourth section, `agent_write_rpcs`**, POST-only, arguments enumerated. **`agent_rpcs`' `maxItems: 0` does not move**: its reason survives the measurement intact. The new category's guarantee is explicitly narrower — the 405 prevents the **effect**, not the **disclosure**, because the argument is already in every log and cache by then — so the argument list is enumerated as the review surface and may carry no secret. | The first draft put both functions under `agent_rpcs` and deleted the check, which is **D300's shape on a boundary whose justification is still true**. Widening a rule to fit two functions it was not written for is how a boundary stops meaning anything. And the honest half is the one worth keeping: this category is weaker, it says so, and a live-host GET returning 405 is named as the proof rather than assumed. | 0136 |
| **D491** | — (found during Run 1, by a test failing for the wrong reason). | **`test_api_migrations.py`'s `_CREATE_FUNCTION` regex silently over-matched and swallowed a whole function.** It requires `RETURNS` on its own line — `\)\s*\n\s*RETURNS` — and 0019 was first written as `) RETURNS uuid`. With `re.DOTALL` and a non-greedy group the match ran forward from `agent_audit_begin(` to `create_note`'s `RETURNS`, capturing a garbage argument list and consuming the text in which `agent_audit_complete` was defined. The reported failure was *"agent_audit_complete is missing"*, which points at the wrong file entirely. | **The migration's formatting moved, not the shared regex.** Four other functions depend on that anchor, and loosening it to accept both spellings would make the over-match permanent rather than fixing it. Verified afterwards that all four functions now parse with their **correct** argument lists, because a matching count is not the same as a correct capture. | A scanner that mis-parses rather than refusing is this project's signature defect with the failure on the wrong side. Had 0019 added **one** function instead of two, the regex would have swallowed forward, captured garbage arguments, and the count would still have matched — and only the argument comparison, which does not run for this section, could have noticed. **The near-miss is the finding**, not the formatting. | — |
| **D492** | — (found during Run 2, reading the tests that name `agent_writer`). | **A test had been asserting a property the product lost in Session 8.** `test_the_authenticator_cannot_become_an_agent_role` asserted the authenticator could become neither `agent_reader` nor `agent_writer` — but Session 8 activated `agent_reader`, so in production it *can*. It stayed green because its fixture granted a **hardcoded list of four** request roles omitting both, with a comment saying granting them *"would delete the property"*: the fixture was manufacturing the condition the test measured. Its docstring's other premise had expired too — *"there is no path on which the hook could emit an agent-specific error"* is false since migration 0018's `token_use` branch, which raises `AP401`. | **The assertion becomes the rule the old list was an instance of**: the authenticator becomes **exactly** the request roles and no others, both halves read from `AUTHENTICATOR_REQUEST_ROLES`, with the negative arm over every other declared role and an explicit refusal to run vacuously. Every fixture that grants memberships now reads the constant. And a new comparison with teeth: the roles granted `EXECUTE` on the hook, read from the catalog, must **equal** the request-role set — two independent products rather than one read twice. | **A fifth copy of an enumeration that exists as a constant so proofs read it** — D301's shape, after Session 8 Run 2 deleted three others (D416). The habit is durable enough that **Run 1 of this session made a sixth**, one run after this was found, in a test written by the same hand that wrote the row. | 0137 |
| **D493** | — (found during Run 2, by a mutation that survived). | **A subset-versus-exact mutation cannot discriminate while the two sets are equal.** Turning `holders == request_roles` into `holders >= request_roles` SURVIVED — not because the assertion is weak but because every comparison operator agrees when the sets coincide. The battery had nothing to measure. | **The mutation was replaced, not the test.** Proving exactness needs the asymmetric state — a role GRANTED the hook that no token can name — which means granting to a role the migration does not declare, which the renderer refuses (Run 1's M3). So M5 became a **two-file** mutation moving the manifest entry with the template, and it kills. | **D300's property is the one this project re-learns most often, and this is the first time a battery could not demonstrate it.** Worth recording because the obvious reading of a survivor is "the test is weak", and here the test was exact and the mutation was uninformative — the mirror of D269, where an unapplied mutation reads as a weak test. A battery arm that cannot distinguish two behaviours is evidence about the arm. | — |
| **D494** | — (found during Run 3, by running two mcp test modules outside the gate's canonical order). | **The middleware-pipeline test could not pass alone, and a concurrency test's cleanup was why no gate ever saw that.** `test_a_request_reaches_a_tool_through_the_real_middleware_pipeline` (D450's proof) arranged a context resolver and a tool executor and never a **token**, so in isolation `AgentContextMiddleware` correctly refused its tokenless request. It passed every gate since Session 8 Run 8 because `test_concurrent_requests_never_see_each_others_context` swapped `fastmcp.server.dependencies.get_access_token` **per coroutine** and restored it in each one's `finally` — and under interleaving the restores race: a coroutine captures another's stub as `original`, the LAST restore wins, and the framework module keeps a fake token function **for the rest of the process**. Measured with a probe-and-control rig: after the concurrent test a probe asserting the genuine function FAILS; after the sequential `_drive` test beside it, it passes. | **Both tests repaired, neither weakened.** The concurrent test installs ONE stub via `monkeypatch` that reads the caller's token from a `ContextVar` — task-local under `gather`, so the twelve tokens stay distinct and the single restore cannot race (battery M9 mutates the stub to a constant and the test goes red). The pipeline test arranges its own token, which is the thing a pipeline behind an authenticating middleware requires of a caller. Verified: the probe passes after the fixed concurrent test, and the pipeline test passes **alone**. | **A test green only downstream of another test's leak is D374's family with the pollution in the suite rather than in the assertion** — it passed every gate since Session 8 Run 8 for an unrelated reason, and the unrelated reason was another proof's cleanup racing itself. The swap-and-restore pattern (`original = attr; attr = stub; finally: attr = original`) is correct sequentially and wrong under ANY interleaving, and `_drive` in the same file uses it safely — sequential use is the entire boundary, and nothing marked it. §6 question 2 found it: the proof had never run in the environment "alone". | — |
| **D495** | — (found during Run 5, wiring the first tool that reaches upstream and names no resource). | **`bounded()`'s `resource is None` was carrying two ideas**, and they had agreed for as long as every upstream tool had a resource: *"names no resource in the telemetry record"* and *"does not reach upstream, so takes no concurrency slot and no thread"*. A **write** has neither property together — it is one-to-one with its operation (D486), so there is no resource to name, and it dials PostgREST, so it must hold a slot. Registering both writes with the inference intact would have run them **unbounded on the event loop**, which is D451 restored by accident and invisible: the semaphore would simply never see them. | **`bounded` takes an explicit `upstream:` argument** and the four existing call sites state it. The telemetry `resource` stays `None` for a write, which is honest — `ReadRecord.resource` is already `str | None` and the `tool` field already names the operation. | **D463's shape, exactly, one session later**: `POST_BOOTSTRAP_SERVICES` meant two things, one consumer satisfied the second by accident, and the agent plane needed only the second and lost it. Here the accident was in the other direction — the inference was *correct* for every tool that existed when it was written, and a write is the first caller that separates the two. Battery arm W13 restores the inference and the write's slot assertion goes red, with the end-to-end write test green beside it (a write still *works* on the loop; it is only unbounded). | 0140 |
| **D496** | §5 Run 5: *"moves the `live_host` four-tool assertions in `tests/deployment/test_session8_agent_plane.py` (lines asserting the four names and `tool_count == 4`) to six."* | **The two assertions stop being the same number, and only one of them is six.** `mcp.tool_count` is read from the compiled lock and is what the deployment SERVES: six. `tools/list` is now filtered per caller by Run 5's own `on_list_tools` hook, and the probe agent holds `meta:read` and `notes:read` — so its roster is **three** names. `run_report` needs `notes:read` AND `tasks:read` as a conjunction (D421) and both writes need a write scope. The plan's sentence was written before the filter existed and would have had the run assert six from a caller that can reach three. | **The document assertion moves 4 → 6; the roster assertion moves from four names to the three that caller's scopes reach**, with the reason in the docstring rather than the number alone. A new `live_host` test carries `AGT-WRITE-001`'s two halves against the deployment — the write names absent from the roster, and the call refused when made anyway. | **The plan asked for one number and the code produced two questions**, which is the good version of this row: the filter is what the same run was asked to build. Recorded rather than reconciled silently because a future reader comparing `tool_count` with a `tools/list` length would otherwise read a discrepancy where there is a decision — and because the *positive* half is what keeps the exclusion honest (a roster missing `query_resource` would satisfy every exclusion while proving nothing). | 0140 |
| **D497** | — (found during Run 5, asking §6 question 5 of `MAX_SERIALIZED_BYTES`). | **ADR 0129's response bound had exactly one caller, and the write path was not going to be it.** `MAX_SERIALIZED_BYTES` was reachable only from inside `_within_budget`, *after* the row-count check — and a write has no row ceiling to check, so a write result would have been the one thing this process returns without a byte bound. `create_note` echoes the created row back and `content` is an unbounded `text` column, so it is not theoretical. | **The byte half is split into `_within_byte_budget` and the write path calls it.** The row half keeps its own check and calls the byte half, so a read's behaviour is unchanged and there is still one place the ceiling is written down. | **§6 question 5 — when a decision is implemented, which of its callers got it?** — asked of a budget rather than of a grant or a verifier. It cost one function split, found before the code was written rather than on a cluster, which is the cheapest place this question ever pays. Battery arm W18 removes the call and the write's ceiling test goes red with the end-to-end write green beside it. | — |
| **D498** | — (found during Run 6, by a mutation that survived). | **The request id's PROPAGATION was proved and its UNIQUENESS was not.** Every offline test arranges a fixed id through `monkeypatch` so an assertion can name it — which is the right call, because a test that minted its own could only say "some id was forwarded", a claim satisfied by forwarding the wrong one. But it meant nothing offline ever executed `uuid.uuid4()`: replacing the mint with a constant left **every** contract test green, and the only proof that two calls differ was the live-host one, which has never run. | **A new offline test of the mint**, not a changed mutation: three requests through the real middleware, two of them reusing a TOKEN, and all three ids must differ and parse as UUIDs. The token arm matters because an id *derived* from the caller would pass a naive uniqueness check. | **D493's distinction, pointing the other way.** There a survivor was evidence about the *arm* — two equal sets, so no operator could discriminate. Here the arm was right and the coverage was absent, and telling the two apart is the whole reason a survivor gets read rather than re-rolled. Question 2 of §6 found it: *has this run at all, in this environment, since the thing it measures changed?* — and the answer for the mint was **never**. | 0141 |
| **D499** | — (found during Run 6, by the battery's own pairing). | **Two battery arms reported a false survivor because the CONTROL called the mutated function.** A7 and A8 mutate `mcp_audit.redact`; their control was `test_redaction_does_not_invent_a_parameter_the_caller_never_sent`, which calls `redact` directly. Target and control both went red, so the pair proved the target had died and **nothing about isolation**. | **The control moved, not the assertion** — to a test that exercises `begin`/`complete` and never reaches `redact`. Both arms then killed with a green control in the same invocation. | **CLAUDE.md §1 names this rule and says Session 8 paid for it twice** — Run 1 reported two false survivors and Run 3 one, every time because the control legitimately read the mutated value. Recording it a third time because the failure is silent in the direction that matters: a false survivor reads as "the test is weak", and the reflex repair is to strengthen an assertion that was never the problem. | — |
| **D500** | ADR 0135 and D480: the two records "answer different questions", and Run 6 "propagates a request ID through the downstream stack". | **The `database`-source row carries no `request_id`, so the two records for one MCP write cannot be joined by it.** Migration 0019's write RPCs insert `source, agent_id, owner_id, tool, outcome, row_count, completed_at` and no id — correctly, because at the time nothing minted one. Measured alongside it (rig6): **a custom request header DOES reach the database**, in `current_setting('request.headers')::jsonb` as a lowercased `x-request-id`, present when sent and absent when not. So the repair is available and is not taken here. | **The gap is recorded and left open.** The two records correlate by agent, tool and time. Closing it needs a **migration 0020** — 0019 is released, and amending a released migration is what the release control exists to prevent — so it is named in ADR 0141's consequences and in the Session 10 handoff rather than done quietly. A deployment test asserts the `database` row's `request_id` **is** NULL, so the day 0020 lands, the test that says so fails and points at its own premise. | **§6 question 5 — which of this decision's callers got it?** — asked of the id rather than of a grant. The answer is "the agent-plane record and every upstream request, but not the row PostgreSQL writes", and the honest half is that the *header measurement* makes it look cheap while the *release control* makes it a migration. D478's discipline applied forward: `OPS-LOG-001` is Session 11's and this row is what stops Session 9's evidence reading as if it closed the span. | 0141 |
| **D501** | Run 7: *"`GET /admin/…` beside `GET /admin/agents`, same four pieces — `_service` → `authenticate` → `require_scope` → `_guard`."* | **There is no fifth piece and the endpoint needs one: a statement it is allowed to send.** Migration 0019 created `app_private.agent_audit` and two indexes whose own comment names their reader — *"The admin query endpoint (Run 7) reads by owner and by agent, most recent first. Both indexes exist for that one reader; neither is speculative"* — and created neither the reader nor a grant. `repository.py`'s header states what that runs into: *"Fourteen function calls and no table names. `auth_service` holds schema USAGE on `app_private` and nothing else."* Verified: `SET ROLE auth_service; SELECT count(*) FROM app_private.agent_audit` is `permission denied`, with the positive control that the same role reaches the new function. | **Migration 0020**: `app_private.auth_list_agent_audit`, `STABLE SECURITY DEFINER`, granted to `auth_service` alone. Not a `SELECT` grant — the table's own `COMMENT` says no role holds `SELECT` and the definer functions are the only paths in, and a grant would make that sentence false. 0020 rather than an edit to 0019, because 0019 is released (ADR 0091). | **CLAUDE.md §6 question 5, asked of 0019: which of this decision's callers got it?** The indexes did; the grant did not. The failure mode is the one this project keeps producing — the endpoint would have been written, reviewed and merged, and failed on the first cluster with `permission denied for function`, four steps from its cause. It is D465's shape from the other side: there a wrong input produced an artefact rather than an error, here a missing grant produced two indexes rather than a warning. | 0142 |
| **D502** | — (found in Run 7, writing the first query-string endpoint in the auth service). | **`routes.py` refuses the duplicate-member defect for BODIES and nothing had asked the same question of a query string**, because no endpoint had one. Measured (rig7, locked Starlette 0.49.3, control arm first): `QueryParams("limit=1&limit=9999")["limit"]` is `"9999"` — **last wins, silently**, the body defect exactly. But `getlist` and `multi_items` still carry BOTH pairs, so unlike a JSON body the duplicate is still there to be refused. Also measured: keys are case-sensitive (`Limit` and `limit` are two keys, not a repeat); `limit=` is PRESENT with value `""`, not absent; and `int()` accepts whitespace, `+`, `1_0` and any Unicode decimal digit. | **`strict_query`, a sibling of `strict_json`**: a repeat is refused, an unknown name is refused, an empty value is a supplied value, and a bound REFUSES rather than clamping. The route parses; FastAPI binds nothing, because `Query` would inherit the defect. The document's `parameters` fragment is emitted by hand and a contract test compares it against the parser's allowlist. | The refusal is cheap here and the reason to write the difference down is the opposite case: for a body the duplicate had to be caught DURING parsing because nothing afterwards could see it. Two surfaces, one defect, two mechanisms — and the hand-declared document is **D274's shape** waiting to happen, which is why the comparison test exists rather than a comment saying to keep them in step. | 0143 |
| **D503** | D472, quoting migration 0011: *"a user is `disabled` by an administrator and can be re-enabled; an agent credential is `revoked`, which is **terminal** for that credential"* — and that comment names `SEC-REV-001` as its proof. | **Terminality is stated in a comment and enforced by nothing.** Measured through the product's own route: `PATCH /admin/agents/{id}` with `{"status": "active"}` on a revoked agent answers **200**, and the agent works again. `app_private.auth_set_agent_status` is a plain `UPDATE ... SET status = p_status` with no transition guard. The two-value enum is what stops a third state existing; it does not stop the second transition. | **Recorded, and the test asserts what the product DOES.** Session 9 Run 7 proves revocation rather than building it (D471, D472), and a transition guard is a migration and a product change. The day one lands, `test_the_status_type_admits_no_third_state_and_terminality_is_UNENFORCED` fails and points at its own premise — D500's arrangement, applied to a second gap. | **CLAUDE.md §6 question 1, asked of a comment rather than a test: what would have to break for this to go red?** Until Run 7, nothing — the sentence had sat in a released migration for three sessions naming a requirement that was still a placeholder. The bound half is worth stating precisely: every status change moves `authz_version`, so **no token issued before either transition survives**. What un-revoking restores is the SECRET's usefulness, which revocation never invalidated — a second door the kill switch was assumed to have shut and does not. | 0142 |
| **D504** | `docs/session-09-operator-guide.md` §4 step 1, and every session guide before it: `scp … /tmp/apg.bundle op@…:/tmp/`, then on the host `git fetch /tmp/apg.bundle main && git checkout -B main FETCH_HEAD`. | **The `scp` fails, and the command after it succeeds against the wrong release.** `/tmp/apg.bundle` on the host is owned by **`apg-agent`**, written 2026-08-19 15:50 by Session 8's trip; `/tmp` is `drwxrwxrwt`, so the sticky bit stops `op` overwriting a file it does not own — `scp: dest open "/tmp/apg.bundle": Permission denied`. Measured with a control: `op` writes `/tmp/apg-rig9-probe.txt` fine, and the stale file is byte-for-byte unchanged after the overwrite attempt. **The bundle still sitting there carries `3569caa9`** — a mid-Session-8 commit, *behind* the host's own `3899bcd`. | **Transport under a per-release name**, `/tmp/apg-<sha>.bundle` — which is what Sessions 5 and 6 actually did (`apg-session5.bundle`, `apg-session6-run12f.bundle`; nine of them are still on the host). Step 1 of the guide now derives the name from the sha, and the two accounts' leftovers stop colliding because no two releases share a name. | **The failure is loud and its consequence is silent.** An `scp` that refuses gets read. The next command in the guide is `git fetch /tmp/apg.bundle main && git checkout -B main FETCH_HEAD`, and against the stale file **both halves exit 0** and move the host *backwards* to a previous release. That is the trap CLAUDE.md already names — *"a skipped fetch has already produced one deploy of the previous commit"* — reached by a new road, and the guide's "confirm the sha" line is the only control standing between it and a deploy. **A unique name cannot be silently stale.** | — |
| **D505** | `docs/session-09-operator-guide.md` §4 steps 4 and 5, as written in Run 8: `bin/migrate.sh --project … status` / `up`, and `./deploy.sh --project … --through-session 9`. | **Neither runs as `op`, and the guide it was written from said so.** `bin/migrate.sh:152` refuses every subcommand that runs a container unless `id -u` is 0 — *"'status' requires root: it runs a container"* — and `deploy.sh:231` refuses `--through-session` — *"requires root: it writes host state"*. `docs/session-08-operator-guide.md` carries `sudo` on all three of its migrate lines and on its deploy; the Session 9 guide carries it on none of its six. A Run 8 regression, found by an operator at the terminal on the first command of step 4. | **`sudo` restored on all six lines, with the refusal quoted beside them** so the next reader learns the rule rather than the incantation. Step 2 stays un-`sudo`ed and that is now stated as the contrast: `--render-only` writes only `.generated/`, which is why it is the one step of the trip that `op` can run. | **CLAUDE.md §6 question 3 — whose identity, through which tool?** — asked of a runbook rather than a proof. The guide was assembled from Session 8's, whose §4 was correct, and the privilege boundary is the one detail that does not survive being retyped: it is invisible in the command, lives in the script, and fails only when a human is standing at a prompt with a half-migrated cluster in front of them. **Cheap here because `migrate.sh` refuses loudly and changes nothing.** The same omission on a command that *acted* first would have been D475's ordering defect arriving by accident. | — |

---

## 2. What Session 9 adds to the acceptance registry

**Nothing.** The five requirement IDs already exist and point at placeholders:

| ID | What it must prove |
|---|---|
| `AGT-WRITE-001` | A read-only agent can neither discover nor invoke a write |
| `AGT-AUDIT-001` | Read, write, denied and failed attempts are audited with redaction |
| `AGT-AUDITFAIL-001` | A write fails closed when its audit record cannot be created |
| `SEC-REV-001` | A token issued before revocation is denied on its next read and write through both MCP and PostgREST |
| `SEC-PARAM-001` | Tool parameters cannot override agent identity, role or scope |

**Replace the placeholders; keep the IDs and their descriptions**, rewriting a
description only to a *stricter* statement of the same property (ADR 0096, and
D422 for what that looks like). Adding a new ID requires grepping the registry
first — **ADR 0089/D279**: three of Session 6's six "new" IDs were already taken,
and because `claim_session` derives from `max()`, one would have turned three
earlier sessions' evidence red while the other vanished from the gate.

`SEC-REV-002` is **Session 6's and already green** — non-resurrection through
`authz_version`. `SEC-REV-001` is not a second copy of it: it is about a revoked
token failing its next read *and* write through MCP *and* PostgREST, and Session 6
ships no MCP.

**Claims are a separate act.** Under ADR 0045 a requirement complete in a
checkout is not a claim; every claim needs at least one node id marked
`live_host` or `external`, or `claim_mode` refuses it. Session 9's claims are
registered in `evidence_claims.CLAIMS` in the run that publishes.

---

## 3. Environment feasibility

| Requirement | Status | Note |
|---|---|---|
| The two write operations | **exist and are granted** | Migration 0007, `TO {{authenticated}}, {{agent_writer}}`. D469. |
| `agent_writer` as an assumable role | **one string, plus 0019's grants** | It holds no `EXECUTE` on the hook today. D475. |
| An audit table | **must be built** | Migration 0019. Nothing named `audit` exists in any of the 18 migrations. |
| Connection budget | **no change** | The audit write goes over PostgREST as the caller. D473 keeps D407's considered zero intact. |
| Round trips per audited write | **three, and must be measured** | Context resolution + begin + complete, plus the operation. ADR 0125's round trip *has never been timed against the deployment* — a standing open item that this session makes three times more load-bearing. |
| Memory | **re-check, do not re-measure** | ADR 0131's floor is `128 + share × 4` against a limit of 384. Two extra tools and two extra upstream calls do not obviously move it — but `mcp` containers are now running and healthy, so **reading their resident set is one command**, which is the open item this session can close cheaply. |
| An agent with `notes:write` | **mintable once the ceiling and membership move** | `scope_registry` refuses a scope above the role's ceiling today, which is the control that the ceiling is real. |

**The unmeasured boundary that stays unmeasured:** IPv6. Eight
`APG_PUBLIC_IPV6` proofs have never run, and running them from a machine without
IPv6 reports every port closed — a fact about the scanner.

---

## 4. Safety plan for irreversible operations

Four operations cannot be undone by re-running a command.

**1. Activating `agent_writer`.** `GRANT role TO role` is a bootstrap-plane change
(D102) and widens what a token may name — from "an agent can read its owner's
rows" to "an agent can change them". It requires D475's migration to land
**first**, or the first write token is refused by a privilege error rather than
by the boundary. Reversible in principle, disruptive in practice.

**2. Applying migration 0019.** Forward-only, `freeze-lock` after writing it,
applied as `migration_user` and never as a superuser — **D285**: every offline rig
applies migrations as `psql -U postgres`, and a superuser bypasses the ownership
check that made 0012 and 0013 fail on a real cluster. `RESET ROLE` goes **below**
the privileges block.

**3. Moving `CURRENT_SESSION` to 9.** It is the gate session, so it moves in one
commit with all five placeholder replacements (D484). It arms a `session9`
profile that nothing declares, which is expected (D488).

**4. Publishing a capability lock that contains a write.** The deployed lock is
what the runtime obeys, and from this session it is what decides that an agent
may change a row. A lock compiled from the wrong document produced not an error
but an **artefact** in Session 8 — refused four steps from its cause (D465) — so
`bin/mcp-contract.sh lock --outputs` still reads the **rendered** document and
refuses the deployed one by name.

**The standing rules apply unchanged.** `sudo` needs a TTY, so anything
privileged that mutates is run by a human at a terminal; read-only diagnosis is
not — but **`apg-diag` still cannot read `mcp`'s logs** (D380), which sent an
operator to a terminal twice in Session 7 and again in Session 8's trip.

---

## 5. Build order

Runs are the unit. Each ends with the offline gate green on a clean tree, and
CLAUDE.md §4's procedure applies to every one: measure third-party behaviour with
a **control** before writing anything that depends on it, write the ADR when the
measurement decides something with alternatives, implement, then **try to break
the tests** with a mutation battery whose failures are fatal (D269), whose
control is a test the mutation cannot reach, and which asserts *how* each
mutation failed (D386).

### Run 1 — Migration 0019: the audit record, and the grants `agent_writer` never got — **Done.**

- `app_private.agent_audit`, append-only: no `UPDATE` and no `DELETE` granted to
  any request role.
- `api.agent_audit_begin(...) → uuid` and `api.agent_audit_complete(...)`, both
  `SECURITY DEFINER`, both deriving identity from `app.agent_id` / `app.user_id`
  and **taking no identity parameter** (D473).
- Both reviewed into `contracts/postgrest-api-surface.yaml`'s `agent_rpcs:`
  block, which keeps them **unpublished** — `api_documentation` holds no
  `EXECUTE`, and `openapi-mode = follow-privileges` builds the document as that
  role (ADR 0118).
- **The two write RPCs append their own row in the same transaction when
  `app.agent_id` is set** (D480). `CREATE OR REPLACE` on the same signature so
  0007's grants survive — and the whole body is re-read from 0007 first, because
  **D270** is the rule that a function defined in several files is only ever the
  last definition.
- The grants `agent_writer` is missing: `USAGE ON SCHEMA app_private`, `EXECUTE`
  on `postgrest_pre_request`, `EXECUTE` on **both** comparison helpers (D475,
  D417's rule), and `EXECUTE` on the two audit functions.
- Decide the outputs version once, from the whole surface (D485).

**Measure first.** Whether `app.agent_id` is readable inside a `SECURITY DEFINER`
function invoked through PostgREST — with a control proving the rig can tell a
set GUC from an unset one — and what `INSERT … RETURNING` costs inside the write
RPC's existing transaction. **Grep the plans before measuring**: Session 3
measured how PostgreSQL grants `EXECUTE` on a new function (D57, D262) and
Session 8 measured it again.

**ADRs:** who writes an audit record and why the hook cannot (D473, D474);
`mcp_audit_service` stays unactivated and this is the decision, not the deferral
(D482).

**What was measured.** Two rigs, each with its negative control run **first** —
one expectation inverted, `DIVERGES`, exit 1 — so neither could report success
without having been able to report failure.

*The schema rig*, on the pinned `pgvector:pg18` (PostgreSQL 18.4), every request
made as the authenticator with `SET ROLE`. **Nine arms, nine as designed.** The
hook's `app.agent_id` **is** readable inside a VOLATILE `SECURITY DEFINER`
function in the same transaction; an unset custom GUC reads as the **empty
string**, not NULL, which is why every read is spelled `nullif(current_setting(…),
'')` exactly as 0018 spells it; the definer inserts into a table the caller holds
nothing on and whose schema it cannot USE, while the same caller doing it
directly is **denied** with 42501 and leaves zero rows — the control without
which the first arm would be about a table anybody can write.

**And the arm that changed the design is D489**: a write that `RAISE`s loses its
audit row. `RETURNS api.notes` commits or it does not exist, so a `database` row
records a **committed** change and can record nothing else.

*The PostgREST rig*, live on the locked v14.16 image, and **both predictions were
wrong** (D490). A GET on a VOLATILE function is not refused — it executes and
takes the argument from the query string, so volatility protects nothing. What
refuses these two is that they **write**: `405` / `25006 cannot execute INSERT in
a read-only transaction`, which is D474's mechanism arriving from the other side.
So `agent_rpcs`' `maxItems: 0` keeps its reason and does **not** move, and the
audit functions get a fourth contract section of their own.

**What was built.** ADR 0135 and 0136. Migration **0019** — `app_private.agent_audit`
with a `source` column separating the two records, two enums rather than CHECK
constraints (ADR 0058, ADR 0080), `api.agent_audit_begin` and
`api.agent_audit_complete` taking **no principal**, both write RPCs replaced with
`CREATE OR REPLACE` on the same signature from 0007's text (D270) plus one
conditional INSERT each, and **the grants `agent_writer` never received** —
`grep -c agent_writer` on 0018 returns **zero**. `agent_write_rpcs` in the
reviewed contract, its schema definition, and its validation in `api_surface.py`.

**Four independent anchors noticed the two new functions** and every one was
re-derived to an exact set rather than relaxed (D300): the two `declared_objects`
literals, the reviewed-RPC union, and `test_the_reader_is_not_vacuous` — which
is written out by hand precisely so an empty scrape cannot agree with an empty
contract.

**The battery: 10 mutations, 10 killed**, every one `FAILED` rather than `ERROR`,
each control green in the same invocation, template restored byte-identical.
**M4 is the one to read** — it removes `agent_writer`'s EXECUTE on the hook,
restoring D475's actual defect, and the assertion dies. M3's first form was
scored **INVALID rather than KILLED**: adding a role introduced a placeholder the
manifest does not declare for 0019, so the renderer refused and the *fixture*
broke. That is D386's rule catching a false kill, and the repair was the
mutation.

**And D491 is the near-miss worth reading.** The migration-surface scanner
requires `RETURNS` on its own line; written as `) RETURNS uuid`, its non-greedy
`DOTALL` match ran forward to `create_note` and **swallowed an entire function**,
reporting "agent_audit_complete is missing". The formatting moved, not the shared
regex — and the argument captures were checked afterwards, because a matching
count is not a correct capture.

### Run 2 — Activating `agent_writer` — **Done.**

- One string added to `postgres_bootstrap.AUTHENTICATOR_REQUEST_ROLES`.
- The three assertions that name the role by hand — two in
  `tests/security/test_session3_authorization.py`, one as
  `SESSION_NINE_ROLE` in `tests/contract/test_bootstrap_statements.py` — are
  **re-derived, not relaxed**. The forbidden set is already a complement over the
  project's own roles (ADR 0116), so the negative half moves for free; **the
  subset check stays refused** (D300, which arrived three times in one session).
- One independent anchor survives, because a set derived entirely from the
  product cannot refuse a bad edit to the product. `mcp_audit_service` is the
  natural candidate now that `agent_writer` is no longer available for the job.
- `agent_writer`'s ceiling gains `meta:read` (D481).

**ADR:** the ceiling amendment to ADR 0079's table.

**What was measured — nothing new, and that is the correct answer.** Both halves
are decisions about this repository's own constants, not about a third party, so
there was no third-party behaviour to put a control around. What Run 2 did
instead was ask §6 question 5 — *which of this decision's callers got it?* — and
that found the run's real work.

**D492 is what it found.** `test_the_authenticator_cannot_become_an_agent_role`
had been asserting a property the product lost in **Session 8**: it named both
agent roles as unassumable, and `agent_reader` has been assumable since Run 2 of
that session. It stayed green because its fixture granted a hardcoded list of
four request roles omitting both — the fixture manufacturing the condition the
test measured. Its docstring's other premise had expired too: migration 0018's
`token_use` branch is exactly the path it said could not exist.

**What was built.** ADR 0137 and 0138. `agent_writer` in
`AUTHENTICATOR_REQUEST_ROLES` — **six request roles**, with 0019 already landed,
because the other order refuses a request by `permission denied` rather than by
the boundary (D475, D417). The ceiling gains `meta:read`, so a write agent can
ask which rows it may change rather than discovering the surface by probing it.

**Both anchors moved to `mcp_audit_service`, and that is the ADR's real subject.**
`SESSION_NINE_ROLE` named a role a later session was *expected* to activate, so
its correct edit on arrival was deletion — leaving the derived set unanchored at
exactly the moment the constant changed. **An anchor that expires is not an
anchor.** `mcp_audit_service` is wrong in every session, which is what an anchor
has to be.

**And one new comparison with teeth**: the roles granted `EXECUTE` on the hook,
read from the catalog with `aclexplode`, must **equal** the request-role set —
two independent products rather than one read twice. Dropping `agent_writer` from
the constant now fails against the catalog.

**The battery: 5 mutations, 5 killed**, every one `FAILED` rather than `ERROR`,
controls green in the same invocation, restore byte-identical. **M5 is the one to
read, and its first form SURVIVED** (D493): `==` → `>=` could not discriminate,
because every comparison operator agrees while the two sets are equal. The
mutation was replaced, not the test — it became a two-file mutation granting the
hook to a role no token can name, which is the asymmetric state exactness is
about.

### Run 3 — The compiler learns to write — **Done.**

- Two `kind: write` capabilities in `capabilities.example.yaml`, each one-to-one
  with its operation, `max_affected_rows: 1` (D487), `idempotent` stated
  honestly — `create_note` is not, `update_task_status` is, because it is a
  compare-and-swap — and a **non-empty** `audit.redact` on at least one (D479).
- `_compile_tool` gains a write branch: an operation, an argument contract, a
  `max_affected_rows`, and no `columns`/`filters`/`order_by`/`max_rows` (D470).
- `max_affected_rows`, `idempotent` and `audit.redact` reach the lock.
- The canonical snapshot is recompiled; `bin/mcp-contract.sh check` compares it
  byte for byte and **contains no writer**.
- `bin/render-mcp-catalog.py` gains a write rendering path — today it emits a
  detail section only for a tool with `resources`, so a write tool would render
  as a bare table row.
- `docs/mcp-tool-catalog.md`'s "No writes" paragraph is rewritten, and the "what
  is deliberately absent" section is Session 10's inbox.

**The AGT-DRIFT-001 discipline holds**: adding an operation to the reviewed
surface and the approved snapshot must still expose no capability, and the test
is written the only way that means anything — by adding a real one and asserting
the compiled bytes do not move.

**What Run 3 built.** All of the above, as planned: two `kind: write` entries
(`create_note` not idempotent with `audit.redact: [p_content]`,
`update_task_status` idempotent as a compare-and-swap, both `max_affected_rows:
1` per D487); `_compile_tool` split into `_compile_resource` and
`_compile_write` — a write tool carries `operation`, `arguments` (the reviewed
contract's list **in parameter order**), `required_scopes`,
`max_affected_rows`, `idempotent`, and none of the read shape; **every** tool
now carries `audit_redact` (the union over its backing capabilities), which is
what puts D479's orphan into the lock; `surface_operations` carries each
operation's `arguments` through. Three new compiler refusals: a write carrying
any of the five read-shape fields (the schema deliberately does not forbid
them — D403), a write backed by a non-POST operation, and a write naming an
unbacked source. The canonical snapshot recompiled to **6 tools / 7
capabilities**; `render-mcp-catalog.py` gained the write detail section; the
catalog's prose was rewritten where the tripwire test demanded it, "No writes"
left the deliberately-absent list (and a test asserts it stays gone), and the
audit-retention line points at Session 10.

**What was measured.** Nothing third-party — compilation is pure over committed
inputs, and D487's single-composite-row premise was Run 1's measurement. The
run's one rig was D494's probe-and-control (a leaked
`fastmcp.server.dependencies.get_access_token` stub, found because Run 3's
first targeted test run used a non-canonical module order). Battery: **M1–M9
all killed** — redaction key, bound, argument order, idempotency, the three new
refusals, the renderer's write branch, and the repaired concurrency stub — each
with a paired control green in the same invocation.

### Run 4 — The lock and the write transport — **Done.**

- `mcp_lock.WRITE_TOOLS`; `EXPECTED_TOOL_NAMES` re-derived to six; `_tool()`'s
  two kind assertions gain a third arm; a seventh tool still fails the start
  (D486).
- `UpstreamRequest` gains a body; `mcp_upstream.execute` sends it instead of
  `b"{}"`; `build_request` gains a write branch emitting no `select` and no
  `limit` (D477).
- Arguments are validated **by name against the lock's declared argument list**
  and by type — the same shape `mcp_query` already uses for a filter column
  against a frozen allowlist. A caller supplies values, never names.
- `max_affected_rows` is checked against the response, never trusted.
- `mcp_errors.CALLER_FACING_TOKENS` gains what a write refusal needs; it is a
  closed tuple and `AgentVisible.__init__` raises on anything outside it.

**Measure first.** What the locked PostgREST returns for an RPC POST with a
JSON body — status, shape, and what a `Prefer` header does or does not change —
against a live service, with a control. **D438 is the standing warning**: both
obvious answers about escaping an `in` member matched zero rows, and only
measurement said so.

**What was measured (rig4** — the locked v14.16 against the pinned pg18, arms
mirroring 0019's shapes, negative control run first and it failed as designed):
a non-SETOF composite RPC returns **a single JSON object** where a SETOF
control returns an array; `Prefer: return=minimal` changes **nothing** on an
RPC POST and `count=exact` adds only headers, so the header allowlist keeps its
reason; **status alone cannot classify a write refusal** — a missing and an
extra argument are both `404 PGRST202`, the same status as the product's own
`404 PT404` with the opposite meaning; the product's PT errcodes cross HTTP as
their status with the errcode in the body's `code`; a `22P02` message **names
the schema's enum type**; a JSON number where the function takes text is
coerced. **ADR 0139** is the decision the ambiguity forced: write refusals are
**translated from the product's own enumerated errcodes** — `PT409` →
`write_conflict`, `PT404` → `row_not_found`, `PT422` → `input_not_permitted`,
sentences this repository's own — and everything else, `PT401` included, stays
masked. A test compares the map's keys against the errcodes the migration
template actually raises.

**What was built.** `WRITE_TOOLS` beside the other two tuples, `EXPECTED_KINDS`
so a lock cannot re-kind a reviewed name, `WriteSpec` parsed strictly (D470's
shape at load: no resources, POST only, a bound ≥ 1, arguments in parameter
order), and `Tool.audit_redact` parsed for Run 6. `UpstreamRequest.body` built
by `mcp_query` — `build_write_request` is the write branch: a JSON argument
document, an empty query string, names checked in both directions before the
dial. `mcp_upstream._dial` is the one shared transport; `execute_write` parses
the measured single-object shape, checks the bound against the response, and
translates refusals via `mcp_errors.write_refusal`. `mcp_tools.TOOL_NAMES`
stays the four registered tools with an exact-gap test — the gap between it and
the roster must equal `WRITE_TOOLS` precisely, restored to equality in Run 5
(the `live_host` four-tool assertions in `test_session8_agent_plane.py` also
move in Run 5, with registration). Battery: **W1–W11 all killed**, each with a
green control in the same invocation.

### Run 5 — The two write tools, and discovery that filters names

- `create_note` and `update_task_status` registered with explicit `name=`,
  through `bounded()`, taking a concurrency slot because they reach upstream.
- **An `on_list_tools` hook, and `discoverable_by`'s first production caller**
  (D476). The context is already resolved once per HTTP request before both
  discovery and execution, so nothing about ADR 0125 moves.
- Both levels proved separately: a tool **name** hidden from a caller without its
  scope set, and a **resource** hidden behind a visible name.
- `AGT-WRITE-001`: a read-only agent can neither list nor call either write.

**Done.** Both writes registered through `bounded()`, exposing the lock's own
argument names in parameter order and every one required — a caller supplies a
value for each declared argument, because a missing one is a `404 PGRST202`
upstream (rig4). `invoke_write` is one body for both, parameterised by the
roster's name and never a caller's. `mcp_tools.TOOL_NAMES` is **six** and the
equality with `EXPECTED_TOOL_NAMES` is restored, still as two lists rather than
one read twice. **`ToolVisibilityMiddleware` is the third wired framework
object** and `discoverable_by`'s first production caller (D476).

**Measured (rig5, FastMCP 3.4.0, four arms each with a control that fails):**
**M1** a filtered `on_list_tools` removes the name, the unfiltered control shows
both; **M2 — a hidden tool is still CALLABLE and it runs**, so filtering
discovery is disclosure control and the call-time scope check is the boundary;
**M3** the context `on_request` sets is visible in `on_list_tools`, measured over
a real HTTP transport (not the in-memory client, which never reaches
`on_request`), with a control that saw `None`; **M4** `FastMCP.list_tools()` runs
the middleware chain, so the offline pipeline test measures the filter rather
than registration.

**Three divergences, and D495 is the one to read:** `bounded()`'s `resource is
None` was carrying two ideas and a write is the first caller that separates them
— D463's shape, and it would have put both writes unbounded on the event loop.
**D496**: the plan's "four-tool assertions move to six" cannot hold, because
`tool_count` (six, what the deployment serves) and a caller's `tools/list`
(three, for the read-only probe agent) are now different questions. **D497**:
`MAX_SERIALIZED_BYTES` had no caller on the write path (§6 question 5).

**ADR 0140.** Battery: **W12–W22, 11 of 11 killed**, every one `FAILED` rather
than `ERROR` (D386), each with a green control in the same invocation — and the
two mirror arms are the ADR's claim: inverting the call-time scope check leaves
the name filter green, and disabling the name filter leaves the call-time
refusal green.

### Run 6 — The request ID and the audit lifecycle

- The id is minted in `AgentContextMiddleware.on_request`, carried on `_Held`,
  read through an accessor beside `current_agent_context()`, and reset in the
  same `finally`.
- Added to `mcp_telemetry.RECORD_FIELDS` — whose `as_dict` raises if the record
  shape and the tuple disagree — and passed to both audit calls.
- Forwarded upstream: `FORWARDED_HEADERS` gains it **and** `execute`'s equality
  guard moves in the same commit (D477).
- `bounded()` gains its fourth job: begin before the work, complete after, with
  outcome, elapsed ms and parameters redacted per the lock. **Writes fail closed;
  reads do not, and the asymmetry is the ADR** (D483).
- The canary constraints hold unchanged: no token, no fingerprint, no URL, no
  caller value in a telemetry record, and the sink allowlist tests still pass.
- `AGT-AUDIT-001` and `AGT-AUDITFAIL-001`.

**ADR:** what fails closed and what does not, with the measurement in hand.

**Done.** The id is minted in `on_request`, rides on `_Held`, is read through
`current_request_id()` beside `current_agent_context()`, and is reset by the same
`finally`. `RECORD_FIELDS` gained it and the canary's list did not — it is this
plane's own mint and nothing reads one off an inbound header, so it cannot carry
a caller value. `FORWARDED_HEADERS` went two → three **and `_dial`'s equality
guard moved in the same commit** (D477); it stays an equality (D300).
`mcp_audit.py` is new: two paths as module constants, `redact` (D479's orphan,
consumed at last), and `begin`/`complete` through the one shared `_dial`.

**`bounded()` gained its fourth job, and `upstream: bool` became `kind`** — one
vocabulary with three NAMED consequences (`UPSTREAM_KINDS`, `AUDITED_KINDS`,
`FAIL_CLOSED_KINDS`), each with its reason at the definition. That is not D495
repeated: there the correlation was an *accident* of representation; here it is
the lock's own classification, already checked against `EXPECTED_KINDS` at load.

**Measured (rig6, PostgREST v14.16 + the pinned pgvector image, negative control
first).** **The rig was wrong first, and instructively**: it set the agent
identity with `ALTER ROLE rig_anon SET app.agent_id = …` and every `begin` arm
returned `403 PT403` — **a role-level setting is applied at LOGIN**, and
PostgREST logs in as the authenticator and switches role per request, so a
setting on the switched-to role never applies. Moved to a pre-request hook, which
is what production uses. Then: a non-SETOF **scalar** return is a **bare JSON
scalar** (`RETURNS uuid` → a string; the SETOF contrast is an array) — **rig4's
composite finding is not evidence for it**; `RETURNS boolean` is a bare
`true`/`false` and closing an already-closed record is **200 false**, never an
error; a defaulted `jsonb` argument may be omitted or sent as explicit `null`;
`committed` is refused **422/PT422** and a missing identity is **403/PT403**; **a
custom request header DOES reach the database** in
`current_setting('request.headers')` (present when sent, absent when not); and
three `started` rows survived the run, so each RPC call is its own transaction
and commits before the next — D489 arriving from the other side.

**Three divergences, and D498 is the one to read**: the id's propagation was
proved and its **uniqueness was not**, because every offline test arranges a
fixed id — a mutation replacing `uuid4()` with a constant left the whole suite
green. **D499**: two battery arms reported a false survivor because the control
called the mutated function — CLAUDE.md's named rule, third instance.
**D500**: the `database` row carries no `request_id`, so the two records join by
agent, tool and time; the header measurement makes the repair look cheap and the
release control makes it a **migration 0020**.

**ADR 0141.** New live module `tests/deployment/test_session9_agent_writes.py`
with its own `agent_writer` fixture — the two-record proof cannot exist offline.
Battery: **A1–A16, 16 of 16 killed** after the two repairs, every one `FAILED`
rather than `ERROR` (D386), each with a green control in the same invocation —
and A9/A10 are mirror arms, so the fail-closed asymmetry is proved in both
directions rather than asserted once.

### Run 7 — The admin audit endpoint, and revocation proved rather than built

**Done.**

`GET /admin/audit` exists, with the four pieces in that order and a fifth thing
the plan did not anticipate: **migration 0020**. 0019 built two indexes for a
reader it never created and granted `auth_service` nothing, so the endpoint had
no statement it was allowed to send (**D501**, ADR 0142). The reader is
`app_private.auth_list_agent_audit` — `STABLE SECURITY DEFINER`, granted to
`auth_service` and to nobody else, because the table's own `COMMENT` forbids a
`SELECT` grant. **Two migrations are now released and applied on no cluster.**

`admin_audit:read` is in the schema's two enums and in **`project_admin`'s
ceiling alone** — not `admin_agents:read` reused, because listing which agents
exist and reading what they did are different authorities. There is no `:write`
twin and a test asserts the absence: the table is append-only, so the name would
be an authority nothing can exercise.

**The bound on `limit` has one authority and it is the route** — 422 outside
`[1, 500]`, never a clamp; 0020 applies `p_limit` and does not restate it
(D495, D463).

`GET /admin/audit` is the service's first query-string endpoint, so rig7 asked
of a query string what `routes.py` had already measured of a body. **`limit=1&
limit=9999` resolves to `9999`, silently** — but unlike a JSON body the
duplicate survives in `multi_items()`, so it can be refused rather than mourned
(**D502**, ADR 0143). `strict_query` refuses a repeat, an unknown name and an
empty value; the document's `parameters` are declared by hand because FastAPI's
binding would inherit the defect, and a contract test compares the two halves
because that hand-declaration is D274's shape waiting to happen.

**`SEC-REV-001` is proved and not built** (D471, D472). The database half runs
`PATCH /admin/agents/{id}` — the product's own route — captures the agent's
claims while it is active and replays them unchanged afterwards, and the hook
refuses with `AP401`; the positive arm runs first, so a hook that refused
everything cannot pass. The MCP half is in
`tests/security/test_session9_revocation.py`: a revoked agent's context cannot
be resolved, no upstream status becomes a degraded mode, and a read and a write
lose their context together. **The one-token-three-requests arm is live-host and
the module says so**, because a session that half-closes a requirement without
saying which half is which leaves the next reader unable to tell a proved
guarantee from a plausible one (D478, applied to this session's own claim).

**And proving it found D503**: `revoked → active` answers **200**. 0011's
comment says revocation is *terminal* and names `SEC-REV-001` as its proof, and
`auth_set_agent_status` is an unguarded `UPDATE`. Recorded, not repaired — the
test asserts what the product does and fails the day a guard lands. The bound
half: `authz_version` moves on every transition, so no token survives either
way; what un-revoking restores is the secret.

`SEC-PARAM-001` is asserted as an **absence**, in three places: no write tool's
compiled arguments name a principal (read from the committed snapshot, not
re-compiled — D277), neither audit function's `CREATE FUNCTION` header does, and
`GET /admin/audit`'s filters are named as **not** a counterexample — there the
caller is already authorized to read the whole record, so a filter narrows a
permitted read rather than authorizing one.

**ADR 0136's owed proof now exists.** A `GET` against the deployed
`agent_audit_begin` must answer **405** with `25006`, with a POST control first
and a separate arm asserting the refused GET wrote nothing. It is live-host and
runs on the trip.

**Two corrections the run made to itself**, both cases of asserting a property
the product does not claim: `UpstreamRefusal.reason` *does* name the upstream
status, and that is not a D433 violation because it is a plain `Exception` and
ADR 0130's mask is what keeps it off the wire — the useful assertion is that the
upstream *body's* detail never enters it and that the type is the masked one.
And `aclexplode(proacl)` reports a function's OWNER as a grantee, so the
grant-equality subtracts the owner rather than expecting it.

**Battery: A1-A7, 7 of 7 killed** after two repairs, every one `FAILED` rather
than `ERROR` (D386) and every control green in the same invocation. Both repairs
were found by the battery's own machinery and neither weakened a test:

* **A6 was a FALSE KILL on the first run** and the outcome check caught it —
  target and control both `ERROR`, not `FAILED`. The mutation added
  `{{agent_reader}}` to 0020's grant, and 0020's manifest entry does not list
  that placeholder, so the **renderer** hard-failed on residue and nothing about
  the grant was measured. A battery reading only "did the target go red" would
  have scored it KILLED and reported a grant assertion it never exercised. The
  arm is now a two-file mutation, which is what a real change would have to be.
  Its manifest anchor then matched **three** times — three migrations declare the
  same placeholder pair — and pre-flight caught that in one second (CLAUDE.md §1).
* **A7 SURVIVED**, and the repair is the TEST. Dropping `, r.id DESC` left the
  tiebreak assertion green: three rows sharing `started_at` still come back in a
  consistent prefix order, because PostgreSQL's sort is deterministic for an
  input that small. **The behavioural half cannot discriminate the tiebreak** —
  a test passing for a reason unrelated to its name. The migration is right, so
  the behavioural half is kept (it still catches unordered or newest-last) and a
  structural half is added beside it, reading `pg_get_functiondef` from the
  **deployed** function. ADR 0134's division applied to an ordering.

**And the battery caught a third thing before it ran.** Designing an arm against
`AUDIT_LIMIT_MAX` showed that `test_the_documented_limit_range_is_the_enforced_one`
compared the document's `maximum` to the constant the document is *generated
from* — two constants that move together, so a route documenting 500 and
enforcing a literal 100 passed. CLAUDE.md §6 names it. Split in two: the offline
test asserts what a document alone can be wrong about (its own coherence), and a
cluster arm sends the **advertised** boundary and one past it, so the published
bound and the enforced bound are compared through a real request.

**ADRs 0142 and 0143. Divergences D501, D502, D503. Next free: D504, 0144.**

### Run 8 — Publish

**Done.**

`CURRENT_SESSION` is **9**, all five registry entries point at real tests, and
**both placeholder modules are deleted** — `tests/integration/test_future_mcp.py`
and `tests/security/test_future_security_boundaries.py` each carried nothing but
Session 9's markers, so activating the five emptied them. Verified with
`APG_ACCEPTANCE_SESSION=9` first, which named exactly the five D484 predicted.
`docs/threat-model.md`'s `THR-AGENT-TOKEN` row named a deleted node id directly
and moved with it.

**The outputs version does NOT move.** No commit in Session 9 touched
`output_migrations.py` or `outputs.schema.json`, and `tool_count` 4 → 6 is a
value rather than a shape — which is D485's own rule, applied rather than
re-litigated.

**Five claims, one per requirement**, and the two audit ones are split because
they are different guarantees: what is recorded, and what happens when recording
is impossible (ADR 0141's asymmetry). `agent_revocation` is deliberately NOT
extended into Session 6's `token_non_resurrection` — that would move
`claim_session` and drop the claim out of this gate silently, which is the exact
failure D279 measured.

**Two tests were written because the claims needed them, not the other way
round**, and both would otherwise have been claims that read as
deployment-measured while their central property was not:

* **`AGT-AUDITFAIL-001` had only offline proofs.** ADR 0141's asymmetry had never
  been seen on a cluster. The live arm withdraws `EXECUTE` on
  `api.agent_audit_begin` from the writer role inside the project lock, attempts
  a write, and asserts the absence of the ROW rather than the shape of the
  refusal — a tool that errored after committing would satisfy any assertion
  about the response. The read arm beside it is the strongest possible control:
  same failure, same cluster, same token, opposite outcome. The grant is restored
  in a `finally` and the restore is *checked* (D391), and the operator guide says
  what to run if a killed gate leaves it withdrawn.
* **`SEC-REV-001`'s live arm did not exist.** Run 7 named it as live-host and
  deferred it here; registering a claim against a test nobody had written is
  D211–D214's shape. It mints a token, proves all three paths work, revokes
  through `PATCH /admin/agents/{id}`, and replays the same unchanged token
  against its next MCP read, its next MCP write and its next direct PostgREST
  request.

**`bin/session-09-check.sh` keeps THREE modes, and that was checked rather than
assumed.** All five of Session 9's own claims resolve to `host` — but
`claims_through_session(9)` is cumulative, so a Session 9 document must answer
for five *external* claims inherited from Sessions 4–8, `public_agent_boundary`
among them, and the writer refuses a document silent about a claim. A two-mode
gate would have written one quietly.

Its session-specific precondition is **`check_the_audit_plane_is_migrated`**: it
reads each cluster's own ledger and refuses if any released migration is missing,
because without it thirteen proofs fail as a wall of `relation
"app_private.agent_audit" does not exist` and the operator reconstructs one fact
from it. It asks the CLUSTER rather than a manifest — `migrate.sh status` needs a
gitignored host-only input this gate does not take, and the question is what was
*applied*, not what was asked for. `--ssh-destination` is documented as `op@`
(D466) inside the usage command (D213), and the copy is checked for `session-08`
residue afterwards, because D221 is a rename that did not match.

**Battery B1–B4, 4 of 4 killed** after one repair, every one `FAILED` rather than
`ERROR` and every control green in the same invocation. **B3 survived first, and
the mutation was wrong rather than the test**: `claim_session` is the MAX of its
requirements' sessions, so *adding* an earlier id changes nothing and the
assertion was right to pass. The direction that hurts is downward — naming the
earlier id *instead* — which is the substitution D279 caught being made for real,
and the arm now does that. Three of the four target names were guessed and did
not exist; grepping for them first is the cheap version of the anchor pre-flight.

`docs/session-09-operator-guide.md` is written, and it carries the ordering this
trip turns on: **migrations before the deploy**, because 0019 grants the
privileges and the bootstrap plane grants the membership, and the wrong order
produces a `42501` where the boundary's own `AP401` belongs (D475). It also
names D503 under the kill switch, so an operator is not surprised that
un-revoking answers 200.

### Runs 9+ — The host trip

Transport by `git bundle` + `scp`; **read the `release <sha>` line and confirm it
is the sha you fetched**. Then, in order:

- **Re-render all four projects on the host**, not two, and not on the
  workstation (D462, D383 — `.generated/` is gitignored and never transported).
- **Sync the host venv before the gate** (D384, D297 — three times now).
- Migrate both clusters with `migrate.sh --project`, naming the manifest.
- **Deploy twice** if a route or a document field is newly published (D326).
- Run `session-09-check.sh` in all three modes; merge both halves against the
  same release or the merge refuses, correctly.

**Budget three to four more runs than this list.** Session 8 was planned as nine
and took twelve; Session 7 as ten and took sixteen. **Not one of the seven
defects Session 8's trip found was visible to a green offline suite of 3,786
tests.**

---

## 6. The MCP surface

Six tools, and no MCP resources, prompts, roots, sampling, elicitation or UI.

| Tool | Kind | Reaches | Scopes |
|---|---|---|---|
| `list_resources` | metadata | the deployed lock | `meta:read` |
| `describe_resource` | metadata | the deployed lock | `meta:read` |
| `query_resource` | read | PostgREST, structured | `notes:read` or `tasks:read` |
| `run_report` | read | one named RPC | `notes:read`, `tasks:read` |
| `create_note` | **write** | one named RPC, one-to-one | `notes:write` |
| `update_task_status` | **write** | one named RPC, one-to-one | `tasks:write` |

**What a write cannot accept**, structurally rather than by validation: SQL, a
SQL fragment, a PostgREST query string, a path, an operation name, an argument
name the lock does not declare, an owner, an agent id, a role, a scope, or a
row count above `max_affected_rows`.

**What a tool result never carries:** a token, an object key, a presigned URL, a
connection string, another agent's existence, an audit row belonging to anyone
else, or a row the caller's RLS would not have returned.

**No storage.** `objects:read` and `objects:write` are human-only and the scope
vocabulary does not admit them for an agent, so no agent token can carry them
however it is minted (ADR 0100). Adding a write plane does not change that.

---

## 7. Evidence and claims

Unchanged: a claim's verdict is computed from the registry's node ids and JUnit
results, never hand-entered, and **a skip is not a pass**. Host and external
halves are written separately and merged by
`bin/write-session-evidence.py --session 9`.

**Both halves must describe the same release** or the merge refuses — Session 7
proved that the hard way, and was right to. `evidence/*` is gitignored by design.

**The two inherited red claims are Session 5's.** Session 9 does not close them
and must not appear to. If the rotation window is held during this session, it
closes them and the plan says so; if it is not, Session 9's evidence carries them
red for the same stated reason. **This is the third session to close on that
sentence**, and it stays true until the window is held.

**`OPS-LOG-001` is Session 11's and Session 9 does not close it.** Session 9's
request id spans MCP → PostgREST → audit record; `OPS-LOG-001` spans ingress →
API → agent → audit. A session that half-closes another's requirement without
saying so leaves the next reader unable to tell a proved guarantee from a
plausible one (D478).

---

## 8. Security invariant matrix

| Invariant | Control | Proof |
|---|---|---|
| A read-only agent cannot discover a write | `tools/list` filtered by `discoverable_by` | `AGT-WRITE-001` — the name is absent |
| A read-only agent cannot invoke a write | `_resource_for`'s scope check at call time | `AGT-WRITE-001` — refused, not merely hidden |
| An agent write touches only its owner's rows | RLS keyed on `app.user_id`, set to the owner | No policy moves (ADR 0117) |
| A write is bounded | `max_affected_rows`, checked against the response | `AGT-WRITE-001` |
| An agent cannot run SQL | No input accepts one; the compiler cannot emit one | `AGT-SQL-001`, still green |
| Every outcome is recorded | Begin before, complete after, both required | `AGT-AUDIT-001` |
| An unauditable write does not happen | Begin fails ⇒ the call is refused | `AGT-AUDITFAIL-001` |
| A write cannot be routed around the record | The RPC writes its own row in the same transaction | `AGT-AUDIT-001`'s direct-PostgREST arm |
| Parameters cannot name a principal | The audit functions take no identity argument | `SEC-PARAM-001` |
| A revoked token stops on its next request | `agent_claims_are_current`, per request | `SEC-REV-001`, through MCP and PostgREST |
| An audit record carries no secret | `audit.redact`, from the lock | `AGT-AUDIT-001` |
| MCP still holds no database credential | `FORBIDDEN_VARIABLES["mcp"]`, `McpSettings`' shape | The budget arithmetic test, unchanged |
| A seventh tool fails offline | `EXPECTED_TOOL_NAMES`, before registration | A contract test, re-derived to six |

---

## 9. Risks and stop conditions

**Stop and ask** rather than proceeding, when:

- activating `agent_writer` would require relaxing rather than re-deriving an
  assertion, or turning an equality into a subset check;
- the audit record would need a field that is a caller value, a token or a URL;
- a write tool needs an argument the reviewed surface contract does not name;
- making a read fail closed looks like the tidy answer to an inconvenient test;
- `--render-only` stops working with no host and no root;
- a Session 1–8 claim goes red and the fix would weaken a passing test.

**The failure mode this session is most exposed to** is the one this project
keeps producing: *a value that looked measured and was not.* Session 9 adds a
write path, a second and third upstream call per request, an identifier that must
survive three hops, and a record whose whole value is that it is complete.
Every one is a place where a plausible wrong answer passes for exactly as long as
nobody asks.

The five standing questions:

1. What would have to break for this test to go red?
2. Has it run at all, in this environment, since the thing it measures changed?
3. Whose identity, and through which tool, does the proof run — and are they the
   ones production uses?
4. When a defect class was fixed, **which side got the fix** — product or proof?
5. When a decision is implemented, **which of its callers got it?**

**Question 5 wrote three of this plan's rows before a line of code was
touched** — D475 (five roles granted the hook and a sixth about to exist), D476
(`discoverable_by` compiled, tested and called by nothing) and D479
(`audit.redact` validated and consumed by nothing). It caught five defects in
Session 7 and D454 in Session 8. **Ask it at every boundary this session adds.**

---

## 10. Open items carried in

- **The rotation window.** Still the only thing keeping two Session 5 claims red.
- **The signing-key cutover** (ADR 0088). Unblocked since Session 6, and there are
  **four verifiers** now (ADR 0113, ADR 0122). `render-jwks` still prints *"the
  key set CHANGED"* on every deploy (D296).
- **Nothing knows which proofs have never executed** (D211–D214). **Five sessions,
  still unbuilt**, and Session 8 paid again: three assertions in the first host
  gate had never run.
- **The agent plane's round trip has never been timed against the deployment.**
  ADR 0125's deliberate price — and **Run 6 made it four for a write**: context,
  `agent_audit_begin`, the write, `agent_audit_complete`. Three for a read; the
  two metadata tools still make none (ADR 0141). Every one of the four holds a
  PostgREST connection while it runs, and the concurrency bound is a share of
  that pool (ADR 0129), so the cost is on a resource this plane already shares
  with human callers. **Nothing has timed any of them**, and the number of them
  is now the thing most worth timing.
- **The `database`-source audit row carries no `request_id`** (D500). The two
  records for one MCP write join by agent, tool and time. The repair is measured
  and cheap-looking — rig6 showed a forwarded header reaching
  `current_setting('request.headers')` — and is a **migration 0020**, because
  0019 is released.
- **`MCP_MEMORY_LIMIT` is measured for the interpreter, not the container.**
  `mcp` containers are now running and healthy, so reading their resident set is
  one command. §3 says so; nothing forces it.
- **`apg-diag` cannot read the agent plane's logs** (D380). Third service it
  cannot see; it sent an operator to a terminal in Sessions 7 and 8.
- **`test_no_operator_command_puts_a_service_directory_on_the_path` is a text
  scan** (D464). Two strings standing in for a construct. Whoever next touches
  that file owns the decision.
- **The `--ssh-destination` account is not derivable** (D466). The guide names
  `op@`; nothing checks it.
- **`tests/deployment/conftest.py` is past 2,100 lines.** Session 8 put its
  fixtures in the test module instead, which helps the next module and not this
  file. Session 9 should do the same.
- `requirements-dev.in` pins nothing; it has produced a red gate five times.
- **D387** — the REST document observation does not retry; hit twice in one trip.
- **D394** — an sshd deviation that would not reproduce, and the check discards
  `sshd -T`'s output so a one-off leaves nothing to diagnose.
- ADR 0060: the REST document advertises DELETE, PATCH and POST on both views and
  all three return 403 — and an agent now reads that document with a write scope.

---

## 11. Session 10 handoff

Session 10 receives an activated `agent_writer`, two write tools that are
one-to-one with reviewed operations, a durable audit record with a stated
fail-closed contract, a request id that survives from the agent plane to the
database, and a revocation proved through both surfaces on a live deployment.

**Two things about the id are narrower than that sentence** and are written down
here so the next reader does not have to find out: it reaches the **agent-plane**
row and not the **database** one (D500, a migration 0020), and it spans MCP →
PostgREST → the record and **not ingress** — that is `OPS-LOG-001`, Session 11's,
and Session 9 does not close it (D478).

Session 10 is **backup, WAL archiving, PITR and the restore drill**. It **must
not** treat a successful backup as a proved recovery, mount or mutate the active
database volume in a restore path, or record a recovery time it did not measure.
Its five requirement IDs — `REC-PITR-001`, `REC-SAFE-001`, `REC-SMOKE-001`,
`REC-EVID-001`, `REC-WAL-001` — already exist as placeholders in
`tests/recovery/test_future_pitr.py`.

**And it inherits one thing this session creates:** a table that grows without
bound. `app_private.agent_audit` has no retention policy, and secret generations
already accumulate with nothing pruning them.

---

## Appendix — what to consult, and what to measure instead

**Consult:** `docs/decisions/README.md` (134 ADRs, indexed) — for this session
especially **0116** (`agent_writer` is Session 9's, and the forbidden set is a
complement), **0117** (an agent runs under its owner's identity; no RLS policy
moved), **0118** (a reviewed and unpublished RPC), **0119/0120** (derived
operation ids; a tool may be backed by more than one capability), **0125** (the
caller's own token, context once per request), **0127** (a caller value is a
value), **0129/0130** (budgets, and what a caller may be told), **0134** (a grant
assertion reads the catalog; a reach assertion sets the role). Behind them: 0003
(the frozen domain), 0045/0089 (what a claim is), 0065/0066 (a proof takes the
product's route), 0079/0100 (the closed scope vocabulary).
`docs/capability-plan.md` for the two tools. `docs/mcp-tool-catalog.md`'s "what
is deliberately absent". §1 of this document.
`docs/plans/session-08-implementation-plan.md` §1 rows D395–D468 and §5 runs
10–12, which are what one host trip costs.

**Measure instead of consulting**, every time: what PostgREST does with an RPC
body, what a header does to a route, whether a GUC is visible inside a definer
function, what a container holds, and whether a proof has ever run.

**Before measuring how a third party behaves, grep the plans for it.** Session 8
Run 8 measured how PostgreSQL grants `EXECUTE` on a new function; Session 3 had
measured it three sessions earlier in more detail (D57, D262). Every ADR is
indexed; **nothing indexes the ~470 measured facts in the divergence tables by
subject**, so the pointer has to be a `grep`.

**Never write a measurement you did not run** (D267).
