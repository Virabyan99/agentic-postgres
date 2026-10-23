# 0276 — Idle sleep is a trigger

- **Status:** Accepted; decision 2(a)'s reading of an absent counter is amended by ADR 0289 (Session 45)
- **Date:** 2026-10-16
- **Session:** 41, Run 1 (`docs/plans/session-41-implementation-plan.md`,
  D2525, D2531, D2534; the operator's answer of 2026-10-16)
- **Affects:** the control set's `0008` (`app.control_projects.idle_sleep_minutes`
  and `idle_sleep_set_by`, the origin CHECK widened,
  `app.control_request_idle_sleep`, `app.control_set_idle_sleep`, Run 4);
  `PUT /v1/projects/{key}/idle-sleep` (Run 5); `bin/reconciler.py` after each
  usage pass and `reconciler_dispatch.REQUEST_IDLE_SLEEP_SQL` (Run 6);
  `apg project idle-sleep` (Run 7). Requirements `USE-IDLE-001`, `USE-LIVE-002`.
- **Supersedes:** **ADR 0186's** *"expiry is a fact an operator reads, never a
  trigger"* **for one more field only** — a project's idle-sleep setting. For
  a project's `expires_at` it stands, word for word (ADR 0272 kept it for
  projects; this ADR does too).
- **Amends:** **ADR 0272** — *the reconciler requests exactly one kind of
  operation* becomes **two**: an expired branch's deletion and an idle
  project's sleep, each through its own function granted to nobody. **ADR
  0256** by the same sentence.
- **Related:** ADR 0195, ADR 0259 (a sleeping project's archiver is stopped),
  ADR 0275 (the samples it reads), D1953(a), D1956, D2147, D2456 (the workflow
  worker's 5 s heartbeat).

## Context

D1956 asks for idle sleep — *suspend when inactive* — as *"a per-project
setting the reconciler acts on, reading idleness from the edge's request
counter and `pg_stat_activity`"*. D2147 deferred it to Session 41 because the
two signals were unmeasured and no sampler owned them. The operator answered
on 2026-10-16: **opt-in, default never, 15 / 30 / 60 minutes.**

Three facts make the naive signals wrong:

- **Some backend is always there.** PostgREST, auth and `mcp` hold pooled
  connections and the workflow worker commits a heartbeat every 5 s (D2456),
  so a backend count is never zero. Only the project's two **customer** roles
  (ADR 0269) are the customer's activity.
- **Anything on the internet reaches a public name.** A scanner's request moves
  the edge's counter with no customer behind it.
- **An idle sleep stops the customer's archiver** (ADR 0259) without a person
  asking at that moment: its last restore point becomes the moment it slept.

## Measured

Rig 41d (2026-10-16, WSL `~/s41/run1/rig41/rig41d.py`): a draft
`app.control_request_idle_sleep` over the control set `0001`–`0007`, a project
set to 15 minutes, samples written at −840, −540, −240 and −10 s, all `active`,
the counter equal, the last customer activity two hours old.

- The call inserted ONE `project.sleep`, `pending`, `origin = idle`,
  `requested_by` the member who set the setting; a second call with that row
  pending returned `NULL`.
- **Control:** the same window with the −540 s sample missing → `NULL`, no
  row (a gap of 600 s exceeds 1.5 × the interval).
- `origin = idle` on a `project.wake` row: refused by the widened CHECK.

**Sheet E0** (2026-10-16 10:37–11:09Z, `slot3-prod` at `8cc3440`, reads only;
D2539):

- **At rest the signals do not move.** The edge counter's sub-400 part read
  8, 8, 8 at T0, T0+15 and T0+30 min with no traffic from the workstation (all
  eight on the project's health router); the customer roles held no backend.
- **A control moves each.** A GET to `/api/rest/` (200) added one under
  `code=200`; a GET to `/api/app` (404) appeared under `code=404` and not in
  the sub-400 part; one `psql` through `pool.slot3…` left one `customer_app`
  backend, `idle`, whose `state_change` was the query's instant and had not
  moved 97 s later, though the transaction-mode pooler kept the connection
  (`server_reset_query_always = 1` stamps it at release).
- **So "no customer backend" is the quiet case**, and must read as quiet:
  only a failed read is *unread*.

## Decision

1. **A setting**, `app.control_projects.idle_sleep_minutes int NULL CHECK
   (idle_sleep_minutes IN (15, 30, 60))` — `NULL` is *never*, the default — and
   `idle_sleep_set_by uuid`, set by `PUT /v1/projects/{key}/idle-sleep
   {minutes: 15|30|60|null}` (member and above, keys with `projects:write`) and
   `apg project idle-sleep --project-key K --minutes 15|30|60|never`.
2. **The signal**, both from ADR 0275's samples:
   (a) **no HTTP request answered below 400** — the project's edge counter
   restricted to `code < 400` does not increase between any two samples in the
   window (a scanner's 404 does not keep a project awake);
   (b) **no customer-role activity** — `last_customer_activity` (the latest
   `backend_start` / `state_change` of any backend whose role is one of the
   project's two customer roles, or the sample's instant if one is not `idle`)
   is older than the window's start in every sample. **A sample with no
   customer backend records `NULL` and is quiet**; only a failed
   `pg_stat_activity` read names the figure in `unread`. A backend closed
   before the next sample is the case a sample can miss; PgBouncer's default
   `server_idle_timeout` (600 s) outlives the 300 s interval, which Session
   41's Run 8 reads. Platform roles are ignored: they are the product's own
   work. An operator's `doctor --project` crosses the edge with a 200 and keeps
   a project awake for a window — the safe direction.
3. **The decision is the control database's.** After each usage pass the
   reconciler calls **`app.control_request_idle_sleep(p_project text)`** —
   `SECURITY INVOKER`, **granted to nobody**, beside `control_request_expiry` —
   which inserts ONE `project.sleep` with **`origin = 'idle'`** and
   `requested_by = idle_sleep_set_by` **only if** the setting is set, the
   project is awake, its last operation finished at least the window ago (a
   wake restarts the window), no operation for the key is open, **and every
   sample the window should hold is present** (`ceil(minutes × 60 / 300)`
   samples, contiguous within 1.5 × the interval, the first within 1.5 × the
   interval of the window's start and the last of now) **with neither signal's
   figure unread**. **A missing, late or unread sample means *not idle***: the
   decision fails closed.
4. **The origin CHECK** becomes `origin IN ('member', 'expiry', 'idle')` and
   `origin = 'member' OR (origin = 'expiry' AND type = 'branch.delete') OR
   (origin = 'idle' AND type = 'project.sleep')`.
5. **The consequence is said where it is set** (D2534): the route's answer,
   `apg project idle-sleep`'s output, the `idle_sleep` Ledger row and the
   notification each say *"while it sleeps, its backups stop: its last restore
   point is the moment it went to sleep"*. Sleep itself is unchanged.
6. **Wake stays by request.** `wake_on_connect` stays `planned`; the
   notification (ADR 0275) names `apg project wake`.

## Consequences

- Every idle sleep is attributable: a member chose the setting, `origin`
  says the reconciler asked, the notification says why.
- A sampler that stops, or a figure it cannot read, keeps every project awake
  — the safe direction for a customer, the expensive one for the node.
- The reconciler still decides nothing: it asks a function that decides from
  rows anyone with the database can re-read.
- If a future session wants a project's `expires_at` to act, this ADR is not
  the precedent either: D713 is.
