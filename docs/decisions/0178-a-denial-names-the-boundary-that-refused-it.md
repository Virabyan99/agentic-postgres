# 0178 — A denial names the boundary that refused it, and `credential` is not one of them

- **Status:** accepted
- **Date:** 2026-09-03
- **Session:** 16, Run 3 (`AGT-DENIAL-001`, `AGT-CAPVER-001`, `AGT-RISK-001`, D886–D888)
- **Related:** **D433** (three measured 401s are a bad signature, a stale identity
  and a missing privilege — indistinguishable by status, so relaying one is a
  guess dressed as a diagnosis), ADR 0130 (silence by default; one explicit type
  for what a caller may be told), ADR 0139 (a write refusal is *translated* from
  the product's own `PT` errcode, never a relayed status), ADR 0135 (the audit
  record is written by SECURITY DEFINER functions as the caller), **D489** (a row
  written inside the transaction it describes is rolled back with it), ADR 0177
  (the capability's version and risk, parsed and reaching the runtime), ADR 0002.

## Context

Run 3's brief says the taxonomy is *"derived from the refusals that already
exist — scope, allowlist, budget, drift, credential — rather than invented"*,
and that a contract test asserting every refusal path maps to exactly one member
is the run's real output.

The derivation was done. **Four of the five named members are real, the fifth is
not, and three the brief did not name are.**

### The plane already has two vocabularies, and they answer different questions

`CALLER_FACING_TOKENS` is what an agent may be told: six tokens, deliberately
few. `STRUCTURAL_REFUSAL` is the single string for everything a caller is told
*nothing* about, and it is one string on purpose — D433's rule, so that a
refusal cannot become a diagnosis by being named.

A denial reason is neither. It is written to `app_private.agent_audit`, read by
an operator, and it must distinguish the cases a caller is deliberately not told
apart — otherwise the console shows `refused` for a boundary event, a deployment
fault and an unreachable upstream alike.

### What the refusal sites actually are

Enumerated across `mcp_tools.py`, `mcp_query.py`, `mcp_upstream.py`:

| Boundary | Sites | Told to the caller |
|---|---|---|
| a required scope is not held | `mcp_tools` 179, 212 | `scope_not_held` |
| the lock does not permit this resource, column, operator or ordering | `mcp_tools` 170; most of `mcp_query` | `resource_unknown` / `input_not_permitted` |
| the caller's argument shape is wrong | `mcp_tools` 455–463; `mcp_query`'s limit and value checks | `input_not_permitted` |
| a budget is exceeded | `mcp_tools` 344 | `budget_exceeded` |
| the served surface and the lock disagree | `mcp_tools` 208, 325, 367, 384, 443 | **nothing** |
| the upstream refused | `mcp_tools` 305, 378, 437 | **nothing** |
| the write's audit record could not be written | `mcp_tools` 567 | **nothing** |
| the product's own write refusal | `PT404`, `PT409`, `PT422` | `row_not_found`, `write_conflict`, `input_not_permitted` |

### `credential` has no site, and adding it would break D433

**The MCP runtime holds no credential of any kind** — no signing key, no
database credential — and that is enforced, not merely true. So a
credential-failure member could not describe the runtime's own.

If it meant the *caller's*, the measurement in `mcp_upstream.py`'s own header is
the refusal: a 401 from upstream is *"no Authorization"*, *"an unknown agent"* or
*"a forged signature"*, and a 403 is a human token — four states behind two
statuses. **Classifying one as `credential` is exactly the guess D433 forbids**,
and it would be worse in an audit row than in a response, because a durable
record is read later by somebody who cannot re-derive it.

## Decision

**Eight members, each naming the boundary that refused, and none naming a
cause the plane cannot distinguish.**

```
scope_not_held      a required scope was absent from the caller's token
not_in_allowlist    the lock does not permit this resource, column, operator or ordering
input_malformed     the caller's argument shape is wrong, before any allowlist question
budget_exceeded     a bound was reached: rows, bytes, elapsed time, concurrency
contract_drift      the served surface and the deployed lock disagree
upstream_refused    the upstream refused, and this plane does not say why (D433)
audit_unavailable   a write failed closed because its record could not be written
write_rejected      the product's own PT4xx refusal, translated (ADR 0139)
```

**`not_in_allowlist` and `input_malformed` are separate although the caller sees
one token for both.** To an operator they are opposite events: the first is an
agent reaching for something the deployment froze — worth looking at — and the
second is a client bug. Collapsing them would put the interesting one inside the
noisy one, which is the failure a taxonomy exists to prevent.

**`upstream_refused` is a member that deliberately explains nothing**, and it is
the honest form of the brief's `credential`. It says *this plane asked and was
told no*, which is all it knows.

### The vocabulary lives in the catalog, and the runtime is checked against it

Migration 0027 declares `app_private.agent_denial_reason` as an enum, and
`mcp_errors.DENIAL_REASONS` mirrors it. **A contract test compares the two
against the migration template**, exactly as `UPSTREAM_WRITE_REFUSALS`'s keys are
already compared against 0019's `PT` codes — so a member added on one side and
not the other is refused, and neither file is a second authority.

### The class guard, which is the run's real output

`test_every_refusal_site_maps_to_exactly_one_denial_reason` scans the agent
plane's modules for refusal raises and requires each to be reachable from a
branch that records a reason. **It exists so a sixth — now ninth — refusal
cannot be added later with no reason attached**, which is the way a taxonomy
stops covering its subject: not by being wrong, but by standing still.

## Alternatives rejected

**Reuse `CALLER_FACING_TOKENS` as the taxonomy.** It is the wrong set in both
directions: it has no member for the three structural classes, which are the
ones an operator most needs distinguished, and it carries `row_not_found`, which
is an outcome rather than a boundary.

**Free text.** Refused by the brief and by the plane's standing rule: a denial
reason a caller could influence is a caller value in an operator's console. The
column is the enum type, so the database refuses it rather than a convention
discouraging it.

**Five members, as the brief named them.** `credential` would be a reason
nothing can record, and D816's rule cuts the other way too — a declared value
with no writer is as unverified as a field with no reader.

**One member for every structural refusal.** That is `STRUCTURAL_REFUSAL` again,
and it is right for the *caller*. In an audit row it makes a deployment fault, a
dead upstream and an unwritable audit table the same event.

## Consequences

- `app_private.agent_audit` gains three columns and the table's grants do not
  change: the definer functions remain the only path in.
- The audit function signatures move, so **ADR 0175's arity check earns its
  keep** — every call to a released `app_private` function is verified against
  the arity its migrations declare, which is the guard Session 15 Run 8 built
  after exactly this kind of change broke four proofs.
- `denial_reason` is NULL for every outcome that is not a refusal, and that is a
  fact the column states: a served row with a reason would be a contradiction.
- A ninth boundary requires a migration, a constant, and the guard's assent.
  That is deliberately more expensive than adding a string.
