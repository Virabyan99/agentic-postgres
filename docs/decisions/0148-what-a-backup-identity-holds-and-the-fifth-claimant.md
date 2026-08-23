# 0148 — What a backup identity holds, and the fifth claimant on one budget

Status: accepted
Date: 2026-08-23
Session: 10, Run 5

Affects: D307, D517, D518, D530, D541–D546, ADR 0026, ADR 0067, ADR 0070,
ADR 0096, ADR 0099, ADR 0134, `bin/postgres-bootstrap.py`,
`src/agentic_postgres/config.py`, `src/agentic_postgres/deployed_output.py`,
`secrets.required.yaml`

## Context

`backup_user` has been one of the thirteen derived roles since Session 3
(`naming.py:143`) — NOLOGIN, null verifier, no privilege, no credential. Run 4
gave the cluster an archiver, a config and a network. Nothing can yet log in and
use them.

Two questions had to be answered before anything was written, and the plan
required both be **measured** rather than assumed (D467, ADR 0134):

1. **Which privileges does an online backup actually need on PG 18, and is any
   of it the migration plane's work?**
2. **D530: is the backup a fifth summand on `max_connections`, or is it already
   charged to `ADMINISTRATION_RESERVED_CONNECTIONS = 5`, whose comment has
   claimed to hold connections "for … backups" since Session 5?**

Rig 5 answered both, in eight arms against the pinned PG 18 digest and the Run 4
derived image, every arm with a control. What follows is what it measured.

## Decision

### 1. The privileges, and the plane that grants them

**Five grants, all issued by the bootstrap plane. There is no migration 0022.**

```sql
GRANT pg_read_all_settings TO <backup_user>;
GRANT EXECUTE ON FUNCTION pg_catalog.pg_backup_start(text, boolean) TO <backup_user>;
GRANT EXECUTE ON FUNCTION pg_catalog.pg_backup_stop(boolean)        TO <backup_user>;
GRANT EXECUTE ON FUNCTION pg_catalog.pg_create_restore_point(text)  TO <backup_user>;
GRANT EXECUTE ON FUNCTION pg_catalog.pg_switch_wal()                TO <backup_user>;
```

**Arm C decided the plane, and it did not decide it by reading a rule.** The
migration plane runs `SET LOCAL ROLE object_owner` and is never a superuser, so
the question is not "is this a `GRANT`" but "can a non-superuser object owner
issue it". Modelled with a role of exactly that shape, all five were refused:

```
ERROR:  permission denied for function pg_backup_start
ERROR:  permission denied to grant role "pg_read_all_settings"
DETAIL:  Only roles with the ADMIN option on role "pg_read_all_settings" may grant this role.
```

The arm's **control** is what makes that a boundary rather than a broken
`SET ROLE`: the same role, in the same session, issued `GRANT SELECT` on a table
it owned and succeeded. The superuser then issued all five and `aclexplode`
reported them. A migration that needed superuser to apply is D102's shape, and
the answer here is the same as D102's.

### 2. The set is complete, and each member is load-bearing

Arm G revoked each grant in turn and re-ran the commands. This is the necessity
matrix, and it is the reason the set is five rather than the two an early arm
suggested:

| Revoked | `check` | `backup` |
|---|---|---|
| *(all five granted)* | 0 | 0 |
| `pg_switch_wal` | **57** | 0 |
| `pg_create_restore_point` | **57** | 0 |
| `pg_backup_start` | 0 | **57** |
| `pg_backup_stop` | 0 | **57** |
| `pg_read_all_settings` | **27** | **56** |
| *(restored — the control)* | 0 | 0 |

**`check` needs two privileges `backup` does not**, and that asymmetry matters
because Run 6 puts `check` in the deploy's step 6c and on both timers. A role
provisioned from the backup path alone would take backups for weeks and fail
every check.

**D541 is why this ADR does not simply quote the pgBackRest documentation.** An
earlier arm granted only `pg_read_all_settings`, `pg_backup_start` and
`pg_backup_stop`, ran a full backup successfully, and observed `check` failing on
`pg_create_restore_point`. Granting that one did **not** make `check` pass — it
moved the failure to `pg_switch_wal`, which the earlier arm had recorded as "not
needed" because no command had reached it. *One missing privilege masks the
next*, so "the last thing I granted fixed it" is not a measurement of a set.
Only revoke-one-at-a-time is.

