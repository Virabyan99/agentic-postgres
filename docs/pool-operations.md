# Pool operations

Operating the connection pooler: what it is configured to do, how to look at it,
what a restart costs, and how a credential rotation goes.

Background: [database connections](database-connections.md) ·
[client compatibility](client-compatibility.md).

## What is running

One PgBouncer per project, on the project's internal network, at `pgbouncer:6432`.
It publishes no host port and joins no edge network. It runs as uid/gid **70** —
its image sets a default user, so the process is 70 from PID 1 onward and there
is never a root window in which to fix a file's ownership. A secret materialized
at any other uid is simply unreadable to it.

Its configuration is a **rendered INI file**, mounted. The image's documented
configuration interface is `DATABASE_URL`, whose password its entrypoint parses
into the user list and whose own comment notes that `docker inspect` will show
it. That interface is unusable here. Mounting an INI works because the entrypoint
skips generation when a config already exists, which is asserted rather than
assumed — it is the load-bearing half.

## The settings that matter

| Setting | Value | Why |
|---|---|---|
| `pool_mode` | `transaction` | The only mode. A Session 4 command may not quietly select session pooling to make a client pass. |
| `default_pool_size` | `database.pool_size` | Server connections per user/database pair. |
| `max_client_conn` | `database.max_client_connections` | Client ceiling. `pool_size` may not exceed it. |
| `max_prepared_statements` | 100 | Non-zero, deliberately. At `0` a named statement is unusable the moment pooling moves the client to another backend. |
| `query_wait_timeout` | 20s | Bounded so a saturated pool **fails** rather than stalling. A hang has no error message to act on. |
| `server_lifetime` | 3600s | Bounded above so a rotated credential cannot be held indefinitely by a long-lived backend. |
| `auth_type` | `scram-sha-256` | |
| `server_reset_query` | `DISCARD PLANS; DISCARD SEQUENCES; DISCARD TEMP; RESET ALL` | See below. |
| `server_reset_query_always` | `1` | See below. |

### The reset query is `DISCARD ALL` minus one statement, and that is the whole story

Two P0 requirements collided here, one of them created by the other's fix.

**`server_reset_query_always = 1` is load-bearing.** PgBouncer runs
`server_reset_query` only in SESSION pooling unless this is set; in transaction
mode it assumes an application leaves no session state behind. It was measured
not to: a client that ran `set_config('apg.leak_probe', …, false)` and
disconnected left the GUC on the server connection, and **the next client read it
back**. One request's asserted identity becoming the next one's is the most
dangerous single failure available in this design, and nothing about a healthy
pooler distinguishes it.

**But `DISCARD ALL` includes `DEALLOCATE ALL`.** Turning the reset query on with
its default value took every prepared statement on the connection with it, and
the requirement that a named statement survives a backend change cannot hold
against a pooler that deallocates after every transaction.

Both tempting resolutions were weakenings — drop `server_reset_query_always` and
lose the session-state guarantee, or accept that prepared statements do not
survive and rewrite the other requirement into a test of the fallback. The
resolution is `DISCARD ALL` minus the one statement that broke it. `RESET ALL` is
what actually clears a custom GUC set through `set_config`.

**If you change this line, both requirements are in play.** Do not add
`DEALLOCATE ALL` back, and do not remove `RESET ALL`.

## Looking at it

The admin console is a virtual database served by the pooler itself: `SHOW POOLS`,
`SHOW CONFIG` and `RECONNECT` are answered by the daemon, not forwarded. It
authenticates with `pgbouncer_admin_password`, which is **not** a database role
and is deliberately separate from the application credential — a credential that
can read every pool's statistics is not the one an application holds.

From the host, inside the pooler's own container, through the `0600` `PGPASSFILE`
its entrypoint wrote into a tmpfs:

```bash
sudo docker exec apg-alpha-dev-pgbouncer-1 sh -c \
  'PGPASSFILE=/etc/pgbouncer/.pgpass exec psql -h 127.0.0.1 \
     -p "$APG_POOL_LISTEN_PORT" -U "$APG_POOL_ADMIN_USER" -d pgbouncer -w -X -qtA \
     -c "SHOW POOLS"'
```

Read from the **running daemon**, never from the rendered INI. A file nobody
loaded is exactly the kind of value that looks measured and is not.

## Saturation

More clients than the pool holds is a normal state, not a fault: they queue, and
`query_wait_timeout` bounds the queue. What must never happen is server
connections exceeding the configured budget, and that is measured by running more
concurrent clients than `pool_size` and watching `SHOW POOLS` alongside
`pg_stat_activity`.

