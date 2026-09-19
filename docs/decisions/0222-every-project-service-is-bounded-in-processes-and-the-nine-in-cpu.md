# 0222 — Every project service is bounded in processes, and the long-running nine in CPU

- **Status:** Accepted
- **Date:** 2026-09-19
- **Session:** 31, Run 1 (D1586, D1600, D1602, D1603)
- **Affects:** `compose.yaml`'s twenty services, `config.SERVICE_RESOURCE_
  DEFAULTS` and `config.SHORT_LIVED_PIDS_LIMIT`, `rendering.build_compose_env`
  and `COMPOSE_ENV_KEYS`, `apg dev`'s cluster definition. **The edge plane
  (`infra/edge/compose.yaml`) is untouched.** No migration, no schema move.
- **Related:** ADR 0070 (the connection budget), ADR 0133 (one renderer), ADR
  0165 (`anon` is the figure a limit is chosen against), ADR 0169, D52, D765,
  D767, D960.

## Context

`pids_limit`, `cpus`, `cpu_quota`, `ulimits` and `nproc` have **zero hits**
across `src/`, `bin/`, `services/`, `compose.yaml`, `infra/edge/compose.yaml`,
`deploy.sh` and `tests/`. A fork storm in any one container on this 2 vCPU,
no-swap node is unbounded by anything the product does.

**It is not, however, unbounded by the machine.** Rig 31b read
`/sys/fs/cgroup/system.slice/docker-*.scope/pids.max` for all 22 scopes as
`op` with no root: every one reads **3647**, which is systemd's
`DefaultTasksMax` on this host (`docker.service` and `containerd.service` are
both `TasksMax=infinity`; `kernel.pid_max` is 4194304). So this session
**narrows an existing ceiling that nobody chose for these services**, rather
than creating the first one (D1602). That is a weaker starting point than "no
limit", and a much weaker one than a limit anybody measured.

Rig 31b also read `pids.peak`, which exists on this kernel. The measured peaks
across both deployed projects:

| Service | `pids.peak` (alpha, beta) |
|---|---|
| postgres | 28, 29 |
| postgrest | 18, 18 |
| metrics (otelcol) | 16, 16 |
| store (prometheus) | 16, 16 |
| auth / storage / mcp (uvicorn) | 9–12 |
| docs, pgbouncer, edge-probe | 9 |
| traefik, haproxy (**edge**) | 17, 11 |

Rig 31a measured the two Compose keys on this workstation against
`${POSTGRES_IMAGE}`, subject and control in one invocation:

- `pids_limit: 8` → `docker inspect` reads `PidsLimit=8`, `/sys/fs/cgroup/
  pids.max` inside reads `8`, and the shell fails to fork with **exactly**
  `fork: retry: Resource temporarily unavailable` (four times) then
  `fork: Resource temporarily unavailable`.
- The control, with **no** key, reaches all 20 background sleeps
  (`pids.current` 23) and `pids.max` reads `max`. `docker inspect` prints
  **`<nil>`, not `0`** (D1603).
- `cpus: "1.0"` **as a quoted string is accepted** — the interpolated form
  `${X_CPUS:?required}` yields a string, and this is what makes the render
  possible without a fallback. `docker compose config` normalises it to
  `cpus: 1`; `HostConfig.NanoCpus` is `1000000000`; `cpu.max` inside reads
  `100000 100000`. Over a 5 s two-thread burn the capped container used
  **5.06 s** of CPU and the uncapped control **9.95 s**.

`compose.yaml` has twenty services and **no per-service render loop**: four
`mem_limit`s are `${…:?required}` interpolations and two are literals. Eleven
services are one-shots, probes or clients.

## Decision

**Every service in `compose.yaml` carries a `pids_limit`. The nine
long-running services take theirs, and a `cpus`, from the compose
environment; the eleven short-lived ones carry a literal. The edge plane is
untouched.**

1. **The nine** — postgres, pgbouncer, postgrest, docs, metrics, store, auth,
   storage, mcp — carry `pids_limit: ${<SERVICE>_PIDS_LIMIT:?required}` and
   `cpus: ${<SERVICE>_CPUS:?required}`, sourced from
   `config.SERVICE_RESOURCE_DEFAULTS` through `COMPOSE_ENV_KEYS` and
   `rendering.build_compose_env`, exactly as the memory limits already are.

2. **The eleven** — `contract-probe`, `edge-probe`, `unlabeled-probe`,
   `secret-check`, `backup-mirror`, `dbmate`, `dbmate-project`, `client-psql`,
   `client-node-pg`, `client-psycopg`, `client-prisma` — carry the literal
   `pids_limit: 64` (`config.SHORT_LIVED_PIDS_LIMIT`) and **no `cpus`**. A
   one-shot's CPU cap would throttle a migration nobody has measured.

3. **The rule for each number:** *the larger of 64 and four times the measured
   peak, rounded up to a power of two*, and postgres additionally at least
   `max_connections + 32`. Applied to rig 31b's peaks:

   | Service | peak | 4 × peak | `pids_limit` |
   |---|---|---|---|
   | postgres | 29 | 116 | **128** (≥ 56 + 32 = 88) |
   | postgrest | 18 | 72 | **128** |
   | metrics | 16 | 64 | **64** |
   | store | 16 | 64 | **64** |
   | auth, storage, mcp | ≤ 12 | ≤ 48 | **64** |
   | docs, pgbouncer | 9 | 36 | **64** |

4. **`cpus` is `"2.0"` for postgres and `"1.0"` for every other long-running
   service.** postgres gets the host's core count so that a bigger host does
   not silently give it more; no sidecar may take both cores.

5. **A contract test walks every service in `compose.yaml` and asserts the
   split by name**, so a twenty-first service cannot be added without landing
   on one side or the other. Twenty hand edits are the tree's existing shape;
   a render loop would be a second renderer, which is ADR 0133's argument run
   in the other direction.

## Consequences

- Every container of both projects is recreated on the trip, including the
  database, because the compose keys moved (ADR 0155). The sheet says so and
  reads the migration ledger afterwards.
- The effective ceiling for postgres falls from 3647 to 128 and for every
  sidecar to 64. Nothing measured comes within a factor of four of those.
- A fork storm is now bounded to the service that has it, and the failure text
  an operator will see is the one rig 31a recorded verbatim.
- The edge plane keeps systemd's 3647. Recreating Traefik is its own act with
  its own blast radius (every project's ingress at once), and it is not this
  session's (§10).
- `apg dev`'s cluster definition carries the same `pids_limit` as the release
  wherever it carries a `mem_limit`, so the developer surface and the
  deployment do not disagree about what a cluster is.

## Alternatives considered

- **`deploy.resources.limits.cpus`.** The documented Compose v2 spelling, and
  the fallback rig 31a was written to fall back to. Unnecessary: the quoted
  string form is accepted, and the short key is what the file's existing
  `mem_limit`s look like. Rejected.
- **A per-service render loop over the twenty.** A second renderer beside
  `build_compose_env`, for a file whose twenty entries are already written out
  by hand. Rejected.
- **Limits chosen from a round number.** A limit typed from a guess is the
  defect class §7 of the handoff names. Every number here is four times
  something that was read off the running node. Rejected.
- **`cpus` on the one-shots too.** A capped `dbmate` throttles a migration,
  and no migration's CPU profile has been measured. Rejected.
- **Leave it at systemd's 3647.** It is a number nobody chose for these
  services, on a host where the OOM killer is the only backstop and can take
  Traefik. Rejected.
