# 0152 — What a restore drill can honestly report

Status: accepted
Date: 2026-08-25
Session: 10, Run 8

Affects: D267, D529, D550, D559–D566, ADR 0045, ADR 0149, ADR 0151,
`REC-EVID-001`, `REC-PITR-001`, `src/agentic_postgres/restore_drill.py`,
`bin/restore-test.py`, `evidence/`

## Context

D529 is a prohibition before it is a design:

> **RTO is wall time recorded by `bin/restore-test.sh` itself around the
> restore**, and the **latest recoverable time is read from `pgbackrest info`**,
> never from the clock and never from the requested target. The evidence document
> records requested target **and** achieved recovery point as separate fields,
> because a restore that lands early is the failure this pair exists to expose.

Session 9's handoff states the same thing as a rule: Session 10 must not *"record
a recovery time it did not measure."* D267 is the general form — never write a
measurement you did not run.

Every field below is a *measurement*, and rig 8 established where each one comes
from and what the plausible wrong source for it is. This decision exists because
for two of the six fields, the plausible wrong source is **more obvious than the
right one** and produces a well-formed value.

## Decision

### 1. The achieved recovery point is `pg_last_xact_replay_timestamp()`, from the restored instance

Measured, one drill, every candidate read in the same invocation:

| read | value | what it is |
|---|---|---|
| `current_setting('recovery_target_time')` | `10:45:02.599903+00` | the **requested** target |
| `pg_last_xact_replay_timestamp()` | **`10:45:00.109084+00`** | the **achieved** recovery point |
| server log, *last completed transaction was at log time* | `10:45:00.109084+00` | the same instant, in words |
| server log, *recovery stopping before commit of transaction 757, time* | `10:45:04.774492+00` | the first transaction **not** applied |
| `pg_control_checkpoint().checkpoint_time` | `10:45:14+00` | the **end-of-recovery checkpoint** |
| `pg_last_wal_replay_lsn()` | `0/50039F0` | the achieved **LSN** |
| `pg_last_committed_xact()` | *(empty)* | unavailable: `track_commit_timestamp` is off |

Two of those are traps and both would have looked measured.

**`checkpoint_time` is the trap that matters.** It is a real timestamp on the
restored instance, it is available from a catalog function, and here it was
**fourteen seconds after the recovery point**. It records when the end-of-recovery
checkpoint was written — wall time during the drill — and it has nothing to do
with where recovery landed. It is this project's defect pattern in its purest
form: *a value that looked measured and was not*, and it would drift further the
slower the machine.

**`recovery stopping before commit of transaction …, time …` is the near miss.**
It is the correct-looking line in the log and it names the first transaction that
was **not** applied — later than the achieved point, by definition. Reading it as
the recovery point overstates recovery by exactly one transaction's worth of
time.

`pg_last_xact_replay_timestamp()` and the *last completed transaction* log line
agree to the microsecond, and the SQL function is preferred for ADR 0149's
reason: a log line is a third party's formatting decision, a catalog function is
the product's own report.

**The control is free and it is exact.** On the live cluster — which never
recovered — `pg_last_xact_replay_timestamp()` and `pg_last_wal_replay_lsn()` both
return **NULL**. So a drill that read the wrong instance publishes an empty field
rather than a plausible one, and an empty field is a failure here rather than a
value.

### 2. The requested target is read back from the restored instance, not echoed from the command line

`current_setting('recovery_target_time', true)` returns what pgBackRest wrote
into `postgresql.auto.conf` and what PostgreSQL then parsed. Echoing
`--target-time` back into the document would make the field a copy of an input,
and a copy of an input cannot disagree with anything — which is the whole reason
D529 asks for the pair.

They *do* disagree, always: the achieved point is the last transaction at or
before the target, so it is earlier by however long the cluster was idle.

### 3. The backup set comes from pgBackRest's own restore, and an unreadable one fails the drill

Measured, and this is where the product's rendered configuration gets in the way:

| `log-level-console` | restore stdout | restore stderr |
|---|---|---|
| `warn` — what `build_pgbackrest_conf` renders | **0 bytes** | **0 bytes** |
| `info` | 6 lines, including the backup set | 0 bytes |

