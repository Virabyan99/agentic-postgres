# 0226 — The workflow worker is a loop in the auth process, and it holds nothing the auth service did not hold

- **Status:** Accepted
- **Date:** 2026-09-21
- **Session:** 32, Run 1 (D1645, D1648, D1653, and the rows Run 1 added:
  D1668, D1669, D1670)
- **Affects:** `services/auth-api/app/main.py`'s `lifespan` (a supervised task
  in `auth` mode only), a new `services/auth-api/app/workflow_worker.py` and
  `workflow_repository.py`, `services/auth-api/app/service.py` (the
  `agent_token` split), `tests/contract/test_auth_service_shape.py`'s
  `TRANSPORT_ALLOWLIST` (one new row). **No new container, no new database
  role, no new secret, no new compose service, no new connection summand and
  no new deployed-document field.**
- **Related:** ADR 0121 (one image, several modes), ADR 0093 (the work runs in
  the process that holds the credentials), ADR 0124 (a transport is declared
  with a reason), ADR 0125 (the plane asks the authority on every request),
  ADR 0193 (a signal to the process, never `docker kill`), ADR 0217 (nothing
  may require a hosted trust model to be safe), ADR 0221/0222 (the node as a
  finite resource), D388, D765, D1375.

## Context

Stage 4 asks for a durable step substrate and something that executes steps.
The stage plan's §5 named the first measurement as *a loop inside the `auth`
process versus a new `worker` container — memory, a connection claim, and
whether a new container needs a secret with no default*, and left the rig to
choose.

**Three facts decided it before a rig ran, and the rig then priced the
decision rather than choosing it.**

