# Session 29 — the trip: deploy `1.7.0`, sweep, tag. Tier 2.

**Status:** planned 2026-09-17, against `f0c6674` on `main`.
**Shape:** **one host trip. A deploy, a reboot, one sweep, and a tag.**
**No rotation, no registry addition, no new requirement, no new claim.**

---

## 0. What this session is, and what it is not

Session 28 closed Tier 1 of `docs/pre-stage-4-audit.md` offline and left the
release sitting in the tree: `VERSION` **1.7.0**, `CURRENT_SESSION` **28**, and
**no tag**. This session is the other half of that arrangement (D1425) — it
deploys the commit, sweeps it, and *then* cuts the tag on the commit that was
deployed. The audit's §*What "perfect before Stage 4" can actually mean* records
that the operator chose **Tier 1 + Tier 2** on 2026-09-16; Tier 1 is done and
**Tier 2 is what this session discharges.**

**`CURRENT_SESSION` does not move and there is no Session 29 gate.** This
session registers no requirement, so it has no half to write and no evidence
document of its own — the same reason 19, 26 and 27 have none (D1063). What it
writes is **Session 28's host and external halves**, merged with the offline one
already at `evidence/session-28-offline.json`, into `evidence/session-28.json`.
`bin/session-28-check.sh` is the gate; it was derived and tested in Session 28
Run 9 and its host mode has never been run.

**The rotation is not in this trip, and that is a decision** (2026-09-17). The
audit's Tier 2 row for D860 says the signing-key rotation *"unblocks
`bootstrap_identity`, `api_authorization` and `credential_rotation_planes`"* —
and **D1469 measured that it does not** (§1). `docs/upgrade-guide.md` §3 step 5
says it in the product's own voice: *"if you take it, take it as its own sitting
… not as a step of an upgrade."* Run 8's **Appendix R** and
`docs/operator-guide.md` §15 are the sheet when that sitting happens.

**What this session is not:** it is not a release session, not a repair session,
and not a walk. If the trip finds a product defect, the defect is recorded and
the release is not re-cut inside the window (§9).

---

## 1. Divergence — what the tree, the audit and the host say, measured

Twelve rows, every one measured against the host or the tree on 2026-09-17.
Eight were written before a line of §5; **D1497 was written by pushing this
document**; and **D1498–D1500 were written by executing Run 1**, which is what a
pre-flight is for. Numbers from **D1489**; the runs allocate from **D1501**.

