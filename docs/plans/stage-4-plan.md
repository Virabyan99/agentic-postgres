# Stage 4 — plan of record

**This is a stage plan, not a session plan.** It sits above six session plans
and owns what all of them would otherwise repeat: where Stage 4 starts, what
the Stage 4 specification asks for that this repository already has or refuses,
the four decisions CLAUDE.md §4 requires a new body of work to settle, and the
open items carried in from twenty-nine closed sessions.

**§1 is the point of this document.** The Stage 4 specification calls itself an
*"aspirational guidance document; not an implementation specification"* and
says in its own §0 that *"every major Stage 4 commitment must be revalidated
against evidence produced by Stages 1–3 before implementation."* §1 is that
revalidation, measured against the tree rather than recalled. It is why the
answer to *"twenty-four more sessions?"* is **six**, and why the largest half of
the specification — the hosted platform — is **deferred by the operator's
decision** rather than built.

**It builds nothing.** No requirement is registered here, no ADR is written
here, and no code changes because of it. The two ADRs it names are Session 30's
first act. Each of the six sessions gets its own plan, and §11 says what shape
those take.

---

## Status — read this first

```
STAGE 3 IS CLOSED.  Tagged 1.6.0 on a16cb84 (2026-09-15). Sessions 26-29 were
                interludes: 26 documentation (ADR 0208), 27 the repair release
                1.6.1 / 1.6.2 (ADR 0209), 28 offline (ADR 0210-0215, migration
                0033), 29 THE TRIP. None of 26, 27, 29 registered a requirement,
                so the ordinal skips them the way it skips 19 (D1063).
RELEASE         1.9.0, tagged 2026-09-21 on 4344a1ff4836 -- THE COMMIT THAT WAS
                DEPLOYED (D1425, with D1641's one stated exception: the second
                sweep's INSTRUMENTS came from 05fdfe9, whose deployable diff
                against the tag was measured EMPTY).
SESSIONS DONE   30 (2026-09-19, 1.8.0) and 31 (2026-09-21, 1.9.0). FOUR LEFT:
                32 the durable step substrate and workflow execution - 33
                approval gates, compensation, provenance - 34 governed
                connectivity - 35 change-governance, hardening, the third
                reader, the Stage 5 decision report.
EVIDENCE        evidence/session-31.json: 145 claims, 139 passed, 5 not_run,
                1 failed (documented_path, deliberately -- §2.4). The best
                document this repository has produced, and the ten claims
                Session 31 added all passed on their FIRST execution anywhere.
CURRENT_SESSION 31. Stage 4 numbers its sessions 30-35.
template_version 1.9.0. host.yaml schema 3. Outputs schema v18, capability
                manifest 4, lock 4, project lock 3, project manifest 6,
                api-surface 2 -- none of them moved in 30 or 31.
ADRs            225, next free 0226.   migrations 33, released and applied on
                both projects, fix-forward only -- UNCHANGED through 30 and 31.
                requirements 238.   claims 145, 24 declared offline.
divergences     D1-D1513 recorded in the session plans. D1514-D1536 recorded
                here. D1537-D1581 in Session 30's plan, D1582-D1644 in Session
                31's (D1633 never issued).  **Next free: D1645.**
PostgreSQL      18.4 (pgvector/pgvector:pg18 by digest). STAYS. Decided by the
                operator on 2026-09-18 (D1515).
DIRECTION       APPLIANCE FIRST, HOSTING DEFERRED. Decided by the operator on
                2026-09-18 (D1517, D1518). No public endpoint, no organisations,
                no login, no remote contexts, no hosted Studio, no support
                grants in Stage 4.
OBSERVABILITY   The OTel collector and Prometheus that already run, bounded.
                No ClickStack. Decided 2026-09-18 (D1519).
```

**Every number in §1 onward was measured on 2026-09-18 at `de9ecbb`**, or says
whose it is; **the Status block above is re-read at each session's close** and
currently stands at Session 31's, 2026-09-21.

---

## 0. Where Stage 4 actually starts

Session 25 closed Stage 3 and its decision report (`docs/stage-4-decision-
report.md`) said what Stage 4 must start from: two of the three blockers Stage 3
was given are removed (a tenant has a schema of its own; an agent can address
it), the third — *"there is no public endpoint a customer could be given"* —
is *"not removed, and not attempted"*, and **nothing measured in Stage 3 argues
for or against it**. Then four interludes happened that the specification could
not know about: an outsider upgraded a real fork and wrote thirty-four
findings, a repair release answered them, a session rehearsed the signing-key
rotation offline and found the step guarding the irreversible one was reading
the wrong bytes (ADR 0215), and a trip put the deployment, the evidence and the
tag on one commit for the first time. `docs/scope-closure.md` §22 is the list of
what that trip closed and what it hands on.

**The numbers that shape Stage 4's plan, all measured at `de9ecbb`:**

- **953 tracked files. 135,618 lines under `tests/`** (191 contract modules,
  44 deployment, 7 security, 5 external, 2 integration, 2 recovery; there is no
  `tests/unit`). Stage 3's six sessions added ~31,000 lines of tests to Stage
  2's 104,855.
- **222 requirements across twenty id families**; the largest are SEC (~39),
  AGT (~28), CFG 16, OPS 16, DBX 15, DEP 15, REC 15, DX 12, STO 11, API 11, STU
  10, GEN 8. No `future` placeholders, so a session's requirements arrive with
  their proofs in the commit that moves the constant (D690).
- **114 entries under `bin/`**, twenty-six `session-NN-check.sh` gates (the
  newest is 28's, derived from 25's by diff), and **`bin/apg.sh`** as a pure
  dispatcher: `apg <verb>` is `bin/<verb>.sh`, `--list` derives the verbs from
  the directory, `APG_PROJECT` is applied only when the verb's own `--help`
  names `--project FILE` and is announced on stderr every time.
- **Zero lines of worker, queue, outbox, scheduler, webhook, workflow,
  connector, organisation, invitation, control plane or coordinator** anywhere
  under `services/`, `src/`, `bin/`, `migrations/`, `schemas/` or
  `compose.yaml`. The word *workflow* occurs three times, and all three are the
  tree refusing one: `services/auth-api/app/mcp_tools.py:588-590` — *"a
  workflow needs durable pending state, a second principal and a notification
  plane, none of which exists"* — and the same sentence at
  `mcp_errors.py:52-55` beside the `approval_required` boundary. The nearest
  thing to a worker is `services/auth-api/app/storage_cleanup.py`, a lease-based
  tombstone collector (302 lines): a monotonic deadline inside the lease, a
  margin derived from the HTTP client's timeouts, delete-before-finish so the
  delete is at-least-once, `SWEEP_POOL_SIZE = 1`, and an operator command rather
  than a daemon. It is the pattern Stage 4 copies, not the code.
- **The agent plane's write path is already the step a workflow would take**:
  audit begin → scope check → `requires_approval` refusal → dry-run (ADR 0182)
  → idempotency key claimed in the write's own transaction (ADR 0181, `PT412`)
  → upstream → audit end, with nine named denial boundaries (ADR 0178) of which
  `approval_required` and `budget_exceeded` exist and are audited today. Five
  budgets (rows, 1 MiB serialised bytes, elapsed, concurrency, memory) — **all
  per call or per process, none a rate, none per agent or per project**
  (`mcp_budgets.py`).
- **Every capacity number the host has is in code, not in a document a program
  reads**: `HOST_MEMORY_GUARDRAIL_MB = 1600` (`config.py:612`, justified in a
  comment as *"the host is 3814 MiB with no swap"*), `mem_limit` on six of
  twenty services, six claimants summed on `max_connections` 56 (ADR 0070),
  per-role `CONNECTION LIMIT` and `statement_timeout` written by the bootstrap
  plane. **Host RAM is never read** (0 hits for `MemTotal`/`meminfo`);
  `host.yaml` and its schema have no memory, CPU or disk field; nothing sets
  `pids_limit`, `ulimits` or `cpus`.
