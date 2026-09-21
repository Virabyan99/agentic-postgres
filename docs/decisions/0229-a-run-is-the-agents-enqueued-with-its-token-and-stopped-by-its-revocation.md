# 0229 — A run is the agent's: enqueued with its token, authorised by its own scopes, minted per step, and stopped by its revocation

- **Status:** Accepted
- **Date:** 2026-09-21
- **Session:** 32, Run 1 (D1649, D1650, D1651, D1659)
- **Amends:** **ADR 0114** — *one token use per API* becomes *one token use per
  route set*. `authenticate` is unchanged and still refuses an agent token;
  every existing route's refusal is byte-for-byte what it was.
- **Affects:** `services/auth-api/app/service.py` (`step_token`,
  `authenticate_agent`, the `agent_token` split), a new
  `services/auth-api/app/workflow_routes.py` with three routes,
  `openapi_docs.py`, `contracts/app-openapi.canonical.json`, and
  `bin/workflow.py`'s four HTTP verbs.
- **Related:** ADR 0114 (amended), ADR 0115 (the plane accepts `agent` only),
  ADR 0135 (the audit as caller), ADR 0141/0178 (a denial names its boundary),
  ADR 0172 (an expired secret is refused after the hash), ADR 0200 (the
  vocabulary is derived from the surface), ADR 0226, ADR 0227.

## Context

An agent must be able to start a run, read it and cancel it, **as itself**.

The auth API authenticates **access** tokens only: `authenticate()` refuses
`token_use: agent` by decision (`service.py:299`), and every `/admin/*` route
calls it. An agent holds an **agent** token, minted for PostgREST and the
plane. **No route on the auth service accepts one today.**

The three candidates were an MCP tool, a human-token route, and a second
authenticator. An MCP tool would move the compiled contract's `tools_sha256`,
every deployed lock and the harness's cases — a contract move for a control
operation that is not a tool. A human-token route would start a run as the
wrong principal.

## Decision

**Three routes on the auth service, in `auth` mode only** — `POST
/workflows/runs`, `GET /workflows/runs/{run_id}`, `POST
/workflows/runs/{run_id}/cancel` — authenticated by a **second
authenticator**, `AuthService.authenticate_agent(authorization)`.

It parses the bearer and decodes with the same key set and the same claim
contract `authenticate` uses, then **requires `token_use == "agent"`**, loads
the agent record, and refuses unless `status = 'active'` and the record's
`authz_version` equals the token's — the hook's own tuple (`0018:60-78`).
**Each authenticator refuses the other's token use, asserted in both
directions.**

The routes are the agent's own. A run is enqueued **as the token's agent**;
`status` and `cancel` refuse another agent's run with the **same 404** a
missing run gets, so nothing leaks existence. **No new scope**: enqueue
requires the agent's stored scopes to cover the definition's `required_scopes`
union, refused as `scope_not_held` otherwise. A workflow adds no authority, so
inventing a `workflows:run` scope would contradict ADR 0200 — the vocabulary is
derived from the surface.

### `step_token`, and why it is safe without a secret

`agent_token(agent_id, secret)` does: parse the uuid, look the agent up,
**compare the hash**, then refuse a `credential is None`, a mismatch, a
non-`active` status and an expired secret, then issue. The hash is compared
**before** the status is consulted (`service.py:453`), and that order is
deliberate — ADR 0172's indistinguishability.

The split keeps it. Two helpers: `_agent_record(agent_id)` (the uuid parse and
the lookup) and `_refuse_unless_issuable(credential)` (the status and expiry
checks, in the existing order, with the existing messages). `agent_token` is
`_agent_record` + the hash comparison + `_refuse_unless_issuable` + issue.
`step_token(agent_id)` is `_agent_record` + `_refuse_unless_issuable` + issue.

**The secret proves possession; a claimed step in the database proves it
instead.** The loop runs inside the process that holds the signing key and
could already mint for anyone — that is ADR 0226's whole point — so the
question is not whether the loop *can* mint but whether minting this way
reaches any agent an agent's own mint could not.