| D | Said | Measured or read | This session | Why it matters | ADR |
|---|---|---|---|---|---|
| **D1489** | `docs/pre-stage-4-audit.md` Tier 2, and `CLAUDE.md` §2's Session 22 block: *"**D1189** The example project's grant repair (`20260914120002`) **has never been applied on beta**."* | **It is applied.** Beta's deployed document at `/home/op/beta-dev-outputs.json` records `migrations.project_set = {count: 2, root: "projects/example", lock_sha256: a99489e7…}`, and the example set holds exactly `20260914120001` and `20260914120002`. `CLAUDE.md`'s own HOST block agrees from the other side — *"alpha's ledger 32, beta's 34"* — 32 released plus its own two. The row was true when Session 22 wrote it and was closed by ADR 0206's ledger move at Session 24's trip; nobody went back to the audit. | **Confirmed against the LEDGER in Run 5, not against the document** (D941), and closed in the ledger and in `CLAUDE.md` §9 if the ledger agrees. If the ledger says otherwise, the document is wrong and that is a finding worth more than the row. | A Tier 2 row that is already closed makes the trip look bigger than it is, and an operator who plans around it budgets for a migration that will not run. This is the fifteenth expired premise this pair of sessions has found in that page. | 0206 |
| **D1490** | The audit, twice: *"The kernel restart and `--after-reboot` have never happened. 38+ days up"* and *"the host reports `systemctl is-system-running` = **DEGRADED** … unrelated to the deployment … and **not investigated**."* | **Both still true and both now sharper.** `up 40 days, 7:01`, kernel `7.0.0-29-generic`, and `/var/run/reboot-required` present reading *`*** System restart required ***`*. The degraded unit is **named for the first time**: `cloud-init-hotplugd.service` — *Cloud-init: Hotplug Hook* — `loaded failed failed`, and it is the only failed unit. | **Run 2 reboots**, and reads the unit's journal **before** the restart so DEGRADED is understood rather than cleared by accident. If it comes back failed, that is the answer and it is recorded; if it does not, the marker was the whole of it. | A reboot is the one restart nothing in the suite can perform on itself, and the proof that admits it has never been given. Clearing a failed unit by rebooting without reading it first destroys the only evidence of what it was. | — |
| **D1491** | `docs/upgrade-guide.md` §3 step 1: *"The `uv pip sync` line is conditional… Five earlier trips paid for skipping a sync that was needed (D384, D297), and a sync that is not needed reaches PyPI for nothing."* | **A no-op for this hop, measured.** `git diff --stat de2aabf..f0c6674 -- requirements-dev.txt requirements-dev.in .python-version` is **empty**. | **The sheet omits `uv pip sync` and says why**, rather than carrying a line the operator has to decide about at the terminal. | The guide gives the operator a decision and the one-line command that settles it; running that command in the plan rather than in the window is the whole point of having a plan. | — |
| **D1492** | `docs/upgrade-guide.md` §3 step 9, and its table: a release that moved a published operation needs **capture → commit → redeploy**, and *"step 3 is the one this page used to leave out"* (F-031). | **Step 9 does not apply.** `git diff --stat de2aabf..f0c6674 -- contracts/ projects/example/contracts/` is **empty**: no published surface moved. `bin/app-contract.sh --check` and `bin/mcp-contract.sh check` both exit 0 in the tree. | **This is a ONE-PASS trip.** One transport, one render, one price, one deploy per project, one read. §5 says so explicitly so that nobody adds a second pass out of habit. | The second pass is the expensive half of an upgrade and it is conditional. A trip that performs it when nothing moved spends an hour re-deploying a digest that did not change. | — |
| **D1493** | **D1375**, Tier 2: *"`op` on the host cannot reach the Docker socket, and Session 25 is the first release whose OFFLINE mode needs one. The group membership was deliberately not granted."* | **Still exactly true**, measured tonight: `docker ps` as `op` → *permission denied while trying to connect to the docker API at unix:///var/run/docker.sock*, and `id -nG` → `op sudo users`. No `docker` group. | **Unchanged, and the trip does not grant it.** Docker group membership is root-equivalent on a production host. The consequence is stated in §7: **the host cannot produce an offline half**, and the offline half this session merges is the one the workstation already wrote. | The row reads as a defect and is a decision. A trip that "fixed" it would hand a non-root account root on production to make a gate mode symmetrical. | — |
| **D1494** | `CLAUDE.md` §2: *"the bare `/home/op/<key>-outputs.json` are STALE (2026-08-23) — reading those instead is a silent way to measure the wrong release."* | **Still there and still stale**, measured tonight: `alpha-outputs.json` and `beta-outputs.json` both read `template_version 0.1.0-dev`, `deployed_through_session 9`, `schema_version 12`, written 2026-08-23. The current pair are `alpha-dev-outputs.json` and `beta-dev-outputs.json` at `1.6.0` / session 25 / `de2aabf`, written 2026-09-15. | **Every flag in the sheet names the `-dev-` file explicitly**, and Run 6 refreshes those two and **leaves the stale pair alone** — renaming or deleting them is a change to the host this trip did not come to make. | Two of the five filenames under `/home/op` differ by four characters and one of them measures a release from four sessions ago. `--project-a-outputs` pointed at the wrong one produces a sweep that passes against the wrong deployment. | 0158 |
| **D1495** | The plan's own first draft: *reboot, then deploy, then sweep* — with no reading of what `--after-reboot` actually asserts. | **The order is load-bearing and it survives, but only because `bound_at` does not move.** `test_the_reboot_restored_the_projects_from_their_documents` asserts `pg_postmaster_start_time() > btime` **and** `app_private.project_identity.bound_at < btime` — the processes postdate the boot and the data predates it. A deploy after the reboot recreates containers (still postdating) and does **not** re-bind identity, so both halves hold. The allocation check compares the port registry against the deployed document, and ADR 0042's allocation is host-global and stable across a deploy. | **Reboot in Run 2, BEFORE the deploy**, and the declaration is still true at sweep time. The reason for that order is not the proof: it is that a unit failing to come back on `1.6.0` is a different finding from one failing to come back on `1.7.0`, and doing both at once makes the failure unattributable. | The flag is a claim the operator makes and the assertions are what stop it being taken on trust. Ordering it by convenience rather than by what it asserts is how a declaration becomes a formality. | — |
| **D1496** | `docs/pre-stage-4-audit.md` Tier 2, the D860 row: the rotation *"unblocks `bootstrap_identity`, `api_authorization` and `credential_rotation_planes`"*, and the audit's §*What perfect can mean* prices reading 2 as *"one host trip **with the rotation performed**"* which *"closes four of the seven unproven claims"*. | **The premise is wrong and Session 28 Run 8 measured it** (D1468, D1469). All nine of those claims' node ids are `live_host`; between them the three claims need **four** rotations — the signing key, the authenticator password, the documentation Basic Auth password, and the application credential on both projects — and a claim is `not_run` unless **every** node id it names passed. The signing-key cutover moves **one of nine** and therefore closes **no claim on its own**. | **The rotation is out of this trip** (§0), and the audit's row is annotated in `docs/scope-closure.md` rather than silently worked around. The three claims stay `not_run` and this session says so in §7 rather than implying the trip moved them. | Four trips have been offered "the rotation" as a single act that closes three claims. Performing it on that understanding would have produced an irreversible cutover, a fresh window, and three claims still `not_run` — which is the worst of both. | 0170 |
| **D1497** | This plan's own first draft, §5 Run 3: *"`git rev-parse FETCH_HEAD` confirmed to equal `f0c6674289…`"* — the commit the plan was written at. | **Pushing the plan moved `main` past it**, immediately and by construction. A trip plan that pins the SHA it will deploy is stale before anybody reads it, and the failure mode is the worst kind: the operator confirms `FETCH_HEAD` against a number that is *almost* right and transports a tree one commit behind the one the plan describes. | **The SHA is read on the day.** What is written down instead is what must be TRUE of it: `VERSION` 1.7.0, `CURRENT_SESSION` 28, and `git merge-base --is-ancestor f0c6674 HEAD` — the commit contains the bump and everything Session 28's gates passed on. Run 8 tags that commit. | D504 exists because a stale generic bundle name moved a host backwards with both commands exiting 0. This is the same shape one level up: a stale *expected value* rather than a stale file. A property is checkable on the day; a literal is a photograph of a moment. | — |
| **D1498** | This plan, §5 Run 3 and Appendix lines 10–11: *"`bump minor`, `requires minor`, `verdict OK`, `reasons []`, **one leaf differing — `template_version`**. Anything else on either project is read against §9 before the deploy"* — taken from **D1481**, Session 28's offline pricing of the class. | **Alpha differs in TWO leaves and beta in THREE** (rig 29a: both project shapes rendered at the commit the host checkout is actually on and at `origin/main`, then priced by the product's own `upgrade_plan.build_plan`). Alpha: `template_version`, `migrations.release_lock_sha256`. Beta: those two plus `migrations.project_set.lock_sha256`. **Verdict, bump and requires are unchanged** — `ok`, `minor`, `minor` — and `operator_digests_moved` is **empty**, so D1107's split deploy does not apply. **D1481 is not wrong**: it priced `72cb2de`→HEAD, and by `72cb2de` *both* locks had already moved — `0033` at `acb08e4` (Run 6) and the project lock's schema 2→3 at `873bdfd` (Run 3) — so its pair spans only Run 9's bump and one leaf is the true answer **for that pair**. | **Run 3 and sheet lines 10–11 now name both counts and every leaf.** The control is in the same rig: without `--also migration_added` the identical pair requires only `patch`, so the declaration is load-bearing and its effect is visible rather than asserted. | This is the worst place in a trip to carry a wrong expected value — the last check before the irreversible half, written as a stop condition. An operator meeting three leaves where the plan promises one either abandons a sound deploy or stops believing the sheet, and the second is permanent. An offline pricing is only ever as good as the commit it called *installed*. | 0162 |
| **D1499** | `docs/upgrade-guide.md` §2's preamble: *"Every command in this section runs from the release that is **ALREADY INSTALLED** on the host"* — and this plan's D1491 and D1492, which both measured that release as **`de2aabf`**, the `source_commit` the deployed documents record. | **The host's checkout is not on `de2aabf`.** `git rev-parse HEAD` in `~op/agentic-postgres` reads **`13c4b390`** — three commits later (`f653812`, `aef612d`, `13c4b39`; Session 25 Runs 7 and 7a) — with `VERSION` 1.6.0 and `git status --porcelain` empty. Session 25 closed on two sweeps and **D1378** records exactly this gap between `source_commit` and `offline_checkout_commit`; nothing since has closed it. | **Both premises re-measured from `13c4b390`, and both still hold**: the diff over `requirements-dev.txt`, `requirements-dev.in` and `.python-version` is empty (D1491), and the diff over `contracts/` and `projects/example/contracts/` is empty (D1492). Every `git diff <installed>..` in this trip names **`13c4b390`**. | *Installed* means two different commits on this host and they are not interchangeable: the document says what was **deployed**, the checkout says what a command **runs from**, and §2 asks the operator to run from the installed release without saying which of the two that is. Here the gap changed neither answer. It is the kind that changes everything exactly once. | 0158 |
| **D1500** | D1490, which read the marker and not its contents: *"`/var/run/reboot-required` present reading `*** System restart required ***`"*. | **`/var/run/reboot-required.pkgs` names five entries**: `linux-image-7.0.0-30-generic`, `linux-base`, `linux-image-7.0.0-31-generic`, `linux-base`, `libc6` — against a running kernel of `7.0.0-29-generic`. The pending restart is therefore a **two-release kernel hop, 29 → 31, skipping 30**, *and* **`libc6`**, which every running process is still mapped against. | **Run 2 gains the expected value it did not have**: after the reboot `uname -r` reads **`7.0.0-31-generic`**. If it still reads `7.0.0-29-generic` the restart did not take the kernel, and the trip stops there — before anything is transported. | A reboot with no expected value is a step that cannot fail, which is indistinguishable from one that was not performed. And `libc6` in that list is why *"both projects came back"* has to be read rather than assumed: the containers restart against a C library the host only finishes replacing at the boot this trip performs. | — |


