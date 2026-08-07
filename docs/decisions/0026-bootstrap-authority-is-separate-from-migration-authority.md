# 0026 — Bootstrap authority is separate from migration authority

- **Status:** Accepted
- **Date:** 2026-08-07
- **Session:** 3
- **Affects:** DBX-MIG-001, SEC-DB-001, SEC-OWNER-001

## Context

Two different things have to happen to a fresh cluster, and they need different
amounts of authority.

Creating the thirteen roles, the schemas, the `extensions` schema and the
pgvector extension, the identity sentinel, and the database-level
`CREATE`/`TEMPORARY`/`CONNECT` hardening requires an identity that can create
roles and alter the database. Applying migrations requires authority over the
objects the migrations touch, and nothing else.

The obvious implementation gives both jobs to one identity, because that is one
credential to materialize instead of two and one connection path instead of two.
The constraint that makes it wrong is what dbmate is: a tool that executes SQL
from files which are, by design, added to every session. An identity that can
`CREATE ROLE` and is also the identity running arbitrary migration SQL means
every future migration is a role-creation primitive, and the blast radius of a
mistake in a migration is the whole cluster rather than one schema.

The second constraint is reachability. Bootstrap has to run before any service
exists and must not be reachable by any service that exists afterwards. A
migration plane, by contrast, has to be reachable from the project network,
because that is where dbmate runs.

## Decision

Two planes, distinguished by authority, transport, and lifetime.

**The cluster bootstrap plane** is root-controlled and container-local. It
connects over the Unix socket as OS user `postgres`, and it is not reachable
over any network by any runtime service. It creates or verifies the thirteen
roles and their membership options, the identity sentinel, `app_private`, the
dbmate table, the ledger table, the `extensions` schema, the pgvector extension
at the locked version, and the database-level hardening.

It is not a general-purpose SQL endpoint. `bin/db.sh sql` executes only
generated, hash-verified files from an allowlist. There is no path through it
that takes SQL from an argument or from standard input.

**The database migration plane** is dbmate running as `migration_user` over the
project-internal network. That role has `LOGIN` and `NOINHERIT`, and none of
`SUPERUSER`, `CREATEDB`, `CREATEROLE`, `REPLICATION` or `BYPASSRLS`. It reaches
owner authority only through an explicit membership:

```sql
GRANT <object_owner> TO <migration_user> WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;
```

`SET TRUE` lets it assume the owner deliberately. `INHERIT FALSE` means it does
not hold owner authority merely by connecting. `ADMIN FALSE` means it cannot
grant that membership onward.

Every migration's `up` block begins `SET LOCAL ROLE <object_owner>` and ends
`RESET ROLE`, so the objects are owned by the owner role while dbmate records
the version as `migration_user`.

## Consequences

The two planes need two credentials and two code paths, and an operator has to
know which one a given failure came from. That cost is the point: a bootstrap
failure and a migration failure have different remedies, and a single plane
would have made them indistinguishable.

`migration_user` is the only non-bootstrap role created with `LOGIN` and a live
credential in Session 3 (see §6.3 of the Session 3 plan). Every other service
identity is a `NOLOGIN NOINHERIT` stub.

**The catalog tests must read the membership option columns directly** —
`pg_auth_members.admin_option`, `inherit_option`, `set_option`. Inferring the
behaviour from `pg_roles.rolinherit` on `migration_user` would pass for the
wrong reason: the role-level attribute and the per-membership option are
different switches, and PostgreSQL 16 made the membership option the one that
governs. A test that reads the role attribute would stay green if the
membership were later granted with `INHERIT TRUE`, which is precisely the
regression it exists to catch.

Enforced by:

- `DBX-MIG-001` — bootstrap and migration authority are distinct and
  least-privileged (Run 6)
- `SEC-DB-001` — no runtime role holds superuser, `CREATEDB`, `CREATEROLE`,
  replication, or `BYPASSRLS` (Run 6)
- `tests/contract/test_root_script_policy.py` over `bin/postgres-bootstrap.sh`
  and `bin/db.sh` (Run 5)

## Alternatives considered

**One migration identity with `CREATEROLE`.** One credential, one path. It makes
every migration file a role-creation primitive for the life of the product, and
role creation is the one operation whose mistakes are least visible in a diff.

**Let `migration_user` inherit the owner by default** (`INHERIT TRUE`). Removes
the `SET LOCAL ROLE` line from every migration. It also means anything that
obtains a `migration_user` connection holds owner authority implicitly, so the
distinction between "connected" and "acting as owner" disappears — and with it
the ability to write a migration that deliberately does not use owner authority.

**A `SECURITY DEFINER` wrapper that performs bootstrap operations on request.**
Would let the migration plane do bootstrap work through a narrow door. It puts a
privilege-escalation primitive inside the database permanently, to save running
one script at install time.

**Bootstrap over TCP on the project network, as a distinct role.** Simpler than
a socket path. It makes the highest-privilege identity in the system reachable
from the same network as the application services, which is the property the
socket-only rule exists to deny.
