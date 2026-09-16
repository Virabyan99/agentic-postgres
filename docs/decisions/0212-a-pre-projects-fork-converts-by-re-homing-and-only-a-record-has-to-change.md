# 0212 — A fork made before `projects/<slug>/` converts by re-homing without amending, and the merge has four classes with four rules

- **Status:** Accepted
- **Date:** 2026-09-16
- **Session:** 28, Run 2 (D1419, D1434, D1435, D1438, D1439)
- **Affects:** no requirement id moves and no product behaviour changes in this
  ADR. `TEN-SET-001` and `TEN-SET-002` are the claims whose subject it touches.
- **Related:** ADR 0198 (`projects/<slug>/` is the tenant extension point), ADR
  0206 (separate directories, separate ledger tables, and the one-time ledger
  move this ADR finds a second use for), ADR 0210 (the declared record, which
  is the one thing a conversion needs the product to add), ADR 0211 (the lint
  refusal a 1.0.0-era fork meets, and what removing the line costs), D912
  (never amend an applied migration), D1096 (the ledger is the only record of
  which bytes ran), D1118 (a snapshot is captured from a deployment and refuses
  a hand edit), D1288 (the refusal ADR 0206 repaired), `docs/upgrade-guide.md`
  §1.0.

## Context

**Two sessions have called this a product decision and deferred it, and both
gave the same reason: there is no fork to try it on.** There is one, and it is
`git`'s. Tag `1.0.0` carries no `projects/` at all — `git ls-tree -r
--name-only 1.0.0 -- projects/` returns nothing over 802 tracked paths — so the
fork a 1.0.0-era adopter was obliged to build is reproducible from the tag.

**Rig 28a** is that reproduction: a throwaway clone at `1.0.0` given a tenant
table in `migrations/templates/0031-tenant-invoices.sql`, a row in
`migrations/manifest.json`, a row in `migrations/released.lock.json` (written by
the release's own `freeze-lock`), and a relation in
`contracts/postgrest-api-surface.yaml` — the four places §1.0 of the upgrade
guide says such a fork had to write. Its tenant migration copies `0003`
faithfully, including the `{{app_runtime}}` grant, because that is what the
adopter did. It was then merged to `1.6.2`, resolved, and re-homed into
`projects/tenant/`. Everything below was measured on it.

### What the merge actually produces

```
git merge 1.6.2
  CONFLICT (content): migrations/manifest.json
  CONFLICT (content): migrations/released.lock.json
  2 conflicted files, from 4 amended files
```

**The recorded upgrade's nine conflicts are a property of that fork, not of the
release** (D1434). Nine files amended, nine conflicts. The number is not a
constant and a rule stated as *nine files* would be a rule about one adopter.

**`contracts/postgrest-api-surface.yaml` did not conflict**, and that is the
finding worth more than the count. The release's `1.1.0` addition landed at a
different point in the file, `git` auto-merged, and the fork's own relation
survived inside the release's reviewed contract with no marker, no conflict and
no review. ADR 0050 exists because *a contract produced from the thing it
constrains cannot refuse it*; a contract that acquires a relation by a
three-way merge is the same failure arriving by a different route.

**The template files never conflict, and the collision is real anyway** (D1439).
`0031-create-task.sql` and `0031-tenant-invoices.sql` coexist in one directory —
different names, so `git` has nothing to merge. What is actually unique across
sets is the **version**, and `rendering.assert_migration_order` refuses only a
shared version, because `app_private.migration_ledger` keys on the version alone
and is written `ON CONFLICT (version) DO NOTHING`. The fork's `20260905120031`
and the release's `20260912120031` are different versions in the same numbered
slot, and nothing anywhere refuses that.

Resolution, the way the one recorded upgrade did it — the release's side in
every file the release owns, the fork's rows re-applied, the lock re-frozen —
produced a set that `verify-lock` accepts: *"the released lock agrees with the
manifest and templates"*, exit 0.

### What the conversion actually costs

The re-homing itself moves bytes nowhere:

```
git mv migrations/templates/0031-tenant-invoices.sql \
       projects/tenant/migrations/templates/0001-tenant-invoices.sql
  1 file changed, 0 insertions(+), 0 deletions(-)
