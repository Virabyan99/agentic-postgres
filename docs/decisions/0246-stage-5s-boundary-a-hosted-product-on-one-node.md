# 0246 — Stage 5's boundary: a hosted product on one node; ADRs 0042, 0043, 0044, 0216 and 0217 superseded together

- **Status:** Accepted
- **Date:** 2026-10-03
- **Session:** 36, Run 1 (D1949, D1978, D1999, D2004)
- **Affects:** no requirement, no schema, no migration, no deployed field, no
  running process. `docs/product-contract.md` §2 and §5 (amended),
  `docs/threat-model.md` (the hosted threats and the Scope sentence), and the
  index rows and status lines of ADRs 0042, 0043, 0044, 0216 and 0217.
- **Related:** ADR 0001 (the appliance), ADR 0185 (an operator's read is not a
  catalog), ADR 0216 and 0217 (the Stage 4 boundary this replaces), ADR 0247
  (the Reality Ledger), D1946 (the operator's hosted decision of 2026-10-03),
  `docs/plans/stage-5-plan.md` §2.1.

## Context

Stage 4 worked inside a boundary that lapsed by its own wording at Session 35's
close. ADR 0216 said *"Through Session 35, nothing in this product gains a
network path to Postgres from off the host"*; ADR 0217 said *"Nothing built in
Sessions 31–35 may require a hosted trust model to be safe"*. Both name their
own end. ADRs 0042, 0043 and 0044 (the loopback port allocation, the SSH
forward through the host broker, and *"there is no publication"*) still read
as the product's whole answer to the question *who reaches the database, and
how*, and `docs/product-contract.md` §5 still lists a hosted console, a shared
control plane, scale-to-zero, branching and cross-project reporting as
*"not deferred … outside the product."*

On 2026-10-03 the operator decided that Stage 5 is a hosted product: the
appliance offered to people who do not operate it, on one node, invite-only
(D1946, D1951). ADR 0216's own list of preconditions for that reading
(`:95-108`) asks for exactly two documents: an ADR that changes the product
contract's non-goals explicitly, and **one ADR superseding 0042, 0043 and 0044
together**, because superseding one leaves the other two contradicting it. A
boundary that lapses silently is the worst kind: every later session would
read 0216 as standing, or read nothing as forbidding anything.

The constraint that makes the obvious option wrong: the obvious option is to
let each building session supersede the ADR in its way — Session 39 the port,
Session 37 the control plane, Session 40 the branch. That is how a boundary
becomes a sequence of exceptions nobody reads together. The boundary has to be
stated once, before any of it is built, and each later session builds inside
it.

## Decision

**1. ADRs 0042, 0043, 0044, 0216 and 0217 are superseded together**, as the
product's boundary. Their status lines and index rows say *Superseded by 0246*.
What they *describe* is not removed: the port allocation keyed by the volume's
identity (0042), the broker reached through a trampoline (0043) and the
refusal in `runtime_override.publication()` (0044) all keep running exactly as
they run today, and their proofs keep passing. What lapses is their standing
as the answer — the sentence *"there is no publication, ever"* — which this ADR
replaces with item 2.

**2. The ports the host may publish: 80, 443, and one Postgres port whose shape
Session 39 measures and records in its own ADR. Until that ADR, none.**
`publication()` keeps raising, `compose.yaml` keeps zero `ports:` keys, and the
edge keeps publishing 80 and 443 only. `test_port_allocator.py`'s
`test_no_publication_can_be_built_at_all` and
`test_the_override_carries_no_ports_entry_for_any_service` and
`test_deploy_command.py`'s publication assertion stay as they are; Session 39
changes them under its own ADR, with the measurement beside it. No other port
is admitted by this ADR, and a session that wants one stops (the stage plan's
§9).

**3. The product contract is amended in §2 and §5 together** (D2004), because
two lists stating one boundary must move together or one becomes a stale
promise:

- **Removed from the non-goals:** a hosted control plane and a hosted web
  console. Both are Stage 5's to build (Sessions 37 and 42).
- **Narrowed:** scale-to-zero becomes *sleep that stops a project's containers,
  triggered by its owner or by idleness* (autoscaling and compute/storage
  separation stay out); branching becomes *a branch restored from a backup at a
  recovery point* (copy-on-write forks stay out); cross-project reporting
  becomes *the control plane counts its own records and reads each project's
  readings; it never reads a project's rows*.
- **Kept whole:** autoscaling and compute/storage separation; automatic
  failover and multi-region replication; arbitrary SQL execution by an agent,
  under any authentication; general-purpose ORM support beyond the endpoint
  contract.

The generated blocks of the product contract are not touched.

**4. The boundary sentences.** Stage 4's sibling invariants are kept and one is
added one plane up:

- the DX layer holds nothing the human does not hold;
- a workflow, a connector and a worker hold nothing an agent identity does not
  hold (ADR 0217's first commitment, carried forward unchanged);
- **the control plane holds nothing that opens a project's data plane or admin
  plane, and the reconciler runs only a closed set of typed operations** —
  never a string, never a shell, never SQL it was handed;
- **a product surface runs no SQL** — the console, Studio, `/api/v1`, MCP, a
  workflow and a connector. A customer's own client, with the customer's own
  database credential, may; an agent never does. This is CLAUDE.md §6's
  *"A human cannot run SQL through a product surface"* restated with its scope
  named, not loosened: the sentence was always about product surfaces, and a
  customer's `psql` is not one.
- the approver is not the requester (ADR 0217's fourth commitment, carried
  forward unchanged).

**5. External users enter the threat model.** ADR 0217's third commitment (*"no
session adds a sentence about external users, organisations, tenants-as-
customers or a hosted console"*) lapses with it. `docs/threat-model.md` gains
the hosted threats as a numbered list, written before their controls exist
(D1999): a `THR-*` table row needs a registered requirement, and a requirement
for a control nobody has built would be a control that looks measured. Each
item moves into the table in the run that registers its requirement. Denial of
service enters scope for the creation paths and the public Postgres port as
admission and rate limits — **still not as an availability SLA**.

**6. What does NOT change in Session 36: nothing at runtime.** This ADR changes
what is *allowed*, not what *runs*. After it: no new port, route, router,
container, role, network, secret or scope; no customer exists; the host serves
exactly what it served at 1.13.0. CLAUDE.md §6's *"There is no public Postgres
endpoint"* stays true until Session 39 and is rewritten by that session.

## Alternatives rejected

**Supersede piecemeal, per session.** Session 37 would supersede 0217 for the
control plane, Session 39 the three port ADRs for the endpoint, Session 40 the
branching non-goal. Rejected: ADR 0216 itself says superseding one of the
three leaves the other two contradicting it, and five partial supersessions
spread over six sessions is a boundary no reviewer can read in one place. The
point of the boundary is that it is decided before the first thing it governs
is built.

**Keep ADR 0216 and write exceptions to it.** *"No public endpoint, except the
gateway's; no hosted trust model, except the control plane's."* Rejected:
an ADR whose every consequence has an exception is a list of exceptions with a
title, and the title would be the one sentence a reader remembers — the wrong
one.

**Write the hosted threats as table rows now.** Rejected (D1999): every row in
the table must name a registered requirement
(`test_every_threat_row_names_at_least_one_requirement`), and the hosted
controls have none until Sessions 37–42 register them. A row with an invented
requirement is a control that looks measured; the list is the honest form.

## Consequences

**Makes easy:** each Stage 5 session builds inside a boundary already decided;
a reviewer refusing a design cites one ADR and one of its sentences. The ports
are in one place, so *"may this session publish a port?"* has one answer.

**Makes hard:** every later session must check its design against item 4's
sentences, and the reconciler (Session 38) and the gateway (Session 39) each
owe a measurement before their ADR. The superseded ADRs stay readable and stay
the description of what runs, which means a reader must read this ADR to learn
that they no longer bound the product.

**Enforced by:** nothing new at runtime — the existing refusals
(`publication()`, zero `ports:` keys, the two port-allocator tests) are
unchanged and keep failing on every move item 2 forbids until Session 39's ADR
changes them. The threat list's movement into the table is enforced by
`test_acceptance_registry`'s referential integrity as each row arrives. **No
test enforces item 4's architectural sentences themselves**; that is ADR
0217's honest statement, carried forward.
