# 0198 — A project owns a migration set, a reviewed surface and a snapshot beside the release's

- **Status:** accepted
- **Date:** 2026-09-10
- **Session:** 20, Run 1 (D1087–D1092, D1096, D1098)
- **Related:** **ADR 0028** (the rendered payload is the immutable unit; what the
  lock records), **ADR 0050** (a reviewed API surface is a generated artifact,
  and the gate cannot approve its own subject), **ADR 0002** (identity is
  derived once, in `naming`), **ADR 0026** (the migration plane connects as
  `migration_user` and reaches the owner only by `SET LOCAL ROLE`),
  **ADR 0197** (what `documented_path` now means), **ADR 0196** (the task
  domain), **D971** (a third project's manifest inside the checkout dirties
  the release).

## Context

An application built on this appliance adds its own tables by forking the
product and editing seven files the release tracks — `migrations/manifest.json`,
`migrations/released.lock.json`, `contracts/postgrest-api-surface.yaml`, the
approved OpenAPI snapshot, and two hand-written test modules. One of those
edits cannot be made without a running host at all, because the snapshot is
captured from a deployed document. ADR 0197 recorded the consequence: `DX-001`
requires the documented path be walked *without source edits*, the outsider's
run made seven, and the claim is therefore answered **no** rather than left
unattempted.

That is the surface every later Stage 3 session builds on, which is why this
session is first.

### What the premises said, and what the tree says

Two of the stage plan's own sentences were wrong in the reassuring direction,
and both were checked rather than accepted.

**The set does not live on the host.** The stage plan proposed the project's
SQL live "outside the release's `migrations/templates/` — on the host beside
the manifest, where D971 already puts a third project's manifest." But a
release is exactly the commit it is named for: `installed_release.assert_clean`
refuses a dirty checkout, the deploy runs `release/bin/migrate.sh` from the
checked-out release, and `upgrade plan` diffs two rendered releases. SQL sitting
beside a manifest on the host would be applied by a release that does not
contain it — a schema no commit determines, which is the state `assert_clean`
exists to refuse. D971's manifest is *configuration*: a domain, a bucket. A
migration is *code*.

**The module is already parameterised.** The stage plan and the README both say
`migrations.load_manifest()` "reads one hardcoded path". It does not:
`load_manifest(path=MANIFEST_PATH)`, `render_migration(..., root=MIGRATIONS_ROOT)`,
`build_lock(manifest, root)`, `verify_lock(manifest, lock, root)` and
`load_lock(path=LOCK_PATH)` all take one. What is hardcoded is the **default**,
and eleven callers use it. The extension point is a change to callers, not to
the module — question 5 of the defect pattern, asked of a definition with
eleven readers.

## Decision

**A project's set lives in the release checkout, tracked, under
`projects/<slug>/`**, and the project manifest names it by a repo-relative path
the schema constrains to that shape:

```
projects/<slug>/migrations/manifest.json
projects/<slug>/migrations/templates/NNNN-*.sql
projects/<slug>/migrations/released.lock.json
projects/<slug>/contracts/postgrest-api-surface.yaml
projects/<slug>/contracts/postgrest-openapi.canonical.json
```

An adopter's fork commits their own directory and edits none of the release's
files. The property the product argues for throughout — that a deploy is a
reviewed commit — is kept, and the adopter's own account agreed with it:
*"a fork is a reviewable diff … which is the property the product is arguing
for and gets."* What made the fork expensive was **which** files it had to
edit, not that it was a fork.

### The version rule, and who enforces it

dbmate is handed one directory and orders by filename, so two sets interleave
by version stamp. A project migration authored before a later release migration
sorts before it on a fresh cluster and after it on a cluster where the
release's arrived first. **Rig 20a measured what `--strict` does with that**, on
the pinned `amacneil/dbmate:2.34.1` against the pinned cluster, with three arms
and a control:

| Arm | Directory | Result |
|---|---|---|
| control | `20260904120030` alone | applied, exit 0 |
| A | `20260904120030` applied, then `20260903000000` added as **pending** | **exit 2, nothing applied**: *"migration `20260903000000` is out of order with already applied migrations, the version number has to be higher than the applied migration `20260904120030` in --strict mode"* |
| B | `20260904120030` applied, then `20260915000000` added | applied, exit 0 |
| C | both files, **fresh** database | both applied in filename order, exit 0 |

So the divergence D1092 predicted is real (arm C applies what arm A refuses),
and **dbmate already makes the refusal** — loudly, with a message that states
the rule exactly, having applied nothing.

The rule therefore stands, and its place in the product is settled by *when* it
fires rather than by *whether* it is needed:

