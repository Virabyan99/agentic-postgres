# 0223 — The collector is consumed: the runtime exports its two instruments, the store stays unrouted, and every series names its project

- **Status:** Accepted
- **Date:** 2026-09-19
- **Session:** 31, Run 1 (D1582, D1588, D1589, D1590, D1604, D1605, D1607,
  D1609)
- **Affects:** `rendering.build_otel_config` (gains a `project_key`
  parameter), `runtime_override.STORE_RETENTION_DAYS`, `settings.MCP_
  VARIABLES` (gains `APG_OTLP_ENDPOINT`), `compose.yaml`'s mcp environment,
  `mcp_runtime.create_mcp_app`, `bin/doctor.py`'s new `usage` reading,
  `tests/contract/test_mcp_tracing.py:283-322` (replaced by a stricter test).
  **`build_prometheus_config()` stays parameterless.** No migration, no schema
  move.
- **Related:** ADR 0164 (the telemetry plane per project), ADR 0168 (the store
  is routed nowhere), ADR 0195, ADR 0218 (`container_exec`), ADR 0002 (a
  container name is derived), D1114, D1413, D1444, D1519.

## Context

Since Session 14 every project runs an OTel collector (`metrics`) and a
Prometheus (`store`), and **nothing has ever consumed either**.
`mcp_metrics.configure` and `mcp_tracing.configure` have no production caller;
`MCP_VARIABLES` carries no collector endpoint; no span leaves a process. The
store's 14-day retention is a bare literal at `compose.yaml:1022` with no
constant and no test (`14d|retention.time`: zero hits under `tests/ src/
bin/`). Session 31's brief is to **bound what exists and read it**, and to add
nothing else.

Four things were measured in Run 1 before any of this was decided.

**The store is on `edge` only**, not `internal` — a divergence from ADR 0164
§3 recorded in `compose.yaml:1070-1081`. The Session 14 proof already reaches
it the only way anything can: `docker exec <store> wget -q -Y off -O -
http://127.0.0.1:9090/api/v1/query?…`, because the image has `wget` and no
shell.

**`const_labels` on the collector's `prometheus` exporter reaches every
exported series — except `target_info`.** Rig 31c ran otelcol-contrib 0.159.0
three ways. With `const_labels: {project: rig31c}` and an OTLP-pushed sum, the
series carried `project="rig31c"` and the control without the option carried
nothing. With a `prometheus` receiver scraping a **separate** target — the
production shape — `up`, `scrape_duration_seconds`,
`scrape_samples_scraped`, `scrape_samples_post_metric_relabeling` and
`scrape_series_added` all carried it, and **`target_info` did not**: six of
seven series. `target_info` is synthesised by the exporter from the resource
and const_labels are not applied to it (D1604). The stage plan's expectation
that *every* series including `target_info` would carry the label is wrong,
and a proof written to that expectation would have failed on first execution.

**A scraped series that already carries a `project` label is dropped.** The
second arm scraped its own exposition surface and the collector logged
`failed to convert metric up: duplicate label names in constant and variable
labels for metric "up"`. The series simply vanishes from the exposition; only
the collector's log says why (D1605). Traefik's metrics carry no `project`
label today, so the decision is safe — but the hazard is silent, and it is the
reason the offline proof covers it rather than the trip discovering it.

