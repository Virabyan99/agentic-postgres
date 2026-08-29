# Session 14 — observability, alerting, and the capacity envelope

The second Stage 2 session, and **the one place the Stage 2 audit found genuinely
empty**: `opentelemetry`, `prometheus` and `otlp` match nothing in `services/`,
`src/`, `bin/`, `requirements-dev.in` or `compose.yaml` (D706).

**It is empty, not unconstrained.** The host is a 3,814 MB machine with **no
swap**, already running sixteen containers and two PostgreSQL clusters budgeted
768 MB each. Whether an observability plane fits is this session's first
question, and §5 Run 1 answers it before anything is designed.

**Read `docs/plans/stage-2-plan.md` first.** It owns where Stage 2 starts and why
there are six sessions. This document does not repeat it.

---

## Status — read this first

```
SESSION 14 IS NOT STARTED. This is the plan.
CURRENT_SESSION 13; it moves to 14 in the bump run -- ALL-OR-NOTHING (D690).
template_version 0.2.0 -> 0.3.0, and ADR 0162 decides what that permits.
divergences     D760-D764 recorded here. **Next free: D765.**
ADRs            163. Next free: 0164. This session writes at least two.
host            62.238.99.122, still on Session 12's RELEASE (936fe09).
                3814 MB total, 2171 available, **NO SWAP**. 16 containers.
evidence        Session 13's merged: status not_run, 66 passed / 12 not_run /
                0 failed. Session 14 inherits those twelve as not_run.
```

**Three facts shape this session, and all three were measured before it was
planned:**

1. **`/metrics` has been reserved since Session 1** and never used (D760). ADR
   0005 reserved it as *"a promise the platform makes about a route it will one
   day own."* This is that day, thirteen sessions later.
2. **The memory question is the session** (D761). 1,536 MB is already *budgeted*
   to two database containers that are not currently using it, on a machine with
   no swap. An OOM here is a kill.
3. **Correlation already exists and is proved** (D763). `OPS-LOG-001` spans
   ingress → MCP → PostgREST → the audit row, since Session 11 and migration
   0022. OpenTelemetry is a **transport for telemetry that already flows**, not a
   new correlation id.

---

## 0. Where Session 14 starts

Session 13 closed complete: `CURRENT_SESSION` 13, `template_version` 0.2.0, ADRs
0162 and 0163, evidence merged at **66 passed / 12 not_run / 0 failed**. The
twelve are proofs nobody ran — declarations an operator did not supply on a
read-only trip — and they carry into this session unchanged.

**The host still runs Session 12's release.** Session 13 deployed nothing by
design; its whole subject was the plan that precedes a mutation. **Session 14 is
the first Stage 2 session that must actually deploy**, because a metrics surface
that is not running is not a metrics surface.

Three `OPS-*` requirements exist: `OPS-001` (the doctor, eight live checks),
`OPS-HEALTH-001` (the reserved health route) and `OPS-LOG-001` (log
correlation). This session extends that family and opens `CAP-*`.

---

## 1. The divergence table

Six columns, the house shape. **Every row is a fact measured against the tree and
the live host at planning time**, not a prediction.

**Next free number after this table is D765.**

