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
*Offline.*

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
*Offline.*

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
*Offline. The run D100 exists for.*

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
reachable.*

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