1. **The one token-minting route takes the agent's SECRET.** `POST
   /auth/agent-token` takes exactly `{agent_id, secret}`
   (`models.py:264-272`), and `AuthService.agent_token` verifies the hash
   before it consults anything (`service.py:449-496`). A worker in its own
   container may not hold an agent's secret — it is the agent's, hashed at
   rest — so a separate container would need a **new way to obtain an agent's
   token**: a secret shared with `auth`, or a route that mints for a claimed
   step. Either is a second principal holding more than the identity it acts
   for, which is the stage's failure mode in its purest form.
2. **The tree's only lease worker already runs inside the service whose role
   it uses.** `storage_cleanup.py` is driven through `bin/storage-admin.py` by
   a `docker exec` into the storage container, as the storage service's own
   role and environment, and it fits inside that service's *reserved*
   connections rather than becoming a claimant (`storage_cleanup.py:71-83`,
   D388). That is the pattern to copy, and copying it costs nothing new.
3. **A new container costs a role and a service.** A role is
   `naming.ROLE_SUFFIXES`, outputs **v19** with a `migrate_v18_to_v19`, a
   `bootstrap_statements` entry, a `*_CONSUMER` and an `activate_*` in
   `bin/postgres-bootstrap.py`, a seventh summand in the connection budget
   and in `BUDGET_CLAIMANTS`, a row in `secrets.required.yaml`, and the
   literal `13` at `tests/contract/test_naming.py:97`. A service is
   `config.SERVICE_RESOURCE_DEFAULTS`, `rendering.SERVICE_RESOURCE_ORDER` and
   `test_process_limits.py`'s `20`/`9`/`11`. All of that for a process whose
   whole job is to poll one table and make one HTTP call at a time.

## Decision

**The worker is an `asyncio` task started by `main.py`'s `lifespan` in `auth`
mode only.** It uses `application.state.pool` and `application.state.service`,
mints each step's token through the auth service's own issuance path, and
calls tools over HTTP against the `mcp` container exactly as every live proof
already does. It is supervised, so an exception in the loop never stops the
verifier, and it is cancelled at lifespan exit **before** the pool closes.

It adds no container, no role, no secret, no compose service, no connection
summand and no document field.

**The flip criteria, written before rig 32a ran** (D1645): the loop's idle RSS
delta exceeds 32 MiB, or its under-load delta exceeds 96 MiB (the container's
384 MiB cap minus the hash budget's four-concurrent figure of 259,
`config.py:576-592`), or the image is found to run more than one uvicorn
process. Any of the three stops Run 5 and reopens this decision as a row.

## What rig 32a measured

The released image, built from `compose.yaml:1190-1212`'s own build arguments,
run as `APP_MODE: auth` against a cluster with all 33 released migrations
applied. Arm 2 injects a polling task through `sitecustomize`, which CPython
imports at startup, **so the image under measurement is byte-for-byte the
released one** — no edit to `main.py`, which is Run 5's work.

| Reading | Without the loop | With the loop | Delta |
|---|---|---|---|
| `docker stats` RSS | **53.77 MiB** | **61.57 MiB** | **7.8 MiB** |
| cgroup `memory.current` | 54.7 MiB | 62.9 MiB | 8.1 MiB |
| processes in the container (`docker top`) | **1** | **1** | — |

Control: the same image in `APP_MODE: mcp` reads **94.88 MiB** RSS, which is
the mode whose overhead `profile.py:116-128` already records — so the auth
figures are not the rig misreading the machine.

**None of the three flip criteria is tripped**, and the idle criterion is
cleared with a four-fold margin. The injected task is a **conservative
over-estimate**: it runs its own thread, its own event loop and its own
connection, where the real loop shares the application's. Both differences
cost more, not less, which is the only direction in which an approximation may
be used to clear a gate.

Two things the rig found that were not about its subject, both recorded
because each would otherwise have been found later and more expensively:

* The image is `USER 65532:65532`, so a **bind-mounted 0600 secret owned by
  the host's uid is unreadable by the process**. The lifespan then dies with
  `PoolTimeout: pool initialization incomplete after 15.0 sec` — a failure
  that names the pool and never mentions the file. Both arms of the first pass
  failed on exactly that. The rig now seeds a volume the way a deploy does.
* The image carries no `ps`, so the first pass read **zero** processes and the
  third flip criterion was skipped by a falsy guard rather than answered. It
  is read with `docker top` now, and *a criterion that was not read is not
  met* is asserted separately from the criterion itself (ADR 0195).

## What the loop may hold, and what it may not

It holds the auth service's **own** database role — the role the process was
already connected as — and **one token per step attempt**, minted after the
step is claimed and dropped at finish. It caches no token across steps. It
holds no capability lock, no SQL and no credential of any other service. Rig
32f measured the minting half: a token minted without a secret and one minted
with it **differ in `jti` alone**, and the two refuse a revoked agent, an
expired secret, an unknown id and a malformed id with byte-identical messages.

**A new transport row is required and is a widening, not a weakening.**
`test_every_transport_in_the_service_is_declared_with_a_reason` refuses any
module under `services/auth-api/app/` that names a transport without a row in
`TRANSPORT_ALLOWLIST` (ADR 0124). `workflow_worker.py` makes one HTTP call to
the plane, so it gets one row naming `urllib` — the transport
`mcp_upstream.py` already uses — and nothing else (D1669). **`socket` is
NOT taken**: `storage_cleanup.worker_identity` solved this exact problem in
Session 7 by using `os.uname().nodename`, *"the same fact from a call that
cannot open a connection"*, and the holder string is derived the same way
(D1668).

## Consequences

* The auth container's 384 MiB cap now covers the loop, and it covers it with
  room: 61.6 MiB resident against 384.
* **A worker restart is an auth restart**, which makes `service-termination`
  on `auth` into the `worker-restart` rehearsal — and a stronger claim than a
  dedicated worker would have allowed: the signer dies mid-run and the run
  survives.
* The seventh claimant the stage plan anticipated turned out to be a **user of
  the sixth's pool**. `BUDGET_CLAIMANTS` is unchanged and its AST guard runs.
  Charging it twice would be D767's mistake inverted (D1653).
* `op` still cannot reach the Docker socket and does not need to: the cgroup
  figure is world-readable (D765).

## Alternatives rejected

* **A `worker` container with its own role and a step-nonce exchange route.**
  Rejected: it invents a new way to obtain an agent's token, which is the one
  thing Stage 4 §8 says a worker may not have. It also spends a role, a
  service, a secret and a connection summand.
* **A loop in the `mcp` process.** Rejected: that runtime holds no pool and no
  credential **by decision** (`main.py:203-209` returns before the lifespan
  exists), and giving it one to run a loop would undo ADR 0125's central
  property — that a confused deputy is unconstructible there because there is
  nothing to be confused with.
* **A host timer or systemd unit.** Rejected: `systemd/` holds backup units
  only, the unit would run as root on the host, and it would need an agent's
  token from outside every trust boundary the product has.

## Amendment, Session 32 Run 8 (2026-09-26): the loop on production

The loop ran on the deployment host for the first time on 2026-09-26, in
both projects' `auth` containers at 1.10.0. Beta's container was read through
its cgroup (`memory.current`, as root) on the trip's sheets:

| Reading | `memory.current` |
|---|---|
| Before: the 1.9.0 container, five days old, no loop | **53.56 MiB** (56,164,352 B) |
| With the loop: 1.10.0, three minutes after the deploy, idle | **54.91 MiB** (57,577,472 B) |
| After `worker-restart` killed the process and the policy restarted it | **56.11 MiB** (58,830,848 B) |

**The three flip criteria, against production:**

* **Idle delta > 32 MiB: not tripped.** +1.35 MiB, and +2.54 MiB after the
  restart. These are not the loop's cost alone: the two sides are different
  processes of different ages, and `memory.current` counts page cache, so
  rig 32a's +8.1 MiB, which held everything else still, stays the better
  estimate of the loop's own cost. What production establishes is the
  absolute: **56 MiB against the 384 MiB cap.**
* **Under-load delta > 96 MiB: NOT READ.** No figure was taken while a run
  executed (D1711). Every sweep recreates the services early, so the
  container being sampled vanished, and the samples that were taken are of
  a container created after the workflow proofs had finished. *A criterion
  that was not read is not met*, which is this ADR's own rule, so it stands
  as unanswered in `capacity.UNMEASURED`, not as cleared. The run proofs
  passed under the cap, which says a run fits and says nothing about how
  close it came. That is a floor, not the reading.
* **More than one uvicorn process: not tripped where read.** Read as `op`
  from `/proc/<pid>/cgroup` and `mountinfo` at three moments (15:47, 16:53
  and after the cleanup), each `auth` container held exactly one `uvicorn`
  process. Three samples, not a continuous reading.

**And what the day showed about the loop coming back.** Three
`worker-restart` kills (Sheet B4 and one in each sweep) returned a new
heartbeat holder in **8.8 s, 8.4 s and 7.5 s**, with no lease overdue. Each
landed on a container at restart count 0, because the sweeps recreate the
services (D1711), so the restart policy's five-restart budget was never
stacked.
