# 0149 — The backup command, step 6c, and what a repository can honestly report

Status: accepted
Date: 2026-08-23
Session: 10, Run 6

Affects: D519, D520, D529, D535, D548–D552, ADR 0002, ADR 0017, ADR 0033,
ADR 0133, ADR 0146, ADR 0148, `bin/backup.sh`, `bin/backup.py`,
`bin/deploy-project.py`, `schemas/outputs.schema.json`

## Context

Run 4 gave the cluster an archiver and a rendered `pgbackrest.conf`. Run 5 gave
it an identity that can log in. Nothing has ever run a pgBackRest command from
this repository, and `observe_backup`'s own docstring says in as many words that
**Run 6 replaces it with an observer that asks the repository** — a sentence
that would otherwise become D276's shape, a comment describing work nobody
wrote.

Rig 6 measured what `pgbackrest info` actually reports, in five phases against
the Run 4 derived image, with the rig's own setup under a control. Three of its
findings change what this run could have been written to do.

## Decision

### 1. Five verbs, and retention is never restated

`bin/backup.sh` wraps `bin/backup.py`: `stanza-create`, `check`,
`backup --type full|incr`, `info`, `expire`. Root, because the deployed document
and the secret generations are root-owned and every verb reaches a container over
the local socket — `bin/storage-admin.sh`'s shape exactly.

**`retain_full` reaches pgBackRest through the config and through nothing else.**
It is already in the rendered `pgbackrest.conf` as `repo1-retention-full` (Run 4),
and rig 6 confirmed `expire` applies it with **nothing on the command line** —
exit 0, retention read from the file. A `--repo1-retention-full` flag here would
be D495 and D463's shape: one value stated twice, where the second statement is
the one that wins and the first is the one people read.

### 2. Step 6c creates the stanza unconditionally, because it is idempotent

**Measured: `stanza-create` run twice in a row exits 0 both times.** So step 6c
does not ask first. "Create the stanza if absent" was the plan's wording and it
implied a probe; the probe is unnecessary, and a probe-then-act is a race in a
place that does not need one.

Step 6c runs after step 6b and before step 7 — the cluster exists, migrations
have applied, `backup_user` can log in, and the deferred services are up. It
does `stanza-create`, then `check`.

**A `check` failure is a deploy failure with a named reason, not a warning.**
`check` is the only thing in this system that proves archiving works end to end:
it forces a WAL switch and confirms the segment arrived in the repository. A
deploy that converged with a broken archiver is a deploy that reports success
over the exact failure this session exists to prevent.

### 3. `pgbackrest info` exits 0 in every state, including for a stanza that does not exist

**This is the finding that shaped the observer, and it is D145's shape** —
`postgrest --ready` returning 0 while every request 404s. Measured, all four
phases:

| repository state | `info` exit | `status.code` | `status.message` |
|---|---|---|---|
| no stanza | **0** | 1 | `missing stanza path` |
| stanza, no backups | **0** | 2 | `no valid backups` |
| one full backup | **0** | 0 | `ok` |
| a stanza that was never named anywhere | **0** | 1 | `missing stanza path` |

**The observer reads `status.code` and never the exit code.** An observer built
the obvious way — run `info`, check it succeeded, report healthy — would report a
healthy repository for a stanza that does not exist, on every project, forever.

### 4. The status ladder, and a fourth enum value

`backup_state.status` gains **`awaiting_first_backup`**:

| what was read | status |
|---|---|
| backups disabled, or no repository credential in the active generation | `unconfigured` |
| `status.code` 1 — the stanza is not there after step 6c ran | `failing` |
| `status.code` 2 — stanza exists, no backup yet | **`awaiting_first_backup`** |
| `status.code` 0 — at least one backup, and step 6c's `check` passed | `ready` |

**The fourth value exists because the state is real, expected, and none of the
other three describes it.** Every project is in it immediately after its first
Session 10 deploy: the plan puts the first full backup in an operator's hands at
a TTY (Runs 11+), so the deploy converges with a stanza and no backup. `ready` is
false — nothing can be restored. `failing` is false and would be worse than
useless: a status that is red on every first deploy is a status operators learn
to ignore, which is the argument `provision-host.sh` already makes for installing
timers disabled. `unconfigured` is false and actively misleading — it is the
value for a **missing credential**, so an operator seeing it would go hunting for
a secret that is present and correct.

