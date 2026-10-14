# 0272 — A branch's expiry is a trigger

- **Status:** Accepted
- **Date:** 2026-10-14
- **Session:** 40, Run 1 (`docs/plans/session-40-implementation-plan.md`, D2433;
  the operator's answer of 2026-10-14)
- **Affects:** the control set's `0006` (`app.control_operations.origin`, its
  CHECK, `app.control_request_expiry`, Run 4); `bin/reconciler.py`'s idle loop
  (Run 5); `schemas/operation-arguments.schema.json` (`expires_at` on
  `branch.create`, `restore.create` and `branch.reset`, Run 4);
  `bin/branch.sh create|reset --expires-in` (Run 6). Requirement `BR-TTL-001`.
- **Supersedes:** **ADR 0186's** *"Expiry is a fact an operator reads, never a
  trigger"* — **for branches only**. For a project it stands, word for word.
- **Amends:** **ADR 0256** by one sentence: *the reconciler requests exactly one
  kind of operation — an expired branch's deletion — through a function
  granted to nobody.*
- **Related:** ADR 0271 (what a branch is), D713 (a TTL that expires into
  destroying the cipher pass is a data-loss timer), D957, D1953(a) (operations
  are created by `/api/v1` and never by the reconciler).

## Context

The stage plan asks for *"branch TTL as a reconciler trigger (the ADR
superseding 0186 for branches only)"*, and the operator chose on 2026-10-14 to
build it. ADR 0186 refused a timer for a reason that still holds for projects:
a lifecycle whose last step is a timer is a data-loss timer with a schedule
(D713), and a project's backups, cipher pass and data are what it would
destroy. Two things are different for a branch:

- **What expiry removes is a copy.** A branch is restored from its parent's
  repository (ADR 0271); deleting it removes its own volume, containers,
  networks and routers — names `naming.branch_names` derives and nothing else
  — and leaves the parent, its repository and its cipher pass untouched. What
  is lost is the work done ON the branch, which the branch's own page already
  says is not backed up (D2441).
- **The person who loses it chose the instant.** `expires_at` is optional and
  set by the member who creates or resets the branch, at least 15 minutes and
  at most 7 days ahead; nothing defaults it.

D1953(a) said operations are created by `/api/v1` and never by the reconciler,
and `app.control_operations.requested_by` is `NOT NULL` (`0003:41`). A trigger
must therefore either break the rule or stay inside it.

## Measured

Rig 40d (2026-10-14, `~/s40/run1/rig40/rig40d.py`): the control set
`0001`-`0005` applied by Session 37's `control_cluster`, then a draft `0006`
carrying the column, the CHECK and the function below.

- An expired branch, the function called twice: the first call inserted ONE
  `branch.delete`, `pending`, `origin = expiry`, `requested_by` the member who
  set the expiry, `arguments = {"branch": "dev"}`; the second returned `NULL` —
  the first row was still open.
- **Control:** with a `project.sleep` `running` for the key, the call returned
  `NULL`, raised nothing, and the row count stayed 2.
- A branch not yet expired: `NULL`, no row.
- `origin = expiry` on a `project.delete` row: refused by the CHECK
  `control_operations_expiry_deletes_a_branch`.
- As the control mode's request role (`auth_service`): `permission denied for
  function control_request_expiry`; `proacl` holds only the owner.
- Without the function's own check, a second open row for the key is refused by
  `control_operations_one_per_project` (`0004:66-68`) — the guard under the
  guard.

## Decision

**A branch's `expires_at` is acted on by the reconciler, and only by asking the
control database to request the branch's deletion on behalf of the member who
set it.**

1. `app.control_operations` gains **`origin text NOT NULL DEFAULT 'member'
   CHECK (origin IN ('member', 'expiry'))`** and **`CHECK (origin = 'member' OR
   type = 'branch.delete')`**. No route sets `origin`; every row a person
   requests is `member`.
2. **`app.control_request_expiry(p_project text, p_branch text) RETURNS uuid`**
   — `SECURITY INVOKER`, `SET search_path = pg_catalog, pg_temp`, **granted to
   nobody**, reached by the reconciler through `container_exec` exactly as
   `control_record_slots` is. It returns `NULL` and writes nothing unless the
   recorded branch is `ready` with `expires_at <= now()` AND no operation for the
   key is `pending` or `running`; otherwise it inserts ONE `branch.delete`,
   `requested_by` = the branch's `expires_for` (the member whose operation set
   the expiry), `origin = 'expiry'`, in the project's organisation.
3. **The reconciler's idle loop** (every `RECORD_SECONDS`, after it records
   slots and branches) calls it once per recorded branch whose recorded
   `expires_at` has passed. The row is then claimed and executed like any
   other `branch.delete`; nothing about the deletion differs.
4. **A project never expires by trigger.** ADR 0186 stands for every project;
   `BR-TTL-001` keeps a test that nothing in the release acts on a PROJECT's
   `expires_at`.
5. `expires_at` is refused (`400 invalid_request`) less than 15 minutes or more
   than 7 days after the request — the minimum so a branch outlives its own
   creation, the maximum so a forgotten branch's 192 MiB and its certificate
   are bounded in time as well as in number (ADR 0271).

## Consequences

- Every operation row remains attributable to a member, and the one the
  reconciler causes says so in `origin`. `GET /v1/operations` shows it like any
  other; the branch's member sees who it was requested for.
- The reconciler still creates nothing of its own accord: it asks a function
  that decides from rows a person wrote. A superuser of the control database
  could insert the same row by hand — as root on the host could anyway (the
  `THR-OPN-RECONCILER` residual).
- An expiry that falls while another operation for the key is open waits for it
  and fires at the next idle pass; an expiry is never lost and never doubled.
- A member removed from the organisation after setting an expiry still names
  the row; the deletion is attributed to who chose it, not to who is there now.
- If a future session wants a project's expiry to act, this ADR is not the
  precedent: D713 is.
