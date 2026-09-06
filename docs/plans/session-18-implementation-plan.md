# Session 18 — Independent recovery, failure rehearsal, and the Stage 2 release candidate

**Status:** planned 2026-09-05, after Session 17 closed at `98add5c` with
`evidence/session-17.json` reporting 90 passed / 7 `not_run` / 0 failed of 97.
**Brief:** `docs/plans/stage-2-plan.md` §5 *Session 18*, §4's caution about
`fresh_host`, D715 and D716.
**Shape:** six runs. Runs 1–5 build and are green in CI before the trip; Run 6 is
the trip, which needs three things only the operator can arrange (§0).
**Product version at close:** `1.0.0`. `CURRENT_SESSION` 18. Project manifest
schema 4, outputs schema 16.

---

## 0. Where the session starts

Session 17 closed with both permanent projects on release `8dc9842`, scheduled
backups running (the first incrementals completed 2026-09-05 at 03:43 and 03:47
UTC), a third project created and retired, and `project_removal` passed for the
first time since Session 12. Two Stage 1 claims remain `not_run` for want of an
event nobody has arranged: `fresh_host` (`DEP-001`, a deployed document from a
host that started empty) and `documented_path` (`DX-001`, a record from a person
who did not build this). Five more are `not_run` for reasons Session 18 does not
touch: `api_authorization`, `bootstrap_identity`, `credential_rotation_planes`,
`deployment_convergence`, `port_allocation`.

**The brief was checked against the tree in both directions before this plan
was costed.** What the stage plan says is already true is true: the recovery
plane is deployed, the PITR drill never mounts the active volume, a deploy
fails on a broken archiver, and both proofs Session 18 closes are written and
gated. What the brief describes as if it existed and does not is §1 -- above
all *"documented artifacts"* for a replacement host, which no document in the
tree defines, and a second repository, which the archiver supports and the
render has never emitted.

**Three things the trip needs that only the operator can provide**, decided
before Run 6 and not before Run 1:

1. **A second object-storage account at a provider that is neither Cloudflare
   nor Hetzner**, S3-compatible, with one bucket and one key pair scoped to it.
   The recommendation is Backblaze B2 (S3-compatible, a different company from
   both the storage plane and the host, free egress to Cloudflare, ten
   gigabytes free), and the plan is written provider-agnostic: the manifest
   names an endpoint and a bucket, Run 1 measures pgBackRest against two local
   S3 endpoints, and the trip measures the real one.
2. **A replacement host for a day**: a second VPS, empty, provisioned by the
   documented path. A Hetzner CX22 at a few cents an hour is fine -- the
   failure being modelled is the loss of the original VPS and the primary
   backup account, not the loss of the hosting company.
