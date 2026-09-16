# The on-ramp: converting a fork whose domain is inside the release's own files

**Which release this is.** This page describes the release in this checkout's
`VERSION`. Step 5 of the conversion needs `bin/migrate.sh freeze-lock --project
--follows`, which arrives at **1.7.0**: if `VERSION` is below that, this
checkout can do everything here except step 5, and step 5 is the one that was
missing. Check it before you start.

```bash
cat VERSION
bin/migrate.sh --help | grep -- --follows     # present from 1.7.0
```

**Read this only if `projects/<slug>/` did not exist when you forked.** If your
domain already lives in `projects/<slug>/`, this page is not about you and
[the upgrade guide](upgrade-guide.md) §1 is. If you are not sure, run:

```bash
git log --oneline -1 -- projects/        # nothing at all -> this page is yours
```

The tenant extension point arrived at **1.1.0** (`migrations.set`, project
manifest schema 5, ADR 0198) and was completed at **1.2.0** (`mcp.capabilities`,
schema 6, ADR 0201). Tag `1.0.0` carries no `projects/` at all — measured, over
802 tracked paths. If you forked at or before it, the only thing the release
offered was to put your domain **inside the release's own files**: your
migrations in `migrations/templates/`, your operations in
`contracts/postgrest-api-surface.yaml`, your rows in `migrations/manifest.json`
and `migrations/released.lock.json`.

**That fork still works and this page does not deprecate it.** A project
manifest at `schema_version: 4` declares no set of its own, so its migrations
stay in the release's directory and ADR 0206's split never engages. One adopter
upgraded such a fork from 1.0.0 to 1.6.0 on 2026-09-16 and the deployment
doctors 10 ok. What you get by converting is that the release stops treating
your SQL as its own: your set is locked separately, ordered separately, applied
from its own directory into its own ledger table, and a release that adds a
migration stops conflicting with yours.

---

## 0. What this page is, and what it is not

**It is measured, not designed.** Every claim below was taken on **rig 28a**, a
synthesized pre-ADR-0198 fork rebuilt from tag `1.0.0` in a throwaway clone:
a tenant table in `migrations/templates/`, rows in the release's manifest and
lock, a relation in the shared reviewed surface, merged to `1.6.2`, resolved,
and re-homed. The decisions it produced are **ADR 0210**, **ADR 0211** and
**ADR 0212**, and each names what it measured.

**What is NOT proved here is step 7.** The ledger move runs against a cluster
that carries your history, and this project has no such cluster: D940's rule is
that a migration over a table with history must be proved against a cluster with
history, and the only one is yours. Every step a checkout can prove is proved;
that one is stated with its statement and its control, and you perform it on a
copy first.

---

## 1. Before anything: does your set convert at all?

Two questions, in this order, and the second is the one that stops forks.

**Is every one of your migrations already applied somewhere?** If they are not —
a fork that never deployed — you do not need this page. Re-stamp your versions
above the release's newest and freeze normally; nothing here applies.

**Would your SQL pass the project-set lint?** A project's set is refused before
it renders if it names `app_private`, creates or alters a role, schema or
extension, sets any role but `SET LOCAL ROLE {{object_owner}}`, drops an object
the release publishes, creates a table in `app` without `FORCE ROW LEVEL
SECURITY`, or has a `down` block that does not raise `AP900`. It is also refused
if it reads a placeholder outside the six request roles and `database.name` —
and `app_runtime` is the one adopters hit, because the release's own `0003`
grants to it.

The lint is the boundary the conversion has to bring you inside, and §3 says
which of its refusals you may satisfy by editing an applied migration and which
you may not.

---

## 2. The merge, and its four classes

Merging the release into a fork that amended the release's own files produces
conflicts in proportion to **how many of those files you amended**. The one
recorded upgrade amended nine and got nine. Rig 28a amended four and got two.
There is no fixed number and this page does not invent one.

| Class | Files | What to do |
|---|---|---|
| **Generated, carrying digests** | `migrations/released.lock.json`, `contracts/postgrest-openapi.canonical.json`, `projects/<slug>/clients/*/generated.json` | **Never resolve by hand.** Take the release's side whole, then regenerate: `bin/migrate.sh freeze-lock` for the lock, a captured snapshot for the OpenAPI document (it refuses a hand edit — D1118), `bin/apg.sh generate` for a client. |
| **Append-structured, release-owned** | `migrations/manifest.json` | Take the release's side, re-apply your rows on top, sort by version. |
| **Reviewed contracts** | `contracts/postgrest-api-surface.yaml` | **Diff it against the release's own copy at the tag after every merge, whether or not `git` reported a conflict.** |
| **Template bytes** | `migrations/templates/*.sql` | These do not conflict. Check for a shared **version**, not a shared number. |

**The third row is the one that will bite you, and it does so silently.** On rig
28a the reviewed surface did **not** conflict: the release's `1.1.0` addition
landed at a different point in the file, `git` auto-merged, and the fork's own
relation survived inside the release's reviewed contract with no marker and no
review. ADR 0050 exists because a contract produced from the thing it constrains
cannot refuse it; a contract that acquires a relation by three-way merge is that
failure by another route. After every merge:

```bash
git diff <the release tag you merged> -- contracts/postgrest-api-surface.yaml
```

Anything in that diff is yours, and it is in the release's reviewed contract
until you move it to your own.

**The fourth row is measured too.** `0031-create-task.sql` (the release's, from
1.1.0) and a fork's `0031-tenant-invoices.sql` coexist in one directory and
`git` never conflicts on them — different names, nothing to merge. What is
actually unique across sets is the **version stamp**:
`rendering.assert_migration_order` refuses two migrations sharing one, because
`app_private.migration_ledger` keys on the version alone and is written `ON
CONFLICT (version) DO NOTHING`, so a shared version would apply twice and be
recorded once. Renumbering the *files* fixes nothing and changes the bytes of
applied migrations to do it.

---

## 3. What you may edit, and what becomes a new migration

**Moving a migration is not amending it.** D912 forbids changing what an applied
migration does; moving the file and moving the manifest entry that declares it
changes neither the bytes nor the version, and the ledger keys on the version.
Measured: `git mv` reports *1 file changed, 0 insertions, 0 deletions*.

But the lint may refuse your set, and satisfying it means editing bytes that
have already run. **The rule is decided by what the change would do to a
cluster, not by how large it is** (ADR 0212 §2).

| What the lint refuses | What you do |
|---|---|
| a `{{app_runtime}}` grant | **Delete the line, in place.** It grants nothing: `0006-app-runtime-least-privilege.sql` issues `REVOKE ALL ON SCHEMA app FROM app_runtime`, and measured on PostgreSQL 18.4 with a control, `has_table_privilege` answers `true` while the `SELECT` is denied — for a table created *after* the revoke as well as before. |
| a `down` block that does not raise `AP900` | **Replace it, in place.** Those bytes have not run and cannot have: `dbmate up` applies the `migrate:up` section only, and this release's own evidence for that is that every one of its 32 released migrations carries a `down` that raises `AP900` and all 32 apply. |
| a table in `app` without `FORCE ROW LEVEL SECURITY` | **A NEW migration**, stamped above your set's newest. This changes the cluster. |
| a `DROP` of an object the release publishes | **A NEW migration**, and reconsider: a project adds to the published surface and never removes from it. |
| a `SET ROLE` other than the owner preamble | **A NEW migration** for whatever the old one did, and the preamble corrected only if the correction cannot change what ran. |
| anything naming `app_private` | **Your set does not convert.** This is the platform's own state and no rewrite of it is a tenant migration. |

**If you take an in-place edit, record it.** In the manifest entry's
`description`, beside the version: that the template's bytes were changed after
that version was applied, which line was removed, and why it could not alter the
cluster. This is not ceremony. `app_private.migration_ledger` keeps the digest
of the bytes that actually ran — `ON CONFLICT (version) DO NOTHING`, so the row
is never rewritten — and after the conversion no checkout contains those bytes.
The ledger is right; it just cannot say why it disagrees with your tree, so your
manifest does.

---

## 4. The conversion, seven steps

Take a copy first. Everything through step 6 is a checkout and is undone by
`git checkout`; step 7 writes to a cluster.

```bash
# 1. Merge the release. Resolve by §2's four classes.
git fetch origin --tags
git merge <the release tag you are taking>

# 2. Re-home each template. BYTES UNCHANGED.
mkdir -p projects/<slug>/migrations/templates
git mv migrations/templates/0031-your-domain.sql \
       projects/<slug>/migrations/templates/0001-your-domain.sql

# 3. Move each manifest entry into projects/<slug>/migrations/manifest.json,
#    VERSION STAMP PRESERVED, and delete it from migrations/manifest.json.
#    The project manifest declares only the placeholders your set uses, and
#    they come from the six request roles and database.name.

# 4. Re-freeze the release's own lock, now without your entries.
bin/migrate.sh freeze-lock

# 5. Freeze YOUR lock, declaring the release you were actually frozen against.
bin/migrate.sh --project project.yaml freeze-lock --follows 20260904120030

# 6. Point the project manifest at the set, and raise its schema version.
#    migrations:
#      set: projects/<slug>
#    schema_version: 5   (or 6, if you also declare mcp.capabilities)

# 7. Deploy. The ledger move runs as part of it.
sudo ./deploy.sh --project project.yaml --capabilities capabilities.yaml
```

### Step 5 is the only thing the product had to grow

Before **1.7.0**, `freeze-lock --project` computed `follows_release_version` from
**this checkout's** newest release version. For a set frozen against an earlier
release that value is wrong by construction — the freeze runs on the later
checkout — so the freeze refused, and re-freezing computed the same wrong value
and refused again. That was the whole of what made this conversion impossible,
and it was one line (ADR 0210, D1436).

`--follows` declares it. The value must name a release migration version this
release's own manifest declares — the manifest is append-only, so every version
this product has shipped is in your checkout. Read it out of the manifest of the
release you forked from, or out of your set's existing lock if it has one. The
check refuses a typo and a fabricated stamp; it **cannot** prove your set was
frozen against that release, so the lock records that the value was `declared`
rather than `computed`, in `follows_release_version_source`. A reader auditing
your deployment can then tell the two apart, which is the point.

