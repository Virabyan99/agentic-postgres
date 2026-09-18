# Upgrading a deployment

An operator running any earlier release moves a deployment to the release in
the checkout: what to read first, what to hold before anything moves, the
sequence, what each verdict means for you, what a skipped release costs, and
what to do when a step refuses.

**Every command on this page is copied from the `--help` of the command it
runs, as this release prints it, and every sequence is one a host trip
executed.** Where a step names a date and a plan, that is where it was
measured. Where a step has **not** been measured on this deployment the step
says so, and this page does not describe it as safe (ADR 0208 §3). The only
upgrade surface the product has is `bin/upgrade.sh` (`check`, `plan`,
`verify`) and `./deploy.sh --through-session N`; what follows is what a person
does around them.

> **This page is part of release `1.8.0`.** It describes the commands that
> release ships and the sequence a trip on that release executed. A release
> that moves `VERSION` and does not move this line is a release whose upgrade
> procedure describes a release that no longer exists, which is what happened
> at 1.0.0 (D1033) and again at 1.6.0 (D1388) — so a test now holds this line
> against `template_version()` (ADR 0209).

**Who this page is for.** §1 is the checkout half, which an adopter who owns a
`projects/<slug>/` directory does before any host is touched. §2 onwards is
the host half, which an operator with `sudo` at a terminal does. They happen in
that order, and the checkout half alone is not an upgrade (ADR 0208 §2).

---

## 0. What an upgrade is here

