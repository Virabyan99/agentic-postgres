# 0217 — Stage 4's boundary: nothing built in 31–35 may require a hosted trust model to be safe

- **Status:** Accepted
- **Date:** 2026-09-18
- **Session:** 30, Run 2 (D1517, D1527)
- **Affects:** no requirement directly. It binds the design of every plane
  Sessions 31–35 build, and it is the ADR a reviewer cites when refusing one.
- **Related:** ADR 0216 (no public endpoint — the sibling decision of the same
  day), ADR 0135 (the audit as caller), ADR 0141/0178 (a denial is audited and
  names its boundary), ADR 0181/0182/0183 (idempotency, dry-run, a profile only
  narrows), ADR 0195 (a report may not substitute an answer for not knowing),
  ADR 0002 (identities derived once).

## Context

ADR 0216 defers hosting. That decision is only safe if the work done in the
meantime does not quietly *assume* hosting — and Stage 4 is unusually exposed
to exactly that, because **three of its six sessions build a second
principal**: a worker (32), an approver (33), a connector (34).

The stage plan states the exposure in one line: *"a second principal is the
shape most likely to become an authority by accident."* The failure is not
that someone writes a bad rule. It is that a worker, a connector or an
approver is built as the thing that *acts on behalf of* an identity, and a
principal that acts on behalf of an identity has, by construction, to be
trusted more than that identity — which is a hosted trust model arriving
without anyone deciding to adopt one.

### Why this cannot be left to the invariant table

Stage 4's §8 table already names the individual controls: a step is a tool
call under the same scope check; a connector identity only narrows; an inbound
request is signature-checked before any database is touched. Each is
enforceable. But each is also a rule about a *mechanism*, and the failure mode
here is architectural: a design can satisfy every row and still require, to be
safe, that some component be trusted in a way the appliance has no way to
establish. That is what this ADR forbids, and it has to be stated as a
property of the design rather than as another row.

`docs/threat-model.md` carries 14 `THR-*` rows, every one of them written for
**an appliance with one operator**. Its own header says the analysis is
hand-authored and that only referential integrity is machine-checked. Nothing
in it would go red if a Stage 4 plane introduced a principal whose safety
rested on a registry, an org boundary or an identity provider that does not
exist.

## Decision

**Nothing built in Sessions 31–35 may require a hosted trust model in order to
be safe.** Operationally, four commitments:

1. **A workflow, a connector and a worker hold nothing an agent identity does
   not hold.** This is Stage 4's sibling invariant to *a human cannot run SQL
   through a product surface* and *the DX layer holds nothing the human does
   not hold*. A second principal is a **scope set the existing verifier already
   checks** — never a new authority, never a new verifier, never a credential
   the agent plane could not have been given directly.

2. **Every `THR-*` row a session adds is written before that session's code**,
   not after it. A threat row written afterwards describes what was built; one
   written first constrains it. Session 31–35 plans each name their rows in §8.

3. **`docs/threat-model.md` stays the appliance's document.** No session adds a
   sentence about external users, organisations, tenants-as-customers or a
   hosted console. If a design needs such a sentence to be safe, the design is
   out of Stage 4's scope and the session stops (ADR 0216's stop condition).

4. **The approver is not the requester.** Where a plane introduces approval
   (33), the identity that grants an approval is never the identity that
   requested the action, and that is checked in the database rather than in the
   caller.

## Consequences

**Makes easy:** a reviewer can refuse a Stage 4 design in one question —
*what would this have to trust that the appliance cannot establish?* — instead
of arguing about mechanisms. It also makes each session's threat rows a
design input rather than paperwork.

**Makes hard:** genuinely useful hosted-shaped features are unavailable. A
connector cannot hold a broker credential the agent plane does not hold; a
worker cannot be given a standing role that outlives the step it runs; an
approval cannot be delegated to a service account. Each of these would be the
natural design if hosting were assumed, and each is refused here.

**What this forecloses, named so that a session recognises it on sight:**

- **A control plane as a client.** Any component that calls the product's own
  surface holding more than a project identity holds.
- **An approval granted by the requester.** Including the degenerate case: a
  single identity that both requests and approves because it is *the* agent.
- **A connector with a scope its profile did not narrow to.** ADR 0183 says a
  profile only narrows; a connector that widens is the same violation wearing a
  different name.
- **A worker whose credential is not a per-consumer generation.** A shared
  worker credential is a second authority by another route.

**Enforced by:** the per-session invariant tables (stage plan §8), the existing
`FORBIDDEN_VARIABLES` check on the runtime's environment, ADR 0183's profile
tests, and `test_acceptance_registry`'s referential integrity over the threat
model's two ID columns. **No test enforces the architectural property itself**
— that is the honest statement, and it is why this is an ADR a human cites in
review rather than a check. Naming that gap is preferable to implying a
control that does not exist (ADR 0195's habit applied to this document).

## Alternatives considered

**Add the rows to `docs/threat-model.md` and skip the ADR.** Rejected: the
threat model is a table of mechanisms against attacker capabilities, and the
property here is about what a design may presuppose. A row saying *"the design
must not assume hosting"* has no attacker capability and no control, and would
be the one unparseable row in a parsed table.

**Defer the boundary until a session actually needs a second principal
(Session 32).** Rejected because the first session to need it is the session
least able to judge it: it will be mid-build, with a working design, and the
cost of the boundary will be visible while the benefit is not. Deciding it
now, while nothing is at stake, is the only time it is cheap.

**State it as "no new authority" alone.** Too narrow. A design can add no new
authority and still be unsafe without a hosted trust model — for example a
worker that is safe only because a registry would have revoked it. The
commitment has to be about what safety *rests on*, not only about what is
created.

**Write it into `CLAUDE.md` instead.** `CLAUDE.md` is the handoff and is not in
git; it is rewritten every session and nothing backs it up. A binding decision
belongs where decisions live.