---

## 2. What this session adds to `tests/acceptance-registry.yaml`

**Nothing.** No requirement, no claim, no `CURRENT_SESSION` move.

This is the shape 26 and 27 had and the reason is the same one stated
positively: a trip that *runs proofs which already exist* is not a session that
adds a guarantee. `bootstrap_identity`, `api_authorization`,
`credential_rotation_planes`, `deployment_convergence`, `port_allocation`,
`agent_record_retention` and `stage_release` are **already registered**; what
this trip changes is their **verdict**, which is what an evidence document is
for (ADR 0163). Inventing a `trip_performed` claim would be a claim about the
trip having been planned, which ADR 0163 exists to refuse.

**One consequence to hold on to:** the evidence document this trip completes is
`evidence/session-28.json`, not a session 29 one, and `bin/session-28-check.sh`
is the gate in all three modes.

---

## 4. Irreversible operations

**Three, and the rotation is deliberately not among them.**

1. **The migration.** `20260917120033` is applied to both production clusters by
   the deploy, and **a released migration is never amended** (D912). If it is
   wrong, the remedy is a new release with a new migration. It is additive —
   two prune functions granted to nobody and a size reading granted to the
   record's existing reader — and it deletes nothing on application. Rig 28b
   applied it to a cluster with history in Session 28 Run 6 and destroyed that
   cluster afterwards.
