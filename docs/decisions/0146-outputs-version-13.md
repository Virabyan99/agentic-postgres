# 0146 — Outputs version 13, and why the observation is a block of its own

Status: accepted
Date: 2026-08-23
Session: 10, Run 2

Affects: REC-EVID-001, REC-WAL-001, D519, D520, D534, D535, ADR 0012, ADR 0053,
ADR 0099, `schemas/outputs.schema.json`,
`src/agentic_postgres/deployed_output.py`,
`src/agentic_postgres/output_migrations.py`

## Context

Three separate gaps, all in one document, all found while reading rather than
while failing:

**`backup.retain_full` was validated and reached nothing** (D519). The schema
has bounded it at 1–12 since Session 1, both example manifests set it, and no
code has ever read it: `_validate_backup` did not touch it, there was no
defaults dict to resolve it against, and it was absent from `outputs.json`. A
manifest could ask for seven chains and get whatever pgBackRest defaulted to.

**The deployed branch had no `backup` block at all**, and `additionalProperties`
is `false` at every level (D520). So there was nowhere to record when a backup
last succeeded, whether WAL is reaching the repository, or what the latest
recoverable point is — the three things `docs/source-specification.md` §12.3
requires as evidence.

**The cluster needs a network that did not exist.** `internal` is
`internal: true` and rig1 measured what that means: DNS fails and TCP fails, so
`archive-push` cannot reach R2 from where the postmaster runs it (D516).

ADR 0053 set the rule for how these arrive: a version is chosen **once from a
session's whole surface**, not a run at a time. D255 and D308 are the record of
the alternative — version 9 was chosen one run early with the session's
remaining fields in mind and still missed a budget.

## Decision

**Outputs version 13, carrying all three, plus a deployed-only observation.**

Rendered branch:

- `backup.bucket` — `naming`'s, null when backups are disabled.
- `backup.retain_full` — the manifest's, resolved against
  `config.BACKUP_DEFAULTS`, and **published whether or not backups are
  enabled**, because it is a bound rather than a name.
- `compose.networks.backup` — the egress network, named a run before anything
  attaches to it.

Deployed branch:

- `backup` — **the same `$def`**, `backupSettings`, not a copy.
- `backup_state` — a **separate top-level block**, deployed only.

`backup_state` carries `status` (`not_observed | unconfigured | ready |
failing`), `stanza_created`, `last_full_backup_label`, `last_full_backup_at`,
`latest_recoverable_time`, `wal_archived_count`, `wal_failed_count`.
`not_observed` forces every other member null.

## Consequences

**One definition, two branches — and the observation moved out rather than the
settings being duplicated.** This is the decision worth reading. ADR 0012 says a
rendered document contains no observed value, and the cheapest way to keep that
true is for the field to be *unrepresentable* on that branch rather than merely
constrained. `database` achieves that by splitting into `renderedDatabase` and
`deployedDatabase`, where the deployed one is the rendered one plus `observed`
— a copy, maintained twice.

D389 is the record of what that copy costs: `storageSettings` was duplicated per
branch, the two disagreed, and `STO-BOUND-001` read the deployed document for
`max_upload_bytes` and found nothing to measure. *"One definition rather than a
copy per branch, because a copy is what let the two disagree."*

Both constraints are satisfiable at once only by putting the observation
somewhere the rendered branch does not have. Hence `backup_state` beside
`backup` rather than inside it.

**`wal_failed_count` is published and `last_failed_wal` is not**, and that is
D535 rather than an omission. rig1 measured the segment name pinning to the
oldest stuck WAL — `000000010000000000000001` across all three samples — while
the count climbed 11 → 15 → 26. A reader watching the name would see a steady
value for the entire failure. The count is what moves, so the count is what a
document meant to expose failures carries.

**`not_observed` is what every project carries until Run 6 writes an observer**,
and what a project deployed through a session before 10 carries permanently.
`NOT_OBSERVED`'s discipline, for its reason: a zero `wal_failed_count` beside a
`ready` status would be a claim that archiving is healthy, and a zero is
indistinguishable from a real measurement that happened to be zero.

**The v12 → v13 migrator invents nothing.** Bucket and network are `naming`
derivations and arrive as arguments; `retain_full` could have been defaulted
here and deliberately is not, because `config.BACKUP_DEFAULTS` is the one place
that answers "two chains" and a second answer in the migrator would disagree the
first time the default moved. This is `migrate_v11_to_v12`'s refusal applied
again — that step declines to insert `routes.mcp` for exactly this reason.

**Nine hand-chained migration tests had to be edited, not merely re-run.** That
is the design working: each asserts the step's own result as a literal and the
chain's endpoint as `CURRENT_VERSION`, and the file's own comments record that
spelling both as the constant is how the assertion stopped meaning anything the
last time a version was added.

**A rendered name with no consumer for two runs.** `compose.networks.backup` is
published here and attached to nothing until Run 4. That is the state
`storage.bucket` was in from Session 1 to Session 7, and it is why the name is
in `evidence.ISOLATED_FIELDS` now rather than later: D339 found the one derived
identifier that had gone six sessions without a namespace, and it was the one
nothing compared.

## Alternatives considered

**`backup.observed`, nested, with two `$defs` like `database`.** Rejected: it
satisfies ADR 0012 by reintroducing exactly the per-branch copy D389 was written
about. The database pays that cost for historical reasons; a new block need not.

**Put the observation in `routes`, as `storage` and `mcp` readiness are.**
Rejected: those are readiness of an HTTP surface with a URL. A repository is not
a route, has no URL, and `publishedRoute`'s `status`/`url` pair would have to be
bent to carry six unrelated measurements.

**Three separate versions, one per run.** Rejected by ADR 0053 and by D255/D308
before this session started. The cost of being wrong is a second bump inside one
session, and each bump is a migrator, a fixture, and nine chained tests.

**Defer the deployed block until Run 6 has an observer.** Rejected: it would be
version 14 inside the same session, for a field whose shape is already known.
`not_observed` exists so a block can be honest before it is populated.
