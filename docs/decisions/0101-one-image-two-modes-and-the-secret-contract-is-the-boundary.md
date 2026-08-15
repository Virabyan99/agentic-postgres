# 0101 — One image, two modes, and the secret contract is the boundary

Status: accepted
Date: 2026-08-15
Session: 7, Run 1
Settles: D322
Extends: [0084](0084-the-pure-contract-lives-in-the-build-context.md)

## Context

The runbook's §4.1 selects a runtime with `APP_MODE=storage` and describes one
image serving two purposes. D322 recorded that the shape is plausible here and
the reasoning behind it is not this repository's, so the choice had to be made
rather than inherited.

The alternative is a second service directory, `services/storage-api/`, with its
own Dockerfile, its own pins and its own healthcheck. It is the more obvious
answer to "least privilege": storage would hold no signing key, auth would hold
no R2 credential, and neither image would contain the other's code.

**What decides it is ADR 0084's constraint, applied one level out.** That ADR
exists because `compose.yaml` builds the auth service with
`context: ./services/auth-api`, so a `COPY` cannot reach `src/`. The same
sentence is true of any second service directory: **build contexts do not
overlap**, so `services/storage-api/` could not import from
`services/auth-api/app/` any more than either can import from `src/`.

The storage runtime is a JWT verifier (D320) that parses strictly (ADR 0097's
vocabulary), authenticates a subject against the identity registry, and holds a
bounded psycopg pool. Every one of those already exists in `services/auth-api/app/`:

    keys.py         local-only key resolution
    claims.py       the claim contract (ADR 0078)
    tokens.py       the bounded compact-JWT pre-parser
    strict_json.py  the 16 KiB-bounded strict request parser
    errors.py       the closed error vocabulary (ADR 0097)
    settings.py     required-variable declaration
    db.py           the pool with open=False
    scopes.py       the ceiling (ADR 0079, ADR 0100)

A second directory duplicates all eight. ADR 0084 already weighed
duplicate-plus-test against inversion and rejected duplication by name, citing
**D175** — a test comparing two constants goes green again the moment somebody
regenerates the copy — and **D260**, which found three tests in one run comparing
a value against itself. Duplicating a **JWT verifier** is that shape applied to
the component where a silent divergence is least visible and most expensive: two
copies of a verifier drift into accepting different tokens, and both suites stay
green because each tests its own copy.

**The least-privilege argument does not actually turn on the image.** The
Session 7 plan states this and it is worth restating with the mechanism: what
makes "one service cannot read another's credential" true here is
`secrets.required.yaml`'s **per-consumer materialization** — values are written
into `/var/lib/agentic-postgres/secrets/<key>/generations/<id>/<service>/`, one
copy per consumer, at 0600 with that consumer's uid. It is a **filesystem
property**, and it is exactly as true of two containers from one image as of two
containers from two images.

## Decision

**One build context, one image, two containers, and the mode is a runtime
setting that fails closed.**

- Storage code lives in `services/auth-api/app/storage/`, and the two route sets
  are mounted by `create_app()` according to `APP_MODE`.
- `APP_MODE` is a **required** setting in `settings.py`, admitting exactly
  `auth` and `storage`. Not defaulted: a mode that falls back to a value is a
  container whose identity is decided by an omission, and `REQUIRED_VARIABLES`
  is already the mechanism that makes a missing variable a startup failure
  rather than a behaviour.
- **Each mode requires its own secrets and refuses to start without them.** The
  auth mode resolves a signing key at startup; the storage mode resolves an R2
  credential. Neither is present in the other's materialized generation, so a
  container started in the wrong mode fails at startup with a missing input —
  not at the first request, and not by quietly serving the wrong surface.
- The build context keeps ADR 0084's rule unchanged: pure facts both planes need
  live in `services/auth-api/app/` and `src/agentic_postgres/` imports them.
  The object key layout (ADR 0102) arrives that way.

**What this costs, stated plainly rather than discovered later.**

**The image name stops describing what it runs.** The `auth` service declares no
`image:`, so Compose names it `<compose_project_name>-auth`, and a second
container from the same build would carry a name that says `auth` while serving
storage. This is not cosmetic in a project whose recorded defect pattern is *a
value that looked measured and was not*: an operator reading `docker ps` would
be reading a false statement. **Run 7 names the image explicitly and measures
whether Compose builds the shared context once or twice** — that behaviour is a
third party's and is not asserted here.

**boto3 lands in the auth container unused.** It is a real widening of the auth
image's dependency surface, and it is accepted because the alternative widens the
*verifier* surface to two copies. The auth container mounts no R2 credential, so
the library present without a credential is inert.

## Alternatives

**`services/storage-api/`, a second directory.** Honest naming, and boto3 never
enters the auth image. Rejected on the duplication above: eight modules with no
import path between them, including the JWT verifier and the error vocabulary,
tied together only by tests that D175 and D260 have both already shown go green
against themselves.

**A second directory that vendors the shared modules at build time.** A `COPY`
from a parent context, or a build run from the repository root. Rejected on ADR
0084's own reasoning: building from the root puts `schemas/` and the whole
dependency chain in the context, and a vendoring step produces a copy that is
correct at build time and unverifiable afterwards.

**One image, one container, both surfaces served by one process.** Cheapest of
all, and it is what the mode flag is one step away from. Rejected: the two
runtimes hold different credentials, and a single process holding both the
signing key and the R2 credential is precisely the boundary the secret contract
exists to draw. The mode flag is what makes the per-consumer materialization
meaningful; without two containers there is one consumer and nothing is
separated.

**Select the mode at build time rather than at runtime.** Two tags from one
context, each with only its own routes. Genuinely stronger — the storage image
would not contain the signing path at all. Rejected on the build surface it
creates: two builds per project per deploy, two digests to lock and verify, and
a `--render-only` path that has to know which is which. The gain is over an
attacker who already has code execution in the container and no key to sign
with, and the cost is paid on every deploy. Recorded here because it is the
right answer if the storage runtime ever holds something the auth runtime must
never reach.

## Consequences

- `services/auth-api/` is no longer only the auth service's directory. It is
  renamed in neither this run nor this session — a directory rename moves a
  build context, a Dockerfile path, `service_source.SERVICE_ROOT` and every
  `COPY`, for a name. **The name is a divergence to record, not a refactor to
  perform mid-session**, and it belongs to whoever next has a reason to touch
  the build.
- `settings.APP_MODE` joins `REQUIRED_VARIABLES`, so the existing
  `test_the_compose_service_supplies_every_setting_the_service_requires`
  covers it with no new mechanism — the auth service's Compose entry must
  declare it from the moment it exists.
- The auth container gains an `APP_MODE: auth` line in Run 7 and behaves
  identically. Its image gains boto3.
- Run 7 owes two measurements this ADR deliberately does not make: whether
  Compose builds one shared context once or twice, and what the storage
  container's memory floor is (plan §3 — and ADR 0082's warning that
  `ru_maxrss` is a high-water mark makes that one profile per process, with a
  no-work control).