> **A project set's versions must be later than the release lock's newest
> version at the time the project lock is frozen**, recorded in the project lock
> as `follows_release_version` and refused by `verify_lock` otherwise.

That is a **freeze-time** refusal standing in front of a **deploy-time** one
that already exists. It is worth having for the reason every refusal in this
product is moved earlier: dbmate's refusal arrives after the cluster has been
reached, on a host, during a deploy, with a human waiting; `verify_lock`'s
arrives on a workstation before anything is rendered. Neither is a substitute
for the other, and the deploy-time one is the backstop that makes the
freeze-time one safe to be wrong about.

One measured caveat belongs beside it: **`dbmate status` exits 0** and lists the
out-of-order migration as an ordinary `Pending: 1`. The condition is in the
listing and never in the exit code — the same shape as `pgbackrest info` and
`postgrest --ready` (D145, D548), and the same shape as D506, where a
`--runtime status` reading `Applied: 18, Pending: 0` was a green line for work
that had not happened. An operator who reads `status` before `up` sees nothing
coming.

### What the release never does for a project

- It never rewrites a project's lock, and a project verb never rewrites the
  release's. `freeze-lock --project` and `verify-lock --project` are separate
  verbs over separate files.
- It never reads a project's contract into the release's own tests. The
  release's reviewed surface stays project-neutral, and
  `test_the_contract_is_project_neutral` keeps asserting that the release
  contract names no project's slug or domain (D1090).
- The release's anti-vacuity guard is **not** rewritten and **not** loosened.
  With the project's set separate, `test_api_migrations.final_surface` walks the
  release set and its equality against `{"notes","tasks"}` holds for every
  adopter, because an adopter's views are in `projects/<slug>/`. The rewrite
  F-006 proposed was needed only while a tenant's views were in the release
  set. Loosening an equality to a containment check is what the non-negotiables
  call weakening, and it is now unnecessary (D1089).

### The ledger

`bin/migrate.py record_ledger` builds its template digests from the release lock
alone and then indexes it by every *rendered* entry's version. A project
migration's version is absent from that lock, so the first deploy that renders
one raises `KeyError` — **after** dbmate has applied it, leaving a cluster with
an applied migration and no ledger row, from an unhandled exception that never
reaches the `the ledger could not be recorded` path. Found by reading the reader
before changing the writer (D979); a `KeyError` after dbmate returned is the
worst order a failure can arrive in here, because the cluster has moved and the
record has not.

`record_ledger` therefore builds its digests from **every set's lock**, and
records project rows in the same table. The set is recoverable from which lock
holds the version, so no column is added and no platform migration is spent on
the ledger (D1096).

### What a *source edit* is

`DX-001` forbids completing the documented path "without source edits", and
nobody had written down whether adding one's own files to a fork counts.

> **A source edit is a change to a file the release tracks and the project does
> not own.** Authoring under `projects/<slug>/`, and setting a key in a
> gitignored project manifest, is writing the application — which the
> requirement cannot forbid without forbidding the product's purpose.

The definition is stated here so that the walker and the reviewer read the same
one before the walk, and so a second run's count is comparable with ADR 0197's
count of seven. Without it, a later walk could report zero by calling every
edit "authoring". **The claim does not move in this session**: Session 25's
second walk, by somebody who did not build this, is the proof.

## Consequences

- `migrations.py` gains a `MigrationSet` value and `sets_for(document)`. Every
  caller that means *every migration this project applies* switches to
  `sets_for`; every caller that means *the release's migrations* keeps the
  default **and says so in a comment**, because that distinction is the whole
  defect and an uncommented default is where it comes back.
- The project manifest goes to schema 5 with an optional `migrations: {set: …}`,
  forbidden below 5. A project without a set is unchanged in every respect, and
  the host's schema-1 manifests keep deploying (D930).
- A lint bounds what a project set may contain — no `app_private`, no role,
  schema, extension or default-privilege statement, no `SET ROLE` but the owner
  preamble, no drop or alter of a release object, placeholders from an
  allowlist, `FORCE ROW LEVEL SECURITY` on any table in `app`, and a `down`
  block that raises `AP900`. It is the mechanism by which "a project set cannot
  reach the platform's state" is a property rather than a hope.
- The captured control fixture stays a **capture**. A fixture generated from the
  reviewed contract would agree with the contract by construction — question 6's
  shape, a fixture sharing the code's belief — and could never have caught D1036,
  a view the reader could not see. D1054 closes by separation, not by generation.
- Two locks now exist to verify, and a render that reads one and applies two
  would be the next instance of this project's own defect pattern. Both are
  verified before any render or apply.