**A dead collector costs the mcp process 18 seconds to exit.** Rig 31d ran
`mcp_metrics.configure` from the auth-api image against a real collector:
`configure` returned `True`, `record` raised nothing, and
`agent_tool_calls_total{outcome="ok",project=…,tool="list_resources"} 1`
arrived on 8889. The two controls behaved: `endpoint=None` returned `False`
with a **0 KiB** RSS delta and nothing exported, and with the collector
stopped the process still exited **0** with nothing raised into the caller.
But its wall clock went from **1 s** (collector reachable) to **18 s** (name
does not resolve) and **11 s** (connect succeeds, read times out at the
exporter's 10 s default) — against mcp's `stop_grace_period: 15s`. **A stop
while the collector is down is therefore a SIGKILL** (D1607). The provider and
reader cost **25.2 MiB** RSS against `MCP_MEMORY_LIMIT` 384.

Finally, the exporter promotes `service.name` to `job` and the SDK's
auto-generated `service.instance.id` to `instance` **on every series**, not
only on `target_info` as `configure`'s docstring records. `instance` is a
fresh UUID per process, so each mcp restart mints a new series set, bounded
only by `metric_expiration: 60s` (D1609).

## Decision

**Metrics only, bounded, labelled by project, and read through the container.**

1. **`const_labels: {project: <key>}` on the collector's `prometheus`
   exporter.** Every series on the exposition surface — OTLP-pushed and
   edge-scraped alike — carries `project="<key>"`; the store scrapes it and
   the metrics route serves it. `build_otel_config` gains a `project_key`
   parameter. `build_prometheus_config()` stays parameterless, as its own
   docstring insists. **`target_info` is the documented exception**, asserted
   as an exception by name rather than folded away, and the duplicate-label
   drop is covered by a proof.

2. **`mcp_runtime.create_mcp_app` calls `mcp_metrics.configure` once**, after
   `load_lock`, with the lock's tool names and the telemetry outcome
   vocabulary. `APG_OTLP_ENDPOINT` joins `MCP_VARIABLES` and is set in
   compose's mcp environment to `http://metrics:4318/v1/metrics`, **derived in
   a test from `METRICS_SERVICE` and `OTEL_OTLP_HTTP_PORT`** rather than
   typed. The endpoint is a URL, not a credential — which is what lets it be
   an ordinary setting at all.

3. **The OTLP exporter is given an explicit timeout**, and mcp's
   `stop_grace_period` is set above the resulting worst case, so that a
   collector outage cannot turn every mcp stop into a SIGKILL. The number and
   the proof are Run 4's; the requirement is here because rig 31d found it.

4. **`mcp_tracing.configure` stays uncalled**, and the paragraph in
   `mcp_tracing.py:177-202` stays true. Tracing has no reader, and a span
   carries request-shaped values a metric does not. The scan test at
   `test_mcp_tracing.py:283-322` moves from *no module calls `configure(`* to
   ***exactly* `mcp_runtime` calls `mcp_metrics.configure`, and nothing calls
   `mcp_tracing.configure`** — a stricter test replacing a weaker one, which
   is what CLAUDE.md §6 permits under an ADR.

5. **`runtime_override.STORE_RETENTION_DAYS = 14`**, beside the literal, with
   a test that the compose command carries
   `--storage.tsdb.retention.time={STORE_RETENTION_DAYS}d` **and no second
   retention flag**. This is the house pattern the store's own `mem_limit`
   already follows.

6. **`doctor usage` reads the store the way the Session 14 proof does** —
   `container_exec.run(container, "wget", …)` against `127.0.0.1:9090` inside
   `apg-<key>-store-1`. **No network is added to the store and nothing is
   routed** (ADR 0168). The reading asserts that every series it gets back
   names the project it asked for, which is question 3 of the handoff's §7:
   are we reading the right store. It aggregates across `instance`, because
   `instance` is a per-process UUID.

## Consequences

- `agent_tool_calls_total` and `agent_tool_call_duration_milliseconds` exist
  in production for the first time, and the metrics route serves them.
- Every series the store holds is attributable to one project, which is what
  makes a two-project node's telemetry legible at all.
- A collector outage costs the mcp container a slow stop until Run 4 sets the
  timeout; it costs a tool call nothing, because the SDK's reader runs on its
  own thread and `record` raised nothing in the rig's second control.
- The store remains reachable from nowhere but its own container, and joins no
  new network.
- The telemetry plane's cardinality is bounded by four things and no more: two
  instruments, two labels (`METRIC_LABELS`, with `LABEL_OTHER` substituted for
  anything undeclared), one `project` const label, and `metric_expiration:
  60s` retiring the per-restart `instance`.

## Alternatives considered

- **Tracing as well.** No reader, and `mcp_tracing.py` carries a standing
  decision saying so with its reasons. Rejected; the paragraph stays true.
- **`external_labels` in `build_prometheus_config`.** Prometheus attaches
  `external_labels` on federation, remote write and alerts — **not** to locally
  queried series, which is the only thing `doctor usage` reads. It would have
  been a declared field with no reader (D816). Rejected.
- **A route for the store so the doctor can scrape it over HTTP.** Routing the
  store is exactly what ADR 0168 forbids, and the exec path already works and
  is already proved. Rejected (D1582).
- **Asserting the label on every series without exception.** False as
  measured; `target_info` never carries it. Folding that into "every series"
  would be the reassuring-direction premise the handoff's §7 warns about.
  Rejected in favour of a named exception.
- **A constant-free retention literal.** Status quo; a declared value with no
  reader is unverified (D600). Rejected.
