# 0293 — `apg control status` reads the control database as root and derives states with the service's own function

- **Status:** Accepted
- **Date:** 2026-10-24
- **Session:** 46, Run 1 (`docs/plans/session-46-implementation-plan.md`, D2876,
  D2877)
- **Affects:** `bin/control.sh` / `bin/control.py` (a fourth verb, `status
  [--json]`; Run 3), `src/agentic_postgres/control_states.py` (new: re-exports
  the service's module, as `plans.py` does), `tests/contract/test_auth_service_shape.py`
  (`SHARED_MODULES` gains `control_states`), `tests/contract/test_control_command.py`,
  `tests/deployment/test_session46_control_status_host.py` (new),
  `docs/node-loss-runbook.md` (§0–§5: the control project restored first).
  Requirements `OPS-CTLSTATUS-001`, `OPS-CTLSTATUS-002` (Run 8). **No
  migration.**
- **Related:** ADR 0084 (a service module the repository imports needs only the
  standard library), ADR 0093 (a `bin/` command imports only `agentic_postgres`
  and `yaml`), ADR 0185 (an operator's read is not a catalog), ADR 0195 (three
  outcomes), ADR 0218 (no product child reads the terminal), ADR 0246, ADR
  0255, ADR 0256 (states from the operation history), ADR 0287 (branch and
  credential operations leave the state as it was); D704 (one derivation, read
  by everyone), D1984 (the stage plan's `apg control status`), D2253.

## Context

D1984 asks for *"`apg control status` (root, the control project's database
read through the container) — owners, plans, entitlements, operations, sleeping
projects, branches"*. The operator today has `control.sh registry` (does the
registry agree with the deployed documents), `slot.sh status` (the slots) and
`doctor`/`fleet` (the node). Nothing answers *who are my customers and what
state is each project in*, short of a root `psql` the operator types.

Two facts decide the shape:

- **As `postgres`, row security does not bind** (`0001-control-identity.sql:610-613`):
  plain SELECTs read `app.control_projects`, `control_organizations`,
  `control_memberships`, `control_operations`, `control_slots`,
  `control_branches`, `control_usage_samples` and `control_plan_limits`.
  `control.py`'s `psql()` already runs `container_exec.run(container, "psql",
  "-U", "postgres", …)` against the control project found by
  `control_registry.find_control` (the `registry` verb's path, `bin/control.py:185-283`).
- **A project's state exists only as a derivation**, by
  `services/auth-api/app/control_states.py::project_state(history)` (stdlib
  only, 141 lines): the latest deciding operation's type, status and error code.
  The column does not exist in any table. A `bin/` command cannot import the
  service's `app` package (ADR 0093) — **unless the module is a shared one**:
  `src/agentic_postgres/plans.py` loads `app.plans` through
  `service_source.load` and re-exports it, and `SHARED_MODULES`
  (`tests/contract/test_auth_service_shape.py:93-101`) proves each such module
  imports nothing but the standard library.

## Decision

1. **`sudo bin/control.sh status [--json]`** (`apg control status` through the
   dispatcher): root required (`require_root`, the other verbs' rule), the
   control project found as `registry` finds it, **one SELECT per section, run
   as `postgres` through `container_exec.run`, no write, no secret column**:
   - **organisations** — name, plan, the owners' usernames, projects active of
     the plan's `projects_active`;
   - **projects** — key, organisation, slot, profile, **state**, the last
     operation (type, status, when); deleted ones counted, not listed;
   - **operations** pending or running, oldest first;
   - **branches** — project, name, state, expiry;
   - **slots** by state (as `control_slots` records them);
   - **notifications** in the last 24 hours, counted by kind.

   No column holding a hash, a key, a token, an address or a credential is
   selected: each SELECT names its columns, and a contract test reads every
   statement the verb can send.
2. **The state is `control_states.project_state`, the service's own function**
   (D704). `control_states` joins `SHARED_MODULES`;
   `src/agentic_postgres/control_states.py` loads `app.control_states` with
   `service_source.load` and re-exports `project_state` and `STATES`, exactly as
   `plans.py` does. The operations are read oldest first, with `type`, `status`
   and `error_code` — the mapping the function documents.
3. **Three outcomes per section** (ADR 0195). A section whose SELECT failed, or
   answered in a shape not asked for, is printed as *"could not be read: <the
   cluster's last line, or the shape>"* and the others are still printed;
   `--json` carries it as `{"unread": "<reason>"}`. **Exit 0** when every
   section was read, **6** when any could not be — never 0 with a section
   missing. Not finding the control project at all is exit 6 before any
   section. *(Amended at Run 3, D2904: `status` keeps
   `control_registry.find_control`'s codes, as the other three verbs do — 6
   when the search could not finish, 3 when no deployed project enables the
   facility, 5 for two. D2905: the reason printed is the cluster's `ERROR:`
   line, never psql's caret under it.)*
4. **The node-loss runbook restores the control project first** (D2877):
   §0–§5 hold the reconciler stopped (`systemctl disable --now`) until every
   project is back; control-prod is restored and deployed first (the console
   and the relay with it), then the kept customer projects by `slot.sh
   redeploy`, then alpha and beta; `slot.sh status` re-read; the telemetry
   plane rebuilt empty (its volumes are not backed up); `control.sh registry`
   agreeing and `control.sh status` exiting 0 before the reconciler starts. §8's
   *the control project LAST* for a **planned move** stays (D2253), with a
   sentence saying why the orders differ: a move keeps the old control plane
   answering until the end; a loss has none to keep.

## Alternatives rejected

- **A control-set view or function that computes the state in SQL.** A second
  derivation of one value, which D704 forbids, and a migration for a read.
- **Serve it from `/v1` to an operator role.** The plane would gain a
  cross-tenant read — the registry administrator is a person with an
  organisation, not the operator's root.
- **Copy `project_state` into `src/`.** Two copies of a rule drift; the shared
  module is the tree's existing answer (ADR 0084).

## Consequences

- The operator answers *what does each customer have and in what state* with
  one root read, from the same function the API uses.
- `control_states` must stay stdlib-only; `SHARED_MODULES`' test enforces it.
- The host proof (`control_status_host`) holds `status --json` to
  `control.sh registry` and `slot.sh status` on the deployed host after the
  sweep's deploys.
