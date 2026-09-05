# 0188 — The secondary repository is a mirror of the primary, at a second provider, under the primary's key

- **Status:** accepted
- **Date:** 2026-09-05
- **Session:** 18, Run 1 (`REC-REPO-001`, `REC-REPO-002`, `REC-REPO-003`, D715, D984, D985, D994–D1000)
- **Related:** **ADR 0144** (pgBackRest lives in the database image), **ADR
  0145** (the repository is a bucket of its own with its own credential and
  cipher pass), **ADR 0147** (the database reaches its repository over an
  egress network of its own, and its stated residual), **ADR 0152** (the drill
  reads pgBackRest's own lines), **D145/D548** (the state is in a field, never
  the exit code), **D593** (`process-max` is 1), **D976** (a provider hangs).

## Context

Every backup this deployment has ever taken lives in one Cloudflare account,
beside the storage plane, the DNS and both tokens (ADR 0147's stated
limitation; Session 10's plan §11). The stage plan's Session 18 asks for *"a
secondary backup account or provider with independent credentials and an
independent encryption key"*, and D715 names what it bounds: an attacker with
account-level access at the one provider owns the backup history along with
the live data.

pgBackRest 2.59.1 supports several repositories in one stanza, and the obvious
design was to render the secondary as `repo2-*` beside `repo1-*`. Run 1
measured it in a rig -- two MinIO endpoints with distinct credentials, one
cluster on the project's own image, one stanza -- with a control for every
arm. The measurements decide this ADR, and they decide it against the obvious
design.

**Two repositories in one configuration couple the primary to the secondary
(D994).** With the secondary endpoint stopped, every `archive-push` failed as a
whole (`[104] archive-push command encountered error(s): repo2: HostConnectError`)
even though the primary was reachable; the segments piled up as `.ready`;
`backup --repo=1`, `backup` with no `--repo`, and `check` all failed on the
sixty-second archive timeout (`[082]`, `[049]`). Asynchronous archiving
(`archive-async=y`) did not decouple them: the queue stopped at the first
segment the secondary could not take and drained only when it returned.
**`archive-push` has no `--repo` option in this version (`[031]: option 'repo'
not valid for command 'archive-push'`, D996)**, so WAL cannot be steered to one
repository inside one configuration.

**Two configurations for one stanza -- the secondary asynchronous, with its own
spool and lock paths, pushed best-effort after the primary -- did not decouple
them either (D995).** In two variants, one with pgBackRest's default sixty-second
`archive-timeout` on the secondary and one with five seconds, the archiver
completed no push at all while the secondary was down (`archived=0` in
`pg_stat_archiver` after 27 seconds and three switches) and the primary's
backup failed with `[082]`; everything drained when the secondary returned.
A design whose availability the rig could not make independent in two attempts
is not one to deploy on a production cluster on the strength of a third.

**A copy of the primary repository at the second endpoint works, and the
archiver never learns it exists (D998).** `mc mirror --overwrite --remove` copied
the primary's bucket -- 1,978 objects -- to a bucket at the second endpoint in
four seconds, with the second endpoint's credential. A restore from the copy
alone, with the second credential and the primary's cipher pass, produced a
cluster that promoted and answered with every row the source held (9,000 of
9,000). The same restore with a different cipher pass was refused (`[075]: no
backup set found to restore`, D999: to pgBackRest an undecryptable repository
looks like an empty one).

Two more facts the rig fixed. **A restore into a directory that holds a cluster
is pgBackRest's own refusal** -- `[040]: unable to restore to path … because it
contains files. HINT: try using --delta` -- and `--delta` overwrites (D997), so
`REC-SAFE-001`'s *never passes delta* is the whole of the product's guard.
**Retention is per configuration** (two fulls kept where `retention-full=2`,
one where it is 1, D1000), which a mirror inherits from its source.

## Decision

**The secondary repository is a mirror of the primary repository's bucket at a
second, S3-compatible provider, made by a scheduled copy on the host, with the
second provider's own credential, and encrypted with the primary's cipher
pass.** Nothing about the archiver changes: one configuration, one repository,
`archive_command` as it is today. Concretely:

1. **The manifest declares it**: `backup.mirror` (`enabled`, `endpoint`,
   `bucket`, `region`) at project schema 4, absent meaning none. `naming`
   derives the default bucket name once.
2. **A host unit copies it**: `agentic-postgres-backup-mirror@.timer` runs
   `bin/backup.sh mirror` after the nightly incremental, inside a pinned
   client container on the project's backup egress network (ADR 0147), reading
   the primary bucket with the primary's credential and writing the mirror
   with the mirror's. A copy is idempotent and re-runnable; a failed copy is a
   failed unit an operator sees, and the doctor reads the mirror's last
   successful copy as a check of its own.
3. **Two operator-supplied secrets** for the mirror (`APG_MIRROR_S3_ACCESS_KEY_ID`,
   `APG_MIRROR_S3_SECRET_ACCESS_KEY`, `/backup`), consumed by the mirror
   container only. **No second cipher pass**: the objects are encrypted by
   pgBackRest before they leave the database container, and a copy cannot
   re-encrypt them.
4. **A restore from the mirror alone** is a pgBackRest configuration naming
   the mirror bucket as its only repository, with the mirror's credential and
   the primary's cipher pass -- which is what the replacement host's
   configuration is (ADR 0189).
5. **The mirror's client is a third party of its own**, pinned like every
   other image, and Run 2 measures it against the deployment's real second
   provider before a manifest names it.

## What this bounds, and what it does not

- **It survives the loss of the host and of the primary provider account
  together.** The mirror holds every backup set and every archived segment the
  last copy saw, under a credential the primary account cannot revoke.
- **It does not survive the loss of the Infisical project** that holds the
  cipher pass. That pass is held off the host in the disaster kit's terms (ADR
  0189: named, never valued, and the kit says where it lives).
- **The mirror lags the primary by one copy interval.** A restore from it
  reaches the last copied segment, not the last archived one. The deployed
  document publishes the mirror's last successful copy time and the fleet
  inventory shows it, so the lag is a number an operator reads (D700's rule:
  a snapshot says when it was taken).
- **"Independent encryption key" is not delivered, and this ADR says so**
  rather than delivering it by a design whose availability the rig could not
  make independent. An attacker holding the cipher pass and both credentials
  reads both repositories; one holding the cipher pass and one credential
  reads one. That is ADR 0147's residual halved, exactly as D985 states.

## Alternatives, measured and rejected

- **`repo2-*` in the archiver's configuration.** Coupled (D994).
- **A second pgBackRest configuration, asynchronous, best-effort.** Coupled in
  two variants (D995). Left as a question for a later pgBackRest, not for this
  deployment.
- **A second provider account at Hetzner.** Rejected without measuring: the
  host is at Hetzner, and a failure that takes the account takes both.

## Consequences

- Run 2 renders `backup.mirror`, the unit, the verb and the doctor's check, and
  measures the client against the real second provider before the trip.
- `backup_state` in the deployed document gains the mirror's block (outputs
  schema 16); every reader of `backup_state` moves with it (D993).
- The restore drill and `bin/restore.sh` take a repository configuration, not
  a repository number.