**A release is a commit.** `VERSION` holds its `template_version`, and a
deploy installs an immutable copy of the checked-out commit under
`/opt/agentic-postgres/releases/<commit>` and refreshes the launchers from it
(the deploy's step 3, ADR 0037). The checkout on the host is where a release is
fetched to and rendered from; it is not what runs.

**What is installed is read from two documents, and they answer different
questions** (ADR 0158):

| Document | Where | What it says |
|---|---|---|
| the **deployed** document | `/etc/agentic-postgres/projects/<key>/outputs.json`, root, `0600` | what the last deploy **observed**: `template_version`, `deployed_through_session`, `source_commit`, every route's status, the lock digest the plane loaded, the backup state at deploy time |
| the **installed rendered** document | under the project's rendered directory in `/var/lib/agentic-postgres/` | what the last deploy **asked for** — the left-hand side `upgrade plan` compares against (ADR 0162, D733) |

`bin/upgrade.sh check --project <key>` reads both and says whether a comparison
can be made at all.

**What a version bump promises** is ADR 0162, and it is decidable from two
rendered documents without a host:

| Class | What changed | What you do |
|---|---|---|
| **patch** | implementation only; images may move | nothing before the deploy |
| **minor** | a manifest field with a default, a released migration, a contract entry, a capability, an optional secret, an outputs `schema_version` with a migrator that completes alone | nothing before the deploy: **your manifests still validate unchanged** |
| **major** | a manifest stops validating, a published operation is removed or changed, a secret gains a **required** member, or the document migrator needs a value only you hold | **act before the deploy**, on the thing the plan's `reasons` name |

**Every release since the verbs existed has priced as `minor`**, measured on
this host: 0.2.0 (read-only, 2026-08-29), 1.2.0 (2026-09-11), 1.3.0, 1.4.0 and
1.5.0 (2026-09-13, the last three from one installed 1.2.0), 1.6.0
(2026-09-15). **No `major` has ever been produced or performed here.** §5 says
what the page can and cannot tell you about one.

**Migrations are fix-forward, and that is the boundary of every rollback.**
Every released migration's down block raises `AP900`. ADR 0162 §3 puts it in
one sentence: *once a release applies a migration, that release is the floor.*
So a minor that carries a migration is **not reversible by image rollback**,
and the plan is where you find out before the mutation, not after. §6 says
what rollback does mean.

### The release table

Read from each release's own bump commit, never recalled. *Migrations* is the
count in `migrations/released.lock.json` at that commit; *outputs* is the
deployed document's schema version; *project* is the set of project manifest
schema versions that release accepts.

| Release | Session | Bumped | Migrations | Outputs | Project manifest | What an upgrade meets |
|---|---|---|---|---|---|---|
| 0.2.0 | 13 | 2026-08-29 | 22 | v13 | 1 | the `upgrade` verbs and `bin/apg.sh` themselves |
| 0.3.0 | 14 | 2026-09-02 | 22 | v14 | 1 | metrics on the edge's entrypoint: **the edge must be restarted first** (D811, §3 step 2) |
| 0.4.0 | 15 | 2026-09-03 | 26 | v14 | 1 | migrations 0023–0026; the bootstrap issuer retired, **all four verifiers recreated** (ADR 0170) |
| 0.5.0 | 16 | 2026-09-04 | 30 | v14 | 1–2 | migrations 0027–0030; capability schema 2–3; project schema 2 (profiles) |
| 0.6.0 | 17 | 2026-09-04 | 30 | v15 | 1–3 | lifecycle; `fleet`, `project-retire`; **the backup timer units** (`provision-host.sh --apply`) |
| 1.0.0 | 18 | 2026-09-06 | 30 | v16 | 1–4 | the mirror (`backup.mirror`, schema 4), the kit, `restore.sh`, `rehearse.sh`; **the mirror units** |
| 1.0.1 | 18 | 2026-09-10 | 30 | v16 | 1–4 | nineteen repairs from an adopter's bring-up; `CURRENT_SESSION` stays 18 |
| 1.1.0 | 20 | 2026-09-10 | 31 | v17 | 1–5 | migration 0031 (`api.create_task`); a project's own migration set (`migrations.set`, schema 5) |
| 1.2.0 | 21 | 2026-09-11 | 31 | v18 | 1–6 | lock schema 4 with the derived vocabulary; a project's own capability manifest (`mcp.capabilities`, schema 6); capability schema 4; **`auth` and `mcp` recreated** |
| 1.3.0 | 22 | 2026-09-12 | 31 | v18 | 1–6 | `apg dev`. **One leaf differs, `template_version`**: a minor a deployment cannot see |
| 1.4.0 | 23 | 2026-09-12 | 31 | v18 | 1–6 | `apg generate`; `versions.env` moved, so images move |
| 1.5.0 | 24 | 2026-09-13 | 32 | v18 | 1–6 | migration 0032; **a project's set gets its own directory and ledger table** (ADR 0206) — see §4 |
| 1.6.0 | 25 | 2026-09-14 | 32 | v18 | 1–6 | `apg completion`, `apg dx-record`, `APG_PROJECT`. One leaf differs, `template_version` |
| 1.6.1 | 25 | 2026-09-16 | 32 | v18 | 1–6 | documentation repairs from an adopter's 1.0.0→1.6.0 upgrade, and the product defects it exposed. **A patch**: no schema moves, no migration is added, no command gains a verb. `CURRENT_SESSION` stays 25 |
| 1.6.2 | 25 | 2026-09-16 | 32 | v18 | 1–6 | what 1.6.1's tag missed by one commit: `freeze-lock`'s looping remedy, the *10 ok* precondition, and `docs/upgrade-findings-response.md`. **A patch**, `CURRENT_SESSION` stays 25 |
| 1.7.0 | 28 | 2026-09-17 | 33 | v18 | 1–6 | migration 0033 (the agent record's two prunes and its size reading, granted to nobody and called by nothing); `apg release-reading`; **a project's lock moves to schema 3** and records whether its `follows_release_version` was computed or declared (ADR 0210) — a schema-2 lock still reads, as `computed`. `CURRENT_SESSION` goes 25 → 28; 26 and 27 registered nothing. **A minor**: no manifest, outputs, capability or secret schema moves, and `upgrade plan` between a 1.6.2 render and a 1.7.0 one shows **one leaf differing, `template_version`** |
| 1.8.0 | 30 | 2026-09-19 | 33 | v18 | 1–6 | a container-exec discipline (ADR 0218): every `docker exec` and every `compose.sh run` the product performs is built by one function and runs with stdin closed unless input is supplied, so a `sudo` product command under a redirect cannot stop. `apg release-reading --ref REF` (ADR 0219) and `bin/mcp-contract.sh compile --output PATH`, which no longer asks you to truncate your own contract with a `>` (D1359). Two guards over the suite's shape. `CURRENT_SESSION` goes 28 → 30; 29 took the trip that tagged 1.7.0 and registered nothing. **No migration, no schema move, and no command gains or loses a verb**: a redeploy recreates nothing whose mounted content did not move (ADR 0155), so expect the ledger unchanged at 33 and the verifiers' containers to keep their ages |

A row's *what an upgrade meets* is what the trip that deployed it recorded in
its plan's §5 *Done* paragraph. **A project manifest below the newest schema
still deploys**: alpha's is schema 4 and was deployed at 1.6.0 on 2026-09-15
(the control the plans keep); a manifest below 5 renders as a project with no
set of its own. Moving a manifest's schema is a separate operation from an
upgrade, and §3 step 4 says why.

---

## 1.0 What this page does not cover: a fork made before `projects/<slug>/`

**Read this before §1.** §1 assumes your domain lives in `projects/<slug>/`,
which the release tracks as *yours* and never touches. That mechanism arrived
at **1.1.0** (`migrations.set`, project manifest schema 5) and was completed at
**1.2.0** (`mcp.capabilities`, schema 6). If you forked at **1.0.0 or earlier**,
it did not exist, and the only thing the release offered was to put your domain
**inside the release's own files** — your migrations in `migrations/templates/`,
your operations in `contracts/postgrest-api-surface.yaml`, your rows in
`migrations/manifest.json` and `migrations/released.lock.json`.

**If that is your fork, §1 is not written for you and it will not come out
clean.** This is measured, not anticipated: an adopter who forked at 1.0.0 ran
§1's first command against 1.6.0 on 2026-09-16 and `git merge` produced **nine
conflicted files**, every one of them a file the release owns and the fork had
amended. Two of them — `migrations/released.lock.json` and
`contracts/postgrest-openapi.canonical.json` — are generated artefacts carrying
digests, where *resolve by hand* and **a released migration is never amended**
(D912) pull in opposite directions. And the collision is structural rather than
bad luck: the release occupies `0031` at 1.1.0 and `0032` at 1.5.0 in the same
template directory a 1.0.0-era fork was obliged to write into.

**What this release does and does not say about it.**

- **It works.** The same adopter completed the upgrade to 1.6.0 and the
  deployment doctors 10 ok. A fork whose manifest is `schema_version: 4`
  declares no set of its own, so its migrations stay in the release's directory
  and sort below the release's new ones, and ADR 0206's split never engages.
  The release table's own note applies: a project manifest below the newest
  schema still deploys.
- **Two of §1's six checks refuse such a fork, and that is correct** — see §1's
  table below, which says which two and what the refusal means.
- **How a pre-1.1.0 fork CONVERTS to `projects/<slug>/` is DECIDED, and it is
  [`docs/on-ramp.md`](on-ramp.md)** (ADR 0212). It was undecided in 1.6.2 and
  this page said so; what was actually missing was one flag. Re-homing moves no
  bytes and no version, so D912 is not engaged by it; ADR 0206's ledger move
  already relocates a re-homed version by stamp; and the one thing the product
  had to grow is `freeze-lock --project --follows`, which records the release a
  set was really frozen against (ADR 0210, from **1.7.0**). **Do not read §1 as
  describing that conversion** — §1 assumes it has already happened.
- **Which side wins each merge conflict is four classes, on the on-ramp page**,
  measured on a fork rebuilt from tag `1.0.0` rather than reasoned. The count
  is not fixed: that adopter amended nine release-owned files and got nine
  conflicts, and a rebuilt fork amending four got two. The class worth knowing
  before you merge is the third: `contracts/postgrest-api-surface.yaml`
  **auto-merges**, so a tenant relation can end up inside the release's
  reviewed contract with no conflict marker and no review. Diff it against the
  release's own copy after every merge, conflict or not.

---

## 1. The checkout half — an adopter's fork, before any host is touched

An adopter's project is a directory the release checkout tracks (ADR 0198):
`projects/<slug>/` with its migration set, its reviewed surface, its snapshot,
its capability manifest and its generated client. Bringing it to a new
release is a merge and six checks, all of which write nothing to a host and
are undone by `git checkout`.

```bash
git fetch origin --tags
git merge 1.6.0                           # or the release commit, onto the branch that carries projects/<slug>/
bin/migrate.sh --project project.yaml verify-lock
bin/api-contract.sh --check --project project.yaml
bin/mcp-contract.sh check --project project.yaml
bin/apg.sh generate --check --project project.yaml
./deploy.sh --project project.yaml --capabilities capabilities.yaml --render-only
bin/apg.sh dev reset --project project.yaml
```

What each check answers, from its own `--help`:

- **`verify-lock --project`** checks *both* locks: the release's, which the
  merge moved, and yours, which it did not. Your lock records
  `follows_release_version`, the release version your migrations must all
  sort after at the moment you froze. Since 1.5.0 the two sets are applied
  from separate directories into separate ledger tables (ADR 0206), so a
  release migration newer than yours no longer refuses a deploy (that was
  D1288, and it stopped beta's 1.5.0 deploy on 2026-09-13 before the repair).
- **`api-contract.sh --check --project`** compares the *merged* surface
  against *your* snapshot. A release that adds a published operation (1.1.0
  added `rpc/create_task`) makes your snapshot stale: it is captured from a
  deployment and refuses a hand edit, so this check stays red until §3 step 9
  captures a new one. Expect it, and read D1118 there.
- **`mcp-contract.sh check --project`** compiles your capability manifest
  against the merged surface and your snapshot, and compares your committed
  contract byte for byte (ADR 0201).
- **`generate --check`** refuses for **two different reasons**, and the remedy
  differs. If your project has a set of its own, it exits 5 after every bump
  because the client's `templateVersion` is derived from the release (D1238):
  regenerate and commit it in the same change, `bin/apg.sh generate --project
  project.yaml`. **If your manifest is schema 4** it exits 5 saying
  *"clients/typescript/README.md is missing; the client has not been generated
  from this contract"* — the default output for a project with no set is
  `clients/typescript` under the checkout root, **and the release tracks no such
  directory**. Regenerating is not the remedy there; a project with no set of
  its own has no client of its own to regenerate. Measured 2026-09-16 (D1404).
- **`--render-only`** is the whole of what a checkout runs; the gate's step 2
  and `apg dev up` both refuse a project this checkout has not rendered.
- **`dev reset`** rebuilds the local cluster from the new render, applying
  both sets as the migration user — a migration of yours that the new release
  refuses fails here in ten seconds rather than in step 6 of a deploy.

**Which of the six refuse a manifest with no set of its own, measured
2026-09-16** against a valid schema-4 manifest on this checkout:

| Check | schema 4 | Why |
|---|---|---|
| `migrate verify-lock --project` | **refuses, exit 5** | *"declares no `migrations.set`, so it has no lock of its own"* |
| `api-contract --check --project` | **refuses, exit 2** | the same: there is no project-owned snapshot to compare |
| `mcp-contract check --project` | exits 0 | compiles the release's own six tools |
| `--render-only` | exits 0 | |
| `apg dev status --project` | exits 4 | about cluster state, not about the manifest |
| `generate --check --project` | exits 5 | D1404 above, not the `templateVersion` reason |

**The two refusals are correct and they are not a blocker.** Both name a lock
and a snapshot that a project with no set of its own does not have. Run the
`--project`-less forms instead — `bin/migrate.sh verify-lock` and
`bin/api-contract.sh --check`, which each exited 0 in the same reading — and
read the release table's note: a project manifest below the newest schema still
deploys.

Then the gate, on a clean tree: `bin/session-01-check.sh`.

**Not measured.** No adopter's fork has been carried across a release boundary
by this sequence on record: the one adopter this project has (ADR 0197, the
application at its own host) is on its own fork of 1.0.0 and has not been
brought forward. The six checks are the ones the gate runs on every release,
and `verify-lock --project`, `api-contract --check --project` and `generate
--check` have each gone red for the reason named above on a trip. The merge
itself is git's.

---

## 2. Before anything moves on the host

Hold these, in this order, and do not start §3 without them. Each is a thing
that a trip found it needed after the fact.

> **Every command in this section runs from the release that is ALREADY
> INSTALLED on the host, not from the one you are upgrading to** — §3 step 1 is
> where the new release arrives. That matters more than it reads: this page was
> written from a 1.6.0 checkout and describes each command as 1.6.0 performs
> it. Where a step's behaviour was measured on a release later than the one you
> are running, the step says so and gives the older behaviour (D1392). The
> release table's *what an upgrade meets* column is about what the DEPLOY
> meets, and says nothing about which release executes this preparation.

1. **Read what is installed.** As root, per project:
   ```bash
   sudo bin/upgrade.sh check --project alpha-dev
   sudo bin/doctor.sh --project alpha-dev
   sudo bin/fleet.sh
   ```
   **`check` reads no candidate and prices nothing.** Its question is whether
   a comparison can be made at all: was the installed document readable, and is
   it the same kind of document this release renders. Run here — from the
   host's own checkout, before §3 step 1 fetches the new release — **both
   versions it prints are the installed one**, and it will say so cheerfully on
   a host about to take a release six minors ahead. That is not a verdict on
   your upgrade; the pricing is §3 step 4's `plan --candidate`. Since 1.6.1 the
   command says which question it answered in words; on an earlier release it
   prints `verdict OK`, which is the same answer to the same question (D1393).
   `undetermined` blocks and is not *no changes*.

   The doctor reads **10 ok** on a well deployment (2026-09-15, both projects).
   **Not every warning is a reason to stop, and this page used to say it was.**
   A cold reader met a deployment reading *9 ok, 1 warning* — the backup mirror
   had never been enabled — and the page's absolute *"anything else is repaired
   before the upgrade"* gave them no way to tell a pre-existing condition from a
   blocker. Sort what the doctor reports:

   | Verdict | Before the upgrade |
   |---|---|
   | any `problem` | **stop.** Repair it first, whatever it is |
   | `migrations`, `capability drift`, `containers`, `cluster`, `pooler` in warning | **stop.** These are the planes the upgrade moves, and a warning here becomes unreadable once the deploy has run |
   | `backup repository`, `WAL archiver`, `disk headroom` in warning | **stop**, and for a different reason: step 2's whole purpose is to have a restorable copy before anything mutates. A warning here means you may not have one |
   | `backup mirror`, `TLS expiry`, `health route` in warning | **note it and proceed.** These do not affect what the deploy does, and repairing them is not made easier by doing it now. Record the reading so the post-upgrade doctor is compared against it and not against 10 |

   Whatever you decide, **write the pre-upgrade reading down**. A deployment
   that read 9 ok before will read 9 ok after, and an operator who does not know
   that reads step 7 as the upgrade having broken something (D1391's family: a
   page that spends a reader's trust before the failure arrives).

   Anything genuinely broken is repaired before the upgrade, because a failed
   upgrade over a sick project leaves you unable to say which caused what.
2. **Export the kit and take it off the host.** The kit is what you hold if
   the upgrade takes the host with it (ADR 0189, `docs/node-loss-runbook.md`
   §0). As root:
   ```bash
   sudo bin/dr-kit.sh export --host host.yaml --capabilities capabilities.yaml \
        --output /home/op/kit-$(date -u +%Y-%m-%d)-pre \
        --project project.alpha.yaml --project project.beta.yaml
   bin/dr-kit.sh verify /home/op/kit-<date>-pre
   ```
   **The `-pre` suffix is not decoration.** `export` refuses a directory that
   already exists, deliberately, and **§3 step 8 has you export again after the
   upgrade** — so an upgrade performed in one sitting exports twice on one day
   and a bare `kit-$(date)` name makes the second export refuse. Name them
   `-pre` and `-post`; step 8 uses the second (D1398). The guard is right and is
   not being worked around: the two kits describe two different deployments and
   should not share a name.

   `verify` takes no `--project` (D1316). Copy the kit off to an ext4 filesystem
   — the `0700`/`0600` modes do not survive a Windows drive — and `verify` it
   there from a checkout. Measured 2026-09-15 (`s25-kit.sh`, kit-2026-09-15,
   verified on the host and again in `~/dr-kits/`).

   **If the release you are running is 1.0.0 or earlier, `export` does not hand
   the kit over** and you must do it yourself. `_hand_to_operator` arrives in
   **1.0.1** (`git show 1.0.0:bin/dr-kit.py | grep -c _hand_to_operator` → 0; at
   `1.0.1` → 2), so at 1.0.0 the kit stays `root:root 0700`, the operator can
   neither `verify` it nor copy it off, and the remedy is one line as root:
   ```bash
   sudo chown -R op:op /home/op/kit-<date>-pre
   ```
3. **Confirm a full backup exists and the archiver is well.**
   ```bash
   sudo bin/backup.sh --outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json info
   sudo bin/backup.sh --outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json schedule status
   ```
   `awaiting_first_backup` means nothing can be restored yet; take one by hand
   (`backup --type full`) before an upgrade that carries a migration.
4. **Check disk headroom.** A restore materialises a second copy of the
   cluster (`bin/restore-test.sh --help`), and the doctor's disk check reads
   headroom in copies. Nothing else checks it for you.
5. **The checkout on the host is clean and owned by `op`.** The deploy's step
   3 refuses a dirty checkout (`assert_clean`). **A project manifest may live
   inside the checkout since 1.0.1**: `.gitignore` carries `/project.yaml` and
   `/project.*.yaml`, added by D1034 with the reason written beside it, so a
   third manifest at the checkout root is ignored and `git status --porcelain`
   stays empty. D971's refusal — an untracked file dirties the release and every
   deploy refuses — still applies to a manifest that does **not** match that
   glob; those live at `/home/op/<name>.yaml`. Confirm with `git status
   --porcelain` rather than by moving a file that did not need moving (D1399).

   And `.generated/<key>` can be root-owned after a root `--render-only`, a
   `sudo pytest` or a deploy from a real root login (D1110). **Check it with a
   command that can see a dotfile** — the render's staging and lock directories
   are `.generated/.staging` and `.generated/.locks`, and a shell glob does not
   match a leading dot, so `stat -c %U .generated/*` reports a clean tree and
   the render then dies inside one of them (D1391, measured by a cold reader):
   ```bash
   stat -c '%U %n' .generated .generated/.staging .generated/.locks .generated/* 2>/dev/null
   sudo chown -R op:op .generated     # if any line is not op
   ```
   Since **1.6.1** every directory the render creates names its owner, the
   remedy and the whole `.generated` root when it cannot create one; on an
   earlier release the first of them arrives as a `PermissionError` traceback
   and **exit 1, which is not one of the ten codes the README publishes**
   (D1151/D1391).
6. **Know which manifests move with this release, and plan to move them
   separately** (§3 step 4).
7. **Read the previous trips' *if something goes wrong* before the day**
   (D977): §7 below, `docs/session-11-operator-guide.md` §6, and
   `docs/node-loss-runbook.md` §7.

---

## 3. The host sequence

Two accounts. `op` over SSH does every step that reads, renders or checks out;
**a human at a terminal runs every `sudo` line**, because `sudo` here needs a
TTY and a deploy whose output is redirected stops forever (D972, step 6). A
non-interactive SSH session sources no profile, so scripts run as `op` begin
with `export PATH="$HOME/.local/bin:$PATH"` or `uv` is not found.

### Step 1 — Transport the release and check it out, as `op`

Transport is `git bundle` + `scp`, **under a name derived from the commit**
(D504: `/tmp` is sticky, a stale generic bundle is silently fetched by the next
command, and the host moves backwards with both commands exiting 0). No
GitHub credential is ever on the host.

```bash
# on the workstation
SHA="$(git rev-parse HEAD)"
git bundle create "/tmp/apg-${SHA:0:12}.bundle" main
scp "/tmp/apg-${SHA:0:12}.bundle" op@<host>:/tmp/

# on the host, as op
cd /home/op/agentic-postgres
git bundle verify "/tmp/apg-${SHA:0:12}.bundle"
git fetch "/tmp/apg-${SHA:0:12}.bundle" main
git rev-parse FETCH_HEAD          # MUST equal ${SHA} — confirm BEFORE the checkout
git checkout --detach "${SHA}"    # or: git checkout -B main FETCH_HEAD
cat VERSION                       # the release you expect
git status --porcelain | wc -l    # 0
~/.local/bin/uv pip sync requirements-dev.txt
```

Confirm `FETCH_HEAD` before the checkout, never the `release` line the deploy
prints after it. Measured 2026-09-15 (`/home/op/s25-checkout.sh`, Session 25
Run 7).

**The `uv pip sync` line is conditional, and nothing installs `uv` for you.**
Five earlier trips paid for skipping a sync that was needed (D384, D297), and a
sync that is not needed reaches PyPI for nothing — which on a host with no
outbound HTTPS is a failure rather than a no-op. One line tells you which you
are in:

```bash
git diff --stat <installed source_commit>..HEAD -- requirements-dev.txt requirements-dev.in .python-version
```

Empty output means the hop moves no dependency and the sync is a no-op; skip
it. (It was empty for `1.0.0..1.6.0` — the whole of Stage 3 — confirmed
2026-09-16.) Non-empty means run it.

**And if the host has no `~/.local/bin/uv`**: nothing in this product installs
one. `bin/provision-host.sh` never mentions `uv`, `astral` or `pip install`
(`grep -ci` → 0), and `docs/host-baseline.md` describes both `~/.local/bin` and
`.venv/bin` as things an operator's interactive shell already has — which is a
description of the maintainer's host, not of what `--apply` creates (D1396).
On a host without them, run the `bin/*.sh` commands with whatever interpreter
the distribution provides and **read `python3 --version` against
`.python-version` before you trust a render**: the release pins 3.12 and
enforces it on a workstation through `bin/doctor.sh`, and the machine that runs
every deploy is unchecked.

### Step 2 — The host's own units and the edge, as root

A release can add systemd units or change the edge's static configuration,
and **the deploy does neither**: it expects the host to be ready and refuses
otherwise (`deploy.sh --help`).

```bash
sudo bin/provision-host.sh --host host.yaml --check
sudo bin/provision-host.sh --host host.yaml --apply     # if --check reports a deviation
```

`--apply` on a hardened host installs the missing units and launchers and
**skips** the SSH and firewall steps unless their rollback timer is armed
(`--help`; measured 2026-09-06 when 1.0.0 added the mirror units, Session 18
Run 6). The Session 17 backup units were installed by hand because `--check`
was blind to them then (D970) — read `--check`'s output rather than assuming
a clean report means nothing changed.

If step 6's preflight later says *the running edge declares no
`metrics` entry point*, the edge is serving an older static configuration and
the remedy is the one line it prints: `sudo bin/edge.sh --host host.yaml
restart` (D811, first met upgrading to 0.3.0). ACME state survives a restart.

### Step 3 — Render the candidate, as `op`

```bash
cd /home/op/agentic-postgres
./deploy.sh --project project.alpha.yaml --capabilities capabilities.yaml --render-only
./deploy.sh --project project.beta.yaml  --capabilities capabilities.yaml --render-only
```

**With the host's `capabilities.yaml`, not the example file.** The installed
document's `inputs.capabilities_sha256` digests the host's file, and a
candidate rendered from `capabilities.example.yaml` differs on an input rather
than on the release (D1371, found on the first sweep of 2026-09-15). The
render writes `.generated/<key>/outputs.json`, which is the `--candidate` the
next step needs. Confirm its `template_version` equals `VERSION` before
pricing it: a stale render prices the previous release and reports `minor` for
the wrong reason (`s25-upgrade.sh`'s own precondition).

### Step 4 — Price it, as root, and read the verdict

```bash
sudo bin/upgrade.sh check --project alpha-dev
sudo bin/upgrade.sh plan  --project alpha-dev --candidate /home/op/agentic-postgres/.generated/alpha-dev/outputs.json
sudo bin/upgrade.sh plan  --project alpha-dev --candidate /home/op/agentic-postgres/.generated/alpha-dev/outputs.json --json
```

The same for `beta-dev`. `plan` prints every leaf that differs, the change
classes they establish, the bump this release **proposes**, the bump those
changes **require**, and whether the first covers the second. It refuses
before any mutation and performs none. The `--json` form carries `bump`,
`requires`, `verdict` and `reasons`, which is what the release proof reads.

| Verdict | Meaning | What you do |
|---|---|---|
| `OK`, `bump` covers `requires` | the release may be deployed as it is | step 6 |
| `BLOCKED`, a reason naming `project_sha256` or `capabilities_sha256` | **your manifest moved as well as the release** | split it: deploy the release with the manifest as it was, then move the manifest and deploy again (D1107, measured on beta 2026-09-11) |
| `BLOCKED`, the proposed bump does not cover what the changes require | the release is mis-priced; its own gate should have refused it | stop; this is a release defect, not an operator's |
| `UNDETERMINED` | the installed document is absent, unreadable or older than this release migrates from | `check` says which; an unreadable one names its owner (exit 3), an absent one says *never deployed here* (exit 4) |

Exit codes are the command's own: 0 the plan may proceed, 4 never deployed
here, 6 blocked or could not be computed.

**How to read a leaf that differs.** `plan`'s human-readable form prints each
leaf as `installed -> candidate`, and since **1.6.1** the three cases are
spelled apart: `(no such key)` means the installed document does not carry the
key at all — a schema addition, the safest class there is — `null` means it
carries it with a JSON null, and anything else is the JSON value. On an earlier
release both of the first two print as Python repr (`'<absent>'` and `None`),
which read as each other: on a real 1.0.0 → 1.6.0 hop two of seven leaves said
*the v18 schema added this key* in a form indistinguishable from *a value went
away* (D1394). The classification is right either way; only the reading was
ambiguous.

**What the plan cannot see, and must be told.** `--also` declares a change class
no pair of rendered documents can establish. `bin/upgrade.sh --help` names all
eight of them since **1.6.1**; before that only the argparse usage line printed
by `bin/upgrade.sh <verb> --help` carried them (D1381), and on releases before
1.6.1 that form exits 2 rather than printing anything, so read them from
`bin/upgrade.py::DECLARABLE` instead. `migration_added` is the one that matters: a rendered document
records no migration count and the checkout's lock describes the checkout, so
**whether the release adds a migration cannot be derived by the plan** (D743)
and is an operator's declaration. Read it yourself from the release table
above or from `git diff <installed source_commit>..HEAD -- migrations/released.lock.json`,
and pass `--also migration_added` so the plan prices what the deploy will do.
A release that adds a migration is the floor once deployed (§0).

**What `minor` looked like, measured**, so you recognise the shape: 1.6.0 on
both projects was `bump minor`, `requires patch`, `verdict OK`, `reasons []`,
**one leaf differing** (`template_version`). 1.5.0 on alpha differed in three
leaves (`template_version`, `inputs.versions_lock_sha256`,
`migrations.release_lock_sha256`) plus `image_digest`; on beta in five, adding
`project_set.count 1 → 2` and its lock — a project migration that had never
been applied, **visible as pending before the deploy rather than after**
(Session 24 Run 7 *Done*).

### Step 5 — Optional: the credential rotations, and the one that has never been performed

An upgrade is a natural window for a rotation because it already recreates
the containers a rotation needs recreated. `docs/api-operations.md` §*Rotating
a credential* is the sequence for the authenticator and the documentation
password (both performed 2026-08-13 and in Session 11's window); a credential
a container mounts needs `project-runtime.sh … down` before the deploy (D253).

**The signing-key rotation has never been performed on this deployment**
(D860). It was offered and declined at four trips, most recently 2026-09-15.
Its sequence is `bin/rotate-signing-key.sh --help`'s seven steps and its
`promote` is irreversible; if you take it, take it as its own sitting with
`docs/api-operations.md` §*The signing key* open, not as a step of an upgrade.

### Step 6 — Deploy, unredirected, at a terminal, alpha first

```bash
sudo ./deploy.sh --host host.yaml --project project.alpha.yaml \
     --capabilities capabilities.yaml --through-session 30
```

Nothing after it: no `> file`, no `| tee`. `sudo`'s pty puts a command whose
streams are not all terminals in the background, the first `docker exec -i`
stops on `SIGTTIN`, and the deploy waits forever (D972; `deploy.sh` now refuses
that shape with exit 2). The terminal is the log.

**The class is any product child that reads the terminal** — measured on
2026-09-18: a child stops only when it reads stdin *and* was handed one, and
neither half alone does anything. **Since ADR 0218 no product child reads the
terminal**: every `docker exec` the product runs is built by one helper that
closes stdin unless it is feeding input, and every shell `docker exec` redirects
from a file. `deploy.sh` keeps its refusal as a belt, not as the repair. So a
redirected deploy is refused rather than hung, and a redirected `doctor`,
`backup` or `db` command simply works.

**How to satisfy that from anywhere but a keyboard at the machine**, which is
how every other step on this page is run:

- **Over SSH, use `ssh -tt`.** It allocates a pty on the REMOTE side, so the
  deploy's three streams are all terminals and D972's refusal does not fire —
  whatever the local end does with the output. A plain `ssh host 'sudo
  ./deploy.sh …'` has no pty and is the shape that hangs. Measured by an
  adopter on 2026-09-16, who worked it out from D972's stated cause because
  this page did not say it.
- **For a transcript, use `script(1)`, not a redirect.** `script -q
  /home/op/deploy-$(date -u +%FT%H%M).log -c 'sudo ./deploy.sh …'` keeps the
  command's streams attached to a pty and records them. `tmux` with its own
  logging works for the same reason. *The terminal is the log* and *record the
  upgrade* (§7) are not in tension; a redirect is what is refused, not a
  recording.

**Where `--through-session`'s number comes from.** It is `CURRENT_SESSION` in
`src/agentic_postgres/__init__.py` of the release you just checked out — not
`VERSION`, and not something you carry over from the last upgrade. Since
**1.6.1** `./deploy.sh --help` prints it. On an earlier release, read it:
```bash
grep -n 'CURRENT_SESSION' src/agentic_postgres/__init__.py
```
The release table's *Session* column carries it for every release listed, and
for a release the table does not list, the file is the only source. **Get it
wrong low and nothing tells you**: `deploy.sh` accepts any number below
`CURRENT_SESSION` silently and exits 0 having deployed less than the release
(D59).

What happens, in the deploy's own step numbers: **0** preflight reads
everything and changes nothing — an absent prerequisite lists every absent one
with its remedy and exits 4 before the render; **1** render from the
manifests; **2** preconditions this session does not create (the edge, the
providers, the secrets — step 2 above); **3** the release installed under
`/opt/agentic-postgres/releases/<commit>` and the launchers refreshed; **4**
root-owned configuration; **5** the data plane started with the deferred
services held back; **6** bootstrap and migrate — *both* sets since 1.5.0,
each into its own ledger table, the ledger move for an older project set
issued as the superuser before either dbmate run (ADR 0206); **6b** the
deferred services started, with the mount digests re-rendered so a container
whose lock or key set changed is **recreated** (ADR 0155, D1152); **6c** the
backup stanza checked, and a failed `check` fails the deploy; **7** observe
and publish the deployed document.

**Deploy twice if the first pass leaves a route `unavailable`** (D326): the
pass that starts a new container cannot observe it, and the redeploy publishes
`ready`. On an upgrade of a running project this is rare; on 2026-09-15 one
pass converged both projects.

Then beta, the same line with `project.beta.yaml`. Alpha declares no project
set and is the control; beta carries the example set. If step 4 said to split
a manifest move, this is the first of the two deploys.

### Step 7 — Read what the deploy left, as root, never its summary line

```bash
sudo bin/migrate.sh --project project.alpha.yaml --runtime status
sudo bin/doctor.sh --project alpha-dev
sudo bin/upgrade.sh verify --project alpha-dev --candidate /home/op/agentic-postgres/.generated/alpha-dev/outputs.json
docker ps --filter "name=apg-alpha-dev-" --format '{{.Names}}\t{{.Status}}'
```

- **The ledger, not the migrator's line** (D941): dbmate prints `Applied` for
  a migration the cluster rolled back, and the deploy's own exit 5 was the
  line to read on 2026-09-04. `status` marks applied migrations `[X]`; the
  doctor's *migrations* check counts both sets against the ledger and is the
  authoritative number. At 1.6.0: alpha **32**, beta **34** (32 released plus
  its own two), `Pending: 0` printed **twice** on beta, once per dbmate
  invocation.
- **The doctor 10 ok.** Its tenth check reads the lock the **running** agent
  plane loaded, not the file (D1286's repair, 2026-09-13); the document's
  `mcp.tool_count` is the count the plane confirmed.
- **`verify` exit 0**: the release installed is the one this checkout would
  render. Measured for both projects by the sweep of 2026-09-15.
- **Container ages** say what ADR 0155 recreated: on 2026-09-15 `auth`, `mcp`
  and `storage` were seconds old on both projects and seven containers were
  not, because the deploy materialised a new secret generation and those three
  mount it.
- **`render-jwks` used to print *the key set CHANGED: every verifier must be
  RECREATED* on every deploy, and from 1.7.0 it does not.** Measured on both
  projects 2026-09-15 with the same `active_kid` and the same
  `public_jwks_sha256` before and after (D1374): the sentence was reporting
  that the **file's bytes** moved, and they always do, because the deploy
  replaces the whole rendered directory before this step so there is never a
  previous copy to compare against (D1427). It now says which of **three**
  things happened — it wrote against a copy that was here, it confirmed one
  byte-identical, or **there was no previous copy and it cannot tell**. Only
  the first carries the recreate sentence. On an ordinary deploy you will see
  the third, and it names the reading that does answer:
  `sudo bin/rotate-signing-key.sh --outputs <outputs.json> acknowledge`.
  On a release **below 1.7.0** the old sentence is what you get, and the note
  above it applies: nothing rotated unless you rotated it.

### Step 8 — The op-owned copies and the kit, again

```bash
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/alpha-dev/outputs.json /home/op/alpha-dev-outputs.json
```

The gate's external mode and every off-host reader take these copies; a
stale copy measures the previous release silently (`CLAUDE.md` §2 records a
pair from 2026-08-23 that did exactly that). Then **re-export the kit** — the
`-pre` one from §2 step 2 describes a deployment that no longer exists — into
the `-post` name, copy it off, and verify it:
```bash
sudo bin/dr-kit.sh export --host host.yaml --capabilities capabilities.yaml \
     --output /home/op/kit-$(date -u +%Y-%m-%d)-post \
     --project project.alpha.yaml --project project.beta.yaml
```
Both kits are kept. `export` refuses a directory that exists, which is why §2
step 2's name carries `-pre` — without the two suffixes an upgrade done in one
sitting cannot follow both steps as written (D1398). **Do not point the gate's
`--kit-dir` at it** (D1282): `REC-KIT-003`'s claim *is* the version gap
between a stored kit and the tree, its proof `pytest.fail`s when no stored
document is older than the tree, and the flag's own help says which kit to
name.

### Step 9 — A project with its own tables: the snapshot, then one more deploy

If the release added a published operation, or your set did, your snapshot is
behind the deployment that now serves it, **by construction** (D1118): the
deploy computed its `api.canonical_openapi_sha256` from the snapshot you had,
and the new snapshot is captured *from* that deployment. The cycle is capture
→ commit → redeploy, and it was performed on both projects on 2026-09-10/11:

```bash
sudo bin/dev-token.sh --project-outputs /etc/agentic-postgres/projects/beta-dev/outputs.json --role docs -- \
     bin/api-contract.sh --update --project project.beta.yaml \
     --project-outputs /etc/agentic-postgres/projects/beta-dev/outputs.json > /home/op/beta-candidate.json
```

`--update` streams the candidate and, with `--project`, prints on stderr the
path it belongs at inside `projects/<slug>/contracts/`. Copy it to the
workstation, review the diff against the committed snapshot, commit, CI, and
transport the commit back for one more deploy.

**The return trip is step 1, then step 3, then step 6 — and step 3 is the one
this page used to leave out** (F-031, measured by an adopter on 2026-09-16).
`deploy.sh --through-session` deploys from a render, and the render sitting on
the host is the one made from the PREVIOUS commit. Step 1's checkout moves
`contracts/postgrest-openapi.canonical.json`, which feeds
`api.canonical_openapi_sha256` — so a second deploy over the old render
republishes the digest it was supposed to replace, and exits 0.

| Step | Second pass |
|---|---|
| 1 transport and check out | **yes** |
| 2 host units and edge | no — the baseline has not moved |
| 3 render the candidate | **yes, and this is the one that is easy to miss** |
| 4 price it | no — it would compare this release against itself |
| 5 rotations | no |
| 6 deploy | **yes** |
| 7 read what it left | **yes** |
| 8 op-owned copies and the kit | no — step 8's copies are taken after the last deploy |
| 9 the snapshot | no — this pass is what step 9 asked for |

Then `apg generate` against the new snapshot in the checkout (§1). Until the
redeploy, `upgrade verify` and the release proof compare against a document
that names the old digest.

---

## 4. Skipped releases

**An upgrade goes from whatever is installed to the release in the checkout,
in one deploy.** Intermediate releases are not deployed one by one, and the
plan is a comparison of two rendered documents whatever the distance between
them.

Measured: both projects went from **1.2.0 (session 21) to 1.5.0 (session 24)
in one deploy each** on 2026-09-13, with the three intermediate candidates
priced first from worktrees at their commits — all `minor` — so the operator
could read what each hop would have carried. Alpha converged on the first
attempt after a repair; beta refused at step 6 having applied nothing, because
1.5.0's migration 0032 sorted below the example set's already-applied
`20260914120001` (D1288) — the reason ADR 0206 gave a project's set its own
ordering space, in the same session, before beta could be deployed at all.

What a longer hop meets, from the release table:

- **Every pending migration applies in order in step 6**, each in its own
  transaction; a migration that PostgreSQL rolls back stops the deploy at
  step 6 with exit 5 and the project keeps serving its old release (D940,
  2026-09-04: a CHECK over historical rows).
- **The deployed document is migrated by a chain of single-step migrators**
  (v1 → v18); `upgrade check` reports `undetermined` when the installed
  document is older than this release migrates from. Every hop performed on
  this host was from v13 or later. **A hop from a release older than 0.2.0 has
  not been measured** here or anywhere on record.
- **A project set frozen before 1.5.0** has its applied rows in the shared
  `schema_migrations`; the first deploy at 1.5.0 or later moves them to
  `app_private.project_schema_migrations` as the superuser before either
  dbmate invocation, re-applying nothing (ADR 0206, measured on beta
  2026-09-13).
- **Units and the edge**: a hop across 0.3.0, 0.6.0 or 1.0.0 needs step 2.
- **The kit**: a kit exported before 1.0.0 (outputs v16) cannot be verified by
  this release — `KIT_FIRST_OUTPUTS_VERSION` is 16 — so §2 step 2 is not
  optional on a long hop.
- **Verifiers**: a hop across 0.4.0 or 1.2.0 recreates every verifier or the
  `auth`/`mcp` pair; outstanding tokens are refused at their next request.

---

## 5. A `major`, which has never happened here

Nothing on this page about a `major` is measured, and this section says what
the product's own rules make of one rather than describing a sequence.

ADR 0162 defines it as **the operator must act before the upgrade**, and
`upgrade plan` refuses with `BLOCKED` and a `reasons` list naming what:
`operator_manifest_invalidated` (edit the manifest to the new schema, render
as op, plan again — and this is *not* the D1107 split, which is about a
manifest that moved *with* an otherwise-minor release);
`api_operation_removed` or `_changed` (callers of the published surface break;
a generated client's `init()` will answer `stale_contract` naming both
digests, which is the client refusing to run against a surface it was not
generated from, ADR 0204); a secret that gains a **required** member (put the
value at the provider by hand, `materialize-secrets.sh --session 30`, and
plan again — no command in this repository writes a provider value, D249);
`document_schema_needs_operator_input` (the deployed document's migrator
needs a value only you hold; the plan says which).

The order that follows from the rules: read `reasons`; act on the input each
names; render the candidate again as op; `plan` again until it is `OK`; then
§3 from step 6. Whether `apg upgrade` will ever *perform* the operator's half
rather than refuse and hand over a runbook was left open by ADR 0162 and has
not been decided since.

---

## 6. When it refuses, and when it fails halfway

| What you see | What it is | What to do |
|---|---|---|
| `check` → `undetermined` | no installed rendered document, or one this user cannot read | exit 3 names the owner and the `chown`; exit 4 means the project was never deployed here. Not *no changes* |
| `plan` → `BLOCKED`, `project_sha256` or `capabilities_sha256` moved | the manifest and the release moved together | split into two deploys (D1107); the refusal names the remedy |
| `plan` → `BLOCKED`, bump does not cover the changes | a mis-priced release | stop. The release's gate should have refused it; it is not yours to widen |
| the deploy exits 4 at step 0 | preflight: an absent prerequisite, every one listed with a remedy | run the remedies; nothing was written |
| the deploy exits 4 naming the edge's `metrics` entry point | the edge serves an older static configuration (D811) | `sudo bin/edge.sh --host host.yaml restart`, then deploy again |
| the deploy exits 5 at step 6, dbmate says `Applied`, stderr says `Error:` | PostgreSQL rolled the migration back and the ledger has no row (D941, D940) | the project still serves its old release. **Fix forward** — a released migration is never amended (D912); the remedy is a new release with a new migration |
| the deploy exits 5 at step 6, *out of order with already applied migrations* | a release migration sorts below an applied project migration (D1288) | since 1.5.0 the two sets are in separate directories and tables and this cannot occur for a set the deploy has moved; on a release before 1.5.0 there is no remedy but 1.5.0 |
| the deploy exits 5 at step 7 refusing its own document | the plane did not confirm what the file says (D1286 once, 2026-09-13, repaired the same day) | read the doctor's *capability drift* line; the plane is up, the document was not written; each attempt materialised a generation, harmlessly |
| the deploy prints nothing and never returns | process state `T+`: a redirect or pipe gave a child a terminal (D972); or a backgrounded `sudo` whose timestamp expired (D1376) | `kill -CONT` the stopped parents, or `kill %1`; `sudo -v` in the foreground; run it again unredirected |
| `TimeoutError` reading Infisical | a transient in the provider (D976; the client retries idempotent calls three times, and a reconverge still failed four times in five on 2026-09-05) | run the deploy again |
| `render-jwks` says *the key set CHANGED* | **below 1.7.0**: the file's bytes moved with the generation, which they always do (D1374). **From 1.7.0**: this file's bytes moved against a copy that was actually here | below 1.7.0, nothing rotated unless you rotated it — compare `jwt.active_kid`. From 1.7.0 the sentence means what it says |
| `render-jwks` says *cannot be told from here* | from 1.7.0, and it is the normal case: no previous copy at that path, because the deploy replaced the rendered directory first | neither evidence of a rotation nor against one; `sudo bin/rotate-signing-key.sh --outputs <outputs.json> acknowledge` |
| the doctor reports a `PROBLEM` you do not believe | read `--verbose` and the **route** the probe took before the subject it names (D673, D680, D682) | three of Session 11's defects were probes that could not have succeeded |
| `.generated/<key>` root-owned after the day | a root render, a `sudo pytest` or a real root login (D1110); a `sudo ./deploy.sh` hands it back | `sudo chown -R op:op .generated` |
| `scp` of the bundle refused, `Permission denied` on `/tmp/apg-…` | a file of that name owned by another account (D504); or `/tmp` without its sticky bit (D1301, 2026-09-13) | a per-commit name never collides; `chmod 1777 /tmp` was the repair for the second |

**What rollback means, and does not** (ADR 0162 §3). *Configuration rollback*
— re-render from the previous manifests and redeploy — is reversible.
*Image rollback* — `versions.env` to the prior digests and redeploy — is
reversible **only while no migration has been applied since**. *Database* is
fix-forward: a new migration that corrects the last one, never a `down`.
**Deploying an older checkout over a newer deployment has never been
performed on this host**; `deploy.sh` would accept it (`--through-session`
refuses only a number *above* the checkout's own `CURRENT_SESSION`), the
release directories under `/opt/agentic-postgres/releases/` are immutable and
kept, and previous secret generations are left in place (`materialize-secrets.sh
--help`: *they are what a rollback restores*) — but what an older release does
when it reads a newer deployed document is not something this page can tell
you, and it does not describe the operation as safe.

**A failed deploy leaves the previous release serving** in every case measured:
the release directory is installed beside the old one, the deployed document is
the previous deploy's until step 7 writes it (the code's own comment), and
step 6 applies nothing when it refuses. What a failed deploy does leave behind
is a fresh secret generation and, sometimes, a recreated container on the new
image; the doctor says whether the project is well, and `upgrade check` says
which release the document records.

---

## 7. After the upgrade

- Both deployed documents record `template_version 1.6.0`,
  `deployed_through_session 25` and the `source_commit` you transported.
- The kit is re-exported and off the host (§3 step 8).
- The op-owned copies are current (§3 step 8).
- If a snapshot moved, it is captured, committed and redeployed (§3 step 9),
  and the generated client regenerated in the checkout (§1).
- `docs/operator-guide.md` §10 has the gates that turn a deployed release into
  an evidence document, which is how a release is closed here; an upgrade
  without a sweep is deployed, not measured.
