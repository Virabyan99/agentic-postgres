# Database connections

How a developer reaches a project's database, and why the route is the shape it
is.

Background: [the database](database.md) · [database security](database-security.md)
· [pool operations](pool-operations.md).

## The short version

```bash
bin/connect.sh tunnel --project alpha-dev --ssh operator@host.example
bin/connect.sh psql   --project alpha-dev
bin/connect.sh stop   --project alpha-dev
```

That is the whole developer path. There is no host port to reach, no password to
copy, and no URL to keep.

## Two transports, three access profiles

| Profile | Transport | Role | For |
|---|---|---|---|
| `runtime_pooled` | PgBouncer | `<project>_app_runtime` | Prisma Client, Node `pg`, Psycopg, ordinary applications |
| `runtime_direct` | PostgreSQL | `<project>_app_runtime` | Prisma Studio, diagnostics, comparing pooled behaviour against unpooled |
| `migration_direct` | PostgreSQL | `<project>_migration_user` | dbmate, Prisma Migrate, privileged `psql` |

`runtime_direct` is the default. `migration_direct` carries authority over the
schema, so it is never reached by default or by fallback, and asking for it
prints a warning. The pooled transport rejects `migration_user` outright: DDL
through transaction pooling breaks advisory-lock and transaction semantics in
ways that look like intermittent failures rather than like a misconfiguration.

Role names are derived from the project key and are not written down here. Read
them out of the deployed document if you need them.

## Nothing is published

The obvious design — publish each project's pooler on a host-loopback port and
tunnel to that — was built, and then measured. **Docker installs no rule and no
listener for a container attached only to an `internal: true` network.** It
accepts the request and records it in `HostConfig.PortBindings`, which is what
Docker was *asked* for, and nothing answers.

`internal: true` is not incidental: it is the property Session 2's and Session
3's negative proofs rest on. So the publication went, not the network
([ADR 0044](decisions/0044-there-is-no-publication.md)):

- the tunnel's far end is the **container's address on the host's own bridge**;
- that address is resolved by the broker at the moment it answers, and never
  written down — a container's IP changes when the container is recreated, and a
  recorded one is right until the next restart;
- the allocated port is the **near** end, the one your `psql` connects to.

The consequence to hold on to: **you need SSH to reach a database, always.**
There is no host port, so there is nothing to reach even from the host without a
container address. An operator with root on the host uses
`bin/db.sh --project … --runtime psql`, which goes through `docker exec`.

## The allocation

Two ports per project, allocated together from a host range, keyed by
`app_private.project_identity.instance_uuid` — the identity the *data volume*
carries, generated once on the first bootstrap of an empty volume and recovered
on every bootstrap since. A restored volume brings its ports with it.

```bash
sudo bin/database-ports.sh show
```

- **Reuse is the default.** A redeploy gets the same numbers back, because they
  are in somebody's saved tunnel and in somebody's notes.
- **`reserved` becomes `active` only after both endpoints answer.** A deploy that
  crashed after reserving leaves a reservation nothing serves, which is provable
  rather than invisible.
- **Reassignment requires an explicit release**, after shutdown, with the project
  key confirmed. Never reassign an initialised project because a lower port came
  free.

Allocations are stable across redeploy, restart and reboot, and that is measured
rather than intended: the restart matrix in
`tests/deployment/test_session4_convergence.py` restarts the pooler, the cluster
and the unit, and asserts the registry record is unchanged each time.

## The helper

`bin/connect.sh` is a developer's program. It runs on a developer's machine, not
on the host.

| Command | What it does |
|---|---|
| `tunnel` | Opens an SSH local forward to one profile's endpoint and records it. Binds `127.0.0.1` and nothing else. |
| `status` | Reports which recorded tunnels are live. |
| `stop` | Closes one this helper opened, or `--all`. |
| `print-env` | `PG*` variables and a password-free `DATABASE_URL`. |
| `psql` | Interactive `psql` over an open tunnel. |
| `exec` | Runs a command with the connection environment set. |

Four properties worth knowing, because each of them is a refusal you may run
into:

**Host-key verification is required.** `StrictHostKeyChecking=no` and a
`UserKnownHostsFile` of `/dev/null` are refused rather than passed through. A
tunnel to an unverified host is a private channel to somebody.

**A tunnel that failed to forward is not a tunnel.** `ExitOnForwardFailure` turns
a bind failure into a failed command rather than a connected session with no
forward, which otherwise fails later as "connection refused" against your own
loopback.

**A recorded process is matched by identity, not by name.** Start time and full
argument vector must match before anything is signalled, and a record whose
process is gone is quarantined rather than deleted or believed. Nothing is ever
matched by process name.

**No command prints a credential.** `print-env` emits a `DATABASE_URL` with no
password in it; `exec` sets `PGPASSFILE` to a `0600` file that exists for the
child's lifetime and is removed afterwards. No secret is ever an argument.

## The broker

The helper does not read secrets. It asks a privileged broker on the host, over
SSH, through `sudo -n` and a fixed trampoline path:

```
/usr/local/libexec/agentic-postgres/database-access <project> <operation> <profile>
```

The broker decides **before** it reads any project state, so a refusal for an
ungranted profile is indistinguishable from one for a project that does not
exist — that identity is what stops an authorised caller enumerating other
people's projects by exit code. A refusal is exit `6`, says nothing on stdout,
and names neither the project nor the profile.

The policy is an enumerated grant of one account to one project's named
profiles. **There is no wildcard in any of the three fields**: a grant matching
every project would silently cover projects deployed months later, and one
matching every profile would hand out migration authority as a side effect of
asking for runtime access.

```bash
sudo bin/database-access.sh show
bin/database-access.sh check --policy candidate.json
sudo bin/database-access.sh publish --policy candidate.json
```

The password comes from the generation `active-secret-generation.json` points
at, not from the deployed document. Both name a generation; after a rotation
they differ, and the document's is the one that no longer authenticates
([ADR 0038](decisions/0038-the-deployed-document-records-the-generation-it-verified.md)).

## Traps

**The pooled transport is transaction pooling, and there is no other mode.**
Session-scoped `SET`, `LISTEN`, session advisory locks and temporary tables are
outside the compatibility promise. Use `SET LOCAL` or
`set_config(..., is_local => true)`. See
[client compatibility](client-compatibility.md).

**`app_runtime` is a server-application credential, not an end-user account.**
Possession is equivalent to possession of a trusted application server's
credential, and it permits controlled impersonation through request context. It
is never distributed to browsers, mobile clients or untrusted end users.

**A stale tunnel to a recreated container fails at connect time, not at open
time.** The container address is resolved when the tunnel opens; recreate the
container and the forward points at an address nothing holds. `stop` and
`tunnel` again.
