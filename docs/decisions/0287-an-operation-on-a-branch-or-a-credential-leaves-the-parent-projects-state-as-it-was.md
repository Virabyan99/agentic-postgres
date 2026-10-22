# 0287 — An operation on a branch or a credential leaves the parent project's state as it was

- **Status:** Accepted
- **Date:** 2026-10-22
- **Session:** 44, Run 8 (`docs/plans/session-44-implementation-plan.md`, D2795;
  Sheet E0)
- **Affects:** `services/auth-api/app/control_states.py` (`ELSEWHERE`, `_after`),
  `tests/contract/test_control_states.py` (the `unknown` proof's two
  `branch.create` cases replaced by an unknown type; two proofs added),
  `docs/control-plane.md`. Requirement `OPN-STATE-001` (claim `project_states`).
- **Related:** ADR 0195 (three outcomes), ADR 0256 (the state is derived from
  the operation history alone, D2159), ADR 0271–0273 (branches and restore to a
  branch), ADR 0270 (the customer credential rotation), ADR 0285 (the editor
  opens only a `ready` or `updating` project, D2737).

## Context

A project's `state` is computed on every read from its operation history,
oldest first, the latest *deciding* operation winning (ADR 0256). The rules
were written in Session 38 for the six `project.*` types. Sessions 39 and 40
added five types that record the PARENT project's key — `credential.rotate`,
`branch.create`, `branch.reset`, `branch.delete`, `restore.create` — and no
rule: `SUCCEEDED.get(type, "unknown")` and `RUNNING.get(type, "unknown")` read
each of them as `unknown`, and `test_a_history_it_cannot_read_is_unknown`
pinned a succeeded `branch.create` as `unknown`.

Nothing read the state for a decision until Session 44: the Connect page and
the connections route ignore it. The SQL editor (ADR 0285) opens a door only
for `ready` or `updating` — `unknown` is *"the project's state could not be
read; nothing was opened"*, by design (D2737). **Sheet E0 at 1.22.0 found the
kept customer project `slot3-prod` reading `unknown`** — its history ends in
Session 40's branch operations — and the editor refused it. Every project that
has ever had a branch, a restore or a rotation would be refused the same way,
and the sitting's own W1′ (a rotation) and branches would have refused it
again before E1.

## Decision

**An operation of those five types leaves the project's state as it was, in
every status** — pending, running, succeeded, cancelled, and failed with any
code. `control_states.ELSEWHERE` names them; `_after` returns "unchanged" for
them before any other rule.

- **Why it is not folding the third outcome into `ready`** (ADR 0195): these
  operations act on something else. A branch is its own runtime with its own
  state, read at `/projects/{key}/branches`; a restore is a branch created at a
  point (ADR 0271); a rotation changes a credential and the doors' userlists,
  not the project's compute. What they left — a half-made branch, an
  undetermined rotation — is reported where it lives (the operation row, the
  branch record), never by making the project's own state unreadable. The
  parent's state is still exactly what its last `project.*` operation decided.
- **A type outside every table still reads `unknown`** — the replaced proof
  now uses an invented type, so the third outcome is still pinned for what this
  module cannot read. A new proof holds that every type in the closed table
  (`operations.OPERATION_TYPES`, the schema's CHECK, D2054) is either decided
  or in `ELSEWHERE`, so the next type added without a rule fails offline
  instead of on a host.
- **The state is a report, never an admission**: `_project()` is its one
  reader; no route admits or refuses an operation on it, so no concurrency
  changes.

## Alternatives

- **Leave it, and run a `project.export` before every editor walk** (a
  succeeded export reads `ready`). Rejected: the defect ships — the editor
  refuses real projects after any branch or rotation, and `sql_editor` could
  not honestly be `beta`.
- **Give the five types their own running states** (`branching`, `rotating`).
  Rejected: the editor would refuse a project while a branch is created, though
  the project's own doors are untouched; and the closed state list would grow
  for no reader.
- **Let the editor open `unknown` too.** Rejected: `unknown` after an
  interrupted `project.*` operation is the genuine third outcome (D2737), and
  opening it would hide exactly what ADR 0195 reports.

## Consequences

- A contract proof changes with this ADR: two cases of
  `test_a_history_it_cannot_read_is_unknown` move from `branch.create` to an
  unknown type (stricter in kind: it still pins `unknown` for the unreadable),
  and `test_an_operation_on_a_branch_or_a_credential_leaves_the_state` and
  `test_every_operation_type_is_decided_or_elsewhere` are added.
- The `auth` image moves: 1.22.0 is redeployed on all four projects at the
  repair commit (the Postgres image does not move, so no database restarts).
- `slot3-prod` reads `ready` (reconciler-managed) at once after the deploy —
  its last `project.*` operation was its creation.
