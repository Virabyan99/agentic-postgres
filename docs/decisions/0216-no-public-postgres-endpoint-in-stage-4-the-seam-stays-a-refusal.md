# 0216 — No public Postgres endpoint in Stage 4; the seam stays a refusal

- **Status:** Accepted
- **Date:** 2026-09-18
- **Session:** 30, Run 2 (D1518)
- **Affects:** no requirement, no schema, no migration, no deployed field. This
  ADR forecloses; it builds nothing. What it binds is every session from 31 to
  35.
- **Related:** ADR 0042 (no publication), ADR 0043 (the SSH forward), ADR 0044
  (the broker on the host) — the three a hosted product would have to supersede
  **together**; ADR 0001 (the appliance); ADR 0185 (an operator's read is not a
  catalog); D1084, D1518.

## Context

D1084 named this Stage 4's first ADR. The stage-4 decision report put the
question plainly and then said the thing that makes it an ADR rather than a
measurement: the answer is **not a consequence of any number**. No benchmark,
no capacity reading and no adopter count decides it. It is a product decision,
and the operator took it on 2026-09-18: **appliance first, hosting deferred.**

### What the tree already is

The refusal is not a policy laid over a capability. The capability is absent,
and four independent places say so — read at `5444c71`:

- `runtime_override.publication()` (`:504-518`) **raises**. Its docstring
  records why it is kept rather than deleted: *"The signature is what a future
  reader reaches for when they want to publish a database port, and finding it
  raise with the reason is worth more than finding nothing and writing it
  again."*
- `compose.yaml` contains **zero** `ports:` keys. Not one commented out; none.
- `bin/connect.sh:67` binds `127.0.0.1` by constant — `readonly
  LOCAL_BIND="127.0.0.1"` — and `:90` says *"The local bind is 127.0.0.1 and
  nothing else."*
- `docs/product-contract.md` §5 lists *a hosted web console or SaaS offering*
  and *a shared, multi-tenant control plane* under **Non-goals**, with the
  sentence *"These are not deferred. They are outside the product."*

And two tests hold the line rather than describe it.
`test_port_allocator.py:363` `test_no_publication_can_be_built_at_all` is
parametrised over `127.0.0.53`, `::1`, `0.0.0.0`, the host's own public
address, `127.0.0.1:443` and the empty string, and expects `RuntimeError`
matching *nothing is published* for every one. Its docstring is the reason this
ADR can be short: *"The first three rows are what the superseded design called
correct: a loopback address and an unprivileged port. They are refused here,
which is what makes this stricter than the tests it replaces rather than a
relaxation wearing an ADR number."* `test_port_allocator.py:379`
`test_the_override_carries_no_ports_entry_for_any_service` is the second, and
`test_deploy_command.py:370` asserts `publications=` never reaches the runtime
render.

### The constraint that made the obvious option wrong

The obvious option is to add a loopback publication — *"it is only
127.0.0.1"* — and it is wrong for a reason the tree already measured: on an
`internal: true` network Docker installs no DNAT rule and no listener, so the
entry **does nothing today and does something the day the network stops being
internal**. A control that is inert until a configuration change elsewhere
activates it is not a control. That is why the refusal refuses loopback too.

## Decision

**Through Session 35, nothing in this product gains a network path to Postgres
from off the host.** Concretely, no session from 31 to 35 may add:

- a `ports:` entry to any service in `compose.yaml` or any override, for any
  address including loopback;
- a published Prometheus, collector or Studio route, or any Traefik router for
  a transport that is not already routed;
- a bind to any address other than `127.0.0.1` in a command that forwards;
- a database transport reachable off-host by any means, including a tunnel the
  product itself manages.

`publication()` stays a refusal with its reason. **Wanting one of these is a
stop condition** (stage plan §9), not a design discussion to have mid-session:
the session stops and the question returns to the operator.

## Consequences

**Makes easy:** every Stage 4 plane — the workflow substrate, the connectors,
the outbox, the webhook connector — is designed against a single trust
boundary that already exists, and none of them needs a threat model for
external callers. A reviewer checking a Stage 4 diff for compliance greps for
`ports:` and for a non-loopback bind, and that is the whole check.

**Makes hard:** any adopter who wants a psql connection from their laptop
keeps paying ADR 0043's SSH forward. That cost is accepted and is not revisited
before Stage 5.

**Forecloses:** a hosted Studio, remote contexts, organisations, login, support
grants, and a public endpoint — as a *set*. They are one decision, not six,
because each of them alone is refused by the same three ADRs.

**The preconditions a Stage 5 reading must pay**, listed here so that the
reading is a checklist rather than an argument:

1. The signing-key rotation **performed**, not merely rehearsed (D860). Session
   30 Run 8 pays this one.
2. `docs/product-contract.md` §5's tenancy non-goal changed by an ADR that
   supersedes it explicitly.
3. An authoritative registry replacing ADR 0185's *an operator's read is not a
   catalog* — a hosted plane needs a catalog that is authoritative, and today
   nothing is.
4. A threat model for external users. `docs/threat-model.md` is written for an
   appliance with one operator; ADR 0217 keeps it that way for Stage 4.
5. A single ADR superseding **0042, 0043 and 0044 together**. Superseding one
   of the three leaves the other two contradicting it.

**Enforced by:** `tests/contract/test_port_allocator.py:363` and `:379`;
`tests/contract/test_deploy_command.py:370`. No new test is added — the
existing three already fail on every move this ADR forbids, which is the
evidence that the refusal is structural rather than declared.

## Alternatives considered

**Publish on loopback only, for `psql` convenience.** Refused above: inert on
an internal network, live the day it is not. `test_port_allocator.py:363`
refuses loopback by name for exactly this reason, and weakening it to admit
loopback would be the *"relaxation wearing an ADR number"* its own docstring
warns about.

**Decide hosting now, on the evidence available.** The decision report's
finding was that no number decides it. Taking it now would mean taking it on
taste while pretending it was derived — and the five preconditions above are
real work that nobody has done, so the answer today would be *no* regardless.
Deferring states that plainly and names the price.

**Leave it undecided and judge each session as it comes.** This is what Stage
3 effectively did, and it cost: the question resurfaced in Sessions 26, 28 and
29 without anything having changed. An ADR ends the recurrence. A decision
that has to be retaken every session is not a decision.

**Delete `publication()` rather than keep it raising.** Its own docstring is
the counter-argument and it is persuasive: a future reader who wants to publish
a port will find the function, read why it raises, and stop — where finding
nothing they would write it again.
