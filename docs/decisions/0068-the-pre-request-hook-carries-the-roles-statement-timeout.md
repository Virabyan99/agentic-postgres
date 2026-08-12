# 0068 — The pre-request hook carries the role's statement timeout

Status: accepted
Date: 2026-08-12
Session: 5, Run 9
Amends: [0067](0067-a-validated-value-must-reach-the-plane-that-applies-it.md)
Affects: API-LIMIT-001

## Context

ADR 0067 put the manifest's `statement_timeout` on each request role, and the
deployment carries it: `pg_roles.rolconfig` shows `2s` on `anon` and `5s` on
`authenticated`, applied by the bootstrap plane from `database.statement_timeouts`.

A REST request was still unbounded. `API-LIMIT-001` failed against the redeployed
cluster with a 30-second RPC that ran to completion — the same symptom as before
version 7 existed.

**PostgreSQL processes a role's settings only at login.** PostgREST logs in as
the authenticator and reaches the request role with `SET LOCAL ROLE`, which is
not a login. Measured on `pgvector/pgvector:pg18` with controls on both arms:

| | |
|---|---|
| `pg_db_role_setting` for the role | `statement_timeout=2s` |
| **control** — direct `LOGIN` as that role | `2s` |
| login as authenticator, then `SET LOCAL ROLE` | **`0`** |
| `pg_sleep(5)` on that path | completes |
| **control** — the same five seconds after a direct login | `canceling statement due to statement timeout` |

So the value was correct, applied, verifiable in the catalog, and read by
nothing. This is ADR 0067's own lesson one boundary further out: **the far side
of one plane is the near side of the next.**

## Decision

**`app_private.postgrest_pre_request()` reads the role's `statement_timeout`
from `pg_db_role_setting` and applies it to the request transaction**, in
migration 0010.

The hook decides nothing and holds no copy. The value is the one the bootstrap
plane wrote from `database.statement_timeouts`, so there is still exactly one
authority for what a role's timeout is (ADR 0002); this is a carrier across a
boundary PostgreSQL does not carry it across.

Three properties, each of which the measurements chose rather than confirmed:

1. **Before the two early returns.** The documentation role and an anonymous
   request both return early and both can hold a connection. A bound applied
   after them would be a bound on exactly the callers who authenticated.
2. **`SECURITY INVOKER`, no definer helper.** Measured: a plain role reads
   `pg_db_role_setting` directly, so a `SECURITY DEFINER` function would be a
   privilege boundary bought for nothing. It would also have been *wrong*: the
   first draft was a definer function, and `SECURITY DEFINER` makes
   `current_user` the function's **owner**, so the lookup asked for the owner's
   timeout, found none, set nothing, and looked exactly like a hook that had run
   and found nothing to do. It measured green as "no bound configured".
3. **A role with no entry sets nothing.** The platform bounds what the document
   names and invents no bound for what it does not.

## Alternatives

**`db-config = true`.** Measured to work — bounded at 2.0 s — and measured to
work *whether or not* `db-hoisted-tx-settings` names `statement_timeout`, so the
hoist list is not the operative variable and `db-config` is. Rejected: `db-config`
is `false` deliberately, so that the reviewed Compose file is the only authority
on PostgREST's configuration. Turning it on to deliver one value would let the
database override every other one.

**Set the timeout on the authenticator instead.** Measured to work, and for a
reason that disqualifies it: the authenticator *does* log in, so its setting
binds the session. That is one timeout for every request role, and the manifest
declares a timeout per role. Rejected as unable to express the requirement.

**`db-hoisted-tx-settings` alone.** Measured not to work with `db-config=false`:
`statement_timeout` stayed `0` and a 5-second statement completed.

## Consequences

- `API-LIMIT-001`'s time half can pass. It has never passed.
- **One catalog query per request**, on a hook that already runs per request.
  Bounded and indexed, and the alternative was an unbounded statement.
- A tenth released migration. The lock moves from nine to ten and every project
  must be redeployed to apply it.
- The hook is now load-bearing for a *second* property. It refuses the
  documentation role an identity and it bounds every role's statements, and a
  failure in either direction is silent in a different way. Both now have live
  proofs; before this run, one of them had none.
- **What this ADR does not fix**: `PGRST_DB_HOISTED_TX_SETTINGS` is set to `""`
  by the rendered Compose file, and an empty value is read as *unset* — the
  binary reports the full three-setting default either way. It is inert today
  only because `db-config` is `false`. Recorded as D199 rather than repaired
  here, because repairing it means deciding what "off" is for a setting that has
  no off, and that is a separate question from this one.
