# Session 21 — The agent plane opened to a tenant's domain

**Status:** planned 2026-09-11 at `5a43f12`, Session 20's close. Not started.
**Brief:** `docs/plans/stage-3-plan.md` §5 *Session 21*, and its rows D1083
(the two closures, measured), D1070 (`apg agent init` is this session's last
run), D1072 (the editor association is one line), D1081 (`template_version`
is read from `upgrade plan`). Plus the three items Session 20 deliberately
left with their repairs named: D1121, D1122, D1123.
**Shape:** seven runs. Runs 1–6 are offline and green in CI on a `session-21`
branch; Run 7 is a host trip that ends with the branch merged to `main`.
**Product version at close:** `CURRENT_SESSION` 21; `template_version` as
`upgrade plan` prices it, proposed `1.2.0` (D1081).
**Written for whoever picks this up cold.** Every path is exact, every third
party the session touches is measured in Run 1 before anything is built on
it, and the appendix says how a run is executed in this repository — read
`CLAUDE.md` §1 in the launch folder before the first command.

---

## 0. Where the session starts

Session 20 built the tenant extension point (ADR 0198): a project owns a
migration set, a reviewed surface and a snapshot under `projects/<slug>/`, and
beta serves `api.note_embeddings` from the example set while alpha, at a
schema-1 manifest, serves none of it. **What a project still cannot own is a
tool.** The agent plane is closed to a tenant's domain twice over, both
closures working as designed (D1056, D1083): `mcp_lock` refuses a lock whose
tools are not exactly the six names it was written with, and `required_scopes`
binds to a five-member enum that cannot name an application's relation. An
application built on this appliance therefore gets a first-class REST surface,
a first-class storage surface, and no agent surface at all for its own tables
— which `README.md` §*What is intentionally unavailable* says in as many words.
This session removes both closures, and it is the larger security decision of
Stage 3 because the vocabulary and the roster are the two definitions with the
most readers in the tree (§1).

**What is deployed** (measured 2026-09-11, `CLAUDE.md` §2): host
`62.238.99.122`, checkout `90b3b446`, deployed release `671bb048` on both
projects, alpha's manifest at project schema 1 and beta's at 5 declaring
`projects/example`, outputs v17, 31 release migrations applied on alpha and
32 on beta, doctor 10/10, backups and the B2 mirror current. The deployed
lock on both projects is the same six-tool document compiled from
`capabilities.example.yaml`. A fresh DR kit is at `/home/op/kit-2026-09-11`,
verified at `90b3b446`, **and has not been copied off the host** — Run 7's
first step.

**What this session builds, in one paragraph.** The scope vocabulary's data
class becomes a *function of a reviewed surface* — one `<relation>:read` and
`<relation>:write` per published relation plus `meta:read` — computed by one
function in `scope_registry`, with the storage and administrative classes
still enumerated in the schema and the partition still asserted, per surface
(ADR 0200). The runtime registers its tools *from the lock*, by kind and
shape rather than by name; the loader refuses a lock that is internally
inconsistent with the contract it was compiled from, not one that is not six
(D933 closed for both things it blocks). The lock goes to schema 4 and
carries the vocabulary, and the auth service mounts it so the issuer's
ceiling is a function of the deployment's vocabulary rather than a hardcoded
map (D1126). A project owns a capability manifest and a compiled contract
beside its surface — `projects/<slug>/capabilities.yaml` and
`projects/<slug>/contracts/mcp-capabilities.canonical.json` — compiled
against the *merged* surface and the project's own snapshot, and the deployed
lock is the release's contract joined with the project's, narrowed by the
profile (ADR 0201). Outputs v18 records it. Then `apg agent init` scaffolds a
capability entry from one selected reviewed operation, and the example
project's own manifest is what that scaffold produced. The three things
Session 20 left — D1121, D1122, D1123 — are Run 1's, before anything new.

**The premises were checked against the tree before this plan was costed**,
and two of the stage plan's sentences are wrong in the reassuring direction
(D1124, D1126). The largest finding is that the roster is written in four
places by decision and guarded by two tests that read the *source text* of the
runtime modules, and that the vocabulary has a reader the stage plan does not
name: the token issuer, in a container that has never seen the lock.

**Read before touching anything**: ADR 0006 (the vocabulary lives in the
schema), 0079 and 0100 (the ceiling; three classes and their partition), 0120
(a tool is one or more capabilities), 0127 (the lock is the answer), 0140 (a
hidden tool is still callable), 0141 (a denial is audited, so `begin` runs
before the scope check), 0177 (a field arrives at its version), 0183 (a
profile only narrows), 0184 (cases are derived per frozen field), 0195, 0196,
0198; D486 and D933 in `docs/plans/session-16-implementation-plan.md` §1;
D1056 in Session 19's; `FINDINGS.md` F-025 in the launch folder, which is the
account this session is written from.

---

## 1. The divergence table

Six columns, next free number after this table **D1151**. Rows D1124–D1139
were measured at planning on 2026-09-11 at `5a43f12`; the runs add theirs
below them as they go (D1140–D1143 are Run 1's, D1144 Run 2's, D1145–D1146
Run 3's, D1147 Run 4's, D1148–D1149 Run 5's, D1150 Run 6's).