**Rig 32f answered it against the real `AuthService`:**

| Record | `agent_token` | `step_token` |
|---|---|---|
| active | issues | issues |
| revoked | `agent is revoked` | `agent is revoked` |
| expired secret | `agent secret has expired` | `agent secret has expired` |
| unknown id (control) | `no such agent` | `no such agent` |
| not a uuid (control) | `agent id is not a uuid` | `agent id is not a uuid` |
| active, wrong secret | `secret mismatch` | — no secret to be wrong |

The two tokens for the same active agent **differ in `jti` alone**: same
`token_use`, same `scope`, same `role`, same `authz_version`, same
`credential_version`, same `sub`, same `iss`/`aud`. The claim is spelled
**`scope`**, not `scopes` — measured, after the rig's first pass compared two
absent keys and passed vacuously.

**One token per step attempt, minted after the claim and dropped at finish.**
Never stored on the run, never reused across steps — asserted by an AST proof
that no name `token` outlives the step function's frame and by a unit proof
counting `step_token` calls against steps.

### What a revocation does

A refused mint (`AuthenticationFailed`) finishes the step as `token_refused`
and stops the run with `stopped_reason: agent_not_active`. **No tool call is
made**, so **no audit row exists for that step.**

The brief asked for `scope_not_held` audited at the boundary. That claim is
rewritten, because the tree cannot show it (D1650): an audit row is written
**by the agent** through `agent_audit_begin` as the caller (ADR 0135), and
when the mint is refused there is no token, no call and no row. A revocation
landing **mid**-step is refused by the hook before the audit function runs
(`0018:238`, `PT403`), which the plane records as a **structural** refusal
(`AUDIT_UNAVAILABLE`, `mcp_tools.py:801-808`) — not `scope_not_held`.

So the claim is: **the run stops at the next step boundary with
`stopped_reason: agent_not_active`, the step is `token_refused`, and the audit
table holds NO row for that step** — with the control run, unrevoked, holding
one row per step. An empty audit table for the step is a *stronger* statement
than a denial row, and it is one that will not fail on first execution.

The mid-step arm is not separately proved. It is the plane's own revocation
proof (`tests/security/test_session9_revocation.py`), unchanged.

### The command

`bin/workflow.sh` has six verbs: `init`, `validate` (ADR 0228's), and `run`,
`dry-run`, `status`, `cancel`. The three HTTP verbs call a **closed table** of
three routes and nothing else, take the base URL from `--project-outputs FILE`
(`bin/api.py`'s shape) and the token from **`APG_AGENT_TOKEN`** — from the
environment, never an argument. The command holds no SQL.

## Consequences

* ADR 0114's amendment is the **smaller** change: it keeps every existing
  route's behaviour byte-for-byte and adds a second authenticator beside the
  first, rather than widening the first.
* The OpenAPI document gains three operations, so the release's floor is
  `api_operation_added` — declared, not inferred (D1666).
* A revoked agent cannot **enqueue** at all: the route's `authenticate_agent`
  and `workflow_enqueue`'s own `PT403` both refuse it. The live revocation
  proof must therefore revoke *after* the enqueue, which makes it a race — and
  the proof says so in its own docstring rather than pretending otherwise. The
  offline proof is where the boundary is pinned exactly.

## Alternatives rejected

* **An MCP tool to start a run.** Rejected: it moves `tools_sha256`, every
  deployed lock and the harness's cases, for an operation that is not a tool
  call.
* **A route taking a human's access token.** Rejected: it would start a run as
  the wrong principal, and the whole point is that a run holds nothing the
  agent does not.
* **A new `workflows:run` scope.** Rejected: the vocabulary is derived from
  the reviewed surface (ADR 0200), and a workflow adds no authority — it
  spends the agent's own.
* **Widening `authenticate` to accept both uses.** Rejected: it would change
  the refusal every `/admin/*` route depends on, which is ADR 0114's actual
  content.
