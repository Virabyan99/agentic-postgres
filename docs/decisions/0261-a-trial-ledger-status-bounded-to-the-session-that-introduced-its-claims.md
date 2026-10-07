# 0261 — A `trial` Ledger status, bounded to the session that introduced its claims

- **Status:** Accepted
- **Date:** 2026-10-07
- **Session:** 38, Run 1 (D2170)
- **Affects:** `schemas/reality-ledger.schema.json` (the status enum),
  `src/agentic_postgres/reality_ledger.py` (`STATUSES`),
  `src/agentic_postgres/operations.py` (`ACCEPTING_STATUSES`),
  `services/auth-api/app/operations.py` (`ACCEPTED_TYPES`),
  `tests/contract/test_reality_ledger.py` (three new rules), `docs/reality-ledger.yaml`
  (six rows in Run 10, resolved in Run 13). `LEDGER-001`, `CTL-OPS-001`.
- **Related:** ADR 0254 (**amended by this ADR**), ADR 0247 (the fake-complete
  guard), ADR 0163 (three evidence statuses).

## Context

ADR 0254 accepts an operation type exactly when its Ledger row is `available`
or `beta`, and amends ADR 0247 so that a row's STATUS moves in the run whose
evidence makes it true. The guard enforces the second half:
`test_available_and_beta_rows_name_evidence_that_resolves` requires every
`available` or `beta` row's evidence to read `passed` in the newest evidence
document.

Session 38 is the first session to accept a type. For its trip to measure
`project.create`, the type must be accepted **on the deployed commit** — so
its row must be `available` or `beta` there — while the guard requires a
`beta` row's evidence to have passed, which for this session's claims happens
only after the trip, in `evidence/session-38.json`. Session 37 never met this:
no type was accepted. The two rules are each right and cannot both hold on the
deployed commit.

## Decision

1. **A sixth status, `trial`**: *built in the current session and reachable
   while its evidence is collected.* `operations.ACCEPTING_STATUSES` becomes
   `{available, beta, trial}`.
2. **The guard gains three rules and loses none.** A `trial` row's `evidence`
   names only claims whose `CLAIM_INTRODUCED_IN` equals `CURRENT_SESSION`; its
   `target_session` equals `CURRENT_SESSION`; its `customer_text` contains
   *"being verified"*. **A `trial` row from an earlier session fails the guard**,
   so a session cannot leave one behind.
3. **The bump moves the rows to `trial`; the close resolves them.** Session
   38's Run 10 moves `projects_self_service`, `project_deletion`, `export`,
   `region`, `compute_profiles` and `sleep` to `trial`. Run 13 moves each to
   `beta` if every claim it names reads `passed` in `evidence/session-38.json`
   — dropping *"being verified"* from its customer text — and otherwise back to
   `planned` with its operation types removed from `ACCEPTED_TYPES`, the Done
   saying why.
4. **`beta` is not loosened.** Its evidence rule is unchanged: a `beta` row
   still names claims that passed.

## Alternatives rejected

- **Move the rows to `beta` on the deployed commit and skip the evidence
  check until the merge.** The skip ADR 0254 rejected, in the reassuring
  direction.
- **Accept the types by a flag outside the Ledger.** A second source of truth
  for what a customer can press.
- **Measure the lifecycle with the rows `planned`, by a back door.** The trip
  would measure a path no customer can take.

## Consequences

- For one session a customer can press an operation the Ledger names as being
  verified, and says so in the customer's text.
- A session that ends without resolving its `trial` rows fails its own close's
  guard — the gap is named, bounded and closed by the close.
