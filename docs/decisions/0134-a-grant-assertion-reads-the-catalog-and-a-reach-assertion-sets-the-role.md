# 0134 — A grant assertion reads the catalog, and a reach assertion sets the role

Status: accepted
Date: 2026-08-22
Session: 8, Run 12
Affects: ADR 0041, ADR 0052, ADR 0096, ADR 0116, ADR 0118, D103, D467, D468,
`tests/security/test_session3_authorization.py`

## Context

Session 8's first host gate ran three Session 3 security assertions that had
never executed against a cluster carrying migration 0018. All three failed. Two
were stale allowlists; one was a measurement using the wrong function, and it is
the reason this ADR exists.

## What was measured

On the deployed cluster, directly:

```
nspacl(app_private) =
  object_owner=UC, migration_user=UC,
  anon=U, authenticated=U, api_documentation=U, project_admin=U, agent_reader=U,
  auth_service=U, storage_service=U

app_runtime -> member of authenticated, rolinherit = FALSE
```

**The direct grant is exactly right.** Strip the four service roles and what
remains is `{anon, authenticated, api_documentation, project_admin,
agent_reader}` — precisely `AUTHENTICATOR_REQUEST_ROLES`. Migration 0006's
`REVOKE ALL ON SCHEMA app_private FROM app_runtime` worked and still holds:
**`app_runtime` appears in no ACL entry at all.**

And yet:

```
has_schema_privilege('…app_runtime', 'app_private', 'USAGE')  ->  true
```

`has_schema_privilege` reports a privilege held **directly or by way of
membership in a role that holds it**. Membership — not inheritance. `app_runtime`
is `NOINHERIT`, so it cannot exercise anything of `authenticated`'s without an
explicit `SET ROLE`, and the function reports `true` regardless.

## The part that matters

**Migration 0006 wrote this trap down, for the table twin, and the test written
two sessions later walked into the schema one.** Its comment says:

> *"THE SCHEMA REVOKE IS THE ONE THAT HOLDS. Measured, because the obvious test
> for this migration fails while the property is true:*
>
>     has_table_privilege(app_runtime, 'app.notes', 'SELECT')  ->  true
>     SET ROLE app_runtime; SELECT * FROM app.notes            ->  denied
>
> *Both are correct."*

`has_table_privilege` and `has_schema_privilege` mislead for the same reason, on
the same role, for the same design. The migration named the first and Run 2's
re-derivation used the second — and could not fail on the workstation, because it
is `live_host` and nothing offline runs it (D211–D214).

**`app_runtime`'s reach through `authenticated` is ADR 0041's design**, not a
leak: *"the application runtime role reaches data through `authenticated`, and by
no other path"* (SEC-DBX-002). What was wrong was a proof that could not tell a
grant from a membership.

## Decision

**1. A question about a GRANT is asked of the catalog.**

`pg_namespace.nspacl` is what a migration's `GRANT` and `REVOKE` write. Reading
it answers the question the assertion is actually about — *which roles were
granted USAGE* — and it is **stricter** than what it replaces: membership-derived
reach no longer counts as a grant, so a sixth role acquiring a real grant still
fails, and a role merely being made a member of a request role no longer raises
a false alarm.

The exact-set form stays. `granted ⊇ expected` is still refused (D300).

**2. A question about REACH sets the role and tries it.**

Because the catalog answers only half. `SET ROLE app_runtime` and then naming an
`app_private` object is what the boundary actually means, and it is what
migration 0006 says to assert. It is added rather than substituted: the two
questions are different and each can be true while the other is false.

**3. The two allowlists gain migration 0018's objects, by name, with 0018's
reasons** — not by relaxing the form to a subset.

* `app_private.agent_claims_are_current` joins the functions a request role may
  execute. 0018 grants it to **all five** request roles deliberately: `role` and
  `token_use` are independent claims, so *every combination of physical role and
  hook branch is a reachable request*, and a human token naming the agent role
  was measured being refused `42501 permission denied` instead of `AP401` — D393
  arriving through a missing grant. Its safety is 0013's argument unchanged: it
  takes the whole claim tuple and returns a **boolean**, so it answers no
  question of the form "what may subject X do".
* `api.mcp_agent_context` and `api.owner_activity_report` join the functions
  schema `api` holds. Both are `REVOKE ALL … FROM PUBLIC` and granted to
  `agent_reader` alone (ADR 0118), which is what keeps them out of the OpenAPI
  document an anonymous caller receives.

## Alternatives rejected

**Keep `has_schema_privilege` and add `app_runtime` to the exempt set.** One line,
and it records the symptom as a rule: the next reader would believe
`app_runtime` was *granted* something and go looking for the migration that did
it. There is no such migration.

**Drop `app_runtime`'s membership of `authenticated`.** It is ADR 0041's whole
design, and the application would lose its only path to data.

**Make `app_runtime` the exception by asserting behaviour alone.** The behavioural
arm cannot see a grant to a role nobody exercises — a sixth role granted USAGE
and never used would pass. The catalog arm is what catches that, which is why
both exist.

**Relax the enumerations to "contains".** D300, three times in one session, and
it would pass the next accidental grant forever.

## Consequences

- **A grant and a reach are two assertions**, and a future role that has one
  without the other is visible instead of averaged away.
- `has_*_privilege` is now the wrong tool in this file by decision rather than by
  accident, and D103 already recorded it returning true for objects a role cannot
  read. Migration 0006 said so first, about the table twin.
- The three failures were **all first executions**. Nothing here was a
  regression: two allowlists were simply older than migration 0018, and the third
  had never met the cluster it describes.
