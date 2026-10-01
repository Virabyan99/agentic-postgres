# 0244 — The edge and every long-running project service are bounded in memory, processes and CPU, and recreating the edge is a measured act

- **Status:** Accepted
- **Date:** 2026-10-01
- **Session:** 35, Run 1 (D1586, D1710, D1877, D1878, D1900; Sheet E0)
- **Affects:** `infra/edge/compose.yaml` (Run 5: `mem_limit`, `pids_limit`,
  `cpus` on `traefik` and `docker-socket-proxy`), `compose.yaml` and
  `src/agentic_postgres/config.py` (Run 5: `SERVICE_MEMORY_LIMITS_MB` for
  `pgbouncer`, `postgrest`, `docs`, `edge-probe`), `src/agentic_postgres/
  rendering.py` (`PGBOUNCER_MEMORY_LIMIT`, `POSTGREST_MEMORY_LIMIT`,
  `DOCS_MEMORY_LIMIT`, `EDGE_PROBE_MEMORY_LIMIT`),
  `tests/contract/test_process_limits.py` (`test_the_edge_plane_is_bounded`
  REPLACES `test_the_edge_plane_is_untouched`), `docs/threat-model.md`
  (`THR-NOISY-NEIGHBOUR`); Session 35's trip, Sheet F4.
- **Related:** ADR 0129/0131 (the budgets), ADR 0221 (admission charges
  unreclaimable memory, never the caps — D767), ADR 0222 (the 4× method for
  `pids_limit` and `cpus`), ADR 0155 (a deploy recreates what changed), D770
  (a limit is a measurement first), D1586, D1710.

## Context

Two projects on one host share exactly the edge — Traefik and the socket
proxy. Neither carries `mem_limit`, `pids_limit` or `cpus`, and a contract
proof pins the absence (`test_the_edge_plane_is_untouched`) *"so that adding it
later is a decision somebody takes"* (D1586), deferred to Session 35's
hardening with the downtime measurement it owes. The threat model's
`THR-NOISY-NEIGHBOUR` says *"per-service `mem_limit` and `pids_limit` on every
service"*, which the tree makes false for memory: `doctor capacity` reads
**10 unbounded** containers on the reference host.

**Sheet E0 read the host on 2026-09-30 at 19:57Z** (as root, from each
container's own cgroup, resolved through `/proc/<pid>/cgroup`; no figure
`absent`). The edge's two had run since 2026-09-17 — thirteen days, through
every deploy and sweep of Sessions 31–34. The project services had run since
17:54–17:57Z — about two hours, across most of Session 34's third sweep, the
heaviest workload this host carries. `memory.peak` / `pids.peak`:

| Container | alpha | beta | edge |
|---|---|---|---|
| `traefik` | | | 149.05 MiB / 19 (current 123.02 MiB) |
| `docker-socket-proxy` | | | 14.27 MiB / 12 (current 6.86 MiB) |
| `pgbouncer` | 9.47 MiB / 9 | 6.92 MiB / 9 | |
| `postgrest` | 26.03 MiB / 20 | 24.52 MiB / 18 | |
| `docs` | 53.80 MiB / 9 | 47.78 MiB / 9 | |
| `edge-probe` | 51.51 MiB / 9 | 49.42 MiB / 9 | |

**The tenth unbounded container per pair is `edge-probe`** (D1900): ADR 0222
classed it among the one-shots, probes and clients (a literal `pids_limit: 64`,
no `cpus`), but it is the project's health route's server, `restart:
on-failure:5`, and it was running on both projects. The 10 is 4 per project
(`pgbouncer`, `postgrest`, `docs`, `edge-probe`) plus the edge's 2 — not
D1710's *"2 × three + the edge's two"*, which sums to 8.

## Decision

1. **The rule.** Memory = max(4 × `memory.peak` rounded UP to a multiple of
   32 MiB, 64 MiB); pids = max(4 × `pids.peak`, 64); `cpus` `"1.0"` on the
   edge's two. One value per service NAME, the larger of alpha's and beta's.
   ADR 0222's 4× method, with a floor for memory because a cap near a small
   peak trades a slow day for an OOM kill.
2. **The values:**

   | Service | `mem_limit` | `pids_limit` | `cpus` |
   |---|---|---|---|
   | `traefik` (edge) | **608m** (4 × 149.05 = 596.2 → 608) | **76** | `"1.0"` |
   | `docker-socket-proxy` (edge) | **64m** (57.1 → 64, the floor) | **64** (48 → floor) | `"1.0"` |
   | `pgbouncer` | **64m** (37.9 → floor) | unchanged (64) | unchanged |
   | `postgrest` | **128m** (104.1 → 128) | unchanged (128) | unchanged |
   | `docs` | **224m** (215.2 → 224) | unchanged (64) | unchanged |
   | `edge-probe` | **224m** (206.0 → 224) | unchanged (64) | none (unchanged) |

   Each edge limit is above twice its container's `memory.current` (246 MiB
   and 13.7 MiB against 608 and 64), the plan's stop condition for a peak whose
   window was too short.
3. **Where they live.** The edge's are LITERALS in `infra/edge/compose.yaml`
   (the edge has no render of its own variables). The four project services'
   come from `config.SERVICE_MEMORY_LIMITS_MB`, rendered into compose
   variables exactly as `AUTH_MEMORY_LIMIT` is.
4. **The proof is replaced, not loosened.** `test_the_edge_plane_is_bounded`
   asserts those exact values on both edge services and REPLACES
   `test_the_edge_plane_is_untouched` — the one replacement Session 35's plan
   authorises (CLAUDE.md §6). A second proof asserts every long-running
   service in `compose.yaml` carries a `mem_limit`.
5. **Recreating the edge is a sheet of its own** (Session 35 Sheet F4: `bin/edge.sh
   restart` with the probe running on BOTH projects). It takes every
   project's ingress down at once, so its window is measured and recorded as
   the EDGE class of the downtime readings, never assumed.

## Alternatives rejected

- **Leaving the edge unbounded.** The one container both projects share is the
  one no ceiling covered; a leak there is every project's outage.
- **A limit from prose or a round number.** D770: a measurement first.
- **Bounding the three the plan named and not `edge-probe`.** It is running, it
  is unbounded, and `doctor capacity` counts it; the threat-model sentence would
  stay false by one service per project.

## Consequences

- `doctor capacity`'s `unbounded` falls **10 → 0**, and its project ceilings
  rise by 2 × (64 + 128 + 224 + 224) = 1,280 MiB, plus whatever the reading
  attributes to the edge's 672 — both READ on the trip, never predicted into a
  record. Admission is unmoved: it charges `unreclaimable_mb`, never a cap
  (D767; Run 5 re-reads `decide` before its commit).
- `THR-NOISY-NEIGHBOUR`'s sentence becomes *"on every long-running service"*.
- A peak read over two hours of a sweep is not a peak over a month of
  production; the 4× margin is the answer to that, and the doctor's reading
  after the trip is the check.
