# 0167 — A metric reads from the decision that owns its value, and its scope is an enumeration

- **Status:** accepted
- **Date:** 2026-09-02
- **Session:** 14, Run 4 (`OPS-METRIC-001`, `CAP-ENV-001`, D774–D781)
- **Related:** **D774** (a prefix over a project key admits another project),
  **D775** (an unset metrics entry point takes the shared edge down), **D776**
  (the exposed metric name is not the source name), **D777** (a series outlives
  its emitter), **D778** (export interval and expiration were both 60s), **D779**
  (`instance` is minted per process), **D780** (three metrics would need a sixth
  claimant on `max_connections`), **D781** (the alias gap is silent), ADR 0002
  (one derivation per identity), ADR 0164 (the surface this fills), ADR 0165 (a
  telemetry component's memory limit, and why cardinality is a memory question),
  ADR 0149/0150 (backup and archiver each have one source), ADR 0070/0148 (the
  claimants on `max_connections`), D300 (never loosen an allowlist to a subset
  check), D553 (a cumulative counter cannot answer a point-in-time question),
  D701 (a status computed twice is computed wrong the second time).

## Context

ADR 0164 built a metrics surface and deliberately left it empty: *"what flows in
is Run 3's transport and Run 4's metric set; the surface exists first."* This is
that metric set.

The session plan lists nine candidates — pooler saturation, connections against
`max_connections`, transaction duration, PostgREST latency and errors, MCP calls
and denials, audit-write failures, backup and WAL freshness, disk headroom — and
attaches a warning that turns out to be the whole design: **two of them already
have a source and must not grow a second.**

That warning generalises. **A metric is a new READER of a value some other
decision owns**, and this repository's most common defect is a decision whose
readers were not all updated. So the question for each candidate is not "can it
be measured" but "which decision owns this value, and can this metric read from
that decision rather than re-derive it".

Answering it eliminated most of the list, and the eliminations are the content.

## Decision

### 1. A metric reads from the decision that owns its value, or it is not built

Each metric names the decision it reads from, and a candidate that cannot name
one is not built in this run.

| What ships | Reads from |
|---|---|
| `agent_tool_calls_total{tool,outcome}` | `mcp_telemetry.Timed` — the same record that writes the log line, built once in `__exit__` and handed to both carriers |
| `agent_tool_call_duration_milliseconds{tool}` | the same record's `elapsed_ms`, whose docstring already refuses computing it twice |
| `traefik_router_*`, `traefik_service_*` for this project's routes | Traefik's own exporter, filtered to `naming.project_router_names` |

**Backup freshness, WAL archiving and disk headroom are not built**, and not
because they are hard. Each has exactly one source and that source is a
root-plane on-demand command — `bin/backup.py info --json` (ADR 0149/0150),
`pg_stat_archiver`, `diagnosis.disk_headroom`. Reaching them from a
continuously-running exporter would mean either a second computation of a
finished value — **which is D701 exactly**, where a deploy called `backup_state`
on a state block that already had one and published `failing` for every project
— or new host machinery the session plan's §4 does not list among its
irreversible operations. The plan's own stop condition covers this, and it is
respected rather than argued around.

**Pooler saturation, live connection counts and transaction duration are not
built either**, and the reason is sharper: each needs a database credential, and
a process holding one is a **sixth claimant on `max_connections`** (D780).
`config.connection_claimants` sums every claimant and raises when they exceed the
manifest's ceiling; ADR 0148 took a whole run to move that count from four to
five. **Acquiring a claimant as a side effect of a metrics run is exactly the
unintended change that guard exists to prevent**, and it would arrive under a
commit message about observability — the same sentence D762 uses about adopting
a PostgreSQL image while adding a collector.

### 2. A project's scope on a shared surface is an ENUMERATION, never a prefix

The edge is host-scoped and the metrics surface is per project, so a per-project
collector scraping the shared proxy must keep this project's series and drop
every other project's.

**A prefix over the project key does not do that.** A key is
`^[a-z][a-z0-9-]{4,47}$` and permits hyphens, so `alpha` and `alpha-two` are two
lawful keys on one host and `apg-alpha-.*` matches both. Measured against the
locked Traefik and the locked collector with four routers across three projects:
the prefix form admitted **twenty series belonging to `alpha-two`** onto
`alpha`'s surface; the enumeration dropped all twenty and kept this project's
twenty. Both halves ran in one invocation, and the prefix form is retained as
that proof's control precisely because it must still leak.

So the filter is `naming.project_router_names(key)` — the exact names, from the
same `*_router_name` functions the identity is built from (ADR 0002). **This is
D300 reaching a place that looks like string formatting**: a prefix is a subset
check, and the rule against loosening an allowlist to one does not stop applying
because the allowlist is spelled as a regex.

A router that reaches `identity` without reaching the enumeration is a route
whose metrics never appear — **and that failure is silent**, because an absent
series looks exactly like a route nobody used.
`test_the_router_enumeration_names_every_router_the_identity_carries` derives the
expected set from `identity` so a ninth route breaks a test instead.

**Entry-point families are dropped for the same reason under a different shape.**
They name no other project, but an entrypoint is crossed by every project on the
host, so publishing one on a per-project surface publishes every other project's
traffic in aggregate. `addEntryPointsLabels` is off.

### 3. The exposed name is measured, not derived

A rule is written against the name on the surface, and that is not the name the
source writes. Measured through the locked collector: a counter gains `_total`,
dots become underscores, and **a unit abbreviation is expanded into the name** —
`agent.tool_call.duration` in `ms` is served as
`agent_tool_call_duration_milliseconds`. `mcp_metrics.EXPOSED_METRIC_NAMES` is
that mapping as a declared constant, because Run 5's rules depend on it and
changing an instrument's unit silently renames a series something reads.

### 4. A label is a series, so its value set is closed

A span attribute is read by whoever holds the trace. A label persists, is
published to every reader of the route, and — on a host with no swap (ADR 0165)
— an unbounded one is an OOM whose victim the kernel picks.

So `METRIC_LABELS` is `("outcome", "tool")`: `RECORD_FIELDS` has eight and this
carrier takes two. `agent_id` and `owner_id` are identities, `resource` names a
table, and `request_id` would mint one series per request. A value outside its
closed set becomes `other` rather than a new series — **substituted rather than
dropped**, because a call nobody counted is a worse answer than a call counted
under a name that says it was unexpected.

**Nothing but `service.name` goes in the OTel `Resource`**, and that is measured
rather than cautious: every resource attribute is served verbatim as a label of
a synthesised `target_info` series. A Resource is published, not metadata.

### 5. An absent series has three meanings, and only `up` separates them

A series can be absent because it was never emitted, because nothing has happened
yet, or because the process emitting it has stopped. **The third is the one that
matters and the exposition hides it by default**: measured, with the emitter
dead, the pipeline still served its gauge at t+40s, because `metric_expiration`
defaults to five minutes. It is set to 60s here.

That set up a defect this run nearly shipped. The SDK's export interval **also**
defaults to 60s — measured in its own source, falling back through
`OTEL_METRIC_EXPORT_INTERVAL` to `60000` — so a series would have expired at
exactly the cadence it was refreshed, flapping according to which timer won and
taking any rule over it in and out with it. The export interval is now explicit
at 15s, four per expiration window, and
`test_a_metric_series_is_refreshed_several_times_before_it_can_expire` holds the
relationship. It is one property living in two processes' configuration, and
nothing else would notice them drifting.

`up` and the `scrape_*` series survive `metric_relabel_configs` — measured, the
receiver synthesises them afterwards — so the distinction stays available to
Run 5's rules. D769 requires each rule to say what it means by an absent series;
this is the mechanism that makes an honest answer possible.

## Consequences

- **The shared edge gains an entry point, and its name must be explicit.**
  With `metrics.prometheus.entryPoint` unset, Traefik builds its internal
  `traefik` entry point on :8080 — which is `web` here — and refuses to start:
  *"listen tcp :8080: bind: address already in use"*. It fails closed, which is
  the good half. **The bad half is that the thing that fails is shared**, so one
  omission costs every project on the host its ingress at once (D775).
- **The proxy is reachable under a registered alias.** `edge-network.sh`
  resolves Traefik by Compose label because *"a container name is a formatting
  convention that changes between Compose versions"* — and a scrape target
  cannot resolve a label. So the attachment registers `apg-edge-proxy`.
  `attach` returns early on an already-attached proxy, so **the alias had to
  become part of what "attached" means** (D781); otherwise every existing
  deployment would keep an aliasless endpoint, ingress would be fine, the scrape
  would never resolve, and the surface would quietly carry no edge series at all.
  The first start after this release reconnects each project's endpoint once.
- **`instance` is a UUID minted per process** (D779), so an MCP restart forks a
  counter's series rather than continuing it, and the pre-restart twin is served
  until it expires. Run 5's rules aggregate away from `instance`; nothing here
  tries to make the label stable, because a stable one would have to be derived
  from something and there is no second authority available for it.
- **A telemetry carrier may not fail a request.** `Timed._count` catches, and
  names the exception TYPE only — the module's existing rule about where a
  caller's value would be if one ever reached an exception string.
- **The metric set is narrow, and the ledger says so.** Six of nine candidates
  are not built. Each is recorded in the plan with the measurement behind it, so
  a later reader can tell a deliberate omission from an oversight.

## Alternatives considered

**A prefix filter on the project key.** Rejected on measurement, not on taste:
it admits `alpha-two` into `alpha`. Kept as the enumeration's control.

**A `postgres_exporter` beside the cluster.** It answers three of the candidates
directly and is the obvious shape. Rejected for this run because it is a sixth
claimant on `max_connections` (D780) — a budget with a hard preflight — and that
is a decision with its own ADR, not a side effect.

**Keeping host-scoped edge series on the per-project surface** (Traefik's config
counters, its Go and process metrics, entry-point families). They name no other
project and would have made "is the edge healthy" answerable per project.
Rejected because entry-point counters aggregate other projects' traffic, and
because a per-project surface carrying identical host-wide numbers invites
exactly the reading ADR 0164 refused.

**Letting the collector scrape the cluster's services directly.** It is on `edge`
only, and putting it on `internal` would widen a boundary for values that mostly
already have owners. Deferred with the metrics that would need it.
