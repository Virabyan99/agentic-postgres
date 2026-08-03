# Security acceptance

Expected denial behaviour for every security guarantee. A value may remain
undecided only when it has an owner, a target session, and a requirement ID —
"TBD" with none of those is an unowned TODO, which the handoff rules forbid.

Companion to [the threat model](threat-model.md), which maps threats to
controls. This file records what a *denial actually looks like*, so a test
asserting "access was denied" can assert something specific rather than merely
"not 200".

## Why denial codes are specified in advance

A denial that returns the wrong status is still a bug, and one that returns a
*revealing* status is a security bug. `404` versus `403` on another user's row
is the standard example: `403` confirms the row exists.

The rule for this project: **an authorization failure must not distinguish
"does not exist" from "exists but is not yours."** Row-level security produces
this naturally — a filtered row is simply absent — and the API surface must not
reintroduce the distinction by checking existence before ownership.

## Denial matrix

| Scenario | Surface | Expected result | Must not reveal | Requirement | Session |
|---|---|---|---|---|---:|
| Anonymous request for a protected resource | PostgREST | `401` when no token, `403` when the token carries no grant | Whether the resource exists | `SEC-ANON-001` | 5 |
| User A requests User B's note by ID | PostgREST | `200` with an empty result set | That the ID is valid | `SEC-RLS-001` | 3 |
| User A attempts to update User B's task | PostgREST RPC | Zero rows affected, not an error | That the row exists | `SEC-RLS-001` | 3 |
| Request against `app` or `app_private` | PostgREST | `404` — the schema is not exposed at all | The internal schema layout | `SEC-PRIV-001` | 5 |
| Call to an ungranted function | PostgREST | `403` | The function signature | `SEC-FUNC-001` | 3 |
| Token with wrong issuer, audience, or algorithm | Any verifier | `401`, no role assumed | Which claim failed | `SEC-JWT-001` | 6 |
| Expired token | Any verifier | `401` | Time skew details | `SEC-JWT-001` | 6 |
| Token for a revoked agent | MCP and PostgREST | `403` on the next request, both paths | Whether the agent ever existed | `SEC-REV-001` | 9 |
| Read-only agent lists tools | MCP | Write tools absent from the listing | That write tools exist | `AGT-WRITE-001` | 9 |
| Read-only agent invokes a write by name | MCP | `403`, audited as `denied` | That the tool name is valid | `AGT-WRITE-001` | 9 |
| Agent supplies `agent_id` as a tool parameter | MCP | Parameter ignored; identity taken from claims | That the parameter was seen | `SEC-PARAM-001` | 9 |
| Agent submits a SQL string in a filter value | MCP | Treated as a literal value; zero or unrelated rows | Any parse error text | `SEC-INJ-001` | 8 |
| Agent requests more rows than its budget | MCP | Truncated to the server-side ceiling | The true total row count | `AGT-BUDGET-001` | 8 |
| User A requests a download URL for User B's object | FastAPI | `404` | That the object ID is valid | `STO-OWN-001` | 7 |
| Client supplies its own object key | FastAPI | `422` — the field does not exist in the schema | The key-generation scheme | `STO-KEY-001` | 7 |
| Download of an object still `pending` | FastAPI | `404` | That an upload was started | `STO-COMPLETE-001` | 7 |
| Direct connection attempt to PostgreSQL from the internet | Network | Connection refused or timed out | That PostgreSQL is running | `SEC-NET-001` | 2 |
| Enabled capability with no live backing operation | Deployment | Exit `5`, deployment refused | — (operator-facing) | `CFG-013` | 1 |

## Audit expectations

Every agent tool attempt produces exactly one audit record whose terminal
status is `succeeded`, `failed`, or `denied`. A `started` record with no
terminal status means the process died mid-request and is itself a signal.

Redacted from every audit payload, without exception:

- Bearer tokens, in whole or in part.
- Passwords and agent secrets, hashed or otherwise.
- Presigned URLs, including their query strings.
- Object contents.
- Any parameter named in the capability's `audit.redact` list.

A write whose `started` record cannot be created **does not execute**
(`AGT-AUDITFAIL-001`). Failing closed is deliberate: an unauditable write is
indistinguishable from an unauthorized one after the fact.

## Undecided, with owners

Nothing is currently undecided. Any entry added here must carry an owner, a
target session, and a requirement ID at the moment it is written.

| Question | Owner | Target session | Requirement |
|---|---|---:|---|
| _(none)_ | — | — | — |
