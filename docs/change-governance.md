# Change governance

Since `1.13.0`. A change to your project's migration set is **proposed** on a
workstation, recorded in a file you commit, optionally **approved** under a
second name, and a host **applies only a proposed set** (ADR 0243).

**What the records are, in the one sentence every page repeats: they stop an
unreviewed or altered set reaching a host; they do not authenticate a
reviewer.** Both records say `declared_by`, never `approved_by` or `author`,
and each carries the line *"The names in this record are declared, not
authenticated (ADR 0243)."* There is no operator identity in this product — a
name typed by the person it names is a record of intent (D1864).

The other half of the same session is **approval in the database** (ADR 0242,
the last section below): a gated project function refuses an agent that
reaches it directly, as well as through the agent plane.

## The digest

A set is identified by **the sha256 of its lock file's bytes** —
`projects/<slug>/migrations/released.lock.json`, exactly as committed. The
lock binds every template and its canonical render, so the digest moves when
any migration in the set does, and when the lock is re-serialised: a lock
re-indented is a different file. The render records the same value as the
deployed document's `migrations.project_set.lock_sha256` — one function
computes it for both (D1857).

A proposal is named by that digest:
`projects/<slug>/proposals/<digest>.json`, and its approval sits beside it as
`<digest>.approval.json`.

## Proposing

```bash
bin/apg.sh dev down --project project.yaml     # if you have one up
bin/apg.sh migrate propose --project project.yaml --by "Ada Lovelace"
```

```
proposal a097d35e2fb8655c written: projects/walk-demo/proposals/a097d35e…f5e.json (0 destructive finding(s))
```

`bin/migrate.sh propose` (which `apg migrate propose` dispatches to) checks
the set's lock and runs the lint, refuses a gated function that does not call
the guard first, and then **applies the set to an EMPTY cluster through
`bin/dev.sh up`, and removes it with `bin/dev.sh down`**. It refuses before
starting if a development environment exists for the project — up, stopped,
or in a state it cannot read — and never removes yours (D1904). About ten
seconds. It writes the record once (`O_EXCL`); a changed set has a new digest
and so a new proposal.

What the record holds, member by member:

| Member | What it says |
|---|---|
| `set_digest`, `set` | The digest; the set's root, every version and name, and its `follows_release_version` with whether that was computed or declared |
| `release` | The release it was proposed against: `template_version` and the release lock's own sha256 |
| `lint` | Always `passed` — a set the lint refuses gets no record |
| `destructive` | Every destructive statement, **named and never refused** (below) |
| `dev_apply` | `exit`, `migrations_applied` (the whole cluster's count, release and set), `seconds`, and its limits verbatim: `from_empty: true`, `applied_by: "psql as migration_user"`, `existing_rows: "none"` |
| `surface` | Every function and view the set defines or replaces, each with whether your reviewed `contracts/postgrest-api-surface.yaml` names it |
| `approval_gate` | The approval-gate check's findings — `[]` for a set whose every gated function calls the guard first |
| `harness` | The evaluation harness's cases ASKED of the capability contract — derived, written, capabilities — and the line *"cases asked of the contract, not results"* |
| `capability_contract_sha256` | The committed capability contract's sha256 |
| `declared_by`, `declared_at`, `note` | The declared name, the time, and the sentence above |

### Three readings it cannot take, and says so

- **An upgrade class.** `bin/upgrade.sh plan` cannot price a change to a
  project's set — it prices a release by its `template_version` — so the
  record carries the facts that command would have read (`release`, the
  `follows_release_version`) rather than a class it could not compute (D1858).
- **The client's diff.** A generated client is built from the snapshot a
  deployment's PostgREST serves, captured after a deploy, so no pre-deploy
  check can see a migration in it. The record carries the reading that CAN be
  taken on a workstation — the set's final surface against your reviewed one —
  and the client moves after the deploy by the usual path (D1859).
- **Results.** The harness records cases asked, never outcomes; outcomes exist
  only in test runs. A project whose manifest declares no capabilities records
  `{"not_applicable": "the manifest declares no capabilities"}` for `harness`
  and for `capability_contract_sha256` — said, never zero (D1860).

And the apply is **from empty**: a cluster with no rows cannot say what an
`ALTER … TYPE` does to real data. That is why `dev_apply` states its limits
rather than calling itself a shadow of production (D1861).

### `destructive`

Sixteen kinds, each a `{version, kind, object}`: `DROP` of a table, view,
materialized view, function, procedure, index, type, sequence, trigger or
policy; `ALTER TABLE … DROP COLUMN`, `… DROP CONSTRAINT`, `… ALTER [COLUMN] …
[SET DATA] TYPE` and `… RENAME`; `TRUNCATE`; and `DELETE FROM` with no
`WHERE`. Every spelling PostgreSQL accepts is read — `IF EXISTS`, quoted and
schema-qualified names. Comments and string literals are not findings; a
statement inside a dollar-quoted body IS read, because a `DO` block runs at
apply time (D1911).

**Named, never refused** (D1862). A reviewer decides, and a destructive change
is sometimes the change. The lint is untouched by this list.

## Approving

```bash
bin/apg.sh migrate approve --project project.yaml --proposal <digest> --by "Grace Hopper"
```

Writes `<digest>.approval.json`, naming **the proposal file's own sha256**, so
an edited proposal invalidates its approval. It refuses the proposer's own name
compared without case or spacing — *"ada  LOVELACE"* is Ada Lovelace —
with *"an approval needs a second name (ADR 0243)"*, a missing proposal, and a
second approval. That the second name is a second PERSON is what the record
cannot know, and says so.

A declared name is a letter, then letters, digits, spaces or `. _ ' -`, 2 to
64 characters. No comma.

**Whether a host asks for an approval is the project's own setting**:
`migrations.approvals_required`, `0` or `1`, at project manifest schema 8, in
the `migrations` block beside the `set` it governs. Absent is `0`. The example
project sets `1`, to demonstrate the two-name rule; a project worked on by one
person sets `0`, or nothing.

### Exit codes, both verbs

| Exit | Meaning |
|---|---|
| `0` | Written |
| `2` | Bad input: a name that is not a declared name, a digest that is not 64 lowercase hex, a project with no set of its own |
| `3` | A prerequisite is missing: the project is not rendered, or a development environment exists |
| `5` | Refused: the lint, the approval-gate check, the two-name rule; the set did not apply on the empty cluster; or the record already exists |

**Neither verb commits.** The records are committed by whoever wrote them,
like any other file under `projects/<slug>/`.

## What a host refuses

`bin/migrate.sh up` — which a deploy's step 6 runs — asks one question before
it writes anything: **does the project's set have a version this cluster has
not applied?** If not, nothing is needed: a set applied before proposals
existed is never refused, so upgrading breaks nobody (D1865). The release's
own set is never asked; its own lock is its review.

If something is pending, it requires the COMMITTED proposal for exactly the
set being applied, and — under `approvals_required: 1` — its approval. The
check runs before the ledger repair and before either set's migrator, so a
refusal has applied and written nothing (D1912). It refuses at exit 5 with one
of four sentences, and step 6 relays it as *"migrations did not apply:"*
followed by the sentence:

| Sentence | Means |
|---|---|
| `no proposal for this set <digest16>` | No `proposals/<digest>.json` for the set this release carries |
| `the proposal names another set` | The file at that path names a different digest — compared whole, never by its first sixteen characters |
| `approvals_required is 1 and the proposal has no approval` | The project asks for an approval and there is none |
| `the approval does not name this proposal, or names its proposer` | The approval names other bytes, another set, or the proposer's own name |

**The remedy is always on the workstation**: propose (and approve, if asked),
commit, and deploy again. Only committed files reach the release a host runs
from, and nothing is ever written into a host's checkout (D971, D1852).

`bin/migrate.sh --runtime status` prints one line after the ledger:

```
migrate: proposal 35245421404e77d3: not needed (nothing pending)
migrate: proposal 35245421404e77d3: absent (1 pending; up refuses)
migrate: proposal 35245421404e77d3: present, approved by Grace Hopper
migrate: proposal 35245421404e77d3: present (approvals_required is 0)
migrate: proposal 35245421404e77d3: present; up refuses: <one of the four sentences>
migrate: proposal 35245421404e77d3: whether anything is pending could not be read (<why>)
migrate: proposal: not applicable (this project applies no set of its own)
```

The sixth is a reading it could not take, said rather than guessed (ADR 0195).

## The capability contract, reported

The capability contract is recompiled into the lock at every deploy, so there
is no pending capability state to refuse on. Step 6 prints one line after the
lock is written — **a report, never a refusal** (D1866):

```
  capability contract 3d7d6e6d513a1e6c: named by proposal 35245421404e77d3
  capability contract 3d7d6e6d513a1e6c: named by no proposal of this project
  capability contract 3d7d6e6d513a1e6c: the project's proposals could not be read (<why>)
  no capability contract (the manifest declares none)
```

## Approval, in the database

Since `1.13.0` approval is not only a plane control (ADR 0242). A project's
gated function — one whose capability declares `requires_approval` — calls
**`app.require_approval('<tool>')` as its first statement**. The guard is
granted to nobody and lives in `app`, which PostgREST cannot address, so it is
reachable only from a reviewed definer function running as the owner.

- **An agent calling the function directly** — through the REST route, with
  its own token and the capability's scope — is refused `403` with *"AP403:
  approval_required"*, and nothing is written.
- **The approved step's call through the plane** carries the signed approval
  claim and its idempotency key, and is served — once, for that tool and that
  key, while the run is running.
- **A person's own call** passes: approvals are made by people, and a person's
  own write through the reviewed surface was never what an approval gates.

`bin/mcp-contract.sh check --project` and `propose` **refuse** a gated
function whose first statement is not that call; the render **reports** it.
Two things stay plane controls, and the check says so: an approval a
deployment's PROFILE adds to a RELEASE tool (the check prints it as
`release_function` — the database cannot read a deployment's profile, D1869),
and the dry run — a person's own direct call with a `Dry-Run` header still
writes (D1870). The guard does not make a function idempotent (D1871).

The example set's `0004-approval-in-the-database.sql` is the worked one: the
previous body of `api.set_note_embedding`, byte for byte, with the guard as
its first statement.

## What is not here

- **A lock-risk estimate.** Nothing says how long a migration holds a lock on
  a table with rows in it; the apply is from empty.
- **A capability refusal at deploy.** A capability change is reported (above),
  never refused.
- **A proposal for a workflow or a connector.** Both are reviewed files under
  `projects/<slug>/`, installed by the deploy; neither is governed here.
- **An authenticated reviewer.** The names are declared. A reviewer's identity
  is the business of whatever reviews your commits.

Operating it on a deployment is [Operating a deployment](operator-guide.md)
§19; the first time you meet it is
[the new team member guide](new-team-member.md)'s step 11.
