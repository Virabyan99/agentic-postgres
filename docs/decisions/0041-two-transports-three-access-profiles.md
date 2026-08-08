# 0041 — Two transports, three access profiles

Status: proposed
Date: 2026-08-08
Session: 4, Run 1
Affects: DBX-001, DBX-002, DBX-003, DBX-005, SEC-DBX-002

Accepted in Run 2, the run that bumps the output schema.

## Context

Session 4 delivers a pooled transport for application traffic and a direct
transport for migration and operations. Three ways of reaching a database result
from two transports, because the direct transport is used by two different
roles for two different purposes:

| Access profile | Transport | Role | Intended use |
|---|---|---|---|
| `runtime_pooled` | PgBouncer | the project's app-runtime role | Prisma Client, Node `pg`, Psycopg, applications |
| `runtime_direct` | PostgreSQL | the project's app-runtime role | Prisma Studio, diagnostics, pooling comparison |
| `migration_direct` | PostgreSQL | the project's migration role | dbmate, Prisma Migrate, privileged `psql` |

The output schema already anticipated the transports. `$defs.endpoint` carries
`available` in its `status` enum and constrains fields only when `unavailable`,
so flipping `database.pooled` and `database.direct` to `available` with a real
host, port, url and `password_secret_ref` needs no change to that definition at
all. Session 2 wrote it that way for this session.

What it cannot express is the third row. One `endpoint` object carries one URL
and one `password_secret_ref`, and `runtime_direct` and `migration_direct` are
the *same* transport reached with *different* credentials under *different*
authority. Serialising them as two endpoints would say the project has three
transports, which is false and would make the port allocator wrong.

## Decision

**`pooled` and `direct` stay the transports. Access profiles are a separate
object that names a transport, a role and a secret reference.**

1. `database.access_profiles` is added, keyed by profile name, each entry naming
   its transport (`pooled` | `direct`), its role, its `password_secret_ref`, and
   the authority it carries. The endpoint objects keep describing *where*; the
   profiles describe *as whom*.

2. Output schema version goes to **4** on both document kinds, with a `v3 → v4`
   function in `output_migrations.py` and a committed
   `tests/fixtures/outputs-v3.json` — the full price D40 set for a schema bump,
   paid rather than avoided. Migration never produces a *deployed* document.

3. `available_from_session` stays 4 and is now satisfied rather than pending.

4. Role names are not written here. They are derived by `naming.py` from the
   project key, the same rule D38 set for Session 3; an ADR that spelled them
   out would be a second naming authority.

5. The pooled transport rejects the migration role. Developer tooling defaults
   to `runtime_direct`; `migration_direct` is always an explicit choice.

## Consequences

A reader of a deployed document can answer "what may this credential do" without
consulting the code, because authority is a field rather than an inference from
a role name.

Three profiles over two transports means the number of secrets per project rises
by two, and every one of them has to be reachable by exactly one consumer. That
cost lands in Run 3 and is the reason ADR 0033's rendered grant surface exists.

The alternative shape — one endpoint per profile — would have been simpler to
serialise and would have made `DBX-PORT-001` unprovable, because "two projects
never share a port" needs a transport count that does not move when a profile is
added.

`app_runtime` is a server-application credential, not an end-user account.
Possession is equivalent to possession of a trusted application server's
credential, and it permits controlled impersonation through request context. It
is never distributed to browsers, mobile clients or untrusted end users. That
sentence belongs in the operator guide as well as here.

## Alternatives considered

**A fourth endpoint, `migration`, beside `pooled` and `direct`.** Rejected: it
duplicates a host and port that must stay equal by construction, and two fields
that must stay equal are two fields that will eventually differ.

**One endpoint with a list of credentials.** Rejected: it makes the common
case — "give me the URL for this profile" — a search rather than a lookup, and
every consumer would reimplement the search.

**Defer profiles to Session 5 and ship two endpoints now.** Rejected: the
migration/runtime split is the security property Session 4 is for. Shipping the
transports without it would mean the first client to connect would do so as
whichever role the single endpoint named, and that role would have had to be the
privileged one.
