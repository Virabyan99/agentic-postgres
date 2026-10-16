# 0274 — Plans are a release table, enforced before an operation exists

- **Status:** Accepted
- **Date:** 2026-10-16
- **Session:** 41, Run 1 (`docs/plans/session-41-implementation-plan.md`,
  D2519–D2522, D2528, D2538; the operator's answer of 2026-10-16)
- **Affects:** `services/auth-api/app/plans.py` and its re-export
  `src/agentic_postgres/plans.py` (Run 4); the control set's `0008`
  (`app.control_organizations.plan`, `app.control_plan_limits`,
  `app.control_plan_interest`, the lock policy, `app.control_request_operation`
  re-created, Run 4); `control_service.create_project` and `_branch_write`, the
  routes `GET /v1/plans`, `GET /v1/organizations/{org}/plan`,
  `POST /v1/organizations/{org}/plan-interest` (Run 5); `bin/plan.sh` (Run 7).
  Requirements `PLAN-ENT-001`, `PLAN-API-001`, `PLAN-CLI-001`, `PLAN-LIVE-001`.
- **Replaces a guard:** `tests/contract/test_control_projects.py::test_no_string_produces_plan_limit_reached`
  (*"D2160: no entitlement code exists in Session 38"*) becomes
  `test_plan_limit_reached_is_produced_only_by_the_entitlement_readers` — the
  word occurs in exactly the entitlement readers and nowhere else. A stricter
  guard over the code that now exists, authorised here.
- **Related:** ADR 0221 (admission: capacity is a reading), ADR 0246 (the
  control plane holds nothing that opens a project's data or admin plane), ADR
  0247 (nothing `planned` has a control), ADR 0251 (the control set's two
  doors), ADR 0261 (`trial`), D1954, D1955, D1967, D2160, D2166.

## Context

The stage plan's D1967 asks for plans as *"a release file … `free` active,
`premium` `unavailable_during_beta`, every number derived from the new host's
readings"*, enforced on `projects_active`, `branches_total`, `compute_profiles`
and `agent_calls_per_day`, read but not enforced on `storage_gb` and the
retention. D1954 fixes the order: *"the control plane checks the entitlement
first and refuses with `plan_limit_reached` (or `branch_limit_reached`) before
an operation row exists … neither code may be produced by the other's
reader"*. Until this session no code produced `plan_limit_reached` (a guard
said so, D2160); the one branch rule was a constant
(`operations.BRANCHES_PER_PROJECT = 1`) with an SQL twin in `0006`.

The operator answered on 2026-10-16: **Free is one project per organisation,
every compute profile, one branch per project.**

Two facts of the tree shape the rest:

- **The control plane creates no agent.** A project's agents are created by
  that project's own admin through its own auth service; `0028`'s windowed
  quota is set by no route, CLI or code. Writing `agent_calls_per_day` onto a
  project's agents would give the control plane a write into the admin plane
  it describes — ADR 0246 forbids exactly that.
- **No per-project disk quota exists** (D1955). `storage_gb` can be read and
  shown; nothing can hold a project to it.

## Measured

Rig 41d (2026-10-16, WSL `~/s41/run1/rig41/rig41d.py`, output `rig41d.txt`):
the control set `0001`–`0007` applied by `tests/contract/control_cluster.py`,
then a draft `0008` carrying the organisation's plan, the limits table and
`app.control_request_operation` with the entitlement count under `SELECT …
FOR UPDATE` of the organisation's row.

- **Without an UPDATE policy the lock locks nothing.** `0001` gives
  `app.control_organizations` a SELECT and an INSERT policy and no UPDATE
  policy; under FORCE row level security the definer's `SELECT … FOR UPDATE`
  returned NO row (the draft's guard raised `AP500: the organisation row was not
  locked` for every request, both connections, both organisations). Had the
  function not checked `FOUND`, the count would have run unlocked and silently
  (D2538).
- **With a lock-only UPDATE policy** (`FOR UPDATE TO object_owner USING (id::text
  = current_setting('app.control_org', true)) WITH CHECK (false)`): two
  `project.create` requests for ONE organisation from two connections, the first
  holding its transaction 4 s — the second **waited 3.2 s on the row, then
  `AP409: plan_limit_reached`**; one row. **Control:** two organisations — two
  rows, the second request not delayed (0.1 s).
- An UPDATE of the organisation as the owner with no scope set matched no row
  (exit 0, nothing changed); the `WITH CHECK (false)` refusal inside a scope is
  Run 4's test to measure, not this rig's.

## Decision

1. **The plans are a release table**, `services/auth-api/app/plans.py` (the
   control plane's image carries only `services/auth-api/`, the
   `compute_profiles.py` precedent), re-exported by `src/agentic_postgres/plans.py`.
   `PLANS = {"free": Plan(status="active", …), "premium":
   Plan(status="unavailable_during_beta", …)}`; each entitlement is
   `Entitlement(value, enforced: bool, reader: str)`.

   | Entitlement | Free | Premium (defined, unavailable) | Enforced | Reader | Why this number |
   |---|---|---|---|---|---|
   | `projects_active` | 1 | 3 | yes | the control plane: the organisation's projects not deleted + its non-terminal `project.create` rows | Slots are prepared by hand, one per project, and each project charges 192–840 MiB of a node with ~4.4 GiB safe at admission (Session 40's envelope) |
   | `branches_total` | 1 | 3 | yes | the control plane: the project's recorded branches not deleted + its non-terminal branch creations | A branch is a 192 MiB cluster on the same node (ADR 0271); it replaces `BRANCHES_PER_PROJECT` |
   | `compute_profiles` | small, standard, large | the same three | yes | the control plane: the profile names `compute_profiles.py` defines | The operator's answer: every profile on Free; admission still decides a resize by its reading |
   | `storage_gb` | 5 | 20 | **no** — read | usage (`database_bytes`, ADR 0275) | ~10× what a beta project used on this host (Sheet E0 reads `slot3-prod`'s database bytes); no per-project disk quota exists (D1955) |
   | `agent_calls_per_day` | 10,000 | 100,000 | **no** — read | usage (`agent_calls`, ADR 0275) | ~10× a beta project's agent rows; the control plane holds no path to a project's agents (ADR 0246, D2520) |
   | `backup_retention` | *two weekly full backups and the WAL between them* | *planned* | — text | the deployed `repo1-retention-full` 2 (`config.py`) | It is what the product does; it is not a number a plan can move yet |

   **`projects_active` counts a sleeping project** — it holds its slot — and an
   adopted operator project counts like any other (the operator's organisation
   creates nothing).
2. **The SQL twin is `app.control_plan_limits`** (`plan`, `entitlement`,
   `value`), seeded by `0008` and **held equal to `plans.PLANS` by a test** —
   the release table and its SQL copy cannot drift silently.
   `app.control_organizations` gains `plan text NOT NULL DEFAULT 'free' CHECK
   (plan IN ('free', 'premium'))`. **No route writes a plan or a limit**;
   changing an organisation's plan is a root `psql` act, and none is taken in
   the beta.
3. **Two readers, one order, two codes** (D1954, D2521). `create_project`
   reads the entitlement FIRST (`409 plan_limit_reached {entitlement:
   "projects_active", limit, plan}`, *"this organization's plan allows 1
   project; delete one first (Free plan, beta)"*), THEN the slot reading
   (`capacity_exhausted`, unchanged). The authoritative check is in SQL:
   `app.control_request_operation` takes the organisation's row `FOR UPDATE`
   **and raises if it locked nothing** (the measured silent case; a decision
   fails closed, ADR 0195) before counting, for `project.create` and for
   `branch.create`/`restore.create` (its number read from
   `app.control_plan_limits`), raising `AP409: plan_limit_reached` or
   `AP409: branch_limit_reached`. **`branch_limit_reached` keeps its word** —
   D1954's *"or"*, and the 1.18.0 contract.
4. **The lock is reachable by a lock-only policy**: `0008` adds
   `control_organizations_lock FOR UPDATE TO object_owner USING (id::text =
   current_setting('app.control_org', true)) WITH CHECK (false)` — the row the
   caller's role was just checked against is lockable inside its scope, and no
   UPDATE through it can succeed.
5. **A pending creation counts.** With Free's 1, a second creation asked while
   the first is still `pending` or `running` now answers `plan_limit_reached`
   (before this release it answered `409 conflict {operation}` from D2166's
   unique index, which stays as the guard under the guard).
6. **Premium is defined and unavailable.** Its limits are served; *Notify me*
   (`POST /v1/organizations/{org}/plan-interest {plan: "premium"}`, member,
   human session; `apg plan notify-me`) writes ONE row of
   `app.control_plan_interest` (`organization_id`, `plan`, `requested_by`,
   `requested_at`; primary key `(organization_id, plan)`, an upsert) through a
   definer function. The operator reads interest with a documented query
   through `bin/db.sh` on control-prod; no operator command is built.
7. **No override verb.** The stage plan's *"with the limit raised for the
   test"* is met by a second organisation, which the product already lets an
   account create (`create_organization: ACCOUNT`): the lifecycle's own new
   organisation reaches the capacity path with zero projects.
8. `/v1/plans`, `/v1/organizations/{org}/plan`, `apg plan` and the Ledger rows
   say, for each entitlement, whether it is enforced and by which reader:
   *"agent calls per day: shown against your usage; not enforced during the
   beta."*

## Alternatives rejected

- **A quota written onto each agent by the control plane** (D1967's wording):
  a control-plane write into a project's admin plane (ADR 0246). Not built.
- **An advisory lock** (`pg_advisory_xact_lock(hashtext(org))`): it serialises
  the same requests without a policy, but names nothing a reader of the table
  can see and hashes into a space other code could collide with. The row lock
  is the organisation's own row.
- **An override verb for the trip:** a support tool nobody asked for, which
  the beta would then have to bound.

## Consequences

- A limit is a limit under two requests: the second waits on the
  organisation's row and reads the first's row.
- A beta tester who needs a second project is the operator's problem with no
  tool (Session 41 §10).
- `storage_gb` and `agent_calls_per_day` are context, not ceilings; a
  `limit_approaching` notification (ADR 0275) informs and enforces nothing.
- The guard over the word moves from *nowhere* to *exactly these readers*; a
  new producer of the word fails it.