2. **The tag.** `1.7.0`, cut on the commit that was deployed, **after** the
   reading. A tag can be deleted and cannot be un-published; the three
   occurrences of D1033's class all begin with a tag cut at the wrong moment,
   which is why this one waits for the deploy (D1425).
3. **The reboot**, in the ordinary sense that a production host goes away for a
   few minutes. It is reversible in that the host comes back; it is
   irreversible in that the failed `cloud-init-hotplugd.service`'s journal is
   read **before** it, not after (D1490).

**Reversible and worth naming so nobody treats them as risky:** the transport
and checkout (a `git checkout` on the host), the renders (`--render-only`
writes into `.generated/` and starts nothing), `upgrade check` and `upgrade
plan` (both refuse before any mutation and perform none), and the kit exports.

**A failed deploy leaves the previous release serving**, in every case this
project has measured: the release directory installs beside the old one, the
deployed document is the previous deploy's until step 7 writes it, and step 6
applies nothing when it refuses (`docs/upgrade-guide.md` §6).

---

## 5. Build order, run by run

**The procedure is `docs/upgrade-guide.md` §2 and §3 and this document does not
restate it.** What is here is what is *specific to this hop*: what was measured
in advance, what the operator types, and what each run must read before it
proceeds. Every `sudo` line is the operator's at a TTY; every other line is the
agent's over SSH as `op` (`docs/upgrade-guide.md` §3's two-account rule).

Runs allocate `D` numbers from **D1501**.

### Run 1 — the pre-flight, and the reading that everything after is compared against

`docs/upgrade-guide.md` §2, all seven items, in order. The half that matters
most is the one that is easiest to skip:

