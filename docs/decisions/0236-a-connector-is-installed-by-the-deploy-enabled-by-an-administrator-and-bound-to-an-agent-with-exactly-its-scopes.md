# 0236 — A connector is a project artefact installed by the deploy, enabled by an administrator, and bound to an agent that holds exactly its definition's scopes; inbound and scheduled connectors start runs

- **Status:** Accepted
- **Date:** 2026-09-29
- **Session:** 34, Run 1 (D1783, D1795, D1796, D1797, D1798, D1799; rig 34c)
- **Affects:** migration 0036 (`app_private.connector`,
  `connector_enable`, `connector_disable`, `connector_accept`,
  `connector_fire_due`), `schemas/connector.schema.json`,
  `src/agentic_postgres/connector_definition.py`, deploy step 6e, `apg dev`,
  `schemas/capabilities.schema.json` (two administrative scopes),
  `services/auth-api/app/scopes.py`, `bin/connector.sh` / `bin/connector.py`.
- **Related:** ADR 0183 (a profile only narrows — and is per deployment), ADR
  0226/0227/0228/0229 (the loop, the substrate, the definition, a run is the
  agent's), ADR 0232 (approving is an administrative scope), ADR 0237 (the
  signature), ADR 0238 (delivery).

## Context

The stage plan asks for a connector that invokes *"exactly one allowlisted tool
… as the connector's agent identity (created like any agent, under a profile
that names one tool)"*. **There is no per-agent profile.** `mcp.profile` is per
DEPLOYMENT and *"cannot remove a tool"*; the agents table has no profile or tool
column; `POST /admin/agents` takes a name, a description, a role, scopes and a
secret lifetime. An agent is narrowed only by its stored scopes, and one scope
may serve several tools. The worker has exactly one way to call a tool: a step.

**Rig 34c measured whether a `tools/call` needs `meta:read`**, on the rig 33
stack: an `agent_writer` agent with stored scopes exactly `["notes:write"]`
was served `tools/call create_note` (HTTP 200, `isError: false`, one note
written, audit `served` then `committed`) and its `tools/list` named
`create_note` alone. Control: `["meta:read", "notes:write"]` — served the same;
its `tools/list` added `describe_resource` and `list_resources`. **A tool call
needs only the tool's own scope, so `meta:read` does not join the equality.**

## Decision

1. **Three kinds, one file each** under `projects/<slug>/connectors/<name>.yaml`
   (`schemas/connector.schema.json`): `outbound` names `event: name@version`
   and a `retry` (ADR 0238); `inbound` names `workflow: name@version` and a
   closed `body` declaration (ADR 0237); `scheduled` names `workflow:
   name@version`, `schedule: {every_seconds: 60..86400}` and literal `input`.
   An inbound or scheduled connector records the definition's
   `required_scopes` at compile time.
2. **Installed DISABLED by the deploy** (step 6e, after 6d's definitions),
   only when the project's facility is on (ADR 0237). Installation never
   enables.
3. **Enabled by an administrator**, binding an agent: `connector_enable`
   refuses an agent that is not `active` (`agent_not_active`), is bound to
   another connector (`agent_already_bound`), or whose stored scopes are not
   EXACTLY the definition's `required_scopes` (`agent_scopes_differ`, naming the
   difference), and an outbound connector with no endpoint (`no_endpoint`); it
   records who enabled it. `connector_accept` and `connector_fire_due` re-check
   the equality and refuse `agent_scopes_differ` if the agent was widened after
   binding. A one-tool connector is a one-step definition.
4. **Two administrative scopes**: `admin_connectors:read` (`GET
   /admin/connectors`) and `admin_connectors:write` (enable, disable), in the
   administrative enum and in `$defs/scope`; `project_admin`'s ceiling carries
   them by class; **no existing administrator gains either on upgrade** — the
   operator grants them by `PATCH /admin/users`.
5. **An inbound delivery or a due schedule starts a RUN** of the named
   definition as the bound agent, through the substrate's own enqueue. The run
   inherits the scope check, the per-step token, the budgets, the audit and
   the idempotency key; no new code path reaches a tool. **No new token
   claim** (D1795): the approval claim's discipline is what is reused —
   authority built only by the signer from the database, checked at the point
   of use.
6. **The interval table is the connector row's `next_fire_at`.** Enabling sets
   it to `now()`, disabling to `NULL`; `connector_fire_due` enqueues ONE run per
   due enabled scheduled connector and sets `next_fire_at = now() +
   every_seconds` — missed fires coalesce to one.
7. **Six verbs**: `init`, `validate`, `status`, `enable`, `disable`, `key`. No
   `test` verb, and no redelivery: dead letters are visible, not replayable, in
   Stage 4 (D1798).

## Consequences

- The connector holds the least authority that lets it do its one thing, at
  the only place this tree can enforce it — the stored scopes — and a later
  widening of the agent stops the connector rather than widening it.
- An agent is created by a person and bound by an administrator; nothing in a
  committed file names an agent.
- A worker that was down fires a schedule once when it returns, not a backlog.

## Alternatives rejected

- **A per-agent profile** — a second permission model (the stage's §9 failure
  mode).
- **Calling a tool directly from the route** — a second path to a tool, and a
  request held open across the plane's timeout.
- **Binding by agent NAME in the file** — an agent id is per deployment and an
  agent is created by a person.
- **A `test` verb** — one that performs a real delivery would be a lie in the
  vocabulary; one that does not would test nothing.
