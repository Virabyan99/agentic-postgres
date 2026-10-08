# 0256 — The reconciler, and the operations it executes

- **Status:** Accepted
- **Date:** 2026-10-07
- **Session:** 38, Run 1 (D2151–D2154, D2159–D2160, D2165–D2168, D2173,
  D2178–D2179, D2184, D2188; rig rows D2189, D2191)
- **Affects:** `bin/reconciler.sh|py` and `systemd/agentic-postgres-reconciler.service`
  (new, Run 6), `src/agentic_postgres/reconciler_dispatch.py` and
  `src/agentic_postgres/control_registry.py` (new, Run 6),
  `schemas/operation-arguments.schema.json` (new, Run 4), the control set's
  `0004` (Run 4), `services/auth-api/app/control_states.py` (new, Run 4),
  `control_routes.py`, `control_service.py`, `control_roles.py`, `errors.py`.
  Requirements `OPN-CLAIM-001`, `OPN-DISPATCH-001`, `OPN-API-001`,
  `OPN-STATE-001`, `OPN-REG-001`, `LIFE-CAP-001`, `OPN-LIVE-001` (registered by
  Run 10).
- **Related:** ADR 0251 (the control plane is a project; `bin/control.sh`'s
  path), ADR 0253 (keys and `/v1`), ADR 0254 (a type is accepted only when its
  Ledger row is reachable — amended by ADR 0261), ADR 0218 (no product child
  reads the terminal), ADR 0221/0222 (admission), ADR 0195 (three outcomes),
  ADR 0050/0178 (no input accepts a command).

## Context

Session 37 built the operation table and left it empty: `POST /v1/projects`
answers `409 not_available` and *"no function inserts an operation"*. Session
38 makes a managed project's lifecycle real on one host, so something has to
turn a row a customer's request wrote into the deploys, retirements and backups
an operator runs by hand today — **as root**, because every one of those
commands is root's. That is the stage's failure mode in its sharpest form: a
customer's HTTP request becoming a root process's behaviour.

What the tree already offered, read at planning (D2151, D2173): `bin/control.sh`
reaches the control database as the superuser through `container_exec.run` and
calls functions granted to nobody (D2093); the deploy's TTY guard passes a
process whose stdin is `/dev/null`; `auth-admin bootstrap` takes
`--password-fd`; materialize, admit, verify and retire take no prompt. What a
creation still needs a human for is the provider half (buckets, tokens, DNS,
the Infisical credential), which a slot prepares in advance (ADR 0257).

Run 1 measured the claim in rig 38f on the shared control cluster with a draft
`0004`: two claimers overlapping deterministically (A holds its claim 2.0 s, B
starts 0.3 s later), ten rounds per variant —

| claim | B gets | B waits | rows claimed twice |
|---|---|---|---|
| `FOR UPDATE SKIP LOCKED` + outer `status = 'pending'` | a distinct row, 10/10 | 0.13–0.17 s | 0 |
| `FOR UPDATE` + outer recheck | a distinct row, 10/10 | 1.84–1.87 s | 0 |
| neither | **the same row**, 10/10 | 1.85 s | **10** |

**`SKIP LOCKED` buys not-waiting; distinctness comes from the row lock and the
status recheck** (D2191). And a claimer SIGKILLed between claim and finish left
its row `running` with its last step; read back at restart, finished `failed
interrupted {"step": …}`, finishing it again refused, and the next claim took a
different row (control: an uninterrupted operation `succeeded`, attempt 1).

## Decision

