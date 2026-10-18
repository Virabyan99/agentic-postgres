# 0277 — The telemetry plane is ClickStack, bounded on the host, fed by the projects' own collectors

- **Status:** Accepted (the limits from rig 42a; Sheet E1 re-reads them on the
  upgraded host and this ADR's numbers move with it, D2598)
- **Date:** 2026-10-18
- **Session:** 42, Run 1 (`docs/plans/session-42-implementation-plan.md`,
  D2573–D2580, D2600–D2605; rig 42a)
- **Affects:** `infra/telemetry/compose.yaml` and `infra/telemetry/clickhouse/`
  (Run 4); `rendering.build_gateway_config()` (Run 4); `bin/telemetry.sh`,
  `libexec/agentic-postgres-telemetry`, `systemd/agentic-postgres-telemetry.service`
  (Run 4); `capacity_probe` and `doctor capacity` (the charge, Run 4);
  `rendering.build_otel_config()`'s logs pipeline and `compose.yaml`'s `metrics`
  service (Run 5); `services/auth-api/app/log_setup.py` (Run 5); `apg-diag
  containers`. Requirements `INS-PLANE-001`, `INS-ADMIT-001`, `INS-LOGS-001`,
  `INS-HOST-001`.
- **Amends:** **ADR 0221** — a platform component whose use follows its load is
  charged by admission at its ceilings (a project is still charged at its
  `unreclaimable_mb`, D767). **ADR 0244** — the telemetry plane is bounded by its
  rule, from rig 42a's peaks. **ADR 0249** — D1918's lines are also exported over
  OTLP, the same records, message only.
- **Related:** ADR 0043 (the SSH forward), ADR 0164/0165/0223 (the per-project
  collector and store), ADR 0195, ADR 0246, D1519 (Stage 4's refusal), D1964.

## Context

D1964 adds ClickStack on the host, bounded, unrouted, admission-charged, with
each project's collector feeding it D1918's lines. Stage 4 refused it (D1519)
because a 3.8 GB host could not price it. The open-source distribution is four
services: ClickHouse, HyperDX, MongoDB (HyperDX's own state), and a collector
that HyperDX supervises over OpAMP and that takes an ingestion key minted in
the UI (p7). The Stage 4 invariant stands: *observability may lose optional
detail under pressure; it may not destabilise the workloads it observes.*

## Measured

Rig 42a (2026-10-18, WSL `~/s42/run1/rig42/rig42a/`, Docker 29.5.2; transcripts
`up.txt`, `case3c.txt`, `case5-100.txt`, `case7-100.txt`). The release read is
`@hyperdx/app@2.41.0` (2026-10-13); images by index digest:
`hyperdx/hyperdx:2.41.0@sha256:00c6d5b7…` (the same index as
`docker.hyperdx.io/hyperdx/hyperdx:2.41.0`; runs as `node`, uid 1000, entrypoint
`sh /etc/local/entry.sh`), `clickhouse/clickhouse-server:26.8-alpine@sha256:2ad32242…`
(26.8.30.8), `mongo:5.0.32-focal@sha256:3b6c281e…`; the gateway the projects'
pinned `otel/opentelemetry-collector-contrib:0.159.0`, which carries the
`clickhouse` exporter.

- **The project is stamped by its collector.** 20 records whose resource said
  `project=other`, sent to a project-shaped collector with a `resource` upsert,
  arrived as `beta-dev`; **control**: 3 records sent straight to the gateway
  kept `other` — which is why only collectors join the ingest network.
- **HyperDX reads the contrib exporter's table.** One user registered, a
  connection (`http://clickhouse:8123`, `reader`, no password) and a log source
  on `otel.otel_logs`, and HyperDX's own ClickHouse proxy returned the rows.
  **Control**: ClickStack's own collector, OpAMP-connected to the same HyperDX,
  created `otel_logs` with column-for-column identical names and types.
- **The store bounds itself.** The table carries `TTL toDateTime(Timestamp) +
  toIntervalDay(7)` with `ttl_only_drop_parts = 1`, partitioned by day.
  `reader` and `gateway` are refused from inside ClickHouse's own container
  (admitted only from the telemetry network's subnet); `reader`'s `CREATE` is
  refused 403; a container on the ingest network cannot resolve ClickHouse.
- **Nothing is published.** No container but the rig's own forwarder has a
  port; HyperDX's `docker inspect` `Env` holds the session secret 0 times (its
  processes hold it); no traefik label.
- **A project does not depend on the plane.** At 100 lines/s with the gateway
  STOPPED for 600 s, the project's collector went 49→66 MiB of its 192, never
  restarted, and served its Prometheus scrape (200, 11–17 ms) every 30 s; the
  sending service's logging call stayed p50 157–272 µs / p99 552–784 µs against
  the control's (gateway up) 161–224 / 447–621 µs. **The cost**: of 60,000
  lines sent while the gateway was down, 5,401 arrived after it came back — the
  queue drops after its 60 s retry window.
- **The footprint at 100 lines/s for 30 minutes** (180,000 lines, 28 HyperDX
  searches, median 49 ms): `memory.peak` ClickHouse 285 MiB (pids 185, CPU up to
  33 %), HyperDX 420 MiB (54), MongoDB 107 MiB (65); the gateway 52 MiB by
  `docker stats` (8 pids; the image has no shell to read its cgroup). 11.15 MiB
  on disk compressed (66.96 MiB raw); ClickHouse's volume 98 M, MongoDB's 302 M.
  No OOM, no restart.
- **HyperDX admits one team**: a second registration answered `409
  teamAlreadyExists`. Its session cookie is `Domain=localhost`.

## Decision

1. **Four services in one platform compose project, `apg-telemetry`**:
   ClickHouse, HyperDX, MongoDB, and a **gateway that is the projects' pinned
   contrib collector** with its `clickhouse` exporter (database `otel`, table
   `otel_logs`, `ttl: 168h`). ClickStack's OpAMP-supervised collector is **not**
   used: no UI rewrites a pipeline and no ingestion key exists. Every image by
   digest in `versions.env` (`CLICKHOUSE_IMAGE`, `HYPERDX_IMAGE`, `MONGO_IMAGE`).
2. **Three networks, none published, none routed**: `apg-telemetry-ingest`
   (internal; the gateway and every project's `metrics` collector, nothing
   else), `apg-telemetry` (internal; the four services), `apg-telemetry-ui` (a
   plain bridge holding HyperDX alone — the host's route for the operator's SSH
   forward). Each network is ensured by `docker network create` and, on *already
   exists*, read again (D2563's shape).
3. **A project never depends on the plane.** Its collector joins the ingest
   network as an external network ensured by the project's runtime as well as by
   the plane; it stamps `project` from the render with a `resource` upsert over
   whatever the payload says, and exports through a bounded queue
   (`sending_queue.queue_size` 1000, `retry_on_failure.max_elapsed_time` 60 s,
   `memory_limiter` first). No project unit orders after the plane's.
4. **Only D1918's lines are collected.** The services that print them export
   the same records over OTLP to their own project's collector: the formatted
   message only, `exc_info` and `stack_info` dropped, a bounded batch processor
   that never blocks a request. No `docker logs`, no PostgreSQL log, no Traefik
   access log.
5. **Bounded by ADR 0244's rule from the rig's peaks** (max(4 × peak rounded up
   to 32 MiB, 64); pids max(4 × peak, 64); `cpus` "1.0"): ClickHouse **1,152 MiB /
   740 pids**, HyperDX **1,696 MiB / 216**, MongoDB **448 MiB / 260**, the gateway
   **224 MiB / 64**. ClickHouse's own ceiling `max_server_memory_usage` = 80 % of
   its limit; its system log tables removed and its caches set small
   (`mark_cache_size` 256 MiB, `index_mark_cache_size` 64 MiB,
   `uncompressed_cache_size` 0); MongoDB `--wiredTigerCacheSizeGB 0.25`. **Sheet
   E1 re-reads the peaks on the upgraded host** and the limits move to what it
   reads (D2576, D2598).
6. **Charged at its ceilings**: `telemetry.sh up` asks admission first (`exit
   12` when it does not fit) and then writes `charge_mb` — the sum of the four
   limits, **3,520 MiB** at the rig's numbers — into
   `/etc/agentic-postgres/telemetry/state.json`, which `capacity_probe` adds to
   `committed`. A store whose use follows its load has no unreclaimable figure
   to declare; its ceiling is what keeps it from being admitted twice.
7. **No password, one secret.** ClickHouse's `gateway` (**`CREATE DATABASE`,
   `CREATE TABLE` and `INSERT` on `otel.*`, no `SELECT`** -- Run 4 measured that
   the exporter's `create_schema` issues `CREATE DATABASE` even when the
   database exists, and that without the grant the whole gateway exits at
   start; so the gateway restarts on failure and waits for ClickHouse to be
   healthy, D2603) and `reader` (`SELECT` on
   `otel`, `readonly = 2`) are admitted only from the telemetry network's subnet
   — the store is reachable by two containers, and a password would be a secret
   with nothing to keep out. MongoDB listens only on the internal network.
   **HyperDX's session secret** is generated once into
   `/etc/agentic-postgres/telemetry/hyperdx-session`, **`0440 root:1000`**
   (HyperDX runs as uid 1000, D2600), mounted read-only and exported by a
   two-line entrypoint wrapper — never in the compose file nor `docker
   inspect`'s `Env`. `USAGE_STATS_ENABLED` is `"false"` and `OTEL_SDK_DISABLED`
   `"true"` (D2601: the default phones home, and the UI bridge has egress).
8. **HyperDX keeps its own login, behind the SSH forward** (the operator,
   2026-10-17, D2579). It admits one team: the operator registers immediately
   after the plane first starts (Sheet T2), at `http://localhost:18080` — its
   cookie is `Domain=localhost` (D2602). Until then anyone who could open the
   forward could register first; opening it needs an account on the host.
9. **One more plane, made the way the edge was**: `bin/telemetry.sh` (`up`,
   `down`, `status`; root), `systemd/agentic-postgres-telemetry.service` through
   `libexec/agentic-postgres-telemetry`, installed by `provision-host.sh` and
   enabled by the operator; `apg-diag containers` lists it.

## Consequences

- **The plane is a second store.** Prometheus per project answers what
  `doctor` reads; ClickHouse holds D1918's lines for the operator; the control
  database holds every customer-visible history (ADR 0278). A fourth place for
  a number is a decision of its own.
- **A gateway outage loses lines, never service**: beyond 60 s a project's
  collector drops what it could not send. The lines are optional detail.
- **HyperDX's MongoDB and ClickHouse's volumes are not backed up**: losing them
  loses the operator's saved searches and up to 7 days of lines, never a
  customer's data.
- **`apg-agent` can open the same forward as `op`** (the sshd file is global);
  it meets HyperDX's login.
- **At these limits the plane charges 3.5 GB**: it fits the 12 GB host D2511
  planned for; on the 7,746 MiB host it competes with a slot (D2598).
