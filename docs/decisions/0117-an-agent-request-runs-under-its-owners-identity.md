# 0117 — An agent request runs under its owner's identity

Status: accepted
Date: 2026-08-19
Session: 8, Run 2
Affects: ADR 0029, ADR 0052, ADR 0068, ADR 0078, ADR 0115, D270, D393, D397,
D398, `migrations/templates/0018-agent-read-plane.sql`,
`migrations/templates/0003-owner-scoped-tables-and-forced-rls.sql`

## Context

Every row policy in migration 0003 keys on one value:

```sql
CREATE POLICY notes_owner_select ON app.notes
  FOR SELECT USING (owner_id = app.current_user_id());
```

and `app.current_user_id()` reads the transaction-local GUC `app.user_id`, which
`app_private.postgrest_pre_request` establishes from the token's `sub`.

An agent's `sub` is an **agent id**. `app_private.agents` is a separate registry
from `app_private.users`, and no note or task has ever been owned by an agent —
`app.notes.owner_id` names a human. So the hook as 0013 left it does one of two
things to an agent request, both wrong: if it establishes `sub`, the agent sees
**nothing**, because no row is owned by it; and before it could do even that,
`auth_claims_are_current` reads `app_private.users`, finds no such subject, and
refuses the request outright.

The runbook proposed adding an immutable `data_owner_id` to each agent,
backfilled from a `created_by` column. **`app_private.agents.owner_id` has been
`uuid NOT NULL REFERENCES app_private.users (id)` since migration 0011** (D398),
with the comment *"Non-human subjects, owned by a human one."* There is no
`created_by` and nothing to backfill.

## What was measured

The rig described in ADR 0116 — the locked image, all eighteen migrations as
`migration_user`, every request as the authenticator with `SET ROLE`. The arms
that decided this ADR:

| arm | result |
|---|---|
| the hook establishes `app.user_id` = the agent's **owner**, `app.agent_id` = the agent | as designed |
| the agent reads exactly its owner's notes | `a1,a2` — a second owner's `b1` absent |
| **control:** the owner's own human token returns the same rows | `a1,a2` |
| the agent's report equals the rows the agent itself can read | `2 2 1 1` both ways |
| **control:** and equals what its owner reads with a human token | `2 2 1 1` |
| **control:** a different owner reads different numbers | `1 1 1 0` |
| a stale `authz_version` is refused | `AP401` |
| `credential_version` 1 on an agent token is refused | `AP401` |
| an agent token naming a human role is refused | `AP401` |
| an agent token with a narrowed scope set is refused | `AP401` |
| an unknown agent id is refused | `AP401` |
| **control:** the same request with unmodified claims still succeeds | serves |
| an agent still cannot reach `app_private.agents` or `app.notes` directly | permission denied |

**No policy was changed and none needed to be.** The isolation an agent gets is
the isolation its owner already had, produced by the same eight policies, and
that is the property this ADR exists to make deliberate rather than incidental.

The **cross product** is the measurement that changed the design, and it is
recorded in ADR 0116: `role` and `token_use` are independent claims, so a human
token naming an agent role and an agent token naming a human role are both real
requests. Both must be refused by the hook's own `AP401`, not by a missing
`GRANT`.

## Decision

**An agent request establishes its OWNER as `app.user_id`.** An agent sees
exactly what its owner sees, through policies that do not move.

**`app.agent_id` is set beside it, and no policy reads it.** It exists so a
function can tell *which* principal asked — `api.mcp_agent_context()` is its one
consumer — and it is deliberately not an authorization input. A GUC that both
identifies and authorizes would make every future policy a place to get the
distinction wrong.

**The discriminator is `token_use`, not the physical role.** Branching on
`current_user` would work today, because the authenticator's memberships happen
to line up with the two registries. **That is the mechanism D393 was**: a
boundary standing on a correlation, changing silently the day the correlation
stops holding. `token_use` is minted as a discriminator and is the only claim in
the token that is one — Run 1 measured an agent token and a human token carrying
the same twelve claims, the same issuer, the same audience and the same key.

**`credential_version` must be 0 on the agent branch.** D397 made `0` a value
rather than an absence so that "not a human" could be read rather than inferred.
The hook checks it instead of trusting it, so a token claiming to be an agent
while carrying a human's credential version is refused.

**`agent_claims_are_current` returns the owner, not a boolean.** 0013's human
twin returns a boolean because the hook already holds the identity it is about
to establish. Here it does not, and the answer has to carry it. The disclosure is
bounded by the same rule: a caller learns one uuid, and only by presenting a
correct guess of the agent id, its role, its exact sorted scope set **and** its
current `authz_version`. `owner_id` is `NOT NULL`, so `NULL` means "no agent
matched" and can mean nothing else.

**Migration 0018 redefines the hook from 0013's body**, and the diff is
mechanical rather than a claim: **zero statement lines removed, twenty-one
added**. D270 is why — the hook is defined in four files and only the last one
runs, so a body assembled from an older version silently deletes the
statement-timeout carry, the documentation-role clause and the current-state
comparison.

## Alternatives rejected

**Give agents their own RLS policies keyed on `app.agent_id`.** Eight more
policies over two tables, saying the same thing the eight existing ones say,
that would have to be kept in step forever. Every future table would need two.
And it would make "an agent sees its owner's rows" a property of policy text
rather than of one line in the hook.

**Own the data with the agent.** `app.notes.owner_id` would have to accept
either registry, which means dropping a foreign key or adding a discriminated
one, and deleting an agent would then orphan or destroy the rows it created.
D392 is the nearby lesson: `agents.owner_id` is `NO ACTION` on purpose, so an
agent blocks its owner's deletion rather than the reverse.

**Establish `sub` and let the agent see nothing.** Technically safe, and it
would make every agent tool return zero rows while every test passed. A read
plane that reads nothing is a plane whose isolation nobody has measured.

**Branch on `current_user`.** Rejected above; it is D393's mechanism.

## Consequences

- **Revocation reaches an agent on the next request**, not at its token's
  expiry: `authz_version` is compared per request, and rotating an agent secret
  moves it (0013's `auth_rotate_agent_secret`).
- **An agent inherits its owner's data reach and nothing else.** It does not
  inherit the owner's *scopes* — those are the agent's own, from
  `app_private.agents.scopes`, and `objects:*` is not in the agent vocabulary at
  all (ADR 0100).
- **Deleting an owner is blocked while an agent exists** (D392, `NO ACTION`), and
  that is now load-bearing rather than incidental: an agent whose owner vanished
  would be a principal with an identity and no data.
- Session 9's write tools inherit this identity unchanged. A row an agent
  creates is owned by the owner, which is what makes a write tool one-to-one
  with the human RPC it maps to.
