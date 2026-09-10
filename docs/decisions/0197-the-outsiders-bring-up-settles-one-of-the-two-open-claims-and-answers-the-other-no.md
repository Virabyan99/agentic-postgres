# 0197 — The outsider's bring-up settles one of the two open claims, and answers the other "no"

- **Status:** accepted
- **Date:** 2026-09-10
- **Session:** 19, Run 7 (D1040, D1056)
- **Related:** **D119** (the two claims are separate and measured differently),
  **D669** (`DEP-001`'s offline half proves a path resolves, never that anybody
  walked it), **ADR 0163** (three statuses; `not_run` means the evidence is
  wrong, not the system), **docs/stage-3-decision-report.md** §5.

## Context

`fresh_host` and `documented_path` have been `not_run` since Session 12. Both
are gated on a declaration nobody supplied: `APG_FRESH_HOST_OUTPUTS` and
`APG_DX_RECORD_FILE`. The Stage 3 decision report predicted what supplying them
would find — *"An insider found five; an outsider would find more."*

In September 2026 an outsider built an application on 1.0.0, on a host that
started empty, from the documentation, and recorded twenty-five findings. The
question this ADR answers is what that run is evidence *of*.

`evidence_claims.py` keeps the two apart on purpose, and D119 is the rule:
*"the path resolves and needs no source edit" and "a host that started empty
reached a working deployment" are different guarantees, measured differently,
failing for different reasons.* Keeping them apart is what makes this decision
possible, because the answers turn out to be different.

## Decision

### `fresh_host` / `DEP-001` — supply it. The artifact exists.

`DEP-001` reads: *a fresh project deploys on an empty host from documentation
alone.* Its live half,
`test_a_project_deployed_on_an_empty_host_is_a_working_deployment`, wants a
deployed document from such a host. That document exists: a fresh Ubuntu host
went from empty to a running appliance with trusted TLS, thirty-four
migrations, encrypted backups on two providers and ten green doctor checks.

**Who drove the bring-up does not bear on this claim.** `DEP-001` asks whether
an empty host reached a working deployment, and a deployment is working or it
is not. Supplying `APG_FRESH_HOST_OUTPUTS` is therefore a mechanical step for
the operator — obtain the document, point the gate at it — and not a judgment.

Until that is done the claim stays `not_run`, which under ADR 0163 means the
evidence is missing rather than the system wrong. That remains the correct
status and nothing here changes it by assertion.

### `documented_path` / `DX-001` — do not claim it. The run answers "no".

`DX-001` reads: *a developer who did not build the primitive completes the
documented path **without source edits or undocumented commands**.*

The run required source edits. Seven tracked files, listed in the adopter's own
account and now in README's *Adding your own tables*: the ignore rules, three
migration templates, the migration manifest and its lock, the reviewed
contract, two test modules naming the published surface by hand, and a snapshot
that cannot be edited at all without a deployment.

So `DX-001` is not satisfied, and the reason has nothing to do with who walked
it. **The condition the requirement names was not met.** The findings are the
record of why it was not met, not evidence that it was.

That is worth stating plainly because the tempting reading is the opposite one:
the afternoon finally happened, so surely the claim can move. It moved — from
"nobody has tried" to "somebody tried and the path does not hold" — and the
honest place for that is this ADR and the ledger, not a green claim.

**The cause is the tenant extension point**, which is Stage 3's subject. Two of
the seven edits are already gone: Session 19 Run 4 repaired the ignore rules
(D1034) so an adopter's manifest needs no fork, and closed the README
quick-start that created a file failing the product's own gate (D1035). The
remaining five are the migration set, the reviewed contract, the two
hand-written test surfaces and the snapshot — all one design question.

### The question this does not answer

The author was an AI agent rather than a person. Whether an agent's afternoon
can ever satisfy a requirement whose text says *"a developer"* is a real
question about what these claims are for, and it is **deliberately left open**:
it does not need answering, because `DX-001`'s stated condition already fails
on its own terms. If the extension point lands in Stage 3 and a second
bring-up needs no source edits, the question becomes live and gets its own
decision then.

## Consequences

- `fresh_host` can move to `passed` on the next gate that is handed the
  document; nothing in the product changes to allow it.
- `documented_path` stays `not_run` and its ledger entry gains a reason it did
  not have: it has now been attempted, and the attempt required source edits.
  That is a stronger statement than "nobody has tried" and should not be
  softened into one.
- The count of things Stage 3's tenant extension point is blocking rises to
  three: an adopter's schema (D1040), the reviewed contract's project-neutrality
  (D1054), and this claim.
- Nothing here is hand-entered into the evidence document. A claim's verdict is
  computed from registry node ids and JUnit results, and this ADR changes
  neither — it records what the two claims mean now that somebody has walked
  the path.
