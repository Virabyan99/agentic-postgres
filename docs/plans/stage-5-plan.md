# Stage 5 — plan of record

**This is a stage plan, not a session plan.** It sits above seven session plans
and owns what all of them would otherwise repeat: where Stage 5 starts, what
the Stage 5 specification asks for that this repository already has, refuses
or has decided against, the decisions CLAUDE.md §4 requires a new body of work
to settle, and the open items carried in from thirty-five sessions.

**§1 is the point of this document.** The Stage 5 specification
(`stage-5-consolidated-spec.md`, *"Bonsai Managed Postgres"*) calls itself an
*"aspirational guidance document; not an implementation specification"*, and
its own Appendix D says what to do with it after Stage 4: *"Review every Stage 5
assumption against Stage 4 capacity/security evidence … It should never
override evidence produced by Stages 1–4."* §1 is that review, **measured
against the tree at `42bf306` on 2026-10-03**, not recalled. The specification
was written on top of a Stage 4 that did not happen — it assumes invite-only
organisations, Better Auth, remote `apg`, hosted Studio, support grants,
ClickStack and a public endpoint already exist — and Stage 4 deferred every one
of them (D1517, D1518). So Stage 5 is not a *"skip forward"* from a hosted
platform; **it is the hosted platform and the silhouette at once**, and §3
prices that honestly.

**The operator decided the direction during this audit, on 2026-10-03**, the
same day they accepted the Stage 5 decision report's §6: **build the hosted
product** (D1946). That reverses §6's *"do not start the hosted platform as
Stage 5's first work"* — and it does not discard §6's list: **every one of §6's
four debt items is a precondition the hosted reading has to pay** (Stage 4
plan §6 said so in advance), so they are Session 36's work rather than
Stage 5's whole.

**It builds nothing.** No requirement is registered here, no ADR is written
here, and no code changes because of it. The three ADRs it names are Session
36's first act. Each of the seven sessions gets its own plan, and §11 says what
shape those take.

---

## Status — read this first

```
STAGE 5 IS EXECUTING. SESSION 36 CLOSED 2026-10-04: 1.14.0 deployed, swept,
                merged and TAGGED on 2538ac0 (the deploy, the sweep and the tag
                on one commit, D1425). docs/plans/session-36-implementation-
                plan.md is its record; docs/scope-closure.md §29 what it closed,
                left and hands Session 37. This plan was written 2026-10-03 at
                42bf306.
DIRECTION       HOSTED. The operator's decision of 2026-10-03, taken during this
                audit (D1946). The Stage 5 decision report's §6 order was
                Session 36's PRECONDITIONS, now paid: retention (ADR 0248), the
                three rotations on alpha + a schedule (ADR 0250), D1918 (ADR
                0249), D1581/D1941 measured (Session 36's D2034); D1547 deferred
                (D1990); the edge window untouched by design (D1975).
SESSIONS        36-42 (D1945), seven, numbered on from 35. 36 DONE; NEXT: 37,
                the control plane (/api/v1, orgs, invitations, TOTP, API keys).
CURRENT_SESSION 36. Moves 37 -> 42, all-or-nothing per session (D690).
template_version 1.14.0. host.yaml schema 3. Outputs v19, project manifest 8,
                capability manifest 4, lock 4, project lock 3, api-surface 2.
POSTGRESQL      18.4 STAYS -- the operator, 2026-10-03 (D1947). Measured that
                day on Docker Hub: postgres 19beta4 is the newest 19 tag; no
                19rc, no 19 GA, no pgvector pg19 image.
HOST            THE SAME HETZNER SERVER, TO BE RESCALED IN PLACE (CPU and RAM
                only; D1948 superseded by Session 36's D1991) -- **NOT YET
                RESCALED**: on 2026-10-04 the console had no CX33 in hel1
                (Session 36's D2032). Still CX23: 3,814 MiB, 2 vCPU Skylake,
                38 GB, 62.238.99.122, kernel 7.0.0-34. Every capacity number
                that names 3814 MiB is still current.
CONTROL PLANE   PYTHON, DOGFOODED -- the operator, 2026-10-03 (D1950): the
                control plane is a project the product itself deploys, with
                its own migration set and the existing auth service. No
                Next.js, no Better Auth, one identity system.
ACCOUNTS        INVITE-ONLY -- the operator, 2026-10-03 (D1951). No public signup.
OBSERVABILITY   ClickStack ADDED, bounded, on-host -- the operator, 2026-10-03,
                reversing D1519 for Stage 5 (D1964). The per-project collector
                and Prometheus stay; one source per customer-visible metric.
EVIDENCE        evidence/session-36.json: 206 claims, 204 passed, 1 not_run
                (replacement_host_restore, D1028), 1 failed (documented_path,
                by decision, D1935). port_allocation and the rotation trio
                passed.
ADRs            250, next free 0251.   migrations 39.   requirements 299.
                claims 206, 65 declared offline.
divergences     D1-D1944 in earlier plans; D1945-D1984 here; D1985-D2041 in
                Session 36's. **Next free: D2042.**
```

**Every number in §0 onward was measured on 2026-10-03 at `42bf306`**, or says
whose it is. **The Status block above is re-read at each session's close.** (Re-read and rewritten at Session 36's close, 2026-10-04.)

---

## 0. Where Stage 5 actually starts

Session 35 closed Stage 4 and its decision report (`docs/stage-5-decision-
report.md`) answered the question Stage 4 deferred with numbers: two projects
share one host well and its edge badly; every hosted precondition is unbuilt
except a quarter of the first (one rotation of four); and the appliance carries
an operating debt that grows with every feature (nothing in `app_private`'s
workflow and connector tables is ever pruned). Its §6 recommended paying the
debt first. **The operator accepted §6 and then, reading the Stage 5
specification during this audit, chose to build the hosted product** (D1946).
`docs/scope-closure.md` §28 is the list of what Session 35 left.

**The numbers that shape Stage 5's plan, all measured at `42bf306`:**

- **1,093 tracked files. 175,270 lines under `tests/`** in 313 tracked files
  (229 contract, 49 deployment, 14 fixtures, 7 security, 5 external, 4
  recovery, 2 integration). The Stage 4 audit counted 135,618 at `de9ecbb`,
  so Stage 4 added ~39,650.
- **291 requirements across twenty-five id families** — SEC 37, AGT 34, OPS
  23, WF 20, CFG 16, REC 15, DBX 15, DEP 14, STU 11, STO 11, DX 11, CONN 11, API
  11, NODE 10, GEN 8, REL 7, FLEET 7, DEV 6, IDN 5, GOV 5, TEN 4, EVT 4, EVD 2,
  EVAL 2, CAP 2. 198 claims, 60 declared offline (ADR 0202).