**`pg_read_all_settings` fails in a shape worth writing down (D542).** pgBackRest
does not use `SHOW`; arm E caught it issuing
`select setting from pg_catalog.pg_settings where name = 'data_directory'`. A
`SHOW` errors, but `pg_settings` **omits the restricted row entirely** rather
than nulling it — four of five rows visible instead of five. pgBackRest detects
the shortfall and names the cause exactly:

```
WARN: unable to check pg1: [DbQueryError] unable to select some rows from pg_settings
      HINT: is the pg_read_all_settings role assigned for PostgreSQL >= 10?
```

Of the five settings it reads, only `data_directory` is restricted;
`archive_command`, `archive_mode`, `checkpoint_timeout` and `server_version_num`
are readable without the membership. So the failure is total and loud, not a
`pg1-path` silently compared against NULL — which was the outcome worth checking
for, given D514.

**Nothing beyond these five.** Arm G3 confirms the role remains non-superuser and
is still refused `pg_authid` and `pg_read_file`. `archive-push` — the command
that runs most often — opens no database connection at all.

### 3. D530: the backup is its own summand, and the number is 2

**`config.BACKUP_RESERVED_CONNECTIONS = 2`, added to
`_validate_connection_budget`'s sum, and `ADMINISTRATION_RESERVED_CONNECTIONS`'s
comment loses the word "backups".**

*Why a summand rather than the reserve.* The reserve exists for consumers that
hold **no `CONNECTION LIMIT`**: the migration plane, the bootstrap plane itself,
and an operator's psql. It bounds them by convention, because there is nothing on
those roles to bound them with. `backup_user` is not that kind of claimant — it
is a role with a server-enforced ceiling, like `postgrest_authenticator`,
`auth_service`, `storage_service` and `app_runtime`, every one of which is its
own summand.

A role whose ceiling is enforced but whose ceiling is *absent from the
arithmetic* is the worst of both: the sum of enforced limits may exceed
`max_connections` while every check passes. That is precisely ADR 0070's "a
budget that looks computed and is not", and charging it to a reserve would have
been the version of D530 that reads as thrift.

*Why 2 and not 1.* Measured, in two arms:

- Arm E sampled `pg_stat_activity` **inside the same invocation** as a real full
  backup: 68 samples, **maximum 1** concurrent backend. A lone pgBackRest command
  holds one connection.
- Arm I asked whether two commands can overlap, because Run 6 puts `check` in the
  deploy and Run 9 puts `backup` on a timer, and a deploy does not consult a
  timer. **pgBackRest takes no lock that prevents it**: a `check` launched two
  seconds into a full backup ran to completion, both exited 0, and the sampler
  recorded **2** concurrent backends.

So 2 is not a margin. It is a reachable steady state of the schedule this session
is building, and the ceiling is set to what was measured rather than to what the
quiet case needs.

*What a ceiling of 1 would have cost, measured (D543).* Arm I2 repeated the same
overlap at `CONNECTION LIMIT 1`:

```
WARN: unable to check pg1: [DbConnectError] … FATAL:  too many connections for role "rig_backup"
ERROR: [027]: no database found
       HINT: check indexed pg-path/pg-host configurations
```

The diagnosis is demoted to a `WARN`; the **headline sends the reader to
`pg1-path`**, which is the one setting that is correct. Arm I3 is the control —
the same `check`, at the same ceiling, with no backup running — and it exits 0,
so I2 measured the overlap rather than the ceiling in general. D518 predicted
this class of failure would be hard to debug. It is worse than predicted: the
error does not mention connections at all.

### 4. Both arithmetics move together

There are two arithmetics over one budget and D327 is the record of what happens
when only one is checked — they agreed by coincidence, 23 against 20, and nothing
compared them for four sessions. Driven through the product's own functions
against `project.example.yaml`:

| | before | after |
|---|---|---|
| manifest: `rest 13 + auth 6 + storage 6 + pool 20 + admin 5` | 50 of 56 | **52** of 56 (`+ backup 2`) |
| bootstrap: application remainder | 23, pooler pool 20 | **21**, pooler pool 20 |
| operational headroom | 5 | 5 |

