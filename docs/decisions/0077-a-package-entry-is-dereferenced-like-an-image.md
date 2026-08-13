# 0077 — A package entry is dereferenced like an image

Status: accepted
Date: 2026-08-13
Session: 6, Run 2
Amends: [0004](0004-version-lock-format.md)
Affects: the version lock (`versions.in.yaml`, `versions.env`, `bin/lock-versions.sh`)

## Context

D201 is the defect this repository is worst at: **a value that looks measured
and is not.** `SCALAR_VERSION: "1.36.4"` sat in the version lock for four
sessions naming a release that has never been published. It survived a gate that
runs `bin/lock-versions.sh --check` on every run of every session.

What it survived *by* is the shape of the check. `--update` resolved every
`images:` entry through `docker buildx imagetools inspect` and wrote an immutable
digest; `--check` verified that digest offline. A `packages:` entry was one line:

    for name, version in sorted(spec["packages"].items()):
        lines.append(f"{name}={version}")

Copied through. There was nothing to dereference even in principle — the entry
was `NAME: "version"`, with no registry and no package name — so the lock could
not have checked it however hard it tried. **A lock verifies what it can
dereference; everything else in it is a comment with a colon in it.**

Session 5 recorded the general repair as unsolved, on the grounds that resolving
package versions needs network in a check that deliberately has none. That
framing is what kept it unsolved, and it is wrong in the same way the original
line was: it treats `--check` as the only place verification can happen.
`--update` already reaches the network. Images work not because `--check` can
reach a registry — it cannot — but because `--update` writes down something
**only a successful dereference could have produced**, and `--check` verifies
that offline.

Session 6 forced the question: the runbook supplied nine exact dependency
versions with no provenance, which is nine instances of D201 waiting.

## Decision

**A `packages:` entry names its registry and its package, and the lock records
the digest of the one artifact it resolves to.** Lock format 1 → 2.

```yaml
packages:
  PWDLIB_VERSION:
    registry: pypi
    package: pwdlib
    version: "0.3.0"
```

`--update` resolves each entry and writes two lines:

    PWDLIB_VERSION=0.3.0
    PWDLIB_VERSION_DIGEST=sha256:6ca30f9642a1467d...

One canonical artifact per version, per registry, measured rather than chosen:

- **PyPI — the sdist.** Exactly one per release, and what every wheel is built
  from. Choosing among wheels would make the lock record a preference; all
  twelve entries were checked and every one publishes exactly one sdist. A
  release with none is a blocking condition rather than a fallback.
- **npm — `dist.integrity`.** Exactly one tarball, always, with a
  registry-published `sha512-` integrity string.

`--check` stays entirely offline. It verifies that every declared package has a
well-formed `<algorithm>:<value>` digest, that no orphan digest survives a
removed package, and that a format-1 bare string is refused by name. **That is
not proof the artifact exists today; it is proof that whoever ran `--update`
found one**, which a copied version string could never be.

A version that does not exist now **blocks** `--update`. It cannot be written
down, because there is nothing to name.

## Alternatives

**Leave it, as Session 5 did, and rely on review.** Rejected on evidence: four
sessions of review did not catch `1.36.4`, and the reason is structural — a
version string is unfalsifiable by reading.

**Have `--check` query the registries.** Rejected, and this is the alternative
that looks right. `--check` runs in the gate and must not be able to pass
because a registry is up, or fail because one is down; ADR 0004 made that a
property. It would also make the offline gate require network, which
`--render-only` and the whole offline mode exist to avoid.

**Vendor the artifacts and hash them locally.** Rejected as disproportionate:
it is a supply-chain posture, not a lock-file repair, and it would put megabytes
of third-party tarballs in the repository to answer "does this version exist".

**Record a resolution timestamp instead of a digest.** Rejected: a date is
another string nothing dereferences, which is the defect with a fresher face.

## Consequences

- **`--update` and `--check` disagree about what they can prove, and that is the
  design.** `--update` reaches out; `--check` verifies the artefact of having
  reached out. The digest is the join.
- **`--update` regenerates the lock wholesale**, so adding one package pin also
  re-resolves every image — and four of the ten are pinned by tags that move
  (`pg18`, `v3.7`, `22-alpine`, `3.12-slim`). Measured immediately before this
  run: **zero drift**, so every image digest came back byte-identical and that
  identity was the control on this change. It is a window, not a property, and
  it is carried as an open item: on a day when a tag has moved, locking a
  package would silently change what the deployment runs.
- Twelve package entries now carry digests, including `SCALAR_VERSION` and
  `PRISMA_VERSION`, which nothing had ever dereferenced.
- Proved by mutation, each with a paired control in the same invocation:
  removing the absent-digest check, widening the digest pattern, and removing
  the format-1 guard each turn a test red. The one that matters is **M4** —
  a copied repository with `pwdlib==0.999.999` in it, where `--update` exits 5
  and says so, and the same rig with the real version exits 0.
- **This does not verify that the artifact is what it claims to be**, only that
  the version exists and was resolved once. Pinning a hash the installer checks
  is a different and larger property, and `requirements-dev.in` pinning nothing
  is the open item it belongs to.