- **Write the pre-upgrade doctor reading down, per project.** A deployment that
  reads *9 ok, 1 warning* before will read the same after, and an operator who
  did not record it reads step 7 as the upgrade having broken something. Sort
  what it reports by §2's table: any `problem` stops; `migrations`, `capability
  drift`, `containers`, `cluster`, `pooler` in warning stop; `backup
  repository`, `WAL archiver`, `disk headroom` in warning stop for a different
  reason; `backup mirror`, `TLS expiry`, `health route` in warning are noted and
  proceed.
- **The kit, `-pre`.** `bin/dr-kit.sh export … --output /home/op/kit-<date>-pre`
  for both projects, `verify` it, copy it off to ext4 and verify it again there.
  The `-pre`/`-post` suffixes are not decoration: `export` refuses a directory
  that exists and Run 6 exports again (D1398).
- **A full backup exists and the archiver is well**, both projects.
- **The checkout is clean and `.generated` is owned by `op`**, read with a
  command that can see a dotfile — `.generated/.staging` and `.generated/.locks`
  are dotfiles a glob does not match, which is how a clean-looking tree kills a
  render (D1391).
- **Headroom.** Measured off-host tonight as 23 G free of 38 G and **3.8 G RAM
  with no swap**; the doctor's disk check reads headroom in copies and is the
  authority.

**Done.** _to be written, with the two pre-upgrade doctor readings quoted in
full._

### Run 2 — the reboot, read first and then performed

The audit's row, taken in the order that keeps the evidence (D1490):

1. **Read the failed unit before restarting anything**: `systemctl status
   cloud-init-hotplugd.service` and `journalctl -u cloud-init-hotplugd.service
   --no-pager -n 100`. Record what it says. This is the only chance to see it.
2. **Reboot**, and it has an expected value (D1500). `/var/run/reboot-required.pkgs`
   names `linux-image-7.0.0-30-generic`, `linux-image-7.0.0-31-generic`,
   `linux-base` and **`libc6`**, against a running `7.0.0-29-generic`. So
   afterwards **`uname -r` must read `7.0.0-31-generic`** — a two-release hop,
   skipping 30. If it still reads 29 the restart did not take the kernel and the
   trip stops here, before anything has been transported.

   Wait for the units to reach `active` before reading anything — at `up 0 min`
   every failure means *still booting* and none of them means what it says.
3. **Confirm both projects came back by themselves**: the per-project unit
   `agentic-postgres-project@<key>.service` is `active`, the doctor is no worse
   than Run 1's reading, and `systemctl is-system-running` is re-read — if it is
   still `degraded` with the same unit, that is the answer to the audit's row.
4. The `--after-reboot` declaration is **not** made here; it is a flag on Run 7's
   sweep, and D1495 is why the ordering survives.

**This run is where the trip can be abandoned most cheaply.** Nothing has been
transported and nothing deployed; if the host does not come back well, the
deploy does not happen and the session becomes a repair session.

**Done.** _to be written._

### Run 3 — transport, host units, render, price

`docs/upgrade-guide.md` §3 steps 1–4, with three things settled in advance:

- **`git bundle` under a per-commit name** — `/tmp/apg-<sha[0:12]>.bundle` — and
  `git rev-parse FETCH_HEAD` confirmed to equal the SHA that was bundled
  **before** the checkout, never the `release` line the deploy prints after it
  (D504).

  **The SHA is read on the day and is not written down here.** This plan was
  written at `f0c6674` and pushing the plan itself moved `main` past it, which
  is the whole of D1497: a plan that pins the commit it will be deployed from
  is stale the moment it is committed. What the trip must confirm instead is
  three properties of whatever `main` holds — `cat VERSION` is **1.7.0**,
  `CURRENT_SESSION` is **28**, and `git merge-base --is-ancestor f0c6674 HEAD`
  succeeds, so the commit being deployed contains the bump and everything
  Session 28's gates passed on. The tag goes on **that** commit (Run 8).
- **No `uv pip sync`** (D1491): the hop moves no dependency and the sync would
  reach PyPI for nothing.
- **`--render-only` with the HOST's `capabilities.yaml`**, not the example file
  (D1371), and `template_version` in each rendered document confirmed to equal
  `VERSION` before it is priced.
- **`upgrade plan --also migration_added`**, because a rendered document records
  no migration count and the plan cannot derive it (D743). **What it must
  print**, from **rig 29a**'s measurement of the real installed side in Run 1
  (D1498 — *not* rig 28l's, whose installed side was `72cb2de` and which
  therefore saw one leaf where this hop has two and three):

  | project | leaves that differ | which |
  |---|---|---|
  | **alpha-dev** | **two** | `template_version`, `migrations.release_lock_sha256` |
  | **beta-dev** | **three** | those two, plus `migrations.project_set.lock_sha256` |

  On **both**: `bump minor`, `requires minor`, `verdict OK`, `reasons []`, and
  **`operator_digests_moved` empty** — so D1107's split deploy does not apply and
  neither manifest has to move with this release. Beta's third leaf is ADR 0210's
  doing: the project lock gained `follows_release_version_source` and went to
  schema 3, which moves the bytes `project_set.lock_sha256` digests. The release
  lock leaf is `0033`. **Anything beyond these** — a fourth leaf on beta, any
  non-empty `reasons`, any `operator_digests_moved` — is read against §9
  before the deploy.

**Done.** _to be written, with both projects' `plan --json` quoted._

### Run 4 — the deploy, alpha first, unredirected at a terminal

```
sudo ./deploy.sh --host host.yaml --project project.alpha.yaml \
     --capabilities capabilities.yaml --through-session 28
