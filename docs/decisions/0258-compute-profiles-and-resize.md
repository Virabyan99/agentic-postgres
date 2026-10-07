# 0258 — Compute profiles, and a resize that says what it has measured

- **Status:** Accepted
- **Date:** 2026-10-08
- **Session:** 38, Run 1 (D2156, D2157; rig row D2193)
- **Affects:** `services/auth-api/app/compute_profiles.py` and
  `src/agentic_postgres/compute_profiles.py` (new, Run 3), manifest schema 10's
  `compute: {profile}` (Run 3), `config.py`'s budget readers and
  `rendering.build_compose_env` (Run 3), the reconciler's resize handler
  (Run 7), `bin/compute.sh` (Run 8). Requirements `LIFE-PROFILE-001`,
  `LIFE-RESIZE-001`.
- **Related:** ADR 0221/0222 (admission charges `unreclaimable_mb`), ADR 0070
  (the connection budget), ADR 0082 (the auth memory floor), ADR 0244 (the
  memory caps and the rule that derived them), ADR 0256.

## Context

The stage plan (D1955) makes a profile *"a named, versioned set of the values
a manifest can already carry plus pids and cpus"*, with today's defaults as
`standard` and the other numbers derived on the host. Every value a manifest
can already carry is already enforced by a validator: the memory relation
(`shm ≥ shared_buffers`, `memory_limit > unreclaimable`, `unreclaimable ≤ 1600`),
the auth floor (224 MiB, ADR 0082) and the connection budget summed over six
claimants (ADR 0070).

Sheet E0 read the host on 2026-10-07 20:28Z: 3,814 MiB, **1,725 MiB available**,
**912 of 1,600 MiB committed** across three projects (304 each), Docker Compose
v5.4.0, 20 GiB free at the Docker root. Control-prod — the idlest project, the
best predictor of a fresh one — held **620–631 MiB resident** across three
`docker stats` samples 23 s apart (auth 58, docs 137, edge-probe 116–126, mcp
104, metrics 42–46, pgbouncer 2, postgres 50, postgrest 16, storage 73, store
22). Session 37 measured the control project's arrival as 521 MiB (2,145 →
1,624 available). Every project's memory CAPS sum to 2,880 MiB.

**The plan's rule for `small` could not hold** (D2193): *"its sum of memory
caps plus the three projects' resident leaves available ≥ 1,024"* — the caps
alone exceed what is available. Caps are ceilings, never reservations (D767);
what decides whether the host stays above its floor is resident memory, and
what admission decides on is the charge. Of a fresh project's ~620 MiB
resident, ~50 MiB is the database; the rest is seven processes no profile
member moves. **A profile changes the admission charge and the ceilings; it
cannot make a project small in resident memory.**

Rig 38c′ ran each candidate through the three validators directly and through
`config.load_project_manifest` on a copy of `project.example.yaml` carrying the
values explicitly; both accepted all three, and both refused the control
(`memory_limit_mb` equal to the charge).

## Decision

1. **Three profiles**, in `services/auth-api/app/compute_profiles.py` (standard
   library, so the image can validate a request's profile name) and loaded by
   `src/agentic_postgres/compute_profiles.py` through `service_source`:

   | member | `small` | `standard` | `large` |
   |---|---|---|---|
   | `database.shared_buffers_mb` | 64 | 128 | 512 |
   | `database.maintenance_work_mem_mb` | 32 | 64 | 128 |
   | `database.max_connections` | 48 | 56 | 100 |
   | `database.work_mem_mb` | 4 | 4 | 4 |
   | `database.memory_limit_mb` | 512 | 768 | 1536 |
   | `database.shm_size_mb` | 128 | 256 | 768 |
   | `api.app.memory_limit_mb` | 384 | 384 | 512 |
   | `api.app.pool_size` | 2 | 4 | 6 |
   | `api.rest.pool_size` | 6 | 10 | 16 |
   | `storage.memory_limit_mb` | 384 | 384 | 512 |
   | `storage.pool_size` | 2 | 4 | 6 |
   | postgres `cpus` | `"1.0"` | `"2.0"` | `"2.0"` |
   | **admission charge** (`unreclaimable_mb`) | **192** | **304** | **840** |
   | connections committed (pool 20) | 44 of 48 | 52 of 56 | 62 of 100 |

   Every other `pids_limit` and `cpus` is `SERVICE_RESOURCE_DEFAULTS`' in all
   three: those were derived from measured peaks (ADR 0244), and a profile has
   no measurement to move them by. `small` lowers no memory cap below today's,
   for the same reason; `large` raises two.
2. **`standard` is today's defaults exactly**: a manifest with `compute:
   {profile: standard}` renders byte-identically to one with no `compute`.
3. **Manifest schema 10 adds `compute: {profile}`** — optional, forbidden below
   10, absent meaning `standard`; a manifest naming `compute` may not also set
   a member the profile owns (refused by name). Every budget reader takes the
   profile's values.
4. **What the numbers do on this host.** A slot created at `small` brings the
   committed charge to 1,104 of 1,600; a resize to `standard` (own key
   excluded) to 1,216 — admitted; a resize to `large` to 1,752 — **refused by
   admission**, which is how Session 38 shows capacity with one slot. Resident
   memory after the creation is predicted at ~1,094–1,204 MiB available —
   above D2042's 1,024 floor by 70–180 MiB, and read on the day by
   `s38-free.sh`; below the floor is a stop.
5. **The resize message names only a measured window** (D2157).
   `compute_profiles.RESIZE_WINDOW_SECONDS` is `None` until an envelope row
   exists; while it is, the `202` body and `bin/compute.sh set` say
   *"Resizing restarts the database and the services that use it; the restart
   has not been measured on this server yet."* Session 38's close sets it from
   the trip's resize row, and a test holds the constant equal to that row.
6. **Storage reservation is not a profile member**: no per-project disk quota
   exists, and the Ledger says so.

## Alternatives rejected

- **The plan's caps rule.** Unsatisfiable by any profile on this host, and a
  rule about ceilings would decide nothing that resident memory does.
- **A `small` with lower memory caps.** Caps below a measured peak are the
  guesses ADR 0244 replaced; they buy no admission charge.
- **Profiles in the specification's numbers.** Values that look measured.
- **A disk quota member.** Nothing enforces one (no `blkio`, no quota).

## Consequences

- One CX23 holds three projects at `standard` and one at `small`, with ~70–180
  MiB above the floor; the rescale or a move is owed before Session 41.
- The resize window ships unmeasured in 1.16.0 and measured from the next
  release.
