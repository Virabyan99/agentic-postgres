# Session 8 — The agent plane

One remote MCP read surface at the manifest-derived `/mcp` route, reachable only
by an agent token, authorised by the same PostgREST path a human uses, exposing
exactly the four tools `docs/capability-plan.md` has named since Session 1.

**No second database API. No second authorization system. No SQL.**

---

## 0. Where Session 8 actually starts

Session 7 closed with `evidence/session-07.json`: **33 claims passed, 2 failed**,
the two red ones Session 5's and blocked on the rotation window. Both projects
run `3569caa` with 17 migrations, `max_connections` 56, outputs v11, and a
working object-storage plane.

The runbook this plan rewrites was written against a repository that does not
exist. Its numbers are off by whole sessions — migration `0013`, outputs `v8`,
capabilities `schema_version: 2` — and, more importantly, several of its
*contracts* were superseded by what Sessions 3–7 actually built. **§1 is the
list, and it is the point of this document.**

Three things are already true and change the shape of the work:

1. **The four tools and their scopes are already written down**, in
   `docs/capability-plan.md`, with the real scope names. Session 8 implements a
   plan, it does not invent one.
2. **The five `AGT-*` requirement IDs already exist** in
   `tests/acceptance-registry.yaml`, pointing at placeholders in
   `tests/integration/test_future_mcp.py`. Session 8 **replaces** them.
3. **`capabilities.schema.json` v1 already carries the full capability shape** —
   `name, kind, enabled, required_scopes, operation, resource, columns, filters,
   order_by, max_rows, max_affected_rows, idempotent, timeout_ms, audit`.

Session 7 was planned as ten runs and took sixteen, because the host trip found
eight defects. **Plan for the same.**

---

## 1. Runbook divergences

Six columns, the house shape. Rows are predictions made at plan time; each is
confirmed, corrected or replaced during implementation, and anything found
*during* implementation is appended with the next free number.

**Next free number after this table is D469.**

