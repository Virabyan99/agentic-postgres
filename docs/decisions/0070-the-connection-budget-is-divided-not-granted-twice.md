# 0070 — The connection budget is divided, not granted twice

Status: accepted
Date: 2026-08-13
Session: 5, Run 10
Settles: D161
Amends: [0067](0067-a-validated-value-must-reach-the-plane-that-applies-it.md)

## Context

Role activation was supposed to set "an explicit `CONNECTION LIMIT` fitting the
queried budget". It set one for `app_runtime` and none for the API's
authenticator, and D161 recorded why: half the arithmetic had nowhere to come
from, and the other half was already spent.

**Already spent.** `app_runtime` was given `max_connections - superuser_reserved
- 5` — everything the server had, minus operational headroom. A ceiling for the
API *on top of* everything is two limits that sum past what the server will hand
out, which is a budget that looks computed and is not.

**Nowhere to come from.** The rendered document carried no API figure at all, and
the bootstrap plane reads only that document. It could not see the declared
`api.rest.pool_size` even to add it up.

So the honest intermediate state was no limit at all, and that is what shipped:
the authenticator bounded by `max_connections` like every other role, with
nothing claiming otherwise.

## Decision

**The two limits are computed together, from one query, and the application gets
what is left.**

    available   = max_connections − superuser_reserved_connections   (live, queried)
    api         = database.api_connection_budget                     (published)
    application = available − api − OPERATIONAL_CONNECTION_HEADROOM

Three properties, and the third is the one that took the decision:

1. **One query, both limits.** `connection_limits` returns the pair, so neither
   can be applied without the other having been computed. The failure D161
   describes — one ceiling moved without the other — is unrepresentable rather
   than merely discouraged.
2. **The API's figure is published, not recomputed.** Outputs version 8 adds
   `database.api_connection_budget`, written by `rendering` from
   `config.postgrest_connection_budget` — the same call the manifest-side budget
   check reasons about. One answer, in one place (ADR 0002 applied to a number).
3. **The application's figure is not published, deliberately.** It depends on
   what the *live* server reports, and a rendered document naming it would be
   publishing a guess about a server nobody has queried yet (D94). The rendered
   document carries the manifest's commitment; the plane that can ask the server
   does the subtraction.

`app_runtime` gets the remainder rather than a chosen number because it serves
both the pooler's server-side pool **and** the direct access profile. A ceiling
of `database.pool_size` would refuse a developer's direct session whenever the
pooler was busy, and any allowance added on top would be a number nobody
measured.

## Alternatives

**Give `app_runtime` `database.pool_size` and the API its budget, leaving the
rest unallocated.** Rejected: it invents a second reserve nobody named, and it
breaks the direct transport under load — the failure would look like a
credential problem and be a ceiling.

**Read the manifest in the bootstrap plane.** Rejected on ADR 0002 and D102: the
bootstrap reads the rendered document precisely so that SQL and Compose cannot be
derived from two readings of one manifest. The document gaining a field is the
consistent answer; the plane gaining a second input is not.

**Compute the API's figure in the bootstrap from `pool_size`.** Rejected as a
second authority on one number. `config.postgrest_connection_budget` already
adds the reservations, and the manifest was checked against that sum; a
re-derivation would agree today.

**Leave it as it was.** Rejected because the state is not neutral: with no limit,
one misconfigured client holding connections through the API can exhaust the
cluster for the application, and the deployed document says nothing about it.

## Consequences

- **`app_runtime`'s limit drops.** On the example manifest — `max_connections`
  50, `superuser_reserved` 3, `api.rest.pool_size` 10 — it goes from 42 to
  **29**, with the API at 13 and 5 held back. That is a real reduction, and it is
  the point: 42 was never a budget, it was the absence of one.
- **The pooler still fits.** `database.pool_size` is 20, so 29 leaves 9 above the
  pooler's server-side pool for direct sessions.
- Deployed documents at version 7 stop validating until each project is
  redeployed — the same cost versions 6 and 7 imposed, anticipated by ADR 0053.
- **A cluster too small for the sum now refuses at bootstrap** rather than
  handing out limits that oversubscribe. A negative limit means *unlimited* to
  PostgreSQL and `0` means *reject every login*, so raising is the only honest
  failure — both are values it would accept and neither is what the arithmetic
  meant.
- D161 is closed. The placeholder comment that recorded it is gone from
  `bin/postgres-bootstrap.py`, and a test asserts it stays gone.
