# 0125 — The agent plane forwards the caller's own token, and resolves context once

Status: accepted
Date: 2026-08-20
Session: 8, Run 5
Affects: ADR 0065, ADR 0066, ADR 0113, ADR 0115, ADR 0117, ADR 0118, ADR 0121,
ADR 0124, D407, D417, D432, D433, D434, D435,
`services/auth-api/app/mcp_upstream.py`,
`services/auth-api/app/mcp_authorization.py`,
`services/auth-api/app/mcp_runtime.py`

## Context

ADR 0117 decided that an agent request runs under its **owner's** identity, and
that the discriminator is `token_use` rather than the physical role. Migration
0018 implements it: the pre-request hook establishes `app.user_id` as the
agent's owner with `app.agent_id` beside it, and `api.mcp_agent_context()`
returns the calling agent's own row.

What was not decided is **how the MCP runtime learns that context**, and the
question has exactly one dangerous answer. A runtime that holds a service
credential and looks the agent up on the caller's behalf is a confused deputy:
its authority, not the caller's, decides what the lookup can see. ADR 0065/0066
already state the general form — *a proof that reaches the right end state by a
route the product does not take proves the end state is reachable, not that the
product reaches it* — and this is the same error committed in production rather
than in a test.

## What was measured

**Against a live PostgREST on the locked digest**, with all eighteen migrations
applied as `migration_user` and real RS256 tokens. Nine arms, every one with a
control that discriminates.

| arm | request | result |
|---|---|---|
| M1 | agent token → `POST /rpc/mcp_agent_context` | **200**, a JSON **array of one object**: `agent_id, role_name, scopes, authz_version, owner_id`, and `owner_id` is the agent's owner |
| M2 | the same, `Accept: application/vnd.pgrst.object+json` | **200**, a single object |
| M3 | CONTROL — a human `access` token | **403**, `42501 permission denied for function mcp_agent_context` |
| M4 | CONTROL — no `Authorization` header | **401**, and the body is also `42501 permission denied` |
| M5 | agent token naming an agent that does not exist | **401**, `PT401 / AP401: the request identity is no longer current` |
| M6 | agent token → `POST /rpc/owner_activity_report` | **200**, the owner's counts |
| M7 | CONTROL — a token signed by another key, same `kid` | **401**, `PGRST301 None of the keys was able to decode the JWT` |

Three of those change the design rather than confirm it.

**M5 is the important one.** The migration's own comment says
`mcp_agent_context` returns *"zero rows when the caller is not an agent — a
question with no answer rather than an error"*. Over HTTP that branch is
**unreachable for a stale or unknown agent**: the pre-request hook refuses first,
with `AP401`, and the function is never entered. So a client written to treat
"200 with an empty array" as the normal not-an-agent answer would be handling a
case the product does not produce — while a 200 with zero rows, if it ever *did*
occur, would mean something has gone wrong. It has to be a refusal, not an empty
context.

**M4 shows a 401 whose body is a privilege error.** Anonymous requests fail on
`42501`, not on a token error, so **status alone does not say what went wrong**
and the runtime must not report "your token is invalid" from a 401.

**M3 is D417 seen from the other side.** A human token is refused by a *missing
GRANT* rather than by the `token_use` branch — correct outcome, and the reason
is a privilege. This path is not reachable from the agent plane, because ADR
0115 refuses `token_use: "access"` before any lookup; it is the defence behind
that door, and it is worth knowing it answers 403 rather than 401.

**The one-request cache was measured too**, because "cached for one HTTP request"
is a claim about a mechanism. A `ContextVar` set on entry and reset in a
`finally`, against twelve concurrent requests with twelve different tokens:

| implementation | requests observing another caller's context |
|---|---|
| `ContextVar`, reset in `finally` | **0 of 12** |
| CONTROL — a module-level dict | **11 of 12** |

And the control's failure mode is the reason the concurrency arm exists: run
**sequentially**, the module-level dict is correct every time. A test written
against sequential requests would have passed the broken implementation.

**The framework's own ordering was measured** (Run 5, Rig J): an unauthenticated
request is refused at **401 with no middleware hook reached at all**, and
`on_request` fires **once per HTTP request**, before both `on_list_tools` and
`on_call_tool`.

## Decision

**The agent plane forwards the caller's own token, unchanged, and resolves the
agent's context exactly once per HTTP request.**

1. **The original compact token is what goes upstream.** Not re-signed, not
   re-minted, not exchanged. The runtime holds no signing key (ADR 0121) and no
   database credential (D407), so it has nothing else it *could* send — which is
   the point: the absence of a service identity is what makes the confused
   deputy unconstructible rather than merely unwritten.
2. **No injected identity headers.** The runtime never sets a role, a subject,
   an owner, `request.jwt.claims`, or any PostgREST header that would name a
   principal. The only authorization input is `Authorization`, and it is the
   caller's.
3. **Resolution happens in `on_request`**, before discovery or execution, so
   both paths see the same context and neither can run without one.
4. **The result is held in a `ContextVar`, keyed by a non-reversible fingerprint
   of the token**, and reset in a `finally`. The key is belt and braces: if a
   value ever outlived its request, a fingerprint mismatch turns a **leak into a
   miss**. The fingerprint is a SHA-256 of the token and is never logged.
5. **Exactly one row is a context. Anything else is a refusal.** Zero rows, two
   rows, a non-200, or a malformed body are all refusals, and none of them
   produces an empty context that a later tool could read as "an agent with no
   scopes".
6. **A refusal tells the caller nothing about which** — upstream status codes and
   PostgREST error codes are not relayed. ADR 0097's split: a structural refusal
   says nothing, because anything it said would be a claim about state to
   somebody who has not established they may ask.

## Alternatives rejected

**Give the runtime a service token or a database role for the lookup.** The
confused deputy, in the form the runbook's §4.9 half-invites. It would also put
a fifth claimant in ADR 0099's connection budget, whose considered zero is
asserted by a test that parses the arithmetic (D407).

**Trust the claims the runtime already verified, and skip the call.** The
runtime verified a *signature and a shape* (Run 4). It cannot know whether the
agent was disabled, its scopes narrowed, or its `authz_version` moved since the
token was minted — which is exactly what `agent_claims_are_current` compares and
what M5 refuses. A token is a statement about the past.

**Cache across requests, keyed by the token.** It is the obvious performance
answer and it reintroduces the whole revocation problem: an agent disabled
between two requests would keep working until the entry expired, and the expiry
would be a number nobody measured. The cost of not caching is one round trip per
HTTP request to a service on the same internal network.

**Cache in a module-level dict.** Measured: 11 of 12 concurrent requests saw
another caller's context. It passes every sequential test.

**Treat 200-with-zero-rows as "not an agent" and continue with no context.** M5
shows the product does not produce it, so the branch would be untested by
construction — and it is the branch that would hand a tool an empty scope set.

## Consequences

- **Every MCP request costs one PostgREST round trip**, on the internal network,
  before anything is served. That is the price of asking the authority rather
  than trusting a token, and ADR 0088's rotation model makes the same trade.
- **The agent plane depends on PostgREST being up.** A 5xx or a connection
  failure is a refusal, not a degraded mode — there is no cached identity to fall
  back to, deliberately.
- **`mcp_upstream.py` is the second row in ADR 0124's transport allowlist**, and
  the reason is recorded there.
- Run 6's tools read the context from the same `ContextVar`. They never call
  `mcp_agent_context` themselves, so there is one resolution per request and one
  place that decides what a refusal is.
