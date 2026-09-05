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
free number after this table is D994**; Run 1 writes its measurements as rows
from there.

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

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

Family `REC-*` extended, and `OPS-REHEARSE-*` new. Every requirement belongs to
a claim (D697); the four new claims are `independent_repository`,
`disaster_kit`, `replacement_host_restore` and `failure_rehearsal`, all dated 18.
`DEP-001` and `DX-001` are unchanged and keep their Session 12 claims.

| Requirement | Priority | What it states |
|---|---|---|
| `REC-REPO-001` | P0 | A project with a secondary repository archives every WAL segment to both repositories and holds the same backup sets in both; `backup.sh check` reports both, and a deploy fails when either is unreachable |
| `REC-REPO-002` | P0 | The secondary repository has its own credential and its own cipher pass; the primary's credential is not sufficient to read it and the secondary's is not sufficient to read the primary |
| `REC-REPO-003` | P0 | A restore from the secondary repository alone, with the primary's credential absent, produces a cluster the drill queries and answers from |
| `REC-KIT-001` | P0 | `dr-kit.sh export` writes every artifact the node-loss runbook names and no secret value; `verify` refuses a kit missing any of them |
| `REC-KIT-002` | P0 | `bootstrap-providers.sh --adopt` binds a host to the Infisical project the kit records BY ID, mints a fresh runtime identity, and refuses to look anything up by name |
| `REC-NODE-001` | P0 | `restore.sh` restores a stanza into the project's own volume only when that volume holds no cluster, refuses otherwise, and never names the live volume of any other project |
| `REC-NODE-002` | P0 | On a replacement host, the restored project publishes the original's `instance_uuid`, holds the rows the backup set held, and every route reads `ready` |
| `OPS-REHEARSE-001` | P0 | `rehearse.sh` induces exactly the scenario named, reverses it, and leaves nothing of its own behind; `--plan` prints and does nothing |
| `OPS-REHEARSE-002` | P0 | Service termination: a killed stateless service is back and its route `ready` within the bound, and the doctor reported the gap |
| `OPS-REHEARSE-003` | P0 | Database restart: every dependent service reconnects without a redeploy; an agent read answers after |
| `OPS-REHEARSE-004` | P0 | Backup credential failure: `check` against a repository with a wrong credential fails closed with the repository named, and a deploy's 6c would refuse |
| `OPS-REHEARSE-005` | P0 | WAL archiving failure: an archiver that cannot reach its repository is reported by the doctor's `archiver` check within one archive timeout, and archiving resumes when the path is restored |
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

### Run 2 — the second repository

Project manifest schema 4: `backup.secondary` (`enabled`, `endpoint`, `bucket`,
`region`, `retain_full`), absent meaning none, forbidden below v4, with the v3
manifests loading unchanged. `naming` derives the secondary bucket's default
name (`apg-<key>-backup-2`) once. `rendering` emits `repo2-*` from `outputs` as
it emits `repo1-*`. `secrets.required.yaml` gains `backup2_s3_access_key_id`,
`backup2_s3_secret_access_key` (operator-supplied, `/backup`) and
`pgbackrest_repo2_cipher_pass` (generated), rendered as `21-repo2-s3-key-
secret.conf` and `31-repo2-cipher-pass.conf` for the postgres service; the
secret-contract proofs cover them in both directions. Outputs v16:
`backup_state.repositories`, a list with the fields today's single block has,
`migrate_v15_to_v16` wrapping the single block as repository 1; **every reader
of `backup_state` moves** -- `deployed_output`, `fleet`, `diagnosis`, the
schema, the matrix's classification, and the ten hand-chained migrator tests
(D965's grep). `backup.sh info|check|backup` accept `--repo N` and `check`
reports both; `restore-test.sh` accepts `--repo`. Offline proofs for every
piece; the live proofs of `REC-REPO-001..003` written and gated on the trip.

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

### Run 6 — the trip

Gate once, every mode; `--setup-plan` with every environment variable set.
Then, in order, the operator at a terminal:

1. The second account, bucket and key pair (§0.1); the two values into Infisical
   under `/backup` for alpha and beta; both manifests to schema 4 with
   `backup.secondary`; materialize; deploy both (unredirected, D972); `check`
   reports both repositories; first full backup to the secondary by hand, one
   project at a time (~7 minutes each); the scheduled incrementals the next
   morning land in both -- read from the journal and `info` (D973's method).
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
| One credential reaches one repository | Two key pairs, two buckets, two cipher passes | `REC-REPO-002` |
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
