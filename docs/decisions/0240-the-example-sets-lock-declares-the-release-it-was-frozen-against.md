# 0240 — The example set's lock declares the release it was frozen against

- **Status:** Accepted
- **Date:** 2026-09-30
- **Session:** 34, Run 5 (D1833)
- **Affects:** `projects/example/migrations/released.lock.json`
  (`follows_release_version_source`),
  `tests/contract/test_project_migration_sets.py`
  (`test_the_project_lock_is_frozen_and_verified_apart_from_the_release_lock`).
- **Related:** ADR 0206 (each set is ordered against its own applied set),
  ADR 0210 (a record may be declared), ADR 0212 (the on-ramp), D912, D1440.

## Context

Session 34 adds `0003-note-embedding-events.sql` to the example set (D1781).
The plan said `bin/migrate.sh freeze-lock --project project.example.yaml`.
**Measured, it exits 5**: without `--follows` the freeze records this
checkout's newest release version, `20260929120036` (migration 0036, this
session's), and the set's `20260914120001` and `20260914120002` sort below it.
The refusal names the two ways out itself: re-stamp the migrations, or declare
the release the set was frozen against.

A proof pins the committed example lock's record as **computed** — *"the
committed example lock was written by a freeze on this checkout, so its record
is computed; a `declared` value here would be an unexplained assertion in the
release's own example"*. That was true for as long as no release migration was
stamped after the set's first. It stopped being true the day a release
migration was, and it will be false after every future release migration too:
a set that outlives the release it was frozen against is the ordinary case,
and ADR 0210 exists for it.

## Decision

1. **The example set is frozen with `--follows 20260912120031`** — the value
   its last computed freeze recorded (the re-freeze after release migration
   0031, which `test_project_migration_sets.py`'s own docstring names). The lock records
   `follows_release_version_source: declared`. The value does not change;
   only how it is known does, and the lock now says so.
2. **The proof is replaced by a stricter one.** It asserts the record is
   `declared`, that its value is exactly `20260912120031`, AND that the
   declaration is EXPLAINED: the release's newest version sorts above the
   set's oldest, which is the condition under which a computed freeze refuses
   (measured in this run, exit 5). A future freeze that could compute the
   record again — every set version above the release's newest — makes the
   last assertion fail, and the proof names what changed.
3. **`0003`'s stamp is `20260930120003`**: after the set's own newest
   (`20260914120002`), the only ordering a project set has had since ADR 0206,
   in the set's `YYYYMMDD12000N` convention. Nothing orders `0003` against
   release migration 0036, which creates `app.emit_event`, and nothing needs
   to: a PL/pgSQL body resolves the call when it RUNS, not when it is created,
   and every cluster that runs `0003` has applied the whole release set in the
   same step (`migrate.sh` renders every set, the release's first, ADR 0198).

## Alternatives rejected

- **Re-stamp `0001` and `0002` above `20260929120036`.** They are applied on
  beta; re-stamping amends applied migrations (D912), and ADR 0206's ledger
  matches rows by version, so the deploy would re-apply SQL against objects
  that exist.
- **Declare `20260929120036`.** The freeze refuses it for the same reason it
  refuses the computed value, and it would claim the first two migrations were
  reviewed against a release that did not exist when they were written.
- **A per-migration record (project lock schema 4).** The record is not a
  guard (ADR 0206, D1440); a schema move for a record nothing enforces is a
  decision about migrating every adopter's lock for no reader.

## Consequences

- Every adopter whose set predates a release migration meets the same refusal
  on its next freeze; the refusal's remedy is this ADR's, and the example now
  demonstrates it rather than contradicting it.
- The committed example is no longer evidence that a computed freeze works on
  this checkout. `test_project_migration_sets.py`'s tmp-path freezes are.
