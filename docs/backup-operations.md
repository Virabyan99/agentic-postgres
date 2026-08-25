# Backup operations

What the backup plane is, how to operate it, and what it does not protect you
from. Session 10 built it; nothing in it has run against Cloudflare R2 yet, and
this document says so wherever that matters.

Cited by `Documentation=` in the four backup units, so `systemctl status` sends
you here.

---

## 1. The shape, in one screen

Each project has **its own R2 bucket**, its own API token and its own repository
cipher pass (ADR 0145). Not a prefix inside the application's bucket: R2 scopes a
token to buckets far more cleanly than to key prefixes, which turns "the storage
service cannot reach the backup repository" into a token scope you can measure a
`HeadBucket` against instead of a policy sentence nothing executes.

**pgBackRest runs inside the database container** (ADR 0144). `archive_command` is
executed by the postmaster, and it must return non-zero *synchronously* for a
segment to count as unarchived — a sidecar sharing the volume can take a backup
and cannot serve an archive command. So the image is built rather than pulled,
the credential is materialized into that container's secret generation owned by
uid 999, and **the host has no pgBackRest and no repository credential at all**.

The cluster reaches R2 over a **`backup` egress network of its own** (ADR 0147).
The `internal` network is `internal: true` and has no route off the host —
measured, not assumed — so `archive-push` could not reach anything from where the
postmaster runs it. `edge` would have worked and was refused: it is where
Traefik's public side lives and the database has never been on it.

The three credentials reach pgBackRest as **configuration fragments under
`/etc/pgbackrest/conf.d`** (ADR 0153), one option per file, mode `0400`, owned by
999. pgBackRest has no `-file` option for any of them and nothing here puts a
value in its environment, so this is the only route that exists.

**Two identities, and neither is an application identity.** `backup_user` is a
real login role with exactly five measured privileges and `CONNECTION LIMIT 2`
(ADR 0148); it is the fifth claimant on one `max_connections`.

---

## 2. The account boundary — read this before you rely on any of it

**Everything here lives in one Cloudflare account.** The application bucket, the
backup bucket, both API tokens and the DNS all sit under the same account, and
the credential that could delete a bucket is a Cloudflare API token a human
holds.

So the backup plane protects you from:

- a dropped table, a bad migration, a bad deploy, an application bug;
- a lost or corrupted `postgres-data` volume;
- a host that will not boot.

It does **not** protect you from:

- **a compromised or closed Cloudflare account.** The backups are in it. An
  attacker with account-level access can delete the bucket, and so can a billing
  failure.
- **a compromised database container.** It holds the repository credential *and*
  the cipher pass, which is ADR 0147's stated residual: an attacker inside it
  owns the backup history as well as the live data.
- **destruction of `pgbackrest_repo_cipher_pass`.** It is in
  `bootstrap-state.schema.json`'s `managed_resources`, so `--destroy` may remove
  it — correct for a project being torn down, and catastrophic for one that is
  not. Losing it orphans **every backup ever taken**, and every check in this
  repository still passes (D538).

Cross-account replication, a second provider and an offline copy are all absent
by decision, not oversight. If the account boundary is a risk you need retired,
that is a session of its own and nothing here is a substitute.

---

## 3. Setting a project up, once

Steps 1 and 2 are **out of band and irreversible in the ordinary sense**: nothing
in this repository creates a bucket or issues a token (ADR 0110), and Cloudflare
shows a secret access key exactly once.

1. **Create the bucket.** The derived name is `apg-<project-key>-backup`;
   `bin/deploy.sh --render-only` prints it, or read `backup.bucket` from the
   project's `outputs.json`. Use the derived name unless you are deliberately
   pointing at a bucket named by somebody else's convention, in which case set
   `backup.bucket` in the manifest and the override is used verbatim.