| # | The plan says | The repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D760** | Session 14 adds a metrics surface, so it needs a route for it — and adding a route means deciding a path and defending it against collision. | **The path was decided in Session 1 and defended ever since.** `RESERVED_BASE_PATHS` has held `/metrics` since ADR 0005, beside `/health`, `/healthz` and `/ready`, all four described there as *"the `OPS-001` surface"*. The reservation is enforced in `config.paths_overlap()` and **cannot be lifted by a deployment**: *"The tuple is not exposed in `project.yaml`. A deployment cannot un-reserve `/metrics` locally, which is the point."* | **The route is not designed; it is claimed.** Session 14 uses a reservation that has been waiting thirteen sessions, and adds nothing to `RESERVED_BASE_PATHS`. | ADR 0005 called a reserved path *"a promise the platform makes about a route it will one day own"* — and then nothing owned it for thirteen sessions. **A reservation nobody redeems is indistinguishable from a reservation nobody needed**, which is the argument for checking, before designing a surface, whether the last person to think about it left something behind. | 0005 |
| **D761** | The Stage 2 plan calls this *"the one session in the spec's mandatory core that is genuinely empty"*, so its constraint is effort. | **Its constraint is memory, and there is less than it looks.** Measured on the host: **3,814 MB total, 1,643 used, 2,171 available, and NO SWAP.** Two PostgreSQL containers carry `memory_limit_mb: 768` **each** — 1,536 MB *budgeted* to processes not currently claiming it. Sixteen containers run today. Load average ~1.0. | **Run 1 measures what an observability plane costs before Run 2 designs one**, with a control, and **the session's shape is contingent on that number.** If a collector plus a store does not fit beside a database that may claim its full budget, the answer is a smaller surface — not a bigger host and not a reduced database budget. | **No swap means an OOM is a kill, not a slowdown**, and the thing killed is chosen by the kernel rather than by this repository. A metrics stack that evicts a PostgreSQL container has made the deployment less observable, not more. **"Empty" describes the code, not the room it has to run in.** | 0131 |
| **D762** | Session 14 adds at least one container, so it adds at least one pinned image to `versions.in.yaml`. | **That file cannot be touched cheaply.** D754, measured in Session 13 Run 8: `versions.env` records a SHA-256 of the whole of `versions.in.yaml`, so **a comment invalidates the lock**, `--update` is the only way to revalidate it, and `--update` re-resolves every rolling tag while it is there. Three moved on a comment: `POSTGRES_IMAGE` (`pg18`), `PYTHON_RUNTIME_IMAGE` (`3.12-slim`), `TRAEFIK_IMAGE` (`v3.7`). | **Snapshot `versions.env`, run `--update`, restore every digest that is not this session's, `--check`.** The procedure is written into the run rather than left as a caution, and the diff is read line by line. | **D540 has been open for four sessions saying the drift is real.** Session 13 measured how little it takes; Session 14 is the first session since that must add an image, so it is the first that pays. **Adopting a new PostgreSQL image as a side effect of adding a metrics collector is exactly the unintended change a digest pin exists to prevent**, and it would arrive under a commit message about observability. | 0077 |
| **D763** | The specification: *"Add OpenTelemetry propagation through Traefik, FastAPI, FastMCP, protected downstream HTTP calls…"* — read as building request correlation. | **The correlation exists and is proved.** `OPS-LOG-001` is a Session 11 claim, green in Session 13's evidence, spanning **ingress → FastMCP → PostgREST → `app_private.agent_audit.request_id`** (migration 0022, ADR 0160). `mcp_telemetry.py` already emits one structured record per tool call with a documented forbidden list and a canary scan behind it. | **OTel is adopted as a TRANSPORT for telemetry that already flows**, not as a new identifier. Nothing re-derives a request id; the existing one becomes a trace context. The first exit criterion of the spec's Session 14 — *"one agent write correlated across ingress, FastMCP, downstream API, PostgreSQL and audit"* — **is already met and the plan says so** rather than re-proving it. | **A session that re-derived the request id would produce a second authority for one value** (ADR 0002), and this repository has paid for that twice in one session already (D680, D682). The budget belongs to metrics and alert rules. | 0160, 0002 |
| **D764** | `MCP_MEMORY_LIMIT_MB` is 384 and ADR 0131 measured the floor as `128 + share × 4`, so the limit is understood. | **It was measured for the INTERPRETER, not the container**, and CLAUDE.md §9 has said so since Session 8: *"reading a running container's resident set is one command, and it is the number a limit actually bounds."* Eight sessions; still unread. `MCP_MEMORY_LIMIT_MB = 384` lives in `rendering.py:727` and is **inherited rather than derived** per its own comment. | **Read in Run 1, beside the host's own memory figures**, because the same command answers both questions. | **It stopped being a tidy loose end the moment memory became the session's constraint** (D761). A plane whose limit was set from an interpreter measurement is a plane whose real headroom nobody knows — and Session 14 proposes to run new processes beside it. **The cheap open item and the expensive design question are the same measurement.** | 0131 |

