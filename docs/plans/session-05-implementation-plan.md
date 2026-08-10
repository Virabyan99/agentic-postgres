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
| **D140** | §8.1 adds `docs_basic_auth_password` to `secrets.required.yaml`; §8.5 generates a bcrypt hash into a root-owned `usersFile` published under `/var/lib/agentic-postgres/edge/dynamic`, which Session 2 already mounts read-only into Traefik at `/etc/traefik/dynamic`. | The mount is real and the path is right — that half checks out. The secret does not fit the contract: `schemas/secret-contract.schema.json` requires **`consumers` with `minItems: 1`**, and `tests/contract/test_secret_contract.py` cross-checks every consumer against a Compose service and its `user:`. **Traefik is not a project Compose service** — it is the shared edge stack in `infra/edge/compose.yaml` — and the documentation service must never receive this credential, which is the entire point of `removeHeader: true`. There is no service to name. | **Settled in Run 3, from three options with different costs.** (a) The credential is generated by the deploy into the root-owned generation and never traverses the provider — cheapest, and it breaks "secret material is published as an immutable generation" for one value. (b) The secret contract admits a **root-plane consumer** — a schema change and a contract-test change, therefore an ADR, and it also gives `migration_user_password`'s bootstrap reader somewhere honest to live. (c) Name the documentation service as consumer — **refused**, because it materializes the cleartext into the one container that must not have it. `htpasswd` is not a dependency: bcrypt through the locked Python toolchain, or the hash is not generated here at all. | (b) is the shape that generalises, and the bootstrap plane has been an undeclared reader since Session 3 with a comment explaining why. But it changes a currently-passing contract test, so it is an ADR and not a Run-3 convenience. | **maybe** |
| **D141** | §12.1: configure "the protected Traefik access-log field policy to retain the **response** `X-Request-ID` for correlation while dropping request headers by default, **dropping query parameters**, and explicitly dropping `Authorization`, `Cookie`, `X-Request-ID`". | **`accessLog.fields.queryParameters` does not exist in Traefik, and ADR 0019 exists because a floor was once written to guarantee it.** Probed against the locked digest, `accessLog.fields` accepts exactly `defaultMode`, `headers` and `names`. The resolution shipped in Session 2 is that **`RequestPath` is dropped entirely**, because it carries the query string and there is no way to keep one without the other. The path is already gone from access logs; `RouterName` and `ServiceName` remain. | **The query-parameter clause is struck.** Header dropping and the response-header retention are real capabilities and are configured; whether `X-Request-ID` can be retained as a *response* field is measured against the locked digest before it is written, not read from a page. The proof is the outcome, as ADR 0019 rewrote it: a request carrying a secret-shaped query-string sentinel leaves no trace of it in any log layer. | This is the second time this exact key has been asked for by a document written from vendor documentation, and the first time cost a run and took the edge plane down. A setting that decides whether a token reaches a log is the last place to accept a documentation claim. | no |
| **D142** | §5.3 requires "a hash/digest-locked Playwright + Chromium (or equivalently locked headless-browser harness) for Scalar storage/network assertions"; §16.8 asserts no credential in "HTML, JS, network log, local/session storage". | The dev toolchain is hash-locked through `uv pip compile` into `requirements-dev.txt`, and `requirements-dev.in` **pins nothing** — a carried-in open item that has produced a red gate in two sessions. A browser is several hundred megabytes of new dependency, and what it would prove is that a third party's page honours its own `persistAuth: false`. | **No browser.** The documentation page is a **static local snapshot**, so "no credential in the served bytes" is a byte scan of files this deployment wrote — stronger than a browser assertion, because it holds for every visitor rather than for the one that was driven. `persistAuth: false`, the empty plugin set, the absent proxy URL and the absent external document URL are asserted against the generated configuration. The one thing genuinely lost is "Scalar does not itself call out to a third party at runtime", and that is proved instead at the network layer: the container joins one network, holds no credential, and D128's measurement establishes the bundle is self-contained. | A proof whose subject is another project's runtime behaviour is a proof of the wrong thing. This deployment's obligations are: serve no credential, load nothing remote, and let no header through. All three are measurable without driving a browser, and each of the three is measured where it is *caused* rather than where it would be *observed*. | no |
| **D143** | §14.4: PostgREST provides no general body-size control, so Traefik enforces `maxRequestBodyBytes` and `memRequestBodyBytes`; "requests one byte above the maximum receive HTTP 413 before reaching PostgREST" and "a body exactly at the limit reaches the upstream". | The reasoning is right and the middleware exists. Whether those two keys behave as stated against **the locked Traefik digest** is a documentation claim, and it is the same class of claim as D141's. | **Adopted, and measured before it is depended on.** Run 6 sends `limit` and `limit + 1` against the locked digest and asserts the two outcomes; the exact-boundary case must reach the upstream and receive a deterministic non-413 answer, which need not be a valid domain payload. `memRequestBodyBytes == maxRequestBodyBytes` for P0, with a test that no spill file is created — which is a filesystem observation of the running container, not an inference from the equality. | ADR 0019's lesson, applied prospectively for once rather than after an edge plane refuses to start. The boundary test is worth more than the middleware assertion: it fails whether the cause is a renamed key, a changed default, or a router the middleware was never attached to. | no |

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

1. **PostgREST 13.0.4's complete configuration surface** (D127). Every key this
   session intends to set, compared against what `--dump-config` emits. A key
   the binary does not recognise is a boundary that is not there.
2. **What PostgREST does when `db-pre-request` names a function that does not
   exist**, and when the authenticator cannot authenticate (D139). Fails closed
   is a deploy that stops; fails open is a public API with claim validation
   silently disabled, and every other check still green.
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
*Offline, plus a container runtime.*

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
*Offline.*

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
*Offline, then one host materialization plan.*

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
*Offline.*

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

### Run 5 — Migration 0007 and role activation
*Offline. The code, not its execution.*

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

The runbook's §4.2 and §4.11 survive in substance. Restated against the real
identifiers — **subject to ADR 0048**, which is the one thing in this section
that is not yet decided (D129):

| Surface | Methods | Authority |
|---|---|---|
| `api.notes` | `GET`, `HEAD` | security-invoker view; the caller's row policy applies |
| `api.tasks` | `GET`, `HEAD` | security-invoker view; the caller's row policy applies |
| `api.create_note` | `POST` | `SECURITY DEFINER`, safe only because the base tables carry FORCE RLS (D58) |
| the second write RPC | `POST` | named by ADR 0048 |

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
