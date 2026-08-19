# 0115 — The agent plane accepts only agent tokens

Status: accepted
Date: 2026-08-19
Session: 8, Run 1
Affects: ADR 0095, ADR 0100, ADR 0113, ADR 0114, D393, D396, D397,
`services/auth-api/app/claims.py`, `services/auth-api/app/service.py`,
`schemas/outputs.schema.json`, `src/agentic_postgres/deployed_output.py`

## Context

ADR 0114 closed one half of a question and said, in as many words, that the other
half is Session 8's: *"Session 8 will want agents to reach an MCP surface. That
surface will have to say which token uses **it** accepts, rather than inheriting
this one's answer."*

This is that answer, and it is written before the runtime exists rather than
after, because the failure ADR 0114 records is what happens when a boundary is
never chosen. D393 was an agent token refused at the application API for a false
reason — `sub` was an agent id, `auth_user_state` knows only humans, the lookup
returned nothing, and the caller was told *"the subject no longer exists"* about
an agent that exists. The outcome was right. The mechanism was an accident of
which table a row lives in, and it would have changed the day `authenticate`
learned about agents for any purpose at all.

The agent plane is the mirror image of that surface, and it is exposed to the
mirror image of that accident. An MCP runtime that verifies the claim contract
and then goes looking for an agent would refuse a **human** token because
`app_private.agents` has no row for a user id — correct outcome, false reason,
same shape, arriving from the other direction.

## What was measured

A rig in `/tmp`, minting through `AuthService.agent_token` — the real path
`POST /auth/agent-token` takes, hasher and repository included — and reading the
claims back out of the signed token. The **control** is a human token from the
same service, the same signing key and the same issuer, differing only in the
exchange that produced it. A negative control was run first: one expectation
inverted, rig reports `DIVERGES`, exits 1. It can tell success from failure.

| | agent token | control (human token) |
|---|---|---|
| `token_use` | `agent` | `access` |
| `sub` | the agent id | the user id |
| `credential_version` | **0** | 4 (the subject's) |
| `authz_version` | 7 (the agent's) | 7 |
| `role` | `…_agent_reader` | `…_authenticated` |
| claim set | 12 claims | **the same 12 claims** |

`TOKEN_USES` is `("access", "agent")`. `REQUIRED_CLAIMS` has exactly twelve
members and there is **no `agent_id` claim** — `sub` is the agent id (D397).

**The two token classes are structurally identical.** Same issuer, same audience,
same key set, same twelve claims, same lengths. Nothing about the shape of an
agent token distinguishes it from a human one. The only two claims that differ in
kind are `token_use` and the `credential_version: 0` convention, and of those
only the first was minted as a discriminator.

That is the whole reason this ADR exists. A surface that does not read
`token_use` is not defended by anything else in the token.

## Decision

**The MCP surface accepts `token_use: "agent"` and nothing else, and refuses any
other value before it looks up an agent, a scope or a capability.**

Three consequences follow, and each is stated rather than implied:

**1. A human access token reaching `/mcp` is refused on `token_use`.** Not
because `app_private.agents` has no row for it — that refusal would be D393
running backwards. The refusal is a declaration.

**2. The application API's answer does not move.** ADR 0114 stands unchanged:
`ACCEPTED_TOKEN_USE = "access"` there, `"agent"` here, and the two constants are
named in their own runtimes rather than derived from each other. Deriving one
from the other — a shared `THE_OTHER_ONE` — would make the pair a single
decision, and they are two, taken by two services for two reasons.

**3. The accepted value is published as a field, not as prose.** The deployed
document's `mcp.accepted_token_use` carries it (outputs v12, and D413 is the
rule: *a claim that lives only in prose is a claim nobody checks*). `/docs/rest`
was proved at 401 and 200 for four runs and had never rendered, because nothing
requested the script its own markup named (D274).

**`credential_version: 0` is not the discriminator.** It is a convention that
makes "not a human" a value rather than an absence (D397), and it is load-bearing
in that direction only. Reading it as an authorization input would put the
boundary back on an accident: a human whose credential version legitimately
reached 0 does not exist today, and "does not exist today" is not a control.

## Alternatives rejected

**Accept both, and let scopes do the work.** `objects:*` is human-only (ADR 0100)
and the agent scope vocabulary is closed, so a human token carrying `notes:read`
would pass every scope check on the read surface. It would then be authorized as
an agent — through an agent's PostgREST role, under an agent's RLS — while
naming a user id in `sub`. The scopes are per (resource, verb) precisely so they
do **not** say who is asking (D399); asking them to is asking the wrong authority.

**Refuse by looking the subject up.** `sub` is not in `app_private.agents`, so a
human token fails there already, today, without a line being written. This is
exactly ADR 0114's rejected alternative, and it fails for exactly its reason: the
boundary would stand on which table a row is in, and would change silently the
day the agent plane learns about owners — which Session 8's
`api.mcp_agent_context()` does in the very next run, returning `owner_id`.

**Mint a third `token_use` for MCP** — `mcp`, say. It would make the surface and
the token one-to-one, and it would also make `POST /auth/agent-token` issue a
token that PostgREST's data plane no longer recognises, splitting one principal
class in two by the door it walked through. An agent is an agent whichever
surface it presents at; ADR 0100's classes are about resources, not doors.

## Consequences

- **Both refusals are explicit, and both are proved.** The application API's is
  `test_an_agent_token_is_refused_before_any_subject_lookup`; the agent plane's
  is its mirror, and neither may pass by reaching the right end state through a
  lookup that happens to miss.
- **`accepted_token_use` is in the deployed document**, so a deployment that
  changed its mind is visible to a proof that reads the document rather than the
  source.
- The two constants will be compared by a test that asserts they are
  **different** — one value each, and no overlap. A surface that accepted both
  would satisfy any test asserting only its own value.
- Session 9 adds write tools. It inherits this answer and does not restate it:
  `agent_writer` is a role and a scope class, not a token use.
