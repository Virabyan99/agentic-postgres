# 0158 — The deployed document is the address book, not the diagnosis

- **Status:** accepted
- **Date:** 2026-08-27
- **Session:** 11, Run 3 (`OPS-001`)
- **Related:** **D616** (`doctor.sh` is asserted not root-reachable, and the
  deployed document is `0600 root`), **D630** (`archiving_is_failing` already
  ships), **D634/D635** (read the mount point, not `/`; the host cross-check is
  not answerable off-host), **D553** (a cumulative counter cannot answer a
  point-in-time question), **D548/D145** (the state is in a field, never in the
  exit code), ADR 0002, ADR 0071, ADR 0149/0150, ADR 0157.

## Context

`OPS-001` asks that *the diagnostic command reports every required check without
secrets.* `bin/doctor.sh` has been Session 1's workstation check since Session 1,
and its own header has named this requirement as its successor the whole time.

Two things had to be decided before any check was written.

**Where the deployed mode gets its facts.** Every project publishes
`/etc/agentic-postgres/projects/<key>/outputs.json`, and it already contains a
`backup_state.status`, a `tls.status`, a `database.observed` block and a `mcp`
block. Echoing those would produce a plausible, well-formed, entirely dishonest
diagnosis: **that document records what was observed at deploy time.** A project
deployed three weeks ago whose archiver died yesterday publishes
`backup_state.status: ok` and will keep publishing it until the next deploy.

The schema settles it rather than taste. `backupState` carries
`wal_archived_count` and `wal_failed_count` — **and not `last_archived_time` or
`last_failed_time`.** So a doctor reading the document for archiver health has
only the cumulative counters available, and D553 measured exactly why those
cannot answer the question: `failed_count` stood at **26 on a healthy,
fully-caught-up cluster**, because every project fails to archive until its
stanza exists. The document is *structurally incapable* of answering the health
question it appears to answer.

**Who is allowed to run it.** The deployed document is `0600 root`
(`deployed_output.write_deployed_document`, whose docstring gives the reason: it
is a map of where the secrets are). Meanwhile
`tests/contract/test_root_script_policy.py` asserts `bin/doctor.sh` is **not**
root-reachable — *"a developer command nothing privileged calls"* — and
`test_no_root_reachable_script_invokes_a_bare_python` is parametrised over that
same closure. `doctor.sh` calls a bare `python` on purpose: its whole job in
workstation mode is to check the developer's *own* interpreter against
`.python-version`.

## Decision

**The document supplies the identities; every verdict comes from a live read.**

The document is read for *what to look at* — the project key, the database
container, the stanza, the routes, the volume — and for nothing else. It is an
address book. No `status` field in it is ever echoed as a verdict. Where a name
is absent from the document (there is no `compose` block, D592) it is derived
from `project.key` through `naming`, never re-derived a second way.

**Two modes in one command, split by argument, not by flag-on-the-same-work.**

| Invocation | Mode | Privilege |
|---|---|---|
| `bin/doctor.sh` | workstation: tools, interpreter, repository shape, locks | none |
| `sudo bin/doctor.sh --project <key>` | deployed: the seven live checks | root |

The modes do not overlap and do not run together. `--project` runs the deployed
checks *only*, which is what keeps the bare `python` confined to workstation mode
— under `sudo`, `secure_path` makes an operator's activated venv invisible, and a
`check_python_minor` running there would report a false failure on every host.
The deployed mode resolves its interpreter the way `deploy.sh` does.

**`test_root_script_policy`'s assertion is kept, not flipped.** No privileged
*script* invokes `doctor.sh`; an operator typing `sudo` is not a script. What
changes is that the comment's premise — "a developer command" — is now half
true, so a **stricter** test is added beside it: the bare `python` must be
unreachable from the deployed path. That is the property that actually matters
once the command has a root mode, and it did not exist before.