```

Then beta. **Nothing after the command**: no `> file`, no `| tee`, no `&`.
`sudo`'s pty puts a command whose streams are not all terminals into the
background and the deploy stops forever (D972, D1376).

**This is the first deploy in four sessions that moves a ledger.** It applies
`20260917120033` on both projects and nothing else: one migration, additive,
`app_private` only, granted to nobody.

**Done.** _to be written._

### Run 5 — read what the deploy left, never its summary line

`docs/upgrade-guide.md` §3 step 7, and four readings this hop makes specific:

- **The ledger, not the migrator's line** (D941). Expect alpha **33** and beta
  **35** — 33 released, plus beta's own two. `Pending: 0` prints **twice** on
  beta, once per dbmate invocation.
- **D1489 closes or does not close here.** Beta's ledger is where
  `20260914120002` either is or is not; the document already says it is.
- **The doctor, and it now has ELEVEN checks**, not ten (D1459, D1462). The
  eleventh is `agent record` and it reports two counts and the date the record
  starts with **no threshold**. Its first live reading on this deployment is
  recorded here.
- **`render-jwks` will say something new, and it is not a fault.** This is the
  first deploy at a release carrying D1374's repair: it now says which of three
  things happened, and on an ordinary deploy the answer is *there was no
  previous copy and it cannot tell* — because the deploy replaces the whole
  rendered directory first (D1427). **That is the normal case.** It is neither
  evidence of a rotation nor against one. `upgrade verify` exit 0 and the
  container ages are what say what was recreated.

**Done.** _to be written, with both ledgers, both doctors and the eleventh
check's first live numbers._

### Run 6 — the op-owned copies and the kit, again

`docs/upgrade-guide.md` §3 step 8. Refresh `/home/op/alpha-dev-outputs.json`
and `/home/op/beta-dev-outputs.json` — **those two filenames**, and leave the
stale bare pair alone (D1494). Export `kit-<date>-post`, copy it off, verify it
off the host. **Do not point the gate's `--kit-dir` at it** (D1282):
`REC-KIT-003`'s claim *is* the version gap, its proof `pytest.fail`s on exactly
that, and the flag stays on `kit-2026-09-11`.

**Done.** _to be written._

### Run 7 — one sweep, and the flags it has never been given

**`bin/session-28-check.sh --mode host`**, as root, on the host, with every
declaration a proof it runs can read — a proof that skips for want of its flag
outvotes the pass an earlier session's gate recorded when the JUnits are merged
(D1123, D1133). The flags this trip supplies that no trip has supplied together:

- `--after-reboot` (Run 2 happened, and D1495 is why it is still true here)
- `--fresh-host-outputs /home/op/snippets-dev-outputs.json` — the outsider's
  appliance document, present on the host and read at Session 25
- `--dx-record-file` — **only if a third reader walked the documentation.**
  Without one it is not given, and `documented_path` stays `failed`, which is
  the honest verdict (§7)
- `--kit-dir /home/op/kit-2026-09-11` (D1282), the four replacement/rehearsal
  declarations, `--admin-password-file`, `--removed-project-file`
- **Not** `--rotated-jwt-from-file` or any `--rotated-*`: nothing was rotated.

Then **`--mode external` from the workstation**, which must run from WSL and
therefore needs WSL's outbound TCP — probed healthy 2026-09-17 and re-probed on
the day (`/tmp/s29-net.sh`). Then the merge:

```
python bin/write-session-evidence.py --session 28 \
  --host-input evidence/session-28-host.json \
  --external-input evidence/session-28-external.json \
  --offline-input evidence/session-28-offline.json \
  --output evidence/session-28.json
