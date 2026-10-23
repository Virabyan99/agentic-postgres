# 0289 — An absent request series reads zero when the store shows the edge was read for the project

- **Status:** Proposed — accepted when Sheet IR2 reads both witnesses on a live,
  awake project's store (`docs/plans/session-45-implementation-plan.md` Run 1
  step 3; either witness absent there is §9's stop, and another witness would
  be the operator's decision)
- **Date:** 2026-10-23
- **Session:** 45, Run 1 (`docs/plans/session-45-implementation-plan.md`,
  D2805, D2812 (1), D2832, D2833, D2845; the operator's answer at planning,
  2026-10-23)
- **Affects:** `src/agentic_postgres/usage_reading.py` (`requests_below_400`,
  its two witness queries and its reason sentence, beside
  `REQUESTS_BELOW_400_QUERY`; the module sentence), `bin/reconciler.py` (the
  usage pass's request read, `:1502-1505`), `tests/contract/test_usage_sampler.py`,
  `tests/contract/test_idle_sleep.py`, `tests/external/test_session45_idle.py`
  (new). Requirements `USE-IDLE-002`, `USE-LIVE-006` (Run 8); claims
  `idle_absent_series`, `idle_after_wake_live`. **No control-set migration.**
- **Amends:** **ADR 0276** decision 2(a) — how the edge counter's absence is
  read — and nothing else in it: the window, the samples' contiguity, the
  customer-activity signal, the decision's function and its fail-closed rule
  stand word for word. The module sentence of `usage_reading.py:9-10`
  (*"Nothing here returns a zero for a reading that did not arrive"*) gains
  *"…unless the store shows the edge was read for this project"*.
- **Related:** ADR 0168 (the store is routed nowhere and read through its
  container), ADR 0195 (three outcomes), ADR 0223 (every exported series names
  its project), ADR 0275 (the usage samples), D553, D782–D784 (Session 14's
  measurements of `up` and the certificate series), D2539, D2797, D2798.

## Context

ADR 0276's signal (a) asks whether the edge's counter of requests answered
below 400 increased across the idle window. The reconciler reads it with
`usage_reading.store_value(key, REQUESTS_BELOW_400_QUERY, …)`, and an empty
store answer is **unread** (`usage_reading.py:151-157`: *"Truthfully zero is
NOT this case"*), so `app.control_request_idle_sleep` — which needs every
sample in the window present, `requests_counter IS NOT NULL` and the counter
unmoved — keeps the project awake.

**D2805 (Session 44, Run 9).** Traefik's per-service counter exists only after
the service has answered a request. Every operation that recreates a project's
services — a wake, a resize, an export — removes the series, and it returns
only with the next request. A woken project that nobody uses therefore has no
series at all, every sample of its window reads the counter as unread, and
**idle sleep never fires for it** — the case the setting exists for. Session
44's third lifecycle attempt slept only because the instrument itself made
requests after the wake.

The empty answer is genuinely ambiguous. It is what a quiet project looks like,
and it is also what a store that never reached the edge looks like — the
collector's rendered comment says so: *"`up` and the `scrape_*` series are NOT
filterable here … they are the only thing that distinguishes a route nobody
used from an edge nobody could reach — and both are an absent series."* Folding
the second into the first would let a project sleep because its own
observation broke (ADR 0195: a report may not substitute an answer for a
failure to determine one).

The operator chose at planning (D2812 (1)): **an absent series reads 0 only
with a witness that the edge was read for this project; without one it stays
unread.** The sampler alone changes; no migration.

## Measured

- **Session 14 (D783, D784), still the rendered configuration:** with the
  edge's metrics endpoint stopped, the collector's `up{job="edge"}` reads
  **0, not absent**; with `honor_labels: true` the collector's scrape keeps
  `job="edge"` rather than being restamped `job="collector"`. So
  `up{job="edge"} == 1` holds exactly when the last scrape of the edge
  succeeded.
- **Session 14 (D782):** `traefik_tls_certs_not_after` exists while Traefik
  holds a certificate, is absent without one, and is kept by the collector's
  third keep branch — the certificate's `cn` equal to this project's domain
  (`rendering._scrape_keep_regex`). It does not depend on any request having
  been answered, so it survives the recreation that removes the request series.
- **Owed (Sheet IR2, Run 1, root, read-only):** on `slot3-prod`'s store (an
  awake customer project) and `alpha-dev`'s (the control: a project with no
  customer door) — `count(up{job="edge"} == 1)`,
  `count(traefik_tls_certs_not_after)`,
  `count by (__name__) ({__name__=~"up|traefik_.*"})`, and each witness's raw
  label set (`project`, `job`, `instance`, `cn` only) and its
  `count by (project)` form (D2845). **This ADR is accepted on that reading.**