| # | Runbook says | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D395** | §9: outputs gains an MCP fragment, and the route is published. | **`routes.mcp` is in the RENDERED document and absent from the DEPLOYED one.** Measured on the host before a line was written: the deployed document carries `app, app_docs, docs, health, rest, storage` and no `mcp`. `deployed_output.py` builds from an explicit key list. | Session 8's **first** run carries `routes.mcp` through, with the readiness claim on the deployed branch, and a test comparing the rendered route set against the deployed one **as a set** rather than field by field. | **This is D389 exactly, found before it could cost a host trip.** Session 7 lost a gate run to the storage block existing in the rendered document and being forbidden in the deployed one, and the schema's own description said the runtime reads it from there. The same gap is sitting in `routes`, and the fix is now a known shape rather than a discovery. | — |
| **D396** | §2.6: agent tokens carry `token_use=access`. | **Agent tokens carry `token_use: "agent"`.** `TOKEN_USES = ("access", "agent")`; `auth_token` mints agents with `token_use="agent"` and `sub` = the agent id. And **ADR 0114 refuses anything but `access` at the application API**, before any subject lookup. | **An ADR, and it is Session 8's first decision.** MCP is a different surface with a different principal class, and ADR 0114 says in as many words that it *must state its own answer rather than inherit this one*. Session 8 declares `token_use: "agent"` as the one value the MCP surface accepts, and refuses `access` there. | The two surfaces are mirror images and both refusals must be explicit. A human token reaching `/mcp` and an agent token reaching `/api/app` are each a principal in the wrong place, and neither should be refused by an accident of which table a subject lives in — which is what D393 was. | needed |
| **D397** | §2.6: the token carries `agent_id`, equal to `sub`; agents carry no `credential_version`. | **There is no `agent_id` claim.** `REQUIRED_CLAIMS` is fixed at twelve members and `sub` **is** the agent id. **`credential_version` is required for every token**, and an agent's is `0` — deliberately, so that "not a human" is a value rather than an absence. | The verifier reads `sub`. Nothing is added to the claim contract: a thirteenth claim would be a second authority for an identity `sub` already carries, and `claims.py` is one list read by three services. | **D264's shape.** Two claims meaning one thing is two things to keep in step, and the runbook's own text concedes they are always equal. The `credential_version: 0` convention is load-bearing in the opposite direction — a missing claim is indistinguishable from a stripped one. | — |
| **D398** | §3.1, §4.9: add an immutable `data_owner_id` to each agent, backfilled from `created_by`. | **`app_private.agents.owner_id` has been `uuid NOT NULL REFERENCES app_private.users (id)` since migration 0011**, with the comment *"Non-human subjects, owned by a human one."* There is no `created_by` column and nothing to backfill. | The RLS-effective principal is `agents.owner_id`. **No migration adds a column.** The name in every document becomes `owner_id`. | The runbook proposes building something the identity registry already has, under a second name — which would give the same fact two spellings and a migration to keep them in step. Session 7 met the constraint from the other side: `owner_id` is `NO ACTION`, so an agent blocks its owner's deletion (D392). | — |
| **D399** | §2.6, §4.12: scope names are `agent:read` and `agent:write`. | **The vocabulary is closed and those names are not in it.** `schemas/capabilities.schema.json` is the sole authority: `$defs/agent_scope` is `notes:read, notes:write, tasks:read, tasks:write, meta:read`, and `scopes.py`'s `agent_reader` ceiling is `{notes:read, tasks:read, meta:read}`. | The scopes are the real ones. `docs/capability-plan.md` already assigns them per tool: `meta:read` for the two metadata tools, `notes:read`/`tasks:read` for `query_resource`, both for `run_report`. | **ADR 0079's classes exist so that a scope is per (resource, verb), not per audience.** `agent:read` would be a scope that says who is asking rather than what is being asked for, and one that grants every resource at once — which is the coarse-grained model the vocabulary was closed to prevent. | — |
| **D400** | §3.1, §4.12: Session 8 activates the physical agent-reader role. | **Two passing tests say the agent roles are Session 9's.** `test_session3_authorization.py` asserts `agent_reader` holds no `USAGE` on `app_private`; `test_api_migrations.py` asserts migration 0008's grant names exactly `{object_owner, anon, authenticated}` and that the agent roles are "deliberately not granted to the authenticator, so PostgREST cannot become either". | **Session 8 activates `agent_reader` and this is a decision with an ADR**, because it moves a boundary two tests currently assert. Both are **re-derived, not relaxed** (ADR 0096): the grant list becomes the set the deployment actually needs, derived from the same authority, so a *third* unexpected role still fails. `agent_writer` stays inactive and Session 9 owns it. | **D300 is this exact situation and it happened three times in one session.** The tempting fix is a subset check — `granted ⊇ expected` — which turns *exactly what is granted* into *at least what is granted* and would pass the next accidental grant. The assertion must still be exact after the change. | needed |
| **D401** | §10: migration `0013_mcp_reads.sql.tmpl`. | **Seventeen migrations are released and applied on both clusters.** Session 8's is **0018**, named `migrations/templates/0018-<name>.sql`, rendered by the deliberately incapable renderer and frozen with `bin/migrate.sh freeze-lock`. | `0018-agent-read-plane.sql`. **It does not redefine the pre-request hook.** | **D270**: the hook is defined in four files and only the last one runs. 0013's body carries the statement-timeout carry, the documentation-role clause and the current-state comparison. A 0018 that redefined it from an older body would silently delete all three — and Session 8 needs to *extend* the hook, which is precisely the dangerous case. | — |
| **D402** | §9: outputs schema version 8. | Outputs is **v11**, and both deployed projects are on it. v8 was Session 5's. | Session 8 publishes **v12**, chosen **once, from the session's whole surface** — the MCP route's readiness, the capability lock identity, the protocol and authorization-profile fields, and whatever the agent context needs. | **D255 and D308 are the same mistake twice**: a version bump chosen one run early, from the run in front of you rather than from the session's whole surface. | — |
| **D403** | §7: `capabilities.yaml` schema version 2, with a new capability shape. | **v1 already has that shape.** `$defs/capability` requires `name, kind, enabled, required_scopes, operation` and permits `resource, columns, filters, order_by, max_rows, max_affected_rows, idempotent, timeout_ms, audit`. The file has carried `capabilities: []` since Session 1 because no live backing contract existed. | **Extend v1 where a field is genuinely missing; bump only if a member changes meaning.** A version bump that renames nothing and removes nothing is a migration everyone pays for and nobody needed. | The schema was written in Session 1 *for this session* and its own description says so. Discovering that it already fits is the intended outcome, not a coincidence to overwrite. | — |
| **D404** | §2.8: `bin/session-07-check.sh --project project.yaml --peer-project tests/fixtures/projects/project-b.yaml`. | Gates take **`--mode offline\|host\|external`** plus `--host`, `--project-a-outputs`, `--project-b-outputs`, and where the claims need them `--admin-password-file`, `--sentinel-file`, `--ssh-destination`. There is no `--peer-project`. | `bin/session-08-check.sh` in `session-07-check.sh`'s shape, three modes. Every flag a claim depends on goes **in** the usage command, not below it. | **D213**: a flag mentioned under a command is a flag nobody passes. And **D316** is this same row from Session 7, which means the runbook family has now proposed the wrong invocation twice. | — |
| **D405** | §20: a nineteen-phase build with a findings ledger, phases for each tool, and separate phases for tests. | Runs are the unit here, each ending with the offline gate green on a clean tree. | **Nine runs**, §5. Tests are written *inside* the run that owns the code, then broken with a mutation battery — not deferred to a phase of their own. | A phase list that separates "implement" from "test" produces a session whose tests are written against code that already exists and already passes, which is the weakest moment to write them. CLAUDE.md §4 step 5 is the rule and it is not optional. | — |
| **D406** | §4.2: pin FastMCP **3.4.5** and its hash-locked graph. | **Unmeasured.** No version of FastMCP is in `requirements-dev.in` or any image, and the runbook's number is asserted, not observed. | **Measure the version that exists before pinning anything**, then lock with `bin/lock-versions.sh --update --packages-only` and carry the image digests forward unchanged. The protocol revision the locked framework actually implements is read from the framework, not from this document. | **D321/ADR 0083**: a plain `--update` re-resolves every image and once moved `pgvector:pg18` and `python:3.12-slim`, which would have shipped an unmeasured PostgreSQL upgrade inside an unrelated session. And **D267**: never write a measurement you did not run — a pinned version nobody checked is exactly that. | — |
| **D407** | §4.9–4.11: FastMCP forwards the bearer token to PostgREST and holds no database credential. | **Correct, and it has a consequence the runbook does not draw**: an MCP runtime with no database credential takes **no share of ADR 0099's connection budget**. `max_connections` 56 stays divided api 13, auth 6, storage 6, application 23, headroom 5. | The budget is **unchanged**, and a test asserts that the MCP service is absent from it — so a later change that quietly gives MCP a pool is caught by arithmetic rather than by a cluster running out. | **D309 was the opposite mistake**: a service added with no term in the budget. Recording "this one costs nothing" is the same discipline as recording a cost, and it is the only way the next reader can tell a considered zero from an oversight. | — |
| **D408** | §17: publish the MCP route at `/mcp`. | **Traefik orders overlapping routers by rule LENGTH, not specificity** (D352, ADR 0108), and `PathPrefix` is a **string** prefix, so `/mcp` also matches `/mcpx` (D162). `/mcp` is short — four characters — and nothing today guarantees it outranks a longer rule that could match it. | The rule is written in the form ADR 0108 froze, its precedence is **derived from the rule** rather than pinned by a priority, and the boundary is proved **by request**: `/mcpx` must reach a different backend, and which service answered is read from the response, never from the status code. | **D353**: a sibling of a nested path is not a 404, and Traefik's own 404 is indistinguishable from a routed one except by a 19-byte body and a missing `RouterName`. A boundary test here that checks only the status proves nothing. | — |
| **D409** | §4.8: FastMCP receives a read-only public JWKS generation. | **ADR 0113 already decided how a non-issuing verifier gets its key set**: the rendered `jwks.json`, mounted read-only, loaded with `LocalKeySet.from_path` — the same file PostgREST and storage read. MCP is the **fourth** verifier. | MCP mounts the same artefact by the same mechanism. **Nothing new is designed.** | **D381 is what happens otherwise**: storage was declared the third verifier in four places and handed no key set, and exited 3 on its first start anywhere. The fourth verifier is the moment to check that ADR 0088's *recreate, never restart* list and `SEC-KEY-002`'s readings both moved — which is D320's prediction, now due a second time. | — |
| **D410** | §12, §19: a FastMCP container with its own settings and health routes. | Services that authenticate as a bootstrap-activated role must join `runtime_override.POST_BOOTSTRAP_SERVICES` (D324). **MCP holds no database credential, so it does not belong there** — but it does need the `session8` Compose profile, and `CURRENT_SESSION` must move to 8 to arm it. | `profiles: [session8]`, absent from `POST_BOOTSTRAP_SERVICES`, and the reason written where the constant is read. Moving `CURRENT_SESSION` **arms the profile on the next deploy of any project**, so it is a deliberate step, not a tidy-up. | Session 7 learned this from the other side: Run 9 moved `CURRENT_SESSION` to 7 and the next deploy immediately tried to start a storage container that failed closed without its secrets. The operator guide had to say so **before** the step, not after. | — |
| **D411** | §19.2: inspect the container to prove what it holds. | **The locked PostgREST image is distroless** and `docker exec … cat` exits 127 (D305); the storage image is hardened the same way — read-only rootfs, uid 65532, no package manager. | Container-side reads use `docker cp`, measured with a control. Operator commands that need service logic run **inside** the service's container (ADR 0093). | **D305 was found only because D299's fix let execution reach the next line.** One unrun proof hides the next, which Session 7 then demonstrated four times over. | — |
| **D412** | §4.29: read telemetry is structured but not durable audit. | Correct, and the boundary needs stating against something real: `mcp_audit_service` is in `naming.ROLE_SUFFIXES` and has been since Session 3, unactivated. | Session 8 writes **no** durable audit record and does not activate `mcp_audit_service`. Telemetry is logs, and the logs are subject to the same canary scan Session 7 built for URLs and keys. | A role that exists and is not activated is a promise the next session keeps. Activating it here to "get ahead" would put an audit identity in production before the record it writes has been designed — which is Session 9's, with its own fail-closed contract. | — |
| **D413** | §4.6, §4.3: an internal pre-provisioned bearer profile, documented as not standards-conformant. | **Right, and the honesty is the valuable part.** But the runbook states it in prose only; nothing in the deployment carries it. | The deployed document publishes the protocol revision and `authorization_spec_conformant: false` as **fields**, and the contract test asserts the document says what the docs say. | **D274 is the precedent**: `/docs/rest` was proved at 401 and 200 for four runs and had never rendered, because nothing requested the script its own markup named. A claim that lives only in prose is a claim nobody checks. | — |
| **D414** | CLAUDE.md §2's status block: *"`CURRENT_SESSION` 7 — Session 8's first code run moves it to 8."* | **Moving it in Run 1 turns the gate red, and not for the reason D410 predicts.** `CURRENT_SESSION` is the gate session, and `test_no_requirement_at_or_before_the_gate_session_remains_future` refuses any registry entry targeted at or before it that still points at a `future` marker. **Five do** — `AGT-READ-001`, `AGT-SQL-001`, `AGT-SCOPE-001`, `AGT-DRIFT-001`, `AGT-BUDGET-001`, all `target_session: 8`, all pointing at `tests/integration/test_future_mcp.py`. Session 7 hit the same coupling and answered it the same way: Run 9 moved the constant **and** activated eleven entries in one commit. | **It moves in Run 7**, with the `session8` Compose profile, and **only after Run 6 has replaced the five placeholders**. Not Run 1. `AGENT_PLANE_SESSION = 8` is defined now and deliberately sits above `CURRENT_SESSION`, so `--through-session` cannot reach the agent plane and no observation branch exists to run. | The handoff's sentence is a tidy-up instruction for a constant that is not a tidy-up (D410 says so from the deploy side; this is the same constant refusing from the gate side). Moving it early would have produced a red gate in Run 1 whose cause is five tests Run 6 owns — and the tempting repair is to relax the registry policy, which is D300's shape on the one control that keeps a placeholder from passing for a proof. | — |
| **D415** | — (found during Run 1). | **Three single-step migration tests asserted `migrated["schema_version"] == CURRENT_VERSION`.** The v10→v11 step's own result was compared against *the release's current version*, which held only while v11 was current. The v9 test already carried a comment saying this had happened before and had been fixed there; the same shape survived in three neighbours. | **A single step's result is asserted as a literal; only the end of a chain compares against `CURRENT_VERSION`.** All three re-derived, not relaxed: the v11 assertion stays and a v12 assertion is added beside it, so both the step and the endpoint are checked. | A test that compares a function's output to a constant which moves *with* the function is a test that cannot fail for the reason it was written — and it degrades silently, one version at a time. It is the *"test comparing two constants"* shape (Session 7 Run 7 M8), arriving through a name rather than a literal. | — |
| **D416** | D400: two passing tests say the agent roles are Session 9's, and Session 8 re-derives them. | **There were four copies of the enumeration, not two tests.** `AUTHENTICATOR_REQUEST_ROLES` was created in Session 6 Run 9 *precisely so that the proof could read it instead of restating it* -- its own docstring says so, and says the restatement is what reported the product's deliberate `project_admin` grant as a violation on the first host gate (D301). The fix reached `role_statements`, which **grants**. It never reached `check_violations`, which **verifies** and still carried the list as a literal -- twice, once for the memberships and once for a two-name forbidden set. `tests/contract/test_bootstrap_statements.py` carried a fourth. | All three copies deleted. Both loops in `check_violations` read the constant; the forbidden set is its **complement over the project's own roles**; the test reads the constant and keeps one independent anchor -- `agent_writer` is named, with ADR 0116 behind it, because a set derived entirely from the product cannot refuse a bad edit to the product (D300). | **§6 question 5, in the file that records the last time it was asked here.** The two-name literal is the part worth noticing: activating one agent role would have left the other as the only forbidden membership, and `app_runtime`, `auth_service` and `storage_service` were forbidden by nothing at all. | 0116 |
| **D417** | — (measured during Run 2). | **A human token naming the agent role was refused by `permission denied for function auth_claims_are_current`, not by `AP401`.** The first draft granted the new agent comparison helper to the agent role alone, reasoning that a human request never reaches the agent branch. The reasoning is right; the conclusion was wrong. A token's `role` claim decides which role PostgREST becomes and `token_use` decides which branch the hook takes -- **independent claims, so every combination is a reachable request**. | Both comparison helpers granted to **all five** request roles, which is the rule 0013 already states for its own: *"the comparison helper, to every role that runs the hook."* Both refusals are then the hook's own `AP401` on a tuple comparison, for every principal at every door. | **D393 exactly, arriving through a missing GRANT rather than a missing row.** Correct outcome, false reason, boundary standing on a privilege nobody chose -- and a 42501 reaches the caller as a different failure from every other refusal the hook issues, so a client cannot treat "your token is stale" as one outcome. Found on the first run of the rig, not by review. | 0117 |
| **D418** | The plan's Run 2: *"one named read report RPC"*, and AGT-READ-001 compares an agent read against "the equivalent PostgREST result". | **The equivalent request is `permission denied`, and it must stay that way.** The rig argued for granting `owner_activity_report` to `authenticated` so the comparison would have a human half. But a read RPC a human may call is a **fifth human operation**, and **ADR 0003's example domain is frozen** -- four operations, amended once by ADR 0048 for one additive column. | The report stays agent-only. The equivalence is proved against the **row surface** instead: the agent's counts must equal the rows the same principal reads through `api.notes` and `api.tasks`. Measured equal both ways (`2 2 1 1`), with a second owner reading `1 1 1 0` as the control that neither number is a constant. | **The proof moved, not the product.** It is also the stronger comparison: two functions can be wrong in the same direction, and a count that disagrees with the rows it counts cannot be. A test's convenience is not a reason to widen a frozen surface. | 0118 |
| **D419** | The capability plan, rule 3: *"It references exactly one pre-existing operation by ID."* `capabilities.schema.json` requires `operation.operation_id`. | **The live PostgREST publishes no `operationId` anywhere.** Measured against a running service on the locked image, captured through a documentation-role token because `follow-privileges` builds the document as the role of the request: Swagger **2.0**, where the field is optional, and every operation without one. The committed snapshot shows the same, but a normalized capture is evidence about `openapi_normalize`, not about PostgREST -- which is why this was measured live. | The id is **derived**, `<object>.<method>` with `/` written as `.`, by one function that is the single authority for the spelling. Capabilities resolve against the **reviewed surface contract**, not the served document; the document is then read as a cross-check in both directions. | The rule is right about what a capability must not contain and wrong about what the source provides. Carrying `method` and `path` instead would be honest, change a member's meaning (a v2 bump under D403) and put a **path** in the manifest -- which the same sentence forbids. | 0119 |
| **D420** | — (found during Run 3). | **`config.load_capabilities_manifest` refused *every* `enabled: true` capability**, with the message *"no live API contract exists to validate it against in this session"*. That was true when it was written and **stopped being true in Session 5**, which shipped `contracts/postgrest-api-surface.yaml` and the approved OpenAPI snapshot. It survived three sessions because nothing ever enabled a capability, so the guard's stated condition and its behaviour never had to agree. | The blanket refusal is removed and the validation moves to `capability_compiler`, which needs two documents `load_capabilities_manifest` is not given. `CapabilityContractError` survives and `CompilerError` now **subclasses** it, so the exit-5 distinction the class was created for moves with the check. | A guard whose stated condition is false is worse than no guard: it reads as a live control and is a comment. It is the mirror of **D391** -- there, a guard whose result was discarded; here, a guard whose reason had expired. Neither is visible while nothing exercises it. | — |
| **D421** | — (found during Run 3, by reading the compiler's own output). | **A flat `discovery_scopes` list cannot distinguish "any of" from "all of".** `query_resource` is `notes:read` OR `tasks:read`; `run_report` is `notes:read` AND `tasks:read`. Flattened, **both are the same two strings** -- so an agent holding only `notes:read` would be shown `run_report` in discovery and refused when it called. | `discovery_scope_sets`: a disjunction of conjunctions. One set per backing capability; the tool is discoverable when the caller holds every scope in **any one** set. | Found by reading the compiled artefact rather than by a failing test, which is the only way this class shows up: both spellings validate, both look right, and the difference is invisible until an agent holds exactly half of what a tool needs. **A tool list that advertises what it will refuse is a tool list that lies.** | 0120 |
| **D422** | — (found by the full suite, during Run 3). | **`CFG-013` is a P0 requirement whose description became false.** It read *"the capability surface is empty by default, cannot be enabled without a live backing contract, and cannot express SQL or a raw query"*, and two of its three clauses stopped being true the moment five capabilities were enabled. `test_every_registered_node_id_is_collectible` caught the renamed node ids; **nothing would have caught the stale description** — D175 records that as a review rule with no test behind it. | The node ids move and the description is rewritten to the property the old one was an instance of: the surface is **exactly the reviewed set**, compiled against a live backing contract rather than trusted, unable to declare a backend it does not reach, and unable to express SQL. A compiler node id joins the three manifest ones, so the "live backing contract" clause points at the thing that now enforces it. | **Not a weakening, and the distinction is the whole of ADR 0096.** "Nothing is enabled" proved less than "exactly the reviewed set is enabled, each resolved against the reviewed contract" — the second refuses a sixth capability and the first never had to. A P0 description may not be relaxed; this one is replaced by a stricter statement of the same property, which is what the README permits and what ADR 0119/0120 authorise. | 0119 |
| **D423** | §4.2: pin FastMCP **3.4.5**. D406 predicted at plan time that the number was asserted rather than observed. | **3.4.5 exists** -- D406's prediction is corrected, not confirmed. What is wrong is the repository's own entry: `FASTMCP_VERSION` has read **2.14.1** since Session 1 and **installs cleanly and then fails to import** against the locked `python:3.12-slim`, with `ModuleNotFoundError: No module named 'pydantic_settings'`. Cause, read rather than guessed: fastmcp 2.14.1 declares `mcp>=1.24.0` with no ceiling, pip resolves **mcp 2.0.0**, and that major dropped a transitive dependency fastmcp imports directly and never declared. Constrained to `mcp<2` it imports. Control: `fastmcp==999.999.999` is refused by the same command. | The entry moves to a version that has been **run**, and the Dockerfile's trailing import control names `fastmcp` and `mcp`. Locked with `--update --packages-only`, which moved one package and carried all **ten image digests forward unchanged** -- verified by diff, so D321's `pgvector:pg18` cannot travel in an MCP run. | **D201 with the defect finally arriving.** `SCALAR_VERSION` named a release that never existed for four sessions because nothing built from it; this named a release that *did* exist and stopped working, through nobody's change here. A lock verifies what it can dereference, and dereferencing is not importing -- which is **ADR 0083's distinction, second instance**. | 0121 |
| **D424** | §4.2 treats the FastMCP version as a free choice. | **It is bounded by FastAPI, and the boundary was bisected.** `fastmcp-slim[server]` moved to `starlette>=1.0.1` at **3.4.1**; `fastapi==0.121.2` requires `starlette<0.50.0,>=0.40.0`. Measured one arm per patch release: 3.4.0 resolves, 3.4.1 through 3.4.7 are each `ResolutionImpossible`. Controls: `3.4.7 + pydantic==1.10.0` -> CONFLICT, `3.4.5` alone -> OK. 3.4.0 then installed **for real**, not `--dry-run`, beside the entire pinned set: everything imports, `pip check` clean, mcp 1.29.0 and starlette 0.49.3. | **3.4.0**, pinned as a measured ceiling with the reason at the lock entry. Adopting `latest` would mean bumping fastapi to **0.141.1** -- twenty minor releases, on the service that hashes passwords and signs tokens -- inside a run about the agent plane. | The ceiling is what makes **ADR 0121's one-image model possible at all**: 3.4.1 would force a second image for the agent plane, and a second image cannot import `LocalKeySet`. So the number is load-bearing rather than current, and raising it is a decision about ADR 0101 rather than a dependency refresh. Bumping FastAPI instead is **D321's mistake with a different package**. | 0121 |
| **D425** | D409, and ADR 0113's own Consequences section: *"Storage joins the recreate list ... There are now three."* | **It never joined.** `bin/rotate-signing-key.py` still read `VERIFIERS = (runtime_override.REST_SERVICE,)` -- **one of three** -- with a Session 6 comment saying *"one today ... and Session 9 adds agent-facing verifiers"*, which was true when written and is the sentence that made the omission look intended. `promote_rotation` blocks until every name in that tuple has acknowledged, so a rotation would have switched the signing key while the storage container still held the retired set. Every test in the module iterates `for verifier in command.VERIFIERS`, so none of them could see it. | The roster becomes a **table**, one row per verifier carrying service and container path, with storage and mcp in it. Two tests, deliberately: a sweep DERIVED from `compose.yaml` (every service given `APG_JWKS_FILE`, plus PostgREST) that catches the *next* verifier, and a literal anchor naming storage and mcp that a bad edit to the product cannot move. | **D333's question for the sixth time, and the first time the unimplemented half is an ADR's own stated consequence.** The symptom would have been **D276's**: 401 on every token from one surface, invisible until something asked both. And the tests being derived entirely from the constant is **D300/D416** again -- a set derived from the product cannot refuse a bad edit to the product. | 0122 |
| **D426** | `VERIFIER_JWKS_PATH = runtime_override.JWKS_CONTAINER_PATH`, guarded by `test_the_key_set_is_read_where_the_container_reads_it`. | **One constant, three paths.** PostgREST reads `/etc/postgrest/jwks.json`, storage `/etc/storage/jwks.json`, and the agent plane now `/etc/mcp/jwks.json`. The guard asserted one constant equals one constant and passed throughout. | The path comes from the roster row. `VERIFIER_JWKS_PATH` is **deleted rather than generalised**, and a test asserts the attribute is gone -- a single name for a per-verifier value is the defect, not its spelling. The replacement asserts the map service -> path and that no two verifiers share one. | **CLAUDE.md §6: a test comparing two constants is not testing the thing between them.** Session 7 Run 7's M8 found the same shape with both constants holding the same number; here they held the same *string* for one of three readers. | 0122 |
| **D427** | `loaded_digest` reads a verifier's key set with `docker exec <container> cat <path>`. | **It cannot, in the image of the only verifier the roster held.** Measured against the locked images on Docker 29.5.2: `postgrest:v14.16` has neither `cat` nor `sh` -- both exit **127**, *"executable file not found in $PATH"* -- while `docker cp` on the same image exits 0. Control: the locked `python:3.12-slim` has both. So `acknowledge` raises `EXIT_STATE` for PostgREST and **promotion can never be unblocked**. | `docker cp` streamed to stdout, with the single archive member extracted so the digest is of the FILE rather than of the tar. Built by `read_command`, a pure function, so the shape is assertable offline instead of an AST dump being searched for `'exec'`. | **D305 and D411, arriving in the one command that most needed them.** It also gives the standing open item a measured cause: *"the rotation window -- the only thing keeping two Session 5 claims red"* has been carried three sessions, and its second phase could not complete. Whether `docker cp` finishes the sequence is a **live-host** claim this session does not assert. | 0122 |
| **D428** | Outputs v12, written in Run 1: *"the MCP protocol revision the deployed runtime actually **negotiated**, read FROM the runtime"*. | **A negotiated revision is a fact about the CLIENT.** Measured against a running FastMCP 3.4.0: an `initialize` asking for `2025-11-25` is answered `2025-11-25`; the control arm asking for `2025-03-26` is answered **`2025-03-26`**. A field filled from one handshake records the version of the probe that measured it. `DEFAULT_NEGOTIATED_VERSION` is the neighbouring trap -- `2025-03-26`, what an unversioned caller gets, two revisions below the ceiling. | The field is the **highest revision the runtime implements**, read from `mcp.types.LATEST_PROTOCOL_VERSION` at startup and never written down here. The schema's description is corrected in place. No version bump: the member's shape and nullability are unchanged, only what it means. | The second half of Run 1's sentence -- *never from a document that hoped for one* -- was right, and the first half named the wrong quantity. **Nothing in the deployment pipeline may fill this by asking the server**, which is the opposite of what the old description invited. | 0123 |
| **D429** | §12/§19: the MCP container has its own health routes, and every other application service here carries a Compose healthcheck. | **`services/auth-api/` may contain no network client at all.** `test_the_service_never_constructs_a_network_jwks_client` forbids `PyJWKClient`, `urllib`, `httpx`, `requests`, `aiohttp` and `socket` anywhere under that tree, by AST, with a control proving it tells code from prose. A liveness probe written as `app/mcp_health.py` is refused by it -- correctly. **The guard is nevertheless escaped by the existing pattern**: the auth service's `HEALTHCHECK` performs an HTTP request from an inline `python -c` string in the Dockerfile, which no AST scan of `.py` files can see. | **Run 4 ships the `mcp` service with no healthcheck, and says so where the entry is.** The reasoning the probe would have encoded is written there for Run 7, which the plan already gives the health surface: a 401 proves the process serves and the verifier is mounted, and **a 200 is a failure** because it means the boundary is gone. Nothing starts this container before Run 7 in any case. | Weakening a P0 guard to fit a liveness probe is the wrong trade, and the honest alternative to a hacky one-liner is to leave the surface to the run that owns it. The escape hatch is recorded rather than used: a guard satisfied by moving code into a string is **D277's shape** -- there, an AST scan satisfied by dead code -- and whether it should scan the import graph instead is a decision, not a tidy-up. | -- |
| **D430** | --- (met while implementing ADR 0122.) | **A `@dataclass` cannot be defined in a `bin/` command module.** `tests/contract/test_rotate_signing_key.py` loads the command with `spec_from_file_location` + `exec_module` and never registers it in `sys.modules`; `dataclasses` looks the defining module up by name while processing annotations, so the class raises `AttributeError: 'NoneType' object has no attribute '__dict__'` **at import, inside the test rather than the command**. | `Verifier` is a `NamedTuple`, which needs no such lookup, and the constraint is written at the class rather than in a commit message. | The failure names neither dataclasses nor the loader, and it appears only under the test harness -- so the command runs fine by hand and the suite goes red. Recorded because the next person to reach for a dataclass in a `bin/` command will meet it, and because a five-minute diagnosis is worth one sentence. | -- |
| **D431** | D429 deferred the question: `test_the_service_never_constructs_a_network_jwks_client` forbids `urllib`, `httpx`, `requests`, `aiohttp` and `socket` anywhere under `services/auth-api/`. | **Run 5 cannot defer it** — the agent plane's whole job is an HTTP call to `mcp_agent_context`. And the guard turns out to be **both too wide and too narrow**: `storage_client.py` has been making real R2 round trips (`head_object`, `delete_object`) through **boto3** for a whole session, and boto3 is not one of the five names. The guard's docstring is about a *network JWKS client*; its implementation is a list of transport spellings. | Replaced by **three** stricter checks (ADR 0124). `PyJWKClient` stays banned outright. A key set may be built **only** by `LocalKeySet.load`/`from_path`, asserted directly rather than inferred from the absence of a transport. And every transport — now **eight** names including boto3 and botocore — is refused except in a module that declares it in an allowlist with a reason. Two rows today. | **D277's shape**: an AST scan asking whether a *name* is mentioned is satisfied by importing a different one, exactly as one asking whether a function is mentioned was satisfied by dead code. A filesystem fact standing in for a logic test — CLAUDE.md §6's pattern, produced by a test written to enforce §6. The replacement **fails for a case the old one passed** (boto3 in an undeclared module), so it is a net tightening rather than an exemption. | 0124 |
| **D432** | Migration 0018's comment on `api.mcp_agent_context`: *"Zero rows when the caller is not an agent — a question with no answer rather than an error."* | **Over HTTP that branch is unreachable for a stale or unknown agent.** Measured against a live PostgREST on the locked digest with all eighteen migrations applied: an agent token naming an agent that does not exist is refused by the **pre-request hook** with `401 PT401 / AP401: the request identity is no longer current`, and the function is never entered. The comment is true of the function and false of the surface. | **Exactly one row is a context; zero rows is a refusal.** The client does not treat an empty array as "not an agent" — a 200 with no rows would mean something the product does not produce, and continuing would hand a tool an agent with **no scopes and no owner**. | The tempting reading is the dangerous one, because the comment invites it and the branch would then be untested by construction. It is the same class as **D420**: a guard whose stated condition and whose behaviour never had to agree, because nothing exercised it. | 0125 |
| **D433** | §4.9–4.11 treats "FastMCP forwards the bearer token to PostgREST" as the whole of the authorization design. | **Two of the measured refusals do not say what a reader would assume.** An anonymous request is refused **401 with a body of `42501 permission denied for function mcp_agent_context`** — a *privilege* error carrying an authentication status. A human `access` token is refused **403**, also on `42501`, by a missing GRANT rather than by the `token_use` branch. So neither the status nor the body identifies the cause, and the three 401s measured (`PT401` stale identity, `PGRST301` bad key, `42501` no privilege) are indistinguishable by status. | **No upstream status or error code is relayed.** A refusal carries a short machine reason for this process's own telemetry and nothing for a response body (ADR 0097). A test asserts that `42501`, `permission denied` and the function's name are all absent from what the refusal carries. | **D417 from the other side.** There, a human token naming the agent role was refused by a missing GRANT rather than by the hook — correct outcome, false reason. Here the same shape would let the runtime report "your token is invalid" for what is actually a privilege boundary, to a caller who is in no position to act on either. | 0125 |
| **D434** | — (found by Run 5's mutation battery, N3.) | **The `HTTPError` branch of `resolve_agent_context` had never executed in any test.** The test recorder returned a 403 as an ordinary response object, which `urlopen` never does — it raises `HTTPError` for every 4xx and 5xx. So the assertions about refusal content were reaching the *other* branch, and a mutation that relayed PostgREST's error text to the caller **survived**. | The recorder raises `HTTPError` for any status ≥ 400, which is what urllib does. The branch every real refusal takes is now the branch the test exercises. | **D211–D214's family, inside a fixture.** A proof that has never executed in the configuration that ships, and nothing in a green suite says so. It is also what the battery is *for*: the test read correct, the product was correct, and the path between them was not the one production uses (ADR 0065's question, asked of a fixture). | — |
| **D435** | — (found while writing Run 5's battery.) | **Two survivors were the mutation's fault, not the test's, and each hid a real gap.** N7 replaced the middleware body but still wrote through the `ContextVar`, so the mechanism it meant to break was still intact. N12 admitted the `postgres://` scheme, but the only `postgres://` case in the test carried **userinfo**, so a *different* rule refused it and the scheme rule was never isolated. | N7 swaps the mechanism itself — the `ContextVar` for a module-level holder — which is the thing measured to leak 11 of 12 concurrent requests. N12 gains a `postgres://postgres:5432/db` case with no userinfo, so **each rule has a case only it can refuse**. | **CLAUDE.md §1's rule, met twice in one battery**: when an arm survives, the repair may be the mutation rather than the assertion, and deciding which requires reading what actually ran. A battery that had recorded "2 survivors, weak tests" would have produced two false findings and left the real gap — a validator rule with no isolating case — in place. | — |
| **D436** | `capability_compiler.compile_lock`: *"`upstream` is the ONE address the runtime may call — Run 6's fixed upstream."* | **The runtime cannot call it.** `bin/mcp-contract.sh lock` fills `upstream` from the deployed document's `routes.rest`, which is the project's **public** URL — `https://<domain>/api/rest`, behind Traefik and TLS. The agent plane runs on the `internal` Compose network, declared `internal: true` (*"no route off the host"*), where the address that resolves is `http://postgrest:3000` — the one Run 5 already dials and measured working. | **The runtime dials `APG_POSTGREST_URL`; the lock's `upstream` is the surface's published identity and nothing dials it** (ADR 0126). The field keeps its value and gains a corrected meaning: it says *which API surface this contract describes*, which is what makes two projects' locks distinguishable. A test asserts no request is built from it. | **D389's shape**: there, outputs v11 put the storage bounds in the rendered document while the deployed branch forbade them, and the runtime read the deployed one. Here a compiled artefact declares an address the consumer cannot use. Both are correct-looking URLs and only one resolves, so the separation has to be asserted rather than remembered. | 0126 |
| **D437** | AGT-SQL-001: *no SQL, no fragment, no raw query string, no path, no runtime-selected operation.* | **Stated as absences it is satisfied by any code nobody has written badly yet.** The real hazard is narrower and is not SQL injection: PostgREST takes filters as `column=operator.value` in the query string, so a caller's *value* carrying `&` becomes a second parameter. Measured, with a control that CAN fail — `title=neq.<value>`, value `zzz&limit=1`: **percent-encoded → 3 rows** (one literal), **unencoded → 1 row** (a filter AND a limit). The first version of this measurement proved nothing: both arms returned zero, one because the value matched nothing and one because **RLS already excluded the injected owner**. | A construction rule instead of a list of absences (ADR 0127): every part of the request except the caller's values comes from the lock, and each value is escaped **for the position it occupies**. Columns, operators and orderings are checked against the lock's frozen sets before a request is built, so an invalid call costs no upstream request. | Two arms agreeing for different reasons is not a control, and Session 8 has now paid for that twice (D435 is the other). The re-measured arm is what makes the encoding claim mean anything. | 0127 |
| **D438** | — (measured while building the adapter.) | **Percent-encoding does not remove a comma from `in.(…)` list syntax, and the SQL quote convention is wrong.** PostgREST decodes the query string *before* it parses the list. Measured against the locked image: `in.(weird,title)` → **0 rows** (silently split); `in.(weird%2Ctitle)` → **0 rows**; `in.("weird,title")` → **1 row**. And inside a quoted member an embedded quote needs a **backslash**: the doubled quote SQL uses → **0 rows**, `\"` → **1 row**. | Members are backslash-escaped (`\\` then `\"`), quoted, then percent-encoded. Verified against **eight** awkward values — comma, quote, backslash, trailing backslash, both, close-paren, dot, plain — each compared with the same row fetched by `eq.`, which needs no list syntax; **eight of eight agree**, and an absent value returns nothing. Then re-verified end to end by firing the **product's own builder** at the live service. | **Both wrong answers fail by matching nothing**, which reads as an empty result rather than an error — the worst failure mode available in a filter. A careful implementer would have reached for `%2C` first and for doubled quotes second, and neither would have raised anything. | 0127 |
| **D439** | D414: the five `AGT-*` placeholders move in **Run 6**, and `CURRENT_SESSION` moves in **Run 7**. | **That split is not executable, and the count is six.** `test_every_later_requirement_has_a_placeholder` requires a placeholder for every requirement with `target_session > gate_session`; `test_no_requirement_at_or_before_the_gate_session_remains_future` forbids one for `target_session <= gate_session`. They are exact mirrors, so replacing the placeholders while `CURRENT_SESSION` is 7 reddens the first, and moving the constant first reddens the second. **`SEC-INJ-001` also targets session 8** and was not in D414's list of five. | **Run 6 does both, in one commit**, with all six requirements repointed at real tests — which is exactly what Session 7 Run 9 did for the same coupling. Run 7 keeps the publish work: the route, its precedence, and the health surface. | The handoff's instruction was written from the gate side only and would have produced a red commit whichever half went first. Undercounting by one is the smaller half: `SEC-INJ-001` sits in a different file under a different prefix, and D414 enumerated the `AGT-*` ones by name. | — |
| **D440** | ADR 0124's transport allowlist, written in Run 5 with two rows. | **A third module needed one, and not because it reaches the network.** `mcp_query.py` imports `urllib.parse` to percent-encode, and the AST scan sees the top-level package `urllib` — the same name `urllib.request` presents. The allowlist could not tell an encoder from a sender. | The row is added with the reason stated, **and the test is tightened**: a module in the allowlist that is not one of the declared *senders* may not name `urlopen`, `Request` or `urlretrieve`. So a query builder that grew a sender is refused by its own row rather than covered by it. | The alternative was to drop `urllib` from the transport set, which would have removed the guard from the one module that does send. Naming the package and then distinguishing the callable is stricter than either half alone — and it is the same correction ADR 0124 made to the guard it replaced. | — |
| **D441** | Run 7's plan: *"Host/Origin protection"*, as though it were a setting. | **The pinned framework does not have it.** Measured at fastmcp **3.4.0** — ADR 0121's ceiling, because 3.4.1 cannot share a process with this repository's FastAPI: `http_app` takes `path, middleware, json_response, stateless_http, transport, event_store, retry_interval` and **`host_origin_protection`, `allowed_hosts` and `allowed_origins` are all absent**. They arrive at 3.4.7. And the runtime does nothing about either today: a request with `Origin: https://evil.test` and a valid token is **processed and answered 200**; a `Host: evil.test` is likewise 200. What stops a browser is the **405** on preflight, which is the absence of a CORS middleware rather than anything the runtime does. | **Origin is refused by our own ASGI middleware, and not by an allowlist — any `Origin` at all** (ADR 0128). No legitimate client of an agent API is a browser, so the header's presence is the signal; it is stricter than a list, needs no configuration, and has nothing to drift from. **Host stays Traefik's**: the router's `Host()` clause is derived from the domain `naming.py` owns, and a second check inside the image would need that domain as a setting. | A protection that lives only in the edge configuration is one the runtime cannot state, and D274's lesson is that a claim nobody checks is a claim nobody has. A test asserts the framework still lacks its own version, so a future bump makes keeping both a real choice rather than a duplicate nobody noticed. | 0128 |
| **D442** | — (measured while designing the route.) | **A `custom_route` mounts at the application ROOT, not under `http_app(path=…)`, and is not behind the token verifier.** Read from the route table the framework builds: `/mcp`, `/health/live`, `/health/ready`, and `GET /mcp/health/live` is a **404**. The health routes answer **200 without a token**, with the control alongside — `POST /mcp` without one is still **401**. | The router publishes `/mcp` and **strips nothing**, because the served path and the published path are then the same string. Health is **private by the absence of a route**: no Traefik router names it, so it is reachable only from inside the internal network, and the public health answer stays `__apg/healthz` (D231). | Had a strip been added by habit — every other application route has one — the edge would have forwarded `/` to a service that answers 404 there, which at the edge is indistinguishable from a missing route (D186, D187). The unauthenticated-health arm means nothing without the 401 control beside it: together they say the routes are open **and** authentication is on. | 0128 |
| **D443** | D408: *"`/mcpx` must reach a different backend, and which service answered is read from the response."* | **There is no different backend.** `/mcp` is **top-level**, unlike `/api/app/storage`, so a sibling matches no router at all and gets **Traefik's own** 404 — a 19-byte body carrying no `RouterName` — rather than another service's. The prediction assumed the storage shape, where a parent router catches the sibling. | The two-matcher rule is unchanged and still necessary (`PathPrefix` is a string prefix, D162). What changes is what the proof looks for: **the absence of a `RouterName`**, not the presence of a different one. Offline, every rule in the override is interpolated with real values and evaluated against `/mcp`; exactly one router matches. | The distinction matters because the two 404s are indistinguishable by status and by body length is how they are told apart (D353). A proof written for the storage shape would have looked for a service that never answers and reported a boundary it had not tested. | 0128 |
| **D444** | Run 4's `AgentTokenVerifier`: *"Structurally typed against the framework rather than subclassing it: the protocol is one coroutine."* | **The protocol is not one coroutine, and nothing had ever built the application.** `http_app` calls `auth.get_middleware()` while assembling, and `AuthProvider` also supplies `get_routes`, `get_well_known_routes` and `set_mcp_path`. A duck-typed verifier raises `AttributeError: 'AgentTokenVerifier' object has no attribute 'get_middleware'` — **on the first real start, anywhere**. Every test since Run 4 constructed the class and called `verify_token` directly, so `build_server(...).http_app(...)` was never executed by anything. | `AgentTokenVerifier` subclasses the framework's `TokenVerifier`. A test now **assembles the real application** and asserts its route table — `/mcp` plus the two health paths — and a second names all four contract methods, so a refactor back to duck typing fails offline rather than on a host. | **D381 exactly, and in the same session that wrote D381 into four ADRs.** A runtime declared in code, assembled nowhere, correct-looking until the first start. It survived Runs 4, 5 and 6 — three green batteries and 3,662 passing tests — because the seam nobody crossed was *construction*, not behaviour. §6 question 2: has it run at all, in this environment, since the thing it measures last changed? | — |
| **D445** | — (found by an existing guard, during Run 7.) | **The deploy tried to import the agent runtime to read its published constants.** `observe_mcp` needs `PROTOCOL_REVISION`, `AUTHORIZATION_SPEC_CONFORMANT` and `ACCEPTED_TOKEN_USE` for the document, and the first version loaded `services/auth-api/app/mcp_runtime.py` from the release by path. That module imports `fastmcp`, `mcp.types` and the service package — **none of which exist on the host** — so it would have raised `ModuleNotFoundError` at deploy time, in the command where it costs most. | The constants are asked of the **running container**: `docker exec … python -c` importing the module that container is actually serving from (ADR 0093). The block stays `unavailable` when the container cannot answer, rather than being filled with a guess. | **`test_no_operator_command_puts_a_service_directory_on_the_path` caught it before the suite did**, and its message names the fix: *“reach the service's logic through a container instead”*. It is D292's guard doing exactly the job it was written for, one session later — and the answer is stronger than the mistake, because what the document publishes is now what the process answering requests holds rather than what the release says it should (D413). | — |
| **D446** | Run 8's plan: *"rows, elapsed time, concurrency and serialized bytes bounded independently"*, as four things to build. | **Two were already built, one was already bounded by the framework, and one did not exist at all.** Run 6 delivered rows and bytes. Elapsed time: measured, a tool body sleeping **5 s** under a 1 s timeout returns at **1.10 s**, `isError=True`, against a control sleeping 0.05 s that returns at 0.09 s — so `@server.tool(timeout=…)`, which Run 6 wired from the lock's `timeout_ms` **without measuring that it bounds anything**, does. Concurrency: eight overlapping tool calls ran **eight bodies at once**. | Three bounds are recorded as already-holding with the measurement behind each, and **concurrency is the one Run 8 adds** — an `asyncio.Semaphore` around the upstream read. | A budget nobody measured is a line in a config file. Run 6's timeout was correct and unproved, which is the better half of the two outcomes here — but the difference between "correct" and "proved" is the whole of §6 question 1, and the concurrency arm is what it looks like when the answer is *nothing would have to break*. | 0129 |
| **D447** | — (a number the plan does not give.) | **The agent plane's concurrency bound is not about the agent plane.** It holds no database credential and no share of ADR 0099's budget (D407) — but each read occupies one of **PostgREST's** connections while it runs, and that pool is shared with human callers. An unbounded agent plane cannot exhaust the cluster; it can exhaust the API. | `MCP_MAX_CONCURRENT_READS` is **rendered from `api.rest.pool_size`**, at half, floor one — so a manifest that shrinks the pool shrinks the agent plane's share with it. The runtime **requires** it rather than defaulting, because a fallback constant would be a second authority for a division `config` owns. | ADR 0070's rule — a division rather than a set of independent grants — applied one level out. **The ratio is a choice and is flagged as one**; what is measured is that the two numbers must move together, and deriving is what makes that true rather than a coincidence two constants maintain until somebody edits one (D264). | 0129 |
| **D448** | Run 6's `ToolRefusal` messages, written to name the INPUT and never the schema, and Run 4's `mask_error_details=True`. | **They cancel.** Measured against a masked server with an unmasked control: a plain exception's message is replaced by `"Error calling tool 'query_resource'"`, while a `ToolError` carrying the same text **passes through the mask unchanged**. So every one of Run 6's carefully-worded input refusals — written, reviewed, tested — reached **nobody**. | Two vocabularies (ADR 0130). `AgentVisible` for what an authenticated caller can act on, raised as `ToolError` at the boundary and reaching them; a plain `ToolRefusal` for everything structural, masked. **The mask stays on**, which is what makes a new refusal silent by default and telling a caller something the act that needs a decision. | **D274's shape**: a claim that lives only where nobody reads it. The tests asserted the message text and passed, because they called the function rather than the surface — the same seam as D444, one layer up. And `ToolError` turning out to be the framework's own name for ADR 0097's second half is the pleasant half of the finding. | 0130 |
| **D449** | — (a worry checked before it was written down as a control.) | **A logged traceback does not carry caller data, and the first guess said it did.** The draft of ADR 0130 claimed rich tracebacks render frame locals, which would put a caller's filter operand in the log. Measured: `show_locals` is **never set** anywhere in the framework's logging setup, so `RichHandler`'s default of `False` applies and a panel shows this repository's own source lines and nothing of the request. | The ADR states the measurement instead of the guess, and says plainly that the property **rests on a framework default this repository does not pin**. It is in the open items rather than claimed as a control the runtime enforces. What the runtime does enforce is narrower and its own: an unclassified failure logs the exception's **type** and never its message. | Writing a control for a premise that is false would have been worse than not writing one: it reads as protection and protects against nothing. **Never write a measurement you did not run** (D267) applies to the reason for a control as much as to a version number. | 0130 |
| **D450** | Run 5's `AgentContextMiddleware`: *"Structurally typed against FastMCP's `Middleware` rather than subclassing it, for the reason `AgentTokenVerifier` is."* | **D444 had a second instance, and Run 7 did not find it.** The framework's pipeline does not duck-type a middleware: the first request through it raises `'AgentContextMiddleware' object is not callable`. Nothing caught it because every test called `on_request` directly — the same seam that hid the verifier for three runs, in the module written one run later, **citing the verifier as its precedent**. | It subclasses `Middleware`. And the test is written as a **pair**: every object the framework is asked to wire is asserted to be a framework type, so a third one added later has an obvious place to be listed rather than a third discovery. | The reasoning was copied from a decision that was already wrong, which is how one defect becomes two. **Run 7's fix was the verifier alone**, because the test it added asserted the assembly rather than the pipeline — a request had still never reached a tool. | — |
| **D451** | — (found by executing the assembled runtime, Run 8's rig.) | **The upstream read runs on the event loop, so the concurrency bound was unreachable.** `execute` is blocking `urllib`; Run 8 made the tools `async def` and awaited it directly. Measured against six overlapping real requests with a bound of two: **peak 1 concurrent**. The semaphore never saw contention — it *appeared* to work, and every other request in the process, health routes included, was serialised behind each read. | The read is moved to `asyncio.to_thread`. Re-measured: **peak 2 of 2**, the bound. Metadata tools stay on the loop and take no slot, because the lock is in memory and a bound that queued discovery would make it contend with reads for nothing. | **A bound that cannot be reached passes every test written against it**, and the arm that caught this is the one that fires real overlapping HTTP requests rather than awaiting a coroutine. It is also the sharper half of D446: the concurrency budget was added *and* was inert, which is a worse state than not having it — the number in the document would have been a promise nothing kept. | 0129 |
| **D452** | CLAUDE.md §1: a mutation battery must **assert HOW each mutation failed**, because pytest distinguishes `FAILED` from `ERROR` and a battery reading neither reports `KILLED` for a mutation that broke the fixture (D386). | **There is a third outcome, and it is neither.** The Q2 arm leaks a semaphore slot; the test that catches it then **blocks forever** on the next `acquire()`. The battery printed nothing, produced no verdict for any later arm, and had to be killed — and the `SIGTERM` skipped the restore `finally`, leaving a mutated file in the working tree. | The test bounds its own wait (`async with asyncio.timeout(2)`), so a leaked slot fails in two seconds with a message rather than hanging. **The restore is verified by `filecmp` after every run**, and this one was repaired by copy from the snapshot rather than by `git checkout` — the files under test are uncommitted. | D386 is the false *kill* and D269 the false *survivor*; this is the **no verdict at all**, and it is the only one of the three that can also damage the tree. A battery arm whose failure mode is a hang is not a slow test: it is an arm that reports nothing about itself or anything after it. **Every arm asserting a resource is released needs a bounded wait.** | — |
| **D453** | — (a surviving arm, diagnosed rather than assumed.) | **A test that reads `.generated/` cannot detect a change to the renderer that produced it.** The arm mutating `MCP_MAX_CONCURRENT_READS`'s derivation survived: the test reads both fixtures' rendered `compose.env`, which is a build artefact refreshed by hand, so the mutated renderer never ran. And the guard that protects those fixtures compares **`schema_version` alone** — which a Compose variable can be added or changed without moving. `rendered_fixtures.py`'s own docstring says exactly this; this is the first arm that needed it to be false. | A second test renders **in process**, with two pool sizes that disagree so a constant cannot satisfy both. Both tests are kept and neither replaces the other: one proves the value reached a rendered artefact, the other proves the renderer derives it. | **The survivor's repair was the test, not the mutation** — but only reading what actually ran could say which. This is D212's stale artefact, in the one place the repository had already written down that its staleness check would not catch it. | — |
| **D454** | — (the second surviving arm.) | **Nothing in this repository had ever called `mcp_tools.register()`.** The arm making a metadata tool take a concurrency slot survived, because the rule — the two metadata tools answer from the lock and take no slot — lived in `bounded`'s docstring and in **no assertion at all**. Every tool test calls the module function the registration wraps; `test_mcp_route` asserts the registered *names* and never a registered *callable*. | A test calls `register()` against a recording registry and observes the semaphore from inside the work, with a **control**: the same rig, the same semaphore, a tool that does reach upstream, asserted to be holding a slot. Without the control, "the semaphore is full" is satisfied by a semaphore nothing touches. | **D444 and D450's family, third instance**, and the first one found by a surviving mutation rather than by a start. The seam is always the same: the wrapper between this repository's functions and the framework's, which unit tests reach around by design. | — |
| **D455** | `test_environment_gates.consumed_variables`, whose own comment says it looks for *"`os.environ["APG_…"]` anywhere in the body"*. | **It matches any subscript at all whose key is an `APG_`-prefixed literal.** A settings test that builds a LOCAL dict of eight strings and then does `del environment["APG_MCP_MAX_CONCURRENT_READS"]` was reported as consuming a live environment it never touches — an offline test, failing a guard about skipping versus erroring on a host. | **The scan is not narrowed.** Narrowing a currently-passing guard is a weakening and needs an ADR (§5), and this run does not own that decision. The test is rewritten instead: the incomplete environment is the constant and the complete one is built from it, which removes the subscript and reads better anyway. | The guard is **wider than its own comment**, which is this repository's standing defect in the mirror — a check whose evidence exceeds its stated scope produces false positives, and a false positive is how a guard stops being read. Worth an ADR-shaped decision by whichever session next touches the file; recorded here rather than fixed in passing. | — |
| **D456** | CLAUDE.md's open items: *"`MCP_MEMORY_LIMIT` is 384 MiB, inherited and not measured … ADR 0082 is the shape the measurement takes and it needs Run 6's four tools to profile. **Run 8 owns budgets.**"* | **Measured, and the obvious follow-up turned out to be a guard that cannot fail.** ADR 0082's rig with a zero-import control: the loaded runtime is **69.2 MiB** resident — `mcp.types` alone is 25 of them and `fastmcp` on top adds **0.6** — and one concurrent read at the byte ceiling costs **1.8 MiB**, linear to ten, against a zero-read control at 0.0. So `floor(share) = 128 + share x 4`, **148 MiB** at the default share. The mirror of `_validate_auth_memory` was then checked rather than written: `api.rest.pool_size` is capped at **100** by the schema, so the largest floor a valid manifest can ask for is **328** against a limit of 384 — **no document the schema admits could fail it.** | The limit stays 384 and stops being inherited: it is a choice with a measured floor and 2.6x headroom (**ADR 0131**). **No validator is written**, and the refusal is the decision. What replaces it is a test that reads the schema's own maximum: raise that bound past 128 and it goes red, naming the choice. | **A guard that cannot go red is §6's pattern with the polarity reversed** — not a value that looked measured and was not, but a check that would look enforced and enforce nothing (D277, D391). And the direction NOT taken is the load-bearing one: lowering the limit to the floor would free 256–384 MiB across two projects on a swapless host, and the profile is of the *interpreter*, not the container — **no `mcp` container has started anywhere.** Run 9's trip is where that number comes from. | 0131 |
| **D457** | §2: *"What Session 8 adds to the acceptance registry: **Nothing.** … Replace the placeholders; keep the IDs and their descriptions."* And §7: *"Host and external halves are written separately and merged."* | **Both cannot be true, and the model says which.** Run 6 replaced the five placeholders with CONTRACT tests, correctly — they are contract properties. Measured, with a control: all six Session 8 requirements carry **no environment marker**, and a claim over two of them is refused *"has no live proof: every test it names runs in a checkout, so no deployment is being measured"*. The control, `object_ownership`, resolves to `host`. **Session 8 had six requirements and could make no claim at all**; its gate would have had two modes and nothing to say in either. | **ADR 0132.** Four requirements gain **live proofs rather than twins** — the guarantee did not change, only where it is measured, and a second id would be one guarantee with two names (D47). Four **new** ids carry guarantees that are about a deployment and did not exist offline: `AGT-PLANE-001`, `AGT-TOKEN-001`, `AGT-CRED-001` (host) and `AGT-PUBLIC-001` (external). Eight claims. **`AGT-DRIFT-001` is deliberately in none of them**, because its guarantee is a property of the compiler and is complete in a checkout — D331's precedent, where two Session 7 claims were refused by the model and stayed out. | A plan can be internally inconsistent in a way no single sentence reveals, and this one was: §2 is right about the ids and §7 is right about the halves, and nothing connected them. **The control is what makes the answer usable** — without it, "every arm refused" is equally well explained by a rig that resolves nothing. | 0132 |
| **D458** | — (nothing had ever sent the assembled application a request over a socket.) | **Three facts about the wire, none of them the obvious answer.** Measured against the real application served by uvicorn, with controls. (1) Every reply is **`text/event-stream`**, SSE-framed as `event: message\r\ndata: {…}`, *even for a single JSON-RPC result* — `json.loads(body)` raises on a perfectly good answer. (2) `Accept: application/json` alone is answered **406**, `"Client must accept both application/json and text/event-stream"`. (3) In `stateless_http` mode **no handshake is required**: a bare `tools/call` with no `initialize` answers 200, and no `Mcp-Session-Id` is issued. Separately: the `scope` claim is an **array of strings**, not the space-delimited OAuth form — a hand-minted probe token carrying the string is refused with a message about shape, which reads as an authentication failure. | `mcp_rpc` in the deployment module sends both media types and parses the SSE frame, and the module's docstring carries the table. The external probe asserts **401 specifically**, and says in its own message that a 406 would mean it never reached authentication. | **406 is not 401**, and that is the whole row. A boundary proof written the obvious way — post JSON, read JSON — is refused by **content negotiation** before authentication runs, and a test asserting "an anonymous caller is refused" would go green having measured the media-type header. Run 7 asserted the application's route TABLE; this is the layer above it, and D444 is what an unexercised assembly costs one level down. | — |
| **D459** | `tests/contract/test_session_seven_gate_modes.py`, whose `test_the_gate_resolves_claims_for_its_own_session` exists to catch a session number left behind by a copy. | **The module was itself in the wrong session.** It carries `SESSION = 6`, left behind when it was copied from Session 6's, and the one test that reads it — `test_both_environments_carry_a_claim` — therefore asserted a property of **Session 6** inside a module about the Session 7 gate. Claims are cumulative, so it passed on Session 4's inherited `transport_boundary` **whether or not Session 7 had an external claim at all**. Measured: `claims_for_mode('external', 6)` is non-empty for every session from 4 onward. | The constant is corrected to 7, with the reason at its definition. Session 8's module asserts the session's **own** claims, from a table written out rather than derived from `claims_for_mode` — which would be the mechanism checking itself. | **A test that cannot fail for the thing it names**, in the file written to catch exactly that failure one layer down. "This mode carries a claim" is true from Session 4 onward and is not a property of any later session; the assertion had to name which claims before it measured anything. | — |
| **D460** | §5 Run 9: *"The MCP tool catalog, generated from the lock, and a page that **fetches its own assets** (D274)."* | **The catalog is not a page, and forcing it into the one surface that serves pages would be worse than not.** The documentation service renders **OpenAPI** documents through Scalar; a capability lock is not an OpenAPI document, and publishing one there needs a third Traefik router and a renderer for a format Scalar does not read. What the deployment already publishes about its agent surface is machine-readable and asserted: the `mcp` block's protocol revision, accepted token use, contract digest and tool count. | `docs/mcp-tool-catalog.md`, generated from the committed canonical contract by `bin/render-mcp-catalog.py`, with `--check` in the **Session 1 gate**. D274's instruction is obeyed in the form that applies: the document names tools, scopes, ceilings, ADRs and divergence numbers, and **every one of them is resolved against the authority that owns it** — with a control per scan. | D274's lesson is not about HTML. It is *the proof asked for the artifact's URL and never for what the artifact then asks for*. A catalog citing an ADR that does not exist is the same defect wearing different clothes: a document that reads correct and is not, offered to a reader who cannot check it. | — |
| **D461** | — (found by the arm that exists to check the checker.) | **The drift message raised while reporting drift.** `render-mcp-catalog.py --check` printed `{CATALOG.relative_to(REPO_ROOT)}`, and `relative_to` **raises `ValueError`** for a path outside the repository. The only caller that reaches it is the guard-the-guard test, which perturbs the catalog at a temporary path — so the branch that reports a failure turned into a traceback that hid it. | A `shown()` helper that falls back to the absolute path. Four call sites, one function. | **The guard-the-guard arm found a defect in the guard**, which is what it is for and the first time in this repository that it has. A diagnostic is code: it has a failure path, and its failure path runs precisely when something is already wrong. D391 is the same family — a guard whose result was discarded — arriving here as a guard whose *message* could not be printed. | — |
| **D462** | The Session 7 guide's step 0, carried into Session 8's: *"Re-render the fixtures — ON THE HOST, after transport (D383)"*, with the two **example** manifests. | **That is half of what `.generated/` holds.** Run on the host at `42db9e4`, with both fixtures freshly re-rendered at v12, `bin/session-01-check.sh` exited **5** at step 8: *"these projects were rendered by an older release: alpha-dev (v11), beta-dev (v11)"*. The evidence step compares **every** rendered project — and the host also carries `.generated/alpha-dev` and `.generated/beta-dev` from real deploys, which the example manifests do not touch. A collision count over two schema versions compares different documents, so the refusal is right. | Step 0 re-renders **four** projects: the two example fixtures and the two real ones, with `project.alpha.yaml`/`project.beta.yaml` and `capabilities.yaml`. All four are `--render-only`, all four need **no root**, and all four reached v12. `session-01-check` then passed on the host. | **D383 said where to re-render and not what.** The fixture guard (`rendered_fixtures.py`) only knows about the two example keys, so it reported `current` while two other rendered projects sat a version behind — the guard was right about its own question and silent about the one the gate asks. A second finding rode along: `op` **cannot reach the Docker daemon**, so step 7's *"no project container is running"* half is not proved by an operator-run gate. The gate says so in as many words rather than passing quietly (ADR 0018), which is the behaviour to keep. | — |
| **D463** | `MCP_SERVICE`'s own docstring: *"it is **deliberately absent from `POST_BOOTSTRAP_SERVICES`** … every other application service is in that tuple because it logs in as a role the bootstrap plane must activate first. This one has no role to activate (D410)."* Asserted by a passing test. | **Every word of that is true, and the agent plane's first start anywhere exited 1 because of it.** On the host at `bf1d398`: `IsADirectoryError: Is a directory: '/etc/mcp/jwks.json'`, on both projects. **Docker creates a bind-mount source that does not exist as a DIRECTORY**, so the fourth verifier opened a directory where its key set should be. Read out of the deploy's line order: `install_rendered` (1327) replaces the rendered directory, **step 5 starts everything not deferred (1332)**, `render-jwks` writes the key set (1413), the lock is compiled (1453). The agent plane is started **eighty lines before the two files it mounts are written**. The deploy then failed at 1413 — `staging.replace()` onto a directory raises — so the deployed document stayed **v11** and all four deploys failed identically. | **ADR 0133**, and it adds a concept rather than redefining one. `POST_ARTIFACT_SERVICES` carries the second reason — *cannot start until the deploy has written the files it mounts* — `DEFERRED_SERVICES` is the **computed** union, and the deploy defers that. D410's assertion and its docstring stand unchanged. And because the ordering fix closes this instance and not the class, the deploy now **proves its file mounts exist before each start**, derived from the override it is about to write. | **One name was carrying two ideas.** A service landed in that tuple for a stated reason (a database role) and the deploy used it for an unstated one (an artefact written late). PostgREST needs both, so membership satisfied the second **by accident** and nothing ever separated them; the agent plane needs only the second, was correctly excluded for a reason about the first, and lost the second with it. **§6's question 5** — *when a decision is implemented, which of its callers got it?* — and **D381's family**: the mount was written in the right run, by an author who cited D381 while writing it, and the START ORDERING was the caller nobody asked. `deploy-project.py` already carried a comment naming this exact Docker behaviour, **written for PostgREST**. | 0133 |
| **D464** | `test_no_operator_command_puts_a_service_directory_on_the_path`, whose docstring names one thing: a `bin/` command doing `sys.path.insert(0, REPO_ROOT / "services" / "auth-api")` so an image-only package becomes importable in a checkout. | **It is a text scan for two unrelated strings**: `'"services"' in source and "sys.path" in source`. Run 10's mount pre-flight read `document.get("services")` — a YAML key — and `deploy-project.py` has a legitimate `sys.path.insert(…, "src")` twenty lines from the top. The guard reported a command that does nothing of the kind, in the run whose whole subject is a guard that was too narrow. | **The scan is not narrowed** — that is a weakening of a passing guard and needs an ADR this run does not own. The parsing moved instead, and it moved somewhere better: `runtime_override` **builds** the override, so it is the module that should read it back. `mount_sources` and `override_service_names` take the rendered bytes, and the command now mentions neither `"services"` nor `yaml`. | **D455's family, one session later, and the mirror of this run's own subject.** D463 is a check whose evidence was too NARROW — one name for two ideas. This is a check whose evidence is too WIDE — two strings standing in for a construct. Both pass for exactly as long as their approximation happens to coincide with the property. The repair here was free because the code was better the other way; the next one may not be, and the row is what that reader needs. | — |
| **D465** | `deploy-project.py`, above the lock step: *"`--outputs` is the document THIS deploy is about to write, so the lock is compiled last, from the **rendered outputs** rather than from the previous deploy's."* | **Two errors in one sentence, and it passed `deployed_path`.** (1) The deployed document IS the previous deploy's — step 7 writes the new one 140 lines later. (2) The two branches carry `routes.rest` in **different shapes**: rendered it is a string, `"https://…/api/rest"`; deployed it is a published-route **object**, `{"status": "ready", "url": …}`. `command_lock` reads `outputs["routes"]["rest"]` and wants the URL — so it got a dict, compiled happily, and **wrote a lock whose `upstream` was an object**. The failure surfaced at container start, one step and one restart later: `LockError: the lock.upstream is not str`. Measured on the host after D463's fix let execution reach it. | The deploy passes `rendered_path(key) / "outputs.json"` — the same directory the lock is written into. And `command_lock` now **refuses a deployed-shaped document by name**, exit 3, naming both branches. Verified end to end: rendered → a string upstream that `load_lock` accepts with all four tools; deployed → refused. | **D389's shape, and the third time this session.** One field, two branches, different shapes, a consumer reading the wrong one. The sharp part is what the wrong input produced: not an error but an **artefact** — a lock, written to the rendered directory, mounted into a container, and refused four steps away from its cause. A wrong input that yields an artefact is worse than one that yields an exception, because the artefact gets published. **And D463 is why this was found at all**: one unrun proof hides the next, and one broken start hides the next. | — |
| **D466** | Every gate's `--help` since Session 4: `--mode external … --ssh-destination USER@HOST`, and the guides repeat `<dest>`. | **There are two accounts and only one of them works, and the obvious choice is the wrong one.** `apg-agent` is the read-only diagnosis account (ADR 0071) and the external suite's connection-tooling proofs exercise the **access broker**, whose policy is *"an enumerated grant of one account to one project's named profiles"* — and that account is `op`. Run with `apg-agent`, two Session 4 proofs failed on `sudo: I'm sorry apg-agent. I'm afraid I can't do that`, and the positive control fired first, exactly as written: *"Every refusal below would then prove nothing."* | Both the gate's `--help` and the operator guide name **`op@HOST`** explicitly, with the reason. `sudo -n` on the trampoline needs no password and no TTY for that account, which is what makes the external half runnable without a human. | **`USER@HOST` is a placeholder that looks like an instruction.** The account is not a preference: it is the one the published policy grants, and picking the *more restricted* of the two — which is the safer-looking choice, and the one a reader who has just been told `apg-agent` is for read-only diagnosis will make — fails. The control saved it from being read as a broker defect. | — |
| **D467** | Session 8 Run 2's re-derived assertion: *"the roles holding `USAGE` on the private schema are exactly the roles that run the hook, plus the services that administer what lives there"*, measured with `has_schema_privilege`. | **It reports `true` for a role that was granted nothing.** On the deployed cluster: `nspacl` on `app_private` names nine roles and **`app_runtime` is not one of them** — migration 0006's `REVOKE ALL` worked and holds. But `app_runtime` is a member of `authenticated` (ADR 0041's design, SEC-DBX-002) with **`rolinherit = false`**, and `has_schema_privilege` reports a privilege held *directly or by way of membership* — membership, not inheritance. So it answers `true` for a privilege the role cannot passively exercise. Strip the four service roles from the catalog and what remains is **exactly** `AUTHENTICATOR_REQUEST_ROLES`. | **ADR 0134.** A question about a GRANT is asked of `pg_namespace.nspacl` through `aclexplode` — what a `GRANT` writes and a `REVOKE` removes. A question about REACH sets the role and tries it, with the control that `app_runtime` must still read `api.notes` **through** `authenticated`. Two assertions, because each can be true while the other is false. The exact-set form stays; `⊇` is still refused (D300). | **Migration 0006 wrote this trap down — for the table twin — and the test written two sessions later walked into the schema one.** Its comment reads: *"the obvious test for this migration fails while the property is true: `has_table_privilege(...)` -> true; `SET ROLE app_runtime; SELECT ...` -> denied. Both are correct."* `has_table_privilege` and `has_schema_privilege` mislead for the same reason, about the same role, for the same design. And it could not fail on a workstation: the proof is `live_host` and had **never executed** (D211–D214). §6's questions 2 and 5, arriving together. | 0134 |
| **D468** | Two Session 3 allowlists, enumerated by name: the functions a request role may `EXECUTE` in `app_private`, and every function schema `api` holds. | **Migration 0018 added three objects and neither list was updated.** `anon` can execute `agent_claims_are_current`; schema `api` holds `mcp_agent_context` and `owner_activity_report`. All three are 0018 working as designed — and both assertions were **right to fail**: they are allowlists, and new objects appeared in them. | The lists gain the three by name, with 0018's own reasoning rather than a shrug. `agent_claims_are_current` goes to **all five** request roles because `role` and `token_use` are independent claims, so every combination of physical role and hook branch is reachable — measured, a human token naming the agent role was refused `42501` instead of `AP401` (D393 through a missing grant). The two `api` functions are `REVOKE ALL … FROM PUBLIC` and granted to `agent_reader` alone (ADR 0118). **No list becomes a subset check.** | Run 2 wrote migration 0018 **and** re-derived one of the three Session 3 assertions it invalidated. It did not ask which others read the same catalog — which is §6's question 5 asked of a migration rather than of code. Both surviving assertions are `live_host`, so a green offline suite of 3,786 tests said nothing about either. | 0134 |

---

## 2. What Session 8 adds to the acceptance registry

**Nothing.** The five requirement IDs already exist and point at placeholders:

| ID | What it must prove |
|---|---|
| `AGT-READ-001` | An agent read through MCP equals the equivalent PostgREST result |
| `AGT-SQL-001` | No agent input accepts SQL, a SQL fragment, or a raw query string |
| `AGT-SCOPE-001` | Tool discovery is filtered by the caller's scopes |
| `AGT-DRIFT-001` | Adding an API operation exposes no capability without a `capabilities.yaml` change |
| `AGT-BUDGET-001` | Row and response-size budgets are enforced server-side |

`SEC-INJ-001` is also Session 8's and lives in `tests/security/`.

**Replace the placeholders; keep the IDs and their descriptions.** Adding a new
ID requires grepping the registry first — **ADR 0089/D279**: three of Session 6's
six "new" IDs were already taken, and because `claim_session` derives from
`max()`, one would have turned three earlier sessions' evidence red while the
other vanished from the gate.

`AGT-SQL-001` is the load-bearing one. Its own module says so: *the product's
central claim is that an agent has no path to arbitrary SQL under any
authentication, and that claim is only worth what this test proves.*

---

## 3. Environment feasibility

| Requirement | Status | Note |
|---|---|---|
| A FastMCP release | **must be measured** | Version, protocol revision, and whether it imports on the locked base image. D406. |
| Connection budget | **no change** | MCP holds no database credential. D407. |
| Memory | **must be measured** | A fourth application container has a floor. ADR 0082 is the shape: one profile per process with a no-work control, because `ru_maxrss` is a high-water mark already set by earlier work. |
| PostgREST reachable from MCP | **project internal network** | Existing. MCP joins `internal` and `edge`; it needs no host port. |
| Agent tokens | **exist and are issued** | `POST /auth/agent-token` works and is tested. What has never happened is one being *accepted* anywhere. |
| An agent with an owner | **exists** | `agents.owner_id`, `NOT NULL`. Session 7's fixtures create one. |

**The unmeasured boundary that stays unmeasured:** IPv6. Eight
`APG_PUBLIC_IPV6` proofs have never run, and running them from a machine without
IPv6 reports every port closed — a fact about the scanner.

---

## 4. Safety plan for irreversible operations

Four operations cannot be undone by re-running a command.

**1. Moving `CURRENT_SESSION` to 8.** It arms the `session8` profile, so the next
deploy of *any* project tries to start an MCP container. It must fail closed
without its inputs rather than start without them. The operator guide says so
**before** the step (D410).

**2. Activating `agent_reader`.** Granting the authenticator membership in a role
is a bootstrap-plane change (D102) and widens what a token may name. It is
reversible in principle and disruptive in practice. It requires the ADR from
D400 and the re-derivation of two assertions.

**3. Applying migration 0018.** Forward-only, `freeze-lock` after writing it,
applied as `migration_user` and never as a superuser — **D285**: every offline
rig applies migrations as `psql -U postgres`, and a superuser bypasses the
ownership check that made 0012 and 0013 fail on a real cluster.

**4. Publishing a capability lock.** The deployed lock is what the runtime
obeys. A lock built from an unreviewed OpenAPI capture is a capability surface
nobody approved, which is the whole failure mode `capabilities.yaml` exists to
prevent.

**The standing rules apply unchanged.** `sudo` needs a TTY, so anything
privileged that mutates is run by a human at a terminal. Read-only diagnosis is
not — but note **D380**: `apg-diag`'s service allowlist has no `auth` and no
`storage`, and will have no `mcp` either unless Session 8 adds it. Session 7 was
sent to a terminal twice for a read-only question.

---

## 5. Build order

Runs are the unit. Each ends with the offline gate green on a clean tree, and
CLAUDE.md §4's procedure applies to every one: measure third-party behaviour with
a **control** before writing anything that depends on it, write the ADR when the
measurement decides something with alternatives, implement, then **try to break
the tests** with a mutation battery whose failures are fatal (D269) and which
asserts *how* each mutation failed (D386).

### Run 1 — The route, the document, and the two boundaries — **Done.**

- **`routes.mcp` into the deployed document** (D395), with the rendered/deployed
  route sets compared as sets.
- **Outputs v12**, chosen from the whole session surface (D402).
- **The ADR from D396**: what `token_use` the MCP surface accepts, and the
  mirror refusal at the application API restated rather than assumed.
- The connection budget's considered zero, asserted (D407).

**What was measured.** A rig in `/tmp` minting an agent token through
`AuthService.agent_token` — the path `POST /auth/agent-token` takes, hasher and
repository included — with a human token from the same service and the same
signing key as the **control**, and a negative control run first (one expectation
inverted → `DIVERGES`, exit 1, so the rig can tell success from failure).

The result is ADR 0115's "What was measured" table, and the finding that matters
is not any single claim: **the two token classes are structurally identical.**
Same issuer, same audience, same twelve claims, same key set. `token_use` is
`agent` against `access`, `sub` is the agent id, `credential_version` is **0**,
there is **no `agent_id` claim** — D396 and D397 both confirmed as written. A
surface that does not read `token_use` is defended by nothing else in the token,
which is why ADR 0115 exists rather than being left implicit.

**D395 confirmed from the repository**, not only from the host: the deployed
branch of `schemas/outputs.schema.json` required six routes and declared six,
`mcp` among neither, while the rendered branch has required it since version 1.

**What was built.** ADR 0115. Outputs **v12** — `routes.mcp` as a
`publishedRoute` and a `$defs/deployedMcp` block in `deployedApi`'s shape
(protocol revision, `authorization_spec_conformant`, `accepted_token_use`, the
canonical-contract and lock digests, the tool count), `MCP_NOT_PUBLISHED`, the
`mcp`/`routes.mcp` coherence rule beside the `api`/`routes.rest` one, and
`migrate_v11_to_v12`. `AGENT_PLANE_SESSION = 8` in the deploy path, above
`CURRENT_SESSION` on purpose (D414).

**The battery: 7 mutations, 7 killed, every one `FAILED` rather than `ERROR`,
each with its control green in the same invocation.** M1 the deployed branch
stops requiring `routes.mcp`; M2 `build_deployed_document` drops it from its key
list — *D395's literal state*; M3 the application API accepts `agent`; M4 the
schema permits either token use; M5 `MCP_NOT_PUBLISHED` loses a member; M6 the
agent plane acquires a budget term; M7 the deployed block publishes a pool size.

**And the controls earned their place.** The first run reported M3 and M7 as
survivors — both targets had died, but their *controls* had gone red too, because
the control test genuinely read the mutated value. That is a false kill caught in
the direction D386 warns about, and the repair was the control, not the test.
**A mutation whose control also fails is not evidence, whatever the target did.**

### Run 2 — Migration 0018, the agent read plane — **Done.**

- Activate `agent_reader` — bootstrap plane, not the migration plane (D102) —
  and **re-derive** the two assertions D400 names, exactly rather than loosely.
- Extend the pre-request hook's physical-role branch **from 0013's body, not from
  memory of it** (D270).
- `api.mcp_agent_context()` returning agent id, role, scopes, `authz_version`
  and `owner_id`.
- One named read report RPC.
- Grants to the agent-reader role, explicit `REVOKE … FROM PUBLIC` beside every
  `CREATE FUNCTION` (D57, re-measured as D262), and `RESET ROLE` **below** the
  privileges block (D285).

**What was measured.** A rig on the locked image: all **eighteen** migrations
applied as `migration_user` over TCP — dbmate's route, not `psql -U postgres` on
the socket, which is the superuser route that let 0012 pass four sessions of
green proofs while being unappliable (D285) — and **every request made by
connecting as the authenticator and issuing `SET ROLE`**, which is PostgREST's.
A privilege refusal measured as a superuser measures nothing (ADR 0065/0066).

**23 arms, 23 as designed**, interleaved with controls. The agent read plane
works end to end: the hook establishes the **owner** as `app.user_id` and the
agent as `app.agent_id`; the agent reads `a1,a2` and not a second owner's `b1`;
its report says `2 2 1 1` and so do the rows it can read, and so does what its
owner reads with a human token, while a different owner reads `1 1 1 0`. Five
refusals — stale `authz_version`, `credential_version` 1, a human role, a
narrowed scope set, an unknown agent — all `AP401`, with the unmutated request
still serving as the control. **No policy was changed and none needed to be.**

**Three findings, and two of them changed the design.**

**D417** — the rig's first run refused a human token naming the agent role with
`permission denied for function auth_claims_are_current` instead of `AP401`. The
first draft had granted the new helper to the agent role alone, reasoning that a
human never reaches the agent branch. `role` and `token_use` are **independent**
claims, so every combination of role and branch is a reachable request. Both
helpers now go to all five request roles. **D393 through a missing grant.**

**D418** — the rig then argued for granting the report to `authenticated`, so
AGT-READ-001 would have a human half to compare against. **ADR 0003's domain is
frozen**, and a read RPC a human may call is a fifth operation. The proof moved
instead, to the row surface — the stronger comparison of the two.

**D416** — `AUTHENTICATOR_REQUEST_ROLES` exists so the proof reads the
enumeration instead of restating it, and there were **four** restatements:
two in `check_violations`, one in the bootstrap test module, and a two-name
forbidden literal that would have left `app_runtime`, `auth_service` and
`storage_service` forbidden by nothing.

**What was built.** ADR 0116, 0117, 0118. Migration **0018**, frozen. The hook's
fifth definition — **zero statement lines removed from 0013's, twenty-one
added**, asserted mechanically rather than claimed (D270).
`agent_claims_are_current` returning the owner. `api.mcp_agent_context()`
(definer, no argument) and `api.owner_activity_report()` (**invoker**, reading
the `api` views so counting rows does not widen 0004's boundary). A new
`agent_rpcs` section in the reviewed surface contract, with `published_objects`
beside `declared_objects` because those stopped being the same question.

**The battery: 15 mutations, 15 killed, every one `FAILED` rather than `ERROR`,
each control green in the same invocation.** And the controls earned their place
a second time: M2 first reported as a survivor because both branch tests share
one extractor, so removing the marker reddened the control too. The extractor
gained a real failure message and the control was swapped — **a mutation whose
control also fails is not evidence, whatever the target did.**

### Run 3 — The capability compiler — **Done.**

- Capture the live PostgREST OpenAPI through the documentation token, normalise,
  and **compare against the approved snapshot**. Drift fails.
- Compile `contracts/snapshots/mcp/mcp-capabilities.canonical.json` from
  `capabilities.yaml` + the reviewed surface. Project-neutral.
- The deployed `mcp-capabilities.lock.json` resolves project-scoped paths and
  hashes.
- The compiler may **read** OpenAPI and may never **infer** a capability from it
  (AGT-DRIFT-001).

**What was measured.** A live PostgREST on the locked image, against a cluster
carrying all eighteen migrations, configured as `compose.yaml` configures it, and
captured **through a documentation-role token** — because `follow-privileges`
builds the document as the role of the request, and an anonymous capture would
describe `anon`'s surface, which is nothing. **10 measurements, 10 as designed.**

**The live document publishes no `operationId` anywhere** (D419). Swagger 2.0,
where the field is optional, and every operation without one. The committed
snapshot said the same, but it is a *normalized* capture — evidence about
`openapi_normalize`, not about PostgREST — which is why this was measured live.

**And ADR 0118 now holds against the artefact rather than the intention.**
`rpc/mcp_agent_context` and `rpc/owner_activity_report` are absent from the
document built as `api_documentation`; all four published objects are present as
the control. Run 2 asserted that from the migration text and the approved
snapshot. This is the running service agreeing.

**What was built.** ADR 0119 and 0120. Five capabilities in
`capabilities.example.yaml` behind **four tools**, with `tool`, `kind: metadata`
and `source: lock` extending v1 — nothing renamed, nothing removed, so no bump
(D403). `capability_compiler`, pure over its arguments. `bin/mcp-contract.sh`
with `compile`/`check`/`lock`, and **no writer in the check path** (ADR 0050).
The canonical contract, committed and project-neutral.

**Two findings.** **D420** — `load_capabilities_manifest` refused *every*
enabled capability with a reason that **expired in Session 5**, and survived
three sessions because nothing ever enabled one. **D421** — a flat
`discovery_scopes` list cannot tell "any of" from "all of", so `run_report` would
have been advertised to an agent holding half its scopes; found by reading the
compiler's own output, which is the only way that class shows up.

**The battery: 11 mutations, 11 killed**, every one `FAILED` rather than `ERROR`,
each control green in the same invocation. M1 is the one that matters: the
compiler is made to enumerate the reviewed surface, and **AGT-DRIFT-001** dies —
which is the test written the only way that means anything, by *adding a real
operation to both the contract and the snapshot* and asserting the compiled
bytes do not move.

### Run 4 — The runtime and the fourth verifier — **Done.**

**What was measured, and every arm had a control.**

**FastMCP, against the locked `python:3.12-slim` digest on Docker 29.5.2.** The
runbook's **3.4.5 exists** — D406 predicted a fabricated number and was wrong
about that. What was wrong is this repository's own entry: **2.14.1, locked since
Session 1, installs and does not import** (`ModuleNotFoundError: No module named
'pydantic_settings'`), because it declares `mcp>=1.24.0` with no ceiling, pip
resolves mcp 2.0.0, and that major dropped a dependency fastmcp imports directly
and never declared (**D423**). And the adoptable version is **bounded by
FastAPI**: `fastmcp-slim[server]` moved to `starlette>=1.0.1` at 3.4.1 while
`fastapi==0.121.2` requires `starlette<0.50.0`. Bisected, one arm per patch
release — **3.4.0 resolves, 3.4.1 through 3.4.7 do not** (**D424**). 3.4.0 then
installed for real beside the whole pinned set: every package imports, `pip
check` clean. Locked with `--update --packages-only`, and the diff confirms it
moved **one package and carried all ten image digests forward unchanged**.

**The framework's own surface, from a RUNNING server.** `verify_token(token:
str) -> AccessToken | None` is handed the raw compact token, which is what Run 5
forwards. No header → 401, bad token → 401, good token → 200. And the finding
that mattered: a server asked to `initialize` at `2025-03-26` **answers
`2025-03-26`**, so a *negotiated* protocol revision is a fact about the client
(**D428**, ADR 0123). Also measured, and it turns `authorization_spec_conformant`
from prose into an observation: a 401 from a bare `TokenVerifier` carries **no
`WWW-Authenticate` challenge**, which RFC 9728 requires.

**D409 was the bullet to check, and the answer was worse than it predicted.**
ADR 0088's recreate list had never moved for the **third** verifier either.
`bin/rotate-signing-key.py` still read `VERIFIERS = (REST_SERVICE,)` — one of
three — while ADR 0113's own Consequences section says *"storage joins the
recreate list"*. A rotation would have promoted as soon as PostgREST
acknowledged, with storage still on the retired set: **D276's symptom** (D425).
Underneath it, two more: one `VERIFIER_JWKS_PATH` for verifiers that read three
different paths (**D426**), and `docker exec … cat` as the read mechanism when
the locked PostgREST image is **distroless and exits 127** for both `cat` and
`sh` — so `acknowledge` could never unblock a promotion (**D427**). That last one
gives the three-session-old rotation-window open item a measured cause.

**What was built.** ADR 0121, 0122 and 0123. The agent plane as a **third
`APP_MODE` of the one image** — one build context, because a second service
directory could not import `LocalKeySet` and the fourth verifier acquiring a
second key-set parser is exactly how D381 happened to the third.
`app/mcp_runtime.py`: the key set from the rendered file by path, and an
`AgentTokenVerifier` whose `jwt.decode` arguments and option flags are
`AuthService.authenticate`'s line for line. `McpSettings` and `load_mcp`, which
**refuse to start** when handed a signing key or any database setting — making
D407's zero share of the connection budget a decision rather than an oversight.
The `mcp` Compose service, hardened as storage is, `profiles: [session8]`, and
deliberately **absent from `POST_BOOTSTRAP_SERVICES`** (D410). The verifier
roster as a table, with all three verifiers and their own paths.

**No tools are registered**, and that is Run 6's. A placeholder would be a
discovery response that lies, which is D421's lesson.

**What Run 4 did NOT ship, and why.** The `mcp` service carries **no
healthcheck** (**D429**). The probe was written and removed:
`test_the_service_never_constructs_a_network_jwks_client` forbids every network
name under `services/auth-api/`, correctly, and weakening a P0 guard to fit a
liveness check is the wrong trade. Run 7 owns the health surface and the
reasoning is left at the Compose entry for it. Recorded in the same row: that
guard is **escaped by an inline `python -c` in the Dockerfile**, which is D277's
shape and a decision somebody should take deliberately. `MCP_MEMORY_LIMIT` is a
rendered constant at 384 MiB, **inherited and not measured**, flagged as such at
the constant — ADR 0082 is the shape the measurement takes and **Run 8 owns
budgets**.

**The battery: 12 mutations, 12 killed**, every one `FAILED` rather than `ERROR`,
each control green in the same invocation. **And the battery was itself
controlled** — two self-check arms confirmed it reports `ERRORED` for an
import-time break and `SURVIVED` for an uncovered change, because a battery that
has only ever printed KILLED has not shown it can print anything else (D386).
M9 is the one to read: it deletes the storage row from the roster, reproducing
the Session 7 defect exactly, and the derived sweep and the literal anchor both
die.

Suite **3563 passed, 261 skipped**.

### Run 5 — The authorization path — **Done.**

**What was measured, against a live PostgREST and a running FastMCP.**

**The RPC, on the locked digest with all eighteen migrations applied and real
RS256 tokens.** Nine arms, every one with a control. An agent token resolves its
own context at **200**, as a JSON **array of one object** carrying `agent_id,
role_name, scopes, authz_version, owner_id` — and `owner_id` is the agent's
owner, which is ADR 0117 answering over HTTP rather than in SQL. Three arms
changed the design:

* **D432** — migration 0018's comment says the function returns *"zero rows when
  the caller is not an agent"*. Over HTTP that branch is **unreachable**: the
  pre-request hook refuses an unknown agent with `401 PT401 / AP401` and the
  function is never entered. So zero rows is a **refusal**, not an empty
  context; treating it as "not an agent" would hand a tool an agent with no
  scopes and no owner, from a state the product does not produce.
* **D433** — an anonymous request is refused **401 with a body of `42501
  permission denied`**, and a human `access` token **403** on the same SQLSTATE.
  Neither status nor body identifies the cause, and the three measured 401s
  (`PT401`, `PGRST301`, `42501`) are indistinguishable. So **no upstream status
  or code is relayed**; a refusal says nothing (ADR 0097). D417 from the other
  side.
* The forged-signature and human-token arms are the controls that make the rest
  mean something: `PGRST301` and `403` respectively, not a blanket refusal.

**The framework's ordering, from a running server.** An unauthenticated request
is answered **401 with no middleware hook reached at all** — so ADR 0115's
"refused before any lookup" is structural rather than something this run's code
enforces. `on_request` fires **once per HTTP request**, before both
`on_list_tools` and `on_call_tool`, and reaches the **raw compact token**.

**The cache, measured against the obvious wrong answer.** Twelve concurrent
requests with twelve different tokens, both implementations running at once:

    ContextVar, reset in a `finally`    0 of 12 saw another caller's context
    CONTROL -- a module-level dict     11 of 12 saw another caller's context

and the control is **correct on every sequential request**, which is why the
concurrency arm exists. A suite without it passes the broken implementation.

**What was built.** ADR 0124 and 0125. `mcp_upstream.py` — one RPC, the caller's
own token in `Authorization` and **no header naming a principal**, with the
response contract as a pure function so every refusal branch is reachable
without a socket. `mcp_authorization.py` — resolution in `on_request`, held in a
`ContextVar` keyed by a **SHA-256 fingerprint** so that a value outliving its
request becomes a *miss* rather than a *leak*, reset in a `finally`.
`McpSettings.postgrest_url`, parsed rather than trusted: `postgres://` and
userinfo are both refused, because `PGRST_DB_URI` is a conninfo naming a role and
sits metres away in the same file.

**D431 is the row to read.** Run 4 deferred the transport guard (D429) and Run 5
could not. Measured: `test_the_service_never_constructs_a_network_jwks_client`
banned five transport names and **admitted the boto3 `storage_client.py` has been
making real R2 round trips with for a whole session**. It was too wide and too
narrow at once — D277's shape. Replaced by three checks that are **strictly
stronger**: `PyJWKClient` banned outright, key sets provably built only from a
local read, and every transport (now eight names, boto3 included) refused outside
a declared allowlist row. It fails for a case the old one passed.

**The battery: 17 mutations, 17 killed**, each `FAILED` rather than `ERROR` with
its control green in the same invocation, and the harness re-checked against an
import-time break and an uncovered change so that `KILLED` still means something.
**Three arms survived the first run and two of the three were the mutation's
fault** (D435) — a mechanism swap that still wrote through the real one, and a
validator case that a *different* rule refused. The third was a genuine defect in
the tests: **D434**, the `HTTPError` branch every real refusal takes had never
executed, because the recorder returned a 403 the way `urlopen` never does.

Suite **3597 passed, 261 skipped**.

### Run 6 — The PostgREST adapter and the four tools — **Done.**

**What was measured.** Four rigs against a live PostgREST on the locked digest,
eighteen migrations applied, **two owners and two agents** throughout so that a
working filter could never be confused with an empty result.

The operator spellings, `select=`, `order=`, `limit=`, and the 400 an unknown
column gets. Then the two findings that changed the code:

* **D437** — the injection arm. `title=neq.<value>` with value `zzz&limit=1`:
  **percent-encoded → 3 rows**, **unencoded → 1 row**. The first version of this
  measurement proved nothing — both arms returned zero, one because the value
  matched nothing and one because **RLS already excluded the injected owner**.
  Two arms agreeing for different reasons is not a control.
* **D438** — the in-list rule, and **both obvious answers are wrong**.
  `in.(weird%2Ctitle)` → **0 rows**: percent-encoding does not remove a comma
  from list syntax, because PostgREST decodes before it parses. And the SQL
  convention for an embedded quote → **0 rows**; a **backslash** escape → 1.
  Verified across eight awkward values against the same rows fetched by `eq.`,
  then re-verified end to end by firing **the product's own builder** at the
  live service: 6 of 6, with the other owner's agent returning different counts
  on every arm.

Both wrong answers fail by matching **nothing**, which reads as an empty result
rather than an error. That is why the escape rule is a test and not a comment.

**What was built.** ADR 0126 and 0127. `mcp_lock.py` — the deployed lock, read
once at startup and validated strictly, because it decides which columns a
caller may name and which operation is reached. `mcp_query.py` — the
construction rule AGT-SQL-001 reduces to: the operation is chosen **by name from
the lock**, columns/operators/orderings are checked against frozen sets before a
request is built, and values are escaped **by position**. `mcp_tools.py` — the
four tools, two answering from the lock alone and two reaching PostgREST with the
caller's own token, plus **two independent budgets**: the lock's row ceiling,
which a caller may only lower, and a serialized-byte ceiling a caller cannot
express at all.

**D436 is the row to read.** Run 3's compiler calls the lock's `upstream` *"the
ONE address the runtime may call"*, and it is the project's **public**
`routes.rest` — unreachable from the `internal` network the agent plane runs on.
The runtime dials the internal address Run 5 established; the lock's `upstream`
is the surface's published identity, and a test asserts nothing dials it. D389's
shape, in a compiled artefact.

**D439: the placeholder replacement and `CURRENT_SESSION` cannot be split.**
D414 assigned the five `AGT-*` placeholders to Run 6 and the constant to Run 7.
`test_every_later_requirement_has_a_placeholder` and
`test_no_requirement_at_or_before_the_gate_session_remains_future` are exact
mirrors on the gate session, so whichever half moved first would go red. **And
the count is six** — `SEC-INJ-001` also targets session 8 and was not in D414's
list. Run 6 therefore moves **`CURRENT_SESSION` to 8** in the same commit as all
six replacements, which is what Session 7 Run 9 did for the same coupling. Run 7
keeps the publish work.

`SEC-INJ-001` gets its own security module, asserting the property from the
attacker's side: given full control of every input, the request's **structure**
does not move, and a column or an operator is refused against the lock rather
than escaped — because an identifier has no safe encoding.

**D440** — ADR 0124's allowlist needed a third row for a module that does **not**
reach the network: `mcp_query` imports `urllib.parse` to encode, and the scan
sees the same top-level package a sender presents. The row is added and the test
tightened, so an allowlisted encoder that grew a `urlopen` is refused by its own
row.

**The battery: 17 mutations, 17 killed**, each `FAILED` rather than `ERROR` with
its control green in the same invocation. O2 is the one to read — it swaps the
measured backslash escape for the SQL convention, which is the mistake this run
came closest to shipping.

Suite **3662 passed, 255 skipped**.

### Run 7 — Publish — **Done.**

**What was measured, and three of the four bullets turned out to be decisions
rather than settings.**

**D441** — the plan asks for Host/Origin protection. At the pinned fastmcp
**3.4.0**, `http_app` has no `host_origin_protection`, `allowed_hosts` or
`allowed_origins`; they arrive at 3.4.7, above ADR 0121's measured ceiling. And
the runtime does nothing about either: a cross-origin request with a valid token
is **answered 200**, and so is one with `Host: evil.test`. What stops a browser
today is the **405** on preflight — the absence of a CORS middleware, which is a
property of the edge rather than of this process.

**D442** — a `custom_route` mounts at the application **root**, not under
`http_app(path=…)`, and is **not** behind the verifier. Route table: `/mcp`,
`/health/live`, `/health/ready`; `GET /mcp/health/live` is a 404. Health answers
**200 without a token**, with the control that makes it mean something —
`POST /mcp` without one is still **401**.

**D443** — D408 predicted `/mcpx` would reach a different backend. It reaches
**none**: `/mcp` is top-level, so a sibling matches no router and gets Traefik's
own 404. The prediction assumed the storage shape, where a parent catches the
sibling.

**D444 is the one to read, and it is D381 again.** `AgentTokenVerifier` was
"structurally typed against the framework rather than subclassing it: the
protocol is one coroutine". It is not: `http_app` calls `auth.get_middleware()`
while assembling. A duck-typed verifier raises `AttributeError` **on the first
real start anywhere** — and it survived Runs 4, 5 and 6, three green batteries
and 3,662 passing tests, because **nothing had ever built the application.**
Every test constructed the verifier and called `verify_token` directly. The seam
nobody crossed was construction, not behaviour.

**What was built.** ADR 0128. The router: one published path in ADR 0108's
two-matcher form, **stripping nothing** — because the container serves `/mcp` at
its own root, so the published and served paths are one string and a strip would
forward `/` to a 404. No CORS and no buffering, each absent for a stated reason.
Health served and published by nothing, **private by the absence of a route**,
with readiness reporting only what startup established — the key set and the
capability lock are loaded — and calling nothing, because this runtime has no
dependency of its own to probe. `RefuseBrowserOrigins`, an ASGI middleware
outside everything, refusing **any** request carrying an `Origin`. The health
probe module Run 4 deleted rather than weaken a guard (D429) is back as ADR
0124's third allowlist row. And `observe_mcp`, publishing `routes.mcp` and the
`mcp` block on the two-stage convergence `routes.app` and `routes.storage` both
use (D326).

**The battery: 12 mutations, 12 killed.** P9 is the one that matters: it reverts
the verifier to duck typing, and the assembly test dies — the test that did not
exist until this run.

Suite **3684 passed, 255 skipped**.

### Run 8 — Budgets, errors, telemetry — **Done.**

**Of the four budgets, three were already there and one was missing** (D446).
Measured: a tool body sleeping **5 s** under a 1 s timeout returns at **1.10 s**
against a 0.09 s control, so `@server.tool(timeout=…)` — wired by Run 6 from the
lock's `timeout_ms` without anybody measuring it — does bound elapsed time. And
eight overlapping tool calls ran **eight bodies at once**: no concurrency bound
of any kind.

**The concurrency bound is not about this process** (D447). The agent plane holds
no database credential, but each read occupies one of **PostgREST's** connections
while it runs, and that pool is shared with human callers. So
`MCP_MAX_CONCURRENT_READS` is rendered from `api.rest.pool_size` at half — a
division, ADR 0070's rule one level out — and the runtime requires it rather than
defaulting to a constant that would be a second authority for it.

**D448 is the error finding, and it is D274's shape.** Run 6's refusal messages
and Run 4's `mask_error_details=True` cancel: measured, a plain exception's
message is replaced by `"Error calling tool 'query_resource'"`, while a
`ToolError` carrying the same text passes through unchanged. So every carefully
worded input refusal reached **nobody**. Two vocabularies now (ADR 0130):
`AgentVisible` for what an authenticated caller can act on, masked
`ToolRefusal` for everything structural — and the mask stays on, so a new refusal
is silent by default.

**D451 is the sharpest row.** Run 8 made the tools `async def` and awaited the
blocking upstream read directly, so it ran **on the event loop**: six overlapping
requests against a bound of two peaked at **one** concurrent. The semaphore never
saw contention, the bound *appeared* to work, and every other request in the
process was serialised behind each read. Moved to `asyncio.to_thread`,
re-measured at **2 of 2**. A budget that cannot be reached passes every test
written against it.

**D450 is D444's second instance**, and Run 7 did not find it.
`AgentContextMiddleware` was duck-typed too — *citing the verifier as its
precedent* — and the framework's pipeline raised `'AgentContextMiddleware' object
is not callable` on the first request through it. Every test called `on_request`
directly. The replacement test is a **pair**: every object the framework is asked
to wire is asserted to be a framework type.

**D449 is a control that was not written**, because the premise turned out false.
The draft ADR claimed rich tracebacks render frame locals; measured,
`show_locals` is never set, so the default `False` applies and a panel carries
this repository's own source lines and nothing of the request. The ADR states the
measurement, and says plainly that the property rests on a framework default
nothing here pins.

**Telemetry**: one structured record per call — tool, resource, outcome, row
count, elapsed ms, and the agent and owner ids. **No token, no fingerprint, no
URL, no caller value.** Durable nowhere, and `mcp_audit_service` untouched
(D412). The canary gains its offline half: an AST scan asserting no sink call in
the agent plane is handed a token, with a control that proves the scan finds one
when it is there.

**The battery: 17 of 17 killed** — and the last two took a second pass.
**Both survivors were missing arms rather than weak assertions** (D453, D454):
one read a rendered artefact the mutation does not rebuild, the other called the
module function the registration wraps, because **nothing in this repository had
ever called `register()`**. A third row came out of the battery itself: a leaked
semaphore slot makes its test **hang**, which is neither `FAILED` nor `ERROR` and
leaves no verdict for any later arm (**D452**).

**D455 came from the suite rather than the battery**, and is left as a finding
rather than a fix: `test_environment_gates` flags any subscript whose key is an
`APG_`-prefixed literal, so an offline settings test doing `del` on a **local
dict** was reported as consuming a live environment. Narrowing that guard is a
weakening and needs an ADR; the test is rewritten instead.

**And the run closes its own oldest open item** (D456). `MCP_MEMORY_LIMIT_MB` had
been 384 and unmeasured since Run 4, flagged as Run 8's. Measured with ADR 0082's
rig and a zero-import control: the loaded runtime is **69.2 MiB** — `mcp.types`
is 25 of them and `fastmcp` on top adds **0.6**, which is the opposite of the
intuition — and one read at the byte ceiling costs **1.8 MiB**, linear to ten.
`floor(share) = 128 + share x 4`, so **148 MiB** at the default share.

**The validator that would have enforced it was checked instead of written, and
could not fail**: the schema caps `api.rest.pool_size` at 100, so the largest
floor a valid manifest can ask for is 328 against a limit of 384. A guard that
cannot go red is §6's pattern reversed, so **ADR 0131 declines to write one** and
puts the relation in a test that reads the schema's own maximum. The limit stays
384 and stops being inherited. Lowering it would free 256–384 MiB across two
projects — and the profile is of the interpreter, not the container, so that is
Run 9's to take. The floor battery killed **4 of 4**.

Suite **3718 passed, 255 skipped**.

### Run 9 — The contract, the docs, the evidence — **Done, except the trip.**

**Everything that can be built off-host is built. The host trip is not done**,
because it cannot be: `sudo` needs a TTY and a human at a terminal. §4 of
`docs/session-08-operator-guide.md` is the sequence, written to be worked through
in order.

**D457 is the row to read, and it is about this plan.** §2 says Session 8 adds
**nothing** to the registry; §7 says the evidence has two halves. Measured with a
control before anything was written: all six Session 8 requirements carry **no
environment marker**, a claim over two of them is refused *"has no live proof"*,
and the control resolves to `host`. **Session 8 had six requirements and could
make no claim at all.** **ADR 0132** is the answer: four requirements gain live
proofs rather than twins, four new ids carry the guarantees that are about a
deployment, and `AGT-DRIFT-001` is deliberately in no claim because its guarantee
is complete in a checkout (D331's precedent).

**Eight claims** — seven host, one external. `public_agent_boundary` is what
makes Session 8's external mode load-bearing rather than ceremonial, and the
reason is sharper than Session 7's: the agent plane's health routes answer **200
on the container's own socket** and are private by the *absence* of a router, so
a scan run on the host would report them reachable and conclude a working
boundary was broken.

**D458 is the measurement the live proofs rest on**, and nothing had ever sent
the assembled application a request over a socket. Every reply is **SSE-framed**,
even a single JSON-RPC result; `Accept: application/json` alone is answered
**406**; and in stateless mode **no handshake is required** — a bare `tools/call`
answers 200. **406 is not 401**: a boundary proof written the obvious way is
refused by content negotiation before authentication runs, and would go green
having measured a media-type header.

**`bin/session-08-check.sh`**, three modes, in Session 7's shape with every flag
a claim depends on **in** the documented command (D404, D213). Three new
refusals — `--project`, `--capability-lock` and `--agent-token` — because each is
something an operator might reasonably expect an agent-plane gate to take, and
the answer to each is that it does not work that way. And one precondition:
`check_agent_plane_is_published` refuses a document whose `routes.mcp` is not
`ready`, naming D326's two-stage convergence, so one message replaces forty
tracebacks.

**D459 came out of writing the Session 8 gate's contract module**: the Session 7
one carries `SESSION = 6`, left behind by the copy, so the test written to catch
a session number left behind by a copy **was itself in the wrong session** and
passed on Session 4's inherited claim regardless.

**The catalog is `docs/mcp-tool-catalog.md`, generated from the committed
contract**, with `--check` in the Session 1 gate. It is **not** a served page and
D460 says why: Scalar renders OpenAPI and a capability lock is not one. D274's
instruction is obeyed in the form that applies — every tool, scope, ceiling, ADR
and divergence number the document names is resolved against the authority that
owns it, each scan with a control. **D461** is what one of those controls found:
the drift message called `relative_to` and **raised while reporting drift**.

**And two existing guards caught this run's own code, which is worth recording
because one of them had never fired.** `test_every_test_declares_the_environment
_it_consumes` found that the cross-project refusal takes the `project_b` fixture
while its module declared only `APG_LIVE_HOST` and `APG_PROJECT_A_OUTPUTS` — so
on a host with one project deployed it would have raised `KeyError` at fixture
setup **instead of skipping**. That is the exact five-test failure the guard was
written for, arriving on schedule. `test_cli_contract` caught both new commands
before either had a mode in the git index.

Battery **15 of 15 killed**. Suite **3776 passed, 271 skipped**.

**The trip has started, and everything non-privileged is done.** The host is at
`42db9e4` on a clean tree; its venv is synced (**fastmcp 3.4.0**, protocol
`2025-11-25`); all four projects in `.generated/` are re-rendered at **v12**;
`bin/session-08-check.sh --mode offline` **passed** there and so did
`bin/session-01-check.sh` — 3474 passed, 143 skipped, four rendered projects,
zero identity collisions.

**D462 came out of doing it.** Step 0 named the two example fixtures, and the
Session 1 gate's evidence step reads **every** rendered project: `alpha-dev` and
`beta-dev` were still at v11 and the gate exited 5 saying so. Step 0 now
re-renders four.

**What is left needs `sudo`, and therefore a human at a terminal**: migration
0018 as `migration_user`, the two deploys at `--through-session 8` (**twice**,
D326), `--mode host`, and one `install -o op` so the deployed documents can be
read off-host. The **external** half needs neither root nor a TTY and is the
assistant's.

---

### Run 10 — The first start, and what it found — **Done, pending the redeploy.**

**The agent plane started nowhere.** Both `mcp` containers exited 1 on the host's
first deploy of Session 8, and the cause is **D463** — the row to read, and the
sharpest instance of §6's question 5 this session has produced.

`POST_BOOTSTRAP_SERVICES` meant *"authenticates as a role the bootstrap must
activate"*. The deploy also used it to mean *"must not start before the files it
mounts are written"*. PostgREST needs both, so its membership satisfied the
second **by accident**. The agent plane needs only the second, was correctly
excluded for a correct reason about the first, and lost the second with it —
so step 5 started it eighty lines before its key set and capability lock were
written. **Docker creates a missing bind-mount source as a directory**, and the
runtime opened a directory where a key set should be.

**The deploy behaved well.** It failed at the key-set step rather than
continuing, and never published a document claiming an agent plane that had not
started: both deployed documents are still v11 with `routes.mcp: null`. All
fourteen pre-existing containers stayed up and healthy.

**ADR 0133** splits the two reasons — `POST_ARTIFACT_SERVICES` beside
`POST_BOOTSTRAP_SERVICES`, with `DEFERRED_SERVICES` the **computed** union — so
D410's assertion and its docstring stand unchanged. Adding a third case to the
overloaded name would have been the same defect with more members.

**And because that closes the instance rather than the class**, the deploy now
proves its file mounts exist before each start, derived from the override it is
about to write rather than from a second list. A missing source, or the
directory Docker leaves behind, is a named refusal with the path in it.

**The trip's non-privileged half is done and green**: the host is at the release,
its venv is synced, all four projects render at v12, and both `session-01-check`
and `session-08-check --mode offline` pass there.

Battery **10 of 10 killed** — one arm survived and it was the test's fault: the mount
pre-flight was proved as a *function* while its **wiring** was asserted nowhere,
so removing the deploy's second call to it stayed green. **D454's family**, one
run later.

**D464 is the run's second row, and it is D463's mirror.** The suite refused the
new code: `test_no_operator_command_puts_a_service_directory_on_the_path` is a
text scan for `"services"` and `sys.path`, and the pre-flight read a YAML key
called `services` in a file with a legitimate `sys.path.insert`. D463 is a check
whose evidence was too **narrow**; this is one whose evidence is too **wide**.
The scan was not touched — narrowing a passing guard needs an ADR — and the
parsing moved to `runtime_override`, which builds the override and should be
what reads it back.

Suite **3783 passed, 271 skipped**.

**What is left is one `sudo` sequence**: remove the two directories Docker
created (`rmdir` — it refuses a non-empty directory and is therefore the safe
verb), redeploy twice, then the host gate. The external half is the assistant's.

### Run 11 — The second start, and the lock nobody could load — **Done, pending the redeploy.**

**D463's fix worked and revealed the next thing**, which is what a first start is
for. With the agent plane deferred to step 6b, the key set and the capability
lock both existed as real files — and the container still exited 1:

    LockError: the lock.upstream is not str

**D465.** The deploy compiled the lock from `deployed_path` while a comment
directly above it said *"from the rendered outputs"*. Both halves of that
sentence were wrong: the deployed document is the **previous** deploy's, and the
two branches carry `routes.rest` in **different shapes** — a string when
rendered, a published-route object when deployed. The compiler wanted the URL,
got the object, and **wrote a lock** whose `upstream` was a dict.

**That is D389's shape for the third time this session**, and the sharp part is
what a wrong input produced: not an exception but an **artefact**. The lock was
written, mounted, and refused four steps from its cause.

The deploy now passes the rendered document, and `command_lock` **refuses a
deployed-shaped one by name** — exit 3, naming both branches — so the mistake
cannot produce a lock at all. Verified end to end offline: rendered compiles a
lock `load_lock` accepts with all four tools; deployed is refused.

**The trip's ledger so far.** Two starts, two defects, both invisible to a green
offline suite of 3,783 tests, and each hidden behind the one before it. That is
D211–D214's rule — *one unrun proof hides the next* — arriving as *one broken
start hides the next*.

Battery **BATTERY**. Suite **SUITE**.

### Run 12 — The first host gate, and three assertions that had never run — **Done, pending the re-run.**

**The agent plane is LIVE.** Both `mcp` containers `Up (healthy)`, both deployed
documents at **v12** with `routes.mcp: ready` and an `mcp` block carrying
protocol `2025-11-25`, `token_use: "agent"` and four tools. Reached from off-host:
anonymous **401**, an `Origin` **403 `origin_not_permitted`**, and both health
routes **404 at the edge** — private by the absence of a router, which is the one
property only an off-host observer can see. **`session-08-check --mode external`
PASSED**, five claims green including `public_agent_boundary`.

**The host gate found three, and all three had never executed.**

**D467 is the one to read.** A Session 8 Run 2 assertion measured schema grants
with `has_schema_privilege`, which reports a privilege held *directly or by way
of membership* — so it answered `true` for `app_runtime`, a `NOINHERIT` member of
`authenticated` that appears in **no ACL entry at all**. Migration 0006's revoke
worked; the proof could not tell a grant from a membership. **Migration 0006 wrote
that exact trap down for the table twin**, and the test written two sessions later
walked into the schema one. ADR 0134 splits it: a grant question reads
`aclexplode(nspacl)`, a reach question sets the role and tries it.

**D468** is two allowlists older than migration 0018 — `agent_claims_are_current`
in `app_private`, `mcp_agent_context` and `owner_activity_report` in `api`. Both
were **right to fail**; both gain the objects by name with 0018's reasoning, and
neither becomes a subset check (D300).

**D466** cost a gate run before either: `--ssh-destination` needs **`op@`**, not
`apg-agent@`. The access broker's policy grants one enumerated account, and the
*more restricted* account — the obvious, safer-looking choice — is the wrong one.
The positive control fired first and said so, exactly as written.

Suite **3786 passed, 272 skipped**.

**The re-run is green.** `session-08-check --mode host` PASSED — 212 live proofs,
0 failed, plus 108 static claim proofs — and the three repaired assertions were
among them, which is the first time any of the three had executed against a
cluster carrying migration 0018.

---

## Session 8 is complete

`evidence/session-08.json`, merged from both halves against release
**`911a9d3b`**: **43 claims, 41 passed, 2 failed.**

**All eight Session 8 claims passed** — `agent_reads`,
`agent_query_construction`, `agent_scopes`, `agent_budgets`, `agent_surface`,
`agent_authentication`, `agent_credentials` on the host, and
`public_agent_boundary` from off-host.

**The document reads `status: failed`, and that is the documented outcome.** The
two red claims are Session 5's — `api_authorization` and `bootstrap_identity` —
blocked on the rotation window. §7 of this plan wrote it down before the session
began: *"Session 8 does not close them and must not appear to."* It is the same
sentence Session 7 closed on, for the same two claims, for the same reason.
**Nothing in Session 8 is unproved.**

**The trip found seven** (D462–D468), none of them visible to a green offline
suite of 3,786 tests, and each hidden behind the one before it:

| | What |
|---|---|
| **D463** | The agent plane started before its files existed — one constant carrying two reasons to defer a service. **The row to read.** |
| **D465** | The lock was compiled from the deployed document, whose `routes.rest` is an object where the compiler wants a string. D389's shape, third time. |
| **D467** | A grant assertion that could not tell a grant from a membership — and migration 0006 had written that exact trap down for the table twin. |
| **D468** | Two allowlists older than migration 0018. Both right to fail. |
| **D462** | Step 0 re-rendered two of the four projects the Session 1 gate reads. |
| **D464** | A guard whose evidence is two strings standing in for a construct. D463's mirror. |
| **D466** | `--ssh-destination` needs `op@`; the safer-looking account is the wrong one. |

Session 8 was planned as **nine** runs and took **twelve**. Session 7 was planned
as ten and took sixteen; §2 said to budget for the same, and the budget was
right.

---

## 6. The MCP surface

Four tools, and no MCP resources, prompts, roots, sampling, elicitation or UI.

| Tool | Reads | Scopes |
|---|---|---|
| `list_resources` | the deployed lock | `meta:read` |
| `describe_resource` | the deployed lock | `meta:read` |
| `query_resource` | PostgREST, structured | `notes:read` or `tasks:read` |
| `run_report` | one named RPC | `notes:read`, `tasks:read` |

**What a tool result never carries:** a token, an object key, a presigned URL, a
connection string, another agent's existence, or a row the caller's RLS would not
have returned.

**What `query_resource` cannot accept**, structurally rather than by validation:
SQL, a SQL fragment, a PostgREST query string, a path, an operation name, a
column outside the frozen allowlist, an operator outside the typed vocabulary, an
ordering expression, or a relationship traversal.

**Annotations are client hints, not controls.** `readOnlyHint`,
`destructiveHint=false`, `idempotentHint`, `openWorldHint=false` are published
where the negotiated protocol supports them and enforce nothing.

---

## 7. Evidence and claims

Unchanged: a claim's verdict is computed from the registry's node ids and JUnit
results, never hand-entered, and **a skip is not a pass**. Host and external
halves are written separately and merged by
`bin/write-session-evidence.py --session 8`.

**Both halves must describe the same release** or the merge refuses — Session 7
proved that the hard way, and was right to.

`evidence/*` is gitignored by design.

**The two inherited red claims are Session 5's.** Session 8 does not close them
and must not appear to. If the rotation window is held during this session, it
closes them and the plan says so; if it is not, Session 8's evidence carries them
red for the same stated reason.

---

## 8. Security invariant matrix

| Invariant | Control | Proof |
|---|---|---|
| An agent cannot run SQL | No input accepts one; the compiler cannot emit one | `AGT-SQL-001`, by request |
| An agent sees only its owner's rows | RLS, keyed by `agents.owner_id` | `AGT-READ-001` — MCP result equals PostgREST result |
| A new API operation grants nothing | The lock is compiled from `capabilities.yaml` | `AGT-DRIFT-001` — add an operation, expect no new tool |
| Discovery respects scopes | Filtered at `tools/list` and re-checked at call | `AGT-SCOPE-001` |
| Budgets hold server-side | Rows, bytes, time, concurrency, independently | `AGT-BUDGET-001` |
| A revoked agent stops immediately | `authz_version` compared per HTTP request | Revoke mid-session, next request refused |
| A human token cannot use MCP | Declared accepted `token_use` | The mirror of ADR 0114 |
| An agent token cannot use storage | `objects:*` absent from `agent_scope` | Session 7's `STO-AGENT-001`, still green |
| MCP holds no database credential | The secret contract grants it none | Mount and inspection scan, via `docker cp` (D411) |
| MCP cannot sign | It receives public JWKS only | The fourth verifier's key-set proof |
| Cross-project authority is denied | Distinct issuers, audiences, roles, locks | Two-project gate |
| No token or key reaches a sink | Allowlist logging | The canary scan, extended |

---

## 9. Risks and stop conditions

**Stop and ask** rather than proceeding, when:

- activating `agent_reader` would require relaxing rather than re-deriving an
  assertion;
- the live OpenAPI and the approved snapshot disagree and the difference looks
  benign;
- a tool needs a column, operator or ordering that `capabilities.yaml` does not
  list;
- `--render-only` stops working with no host and no root;
- a Session 1–7 claim goes red and the fix would weaken a passing test.

**The failure mode this session is most exposed to** is the one this project
keeps producing: *a value that looked measured and was not.* Session 8 adds a
framework whose behaviour is documented by somebody else, a protocol revision
that changes on a schedule nobody here controls, and a tool surface an LLM reads
as instructions. Every one is a place where a plausible wrong answer passes for
exactly as long as nobody asks.

The five standing questions:

1. What would have to break for this test to go red?
2. Has it run at all, in this environment, since the thing it measures changed?
3. Whose identity, and through which tool, does the proof run — and are they the
   ones production uses?
4. When a defect class was fixed, **which side got the fix** — product or proof?
5. When a decision is implemented, **which of its callers got it?**

**Question 5 caught five defects in Session 7** — D381, D385, D389, D390, D392 —
each a decision implemented everywhere except the place that consumes it. Session
8 adds a fourth verifier, a fourth application container, a second principal
class and a new route. **Ask it at every boundary.**

---

## 10. Open items carried in

- **The rotation window.** Still the only thing keeping two Session 5 claims red.
- **The signing-key cutover** (ADR 0088). Unblocked, and MCP makes it a **fourth**
  verifier to recreate. `render-jwks` still prints *"the key set CHANGED"* on
  every deploy (D296), which a fourth verifier makes more load-bearing, not less.
- **Nothing knows which proofs have never executed** (D211–D214). Session 7 paid
  for this again: D390 and D392 were a role that never existed and a `NULL` owner,
  sitting in a `live_host` fixture that had never run. **Five sessions, unbuilt.**
- **`apg-diag` cannot read the new services' logs** (D380). It will not read
  MCP's either unless Session 8 widens the allowlist — an ADR-shaped decision,
  since it widens what the agent account may read.
- **The REST document observation does not retry** (D387). Hit twice in one trip.
- **D394** — an sshd baseline deviation that would not reproduce; the check keeps
  the verdict and discards `sshd -T`'s output, so a one-off leaves nothing to
  diagnose.
- **`tests/deployment/conftest.py`** is past 1,200 lines and now carries the
  storage fixtures, two probe subjects and a recovery path.
- `requirements-dev.in` pins nothing; adding FastMCP is the fourth chance to do
  it carefully, and the environment is still not verified against the lock (D297,
  which cost a gate run in Session 7).
- Secret generations accumulate; nothing prunes them.
- ADR 0060: the REST document advertises DELETE, PATCH and POST on both views and
  all three return 403. Recorded, not fixed — and now an agent will read that
  document.

---

## 11. Session 9 handoff

Session 9 receives an activated `agent_reader`, a compiled and deployed capability
lock, a four-tool read surface with proved budgets, an authorization path that
runs through PostgREST rather than beside it, and an unactivated
`mcp_audit_service` waiting for the record it will write.

Session 9 **must not** activate `agent_writer` without the reviewed role and scope
expansion, register a write tool that is not one-to-one with a named operation,
write an audit record that can be lost without failing the call, or let a tool
result carry a value the read surface was built to keep out of sinks.

---

## Appendix — what to consult, and what to measure instead

**Consult:** `docs/decisions/README.md` (114 ADRs, indexed) — especially 0003
(the frozen domain), 0006 and 0079 (scopes and ceilings), 0052 (the private
schema grant), 0088 and 0098 (verifiers), 0100 (agents and storage), 0108
(route ordering), 0113 (key sets) and 0114 (accepted token uses).
`docs/capability-plan.md` for the four tools. §1 of this document.
`docs/plans/session-07-implementation-plan.md` §1 rows D376–D394 and §5 runs
10–16, which are what a host trip costs.

**Measure instead of consulting**, every time: what the framework does by
default, what the protocol revision requires, what a header does to a route, what
a container holds, and whether a proof has ever run.

**Before measuring how a third party behaves, grep the plans for it.** Run 8 of
Session 7 measured how PostgreSQL grants `EXECUTE` on a new function and recorded
it as a finding; Session 3 had measured the same thing three sessions earlier, in
more detail (D57, D262). Every ADR is indexed; **nothing indexes the ~400 measured
facts in the divergence tables by subject**, so the pointer has to be a `grep`.

**Never write a measurement you did not run** (D267).
