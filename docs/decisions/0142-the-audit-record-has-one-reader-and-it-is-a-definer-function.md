# 0142 — The audit record has exactly one reader, it is a definer function, and reading it is its own scope

Status: accepted
Date: 2026-08-22
Session: 9, Run 7
Affects: ADR 0052, ADR 0079, ADR 0100, ADR 0118, ADR 0134, ADR 0135, D471, D472,
D501, `migrations/templates/0020-agent-audit-reader.sql`,
`schemas/capabilities.schema.json`, `services/auth-api/app/scopes.py`,
`services/auth-api/app/routes.py`, `services/auth-api/app/repository.py`

## Context

Session 9's summary asks for an "admin audit query **and revocation**"
endpoint. **The revocation half already exists** and D472 is what keeps this run
from building a second one: `PATCH /admin/agents/{agent_id}`, gated on
`admin_agents:write`, has revoked agents since Session 6, and migration 0018
already carries the authoritative check that stops the token. Only the query
endpoint is new.

Building it ran into something the plan did not anticipate.

**Migration 0019 created the table and the indexes for a reader it did not
create.** Its own comment, above them:

> The admin query endpoint (Run 7) reads by owner and by agent, most recent
> first. Both indexes exist for that one reader; neither is speculative.

And `services/auth-api/app/repository.py`'s header states the constraint that
omission runs into:

> Fourteen function calls and no table names. `auth_service` holds schema USAGE
> on `app_private` and nothing else.

So `GET /admin/audit` had **no statement it was allowed to send**. This is
CLAUDE.md §6's question 5 — *when a decision is implemented, which of its callers
got it?* — asked of 0019. The indexes got it. The grant did not. **D501.**

## The decision

### One reader, and it is a `SECURITY DEFINER` function in a new migration

`app_private.auth_list_agent_audit(p_agent_id, p_owner_id, p_limit)`, `STABLE`,
`SECURITY DEFINER`, `SET search_path = pg_catalog, pg_temp`, granted to
`auth_service` and to nobody else. **Migration 0020**, because 0019 is released
and released migrations are fix-forward only (ADR 0091).

The alternative was a `SELECT` grant to `auth_service`, and the table's own
`COMMENT` forbids it in as many words:

> Append-only to every request role: no role holds INSERT, UPDATE, DELETE or
> SELECT on it, and the only paths in are the definer functions below.

A `SELECT` grant would have made that sentence false and put a second *kind* of
access beside the definer route. This is 0014's arrangement for the storage
plane and ADR 0052's for the identity registry, applied to the one table Session
9 added.

### The grantee list is one name, and every omission has its own reason

* **Not `project_admin`.** The scope is checked at the endpoint. A *request role*
  holding `EXECUTE` could reach the same rows over PostgREST with no scope check
  anywhere.
* **Not either agent role.** An agent must not read the record that exists to
  attribute it. ADR 0135's stated residual threat is that an agent can add noise
  to its own record under a true identity; reading the record back is not part of
  that threat and must not become part of it.
* **Not `api_documentation`.** The function is not in `api` and could not be
  served — and a grant is the one thing that could change that (ADR 0118).

### Reading the record is its own scope

`admin_audit:read`, in the schema's `$defs/scope` and `$defs/administrative_scope`
and in **`project_admin`'s ceiling alone**.

Reusing `admin_agents:read` was the cheap option and it is the wrong one.
Listing **which agents exist** and reading **what they did** — parameters
included — are different authorities. An operator who should see the roster is
not thereby an operator who should see every audited call, and a reuse would have
made that one decision, taken once, by whoever first granted the roster scope.

**There is no `admin_audit:write` twin**, and the asymmetry is a decision rather
than an omission: the table is append-only, so a write scope would name an
authority nothing can exercise. A test asserts the absence, because the way it
would arrive is somebody completing the pattern.

### The bound on `limit` has one authority, and it is the route

The route validates `limit` into `[1, 500]` and answers **422** outside it. The
function applies `p_limit` and does not clamp.

A second clamp in the database would be a second bound over one rule, and the two
drift the moment either moves — which is D495's shape and D463's. And a clamp is
the wrong mechanism regardless of where it lives: it answers a different question
than the one asked and says nothing about having done so, which is how a caller
comes to believe it read the whole record. A refusal names the bound.

### The filters are not a counterexample to SEC-PARAM-001

`GET /admin/audit` takes `agent_id` and `owner_id`; the agent plane's audit
functions take no identity argument at all (D473). Those are different questions
and the plan says which is which:

* **There**, the caller is an agent and a parameter naming a principal **would
  be** the authority. The absence of any such argument is the whole of
  `SEC-PARAM-001`, and it is structural rather than validated.
* **Here**, the caller is a human administrator already authorized by
  `admin_audit:read` to read the whole record. A filter can only ever return
  **less**. It narrows a permitted read rather than authorizing one.

Stated in the migration, in the route and in a test, because the way it breaks is
somebody generalising one into the other.

## What was measured

`GET /admin/audit` is the **first** endpoint in this service to read a query
string, and `routes.py`'s header already records the sibling defect for bodies:
`json.loads` resolves a duplicate member to its last value, silently. rig7 asked
the same question of the query string, on the locked Starlette 0.49.3, with a
control arm that sent each key once and had to read back one value per key.

| Arm | Observed |
|---|---|
| control, `agent_id=aaa&limit=7` | two pairs, one value each |
| `limit=1&limit=9999` → `__getitem__` | **`"9999"` — last wins, silently** |
| the same, through `getlist` / `multi_items` | **both pairs still there** |
| `Limit=1&limit=2` | **two distinct keys**, not a repeat |
| `limit=` | present, value `""` — not absent |

The consequences are ADR 0143's. What matters here is that the endpoint's
parameters are parsed strictly rather than bound by the framework.

## Consequences

**Migration 0020 exists and is applied on no cluster**, alongside 0019. The trip
now transports two unapplied migrations rather than one, and
`test_the_admin_audit_endpoint_serves_what_the_table_holds` answers 500 rather
than 200 until 0020 lands — correctly and loudly, which is what a
released-and-unapplied migration should look like from a gate.

**`repository.py` has fifteen function calls and still no table names.** The
count is in that module's header sentence because that sentence is what a
reviewer reads to know the surface — and a count that stops being maintained is a
count that stops being read, which is the same failure 0019's indexes had.

**D500 is not closed here.** The `database`-source row still carries no
`request_id`. Closing it means replacing both write RPCs, which is a change to
what the product *writes*; this migration only adds a way to *read* what is
already written. Bundling them would make one migration two decisions. The
deployment test asserting the row's `request_id` **is** NULL stays green and
stays the thing that will fail on the day the repair lands.

**Retention is still decided by nobody.** `app_private.agent_audit` grows without
bound, exactly as secret generations do. A reader is not the place to decide it:
a `DELETE` path would be a second write authority over a table whose append-only
property is stated in its own comment.

**And D503 was found while proving the revocation half.** Migration 0011's
comment says an agent credential *"is `revoked`, which is terminal for that
credential"* and names `SEC-REV-001` as the proof — and
`app_private.auth_set_agent_status` is an unguarded `UPDATE`, so `revoked →
active` answers 200. The two-value enum stops a third state existing; nothing
stops the second transition. Recorded rather than repaired, because Run 7 proves
revocation rather than building it, and a transition guard is a migration and a
product change. The test asserts what the product does and says so.