2. **Issue an API token scoped to that bucket**, with object read and write. Paste
   the two halves into the provider at `/backup`:
   `APG_BACKUP_R2_ACCESS_KEY_ID` and `APG_BACKUP_R2_SECRET_ACCESS_KEY`. A lost
   value is replaced by issuing a **new token**, which is a rotation and not a
   retry.

3. **Deploy.** The cipher pass is generated for you. Step 6c creates the stanza
   and runs `pgbackrest check`, and **a check failure fails the deploy** — it is
   the only thing in this system that tests archiving end to end, so a release
   converging over a broken archiver is the failure it exists to prevent.

4. **Take the first full backup, by hand, at a TTY.**

   ```
   sudo bin/backup.sh --outputs /etc/agentic-postgres/projects/<key>/outputs.json \
       backup --type full
   ```

   This is deliberately not automatic: it is the first operation that writes a
   meaningful amount to a repository nobody has paid for yet. Until it runs the
   deployed document says **`awaiting_first_backup`**, which is a real state and
   not a fault.

5. **Enable the timers**, once the first backup exists:

   ```
   sudo systemctl enable --now agentic-postgres-backup-full@<key>.timer
   sudo systemctl enable --now agentic-postgres-backup-incr@<key>.timer
   ```

   They are installed disabled on purpose. A unit that fails on every boot until
   an operator is ready trains an operator to ignore it.

---

## 4. The commands

`bin/backup.sh` runs every verb **inside the database container**, because that
is where pgBackRest and the credential are. Root, because the deployed document
is root-owned and every verb reaches a container over the local socket.

| Verb | What it does |
|---|---|
| `stanza-create` | Initialise the repository. Idempotent — twice in a row exits 0, which is why step 6c runs it unconditionally rather than probing. |
| `check` | Prove archiving **and** the repository both work. Forces a WAL switch and confirms the segment arrived. |
| `backup --type full\|incr` | Take one. Retention is applied afterwards, from the config. |
| `info [--json]` | What the repository reports. `--json` prints the block the deployed document is built from. |
| `expire` | Apply retention now. Asks for confirmation; `--yes` for a scheduled sweep. |

**No verb names a bucket, a stanza, a repository prefix or a retention count.**
All four are decided once and published (ADR 0002), so there is no flag here that
could point a command at a repository the archiver is not writing to.

**`expire` is the only verb that destroys anything**, and what it destroys may be
the only copy of a database. It prints `info` first, deliberately: an operator
approving a deletion should be reading what they are deleting.

---

## 5. Reading the state

The deployed document's `backup_state` block carries the answer, and it is built
from **two sources that fail independently** (ADR 0150): `pgbackrest info` for the
repository, `pg_stat_archiver` for the archiver. A repository full of good backups
can sit behind an archiver that stopped an hour ago, and `pgbackrest info` reports
`ok` for exactly that cluster.

| `status` | Means |
|---|---|
| `unconfigured` | A credential is missing. Not "misconfigured" — a *missing secret*. |
| `awaiting_first_backup` | The stanza exists and holds no backup. Every project is here until step 4 above. |
| `ready` | A full backup exists and the archiver is not failing. |
| `failing` | Either the repository is unhealthy, or **the most recent archive attempt failed**. |
| `not_observed` | Nothing read the cluster. Not a verdict. |

**`wal_failed_count` being non-zero on a healthy cluster is normal**, and is the
single most misread number here. It is cumulative and never resets, and every
project accrues failures in the window between its container starting with
`archive_mode=on` and step 6c creating its stanza — measured at **26** on a
healthy, fully caught-up cluster. The status compares *timestamps*
(`last_failed_time > last_archived_time`), never the counter, and it does so
because `failed_count > 0` would report every project as failing, permanently,
from its first deploy.

**The archiving signal is deliberately not in the Postgres healthcheck** (ADR
0150). Three services gate on `postgres: service_healthy`, so an archiving
predicate there would turn a recoverability problem into an availability one —
and it would block the deploy carrying its own repair. The three paths that do
carry it are `backup_state.status`, `bin/backup.sh check`'s non-zero exit, and
step 6c failing the deploy.