**A successful restore is completely silent at the product's own log level.** A
command that parsed the restore's output for a backup set would find nothing at
all on a production render, and would publish an empty field on every drill that
worked. So `bin/restore-test.py` passes `--log-level-console=info` on the restore
command line, overriding the rendered config for its own invocation only.

The line, verbatim:

```
2026-08-25 10:45:06.244 P00   INFO: repo1: restore backup set 20260825-104447F, recovery will start at 2026-08-25 10:44:47
```

Parsing a third party's log line is D374's shape — *a test can check a string its
target cannot contain* — so it is bounded two ways:

- **A restore whose output does not name a backup set fails the drill.** The
  field is never left null and never inferred. If pgBackRest changes the wording,
  the drill goes red on a working restore, which is the failure direction this
  repository accepts.
- **The label is cross-checked.** `pgbackrest info --output=json` is read
  independently and the parsed label must appear among its backups; the backup's
  **type** (`full`, `diff`, `incr`) is taken from *there*, not from the label's
  trailing letter. Two independent reads that have to agree, rather than one read
  and a naming convention.

What was rejected: **selecting the backup set ourselves** and passing `--set`.
pgBackRest's rule is *the newest backup set whose stop time is less than the
target* — it says so in its own error (see 5) — and re-implementing it here would
put a second authority in the path of the one thing the drill is proving.

What does **not** work, measured: `backup_label` in the restored PGDATA carries
`LABEL: pgBackRest backup started at 2026-08-25 10:44:47.988569+00`, which is a
sentence, not the backup set `20260825-104447F`.

### 4. RTO is wall time this command measured, around a phase it names

Two spans, recorded separately, because they fail for different reasons and an
operator sizing a maintenance window needs both:

- **restore** — `pgbackrest restore` start to exit. Bound by repository read
  throughput and cluster size.
- **recovery** — the drill container starting to `pg_is_in_recovery()` returning
  false. Bound by how much WAL lies between the backup set and the target.

`rto_seconds` is their sum plus the drill's own setup, measured by
`time.monotonic()` around the whole span. pgBackRest reports its own elapsed time
(`restore command end: completed successfully (5337ms)`) and it is recorded
beside ours rather than instead of it — it excludes recovery entirely, so a
document carrying it alone would understate an RTO by the part that scales with
the recovery window.

It is a **measurement of this deployment on this data**, never a bound. The
document says so in the field's own units and §3 of the plan says so about the
unmeasured case.

### 5. Latest recoverable time is `pgbackrest info`'s floor, and the achieved point is legitimately later

`backup_report.summarise` publishes `latest_recoverable_time` as the newest
backup's stop time, and ADR 0149 already records why: **`pgbackrest info` has no
latest-recoverable-time field** (D550). It is a proven floor, not the true latest.

Rig 8 confirmed the prediction rather than assuming it:

```
newest backup stop time   2026-08-25T10:42:29Z      <- the published floor
achieved recovery point   2026-08-25T10:42:30.69Z   <- LATER, by design
```

The document records both, and the drill does **not** treat `achieved > floor` as
an inconsistency. It treats `achieved < floor` as one, because that is a restore
that landed before a point the repository claims is recoverable.

pgBackRest states its selection rule in the error it raises when the rule cannot
be satisfied — measured, arm H4, exit **75**:

```
ERROR: [075]: unable to find backup set with stop time less than '2026-08-25 10:44:46.51886+00'
```

### 6. A target the archive cannot reach is a failure, and it fails at the instance, not at the restore

Measured, arm H3 — a target one hour in the future:

| step | result |
|---|---|
| `pgbackrest restore` | **exit 0** |
| the restored instance | `FATAL: recovery ended before configured recovery target was reached` |
| `pg_is_in_recovery()` | unreachable — the instance never accepts connections |

**A restore that exits 0 has not proved anything.** This is D145's shape and
D548's — `postgrest --ready` returning 0 while every request 404s,
`pgbackrest info` exiting 0 for a stanza that does not exist — a third time, in a
third third-party command. The drill's verdict comes from querying the promoted
instance, and a drill whose instance never promotes reports a failure with the
container's own log attached.

