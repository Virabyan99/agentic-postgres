# 0088 — A verifier acknowledges by being recreated

Status: accepted
Date: 2026-08-14
Session: 6, Run 10
Affects: ADR 0051, ADR 0076, D235, D253, D254, `jwt_keys.py`, `bin/render-jwks.py`

## Context

D235 measured that the two-phase rotation this session inherited has never run:
`begin_rotation` and `complete_rotation` have no callers, `render-jwks.py`
publishes exactly one key, and the deploy writes `retire_after: None`
unconditionally. Run 10 builds the path from nothing, and §4 states the property
that is supposed to make it safe:

> promotion is blocked until every verifier has applied the same JWKS checksum,
> and that acknowledgement is a recorded per-consumer generation, not an
> assumption about propagation.

That sentence needs three facts about the locked PostgREST that nothing in this
repository had measured — the committed verification rig uses an HS256 shared
secret, so no offline test has ever pointed PostgREST at an RS256 key set.

## The measurements

Locked PostgREST against the locked PostgreSQL, two published RSA keys and a
third that is never published as the control.

**1. A two-key set verifies both keys.**

    no token (anon)                        401
    signed by A (published)                200
    signed by B (published)                200
    CONTROL signed by X (not published)    401

So an overlap is real: during a rotation both keys verify, which is the whole
point of publishing two.

**2. `kid` selects the key, and its absence does not.**

    signed by A, labelled kid B            401
    signed by A, no kid header             200

A token whose `kid` names a different key in the set is refused rather than
tried against the others; a token with no `kid` is tried against all of them.
`jwt_keys.public_jwk` derives `kid` as the RFC 7638 thumbprint and `build_jwks`
refuses any other, so a token this issuer mints always carries the right one.

**3. A running PostgREST does not re-read the key set.**

    started with A only
      signed by A                          200
      signed by B                          401
    rewrote the file to hold A and B, waited 20s
      signed by B, same container          401      <- unchanged
      CONTROL signed by A, same container  200

The key set is read at startup. Nothing about writing a file makes a running
verifier accept a new key.

## And the defect the third measurement uncovered

`bin/render-jwks.py::write` writes a staging file and `replace()`s it — which is
correct for atomicity and **creates a new inode**. `runtime_override.py` mounts
the JWKS as a single *file*, and a file bind mount binds the inode.

Measured directly, with an in-place rewrite as the control:

    container sees, at the start          inode 1059252, kid A
    staging.replace(target)  ->  host holds A and B, at a NEW inode
    container sees                        inode 1059252, kid A      <- stranded

    CONTROL, same file rewritten in place (inode kept)
    container sees                        inode 1059254, kid A and kid B

**And the restart does not repair it.** After a replace, `docker restart` leaves
the container `Running: false` — the mount source it was bound to no longer
exists, so it cannot start at all.

This has never fired because of D254: `write()` byte-compares and only replaces
when the bytes differ, and no key set has ever changed. **The first rotation
would have stranded every verifier's key set and then failed to restart it.**
That is D253 one layer down, in the artefact a rotation exists to change.

## Decision

**An acknowledgement is a statement about a recreated container**, and the
rotation is a four-phase path in which every phase that changes the published
set recreates the verifiers.

    prepare      publish [active, incoming]; the ACTIVE key is unchanged, so
                 nothing that is signing changes and every existing token stays
                 valid. Recreate the verifiers.
    acknowledge  record, per consumer, the sha256 of the key set that consumer's
                 RUNNING process has loaded -- read from the container, not from
                 the host file it was supposed to have read.
    promote      REFUSED unless every declared verifier has acknowledged the
                 prepared digest. Switch the active key and record `retire_after`.
    retire       not before `retire_after`; publish [active] only, and recreate.

`begin_rotation` and `complete_rotation` are replaced by `prepare_rotation`,
`record_acknowledgement`, `promote_rotation` and `retire_rotation`. That is a
change to a contract test's subject, and this ADR is what authorises it: the two
functions collapsed prepare and promote into one step, which cannot be made safe
because the moment the active key moves is the moment acknowledgement has to
already have happened.

**The operator command is a recreate, never a restart.** `bin/project-runtime.sh
… down` then a deploy, or `compose up --force-recreate`. `docker restart` is
measured to leave the container dead after the key set has been replaced, and
that is the failure to make impossible rather than to document.

**The JWKS keeps its atomic replace.** The alternative — an in-place rewrite —
is measured to propagate, and it reintroduces exactly what the replace exists to
prevent: a verifier starting mid-write opens a partial key set, and a partial key
set is not a smaller key set but a parse error. Correctness of the file wins;
propagation is bought by recreating the reader, which is required anyway because
of measurement 3.

## Alternatives

**Mount the rendered directory instead of the file.** A directory bind mount
resolves the name on each open, so a replaced inode is seen. Refused: the
rendered directory holds `compose.env` and `outputs.json`, and the verifier has
no business reading either. Mounting a directory to solve an inode problem widens
what a container can read to fix something the container does not need to do.

**Write the key set in place.** Measured to work, and it is the shape that lets a
reader open a half-written key set. The window is small and the failure is a
verifier that refuses every token; a rotation is exactly when that window is
entered on purpose.

**Publish each key set under a generation-scoped filename.** Consistent with how
secrets are materialized, and it removes the inode question entirely — the
container mounts a path that never changes contents. It also requires the mount
path to move on every rotation, which means recreating the container anyway,
which is what this decision already requires. Kept as the move to reach for if a
future session needs a verifier that can rotate without a recreate.

## Consequences

- **A rotation is a maintenance window with a service interruption**, and the
  document says so. The verifiers are recreated twice: once at prepare, once at
  retire. Neither moves the active key, so no token is invalidated by either.
- `promote` is the only irreversible step, and it is blocked on recorded state
  rather than on elapsed time.
- Rollback before promotion is deleting the prepared key and republishing
  `[active]`. Rollback after promotion is completing forward: there is no path
  that resumes signing with the retired key, because the retired key's private
  material is gone by then.
- **The acknowledgement is read from the container**, so a verifier that was not
  recreated cannot acknowledge — which is the property that would have caught
  the stranded-inode defect above without anyone knowing it existed.
