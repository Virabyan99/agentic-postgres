# 0150 — A broken archiver is visible, and it does not take the database down

Status: accepted
Date: 2026-08-23
Session: 10, Run 7

Affects: D528, D534, D535, D553–D557, ADR 0033, ADR 0149, `REC-WAL-001`,
`src/agentic_postgres/backup_report.py`, `bin/deploy-project.py`,
`bin/backup.py`, `compose.yaml`

## Context

D534 left one question explicitly open for this run: *"Whether the Postgres
healthcheck gains an archiving clause or a second check carries it is decided in
Run 7, with the numbers in hand."* The plan's Run 7 entry predicted the answer —
"the healthcheck goes unhealthy" — and rig 7 measured what that would cost.

Rig 7 also had to re-measure the signal itself. Run 1 characterised a broken
archiver with `archive_command=/bin/false` (D534, D535); a shell builtin
returning 1 is neither of this run's two arms, and the question is whether a real
pgBackRest failure has the same signature.

## Decision

### 1. The status predicate compares timestamps; it does not count failures

```sql
CASE WHEN last_failed_time IS NULL          THEN ok      -- never failed
     WHEN last_archived_time IS NULL        THEN failing -- never archived
     WHEN last_failed_time > last_archived_time THEN failing
     ELSE ok END
FROM pg_stat_archiver
```

Measured, arm G, with the arm and its control in one invocation and the rig's own
churn under a control of its own:

| | `archived_count` | `failed_count` | predicate |
|---|---|---|---|
| healthy baseline | 8 → **12** | 11 → 11 | `ok` |
| archiving broken | 12 → **12** (frozen) | 11 → **26** | **`failing`** |
| repaired (control) | 12 → **21** (catches up) | 26 → 26 | `ok` |

**`failed_count > 0` is unusable as a status, and this is the finding that
matters (D553).** The healthy, fully-caught-up cluster in the last row carries
`failed_count = 26`. The counter is cumulative and never resets, and **every
project accrues failures before its stanza exists** — the window between the
container starting with `archive_mode=on` and step 6c running `stanza-create` is
a window in which every archive attempt fails. A `failed_count > 0` status would
therefore report **every project as failing, permanently, from its first deploy**.

This refines D535 rather than contradicting it. D535 says `failed_count` is the
value that *moves* while `last_failed_wal` pins to the oldest stuck segment, and
that is right — **for detecting a change across an interval**, which is what
`REC-WAL-001` asserts. A **point-in-time status** is a different question and
needs the timestamps. Two proofs, two readings of one view, and conflating them
is how the count ends up in a status field.

`archived_count` alone is no better: it freezes during the failure and then
*catches up* (12 → 21 across the repair), so a reader sampling it twice around a
repair sees a healthy-looking increase.

### 2. `wal_archived_count` and `wal_failed_count` are published, and stop being null

Run 6 returned both as `None` and a test asserted it, because they come from the
archiver rather than from the repository. Run 7 populates them, and the two move
together with the predicate: a document that carries a `failing` status carries
the counters that justify it.

The counters are published **as measured, cumulative and unreset** — including
the pre-stanza failures. They are a diagnostic, not the status, and the schema
already says the count is what a reader watches rather than `last_failed_wal`
(D535).

### 3. The archiving signal does NOT go in the Postgres container healthcheck

**This is the reversal of the plan's prediction, and it is measured.**

Arm F: a healthcheck reading the predicate goes `unhealthy` in ~15s — and the
container stays `running`, `RestartCount` **0**, and the database **answers
queries throughout**. So a red healthcheck costs nothing at the container level.

Arm H is where the cost is, and it is severe:

| | `compose up --wait` | container | serving? |
|---|---|---|---|
| archiving predicate as healthcheck | **exit 1**, "container … is unhealthy" | running, unhealthy | **yes, answered a query** |
| `pg_isready` (control, same broken archiver) | **exit 0** | running, healthy | yes |

