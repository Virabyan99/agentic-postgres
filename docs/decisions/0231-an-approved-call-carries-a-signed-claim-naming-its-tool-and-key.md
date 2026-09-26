# 0231 — An approved call carries a signed claim naming its tool and its key, and approval is a control on the governed path

- **Status:** Accepted
- **Date:** 2026-09-26
- **Session:** 33, Run 1 (D1715, D1721, D1722; rigs 33a, 33b)
- **Affects:** `services/auth-api/app/claims.py` (`APPROVAL_CLAIM`,
  `approval_claim`), `service.py` (`issue(extra_claims=…)`,
  `step_token(…, approval_id=…)`), `repository.py`
  (`approval_for_token`), `mcp_tools.py` (`invoke_write`'s approval branch,
  `register_write`), `mcp_errors.py` (a comment), migration 0035
  (`workflow_approval_for_token`).
- **Related:** ADR 0113 (only `auth` signs), ADR 0115 (the plane accepts
  `agent` tokens only), ADR 0179 (the refusal), ADR 0181 (the key claimed in
  the write's own transaction), ADR 0182 (a dry run), ADR 0230, ADR 0232.

## Context

ADR 0230 parks an approval step on the plane's refusal and records a human's
decision. The approved attempt must then reach the plane and be SERVED — but the
plane refuses `requires_approval` unconditionally (`mcp_tools.py:591`), holds no
pool and no credential, and cannot ask the database. What it can see is the
caller's verified claims (`get_access_token().claims`).

**Rig 33a measured the premise**, on a stack of the release plus the example
project's set, PostgREST from the pinned image verifying the auth application's
own JWKS, and both application modes run from the checkout: an agent token
re-signed with the same key and one extra claim `apg_approval: {id, tool, key}`
passes `claims.verify_claims` with the member intact; the plane's own
`AgentTokenVerifier` returns it in `AccessToken.claims` (the same token without
it: no member); `tools/list` over HTTP answers 200 with the same seven tools
for both; PostgREST and the pre-request hook serve `GET /notes` 200 for both.
The same claim signed by a SECOND key under the same `kid` is 401 at the plane
and `PGRST301` 401 at PostgREST.

## Decision

**An approved attempt's ONE step token carries `apg_approval: {"id": <approval
uuid>, "tool": <tool name>, "key": <the step's idempotency key>}`.**

* `AuthService.step_token(agent_id, *, approval_id=None)` builds the claim from
  the DATABASE, through `workflow_approval_for_token(approval, agent)` — the row
  only when it is approved, unexpired and the run's agent is this agent — and
  never from the loop's variables. Zero rows is `AuthenticationFailed`.
* `issue()` gains `extra_claims`, which may not name a required claim (refused
  `InvalidRequest`); the extras are merged before `verify_claims`.
  `/auth/agent-token` and `agent_token` never pass it (an AST proof).
* `claims.approval_claim(payload)` validates the shape (an object with exactly
  `id` a uuid, `tool` and `key` non-empty strings); malformed is a
  `ClaimError`, which the plane reads as the ordinary approval refusal, never a
  500. `REQUIRED_CLAIMS` and the database's literal do not move.
* **The plane serves a `requires_approval` write only when the claim names the
  tool being called AND the idempotency key being presented, and never with
  `dry_run`.** An approved dry run is refused `input_not_permitted`
  (*"an approved call is not rehearsed"*). Every other case raises the existing
  refusal byte-for-byte — same token, same detail, same reason, audited — so
  AGT-APPROVE-001's proofs are the unchanged contract.

Binding the key means the claim authorises ONE write: a replay of that key is
re-read by ADR 0181, not a second write, and any other write inside the token's
life (at most 900 s + 30 s skew) is refused.

**Approval is a control on the GOVERNED path — the plane and workflows — not in
the database.** Rig 33b measured it: with the agent's own token,
`POST /rpc/set_note_embedding` sent DIRECTLY to PostgREST answered **200 and
wrote the row**, because the example project grants the function to
`agent_writer` and its SQL checks no approval. The same call through the plane
was refused `approval_required` (HTTP 200, `isError`), one `refused` audit row,
no row written. That posture predates this session (ADR 0179, D870); this ADR
states it as `THR-APPROVAL`'s residual rather than claiming more than the plane
enforces. The database half is priced, not built: a release-owned
`api.require_approval(p_tool)` a gated project RPC calls first, reading the
claim from `request.jwt.claims`.

**Two belts keep a rehearsal from writing through an approval.** Rig 33b also
measured that `set_note_embedding` has no dry-run branch: the direct call with
`Idempotency-Key` and `Dry-Run: true` — the headers the plane sends — answered
200 and WROTE the row, although its capability declares
`supports_dry_run: true`. Today that is unreachable through the plane, because
the approval refusal precedes the dry-run check. Once an approved claim lets the
call through it would not be, so (1) a dry-run run never requests approval (the
loop finishes an approval step `dry_run` without a call) and (2) the plane
refuses an approval claim together with `dry_run`.

## Consequences

* Nobody but the signer can mint the claim, and the signer mints it only from a
  decided row it reads itself.
* The example project's missing dry-run branch is a defect in that project's
  SQL, recorded for whoever next moves its set (D1722).
* An operator who needs approval enforced against a direct PostgREST call must
  either withhold the project RPC's grant from `agent_writer` or take the priced
  database half.

## Alternatives rejected

* **The plane asking the database through a new `api` RPC.** Rejected: it moves
  the `api` contract and every generated client for a check the signer can make
  when it mints.
* **A header or a tool argument.** Rejected: the agent's to set.
* **Enforcing approval in each project's SQL now.** Rejected for this session:
  it moves the example project's SQL, the project lint's allowlist and a
  release function; priced instead.