---

## 2. What Session 14 adds to the acceptance registry

`CURRENT_SESSION` moves to **14**, all-or-nothing (D690): every requirement below
stops being a placeholder in the commit that moves the constant.

**Each claim needs a live proof in exactly one mode** (D720/D721) — decided when
the node ids are written, not discovered at merge time.

| Requirement | Guarantee | Family |
|---|---|---|
| `OPS-METRIC-001` | The reserved `/metrics` route serves a metrics surface for a deployed project, and serves it to nobody who is not authorised | `OPS-*` |
| `OPS-ALERT-001` | A deliberately induced failure — backup, WAL, disk, service health, certificate — produces an alert, and a healthy deployment produces none | `OPS-*` |
| `OPS-REDACT-001` | No token, URL, object key or caller value reaches the telemetry plane, proved by planting a value nothing else could produce | `OPS-*` |
| `CAP-ENV-001` | A capacity envelope with **measured** numbers, each stating the conditions it was sampled under | `CAP-*` |

**`OPS-ALERT-001` needs both halves and they are different guarantees** (D70):
that an alert fires for a real failure, and that a healthy deployment is quiet.
**The second is the harder one** and the one this repository has learned to
demand — a rule that fires always is `failed_count > 0` again (D553), and a rule
that never fires is `postgrest --ready` (D145).

`REL` and `CAP` join `ID_PATTERN`'s enumeration, which stays enumerated (ADR
0006).

---

## 4. Irreversible operations

**1. Deploying Session 14 to the host.** The first Stage 2 deploy. `deploy.sh
--through-session 14`, root at a TTY. It recreates any container whose mounted
*content* changed (ADR 0155), so a metrics configuration file is a recreation
trigger — which is the mechanism working and worth expecting rather than
discovering.

**2. Adding an image to `versions.in.yaml`.** D762's procedure, every time:
snapshot `versions.env`, `--update`, restore every digest that is not this
session's, `--check`, and read the diff line by line.

**3. Moving `CURRENT_SESSION` to 14 and `VERSION` to 0.3.0.** One commit. ADR
0162 decides what a minor bump permits — and **a metrics surface is a new
published route**, so if it reaches the API contract this is a minor at least.
If a migration is required it is still minor, **and then image rollback stops
being available** (ADR 0162 §3), which the plan says before the deploy rather
than after.

**4. Publishing an alert rule that pages.** Nothing here pages anybody yet, and
that is deliberate: **a rule with no measured false-positive rate is not a rule
anybody should be woken by.** `OPS-ALERT-001` proves a rule fires and stays
quiet; routing it to a human is a later decision.

---

## 5. Build order

Runs are the unit. CLAUDE.md §5 applies to each: **measure third-party behaviour
with a control before writing anything that depends on it**, write the ADR when
the measurement decides something with alternatives, implement, then **try to
break the tests** with a mutation battery whose failures are fatal (D269), whose
control is a test the mutation cannot reach (D499), and which asserts *how* each
mutation failed (D386).

### Run 1 — What fits, measured before anything is designed

The session's shape is contingent on this run, so it comes first and it decides.

- **The host's real headroom.** Total, used, available, swap — and **what each
  container actually holds**, which needs `docker stats` under root and answers
  D764 in the same command. `MCP_MEMORY_LIMIT_MB` is 384 and nobody has read the
  resident set it bounds.
- **What a collector and a store cost.** Measured by running them, not by reading
  a vendor's page. **With a control**: a rig that reports a number for a
  container that is not running has measured nothing.
- **Whether Traefik publishes metrics at the pinned digest**, and on which
  entrypoint. Measured against `TRAEFIK_IMAGE` as locked, because a feature
  present in `v3.7` generally is not a feature present in the digest deployed
  here.

**Nothing is designed until this reports.** If the honest answer is that a store
does not fit, the surface shrinks — a scrape endpoint with no local retention is
still `OPS-METRIC-001`, and an envelope measured by an off-host load generator is
still `CAP-ENV-001`.