```

**One sweep, and a second only if the first found a defect.** `-k` for
iteration, which writes no evidence.

**Done.** _to be written, with the three halves' claim tables and the merge's
exit code._

### Run 8 — the reading, and then the tag

**`bin/apg.sh release-reading` on the deployed commit, before the tag** — ADR
0214's first use for a tag actually being cut. It will read `tag_is_owed` with
the bump commit `c14b0ef` behind it and whatever has landed since; the reading's
third question, *is this commit the one the tag goes on?*, is the one this
session answers **yes** to and Session 28 answered **no**. **Read its
`commits after it` line**: the bump is not the tip, so that number is not zero
and every commit it counts is one the tag will carry.

```
git tag -a 1.7.0 <the deployed commit>
git push origin 1.7.0
```

**Then the tag's own proof**, which is not a test and cannot be (ADR 0209 §2 —
a test runs inside a commit):

```
git ls-tree -r --name-only 1.7.0 -- docs/ | grep -E "upgrade-guide|operator-guide"
```

Both paths must print. That is D1388's check, run after the tag rather than
before it, and it is the whole reason the tag waits for the deploy.

**Done.** _to be written, with the reading and the `ls-tree` output quoted._

### Run 9 — the close

`docs/scope-closure.md` §22, `CLAUDE.md` §2's Session 29 block and its HOST
block, the audit's Tier 2 rows marked with what closed them, and the divergence
rows this trip produced. **No code, unless the trip found a defect** — and if it
did, §9 says where that goes.

**Done.** _to be written._

---

## 7. Evidence

**Three halves, one document, and it is Session 28's.**
`evidence/session-28.json`, merged from the offline half already written at
`f0c6674` and the two this trip produces.

| Claim | Now | After this trip |
|---|---|---|
| `stage_release` | **passed offline, red live** | **passed** — the trip deploys before it sweeps, which ends D1401's third occurrence |
| `agent_record_retention` | `not_run` | **passed**, by the deploy that applies `20260917120033` and the six live proofs written in Session 28 Run 9 |
| `project_set_release_record`, `release_reading` | passed (offline) | unchanged; they are checkout claims |
| `deployment_convergence` | `not_run` | **depends on `--redeploy-before-file`** being opened before a redeploy. If the trip performs no redeploy, it stays `not_run` |
| `port_allocation` | `not_run` | depends on what the sweep exercises; the reboot gives it its best chance in twelve sessions |
| `fresh_host` | passed (2026-09-15) | passed, on the same document |
| `documented_path` | **failed** | **still failed**, unless a third reader walked the documentation. §9 |
| `bootstrap_identity`, `api_authorization`, `credential_rotation_planes` | `not_run` | **still `not_run`** — D1496. No rotation is performed |
| `replacement_host_restore` | `not_run` | **still `not_run`.** By decision (D1028) |

**The host cannot produce an offline half** (D1493): `op` has no Docker socket
and the offline mode needs one. The half being merged is the workstation's, at
`f0c6674`, and `write-session-evidence` records the commit each half measured —
so if the host checkout and the workstation disagree the document says so
(D1378's shape).

**`documented_path` stays `failed` and this trip must not make it look
otherwise.** The audit's own closing line is the rule: a session that repairs
what the readers found and then declares victory without a third reader has
gone back to the state where the status had never been emitted. `--dx-record-file`
is given only if somebody actually walked it.

---

## 8. Security invariants this session touches

1. **No GitHub credential reaches the VPS.** Transport is `git bundle` + `scp`
   under a per-commit name (D504). Nothing on the host authenticates to GitHub.
2. **No secret value in a process argument, a log or a redirect.** The deploy
   runs unredirected at a TTY (D972) precisely so the terminal is the log;
   `--admin-password-file` and the rotation flags name *files*, never values.
3. **`op` does not gain the Docker group** (D1493). It is root-equivalent on
   production and the offline gate mode is not worth it.
4. **The agent record is evidence** (ADR 0135, ADR 0142). `20260917120033`
   deletes nothing on application, both prunes are granted to nobody, and
   nothing in this release calls either. **No prune is invoked on production in
   this trip**, and the live proof that exercises one does it inside a
   transaction it rolls back.
5. **DNS records stay grey-cloud; ACME is not retried in a loop** (5/hour/
   hostname). Nothing in this trip touches either, and the reboot does not
   re-issue a certificate.
6. **No applied migration is re-stamped** (D912).

---

## 9. Stop conditions

- **Any `problem` from the pre-upgrade doctor, or a warning on `migrations`,
  `capability drift`, `containers`, `cluster`, `pooler`, `backup repository`,
  `WAL archiver` or `disk headroom`** — repair first, or do not deploy.
- **The host does not come back well from the reboot** (Run 2). Nothing has been
  transported; the session becomes a repair session and the deploy waits.
- **`upgrade plan` prints anything other than `bump minor` / `requires minor` /
  `OK` / `reasons []` with one leaf differing**, on either project. Rig 28l
  measured that exact shape offline against the same pair of documents; a
  different answer on the host means the deployment differs from what the
  render describes, and that is read before it is deployed, not after.
- **`plan` says `BLOCKED` naming `project_sha256` or `capabilities_sha256`** —
  the operator's manifest moved as well as the release. Split it into two
  deploys (D1107) or stop.
- **The deploy exits 5 at step 6 with dbmate saying `Applied` and stderr saying
  `Error:`** — PostgreSQL rolled the migration back and the ledger has no row
  (D940, D941). The project still serves its old release. **Fix forward**; do
  not amend.
- **No tag is cut before the sweep is green**, and none is cut on a commit that
  was not deployed. If the sweep finds a defect, the tag waits for the next
  session — which is exactly the arrangement this pair of sessions exists to
  establish.
- **No rotation.** If the operator decides during the window to perform one, it
  becomes its own sitting with Appendix R open, **after** the sweep — the
  signing-key proof is red between `promote` and `retire` by design (D1470).
- **Nothing is repaired inside the window that can be repaired after it.** A
  product defect found on the host is recorded as a divergence row and carried;
  a release is not re-cut in a maintenance window.

---

## 10. Open items this session carries and creates

### What it closes, if the runs go as planned

`stage_release` · `agent_record_retention` · D1401 (third and last occurrence) ·
the kernel restart and `--after-reboot` · the DEGRADED unit, at least named and
read · D1189 (D1489 — likely already closed) · the tree-and-deployment gap ·
`1.7.0` existing as a ref anyone can adopt.

### What it does not, and who must act

| Item | Who |
|---|---|
| `documented_path` — **failed** | **a third person**, walking the documentation. Not a session |
| `bootstrap_identity`, `api_authorization`, `credential_rotation_planes` | **four rotations**, not one (D1496). Their own sitting, Appendix R for the first of them |
| `replacement_host_restore` | nobody — `not_run` by decision (D1028) |
| `op` cannot reach the Docker socket | a decision, and the decision so far is *no* (D1493) |
| The Infisical control-plane identity holds org admin | a provider-side change nobody has scoped |
| The database container can reach the internet | ADR 0147's residual |
| D688 (nothing to scan over IPv6), D771 (the OOM history) | a network with IPv6 transit; a host reading |
| D976 (Infisical's intermittent hangs) | recorded; the client retries three times |
| The two open product questions | **Stage 4's subject**, not its precondition |

---

## Appendix — the operator's sheet

**Every line below is typed by a human at a TTY on the host.** The agent runs
everything else over SSH as `op` and hands these over one run at a time, with
the expected output beside each. `sudo -n` is not available on this host
(measured 2026-09-17), so each of these prompts for a password.

| # | Run | Line | What it must print |
|---|---|---|---|
| 1 | 1 | `sudo bin/upgrade.sh check --project alpha-dev` | both versions the **installed** one; `verdict OK` |
| 2 | 1 | `sudo bin/doctor.sh --project alpha-dev` | the pre-upgrade reading — **write it down** |
| 3 | 1 | `sudo bin/doctor.sh --project beta-dev` | the same, for beta |
| 4 | 1 | `sudo bin/fleet.sh` | both projects, no surprise third |
| 5 | 1 | `sudo bin/backup.sh --outputs …/alpha-dev/outputs.json info` | a full backup exists; not `awaiting_first_backup` |
| 6 | 1 | `sudo bin/dr-kit.sh export … --output /home/op/kit-<date>-pre …` | the kit, handed to `op` |
| 7 | 2 | `journalctl -u cloud-init-hotplugd.service --no-pager -n 100` | **read before the reboot**, D1490 |
| 8 | 2 | `sudo reboot` | afterwards `uname -r` = **`7.0.0-31-generic`**, not 29 (D1500) |
| 9 | 3 | `sudo bin/provision-host.sh --host host.yaml --check` | no deviation, or the deviation to `--apply` |
| 10 | 3 | `sudo bin/upgrade.sh plan --project alpha-dev --candidate …/.generated/alpha-dev/outputs.json --also migration_added --json` | `bump minor`, `requires minor`, `OK`, `reasons []`, **TWO** leaves: `template_version`, `migrations.release_lock_sha256` (D1498) |
| 11 | 3 | the same for `beta-dev` | the same verdict, **THREE** leaves — those two plus `migrations.project_set.lock_sha256` (D1498) |
| 12 | 4 | `sudo ./deploy.sh --host host.yaml --project project.alpha.yaml --capabilities capabilities.yaml --through-session 28` | **nothing after it** |
| 13 | 4 | the same for `project.beta.yaml` | — |
| 14 | 5 | `sudo bin/migrate.sh --project project.alpha.yaml --runtime status` | 33 `[X]`, `Pending: 0` |
| 15 | 5 | the same for beta | 33 + 2, `Pending: 0` **twice** |
| 16 | 5 | `sudo bin/doctor.sh --project alpha-dev` | **eleven** checks now |
| 17 | 5 | `sudo bin/upgrade.sh verify --project alpha-dev --candidate …` | exit 0 |
| 18 | 6 | `sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/alpha-dev/outputs.json /home/op/alpha-dev-outputs.json` | the **`-dev-`** name (D1494) |
| 19 | 6 | `sudo bin/dr-kit.sh export … --output /home/op/kit-<date>-post …` | the second kit |
| 20 | 7 | `sudo bin/session-28-check.sh --mode host …` | the host half, one sweep |

**Read before the day** (D977): `docs/upgrade-guide.md` §6 and §7,
`docs/session-11-operator-guide.md` §6, `docs/node-loss-runbook.md` §7.

**If something is wrong that this plan did not anticipate**, the rule is §9's
last line: record it, do not repair it in the window.
