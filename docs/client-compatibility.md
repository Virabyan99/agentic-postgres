# Client compatibility

Which clients are proved to work against this database, over which transport,
and what transaction pooling costs each of them.

Background: [database connections](database-connections.md) ·
[pool operations](pool-operations.md).

## What is proved, and by what

Four fixtures under `services/clients/`. Each is a real container running a real
driver against a real deployment, built from a committed lock file, holding the
application credential as a file at its own uid.

| Fixture | Transport | Requirement | Priority |
|---|---|---|---|
| `client-psql` | pooled and direct | `DBX-003` | P0 |
| `client-prisma` (Client) | pooled | `DBX-002` | P0 |
| `client-prisma` (Migrate) | direct | `DBX-001` | P0 |
| `client-node-pg`, `client-psycopg` | pooled | `DBX-004` | **P1** |

`DBX-004` is the session's only P1 and **belongs to no claim**. That is
deliberate: a claim is the thing a release blocks on, and `DBX-004` is P1
precisely because it must not block one. It is still implemented, still run, and
still in the acceptance matrix — it may fail without failing the release, which
is what P1 says.

Each fixture proves the same five things, so a difference between them is a
difference in the driver rather than in the test:

1. a connection authenticates and its `application_name` reaches the server;
2. a write lands under a **transaction-local** claim;
3. each user sees its own rows and none of the other's;
4. a transaction that sets no claim sees nothing at all;
5. `app.notes` is not addressable and `api.notes` is.

Point 5 is asserted in both directions on purpose. The catalog reports
`has_table_privilege(..., 'app.notes', 'SELECT')` as **true** — the role inherits
that grant through `authenticated` so the security-invoker views work — and the
read is denied by the absence of schema `USAGE`. A test that asserted the table
bit would fail while the property held, and the obvious fix for that failure
would silently break every `api` view.

## Transaction pooling, per client

Transaction pooling is the only mode. A server connection is returned to the pool
at the end of each transaction and the next client may get it, so **anything
scoped to a session is not yours.**

Outside the compatibility promise, for every client:

- session-scoped `SET` and `RESET`
- `LISTEN` / `NOTIFY`
- session-level advisory locks
- temporary tables
- cursors held outside a transaction
- `SET ROLE` as a session-lifetime act

Supported, and the mechanism to use instead: `SET LOCAL`, and
`set_config(name, value, is_local => true)` — the function form, and the only one
that takes a bound parameter.

**Protocol-level prepared statements do work**, and that is measured rather than
assumed: `max_prepared_statements = 100` at the locked pooler version, proved by
reusing a named statement across an *observed* backend change, with the negative
case at `0` proving the positive one is the pooler working rather than the client
landing on the same backend. This is the setting a failing client test must never
be "fixed" by lowering.

Note the distinction that cost a stage of Run 9: PgBouncer tracks **protocol-level**
named statements — what a driver issues through the extended query protocol. A
SQL-level `PREPARE foo AS …` is not tracked, and fails on the next transaction
with "prepared statement does not exist", which is indistinguishable from
`max_prepared_statements` being zero.

### psql

Nothing between the client and the boundary, which is why it is the first
fixture: a failure here is the database's or the pooler's, not a library's.

Use `\bind` for parameters (psql 16+; the image is 17.5). `:name` is the variable
form for a bound **value**; `:'name'` is SQL-literal quoting, right for building
statement text and wrong for a parameter — psql expands the variable after
parsing the meta-command's arguments, so the quotes it adds arrive as part of the
value.

### Node `pg`

Works through the pooler as-is. Do not set `statement_timeout` or anything else
at connection time expecting it to persist: a `pg.Pool` client is a *client*
connection to PgBouncer, and the server connection behind it changes.

### Psycopg

Works through the pooler as-is, including its own connection pool — which is a
pool of client connections to a pool of server connections, and is fine.
`autocommit=False` transactions are the natural unit; anything set with
`connection.execute("SET …")` outside a transaction is not durable.

### Prisma

Two rules, and both are in `schema.prisma` rather than in an operator step:

```prisma
datasource db {
  provider  = "postgresql"
  url       = env("DATABASE_URL")   // the pooled runtime endpoint
  directUrl = env("DIRECT_URL")     // the direct migration endpoint
}
```

**`url` is pooled and `directUrl` is direct.** Prisma Client uses the first and
Prisma Migrate uses the second, from one schema, with no operator step between
them. Setting both to the direct URL would make the compatibility claim true by
construction and prove nothing.

**`migrate deploy`, never `migrate dev`.** `dev` needs a shadow database it may
create and drop, and `migration_user` holds no database `CREATE` by design — so
`dev` cannot run against this deployment at all, and `deploy` is the production
command in any case.

**`?pgbouncer=true` is refused by the URL builder.** It is a flag for a
*different* deployment shape — Prisma's own connection-string workaround for
poolers that do not track prepared statements. This one does, at
`max_prepared_statements = 100`, and passing the flag would disable the behaviour
the pooled claim exists to prove while everything still appeared to work.

The migration fixture creates a **disposable schema** in the live project
database. It is created and dropped through the container-local privileged
socket, never through the TCP endpoint, because `migration_user` deliberately
holds no database `CREATE`. Its identity is recorded in root-owned state before
the unprivileged test sees it, the drop targets only the recorded name, and
`api`, `app`, `app_private`, `extensions`, `public`, `pg_catalog` and
`information_schema` are refused by name. A cleanup failure is a gate failure,
not a warning.

## Running a fixture by hand

They are Compose services under the `session4-verify` profile:

```bash
sudo bin/compose.sh /var/lib/agentic-postgres/rendered/alpha-dev \
  --runtime --profile session4-verify config --format json | jq '.services | keys'
```

Each ends with `client-<name>: every check passed`, and the harness asserts on
that line. An exit status of `0` from a CLI that was never reached looks
identical to success; the line is a contract, not a courtesy.

If you run one outside the harness, mount the credential at its **target**
filename under `/run/secrets/`, not at the namespaced `source` name. Compose
distinguishes the two so that two services' copies of one secret stay separate in
a single top-level block; `docker run` has no such notion. Mounting at the source
name produces a container whose credential is present, correct, and at a path its
own entrypoint has no reason to try — which reads exactly like a broken
materialization.
