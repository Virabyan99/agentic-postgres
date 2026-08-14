# 0083 — The lock names what it can dereference, and what is actually a choice

Status: accepted
Date: 2026-08-14
Session: 6, Run 7
Affects: ADR 0077, D201, D238, and every future dependency this repository adds

## Context

Run 7 is the first run that builds anything from `versions.in.yaml`'s `packages:`
section. Three things went wrong on the way, each of them a measurement.

### 1. The locked psycopg cannot import

`psycopg==3.3.4` installs cleanly and then:

    ImportError: no pq wrapper available.
    - couldn't import psycopg 'c' implementation: No module named 'psycopg_c'
    - couldn't import psycopg 'binary' implementation: No module named 'psycopg_binary'
    - couldn't import psycopg 'python' implementation: libpq library not found

Measured against the locked `python:3.12-slim` digest: the image ships **no
libpq, no `pg_config` and no compiler**. So of psycopg's three implementations,
exactly one is reachable — the `binary` wheel. Control: `psycopg[binary]` lands
`psycopg-binary` and imports; `psycopg[nosuchextra]` does not and raises.

Run 2's note in `versions.in.yaml` called it "psycopg-binary **if the C speedups
are wanted**". The conclusion that note reached (no build toolchain is needed in
the runtime image) is correct. The clause inside it is a value that looked
measured and was not.

### 2. `psycopg-pool` is a separate distribution at a different version

`psycopg` 3.3.4; `psycopg-pool` **3.3.1**. `PSYCOPG_VERSION` does not cover it,
and a reader assuming it did would have pinned a release that does not exist for
that package — D201, arriving a second time through a different door.

### 3. ADR 0077's model met the first package that does not fit it

Written as a lock entry, `--update` refused `psycopg-binary`:

    PSYCOPG_BINARY_VERSION: psycopg-binary 3.3.4 publishes 0 sdists; the lock
    records one canonical artifact per version and cannot choose

Measured: psycopg-binary 3.3.4 publishes **55 artifacts and no sdist** — one
wheel per platform and ABI. Every other package in the file publishes exactly one
sdist and one wheel (pyjwt 2.13.0, as the control: 2 artifacts, 1 sdist, 1 wheel).

### 4. D238 fired

`--update` rewrites `versions.env` wholesale, so adding one package pin also
re-resolves ten images — four of which are pinned by tags that move. Run 2
measured that coupling and found no drift *on the day*, and carried it as an open
item. Run 7 added one package entry and the control caught **two images moving**:

    -POSTGRES_IMAGE=...pgvector:pg18@sha256:691673308c99...
    +POSTGRES_IMAGE=...pgvector:pg18@sha256:2ba9ca5f2e7d...
    -PYTHON_RUNTIME_IMAGE=...python:3.12-slim@sha256:229a2c5bfa27...
    +PYTHON_RUNTIME_IMAGE=...python:3.12-slim@sha256:dd29372629ee...

Locking a dependency would have shipped an unmeasured PostgreSQL upgrade and a
new base image for every service, inside a run about authentication.

## Decision

**A `packages:` entry exists when the version is a choice this repository makes
and the artifact can be dereferenced. Otherwise it does not exist, and the
reason is written where the entry would have been.**

- **`psycopg-pool` is an entry.** psycopg declares `psycopg-pool; extra ==
  "pool"` with no version, so the version is a real choice; it publishes an
  sdist, so the lock can dereference it.
- **`psycopg-binary` is not an entry.** psycopg declares
  `psycopg-binary==3.3.4; extra == "binary"` — an *exact equality* — so the
  version is not a choice anybody here makes, and an entry would be a second
  authority for a value psycopg already fixes. The image installs
  `psycopg[binary]==${PSYCOPG_VERSION}` and the extra decides.

**`bin/lock-versions.sh --update --packages-only`** resolves the `packages:`
entries and carries every image digest through from the existing lock unchanged.
It needs no Docker. It refuses to carry a digest forward when `versions.in.yaml`
names a different tagged reference than the lock holds — because the recorded
digest would then describe the old image, and writing it under the new tag's name
would be a lock that lies. Controls, both run: no image line moved, and editing
`pgvector:pg18` to `pg17` blocked with exit 5.

**The development environment installs the service's runtime set, pinned to
`versions.in.yaml`.** SEC-CRED-002 reads the Argon2id profile back from an
encoded hash, which cannot be done without producing one; the same is true of
every measured claim in Run 7's batteries. A test compares the two files, because
two files naming one version is this repository's recurring defect and something
computing the relation is the only thing that has ever stopped it.

## Alternatives

**Extend the resolver to pick a wheel for the declared target platform.** The
lock already declares `target_platform: linux/amd64`, so "one canonical artifact
per version *and platform*" is a coherent model and would generalise to the next
wheel-only dependency. Not taken here: nothing needs it, because the one package
that provoked it is pinned exactly by its own parent, and a change to the
locking tool's contract made to accommodate a package that does not need locking
is a change made for no measured reason. **If a wheel-only distribution ever
appears whose version IS a choice, this is the work.**

**Install libpq in the image with `apt-get`.** Replaces a pinned wheel with an
unpinned Debian package resolved at build time, in an image whose whole point is
that its contents come from a digest.

**Leave `--update` as it is and accept the image drift.** It re-resolves ten
images whether or not the operator wanted them re-resolved. Run 2 could argue
this was theoretical. It is not.

## Consequences

- `bin/lock-versions.sh --check` is unchanged and still refuses a package entry
  with no digest, which is D201's guard.
- Adding a dependency and upgrading an image are now separate acts. Refreshing
  image digests deliberately is still `--update` with no flag, and should be its
  own commit with its own measurements.
- **The runtime install is not hash-pinned.** `requirements-dev.txt` is, through
  uv; the image's `pip install` names versions only. The lock records an artifact
  digest per package, so the material to close this exists; wiring it into the
  Dockerfile is not done and is carried as an open item.
- `PWDLIB_VERSION` and `FASTMCP_VERSION` remain in the lock and are installed by
  nothing. That is the file's declared nature — "human-selected version
  candidates" — but it is also how `SCALAR_VERSION` survived four sessions, and
  the difference now is that `--check` dereferences every one of them.