`connection_limits` subtracts the backup budget too, so the invariant holds:
the sum of enforced ceilings plus the headroom is still exactly what the server
hands out. **The application's slack over the pooler's pool falls from 3 to 1**,
and that is the price, stated rather than discovered. It is charged to the
application because the application is where the remainder lives; the headroom
that keeps a psql available when this is wrong is untouched.

**One constant, imported, not restated.** `BACKUP_RESERVED_CONNECTIONS` lives in
`config` and `bin/postgres-bootstrap.py` imports it. The alternative — a second
literal beside `OPERATIONAL_CONNECTION_HEADROOM` — is exactly the shape D530
warns about, and D545 records that this file already contains one instance of it.

## Consequences

**`test_only_the_activated_roles_may_log_in` goes red, and that was predicted
(D517).** `LOGIN_ROLES` and `deployed_output.activated_login_roles` are
**re-derived from the event, not restated** (ADR 0096): the new clause keys on
`backup_user_password` appearing in `secrets.required_names`, which is the same
fact `activate_backup_user` reads when it decides whether to credential the role.
`routes.backup` does not exist and could not have served — there is no route.

**`_summands_of_the_budget_check` is re-derived to five, not weakened (D518).**
It parses the arithmetic rather than a list beside it, precisely so a fifth
claimant fails offline, and it did. `BUDGET_CLAIMANTS` gains
`BACKUP_RESERVED_CONNECTIONS`; the assertion that the agent plane has no term is
untouched and still passes, because the agent plane still has none.

**`config.backup_connection_budget` is deliberately not written.**
`test_no_module_derives_an_mcp_connection_budget` asserts that `config` derives
exactly three `*_connection_budget` functions, and it stays green. The other
three exist because each resolves a **manifest** figure — a `pool_size` plus a
reservation. There is no manifest figure here: 2 is a constant of the release,
like `ARCHIVE_TIMEOUT_SECONDS`, and a zero-argument function returning a constant
would be the constant with a second name.

**It is a product constant rather than a manifest field**, for ADR 0146's reason
restated: publishing a per-project value means a member on `backupSettings`, and
a project that needs its own arrives with the next outputs version. No outputs
field is added by this run — the bootstrap plane imports the number rather than
reading it from the document, which is available to it precisely because the
number is not a manifest figure.

**The application's direct-session slack is now 1 on the example manifest, and
the real ones are unread (D546).** `project.alpha.yaml` and `project.beta.yaml`
are gitignored operator inputs that exist only on the host. If either sets
`database.pool_size` within two of its remainder, `connection_limits` will raise
and the deploy will refuse. That refusal is **loud, offline and reachable without
root** — `deploy.sh --render-only` — so it is the first thing the trip runs, and
the operator guide says so rather than leaving it to be found by a failed
convergence.

**A backup identity that cannot connect fails as a missing database.** D543 is
not repaired here — the message is pgBackRest's, not this product's. What this
decision does is set the ceiling above the measured concurrency so the message is
not reached, and record the string so that the next reader of a `[027]` does not
spend the incident on `pg1-path`.

## Alternatives considered

**Charge the backup to `ADMINISTRATION_RESERVED_CONNECTIONS`.** Rejected above:
the reserve bounds claimants that have no ceiling of their own, and a claimant
with an enforced ceiling that the arithmetic cannot see is the defect ADR 0070
exists to prevent. It also leaves the number invisible — the reserve is 5 whether
the backup takes 1 or 4.

**Grant `pg_monitor`, or make the role a member of `pg_read_all_stats`.**
Rejected: `pg_monitor` is a superset that carries `pg_read_all_stats` and
`pg_stat_scan_tables`, none of which any measured command needs. Arm G's
necessity matrix is the standard applied here, and a grant that can be revoked
with nothing failing is a grant this project does not make.

**`CONNECTION LIMIT 1`, matching the measured steady state.** Rejected on arm
I1's evidence: the overlap is not hypothetical, it is the schedule Runs 6 and 9
are building, and I2 measured what it costs.

**A migration 0022 carrying the `GRANT EXECUTE`s.** Rejected because arm C
measured that it cannot work, not because a rule forbids it. A released migration
that raises on every cluster is fix-forward-only and would have been discovered
on a host.

**Leave `ADMINISTRATION_RESERVED_CONNECTIONS`'s comment alone.** Rejected: it has
claimed to hold connections for backups since Session 5, and after this run it
does not. A comment describing work that moved elsewhere is D276's shape, and
this file is where D276 was found.
