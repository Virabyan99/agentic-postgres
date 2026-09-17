# 0214 — The reading before a tag states facts and names the judgement it cannot make

- **Status:** Accepted
- **Date:** 2026-09-17
- **Session:** 28, Run 7 (D1424, D1463–D1467)
- **Affects:** one new operator command, `bin/release-reading.sh`, and
  `agentic_postgres.release_reading`. No schema, no migration, no deployment.
  The requirement and its claim are registered in Run 9.
- **Related:** ADR 0209 (a release is held to its own documentation by a test),
  ADR 0195 (a report may not substitute an answer for not knowing), ADR 0162
  (what a patch is), ADR 0093 (a `bin/` command's imports).

## Context

A release's documentation has landed one commit past its own tag three times,
twice of them on one day. D1033 at `1.0.0`, repaired by cutting `1.0.1`; D1388
at `1.6.0`; and then on 2026-09-16, in the release that shipped ADR 0209,
two repairs and a reply page landed past `1.6.1`, which cost `1.6.2`.

**ADR 0209's guard caught none of them, and it is right not to.** A test runs
inside a commit and cannot see a tag cut after CI is green; the ADR says so in
its own Consequences. So the guard is correct about what it can assert and the
habit around it is what fails. D1424 asked for a pre-tag reading and left one
question open: **a command, or a checklist?** — noting that D1033's row says a
checklist already existed in prose and the session that wrote it did not follow
it.

Rig 28c answered it by measuring this repository's own history. Five passes,
every number read from `git`, with controls.

### 1. Every tag in this repository has release bytes landing past it

Five tags: `1.0.0`, `1.0.1`, `1.6.0`, `1.6.1`, `1.6.2`, all annotated. For each
one, the commits that follow it on `main` up to the next `VERSION` change:

| Tag | The first commit past it | What it touched |
|---|---|---|
| `1.0.0` | `b60814b` | `bin/bootstrap-providers.py`, `tests/contract/test_disaster_kit.py` |
| `1.0.1` | `a0d853f` | the plan and the ledger |
| `1.6.0` | `d1a6db0` | the plan's Done paragraph |
| `1.6.1` | `f97075d` | the plan's close, the ledger |
| `1.6.2` | `ad96673` | the audit |

**D1424 said three times. It is five of five**, and the first one is not
documentation at all — `1.0.0`'s next commit is a product repair in `bin/`
(D1463).

### 2. The discriminator that looked obvious does not exist

If the class were *product bytes landing after a tag*, it would be computable:
classify each path as a record (a plan, the ledger, an audit, an evidence
document) or as release bytes, and report the first release-byte commit past
the tag. Measured over all five tags, twelve commits deep each:

- `1.0.0` → release bytes at **+1**, and that one was a defect.
- `1.0.1` → records at +1, +2, +3, then release bytes at **+4**, and that one
  was Session 20 starting work on the next release.
- `1.6.0` → records at +1, release bytes at **+2** (Session 26's guides).
- `1.6.1` → records at +1, release bytes at **+2**, and that one was a defect.
- `1.6.2` → records at +1 through +4, release bytes at **+5**, and that one is
  Session 28 doing exactly what it is supposed to.

**The defect and the ordinary state are the same shape.** Release bytes land
within one to five commits of every tag, always, because the next session
starts. What separates *work that belonged inside the release* from *the next
release's work* is intent, and intent is not in the tree (D1464). Any verdict a
command printed here would be invented, which is D1441's mistake — a threshold
on an unmeasured footing — struck earlier in this same session, from the one
command that runs as root on production.

### 3. A verdict about the interval would fire on a third of the history

Replaying the naive question — *is the tree's `VERSION` already tagged, and have
commits landed since?* — against all 147 commits from `1.0.0` forward: **45 of
them answer yes** (D1465). That is not a warning, it is the normal condition of
a repository between releases, and a reading that shouts at a third of every
history is a reading that gets ignored — which is precisely how the prose
checklist failed.

### 4. The facts a person cannot hold in their head, they cannot check

At `acb08e4`, ten commits past `1.6.2`, with `VERSION` unmoved:

| | At the tag | In the tree |
|---|---|---|
| Released migrations | 32 | **33** |
| ADRs | 209 | **213** |
| Files changed | — | 61 |
| `VERSION` | `1.6.2` | `1.6.2` |

Nobody cutting a tag knows those numbers. A checklist can only ask somebody to
check them; it cannot produce them.

### 5. A test could not take this reading even if it wanted to

`.github/workflows/ci.yml` has three jobs. Only the first, the gate, checks out
with `fetch-depth: 0`. The job that runs the contract suite and the P0
inventory job use `actions/checkout`'s default. Measured against a control — a
depth-1 clone of this repository beside a full clone of the same commit:

```
depth 1 :  git tag → (empty), count 0;  git describe → fatal: No names found
full    :  git tag → 1.0.0 1.0.1 1.6.0 1.6.1 1.6.2, count 5;  describe → 1.6.2
```

ADR 0209's reason — *a test runs inside a commit* — is right and incomplete.
There is a second, independent reason: **in two of CI's three jobs the tags do
not exist at all**, so a proof about them would pass by measuring nothing,
which is D600's value exactly (D1466).

## Decision

**The reading before a tag is a command that states facts and names the one
judgement it cannot make. The judgement is a short checklist, and the command
prints it.**

### 1. It is a command, because the facts have to be produced

`bin/release-reading.sh` — one verb, no arguments beyond `--help` — prints, from
the checkout alone:

- **where HEAD stands**: the commit, the tree's `VERSION`, and any tag pointing
  at HEAD;
- **the last tag**: its name, its commit, its date and the `VERSION` it carries;
- **what has landed since it**: commits, files, the paths grouped by the
  directory they sit in, and the two counts nobody remembers — released
  migrations and ADRs, at the tag against the tree;
- **the bump**: the commit that last moved `VERSION`, what else moved in it, and
  **what has landed after it**, which is the narrow window where *does this
  belong inside the release* has a right answer, because the bump commit is
  where the release is declared.

`agentic_postgres.release_reading` holds the classification and the rendering
and reads nothing; `bin/release-reading.py` owns the `git` subprocesses. The
command imports only `agentic_postgres` (ADR 0093).

### 2. It is also a checklist, because the judgement is not computable

The command ends by printing three questions, in the second person, unanswered:

```
  Does everything in this window belong inside <VERSION>?
  Is there anything you intended to be in <VERSION> that is not in this list?
  Is this commit the one the tag goes on?
```

**The checklist is inside the command rather than beside it.** A checklist on a
page can go stale, can be skipped by somebody who ran the command, and asks a
person to gather the facts as well as judge them — which is the arrangement
that failed five times. Printed by the command, it cannot drift from the facts
above it and it cannot be reached without them.

### 3. It states three outcomes and takes none of them (ADR 0195)

| What it found | What it prints | Exit |
|---|---|---|
| The tree's `VERSION` has no tag | **a tag is owed on this commit**, and here is what it would contain | 0 |
| The tree's `VERSION` is tagged, commits since | **that tag does not contain these bytes**; whether they belong inside it is yours to decide | 0 |
| The tree's `VERSION` is tagged, nothing since | there is nothing to decide | 0 |
| **No tags in this clone** | **the reading cannot be taken here** | 3 |

**It never exits non-zero on a judgement**, because it makes none: a report may
not fail closed (ADR 0195). It exits 3 when it could not take the reading at
all, which is the opposite — refusing to print a clean answer it did not
measure.

### 4. It is not in the gate, and that is measured rather than chosen

The gate runs in CI, where the suite's job has no tags. Wiring the reading into
it would print *the reading cannot be taken here* on every CI run, which trains
its reader to skip it. It is run by a person at a workstation with a full
clone, at the session close, and `docs/operator-guide.md` and each session
plan's close say so (D1467).

## Consequences

**The five-of-five habit gets one thing it never had: the facts, at the moment
they are answerable.** It does not get an enforcement, and this ADR does not
claim one. Somebody can still cut a tag without running this, exactly as
somebody could still ignore the prose checklist — the difference is that the
question now costs one command instead of an afternoon of `git` archaeology,
and the two counts it prints are ones no human was ever going to reconstruct.

**A new operator command joins the surface.** `test_cli_contract` covers it
like every other: CRLF, a working `--help`, the executable bit in the git
index, and no secret in a documented argument.

**`apg release-reading` works on the day it lands**, without an edit: `bin/apg.sh`
derives its verbs from `bin/` rather than from a list.

**The counts it reads are two of many.** Released migrations and ADRs were
chosen because they are cheap, exact, and move in every release; requirements,
claims and the registry are not read, and adding one later is an edit to one
function. What it prints is not a definition of what a release is.

**Nothing here is asserted about a tag by a test**, and ADR 0209's line stays
where it is. This command is the operator's instrument, not the suite's.

## Alternatives rejected

**A checklist in `docs/operator-guide.md` and nothing else.** This is what
D1424 asked about, and the measurement is against it: five tags, five failures,
and a checklist cannot produce the counts in §4 above. It is kept — as three
questions — but only where the facts already are.

**A test that reads the tags.** Refused twice over: a test runs inside a commit
(ADR 0209), and in two of CI's three jobs there are no tags to read, so the
proof would be green by measuring nothing (D1466).

**A verdict on whether the tag is owed.** §2 and §3 above are the refusal: the
defect and the ordinary between-releases state are the same shape, and a
threshold on that footing would be invented. D1441, earlier in this same
session, is the precedent: a check struck for resting on nothing measured.

**Exiting non-zero when commits have landed since the tag.** It fires on 45 of
147 commits and it is a judgement the command cannot make. A report may not
fail closed.

**Wiring it into `bin/session-01-check.sh`.** The gate runs where the tags are
not, so it would print *cannot be taken* on every CI run. §4 of the Decision.

**Making the command cut the tag.** A tag is an irreversible publication and it
is the operator's `git tag -a`, as it has been for all five. A reading that also
acts is no longer a reading, and the one thing the measurements say clearly is
that the decision is a person's.
