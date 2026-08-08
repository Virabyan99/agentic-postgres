# 0039 — A claim belongs to the session that introduced it

Status: accepted
Date: 2026-08-08
Session: 3, Run 9

## Context

`evidence_claims.CLAIMS` is one dictionary mapping a claim name to the
acceptance requirements that prove it. Session 2 put two entries in it and had
one gate, so "every claim" and "this gate's claims" were the same set and nothing
had to distinguish them.

Session 3 adds four, and there are now two gates. Left flat, the set breaks in
both directions:

- `bin/session-02-check.sh` would resolve Session 3's claims, find their proofs
  absent from a Session 2 run, and report them `not_run` — the Session 2 gate
  failing over a guarantee Session 2 does not make.
- Worse, `merge` refuses to write a document that is **silent** about a claim,
  which is the check that stops a half nobody ran from passing unnoticed. With
  Session 3's claims in the flat set, that check makes the Session 2 merge
  unsatisfiable by any pair of runs: no Session 2 gate can produce them, and the
  merge will not proceed without them.

The second one matters more than the first. A guard designed to catch an
unmeasured claim would have become a permanent blocker on a session that was
already complete and deployed.

## Decision

**A claim's session is the latest `target_session` of the requirements it names,
read from the acceptance registry.**

Derived, not declared beside the claim — for the same reason `claim_mode` is
derived from pytest markers rather than written down: a claim that gains a
requirement from a later session becomes that session's claim without anyone
remembering to say so.

`claims_for_mode`, `static_nodeids_for_mode` and `results_for_mode` take a
required `session`. No default: a default would be a fourth place that knows
which session is current, and every caller here already knows which session's
gate it is.

**Claims are cumulative.** `claims_through_session(3)` includes Session 2's
`isolation` and `secret_leakage`, because the product did not stop making those
promises when it grew a database. The Session 3 gate proves them and its evidence
records them.

## Consequences

`evidence/session-03.json` carries six claims; `evidence/session-02.json` carries
two, unchanged. A Session 2 evidence file produced before this ADR and one
produced after are identical.

Adding a claim to `CLAIMS` now has a consequence beyond the session adding it: if
its requirements are all from earlier sessions, it becomes an earlier session's
claim retroactively, and that session's merge starts demanding it. That is the
correct behaviour — a guarantee provable by Session 2's tests *is* a Session 2
guarantee — but it is the trap in this design, and `test_every_claim_belongs_to_a_session_the_release_has_reached`
is what makes the session assignment visible rather than implicit.

Session 3's four claims are `least_privilege`, `row_level_security`,
`database_isolation` and `boot_convergence`. Not every Session 3 requirement is a
claim: `DBX-MIG-002` and `DBX-MIG-003` are about render determinism and preflight
refusal, both entirely properties of a checkout, and a claim needs at least one
proof that runs against a deployment. They are proved and they appear in the
acceptance matrix; they are not guarantees about a running system, so this
session's evidence does not name them as ones.

## Alternatives considered

**A `session:` key beside each claim.** Simpler to read, and it is a second place
the answer lives. The registry already records `target_session` per requirement,
and two sources for one fact is how a claim ends up asserting it belongs to a
session none of its proofs do.

**A separate `CLAIMS` table per session.** Then a Session 2 claim that Session 3
still makes has to be written twice or imported, and the cumulative property —
the one that matters — becomes a convention instead of a computation.

**Filtering in the gate scripts.** Two shell scripts would each hold a list of
which claims are theirs, and they would drift. The gates now pass a number.

## Proofs

- `tests/contract/test_evidence_claims.py::test_a_claims_session_is_the_latest_of_its_requirements`
- `tests/contract/test_evidence_claims.py::test_claims_are_cumulative_and_a_later_one_is_not_backdated`
- `tests/contract/test_evidence_claims.py::test_every_claim_belongs_to_a_session_the_release_has_reached`
- `tests/contract/test_session_three_gate_modes.py::test_the_gate_resolves_claims_for_its_own_session`
- `tests/contract/test_session_three_gate_modes.py::test_the_session_two_gate_still_names_session_two`
