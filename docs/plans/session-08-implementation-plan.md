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

**Next free number after this table is D419.**

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

### Run 3 — The capability compiler

- Capture the live PostgREST OpenAPI through the documentation token, normalise,
  and **compare against the approved snapshot**. Drift fails.
- Compile `contracts/snapshots/mcp/mcp-capabilities.canonical.json` from
  `capabilities.yaml` + the reviewed surface. Project-neutral.
- The deployed `mcp-capabilities.lock.json` resolves project-scoped paths and
  hashes.
- The compiler may **read** OpenAPI and may never **infer** a capability from it
  (AGT-DRIFT-001).

### Run 4 — The runtime and the fourth verifier

- Measure FastMCP, then lock with `--packages-only` (D406).
- The image, hardened like storage: read-only rootfs, uid 65532, no shell.
- Mount the rendered `jwks.json` by ADR 0113's mechanism; MCP is the **fourth**
  verifier, so ADR 0088's recreate list and `SEC-KEY-002`'s readings both move
  (D409).
- The token verifier: the strict contract, `token_use: "agent"`, `sub` as the
  agent id, exact scopes, positive `authz_version`.

### Run 5 — The authorization path

- Per-request middleware forwards the **original** token to
  `mcp_agent_context` before discovery or execution.
- Cached for one HTTP request, keyed by a non-reversible fingerprint, never
  across requests, tokens, workers, or expiry.
- No confused deputy: no service token, no re-signing, no injected role or
  subject header.

### Run 6 — The PostgREST adapter and the four tools

- A fixed upstream, a header allowlist, and encoded query construction — never
  string concatenation of a caller value.
- `list_resources`, `describe_resource` from the **lock only**: no live OpenAPI,
  no database.
- `query_resource`: structured input, frozen columns, typed operators, AND-only,
  explicit ordering. **No SQL, no fragment, no raw query string, no path, no
  runtime-selected operation** (AGT-SQL-001).
- `run_report`: one named RPC.
- Exactly four tools registered, names asserted lexicographically, schemas hashed
  against the canonical contract.

### Run 7 — Publish

- The route in ADR 0108's frozen form, precedence **derived**, `/mcpx` proved to
  reach a different backend by which service answered (D408).
- `profiles: [session8]`, absent from `POST_BOOTSTRAP_SERVICES` (D410).
- Host/Origin protection; browser CORS off by default.
- Private unauthenticated health; readiness tokenless and inventing no private
  dependency endpoint.
- The two-stage convergence `routes.app` and `routes.storage` both use: first
  deploy `unavailable`, redeploy `ready` (D326).

### Run 8 — Budgets, errors, telemetry

- Rows, elapsed time, concurrency and serialized bytes bounded **independently**.
- The error registry, in `errors.py`'s shape and ADR 0097's split: structural
  refusals say nothing; an authenticated caller may be told a state.
- Structured read telemetry, no durable audit, `mcp_audit_service` untouched
  (D412).
- The canary scan Session 7 built, extended: **no token, no key, no URL** in any
  sink.

### Run 9 — The contract, the docs, the evidence

- The MCP tool catalog, generated from the lock, and a page that **fetches its
  own assets** (D274).
- `bin/session-08-check.sh`, three modes, every flag in the usage command (D404).
- The claims, the registry replacements, the evidence.
- Then the host trip, and **plan for it to find things**.

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