Two numbers to keep in view on this host: it has **no swap**, and the OOM killer
does not choose politely — it can take Traefik, which drops every project's
ingress at once. The memory guardrail is computed over *unreclaimable* memory and
rendering fails when the declared sum exceeds it; `mem_limit` is set deliberately
**above** the guardrail, because a container memory limit caps page cache too and
a limit sized from an anonymous-memory formula produces a service that pegs it
permanently and never OOMs.

## Restart

```bash
sudo docker restart apg-alpha-dev-pgbouncer-1                    # the pooler
sudo docker restart apg-alpha-dev-postgres-1                     # the cluster
sudo systemctl restart agentic-postgres-project@alpha-dev.service # the stack
```

All three are asserted by `tests/deployment/test_session4_convergence.py`, so
running them by hand is for confirming a specific worry. After each, three things
must be true and are checked: **the allocation is unchanged, both transports
accept the runtime credential again, and no public listener appeared.**

The second one is the interesting case. A cluster restart invalidates every
server connection the pooler holds, simultaneously. A pooler that did not
reconnect would answer new clients with a stale backend error while its own
container stayed healthy and its admin console kept working.

**A restart does not pick up a code change.** The installed launcher runs the
release the deployed document records
([ADR 0037](decisions/0037-an-installed-launcher-resolves-a-release-and-nothing-else.md)).
Changing the rendered INI in the checkout and restarting changes nothing;
redeploy.

## Reboot

Take the snapshot from the deployed document, not from a suite run. Then reboot,
**wait for both project units to reach `active`**, and check:

```bash
sudo systemctl is-active agentic-postgres-project@alpha-dev.service
sudo bin/session-04-check.sh --mode host --host host.yaml \
  --project-a-outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json \
  --project-b-outputs /etc/agentic-postgres/projects/beta-dev/outputs.json \
  --after-reboot
```

`--after-reboot` admits a proof that is otherwise skipped: **the data predates the
boot and every process reading it postdates the boot.** Both halves are needed —
a cluster that reinitialised into a fresh volume satisfies the second, and a host
that was never rebooted satisfies the first.

Two things that cost a run each in Session 3:

- a post-reboot check run at `up 0 min` reported ten failures that all meant the
  host was still booting;
- comparing `app.notes` row counts for equality across a reboot fails, because the
  isolation suite inserts a row on every run. Compare identity and ledger for
  equality; compare rows for **never lost**.

## Rotation

Zero-downtime rotation is out of scope. Plan for the state that makes it
dangerous: **PostgreSQL holding one password while the pooler holds another.**

1. **Determine which plane holds which credential before making a second change.**
2. Set the new value at the provider. Nothing in this repository writes one — the
   Infisical client here reads.
3. Re-materialize, which writes a new generation and repoints
   `active-secret-generation.json` at it:
   ```bash
   sudo bin/materialize-secrets.sh --project project.alpha.yaml \
     --requirements secrets.required.yaml --session 12
   ```
4. Redeploy, so bootstrap sets the role's verifier and the pooler starts against
   the new generation. A bare restart does not run bootstrap.
5. Prove it, in the same window, with the credential from the **previous**
   generation directory (they accumulate; nothing prunes them):
   ```bash
   sudo bin/session-04-check.sh --mode host --host host.yaml \
     --project-a-outputs … --project-b-outputs … \
     --rotated-from-file /var/lib/agentic-postgres/secrets/alpha-dev/generations/<old>/pgbouncer/app_runtime_password
   ```

That check asserts all four combinations in one run: the new credential opens the
pooled and the direct transport, and the old one opens neither. Each half alone
is satisfied by a split brain, whichever way round it went.

**Never publish `ready` with the two planes disagreeing, and do not generate a
third password to escape a two-password problem.**

`app_runtime_password` reaches **five files** — the pooler's and the four client
fixtures' — and `migration_user_password` reaches two. Per-consumer copies are
what make "one service cannot read another's credential" true; the count is the
price, and it is written down rather than reduced by sharing a mount.

Those two counts are what Session 4 declared. Ask
`bin/materialize-secrets.sh --plan --session N` rather than this paragraph: it
prints every file, its owner and its mode, totals them, and contacts nothing
(D108). Session 5 adds files that are not copies of either credential —
including one written in **pgpass format** rather than as the raw value, because
the service that reads it has no shell to wrap it (ADR 0056), and two on the
**root plane** that no container receives at all (ADR 0054).

`postgres_init_superuser_password` is the exception in the other direction: the
image reads it only when the data directory is empty, so writing a new generation
of that file changes the file and nothing else. Rotating it for real is a
coordinated `ALTER ROLE` through the privileged local path, which is a different
operation with a different name.
