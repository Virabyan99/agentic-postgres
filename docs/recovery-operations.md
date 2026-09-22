# Recovery operations

The second copy of every backup, the kit an operator holds off the host, the
restore onto a replacement, and the eight failure rehearsals. Session 18, ADRs
0188–0193. The node-loss runbook is the ordered procedure for the day the host
is gone ([node-loss-runbook.md](node-loss-runbook.md)); this page is what you
run on the ordinary days before it, and what each command reads.

Every command here runs as root at a terminal. None of them holds a
credential in its own process: the mirror copy and the restore run inside
containers that mount the secret files the generation materialised, and the
rehearsals read the doctor's verdicts and exit codes.

---

## 1. The mirror

A project whose manifest enables `backup.mirror` (manifest schema 4) has its
primary backup repository copied, object for object, to a bucket at a second
provider by a nightly host unit. The archiver never knows the mirror exists:
a lost mirror costs the primary nothing (ADR 0188). The mirror is written by
`mc mirror --overwrite --remove`, so the primary's retention is the mirror's
(D1000), and a copy that exits non-zero has left objects behind that the next
pass completes (D1001).

```yaml
backup:
  mirror:
    enabled: true
    endpoint: s3.eu-central-003.backblazeb2.com   # never the primary's provider
    region: eu-central-003
    # bucket: apg-<key>-backup-mirror             # derived when omitted
```

The mirror pair (`APG_MIRROR_S3_ACCESS_KEY_ID`, `_SECRET_ACCESS_KEY`) lives
under `/backup` in the project's Infisical project and exists exactly when the
mirror is enabled (ADR 0191): a mirrored project that lacks it fails the
materialize step by name, and an unmirrored project never asks for it.

```
sudo bin/backup.sh --outputs <outputs.json> mirror          # one copy, by hand
sudo bin/backup.sh --outputs <outputs.json> schedule status  # three timers for a mirrored project
sudo bin/doctor.sh --project <key>                           # the `backup mirror` check
```

What each reads:

| Reader | What it says |
|---|---|
| `backup.sh mirror` exit | 0 only when the pass completed and the mirror bucket listed; the copy record `mirror-state.json` beside the deployed document is written only then |
| the unit `agentic-postgres-backup-mirror@<key>.service` | the same verb; a failed pass is a failed unit in `systemctl list-units --failed`, and no record |
| the doctor's `backup mirror` check | `never` until a copy completed, `ok` while the last record is under two days old, `warn` after. **It reads the record, not the pass**: one failed copy is the unit's failure, not this check's (D1016) |
| `backup_state.mirror` in the deployed document | the copy time the last deploy observed: a snapshot, never the diagnosis (ADR 0158) |

## 2. The kit

What an operator holds off the host so a replacement can be built on the day
this one is gone: the host and capability manifests and, per project, the
manifest, `bootstrap-state.json`, the deployed document and `secrets.txt` --
every secret's NAME, provider path and origin, and never a value (ADR 0189).

```
sudo bin/dr-kit.sh export --host host.yaml --capabilities capabilities.yaml \
     --project project.alpha.yaml --project project.beta.yaml --output <dir>
bin/dr-kit.sh verify <dir>
```

Export it after every deploy that changed a manifest, copy it off the host,
and verify the copy. A kit that holds a value is a second secret store with
no rotation and no owner; `verify` refuses one.

## 3. The restore onto a replacement

The order on a replacement host is **adopt, materialize, render, restore,
deploy** (D1008, ADR 0192), and the runbook carries it step by step. What
`restore.sh` promises: it restores into the project's own volume only when
that volume holds no cluster and no container mounts it, never passes
`--delta`, never removes a volume, and reads the mirror through the restore
container's own environment so that the primary's credential is never
present (D1009). Its `--plan` prints and starts nothing, and refuses a
populated volume with exit 7 exactly as a real run would.

```
sudo bin/restore.sh --outputs <kit>/projects/<key>/outputs.json \
     --project <kit>/projects/<key>/project.yaml --rendered-dir <rendered> \
     --from mirror --latest [--plan]
```

The record it writes, `evidence/restore-<key>-<id>.json`, is the drill's shape
with `source` and `identity`: the restored cluster's `instance_uuid` must be
the kit's, or the verdict fails and says so.

## 4. The rehearsals