1. **A root systemd unit with no listener.** `bin/reconciler.py` (+
   `bin/reconciler.sh run|once|status|install`), the unit
   `agentic-postgres-reconciler.service` (`Type=simple`, `Restart=on-failure`,
   `RestartSec=30`, `StandardInput=null`, after Docker and the control
   project's unit). It opens no socket and binds no port. It finds the control
   project with `find_control`, moved to `src/agentic_postgres/control_registry.py`
   and imported by both commands — two control projects is exit 5 at start
   (D2168).
2. **It reaches the control plane the way `bin/control.sh` does** — `docker
   exec … psql -U postgres` through `container_exec.run` — and calls functions
   in the control set's `0004` that are **`SECURITY INVOKER` and granted to
   nobody**: `control_claim_operation`, `control_advance_operation`,
   `control_finish_operation` (refuses a terminal row and a result member the
   type does not declare), `control_interrupted_operations`,
   `control_record_slots`, `control_mark_deleted`, and `control_adopt_project`
   re-created with the region, profile and slot members.
3. **One operation at a time, host-wide.** The claim is `UPDATE … WHERE id =
   (SELECT … WHERE status = 'pending' ORDER BY created_at, id FOR UPDATE SKIP
   LOCKED LIMIT 1) AND status = 'pending'`; the reconciler polls every 5 s and
   holds `/run/agentic-postgres/reconciler.lock` (flock) for each operation.
   **The proof of distinctness is killed by removing the lock and the
   recheck; the proof that a claimer does not wait is killed by removing
   `SKIP LOCKED`** — two tests, two mutations (D2191).
4. **Never resume.** At start, before its first claim, every row still
   `running` is finished `failed`, `error_code interrupted`, `result {"step":
   <last step>}`; an interrupted `project.create` quarantines its slot. A
   creation is not idempotent end to end (`auth-admin bootstrap` refuses a
   second run), so running one twice is the failure, and failing closed with
   the step named is ADR 0195's decision half (D2152).
5. **A closed set of typed operations, validated twice.**
   `schemas/operation-arguments.schema.json` has one branch per accepted type,
   `additionalProperties: false`, every string a pattern; the control mode
   validates a request against it (pydantic, `extra="forbid"`) before the row
   is written, and the reconciler validates the row against the same file
   before dispatch — a row that fails is finished `failed invalid_request`
   with nothing run. **The dispatch table maps each type to one function
   building argv LISTS** from validated members only; an AST guard refuses
   `shell=True`, `os.system`, `os.popen` and a string command, and only
   `profile` and `admin_username` may appear in an argv (D2154).
6. **It runs the existing `bin/` commands** — `admit.sh`, `deploy.sh`,
   `auth-admin.sh`, `database-ports.sh verify`, `systemctl`, `backup.sh`,
   `project-runtime.sh`, `project-retire.sh` — stdin `/dev/null`, output to
   `/var/log/agentic-postgres/reconciler/<op>-<step>.log` (0600; a line names
   steps and exit codes, never an argument value but the key and the profile).
   Its children carry `SUDO_UID`/`SUDO_GID` = the checkout's owner, refused if
   that is root, so a deploy hands `.generated/<key>` back as an operator's
   `sudo` deploy does (D2153; rig 38a measured the hand-back and its control),
   and a FAILED render hands its lock back too (D2189).
7. **It refuses to run on a moved checkout.** It records `git rev-parse HEAD`
   and the porcelain status at start and finishes every operation `failed
   could_not_determine {"reason": "checkout moved"}` when either changes; it
   never runs `git` (D2179). A ship stops it first (D2178).
8. **`project.create`'s steps** (D2173, D2184): allocate a `ready` slot →
   admit (exit 12 → `capacity_exhausted {reason: admission}`, the slot back to
   `ready`, *"No resources were created"*) → deploy 1 → the administrator and
   the handoff (ADR 0260) → `--render-runtime-only` and `database-ports.sh
   verify` with an argv BUILT from the deployed document, never the printed
   line → deploy 2 → `systemctl enable` → a full backup, the schedule, the
   mirror → the registry row refreshed → `succeeded`. Each step is a
   `result.steps[]` entry with its seconds; `progress` 10/30/40/60/70/90/100;
   the operation's timeout 30 minutes, each child its own.
9. **Refusals: one code, two readers** (D2160). `capacity_exhausted {reason:
   no_slot}` comes from the API **before a row is written**, when the slot
   reading the reconciler records (`app.control_slots`, with `observed_at`)
   holds no `ready` slot or is older than ten minutes; `capacity_exhausted
   {reason: admission}` comes from the reconciler. **No entitlement code
   exists in Session 38**; nothing may produce `plan_limit_reached`.
10. **The bound on creation is stock and serialisation, not a time window**
    (D2166): one non-terminal operation per project, one non-terminal
    creation per organisation (partial unique indexes), and the slot stock.
    No rate limiter is built; `/v1/sessions` stays unthrottled (§10).
11. **A project's state is derived from its operation history alone**, by one
    pure function, with `unknown` for an interrupted or undetermined latest
    operation and `ready (operator-managed)` for an adopted project with no
    operation (D2159). The doctor is not read: the control plane holds no
    credential to the node (ADR 0246).
12. **Roles** (D2165): `projects:write` joins the vocabulary; `viewer` reads,
    `member`+ writes; create, export and delete are human-session only (they
    start a handoff, yield a download URL, or destroy); sleep, wake and resize
    accept a key holding `projects:write`; delete is `admin`+.
13. **The registry follows the operations** (D2167). The reconciler refreshes
    its project's row after the last deploy of every operation; deletion sets
    `deleted_at`; `registry` reads a deleted row with its tombstone as
    `agrees (deleted)` and one whose document is still present as `differs:
    deleted`. Alpha, beta and control-prod stay operator-adopted.

## Alternatives rejected

- **A listener on the reconciler** (the control plane calling it). A second
  door into a root process, guarded by whatever authenticates the call. The
  pull through the control database uses the one path already reviewed.
- **Resuming an interrupted operation.** Needs every step idempotent; the
  administrator's bootstrap is not, and a half-made deploy leaves state
  admission then reads (D2135).
- **A definer claim granted to `auth_service`.** Would let the control mode —
  the internet-facing process — claim and finish operations. The claim is
  root's, so its functions are granted to nobody (D2093's shape).
- **A rate limit on `/v1` creation routes.** A limiter nobody measured looks
  complete; with one slot the stock is the bound.
- **Reading the doctor for state.** Needs the credential the boundary forbids.

## Consequences

- A customer's request reaches root only as a validated row of a closed type,
  executed as argv lists of existing commands.
- The reconciler and an operator's sheet are serialised by a rule (stop the
  unit first), not a lock — a host-wide deploy lock is owed (§10).
- An interrupted creation leaves a quarantined slot that only the operator
  clears.

## Amendment (Session 38, Run 7, D2222)

ADR 0186 decided that nothing automatic retires a project: *"No unit, timer,
cron or deploy step reads `expires_at` and acts"*, every removal path a human's
(D951), and `test_no_unit_timer_or_command_names_the_retirement_verb` keeps
`project-retire` out of every unit and command but the verb itself. Decision
§6 above (D2158) makes the reconciler run `project-retire.sh` for
`project.delete`, which that guard refuses.

**The reconciler is the one command besides the verb that may name it**, and
on three conditions the guard now reads with it: the retirement runs only for
a `project.delete` -- a request a PERSON made, human-session only, `admin` or
`owner` (D2165), never a key and never a date -- on a declared slot the
reconciler created (D2218); its argv carries `--permanent` and never
`--before-expiry` (a slot's lifecycle is `permanent`, ADR 0257); and
`bin/reconciler.py` never reads `expires_at`. ADR 0186's sentence stands for
what it was about: no timer acts on expiry. A deletion is still a human's
decision; it reaches the host as a validated row instead of a terminal.
