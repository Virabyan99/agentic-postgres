# 0206 — A project's migration set gets its own directory and its own migrations table

- **Status:** accepted
- **Date:** 2026-09-13
- **Session:** 24, Run 8 (D1288)
- **Related:** ADR 0028 (the rendered payload is the immutable unit), ADR 0093
  (an operator command imports only what the host has), ADR 0155 (a deploy
  recreates a container whose mounted content changed), ADR 0195 (three
  outcomes, the third reported), ADR 0198 (a project may declare its own
  migration set, applied after the release's), ADR 0203 (`apg dev` applies the
  same rendered payloads); D912 (never amend an applied migration; fix
  forward), D940 (a migration over a table with history must be proved against
  a cluster with history), D1096 (a cluster that has moved and a record that
  has not is the worst order a failure can arrive in), D1098 (rig 20a: `up
  --strict` exits 2 having applied nothing when the order is broken on a
  deployed cluster, and applies the same pair silently on a fresh one), D1288.

## Context

ADR 0198 let a project declare migrations of its own, applied after the
release's. The two sets were rendered into **one directory** and applied by
**one `dbmate` invocation** against **one `app_private.schema_migrations`**, so
their versions share a single ordering space. `follows_release_version` records
the release version a project set was frozen against and refuses any project
migration that does not sort after it.

`_assert_follows_release_version` explains why only that one direction is
checked:

> The direction is not symmetric and that is the whole rule. A project
> migration older than an APPLIED release migration is refused by the cluster;
> a release migration newer than an applied project migration is fine, because
> it sorts after everything on both a fresh cluster and a deployed one. So the
> rule constrains only what a project may author, and never what the release
> may.

**That is false, and Session 24's trip is where it was refuted** (D1288). It
conflates *authored later* with *sorts higher*. Versions are authoring-date
stamps. The example project's set is stamped `20260914120001`/`…0002` — chosen
at freeze to clear `follows_release_version` `20260912120031`, and therefore
**two days ahead of the release's own clock**. That left the release a window
in which anything it authored sorted *below* an applied project migration.
Session 24's migration `0032` is stamped `20260912120032` and landed in it, so
beta refused the deploy at step 6 having applied nothing:

    migration `20260912120032` is out of order with already applied migrations,
    the version number has to be higher than the applied migration
    `20260914120001` in --strict mode

Alpha was unaffected: it declares no project set.

**The conflict is structural, not a bad stamp.** With one shared ordering
space, a project set must stamp *above* the release's newest at freeze, while
every later release migration must stamp *above* every applied project version.
Those two demands climb past each other indefinitely, and each new project set
raises the floor the release must clear. There is no pair of stamping rules
that satisfies both for an arbitrary sequence of releases.

## Decision

**A project's migration set is rendered into its own directory and applied
against its own migrations table.** The release's set keeps
`app_private.schema_migrations`, `<rendered>/migrations/`, and its existing
`dbmate` invocation unchanged; a project set is rendered to
`<rendered>/migrations-project/`, mounted separately, and applied with
`--migrations-table app_private.project_schema_migrations`. dbmate 2.34.1 —
the digest-pinned image this release already runs — takes `--migrations-table`
and `--migrations-dir` as global options, so this is parameterisation rather
than new machinery.

Each set is then ordered against its own applied set only. A new release
migration compares against applied *release* migrations, and a project
migration against applied *project* ones. `--strict` stays on both, for the
reason it was added: without it dbmate applies what it can and exits 0 on a
partially applied set.

A cluster that already applied project migrations into
`app_private.schema_migrations` — beta is the only one — has those rows
**moved** to the project table once, by the deploy, as the superuser, before
either invocation. Moved rather than re-applied: the example project's
`0001-note-embeddings.sql` is a bare `CREATE TABLE`, so re-applying it would
fail, and a row deleted without being re-recorded would make the cluster's
history unreadable.

`follows_release_version` is **kept**. It no longer prevents anything the
cluster would refuse, but it still records which release a set was reviewed
against, and removing a released guard is a separate decision from the one
this ADR takes.

## Alternatives rejected

**Re-stamp the project set above the release.** Does nothing: beta's applied
`20260914120001` row stays in `schema_migrations`, so `max(applied)` does not
move and `0032` is still refused. It would also fail on apply, because
`0001-note-embeddings.sql` is not re-runnable.

**Supersede `0032` at a version above the project set** (retire it from the
manifest, or re-stamp it). It works — `0032` is re-runnable, being a `DROP
FUNCTION` and `CREATE FUNCTION` of the same signature — and it is the cheapest
change by a wide margin. It was rejected for what it leaves behind:
`app_private.migration_ledger` is written `ON CONFLICT (version) DO NOTHING`
and `migration_user` deliberately holds no privilege on it, so the retired
version's row cannot be removed by any migration. Alpha would stand at 33
applied against 32 released **permanently**, which `diagnosis.migrations`
reports as `WARN … it is ahead of this checkout`. Buying a day by degrading the
one healthy deployment's doctor to a standing false warning is the trade this
project exists not to make. It also leaves the structural conflict in place for
the next release migration and the next project set.

**Drop `--strict`.** It guards partial application, not only ordering: without
it dbmate applies what it can and exits 0 having applied some of a set. Removing
it to get past an ordering refusal would trade a loud stop for a silent
partial migration.

**One-time out-of-order apply on beta.** No supported path: `--strict` is
appended unconditionally, so it means either editing the product to weaken a
released property without a decision, or running dbmate outside the product on
a deployed host — the inverse of D1114.

## Consequences

The release's path is unchanged end to end — same directory, same mount, same
table, same invocation — so a project that declares no set renders and migrates
exactly as before, and alpha needs nothing. What changes is confined to
projects that declare a set: a second rendered directory, a second mount, a
second invocation, a second table, and a one-time move of existing rows.

`app_private.migration_ledger` still records every set, so the doctor's
`applied` count and `record_ledger` are untouched — the split is in dbmate's
bookkeeping, not in this repository's record of which bytes ran (D1096's
distinction, load-bearing again).

The two sets can now be stamped independently, which is the point, and it means
a project set's versions no longer say anything about the release's. A reader
who wants the order in which a cluster applied everything reads
`migration_ledger`, which has always been the answer and is now the only one.

`apg dev` applies the same rendered payloads (ADR 0203) and gains the same
split, so a dev cluster and a deployment continue to be built by one code path
rather than two that agree.