The table below is the list, and it carries no count of its own -- a number
in this paragraph was wrong for two sessions (D1595, D1664). Each scenario is
an induce, an observe and a reverse over a reader that
already exists (ADR 0190, ADR 0193). One at a time, never during a backup,
and never on a host whose mirror is not yet enabled for the WAL scenario.
`--plan` prints the three phases with every command and does nothing.

```
sudo bin/rehearse.sh <scenario> --outputs <outputs.json> [--plan]
sudo bin/rehearse.sh reverse                         # after an interrupted one
```

| Scenario | Induces | Reads | Reverses |
|---|---|---|---|
| `service-termination` | SIGKILL to `edge-probe`'s main process, never `docker kill` (D1015) | the restart count, the health route, the doctor's containers and route checks | the restart policy; `docker start` only if it did not |
| `database-restart` | `docker restart` of the cluster | the doctor's database, containers and route checks; every dependent's restart count; the agent route's 401 | the restart is its own reversal |
| `backup-credential-failure` | nothing; one `pgbackrest check` with a throwaway credential in its environment | that check's exit, and the deployed credential's check as the control | nothing was changed |
| `wal-archiving-failure` | REJECT rules for the MIRROR endpoint from the backup network in DOCKER-USER | the mirror copy's exit; the archiver check as the control | the rules deleted by comment; the next copy |
| `registry-loss` | the port registry moved aside | every `database-ports.sh` verb's exit 4 | the registry moved back, bytes compared |
| `disk-threshold` | nothing; the doctor with injected thresholds | `disk headroom` at `warn` and `problem` | nothing was changed |
| `capability-drift` | a lock with a foreign hash beside the deployed document | the doctor's `capability drift` check with `--lock-file` | the file removed |
| `provider-loss` | nothing: recorded (D976) | the record | nothing |
| `admission-refused` | nothing; `bin/admit.py` with `--reserve-memory-mb` injected so nothing can fit | the injected run's refusal; the host's own declaration as the control | nothing was changed |
| `worker-restart` | SIGKILL to the `auth` process, which holds the workflow loop (ADR 0226) | the doctor's `workflow` check: the heartbeat's HOLDER before and after, and the oldest overdue lease; the restart count as the control | the restart policy; `docker start` only if it did not |

Exit codes: 0 the reader read and the reversal verified; 5 refused (another
rehearsal un-reversed, or the scenario has nothing to induce here); 6 the
rehearsal ran and was reversed and the reader read nothing -- a finding,
recorded; 7 the reversal did not verify, and
`/etc/agentic-postgres/rehearsal-in-progress.json` names what is left.

Each writes `evidence/rehearsal-<key>-<scenario>-<id>.json`: the plan as
printed, every reading as a value the command produced, the verification and
the verdict. The session gate reads those records
(`--rehearsal-evidence-dir`), so a rehearsal is the trip's evidence, not a
step the trip repeats.

## 5. The doctor's two rehearsed readers

`sudo bin/doctor.sh --project <key>` reports **twelve** checks since 1.10.0: the
ninth is the mirror (§1), the tenth is `capability drift`, the live SHA-256
of the lock on disk against the digest the deployed document recorded, the
eleventh is `agent record` — the two agent tables' counts and the date the
record starts, with **no threshold** (ADR 0213) — and the twelfth is
`workflow`, the substrate's counts by status and the loop's heartbeat, with no
threshold for the same reason (ADR 0226). It reads the tables rather
than migration 0033's functions, so it answers the same against a deployment
that has not applied the retention migration. Three
flags exist for the rehearsals and are carried in the evidence so an
injected reading is never mistaken for the host's:

```
--disk-warn-copies N --disk-problem-copies N    # copies of the cluster; 0 < problem < warn
--lock-file PATH                                # read this lock instead of the deployed one
```

## 6. What has been measured, and what has not

- The mirror against the real provider (Backblaze B2): a complete copy on the
  second pass, a restore from the mirror alone in 151 s with every row, on the
  project's own image (D1001, D1002).
- `docker kill` is never restarted by a restart policy; a SIGKILL to the main
  process is (rig 4, D1015).
- A DOCKER-USER rule selected by source subnet and destination blocks that
  network only (rig 4).
- Not measured: that the primary's key is refused BY the mirror bucket -- the
  providers' account boundary, stated rather than probed (D1022); the
  scheduled copy on the production host, the kit from production, the
  replacement host and the eight readings there -- the trip's (Run 6).
