# 0297 — Every refusal and notice the console shows is a sentence with a next action

- **Status:** Accepted
- **Date:** 2026-10-29
- **Session:** 47, Run 1 (`docs/plans/session-47-implementation-plan.md`, D2951–D2954;
  rows D2981, D2989; the inventory `docs/design/session-47/inventory.md`)
- **Affects:** `services/console/public/messages.js` (new), `app.js`,
  `services/auth-api/app/control_service.py` (`_projects_held`; the
  `branch_limit_reached` body), `models.py`, control migration 0011 (the
  `operation_started` kind; notifications' `operation_id`, `operation_type`),
  `contracts/control-openapi.canonical.json`. Tests: new
  `tests/contract/test_console_refusals.py`; widened `test_control_routes`,
  `test_control_set`, `test_console_*`. Runs 3, 5, 7.
- **Related:** ADRs 0195, 0274 (plans; *"two readers, one order"*, D2521), 0286 (the
  relay's close codes), D2469.

## Context

The console's `REFUSALS` (`app.js:20-37`) holds 16 words, each a sentence, none a
next action. The inventory, **derived** from the server's modules, finds 20 words a
`/v1` caller can meet (`errors.CONTROL_STATUS`, the error documents the control
modules use — directly or through an `errors.*()` helper such as `malformed()` —
and `OPERATION_ERROR_CODES`); five have no entry: `could_not_determine`,
`interrupted`, `last_owner`, `malformed_request`, `operation_failed`. The relay's
five close codes are worded in `sql.js`. `branch_limit_reached` carries no limit.

The person's second creation was refused `capacity_exhausted` — *"No room on this
server"* — while their first was still running. The planning row (D2951) supposed
the capacity check ran before the plan check. **It does not** (`create_project`,
`control_service.py:689-716`, reads the plan first). The cause is D2981: the
service's reader of what an organisation holds, `_projects_held`
(`control_service.py:730-747`), counts an open creation only while its
`project_key` is NULL; the control set (`0008:233-249`) counts it while its key is
NULL **or not yet in `control_projects`**. A creation is given its key at
`allocate` and registered at `registry`, so for almost all of its twenty-odd
minutes the service counts it nowhere: the plan check passes, the slot reading
refuses. The same function serves `GET …/plan`'s `projects_active.held`, which
therefore read **0 of 1** during the person's creation.

## Decision

1. **`_projects_held` counts as the control set counts**: an open `project.create`
   whose key is NULL or names no row of the organisation's projects. A test seeds
   a running creation with its key set and no project row, and reads
   `plan_limit_reached` from `POST /v1/projects` and `held = 1` from `GET …/plan`
   (control: the same seed with the creation finished reads `held` from the
   project row alone). The two readers are held equal by that test, not by prose.
2. **The refusal order is already the customer's**: the plan before the slot.
   It stays, and decision 1 makes it true during a creation.
3. **`messages.js` maps every word** to `{sentence, action, link}`: the sentence
   says what happened in the customer's terms, the action what they can do now (a
   button, a page, or *"Nothing to do: try again in a minute"*), the link a built
   site route or a console route. The set is the inventory's — `CONTROL_STATUS`,
   the control modules' error documents including those reached through an
   `errors.*()` helper, `OPERATION_ERROR_CODES`, the relay's `CLOSE_*` constants
   with 1000, 1006 and 1011, and the console's own `console_unconfigured`.
   **`tests/contract/test_console_refusals.py` derives the set from the modules by
   the inventory's method** (an AST read of `errors.py` and the control modules,
   never a typed list) and fails on a word without an entry and on an entry for no
   word.
4. **`branch_limit_reached` carries `limit` and `plan`**, as `plan_limit_reached`
   carries `entitlement`, `limit`, `plan` and `message`.
5. **Notifications say what happened, and when it started.** 0011 adds the kind
   **`operation_started`**, written by `control_request_operation` for
   `project.create`, `branch.create`, `restore.create` and `branch.reset`; every
   notification carries `operation_id` and `operation_type` (nullable). The
   console words each kind in plain language and links to `#/operations/<id>`; the
   page opens with one paragraph saying what notifications are and which events
   make them. **Nothing is emailed** (unchanged; `site/pages/pricing.md` says so).
6. **A limit the customer can see coming is a banner, not a refusal**: derived
   from `GET …/plan`'s `held` and `limit` on the Overview, *New project* and
   Branches, linking to the console's Plan page and the site's `/pricing`. **No
   notification is written on a refusal** — *"No resources were created"* stays
   true. *New project* is disabled, with the reason, while the organisation has an
   open creation or `held ≥ limit`.

## Consequences

- The person's second creation would now read *"Your plan holds one project, and
  one is being created"*, with a link to it.
- A new refusal word anywhere in the control surface is a red offline test until
  the console can say it.
- `operation_started` adds one row per long operation to a table pruned as today.

## Alternatives considered

- **Reorder the checks** (the planning row's guess) — they were already in the
  customer's order; the defect was a reader, and reordering would have hidden it.
- **A typed word list in the test** — goes silently stale when a word is added;
  the derivation is the guard.
- **Email the notifications** — a new provider and a new secret; not this
  session's, and the pricing page says nothing is emailed.