### Run 2 — The metrics surface, on the route Session 1 reserved

`/metrics` (D760). Two decisions with alternatives, so **at least one ADR**:

- **Who may read it.** A metrics surface is a description of the deployment's
  internals, and the reserved path sits behind the same edge as everything else.
  **The default is that it is not public**, and the proof is `OPS-METRIC-001`'s
  second half.
- **Whether it is per-project or per-host.** The naming plane derives everything
  per project (ADR 0002), and a metrics surface that aggregates two projects is a
  place their identities meet.

### Run 3 — OpenTelemetry as a transport, not an identifier

The existing request id becomes the trace context (D763). **Nothing re-derives
it.** Propagation through Traefik, the auth API, FastMCP and the protected
downstream calls, with `mcp_telemetry`'s forbidden list applying unchanged to
whatever the new transport carries.

**The redaction canary is extended to the new surface in the same run**, not a
later one: a telemetry plane that ships spans is a second place a presigned URL
can reach, and Session 7's canary exists because one did.

### Run 4 — Metrics that answer a question somebody has

Pooler saturation, database connections against the five claimants of
`max_connections` (ADR 0099/0148), transaction duration, PostgREST latency and
errors, **MCP calls and denials by reason**, audit-write failures, backup and WAL
freshness, disk headroom.

**Two of these already have a source and must not grow a second** (ADR 0002):
backup state comes from `bin/backup.py info --json` (ADR 0149/0150), and the
archiver from `pg_stat_archiver`. **`failed_count` is cumulative and cannot
answer a point-in-time question** — it stood at 26 on a healthy cluster (D553),
and a metric that exports it as a gauge re-creates that defect in a dashboard.

### Run 5 — Alert rules, and the quiet half

A rule per failure class, each with **both** proofs: it fires when the failure is
induced, and it is silent on a healthy deployment. `OPS-ALERT-001`.

**Inducing the failures is the work**, and each has a safe method already in the
repository: `bin/backup.sh` can be pointed at a broken stanza, disk pressure can
be simulated against a threshold rather than by filling a disk, and a certificate
deadline is arithmetic on a date the deployed document already carries.

**Nothing pages anybody** (§4.4).

### Run 6 — The capacity envelope

Load scenarios: pooled database clients, REST reads and writes, MCP reads and
writes, and **backup behaviour under load**. Then the timeout and pool tuning,
then the envelope.

**Every number states the conditions it was sampled under**, and one condition
dominates: **`process-max` is 1**, so a 31 MB backup takes six minutes and a
restore is ~1,330 serialised S3 round trips — latency, not bandwidth (D593,
D603). **An envelope number taken under backup load is a sample from a band**, and
the envelope says so or it is a number about nothing.

**No replica and no cache.** This run produces the evidence that would justify
one later; that is the whole of its relationship to them.

### Run 7 — The bump

`CURRENT_SESSION` 14, `VERSION` 0.3.0, every requirement activated, and
`bin/session-14-check.sh` **derived by diff** from Session 13's — registered in
`SHELL_COMMANDS`, and **its printed session numbers derived from `${SESSION}`**,
which Session 13 made possible and which the D751 guard now enforces.

### Run 8 — The host trip