```

The manifest entry moves with the **version stamp preserved**, which is the
whole hinge. Three measurements follow from it.

**1. `freeze-lock --project` refuses, and only because it computes the record.**
The floor is `20260912120032`, the merged checkout's newest; the set's version is
`20260905120031`; exit 5, with the message that says there is no supported way
forward. Given the true record the set passes:
`build_lock(..., follows_release_version="20260904120030")` then `verify_lock` →
**PASSED** (D1436). ADR 0210 is that flag.

**2. ADR 0206's ledger move already performs the conversion's cluster half, and
nobody knew** (D1435). `project_ledger_move_statement` is driven by the rendered
manifest and matches **by version**. Handed a render in which the re-homed
migration is declared `set: project`, it emits exactly:

```sql
BEGIN;
INSERT INTO app_private.project_schema_migrations (version)
  SELECT version FROM app_private.schema_migrations WHERE version IN ('20260905120031')
  ON CONFLICT (version) DO NOTHING;
DELETE FROM app_private.schema_migrations WHERE version IN ('20260905120031');
COMMIT;
```

The control — the release's own `20260912120031` — does not appear. The
statement was written as a one-time repair for D1288 and is re-runnable by
construction; a re-homed migration that keeps its stamp is moved by the next
deploy, for free, with no new code. **This is why the conversion exists.**

**3. The lint refuses the fork's template, and satisfying it changes applied
bytes** (ADR 0211). Measured on the rig: removing the `{{app_runtime}}` grant
moves `template_sha256` and `canonical_render_sha256`, and the lint then passes.
The removal changes nothing on a cluster — the grant is unreachable through a
revoked schema, measured on 18.4 with a control in ADR 0211 — but it changes
the bytes recorded for a version that has already run.

**And the ledger will not notice** (D1438). `ledger_insert_statement` writes `ON
CONFLICT (version) DO NOTHING`, so the row for `20260905120031` keeps the
`rendered_sha256` of the bytes that actually ran. That is correct as history and
unverifiable as a record: nothing on a deployed host compares a ledger row
against the tree, and after the conversion no checkout contains those bytes.

## Decision

### 1. A conversion exists, and it is this one

For a fork whose domain is in the release's own files:

1. Merge the release. Resolve by §3's four classes.
2. `git mv` each tenant template into `projects/<slug>/migrations/templates/`.
   **Bytes unchanged.**
3. Move each manifest entry into `projects/<slug>/migrations/manifest.json`,
   **version stamp preserved**, and remove it from the release's manifest.
4. `bin/migrate.sh freeze-lock` — the release's own lock, now without those
   entries.
5. `bin/migrate.sh freeze-lock --project <manifest> --follows <the release
   version the set was actually frozen against>` (ADR 0210).
6. Set `migrations.set` in the project manifest and raise its `schema_version`
   to at least 5.
7. Deploy. ADR 0206's ledger move relocates each applied version by stamp.

**Step 2 is not an amendment and D912 is not engaged by it.** D912 forbids
changing what an applied migration *does*; moving a file and moving the entry
that declares it changes neither the bytes nor the version, and the ledger keys
on the version.

### 2. What the lint may force, and where the conversion stops

A 1.0.0-era set will usually not pass `lint_project_set`. The rule is decided by
**what the change would do to a cluster**, not by how large it is:

- **A change to bytes that cannot alter the cluster may be made in place**, and
  the conversion records that it was made. Two classes qualify and no others are
  granted by this ADR: removing a `{{app_runtime}}` grant, which ADR 0211
  measures to grant nothing reachable; and replacing a `migrate:down` section
  with the `AP900` refusal, which `dbmate up` never executes.
- **Anything that would alter the cluster is a NEW migration in the re-homed
  set**, stamped above the set's own newest — never an edit to the applied one.
  A missing `FORCE ROW LEVEL SECURITY`, a `DROP` the release publishes, a `SET
  ROLE` other than the owner preamble: each is a fix-forward migration.
- **A set that cannot reach a passing lint by those two routes does not
  convert.** It stays where it is. `docs/upgrade-guide.md` §1.0's position — a
  schema-4 manifest declares no set, its migrations stay in the release's
  directory, and the deployment works — remains available and supported, and
  this ADR does not deprecate it.

### 3. The merge has four classes and four rules

| Class | Files | Rule |
|---|---|---|
| **Generated, carrying digests** | `migrations/released.lock.json`, `contracts/postgrest-openapi.canonical.json`, `projects/<slug>/clients/*/generated.json` | **Never hand-resolved.** Take the release's side whole, then regenerate: `freeze-lock` for a lock, a captured snapshot for a surface (D1118 — it refuses a hand edit), `apg generate` for a client. |
| **Append-structured, release-owned** | `migrations/manifest.json` | Take the release's side, re-apply the fork's rows, sort by version. |
| **Reviewed contracts** | `contracts/postgrest-api-surface.yaml` | **Diff against the release's own copy at the tag after every merge, whether or not `git` reported a conflict.** Measured: it auto-merges, and a tenant relation survives inside the release's reviewed contract unreviewed. |
| **Template bytes** | `migrations/templates/*.sql` | These do not conflict. The check is for a **shared version**, not a shared number: two `0031-` files are legal and two `20260905120031`s are not. |

### 4. What is recorded, by whom, and where

When the conversion takes §2's in-place route, the operator records in the
project's own set — in the manifest entry's `description`, beside the version —
that the template's bytes were changed after that version was applied, which
line was removed, and why it could not alter the cluster. **The ledger row keeps
the old digest and is right to.** The record of the divergence is the manifest's
job because the ledger's `ON CONFLICT DO NOTHING` means the ledger cannot do it
(D1438).

## Consequences

- **The on-ramp question is answered and the answer is yes, bounded.** It is
  removed from `docs/scope-closure.md` §15 as an open decision, and the upgrade
  guide's §1.0 sentence *"how a pre-1.1.0 fork CONVERTS is undecided"* becomes
  false in the commit that implements this.
- The conversion needs exactly **one** new product capability: ADR 0210's
  `--follows`. Everything else already exists, and the piece nobody knew existed
  is ADR 0206's ledger move (D1435).
- **`docs/upgrade-guide.md` gains the procedure as §1.0's second half**, written
  from this ADR and from rig 28a's measurements, with the classes table as the
  merge rule the page said it would not invent. Run 3.
- A conversion is not verifiable end to end without a cluster that carries the
  fork's history. **This session does not perform one** — D940's rule is that a
  migration over a table with history must be proved against a cluster with
  history, and the only such cluster is an adopter's. What is proved here is
  every step that a checkout can prove, and the ADR says which step is not:
  step 7, the ledger move on a real ledger.
- Rig 28a is a throwaway and is rebuilt from its scripts, not preserved. The
  build is deterministic from tag `1.0.0` and tag `1.6.2`.

## Alternatives considered

**Decide that no conversion exists.** This was a permitted outcome and the
measurements took it off the table. The blocker everyone assumed — re-homing
means amending applied migrations, which D912 forbids — is not what re-homing
does: the bytes and the version do not move, only the file and the declaration.
Deciding *no* would have been deciding against a measurement.

**Re-stamp the fork's migrations above the release's newest.** Rejected, and the
product already refuses it in prose: it amends applied migrations (D912), and
ADR 0206's ledger move matches by version, so re-stamped versions would move
nothing and the next deploy would re-apply SQL against objects that exist. The
refusal message has said this since 1.6.2; this ADR keeps it true.

**Write a `bin/apg.sh convert` that performs the seven steps.** Rejected for
this session and recorded rather than refused. Five of the steps are `git mv`
and a JSON edit; one is a flag; one is a deploy. A command would have to be
proved against a fork it did not build, and the only real fork lives on a host
this project does not administer. The procedure is written first and a command
is a later session's, if an adopter ever asks twice.

**Widen the lint so a 1.0.0-era set passes unchanged.** Rejected by ADR 0211 and
repeated here because it is the shortcut this ADR would otherwise invite: it
would convert a fork by lowering the boundary the conversion exists to bring it
inside.