**Four verdicts.** `ok`, `warn`, `problem`, `unknown` — ADR 0157's three plus an
advisory tier. That ADR's "what this does not decide" predicted this exactly:
*"whether `undetermined` should ever be non-blocking … `OPS-001`'s `doctor.sh` is
where that pressure will come from first."* It came from disk headroom, which has
a real middle state. `warn` exits `0`; `problem` and `unknown` exit `6`.

**Reuse, do not rebuild** (D618, D630). Repository health is
`bin/backup.sh --outputs … info --json`, which is the same function the deploy
publishes from (ADR 0149). Archiver health is `backup_report.archiving_is_failing`
over a live `pg_stat_archiver` read — Session 10 already shipped that predicate
with rig 7 arm G's numbers in its docstring, and deriving a second threshold here
would be the D57/D262 pattern. **Nothing reads an exit code where a state field
exists** (D548: `pgbackrest info` exits 0 for a stanza that does not exist; D145:
`postgrest --ready` returns 0 while every request 404s).

**The disk threshold is derived, not typed.** A restore materialises a second
copy of the cluster, so the number that matters is `du` of PGDATA against the
available space on the filesystem holding it: below one copy is a `problem`,
below two is a `warn`. And it reads **the mount point, never `/`** (D634) —
measured in Run 1, the two coincide on a developer machine, so a check reading
`/` would pass there for a reason that does not generalise.

## Consequences

- A doctor run costs one `docker ps`, a handful of `docker exec`s and one
  `pgbackrest info` (which is a network round trip to R2). It is not free and it
  is not a healthcheck; it is a command an operator runs.
- **`bin/doctor.py` joins `DEPLOYED_DOCUMENT_READERS`** in
  `test_container_selectors.py`, so D600's class guard covers it from its first
  commit rather than after its first failure.
- The workstation mode is untouched. `bin/doctor.sh` with no arguments still
  exits `3` and still names what is missing, and the README's bootstrap step
  keeps working.
- `unknown` exits non-zero. A check that could not run is not a passing check,
  and a monitoring caller that treated it as one would be back at D600.

## What the battery established

Nine arms, **9 killed, 0 survived, 0 defective** — every control green in the
same invocation and unreachable by its arm, every arm `FAILED` rather than
`ERROR`.

The two that guard this ADR's reasoning rather than its arithmetic:

- **M1 (an unknown check starts exiting 0): KILLED.** This is the single
  mutation that would turn the whole command back into D600 — a diagnosis that
  measured nothing reporting success.
- **M2 (unknown ranked below warn): KILLED.** The severity order is asserted, not
  merely written down. An `unknown` beside a `warn` must still decide the exit
  code, because nobody knows which of the other three it would have been.

**M5 (the disk threshold stops being one copy of the cluster)** is the arm that
proves the threshold is derived. A percentage-based check would have survived it.

## What this ADR rests on, and what re-opens it

`test_the_schema_still_gives_the_backup_state_no_timestamps` asserts the premise
directly: `backupState` has `wal_archived_count` and `wal_failed_count` and no
`last_archived_time`. **If that block ever gains the timestamps, the argument
that the document cannot answer archiver health stops holding** — and the test
fails, pointing whoever added them back here rather than letting the field be
quietly trusted. That is the shape D600's repair called for: guard the reasoning,
not the field.

## What this does not decide

**Whether `apg-diag` gains a `doctor` verb.** The read-only agent account
(ADR 0071) cannot run any of this today, and D380 — *`apg-diag` cannot read
`auth`, `storage` or `mcp` logs* — has sent an operator to a terminal in three
consecutive sessions. Widening that allowlist is an authority decision about what
an unprivileged account may see, it is explicitly listed as "an ADR-shaped
decision nobody has taken", and bundling it into a run about checks would decide
it by accident. The deployed checks live in `bin/doctor.py` precisely so that a
future `apg-diag` verb can call them without `doctor.sh` entering the
root-reachable closure.

**Whether the host and the container agree about disk.** They cannot be compared
on a developer machine at all — Docker Desktop runs the daemon in its own VM, so
the two `df` readings are of two kernels (D635). The container-side reading is
measured and faithful; the cross-check is a `host`-mode node id for Run 9.