3. **A person who did not build this, for one afternoon**, to walk the
   documented path on the replacement host and produce the `DX-001` record. If
   nobody can be found, `documented_path` stays `not_run` with that reason in
   §1, and this plan says so rather than having the builder produce the record
   (D716's *"a test that tried would be measuring its author"*).

**Read D969–D983 before touching anything.** Eleven defects in two days, and
most of them one of two shapes: a reader that did not move when a decision was
implemented (D970, D978, D979, D981), or a proof that had never executed until
the trip ran it (D982, D983). Every run below names the readers it touches and
runs its live proofs' `--setup-plan` before the trip.

---

## 1. The divergence table

Six columns: the number, what the brief or the tree said, what was measured or
read, what this plan does, why it matters, the ADR if one decides it. **Next
free number after this table is D1015.** D984–D993 were written at planning;
D994–D1000 are Run 1's measurements, and they reversed Run 2's design (ADR
0188); D1001–D1003 are Run 2's first step, the real second provider;
D1004–D1007 are Run 2's build; D1008–D1014 are Run 3's, and D1008 reversed
Run 3's order (ADR 0192).

| D | Said | Measured or read | This plan | Why it matters | ADR |
|---|---|---|---|---|---|
| **D984** | The brief: *"a secondary backup account or provider with independent credentials and an independent encryption key"*, read as new archiver machinery. | **The archiver already supports it and the render has never used it.** `rendering.py` emits exactly one repository (`repo1-type=s3`, `repo1-s3-bucket`, `repo1-cipher-type`, `repo1-retention-full`) and the credential and cipher pass reach the container as two `pgbackrest`-format include files (`20-repo1-s3-key-secret.conf`, `30-repo1-cipher-pass.conf`) from `secrets.required.yaml`. pgBackRest itself is multi-repository (`repo2-*` options, `backup --repo`, `restore --repo`, archiving to every configured repository); **none of that has been measured by this repository**, and the one behaviour that decides whether a second repository is safe on a production cluster -- what `archive_command` does when one of two repositories is unreachable -- is exactly what Run 1 measures with a control. | **A second repository is rendered, not built**: `backup.secondary` in the manifest, `repo2-*` in the rendered config, three more secrets (two operator-supplied, one generated cipher pass), and the verbs made repository-aware. Nothing new runs in the container. | The Stage 2 failure mode (stage plan §9): re-implementing what a third party already does because the specification described it. The risk is the opposite one -- assuming the archiver's multi-repo semantics instead of measuring them, on a cluster whose WAL must keep archiving. | 0188 |
| **D985** | *"An independent encryption key."* | **Every project's cipher pass is a generated secret in that project's Infisical project**, materialised into the database container's generation. A second cipher pass for the second repository is generated the same way and lands in the same Infisical project and the same container. What the second repository is independent OF is the storage provider and its credential; it is not independent of the secret store or of the database container (ADR 0147's residual is halved, not closed: an attacker inside the container still holds both passes). | **ADR 0188 states the boundary exactly**: the second repository survives the loss of the host and of the primary storage account; it does not survive the loss of the Infisical project, and the kit (D986) is where a cipher pass is held outside it. | A premise wrong in the reassuring direction (D930): "independent" read as "independent of everything" would have the ledger claim a guarantee the design does not give. | 0188 |
| **D986** | *"A project restores onto a clean replacement host using only the independent backup account and documented artifacts."* | **No document in the tree says what those artifacts are, and the bootstrap cannot start on a host that has no state.** `bootstrap-providers.sh --apply` on an empty host creates an Infisical project and identity by NAME; the original project's Infisical project already exists under that name and the bootstrap refuses to adopt by name (provider-bootstrap.md's stop condition). The runtime credential and `bootstrap-state.json` are root-only files on the host that was lost. Nothing exports them, nothing lists them, and `restore-test.sh` restores only into a disposable volume by design (REC-SAFE-001). | **Run 3 defines the kit and the two verbs the runbook needs**: `bin/dr-kit.sh export` writes the operator's off-host set -- the three manifests, `bootstrap-state.json` per project, and the NAMES and provider paths of every secret, never a value -- and `verify` checks a kit is complete; `bootstrap-providers.sh --adopt` reads the recorded Infisical project id from the kit and mints a fresh runtime identity against it, refusing to look anything up by name; `bin/restore.sh` restores a stanza from a named repository into the project's own volume **only when that volume holds no cluster**, and refuses otherwise. `docs/node-loss-runbook.md` is derived by diff from the Session 11 and 17 guides (D693). | The brief priced a runbook; the tree needs a definition of what an operator must be holding on the day the host is gone, and three refusals that keep the restore path incapable of touching a live cluster. | 0189 |
| **D987** | Stage plan §4: *"`fresh_host` proves the documented deployment path reaches a running project; Session 18 proves a restore from an independent account does. Do not fold them."* | **`DEP-001`'s proof refuses the production host's document and needs one from a host that started empty**, distinct from the one `project_a` runs on. A replacement host provides such a document only if a project is deployed there by the documented path, and a restore of alpha into an empty cluster is not that path. Both events fit one machine: two projects on the replacement (D959's memory figure allows three). | **Two events, one host, two claims, in this order**: first a NEW ephemeral project (`delta-dev`) deployed on the replacement by the documented path -- its document is `APG_FRESH_HOST_OUTPUTS` -- then alpha's stanza restored from the secondary repository into a second project on the same host, under a drill domain, with the primary account's credential deliberately absent from that host. | Folding them would close a Stage 1 claim by an event that is not what the claim states (D478). | — |
| **D988** | *"The external pilot"*: `documented_path` (`DX-001`). | **The proof needs a record from a person who did not build this**, with the fields `DX_RECORD_FIELDS` names, checked against the commands the README and `docs/README.md` actually name. The tree cannot produce it and the builder must not (D716). The reader's afternoon is the deployment of `delta-dev` on the replacement host by the documented path -- the same event as `fresh_host`'s, walked by the outsider. | **Arranged, not built.** If an outsider is available, one afternoon closes both Stage 1 claims; if not, `fresh_host` closes through the builder's own walk and `documented_path` stays `not_run` with that reason recorded here. | The one claim in the repository a test cannot make alone, and the one the stage plan says has waited since Session 12 *"for want of an afternoon"*. | — |
| **D989** | *"Bounded failure rehearsals -- service termination, database restart, backup credential failure, disk threshold breach, WAL archiving failure, registry loss, capability drift. These test detection and graceful degradation, not automatic failover."* | **The detections exist; the rehearsals do not.** The doctor reads `disk_headroom` (warn at two copies of the database size, problem at one), `repository` and `archiver`; six alert rules render per project (collector unreachable, edge unreachable, store scrape missing, certificate expiring, route error rate, agent plane failing); `AGT-DRIFT-001` proves capability drift offline; the port registry's loss is detected by nothing -- `database-ports.sh allocate` on an absent registry would create a fresh one and could hand out a port a running project binds. **Nothing induces any of these on purpose, observes the detection, and puts the host back.** Filling the production disk is not a rehearsal anyone should run. | **Run 4 builds `bin/rehearse.sh SCENARIO`**: each scenario induces a bounded, reversible failure, reads the detection that exists, and restores, printing what it did and what it read; six scenarios, and the seventh -- disk threshold -- rehearses the READER (the doctor with an injected threshold reports `warn`) and not the disk, stated as such. **Registry loss becomes a refusal first**: an absent registry is not an empty one. | *"Detection and graceful degradation"* is a claim about readers, and a reader that has never seen its failure is D982's shape. The registry gap is the kind of finding a rehearsal exists to make before a host does. | 0190 |
| **D990** | Stage plan §3's table: *"coordinator-loss and chaos rehearsal."* | **There is no coordinator** (the Stage 3 spec's reading, checked 2026-09-05: the word occurs in the stage plan only, where a coordinator is declared non-authoritative and any need for one *"evidence for a Stage 3 specification"*). The nearest real dependency whose loss a deploy feels is Infisical, and D976 measured that shape on the trip: a slow or absent provider fails a deploy at step 5 and touches nothing running. | **Recorded, not built.** Provider loss is one of Run 4's six scenarios (backup credential failure covers the archiver; a materialization against an unreachable provider is D976's measurement and is not repeated). | A rehearsal of a component that does not exist would pass, which is the worst kind of green. | — |
| **D991** | D704: *"`1.0.0` at Session 18."* | **The compatibility rules a major version promises are the ones `docs/product-contract.md` has carried since Session 13** for manifest, migration, contract, capability and secret-format changes; a major version adds nothing to them except that the next breaking change to any of the five needs the next major. Session 18 itself bumps the project manifest (v4, `backup.secondary`) and the outputs document (v16, per-repository backup state), both additive with migrators, which the rules allow inside a major. | **Run 5 bumps to `1.0.0` and writes the one sentence the rules need**: what `1.x` may change and what needs `2.0`. No second version axis (D704). | A number that promises more than the rules behind it is D600's null. | — |
| **D992** | *"The Stage 3 decision report written from actual evidence."* | **The evidence is `evidence/session-18.json`, the ledger, and the Stage 3 consolidated specification's premises checked against the tree on 2026-09-05** (no coordinator; Stage 2 is 13–18, not 13–24; a PostgreSQL 19 baseline the tree does not run; `apg dev` replicating from a database with no public port). None of that is in a document. | **Run 5 writes `docs/stage-3-decision-report.md`** from those three sources, with its numbers filled at the trip's close: what 1.0.0 measured, what stayed `not_run` and why, which of the Stage 3 spec's premises hold, and a recommendation on the template-or-control-plane question (`scope-closure.md` §6) that the report answers rather than restates. | A decision report written before the evidence is a plan; written after it is the thing the stage plan asked for. | — |
| **D993** | `docs/backup-operations.md` and ADR 0147: *"everything is in one Cloudflare account … cross-account replication, a second provider and an offline copy are absent by decision."* | True on 2026-09-05, and the sentence is a limitation the second repository removes. `backup_state` in the deployed document is a deploy-time snapshot of ONE repository (D700). | **Outputs v16 carries `backup_state.repositories`, one entry per repository, each with the fields the single one has today**; the fleet inventory's backups line reads the secondary too; the document states the boundary as ADR 0188 draws it. | Every reader of `backup_state` is a reader that must move (question 5): `deployed_output`, `fleet`, `doctor`, the migrator, the schema, the matrix's classification. Run 2 lists them before changing one. | 0188 |
| **D994** | This plan's D984 and Run 2 as first written: *"a second repository is rendered, not built: `repo2-*` in the rendered config"*, with Run 1 to measure *"what `archive_command` does when one of two repositories is unreachable"*. | **Two repositories in one configuration couple the primary to the secondary.** Rig 18 (two MinIO endpoints, distinct credentials, the project's own image, pgBackRest 2.59.1, PostgreSQL 18.4): with the secondary stopped, every `archive-push` failed as a whole -- `[104] … repo2: HostConnectError` -- although the primary answered; three segments waited as `.ready`; `backup --repo=1`, `backup` with no `--repo`, and `check` failed (`[082]` on the 60-second timeout, `[049]`). With `archive-async=y` the queue stopped at the first segment the secondary refused and drained only when it returned. With both endpoints up, a full with no `--repo` went to repo1 only (*"repo option not specified, defaulting to repo1"*) and archiving reached both. | **Run 2 does not render `repo2-*`.** ADR 0188 makes the secondary a mirror of the primary's bucket at the second provider, copied by a host unit; the archiver keeps one repository. | The obvious design was one that would have stalled production archiving on the first outage of a provider nobody had measured, and it was one measurement away from being rendered. The Stage 2 failure mode's mirror image: not re-implementing a third party, but assuming its semantics. | 0188 |
| **D995** | Rig 18's fallback, written into this plan's §9: *"the secondary is written by scheduled `backup --repo=2` only, WAL goes to the primary alone."* | **A second pgBackRest configuration for the same stanza -- the secondary as its own `repo1`, asynchronous, its own spool and lock paths, pushed best-effort after the primary with `\|\| true` -- did not decouple them either, in two variants.** With pgBackRest's default 60-second `archive-timeout` and with `archive-timeout=5` on the secondary, the archiver completed no push at all while the secondary was down (`pg_stat_archiver` at `archived=0 failed=0` after 27 seconds and three switches) and the primary's backup failed `[082]`; when the secondary returned, its spool drained and both archives reached the same segment. A configuration written inside the file (`config-include-path=`) was ignored -- the option is command-line only -- which cost one rerun before the variant was measured at all. | **Not the design.** Recorded so the next reader does not spend a day on it; left as a question for a later pgBackRest. | Twice the rig could not make the primary's availability independent of the secondary's with the archiver in the loop, and the third attempt would have been the one deployed. The mirror keeps the archiver out of the loop altogether. | 0188 |
| **D996** | The §9 fallback assumed `archive-push --repo=1`. | **`archive-push` has no `--repo` option in 2.59.1**: `[031]: option 'repo' not valid for command 'archive-push'`, from the postmaster's log after the container was started with it. | Recorded; the mirror needs no such option. | An option assumed from the shape of its siblings (`backup --repo`, `restore --repo` exist). Grep the third party's own reference before the plan names a flag. | — |
| **D997** | `REC-SAFE-001`: *"the command never passes delta"*; this plan's Run 3: *"`restore.sh` refuses when the volume holds a cluster"*, priced as a refusal the product builds. | **The refusal is pgBackRest's own**: a restore into a directory holding a cluster exits **40** -- *"unable to restore to path '…/pgdata' because it contains files. HINT: try using --delta if this is what you intended."* -- and `--delta` overwrites it (exit 0). One earlier arm read exit 0 for the same case and was wrong: its target volume had been recreated empty by the rig between runs (D702's shape, an observation's accident). | **`restore.sh` still refuses before calling pgBackRest**, so the message is the product's, but the guard the invariant rests on is *never passes `--delta`*, which `REC-SAFE-001` already asserts and `REC-NODE-001` inherits. | A product refusal in front of a third party's refusal is not redundant when the third party's has an override flag; the product's job is to never hold the flag. | 0189 |
| **D998** | D715: *"restore-to-new-host … using only the independent backup account"*; this plan's Run 6 step 5 assumed a restore *"from the secondary repository"* as a pgBackRest repository of its own. | **A copy of the primary's bucket restores.** `mc mirror --overwrite --remove` copied 1,978 objects to a bucket at the second endpoint in 4 seconds with the second endpoint's credential; a pgBackRest configuration naming the copy as its only repository, with the second credential and the PRIMARY's cipher pass, restored (`--type=immediate`, promoted) a cluster that answered with 9,000 of 9,000 rows. Earlier, the same shape against a real second repository restored 11,000 of 11,000 and, with `--type=default`, replayed the archived segments beyond the set. | **The mirror is a repository to a restore**, and the replacement host's configuration names it as `repo1`. | The whole of what the secondary must provide is *a bucket a restore can read with a credential the primary account cannot revoke*, and a copy is that. | 0188, 0189 |
| **D999** | ADR 0152 §3 and the drill: a restore *"fails the drill rather than publishing a null"* when its output does not match; the doctor's `repository` check reads `pgbackrest info`'s status. | **An undecryptable repository looks like an empty one.** A restore with the wrong cipher pass exits **75** -- *"no backup set found to restore"* -- not a decryption error; `info` with the wrong pass would report the same absence. Measured as the control of two arms. | **The doctor's mirror check and `restore.sh` name the possibility**: *no backup set found -- the repository is empty OR the cipher pass is not this repository's* -- and the kit's `secrets.txt` says which pass a repository was written under. | D145's family at the cryptographic layer: the exit code says "nothing there" for two states with opposite remedies. | 0188 |
| **D1000** | `repo1-retention-full` is one value the manifest declares; a mirror inherits whatever its source kept. | **Retention is per configuration**: with `retention-full=2` on the primary and `1` on the second repository, three fulls left two sets on the primary and one on the second, expired by each backup on its own repository. A mirror made with `--remove` follows the primary's expiry within one copy interval. | The mirror has no retention of its own; the manifest's `retain_full` governs both, and the document says so. | One value, one statement of it (D495) survives the second repository only because the second is a copy. | 0188 |
| **D1001** | ADR 0188 and Run 2's first step: *"the mirror client against the deployment's real second provider … before a manifest names it."* | **Measured against Backblaze B2 (`s3.eu-central-003.backblazeb2.com`, a bucket-scoped application key) from this workstation, on the project's own image built from the pinned base.** `mc mirror --overwrite --remove` (`RELEASE.2025-08-13T08-35-41Z`) copied a local pgBackRest repository of 1,001 objects in 28 seconds; **the first pass exited 1 with two objects behind, and the next pass exited 0 with the copy complete**. A source object removed is removed at the copy on the next pass with `--remove` and stays without it (the control). A segment archived while a copy is listing lands in the following copy: the mirror is a snapshot of a listing, not a stream. | **`backup.sh mirror` treats a non-zero exit as a failed run, prints the client's last lines (D980), and leaves completion to the timer's next run**; the doctor's mirror check reads the last SUCCESSFUL copy, never the last attempt. The client image is pinned in `versions.in.yaml`; it carries no `grep` or `awk`, so every listing is parsed on the host side. | A copy that can be partial by one pass and complete by the next is exactly the kind of tool a timer suits and a one-shot verb misreports. | 0188 |
| **D1002** | This plan's Run 6: a restore *"from the secondary"* on a replacement host, with D593's band for the restore time. | **A restore from Backblaze alone, on the project's image, with the mirror's credential and the primary's cipher pass: exit 0 in 151 seconds for ~1,000 objects (a ~30 MB repository), promoted, 9,000 of 9,000 rows; `info` against it reports `status: ok` with the full and two incrementals; the wrong cipher pass exits 75.** The Session 10 rig image (`apg-rig8-pg`) could not do any of it: it predates D590 and holds no CA store, so it verifies neither Backblaze's Let's Encrypt chain nor Cloudflare's -- a rig fact that cost one pass and that the project's image, which installs `ca-certificates` in the archiver's layer, does not share. | **Run 6's replacement-host restore is priced from this band**: a few minutes per gigabyte of repository at `process-max` 1 from `eu-central-003`, sampled once; the trip records its own figure. Every rig from here runs the project's image built from `versions.env`, never a session's leftover. | The restore's time is a sample from a band (D593), and a rig image is a third party of its own: the measurement that matters was almost taken on an image the deployment does not run. | 0188 |
| **D1003** | Backblaze's bucket is the operator's (ADR 0110), created by hand. | **Unmeasured, and stated as such**: Backblaze keeps file versions by default, so a delete through the S3 API hides a version rather than freeing it, and a mirror with `--remove` may never reclaim space unless the bucket's lifecycle keeps only the last version. The measurement's own cleanup listed 0 objects afterwards, which is what a hidden version looks like from the S3 side. | **Run 6 reads the bucket's lifecycle setting before the first copy** and `docs/recovery-operations.md` names it as the one bucket setting the mirror needs; the doctor cannot see it. | A cost that grows silently is D700's shape at the provider: the listing says empty and the bill says otherwise. | — |
| **D1004** | D1001: the client image carries no `grep` or `awk`, *"so every listing is parsed on the host side"* -- and the first step's rig counted `mc ls`'s TEXT lines. | **`mc ls --recursive --json` on the pinned image, measured against a two-file directory with a nested prefix, and its non-recursive form as the control**: one JSON object per line, `"type":"file"` for an object; with `--recursive` a prefix appears only inside a key, without it as its own `"type":"folder"` line. No summary line, no trailer. | `backup_report.count_listing` counts `file` entries only and returns None -- never zero -- for a line that is not JSON; the verb writes no record on None. The proof carries both samples verbatim. | A count of zero is the number a restore would be planned against; the format a counter reads must be the format that was measured, not the one a text listing suggested. | 0188 |
| **D1005** | Run 2's build, as drafted: the mirror pair becomes *"required"* through the rendered document's `secrets.required_names`. | **The rendered document's `required_names` is `RENDER_SESSION`'s list -- Session 2's one sentinel -- by design**; the DEPLOYED document's `secrets.required_names` is built from the generation manifest, which is what the materializer wrote. The reader that decides what a project must hold is the materializer's view of the contract, and the deploy's preflight and the bootstrap compute the same set from the same reader. | The render's `required_secret_names` is filtered by facility for the future but is not the proof's subject; the proof reads the bootstrap's declared and operator-supplied lists and the deploy's preflight instead (`test_backup_mirror`). | A premise wrong in the reassuring direction (D930): a test on the rendered field would have passed for the wrong reason at Session 2's list and proved nothing about what a mirrored project holds. | 0191 |
| **D1006** | Run 2 as drafted: *"`restore-test.sh` and `backup.sh info\|check` accept `--from CONFIG`, a pgBackRest configuration naming one repository, which is how a mirror is read."* | **Not built in Run 2.** The mirror is read by the copy record on the host and, for a restore, by ADR 0189's `restore.sh` on a replacement host with the mirror's credential and the primary's cipher pass -- which Run 3 builds. A `--from` on the drill would be a second reader of a repository configuration this run has no consumer for. | Deferred to Run 3, where `restore.sh` needs the mirror's configuration anyway; recorded here rather than silently dropped. | A declared flag with no reader is an unverified flag (D816, D929). | 0189 |
| **D1007** | The contract had two states for a secret, `required: true` and `required: false`; ADR 0188 named the mirror's pair *"consumed by the mirror container only"* and gave the primary's pair *"that container as a second consumer"*. | **Neither state fits a secret two projects lack and one needs**: required everywhere fails both host projects' materialization (their manifests are schema 1); optional is refused for a compose consumer because Compose does not start a service whose mount source is missing. And the primary pair's second consumer, declared plainly, would be materialized and granted for every project -- two files nobody reads. | **ADR 0191**: a third state, `facility: backup_mirror`, on a secret or on a consumer; `active_secrets(..., facilities=)` is the project's view; every writer, mounter, requirer and creator asks it (the materializer, the override, the render, the deploy's preflight, the bootstrap's three lists). The declared view stays for the rotation planner and the contract tests. | The reader that did not move is this repository's defect class (D600, D918); nine readers of one contract were grepped before one was changed. | 0191 |
| **D1008** | ADR 0189 and this plan's Run 3 and Run 6: on the replacement, *adopt, materialize, deploy, then `restore.sh` into the project's own volume*, with the manifest's backup block *pointing at the mirror bucket as the primary*. | **A deploy fills the volume and cannot then meet the repository.** The first `up` on an empty volume runs `initdb`; step 6c's `stanza-create` then names a cluster whose system identifier is not the repository's, and the restore that followed would meet `PG_VERSION` and pgBackRest's `[040]` (measured on the project's image, arm C). And a mirror cannot be a manifest's primary: the primary endpoint is derived from `backup.account_id` in Cloudflare's shape and the region is `auto` by construction. | **The order is adopt, materialize, render, `restore.sh`, deploy** (ADR 0192): the restore fills the volume through the project's own image and starts the cluster once to promote it; the deploy then starts a cluster that exists and skips `initdb`; the manifest keeps `backup.mirror` and names a NEW primary bucket. The runbook is written in that order and a proof asserts it. | A runbook that deploys first would have failed at its fourth step on the trip, with the volume already holding a fresh cluster the operator would then have to remove by hand (D977's shape). | 0192 |
| **D1009** | pgBackRest's documentation: *command line > environment > config file*. | **Measured on the project's image with a control**: a configuration naming `repo1-path=/repoA` (holding the stanza) and no environment answered `ok`; the environment set to `/repoB` (empty) answered `missing stanza path`; `--config` naming `/repoB` with the environment set to `/repoA` answered `ok`. The environment overrides the configuration file. | **A mirror restore carries the mirror's key pair in the restore container's own environment**, exported by a wrapper from two mounted raw files (the pattern `mirror.sh` uses); the primary's includes are not mounted at all, so the primary account's credential is absent rather than overridden. | Without the measurement the design would have rested on a documented precedence nobody here had seen hold; D267. | 0192 |
| **D1010** | Run 1's rig: pgBackRest honours `config-include-path` on the command line only. | **A restore invoked with `--config=X --config-include-path=Y` writes `restore_command = 'pgbackrest --config=X --config-include-path=Y --stanza=S archive-get %f "%p"'` into `postgresql.auto.conf`** (measured, arm B). The recovering instance therefore needs the same configuration at the same paths and the same credential the restore had. | **The recovering instance runs in `restore.sh`'s own container**, with the restore's mounts and environment, until it promotes; the deploy's postmaster then starts a promoted cluster whose `restore_command` is inert. | A cluster started by the deploy while still in recovery would have run `archive-get` against a path the deploy's container does not mount. | 0192 |
| **D1011** | Run 3 as drafted: `--target-time T\|--latest`, with the drill's `--target-action=promote` on both. | **`--target-action` is refused without a `--type` in `(immediate, lsn, name, time, xid)`**: pgBackRest error `[031]`, measured (the rig's first pass failed on it). A plain `restore` replays every archived segment and promotes at the end of WAL. | `restore_arguments` emits a plain `restore` for `--latest` and `--type=time --target=T --target-action=promote` for a target time; the proof pins both vectors. | A flag copied from a working command is not a flag that works in every command; the rig found it before the trip did. | 0192 |
| **D1012** | ADR 0189: *"only when that volume holds no cluster"* -- with no reading named. | **`PG_VERSION` under PGDATA is present in a restored volume and absent in a fresh one** (measured, arm D); `PGDATA` sits at `18/docker` inside the volume's mount (`runtime_override`'s two constants). A container mounting the volume is read from `docker ps -a --filter volume=`. | `restore.sh` probes `<mount>/18/docker/PG_VERSION` through the project's own image and refuses presence with exit 7, before building anything; `node_restore.pg_version_relative_path` derives the path. | "Holds no cluster" had to become a reading with a control, or the refusal would have been a sentence. | 0192 |
| **D1013** | ADR 0189: `--adopt` *"refuses when the recorded project id does not exist and never searches by name"*, with no route named. | **Infisical's router declares `GET /api/v1/workspace/:projectId`** (operation `getProjectById`, response `{project: {id, orgId, …}}`, bearer auth), read from the API's source; the unauthenticated route probe against `app.infisical.com` answered 200 for every path, so nothing offline distinguishes the route from the site. The list route (`GET /api/v1/projects`) is the one adoption must never call. | `ControlPlane.get_project` calls the by-id route and nothing else; a proof drives adoption against a recorded control plane and asserts the exact call sequence; the live proof of the route is the trip's (the first `--adopt` on the replacement). | A by-name lookup is the runbook's stop condition; the guard is on the calls made, not on the words in the source. | 0189 |
| **D1014** | CLAUDE.md §2: *"a run's targeted list must include every guard module whose subject the run touched."* Run 3 added four files to `bin/` and its targeted list held twenty-five modules. | **CI on `a8cf5d6` was red on one test**: `test_cli_contract`'s coverage guard, which holds every command in `bin/` to nine checks (the executable bit in the index, `--help`, the secret-argument scan among them) and found `dr-kit.sh`, `dr-kit.py`, `restore.sh` and `restore.py` in neither of its lists. Listed, the module's 388 passed at once: nothing was wrong, which is the shape the guard exists for (D175). | Listed in the repair commit; the run's targeted list now names `test_cli_contract` whenever a run adds or removes a command. | The rule was written after Session 17's trip and broken by the next run that added a command; a rule kept by memory is D175's shape. CI caught it, as CI is the full check for (D913). | — |
| **D1015** | ADR 0190's table: service termination is induced by *"`docker kill` one stateless service"* and reversed by *"Compose's restart policy"*. | **Measured in rig 4** (`~/rig18/rig4.sh`, four arms with controls, Docker Desktop 29.5.2): `docker kill` on an `on-failure:5` container leaves it stopped -- exit 137, restart count 0 -- because the daemon records a manual stop and cancels the restart manager; a SIGKILL to the container's main process from the daemon's PID namespace is an unexpected exit and the same policy restarts it in 1.7 s with restart count 1; `kill -9 1` from inside the container's own namespace is ignored by the kernel; `docker start` after a `docker kill` brings it back. The table's reversal never fires for the table's induce. | The induce is `kill -KILL <host pid>` from the host; `docker start` is the conditional fallback the plan prints, and a service the policy did not bring back is a rehearsal that read nothing (exit 6). The plan says why in the line it prints. | A reversal that is a property of a third party has to be measured against the induce it is paired with; the ADR paired a manual stop with a policy that exists to ignore manual stops. | 0193 |
| **D1016** | ADR 0190's table reads *"the mirror unit's failure and the doctor's mirror check"* for a blocked mirror path. | **The doctor's mirror check reads the copy record, which a failed copy never writes**: `backup.sh mirror` writes it only after a pass that exits 0, so the check reports the last completed copy until it is `MIRROR_STALE_AFTER_DAYS` (2) old. Under a block it says `ok, last copied <yesterday>`. The reader that names one failed copy is the verb's exit, which is what the unit runs and how the unit fails. | The scenario's reader is the mirror verb's exit; the doctor's mirror check is read and recorded as what it reports; the doctor's archiver check is the control that the primary's path was never touched; the copy after the reversal is part of the reversal. `OPS-REHEARSE-005`'s wording in §2 corrected to the mirror path. | A reader named before it was read; D982's shape one step earlier -- the reader exists and does not read this failure, by its own design. | 0193 |
| **D1017** | ADR 0190 and `OPS-REHEARSE-008`: capability drift is *"reported by the doctor's drift check"*. | **The doctor had no drift check.** `AGT-DRIFT-001` proves the compiler offline; nothing on a host compared the lock on disk with the digest the deploy recorded in `mcp.capability_lock_sha256`. The doctor's ADR 0158 guard in `test_diagnosis` forbade reading the `mcp` block at all. | Built as the doctor's tenth check, `capability drift`: the live SHA-256 of the lock file against the recorded digest, the check handed booleans and never a digest (ADR 0159). The guard replaced by a stricter one that pins the single `mcp` read by its exact shape (ADR 0193). `--lock-file` is the rehearsal's injection. | The requirement named a reader the tree did not have (D950's shape, a brief that says "add X to Y" when Y does not exist). | 0193 |
| **D1018** | Plan §5 Run 4: *"`load_registry` on an absent file raises, every verb reports it, and `allocate` never creates a registry it did not find"* -- one reader. | **Three readers.** `bin/database-ports.py` returned `empty_registry()` for an absent file; `bin/deploy-project.py`'s `_live_allocation` returned `None` and the deploy published the transports `unavailable` -- a loss of host state read as "nothing allocated yet"; `access_broker` already refused (exit 4). And nothing created the initial registry but an allocation, so provisioning had no step for it. | `port_allocations.RegistryMissing`, exit 4 from every verb; the deploy fails by name (exit 5); `provision-host.sh --apply` creates the empty registry once and `--check` reports its absence; an existing registry is never rewritten. All three readers proved in `test_rehearsal`. | §7 question 5: which of a decision's callers got it. Grep every reader before fixing one (D979). | 0193 |
| **D1019** | ADR 0190's table: *"one stateless service"*, read through *"the doctor's route status"*. | **The doctor asserts 200 on one route**, the reserved health route (ADR 0015), and `edge-probe` serves it. Killing PostgREST, the obvious stateless service, leaves every doctor check green. | `rehearsal.HEALTH_SERVICE = "edge-probe"`: the service terminated is the one whose route the reader reads, found by its Compose service label. | A rehearsal of a service no reader covers passes for the wrong reason (ADR 0065's shape). | 0193 |
| **D1020** | Session 17's bump (7fefff4) and D938: *"every live half written in the run that built its plane"*; this plan's Runs 2–4 say their live halves *"are the trip's"*. | **None of Session 18's fifteen requirements had a live proof before Run 5.** The four offline modules carry no `live_host` marker and `tests/deployment/` had no Session 18 file; `claim_mode` refuses a claim with no live proof, so none of the four claims could have been registered at the bump as the runs left it. | Two deployment modules written at the bump, `test_session18_recovery.py` (seven proofs) and `test_session18_rehearsal.py` (eight), gated on four new declarations -- `APG_KIT_DIR`, `APG_REPLACEMENT_HOST_OUTPUTS`, `APG_RESTORE_EVIDENCE_FILE`, `APG_REHEARSAL_EVIDENCE_DIR` -- in the roster and exported by the gate (D687). Never executed before the trip, and each docstring says so. | D938's shape again, one session later: the lesson was in Session 17's commit message and Done paragraph and not in this plan's run texts, which said "the trip's" where they should have said "written now, gated on the trip". | — |
| **D1021** | Plan §5 Run 5: host mode gains *"`--secondary-repo-check`, `--kit-dir`, `--replacement-host-outputs`"*. | **The first predates Run 1's reversal**: there is no second repository to check; the mirror's readiness is a state of the deployment (a record beside the document, ADR 0188), not a declaration. And two declarations the plan did not name are needed: the restore's record and the rehearsals' records, since a gate that ran a restore or a rehearsal would measure its own run. | The gate takes `--kit-dir`, `--replacement-host-outputs`, `--restore-evidence-file` and `--rehearsal-evidence-dir`; `--secondary-repo-check` is refused by name with the reason; the mirror's readiness is host mode's step 4b, checked on both projects before anything runs. | A flag named before the design it belonged to was reversed; caught by deriving the gate from the plan's own §7 rather than its §5. | — |
| **D1022** | §2's `REC-REPO-002`: *"the primary's credential cannot read it and the mirror's cannot read the primary"*; `REC-REPO-003`: *"the wrong cipher pass is reported as empty or undecryptable, never as empty"*. | **No node id proves either clause.** A cross-account read needs a client holding one account's key against the other's bucket, which no container holds by design (ADR 0191) and no rig measured; the cipher-pass wording was never measured in rig 18 or Run 2 (no arm names it). | The registered descriptions state what is proved: the two key ids differ, the endpoints are two providers', the archiver names no mirror, and the account boundary is the providers', stated rather than probed; the cipher-pass clause is dropped from `REC-REPO-003`. | A requirement clause with no node id is D816's unverified field, and a registry that carried it would report it passed on the strength of the clauses beside it. | — |

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

