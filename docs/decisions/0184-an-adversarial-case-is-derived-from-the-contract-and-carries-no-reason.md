# 0184 — An adversarial case is derived from the contract and carries no reason

- **Status:** accepted
- **Date:** 2026-09-04
- **Session:** 16, Run 9 (`EVAL-HARNESS-001`, D868, D934–D939)
- **Related:** **D868** (the harness's cases are derived from the capability
  contract rather than from the runtime), **ADR 0127** (a caller's `limit`
  above the ceiling is clamped, not refused), **ADR 0177** (a capability
  declares a version), **ADR 0178** (the denial taxonomy is derived from the
  refusal sites), **ADR 0181** (the two reserved write parameters), ADR 0065/
  0066 (a proof that reaches an end state by a route the product does not take),
  ADR 0089/0045 (what a claim is), CLAUDE.md §7's sixth question.

## Context

The stage plan asks for *"an evaluation harness with positive and adversarial
cases per capability, failing CI when a capability changes without them"*, and
names its own hardest question: **an adversarial case whose expected denial was
written from the implementation is a description of the implementation.** That
is §7's sixth question — a proof and its subject agreeing is not evidence when
one author wrote both — and it was invisible to a green offline suite three
times (D673, D680/D682, D687).

Measured before anything was built:

- The word `adversarial` appeared nowhere in the tree except the stage plan.
- The compiled contract freezes, per tool, exactly the fields a request can
  violate: `required_scopes`, `resources`, `columns`, `filters` (column and
  operators), `order_by`, `max_rows`, `arguments`, `supports_dry_run`,
  `requires_approval`, `max_affected_rows`, `max_response_bytes` — and the
  runtime adds two reserved write parameters the contract does not carry.
- **A `limit` above `max_rows` is not refused.** `build_request` clamps it to
  the ceiling (ADR 0127: *"asking for too many is a reasonable thing for a
  client to do and a bounded answer is the right reply"*). A harness with two
  verdicts would have derived a `refused` case for it and reported the runtime
  wrong for doing what the ADR decided (D937).
- **A listing held on fewer scopes is filtered, not refused** (D421).
- `capabilities.example.yaml` declares every capability at `version: 1.0.0`,
  and **nothing consumed the version with any consequence**: it reaches the lock
  and the audit row and constrains nothing.

## Decision

**A case is derived from the approved contract, one adversarial case per frozen
field, and it carries an expectation — `permitted`, `refused` or `bounded` —
and never a denial reason. Hand-written cases are counted separately and are
bound to the capability version they were written against.**

### Derived, per field, mechanically

`evaluation_harness.derive_cases(contract)` is pure over the contract. For each
capability it produces one positive case (a request the contract permits) and,
for every field the contract freezes for that capability's kind, one
adversarial case that violates exactly that field: a column the allowlist does
not name, a column the caller may read and may not filter on, an operator the
closed enum has and the column does not permit, an ordering index past the
frozen list, an argument the function does not take and one it requires, a
malformed reserved parameter, a dry run against a capability that declares
none, and — on the response side — more rows than the ceiling, more bytes than
the budget. A contract that gains a filter gains a case; one that loses one
loses one; `test_the_derivation_follows_the_contract` is the control against
this becoming a hand-kept list.

### Three expectations, not two

`bounded` is the third, and it is the decision this ADR exists for. The
contract does two different things with a value it does not permit: it refuses
some and bounds others, and both are correct. A `limit` above `max_rows` is
clamped; a listing held on `meta:read` alone is empty. The harness records that
as *permitted, and the bound was applied* — the evaluation reads the built
request's `limit` and the listing's members — rather than as a refusal that did
not happen.

### No reason is asserted; the reason is observed

A derived case says `refused` and nothing more. The evaluation catches the
refusal, records the caller-facing token and the audit-side denial reason, and
writes both into the outcome. What is then asserted is **structural**, not
implementation-derived: the scope check runs first, so a case that withholds a
scope must be refused by it and a case that holds every scope must be refused
by something else — otherwise the case never reached the field it targets.
That is the stop condition the session plan fixed (*"every one denied by the
same first check"*), made into an assertion.

### Written cases are bound to a version

`tests/evaluation-cases.yaml` carries hand-authored cases — the ones a person
writes because they know something the contract's shape does not say — and
every entry carries the `capability_version` it was written against.
`load_written_cases` refuses an entry whose version the contract no longer
declares. So a capability whose version moves without its cases moving fails
the harness test, the offline gate (`render-evaluation-report --check` exits
5) and CI, which is the enforcement the stage plan asked for and the first
consequence `version` has ever had.

### The report carries what was asked, never what was answered

`docs/evaluation-report.md` is generated: counts per capability, derived and
written separately, every case's field and expectation, and the contract's
digest. It carries no outcome, because an outcome is what the evaluation
observes on the day and a document asserting one is a proof result committed
as prose. The digest is the same number the lock records as `canonical_sha256`
and the deployed document publishes as `capability_contract_sha256`, which is
what makes `EVAL-HARNESS-001`'s live half one comparison.

### The evaluation lives with the proofs, not in `bin/`

Running a case means calling the runtime's own request builders with a fake
upstream. The service package is importable in the contract suite and nowhere
else in a checkout, so the evaluation is `tests/contract/test_evaluation_harness.py`,
one parametrized node per case. `bin/render-evaluation-report.py` imports no
service module; it derives, counts and refuses.

## Alternatives rejected

**Assert the expected denial reason per derived case.** It would make the
harness precise and it is exactly the thing D868 forbids: the reason would be
copied from the refusal site, and a refusal site that moved to a wrong reason
would move the case with it.

**Two expectations.** Measured wrong twice before the first case ran: the row
ceiling clamps and the listing filters. A harness that reported those as
defects would be a harness nobody trusts the third time it is right.

**Sum derived and written cases into one count.** A capability with eleven
derived cases and no written one would look reviewed. The two answer
different questions — *does the runtime obey the contract's shape* and *did a
person think about this capability* — and are reported apart.

**A `bin/evaluate.py` that imports the runtime.** A root-level script importing
a service package by path is the fragile half of the D486 trade, and it would
duplicate what pytest already does with the same import.

**Derive cases from the manifest rather than the compiled contract.** The
contract is what the lock carries and what the runtime obeys; the manifest is
what a person wrote. A case derived from the manifest would be a case about
the compiler.

## Consequences

- `EVAL` joins the registered requirement-id prefixes.
- `RESERVED_WRITE_PARAMETERS` now has a third copy, in `evaluation_harness`,
  and the test between the copies covers three.
- Adding a capability without cases fails `render-evaluation-report --check`,
  the harness test, the offline gate and CI. Changing a capability's version
  without touching its written cases fails the same four.
- The report is indexed in `docs/README.md` as generated and is checked by the
  Session 16 gate's offline mode.
