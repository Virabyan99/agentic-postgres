# 0210 — `follows_release_version` is a record the operator may declare, and the lock says which kind it is

- **Status:** Accepted
- **Date:** 2026-09-16
- **Session:** 28, Run 2 (D1412, D1436)
- **Affects:** no requirement id moves. `TEN-SET-002` is the claim whose subject
  this touches; its proof gains a case and loses none. The **project** lock's
  `schema_version` moves **2 → 3**; the release lock's stays **1**.
- **Related:** ADR 0198 (a project owns a migration set beside the release's, and
  the freeze records the release it was done under), ADR 0206 (the two sets got
  separate directories and separate ledger tables, which is what turned this
  value from a guard into a record), ADR 0195 (a reader has three outcomes and
  the third is reported rather than folded — the rule this ADR applies to a
  field that is sometimes measured and sometimes asserted), ADR 0212 (the
  conversion this unblocks), D912 (never amend an applied migration), D1098
  (rig 20a: one set, two schemas, the measurement the original guard was built
  from), D1288 (beta's refused deploy, and the structural repair), D1412,
  D1436.

## Context

**The refusal this ADR is about no longer prevents anything a cluster would
refuse, and the function that carries it says so in its own docstring.**
`migrations._assert_follows_release_version` was written when both sets rendered
into one directory and applied through one `dbmate` invocation against one
`app_private.schema_migrations`. There, a project version below an applied
release version was an `up --strict` refusal on a deployed cluster and a silent
apply on a fresh one — one set producing two schemas (rig 20a, D1098). ADR 0206
removed that shared ordering space. What survives is a record of **which release
a set was reviewed against**, and a refusal when the set's own versions disagree
with that record.

**The record is written by one line in one command and cannot be written any
other way.** `bin/migrate.py::freeze_project_lock` computes it:

```python
follows = migrations.newest_release_version()
lock = migrations.build_lock(manifest, migration_set.root, follows_release_version=follows)
```

`build_lock` has taken the value as a parameter since ADR 0198. The command is
the only caller, and it always passes the newest version **of the checkout in
hand**. So the record cannot say *this set was frozen against 1.0.0* on a
checkout at 1.6.2, even when that is the truth.

**Who meets this, and what they are told.** A fork made before
`projects/<slug>/` existed keeps its domain inside the release's own files
(`docs/upgrade-guide.md` §1.0). When such a fork re-homes its set — the
conversion ADR 0212 decides — its migrations carry the stamps they were applied
under, which are below the current release's newest, and `freeze-lock --project`
refuses. The refusal's own text says there is no supported way forward and that
the gap is a product decision. This is that decision.

**Measured on rig 28a**, a synthesized pre-ADR-0198 fork built from tag `1.0.0`
(which `git ls-tree` confirms carries no `projects/` at all over 802 tracked
paths), merged to `1.6.2` and re-homed into `projects/tenant/`:

```
freeze-lock --project project.tenant.yaml
  -> these project migrations do not sort after the release version this set
     was frozen against (20260912120032): ['20260905120031'] ...             exit 5

build_lock(manifest, root, follows_release_version="20260904120030")   # 1.0.0's newest
verify_lock(manifest, lock, root)
  -> PASSED
```

**The whole blocker is one computed value in one command.** With the true
record in the lock, every other check in the pipeline accepts the re-homed set
unchanged: the digests match, the ordering rule is satisfied, and
`_assert_follows_release_version` — the refusal itself — passes (D1436).

**And the release's manifest can check the claim.** The release's
`migrations/manifest.json` is append-only: `20260904120030`, the newest version
at tag `1.0.0`, is still the thirtieth entry at `1.6.2`. So a declared value is
not unbounded text. It must name a version this release's own manifest declares.
That is not proof the freeze happened then — nothing in a checkout can be — but
it refuses a typo, a fabricated stamp and a value from another product.

## Decision

### 1. The operator may declare the record, and the default does not move

`bin/migrate.sh freeze-lock --project <manifest>` keeps computing
`newest_release_version()` and writing it. A new optional flag,
`--follows <14-digit version>`, records the declared value instead.

Nothing about the refusal changes: `_assert_follows_release_version` keeps
refusing a set whose versions do not sort above the record, whichever way the
record was obtained. **The guard is not relaxed, removed or made
configurable.** What becomes possible is stating a record that is true.

### 2. A declared value is checked for what a checkout can check

`--follows` is refused unless it is a 14-digit stamp **that the release's own
`migrations/manifest.json` declares**. The refusal names the nearest versions.
This is a plausibility check and the ADR says so where it is implemented: it
proves the value names a release migration this release knows about, and it does
not prove the set was frozen against it.

### 3. The lock records WHICH KIND of record it holds

Project lock `schema_version` moves **2 → 3** and gains
`follows_release_version_source`, one of `"computed"` or `"declared"`.

This is ADR 0195 applied to a field, and it is the half that makes declaring
safe. A value that is sometimes measured from the checkout and sometimes
asserted by a person, with no way to tell which, is a `null` that looks
measured (D600) — the class this project produces most. A reader auditing a
deployment can now answer *was this record computed or asserted?*, which is a
different question from *what does it say?*

A `schema_version: 2` lock still loads and reads as `computed`, because that is
what every existing project lock is. Nothing re-freezes on account of this ADR;
the next freeze of a set writes 3.

### 4. What a set that declares a false record can do

**Nothing to a cluster.** Since ADR 0206 the record orders nothing across sets,
so a false value produces a wrong record and no wrong SQL: the set still applies
from its own directory against its own table, in its own version order. The cost
of a lie is that the lock states a review that did not happen — which is why §3
exists, and why the declared case is visible rather than indistinguishable.

Said plainly because the opposite would be easy to imply: this is not a
privilege escalation and not an ordering bypass. It is a record.

## Consequences

- `freeze-lock --project --follows` is the on-ramp's first moving part. ADR 0212
  depends on it and says so.
- The project lock schema moves, so `test_project_migration_sets` gains the
  schema-3 case and the schema-2 backward-compatible read. No existing
  assertion is weakened: the refusal keeps its exact inputs and its exact exit.
- **`bin/migrate.sh freeze-lock --help` owes the flag in the same commit**
  (D1381 is the same defect one command over: a parser that accepts a flag the
  help does not name makes an operator declaration invisible).
- The refusal message in `_assert_follows_release_version` currently ends *"there
  is no supported way forward today"*. That sentence becomes false in the commit
  that implements this, and a run that leaves it is D1116's failure — the
  message is part of the diff, not a follow-up.
- An operator who declares a record they cannot support has made a false
  statement in a committed file. That is the same class as every other
  declaration this product accepts (`OFFLINE_CLAIMS` under ADR 0202,
  `--also` under D743), and it is handled the same way: it is visible, it is
  attributable, and nothing infers it.

## Alternatives considered

**Derive it from the installed deployed document.** Rejected, and the reason is
a measurement rather than a preference: the deployed document carries
`template_version` — a release *name* like `1.6.0` — and no 14-digit migration
version. Deriving the record would need a mapping from release name to newest
migration version, which exists only in the checkout's own manifest history, so
the derivation is just the declaration with a lookup in front of it. Worse, it
would read a **deployed** document to decide what a **freeze** on a workstation
may write, and `freeze_project_lock`'s own docstring says why it reads the
manifest and not a document: a freeze runs before anything is deployed.

**Remove the refusal.** Rejected. ADR 0206 considered exactly this and declined:
*"removing a released guard is a separate decision from the one that ADR took."*
The refusal costs nothing when the record is true, and it is the only thing that
notices a set whose versions and whose record disagree — which, once a value can
be declared, becomes more worth noticing, not less.

**Make the floor advisory: warn instead of refuse.** Rejected. A warning on a
freeze is read by nobody, the command's output is already three lines a reader
skims, and ADR 0195's rule is that a decision may fail closed. This one does.

**Let `freeze-lock --project` fall back to the oldest project version minus one
when the computed floor would refuse.** Rejected as the worst of the options
available: it would make every refusing set freeze silently, inferring the
record from the thing the record is supposed to constrain. That is the shape of
D930 and D957 — a premise wrong in the reassuring direction.
