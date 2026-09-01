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
SESSION 14 IS IN PROGRESS. Run 1 is COMPLETE; Run 2 is next.
CURRENT_SESSION 13; it moves to 14 in the bump run -- ALL-OR-NOTHING (D690).
template_version 0.2.0 -> 0.3.0, and ADR 0162 decides what that permits.
divergences     D760-D772 recorded here (D765-D771 are Run 1's; D772 is Run 2's
                first finding). **Next free: D773.**
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

**Next free number after this table is D773.**

| # | The plan says | The repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D760** | Session 14 adds a metrics surface, so it needs a route for it — and adding a route means deciding a path and defending it against collision. | **The path was decided in Session 1 and defended ever since.** `RESERVED_BASE_PATHS` has held `/metrics` since ADR 0005, beside `/health`, `/healthz` and `/ready`, all four described there as *"the `OPS-001` surface"*. The reservation is enforced in `config.paths_overlap()` and **cannot be lifted by a deployment**: *"The tuple is not exposed in `project.yaml`. A deployment cannot un-reserve `/metrics` locally, which is the point."* | **The route is not designed; it is claimed.** Session 14 uses a reservation that has been waiting thirteen sessions, and adds nothing to `RESERVED_BASE_PATHS`. | ADR 0005 called a reserved path *"a promise the platform makes about a route it will one day own"* — and then nothing owned it for thirteen sessions. **A reservation nobody redeems is indistinguishable from a reservation nobody needed**, which is the argument for checking, before designing a surface, whether the last person to think about it left something behind. | 0005 |
| **D761** | The Stage 2 plan calls this *"the one session in the spec's mandatory core that is genuinely empty"*, so its constraint is effort. | **Its constraint is memory, and there is less than it looks.** Measured on the host: **3,814 MB total, 1,643 used, 2,171 available, and NO SWAP.** Two PostgreSQL containers carry `memory_limit_mb: 768` **each** — 1,536 MB *budgeted* to processes not currently claiming it. Sixteen containers run today. Load average ~1.0. | **Run 1 measures what an observability plane costs before Run 2 designs one**, with a control, and **the session's shape is contingent on that number.** If a collector plus a store does not fit beside a database that may claim its full budget, the answer is a smaller surface — not a bigger host and not a reduced database budget. | **No swap means an OOM is a kill, not a slowdown**, and the thing killed is chosen by the kernel rather than by this repository. A metrics stack that evicts a PostgreSQL container has made the deployment less observable, not more. **"Empty" describes the code, not the room it has to run in.** | 0131 |
| **D762** | Session 14 adds at least one container, so it adds at least one pinned image to `versions.in.yaml`. | **That file cannot be touched cheaply.** D754, measured in Session 13 Run 8: `versions.env` records a SHA-256 of the whole of `versions.in.yaml`, so **a comment invalidates the lock**, `--update` is the only way to revalidate it, and `--update` re-resolves every rolling tag while it is there. Three moved on a comment: `POSTGRES_IMAGE` (`pg18`), `PYTHON_RUNTIME_IMAGE` (`3.12-slim`), `TRAEFIK_IMAGE` (`v3.7`). | **Snapshot `versions.env`, run `--update`, restore every digest that is not this session's, `--check`.** The procedure is written into the run rather than left as a caution, and the diff is read line by line. | **D540 has been open for four sessions saying the drift is real.** Session 13 measured how little it takes; Session 14 is the first session since that must add an image, so it is the first that pays. **Adopting a new PostgreSQL image as a side effect of adding a metrics collector is exactly the unintended change a digest pin exists to prevent**, and it would arrive under a commit message about observability. | 0077 |
| **D763** | The specification: *"Add OpenTelemetry propagation through Traefik, FastAPI, FastMCP, protected downstream HTTP calls…"* — read as building request correlation. | **The correlation exists and is proved.** `OPS-LOG-001` is a Session 11 claim, green in Session 13's evidence, spanning **ingress → FastMCP → PostgREST → `app_private.agent_audit.request_id`** (migration 0022, ADR 0160). `mcp_telemetry.py` already emits one structured record per tool call with a documented forbidden list and a canary scan behind it. | **OTel is adopted as a TRANSPORT for telemetry that already flows**, not as a new identifier. Nothing re-derives a request id; the existing one becomes a trace context. The first exit criterion of the spec's Session 14 — *"one agent write correlated across ingress, FastMCP, downstream API, PostgreSQL and audit"* — **is already met and the plan says so** rather than re-proving it. | **A session that re-derived the request id would produce a second authority for one value** (ADR 0002), and this repository has paid for that twice in one session already (D680, D682). The budget belongs to metrics and alert rules. | 0160, 0002 |
| **D764** | `MCP_MEMORY_LIMIT_MB` is 384 and ADR 0131 measured the floor as `128 + share × 4`, so the limit is understood. | **It was measured for the INTERPRETER, not the container**, and CLAUDE.md §9 has said so since Session 8: *"reading a running container's resident set is one command, and it is the number a limit actually bounds."* Eight sessions; still unread. `MCP_MEMORY_LIMIT_MB = 384` lives in `rendering.py:727` and is **inherited rather than derived** per its own comment. | **Read in Run 1, beside the host's own memory figures**, because the same command answers both questions. | **It stopped being a tidy loose end the moment memory became the session's constraint** (D761). A plane whose limit was set from an interpreter measurement is a plane whose real headroom nobody knows — and Session 14 proposes to run new processes beside it. **The cheap open item and the expensive design question are the same measurement.** | 0131 |
| **D765** | Run 1 reads *"what each container actually holds, which needs `docker stats` under root"* — so the measurement is privileged and waits for a human at a TTY. | **It needs none of that.** `/sys/fs/cgroup/system.slice/docker-*.scope/memory.stat` carries `anon`, `file` and `shmem`; `memory.current`, `memory.peak` and `memory.max` sit beside it; `/proc/<pid>/mountinfo` names the bind mounts that say which container is which. All are world-readable. The whole host half of Run 1 ran as **`op` over SSH with no TTY, no `sudo`, and no reachable Docker daemon.** | **The host half of Run 1 is a read-only probe**, and the method is written down here so no future session budgets a trip for it. | **D764 stayed open for eight sessions because CLAUDE.md called it "one command" and that command was believed to need root.** A measurement that needs a human is a measurement that gets taken once. This one needs nobody — and the same read is available to `doctor.sh` and to any future gate. | 0071 |
| **D766** | *"Sixteen containers run today"*, and `apg-diag containers` agrees. | **The machine runs eighteen.** The cgroup walk found 18 scopes; `apg-diag containers` lists 16. The two it omits are the shared edge — `traefik` (21.6 MB anon) and `haproxy` (4.4 MB) — because `verb_containers` iterates `PROJECT_ROOT` and the edge is host-scoped. The 16 it lists are exactly 8 per project: postgres, pgbouncer, postgrest, auth, storage, mcp, docs, edge-probe. | **Both numbers are right about different questions, and this plan says which it means.** A capacity figure counts 18. | **The count everybody quotes comes from the diagnostic surface everybody reads, and that surface cannot see a host-scoped service by construction.** Small in megabytes, total in kind: any per-project iterator under-reports the machine, and a memory envelope derived from one is short by whatever the edge holds. | 0071, 0158 |
| **D767** | 1,536 MB is *"already budgeted to two database containers"*, so an observability plane must fit in what is left after it. | **The budget is a cap, nothing is holding it, and the caps already oversubscribe the machine.** Each PostgreSQL container holds **17.6 / 18.5 MB anon plus ~19–20 MB shmem — about 37 MB against a 768 MB cap**. Total anonymous memory across all **18** containers is **573.8 MB** on a 3,814 MB host with 2,110 MB available. Meanwhile the caps that exist sum to **3,840 MB** (2 × 768 + 6 × 384) on a 3,814 MB machine, and ten further containers carry `memory.max=max`. | **The fit question is answered against measured occupancy, and the envelope publishes occupancy and headroom separately.** `memory.max` is a ceiling the kernel permits, never a reservation it makes. | **A budget nothing is holding is not consumed memory — and a set of caps that already exceeds RAM is not a budget at all.** Reading 1,536 MB as spoken-for would have shrunk the surface for room nobody had taken; reading it as free would ignore a ceiling the kernel will honour. **Both readings are wrong in opposite directions**, which is why the envelope quotes two numbers (D593's band, applied to memory). | 0131 |
| **D768** | Run 1 asks *whether* Traefik publishes metrics at the pinned digest — a yes or a no. | **Yes, and the yes has a window in it.** `traefik:v3.7@sha256:9c3b91d5…` is **3.7.10**, and the host's checkout pins the identical digest. Polled from t=0 with `--metrics.prometheus.entryPoint=metrics`: **refused at +10 ms, HTTP 404 at +154 ms, HTTP 200 at +298 ms** — the entrypoint's TCP server starts before `prometheus@internal` is installed. The control, a metrics-**disabled** Traefik on the same entrypoint, reaches 404 at +215 ms and **stays 404 for ever**. With `entryPoint` unset the surface lands on the internal `traefik` entrypoint at **:8080**, not on `web`. | **Nothing may read a 404 from `/metrics` as "metrics are not configured."** A scrape check, an alert rule and `OPS-METRIC-001`'s proof all discriminate on the body — the `traefik_*` families — never on the status code. | **D145's family at a different vendor.** `postgrest --ready` returned 0 while every request 404'd; here two unrelated states — *scraped 150 ms too early* and *never configured* — are the same three digits. The digest was measured rather than the tag because a feature in `v3.7` generally is not a feature in the digest deployed here. This time they agreed. | 0005 |
| **D769** | Run 4 names the metrics that answer a question somebody has; Run 5 writes a rule per failure class over them. | **The exported family set is not fixed — it grows with traffic.** At the pinned digest a freshly started Traefik exports **3** `traefik_*` families (`config_last_reload_success`, `config_reloads_total`, `open_connections`). After five requests crossed an entrypoint it exports **7**: the arrivals are `traefik_entrypoint_request_duration_seconds`, `_requests_bytes_total`, `_requests_total` and `_responses_bytes_total`. | **Every alert rule states explicitly what it means by an absent series**, rather than assuming the series exists and reads zero. | **A deployment that has served no request and a deployment whose exporter is broken produce the same empty result.** A rule over `traefik_entrypoint_requests_total` on a quiet deployment is evaluating nothing and reporting healthy. **D553 inverted** — there a cumulative counter answered a point-in-time question; here a point-in-time series does not exist yet — and both are one mistake about when a number means anything. | 0149, 0150 |
| **D770** | Run 1 measures *"what a collector and a store cost"* — a number per candidate. | **A store's memory is a function of the machine it lands on, not of the workload.** Unbounded on the 7,786 MB rig, VictoriaMetrics logs *"limiting caches to 4898660352 bytes … according to -memory.allowedPercent=60, system memory limit 8164433920"* and climbed past 63 MB still rising. The same image under `--memory=192m` logs *"limiting caches to 120795955 bytes … system memory limit 201326592"* and settles at **45.6 MB**. Bounded, against a real scrape target with ingestion confirmed at both ends of the run: **Prometheus 21.2 MB anon (peak 37.4), otelcol-core 14.3 (16.7), Alertmanager 10.3 (12.3), VictoriaMetrics 45.6 (48.2)**. Nothing was OOM-killed. | **Every store or collector deployed here carries an explicit container memory limit**, and **no unbounded number measured off-host may be quoted for the host.** Which store is Run 2's choice, now a choice between measured numbers. | **An unbounded store on the 3,814 MB host would size caches to roughly 2.3 GB**, on a machine with no swap where the kernel picks the victim. The reputation inverts under measurement too: VictoriaMetrics has the smallest image (17.5 MB against Prometheus's 104.3 MB) and **twice the resident set**. ADR-shaped, and the ADR belongs to Run 2 where the store is chosen. | 0131, 0155 |
| **D771** | D761: *"No swap means an OOM is a kill, not a slowdown"* — the risk this session is built around. | **Whether it has ever happened here is unknown, and the first reading said it had not.** `grep -c` over `journalctl -k` returned **0** OOM lines, which reads as a clean history. The control — total kernel journal lines over the same window — returned **1**, and that line is *"Hint: You are currently not seeing messages from other users and the system."* followed by `-- No entries --`. `op` is in `op, sudo, users`; the journal is `root:systemd-journal 0640` and `dmesg` is restricted. | **The host's OOM history is recorded as UNKNOWN.** Reading it needs root, or `op` in `adm`/`systemd-journal` — a decision, not a command. | **A zero meaning "no access" and a zero meaning "no kills" are the same character**, and the comforting one is the wrong one. It was caught only because the control counted total lines instead of trusting the filtered count — and it nearly passed anyway, because the threshold asked for *more than zero* and got exactly one. **§7's defect, produced by the rig built to avoid it.** | 0071 |
| **D772** | Run 2 attaches the platform middleware chain to a new `/metrics` router, and `BASELINE_MIDDLEWARE_CHAIN` is that chain. | **`apg-response-policy` is attached to nothing, on any route, in production — and has been since Session 5 defined it.** `baseline.yaml` defines four middlewares and an `apg-baseline` chain of three, saying the chain is *"what project routers attach"*. **Project routers attach neither.** `host_config.BASELINE_MIDDLEWARE_CHAIN` enumerates `apg-security-headers@file,apg-rate-limit@file` — two of the three — and every router label interpolates that constant. Measured live on `alpha-dev`: the router label is `…middlewares=apg-security-headers@file,apg-rate-limit@file,…api-buffering,…api-stripprefix`, `GET /api/rest` returns **`server: postgrest/14.16` and no `Cache-Control`**, and no entrypoint-level middleware supplies it (`traefik.yaml`'s `websecure` carries only `transport`). | **Repaired in Run 2, by the user's decision.** `BASELINE_MIDDLEWARE_CHAIN` becomes the single name `apg-baseline@file` rather than a corrected enumeration — the enumeration was the wrong *shape*, and naming the chain is what `baseline.yaml` always intended so that *"adding a baseline middleware later does not require touching any project."* Measured first against the locked Traefik, because the existing proof only covered an unsuffixed same-provider reference: subject drops `Server` and adds `no-store`; a control carrying the old enumeration **reproduces the defect offline**. Guarded by `test_every_middleware_baseline_defines_is_attached_to_project_routes`, which reads from the constant outwards. **It reaches the deployment at Run 8, not before** — the host still runs Session 12's release. | **`apg-response-policy` is the middleware that sets `Cache-Control: no-store`**, and `baseline.yaml`'s own rationale says why it exists: *"every row the REST surface returns is selected by a row policy keyed on the requester's identity, so a shared cache holding one is holding one caller's data under a URL another caller will ask for."* That protection is absent from the deployed REST surface. **Two green tests assert the chain's contents and neither can see that nothing attaches it** — `test_the_baseline_chain_exists_and_is_referenced_by_name` is *named for* the property that is false. And `test_edge_behaviour.py`'s fixture attaches `apg-baseline`, so the behavioural proof of `apg-response-policy` runs by a route the product does not take (ADR 0065/0066), written by the author of the code it agrees with (§7 question 6). **Question 5's shape exactly**: Session 5 added a middleware and one reader of the chain never moved. | 0065, 0066, 0009 |

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

**Done.** — D765–D771. **The fit question has a yes, and the surface does not
have to shrink.**

**The numbers.** A bounded plane of **Prometheus + otelcol-core + Alertmanager
settles at 45.8 MB anon** (66.4 MB summing peaks) against a host holding
**573.8 MB across 18 containers** with **2,110 MB available**. Substituting
VictoriaMetrics makes it 70.2 MB. **None of §9's stop conditions fired**: no
store had to be dropped, no database budget was touched, and nothing was
OOM-killed under a deliberately tight cap.

**The database budget was the wrong thing to be afraid of** (D767). The two
clusters hold ~37 MB each against 768 MB caps; the caps in aggregate already
exceed the machine's RAM, so they were never a reservation anybody could spend
against. **The constraint is real but it is not where D761 put it** — it is that
an *unbounded* store sizes itself from the machine (D770), which is a
configuration decision rather than a shortage.

**D764 is answered, and it took no root.** The MCP containers hold **89.1 MB
(alpha) and 88.0 MB (beta) anon, peaks 116.5 / 116.0 MB, against
`MCP_MEMORY_LIMIT_MB = 384`** — about 3.3× headroom on peak. ADR 0131's
`128 + share × 4` interpreter floor was not the binding number. The two were
identified positively, by the capability lock and JWKS they mount: they are the
only containers on the host that mount **no credential at all**, which is the
agent plane's invariant turning up in a measurement that was not looking for it.

**What the rig cost, because two of its own parts were the defect** (§7's
standing pattern, and both were caught by controls rather than by inspection):

- **`date` on this machine is uutils coreutils 0.8.0, not GNU**, and it silently
  ignores the width in `%3N` — `date +%s%3N` returns seconds followed by *nine*
  digits. A readiness poller read that as milliseconds, computed an elapsed time
  of ~1.01 × 10⁹ ms, broke on its first iteration and reported `polls=0`: a rig
  printing a result while measuring nothing. **The fatal clock preflight is the
  only reason it did not become a finding.**
- **The ingestion control produced a false negative and condemned a working
  store.** It asked `up` through `/api/v1/query`; VictoriaMetrics defaults to
  `-search.latencyOffset=30s`, so a query at t+25 s evaluates at t−5 s and
  returns an empty vector. VM had been scraping throughout — 48 samples per
  scrape, target `health: "up"`. **A control that fails for a reason unrelated to
  what it watches is D509's rule inverted**, and it is the more dangerous
  direction: this one would have thrown away a correct measurement rather than
  passing a wrong one. Rewritten onto `/api/v1/targets` and
  `/api/v1/status/tsdb`, neither of which is latency-offset.

**What Run 2 inherits as decided-by-measurement rather than open:** the route
exists and is unredeemed (`/metrics` appears once outside tests, at
`config.py:66`); Traefik serves the surface at the deployed digest but a 404
means two different things (D768); the exported family set is dynamic (D769);
and any store carries an explicit container limit (D770), which is the ADR
Run 2 writes.

**Not measured, and it is Run 6's problem rather than Run 1's:** every figure
here is an *idle* plane scraping one target. The envelope's numbers come from
load, and this run bounds the floor, not the band.

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
