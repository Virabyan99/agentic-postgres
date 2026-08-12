# Session 5 implementation plan — PostgREST, a reviewed API surface, and documentation metadata

**Primary outcome.** Each project serves a narrowly bounded PostgREST API at a
stable public HTTPS prefix, backed by exactly the `api` schema, authorized by
PostgreSQL rather than beside it, described by a reviewed source-controlled
contract and a normalized OpenAPI snapshot, documented behind a credential, and
reachable from nowhere the reviewed contract does not name.

**What this document is.** The Session 5 runbook, rewritten against the
repository that exists. The runbook it replaces was written on top of Sessions
1–4 *as those documents described them*, and Sessions 1–4 diverged from their own
documents in a hundred and twenty-six recorded places. Its scope boundaries, its
authority ordering and almost all of its security judgement survive intact. Its
paths, command shapes, schema versions, requirement IDs, pinned versions, scope
names, error codes and — most consequentially — its statement of the example
domain do not.

Per the standing rule — *never silently reconcile a conflict between a runbook
and the code* — every one of those conflicts is a numbered divergence below
rather than a quiet edit. The `D` sequence continues from Session 4, which ended
at **D126**.

---

## 1. Runbook divergences

| # | Runbook says | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D127** | Pin exactly PostgREST **14.16** and its platform digest; "no floating tag, semver range, '14.16 or newer,' or unreviewed 14.x substitution is accepted." §11.3 then lists a configuration baseline: `db-hoisted-tx-settings`, `db-aggregates-enabled`, `db-plan-enabled`, `jwt-cache-max-entries`, `server-trace-header`, `admin-server-host`, `postgrest --ready`, `postgrest --dump-config`. | **`versions.in.yaml` has pinned `docker.io/postgrest/postgrest:v13.0.4` since Session 1**, resolved to a digest for `linux/amd64` in the generated `versions.env`. D37 settled that a session adds nothing to the lock inventory and uses what is already pinned; D85 applied the same rule to PgBouncer and kept `v1.24.1-p1` against a runbook demanding `1.25.2`. And ADR 0019 is the standing lesson that **a configuration key read from documentation is not a fact**: a floor was once written to guarantee `accessLog.fields.queryParameters`, a Traefik key that exists in no released version. Half the baseline above is major-sensitive. | **Measure `v13.0.4` first.** Run 1 records, against the locked digest and into `tests/contract/test_image_contracts.py`: `postgrest --version`; the complete key set `--dump-config` emits, compared against every key this session intends to set; whether `--ready` and the admin server exist and where they bind; whether `jwt-secret` accepts a JWKS **file** and with what syntax; whether `db-pre-request`, `db-schemas`, `db-extra-search-path` and `db-config` behave as this plan needs. Bump the candidate in `versions.in.yaml` and re-lock **only if a measurement requires it**, and re-measure all of it when you do. | A version claim is a documentation claim, and this project has a rule about those. If 13.0.4 cannot express a boundary this session depends on — an empty extra search path, a pre-request hook, a verification-only JWKS — the bump is right; it gets made because someone ran the binary, not because a plan asserted a number. The keys are the more dangerous half: a config key that silently does nothing produces a service that starts, answers, and enforces less than the file says. | no |
| **D128** | Lock a Scalar API Reference **image** tag and digest, recording "the image digest, OCI revision/version labels when present, expected `/health` behavior". | `versions.in.yaml` has **`SCALAR_VERSION: "1.36.4"` under `packages:`** — a package version string, locked since Session 1 — and **no Scalar entry under `images:`**. Meanwhile `services/docs/.gitkeep` has been in `REQUIRED_PATHS` since Session 1, reserving a first-party build context, and every first-party service in this repository (`services/edge-probe/`, `services/secret-check/`, the four `services/clients/*`) is built `FROM` a locked base with a committed dependency lock. | **Decided in Run 1, from a measurement, between two shapes with different costs.** (a) Add `SCALAR_IMAGE` to `images:` and re-lock — cheap, and inherits the hazard the runbook itself names, that Scalar's Docker interface moves independently of the package. (b) Build `services/docs/` from the locked Node runtime at the already-pinned 1.36.4 with a committed lock file — the repository's own precedent, and it makes the version this session ships the version Session 1 locked. The measurement that decides it: does 1.36.4 produce a **self-contained** bundle with no runtime fetch, given a static OpenAPI document? | The documentation service must load nothing from the internet — that is a P0 property, not a preference, and it is the one thing the choice between an upstream image and a first-party build actually turns on. Deciding it by preference and discovering it at Run 9 is how a run gets spent. | no |
| **D129** | The API surface is `notes(id, title, content, created_at, updated_at)`, `tasks(id, title, description, status, created_at, updated_at)`, and two RPCs: `create_note(title, content)` and `update_task_status(task_id, expected_status, new_status)`. `docs/decisions/0003-example-domain.md`, `docs/source-specification.md` §7 and `docs/capability-plan.md` all say the same, and the capability plan maps `update_task_status` 1:1 onto the `tasks:write` scope. | **Session 3 shipped something else, and nothing recorded it.** `api.notes` is `(id, owner_id, title, body, created_at, updated_at)`; `api.tasks` is `(id, owner_id, note_id, title, done, created_at, updated_at)`; the two write RPCs are `api.create_note(p_title text, p_body text)` and **`api.create_task(p_title text, p_note_id uuid)`**. There is no `status` enum, no `update_task_status`, and `owner_id` is an exposed column. Four source-controlled documents say one thing and six applied migrations say another. | **UNRESOLVED HERE — it is ADR 0048, written in Run 1 before anything else.** Two resolutions, both real: **converge the code**, with a new migration adding the bounded `status` enum and `update_task_status` and retiring `create_task` — released migrations are immutable and fix-forward, so this is additive plus a revoke, and it touches P0 tests in `tests/security/test_session3_authorization.py`; or **supersede ADR 0003's domain clause** to state what is deployed, which also rewrites the capability plan Session 8 builds from. **The plan's recommendation is to converge the code**: three independent documents naming one shape and one implementation naming another is the implementation being wrong, and ADR 0003 explains why operation 4 is a narrow status transition rather than a general update — a reason that survives, and that `create_task` does not satisfy. | This is the session where the two stop being able to disagree quietly. Session 5's entire job is to publish this surface as a reviewed contract and a generated OpenAPI document; whichever shape is right, the contract file, the snapshot, the SQL comments, the docs page and Session 8's capability catalog will all be built from it. Choosing at Run 1 costs one migration. Choosing at Run 9 costs the contract, the snapshot, the approval and the deploy that produced them. | **yes** |
| **D130** | §4.12 freezes an application error table — `AP001` missing identity, `AP002` validation, `AP404`, `AP409` optimistic conflict, `AP422` invalid transition, `AP500`, `AP900` — and says "Session 3's direct-database SQLSTATE meanings remain authoritative." | Session 3 raises exactly three: **`AP401`** (no request identity for this transaction), **`AP404`** (no such note), **`AP900`** (released migrations are fix-forward only). `AP001`, `AP002`, `AP409`, `AP422` and `AP500` do not exist, and two of them — the conflict and the transition — describe an operation the database does not have (D129). | **The HTTP mapping is written from the codes that exist.** `AP401 → 401`, `AP404 → 404`, `AP900` is not a public response. Any further code is created **by the RPC that raises it**, in the migration that adds it, with a test that produces it — never asserted in a table first. If D129 converges the domain, `update_task_status` brings its conflict and transition codes with it and they are added there. | An error-code table is a contract about behaviour, and a contract asserting behaviour nothing produces is the shape this project keeps producing: a value that looks measured and is not. Five of the runbook's seven codes would have been unreachable on day one, and the tests written against them would have had to be weakened or deleted — the weakening happening quietly, under time pressure, at Run 12. | no |
| **D131** | Non-anonymous bootstrap tokens carry a `scope` array, and "Session 5 recognizes only `api:read`, `api:write`, and `openapi:read`". These are rendered into `postgrest.conf` as `app.settings.scope_api_read` and read back by the pre-request function. | **ADR 0006 makes `schemas/capabilities.schema.json` the sole authority for the approved scope vocabulary**, in its own words: "this file is also the sole authority for the approved scope vocabulary; the code carries no second copy." That vocabulary is exactly `notes:read`, `notes:write`, `tasks:read`, `tasks:write`, `meta:read`, and the schema says it "grows only when `docs/decisions/0003-example-domain.md` is superseded". Three new names in a PostgREST config file would be a second vocabulary in a second authority. | **The token's scopes are the vocabulary that already exists** (ADR 0049). A reader token carries `notes:read`/`tasks:read`; a writer token carries the write scopes; the documentation role carries **`meta:read`**, which the schema already describes as "for schema introspection" — precisely what `openapi:read` was invented to mean. Adding a scope name requires editing the capability schema, which is what ADR 0006 exists to force. | Session 8 builds MCP tools whose `required_scopes` come from that enum. If Session 5 mints a parallel set, Session 8 has to map between two vocabularies for the same operations, and the mapping becomes the place a scope quietly widens. One vocabulary is the whole point of ADR 0006 and it costs nothing to keep. | **yes** |
| **D132** | The gate is `sudo bin/session-05-check.sh --host … --project-a <project.yaml> --project-b <project.yaml> --capabilities … --external-probe <target>`. | D45 settled the gate shape in Session 2 and Sessions 3 and 4 kept it: `--mode offline\|host\|external`, `--project-a-outputs` / `--project-b-outputs` naming **deployed documents** rather than manifests, `--sentinel-file`, `-k` (which writes no evidence), verify-only. `bin/session-04-check.sh` **refuses `--capabilities` and `--external-probe` by name**, with a message pointing at the right flag. | **`bin/session-04-check.sh`'s shape, `readonly SESSION=5`, three modes, and the two refusals kept verbatim.** External mode is emphatically not vacuous here: Session 5 is the first session whose public surface carries authorization, so what a stranger can reach is a first-class measurement rather than a structural inference. `--ssh-destination` stays required in external mode for the same reason Session 4 made it so. | The gate takes deployed documents because a manifest describes what was asked for and a deployed document describes what happened. The refusals stay because an operator reading the runbook is asking a reasonable question, and the answer is a different flag rather than a typo. | no |
| **D133** | Evidence is a bespoke `schemas/session-05-evidence.schema.json` holding roughly thirty hand-shaped booleans: `rls_http_proven`, `capture_mode_inactive`, `browser_token_absence_proven`, `cross_layer_log_redaction_proven`, and so on. | ADR 0025 replaced suite-name evidence keys with **claims** resolved from the acceptance registry and JUnit results; ADR 0039 derives a claim's session from its requirements and makes claims cumulative; ADR 0045 splits a claim where its measurement lives. `bin/write-session-evidence.py` is session-agnostic. D49 and D91 both settled it: **a session adds claims, not a format.** | **Session 5 adds claims to `evidence_claims.CLAIMS`** (§7). Counts come from catalogs and JUnit; nothing is hand-entered. | Every one of those thirty booleans is a place a `true` can be written by something that is not a test. A claim's verdict is computed from exactly the node IDs the registry lists, a proof missing from the artifact is `not_run` rather than `passed`, and a skip is not a pass. A bespoke schema re-derives all of that and becomes the second definition of "proved" — which is how the two definitions drift and the weaker one wins. | no |
| **D134** | A large implied set of new Session 5 requirement IDs, scattered through §16's test plan. | **Five Session 5 requirements already exist** in `tests/acceptance-registry.yaml`, each with a `future` placeholder carrying an exact node ID: `API-SCHEMA-001`, `API-CACHE-001`, `API-LIMIT-001` (in `tests/integration/test_future_api.py`) and `SEC-ANON-001`, `SEC-PRIV-001` (in `tests/security/test_future_security_boundaries.py`). `ID_PATTERN` admits only `DEP CFG DBX SEC API AGT STO REC OPS DX`. | **Activate the five that exist; add new IDs only where none of them covers the claim.** Final list in §2. Two collisions are refused there: a Session 5 token-validation ID would collide in meaning with Session 6's `SEC-JWT-001`, and a Session 5 key-separation ID with `SEC-KEY-001` — the same call D47 made when it dropped `API-DB-001` against `SEC-VIEW-001`. | Activating a requirement means removing its `future` marker and implementing the body; the placeholder already fails when executed, which is what makes it activatable. `test_future_marker_policy.py` enforces registry↔marker agreement in both directions, so a duplicate ID fails offline and an unregistered prefix fails offline. | no |
| **D135** | §4.14: a two-commit workflow with an explicit root-only `deploy.sh --capture-session-5-contract` submode, a `session-05-capture-state.json` document with its own schema, a non-ready non-public deployment state, and a final gate that fails "if capture mode is active, capture state remains, or the deployed release commit differs from the clean source commit under test". | **The problem is real and the machinery is a fourth answer to a question this repository has already answered three times.** The canonical snapshot genuinely cannot be committed before the locked PostgREST has generated it, and privileged work genuinely runs from a clean installed release (ADR 0037). But `versions.env` is generated by `bin/lock-versions.sh --update`, committed, and checked offline by `--check`; `migrations/released.lock.json` is the same shape; `docs/acceptance-matrix.md` is the same shape again, generated by `bin/render-acceptance-matrix.py` with the gate running `--check` and failing on drift. | **The snapshot is a generated-and-committed artifact with an `--update`/`--check` split** (ADR 0050). `bin/api-contract.sh --update` runs privileged against a deployed release and writes a candidate; the source owner reviews and commits it; the gate runs `--check`, offline where it can and against the live document in host mode, and **never rewrites**. The two-commit sequence survives in substance — capture, review, commit, redeploy — and Session 4 already deploys twice for exactly this reason (D112). No capture submode, no capture-state schema, no non-ready deployment kind. | Three existing mechanisms of this shape means the fourth needs a reason to be different, and "this one is about an API" is not one. The runbook's version also invents a *deployment state* — a project that is deployed but not ready and not public — which is a fifth thing `deployed_through_session` and the endpoint `status` fields would have to be read against, and a state nothing else in the system knows how to reason about. | **yes** |
| **D136** | §4.15: `bin/migrate.sh` gains a root-only `migrate-through --version 0007`, available only under the capture submode, which copies a contiguous migration prefix into a private temporary directory and runs dbmate against it — so that PostgREST can be started between `0007` and `0008` and prove a live schema-cache reload. | `bin/migrate.sh`'s whole contract is that **the released set applies in order, immutably, verified against `released.lock.json`, with the ledger written by the superuser** (ADR 0034). A second way to apply released migrations is a second answer to "what has been applied". And D110's lesson is directly on point: inventing a route through the one script whose job is to bound what may be asked is the change that should be made deliberately, in the run that needs it, with its own test — not as a side effect of arranging a proof. | **The reload proof does not need a staged migration, and `API-CACHE-001` does not ask for one.** Its registered description is "a DDL change appears in OpenAPI after the reload". The transient acceptance-only object that §9.4 already requires for the timeout tests — created and dropped inside the host lock, under a reserved name, with `NOTIFY pgrst, 'reload schema'` on each side — proves exactly that: the OpenAPI fingerprint changes, the expected description appears, and the container ID and process start time are unchanged. Both released migrations apply through the ordinary wrapper, in order, and every migration that changes the API still ends with `NOTIFY` because that is what makes the ordinary path work. | The property under test is "a DDL change reaches OpenAPI without a restart". The runbook proves it with a mechanism that exists only during one privileged submode of one session and is then forbidden forever, which means the proof measures a path no deployment ever takes. The transient object proves the same property through the path every future migration will use, and it is re-runnable. | **yes** |
| **D137** | §7.3: outputs schema version 5 adds a top-level `http_api` block with `rest`, `documentation` and `bootstrap_issuer` sub-objects, carrying public URLs, checksums, pool size and a connection budget. | The v4 schema **already has most of the addresses**: `routes.rest` and `routes.docs` are required `httpsUrl`s on the *rendered* branch, and `jwt.issuer`/`jwt.audience` are there too. What is missing is on the **deployed** branch, whose `routes` object requires only `health` and whose only status-carrying route is that one. There is also a debt with a name on it: **D106 deferred `database.observed.instance_uuid` to Session 5**, because the access broker currently searches live port allocations by project key and refuses ambiguity for want of the identity the registry is actually keyed by. | **Version 5 extends what exists rather than parallelling it.** The deployed `routes` gains `rest` and `docs` as status-carrying objects shaped like `health`; a new `api` block carries the observed exposed schema, limits, pool, and the three checksums (API-surface contract, canonical snapshot, per-project snapshot); the deployed branch gains `jwt` public metadata — issuer, audience, algorithm, active kid, verification kids, JWKS checksum, and an explicit `temporary` flag. **`database.observed.instance_uuid` lands in the same bump and the broker switches to it.** The full D40 price is paid: a `v4 → v5` function in `output_migrations.py`, a committed `tests/fixtures/outputs-v4.json`, and the standing rule that migration never produces a *deployed* document. | Session 2 wrote `routes` with a status-carrying `health` "so the rendered and deployed branches stay structurally parallel: the deployed document has to carry a readiness claim, and a claim needs somewhere to live." That is this session's requirement arriving three sessions early; using it is the design paying off. A parallel `http_api` block would give `routes.rest` and `http_api.rest.public_url` as two records of one URL, and this repository has watched such a pair drift. | **yes** |
| **D138** | §4.3: create `app_private.postgrest_pre_request()`; "active impersonated roles receive only `USAGE` on `app_private` plus `EXECUTE` on `app_private.postgrest_pre_request()`." | The grant is necessary — PostgREST runs the pre-request hook *after* the role switch, so the impersonated role needs `EXECUTE`, which needs schema `USAGE`. But it re-opens, for every HTTP caller, the exact boundary **migration 0006 closed one session ago**: `app_runtime` lost `USAGE` on `app` and `app_private` because "direct table reach is the difference between a compromised application seeing its own rows and seeing the shape of everything". And D103 measured that **schema `USAGE` is the boundary that does the work** — `has_table_privilege` returns true for objects the caller cannot read, because the schema grant is missing. | **Adopted, bounded by name, and proved behaviourally** (ADR 0052). The request roles receive `USAGE` on `app_private` and `EXECUTE` on exactly one function. Default privileges in `app_private` stay closed. The proof is not a catalog read: it **attempts** a read of a private table, a call of every other `app_private` function, and a `SELECT` against `app` — the D103 construction, because the obvious catalog assertion can be true while the property is false and vice versa. `PUBLIC` keeps nothing. | Granting name resolution in the private schema to every anonymous HTTP request is the largest authorization change in this session, and it is invisible in a diff that reads as one `GRANT USAGE`. If Session 9 needs a private-table lookup it adds a separately reviewed security-definer helper; it does not widen this. | **yes** |
| **D139** | §11.2: the `postgrest` service "depends on PostgreSQL readiness and completed role/migration convergence", and §15's Phase 7 starts it as part of a deploy. | **The deploy's ordering makes that impossible as written, and this is D101 one session on.** `bin/project-runtime.sh up` runs `compose up --wait`, and the deploy runs `postgres-bootstrap` — which creates the roles — *after* that returns; migrations run after that. A PostgREST in the `session5` profile therefore starts on a first deploy before its authenticator role exists and before migration `0007` has created the function `db-pre-request` names. A readiness probe that requires a working pool and a warm schema cache **fails `--wait` and takes the deploy down with it**. | **Measure the failure first, then sequence it explicitly.** Run 1 measures what PostgREST 13 does when `db-pre-request` names a missing function and when the authenticator cannot log in — specifically whether it fails closed (refuses requests) or open (ignores the hook). Run 4 then decides the start phase from that, and **the systemd launcher must make the same decision**: it runs at boot with no operator to ask, and D59 is what a launcher that disagrees with the deploy costs — a Session 3 project restarted into Session 2's profile set, with `systemctl status` showing a clean start. | The dangerous half is not the failed deploy; a failed deploy is loud. It is a PostgREST that comes up, answers, and skips a pre-request hook it could not resolve — which is a public API with its claim validation silently disabled, in a state where every other check passes. That measurement is the one this session most needs before anything is published. | no |
| **D140** | §8.1 adds `docs_basic_auth_password` to `secrets.required.yaml`; §8.5 generates a bcrypt hash into a root-owned `usersFile` published under `/var/lib/agentic-postgres/edge/dynamic`, which Session 2 already mounts read-only into Traefik at `/etc/traefik/dynamic`. | The mount is real and the path is right — that half checks out. The secret does not fit the contract: `schemas/secret-contract.schema.json` requires **`consumers` with `minItems: 1`**, and `tests/contract/test_secret_contract.py` cross-checks every consumer against a Compose service and its `user:`. **Traefik is not a project Compose service** — it is the shared edge stack in `infra/edge/compose.yaml` — and the documentation service must never receive this credential, which is the entire point of `removeHeader: true`. There is no service to name. | **Settled in Run 3, from three options with different costs.** (a) The credential is generated by the deploy into the root-owned generation and never traverses the provider — cheapest, and it breaks "secret material is published as an immutable generation" for one value. (b) The secret contract admits a **root-plane consumer** — a schema change and a contract-test change, therefore an ADR, and it also gives `migration_user_password`'s bootstrap reader somewhere honest to live. (c) Name the documentation service as consumer — **refused**, because it materializes the cleartext into the one container that must not have it. `htpasswd` is not a dependency: bcrypt through the locked Python toolchain, or the hash is not generated here at all. | **Settled as (b) in ADR 0054**, and one half of the reasoning above turned out to be wrong. A root-plane consumer is a *materialization target for a value no container may hold*; `migration_user_password`'s bootstrap reader is not one, because it reads dbmate's already-materialized copy and giving it a root-plane consumer would materialize a **second copy** of one credential — the thing that file's own comment refuses, in those words, twice. ADR 0055 came with it: the signing key is not a password, and a generator that wrote 32 bytes of hex under that name would have passed every check here. | **yes — ADRs 0054, 0055** |
| **D141** | §12.1: configure "the protected Traefik access-log field policy to retain the **response** `X-Request-ID` for correlation while dropping request headers by default, **dropping query parameters**, and explicitly dropping `Authorization`, `Cookie`, `X-Request-ID`". | **`accessLog.fields.queryParameters` does not exist in Traefik, and ADR 0019 exists because a floor was once written to guarantee it.** Probed against the locked digest, `accessLog.fields` accepts exactly `defaultMode`, `headers` and `names`. The resolution shipped in Session 2 is that **`RequestPath` is dropped entirely**, because it carries the query string and there is no way to keep one without the other. The path is already gone from access logs; `RouterName` and `ServiceName` remain. | **The query-parameter clause is struck.** Header dropping and the response-header retention are real capabilities and are configured; whether `X-Request-ID` can be retained as a *response* field is measured against the locked digest before it is written, not read from a page. The proof is the outcome, as ADR 0019 rewrote it: a request carrying a secret-shaped query-string sentinel leaves no trace of it in any log layer. | This is the second time this exact key has been asked for by a document written from vendor documentation, and the first time cost a run and took the edge plane down. A setting that decides whether a token reaches a log is the last place to accept a documentation claim. | no |
| **D142** | §5.3 requires "a hash/digest-locked Playwright + Chromium (or equivalently locked headless-browser harness) for Scalar storage/network assertions"; §16.8 asserts no credential in "HTML, JS, network log, local/session storage". | The dev toolchain is hash-locked through `uv pip compile` into `requirements-dev.txt`, and `requirements-dev.in` **pins nothing** — a carried-in open item that has produced a red gate in two sessions. A browser is several hundred megabytes of new dependency, and what it would prove is that a third party's page honours its own `persistAuth: false`. | **No browser.** The documentation page is a **static local snapshot**, so "no credential in the served bytes" is a byte scan of files this deployment wrote — stronger than a browser assertion, because it holds for every visitor rather than for the one that was driven. `persistAuth: false`, the empty plugin set, the absent proxy URL and the absent external document URL are asserted against the generated configuration. The one thing genuinely lost is "Scalar does not itself call out to a third party at runtime", and that is proved instead at the network layer: the container joins one network, holds no credential, and D128's measurement establishes the bundle is self-contained. | A proof whose subject is another project's runtime behaviour is a proof of the wrong thing. This deployment's obligations are: serve no credential, load nothing remote, and let no header through. All three are measurable without driving a browser, and each of the three is measured where it is *caused* rather than where it would be *observed*. | no |
| **D143** | §14.4: PostgREST provides no general body-size control, so Traefik enforces `maxRequestBodyBytes` and `memRequestBodyBytes`; "requests one byte above the maximum receive HTTP 413 before reaching PostgREST" and "a body exactly at the limit reaches the upstream". | The reasoning is right and the middleware exists. Whether those two keys behave as stated against **the locked Traefik digest** is a documentation claim, and it is the same class of claim as D141's. | **Adopted, and measured before it is depended on.** Run 6 sends `limit` and `limit + 1` against the locked digest and asserts the two outcomes; the exact-boundary case must reach the upstream and receive a deterministic non-413 answer, which need not be a valid domain payload. `memRequestBodyBytes == maxRequestBodyBytes` for P0, with a test that no spill file is created — which is a filesystem observation of the running container, not an inference from the equality. | ADR 0019's lesson, applied prospectively for once rather than after an edge plane refuses to start. The boundary test is worth more than the middleware assertion: it fails whether the cause is a renamed key, a changed default, or a router the middleware was never attached to. | no |
| **D144** | *(§11.3, §16.2)* `client-error-verbosity = "minimal"` is required configuration and the gate asserts it. | **It exists in neither the locked v13.0.4 nor the runbook's own v14.16.** Both dump exactly 40 configuration keys and neither includes it; it arrives in **16.0**, which is what `latest` resolves to today. The runbook asked the version it pins for a key that version does not have. | **The clause is struck, and the absence is asserted rather than noted.** `test_a_key_the_runbook_requires_does_not_exist` fails on the day it starts existing, because that is the day the workaround can be reconsidered. The workaround is that **every public error is raised deliberately**: the RPCs and the pre-request function raise `PGRST`-coded errors with controlled bodies, and an unexpected error is caught and converted rather than passed through. | ADR 0019's defect, in the runbook's own required-configuration list — and this time found before it was rendered rather than four runs after. The consequence is not cosmetic: without the global control, **PostgreSQL's message text reaches the client verbatim**, which is how D148's private schema name got out. | no |
| **D145** | *(§11.6)* Readiness is `postgrest --ready`, which "checks database pool and schema cache"; §19.2 step 10 verifies "container-local readiness". | **It returns exit 0 while every request is failing.** Measured: PostgREST configured with a `db-pre-request` naming a function that does not exist starts, connects, loads the schema cache, listens, and answers `--ready` with `OK`. Every request to the API returns 404. The probe asks the admin server about the pool and the schema cache and about nothing else. | **`--ready` is necessary and not sufficient, and the healthcheck says so.** It is the liveness-and-pool half; the other half must traverse the surface the service exists to serve. Run 4 decides the exact shape under D139's constraint that a first deploy has no roles yet — but it may not be `--ready` alone. | **This is D101's pooler one session on, in the mechanism the runbook designates as the health check.** The pooler listened while refusing every connection; PostgREST reports *ready* while refusing every request. Nothing about the probe distinguishes the two, which is the entire lesson of that divergence and the reason it was worth measuring rather than reading. | no |
| **D146** | *(§10.1)* "When rejecting with SQLSTATE `PGRST`, put status and error-response headers — including `X-Request-ID`, `Cache-Control: no-store`, and `WWW-Authenticate: Bearer` for 401 — inside the `PGRST` error **`DETAIL`** JSON." | **The two halves are the other way round.** Measured against both versions: the **response body** is the JSON in `MESSAGE` — `{"code","message","details","hint"}`, with `code` and `message` obligatory — and the **status and headers** are the JSON in `DETAIL`. Raising the runbook's way produces `PGRST121`, *"Invalid JSON value for MESSAGE"*, and **HTTP 500**. Raising the measured way produces the intended **HTTP 401** with `WWW-Authenticate: Bearer` and the exact body. | **The measured shape**, and a test that raises each of the four pre-request refusals and asserts the status, the challenge and the body — not the SQL that produced them. | Getting this backwards does not produce a wrong message; it produces **a 500 where a 401 was intended**, which is an authentication refusal reported as a server fault. It would have passed any review that read the SQL, and it fails the first request that exercises it. | no |
| **D147** | *(nothing in the runbook; §11.2 implies an ordinary image)* | **The PostgREST image is distroless.** No shell, no `wget`, no `curl` — `docker run --entrypoint sh` fails with *executable file not found*. It also declares no `ENTRYPOINT`, so an argument passed without `--entrypoint postgrest` lands in `exec` position and is reported as a missing executable. | **A Compose healthcheck can be neither `CMD-SHELL` nor an HTTP probe**, which leaves the binary itself — and that is what forced the version bump (D127), because v13.0.4's CLI has no probe subcommand at all. The Compose service names its command explicitly rather than inheriting one. | Recorded because the failure is silent in the worst direction: a `CMD-SHELL` healthcheck on a shell-less image is reported by Docker as an *unhealthy container*, and the obvious repair is to weaken the check rather than to notice the image. It is also the whole reason a two-major bump was cheaper than the alternatives — adding a shell to the image, or publishing the admin port that is bound to container loopback precisely so nothing can reach it. | no |
| **D148** | *(§14.3)* Errors carry "no SQL query, role list, schema path, hint containing internal names, or failing row data". | **A missing pre-request function discloses the private schema and the function name to an unauthenticated caller.** `GET /thing` with an unresolvable `db-pre-request` returns 404 and `{"code":"42883", "message":"function app_private.does_not_exist() does not exist", "hint":"No function matches the given name…"}`. The row does not come out — it **fails closed** on the data, which is the important half — but `app_private` does. | **The error wrapper is not optional and it is not only for the RPCs.** Every path that can reach a client raises a `PGRST`-coded error with a controlled body, and `API-ERR-001` asserts the *absence of the internal name* rather than the presence of a code. With no `client-error-verbosity` to fall back on (D144), this is the only control there is. | The good news and the bad news arrived together: PostgREST fails closed on the data when its hook cannot resolve, which is the answer §3.2 measurement 2 was written to get. What it does not do is fail quietly, and a schema name is a small leak that tells an attacker exactly which schema to aim at. | no |
| **D149** | *(§7.2)* The surface contract names RPC arguments `title`, `content`, `task_id`, `expected_status`, `new_status`. | **The functions carry a `p_` prefix**, and PostgREST maps JSON body keys straight onto PostgreSQL parameter names — so those five strings are not labels, they are the wire format. A contract naming `title` describes a request body no caller can send. Measured from `0005-write-rpcs.sql`, which shipped `api.create_note(p_title text, p_body text DEFAULT '')`. | **The contract names the parameters as they are**: `p_title`, `p_content`, `p_task_id`, `p_expected_status`, `p_new_status`. And the second half, which is a decision rather than a transcription: **Run 5 drops and recreates `api.create_note` so its parameter is `p_content`**, not `p_body`. `CREATE OR REPLACE FUNCTION` cannot rename a parameter, so this is a drop and a create inside the same migration, alongside the column rename ADR 0048 already requires. | Publishing `content` on the read surface while requiring `p_body` on the write surface is two names for one field, in the one session where the cost of fixing it is zero — no client exists yet, and after this session the name is in a generated OpenAPI document somebody has built against. The prefix itself stays: it is what distinguishes a parameter from the column it writes inside a function body, and renaming *that* away would be a change to five signatures to make a document read better. | no |
| **D150** | *(§7.1)* Every project manifest carries an `api.rest` section, shown unconditionally with `enabled: true`. | **`host.yaml`, `project.alpha.yaml` and `project.beta.yaml` are gitignored operator inputs that exist only on the deployment host**, and none of them has ever seen this section. A required section makes the next render on that host fail against a manifest nobody has touched — before any of Session 5 has been deployed. | **The whole section is optional, and `enabled` defaults to `false`.** A project that declares no REST service publishes `routes.rest: unavailable` with a null URL, which is exactly what every project deployed before this session is. A *disabled* section still has its numbers validated, so a manifest carrying an unusable configuration behind one boolean fails on the day it is written rather than on the day the boolean is flipped. | The alternative is a schema change that breaks a host the operator cannot see from here, and whose repair is to edit two files that are deliberately not in the repository. It also states the right default: a public API is something a project asks for, not something it acquires because a schema had a default. | no |
| **D151** | *(§7.1)* `statement_timeouts` names three roles: `anon`, `authenticated`, and `api_documentation`. | **The platform derives thirteen roles and `api_documentation` is not one of them.** `naming.ROLE_SUFFIXES` is the sole authority and a fourteenth entry is a Session 5 decision that belongs with the role's creation, not with a manifest key that references it. | **The manifest may name only roles the platform derives, checked against `naming.ROLE_SUFFIXES` rather than against a list written beside it.** The fixtures set `anon` and `authenticated`. The day the documentation role exists, it becomes namable here with no schema change and no test change. | A timeout set on a role nothing created is applied to nothing, reports nothing, and reads in the manifest exactly like one that works — this project's signature defect in a configuration file. Validating against the derivation rather than against an enumeration is what makes the check keep meaning something after the roles change. | no |
| **D152** | *(§11.5)* The admin server is "container-loopback-only", and §11.7's negative test is that probes to `postgrest:3001` from another container fail. | **It binds whatever `server-host` binds.** Measured with a control: with `server-host = "0.0.0.0"` — which every containerised service needs — and only `admin-server-port` set, `--dump-config` reports `admin-server-host = "0.0.0.0"`, and `/live` and `/ready` **answered a peer container on the project network**. With `admin-server-host = "127.0.0.1"` the same peer is refused and `--ready` still works from inside. | **`admin-server-host` is set explicitly and the negative probe is a real test**, not a restatement of a property. The §11.7 assertion is right about what must be true and wrong about what makes it true: it would have passed against a configuration that published the admin surface to every container on the network, because nothing would have been probing for it. | The runbook's sentence is a description of a *default* that is not the default. A service is loopback-only when it is told to be, and the failure of not telling it is silent in the direction that matters — the admin surface answers, to the wrong audience, and every other check stays green. | no |
| **D153** | *(§11.6, §19.2 step 10)* Container-local readiness is `postgrest --ready`. | **`--ready` is a client and it reads its own configuration, not the running process's.** Against a service answering 200: bare `--ready` exits **1** with *"Admin server is not running"*; `--ready /path/to/postgrest.conf` exits 0; `PGRST_ADMIN_SERVER_PORT` alone exits 1 with *"the `--ready` flag cannot be used when server-host is …"* because the default host is a wildcard; both `PGRST_ADMIN_SERVER_HOST` and `PGRST_ADMIN_SERVER_PORT` exit 0. | **The healthcheck names the configuration file**, and a contract test asserts that the bare form fails — so the obvious spelling cannot be written and pass. The healthcheck process therefore reads a file containing `db-uri`; it prints nothing, and Run 4's no-secret-in-logs assertion covers the command as well as the service. | This is D145 from the other side, and the pair is the whole lesson. `--ready` returns **0 while every request fails** when the hook cannot resolve, and **1 while every request succeeds** when nobody handed it a port. Neither direction is a readiness signal on its own, and the version bump this probe justified (D127) bought a mechanism that needs two more decisions before it means anything. | no |
| **D154** | *(§13.2)* The public JWKS is "verification-only" and generation refuses a key carrying a private parameter — stated as a property of the pipeline. | **PostgREST does not refuse one.** A JWKS whose single key carried `d` was loaded and served a request normally. Nothing between the file and the verifier objects to a private key being published. | **Unchanged in substance and reclassified in weight.** `jwt_keys.assert_public` refuses all seven RFC 7518 private parameters, by name, against the complete set — and it is now known to be the *only* thing that would. `test_jwt_keys.py` asserts the refusal against a deliberately malformed input, one test per parameter, which is what ADR 0051 asked for and now the reason it asked. | The check was written as belt and braces over a service assumed to be doing the same thing. It is not: the service accepts what it is given. A generation bug that published the signing key would produce a working deployment, and the only signal would be the file itself. | no |
| **D155** | *(§11.4, and this plan's own Run 4 paragraph)* "The entrypoint assembles the database URI in tmpfs at `0600` from the mounted secret file and never logs it" — the shape Session 4 used for the pooler, dbmate and three client fixtures. | **There is no entrypoint that can.** The image is distroless (D147): no shell, no `wget`, no `curl`, no declared `ENTRYPOINT`. Nothing in the container can read one file and write another. Run 4 measured the four ways a password could arrive instead, with a control that put it inline to prove the rig was real — inline works, `PGPASSFILE` works, `?passfile=` inside the conninfo works, and the `@file` form holding a whole URI works. | **The configuration is `PGRST_*` in the environment and the credential is a file named by `?passfile=`** (ADR 0056). Every environment value is a derived non-secret identifier interpolated by Compose; the mounted file is `*:*:*:*:<password>`, written in that shape by the materializer because nothing downstream can wrap it. Measured on a running container: the password is in no environment variable, no argument (`.Args` is empty), no label, no log line and nothing `docker inspect` prints, while the request path answers 200. | The `@file` form was the near miss: it works, and it would have put a derived role, host and database name inside an operator-facing value — which is D60 exactly, one session on. The wildcards in the pgpass line are the same decision at a smaller scale: naming the four match fields would put those identifiers in a secret file that goes stale when any of them changes, with `fe_sendauth: no password supplied` as the symptom and the wrong file as the place to look. | **yes — ADR 0056** |
| **D156** | *(§11.6)* The container healthcheck proves readiness, and §19.2 step 10 verifies it. This plan's §5 adds D101's rule: a healthcheck must prove a failure a port check calls healthy. | **Half of that is reachable from inside this container and half is not.** `postgrest --ready` proves the pool and the schema cache, which a port check does not — that half is real, and it works bare here only because the configuration is in the environment, so the probe's own configuration *is* the service's (D153). The other half is the request path, and D145 measured `--ready` returning 0 while every request 404'd. With no HTTP client in the image, no check that traverses the surface can run inside the container. | **The healthcheck is `postgrest --ready` and the comment above it says what it cannot prove.** The request-path proof moves to the deploy's own verification and to `API-REST-001`, where it is a real request rather than a probe standing in for one. | Writing this down is the point. A healthcheck that proves the pool and is *described* as proving readiness is how D145 happens again — the failure it misses is precisely the one the deploy is otherwise most likely to have, and a green container beside a 404 is the shape this repository keeps producing. | no |
| **D157** | *(§5)* "Run 5 — **Migration 0007** and role activation": one migration carrying the convergence, the pre-request function and the request-role grants. | **The two halves have different diffs and different failure modes.** One is a data migration against two live projects: a column rename, a derived enum, a dropped boolean, two rebuilt views and two rebuilt functions. The other is four grants, one of which -- `USAGE ON SCHEMA app_private` to every HTTP caller -- is the largest authorization change in this session and is invisible inside a two-hundred-line diff. D136 already assumed both, describing a proof "between `0007` and `0008`". | **`0007-api-surface-convergence.sql` and `0008-http-request-plane.sql`.** The second migration's entire content is the pre-request function and the grants that reach it, so the line D138 warns about is the diff rather than a line in one. | D138's own words: the grant "is invisible in a diff that reads as one `GRANT USAGE`". The remedy for that is not a better comment, it is a diff in which it is the only thing to read. Splitting also keeps the fix-forward story honest -- the convergence is the migration that touches data, and it is the one an operator is most likely to have to reason about after the fact. | no |
| **D158** | *(§5, Run 5)* "The documentation role's metadata-visible grants." D151 already settled that the manifest may name it "the day the documentation role exists". | **`naming.ROLE_SUFFIXES` derives thirteen roles, and a fourteenth is an outputs schema version** -- `database.roles` is `required` with `additionalProperties: false` on both branches, so the role cannot exist without a v6 and a `migrate_v5_to_v6` whose new field no code path reads until Run 7. And Run 5's measurements changed what the role's grants have to be: `follow-privileges` publishes the **whole** surface to a role holding view `SELECT` and no base-table grant -- the document is complete and every read is 403 -- but a write RPC only appears if the role holds `EXECUTE`, and a role holding `EXECUTE` **wrote a row** when a token carried a subject. | **The role lands in Run 7, with the capture tool that is its only consumer**, and with the pre-request rule the measurement showed it needs: the hook refuses to establish an identity for the documentation role, so `EXECUTE` publishes the RPC and can never perform it. The measurement is banked in `tests/contract/test_api_behaviour.py` now, so Run 7 inherits a decided question. | `migrate_v4_to_v5`'s own reasoning is the argument: a version bump that no code path exercises is the thing to avoid. And the grants are not derivable from the plan sentence -- "metadata-visible" turned out to mean two different things depending on whether a write RPC is in the document, which is exactly the kind of detail that gets settled wrongly when the consumer is three runs away. | no |
| **D159** | *(§4.3, ADR 0052, D138)* The `app_private` grant is bounded to "active impersonated roles", and migration 0006's revocation of that same `USAGE` from `app_runtime` stands. | **`app_runtime` gets it back, by inheritance, and nothing anticipated that.** It is a member of `authenticated` with `INHERIT TRUE` (bootstrap, Session 4), so `GRANT USAGE ON SCHEMA app_private TO {{authenticated}}` reaches it. Measured on a cluster with all eight migrations applied: `has_schema_privilege(app_runtime, 'app_private', 'USAGE')` is **true**, one session after 0006 made it false on purpose. | **Accepted, and asserted rather than left to be noticed.** `USAGE` alone resolves names and confers nothing, and `app_runtime` holds no privilege on any object in the schema -- which is checked, per role, in all four table modes. `test_the_runtime_role_inherits_the_private_schema_grant_and_nothing_in_it` states the inheritance as a fact with a reason, so a later migration granting a private table to `authenticated` fails there instead of reaching an application by a path nobody wrote down. | The alternatives are worse in both directions. `INHERIT FALSE` on the application's membership would make it `SET ROLE` to do its job. A fifth schema for one function is the change ADR 0052 already refused. What is left is to say out loud that the boundary 0006 drew now has one hole in it, that the hole is empty, and where the test is that would notice it filling up. | no |
| **D160** | *(§4.12)* An error table mapping application codes to HTTP statuses, with D130 narrowing it to "the HTTP mapping is written from the codes that exist". | **There is no mapping to write.** Measured against the locked image: the SQLSTATE *is* the mechanism -- `PT401` is 401 with a `WWW-Authenticate` challenge, `PT404`/`PT409`/`PT422` are their numbers, and a bare `RAISE EXCEPTION` stays `P0001`, which is **400**. Two further findings decided the migration's shape: `HINT` and `DETAIL` are published to the caller **verbatim**, so 0005's "SET LOCAL app.user_id before calling this function" was on its way to becoming a public sentence about an internal GUC; and `28000`, the semantically exact code for a missing identity, answers **403** with no challenge. | **ADR 0057.** The function chooses its status by choosing its SQLSTATE, and no caller-reachable raise carries a `HINT` or a `DETAIL`. `AP900` keeps both and is exempt: only a `migrate:down` block and the derivation guard raise it, and their reader is an operator at a terminal. | An error table is a contract about behaviour, and this one would have been written from documentation and read as configuration. The hint is the part that would have shipped: it is correct, useful, was written for the right audience in Session 3, and becomes a disclosure the moment the same function is reachable over HTTP. Nothing in the migration that contains it looks like a leak. | **yes — ADR 0057** |
| **D161** | *(§5, Run 5)* Role activation sets "an explicit `CONNECTION LIMIT` fitting the queried budget". | **Half of that arithmetic has nowhere to come from, and the other half is already spent.** The rendered document carries no `api` block, so the bootstrap plane cannot see the declared `pool_size`; and `app_runtime` is already given `max_connections - superuser_reserved - 5`, which is everything. A limit for the API on top of that produces two limits that **sum past what the server will hand out**. | **The authenticator is activated with `LOGIN`, a password from its materialized file, and its two memberships -- and deliberately no `CONNECTION LIMIT`.** Both limits land together with the live re-computation of the connection budget (§3.2 measurement 5), which queries the server rather than extrapolating. The manifest-side check that a declared pool fits the budget stays where it is. | Setting one ceiling without lowering the other is a budget that looks computed and is not, which is this project's signature defect applied to a number. The honest intermediate state is no limit at all: the role is bounded by `max_connections` like every other, and nothing claims otherwise. | no |
| **D162** | *(§5, Run 6)* "The REST router with an exact prefix boundary." | **The obvious spelling is not one.** Measured against the locked Traefik: a router ruled ``PathPrefix(`/api/rest`)`` answers `/api/restaurant`, `/api/rest-extra` and `/api/rest2` with **200**. `PathPrefix` is a string prefix, not a segment prefix — and `config.RESERVED_BASE_PATHS` already refuses overlaps *segment-wise* (ADR 0005), so the manifest layer and the edge would have disagreed about what a path boundary is, with the permissive one at the front. | **Every prefix route is a pair: ``Path(`X`) \|\| PathPrefix(`X/`)``** (ADR 0059). Both halves are load-bearing — the `PathPrefix` alone 404s the bare `/api/rest`, which is the URL the deployed document publishes. Asserted offline as a shape and live as an outcome, with a **control router ruled the naive way** that must over-match. | Without the control the negative assertions are satisfied by any rule that happens to 404, including a broken one. And the rule is written down as a property of route boundaries rather than of one router, because the next one will be written by copying this one. | **yes — ADR 0059** |
| **D163** | *(§5, Run 6)* "A `usersFile` cannot be a label at all, so the credential middleware is the **first per-project artifact this repository writes into the Traefik file provider**." | **The middleware can be a label; the file cannot.** Measured: a container carrying `traefik.http.middlewares.<n>.basicauth.usersfile=/etc/traefik/dynamic/<f>` produces a working middleware — 401 without a credential, 200 with it, and the `Authorization` header removed before the upstream sees it. What no label can do is *put the file there*. | **The conclusion stands and the reason changes**, which is worth the row because the reason is what the next reader reuses. The middleware is written into the file provider anyway, deliberately: defined there it exists independently of any container's lifecycle, so a documentation service being recreated cannot leave a router referencing a middleware that has momentarily stopped existing — which Traefik rejects route by route while the hostname keeps answering 404 behind a valid certificate. | A design justified by an impossibility that is not one is a design nobody can revisit: the next person to want a label finds a sentence saying it cannot be done, rather than a trade-off they can weigh. | no |
| **D164** | *(§5, Run 6)* A response-header middleware sets `Cache-Control: no-store` and removes any upstream `Server` header on **every** response — "including the ones that never reach a database transaction". | **True for every response a project router produces, and not for a path no router matched.** Measured: attached to the router, the policy reaches the **413 the buffering middleware itself generates**, which is the case the clause is really about. It does not reach Traefik's bare 404 for an unrouted path, and configuring the chain at the **entry point** does not change that — a chain is a property of a router, and no router ran. | **The policy is a middleware in `apg-baseline`**, so every project route carries it and adding it touched no project. The unrouted 404 is recorded as the boundary it is. | The gap is real and small: that response belongs to no project, carries no body and discloses nothing. What matters is that "every response" now means *every response this deployment routes* rather than every packet the port answers, and the difference is written down instead of being discovered by someone who assumed the stronger reading. | no |
| **D165** | *(§8.5, D140)* The documentation credential's bcrypt hash is generated "through the locked Python toolchain". | **The host cannot generate it.** `crypt` was removed from the standard library in Python 3.13 and the development host's interpreter is 3.14 — `import crypt` raises `ModuleNotFoundError`, so there is no in-process way to produce a hash on any current host. The locked runtime image is 3.12 and its glibc offers `METHOD_BLOWFISH`, which produces the `$2b$` form. And the format is not a preference: Traefik refuses a SHA-512 crypt hash — what `crypt.crypt` produces by default, and what a host `mkpasswd` hands you — with **401 on a correct password**, indistinguishable from the operator mistyping it. | **The hash is produced inside the locked runtime image**, and `edge_credentials.assert_bcrypt` refuses every other format before the file is written. The validation is pure and tested; the one impure step is a container invocation the caller owns. | "Through the locked toolchain" turned out to mean *in a container* rather than *by the deploy script*, and the reason it matters is the failure mode: a wrong-format hash produces a documentation route that refuses the right password, with nothing in any log naming the hash as the cause. Checking the format where it is written is the only place the mistake is visible. | no |
| **D166** | *(ADR 0050, consequences)* "Normalization replaces host, base path, **title suffix** and **server metadata** with sentinels." | **Two of those four fields do not exist.** The document is **Swagger 2.0**, which has no `servers` block at all, and `info.title` is the constant `"PostgREST API"` — measured identical across two projects' worth of configuration. Restarting the same service with `openapi-server-proxy-uri` set changed exactly three top-level fields, `host`, `basePath` and `schemes`, and left `info`, `paths`, `definitions` and `parameters` byte-identical. The `Host` request header reaches none of them: without a proxy URI the document carries the container's own `0.0.0.0:3000`. | **Two fields are substituted and the third is asserted.** `host` and `basePath` become fixed sentinels; `schemes` is *compared* against `["https"]` rather than replaced, because a capture taken straight off the container carries `["http"]` and replacing it unread would write a snapshot claiming a transport the captured service never offered. `info.version` and `externalDocs.url` carry the PostgREST version and are deliberately kept, so a version bump reaches a reviewer through the snapshot diff. | ADR 0050's decision is untouched; only its list of fields was written before anything was measured. Recording it rather than quietly implementing the right list is what stops the next reader from looking for a title-suffix substitution and concluding the normalizer forgot one. The sentinel host is `project.invalid:443` because RFC 2606 reserves `.invalid`, so no deployment can ever serve it — a sentinel a real value could equal is a sentinel that can be satisfied by accident. | no |
| **D167** | *(§5, Run 7)* "Normalization is deterministic and strict, with duplicate-key rejection, **sorted map keys**, and sentinel substitution." | **The order is already deterministic, and sorting is not what makes it so.** Measured: two clusters built with the objects created in opposite orders produced **identical** key order, and the same document fetched three times was byte-identical. The order is a hash artifact — `/tasks` precedes `/notes`, and an inserted `/extra` landed between them without moving either. So what sorting buys is a diff a reviewer can read, not a document that stops moving. | **Sorting stays, with the honest reason, and one rule beside it: map keys are sorted and array order is never touched.** `enum` arrays carry `enumsortorder` — which the surface contract calls order-sensitive, because a reordering passes a set comparison and changes what every generated client lists first — and `required` arrays carry argument order. `test_an_enum_keeps_its_declared_order` and `test_a_required_argument_list_keeps_its_order` both go red the moment `sort_maps` starts sorting arrays. | A rule kept for a reason that turns out to be false is a rule the next person deletes, and this one has a real reason underneath the wrong one. The dangerous half is the array: a comparator that sorted everything would normalize away exactly the differences it exists to notice, and it would do it silently. Nothing promises the hash order stays stable either, which is the second reason to sort and the one that would otherwise be mistaken for the first. | no |
| **D168** | *(§6, and `contracts/postgrest-api-surface.yaml`)* The relations declare `methods: [GET, HEAD]`, and `API-CONTRACT-001` compares the committed snapshot against that contract. | **`follow-privileges` filters the path, not the methods on it.** Measured with the grant read back out of `information_schema.role_table_grants` rather than assumed: a role holding **`SELECT` and nothing else** on `api.notes` is served a document advertising `delete`, `get`, `patch` and `post` — and all three writes return **403 `42501 permission denied for view notes`**. `HEAD` is served with 200 and is **not** in the document. The published method list is a property of the relation being an updatable view, not of what the caller may do to it. | **ADR 0060.** The snapshot↔contract comparison is at the level of *objects*; `methods:` is enforced against the catalog by `API-RPC-001`, which attempts each refused method. The extra methods are not stripped during normalization, because a snapshot that differs from the served bytes stops being the document a client is generated from. | A method-for-method comparison could only ever have failed, and its repair is the dangerous one: widening `methods:` to the published set would make `api_surface`'s refusal of table-style writes unreachable, converting the reviewed read-only surface into a permissive one — in the one file whose entire function is to be narrower than the catalog. This is §6's defect with the green test on the wrong side of it. | **yes — ADR 0060** |
| **D169** | *(§5, Run 7; D158)* "The hook refuses to establish an identity for the documentation role, so `EXECUTE` publishes the RPC and can never perform it." | **True, and the refusal has to be written in one specific way.** `current_user` is a SQL construct the parser rewrites, not a function to look up — the same class as the `nullif` that took the whole API down in migration 0008 — so `pg_catalog.current_user` is a hook that fails on every request while the service stays healthy. Measured both ways against the locked image: **`current_user::text = <literal>` works** inside a function pinned to `search_path = pg_catalog, pg_temp`. The rest of D158 measured out exactly as stated: a bare documentation token fetches the OpenAPI document (**200**) and sees `/rpc/create_note` in it; one carrying a subject is **401 `PT401`**; a bare one calling that RPC is **403 `new row violates row-level security policy`**; and the table held only the seed row and the control's own write afterwards. | **Migration 0009**, carrying the grants and the replaced hook together, and two placeholders — `api_documentation` (identifier) and `api_documentation_name` (literal) — resolved from **one** source key so they cannot name different roles. The refusal *raises* on a subject rather than ignoring it: the outcome is the same today and the difference is between a credential that cannot act and a request that was quietly reinterpreted. | The measurement that mattered was not whether the design works but whether the one line expressing it parses, because its failure mode is the one this repository has already paid for once: a hook that resolves at deploy time, reports a warm schema cache, and refuses every request. Writing it from the 0008 comment rather than measuring would have been reading the lesson and repeating the mistake. | no |
| **D170** | *(implicit in every hook test)* `tests/contract/test_api_migrations.py` reads the pre-request function out of migration 0008 by name. | **Migration 0009 replaces that function, and every one of those tests stayed green describing a body no request executes.** `CREATE OR REPLACE` means the last migration to define the function is the only one whose body runs; seven tests — writes-nothing, pinned search path, the `nullif` qualification, the UUID refusal, transaction-locality, fail-closed — were all still asserting things about the superseded text, and all still passing. | **The constant is replaced by a derivation.** `effective_hook_template(manifest)` walks the migrations in applied order and returns the last one that defines the function; every hook test reads that. `test_the_effective_hook_is_the_last_migration_that_defines_it` asserts it currently resolves to 0009, so a future 0010 that replaces the hook again fails there rather than silently retiring seven assertions. | This is §6's defect found inside the machinery built to catch §6's defect, which is the reason it is worth a row of its own. The tests were not wrong when they were written and no edit made them wrong — a *new file* made them wrong, silently, and nothing in a diff of that file would show it. The repair is not to update a constant, it is to stop having one. | no |
| **D171** | *(§5, Run 7)* "Tokens reach a child through an already-open descriptor or a tightly scoped environment, never through argv or stdout." | **The environment is reachable and the obvious spelling of it is not tight.** `env VAR=value command` puts the value in `env`'s *own* argument vector, where `ps` shows it to every user on the host — so the spelling that reads as "through the environment" is the one that publishes it. And there is no JWT dependency to sign with: `requirements-dev.txt` is hash-locked and covers the development environment, and the standard library has no RSA. Measured end to end against the locked PostgREST: a token signed with **`openssl dgst -sha256 -sign`** and verified against the JWKS derived from the same key answers **200**; one signed by a different key is **401 `PGRST301`** ("None of the keys was able to decode the JWT"); an expired one is **401 `PGRST303`**; and `PGRST_JWT_SECRET=@/path/jwks.json` loads a key set from a mounted file. | **`os.execvpe`**, so the token crosses into the child through the environment block of `execve` and never through an argument vector, and **openssl for the signature** — the only route that adds no unlocked input. `test_dev_token_passes_the_token_through_execve_and_not_through_argv` asserts the spelling on the source, because both spellings run the child with the variable set and only one of them is visible in `ps`. | ADR 0051 measured that PostgREST *accepts* RS256, which is not the same claim as "this is how to produce one" — two third parties agreeing about a signature format is exactly ADR 0019's class. The control is the load-bearing half: without the wrong-key probe, a service that ignored signatures entirely would have passed the positive test, and the tool would have shipped minting tokens nothing verified. | no |
| **D172** | *(this file's own test, `test_dev_token_never_writes_the_token_to_a_stream`)* A source scan asserting no line containing `print(` also contains the token. | **A `print()` spread over four lines has the interpolation on a line carrying neither `print(` nor `file=`.** The mutation that plants `f"token={token}"` inside an existing multi-line call walked straight through the scan, which stayed **green while the command printed the credential**. Found by running the mutation, not by reading the test. | **The scan parses instead.** `ast.walk` finds every call to a writer and checks whether the `token` local appears anywhere in its arguments, however the call is formatted — and `test_the_token_writing_scan_would_catch_a_real_one` plants exactly the multi-line shape that defeated the first version. | This is the run's second instance of a green test measuring nothing, and the second one found only because the mutation step is not optional. The first (D170) was a test pointed at a superseded file; this one was pointed at the right file and looked at the wrong lines. Both would have read as thorough in review. | no |
| **D173** | *(§2.1/§2.2, as written)* The activated tests compare "the served surface" against "the reviewed contract". | **There are two `declared_objects` in this repository and they spell an object differently.** `api_surface.declared_objects` returns `api.notes`; `openapi_normalize.declared_objects` returns `notes` and `rpc/create_note`. Both docstrings say they exist so the two sides of `API-CONTRACT-001` can be compared, and neither is the bridge — `bin/api-contract.py:surface_objects` is. Written the obvious way, Run 8 produced both failure modes at once: a containment check `served <= api_surface.declared_objects(...)` that would have failed on **every** run against disjoint sets, and a `probe not in declared_objects(...)` that could **never** fail, because a bare name is absent from a set of qualified ones for every possible contract. | **Every comparison goes through `surface_objects`**, exposed as an `api_contract` fixture in `tests/deployment/conftest.py` so both modules that need it use the same one, and the offline probe assertion qualifies the name from the contract's own `exposed_schema`. Measured both ways with the text-scan assertion removed so the comparison was isolated: qualified catches the planted object, bare does not. | The vacuous half is the one worth the row. It was not caught by a test failing — it was caught by reading which function returned which spelling, and the mutation only confirmed it afterwards. A reviewer looking at `ACCEPTANCE_PROBE_FUNCTION not in declared_objects(surface)` reads a check; what is there is a tautology. §6's defect in its purest form: a value that looked measured and was not. | no |
| **D174** | *(§2.2, as written)* "The environment split is enforced here, not discovered in Run 10. No requirement's node IDs straddle host and external. `claim_mode` is what would refuse it." | **`claim_mode` refuses a straddle and accepts a relocation.** Measured with controls: a requirement carrying one `live_host` node ID and one `external` one makes four tests in `test_evidence_claims.py` fail, including `test_every_claim_proof_is_collected_by_exactly_one_selector`; the same construction with both node IDs on the host resolves cleanly. But `SEC-API-001` repointed *wholesale* at a host test — its only proof moved off the network it is about — fails nothing at all once `docs/acceptance-matrix.md` is regenerated. `public_api_boundary` simply becomes a host claim, and the external gate quietly stops carrying a Session 5 claim. | **Recorded, not fixed.** The enforced property is "no claim spans two environments", which is what the mechanism computes and what the merge needs. "This requirement is measured off-host" is a property of the requirement's meaning, and nothing derives it — the registry has no field for the environment a requirement *belongs* to, and adding one would be a second authority beside the markers, which is the shape ADR 0045 rejected. It stays a review rule, written down here rather than assumed. | Found by a mutation that was expected to go red and came out green. The plan's sentence is true of the failure it names and wider than the mechanism: a straddle is refused, a migration is not. Session 6 inherits the question, because retiring the bootstrap issuer moves `SEC-BOOT-001`'s proofs. | no |
| **D175** | *(§2.2 and the registry comment beside `DEP-ISO-004`)* `DEP-ISO-005`'s cross-project clause "gains node IDs of its own here, which the registry records as an activation obligation rather than leaving to memory." | **The registry records it; nothing enforces it.** Deleting the cross-project node ID and leaving the structural one fails exactly one test — `test_acceptance_matrix_is_generated_from_the_registry` — and that test passes again the moment the matrix is regenerated, which is a normal step of any registry change. So the obligation is discharged by review or not at all, and D70's failure is reachable again by an edit that looks routine. | **Both node IDs are written, and the honest limit is recorded here.** No structural check is added: "this requirement's proofs cover its description" is a statement about English, and a test that could decide it would be a test that could read the description. What *is* structural stays — a requirement must name at least one collectible node ID, and a claim must resolve to one mode. | The measurement is the point: the drift check that appeared to catch this is checking that a generated file matches its source, not that a claim still has its proof. Two different questions with the same red. D70 cost two runs; this is the note saying the machinery that was supposed to prevent a third does not. | no |
| **D176** | *(§4.4, as written)* The transient acceptance object is "owned by the object owner, executable only by the fixture role". | **There is no single fixture role, because `openapi-mode = follow-privileges` decides who can see the object.** The row-ceiling and timeout proofs call it as `authenticated`, so that role needs `EXECUTE`; the reload proof asserts it *appears in the served document*, and the document under test is the documentation role's — a role without `EXECUTE` is served a document that never mentions it, so the reload would look like a dead listener. One grant cannot serve both. | **Two uses, two grants, one reserved name.** `rendering.ACCEPTANCE_PROBE_FUNCTION` is a constant for D109's reason restated — a name chosen per run cannot be asserted absent by a test that does not know it. The `acceptance_probe` fixture grants `EXECUTE` to `authenticated`; the reload test creates its own and grants it to `api_documentation`. Both hold `rendering.project_lock` across creation as well as teardown, both `NOTIFY` on each side, and both assert the object and its rows are gone afterwards — a cleanup failure is a failure. Three tests check the name is absent: two on the host, one offline against the reviewed contract. | The grant is not a detail: it is the same ADR 0060 fact one layer down. What a caller is *shown* follows its privileges and what a caller may *do* follows its privileges, and Session 5 keeps finding places where those two are assumed to be one thing. | no |
| **D177** | *(§5 Run 9, as written)* "only then add edge membership and **publish the two routers**" — the REST route and the documentation route, each at the prefix this session derives. | **The repository derives the documentation path twice, and the two disagree.** `naming.derive` produced `route_docs = https://<domain>/docs` — the root `RESERVED_BASE_PATHS` holds for a Session 11 index — while `config.DOCS_REST_PATH` said `/docs/rest`, which is the only path anything has measured: Run 6's edge rig proved 401 without a credential, 200 with it and the `Authorization` header stripped, all at `/docs/rest`. Nothing put the two in one expression, so no test could see it. `routes.docs` is what `rendering.py` writes and `deployed_output.py` copies with a status, so it is what `bin/docs.py`, `SEC-DOCS-001` and `SEC-API-001` all request — **one segment above the router Run 9 was going to publish.** `bin/docs.sh check` would have returned **404, not 401**, and correctly refused to call that a refusal; two of Run 8's new proofs would have failed for a reason that is not a boundary, in the middle of a maintenance window. | **ADR 0061: a published route names the page, not the root above it.** `naming` gains `DOCS_ROOT_PATH` and `DOCS_PAGE_PATH` and is the single authority ADR 0002 says it is; `config.DOCS_REST_PATH` and `REST_PATH_SUFFIX` become reads of it rather than literals. `routes.docs` is now `https://<domain>/docs/rest` on both branches. No schema bump — the value is still an `httpsUrl`. `test_derived_identity_matches_the_specified_table`'s `== ".../docs"` is **replaced by a stricter assertion** under that ADR, and a new test asserts the *derived URL* ends with the *compared prefix*, because two constants agreeing is not the property. Both mutations confirmed red: reverting `route_docs` to the root, and restating either constant in `config`. | Found offline while checking that a session-5 render works before a human spends a window on Run 9 — which is the whole reason the host half of a run gets rehearsed early, and the same shape as D100 one session on. The rejected alternatives are in the ADR; the one worth naming here is *publish the router at `/docs` instead*, which would have made the two agree by discarding the only measurement anybody has. Note also what was **not** wrong: `REST_PATH_SUFFIX` carried a comment saying it was "kept in step with `naming.derive`", and it was. The one with no comment was the one that had drifted. | **yes** |
| **D178** | *(D150, and `rendering.build_compose_env`'s own comment)* `api.rest` is optional, so "a project with no REST service still has to render" — and an empty CORS list is emitted as an empty string "rather than being omitted, because an unset variable is a required interpolation that fails". | **The mechanism does not do what the comment says, and the first live deploy failed at step 1 having touched nothing.** `compose.yaml` referenced `${POSTGREST_CORS_ORIGINS:?required}`, and Compose's `:?` form rejects an **empty** value as well as an unset one. Measured against Compose 29.5.2, both spellings against both inputs, with a rendered control: `${VAR:?err}` fails unset **and** empty; `${VAR?err}` fails only unset and renders `""` otherwise. So a manifest without `api.rest` — which `project.alpha.yaml` was — rendered `POSTGREST_CORS_ORIGINS=` and could not be validated at all. Nothing caught it because every test renders `project.example.yaml`, which names an origin, so the empty case had never been rendered. | **One character: `${POSTGREST_CORS_ORIGINS?required}`.** It is now the only variable in the model spelled without the colon, and the reason is written beside it — every other required interpolation names an identifier, a port or a secret reference, none of which is ever legally empty, so `:?` is right for those and wrong for exactly this one. Unset still fails, so a `compose.env` missing the key remains an error rather than a permissive default. The rejected alternatives were emitting a sentinel origin, which is a value PostgREST would parse as an origin, and making the service conditional on `api.rest.enabled`, which D150 deliberately refused. `test_no_required_interpolation_names_a_value_that_renders_empty` renders the no-REST case and compares the set of variables that come out empty against the set the model marks `:?` — **both sides derived**, one from a real render and one from the model's own text, so neither is a copy of the other. Confirmed red by restoring the colon, green unmutated, and the real `docker compose config` now accepts a no-REST project. | The first defect the live path produced, and it is §6's shape with a comment on top: the author reasoned about the failure correctly, chose a mechanism that does not produce it, and wrote the reasoning down where it reads as evidence. A reviewer checking "does an empty list render safely?" would have found a comment saying yes. **Separately: `project.alpha.yaml` declaring no `api.rest` is also an operator-input gap** — a Session 5 project needs the block or it publishes no REST route and none of Run 8's sixteen proofs can run. Two problems, one symptom; fixing only the manifest would have left the code broken for every project that legitimately declines a REST service. | no |
| **D179** | *(this file's own first draft of `bin/render-jwks.py`)* "The private key is read by `openssl` and never by this process… `-noout` is what keeps the key itself out of the output." | **`-noout` suppresses the re-encoded key, not the text dump.** Measured against OpenSSL 3.5.5 with a control confirming the search finds them when present: `openssl rsa -in <private> -noout -text` prints `privateExponent`, `prime1`, `prime2` and the coefficient. The obvious way to read a modulus and an exponent therefore pulls the entire private key into a captured `stdout`, where a traceback, a log line or an exception message can carry it — for the one secret in this system that must never leave the root plane. Also measured: the public path labels the field **`Exponent:`** while the private path labels it `publicExponent:`, so a pattern written against one silently matches nothing on the other. | **`-pubout` first, then read the public half over a pipe.** Two invocations take the public PEM on stdin, so no private parameter is ever in this process and no temporary file holds one. `test_the_derivation_never_reads_private_material` parses the source and asserts the *spelling*: any invocation carrying `-text` or `-modulus` must carry `-pubin` and must not name a key file, and the only invocation given the private key's path must be the `-pubout`. Both leaking spellings confirmed red. The exponent pattern accepts both labels and a miss is an error rather than a default of 65537 — a default would be correct for every key this project generates, which is exactly what would keep it from being noticed. | The comment was the dangerous part, not the flag. It stated a security property in the voice of a measurement, and a reviewer checking "does this read private material?" would have found a sentence saying no. §6's shape, in a file written to protect the one key that has no second copy. | no |
| **D180** | *(every mutation battery this session has run)* A mutation that leaves the tests green means the tests do not measure the mutated property. | **Not if the mutation does not change the file's length.** Python invalidates a cached `.pyc` on the source's mtime **to the second** and its **size**. A battery that restores a snapshot and then mutates within the same second, changing `"jwks.json"` to `"keys.json"` — the same byte count — runs the **stale bytecode**, and the verdict describes the unmutated code. Found because the harness reported "stayed green" for a mutation that, run by hand, went red immediately and with a clear message. | **`PYTHONDONTWRITEBYTECODE=1` and a cleared `__pycache__` before every battery**, recorded in `CLAUDE.md` beside the other traps. The two batteries already run this session were re-run under it and re-confirmed. | This is the session's fourth instance of a check that did not check, and the first one inside the *verification* rather than inside the thing verified. Worth writing down for its blast radius: every same-length mutation run before this was noticed is unverified, and "the mutation went red" is only evidence if the mutated bytes were the ones executed. | no |
| **D181** | *(§5 Run 9, and `bin/deploy-project.py`'s own comment)* "Session 5's runs replace these with observations of a running PostgREST." The deploy hard-codes `routes.rest`, `routes.docs`, `api` and `jwt` to `unavailable`. | **The observation was unbuilt, and the first live deploy proved it by succeeding.** PostgREST came up healthy, all nine migrations applied, and the deployed document said `unavailable` about every Session 5 field — correctly, because nothing observed them. Three further facts the deploy surfaced: `api.status: ready` requires all three checksums (the schema's own `else` branch), so a project's **first** deploy can never publish one — the canonical snapshot is captured *from* a running deployment and reviewed by a human, so it does not exist yet. And **`routes.docs` cannot become ready at all**: `services/docs/` holds a `.gitkeep`, `compose.yaml` declares no such service, and D128's choice between an upstream Scalar image and a first-party build is recorded as "settled in Run 1" by the plan while no ADR records a decision and nothing implements one. | **`observe_jwt`, `observe_served_document` and `observe_api`.** The JWT block is derived from the key set the deploy just wrote — identifiers and a digest, never material — and `temporary: True` is the value `SEC-BOOT-001` compares against `deployed_through_session`. The served document is fetched as the documentation role, because `follow-privileges` makes "the OpenAPI document" depend on the caller. `api` is `ready` only with a reviewed snapshot **and** a served document, so the two-deploy sequence D112 already established is what publishes it. `routes.docs` stays `unavailable` with the reason in the code: nothing serves it. | The deploy was not wrong; it was honest about being incomplete, and its comment said which run owed the work. What is worth carrying forward is the third fact: **a route this session's requirements depend on has no service behind it**, and the plan asserts that question was settled. `SEC-DOCS-001` and the documentation half of `SEC-API-001` cannot pass until D128 is decided and built, which is a run of its own rather than a step in this one. | no |
| **D182** | *(this run's own mutation batteries)* A mutation that leaves a test green shows the test does not measure the mutated property. | **Not when the mutated code is unreachable.** `observe_api` read the snapshot path from a constant inside the function, and with no snapshot committed the first refusal always fired — so the second refusal was dead code, and deleting it left the test green. The battery reported "stayed green" and the honest reading was not "the test is weak" but "the branch was never executed". | **The snapshot path became a parameter**, so both refusals are reachable from a test, and both are now mutated. The same run also found that a battery repointed with `sed` through nested quoting silently did not repoint, so a mutation ran against a node ID that no longer existed and pytest's collection error was recorded as RED. Only the paired control caught it. | Two ways for a mutation battery to lie, in one run, on top of D180's third. The rule that survives all three: **a mutation is evidence only when its control is run in the same invocation and comes out green.** A battery without paired controls reports its own faults as findings. | no |
| **D183** | *(ADR 0063, as accepted)* "Deferred services are excluded from the `--wait` set, and — because a project whose API is not up must not be advertised — the edge attachment is deferred with them." | **The deferral worked and the deferring did not.** The filtering that sets `HELD_BACK` lived in a function consumed as `mapfile -t services < <(wanted_services ...)`, which runs it in a **subshell**: the global was set in a child and lost, so the caller saw an empty string, attached the edge immediately, and printed `up and attached`. Measured with a control — a variable assigned inside a function called through process substitution does not survive, while the same function called normally sets it. **Nothing crashed and the right services started.** The only casualty was the one ordering property the ADR exists to deliver, and the source-ordering test could not see it because the order in the source was still correct. | **The filtering moved into the caller**, where its results are in scope; `model_services` now only reads. The rule is structural rather than remembered: `test_no_function_consumed_in_a_subshell_assigns_a_global` finds every function invoked as `<(name ...)` and refuses any assignment to a capitalised global inside it. Confirmed red by putting the assignment back. | Found by deploying, not by reading — the deploy printed `up and attached` where it should have printed `up without postgrest`. Two lessons, and the second is the general one: **a test that asserts an ordering in the source cannot see an ordering broken by scope.** The guard test earned its place immediately: the first body scanner advanced past `${` by two characters, so the `}` of `${ROOT_DIR}` closed the function and it read one line of a body full of assignments. | no |
| **D184** | *(this repository's standing trap, documented since Session 2)* "Ubuntu ships no bare `python`, and `sudo` resets PATH" — which is why every root-reachable script carries a `python_bin()` resolver, and why `test_no_root_reachable_script_invokes_a_bare_python` exists. | **The rule is enforced for shell scripts and says nothing about a shebang.** `bin/render-jwks.py` was written with `#!/usr/bin/env python`, copied from `bin/dev-token.py`, whose shebang has never mattered because it is only ever invoked through its `.sh` wrapper. The deploy invokes `render-jwks.py` **directly by path**, so the shebang was load-bearing for the first time, and the first live run failed with `env: 'python': No such file or directory` — after the data plane had already started. | **`sys.executable`**, not the shebang and not a resolver. The deploy is already running under a working interpreter, so passing it is stricter than resolving one: it cannot select a different Python from the one whose imports were validated at startup. The shebang is corrected to `python3` as well, for anyone who runs the file by hand. | The scan that would have caught this is scoped to `.sh` files, because that is where the trap had always been. A `.py` invoked directly by another `.py` was a new shape in this repository — this is the first command the deploy calls without a shell wrapper — and the rule did not follow it there. | no |
| **D185** | *(every test that exercises `bin/deploy-project.py`)* The module is loaded with `importlib` and its functions called directly, which is how the observers of D181 were tested. | **An import and a script run are different execution modes, and only one of them was ever tried.** The four observers were appended to the file and landed **below** `if __name__ == "__main__": raise SystemExit(main())`. Python executes a module top to bottom, so the guard calls `main()` at the line it appears on and a function defined after it is not yet bound. Under `importlib` the guard never fires — `__name__` is the alias, not `"__main__"` — so all four definitions execute and every test passed. The deploy ran it as a script: `NameError: name 'observe_jwt' is not defined`, **after** the data plane had started, the cluster had been bootstrapped and nine migrations had applied. | **The definitions moved above the guard**, and the rule is structural rather than remembered: `test_no_command_defines_anything_after_its_entry_point` parses every `bin/*.py`, finds the `if __name__ == "__main__"` statement, and refuses any `def` or `class` below it. Confirmed red by appending one. | The third live-path defect in this run and the only one no import-based test could have caught, because the property is about *how the file is run*. Worth pairing with D184: that one was a shebang that only matters when a file is executed directly, this one is a definition order that only matters when it is executed at all. Both were invisible to a suite that imports. And the mechanism was mundane — `cat >>` appends, and the entry point is at the end of the file. | no |
| **D186** | *(§5 Run 9, as written)* "…and only then add edge membership and **publish the two routers**." The REST router's labels are rendered by `runtime_override._rest_labels`, which Run 6 measured against the locked Traefik — a two-matcher rule, an entrypoint, a certresolver, a middleware chain and a service port. | **The router was never published, because the container was invisible.** `infra/edge/traefik.yaml` sets `constraints: Label(apg.traefik.scope, managed)`, and `compose.yaml` gave the `postgrest` service **no labels at all** — the identity labels `edge-probe` carries were never added to it. Traefik therefore never looked at the container, created no router, and answered **404** for `https://<domain>/api/rest`. Measured decisively: from a peer on the same network, `GET http://postgrest:3000/` returns **200** with a complete document, and the service log shows a schema cache of 2 relations and 2 RPCs. The service was correct the whole time. **The deploy's own error message asserted the opposite** — it named D145's unresolvable-pre-request-hook shape, which is a hypothesis compiled into a string and printed as a finding. A second cause sat behind the first: `postgrest` is on **two** networks and carried no `traefik.docker.network`, which leaves Traefik no way to choose and one of the two unreachable. And a third, independent of routing: `PGRST_OPENAPI_SERVER_PROXY_URI` was set nowhere, so the generated document carried `"host": "0.0.0.0:3000"` and `"basePath": "/"` — the container's own bind, published to every consumer, and a document `openapi_normalize` refuses. Run 7's committed fixture was captured *with* that setting, against a configuration the product did not produce. | **Four labels and one environment variable, all in `compose.yaml`.** `apg.traefik.scope`, `apg.project.key`, `apg.environment` and `traefik.docker.network` mirror what `edge-probe` has carried since Session 2; `PGRST_OPENAPI_SERVER_PROXY_URI` is built from the same two values `naming.derive` builds `route_rest` from, so the address the document declares and the address the router serves are one derivation. `test_every_routed_service_carries_the_label_the_edge_filters_on` reads the label **and its value out of the edge's own constraint** and refuses any service the override gives a router without it — the three files involved cannot see each other and this is the only place they meet. Three mutations red, controls green. | The router labels were measured, correct, and attached to nothing. That is a new shape for this project's signature defect: not a value that looked measured and was not, but a value that **was** measured, in isolation, and never checked against the thing that had to consume it. Also worth keeping: the deploy printed a confident, specific, wrong diagnosis. A message that names a divergence number reads as evidence, and this one cost nothing only because it was checked. | no |
| **D187** | *(§5 Run 9, and `runtime_override._rest_labels`)* The REST router publishes `{api.public_base_path}/rest` with a rule Run 6 measured against the locked Traefik: `Path(/api/rest) || PathPrefix(/api/rest/)`, a baseline chain, a body-size middleware, an entrypoint, a certresolver and a service port. | **The router forwarded the published path unchanged, and PostgREST serves at `/`.** With D186's labels in place Traefik created the router and routed the request — the access log names `apg-alpha-dev-rest@docker` and `http://172.23.0.4:3000` — and the answer was still 404. Measured on the deployed service from a peer: `GET /` returns **200 with 2412 bytes**, `GET /api/rest` returns **404 with 96 bytes**, and 96 is exactly the `DownstreamContentSize` Traefik logged for the failing request. So the 404 came from behind the router, not from the edge. There was no `stripPrefix` in the chain, and PostgREST has never heard of `/api/rest`: it serves the document at `/` and its objects at `/notes` and `/rpc/create_note`. | **A per-project `stripPrefix` middleware**, derived in `naming.py` beside the buffering one for the same reason — the prefix is a manifest value, so a middleware in the shared baseline could carry only one project's path. It is **last** in the chain: everything above it matches and reports on the published path, and the upstream is the only thing that wants the path without it. Measured against the locked Traefik v3.7 with a control before it was written: `/api/rest` arrives as **`/`** rather than as an empty path, `/api/rest/` as `/`, `/api/rest/notes` as `/notes`. `test_the_published_prefix_is_removed_before_the_upstream_sees_it` asserts the stripped prefix is the **same interpolation the rule matches on**, so a router cannot match one path and strip another. Two mutations red. | Three 404s in a row with three different causes: no router (D186), a router forwarding an unstripped path (this), and — had the first two been fixed together — a document naming `0.0.0.0:3000`. Each was invisible to the one before it, and each would have been diagnosed wrongly from the status code alone. The general lesson is in the log rather than the fix: Traefik's own 404 carries **no `RouterName` and a 19-byte body**, while a routed 404 carries the router, the service URL and the upstream's body. Those are different failures that are identical from outside, and the access log is the only place they separate. | no |
| **D188** | *(§5 Run 9, and `openapi_normalize.KNOWN_TOP_LEVEL`'s own docstring)* "Every top-level key the locked PostgREST emits, measured. […] A PostgREST upgrade is *expected* to fail here, and the repair is to re-measure and re-approve, not to widen the set." | **The first capture from a real deployment was refused, and there had been no upgrade.** `bin/api-contract.sh --update` exited 5: the served document carried top-level `security` and `securityDefinitions`, which the set does not name. The image is the digest the lock has named since Run 4. The set was measured against a throwaway rig running that same image under a **different configuration**. Measured on the locked image, three arms, JWT secret held constant across all three so it cannot be the cause: `PGRST_OPENAPI_SECURITY_ACTIVE=true` (what `compose.yaml:585` sets) emits both keys; unset emits neither; `false` emits neither and is byte-identical to unset. A prior rig ruled the JWT secret out directly — with and without `PGRST_JWT_SECRET`, security-active unset in both, the documents were identical. `PGRST_OPENAPI_SECURITY_ACTIVE` was set in Run 4 and `test_postgrest_service.py:169` asserts it; nothing ever measured what it does to the document, and it is the only `PGRST_*` entry in its block carrying no comment while every neighbour carries a measured justification. | **ADR 0065.** The two keys join `KNOWN_TOP_LEVEL`, and also a new `REQUIRED_SECURITY_TOP_LEVEL` so their *absence* is a refusal — a capture from a deployment with the setting off would otherwise normalize cleanly into a snapshot describing an API served behind a bearer token as needing none, which is what `REQUIRED_SCHEMES` already exists to prevent for `["http"]`. `security` is asserted equal to `({"JWT": []},)` in code, because a changed requirement is a changed posture rather than a diff to approve; `securityDefinitions` is carried into the snapshot, because it is prose describing how to send the credential and an upstream rewording should produce a reviewable artifact rather than a refusal. The docstring is corrected: a configuration change to the same version is expected to fail here too. Seven mutations red with seven paired controls green. | The set was exactly as strict as it claimed and still recorded the wrong thing, because "measured" named a version and the measurement had also fixed a configuration. **Every constant in this module derived from a throwaway rig is suspect until it has seen a capture from a deployment, and this is the first one that has.** The rig was not wrong to exist — it is how the module was built — but a rig is a second configuration of the product, and nothing in the repository said which one it was. | **yes** |
| **D189** | *(`tests/contract/test_openapi_normalize.py`'s module docstring, as written)* "The fixture is not hand-written. `tests/fixtures/postgrest-openapi.captured.json` is the document the locked PostgREST actually served, captured in Run 7 from a cluster carrying the surface `contracts/postgrest-api-surface.yaml` describes." | **The fixture was a real capture from a cluster this repository does not build.** Re-capturing it for D188 was guarded by a control — reproduce Run 7's rig, and the only difference from the committed file must be the two keys `openapi-security-active` adds. The control failed: sixteen leaf differences, not two. The other fourteen are all `COMMENT ON` text. The committed fixture describes `notes` as `"Notes visible to the caller."` — a string that appears **nowhere in `migrations/`** — where the repository's own migration 0004 produces `"Read surface for notes. security_invoker means the caller's row policy applies…"`. Seven summaries were absent entirely and both RPC body schemas lacked their description. Every path, definition, property, format and `required` array was identical, which is why no test ever noticed: the *shape* was right and only the prose was another cluster's. | **Re-captured from the rendered migrations.** The rig applies `.generated/fixture-alpha-dev/migrations/`, all nine in order, to the locked pgvector image and serves them through the locked PostgREST under the product's `PGRST_*` settings, with Run 7's `openapi-server-proxy-uri` so `host` and `basePath` are unchanged. The provenance now lives in the module docstring in full — what was measured, what the control was, and what the control found — because the old docstring's claim was the thing that made this invisible. | **Nothing compares this fixture to what the migrations produce, and that gap is still open.** It was found only because D188 forced a re-capture and the re-capture had a control; a fixture is compared against itself forever otherwise. The surface contract is checked against the catalog (ADR 0050) and the *snapshot* will be checked against a live document, but the test fixture sits outside both. Recorded rather than fixed: closing it means either committing the rig or generating the fixture during the suite, and both are larger than this run. | no |
| **D190** | *(this run's own first attempt)* A refusal test parametrized over the constant it enforces — `@pytest.mark.parametrize("field", sorted(REQUIRED_SECURITY_TOP_LEVEL))` — reads as the DRY spelling and was written that way. | **Emptying the constant deleted the test instead of failing it.** The mutation that empties `REQUIRED_SECURITY_TOP_LEVEL` — the exact weakening the test exists to catch — produced an empty parameter set, which pytest reports as a skip and an exit code of `0`. The battery recorded the mutation as GREEN. Nothing was broken except the measurement: the rule still held, and the test that proved it had silently stopped existing. | **The fields are spelled as literals in the `parametrize` list**, and the constant gets one test of its own asserting it equals exactly those two names. Emptying it now fails that test; deleting a field from a document still fails the refusal. Both confirmed red, plus a third mutation that requires only one of the two. | The third member of this run's family of batteries that lie (stale bytecode, D180; unreachable code and a `sed` that did not repoint, D182), and the only one where the test was *well-formed and correct* — it simply evaporated under the mutation. The general rule: **a test must not derive its own parameters from the thing it is testing**, because the mutation that empties the source empties the test. Caught only because the mutation stayed green and was expected to go red. | no |
| **D191** | *(`tests/contract/test_api_contract_command.py`'s module docstring, and ADR 0050)* "The one that matters is that **the check cannot approve its own subject**. It is asserted three ways, because 'never writes' is the kind of claim a test passes by not exercising the path that would." | **Two of the three ways were defeated by one function call, and the third had never run.** Committing the snapshot turned the two tests written around its absence red — as their own docstrings predicted — and replacing them exposed the rest. `test_the_check_path_contains_no_writer` sliced the source with `body.split("def command_check(")[1].split("\ndef ")[0]`, so it read one function body and stopped at the next `def`: a helper containing `SNAPSHOT_PATH.write_bytes(...)`, **called from `command_check`'s first line**, left it green. The behavioural half stayed green too, for an unrelated reason — the failure it induced (`--check --project-outputs <absent>`) exits **2 from the shell wrapper before Python runs**, and an unreachable route with no token exits **3**, also from the wrapper. Neither ever reached `command_check`, so neither could observe a writer inside it. The first mutation attempt was itself the D182 shape — a helper defined but never called, green for a reason that is not weakness — and only calling it made the hole visible. | **The scanner walks the call graph.** `_reachable_from` parses the module with `ast`, follows calls transitively from `command_check`, and scans every reachable function; it asserts it reached `load_snapshot` and `fetch_live` and did *not* reach `command_update`, so a walk that silently found nothing cannot pass. The tokens became regexes at the same time and for a discovered reason: widening the scan made `open(` match `urlopen(` inside `fetch_live`, which reads and writes nothing — a false positive whose obvious repair is deleting the token, quietly removing the only check on the plainest writer there is. The behavioural half now supplies a token and an address nothing answers on, so the failure lands at `fetch_live` **after** `load_snapshot` and the surface comparison, and asserts on the Python-level message to prove it got there. Red at one hop and at two, green on the `urlopen` control. | The property was correct, the tests were three, and the coverage was one text slice. What makes this worth a row rather than a fix is *why* it survived: the snapshot's absence supplied the behavioural failure for free, so the test passed for two sessions without its subject ever executing — and the structural test's limit was invisible while the only writer anyone would add was imagined as inline. **A test whose failure condition is supplied by a file that does not exist yet stops testing on the day that file arrives**, and this repository now has two of those in one run (the other is the pair this replaced). | no |
| **D192** | *(migration 0008's own closing comment)* "…`db-pre-request` names a function that did not exist a moment ago, and a PostgREST holding a cache from before it was created answers every request with `function … does not exist`." The migration creates `app_private.postgrest_pre_request()`, migration 0009 replaces it, both grant `EXECUTE` on it by name to exactly the three request roles, and 0008 ends with `NOTIFY pgrst, 'reload schema'`. | **`PGRST_DB_PRE_REQUEST` was set nowhere.** Zero occurrences in `compose.yaml`, zero in `src/agentic_postgres/`. The identity plane was built, granted, commented and reloaded, and nothing ever told PostgREST to call it — so `app.user_id` was never set, `app.current_user_id()` returned NULL, every row policy denied and every write RPC raised `AP401: no request identity for this transaction`. The first live run of Run 8's proofs produced exactly that, four times, and every one of the four failed on its **positive control** rather than its boundary assertion. Measured on the locked image with a control, same nine migrations and same token, one setting different: with it set, `POST /rpc/create_note` returns **200** and the row's `owner_id` is the token's `sub`; unset, the same request returns **401 AP401** and `GET /notes` returns `[]` — reproducing the deployed failure byte for byte. `db-config` is `false`, so an `ALTER ROLE … SET` could not have supplied it either; the environment was the only path and it was empty. | **ADR 0066.** The setting is added, schema-qualified because `app_private` is on no request role's `search_path` (ADR 0052). The rule that matters is structural: `test_every_setting_the_behaviour_rig_configures_is_configured_by_the_product` parses the `PGRST_*` names `tests/contract/test_api_behaviour.py` passes to `docker run` and requires each to be set by the model or exempted with a reason. Two locks, because one can be picked: an exemption silences the tie-test, so `test_nothing_is_exempted_today` asserts the list is empty and makes adding one a second, visible edit. Both demonstrated — M65 silences the first and is refused by the second. Six mutations red, three controls green. **The exemption list is empty, and finding that out was itself the correction**: its first draft exempted seven names on the theory that a throwaway cluster, a constant signing key and a wildcard bind were rig-only. The product sets all seven, with interpolations rather than literals — a difference in *value*, where the rule is about *presence*. | The third instance of one shape in a single run, after ADR 0065 (a constant measured against a rig that did not set `openapi-security-active`) and D189 (a fixture captured from a cluster built without the repository's own `COMMENT ON` statements) — and the first in the reverse direction, where the **rig** had what the product lacked. The rig was not wrong; it was complete. Nothing compared them. What makes this the most expensive of the three is that the offline suite tested the hook's behaviour thoroughly and correctly, on a container configured with a setting the product does not apply, so the coverage read as proof of a plane that had never once run. **A rig is a second configuration of the product, and an untied rig measures a system nobody ships.** | **yes** |
| **D193** | *(§2 of this plan, on Run 8)* "Every one of the sixteen is `live_host` or `external`, so every one is deselected in the offline gate and none has ever executed. Run 9 is the first run that finds out how much of Run 8 is a harness fault rather than a finding." | **Three of the sixteen were harness faults, and each failed in a way that reads as a product defect.** (1) `SEC-ROLE-001` compared `rolsuper::text \|\| ',' \|\| …` to `"f,f,f"`. The `::text` cast of a boolean yields `false`, not `f` — `f`/`t` is psql's *display* form. So the assertion compared `'false,false,false'` to `'f,f,f'` and failed against a role holding none of the three, then reported `"apg_alpha_dev_postgrest_authenticator holds superuser, bypassrls or createrole (false,false,false)"` — a message asserting the opposite of what it had found. (2) `API-CACHE-001` took the 12-character ID `docker ps` returns and passed it to `docker inspect`, which failed outright with `no such object`; below it, the re-inspection compared that prefix to `container["Id"]`, the full 64-character form — **a comparison that can never be true**, so the restart check was a tautology in the failing direction, the D173 shape one field over. (3) `API-LIMIT-001` called the probe RPC immediately after the fixture's `NOTIFY pgrst, 'reload schema'`. The reload is asynchronous, so the request arrived before PostgREST rebuilt its cache and returned `404 Could not find the function api.apg_acceptance_probe(p_seconds) in the schema cache` — indistinguishable from an RPC that was never created. | **(1)** One query per attribute, so the message names which one, plus a control refusing a value that is neither `true` nor `false` — an empty result means the role was not found, which would otherwise read as "attribute absent". **(2)** The ID is resolved to the full `Id` once, with a length assertion, and the comparison below is commented as depending on it. **(3)** The fixture waits, **through the REST plane**. The first attempt polled `pg_proc` and was wrong in the way this project keeps producing: the catalog has the function the instant the `CREATE` commits, so that poll would have waited for nothing while looking like a fix. Only a request can see the cache. The wait is bounded and its failure names `db-channel-enabled`, so a dead channel is a finding rather than a hang. | Run 8 shipped sixteen node IDs that the offline gate deselects, and this is the accounting: **three harness faults, two blocked on an unbuilt service, and one real product defect** (D192) that all sixteen existed to find. The three faults share one cause — code that had never executed — and each was *plausible*: a boolean spelling, an ID length, a notification's timing. None would have survived one run. What is worth carrying is that all three failed **loudly and in the right place**, because every one of these tests asserts its positive control before its boundary; the suite said "the instrument is broken" rather than "the boundary held". That is the difference between a run that costs an afternoon and one that ships a false green. | no |
| **D194** | *(§2 of this plan, and `docs/handoff.md`)* Transport to the host is `git bundle` + `scp`, and every run ends `git fetch /tmp/apg-session5.bundle main && git checkout -B main FETCH_HEAD`. The deploy already hands the checkout back: `_restore_checkout_ownership` exists precisely because a render under `sudo` leaves root-owned files the operator cannot read (D65). | **The deploy took a permission it never gave back, and it was the one the transport needs.** Step 3 calls `installed_release.assert_clean`, which shells out to `git`; git rewrites `.git/index` whenever a stat check makes the cached one stale, and under `sudo` the replacement lands **`-rw------- root:root`**. Observed after a `sudo` pytest run touched enough mtimes to force the rewrite: `.git/index` at `root:root`, and the next unprivileged command died with `fatal: .git/index: index file open failed: Permission denied`. It reads as a corrupt repository. It is a file the deploy chowned. **The failure mode is the serious part**: transport to this host is a bundle and a fetch, so a deploy that breaks `git` for `op` breaks the only way to deliver the deploy that would fix it — recoverable here only because a human with `sudo` was at the terminal. The same run also confirmed `evidence/*.xml` from sessions 2, 3 and 4 sitting at `root:root` for the same reason, and a `--junitxml` written under `sudo` is unreadable to the operator who must commit it. | **`_restore_git_index_ownership`, called immediately after the two git calls in step 3** rather than at the end, so a later failure still leaves the operator able to fetch and retry. It names `index`, `index.lock`, `FETCH_HEAD` and `ORIG_HEAD`, skips what is absent, and is a no-op without `SUDO_UID` — there is no operator to hand anything to outside `sudo`, and guessing an owner is worse than doing nothing. **Tested behaviourally rather than by text slice**, which this module otherwise uses because the deploy needs root: the helper is pure filesystem work gated on an environment variable, so it can be *run*, with `os.chown` recorded rather than performed — an unprivileged chown to the caller's own uid succeeds while proving nothing about which paths were reached (D191's lesson applied one file over). Three mutations red, two controls green. | The deploy has had a handback since Session 2 and it covered the directory it wrote, not the directory it *touched*. `_restore_checkout_ownership`'s own docstring records the same lesson one scope smaller — restoring the rendered directory left the lock file behind (D65) — so this is that defect a third time: the boundary of "what this run made root-owned" is wider than the boundary of "what this run created". **The remaining instance is unfixed and belongs to Run 10**: the host gate's `--junitxml` is still written by a root pytest, and evidence verdicts are computed from it. | no |
| **D195** | *(D193, this table, one run earlier)* "Three of the sixteen were harness faults… none would have survived one run." The three were fixed and the suite re-run against the deployment. | **Two of the three had a second fault behind the first, and one of them was a contradiction between two tests in the same file.** (1) `SEC-ROLE-001`'s boolean comparison was fixed and the test then failed later: it requires 200 or 206 from *every* role the authenticator is a member of, including `anon`. The manifest sets `anonymous_access: deny_data`, and `SEC-ANON-001` — in the same module — asserts `anon` reads nothing. **Both tests described the same request and asserted opposite outcomes.** The live run settled it: `anon` returned `401 {"code":"42501","message":"permission denied for view notes"}`, a PostgreSQL *grant* refusal, which is the boundary `SEC-ANON-001` exists to prove. (2) `API-CACHE-001`'s container ID was resolved to its full 64-character form and `docker inspect` still failed with `no such object`, for a *different* ID than before. The ID was never the problem: `running_containers` is a **session-scoped** fixture that runs one `docker ps` at the start of the run, and Session 4's convergence tests restart the project unit, which replaces the container. The cached listing was stale by the time this test ran. | **(1)** The positive control narrows to `authenticated`, which is the only role designed to read. The loop over memberships now asserts what this test actually needs — that the switch *happened* — by requiring either a served response or a PostgreSQL SQLSTATE in the body, since a JWT-layer rejection never reaches the database at all. **(2)** The listing is taken at the point of use rather than from the session fixture, with the fixture explicitly discarded so nothing reads it by habit. | Both are the same mistake at one remove: **a fix aimed at the symptom the failure named, when the failure had two causes stacked.** The boolean spelling was real and so was the contradiction behind it; the ID length was real and so was the stale listing behind it. What makes this worth its own row rather than an amendment to D193 is the first one's shape — two tests in one file, both P0, both live_host, asserting incompatible things about one request, and neither able to notice because **neither had ever run**. Run 8 wrote them in the same afternoon. The second is a reminder that a session-scoped fixture is a snapshot, and a suite that restarts services invalidates snapshots taken before it. | no |
| **D196** | *(D195, this table, in the same run)* The role-switching proof's loop was settled: it asserts the switch *happened* by requiring a served response or a PostgreSQL SQLSTATE in the body, over every role the authenticator is a member of. `bin/dev-token.sh` mints a token for any of them. | **A third fault was stacked behind the second, and the product was right both times.** The loop minted every membership token the same way, including the documentation role — and migration 0009's pre-request hook refuses a documentation token that carries a subject, with `AP401: the documentation role has no request identity`. The documentation role reads the published schema; it is not a caller, and a `sub` on its token is a caller's claim. `bin/dev-token.sh` says so in its own help text. **The test asked the product for a credential the product is designed to reject, and read the refusal as a role-switch failure.** | The documentation token is minted with no subject, and the acceptance criterion admits the request plane's own refusal beside a grant refusal: both are raised by the database *after* the authenticator has become the role, which is the only thing this loop needs to establish. A JWT-layer rejection never gets that far, and that distinction is what the criterion now turns on. | Three faults stacked in one test — a boolean spelling (D193), a contradiction with `SEC-ANON-001` (D195), and this — and every one of them was the harness, not the product. What is worth carrying is the shape of the third: **the test generalised over a set the product does not treat uniformly.** "Every role the authenticator can become" reads as the thorough choice and quietly includes a role whose whole design is that it carries no identity. A loop over a set is only as correct as the set's members are alike. | no |
| **D197** | *(`schemas/project.schema.json`, since Run 1)* `api.rest.statement_timeouts` is declared with a bounded duration grammar, and `config._validate_statement_timeouts` refuses a role the platform does not derive and a value outside 100 ms – 30 s. The schema's own description reads: "a timeout set on a role nothing created is a setting that never applies and never says so." | **Nothing applied it.** `bin/postgres-bootstrap.py` — the only plane that may `ALTER ROLE` (D102) — carried one hard-coded line, `ALTER ROLE <app_runtime> SET statement_timeout = '30s'`, and nothing else. The manifest's values were validated and then dropped **at the rendering boundary**, because `renderedDatabase` had no field to carry them and the bootstrap reads only the rendered document. Measured on the deployed cluster: `pg_roles.rolconfig` returned **one row**, `app_runtime`, under a manifest declaring `anon: 2s` and `authenticated: 5s`. `anon`, `authenticated` and `api_documentation` had no `rolconfig` at all, and a 30-second request through the REST plane ran until the connection died. | **ADR 0067**, outputs schema version 7. `database.statement_timeouts` is required on both branches, **keyed by the derived role name rather than the manifest's suffix** — `rendering.resolve_statement_timeouts` resolves each through `identity.roles`, so the bootstrap applies a name it was handed rather than deriving one. The platform's own `30s` floor for `app_runtime` moved out of the script and into `rendering.DEFAULT_APP_RUNTIME_STATEMENT_TIMEOUT`, where a manifest entry overrides it. `migrate_v6_to_v7` validates rather than derives, as `documentation_role` does in v5 → v6. **And `--check` now reads `pg_roles.rolconfig` and compares it to the document**, which is the half that was missing: the near side had no test either, and a plane that issues the right SQL against a cluster nobody inspects is the same silence one step later. Fourteen mutations red with paired controls green. | The second instance in one run of **built, declared, validated, and never wired to the thing that would act on it** — D192 was the first, and the two are one defect at two boundaries. Both read as thorough: a grammar, a validator, an error message, a schema description explaining why the setting matters. **Validation proves a manifest is well formed. It never proves anything consumes it.** The general rule ADR 0067 records is where the test has to go: where a setting crosses a plane boundary, the assertion that matters is on the far side, and neither side had one — `resolve_statement_timeouts` shipped with no test, `migrate_v6_to_v7` was exercised only through the chain's happy path, and `build_statements` had never been asserted on at all. Two comments written the same day claimed tests that did not exist. | **yes** |
| **D198** | *(ADR 0067, written in this run)* "`API-LIMIT-001`'s time half becomes measurable for the first time." The manifest's timeouts now reach `pg_roles.rolconfig` through outputs v7, and `bin/postgres-bootstrap.py` applies them — measured on the deployment, `51 statements applied` where there were 49. | **It became measurable and measured false.** With `authenticated` carrying `5s`, a 30-second RPC through the REST plane was not bounded: the request died as `SSLError: record layer failure` with no HTTP status at all, the same symptom as before v7. Measured on the locked `pgvector/pgvector:pg18` image with controls on both arms — **(A)** `pg_db_role_setting` carries `statement_timeout=2s` for the role; **(B, control)** a direct `LOGIN` as that role reports `2s`; **(C)** login as the authenticator then `SET LOCAL ROLE` reports **`statement_timeout=0`**; **(D)** `pg_sleep(5)` on that path completes; **(E, control for D)** the same five seconds after a direct login raises `canceling statement due to statement timeout`; **(F)** an explicit `SET LOCAL statement_timeout` inside the transaction *does* bind. **PostgreSQL processes a role's settings only at login, and `SET LOCAL ROLE` is not a login** — which is exactly how PostgREST reaches every request role. | **Undecided; it needs an ADR and one more measurement, and it is the head of the next run.** Two candidates, and the choice is not obvious. (1) `PGRST_DB_HOISTED_TX_SETTINGS: "statement_timeout"` — PostgREST's own carrier, whose default is `statement_timeout,plan_filter.statement_cost_limit,default_transaction_isolation` and which **`compose.yaml:563` sets to `""`**, deliberately, in Run 1, as one of "the three dangerous defaults". Narrowing it to the one setting the platform declares is the smallest change, and it must be measured against the locked PostgREST image rather than assumed. (2) `app_private.postgrest_pre_request` issues `SET LOCAL statement_timeout` for the role it just switched to — first-party, proven to bind by measurement (F), and it puts a per-role policy value inside a migration, which is a second authority beside the document. Nothing is reconciled inline. | ADR 0067 was correct about its own boundary and wrong about the one after it, which is the sharpest form of this project's standing defect yet: **the far side of one plane is the near side of the next.** The value was declared (Run 1), validated (Run 1), carried into the document (Run 9), applied to the role (Run 9) — and read by nothing, because the consumer authenticates as a different role than it acts as. Every one of those five steps has a test, and all five are green. What none of them asserts is the only thing that matters: **that a request is actually bounded.** The live proof was the first thing to ask, and it took a deployment to ask it. Note also that Run 1 disabled the carrier as a hardening measure and was not wrong to review it — the fault is that eight runs later a feature was built on a mechanism nobody re-checked. | pending |

---

## 2. What Session 5 adds to the acceptance registry

### 2.1 Requirements that already exist and are activated

Each has a `future` placeholder today. Activation deletes the placeholder,
writes real tests, and repoints the registry's `test_nodeids`.

| ID | Claim | Priority | Placeholder to remove |
|---|---|---|---|
| `API-SCHEMA-001` | Only the `api` schema is exposed, matching a committed allowlist | P0 | `tests/integration/test_future_api.py::test_only_the_api_schema_is_exposed` |
| `API-CACHE-001` | A DDL change appears in OpenAPI after the reload | P0 | `…::test_api_migration_reloads_the_schema_cache_and_updates_openapi` |
| `API-LIMIT-001` | Row limits and timeouts are enforced server-side | P0 | `…::test_row_limits_and_timeouts_are_enforced_server_side` |
| `SEC-ANON-001` | The anonymous role reads nothing it is not granted | P0 | `tests/security/test_future_security_boundaries.py::test_anon_cannot_reach_protected_resources` |
| `SEC-PRIV-001` | `app` and `app_private` are unreachable through PostgREST | P0 | `…::test_api_roles_cannot_reach_the_private_schema` |

### 2.2 New requirement IDs

Added only where no placeholder covers the claim. Prefixes follow the frozen
catalog in `docs/product-contract.md` §3.

| ID | Requirement | Priority |
|---|---|---|
| `API-REST-001` | HTTP reads reproduce the database's row-level result exactly: a caller sees its own rows and none of another's, and the same query run directly against the database agrees | P0 |
| `API-RPC-001` | The write surface is exactly the named RPCs; generic table and view writes are refused, ownership is derived rather than accepted, and each call changes at most one row | P0 |
| `API-ERR-001` | The public error contract is stable and discloses no SQL, role name, schema path, hint containing an internal name, or another owner's row | P0 |
| `API-CONTRACT-001` | The live OpenAPI, normalized, equals the committed snapshot, and the snapshot equals the reviewed API-surface allowlist; an unlisted object in `api` fails the gate | P0 |
| `SEC-ROLE-001` | Role switching cannot exceed the authenticator's granted memberships: a token naming an unactivated, privileged or foreign-project role is refused | P0 |
| `SEC-BOOT-001` | The temporary bootstrap issuer signs with a private key no service holds, PostgREST holds verification-only public material, and the deployed document records the issuer as temporary | P0 |
| `SEC-DOCS-001` | The documentation credential never reaches the documentation service, the served bytes carry no credential, and no API token is served to a browser | P0 |
| `SEC-API-001` | From a network that is not the host: the REST route answers over HTTPS with the approved surface, the documentation route refuses without a credential, and nothing else of the API plane is reachable | P0 |
| `DEP-ISO-005` | Two projects have distinct routes, authenticator credentials, issuers, audiences, keys, snapshots and documentation credentials, and neither's token or credential works against the other | P0 |
| `DX-API-001` | The request broker performs an authorized call without a token reaching argv, stdout, shell history, a log or evidence | P0 |

**Two IDs are deliberately not created.** A Session 5 token-validation
requirement would collide in meaning with Session 6's `SEC-JWT-001`, and a
key-separation requirement with `SEC-KEY-001`. Both remain Session 6's. Session 5
proves the negative-token matrix under `SEC-ROLE-001` and `SEC-ANON-001`, and the
key separation of the *temporary* issuer under `SEC-BOOT-001` — which Session 6
retires rather than inherits. This is D47's call, made for the same reason.

**`DEP-ISO-005`'s cross-project clause must have node IDs of its own.** D70 is
the standing lesson: `DEP-ISO-003` claimed "neither project's credential
authenticates against the other" for two runs behind six node IDs, not one of
which presented a credential to anything. The construction that works here is
Project A's token presented to Project B's **own** route, and Project A's
authenticator password presented against Project B's **own** authenticator role
— with each project's own token and credential accepted first as the control.

**`SEC-API-001` and `SEC-DOCS-001` split along the environment boundary, on
purpose.** ADR 0045's rule is that a claim is measured in exactly one
environment, and `claim_mode` computes that from the union of markers across
every node ID of every requirement in the claim. So **a single requirement whose
node IDs straddle host and external breaks any claim containing it.** Session 4
discovered that in Run 10 (D118); Session 5 designs for it in Run 8. Every
requirement above carries proofs in exactly one environment, and
`tests/contract/test_evidence_claims.py` is what fails if that stops being true.

### 2.3 Registry mechanics

`docs/acceptance-matrix.md` and the `product-contract.md` marker block are
**generated** from the registry by `bin/render-acceptance-matrix.py`; the gate
runs `--check` and fails on drift. Never hand-edit either.

`CURRENT_SESSION` moves from `4` to `5` in `src/agentic_postgres/__init__.py`,
and — per **D54**, applied for the fourth time — it moves in the run that deletes
the placeholders and replaces them with real tests, not in Run 1. That constant
drives `APG_ACCEPTANCE_SESSION`, which is what makes "no requirement owned by
session ≤ 5 is still a placeholder" a gate failure rather than a convention.
Moving it early produces a red gate through every intermediate run, which
suspends the only signal that would catch a regression in them. It is also the
ceiling `deploy.sh --through-session` reads, so no session-5 deploy is possible
before it moves (D100).

### 2.4 ADRs to write

Numbering continues from **0047**.

| ADR | Title |
|---|---|
| 0048 | The example domain the migrations shipped, and the one four documents describe |
| 0049 | One scope vocabulary, and it lives in the capability schema |
| 0050 | A reviewed API surface is a generated artifact with an update/check split |
| 0051 | The bootstrap issuer is temporary, asymmetric, and carries its own expiry |
| 0052 | The pre-request function is the one private object a request role may reach |
| 0053 | Outputs version 5: the deployed document carries the public surface and the identity the broker needs |

0048 is mandatory and comes first: nothing downstream can be written until the
surface is decided. 0053 pays for the schema bump, as 0041 paid for v4. 0050 is
the one that replaces a runbook mechanism rather than a runbook sentence.

---

## 3. Environment feasibility

### 3.1 The three execution environments

| Concern | Where it is provable |
|---|---|
| Schema v5 and its migration, the API-surface contract, OpenAPI normalization, PostgREST config statics, route-boundary rules, JWKS structure, command contracts | offline |
| PostgREST's actual config key set, `--ready`, the admin server, JWKS-file syntax, behaviour when the pre-request function is missing; the documentation bundle's self-containedness; Traefik's body-limit middleware | **needs the image**; a locked-digest pull in CI or on the host |
| Role activation, HBA, the pre-request hook, RLS through HTTP, the RPCs, row limits, statement timeouts, pool saturation, the schema-cache reload, snapshot comparison, restart and rotation | host |
| Two-project route, token, key, credential and data isolation | host, two projects |
| **What a stranger can reach: the REST route, the docs 401, and nothing else** | external |

### 3.2 The measurements that must be made before anything is published

Written into `tests/contract/test_image_contracts.py`, not into this document,
for the reason Session 4 gave: one authority, and it is executable.

1. ~~**PostgREST 13.0.4's complete configuration surface**~~ (D127). **Done:**
   forty keys, `client-error-verbosity` absent (D144), three dangerous defaults
   recorded, and the version bumped to 14.16 for a measured reason (D147).
2. ~~**What PostgREST does when `db-pre-request` names a function that does not
   exist**~~ (D139). **Done, and it is the finding of the run:** it starts,
   reports itself **ready**, and refuses every request (D145) — while failing
   closed on the data and open on the schema name (D148). What remains of this
   measurement is the authenticator half: what happens when the role cannot
   authenticate, which needs the roles Run 5 creates.
3. **Whether the documentation bundle loads anything at runtime** (D128). This
   decides the image-versus-build question and is a P0 property in its own right.
4. **Traefik's `buffering` limits against the locked digest** (D143), by sending
   `limit` and `limit + 1` and reading the two answers.
5. **The connection budget, re-computed.** Session 4 queried `max_connections`
   and `superuser_reserved_connections` from the running server rather than
   assuming them (D94). PostgREST adds its own direct pool plus one LISTEN/NOTIFY
   connection plus a startup margin, on top of PgBouncer's backends, the
   migration plane, and the operator's `psql`. Queried again, not extrapolated.
6. **What PostgREST costs in unreclaimable memory**, measured from the
   container's own `memory.stat` under the saturation test, against a host with
   **no swap** already running two clusters and two poolers (§3.3).

Each has a plausible answer that is wrong. Measurement 2 is the one to do first:
it is the only one whose wrong answer is invisible from inside a passing suite.

### 3.3 Capacity

```
total 3814 MiB     swap 0     vCPU 2
two Session 3 clusters + two Session 4 poolers already resident
per cluster, unreclaimable: ~218 MiB under load, ~22 MiB idle
```

Two PostgREST processes and two documentation services must fit in what remains,
under D52's discipline: the **guardrail** is computed over unreclaimable memory
and rendering fails when the declared sum exceeds it; `mem_limit` is set *above*
the guardrail with deliberate cache headroom, because a container limit caps page
cache too. With zero swap the OOM killer is the only backstop, and it can take
Traefik — which drops every project's ingress at once.

### 3.4 What CI can and cannot assert

CI runs `--mode offline`. It can assert every schema, model, config-static,
normalization, allowlist and command-contract claim, and it can compare the
committed snapshot against the committed surface contract. It cannot assert a
role grant, a live OpenAPI document, a 401, or a closed port. The image-contract
tests sit on the boundary and are marked so a runner without Docker reports that
rather than a verdict (ADR 0018).

**ADR 0019's unbuilt follow-up finally has a customer.** "A CI job that starts
the locked image against the rendered configuration and asserts it does not exit"
would have caught the Traefik key that exists in no version. Session 5 renders a
PostgREST configuration whose keys are equally unverifiable offline, and it is
the second session to want that job. It remains an open item unless Run 1's
measurement makes it cheap.

---

## 4. Safety plan for irreversible operations

Session 2's irreversible operations were about losing access to a host;
Session 3's were about losing data; Session 4's were about exposing it. Session 5
is the first session that **publishes an authenticated-looking public route to a
database**, and the whole class of failure is silent from the inside.

### 4.1 The public route

- No REST or documentation router is published until the negative checks pass:
  the protected schemas are not addressable, the anonymous role reads nothing,
  the pre-request hook is resolved and running, and the reviewed snapshot matches.
- **The route is added last.** The service starts on the internal network, is
  verified there, and joins the edge network in a separate step — so a
  misconfigured PostgREST is a project that does not answer rather than a project
  that answers wrongly to the internet.
- Deployed output may not report `ready` before those checks pass, and the
  external half of the evidence is what turns "we did not publish anything else"
  from an inference into a measurement.

### 4.2 The authorization surface

- **A token is not authorization.** Every negative in §8 has a positive control
  in the same test: a suite where every request fails passes every negative test
  completely, and that is the failure mode of a misconfigured authenticator.
- The authenticator receives membership in exactly the roles this session
  activates. `agent_reader`, `agent_writer` and `project_admin` stay `NOLOGIN`
  and ungranted — **and ADR 0046 now applies to them**: the assertion that they
  cannot be reached is a fact with an expiry date, written so that the session
  which activates them makes it fail rather than makes it stale.
- No runtime role gains ownership, DDL, `BYPASSRLS`, or the ability to become
  another role. `SEC-DBX-002`'s behavioural construction (D103) is the model:
  attempt the operation, do not read the catalog bit.

### 4.3 The signing key

- One active private key, held only by root-controlled tooling, never mounted
  into any service, never printed, never an argument.
- Rotation is two-phase and the second phase has a deadline: publish old+new
  verification keys and switch signing; after `max_token_ttl + clock_skew`,
  remove the retiring key. **The deadline is recorded in the deployed document**,
  so a half-completed rotation is visible rather than merely remembered.
- The issuer is marked `temporary` from the first render, and Session 6's gate is
  what retires it.

### 4.4 The transient acceptance object

The timeout, pool-saturation and reload proofs need an object that does not exist
in the released schema. It is created and dropped inside the host deployment lock,
under one reserved name, owned by the object owner, executable only by the
fixture role, with trap-protected removal and a `NOTIFY` on each side. The gate
asserts it is absent from the catalog, from OpenAPI, from the approved contract
and from the published snapshot. **A cleanup failure is a gate failure, not a
warning** — the same rule Session 4 set for the disposable compatibility schema,
whose `apg_client_fixture` name is the precedent for how this one is derived
(D109: a name chosen per run can reach neither `compose.env` nor a required
interpolation).

---

## 5. Build order

Runs are sized so each ends with a green gate and a reviewable commit. The
offline runs come first; nothing public exists until Run 9.

### Run 1 — ADRs, requirement IDs, versions, and the measurements
*Offline, plus a container runtime.* **Done.**

> **The measurements bumped the version, and the reason is not the runbook's.**
> D127 said measure v13.0.4 first and bump only if a measurement requires one.
> One did, and it is not a feature: **the image is distroless** (D147), so a
> healthcheck can be neither a shell nor an HTTP probe, and **`postgrest
> --ready` exists in 14.16 and not in 13.0.4**. On 13.0.4 there is no way to
> probe PostgREST from inside its own container at all. The rest of the 13→14
> delta is *one key* — `jwt-cache-max-lifetime` becomes `jwt-cache-max-entries`
> — and both versions dump exactly 40. `latest` is 16.0 and was not adopted:
> two majors of unmeasured configuration change, for one key this session
> mitigates in the error wrapper.
>
> **`client-error-verbosity` exists in neither** (D144). The runbook sets it in
> its required baseline and asserts it in its gate. It arrives in 16.0. That is
> ADR 0019's defect inside the runbook's own §11.3, and it was found before
> anything was rendered rather than four runs after.
>
> **The finding worth the whole run: `--ready` returned 0 while every request
> returned 404** (D145). A PostgREST whose `db-pre-request` names a function
> that does not exist starts, connects, loads its schema cache, listens, and
> reports itself ready — and refuses every request. This is D101's pooler again
> in the mechanism the runbook designates as the health check.
>
> **And the pre-request hook fails closed on data and open on names** (D148).
> The row does not come out; `app_private` does, in the error message. With no
> `client-error-verbosity` to fall back on, the deliberate error wrapper is the
> only control there is.
>
> **The `PGRST` error shape is inverted** from the runbook's (D146): the body is
> the JSON in `MESSAGE`, the status and headers are the JSON in `DETAIL`.
> Following the runbook yields `PGRST121` and HTTP 500 where a 401 was intended.
>
> Two of my own probes were too weak to mean anything and were re-run.
> `db-config = false` was measured against a table with one row and a role
> setting asking for `db_max_rows = 1`, so the right and wrong answers were the
> same bytes; with two rows and a `db-config = true` control it returns two and
> one respectively, and the suppression is real. And the JWKS-from-a-file check
> proved only that the container did not crash, which is not the same as the
> file being loaded — that becomes a real proof in Run 3, when there is a signed
> token to present.
>
> **`tests/contract/test_image_contracts.py` is where all of it lives**, not
> here. Six tests, forty passing.

**ADR 0048 first, before anything else is written.** The example domain the
contract will state is decided here (D129), and if it converges the code, the
migration that does so is named here and written in Run 5.

ADRs 0049–0053 as drafts of record. The ten new requirement IDs added as `future`
placeholders. `CURRENT_SESSION` stays `4` (D54).

Then the six measurements of §3.2, each written into a contract test rather than
into this document. The PostgREST candidate is either kept or bumped (D127), with
the reason recorded; the documentation delivery is settled (D128); and the
answer to measurement 2 decides Run 4's start ordering (D139).

### Run 2 — Schemas and static contracts
*Offline.* **Done.**

> Outputs **version 5** is entirely on the deployed branch, which is the fact
> that shaped the run. The rendered branch gained one integer: `routes.rest`,
> `routes.docs`, `jwt.issuer` and `jwt.audience` have been derived since Session
> 1 and stay their single derivation. So `migrate_v4_to_v5` takes no argument,
> invents no field, and still refuses everything the expensive steps refuse —
> `test_v5_changes_exactly_one_field` asserts the whole of it as a difference.
>
> **`routes.rest` and `routes.docs` null their URL when unavailable, and
> `health` does not.** The asymmetry is deliberate and has its own test: the
> health path is the same string for every project at every session whether or
> not it answers, so nulling it would delete an address an operator needs; a
> REST URL before Session 5 would name a surface nothing is listening on.
>
> **D106's debt is paid.** `database.observed.instance_uuid` is read by the same
> query the port allocator uses, and `access_broker.resolve_allocation` matches
> on it — the project key stops being a search term and becomes a *check*, with
> a disagreement between the document and the registry refused rather than
> resolved. The old key search survives untouched for documents that predate
> version 5, which is every document on the host until it is redeployed.
>
> **`bounds_table` had to learn to follow `$ref`.** The REST service went into
> `$defs`, and a generator that stopped at the reference would have produced a
> bounds table missing eight fields — and it would have looked complete. That is
> ADR 0007's failure arriving through the documentation generator rather than
> through the schema.
>
> Three new divergences, all from writing the manifest section against what the
> repository actually has: the RPC argument names carry a `p_` prefix and are the
> wire format (D149), the section is optional because two host manifests are
> gitignored operator inputs (D150), and a timeout may name only a role the
> platform derives (D151).
>
> 2081 passed, 216 skipped.

Outputs schema v5 on both branches: deployed `routes.rest` and `routes.docs` as
status-carrying objects, the `api` observation block, the deployed `jwt` public
metadata, and **`database.observed.instance_uuid`** — D106's deferred debt, with
the access broker switched onto it in the same commit. The `v4 → v5` function in
`output_migrations.py`, a committed `tests/fixtures/outputs-v4.json`, and the
standing rule that migration never produces a *deployed* document.

`contracts/postgrest-api-surface.yaml` and its schema: every exposed relation,
column, RPC and method named exactly, no wildcards, no SQL, and the four
forbidden schemas listed. It is project-neutral, because the domain is.

The manifest's `api.rest` section with validation: body limits positive and
bounded and equal, pool size fitting the queried budget, acquisition timeout and
lifetimes bounded, CORS origins exact HTTPS origins with no path, credentials,
wildcard or `null`, statement timeouts under a strict duration grammar.

Route boundaries under the existing relation: the REST prefix is
`{api.public_base_path}/rest` and the documentation prefix is `/docs/rest`, both
checked with `config.paths_overlap`'s segment-wise rule (ADR 0005). `/docs` is
already a **reserved** base path and `routes.docs` is already derived
unconditionally, so nothing new is claimed — but the two prefixes must be proved
distinct and neither a segment-prefix of the other.

### Run 3 — Secrets and the bootstrap issuer
*Offline, then one host materialization plan.* **Done.**

> **D140 is settled as option (b)** — the secret contract admits a **root-plane
> consumer** (ADR 0054): no service, materialized into `_root/` at `0400` owned
> `0:0`, granted to no container. `_root` is a directory name no Compose service
> can have, because the service pattern admits no underscore, so the collision
> is impossible by construction rather than by convention. `plane` is required
> on every consumer, including the ten that predate it.
>
> **And a second ADR came with it.** Bootstrap creates every declared secret as
> `token_hex(32)`, which is right for a password and wrong for a signing key. A
> hex string stored under `bootstrap_jwt_signing_key` would have satisfied the
> contract, the manifest, the file mode and every check here, and failed several
> runs later as a JWKS derived from something that is not a key. So every secret
> declares its `value_kind` (ADR 0055), and the generator refuses one it does
> not understand rather than falling through.
>
> **`postgrest_authenticator_password` moved to Run 4**, and the reason is a
> currently-passing test rather than a change of mind:
> `test_every_consumer_names_a_real_compose_service` requires a compose-plane
> consumer to name a service that exists *now*, and the PostgREST service is Run
> 4's. Declaring the credential first meant either a red gate for one run or
> weakening that test, and the test is right. The credential arrives with its
> consumer, in one commit. The two root-plane secrets have no such constraint —
> they name no service at all.
>
> **The measurements closed Run 1's deferred item and opened two more.** The
> JWKS file *is* genuinely loaded, proved by three distinguishable answers
> against a real cluster rather than by the container not crashing: a token
> signed with the key returns 200, the same token against a different key set
> returns `PGRST301` *"No suitable key was found"*, and a token signed by
> another key returns `PGRST301` *"None of the keys was able to decode the
> JWT"*. RS256 from a file JWKS works; EdDSA was **not** tested, so ADR 0051's
> "revisit if it accepts EdDSA" is still open and still unmeasured.
>
> Then D152, D153 and D154 — the admin server publishes itself to the project
> network by default, `--ready` fails on a healthy container, and PostgREST
> serves happily from a JWKS carrying a private key.
>
> One more thing seen in passing and not yet a divergence: an anonymous request
> for a table the anon role cannot read returned **401** with
> `{"code":"42501","message":"permission denied for table thing"}` — the raw
> PostgreSQL message and the table's name, on the default path, with no
> pre-request function involved. D144 and D148 said the error wrapper was the
> only control there is; this is the third demonstration.

`postgrest_authenticator_password` and `bootstrap_jwt_private_jwk` join
`secrets.required.yaml` with their consumers, uids, gids and modes. Per ADR 0036
the provider bootstrap creates whatever the contract declares, so a project
bootstrapped earlier converges by acquiring them; an existing secret is adopted,
never overwritten.

**The documentation credential's shape is settled here** (D140), with an ADR if
it needs one. `--plan --session 5` is the safe way to see where every file lands
before anything is created — it contacts nothing and writes nothing, which is how
Run 3 of Session 4 found D100 without touching a project.

Key generation: one active RSA private signing key, RFC 7638 thumbprint `kid`,
a verification-only public JWKS that is refused if it carries any private
parameter, distinct material per project, and a two-phase rotation state machine
with a recorded deadline. The private key is mounted nowhere.

**Rotation now reaches more files than it did.** Session 4 left it at five for
`app_runtime_password` and two for `migration_user_password`; Session 5's
authenticator credential adds its own, and the rotation procedure in the operator
guide is written against the number the materialization plan prints, not against
a number counted in prose (D108).

### Run 4 — The PostgREST service and its configuration
*Offline, plus a container runtime for the credential measurements.* **Done.**

> **The service has no entrypoint, no config file and no shell** (D155). That is
> not a simplification, it is the only shape available: the image is distroless,
> so nothing in the container can read a mounted secret and write a connection
> string. Four ways a password could arrive were measured, with a control that
> put it inline to prove the rig was real, and all four work. The one chosen
> keeps it out of the environment, the argument vector, the labels and `docker
> inspect` — all four checked afterwards on a running container, where `.Args`
> is literally empty.
>
> The credential reaches libpq through a **pgpass file with wildcards in all
> four match fields**, written in that shape by the materializer because nothing
> downstream can wrap it (ADR 0056). Naming the host, port, database and role
> would have put four derived identifiers into a secret file — D60's defect at a
> smaller scale, with `fe_sendauth: no password supplied` as the symptom.
>
> **`postgrest --ready` works bare here**, which D153 said it would not. The
> reason is specific to this design and worth stating: the probe reads its own
> configuration, and its own configuration is the service's, because both come
> from the same environment. What it proves is the pool and the schema cache;
> what it cannot prove is the request path, and D156 records that rather than
> letting the check be described as readiness.
>
> **It fails closed, and differently from the pooler.** With an unreadable
> pgpass, PostgREST logs `fe_sendauth: no password supplied` and **exits 1**.
> D101's pooler logged a permission error and went on listening, refusing every
> connection while a port check called it healthy. Measured both ways.
>
> **`PGRST_JWT_SECRET` is deliberately absent**, and `test_no_verification_key_is_configured_yet`
> asserts the absence. It names the verification JWKS, which root tooling derives
> from the bootstrap signing key at deploy time, and a service pointed at a file
> no deploy has written does not start. Until it is set every request is `anon` —
> a token is not rejected, it is not considered — which is the honest state for a
> session with no activated request role. The test goes red on the day the key is
> added, which is the day the run that renders the JWKS has to say so.
>
> `postgrest_authenticator_password` arrives here rather than in Run 3, with its
> consumer, for the reason Run 3 recorded. And `session_profiles` needed no
> change: it has selected `session2..N` since Session 2, so it was already
> cumulative.

The service joins the root `compose.yaml` under a new `session5` profile;
`bin/project-runtime.sh::session_profiles` becomes cumulative through 5. No host
port. Read-only root, tmpfs for the assembled connection string and any rendered
config, all capabilities dropped, `no-new-privileges`, a fixed non-root uid — and
that uid is **declared** rather than inherited from whatever the base image
defaults to, because `secrets.required.yaml`, `user:` and the Dockerfile are
cross-checked and a uid taken from a base image changes when the base image does.

The entrypoint assembles the database URI in tmpfs at `0600` from the mounted
secret file and never logs it. **No password in a Compose environment block, an
argument vector, a label, or `docker inspect`** — the constraint Session 4 met
with a `.pgpass` file rather than an exception (D101), and the same answer works
here.

The static configuration checks: `db-config` exactly false, `db-schemas` exactly
`api`, an empty extra search path, the direct endpoint rather than the pooler,
the authenticator role, the notification channel enabled, aggregates and plans
disabled, minimal client errors, OpenAPI following privileges, an audience, exact
CORS, the proxy URI's scheme host and prefix, no secret literal, no foreign
project's role — **and each of those keys existing in the locked binary**, which
is D127's measurement and not an assumption.

The health check follows D101's rule: it must prove a failure a port check calls
healthy, and it must not be satisfiable before the things it depends on exist.
The start phase follows D139.

### Run 5 — Migrations 0007 and 0008, and role activation
*Offline, plus a cluster and a PostgREST for the measurements.* **Done.**

> **Two migrations, not one** (D157). `0007` converges the domain on ADR 0003 as
> ADR 0048 amends it; `0008` is the pre-request function and the four grants that
> reach it, alone in a diff, because D138's warning is that the dangerous line is
> invisible inside a large one.
>
> **The bounded status is an enum in `api`** (ADR 0058), and both halves of that
> are measured. A CHECK constraint bounding the same column appears **nowhere**
> in the generated document, so the four values ADR 0003 argued about would have
> been invisible to every consumer of the artifact this session ships. And the
> published `format` string is the type's schema-qualified name, so a type in
> `app` would print a forbidden schema's name in a document served to the
> internet.
>
> **The error contract is a SQLSTATE the function chooses** (ADR 0057, D160).
> `PT401` is 401 with a challenge; a bare `RAISE EXCEPTION` is 400. The finding
> that shaped the migration is that **`HINT` and `DETAIL` reach the caller
> verbatim** — 0005's hint about `SET LOCAL app.user_id` was a correct sentence
> written for a psql prompt, and a disclosure the moment the same function
> answers HTTP.
>
> **The migration's dangerous three lines are the derivation.** `app.tasks`
> carries FORCE row-level security and the policies key on a claim that is NULL
> inside a migration, so `UPDATE … SET status` would have matched **zero rows and
> reported success**. FORCE is lifted for exactly one statement, restored, and
> then *read back* out of `pg_class` — because the restoration is a claim like
> any other.
>
> **`db-pre-request` runs after the role switch, inside the request transaction,
> which is read-only on a GET.** Both halves measured, the second the hard way: a
> hook that kept an audit row turned every read of the API into
> `405 cannot execute INSERT in a read-only transaction`.
>
> **D139 is answered in both directions.** An unresolvable hook does *not* fail
> open — the request fails rather than the hook being skipped — and it does not
> stop the service either. It starts, warms its schema cache, passes `--ready`,
> and 404s every request. A green container beside a broken API, which is D145's
> shape and the reason the deploy sequencing still matters.
>
> **A container-to-container connection matches `host all all all
> scram-sha-256`**, not the trust line, with the same two-assertion construction
> Session 4 used for the published port and a control that proves the probe can
> tell them apart.
>
> The documentation role is deferred to Run 7 with its consumer (D158), and the
> authenticator gets no `CONNECTION LIMIT` until the budget is re-computed for
> both roles at once (D161).

`app_private.postgrest_pre_request()`, owned by the object owner, `SET search_path
= pg_catalog, pg_temp`, fully qualified, treating empty `current_setting` as
absent, parsing claims once, and failing closed on malformed JSON. The
documentation role's metadata-visible grants. The request roles' `USAGE` +
`EXECUTE` and nothing else (D138, ADR 0052). The HTTP adaptation of the existing
application error codes (D130). If ADR 0048 converged the domain, the migration
that does it lands here too. Every migration that changes the API ends with
`NOTIFY pgrst, 'reload schema'`.

Role activation is a privileged, idempotent bootstrap action, not a migration:
`LOGIN` and a SCRAM password set over the container-local socket from the mounted
secret, never through argv and never printed; `NOINHERIT` preserved; every
negative attribute preserved; memberships granted with exact options; an explicit
`CONNECTION LIMIT` fitting the queried budget. **Role-level settings are the
bootstrap plane's, not the migration's** — D102 measured that `ALTER ROLE … SET`
on another role needs an authority the migration plane deliberately does not hold.

Session 4 measured that a published loopback connection matches
`host all all all scram-sha-256` rather than the trust line, and the cluster runs
the image's default HBA with no rendered `pg_hba.conf` (D90). PostgREST connects
over the project-internal Docker network, which is the same NAT path. **Whether
that still holds for a container-to-container connection is measured, not
inherited** — it is a different source address from a different bridge, and the
consequence of being wrong is unauthenticated superuser access from inside the
project network.

### Run 6 — The edge
*Offline, plus a Traefik and an upstream for the measurements.* **Done.**

> Four claims in this run were documentation claims first, which is the class
> ADR 0019 exists for. All four were measured against the locked Traefik, and
> two of them were wrong.
>
> **`PathPrefix` is not segment-aware** (D162, ADR 0059). A router ruled
> ``PathPrefix(`/api/rest`)`` answers `/api/restaurant`. Every prefix route is
> now ``Path(`X`) || PathPrefix(`X/`)``, asserted offline as a shape and live as
> an outcome — with a control router ruled the naive way, which must over-match,
> because otherwise the negative assertions pass against a broken rule.
>
> **A `usersFile` can be a label** (D163). The plan says it cannot. The
> middleware goes into the file provider anyway, for a different and better
> reason: defined there it outlives the container that uses it.
>
> **The response policy reaches a 413 and not an unrouted 404** (D164). The
> first is the case that matters — a body-limit refusal never reaches a service,
> so a policy attached beside the upstream would miss it. The second is a
> boundary rather than a bug, and it is recorded rather than assumed away.
>
> **`buffering.maxRequestBodyBytes` is inclusive** (D143, adopted as written):
> the limit reaches the upstream with every byte intact, one more is 413.
> `memRequestBodyBytes` equals the maximum, so no request body is ever written
> to the edge's filesystem.
>
> **The credential hash cannot be produced on the host** (D165). `crypt` was
> removed in Python 3.13; the locked 3.12 image has `METHOD_BLOWFISH`. And
> Traefik refuses every non-bcrypt format with a 401 on a *correct* password, so
> the format is checked where the file is written.
>
> The documentation **router** is not here: a router's labels live on the
> container that serves it, and the documentation service arrives in Run 9. What
> is here is the middleware and the credential file it names, so Run 9 adds a
> reference rather than a mechanism.

The REST router with an exact prefix boundary, the baseline middleware chain, the
buffering middleware whose limits are measured rather than configured (D143), and
a response-header middleware setting `Cache-Control: no-store` and removing any
upstream `Server` header on **every** response — including the ones that never
reach a database transaction. The documentation router with its own boundary, its
own credential middleware, and `removeHeader: true`.

Router labels reach the container through the root-owned runtime override, as
they have since ADR 0013 — a router label's *key* contains the router name and
Compose cannot interpolate inside a key. A `usersFile` cannot be a label at all,
so the credential middleware is the **first per-project artifact this repository
writes into the Traefik file provider**. It is staged, validated and atomically
published; a failed update leaves the previous valid middleware active.

Access-log policy per D141, with the query-parameter clause struck and the
sentinel proof asserting the outcome.

### Run 7 — The contract tooling
*Offline.* **Done.**

> **Landed.** `src/agentic_postgres/openapi_normalize.py`, `bin/api-contract.sh`
> and `bin/api-contract.py`, with the measurements they were written from and
> three divergence rows.
>
> Everything about the served document was measured against the locked
> PostgREST 14.16 before a line of the normalizer existed, and **three of the
> claims that shaped it were wrong**:
>
> - **Two of ADR 0050's four substituted fields do not exist** (D166). The
>   document is Swagger 2.0 — no `servers` block — and `info.title` is the
>   constant `"PostgREST API"`. Exactly three top-level fields carry a project's
>   identity, and only two of them are substituted: `schemes` is *asserted*
>   against `["https"]`, because a capture taken off the container carries
>   `["http"]` and replacing it unread would write a snapshot claiming a
>   transport the captured service never offered.
> - **Sorting is not what makes the document deterministic** (D167). Two
>   clusters built in opposite orders produced identical key order, and three
>   fetches were byte-identical. The order is a hash artifact — `/tasks`
>   precedes `/notes` — so sorting buys a reviewable diff rather than a stable
>   one. The rule that matters is the one beside it: **map keys are sorted and
>   array order is never touched**, because `enum` carries `enumsortorder` and
>   `required` carries argument order.
> - **`follow-privileges` filters the path, not the methods on it** (D168,
>   ADR 0060). A role holding `SELECT` and nothing else — read back out of
>   `information_schema.role_table_grants` — is served a document advertising
>   `delete`, `patch` and `post`, all three of which return **403**; and `HEAD`
>   is served and not advertised. So the snapshot↔contract comparison is at the
>   level of objects, and `methods:` is enforced against the catalog where it is
>   true. A method-for-method comparison could only ever have failed, and its
>   repair would have been to widen the reviewed read-only surface.
>
> Seven mutations of the normalizer were each confirmed to turn the suite red,
> including the two that matter most: sorting arrays as well as maps, and
> substituting without validating first.
>
> `contracts/postgrest-openapi.canonical.json` deliberately does not exist yet —
> it is captured from a deployed release in Run 9 — so `--check` exits **5**
> naming that run, and a test asserts both the absence and the exit code.
>
> **The documentation role landed second**, with outputs schema **v6** and
> migration `0009-documentation-role.sql`. Two more findings:
>
> - **The refusal has one spelling that parses** (D169). `current_user` is a
>   construct, not a function, so `pg_catalog.current_user` is migration 0008's
>   `nullif` failure in a second place. `current_user::text = <literal>` is what
>   works, measured both ways. Everything else D158 predicted held exactly: a
>   bare documentation token fetches the document (200) and sees the write RPC
>   in it, one carrying a subject is 401, and a bare one calling that RPC is 403
>   from the row policy. The table held only the seed row afterwards.
> - **Migration 0009 replaced the hook, and seven tests kept passing about the
>   body it replaced** (D170). They read 0008 by name. Nothing edited them and
>   nothing in a diff of 0009 would have shown it. The constant is now a
>   derivation off the manifest, with a test asserting which migration it
>   currently resolves to.
>
> Eight more mutations confirmed red, including dropping the refusal clause,
> qualifying `current_user`, granting the role `INSERT` on a view, and pointing
> the two placeholders at two sources.
>
> **The three operator commands landed third.** `bin/dev-token.sh` mints and
> never emits; `bin/api.sh` enumerates five operations; `bin/docs.sh` two, and
> neither of them authenticates. Two more findings:
>
> - **`env VAR=value command` is not "through the environment"** (D171). It puts
>   the value in `env`'s own argument vector, where `ps` shows it to every user
>   on the host. `os.execvpe` is the spelling that does what the plan sentence
>   means, and the test asserts the spelling because both run the child with the
>   variable set. Signing is `openssl dgst -sha256 -sign`, measured end to end:
>   200 against the derived JWKS, **401 `PGRST301`** for a wrong key, **401
>   `PGRST303`** for an expired token, and `PGRST_JWT_SECRET=@/path` loads a key
>   set from a mounted file.
> - **A source scan looking for `print(` on a line missed a `print()` spread
>   over four** (D172). The mutation planting the token inside an existing
>   multi-line call left the suite green while the command printed the
>   credential. The scan now parses; a guard test plants the shape that defeated
>   the first version.
>
> Eight more mutations confirmed red, one of which is D172 — it was the mutation
> that found it.
>
> **What Run 7 has not proved, and Run 9 will.** `--update`'s live path,
> `bin/api.sh` and `bin/docs.sh` against a real deployment, and migration 0009
> applied through `bin/migrate.sh` rather than as SQL against a probe cluster.
> Everything above is offline or measured against a throwaway rig, which is what
> this run's scope is — but "measured against a rig" is not "ran in the product",
> and no evidence claim should say otherwise before Run 9.

`bin/api-contract.sh` with the `--update`/`--check` split ADR 0050 sets:
privileged capture streams a secret-free candidate and accepts no arbitrary
output path; normalization is deterministic and strict, with duplicate-key
rejection, sorted map keys, and sentinel substitution for exactly the
project-specific fields; `check` never rewrites. `src/agentic_postgres/
openapi_normalize.py` holds the logic, because a comparator that lives in shell
cannot be unit-tested against a drifted document.

`bin/api.sh`, `bin/dev-token.sh` and `bin/docs.sh` with enumerated operations
only — no arbitrary URL, method, role, subject, header, path or curl option from
the caller. Tokens reach a child through an already-open descriptor or a tightly
scoped environment, never through argv or stdout. D105's rule stands and is
stricter than the specification: there is no flag that prints a credential,
because a flag that prints one is a credential in a scrollback buffer, a shell
history, a screen share and a support ticket.

Every new command joins `SHELL_COMMANDS` in `tests/contract/test_cli_contract.py`
(D97) — which is what subjects it to the exit-code convention, the `--help`
contract, the works-from-any-directory rule, and the `100755` index mode. **Writing
through the `\\wsl$` share strips the executable bit**, and the index mode is what
the contract checks; it has cost time in every session so far.

### Run 8 — Activation
*Offline. The run D100 exists for.* **Done.**

> **All fifteen placeholders deleted, fifteen requirements repointed, and
> `CURRENT_SESSION` moved from 4 to 5, in one commit.** The exact fifteen the
> registry suite names under `APG_ACCEPTANCE_SESSION=5`, run before anything was
> written: `API-SCHEMA-001`, `API-CACHE-001`, `API-LIMIT-001`, `API-REST-001`,
> `API-RPC-001`, `API-ERR-001`, `API-CONTRACT-001`, `SEC-ANON-001`,
> `SEC-PRIV-001`, `SEC-ROLE-001`, `SEC-BOOT-001`, `SEC-DOCS-001`, `SEC-API-001`,
> `DEP-ISO-005`, `DX-API-001`. Sixteen node IDs, because `DEP-ISO-005`'s
> cross-project clause has its own. Seven claims added, none added to an existing
> one (D119): eighteen in the Session 5 document, fifteen host and three external.
>
> **The environment split was measured with both controls before it was designed
> around, and the plan's sentence turned out wider than the mechanism (D174).** A
> requirement whose node IDs straddle is refused, as §2.2 says. A requirement
> moved *wholesale* to the wrong environment is not — `SEC-API-001` repointed at a
> host test fails nothing once the matrix is regenerated. Recorded rather than
> fixed, because deriving "which environment does this requirement belong to"
> would be a second authority beside the markers.
>
> **Two green tests that measured nothing, both found by mutating.** D173: there
> are two `declared_objects` in this repository with two spellings, and written
> the obvious way the comparison is a tautology in one direction and impossible in
> the other. D175: `DEP-ISO-005`'s dropped proof is caught only by generated-file
> drift, which passes again the moment the matrix is regenerated — so D70's
> obligation is a review rule and now says so.
>
> **§4.4's transient object exists** as `rendering.ACCEPTANCE_PROBE_FUNCTION`, a
> constant for D109's reason. Its grant could not be "the fixture role" (D176):
> `follow-privileges` means the role that must hold `EXECUTE` for the reload proof
> is the documentation role, and the role that needs it for the limit proofs is
> `authenticated`. Both uses hold `project_lock` across creation and teardown, and
> three tests assert the name is absent afterwards — two on the host, one offline
> against the reviewed contract, which is the only half with a signal before Run 9.
>
> **Nothing here has been seen to pass.** Every one of the sixteen is deselected
> in an offline gate; Run 9 is the first run that executes any of it, and the
> first that finds out how much of Run 8 is a harness fault rather than a finding.
>
> **And then a session-5 render was run offline before handing Run 9 to a human,
> which found D177 and ADR 0061.** The documentation path was derived twice and
> the two disagreed: `routes.docs` named the reserved `/docs` root while the only
> path Run 6 measured was `/docs/rest`. `bin/docs.sh check` would have answered
> **404 rather than 401** against the router Run 9 is about to publish, and two of
> the sixteen proofs above would have failed for a reason that is not a boundary.
> One derivation now, in `naming`, which is what ADR 0002 already said.

**All fifteen placeholders deleted, fifteen requirements repointed, and
`CURRENT_SESSION` moved from 4 to 5, in one commit.** The constant and the
implementations it vouches for move together, or the constant means nothing. That
is D54's rule and this is the fourth time it has decided a build order.

Every test here is deselected in an offline gate, so **every one states in its own
docstring what would have to break for it to go red**. Where a property could be
satisfied by an absence, both halves are asserted: the anonymous role is refused
*and* an authenticated one succeeds; the foreign token is refused only after the
project's own is accepted; the row ceiling holds *and* a request under it returns
rows; the private schema is unreachable *and* the api surface answers, because a
PostgREST that refuses everything passes every negative test completely.

**The environment split is enforced here, not discovered in Run 10.** No
requirement's node IDs straddle host and external (§2.2). `claim_mode` is what
would refuse it, and Session 4 found that out at the end.

`DEP-ISO-005`'s cross-project clause gains node IDs of its own here, which the
registry records as an activation obligation rather than leaving to memory.

### Run 9 — The host sequence
*Host, and off-host for the negative proof. The first run that changes what is
reachable.* **In progress.**

> **The first live deploy failed at step 1 and never touched the host** (D178,
> ADR 0062). `${POSTGREST_CORS_ORIGINS:?required}` refuses an empty value as
> well as an unset one, and a manifest with no `api.rest` renders exactly that —
> so a project that legitimately declines a REST service could not render at
> all. Fixed to `${VAR?required}`, which is now the only variable in the model
> spelled that way, under an ADR because the spelling rule it collided with is a
> Session 1 contract test protecting `DEP-ISO-002`.
>
> **Two problems, one symptom.** `project.alpha.yaml` also declared no
> `api.rest`, which is an operator-input gap: a Session 5 project needs the
> block or it publishes no REST route and none of Run 8's sixteen proofs can
> run. Fixing only the manifest would have left the code broken for every
> project that declines a REST service; fixing only the code would have left a
> deployment with nothing to measure.
>
> **The gap that let it reach a live deploy is worth more than the defect.**
> `tests/contract/test_compose_contract.py` skips its whole module unless
> `.generated/fixture-alpha-dev` has been rendered, so the assertion that would
> have caught the spelling was not running in the gate. Run 10 should revisit
> that skip.

> **Project A is deployed through session 5.** PostgREST healthy, all nine
> migrations applied through `bin/migrate.sh` — 0009 for the first time, against
> a real cluster rather than a probe — and the fourteenth role created.
>
> **Three things nobody had noticed were unbuilt, found by deploying.** The
> deploy hard-coded `routes`, `api` and `jwt` to `unavailable` with a comment
> naming this run as the one that owed the observation (D181); PostgREST
> validated no tokens at all, because `PGRST_JWT_SECRET` was deliberately absent
> until the run that renders the JWKS (part 2); and a service that authenticates
> as a project role was started before the bootstrap plane activates that role,
> which deadlocks a greenfield deploy (ADR 0063).
>
> **What is built:** the two-phase start, with the edge attached last — which is
> §4.1's rule and closes D177; the verification JWKS and its mount; and the
> observation of `jwt`, `api` and `routes.rest`.
>
> **What is not, and why each is a run rather than a step.** `routes.docs` cannot
> become ready: `services/docs/` holds a `.gitkeep`, the model declares no such
> service, and **D128's decision is recorded as settled in this plan while no ADR
> records it and nothing implements it.** `SEC-DOCS-001` and the documentation
> half of `SEC-API-001` are blocked behind that. And `api.status` stays
> `unavailable` until a reviewed snapshot exists, so the capture-review-commit-
> redeploy sequence is still ahead — which is D112's two-deploy shape and §9's
> seventh risk, arriving as predicted.
>
> **Nothing here has been run against the host.** Parts 1–3 change what the
> *next* deploy does. The deployment that exists was produced by the code before
> them, with one manual `postgres-bootstrap.sh --apply` standing in for the
> ordering fix.

> **The REST plane answers from outside.** The deploy at `8c46a87` published the
> router, and the route was measured off-host with no credential:
>
> | path | status | bytes | what answered |
> |---|---|---|---|
> | `/` | 404 | 19 | Traefik's own — nothing publishes the root |
> | `/api/rest` | 200 | 2412 | PostgREST's document |
> | `/api/rest/` | 200 | 2412 | the trailing-slash form of the same rule |
> | `/api/rest/notes` | 401 | 88 | PostgREST: `permission denied for view notes` |
> | `/docs/rest` | 404 | 19 | Traefik's own — no documentation service exists |
>
> The 401 is the one that carries the information. An 88-byte PostgREST error
> body means the request matched the router, passed the chain, was stripped and
> was answered by the upstream — a routed refusal rather than an edge miss, which
> is the shape `SEC-ANON-001` is written against. The two 19-byte 404s are
> Traefik's own and carry no `RouterName`; that distinction is D187's lesson and
> it is what makes the `/docs/rest` line readable as "no service" rather than
> "wrong path".
>
> **The first capture from a deployment was refused, and it was right to be**
> (D188, ADR 0065). `bin/api-contract.sh --update` exited 5: the served document
> carries top-level `security` and `securityDefinitions`, which
> `openapi_normalize.KNOWN_TOP_LEVEL` does not name. There was no upgrade — the
> set had been measured against a rig that did not set
> `openapi-security-active`, while the product has set it since Run 4. Widening
> the set was not the whole repair: both keys are now *required*, because a
> capture from a deployment that lost the setting would otherwise produce a
> snapshot describing an API served behind a bearer token as needing none.
>
> **Re-capturing the test fixture found a second drift nothing was watching**
> (D189). The control on the re-capture was that the only difference from the
> committed file should be those two keys. It was sixteen. The other fourteen are
> `COMMENT ON` text: the committed fixture described `notes` as `"Notes visible
> to the caller."`, a string that appears nowhere in `migrations/`. Every path,
> definition, property, format and `required` array was identical, which is why
> no test noticed — the shape was right and only the prose belonged to another
> cluster. The fixture is re-captured from the rendered migrations; **nothing
> still compares it to what those migrations produce**, and that gap is recorded
> rather than closed.
>
> **A third battery lie, and a new one** (D190). The refusal test for the two
> required keys was first written parametrized over the constant it enforces.
> Emptying the constant produced an empty parameter set, which pytest skips and
> reports as success — so the mutation that removes the rule *deleted the test*
> instead of failing it. The fields are now literals and the constant has a test
> of its own. A test must not derive its own parameters from the thing it is
> testing.
>
> **Still ahead in this run:** the capture, now that it can succeed; the review
> and the commit of the snapshot; the redeploy that makes `api.status` ready;
> then Project B and the off-host scan.

Deploy Project A through session 5 with no public router. Verify internally:
readiness, the pre-request hook resolved, the anonymous refusal, the private
schema unreachable, RLS through the internal address matching the database.
Capture the OpenAPI candidate, normalize it both ways, review the semantic diff,
and commit the approved snapshot as the unprivileged source owner. Redeploy at
that commit — the second deploy, which is the shape Session 4 already has (D112)
— and only then add edge membership and publish the two routers.

Then Project B, and the isolation proofs. Then the off-host scan, **before
anything reports ready**: 443 and 80 open as the positive control, the REST route
answering, the documentation route refusing, and nothing else of the API plane
reachable. A negative from an instrument that can see nothing is not a boundary.

**Both routers are published at the paths `outputs.json` names, and at no other
path** (ADR 0061, D177). The documentation router's rule is the segment-safe pair
Run 6 measured — `Path(/docs/rest) || PathPrefix(/docs/rest/)`, never a bare
`PathPrefix` (ADR 0059, D162) — and the path itself comes from the deployed
document rather than from a constant this run chooses. Run 8 found the two
disagreeing and closed it; if a router here is built from anything but
`routes.rest.url` and `routes.docs.url`, that is the same defect returning.

### Run 10 — Restart, rotation, documentation, and the gate
*Host, one maintenance window, then all three environments.*

The restart matrix extends `API-CONTRACT-001` and `DBX-PORT-001`'s precedent
(D120): PostgREST restart, documentation restart, cluster restart with PostgREST
configured, project unit restart. After each, the routes still answer, the
snapshot still matches, the reload listener still works, and no new listener
appeared — with 443 asserted **present** in the same output.

Rotation, in one window: the authenticator password through a new immutable
generation with a coordinated role update; both bootstrap-key phases; the
documentation credential. Each is a declared proof admitted by a flag and written
to refuse a false declaration, per D121 — a claim over a rotation would be
permanently, trivially green after the first window.

`bin/session-05-check.sh` in the shape D132 settles, in three modes.
Documentation: `docs/api-surface.md`, `docs/api-operations.md`,
`docs/session-05-operator-guide.md` — flat in `docs/`, in `REQUIRED_PATHS`, linked
from `README.md` and `docs/handoff.md`, recording **what was measured** rather
than what was intended.

Both evidence halves, then the merge.

---

## 6. The API surface

The runbook's §4.2 and §4.11 survive in substance, restated against the real
identifiers. **ADR 0048 decided it and Run 2 wrote it down**: the table below is
now a summary of `contracts/postgrest-api-surface.yaml`, which is the authority,
and D129 is closed.

| Surface | Methods | Authority |
|---|---|---|
| `api.notes` | `GET`, `HEAD` | security-invoker view; the caller's row policy applies |
| `api.tasks` | `GET`, `HEAD` | security-invoker view; the caller's row policy applies |
| `api.create_note(p_title, p_content)` | `POST` | `SECURITY DEFINER`, safe only because the base tables carry FORCE RLS (D58) |
| `api.update_task_status(p_task_id, p_expected_status, p_new_status)` | `POST` | ADR 0003's operation 4, which the shipped migrations never had; created in Run 5 |

`api.create_task` is **retired** in Run 5 rather than published. Argument names
carry the `p_` prefix the functions actually have, because PostgREST maps JSON
body keys onto parameter names — see D149.

No table-style `POST`/`PATCH`/`PUT`/`DELETE` is granted on the views. Tests use
actual authorization results rather than `OPTIONS`, because view method discovery
can reflect updatability independently of role grants.

**PostgreSQL is the authorization system, and PostgREST is transport.** The
request identity is the transaction-local claim `app.user_id` that Session 3
established (ADR 0029) — trusted, not authenticated, which is exactly why the
pre-request function's job is to refuse to set it from anything but a validated
token. Every read passes through a security-invoker view over a FORCE-RLS table;
every write derives ownership rather than accepting it.

**PostgREST connects directly, not through the pooler.** It owns a bounded pool,
needs prepared statements and needs the `LISTEN`/`NOTIFY` channel for the schema
cache; the pooled endpoint stays dedicated to ordinary application clients. The
direct pool joins the queried connection budget.

Three authorities, in order, and OpenAPI is not one of them:

1. `contracts/postgrest-api-surface.yaml` — the reviewed intent.
2. The PostgreSQL catalog and its ACLs — what is actually there.
3. The normalized OpenAPI snapshot — the generated client contract.
4. The documentation page — presentation only.

An object present in `api` and absent from (1) is a release failure even when its
grants keep it out of OpenAPI, because the next grant change would publish it.

---

## 7. Evidence and claims

Session 5 adds claims, not a format (D133). Each names registry requirements and
inherits every rule ADR 0025 set: a proof absent from the artifact is `not_run`
rather than `passed`, a skip is not a pass, and each claim is measured in exactly
one environment.

| Claim | Requirements | Mode |
|---|---|---|
| `rest_surface` | `API-SCHEMA-001`, `API-REST-001`, `API-RPC-001`, `API-ERR-001`, `API-LIMIT-001` | host |
| `api_contract` | `API-CONTRACT-001`, `API-CACHE-001` | host |
| `api_authorization` | `SEC-ANON-001`, `SEC-PRIV-001`, `SEC-ROLE-001`, `SEC-DOCS-001` | host |
| `bootstrap_identity` | `SEC-BOOT-001` | host |
| `api_isolation` | `DEP-ISO-005` | host |
| `api_tooling` | `DX-API-001` | host |
| `public_api_boundary` | `SEC-API-001` | external |

Seven new claims; eighteen in the Session 5 document, because claims are
cumulative and Session 5 does not stop making Sessions 2–4's promises.

**Nothing is added to an existing claim, and that is a decision rather than an
oversight.** `claim_session` is the maximum of a claim's requirements' sessions
(ADR 0039), so giving `connection_tooling` a Session 5 requirement would move it
to Session 5 and **withdraw it from Session 4's evidence** — and the jq
expression `docs/session-04-operator-guide.md` documents would fail against
freshly written Session 4 evidence with the product's behaviour unchanged. That
is D119, and it applies here to `connection_tooling`, `database_isolation` and
`transport_boundary` alike. Extending a claim is a decision about which sessions'
evidence records it: right when the guarantee genuinely grew, wrong when a new
requirement merely neighbours an old one.

**Session 5's evidence has two halves and cannot be written from one.**
`public_api_boundary` is measured off-host, so the writer refuses a session
document silent about it. Run both modes, then merge — the same shape Session 4
established, and the reason `--external-input` stopped being optional (D78).

---

## 8. Security invariant matrix

| Invariant | Positive proof | Negative proof |
|---|---|---|
| Only `api` is exposed | The approved reads and RPCs succeed | Protected schema, profile and path requests fail without disclosing contents |
| PostgreSQL remains the authorization system | HTTP results equal direct-database results under the same claim | No proxy-side or application-side bypass exists |
| The authenticator is least privileged | It becomes exactly the activated group roles | It cannot become owner, migration, runtime, service or superuser roles |
| Anonymous access reads nothing | The anonymous role has a deterministic identity and a stable refusal | An empty successful response is not accepted as a refusal |
| The private schema stays private | The one pre-request function runs through its exact grant | Every other `app_private` object is refused **by attempting it**, not by reading a catalog bit |
| Writes are narrow | The named RPCs succeed and derive ownership | Generic view and table writes fail; a caller-supplied owner is ignored or refused |
| The contract is reviewed | The live normalized OpenAPI equals the committed snapshot | An unlisted object in `api`, or a drifted snapshot, fails the gate and cannot be approved by the gate |
| Reload is live | A DDL change appears in OpenAPI | The container ID and process start time are unchanged across it |
| Limits are enforced | Bounded requests succeed | Over-row, over-body, over-time and pool-saturated requests fail predictably; the transient object is gone afterwards |
| Key material is separated | Tokens verify against the public JWKS | The private key is absent from every service mount, argv, log, output and evidence file |
| Documentation is protected | The page loads through the broker | It refuses without a credential, the credential never reaches the service, and the served bytes carry none |
| Nothing else is reachable | 443 answers from off-host | The admin surface, the direct service address and every non-approved path are unreachable from off-host |
| Projects are isolated | Each project's token opens its own route | Cross-project tokens, credentials, keys and hostnames all fail |

---

## 9. Risks and stop conditions

**Stop before mutating** when: the Session 4 gate is not green; the project
identity in deployed state does not match the cluster's sentinel; the installed
release differs from the one the deployment records; the migration ledger
disagrees with `released.lock.json`; the API-surface contract and the catalog
disagree; the committed snapshot is absent; a required consumer file is missing
from the active secret generation; the runtime roles hold unexpected privileges;
or the checkout is dirty where a release requires a clean tree.

**The specific risks of this session**, in the order they are likely to bite:

1. **PostgREST resolves a missing pre-request function by ignoring it** (D139).
   Measured in Run 1, because every other check passes either way.
2. **A locked binary does not have the keys the configuration sets** (D127).
   Measured in Run 1. A key the parser drops is a boundary that is not there.
3. **The example domain is settled late** (D129). Every artifact this session
   produces is derived from it.
4. **The pre-request grant widens more than it looks like** (D138). The proof is
   behavioural or it is not a proof.
5. **The documentation credential has nowhere legal to live** (D140), and the
   convenient answer materializes it into the one container that must not have it.
6. **A configuration key is adopted from documentation** (D141, D143). Twice
   already in this repository, once taking the edge plane down.
7. **The evidence names the deployed release rather than the reviewed one.** True
   by design; if Session 5 wants them equal, the last deploy happens after the
   last code commit, deliberately — and the snapshot approval makes that a
   two-commit sequence whether or not anyone plans for it.

---

## 10. Open items carried in

- **`requirements-dev.in` pins nothing**, so `bin/lock-dev-deps.sh --check`
  re-resolves against PyPI and fails the day any dependency ships. It has now
  bitten in three sessions, most recently in the middle of Session 4's final gate.
- **ADR 0019's follow-up CI job is unbuilt**, and Session 5 is the second session
  to want it (§3.4).
- **The Infisical control-plane identity still holds organisation admin**, and a
  `.save` copy of that credential is still on the host.
- **Secret generations accumulate with no pruning.** Session 5 adds two or three
  more secrets per project. ADR 0038 records the constraint pruning must respect:
  a deployed document names the generation it verified, and removing it without
  saying so turns an audit trail into a dangling identifier.
- **`bin/restore-test.sh` is the last `FUTURE_STUB`**, owned by Session 10.
- **`PYTHON_RUNTIME_IMAGE` selects a rolling minor tag** (D99). A test compares
  the image's Python against `PYTHON_VERSION`, so drift is loud; tightening the
  tag to `3.12.13-slim` remains a deliberate candidate change with a re-lock
  behind it.
- **`docs/capability-plan.md` and `docs/source-specification.md` describe an API
  the database does not have** (D129). Whichever way ADR 0048 goes, one of them
  is edited in this session.

---

## 11. Session 6 handoff

Session 6 receives a healthy PostgREST per project connected through a dedicated
authenticator; a stable public REST route and a credential-gated documentation
route; outputs schema 5, including the instance identity the access broker needed;
a reviewed API-surface contract and a normalized OpenAPI snapshot with an
update/check split; `app_private.postgrest_pre_request()` with final-shaped claim
validation and an explicit extension point; a temporary asymmetric bootstrap
issuer with a recorded retirement deadline; and two-project route, token, key and
data isolation evidence.

Session 6 must replace the bootstrap issuer with the auth service, keep the
private signing key out of every verifier, reuse the established
issuer/audience/role/claim contract, replace the temporary documentation
credential with project-admin authentication, and **retire the absence proofs
Session 5 wrote about roles it did not activate** — ADR 0046 and ADR 0047 are
addressed to exactly that, and Session 5 will have written more of them.

Session 6 must not give the auth service the migration or object-owner
credential, put the signing key into PostgREST, broaden `db-schemas` or the
request roles' grants, bypass the reviewed contract, or remove the pre-request
validation.

Before Session 6 mutates a project, it runs Session 5's gate — **both halves**.

---

## Appendix — what to consult, and what to measure instead

Documentation matching the **locked** version is worth reading for configuration
keys and semantics: PostgREST's configuration, authentication, transactions,
schema-cache, OpenAPI, admin-server and error references **for the major that is
pinned**; Traefik's routing, middleware and file-provider documentation for the
installed version; PostgreSQL 18 on roles, RLS, function security, `COMMENT`,
`pg_hba.conf` and `NOTIFY`.

None of it is a proof. Every number and every key this session depends on — which
configuration keys the binary accepts, what it does when a hook is missing,
whether a body limit fires at the byte the middleware claims, what a container's
connection to the cluster authenticates as, whether the documentation bundle
reaches the network, what PostgREST costs in unreclaimable memory — is measured
against the locked artifact and written into an executable test.

That rule has already caught, in advance, an `ALTER DEFAULT PRIVILEGES` that
reports success and stores nothing, a Traefik key that exists in no version, a
launcher two sessions out of date, a loopback login that succeeded with a
deliberately wrong password, a pooler that listens while refusing every
connection, and a session GUC that outlived its client. It is the same rule that
would have caught the two absence proofs Session 4 found at its very end.

When a test is green, ask what would have to break for it to go red.
