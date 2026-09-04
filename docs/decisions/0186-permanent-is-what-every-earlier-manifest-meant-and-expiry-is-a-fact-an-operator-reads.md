# 0186 — Permanent is what every earlier manifest meant, and expiry is a fact an operator reads

- **Status:** accepted
- **Date:** 2026-09-04
- **Session:** 17, Run 3 (`FLEET-LIFE-001`, `FLEET-EXPIRE-001`, D949, D951)
- **Related:** **ADR 0177** (a field is forbidden below the version that
  introduces it and required at or above it), **ADR 0183** (project manifest
  version 2, the last bump, and what a version 1 manifest still does), **ADR
  0185** (the inventory reads and does nothing), **D713** (a TTL that expires
  into destroying the cipher pass is a data-loss timer), **D930** (both host
  manifests are version 1 and no commit can edit them), **D949** (the manifest
  could not say that a project expires), **D951** (every removal path needs a
  human at a terminal).

## Context

The stage brief asks for *"ephemeral/preview projects with TTL metadata"*.
Measured at planning (D949): the project manifest has no field that says a
project ends. `project.environment` is a 2–16 character string and a preview
project is a project whose environment differs, nothing more. Project schema
version 2 arrived one run before this session (ADR 0183); both manifests on
the host are version 1; the decision whether a `--migrate-manifest` helper
ships is open (D930).

Two things are at stake in how the field arrives:

- **What a manifest that says nothing means.** Every project deployed before
  the field existed is permanent. A field whose absence had to be guessed at
  would make the two host manifests ambiguous documents overnight.
- **What the date does.** The specification's *"automatic cleanup"* and the
  stage plan's own D713 pull opposite ways, and D951 measured which way the
  tree already leans: every removal path is root at a terminal with the key
  said back, and the one thing a retirement must never reach — the backup
  repository — is exactly what a timer that "cleans up" would reach first.

## Decision

**Project manifest version 3 adds `project.lifecycle`: `kind` is `permanent`
or `ephemeral`, `expires_at` is required exactly when the kind is ephemeral,
and `permanent` is what every earlier version meant by saying nothing.**

### The field, at the version that introduces it

`lifecycle` is required at version 3 and forbidden below it — ADR 0177's rule
applied to this document a third time, and for the same reason: a manifest
declaring version 2 and carrying a lifecycle is a field read by a version the
manifest does not claim to be. `expires_at` is RFC 3339 UTC at second precision
with a `Z`, the shape `observed_at` has, so one instant has one spelling.

### Absence means permanent, everywhere

`config.project_lifecycle` returns `{"kind": "permanent"}` for a manifest
below version 3, the renderer carries that into outputs version 15, the
deployed document repeats it, and `output_migrations.migrate_v14_to_v15` fills
the same value into a rendered document that predates the field. **The
migration step takes no argument**, and that is a decision against the
module's own rule that every added value is required: every other step adds a
fact the caller knows and the input predates; this one adds the meaning the
version already had, and an argument with one possible value is a constant
with a signature. The three readers are held to one rule by a test that
compares them.

So neither host manifest changes, and the trip deploys both as permanent
projects at version 15 without an edit. `--migrate-manifest` stays an open
decision (D930) because nothing here needs it.

### A project born expired is refused, and nothing else is refused

The render compares an ephemeral project's `expires_at` against its own clock
and refuses one at or before it: the render is the last moment a human is
looking, and a typo in a date is invisible after it. That is the only place a
clock enters the manifest's validation, and it enters only to refuse.

### Expiry is a fact an operator reads, never a trigger

The fleet inventory (ADR 0185) reports an ephemeral project past its
`expires_at` as **expired**, and the retirement verb (Run 4) refuses to retire
an unexpired ephemeral project without a flag saying so. **That is the whole
automation.** No unit, timer, cron or deploy step reads `expires_at` and acts;
`FLEET-EXPIRE-001` asserts that nothing in the release names the retirement
verb. A lifecycle whose last step is a timer is D713's data-loss timer with a
schedule, and the deployment's backups are already one `--destroy` away from
the console action that would orphan them (D957).

## Consequences

- Outputs schema **v15**: `project.lifecycle` on both branches, required, the
  first move since Session 14 Run 7. The isolation matrix classifies
  `project.lifecycle.*` as carrying no authority: two permanent projects share
  it, an ephemeral one differs, and neither says anything about isolation.
- The example manifests move to version 3 and say `permanent`. The two host
  manifests stay at version 1 and mean it.
- An ephemeral project cannot be *migrated into*: a rendered document below
  version 15 can only become permanent. One that is ephemeral was rendered
  from a version 3 manifest that said so.
- The retirement verb (Run 4) reads `lifecycle.kind` to decide which refusals
  apply — a permanent project needs `--permanent`, an unexpired ephemeral one
  `--before-expiry` — and reads `expires_at` for nothing else.
- If a future session wants a timer to act on `expires_at`, this ADR is the
  one it supersedes, and it should start from D713 and D957.
