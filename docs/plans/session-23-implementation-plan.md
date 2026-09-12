# Session 23 — Generated typed clients

**Status:** **PLANNED 2026-09-12** at `d6f6e94`, Session 22's close, on `main`.
No run has started. §1 is D1200–D1211 (planning rows, every one measured
today in a rig or read from the tree at `d6f6e94`); Run 1 added **D1212–D1215**,
measured at the branch point, Run 2 added **D1216-D1223**, Run 3 **D1224-D1228**, Run 4 **D1229-D1233**, Run 5
**D1234-D1235**, Run 6 **D1236-D1241** and Run 7 **D1242**, so next free is **D1243**. ADR
**0204** is this session's; the runs add theirs below the planning rows.
**Brief:** `docs/plans/stage-3-plan.md` §5 *Session 23* and its rows D1067
(the `generate` hook after a project migration), D1068 (one session, the IR
is the three frozen contracts, the hash must read the service), D1074 (each
building session ships its own negative tests), D1079 (generation time in the
envelope); §7's rule *"a generated artefact is a claim about the hash it was
generated from, and its proof reads the served surface, never the document"*;
§8's two rows that name this session (*a generated client's config* and *a
generated client's logging*); §9's stop condition (*a generated client would
learn the live hash from the deployed document rather than from the served
surface*). Plus what Session 22 left in `docs/scope-closure.md` §11 that
touches this session: *PostgREST on a dev cluster is Session 23's first
measurement* (D1157).
**Shape:** seven runs, all offline, all green in CI on a `session-23` branch.
**There is no host trip** — the Session 22 precedent (D1163, ADR 0202). Run 7
is the close: the offline gate on this workstation, the offline evidence
half, the handoff, the fast-forward to `main`. The two HOST claims this
session registers (§2) are measured at Session 24's trip, and this plan says
so wherever it matters (§7, §10).
**Product version at close:** `CURRENT_SESSION` 23; `template_version`
proposed `1.4.0` (a new operator command, a new optional directory under
`projects/<slug>/`, one additive field in a metadata tool's result, a new
fixture image — a minor under ADR 0162; confirmed by the next host's `upgrade
plan`, which is Session 24's).
**Written for whoever picks this up cold, and it will be a different model
than the one that planned it.** Every path is exact; every third party was
measured today, and the two measurements that decide the design (rigs 23a and
23b) are already run and their numbers are in §1 — Run 1 re-runs them as the
control that the tree has not moved, and adds the three that could not be run
at planning. The appendix says how a run is executed in this repository. Read
`CLAUDE.md` §1 in the launch folder before the first command. **Read this
plan's §1 before Run 1**: four of the stage plan's sentences about this
session are wrong or unmeasured (D1200, D1202, D1203, D1206), and the design
below follows the measurements, not the sentences.

---

## 0. Where the session starts

Session 22 shipped `apg dev` and the evidence model's third mode (ADR 0202,
ADR 0203). `evidence/session-22-offline.json`: four offline claims, all
`passed`, at `8823877e`. The host is untouched: deployed release `f61f716` on
both projects, host checkout `f61f716`. Session 23 transports nothing either.

**What a client of this product is today, measured at `d6f6e94`.** Nothing
generates code. `services/clients/` holds four *driver* fixtures (psql,
node-pg, psycopg, prisma — `DBX-001..005`), each a container proving a driver
reaches the database through the pooler; none of them is a client of the
REST, application or agent surface. A developer who wants to call
`api.notes` from TypeScript reads `docs/api-surface.md`, types the path, and
learns the row shape from `contracts/postgrest-openapi.canonical.json` by
eye. A developer who wants to call a tool reads `docs/mcp-tool-catalog.md`
and hand-rolls a JSON-RPC body (`tests/deployment/test_session16_agent_governance.py:128`
is the shape). Neither can tell, before the first request fails, whether the
surface they wrote against is the one being served — which is D700's shape
(`backup_state`) at the client: an artefact that goes stale in both
directions and is held by people who did not generate it.

**What exists and is not rebuilt.** The three frozen contracts and their
digests: `contracts/postgrest-api-surface.yaml` (the reviewed intent,
`api_surface.contract_digest`), `contracts/postgrest-openapi.canonical.json`
(the project-neutral snapshot, `openapi_normalize.fingerprint`, sentinels
`project.invalid:443` / `/__project_base_path__` / `["https"]`),
`contracts/app-openapi.canonical.json` (auth and storage merged, ADR 0087),
`contracts/snapshots/mcp/mcp-capabilities.canonical.json` (the compiled
release contract, schema 4) — and per project the same three under
`projects/<slug>/contracts/` (ADR 0198, ADR 0201; `projects/example` has all
of them). `openapi_normalize.normalize/canonical_bytes/fingerprint/declared_objects`,
`api_surface.merged_surface/load_project_surface`,
`capability_compiler.compile_lock` (the lock's `tools_sha256` is the digest
of `canonical_bytes(tools)` after the profile — line 895 — and covers
**nothing else**, so it is computable from a checkout), `compatibility.CHANGE_CLASSES`
and `required_level` (ADR 0162), the PT SQLSTATEs the migrations raise
(`PT401 PT403 PT404 PT409 PT412 PT422`, `grep -o "PT4[0-9][0-9]" migrations/templates/*.sql`),
the seven caller-facing tokens (`services/auth-api/app/mcp_errors.py:332`),
`PT412` and the `Idempotency-Key` header (`mcp_query.py:104`), `bin/api.sh`'s
enumerated operations, the docs route (Basic-auth, `bin/docs.sh`'s header),
`apg dev` and its rendered fixture, the pinned Node image
(`NODE_RUNTIME_IMAGE`, `node:22-alpine@sha256:c610fcdf…`, **v22.23.2**), and
the npm package-pinning shape (`PRISMA_VERSION` in `versions.in.yaml`, sha512
digest, `npm ci --ignore-scripts` in a Dockerfile, an integrity hash on every
lock entry — `test_client_fixtures.py:171`).

**What this session builds, in one paragraph.** A pure intermediate
representation (`src/agentic_postgres/client_ir.py`) read from exactly four
inputs — the merged reviewed surface, the project's (or the release's)
PostgREST snapshot, the application snapshot, and the project's compiled
lock — carrying every relation with its columns and types, every reviewed
RPC with its argument schema, the three authentication operations, every tool
in the lock with its arguments and scopes, the enum vocabulary, the filter
operator set, the PT-code vocabulary the release and the project's set raise,
the caller-facing tokens, and **four digests** (`api_surface_sha256`,
`rest_openapi_sha256`, `app_openapi_sha256`, `tools_sha256`). A TypeScript
emitter (`client_typescript.py`) that reads the IR and nothing else and
writes a dependency-free package: `client.ts` (typed reads over the reviewed
views, typed RPC writes, the three auth calls, a `RestError` union from the
PT codes), `agent.ts` (a tool-call wrapper per tool in the lock over JSON-RPC
`tools/call`, an idempotency-key helper, an `AgentRefusal` union from the
seven tokens), `contract.ts` (the four digests and the contract ids, the one
place they live), `canonical.ts` (the canonical-JSON fingerprint, proved
byte-equal to Python's over every snapshot in the tree), `package.json` (the
derived version, `typescript` as the only devDependency, no dependencies),
and `README.md`. `init()` is the whole defence: it fetches the served REST
OpenAPI document **as the caller**, normalizes it the way the capture does,
and refuses every later call unless the fingerprint equals the embedded one
— naming both digests; the agent wrapper's `listResources()` reads the lock
digest the **running** plane reports (a field this session adds to that
tool's result, from the lock the process loaded) and the client refuses when
it is not the one it was generated from. `bin/generate.sh` + `bin/generate.py`
(reached as `apg generate`, by construction) with `--project FILE [--out DIR]
[--check]`; the example project's client committed under
`projects/example/clients/typescript/` byte for byte and drift-checked by the
gate. A toolchain image `services/clients/typescript/` on the pinned Node
with `typescript` pinned and hash-locked, used only to typecheck and to run
the client's smoke against `apg dev` plus a PostgREST rig configured from
`compose.yaml`'s own `postgrest.environment` block. Generation time in the
envelope. A version derived from ADR 0162's classes over the IR diff.
Everything a generated file could hold that the human does not — a token, a
password, a URL with a credential, a signing key — is refused by the emitter
and scanned for by a test.

**What it does not build, by decision** (§1): a Python client (D1205); an
ORM, a query builder over base tables, or any call the contracts do not name
(the stage plan's *must not*, and `product-contract.md` §5); the admin and
storage halves of the application API (D1209); a client that reads the
deployed document (ADR 0158); a second canonical serializer in Python
(D1203); PostgREST as a verb of `apg dev` (ADR 0203 stands — the rig is a
test's, tied to the product's configuration by reading it).

**Read before touching anything:** ADR 0002 (derive an identity once), 0050
(a reviewed surface is a generated artefact with an update/check split),
0065/0066 (a rig is a second configuration of the product and must be tied
to it), 0087 (both documentation surfaces strip the root), 0093 (an operator
command reaches service logic through a container), 0119 (an operation id is
derived), 0120 (a tool may be backed by more than one capability), 0125 (the
plane forwards the caller's own token; `stateless_http`, no handshake), 0127
(a caller value is a value; the request is built from the lock), 0130 (a
refusal reaches the caller only through `ToolError`), 0139 (a write refusal
is translated from the product's errcode), 0158 (the deployed document is
the address book, not the diagnosis), 0162 (what a bump permits), 0181 (an
idempotency key is claimed in the write's own transaction), 0182 (a dry-run
attempts the write and rolls it back), 0183 (a profile only narrows), 0195
(three outcomes, the third reported), 0198/0200/0201 (a project's set,
surface, snapshot, vocabulary and capability manifest), 0202/0203 (the
offline claim; the dev environment is the database); D105 (nothing prints a
token), D292/ADR 0093 (an operator command imports only what the host has —
`HOST_PACKAGES = {"agentic_postgres", "yaml"}`), D433, D486 (a second copy of
a value is a compared pair with a contract test between them), D600, D1114
(a proof calls the product's own command), D1152/D1153, D1157, D1184 (in a
`bin/` command the identifier `document` MEANS the deployed document), D1187
(a move greps the moved text), D1199 (a gate's last lines are the least
executed).

---

## 1. The divergence table

Six columns, next free number after this table **D1243**. Rows D1200–D1211
were measured at planning on 2026-09-12 at `d6f6e94`; **D1212–D1215 are Run 1's** and
**D1216–D1223 Run 2's**, each measured while the run that names it was built.
The runs add theirs below them as they go, each run's numbers named in its Done
paragraph.

| # | Said | Repository does | This session | Why | ADR |
|---|---|---|---|---|---|
| **D1200** | Stage plan §5 Session 23: the hash is *"checked at init against a served value: which value, and which route serves it, is the session's first measurement (a candidate is the docs route's served OpenAPI digest plus `list_resources`' lock digest; the deployed document is not the answer, ADR 0158)"*. | **Measured today, rig 23a.** On an `apg dev` cluster (33 migrations, the example set applied) with PostgREST started from `compose.yaml`'s own `postgrest.environment` values (`follow-privileges`, the pre-request hook, the proxy URI), `GET /` served to the **`authenticated`** role normalizes to fingerprint **`808ac715c09aeebc…`** — **exactly the committed project snapshot** `projects/example/contracts/postgrest-openapi.canonical.json` — and so does the `api_documentation` role's (the role the capture runs as, D1114). The **`anon`** role's document publishes **zero paths** (fingerprint `1da00c119b984b82…`), so an unauthenticated request cannot verify anything. The docs route (`/docs/rest/openapi.json`) serves the FILE the deploy mounted (`rendering.py:2449` copies `CANONICAL_OPENAPI` byte for byte) behind **Basic auth** whose password is materialised for Traefik and never handed to anybody (`bin/docs.sh` header) — a client cannot hold it and should not. | **The client checks the live REST surface, as the caller, by strict fingerprint equality**: `init()` performs `GET <restUrl>/` with `Accept: application/openapi+json` and the caller's own bearer, normalizes (D1207), fingerprints (D1203), and compares to `contract.ts`'s `rest_openapi_sha256`. A mismatch is `stale_contract` naming both digests and every later call is refused; a fetch that fails is `unreachable`, a document that will not parse is `unreadable` — three outcomes, reported (ADR 0195). The docs route is not read. The MCP half's served value is `list_resources` (D1201). | The served surface is what the caller is about to use; the docs route is what the deploy mounted; the deployed document is what the deploy observed. Only the first is the thing the client's types describe, and rig 23a shows a caller's own token sees exactly what the capture saw. | 0204 |
| **D1201** | Stage plan: *"`list_resources`' lock digest"* as a candidate served value for the agent half. | **No route or tool serves the lock digest.** `mcp_tools.list_resources` (`services/auth-api/app/mcp_tools.py:260`) returns `{contract_id, resources}` and nothing about the lock; `tools/list` returns names and input schemas; the runtime records which lock it loaded only in `mcp_runtime.LOADED_LOCK` (D1153), read by the deploy's `docker exec` probe and by nobody over HTTP. `CapabilityLock.tools_sha256` is `None` below lock schema 4 (D1182). | **`list_resources` gains one additive member `lock: {"tools_sha256": <str \| null>, "tool_count": <int>}`** from the `CapabilityLock` the process holds (the same object `LOADED_LOCK` records); `null` below schema 4, never a recomputation. The generated `agent.ts` `listResources()` compares it to `contract.ts`'s `tools_sha256`: equal → the roster the client wraps is the one being served; different → `stale_contract` with both digests; `null` → `unconfirmable` (ADR 0195: reported, not folded). Readers grepped in Run 2 (`test_mcp_tools.py:143,653,734` pin the result's shape; the harness's metadata cases read scope sets, not the body). | The deploy already asks the container which lock it serves (D1153); an agent asking the same question over the plane's own transport is the same fact at the boundary where a client needs it. A digest the runtime *carried* (D1182) is the honest value; a count is not a signature. | 0204 |
| **D1202** | Stage plan: *"an idempotency-key helper that sets the header ADR 0181 claims"*. | **The caller never sets that header.** An agent supplies `idempotency_key` as a **tool argument** (`mcp_tools.py:1101`, `RESERVED_WRITE_PARAMETERS`); the **runtime** sets `Idempotency-Key` toward PostgREST (`mcp_query.IDEMPOTENCY_KEY_HEADER`, `mcp_upstream.py:389`); the database requires it only when `acting_agent IS NOT NULL` (`0029:287-291`), so a **human's** REST write carries none and needs none. The key's shape is `^[\x21-\x7e]{8,255}$` (`0029:163`, mirrored at `mcp_tools.py:514`). | The helper is `idempotencyKey()` in `agent.ts`: 32 hex characters from `crypto.getRandomValues`, satisfying the shape, and every write wrapper takes `{idempotency_key, dry_run}` as required members beside the tool's arguments (the runtime requires both, `mcp_tools.py:1048`). `client.ts` sets no idempotency header. `PT412` reaches a caller of the wrapper as `input_not_permitted` with the runtime's sentence (`mcp_errors.py:372`), which is what the union carries. | The header is an implementation detail between two containers; the contract a caller holds is the tool's argument list, which the lock is the authority for (ADR 0127). | 0204 |
| **D1203** | Stage plan: *"the generation hash — the three contract digests and the lock's — embedded, and checked at init"*, read as though every digest could be recomputed by the client. | **Measured today, rig 23b, on the pinned image.** `JSON.stringify(sortKeysDeep(x), null, 2) + "\n"` reproduces `openapi_normalize.canonical_bytes` **byte for byte** for the release REST snapshot (`85adb686…`), the release MCP contract, the project REST snapshot (`808ac715…`) and the project MCP contract — and **NOT** for `contracts/app-openapi.canonical.json`: two Pydantic float literals, `"minimum": 1.0` (line 494) and `"exclusiveMinimum": 0.0` (line 1745), which JavaScript prints as `1` and `0`. Controls: JS renders `1.0`→`1`, `-0`→`0`, and loses precision above 2^53; Python keeps all three. `bin/app-contract.py:160` also serializes with `ensure_ascii=True` where `canonical_bytes` uses `False` — equal today only because the document is ASCII. | **The client recomputes exactly one digest at init — the REST snapshot's — and `canonical.ts` is a second implementation of the canonical form guarded two ways**: (a) `client_ir.js_reproducible(document)` in Python refuses, at generation time, any REST snapshot whose canonical form JavaScript cannot reproduce (a `float` anywhere, an `int` outside ±2^53, a key that sorts differently under UTF-16), naming the JSON pointer; (b) `test_generated_client_toolchain.py` runs `canonical.ts` in the toolchain image over every committed snapshot and asserts each digest equals Python's (four EQUAL, the app document listed as the known exception with its two lines). `app_openapi_sha256` and `tools_sha256` are embedded as provenance and compared to a served value only where one exists (`tools_sha256`: D1201; the app document: none, D1209). | A second implementation of a canonical form is D486's shape and is acceptable only with the comparison test that keeps the pair honest; the alternative — the client fetching a digest somebody else computed — is trusting a document over the surface, which is the stop condition. | 0204 |
| **D1204** | Stage plan: TypeScript, with no statement of the toolchain; `versions.env` pins `NODE_RUNTIME_IMAGE` only for the docs bundle and the node-pg fixture. | **Measured today, rig 23b.** The pinned image is Node **v22.23.2**, npm 10.9.8: it runs a `.ts` file **directly with no flag** (type stripping is unflagged at this version; `--experimental-strip-types` is accepted and redundant), `fetch` is a global, and `crypto.getRandomValues` exists. So a generated client needs **no build step and no runtime dependency**; `typescript` is needed only to typecheck. | The generated package declares `"dependencies": {}` and `"devDependencies": {"typescript": "<TYPESCRIPT_VERSION>"}`; the toolchain image `services/clients/typescript/` pins `typescript` through `package-lock.json` with an integrity hash and `npm ci --ignore-scripts`; its entrypoint typechecks `/work` (`tsc --noEmit --strict`) and runs `/work/smoke.ts` with plain `node`. `TYPESCRIPT_VERSION` joins `versions.in.yaml` under `packages:` with `registry: npm`, locked by `bin/lock-versions.sh --update --packages-only`. A test asserts the lock's `typescript` version equals `versions.env`'s (the `test_client_fixtures.py:186` shape). | A client that needed a bundler would need a lockfile per adopter and a build nobody reviews; one that runs as source on the pinned runtime is reviewable line by line. | 0204 |
| **D1205** | Stage plan §5/§6: *"Python evidence-selected inside the session: built only if the TypeScript generator proves the IR carries without a second reader of the contracts."* | The criterion is a property of two modules and is assertable without building the second client: `client_typescript.py` imports `client_ir` and the standard library only, and reads no file under `contracts/` or `projects/` (an AST test over its imports and its string literals). | **The criterion is measured (Run 3) and the Python client is NOT built in this session.** If the test holds, the IR carries by construction and a Python emitter is one module over the same IR — priced for Session 25's hardening run or a later session, with this row as its evidence. If it does not hold, the emitter is repaired until it does; a second reader of the contracts is the thing this row forbids. | A second emitter doubles the surface a weaker executor has to get right and proves nothing the AST test does not; the stage plan asked for evidence, and the evidence is the test. | — |
| **D1206** | Stage plan: *"Versions derived from ADR 0162's change classes over the contract diff — never a second scheme"*; *"the version derivation agreeing with `upgrade plan`'s class for the same diff"*. | `compatibility.CHANGE_CLASSES` names `api_operation_added` (minor), `api_operation_removed` and `api_operation_changed` (major), `capability_added` (minor). **Nothing in the tree classifies a contract diff into those three `api_operation_*` classes**: `upgrade_plan.classify_document_changes` (`upgrade_plan.py:139`) reads rendered-document leaves only — `image_digest`, `implementation`, `secret_required_added`, `capability_added` — and its docstring says an API change *"lives in `contracts/`; neither is visible in a rendered document, so neither is guessed here. The caller measures those and passes them to `build_plan` as `also`."* Run 1's rig 23d reads `bin/upgrade.py` to record whether any caller passes an `api_operation_*` class today. | `client_ir.classify_changes(previous: IR, current: IR) -> tuple[str, ...]` returns **only names in `compatibility.CHANGE_CLASSES`** (asserted): an operation, tool or column present in `current` and absent in `previous` → `api_operation_added` / `capability_added`; absent in `current` → `api_operation_removed`; same name with a different argument list, column type, enum member set or required-scope set → `api_operation_changed`; no IR difference → `()`. `compatibility.required_level(classes)` gives the bump, `client_ir.next_version(previous_version, level)` applies it (`1.0.0` for a first generation). The measurement the stage plan asked for is made at that level: a planted `api_operation_added` (rig 23d, a copy of the example surface + snapshot with one more RPC) makes `generate` say `minor` and `required_level(["api_operation_added"])` says `minor` — the same function, not an agreeing second one. **`generate` does not touch `template_version`** and `upgrade plan` does not read the client's version: the client's number is the project's artefact, priced by the release's rule. | The rule is ADR 0162's; the number is the artefact's. Two numbers with one rule is what *"never a second scheme"* permits, and the alternative — the client's version being `template_version` — cannot move when a project's own contract does and the release's does not. | 0204 |
| **D1207** | `openapi_normalize.normalize` validates `host`, `basePath` and `schemes` against the deployed document before substituting the sentinels (ADR 0050: *"validate the real values, then substitute"*). | A client holds no deployed document. It holds a URL it is already connected to. The served `host` carries `:443` (`fixture-alpha-dev.test:443`, rig 23a) where `new URL(restUrl).host` omits a default port; and the offline runtime proof reaches PostgREST over `http` on a bridge address, where `schemes` is `["http"]`. | `canonical.ts`'s `normalizeServed(document, restUrl)` asserts exactly one thing before substituting the three sentinels: `document.basePath === new URL(restUrl).pathname` (with one trailing slash tolerated), because that is the string the client prefixes every request with; a mismatch is `stale_contract` naming both. `host` and `schemes` are substituted without assertion — the client is speaking to that host over that scheme already — and `_refuse_residue`'s search is repeated over the served host and base path so a value that leaked into a description is refused rather than normalized into agreement. Stated in ADR 0204 as the one place the client's normalization is deliberately narrower than the capture's. | The capture's validation protects a *committed* file from describing an unreachable address; a client has no file to protect and its own address to compare against. | 0204 |
| **D1208** | Stage plan D1067: *"`apg generate`, and its hook after a project migration"*. | A client is generated from the **snapshot**, and a project's snapshot is captured only after a deploy (README *Adding your own tables* row 4: *"captured from a running deployment"*) — a migration alone moves nothing the generator reads. The step that changes the generator's input is `bin/api-contract.sh --update --project` (the capture) and, for the agent half, `bin/mcp-contract.sh compile --project`. Nothing in `bin/` prints a *next step* to run a generator, and there is no generator. | **The hook is a printed next step, never an implicit run**: `api-contract.py::command_update` (with `--project`) and `mcp-contract.py`'s `compile --project` path each print one more stderr line — `then: bin/apg.sh generate --project <FILE>` with the path the process holds (D975 / `test_printed_commands`) — and **the gate refuses a stale client**: `apg generate --check --project project.example.yaml` in `session-23-check.sh` step 6 and in CI, exit 5 with the first differing file named. A committed client that does not match a fresh generation is what *stale* means here. | A hook that ran the generator inside the capture would write a file under sudo (the capture streams for exactly that reason) and would hide the step a reviewer needs to see. | 0204 |
| **D1209** | Stage plan: the client is generated from *"the PostgREST snapshot, the application snapshot and the project's compiled MCP contract"*, without saying which of the application API's 18 paths a client should wrap. | `contracts/app-openapi.canonical.json` publishes `/auth/*` (login, refresh, me, jwks, sessions, reset-password, agent-token), `/admin/*` (users, agents, audit) and `/storage/*`. The admin paths are the operator's (`bin/auth-admin.sh`, a password file, D1150), the storage paths are a plane with its own credential flow, and the application document is not live-served on any route a client can read without the docs password (D1200) — it enters the client as provenance only. | **`client.ts` wraps exactly three application operations — `login`, `refresh`, `me`** — typed from the snapshot's request and response schemas (`LoginRequest`, `SessionTokenResponse`, `TokenResponse`, `SubjectResponse`), so a client can obtain, renew and inspect the token it then presents to the REST surface. No admin, no storage, no agent-token exchange for a human (an agent's secret is a credential a human should not hold). `app_openapi_sha256` is embedded and reported by `contract.ts`, not verified at init. The stage plan's four inputs are all read; the row is what is emitted from the second. | The DX layer holds nothing the human does not hold (§8, stage plan §2.1). Three calls a human already makes through a browser are the whole of what a human-side client needs from that surface. | 0204 |
| **D1210** | Stage plan §5 *Must not*: *"Generate a call the contract does not name — a base table, a column outside the allowlist, a filter operator outside the set."* | The reviewed surface names relations with `columns` and RPCs with `arguments` (`contracts/postgrest-api-surface.yaml`, `projects/example/contracts/postgrest-api-surface.yaml`); the snapshot names the same objects plus every column's `format` and every RPC's body schema; **the filter-operator set** exists once, in `evaluation_harness.filter_operators()` (from `schemas/capabilities.schema.json`) — the operators a capability may declare. PostgREST itself accepts many more (`like`, `ilike`, `fts`, …). | The IR takes relations and RPCs from the **merged surface** and refuses (exit 5, naming the object) any snapshot object the surface does not name and any surface object the snapshot does not publish — the two-sided comparison `api-contract.sh --check` makes, repeated here because a generator that ran on a disagreeing pair would emit a call for one side's belief. Columns are the surface's `columns` in the surface's order; types come from the snapshot's `definitions.<relation>.properties[column].format`; **filters are typed per column over the same operator set the capability schema enumerates** and no other — one operator vocabulary in the product, which the agent plane already enforces (ADR 0127). A read request is built from `select`, `order`, `limit` and `<column>=<op>.<value>` and nothing a caller types reaches the query string unencoded. | A client over the reviewed contract is inside DBX's non-goal line; a client offering PostgREST's whole operator grammar would be a query language with a type signature, and an operator the capability schema forbids an agent would then be one a generated client offered a human. | 0204 |
| **D1211** | `docs/scope-closure.md` §11, D1157: *"PostgREST on a dev cluster is Session 23's first measurement if its client needs a served surface"*, with the open worry that a locally captured snapshot *"must be measured byte for byte against a deployed one before anybody trusts it"*. | **Measured today, rig 23a.** PostgREST started beside `apg dev` with the product's own environment values serves, to `authenticated`, a document whose normalized fingerprint **equals the snapshot captured from the deployment** (`808ac715…`), the example set included. The `postgrest_authenticator` role exists on the dev cluster (the bootstrap creates it) and is **not** activated by `apg dev up` (`ACTIVATED_ROLES = ("migration_user", "app_runtime")`); the rig activated it as the superuser through `docker exec`. | The offline runtime proof (Run 4) is a **rig** beside the product's environment, and ADR 0066 is what keeps it honest: it reads `compose.yaml`'s `services.postgrest.environment` as YAML and substitutes only the values it must (`PGRST_DB_URI` with the rig's own password file, no `PGRST_JWT_SECRET`, `PGRST_DB_ANON_ROLE` set to the role under test), so a setting the product changes reaches the rig without anybody editing it. `apg dev` gains **no** `--with-rest` verb (ADR 0203 stands; §10 records the option). The worry in §11 is answered as far as this session needs it: a local capture equals the deployed one for the example project, once, today — recorded in the Done paragraph, not promoted to a claim. | The measurement was the cheapest thing in this plan and it decided the design; making it a product verb would make the dev environment a second way to start the product's containers, which ADR 0013 and ADR 0065 refuse. | 0203 |
| **D1212** | This plan's Run 1, rig 23c: *"`{"typescript":"5.9.3"}` — 5.9.3 is a guess; read the current stable from `https://registry.npmjs.org/typescript/latest` first and use that"*, and *"`… bad.ts` (expect 2, one error line naming the file: the control)"*. | **Measured today, rig 23c, in the pinned image.** `typescript`'s `dist-tags.latest` is **7.0.2** — the native compiler — and the 5.x line ends at 5.9.3. Both arms install and typecheck on musl: `npm install --package-lock-only --ignore-scripts` gives 7.0.2 a **22-entry** lock (the package plus 20 optional per-platform binaries) and 5.9.3 a 2-entry one, **every entry in both carrying an `integrity` hash**; `npm ci --ignore-scripts` exits 0 and `tsc --version` answers for both. But a type error exits **1 under 7.0.2 and 2 under 5.9.3** — same message (`bad.ts(4,7): error TS2322: Type 'string' is not assignable to type 'number'`), different status. | Pin `TYPESCRIPT_VERSION=7.0.2` (current stable; `lock-versions.sh --update --packages-only` would resolve to it anyway, and a pin two majors behind what the locker resolves is D540's shape). **Every typecheck proof asserts a non-zero exit AND the error line naming the file and the TS code, never the bare number** — the plan's "expect 2" would have been a green proof that measured the wrong thing under the version actually pinned. | The plan's own number was flagged in it as a guess, and it was wrong by two majors. An exit code that changes with a major version is §7's *value that looked measured and was not*: the assertion that survives the bump is the message, and it is strictly stronger than the number. | 0204 |
| **D1213** | This plan's Run 1, rig 23d: *"record whether any caller passes an `api_operation_*` class into `build_plan(also=…)` (**the plan expects none**; D1206 says so from a read, this confirms it from the tree)"*. | **Half right, and the wrong half matters.** No caller *computes* an `api_operation_*` class — but `bin/upgrade.py:100–102` already **lists all three** (`api_operation_added`, `api_operation_removed`, `api_operation_changed`) as classes an operator may **declare** with `--also`, and `upgrade_plan.build_plan` unions `also` into the classified set (`upgrade_plan.py:250`). 15 mentions tree-wide; the others are `compatibility.py`'s three definitions, `test_capability_compiler.py`'s unrelated `test_a_new_api_operation_exposes_no_capability`, and this plan. `required_level` separates them as written: `[]`→patch, `api_operation_added`→minor, `capability_added`→minor, `api_operation_removed`/`api_operation_changed`→major, and an **unclassified name raises** rather than defaulting to patch. | `classify_changes` emits **only** names already in `CHANGE_CLASSES`, so its output is exactly the vocabulary `upgrade plan --also` already accepts. The agreement the stage plan asked for between the generator's class and `upgrade plan`'s is therefore **an agreement by construction**, not a second scheme to reconcile — and a test asserts the generator's vocabulary is a subset of `bin/upgrade.py`'s declarable set. | D1206 read the tree for what computes a class and concluded nothing touches them. The operator surface had accepted all three since ADR 0162. Reading for the producer and missing the consumer is §7 question 5 — *which of its callers got it* — answered from the wrong end. | 0204 |
| **D1214** | This plan's Run 1 cites `tests/deployment/test_session22_plane.py:831-850` for `sse_result`/`refused`/`tool_text`, and D1200/§1 cite `bin/api-contract.py:665`'s own message about object sets. | **Both line numbers are out of range.** `test_session22_plane.py` is **407** lines and the three helpers are at **:73–95**; `bin/api-contract.py` is **546** lines and the object-sets-agree message is at **:457**. The cited text exists in both cases — only the addresses are wrong, and each file has the helper under a different name elsewhere too (`sse_result` is defined in **six** deployment modules). | Cite **:73** and **:457**; Run 3's emitter is written from the text read at those lines, recorded in this run's Done paragraph rather than re-derived. Every later run that cites a line re-reads it first. | A plan written to be executed by a different model makes a line number an instruction. These two resolved to nothing, which is the safe failure; a line number that resolves to the *wrong* code is the one that costs a run, and nothing in this repository checks a citation. D1187's shape (grep the moved text, not the name) applied to the plan itself. | — |
| **D1215** | This plan's §2, `AGT-META-001`: the lock digest is *"`null` **below lock schema 4**"*, read as though the loaded lock carried its schema version. | **`CapabilityLock` has no `schema_version` field.** Its ten fields are `contract_id, project_key, upstream, canonical_sha256, tool_count, capability_count, tools, profile, vocabulary, tools_sha256`; `tools_sha256` is `str | None` and `vocabulary` is `dict | None`. The schema version is read by `load_lock` (`SUPPORTED_SCHEMA_VERSIONS` is `{1,2,3,4}`) and **not carried onto the object**. Measured: `list_resources` on a lock with `tools_sha256` set and on one with it `None` returns the same two keys either way. | `AGT-META-001` is written against **`tools_sha256 is None`**, not against a schema version: the `lock` member reports `{tools_sha256, tool_count}` from the loaded object, and `tools_sha256` is `null` exactly when the loaded lock carried none. No schema version is threaded onto `CapabilityLock` to satisfy a requirement's wording. | The wording implied a field, and implementing it literally would have added a field to a released dataclass to make a test sentence true — the inverse of the fix this project wants. `tools_sha256 is None` is the same condition with no new state, and it is the condition the runtime can actually answer. | 0204 |
| **D1216** | Run 2's format table, from the plan: *"typed from `snapshot["definitions"][relation]["properties"][column]["format"]` by one table — `uuid\|text\|…\|extensions.vector → string` … an enum's format (the type's schema-qualified name, `api.task_status`) → a string-literal union"*, i.e. one spelling per type. | **One type has up to three spellings in one document, measured in `projects/example`'s own snapshot.** An enum COLUMN carries the schema-qualified name (`tasks.status` → `api.task_status`) and the same type as an RPC ARGUMENT carries the BARE name (`update_task_status.p_expected_status` → `task_status`); a parameterised type carries its modifier as a column and not as an argument (`note_embeddings.embedding` → `extensions.vector(768)`, `set_note_embedding.p_embedding` → `extensions.vector`). An exact-match table refused the release's own contract on the second call. | `_ts_type` strips a trailing `(…)` modifier, then resolves in a fixed order: the qualified name, then the built-in table, then the bare enum name. An enum whose name is also a format name is **refused outright** — a column of it would be served qualified and an argument bare, so the two spellings would resolve to different TypeScript types and the generated client would disagree with itself about one type. | The plan read one example (a column) and generalised. Three spellings of one type is the sort of fact only the document says, and it says it in a file that was already committed — nothing had to be deployed to find it. The refusal of a shadowing enum is the part worth keeping: it closes the case rather than picking a winner. | 0204 |
| **D1217** | The plan fixes the IR's digest block as `Digests: api_surface_sha256; rest_openapi_sha256; app_openapi_sha256; tools_sha256`. | **`api_surface_sha256` is a taken name with a different meaning.** `bin/mcp-contract.py` writes `sources.api_surface_sha256 = api_surface.contract_digest()` and the deployed document publishes `api.api_surface_sha256`; both mean *the digest of the RELEASE file's bytes*. The IR's value covers the MERGED surface — release joined with the project's — which for any project declaring a set is a different number. | The IR's field is **`merged_surface_sha256`**, over `capability_compiler.canonical_bytes(merged)`. A test asserts it is NOT equal to `api_surface.contract_digest()`. | This repository already carries one instance of *two fields with one name digesting two files* (the two `capabilities_sha256`, still an open item). A third for the sake of matching the plan's word would have been the cheapest possible way to reproduce a defect that is already written down as a defect. | 0204 |
| **D1218** | The plan: *"a `write` tool's [arguments] are the lock's `write.arguments` plus `idempotency_key` and `dry_run`"*. | **That is the loaded dataclass's shape, not the document's.** `mcp_lock.CapabilityLock` nests a `WriteSpec` under `write`; the lock DOCUMENT that `capability_compiler.compile_lock` emits is FLAT — `arguments`, `operation`, `required_scopes`, `max_affected_rows` and `idempotent` sit at the tool entry's top level. Reading `entry["write"]["arguments"]` found every write tool argument-less and refused the release's own lock. | The IR reads `entry["arguments"]`. The plan's own instruction two lines earlier was the right one and says why: *the IR reads the lock document, the JSON, never the service's dataclasses* — `src/` may not import `services/` (ADR 0084), so the document is the only shape this module may believe. | A plan that states a rule and then contradicts it in a detail is the ordinary case, not the unusual one. The rule was written down because it is easy to slip; the slip was in the same paragraph. | 0204 |
| **D1219** | Run 2's `classify_changes`, read as a comparison of IR members: *"a changed argument list, column type, enum set or scope set `api_operation_changed`"*, implemented as dataclass inequality. | **Dataclass equality cannot tell an addition from a retyping, and `api_operation_changed` is MAJOR.** Measured on the tree's own pair: release → example project, a purely additive tenant extension, classified as **major**, because `query_resource` gained the `note_embeddings` resource and a second discovery scope set. A `discovery_scope_sets` entry is an ALTERNATIVE — a caller holding `notes:read` still discovers the tool — so gaining one takes nothing from anybody. | Compared member by member. A relation's column gained, a tool's resource gained, a discovery scope set gained → additive (`api_operation_added` / `capability_added`). A column retyped or lost, a scope set lost, an argument list moved in any way, an enum's members moved → `api_operation_changed` or `api_operation_removed`. **An argument ADDED to an existing RPC stays breaking** and that is not laziness: PostgREST resolves a function by the names supplied and a missing one is a `404 PGRST202` (ADR 0139). Now measured: release → project is `minor`, project → release is `major`, identity is empty. | Stage 3's entire premise is that a project adding a table is additive. A version rule that made the example project's own extension a major bump would have been refuted by the first adopter who used the feature the stage was built for — and it would have looked like a considered answer, because it came out of a comparison rather than a guess. | 0204 |
| **D1220** | This session's own ADR 0204 draft and D1213: *"a generator that classifies its own diff produces exactly the vocabulary `upgrade plan --also` already takes"*. | **The planner reaches a class two ways, and `--also` is only one of them.** `bin/upgrade.py::DECLARABLE` carries eight names — the ones *"no pair of rendered documents can establish"* — and `capability_added` is deliberately **not** among them, because `upgrade_plan.classify_document_changes:167` computes it itself from a `capabilities.*` addition in the rendered document. Run 2's own proof, written to assert the D1213 sentence, failed on the generator's most ordinary output. | The property asserted is the UNION: every class the generator emits is one the planner can **reach**, by being told it (`DECLARABLE`) or by computing it (`classify_document_changes`). ADR 0204's paragraph was corrected in the same run. | D1213 was itself a correction of the plan, written the same day, and it was still half wrong — in the reassuring direction. The test that caught it was written to confirm the sentence, which is the only reason it was caught: a proof written to agree with a claim is the one that can disagree with it. | 0204 |
| **D1221** | Run 2's battery, as planned: *"the format table losing `uuid` (kill: `_types` test)"* and *"`pt_codes` scanning only the release"* — both expected to be killed by the proofs as written. | **Neither was.** The `uuid` mutation produced an **ERROR, not a FAILED**: `build` raises inside a module-scoped fixture, so every test in the module errored and none reached an assertion — a broken fixture, which D386 says is never a kill. The `pt_codes` mutation **SURVIVED**: the example project's own migrations raise no code the release does not, so `sources[:1]` returns the same set and no assertion over the committed tree can see the difference. | Two new proofs. `test_every_format_the_committed_snapshots_serve_has_a_typescript_type` reads the table and the documents only, touching no fixture, so the same mutation fails as an assertion; `test_the_pt_codes_are_scanned_from_the_release_and_the_set` gained a synthetic second directory raising `PT499`, which is the only arm that can fail. Both mutations now kill. The battery itself was repaired too: each mutation runs scoped to the test meant to kill it (`-k`), or a fixture-level break masks the assertion under test. | Two of the four defect shapes this project keeps producing, in one battery, in proofs written the same hour: a test that cannot fail, and a reader that cannot tell a broken fixture from a kill. The planned mutation list was right about what to attack and wrong about what would happen — which is the only reason to run one rather than reason about it. | — |
| **D1222** | The plan's §5: each run ends with *"one commit on the `session-23` branch"*, with Run 2 (the IR) and Run 3 (the emitter) as separate commits. | **A commit of Run 2 alone cannot be green.** `test_repository_contract::test_no_module_is_imported_only_by_its_own_tests` refuses a module imported by nothing outside its own tests (D204: *"a module with no caller is a feature that does not exist, however well it is tested"*), and `client_ir`'s only caller is `client_typescript`, which is Run 3's. Measured: 1156 passed, that one failed. | Run 2 and Run 3's **emitter** land in ONE commit; the rest of Run 3 (the toolchain image, `versions.in.yaml`'s two packages, `bin/generate.sh`/`generate.py`, the committed example client) follows in its own. The guard is not weakened and no placeholder caller is written — writing one to satisfy it would be exactly the gaming D204 exists to prevent. | A run boundary that the repository's own guards make un-commitable is a planning error, not a licence to commit red. The cheap alternative — a caller written to satisfy the check — is available in every instance of this and is always wrong. | — |
| **D1223** | The emitter's structural proofs: the banner, the digests in one file, no credential, the unions equal to the contract's names — all green on the first emitted package. | **The emitted TypeScript did not compile.** `tsc --noEmit --strict` in the pinned image, first run: `agent.ts(141,11): error TS2300: Duplicate identifier 'listResources'` (written by hand for the digest comparison AND emitted again from the tool roster) and `agent.ts(183,81): error TS2304: Cannot find name 'AgentFilter'` (referenced by the read tool's argument list, emitted by nothing). Every structural proof passed on that code. | `list_resources` is excluded from the generated roster methods, and `AgentFilter` is emitted in `types.ts`. `test_the_emitted_client_typechecks_strict_in_the_pinned_image` is now in the tree with a paired control — a deliberately wrong line in the SAME container — and it asserts the error MESSAGE as well as a non-zero exit, because the exit status for a type error is 1 under 7.0.2 and 2 under 5.x (D1212). | §7's question 1 — *what would have to break for this to go red* — answered honestly about eight green proofs: nothing, because none of them compiled anything. A generator is the one kind of code whose output has a compiler, and not running it is choosing not to use the only total check available. | 0204 |
| **D1224** | Run 3's version rule: *"the package version is the previous one bumped by `compatibility.required_level(...)`"*. | **Applied literally it moves the number on every regeneration, and makes `--check` permanently red.** `required_level([])` is `patch` — correct for the TEMPLATE, where *"a release that publishes nothing new is still a release"*, and wrong for a generated artefact. Measured on the first `--check` this command ever ran: `generate` wrote the client at `1.0.0`, and `--check` seconds later, against an untouched directory and an unmoved contract, bumped to `1.0.1` and reported `README.md` as drift, exit 5. | The number moves only when `classify_changes` is **non-empty**; an unchanged contract keeps the version it had. That is what ADR 0204 already said in words — *"a client regenerated from an unchanged contract does not move"* — and the code now says it too. Proved by generating three times and checking between each, plus a control: one appended comment in `types.ts` is caught, exit 5, naming that file. | The plan's sentence was right about the mechanism and wrong about the empty case, and the empty case is the one that happens on every run. A drift check that fails on an unmodified artefact is worse than no drift check: it is turned off in a week, and then the real drift is not caught either. Found in five seconds by running the command twice — which is the whole argument for `--check` being exercised by a proof that calls the product's own command (D1114). | 0204 |
| **D1225** | Run 3 step 3's `entrypoint.sh`, as planned: *"`cd /work && npx tsc -p tsconfig.json --noEmit`"*. | **`npx` can reach the registry.** It resolves from the working directory first, and finding nothing there — which is exactly the case, since a generated client declares no dependency and has no `node_modules` — it **fetches the package**. So the entrypoint as written would have made every typecheck a silent network call, passing on any machine that happened to be online and failing in a gate with no route out. The same call also has nowhere to find `@types/node`: the emitted `tsconfig.json` declares `types: ["node"]`, and TypeScript resolves that by walking up from the tsconfig's directory, which is the read-only mount. | The compiler is addressed as `/app/node_modules/.bin/tsc`, the path **in this image**, and `@types` is supplied with `--typeRoots /app/node_modules/@types` rather than by installing anything into the directory under test. `test_the_entrypoint_addresses_the_compiler_by_path_and_never_through_npx` asserts the mechanism and `test_the_toolchain_typechecks_with_no_network_at_all` proves the result — `docker run --network none` exits 0. | A toolchain image exists so that a check is reproducible and offline; one word in its entrypoint gave both away, and nothing about the output would have shown it. The second half is worth as much: a toolchain that fixed the `@types` problem by writing a `node_modules` into the directory it was handed would dirty a developer's checkout, and the dirt would appear in their `git status` after a command that only claimed to read. | 0204 |
| **D1226** | The emitted package's import specifiers, written `./client.js` — the TypeScript convention under `moduleResolution: nodenext`, and what `tsc` accepts. | **It typechecks and it cannot RUN.** That convention is for a package that is COMPILED, where the emitted JavaScript sits beside the source. This package is never compiled — `noEmit`, executed directly by the pinned Node's type stripping (D1204) — so at runtime `./client.js` does not exist. Measured: `tsc` exit **0**, then `node smoke.ts` dead with `ERR_MODULE_NOT_FOUND: Cannot find module '/work/client.js'`. | Specifiers name the files that exist (`./client.ts`), and the emitted `tsconfig.json` gains `allowImportingTsExtensions` — which `tsc` only accepts alongside `noEmit`, the setting this package already had for the same underlying reason. Eight specifiers across three emitted files. Now measured both ways: typecheck exit 0, and `node smoke.ts` runs, refusing cleanly with exit 2 on a missing environment and exit 1 reporting `unreachable`. | **D1223 one layer out, and it is the more interesting half.** That one said a generator's output has a compiler and not running it declines the only total check available. This says the compiler is not the last word either: a package can satisfy the type checker and still not load. The check that found it was executing the artefact, which is what Run 4 exists to do — and it was cheaper to find here. | 0204 |
| **D1227** | Run 3's first pair of toolchain proofs, written in `test_client_typescript.py`: they installed `typescript` and `@types/node` from the npm registry **inside the test**, then typechecked. | **They were green, and they could not have run in the gate that will report them.** `generated_client_toolchain` is DECLARED an offline claim (`OFFLINE_CLAIMS`, ADR 0202), and a proof that reaches `registry.npmjs.org` needs the network the offline mode is defined by not having. On this very workstation WSL cannot reach HTTPS at all — the proofs passed only because Docker's containers still can. | Both moved to `tests/contract/test_generated_client_toolchain.py`, against the hash-locked image, and `run_toolchain` passes `--network none` by DEFAULT rather than as an option a later test can forget. They are not duplicated in the old module: two proofs of one fact, where one is weaker, is the arrangement in which the weaker one is the one that stays green. | A declared offline claim whose proof needs the internet is the strongest form of *a value that looked measured and was not* — it would have passed every run on this machine and failed the first time somebody ran the gate on an air-gapped host, which is precisely the case the offline mode was built for (ADR 0202). Nothing in the tree checks that an offline claim's proofs are offline; `--network none` in the runner is the closest thing to one. | 0202 |
| **D1228** | The toolchain entrypoint's input check: `[ -f /work/tsconfig.json ]`, and the refusal *"there is no generated client to check"*. | **An UNREADABLE directory is not an absent one, and the test was false for both.** The image runs as 65532; pytest's `tmp_path` is `0700` owned by the invoking user, so a mount of it is perfectly present and simply cannot be read — and every `[ -f … ]` inside answers false. Measured with a control: the same directory at `0755` typechecks, at `0700` the image said *"tsconfig.json is not there"* and exited 2. Two of this module's proofs failed that way before the cause was found. | A third answer, before the file tests: an unreadable `/work` exits **3** and says which uid the image runs as and what the directory needs, explicitly ending *"This is NOT 'no client here'"*. `test_an_unreadable_mount_is_reported_as_unreadable_and_never_as_absent` asserts the code, the message, and — the control — that the same bytes at `0755` typecheck. | **ADR 0195's class, in a component built the same day by someone who had just written the ADR's number into three other files.** Reported as absence it sends a developer to regenerate a client already sitting in front of them. The reason it was found is that the failure happened to be *mine*, in a test; had the first person to hit it been an adopter with an unusual umask, the message would have sent them the wrong way and the tests would all have been green. | 0195 |
| **D1229** | The generated client's `normalizeServed`, and `openapi_normalize._refuse_residue` it mirrors: after substituting `host` and `basePath` with the sentinels, refuse if either real value *survives anywhere* in the document. | **A `basePath` of `/` occurs in every OpenAPI document, so the check refuses every document.** Every path key begins with one, so the substring test always matches. Measured in rig 23g: PostgREST configured with a proxy URI of `http://arm-b:3000/` served a document whose fingerprint was **exactly** the committed snapshot's (`808ac715c09aeebc`), and the client refused it with *"the document still names / after substitution, so the normalized form would not be project-neutral"*. | The client checks residue on the **trailing-slash-stripped** base path and skips it when empty — there is nothing distinctive to look for — and gains the capture's **bare-hostname** clause, which it was missing. Measured after the change: production's shape still `ok`, so the added clause refuses nothing real. **`openapi_normalize` is NOT changed**: it carries the same clause and cannot reach it, because `project.schema.json`'s `public_base_path` pattern (`^/[^/].*[^/]$\|^/[^/]$`) forbids a bare `/`. | The interesting half is which copy was worth repairing. In the capture the condition is unreachable and the module is released; in the client it is reachable by whoever holds the package, because a client is copied and pointed at things its author never saw. Same clause, two reachability answers, two decisions. | 0204 |
| **D1230** | Run 4's rig, as planned: PostgREST beside `apg dev`, the client pointed at its published port. No edge. | **That rig cannot reproduce the shape any adopter has.** Production serves `basePath: /api/rest` because Traefik strips that prefix before PostgREST, and PostgREST has no path-prefix option of its own. Measured across rigs 23g and 23h: the client pointed at PostgREST's root is refused — correctly — with *"the document's basePath /api/rest is not the path of http://postgrest:3000"*; pointed at the prefix it gets a **404**. So the planned rig could only ever have tested a base path no deployment publishes. | The rig runs the **pinned Traefik** with a `stripPrefix` middleware over the project's own `API_REST_PATH`, which is what the deployment does — a rig as a second configuration of the product (ADR 0065/0066), not a different thing. Through it: `init` → `ok`, a typed read → `ok`, the write → `refused` `PT401`. The direct-at-the-root arm is kept as the **control**, because a pass through the edge has to be a pass *because of* the edge. | A rig that omits the edge is a proof by a route the product does not take (ADR 0065/0066) — and the omission is invisible, because the client's refusal at the root looks like a client defect rather than a missing component. Rig 23a did not meet this: it normalized with `expected_base_path=served["basePath"]`, taking the served value as the expected one, so it never exercised the assertion at all. | 0204 |
| **D1231** | Run 4's rig, as planned: *"drop `PGRST_JWT_SECRET` (the rig has no key set) and record in the docstring that role selection is therefore by `PGRST_DB_ANON_ROLE`"*. | **Every request then answers 500.** The generated client ALWAYS sends `Authorization: Bearer` — reading the surface *as the caller* is the whole of ADR 0204 — and PostgREST with no JWT configuration cannot verify a token it was given. Measured in rig 23g: all four arms returned `{"kind":"unreachable","reason":"the service answered 500"}` before the secret existed. Rig 23a never met it because it sent no Authorization header. | The rig generates an HS256 secret, sets `PGRST_JWT_SECRET`, and mints its own tokens naming a **role and no subject** — `bin/dev-token.py`'s documented property, since migration 0013's hook returns early without a `sub`. That is also what makes the two proofs honest: the read succeeds and returns **0 rows** because no `app.user_id` is set, and the write is refused with a real `PT401` for want of an identity. The role now comes from the token rather than from `PGRST_DB_ANON_ROLE`, which is how a deployment selects it. | `PGRST_DB_ANON_ROLE` was the right mechanism for rig 23a, which fetched a document anonymously, and the wrong one the moment the *client* became the instrument. A rig inherits its predecessor's configuration far more readily than its predecessor's reason for it. | 0204 |
| **D1232** | Run 4's `GEN-TYPES-001` proof of the query string, as planned: *"the smoke prints the URL it built, asserted to be `…/notes?select=id,title&order=created_at.desc&limit=5&title=eq.x` after decoding"*. | **The client does not expose the URL it built, and adding that only for a test would be a backdoor.** The deeper problem is that the assertion would compare the client against a string this session wrote — it could not tell a correctly built query from an incorrectly built one that the test was updated to match. | Proved **through the service instead**. The smoke gains an optional `APG_SMOKE_FILTER_VALUE`, and the proof sends `probe&select=no_such_column`: percent-encoded it is an ordinary filter matching nothing (**200**), concatenated it becomes a second query parameter naming a column the relation does not have (**400**). Two outcomes far apart, neither a coincidence, and PostgREST is the judge rather than a literal in the test. The unfiltered read in the same invocation is the control. | ADR 0127 — *a caller value is a value and never syntax* — is one of this product's central claims, and the planned proof would have asserted it against a string rather than against a parser. The battery's `encodeURIComponent` mutation is what says the difference is real. | 0127 |
| **D1233** | Run 4's rig wrote the authenticator's pgpass at `0600` under `tmp_path` and bind-mounted it into PostgREST. Seven proofs green on this workstation. | **CI RED on the first push.** `fe_sendauth: no password supplied`, surfacing 90 seconds later as *"PostgREST never loaded its schema cache"*. The cause: the PostgREST image declares `User=1000` (`docker inspect --format '{{.Config.User}}'`), and libpq **ignores a passfile looser than 0600** — so the file must be `0600` **and** owned by uid 1000. On this workstation the author's uid is *also* 1000, so it was readable **by coincidence**; the CI runner is uid **1001** and the container could not open it. Reproduced locally with a control: the same file at uid 1000 reads, at uid 1001 gives `Permission denied`. | The uid is read from the image (`image_user`) rather than assumed, and the file is given that owner through a **root container** on a pinned image — a test process cannot `chown` to an arbitrary uid, and the looser mode that would avoid the question is the one libpq refuses. And the fixture now **reads the file as that user before waiting on anything**, so the failure names a permission rather than timing out on a schema cache. | **D1228, two runs earlier, was the same fact in the same session**: a file the author can read and the container's user cannot. That one was a directory at `0700` and this one a file at `0600`; both were found by a container refusing to see something that was plainly there, and the first did not generalise into a habit. The tell both times was a message about the *content* — "no client here", "no password supplied" — where the truth was about *access*. **A rig that passes because the author's uid happens to match the image's is a value that looks measured and is not** (§7), and the only thing that distinguishes it from a correct one is a machine nobody has run it on yet. | 0204 |
| **D1234** | Run 5's envelope rows were to be *"`apg generate` wall time for the release contract (5 objects, 6 tools) and for the example project's (7 objects, 8 tools)"*. | The example project's contract compiles to **7 tools, not 8** — measured by generating both in rig 23g and counting the IR: release `relations=2 rpcs=3 tools=6` (5 objects), example `relations=3 rpcs=4 tools=7` (7 objects). The release's six plus the project's one (`set_note_embedding`) is seven, which is also the number beta serves live and has since Session 21. | The rows name what was counted. The second row's subject reads *"a project's contract, 7 objects and 7 tools"* and its conditions carry the relation, RPC and tool counts and the emitted byte count, so a re-measurement that changes the shape cannot inherit a stale size. | A number in a plan is a guess until a run counts it, and this one was about to be written into a **published capacity document** — the class of artefact §7 calls most at risk of being reported dishonestly, because a document goes green by existing. The counting cost one line of the rig. | 0204 |
| **D1235** | Run 5 step 1: *"`test_printed_commands` scans the new prints"*. | **It could not have.** `tests/contract/test_printed_commands.py` read exactly one file — `bin/deploy-project.py` — and D975's rule has been enforced on that driver alone since Session 17. The two commands that gained a printed command in this run are `bin/api-contract.py` and `bin/mcp-contract.py`, and a placeholder in either would have been invisible to the guard the plan named as its reader. | The scan is widened to a `PRINTING_DRIVERS` map of the three drivers that actually print a command, with the rule and every assertion unchanged — a widening to a measured set, which the non-negotiables distinguish from loosening a check to a subset. A second proof asserts the shape the scan cannot: that `--project` is followed by an interpolation and not a literal, in each of the two. The battery applied the placeholder mutation against both, separately, and both killed. | The plan named a guard as the reader of a new print without checking what that guard reads — question 5's shape (*when a decision is implemented, which of its callers got it?*) turned around: **when a rule is relied on, which files does it actually cover?** A rule enforced on one file for six sessions reads, from a plan, as a rule about the repository. | — |
| **D1236** | §2's `GEN-EMIT-001` states that *"the emitted `RestError` union is the PT-code vocabulary and the `AgentRefusal` union is the seven tokens"* and that *"a write wrapper requires `idempotency_key` and `dry_run`"*. | **Nothing asserted either.** `grep -n 'AgentRefusal\|PtCode' tests/contract/test_client_typescript.py` and the same for `idempotency_key` each returned zero lines. The emitter does both correctly — measured in the committed `types.ts` and `agent.ts` — and the proofs that existed (`test_the_caller_facing_tokens_match_the_runtimes`, `test_the_reserved_write_parameters_match_the_harnesss`) are about what the **IR** carries. Between the IR and the file is an emitter, and a union written from a hard-coded list would satisfy every IR-side proof. | Two proofs written BEFORE the requirement was registered: `test_the_error_unions_are_the_pt_codes_and_the_seven_tokens` asserts exact equality in both directions (a superset is the failure, and a containment check passes on one), and `test_a_write_wrapper_requires_the_two_reserved_parameters` reads the roster from the IR and refuses an optional `?` on either parameter. | **D816/D929 one level up.** A declared field with no reader is an unverified field; a registered requirement CLAUSE with no proof is an unverified claim, and it goes into an acceptance matrix and a verdict. The cost of finding it was one grep, run because Run 6's own instruction is to write *what the runs actually wrote* rather than what the plan proposed — and four of the nine requirements' node ids had drifted from the plan's guesses, which is what made reading each one necessary. | 0204 |
| **D1237** | The plan's targeted list says `test_session_twenty_two_gate_modes` *"must still pass"* unchanged. | **It could not.** Its `test_exactly_the_four_declared_claims_are_offline` asserts `set(claims.OFFLINE_CLAIMS) == set(SESSION_TWENTY_TWO_CLAIMS["offline"])` — an equality against the WHOLE declared set. That was correct while Session 22's four were the only offline claims in the project, and on the day a second session declared any it became a rule that **no later session may ever have an offline claim**. It failed at the earliest moment it could, which is a whole session after it was written. | Narrowed in both modules to what each is about. Session 22's asserts its own four are declared and neither of its host claims is; Session 23's asserts, by SUBTRACTION against `CLAIM_INTRODUCED_IN`, that `OFFLINE_CLAIMS` less every earlier session's claims is exactly this session's two — so a third arriving without anybody deciding to still fails. Neither assertion was weakened: both got stricter about their own scope. | **A scope too wide reads as correct for exactly as long as nothing else exists.** The assertion was not wrong about Session 22; it was stated one level up from the property it was about, and nothing in the tree could tell the difference until a second instance existed. The same shape as §7's *a premise wrong in the reassuring direction survives longest* — and the thing that found it was not a review but a second session simply happening. | 0202 |
| **D1238** | Run 6 step 1 moves `VERSION` 1.3.0 → 1.4.0. The plan's step 1 lists what the bump prices and stops there. | **The bump breaks `apg generate --check`.** `contract.ts` carries `templateVersion`, so the committed example client stopped being what its contract generates the instant the constant moved — exit 5, on a file nobody had touched, with the gate's step 6 and CI's new step both refusing it. | The client is regenerated in the same commit as the bump. The version rule behaved **correctly** and that is the part worth recording: `generate` reported *no contract change*, so `clientVersion` stayed `1.0.0` and all four digests are byte-identical — only the provenance line moved. D1224's rule earns its keep here, because the naive rule would have published `1.0.1` and told every adopter the contract had moved. | **Every release bump from now on owes a regeneration in the same commit**, and this is the first session in which a release constant reaches a committed ARTEFACT rather than only a rendered document. Recorded in the ledger's §12 rather than only here, because the next person to move `VERSION` is not reading this plan. | 0162 |
| **D1239** | Run 6 step 7: *"`bin/session-01-check.sh` once on the clean tree (a session close is one of the cases the working agreement allows)"*. | **It cannot complete on this workstation.** Step 2 runs `bin/lock-dev-deps.sh --check`, which resolves `requirements-dev.in` against PyPI, and **WSL here has no outbound HTTPS** — measured again at this step, not recalled: `getent` resolves `pypi.org` to `151.101.64.223`, `curl -m 20` exits **28** after 20.00 s, and the *same request from a container* answers **http 200 in 2.8 s**. The gate died at step 2 with exit 2, having passed step 1 clean and shellcheck and ruff inside step 2. | The one question the gate could not ask was asked **with the gate's own command**, in the pinned `PYTHON_RUNTIME_IMAGE` with the checkout mounted — Run 3's workaround for the same fact. First attempt exit **3**: *"uv version mismatch: found 0.12.13, this repository pins 0.12.1"*, which is the command being right rather than a failure. With `uv==0.12.1` installed: *"requirements-dev.txt is current at cutoff 2026-09-03T15:16:21Z"*, **exit 0**. Everything else the gate would have run was run directly: `ruff check` exit 0, `shellcheck` exit 0 on the new gate, and 1099 targeted proofs across 17 modules. **CI is the full check** (`CLAUDE.md` §2) and runs on a machine with network. | The gate cannot be run here, and **the session close needs it** — which is a Run 7 problem and not a Run 6 one, because `bin/session-23-check.sh --mode offline` runs `bin/lock-versions.sh --check` and NOT `lock-dev-deps`, and that one is offline by construction (no registry, no credentials). So the close is not blocked; only this step is. What is worth carrying is the shape of the answer: **a command that cannot run in one environment is still the command, and running it somewhere it can is not the same as running something else.** The alternative — invoking the gate's individual steps by hand and calling that a gate — is the route D1114/D1117 refuses. | — |
| **D1240** | Runs 2, 3 and 5 wrote `test_client_ir.py`, `test_client_typescript.py`, `test_generate_command.py` and `test_generated_client_toolchain.py`, ran them targeted, and read each commit's CI verdict green. | **None of those four modules carried a `pytestmark` at all**, so no marker-selected sweep has ever collected one of them. CI went RED the first time this run registered their requirements: `write-session-evidence: these claims are not proved by this run: ['generated_client', 'generated_client_toolchain']`, with **no result recorded** for all forty-odd node ids. Measured with a control before repairing: `--collect-only -m "contract and not future"` (the Session 1 gate's own selector) and `-m "p0 and not future and not live_host and not external"` (CI's Session 2 job) each collect **0** from the four, while collecting **7** from `test_generated_client_runtime`, which is marked. ~50 proofs, green on four commits, run only when a person named the file. | Each module gains `pytestmark = [pytest.mark.contract, pytest.mark.p0]` with the reason beside it. And the class is guarded: `test_every_offline_claims_proof_is_swept_by_the_gate_that_reports_it` collects with the gate's OWN selector and asserts every registered proof of a DECLARED OFFLINE claim is in it. Battery: the mark removed from each of two modules, both killed, and **the control both times is `test_every_registered_node_id_is_collectible`, which stayed green** — the test that was green through the entire defect. | **Collectible and collected are different questions, and this repository had only ever asked the first.** `test_acceptance_registry` verified every node id exists — a real property, which catches a renamed or mistyped test — and a verdict is computed from the JUnit of a run that SELECTED BY MARKER. An unmarked module satisfies the first and is invisible to the second. It is §7's second question (*has it run at all, in this environment?*) with a new answer: `--setup-plan` says whether a proof WILL run **given a selection**, and nothing asked whether the selection reaches it. Also note what did NOT find this: four CI runs, five mutation batteries whose own `-k` named the files, and a registry guard written for exactly this family. **What found it was registering the requirement** — the evidence writer is the only reader in the tree that consumes a marker-selected JUnit and says which ids are missing from it. Four more modules have the same shape and are NOT this session's: `test_database_function_signatures`, `test_storage_client`, `test_storage_endpoint`, `test_storage_endpoints`, each collecting 0 by the same selector, measured. None belongs to a declared offline claim, so the new guard is silent about them; they are recorded in the ledger's §12 for a session that owns them. | — |
| **D1241** | With D1240 repaired, the Session 1 gate went green and **the Session 2 offline contract job went red** — on a proof that had just entered a sweep for the first time. | `test_a_project_declaring_no_set_generates_the_releases_client` runs `apg generate --project project.second.example.yaml`, and got **exit 4**: *"fixture-alpine-dev has not been rendered in this checkout. Render it first."* CI's `session-2-contract` job renders **one** fixture; `bin/session-01-check.sh` step 3 is named *"Render both fixtures"* and renders two — which is why the gate job passed the same push. On this workstation `.generated/fixture-alpine-dev` survives from the last gate run, so the dependency never showed. | CI's render step renders both, with the reason in a comment beside D877's. | **D877's fact, applied to a different axis.** Its comment sits three lines above this edit and says *"on a developer machine `.generated/` survives from the last gate run, so the ordering never showed; on a fresh runner it produced 88 errors"* — that was about the ORDER of the render, this is about WHICH FIXTURE. And the command behaved correctly throughout: it refused with exit 4 naming the render command, which is ADR 0195's third answer working. What makes the row worth writing is **when** it was found: this proof was written in Run 3, passed locally four times, and could not fail on a fresh machine until D1240 put it in a sweep at all. A proof outside every selection cannot report the environment it depends on. | — |
| **D1242** | Run 6's D1240 repair: a guard that *"collects with the gate's own selector and asserts that every registered proof of a declared offline claim is in that collection"*, and Run 7 step 1 expecting the offline half's two claims `passed`. | **The gate exited 5.** `generated_client` came back **`not_run`**: *"no result recorded for `tests/contract/test_printed_commands.py::test_the_generate_hook_prints_the_path_the_process_was_given`"* — D1240's own shape, one level deeper. That module is marked `contract, p1`. The guard collects with **`contract and not future`**, the Session 1 gate's selector, and reaches it. The sweep that **reports an offline claim** is `session-23-check.sh --mode offline` step 3, which selects **`p0 and not future and not live_host and not external`** — and does not. Measured both ways: the module contributes **4** node ids to the first collection and **0** to the second. A registry-wide scan says this is the **only** such node in 202 entries: no other P0 requirement is proved in a module the P0 sweep does not select. (Three further misses the first reader printed were its own artefact — parametrized ids it did not strip; those claims passed.) | The proof of a P0 requirement gains a function-level `@pytest.mark.p0` (the module's other three stay `p1`; a function mark composes). The guard's selector becomes `OFFLINE_SWEEP_SELECTOR`, set to the **offline gate's**, and a new `test_the_offline_sweep_selector_is_the_newest_gates` reads the newest `bin/session-*-check.sh` and asserts the string appears in it verbatim (D486). Battery 3/3 killed, control `test_every_registered_node_id_is_collectible` green throughout. | **The guard was right about the class and wrong about which gate, and the wrong answer was green.** Both strings are real selectors collecting thousands of tests; the docstring I wrote for D1240 *names both of them in one sentence* and then copied the one that does not report this claim. Mutation M2 is the demonstration: with the selector set back to `contract and not future` the offline guard **passes** and only the drift test fails. D1240 said collectible and collected are different questions; this says **collected by WHICH sweep** is a third, and the only reader that can answer it is the one whose JUnit the claim is computed from. Found, again, by running the thing to completion rather than by any check standing in for it. | — |

---
## 2. What the session adds to `tests/acceptance-registry.yaml`

Family `GEN-*` (new; joins `ID_PATTERN` in
`tests/contract/test_acceptance_registry.py:39` with its reason — *a
GENERATED artefact: what the product writes for a developer to hold, as
opposed to what it serves*), `AGT-*` extended. All P0, `target_session: 23`.
Every requirement belongs to a claim (D697); **a new requirement gets a claim
of its own and is never joined into an older one** (D1150, ADR 0089). Node
ids are proposed; the runs settle the names, and Run 6 writes what the runs
actually wrote.

| Requirement | What it states | Offline node ids (proposed) | Live half |
|---|---|---|---|
| `GEN-IR-001` | `client_ir.build(...)` reads exactly the merged reviewed surface, the project's (or the release's) PostgREST snapshot, the application snapshot and the project's compiled lock; it carries every relation with the surface's columns and the snapshot's types, every reviewed RPC with its argument schema, the three authentication operations, every tool of the lock with its arguments and scopes, the enum vocabulary in `enumsortorder`, the capability schema's filter operators, the PT codes the release and the project's set raise, the seven caller-facing tokens, and four digests; it refuses a snapshot object the surface does not name and a surface object the snapshot does not publish; it is deterministic (two builds are equal); no input outside `contracts/`, `projects/<slug>/contracts/`, the project manifest and the rendered document is read | `test_client_ir.py::test_the_ir_is_built_from_the_four_inputs_and_nothing_else`, `::test_relations_carry_the_surfaces_columns_and_the_snapshots_types`, `::test_rpcs_carry_the_snapshots_argument_schema_in_parameter_order`, `::test_the_lock_tools_carry_arguments_scopes_and_the_reserved_write_parameters`, `::test_a_snapshot_object_the_surface_does_not_name_is_refused_and_vice_versa`, `::test_the_pt_codes_are_scanned_from_the_release_and_the_set`, `::test_the_caller_facing_tokens_match_the_runtimes`, `::test_two_builds_are_equal` | — (offline claim) |
| `GEN-EMIT-001` | The TypeScript emitter reads the IR and nothing else (AST: imports `client_ir` and the standard library; no path under `contracts/` or `projects/` in its source); the emitted package has no runtime dependency and one devDependency (`typescript` at `TYPESCRIPT_VERSION`); no emitted file contains a credential, a token, a password, a signing key or a URL carrying userinfo; every emitted call names an operation, tool, column or argument the IR carries and no other; the filter operators offered are the capability schema's; a write wrapper requires `idempotency_key` and `dry_run`; the emitted `RestError` union is the PT-code vocabulary and the `AgentRefusal` union is the seven tokens | `test_client_typescript.py::test_the_emitter_reads_the_ir_and_no_contract`, `::test_the_package_declares_no_runtime_dependency_and_the_pinned_typescript`, `::test_no_emitted_file_carries_a_credential_a_token_or_a_userinfo_url`, `::test_every_emitted_operation_and_column_is_in_the_ir`, `::test_the_filter_operators_are_the_capability_schemas`, `::test_a_write_wrapper_requires_the_two_reserved_parameters`, `::test_the_error_unions_are_the_pt_codes_and_the_seven_tokens`, `::test_the_example_client_is_the_emitters_output_byte_for_byte` | — |
| `GEN-HASH-001` | `init()` fetches the served REST OpenAPI document as the caller, normalizes it (basePath asserted, host and schemes substituted, residue refused), fingerprints it in the JavaScript canonical form, and compares to the embedded digest; a mismatch refuses every later call with `stale_contract` naming both digests; an unreachable service is `unreachable` and an unparsable document `unreadable`; the agent wrapper's `listResources()` compares the plane's reported `lock.tools_sha256` to the embedded one and reports `unconfirmable` on `null`; the generated example client accepts the served surface of the deployment it was generated for and refuses the other project's | `test_generated_client_runtime.py::test_init_accepts_the_served_surface_it_was_generated_from`, `::test_init_refuses_a_surface_with_another_fingerprint_naming_both`, `::test_init_reports_unreachable_and_unreadable_as_two_different_answers`, `test_client_typescript.py::test_list_resources_compares_the_reported_lock_digest_and_reports_null_as_unconfirmable` (recorded SSE bodies) | `test_session23_client.py::test_the_example_client_initialises_on_beta_and_refuses_alpha` (Session 24's trip) |
| `GEN-TYPES-001` | Through the generated client against a served surface: a typed relation read returns rows of the declared shape; an RPC write refused by the product arrives as `RestError{kind: refused, code}` with the PT code the database raised (PT401 without an identity), and never as a thrown transport error; a request the client cannot express cannot be sent (no `select` outside the columns, no operator outside the set) | `test_generated_client_runtime.py::test_a_typed_read_returns_rows_of_the_declared_shape`, `::test_a_refused_write_arrives_as_the_pt_code_the_database_raised`, `test_client_typescript.py::test_a_request_names_only_reviewed_columns_operators_and_arguments` | — |
| `GEN-VERSION-001` | `classify_changes` returns only names in `compatibility.CHANGE_CLASSES`; an added operation or tool is `api_operation_added`/`capability_added`, a removed one `api_operation_removed`, a changed argument list, column type, enum set or scope set `api_operation_changed`, and an unchanged IR is empty; the package version is the previous one bumped by `compatibility.required_level` and `1.0.0` for a first generation; `generate --check` exits 5 naming the first differing file when the committed client is not a fresh generation, and 0 when it is | `test_client_ir.py::test_classify_changes_emits_only_adr_0162_classes`, `::test_an_added_operation_is_minor_and_a_removed_one_is_major_by_the_releases_rule`, `::test_an_unchanged_ir_bumps_nothing`, `test_generate_command.py::test_check_refuses_a_stale_client_and_names_the_file`, `::test_check_accepts_the_committed_example_client` | — |
| `GEN-TOOLCHAIN-001` | The toolchain image builds from the pinned Node image with `typescript` pinned by `package-lock.json` (every entry with an integrity hash, `npm ci --ignore-scripts`) at the version `versions.env` records; the emitted `canonical.ts` produces, for every committed REST and MCP snapshot in the tree, the digest `openapi_normalize.fingerprint` produces; `js_reproducible` refuses a document carrying a float or an integer beyond 2^53 and names the pointer; the generated example client typechecks under `--strict`; CI typechecks and smokes it | `test_generated_client_toolchain.py::test_the_image_pins_node_and_typescript_and_the_lock_carries_integrity_hashes`, `::test_canonical_ts_reproduces_pythons_fingerprint_for_every_committed_snapshot`, `::test_js_reproducible_refuses_a_float_and_a_big_integer_and_accepts_every_rest_snapshot`, `::test_the_example_client_typechecks_strict`, `test_client_typescript.py::test_ci_typechecks_and_smokes_the_example_client` | — |
| `GEN-CMD-001` | `bin/generate.sh` is a verb of the dispatcher; argument errors exit 2 before any file is read; an unrendered project is refused with exit 4 naming the render command; a project declaring no set generates the release's client; `--out` outside the checkout is refused; `--check` writes nothing; nothing the command prints is a credential; the capture and the compile print the generate command as the next step | `test_generate_command.py::test_generate_is_a_verb_of_the_dispatcher`, `::test_argument_errors_exit_two_before_anything_is_read`, `::test_an_unrendered_project_is_refused_with_exit_four_and_the_render_command`, `::test_a_project_with_no_set_generates_the_releases_client`, `::test_check_writes_nothing`, `::test_the_capture_and_the_compile_print_the_next_step`, `test_cli_contract.py::test_commands_are_executable_in_the_git_index` | — |
| `GEN-ENV-001` | The capacity envelope carries the generator's wall time for the release contract and for the example project's as `MACHINE` measurements naming the machine, with the contract sizes as conditions; the document is current | `test_capacity_envelope.py::test_the_envelope_carries_generation_time_per_contract_size`, `::test_the_envelope_is_current` | — |
| `AGT-META-001` | `list_resources` reports, beside the roster, the digest and count of the lock the running process loaded (`lock.tools_sha256`, `lock.tool_count`); the digest is the one the lock carried, `null` below lock schema 4, never recomputed; the field is served on a deployment and equals the deployed document's confirmed value | `test_mcp_tools.py::test_list_resources_reports_the_loaded_locks_digest_and_count`, `::test_list_resources_reports_null_for_a_lock_below_schema_four` | `test_session23_client.py::test_list_resources_on_beta_reports_the_lock_the_plane_confirmed` (Session 24's trip) |

**Claims** (`src/agentic_postgres/evidence_claims.py`), each dated 23:
`generated_client: ("GEN-IR-001", "GEN-EMIT-001", "GEN-TYPES-001", "GEN-VERSION-001", "GEN-CMD-001")`,
`generated_client_toolchain: ("GEN-TOOLCHAIN-001", "GEN-ENV-001")` — both in
`OFFLINE_CLAIMS` (every proof runs in a checkout, with Docker; a skip is not
a pass, the gate refuses an absent daemon exactly as Session 22's does);
`generated_client_hash: ("GEN-HASH-001",)` and
`agent_lock_reported: ("AGT-META-001",)` are **host** claims, deliberately
not declared offline: each has one live proof on beta with alpha as the
control, and a checkout cannot answer whether a deployment serves the
surface a client was generated for. They are `not_run` at this session's
close and Session 24's trip collects them (§7, §10).

**No new gate variable.** The two live halves read `APG_LIVE_HOST`,
`APG_PROJECT_A_OUTPUTS`, `APG_PROJECT_B_OUTPUTS`, and — for the agent half —
`APG_ADMIN_PASSWORD_FILE` (agent creation as Session 22's module does it).
The human token for `init()` comes from the suite's `owner_session` fixture
(`tests/deployment/conftest.py:1744`), never minted by the test.

---

## 4. Irreversible operations

| Operation | Where | What makes it safe |
|---|---|---|
| `list_resources`' result gains a `lock` member | Run 2 | Additive; every existing key unchanged; readers grepped (`git grep -n "list_resources" -- tests services src bin docs`) and every module found run whole; the catalog regenerated; the evaluation report unchanged (cases read scope sets) |
| `versions.in.yaml` gains `TYPESCRIPT_VERSION`; `versions.env` re-locked | Run 3 | `--update --packages-only` carries every image digest forward unchanged (D238); the diff is asserted to touch the new package's two lines and `APG_VERSIONS_IN_SHA256`/`APG_LOCKED_AT` only |
| `services/clients/typescript/` and its `package-lock.json` | Run 3 | Built by `npm ci` from a lock every entry of which carries an integrity hash; runs nothing from the internet after the build; listed in `test_repository_contract.py`'s tracked-file list |
| `projects/example/clients/typescript/` committed | Run 3 | The emitter's output byte for byte, asserted by a test and by `generate --check` in the gate; regenerated whenever the example contract moves, and the diff is the review |
| `api-contract.py` and `mcp-contract.py` print one more line | Run 5 | stderr only; the captured document on stdout is unchanged (`test_api_contract_command`); `test_printed_commands` scans the new line |
| `CURRENT_SESSION` 22 → 23 | Run 6 | All-or-nothing (D690); every `target_session: 23` requirement has its proofs in the same commit; the two live halves are collected under `--setup-plan` with the variables set |
| `VERSION` 1.3.0 → 1.4.0 | Run 6 | Proposed: a new command, an optional `projects/<slug>/clients/` directory, one additive tool-result member, a new fixture image; no manifest, outputs, capability, lock or secret schema moves; a minor, confirmed by Session 24's `upgrade plan` (§9) |
| `ci.yml` gains the client typecheck and smoke | Run 6 | Runs after the render and the `apg dev` round trip the job already does; a failure is a red push |
| Merge of `session-23` into `main` | Run 7 | Fast-forward only, after CI is green on the branch's last commit |

Not irreversible and worth saying: every rig removes its containers with
`docker rm -f -v`; `apg dev down` is run in `finally`; the toolchain image
is tagged `apg-client-typescript:<versions.env digest>` and left in the
daemon's cache like the probe images are.

---

## 5. Build order, run by run

Each run ends with: ruff (its **exit code** printed), the targeted modules
(named, each checked for existence individually — D1104), derived documents
regenerated where a generator's input moved, `chmod 755 bin/*.sh bin/*.py
deploy.sh`, one commit on the `session-23` branch with a message file, a
push, and **that commit's CI verdict read** by full SHA with three buckets
(D1059). A run that writes a test runs its battery (appendix). Mark the run
**Done.** here with what it measured. **A targeted list is derived from the
tree** (D1146, D1149, D1184, D1187): a run that moves a definition greps
every reader of the name AND of the distinctive text
(`git grep -n <name> -- tests bin src services docs`) and runs every module
found, whole. A red CI on the branch is a stop condition.

**Docker is required for Runs 1, 3, 4, 6 and 7** (the rigs, the toolchain
image, the runtime proof, the gate). If `docker version` fails in WSL, stop
and say so; do not write a proof that skips.

**Network is required once**, in Run 3, to lock `typescript`
(`registry.npmjs.org`, twice: `lock-versions.sh --update --packages-only`
and `npm install --package-lock-only` inside the Node image). If WSL has lost
outbound HTTPS (`CLAUDE.md` §1's note; `wsl --shutdown` after copying `/tmp`
scripts to the scratchpad), do that step from a shell that has it and record
which.

### Run 1 — the measurements and ADR 0204

**Rigs** (scripts written with the Write tool to `\\wsl$\Ubuntu\tmp\`, run
with `wsl bash -lc "bash /tmp/r23X.sh > /tmp/r23X.txt 2>&1"` and the file
read back; every number pasted into the Done paragraph; each names its
control; each removes every container, volume and file it created). **23a
and 23b already exist** — `/tmp/r23a.py`, `/tmp/r23b.sh`, `/tmp/r23b2.sh` in
WSL from planning day, with outputs beside them; copy them to the scratchpad
before anything shuts WSL down. Re-run both first: their job in Run 1 is to
confirm the tree at the branch point still measures what §1 says.

- **23a, the served surface per role** (`/tmp/r23a.py`; runs in the venv
  with `sys.path` set to `src`). Expect: `apg dev up` exit 0, 33 migrations;
  `ALTER ROLE <postgrest_authenticator> LOGIN PASSWORD` as the superuser
  through `docker exec` exit 0; three PostgREST containers on the pinned
  image with `compose.yaml`'s `postgrest.environment` values and
  `PGRST_DB_ANON_ROLE` set to each role; `GET /` with `Accept:
  application/openapi+json` → 200 for all three; normalized fingerprints
  **`authenticated` = `api_documentation` = the project snapshot's**
  (`808ac715c09aeebc…` at `d6f6e94`; recompute with
  `openapi_normalize.fingerprint(json.load(open("projects/example/contracts/postgrest-openapi.canonical.json")))`
  at the branch point and compare to what the rig prints), **`anon` with
  zero paths** and a different fingerprint. If `authenticated` no longer
  equals the snapshot: stop; the tree moved under the plan and D1200's
  design needs the difference read (a `diff` of the two canonical texts is
  printed by the rig when the object sets agree).
- **23b, the canonical form in JavaScript** (`/tmp/r23b.sh`, then
  `/tmp/r23b2.sh`). Expect four `EQUAL` and `app-openapi.canonical.json`
  `DIFFER` on exactly the two float lines; `node /r/hello.ts` exit 0 with no
  flag; `typeof fetch: function`; `v22.23.2`; npm `10.9.8`.
- **23c, typecheck and smoke inside the pinned image, and the lockfile.** Write
  `/tmp/r23c/package.json` (`{"name":"r23c","private":true,"devDependencies":{"typescript":"5.9.3"}}`
  — 5.9.3 is a guess; read the current stable from
  `https://registry.npmjs.org/typescript/latest` first and use that) and run
  `docker run --rm -v /tmp/r23c:/w -w /w <NODE_RUNTIME_IMAGE> npm install
  --package-lock-only --ignore-scripts --no-audit --no-fund`; expect a
  `package-lock.json` whose `packages["node_modules/typescript"]` has
  `version`, `resolved` and `integrity` (`sha512-…`). Then `npm ci
  --ignore-scripts --no-audit --no-fund` in a second container and `npx tsc
  --version`. Then write `/tmp/r23c/good.ts` (a typed function with a
  deliberate `const n: number = "x"` in `/tmp/r23c/bad.ts`) and run `npx tsc
  --noEmit --strict good.ts` (expect 0) and `… bad.ts` (expect 2, one error
  line naming the file: the control). Record the `typescript` version and
  integrity for Run 3's `versions.in.yaml` entry.
- **23d, what classifies an API change today.** In Python (venv,
  `PYTHONPATH=src`): `grep -n "also\|api_operation" bin/upgrade.py
  src/agentic_postgres/upgrade_plan.py` and record whether any caller passes
  an `api_operation_*` class into `build_plan(also=…)` (the plan expects
  **none**; D1206 says so from a read, this confirms it from the tree at the
  branch point). Then the planted change: copy
  `projects/example/contracts/postgrest-api-surface.yaml` and
  `…/postgrest-openapi.canonical.json` to `/tmp/r23d/`, add one RPC
  `rpc_probe` (`methods: [POST]`, `arguments: [p_x]`) to the surface copy and
  the matching `/rpc/rpc_probe` path to the snapshot copy (post, one body
  parameter with `p_x: {type: string, format: text}`, the same `produces` and
  `responses` as `create_note`'s), rewrite the snapshot copy through
  `openapi_normalize.canonical_bytes` so it stays canonical, and record that
  `compatibility.required_level(["api_operation_added"]) == "minor"` and
  `required_level(["api_operation_removed"]) == "major"`. These two files are
  Run 2's fixture for `classify_changes`; keep them.
- **23e, the agent plane's `list_resources` today, offline.** In the venv
  with `services/auth-api` on the path the way `tests/contract/test_mcp_tools.py`
  imports it (read its first 60 lines and copy the import), load the example
  lock the tests build (`test_mcp_tools.py:143`'s fixture) and call
  `list_resources(lock)`: record the exact keys of the result (`contract_id`,
  `resources`) and that `lock.tools_sha256` is a string on a schema-4 lock.
  Control for Run 2: the same call after the change carries `lock`. Also
  `git grep -n "list_resources" -- tests services src bin docs | wc -l` and
  the list, which is Run 2's reader list.
- **23f, the client's wire shape against a recorded plane.** Not a container:
  read `tests/deployment/test_session22_plane.py:831-850` (`sse_result`,
  `refused`, `tool_text`) and `test_session8_agent_plane.py:120-160` (the
  bare `tools/call` with `Accept: application/json, text/event-stream`, no
  `initialize`), and record in the Done paragraph the exact request the
  wrapper must send and the two response shapes it must parse (`data:` SSE
  lines; `result.isError`; `error.message`). This is a reading, and it is
  written down so Run 3's emitter is written from the tree rather than from
  memory of MCP.

**ADR 0204 — A generated client is a claim about the surface it was
generated from, and its proof reads the served surface as the caller.**
Indexed in `docs/decisions/README.md` (the row format is the index's last
six rows; Session 23, Accepted). D1200–D1204, D1206–D1210. Related: 0050,
0065/0066, 0119, 0127, 0139, 0158, 0162, 0181, 0195, 0198, 0201, 0203.
States: the four inputs and the one IR; what `init()` checks (the served
REST document, as the caller, fingerprint equality after the client's
normalization — D1207 — and why `basePath` is the one field asserted), what
`listResources()` checks (the plane's reported lock digest), and what is
embedded but not checked (the application digest, D1209); three outcomes at
init and how each is reported; the version rule (ADR 0162's classes over the
IR diff, the artefact's own number, `1.0.0` first); what a generated file may
never contain (a credential, a token, a password, a key, a URL with
userinfo, a call the contract does not name, an operator outside the set);
that the canonical form has a second implementation guarded by
`js_reproducible` and the toolchain comparison (D1203); that the client is
committed under `projects/<slug>/clients/typescript/` and drift-checked, and
the hook is a printed next step (D1208); that the Python client is not built
and what would make it one module (D1205). Alternatives refused: reading the
deployed document (ADR 0158; it is `0600 root` on a host and a client has
none); reading the docs route (Basic auth, a password a client may not hold);
comparing object sets instead of fingerprints (a definition or a parameter
can move with the set unchanged — `api-contract.py:665`'s own message);
generating from `capabilities.yaml` on the host (D930: the lock is compiled
from the committed contract).

**Targeted:** none (documentation). **Push.** CI is expected green (docs
only). Record the run id. Mark Done with 23a–23f's numbers.

**Done.** 2026-09-12, on `session-23` branched at `2a62833` (this plan's own
commit, directly after `d6f6e94`). Documentation only: ADR 0204, its index row,
four divergence rows **D1212–D1215**, and this paragraph. Next free **D1216**.

**23a and 23b re-ran as the control, and the tree has not moved.** Every number
in §1 reproduced at the branch point. `apg dev up` exit 0, **33 migrations**,
port 32811; the authenticator activated as the superuser; three PostgREST
containers on the pinned digest with `compose.yaml`'s own
`postgrest.environment` values. `GET /` with `Accept: application/openapi+json`,
200 on all three arms:

| role | bytes | fingerprint | objects | == project snapshot |
|---|---|---|---|---|
| `anon` | 2404 | `1da00c119b984b82` | **none** | no |
| `authenticated` | 16035 | `808ac715c09aeebc` | all 7 | **yes** |
| `api_documentation` | 16035 | `808ac715c09aeebc` | all 7 | **yes** |

`808ac715c09aeebc382dd5afc886c1680fe2ea9870e729b9d34a623dee8d18de` recomputed
from `projects/example/contracts/postgrest-openapi.canonical.json` at the branch
point is the same value — so **D1200 and D1211 stand**: the live surface read as
the ordinary caller normalizes to the committed snapshot under strict equality,
`host` is `fixture-alpha-dev.test:443` (D1207's `:443`, measured), `basePath`
`/api/rest`, `schemes` `["https"]`, and the pre-request hook does not refuse the
root document. `anon`'s zero-object document at a different fingerprint is the
control that the arm reads privileges rather than a constant. 23b: node
**v22.23.2**, npm **10.9.8**, `typeof fetch: function`, `node x.ts` exit 0 with
no flag (`--experimental-strip-types` accepted and redundant), and **four
`EQUAL` plus `app-openapi.canonical.json` `DIFFER`** (`f21bf4a8da90` against
`3007d815448e`) on **exactly** two lines — 494 `"minimum": 1.0` → `1` and 1745
`"exclusiveMinimum": 0.0` → `0`. **D1203 stands.** All containers removed;
`apg dev down` in `finally`; the rigs are in the scratchpad under
`s23-planning-rigs/`.

**23c, the toolchain — and the run's first real find (D1212).** `typescript`'s
`dist-tags.latest` is **7.0.2**, not the plan's guessed 5.9.3; the 5.x line ends
at 5.9.3. Both measured in the pinned image, on musl, with `bad.ts` as the
control in every arm: 7.0.2 locks **22 entries** (the package plus 20 optional
per-platform binaries, none constrained by `libc`), 5.9.3 locks **2**, and
**every entry of both carries an `integrity` hash** (`entries WITHOUT
integrity: []`). `npm ci --ignore-scripts --no-audit --no-fund` exit 0 on both;
`tsc --version` answers `Version 7.0.2` / `Version 5.9.3`; `good.ts` exits 0 on
both. **`bad.ts` exits 1 under 7.0.2 and 2 under 5.9.3**, with the identical
message `bad.ts(4,7): error TS2322: Type 'string' is not assignable to type
'number'`. `TYPESCRIPT_VERSION=7.0.2` is Run 3's pin, and every typecheck proof
asserts a non-zero exit **and** the message, never the bare status.

**23d, what classifies an API change today (D1213).** `required_level` measured:
`[]`→`patch`, `api_operation_added`→`minor`, `capability_added`→`minor`,
`api_operation_removed`→`major`, `api_operation_changed`→`major`, the pair
→`major`, and an unclassified name **raises** (`unclassified change(s):
['client_shape_changed']`) rather than defaulting to patch — the control. The
plan expected *no* caller to touch an `api_operation_*` class; in fact
`bin/upgrade.py:100–102` already lists all three as `--also`-declarable and
`upgrade_plan.py:250` unions them in. Nothing **computes** one, which is the
half D1206 got right. The planted change is in `/tmp/r23d/`
(`surface-before.yaml`, `snapshot-before.json`, `snapshot-after.json`): one RPC
`rpc_probe` with a single `p_x` string body parameter, `create_note`'s
`produces` and `responses`; fingerprint moves `808ac715c09aeebc` →
`aa7591474198e25e`, `ADDED objects: ['rpc/rpc_probe']`, and the planted file
round-trips through `canonical_bytes` unchanged. That is Run 2's
`classify_changes` fixture.

**23e, `list_resources` today (D1201 confirmed, D1215 found).** The result keys
are **exactly** `['contract_id', 'resources']` — measured on a lock with
`tools_sha256` set to a 64-char string and on one with it `None`, both returning
the same two keys and the same non-empty resource entry (`{"tool":
"query_resource", "resource": "notes", "required_scopes": ["notes:read"],
"max_rows": 50}`). `'lock' in result` is `False` on both, which is Run 2's
before-half control. **`CapabilityLock` carries no `schema_version`**: its ten
fields are `contract_id, project_key, upstream, canonical_sha256, tool_count,
capability_count, tools, profile, vocabulary, tools_sha256`, and
`SUPPORTED_SCHEMA_VERSIONS` `{1,2,3,4}` is read by `load_lock` only — so
`AGT-META-001` is written against `tools_sha256 is None`. The caller's scopes
reach `list_resources` through `current_agent_context()`, replaced in the module
under test the way `test_mcp_tools.py:210` does it. **Run 2's reader list, from
the tree:** 134 hits in 41 files — the ones that are not prose are
`services/auth-api/app/mcp_lock.py` (4), `mcp_runtime.py` (1), `mcp_tools.py`
(7), `scopes.py` (1), `src/agentic_postgres/capability_compiler.py` (1),
`evaluation_harness.py` (1), and the test modules `test_mcp_tools.py` (19),
`test_lock_roster.py` (5), `test_capabilities_manifest.py` (5),
`test_evaluation_harness.py` (6), `test_capability_profile.py` (4),
`test_capability_compiler.py` (3), `test_mcp_route.py` (3), `test_mcp_budgets.py`
(2), `test_project_agent_surface.py` (2), `test_agent_audit_plane.py`,
`test_api_migrations.py`, `test_auth_endpoints.py`, `test_metrics_surface.py`,
`test_scope_registry.py` (1 each), `tests/deployment/test_session8_agent_plane.py`
(2), `tests/external/test_session8_public_agent.py` (1), plus
`tests/evaluation-cases.yaml` (7) and `docs/mcp-tool-catalog.md` /
`docs/evaluation-report.md`, which are regenerated.

**23f, the wire shape, read from the tree (and D1214).** The plan's two line
citations are out of range: `test_session22_plane.py` is 407 lines with the
helpers at **:73–95**, and `bin/api-contract.py` is 546 lines with the
object-sets message at **:457**. Read at the real addresses, the request the
`agent.ts` wrapper must send is one `POST` to the plane's URL with
`Accept: application/json, text/event-stream`, `Authorization: Bearer <the
caller's own token>`, and body `{"jsonrpc": "2.0", "id": 1, "method":
"tools/call", "params": {"name": …, "arguments": {…}}}` — **no `initialize`
handshake**, because the runtime is assembled `stateless_http=True` (ADR 0125)
and a bare `tools/call` was measured answering 200. The two response shapes it
must parse: **SSE framing** (`event: message\r\ndata: {…}`; take the **last**
`data: ` line and `json.loads(line[6:])` — `json.loads(body)` raises on a
perfectly good answer, D458), and **a refusal in either of two places** —
top-level `error` with `.message`, or `result.isError` true with the text at
`result.content[0].text`. Reading only `error` passes on a refused write, which
is the open item §9 of `CLAUDE.md` still carries against Session 9's live
proofs; `agent.ts` reads both, and a negative test in Run 4 covers each.

**Targeted:** none — documentation only, so nothing ran before the push, per the
appendix. CI verdict on this commit read by full SHA, three buckets.

### Run 2 — the IR, and the plane reports its lock

**Read first:** `src/agentic_postgres/api_surface.py` whole (`load_surface`,
`load_project_surface`, `merged_surface`, `declared_objects`,
`published_objects`, `declared_types`, `contract_digest`);
`openapi_normalize.py` lines 100–160 and 395–440; `capability_compiler.py`
lines 40–100 and 800–900; `services/auth-api/app/mcp_lock.py` lines 95–300
(the lock's shape — the IR reads the lock **document**, the JSON, never the
service's dataclasses: `src/` may not import `services/`); `mcp_tools.py`
lines 255–310 and 480–530; `evaluation_harness.py` lines 60–160
(`RESERVED_WRITE_PARAMETERS`, `filter_operators`, `contract_digest`);
`bin/mcp-contract.py` lines 263–379 (`command_lock` — where the lock is
written and what it needs); `tests/contract/test_mcp_tools.py` lines 1–160
and the three sites rig 23e listed.

1. **`list_resources` reports the loaded lock** (D1201, `AGT-META-001`).
   `services/auth-api/app/mcp_tools.py::list_resources` returns
   `{"contract_id": …, "lock": {"tools_sha256": lock.tools_sha256, "tool_count": lock.tool_count}, "resources": […]}`.
   `lock.tools_sha256` is the `CapabilityLock` field D1182 added (the value
   the lock carried; `None` below schema 4, which JSON renders as `null`).
   Docstring: why the plane says which lock it serves to a caller (D1152,
   D1153) and why it is the carried digest, not a recomputation. Tests in
   `test_mcp_tools.py`: `test_list_resources_reports_the_loaded_locks_digest_and_count`
   (the schema-4 fixture lock; the value equals the lock document's
   `tools_sha256`) and `test_list_resources_reports_null_for_a_lock_below_schema_four`
   (the module's older fixture, or a copy with `schema_version: 3` and no
   `tools_sha256`, loaded through `load_lock`; `lock` is
   `{"tools_sha256": None, "tool_count": …}`). **Grep every reader** of
   `list_resources` (rig 23e's list) and run each module whole; regenerate
   `docs/mcp-tool-catalog.md` if the catalog renders result shapes (read
   `bin/render-mcp-catalog.py` — if it does not, say so in the Done
   paragraph rather than assuming).
2. **`src/agentic_postgres/client_ir.py`** (pure: files in, a frozen
   dataclass out; no subprocess, no network, no `services/` import). Public
   surface — the names Run 3's emitter and Run 5's command use, fixed here:

   ```python
   @dataclass(frozen=True)
   class Column:      name: str; ts_type: str; format: str; nullable: bool
   @dataclass(frozen=True)
   class Relation:    name: str; columns: tuple[Column, ...]; methods: tuple[str, ...]
   @dataclass(frozen=True)
   class Argument:    name: str; ts_type: str; format: str; required: bool
   @dataclass(frozen=True)
   class Rpc:         name: str; arguments: tuple[Argument, ...]; path: str
   @dataclass(frozen=True)
   class AuthOperation: name: str; method: str; path: str; request: tuple[Argument, ...]; response_schema: str
   @dataclass(frozen=True)
   class ToolArgument: name: str; ts_type: str; required: bool
   @dataclass(frozen=True)
   class Tool:        name: str; kind: str; arguments: tuple[ToolArgument, ...]; discovery_scope_sets: tuple[tuple[str, ...], ...]; resources: tuple[str, ...]; supports_dry_run: bool | None; requires_approval: bool | None; descriptions: tuple[str, ...]
   @dataclass(frozen=True)
   class Digests:     api_surface_sha256: str; rest_openapi_sha256: str; app_openapi_sha256: str; tools_sha256: str
   @dataclass(frozen=True)
   class IR:
       rest_contract_id: str; agent_contract_id: str; project_root: str | None
       relations: tuple[Relation, ...]; rpcs: tuple[Rpc, ...]; auth: tuple[AuthOperation, ...]
       tools: tuple[Tool, ...]; enums: dict[str, tuple[str, ...]]
       filter_operators: tuple[str, ...]; pt_codes: tuple[str, ...]
       caller_facing_tokens: tuple[str, ...]; digests: Digests
       template_version: str

   def build(*, surface, snapshot, app_snapshot, lock, project_root, pt_sources) -> IR
   def js_reproducible(document) -> str | None        # the offending JSON pointer, or None
   def classify_changes(previous: IR, current: IR) -> tuple[str, ...]
   def next_version(previous: str | None, level: str) -> str
   def to_document(ir: IR) -> dict            # JSON-able, sorted, for the emitter's manifest
   def from_document(document: dict) -> IR    # the inverse, for --check and for classify
   ```

   Rules, each with a test: `build` refuses (raising `ClientIrError`, a
   `ManifestError` subclass like the others) a snapshot object the surface
   does not name and a surface object the snapshot does not publish (the
   comparison `api-contract.py::compare_snapshot_to_surface` makes — read it
   and make the same one over `openapi_normalize.declared_objects` and
   `api_surface.declared_objects`, do not import `bin/`); columns are the
   surface's `columns` in the surface's order, each typed from
   `snapshot["definitions"][relation]["properties"][column]["format"]` by
   one table — `uuid|text|character varying|timestamp with time zone|timestamp without time zone|date|extensions.vector → string`, `integer|bigint|smallint|real|double precision|numeric → number`, `boolean → boolean`, `json|jsonb → unknown`, an enum's format (the type's schema-qualified name, `api.task_status`) → a string-literal union from the surface's `enums` in `enumsortorder` — and an unknown format refuses with the format named (never `any`); RPC arguments come from `paths["/rpc/<name>"]["post"]["parameters"][0]["schema"]` (`properties` and `required`), in the surface's `arguments` order, and a name in one and not the other refuses; the three auth operations are read from the application snapshot by path (`/auth/login`, `/auth/refresh`, `/auth/me`) and their request/response schema names; tools come from the lock document's `tools` — a `read` tool's arguments are the runtime's fixed read signature (`resource`, `columns?`, `filters?`, `order_by?`, `limit?` — read `mcp_tools.py:310-330` and `query_resource`'s registration at `:975-1030` for the exact names and types the runtime declares, and copy them), a `write` tool's are the lock's `write.arguments` plus `idempotency_key` and `dry_run` (required), a `metadata` tool's are none (`list_resources`) or `tool`+`resource` (`describe_resource`); `filter_operators` is `evaluation_harness.filter_operators()`; `pt_codes` is the sorted set of `PT\d{3}` matched in every `*.sql` under `migrations/templates/` and under each `pt_sources` directory the caller passes (the project set's templates), so a project raising its own code is in its own client's union; `caller_facing_tokens` is a **second copy** of `mcp_errors.CALLER_FACING_TOKENS` — seven strings, in a module constant `CALLER_FACING_TOKENS` — with `test_the_caller_facing_tokens_match_the_runtimes` importing the service module the way `test_mcp_tools.py` does and asserting equality (D486); `digests` are `api_surface.contract_digest(<merged surface's canonical bytes>)` — read how `contract_digest` digests a path and digest the merged document the same way, or digest the two files and say so —, `openapi_normalize.fingerprint(snapshot)`, `sha256(app_snapshot file bytes)` (the file, because its canonical form is not the module's — D1203), and `lock["tools_sha256"]`. `js_reproducible` walks the document and returns the first pointer holding a `float`, an `int` with `abs(v) > 2**53`, or a key that `sorted()` orders differently from UTF-16 code-unit order (compare `sorted(keys)` with `sorted(keys, key=lambda k: k.encode("utf-16-be"))`); `build` calls it on the REST snapshot and refuses on a pointer. `classify_changes` per D1206. `next_version` parses with `compatibility.parse` and bumps the named component, resetting the lower ones; `None` → `"1.0.0"`. `to_document`/`from_document` round-trip (asserted).
3. **`tests/contract/test_client_ir.py`** — the eight `GEN-IR-001` proofs
   of §2, the three `GEN-VERSION-001` ones over rig 23d's planted pair, and
   `test_js_reproducible_refuses_a_float_and_a_big_integer_and_accepts_every_rest_snapshot`
   (this one is registered under `GEN-TOOLCHAIN-001` and lives here because
   it needs no image). Fixtures: the release contracts from the tree, the
   example project's, and the lock **compiled in the test** through
   `capability_compiler.compile_lock` over the example's joint contract the
   way `bin/mcp-contract.py::command_lock` does it — read that function and
   call the same library functions in the same order (`capability_manifest.project_inputs`,
   `compile_joint_contract`, `scope_registry.vocabulary_block`,
   `compile_lock` with `upstream="https://example.invalid"` and the four
   `sources`); if the exact sequence needs `bin/` code that is not in `src/`,
   move that code to `src/agentic_postgres/capability_manifest.py` (or a new
   `lock_build.py`) with the command delegating to it — an ADR 0175 move,
   names and arities kept, readers grepped (D1187: grep the SQL and literal
   text too).
4. **Battery** (appendix): mutations over `client_ir.py` — the format table
   losing `uuid` (kill: `_types` test), the refusal of an unnamed object
   inverted, `pt_codes` scanning only the release, `classify_changes`
   returning `"api_operation_changed"` for an addition, `next_version`
   returning the same string, `js_reproducible` accepting a float — each
   with a paired control the mutation cannot reach; over `mcp_tools.py` —
   the `lock` member reporting `tool_count` in both fields (kill: the digest
   test) and reporting a recomputed digest (`sha256(canonical_bytes(tools))`)
   rather than the carried one (kill: the below-schema-four test, where the
   carried value is `None` and a recomputation is a string).

**Targeted:** `test_client_ir`, `test_mcp_tools`, every module rig 23e's
grep named, `test_capability_compiler` and `test_mcp_catalog` if step 1's
render moved, `test_operator_commands_run_on_the_host` (a new `src/` module
imports nothing outside the standard library, `yaml` and `agentic_postgres`
— asserted by that module for `bin/`, and by `test_embedded_python` for
`src/`; read what each checks). **Push, read CI.**

**Done.** 2026-09-12, in one commit with Run 3's emitter — **D1222**: a commit of
Run 2 alone cannot be green, because `test_repository_contract::test_no_module_is_imported_only_by_its_own_tests`
refuses a module imported by nothing outside its own tests (D204) and
`client_ir`'s only caller is `client_typescript`. Measured: 1156 passed, that
one failed. The guard is not weakened and no placeholder caller was written.
Rows **D1216–D1223**; next free **D1224**.

**Step 1, `list_resources` reports the loaded lock.** The result now carries
`lock: {tools_sha256, tool_count}` from the loaded object, beside the two
existing keys. The digest is the one the lock **carried** — `str | None`, and
`None` is the answer for a lock below schema 4, which is a distinct answer
rather than an absent one (ADR 0195). Two proofs in `test_mcp_tools.py`, over a
document put through the real `load_lock`: the schema-4 arm asserts the reported
digest equals the fixture's own `tools_sha256`, which the loader has already
verified against the tool list, so the value is traced end to end; the
below-schema-4 arm is the one that **kills a recomputation**, because at schema 4
the carried digest and a freshly computed one are the same string and only below
it is the honest answer `null`. A third proof keeps `mcp_lock.canonical_bytes`
equal to `capability_compiler.canonical_bytes` (D486), since the digest is over
those bytes. The v3 fixture was factored out of the existing v3 test so the new
v4 one is that document plus the two members version 4 adds, and nothing else;
at schema 4 a read tool must also DECLARE `reads`, derived in the fixture from
the methods its resources reach rather than written as a literal.
**`bin/render-mcp-catalog.py` renders tool metadata and no result shapes, so
nothing was regenerated** — read, not assumed, as the plan asked. Every reader
rig 23e's grep named was run whole: **679 passed** across sixteen modules.

**Step 2, `client_ir.py`.** Pure — files in, a frozen dataclass out — and
asserted so by AST. Built against both arms of the tree: the release client
(`notes-tasks-v1`, 2 relations, 3 RPCs, 6 tools) and the example project's
(`notes-tasks-v1+example-note-embeddings-v1`, 3 relations, 4 RPCs, 7 tools),
with the lock compiled in the test by `command_lock`'s own sequence. No `bin/`
code was needed for that, so nothing moved into `src/`. Five rows came out of
building it: **D1216** (one type has up to three spellings in one document — an
enum column qualified, the same enum as an argument bare, a vector column
carrying `(768)` where the argument does not), **D1217** (`api_surface_sha256`
is a taken name meaning the release file's bytes, so the IR's field is
`merged_surface_sha256`), **D1218** (the lock DOCUMENT is flat; `write.arguments`
is the loaded dataclass's shape and reading it found every write tool
argument-less), **D1219** (member-by-member classification, because dataclass
equality made the example project's purely additive tenant extension a MAJOR
bump) and **D1220** (the planner reaches a class either by `--also` or by
computing it, so the agreement is a union of two sets — the proof written to
confirm D1213 disproved half of it).

Measured, both arms: `js_reproducible` clears every committed REST and MCP
snapshot and finds the application document's offender at
`/paths/~1admin~1agents/post/requestBody/content/application~1json/schema/properties/secret_ttl_seconds/anyOf/0/minimum`
— **the same value rig 23b found by comparing bytes**, from the other side.
`classify_changes(release, project)` is `('api_operation_added',
'capability_added')` → **minor**; the reverse is `('api_operation_removed',)` →
**major**; identity is empty. `next_version(None, …)` is `1.0.0`.
`from_document(to_document(ir)) == ir` on both.

**Step 4, the battery: 10 mutations, 10 killed, 10 paired controls green,**
both files restored byte-identical to their `/tmp` snapshots. It found two proof
defects before it found anything else (**D1221**): the `uuid` mutation produced
an **ERROR**, not a kill, because `build` raises inside a module-scoped fixture
and no assertion was ever reached (D386); and the `pt_codes` mutation
**SURVIVED**, because the example project raises no code the release does not,
so `sources[:1]` is invisible to any assertion over the committed tree. Both
repaired with new proofs — a format-table test that touches no fixture, and a
synthetic second migration directory raising `PT499`. The battery itself was
repaired to run each mutation scoped to the test meant to kill it, or a
fixture-level break masks the assertion under test. One mutation of mine was
uninformative (D493) and rewritten: it called a helper that does not exist, so
the module failed to import and a different test went red.

**Targeted:** `test_client_ir`, `test_client_typescript`, `test_mcp_tools` and
every module rig 23e's grep named, plus `test_deploy_command`, `test_diagnosis`,
`test_acceptance_registry` (test functions added, D1119), `test_embedded_python`
and `test_operator_commands_run_on_the_host` (a new `src/` module),
`test_repository_contract`, `test_documentation_index`,
`test_openapi_normalize`, `test_compatibility` — each checked for existence
individually (D1104; `test_api_surface.py` does not exist and was dropped rather
than run by association).

### Run 3 — the emitter, the toolchain, `apg generate`

**Read first:** `bin/dev.sh` and `bin/dev.py` whole (the shape both new
files copy: the shell wrapper decides every argument error before Python
runs; `python_bin()`; `exec` of the `.py`; `rendered_document(key, …)`
through `deployed_output.read_rendered_document`; `EXIT_NOT_RENDERED = 4`
naming the render command); `tests/contract/test_dev_command.py` whole (the
test shape for a `bin/` command); `services/clients/node-pg/Dockerfile` and
`entrypoint.sh`; `services/docs/Dockerfile` lines 1–40; `versions.in.yaml`
lines 193–310 (the `packages:` block, `PRISMA_VERSION`'s entry);
`bin/lock-versions.sh` lines 25–110 and 280–300; `tests/contract/test_client_fixtures.py`
lines 150–200; `tests/contract/test_cli_contract.py` lines 40–200;
`tests/contract/test_repository_contract.py` lines 170–215; rig 23f's
recorded wire shape.

1. **`src/agentic_postgres/client_typescript.py`** — `emit(ir: IR) -> dict[str, str]`
   (relative path → file text) and nothing else public. Imports `client_ir`
   and the standard library; no path under `contracts/` or `projects/`
   anywhere in its source (the AST test). Every file's first line is
   `// Generated by bin/apg.sh generate from <rest_contract_id> + <agent_contract_id>; do not edit.`
   Files:
   - `contract.ts`: `export const CONTRACT = { rest_contract_id, agent_contract_id, template_version, client_version, api_surface_sha256, rest_openapi_sha256, app_openapi_sha256, tools_sha256 } as const;` — **the only file that carries a digest**, and `client_version` is `package.json`'s.
   - `canonical.ts`: `sortKeysDeep`, `canonicalText(document) = JSON.stringify(sortKeysDeep(document), null, 2) + "\n"`, `fingerprint(document) = sha256 hex of canonicalText`, using `node:crypto`'s `createHash` (a Node client; the browser is §10), and `normalizeServed(document, restUrl)` per D1207 with the sentinel constants **emitted from Python's** (`openapi_normalize.SENTINEL_HOST`, `SENTINEL_BASE_PATH`, `REQUIRED_SCHEMES` — read, never retyped).
   - `client.ts`: `createClient({ restUrl, appUrl, token })` returning an object whose every method except `init` and `login` refuses with `{ kind: "not_initialised" }` until `init()` has returned `{ kind: "ok" }`; `init()` per D1200 with the three refusals; per relation `list<Relation>(query?)` where `query` is `{ select?: (<column union>)[]; order?: { column, direction: "asc" | "desc" }[]; limit?: number; filters?: { column, op: <operator union>, value }[] }`, building `?select=…&order=…&limit=…&<column>=<op>.<encoded value>` with `encodeURIComponent` on every value and `Prefer: count=none`; per RPC `<camelCase name>(args)` doing `POST /rpc/<name>` with `Content-Type: application/json`, `Accept: application/json`, `Prefer: return=representation`; the three auth operations against `appUrl`; every response classified into `{ kind: "ok", status, body } | { kind: "refused", status, code: PtCode | string, message } | { kind: "transport", reason }` where `code` is the body's `code` member when the body parses (PostgREST's `{code, message, details, hint}` shape — `api.sh`'s `perform` reads the same) and `PtCode` is the union of `ir.pt_codes`. No retry, no logging, no `console.*` anywhere (the canary: nothing the wrapper prints), the token in a closure and never in a URL.
   - `agent.ts`: `createAgentClient({ mcpUrl, token })`; `idempotencyKey()` (D1202); per tool a method whose argument type is the tool's `ToolArgument`s (writes: the lock's arguments plus `idempotency_key: string; dry_run: boolean`, both required); the wire per rig 23f: `POST mcpUrl`, `Authorization: Bearer`, `Content-Type: application/json`, `Accept: application/json, text/event-stream`, body `{"jsonrpc":"2.0","id":<n>,"method":"tools/call","params":{"name":<tool>,"arguments":<args>}}`, the response parsed from `data:` lines when the content type is `text/event-stream` and as JSON otherwise; the result classified into `{ kind: "ok", content, structured } | { kind: "refused", token: AgentRefusal | null, message } | { kind: "transport", reason }` where a refusal is `result.isError === true` or a top-level `error`, and `token` is the first of the seven tokens found in the message text, else `null` (the runtime's messages carry the token as a word — read `mcp_errors.py:380-420` for the shape `AgentVisible` renders, and match that, not a guess); `listResources()` additionally compares `lock.tools_sha256` per D1201 and returns `{ kind: "ok" | "stale_contract" | "unconfirmable", … }`.
   - `package.json`: `{"name": "<rest_contract_id>-client", "version": <derived>, "private": true, "type": "module", "description": "Generated…", "dependencies": {}, "devDependencies": {"typescript": "<TYPESCRIPT_VERSION from versions.env>"}}`; `tsconfig.json` with `"strict": true, "module": "nodenext", "moduleResolution": "nodenext", "target": "es2022", "noEmit": true, "types": ["node"]` — **measure in 23c whether `types: ["node"]` needs `@types/node` installed** (it does: add it to the toolchain image's lock beside `typescript` and to the generated devDependencies; record the version); `README.md` (what the client is, `init()` first, the three refusals, that it holds only what it was given); `smoke.ts` (the offline proof's driver: reads `APG_REST_URL`, `APG_TOKEN`, optional `APG_MCP_URL` from the environment, runs `init()`, one relation read, one RPC, prints one JSON line per step — the only file that prints, and it prints outcomes, never the token).
2. **`tests/contract/test_client_typescript.py`** — the `GEN-EMIT-001`
   proofs of §2, plus `test_list_resources_compares_the_reported_lock_digest_and_reports_null_as_unconfirmable`
   over recorded bodies (three SSE texts in the module: agree, differ,
   null — run the emitted `agent.ts`'s classifier through the toolchain image
   with a tiny driver, or assert the emitted source contains the three
   branches by structure; the former is the honest one, and it costs one
   `docker run`), `test_a_request_names_only_reviewed_columns_operators_and_arguments`
   (the emitted union types are exactly the IR's names), and
   `test_the_example_client_is_the_emitters_output_byte_for_byte`.
   Credential scan: every emitted file against the patterns
   `test_root_script_policy` and `test_dev_environment_cluster::test_nothing_the_command_prints_is_a_password`
   use (read both and reuse the same regexes; add `://[^/]*:[^/]*@` for
   userinfo URLs).
3. **`services/clients/typescript/`**: `Dockerfile` (the node-pg shape:
   `ARG BASE_IMAGE`, `npm ci --ignore-scripts --no-audit --no-fund`, the
   65532 user, `ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]`),
   `package.json` (`typescript` and `@types/node` as dependencies of the
   *image* — they are its whole purpose), `package-lock.json` (from 23c's
   `npm install --package-lock-only` inside the image), `entrypoint.sh`
   (`cd /work && npx tsc -p tsconfig.json --noEmit` then, if `$1` is `smoke`,
   `node smoke.ts`; exit codes passed through). `versions.in.yaml` gains
   `TYPESCRIPT_VERSION` and `TYPES_NODE_VERSION` under `packages:` with
   `registry: npm`, the package names as npm spells them (`typescript`,
   `@types/node`) and a comment saying what reads them; `bin/lock-versions.sh
   --update --packages-only`; assert the `versions.env` diff is the two new
   pairs plus `APG_VERSIONS_IN_SHA256` and `APG_LOCKED_AT`. Tests in a new
   `tests/contract/test_generated_client_toolchain.py`:
   `test_the_image_pins_node_and_typescript_and_the_lock_carries_integrity_hashes`
   (the `test_client_fixtures.py:171/186` shape over this directory),
   `test_canonical_ts_reproduces_pythons_fingerprint_for_every_committed_snapshot`
   (builds the image — `docker build -q --build-arg BASE_IMAGE=<NODE_RUNTIME_IMAGE>` — then runs the emitted `canonical.ts` over `contracts/postgrest-openapi.canonical.json`, `contracts/snapshots/mcp/…`, and every `projects/*/contracts/*.canonical.json`, asserting each digest equals `openapi_normalize.fingerprint` of the parsed document; the app document is asserted to DIFFER, with the two pointers named, so the day it stops differing somebody reads why), `test_the_example_client_typechecks_strict` (the image over `projects/example/clients/typescript` mounted at `/work`). Both skip without docker the way the six cluster fixtures skip, and the gate refuses an absent daemon (Run 6). Add every new tracked file to `test_repository_contract.py`'s list.
4. **`bin/generate.sh` + `bin/generate.py`**. Usage:
   `bin/generate.sh --project FILE [--capabilities FILE] [--out DIR] [--check]`.
   The shell wrapper refuses (exit 2, before Python): no `--project`, a
   manifest that is not there, an unknown flag, `--out` given twice, a
   positional argument. The Python: derive the key as `dev.py::project_key_of`
   does (call the same function — move it to `src/` if it is only in
   `bin/dev.py`, with the re-export); read the rendered document through
   `deployed_output.read_rendered_document(key, runtime=False)` and refuse an
   unrendered project with exit 4 naming `./deploy.sh --project FILE
   --capabilities FILE --render-only` (the path the process holds, D975);
   load the merged surface and the project's snapshot when the manifest
   declares a set (`config.project_migration_set`), else the release's
   (`GEN-CMD-001`'s *no set* clause); the application snapshot; compile the
   lock in-process with the sequence Run 2 step 3 settled; `client_ir.build`;
   the previous IR from `<out>/generated.json` if present (`to_document`
   written beside the client — the manifest `--check` and `classify_changes`
   read) and the previous version from `<out>/package.json`; `emit`; write
   every file under `--out` (default
   `projects/<slug>/clients/typescript/` for a project with a set,
   `clients/typescript/` under the checkout root otherwise — say so in
   `--help`; refuse an `--out` that resolves outside `REPO_ROOT`, exit 2);
   `--check` compares each emitted text to the file on disk and exits 5
   naming the first differing file (or a missing one), writing nothing;
   print one line per file written, the derived version and the four
   digests, and never a token (there is none to print). Register both in
   `test_cli_contract.py` (`SHELL_COMMANDS`, `PYTHON_COMMANDS`) **before**
   running that module, and `git add` both before `test_commands_are_executable_in_the_git_index`
   (D1188). `tests/contract/test_generate_command.py`: the `GEN-CMD-001`
   proofs of §2 except the printed-next-step one (Run 5), and
   `GEN-VERSION-001`'s two `--check` proofs.
5. **The example client**: `bin/apg.sh generate --project project.example.yaml`
   after `./deploy.sh --project project.example.yaml --capabilities
   capabilities.example.yaml --render-only`; commit
   `projects/example/clients/typescript/` (every file), and run
   `bin/apg.sh generate --check --project project.example.yaml` (exit 0)
   and the toolchain typecheck (exit 0) before the commit. `.gitignore`
   needs no change (`projects/` is tracked); confirm with `git check-ignore
   -v projects/example/clients/typescript/client.ts` printing nothing.
6. **Battery**: over `client_typescript.py` — the digest constant emitted
   with a recomputed digest (kill: byte-for-byte test), `dry_run` dropped from
   a write's required arguments (kill: reserved-parameters test), a
   `console.log` inserted into `client.ts` (kill: the canary), a `like`
   operator added to the union (kill: operator test), `require("fs")` in
   `agent.ts` (kill: a test that the emitted sources import only `node:crypto`
   — add it); over `bin/generate.py` — `--check` writing the file it found
   differing (kill: `test_check_writes_nothing`), the render refusal
   returning 5 (kill: exit-4 test), `--out /tmp/x` accepted (kill: outside
   test). Over the Dockerfile — `npm install` in place of `npm ci` (kill: the
   pin test's `"npm ci" in dockerfile` clause, comment-stripped per D1197).

**Targeted:** `test_client_typescript`, `test_generate_command`,
`test_generated_client_toolchain`, `test_client_ir`, `test_cli_contract`,
`test_repository_contract`, `test_version_lock`, `test_client_fixtures`,
`test_operator_commands_run_on_the_host`, `test_root_script_policy`,
`test_apg_dispatcher`, `test_container_selectors` (D1184: `generate.py` reads
the rendered document — name the local `document` only for that, and a lock
`lock`), `test_dev_command` and `test_dev_environment` if `project_key_of`
moved (grep its readers). **Push, read CI.**

**Done.** 2026-09-12. Steps 1, 2, 4 and 5 landed at `0fe0bf9` with Run 2
(D1222, CI green); step 3 — the toolchain image — and the two remaining test
modules land here. Rows **D1225–D1228**; next free **D1229**.

**The image.** `services/clients/typescript/`: a `Dockerfile` on the node-pg
shape (`ARG BASE_IMAGE`, `npm ci --ignore-scripts`, uid 65532), a `package.json`
declaring `typescript` and `@types/node` as **dependencies** — for this image the
compiler is not a development convenience, it is the payload — a
`package-lock.json` of **24 entries, every one carrying an integrity hash**, and
an `entrypoint.sh` that typechecks `/work` and, given `smoke`, runs the client's
own driver. Both locked versions agree across three places (`versions.env`,
`package.json`, the lock), asserted rather than trusted (D486); the lock's
`typescript` integrity is `sha512-8FYau96o3NKOhbjKi…`, the value rig 23c measured
independently.

**What the image is FOR, measured:** the committed example client mounted
**read-only** typechecks with **`--network none`**, exit 0; a copy with one
wrong line fails in the same image at `contract.ts(27,7): error TS2322`; a
directory with no client exits 2; an unreadable one exits 3. The checkout is
untouched afterwards — no `node_modules`, no `tsbuildinfo`, nothing in `git
status`.

**Four rows, and three of them are about a check that could not have failed.**

* **D1225** — the plan's `npx tsc` **can reach the registry**: it resolves from
  the working directory first and, finding nothing (a generated client declares
  no dependency and has no `node_modules`), it fetches. Every typecheck would
  have been a silent network call. The compiler is addressed by its path in the
  image, and `@types` comes from `--typeRoots` rather than by writing a
  `node_modules` into the directory under test.
* **D1227** — the two toolchain proofs written earlier in Run 3 **installed
  `typescript` from the registry inside the test**. They were green, and
  `generated_client_toolchain` is a DECLARED OFFLINE claim (ADR 0202): they
  could not have run in the gate that will report them. Moved here, against the
  image, with `--network none` as the runner's DEFAULT rather than an option a
  later test can forget.
* **D1228** — the entrypoint reported an **unreadable** `/work` as *"there is no
  generated client to check"*. The image runs as 65532 and `tmp_path` is 0700,
  so the mount is present and unreadable, and every `[ -f … ]` is false for both
  reasons. Two proofs in this module failed that way before the cause was found.
  Now a third answer: exit 3, naming the uid and the modes, ending *"This is NOT
  'no client here'"*. **ADR 0195's class, in a component written the same day by
  someone who had just put that ADR's number in three other files.**
* **D1226** is the one to carry forward. The emitted package used `./client.js`
  specifiers — correct TypeScript for a package that is COMPILED. This one never
  is: `noEmit`, run directly on the pinned Node's type stripping. So it
  **typechecked, exit 0, and could not run**: `node smoke.ts` died with
  `ERR_MODULE_NOT_FOUND: Cannot find module '/work/client.js'`. D1223 said a
  generator's output has a compiler and not running it declines the only total
  check available; D1226 says the compiler is not the last word either.

**`smoke.ts` ships** (emitter step 1's last file): the only emitted file that
prints, and it prints outcomes — the kind of each step, a refusal's code, never
a token, a URL or a row. Measured in the image with no network: missing
environment → `{"step":"environment","missing":"APG_REST_URL"}`, exit 2; an
address that resolves to nothing → `{"step":"init","kind":"unreachable"}` then
`{"step":"done","ok":false,"reason":"unreachable"}`, exit 1 — **`unreachable`,
not `stale_contract`**, which is ADR 0195 proved at runtime rather than by
reading the emitted source for three branches. The RPC step is behind
`APG_SMOKE_ALLOW_WRITE` because the first reviewed function of any real contract
is a write, and skipping is reported as its own outcome rather than as a pass.

**`tests/contract/test_generate_command.py`**, 18 proofs: nine argument errors
each exiting 2 **before Python runs** (no `Traceback` in any of them), `apg
--list` offering the verb by the dispatcher's own derivation, `--out` outside the
checkout refused, an unrendered project refused with **exit 4 naming the render
command and this invocation's own arguments**, a project declaring **no set**
generating the RELEASE's client (two relations, no `note_embeddings`, fingerprint
`85adb686223e` — ADR 0198's boundary), `--check` agreeing with the committed
client and **writing nothing** (asserted over the directory's bytes AND mtimes,
not by reading the code), drift reported as exit 5 naming the file, a MISSING
file reported as missing rather than as drift, and nothing printed that matches a
credential.

**Battery: 8 mutations, 8 killed, 8 paired controls green**, every subject
restored byte-identical and the committed client's ten files unchanged. The
mutations that matter: the unreadable/absent distinction removed (killed by
D1228's proof), `npx` reintroduced, `--typeRoots` dropped, the smoke reporting
`unreachable` as `stale_contract`, `--out` accepted twice, an `--out` outside the
checkout permitted, a missing file reported as drift, and `--check` writing the
files it was asked only to compare.

**Targeted:** `test_generated_client_toolchain` (8), `test_generate_command`
(18), `test_client_typescript`, `test_client_ir`, `test_repository_contract`
(the tracked-file list gained the image's four files), `test_client_fixtures`,
`test_cli_contract`, `test_version_lock`, `test_image_contracts`,
`test_documentation_index`, `test_acceptance_registry` — each checked for
existence individually (D1104). `ruff check` exit 0, `shellcheck` exit 0.

### Run 4 — the runtime proof, offline

**Read first:** `tests/contract/test_api_behaviour.py` lines 200–420 (the
PostgREST rig's container arguments, the schema-cache wait, `docker port`,
the teardown order); `tests/contract/test_dev_environment_cluster.py` lines
1–140 (the `environment` fixture: `apg dev down`, `up`, the state file,
`down` in `finally`); `compose.yaml` lines 640–760 (the `postgrest`
service's `environment` block — the rig reads it as YAML); `/tmp/r23a.py`
(the env-file construction and the three-role loop); `bin/api.py`
`perform` (lines 100–135; what a caller of PostgREST sends today).

1. **`tests/contract/test_generated_client_runtime.py`** — marked
   `contract`, `p0`, `database`, `security`; skips exactly as
   `test_dev_environment_cluster` skips (no rendered fixture, no docker) and
   for no other reason. Module fixture `served`:
   - `apg dev down` then `apg dev up --project project.example.yaml`
     (through `bin/apg.sh`, D1114); read `state.json` for `container`,
     `database`, `rendered_dir`; the roles from
     `.generated/fixture-alpha-dev/outputs.json`.
   - **The rig's one superuser action, and it is named as a rig's**
     (ADR 0066): `docker exec -i <container> psql -U postgres -d <database>
     -c 'ALTER ROLE "<postgrest_authenticator>" LOGIN PASSWORD ...'` with the
     password from a `0600` env file the fixture writes under `tmp_path`,
     never an argument (the statement goes through stdin, D1160). The dev
     environment activates two roles by decision (ADR 0203); a third is this
     test's, for the service it runs beside.
   - **PostgREST configured from the product's own model.** Load
     `compose.yaml` with `yaml.safe_load`, take
     `services.postgrest.environment`, and substitute: `PGRST_DB_URI` →
     `postgres://<authenticator>@<dev container bridge ip>:5432/<database>?passfile=/run/secrets/pgpass`
     with the password in a `0600` file bind-mounted read-only at that path
     (the product's own `?passfile=` shape, no password in `docker inspect`);
     every `${NAME:?required}` → the value from
     `.generated/fixture-alpha-dev/compose.env` (parse `KEY=VALUE` lines) —
     `ANON_ROLE_NAME`, `POSTGREST_MAX_ROWS`, the pool values, `PROJECT_DOMAIN`,
     `API_REST_PATH`, `JWT_AUDIENCE`, `POSTGREST_CORS_ORIGINS`; drop
     `PGRST_JWT_SECRET` (the rig has no key set) and record in the docstring
     that role selection is therefore by `PGRST_DB_ANON_ROLE`; an unresolved
     `${…}` after substitution fails the fixture with the name (never a
     silent empty). Two containers on the pinned `POSTGREST_IMAGE`, `-p
     127.0.0.1:0:3000`: **`served_as_authenticated`** (`PGRST_DB_ANON_ROLE`
     = the `authenticated` role) and the control **`served_as_anon`** (the
     `anon` role). Wait for `Schema cache loaded` in the logs (90 s
     deadline, `test_api_behaviour.py:262`'s loop). Yield both loopback
     URLs. `finally`: `docker rm -f -v` both, `apg dev down`.
   - `client_run(mount_dir, env)`: runs the toolchain image with
     `projects/example/clients/typescript` mounted at `/work` and
     `--network host` **only if** rig 23a's daemon is native (record); else
     with the PostgREST containers reached by bridge IP — decide once from
     `docker info --format '{{.OperatingSystem}}'` and say which in the Done
     paragraph. The environment passes `APG_REST_URL`, `APG_TOKEN` (a
     placeholder string: PostgREST has no secret and ignores it; the client
     still sends it, and the test asserts it never appears in the container's
     stdout) through `--env-file`, never `-e NAME=VALUE`.
   - Proofs (`GEN-HASH-001`, `GEN-TYPES-001`):
     `test_init_accepts_the_served_surface_it_was_generated_from` (smoke's
     first line is `{"step":"init","kind":"ok","fingerprint":"808ac…"}` and
     the fingerprint equals `openapi_normalize.fingerprint` of the example
     snapshot, computed in the test — the same number two ways);
     `test_init_refuses_a_surface_with_another_fingerprint_naming_both`
     (against `served_as_anon`: `kind: "stale_contract"`, both digests
     present, and a subsequent `listNotes()` in the same run is
     `not_initialised`);
     `test_init_reports_unreachable_and_unreadable_as_two_different_answers`
     (`APG_REST_URL=http://127.0.0.1:9/` → `unreachable`; a third tiny
     container serving `{"not":"openapi"}` at `/` — `python -m http.server`
     on the pinned Python image over a directory holding `index.html`?
     simpler: PostgREST's own `/rpc/nonexistent` URL as the base, which
     returns a JSON error body, not a document → `unreadable`; measure which
     is honest and use that);
     `test_a_typed_read_returns_rows_of_the_declared_shape` (`listNotes({
     select: ["id","title"], limit: 5 })` → `kind: ok`, status 200, an array
     — empty is fine, the shape is the claim; and a second read with an
     `order` and a filter to prove the query string builds: the smoke prints
     the URL it built, asserted to be `…/notes?select=id,title&order=created_at.desc&limit=5&title=eq.x` after decoding);
     `test_a_refused_write_arrives_as_the_pt_code_the_database_raised`
     (`createNote({p_title: "probe"})` without an identity → the hook has no
     subject → `AP401` raised with `PT401` → HTTP 401 → `{kind: "refused",
     status: 401, code: "PT401"}`; the control is the read above returning
     200 — a rig that refused everything would pass a refusal test for the
     wrong reason).
   - `test_nothing_the_client_prints_is_the_token`: the placeholder token
     string absent from every container's stdout and stderr.
2. **Battery** (appendix): over the emitted `client.ts` **through the
   generator** (mutate `client_typescript.py`, regenerate into a `tmp_path`
   copy, run the proofs against the copy): the fingerprint comparison
   inverted (kill: the accept test), `basePath` assertion removed (kill: a
   test added here that mounts the client with `APG_REST_URL` carrying a
   wrong path → `stale_contract`, control the right path), the `code` member
   read from `message` (kill: PT401 test), `encodeURIComponent` dropped
   (kill: the query-string test with a value carrying `&`). Each paired with
   the unmutated run in the same invocation; `PYTHONDONTWRITEBYTECODE=1`.

**Targeted:** `test_generated_client_runtime`, `test_client_typescript`,
`test_dev_environment_cluster` (the `apg dev` round trip is shared, and a
fixture that left an environment up would make the next module's `down`
first), `test_generated_client_toolchain`. **Push, read CI** — the runtime
module runs in the `session-2-contract` job, which has Docker and the
render; the `gate` job's suite runs it too. Read both jobs' logs for the
step's wall time (Run 5's envelope wants the generation time, and this
step's time is a bound on the smoke).

**Done.** 2026-09-12. `tests/contract/test_generated_client_runtime.py`, seven
proofs, all green against a real cluster. Rows **D1229–D1232**; next free
**D1233**.

**THE CHAIN CLOSES, MEASURED END TO END.** `apg dev up` (33 migrations), the
authenticator activated by the rig's one superuser action through `docker exec`
stdin, PostgREST configured from `compose.yaml`'s own `postgrest.environment`
block with every `${…}` resolved from the rendered `compose.env`, the pinned
Traefik stripping the project's own `API_REST_PATH`, and the generated client
run in the toolchain image against it:

```
{"step":"init","kind":"ok"}
{"step":"read","relation":"note_embeddings","kind":"ok","rows":0}
{"step":"filter","relation":"notes","column":"title","kind":"ok"}
{"step":"rpc","name":"create_note","kind":"refused","code":"PT401"}
```

`init` verified `808ac715c09aeebc…` — **arrived at two ways in one assertion**:
computed here from the committed snapshot by `openapi_normalize.fingerprint`,
and computed inside the container by the emitted `canonical.ts` over the
document the service actually served, as the caller. That is rig 23a's
measurement made a proof, with the client as the instrument.

The three refusals, each distinct: the `anon` role's document →
`stale_contract` **naming both digests** (`808ac715c09a…` expected,
`1da00c119b98…` served) and no later call attempted; nothing listening and the
right service at a wrong path → `unreachable`; the right service at its own
root → `unparsable`, naming the basePath mismatch. **A read of 0 rows is the
correct result** — the token names a role and no subject, so migration 0013's
hook sets no `app.user_id` and every owner-scoped policy matches nothing; rows
here would mean the policy was not applied.

**FOUR ROWS, AND THREE ARE THE RIG'S DESIGN NOT SURVIVING CONTACT WITH THE
PRODUCT.**

* **D1230 — the rig needed the product's own edge.** PostgREST serves at the
  root and has no prefix option; production's `basePath: /api/rest` exists
  because Traefik strips it. The planned rig — PostgREST alone — could only ever
  have tested a base path no deployment publishes: measured, the client at the
  root is refused (correctly) and at the prefix gets a 404. Rig 23a never met
  this because it normalized with `expected_base_path=served["basePath"]`,
  taking the served value as the expected one, so it never exercised the
  assertion at all. The direct-at-the-root arm is kept as the control.
* **D1231 — the planned rig would have answered 500 to everything.** It said to
  drop `PGRST_JWT_SECRET` and select roles by `PGRST_DB_ANON_ROLE`. But the
  generated client ALWAYS sends `Authorization: Bearer` — reading the surface as
  the caller is the whole of ADR 0204 — and PostgREST with no JWT configuration
  cannot verify a token it was handed. All four arms of rig 23g returned
  `{"kind":"unreachable","reason":"the service answered 500"}` before the rig
  signed its own. `PGRST_DB_ANON_ROLE` was right for rig 23a, which fetched a
  document anonymously, and wrong the moment the CLIENT became the instrument.
* **D1232 — the query-string proof would have compared the client to a string
  this session wrote.** Replaced by a proof through the service: the filter
  value `probe&select=no_such_column` is **200** when percent-encoded and
  **400** when concatenated, because the second form names a column the relation
  does not have. PostgREST is the judge rather than a literal in the test, and
  ADR 0127 — *a caller value is a value, never syntax* — is asserted at the
  client for the first time.
* **D1229** is the defect the rigs exposed on the way: the client refused any
  document whose `basePath` is `/`, because `/` occurs in every OpenAPI document
  and the residue check is a substring test. Unreachable for this product —
  `project.schema.json` forbids a root base path — but reachable by whoever
  holds a copied client, so the client was repaired and `openapi_normalize`,
  which carries the same clause and cannot reach it, was not.

**BATTERY: 5 mutations, 5 killed, 5 paired controls green**, the emitter
restored byte-identical and the committed client's ten files unchanged. Every
mutation is made in `client_typescript.py`, the client **regenerated with the
product's own command**, and the proof run against a fresh cluster — a battery
over the emitter's source would only prove that the emitter emits what it
emits. Killed: the fingerprint comparison inverted, the basePath assertion
removed, a refusal's code read from the status instead of the body,
`encodeURIComponent` dropped, and an unreachable service reported as a stale
contract. **The pre-flight earned its keep**: the first run stopped on a
`0x` anchor — a backslash lost to Python string escaping — before spending
twenty minutes reporting an unapplied mutation as a weak test (D269).

**Cost, for Run 5's envelope:** the module is **~150 s** wall (7 proofs, one
`apg dev up`, one PostgREST, one edge, one image build, 13 container runs); the
battery is six full cycles at roughly that each.

**CI WAS RED ON THE FIRST PUSH, AND THE CAUSE IS WORTH MORE THAN THE RUN**
(D1233). Every proof errored with *"PostgREST never loaded its schema cache"*,
and eight hundred characters into the container's log: `fe_sendauth: no password
supplied`. The PostgREST image declares `User=1000`, libpq ignores a passfile
looser than `0600`, and the author's uid on this workstation **is also 1000** —
so the rig read its own pgpass by coincidence and the CI runner, at uid 1001,
could not. Reproduced locally with a control (readable at 1000, `Permission
denied` at 1001), repaired by taking the uid from the image and giving the file
that owner through a root container, and the fixture now **reads the file as
that user before waiting on anything**, so the failure names a permission
instead of timing out on a cache. **D1228, two runs earlier, was the same fact**
— a file the author can read and the container's user cannot — and it did not
generalise into a habit. Both times the message was about the content ("no
client here", "no password supplied") where the truth was about access.

**Targeted:** `test_generated_client_runtime`, `test_client_typescript`,
`test_client_ir`, `test_generated_client_toolchain`, `test_generate_command`,
`test_dev_environment_cluster` (the `apg dev` round trip is shared, and a
fixture that left an environment up would make the next module's `down` the
first thing that ran), `test_repository_contract`, `test_acceptance_registry`.
`ruff check` exit 0.

### Run 5 — the version, the hook, the envelope, the documents

**Read first:** `src/agentic_postgres/capacity.py` lines 240–360 (the
`MACHINE` rows Session 22 wrote and their conditions);
`bin/render-capacity-envelope.py`; `tests/contract/test_capacity_envelope.py`
lines 290–383; `bin/api-contract.py` lines 355–394 and `bin/mcp-contract.py`'s
`compile` verb; `tests/contract/test_printed_commands.py`;
`tests/contract/test_api_contract_command.py` (what it asserts of stderr);
`README.md` lines 157–260 and 337–430; `docs/dev-environment.md` (the shape
the new page copies); `docs/README.md` §*Developer loop*;
`docs/client-compatibility.md` §1.

1. **The hook** (D1208): `api-contract.py::command_update` with `--project`
   prints, after its *"this candidate belongs at …"* line,
   `api-contract: then generate the project's client: bin/apg.sh generate --project <project_path>`
   (the path the process holds); `mcp-contract.py`'s `compile --project`
   path prints the same line to stderr after streaming the contract. The
   release-only paths print nothing new (a release client is regenerated by
   the same command without `--project`, and README says so).
   `test_generate_command.py::test_the_capture_and_the_compile_print_the_next_step`
   runs `bin/api-contract.sh --update --project project.example.yaml
   --project-outputs <a file that fails at `fetch_live` for want of a
   token>` — no: `--update` needs a token before it reaches the print, so
   assert the print by structure (`inspect.getsource` of both functions
   contains the literal `bin/apg.sh generate --project`) **and** run
   `bin/mcp-contract.sh compile --project project.example.yaml >/dev/null`
   and assert the stderr line; `test_printed_commands` scans the new prints
   (no `<placeholder>` for a value the process holds).
2. **The envelope** (`GEN-ENV-001`, D1079): two `Measurement(kind=MACHINE)`
   rows in `capacity.ENVELOPE` — `apg generate` wall time for the release
   contract (5 objects, 6 tools) and for the example project's (7 objects, 8
   tools), on this workstation, twice each, conditions naming the machine,
   WSL2/native, the Docker server version (the generator itself needs no
   daemon; say so), the object and tool counts, and *Python only — no
   typecheck in the number*; a third row for the toolchain typecheck of the
   example client (image cached), since that is what a developer waits for.
   Measured by a rig `/tmp/r23g.sh` with `date +%s.%N` around
   `bin/apg.sh generate --project … --out /tmp/r23g-out` (an `--out` inside
   the checkout is required — use `.generated/.r23g/` and delete it) and
   around the toolchain run. `render-capacity-envelope.py --write`;
   `test_the_envelope_carries_generation_time_per_contract_size` (per-row,
   D1197's lesson: each row is checked on its own line, not the joined
   document).
3. **Documents.** README: a new section *## A generated client* between
   *A local environment* and *Deploying* — what `apg generate` writes (one
   paragraph), `init()` first and the three refusals, what the client holds
   (a URL and a token the caller supplied; nothing else), the version rule
   in one sentence, `--check` and where the example lives; the *Adding your
   own tables* table gains row 5: `bin/apg.sh generate --project project.yaml
   — a typed client over your surface, regenerated after every capture —
   offline: yes`; *Giving an agent your tables* gains one sentence after the
   compile command (the generate step, and that the agent wrapper wraps your
   tool). `docs/generated-clients.md` (new; indexed in `docs/README.md`
   under *Developer loop*): the four inputs, the files, `init()` and
   `listResources()` and their outcomes, the `RestError` and `AgentRefusal`
   unions with the sentences, the version rule with a worked diff, the
   toolchain image and how to typecheck, *what this is not* (an ORM, a
   query language, a holder of a credential, a browser bundle — §10), and
   *what to do when* (`stale_contract` after a deploy: regenerate from the
   commit the deployment is at; `unconfirmable`: the deployment's lock
   predates schema 4; a typecheck failure after a regeneration: the contract
   moved and the caller's code names something it no longer publishes —
   which is the point). `docs/client-compatibility.md` §1 gains one line
   pointing at the new page (the four fixtures prove drivers; the generated
   client is over the endpoint contract). `docs/new-team-member.md` gains
   one step after 8a, derived by diff (D693). `test_documentation_index`
   passes (every page indexed once; every command README names exists and
   its flags appear in its usage).
4. **Battery**: the printed-next-step line pointing at `bin/generate.sh`
   instead of `bin/apg.sh generate` (kill: the structure test asserts the
   dispatcher spelling, which is the one README teaches); a `MACHINE` row
   without the machine in its conditions (kill: `test_a_machine_measurement_names_the_machine_it_describes`
   — the existing guard, run as the control that the new rows are guarded
   by it).

**Targeted:** `test_generate_command`, `test_printed_commands`,
`test_api_contract_command`, `test_capability_compiler` (if the compile verb
moved), `test_capacity_envelope`, `test_documentation_index`,
`test_session12_documented_path`, `test_repository_contract`. **Push, read
CI.**

**Done.** The hook, the envelope, the documents (2026-09-12).

**What the run built.** `api-contract.py --update --project` and
`mcp-contract.py compile --project` each end by printing
`bin/apg.sh generate --project <the path the process was given>`, on **stderr**,
so a redirected capture is still the document and nothing else; the
release-only paths of both print nothing, which is the control that says the
line belongs to the project argument. Three `MACHINE` rows in
`capacity.ENVELOPE` and the rendered `docs/capacity-envelope.md`.
`docs/generated-clients.md` (277 lines, nine sections), indexed in
`docs/README.md` under *Developer loop*; README's new *A generated client*
section between *A local environment* and *Deploying*, row 5 of the
*Adding your own tables* table, and the regeneration sentence after the
compile block; `docs/client-compatibility.md` gains the sentence separating a
driver proof from an endpoint-contract one; `docs/new-team-member.md` gains
step **8b**, derived by diff (D693).

**What it measured** (rig 23g, `/tmp/r23g.sh`, `/tmp/r23g2.sh`, `/tmp/r23g3.sh`,
`date +%s.%N` around the command, output in the scratchpad):

* `apg generate` for the **release** contract — 2 relations, 3 RPCs, 6 tools,
  29,157 bytes emitted — **0.28 s, 0.28 s, 0.29 s**;
* for the **example project's** contract — 3 relations, 4 RPCs, 7 tools,
  31,097 bytes — **0.31 s, 0.32 s, 0.33 s**. Forty milliseconds for two more
  objects, one more tool and 1,940 more bytes: **the slope is what publishing
  two sizes buys**, and it is flat, because the cost is the process starting;
* the **first** `bin/apg.sh generate` in a fresh shell — **0.81 s**, against
  0.28 s for every one after it on the same inputs. Stated in the row rather
  than averaged in;
* the toolchain typecheck of the committed example client, image cached —
  **1.12, 1.22, 1.57, 1.61 s** over four samples, and **2.72 s** on the first
  run after the image was built. The first two samples differed by 2× so two
  more were taken rather than published as a range of two;
* and the version rule's worked diff, **run rather than written**: identity ⇒
  no change; a relation removed ⇒ `api_operation_removed` ⇒ major ⇒ 2.0.0;
  added ⇒ `api_operation_added` ⇒ minor ⇒ 1.1.0; a tool added ⇒
  `capability_added` ⇒ minor. Eight filter operators, six `PT` codes, seven
  caller-facing tokens, all read from the committed IR. Every table in the new
  page is a measurement, not a description of the code's intent.

**Battery: 10 mutations, 10 killed, 10 controls green**, every anchor
pre-flighted to exactly one match, all three files restored and verified by
`cmp`. Five against the hook (the dispatcher spelling; the placeholder, killed
twice — once by the widened scan and once by the shape guard; the hook made
unconditional, killed by the release control; the hook moved to stdout, killed
by the redirect-purity assertion) and five against the envelope (the size
dropped; `Python only` dropped; the cache state dropped; a row renamed out of
the pair; and the plan's own mutation, a `MACHINE` row naming no machine,
killed by the existing guard with the churn proof green beside it).

**Two rows. D1234**: the plan said the example project's contract is 7 objects
and **8** tools; it is **7**, counted in the rig, and the number was one line
from being written into a published capacity document. **D1235**: the plan
named `test_printed_commands` as the reader of the two new prints, and that
module read `bin/deploy-project.py` and nothing else — D975's rule has been
enforced on one file since Session 17, and from a plan it reads as a rule about
the repository. Widened to the three drivers that print a command; the
placeholder mutation was then applied against the capture and killed.

**Targeted:** `test_generate_command` (20), `test_printed_commands` (5),
`test_api_contract_command`, `test_capability_compiler`,
`test_capacity_envelope` (16), `test_documentation_index`,
`test_session12_documented_path`, `test_repository_contract` — 109 + 257
passed. Also cleaned: six root-owned `node_modules` directories left under
`/tmp/pytest-of-gmpar` by D1227's *pre-repair* toolchain proofs, which pytest's
own garbage collection cannot remove and which had been accumulating silently.
The repaired proofs create none — grep, not assumption.

### Run 6 — the bump

**Read first:** `docs/plans/session-22-implementation-plan.md` §5 Run 6 whole
(the shape this run copies step by step, and its Done paragraph — D1194–D1198
were all in that run's own tests); `bin/session-22-check.sh` whole (the gate
this one is derived from); `tests/contract/test_session_twenty_two_gate_modes.py`
whole; `.github/workflows/ci.yml` lines 220–260; `tests/deployment/test_session22_plane.py`
whole (the live module this one copies: markers, the roster variables, the
`mcp_rpc` fixture, `beta_owner`, `create_reader`, the sweep in `finally`);
`tests/deployment/conftest.py` lines 560–720 (`client_image`,
`run_client_fixture` — how the trip runs a fixture container on the host) and
1744–1810 (`owner_session`).

1. `src/agentic_postgres/__init__.py`: `CURRENT_SESSION = 23`; `VERSION` →
   `1.4.0` with ADR 0162's pricing in the constant's comment (a new
   operator command, an optional `projects/<slug>/clients/` directory, one
   additive member in a metadata tool's result, a new fixture image; no
   manifest, outputs, capability, lock or secret schema moves; a minor,
   confirmed by Session 24's `upgrade plan`).
2. `tests/acceptance-registry.yaml`: the nine requirements of §2 with the
   node ids the runs actually wrote; `ID_PATTERN` gains `GEN` with its
   reason; `evidence_claims.py`: the four claims and
   `OFFLINE_CLAIMS |= {"generated_client", "generated_client_toolchain"}` —
   the two host claims deliberately **not** declared, with the reason in the
   comment beside them (a checkout cannot say what a deployment serves);
   `bin/render-acceptance-matrix.py --write`; `test_acceptance_registry`
   green (every node id collects; every registered proof exists).
3. **The live module** `tests/deployment/test_session23_client.py`, marked
   `p0`, `security`, `live_host`, `requires_environment("APG_LIVE_HOST",
   "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS")`:
   - `test_the_example_client_initialises_on_beta_and_refuses_alpha`
     (`GEN-HASH-001`): the committed example client, run in the toolchain
     image on the host (build it with `client_image`'s shape from the
     checkout's `services/clients/typescript`, `--build-arg BASE_IMAGE`),
     with `APG_REST_URL` = beta's `routes.rest.url` and `APG_TOKEN` = an
     `owner_session` token for beta (the human's own, issued by the service,
     never minted here — D298/ADR 0095), through `--env-file`: `init` →
     `ok` with the fingerprint equal to the committed example snapshot's
     (computed in the test); then the same client with alpha's URL and an
     alpha owner token → `stale_contract` naming both digests (alpha
     publishes the release surface, which is a different document — the
     control that the check discriminates, not merely passes). Then on beta
     `listNotes({limit: 1})` → `ok`.
   - `test_list_resources_on_beta_reports_the_lock_the_plane_confirmed`
     (`AGT-META-001`): an agent on beta (Session 22's `create_reader` shape
     with this module's own names, swept in `finally`), a `tools/call` of
     `list_resources` through `mcp_rpc`, and the result's
     `lock.tools_sha256` equal to what the plane's probe reports
     (`plane_report(project_b, sh_status).tools_sha256`, Session 22's helper
     — import it from that module or move it to a shared helper; grep) and
     equal to the committed example client's `CONTRACT.tools_sha256` read
     from `contract.ts`; on alpha the same call returns a digest that
     differs from the example client's (the control).
   - **Docker on the host is required** for the first proof and the sweep
     has it (the doctor and every Session 18 rehearsal use it as root).
     The gate's usage text says so.
   `pytest --setup-plan tests/deployment/test_session23_client.py` with
   `APG_LIVE_HOST=1 APG_PROJECT_A_OUTPUTS=.generated/fixture-alpha-dev/outputs.json
   APG_PROJECT_B_OUTPUTS=.generated/fixture-alpine-dev/outputs.json` set:
   both proofs collected, neither deselected (D671, D676).
4. **CI** (`GEN-TOOLCHAIN-001`'s CI clause): in `.github/workflows/ci.yml`,
   `session-2-contract` job, after *The local environment stands up, seeds,
   resets and comes down*:

   ```yaml
         # Session 23 (ADR 0204): the committed example client is what the
         # emitter produces, it typechecks under --strict on the pinned
         # toolchain, and `generate --check` refuses a stale one. The runtime
         # smoke runs inside the suite below (test_generated_client_runtime).
         - name: The generated example client is current and typechecks
           run: |
             . .venv/bin/activate
             bin/apg.sh generate --check --project project.example.yaml
             set -a; . ./versions.env; set +a
             docker build -q --build-arg "BASE_IMAGE=${NODE_RUNTIME_IMAGE}" \
               -t apg-client-typescript services/clients/typescript
             docker run --rm -v "$PWD/projects/example/clients/typescript:/work:ro" \
               apg-client-typescript
   ```

   Guard: `test_client_typescript.py::test_ci_typechecks_and_smokes_the_example_client`
   reads the workflow as YAML (the `test_dev_environment.py:942` shape) and
   asserts the step exists after the round trip and names `generate --check`
   and the image directory.
5. **The gate.** `bin/session-23-check.sh` **derived from
   `bin/session-22-check.sh` by diff** (D505, D507, D678, D693, D703, D1108,
   D1109): a derivation script under `/tmp` (copied to the scratchpad) whose
   every substitution is anchored to match exactly once; `readonly SESSION=23`;
   header and usage rewritten whole and read line by line, both halves.
   Offline mode changes: step 6 gains `bin/apg.sh generate --check --project
   project.example.yaml` (the client is current) after the contract checks;
   a new step **8b** *"The generated client typechecks on the pinned
   toolchain"* running the two docker lines from step 4; step 3's suite now
   carries the runtime module (nothing to add — it is `p0 and not future …`);
   the usage prose names the two new claims as offline and the two host ones
   as Session 24's. Host mode: unchanged except prose — the two Session 23
   host claims are collected by the existing `live_host` sweep, **and the
   sweep needs docker, which it has**; the usage says the example client is
   run in the toolchain image on the host. External: unchanged, prose only.
   Session 18's five declaration flags stay (D1133). `SHELL_COMMANDS` gains
   it. **Every `printf` whose format begins with `-` is `printf -- `**
   (D1199; `test_cli_contract.py:756`'s guard runs over it because it is
   listed). `tests/contract/test_session_twenty_three_gate_modes.py` derived
   from Session 22's the same way: `SESSION_TWENTY_THREE_CLAIMS = {"offline":
   ("generated_client", "generated_client_toolchain"), "host":
   ("generated_client_hash", "agent_lock_reported")}`, comment-stripped
   scans (`code()`), the docker refusal, the offline half written from step
   3's JUnit with no deployed document, and the two new steps present in
   `mode_offline` by structure.
6. **Documents.** README's status paragraph at Session 23 and 1.4.0; *Adopt
   `1.4.0`*; every `--through-session 22` a reader is told to type moved to
   23 (`grep -rn "through-session 22\|--session 22" README.md docs/*.md`,
   D693). `docs/scope-closure.md` §1's numbers **counted, not recalled**
   (D1194's lesson from Session 22: they were four sessions stale) and a new
   §12 *What Session 23 left open* (§10 of this plan). `docs/decisions/README.md`
   count. The evaluation report and matrix regenerated where their inputs
   moved.
7. `bin/session-01-check.sh` once on the clean tree (a session close is one
   of the cases the working agreement allows). If it finds something, repair
   and re-run **only the module that failed**, then push.

**Targeted:** `test_evidence_claims`, `test_acceptance_registry`,
`test_cli_contract`, `test_capacity_envelope`, `test_documentation_index`,
`test_session12_documented_path`, `test_repository_contract`,
`test_gate_contract`, `test_session_twenty_three_gate_modes`,
`test_session_twenty_two_gate_modes` (its `SESSION_PREVIOUS` reads 21's; it
must still pass), `test_compatibility`, `test_upgrade_plan`,
`test_upgrade_command`, `test_deployment_suite_shape`, `test_client_typescript`,
then the gate. **Push.** CI green expected; record the run id.

**Done.** The bump (2026-09-12).

`CURRENT_SESSION` **23**, `template_version` **1.4.0**, with ADR 0162's pricing
in the constant's comment: a new operator command, an optional
`projects/<slug>/clients/` directory, one additive member in a metadata tool's
result, and a new fixture image. No manifest, outputs, capability, lock or
secret schema moves and no released migration is added — **a project that
adopts 1.4.0 and never types `apg generate` renders byte-identical artefacts
and deploys the same containers.** A minor, proposed; Session 24's `upgrade
plan` confirms it.

**Nine requirements and four claims.** `GEN-*` joins `ID_PATTERN` with its
reason — *a GENERATED ARTEFACT: what the product writes for a developer to
hold, as opposed to what it serves*; neither `DX` (a documented path a person
walks) nor `DEV` (a developer's own machine) names it. The node ids are **what
the runs actually wrote, read out of the tree**, and four of the nine
requirements' lists differed from the plan's proposals. `generated_client` and
`generated_client_toolchain` are in `OFFLINE_CLAIMS`;
`generated_client_hash` and `agent_lock_reported` are deliberately not, with
the reason beside them.

**The live module** `tests/deployment/test_session23_client.py`: the committed
client run in the toolchain image against beta (`ok`, and a typed read back)
and against alpha (`stale_contract` naming both digests — the control that says
`init()` discriminates), and `list_resources` on beta compared three ways
against the plane's own probe and the digest in `contract.ts`, with alpha
differing. `--setup-plan` with the three variables SET collects both and
deselects neither; the same command with them unset skips both cleanly, which
is the control (D671, D676).

**CI** gains *The generated example client is current and typechecks*, after
the `apg dev` round trip, guarded by a proof that reads the workflow as YAML
and asserts `--check` runs BEFORE the container — a stale client is usually
still perfectly valid TypeScript.

**The gate** `bin/session-23-check.sh`, derived from 22's by diff: twelve
anchored substitutions, each required to match exactly once, **and the run that
matters is the line-by-line read afterwards**. It found two lines no
substitution could have — `claims_through_session(22)` in the declarations
paragraph, and step 9's comment still calling itself *the first gate whose
offline mode writes a half*. Exercising it found two more: shellcheck refuses a
directive with prose after it on the same line and fails the WHOLE FILE with an
error pointing four hundred lines away; and the usage named this session's two
host claims only in prose, where an operator reading a `not_run` verdict cannot
find them. Step 8b reads **one** locked value with `sed` rather than sourcing
`versions.env`, because `set -a; . ./versions.env` exports forty names into the
rest of the process — including into step 9, where evidence is written.
`shellcheck` exit 0, `--help` exit 0 at 173 lines, an unknown mode exit 2.

**Three rows, and two of them are about assertions rather than code.**
**D1236**: two clauses of `GEN-EMIT-001` had no proof at all — the emitted
refusal unions and a write wrapper's required `idempotency_key`/`dry_run`. The
emitter does both; nothing asserted either, because the proofs that existed
were about the IR. Found only because this run's instruction is to write what
the runs *actually wrote*. **D1237**: Session 22's offline-claims test asserted
a global equality for a session-scoped property, which made it a rule that no
later session may declare an offline claim — it failed at the earliest moment
it could. **D1238**: the bump moved `templateVersion` in the committed client
and `generate --check` exited 5 on a file nobody had touched; the version rule
itself behaved correctly, keeping `clientVersion` at `1.0.0` because no digest
moved.

**Battery: 13 mutations, 13 killed, 13 controls green.** The first version of
mutation 1 SURVIVED and was read before it was reported: it added a dead type
alias beside the real union rather than changing the union, so nothing in the
tree claimed anything about it — an **uninformative mutation** (D493), not a
weak test. Replaced with one that widens `AgentRefusal` to `string`; killed.

**CI WAS RED ON THE FIRST PUSH, AND THE CAUSE IS THE SESSION'S MOST
CONSEQUENTIAL FIND** (D1240). `write-session-evidence` reported *"these claims
are not proved by this run: ['generated_client', 'generated_client_toolchain']"*
with **no result recorded** for all forty-odd node ids. Not a failing proof — an
absent one. Four modules written in Runs 2, 3 and 5 carried **no `pytestmark` at
all**, so `-m "contract and not future"` and `-m "p0 and not future and not
live_host and not external"` each collect **0** tests from them (measured, with
`test_generated_client_runtime` at 7 as the control). About fifty proofs had
been green on four commits and had never run in any sweep — only when a person
named the file.

**Collectible and collected are different questions, and this repository had
only ever asked the first.** `test_acceptance_registry` checks every node id
exists, which catches a renamed test and cannot catch this. Repaired by marking
the four, and the class is now guarded by
`test_every_offline_claims_proof_is_swept_by_the_gate_that_reports_it`, which
collects with the gate's own selector. Battery: the mark removed from each of
two modules, both killed, **with the collectibility test green both times** —
the control is the test that was green through the whole defect. Nothing else
found it: not four CI runs, not five batteries whose `-k` named the files, not a
registry guard written for this family. **Registering the requirement found
it**, because the evidence writer is the only reader that consumes a
marker-selected JUnit and names what is missing from it.

**And the repair immediately found something** (D1241). With the four
modules marked, the Session 1 gate went green and the Session 2 job went red —
on `test_a_project_declaring_no_set_generates_the_releases_client`, which needs
the SECOND fixture rendered and got the command's own exit 4 naming the render
command. CI renders one fixture; the gate's step 3 is called *"Render both
fixtures"* and renders two. Written in Run 3, passed locally four times, and
could not fail on a fresh machine until it was in a sweep at all. **A proof
outside every selection cannot report the environment it depends on.**

**Step 7's gate could not run here (D1239).** `bin/session-01-check.sh` step 2
is `bin/lock-dev-deps.sh --check`, which resolves against PyPI, and this WSL
has no outbound HTTPS — measured at the step: `curl -m 20` exit 28, the same
request from a container http 200 in 2.8 s. The one question the gate could not
ask was asked with **the gate's own command** inside the pinned image:
`requirements-dev.txt is current at cutoff 2026-09-03T15:16:21Z`, exit 0 (and
exit 3 first, refusing the container's `uv` 0.12.13 against the pinned 0.12.1 —
the command being right). Run 7's close is **not** blocked: `session-23-check.sh
--mode offline` runs `lock-versions.sh --check`, which is offline by
construction.

**Targeted:** `test_evidence_claims`, `test_acceptance_registry`,
`test_cli_contract`, `test_capacity_envelope`, `test_documentation_index`,
`test_session12_documented_path`, `test_repository_contract`,
`test_gate_contract`, `test_session_twenty_three_gate_modes`,
`test_session_twenty_two_gate_modes`, `test_compatibility`, `test_upgrade_plan`,
`test_upgrade_command`, `test_deployment_suite_shape`, `test_client_typescript`,
`test_generate_command`, `test_mcp_tools`, then `bin/session-01-check.sh`.

### Run 7 — the close (no trip)

1. `bin/session-23-check.sh --mode offline` on this workstation, in WSL,
   with Docker, output to a file (`rm` it first; never `tail`; the exit code
   printed from inside WSL). Expect `evidence/session-23-offline.json` with
   the two offline claims `passed` and exit 0. If a claim is `not_run`, read
   which node id and why (a docker skip is the likely cause) — a skip is not
   a pass. **Read the gate's last twenty lines**: they are the least-executed
   code in it (D1199).
2. `git bundle` is **not** made: nothing is transported. The DR kit is not
   re-exported (no deploy of consequence).
3. Merge `session-23` into `main` fast-forward after CI is green on the
   branch's last commit; delete the branch; push `main`.
4. `CLAUDE.md` §2 in the launch folder (copy it to the scratchpad first,
   CLAUDE.md's own rule): a `SESSION 23 COMPLETE` block in the shape of
   Session 22's — what shipped, the offline half's numbers, **what Session
   24's trip owes this session** (§10: the two host claims, the example
   client run on the host, `list_resources` on beta, and — carried from 22 —
   the deploy through ≥23, the three-half merges for BOTH 22 and 23,
   D1164's confirmation, the two root-run `test_honest_readers` proofs, the
   kit re-export), and the next free `D` and ADR numbers. Memory: the state
   file updated.
5. Mark this run **Done.** with the offline half's claim table pasted, the
   `main` SHA, and the two host claims named as waiting.

**Done.** Session 23 is complete, and **the gate found one more thing on its
way out** (D1242). The first run of `bin/session-23-check.sh --mode offline`
exited **5**: `generated_client` came back `not_run` with *"no result recorded
for `test_printed_commands.py::test_the_generate_hook_prints_the_path_the_process_was_given`"*
— D1240's shape one level deeper, a P0 requirement proved in a `p1` module, in
the Session 1 gate's collection and absent from the sweep that reports the
claim. Repaired on both sides, battery 3/3, and the **second** run passed.

**The offline half, `evidence/session-23-offline.json`** (gitignored, on this
workstation; `checkout_commit` **2121c029**, which is CI-green):

| Claim | Mode | Status |
|---|---|---|
| `dev_environment`, `dev_isolation`, `dev_churn`, `offline_evidence` | offline (Session 22's) | **passed**, re-measured |
| `generated_client` | offline | **passed** |
| `generated_client_toolchain` | offline | **passed** |
| `generated_client_hash` | host | **absent by construction** — Session 24's trip |
| `agent_lock_reported` | host | **absent by construction** — Session 24's trip |

**5570 passed, 0 failed, 3 skipped, 0 errors**, and the three skips were read
rather than accepted: two are `test_root_script_policy`'s parametrized cases
for shell scripts that run no Python, and one is
`test_secret_generation::test_written_manifest_is_owner_read_only`, which needs
a `chown` to root this run does not have. None belongs to a claim. Two tests
more than the failing run's 5568, which is the repair's own arithmetic: the new
drift guard, and the proof that had been outside this sweep entering it.
`source_commit`, `project_keys`, `routes` and `certificate_sha256` are null for
the reason ADR 0202 gives — an offline half measures a checkout, not a
deployment. **The gate's last twenty lines were read** (D1199): step 8b's
`client-typescript: /work typechecks`, step 9's six claims, the two sentences
naming what is still owed, and `session-23-check: offline PASSED`.

**Nothing was transported and nothing needed to be**: no deploy, no container,
no secret, no migration. No `git bundle`, no DR kit re-export. The host stays at
`f61f716` with the same release deployed on both projects, untouched since
Session 21.

**`session-23` fast-forwarded into `main` and the branch deleted** after CI was
green on its last commit. `CLAUDE.md` §2 carries the `SESSION 23 COMPLETE`
block: what shipped, the offline half's numbers, and what Session 24's trip
owes — the two host claims, the deploy through ≥23 that recreates the auth/mcp
container, the example client run on the host against beta and alpha,
`list_resources` on beta, and everything Session 22 already owed, which is a
separate three-half merge. Next free **D1243**; next free ADR **0205**.

---
## 7. Evidence and claims

A claim's verdict is computed from the registry's node ids and JUnit
results, never hand-entered; three statuses (ADR 0163); a skip is not a
pass; a `-k` run writes nothing; an offline claim is declared, never
inferred (ADR 0202). **A generated artefact is a claim about the hash it was
generated from, and its proof reads the served surface** (stage plan §7,
ADR 0204): the offline proofs read a surface served on this workstation by
the product's own PostgREST configuration; the live proof reads the
deployment's.

| Claim | Mode | Measured where | Expected at close |
|---|---|---|---|
| `generated_client`, `generated_client_toolchain` | offline | the gate's offline mode here; CI | `passed` in `evidence/session-23-offline.json` |
| `generated_client_hash`, `agent_lock_reported` | host | Session 24's trip | absent from the offline half (by construction); `not_run` until the trip's merge |
| `plane_confirmed_count`, `agent_tenant_read` (Session 22) | host | Session 24's trip | unchanged, `not_run` |
| every claim through 22 | host / external / offline | Session 24's trip | unchanged |

`evidence/session-23.json` (merged) does not exist at this session's close
and this plan says so. Session 24's merge for this session is
`write-session-evidence.py --session 23 --host-input … --external-input …
--offline-input evidence/session-23-offline.json --output evidence/session-23.json`
— from a checkout at the commit the offline half measured, or the writer
prints the difference. **Session 24's trip owes two three-half merges**, 22's
and 23's, and each offline half names its own `checkout_commit`.

---

## 8. Security invariants this session touches

- **The DX layer holds nothing the human does not hold** (stage plan §8):
  a generated client holds a URL and a token the caller supplied, in a
  closure, and nothing else; no emitted file contains a credential, a
  token, a password, a signing key or a URL with userinfo — `test_no_emitted_file_carries_a_credential_a_token_or_a_userinfo_url`,
  and `test_nothing_the_client_prints_is_the_token` on the running client.
- **A client is not an authority** (stage plan §9's failure mode): `init()`
  refuses on a fingerprint it did not expect and every later call refuses
  until it has one; nothing in the client reads the deployed document, the
  docs route, or a digest computed by somebody else — `test_init_refuses_a_surface_with_another_fingerprint_naming_both`,
  and the live control on alpha.
- **A generated call names only what the contract names** (D1210):
  relations, columns, RPC arguments, tools and tool arguments from the IR;
  filter operators from the capability schema's set; no base table, no
  free path, no free operator — `test_every_emitted_operation_and_column_is_in_the_ir`,
  `test_the_filter_operators_are_the_capability_schemas`.
- **An agent cannot run SQL** (stage plan §8): the wrapper's arguments are
  the lock's; a write requires the two reserved parameters; the runtime's
  scope check is untouched — `test_a_write_wrapper_requires_the_two_reserved_parameters`.
- **A refusal is translated, never relayed** (ADR 0139, D433): the client
  classifies by the body's `code` (PostgREST) and by the seven tokens (the
  plane), and passes nothing else through as a diagnosis.
- **No agent record carries a URL, key, token or caller value** (stage plan
  §8's *a generated client's logging*): the client logs nothing; `smoke.ts`
  prints outcomes and a fingerprint, and its output is scanned.
- **The plane reports which lock it serves, from the lock it carried** (D1201,
  ADR 0195): `null` below schema 4, never a recomputation — the same rule
  D1182 gave the probe.
- **A second implementation of the canonical form is a compared pair**
  (D486, D1203): `js_reproducible` in the generator and the toolchain
  comparison over every committed snapshot.
- **An offline claim cannot report a live half** (ADR 0202): the two host
  claims are undeclared and `claim_mode` refuses the other reading.

---

## 9. Stop conditions

- Rig 23a at the branch point no longer shows `authenticated`'s served
  document equal to the project snapshot: stop; read the printed diff; the
  design of D1200 rests on that equality and the difference must be
  understood before anything is generated against it.
- `js_reproducible` refuses a committed REST snapshot (a float or a big
  integer appears in `contracts/postgrest-openapi.canonical.json` or the
  example project's): stop and read where PostgREST put it; do **not**
  widen the JavaScript canonicalizer to imitate Python's float spelling — a
  second serializer that guesses is the thing D1203 refuses.
- The lock compilation the generator needs cannot be reached without
  importing `bin/mcp-contract.py`: move the sequence to `src/` under ADR
  0175 (names and arities kept, the command delegating); if that move
  exceeds a run, `apg generate` runs `bin/mcp-contract.sh lock` as a
  subprocess into a temporary file — never a second compiler.
- A generated client would read the deployed document, the docs route, or
  any digest it did not compute from a served document (stage plan §9).
- A generated file would carry a credential, or `smoke.ts` prints the token
  in any run.
- The toolchain image cannot be built without network at test time
  (`npm ci` reaching the registry inside a test): stop; the lock is
  incomplete, and the fix is the lock, not a network allowance.
- `--experimental-strip-types` turns out to be required at the pinned Node
  (it is not, at v22.23.2 — measured): pass it in the entrypoint and record
  the row; never emit JavaScript by hand to avoid it.
- Session 24's `upgrade plan` prices this release as a **major**: a stop for
  that plan, not a number to write down here.
- CI red on the branch: stop and read the log; a cancelled run is not a
  failed one (D1059).
- Docker absent in WSL: stop; do not write a proof that skips and call it
  offline evidence.

---

## 10. Open items this session carries and creates

**Carried in, untouched:** everything in `docs/scope-closure.md` §11 that
this session does not repair (the two Session 22 host claims — Session 24's;
`test_honest_readers`' root branch; the uncached first run; `dev prune`; the
seed lint as a scan); the stage plan's §10 list; D1045; the rotation
performed (D860); `replacement_host_restore` (D1028); `fresh_host` and
`documented_path` (ADR 0197).

**Created here, and owed to Session 24's trip:**

- Deploy both projects `--through-session ≥23` (which applies nothing new
  on either — this session adds no migration — but `list_resources` on
  beta answers with its `lock` member only once the auth/mcp container is
  recreated by a deploy whose mount digest moved: **read the container's
  answer, not the file**, D1152/D1153).
- Run `bin/session-23-check.sh --mode host` and `--mode external`; merge
  three halves into `evidence/session-23.json` — and still the three
  Session 22 halves into `evidence/session-22.json` (§7).
- The example client run in the toolchain image on the host against beta
  (`ok`) and alpha (`stale_contract`) — the first execution of
  `test_session23_client.py`, the thirteenth never-executed proof this
  project has carried to a host; `pytest --setup-plan` with the variables set
  is the cheap half and Run 6 step 3 runs it.
- `list_resources` on beta reporting the lock the plane confirmed.
- Everything Session 22 already owed (`CLAUDE.md` §2's list).

**Created here, not addressed:**

- **A Python client is not built** (D1205). The AST test is the evidence
  that the IR carries; a second emitter is one module over `client_ir.IR`
  and is priced for a hardening run, not built to be deleted.
- **The client is a Node client.** `canonical.ts` uses `node:crypto`; a
  browser build would need Web Crypto's `subtle.digest` (async) and a
  bundler nobody has pinned. The stage plan asked for TypeScript, not for a
  browser; recorded so the first person who wants one finds the boundary.
- **The application API is wrapped three operations wide** (D1209). Admin
  and storage stay the operator's and the storage plane's.
- **`app-openapi.canonical.json`'s canonical form is `bin/app-contract.py`'s,
  not `openapi_normalize`'s** (D1203: `ensure_ascii=True`, and Pydantic's
  float literals). Two serializers agree today because the document is
  ASCII; the day it is not, `app-contract.sh --check` and a reader using
  `canonical_bytes` will disagree about the same file. A decision for a
  session that versions that snapshot.
- **PostgREST beside `apg dev` is a rig, not a verb** (D1211). If Session 24's
  Studio wants a served surface on a workstation, that is the session to
  decide whether ADR 0203's boundary moves, with this rig as the measured
  cost.
- **Nothing regenerates a client automatically**, by decision (D1208): the
  hook is a printed line and a gate refusal. An adopter who ignores both
  holds a client whose `init()` will refuse — which is the designed outcome.
- **The filter-operator set is the capability schema's**, for humans too
  (D1210). A human wanting `ilike` through the client is a reviewed
  widening of that schema, which then reaches agents — the coupling is
  deliberate and is written down here so it is not undone by accident.

---

## Appendix — what to consult, and how a run is executed here

**Consult, in this order.** `docs/plans/stage-3-plan.md` §5 *Session 23*,
§7, §8, §9, §10 and its rows D1067, D1068, D1074, D1079; this document's §1;
`docs/plans/session-22-implementation-plan.md` §1 rows D1184, D1187, D1188,
D1194–D1199 (what the last session's runs cost, all in their own tests), its
§5 Run 6 (the bump's exact steps) and its appendix; `docs/scope-closure.md`
§11; ADR 0050, 0065, 0066, 0093, 0119, 0127, 0139, 0158, 0162, 0175, 0181,
0182, 0195, 0198, 0200, 0201, 0202, 0203; `bin/api-contract.py` whole (the
capture and check this client's `init()` repeats at the caller);
`bin/api.py` lines 60–135; `services/auth-api/app/mcp_tools.py` lines 1–60,
255–330, 480–530 and 940–1120 (registration: the argument names the runtime
declares); `services/auth-api/app/mcp_errors.py` whole;
`tests/deployment/test_session22_plane.py` whole; `tests/contract/test_api_behaviour.py`
lines 200–420; `bin/dev.sh`, `bin/dev.py`, `tests/contract/test_dev_command.py`
and `tests/contract/test_dev_environment_cluster.py` (the four shapes the new
command and its tests copy); `/tmp/r23a.py` and `/tmp/r23b.sh` in WSL with
their `.txt` outputs (planning day's rigs — copy them to the scratchpad
before the first `wsl --shutdown`).

**How a run is executed in this repository** (the short form of `CLAUDE.md`
§1 and §5; read those, they are the record of what each of these cost):

- The Bash tool is Git Bash on Windows. The tree is in WSL:
  `wsl bash -lc "cd ~/projects/agentic-postgres && . .venv/bin/activate && …"`.
  Anything with nested quotes, `$VAR`, a heredoc or a loop variable goes in a
  script written with the Write tool to `\\wsl$\Ubuntu\tmp\x.sh` and run
  with `wsl bash -lc "bash /tmp/x.sh > /tmp/x.txt 2>&1"`, printing its own
  exit codes; read the output file back with the Read tool at
  `C:\Users\gmpar\AppData\Local\Temp\x.txt` (Git Bash's `/tmp`) or through
  `\\wsl$\Ubuntu\tmp\x.txt`.
- **The venv does not install the package.** Every Python that imports
  `agentic_postgres` outside pytest needs `PYTHONPATH=src` (or
  `sys.path.insert(0, ".../src")` as `/tmp/r23a.py` does); `python -c
  "import agentic_postgres"` in the activated venv fails without it, and the
  failure reads like a broken checkout.
- File content and commit messages are written with the Write tool and read
  by the script (`git commit -F /tmp/msg.txt`). Never a heredoc for content.
- `chmod 755 bin/*.sh bin/*.py deploy.sh services/clients/typescript/entrypoint.sh`
  before every `git add`.
- Never pipe a suite or a gate into `tail`; redirect to a file, `rm` it first.
- `PYTHONDONTWRITEBYTECODE=1` and `__pycache__` cleared before a battery;
  a fixture that rewrites a module twice in one test with same-length
  versions imports stale bytecode (D1198) — sleep past the second or change
  the length.
- A run's commit: `ruff format && ruff check` (print the exit code), the
  targeted modules — each named module checked for existence individually,
  never by association (D1104) — the derived-document generators whose
  inputs moved, `chmod`, `git add -A`, commit with `-F`, push to
  `session-23`, then read that SHA's verdict: `gh api
  "repos/Virabyan99/agentic-postgres/actions/runs?head_sha=<40 chars>" --jq
  '.workflow_runs[] | [.id,.status,.conclusion] | @tsv'`, judged on HTTP
  status, three buckets (D1059). **Read it every time** (D1120). The
  scratchpad's `s19-ci-watch.sh` / `r8-ci-watch.sh` is the working watcher;
  edit `SHA=`. Never run the gate and a watcher at the same time.
- **A commit message is not evidence that the diff contains what it says**
  (D1116): before the message is written, `git diff --stat` against the list
  of repairs it claims, one line each.
- A run that renames, removes or adds a test function puts
  `test_acceptance_registry` in its targeted list (D1119); one that adds or
  removes a `bin/` command puts `test_cli_contract` there (D1014) and
  `git add`s the command first (D1188); one that adds any `document[...]`
  or `document.get(...)` read to a `bin/` command puts
  `test_container_selectors` there (D1184) — in a `bin/` command the
  identifier `document` MEANS the deployed document; a lock, a manifest or a
  report parsed into a local is named for what it is.
- **A run that MOVES a definition greps the moved TEXT as well as the moved
  name** (D1187): a SQL fragment, an assignment's left-hand side, a literal
  a test scans for; repair each reader to follow its subject
  (`inspect.getsource`, or the value itself) rather than a path.
- **The targeted list is run ONCE, at the run's close, and it is scaled to
  the change.** After a failure re-run only the module that failed; CI is
  the full check (the operator has asked for this twelve times). During a
  run, run the one module under the hand.
- **A targeted list is derived from the tree, never from the plan's text**
  (D1146, D1149): the plan's lists above name what a run ADDS; the grep
  names what it CHANGES, and CI has caught the difference three times.
- Documentation-only commits run nothing before push. Code runs the targeted
  modules; CI is the full check. The gate (`bin/session-01-check.sh`) runs
  on a clean tree at Run 6's close and Run 7, never at a run's close.
- A rig is a throwaway script with a control arm, its output in a file and
  its numbers pasted into the Done paragraph. Never write a measurement you
  did not run (D267). Delete what a rig publishes under `.generated/` unless
  the key already existed; `docker rm -f -v` every container it started;
  `apg dev down` in `finally`.
- The battery: every mutation's anchor pre-flighted to match exactly once
  and a miss fatal (D269); a paired control the mutation cannot reach, in
  the same invocation, green (D499); the reader distinguishes `FAILED` from
  `ERROR` (D386); restore by copy and `cmp`, never `git checkout --`; a
  survivor is evidence and is read as such (D493, D498); a scan over a
  file with good comments is a scan over prose unless the comments are
  stripped first (D1197).
- **A proof calls the product's own command** rather than hand-rolling the
  request that command makes (D1114, D1117): the runtime module runs
  `bin/apg.sh dev up` and `bin/apg.sh generate`, and runs the generated
  client itself in the toolchain image — not a Python re-implementation of
  what the client would send.
- **This session touches no host.** No SSH, no `sudo`, no deploy. If a step
  seems to need one, it belongs to Session 24's trip and goes in §10.

**Grep the plans before measuring a third party.** PostgREST's OpenAPI mode
and proxy URI: `compose.yaml:698-716`, D186, D1114; `follow-privileges` and
the documentation role: migration `0009`, ADR 0050's sessions
(`grep -n "follow-privileges" docs/plans/*.md`); JSON-RPC over the plane:
`test_session8_agent_plane.py:1-160`, ADR 0125, D458 (`sse_result`); Node
in this tree: the docs bundle (`services/docs/Dockerfile`, D202) and the
node-pg fixture; npm locks: `test_client_fixtures.py:150-200`, D238;
canonical JSON: `openapi_normalize.canonical_bytes`'s docstring and
`capability_compiler.canonical_bytes` (two functions, one rule — and now a
third in TypeScript, guarded); the pre-request hook on `GET /`: measured in
rig 23a (it does not refuse the root document); the `authenticated` role's
served document equals the capture's: rig 23a — nothing earlier recorded it.
Nothing indexes the ~1,200 measured facts by subject; `grep` is the index.