Family `REC-*` extended, and `OPS-REHEARSE-*` new. Every requirement belongs to
a claim (D697); the four new claims are `independent_repository`,
`disaster_kit`, `replacement_host_restore` and `failure_rehearsal`, all dated 18.
`DEP-001` and `DX-001` are unchanged and keep their Session 12 claims.

| Requirement | Priority | What it states |
|---|---|---|
| `REC-REPO-001` | P0 | A project with a mirror holds, at the second provider, every backup set and archived segment the last copy saw; the copy is a scheduled unit whose failure is a failed unit and a doctor check, and the deployed document publishes the last successful copy time (ADR 0188) |
| `REC-REPO-002` | P0 | The mirror has its own credential at its own provider: the mirror pair exists exactly when the mirror is enabled and is not the primary's key, the endpoint is not the primary provider's, and the archiver's configuration never names the mirror; the account boundary is the providers', stated rather than probed (D1022) |
| `REC-REPO-003` | P0 | A restore from the mirror alone, with the mirror's credential and the primary's cipher pass and the primary's credential absent from the container, produces a promoted cluster with the kit's identity and a migration ledger; the mirror's pair reaches pgBackRest through the container's own environment (D1009; the cipher-pass wording dropped, D1022) |
| `REC-KIT-001` | P0 | `dr-kit.sh export` writes every artifact the node-loss runbook names and no secret value; `verify` refuses a kit missing any of them |
| `REC-KIT-002` | P0 | `bootstrap-providers.sh --adopt` binds a host to the Infisical project the kit records BY ID, mints a fresh runtime identity, and refuses to look anything up by name |
| `REC-NODE-001` | P0 | `restore.sh` restores a stanza into the project's own volume only when that volume holds no cluster, refuses otherwise, and never names the live volume of any other project |
| `REC-NODE-002` | P0 | On a replacement host, the restored project publishes the original's `instance_uuid`, holds the rows the backup set held, and every route reads `ready` |
| `OPS-REHEARSE-001` | P0 | `rehearse.sh` induces exactly the scenario named, reverses it, and leaves nothing of its own behind; `--plan` prints and does nothing |
| `OPS-REHEARSE-002` | P0 | Service termination: a killed stateless service is back and its route `ready` within the bound, and the doctor reported the gap |
| `OPS-REHEARSE-003` | P0 | Database restart: every dependent service reconnects without a redeploy; an agent read answers after |
| `OPS-REHEARSE-004` | P0 | Backup credential failure: `check` against a repository with a wrong credential fails closed with the repository named, and a deploy's 6c would refuse |
| `OPS-REHEARSE-005` | P0 | WAL archiving failure, on the MIRROR's path (ADR 0188, D1016): with the mirror endpoint rejected on the backup network, the mirror copy fails -- the unit's failure -- while the doctor's `archiver` check stays ok, and the next copy completes once the path is restored; the primary's archiving is never blocked |
| `OPS-REHEARSE-006` | P0 | Registry loss: an absent port registry is refused by every verb, never recreated; the deploy names the loss |
| `OPS-REHEARSE-007` | P1 | Disk threshold: the doctor's `disk_headroom` reports `warn` and `problem` at its thresholds, rehearsed by injecting the threshold, never by filling a disk |
| `OPS-REHEARSE-008` | P1 | Capability drift: a lock whose hash differs from the deployed document's is reported by the doctor (extends `AGT-DRIFT-001` to the running deployment) |