- **127 entries under `bin/`** (79 `*.sh`), thirty-one `session-NN-check.sh`
  gates (01–18, 20–25, 28, 30–35; the newest is 35's, with `--mode
  offline|host|external`), and `bin/apg.sh` as a pure dispatcher: a verb `X`
  is `bin/X.sh`, `deploy` is `./deploy.sh`.
- **Zero lines of organisation, membership, invitation, signup, TOTP, passkey,
  WebAuthn, OAuth, SSO, API key, plan, entitlement, billing, operation record,
  region, branch, sleep, wake, notification or email transport** under
  `services/`, `src/`, `bin/`, `migrations/`, `schemas/` or `compose.yaml`
  (`organization` hits are Infisical's org id; `tenant` means a project's own
  domain, ADR 0198; `region` is the S3 region of R2 and the B2 mirror;
  `branch` is code branches and `oneOf` branches; `sleep` is `time.sleep`).
  No `package.json` carries `next`, `react` or `better-auth`.
- **The auth service serves 28 routes in `auth` mode, 4 in `storage` mode and
  `/mcp` in `mcp` mode** (`services/auth-api/app/main.py:258-335`):
  `/auth/login|refresh|sessions|me|jwks.json|reset-password|agent-token`,
  `/admin/users|agents|audit`, `/admin/workflows/...`, `/admin/connectors/...`,
  `/workflows/runs...` and the unauthenticated, signature-checked `POST
  /connectors/{name}`. Published under `/api/app`; **no route is under
  `/api/v1`** (the eleven `/api/v1` hits are Infisical's API and Prometheus's
  query path). A person's authority is `app_private.users.scopes text[]` plus
  `authz_version` (`0011:109`); eight administrative scopes
  (`schemas/capabilities.schema.json:244-251`). **Agent tokens live 900 s**
  (`claims.py:84`); an agent secret 90 days by default (`service.py:117-119`);
  a refresh token 30 days; **password reset is an admin-issued token handed
  over out of band** (`routes.py:617-658`) — there is no email transport.
- **There is no public Postgres endpoint and no TLS on the Postgres wire.**
  `runtime_override.publication()` raises (`src/agentic_postgres/
  runtime_override.py:527-547`); the project `compose.yaml` has **zero
  `ports:` keys**; the database joins `internal` and `backup`, PgBouncer
  `internal` only (`internal: true`, `compose.yaml:1813-1817`); `sslmode=
  disable` appears at eight sites; `database.pooled_public` is refused with
  `UNSUPPORTED_PUBLIC_POOL` (`config.py:1354`). A developer reaches a
  transport through `bin/connect.sh`'s SSH local forward to `127.0.0.1`
  (profiles `runtime_direct`, `runtime_pooled`, `migration_direct`; ADR 0043).
  **The shared edge publishes exactly 80 and 443** (`infra/edge/compose.yaml:
  135-137`), runs **Traefik v3.7** (`versions.env:23`) with both the Docker
  provider (labels, `watch: true`) and a file provider watching
  `/etc/traefik/dynamic`, and takes certificates by **ACME HTTP-01** per
  hostname (`infra/edge/traefik.yaml:117-127`). PgBouncer runs `pool_mode =
  transaction` (`rendering.py:925`). `STARTTLS`, `HostSNI` and
  `sslnegotiation` occur in **no** plan or ADR: nothing about Traefik and the
  Postgres protocol has ever been measured here.
- **A project is created by a root operator at a terminal.** `./deploy.sh` →
  `bin/deploy-project.py`, steps 0, 1–7, 6b–6e (`:2238-2815`); step 0 is
  admission, refusing at **exit 12** with the shape *declared / reserved /
  committed / requested / safe available / suggested action*
  (`capacity_reading.py:89`, `:511-520`; `deploy-project.py:2285-2286`).
  Provider resources are made by hand or by `bootstrap-providers`: **nothing
  in the repository creates or deletes a bucket** (ADR 0110), and the Infisical
  control-plane identity's credential is placed by hand and shredded after
  (`/root/.config/agentic-postgres/bootstrap/`). Retirement is
  `bin/project-retire.sh` (ADR 0187: record → down → … → volumes only with
  `--destroy-data`; **never a backup, a bucket, a secret or a DNS record**).
  `project.lifecycle` is `permanent | ephemeral` with `expires_at` *"a fact an
  operator reads … never a trigger"* (ADR 0186).
- **Resources are per service, not per project profile.**
  `SERVICE_RESOURCE_DEFAULTS` (`config.py:686`: postgres pids 128 / cpus 2.0;
  the rest pids 64 / cpus 1.0, postgrest pids 128), `SERVICE_MEMORY_LIMITS_MB`
  (`:721`), `DATABASE_BUDGET_DEFAULTS` (`:218`: `max_connections` 56,
  `memory_limit_mb` 768, `shared_buffers_mb` 128), `HOST_MEMORY_GUARDRAIL_MB =
  1600` (`:646`). A manifest may override database, storage and app memory and
  the pool size; **pids and cpus have no manifest override.** `host.yaml`
  schema 3 declares `memory_mb`, `reserve_memory_mb`, `disk_gb`,
  `reserve_disk_gb`.
- **The old host:** 3,814 MiB RAM, no swap, 2 vCPU; 2,073 MiB available with
  both projects and the edge running; caps summing to 6,432 MiB across three
  compose projects (ceilings, D767); 608 MiB committed of 1,600 claimable (304
  per project). A deploy takes a project's API away 10–17 s by design (D1941);
  recreating the edge takes both away 24.4 s; a database restart 3.1 s at REST;
  one project's saturated REST moves the other's p95 from ~54 to ~100 ms
  (`capacity.ENVELOPE`, 33 rows, Session 35's twelve at `:602`).
- **What exists that a branch, a restore point and an export would start
  from.** `bin/restore-test.sh` restores a project's stanza **at a target time**
  (`--type=time --target=… --target-action=promote`,
  `restore_drill.py:481-500`) into a **new** volume `apg-<key>-restore-<id>`
  named by `naming.restore_drill_names` (`naming.py:794`), with archiving off,
  and removes everything it made (ADR 0151). `bin/restore.sh --from
  primary|mirror (--latest | --target-time)` restores into the project's OWN,
  unmounted, empty volume on a replacement host (ADR 0189/0192). `bin/dr-kit.sh
  export` carries manifests, the deployed document and secret NAMES, no data.
  **`pg_dump` has no product caller.** pgBackRest keeps `repo1-retention-full`
  2 (default) with fulls `Sun 02:00`, incrementals daily `03:30`, `archive_
  timeout` 60 s, a B2 mirror daily `04:30`.
- **What exists that Query Insights, monitoring and usage would start from.**
  No `pg_stat_statements`, no `shared_preload_libraries` (0 hits; every
  setting is a `-c` flag at `compose.yaml:223-267`). `doctor usage` reads
  eight figures (`doctor.py:1076-1123`): `database_bytes`, `pgdata_kb`,
  `wal_kb`, `repository_bytes`, `audit_rows`, `idempotency_rows`,
  `requests_total` (Traefik), `tool_calls_total`. One collector and one
  Prometheus per project, metrics only, no off-host export; six alert rules;
  no Postgres exporter. The only quota is the per-agent windowed call quota
  (`0028`); the five agent budgets are per call or per process.
- **The record nobody prunes.** 26 `app_private` tables; **two** have prune
  functions (`agent_audit_prune`, `agent_idempotency_prune`, `0033`, granted
  to nobody, ADR 0213) and **no `bin/` verb calls either**. The ten workflow and
  connector tables (0034–0036) have **no `ON DELETE` on any foreign key**
  (`0034:39`: *"No trigger, no schedule, no ON DELETE"*); beta holds 133 runs,
  372 steps, 327 attempts, 29 approvals, 83 revoked probe agents and 7
  `pending` approvals on ended runs (D1886, D1700, D1775).
- **The trust boundary has an expiry date.** ADR 0216's decision is scoped
  *"Through Session 35"* and ADR 0217's *"Sessions 31–35"*; **both lapse with
  Stage 4** and nothing replaces them. `docs/threat-model.md` has 21 `THR-*`
  rows, every one about the operator and their agents, and ADR 0217's third
  commitment forbade any sentence about external users. `docs/product-
  contract.md` §5 (lines 470–481) lists eight non-goals — *"not deferred; they
  are outside the product"* — of which five are exactly what the specification
  builds.

**What Stage 5 has is a specification written on top of a Stage 4
specification**, not on top of Stage 4's tree. Its premises — a hosted Stage 4,
Better Auth, PostgreSQL 19, ClickStack already running, a remote CLI, support
grants, *"the Stage 4 admission controller"*, *"the Stage 4 reviewed change
system"* — are each measured here as absent, present in a different shape, or
decided. **§1's job is the one the Stage 2, 3 and 4 plans named**: the list of
places where the specification asks for something this repository already
has, asks for it in a shape this repository refuses, or asks for something the
operator has now decided to build that needs a decision first.

**Three sentences of the specification are right and load-bearing and this
plan keeps them whole.** *"What is not acceptable is pretending a feature
exists when its semantics do not"* (§1) — the Reality Ledger (D1979) and the
fake-complete guard are its control. *"Two separate reasons may block creation
… these must not be conflated"* (§39) — capacity refuses at exit 12 today and
an entitlement refusal is built beside it, never folded into it (D1954). *"The
product should not quietly gain a universal operator backdoor merely because
it now looks commercial"* (§48) — the control plane holds no credential that
opens a project's data (D1969, §8). **And one sentence is refused**: *"open the
SQL editor"* (§9, §26, §57 step 11) collides with the non-negotiable that a
human runs no SQL through a product surface; the customer's SQL goes through
the customer's own client with the customer's own credential (D1959, D1969).

---

## 1. The divergence table

Six columns, the house shape. Rows are **measured facts about this repository
as it stands at `42bf306`**, not predictions about the sessions. Where a
premise was settled by the operator rather than by measurement, the `Decision`
column says so with the date. The specification is cited by its section
numbers (§N); it has no session numbers.

**Next free number after this table is D1985.**

| # | Spec says | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D1945** | Header: *"Expected delivery envelope: to be determined after Stage 4"*; §60: *"This document intentionally does not freeze a session count."* | Stage 1 was Sessions 1–12, Stage 2 13–18, Stage 3 20–25, Stage 4 30–35; 19, 26–29 registered nothing (`src/agentic_postgres/__init__.py` records the skips). `CURRENT_SESSION = 35` (`__init__.py:834`). Nothing asserts consecutive numbers; the ordinal is the evidence model's key (D705). | **Stage 5 is Sessions 36–42: seven.** No gap: 36 starts the day this plan is accepted. | The count is what §3 arrives at after §1's subtractions, and it is one more than Stages 2–4 because Stage 4 deferred the hosted half this specification assumes was built. | — |
| **D1946** | §0, §2, Appendix D: Stage 5 *"skips forward"* from a hosted Stage 4 (invite-only organisations, remote CLI/Studio, support grants, ClickStack) to *"the complete commercial-service silhouette"*. Appendix D step 2: *"Re-evaluate whether the product is mature enough to justify the Stage 5 skip-forward strategy."* | **Stage 4 built the appliance and deferred hosting by decision** (D1517, D1518; ADR 0216/0217). The Stage 5 decision report's §6 — accepted by the operator on 2026-10-03 — recommended *"do not start the hosted platform as Stage 5's first work"* and listed four debt items. Its §5 priced the hosted preconditions: one of four rotations done; the tenancy non-goal, an authoritative registry, an external threat model, TLS on the wire, a scheduled rotation and an ADR superseding 0042/0043/0044 all unbuilt. | **Build the hosted product. The operator decided this on 2026-10-03, during this plan's audit, reversing §6's first sentence the same day** — recorded, not argued. **§6's four items are kept as Session 36's preconditions** (D1973–D1977), and §5's price list is Session 36's and 37's first runs (D1949, D1950, D1978). | The specification's Appendix D asks exactly this question and the operator answered it. What the evidence said — *"they are not yet something to sell"* — becomes a list of things to make true before the first stranger is invited, not a reason to keep the plan small. | 0216, 0217; **0246** |
| **D1947** | Header and §53: *"PostgreSQL 19+ baseline"*; §9 shows *"PostgreSQL 19"* in the project list. | **18.4** (`versions.env:20`, `pgvector/pgvector:pg18` by digest). **Measured 2026-10-03 on Docker Hub:** `postgres` has `19beta1`…`19beta4` and no `19rc*`, no `19`, no `19.0`; `pgvector/pgvector` has no `pg19` tag (newest `0.8.7-pg18`). pgBackRest pin `2.59.1-1.pgdg12+1`. | **Stage 5 stays on PostgreSQL 18.4 — the operator's decision of 2026-10-03, as for Stages 3 and 4 (D1061, D1515).** The console and the API report the version the cluster reports (`SHOW server_version`), never a literal. | A baseline on a beta is a moving target, and the extension that carries a real workload has no image for it. A move is its own ADR priced by `upgrade plan` when a GA image and a pgvector pg19 image exist. | 0162 |
| **D1948** | Header: *"one sufficiently provisioned OVH Ubuntu VPS"*; §14: profile numbers *"must come from Stage 4 capacity evidence"*. | The host is **3,814 MiB, 2 vCPU, no swap** (`apg-vps-01`, 62.238.99.122), 2,073 MiB available with two projects and the edge, 1,600 MiB claimable by projects of which 608 committed. A replacement host has been built from a kit once (247 s from the mirror, D1028), and `replacement_host_restore` stays `not_run` because *"a rehearsal ends at the restore"*. `port_allocation` waits for a reboot. | **A new, larger VPS — the operator's decision of 2026-10-03. Session 36 moves alpha and beta onto it** with `bin/dr-kit.sh export` → `provision-host.sh` → `bin/restore.sh --from mirror` → deploy (ADR 0189/0192), declares its capacity in `host.yaml`, switches the DNS A records (grey cloud), and re-reads every capacity number. The old host is retired on a later day, after the new one has served (§4). **The size and provider are the operator's**; the plan names no number it has not read. | The specification's profiles, a control plane, ClickStack, a gateway and branches cannot be priced on a host with 992 MiB of claimable headroom left. A move is also the first time the replacement path runs to the end rather than stopping at the restore, which is what `replacement_host_restore` has waited for since D1028; whether its proof's preconditions are met by a move is Session 36's measurement, not this plan's assumption. **Superseded 2026-10-03 by Session 36's D1991: the operator chose to rescale the existing Hetzner server in place, CPU and RAM only — no move, no restore, no DNS change; `replacement_host_restore` stays `not_run` by D1028.** | 0189, 0192, 0221 |
| **D1949** | §1: *"Stage 5 must not short-circuit … authorization; isolation semantics … credential handling … truthful product messaging"*; §11–§12: pooled and direct URLs, a gateway; §10: *"isolated deployment namespace"*. | **The boundary Stage 4 worked inside has lapsed by its own wording**: ADR 0216 (*"Through Session 35, nothing in this product gains a network path to Postgres from off the host"*) and ADR 0217 (*"Nothing built in Sessions 31–35 may require a hosted trust model"*). ADR 0042/0043/0044 (loopback ports keyed by the volume; the SSH forward; *"there is no publication"*) still stand, as does `product-contract.md` §5: a shared multi-tenant control plane, a hosted console or SaaS, scale-to-zero, database branching, automatic failover, agent SQL, a general ORM, cross-project reporting — *"not deferred; outside the product."* | **Session 36 writes ADR 0246 first, before any code**: it supersedes 0042, 0043, 0044, 0216 and 0217 **together** and amends `product-contract.md` §5 under its §7 change control. **Removed:** the control plane, the hosted console. **Narrowed:** scale-to-zero becomes *operator- or customer-triggered sleep that stops containers* (autoscaling and compute/storage separation stay out); branching becomes *a branch restored from backup* (copy-on-write forks stay out); cross-project reporting becomes *the control plane counts its own records and reads each project's readings, never a project's rows*. **Kept whole:** agent SQL, the ORM non-goal, automatic failover and multi-region. ADR 0246 also states Stage 5's boundary sentence (§2.1) and lists the ports the host may publish: 80, 443 and the one Postgres port Session 39 measures. | A boundary that lapses silently is the worst kind: every later session would read 0216 as standing and nothing as forbidding. Superseding all five together is what Stage 4 plan §6 said the hosted reading must do (*"one ADR superseding 0042, 0043 and 0044 together"*); doing it in one document keeps the non-goals and the ports in one place a reviewer reads. | 0042, 0043, 0044, 0216, 0217; **0246** |
| **D1950** | §8: *"Better Auth remains the preferred control-plane identity direction unless Stage 4 evidence changes that decision"*; §53: *"Next.js, Better Auth, organization/member/invitation model, Passkeys/2FA … management API, reconciliation/lifecycle engine … plan/entitlement service, usage aggregation"*. | **No control plane** (D1062, D1517 still true: 0 hits). What exists: a FastAPI auth service with Argon2id credentials, sessions, refresh families (`0023`), scopes with `authz_version`, admin routes, an audit, and three `APP_MODE`s from one image (`main.py:258-335`). **ADR 0185**: *"an operator's read over the host's own documents is not a cross-project catalog"* — the fleet is `bin/fleet.sh` over deployed documents. The tenant extension point lets a project carry its own migration set (ADR 0198) and its own capability manifest (ADR 0201). | **The control plane is a project the product deploys — `control`, permanent — the operator's decision of 2026-10-03.** Its database is an ordinary project database; its tables (organisations, memberships, invitations, API keys, projects, operations, plans, usage, notifications) are its own migration set under `projects/control/`, linted like any set (no `app_private`, FORCE RLS on every `app` table); its accounts are the auth service's users of that project; its management API is a fourth `APP_MODE` (`control`) of the same image. **ADR 0185 is superseded for the control plane by an authoritative registry: the `projects` table**, reconciled against the host's deployed documents by the reconciler (D1953) and reported with three outcomes when they disagree (ADR 0195). Session 37. | Two identity systems (D1517's objection) would give every security question two answers; one stack keeps every Stage 1–4 proof — Argon2id, refresh-family theft detection, `authz_version`, the audit — standing under the control plane for free. Dogfooding also makes the control plane's backups, restore, capacity charge and doctor reading the same as any project's. | 0185, 0198, 0201; ADR needed (37) |
| **D1951** | §8: *"sign up or accept an invitation according to beta policy; create or join an organization; invite teammates; assign organization roles … Privileged organization roles should continue to support stronger authentication such as passkeys or 2FA."* §45: *"in-app and email where appropriate."* | No organisation, membership, invitation, signup, TOTP, passkey, WebAuthn, MFA, OAuth or SSO (0 hits each). **No email transport** (`smtp`, `sendmail`, `mailer`: 0; `email` hits are the ACME contact). Password reset is an admin-issued token handed over out of band. A user has `scopes` and a `role_name`; `project_admin` is the only role with administrative scopes. | **Invite-only — the operator's decision of 2026-10-03.** An invitation is a single-use, expiring token minted by an organisation owner or admin and **shown once to the inviter, who hands it over** (the password-reset shape, `routes.py:617-658`); accepting it creates the account and the membership in one transaction. Organisation roles `owner \| admin \| member \| viewer`, mapped onto control-plane scopes. **TOTP (RFC 6238) is required for `owner` and `admin`**, implemented over the standard library's `hmac` with no new dependency, measured against the RFC's test vectors (control: a wrong-step code refused). **Passkeys and email are `planned` in the Reality Ledger.** Session 37. | An invitation shown once and handed over is the one delivery the tree already trusts for a credential, and it needs no transport whose abuse surface (an open relay, a bounce loop, a spoofed sender) nobody has modelled. Signup abuse, invitation enumeration and email spoofing leave the threat model by the same decision. | 0217's successor (0246); ADR needed (37) |
| **D1952** | §27: *"/api/v1 … Console, CLI, and SDKs should use the same management API … No hidden web-console-only administrative backdoor"*; §29: `apg login`, `apg org`, `apg project create\|list\|use`, `apg db connect\|status`, `apg branch …`, `apg backup status`, `apg restore create`, `apg compute get\|set`, `apg usage`, `apg plan`; §30: scoped management API keys distinct from database credentials; §31: SDKs secondary. | `apg` is a dispatcher over `bin/` (verbs = files; no roster); `APG_PROJECT` is announced when applied. No `apg login`, `org`, `project`, `branch`, `compute`, `usage` or `plan` verb (`project-retire` and `project-runtime` exist). No long-lived management key (`api_key`: one hit, a redaction regex). Four frozen contracts (`contracts/`), a generated TypeScript client from them (ADR 0204). | **One management API under `/api/v1` in the `control` app mode, frozen as a fifth contract** (`contracts/control-openapi.canonical.json`) with a `--check` like `app-contract.sh`'s. **API keys**: `apg_` + 32 random bytes, Argon2id-hashed like an agent secret, shown once, scoped from a closed vocabulary (`projects:read\|write`, `branches:read\|write`, `backups:read`, `restores:write`, `compute:write`, `usage:read`, `members:write`, `keys:write`), owned by a member and revoked with them; **a key authorises control-plane operations only and opens no database.** **The CLI is new `bin/` verbs that are clients of `/api/v1`** — `apg login\|logout\|context` (a context file `~/.config/apg/context.json`, 0600, holding the endpoint and a key reference, never a database credential), `apg org`, `apg project`, `apg branch`, `apg backup`, `apg restore`, `apg compute`, `apg usage`, `apg plan` — each with `--json`; the existing operator verbs stay the operator's. **No management SDK**: `apg generate`'s generator is pointed at the fifth contract only if a session needs it (the spec's §31 agrees). Sessions 37 (API, keys, `login`, `org`, `project list\|use`) and onward (each later session adds its verbs). | The console is the most likely place for a backdoor to grow; making it a static client of a frozen contract the CLI also calls means a capability exists in the console only if it exists in the contract a test reads (ADR 0050's rule, moved up one plane). | 0050, 0204; ADR needed (37) |
| **D1953** | §10: *"Create Project … should create or reconcile"* nineteen things; §28: an `Operation` resource (`pending\|running\|succeeded\|failed\|cancelled`, `progress`); §46: resource states `creating\|ready\|sleeping\|starting\|updating\|restoring\|degraded\|failed\|deleting`; §47: ten domain errors; §10: *"Not a raw Docker error … No resources were created."* | **Every lifecycle act is a root operator at a TTY running a sheet.** Nothing executes an operation, nothing records one (`operation_id` is an OpenAPI operation id). Provider resources are hand-made: a bucket pair, a backup bucket, a B2 mirror bucket and an Infisical project per project (ADR 0110; `bootstrap-providers`); the Infisical control-plane identity holds org admin (an open item) and its credential is shredded after use. Retirement keeps the backups (ADR 0187), so a project key's repository outlives the project. `op` cannot reach the Docker socket (D1375, by decision). | **Three pieces, Session 38.** **(a) Operations** are rows in the control project (`operations`: a closed `type` enum — `project.create\|delete\|sleep\|wake\|resize\|export`, `branch.create\|reset\|delete`, `restore.create`, `credential.rotate`; `status` as the spec's five; `progress`; the requesting member; a typed `arguments` object validated by a JSON Schema per type), created by `/api/v1` and never by the reconciler. **(b) The reconciler** is a root systemd unit on the host (`agentic-postgres-reconciler.service`) that **claims one operation at a time through a definer function reached by `container_exec.run` into the control project's database** — no network listener, no socket shared with the control plane — runs the matching existing `bin/` command with an argv built from the typed arguments (never a shell string), and writes the outcome. **(c) Slots**: a customer project is created into a **slot the operator provisioned in advance** — buckets, mirror bucket, Infisical project and secrets made by the existing bootstrap path under a derived key (`s<n>`), recorded in `host.yaml` — so ADR 0110 stands and the reconciler never holds a provider-administering credential. **A slot is single-use**: its repository is never handed to a second customer (ADR 0187 keeps the backups). Resource states are derived from the operation history plus the deployed document plus the doctor's readings, three outcomes each (ADR 0195). Domain errors are a closed enum in the API's error body. | A reconciler that accepts a closed set of typed operations is the agent plane's lesson applied to root: no input accepts a command (ADR 0050, ADR 0178's named boundaries). Pre-provisioned slots are the bonsai answer to provider automation: the *"No resources were created"* sentence is true by construction when creation consumes nothing at a provider. **Session 38's Run 1 owes the measurement this rests on**: what a deploy of a pre-bootstrapped slot needs from a human today (the Infisical identity, a TTY, a hand-placed file), each named with its file:line. | 0050, 0110, 0187, 0195, 0218; ADR needed (38) |
| **D1954** | §39: *"Plan entitlement check → Project resource profile → Node capacity admission → Provision or refuse … Plan limit reached versus Beta node does not have sufficient safe capacity. These must not be conflated."* | **Capacity admission exists and refuses at exit 12** (ADR 0221/0222), with its shape and suggested action (`capacity_reading.py:94-104`), and `bin/admit.sh` makes the same decision without deploying. **Entitlements do not exist** (0 hits). | **Two refusals, two codes, one order.** The control plane checks the entitlement first and refuses with `plan_limit_reached` (or `branch_limit_reached`) before an operation row exists; the reconciler runs `bin/admit.sh` for the slot's rendered profile and maps exit 12 to `capacity_exhausted` with **"No resources were created"** — true because the slot already existed and nothing was deployed. Neither code may be produced by the other's reader (a test reads both paths with the other held green). Entitlements: Session 41; the capacity mapping: Session 38. | ADR 0195's two halves again: an entitlement is a decision the control plane owns; capacity is a reading the node owns. Folding them would let a plan limit masquerade as a capacity fact, which is exactly the misleading surface the specification forbids. | 0221, 0222; ADR needed (41) |
| **D1955** | §14–§15: profiles `bonsai-nano\|small\|medium` (+`custom` operator-only, `auto` unavailable) with cpu, memory reservation and limit, pooled/direct connections, workflow and worker concurrency, storage reservation; a change *"Project restart required … Do not label this seamless autoscaling."* | Per-service defaults in `config.py` (`:218`, `:686`, `:721`) rendered into `compose.env` (`rendering.py:1816-1840`) and consumed as `${X:?required}`. A manifest overrides database, storage and app memory and `pool_size`; **no pids/cpus override, no named profile.** Admission charges `unreclaimable_mb`, never the caps (D767). Connections are six claimants on `max_connections` 56 (ADR 0070). | **A profile is a named, versioned set of the values a manifest can already carry plus pids and cpus**, in a release file (`src/agentic_postgres/compute_profiles.py`, one table), selected by a manifest field `compute.profile` (project manifest **schema 9**, migratable: absent = today's defaults, which become profile `standard`). **The numbers are derived on the new host in Session 38's Run 1** from `doctor capacity` and the envelope, never copied from the specification's example. A change is the `project.resize` operation: render, `upgrade plan`, admission, deploy — and its message states the measured window for the classes it restarts (the envelope's rows; the database restarts when its memory limit changes). Storage reservation is **not** a profile field: disk is declared per host and nothing enforces a per-project disk quota (no `blkio`, no filesystem quota) — the Ledger says `planned`. Session 38. | The specification's own rule is *"a profile should have real semantics"*: every value in a profile here is a value a deploy already enforces. A storage reservation nothing enforces would be the fake-complete feature §51 forbids. | 0070, 0221, 0222, 0244; ADR needed (38) |
| **D1956** | §16: sleep as `ACTIVE → SUSPENDING → SLEEPING → STARTING → ACTIVE`; *"Suspend when inactive: Never / 5 / 15 / 30 minutes / 1 hour"*; *"A connection attempts to wake the project"*; cold start published. | **Nothing sleeps** (0 hits for suspend/wake/scale-to-zero). `bin/project-runtime.sh down` (`:355-372`) detaches the edge and runs `compose down` without `-v` — volumes kept, containers removed; there is no `stop` path. **Every deploy holds back auth, mcp, postgrest and storage at step 5 and starts them at 6b** (D1941), and why a held-back service is or is not a new container is undetermined (D1581/D1713). `product-contract.md` §5 lists scale-to-zero as a non-goal (narrowed by D1949). | **Sleep and wake are operations** (`project.sleep`, `project.wake`): sleep stops the project's data-plane containers (`docker compose stop`, volumes and containers kept; **what a caller sees while it sleeps is measured in Session 38's rig** — a stopped container's Docker-provider routes disappear, so whether the edge answers `404` or a file-provider fallback can serve a body naming `project_sleeping` is the measurement); wake starts them and waits for the doctor's twelve checks. **Idle sleep** (*"suspend when inactive"*) is a per-project setting the reconciler acts on, reading idleness from the edge's request counter and `pg_stat_activity` — **a trigger, which ADR 0186's *"never a trigger"* rule does not cover because it is a different field; ADR 0246 says so**. **Wake-on-connect is measured, not promised**: Session 39's rig decides whether the gateway can hold a TCP connection while a wake completes; if it cannot, the Ledger says `planned` and the client sees `project_sleeping`. Backups: a sleeping project's archiver is stopped, so its restore point is its sleep time — stated in the Ledger and the API. Session 38 (operations), 39 (wake-on-connect). | Stop/start is the specification's own bonsai and needs no new mechanism; the two things it hides — a backup gap and the wake latency — are exactly what a truthful surface must state. D1581 has to be answered before sleep is built, because a wake that recreates a container is a different promise from one that restarts it. | 0155, 0186, 0246; ADR needed (38) |
| **D1957** | §17: *"Region: Europe — Gravelines, eu-west-bonsai-1 … Additional regions are planned"*; §51: never *"Choose US / EU / APAC"* when they route to one VPS. | No deployment region (the `region` hits are S3 regions for R2 and the mirror; `storage.jurisdiction` and `backup.jurisdiction` take `default \| eu \| fedramp`). | **One region object, declared by the operator in `host.yaml`** (`region: {id, display_name, provider, location}`, host schema 4, migratable), carried into every project's deployed document and the control plane's `regions` table, and read — never typed — by the console and the API. The specification's *"Gravelines"* appears only if the new VPS is there. Session 38. | The region is real exactly when it is the operator's declaration of where the machine is; a literal in the console would be a value that looks measured. | 0221; ADR needed (38) |
| **D1958** | §11–§12: *"Pooled connection postgresql://…@pool.pg.example.com:5432 … Mode Transaction pooling, TLS Required"*; *"Direct connection … may still terminate through a gateway rather than exposing arbitrary container ports"*; the gateway owns endpoint resolution, TLS, wake-on-connect, admission, limits, telemetry. | **No listener, no TLS, no hostname for Postgres** (§0). The edge publishes 80 and 443 and runs Traefik v3.7 with HTTP-01 ACME per hostname. The database's `listen_addresses=*` is reachable only on `internal`/`backup`. **Nothing about Traefik and the Postgres wire protocol has been measured here** (`STARTTLS`, `HostSNI`, `sslnegotiation`: 0 hits in plans and ADRs). Let's Encrypt's per-domain issuance limits have never been read against a per-project certificate. | **The gateway is the existing edge with one more entrypoint, decided by measurement in Session 39's Run 1 rig.** The rig, with controls, owes: (1) whether Traefik v3.7's TCP router can route the Postgres protocol by SNI and terminate TLS for **libpq's default `SSLRequest` negotiation** and for `sslnegotiation=direct`, against `psql` 18, `psycopg`, `node-pg` and Prisma (the four driver fixtures under `services/clients/`, DBX-001..004) — control: a plaintext connection refused; (2) a wrong SNI refused (control: the right one served); (3) whether one 5432 host port can carry both the pooled and direct hostnames (`<key>.pool.<domain>`, `<key>.direct.<domain>`); (4) the certificate path — HTTP-01 per hostname against the issuance limits, versus one wildcard by DNS-01, which puts a DNS-edit token on the host — **a security decision ADR-recorded with the measurement**; (5) wake-on-connect (D1956). **If (1) fails, the gateway is a small TCP proxy of the product's own** and that is priced in the session, not assumed. The pooled endpoint is PgBouncer (`transaction`); the direct endpoint is the database. Session 39. | The specification's own rule is that the abstraction is fixed and the implementation may be simple. The edge is already the one shared, bounded, measured ingress (ADR 0244: 608 MiB, its recreation 24.4 s), and a second ingress would be a second thing to bound, rotate and threat-model. But every third-party claim here is unmeasured, and D267 forbids writing one down. | 0042–0044 (superseded by 0246), 0244; ADR needed (39) |
| **D1959** | §9: *"run `psql` … create data"*; §57 steps 8–13: connect a standard client and Prisma, create tables, *"apply a migration to that branch"*; §11: direct *"for migrations, pg_dump, specialized administration"*. | **No role a customer could hold exists.** The bootstrap plane owns `migration_user` (NOINHERIT, no SUPERUSER, `SET LOCAL ROLE` to the owner, ADR 0028), the authenticator, the service roles and per-role `CONNECTION LIMIT`s summed on `max_connections` 56 (ADR 0070); `connect.sh` reaches them through the host broker. **CLAUDE.md §6: *"A human cannot run SQL through a product surface"*; product-contract §5: no agent SQL under any authentication.** The project's own migration set is linted (no `app_private`, no role/schema/extension DDL, FORCE RLS on every `app` table). | **A customer gets two login roles per project, both new, both SCRAM, both reached only over TLS through the gateway**: `customer_app` (pooled; DML through the reviewed surface's grants) and `customer_admin` (direct; DDL in `app` and in schemas it creates, **never** `app_private`, `api`'s definer internals, `extensions`, roles or `SUPERUSER`), each with a `CONNECTION LIMIT` summed into ADR 0070's budget as two new claimants. Passwords are generated secrets materialised like every other and **shown once through `/api/v1`**, rotated by the `credential.rotate` operation. **The non-negotiable is kept by scoping it**: a *product surface* (console, Studio, `/api/v1`, MCP, a workflow, a connector) runs no SQL; the customer's own client, with the customer's own credential, does — and an agent still runs none. ADR 0246 restates the sentence that way. **The lint stays the rule for the project set the platform applies; a customer's own DDL over `customer_admin` is the customer's.** Session 39. | A managed Postgres the customer cannot run DDL against is not one; giving them `migration_user` would give them the platform's migration ledger. Two roles keep the pooled/direct distinction meaningful (transaction pooling breaks session state, which is what a migration needs) and keep `app_private` — the audit, the workflow record, the identity registry — outside anything a customer credential reaches, which is the one isolation property the agent plane depends on. | 0028, 0070, 0246; ADR needed (39) |
| **D1960** | §13: Connect tabs for Prisma, Drizzle, Kysely, node-postgres, psql, Python, generic; *"Generated snippets should be treated as documentation output from connection metadata rather than hand-maintained text."* | **Four driver-compatibility fixtures exist and run** (`services/clients/psql\|prisma\|node-pg\|psycopg`, DBX-001..004), against the SSH-forwarded endpoint. Drizzle and Kysely: 0 hits. Generated documentation with `--check` is the house shape (`render-mcp-catalog.py`, `render-config.py --bounds-doc`). | **Snippets are rendered from the endpoint metadata `/api/v1` serves**, by one function in `src/agentic_postgres/`, for exactly the clients a fixture proves: psql, Prisma (`DATABASE_URL` pooled + `DIRECT_URL` direct), node-postgres, psycopg — **each fixture re-pointed at the TLS endpoint in Session 39** so a snippet is shown only for a client that has connected through it. Drizzle and Kysely are added only with a fixture each. | A snippet for a client nobody connected is documentation that looks measured. | 0204; ADR 0246 |
| **D1961** | §18–§20: branches as first-class objects — `apg branch create\|list\|inspect\|reset\|promote\|delete`; semantics: a defined source/recovery point, an independent runtime identity, isolation, independent mutation, safe deletion, provenance, capacity accounted, credentials and routing that differ, *"cannot corrupt the parent"*; classes `production\|development\|preview\|temporary`; `main` protected; preview TTL; development branches may sleep. | **No database branch exists** (product-contract §5: *"Database branching or copy-on-write forks"* — narrowed by D1949). **The mechanism nearly does**: `restore-test` restores the project's own stanza at a target time into a new volume with derived names and archiving off, and refuses to touch the live volume (ADR 0151); `restore.sh` restores the latest or a target time from primary or mirror. **Unmeasured and load-bearing: a physical restore carries the parent's `pg_authid`**, so a branch starts with the parent's role passwords and the parent's `app_private` (users, agents, audit). Ephemeral expiry is *"never a trigger"* (ADR 0186). | **A branch is a child deployment of its project**, named by a new `naming.branch_names(key, branch)` with its own stem (ADR 0151's discipline), **restored from the parent's repository at a target time** (default: now) through the restore drill's argv made persistent, **started with archiving off and no backup stanza of its own** (the Ledger: *"a branch is not backed up; `main` is"*), **re-keyed before its endpoint opens** — every login role's password regenerated and every agent and refresh credential revoked inside the branch, measured in Run 1's rig (control: a parent credential refused at the branch, the branch's own accepted). Its data plane is the database and PgBouncer only, plus the two endpoints; **capacity is charged at admission like any deploy**. `main` is the project; `apg branch reset` re-restores; `delete` removes what its names derive and nothing of the parent's. **Branch TTL is a trigger the reconciler acts on** — ADR 0186's rule is kept for projects and superseded for branches only, in the session's ADR. Session 40. | Restore-from-backup is the specification's own *"safest default"* (§23) and the only mechanism in the tree with proofs; a filesystem snapshot gives *"branch from now"* only, not a recovery point (D1980). The re-key is the property the specification names (*"credentials differ"*) and the one a naive restore silently breaks: a branch that answers the parent's password is a second door to the parent's identity registry. | 0151, 0186, 0189; ADR needed (40) |
| **D1962** | §21: promotion as *"an operation with evidence, not a metadata rename"* — checks, backup evidence, write coordination, route cutover, post-cutover verification. | No cutover, no candidate stack, no blue/green: D1524 cut it and measured instead; a deploy's windows are 10–17 s per class. | **Cut. `apg branch promote` is `planned` in the Reality Ledger.** The supported path from a branch to `main` is a migration applied to `main` through the proposal record (ADR 0243), which already binds a change to its readings. | A promotion is a route cutover plus write coordination, and nothing here coordinates writes across two clusters; building it would be D1524's candidate stack under a new name. | 0243 |
| **D1963** | §22–§23: a backups screen (*"Continuous protection Healthy, Last WAL archived 12 seconds ago, Restore window 7 days"*, restore points), actions *"Restore to new branch / Restore project / Test restore / View backup health"*; PITR with *"Replace current branch"* as an option. | The doctor already reads `backup repository` (`backup.sh info --json`), `wal archiver` (`pg_stat_archiver`) and `backup mirror` (stale after 2 days); `repo1-retention-full` 2 with weekly fulls, so the window is the span between the oldest kept full and now, readable from `pgbackrest info`. `restore-test` is the test restore. **An in-place restore exists only for a replacement host** (`restore.py` refuses a mounted volume or one holding a cluster). | **The backups surface is the doctor's three readings served through `/api/v1`, with the restore window computed from `pgbackrest info` — never declared** — and the restore points listed from the same reading. *Restore to new branch* is `branch.create` with a target time (D1961). *Test restore* is a `restore-test` run as an operation. **In-place restore is not a customer action** — `planned` in the Ledger; the operator's replacement-host path is unchanged. Session 40. | Every number on that screen exists today as a reading with three outcomes; the work is serving it, not measuring it. A destructive restore exposed to a customer is the one action whose failure loses the data the product exists to keep, and the specification itself prefers the branch. | 0151, 0192, 0195 |
| **D1964** | §24–§25, §53: *"ClickStack — ClickHouse, HyperDX, OTel ingestion"* as the internal telemetry substrate; *"The customer UI should expose curated metrics, not the full platform observability backend."* | **D1519 refused ClickStack for Stage 4** (the operator, 2026-09-18) and kept the per-project collector + Prometheus, which `doctor usage` now consumes. `clickhouse\|hyperdx`: 0 hits in product dirs. The collector is metrics-only with no off-host export; the `apg.*` INFO lines never reach `docker logs` (D1918). The old host could not have priced ClickHouse; the new one has not been read. | **ClickStack is added — the operator's decision of 2026-10-03, reversing D1519 for Stage 5.** A platform compose project (`apg-telemetry`) with ClickHouse, the HyperDX UI and an OTel gateway, every image pinned by digest, `mem_limit`/`pids_limit`/`cpus` from day one (ADR 0244's rule), ClickHouse TTLs as the retention, **no route and no published port**: the operator reaches HyperDX by the SSH forward (ADR 0043's shape). Each project's collector gains a logs pipeline and an OTLP exporter to the gateway on a dedicated network. **One source per customer-visible metric** (D704): Prometheus keeps what `doctor` reads; ClickStack holds logs, traces and the Query Insights history. Its memory is charged by admission like a project. Session 41. | The operator chose it with the new host in view; the invariant the Stage 4 specification wrote — *"observability may lose optional detail under pressure; it may not destabilise the PostgreSQL workloads it exists to observe"* — becomes ClickStack's caps and its admission charge. Two stores answering the same question would be two answers. | 0164, 0224, 0244; ADR needed (41) |
| **D1965** | §24: Query Insights — top queries by p95, calls, DB time; a finding (*"Repeated sequential scan … Recommendation: Consider compound index"*); *"[Create tuning proposal]"*; *"avoid autonomous production DDL"*; §25 monitoring signals. | No `pg_stat_statements` (D1535 left it for a later stage); no query statistics reader; no Postgres exporter. **The reviewed change system exists**: `bin/migrate.sh propose\|approve` writes the committed proposal records (ADR 0243). | **`pg_stat_statements` is loaded** (`-c shared_preload_libraries=pg_stat_statements`, `CREATE EXTENSION` in `extensions` by the bootstrap plane) — **one database restart per project, scheduled into Session 41's deploy and measured against the envelope's 3.1 s row**. Query Insights is a reading: top N by total time with calls, mean, rows and shared-block reads, **normalised text only**, per project, read through the container the way the doctor reads, sampled into ClickHouse for history. **No recommendation engine**: a finding states the evidence (calls, rows scanned vs returned) and never a confidence; *"Create tuning proposal"* opens `migrate propose` for a migration the customer writes. Monitoring is a curated list of signals that each name the reading they come from. Session 41. | D1535's argument stands: a recommendation with a confidence field is a value that looks measured. The statistics extension is the one thing nobody had decided to load; the operator's ClickStack decision gives it a history store. | 0195, 0243; ADR needed (41) |
| **D1966** | §38: usage — database, backup and branch storage, active and sleeping compute time, API calls, connections, DB execution time, workflow executions, agent calls, provider and embedding usage, egress *"where measurable"*, project and branch counts; *"Usage should drive real entitlement enforcement."* | `doctor usage` reads eight figures per project (§0); `doctor capacity` reads the node; the workflow and connector counts are in `workflow_counts()`. No aggregation over time, no per-organisation total, no egress, provider or embedding meter. | **The reconciler samples each project's readings on an interval into the control project's `usage_samples`** (through the same container reads as the doctor), and `/api/v1/usage` aggregates per project and per organisation. Metered: database and repository bytes, branch count and bytes, active and sleeping seconds (from the operation history), requests, agent calls, workflow executions, connections (`pg_stat_activity`), DB time (`pg_stat_statements`, after 41). **Egress, provider and embedding usage are `not metered` in the Ledger.** Session 41. | Usage that exists is read; usage that cannot be read is said to be unread. A sample per interval is a cumulative-counter question answered as a point in time, which D553 forbids folding, so each sample names its instant. | 0213, 0224; ADR needed (41) |
| **D1967** | §32–§37, §56, Appendix B: Free (active, $0 during beta) and Premium (defined, unavailable, *"Notify me"*); entitlements (`projects_active`, `branches_total`, `compute_profiles`, `storage_gb`, `backup_retention_days`, `workflows_concurrent`, `agent_calls_per_day`); no fake billing. | Nothing (0 hits). The only per-identity limit is the agent windowed quota (`0028`), set per agent by an admin; workflow concurrency is the worker's own knob. | **Plans are a release file** (`src/agentic_postgres/plans.py`: `free` active, `premium` `unavailable_during_beta`), every number **derived from the new host's readings in Session 41**, with an ADR naming each. **Enforced**: `projects_active`, `branches_total`, `compute_profiles` (at the control plane, D1954); `agent_calls_per_day` (as the existing windowed quota written onto each agent the control plane creates). **Read but not enforced**, and labelled so: `storage_gb` (no per-project disk quota exists, D1955). `backup_retention_days` maps to `repo1-retention-full` and is a **planned** Premium difference, not an enforced Free limit. *"Notify me"* writes an interest row. **No checkout, invoice, card form or tax field** — the specification's §37 agreed whole. Session 41. | An entitlement that nothing enforces is the fake-complete feature; one that is enforced by a mechanism that already exists (the quota, admission) is the bonsai. | ADR needed (41) |
| **D1968** | §45: notifications — project ready, restore and branch complete, sleeping/woken, limits approaching, backup unhealthy, approvals requested, API key created, security event; *"in-app and email where appropriate"*. | No notification plane; Stage 4's approvals are polled (`apg workflow approvals`, `GET /admin/workflows/approvals`). No email transport (D1951). | **In-app only**: a `notifications` table in the control project written by the reconciler when an operation ends and by the usage sampler when a limit crosses 80%, listed by `/api/v1/notifications` and the console. **Email is `planned`.** Project-plane events (approvals, backup health) are read from the readings that already state them, not copied. Session 41. | The specification's own *"avoid building a general notification platform"*. | — |
| **D1969** | §26: Studio merged into *"a true database product surface"* with a **SQL** tab, *"RLS and identity aware … should never receive an undisclosed privileged universal database credential"*; §54 navigation (Overview, Connect, Tables, SQL, Branches, Backups, Monitoring, Query Insights, Agents, Workflows, Connectors, Usage, Settings); §41–§43: managed agents, workflows, connectors in the console. | **Studio is local by construction**: binds `127.0.0.1` (`studio.py:100`), forwards seven operations (`surface`, `query`, `me`, `sessions`, `agents`, `audit`, `revoke_agent`), runs no SQL in any form, holds the human's token in memory (ADR 0205). **A project's people and agents are that project's auth-service identities**; a control-plane account is not one. Every admin surface for agents, workflows, connectors and the audit exists as a project route. | **The console is a static web UI served by the control project, calling `/api/v1` only**, with the specification's navigation **minus SQL** — the SQL tab is replaced by the Connect page's direct URL and a `psql` snippet, and the Ledger says *"SQL editor: not available, by decision (ADR 0246)"*. **The control plane holds no credential that opens a project's data or admin plane.** For Tables, Agents, Workflows, Connectors and Audit, the console opens **the project's own Studio forwarders, served behind that project's router as that project's user**: at `project.create` the reconciler bootstraps the creating member as the project's first `project_admin` (the existing `auth-admin.sh bootstrap`) and the one-time secret is shown once to that member. Session 42 (console), 38 (the first admin at creation). | This is the specification's own §48 sentence made structural: a control plane that held a token for every project would be the universal backdoor, and a SQL box would be a product surface that runs SQL. A second login per project is the cost, and it is stated. | 0205, 0246; ADR needed (38, 42) |
| **D1970** | §40–§44: Agentic Postgres as the differentiator — create agents, assign profiles, budgets, audit, revoke, evaluations, denials, usage; workflows with versions, executions, approvals, retries, compensation; connectors as integrations; *"`apg doctor` and the hosted Console should increasingly surface the same evidence."* | **All of it exists per project**: `/admin/agents` (create, rotate, revoke), the five budgets, the audit with nine named boundaries and its cursor, the harness (`EVAL-HARNESS-001`), `apg workflow init\|validate\|run\|dry-run\|status\|cancel\|approvals\|approve\|reject\|inspect`, `apg connector init\|validate\|status\|enable\|disable\|key`, and the doctor's `agent record` and `workflow` checks. | **Nothing new in the plane.** The console reaches these through the project's Studio forwarders (D1969); Studio gains read forwarders for workflows and connectors (`GET /admin/workflows/approvals`, `GET /admin/workflows/runs/{id}`, `GET /admin/connectors`) — its forwarder table grows from seven, with the test that guards it. Session 42. | A second implementation of the agent plane in the control plane would be D704's second axis at the product's differentiator. | 0205, 0226–0239 |
| **D1971** | §48: Help → Documentation, Diagnostics, *"Export support bundle"*, *"Request temporary support access"* — bounded, short-lived, auditable, explicit; §64: never approximate *"support-access limits"*. | **The operator holds root on the one node**; the standing read-only path is `apg-diag` (ADR 0071, widened by ADR 0245) behind one SSH key, with no lifetime (D1528). | **The support bundle is built** (a member's `/api/v1/projects/{id}/diagnostics`: the doctor's twelve readings and the project's operation history, redacted by the canary). **Temporary support grants are not built, and the Ledger says why in the customer's words**: *"the operator of this single node has root on it; support access is not technically bounded in this beta."* The beta terms carry the same sentence. Session 42. | A grant that bounds a support engineer means nothing when the person granting support also holds root; pretending otherwise is the one dishonest sentence a bonsai product can write about trust. | 0071, 0245, 0246 |
| **D1972** | §10/§57 step 30: *"Retire/delete a test project"*; step 28: *"Export project data/configuration"*; §61 items 22–23: deletion/retention policy, data export/portability. | Retirement keeps the backups, the buckets and the secrets (ADR 0187). `pg_dump` has no product caller; `dr-kit export` holds no data. | **`project.delete`** runs `project-retire.sh --destroy-data` against the project's slot and then marks the **slot consumed, never reissued** — its backup repository is kept for the deletion policy's window and then destroyed by the operator (ADR 0187 kept; the window stated in the Ledger and the terms). **`project.export`** runs `pg_dump -Fc` of the customer's schemas (never `app_private`) inside the project's database container through `container_exec.run`, writes the archive into the project's own storage bucket, and returns a presigned URL valid 15 minutes; configuration export is the manifest, the lock and the endpoints, no secret. Session 38. | A reused slot would hand the next customer the last one's encrypted repository and its cipher pass; single use makes that impossible by construction. Export through the project's own bucket keeps the dump inside the project's isolation boundary all the way to the customer. | 0110, 0187; ADR needed (38) |
| **D1973** | §64: *"Never approximate … audit … revocation"*; §61 item 22: retention policy. **Report §6 item 1.** | Two of 26 `app_private` tables can be pruned, by functions granted to nobody, with no `bin/` verb (ADR 0213); the ten Stage 4 tables have no prune and no `ON DELETE`; beta's bill is D1886's numbers; a run pins its agent (D1700); an undecided approval on an ended run stays `pending` (D1775); a dead letter cannot be redelivered (D1798). | **Session 36: the retention plane.** One definer function per table in FK order (attempts → approvals → steps → receipts → runs; deliveries → events; then agents with no run), each taking an operator's horizon and a limit, granted to nobody, ADR 0213's shape; `bin/record.sh prune --project KEY --before ISO --table T [--limit N] --confirm KEY` as root, printing counts before and after; the doctor's `agent record` check widened to every table it can prune; an approval on an ended run moved to a new `cancelled` status by the run's end (D1775). **A hosted project's deletion removes its rows by deleting its database (D1972), so the plane is for the living project's growth.** D1798 (redelivery) stays open. | Every later session writes rows into these tables for strangers; a product that cannot bound its own record is the debt the report named first, and it is cheapest before there are customers. | 0213; **0248** |
| **D1974** | §64: never approximate credential isolation; §28: *"credential rotation"* as an operation. **Report §6 item 2.** | One rotation of four performed (the signing key, 2026-09-19, ADR 0224); the trio (`bootstrap_identity`, `api_authorization`, `credential_rotation_planes`) needs the authenticator password, the docs Basic Auth password and the application credential on both projects (D1469, D1496); `rotate-secret.sh` is a planner and performs none; no schedule exists anywhere (0 hits in code). | **Session 36's second sitting, on the new host, on its own day: the three remaining rotations**, from `rotate-secret.sh`'s plan and the operator guide, one sheet per rotation (D1510) — the first time the trio can move. **A schedule as a reading**: each declared secret gets a `max_age_days` in the secret contract and the doctor reads each secret generation's age with three outcomes; nothing rotates on its own. **A customer's database credentials rotate through `credential.rotate`** (Session 39). | The trio has been `not_run` since Session 5 for want of three acts; a hosted product hands out credentials that travel, and a schedule nobody can read is a schedule nobody keeps. | 0088, 0174, 0224 |
| **D1975** | §12: the gateway *"should eventually own"* routing; *"A future multi-node architecture should be able to replace the gateway internals."* **Report §6 item 3.** | Recreating the shared edge takes **every** project away 24.4 s (bound 27.1); **only a static-config change needs it** — routes arrive through the Docker provider's labels and the file provider's watched directory with no recreation (`infra/edge/traefik.yaml:102-115`; the deploy writes the docs middleware there, `deploy-project.py:2426-2436`). The static config changes on `promote-acme` and on limit changes (ADR 0244). | **No second Traefik.** The move (Session 36) is the edge's one scheduled recreation, carrying the Postgres entrypoint Session 39 needs **only if 39's rig has decided its shape by then**; otherwise 39 pays one recreation, announced. **Session 39 measures, with a control, that creating a project's routers (HTTP and TCP) moves no other project's latency** — the claim a hosted reading needs is that the *frequent* change is free, and the 24.4 s is the *rare* one, stated in the Ledger. | The window that matters to a tenant is the one every project creation would pay; if that is zero, the rare one is a maintenance window, which is what the Ledger says it is. | 0244 |
| **D1976** | §15: *"If Stage 5 requires a restart, say so"*; §16: wake latency published. **Report §6 item 4 (D1581, D1941).** | Every deploy holds back four services and starts them at 6b (D1941); whether a held-back service is a new container, and what moves a secret generation, is undetermined (D1581/D1713). | **Session 36 answers D1581/D1713 with a rig** — two deploys with no change between them, container ids and generation directories read before and after (control: a deploy with a changed mount) — **before Session 38 builds resize and sleep on top of it**, and the resize message quotes the class windows measured. | A restart message that is wrong in either direction is a product error; the number has to be known before it is printed to a customer. | 0155 |
| **D1977** | — (the specification has no row). **Report §6 item 4.** | **D1918**: no handler on `apg.*`, so INFO never reaches `docker logs` (`main.py:391`, `mcp_telemetry.py:46`; uvicorn `--no-access-log`). **D1547**: `api.create_note` and no `delete_note`; sentinel rows are removed by root `psql`. | **Session 36**: one `logging` handler configured in `create_app` for `apg.*` at INFO, JSON lines on stdout, the canary run over a captured line (it becomes ClickStack's log input in 41); `api.delete_note(id)` under the notes grants, owner-only by RLS, with the release's next migration. | Both are certain and small, and both are prerequisites: 41's logs pipeline has nothing to carry without D1918, and the journey's cleanup would otherwise need root. | 0050 |
| **D1978** | §49: the Stage 5 threat model — signup abuse, invitation abuse, API key compromise, organisation privilege escalation, project and branch enumeration, endpoint confusion, gateway attacks, wake-on-connect abuse, creation and branch exhaustion, plan-limit bypass, usage tampering, restore abuse, control/data-plane credential confusion, deletion races, API replay, connector abuse, observability poisoning, support-grant misuse, cross-project leakage, storage exhaustion, ClickStack exhaustion. *"The polished UI must not reduce the rigor of negative testing."* | `docs/threat-model.md`: 21 `THR-*` rows about the operator and their agents; Scope excludes DoS (*"no availability SLA is claimed"*); ADR 0217 commitment 3 forbade external-user sentences (lapsed, D1949). | **Session 36 writes the hosted rows before any code** — one `THR-*` per specification item that survives §1 (signup abuse leaves with invite-only; support-grant misuse becomes D1971's sentence), each naming the session that builds its control and the negative test that proves it — and **every building session adds its own rows in its first run**, Stage 4's discipline (D1527). Scope gains one sentence: denial of service is now in scope for the gateway and the creation paths, as **admission and rate limits, still not an availability SLA**. | The specification's own sentence about negative testing, and the order that caught D868 in Stage 2. | 0246 |
| **D1979** | §6: a persistent beta message; §50: the **Reality Ledger**, *"mandatory"*, updated whenever an implementation changes; §51: every feature `available \| beta \| planned/unavailable`, never *"looks active but does nothing"*; §59: forbidden words unless evidenced (*production-ready, enterprise-grade, highly available, fault tolerant, multi-region, serverless, autoscaling, zero downtime*); Appendix A's template. | Nothing by that name. The nearest: `docs/scope-closure.md` (what each session closed and left), `product-contract.md` §2 (*"none of the elasticity"*), `capacity.ENVELOPE` (measured windows). No document is read by a program to decide what a UI may show. | **`docs/reality-ledger.yaml`** — one entry per product concept, Appendix A's fields plus `status` (`available \| beta \| planned \| not_metered`), `evidence` (a claim name or an envelope row) and `since_session` — rendered to `docs/reality-ledger.md` with `--check`, **served by `/api/v1/ledger` and read by the console**, and guarded: (1) every console control and every `/api/v1` operation type maps to an entry; (2) an entry `planned` has no operation type and no enabled control (the fake-complete guard); (3) the forbidden words appear in no served page, no `docs/` page and no API string except inside the Ledger's own list. **Session 36 writes it with today's truth** (most rows `planned`) and every session moves its rows in the run that builds them. | The Ledger is the control for the class this stage is most exposed to (§9): a surface that claims what the node does not do. Making a program read it is the difference between a document and a control. | **0247** |
| **D1980** | §53 optional/evidence-selected: pgvector, `pg_ivm`, `pg_cron`, Valkey, a local inference sidecar, snapshot-capable storage (ZFS/btrfs), a same-host read replica; `pgroll`; §19's clone candidates. | pgvector runs; the others: 0 hits. D1530 rejected each for Stage 4 *"if evidence ever appears"*. The move (D1948) is the one moment a filesystem choice for the Docker data root is cheap. | **Rejected for Stage 5, in one row**, with one note: **snapshot storage is not taken at the move**, because a snapshot of a live cluster gives a branch *from now* and never from a recovery point, and the restore path already gives both with proofs (D1961). If Session 40's measured branch time is unacceptable, ADR-record the snapshot option against that number then. | *"Do not add merely because it exists"*, again; and the one item with a cheap moment has a measured reason not to be taken at it. | — |
| **D1981** | §9 (*"The First 20 Minutes Must Feel Complete"*), §57 (thirty-one steps), Appendix C (thirty-one checkboxes): *"turn this into executable acceptance tests."* | `documented_path` is `failed` by decision (D1935: the walk deferred **until after Stage 5**); `DX-001` and `apg dx-record check` read a walk record; external mode runs from the workstation with no SSH beyond the ephemeral agent (D466). | **Session 42 builds `tests/external/test_journey.py`**: Appendix C as one ordered proof against the hosted node from the workstation, through `apg` and `/api/v1` only, with **no SSH destination set** (the absence asserted), each step a node id of a new `journey` claim. **Then the walk D1935 deferred**: a person who did not build Stage 5, holding the invitation and the console URL only, walks the first twenty minutes, and the record goes to the gate as `APG_DX_RECORD_FILE`. **Arranged, never closed by the author.** | The specification's success criterion is a person's experience; the executable journey is what makes it repeatable, and the person is what makes it true. | 0207 |
| **D1982** | §61: twenty-six ADRs *"before implementation"*. | 245 ADRs; each Stage 4 session wrote its own in its first run (0216–0245). | **Mapped, not written up front**: hierarchy, project/database/branch meaning and the beta and single-node messaging are ADR 0246 and 0247 (36); API versioning, key scopes, the operation model are 37's; compute profiles, sleep/wake, region, deletion/export are 38's; the gateway, endpoint hostnames and the customer roles are 39's; branch implementation, restore semantics and branch TTL are 40's; Query Insights, metric retention, plans, Free/Premium limits, usage aggregation and entitlement enforcement are 41's; the Stage 6 criteria are the decision report in 42. Promotion's ADR is not written (D1962). | An ADR records a decision when its measurement exists; twenty-six written before any rig would be twenty-six guesses. | — |
| **D1983** | §62: twenty-three inputs Stage 5 *"must consume"* from Stage 4 — sustainable hosted projects, the node envelope, disk/WAL reserve, connection saturation, ClickStack footprint, hosted Studio performance, remote CLI usage, organisation/auth feedback, support-grant experience, workflow and connector load, provisioning and deletion time, restore RTO/RPO, upgrade/cutover, noisy neighbour, admission, pilot feedback, demand for branches, sleep and larger profiles, likely plan limits, user understanding. | **Measured**: the envelope (memory, windows, the neighbour, `auth` under runs), admission behaviour (exit 12), RTO (247 s, D593's band), deploy windows. **Absent because hosting was deferred**: every hosted, pilot, demand and feedback input. ClickStack footprint: never run. | **Recorded as the honest premise: Stage 5 proceeds on the operator's decision, not on Stage 4 demand evidence**, and each session that needs a number measures it on the new host in its Run 1 (profiles in 38, plan limits in 41, ClickStack's footprint in 41, provisioning and deletion time in 38, branch time in 40). Demand questions are the walk's (D1981). | The specification says Stage 5 *"is allowed to revise major assumptions based on this evidence"*; where the evidence is absent, saying so is the revision. | — |
| **D1984** | §58: the operator must answer sixteen questions without undocumented shell commands (active projects, branches, sleeping projects, owners, plans, entitlements consumed, safe capacity, top consumers, pressure, ClickStack within budget, backups healthy, policy excess, admit or not, support grants, running operations, reconstruction after loss). | `apg fleet` (per project and across the host), `apg doctor` (twelve checks), `doctor capacity\|usage`, `admit.sh`, `dr-kit.sh export\|verify`, the node-loss runbook. | **One operator verb, `apg control status`** (root, the control project's database read through the container), answering the questions the control plane owns — owners, plans, entitlements, operations, sleeping projects, branches — beside the existing `fleet`, `doctor capacity` and `admit` for the node's. Support grants: none, by D1971. Session 42, with the runbook updated for the control project's own restore. | The operator's questions split along the same line as the two refusals (D1954): what the control plane decided and what the node measured. | 0185 (superseded for the control plane, D1950) |

---

## 2. The four decisions CLAUDE.md §4 requires

### 2.1 What is the new body of work for?

**The appliance offered to people who do not operate it — on one node,
honestly.**

Stages 1–4 built a governed, recoverable, bounded appliance one operator runs
for their own projects. The specification asks Stage 5 to make it *"look, feel,
and behave like a real commercial managed Postgres product while remaining
explicitly single-node and non-production-grade"*, and the operator decided on
2026-10-03 that it does. What that changes is **who the principals are**: until
now every identity on the host was the operator, the operator's people, or an
agent one of them created. Stage 5 adds a **customer** — an account in an
organisation that holds a database credential, an API key and a project it did
not deploy — and a **reconciler** that acts on the customer's request as root.

**The boundary sentence ADR 0246 records**, extending Stage 4's sibling
invariant one plane up: *the DX layer holds nothing the human does not hold; a
workflow, a connector and a worker hold nothing an agent identity does not
hold;* and now **the control plane holds nothing that opens a project's data,
and the reconciler does nothing but a closed set of typed operations.** A
control plane that held every project's admin token, or a reconciler that ran
a string, would each become the universal backdoor the specification's §48
forbids — the moment the first stranger was invited, which is exactly when it
would be found.

**The second sentence, from the specification and kept whole**: *commercial
product semantics now; commercial infrastructure guarantees never claimed.*
Every product concept is `available`, `beta`, `planned` or `not_metered` in
the Reality Ledger, a program reads it, and nothing `planned` has a control
(D1979).

### 2.2 Does `CURRENT_SESSION` move, and to what?

**Yes, seven times: 35 → 36 → 37 → 38 → 39 → 40 → 41 → 42.** No gap.

Moving it stays **all-or-nothing** (D690), so every session's requirements
arrive with their proofs in the commit that moves the constant, and a
session's registry additions are decided before its first run (§11).

**`template_version` moves with it, one minor per session — unless a session's
own `upgrade plan` prices its change at major** (D1081's rule, kept). **Stage 5
is the first stage likely to cross `2.0`**, and the candidates are named so
nobody is surprised: Session 37 adds a project (the control plane — no
release change by itself); Session 38 adds manifest schema 9 (`compute`,
migratable: a minor) and host schema 4 (`region`, slots: migratable); **Session
39 adds two generated secrets per project with no default (`customer_app`,
`customer_admin` passwords) — `secret_required_added`, which ADR 0162 prices at
major — and a published port**; Session 41 adds `shared_preload_libraries`
(a restart, a minor if `upgrade plan` says so). The class is **read from the
plan's output at each session's close and never chosen** (D704). If 39 prices
at major, Stage 5 closes at `2.x`.

### 2.3 Which open items are actually open?

Ledger §28, the decision report §5–§6, Session 35's §10 and CLAUDE.md §9,
re-read against the tree at `42bf306`:

| Item | Verdict |
|---|---|
| **D1886 / D1700 / D1775 — retention** | **Open. Session 36** (D1973). |
| **The rotation trio** | **Open. Session 36's second sitting**, three rotations, one sheet each (D1974). |
| **The edge window (24.4 s)** | **Open as a measurement. Sessions 36 (the move's recreation) and 39 (project creation moves nothing)** (D1975). |
| **D1581 / D1713 / D1941** | **Open. Session 36's rig, before 38 builds on it** (D1976). |
| **D1918, D1547** | **Open. Session 36** (D1977). |
| **D1936 — beta does not read the approval** | **Open, the operator's edit** (beta manifest to schema 8, `approvals_required: 1`). Session 36's move re-renders beta's manifest anyway; the sheet offers the edit as a separate line the operator may skip. |
| **D1642 — a kit names the checkout's commit** | **Open; matters at the move.** Session 36's move exports the kit from the deployed commit's checkout, so the two agree; the row stays open for the class. |
| **D1798 — no redelivery of a dead letter** | **Open**, not Stage 5's. |
| **D1869 / D1871 / D1722 / D1806 / D1784 / D1792 / ADR 0241's bound** | **Open, unchanged**; D1784 (one connector master per project) is restated for customers in the Ledger. |
| **`port_allocation`** | **Open; the new host boots.** Session 36 declares `--after-reboot` after the new host's first reboot. |
| **`replacement_host_restore`** | **Open by decision (D1028); re-read at the move.** Whether a real move satisfies the proof's preconditions is Session 36's measurement. |
| **`documented_path`** | **`failed` by decision (D1935: walk after Stage 5). Session 42 arranges the person's walk of the journey** (D1981). |
| **D1375 — `op` cannot reach the Docker socket** | **Open by decision.** The reconciler is root (D1953); `op` still is not in the docker group. |
| **D1045, D976, D688, D771, D340, D466, D540, D942, D1203, D1205, D1211** | **Open, each still true, none Stage 5's**, except **D688** (no IPv6 to scan): the new host may have IPv6 — Session 36 reads it and either declares `host.public_ipv6` or keeps the row. §10. |
| **The Infisical control-plane identity holds org admin** | **Open, and now load-bearing**: slots are bootstrapped by it (D1953). Session 38's Run 1 reads what scope a slot's bootstrap needs and the operator narrows it if the provider allows. |
| **The 24 unclaimed requirements** | **Open**; reportable one declaration at a time (ADR 0202). |

### 2.4 Are the unproved claims in scope?

**All five `not_run` are touched and none is promised.** The rotation trio
needs Session 36's three rotations and then every one of its nine node ids
passing on a sweep; the plan reports the trio as moved only when the merged
document says so. `port_allocation` needs the new host's reboot declared.
`replacement_host_restore` is re-read against the move (D1948) and stays
`not_run` if the proof's conditions are not what the move did.
`documented_path` stays `failed` until the person's walk in Session 42 (D1981).
**A session that reports any of these moved before the evidence document says
so is the failure mode CLAUDE.md §7 names.**

---

## 3. Release structure — seven sessions

| Stage 5 session | Absorbs spec sections | Shape |
|---|---|---|
| **36 — Preconditions: the boundary, the move, and the operating debt** | §1, §6, §49, §50–§52, §59, §61 items 1–2/19/24/25, §64; report §6 items 1–4 | ADR 0246 (the hosted boundary; 0042/0043/0044/0216/0217 superseded; product-contract §5 amended), ADR 0247 (the Reality Ledger), ADR 0248 (retention); the hosted `THR-*` rows; the retention plane; D1918's handler; `delete_note`; the Ledger and its guard; D1581's rig; **three sittings on three days**: the move to the new host, the three rotations, the old host retired |
| **37 — The control plane** | §7, §8, §27, §28 (the model), §29 (`login`, `org`, `project list\|use`), §30, §31 | The `control` project and its migration set; organisations, memberships, roles, invitations, TOTP; API keys; `/api/v1` and its frozen contract; the `operations` table (no executor yet); the authoritative `projects` registry; `apg login\|logout\|context\|org\|project list\|use`; ends on the new host with a person invited, an organisation, a key and an operation recorded |
| **38 — Managed projects** | §9, §10, §14–§17, §28 (execution), §46, §47, §57 steps 4–6/26–28/30 | The reconciler; slots; `project.create\|delete\|sleep\|wake\|resize\|export`; capacity as `capacity_exhausted`; states and domain errors; compute profiles (manifest 9); region (host schema 4); the creator as the project's first admin; ends on the host with a project created, slept, woken, resized, exported and deleted from the workstation with no SSH |
| **39 — Connection endpoints** | §11–§13, §57 steps 7–10 | The gateway rig first (Traefik's Postgres routing, TLS, SNI, certificates, wake-on-connect); the Postgres entrypoint; `customer_app` / `customer_admin`; `credential.rotate`; Connect snippets from metadata; the four driver fixtures over TLS; the isolation matrix extended to the listener; external-mode scans; ends on the host with `psql` and Prisma connected through both URLs |
| **40 — Branches and restore to a branch** | §18–§23, §57 steps 12–14/17–18/29 | `naming.branch_names`; `branch.create\|reset\|delete` from the parent's repository at a target time; the re-key; branch TTL; protection; the backups surface; test restore as an operation; ends on the host with a branch from a point in time, migrated, inspected and deleted, the parent untouched |
| **41 — Telemetry, insights, usage and plans** | §24, §25, §32–§39, §44, §45, §53 (ClickStack), §56, §57 steps 15–16/21 | ClickStack bounded; `pg_stat_statements` and Query Insights; curated monitoring; usage sampling; Free/Premium and entitlements as `plan_limit_reached`; notifications; ends on the host with an entitlement refusal and a capacity refusal side by side |
| **42 — The console, the journey, and the Stage 5 release** | §9, §26, §40–§43 (surfaces), §48, §54–§58, Appendix C | The console over `/api/v1`; Studio forwarders for workflows and connectors; the support bundle; `apg control status`; the executable journey; **the person's walk arranged**; the bump; `session-42-check.sh`; `docs/stage-6-decision-report.md` |
| *(cut, with the reason in §1)* | §21 promotion (D1962), in-place restore for customers (D1963), the SQL editor (D1969), temporary support grants (D1971), §53's optional technologies and PostgreSQL 19 (D1947, D1980), billing (D1967), a management SDK (D1952) | — |
| *(`planned` in the Ledger)* | passkeys, email, wake-on-connect if 39's rig refuses it, storage quotas, egress/provider/embedding metering, autoscaling, HA, multi-region, SLA | — |

**Four orderings are forced and the rest is preference.**

1. **36 before everything.** The boundary ADR before any port or customer
   credential; the threat rows before any code; the move before any capacity
   number is derived; D1581 answered before resize and sleep are built.
2. **37 before 38.** Operations live in the control project; the reconciler
   claims from it.
3. **38 before 39 and 40.** A customer's endpoint and a branch are created by
   operations; a branch is charged by admission through the reconciler.
4. **41 before 42.** The console shows usage, insights and plans; the journey
   needs an entitlement refusal to exist.

**39 and 40 are independent** and could swap; 39 is first because a branch's
endpoints are 39's mechanism and Session 40's proof connects to a branch.

**The count, honestly:** the specification freezes no count; its §60 names six
workstreams and its §57 thirty-one steps. Stage 4 deferred the half of the
work this specification assumed was done, so Stage 5 carries the hosted
platform (37, 38, 39) *and* the silhouette (40, 41, 42) *and* the debt the
evidence named (36). Seven is that, and one session more than Stages 2–4 —
not because the specification is larger but because Stage 4 said *not yet* to
its premise.

---

## 4. What is not a session

| Spec section | What it is here | Arranged where |
|---|---|---|
| **§6, §50–§52, §59** — truthful messaging, the Reality Ledger, no fake-complete features, release language | One ADR, one YAML with a guard, every session moving its rows (D1979) | 36 writes it; each session's last run updates it |
| **§13** — framework snippets | A rendering function over endpoint metadata, shown only for a fixture-proved client (D1960) | 39, one run |
| **§17** — regions | A `host.yaml` field read everywhere (D1957) | 38, one run |
| **§21** — branch promotion | Cut; `planned` (D1962) | — |
| **§31** — SDKs | Not built (D1952) | — |
| **§45** — notifications | A table and a list route (D1968) | 41, one run |
| **§48** — support surface | A diagnostics route and one honest sentence (D1971) | 42, one run |
| **§49** — threat model | Rows before code in every session (D1978) | 36, then each session's first run |
| **§58** — operator criterion | One `apg control status` verb beside the node's readings (D1984) | 42 |
| **§61** — the ADR list | Each decision in the session that measures it (D1982) | 36–42 |
| **§62** — evidence from Stage 4 | Measured in each session's Run 1 on the new host, or stated absent (D1983) | 38, 40, 41 |
| **Appendix C** — the journey | An external proof and a person's walk (D1981) | 42 |

**A declaration may not be closed by the author.** The walk must be by a person
who did not build Sessions 36–41, holding only an invitation and the console
URL, and the record must be handed to the gate as `APG_DX_RECORD_FILE` and read
by `apg dx-record check`. A shorter finding list is not a pass.

**A caution about the rotations.** Three rotations on three sheets move the
trio only if every one of the nine node ids passes on the sweep that follows;
the sheet for the second sitting says so at the top, and Session 36's §7
reports the trio from the merged document and nothing else.

**A caution about the move.** The old host is the only copy of a running
deployment until the new one has been deployed, swept and served. Session 36's
third sitting — the old host stopped, then retired — is on a later day than the
move, and its sheet may not be issued until the move's sweep has been read
(D1510).

---

## 5. The seven sessions

Each gets its own plan. What follows is the sentence each plan starts from,
what it must not do, what it measures, and where its exit criteria come from.
**Requirement id families are proposed, not fixed** — each session's own §2
settles them (D691). **Every path, flag and exit code below is what the tree
has today; a session plan re-measures each before depending on it** (§11).
**Every number about the host is the old host's until Session 36's move**, and
is re-read on the new one.

### Session 36 — Preconditions: the boundary, the move, and the operating debt

> **Revised 2026-10-03 (Session 36's D1991).** The operator chose to rescale the
> existing Hetzner server in place — CPU and RAM only — instead of moving to a
> new VPS. Every mention of *the move*, *the new host* and *the old host
> retired* in this stage plan (here, in §2.3, §2.4, §3, §4, §7, §10 and the
> appendix) is superseded by `docs/plans/session-36-implementation-plan.md`,
> the plan of record for the session: no restore, no DNS change, no
> retirement; `replacement_host_restore` stays `not_run` by D1028.


**Builds.** In this order. **(a) ADR 0246** — the hosted boundary: supersedes
0042, 0043, 0044, 0216 and 0217 together; amends `docs/product-contract.md`
§5 under its §7 (removed: the control plane, the hosted console; narrowed:
sleep, branch-from-backup, the control plane's own counts; kept: agent SQL,
the ORM non-goal, failover and multi-region, autoscaling, copy-on-write);
restates CLAUDE.md §6's SQL sentence as *a product surface runs no SQL*;
names the ports the host may publish (80, 443, and the one Postgres port
Session 39 decides); states §2.1's boundary sentence. **(b) The hosted
`THR-*` rows** in `docs/threat-model.md` (D1978), each naming its session and
negative test, and the Scope sentence on denial of service. **(c) ADR 0247 and
the Reality Ledger** (D1979): `docs/reality-ledger.yaml`, `bin/render-reality-
ledger.py --write|--check`, the generated `docs/reality-ledger.md`, and
`tests/contract/test_reality_ledger.py` with the three guards (most rows
`planned` today; the operation-type and console-control halves of the guard
read empty sets until 37 and 42 fill them, and say so). **(d) ADR 0248 and the
retention plane** (D1973): migration 0038 with one definer prune function per
table in FK order, the approval `cancelled` status (D1775), `bin/record.sh
prune|size`, the doctor's `agent record` check widened. **(e) D1918's handler**
and **D1547's `api.delete_note`** (in 0038 or its own 0039 — the session plan
decides by `upgrade plan`'s reading). **(f) D1581's rig** (D1976): two
no-change deploys in a throwaway rig, container ids and generation directories
before and after, control: a changed mount. **(g) The move** (D1948): the new
host's `host.yaml` (capacity read, not typed — `free -m`, `nproc`, `df` at the
Docker root, through `doctor capacity`), `provision-host.sh`, the kits exported
from the old host at the deployed commit, `restore.sh --from mirror` for alpha
and beta on the new host, the edge up, both deployed, DNS A records switched
(grey cloud; ACME's 5-failures-per-hour limit read before the switch), one
sweep, `port_allocation` declared after the new host's first reboot, and the
envelope's Session 35 rows re-measured where the host moved them. **Then two
more sittings on two more days**: **the three rotations** (D1974), one sheet
each, then the sweep that reads the trio; and **the old host retired** —
stopped, its kit verified on the new host, its DNS gone, its disk left for the
operator to destroy.

**Already true, so do not rebuild it.** ADR 0213's prune shape and
`agent_record_size()`; the DR kit, `restore.sh --from mirror`, the
node-loss runbook; `rotate-secret.sh`'s plans; the edge's watched file
provider.

**Must not.** Write any code that serves a customer. Open a port. Copy a
number from the specification into a profile, a plan or the Ledger. Retire
the old host on the day of the move. Bundle two rotations on one sheet.
Report the trio moved from a sheet rather than a sweep. Let a prune run on
its own (ADR 0213).

**Measures.** D1581's rig with its control. On the new host: `doctor
capacity` against `free -m`/`df`; the restore's wall time from the mirror
against D1028's 247 s; the edge's recreation window on the new host; the
envelope's deploy windows on the new host; the IPv6 address (D688).

**Closes.** D1886, D1700, D1775 (as a plane), D1918, D1547, D1581/D1713 (as a
measurement), D1949 (as a decision), D1978's first half, D1979's first half;
the trio and `port_allocation` if the evidence says so.

**Proposed families.** `HOST-*` (the move), `OPS-*` extended (retention),
`LEDGER-*`.

### Session 37 — The control plane

**Builds.** **First run: the `THR-*` rows** for accounts, invitations, API
keys, organisation privilege escalation, API replay and enumeration. **The
`control` project**: a manifest (`/home/op/control.yaml` on the host, never in
the checkout, D971) with `lifecycle: permanent`, its own migration set under
`projects/control/migrations/` (organisations, memberships with roles
`owner|admin|member|viewer`, invitations, API keys, projects, operations,
regions, notifications; FORCE RLS on every `app` table, the lint passing), and
its own capability manifest naming **no** agent tools beyond the release's
defaults (a control plane offers its customers no MCP surface in Stage 5).
**A fourth `APP_MODE`, `control`**, in `services/auth-api/app/main.py`, serving
`/api/v1` behind the control project's router: `organizations`, `members`,
`invitations` (create → token shown once; accept → account + membership in
one transaction), `api-keys`, `projects` (list/get; create returns an
operation), `operations` (get/list/cancel while `pending`), `ledger`. TOTP
(RFC 6238 over `hmac`, the RFC's vectors as the rig) required for `owner` and
`admin` at login. API keys as D1952 describes. The contract frozen as
`contracts/control-openapi.canonical.json` with `bin/control-contract.sh
--check`. **The `projects` registry** seeded from the host's deployed documents
by an operator verb (`apg control adopt --project KEY`, root) for alpha, beta
and the control project itself, and reported against them with three outcomes.
**CLI verbs**: `apg login` (key or password + TOTP; writes the context file
0600), `apg logout`, `apg context`, `apg org list|create|invite|members`, `apg
project list|use|status`. **No operation executes in this session**: `POST
/api/v1/projects` returns an operation that stays `pending`, and the Ledger
says `planned` for its execution. **Ends on the new host**: the control
project deployed; the operator invited by the bootstrap admin, the invitation
accepted from the workstation, TOTP enrolled, an organisation created, a
second person invited and accepted as `member`, a key minted and used by `apg
project list`, a `project.create` operation recorded and listed.

**Already true, so do not rebuild it.** The auth service's login, sessions,
refresh families, Argon2id, `authz_version` and audit; the tenant extension
point and its lint; the generator if a client is ever wanted.

**Must not.** Give the control plane any credential to a project's database,
auth service or admin routes (the boundary). Add a signup route. Send an
email. Store a key or an invitation token in clear. Let a `viewer` hold a
write scope or a member manage keys they do not own. Serve `/api/v1` without
the frozen contract matching. Execute an operation.

**Measures.** TOTP against RFC 6238's vectors (control: an off-by-one step
refused); an invitation replayed after acceptance refused (control: a fresh one
accepted); a key revoked with its member refused on its next request (control:
a sibling member's key served); the control project's admission charge on the
new host.

**Closes.** D1950, D1951, D1952 (as an API and the first verbs), D1953's (a).

**Proposed families.** `CTL-*`, `KEY-*`.

### Session 38 — Managed projects

**Builds.** **First run: the `THR-*` rows** (creation exhaustion, deletion
races, the reconciler as root, slot confusion) **and the measurement D1953
rests on**: a pre-bootstrapped slot deployed by a non-interactive root process
on the new host with stdin at `/dev/null` (the D972 guard's fully detached
shape), every human dependency named with file:line. **The slot**: host schema
4 (`region`, `slots: [{key, state}]`), `bin/slot.sh provision --key sN` (the
operator's, root, wrapping `bootstrap-providers` and the bucket steps a human
does today). **The reconciler**: `bin/reconciler.py` + `bin/reconciler.sh`,
`systemd/agentic-postgres-reconciler.service`, claiming through
`control_claim_operation()` by `container_exec.run`, one operation at a time,
a closed type enum dispatching to existing `bin/` commands by argv, every
outcome written back with three outcomes (an operation whose result could not
be read is `failed` with the reason, never `succeeded`). **Operations**:
`project.create` (entitlement placeholder: the control plane's
`projects_active` read from a constant until 41; slot allocated; manifest
generated from the request and the profile; `admit.sh` → `capacity_exhausted`
on exit 12 with *"No resources were created"*; deploy; the creator
bootstrapped as the project's first `project_admin` with the secret shown once,
D1969), `project.delete` (D1972), `project.sleep|wake` (D1956: stop/start, the
caller's view while asleep **measured in the rig** — a stopped container's
Docker-provider routes disappear, so whether the edge answers `404` or a
file-provider fallback can serve a body naming `project_sleeping` is the
measurement, control: an awake project's route), `project.resize` (D1955:
profiles derived in Run 1, manifest schema 9, the restart message from the
envelope), `project.export` (D1972). **Idle sleep** as a per-project setting
the reconciler acts on. **States** derived per D1953; the domain-error enum.
`apg project create|delete|sleep|wake|export`, `apg compute get|set`, all over
`/api/v1`. **Ends on the new host**: from the workstation with no SSH, a
project created into a slot, its doctor at twelve ok, slept (the caller's view
recorded), woken (the cold start timed into the envelope), resized (the window
timed), exported (the archive downloaded and listed), deleted (the slot
consumed); and a third creation refused by capacity with nothing created.

**Already true, so do not rebuild it.** Deploy, admission, retirement,
`project-runtime.sh`, the restore drill's naming discipline, `container_exec`.

**Must not.** Accept a free-form command, path or shell fragment in any
operation's arguments. Give the reconciler a network listener or a provider-
administering credential. Reuse a slot. Let a capacity refusal and an
entitlement refusal share a code. Print a restart window nobody measured.
Delete a backup repository from an operation.

**Measures.** The slot rig above; the reconciler killed mid-operation and
restarted (the operation resumes or fails with its reason, never runs twice —
control: an uninterrupted one); the sleep/wake caller's view and cold start;
the resize window per class; provisioning and deletion time (D1983).

**Closes.** D1953, D1954's capacity half, D1955, D1956's operation half, D1957,
D1972, D1976's use.

**Proposed families.** `LIFE-*`, `OPN-*`.

### Session 39 — Connection endpoints

**Builds.** **First run: the `THR-*` rows** (endpoint confusion, gateway
attacks, wake-on-connect abuse, control/data-plane credential confusion) **and
the gateway rig** (D1958's five measurements, each with its control) on a
throwaway Traefik v3.7 and a throwaway cluster; the ADR records what Traefik
does and does not do and, if it cannot route the protocol, prices the
product's own TCP proxy before building it. **The Postgres entrypoint** on the
edge (the edge's one announced recreation if the move did not carry it,
D1975), per-project TCP routers for `<key>.pool.<domain>` (PgBouncer) and
`<key>.direct.<domain>` (the database), certificates by the path the rig
chose, plaintext refused. **The two customer roles** (D1959) created by the
bootstrap plane, their `CONNECTION LIMIT`s summed into ADR 0070's budget (the
budget test extended), their passwords as generated secrets shown once through
`/api/v1/projects/{id}/connections` and rotated by `credential.rotate`.
**Snippets** (D1960). **The four driver fixtures re-pointed at the TLS
endpoints**, and the isolation matrix extended with the listener's hostnames
(D702's rule). **External mode** gains the scan: only 80, 443 and the Postgres
port answer; a wrong SNI is refused; a plaintext `SSLRequest`-less start is
refused. Wake-on-connect built only if the rig allowed it. `apg db connect|
status`. **Ends on the new host**: `psql` and Prisma connected from the
workstation through both URLs of a project created in 38, a migration applied
over the direct URL by `customer_admin`, `app_private` refused to it, a wrong
SNI refused, a rotated password refused at its old value — and creating a
second project's routers measured against the first's latency (D1975).

**Already true, so do not rebuild it.** PgBouncer in transaction mode; the
bootstrap plane's role and limit writing; the driver fixtures; the edge's
bounded container.

**Must not.** Publish any port beyond ADR 0246's list. Accept a plaintext
Postgres connection on the public port. Grant a customer role anything in
`app_private`, `extensions`, role DDL or `SUPERUSER`. Hand a customer
`migration_user`. Put a customer password in a URL the API logs. Raise
`max_connections` to fit the new claimants without the budget test.

**Measures.** The gateway rig; the per-driver matrix over TLS; the router-
creation latency against the neighbour; the certificate issuance count
against the provider's limits.

**Closes.** D1958, D1959, D1960, D1975's second half, D1956's wake-on-connect
half (built or `planned`).

**Proposed families.** `EP-*`, `SEC-*` extended.

### Session 40 — Branches and restore to a branch

**Builds.** **First run: the `THR-*` rows** (branch enumeration, restore
abuse, branch exhaustion, a branch reaching its parent) **and the re-key rig**:
a parent restored at a target time into a throwaway volume, the parent's
credentials tried against it (control: refused after the re-key, accepted
before it — the measurement that proves the re-key is load-bearing).
`naming.branch_names(key, branch)` with its own stem; `branch.create` (name,
class, source time; the restore drill's argv persistent; archiving off; the
re-key before the endpoint opens; endpoints from 39; admission charged),
`branch.reset`, `branch.delete` (only what its names derive); the branch
classes and `main`'s protection; **branch TTL as a reconciler trigger** (the
ADR superseding 0186 for branches only); `branches_total` read from a
constant until 41. **The backups surface** (D1963): `/api/v1/projects/{id}/
backups` from the doctor's three readings and `pgbackrest info`, the restore
window computed; `restore.create` = `branch.create` with a target time; *test
restore* as an operation over `restore-test`. `apg branch create|list|inspect|
reset|delete`, `apg backup status`, `apg restore create`. **Ends on the new
host**: a branch of a 38 project from a point in time before a deliberate
change, the change absent on the branch and present on `main`, a migration
applied to the branch over its direct URL, its provenance read, the parent's
credential refused at the branch, the branch deleted, the parent's doctor at
twelve ok throughout.

**Already true, so do not rebuild it.** The restore drill and its
disposability rules; the restore from primary or mirror; the doctor's backup
readings.

**Must not.** Write to the parent's repository from a branch (no stanza, no
archive). Open a branch's endpoint before the re-key. Delete anything a
branch's names do not derive. Offer an in-place restore to a customer. Build
promotion.

**Measures.** The re-key rig; branch creation time against the parent's
repository size on the new host (the envelope row the specification asks to be
*"reported, not hidden"*); a branch's capacity charge.

**Closes.** D1961, D1962 (as a cut), D1963.

**Proposed family.** `BR-*`.

### Session 41 — Telemetry, insights, usage and plans

**Builds.** **First run: the `THR-*` rows** (plan-limit bypass, usage
tampering, observability poisoning, ClickStack exhaustion) **and ClickStack's
footprint measured** on the new host with a control load. **ClickStack**
(D1964): `infra/telemetry/compose.yaml`, images by digest, bounded, unrouted,
TTLs, admission-charged; each collector's logs pipeline (D1918's lines) and
OTLP export to it. **`pg_stat_statements`** (D1965): the `-c` flag, the
extension in `extensions`, one restart per project in the session's deploy
(the window recorded); Query Insights through `/api/v1/projects/{id}/
insights` with normalised text; history sampled into ClickHouse; *"Create
tuning proposal"* as a pointer to `migrate propose`. **Monitoring**: a
curated signal list, each naming its source. **Usage** (D1966): the
reconciler's sampler into `usage_samples`, `/api/v1/usage` per project and
organisation, `apg usage`. **Plans and entitlements** (D1967, D1954): `plans.py`
with every number derived in Run 1 and named in the ADR; the control plane's
`plan_limit_reached` / `branch_limit_reached` before an operation exists; the
agent quota written on agents; `apg plan`; the pricing page's data served by
`/api/v1/plans` with the beta sentence. **Notifications** (D1968). **Ends on
the new host**: a second project refused by the Free plan's `projects_active`
with `plan_limit_reached`, and — with the limit raised for the test — a
creation refused by capacity with `capacity_exhausted`, the two side by side;
Query Insights read after a known workload; usage read; HyperDX reached by the
operator's SSH forward and by nothing else.

**Already true, so do not rebuild it.** The collector and Prometheus, `doctor
usage`, the windowed quota, admission.

**Must not.** Route ClickStack or HyperDX, or export telemetry off the host.
Put a caller value, a key, a URL or literal query constants in a series, a log
line or an insight (the canary). Show a recommendation with a confidence.
Enforce a limit nothing can enforce. Add a checkout, an invoice or a card
field. Let one store answer a question the other already answers.

**Measures.** ClickStack's memory and CPU under the control load; the
`pg_stat_statements` restart window per project; the entitlement and capacity
refusals with each other held green.

**Closes.** D1954's entitlement half, D1964, D1965, D1966, D1967, D1968.

**Proposed families.** `INS-*`, `USE-*`, `PLAN-*`.

### Session 42 — The console, the journey, and the Stage 5 release

**Builds.** **The console** (D1969): static files under `services/console/`,
served by the control project's router, calling `/api/v1` only, the
specification's navigation minus SQL, the beta sentence and the Ledger served
from `/api/v1/ledger`, the pricing page with Premium unavailable and *"Notify
me"*; the project data views opening that project's Studio forwarders as the
member's project identity. **Studio's forwarders** for workflows and
connectors (D1970). **The support bundle** (D1971). **`apg control status`**
(D1984) and the node-loss runbook updated for the control project. **The
executable journey** (D1981) in external mode. **The person's walk arranged.**
Then the bump: `CURRENT_SESSION` 42, `template_version` as `upgrade plan`
prices it, requirements and claims, `session-42-check.sh` derived by diff from
41's, `scope-closure.md` re-audited row by row, the Ledger re-read against the
evidence, `evidence/session-42.json` from a host trip, and **`docs/stage-6-
decision-report.md`** written from that document — answering the
specification's §65 question with numbers: *which bonsai implementation is
the most important bottleneck or false assumption to replace next.*

**Already true, so do not rebuild it.** Studio's forwarder pattern and its
loopback rule for the local verb; the release machinery; the gate cadence.

**Must not.** Add a SQL box, or any console control the Ledger marks
`planned`. Give the console a route `/api/v1` does not serve. Close
`documented_path` on the author's walk or a shorter list. Use a §59 word. Write
the decision report before the evidence document exists.

**Measures.** The journey's thirty-one steps; the console's first paint
against the new host; the walk's record; every gate in every mode the evidence
needs.

**Closes.** D1969, D1970, D1971, D1981 (if the walk is clean), D1984, D1979's
second half.

**Proposed families.** `CON-*`, `JRN-*`, `REL-*` extended, `DX-*` extended.

---

## 6. What Stage 5 does not build

`product-contract.md` §5 as ADR 0246 amends it is read as written: **no
autoscaling or compute/storage separation, no copy-on-write forks or instant
branching, no automatic failover or multi-region, no arbitrary agent SQL, no
general ORM, and no product surface that runs SQL.**

**What the specification asks for and this plan cuts or marks `planned`, each
with its row:**

- **PostgreSQL 19** (D1947), **`pg_ivm`, `pg_cron`, `pgroll`, Valkey, local
  inference, snapshot storage, a same-host replica** (D1980).
- **Branch promotion** (D1962) and **in-place restore for a customer** (D1963).
- **A SQL editor in the console** (D1969).
- **Temporary support grants** (D1971) — replaced by a sentence that is true.
- **Public signup and email** (D1951); **passkeys** (`planned`).
- **Billing in any form** — checkout, invoices, cards, tax, credits (D1967).
- **A management SDK** (D1952).
- **Storage quotas, egress, provider and embedding metering** (D1955, D1966) —
  `planned` / `not_metered`.
- **Wake-on-connect** if Session 39's rig refuses it (D1956) — `planned`.
- **A recommendation engine** for Query Insights (D1965).
- **A second edge** (D1975).
- **Autoscaling, HA, multi-region, an SLA** — §52, agreed whole; `planned`
  for a later stage in the Ledger, never offered.

---

## 7. Evidence and claims across Stage 5

**Unchanged, and none of it is renegotiated.** A claim's verdict is computed
from the acceptance registry's node ids and JUnit results, never hand-entered.
Three statuses (ADR 0163): `failed` means the system is wrong, `not_run` means
the evidence is, both exit 5. Three modes, and an offline claim is declared in
`OFFLINE_CLAIMS`, never inferred (ADR 0202). A skip is not a pass; a `-k` run
writes nothing; each half names the commit it measured; two live halves naming
different commits do not merge.

**External mode becomes the customer's mode.** Until now external mode was
the operator's workstation reaching the host. From Session 37 a proof that a
customer can do something runs in external mode **with no SSH destination**
(the absence asserted by the proof), through `/api/v1`, `apg` and the public
Postgres port only. A customer claim proved over SSH would be measured through
the wrong door (CLAUDE.md §7 question 3).

**Which claims each session touches.**

| Session | Touches | Ends on a host? |
|---|---|---|
| 36 | new `HOST-*` (the move), `OPS-*` retention, `LEDGER-*` (offline-declared); the rotation trio; `port_allocation`; `replacement_host_restore` re-read | **Yes, three sittings** — the move and sweep; the rotations and sweep; the old host retired |
| 37 | new `CTL-*`, `KEY-*` (contract and guards offline; invitation, TOTP and keys live, external) | **Yes** |
| 38 | new `LIFE-*`, `OPN-*` (the reconciler's dispatch offline; every operation live, external) | **Yes** |
| 39 | new `EP-*`; `project_isolation` re-run with the listener; the four DBX driver claims re-pointed | **Yes** |
| 40 | new `BR-*` (naming and the re-key offline in a rig; the branch live) | **Yes** |
| 41 | new `INS-*`, `USE-*`, `PLAN-*`; `every_service_bounded_live` re-run with ClickStack | **Yes** |
| 42 | new `CON-*`, `JRN-*`; `documented_path`; every Stage 5 claim in every mode | **Yes** — the release trip |

**Three things Stage 5 adds to the model:**

1. **A customer claim is proved by a customer's credentials through a
   customer's door** — an API key, an invitation, a database password over
   TLS — never by the operator's SSH or root.
2. **A Ledger row is evidence-bearing**: an entry `available` or `beta` names
   the claim or envelope row that makes it so, and the Ledger's guard fails
   when that claim is not `passed` in the newest evidence document.
3. **Every new deployed-document field is classified in the isolation matrix
   in the session that adds it** (D702, D1029) — the region, the compute
   profile, the endpoints, the customer roles, the branch names — and the
   trip's gate proves it.

---

## 8. The security invariants Stage 5 may not weaken

Stage 4's table carries forward whole. What is new is that Stage 5 adds **a
customer** and **a reconciler**: a principal from outside and an actor with
root — and those are the two shapes most likely to become an authority by
accident.

| Invariant | Control | Where Stage 5 puts it at risk |
|---|---|---|
| PostgreSQL is the final authorization authority | RLS, FORCE, the pre-request hook | The control project's tables (37); the customer roles (39) |
| A project's identities are derived once, in `naming` | ADR 0002 | Slots, branches, endpoint hostnames (38, 39, 40) |
| An agent cannot run SQL | No input accepts one | Unchanged; a customer role is not an agent (39) |
| **A product surface runs no SQL** | ADR 0246; the console and Studio forward named operations | The console (42); Query Insights shows text, never runs it (41) |
| **The control plane holds nothing that opens a project's data or admin plane** | ADR 0246; the creator bootstrapped as the project's own admin, secret shown once | 37, 38, 42 |
| **The reconciler runs only a closed set of typed operations** | A type enum, a JSON Schema per type, argv never a string, no listener | 38, 40 |
| **A capacity refusal and an entitlement refusal are different codes from different readers** | `capacity_exhausted` from exit 12; `plan_limit_reached` from the control plane | 38, 41 |
| **A slot is never reused** | A consumed state with no transition back | 38 |
| **A branch starts re-keyed and cannot write its parent's repository** | The re-key before the endpoint opens; no stanza, no archive | 40 |
| **The public Postgres port accepts only TLS, routed by name** | The gateway rig's refusals as standing tests | 39 |
| **A customer role never reaches `app_private`** | Grants, and a negative test per schema | 39 |
| **A credential shown to a customer is shown once and stored hashed or materialised, never logged** | Argon2id for keys and invitations; generations for passwords; the canary | 37, 39 |
| **Nothing `planned` has a control** | The Reality Ledger guard | Every session; 42 most |
| A revoked token stops on its next request, locally | `authz_version`; per-step minting | API keys revoked with their member (37) |
| An agent record carries no URL, key, token or caller value | `audit.redact`, the canary | ClickStack's logs and Query Insights' text (41) |
| One service cannot read another's credential | Per-consumer immutable generations | The customer passwords (39) |
| A restore never overwrites the active volume | The restore path's refusal | Branches (40) |
| Projects share no project-scoped value | The isolation matrix | Every new field (38–40) |
| A deploy over a broken archiver fails | Step 6c | A sleeping project's archiver is stopped by design, and the Ledger says so (38) |
| The deploy, the sweep and the tag land on one commit | D1425 | Session 42's release |
| **A report may not substitute an answer for a failure to determine one** | ADR 0195 | Resource states (38), the backups surface (40), usage and insights (41), `apg control status` (42) |

**The last row is still the one most exposed**, because every customer-facing
status is a reader of durable state a person will act on — and now the person
did not build it. The voice to copy remains `bin/backup.sh`'s timeout message
and the doctor's `pooler could not be asked`.

---

## 9. Risks and stop conditions

**Stop and ask** rather than proceeding, when:

- the control plane would need a credential that opens a project's database,
  auth service or admin routes, or the console would need one (37, 38, 42);
- an operation would carry a command, a path, a shell fragment or SQL in its
  arguments, or the reconciler would need a listener or a provider-
  administering credential (38);
- a port beyond ADR 0246's list, a published ClickStack/HyperDX/Prometheus
  route, or a plaintext Postgres connection on the public port would be added
  (39, 41);
- a customer role would need anything in `app_private`, role DDL, extension
  DDL or `SUPERUSER`, or a customer would be handed `migration_user` (39);
- a branch would open its endpoint before the re-key, or write to its parent's
  repository (40);
- a slot would be reused, or an operation would delete a backup repository
  (38);
- a capacity refusal and an entitlement refusal would share a code or a
  reader (38, 41);
- a console control, an API operation or a document sentence would present a
  `planned` feature as working, or use a §59 word without evidence (every
  session);
- a number from the specification would be used where a reading of the new
  host is owed (36, 38, 41);
- a SQL box would be added to any product surface (42);
- the old host would be retired before the new one's sweep has been read (36);
- a currently-passing test would be weakened to make a new one pass;
- a Stage 1–4 claim goes red and the tidy fix is on the proof's side;
- `--render-only` stops working with no host and no root;
- a session's `upgrade plan` prices a change at major for a reason the session
  plan did not name (§2.2).

**The failure mode Stage 5 is most exposed to is new.** Stage 1 kept producing
*a value that looked measured and was not*; Stage 2's was *re-implementing
what existed one layer over*; Stage 3's *a client that becomes an authority*;
Stage 4's *a principal that holds more than the identity it acts for*. **Stage
5's is a product surface that claims more than the node does** — a region
that is not a place, a profile no deploy enforces, a plan limit nothing
checks, a restart message nobody timed, a branch that still answers its
parent's password, a support promise root makes untrue — **and its sibling, a
control plane that becomes the authority over the data plane it describes.**
The Reality Ledger is the first's control and §8's bold rows are the second's.

---

## 10. Open items carried in

Everything in ledger §28 and CLAUDE.md §9 that §2.3 did not resolve, plus what
Stage 5 creates.

**Carried in and not addressed by Stage 5:** D1045 (the owner's); D1375 (by
decision); the 24 unclaimed requirements (one declaration at a time); D976
(Infisical's hangs — now on the creation path, so 38 reads it); D771; D340;
D466; D540; D942; D1203; D1205; D1211; D1798; D1869; D1871; D1722/D1806;
D1784; D1792; ADR 0241's bound; `process-max` 1 (D593) — **now a customer's
restore time and a branch's creation time**, stated in the Ledger.

**Carried in and addressed:** D1886/D1700/D1775, D1918, D1547, D1581/D1713,
the rotation trio, `port_allocation` (36); D688 if the new host has IPv6 (36);
D1642 at the move (36); D1936 offered as an operator line (36);
`documented_path` (42).

**Created by Stage 5, and named here so no session inherits them silently:**

- **The control project is the platform's single point of failure on a single
  node.** Its backup, restore and DR kit are a project's like any other, and
  the node-loss runbook must restore it **first** (42), because without it no
  customer can reach the API that would tell them their project is fine.
- **The reconciler is a new standing root actor.** Its unit, its claim function
  and its dispatch table are the most security-relevant code Stage 5 writes;
  each session that adds an operation type adds its row to the dispatch test
  and its `THR-*` row.
- **Slots are a stock the operator replenishes.** When none is free, creation
  refuses with a domain error that says so (`capacity_exhausted` with the
  reason *no prepared slot*), and `apg control status` counts them.
- **Customer credentials are secrets with outside holders**, like a connector's
  (D1784): their rotation is an operation the customer runs; a compromise
  report is the customer's to make, and the threat model says what the
  operator can see.
- **Two telemetry stores** (Prometheus and ClickStack) are one more than the
  rule likes; Session 41's ADR names which question each answers and a test
  holds the split.
- **Seven more gate scripts**, each derived by diff from the newest and
  registered in `SHELL_COMMANDS` (D1014); header and usage block rewritten
  whole (D1488).
- **The person's walk will find what seven sessions of new surface did not
  say**, and the repairs will land after the reader has gone (D1359's shape).
  Session 42 budgets a second reader if the first records more than D1935's
  eleven steps.

---

## 11. How a Stage 5 session is planned

**Each of the seven still gets its own plan**, in the shape Stage 2's §11
fixed and Stages 3 and 4 kept — sections 0, **1**, 2, 4, **5**, 7, 8, 9, 10,
appendix — **with the operator's numbered sheet inside the plan**, op steps
and sudo steps separated, one sheet per outcome.

**Before a line of a session plan:**

1. **Read this document's §1 rows for the session and check each premise
   against the tree again** — and, from Session 37 on, **against the new
   host**, because every capacity number in §0 is the old host's.
2. **Decide the requirement ids** (§2 of the session plan). Moving
   `CURRENT_SESSION` is all-or-nothing (D690).
3. **Decide the trip's shape.** Every Stage 5 session ends on the new host;
   Session 36 on it three times. A trip is three gates and two repairs; **grep
   the previous trips' *"if something goes wrong"* sections first** (D977). A
   sheet may not hand over a command whose precondition is the previous
   sheet's success (D1510); the gate reads four renders (D1507) — **plus the
   control project's from Session 37**, which the session plan names; `/tmp` on
   the host is tmpfs.
4. **List the rigs**, each with its control, before the runs that depend on
   them — and **grep the plans for every third party first**: Traefik and the
   Postgres protocol (39 — **0 hits today**), Let's Encrypt's issuance limits
   (39), ClickHouse and HyperDX (41 — one hit, the Stage 4 refusal), RFC 6238
   (37), pgBackRest's restore into a second volume and `pg_authid` (40),
   `pg_stat_statements`' loading and its restart (41), the VPS provider's
   provisioning (36).
5. **Grep every reader** of any definition the session changes (D979): every
   reader of `publication()` and `ports:` in 36 and 39; every reader of the
   manifest schema version in 38; every caller of `restore_drill` in 40; every
   reader of `ISOLATED_FIELDS` in 38–40; every reader of `ADR 0070`'s budget in
   39.
6. **Write for a cold executor.** The plan is executed by a session that starts
   with nothing but the tree and the plan: every path, flag, fixture, helper
   and exit code by name; every command spelled out; every third-party claim
   measured in Run 1's rig with its control named or marked as the measurement
   that run owes. **When the tree and the plan disagree, the tree wins and the
   disagreement is a divergence row.** A documentation-only push reads no CI
   verdict.

**What is deliberately not simplified**, because it is what caught the defects
rather than what cost the time — Stage 4's seven, plus one:

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
  adds or removes a `bin/` verb** (D1014) — Stage 5 adds more verbs than any
  stage before it.
- **Every proof registered to a claim, checked by the registry test**, so an
  orphan cannot read as `passed` (D1236).
- **The Reality Ledger moved in the run that builds the thing**, never at the
  close — a row moved at the close is a row nobody checked against the run.

**The gate cadence does not change and is not a save button.** Documentation
only → nothing, and no CI read. Generated artefacts could drift →
`bin/session-01-check.sh` alone. Code → the modules the change touches; **CI
is the full check**, read by the full SHA and the HTTP status, with three
buckets (D1059). Before a host trip, a deploy or a session close → every
applicable gate, once, in every mode the evidence needs.

---

## Appendix — what to consult, and what to measure instead

**Consult, in this order:** this document's §1 and §3.
`docs/stage-5-decision-report.md` whole — the numbers Stage 4 measured and §5's
price list, which is Session 36's and 37's first work. `docs/scope-closure.md`
§28. `docs/plans/stage-4-plan.md` §6 (what deferring hosting was priced at) and
§8–§9. `docs/plans/session-35-implementation-plan.md` §5 Run 10 and Sheets
F1–F8 with D1941–D1944 — the last trip's shape and what went wrong on it.
`docs/node-loss-runbook.md` and ADRs **0189/0192** before the move; **0088,
0174, 0224** and `docs/operator-guide.md` §15 before the rotations; **0213**
before the retention plane; **0042/0043/0044/0216/0217** before writing ADR
0246; **0185** before the registry; **0198/0201** before the control project's
set; **0151** before branches; **0110, 0186, 0187** before slots and deletion;
**0221/0222/0244** before profiles and ClickStack; **0205** before the
console; **0195** before writing any reader. The specification's §1, §39 and
§48 — the three passages this plan adopts as written — and its §51–§52 and
§59, which it agrees with whole.

**Measure instead of consulting**, every time: what the new host actually has
(Session 36 is the first time a program reads it); what Traefik does with the
Postgres protocol (nobody has looked); what a physical restore carries into a
branch (the parent's roles — measured, not assumed); what a sleeping project's
caller sees; what a served surface says against what the control plane's
registry recorded (ADR 0158's rule, one plane up); whether a reader can say
*unknown* (ADR 0195); whether a proof has ever run and belongs to a claim; and
**what the tree does today**, because every premise this plan audited was true
of a specification written on top of a specification, and false of the tree.

**Before measuring how a third party behaves, `grep` the plans for it.**
Nothing indexes the ~1,600 measured facts by subject; the pointer has to be a
`grep`.

**Never write a measurement you did not run** (D267). Every number in this
document was measured on 2026-10-03 at `42bf306`, or says whose it is.