**This extends outputs v13 rather than opening v14.** ADR 0146 refused "three
separate versions, one per run"; it did not refuse extending the session's own
version before anything has ever deployed it. **v13 has never left this tree** —
both host projects are on v12 — so a v13 document with this enum value is a
document nothing has to migrate. That it was missed at all is the third instance
of ADR 0053's cost (D255, D308): a version chosen once from the whole surface,
and still short a value that only measurement surfaced.

### 5. `latest_recoverable_time` is a proven floor, and `info` does not report it

**`pgbackrest info --output=json` has no latest-recoverable-time field.** The
schema's description said it "is read from `pgbackrest info`" (D529); the
measurement says there is nothing there to read. What `info` carries is:

- `backup[].timestamp.stop` — an epoch integer, per backup;
- `archive[].min` / `archive[].max` — WAL **segment names**, with no timestamp
  anywhere in or beside them.

So the quantity a reader wants — the most recent instant recoverable by replaying
archived WAL — is not derivable from `info` at all. What is derivable is the
newest backup's stop time, and **that is published, named in the schema for what
it is: the latest point this deployment can *prove* is recoverable.**

**A drill that lands later than this value is not a contradiction.** It is the
floor being a floor: WAL archived after the newest backup extends real recovery
past it, and Run 8's evidence document records the **achieved** recovery point as
its own field precisely because the requested target, the proven floor and the
achieved point are three different numbers (D529). The schema description is
corrected in this run rather than left saying something the measurement refutes.

### 6. What Run 6 does not observe

`wal_archived_count` and `wal_failed_count` stay **null**. They come from
`pg_stat_archiver`, which is Run 7's subject and D534's measurement — the
archiver's own counters, not the repository's report. A `ready` status beside two
null counts is honest: the repository was read, the archiver was not.

`status: ready` does not depend on them, and that is defensible because
**step 6c's `check` is itself an archiving proof** — it forces a WAL switch and
confirms arrival. Run 7 adds the continuous signal; Run 6 has the point-in-time
one.

## Consequences

**The deploy now fails on a broken archiver, and that is new.** Before this run a
project with `archive_command` misconfigured deployed cleanly and published
`not_observed`. D534 measured what that looks like from outside: `pg_isready`
answers *accepting connections* while `failed_count` climbs 11 → 15 → 26 and
`pg_wal` fills. Step 6c is the first thing in this system that turns that into a
non-zero exit.

**`observe_backup` can now return `ready`, and its Run 3 test asserted it could
not.** That test is replaced by a stricter one rather than deleted: `ready`
requires `status.code == 0` **and** a backup label, and the three non-ready
ladders are each asserted separately. Run 3's assertion was correct for Run 3 —
`ready` on the strength of three files existing would have been a value that
looked measured and was not — and what makes it safe to relax is that something
now reads the repository.

**`bin/backup.sh` joins `SHELL_COMMANDS` and `bin/backup.py` joins
`PYTHON_COMMANDS`**, in the same commit that creates them.
`test_every_command_in_bin_is_covered_by_this_module` refuses the alternative,
which is the whole reason it exists — Run 8 of Session 8 found twelve commands
outside those lists, each passing all nine checks the moment it was listed.

**`FUTURE_STUBS` is unchanged.** `bin/restore-test.sh` is still a stub and is
still Run 8's. This run adds a command; it does not promote one.

## Alternatives considered

**Probe for the stanza before creating it.** Rejected on measurement:
`stanza-create` is idempotent, so the probe buys nothing and adds a window in
which the answer can change.

**Treat `status.code` 2 as `unconfigured`.** Rejected: it is the value for a
missing credential, and conflating the two sends an operator looking for a secret
that is present. The states differ in what the operator must do next, which is
the only thing a status is for.

**Treat `status.code` 2 as `failing`.** Rejected: it is the state of every
project on its first deploy, and a status that is red by design on day one is one
nobody reads on day two.

**Publish `latest_recoverable_time` as null until something can measure it
exactly.** Rejected: the newest backup's stop time is a real measured quantity
from the repository's own report, and a required field that is always null is
D519's defect inverted — published, and reaching nothing.

**Derive `latest_recoverable_time` from `archive[].max`.** Rejected: it is a WAL
segment name and carries no time. Converting one to a timestamp means asking the
database when that segment was archived, which is a second authority over a value
the repository is supposed to be reporting.

**Put the retention count on the `expire` command line "to be explicit".**
Rejected, and measured unnecessary: `expire` reads it from the config. D495 and
D463 are the record of what a second statement of one value costs.