---

## 4. Irreversible operations

| Operation | Why it cannot be undone, and what bounds it |
|---|---|
| Creating the second account, bucket and key pair | The operator's, by hand, at a provider this repository has never touched; the key is shown once. Scoped to the one bucket. |
| The first full backup to the secondary | Cost and time (~7 minutes per project at `process-max` 1); it also makes the secondary's retention real. Taken by hand, once per project. |
| Rehearsals on the production host | Service termination and a database restart are brief outages of a real project, bounded by `rehearse.sh`'s reversal; run one at a time, never during a backup. WAL-archiving failure is induced on the SECONDARY repository's path (a firewall rule on the backup egress network), never on the primary. |
| The replacement host | Provisioned, two ACME issuances (5/hour/hostname, one each), retired and destroyed at the end of the trip; its retirement records are the trip's. |
| `restore.sh` on the replacement | Into an empty volume only; refuses a cluster. On the production host it is never run. |
| The `1.0.0` tag and the evidence merge | A tag is a promise the compatibility sentence describes; the merge is the only evidence document the stage closes on. |

---

## 5. Build order, run by run

Each run: read its rows, measure what it asserts about a third party with a
control, write the ADR if a decision has alternatives, implement, prove, break
the proofs with a battery, record divergences from D994, mark **Done.** with what
was measured, commit, push, read CI's verdict by full SHA. **Grep every reader of
a function before repairing one** (D979) and **every previous trip's "if
something goes wrong" section before Run 6** (D977).

