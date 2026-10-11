# 0270 — A refusal proof proves the decision, not the refusal

- **Status:** Accepted
- **Date:** 2026-10-11
- **Session:** 39, Run 1 (`docs/plans/session-39-implementation-plan.md`, D2340;
  the operator's answer of 2026-10-10)
- **Affects:** `tests/deployment/test_session31_capacity.py`
  (`test_a_third_project_that_does_not_fit_is_refused_on_this_host`, Run 2),
  `tests/external/test_session38_public_lifecycle.py` (`LIFECYCLE` and
  `test_the_refused_resize_changed_nothing`, Run 2), a resize's operation
  result (the `admission` member: the control set's `0005`,
  `operations.RESULT_MEMBERS` and `bin/reconciler.py`, Run 6, D2362),
  `tests/external/test_session39_public_lifecycle.py::test_the_resizes_followed_the_admission_reading`
  (Run 7). Requirements `NODE-ADMIT-002`, `LIFE-LIVE-001`, `LIFE-LIVE-003`.
- **Related:** ADR 0221/0222 (the host declares itself; admission refuses at
  exit 12), ADR 0258 (compute profiles; a resize is admitted like a deploy),
  ADR 0195 (a reader has three outcomes), ADR 0163 (`failed` means the system
  is wrong).

## Context

Two live proofs assert that a refusal HAPPENED: NODE-ADMIT-002's direct test
requires `admit.sh` to exit 12 for a third project, and LIFE-LIVE-001's
lifecycle requires the `large` resize to fail `capacity_exhausted` with
admission as its reason. Both were written on the Hetzner CX23 (3,814 MiB),
where those candidates genuinely did not fit. On OVH (7,745 MiB) `large`'s
840 MiB is admitted and the guardrail of 1,600 MiB sits below a safe available
of 4,620 (D2310, D2292): the host cannot be made to refuse them, so both
claims `failed` at Session 38 while the rule they test held. A proof that
needs a full host to say *no* measured the host, not the rule.

## Decision

**A live refusal proof asserts that the outcome equals what the recorded
reading implies, and prints both numbers.** Admission's own JSON carries the
reading (`requested`, `safe available`, the committed line) beside the
outcome; the proof reads both from the SAME document and requires:

> refused (exit 12, `capacity_exhausted` with reason `admission`) **iff** the
> candidate's charge exceeds `safe available`; admitted (exit 0, the operation
> `succeeded`) otherwise.

- **NODE-ADMIT-002**: `test_a_third_project_that_does_not_fit_is_refused_on_this_host`
  keeps its node id and its structural assertions (the five labelled reading
  lines, the suggested action iff refused, the committed line naming the
  deployed projects, no injected declaration) and replaces the fixed `exit 12`
  with the decision assertion. On a host where the candidate fits, it
  **requires** that the admission rehearsal's injected refusal and its control
  are recorded on this host, in a record that **finished after the deployed
  commit's own commit time** — the record carries no commit and the deployed
  document no deploy time, so the commit's time, read from the checkout, is
  the bound (D2361) — so the refusal path itself is still exercised, against
  an injected declaration, at this release.
- **LIFE-LIVE-001 / LIFE-LIVE-003**: each resize's operation result carries
  `admission` — `requested_mb` and `safe_available_mb`, read by the reconciler
  from the `admit.sh --json` it runs at the resize's `admit` step, on both
  outcomes (D2362) — and the proof reads it back through `/v1`, never from the
  host. It requires the terminal status to be the one that reading implies,
  and the profile the customer read afterwards to be the one admission left.
  **The member is required**: a resize without it (every Session 38 resize)
  fails the proof — that claim already failed, so nothing moves — and there is
  no fallback to an envelope row. Session 38's module reads only its six
  types, so it can be run against Session 39's record too (D2343).

## Consequences

- **Stricter, not weaker**: a wrong decision in EITHER direction now fails —
  a refusal of a candidate that fits, which the fixed assertion would have
  passed, as well as an admission of one that does not.
- The proof no longer depends on the host being full; it depends on the
  reading being recorded, which the instrument does.
- What is NOT proved on a host where everything fits: that a real refusal
  reaches the customer as `capacity_exhausted` end to end. The rehearsal's
  injected refusal covers the admission half; the customer-facing half is
  read only on a host where the candidate does not fit.
