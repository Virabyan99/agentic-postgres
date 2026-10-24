# 0292 — The support bundle is the doctor's verdicts, recorded by the reconciler, read by a member

- **Status:** Accepted (on Sheet IR4's reading, 2026-10-24 11:53Z: the doctor
  took 7.7 s on `slot3-prod` and 6.6 s on `control-prod`, twelve checks each —
  under the plan's 120 s stop)
- **Date:** 2026-10-24
- **Session:** 46, Run 1 (`docs/plans/session-46-implementation-plan.md`, D2874,
  D2875; Run 1's row D2894; Sheet IR4)
- **Affects:** the control set's **`0010-control-diagnostics.sql`** (new; Run 2),
  `bin/reconciler.py` (`record_diagnostics`, `DIAGNOSTICS_RECORD_SECONDS`),
  `src/agentic_postgres/reconciler_dispatch.py` (`RECORD_DIAGNOSTICS_SQL`, the
  reading's shape), `services/auth-api/app/control_routes.py` and
  `control_service.py` / `control_repository.py` (`GET
  /v1/projects/{key}/diagnostics`), `bin/cloud.py` (`apg project diagnostics
  --output FILE`), `services/console/public/app.js` (Settings: *Support
  bundle*), `tests/contract/test_control_diagnostics.py` (new). Requirements
  `CTL-DIAG-001`, `CTL-DIAG-002` (Run 8).
- **Related:** ADR 0071 (the read-only diagnostic surface), ADR 0158 (the
  deployed document is the address book, not the diagnosis), ADR 0195 (three
  outcomes), ADR 0246 (the control plane holds nothing that opens the node),
  ADR 0256 (the reconciler is the only host actor the plane has), **ADR 0273**
  (the backups reading — the shape this copies, its age and its asleep), D1971
  (the stage plan's support bundle), D2182 (a sleeping project's backups are
  unread).

## Context

D1971 asks for *"a member's `/api/v1/projects/{id}/diagnostics`: the doctor's
twelve readings and the project's operation history, redacted by the canary"*.
Three things in the tree stand between that sentence and a build (D2874):

- **The control plane cannot read a doctor.** It holds no credential to the
  node (`control_states.py:1-6`, ADR 0246); `bin/doctor.py --project KEY --json`
  runs as root on the host and probes containers, routes, TLS, the database,
  the migration ledger, the repository, the archiver, the mirror, the disk, the
  capability lock, the agent record and the workflow worker
  (`bin/doctor.py:1065-1089`).
- **The doctor's `evidence` holds values a customer must not get**: the disk
  check's `mount` is a host path (`diagnosis.py:413`), the workflow check's
  `heartbeat_holder` names a lock holder (`:651`), and every check's evidence is
  the operator's view of the node.
- **"The canary" is a test discipline, not a runtime filter**:
  `tests/contract/test_doctor_redaction.py` plants `SENSITIVE` values and
  asserts the doctor prints none (`:44-45`). There is nothing at run time to
  "redact by".

The tree already has the shape that crosses this gap, built for backups (ADR
0273): **the reconciler records a reading, the plane serves it with its age**.
`record_backups` (`bin/reconciler.py:1210-1228`) calls
`app.control_record_backups(jsonb)` (`0006-control-branches.sql:403-445`) —
**`SECURITY INVOKER`, REVOKEd from PUBLIC, granted to nobody, called as
`postgres` through `container_exec`** (the plan called it a definer; the tree
wins, D2894) — and members read it through `app.control_get_backups(p_user,
p_key)`, a **`SECURITY DEFINER`** reader that enters as the caller
(`control_enter`) and requires a role (`control_require_role(…, 'viewer')`,
`:191-211`).

### Measured (Sheet IR4, 2026-10-24 11:53Z, root, read-only, checkout `4f4b207`)

`bin/doctor.py --project KEY --json` from the host checkout's `.venv`, `stdin`
closed, timed by the caller; only names, verdicts and evidence **keys** printed
(`/home/op/s46-ir4.txt`):

| Project | Exit | Wall | Checks | Worst |
|---|---|---|---|---|
| `slot3-prod` | 0 | **7.7 s** | 12 | ok |
| `control-prod` | 0 | **6.6 s** | 12 | ok |

- **Twelve checks, one of them `route health`** (the routes probe yields one
  check on both): `containers`, `route health`, `tls`, `database`,
  `migrations`, `backup repository`, `wal archiver`, `backup mirror`, `disk
  headroom`, `capability drift`, `agent record`, `workflow` — D1971's *"twelve
  readings"* is the tree's count.
- **The evidence keys confirm why evidence is never recorded**: `disk headroom`
  carries `mount` (a host path), `workflow` carries `heartbeat_holder`, `route
  health` carries `url`, and `agent record` carries row counts of the project's
  own audit — the operator's view of the node.
- **The pass's price**: at ~7 s a project, one diagnostics pass over the
  declared slots costs well under the 300 s child budget per slot, and the
  loop's claim of the next operation waits that long once every 900 s.

## Decision

1. **What is recorded is the verdicts, never the evidence.** Per check:
   `{name, verdict, detail}` — the doctor's own check name, its verdict
   (`ok`/`warn`/`problem`/`unknown`, `diagnosis`'s vocabulary) and its one-line
   detail. **`evidence` never leaves the reconciler**: it is dropped in the
   process that ran the doctor, before anything is sent to the control
   database. **Run 2 read every `detail` sentence the twelve probes can
   produce** (`diagnosis.py`'s `_check` calls; D2897): they are the doctor's own
   sentences, never a third party's bytes (ADR 0159), and the host values in
   them are the disk check's `mount` — in **every** verdict, `ok` included
   (*"N MiB free at <mount>, …"*) — and, in `containers`, the unhealthy
   containers' names. So the reduction (`reconciler_dispatch.diagnostics_reading`,
   a pure function and the tested unit) keeps the sentence and **replaces
   inside it** every host path (`[a host path]`) and every opaque run of 32 or
   more token characters (`[a value not shown]` — a hash, a key, a UUID, a
   canary), then bounds it at 300 characters; a route's public URL, a time and
   a count stay. A guard holds the class: a doctor answer carrying
   `test_doctor_redaction`'s planted values in its `evidence` and in its
   `detail`, and a host path in its `detail`, records none of them.
2. **Control set migration `0010-control-diagnostics.sql`**:
   - `app.control_diagnostic_readings (project_key, check_name, verdict,
     detail, read_at; PRIMARY KEY (project_key, check_name))`, `project_key`
     referencing `app.control_projects(key)`, `verdict` CHECKed against the
     vocabulary plus `asleep`, `detail` length-bounded (300, `reason`'s bound in
     0006); ENABLE and FORCE ROW LEVEL SECURITY; a SELECT policy for the object
     owner only, as `control_backup_readings`.
   - `app.control_record_diagnostics(p_readings jsonb)` — **`SECURITY
     INVOKER`, REVOKEd from PUBLIC, granted to nobody**, called as `postgres`
     through `container_exec` (the tree's `control_record_backups`): an array of
     `{project_key, checks: [{name, verdict, detail}]}` or `{project_key,
     asleep: true}`; any other key refused (`AP422: invalid_readings`); a
     project's rows replaced as one set, `read_at = now()`.
   - `app.control_project_diagnostics(p_user uuid, p_key text)` — **`SECURITY
     DEFINER`**, `control_enter(p_user)`, then
     `control_require_role(control_project_organization(p_key), 'member')`;
     returns the rows. Granted to `{{auth_service}}`.
3. **The reconciler's pass**, `record_diagnostics`, every
   **`DIAGNOSTICS_RECORD_SECONDS = 900`**, beside `record_backups` in `run`'s
   loop: for each declared slot with a deployed document, `bin/doctor.py
   --project KEY --json` as a child with a **300 s budget** (the backups pass's
   child budget), `stdin` closed; exit 0 and 6 both carry a document (the
   doctor's own rule, `bin/fleet.py:105-108`); any other exit, a timeout or
   unreadable output records nothing for that slot and says so in the journal
   (the previous rows stay and age into `stale`). **A slot whose database is
   stopped is recorded as one row, `state` / `asleep`** — never twelve failures
   — read the way `backups_of` reads it (`dispatch.running_argv`). **The pass
   runs between cycles, so its duration delays the next operation claim by that
   long**: Sheet IR4's wall time per project is what prices it, and above 120 s
   on either project is the plan's stop.
4. **`GET /v1/projects/{key}/diagnostics`** (member and above; a foreign or
   missing project the one `not_found`; **a person's session only** — the
   route is absent from `control_roles.KEY_SCOPES`, so a key is `403
   human_session_required`: the bundle is the support conversation's page, a
   person downloads it, D2898): `{project_key, checks: [{name,
   verdict, detail, read_at, stale}], operations: [...]}` — the operations from
   `app.control_project_operations(p_user, p_key)` (`0004:284`, already granted
   to the service). **A reading older than 1,800 s (2 × 900) is served with
   `stale: true`, its verdict unchanged and named as old — never as current.**
   No reading at all is an empty `checks` with the sentence *"no reading has
   been recorded for this project yet"* — ADR 0195's third answer, said.
5. **The CLI** `apg project diagnostics [--project-key K] --output FILE` writes
   the answer as JSON, **0600, refused if FILE exists** (`write_new_private_file`,
   the handoff file's rule). **The console's Settings** gains *Support bundle*:
   the readings with their ages, read-only, every value through `h`.

## Alternatives rejected

- **The plane runs the doctor.** It would need a credential to the node — the
  one thing ADR 0246 forbids.
- **Record the evidence and redact at read time.** The values would sit in the
  control database, its WAL and its backups; a filter forgotten once is a leak
  forever. Dropped where they are produced, they exist nowhere to leak from.
- **Serve the doctor's whole document to the operator only.** That is `sudo
  bin/doctor.sh`, which exists; the bundle is the customer's first page of a
  support conversation.

## Consequences

- A member reads the node's verdicts for their own project, at most ~15
  minutes old, beside the project's operation history: *what the platform last
  saw*, never *what is true now*.
- **A change to a doctor `detail` sentence is a change to what customers
  read** (threat item 29, `THR-CTL-DIAG`): the guard reads every sentence the
  probes can produce.
- The reconciler spends one doctor run per slot every 900 s, and its loop
  claims no operation while it does.
- Ledger: a `support_bundle` row, `trial` at the bump naming
  `support_bundle_live`; `support_access`'s *"a support bundle a member
  downloads is"* is read true at the close only if that claim passed (D2875).