### Run 1 — the measurements, ADRs 0188–0190

The rig: two S3-compatible endpoints on this workstation (two MinIO containers,
distinct credentials), one pgBackRest in the project's own postgres image, one
stanza. Arms, each with a control:

1. `repo1` + `repo2` configured: a full backup lands in both; `archive-push`
   writes each segment to both; `info` reports both.
2. **`repo2` unreachable** (its container stopped): what `archive_command`
   returns, whether WAL accumulates in `pg_wal`, whether `backup --repo=1`
   proceeds, what `check` reports. **This arm decides the design**: if a lost
   secondary stalls archiving, the render must use asynchronous archiving with
   a per-repository queue, or the secondary must be written by a scheduled
   `backup --repo=2` only, and ADR 0188 says which and why.
3. Restore with only `repo2`'s credential and cipher pass present, `repo1`'s
   files absent: the cluster promotes and answers. Control: with `repo1`'s
   cipher pass swapped in, the restore fails to decrypt.
4. Retention per repository (`repo2-retention-full` differing from `repo1`'s).
5. `restore --repo=2` into an EMPTY data directory versus a directory holding a
   cluster: the refusal `restore.sh` will build on, measured rather than
   assumed.

ADR 0188: the second repository -- a second provider, its own credential and
cipher pass, what it survives and what it does not (D985), and which archiving
mode arm 2 chose. ADR 0189: the disaster kit -- what an operator holds off-host,
that it never holds a value, and adoption by recorded id. ADR 0190: rehearsals
are bounded, reversible, and read a detection that exists; the disk is never
filled. Ledger rows D994+ for whatever the rig disagrees with. Nothing else
changes in this run.

**Done.** Rig 18 on this workstation: two MinIO endpoints
(`RELEASE.2025-09-07T16-13-09Z`) behind one self-signed certificate, distinct
credentials and buckets, one cluster on the project's own image (PostgreSQL
18.4, pgBackRest 2.59.1), one stanza; six arms, every one with a control, and
the rig rebuilt twice for mistakes of its own (container names not matching the
certificate; an include path pgBackRest honours only on the command line) and
once for a WSL restart that emptied `/tmp`. **The design arm reversed Run 2**
(D994–D996): two repositories in one configuration couple the primary's
archiving and backups to the secondary's availability, asynchronous archiving
does not decouple them, a second configuration for the same stanza does not
either in two variants, and `archive-push` has no `--repo`. **The mirror
works** (D998): the primary's bucket copied to the second endpoint in four
seconds, restored from the copy alone with the second credential and the
primary's cipher pass to every row, the wrong pass refused as *no backup set
found* (D999). The non-empty-directory refusal is pgBackRest's own, error 40,
overridable only by `--delta` (D997); retention is per configuration (D1000).
ADRs 0188–0190 written and indexed; §2's `REC-REPO-*` rows and Run 2 rewritten
to the mirror. No code changed. The rig is torn down; its scripts live in
`~/rig18` on the workstation, not in the tree.

