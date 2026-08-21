# 0132 — Session 8's requirements gain live proofs, and four new ids carry the deployed guarantees

Status: accepted
Date: 2026-08-21
Session: 8, Run 9
Affects: ADR 0045, ADR 0089, D47, D279, D331, D457,
`tests/acceptance-registry.yaml`, `src/agentic_postgres/evidence_claims.py`

## Context

The Session 8 plan says two things that cannot both be true as written.

**§2:** *"What Session 8 adds to the acceptance registry: **Nothing.** The five
requirement IDs already exist and point at placeholders … Replace the
placeholders; keep the IDs and their descriptions."* Run 6 did exactly that.

**§7:** *"Host and external halves are written separately and merged by
`bin/write-session-evidence.py --session 8`."*

A session's evidence is its claims, and `claim_mode` derives where a claim can be
measured from the environment markers on the tests its requirements name.

## What was measured

Asked of the model rather than of the plan, with a control:

| arm | result |
|---|---|
| `AGT-READ-001` | 2 node ids, **no environment marker** |
| `AGT-SQL-001` | 6 node ids, **no environment marker** |
| `AGT-SCOPE-001` | 3 node ids, **no environment marker** |
| `AGT-DRIFT-001` | 1 node id, **no environment marker** |
| `AGT-BUDGET-001` | 4 node ids, **no environment marker** |
| `SEC-INJ-001` | 5 node ids, **no environment marker** |
| a claim over two of them | **refused** — *"has no live proof: every test it names runs in a checkout, so no deployment is being measured"* |
| **CONTROL** — `object_ownership`, a Session 7 claim | resolves to `host` |

**Session 8 has six requirements and not one of them can carry a claim.** Run 6
replaced the placeholders with contract tests, which was right — they are
contract properties — and it left the session with no evidence at all. The gate
would have had two modes and nothing to say in either.

The control matters here more than usual: without it, "every arm refused" is
equally well explained by a rig that cannot resolve anything.

## Decision

**Three rules, and which one applies is decided by whether the guarantee changed
or only the environment did.**

**1. Where the guarantee is the same, the existing requirement gains live node
ids.** `AGT-READ-001`, `AGT-SCOPE-001`, `AGT-BUDGET-001` and `SEC-INJ-001` each
state a property of a *deployment* that Run 6 could only prove structurally. A
second id for "the same thing, but really running" would be one guarantee with
two names, which is what D47 refused. The offline proofs stay: `claim_mode`
resolves the requirement to `host` on its live members, and the contract members
are run by name through `static_nodeids_for_mode`.

**2. Four new ids, because four guarantees are about a deployment and did not
exist offline.**

| id | mode | guarantee |
|---|---|---|
| `AGT-PLANE-001` | host | The plane is published at **one** path; health is private by the absence of a route; an `Origin` is refused |
| `AGT-TOKEN-001` | host | Only `token_use: "agent"` is accepted — an access token, an anonymous request and an unknown agent are each refused |
| `AGT-CRED-001` | host | The container holds **no** database credential and **no** signing key, read out of the running container (D411) |
| `AGT-PUBLIC-001` | external | What a stranger reaches of `/mcp`, from a network that is not the host |

Every one names `target_session: 8` and only Session 8 requirements, because
`claim_session` is a `max()` and a single older id mixed in either drags the
claim into an earlier session's evidence or hides it from this gate — and **both
failures are silent** (ADR 0089, D279).

`AGT-PUBLIC-001` is a new id rather than a widening of `SEC-API-001` for the
reason `STO-PUBLIC-001` was: a claim is measured in exactly one environment
(ADR 0045), and widening a Session 5 id would withdraw a Session 5 claim from
Session 5's evidence.

**3. `AGT-DRIFT-001` is deliberately in no claim.** Its guarantee — adding an API
operation exposes no capability without a `capabilities.yaml` change — is a
property of the **compiler**, proved by adding a real operation to both the
reviewed surface and the approved snapshot and asserting the compiled bytes do
not move. That is complete in a checkout. Under ADR 0045 it is therefore not a
claim, and **D331 is the precedent**: Session 7's Run 1 wrote
`connection_budget_division` and `storage_scope_class`, the model refused both,
and they stayed out as ordinary suite properties rather than being given a host
arm to qualify them.

**Eight claims**, and one guarantee each (D47):

    agent_reads               AGT-READ-001
    agent_query_construction  AGT-SQL-001, SEC-INJ-001
    agent_scopes              AGT-SCOPE-001
    agent_budgets             AGT-BUDGET-001
    agent_surface             AGT-PLANE-001
    agent_authentication      AGT-TOKEN-001
    agent_credentials         AGT-CRED-001
    public_agent_boundary     AGT-PUBLIC-001

`agent_query_construction` carries two ids for the reason `object_completion`
does: *no caller input becomes syntax* is one guarantee measured from two sides —
the builder's, which shows what it constructs, and the attacker's, which shows
what it cannot be made to construct.

**`AGT-BUDGET-001` is also widened to the four budgets.** Its description said
*"Elapsed time and concurrency are Run 8's and are deliberately not claimed
here"*, and Run 8 built them (ADR 0129). Leaving the sentence would be a
description that has outlived its node ids, which is D175's unfixed failure mode
sitting in the one file that is supposed to be authoritative.

## Alternatives rejected

**A new id for every deployed property, leaving the six offline ones alone.** It
reads tidier and it splits four guarantees in half: `AGT-READ-001` would mean
"the adapter forwards the caller's token" and its twin would mean "and when it
does, rows come back". Nobody could say which one a regression belonged to.

**Declare the claims anyway and let them be offline.** The model refuses, and the
refusal is right: ADR 0045 shapes a claim by where it can be measured, and a
claim proved in a checkout is a statement about a repository rather than about a
deployment. Evidence that said `passed` for a plane that had never started is
exactly what D282 and D211–D214 are about.

**Give `AGT-DRIFT-001` a host arm to make it claimable.** The available host arm
is "the deployed lock matches the committed contract", which is a *different*
guarantee — about what was published, not about what the compiler will emit. Two
guarantees under one id is D47 again, and it would be reached for only to satisfy
the shape of the evidence document.

## Consequences

- **Session 8's evidence has both halves**, and the external half is not
  ceremonial: `AGT-PUBLIC-001` is measured from off-host or not at all.
- **Every one of these claims reports `not_run` until a host trip.** No `mcp`
  container has started anywhere. This sentence is the one D282 wrote one run
  before Session 6's trip found nine defects, and D331's module wrote again one
  run before Session 7's found eight. **A claim that has never been measured must
  not be mistaken for one that passed.**
- The offline contract proofs are now load-bearing twice: once as suite
  properties and once as explicitly-run members of a host claim. A test moved
  between files silently breaks the second, which
  `test_every_claim_proof_is_collected_by_exactly_one_selector` catches.
- `AGT-DRIFT-001` remains a P0 requirement with a passing test and no claim, and
  that combination is now precedented twice rather than once.