Declaring changes no refusal and no ordering. Since ADR 0206 the record orders
nothing across sets, so a wrong declaration produces a wrong record and no wrong
SQL.

### Step 7 is the step this project cannot prove for you

ADR 0206 gave a project's set its own ledger table and, with it, a one-time move
for clusters migrated before the split. It is driven by the **rendered
manifest** and matches **by version**, so a re-homed migration that kept its
stamp is relocated by the next deploy, for free:

```sql
BEGIN;
INSERT INTO app_private.project_schema_migrations (version)
  SELECT version FROM app_private.schema_migrations WHERE version IN ('20260905120031')
  ON CONFLICT (version) DO NOTHING;
DELETE FROM app_private.schema_migrations WHERE version IN ('20260905120031');
COMMIT;
```

That statement was measured on rig 28a with a control: the release's own
`20260912120031` does not appear in it. What was **not** measured is it running
against a real ledger with your rows in it. Before you deploy:

```bash
# on a COPY of your cluster, or a restore from your own DR kit
psql -c "SELECT version FROM app_private.schema_migrations ORDER BY version"
```

Every version you re-homed must be in that list, spelled exactly as your
manifest spells it. If one is not, the move will relocate nothing and the deploy
will apply your SQL against objects that already exist. That is the failure mode
to look for, and it is why this step gets a copy first.

After the deploy:

```bash
sudo apg-diag catalog <key> migration-ledger     # your versions, in the ledger
sudo bin/doctor.sh --project <key>
```

---

## 4a. The gate, which is what F-022 is about

**Your fork can deploy and cannot pass this release's gate, and that is not a
second problem.** It was measured here rather than taken from the finding: the
release's own `contract and p0` sweep, run against a fork rebuilt from tag
`1.0.0` and merged to the current release, gives **52 failed, 5,692 passed, 3
skipped, 49 errors**. The adopter who reported it saw 47 failures and 49 errors
on their own fork. Close enough to be the same thing; the useful part is not the
number.

The control is the same command on an unforked checkout of the same release, in
the same session: **5,800 passed, 3 skipped, 0 failed, 0 errors**. So the 52 and
the 49 are the fork, not the sweep.

**The failures are one family.** `test_api_surface_contract`,
`test_api_contract_command`, `test_client_ir`, `test_generate_command`,
`test_generated_client_runtime`, `test_scope_registry`, `test_scope_vocabulary`,
`test_studio_*` — everything that reads the release's reviewed surface as the
*release's own*. **`test_migrations` passes.** The gate does not object to your
migrations sitting in the release's directory. It objects to your relation
sitting in `contracts/postgrest-api-surface.yaml`, because every proof that
reads that file reads it as a statement of what the release publishes, and it
now names an object the release does not.

So the answer to *what do I do about the gate* is this page. Converting moves
your relation into `projects/<slug>/contracts/`, where the release's proofs do
not read it and your own snapshot does — which is the layout ADR 0198 describes
and the one the gate assumes.

**Until then, and if you do not convert:** a green gate is not a deploy
precondition and never has been. Your deployment converges, doctors and serves.
What you cannot have is §7's measurement — *an upgrade without a sweep is
deployed, not measured* — so read the doctor and `upgrade verify` on the host,
and treat the gate's verdict on your tree as unavailable rather than as a
failure. The families outside the reviewed-surface one were not analysed, and
this page does not pretend they were.

---

## 5. When it does not convert

**Say so and stay.** A set that needs `app_private`, or that cannot reach a
passing lint without a change that would alter the cluster it already ran on, is
not a project set and no amount of moving files makes it one. The supported
position is the one you are already in: a `schema_version: 4` manifest, your
domain in the release's files, a merge per release resolved by §2's classes, and
the checks in the upgrade guide's §1 that refuse you — which are correct to.

This page exists so that the choice is a decision rather than a dead end. Two
sessions called the conversion undecided and deferred it; what was actually
missing was one flag and a measurement, and what remains genuinely undecided is
nothing.

---

## 6. Where each claim on this page was measured

| Claim | Where |
|---|---|
| `1.0.0` carries no `projects/` | `git ls-tree -r --name-only 1.0.0 -- projects/`, empty over 802 paths (D1419) |
| Four amended files produce two conflicts; the reviewed surface auto-merges | rig 28a (D1434) |
| The `0031` collision is on the version, not the filename | rig 28a (D1439) |
| Re-homing moves no bytes and no version | `git mv`, 0 insertions and 0 deletions (ADR 0212) |
| The freeze refuses, and passes on the true record | rig 28a (D1436), ADR 0210 |
| The ledger move relocates a re-homed version, with a control | rig 28a (D1435), ADR 0206 |
| The `app_runtime` grant reaches nothing, including for a table created after the revoke | PostgreSQL 18.4, pinned image, with a control (D1058, D1411, D1437), ADR 0211 |
| A byte change after the fact is invisible to the ledger | `ON CONFLICT (version) DO NOTHING`, and no reader compares (D1438) |
