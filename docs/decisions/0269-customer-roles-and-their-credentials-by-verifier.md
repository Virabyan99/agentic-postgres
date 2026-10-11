# 0269 — Customer roles, and their credentials by verifier

- **Status:** Accepted
- **Date:** 2026-10-11
- **Session:** 39, Run 1 (`docs/plans/session-39-implementation-plan.md`,
  D2329–D2334, D2354, D2358)
- **Affects:** `src/agentic_postgres/naming.py` (`ROLE_SUFFIXES` gains
  `customer_app`, `customer_admin`, appended last; Run 3),
  `src/agentic_postgres/bootstrap_statements.py` and `bin/postgres-bootstrap.py`
  (the roles, their grants, LOGIN and `CONNECTION LIMIT` only when enabled, the
  application remainder; Run 5), `src/agentic_postgres/config.py`
  (`_validate_connection_budget`'s two claimants; Run 5),
  `services/auth-api/app/compute_profiles.py` (the claimants per profile;
  Run 5), `compose.yaml` (`customer-pool`, `customer-direct`; Run 5),
  `bin/customer-credentials.sh` (new, root: `sync`; Run 5),
  `services/auth-api/app/operations.py` and
  `schemas/operation-arguments.schema.json` (`credential.rotate`; Run 6),
  `bin/reconciler.py` (its handler; Run 6), `bin/endpoint.sh` (new, the
  customer's CLI; Run 7), `tests/contract/test_agent_plane_contract.py`
  (`BUDGET_CLAIMANTS` widened by two). Requirements `EP-ROLE-001`,
  `EP-BUDGET-001`, `EP-POOL-001`, `EP-CRED-001`.
- **Amends:** ADR 0070's claimant list (two claimants, only for an enabled
  project; `max_connections` is not raised).
- **Related:** ADR 0268 (the door), ADR 0260 (the handoff by hash — the same
  shape), ADR 0026 (NOINHERIT), ADR 0099 (the bootstrap's remainder), ADR 0244
  (bounds), ADR 0256 (the closed set of operations).

## Context

The stage plan (D1959) asks for `customer_app` (pooled) and `customer_admin`
(direct), *"passwords generated secrets materialised like every other and shown
once through `/api/v1`"*, each with a `CONNECTION LIMIT` summed into ADR 0070's
budget. Three facts in the tree stand against the literal brief:

- **ADR 0260 rejected** *"the reconciler writes a one-time password into the
  operation's result"* — the control database, its WAL and its backups would
  hold it — and `0004` CHECKs `result_secret` to `project.export` only.
- **The image's `pg_hba` admits every role from any non-loopback address by
  SCRAM.** Routed straight to `postgres` or the platform `pgbouncer`, a public
  port would accept a platform credential — and `bin/connect.sh print-env`
  hands `op` the application runtime's password today.
- **`app` is the platform's reviewed schema**, with FORCE RLS on every table as
  the project-set lint's rule; `CREATE` on the database would grant both
  `CREATE SCHEMA` and trusted extensions.

## Measured

Planning rig 2 and Run 1's rigs 39c/39d/39e (WSL, PgBouncer 1.24.1, psql and
PostgreSQL 18.4):

- **A pooler whose userlist holds only a SCRAM verifier authenticates to the
  server by pass-through** (no password anywhere in the pooler). **Control
  (rig 39d, a FRESH pooler each case)**: a verifier for the same password with
  a different salt than the server's → refused, *"password authentication
  failed"*; the server's own verifier → connected. Planning's case 1f had
  connected only because PgBouncer reused a server connection opened earlier
  (X3: passes after SIGHUP alone, refused after a restart).
- **A pooler whose userlist names one role refuses every other** — the
  superuser `postgres`, the other customer role, a wrong password — **with one
  message**, *"SASL authentication failed"*: no role-existence oracle.
- **An empty userlist starts, stays up and refuses every login**; writing the
  verifier and a SIGHUP admits it.
- **Rotation**: `ALTER ROLE … PASSWORD :'verifier'`, the userlist rewritten,
  `docker kill -s HUP` → the old password refused, the new accepted, the
  container not restarted.
- **The grants below** (rig 39c): `customer_admin` creates a table with an
  `extensions.vector(3)` column in `public`; `customer_app` inserts and selects
  it through default privileges and is refused `CREATE TABLE`; the admin is
  refused `app` (*"permission denied for schema app"*), `app_private`,
  `CREATE SCHEMA`, `CREATE EXTENSION` (*"Must have CREATE privilege on current
  database"*) and `CREATE ROLE`; session state and an advisory lock survive
  across statements on the session-mode door; `pg_dump -n public` works
  through it; `prisma migrate deploy` runs through it.
- **The budget (rig 39e, the product's own `_validate_connection_budget`
  summands and `connection_limits`, the slot manifest's `pool_size` 16,
  `superuser_reserved_connections` 3):** small (48) fits **2/2** (3/3 leaves
  the application 15 < 16); standard (56) fits **2/2** (3/3 leaves 15 — the
  plan's proposed 3/3 does not fit); large (100) fits up to 8/8.
- **Memory**: a customer pooler read ~1.5 MiB after the four drivers; ADR
  0244's rule (max(4 × peak, 64 MiB)) gives the floor.

## Decision

1. **Two roles on every project, logging in only where the facility is
   enabled.** `customer_app` and `customer_admin` are appended LAST to
   `ROLE_SUFFIXES` and created `NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB
   NOCREATEROLE NOREPLICATION NOBYPASSRLS` everywhere (uniform statements,
   `check_violations` reads them everywhere). `LOGIN` and `CONNECTION LIMIT`
   are applied only when `database.public_endpoints.enabled`; **the bootstrap
   never sets a customer `PASSWORD`**, so a redeploy cannot reset a
   customer's verifier (a test holds that no statement it builds does).
2. **A customer's DDL lives in `public` and nowhere else.** `GRANT CONNECT` to
   both (the exhaustive list gains two); `GRANT USAGE, CREATE ON SCHEMA public
   TO customer_admin`; `GRANT USAGE ON SCHEMA public TO customer_app`;
   `ALTER DEFAULT PRIVILEGES FOR ROLE customer_admin IN SCHEMA public GRANT
   SELECT, INSERT, UPDATE, DELETE ON TABLES TO customer_app` and `USAGE, SELECT
   ON SEQUENCES`; `GRANT USAGE ON SCHEMA extensions` to both. **Nothing** on
   `app`, `api`, `app_private`; no `CREATE` on the database; no role attribute.
   An export dumps `-n app -n api -n public` (ADR 0259, amended).
3. **The door is customer-only by construction.** `customer-pool`
   (`pool_mode = transaction`, userlist = `customer_app` only) and
   `customer-direct` (`pool_mode = session`, userlist = `customer_admin`
   only), each `auth_type = scram-sha-256`, `max_prepared_statements = 100`,
   `track_extra_parameters = search_path` (ADR 0268), `max_db_connections`
   equal to its claimant, read-only with a tmpfs `/etc/pgbouncer`, `mem_limit`
   64m, `pids_limit` 64. **"Direct" is a session-mode connection** — one server
   connection per client, session state kept; the Ledger's `direct_endpoint`
   says exactly that. No `hba_file` is rendered; no platform role is ever in a
   customer userlist.
4. **Two claimants, only when enabled**: `customer_pool_connections` and
   `customer_direct_connections`, **small 2/2, standard 2/2, large 5/5**, in
   the profile table; summed by `_validate_connection_budget`, subtracted by
   `connection_limits` from the application's remainder, and equal to each
   role's `CONNECTION LIMIT`. `BUDGET_CLAIMANTS` widens by the two names under
   this ADR. `max_connections` is not raised.
5. **Credentials by verifier — no customer password ever exists on the host or
   in the control plane.** `bin/endpoint.sh credential --project-key K --role
   app|admin --password-file F` generates `secrets.token_urlsafe(32)` on the
   workstation, writes F (0600, `O_EXCL`), computes the SCRAM-SHA-256 verifier
   (4096 iterations, 16-byte salt) and posts **only the verifier** as a
   `credential.rotate` operation `{role, verifier}`, validated by the schema at
   the route and again by the reconciler. The handler sets it with `ALTER ROLE
   <role> PASSWORD :'verifier'` through `container_exec.run`, the value on
   stdin as a psql variable (never argv, never a log line), then
   `bin/customer-credentials.sh sync` regenerates both userlists **from
   `pg_authid`** and SIGHUPs both poolers; a deploy runs `sync` too. A customer
   cannot choose a password (the CLI has no such flag).

## Consequences

- The control plane holds a verifier of a 256-bit random password, which opens
  nothing and cannot be brute-forced; a stolen platform credential is useless
  at the public door.
- `pg_authid` is the one source, so a restore or a branch carries the
  credential with the data — **Session 40's re-key must rotate both customer
  roles** before a branch's names open.
- A customer's verifier lives in two places (`pg_authid` and the userlists);
  `sync` is the one writer of the second. Between `ALTER ROLE` and `sync` the
  new password is refused at the door for that instant; pooled server
  connections opened before a rotation stay open (they authenticated already).
- The operator can read the verifier, never the password.
