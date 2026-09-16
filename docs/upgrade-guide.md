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

A row's *what an upgrade meets* is what the trip that deployed it recorded in
its plan's §5 *Done* paragraph. **A project manifest below the newest schema
still deploys**: alpha's is schema 4 and was deployed at 1.6.0 on 2026-09-15
(the control the plans keep); a manifest below 5 renders as a project with no
set of its own. Moving a manifest's schema is a separate operation from an
upgrade, and §3 step 4 says why.

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
- **`generate --check`** exits 5 after **every** bump, because the client's
  `templateVersion` is derived from the release (D1238). Regenerate and commit
  it in the same change: `bin/apg.sh generate --project project.yaml`.
- **`--render-only`** is the whole of what a checkout runs; the gate's step 2
  and `apg dev up` both refuse a project this checkout has not rendered.
- **`dev reset`** rebuilds the local cluster from the new render, applying
  both sets as the migration user — a migration of yours that the new release
  refuses fails here in ten seconds rather than in step 6 of a deploy.

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

1. **Read what is installed.** As root, per project:
   ```bash
   sudo bin/upgrade.sh check --project alpha-dev
   sudo bin/doctor.sh --project alpha-dev
   sudo bin/fleet.sh
   ```
   `check` reports the installed release and whether a comparison can be
   made; `undetermined` blocks and is not *no changes*. The doctor reads
   **10 ok** on a well deployment (2026-09-15, both projects). Anything else
   is repaired before the upgrade, because a failed upgrade over a sick
   project leaves you unable to say which caused what.
2. **Export the kit and take it off the host.** The kit is what you hold if
   the upgrade takes the host with it (ADR 0189, `docs/node-loss-runbook.md`
   §0). As root:
   ```bash
   sudo bin/dr-kit.sh export --host host.yaml --capabilities capabilities.yaml \
        --output /home/op/kit-$(date -u +%Y-%m-%d) \
        --project project.alpha.yaml --project project.beta.yaml
   bin/dr-kit.sh verify /home/op/kit-<date>
   ```
   `export` refuses a directory that exists (the day is in the name so two
   exports on one day collide on purpose), hands the kit to the operator user,
   and `verify` takes no `--project` (D1316). Copy it off to an ext4 filesystem
   — the `0700`/`0600` modes do not survive a Windows drive — and `verify` it
   there from a checkout. Measured 2026-09-15 (`s25-kit.sh`, kit-2026-09-15,
   verified on the host and again in `~/dr-kits/`).
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
   3 refuses a dirty checkout (`assert_clean`); a third manifest inside it is
   untracked and makes every deploy refuse (D971), so it lives at
   `/home/op/<name>.yaml`. And `.generated/<key>` can be root-owned after a
   root `--render-only`, a `sudo pytest` or a deploy from a real root login
   (D1110): as op, `stat -c %U .generated/*`, and if any is not `op`,
   `sudo chown -R op:op .generated` first. A render into a root-owned
   directory dies on a permission error rather than a sentence (D1151;
   `render_project` names the owner and the remedy since 1.3.0).
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
Run 7). `uv pip sync` reaches PyPI; five earlier trips paid for skipping the
sync (D384, D297).

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

**Two things the plan cannot see, and both are printed by the parser rather
than by `--help`.** `bin/upgrade.sh <verb> --help` prints an argparse usage
line carrying `--also {migration_added, api_operation_added,
api_operation_removed, api_operation_changed, secret_optional_added,
document_schema_migratable, document_schema_needs_operator_input,
operator_manifest_invalidated}`, and `bin/upgrade.sh --help` does not mention
it (D1381). `migration_added` is the one that matters: a rendered document
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
     --capabilities capabilities.yaml --through-session 25
```

Nothing after it: no `> file`, no `| tee`. `sudo`'s pty puts a command whose
streams are not all terminals in the background, the first `docker exec -i`
stops on `SIGTTIN`, and the deploy waits forever (D972; `deploy.sh` now refuses
that shape with exit 2). The terminal is the log.

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
- **`render-jwks` prints *the key set CHANGED: every verifier must be
  RECREATED*** on every deploy that materialises a new generation, and it is
  reporting that the **file's bytes** moved, not that a key did (D1374,
  measured on both projects 2026-09-15: same `active_kid`, same
  `public_jwks_sha256` before and after). Nothing rotated unless you rotated
  it. The advice is conservative and every verifier was recreated anyway;
  read `jwt.active_kid` in the deployed document if you need to be sure.

### Step 8 — The op-owned copies and the kit, again

```bash
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/alpha-dev/outputs.json /home/op/alpha-dev-outputs.json
```

The gate's external mode and every off-host reader take these copies; a
stale copy measures the previous release silently (`CLAUDE.md` §2 records a
pair from 2026-08-23 that did exactly that). Then **re-export the kit** (§2
step 2) — the one you exported before the upgrade describes a deployment that
no longer exists — copy it off, and verify it. **Do not point the gate's
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
transport the commit back (step 1) for one more deploy. Then `apg generate`
against the new snapshot in the checkout (§1). Until the redeploy, `upgrade
verify` and the release proof compare against a document that names the old
digest.

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
value at the provider by hand, `materialize-secrets.sh --session 25`, and
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
| `render-jwks` says *the key set CHANGED* | the file's bytes moved with the generation (D1374) | nothing rotated; compare `jwt.active_kid` if in doubt |
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
