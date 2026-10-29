# 0296 — A long operation is visible: a step log, open operations listed, a subject served, typical durations from one module

- **Status:** Accepted
- **Date:** 2026-10-29
- **Session:** 47, Run 1 (`docs/plans/session-47-implementation-plan.md`, D2948,
  D2949, D2950, D2975; rows D2990; rig 47e)
- **Affects:** `projects/control/migrations/templates/0011-control-operation-steps.sql`
  (new; control set 10 → 11), `services/auth-api/app/control_routes.py`
  (`GET /v1/operations` gains `status`), `control_service.py`, `control_repository.py`,
  `models.py`, `contracts/control-openapi.canonical.json`, new
  `services/auth-api/app/operation_steps.py` (the service's own module; its tests
  load it by `service_source.load`, ADR 0084 — D2992, D2998),
  `services/console/public/progress.js` and the tracker view. Tests: new
  `tests/contract/test_control_operation_steps.py`, `test_operation_steps.py`;
  widened `test_control_set`, `test_control_routes`, `test_auth_service_shape`
  (`SHARED_MODULES`). Runs 3–5.
- **Related:** ADRs 0195, 0254 (the operation reader), 0256 (the reconciler), 0291
  (the token shown once), D2895 (`arguments` never served).

## Context

A creation is nine reconciler steps (`reconciler_dispatch.STEPS["project.create"]`);
`app.control_operations` keeps only the **current** `step` and `progress`. The
only per-step measurement (slot6-prod, 1.20.0, `capacity.ENVELOPE`) puts 1,259.1 s
of 1,369.8 s — **92 %** — in `backup`, whose progress number is 90 (inventory §3).
So the console printed *"Operation running, backup (90%)"* for twenty minutes,
and the person read it as a hang. The console never calls `GET /v1/operations`;
it follows one operation by the id it got at acceptance, held in the tab — after a
refresh, *"there was no record of that project anywhere"*. And an operation read
never serves its `arguments` (D2895), so even a listed creation could not say which
project it is.

## Measured

Rig 47e (`~/s47/rigs/47e/`, 2026-10-29): a migrated control cluster
(`tests/contract/control_cluster.py`, rig 46c's method) with a draft of decision 1
applied as the object owner. The reconciler's calls as the superuser, each its own
transaction, 1.1 s apart: `allocate`, `admit`, `admit` again, `deploy-1`. Read back
by the member through the widened `control_get_operation`: **three** steps in
order, three distinct strictly increasing `started_at`, the repeated `admit`
keeping its first time; `subject` exactly `{"name": "My app", "profile":
"small"}`, the digest, the member name `handoff_sha256` and the administrator name
absent from the whole row. The request role selecting the table directly:
`permission denied` (control: the superuser reads 3). A non-member reads 0 rows
(control: the member, 1). An advance after the operation finished: refused
`AP409: not_running`, still 3 rows.

## Decision

1. **Control migration 0011, `app.control_operation_steps`**: `(operation_id uuid
   REFERENCES app.control_operations(id) ON DELETE CASCADE, step text CHECK (step ~
   '^[a-z][a-z0-9-]{0,31}$'), started_at timestamptz DEFAULT clock_timestamp(),
   PRIMARY KEY (operation_id, step))`; ENABLE and FORCE row-level security; `REVOKE
   ALL … FROM PUBLIC`; **one policy, SELECT to the object owner, `operation_id IN
   (SELECT id FROM app.control_operations)`** — so it follows the operations
   policy's own membership filter; no request role is granted the table.
   `control_advance_operation` (same signature) inserts `(p_id, p_step) ON CONFLICT
   DO NOTHING` after its update: a step's row records when it **first** began. The
   step names are `reconciler_dispatch.STEPS`'; a test holds them equal.
2. **Both operation readers serve `steps` and `subject`** — dropped and created
   again, wider, with their grants (0007's shape). `steps` is `[{step, started_at}]`
   in start order (`[]` for an operation not yet claimed). **`subject` names the
   thing the operation acts on and nothing else**: `{name, profile}` for
   `project.create`; `{branch}` for the four branch types (the schema's member);
   `{profile}` for `project.resize`; `{}` for the rest — computed by one helper,
   `app.control_operation_subject(type, arguments)`, executable by no role
   (D2994). **Never `handoff_sha256`, `admin_username`, a verifier or any other
   argument** — a test writes every argument member the schema allows and asserts
   each absent unless named here.
3. **`GET /v1/operations?organization=<id>&status=open`**: `status` takes the one
   value `open` (`pending` or `running`); anything else is `invalid_request`, 422 —
   the route's own answer to a bad query, as for a missing `organization` (D2993);
   absent, the list is unchanged. Filtered in the service over the existing
   reader — no new SQL argument.
4. **`services/auth-api/app/operation_steps.py`** (standard library only; the
   service's module, loaded by its tests through `service_source.load` as
   `connection_snippets` is — no `src/` re-export, which nothing but a test would
   import, D204, D2998): per operation type, the ordered steps, a plain
   label each (*"Taking the first full backup"*, never `backup`), the measured
   **typical time** as a range (`low`, `high`, each citing its envelope record),
   **per-step seconds where a per-step measurement exists** (`project.create`'s,
   slot6-prod), and the reconciler's **bound**. Every operation read serves
   `expected: {steps: [{step, label, typical_seconds}], typical_seconds: {low,
   high}, bound_seconds}` — computed by the service, never stored; `null` for a
   type the module does not know (D2995). `tests/contract/test_operation_steps.py`
   holds the steps equal to `STEPS`, the bounds to `bin/reconciler.py`'s, and every
   number to the words of the measurement it cites; Run 14 moves them from the step
   log's own readings.
5. **The tracker is a route**: `#/operations/<id>`. Every load reads the operation
   from the API; the page holds nothing a refresh could lose. It shows each
   expected step as done / current / to come, the elapsed time of the whole and of
   the current step, and the typical time — **no percent bar for a step whose
   time dominates**; the console's words are *"usually about N minutes"*, never a
   promise. The reconciler's time bounds (30 minutes; 60 for `branch.create`,
   `restore.create`, `branch.reset`) are shown as *"stopped after"* limits.
   **All eleven types** use it (D2975). The Overview lists the organisation's open
   creations, by `subject.name`, as pending projects that link to the tracker.
6. **The handoff token stays shown once** (ADR 0291). After a refresh it is gone;
   the tracker says so in one sentence and adds *"You do not need it to connect."*
7. **Elapsed time is the browser's clock against the server's `started_at`** and
   is worded *about*; a step with no row is *not started*, an operation the reader
   could not read is the third outcome (ADR 0195), never *0 s*.

## Consequences

- A refresh, a second tab and a second device show the same creation.
- One small table grows by about ten rows per operation, deleted with it.
- The step labels become customer-facing words; renaming a step is now a contract
  change (`STEPS`, `operation_steps`, the test).
- What the tracker cannot show: progress *inside* a step (the backup's bytes).
  That would need the reconciler to read pgBackRest's own progress; a Stage 6
  candidate.

## Alternatives considered

- **Keep the percent and add a spinner** — the person's finding was that a
  number standing still reads as a hang; a spinner says the same.
- **Hold the operation id in `localStorage`** — survives a refresh, not another
  device, and the console holds no storage (ADR 0281's rule).
- **Serve `arguments` with the digest removed** — a subtraction from a list that
  grows; decision 2 is a closed allowlist instead.
- **The console's own copy of the typical seconds** — two sources for one
  customer-facing number; the service computes it from one module.
