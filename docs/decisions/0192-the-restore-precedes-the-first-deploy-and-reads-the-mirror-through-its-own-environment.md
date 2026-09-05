# 0192 — On a replacement host the restore precedes the first deploy, and a restore from the mirror carries the mirror's key in its own container's environment

- **Status:** accepted
- **Date:** 2026-09-05
- **Session:** 18, Run 3 (`REC-NODE-001`, `REC-NODE-002`, D1008–D1013)
- **Related:** **ADR 0189** (the kit, adoption, `restore.sh`), **ADR 0188**
  (the mirror), **ADR 0191** (facility-gated secrets), **ADR 0151** (the
  drill never mounts the active volume), **ADR 0153** (a pgBackRest include is
  mounted where pgBackRest reads it), **ADR 0144** (the derived image),
  **D558** (nothing puts a value into the archiver's environment), **D997**
  (pgBackRest's `[040]`), **D999** (an undecryptable repository looks empty).

## Context

ADR 0189 stated the replacement-host order as *adopt, materialize, deploy,
`restore.sh` into the project's own volume*, with the manifest's `backup`
block *pointing at the mirror bucket as the primary*. Checked against the
tree and measured on the project's own image before Run 3 built anything
(D1008, D1010–D1012), three of its premises do not hold:

1. **A deploy fills the volume.** The first `up` on an empty volume runs
   `initdb`; the deploy's step 6c then runs `stanza-create` for a cluster
   whose system identifier is not the repository's, and `check` fails. The
   restore into "the project's own volume" would then meet `PG_VERSION` and
   pgBackRest's own refusal (`[040]`, D997) -- correctly.
2. **The mirror cannot be the primary in a manifest.** The primary
   repository's endpoint is derived from `backup.account_id` in Cloudflare's
   shape (`naming.storage_endpoint_url`); a Backblaze endpoint is not
   expressible there, and `repo1-s3-region` is `auto` by construction.
3. **The mirror's credential is not where pgBackRest reads credentials.** The
   pair is materialized as raw files for the mirror container's uid (ADR
   0188). pgBackRest takes `repo1-s3-key` from a configuration file or from
   the environment; a pgbackrest-format include for the mirror's key would
   sit in the same include directory as the primary's and the last one loaded
   would win, which breaks the archiver.

The alternatives considered for the credential:

- **A pgbackrest-format include in a second include directory.** The
  consumer contract has one include directory (ADR 0153) and one target
  directory per service; a second directory is a new consumer field and a new
  mount in the model for a file only a replacement host reads.
- **`restore.sh` renders an include from the raw file.** A second writer of
  a secret file beside the materializer, root-only and ephemeral -- the
  second authority ADR 0056 exists to prevent.
- **The restore container's own environment.** pgBackRest reads
  `PGBACKREST_REPO1_S3_KEY` and `_SECRET` from its environment, and an
  environment option overrides the same option in a configuration file --
  measured (D1009) with a control: a configuration naming an empty
  repository path and an environment naming the full one answered `ok`.
  The values enter the environment inside the container, from mounted files,
  by the shape `services/backup-mirror/mirror.sh` already uses.

## Decision

**The order on a replacement host is adopt, materialize, render, `restore.sh`,
deploy.** `restore.sh` creates the project's volume when absent, refuses it
when a container mounts it or when it holds `PG_VERSION` under PGDATA
(D1012), restores through the project's own image built by the model
(`bin/compose.sh … build postgres`), starts the cluster once with archiving
off to finish recovery and promote, reads its identity, stops it, and leaves
the volume for `deploy.sh`, which starts the cluster without `initdb`.

**A restore from the mirror reads the mirror bucket with the mirror's pair
in the restore container's own environment**, from two raw files the
postgres service now receives as a second, facility-gated consumer of the
pair (ADR 0191) -- never as pgbackrest includes, never through argv, never
printed. The configuration it runs with is `rendering.build_pgbackrest_conf`
over the kit's deployed document with the mirror's endpoint and region
substituted (one renderer; a `region` keyword), mounted at
`/etc/pgbackrest/restore.conf` -- not the archiver's path -- with the include
directory holding **only the cipher pass** for a mirror restore, so the
primary account's credential is absent from the argument vector rather than
merely overridden. A restore from the primary mounts the archiver's three
includes as the drill does.

**`--latest` is a plain `restore`** (D1011: `--target-action` is refused
without a `--type`); recovery replays every archived segment and ends on a
new timeline. **The recovering instance runs in `restore.sh`'s own
container** with the same mounts and environment, because pgBackRest writes
its `--config` and `--config-include-path` into the `restore_command` it
leaves in `postgresql.auto.conf` (D1010), and `archive-get` needs the same
credential the restore had.

**The manifest deployed on the replacement keeps `backup.mirror` as the kit
recorded it and names a NEW primary bucket**: after a real loss, a new
account's; during a rehearsal, a rehearsal bucket. The mirror timer is never
enabled during a rehearsal -- its copy would `--remove` production's objects
from the mirror bucket -- and the runbook says so.

## What this refuses

- A restore into a volume that holds a cluster or that a container mounts,
  on any host; `--delta` on any argument vector.
- A second writer of secret files; a value in argv, in a log, or in the
  evidence document.
- A search by name at any provider (unchanged from ADR 0189).

## Consequences

- ADR 0189's order and its "mirror as primary" sentence are superseded by
  this ADR; the kit, `--adopt` and the verify rule stand as written there.
- `restore.sh` takes `--outputs` (the kit's deployed document), `--project`
  (the manifest deployed here), `--rendered-dir` and `--from mirror|primary`;
  the drill's `--from CONFIG` (D1006) is not built, because the mirror is read
  by `restore.sh` and the drill's subject is the primary.
- The verdict does not require `pg_last_xact_replay_timestamp()`: a restore
  to the latest point right after a full backup replays no committed
  transaction and is complete; a replay LSN, a timeline of two or more, the
  kit's `instance_uuid` and a non-empty migration ledger are required.
- The live half -- a restore from the real mirror on a replacement host,
  `REC-NODE-002` -- is the trip's, with the by-id project read (D1013).
