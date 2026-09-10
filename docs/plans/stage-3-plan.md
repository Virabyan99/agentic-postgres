# Stage 3 — plan of record

**This is a stage plan, not a session plan.** It sits above six session plans
and owns what all of them would otherwise repeat: where Stage 3 starts, what
the Stage 3 specification asks for that this repository already has or refuses,
the four decisions CLAUDE.md §4 requires a new body of work to settle, and the
open items carried in from nineteen closed sessions.

**§1 is the point of this document.** The Stage 3 specification was written
against Stage 2's *specification*, not against Stage 2's *tree* — and Stage 2
did not happen the way that document assumes. §1 is the list of places where
those differ, measured rather than recalled. It is why the answer to
*"twenty-four more sessions?"* is **six**.

**It builds nothing.** No requirement is registered here, no ADR is written
here, and no code changes because of it. Each of the six sessions gets its own
plan, and §11 says what shape those take.

---

## Status — read this first

```
STAGE 2 IS CLOSED.  evidence/session-18.json: 101 claims, 93 passed, 8 not_run,
                0 failed (2026-09-06, release 054f54e). SESSION 19 IS CLOSED
                (2026-09-10): a repair session, nineteen defects, no plane
                built, no requirement registered. Release 1.0.1 is tagged on
                b8bab01.
HEAD            a0d853f, main, local and origin identical (D1060's record,
                documentation only).
CURRENT_SESSION 18. Stage 3 numbers its releases 20-25. Session 19 moved
                VERSION alone, so 19 is a session that was never a release,
                and the ordinal skips it (D1063).
template_version 1.0.1. What a major promises is product-contract.md §7's
                sentence (D991, ADR 0162).
outputs schema  v16.  project manifest schema 4.  capability schema 3.
ADRs            197, next free 0198.   migrations 30, released and applied,
                fix-forward only.   requirements 171 (163 P0, 8 P1, 0 P2).
divergences     D1-D1060 recorded. D1061-D1086 recorded here.
                **Next free: D1087.**
PostgreSQL      18.4, pgvector 0.8.6, pinned by digest. STAYS. Decided by
                the operator on 2026-09-10 (D1061).
```

**Two Stage 1 claims are still unproved after Stage 2 and Session 19 settled
what each means** (ADR 0197). They are not Stage 3 work, and one of them is the
measurement Stage 3 exists to pass.

| Claim | What it needs now | Where the spec puts it |
|---|---|---|
| `fresh_host` | **Nothing but a file.** An empty host reached a working deployment on 2026-09-08; supplying its `outputs.json` as `APG_FRESH_HOST_OUTPUTS` is the operator's mechanical step | inside its Sessions 26 and 47 |
| `documented_path` | **Answered, and the answer is no.** `DX-001` forbids source edits and the walk needed seven. It can only pass after the tenant extension point lands, walked again by somebody who did not build it | its whole Session 47 |

---

## 0. Where Stage 3 actually starts

Session 18 closed at `52c534c` with 93 of 101 claims passed and the `1.0.0`
tag on `054f54e`. Then somebody who had not built the product used it: an
adopter built an application on 1.0.0, on a host that started empty, and wrote
twenty-five findings (`FINDINGS.md` in the launch folder). Session 19 repaired
nineteen of them, tagged `1.0.1`, and left the rest in the ledger's §8 with a
reason on every row. **The Stage 3 specification predates all of that**, and
the decision report written at Session 18 Run 5 already said what Stage 3 must
start from: *"§4's premises corrected — no coordinator, no PostgreSQL 19, no
public port"* (`docs/stage-3-decision-report.md` §5).

**The numbers that shape Stage 3's plan, all measured at `a0d853f`:**

- **807 tracked files. 104,855 lines under `tests/`.** The proof apparatus is
  still larger than the product and still the thing that scales with session
  count. Stage 2's six sessions added 21,500 lines of tests.
- **171 requirements across twelve id families** — SEC 35, AGT 20, CFG 16,
  DBX 15, OPS 14, DEP 14, REC 12, STO 11, API 10, FLEET 7, DX 6, IDN 5. No
  `future` placeholders remain, so a session's requirements arrive with their
  proofs in the commit that moves the constant (D690).
- **~70 entries under `bin/`, essentially all with `--json`**, eighteen
  `session-NN-check.sh` gates, and **`bin/apg.sh` since Session 13** — one
  front door over every verb, with no roster of its own (ADR 0002).
- **Three frozen, hashed contracts**: `contracts/postgrest-openapi.canonical.json`,
  `contracts/app-openapi.canonical.json`, and
  `contracts/snapshots/mcp/mcp-capabilities.canonical.json`, with
  `capability_contract_sha256` and `capability_lock_sha256` published in every
  deployed document. This is the intermediate representation the spec's
  codegen sessions ask to introspect, and it already exists.
- **Zero lines of coordinator, outbox, job queue or Studio** anywhere under
  `services/`, `src/`, `migrations/` or `bin/`. The nearest thing to a worker
  is `storage_cleanup.py`'s lease-based tombstone collector inside the auth
  service, which is a garbage collector and not a job substrate.