So the command distinguishes three states, and never collapses them: **promoted**
(the instance answers and `pg_is_in_recovery()` is false), **still recovering**
(the container is running and the instance does not answer), **dead** (the
container has exited). Only the first is a successful drill.

### 7. What the evidence document carries, and what it never does

Written to `evidence/restore-drill-<key>-<drill_id>.json`, which is gitignored
like everything else under `evidence/`.

| field | source |
|---|---|
| `project_key`, `stanza` | the deployed `outputs.json` — never re-derived (ADR 0002) |
| `drill_id`, `drill_volume`, `drill_container` | `naming.restore_drill_names` |
| `backup_set.label` | pgBackRest's restore output at `--log-level-console=info` |
| `backup_set.type` | `pgbackrest info --output=json`, cross-checked by label |
| `requested_target` | `current_setting('recovery_target_time')` on the restored instance |
| `achieved_recovery_point` | `pg_last_xact_replay_timestamp()` on the restored instance |
| `achieved_lsn` | `pg_last_wal_replay_lsn()` on the restored instance |
| `latest_recoverable_time` | `backup_report.summarise` — the floor (D550) |
| `timeline_id` | `pg_control_checkpoint()` — 2 on a promoted restore, 1 on the live cluster |
| `rto_seconds`, `restore_seconds`, `recovery_seconds` | `time.monotonic()`, this command |
| `schema_version` | `max(version)` from the restored instance's `schema_migrations` |
| `smoke` | the checks, each with its own verdict |
| `verdict` | computed from the above; never written by hand |

**What it never carries**, and this is §6 of the plan restated so that a future
field has to argue against it: a credential, a cipher pass, a connection string,
a bucket URL with a signature in it, or any row of restored user data. It carries
identifiers, timestamps, an LSN, counts and verdicts.

One measured comfort: pgBackRest redacts its own secret when it echoes its
command line — `--repo1-cipher-pass=<redacted>` — so even the captured restore
output at info level carries no value. That is a property of pgBackRest, not of
this repository, and it is recorded as a happy accident rather than as a control.

### 8. This document is not a claim

ADR 0045 stands: a requirement complete in a checkout is not a claim, and a claim
needs a node id marked `live_host` or `external`. The drill's evidence document
is an **artefact a proof reads**, and `REC-EVID-001` is the proof — Run 9's, in
`tests/recovery/`, against a deployment. Nothing here activates a registry id and
nothing here writes a verdict into `evidence_claims`.

## Consequences

- The drill needs the restored instance to answer queries before it can report
  anything at all, which is `REC-SMOKE-001`'s premise and the reason "a restore
  that cannot be verified is a failed restore" is in the command's `--help` and
  has been since Session 1.
- The drill overrides the rendered `log-level-console` for its own invocation.
  That is the only place in this repository where a rendered configuration value
  is overridden on a command line, and it is done because the rendered value
  makes a successful restore silent.
- `pg_last_xact_replay_timestamp()` returning NULL is the drill's own control on
  reading the right instance, and it costs nothing.
- A future session that turns on `track_commit_timestamp` gains
  `pg_last_committed_xact()` as a second reading of the same instant. It is off
  today and the document says so rather than omitting the row.

## Alternatives considered

**Record RTO as one number.** Refused: restore time scales with the cluster,
recovery time scales with the distance from the backup set to the target, and an
operator lowering one of those is not lowering the other.

**Take the achieved recovery point from the requested target.** This is the
failure D529 exists to prevent, written down so that it cannot arrive as a
simplification.

**Take it from `pg_control_checkpoint().checkpoint_time`.** The most plausible
wrong answer, measured at fourteen seconds late, and it would look right on a
fast machine and drift on a slow one.

**Parse the server log for *last completed transaction was at log time*.** It is
correct, it agrees to the microsecond, and it is a third party's formatting where
a catalog function exists. Recorded here because it is the cross-check that
confirmed the function, not the source.

**Publish the drill's evidence into `outputs.json`.** Refused: `outputs.json` is
the deployed document and describes convergence. A drill is an event, not a state
of the deployment, and ADR 0146 refused a fourteenth outputs version inside the
session that shipped the thirteenth.