Two consequences follow, and the second is decisive:

1. **The failure names nothing.** `compose up --wait` says "container
   compose-postgres-1 is unhealthy" — no mention of archiving, of WAL, or of a
   repository. Step 6c already fails the deploy on exactly this condition and
   says *"WAL archiving does not work for this project… the cluster is up and
   serving — this is the archiver"*. Moving the signal earlier replaces a named
   diagnosis with an unnamed one.

2. **Three services gate on `postgres: condition: service_healthy`** — the
   pooler, the auth service and storage. An archiving predicate in that
   healthcheck means **a backup problem stops the application from starting**.
   That converts a recoverability incident into an availability incident, and it
   does so on a cluster that is serving perfectly.

   Worse, it blocks its own repair: fixing a broken archiver — new credentials,
   a corrected prefix — is done **by deploying**, and a deploy that cannot get
   past `compose up --wait` cannot deliver the fix.

So `compose.yaml`'s healthcheck stays `pg_isready`. The archiver's signal reaches
an operator through three paths that already exist or are added here:

- **the deployed document**, `backup_state.status: failing` with both counters;
- **`bin/backup.sh check`**, non-zero (Run 6), and `info` reporting the status;
- **the deploy**, which fails at step 6c with a named reason (Run 6).

## Consequences

**`pg_isready` still cannot see a broken archiver, and that is now a decision
rather than a gap.** D534's measurement stands — `accepting connections` at every
sample while `pg_wal` grew — and arm G reproduced it with a real pgBackRest
failure: 14 segments on disk, `pg_isready` accepting, `archived_count` frozen.
What changed is that something else looks now.

**A cluster whose archiver has been broken since before its stanza existed reads
as `failing` correctly, and one that recovered reads as `ok` correctly**, and
those are the same cluster ten minutes apart. That is the property the timestamp
predicate buys and the counter predicate cannot.

**The two arms are not equally faithful, and the write-up says so (D554).** The
wrong-prefix arm is exact — it is the same misconfiguration a bad
`repository_prefix` produces. The revoked-credential arm is a **stand-in**: rig 7
made the posix repository unwritable, and an `EACCES` from a filesystem is not a
`403` from R2. What is common is what the cluster sees — `archive_command`
exiting non-zero — and that is what `pg_stat_archiver` records. **The real
revoked-credential arm needs the host trip**, and `REC-WAL-001` is where it lands.

**`REC-WAL-001` is still a placeholder and is still Run 9's.** Run 7 builds the
signal and proves the mapping offline; the requirement's node id lives in
`tests/recovery/` and needs a deployment. Nothing here empties `FUTURE_STUBS` or
activates a registry id.

## Alternatives considered

**Put the predicate in the Postgres healthcheck, as the plan predicted.**
Rejected on arm H: three services gate on that health, so a backup problem would
stop the application from starting — on a database that is serving — and would
block the deploy that carries the repair.

**A second container whose healthcheck carries the archiving predicate.**
Rejected for this run, and it is the shape a future session would use if the
signal must be visible to `docker ps`. It is one more service per project for a
value the deployed document already carries, and nothing today reads container
health except `--wait` and `depends_on`, both of which are exactly what must not
see it.

**`failed_count > 0` as the status.** Rejected on measurement: 26 on a healthy
cluster, and every project accrues failures before `stanza-create`.

**`archived_count` stalling as the status.** Rejected: it requires two samples
and a window, it cannot distinguish "stalled" from "idle" on a quiet cluster, and
it reads healthy across a repair because the archiver catches up.

**Reset the statistics after `stanza-create` so `failed_count > 0` becomes
usable.** Rejected: `pg_stat_reset_shared('archiver')` would discard the
diagnostic the counters exist to provide, and it would make the deploy a writer
of statistics — a deploy that edits the evidence is worse than one that reads it
carefully.
