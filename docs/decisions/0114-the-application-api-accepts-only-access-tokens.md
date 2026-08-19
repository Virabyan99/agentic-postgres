# 0114 — The application API accepts only access tokens

Status: accepted
Date: 2026-08-19
Session: 7, Run 16
Affects: ADR 0095, ADR 0098, ADR 0100, ADR 0101, D393,
`services/auth-api/app/service.py`, `services/auth-api/app/claims.py`,
`tests/deployment/test_session7_storage.py`

## Context

`TOKEN_USES = ("access", "agent")`, and `verify_claims` accepts both — correctly,
because both are tokens this deployment issues. `POST /auth/agent-token` mints
the second kind, and its own docstring says what it is for: **PostgREST**, the
data plane, where an agent's role membership is what refuses it at `SET ROLE`.

Nothing was ever supposed to present an agent token to the application API. But
nothing said so, and `AuthService.authenticate` is shared by both runtimes
(ADR 0101), so what actually happened was:

1. signature verifies — same issuer, same key set;
2. `verify_claims` accepts `token_use: "agent"`;
3. `sub` is an **agent id**;
4. `repository.state(agent_id)` reads `app_private.auth_user_state`, which knows
   only humans, and returns nothing;
5. `AuthenticationFailed("the subject no longer exists")` → **401**.

The refusal is correct and the reason is false. **The agent exists.** It is not a
human, and the message says the opposite of that.

STO-AGENT-001 found it on the first host run that reached the assertion: it
expects **403** from the scope check, on the ground that `objects:*` is human-only
(ADR 0100) and an agent token cannot carry it.

## What was measured

On the host, an agent token — real, minted through `POST /auth/agent-token`,
owned by a subject holding `objects:read` and `objects:write`, in role
`apg_alpha_dev_agent_writer` with scopes `("notes:read",)`:

| request | answer |
|---|---|
| `POST /upload-intents` | **401** `{"error":"authentication_failed"}` |

Read rather than assumed: `authenticate` calls exactly one repository method,
`state(user_id)`, against `auth_user_state`; there is no agent branch. Grepped
across `tests/`, every other agent-token reference is about **issuing** one —
nothing presents one to an authenticated application endpoint.

## Decision

**The application API accepts `token_use: "access"` and nothing else, and says
so.** `authenticate` refuses any other value **before** it looks a subject up.

The status stays **401**. This runtime cannot authenticate that principal: it has
no way to check an agent against the record, which is the whole of ADR 0095's
model, and answering 403 would claim an authentication it did not perform.

## Alternatives rejected

**Leave it, and change the proof to expect 401.** Cheapest, and it keeps a
security property standing on an accident of table membership. If anyone later
taught `authenticate` about agents — for an audit surface, say — storage would
silently begin authenticating them and fall through to the scope check, and the
property would change mechanism with every test still green. A boundary that
holds because of where a row lives is not a boundary anybody chose.

**Answer 403 on `token_use` instead.** Tempting, and it keeps STO-AGENT-001's
assertion untouched: the token is validly issued by this deployment, so
"authenticated but not permitted" reads well. But 403 asserts an identity this
service has **not** confirmed — the current-state comparison cannot run for an
agent, so the token might name a revoked one. **A status that claims more than
the check performed is the defect this repository keeps finding.**

**Teach storage to authenticate agents, then refuse on scope.** It would produce
the 403 the proof wanted, and it would need `auth_lookup_agent`, a grant to
`storage_service`, and a storage runtime that knows agents exist — all to reach a
refusal it already reaches. ADR 0100 made object storage human-only; the fix
should not make the human-only service agent-aware.

## Consequences

- The refusal is **declared**, and the proof asserts a decision rather than a
  side effect. STO-AGENT-001 keeps its meaning and changes its expected status,
  with the reason in its docstring.
- **`/auth/agent-token` is unaffected.** Issuing is not presenting; the endpoint
  still mints agent tokens for PostgREST, which is what they are for.
- Session 8 will want agents to reach an MCP surface. That surface will have to
  say which token uses **it** accepts, rather than inheriting this one's answer —
  which is the point of writing it down here instead of leaving it implicit.