## Decision

1. **`usage_reading.requests_below_400(project_key)`** returns `(int, "")` or
   `(None, reason)`:
   - the request query (`REQUESTS_BELOW_400_QUERY`, unchanged) answers a
     series → its value, exactly as `store_value` reads it today;
   - it answers **no series** → two witness queries against the same store:
     **the edge was scraped and answered** — `up{job="edge"} == 1` — and **the
     store holds this project's own certificate series** —
     `traefik_tls_certs_not_after`, kept only by this project's `cn`. **Both
     present → `(0, "")`**, a read zero;
   - either witness empty, or the store unreachable, or any answer malformed →
     `(None, "the store holds no request answered below 400 and could not show
     the edge was read")`, one constant, unread as today.

   The witness queries keep the `project` label (`count by (project) (…)`,
   D2845) so `store_value`'s own check — every series must name the project
   asked about, or the reading reached the wrong store — applies to them too; a
   bare `count(…)` strips every label and would pass that check vacuously. If
   IR2 shows a witness series without `project`, the plan's bare form is used
   and the reason recorded in this section.
2. **The reconciler's usage pass calls it** in place of `store_value` for the
   request figure (`bin/reconciler.py:1502-1505`). **`store_value` itself is
   unchanged**, so `doctor usage`'s `requests_total` (`bin/doctor.py:949-962`)
   keeps reading an absent series as *not measured*: a report, correct as a
   report; this ADR changes only what a decision reads.
3. **The control set is unchanged.** A read 0 satisfies
   `app.control_request_idle_sleep`'s window clause as written
   (`requests_counter IS NOT NULL`, `max = min`): three samples reading
   `0, 0, 0` are a quiet window. A first request afterwards moves the counter
   0 → N and reads as activity; a series that vanishes mid-window after a
   request reads N → 0 and also as movement — **both in the safe direction**.
4. **The proof is where the defect was found** (D2833): the lifecycle instrument
   makes no request to the slot's routes after the last recreation before its
   idle step and records that it made none; the idle window's samples must read
   `requests_counter` 0, never unread, and the sleep must be requested within
   the window plus one interval (`idle_after_wake_live`).

## Consequences

- A woken project left untouched is idle-slept, as the setting promises; the
  site's idle sentence holds after a wake.
- A store that cannot reach the edge, a collector that is down (its `up` goes
  stale and absent), an edge that answers its scrape with an error (`up` 0) or
  a project whose certificate is missing all keep the project awake — ADR
  0195's third outcome kept for the case it is for, and ADR 0276's
  fail-closed decision unchanged.
- **Residual:** the witnesses show that the store read the edge and that this
  project's name passes the keep filter; they do **not** show that the filter's
  router enumeration is right. A rendered filter that kept this project's
  certificate and dropped its routers would read every window as 0 and could
  let a project sleep while it served HTTP. The enumeration is derived by
  `naming` and pinned offline by the rendering tests; the customer-activity
  signal (b) is independent of it.
- The doctor and the sampler now read one absent series two ways, each
  correct for its use; Session 45's §10 names it.

## Alternatives considered

- **Read an absent series as 0 always** — the simplest change, and the one ADR
  0195 forbids: a broken collector would put every idle-enabled project to
  sleep.
- **Keep it unread and change the decision** (let the control set treat an
  unread counter as quiet after a wake) — the decision would fail open on any
  sampler fault; a migration for a reading problem.
- **Make a request after every wake** (the instrument's accidental cure) — the
  platform would generate the traffic it is measuring, and the customer's
  counter would move for a request they did not make.
- **`absent(up{job="edge"})` as the witness** — D783: `absent()` answers
  *nobody is asking*, not *the scrape succeeded*; a stopped edge reads `up 0`,
  which `absent()` does not see.
- **Only `up` as the witness** — it proves the edge was scraped, not that this
  project's filter keeps anything; the certificate series is the project's own.
