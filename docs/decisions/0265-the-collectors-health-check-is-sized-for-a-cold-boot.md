# 0265 — The collector's health check is sized for a cold boot

- **Status:** Accepted
- **Date:** 2026-10-10
- **Session:** 38, migration repairs before Run 11
  (`docs/plans/session-38-migration-plan.md`, D2291, D2297)
- **Affects:** `compose.yaml` (`metrics`: `mem_limit` 128m → 192m;
  `healthcheck.timeout` 5s → 30s, `start_period` 10s → 60s),
  `src/agentic_postgres/runtime_override.py` (`METRICS_MEMORY_LIMIT_MB` 192),
  `tests/contract/test_metrics_surface.py`.
- **Amends:** ADR 0165's number (the limit it requires to exist), not its rule.
- **Related:** ADR 0155 (a deploy recreates a container whose definition
  moved), ADR 0222 (bounded services).

## Context

On 2026-10-09 OVH was rebooted with three projects deployed (migration Run
M6). The firewall and the edge came back; **all three project units failed**.
Each unit's `up` ran `compose up --wait`; every service was healthy within 18 s
except `metrics`, the OTel collector, which read unhealthy at 20:27:51-52 in all
three projects; `--wait` failed, the unit exited 9 and its `ExecStopPost`
took the whole project down. Started by hand a few minutes later, serially,
each unit came up in 27-29 s.

The check is `/otelcol-contrib --version` -- the collector's own ~250 MB binary
exec'd inside the same container -- every 30 s, timeout 5 s, 3 retries, start
period 10 s. Measured on OVH:

- **Refuted**: a slow binary from a cold cache alone (`--version` 0.43 s after
  `drop_caches` on a running collector), the pids limit (peak 13-15 of 64,
  `pids.events max 0`), the kernel's OOM killer (none), the store (0 × 429).
- **Reproduced without a reboot** (the 30 containers stopped, caches dropped,
  all started at once): checks took **2.5-5.4 s and timed out at 5.3-5.4 s**,
  the collector pinned at 127-128 MiB of its 128 MiB cap with
  `memory.events max` climbing ~10,000 every 10 s.
- At steady state each collector holds **33-34 MiB anon**; the rest of the cap
  is the binary's page cache, and at 128 MiB it lives in permanent reclaim:
  **~1.2 million `memory.events max` per collector in 40 minutes**.
- **An in-place A/B** (`docker update`, reverted after): in one cold start,
  control-prod at 192 MiB read **0** pressure events, beta at 256 MiB 3,575,
  alpha at 128 MiB (the control) 17,550. **But in that run the control did not
  reproduce the timeout** -- every check on all three took 0.3-0.4 s. The cap's
  effect on the check is therefore NOT shown; its effect on reclaim is.

## Decision

**The check is sized for a cold boot, and the container for its own binary.**

- `healthcheck.timeout` **30 s** (from 5) and `start_period` **60 s** (from
  10), interval 30 s and retries 3 unchanged. Every check duration measured
  after a cold start (0.3-5.4 s) clears the timeout five times over; the start
  period covers the first two intervals of a boot. A binary that cannot print
  its version in 30 s is unhealthy by any reading.
- `mem_limit` **192 MiB** (from 128), the value that took reclaim to zero in
  the same cold start. It stays above the in-process `memory_limiter` (96 + 24
  MiB), which still binds first (ADR 0165). `METRICS_MEMORY_LIMIT_MB` -- a
  constant nothing read -- is this number, and a test holds the two equal.

Either change alone answers the measured failure only in part: the timeout
without the cap leaves the check racing reclaim on a busier boot; the cap
without the timeout was not shown to fix the check. Both are cheap: the cap is
a ceiling, never a reservation (D767), and admission charges nothing for it.

## Proof owed

This cannot be proved offline. **The next reboot after Run 11's deploy is the
proof**: every project unit BOOT-started (left `inactive` before
`multi-user.target`, D2140's reading) with no hand start. Until that reading
exists the repair is a sizing, measured in its parts and not as a whole.

## Consequences

- `doctor capacity`'s ceilings rise 64 MiB per project.
- The deploy that carries this recreates each `metrics` container (its
  definition moved, ADR 0155): a few seconds of an unauthenticated-for-nobody
  metrics route, no database or API downtime.
- The comment above the check claimed it "probes the port the route points
  at"; it never did. It now says what it proves: the image is intact and
  executable.

## Rejected

- **A different check.** The image has no shell and no HTTP client; the
  collector's `health_check` extension would need a client this image lacks.
- **No check.** `up --wait` would then not wait for the collector, and a
  collector that never starts would be found by nobody until `doctor usage`.
- **`Restart=` on the unit.** It would re-run materialization on every
  failure (the unit's own comment, D72's class) and still take the project
  down first.
