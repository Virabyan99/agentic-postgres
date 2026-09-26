# 0232 — Approving is an administrative scope, and the owner of a run may not approve it

- **Status:** Accepted
- **Date:** 2026-09-26
- **Session:** 33, Run 1 (D1717, D1718; D1638 and D1704 as precedent)
- **Affects:** `schemas/capabilities.schema.json` (`$defs/administrative_scope`
  and `$defs/scope`), `services/auth-api/app/scopes.py`
  (`ADMIN_WORKFLOWS_APPROVE`), the four admin workflow routes, migration 0035
  (`workflow_decide_approval`'s owner check), and the four proofs that pin the
  scope sets exactly (`test_scope_registry.py`, `test_scope_vocabulary.py`) plus
  two fixture lists.
- **Related:** ADR 0114/0229 (one token use per route set), ADR 0200 (the
  vocabulary in the lock), ADR 0217 (a second principal is a scope set the
  existing verifier checks), ADR 0230, ADR 0231.

## Context

The stage plan asks for *"a new scope `workflow_approve`"* and for *"the proof
that the requester cannot hold it for its own run"*. Every scope in the tree is
`resource:verb` (`test_scope_registry.py:91`), and
`api_surface.reserved_resource_names()` reserves the part before `:` of every
administrative scope as a relation name no surface may use. The administrative
class is an enum in the capability schema, not derived from a surface, and only
`project_admin` carries it (`scopes.py:106`).

An agent cannot reach an `/admin/*` route at all: `authenticate` accepts
`token_use: access` only, and `require_scope` is typed to a human `Principal`.
But an agent's OWNER is a human, and `POST /admin/agents` makes the creating
administrator the owner — so an administrator who created an agent holds a
human token that could approve that agent's run.

## Decision

**The scope is `admin_workflows:approve`**, in the administrative class. It
reserves the relation name `admin_workflows`. It moves every compiled lock's
`vocabulary.administrative` (not `tools_sha256`), so a deploy recreates `auth`
and `mcp` (ADR 0200 §2). **The four proofs that pin the exact sets move to the
new exact sets in the same commit** — a set equality with one more member is a
stricter proof, never a subset check — and the two fixture lists gain it.

**An existing administrator does not gain it.** `bin/auth-admin.py` grants
`permitted_scopes("project_admin")` at bootstrap only; the operator grants the
scope with `PATCH /admin/users/{id}` (role and scopes together), and the
operator guide says so.

**Three controls, each proved:**

1. The four admin workflow routes call `authenticate` + `require_scope`, so an
   agent token is 401 — the requester cannot hold the scope for its own run
   because it cannot hold a human token at all.
2. `workflow_decide_approval` refuses the run's owner (`PT403`,
   `approver_is_owner` → 403).
3. The scope is `project_admin`-only by ceiling.

**Reading provenance is `admin_audit:read`, not this scope** (ADR 0234): an
auditor reads; an approver decides.

## Consequences

* D1638 already keeps a tenant's agent's owner apart from an administrator; the
  owner rule makes the same true for an administrator's own agents.
* The trip's approver is created with the scope; an administrator without it is
  refused and the approval stays pending (a live proof).

## Alternatives rejected

* **`workflow_approve`, as the brief wrote it.** Rejected: no colon breaks the
  grammar every scope follows and would reserve a nonsense relation name.
* **A data-class scope.** Rejected: an `authenticated` user or an agent role
  could then hold it.