### Run 2 — the mirror (rewritten after Run 1; ADR 0188)

**First, one more measurement**: the mirror client against the deployment's
real second provider (§0.1) -- `mc mirror` from a pinned `quay.io/minio/mc`
image, the version recorded in `versions.in.yaml` like every other image --
with a control that a deleted source object is removed at the copy only with
`--remove`, and that the copy's listing equals the source's. If the second
provider's S3 dialect fails the client, §9 applies. **Measured 2026-09-05
(D1001, D1002)**: Backblaze B2 at `eu-central-003`, the mirror complete on the
second pass, a restore from it alone in 151 seconds with every row, on the
project's own image. The provider is chosen; the rest of this run builds on
it.

Then: project manifest schema 4 with `backup.mirror` (`enabled`, `endpoint`,
`bucket`, `region`), absent meaning none, forbidden below v4, v3 manifests
loading unchanged; `naming` derives the mirror bucket's default name
(`apg-<key>-backup-mirror`) once. `secrets.required.yaml` gains
`mirror_s3_access_key_id` and `mirror_s3_secret_access_key` (operator-supplied,
`/backup`), consumed by the mirror container only, and the primary's existing
backup credential gains that container as a second consumer -- both directions
proved by the secret-contract module. **The archiver's configuration does not
change.** A unit pair `agentic-postgres-backup-mirror@.service|.timer` runs
`bin/backup.sh mirror` nightly after the incremental, in a container on the
project's backup egress network (ADR 0147); `provision-host.sh` installs and
checks them by the glob (D970). Outputs v16: `backup_state.mirror` (`enabled`,
`bucket`, `last_copied_at`, `objects`, `status`) beside the primary's block,
`migrate_v15_to_v16` filling `enabled: false`; **every reader of `backup_state`
moves** -- `deployed_output`, `fleet`, `diagnosis`, the schema, the matrix's
classification, the hand-chained migrator tests (D965's grep). The doctor gains
a `mirror` check reading the unit's last success and the copy's timestamp,
naming *empty or undecryptable* where pgBackRest says only *no backup set*
(D999). `restore-test.sh` and `backup.sh info|check` accept `--from CONFIG`, a
pgBackRest configuration naming one repository, which is how a mirror is read.
Offline proofs for every piece; the live proofs of `REC-REPO-001..003` written
and gated on the trip.

**Done.** (2026-09-05, D1004–D1007, ADR 0191.) Project manifest schema 4 with
`backup.mirror` (`enabled`, `endpoint`, `region`, optional `bucket`; absent
means none, forbidden below 4, both example manifests at 4);
`naming.backup_mirror_bucket_name` derives `apg-<key>-backup-mirror` once;
outputs schema 16 with `backup.mirror` and `backup_state.mirror`
(`not_observed|disabled|never|copied`, `last_copied_at`, `objects`),
`migrate_v15_to_v16` refusing anything but a rendered v15. **The contract
needed a third state** (D1007, ADR 0191): `facility: backup_mirror` on the
mirror's pair and on the primary pair's mirror consumer, `active_secrets(...,
facilities=)` as the project's view, and every writer, mounter, requirer and
creator moved to it -- the materializer, the secret override (reading the
rendered document beside it), the render, the deploy's preflight and the
bootstrap's three lists. The container: `services/backup-mirror` on the
pinned `quay.io/minio/mc` (`versions.env` relocked with `--packages-only`),
profile `mirror`, uid 65532, the backup egress network only, four secret files
into `MC_HOST_` aliases in its own environment, `copy` and `count` actions.
The unit pair `agentic-postgres-backup-mirror@.service|.timer` (04:30,
`Persistent`, 20 minutes of jitter, after both backup timers), the launcher's
`backup-mirror` action with no `check` before it, `backup.sh mirror` writing
`mirror-state.json` beside the deployed document only after a pass that
exits 0 AND a listing that parses (D1001, D1004). `fleet.timer_kinds` gives a
mirrored project three timers, and `schedule`, the status verb, the inventory
and the retirement plan all read it; `diagnosis.mirror` is the doctor's ninth
check (OK/WARN never/WARN stale after two days/UNKNOWN unreadable), and the
deploy folds `read_mirror` into every branch of `backup_state`. Measured on
the pinned image: `mc ls --json`'s line format (D1004). Not built: `--from
CONFIG` on the drill (D1006, Run 3). Proofs: `tests/contract/test_backup_mirror.py`
(35), the guard modules widened (`test_backup_schedule`, `test_fleet`,
`test_backup_schedule_verb`, `test_doctor_redaction`, `test_repository_contract`,
`test_backup_plane`, `test_output_migrations`, `test_project_manifest`);
battery 13/13 killed after one survivor widened the facility reader's proof
(backups off with a mirror block saying on). The live half -- the first copy
on the host, the timer enabled, `REC-REPO-001..003` -- is the trip's.

### Run 3 — the kit, adoption, `restore.sh`, the runbook

`bin/dr-kit.sh export --host host.yaml --project FILE... --output DIR` writes
the manifests, each project's `bootstrap-state.json`, the capability file, and
`secrets.txt` naming every secret's provider key and path with no value;
`verify DIR` refuses a kit missing any artifact the runbook names, and a proof
asserts the kit contains no value by planting the sentinel. `bootstrap-
providers.sh --adopt --state FILE --operator-credential-file FILE` binds the
host to the recorded Infisical project id, creates a runtime identity, grants
it read, writes the credential files and the state; it refuses when the
recorded project id does not exist and never searches by name. `bin/restore.sh
--outputs FILE --repo N --target-time T|--latest` restores into the project's
own volume through the same image and mounts the drill uses, refusing when the
volume holds a cluster or when the stanza does not match the document, and
records `evidence/restore-<key>-<id>.json` in the drill's shape.
`docs/node-loss-runbook.md`: the kit, the replacement host by the documented
path, adoption, materialization with the secondary only, deploy, `restore.sh`,
verification, and the DNS cutover as the last step -- **rehearsed as a plan
and never performed on the trip** (production alpha keeps its domain; the
restored copy runs under a drill domain). Offline proofs with recorded
subprocesses in the retirement's style; batteries.

**Done.** (2026-09-05, D1008–D1013, ADR 0192.) **Measured first, on the
project's own image** (`~/rig18/r3-precedence.sh`, four arms with controls):
the environment overrides a pgBackRest configuration file (D1009); a restore
writes its `--config` and `--config-include-path` into `restore_command`
(D1010); `--target-action` is refused without a `--type` (D1011); `PG_VERSION`
is present in a restored volume and absent in a fresh one, and a populated
directory is `[040]` (D1012, D997). **These reversed Run 3's order** (D1008,
ADR 0192): on the replacement it is adopt, materialize, render, `restore.sh`,
deploy -- a deploy first would `initdb` the volume and 6c would meet a
foreign system identifier -- and the mirror cannot be a manifest's primary.
Built: `dr_kit` + `bin/dr-kit.sh export|verify` (the two host manifests and,
per project, the manifest, `bootstrap-state.json`, the deployed document and
`secrets.txt` from the project's view of the contract; every file validated by
its loader on the way in, the listing generated, `kit.json` with digests;
export refuses an existing directory and writes 0700/0600; verify refuses a
missing or altered artifact and a directory whose state, document or manifest
names another key); `bootstrap-providers.sh --adopt --state FILE` (ADR 0189:
`ControlPlane.get_project` by id at `GET /api/v1/workspace/{id}`, D1013; a
fresh identity, membership and client secret recorded as this host's, the
project never; refusals for a host that already records the project, a 404, a
foreign organisation, differing provider inputs, a state naming another key);
`node_restore` + `bin/restore.sh --outputs KIT-DOC --project MANIFEST
--rendered-dir DIR --from mirror|primary --latest|--target-time T [--plan]`
(the project's own volume derived from the key and every mount checked
against it; the configuration from `build_pgbackrest_conf` with a `region`
keyword, mounted at `/etc/pgbackrest/restore.conf`; a mirror restore mounts the
cipher pass and the mirror pair's two raw files -- the pair's new postgres
consumers, facility-gated -- and carries them into the container's
environment through a wrapper, the primary's includes never mounted; refuses
a mounted or populated volume with exit 7; builds the image through
`compose.sh`; promotes in its own instance container; the verdict needs a
replay LSN, timeline ≥ 2, the kit's `instance_uuid` and a migration ledger;
`evidence/restore-<key>-<id>.json` in the drill's shape with `source` and
`identity`; the wrapper's trap stops the two containers and never a volume);
`docs/node-loss-runbook.md` in the measured order with §6's three rehearsal
rules (drill domain, own bucket, `schedule enable` never run) and a
symptom table; `docs/provider-bootstrap.md`'s fourth mode. Not built: the
drill's `--from CONFIG` (D1006 stands; the mirror is `restore.sh`'s subject).
Proofs: `tests/contract/test_disaster_kit.py` (16, the sentinel planted in a
generation and asserted absent, adoption against a recorded control plane
that asserts the exact call sequence, the runbook's commands exist in the
measured order) and `tests/contract/test_node_restore.py` (18, the plan, the
refusals, the measured argument vectors, the verdict, the command against a
recorded docker); battery 13/13 killed. CI on `a8cf5d6` was red on one
guard the targeted list had omitted, `test_cli_contract`'s coverage of
`bin/` (D1014); the four commands listed in the repair commit. The live
half -- a kit exported from production, `--adopt` on the replacement, the
restore from the real mirror, `REC-NODE-002` -- is the trip's.

### Run 4 — `rehearse.sh`

One verb, eight scenarios, each a module in `src/agentic_postgres/rehearsal.py`
with `induce`, `observe`, `reverse` and a `--plan` that prints all three and
does nothing. The observations are the readers that exist: the doctor's checks
(`--json`), the alert rules' expressions evaluated against the project's
Prometheus, `backup.sh check`, `database-ports.sh show`. **Registry loss becomes
a refusal in this run**: `port_allocations.load_registry` on an absent file
raises, every verb reports it, and `allocate` never creates a registry it did
not find (the initial registry is provisioning's, not allocation's). Disk
threshold injects `--disk-warn-copies` into the doctor and reads `warn`. WAL
archiving failure blocks the SECONDARY's endpoint on the backup egress network
and reads the archiver check, then unblocks and reads it recover. Offline
halves with recorded docker, systemctl and iptables; live halves are the
`OPS-REHEARSE-*` proofs, gated on the trip.

**Done.** (2026-09-06, D1015–D1019, ADR 0193.) **Measured first** (rig 4,
`~/rig18/rig4.sh` and `rig4.txt`, on Docker Desktop 29.5.2, so the process
kill went through a `--pid=host` container; on the host it is `kill` as root):
`docker kill` leaves an `on-failure:5` container stopped, exit 137, restart
count 0 (D1015); a SIGKILL to its main process from the daemon's namespace is
restarted in 1.7 s; `kill -9 1` from inside is ignored; `docker start` after a
`docker kill` is the fallback; a DOCKER-USER REJECT selected by the backup
network's subnet and the destination address blocks that network only (the
control network reached 1.1.1.1:443 with the rule standing) and is deleted by
its comment in the form `iptables -S` prints. **These changed three rows of
ADR 0190's table** (ADR 0193 amends it): the induce, the service (`edge-probe`,
the health route's server, D1019), and the WAL scenario's reader (the mirror
verb's exit; the doctor's mirror check reads a record a failed copy never
writes, D1016). Built: `agentic_postgres.rehearsal` (the eight plans over
`Facts` the command reads by label, `render_plan`, `iptables_delete_arguments`,
`foreign_lock`, `verdict`, `record`); `bin/rehearse.sh SCENARIO --outputs FILE
[--plan]` and `reverse` (induce, observe, reverse in a `finally`, the
in-progress file at `/etc/agentic-postgres/rehearsal-in-progress.json` that
refuses a second scenario and lets `reverse` replay a crashed one, the evidence
record `evidence/rehearsal-<key>-<scenario>-<id>.json`, exit 6 for a reader that
read nothing and 7 for a reversal that did not verify; every reading a value
the command produced, never a subprocess's words); the doctor's tenth check
`capability drift` (D1017) and its injections `--disk-warn-copies`,
`--disk-problem-copies`, `--lock-file`, forwarded by `doctor.sh`, refused as
input when impossible; the registry refusal in all three readers and its
creation by provisioning (D1018). Not used: the alert rules' expressions --
no scenario's reader is an alert -- and `systemctl`, since the unit's failure
is read through the verb the unit runs. Proofs: `tests/contract/test_rehearsal.py`
(61: the plans, the command against a recorded runner with real files for the
registry and the lock so that "reversed" is a property of the filesystem,
every port verb's refusal, the deploy's, provisioning's creator by scan, the
doctor's two rehearsed readers); `test_diagnosis`'s ADR 0158 guard replaced by
a stricter one pinning the single `mcp` read; `test_doctor_redaction`'s rig
gains the tenth probe; the CLI contract, the reader guard and the live check
list extended. Battery 14/14 killed with green controls (D499, D386). The
targeted list of fourteen guard modules green (946). The live halves -- eight
readings on the production host, `OPS-REHEARSE-002`..`008` -- are the trip's
(Run 6 step 3); the WAL scenario refuses until the trip enables the mirror.

### Run 5 — the bump

`CURRENT_SESSION` 18, `VERSION` 1.0.0 with the compatibility sentence (D991),
the requirements of §2 and four claims, `bin/session-18-check.sh` derived by
diff from session-17's (host mode gains `--secondary-repo-check`, `--kit-dir`,
`--replacement-host-outputs`; the roster in `tests/conftest.py` gains every
gate the new proofs read, D687), `docs/recovery-operations.md` for the second
repository and the rehearsals, `docs/node-loss-runbook.md` linked from the
README's operating block, `docs/scope-closure.md` §2 and §6 updated, and
`docs/stage-3-decision-report.md` written with its numbers marked *filled at
the trip's close* (D992). Documentation, registry, generated docs; the guard
modules the bump touches in the targeted list (D968).

**Done.** (2026-09-06, D1020–D1022.) `CURRENT_SESSION` 18 and
`template_version` 1.0.0 in one commit with the fifteen requirements
(`REC-REPO-001..003`, `REC-KIT-001..002`, `REC-NODE-001..002`,
`OPS-REHEARSE-001..008`; §2's `REC-REPO-002/003` texts corrected to what is
proved, D1022), the four claims and their sessions, and -- because Runs 2–4 had
written no live half (D1020) -- two deployment modules gated on four new
declarations: `tests/deployment/test_session18_recovery.py` (the mirror's
completed copy the doctor reads and the third timer; the mirror's key id not
the primary's and the archiver naming no mirror; the restore record from the
mirror alone; the kit verifying and holding no value the active generations
hold; adoption by the recorded id with a fresh identity; `restore.sh --plan`
refused against the filled volume; the original identity and every route
ready on the replacement) and `test_session18_rehearsal.py` (one proof per
scenario over the rehearsal records, and `-001` reading the host after: no
in-progress file, no moved-aside registry, no foreign lock, no tagged rule,
`--plan` changing nothing). `bin/session-18-check.sh` derived by diff from
session-17's -- the literal once, the header and the usage's modes rewritten
line by line (D853, D858), four host-mode flags `--kit-dir`,
`--replacement-host-outputs`, `--restore-evidence-file`,
`--rehearsal-evidence-dir` with their cases, checks and exports (D687),
`--secondary-repo-check` refused by name (D1021), and one Session 18
precondition, step 4b: the mirror enabled and copied on both projects, read
from the record beside the document. The roster gains the four variables.
`docs/product-contract.md` §7 carries the `1.0.0` sentence (D991);
`docs/recovery-operations.md` is written and indexed; `docs/stage-3-decision-report.md`
is written with every trip number marked *filled at the trip's close* (D992)
and answers §6's question as a recommendation: ship the template, and start
the Stage 3 specification from the corrected premises. `docs/scope-closure.md`
§1 recounted, §2 and §6 extended. README's status names 1.0.0 and its deploy
examples and the two operations documents type `--session 18`. The acceptance
matrix and the contract's requirement table regenerated. No code beyond the
gate changed; the guards the bump touches ran targeted. The live halves are the
trip's; the four claims report `not_run` until it.

### Run 6 — the trip

Gate once, every mode; `--setup-plan` with every environment variable set.
Then, in order, the operator at a terminal:

1. The second account, bucket and key pair (§0.1); the two values into Infisical
   under `/backup` for alpha and beta; both manifests to schema 4 with
   `backup.mirror`; materialize; deploy both (unredirected, D972); the mirror
   units installed and enabled; the first copy by hand (`backup.sh mirror`),
   one project at a time; the scheduled copy the next morning read from the
   journal and the document (D973's method).
2. `dr-kit.sh export` for both projects; the kit copied off the host to the
   workstation; `verify`.
3. Rehearsals on the production host, one at a time, never during a backup:
   `OPS-REHEARSE-002..008` with their reversals; every reading pasted.
4. The replacement host (§0.2): provisioned by the documented path; **the
   outsider (§0.3) deploys `delta-dev` there by the documented path** and
   writes the `DX-001` record; its deployed document is `APG_FRESH_HOST_OUTPUTS`.
   Without an outsider, the operator deploys `delta-dev` and only `fresh_host`
   closes.
5. On the replacement, from the kit alone with the primary account's credential
   never present: `--adopt` for alpha, materialize with the secondary only,
   deploy alpha under the drill domain `alpha-dr-db`, `restore.sh --repo 2
   --latest`; `REC-NODE-002`'s proof reads the original `instance_uuid` and the
   row counts against the backup set's.
6. Host gate on production with the new flags; host gate on the replacement;
   external from the workstation; merge; `1.0.0` tagged on the release both
   gates measured; the decision report's numbers filled; `delta-dev` and the
   restored alpha retired with `--record`; the replacement destroyed.
7. D-rows for what the trip finds, Run 6 **Done.**, CLAUDE.md §2 and §9,
   memory, commit, push, CI.

**Expected**: `fresh_host` passes; `documented_path` passes if §0.3 was
arranged; the four new claims pass; the five unrelated `not_run` remain.

---

## 7. Evidence and claims

| Claim | Offline may report | Needs a live half for |
|---|---|---|
| `independent_repository` | The render of `repo2-*` from a v4 manifest; the three secrets' contract in both directions; the v16 migrator; the verbs' `--repo` routing with a recorded pgBackRest | Two real repositories holding the same set; `check` reporting both; a segment in both; the rig's arm 2 re-measured on the deployment |
| `disaster_kit` | The kit's contents and its refusal of a value; adoption's refusal by name against a fake control plane | A kit exported from the production host that a replacement host was built from |
| `replacement_host_restore` | `restore.sh`'s refusals against a fixture volume; the runbook's commands exist (D693's method) | The restored cluster on the replacement answering with the original identity |
| `failure_rehearsal` | Each scenario's plan, induce/reverse pairing, and reversal against recorded tools | Eight readings on the production host |
| `fresh_host` (12) | — | `APG_FRESH_HOST_OUTPUTS` from the replacement |
| `documented_path` (12) | The commands the path names exist (standing) | `APG_DX_RECORD_FILE` from the outsider |

No claim spans both modes; a skip is not a pass; the five unrelated `not_run`
stay so (D478).

---

## 8. Security invariants this session touches

| Invariant | Control | Proof |
|---|---|---|
| A restore never overwrites the active volume | `restore-test.sh` unchanged; `restore.sh` refuses a volume holding a cluster and runs on a replacement only | `REC-SAFE-001`, `REC-NODE-001` |
| A deploy over a broken archiver fails | 6c's `check` covers every repository | `REC-REPO-001` |
| One credential reaches one repository | Two key pairs, two buckets, one cipher pass held off the host by name (ADR 0188) | `REC-REPO-002` |
| No secret value leaves the host in a kit | The kit names, never holds; the sentinel scan | `REC-KIT-001` |
| The bootstrap never adopts by name | `--adopt` takes an id and refuses a search | `REC-KIT-002` |
| A rehearsal leaves nothing behind | Every scenario reverses; `--plan` mutates nothing | `OPS-REHEARSE-001` |
| The port registry is never silently recreated | An absent registry raises | `OPS-REHEARSE-006` |
| The MCP runtime holds no credential | Standing | Unchanged |

---

## 9. Stop conditions

Stop and ask when:

- **Rig arm 2 shows a lost secondary stalls the primary's archiving** and no
  archiving mode pgBackRest offers keeps the primary independent of the
  secondary. Then the secondary is written by scheduled `backup --repo=2` only,
  WAL goes to the primary alone, and ADR 0188 records the narrower guarantee.
- **The second provider's S3 dialect breaks pgBackRest** (path style, region,
  checksum headers). Measured on the trip before any manifest changes; a
  provider that fails is replaced, not worked around in the render.
- **Adoption would need to find an Infisical project by name.** It never does;
  the kit is incomplete and the runbook says so.
- **`restore.sh` would need to touch a volume holding a cluster**, on any host.
- **A rehearsal cannot be made reversible** on the production host. Then it is
  rehearsed on the replacement host only, and the requirement says so.
- **The replacement host cannot get a certificate**; never retry in a loop.
- **No outsider is available**: `documented_path` stays `not_run`, recorded.
- **The `1.0.0` bump would need a second answer to "what is deployed"** (D704),
  or a compatibility rule the tree does not hold.
- A currently-passing proof would be weakened, or an allowlist loosened to a
  subset check.

---

## Appendix — what to consult

`docs/plans/stage-2-plan.md` §4 (the `fresh_host` caution), §5 *Session 18*,
§7–§9. `docs/scope-closure.md` §2 and §6. ADR 0144, 0145, 0147, 0151, 0152 before
Runs 1–3 (the derived image, the bucket of its own, the egress network, the
drill's refusals and its evidence); ADR 0011 and 0110 before Run 3 (what the
bootstrap owns and never creates); ADR 0158 and 0165 before Run 4 (the deployed
document is the address book; `anon` is the figure); ADR 0163 before Run 5
(three statuses); ADR 0185–0187 for the verbs Session 17 left (the inventory,
lifecycle and retirement, which the replacement host's projects use).

**Grep the plans for anything this session touches.** D145 and D548 (the state is
in a field, never the exit code -- pgBackRest above all), D374 (parsing a third
party's log line), D522 and D944 (a schedule written is not a schedule
installed), D553 (a cumulative counter), D593 (the RTO band), D700–D702 (the
document's staleness and the matrix), D941 (read the cluster, never the
migrator's line), D976–D983 (the last trip: provider hangs, readers that did not
move, proofs that had never run, the incremental label). The Session 11 and 17
"if something goes wrong" sections before Run 6 (D977).
