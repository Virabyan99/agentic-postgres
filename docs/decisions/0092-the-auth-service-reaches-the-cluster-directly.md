# 0092 — The auth service reaches the cluster directly

Status: accepted
Date: 2026-08-15
Session: 6, Run 12
Affects: ADR 0070, ADR 0083, D246, D288, D289, `compose.yaml`,
`bin/postgres-bootstrap.py`

## Context

The auth service was declared against PgBouncer, with a comment that made a
reasonable case for it:

> PgBouncer, not the cluster directly: the auth service's queries are short and
> transactional, which is the shape transaction pooling is for, and the
> connection budget ADR 0070 divides is a budget on the pooler's side of the
> same arithmetic.

The first host deploy that got far enough to start the container found that it
cannot connect at all:

```
error connecting in 'auth': connection failed:
  connection to server at "172.23.0.3", port 6432 failed:
  FATAL:  SASL authentication failed
psycopg_pool.PoolTimeout: pool initialization incomplete after 15.0 sec
ERROR:    Application startup failed. Exiting.
```

Two independent defects, and the order they fire in matters.

**D289.** PgBouncer authenticates its own clients against a userlist its
entrypoint writes, and that list has exactly two entries: `app_runtime` and the
pool admin. `auth_service` is neither, so the pooler refuses the connection
**before postgres is consulted**.

**D288.** `bin/postgres-bootstrap.py` applied the role's CONNECTION LIMIT and
printed `role NOLOGIN until session 6` — a sentence written *in* session 6,
deferring activation to a run that never came. Run 7 built the service, Run 10
published it, and the role reached the host with no password. `app_runtime` and
`postgrest_authenticator` are both activated ten lines above, in the same
function.

Fixing either alone changes nothing: the pooler rejects first, postgres second.

## Decision

**The auth service connects to `POSTGRES_SERVICE_HOST:5432`, exactly as
PostgREST does**, and `postgres-bootstrap.py` activates `auth_service` in the
same shape as the other two roles.

The alternative was to keep the pooler and add a third userlist entry. That is
the change the original comment implies, and it was rejected on what it would
cost rather than on whether it would work:

* it puts the auth service's **database password into PgBouncer's userlist**, so
  a second container holds a credential that reaches the identity registry —
  `app_private.users`, `user_credentials`, `agents`, `agent_credentials`;
* it requires `auth_service_password` to gain a second compose consumer, which
  is a widening of the secret contract, in a session where D257 declined to
  widen it for a weaker reason;
* it buys a transaction-pooling layer **underneath a service that already runs
  its own psycopg pool** (ADR 0083), so the connection is pooled twice.

PostgREST is the precedent and it is exact: it is the only other first-party
service holding a privileged role, it has connected directly since Session 5,
and it is deliberately absent from the userlist for the same reason.

## What is unchanged

**ADR 0070's arithmetic.** The budget divides one `max_connections` — 50, less 3
reserved, into application 23, api 13, auth 6, headroom 5. That division is a
statement about the cluster, not about which host name a client dials.
`AUTH_POOL_SIZE` is 4 and the role's CONNECTION LIMIT is 6, so the pool fits
with headroom on either side of a pooler.

**The bootstrap's advisory lock.** `auth_bootstrap_administrator` takes a
*transaction*-scoped lock, which is safe under transaction pooling and equally
safe without it. Run 8 recorded that a **session**-scoped lock would be stranded
through a transaction pooler, which is why `bin/auth-admin.sh` connects directly;
that reasoning is untouched and now the service agrees with the command.

## Consequences

One line of `compose.yaml`, and a credential the bootstrap now sets. Nothing is
added to the secret contract and PgBouncer holds exactly what it held before.

`tests/contract/test_auth_service_database_access.py` asserts the property in
both directions: that every role a container logs in as is a role the bootstrap
calls `apply_credential` for, and that no service reaches the pooler under a
role its userlist does not carry. The first is the general form of D288 — it
would have failed the moment the auth service was written — and the second is
the general form of D289.

Mutation-tested against the two states that actually shipped, plus a third where
the bootstrap's consumer dictionary disagrees with `secrets.required.yaml` (which
would report the credential absent and leave the role NOLOGIN, with no error).
All three go red.

**What this ADR does not fix is why it took a host to find.** Three separate
offline proofs reported the auth service healthy against a real cluster — Run 8's
endpoint tests, Run 9's agent tests, Run 10's container rehearsal — and every one
of them credentialed the role itself in its own fixture:

```python
cluster.psql(f"ALTER ROLE \"{auth_role}\" LOGIN PASSWORD '{auth_password}'", ...)
```

with a comment saying so: *"What the bootstrap plane does in production (D102,
D246). The rig supplies it because Run 7 shipped the service with the role
NOLOGIN."* The rig knew the product did not do this, said so in a comment, and
did it anyway. That is ADR 0065/0066's class again, in its sharpest form yet:
**a rig that compensates for a gap documents the gap and hides it at the same
time.**
