# 0242 — Approval is enforced in the database by a guard in `app` that a gated project function calls first, and a human's own write passes it

- **Status:** Accepted
- **Date:** 2026-09-30
- **Session:** 35, Run 1 (D1867–D1872; rig 35a)
- **Affects:** `migrations/templates/0037-approval-gate.sql` (Run 2:
  `app.require_approval(p_tool text)`),
  `projects/example/migrations/templates/0004-approval-in-the-database.sql`
  (Run 2), `src/agentic_postgres/approval_gate.py` (Run 2: `unguarded`),
  `bin/mcp-contract.sh check --project`, `bin/migrate.sh propose` (Run 3), the
  render's approval-gate line; `docs/threat-model.md` `THR-APPROVAL`.
- **Related:** ADR 0230–0232 (the approval, its claim, who decides), ADR 0235
  (`app.emit_event`: a release function in `app` granted to nobody), ADR 0181
  (the idempotency key), ADR 0182 (the dry run), D1721, D1722, D1779.

## Context

Since 1.11.0 a capability that declares `requires_approval` is refused by the
agent PLANE until a person decides, and an approved call carries a signed
`apg_approval {id, tool, key}` claim that only `auth` adds, only from an
approved decision it reads itself (ADR 0231). **The database never looked.**
Rig 33b measured an agent holding `note_embeddings:write` calling
`POST /rpc/set_note_embedding` through PostgREST with its own token: 200 and a
written row (D1721). On 2026-09-29 the operator assigned the database half to
Session 35.

Session 33 priced it as `api.require_approval`. An `api` function is either
granted to a request role — and then it is `POST /rpc/require_approval`, an
endpoint — or granted to nobody, and then `test_api_migrations.py` refuses it
as a function no role can call; D1779 measured exactly this for the emitter.
A project body may not name `app_private` (the project lint's first forbidden
pattern), so the guard cannot live there either.

**Rig 35a measured every premise on one stack** — `apg dev up` over the
example project, the pinned PostgREST verifying the auth application's own
key set, the plane from the checkout, and the REAL loop
(`workflow_worker.process` with `AuthService.step_token`) driving
`tasks-approval` to a park on the plane's own `approval_required`, a second
administrator's approval, and the approved call:

- The approved step token's `apg_approval` arrives inside
  `current_setting('request.jwt.claims')` exactly as minted (`{id, key,
  tool}`), and the plane's `Idempotency-Key` header arrives in
  `request.headers` as `idempotency-key`, equal to the claim's key. The plane
  forwards the agent's own token (it holds no signing key), so the approved
  path needs no plane change.
- A prototype guard with this ADR's body, called first by a definer twin of
  the gated function: the agent's OWN token → **403
  `{"code":"PT403","details":null,"hint":null,"message":"AP403:
  approval_required"}`**, 0 rows written, with or without a key. The ungated
  twin, same body without the guard → **200 and a row** (rig 33b reproduced:
  the control). The owner's human token → 200, `app.agent_id` empty. The
  approved claim with the matching key → 200 and the row records the claim
  and key; a claim with another key, or no key → 403, 0 rows; a malformed key
  → 412 `PT412` from `app_private.agent_idempotency_key()` itself. The same
  claim with the decision set `rejected` or `expired`, or its run
  `cancelled` → 403, and 200 again once restored; after the run SUCCEEDED →
  403, and `step_token` itself refuses to mint for it.
