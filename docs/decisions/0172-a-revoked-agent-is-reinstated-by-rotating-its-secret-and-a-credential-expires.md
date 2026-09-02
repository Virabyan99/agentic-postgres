# 0172 — A revoked agent is reinstated by rotating its secret, and a credential expires

- **Status:** accepted
- **Date:** 2026-09-03
- **Session:** 15, Run 4 (`IDN-AGENT-001`, D503, D838–D842)
- **Related:** **D503** (`revoked → active` answers 200 and nobody had decided
  whether it should), **D817** (the plan assigns the decision to this session and
  requires the measurement first), **D838** (what re-activation actually
  restores), **D839** (rotation does not reinstate, so refusing the transition
  outright would strand an agent), **D840** (widening a released function costs a
  DROP, and the DROP takes the grant), ADR 0078 (`authz_version`, and why the
  bound half was already proved), ADR 0091 (released migrations are fix-forward),
  ADR 0171 (the database's `now()` is the authority for a deadline), 0011 (which
  calls a revoked agent credential terminal).

## Context

D503 has been open since Session 9, phrased carefully: migration 0011 calls a
revoked agent credential terminal, `auth_set_agent_status` is an unguarded
`UPDATE`, and **the bound half is proved** — `authz_version` moves on every
transition, so no token issued before either survives. What nobody had decided is
whether un-revoking should be refused at all.

The plan required the measurement before the decision, and the measurement is
what makes this ADR different from the one it would otherwise have been.

**What `revoked → active` restores** (D838), measured end to end through the
running service against a live cluster:

| step | exchange with the ORIGINAL secret | `authz_version` |
|---|---|---|
| fresh | 200 | 1 |
| after `revoked` | 401 | 2 |
| after `active` again | **200** | 3 |

So **revocation frees no credential.** It flips a flag, and re-activation hands
the original secret back its authority. A token issued before the revocation is
still refused afterwards — `authz_version` moved twice — which confirms the half
D503 always said was safe and isolates the half that is not.

**And rotation is not a way back** (D839). Rotating a revoked agent's secret
answers 200, replaces the secret, moves `authz_version` — **and leaves the agent
revoked**, with the new secret refused. So today the *only* path from `revoked`
to a working agent is `revoked → active`, which is exactly the transition that
restores the old secret.

That is why this ADR does not simply refuse the transition: refusing it with
nothing else changed would leave an agent revoked by mistake permanently dead,
recoverable only by creating a new one with a new id, new grants and a new owner
record.

## Decision

### 1. `revoked → active` is refused

`auth_set_agent_status` raises `AP409` with errcode `PT409` on that transition
and on no other. `active → revoked`, `revoked → revoked` and `active → active`
are unchanged, and a refused call leaves the row exactly as it was — measured.

**Revocation is the response to a credential that must stop working.** An
operator who revokes because a secret leaked, and later re-activates, has
silently restored the leaked secret; nothing in the API says so and nothing in
the record distinguishes that from a deliberate reinstatement. This is 0011's own
statement — that a revoked agent credential is terminal — made true of the
credential rather than only of the sentence.

### 2. Reinstatement is rotation, and rotation clears the revocation

`auth_rotate_agent_secret` now sets `status = 'active'` alongside the new secret.
So the way back exists, it is one operation, and it is the operation that
**guarantees the revoked-era secret never authenticates again.**

**One operation and not two, deliberately.** A separate "reinstate" verb — or
requiring rotate-then-activate — leaves a state in which an agent is active while
its live secret is the one revocation was the response to. That window is the
entire thing this decision removes, and a design that reopens it between two API
calls has moved the defect rather than fixed it.

The cost is stated: an operator who revoked an agent temporarily, meaning to
switch it back on unchanged, must now redistribute a secret. **That is the
intended cost.** "Temporarily off, same credential" is not a state this plane
offers, because the plane cannot tell it apart from "off because it leaked".

### 3. An agent credential expires, and the expiry is enforced at verification

`agent_credentials` gains `expires_at`. `auth_lookup_agent` returns
`secret_expired`, computed by the database against its own `now()`, and the
service refuses an expired credential in the exchange — **after** the hash
comparison and beside the status check, so every failure still costs one Argon2
verification and an expired agent is indistinguishable from an unknown one.

**Checked at verification and not at issuance**, which is the difference between
a control and a policy: an expiry consulted only when the credential is minted
constrains the mint and nothing else, and the credential it produced outlives it.

The TTL is `AGENT_SECRET_TTL_SECONDS` — 90 days — and **a create may name a
shorter or longer one within bounds**, which is what makes it configurable rather
than a constant with a comment. Out of bounds is a refusal rather than a clamp:
silently shortening a lifetime an administrator asked for would produce agents
expiring at a moment nobody chose.

**Rotation keeps the deployment default**, and that is a decision rather than an
omission. Rotation is the urgent path — a lost secret, and since decision 2 the
way back from a revocation — so requiring a lifetime there adds a choice at the
moment an operator has least attention to spare. The lifetime belongs to the
agent and is named when the agent is created.

**The database's clock decides**, as it does for a refresh token's deadline (ADR
0171). The service reads a boolean rather than a timestamp it compares itself, so
there is one clock in the decision and no skew to reason about.

### 4. Existing credentials do not expire, and that is a decision

The column is added nullable and **existing rows keep `NULL`**, which
`auth_lookup_agent` reports as not expired.

Backfilling a deadline onto credentials already in use would expire agents whose
operators were never told the rule changed — a deployment that upgraded would
find its agents failing at a moment this repository chose. An expiry applies from
the next credential each agent is issued, which every agent reaches through the
rotation this ADR just made the way back.

## Consequences

- **Four released functions are dropped and recreated**, because
  `CREATE OR REPLACE` cannot widen a `RETURNS TABLE` — measured, `42P13`, with an
  identical replace accepted as the control (D840). **A `DROP` takes the grant
  with it**, also measured, so the migration re-issues every one; forgetting is
  silent until the service is refused at runtime.
- **`PATCH {"status": "active"}` on a revoked agent now answers 422**, translated
  from the product's own `PT409` and naming rotation as the way back. It is not a
  relayed status (ADR 0139): the errcode is this deployment's own.
- **An agent whose secret expires is refused exactly like one that never
  existed**, so an operator diagnosing "my agent stopped working" needs the
  listing, which is why `auth_list_agents` publishes `secret_expires_at`. An
  expiry nobody can see is an outage with a countdown.
- **D503 is closed.** The open question was whether un-revoking should be
  refused; it is, and the way back is a stronger operation than the one removed.
