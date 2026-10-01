# 0243 — A change to a project's migration set is proposed, recorded with the readings that exist, and a host applies a pending set only when a committed proposal names it; the names in both records are declared

- **Status:** Accepted
- **Date:** 2026-09-30
- **Session:** 35, Run 1 (D1857–D1866; rig 35b)
- **Affects:** `src/agentic_postgres/migrations.py` (Run 3: `set_digest`,
  `destructive_findings`), `src/agentic_postgres/rendering.py` (the render's
  `lock_sha256` through `set_digest`), `bin/migrate.sh` / `bin/migrate.py`
  (Run 3: `propose`, `approve`; Run 4: the gate in `up`, the `status` line),
  `bin/deploy-project.py` (step 6 relays the gate; the capability line),
  `schemas/project.schema.json` and `src/agentic_postgres/config.py` (project
  manifest schema 8, `migrations.approvals_required`),
  `projects/<slug>/proposals/`.
- **Related:** ADR 0002 (one reader of a derived identity), ADR 0162 (what a
  bump permits), ADR 0195 (a reader reports what it could not determine),
  ADR 0198/0206/0240 (a project set, its order, its declared `follows`),
  ADR 0203 (`apg dev`), ADR 0242 (the approval-gate check), D971, D1523, D1852.

## Context

A project set is applied by deploy step 6 (`migrate.sh --project … --runtime
up`, the only caller). Nothing records that anyone looked at a set before a
host applied it, and nothing on the host could tell a reviewed set from one
edited afterwards. The stage plan's brief (D1523) asks for a proposal record,
a destructive reading, a configurable second approval, and a host that refuses
an unproposed set — and says the lock-risk estimate *"is not built on a
guess"*.

The planning read and rig 35b measured what can be read before a deploy:

- **The set's identity already exists.** The render records
  `migrations.project_set.lock_sha256`, the sha256 of the set's
  `released.lock.json` — and the lock binds every migration's template and its
  canonical render.
- **`apg dev up` is the shadow** (D1861). Measured on the example project:
  exit 0 in 22–29 s on this workstation; its line is `dev: 39 migrations
  applied as <migration_user>` — **39 is the WHOLE cluster, the release's 36
  plus the set's 3**, so a proposal reads the set's own count from the set,
  never from that line; a second `up` while one is up exits **2** with
  `… is already up (since …); \`apg dev reset\` rebuilds it, \`apg dev down\`
  removes it`; `status` after `down` exits **4** (`no development
  environment`). It applies each migration by `psql` as the migration role,
  from EMPTY — not dbmate `--strict`, and over no existing rows.
- **The set's final `api` surface is readable**: `sql_surface.final_surface`
  over the example set returns the function `set_note_embedding` and the view
  `note_embeddings`, both named by the project's reviewed
  `contracts/postgrest-api-surface.yaml`.
- **Three readings do not exist and are not faked**: `upgrade plan` cannot
  price a project-set change (it bumps from `template_version` alone, D1858);
  a pre-deploy `generate --check` cannot see a migration (the client is built
  from a post-deploy snapshot, D1859); the harness records cases asked, never
  outcomes (D1860).
- **There is no operator identity** (D1864). The one resolver maps `SUDO_UID`
  to a Unix name and says *"an identity supplied on a command line is not an
  identity"*; the host has one operator account; proposals are written on a
  workstation that holds no product credential.

## Decision

1. **The digest.** `migrations.set_digest(set)` = sha256 of the set's lock
   bytes, and the render's `lock_sha256` is computed by calling it: one
   function, two readers.
2. **`bin/migrate.sh propose --project M --by NAME`** writes
   `projects/<slug>/proposals/<digest>.json`: the set's versions, the lint's
   result, `destructive_findings` (named, never refused), the dev-cluster apply
   through the product's own `bin/dev.sh up`/`down` (exit, the set's migration
   count, seconds, and its limits stated verbatim — `from_empty: true`,
   `applied_by: "psql as migration_user"`, `existing_rows: "none"`), the set's
   final `api` surface against the reviewed contract, the approval-gate check
   (ADR 0242), the harness's CASES labelled as cases, the committed capability
   contract's sha256, the release it was proposed against
   (`template_version`, `release_lock_sha256`, the set's
   `follows_release_version` and its source) and `declared_by`. It refuses
   while a dev environment is up (it never downs one), when the lint or the
   approval-gate check fails, and when the file exists. Everything but its
   times is deterministic.
3. **`bin/migrate.sh approve --project M --proposal DIGEST --by NAME`** writes
   `<digest>.approval.json` naming the PROPOSAL FILE's own sha256 and a
   declared name; it refuses the proposer's name (case- and space-folded), a
   missing proposal and an existing approval.
4. **Project manifest schema 8** adds `migrations.approvals_required` (0 or 1,
   default 0) beside `migrations.set`, forbidden below 8 and without a set;
   `config.approvals_required(manifest)` is its one reader. Versions 1–7 load
   unchanged and read as 0.
5. **The host gate is on the ACT.** `migrate.py up`, before dbmate: when the
   project set has a version the project LEDGER lacks, it requires the
   committed proposal for the set being applied, and under
   `approvals_required: 1` an approval naming that proposal's bytes by another
   name — else exit 5 with one of four fixed sentences. A set with nothing
   pending needs nothing; the release set is never gated. `status` prints one
   proposal line; step 6 relays the sentence. Only committed files reach the
   release directory `migrate.py` runs from, so nothing is ever written on a
   host (D971, D1852).
6. **A capability-contract change is REPORTED** (D1866): the proposal records
   the committed contract's sha256, and step 6 prints whether a proposal of
   this project names it — never a refusal.
7. **The records' reach, in one sentence every page repeats: *it stops an
   unreviewed or altered set reaching a host; it does not authenticate a
   reviewer.*** Both records name `declared_by`, never `approved_by` or
   `author`.

## Alternatives rejected

- **A resolved Unix name.** One operator account on the host, and the host is
  not where a set is reviewed.
- **Records written on the host.** A host checkout may not gain a file (D971,
  D1852: an untracked file dirties the release and every deploy refuses).
- **A gate on the STATE** (every applied set must have a proposal). Beta's
  applied `36 + 3` has none; its next deploy would refuse for work done a week
  ago.
- **A lock-risk estimate.** No reading of lock behaviour exists; the brief's
  own words forbid a guess.
- **`upgrade plan`'s class, `generate --check`'s diff, harness results in the
  record.** Each would be a value that looks measured and is not (D600).

## Consequences

- An adopter who adds a migration after upgrading runs `propose` (and, under
  `approvals_required: 1`, has a second person run `approve`) and commits both
  before deploying. The upgrade guide's 1.13.0 row says so.
- A from-empty apply says nothing about existing rows; the record says that in
  its own members rather than in prose nobody reads.
- One person can commit both records; root on the host can do anything. The
  threat model's `THR-CHANGE` carries both.
