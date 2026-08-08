# Database security

Thirteen roles, three schemas, forced row-level security, and two authorities
that never meet. Every claim below is measured against a live cluster's catalog,
not against migration source — a statement that reports success and stores
nothing is the specific failure this session found twice.

## Two authorities

**The bootstrap plane** is root on the host, over the Unix socket, inside the
container, as the OS user `postgres`. It creates or verifies the thirteen roles
and their membership options, the identity sentinel, the schemas, dbmate's table,
the ledger table, the pgvector extension at its locked version, and the
database-level `CREATE`/`TEMPORARY`/`CONNECT` hardening. It is reachable by no
runtime service.

**The migration plane** is a container connecting over the project's internal
network as `migration_user`, which holds `LOGIN` and `NOINHERIT` and none of
`SUPERUSER`, `CREATEDB`, `CREATEROLE`, `REPLICATION` or `BYPASSRLS`. It reaches
owner authority only through an explicit membership it must `SET ROLE` into.

They are separate because a plane that can change the schema and also write the
record of what it changed has no audit trail
([ADR 0026](decisions/0026-bootstrap-authority-is-separate-from-migration-authority.md)).

`bin/postgres-bootstrap.sh --check` asks the catalog nine questions and returns
**6** with the list when any of them is wrong. It used to print how many
statements *would* run and return 0 — against a cluster with no roles, no
schemas, no extension and no credential. `--apply` runs the statements and then
asks the same nine questions again, because psql accepting a statement is not the
catalog holding it.

## The roles

Derived per project by `naming.py`, never by anything else:

```
anon                     authenticated            agent_reader
agent_writer             project_admin            postgrest_authenticator
auth_service             mcp_audit_service        storage_service
migration_user           backup_user              app_runtime
object_owner
```

Two properties are asserted from the catalog:

- **Only `migration_user` may log in.** Every other role is `NOLOGIN`; they are
  reached by `SET ROLE` from a service that authenticated as something else.
- **The object owner is a non-login role** (`SEC-OWNER-001`). Objects belong to
  an identity nothing can authenticate as.

Membership options are read from `pg_auth_members.admin_option`,
`inherit_option` and `set_option` directly — never from `pg_roles.rolinherit`,
which describes the member and not the grant.

`SEC-DB-001`: no runtime role holds superuser, `CREATEDB`, `CREATEROLE`,
replication or `BYPASSRLS`.

## The schemas

| Schema | What it is |
|---|---|
| `app` | Owner-scoped tables. API roles get table `SELECT` and **no schema `USAGE`**. |
| `api` | `security_invoker` views and `SECURITY DEFINER` write RPCs. The only surface. |
| `app_private` | Identity sentinel, ledger, dbmate's table. Not reachable by API roles. |
| `extensions` | pgvector lives here, not in `public`. |
| `public` | Stripped. |

### Table SELECT without schema USAGE

This is the construction that makes the boundary work, and it is not the obvious
one.

A `security_invoker` view evaluates the **base table's** privileges as the
caller. So the views are dead without `SELECT` on `app.notes` and `app.tasks` —
and granting schema `USAGE` to fix that would also make `SELECT * FROM app.notes`
work directly, dissolving the negative proof the boundary rests on.

Granting table `SELECT` **without** schema `USAGE` gives exactly the wanted
shape: schema `USAGE` is resolved when the view is created, by its owner, so the
views return the caller's rows while `app.notes` raises
`permission denied for schema app`. Both halves are asserted separately — neither
is safe to infer from the other.

Write RPCs are `SECURITY DEFINER` for the same reason: a `SECURITY INVOKER` write
function needs `USAGE` on `app` to `INSERT`, so it cannot exist without the grant
it is there to avoid. They return `api.notes` / `api.tasks`, not the private row
types, because a return type is resolved by the caller.

`SECURITY DEFINER` is safe here **only** because of the forced RLS below: the
owner's own writes stay policy-checked, and the policies key on the caller's
claim rather than on `current_user`. Without `FORCE`, the same function is an
ownership-laundering primitive.

## Row-level security

`FORCE ROW LEVEL SECURITY` on the owner-scoped tables — forced, so the table
owner is subject to its own policies too. Policies key on a **transaction-local
claim**, `app.user_id`, set by the caller for the duration of a transaction
([ADR 0029](decisions/0029-request-identity-is-a-trusted-transaction-local-claim.md)).

It is a *trusted* claim, not an authenticated one. Whatever sets it is asserting
an identity the database does not verify; the authentication that backs it
happens in front of the database, and Session 3 does not ship that. The
requirement this satisfies is that rows are isolated *given* a claim — which is
what `SEC-RLS-001` says and all it says.

Live proofs compare each owner's visible rows against that owner's **actual** row
count read as the superuser, not against a constant. An earlier version asserted
`count(*) == 1` after a fixture that seeds a row per run: it could pass once on a
virgin cluster and never again, which a convergence check and every post-reboot
run would have hit.

## Function privileges, and a statement that does nothing

`SEC-DEFAULT-001` — a newly created function is not executable by `PUBLIC`.

The natural implementation is
`ALTER DEFAULT PRIVILEGES … REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC`. **Measured
against the locked image, that statement reports success and stores nothing.**
`pg_default_acl` stays empty and a function created afterwards by `object_owner`
still has `PUBLIC EXECUTE`. Tested both inside `SET LOCAL ROLE` and with an
explicit `FOR ROLE` from a superuser session.

So the mechanism is an explicit `REVOKE ALL ON FUNCTION … FROM PUBLIC` beside
every `CREATE FUNCTION`, measured to leave `has_function_privilege('public', …)`
false. The `ALTER DEFAULT PRIVILEGES` statement stays as defence in depth on any
version where it does work, and the migration says in place that it is not what
is being relied on.

The requirement's test **creates a function and measures it**. It never asserts
that the statement was issued. Had it done so, it would have been green for the
entire life of the product over a cluster where every new function was
world-executable.

## What is not a boundary

**Loopback inside the container is trusted.** The image's `pg_hba.conf` carries

```
host all all 127.0.0.1/32 trust
```

above its `host all all all scram-sha-256` line. Anything that can
`docker exec` into the cluster can connect as any role without a password — which
is not a new exposure, because `docker exec` is root-equivalent already, but it
does mean **a password test run inside the container measures nothing**. A
deliberately wrong password returns `1` and exit `0` there. Credential tests
connect from a separate container on the project's internal network, which is
where dbmate connects from and the only path that reaches a line checking a
password (D74).

## Verifying

```bash
sudo bin/postgres-bootstrap.sh --project project.alpha.yaml --runtime --check
sudo bin/session-03-check.sh --mode host --host host.yaml \
  --project-a-outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json \
  --project-b-outputs /etc/agentic-postgres/projects/beta-dev/outputs.json
```

The gate's `least_privilege` and `row_level_security` claims are computed from
exactly the node IDs the acceptance registry lists for the requirements above. A
proof that was skipped is not a pass, and a proof missing from the artifact is
`not_run` rather than `passed`.

One spelling worth not rediscovering: in PostgreSQL, `boolean || text` and
`boolean::text` both yield the words `true` and `false`. `t` and `f` are what
psql *prints* for a boolean column, which is a different thing — three tests and
one script asserted the printed form and would have failed on first contact with
any cluster.
