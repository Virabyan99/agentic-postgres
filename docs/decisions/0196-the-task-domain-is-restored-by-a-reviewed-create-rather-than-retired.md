# 0196 — The task domain is restored by a reviewed create, because retiring it is blocked

- **Status:** accepted
- **Date:** 2026-09-10
- **Session:** 19, Run 6 (D1055, D1058)
- **Related:** **ADR 0003** (the example domain; operation 4 is a status
  transition, not a second create), **ADR 0048** (what the migrations shipped
  versus what four documents described), **ADR 0116** (the compare-and-swap
  activated), **ADR 0127** (the roster is enumerated, not discovered),
  **ADR 0183 / D933** (a disabled write capability does not deploy),
  **ADR 0050** (nothing exists in `api` which the reviewed contract does not
  name).

## Context

`0005` created `api.create_task`. `0007` revoked and dropped it, correctly:
ADR 0048 found that the shipped surface carried a second create which ADR 0003
never sanctioned, and operation 4 was specified as a narrow status transition.
The removal was right. **Nothing replaced it**, and nothing noticed, because
nothing in this repository has ever needed a task to exist.

An outsider building an application on 1.0.0 noticed, and reported that the
only role permitted to insert a task is `object_owner` — `NOLOGIN`, reachable
only by migrations.

### The premise, measured rather than accepted

That claim looked contradicted by the tree. `0003` line 90 reads:

```sql
-- The runtime identity works on these tables directly; it is granted USAGE on
-- `app` in 0001. …
GRANT SELECT, INSERT, UPDATE, DELETE ON app.notes, app.tasks TO {{app_runtime}};
```

So rig 19 was run: a throwaway cluster on the pinned image, all thirty
released migrations applied, four probes with controls.

| Probe | Result |
|---|---|
| `api.create_task` functions in the catalog | **0** |
| Holders of `INSERT` on `app.tasks` | **`object_owner` only** |
| `app_runtime` inserting, having set `app.user_id` itself | `ERROR: permission denied for schema app` |
| `app_runtime` inserting without the GUC (control) | same refusal, so the first probe proves reachability and not policy |
| `authenticated` inserting, GUC set | `ERROR: permission denied for schema app` |
| Rows in `app.tasks`, and in `api.tasks` | **0**, and **0** |

The grant at `0003` is inert: `0006-app-runtime-least-privilege.sql` revokes
`ALL ON ALL TABLES IN SCHEMA app` **and** `ALL ON SCHEMA app` from
`app_runtime`. The finding's conclusion holds, for a reason neither it nor the
first reading of the tree gave: **no role that any service connects as can
create a task, on any surface this product publishes.**

The consequences are not cosmetic. `query_resource` over `tasks` returns an
empty set on every deployment and cannot do otherwise. `update_task_status`'s
compare-and-swap — argued for in ADR 0003, activated in ADR 0116 — has never
run against a row outside a fixture. Two of the agent plane's six tools address
a table that is permanently empty, and the published surface therefore names a
resource the world cannot reach: ADR 0050's invariant met from the opposite
direction.

## Decision

**Restore a reviewed `api.create_task`, under the same review ADR 0048
applied.** Not `0005`'s function returned: a new migration, fix-forward, whose
entry in the reviewed contract is made deliberately rather than inherited.

**The alternatives are not symmetric, and the other one is blocked.**
Retiring the domain looks equally available and is not:

- Dropping the `query_tasks` *capability* is fine. The roster stays six, because
  `query_notes` and `query_tasks` are two capabilities behind the one tool
  `query_resource`.
- `update_task_status` **is a tool.** Removing it leaves five, and
  `mcp_lock` refuses at startup: `if names != EXPECTED_TOOL_NAMES: raise
  LockError(...)`. That is **D933**, recorded at Session 16 and still open.

So retirement costs restoration's work *plus* D933's. That asymmetry is the
decision's actual argument, and it is also the second thing now blocked on
D933 — which is the case for repairing it in Stage 3, beside the closed agent
scope vocabulary (D1056).

## Consequences

- **This cannot be completed offline.** A new published object changes the
  reviewed contract, and `bin/api-contract.sh --update` reads `routes.rest.url`
  from a *deployed* document: the surface is served only once the migrations
  are applied, and the migrations are applied by the deploy. So the migration,
  the contract entry, the re-frozen lock and the recaptured snapshot belong to
  one sitting that ends in a deploy on alpha or beta. Shipping the migration
  without the recapture would leave the contract suite red for everyone, which
  is exactly the state D1039 was repaired to explain rather than to normalise.
- The migration is specified and not yet written, deliberately. What it must
  do: create `api.create_task(p_title text, p_note_id uuid DEFAULT NULL)`
  `SECURITY DEFINER`, `SET search_path = pg_catalog, pg_temp`, deriving
  `owner_id` from `app.current_user_id()` and never accepting it; raising
  `PT401` with no identity and `PT404` for a note that is absent or another
  owner's; `REVOKE ALL … FROM PUBLIC` then `GRANT EXECUTE … TO {{authenticated}},
  {{agent_writer}}`; ending in `NOTIFY pgrst, 'reload schema'`. `0005`'s body
  is the reference for the shape and not for the grants.
- **`0003`'s comment has been false since `0006`** (D1058). It tells a reader
  that `app_runtime` "works on these tables directly", and it does not. It
  cannot be corrected in place: a released template's bytes are the unit
  `verify_lock` checks, so editing a comment changes a digest the lock records.
  A stale comment inside a released migration is therefore fix-forward like
  everything else here, and it is recorded rather than repaired.
- Until the sitting happens, the product continues to publish `tasks` and
  `update_task_status` against a table nothing can populate. That is the state
  1.0.0 shipped; this ADR records that it is now known rather than fixed.
