# 0209 — A release is held to its own documentation by a test, not by a habit

- **Status:** Accepted
- **Date:** 2026-09-16
- **Session:** 27, Run 1 (D1388)
- **Affects:** no requirement id moves. `DX-001` and `DEP-001` are the claims
  whose subject this touches; neither changes.
- **Related:** ADR 0208 (one current operator guide, edited in place each
  release, with the gap this ADR closes named in its *Consequences*), ADR 0162
  (what a version bump promises), ADR 0207 (a walk measures a document at a
  commit), D1033 (the same failure at `1.0.0`, repaired by cutting `1.0.1`),
  D623 (a status line nobody read, stale for eight sessions), D936 (a version
  quoted in the README through two bumps), D1311 (a tag is the promise the
  compatibility sentence made when it was cut), D1379–D1387 (Session 26's
  rows).

## Context

**The failure this ADR exists for happened twice, seven sessions apart, and
the second time it was committed by the session that had read the first.**

D1033, Session 19: *"A user adopting a product at 1.0.0 checks out the version
tag. The `1.0.0` tag is `054f54e`, and all four documented-path repairs land
after it."* The repair was a patch release cut from a repaired `main`, and the
row's own words were **"Not a documentation fix."**

D1388, Session 27: measured 2026-09-16, `git ls-tree -r --name-only 1.6.0 --
docs/` lists the ten `session-NN-operator-guide.md` files and neither
`docs/upgrade-guide.md` nor `docs/operator-guide.md`. Both land in `c5ad14d`,
one commit past the tag. An outside agent upgrading a real application to
`1.6.0` recorded the consequence in its own words: *an operator who does what
the version number tells them gets a product whose upgrade procedure is not in
it.*

**Nothing could have caught either one.** The repository has guards for the
inverse: `test_documentation_index` holds the README's `template_version` and
its `Session N implemented` line against the constants, holds the index
complete in both directions, and refuses a `--through-session` above what the
release implements. Every one of those answers *does the documentation agree
with the release it is in?* None answers *is the documentation that describes
this release in it at all?*

ADR 0208 already named the gap and left it open: *"Editing the current guide is
the release's job, in the same commit as the bump … No test enforces that yet;
it is named here so the next session that adds one has the ADR to cite."* The
next session is this one.

**What is enforceable and what is not.** A test runs inside a commit. It cannot
know that a tag will later be cut, or on which commit, so *the tag carries the
pages* is not a property a test can assert. What a test can assert is that the
pages describing the release are present, and that they describe **this**
release rather than an earlier one — which is the half that actually decays,
and the half that makes a tag on any commit carry a true page.

## Decision

### 1. The pages that describe a release are part of the release

`docs/operator-guide.md` and `docs/upgrade-guide.md` are release artefacts in
the sense `README.md` already is: a commit that moves `VERSION` and does not
move them is a commit whose documentation describes a release that no longer
exists. They are held by test, in `tests/contract/test_documentation_index.py`,
beside the guards that already hold the README:

- **Both pages exist.** An absent page is the failure D1388 records, and it is
  the cheapest possible assertion.
- **Both name the release the tree carries.** Each states the version it
  describes, and the stated version equals `template_version()` — read from the
  function, never typed, which is what `test_the_readme_states_the_template_version_the_release_carries`
  already does for the README (D936).
- **The upgrade guide's release table has a row for the current release.** The
  table is what an operator reads to find out what their hop crosses, and a
  release missing from it is a hop nobody described.
- **Both join the two documentation scans** — `dx_record.DOCUMENT_ROOTS` and
  `test_session12_documented_path.CURRENT_PATH_DOCUMENTS` — so every command
  they name must exist and be executable, every `--session` and
  `--through-session` must be the release's, and no step may tell a reader to
  edit a tracked file. They were outside both (D1383), which is why eighteen
  defects in them were found by a reader rather than by the suite.

### 2. What is NOT asserted, and why it is left to a person

**That a tag exists, or points anywhere in particular.** A test cannot see the
future, and a test that read `git tag --points-at HEAD` would fail on every
commit that is not a release, which is almost all of them. The tag stays a
human act, and the rule that governs it is D1311's: a tag is the promise the
compatibility sentence beside it made at the moment it was cut.

**What this ADR changes about that act** is that the promise is now checkable
before it is made. A release commit whose pages are absent, or describe an
earlier version, or name a command that does not exist, fails the gate — so a
tag cut on a green commit carries pages that are at least about the release it
names. That is weaker than *the tag carries the right pages* and it is the
strongest thing a test can say.

### 3. The rule a session applies

**A commit that moves `VERSION` moves the two pages' release statements in the
same commit**, the way it already moves the README's status line and the
generated client's `templateVersion` (D1238). This is ADR 0208's sentence,
promoted from a consequence to a decision with a test behind it.

## Consequences

**The failure that happened twice cannot happen silently a third time.** It can
still happen deliberately — somebody can cut a tag on a commit where the pages
are stale in a way no assertion covers, or forget to cut one at all — but the
class D1033 and D1388 share, *documentation that describes a release and is not
in it*, is now a red gate rather than a reader's discovery.

**Two pages join the scans, and the scans get stricter for everybody.** A
command named only in the operator guide now has to exist and be executable.
This is the direction the project already chose for the new-team-member guide
in D1323, for the same reason: the two halves of one claim were reading
different documents.

**A release's cost goes up by a few lines.** Every bump now edits four things
rather than three: `VERSION`, the constant's paragraph, the README's status
line, and the two pages' release statements. That is the intended cost, and it
is smaller than the one it replaces.

**What this does not make true.** A page can name the right version and still
be wrong about everything else, which is what the eighteen findings in
`stage-3-findings.md` are. No test reads prose for truth. The instrument for
that is a cold reader (ADR 0207 for the adopter's path, and nothing yet for the
operator's), and this ADR does not pretend to replace it.

## Alternatives considered

**Do nothing; rely on ADR 0208's stated consequence.** Rejected because that is
exactly what was done. ADR 0208 wrote the rule down four weeks after D1033
wrote a version of it down, and the release shipped without the pages anyway.
A rule that has been written twice and broken twice is a rule that needs a
reader other than the person applying it.

**Assert the tag.** A test that requires `git tag --points-at HEAD` on a commit
that moves `VERSION` would come closest to the real property. Rejected: the tag
is cut after CI is green, so a test demanding it at the moment CI runs demands
something that cannot exist yet. It would either be vacuous or would force the
tag before its own evidence, which inverts D1311.

**A CI step that refuses a tag push whose tree lacks the pages.** Rejected for
this session and worth revisiting: it is a second definition of passing living
outside `bin/session-01-check.sh`, which the workflow's own header says it
deliberately does not maintain. If the property is worth enforcing at tag time,
it belongs in the gate with everything else and needs a way to run there.

**A release checklist in the plan template.** Rejected as the primary
mechanism, for D1033's reason: the checklist existed in prose in ADR 0208 and
the session that wrote it did not follow it. Kept as a secondary — Session 27's
Run 6 carries the four-item list — because a test that fires at the end is
cheaper to satisfy if a human has already done the thing.

**Hold the pages to the release by content rather than by a stated version** —
for instance asserting the operator guide's migration count equals the release
lock's. Rejected as over-fitting: it would break on every release that adds a
migration for a reason unrelated to the page being wrong, and the page states
plenty of numbers whose drift matters less than the version does. The version
is the one number that makes every other number on the page readable.