**This one deploys.** Unlike Session 13's, it is a mutating trip: `deploy.sh
--through-session 14` at a TTY, then the host gate, then external, then merge.

**Expect more than one round.** Sessions 7 and 8 found seven and eight defects on
theirs, and this is the first trip in three sessions that changes what runs.

---

## 7. Evidence and claims — what may honestly be reported

Unchanged: verdicts are computed from the registry's node ids and JUnit results,
never hand-entered; a filtered run writes nothing; both halves must describe the
same release or the merge refuses.

**Since ADR 0163 the statuses are three**, and this session is the first planned
under them: `failed` means the system is wrong, `not_run` means the evidence is,
and both exit 5. **A metrics claim that skips for want of a flag reports
`not_run`, and that is now a sentence the document can say.**

**Session 13's twelve `not_run` claims carry in unchanged.** Session 14 does not
close them and must not appear to — `documented_path`, `fresh_host` and
`project_removal` need declarations, and `bootstrap_identity` needs D683's code.
**A session that half-closes another's requirement without saying so leaves the
next reader unable to tell a proved guarantee from a plausible one** (D478).

**`CAP-ENV-001` is the claim most at risk of being reported dishonestly.** An
envelope is a document, and a claim over a document can go green because the
document exists. Its node ids must assert **that the numbers were measured in the
run that published them** — a stale envelope beside a changed deployment is
D700's stale `backup_state` in a new place.

---

## 8. Security invariants this session touches

| Invariant | Control | Where this session puts it at risk |
|---|---|---|
| No token, URL, object key or caller value in telemetry | `mcp_telemetry`'s forbidden list, and Session 7's canary | **A span is a new carrier**, and OTel's defaults attach more than a log line does (Run 3) |
| A metrics surface describes the deployment to whoever reads it | The reserved route, behind the edge | Run 2's first decision. **The default is not public** |
| One project's identities do not meet another's | Derivation per project (ADR 0002) | A host-scoped metrics store is a place they would (Run 2) |
| The MCP runtime holds no credential | `FORBIDDEN_VARIABLES`, `McpSettings`' shape | A collector endpoint is a new setting, and a URL is not a credential — but a bearer token for one is |
| The database container's egress is the known residual | ADR 0147 | **Do not add a second.** A collector reachable from the database network widens a boundary already named as this deployment's one genuine residual |
| A deploy over a broken archiver fails | Step 6c's `pgbackrest check` | Unchanged, and Run 5 induces exactly this failure — **against a project that is not carrying data anybody needs** |

---

## 9. Risks and stop conditions

**Stop and ask** rather than proceeding, when:

- **an observability plane does not fit** and the proposed remedy is reducing a
  database's memory budget or adding swap. Both change what the deployment *is*,
  and Run 1 exists to find this out before anything is built;
- a metric would need a second source for a value that already has one — backup
  state and the archiver each have one (ADR 0149/0150);
- an alert rule cannot be shown to stay quiet on a healthy deployment;
- an envelope number would be published without the conditions it was sampled
  under (D593, D603);
- adding an image would require accepting a rolling-tag re-adoption rather than
  restoring it (D762);
- OTel propagation would introduce a second request identifier (D763);
- a Session 13 claim goes red and the tidy fix is on the proof's side.

**The failure mode this session is most exposed to** is the one the Stage 2 plan
named and Session 13 confirmed five times: **re-implementing something that
already exists, one layer over.** Correlation exists. The route exists. The
backup and archiver signals exist and have one source each. **What is genuinely
absent is narrow** — a transport, a store, a rule set and a measurement — and
everything around it is already built.

**Question 5 is live throughout.** A metric is a new *reader* of a value some
other decision owns, and this repository's most common defect is a decision whose
readers were not all updated. Every metric added should be able to name the
decision it reads from.

---

## Appendix — what to consult, and what to measure instead

**Consult:** `docs/plans/stage-2-plan.md` §1 and §3. **ADR 0005** (the route
reservation, and why `/metrics` was held for thirteen sessions). **ADR 0131**
(the MCP memory limit, and what it actually measured). **ADR 0099/0148** (the
five claimants on `max_connections`). **ADR 0149/0150** (what the repository and
the archiver can each honestly report — and D553, why a cumulative counter cannot
answer a point-in-time question). **ADR 0160** (the request id flows outward).
**ADR 0155** (a deploy recreates a container whose mounted content changed).
**ADR 0163** (three statuses, new since Session 13).

**Measure instead of consulting:** what a container actually holds; whether
Traefik publishes metrics **at the pinned digest**; what a collector costs when
it is running; and what a load generator does to a deployment whose `process-max`
is 1.

**Before measuring how a third party behaves, `grep` the plans for it.** Nothing
indexes the ~764 measured facts in the divergence tables by subject — and for
this session the grep already paid: `/metrics` turned up in Session 1's plan and
ADR 0005, thirteen sessions before anybody needed it.

**Never write a measurement you did not run** (D267).