- **The observability the specification wants to replace has never been
  read.** An OTel collector (`metrics`, `compose.yaml:937-995`, `mem_limit`
  128m, `edge` only, a metrics-only pipeline exporting Prometheus exposition
  and nothing off-host) and Prometheus (`store`, `:1012-1078`, `mem_limit`
  192m, `--storage.tsdb.retention.time=14d`, **no Traefik router**) run on
  both projects behind `profiles: [session14]`. `mcp_metrics.configure` and
  `mcp_tracing.configure` have no production caller; no span leaves a process;
  no log is shipped (Docker's `local` driver, 10m × 5).
- **The doctor has eleven checks and the eleventh has no threshold** (ADR
  0213). `disk headroom` reads `du`/`df` at PGDATA in copies of the cluster.
  Nothing reads WAL volume, memory, database size in bytes, storage bytes,
  backup bytes or request counts: **there is no metering** beyond agent-record
  counts and `fleet.py`'s denials-by-reason.
- **Eight rehearsal scenarios** (`rehearsal.SCENARIOS`): service-termination,
  database-restart, backup-credential-failure, wal-archiving-failure,
  registry-loss, disk-threshold, capability-drift, provider-loss (recorded,
  never induced). `restore.py --from primary|mirror`; `dr-kit.py export|verify`;
  the replacement-host restore measured once at **247 s** and recorded in four
  documents. The only measured downtime anywhere is the **8 s** kernel reboot
  of 2026-09-17 (D1500); no deploy has ever had its downtime measured.
- **The migration plane is fix-forward with a lint and nothing above it**:
  `migrate.py freeze-lock|verify-lock|render|status|up` (+`--project`,
  `--follows`), `lint_project_set` (`migrations.py:740-860`: ten forbidden
  statement shapes including anything naming `app_private`, only `SET LOCAL
  ROLE {{object_owner}}`, no `DROP` of a release-published object, `FORCE ROW
  LEVEL SECURITY` on every `app` table, a `down` that exists and contains
  `AP900`). No propose, review, approve or reject; no destructive-change lint;
  no schema diff.

**What Stage 4 has is a specification written before Stage 3's tree existed**,
on top of the Stage 1, 2 and 3 specifications rather than on top of their
plans. Its premises — PostgreSQL 19, a coordinator, a Stage 2 job/outbox
substrate, ClickStack, an external audience — are each measured false or
undecided here. **So §1's job is the one the Stage 2 and Stage 3 plans named**:
the list of places where the specification asks for something this repository
already has, asks for it in a shape this repository refuses, or asks for a
product this repository's owner has decided not to build yet.

**Two sentences of the specification are right and load-bearing and this plan
keeps them whole.** *"The platform must know when the host is full and say
no"* (§2) and *"durable composition of already-governed capabilities … should
not invent a separate permission model"* (§8.1). The first is Session 31 and the
second is Sessions 32–33, and each is adopted as written. **The specification's
third sentence — *"multi-user control plane, isolated single-node data
planes"* — is deferred by decision**, and §6 records what it costs to take up.

---

## 1. The divergence table

Six columns, the house shape. Rows are **measured facts about this repository
as it stands at `de9ecbb`**, not predictions about the sessions. Where a
premise was settled by the operator rather than by measurement, the `Decision`
column says so with the date.

**Next free number after this table is D1537.**

| # | Spec says | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D1514** | Header: *"approximately 24 high-intensity sessions, provisionally Sessions 49–72."* §20 numbers them 49–72 in seven blocks. | **Stage 1 was Sessions 1–12, Stage 2 13–18, Stage 3 20–25**, and 26–29 were interludes that registered nothing (`src/agentic_postgres/__init__.py:108-129` records 19, 26 and 27 as skipped; 29 moved no constant). `CURRENT_SESSION` is 28. Nothing asserts consecutive numbers; the ordinal is the evidence model's key (D705). | **Stage 4 is Sessions 30–35.** The specification's numbers appear only in this table and in §3's *absorbs* column. | Renumbering silently is cheaper than carrying two numberings; a gap is honest; a gate for a session that registered nothing would be a file that could never go green (D1063's argument, third time). | — |
| **D1515** | Header: *"PostgreSQL 19 baseline."* §13.3, §13.5 (`pgroll`), §13.6 (`pg_ivm`, `pg_cron`), Appendix A. | **The tree runs 18.4** (`versions.env`: `pgvector/pgvector:pg18` by digest). `pg_ivm`, `pg_cron`, `pgroll` and `pg_stat_statements`: 0 hits under `services/ src/ bin/ migrations/ compose.yaml`. No proof reads a 19-only feature. | **Stage 4 stays on PostgreSQL 18.4. The operator decided this on 2026-09-18, during this plan's audit, as they did for Stage 3 (D1061).** Each extension is its own ADR if ever wanted, and none is wanted by a Stage 4 session: no session here needs a scheduler in the database (D1522 uses the worker's own interval table), an incremental view (the doctor reads counts) or online schema change (D1523). | The specification's own §13.6 says *"do not add merely because it exists"*, and nothing in §1–§20 depends on any of the four. A move to 19 is priced by `upgrade plan` when a `pgvector` pg19 image and a pgBackRest pin exist. | 0162 |
| **D1516** | §0: *"Stage 2 establishes … durable bounded jobs."* §8.1: *"Stage 2 establishes bounded background jobs."* §9.2: *"The durable event path should build on the Stage 2 job/outbox substrate."* §13.3 lists a *"bounded background worker, workflow executor, connector/event worker"* as data-plane components. | **Nothing exists**, re-measured: `outbox`, `job_queue`, `queue` (as a table or process), `cron`, `saga`, `compensat`, `webhook` are 0 hits; `worker` hits are `storage_cleanup.py` and uvicorn prose; `retry` hits are HTTP client constants and advice text. D1064 recorded this at the Stage 3 audit and Stage 3 built no consumer for it, as planned. The tree refuses a workflow in words at `mcp_tools.py:588-590`. | **Stage 4 builds ONE substrate, in Session 32, and pillars III (workflows) and IV (connectivity) both consume it.** The substrate is durable step state in `app_private`, written and read through SECURITY DEFINER functions granted to one worker role (the `agent_audit_begin` pattern, ADR 0135), driven by a worker copying `storage_cleanup.py`'s lease discipline. Session 32's first measurement is where the worker lives — a loop in the `auth` process or a new container — priced by memory and connections against the capacity Session 31 declares. | A substrate with no consumer was the most expensive dead code Stage 2 priced (D711); building it in the session that also builds its first consumer is the only shape that has ever worked here. Two substrates (one for workflows, one for events) would be D704's second axis at the worker. | 0135; ADR needed (32) |
| **D1517** | §4 (organisations, members, roles, invitations), §6.1 (`apg project create|list|use|status|upgrade|export|retire`), §6.3 (`apg login`, `apg context`), §13.2 (*"Next.js, Better Auth, organization/membership/invitation support, Passkeys and/or 2FA"*), Sessions 50–52, 57–59. | **Absent, all of it.** No coordinator (D1062 still true: 0 hits under the product directories). The auth service's routes are `/auth/login|refresh|sessions|me|jwks.json|reset-password|agent-token`, `/admin/users`, `/admin/agents`, `/admin/audit`; a user is a role suffix plus a scope set with no admin boolean; `totp|webauthn|passkey|oauth|sso|invitation|organization`: 0 real hits. `apg` has no `project`, `login` or `context` verb; retirement is `apg project-retire`. `product-contract.md` §5 lists *"a shared, multi-tenant control plane"* and *"a hosted web console or SaaS offering"* as non-goals: *"not deferred; outside the product."* | **Deferred with hosting, by the operator's decision of 2026-09-18.** Stage 4 builds no control plane, no organisation, no login, no remote context, no hosted Studio. **§6 records the precondition list a Stage 5 reading must pay before any of these**: the rotation performed (D860 — Session 30 pays this one), the tenancy non-goal changed by ADR, an authoritative registry replacing the operator's read (ADR 0185 drew that line), a threat model for external users (§17's list), and an ADR superseding 0042/0043/0044 together. | Two identity systems (a FastAPI auth service with users, sessions and agents; a Next.js/Better Auth control plane above it) is exactly the *"contradictory decisions"* the specification's own §15.5 warns against for policy engines, and the decision report's §5 found the evidence *"silent on exactly the questions blocker three asks."* A decision that has no evidence for it is taken as a decision, dated, not as a session. | 0185 |
| **D1518** | §6.3: `apg` as *"an authenticated remote client"*; §5.1: project routes behind Traefik reached by external teams; every hosted reading needs a database or an API reachable from off the host by a customer's credential. | **There is no public Postgres endpoint, by three decisions, and the seam still refuses**: `runtime_override.publication()` (`:504-524`) raises with the reason (ADR 0044); `compose.yaml` has **zero `ports:` keys**; the database and pooler are on `internal` (+`backup` for the database) and never on `edge`; a developer reaches a transport over `connect.sh`'s SSH local forward bound to 127.0.0.1 (ADR 0043). D1084 named this Stage 4's first ADR. | **ADR 0216, written in Session 30, records the decision NOT to open a public endpoint in Stage 4 and keeps the seam.** The API surfaces already on `edge` (REST, auth, storage, mcp, docs) are reached by the project's own users and agents as they are today. Wanting a port for any reason is a §9 stop condition. | The decision report said *"the public-endpoint decision is not a consequence of any number in this document"*, and the same is true here — so it is taken as an ADR with a date, which is what D1084 asked for, rather than as an implementation nobody measured a need for. | 0042, 0043, 0044; **0216** |
| **D1519** | §12: *"Preferred stack: ClickStack — OTel Collector, ClickHouse, HyperDX"*; §12.3 ClickStack as a bounded workload; §12.5 retention; §12.6 cardinality; §12.7 pressure-aware sampling; Session 69. | **A collector and a Prometheus already run per project and nothing reads them** (§0): metrics-only pipeline, `memory_limiter` 96 MiB, exposition on 8889, 14 d retention, Prometheus unrouted, `mem_limit` 128m and 192m, no `pids_limit`. The only instruments are `agent_tool_calls_total` / `agent_tool_call_duration_milliseconds` with labels `{outcome, tool}` (cardinality closed by construction, `mcp_metrics.py:48-50`), and `configure()` has no production caller. `clickhouse|hyperdx|grafana|loki`: 0 hits. The host is 3814 MiB with no swap. | **Keep what runs and bound it — the operator's decision of 2026-09-18.** Session 31: a `pids_limit` on both, the retention asserted by a test rather than a flag nobody reads, a `project` label on every series, the collector's `configure()` finally called from the service so the two instruments exist in production, and **the doctor's `capacity` and `usage` readings as the first consumer**. Session 69 is absorbed whole; §12.5–§12.7 become one row each in the envelope rather than a policy document. | ClickHouse on a 3.8 GB host beside two projects' twenty containers is a workload class this plan cannot price without a bigger VPS, and the specification's own §12.3 invariant — *"observability may lose optional detail under pressure; it may not destabilise the PostgreSQL workloads it exists to observe"* — is already met by a 128m collector that exports nothing off-host. The defect the tree has is not too little telemetry; it is telemetry with no reader (question 2 of §7). | 0164, 0086 |
| **D1520** | §7 (Pillar II), Sessions 53–56: a machine-readable capacity model; cgroup/Docker CPU, memory and PID constraints; PostgreSQL/worker/workflow/agent quotas; disk/WAL reserve and an admission controller that refuses a new project, preview, dev copy, upgrade candidate or expensive workload with the refusal in §7.3's shape. §7.4 load-shedding states. | **Half exists, in code**: the memory budget (`unreclaimable_mb`, the 1600 MiB guardrail, `mem_limit` on postgres/auth/storage/mcp/metrics/store), the connection budget (six claimants, `OPERATIONAL_CONNECTION_HEADROOM` 5, the pooler's pool never larger than the role's limit), `statement_timeout` carried into every request transaction (ADR 0068), `disk headroom` in the doctor, a `disk-threshold` rehearsal. **Half is absent**: no `cpus`/`pids_limit` anywhere, no declaration of the host's capacity a program reads, no reading of host RAM or of free disk at the Docker root, no admission check before a deploy commits a new project, no WAL-volume reading, no per-project attribution. The only cgroup read is `deploy-project.py:834` (postgres `memory.stat`). | **One Session 31.** `host.yaml` gains a `capacity` object (schema 3, migratable: `memory_mb`, `disk_gb`, `reserve_memory_mb`, `reserve_disk_gb`, defaulting to today's prose); a reader that MEASURES (`/proc/meminfo`, `df` at the Docker root and at PGDATA) and reports `unknown` honestly (ADR 0195); `deploy` REFUSES a new project when the sum of every deployed project's `mem_limit`s plus this one's plus the reserve exceeds the declared memory, printing §7.3's shape; `pids_limit` and `cpus` on every service from `config.py` defaults; `apg doctor capacity` (the readings) and `apg doctor usage` (§16); rehearsal `admission-refused`. **§7.4's load-shedding states are cut**: there is no preview, dev or workflow class on the host to shed, and after Session 32 the worker's concurrency is the one knob, set in the definition. | Admission is a *decision* and may fail closed; capacity is a *reading* and may not lie (ADR 0195's two halves in one session). Four spec sessions collapse because three of them are compose lines, a schema field and a reader, and the fourth is the one decision. Load shedding for classes that do not exist would be a policy with no subject. | 0068, 0070, 0131, 0195; ADR needed (31) |
| **D1521** | §8 (Pillar III), Sessions 61–64: a workflow schema with versioned definitions, durable state, restart safety, retries with backoff, idempotency, cancellation, timeouts, human approval gates, external-event waits, compensation, capability-version pinning, policy-version provenance, audit correlation, budget enforcement, revocation checks at step boundaries; `apg workflow init|validate|dry-run|run|status|pause|resume|cancel|inspect`. | **Nothing exists and every ingredient does** (§0): a capability declares a version and is compiled into a lock with a digest (ADR 0177, 0200/0201); a write carries an idempotency key claimed in its own transaction (0181); dry-run is a rolled-back write (0182); `requires_approval` already refuses with the `approval_required` boundary; a denial is audited with its boundary (0178); a token's scopes are re-checked on every call against `authz_version`; the harness derives adversarial cases per frozen field (0184). What is missing is exactly the sentence at `mcp_tools.py:588`: durable pending state, a second principal, a notification plane. | **Two sessions, not four.** **Session 32**: the substrate (D1516) and execution — a definition is YAML naming `tool@capability_version` from the project's lock, compiled and validated the way `mcp-contract.sh` compiles a manifest; `apg workflow init|validate|dry-run|run|status|cancel`; bounded retry with backoff from the definition; the idempotency key per (run, step, attempt) through the existing header; the agent token re-minted per step through `/auth/agent-token` so revocation is checked at every boundary by the existing path; budgets consumed as the owning agent. **Session 33**: `approval` steps (the run parks on `approval_required`; `apg workflow approve|reject` by a human holding a new scope, recorded in the audit), `wait` steps resumed by an event (34) or a timeout, compensation as a named capability run after a later step fails or on cancel, and `apg workflow inspect` as provenance read from `agent_audit` correlated by run id. `pause|resume` are not built: a parked step IS a pause. | A step is a tool call under the same scope check, or it is a second permission model — the specification's own rule (§8.1), and the one that keeps the harness's cases valid for workflows. Four sessions was Stage 1's shape borrowed a third time; the split here follows the two things that are genuinely new: durable state (32) and a second principal (33). | 0135, 0177, 0178, 0181, 0182, 0184; ADR needed (32, 33) |
| **D1522** | §9 (Pillar IV), Sessions 65–67: inbound webhook connectors with signature validation, replay prevention and schema validation; versioned domain events on a transactional outbox; outbound delivery that is durable, at-least-once, idempotency-aware, replayable, bounded-retry with dead-letter visibility; scheduled connectors; event-triggered workflows; *"domain events, not raw CDC"*; `apg connector init|validate|test|enable|disable|status`. | **Nothing exists**, and one constraint is measured that shapes the design: `lint_project_set` refuses any project migration that names `app_private` (`migrations.py:142-159`), and `CREATE PUBLICATION` / `CREATE SUBSCRIPTION` are forbidden statements — so an outbox cannot be a project's table and raw CDC is already refused. An agent identity with a profile that only narrows (ADR 0183) exists, which is what a connector identity is. The auth service is the one place a new route can live, and every route on `edge` sits behind a per-project Traefik router and middleware (`naming.py:1132-1152`). | **One Session 34.** The outbox and its emitter are RELEASE-owned: `app_private.outbox` plus a function under a schema the lint allows (`api.emit_event(name, version, payload)`, SECURITY DEFINER, granted like `agent_audit_begin`), which a project's reviewed RPC calls **inside its own transaction**; delivery by the worker (32): HMAC-signed, at-least-once, bounded retry, dead-letter visible in `apg connector status`; **inbound**: `POST /connectors/<name>` on the auth service — signature, replay window, JSON-schema validation, then ONE allowlisted tool as a connector identity (an agent under a profile); event → workflow start (33's `wait`); scheduled connector = the worker's own interval table. `apg connector init|validate|status|enable|disable`; `test` is `dry-run`. **The inbound route is the one new surface Stage 4 exposes to an unauthenticated third party and it gets its `THR-*` rows before code**, in the session's first run. | An outbox written by a trigger on a base table would bypass the reviewed contract (ADR 0050) and make every base-table write an event nobody reviewed; an emitter the RPC calls is the *"intentional and governed"* event the specification asks for. A connector that is an agent identity inherits the budgets, the audit and the profile for free, and cannot gain SQL because no agent can. Three spec sessions collapse because the outbox, the delivery and the trigger are one worker's three loops. | 0050, 0135, 0141, 0183; ADR needed (34) |
| **D1523** | §10 (Pillar V), Session 68: `MigrationProposal`, `CapabilityProposal`, `PolicyProposal`, `WorkflowProposal`, `UpgradeProposal`; `apg migrate propose|review|approve|reject|apply`; a proposal carries hash, schema before/after, shadow-database result, drift, safe-write lint, destructive operations, lock-risk estimate, contract impact, client impact, evaluation results, approval state; second-person approval configurable by risk. | **The plane is fix-forward with a lint and an operator** (§0): `migrate.py` has no propose/review/approve/reject (0 hits beyond the contract-freeze vocabulary); the shadow result is `apg dev up` with the candidate in the project's set (D1067); drift is `verify-lock` and D1053's installed-render check; the safe-write lint is `lint_project_set`; contract impact is `upgrade plan`'s class (ADR 0162, twelve classes, an unclassified change raises); client impact is `apg generate --check`; evaluation results are `render-evaluation-report.py`. **Absent**: a destructive-change lint (`DROP TABLE`/`ALTER … TYPE` detection: 0 hits; the `destructive` pytest marker is declared and used by zero tests), a lock-risk estimate, any record binding those readings to an application, and a second person. | **Not a session; one run inside Session 35, as a RECORD.** `apg migrate propose --project M` writes `projects/<slug>/proposals/<digest>.json`: the set's digest, the dev-cluster apply result, the lint, a new destructive lint (a `DROP`/`ALTER … TYPE` over a project-owned object named, not refused), `upgrade plan`'s class, `generate --check`'s diff, the harness's counts. `migrate --project up` on a HOST refuses a set whose proposal is absent or stale. `approve` is a second record naming a second username, and a project manifest may declare `approvals_required: 0|1`. `CapabilityProposal` is the same record over `mcp-contract.sh compile`; `PolicyProposal`, `WorkflowProposal`, `UpgradeProposal` are not built — a workflow is a capability manifest's neighbour (32) and an upgrade is `upgrade plan`'s output already. | In an appliance with one operator a proposal system is a record that binds the readings that already exist to the act that applies them, and the lock-risk estimate — the one reading nobody has — is not built on a guess (D267). The two-person rule is a manifest field, so the example project can require it and alpha need not. | 0162, 0184; ADR needed (35) |
| **D1524** | §11.3, Session 70: *"online or reduced-downtime upgrade orchestration"* — a candidate stack on the same VPS, synchronisation, smoke, contract checks, write drain, route switchover, rollback window. | **A deploy already recreates only the containers whose mounted content changed** (ADR 0155: a digest label per service, `render-mount-digests.py`), and a redeploy that changes nothing recreates nothing. The only measured downtime is the **8 s** kernel reboot; **no deploy's downtime has ever been measured**. A candidate cluster synchronised from the running one needs logical replication, which the tree refuses for the reason D1066 gave (`wal_level = logical` makes production a replication source) and the lint forbids (`CREATE PUBLICATION`). `upgrade.py` has exactly `check|plan|verify`; `blue/green`, `candidate stack`, `cutover` as traffic: 0 hits. | **Cut.** Session 35 **measures** a deploy's downtime per service class (REST, auth, storage, mcp, the database) into the envelope, under ADR 0155's conditions, and the operator guide keeps the honest language (*"a deploy recreates what changed; the database restarts when its mounts change"*). No candidate stack, no switchover, no claim. | The specification's own §11.3 says the goal is *"not 'zero downtime' until the measured behavior justifies that guarantee"* — and nothing has been measured. Measuring first is the whole discipline; building a second cluster to avoid a number nobody has taken would be the class §7 names. | 0155 |
| **D1525** | §11.4, Session 71: failure injection — control-plane outage, service restart, PostgreSQL restart, worker restart during a workflow, connector retry storm, invalid backup credentials, R2 unavailability, disk pressure, WAL archive failure, ClickHouse pressure, observability outage, oversized telemetry event, resource-governor failure, credential rotation, operator mistake, candidate-upgrade failure, full VPS loss. | **Eight scenarios run every trip** (`rehearsal.SCENARIOS`), covering service restart, database restart, backup credential, WAL archive, registry loss, disk threshold, capability drift and provider loss; VPS loss is the node-loss runbook rehearsed once (247 s); credential rotation is Session 30's sitting. Five of the specification's list name a component this plan does not build (control plane, ClickHouse, candidate stack) or already has an answer (R2 unavailability is `backup-credential-failure`'s twin). | **Not a session.** Each building session owes its scenario in the run that builds the thing: **31** `admission-refused`; **32** `worker-restart` (a run parked mid-step survives the worker's death and resumes exactly once); **34** `delivery-retry-storm` (an unreachable endpoint produces bounded retries and a visible dead letter, never a hot loop). D1075's shape: a rehearsal that already runs is not re-run as a session. | Stage 3's rule that every deployed-document field is classified in the session that adds it (D702, D1029) has the same argument for scenarios: the author of the plane knows what breaks it. | 0190, 0193 |
| **D1526** | §16: metering (persistent storage, backup storage, WAL, API requests, DB execution time, agent calls, workflow executions, worker runtime, provider consumption, preview time, telemetry footprint) with resource profiles per project; *"operational metering, not necessarily billing."* | **Absent beyond two counters**: the doctor's `agent record` (audit rows, idempotency claims, oldest timestamps) and `fleet.py`'s denials-by-reason over a window. `disk headroom` reads PGDATA in *copies*; the mirror is counted in *objects*; nothing reads `pg_database_size`, storage bytes, backup bytes, WAL bytes or request counts (all 0 hits). Resource profiles: absent. | **One run inside Session 31: `apg doctor usage`**, per project — database size in bytes, PGDATA bytes, WAL bytes since the last full, backup repository size from `pgbackrest info`, storage object count from the existing listing, agent audit and idempotency counts, request counts read from the collector's Traefik scrape (the first consumer of D1519). Reported, never thresholded, never billed. Workflow and delivery counts are added by 32 and 34 in the runs that create the tables. Resource profiles are the `capacity` object's per-project half if a session needs one, and none does. | A reading with no threshold is the shape ADR 0213 chose for the agent record and the one §16 asks for (*"usage data should teach us whether a commercial model is even meaningful"*). Building it in 31 beside the capacity reader means the two are one command with two verbs. | 0213 |
| **D1527** | Session 49, §17: *"a dedicated Stage 4 threat model"* — malicious member, compromised session, abusive agent, connector input attacks, webhook replay, quota exhaustion, noisy neighbour, cross-project route confusion, control-plane authorization errors, hosted Studio scoping, support-access misuse, telemetry injection, project deletion races, invitation abuse, privilege escalation between roles. *"The external threat boundary is a first-class Stage 4 feature, not a final-session checklist."* | **`docs/threat-model.md` covers the appliance** — fourteen `THR-*` rows (agent token, agent SQL, cross-user, privilege escalation, service compromise, JWT forgery, secret disclosure, public ingress, edge daemon, edge logging, checkout swap, cross-project, data loss, backup compromise) plus a Studio section — and **has no sentence about external users, multi-tenancy or a public endpoint** (0 hits). Its Scope excludes DoS: *"rate limiting is a protective control here, not an authorization control."* | **Not a session.** The hosted threats (member, session, invitation, support, hosted Studio, project-deletion races) are deferred with D1517. **What Stage 4 adds gets its rows in the session that adds it, before code**: 32 `THR-WORKER` (a worker's credential and what a compromised worker can reach), 33 `THR-APPROVAL` (an approval forged or replayed), 34 `THR-CONNECTOR-INPUT` and `THR-WEBHOOK-REPLAY` (the one surface that accepts an unauthenticated request) and `THR-DELIVERY` (an outbound endpoint learning more than its payload), 31 `THR-NOISY-NEIGHBOUR` (one project's load against the other's, measured in 35). Session 30's ADR 0217 states the boundary Stage 4 works inside: nothing built here may require a hosted trust model to be safe. | The specification's sentence is right and this plan keeps it by putting each threat beside the plane it threatens, which is how Stage 2's Session 16 caught D868. A threat model for a customer who does not exist would be a document with no test. | 0217 |
| **D1528** | §6.4, Session 60: temporary audited support access — a support grant with bounded capabilities, a lifetime, audited execution, automatic expiry, owner visibility; *"prohibit standing omnipotent support credentials."* | **The standing form is `apg-diag`** (ADR 0071): a fixed allowlist of eight verbs, six services (`auth`, `storage`, `mcp` absent — D380), four queries, a 200-line log cap with redaction, one sudoers line with `env_reset`, reached only by the `apg-agent` SSH key. **It has no lifetime, expiry or rotation anywhere in the tree**, and `provision-host.sh` does not create the account. It is not omnipotent — it is read-only and cannot exec, deploy or read a secret — but it is standing. | **Deferred with hosting** (D1517): a grant with a lifetime presupposes a grantor who is not the operator. Session 30 records the no-expiry fact as this row and D380's allowlist gap in §10, and changes nothing. | The specification's problem statement is *"external users create a requirement that internal-only stages do not have"* — and this stage is internal by decision. Adding expiry to a key the operator holds would be a control with no threat behind it. | 0071 |
| **D1529** | §19, Session 72: rehearse full VPS loss — provision a replacement, install, restore control-plane metadata, restore projects, rebuild routes, verify isolation, resume traffic; publish RTO/RPO. | **Done once and recorded** (D1028, `node-loss-runbook.md`, 247 s from the mirror on a replacement host; `replacement_host_restore` stays `not_run` by decision because a rehearsal ends at the restore). Six DR kits kept. **There is no control-plane metadata** (D1517). What Stage 4 adds — workflow state, the outbox, connector records — lives in each project's database or its manifest, so the existing restore covers it by construction. | **Not a session.** Session 32 owes one restore-test row proving a restored cluster carries a parked run and its steps (`restore-test.sh` over a drill volume, ADR 0151), and Session 34 the same for an undelivered event. The RTO band stays what D593 says it is until `process-max` changes, which nothing here does. | A claim that new state is inside the thing already restored is stronger than a second rehearsal, and cheaper; the rehearsal that exists keeps running. | 0151, 0189, 0192 |
| **D1530** | §13.7 Valkey, §13.8 local inference, §13.9 ZFS/btrfs, §14.1 unified retrieval, §14.2 RLS-aware caching, §14.3 same-host replica, §14.4 snapshot branches, §14.5 local-first sync, §12.4 session replay — each *"optional, evidence-gated."* | **All absent** (`valkey|redis|zfs|btrfs`: 0 hits; no replica, no cache, no branch — branching is a product-contract §5 non-goal). No Stage 3 evidence argues for any of them: `apg dev` resets in ~10 s (`capacity-envelope.md:138-155`), no workload has been measured as interfering with OLTP, no cache miss has been counted. | **Rejected for Stage 4, in one row.** Each is an ADR if evidence ever appears, and the evidence would come from Session 31's readings and Session 35's noisy-neighbour measurement — which is the first time this deployment will have a number to gate any of them on. | The specification says of every one of them *"do not add merely because it exists"*, and §24 lists the evidence Stage 3 was to produce for them; the honest reading of that list is that none was produced because none was needed. | — |
| **D1531** | Session 72, §21: *"a team that did not build Stage 4 must receive an invitation, authenticate, create or receive a project, use remote `apg`, hosted Studio …"* — the success criterion is an invite-only team with **no VPS access** operating a project. | **Not applicable under D1517.** What this repository has instead is `documented_path`, **`failed`** since Session 25 on two model walks (six and eleven undocumented steps), and Tier 3 of `docs/pre-stage-4-audit.md`: a PERSON has never walked the path, the operator guide has never been read cold, Studio has never been opened in a browser by a person (D1303). | **Stage 4's closing measurement is the third reader** — a person, holding only the release and the task statement (ADR 0207), walking the documented path as it stands after Sessions 30–34 have added their pages; and the operator guide read cold. **Arranged in Session 35, never closed by the author** (Stage 3 §4's caution, verbatim). `documented_path` stays `failed` until then and is reported as failed. | The decision report's whole recommendation rested on this: *"the one thing it does not do — hand a stranger a documented path — is now measured, named and failing, which is a better position than a green document that had never asked."* Stage 4 adds five pages' worth of surface to that path; a walk before them would measure the wrong release. | 0207 |
| **D1532** | The specification has no row for these; **`docs/scope-closure.md` §22 and the Session 29 hand-in do**. | Seven things the last trip left, each measured there: **D1504/D1505** — `[ -t 0 ] && { [ ! -t 1 ] \|\| [ ! -t 2 ]; }` occurs once (`deploy.sh:260`) and fourteen callers reach a container the same way, seven with their own `psql()`/`docker()`; **D1359's line** — `docs/new-team-member.md:272-273` and `README.md:551-552` redirect `compile`'s stdout with `>`, which truncates the target before the command refuses; **D1513** — `release-reading` reads `HEAD` and the tag goes on the deployed commit; **D1509** — a local `refused` shadowing the module function cost a claim and `tests/deployment/test_session9_agent_writes.py` still binds one; **the `studio_*` orphan** — `test_the_query_view_shows_the_human_their_own_rows_and_not_anothers` errors at setup (its fixture cannot create a stranger with empty scopes against the `CHECK (array_length(scopes,1) IS NOT NULL)` at `0011:116`) and is a node id of no claim, so three claims read `passed` over a proof that never ran; **D1512** — both B2 mirror units failed since 2026-09-18 04:38, undiagnosed. | **Session 30, all seven, in this order: the mirror diagnosed first (live, ~30 min with root), then offline: a shared exec helper in `src/agentic_postgres/` plus one sourced shell function, the guard moved into it and every one of the fourteen callers routed through it (D979: grep them all; the count is the test); the compile line rewritten in both files (`--output PATH` on the command, or `tmp` + `mv`); `release-reading --ref`; a `ruff` rule or a contract test over `tests/` for a local shadowing a module-level function; the orphan proof repaired and registered to `studio_surface`.** | *"Documentation is not a control"* — the trip proved it twice in one day. These are small, they are certain, and every later session execs into a container through the helper 30 builds. | — |
| **D1533** | §6.4 and §11.4 name *"credential rotation"* among failure scenarios; the Stage 3 decision report names the rotation *"the first item on Stage 4's bill."* | **Never performed** (D860; declined at five trips), **fully rehearsed offline** (Session 28 Run 8, rig 28d: three real containers, a real key set, every refusal, the 930 s deadline waited out), **its pre-flight discharged** (D1477: all ten alpha containers report a non-zero pid, so ADR 0215's `/proc/<pid>/root` reader works on this host). **The audit's reason for performing it was measured false** (D1469): `bootstrap_identity`, `api_authorization` and `credential_rotation_planes` need **four** rotations between them (the signing key, the authenticator password, the docs Basic Auth password, the application credential on both projects) and the signing-key cutover moves **one of nine** node ids, so it closes **none** alone (D1496). `rotate-secret.sh` is a planner and performs none of the other three. | **Session 30's second sitting, on its own sheet and its own day, from Appendix R of the Session 28 plan and `docs/operator-guide.md` §15 — alpha first, then beta, three verifiers not four, no sweep inside the 930 s window.** Planned for what it moves: one node id, the first rotation this deployment has ever had, and the measurement of whether a rehearsed sequence holds on a host. **The other three rotations are NOT bundled**: each is a provider replacement plus a redeploy, and a sheet may not hand over a command whose precondition is the previous sheet's success (D1510). | A credential path built, tested offline and never exercised is the class §7 keeps producing; taking it as its own sitting rather than as a step of a deploy is the decision report's advice and the hand-in's, and this plan follows both. | 0088, 0215 |
| **D1534** | §18: a control-plane failure contract — what a control-plane outage must not stop (application traffic, RLS, capability enforcement, revocation, workers, backups, WAL, audit) and what it may pause (invitations, project creation, central lifecycle actions, support grants). | **Vacuously satisfied**: there is no control plane (D1517), and the list of what must keep working is the list of what runs — every item on it is a per-project container on the host with no dependency off it except the secret provider at deploy time (D976, D990) and R2 at backup time. | **Recorded so nobody builds a contract for an absent thing.** If a Stage 5 reading adds a control plane, §18 becomes its first requirement and the current tree is the control. | A contract stating that the appliance keeps working when a thing that does not exist is down is the shape D1062 refused for the coordinator. | — |
| **D1535** | §11.1–§11.2: `apg doctor capacity` with findings, observations and recommendations; `apg tune analyze|recommendations|explain|propose` finding expensive queries, sequential scans, index opportunities, N+1, bloat, plan regressions; *"recommend automatically; mutate through reviewed normal change paths."* | **No `pg_stat_statements`** (0 hits; not in `shared_preload_libraries`), no advisor, no query statistics reader. `apg doctor` is eleven checks with three outcomes each (ADR 0195). | **`apg doctor capacity` is Session 31's READING** (D1520) and reports what it measured with no recommendation. **`apg tune` is not built.** A recommendation that becomes a proposal presupposes 35's record and a statistics extension nobody has decided to load; both are ADRs for a later stage if a reading in 31 ever shows a query-shaped problem. | A recommendation with a confidence field (§11.1's example says *"confidence: high"*) is a value that looks measured; the tree's rule is that a report says what it read. | 0195 |
| **D1536** | Housekeeping, found by this audit rather than looked for. | `docs/project-isolation.md` says the matrix is *"fifteen parsed semantic fields plus all thirteen derived role names"*; `evidence.ISOLATED_FIELDS` (`evidence.py:37-68`) is **18 JSON pointers**. `docs/capacity-envelope.md:145-147` says *"31 released"* migrations; the tree carries **33**. `docs/threat-model.md` has no row for the worker Stage 4 adds (D1527's subject, not a defect today). | **Corrected in Session 30's documentation commit**, the way D1086 was in Session 20's. | The direction nobody chases (D954): a number in prose that a program stopped agreeing with. | — |

---

## 2. The four decisions CLAUDE.md §4 requires

### 2.1 What is the new body of work for?

**The appliance made durable and governed on one node. Still not a control
plane.**

The specification asks Stage 4 to change *"the trust boundary and operating
model"* — to become a hosted platform for invite-only external teams. The
operator decided on 2026-09-18 that it does not, yet. What survives that
decision is the specification's other half, which needs no customer to be
worth building: **the host is a finite resource and the product must say no
when it is full** (31); **an agent's already-governed capabilities can be
composed into a durable, resumable, approvable run without a second
permission model** (32, 33); **the appliance can emit and accept events through
the same governed path** (34); **a consequential change can be bound to the
readings that already exist before it is applied** (35). And before all of it,
the guard the last trip proved it needs and the rotation it has owed since
Session 15 (30).

**What survives either reading of Stage 5** — hosted or not — is the invariant
Stage 3 wrote for its clients, extended one step: *the DX layer holds nothing
the human does not hold*, and now **a workflow, a connector and a worker hold
nothing an agent identity does not hold.** A worker that could reach a base
table, a connector that could gain a scope its profile does not narrow to, or
a step that skipped the audit would each become an authority the moment the
deployment was somebody else's — which is exactly when it would be found.

**The decision this stage plan takes and records rather than hides**: the
public endpoint is not opened (D1518, ADR 0216) and the hosted trust model is
not built (D1517). §6 prices what a Stage 5 reading pays to reverse either.

### 2.2 Does `CURRENT_SESSION` move, and to what?

**Yes, six times: 28 → 30 → 31 → 32 → 33 → 34 → 35.** Session 29 is skipped
(D1514) and nothing is renumbered.

Moving it stays **all-or-nothing** (D690), so every session's requirements
arrive with their proofs in the commit that moves the constant, and a
session's registry additions are decided before its first run (§11).

**`template_version` moves with it, one minor per session — unless a session's
own `upgrade plan` prices its change at major** (D1081's rule, kept). The
candidates: Session 31 adds a `host.yaml` field (migratable, a minor); Session
32 adds `app_private` tables (`migration_added`, a minor) and possibly a
container (a new deployed-document field with a migrator,
`document_schema_migratable`, a minor — but a worker that needs a new secret
with no default is `secret_required_added`, a major, which is why 32's first
measurement decides where the worker lives); Session 34 adds a route (a
deployed-document field, migratable). `compatibility.CHANGE_CLASSES` raises on
an unclassified change, so the class is **read from the plan's output at each
session's close and never chosen** (D704). If none prices at major, Stage 4
closes at `1.13.0`; if one does, at `2.x`.

### 2.3 Which open items are actually open?

Ledger §22, the decision report §4, Session 29's §10 and CLAUDE.md §9, re-read
against the tree at `de9ecbb`:

| Item | Verdict |
|---|---|
| **D1504/D1505 — the guard on one of fourteen callers** | **Open. Session 30, first.** |
| **D1512 — the B2 mirror** | **Open and live. Session 30's first host act.** |
| **D1513 — `release-reading` takes no ref** | **Open. Session 30.** |
| **D1359's line — the truncating `>`** | **Open in two files. Session 30.** |
| **D1509 — a shadowing local** | **Open. Session 30.** |
| **The `studio_*` orphan proof** | **Open. Session 30.** |
| **D860 — the rotation performed** | **Open. Session 30's own sitting**, closing no claim by itself (D1469) and saying so. |
| **D1248 — `/admin/audit` filters** | **Open. Session 33**, because the provenance reader needs a window, an outcome filter and a cursor over the audit. |
| **D1375 — `op` cannot reach the Docker socket** | **Open by decision** (D1493). The host writes no offline half; the workstation's is merged. Unchanged. |
| **`documented_path` failed** | **Open until a person walks it. Session 35 arranges the walk**; nothing closes it by the author's hand (§4). |
| **`replacement_host_restore`** | **Open by decision** (D1028). Unchanged. |
| **D1045 — the provider's error body** | **Open, the owner's.** Not assigned. |
| **D380 — `apg-diag` cannot read `auth`, `storage`, `mcp`** | **Open**; Session 30 records it beside D1528. If 34's connector route needs its log readable by the agent account, 34 widens the allowlist by one service with a test. |
| **The 21 unclaimed requirements** | **Open**; reportable one declaration at a time (ADR 0202); not retrofitted. |
| **D976, D688, D771, D340, D466, D540, D942, D1203, D1205, D1211** | **Open, each still true, none Stage 4's.** §10. |
| **The Infisical control-plane identity holds org admin** | **Open**; a provider-side change nobody has scoped. |
| **D1536 — two stale counts in prose** | **Open. Session 30's documentation commit.** |

### 2.4 Are the unproved claims in scope?

**One is arranged and none is closed by a session.** `documented_path` is
arranged in Session 35 (D1531). `bootstrap_identity`, `api_authorization` and
`credential_rotation_planes` need four rotations; Session 30 performs one and
the plan says which node id it moves and which eight it does not. **A session
that reports them as moved after one rotation is the failure mode §7 names.**
`deployment_convergence` needs a redeploy declared with `--redeploy-before-
file`, which any Stage 4 trip that redeploys can declare — Session 31's is the
first candidate. `replacement_host_restore` stays by decision.

---

## 3. Release structure — six sessions, not twenty-four

| Stage 4 session | Absorbs spec sessions | Shape |
|---|---|---|
| **30 — Inheritance, the rotation, and the two decisions** | 49 (as ADRs 0216 and 0217), 60's answer (D1528), the seven carried-in items (D1532), the rotation sitting (D1533), D1536 | The B2 mirror diagnosed; the shared exec helper and the guard on all fourteen callers; the compile line; `release-reading --ref`; the shadowing lint; the orphan proof registered; two ADRs; **two trips on two sheets on two days**: the deploy-and-sweep, then the rotation |
| **31 — The node as a finite resource** | 53, 54, 55, 56, 69, §16 metering, 71's resource scenario | `host.yaml` `capacity` declared and MEASURED; admission at `deploy`; `pids_limit` and `cpus` on every service; the collector and Prometheus bounded and read for the first time; `apg doctor capacity|usage`; rehearsal `admission-refused`; ends on a host with a refused third project as the live proof |
| **32 — The durable step substrate and workflow execution** | 61, 62, §19's state proof | Where the worker lives, measured; the tables and their SECURITY DEFINER access; a definition compiled from the lock; `apg workflow init|validate|dry-run|run|status|cancel`; retry, idempotency per step, re-minted tokens, budgets as the owning agent; rehearsal `worker-restart`; a restore-test row; ends on a host |
| **33 — Gates, compensation and provenance** | 63, 64, D1248 | `approval` and `wait` steps; `apg workflow approve|reject` under a new scope; compensation on failure and cancel; `apg workflow inspect` from the audit (the audit filters built here); harness cases for workflows; ends on a host for the approval round trip |
| **34 — Governed connectivity** | 65, 66, 67 | `THR-*` rows first; the release-owned outbox and `api.emit_event`; outbound delivery by the worker with dead-letter visibility; `POST /connectors/<name>` as a connector identity; event → run; the interval table; `apg connector init|validate|status|enable|disable`; rehearsal `delivery-retry-storm`; ends on a host |
| **35 — Change governance, hardening, and the Stage 4 release** | 68, 70 (measured, not built), 71, 72 | `apg migrate propose|approve` records and the destructive lint; the noisy-neighbour measurement both ways; deploy downtime per service class; documentation converged; **the third reader arranged**; the bump; `session-35-check.sh` derived from 28's; `docs/stage-5-decision-report.md` from the evidence document |
| *(deferred with hosting, by decision)* | 50, 51, 52, 57, 58, 59, 60 | §6 |
| *(cut, with the reason in §1)* | 70's candidate stack (D1524), §7.4's shedding classes (D1520), `apg tune` (D1535), §13–§14's technologies (D1530), §18 (D1534) | — |

**Three orderings are forced and the rest is preference.**

1. **30 before everything.** The helper and guard before any session routinely
   execs into a container; the rotation before a fourth verifier-shaped thing
   (a worker) is added; the two ADRs before any code that would want a port.
2. **31 before 32.** The worker's memory and connection claim must be charged
   against a declared capacity, or it is the seventh claimant nobody summed.
3. **32 before 33 and 34.** Both consume the substrate.

**33 and 34 are independent of each other** and could swap; 33 is placed first
because 34's event-triggered run needs a `wait` step to resume.

**The count, honestly:** the specification's twenty-four is Stage 1's shape
borrowed a fourth time. Seven of its sessions are deferred with a product
decision the operator took rather than a measurement this plan made; five are
cut because they build a mechanism the tree refuses or a policy with no subject;
four are gates, scenarios or readings that already run or that each building
session owes; and the remaining eight collapse onto one substrate, one
capacity model and one record. Six is what is left, and it is also the count
Stages 2 and 3 arrived at from the same method.

---

## 4. What is not a session

| Spec session or section | What it is here | Arranged where |
|---|---|---|
| **49** — threat model and product contract | Two ADRs (0216 the endpoint, 0217 the boundary) and a `THR-*` row per plane (D1527) | Session 30; then each building session's first run |
| **53** — capacity model | A `host.yaml` field and a reader (D1520) | Session 31, one run |
| **54** — container isolation | Compose lines from `config.py` defaults (D1520) | Session 31, one run |
| **60** — support grants | Deferred; `apg-diag` recorded (D1528) | §6 |
| **70** — reduced-downtime upgrade | A measurement into the envelope (D1524) | Session 35, one run |
| **71** — failure injection | A scenario per building session (D1525) | 31, 32, 34 |
| **72** — the pilot team | The third reader, a person (D1531) | Session 35 arranges; nobody closes |
| **§11.2** — `apg tune` | A reading with no recommendation (D1535) | Session 31's `doctor capacity` |
| **§18** — control-plane failure contract | Nothing (D1534) | — |

**A declaration may not be closed by the author.** The third walk must be by a
person who did not build Sessions 30–34, holding only the release and the task
statement, and the record must be handed to the gate as `APG_DX_RECORD_FILE`
and read by `apg dx-record check`. A shorter finding list is not a pass.

**A caution about the rotation and the trio of claims.** Performing the signing
-key cutover moves one node id of nine (D1469). The sheet for Session 30 says
so at the top, and the session's §7 reports the three claims as `not_run` with
the remaining rotations named. A trip that performs one rotation and reports
three claims moved is the class §7 of CLAUDE.md names, in the evidence model.

---

## 5. The six sessions

Each gets its own plan. What follows is the sentence each plan starts from,
what it must not do, what it measures, and where its exit criteria come from.
**Requirement id families are proposed, not fixed** — each session's own §2
settles them (D691). **Every path, flag and exit code below is what the tree
has today; a session plan re-measures each before depending on it** (§11).

### Session 30 — Inheritance, the rotation, and the two decisions

**Builds.** In this order. **(a)** The B2 mirror diagnosed with root
(`journalctl -u agentic-postgres-backup-mirror@alpha-dev`, the `mc` error
inside `services/backup-mirror/mirror.sh`'s `copy`, the B2 key pair's validity
at the provider) — a repair if it is ours, a row if it is the provider's.
**(b)** A shared container-exec helper: `src/agentic_postgres/container_exec.py`
(one function that builds the `docker exec` argv, applies the D972 guard —
`[ -t 0 ] && { [ ! -t 1 ] || [ ! -t 2 ]; }` moved, not retyped — and refuses
with the message `deploy.sh:260` prints today) and one sourced shell function
under `bin/lib/` for the three `.sh` callers; **every one of the fourteen
callers D1504 names is routed through it**, and the proof is a test that greps
`bin/` and `src/` for a `docker exec` argv built anywhere else and finds none.
**(c)** The compile line in `docs/new-team-member.md:272-273` and
`README.md:551-552`: `bin/mcp-contract.sh compile --output PATH` (the command
writes the file after it succeeds and refuses before touching it), and the
documentation tests that read those pages. **(d)** `apg release-reading --ref
REF` (default `HEAD`), reading the tag target the way D1425 puts it.
**(e)** A contract test over `tests/` that fails on a local binding that
shadows a module-level function imported in the same module (D1509's shape;
`tests/deployment/test_session9_agent_writes.py` is the first case it must
catch, with a control that a differently-named local passes). **(f)** The
orphan proof `test_the_query_view_shows_the_human_their_own_rows_and_not_
anothers` given a fixture that creates a stranger with a non-empty, disjoint
scope set, and registered to `studio_surface` in `tests/acceptance-registry.yaml`.
**(g)** ADR 0216 (no public endpoint in Stage 4; the seam kept; the
preconditions listed) and ADR 0217 (Stage 4's boundary: nothing built in
Sessions 31–35 may require a hosted trust model to be safe; the sibling
invariant of §2.1). **(h)** D1536's two counts. **Then two sittings on two
sheets on two days**: the deploy and one sweep (`deployment_convergence`
declared if the deploy is a redeploy); and **the rotation**, Appendix R of the
Session 28 plan verbatim, alpha then beta.

**Already true, so do not rebuild it.** `deploy.sh:260`'s guard text; `bin/
rotate-signing-key.sh` and its five steps; ADR 0215's reader; the 930 s
deadline; `release-reading`'s eleven facts.

**Must not.** Retype the guard. Leave a caller outside the helper because it
is "only a read" — the seven-minute hang was a read. Bundle any of the other
three rotations onto the rotation sheet (D1510). Run a sweep between `promote`
and `retire`. Report the rotation trio as moved. Open a port.

**Measures.** In a rig with a control before (b): the mixed shape hanging
through the helper's refusal path versus a fully detached invocation
completing (the control). On the host: the mirror's actual error text; the
rotation's `acknowledge` reading three verifiers by pid.

**Closes.** D1504, D1505, D1512 (or records its owner), D1513, D1359's line,
D1509, the orphan, D1536, D1084 (as a decision), D860 (as *performed once*).

**Proposed families.** `OPS-*` extended, `REL-*` extended, `STU-*` extended.

### Session 31 — The node as a finite resource

**Builds.** `host.yaml` schema 3 with a `capacity` object — `memory_mb`,
`disk_gb`, `reserve_memory_mb`, `reserve_disk_gb` — migratable from schema 2
with defaults equal to today's prose (3814 MiB, no swap; the disk from `df`
at first read). A reader in `src/agentic_postgres/capacity_reading.py` that
MEASURES `/proc/meminfo`, `df` at the Docker root and at each project's PGDATA,
the sum of every deployed project's `mem_limit`s from their documents, and the
sum of `max_connections` claims — three outcomes each, `unknown` reported when
a read fails (ADR 0195). **Admission**: `deploy.sh` for a project whose
document does not yet exist refuses when `Σ mem_limits + this project's +
reserve_memory_mb > memory_mb` or the disk equivalent, printing the
specification §7.3's shape (current, reserved, committed, requested, safe
available, suggested action) and exiting with a new code the CLI contract
names. `pids_limit` and `cpus` on every service, defaults in `config.py`
beside the memory defaults and rendered like `mem_limit`. The collector and
Prometheus: `pids_limit`, a `project` label on every scraped series, the 14 d
retention asserted by a test, `mcp_metrics.configure()` called from the
service's startup so the two instruments exist. `apg doctor capacity` (the
readings above) and `apg doctor usage` (D1526's list per project, from the
collector's Traefik scrape for request counts). Rehearsal `admission-refused`.
The envelope gains the readings' cost. **Ends on a host**: a third project's
manifest rendered against the declared capacity and refused (the live proof),
`doctor capacity|usage` read on both projects, and the first Prometheus
query anyone has ever run on this deployment.

**Already true, so do not rebuild it.** The memory and connection budgets in
`config.py`; the doctor's `disk headroom`; the collector's `memory_limiter`;
the closed label set in `mcp_metrics.py`.

**Must not.** Let a capacity READING refuse anything — admission decides,
the reading reports. Publish Prometheus on a route (it stays unrouted; the
doctor reads it over the internal network). Add a label that is a caller
value, a URL or a key (the canary). Raise the 1600 MiB guardrail to fit a
third project. Read host RAM from prose.

**Measures.** In a rig with a control: a rendered third project against a
declared capacity that cannot hold it, refused (control: one that can,
admitted); `pids_limit` on the auth container measured by forking past it in
a throwaway container (control: the same fork under no limit). On the host:
`free -m` against the reader's number; `df` against the reader's.

**Closes.** D1520, D1519, D1526, D1535 (as a reading), 71's resource scenario.

**Proposed family.** `NODE-*`, `OPS-*` extended.

### Session 32 — The durable step substrate and workflow execution

**Builds.** **First measurement**: the worker as a loop inside the `auth`
process versus a new `worker` container — memory (against 31's declaration),
a connection claim (a seventh claimant on `max_connections`, summed), and
whether a new container needs a secret with no default (which prices the
session at major, §2.2); the rig decides and the ADR records. Migration 0034:
`app_private.workflow_definition`, `workflow_run`, `workflow_step` with FORCE
RLS and SECURITY DEFINER functions (`workflow_claim_step`, `workflow_finish_
step`, `workflow_park`) granted to the worker's role only, copying
`storage_cleanup.py`'s lease discipline (a monotonic deadline inside the
lease, a margin derived from the tool timeout, claim-then-act-then-finish so
a step is at-least-once and its idempotency key makes it exactly-once at the
upstream). A definition: `projects/<slug>/workflows/<name>.yaml` naming steps
as `tool@capability_version` from the project's lock, with `retry: {max,
backoff_seconds}` and `timeout_seconds`, compiled and validated against the
lock the way `mcp-contract.sh` validates a manifest (a tool the lock does not
compile is refused at `validate`). `apg workflow init|validate|dry-run|run|
status|cancel`: `dry-run` runs every step under ADR 0182; `run` enqueues as
the invoking agent identity; the worker re-mints the agent's token per step
through `/auth/agent-token` so revocation lands at the next boundary by the
existing path; budgets are consumed as that agent. Rehearsal `worker-restart`
(a run parked mid-step survives the worker's death and resumes exactly once,
proved by the idempotency table). A restore-test row (D1529). `THR-WORKER`.
**Ends on a host**: a three-step run over the example project's tools, the
worker killed between steps two and three, resumed, and the audit correlated.

**Already true, so do not rebuild it.** The write path and its order; the
idempotency header; `agent_audit_begin`'s grant shape; the harness's derived
cases (a workflow step over a tool is that tool's cases).

**Must not.** Give the worker a credential beyond its own role and the
agent's short-lived token. Let a step name anything but a lock tool. Cache a
token across steps. Write step state anywhere but `app_private` through the
functions. Build `pause|resume` (a parked step is a pause). Build a second
retry loop in the upstream client.

**Measures.** The rig above with both worker placements; a step replayed
after a crash refused with `PT412` through the worker (control: a fresh key
accepted); a revoked agent's run stopping at the next boundary with
`scope_not_held` audited (control: an unrevoked one completing).

**Closes.** D1516, D1521's first half, 61, 62.

**Proposed family.** `WF-*`.

### Session 33 — Gates, compensation and provenance

**Builds.** Two step kinds: `approval` (the run parks with `approval_required`
in the audit; `apg workflow approve|reject RUN --confirm RUN` by a human whose
token holds a new scope `workflow_approve`, recorded as the second principal's
audit row; a rejection is a cancel) and `wait` (parked until an event named
by 34 arrives or `timeout_seconds` elapses). Compensation: a step may declare
`compensation: tool@version`, run by the worker in reverse order for every
succeeded step when a later step fails terminally or the run is cancelled, as
the same agent, audited as `compensation` — never a rollback of the outside
world, and the definition's `validate` refuses a compensation the lock does not
compile. `apg workflow inspect RUN`: who started it, the agent, the definition
digest, each step's tool and capability version, the lock digest the worker
loaded, the profile, each approval's principal, each idempotency key, each
denial's boundary, budgets consumed, whether compensation ran — **read from
`agent_audit` correlated by run id**, which is why this session builds
**D1248's audit filters** (a time window, an outcome/boundary filter, a
cursor: one migration over 0032's reader and one change to `GET
/admin/audit`, exposed through Studio's existing `audit` forwarder as well).
Harness cases for workflows (a step whose scope the agent no longer holds; a
replayed approval; a compensation named for a tool that is not a write).
`THR-APPROVAL`. **Ends on a host**: an approval round trip by a second user
on alpha, and the provenance read back complete.

**Already true, so do not rebuild it.** The `approval_required` boundary and
`requires_approval` field; `authz_version`; Studio's audit view; the harness.

**Must not.** Let approval be granted by the agent that requested it. Add a
notification plane beyond the parked state (a human polls `status`; ADR 0195
says what it reports). Promise rollback. Widen a profile to run a
compensation. Summarise the provenance.

**Measures.** A rig with a control: an approval by a token without the scope
refused and audited (control: with it, the run resumes); a cursor over 1,000
audit rows returning every row exactly once (control: the unfiltered read's
count).

**Closes.** D1521's second half, D1248, 63, 64.

**Proposed family.** `WF-*` extended, `AGT-*` extended.

### Session 34 — Governed connectivity

**Builds.** **First run: the `THR-*` rows** (connector input, webhook replay,
delivery). Migration 0035: `app_private.outbox` and `api.emit_event(name,
version, payload)` (SECURITY DEFINER, writing the caller's row inside the
caller's transaction, granted to the request roles like the audit functions);
`app_private.connector` and `app_private.delivery` records. A project's
reviewed RPC calls `api.emit_event` — measured first in a rig that the lint
still refuses a project migration naming `app_private` (the control) while
one calling `api.emit_event` passes. Outbound: a connector of kind
`outbound-webhook` declared in `projects/<slug>/connectors/<name>.yaml`
(event, URL, a secret name the deploy materialises), delivered by the worker
with an HMAC over the body, at-least-once, `retry: {max, backoff_seconds}`,
a dead letter after `max` visible in `apg connector status` with the last
error and no payload. Inbound: `POST /connectors/<name>` on the auth service
behind the project's router — signature over a shared secret, a replay window
keyed on the delivery id, JSON-schema validation from the connector's file,
then exactly one allowlisted tool invoked as the connector's agent identity
(created like any agent, under a profile that names one tool). Event →
workflow start (a `wait` step in 33 resumes on `name@version`). Scheduled: a
connector of kind `scheduled` with an interval, run by the worker's interval
table, invoking one tool. `apg connector init|validate|status|enable|
disable`. Rehearsal `delivery-retry-storm`. A restore-test row for an
undelivered event. **Ends on a host**: an inbound request signed correctly
creating a task on the example project, one signed wrong refused and audited,
one outbound delivery to a sink and one dead-lettered.

**Already true, so do not rebuild it.** Agent identities and profiles;
the worker (32); the write path; Traefik's per-project routers.

**Must not.** Write the outbox from a trigger on a base table. Expose WAL or
a change feed. Give a connector identity more than one tool or any scope its
profile does not narrow to. Log a payload, a URL or a secret in the delivery
record (the canary). Accept an inbound body before the signature is checked.
Use `pg_cron`.

**Measures.** The lint rig above; a replayed inbound delivery refused
(control: a fresh id accepted); an outbound endpoint returning 500 producing
exactly `max` attempts with the declared backoff and then a dead letter
(control: a 200 producing one).

**Closes.** D1522, 65, 66, 67.

**Proposed families.** `EVT-*`, `CONN-*`.

### Session 35 — Change governance, hardening, and the Stage 4 release

**Builds.** `apg migrate propose --project M` writing `projects/<slug>/
proposals/<set-digest>.json` (D1523's readings, including a new destructive
lint that NAMES a `DROP`/`ALTER … TYPE` over a project-owned object) and `apg
migrate approve --project M --proposal DIGEST` writing a second record with
a second username; `migrate --project up` on a host refusing a set whose
proposal is absent or whose digest moved; `approvals_required` in the project
manifest (schema 7, default 0). The same record over `mcp-contract.sh
compile` for a capability change. **The noisy-neighbour measurement**: alpha's
worker at its declared concurrency against beta's REST p95, and the reverse,
into the envelope with the conditions; the deploy's downtime per service class
under ADR 0155 (D1524). Documentation converged: the operator guide gains
sections for capacity, workflows, connectors and proposals; `new-team-member.md`
gains the workflow and connector steps; the generated references rendered for
the example project. **The third reader arranged** — a person, only the
release and the task statement, the record handed to the gate. Then the bump:
`CURRENT_SESSION` 35, `template_version` as `upgrade plan` prices it,
requirements and claims, `session-35-check.sh` derived by diff from 28's,
`scope-closure.md` re-audited row by row, `evidence/session-35.json` from a
host trip, and **`docs/stage-5-decision-report.md`** written from that document
— answering with numbers the question this stage deferred: what a hosted
reading would cost against the capacity, workload and threat readings Stage
4 produced (the specification's §25 gate).

**Already true, so do not rebuild it.** The release machinery; the gate
cadence; `upgrade plan`; `generate --check`; the harness; the envelope.

**Must not.** Close `documented_path` on the author's walk or a shorter list.
Soften a `not_run`. Choose the version by hand. Write the decision report
before the evidence document exists. Build a lock-risk estimate from a guess.

**Measures.** The walk's record; the two envelope rows; every gate in every
mode the evidence needs.

**Closes.** D1523, D1524 (as a measurement), D1531 (if the walk is clean),
68, 70, 71, 72.

**Proposed families.** `GOV-*`, `REL-*` extended, `DX-*` extended.

---

## 6. What Stage 4 does not build

The Stage 1, 2 and 3 non-goals hold unchanged, and `product-contract.md` §5 is
read as written: **no multi-tenant control plane, no hosted console or SaaS,
no autoscaling or scale-to-zero, no branching, no automatic failover, no
arbitrary agent SQL, no general ORM, no cross-project reporting.**

**What the specification asks for and this plan defers or cuts, each with its
row:**

- **The hosted platform** (D1517, D1518, D1528, D1531, D1534): organisations,
  members, roles, invitations, `apg login`, contexts, remote project lifecycle,
  hosted Studio, support grants, a control-plane persistence layer, Next.js,
  Better Auth, passkeys, a public endpoint. **What a Stage 5 reading pays to
  take it up, in order**: the rotation performed (Session 30 pays this); the
  tenancy non-goal changed by an ADR; a registry that is authoritative rather
  than the operator's read (ADR 0185); a threat model for external users
  (§17's list plus *connection-gateway attacks*); TLS for the PostgreSQL
  protocol at the edge or in PgBouncer; a credential that travels and
  therefore rotates on a schedule; the isolation matrix extended to a listener;
  and one ADR superseding 0042, 0043 and 0044 together. **Session 35's
  decision report prices these against measured numbers for the first time.**
- **ClickStack** (D1519) and any second observability store.
- **PostgreSQL 19, `pg_ivm`, `pg_cron`, `pgroll`, `pg_stat_statements`**
  (D1515, D1535).
- **Valkey, ZFS/btrfs, a same-host replica, snapshot branches, local
  inference, an RLS-aware cache, local-first sync, session replay** (D1530).
- **A candidate stack, blue/green or a traffic cutover** (D1524).
- **Load-shedding workload classes** (D1520): the worker's concurrency is the
  knob and there is no other class to shed.
- **`apg tune`** and any recommendation with a confidence field (D1535).
- **Billing** (§16 says so itself), Temporal, Kafka/Redpanda/RabbitMQ/NATS,
  OPA/OpenFGA/Cedar, Kubernetes (§15, agreed).
- **`PolicyProposal`, `WorkflowProposal`, `UpgradeProposal`** (D1523) and a
  lock-risk estimate.
- **A control-plane failure contract** (D1534).

---

## 7. Evidence and claims across Stage 4

**Unchanged, and none of it is renegotiated.** A claim's verdict is computed
from the acceptance registry's node ids and JUnit results, never hand-entered.
Three statuses (ADR 0163): `failed` means the system is wrong, `not_run` means
the evidence is, both exit 5. Three modes, and an offline claim is declared in
`OFFLINE_CLAIMS`, never inferred (ADR 0202). A skip is not a pass; a `-k` run
writes nothing; each half names the commit it measured; two live halves naming
different commits do not merge (Session 29's rule).

**Which claims each session touches.**

| Session | Touches | Ends on a host? |
|---|---|---|
| 30 | `studio_surface` (the orphan registered); `stage_release`; `deployment_convergence` if the deploy is a redeploy; the rotation trio reported `not_run` with the remaining rotations named | **Yes, twice** — the deploy sweep; the rotation sitting |
| 31 | new `NODE-*` claims (the reader offline-declared; admission live) | **Yes** — the refused third project |
| 32 | new `WF-*` claims (definition compile and dry-run offline-declared under `apg dev`; execution and `worker-restart` live) | **Yes** |
| 33 | `WF-*` extended; `audit_boundary_reported` re-run (the audit reader changed, D942) | **Yes** — the approval round trip |
| 34 | new `EVT-*` / `CONN-*` claims (schema validation offline; the inbound refusal and delivery live) | **Yes** |
| 35 | new `GOV-*` claims; `documented_path`; every Stage 4 claim in every mode | **Yes** — the release trip |

**The five `not_run` and the one `failed`, and what moves each.** The rotation
trio — four rotations; Session 30 performs one and says which node id moved.
`deployment_convergence` — a redeploy declared; Session 30 or 31.
`replacement_host_restore` — by decision, untouched. `documented_path` — a
person's walk with no edit, arranged in 35; anything else keeps it `failed`.

**Three things Stage 4 adds to the model:**

1. **A claim about a worker is a claim about at-least-once plus an idempotent
   upstream**, proved by killing the worker (Session 32's scenario), never by
   reading a status.
2. **A capacity reading and an admission decision are two claims**, one that
   may report `unknown` and one that may only refuse or admit (Session 31).
3. **Every new deployed-document field is classified in the isolation matrix
   in the session that adds it** (D702, D1029): 31's capacity, 32's worker,
   34's connector route — and the trip's gate proves it.

---

## 8. The security invariants Stage 4 may not weaken

Stage 3's table carries forward whole. What is new is that three of the six
sessions build a **second principal** — a worker, an approver, a connector —
and a second principal is the shape most likely to become an authority by
accident.

| Invariant | Control | Where Stage 4 puts it at risk |
|---|---|---|
| PostgreSQL is the final authorization authority | RLS, FORCE, the pre-request hook | The worker's tables (32); the outbox (34) |
| A project's identities are derived once, in `naming` | ADR 0002 | The worker's role, the connector route (32, 34) |
| An agent cannot run SQL | No input accepts one; the compiler cannot emit one | A step (32), a connector (34) — both are lock tools or nothing |
| **A step is a tool call under the same scope check** | The write path's order; the token re-minted per step | The worker (32); compensation (33) |
| **A connector identity only narrows** | ADR 0183; a profile naming one tool | 34 |
| **The outbox is written in the caller's transaction by a reviewed function, never by a trigger on a base table** | `api.emit_event`; the lint | 34 |
| **An inbound request is signature-checked before any database is touched** | The route's order; a test that a bad signature produces no audit row and no connection | 34 |
| **Admission refuses; a capacity reading reports** | ADR 0195's two halves | 31 |
| A revoked token stops on its next request, locally | `agent_claims_are_current`; per-step minting | 32, 33 |
| An unauditable write does not happen | `agent_audit_begin` before the scope check | The worker must not reorder (32) |
| An agent record carries no URL, key, token or caller value | `audit.redact`, the canary | The delivery record (34); provenance (33); Prometheus labels (31) |
| The MCP runtime holds no credential | `FORBIDDEN_VARIABLES` | The worker's environment (32) — the same list applies |
| One service cannot read another's credential | Per-consumer immutable generations | A worker container's generation (32) |
| A restore never overwrites the active volume | The restore path's refusal | Unchanged; the restore-test rows (32, 34) |
| **A workstation holds no production secret** | `connect.sh`, `dev-token.sh` | A connector's shared secret is materialised on the host, never in the file (34) |
| Projects share no project-scoped value | The isolation matrix, 18 pointers | Every new deployed-document field (31, 32, 34) |
| **There is no public Postgres endpoint** | ADR 0042/0044; `publication()` raises; **ADR 0216** | Nothing in Stage 4 may call it |
| A deploy over a broken archiver fails | Step 6c | Unchanged |
| The deploy, the sweep and the tag land on one commit | D1425 | Session 35's release |
| **A report may not substitute an answer for a failure to determine one** | ADR 0195 | Every new reader: capacity (31), `workflow status|inspect` (32, 33), `connector status` (34), the proposal record (35) |

**The last row is the one Stage 4 is most exposed to**, as it was for Stage 3,
because four of the six sessions build readers of durable state that a human
will act on. The voice to copy is `bin/backup.sh`'s timeout message and the
doctor's `pooler could not be asked`.

---

## 9. Risks and stop conditions

**Stop and ask** rather than proceeding, when:

- a workflow step, a compensation or a connector would invoke anything that is
  not a tool the project's lock compiles (32, 33, 34);
- the worker would need a credential beyond its own database role and the
  agent's short-lived token, or would cache a token across steps (32);
- the outbox would be written by a trigger, or a change feed would be exposed
  (34);
- an inbound route would touch the database before the signature check (34);
- admission would degrade a running project instead of refusing a new one, or
  a capacity reading would refuse anything (31);
- a public Postgres port, a published Prometheus route or a non-loopback bind
  would be added for any reason (D1518, ADR 0216);
- a session would want a control plane, an organisation or a login to be a
  client of (D1517);
- a currently-passing test would be weakened to make a new one pass;
- a Stage 1–3 claim goes red and the tidy fix is on the proof's side;
- the rotation sheet would gain a step from another rotation, or a sweep would
  be scheduled inside the 930 s window (30);
- `--render-only` stops working with no host and no root;
- a session's `upgrade plan` prices a change at major for a reason the session
  plan did not name (§2.2).

**The failure mode Stage 4 is most exposed to is new.** Stage 1 kept
producing *a value that looked measured and was not*; Stage 2's was
*re-implementing what existed one layer over*; Stage 3's was *a client that
becomes an authority*. Stage 4 builds **second principals** — a worker that
acts for an agent, an approver who acts on a run, a connector that acts for an
outside system — and its failure mode is **a principal that holds more than
the identity it acts for**: a worker with a superuser socket, an approval
granted by the requester, a connector with a scope its profile did not narrow
to. Every row in §8 marked new is an instance caught at plan time.

---

## 10. Open items carried in

Everything in ledger §22 and CLAUDE.md §9 that §2.3 did not resolve, plus
what Stage 4 creates.

**Carried in and not addressed by Stage 4:** D1045 (the owner's);
`replacement_host_restore` (D1028); D1375 (by decision); the 21 unclaimed
requirements (one declaration at a time); D976 (Infisical's hangs); D688 (no
IPv6 to scan, declared); D771 (the OOM history); D340; D466; D540; D942;
D1203; D1205; D1211; the Infisical control-plane identity's org admin; the
three rotations Session 30 does not perform; `process-max` 1 (D593).

**Carried in and addressed:** D1504/D1505, D1512, D1513, D1359's line, D1509,
the orphan proof, D1536 (30); D860 as *performed once* (30); D1084 as a
decision (30); D1248 (33); `documented_path`'s next reader (35).

**Created by Stage 4, and named here so no session inherits them silently:**

- **A second principal is a second set of scopes to keep honest.** Session 33
  owns `workflow_approve`'s place in the derived vocabulary (ADR 0200) and the
  proof that the requester cannot hold it for its own run.
- **A worker is a seventh claimant on `max_connections` and a new
  `mem_limit`**, and the capacity Session 31 declares must be re-read by 32
  before it is charged.
- **Durable step state is state the DR kit does not carry** — it lives in the
  database and the restore covers it, and Sessions 32 and 34 each owe the
  restore-test row that proves it.
- **A connector's shared secret is a secret with an outside holder**, and its
  rotation is a provider replacement like the other three Session 30 does not
  perform. Session 34 owns saying so in the operator guide.
- **Six more gate scripts**, each derived by diff from the newest and
  registered in `SHELL_COMMANDS` (D1014); the header and usage block rewritten
  whole each time (D1488).
- **The third reader will find what five sessions of new pages did not say**,
  and the repairs will land after the reader has gone (Session 25's D1359
  shape). Session 35 budgets a second reader if the first records more than
  the walk before it did.

---

## 11. How a Stage 4 session is planned

**Yes, each of the six still gets its own plan**, in the seven-section shape
Stage 2's §11 fixed and Stage 3's §11 kept — sections 0, **1**, 2, 4, **5**, 7,
8, 9, 10, appendix — at 400–800 lines, **with the operator's numbered sheet
inside the plan**, op steps and sudo steps separated, one sheet per outcome.

**Before a line of a session plan:**

1. **Read this document's §1 rows for the session and check each premise
   against the tree again.** A row here is a measurement with a date, and
   D954 found two of Stage 2's premises wrong within ten weeks.
2. **Decide the requirement ids** (§2 of the session plan). Moving
   `CURRENT_SESSION` is all-or-nothing (D690).
3. **Decide the trip's shape.** Every Stage 4 session ends on a host and
   Session 30 ends on it twice. A trip is three gates and two repairs; **grep
   the previous trips' *"if something goes wrong"* sections first** (D977).
   The sheet may not hand over a command whose precondition is the previous
   sheet's success (D1510); never pipe, redirect or capture a `sudo` command
   that execs into a container (until 30's helper lands, and through it
   after); the gate reads four renders (D1507); `/tmp` on the host is tmpfs.
4. **List the rigs**, each with its control, before the runs that depend on
   them — and **grep the plans for every third party first**: Docker's
   `pids_limit` semantics in 31, dbmate's behaviour with a second table under
   FORCE RLS in 32, Traefik's per-router middleware order in 34.
5. **Grep every reader** of any definition the session changes (D979): every
   builder of a `docker exec` argv in 30 (fourteen); every reader of
   `HOST_MEMORY_GUARDRAIL_MB` and `mem_limit` in 31; every reader of
   `agent_audit` in 33; every reader of `lint_project_set` in 34.
6. **Write for a cold executor.** The plan is executed by a session that
   starts with nothing but the tree and the plan: every path, flag, fixture,
   helper and exit code by name; every command spelled out; every third-party
   claim measured in Run 1's rig with its control named or marked as the
   measurement that run owes. **When the tree and the plan disagree, the tree
   wins and the disagreement is a divergence row.** A documentation-only push
   reads no CI verdict.

**What is deliberately not simplified**, because it is what caught the
defects rather than what cost the time — Stage 3's six, plus one:

- **§1's six columns.** A row with four columns is a note.
- **The mutation battery** in every run that writes a test: anchors
  pre-flighted and a miss fatal (D269), a control the mutation cannot reach
  (D499), an assertion about *how* each mutation failed (D386), a survivor read
  as evidence.
- **Measuring a third party with a control before writing anything that
  depends on it.**
- **`pytest --setup-plan` before a trip**, with the variables set (D671, D676).
- **ADR 0195 applied to every reader the run writes.**
- **`tests/contract/test_cli_contract.py` in the targeted list of any run that
  adds or removes a `bin/` verb** (D1014), and every guard module whose subject
  the run touched.
- **Every proof registered to a claim, checked by the registry test**, so an
  orphan cannot read as `passed` (the `studio_*` lesson, D1236).

**The gate cadence does not change and is not a save button.** Documentation
only → nothing, and no CI read. Generated artefacts could drift →
`bin/session-01-check.sh` alone. Code → the modules the change touches;
**CI is the full check**, read by the full SHA and the HTTP status, with three
buckets (D1059). Before a host trip, a deploy or a session close → every
applicable gate, once, in every mode the evidence needs.

---

## Appendix — what to consult, and what to measure instead

**Consult, in this order:** this document's §1 and §3. `docs/scope-closure.md`
§22 — what Session 29 closed and what it hands on, with a reason on every row.
`docs/stage-4-decision-report.md` §4–§6 — the three blockers and the hosted
question's evidence. `docs/plans/session-28-implementation-plan.md` Appendix R
and `docs/operator-guide.md` §15 — the rotation sheet Session 30 executes.
`docs/plans/session-29-implementation-plan.md` §5 Runs 7–9 and §10 — what a
trip costs now and the constraints it found. ADR **0195** before writing any
reader; **0181/0182/0183/0184** before touching the agent plane; **0135** for
the SECURITY DEFINER grant shape every new `app_private` table copies;
**0155** for what a deploy recreates; **0190/0193** for what a rehearsal is;
**0206** for how a second migration set is ordered; **0213** for a reading
with no threshold; **0215** for how a container's file is read. The
specification's §2, §7.3 and §8.1 — the three passages this plan adopts as
written — and its §15, §22 and §25, which it agrees with whole.

**Measure instead of consulting**, every time: what a *served* surface says
against what the deployed document recorded (ADR 0158); whether a fixture
shares the code's belief (question 6); whether a reader can say *unknown*
(ADR 0195); what a third party's exit code means when the state is in a field
(D145, D548); whether a proof has ever run and whether it belongs to a claim
(`--setup-plan`, the registry test, a battery); what the host's memory and
disk actually are (Session 31 is the first time a program will read them); and
**what the tree does today**, because every premise in the specification this
plan audited was true of a document written on top of documents, and false of
the tree.

**Before measuring how a third party behaves, `grep` the plans for it.** Nothing
indexes the ~1,530 measured facts by subject; the pointer has to be a `grep`.

**Never write a measurement you did not run** (D267). Every number in this
document was measured on 2026-09-18 at `de9ecbb`, or says whose it is.
