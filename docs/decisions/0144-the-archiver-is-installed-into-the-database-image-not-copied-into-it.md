# 0144 — The archiver is installed into the database image, not copied into it

Status: accepted
Date: 2026-08-23
Session: 10, Run 1
Affects: REC-PITR-001, REC-WAL-001, D513, D514, D515, D531, D532, D533,
`services/postgres/Dockerfile`, `compose.yaml`, `versions.in.yaml`,
`versions.env`

## Context

`archive_command` runs **inside the Postgres container**, invoked by the
postmaster, and must return non-zero synchronously for the postmaster to treat
a segment as unarchived. A sidecar that shares the data volume can take a
backup; it cannot serve an `archive_command`. So continuous WAL archiving
requires the pgBackRest binary to be present beside the cluster, and the
digest-pinned `pgvector/pgvector:pg18` does not carry one.

`PGBACKREST_IMAGE` has been pinned in `versions.env` since Session 1 and is
referenced by no service, script or test. The obvious move — lift the binary
out of that image — was measured and does not work, and the reason is not the
one Session 10's plan predicted.

**Measured (rig1, 2026-08-23, against the pinned digests):**

- The pinned `woblerr/pgbackrest:2.55.1` image is **Ubuntu 24.04**, glibc, not
  musl. The plan's predicted musl-versus-glibc trap does not exist.
- A multi-stage `COPY` of `/usr/bin/pgbackrest` into the Debian 12 base
  **builds and does not run**: `error while loading shared libraries:
  libssh2.so.1: cannot open shared object file`. Every other soname resolved,
  `libc.so.6` included. The base simply does not ship libssh2.
- Installing `pgbackrest` from the PGDG repository the Postgres image already
  configures adds **exactly two packages** — `pgbackrest` and `libssh2-1` —
  and **800,863 bytes** to a 158,801,932-byte base. The missing library from
  the `COPY` attempt is precisely one of the two.
- PGDG bookworm offers **2.59.1, 2.59.0 and 2.58.0**. It **does not carry
  2.55.1**, the version `PGBACKREST_IMAGE` pins. Debian's own repository has
  2.45, three years old.
- A `0400` config owned by root, read by uid 999, fails **loudly**:
  `P00 ERROR: [041]: unable to open file … for read: [13] Permission denied`,
  exit 41. Owned `999:999` at the same mode it is read, exit 0. pgBackRest
  does not silently fall back to defaults.

Each arm ran with a control in the same invocation. The install arm's control
is the same Dockerfile with `pgbackrest=0.0.0-doesnotexist`, which fails with
`E: Version '0.0.0-doesnotexist' for 'pgbackrest' was not found` — so a green
install is not a build step that cannot fail.

## Decision

**A project Postgres image is derived from the pinned upstream one, and
pgBackRest is installed into it from PGDG at an exact version pin.**

- `services/postgres/Dockerfile` takes `BASE_IMAGE` and
  `PGBACKREST_APT_VERSION` as build arguments with **no defaults**, the shape
  `services/auth-api/Dockerfile` already uses, so `versions.env` stays the
  single authority for what this is built from.
- `archive_command` is `pgbackrest --stanza=<stanza> archive-push %p`, running
  as the postmaster's own uid.
- `pg1-path` is **`/var/lib/postgresql/18/docker`** — PGDATA, read off the
  running image — and never `/var/lib/postgresql`, which is the mount target
  and the value a careless reader assumes.
- Every file the archiver reads inside that container is owned **`999:999`**,
  mode `0400`.
- **`PGBACKREST_IMAGE` is retired from `versions.in.yaml` and `versions.env`.**

## Consequences

**This repository now builds its own database image.** That is new: the auth
service, the documentation service, the client fixtures and the probes are
built here, and the cluster was the one component taken whole from upstream.
The base stays digest-pinned and the derived layer adds two packages, so what
changed is the build, not the cluster.

**The apt pin is not a digest, and it will expire.** PGDG is a rolling
repository that removes superseded versions, so `pgbackrest=2.59.1-1.pgdg12+1`
will one day stop resolving. The build then **fails closed** — measured: an
unresolvable pin exits 100 and the image is not produced — which is the
acceptable half of D99's shape. It is not a floating tag: nothing silently
moves. Refreshing it is a deliberate edit to `versions.in.yaml`, and
`bin/lock-versions.sh` is where a future session should teach the lock about
it.

**Retiring `PGBACKREST_IMAGE` removes a second authority that was already
wrong.** Keeping it beside an apt pin would put two pgBackRest versions in one
lock — 2.55.1 that nothing installs and 2.59.1 that everything runs — and the
inert one is the one a reader would quote.

**A config the archiver cannot read stops it rather than degrading it.** The
failure this project fears — a value that looked configured and was not — is
absent here, and `test_secret_contract.py`'s
`test_consumer_ownership_matches_the_service_runtime_user` is what keeps the
`999:999` half true.

What this forecloses: running the archiver as a different user from the
postmaster, and reaching the repository from anywhere but the database
container. Both are properties Session 10's restore path depends on.

## Alternatives considered

**A multi-stage `COPY` from the pinned pgBackRest image.** Measured and
rejected: it produces an image whose binary cannot load. Making it work means
apt-installing `libssh2-1` — at which point apt is already in use, and
installing the package is one line instead of two plus a soname audit that
would have to be redone on every base bump.

**A pgBackRest sidecar sharing the data volume, with no `archive_command`.**
Rejected: it makes RPO the backup interval, leaves no point *between* two
backups to recover to, and gives `REC-WAL-001` nothing to measure. It does not
deliver the session.

**A pgBackRest TLS server sidecar, with the client in the Postgres container.**
Rejected for Session 10, not on principle: it still requires the binary in the
Postgres container, so it does not avoid this decision — it adds a mutual-TLS
cert pair and a topology nothing here has measured, on top of it. Recorded
because it is the right shape if the repository credential ever has to leave
the database container.

**Debian's own `pgbackrest` 2.45.** Rejected: three years behind, and the
repository format and the `--target-action` behaviour the restore path depends
on have both moved since.
