# 0045 — A claim is shaped by where it can be measured

Status: accepted
Date: 2026-08-10
Session: 4, Run 10
Amends: [0025](0025-evidence-names-the-claim-not-the-suite.md), [0039](0039-a-claim-belongs-to-the-session-that-introduced-it.md)
Affects: DBX-001, DBX-003, DBX-005, SEC-DBX-001, DX-DB-001, DX-DB-002, DEP-ISO-004

## Context

ADR 0025 replaced suite-name evidence keys with **claims**, and gave them three
rules: absence is not success, a skip is not a pass, and **each claim is measured
in exactly one environment**. ADR 0039 made a claim's session derived from its
requirements — the latest of them — so that a claim which gains a later
requirement becomes that session's claim without anyone remembering to say so.

Session 4's plan drafted four claims in §7. Session 3 ran with one environment;
Session 4 restores the external gate (D82), and the draft is the first claim
table written against three modes since Session 2. Two of its four entries turn
out to be unimplementable as written, and both discoveries are about the same
thing: **a claim is not free to be shaped by the sentence it states. It is shaped
by where its proofs can run and by whose evidence has to carry it.**

Neither was visible by reading. The first is refused by `claim_mode` at import
time; the second passes every test and takes a claim away from a *previous*
session's evidence.

## Decision

**1. `direct_transport` splits, because its drafted proofs span two
environments.**

The draft is `DBX-001, DBX-003, DBX-005, SEC-DBX-001`. The first two are proved
on the host, by running Prisma Migrate and `psql` against the direct endpoint.
The last two are proved from off-host, by *failing* to reach the same endpoint.
One claim, two environments — and `claim_mode` refuses it, correctly: neither
half of the evidence could report a verdict on it, and a merged verdict computed
from half the proofs would say `passed`.

So the guarantee is split where the measurement is:

| Claim | Requirements | Mode |
|---|---|---|
| `direct_transport` | `DBX-001`, `DBX-003` | host |
| `transport_boundary` | `DBX-005`, `SEC-DBX-001` | external |

`transport_boundary` is the external claim `public_boundary` could not be. That
one was written over `SEC-NET-001` and removed because its proofs include an IPv6
scan and no network available to run the external gate from has IPv6 transit — a
claim that could only ever come out `failed`, for want of a vantage point rather
than for want of a boundary. `SEC-DBX-001` and `DBX-005` scan IPv4 only. The
external mode therefore carries a claim for the first time.

**2. `DEP-ISO-004` gets its own claim rather than joining `database_isolation`.**

The plan says `database_isolation` *gains* `DEP-ISO-004`. Follow the mechanism
through: `claim_session` is the maximum of a claim's requirements' sessions, so
gaining a Session 4 requirement moves the whole claim to Session 4, and
`claims_through_session(3)` stops returning it. **Session 3's gate would quietly
stop recording a claim it has recorded since Session 3 shipped**, and the jq
expression `docs/session-03-operator-guide.md` documents —
`.tests.database_isolation=="passed"` — would fail against freshly written
Session 3 evidence while the product's behaviour was unchanged.

Cumulative was meant to mean that a later session keeps proving an earlier one's
guarantees. It was not meant to mean that a later requirement withdraws one from
an earlier session's evidence. So:

| Claim | Requirements | Session |
|---|---|---|
| `database_isolation` | `DEP-ISO-003`, `DBX-PG-003` | 3, unchanged |
| `transport_isolation` | `DEP-ISO-004` | 4 |

Both are proved on the host, both appear in Session 4's evidence, and Session 3's
evidence still says what it said.

**3. Two contract tests in `tests/contract/test_evidence_claims.py` change.**

`test_a_mode_that_carries_a_claim_has_a_static_proof_to_run` asserts that a mode
carrying a claim resolves at least one proof carrying *no* environment marker.
That is true of Sessions 2 and 3 by accident — each of their claims happens to
include a contract test — and it is not the property that matters.
`transport_boundary` and `connection_tooling` are proved entirely by tests marked
`external`, every one of which the mode's own `-m external` selector collects.
Nothing is missing from the artifact; the assertion would have refused a correct
claim table. **It is replaced by the coverage rule it was reaching for**: every
proof of a mode's claims is collected either by that mode's marker or by the
explicit node-ID list, and a proof in neither is one no selector runs. The half
that was measuring something — a mode with no claim must resolve no proofs — is
kept as a test of its own.

`test_a_session_with_one_environment_merges_a_single_half` is pinned to session 3
rather than to `CURRENT_SESSION`. It is a test *about* a session with one
environment; Session 3 is the one that has one. Left at `CURRENT_SESSION` it
began, the moment Session 4 acquired an external claim, asserting that a
two-environment session merges from a single half — which is the exact refusal
the test immediately after it exists to prove.

## Consequences

**Session 4's evidence has two halves and cannot be written from one.** The
writer already refuses a single half for a session with an external claim; that
guard, dormant since Session 2, is live again. An operator who runs only
`--mode host` gets a host half and no session document, and is told which claims
are measured from outside.

**A claim table is now checked for coverage rather than for a habit.** The
replaced assertion would have gone red on a correct table and green on one whose
proofs no selector collected, provided one contract test was in the set. The new
one goes red on exactly the case that produces a permanent `not_run`.

**ADR 0039's derivation is unchanged and its edge is documented.** A claim's
session is still the maximum of its requirements'. What this ADR adds is the
consequence: adding a later requirement to an existing claim *moves* it, so the
decision to extend a claim is a decision about which sessions' evidence records
it. Extending is still right when the guarantee genuinely grew; it is wrong when
a new requirement merely neighbours an old one.

**Session 4 records eleven claims**, cumulatively: Session 2's two, Session 3's
four, and Session 4's five.

## Alternatives considered

**Keep `direct_transport` whole and relax the one-environment rule.** Rejected
outright. The rule is what stops a verdict being computed from the proofs that
happened to be reachable, and this is the first session with two environments in
which it would have bitten — which is evidence that it works, not that it is in
the way.

**Let `database_isolation` move to Session 4 and update the Session 3 operator
guide.** Honest, and cheaper by one claim name. Rejected because it makes an
already-published session's evidence non-reproducible: the Session 3 gate is
still runnable and still expected to produce the document it produced, and a
re-run that silently dropped a claim would be the strongest possible example of
this project's own defect pattern — a green result whose meaning changed
underneath it.

**Name the external claim `public_boundary` and reuse the removed name.**
Rejected: `public_boundary` was refused over `SEC-NET-001`, which is still
unproved from any available network. Reusing the name would make the two
indistinguishable in evidence and would suggest the IPv6 gap had been closed.