| # | Said | Repository does | This session | Why | ADR |
|---|---|---|---|---|---|
| **D1124** | Stage 3 plan §5 Session 21: *"`EXPECTED_TOOL_NAMES` replaced by the lock's own tool list."* | **The roster is written in four places by decision, and guarded by tests that read source text.** `services/auth-api/app/mcp_lock.py:70` derives `EXPECTED_TOOL_NAMES` from `METADATA_TOOLS`/`READ_TOOLS`/`WRITE_TOOLS` and `EXPECTED_KINDS` from the same three; `mcp_tools.py:127` writes `TOOL_NAMES` out again *"two lists that must agree, not one list read twice"* (D486) and registers six tools with six `@server.tool` decorators carrying typed Python signatures (`_create_note(p_title: str, p_content: str, idempotency_key: str, dry_run: bool)`); `capability_compiler.PLANNED_TOOLS` is the reviewed answer the compiled set is compared against. Beyond those, `test_mcp_catalog.py:303` asserts `tool_count == 6` **and** the string `"exactly six"` in the catalog prose, and `test_api_migrations.py:1330` asserts the SOURCE of `mcp_tools.py` contains `"there are exactly six"` and the source of `mcp_lock.py` contains `"names != EXPECTED_TOOL_NAMES"` — with a message that already names this session: *"if that is deliberate, D933 may be closed and ADR 0196 revisited."* `test_mcp_tools.py` reads the constant at twenty sites. | **The runtime registers from the lock by KIND and SHAPE, never by name.** Four shapes: the metadata pair (fixed names, the runtime's own, required in every lock); a resource-selecting read (`query_resource`'s parameters: `resource, columns, filters, order_by, limit`); an argument-free RPC read (`run_report`'s: none); a write (the lock's argument list plus `idempotency_key` and `dry_run`). `EXPECTED_TOOL_NAMES`, `TOOL_NAMES` and `PLANNED_TOOLS` go; what replaces the refusal is structural (D1130). Every guard above is **replaced by a stricter one under ADR 0200** (the non-negotiable's one permitted route): the catalog asserts the count the contract carries; the ADR 0196 asymmetry test asserts D933 is CLOSED — a five-tool lock loads. Run 3. | Question 5 of the defect pattern, asked of a definition with four writers and a guard that would have gone red on the first correct change. The text guards were right to exist — they made the roster's closure a fact a test could read — and they are what makes this row a decision rather than an edit. | 0200 |
| **D1125** | Stage 3 plan §5: *"`$defs/agent_scope` generated from the reviewed contract's resources."* | **The vocabulary has five readers beyond the schema, and one of them is in a container.** `scope_registry.agent_requestable_scopes()` and `approved_scopes()` read the two enums; `assert_classes_partition_the_vocabulary` compares three classes to the union. `services/auth-api/app/scopes.py` `ROLE_SCOPES` hardcodes `notes:*` and `tasks:*` into four ceilings, and `service.py:207` and `:411` refuse an agent record or a request whose scopes exceed the ceiling — **so a tenant's scope is refused at agent creation, before any lock or manifest is consulted.** `bin/dev-token.py:340` reads the ceiling through `permitted_scopes`. `test_scope_registry.py:31` asserts the data class is exactly ADR 0003's five; `test_capabilities_manifest.py:196` refuses names outside the enum. The MCP runtime's call-time check (`mcp_tools.py:224`, held against the lock's `required_scopes`), the verifier (`claims.py:140`: a sorted, deduplicated array of strings) and the SQL (`app_private.is_scope_set`: sorted, deduplicated, no NULL; the hook compares arrays exactly) are **vocabulary-agnostic**. | **The data class is a function**: `scope_registry.vocabulary(surface)` returns `{f"{r}:read", f"{r}:write"} for r in surface["relations"]} | {"meta:read"}`; the storage and administrative classes stay enumerated in `$defs/storage_scope` and `$defs/administrative_scope`; `assert_classes_partition_the_vocabulary(surface)` asserts the partition per surface. **The ceiling becomes a function of the vocabulary** (`scopes.py` keeps the role→class mapping and stops naming any data scope). A relation whose derived names would collide with an enumerated class — `objects`, `admin_users`, `admin_agents`, `admin_audit` — is refused by `api_surface` at load and at merge, which is how the derived class *cannot* name an administrative or storage scope. Run 2. | Every reader that stays enumerated is a copy of the vocabulary that goes stale on the first tenant relation, and the one in the issuer fails in the worst place: a refusal on the admin endpoint that reads as a policy decision. ADR 0006's rule stands — no second copy — with the copy replaced by a computation. | 0200 |
| **D1126** | Stage 3 plan §5 and §8: *"The MCP runtime holds no credential … 21 touches the roster, not the environment."* | **The lock is mounted into `mcp` only** (`runtime_override.py:834`; `settings.py:265` requires `APG_MCP_LOCK_FILE` in the MCP settings alone), and the auth service — the same image, a different entrypoint — has no lock, no schema (ADR 0084: the build context cannot reach `src/` or `schemas/`) and no way to learn a tenant's scope. The issuer's ceiling is `scopes.py`'s static map (D1125). | **Lock schema 4 carries a `vocabulary` block** — the derived data class, and the two enumerated classes verbatim from the schema at compile time — **and the auth container mounts the same lock read-only** under the same variable, so the issuer computes its ceilings at startup from the deployment's vocabulary. ADR 0155 does the rest: a lock whose bytes changed recreates both containers on the next deploy. The environment changes by one mount and one variable, and holds no credential. Run 2, with `runtime_override`'s guard tests. | The stage plan's sentence was true of the runtime and false of the *plane*: the issuer is part of the authorization path, and a vocabulary it cannot read is a vocabulary it refuses. Putting the answer in the lock rather than a second file keeps ADR 0127's rule: the lock is the answer, read once at startup. | 0200 |
| **D1127** | D933: *"a project disabling a write capability"* does not deploy; ADR 0183 §*what a profile cannot do*: *"a project that must not expose a write disables it in the capability manifest, where the compiler compiles it out entirely."* | **The manifest ADR 0183 points at is per HOST, and the deployed lock is not compiled from it.** `bin/deploy-project.py:2151` runs `mcp-contract.sh lock --outputs … --project …` with no `--capabilities`, so the lock is compiled from the release's `capabilities.example.yaml`; the host's `capabilities.yaml` reaches the render's `capabilities.enabled` list and `capabilities_sha256` only (D930's two-digest item, unchanged here). So `enabled: false` on the host has never reached a lock, and the "project" in D933 was a host. Both host files are schema 1. | **A project's own capability manifest, tracked, at `projects/<slug>/capabilities.yaml`** (schema 4), named by a new optional `mcp.capabilities: projects/<slug>` key in the project manifest (schema 6, forbidden below 6 — the same shape as `migrations.set`). It declares the project's own capabilities and may name release capabilities to leave out of *this project's* lock (`release: {disabled: [create_note]}`; a metadata capability may not be named, a name the release does not declare is refused). The lock is the release's contract joined with the project's, then the profile. **D933's first thing closes per project, in the narrowing direction, at compile time**; its second closes with D1124. **D930 stays open** and is named in §10: the host file's role is unchanged. Run 4. | ADR 0198's rule applied to a capability: a release is its commit, and a tool an agent can call is code, not configuration. Compiling the lock from a host file would also downgrade it — a schema-1 host manifest compiles a schema-1 contract with no budgets (ADR 0177), which is the reason the deploy never did. | 0201 |
| **D1128** | Stage 3 plan §5: capabilities *"over a tenant's domain … from a selected reviewed operation."* | **The compiler resolves against the release surface alone.** `bin/mcp-contract.py:79` loads `api_surface.load_surface()` and `SNAPSHOT_PATH`; `capability_compiler.surface_operations` reads `relations`, `rpcs` and `agent_rpcs`. Session 20's `merged_surface(release, project)` and `load_project_snapshot` exist and nothing in the MCP path calls them. The project surface (schema 2) carries no `agent_rpcs`, no `agent_write_rpcs` and no `forbidden_schemas` (`PLATFORM_ONLY_SECTIONS`). | `compile_canonical` and `compile_lock` take the merged surface and the project's declared objects when a project declares capabilities. A tenant capability resolves against the project's `relations` and `rpcs` — **published objects only**: `agent_rpcs` stay platform-only, so a project cannot declare an agent-only unpublished function, and the merged `forbidden_schemas` are the release's. Run 4. | The two agent sections describe the whole database (Session 20's reason for forbidding them at schema 2), and a tenant tool over an unpublished function would be a tool the reviewed OpenAPI does not name — ADR 0050 from the other direction. | 0201 |
| **D1129** | Stage 3 plan §5: `list_resources` and `describe_resource` *"answering for the tenant's resources from the lock (ADR 0127 unchanged)"*; a capability is a read or a write. | **Reads have two shapes and a tenant may want a third.** `query_resource` takes the caller's query shape over a relation; `run_report` takes **nothing** — an argument-free POST to an RPC with `max_rows: 1`. A read over an RPC *with arguments* (the pgvector example's obvious next step, `search_similar(p_embedding)`) has no shape in the runtime: an RPC argument is a caller value in a request body, which is a write's shape (D486, D470). | **Not built.** The compiler refuses a read capability whose operation is an RPC with arguments, naming the two read shapes it compiles and the reason. Recorded in §9 and §10 as the shape Stage 4's proposal system inherits; the metadata tools answer for every resource the lock carries and change by nothing. | Three shapes derived from the lock is a runtime that registers from data; a fourth invented for a case no reviewed surface yet has is D267's shape one level up. The refusal names its remedy — publish the query as a view, and read it as one. | 0200 |
| **D1130** | This plan D1124: the refusal *"becomes structural"*. | **The runtime cannot recompile, so it cannot compare a lock to the contract.** ADR 0084: standard library only, no `agentic_postgres` import. What it can check: `tool_count`, kinds, the metadata pair, every read carrying resources and every write an argument list — and a digest. `canonical_sha256` is the *contract's* digest and does not cover a lock's tool list after the profile. | **Lock schema 4 carries `tools_sha256`**, the compiler's digest over the canonical bytes of the tool list as compiled, after the profile; `load_lock` recomputes it and refuses a mismatch. A tool added, removed or edited by hand is a digest the compiler did not write. With it: kinds in `{metadata, read, write}`, exactly the metadata pair, `tool_count`, and the per-kind shape. Run 3. | The property ADR 0127 wanted — *enumerated, not discovered* — is kept as *compiled, not edited*. Six was the shape of the only contract there was; the digest is the shape of every contract there can be. | 0200 |
| **D1131** | D1121: `honest_readers`' live half *"reads as whoever invoked the gate, and the gate runs as root."* Its repair is named there. | Measured again at `5a43f12`: `test_session20_tenant.py:478` reads `os.access(generated, R_OK \| X_OK)` and skips when true, which is always for root; `test_honest_readers.py:100` and `:165` skip root with *"root traverses a 0000 directory"*. | **Run 1 repairs it as D1121 says**: the proof runs `bin/migrate.sh render` as the checkout's owner (`sudo -u "$(stat -c %U REPO_ROOT)"`) when `geteuid() == 0`, and it **constructs** the root-owned state on `.generated/alpha-dev` (a `chown root:root` on the directory as root) and **restores** it in `finally` (`chown` back to the recorded owner and group), asserting the restore by `stat` before returning. The node id is renamed to say so; `test_acceptance_registry` is in the targeted list (D1119). | Both halves, or it measures the wrong thing; and a proof that changes the host must put the host back, verified, or the next proof in the sweep inherits the state. | — |
| **D1132** | D1122: `bin/dr-kit.sh verify` *"must migrate a stored deployed document to the current schema BEFORE validating it."* | `src/agentic_postgres/dr_kit.py:325` calls `deployed_output.validate_deployed_document(document)` on the stored bytes; `output_migrations.migrate_v16_to_v17` exists and is not called on this path. **The arm exists**: `~/dr-kits/dr-kit-1.0.1` in WSL is the v16 kit exported 2026-09-06, which exits 5 against this checkout. | **Run 1**: `verify_kit` migrates each stored deployed document to `CURRENT_VERSION` through `migrate_rendered`'s deployed twin (whatever the chain needs — the kit carries its own bootstrap state and secrets listing, so the parameters older steps take are read from the kit, never invented) and validates the result; a document it cannot migrate is reported as *cannot be carried to version N*, a third outcome (ADR 0195), never as *does not validate*. Arm: the v16 kit exits 0. Control: the kit exported 09-11 at v17 still exits 0, and a kit with a byte flipped in a document still exits 5. `REC-KIT-003`. | A DR kit is by construction read at a later release than the one that wrote it, so validating it against the reading release is the one rule that guarantees failure in the only scenario the kit exists for. | — |
| **D1133** | D1123: *"decide which: re-add the four declaration flags to the session gate (reversing D1021), or document that the older gate writes the half."* D1021: a gate must not carry flags *its own proofs* never read. | `bin/session-20-check.sh --mode host` runs the cumulative suite — `claims_through_session(20)` — so Session 18's declaration proofs **run in it**, skip without the flags, and outvote the pass Session 18's own gate recorded (`_SEVERITY` in `evidence_claims.py:584`: failed, skipped, passed). D1021 was applied to Session 20's gate as if "its own proofs" meant *the proofs it adds*; the proofs it *runs* include every earlier session's. | **The flags come back, optional, in `session-21-check.sh` and stay in every later gate**: `--kit-dir`, `--replacement-host-outputs`, `--restore-evidence-file`, `--rehearsal-evidence-dir`, parsed and exported exactly as Session 18's parses them, with the pre-flight loop D1108 removed restored beside them. **One sweep writes the host half.** `--junit` stays repeatable for the offline and host halves of one session; it is not a bridge between two gates. D1021's rule is restated: a gate carries every declaration a proof it runs can read. | The two rules never collided; one of them had been misread. A skip is still not a pass (ADR 0163), and four claims measured passing on 2026-09-11 will be recorded passing on the next trip because the same sweep reads the declarations. | — |
| **D1134** | D1105: eleven test sites chain the outputs migrator by hand; the repair is one helper, *"left for a session that can give it a battery of its own."* | This session bumps outputs to v18 (D1136), which is the twelfth edit of those sites. `output_migrations.migrate_rendered` exists (`:222`) and takes the per-step keyword parameters; the tests chain by hand because each step's parameters differ. | **Run 4 writes the helper first**: `tests/contract/_outputs.py::carry_to_current(document, **fixture_parameters)` walks `CURRENT_VERSION` from `detect_version`, and the eleven sites call it. Battery: a step skipped inside the helper kills the v14 fixture's test; a fixture that carries a field its version does not have is refused (Session 20's fixture-by-subtraction lesson). Then v18 is one edit. | The class whose repair is mechanical and whose discovery is not; taking it in the run that would otherwise pay for it a twelfth time. | — |
| **D1135** | ADR 0006's rejected alternative: *"Deriving scopes from the OpenAPI document at validation time … a vocabulary that changes when an unrelated service is redeployed is not a contract."* | The derivation here reads the **reviewed surface file** — hand-written, digested into every lock as `compiled_from.api_surface_sha256`, compared against the served document by `api-contract.sh --check` — never the served OpenAPI. It changes on a reviewed edit and on nothing else. | ADR 0200 says so explicitly, and the guard is `test_the_vocabulary_is_derived_from_the_reviewed_surface_and_never_from_a_served_document`: the function takes a surface document and no path, no URL and no snapshot. ADR 0006's other two alternatives stay rejected; its decision is amended rather than superseded — the schema is still the sole authority for the two classes it enumerates and for the *shape* of the third. | The objection was to a source that moves without review, and the reviewed surface is the artefact this repository moves with the most ceremony. | 0200 |
| **D1136** | Stage 3 plan §7: *"every new deployed-document field is classified in the matrix in the session that adds it (D702, D1029)"*, and D1111: the prefix AND the bare leaf. | The deployed document's `mcp` block carries `capability_contract_sha256` and `capability_lock_sha256`; the isolation matrix names `mcp.capability_lock_sha256` at `:129` and the `mcp.` prefix at `:209`; the doctor's redaction map classifies the block. A project's contract is not in the document at all. | **Outputs v18**: `mcp.project_capabilities: null \| {root, contract_sha256, tool_count, capability_count}` on both branches, from the manifest's `mcp.capabilities` key; `mcp.capability_contract_sha256` keeps its name and digests **the canonical the lock was compiled from** (merged for a project that declares capabilities), which the migrator leaves as recorded. Classified in the matrix (the digests may differ between projects; the root carries no authority) and in the doctor's map (printable, prefix and bare leaf), in Run 4, with the D1111 control: a project without capabilities renders the explicit null. | Paid in advance, with the row that says it was paid in advance a third time (D1111). | 0201 |
| **D1137** | Stage 3 plan D1070: *"`init` is Session 21's last run … `validate`, `dry-run` and `test` get their `apg` names for free."* | `bin/apg.sh` resolves `apg agent init` to `bin/agent.sh init` by construction (a verb IS a script, ADR 0002); no `bin/agent.sh` exists. `validate` is `bin/mcp-contract.sh check --project FILE`, `test` is `bin/render-evaluation-report.py --check` over the harness, `dry-run` is the runtime's (ADR 0182). | **`bin/agent.sh` with one verb, `init`**, and a usage that names where the other three live rather than wrapping them (D707: renaming a surface buys nothing). `init --project FILE --operation NAME [--kind read\|write]` streams one capability entry to stdout, derived from the merged surface: a relation → a read with the view's column list, no filters, no ordering, `max_rows` 100; an RPC → a write with the reviewed argument list, `supports_dry_run: true`, `requires_approval: true`, `idempotent: false`, every argument redacted; scopes derived; `version 1.0.0`, `lifecycle active`, `risk` `low` for a read and `moderate` for a write. It writes no file. `SHELL_COMMANDS` gains it (D1014). Run 5. | A scaffold cannot express what the compiler cannot emit because it is written from the same operations table the compiler resolves against; the defaults are the conservative end of every bound a profile could narrow (ADR 0183's polarity, D925). | 0201 |
| **D1138** | Stage 3 plan D1072: *"one documented line associating the schema, in Session 21's documentation beside `init`."* | The convention is the YAML language server's modeline, `# yaml-language-server: $schema=<path>`, read by the Red Hat YAML extension and by every editor that embeds that server; a `yaml.schemas` setting is the other form. **Nothing in CI can measure an editor**, and the schema at version 4 must admit a tenant scope by *shape* (D1125) for the editor's validation to accept one — the approval half is `mcp-contract.sh check --project`, which is D1072's point. | The line is written into `projects/example/capabilities.yaml` and documented in README §*Giving an agent your tables*; **recorded as documentation and not as a proof**. The operator's reading of it in an editor is a reading, pasted into Run 5's Done paragraph if made. | Never write a measurement you did not run (D267), and never call a documented line a guarantee. | — |
| **D1139** | ADR 0183 §*what a profile cannot do*: *"Remove a tool. The runtime refuses a lock with fewer than six (ADR 0127)"*, and D933's row: *"whether a disabled capability leaves the lock … or the runtime's roster becomes the manifest's is an ADR-shaped decision."* | The reason was the runtime's refusal, which D1124 removes. What ADR 0183 was protecting — that a profile is a monotone restriction in a vocabulary of seven bounds the runtime reads — is untouched by where a capability is disabled. | **The profile still cannot remove a tool**; a project removes a release tool in its own capability manifest (D1127), where the compiler compiles it out. ADR 0201 amends 0183's sentence to say where removal lives and why it is not the profile: a profile narrows *values* on tools that exist, and the roster is a *set*, decided one level up. | Keeping the two levels apart is what keeps `apply_profile`'s seven-field vocabulary the whole of what a profile can say. | 0201 |
| **D1140** | This plan §5 Run 1, rig 21a: *"a closure whose `__signature__` is an `inspect.Signature` assembled from a lock-derived parameter list"*; arm B *"`server.add_tool(Tool(...))` with an explicit `parameters` JSON schema"*. | **A `Signature` alone is refused at registration, and an explicit schema is advertised without being enforced.** Rig 21a on the pinned FastMCP 3.4.0, through the in-memory client: the closure with a constructed `__signature__` and nothing else raised `KeyError: 'p_note_id'` from pydantic's `_arguments_schema` — it reads `get_type_hints()`, i.e. `__annotations__`, and never consults the signature for types. With `__annotations__` set as well: `tools/list` carries exactly the derived names with `additionalProperties: false`, an undeclared argument is refused (*unexpected keyword argument*), a missing one is refused (*missing required keyword only argument*), and `timeout=0.1` fires around a 2 s sleep — identical to the control's static function. `FunctionTool(name=, parameters=<schema>, fn=)` via `add_tool` **advertises** the same shape and **enforces none of it**: an undeclared argument and a missing one both reached the handler. | **Run 3 registers by constructed signature AND annotations, never by an explicit schema.** The rig's output is `~/rig21/rig21a.txt` (rig at `/tmp/rig21/rig21a.py`). | The fourth arm is exactly the shape §7 warns about: a bound that looks enforced to every client and enforces nothing. Found because the rig asked the two negative questions of every arm rather than the positive one. | 0200 |
| **D1141** | D1122, and this plan's D1132: `dr-kit.sh verify` *"must migrate a stored deployed document to the current schema BEFORE validating it"*; *"`migrate_v16_to_v17` is exactly the function that would make the stored document readable."* | **The named repair cannot be built without reversing a standing decision, and the function named does not do what the row says.** `migrate_v16_to_v17` — every step in the chain — calls `require_kind(document, "rendered")`; `test_a_deployed_document_is_not_migrated` asserts the refusal under ADR 0012 (*"an observation republished under a version that never measured it"*); `migrate_rendered` takes eighteen rendered-branch parameters a deployed document does not have. There is no deployed-branch migrator anywhere. And `outputs.schema.json` admits exactly **one** `schema_version` on both branches — `enum: [17]` — so every reader that validates a deployed document refuses any document an earlier release wrote. Measured at `7fae1ae`: the v16 kit at `~/dr-kits/dr-kit-1.0.1` exits 5 on both documents (*not valid under any of the given schemas*); the v17 kit copied off the host today exits 0. | **`verify` checks a stored document by the version it declares, three ways** (`dr_kit.verify_deployed_document`, `KIT_FIRST_OUTPUTS_VERSION = 16`): the current version validates against the full schema exactly as before; a version between the facility's first and the current one is checked for what a kit is FOR — `document_kind: deployed`, this project's key, no sensitive key anywhere — because a restore reads identity and provider ids from it and nothing else; a version above the current one, or below 16, is reported as a document *this release cannot read*, never as *does not validate* (ADR 0195's third outcome). `REC-KIT-003`'s two proofs; the v16 kit is the arm, the v17 kit and a corrupted copy the controls. | Question 6 of the defect pattern asked of a plan row: D1122's author and the plan both believed a migrator existed for the document because one exists for the other branch with the same version numbers. The rule that stopped it — a deployed document is an observation and is never rewritten — is the right rule, and the kit's reader had to be made version-aware rather than the document made current. | 0189, 0195 |
| **D1142** | `deployed_output.validate_deployed_document` is called by five readers — `dr_kit.py` (export and verify), `fleet.py:96`, `bin/project-retire.py:93`, `write_deployed_document` — and by every command that loads a deployed document through it. | **Every one of them refuses a deployed document an earlier release wrote**, by the same `enum: [17]` D1141 measured, from the moment a newer release is checked out until that project is redeployed. On the trip that window is short; on a replacement host built from a kit it is the whole restore. Measured only through the kit's path; the others share the function and were not exercised. | **Recorded, not repaired.** The kit's verifier is the one reader whose whole purpose is that window, and it is version-aware now. Whether `fleet`, `doctor` and `project-retire` should read an older document (and what they may say about it) is a decision for the hardening session, §10. | D600's rule — every reader of the deployed document is guarded against the schema — was applied with a single-version schema, so "guarded" means "refuses the previous release's document". That was invisible while every read happened after a redeploy. | 0195 |
| **D1143** | This plan §5 Run 1: *"the registry gains the requirement here (its proofs are offline and the constant does not move for it — `target_session: 21` is set in Run 6 with the rest)."* | **The registry refuses an entry whose `target_session` exceeds `CURRENT_SESSION`** (`test_acceptance_registry.py:131`: `1 <= target_session <= CURRENT_SESSION`), and every entry must carry one. An entry with no target session or a future one cannot be committed before the bump. | `REC-KIT-003`'s two proofs are written and green in Run 1 and **registered in Run 6** with the rest, exactly as `AGT-*` are. The plan text is corrected here rather than in place. | D690's rule seen from the registry's side: a session's requirements arrive with the constant, all of them, and a proof may exist before its requirement does but not the other way round. | — |
| **D1144** | `deploy.sh --through-session N` is admitted for every N from 2 to `CURRENT_SESSION` (`bin/deploy-project.py:1894`, D59); the auth service exists from session 6 (`profiles: [session6]`). | **The lock is compiled only when `through_session >= AGENT_PLANE_SESSION` (8)** (`deploy-project.py:2159`), and since this run the issuer REQUIRES `APG_MCP_LOCK_FILE` (`settings.REQUIRED_VARIABLES`) and the override mounts the lock into `auth` unconditionally (D1126). A deploy through session 6 or 7 would therefore start an issuer whose mount source does not exist -- refused by the step 6b mount pre-flight, or by `settings.load` if it got that far. Nothing has deployed through a session below 8 since Session 8, and both production projects are through 20. | **Recorded, not repaired.** The honest floor for a deploy that starts the issuer is now 8, and lifting `deploy.sh`'s admitted minimum from 2 is a D59 change for Run 6 (the bump) or Session 25 to take with the operator; a conditional mount would be a lock-less issuer that starts, which is D381's shape. | ADR 0177's rule applied to a container rather than a field: a capability arriving at a version must be refused below it, not silently absent. The consequence was found by reading the deploy's order (the lock is written before step 6, so the mount is satisfied on every deploy that compiles one) rather than by a test, because no test deploys through 7. | 0200 |
| **D1145** | D1124 counted the roster's writers: four places in the runtime and the compiler, plus two source-text guards. The stage plan's §11: *"for 21 every reader of `agent_scope` and `EXPECTED_TOOL_NAMES`"*. | **Two more readers keyed on a tool's NAME rather than its shape, outside the runtime, and neither imports the roster constant** -- so no grep for `EXPECTED_TOOL_NAMES` finds them. `evaluation_harness._read_cases` decided whether a read case names a resource with `if tool_name == "query_resource"` (twice), and `test_evaluation_harness`'s dispatcher chose `query_resource` versus `run_report` by the same literal and imported `WRITE_TOOLS` for the third branch. Under a tenant's lock the harness would have derived the report shape for every read whose tool was not called `query_resource`, and the dispatcher would have found no branch. | Both decide by shape: `_selects_a_resource(resource)` reads the resource's operation method (`get` selects, `post` runs one RPC), and the dispatcher reads `lock.tool(tool).read_shape` and `.kind`. The runtime's two read functions take the tool's name as a keyword whose default is the release's, so registration always passes the lock's. | Question 5 of the defect pattern, in the form D979 warned about: the second reader was not a caller of the definition but a string comparison against one of its values, which is invisible to every grep for the definition's name. The name `query_resource` meant "relation read" for exactly as long as there was one. | 0200 |
| **D1146** | Run 3's reader enumeration: a grep for the roster constants over a NAMED list of test modules, and the appendix's rule that a run's targeted list holds every guard module whose subject it touched. | **`tests/contract/test_metrics_surface.py:40` imported `TOOL_NAMES` from the runtime and was in neither list.** CI was RED on `4555645` on all three jobs -- every one collects the module -- and the local gate reproduced it in ten seconds: *ImportError: cannot import name 'TOOL_NAMES'*. A second grep, over the whole of `tests/`, `bin/`, `src/` and `services/`, found it and nothing else. The first grep's file list was written from the modules I could think of, which is D1104's error in the other direction: not a module named and dropped, but a module never named. | The import replaced by a fixture roster with a comment; the row recorded; **the rule sharpened**: a grep for a removed definition's readers runs over the whole tree, never over a list, and `git grep -n <name> -- tests bin src services` is the form. Repaired in Run 3's second commit, CI read. | Question 5 again, at the cheapest possible point -- found by CI six minutes after the push, reproduced by the gate in ten seconds -- and recorded because the plan's own appendix says a commit's CI verdict is read every time (D1120), and it was. | — |
| **D1147** | ADR 0201 §3 as written at planning: *"`compile_canonical` runs twice … and `compile_lock` joins the two canonicals: tools concatenated with the release's disabled ones removed."* | **A disabled capability behind a grouped tool cannot be removed from a compiled tool.** `query_notes` and `query_tasks` compile into ONE `query_resource` tool with two resources, two discovery scope sets and one merged bound per field; disabling `query_notes` at the contract level means recompiling the tool from the remaining capability, which is `compile_canonical`'s job and nobody else's. And a project's capabilities have no surface to be approved against, no snapshot to be checked against and no contract id to be named by except its reviewed surface's -- so `mcp.capabilities` without `migrations.set` is a manifest with nothing to open. | **The join is of MANIFESTS**: `capability_manifest.joined_capabilities(release, project)` -- the release's entries less `release.disabled` plus the project's -- compiled ONCE against the merged surface and the project's snapshot with the joint contract id; `lock` first proves both committed contracts are what their manifests compile to (exit 5 otherwise). `mcp.capabilities` requires `migrations.set` with a reviewed surface and a snapshot, each refused by name with the command that writes it. ADR 0201 §3 amended in place with the reason. The example project's manifest and the positive CLI arms are Run 5's, with the file the scaffold emits; this run's tests drive a hand-built manifest under `tmp_path` over the example project's committed surface and snapshot. | The plan's sentence described the result correctly and the mechanism wrongly, and the first grouped read would have found it on a host; an ADR amended before the build is cheaper than one amended after a trip (D1116's shape, avoided). | 0201 (amended) |
| **D1148** | ADR 0184 / `EVAL-HARNESS-001`: *"every enabled capability needs a positive and an adversarial case of each origin"*, enforced by `evaluation_harness.coverage`; ADR 0201 §5: the scaffold emits `requires_approval: true`. | **The two rules had never met.** D870 reclassifies an approval-requiring write's derived positive as the `requires_approval` adversarial case, so such a capability has NO derived positive by construction -- and `coverage` refused it: `render-evaluation-report.py --write --project project.example.yaml` exited 5 on the first manifest the scaffold wrote (*"capability 'set_note_embedding' has no derived positive case"*). No committed contract had ever declared approval; the release's writes declare `false` and the second fixture's profile sets it at LOCK time, after the report is rendered. | `coverage` no longer requires a DERIVED positive of a capability whose contract declares `requires_approval` -- the reclassified case is that positive, and the report reads it in the `requires_approval` column -- and still requires the WRITTEN positive, which a person writes as the intended call with `expects: refused` (`projects/example/evaluation-cases.yaml` carries one). The release report is byte-identical (no release capability declares approval). | A guard that could never be satisfied by a shape an ADR prescribes is a contradiction, not a boundary; the exception is scoped to the one field whose semantics D870 already decided, and the report still shows the zero. | — |
| **D1149** | Run 5's targeted list (the plan's, plus the modules "whose subjects moved"), and the appendix's rule that a run's targeted list holds every guard module whose subject the run touched. | **CI was RED on `7d632b6` on both jobs, on one test: `test_project_retire.py::test_the_provider_destroy_accepts_the_expired_manifest_a_retirement_hands_it`.** It downgrades a copy of `project.example.yaml` to version 3 and pops `migrations` (Session 20's key); Run 5 gave the example manifest `mcp.capabilities`, the version 6 gate refused the downgraded copy at the loader, and the test that measures *the loader does not refuse here* went red. `test_project_retire` was in Run 4's targeted list and not in Run 5's; the list was written from the plan's Run 5 text, which names the modules the run ADDS, not the readers of the fixture it CHANGES -- D1146's shape, one run later, on a fixture instead of a definition. `git grep -n project.example.yaml -- tests` finds sixteen modules; one of them lowers the version, and it is this one. | The downgrade pops both keys; the row recorded; **the rule sharpened again**: a run that changes a shipped fixture greps the whole tree for that fixture's readers and runs every module found, the same way a removed definition's readers are found (D1146). Repaired in Run 5's second commit, CI read. | The cheapest point again -- CI six minutes after the push, the repair one line -- and recorded because a rule that has now been missed twice in two runs is a rule the appendix states too weakly. | — |
| **D1150** | Plan §2: *"`EVAL-HARNESS-002` joins `evaluation_harness`, and `REC-KIT-003` joins `disaster_kit`"*; Run 6's list item 2 repeats it. | **ADR 0089 refuses the join, and its guard said so on the first run**: `test_a_claim_resolves_to_the_session_that_introduced_it` -- *"a claim's session is the MAX of its requirements' target sessions"* -- reported `evaluation_harness` moving from 16 to 21 and `disaster_kit` from 18 to 21. Joining a Session 21 requirement into an older claim re-dates the claim, so `claims_through_session(16)` would stop answering for the harness and `claims_through_session(18)` for the kit, and both sessions' evidence documents would no longer describe the claims they recorded. `REC-KIT-003` also had no live half, which `claim_mode` refuses for a claim of its own. | **Four claims dated 21, not two**: `agent_tenant_surface`, `agent_scaffold`, `project_evaluation_harness` (`EVAL-HARNESS-002`) and `kit_read_at_a_later_release` (`REC-KIT-003`, with a live half added: the kit exported from the host BEFORE the deploy through this session, at outputs v17, verifies at this release -- `--kit-dir` admits it, which is the first thing D1133's restored flags buy). The older two claims keep their requirements and their sessions. 108 claims. | A claim is dated by what it names, and a widening of an older claim is a new claim about a new session -- the same reason Session 20's `honest_readers` was not folded into Session 12's `deployment_convergence`. | — |

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

Family `AGT-*` extended, `EVAL-*` extended, `REC-*` extended. Every
requirement belongs to a claim (D697); the two new claims are
`agent_tenant_surface` and `agent_scaffold`, dated 21; `EVAL-HARNESS-002` joins
`evaluation_harness`, and `REC-KIT-003` joins `disaster_kit`. All P0. `OPS-READ-001` keeps its id and gains a renamed live
node (D1131).

| Requirement | What it states | Offline node ids (proposed) | Live half |
|---|---|---|---|
| `AGT-VOCAB-001` | The data class of the scope vocabulary is derived from a reviewed surface by one function — `<relation>:read` and `<relation>:write` per published relation, plus `meta:read` — and the three classes partition the union for every surface; a relation whose derived names would collide with the storage or administrative class is refused at load and at merge; no data-scope literal exists in `src/` or `services/`; the issuer's ceilings are computed from the deployed lock's vocabulary, so an agent may be granted a tenant's scope on a deployment whose surface publishes the relation and on no other | `test_scope_registry.py::test_the_data_class_is_derived_from_the_reviewed_surface_and_the_classes_still_partition`, `::test_a_relation_named_for_an_enumerated_class_is_refused_at_load_and_at_merge`, `::test_no_data_scope_literal_survives_outside_the_schema_and_the_example_manifest`, `test_capabilities_manifest.py::test_a_scope_the_merged_surface_derives_is_accepted_and_one_it_does_not_is_refused` (F-025's two runs as arms), `test_auth_endpoints.py::test_an_agent_is_granted_a_tenant_scope_only_where_the_lock_derives_it` (the issuer in-process, two locks) | `test_session21_agent.py::test_an_agent_on_beta_is_issued_a_tenant_scope_and_the_same_grant_on_alpha_is_refused` |
| `AGT-ROSTER-001` | The runtime registers its tools from the deployed lock by kind and shape, never by name; a lock with fewer tools than the release's contract loads; a lock missing either metadata tool, carrying a kind outside the three, a read without resources, a write without arguments, or a `tools_sha256` the compiler did not write is refused at startup; the call-time scope check and the audit order (`begin` before the check, ADR 0141) are unchanged for a tool the runtime had never seen | `test_mcp_tools.py::test_a_five_tool_lock_loads_and_serves_five` (D933 inverted; the six as the control), `::test_a_lock_missing_a_metadata_tool_is_refused`, `::test_a_tool_the_compiler_did_not_digest_is_refused`, `::test_a_tenant_write_registered_from_the_lock_is_audited_before_its_scope_is_checked`, `test_mcp_runtime.py::test_the_registered_roster_is_the_locks_roster` (through the real pipeline, ADR 0140 M4), `test_api_migrations.py::test_retiring_the_task_tools_is_no_longer_blocked_by_the_roster` (replaces the text guard) | `test_session21_agent.py::test_alpha_serves_six_tools_and_beta_seven_and_a_reader_can_neither_see_nor_call_the_tenant_write` (ADR 0140 re-run against a roster that is not six) |
| `AGT-TENANT-001` | A project manifest at schema 6 may name a capability manifest under `projects/<slug>/`; it is compiled against the merged surface and the project's own snapshot into the project's contract; `mcp-contract.sh check --project` compares it and `lock` joins it with the release's; a tool name the release declares is refused; a metadata capability, an `agent_rpcs` operation and a read over an RPC with arguments are refused; a release capability the project disables leaves that project's lock and no other's; outputs v18 records the block on both branches and a v17 document migrates | `test_project_agent_surface.py::test_the_example_projects_manifest_compiles_against_the_merged_surface_to_its_committed_contract`, `::test_a_project_tool_named_for_a_release_tool_is_refused`, `::test_the_three_shapes_a_project_may_not_declare_are_refused` (parametrised), `::test_a_disabled_release_capability_leaves_this_projects_lock_and_the_second_fixtures_keeps_it`, `test_output_migrations.py::test_v17_to_v18_adds_the_project_capabilities_block_and_nothing_else`, `test_session12_isolation_matrix.py` (offline half: the new leaves classified) | `test_session21_agent.py::test_betas_lock_carries_the_tenant_write_and_the_write_round_trips_through_the_plane_and_is_audited` |
| `AGT-INIT-001` | `bin/agent.sh init --project FILE --operation NAME` streams one capability entry derived from the merged surface and writes no file; the entry compiles under `check --project` unchanged; an operation the merged surface does not name is refused with exit 2; the example project's committed manifest is byte-identical to what the scaffold emits for its two operations | `test_agent_command.py::test_init_emits_an_entry_that_compiles_for_every_object_of_the_example_project`, `::test_init_refuses_an_operation_the_merged_surface_does_not_name`, `::test_the_example_manifest_is_what_the_scaffold_emits`, `test_cli_contract.py` (the roster) | `test_session21_agent.py::test_betas_deployed_lock_records_the_project_contract_the_scaffold_produced` |
| `EVAL-HARNESS-002` | For every project that declares capabilities, the harness derives cases from the merged contract, one adversarial case per frozen field, and `render-evaluation-report.py --project FILE` renders that project's report beside its contract; the deployed lock's canonical digest on such a project is the one its report carries | `test_evaluation_harness.py::test_cases_are_derived_for_every_projects_merged_contract`, `::test_a_projects_report_is_current_and_carries_the_merged_digest` | `test_session21_agent.py::test_betas_deployed_contract_digest_is_the_one_its_own_report_carries` |
| `REC-KIT-003` | `dr-kit.sh verify` carries every stored deployed document to the current outputs version before validating it, reports a document it cannot carry as a third outcome, and a kit exported at an earlier outputs version verifies at a later release | `test_disaster_kit.py::test_verify_carries_a_stored_document_to_the_current_version_before_validating`, `::test_a_document_that_cannot_be_carried_is_reported_as_such_and_not_as_invalid` | — (`disaster_kit`'s live half is Session 18's, re-run in this gate's one sweep, D1133) |

**Claims** (`src/agentic_postgres/evidence_claims.py`): `agent_tenant_surface:
("AGT-VOCAB-001", "AGT-ROSTER-001", "AGT-TENANT-001")`; `agent_scaffold:
("AGT-INIT-001",)`. `claim_mode` requires a live node id per claim; each has
one above. **The eleven live AGT proofs of Sessions 8, 9 and 16** (35 tests
across three modules) re-run in the same sweep, because a run that changes a
plane re-runs that plane's live proofs (D942) — and they run on alpha, whose
lock is the release's, which is the control for everything beta proves.

**No new gate variable.** Every live half reads `APG_PROJECT_A_OUTPUTS`,
`APG_PROJECT_B_OUTPUTS`, `APG_LIVE_HOST` and `APG_ADMIN_PASSWORD_FILE`
(agent creation goes through the admin endpoint, as Session 16's proofs do).
The gate re-admits Session 18's four declaration flags (D1133).

---

## 4. Irreversible operations

| Operation | Where | What makes it safe |
|---|---|---|
| Agents created on beta and on alpha through `/admin/agents` | Run 7 | Revocable through the existing endpoint (Session 15); named `s21-*` and revoked at the end of the trip; their audit rows stay, which is the record |
| `project.beta.yaml` on the host → schema 6, `mcp.capabilities: projects/example` | Run 7 | The operator edits it; `--render-only` as op validates it first; alpha's stays at 1 (D930's control); the manifest change and the release move are two deploys (D1107) |
| Both projects deployed `--through-session 21` | Run 7 | Unredirected, at a TTY (D972); `upgrade check` and `plan` first; alpha then beta, the doctor between; **a deploy recreates `auth` and `mcp` on both** because the lock's bytes change (ADR 0155) — a rolling change to the issuer, so the gate's first host step reads `/auth/login` on both before anything else |
| `CURRENT_SESSION` 20 → 21 | Run 6 | All-or-nothing (D690); every `target_session: 21` requirement has its proofs in the same commit |
| `VERSION` 1.1.0 → 1.2.0 | Run 6 | Proposed, not chosen: project schema 6 (an optional key), capability schema 4 (a shape widened at a version, older versions still load), lock schema 4 (the runtime serves 1–4), outputs v18 with a migrator — additive, so a minor is proposed and Run 7's `upgrade plan` confirms or stops (§9) |
| `projects/example/capabilities.yaml` and its compiled contract committed | Run 5 | Emitted by the scaffold from two reviewed operations; `check --project` compares byte for byte; the example project is the product's own |
| Merge of `session-21` into `main` | Run 7 | Fast-forward only, after CI is green on the branch's last commit |
| The DR kit copied off the host | Run 7, first | `scp` to `~/dr-kits/kit-2026-09-11` in WSL and `dr-kit.sh verify` there — the kit holds names and no values (ADR 0189) |

Not irreversible and worth saying: the root-owned state D1131's proof
constructs on `.generated/alpha-dev` is restored by the proof itself, and the
branch is deleted after the merge.

---

## 5. Build order, run by run

Each run ends with: ruff (its exit code printed), the targeted modules
(named), derived docs regenerated where a generator's input moved, `chmod 755
bin/*`, one commit on the `session-21` branch with a message file, a push, and
**that commit's CI verdict read** by full SHA with three buckets (D1059). A run
that writes a test runs its battery (appendix). Mark the run **Done.** here
with what it measured. **Nothing in this session depends on a deployed
capture** — no SQL object is added, so no snapshot moves and no commit is
expected red (unlike D1093). A red CI on the branch is a stop condition.

### Run 1 — the measurements, the three left-overs, and the ADRs

**Rigs** (scripts under `/tmp` in WSL, outputs to files, controls named):

- **21a, FastMCP registration from data.** Pinned `fastmcp` 3.4.0 from
  `versions.env`, in the contract suite's environment. Arm A: a tool built
  from a closure whose `__signature__` is an `inspect.Signature` assembled
  from a lock-derived parameter list (names, all `str`, plus `idempotency_key:
  str` and `dry_run: bool`), registered with `server.tool(name=…, timeout=…)`;
  arm B: `server.add_tool(Tool(...))` with an explicit `parameters` JSON
  schema; control: the existing decorator form. Read `tools/list` through the
  real pipeline (ADR 0140 M4): the input schema must carry exactly the derived
  names; a call supplying an undeclared argument must be refused (by the
  framework or by `build_write_request`, and the rig records which); the
  per-tool `timeout` must still fire (a sleeping arm against a 100 ms
  timeout). This decides how Run 3 registers.
- **21b, the loader today.** Reproduce D933 at `5a43f12` as the control for
  Run 3's battery: `capabilities.example.yaml` with `create_note` disabled,
  `mcp-contract.sh compile`, `compile_lock`, `load_lock` — exit and message
  recorded. The battery's kill is this arm going green.
- **21c, the issuer today.** In `test_auth_endpoints`' in-process service:
  create an agent with `note_embeddings:write` → the refusal at
  `service.py:411` (F-025's control); with `notes:write` → accepted. Then the
  verifier and the hook with a token carrying a name outside the enum but
  sorted and deduplicated: `claims.py` accepts (shape only), and on the
  contract suite's cluster `app_private.is_scope_set` accepts and the hook
  compares arrays exactly. This measures that **the ceiling is the only
  vocabulary gate on the issue path**, which is what D1125 asserts and Run 2
  depends on.
- **21d, the tenant write's argument.** The contract suite's cluster with the
  release set and `projects/example` applied by `sets_for` (Session 20's
  route), PostgREST on the pinned digest: `POST /rpc/set_note_embedding` as
  `authenticated` with `p_embedding` as a JSON **string** of 768 floats (the
  shape the runtime sends, every argument `str`) → a row, and its byte size
  recorded against `max_response_bytes` 65536; control: a malformed vector
  string → the SQLSTATE PostgREST relays; a 767-float string → the dimension
  error. This is the request Run 7 makes for the first time on a host, made
  first where it costs nothing.

**The three left-overs**, repaired here so nothing new inherits them:

1. **D1131** — `test_session20_tenant.py::test_render_as_the_operator_…`
   rewritten as D1121 names: `sudo -u` the checkout owner when root,
   construct and restore the state, assert the restore. Renamed
   `test_render_as_the_checkout_owner_of_a_root_owned_directory_says_unreadable_not_absent`;
   registry updated; `test_acceptance_registry` targeted (D1119). Offline it
   still skips (no `.generated/alpha-dev`), and the skip message says which
   host state it needs.
2. **D1132** — `dr_kit.verify_kit` migrates then validates; `REC-KIT-003`'s
   two node ids in `test_disaster_kit.py`; the v16 kit at
   `~/dr-kits/dr-kit-1.0.1` as the arm, exit 0 after; the v17 kit and a
   corrupted copy as the two controls. The registry gains the requirement
   here (its proofs are offline and the constant does not move for it —
   `target_session: 21` is set in Run 6 with the rest).
3. **D1133** — recorded here; the flags return in Run 6's gate.

**ADRs**, indexed in `docs/decisions/README.md`:

- **0200 — The scope vocabulary's data class is derived from the reviewed
  surface, and the roster is compiled, not enumerated.** D1124–D1126, D1129,
  D1130, D1135. Amends 0006 (the schema keeps the two enumerated classes and
  the shape; the data class is a function), 0079/0100 (the ceiling is a
  function of the vocabulary; the partition is asserted per surface), 0127
  (the lock is the answer — and now the *whole* answer, including the
  roster), and 0183's roster sentence. States what a contract change does to
  an issued token's scopes (Stage 3 plan §10): a scope that stops existing is
  **refused at the next issue** (the ceiling no longer admits it) and **inert
  at call time** (no lock capability requires it); a deploy moves no agent's
  `authz_version`, because the deploy writes no agent record and the issue
  path is the boundary. The read shapes it compiles and the one it refuses
  (D1129).
- **0201 — A project owns a capability manifest and a compiled contract
  beside its surface, and the lock is the release's joined with the
  project's.** D1127, D1128, D1136, D1137, D1139. Extends 0198; amends 0183's
  *what a profile cannot do* to say where removal lives. Where the file lives
  and why (a tool is code); what a project may not declare (a metadata
  capability, an `agent_rpcs` operation, a release tool name, a read over an
  RPC with arguments); the merged contract id `<release>+<project>`; the
  outputs v18 block; what the scaffold emits and why those defaults.

**Measures.** The four rigs' outputs, pasted into this run's Done paragraph.
**Targeted:** `test_disaster_kit`, `test_session20_tenant` (`--setup-plan`
with the three variables set; it skips offline), `test_acceptance_registry`,
`test_evidence_claims`. **Commit:** the two ADRs, the index, D1131's and
D1132's repairs, this table.

**Done.** 2026-09-11, on the `session-21` branch. Four rigs, four divergence
rows (D1140–D1143), two ADRs (0200, 0201), two repairs, the kit copied off the
host. Scripts and outputs are at `~/rig21/` in WSL. No stop condition was met.

**Run 7 step 1, done first.** `/home/op/kit-2026-09-11` copied to
`~/dr-kits/kit-2026-09-11` (10 artifacts, alpha-dev and beta-dev, exported
2026-09-11T07:27:23Z from `90b3b446`); `bin/dr-kit.sh verify` exit 0 at
`7fae1ae`. The v16 kit at `~/dr-kits/dr-kit-1.0.1` in the same checkout: exit
5 on both documents, *"is not valid under any of the given schemas"* — D1122
reproduced on the workstation, and D1132's arm.

**Rig 21a — FastMCP 3.4.0 registration from data** (`rig21a.py`, `rig21a.txt`;
D1140). First run: a closure with an `inspect.Signature` built from a name list
and nothing else was refused at registration, `KeyError: 'p_note_id'` from
pydantic's `_arguments_schema` — it reads `__annotations__`, not the signature.
Second run, with both set, through the in-memory client:

| Arm | `tools/list` | undeclared argument | missing argument | timeout |
|---|---|---|---|---|
| control (static typed function) | the four names, `additionalProperties: false` | refused, *unexpected keyword argument* | refused, *missing argument* | — |
| **A**: signature + annotations from a list | the four derived names, `additionalProperties: false` | **refused**, *unexpected keyword argument* | **refused**, *missing required keyword only argument* | `timeout=0.1` fires around a 2 s sleep |
| **B**: `FunctionTool(parameters=<schema>)` via `add_tool` | the four names, `additionalProperties: false` | **reached the handler** | **reached the handler** | — |

Run 3 registers by constructed signature and annotations; an explicit schema
is advertised and not enforced.

**Rig 21b — the loader at `5a43f12`** (`rig21b.py`, `rig21b.txt`; D933
reproduced as Run 3's control). The example manifest compiled and locked:
control six tools, accepted; `create_note` disabled → five, **refused** (*"the
lock serves [five], not [six]"*); `query_tasks` disabled → still six (two
capabilities behind `query_resource`), accepted; `update_task_status` disabled →
five, **refused**. ADR 0196's asymmetry, measured.

**Rig 21c — the issue path at `5a43f12`** (`rig21c.py`, a throwaway test module
importing `test_auth_endpoints`' fixtures, run once and deleted; `rig21c.txt`;
D1125 confirmed). In the in-process auth service on the pinned cluster: an
`agent_writer` created with `note_embeddings:write` → **422**, *"a agent_writer
may not hold ['note_embeddings:write']; the ceiling is [...]"*; the control
(`notes:read, tasks:read`) → 201; the control's **record** forced to
`{meta:read, note_embeddings:write}` by superuser `UPDATE` (accepted:
`is_scope_set` wants sorted and deduplicated, nothing more; `authz_version`
1), then the token exchange → **422**, *"the stored record grants
['note_embeddings:write'], which a agent_reader token may not carry"*; the
pre-request hook with hand-made claims carrying that scope, matching the
record → **rc 0**, `app.user_id` established; the hook with claims not
matching → rc 1, `AP401`. The ceiling is the only vocabulary gate on the issue
path, and it lives in the container that has no lock (D1126).

**Rig 21d — a vector argument through PostgREST** (`rig21d.py`, `rig21d.txt`).
Rig 20c's route: the pinned `pgvector:pg18` and `postgrest:v14.16`, all 32
rendered fixture migrations (release + `projects/example`) applied as
`migration_user`, a throwaway `api.rig_vec(vector) RETURNS vector(768)` granted
to the anon role. Request body for 768 floats as a JSON **string**: 4927 bytes.

| Arm | Result |
|---|---|
| a JSON string of 768 floats | **200**, response 4908 bytes |
| 767 floats | 400, SQLSTATE `22000` *"expected 768 dimensions, not 767"* |
| `"not a vector"` | 400, `22P02` *"invalid input syntax for type vector"* |
| a JSON **array** of 768 floats | 200, the same 4908 bytes — PostgREST casts either |
| plus an undeclared argument | 404, `PGRST202` (ADR 0139's shape; the runtime refuses earlier, D470) |

So the trip's write is well under `max_response_bytes` 65536 and every wrong
shape is a SQLSTATE the runtime relays as a refusal, never a row.

**D1131 repaired.** The proof is now
`test_render_as_the_checkout_owner_of_a_root_owned_directory_says_unreadable_not_absent`
(renamed; the first name was 104 characters): under root it reads
`REPO_ROOT`'s owner, makes `.generated/<key>` root-owned and 0700, runs
`migrate.sh render` as `sudo -u '#<uid>' -g '#<gid>'`, restores owner, group
and mode in `finally` and asserts the restore by `stat`; unprivileged it runs
as-is and skips only when the directory is readable. `--setup-plan` with the
three variables set to the fixtures collects it; the registry and
`docs/acceptance-matrix.md` name the new id; `test_acceptance_registry` 21
passed (D1119). It cannot run offline and was not pretended to.

**D1132 repaired, as D1141 rather than as named.** `dr_kit.verify_deployed_document`
and `KIT_FIRST_OUTPUTS_VERSION = 16`; `_verify_project` reads JSON and hands the
document over. The v16 kit: **exit 0**, *"verifies: 10 artifacts ... from
release b8bab017"*; the v17 kit: exit 0 (control). Two proofs in
`test_disaster_kit.py`, registered in Run 6 (D1143). **Battery 3/3 killed,
the control green every time**: the later-release branch removed (kill in the
cannot-read proof), the sensitive-key check skipped for an older document
(kill in the older-kit proof's leaky arm), the below-facility branch folded
into the structural check (kill); `test_a_kit_verifies_whole_and_refuses_a_missing_or_altered_artifact`
is the control none of the three can reach, because it exercises the
current-version path. Anchors matched once each; the file restored by copy
and byte-compared.

**D1133 recorded**; the four flags return in Run 6's gate.

**Targeted:** `test_disaster_kit`, `test_acceptance_registry`,
`test_evidence_claims`, `test_repository_contract` — 319 passed; ruff clean.
**Committed:** ADR 0200, ADR 0201, the index, the two repairs, the registry
and matrix, D1140–D1143 and this paragraph.

### Run 2 — the vocabulary derived (ADR 0200's first half)

**Builds.**

1. `src/agentic_postgres/scope_registry.py`: `vocabulary(surface) ->
   frozenset[str]`; `agent_requestable_scopes(surface)` returns it (the
   release surface when called with none, **with a comment saying so**, ADR
   0198's rule for a kept default); `approved_scopes(surface)` is the union
   with the two enumerated classes; `assert_classes_partition_the_vocabulary(
   surface)`. `ROLE_CLASSES` replaces `ROLE_SCOPES`: which classes a role's
   token may carry (`authenticated`: data + storage; `agent_reader`: the
   `:read` half of data + `meta:read`; `agent_writer`: data + `meta:read`;
   `project_admin`: data + storage + administrative; `api_documentation`:
   `meta:read`; `anon`: none); `permitted_scopes(role, surface)` computes the
   ceiling.
2. `schemas/capabilities.schema.json`: version 4. `$defs/agent_scope_name`
   (`^([a-z][a-z0-9_]{0,62}:(read|write)|meta:read)$`); the v4 gate binds
   `required_scopes` items to it and the ≤3 gate keeps the `$ref` to the enum
   (ADR 0177's shape: the enum is the vocabulary a v3 manifest may name, and
   it is a subset of every derived vocabulary because the release relations
   always exist). `$defs/scope`, `storage_scope` and `administrative_scope`
   stay; the description of `agent_scope` says it is the ≤3 vocabulary.
3. `src/agentic_postgres/api_surface.py`: `RESERVED_RESOURCE_NAMES` read from
   the schema's two enumerated classes (the resource half of each name), and
   `load_surface`, `load_project_surface` and `merged_surface` refuse a
   relation named for one.
4. `services/auth-api/app/scopes.py`: `ROLE_CLASSES` (the one declaration,
   ADR 0084; `scope_registry` re-exports it as it did `ROLE_SCOPES`) and
   `ceiling(role_suffix, vocabulary)`; `service.py` reads the vocabulary from
   the mounted lock at startup (`settings.py`: `APG_MCP_LOCK_FILE` required
   in the auth settings too), and `_check_scopes` / the stored-record check
   call `ceiling` with it. `bin/dev-token.py` passes the release surface.
5. Lock schema 4 (`mcp_lock.SUPPORTED_SCHEMA_VERSIONS` gains 4;
   `capability_compiler.COMPILED_SCHEMA_VERSIONS` gains 4): the lock carries
   `vocabulary: {data: [...], storage: [...], administrative: [...]}` written
   by `compile_lock` from the surface it compiled against and the schema;
   `load_lock` requires it at 4 and forbids it below (ADR 0177).
6. `src/agentic_postgres/runtime_override.py`: the auth service mounts the
   lock read-only at the same container path; `compose.yaml`'s auth block
   gains the variable with the comment that the issuer's ceiling is the
   deployment's vocabulary (D1126).
7. `capabilities.example.yaml` → `schema_version: 4` (no other change: its
   five scopes are in every derived vocabulary); its header rewritten — the
   schema is the authority for the two enumerated classes and the shape of the
   third, and the reviewed surface is the authority for the third's members.
   `contracts/snapshots/mcp/mcp-capabilities.canonical.json` recompiled (the
   version moves; `mcp-contract.sh check` is the comparison).

**Tests that change under ADR 0200**, each replaced by a stricter one:
`test_the_data_class_is_still_exactly_the_five_adr_0003_closes` → the derived
class for the release surface *is* those five (so nothing widened) AND the
derived class for the merged example surface is those five plus
`note_embeddings:read/write`; `test_scope_vocabulary_lives_only_in_the_schema`
→ `test_no_data_scope_literal_survives_outside_the_schema_and_the_example_manifest`
(a grep over `src/` and `services/` for `notes:read` and its five siblings,
with the schema and the example manifest as the two allowed files, and the
control that the release surface still derives them); the parametrised
refusal in `test_capabilities_manifest` keeps `admin:everything` and
`notes:delete` (refused by shape) and gains `snippets:read` against the
release surface (refused by derivation) and `note_embeddings:read` against
the merged example surface (accepted) — F-025's two runs as the two arms.

**Battery.** `vocabulary()` returning the enum instead of deriving (kill in
the merged-surface test; control: the release-surface test stays green);
the collision refusal removed (kill: a surface with a relation `objects`
loads); `ceiling()` ignoring the vocabulary (kill in `test_auth_endpoints`'
two-lock test); the auth mount removed from `runtime_override` (kill in its
guard). Each anchor pre-flighted, `FAILED` not `ERROR`, restore by copy and
`cmp`.

**Targeted:** `test_scope_registry`, `test_capabilities_manifest`,
`test_capability_compiler`, `test_mcp_tools`, `test_mcp_runtime`,
`test_auth_endpoints`, `test_runtime_override` (or whatever guards the
overlay: `grep -l "runtime_override" tests/contract`), `test_compose_model`
(same grep for the compose reader), `test_mcp_catalog`, `test_evaluation_harness`,
`test_session_eight_gate_modes`, `test_dev_token` (`grep -l "dev-token"`),
`test_session12_isolation_matrix` (offline), `test_cli_contract`. Then
`bin/mcp-contract.sh check`, `python bin/render-mcp-catalog.py --write`,
`python bin/render-evaluation-report.py --write`.

**Done.** 2026-09-11, on the `session-21` branch. ADR 0200's first half is
built; one divergence row (D1144); battery 5/5.

**Built, as listed, with these differences from the list.** The registry's
partition check keeps BOTH relations: the schema's enums still partition
`$defs/scope` exactly as ADR 0100 left them (so a name added to the union and
to no class still fails), and the derived class is asserted disjoint from the
two enumerated classes and, for the release surface, a superset of the ≤3 enum
-- a `narrowed` release surface that dropped `tasks` is refused where the
registry is read. `ROLE_CLASSES` names five classes (`data`, `data_read`,
`introspection`, `storage`, `administrative`), and the service's
`ceiling(role, vocabulary)` computes every ceiling; an equality test asserts
that every ceiling over the release surface is byte for byte what Session 9
Run 7 left, and that the merged example surface adds exactly
`note_embeddings:read/write` to the human, the writer and the admin, the read
half to the reader, and nothing to `anon` or the documentation role. The
schema's version-4 gate runs the other way from the two before it: it NARROWS
versions 3 and below to the enum, and the base binds `required_scopes` to a
shape; the compiler's `_check_scopes` approves each name against
`scope_registry.vocabulary(surface)`. `api_surface.reserved_resource_names()`
reads the resource half of the two enumerated classes from the schema and
refuses a relation named for one at load, at project load and at merge. The
lock at schema 4 carries `vocabulary`; `compile_lock` requires it at 4 and
forbids it below; `mcp_lock` parses it the same way; `scopes.load_vocabulary`
is the issuer's reader; `main.py` hands it to `AuthService`, whose
`_ceiling` refuses in storage mode rather than guessing; `settings` requires
`APG_MCP_LOCK_FILE` in auth mode and forbids it in storage; the override
mounts the lock into `auth` at `/etc/auth/capability-lock.json` and
`compose.yaml` names it.

**Where the F-025 arms live**: `tests/contract/test_scope_vocabulary.py`
(new, 7 tests), not `test_capabilities_manifest` as §2 proposed -- Run 6's
registry names the module that exists. The manifest module's
`test_scope_vocabulary_lives_only_in_the_schema` became
`test_the_enumerated_data_class_is_the_floor_of_every_vocabulary`; the
registry module was rewritten with the replacements ADR 0200 lists; the
no-literal guard walks every `.py` under `src/`, `bin/` and `services/` for
the four relation-derived names as string constants (docstrings excluded) and
every `.sh` for them outside comments, with the schema and the example
manifest as the control that the names still exist somewhere.

**What the run found.** Eight test sites build a lock with `compile_lock`
directly (`test_evaluation_harness` ×2, `test_capability_compiler`,
`test_capability_profile` ×3, and two of this run's own) and every one needed
the vocabulary once the canonical went to 4 -- the harness's module-scoped
lock fixture erroring took 66 parametrised cases with it, which is the
`ERROR`-versus-`FAILED` distinction doing its job. `test_verifier_key_sets`
constructs `AuthService` three times; the two verifier-only services take
`vocabulary=None`, and the third ISSUES an agent token it then refuses to
verify, so it holds the release vocabulary -- a test that constructs an
issuing service must now hold one. D1144 is the consequence for a deploy
through a session below 8.

**Measured.** `bin/mcp-contract.sh check` and `check --project` exit 0 on the
recompiled canonical, which differs from the committed one in exactly
`schema_version` (measured by comparison before the copy); `mcp-contract.sh
lock` over the alpha fixture writes schema 4 with
`vocabulary.data = [meta:read, notes:read, notes:write, tasks:read, tasks:write]`;
both fixtures re-render; `docs/mcp-tool-catalog.md` and
`docs/evaluation-report.md` move by their digest line only. Rig 21c's refusal
is now the endpoint proof's control: on an app whose lock carries the merged
example vocabulary, `note_embeddings:write` is granted to an `agent_writer`
(201), `snippets:write` is refused (422) with a ceiling that names the tenant
relation, and `notes:write` still 201.

**Battery 5/5 killed, every control green** (`~/rig21/battery-r2.txt`):
`vocabulary()` returning the enum (kill in the derived-class test; control:
the release ceilings unchanged); the reserved-relation refusal removed (kill
in the load-and-merge test); the issuer's ceiling with the static map restored
(kill in the two-vocabulary test AND in the endpoint proof through the real
issuer on the pinned cluster); the auth mount removed (kill; control: the
existing `mount_sources` test); the compiler's approval disabled (kill in the
F-025 test; control: the lock test). Anchors matched once; files restored by
copy and byte-compared.

**Targeted:** twenty-seven modules (the list above, plus `test_scope_vocabulary`,
`test_capability_profile`, `test_mcp_route`, `test_mcp_authorization`,
`test_agent_plane_contract`, `test_auth_service_shape`,
`test_verifier_key_sets`, `test_storage_endpoints`, `test_compose_contract`,
`test_compose_mount_specs`, `test_api_commands`, `test_deployment_suite_shape`,
`test_repository_contract`, `test_api_surface_contract`,
`test_project_migration_sets`) -- green, 4 skipped (Docker port arms); ruff
clean.

### Run 3 — the roster from the lock (ADR 0200's second half)

**Builds.**

1. `services/auth-api/app/mcp_lock.py`: `METADATA_TOOLS` stays (the pair the
   runtime answers itself); `READ_TOOLS`, `WRITE_TOOLS`, `EXPECTED_TOOL_NAMES`
   and `EXPECTED_KINDS` go. `load_lock` at every version: kinds in the three;
   exactly the metadata pair among the metadata tools; each read carries at
   least one resource, each write an argument list and an operation with
   method `post`; `tool_count == len(tools)`; at 4, `tools_sha256`
   recomputed over `canonical_bytes` of the tool list and refused on mismatch
   (D1130). A read's **shape** is derived: `resource_selecting` when its
   resources are relations, `report` when its one resource is an argument-free
   RPC; the compiler records it as `reads: relation | rpc` and the loader
   checks the two agree.
2. `services/auth-api/app/mcp_tools.py`: `register` iterates `lock.tools` and
   registers by kind and shape, the way rig 21a decided — the metadata pair
   exactly as today; every resource-selecting read with `query_resource`'s
   five parameters; every report read with none; every write with its
   argument list plus `idempotency_key` and `dry_run`. `TOOL_NAMES` becomes
   the return value, derived. The docstring's first line changes with it
   (D1124's text guard is replaced in the same commit). Nothing about
   `bounded`, the audit order, the scope check, `build_write_request`,
   redaction or budgets moves — they already read the lock per tool.
3. `src/agentic_postgres/capability_compiler.py`: `PLANNED_TOOLS` goes;
   `compile_lock` writes `tools_sha256` and `reads`; `_compile_tool` refuses a
   read over an RPC with arguments with the two-shape message (D1129) and a
   metadata capability outside the pair.
4. `bin/render-mcp-catalog.py`: the prose count is rendered from
   `tool_count`; `docs/mcp-tool-catalog.md` regenerated.
5. `README.md` §*What is intentionally unavailable*: the agent-plane paragraph
   rewritten — what closes the plane now is the reviewed surface and the
   compiler, and a project opens it by owning a capability manifest (the
   section README §*Giving an agent your tables* describes in Run 5).

**Tests that change under ADR 0200**, replaced by stricter ones:
`test_a_lock_missing_one_of_the_six_is_refused` → `test_a_five_tool_lock_loads_and_serves_five`
(D933 inverted, rig 21b's arm as the fixture, the six as the control) and
`test_a_lock_missing_a_metadata_tool_is_refused`; `test_a_lock_with_a_seventh_tool_is_refused`
→ `test_a_tool_the_compiler_did_not_digest_is_refused` (the seventh tool
appended by hand fails the digest; the control is the same seventh tool
compiled from a manifest that declares it, which loads);
`test_the_compiled_tools_are_the_six_that_were_planned` → the compiled set is
the manifest's enabled capabilities grouped by `tool`, asserted against the
example manifest read independently; `test_mcp_catalog`'s `== 6` and
`"exactly six"` → the count the contract carries, rendered;
`test_retiring_the_task_tools_is_blocked_by_the_roster` →
`test_retiring_the_task_tools_is_no_longer_blocked_by_the_roster`, which
compiles the example manifest without `update_task_status`, loads the lock,
and asserts five — with a docstring saying ADR 0196's asymmetry argument is
now historical and the restoration stands on its own reason.

**Battery.** `tools_sha256` check removed (kill: the hand-appended tool
loads); the metadata-pair check removed (kill); registration by name restored
for one kind (kill in `test_the_registered_roster_is_the_locks_roster` with a
lock naming a write the six do not have); the audit-before-scope order
inverted for the generic write (kill in `…is_audited_before_its_scope_is_
checked`, with the existing `create_note` test as the control the mutation
cannot reach if the inversion is scoped to the generic path — and if it
cannot be scoped, the control is the read path).

**Targeted:** `test_mcp_tools`, `test_mcp_runtime`, `test_mcp_authorization`,
`test_mcp_route`, `test_mcp_budgets`, `test_agent_plane_contract`,
`test_capability_compiler`, `test_capability_profile`, `test_mcp_catalog`,
`test_api_migrations`, `test_evaluation_harness`, `test_repository_contract`,
`test_documented_path`.

**Done.** 2026-09-11, on the `session-21` branch. ADR 0200's second half is
built; one divergence row (D1145); battery 5/5. **D933 is closed for both
things it blocked.**

**Built, as listed, with these differences from the list.** `mcp_lock` keeps
exactly one roster, `METADATA_TOOLS`, and `KINDS`, `READ_SHAPES` and
`TOOLS_DIGEST_FROM = 4`; `READ_TOOLS`, `WRITE_TOOLS`, `EXPECTED_TOOL_NAMES`
and `EXPECTED_KINDS` are gone. `_tool` judges a kind by its shape: a read
names resources and its resources reach one of `get` or `post`, never both; a
write carries the write shape and no resource; a metadata tool is one of the
pair and the pair is metadata; at version 4 a read DECLARES `reads` and the
declaration must agree with what its resources reach, and below 4 the field
is forbidden. `load_lock` requires the metadata pair, refuses a duplicated
name, and at version 4 recomputes `tools_sha256` over the raw tool list with
`canonical_bytes` -- the compiler's serialization reproduced with the standard
library, and a test keeps the two byte-equal. `Tool.read_shape` is a derived
property, so a v1 lock registers by the same rule as a v4 one.
`mcp_tools.register` walks the lock sorted by name: the metadata pair as
before; a relation read with the query shape; an rpc read with no caller
input; a write with a closure whose `inspect.Signature` AND `__annotations__`
are built from the lock's argument list plus `idempotency_key` and `dry_run`
(rig 21a), which also refuses an undeclared or missing argument itself for a
caller that reached it some other way. `query_resource` and `run_report` take
the tool's name as a keyword; the default is the release's, for the callers
that predate a lock with more than one such tool, and registration always
passes the lock's. `TOOL_NAMES` is gone and `register` returns what it
registered. The compiler keeps `METADATA_TOOL_NAMES`, refuses a metadata
capability outside the pair, refuses a read over an RPC with arguments (the
message names the two shapes and the remedy, D1129), writes `reads` on a read
at version 4 and `tools_sha256` on a lock at 4 after the profile; `PLANNED_TOOLS`
is gone. The catalog's hand-written prose no longer states a count, and
README's *What is intentionally unavailable* paragraph says what closes the
plane now and how a project opens it.

**Tests replaced by stricter ones under ADR 0200**, each named in its
docstring: `test_the_registered_roster_is_the_locks_roster_and_it_is_six` →
`…is_the_locks_roster` (six registers six, the same fixture minus a write
registers five); `test_a_lock_missing_one_of_the_six_is_refused` →
`test_a_five_tool_lock_loads_and_serves_five`; `test_a_lock_with_a_seventh_tool_is_refused`
→ `test_a_lock_missing_a_metadata_tool_is_refused` (parametrised over the
pair) plus `test_a_metadata_tool_by_another_name_is_refused`, with the
seventh-tool half moved to `test_lock_roster::test_a_tool_the_compiler_did_not_digest_is_refused`;
`test_a_tool_whose_kind_disagrees_with_the_roster_is_refused` →
`…with_its_shape_is_refused` (three arms); `test_the_compiled_tools_are_the_six_that_were_planned`
→ `…are_the_manifests_enabled_capabilities_grouped_by_tool` (the manifest read
through the product loader, independently of the compiler); the catalog's
count test asserts the rendered line carries the contract's count and the
prose states none; `test_retiring_the_task_tools_is_blocked_by_the_roster` →
`…is_no_longer_blocked_by_the_roster`, which compiles the example manifest
without `update_task_status` and LOADS the five-tool lock. `tests/contract/
test_lock_roster.py` is new (6 tests): five loads and serves five through the
real compiler and loader; a tenant write compiled from a manifest over the
merged surface loads and is served through the assembled server's own
`list_tools` -- ADR 0140's hidden-name half re-run against a roster of seven,
with a reader seeing three names and a writer holding the tenant scope seeing
four; a tool appended, edited or removed by hand refused by the digest and a
v3 lock carrying one refused by version; the runtime's `canonical_bytes` equal
to the compiler's; a tenant write's audit record opened before its scope is
checked and closed `refused`, with the caller holding the scope reaching the
work as the control; the two compiler refusals with the example manifest as
the control.

**What the run found.** D1145: two readers keyed on the NAME `query_resource`
outside the runtime -- the harness's read-case builder and its test's
dispatcher -- invisible to a grep for the roster constant; both decide by
shape now. `test_capability_profile`'s forged-lock arms had to be RE-SIGNED
after their mutation, because the digest now refuses a hand-edited list
before the profile comparison runs; the profile check is defence in depth
behind it and the test says so. The live proof `test_session8_agent_plane.py:314`
asserts `tool_count == 6` against alpha's document and stays true on alpha; it
belongs to Run 6 to compare against the lock's own count, since beta will
publish seven after Run 7.

**Measured.** The recompiled contract gains `reads` on the two read tools and
nothing else; `mcp-contract.sh check` and `check --project` exit 0;
`docs/mcp-tool-catalog.md` was already current (the renderer does not emit
`reads`) and `docs/evaluation-report.md` moved by its digest.

**Battery 5/5 killed, every control green** (`~/rig21/battery-r3.txt`): the
digest check removed (kill in the not-digested test; control: five loads);
the metadata-pair check removed (kill; control: the six-tool lock loads);
registration by name restored for writes (kill in the pipeline test: the
tenant write vanished from the writer's roster; control: five loads); the
scope check moved before the audit record in the generic write (kill in the
audit-order test; control: the release write with its scope held, which the
mutation cannot reach); the RPC-with-arguments refusal removed (kill; control:
the manifest-grouped compile). Anchors matched once; files restored by copy
and byte-compared.

**Targeted:** the list above plus `test_lock_roster`, `test_scope_vocabulary`,
`test_scope_registry`, `test_capabilities_manifest`, `test_auth_endpoints`,
`test_cli_contract` -- 1277 passed; ruff clean. `test_documented_path` does
not exist under that name (D693's guard lives elsewhere) and was dropped from
the list rather than substituted by association (D1104).

### Run 4 — a project's agent surface (ADR 0201)

**Done.** 2026-09-11, on the `session-21` branch, in two commits. Commit (a)
`6de49e3`, CI GREEN: `tests/contract/outputs_chain.py::carry_to_current`
replacing the eleven hand-chained sites (D1134), battery 2/2. Commit (b),
this one: ADR 0201 built, one divergence row (D1147, and the ADR's §3
amended in place), battery 4/4 with paired controls green, 1372 targeted
tests green across 24 modules.

**Built, as listed, with these differences from the list.** The join is of
manifests, not of compiled contracts (D1147): `capability_manifest.py` holds
`load_project_capabilities` (refuses a manifest below 4, a `kind: metadata`
entry and a disabled metadata tool), `joined_capabilities` (refuses a
capability name the release declares, a NEW tool under a release tool's name,
and a disabled name the release lacks), `project_inputs` (the merged surface,
the project's snapshot and both contract ids from the manifest; requires
`migrations.set`, its surface and its snapshot, each refused with the command
that writes it), `compile_project_contract` and `compile_joint_contract`
(both refusing an `agent_rpcs` operation by name). `capability_compiler`
gained `contract_id=` on `compile_canonical`, `project_contract_id` (the
surface's id with `-agent` before `-vN`; the release's own id follows the
rule) and `joint_contract_id`. `bin/mcp-contract.py`: `compile --project`
streams the project's contract (exit 2 for a manifest naming none); `check
--project` compares the committed project contract byte for byte and applies
the profile to the joint; `lock` proves both committed contracts current,
compiles the joint, records `project_capabilities_sha256` and
`project_contract_sha256` beside the four digests, and writes the vocabulary
from the MERGED surface. Project schema 6 (`mcp.capabilities`, optional at 6,
forbidden below; the semantic check requires the set and the file);
capability schema 4's project form (`release.disabled`, forbidden below 4);
outputs v18 (`capabilities.project` rendered from the committed contract's
bytes, `mcp.project_capabilities` deployed -- required, null beside
`unavailable`, null or the object beside `ready`; `MCP_NOT_PUBLISHED` gains
it; `observe_mcp` takes it by keyword from the rendered document);
`migrate_v17_to_v18` (null, nothing else, no argument); `outputs_chain._steps`
gains 17. `bin/render-evaluation-report.py --project FILE` renders
`projects/<slug>/contracts/evaluation-report.md` from the joint contract,
creating the file with a short head on `--write` and refusing on `--check`
when it is absent; `load_written_cases(..., disabled=)` leaves out a release
case for a capability the project disabled, by name, and refuses every other
unknown. Both example manifests are at 6 WITHOUT the key -- the example
project's `capabilities.yaml` is the scaffold's (Run 5), and until then the
shipped fixtures are the control. The isolation matrix's `mcp.` prefix and
the doctor's `mcp` sensitive block already cover the new leaf; both were read,
neither was edited.

**Tests.** `tests/contract/test_project_agent_surface.py` (15, driving a
hand-built manifest under `tmp_path` over the example project's committed
surface and snapshot: the project contract, its id, the joint, a lock through
`load_lock` with the merged vocabulary, the disabled write absent from this
project's lock and present in the second fixture's, the tool-name refusals,
the three shapes parametrised, the render block and its refusal, the deployed
schema's coupling, the observer's source, the CLI's negative arms);
`test_output_migrations` (v17 fixture, chain-end renamed to
`test_the_chain_ends_at_version_18_with_nothing_of_a_projects_own` -- registry
and matrix regenerated -- and five v18 tests); `test_project_manifest`
(`downgrade_to_five`, the version 6 gate with both semantic refusals);
`test_evaluation_harness` (three: the joint derivation, the disabled-by-name
rule, the command's refusal); `test_disaster_kit._previous_version` at 18.
The plan's `test_the_example_projects_manifest_compiles_…` and
`test_a_projects_report_is_current_and_carries_the_merged_digest` need the
example project's manifest and report and are Run 5's, under the names §2
proposes.

**Battery** (`/tmp/s21-r4-battery.py`, 4/4): the collision refusal removed
(kill, `…named_for_a_release_tool_is_refused`); `release.disabled` ignored by
the join (kill, two tests); the migrator writing `{}` for null (kill, two
tests); the merged surface replaced by the release's (kill, two tests). Paired
controls `…contract_id_is_derived_from_its_surfaces` and
`…deployed_schema_couples_the_block_to_a_ready_plane` green under every
mutation; restore by copy + cmp.

**Targeted, all green:** the plan's list, with `test_rendered_migrations`
where the plan wrote `test_rendering` (no such module) and
`test_capability_profile`, `test_scope_vocabulary`, `test_lock_roster`,
`test_acceptance_registry`, `test_project_migration_sets`, `test_upgrade_plan`,
`test_render_isolation` and `test_session12_isolation_matrix` (offline) added
because their subjects moved. `bin/mcp-contract.sh check`, `app-contract.sh
--check`, `render-mcp-catalog.py --check`, `render-evaluation-report.py
--check` and the bounds doc all current. No full suite and no gate, by the
user's instruction; CI is the full check.

**Builds.**

1. `tests/contract/_outputs.py::carry_to_current` and the eleven sites
   (D1134), **first**, with its own battery, in its own commit.
2. `schemas/project.schema.json`: `schema_version` enum gains 6; optional
   `mcp.capabilities: string` with the `^projects/[a-z][a-z0-9-]{2,30}$`
   pattern, forbidden below 6; `config.py`: `SUPPORTED_PROJECT_SCHEMA_VERSIONS`
   gains 6; `validate_project_semantics` refuses a directory without
   `capabilities.yaml`. `bin/render-config.py --bounds-doc --write`.
   `project.example.yaml` → 6 with `mcp.capabilities: projects/example`;
   `project.second.example.yaml` → 6 without. (The example project's
   `capabilities.yaml` is Run 5's, emitted by the scaffold; **this run
   commits a hand-built one under `tmp_path` in tests only**, and the fixture
   manifest's key arrives in Run 5 with the file it names.)
3. `schemas/capabilities.schema.json`: the project form at 4 — the top-level
   optional `release: {disabled: [names]}`; a project manifest may not declare
   `kind: metadata` (a v4 `allOf` gate keyed on the presence of `release`, or
   on a `form: project` marker — decide in the run, and say why in the ADR's
   consequences).
4. `src/agentic_postgres/capability_manifest.py` (or wherever
   `load_capabilities_manifest` lives — `grep -n "def load_capabilities_manifest"
   src/`): `load_project_capabilities(set_root)`, `merged_capabilities(release,
   project)` refusing a tool or capability name the release declares and a
   disabled name the release does not; `project_capabilities_path(root)`,
   `project_contract_path(root)`.
5. `capability_compiler.compile_canonical(capabilities, surface, declared)`
   is called twice by `bin/mcp-contract.py` — once for the release as today,
   once for the project against the **merged** surface and the project's
   snapshot — and `compile_lock` takes both canonicals, joins them (contract
   id `<release>+<project>`, tools concatenated, `tools_sha256` over the
   joint list), applies the profile, and writes the vocabulary from the
   merged surface. `command_check --project` compiles the project's contract
   and compares it with `projects/<slug>/contracts/mcp-capabilities.canonical.json`;
   `command_compile --project` streams it; `command_lock` reads
   `mcp.capabilities` from the manifest it is already given.
6. `bin/deploy-project.py:2151`: unchanged in shape — the manifest it passes
   names the project's capabilities. `bin/session-21-check.sh`'s offline step
   6 gains `check --project` over both fixtures (it already runs them for the
   profile).
7. Outputs **v18** (`schemas/outputs.schema.json`, `migrate_v17_to_v18`,
   `CURRENT_VERSION = 18`, `rendering._mcp_block`): `mcp.project_capabilities`
   (D1136). The migrator adds the block as `null` and touches nothing else.
   The isolation matrix's classification and the doctor's redaction map: the
   prefix `mcp.project_capabilities.` and the bare leaf (D1111).
8. `evaluation_harness`: `derive_cases` is already generic over a contract;
   `bin/render-evaluation-report.py --project FILE [--write|--check]` renders
   `projects/<slug>/contracts/evaluation-report.md` from the merged contract;
   `tests/evaluation-cases.yaml` stays the release's, and a project's written
   cases, if any, live at `projects/<slug>/evaluation-cases.yaml` (optional,
   bound to versions the same way).

**Tests.** `tests/contract/test_project_agent_surface.py` (new; the
`AGT-TENANT-001` node ids in §2, driving a hand-built project manifest under
`tmp_path` against the example project's surface and snapshot);
`test_output_migrations` for v18; `test_project_manifest` for schema 6 (its
downgrade chain pops `mcp.capabilities`, D1104's lesson); `test_evaluation_harness`
for `EVAL-HARNESS-002`; `test_mcp_contract_command` (`grep -l "mcp-contract"
tests/contract`) for the three verbs with `--project`.

**Battery.** The collision refusal in `merged_capabilities` removed (kill);
`release.disabled` ignored by `compile_lock` (kill: the disabled tool is in
the lock); the migrator writing an empty object instead of `null` (kill in
`test_output_migrations`); the merged surface replaced by the release's in
the project compile (kill: `note_embeddings` does not resolve).

**Targeted:** `test_project_agent_surface`, `test_output_migrations`,
`test_backup_plane` (the eleventh site), `test_project_manifest`,
`test_project_retire`, `test_deployed_output`, `test_doctor_redaction`,
`test_diagnosis`, `test_fleet`, `test_backup_mirror` (D1104's five, by name,
each checked for existence individually), `test_session12_isolation_matrix`
(offline), `test_evaluation_harness`, `test_mcp_contract_command`,
`test_capability_compiler`, `test_rendering` (`grep -l "_mcp_block"`),
`test_cli_contract`.

### Run 5 — `apg agent init`, the example project's manifest, the documents

**Done.** 2026-09-11, on the `session-21` branch, in two commits. Two
divergence rows (D1148, D1149), battery 2/2 with paired controls green,
1370 targeted tests green across 18 modules in the first commit -- and CI
RED on it (`7d632b6`), on one test in a module the list omitted: the retire
proof downgrades a copy of the example manifest and now has a second key to
pop (D1149). The second commit pops it and runs every module that reads the
example manifest, 34 of them, 2023 tests green; CI read. The example project's capability manifest is **what the scaffold
wrote**, byte for byte, and a test keeps it so.

**Built, as listed, with these differences from the list.** `bin/agent.sh` /
`bin/agent.py`, one verb: `init --project FILE --operation NAME [--relation
NAME] [--kind read|write]` and `init --head`. Two things the list did not
say. First, **a write's scope is taken, not guessed**: `--relation NAME` names
the relation whose `:write` scope the entry requires (ADR 0201 §5's "the
relation the reviewer names"), refused on a read, required on a write, and
refused for a relation the merged surface does not publish -- so every entry
the scaffold emits compiles unchanged, which is `AGT-INIT-001`'s second clause.
Second, `init --head` prints the manifest's fixed head (the
`yaml-language-server` modeline, D1138; `schema_version: 4`; `capabilities:`),
so the committed example is provably `head + read + write` and nothing typed.
`--kind` may only confirm the kind the object derives (a read over an RPC has
one shape and is written by hand from `run_report`). Refused with exit 2, each
naming what the surface does publish: an operation the merged surface does not
name; a release-owned object (its capabilities are the release's, narrowed by
the profile or disabled by `release.disabled`); an agent-plane operation.
Exit 3 without a set. Order matters and the README says so: the file exists
before the manifest names it, because the semantic check refuses a manifest
naming a directory without one (Run 4's rule, met from the other side).
`bin/mcp-contract.sh` stopped refusing `compile --project` (the wrapper
predated the project form; the Python command already took it), and its usage
names the project form for all three verbs. `rendering._project_capabilities_
block` refuses an unreadable contract by name rather than with a traceback
(found when an empty file was left by a failed compile).

**The example project.** `projects/example/capabilities.yaml` (the scaffold's
two entries: `query_note_embeddings` grouped under `query_resource` over the
view's four columns, no filters, no orderings; `set_note_embedding` with both
arguments redacted and approval required), `contracts/mcp-capabilities.
canonical.json` (`example-note-embeddings-agent-v1`, 2 tools), `evaluation-
cases.yaml` (four written cases, one per kind per capability), and
`contracts/evaluation-report.md` over the joint contract
`notes-tasks-agent-v1+example-note-embeddings-agent-v1` (9 capabilities, 62
derived and 19 written cases). `project.example.yaml` names
`mcp.capabilities: projects/example`; both fixtures re-rendered -- alpha's
`capabilities.project` is the block, alpine's the explicit null.

**D1148.** The first contract ever to declare `requires_approval` met
`EVAL-HARNESS-001`'s coverage rule, which required a derived positive that
D870 had already reclassified as the approval refusal. `coverage` now exempts
exactly that cell for exactly that declaration; the written positive is still
required, and the example's says the intended call is refused today.

**Documents.** README §*Giving an agent your tables* (the order, the three
commands, the manifest key, the scopes and where they are granted, what a
project may not declare, the `$schema` line stated as a reading and not a
guarantee); `docs/mcp-tool-catalog.md` says a project's tools are beside its
contract; `docs/capability-plan.md` opens by saying it is historical and the
roster is the contract's.

**Tests.** `tests/contract/test_agent_command.py` (11: every object of the
example project scaffolds an entry that compiles through `project_inputs`;
no file written; the head; the refusals parametrised; the set requirement;
byte identity with the committed manifest and `check --project` reporting the
joint; and `AGT-TENANT-001`'s example-based node, named
`test_the_example_projects_manifest_compiles_to_its_committed_contract` --
shorter than §2 proposed, for the line length -- with `compile --project`
streaming the committed bytes). Run 4's three control tests moved to their
positive arms; `test_cli_contract` rosters gain both commands.

**Battery** (`/tmp/s21-r5-battery.py`, 2/2): the scaffold emitting
`requires_approval: false` (kill, the byte-identity test); the operation
lookup reading the release surface (kill, two tests). Controls: the set
requirement and the release-object refusal, green under both.

**Targeted, all green:** the plan's list, with `test_session12_documented_path`
where the plan wrote `test_documented_path`, plus `test_capability_profile`,
`test_lock_roster`, `test_scope_vocabulary`, `test_capabilities_manifest`,
`test_project_migration_sets`, `test_output_migrations`,
`test_render_isolation`, `test_api_contract_command`,
`test_documentation_index` and `test_acceptance_registry`, because their
subjects moved. No full suite and no gate, by the user's instruction.

**Builds.**

1. `bin/agent.sh` and `bin/agent.py`: `init --project FILE --operation NAME
   [--kind read|write]` (D1137); exit 2 for an operation the merged surface
   does not name, naming the ones it does; exit 3 without a merged surface
   (a manifest with no set); stdout only. The usage names `validate`
   (`mcp-contract.sh check --project`), `test` (`render-evaluation-report.py
   --project --check`) and `dry-run` (the runtime's, ADR 0182) as where they
   already live.
2. `projects/example/capabilities.yaml`: **emitted by the scaffold**, twice
   — `init --operation note_embeddings` (a read, `tool: query_resource`,
   scope `note_embeddings:read`) and `init --operation set_note_embedding` (a
   write, scope `note_embeddings:write`, `p_embedding` redacted) — with the
   `# yaml-language-server: $schema=../../schemas/capabilities.schema.json`
   line at the top (D1138) and the header comment. Its compiled contract at
   `projects/example/contracts/mcp-capabilities.canonical.json`; its report at
   `projects/example/contracts/evaluation-report.md`. `project.example.yaml`
   gains `mcp.capabilities: projects/example`. Re-render both fixtures.
3. `README.md` §*Giving an agent your tables* (new, after *Adding your own
   tables*): the manifest key, `apg agent init`, `check --project`, the two
   scopes an agent is then granted through `/admin/agents`, what a project
   may not declare, the `$schema` line. `docs/mcp-tool-catalog.md` gains a
   sentence that a project's catalog is rendered beside its contract.
   `docs/capability-plan.md` gets one paragraph: the plan is historical; the
   roster is the contract's.

**Tests.** `tests/contract/test_agent_command.py` (new; `AGT-INIT-001`'s node
ids, driving `bin/agent.sh` for every object of the example project and
asserting each entry compiles under `check --project` when placed in a copy
of the manifest under `tmp_path`); `test_cli_contract` (`SHELL_COMMANDS`
gains `bin/agent.sh` and `bin/agent.py`, D1014); `test_documented_path`
(D693's guard over README commands).

**Battery.** The scaffold emitting `requires_approval: false` (kill: the
byte-identity test against the committed manifest); the operation lookup
reading the release surface instead of the merged one (kill: `note_embeddings`
refused).

**Targeted:** `test_agent_command`, `test_cli_contract`, `test_documented_path`,
`test_repository_contract`, `test_project_agent_surface`, `test_mcp_contract_command`,
`test_evaluation_harness`, `test_mcp_catalog`.

### Run 6 — the bump

**Done.** 2026-09-11, on the `session-21` branch. One divergence row (D1150),
1010 targeted tests green across 13 modules, the live module collecting six
proofs under `--setup-plan` with the roster variables set, and the Session 1
gate run once on the clean tree before the push.

**Built, as listed, with these differences from the list.** `CURRENT_SESSION`
21 and `VERSION` 1.2.0, with ADR 0162's pricing in the constant's comment (four
additive schema moves; a minor, confirmed or stopped by Run 7's `upgrade
plan`). Six requirements registered with the node ids the runs actually wrote
-- `test_scope_vocabulary`'s seven for `AGT-VOCAB-001` beside the two of
`test_scope_registry`; `test_lock_roster`'s six for `AGT-ROSTER-001` beside
`test_mcp_tools`' four; `test_project_agent_surface`'s eight, the example
project's compile in `test_agent_command`, the v18 migrator and the matrix's
classification for `AGT-TENANT-001`; `test_agent_command`'s five and the CLI
roster for `AGT-INIT-001`; three harness tests for `EVAL-HARNESS-002`, one of
them written here (`test_a_projects_report_is_current_and_carries_the_merged_
digest`, the report's digest equal to the joint contract's and to the lock's);
Run 1's two kit tests for `REC-KIT-003`. **Four claims, not two** (D1150):
ADR 0089's guard refused the plan's joins, so `EVAL-HARNESS-002` and
`REC-KIT-003` are `project_evaluation_harness` and `kit_read_at_a_later_
release`, each dated 21, and the second gained the live half it lacked.

**The live module.** `tests/deployment/test_session21_agent.py`, six proofs,
gated on the three roster variables (the administrator's password is not a
roster variable; `admin_session` skips by itself, as Session 16's module
relies on). Two things the plan's text had wrong, both found by reading the
product before writing the proof. First, **the tenant write is refused, on
purpose**: the example manifest is what the scaffold wrote and the scaffold
declares approval, so the proof named for a round trip is
`test_betas_lock_carries_the_tenant_write_the_plane_refuses_it_pending_
approval_and_audits_it` -- the write registered from beta's lock is reached
over a note the owner holds, carrying rig 21d's 768-float string, refused
pending approval, audited with that reason and the joint contract's hash, and
the tenant row untouched. A proof that rewrote the manifest to make the write
succeed would measure a manifest the release does not ship. Second, **agents
are created through `auth_create_agent` on both projects, not through the
admin endpoint**, because the admin session the suite holds is alpha's; the
ceiling at CREATION is measured through alpha's endpoint (422 for the tenant
scope, 201 for a release one), and the ceiling at ISSUE through
`/auth/agent-token` on both -- beta issues, alpha refuses the same stored
grant. Beta's owner is a subject registered on beta through `auth_create_user`
and swept with its rows. The other four: six tools on alpha and seven on beta
with a reader that can neither see nor call the tenant write and whose call
is audited (ADR 0140 re-run); the deployed lock recording the scaffold's
manifest and contract digests and beta's document the block, alpha's the
null, both at v18; beta's document and lock publishing the digest the example
project's report carries, alpha's the release report's; and the kit exported
before the deploy verifying at this release.

**The gate.** `bin/session-21-check.sh` derived from Session 20's by diff
(`/tmp/s21-r6-gate-derive.py`, every substitution anchored once; header and
usage rewritten whole, both halves read line by line). **Session 18's
declarations are FIVE, not the four D1133 counted**: `--kit-dir`,
`--replacement-host-outputs`, `--replacement-bootstrap-state`,
`--restore-evidence-file`, `--rehearsal-evidence-dir`, parsed, pre-flighted
(files as files, the two directories as directories) and exported exactly as
Session 18's gate does. Host mode gains step 4c, `check_the_tenant_surface_is_
deployed`: both documents at v18 with a ready plane, beta recording
`projects/example` and alpha recording null, and `/auth/login` answering a
4xx on both before the suite runs (a deploy through 21 recreates the issuer,
ADR 0155). Offline step 6 checks the example project's report beside the
release's; `check --project project.example.yaml` there now compares the
project's committed contract too. `SHELL_COMMANDS` gains it; `test_gate_
contract`'s typed-number scan passes on it.

**Documents.** README's status paragraph at Session 21 and 1.2.0 (*Adopt
1.2.0*); every `--through-session 20` and `--session 20` a reader is told to
type moved to 21 (README, `docs/api-operations.md`, and
`docs/pool-operations.md`, which the plan's grep pattern missed and
`test_the_documented_path_passes_session_numbers_this_release_accepts`
caught). `docs/new-team-member.md` carries no session number to re-derive.
The matrix and the product contract regenerated (178 requirements before,
184 after).

**Targeted, all green:** `test_evidence_claims`, `test_acceptance_registry`,
`test_cli_contract`, `test_session12_documented_path`,
`test_repository_contract`, `test_gate_contract`, `test_evaluation_harness`,
`test_documentation_index`, `test_compatibility`, `test_upgrade_plan`,
`test_upgrade_command`, `test_session_eight_gate_modes`, `test_disaster_kit`;
then `bin/session-01-check.sh` once on the clean tree, per the plan and the
working agreement (a run close before a trip is one of the cases). CI read.

1. `src/agentic_postgres/__init__.py`: `CURRENT_SESSION = 21`; `VERSION` →
   `1.2.0` with the ADR 0162 reasoning in the comment (four additive schema
   moves, each with older versions still loading — a minor is proposed and
   Run 7's `upgrade plan` confirms or stops).
2. `tests/acceptance-registry.yaml`: the six requirements of §2 (`REC-KIT-003`
   from Run 1 gets its `target_session`), node ids as the runs named them;
   `evidence_claims.py`: the two claims; `bin/render-acceptance-matrix.py
   --write`; `bin/render-evaluation-report.py --write` and `--project
   project.example.yaml --write`.
3. `tests/deployment/test_session21_agent.py`: the five live halves of §2,
   `requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS",
   "APG_PROJECT_B_OUTPUTS", "APG_ADMIN_PASSWORD_FILE")`, each docstring saying
   what only a deployment can prove. Agents are created through the admin
   endpoint with `admin_session` and revoked in `finally`; the tenant write
   goes through the plane with `agent_session` (Session 16's module is the
   model) after a note is created with `bin/api.sh create-note` under a
   `dev-token.sh`-minted token, and the argument is rig 21d's string. The
   ADR 0140 re-run: a reader agent on beta lists no `set_note_embedding` and
   is refused calling it by name, the refusal audited.
4. `bin/session-21-check.sh` **derived from `bin/session-20-check.sh` by
   diff** (D505, D507, D678, D693, D703, D1108, D1109): `readonly SESSION=21`,
   header and usage rewritten line by line, both halves; host mode's
   precondition block: both projects deployed `--through-session 21`
   publishing outputs v18, beta's manifest at schema 6 naming
   `projects/example` for both keys, `/auth/login` answering on both (the
   issuer was recreated); **Session 18's four declaration flags re-admitted**
   (D1133) with their pre-flight loop; offline step 6 runs `mcp-contract.sh
   check --project` on both fixtures and the project report's `--check`.
   `SHELL_COMMANDS` gains it.
5. `grep -rn "through-session 20" README.md docs/*.md` and update every
   documented line; `docs/new-team-member.md` re-derived by diff (D693).

**Targeted:** `test_evidence_claims`, `test_acceptance_registry`,
`test_cli_contract`, `test_documented_path`, `test_repository_contract`, the
gate-derivation guards (`grep -l "session-20-check" tests/contract`). Then
`bin/session-01-check.sh` once on the clean tree (D1104: the five readers
CI found last time are in Run 4's list by name; the gate is where the ones
nobody listed appear), and `pytest --setup-plan tests/deployment/test_session21_agent.py`
with the four variables set to the fixture documents (D671, D676).

**Push.** CI is expected **green**. Record the run id.

### Run 7 — the trip

Before the day: `grep -n "goes wrong" -A20` in the Session 11, 17, 18 and 20
guides and plans (D977); Session 20's §5 Run 7 Done paragraph and D1116–D1120
(the four gates that were free to save); `pytest --setup-plan` for every
deployment module with the variables set; the transport script
`/tmp/r7-transport2.sh` in WSL takes a SHA (edit it, do not retype it); the CI
watcher `s19-ci-watch.sh` in the scratchpad with `SHA=` edited; the host's
gate scripts under `/tmp` did not survive if the kernel restart happened —
rebuild `g21-host.sh` from `bin/session-21-check.sh --help` with the sentinel
derived by `/tmp/g20-sentinel.py`'s method.

Then, in order, **the operator at a TTY runs anything with `sudo`** and pastes
the output; the agent reads, never redirects a deploy (D972):

1. **Copy the DR kit off the host**: `scp -r op@…:/home/op/kit-2026-09-11
   ~/dr-kits/`, `bin/dr-kit.sh verify ~/dr-kits/kit-2026-09-11` from this
   checkout (exit 0 at v17; after the deploy, exit 0 at v18 too — that is
   `REC-KIT-003` read live, once, as a reading).
2. Bundle the branch's bump commit, `scp`, `git bundle verify`, fetch, `git
   rev-parse FETCH_HEAD` confirmed, checkout as `op`, `uv sync`.
3. As root: `bin/upgrade.sh check --project alpha-dev` and `plan --candidate
   …` (D1106: `plan` needs `--candidate`); the same for beta. **Record the
   bump class** (D1081): a `minor` confirms 1.2.0; a `major` is §9's stop.
4. Deploy alpha `--through-session 21`, unredirected: lock schema 4 with six
   tools and the vocabulary, `auth` and `mcp` recreated (ADR 0155), outputs
   v18 with `project_capabilities: null`, every route `ready`, the doctor
   10/10, `/auth/login` answering. **Read the lock on the host** (`sudo cat`
   of the rendered lock's `tool_count`, `tools_sha256`, `vocabulary.data`),
   never the deploy's summary line (D941).
5. `project.beta.yaml` on the host → `schema_version: 6`, `mcp: {…,
   capabilities: projects/example}` (the operator edits it; `--render-only`
   as op first). Two deploys (D1107): the release first, the manifest second.
   Read: seven tools, `vocabulary.data` carrying `note_embeddings:read/write`,
   `project_capabilities.root` = `projects/example`, the doctor 10/10.
6. `sudo chown` is **not** needed after these deploys (D1110); D1131's proof
   constructs its own state.
7. Transport the merge commit if any repair landed, check out `main` on the
   host, `uv sync`; gates: `bin/session-01-check.sh`, `bin/session-21-check.sh
   --mode offline`, `--mode host` (root, the documented arguments, **with
   the four Session 18 declarations** — export a fresh kit first, as
   `g18-host3.sh` did — so one sweep writes the host half, D1133), `--mode
   external` from the workstation (D466). `evidence/session-21.json` with its
   claim table pasted into this run's Done paragraph. **Expected:** the four
   D1123 claims `passed` again; `honest_readers` `passed` for the first time;
   `disaster_kit` passed against the fresh kit.
8. **The round trips, by hand as well as by the gate**, because the gate's
   pass is a number and the trip's record is what the next reader reads: on
   beta, an agent `s21-writer` with `[meta:read, note_embeddings:read,
   note_embeddings:write]` created through `/admin/agents`; `list_resources`
   naming `note_embeddings` with its scope; `describe_resource` for it;
   `set_note_embedding` with `dry_run: true` then `false` against a note made
   by `bin/api.sh create-note`; `query_resource` over `note_embeddings`
   returning the row; the audit rows for all four through `/admin/audit`. On
   alpha the same agent creation **refused** at the admin endpoint with the
   ceiling's message. Then `update_task_status` **through the agent plane**
   against a row `bin/api.sh create-task` made — the compare-and-swap's first
   agent-plane run on real data (Session 20 ran it over REST). Revoke both
   agents.
9. D rows for what the day found, this run **Done.**, `CLAUDE.md` §2 and
   §9, memory, commit, push, CI; merge fast-forward to `main`, delete the
   branch.

---

## 7. Evidence and claims

| Claim | Offline may report | Needs a live half for |
|---|---|---|
| `agent_tenant_surface` | The vocabulary derived for the release and the merged example surface; the collision refusals; the ceiling from two locks in-process; a five-tool lock loading and a hand-edited one refused; the example project's contract compiled from the merged surface; v18's migrator; the classification of the new leaves | Beta issuing a tenant scope and alpha refusing it; alpha serving six and beta seven; the reader on beta neither seeing nor calling the tenant write; the tenant write round-tripping and audited on beta |
| `agent_scaffold` | The scaffold's entries compiling for every object of the example project; the committed manifest byte-identical to the scaffold's output; the refusal of an unknown operation | Beta's deployed lock recording the project contract the scaffold's manifest compiled to |
| `evaluation_harness` (`EVAL-HARNESS-002`) | Cases derived for the merged contract; the project report current | Beta's deployed digest equal to its own report's |
| `disaster_kit` (`REC-KIT-003`) | `verify` carrying a v16 document to current; the third outcome | Session 18's live half, in this gate's one sweep (D1133) |
| `honest_readers` (20) | Unchanged | D1131's rewritten proof, run as the checkout owner against a state it constructs |
| The eleven AGT claims of 8, 9 and 16 | Unchanged | Re-run on alpha and beta in the same sweep (D942); alpha is the control |
| `fresh_host`, `documented_path` (12) | — | Untouched (ADR 0197); Session 25's |

The five D478 claims and `replacement_host_restore` stay `not_run`. No claim
spans both modes; a skip is not a pass; nothing on the branch is expected red.

---

## 8. Security invariants this session touches

| Invariant | Control | Proof |
|---|---|---|
| An agent cannot run SQL | No input accepts a query, a column list or a path; the compiler cannot emit one; a read over an RPC with arguments is refused (D1129) | `AGT-SQL-001` unchanged; `test_the_three_shapes_a_project_may_not_declare_are_refused` |
| The derived vocabulary can never name an administrative or storage scope | The two classes stay enumerated; a relation named for one is refused at load and at merge; the partition is asserted per surface | `AGT-VOCAB-001` |
| An unauditable write does not happen | `begin` before the scope check, unchanged for a tool registered from the lock | `…is_audited_before_its_scope_is_checked` |
| A hidden tool is still callable, so the boundary is the call-time check (ADR 0140) | `_resource_for` / `_write_for` refuse; discovery filters by `discoverable_by` | The ADR 0140 proof re-run against a roster that is not six |
| The lock is the answer (ADR 0127), and now the whole of it | `tools_sha256` recomputed at load; kinds and shapes checked; the pair required | `AGT-ROSTER-001` |
| A profile only narrows (ADR 0183) | Unchanged; removal lives in the project's capability manifest, not the profile (D1139) | `test_capability_profile` unchanged; `…leaves_this_projects_lock_and_the_second_fixtures_keeps_it` |
| The MCP runtime and the issuer hold no credential | The lock carries names, bounds and a vocabulary; `FORBIDDEN_VARIABLES` unchanged; the auth mount is read-only | `test_the_agent_plane_holds_no_database_credential_and_no_signing_key`, re-run |
| A tenant tool addresses only what the reviewed surface publishes (ADR 0050) | Resolution against the merged `relations` and `rpcs`; `agent_rpcs` platform-only | `AGT-TENANT-001` |
| Projects share no project-scoped value | The new leaves classified in the matrix | `DEP-ISO-001`, re-run |
| A report may not substitute an answer for a failure to determine one (ADR 0195) | `verify` reports *cannot be carried* apart from *invalid*; `init`'s exit 2 names the operations it knows; the loader's refusals name the field | `REC-KIT-003`, `AGT-INIT-001` |
| A scope that stops existing is refused at issue and inert at call time (ADR 0200) | The ceiling from the deployed lock; no capability requires the name | Rig 21c, and the ADR's statement |

---

## 9. Stop conditions

Stop and ask when:

- **rig 21a shows FastMCP 3.4.0 cannot register a tool whose parameters are
  data** — neither a constructed signature nor an explicit schema reaches
  `tools/list` with the derived names, or a call with an undeclared argument
  reaches the handler with nothing refusing it; the registration shape is
  then decided with the operator, not written around;
- the derived vocabulary would admit an administrative or a storage scope, or
  a name for a base table (ADR 0006's reason);
- a roster read from the lock would let a lock serve a tool the compiler did
  not digest;
- the issuer would need a second file, a database read or a network call to
  learn the vocabulary — the lock is the answer or the design is wrong;
- **`upgrade plan` on the host prices the change at major** (Run 7 step 3);
- CI on the branch is red on **any** test — nothing is expected red;
- a currently-passing test would be weakened, or an equality turned into a
  containment check — every replacement above is a *stricter* test authorised
  by ADR 0200 or 0201, and one that is not stricter is a stop;
- the beta deploy leaves `auth` recreated and `/auth/login` not answering —
  fix forward on the host with the operator; never a manual container start;
- a tenant capability would need `agent_rpcs`, a metadata kind, a query
  argument on a read, or a `raw` operation to do something an adopter
  reasonably wants — a product decision for a later session, recorded, not an
  exception;
- `--render-only` stops working with no host and no root, on a manifest at
  any schema version 1–6;
- a session would want the vocabulary from a served document (ADR 0158,
  D1135).

---

## 10. Open items this session carries and creates

**Carried in, untouched, named so nothing inherits them silently:** D930 (two
fields named `capabilities_sha256` digest two files; the host's
`capabilities.yaml` still reaches only the render — D1127); D1045; the
rotation performed (D860); `replacement_host_restore` (D1028); `fresh_host`
and `documented_path` (ADR 0197); the audit and idempotency tables' retention
(Session 24 states it); D1099 (`migrate.sh status` and an out-of-order
pending migration, third-party).

**Created here:** a read over an RPC with arguments has no shape and is
refused (D1129) — Stage 4's proposal system inherits the question; a
project's *written* evaluation cases are optional and unproven until a
project writes one; the ceiling's role→class mapping is the one place an
agent's *kind* of authority is still enumerated, by design.

---

## Appendix — what to consult, and how a run is executed here

**Consult, in this order.** `docs/plans/stage-3-plan.md` §1 rows D1083,
D1070, D1072, D1081 and §5 *Session 21*, §8 and §10 (the `authz_version`
question); this document's §1; `docs/plans/session-20-implementation-plan.md`
§1 rows D1121–D1123 and its §5 Run 7 Done paragraph (what the last trip
cost); `docs/plans/session-16-implementation-plan.md` §1 (D861–D943: the
agent plane's last change, and D933's measurement with its control);
`docs/plans/session-19-implementation-plan.md` §1 D1056; ADR 0006, 0079,
0100, 0120, 0127, 0140, 0141, 0177, 0183, 0184, 0195, 0196, 0198; `FINDINGS.md`
F-025; `docs/session-11-operator-guide.md` §2 before Run 7.

**How a run is executed in this repository** (the short form of `CLAUDE.md`
§1 and §5; read those, they are the record of what each of these cost):

- The Bash tool is Git Bash on Windows. The tree is in WSL:
  `wsl bash -lc "cd ~/projects/agentic-postgres && . .venv/bin/activate && …"`.
  Anything with nested quotes, `$VAR`, a heredoc or a loop variable goes in a
  script written with the Write tool to `\\wsl$\Ubuntu\tmp\x.sh` and run with
  `wsl bash -lc "bash /tmp/x.sh"`, printing its own exit codes.
- File content and commit messages are written with the Write tool and read by
  the script (`git commit -F /tmp/msg.txt`). Never a heredoc for content.
- `chmod 755 bin/*.sh bin/*.py deploy.sh` before every `git add`.
- Never pipe a suite or a gate into `tail`; redirect to a file, `rm` it first.
- `PYTHONDONTWRITEBYTECODE=1` and `__pycache__` cleared before a battery.
- A run's commit: `ruff format && ruff check` (print the exit code), the
  targeted modules — **each named module checked for existence individually,
  never by association** (D1104) — the derived-document generators whose
  inputs moved, `chmod`, `git add -A`, commit with `-F`, push to
  `session-21`, then read that SHA's verdict: `gh api
  "repos/Virabyan99/agentic-postgres/actions/runs?head_sha=<40 chars>" --jq
  '.workflow_runs[] | [.id,.status,.conclusion] | @tsv'`, judged on HTTP
  status, three buckets (D1059). **Read it every time** (D1120).
- **A commit message is not evidence that the diff contains what it says**
  (D1116): before the message is written, `git diff --stat` against the list
  of repairs it claims, one line each.
- A run that renames, removes or adds a test function puts
  `test_acceptance_registry` in its targeted list (D1119); one that adds or
  removes a `bin/` command puts `test_cli_contract` there (D1014).
- **A targeted list is derived from the tree, never from the plan's text**
  (D1146, D1149 -- missed in two consecutive runs). A run that removes a
  definition greps the whole tree for its readers (`git grep -n <name> --
  tests bin src services`); a run that changes a shipped fixture greps for
  the fixture's readers (`git grep -l project.example.yaml -- tests`) and
  runs every module found, whole. The plan's list names what a run ADDS;
  the grep names what it CHANGES, and CI has caught the difference twice.
- Documentation-only commits run nothing before push. Code runs the targeted
  modules; CI is the full check. The gate (`bin/session-01-check.sh`) runs on
  a clean tree at Run 6's close and before the trip, never at a run's close.
- A rig is a throwaway script with a control arm, its output in a file and its
  numbers pasted into the Done paragraph. Never write a measurement you did
  not run (D267). Delete what a rig publishes under `.generated/` unless the
  key already existed.
- The battery: every mutation's anchor pre-flighted to match exactly once and
  a miss fatal (D269); a paired control the mutation cannot reach, in the same
  invocation, green (D499); the reader distinguishes `FAILED` from `ERROR`
  (D386); restore by copy and `cmp`, never `git checkout --`; a survivor is
  evidence and is read as such (D493, D498).
- The host: `op` over SSH with `-i ~/.ssh/agentic_postgres_ed25519` for reads,
  renders and offline gates; anything reaching Docker or `sudo` is the
  operator at a TTY, and the agent reads the pasted output. Never redirect a
  sudo deploy (D972). Never retry ACME. `apg-diag` verbs for read-only
  diagnosis as `apg-agent`.
- **A proof calls the product's own command** rather than hand-rolling the
  request that command makes (D1114, D1117): three of Session 20's four real
  defects were found that way.

**Grep the plans before measuring a third party.** FastMCP: D428, D441, D456,
ADR 0128, ADR 0140 (rig5's four arms — the pipeline and the hook seams); the
issuer's ceiling: ADR 0079, D266; PostgREST RPC argument casting: ADR 0127
(the in-list rule), ADR 0139 (`PGRST202`), D470; the lock's schema versions:
D883, ADR 0177, ADR 0179; the outputs migrator's hand-chained tests: D965,
D1105; the isolation matrix's classification: D702, D1029, D1111. Nothing
indexes the ~1,140 measured facts by subject; `grep` is the index.
