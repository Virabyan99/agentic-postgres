# 0202 — An offline claim is declared, never inferred, and the evidence document says which commit each half measured

- **Status:** accepted
- **Date:** 2026-09-11
- **Session:** 22, Run 1 (D1162, D1163)
- **Amends:** **ADR 0045** and **ADR 0089** (what a claim is) — a third kind of
  claim, about a checkout rather than a deployment, admitted by name and never
  by inference. **ADR 0163**'s three statuses are unchanged; what this adds is
  a third *mode*.
- **Related:** ADR 0014 (the gate's scope and how a session is derived), ADR
  0195 (a report may not substitute an answer for a failure to determine one),
  D696 (the requirements that belong to no claim are not retrofitted), D697
  (every registered requirement belongs to a claim), D1150 (a new requirement
  gets a claim of its own).

## Context

Session 22 builds `apg dev`: a command that stands a disposable cluster up on
a workstation from a rendered document and the release. Nothing it does
happens on the deployment. Its four claims — `dev_environment`,
`dev_isolation`, `dev_churn`, `offline_evidence` — are about a checkout, and
there is no host on which they could be measured differently.

The evidence model has no way to say that.

### What the tree does, measured at `dd9e2be`

Four refusal points, recorded by rig 22e on 2026-09-11:

1. **The writer takes two modes.** `bin/write-session-evidence.py --mode
   offline` exits **2** with argparse's usage line reading `--mode
   {host,external}`. There is no third choice to pass.
2. **`MODE_MARKERS` says the absence is deliberate.**
   `src/agentic_postgres/evidence_claims.py:69` is
   `MODE_MARKERS = {"host": "live_host", "external": "external"}`, above a
   comment that reads: *"``offline`` is absent on purpose: a claim proved only
   by tests that need no environment is a claim about a checkout, and Session
   2's are about a running deployment."*
3. **`claim_mode` refuses a claim with no marker**, with
   `ClaimError("claim {claim!r} has no live proof: every test it names runs in
   a checkout, so no deployment is being measured.")`. The mode is *derived*
   from the markers its proofs carry — the module's own docstring: *"the mode
   that can prove it is derived rather than declared"*.
4. **A contract test pins that refusal.**
   `tests/contract/test_evidence_claims.py::test_a_claim_with_no_live_proof_is_refused`
   monkeypatches a `checkout_only` claim over `CFG-001` and asserts the raise.
   The non-negotiables say a contract test changes only with an ADR. This is
   that ADR.

And a fifth thing, which is the reason the previous four are not simply
relaxed: `merge` (the `--host-input` / `--external-input` path,
`write-session-evidence.py:163`) refuses a claim that neither half recorded,
and `claims_through_session(22)` today returns **108** claims, nearly all of
them live. A session that reported itself through an offline half alone would
have to answer for those 108 or say why it does not.

### The reassuring reading, and why it is wrong

The cheap change is to make `claim_mode` return `"offline"` whenever a claim
carries no live marker. It is one line and it is wrong twice over.

**It would silently make 21 requirements reportable.** Those are the ones
`UNCLAIMED_BY_HISTORY` (in `tests/contract/test_evidence_claims.py:1031`)
records as belonging to no claim, each for a reason of its own (D696, D720–
D722). Inferring the mode from an absence would turn "nobody has decided what
this proves" into "this is proved offline" without a decision being taken.

**And it would let a live claim be reported by a half that never ran its live
proofs.** A claim whose live proofs stop being collected — a marker removed, a
module renamed, a gate variable unset — would stop having a mode, acquire
`offline`, and come out green from a checkout. That is ADR 0195's substitution
in its most expensive form: the report would answer a question it had not
determined.

## Decision

### 1. `OFFLINE_CLAIMS` is the only way a claim becomes offline

A `frozenset[str]` in `src/agentic_postgres/evidence_claims.py`, beside
`CLAIMS`. `claim_mode` gains exactly three behaviours:

- a claim **in** `OFFLINE_CLAIMS` whose proofs carry **no** live marker returns
  `"offline"`;
- a claim **in** `OFFLINE_CLAIMS` whose proofs carry **any** live marker
  **raises** — a declared claim that acquired a live proof is a claim whose
  declaration is now wrong, and the model says so rather than choosing one of
  the two answers;
- a claim **not** in `OFFLINE_CLAIMS` with no live marker raises exactly as it
  does today, with the same message. The 21 are untouched, and adding one
  stays a decision per claim.

`claims_for_mode("offline", session)` follows from that and needs no special
case.

### 2. An offline half is written from a checkout and records its commit

`--mode offline` needs no `--project-a-outputs`, reads no deployed document,
and takes its commit from `git rev-parse HEAD` into a field named
`checkout_commit` — not `source_commit`, which every existing reader
understands as *the release the deployment is running*. A half that carried a
checkout's SHA in that field would be read by those readers as a deployed
release, which is the same substitution again.

`write_half` refuses, with exit 5 and nothing written, a claim whose resolved
node ids include any test carrying a live marker. That is the same property as
§1's second bullet, checked a second time at the point where a document is
produced — because the two can only disagree if one of them is broken, and the
cheap place to find that out is before a file exists.

### 3. `merge` requires the offline half exactly when the session has one

`--offline-input` is required if and only if `claims_for_mode("offline",
session)` is non-empty, and refused otherwise. Not optional-and-ignored: an
input that may be absent is an input a run forgets, and the session whose
claims it carries is the session that cannot tell.

The merged document carries `offline_checkout_commit` **beside**
`source_commit`. `MUST_AGREE` does **not** cover it: the halves measure
different things, and a session may legitimately close with an offline half at
a commit the deployment has never run (Session 22 is exactly that). The writer
**prints** the difference when they differ. Reported, not folded — ADR 0195.

### 4. A session may close on its offline half alone

Session 22 does. `evidence/session-22-offline.json` is its record, written by
`bin/session-22-check.sh --mode offline` and by CI, and it says in its own
`mode` field which half it is. The two host claims Session 22 registers
(`plane_confirmed_count`, `agent_tenant_read`) are declared with live proofs,
are **not** in `OFFLINE_CLAIMS`, and are measured at Session 24's trip. A
merged `evidence/session-22.json` is written then, and not before.

This is the honest shape. The alternative — a merged document now, with 108
live claims answered by a checkout — is the thing every rule above exists to
prevent.

## Alternatives

**Inferring `offline` from the absence of a marker.** One line, and it makes
the 21 unclaimed requirements reportable without a decision, and it turns a
claim whose live proofs stopped being collected into a green one. Rejected —
this is the decision the ADR exists to refuse.

**A fourth status beside `passed` / `failed` / `not_run`.** ADR 0163's three
answer *how did the evidence come out*; this question is *what kind of thing
is being claimed*, which is the mode's. A fourth status would be read by every
existing consumer as a new outcome. Rejected.

**Putting the declaration in `tests/acceptance-registry.yaml`.** The registry
says what a requirement states and which node ids prove it; which claims are
about a checkout is a property of the claim, and `CLAIMS` is where claims
live. Rejected, and the two would drift.

**Writing a merged `evidence/session-22.json` now with the host claims
`not_run`.** `not_run` means *the evidence is wrong*, and for a claim nobody
has yet had a chance to measure that is a true statement wrongly framed: the
session would be recording a deficiency where there is only a schedule.
Session 22 has no host half and says so. Rejected (D1163).

**Letting `--offline-input` be optional.** Rejected: see §3.

## Consequences

- `evidence_claims.OFFLINE_CLAIMS`; `claim_mode`'s three behaviours;
  `claims_for_mode("offline", session)`; `MODE_MARKERS` keeps its two entries
  and its comment is rewritten to point here.
- `bin/write-session-evidence.py`: `--mode offline`, `--offline-input`,
  `checkout_commit`, `offline_checkout_commit`, the printed difference, and
  the `write_half` refusal of a live node id.
- `test_a_claim_with_no_live_proof_is_refused` is replaced by two stricter
  tests: an **undeclared** claim with no live proof is still refused, and a
  **declared** claim carrying a marker is refused. The property the old test
  pinned survives; what changes is that the absence of a marker is no longer
  the whole question.
- `bin/session-22-check.sh --mode offline` writes
  `evidence/session-22-offline.json`; CI's gate job writes the current
  session's offline half from its own JUnit and uploads it.
- Session 24's plan owes: a deploy `--through-session >= 22`, the Session 22
  gate in `host` and `external` modes, and a three-half merge. Recorded in
  `docs/plans/session-22-implementation-plan.md` §10 and in `CLAUDE.md` §2.
- The 21 requirements in `UNCLAIMED_BY_HISTORY` stay unclaimed. This ADR makes
  declaring one possible; it does not declare any.
