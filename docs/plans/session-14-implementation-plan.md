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
SESSION 14 IS IN PROGRESS. Runs 1-5 are DONE. **RUN 6 IS NEXT.**
HEAD af90f4e, main, clean and pushed.
CURRENT_SESSION 13; it moves to 14 in Run 7 -- ALL-OR-NOTHING (D690).
template_version 0.2.0 -> 0.3.0 there too; ADR 0162 says what that permits.
divergences     D760-D789 (D765-D771 Run 1; D772 Run 2; D773 Run 3;
                D774-D781 Run 4; D782-D789 Run 5).
                **Next free: D790.**
ADRs            168. **Next free: 0169.** This session has written 0164 (the
                metrics surface), 0165 (a telemetry component's memory limit),
                0166 (the trace id is the request id), 0167 (a metric reads
                from the decision that owns its value) and 0168 (a rule states
                what its silence means).
outputs schema  still v13. Publishing /metrics needs v14 + a migration and is
                deferred to Run 7, deliberately (Run 2's Done marker).
host            62.238.99.122, still on Session 12's RELEASE (936fe09); its
                CHECKOUT is at 8858246, which is a different thing.
                3814 MB total, 2110 available, **NO SWAP**.
                **18 containers, not 16** (D766) -- apg-diag lists 16 because it
                cannot see the shared edge.
suite           af90f4e has NOT had the full suite or the gate. Targeted only:
                tests/contract/ 4477 passed / 3 skipped, ruff clean. Last full
                run was 4516 / 294 at fd37d53.
                **Do not gate at a run close.** Before the Run 8 trip, or when
                asked -- nowhere else.
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

**Next free number after this table is D790.**

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
| **D773** | Run 3 adopts OTel as a transport, with `mcp_telemetry`'s forbidden list *"applying unchanged to whatever the new transport carries."* | **Unchanged is not enough: a span records a caller's value with nobody writing a line of code.** Measured against `opentelemetry-sdk` 1.44.0, with a planted canary and a clean control. An exception merely **escaping** a span makes the SDK attach `exception.message`, `exception.stacktrace`, and a `status.description` of `"ValueError: <the message>"`. `record_exception` and `set_status_on_exception` both default to **on**. The control span, which never saw the value, came back clean — so this is a path rather than rig contamination. | **Both defaults are turned off, and span attributes are ENUMERATED** the way `RECORD_FIELDS` enumerates a log record's. **The canary is extended to spans in this run**, not a later one. | `mcp_telemetry` already refuses precisely this for log lines — *"an unclassified failure is logged with the exception's TYPE and never its message, because a message is where a caller's value would be if one ever reached one."* **The span carrier arrives with that refusal reversed by default.** D449 measured that a logged traceback carries no caller data *because `show_locals` is off*; this is the same question asked of a different framework and answered the other way. §8 predicted it in one line — *a span is a new carrier, and OTel's defaults attach more than a log line does* — and this measurement is what turns that sentence into a control. | 0130, 0164 |
| **D774** | Run 4's metrics are per project, and the collector is per project, so filtering the shared edge's exposition to this project is a matter of matching its names. | **A prefix over the project key admits a DIFFERENT project.** The key pattern is `^[a-z][a-z0-9-]{4,47}$` — it permits hyphens — so `alpha` and `alpha-two` are two lawful keys on one host and every router of both matches `apg-alpha-.*`. Measured against the locked Traefik and the locked collector, four routers across three projects: the prefix form admitted **20 series belonging to `alpha-two`** onto `alpha`'s surface. The enumerated form dropped all 20, kept this project's 20, and dropped `beta`. | **The filter is `naming.project_router_names(key)`** — the exact names, from the same `*_router_name` functions the identity is built from. The prefix form is retained as the proof's control, because it must still leak or the enumeration's refusal is unmeasured. | **D300 reaching a place that looks like string formatting.** *"Never weaken an allowlist to a subset check"* does not stop applying because the allowlist is spelled as a regex — and a prefix over a derived name IS a subset check. The failure mode is the quiet one in both directions: a foreign project's series arrive with nothing marking them foreign, and a router missing from the enumeration produces **no series at all**, which is indistinguishable from a route nobody used. | 0167, 0002 |
| **D775** | Run 2 measured that Traefik publishes metrics at the pinned digest, and D768 recorded that with `entryPoint` unset the surface lands on the internal `traefik` entrypoint at **:8080**. | **This deployment binds `web` to :8080, so unset is not a default — it is an outage.** Measured against the locked digest with `infra/edge/traefik.yaml`'s own entrypoint layout: Traefik refuses to start with *"error while building entryPoint web: building listener: error opening listener: listen tcp :8080: bind: address already in use"*. The control — the same configuration with `entryPoint` set — answers **404** on :8080/metrics and **200** on :8089/metrics with the seven base families. | **The entrypoint is named explicitly in the static configuration**, with the measurement in a comment beside it, and `test_the_edge_publishes_metrics_on_an_entrypoint_it_names_explicitly` refuses its removal. | **It fails closed and loudly, which is the good half.** The bad half is that the thing that fails is the **shared** edge: one omission in a file that serves every project on the host costs all of them their ingress simultaneously. D768 measured the window and assumed the collision would be a metrics problem; on this host it is an ingress problem. | 0167, 0005 |
| **D776** | Run 5 writes a rule per failure class over the metrics Run 4 names, so naming a metric fixes what a rule refers to. | **The exposed name is not the name the source writes, and the rename is not cosmetic.** Measured through the locked collector: dots become underscores, a counter gains `_total`, and **the unit abbreviation is EXPANDED into the name**. `agent.tool_calls` (unit `1`) is served as `agent_tool_calls_total`; `agent.tool_call.duration` (unit `ms`) is served as `agent_tool_call_duration_**milliseconds**`. Every series also gains `otel_scope_name`, `otel_scope_version` and `otel_scope_schema_url` — two of them empty — and a synthesised `target_info` carries **every resource attribute verbatim**. | **`mcp_metrics.EXPOSED_METRIC_NAMES` is the mapping, as a declared constant with a test behind it**, and Run 5's rules are written against its right-hand side. Nothing but `service.name` goes in the OTel `Resource`. | **A rule written against the source name matches nothing**, and matching nothing is this family's silent failure — a rule over an absent series evaluates and reports healthy. Changing an instrument's unit is a silent rename of a series something depends on, which is why the mapping is a constant rather than folklore. **And a `Resource` is published, not metadata**: whatever is put there is served as a label to every reader of the route. | 0167 |
| **D777** | The metrics surface reports what is happening now. | **A series outlives the process emitting it by five minutes.** Measured: with the emitter stopped, the deployed pipeline still served its gauge at **t+40s**; the control, a collector with `metric_expiration: 10s`, dropped the same series between t+5s and t+10s — so the two states are distinguishable and this is a setting rather than a hope. | **`metric_expiration` is explicit at 60s.** An absent series has three meanings — never emitted, nothing to report, emitter stopped — and only `up` separates the third. `up` and the `scrape_*` series survive `metric_relabel_configs` (measured: the receiver synthesises them afterwards), so the distinction stays available to Run 5. | **D145's family in a new place.** `postgrest --ready` returned 0 while every request 404'd; here a gauge reads `2 in flight` from a container that died four minutes ago. The state is in the freshness, never in the value — and the default is five minutes of a dead process reading as current. | 0167, 0149, 0150 |
| **D778** | D777's expiration makes a stopped emitter visible. | **Set naively it makes a RUNNING emitter flicker.** The OTel SDK's export interval defaults to **60000 ms** — read in its own source, falling back through `OTEL_METRIC_EXPORT_INTERVAL` to `60000` — and `metric_expiration` had been set to 60s. A series would have expired at exactly the cadence it was refreshed, appearing and vanishing according to which timer won. | **The export interval is explicit at 15s, four per expiration window**, and `test_a_metric_series_is_refreshed_several_times_before_it_can_expire` asserts the relationship. | **One property held in two processes' configuration, and nothing else would notice them drifting.** It was caught only because the verification rig read the real exposition and found it empty after 8s — a test asserting `configure()` returned True would have passed, and the flap would have arrived in Run 5 as alert rules that fire and clear at random. **The repair for D777 created this, in the same edit.** | 0167 |
| **D779** | A counter's series continues across a service restart, so a `rate()` over it is continuous. | **`instance` is a UUID minted per process.** Measured: two emitter runs against one collector produced **two live series for one counter**, both served, distinguished only by an `instance` label neither this deployment nor the collector chose. Combined with D777, a restart leaves a stale twin holding the pre-restart value for a full expiration window. | **Recorded, not repaired.** Run 5's rules aggregate away from `instance`. Nothing tries to make the label stable, because a stable value would have to be derived from something and no second authority is available for it. | **A reset and a fork look alike in a graph and are not alike in a rule.** Worth writing down because the obvious repair — pinning `service.instance.id` to something — would put a new identity in the `Resource`, and D776 measured that everything in the `Resource` is published verbatim. **The tidy fix for this one lands on the surface the redaction rule guards.** | 0167 |
| **D780** | Run 4 exports pooler saturation, database connections against the five claimants of `max_connections`, and transaction duration. | **All three need a database credential, and a process holding one is a SIXTH claimant.** `config.connection_claimants` sums every claimant and `config.py:1087` raises when they exceed the manifest's ceiling. ADR 0148 took an entire run to move that count from four to five, with a measured `CONNECTION LIMIT` and five named privileges. | **Not built, by the user's decision, and recorded here with the measurement rather than left as an omission.** The three metrics wait for an ADR of their own. | **Acquiring a claimant on a guarded budget as a SIDE EFFECT of a metrics run is exactly what that guard exists to prevent** — and it would arrive under a commit message about observability, which is the sentence D762 uses about adopting a PostgreSQL image while adding a collector. The preflight would have caught an over-commit on a deployment whose ceiling was tight; it would **not** have caught the fact that nobody decided to spend the connection. | 0167, 0070, 0148 |
| **D781** | The collector scrapes the proxy by name, so registering an alias on the attachment is enough. | **`attach` returns early on an already-attached proxy, and every existing deployment is one.** `is_attached` tested network membership only, and an alias can be registered **only** by `docker network connect --alias` — it cannot be added to a live endpoint. So the alias would have reached exactly the projects created after this release and no others. | **The alias is now part of what "attached" means.** `has_alias` gates `attach`, `reconcile` and `status`; an aliasless endpoint is disconnected and reconnected once, and `status` reports the state separately rather than folding it into "attached". | **The gap would have been SILENT and would have looked like success**: ingress fine, `attach` printing *"already attached"*, the scrape unable to resolve, and the metrics surface serving this project's own OTLP series while carrying none of its edge ones — which reads exactly like a deployment nobody has sent a request to. **Question 5 again**: the decision about what an attachment is gained a case, and the function deciding whether to act did not move. | 0167, 0158 |
| **D782** | Run 5 writes a certificate-deadline rule, and the plan says the deadline is *"arithmetic on a date the deployed document already carries."* | **Traefik publishes the date itself, and Run 4's filter was throwing it away.** `traefik_tls_certs_not_after` exists at the locked digest, is **absent** in a control with no certificate loaded, and its value matches `openssl x509 -enddate` **exactly** (1789816229). So the class needs no new source at all. But it is labelled `cn`, `sans` and `serial` — **neither `router` nor `service`** — and Run 4's two-branch keep filter therefore dropped it: measured, `keep.match(";")` is `False`. | **A third branch, on `cn`, matched against this project's own domain.** The domain is `re.escape`d rather than refused, because a hostname's dots are legitimate where a Traefik name's charset forbids a metacharacter. | **Question 5, one run later, on the run's own code.** Run 4's filter was written from the labels it had, and the enumeration it enforces so carefully was an enumeration of *routers*. A certificate is not a route. **The failure would have been perfectly silent**: the rule would have evaluated an absent series and reported healthy for ever, which is exactly what ADR 0167's own docstring warns a missing router looks like. **The next run's requirement is what found it**, not review. | 0168, 0167 |
| **D783** | `absent()` is the safe way to ask whether a scrape is working, so a rule using it covers the case a plain comparison misses. | **They answer different questions, and the assumption was backwards.** Measured with a configured target **stopped**: `up` becomes **0, not absent**, so `absent(up{job=...})` did **not** fire and the plain `== 0` comparison did. `absent()` fires when the scrape config itself is gone or the store is not evaluating — a different failure entirely. | **Both, as separate rules.** `up == 0` is a configured target that cannot be reached; `absent(up)` is a target nobody is asking about. `ApgStoreScrapeMissing` is the only rule here that fires **on** absence rather than in spite of it. | **Writing only one leaves a gap in whichever direction was chosen, and the gap is silent both ways.** The rig was built to reproduce D769's failure as a control and instead corrected the plan's understanding of which form fails — the control was more informative than the subject. | 0168 |
| **D784** | One `up` rule reports whether this project's metrics are flowing. | **It reported the wrong subject, and Prometheus's default is why.** `honor_labels` defaults to **false**, so the collector's forwarded `up{job="edge", instance="apg-edge-proxy:8089"}` is restamped `job="collector"` with `exported_job`/`exported_instance` beside it. Measured: `up{job="collector"}` matched **two** series — the store's own scrape of the collector, and the collector's scrape of the proxy wearing a disguise. | **`honor_labels: true`, and three rules where there was one.** The collector is a **carrier**, not an origin. `ApgCollectorUnreachable` is a failure of the *observation*; `ApgEdgeUnreachable` is a failure of the *deployment*. Proved by inducing each separately: stopping the collector fired only the first, stopping the proxy fired only the second. | **D145's family, in a signal built to avoid it.** Two unrelated states behind one name, and the remedy for each is in a different place — an operator told "the store cannot reach the collector" would look at the store while ingress was the thing that had failed. **The default that caused it is invisible in the rendered file**, which is why the setting is now written out with the measurement beside it. | 0168 |
| **D785** | The scrape filter's regex is emitted into the collector's YAML like every other rendered value. | **A regex is not a YAML string.** The `cn` branch is `re.escape`d, so it carries `\.` and `\-`; in a **double-quoted** YAML scalar those are escape sequences, `\-` is not a valid one, and the collector refuses the entire document — *"yaml: line 39: found unknown escape character"* — and **exits before serving anything**. | **Single-quoted, which performs no escape processing at all.** Written into the renderer with the measurement, because the correct quoting is invisible in a passing test — a config that never parses and a config that parses are both "a string in a file" to anything that does not run it. | **It failed closed and immediately, which is the good half.** The bad half is where it would have failed: the rendered file is written at *render* time and read at *container start*, so the first sign would have been a metrics container that would not start on the host, during the Run 8 trip. **The rig caught it because it ran the rendered file rather than reading it** (D277). | 0168 |
| **D786** | Adding a Compose variable is an ordinary change; the contract fixtures detect their own staleness. | **They detect it by `schema_version`, and `rendered_fixtures.py` says in its own docstring that this case is the hole**: *"It does not catch a fixture at the current version whose `compose.env` is missing a key, because a Compose variable can be added without an outputs migration."* Adding `STORE_VOLUME_NAME` did exactly that. **Nine tests failed with *"required variable STORE_VOLUME_NAME is missing a value"***, which reads as a broken Compose model. | **Re-render both fixtures, which is the documented remedy.** Recorded rather than repaired: closing it needs the required-interpolation set, which is profile-dependent and deliberately incomplete for the references whose values arrive from root-owned state (ADR 0013). | **The hole fired for the first time, and it presented as the Session 5 experience the module was written about** — a fixture four schema versions old reporting eleven variables "missing a value" as though the model were broken. **A check whose name is wider than its evidence is this repository's standing defect; this one's name is exactly as wide as its evidence, and the cost is that the uncovered half looks like a product bug.** | 0073 |
| **D787** | D762's procedure is followed when an image is added, and Session 14 has already paid it once in Run 2. | **It is paid EVERY time, and Traefik has moved again since Run 2.** Adding `PROMETHEUS_IMAGE` re-resolved the same three rolling tags for the third consecutive session: `pgvector:pg18`, `python:3.12-slim` and `traefik:v3.7` — and `traefik:v3.7`'s digest is **not** the one Run 2 restored three days earlier. | **Snapshot, `--update`, classify every changed key as intended or drift, restore the drift, then RE-READ the file to prove only the intended key differs.** `--check` exits 0 with 11 images. | **`traefik:v3.7` moving twice inside one session is the measurement D540 has been waiting four sessions for**: the drift is not annual, it is roughly weekly, and a session that adds two images at different times pays it twice. **Adopting an unmeasured Traefik as a side effect of adding a metrics store is exactly the change a digest pin exists to prevent** — and Run 4 had already re-measured this deployment's Traefik behaviour against the *old* digest. | 0077 |
| **D788** | The drift guard restores every key that is not this run's, which is the whole of D762's procedure. | **A classifier over two categories met a third.** `APG_LOCKED_AT` and `APG_VERSIONS_IN_SHA256` are neither this run's key nor registry drift — they are derived from the *edit itself*, and the second is a hash **of `versions.in.yaml`**, which this run legitimately changed. Restoring them made the lock describe a file that no longer existed, and `--check` said so: *"versions.in.yaml has changed since the lock was generated … run --update"*. | **Recomputed from the source of truth rather than copied from the update's output**, so the repair reads the file rather than a number in a transcript. | **The guard was written to catch a known failure and acquired one of its own, in the same shape it was guarding against**: a rule that was complete when written and became incomplete when the world gained a case. It failed **loudly**, which is the only reason it cost a minute rather than a release — and the loud failure came from `--check`, not from the guard. | 0077 |
| **D789** | *"A rule per failure class"* — backup, WAL, disk, service health, certificate. | **Five of those classes have no series, because Run 4 deliberately did not build them.** Backup state and the archiver each already have one source and it is a root-plane on-demand command; disk headroom is `diagnosis.disk_headroom`; pooler saturation and connection counts need a database credential and therefore a **sixth claimant on `max_connections`** (D780). What is left with a series is service health (two hops), certificate expiry, route errors and agent-plane failures. | **Six rules over the metrics that exist, and a test that REFUSES a rule naming any of the absent ones.** The plan says which classes are unreported, in the run's own `**Done.**` marker rather than in a footnote. | **A rule over a series nothing publishes is silent in exactly the way a healthy deployment is.** Writing the missing five would have produced a rule set that looked complete, satisfied `OPS-ALERT-001`'s node ids, and measured four of nine classes — **the dangerous half of this claim arriving disguised as the safe half**, and the exact shape of D145. The refusal is a test rather than a review note because the temptation returns every time somebody reads the plan's list. | 0168, 0167 |
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

**Done.** — D772, ADRs **0164** and **0165**. Both decisions were taken against
measurements, and the run's first finding was not about metrics at all.

**The route.** `/metrics` under the project's own host, claimed from
`RESERVED_BASE_PATHS` rather than added to it, behind a per-project basic-auth
middleware in the documentation route's shape. Per project throughout —
collector, credential, router, middleware.

**Its backend is the collector, not the store, and that was forced rather than
preferred.** Prometheus's and VictoriaMetrics' federation endpoints both require
a `match[]` query parameter and **Traefik has no middleware that can add a query
string**, so a store-backed route could not be published at all. The collector's
exporter serves exposition parameterless: measured 200 with the project's series
against a control whose scrape target does not resolve returning 200 with
**none**, and 404 on `/`. A consequence fell out that improved the design — the
store scrapes the collector internally, so **nothing in the metrics plane holds
the edge credential.**

**What Run 2 did not do, deliberately.** The route is **not published in
`outputs.json`**. That needs outputs v14 and a migration, and an endpoint's
`available_from_session` only becomes meaningful when `CURRENT_SESSION` moves —
which is Run 7. Deferred to the bump rather than omitted, and said here so the
next reader does not conclude the document was forgotten.

**D772 was found on the way in and repaired here** (§1). Establishing which
middleware chain the new router should attach turned up that
`apg-response-policy` had been attached to **no route at all since Session 5**:
the deployed REST surface answered without `Cache-Control: no-store` on an API
whose every row is selected per caller. `BASELINE_MIDDLEWARE_CHAIN` is now the
single name `apg-baseline@file`. **The offline control reproduced the live
defect exactly**, which is the strongest form the repair could have taken.

**D762 came due and was paid in full.** `--update` re-resolved three rolling
tags — `pg18`, `3.12-slim` and `v3.7`, the same three D754 measured. Restoring
`TRAEFIK_IMAGE` mattered most: every Traefik measurement in Runs 1 and 2, and
the host's own checkout, are on `9c3b91d5`, so adopting the new digest would
have made this session's measurements describe an image nothing runs.

**Four batteries, thirteen mutations, all killed by assertion with a control the
mutation cannot reach.** The ones worth naming are the three that produce a
route which *looks* correct: `Path` becoming `PathPrefix` (D162 — a string
prefix answers `/metricsanything`), the credential losing its `@file` suffix
(**an unresolved middleware is served, not refused — the route silently stops
asking for the password**), and the service pointing at a port the exporter does
not serve (a 502 behind a healthy collector, with neither file looking wrong).

**Two rig defects, both mine, both caught by the rules that exist for them.** A
test block written through a shell heredoc had every double quote eaten and left
the module syntactically broken — reverted and rewritten with the file tools. And
a `test_connect_command` failure chased for several minutes turned out to be
`bash -c` instead of `bash -lc`, so `jq` was off the PATH. Both are documented
traps; neither reached a commit.

**Not measured here:** what the surface actually *carries*. The collector
receives and exports but scrapes nothing, so a deployed `/metrics` today is an
authenticated, empty exposition. Run 3 gives it a transport and Run 4 gives it
metrics; the surface exists first, which is the order this run was for.

### Run 3 — OpenTelemetry as a transport, not an identifier

The existing request id becomes the trace context (D763). **Nothing re-derives
it.** Propagation through Traefik, the auth API, FastMCP and the protected
downstream calls, with `mcp_telemetry`'s forbidden list applying unchanged to
whatever the new transport carries.

**The redaction canary is extended to the new surface in the same run**, not a
later one: a telemetry plane that ships spans is a second place a presigned URL
can reach, and Session 7's canary exists because one did.

**Done.** — D773, ADR **0166**.

**The trace id IS the request id, and no second value exists.** A W3C trace id
is 16 bytes and a `uuid4` is 16 bytes, so this is an identity rather than a
mapping: the span's trace id renders as the request id's hex and parses back to
the same UUID. D763's *"nothing re-derives it"* is satisfied by construction —
there is nothing to keep in step, because there are not two values.

**Nothing reads an inbound `traceparent`.** W3C propagation works by continuing
a caller's trace, which would have reversed ADR 0160 as a side effect of picking
a format. ADR 0160's reason has not changed: an id a caller chose lets one agent
stamp its actions with another agent's id. §9's stop condition — *"OTel
propagation would introduce a second request identifier"* — was the live risk
all run and it did not fire.

**D773 is the run's real finding, and it inverts the plan's own sentence.** The
plan expected the forbidden list to apply *"unchanged"*. Unchanged is not
enough: measured against `opentelemetry-sdk` 1.44.0, an exception merely
**escaping** a span attaches `exception.message`, `exception.stacktrace` and a
`status.description` carrying the message — `record_exception` and
`set_status_on_exception` both default to **on**. `mcp_telemetry` refuses
exactly this for log records; the span carrier arrives with that refusal
reversed. Both defaults are now off and attributes are enumerated.

**The canary observes a real span, and its control requires the leak to
appear.** The SDK is in the dev environment for that reason: a test asserting
`record_exception=False` appears in the source would be checking which names
appear rather than what the code produces (D277). The control drives the tracer
directly with the SDK's defaults and **fails if the canary is absent** — so it
can fail for the reason it watches, which the absence-only version could not
(D509).

**Four mutations, all killed.** M1 and M2 restore the two SDK defaults, which is
not a synthetic edit — it is the state of the world had this module never been
written.

**Two things the run found by running rather than reading:**

- **The SDK's `IdGenerator` interface has three methods, not two.**
  `TracerProvider` calls `is_trace_id_random()` on every root span, and a
  duck-typed generator without it raises `AttributeError` inside span creation.
  Every offline test that did not build a real span passed. That is *will this
  run* versus *is what it asserts true*, and only the real library closed it.
- **A span named `agent.upstream_call` tripped a security guard.**
  `test_nothing_dials_the_locks_published_upstream` refuses any `.upstream` in
  an `mcp_*.py` line (ADR 0126), and a string literal matched it — D464's text
  scan again. **The name moved rather than the scan**, deliberately: loosening a
  guard over a real boundary to admit a name this module chose freely would
  trade a control for a preference, and `outbound` is the clearer word anyway
  because `upstream` already means something else here.

**Packages cost nothing this time.** `--packages-only` carried all ten image
digests forward unchanged, so Run 3 pays none of Run 2's D762 price. Two pins,
not three: `opentelemetry-sdk` declares `opentelemetry-api` with an exact
equality, so naming the api would be a second authority — psycopg-binary's rule.
Co-resolution with the twelve locked versions was measured with a control
(`pyjwt==2.13.999` → `ResolutionImpossible`) proving the rig detects conflict.

**Not done, and named rather than implied:** `configure()` is not called at
startup and no collector endpoint is a setting, so **no span leaves the process
yet**. `McpSettings` requires every field and defaults none — adding the first
optional one needs its own justification, and a required endpoint would make a
session-13 deployment export into a host that does not resolve. The endpoint
belongs with the session-14 activation in Run 7. What ships here is the
transport, wired into the tool path at zero cost because a span is a no-op
without a tracer, and the image carries the packages.

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

**Done.** — D774–D781, ADR **0167**.

**The design question was never which metrics to collect; it was which decision
owns each value.** A metric is a new *reader*, and this repository's most common
defect is a decision whose readers did not all move. Answering that per candidate
eliminated six of the nine the plan lists, and the eliminations are the result:

- **Backup freshness, WAL archiving and disk headroom** each have exactly one
  source and it is a root-plane on-demand command. Reaching them from a running
  exporter means recomputing a finished value — **D701 exactly**, where a deploy
  called `backup_state` on a state block that already had one and published
  `failing` for every project — or new host machinery §4 does not list.
- **Pooler saturation, connection counts and transaction duration** need a
  database credential, which makes the exporter a **sixth claimant on
  `max_connections`** (D780) — a budget with a hard preflight that took ADR 0148
  a whole run to move from four to five. Not built, by decision, recorded with
  the measurement.

**What ships is two paths, and neither invents a source.** The agent plane's
counts and durations come off the same `mcp_telemetry.Timed` record that writes
the log line — built once in `__exit__` and handed to both carriers, because
`elapsed_ms`' own docstring already refuses computing one duration twice. The
edge's per-route latency and errors come from Traefik's own exporter, scraped.

**D774 is the run's sharpest finding and it is a security one.** A project key
permits hyphens, so `alpha` and `alpha-two` are two lawful keys on one shared
edge and `apg-alpha-.*` matches both: measured, the prefix filter admitted
**twenty of `alpha-two`'s series** onto `alpha`'s surface. The filter is now an
enumeration of `naming.project_router_names`, and the prefix form is kept as
that proof's control because it must still leak. **D300 in a place that looks
like string formatting** — a prefix over a derived name is a subset check.

**D778 is the one the rig caught rather than the reader.** The repair for D777 —
setting `metric_expiration` so a dead emitter's value stops reading as current —
created it in the same edit: the SDK's export interval also defaults to 60s, so
a series would have expired at exactly the cadence it was refreshed. It surfaced
only because the verification read the real exposition and found it empty; a
test asserting `configure()` returned `True` would have passed, and the flap
would have arrived in Run 5 as rules firing and clearing at random.

**Seven mutations, all killed, every paired control green**, and the six touched
files restored byte-for-byte. M2 restores the prefix filter, which is not a
synthetic edit — it is the state of the world had the measurement not been made.

**One existing test was replaced by a stricter one.**
`test_no_dashboard_entry_point_is_published` asserted which entry points *exist*
and is named for whether one is *published* — different properties, in different
files. It has passed for thirteen sessions because no entry point had ever been
added. It now checks both, and the publication half is derived from the entry
points rather than from a list of the safe ones.

**Not done, and named rather than implied:** nothing is deployed. The host still
runs Session 12's release, so **the scrape resolves nothing until Run 8** and
`apg-edge-proxy` exists on no running network. `configure()` is still not called
at startup and no collector endpoint is a setting — that is Run 7's activation,
unchanged from Run 3. Six of the nine candidate metrics are unbuilt, listed
above with the reason for each.

### Run 5 — Alert rules, and the quiet half

A rule per failure class, each with **both** proofs: it fires when the failure is
induced, and it is silent on a healthy deployment. `OPS-ALERT-001`.

**Inducing the failures is the work**, and each has a safe method already in the
repository: `bin/backup.sh` can be pointed at a broken stanza, disk pressure can
be simulated against a threshold rather than by filling a disk, and a certificate
deadline is arithmetic on a date the deployed document already carries.

**Nothing pages anybody** (§4.4).

**Done.** — D782–D789, ADR **0168**.

**The store is Prometheus, and the choice was between measured numbers** (D770):
21.2 MB anon against VictoriaMetrics' 45.6 at the same job, plus native rule
evaluation where the other needs `vmalert` as a second container. It carries an
explicit memory limit, holds no credential, has **no router label of any kind**,
and originates no connection off the host. It is on `edge` rather than
`internal`, which diverges from ADR 0164 §3's wording deliberately — following
that sentence would have meant putting the *collector* on `internal`, reversing
Run 2's decision to keep it off. The property §3 protects is that the store holds
no edge credential and is routed nowhere, and both hold.

**Six rules, and what is NOT here is the point.** Five of the plan's failure
classes have no series because Run 4 deliberately did not build them (D789), so
a rule over any of them would be **silent in exactly the way a healthy deployment
is** — a rule set that looks complete and measures four of nine classes. A test
refuses any rule naming one of those metrics, because the temptation returns
every time somebody reads the list above.

**Three measurements changed the design, and two of them corrected this plan.**

- **D783: `up == 0` and `absent(up)` answer different questions, and the
  assumption was backwards.** With a configured target *stopped*, `up` becomes
  **0, not absent** — so `absent()` did not fire and the comparison did. The rig
  was built to reproduce D769's failure as a control and instead corrected what
  the run believed about which form fails.
- **D784: one `up` rule named the wrong subject.** `honor_labels` defaults to
  false, so the collector's forwarded `up{job="edge"}` is restamped
  `job=collector` beside the store's own and one rule matched both. **The store
  failing to reach the collector is a failure of the observation; the collector
  failing to reach the proxy is a failure of the deployment.** Now three rules,
  each proved by inducing its own failure separately.
- **D782: the certificate metric exists and Run 4's filter was dropping it.**
  `traefik_tls_certs_not_after` matches `openssl`'s `notAfter` exactly and is
  absent without a certificate — but it carries neither `router` nor `service`,
  so the two-branch keep filter refused it. **Question 5 arriving one run later,
  on this session's own code**, and found by the next run's requirement rather
  than by review.

**Nine mutations, all killed — but three survived the first pass and the repair
was the TESTS.** M1 replaced the rendered `TLS_WARN_DAYS` with a literal `21` and
the test stayed green, because the constant *is* 21: a test comparing two values
equal by coincidence. It now moves the constant and requires the rule to follow.
M8 and M9 removed the `cn` branch and its escaping — the whole of Run 5's filter
change — and nothing asserted either existed. **A survivor is evidence, and all
three were real coverage gaps rather than uninformative mutations.**

**Two closed lists were widened to the measured set**, both kept as exact
equalities rather than containment checks: `prometheus.yaml` and
`alert-rules.yaml` join `otelcol.yaml` as world-readable, on its terms — the
store runs as a uid that does not own the rendered directory and neither file
holds a secret.

**Not done, and named rather than implied:** nothing is deployed, and the store
runs nowhere. **No Alertmanager and no receiver** — nothing pages anybody (§4.4),
and `ALERT_FOR_SECONDS` is the first number to re-derive when routing is decided.
**`ALERT_ERROR_RATIO` is chosen, not measured**: no deployment here has been
observed under load, which is Run 6's subject. And a certificate covering more
than one domain is not served by the `cn` equality — the safe direction, with an
absent certificate series meaning *unknown* rather than *fine*.

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