- Installed as the first statement of `api.set_note_embedding` itself
  (`CREATE OR REPLACE` as the owner; grants kept for `authenticated` and
  `agent_writer`): the agent's own token directly → 403, 0 embeddings; the
  owner directly → 200; the approved call THROUGH THE PLANE → served, one
  embedding; the loop then finished the run `succeeded`. The plane's audit
  reads `refused approval_required` (the park), `served`, `served`, `refused`
  (the agent's own token through the plane), `served` (the loop).
- No login or request role — `authenticated`, `agent_writer`,
  `agent_reader`, `anon`, `auth_service`, `postgrest_authenticator`,
  `project_admin` — may execute the prototype (`has_function_privilege`
  false; `42501 permission denied for schema app` when tried), and PostgREST
  answers `POST /rpc/rig_require_approval` with `404 PGRST202`: it cannot
  address a function in `app`.

## Decision

1. **Migration 0037 creates `app.require_approval(p_tool text) RETURNS
   void`**, `LANGUAGE plpgsql`, `SECURITY DEFINER`, `SET search_path =
   pg_catalog, pg_temp`, created as the object owner, `REVOKE ALL … FROM
   PUBLIC`, **granted to nobody**. It is callable only from a definer function
   running as the owner — a reviewed project RPC — exactly as `app.emit_event`
   is (ADR 0235). No table, column, enum or `api` object moves.
2. **Its body.** With no `app.agent_id` for the transaction the caller is a
   HUMAN and it returns: approvals are made BY people, and a person's own
   write through the reviewed surface was never what an approval gates.
   Otherwise it reads `request.jwt.claims -> 'apg_approval'` and
   `app_private.agent_idempotency_key()` (whose own `PT412` for a malformed
   header stands) and refuses unless the claim is an object, its `tool` is
   `p_tool`, the key is present and equals the claim's `key`, its `id` is a
   uuid, and an `app_private.workflow_approval` row with that id is
   `approved`, for that tool and that key, on a `running` run of THIS agent —
   the signer's own predicate (`workflow_approval_for_token`) plus the tool and
   the key. **Every refusal is one sentence, `AP403: approval_required`,
   SQLSTATE `PT403` (HTTP 403)**; it never says which member failed.
3. **The example set's `0004-approval-in-the-database.sql`** replaces
   `api.set_note_embedding` with 0003's signature, `search_path` and body, and
   ONE new first statement, `PERFORM app.require_approval('set_note_embedding');`.
   The signature is unchanged, so the grants and the reviewed surface stay.
4. **The approval-gate check** (`approval_gate.unguarded`): for every tool
   with `requires_approval: true` whose operation is `/rpc/<name>` and whose
   `api.<name>` the project set defines, the function's final body's first
   statement after `BEGIN` must be exactly that `PERFORM`. It REFUSES in
   `bin/mcp-contract.sh check --project` and in `propose`, and REPORTS at
   render — never refusing there. A gated tool whose function is a RELEASE
   function is reported `release_function` and never refused.

## What it does not cover, and says so

- **A profile-added approval on a release tool** (`project.second.example.yaml`
  on `update_task_status`) stays a plane control: the database cannot read a
  deployment's profile (D1869).
- **Idempotency** (D1871). Measured: the same approved claim and key called
  twice writes twice (the rig's twin recorded two rows; through the plane the
  upsert kept one embedding). The guard binds a call to a decision, a tool and
  a key; it does not consume the decision, because a consumed decision would
  turn the worker's own crash replay (D1646) into a terminal step failure and
  a compensation.
- **A human's `Dry-Run` header** (D1870): an agent's direct call — dry or not
  — now stops at the guard; a person's still writes. `app.request_is_dry_run()`
  stays priced, not built.

## Alternatives rejected

- **`api.require_approval`.** Forgeable over `/rpc` when granted, refused by
  the `api` grant guards when not (D1779's measurement).
- **Withholding the RPC's grant from `agent_writer`.** It would stop the
  approved path too: the plane calls PostgREST AS the agent.
- **Consuming the approval on first use.** D1871.
- **Refusing an unguarded gated function at render.** An upgrading project
  whose manifest rendered yesterday would stop rendering today — an
  invalidated manifest, a MAJOR class (ADR 0162). The render reports; the
  workstation's `check --project` and `propose` refuse.

## Consequences

- A project author who marks an RPC `requires_approval` writes one line first
  in its body, and the workstation refuses the set until they do.
- THR-APPROVAL's residual becomes *"since 1.13.0 a project's gated RPC refuses
  an agent's direct call in the database; a profile-added approval on a
  release tool remains a plane control; the guard does not make the project
  function idempotent"* (rewritten in Run 2, when it becomes true).
