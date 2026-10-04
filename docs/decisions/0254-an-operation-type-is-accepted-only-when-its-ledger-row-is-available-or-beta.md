# 0254 — An operation type is accepted only when its Ledger row is `available` or `beta`; a row's status moves with its evidence

- **Status:** Accepted
- **Date:** 2026-10-04
- **Session:** 37, Run 1 (D2054, D2055, D2067)
- **Affects:** `CTL-OPS-001` (registered by Run 9), `LEDGER-001` (one node id
  replaced). `src/agentic_postgres/operations.py`, the control mode's
  `POST /v1/projects` and `GET /v1/operations[/{id}]`,
  `projects/control/migrations/` (`control_operations`),
  `tests/contract/test_reality_ledger.py`, `tests/contract/test_operation_types.py`,
  `docs/reality-ledger.yaml`.
- **Related:** ADR 0247 (**amended by this ADR**), ADR 0246, ADR 0251 (the
  control plane), `docs/plans/stage-5-plan.md` D1953 (operations are rows; no
  executor yet) and D1979 (the fake-complete guard).

## Context

The stage plan's Session 37 says `POST /api/v1/projects` returns an operation
that stays `pending`, with the Ledger saying `planned` for its execution — *"a
`project.create` operation recorded and listed"*. ADR 0247's guard item 3 says
a `planned` row has no control: nothing a customer can press acts on a thing
that is not there. `project.create` acts on `projects_self_service`, which is
`planned` until Session 38. A request accepted into a row that nothing will
ever execute is a control acting on a planned concept, and a `pending` that
never moves is a status claiming a future. The test that names the guard's
empty sets (`test_the_sets_the_guard_will_read_are_empty_today`) asserts that
`src/agentic_postgres/operations.py` does not exist and says Session 37's guard
must replace that assertion.

ADR 0247 also says a row moves *in the run that builds the thing*. Its own
evidence half requires an `available` or `beta` row's evidence to be `passed`
in the newest evidence document, and a live claim first passes in the merged
document a session writes after its trip. A row moved in a building run fails
every workstation gate until the merge — D2021's shape.

## Decision

1. **`src/agentic_postgres/operations.py` holds the CLOSED type table** (D2054)
   — `project.create`, `project.delete`, `project.sleep`, `project.wake`,
   `project.resize`, `project.export`, `branch.create`, `branch.reset`,
   `branch.delete`, `restore.create`, `credential.rotate` — each mapped to the
   Ledger row it acts on, and `accepted(type)` is true exactly when that row is
   `available` or `beta`.
2. **No operation type is accepted in Session 37.** `POST /v1/projects` answers
   `409 {"error":"not_available","ledger_row":"projects_self_service"}` and
   writes no row. `app.control_operations` exists in the shape Session 38 fills,
   and `GET /v1/operations` and `GET /v1/operations/{id}` read it (empty). The
   live end state reads the refusal instead of a pending row.
3. **The guard's operations half is written**: every type names an existing
   Ledger row, and a type is accepted iff its row is `available` or `beta`. It
   replaces the operations half of
   `test_the_sets_the_guard_will_read_are_empty_today`; the console half stays,
   as `test_no_console_exists_yet`, until Session 42.
4. **Not built in Session 37** (D2067): `apg project status` (a project's state
   derives from its operation history, its deployed document and the doctor —
   Session 38's; Session 37 has `apg project show`, the registry record);
   `POST /v1/operations/{id}/cancel` (nothing can be pending); `GET /v1/ledger`
   (its reader is the console, Session 42); `apg project create` (no CLI for a
   refusal).
5. **ADR 0247 is amended** (D2055): **a row's STATUS moves in the run whose
   evidence makes it true; its TEXT moves with the build.** A building run edits
   a row's `stage5_reality` when what it built changes the sentence; the status,
   `evidence` and `controls` move in the run that reads the claims `passed` in
   the newest evidence document — for Session 37, the close, after
   `evidence/session-37.json` exists. `accounts`, `organizations`, `api_keys`,
   `management_api` and `cli_remote` move to `beta` there.

## Alternatives rejected

- **Accept `project.create` into a `pending` row, as the stage plan wrote.** The
  first exception to the guard, in the session that wrote the guard, would
  teach every later session that a plan sentence outranks it.
- **A `planned` operation that is recorded but labelled "not executed".** A
  status a customer must read the small print of is the class the Ledger exists
  to prevent.
- **Moving the rows in the building runs, with the evidence half skipped until
  the merge.** A skip in the reassuring direction is a guard that has stopped
  guarding.

## Consequences

- The stage plan's *"a `project.create` operation recorded and listed"* is
  replaced by a refusal measured live; Session 38 accepts the first type in the
  run whose evidence moves `projects_self_service`.
- Every later session that accepts an operation type moves its Ledger row in the
  same run that reads that row's evidence `passed`.