**`latest_recoverable_time` is a floor, not the latest.** `pgbackrest info` has no
such field; what is published is the newest backup's stop time — the latest
instant this deployment can *prove* is recoverable. WAL archived afterwards
extends real recovery past it, so a drill landing later is the floor being a
floor.

---

## 6. The restore drill

```
sudo bin/restore-test.sh --target-time '2026-08-25 10:45:02+00' \
     --project-dir /etc/agentic-postgres/projects/<key>
```

It restores into a volume named for that drill alone, starts a cluster on it with
**archiving off**, waits for it to promote, queries it, writes
`evidence/restore-drill-<key>-<id>.json`, and removes everything it created —
pass or fail.

**It never mounts the live volume**, and that is enforced on the argument vector
before any container starts, not asserted in a comment. `--delta` is never passed:
pgBackRest refuses to restore over a populated directory (exit 40) and `--delta`
is the one flag that would disarm that refusal.

**It materialises a second copy of the cluster on disk.** Check free space before
the first drill of any deployment; nothing does it for you, and the headroom on
this host has never been measured.

Choosing `--target-time`:

- It must be **later** than the newest backup's stop time. Earlier is refused by
  pgBackRest before anything is written (exit 75).
- A target in the **future** restores and then fails to promote — `recovery ended
  before configured recovery target was reached` — which the command reports as a
  failed drill rather than as a success.

Add `--smoke-owner-id <uuid>` to have the drill run an RLS-protected read and a
write RPC against the restored instance. Without it those two checks are recorded
as **not applicable** rather than as passing.

---

## 7. RPO, RTO, and what has actually been measured

**RPO** is bounded by `archive_timeout`, which is 60 seconds. A quiet cluster
still forces a segment every minute, so the worst case is roughly a minute of
commits plus however long the push takes. This is a bound the configuration sets,
not a measurement of this deployment.

**RTO is measured by the drill and by nothing else.** The evidence document
records `restore_seconds`, `recovery_seconds` and their sum, all wall time the
command took around the operation. It is a measurement of *this* deployment on
*this* data — it is not a bound and it does not generalise to a larger cluster.

**What has never been measured**, and should be read as unknown rather than as
fine:

- how long a full backup or a restore takes against R2 — nothing here has ever
  dialled it;
- the disk headroom a drill needs on this host;
- what a revoked R2 token looks like to the archiver. The offline stand-in was an
  unwritable local repository, and an `EACCES` is not a `403`.

---

## 8. When it goes wrong

**`check` fails.** WAL is not reaching the repository, whatever the cluster's own
health says. Read the error: pgBackRest's messages carry an error number and a
HINT and they are relayed verbatim, deliberately. `[027]: no database found`
pointing at `pg1-path` is what a **connection-limit refusal** looks like — the one
setting in the message that is correct.

**`[037]: ... requires option: repo1-cipher-pass`** or the S3 equivalent. A
credential file is missing from `/etc/pgbackrest/conf.d`. Check the active secret
generation actually carries all three; a partial set is a repository that
authenticates and cannot decrypt, or decrypts and cannot authenticate.

**`[041]: unable to open file ... Permission denied`.** A credential file is not
owned by uid 999. This fails loudly, which is the good news, but it fails at the
first archive-push rather than at materialization.

**The status says `failing` and the counters look fine.** Read the *timestamps*,
not the counts. `last_failed_time > last_archived_time` is the predicate; the
counters are the diagnostic that justifies it.

**A drill left resources behind.** It reports this loudly and exits non-zero. The
teardown removes only what it recorded and refuses to remove anything matching the
live volume, so a leftover is safe to remove by hand once you know what left it:
`docker volume ls | grep -- -restore-`.

**`apg-diag` cannot read `postgres` logs**, any more than it can read `auth`,
`storage` or `mcp`. This will send you to a terminal on the host, and it is a
standing open item rather than a surprise.