- **One local throwaway cluster already exists**, as a test fixture rather
  than a product: five contract modules `docker run` the locked image, create
  the roles the bootstrap plane creates, and apply every released migration.
  Measured on this workstation on 2026-09-10, twice: **10.3 s and 12.9 s wall**
  for the whole module, of which the cluster's readiness and role setup was
  4.4–4.8 s and applying thirty migrations 4.7–6.6 s. The restore from the
  mirror took 247 s on the replacement host (D1028's record). Those two numbers
  are D1066.

**What Stage 3 has is a specification written before Session 12's evidence
existed**, whose own status line says *"pending the Stage 2 Session 24 decision
gate"*. There was no Session 24; the gate it waited for was Session 18 Run 5,
and its report is what this plan starts from. **So §1's job is the one the
Stage 2 plan named**: the list of places where the specification asks for
something this repository already has, or asks for it in a shape this
repository refuses. It is longer than Stage 2's, because the specification was
written one specification further from the tree.

**One thing about the specification is right and load-bearing and this plan
keeps it whole**: the developer-experience layer is *a client of the surfaces
that exist, and never a new authorization path* (its §4.1 and §4.4). `apg`,
a generated client and a Studio each hold nothing the invoking human does not
already hold, and every RLS and audit guarantee that applies to a direct call
applies identically through them. That sentence is the security section of
this plan, and Session 19 supplied its motto: `bin/apg.sh`'s header, *"this
adds a name, not a layer."*

---

## 1. The divergence table

Six columns, the house shape. Rows are **measured facts about this repository
as it stands at `a0d853f`**, not predictions about the sessions. Where a
premise could not be settled by measurement, the `Decision` column says so and
names the run that measures it.

**Next free number after this table is D1087.**

| # | Spec says | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D1061** | Header: *"Baseline database version: PostgreSQL 19 (GA expected September/October 2026)."* Session 25: *"Move the Stage 1/2 base images and all existing projects onto PostgreSQL 19 as the new baseline before any Stage 3 tooling is built."* Four sessions stand on it: 25, 27 (*"non-restart logical replication"*), 36 (`pg_plan_advice` / `pg_stash_advice`) and 40 (SQL/PGQ). | **The tree runs PostgreSQL 18.4, pgvector 0.8.6**, pinned by digest (`versions.env`, `POSTGRES_IMAGE`), and no proof reads a 19-only feature. Measured 2026-09-10: postgresql.org's roadmap lists 19 as **beta 3 (2026-08-13), GA "planned September 2026"**; Docker Hub has `postgres:19beta1` and `19beta3` and **no `postgres:19`, no `19rc1`, and no `pgvector/pgvector:pg19`** — pgvector is load-bearing and carries a real workload. pgBackRest 2.59.1, the apt pin, supports 19beta3. PostgREST 14.16 and PgBouncer 1.24.1 against 19: unmeasured. The 19 release notes (draft, *"AS OF 2026-07-18"*) do list all eight features the spec names; the 18 notes already list asynchronous I/O (`io_method`), so *"async I/O worker autoscaling"* is a 19 refinement (`io_min_workers` / `io_max_workers`) of a feature the tree already runs. | **Stage 3 stays on PostgreSQL 18.4. The operator decided this on 2026-09-10, during this plan's audit, and it is recorded rather than argued.** Spec sessions **25, 36 and 40 are cut**; 27's mechanism is rebuilt (D1066); 42, 43 and 44 lose their *"under v19"* premise and become what they already are (D1075–D1077). A future move to 19 is its own ADR: extension builds, the pgBackRest pin, and `upgrade plan` pricing the change. | A baseline on a beta is a baseline on a moving target, and two of the four dependents would have been built on features that do not exist in any GA release today. **The one thing the spec wanted 19 *for* — a dev environment that resets in seconds — does not need it** (D1066): the slow path was R2 with `process-max` 1, a network problem, and the fast path is a local file-level cluster on the pinned image. | ADR at the move, if ever; 0162 prices it |
| **D1062** | §0: *"Stage 1/2 delivered correctness and governance through scripts, YAML files, and a coordinator API."* §3: the platform operator *"controls the VPS, DNS, provider credentials, and the coordinator."* §1.4.5: revocation *"with or without the coordinator running."* §4.1: `apg` calls *"PostgREST/FastMCP/coordinator surfaces."* | **There is no coordinator.** The word occurs ten times in five documents under `docs/` — the stage plan where it is declared non-authoritative, the decision report where its absence is a finding, and three records of that — and **zero times under `services/`, `src/`, `bin/` or `migrations/`**. What a deploy depends on that is not on the host is the secret provider, felt at step 5 and by nothing running (D976, D990). What a human authenticates to is the auth service (`/auth/login`, `/auth/refresh`, `/auth/me`). | Every *"auth to the coordinator"* in the spec reads as *auth to the project's auth service*, and every *"with or without the coordinator"* is already true because there is nothing to be without. **No session builds one**, and §9 makes wanting one a stop condition, as Stage 2's §9 did. | The Stage 2 plan's §2.1 kept the coordinator non-authoritative and Session 17 then found it did not need to exist at all (ADR 0185: an operator's read over the host's own documents is not a catalog). A Stage 3 that built a coordinator to be a client of would be building the thing Stage 2 proved unnecessary in order to satisfy a sentence. | 0185 |
| **D1063** | §0: *"Stage 2 (Sessions 13–24)"*; delivery constraint: *"24 additional high-intensity coding sessions, Sessions 25–48."* | **Stage 2 was Sessions 13–18** (`docs/plans/stage-2-plan.md` §3, D705). Session 19 was a repair that moved `VERSION` alone and left `CURRENT_SESSION` at 18. Nothing in the tree asserts consecutive session numbers — `grep` finds the ordinal formatted into evidence file names and nowhere compared to its predecessor — so the constant may move 18 → 20. | **Stage 3 begins at Session 20 and numbers its releases 20–25.** Session 19 is never a release: no `session-19-check.sh`, no `--through-session 19`. The spec's numbers appear only in this table and in §3's *absorbs* column. | Renumbering the spec silently is cheaper than carrying two numberings, and the ordinal is the evidence model's key (D705), so it has to name releases that exist. A gap is honest; a gate script for a session that registered nothing would be a file that could never go green. | — |
| **D1064** | Stage 4 §0: *"Stage 2 establishes governance, observability, upgradeability, durable bounded jobs, and multi-project operation."* §8.1: *"Stage 2 establishes bounded background jobs."* §9.2: *"The durable event path should build on the Stage 2 job/outbox substrate."* | **Nothing exists.** `outbox`, `job_queue` and `background job` match nothing under `services/`, `src/` or `migrations/`. Stage 2's D711 made the substrate evidence-selected — *"built only if the semantic track is selected, and then as that track's substrate"* — and the track was never selected (D714, D698: the pgvector example was never registered either). The one worker in the tree is `storage_cleanup.py`'s lease-based tombstone collector, a garbage collector for one table. | **Stage 3 does not build it**, and says so in §6 so Stage 4 can price it. Stage 4's pillar III (durable workflows) and pillar IV (connectivity and events) are both written *"on top of"* it and both must budget the substrate itself. | A substrate with no consumer was the most expensive kind of dead code in Stage 2 (D711), and Stage 3 has no consumer for it either: nothing in the DX layer is asynchronous. Building it here to make Stage 4's premise true would be paying for a sentence. | — |
| **D1065** | Session 26: *"Replace the current collection of `bin/*.sh` scripts and ad hoc coordinator calls with a single CLI binary … `apg connect`, `apg status`, `apg doctor` as wrappers around existing Stage 1/2 functionality. Shell completion, structured error output, `--json` mode."* A mandatory Block I session. | **`bin/apg.sh` has existed since Session 13 Run 5** (D707): *"one front door over the commands that already exist"*, a verb IS a script, no list of verbs anywhere (ADR 0002's rule at the CLI), `exec` so exit codes are the verb's own, and **deliberately not installed onto PATH** (ADR 0037's lesson). `apg doctor`, `apg connect`, `apg fleet` (the status the spec wants, per project and across the host), `apg upgrade check\|plan\|verify`, `apg deploy` all resolve today. `--json` is the norm across `bin/`. What is absent is small: a default project context (`--project KEY` is passed everywhere), shell completion, and *"a single binary"*, which the tree refuses for the reason ADR 0037 records. | **Not a session.** A project-context default and completion are one run inside Session 25, beside the documentation that describes them. The spec's third exit criterion — *"a teammate can complete the Stage 1 happy path using only `apg` commands"* — is `documented_path`, D1080. | Stage 2 priced this exactly (D707: *"renaming the surface is the expensive half and it buys nothing"*) and then built it. A session that rebuilt it as a binary would invalidate `SHELL_COMMANDS`, every `--session N` guard, eight operator documents and eighteen gates to arrive at the same verbs under one name they already have. | 0002, 0037, D707 |
| **D1066** | Session 27: *"`apg dev` should spin up an isolated, reset-in-seconds environment derived from a real project's current schema, using PostgreSQL 19's non-restart logical replication rather than a full restore-from-backup cycle."* Exit: *"available in seconds, not minutes"*; *"never touches the source project's active volume or backup chain."* | **The mechanism is wrong twice and the goal is already reachable.** There is no 19 (D1061); and nothing replicates — `wal_level` is the image's default `replica`, `compose.yaml` sets neither it nor `max_wal_senders`, and the database has no public port to replicate *from* (D1084). What exists: **(a)** a local throwaway cluster on the locked image applying all thirty migrations, as the contract suite's `cluster` fixture — **measured 2026-09-10, ~10 s wall on this workstation, twice**, against **247 s** for the restore from the mirror (D1028); **(b)** ephemeral projects on the *host* (project.lifecycle v3, ADR 0186; `project-retire.sh`, ADR 0187), which are full deployments — ten containers, ~350 MB anon (D959), root at a TTY, an Infisical bootstrap, minutes; **(c)** `restore-test.sh`, which restores a backup into a drill volume and never the live one (ADR 0151). And **(d)** nothing seeds one project from another's data, by decision (D950) and by the contract's non-goal on branching. The *"real project's current schema"* IS the release's migration set, because there is no tenant extension point (D1082) — until Session 20, a project's schema and the checkout's are the same thing. | **`apg dev` is the fixture path made a product** — `dev up\|reset\|down` over the locked image, the bootstrap roles, the release's migrations plus the project's own (D1082), a developer-written seed (D1071), **no production data, no backup credential, no network to the backup plane**. Session 22. Its churn number is measured there against the ~10 s baseline above, and the *"never touches the chain"* exit criterion is proved by construction: a workstation cluster holds no repository credential and no route to R2 (D1076). | The spec diagnosed the slow path as *restore-from-backup* and prescribed replication; the slow path was R2 with `process-max` 1 — ~1330 serialised round trips (D593) — which is a network property, not a size one. A local `initdb` plus thirty migrations never touches R2. **A `wal_level = logical` on production to serve development would also make the production cluster a replication source**, which is a security-model change this plan refuses to take for a developer convenience. | 0151, 0186, D593, D950 |
| **D1067** | Session 28: *"`apg migrate dev` applies a candidate migration against a shadow database, diffs the resulting schema against the target migration's intent, flags drift between the shadow and the real environment, and runs the existing safe-write linting."* Exit: *"the existing dbmate-based migration path remains the actual application mechanism."* | **The shadow half runs on every push.** `test_migrations_apply_as_the_migration_user.py` applies every released migration to a fresh cluster as `migration_user` — NOINHERIT, no SUPERUSER, reaching the owner only through `SET LOCAL ROLE` (ADR 0028) — and CI is the gate. **The drift readers exist**: `test_api_migrations.py` reads the templates against the reviewed contract (D1036 repaired its blind spot), `api-contract.sh --check` reads the snapshot against it (D1039 named the third clause), `migrate.sh status` reads the cluster, and D1053's `assert_installed_render_is_current` compares the checkout to the installed render. **The lint is the role**: `down` blocks raise `AP900`, the plane is fix-forward (D912). **What is absent**: a destructive-change lint over templates, and — the actual gap — *anywhere for a tenant's candidate migration to live* (D1082: `migrations.load_manifest()` reads one hardcoded path). | **Absorbed by Session 20** (the tenant migration set, and a lint over what such a set may contain: no `app_private`, no roles, no `DROP` of a platform object) **and Session 23** (`apg generate` as the post-migration step). No separate session: with the extension point built, *"apply a candidate against a shadow"* is `apg dev up` with the candidate in the project's set. | Told as four features it reads as a tool; told as *what is missing* it is one lint and one directory. D709's rule: spending a session on a property you get for free is paying for it. The intent-diff (*"against the target migration's intent"*) is the part with no reader anywhere, and it is not built: a migration's intent is its reviewed text, and the contract diff is the diff that has consequences (ADR 0050). | 0028, 0050, D1053 |
| **D1068** | Sessions 29, 30 and 38: a typed TypeScript client *"introspected from the `api` schema and the active capability bundle, versioned and contract-hash-verified"*; a Python client sharing the IR; *"semantic-versioning scheme tied to schema/capability-bundle contract hashes"*; *"typed error unions distinguishing validation, authorization, and denial failures"*; *"idempotency/retry helpers."* Three sessions. | **Every input is frozen, canonical and hashed already**: the PostgREST OpenAPI snapshot, the application OpenAPI snapshot (auth and storage merged, ADR 0087), the compiled MCP contract, and `openapi_normalize.declared_objects` that reads them. **The version scheme exists**: ADR 0162's change classes (`compatibility.py`, `upgrade_plan.py`, `REL-COMPAT-001`) already say which contract change is a patch, a minor or a major — a client's version is *derived* from them, not a second scheme. **The error distinctions exist**: `PT401`/`PT404`/`PT412` are SQLSTATEs the plane raises, a denial names its boundary (ADR 0178, an enum), a refusal arrives as `isError`, and idempotency keys are a header claimed in the write's own transaction (ADR 0181). **Nothing generates code.** `services/clients/` holds four *driver-compatibility fixtures* (psql, Prisma, node-pg, psycopg — `DBX-001..004`), not generated clients. And `product-contract.md` §5 lists *"general-purpose ORM support beyond the endpoint contract in DBX"* as a non-goal. **Unmeasured**: how a running client learns the *live* hash — no route serves `capability_contract_sha256` today; the deployed document is the address book, not the diagnosis (ADR 0158). | **One Session 23**: TypeScript first, from the three contracts and the project's lock; the hash embedded at generation and **checked against a served value, measured in the session's first run** (a document read is not an observation); versions derived from ADR 0162's classes; error unions from the enums that exist; Python is P1 and **evidence-selected inside the session** — built only if the TypeScript generator proves the IR carries. Session 38 is folded whole: its three items are the same generator read a second time. The non-goal is read as written — a client over *the reviewed `api` surface* is inside DBX's contract; a client that reached a base table or composed a query the contract does not name would be the thing it forbids. | Three sessions for one generator is Stage 1's shape borrowed: every session there built a plane. Here the IR is the contract snapshots, which are the most carefully frozen artefacts in the tree, and the generator is a *reader* of them. **The risk is not effort, it is authority**: a generated client is a second document about the surface, and the moment it is trusted over the served one it is D704's second axis. That is why the hash check must read the service. | 0087, 0158, 0162, 0178, 0181 |
| **D1069** | Sessions 31, 32 and 39: *"a local Studio (schema browser, RLS-safe query runner, audit/agent-activity viewer) launched per-project via the CLI"*; *"Studio holds no elevated credentials"*; a capability inspector and *"a one-click revocation action that calls the existing admin revocation endpoint"*; then a schema-diff and migration-history visualiser (P2). | **Nothing resembling a Studio exists** (`grep -i studio` finds one line: `connect.sh` refusing `prisma-studio` and naming `exec -- npx prisma studio` instead). `services/docs` is a Scalar API reference with a first-party CSP that loads nothing from the internet (ADR 0069, D202) — a schema *browser* over the two OpenAPI documents already served. **Every surface a Studio would client exists**: PostgREST as the human's JWT (RLS applies), `GET /admin/audit` (`admin_audit:read`), `/admin/agents` and the rotate/revoke endpoints (Session 15), `/auth/sessions`, `dev-token.sh` (root, never prints). **What "RLS-safe query runner" can mean here is fixed by the contract**: `product-contract.md` §5 refuses arbitrary SQL by an agent, `db.sh sql` executes only hash-verified generated files, and a human SQL runner in a browser would be a new authorization surface with no policy above it. A *query runner* is therefore a **PostgREST query builder** — filters, ordering, limits over the reviewed views — as the human's token. | **One Session 24**: a local web UI bound to loopback, holding nothing but the human's short-lived token, over the surfaces named; the schema browser reuses the served OpenAPI; the query runner is REST, never SQL; the audit viewer is `/admin/audit` unsummarised; revocation is the existing endpoint. **Session 39 is cut** (P2, and its diff engine is D1067's intent-diff, which is not built). Session 41's local-auth review is this session's negative tests. | Studio is the session most exposed to the failure the spec itself names in §1.4.7: *"codegen and Studio are new attack surface."* The cheapest way to keep it a client is to give it nothing a client does not have — and a SQL box is the one feature that would make it an authority. ADR 0140's lesson applies to a UI as much as to discovery: hiding a control is not a boundary. | 0069, 0087, 0140 |
| **D1070** | Session 33: *"`apg agent init` scaffolds a bundle that already satisfies the one-tool-to-one-operation pattern … `apg agent validate` checks the bundle against the live OpenAPI surface. `apg agent dry-run` … `apg agent test` runs the evaluation cases."* Exit: *"a scaffolded bundle cannot express arbitrary SQL, a generic dispatcher, or an unscoped write."* | **Three of the four verbs exist.** `validate` is `bin/mcp-contract.sh check`, and the adopter's F-025 measured that it catches a borrowed scope: *"the capability manifest no longer compiles to the approved contract … READ the difference."* `dry-run` is a runtime property (ADR 0182: the write is attempted and rolled back), reachable through `bin/api.sh`'s enumerated operations. `test` is `src/agentic_postgres/evaluation_harness.py` (ADR 0184, `EVAL-HARNESS-001`): cases derived from the contract per frozen field, hand-written ones bound to a capability version in `tests/evaluation-cases.yaml`. **`init` cannot exist yet**: a scaffolded bundle may name one of exactly six tools (`mcp_lock.EXPECTED_TOOL_NAMES`, D933) over one of five scopes (`$defs/agent_scope`: `notes:*`, `tasks:*`, `meta:read`, D1056), so the only bundle it could scaffold is one of the six that ship. | **`init` is Session 21's last run**, after that session opens the roster and the vocabulary (D1083). `validate`, `dry-run` and `test` get their `apg` names for free (D1065) and are not rebuilt. | The exit criterion is already true of the tree — a bundle *cannot* express SQL because the compiler cannot emit it — and the spec's session would have spent itself re-proving that. The real work is the one it does not name: making a bundle able to address an application's own tables at all (F-025: *"the single largest gap between what this product is and what someone adopting it would expect"*). | 0182, 0184, D933, D1056 |
| **D1071** | Session 34: *"`apg seed apply` / `apg seed capture` (capture a fixture from an existing project with anonymization rules) … a captured fixture from a real project never contains unmasked PII by default."* | **Nothing seeds, captures or masks.** D950 measured the copy path: there is none — `restore-test.py` restores into a drill volume and tears itself down, the contract's §5 non-goal covers branching and forks, and *"an ephemeral project starts as every project starts: an empty cluster, migrated."* A capture from production would need either the backup credential and cipher pass on a workstation or a read as a superuser over the socket, and both are credential paths the product refuses (ADR 0147's residual, `db.sh`'s design). | **`apply` is built in Session 22 as a reviewed fixture file** applied to a dev cluster through the migration user — SQL the developer wrote, hash-verified like `db.sh sql`, never a connection to a real project. **`capture` and anonymisation are not built**; they are a data-handling decision with its own threat model, and §6 records them for Stage 4's proposal system if ever. | D864's shape: a brief that says *"add X to Y"* where Y is a copy path, and there is no copy path. Masking is only ever as good as its rule set, and a rule set that misses one column ships production data to a laptop under the label *"safe by default"* — the product's characteristic defect (ADR 0195) as a data-protection failure. | D950, 0147 |
| **D1072** | Session 35: *"LSP-like validation server … VS Code extension surfacing inline diagnostics and autocomplete for capability-bundle fields."* Exit: *"flagged before the file is saved, using the same validation logic as `apg agent validate`."* | **`schemas/capabilities.schema.json` is a JSON Schema**, and every mainstream editor validates a YAML file against one through a `$schema` association or a `yaml.schemas` setting; the field vocabulary, enums and descriptions the extension would autocomplete are already in it. The semantic half — *does it compile to the approved contract* — is `mcp-contract.sh check` and cannot run on keystroke, because it reads the reviewed contract and the project profile. | **Not a session.** One documented line associating the schema, in Session 21's documentation beside `init`. No server, no extension. | A language server for a file that is validated by a schema the editor already reads is a second implementation of the schema (ADR 0002's rule for names, applied to a validator). The half that needs code cannot be inline by construction. | — |
| **D1073** | Session 37: *"a pull request gets its own ephemeral, seeded, migrated environment, exercised by the generated clients and agent evaluation suite, and torn down automatically on merge or close."* | **CI has no host and may not have one** (D952): transport is `git bundle` + `scp`, and *no GitHub credential exists on the VPS, by decision*. What CI already does on every push: render `fixture-alpha-dev` with `--render-only`, resolve its Compose model, create and delete `fixture-*` render-plane projects, stand up the local cluster (D1066) and apply every migration, run the evaluation harness. A CI-*deployed* environment on the one host would be the credential on the VPS this repository refuses. | **Not built, and recorded.** With Session 22, a PR's environment *is* `apg dev` inside CI — the cluster, the migrations, the generated client's tests, the harness — with no host, no route, no teardown to forget. A deployed preview per PR needs a host CI may reach, which is a security-model decision for Stage 4's hosted reading, not a session here. | The isolation the spec wants from a PR environment is exactly what a CI runner gives for free and a shared VPS cannot: nothing survives the job. D713's warning still holds — a TTL that expires into a real project's volume is a data-loss timer — and the cheapest way to never write that timer is to have nothing on the host to expire. | 0189, D952 |
| **D1074** | Session 41: *"Treat the CLI, codegen output, and local Studio as new attack surface … SBOM and dependency supply-chain audit … secrets-handling audit for generated client config … redaction review extended to any new logging surfaces."* | **The supply-chain half is the tree's standing shape**: eight images by immutable digest and every package by version-and-digest in `versions.env` (`lock-versions.sh --check` in the gate), `requirements-dev.txt` hash-locked, third-party actions pinned to SHAs, and `docs/threat-model.md`. The redaction contract and its canary exist (`mcp_telemetry.py`, Session 7's scan). What does not exist is the surface being reviewed, because 22–24 have not been built. | **Each building session ships its own negative tests** (the spec's §1.4.7: *"codegen and Studio are new attack surface and get their own negative tests, not an exemption from existing ones"*), and **Session 25 is the closing review** across the three: no generated artefact embeds a credential, Studio binds loopback only, every new logging surface passes the canary. Not a session of its own. | A review session at the end is where a defect is most expensive and where the fix lands on the proof's side (§7's question 4). Stage 2's Session 16 put its adversarial cases beside the code they test and the harness caught D868 that way. | 0184, D868 |
| **D1075** | Session 42: *"Re-run the full Stage 1/2 two-project isolation matrix against the PostgreSQL 19 baseline and every new Stage 3 surface."* | **`DEP-ISO-001` (`isolation_matrix`) has passed on every host gate since Session 12's trip** — 179 leaves in Session 12, extended by every session that added a deployed-document field, and D1029 found the four unclassified mirror leaves at Session 18's trip precisely because the matrix runs every time. There is no 19 to re-run it against (D1061). | **Not a session.** Every deployed-document field Stage 3 adds — a project migration digest (20), a derived scope vocabulary (21), a generated-client hash (23) — owes the matrix a classification in the session that adds it (D702, D1029), and the trip's gate proves it. | Stage 2's §8 said it: *"every session that adds a deployed-document field owes that field a classification"*, and D1029 is what happened once when one did not. A dedicated re-run session would run a gate that already runs. | D702, D1029 |
| **D1076** | Session 43: *"Re-validate the Stage 1 PITR/restore drill and the Stage 2 independent-account restore against PostgreSQL 19 … confirm that ephemeral `apg dev`/preview environment churn never touches or degrades a real project's backup chain."* | **The drills run every trip**: `restore-test.sh` (`REC-PITR-*`, ADR 0151), `restore.sh --from mirror` (ADR 0192, proved on a replacement in 247 s), `rehearse.sh` over eight scenarios (ADR 0190/0193), `backup.sh` and the mirror's own doctor check. No 19. And **an `apg dev` cluster on a workstation holds no repository credential, no cipher pass, and has no route to the backup network** — the backup plane is a project-scoped egress network on the host that only the database container joins (ADR 0147). | **Not a session.** Session 22 proves the churn claim by construction — one test that the dev environment's container has no backup network, no `pgbackrest.conf` mount and no facility-gated secret (ADR 0191's `active_secrets(..., facilities=)` answers it) — and the trips keep running the drills. | A claim that a thing *cannot* reach the chain is stronger than a claim that it *did not* in one measurement, and cheaper: the isolation is a property of where the cluster runs, not of how carefully it was used. | 0147, 0151, 0191 |
| **D1077** | Session 44: *"Prove that a Stage-1/2-vintage project can be upgraded to the PostgreSQL 19 baseline and Stage 3 tooling without data loss, with an upgrade plan produced before anything is mutated."* | **`bin/upgrade.sh check\|plan\|verify` has existed since Session 13** (ADR 0162): every verb reads, none mutates, `check` reports an unreadable installed document as *undetermined* rather than *no changes* (ADR 0195's rule before ADR 0195), and the deploy performs what the plan priced. **Both production manifests are schema v1 and both render and deploy under a schema-4 release** (D930): every trip since Session 13 has been a vintage-project upgrade. No 19. | **Not a session.** Session 20's deploy sitting is the first Stage 3 upgrade and its `upgrade plan` output is recorded in that session's plan; the *"rollback and fix-forward are distinct operations"* half is ADR 0162's text already. | The rehearsal the spec asks for is the trip this repository makes at every session's close. Making it a session of its own would spend a host trip to observe what the next host trip observes anyway. | 0162, D930 |
| **D1078** | Session 45: *"Generated docs (API reference, capability-bundle reference) are produced from live schema and capability bundles with a CI check for drift; the quickstart is rewritten around `apg` end to end."* | **Generated documents with drift checks in the gate exist**: `render-acceptance-matrix.py --check`, `render-config.py --bounds-doc --check`, `render-mcp-catalog.py --check` (the capability-bundle reference, from the compiled contract), `render-evaluation-report.py`, `render-capacity-envelope.py --check`; the two OpenAPI references are served live by `services/docs` and their snapshots are what `api-contract.sh --check` and `app-contract.sh --check` compare. The quickstart is `README.md` — *Rendering*, *Deploying*, *Adding your own tables* (Session 19 Run 7) — and `docs/new-team-member.md`; the check that its commands resolve is `DX-001`'s offline half (D693). | **Folded into Session 25**, where the documents describing 20–24 are converged and the outsider walks them (D1080). A generated reference for the *tenant's* surface arrives with Session 20 (the catalog and the API surface rendered from the project's contract rather than the example's). | Rewriting the quickstart *around `apg`* before `apg` has verbs it does not have today is rewriting it twice. The one document that matters is the one the outsider follows, and its test is the walk. | D693 |
| **D1079** | Session 46: *"Capture capacity evidence for the new DX surfaces — `apg dev` environment churn rate, codegen pipeline latency, Studio responsiveness … A published capacity envelope exists for ephemeral environment churn and codegen latency."* | **`docs/capacity-envelope.md` exists** (`CAP-ENV-001`, Session 14, rendered by `render-capacity-envelope.py --write` and pinned to three image digests so a moved image reddens it). Every number in it carries the conditions it was sampled under and says whether it transfers (D593, D603). It has no rows for surfaces that do not exist. | **Not a session.** Each building session adds its rows in the run that measures them — 22's churn against the ~10 s baseline (D1066), 23's generation time per contract size, 24's first paint against the fixture project — under the standing rule: a sample from a band, with its conditions, transferring or not. | An envelope session that measures three things built in three earlier sessions is those sessions' last runs moved to a later date, where the machine and the images have moved on. Stage 2's Session 14 measured beside the instrumentation for the same reason. | D593, D603 |
| **D1080** | Session 47: *"handing the CLI and documentation to a teammate who did not build Stage 3. Using only `apg` and the generated docs, they should complete the full Section 1.3 success criterion and record every place undocumented knowledge or a source-file edit was required."* Exit: *"the recorded list … is empty, or every remaining item is explicitly triaged."* | **This is `DX-001` and `documented_path`, verbatim, and it has now been walked once and failed on its stated condition** (ADR 0197): the path needed seven tracked-file edits, two of which Session 19 removed and five of which are one design question — the tenant extension point (D1082). The spec's exit criterion is the requirement's text. The agent-versus-person question (the walker was an AI agent) is deliberately open and does not need answering while the condition fails on its own terms. | **A declaration, arranged in Session 25** — the second walk, by somebody who did not build Session 20, with no source edits — and **Session 20's exit criterion**, because 20 is the session that removes the five edits. Not a session of its own (D716's shape, with a stronger starting point: the list of edits is known). | Stage 2 said an outsider's afternoon was the cheapest measurement the product had never taken; Session 19 got the afternoon and it found the structural fact every other row here turns on. The second afternoon is the proof that Stage 3 did what it was for. | 0197, D716 |
| **D1081** | Session 48: *"resolve all P0 gaps, explicitly list remaining P1/P2 gaps with effort estimates, confirm every Block II item's disposition … decide whether audience/deployment-model assumptions still hold … explicit recommendation on whether Stage 4 is justified."* | **This is Session 18 Run 5's shape**, executed once already: the bump (`CURRENT_SESSION`, `VERSION`, the compatibility sentence), the requirements and claims, `session-NN-check.sh` derived by diff, `scope-closure.md` re-audited, and `stage-3-decision-report.md` written from the evidence document rather than before it. The version question is ADR 0162's, not a choice: `upgrade plan` prices each session's change, and a major is what it says when a change removes or retypes a manifest field, a migration, a contract entry, a capability or a secret, or requires an operator to act first. | **Session 25 closes Stage 3 that way**, and adds the one thing Session 18's report could not: a Stage 4 recommendation that names which of the three blockers Stage 3 removed and what the third costs (§6). **`template_version` moves one minor per session unless a session's own `upgrade plan` prices it at major** — the two candidates are Session 20's migration-manifest shape and Session 21's capability schema — and the number is read from the plan, never chosen. | Stage 2 fixed *"1.0.0 at Session 18"* in advance and it held; Stage 3 has two sessions that retype a document an operator's manifest points at, and fixing *"2.0"* or *"1.6"* in advance would be a second answer to what `upgrade plan` is for (D704). | 0162, D704, D991 |
| **D1082** | Blocker 1, everywhere the spec says *"a real project's schema"* (27), *"the target environment"* (28), *"the `api` schema"* (29), *"any Stage 3 project without project-specific source changes"* (31). The spec assumes a project has a schema of its own. | **There is no tenant extension point, measured from four sides.** `migrations.load_manifest(path: Path = MANIFEST_PATH)` reads one hardcoded path, so an application's tables are migration templates in the product's own repository behind the product's own lock (F-002's *"wider point"*). `test_the_reader_is_not_vacuous` hardcodes `{"notes", "tasks"}` as the whole published surface, deliberately, so an adopter edits a test (D1038). The *"project-neutral"* contract's control fixture is one project's raw capture from `alpha.example.test` (D1054). And the snapshot is captured from a *deployed* document, so an adopter's first bring-up runs with a red gate by construction (D1039). Seven tracked files to add one table; ADR 0197 counts them. **The contract's identifier is `notes-tasks-v1`**: the reviewed surface is named after the example. | **Session 20, first, before anything is generated, browsed or scaffolded for a surface.** A project's own migration set beside the release's, declared in its manifest and frozen under its own lock; the anti-vacuity guard proving the reader found *the platform's* objects rather than *exactly the example's* (F-006's shape, taken as a decision rather than a weakening — the property kept, the coupling dropped); the control fixture **generated from the reviewed contract** rather than captured from a deployment (D1054); the snapshot's ordering made a command with the stale-snapshot clause D1039 added; ADR 0196's `create_task` migration in the same deploy sitting; D1060 and D1048 while the outputs document is versioned anyway. Its exit criterion is D1080's second walk needing no source edit. | Every other row in Block I stands on this one, and it gets more expensive the later it is taken: each of 22, 23 and 24 would otherwise be built for the example domain and rebuilt for a tenant's. **It is also the only row whose consequence is a claim the product already makes and cannot keep** — `documented_path` — which makes it the one piece of Stage 3 work that repairs a promise rather than adding a feature. | 0050, 0196, 0197; the ADR this needs is 0198's subject |
| **D1083** | Blocker 2, Session 33's premise and Session 40's: *"exposed the same way every other agent capability is: as a curated, scoped, auditable tool"* over a tenant's domain. | **The agent plane is closed to a tenant's domain twice over, and both closures are working as designed** (F-025, D1056). `mcp_tools.py`: *"The six tools, and there are exactly six"*; `mcp_lock.EXPECTED_TOOL_NAMES` refuses any other roster at startup, so a manifest that disables one write capability compiles a five-tool lock the runtime refuses — **D933**, measured with a control in Session 16 and still open. `$defs/agent_scope` is an enum of five names, closed *"by ADR 0003 and growing only when that is superseded"*; the honest scope `snippets:read` is refused at schema validation, and the borrowed `notes:read` compiles to a contract the approved one does not match. **And two of the six tools address a table nothing can populate** (ADR 0196): `api.create_task` was dropped by `0007` and never replaced, so `tasks` has held zero rows on every deployment; the reviewed replacement is specified and unwritten because it needs a deploy sitting. | **Session 21, after 20.** The scope vocabulary derived from the reviewed contract's resources rather than enumerated in the schema (superseding ADR 0003's closure, keeping ADR 0006's refusal of pattern-validated names: still three closed classes, the data class now *generated* from the contract, never admitting an administrative or storage scope); the runtime's roster read from the lock, so a project may serve fewer than six and a tenant more (closing D933 for both things it blocks); capability schema 4; then `apg agent init` from a selected reviewed operation. ADR 0196's migration lands in **20's** sitting so 21 starts with a task domain that can hold a row. | The agent plane is the product's differentiator and today it cannot address the application it was deployed to serve. D1056 wrote that down as a decision; this is where it stops being one. The order matters: a vocabulary derived from a contract needs the contract to be the tenant's first (20), and a roster read from the lock needs a lock that is not the six (21). | 0003, 0006, 0127, 0183, 0196; ADR needed |
| **D1084** | Blocker 3. The Stage 3 spec: *"Deployment model: unchanged from Stage 1/2 — one project per isolated deployment, single VPS."* Stage 4 §6.3: `apg` as *"an authenticated remote client"*; Stage 5 §11: *"Pooled connection … Direct connection"* URLs as product objects. | **There is no public Postgres endpoint, by three decisions.** ADR 0042: ports are host-loopback allocations keyed by the volume's identity; ADR 0044: *"there is no publication"* — `runtime_override.publication()` **raises** rather than building a `ports:` entry, because a container on an `internal: true` network gets no DNAT rule and no listener; ADR 0043: a developer reaches a transport over an SSH local forward with the authorization decision on the host, in the release that deployed the project. `compose.yaml` has no `ports:` anywhere. Every hosted reading of Stage 4 and Stage 5 requires reversing this, and the reversal is a security-model change: TLS on the wire, a listener on a public address, a credential that travels, an abuse surface the threat model has never had to consider. | **Stage 3 keeps it, deliberately** — the spec's own header says the deployment model is unchanged, and every Stage 3 surface reaches a database the way `connect.sh` does or runs one locally (D1066). **§6 names it as the blocker Stage 3 leaves for Stage 4**, with the seam (`publication()` is kept as a refusal *"because the signature is what a future reader reaches for"*) and the precondition: Stage 4's threat model before any port. | Reversing it inside a DX stage would take the most consequential security decision of the roadmap as a side effect of a convenience, in a stage whose audience is still internal. Each of the other two blockers gets cheaper by being taken early; this one gets *safer* by being taken after the threat model that Stage 4 §17 says is *"a first-class Stage 4 feature, not a final-session checklist."* | 0042, 0043, 0044 |
| **D1085** | §2.1: three blocks, *"Block I — Core DX platform, 25–33, not cuttable"*, *"Block II — Included depth, 34–40 … included now rather than deferred"*, *"Block III — Hardening & release, 41–48"*. §2.2: seven P0 capabilities, the first *"PostgreSQL 19 validated as the baseline."* | **The block structure describes twenty-four sessions of which this table finds nine already built or already running as gates** (26, 28's shadow and drift, 33's three verbs, 41's locks, 42, 43, 44, 45's generators, 46's envelope), **three cut with 19** (25, 36, 40), **three that are declarations or refusals** (35, 37, 47), and **two that were wrong about their mechanism** (27, 34). The remaining scope collapses onto three blockers (D1082–D1084) and three deliverables (a dev environment, a generator, a Studio). | **Recorded. §3 is what is left after subtracting what is built**, and its count was arrived at from the rows and then found to agree with the spec's own scope-protection clause: the P0 list less its first item is six items, and six is the count. | The spec's *"Block II committed up front per your direction rather than deferred to a menu"* is the one place it departs from Stage 2's evidence discipline, and the departure cost nothing here because Block II's members were each either wrong about the tree (34, 37, 39, 40) or free (35, 38). | D717 |
| **D1086** | Housekeeping, found by this audit rather than looked for. `README.md` §*What is intentionally unavailable*: *"Removing a project is not built, and it is the one Session 12 claim still open … its proof is written and gated on a project actually removed, which has not happened."* `docs/scope-closure.md` §2: *"`DEP-REMOVE-001` awaits a project actually removed."* | **`project_removal` passed on 2026-09-05** — gamma-dev, ephemeral, created 09-04, retired with `--record` through `bin/project-retire.sh` (ADR 0187), and the claim is `passed` in `evidence/session-17.json` and `session-18.json`; it is not among the eight `not_run`. The README paragraph and the ledger's §2 entry both describe finished work as unfinished. D954 recorded exactly this shape for the same claim once already, in the other direction's sibling `isolation_matrix`. | **Corrected in Session 20's first documentation commit**: the README paragraph names what is actually unavailable, and ledger §2 gets the D860 treatment for the removal claim. | The direction nobody chases (D954: *"finished work described as unfinished"*), for the second time on the same entry. It is also the cheapest instance of the standing question — has anything looked at this since it changed? — and the answer was no for five days and one release. | D954 |

---

## 2. The four decisions CLAUDE.md §4 requires

A new body of work cannot begin until these are settled. They are settled here.

### 2.1 What is the new body of work for?

**The template, given a tenant's domain and made usable daily. Still not a
control plane.**

The decision report (§5) answered the question the ledger's §6 recorded and
Stage 2 deferred: ship 1.0.0 as the template the evidence shows it to be, and
put the control-plane question to a Stage 3 specification starting from
corrected premises. The Stage 3 specification agrees with the first half —
*"unchanged from Stage 1/2 — one project per isolated deployment, single VPS,
no multi-tenant hosting"* — and this plan adopts it whole: **Stage 3 is a
developer-experience layer that is a client of the surfaces that exist.**

But the specification's audience sentence — *"internal / small-team use only"*
— hides what Session 19 measured: the product's surface is its *example*
domain. An application built on it gets a REST surface and a storage surface
for its own tables and no agent surface at all, and adding one table means a
fork (D1082, D1083). **So the body of work is for the adopter**, the person who
walked the path and recorded twenty-five findings, and the first two sessions
are for them before any session is for the daily loop.

**What survives either reading of Stage 4** — hosted or not — is that the
DX layer must hold nothing the human does not hold. Under the hosted reading
that matters *more*: a Studio that became an authority on a workstation would
become one on a shared host.

**The decision this stage plan does not take, and flags rather than hides**:
whether a public Postgres endpoint exists is Stage 4's first ADR (D1084), and
§9 makes wanting one inside Stage 3 a stop condition.

### 2.2 Does `CURRENT_SESSION` move, and to what?

**Yes, six times: 18 → 20 → 21 → 22 → 23 → 24 → 25.** Session 19 is skipped
(D1063) and nothing is renumbered.

Moving it stays **all-or-nothing** (D690), and there are no `future`
placeholders left, so every Stage 3 session's requirements arrive with their
proofs in the commit that moves the constant. That is why a session's registry
additions are decided before its first run (§11).

**`template_version` moves with it, one minor per session — unless a session's
own `upgrade plan` prices its change at major** (D1081). Two sessions could:
Session 20 declares a project's migration set in its manifest and freezes it
under a lock (an added field with a default is a minor; a retyped manifest
shape is not), and Session 21 bumps the capability schema to 4 with a derived
vocabulary (a migrator keeps it a minor; a manifest an operator must edit does
not). **The number is read from the plan's output at the session's close and
never chosen in advance.** If either prices at major, that session's release
is `2.0.0` and the ones after it are `2.x`; if neither does, Stage 3 closes at
`1.6.0`. There is no second version axis (D704).

### 2.3 Which open items are actually open?

Ledger §8 and CLAUDE.md §9, re-read against the tree at `a0d853f`:

| Item | Verdict |
|---|---|
| **D1045 — the provider's error body is discarded** | **Open, and the owner's.** A security judgement in a credential path, classifier-blocked when attempted. Not assigned to a session; §10. |
| **ADR 0196's migration — a reviewed `api.create_task`** | **Open. Session 20's deploy sitting**, because that sitting recaptures the snapshot anyway (D1082). |
| **D1060 — a deployed project reported as never deployed** | **Open. Session 20**, ADR 0195's shape (unreadable is not absent), landing in the first release after the tag as the row says. |
| **D1038, D1054 — the example domain as the suite's surface, and the captured control** | **Open. Session 20 is the ADR they were waiting for** (D1082). |
| **D1048's document half — `unavailable` for unobserved** | **Open. The session that next versions the outputs document, expected to be 20** (a project migration digest is a new field). If 20 does not version it, 23 does (a generated-client hash), and D1048 moves with it. |
| **D933 and D1056 — the five-tool lock and the closed vocabulary** | **Open. Session 21** (D1083). |
| **D1058 — `0003`'s comment false since `0006`** | **Open by construction**; fix-forward, and Session 20's new migrations carry the correct comment. |
| **D1059 — a cancelled CI run is not a failed one** | **Open in the watcher, closed in the handoff**; §11 carries the three buckets. |
| **`bootstrap_identity`, `api_authorization`, `credential_rotation_planes` need a rotation PERFORMED** | **Open and untouched by Stage 3.** An operator sequence with an irreversible `promote` (D860). Session 24's Studio makes a fourth verifier of the key set (§10), which is a reason to perform the rotation *before* 24 rather than after. |
| **`deployment_convergence`, `port_allocation`** | **Open**, a redeploy window declared and a witness of an allocation on a fresh host; the second is the operator's when `fresh_host` is supplied. |
| **`replacement_host_restore`** | **Open by decision** (D1028); Stage 3 does not build the adoption change it would need. |
| **The IPv6 scan has nothing to scan** | **Open, not Stage 3's** (D688). |
| **`process-max` is 1** | **Open by decision, and now the reason D1066's mechanism is local rather than a restore.** |
| **The agent audit and idempotency tables grow without bound** | **Open.** Session 24's viewer reads the audit table and inherits the question; §10 names the retention decision as one 24 must state even if it does not take it. |
| **`lock-versions.sh --update` re-adopts rolling tags** (D540) | **Open**; Stage 3 does not fix it. |
| **`apg-diag` cannot read `auth`, `storage` or `mcp` logs** (D380) | **Open**; §10. |
| **Nothing knows which proofs have never executed** | **Open, narrower after Session 19** (five instances guarded; a battery finds a vacuous guard cheaply). Every Stage 3 proof pairs a control (D499) and asserts how it failed (D386). |

### 2.4 Are the unproved claims in scope?

**Two are, and neither needs a session** (§4). `fresh_host` needs a file the
operator has. `documented_path` needs Session 20 and then an afternoon, and it
is Session 25's exit criterion. The other six stay where §2.3 puts them.

---

## 3. Release structure — six sessions, not twenty-four

| Stage 3 session | Absorbs spec sessions | Shape |
|---|---|---|
| **20 — The tenant extension point** | 28 (the tenant set, the lint), 47's cause, plus ADR 0196's migration, D1060, D1048, D1086 | A project's own migration set beside the release's under its own lock; the anti-vacuity guard and the contract's control decoupled from the example domain; the snapshot's ordering made a command; outputs v17; **ends in a deploy sitting** and a second bring-up needing no source edit |
| **21 — The agent plane opened to a tenant's domain** | 33, 35 (a line), 40's substrate premise; closes D933 and D1056 | The scope vocabulary derived from the reviewed contract; the roster read from the lock; capability schema 4; `apg agent init`; live proofs on a host |
| **22 — `apg dev`, the local disposable environment** | 27, 34's `apply`, 43's churn proof, 46's churn numbers, 37's answer | The fixture path as a product: `dev up\|reset\|down`, a reviewed seed file, measured churn against the ~10 s baseline, no credential, no route to the backup plane |
| **23 — Generated typed clients** | 29, 30, 38, 28's `generate` hook, 46's codegen numbers | TypeScript from the three frozen contracts and the project's lock; the hash embedded and checked against a served value; versions derived from ADR 0162's classes; Python evidence-selected |
| **24 — Studio** | 31, 32, 41's local-auth half, 46's Studio numbers | A loopback client: schema browser over the served OpenAPI, a PostgREST query builder as the human, the audit and agent viewer over `/admin/audit`, revocation via the existing endpoint; negative tests |
| **25 — Hardening, the second walk, and the Stage 3 release** | 26, 41, 45, 47, 48 | The closing review of the three new surfaces; documentation converged; `documented_path` walked by an outsider with no source edit; the bump; the decision report with the Stage 4 recommendation |
| *(cut, by the operator's decision)* | 25, 36, 40 | PostgreSQL 19 and the three sessions that stand on it (D1061) |
| *(not built, and recorded)* | 34's capture, 37, 39 | §4 and §6 |

**Two orderings are forced and the rest is preference.**

1. **20 before everything.** The surface has to be a tenant's before anything is
   generated for it, browsed in it, or scaffolded against it. Every one of 21–24
   built before 20 would be built for `notes` and `tasks` and rebuilt.
2. **21 before 23's tool wrappers and 24's agent viewer, and 25 last.** A
   generated client that wraps six tools over five scopes is a client of the
   example domain; a Studio that inspects a closed vocabulary shows an adopter
   the thing they cannot change.

**21 and 22 are independent of each other** and could swap. 21 is placed first
because it is the larger security decision and because 23 needs it. **22 and 23
could also swap**; 22 first because 23's tests want a dev cluster to run
against, which is the same dependency CI has today.

**The count, honestly:** the specification's twenty-four is Stage 1's shape
borrowed a second time, through a Stage 2 that borrowed it once. Nine of its
sessions are built or are gates that already run, three are cut with a
database version that is not released, three are declarations or refusals, and
two prescribed a mechanism the tree cannot host. What is left is three
structural blockers — of which Stage 3 takes two — and three deliverables. Six
is not a schedule concession; it is what is left after subtracting what is
built, and it is also what the specification's own P0 list says once its first
item is removed.

---

## 4. What is not a session

Stage 2 found two of its "sessions" were declarations to be arranged. Stage 3
finds five things the specification prices as sessions and this tree prices as
a file, a line, a refusal, or a gate that already runs.

| Spec session | What it is here | Arranged where |
|---|---|---|
| **47** — fresh-teammate rehearsal | `documented_path`'s second walk (D1080) | Session 25, as its exit criterion; needs Session 20 first |
| **`fresh_host`** (inside 26 and 47) | A file the operator has (ADR 0197) | The first Stage 3 gate that is handed `APG_FRESH_HOST_OUTPUTS` |
| **35** — IDE validation | A `$schema` association line (D1072) | Session 21's documentation |
| **37** — CI preview environments | A refusal with a reason (D1073): no host for CI, by decision | §6; `apg dev` inside CI is what a PR gets |
| **42, 43, 44** — matrix, drills, upgrade rehearsal | The gates every trip runs (D1075–D1077) | Every session that ends on a host: 20, 21, 24, 25 |
| **46** — capacity evidence | Rows in the envelope that exists (D1079) | The run that builds each surface |

**An offline half may not stand in for a declaration**, and the rule that fixed
that before any of these were written still holds. The second walk in
particular must be by somebody who did not build Session 20, and the record of
it must show zero source edits — not a shorter list.

**A caution about `documented_path` and Session 20.** They are the same shape —
an adopter adding a table — and it is tempting to let 20's own bring-up close
the claim. **Do not.** Session 20's author knows where the seven edits were;
the claim asks whether somebody who does not can avoid them. A session that
closes another's claim with its own hands leaves the next reader unable to tell
a proved guarantee from a plausible one (D478).

---

## 5. The six sessions

Each gets its own plan. What follows is the sentence each plan starts from,
what it must not do, what it measures, and where its exit criteria come from.
**Requirement id families are proposed, not fixed** — each session's own §2
settles its ids, because registering one is a decision about what a
requirement *means* (D691).

### Session 20 — The tenant extension point

**Builds.** A project-owned migration set: declared in the project manifest
(schema 5), living outside the release's `migrations/templates/` — on the host
beside the manifest, where D971 already puts a third project's manifest —
rendered through the same `{{name}}` substitution, frozen under the project's
own lock, applied after the release's set by the same dbmate plane as the same
`migration_user`, and digested into the deployed document (outputs v17). A lint
over what such a set may contain: nothing in `app_private`, no role, no grant
the release did not delegate, no `DROP` of a platform object, `down` raising
`AP900` like the release's. The anti-vacuity guard rewritten as *the reader
found the platform's objects and the sets are non-empty* (F-006, D1038), with a
control proving an empty scrape still fails. The contract's control fixture
**generated from the reviewed contract** (D1054) so it cannot drift. The
snapshot's capture-after-deploy made one printed command with the three-clause
message D1039 wrote. ADR 0196's `api.create_task` migration, exactly as that
ADR specifies it, in this session's deploy sitting. D1060 (unreadable is not
absent, in `migrate.sh render`) and D1048's document half (a third
`routes.*.status` member with a migrator and a guarded reader for every
consumer, D600) while the outputs document is versioned. D1086's two
paragraphs. **The session ends on a host**: a deploy on alpha or beta with the
task migration, the snapshot recaptured, `upgrade plan`'s output recorded, and
then — separately, by somebody else — the second walk.

**Already true, so do not rebuild it.** The migration plane (dbmate as
`migration_user`, the manifest, the lock, `verify-lock`, `render`, `status`,
`up`, D1053's installed-render check). The reviewed contract's own rule that a
new object needs a reviewed change there. README's *Adding your own tables*,
which is the list this session shortens to zero.

**Must not.** Let a tenant migration reach `app_private`, `extensions`' owner,
a role, or the pre-request hook — the lint is the boundary and RLS with
`FORCE` stays the authority. Amend an applied migration (D912): the task
migration is `0031`, fix-forward. Loosen the anti-vacuity guard to *anything
non-empty*: it must still name the platform's objects. Capture the control
fixture from a deployment. Introduce a second lock *format* — the project's
lock is the release's lock's shape with a different root. Close
`documented_path` with the author's own walk (§4).

**Measures.** In a rig with a control before building: a second migration
directory applied by dbmate after the first, with `--migrations-table` shared
or separate (decide from the measurement, D57's family — grep the plans for
dbmate first); a tenant view added with `OR REPLACE` seen by the repaired
reader (D1036's control); `api.create_task` under `authenticated` and
`agent_writer` with `PT401`/`PT404` measured, and `app_runtime` refused (rig 19's
probes as the control). On the host: `upgrade plan`'s price for the manifest
change (D1081).

**Closes.** D1038, D1039's structural half, D1040, D1054, D1055 (the migration),
D1060, D1048, D1086; the cause of `documented_path`.

**Proposed family.** `TEN-*`.

### Session 21 — The agent plane opened to a tenant's domain

**Builds.** The scope vocabulary derived: `$defs/agent_scope` generated from
the reviewed contract's resources (one `<resource>:read` / `<resource>:write`
per published relation, plus `meta:read`), superseding ADR 0003's closure while
keeping ADR 0006's refusal — three closed classes, the data class generated and
never able to name an administrative or storage scope, and
`assert_classes_partition_the_vocabulary` still the guard. The roster read
from the lock: `EXPECTED_TOOL_NAMES` replaced by the lock's own tool list,
`mcp_lock` refusing a lock whose tools disagree with the contract it was
compiled from rather than one that is not six (D933, for both things it
blocks). Capability schema 4 with a migrator. `list_resources` and
`describe_resource` answering for the tenant's resources from the lock (ADR
0127 unchanged). Then `apg agent init`: a bundle scaffolded from one selected
reviewed operation, which cannot express what the compiler cannot emit. A
`$schema` line in the documentation (D1072). **Ends on a host**: the lock
recompiled per project, ADR 0140's hidden-tool proof re-run against a roster
that is no longer six, and the round trip against `create_task` measured for
the first time on a row that exists.

**Already true, so do not rebuild it.** `mcp-contract.sh compile|check`
(validate), the dry-run (ADR 0182), the evaluation harness (ADR 0184, with
cases derived per frozen field — a derived vocabulary needs derived cases, and
the harness already derives), the five budgets, the denial taxonomy, the
profile that only narrows (ADR 0183).

**Must not.** Add an `execute_sql`, a generic dispatcher, a schema-management
tool, or any input that accepts a query, a column list or a path (D486, ADR
0127). Let a derived scope name a base table or a schema — resources are the
contract's published relations and functions, nothing else. Let a profile
*widen* (ADR 0183). Relay an upstream status (D433). Hand the runtime a
credential. Let the harness's expected denials be written from the
implementation (D868).

**Measures.** In a rig with a control: a five-tool lock accepted after the
change and a lock naming a tool the contract does not compile refused (D933's
measurement inverted, with the original as the control); the honest scope
`snippets:read` accepted at schema validation and compiled, the borrowed
`notes:read` over a snippets capability *still* refused by `mcp-contract.sh
check` (F-025's two runs as controls); `admin_users:read` in a capability
manifest refused. On the host: `describe_resource` for a tenant relation,
`update_task_status` against a row `create_task` made.

**Closes.** D933, D1056, and the second thing ADR 0196 said D933 blocked.

**Proposed families.** `AGT-*` extended, `EVAL-*` extended.

### Session 22 — `apg dev`, the local disposable environment

**Builds.** `apg dev up | reset | down`: the locked image by digest, the
bootstrap plane's `build_statements()` (F-005: never a second implementation of
the bootstrap), the release's migrations and the project's set (20) applied by
the migration user, a short-lived local JWT signed by a throwaway key that
exists only for the environment, and the developer's own PostgREST and auth
service if the loop needs them — measured first whether it does. `apg dev
seed FILE`: a reviewed fixture file, hash-verified like `db.sh sql`, applied
through the migration user (D1071). Churn measured and published in the
envelope (D1079) against the ~10 s baseline (D1066). One proof that the
environment's container joins no backup network, mounts no `pgbackrest.conf`
and holds no facility-gated secret (D1076). CI runs it, which is what a PR
environment is here (D1073).

**Already true, so do not rebuild it.** The contract fixtures' cluster path,
`--render-only` with no host and no root, `build_statements()`, the rendered
migrations, `dev-token.sh`'s rule that nothing prints a token.

**Must not.** Hold a repository credential, a cipher pass, a provider token or
any production secret on a workstation. Reach a real project's database: `apg
dev` derives from the *release and the manifest*, never from a host. Set
`wal_level = logical` anywhere. Seed from a capture (D1071). Publish a port on a
non-loopback address. Call it a branch: the contract's non-goal stands, and a
dev environment has no parent, no promotion and no durability.

**Measures.** In a rig with a control: wall time for `up` and for `reset` on
this workstation and in CI, twice, image cached and not; the environment's
Compose model resolved with `docker network` listing no `backup` network
(control: a rendered project's model, which has one).

**Closes.** The spec's Session 27 exit criteria on the mechanism the tree can
host; 43's churn claim; 46's churn row.

**Proposed family.** `DEV-*`.

### Session 23 — Generated typed clients

**Builds.** A TypeScript client generated from the PostgREST snapshot, the
application snapshot and the project's compiled MCP contract: typed reads and
writes over the reviewed views and RPCs, tool-call wrappers over the lock's
roster (21), error unions from the SQLSTATEs and the boundary enum, an
idempotency-key helper that sets the header ADR 0181 claims. The generation
hash — the three contract digests and the lock's — embedded, and **checked at
init against a served value**: which value, and which route serves it, is the
session's first measurement (a candidate is the docs route's served OpenAPI
digest plus `list_resources`' lock digest; the deployed document is not the
answer, ADR 0158). Versions derived from ADR 0162's change classes over the
contract diff — never a second scheme. `apg generate`, and its hook after a
project migration (D1067). Python **evidence-selected inside the session**:
built only if the TypeScript generator proves the IR carries without a second
reader of the contracts. Generation time per contract size in the envelope.

**Already true, so do not rebuild it.** The three frozen contracts and their
`--check`s, `openapi_normalize`, `compatibility.py`'s classes, the four driver
fixtures (which stay: they prove drivers, not clients), `PT412` and the
idempotency header, the denial enum.

**Must not.** Embed a credential, a URL with a token, or a long-lived key in a
generated artefact (Session 41's exit criterion, taken here). Generate a call
the contract does not name — a base table, a column outside the allowlist, a
filter operator outside the set. Trust the deployed document over the served
surface for the hash. Become a second authority on the surface: a client that
disagrees with the served OpenAPI is stale, never right (D704's second axis, at
the client). Widen DBX's non-goal: the client is over the endpoint contract,
and an ORM is not.

**Measures.** A stale client against a changed contract failing closed at init
with a clear error (control: the same client against its own contract
succeeding); a generated write with a replayed idempotency key refused with
`PT412` through the client (F-023's measurement, repeated through generated
code); the version derivation agreeing with `upgrade plan`'s class for the
same diff.

**Closes.** Spec sessions 29, 30 and 38; 28's `generate` hook; 46's codegen
row.

**Proposed family.** `GEN-*`.

### Session 24 — Studio

**Builds.** `apg studio`: a local web UI bound to `127.0.0.1` only, launched
with the human's own short-lived token (from `/auth/login`, never minted by
`dev-token.sh` — that is root's) and holding nothing else. A schema browser
over the served OpenAPI (the docs route already renders it; Studio reuses the
documents, not the bundle). A query builder over PostgREST as the human — the
reviewed views, filters, ordering, limits — **and no SQL surface of any kind**
(D1069). An audit and agent-activity viewer over `GET /admin/audit`, unfiltered
by default and filterable by agent, capability, outcome, boundary and time,
showing every denial and failure (the spec's *"no summarization that hides
denials"*). A capability inspector from the project's lock. Revocation as the
existing admin endpoint, one click, with the same confirmation shape
`--confirm KEY` gives a shell. First paint against the fixture project in the
envelope. **Ends on a host** for the one proof that matters: revocation
through Studio rejects the agent's token on its next request, locally.

**Already true, so do not rebuild it.** Every surface it clients (D1069). The
CSP discipline of `services/docs` (loads nothing from the internet, first-party
by decision, ADR 0069). The auth service's session listing and termination
(Session 15).

**Must not.** Bind a non-loopback interface without an explicit flag, and even
then never without TLS it did not get from the edge. Hold a signing key, a
database credential, a provider token, or the operator's SSH key. Offer SQL.
Summarise the audit feed. Become a verifier of the JWT in its own right — it
sends the token, it does not validate it. Read `app_private` over any path.
Log a URL, an object key, a token or a caller value (the canary applies).

**Measures.** In a rig with a control: Studio's listener present on
`127.0.0.1` and absent on `0.0.0.0` (control: a deliberate misconfiguration
refused); a query through the builder as user A returning A's rows and none of
B's (the client fixtures' third assertion, through a browser); the audit view's
row count equal to `SELECT count(*)` over the same window as root over the
socket. On the host: the revocation round trip.

**Closes.** Spec sessions 31 and 32; 41's local-auth half; 46's Studio row.

**Proposed family.** `STU-*`.

### Session 25 — Hardening, the second walk, and the Stage 3 release

**Builds.** The closing review of the three new surfaces against the
invariants in §8, with a battery per guard. The `apg` project-context default
and completion (D1065). Documentation converged: README's quickstart and
*Adding your own tables* rewritten to the path an adopter now walks; the
generated references rendered for a tenant's surface; `docs/new-team-member.md`
re-derived by diff (D693). **The second walk**: an outsider who did not build
Session 20 adopts the product, adds a table and an agent capability for it,
runs `apg dev`, generates a client and opens Studio, from the documentation
alone, and records every edit and every undocumented command — the record
handed to the gate as `APG_DX_RECORD_FILE`. Then the bump: `CURRENT_SESSION`
25, `template_version` as `upgrade plan` prices it (D1081), requirements and
claims, `session-25-check.sh` derived by diff from 18's, `scope-closure.md`
re-audited row by row, `evidence/session-25.json` from a host trip, and
`docs/stage-4-decision-report.md` written from that document — naming which
blockers Stage 3 removed, what the third costs, what the DX layer's evidence
says about the hosted question (Stage 4 §24's list, answered where it can be).

**Already true, so do not rebuild it.** The release machinery (Session 18 Run
5's shape), the gate cadence, the evidence merge, the ledger's structure.

**Must not.** Close `documented_path` on the author's walk or on a shorter
edit list (§4). Soften a `not_run` into a pass. Choose the version by hand.
Write the decision report before the evidence document exists.

**Measures.** The walk's record: zero source edits, or the claim stays
`not_run` with the list. The gates in every mode the evidence needs.

**Closes.** `documented_path`, if the walk needs no edit. Spec sessions 26, 41,
45, 47, 48.

**Proposed families.** `REL-*` extended, `DX-*` extended.

---

## 6. What Stage 3 does not build

The Stage 1 and Stage 2 non-goals hold unchanged. The Stage 3 specification's
§2.3 and §7 deferrals are adopted whole: **no hosted multi-tenant console, no
customer accounts or billing, no move away from one project per deployment on
one VPS, no storage-layer branching, no OAuth, SSO or MFA for humans, no
automatic failover, and no loosening of the agent capability model.**

**Six more, which the specification does not name and this plan does:**

- **No PostgreSQL 19** (D1061), by the operator's decision, and with it no
  `pg_plan_advice`, no SQL/PGQ and no logical-replication dev environments.
- **No public Postgres endpoint** (D1084). ADR 0042/0043/0044 stand. Every
  Stage 3 surface reaches a database over the SSH forward or runs one locally.
- **No job, outbox or worker substrate** (D1064). Stage 4's pillars III and IV
  are written on top of one and must budget building it.
- **No CI-driven deployment** (D1073). CI has no host and no credential
  reaches the VPS. A PR's environment is `apg dev` inside the runner.
- **No capture from production and no anonymisation** (D1071). A seed is a
  reviewed file the developer wrote.
- **No SQL surface for a human in a browser** (D1069), and no `execute_sql`
  for an agent under any name.

**Which of the three blockers Stage 3 unblocks for Stage 4 and 5, and which it
leaves.** Stage 3 removes the first two: after Session 20 a project has a
schema of its own, and after Session 21 an agent can address it. **It leaves
the third deliberately.** Stage 4 §6.3 (a remote `apg`), Stage 5 §11 (pooled
and direct URLs as product objects) and Stage 5 §12 (a connection gateway) all
require a database reachable from off the host, and the specification's own
§17 says the external threat boundary is *"a first-class Stage 4 feature, not a
final-session checklist."* The seam is kept for it: `runtime_override.
publication()` raises with the reason, so the first Stage 4 reader who wants a
port finds the decision before the code. **What it costs Stage 4 to take it**:
a threat model (Stage 4 §17's list, with *connection-gateway attacks* and
*wake-on-connect abuse* from Stage 5 §49 added), TLS termination for the
PostgreSQL protocol at the edge or in PgBouncer, a credential that travels and
therefore rotates (D860's rotation performed first), the isolation matrix
extended to a listener, and an ADR superseding 0042 and 0044 together.

**And one the specification names as P1 that this plan leaves evidence-selected
inside its session: the Python client** (D1068). It is built if the TypeScript
generator proves the intermediate representation carries, and not otherwise.

---

## 7. Evidence and claims across Stage 3

**Unchanged, and none of it is renegotiated.** A claim's verdict is computed
from the acceptance registry's node ids and JUnit results, never hand-entered.
Three statuses (ADR 0163): `failed` means the system is wrong, `not_run` means
the evidence is, both exit 5. A skip is not a pass; a `-k` run writes nothing;
both halves describe one release; `evidence/*` is gitignored and the host half
lives on the host.

**Which claims each session touches.**

| Session | Touches | Ends on a host? |
|---|---|---|
| 20 | new `TEN-*` claims; `documented_path`'s cause; `deployment_convergence` if a redeploy window is declared for the sitting | **Yes** — the task migration and the recapture |
| 21 | `AGT-*` claims re-run live (D942: a run that changes a plane re-runs its live proofs); `agent_scopes`, the round trip | **Yes** |
| 22 | new `DEV-*` claims, offline-only by nature — **and that is the first offline-only claim this model has ever had** (ledger §4: twenty-one requirements have no live proof and need *"an offline-only claim, which is a decision about what a claim IS"*). Session 22 takes that decision, because a workstation environment has no host half | No |
| 23 | new `GEN-*` claims; one live half (the served hash) | The live half rides 24's or 25's trip |
| 24 | new `STU-*` claims; `agent_revocation`'s live half through Studio | **Yes** — revocation |
| 25 | `documented_path`; every Stage 3 claim in every mode | **Yes** — the release trip |

**The eight `not_run`, and what closes each.** `fresh_host` — a file, the first
gate handed it. `documented_path` — Session 25's walk with no edit; anything
else keeps it `not_run` and says why. `bootstrap_identity`, `api_authorization`,
`credential_rotation_planes` — a rotation performed by the operator (D860),
recommended before Session 24 adds a fourth verifier. `deployment_convergence`
— a redeploy window declared, which Session 20's sitting can be. `port_allocation`
— a witness on a fresh host, the operator's alongside `fresh_host`.
`replacement_host_restore` — by decision, untouched.

**`fresh_host` and `documented_path` need particular care** (ADR 0197). The
first is settled: who drove the bring-up does not bear on whether an empty host
reached a working deployment, and the document exists. The second moved from
*nobody has tried* to *somebody tried and the path does not hold*, and Stage 3
must not soften that into a green tick by any route other than a second walk
with zero edits by a person who did not build the extension point. The
agent-versus-person question stays open until that walk needs answering.

**Three things Stage 3 adds to the model:**

1. **An offline-only claim exists** (Session 22), with `claim_mode` taught the
   third mode and `merge` accepting a document with no host half *for that
   claim only*. The twenty-one requirements ledger §4 lists become reportable
   under the same decision; **they are not retrofitted in bulk** (D696).
2. **A generated artefact is a claim about the hash it was generated from**,
   and its proof reads the served surface, never the document (Session 23).
3. **Every new deployed-document field is classified in the matrix in the
   session that adds it** (D702, D1029), and the trip's gate proves it.

---

## 8. The security invariants Stage 3 may not weaken

Stage 2's table carries forward whole. What is new is that three of the six
sessions build *clients*, and a client is the shape most likely to become an
authority by accident.

| Invariant | Control | Where Stage 3 puts it at risk |
|---|---|---|
| PostgreSQL is the final authorization authority | RLS, FORCE, the pre-request hook | A tenant migration (20) that could touch `app_private`; Studio's query builder (24) |
| A project's identities are derived once, in `naming` | ADR 0002 | The project migration set's names (20); the derived scope vocabulary (21) |
| An agent cannot run SQL | No input accepts one; the compiler cannot emit one | The derived vocabulary (21); `agent init` (21); tool wrappers (23) |
| **A human cannot run SQL through a product surface** | `db.sh sql` executes only hash-verified generated files; no other door | **Studio (24)** — the one feature that would make it an authority |
| **The DX layer holds nothing the human does not hold** | The spec's §4.1/§4.4; `apg.sh`'s "a name, not a layer" | `apg dev`'s local JWT (22); a generated client's config (23); Studio's token (24) |
| A revoked token stops on its next request, locally | `agent_claims_are_current` | Studio's revocation (24) must be the existing endpoint, not a second path |
| An unauditable write does not happen | `agent_audit_begin` before the scope check | A roster read from the lock (21) must not change the order |
| An agent record carries no URL, key, token or caller value | `audit.redact` from the lock, the canary | Studio's audit view (24), a generated client's logging (23) |
| The MCP runtime holds no credential | `FORBIDDEN_VARIABLES` | Unchanged; 21 touches the roster, not the environment |
| One service cannot read another's credential | Per-consumer immutable generations | `apg dev` (22) has no generations at all — and no credential to put in one |
| A restore never overwrites the active volume | The restore path's refusal | Unchanged; `apg dev` never restores (22) |
| **A workstation holds no production secret** | `connect.sh` prints no password; `dev-token.sh` never emits one | `apg dev` (22), a generated client's `.env` (23), Studio (24) |
| Projects share no project-scoped value | The isolation matrix | Every new deployed-document field (20, 21, 23) |
| **There is no public Postgres endpoint** | ADR 0042/0044; `publication()` raises | Nothing in Stage 3 may call it; Stage 4 decides (D1084) |
| A deploy over a broken archiver fails | Step 6c | Unchanged |
| **A report may not substitute an answer for a failure to determine one** | ADR 0195 | Every new *reader*: `apg` context resolution, the hash check (23), Studio's status lines (24), `dev`'s readiness (22) |

**The last row is the one Stage 3 is most exposed to.** Session 19 found
twelve instances of ADR 0195's class in one day, four of them in guards written
that day. Stage 3 writes three new surfaces whose entire job is to *report*
state to a human, and each of them has more readers than any command in `bin/`.
The voice to copy is `bin/backup.sh`'s timeout message; the test is whether a
surface can say *unknown* and why.

---

## 9. Risks and stop conditions

**Stop and ask** rather than proceeding, when:

- a tenant migration could reach `app_private`, a role, the pre-request hook
  or a platform object's grants (20);
- the derived scope vocabulary would admit an administrative or a storage
  scope, or a name for a base table (21) — ADR 0006's reason for refusing a
  pattern-validated vocabulary;
- a roster read from the lock would let a lock serve a tool the contract did
  not compile (21);
- `apg dev` would need a provider credential, a repository credential, or a
  route to a real project's database (22);
- a generated client would learn the live hash from the deployed document
  rather than from the served surface (23, ADR 0158);
- a Studio feature needs SQL, a non-loopback bind, or a credential beyond the
  human's token (24);
- a public Postgres port would be published for any reason (D1084);
- a currently-passing test would be weakened to make a new one pass, or an
  equality turned into a containment check — **the anti-vacuity guard's
  rewrite in Session 20 is the one place this plan authorises a shape change,
  and only with the control that an empty scrape still fails**;
- `--render-only` stops working with no host and no root;
- a Stage 1 or Stage 2 claim goes red and the tidy fix is on the proof's side;
- a session would want a coordinator to be a client of (D1062).

**The failure mode Stage 3 is most exposed to is new.** Stage 1 kept producing
*a value that looked measured and was not*; Stage 2's was *re-implementing
what existed one layer over*. Stage 3 builds surfaces that describe the system
to a human, and its failure mode is **a client that becomes an authority**: a
generated type trusted over the served surface, a Studio status computed from
a document instead of observed, a dev environment that "knows" the production
schema. Every row in §8 marked new is an instance caught at plan time. The ones
caught at run time will look like convenience.

**The six standing questions apply unchanged**, and question 5 — *when a
decision is implemented, which of its callers got it?* — is sharper here than
in Stage 2, because Sessions 20 and 21 each change a definition that has more
readers than any decision Stage 2 took: what a migration set is, and what a
scope name is. Grep every reader before touching either (D979: the second
reader was a heredoc in a shell wrapper).

---

## 10. Open items carried in

Everything in ledger §8 and CLAUDE.md §9 that §2.3 did not resolve, plus what
Stage 3 creates.

**Carried in and not addressed by Stage 3:** D1045 (the owner's); the rotation
performed (D860, recommended before Session 24); `replacement_host_restore`
(D1028); the IPv6 scan (D688); `process-max` (D593, now the reason for D1066);
`lock-versions.sh --update`'s re-adoption (D540); D340; `apg-diag`'s log
allowlist (D380); the audit and idempotency tables' retention — **Session 24
must state the decision it inherits even if it does not take it**; no span
leaves the process; the collector on `edge` only; the OOM history unknown
(D771); the signing-key cutover and rotation repairs never performed on a host;
the 24 unclaimed requirements — **reportable after Session 22's offline-only
claim, not retrofitted** (D696); the two unregistered P2 capabilities
(D698, D714 — and the pgvector example becomes a *tenant's* migration after
Session 20, which is the honest place for it); D1059's three buckets in the
watcher; `requirements-dev.in` pinning nothing; the environment not verified
against the lock (D297); the smaller items Stage 2's §10 lists, each still true.

**Carried in and addressed:** the tenant extension point and its three faces
(20); ADR 0196's migration (20); D1060 and D1048 (20); D1086 (20); D933 and
D1056 (21); the offline-only claim decision (22); the `apg` context default
(25); `documented_path` (25); `fresh_host` (the first gate).

**Created by Stage 3, and named here so no session inherits them silently:**

- **A second migration set is a second lock to keep frozen**, and a second
  place a stale render can lie (D1053's family). Session 20 owns the guard
  that both locks are checked by every reader that checks one.
- **A derived vocabulary is a new reader of the contract**, and the contract
  now changes when a tenant's schema does. Session 21 owns saying what a
  contract change does to an *issued* token's scopes — `authz_version` moves
  on every transition today, and a scope that stops existing is a transition
  nobody has defined.
- **Generated artefacts go stale like `backup_state`** (D700), in both
  directions, and are held by people who did not generate them. Session 23's
  hash check is the whole defence, and it is only as good as the served value
  it reads.
- **Studio is a fourth holder of a human's token** and reads the audit table,
  which nothing prunes. Session 24 inherits the retention question and the
  rotation gap.
- **An offline-only claim** changes what `merge` accepts. Session 22 owns the
  guard that no claim with a live half can ever be reported through it.
- **Six more gate scripts**, each derived by diff from the newest and
  registered in `SHELL_COMMANDS` — D1014's rule, and D703's unguarded half
  (the prose a gate prints) is still unguarded.

---

## 11. How a Stage 3 session is planned

**Yes, each of the six still gets its own plan**, in the seven-section shape
Stage 2's §11 fixed — sections 0, **1**, 2, 4, **5**, 7, 8, 9 — at 400–700
lines. That table is not repeated here; it stands. What Stage 3 adds is what
must be settled *before* a plan is written, because Session 19 measured the
cost of settling it during a run.

**Before a line of a session plan:**

1. **Read this document's §1 rows for the session and check each premise
   against the tree again.** Ten weeks passed between the Stage 2 plan and
   Session 17, and D954 found two of its premises wrong by then. A row here is
   a measurement with a date.
2. **Decide the requirement ids** (§2 of the session plan). Moving
   `CURRENT_SESSION` is all-or-nothing (D690), so the ids exist before the
   first run.
3. **Decide the trip's shape.** Every Stage 3 session but 22 and 23 ends on a
   host. A trip is three gates and two repairs (Sessions 15, 16, 17, 18 each
   said so); **grep the previous trips' *"if something goes wrong"* sections
   first** (D977: two hour-long re-discoveries in one trip).
4. **List the rigs**, each with its control, before the runs that depend on
   them — and **grep the plans for every third party first** (dbmate's
   second directory in 20, the editor schema association in 21, Docker's
   loopback publication in 22 and 24, the OpenAPI digest in 23).
5. **Grep every reader** of any definition the session changes (D979). For 20
   that is every reader of `migrations.load_manifest` (eight in `bin/` and
   `src/` alone, plus the gates); for 21 every reader of `agent_scope` and
   `EXPECTED_TOOL_NAMES`.

**What is deliberately not simplified**, because it is what caught the defects
rather than what cost the time — Stage 2's four, plus two from Session 19:

- **§1's six columns.** A row with four columns is a note.
- **The mutation battery** in every run that writes a test: anchors
  pre-flighted and a miss fatal (D269), a control the mutation cannot reach
  (D499), an assertion about *how* each mutation failed (D386), and **a
  survivor read as evidence** — a weak test, an uninformative mutation, a real
  gap, or a broken reader (five times in Session 13).
- **Measuring a third party with a control before writing anything that
  depends on it.**
- **`pytest --setup-plan` before a trip**, with the variables set (D671, D676).
- **ADR 0195 applied to every reader the run writes**: three outcomes, the
  third reported. Six instances in one day were in guards written that day.
- **`tests/contract/test_cli_contract.py` in the targeted list of any run that
  adds or removes a `bin/` verb** (D1014), and every guard module whose subject
  the run touched.

**The gate cadence does not change and is not a save button.** Documentation
only → nothing. Generated artefacts could drift → `bin/session-01-check.sh`
alone. Code → the modules the change touches; **CI is the full check**, read by
the full SHA and the HTTP status, with three buckets (D1059). Before a host
trip, a deploy or a session close → every applicable gate, once, in every mode
the evidence needs.

---

## Appendix — what to consult, and what to measure instead

**Consult, in this order:** this document's §1 and §3. `docs/scope-closure.md`
§8 — what Session 19 left open, with a reason on every row.
`docs/plans/session-19-implementation-plan.md` §1 (D1033–D1060), which reads
as *what the tree said* against *what an outsider measured*, and `FINDINGS.md`
in the launch folder, the account it was written from. ADR **0195** before
writing any check, status line or reader; **0196** and **0197** for the two
decisions Stage 3 starts from. `docs/plans/stage-2-plan.md` §1 for the method
this document copies, and `docs/stage-3-decision-report.md` §4–§5 for the
premises it corrected first. The Stage 3 specification's §1.4 (what stays
unchanged) and §4 (the client principle), which are the two parts this plan
adopts whole; the Stage 4 and 5 visions only for §6's list of what they will
need.

**The ADRs Stage 3 most needs**, rather than all 197: **0002** (derive an
identity once — the rule `apg.sh` and the derived vocabulary both follow);
**0042/0043/0044** (no publication; the forward; the broker on the host — the
three that Stage 3 keeps and Stage 4 must decide together); **0050** (nothing
exists in `api` the reviewed contract does not name, met from both directions
in Session 19); **0127** (a caller value is a value; the request is built from
the lock); **0140/0141** (a hidden tool is still callable; a denial is
audited); **0158** (the deployed document is the address book, not the
diagnosis — the rule the hash check lives by); **0162** (what a bump permits,
and that rollback is three operations); **0177/0183/0184** (a capability
declares a version, a profile only narrows, an adversarial case carries no
reason); **0186/0187** (what ephemeral means and what a retirement never
removes); **0195/0196/0197**.

**Measure instead of consulting**, every time: what a *served* surface says
against what the deployed document recorded (D700, D701, ADR 0158); whether a
fixture shares the code's belief (F-005: one fixture reimplemented the
bootstrap and stopped a line short; question 6); whether a reader can say
*unknown* (ADR 0195); what a third party's exit code means when the state is
in a field (D145, D548); whether a proof has ever run (`--setup-plan` is the
cheap half; a battery is the other); and **what the tree does today**, because
every premise in the specification this plan audited was true of a document
and false of the tree.

**Before measuring how a third party behaves, `grep` the plans for it.** Nothing
indexes the ~1,086 measured facts by subject; the pointer has to be a `grep`,
and Session 19's rig 19 found both readings of the tree wrong on a grant that
three sessions had read the same way.

**Never write a measurement you did not run** (D267). Every number in this
document was measured on 2026-09-10 at `a0d853f`, or says whose it is.
