# The database

One PostgreSQL cluster per project, started by that project's Compose stack and
reachable from nothing outside it. This document is about the cluster itself:
where its data lives, what it is allowed to cost, and how to look at it.

For who may read what, see [database security](database-security.md). For how
schema changes reach it, see [migrations](migrations.md).

## What runs

`pgvector/pgvector:pg18`, digest-pinned in `versions.env` and resolved by
`bin/lock-versions.sh`. Nothing here selects a version; the lock does, and the
feature floors beside it are recorded from observation rather than from
documentation — a floor written from a vendor's documentation once guaranteed a
Traefik key that exists in no released version.

The service is `postgres`, in the `session3` Compose profile. It:

- **publishes no host port.** There is no `ports:` key and there will not be
  one. The boundary is the absence of a published port and the project-internal
  network, not a bind address — the server listens on every interface *inside*
  a network with no route off the host, because binding to localhost would also
  make it unreachable from its own project's services.
- **joins only the project's internal network.** Not the edge network, and it
  carries no Traefik label of any kind.
- runs as **999:999**, drops every capability, and sets `no-new-privileges`.

`DBX-PG-002` is the requirement; four contract tests assert the shape offline,
and the external port scan that has covered 5432 since Session 2 finally means
something now that something could be listening.

## Where the data lives

**The volume mounts at `/var/lib/postgresql`** — the path the image declares as
its `VOLUME` — and not at `PGDATA`, which is `/var/lib/postgresql/18/docker`.

This is measured, and the two wrong answers are worth knowing because one of
them works:

| Mount target | What happens |
|---|---|
| `/var/lib/postgresql/data` | The image **refuses to start**, exit 1, naming the unused mount. |
| `PGDATA` itself | Starts, and persists. Docker also creates a **stray anonymous volume** for the parent and splits the layout. |
| `/var/lib/postgresql` | One mount, no anonymous volume. Correct. |

The dangerous configuration is the one that works. A test that only checked
persistence would pass on the `PGDATA` mount and would not notice the anonymous
volume until a `--renew-anon-volumes` or a `pg_upgrade` made it matter, so the
contract test asserts the target **and** that the service has exactly one volume
mount (D53).

## The identity a volume carries

`app_private.project_identity` holds one row: the project key, the database
name, the Compose project name, an instance UUID, and when it was bound.

The bootstrap plane compares that row against the rendered document before it
does anything else. A mismatch is **exit 11 — the data is not yours**
([ADR 0030](decisions/0030-a-project-volume-carries-an-identity-and-a-mismatch-is-never-adopted.md),
[ADR 0031](decisions/0031-exit-code-11-the-data-is-not-yours.md)). There is no
flag to adopt a volume: an operator who genuinely wants to reuse one removes it
deliberately, which is a different sentence to type.

The UUID is generated once, on the first bootstrap of an empty volume, and
**recovered** on every bootstrap afterwards. `bin/db.sh identity` prints it, and
that it does not change across a restart, a redeploy or a reboot is what
`DEP-BOOT-001` measures — against `pg_postmaster_start_time()`, not against a
value the suite recorded a moment earlier. A snapshot comparison shows the
numbers did not change; it does not show the rows outlived the postmaster.

## What it is allowed to cost

The host is 3814 MiB with **no swap** and 2 vCPU, already running Traefik, a
socket proxy and the project services. Two clusters were measured under load —
49 backends each, driven with pgbench:

```
per cluster, idle        anon   5 MiB   shmem  12 MiB   file(cache)  59 MiB
per cluster, 49 backends anon  62 MiB   shmem 140 MiB   file(cache) 410 MiB
```

With no swap, `file` is reclaimable and `anon + shmem` is not, so the
unreclaimable footprint is **~218 MiB per cluster**. `max_connections × work_mem`
never materialises, because `work_mem` is a per-sort-node ceiling allocated on
demand rather than a per-backend reservation.

**The guardrail and the container limit are two different numbers, and this is
the part that is easy to get wrong.** A container memory limit caps page cache
too, so sizing `mem_limit` from a formula that counts only anonymous memory
produces a limit the cluster reaches immediately and then lives against. At
`mem_limit: 512m` both measured clusters pegged their limit exactly, with 361 and
366 reclaim events and no OOM kill: functional, and permanently thrashing its own
cache. No test would have gone red for that.

So:

- the **guardrail** is computed over unreclaimable memory — `shared_buffers` plus
  `maintenance_work_mem` plus a flat per-backend anonymous allowance — and
  rendering **fails** when the sum across a manifest's projects exceeds it;
- **`mem_limit`** is set above the guardrail, with deliberate cache headroom;
- **`shm_size`** must exceed `shared_buffers`: PostgreSQL's dynamic shared memory
  lands in `/dev/shm`, and Docker's 64 MiB default is below the 128 MiB default
  `shared_buffers`.

Schema-enforced defaults are `shared_buffers_mb: 128`, `max_connections: 50`,
`work_mem_mb: 4`, `maintenance_work_mem_mb: 64`. Fifty connections is not a
compromise: Session 4's answer to connection count is a pooler, and a large
per-cluster limit would make the pooler decorative.

## Looking at it

```bash
sudo bin/db.sh --project project.alpha.yaml --runtime status     # server and extensions
sudo bin/db.sh --project project.alpha.yaml --runtime identity   # the sentinel row
```

`bin/db.sh sql` executes only generated, hash-verified files from an allowlist.
It is not a general-purpose SQL endpoint, and the bootstrap plane it runs on is
reachable by no runtime service — it goes over the Unix socket, inside the
container, as the OS user `postgres`.

The deployed document records what was **observed**, never what was configured:

```json
"observed": {
  "status": "observed",
  "server_version": "18.4",
  "extensions": {"plpgsql": "1.0", "vector": "0.8.6"},
  "memory": {"anon_mb": 5, "shmem_mb": 17, "file_mb": 64}
}
```

The three memory figures are kept separate on purpose. A single `memory_mb`
would average a reclaimable number together with an unreclaimable one and report
something true of neither. `not_observed` with four nulls is the honest state for
a deployment nobody has read yet.

Extensions come from `pg_extension`, not `pg_available_extensions`: what is
available is not what is installed, and that distinction is the whole content of
`DBX-PG-001`.

## What this is not, yet

`database.direct` and `database.pooled` are both `unavailable` with
`available_from_session: 4`, and stay that way for the whole of Session 3. The
cluster's internal Compose address is not a client endpoint and is not written
into either document as one. `DBX-005` — "the direct endpoint is not publicly
reachable" — is Session 4's requirement, and Session 4 is where a client-facing
endpoint gets designed.
