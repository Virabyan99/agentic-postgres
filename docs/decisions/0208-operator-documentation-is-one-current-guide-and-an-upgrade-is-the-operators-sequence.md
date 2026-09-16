# 0208 — Operator documentation is one current guide per release, superseding the per-session set; an upgrade is the operator's sequence, with the checkout's half inside it

- **Status:** Accepted
- **Date:** 2026-09-16
- **Session:** 26 (D1379–D1386)
- **Affects:** `DX-001` (`documented_path`), `DEP-001` (`fresh_host`); no
  requirement text moves.
- **Related:** ADR 0197 and 0207 (what a walk measures and who may walk),
  ADR 0162 (what a bump permits, and what rollback does not mean), ADR 0158
  (the deployed document is the address book), ADR 0155 (a deploy recreates a
  container whose mounted content changed), ADR 0206 (a project's set has its
  own ordering space); D505, D507, D602, D678 (flags and steps lost to retyping
  a guide), D613 (Session 11's guide derived by diff), D1107, D1118, D1282,
  D1371 (steps an upgrade has that no page named), D1351–D1367 (what two cold
  readers could not find).

## Context

Two documents a database product must have did not exist in this repository
on 2026-09-16, and `documented_path` had just closed **`failed`** with
seventeen findings across two walks (ADR 0207, D1351–D1367).

**There was no upgrade guide.** `bin/upgrade.sh --help` describes three verbs
and ends *"To perform an upgrade, run ./deploy.sh --through-session N after
this reports a plan that may proceed."* Every trip since Session 13 has
performed more than that sentence: a render **as the operator** from the
host's own capability manifest (D1371), an ownership repair before it (D1151),
a plan that comes back `BLOCKED` when a manifest moves with the release and is
split into two deploys (D1107), a snapshot that is behind the deployment that
produced it until the next deploy (D1118), and a kit re-exported afterwards
that must **not** be handed to the gate (D1282). Each was measured on a trip
and written into a plan's *Done* paragraph. None was written where an operator
looks.

**The newest operator guide was Session 11's**, and `CURRENT_SESSION` was 25.
The per-session pattern — one guide per session, each *derived from its
predecessor by diff, never retyped* (D613) — produced ten guides for Sessions
2–11 and then produced none for fourteen sessions. In that gap the product
gained the `upgrade` verbs, the fleet inventory, retirement, the backup
timers, the mirror, the kit, the restore, eight rehearsals, a project's own
migration set with its own ordering space, the agent plane opened to a
tenant's tables, `apg dev`, a generated client and Studio. What described
operating them was the session plans' §5 Run 7 *Done* paragraphs, which are
the builder's notebook, excluded from a walk by rule (ADR 0207 §1), and
written for the person who was there.

**`docs/new-team-member.md` ends at the deployment boundary in its own
words** — *"it is the operator guides rather than this page"* — and hands the
reader to a set whose newest member describes a release five outputs versions
and ten migrations ago.

Two decisions had to be taken deliberately rather than by default, because
each has a real alternative and the default had already been taken once, by
omission, for fourteen sessions.

## Decision

### 1. One current operator guide, edited in place, supersedes the per-session set

`docs/operator-guide.md` describes operating **the release in the checkout**,
and it is the only operator guide a reader is sent to. It is derived — by
diff, never retyped — from Session 11's guide, the Run 7 *Done* paragraphs of
the Session 12–25 plans, and the host scripts those trips executed
(`/home/op/s25-*.sh`, `g25-*.sh` on 2026-09-15). Each release's edit to it is
a diff in git history, which is a stronger form of D613's rule than a new file
per session: the diff is against the page the reader last read, not against a
page a builder last wrote.

**The ten per-session guides (`session-02` … `session-11`) stay in the tree,
unedited, indexed as records.** They are not deleted and not merged away:

- `tests/contract/test_repository_contract.py` names four of them as files a
  release must ship, and a product message names `session-07-operator-guide`;
- `dx_record.GUIDE_GLOB` scans them for the commands a walk may name, and
  `test_session12_documented_path.py` exempts them from the argument checks
  *because* they describe their own release — rewriting their flags would
  destroy the record they exist to be;
- every one is cited by number in a divergence row.

`docs/README.md` lists them under a heading that says what they are: the host
sequence *as of* the session named, superseded for anything current.

### 2. The upgrade guide is the operator's, and the checkout's half is a section inside it

`docs/upgrade-guide.md` is the sequence an operator performs on a host to move
a deployment from the release it runs to the release in the checkout, end to
end, including what to do when a step refuses. It lives under *Running a
deployment* in the index. The adopter's half — bringing a fork that owns
`projects/<slug>/` forward to a new release, in a checkout, before any host is
touched — is **§2 of the same page**, not a second page.

The reason is where the irreversible act is. In a checkout, an upgrade is a
`git fetch` and four `--check` commands, every one of which writes nothing and
is undone by `git checkout`. On a host, an upgrade applies migrations that are
fix-forward by construction (ADR 0162 §3: *once a release applies a migration,
that release is the floor*). One page keeps the reader who does the checkout
half from believing it was the whole, and the order of its sections is the
order the two halves must happen in.

### 3. What every command on either page is read from

Every command is copied from the `--help` of the command it invokes, as
printed by the release in the checkout on the day the page was written, and
every sequence is one a trip executed, with the date and the plan's *Done*
paragraph named beside it. Where a step has not been measured on this
deployment the page says so in the step, rather than describing it as if it
had. This is the method the pages were produced by and the rule a later edit
is held to; it is written here so an edit that recalls rather than reads can
be refused on the ADR rather than on taste.

## Consequences

**A reader has one page to open for an upgrade and one for operations**, and
`docs/new-team-member.md`'s last paragraph lands on a section that describes
the release the reader is holding. The walk `documented_path` measures does
not change — it ends where a host begins (ADR 0207 §4) — but `fresh_host`'s
path, which begins there, now has a page.

**The two new pages are outside both documentation scans** (D1383).
`dx_record.DOCUMENT_ROOTS` and `test_session12_documented_path.CURRENT_PATH_DOCUMENTS`
are lists in code, and this session changes no code. The pages are written to
satisfy both checks — every `--through-session` and `--session` at
`CURRENT_SESSION`, every command a file that exists — and adding them to the
two lists is one line each with a test, owed to Stage 4's first code session.
Until then a command named only on these pages reads to a walk as
undocumented, which is the stricter direction (scope-closure §14).

**The per-session guides stop being where a reader is sent, and start being
what a row cites.** Nothing about them changes; what changes is that
`docs/README.md` no longer implies the set is current.

**Editing the current guide is the release's job**, in the same commit as the
bump, the way `apg generate` is (D1238). A release that moves a schema, adds a
migration or adds a unit and does not move the guide's §1 table and the
upgrade guide's release table has shipped an upgrade path that is wrong in
the reassuring direction — the class §7 of `CLAUDE.md` names. No test enforces
that yet; it is named here so the next session that adds one has the ADR to
cite.

**What this does not decide.** Whether `docs/README.md`'s *Running a
deployment* pages (`api-operations`, `backup-operations`, `fleet-operations`,
`recovery-operations`, `node-loss-runbook`) should fold into the operator
guide. They are topic pages with their own measured sections, systemd units
cite two of them by path, and the operator guide hands to them rather than
repeating them. Folding is a later decision, taken if a reader is measured
losing their way between them.

## Alternatives considered

**Continue the per-session set: write fourteen more guides, 12 through 25.**
Rejected on the evidence of the gap itself. The pattern requires a session to
derive a guide from its predecessor on the day it closes, and fourteen
sessions in a row did not; the plans' *Done* paragraphs absorbed the record
because they were written anyway. Fourteen retrospective guides would each be
derived from a plan rather than from a predecessor, which is the retyping D505,
D507 and D602 were about, fourteen times.

**A hybrid: per-session guides for host trips (20, 21, 24, 25) and one topic
page for the rest.** Rejected because it reproduces the reader's problem —
which page is current? — inside the set that exists to answer it. A reader who
did not build this cannot tell which session's guide supersedes which without
reading all of them, which is what the second walk measured (D1364: a required
step present only in a failure table; D1366: an output documented to the byte
and its input in prose).

**Two upgrade pages, one for the operator and one for the adopter.** Rejected
for the reason in Decision 2: the adopter's half is cheap and reversible, the
operator's is neither, and a page that describes only the cheap half is a page
that says the upgrade is done when it is not. The section order on one page is
the ordering rule.

**Fold the upgrade into the operator guide as a section.** Rejected because
the upgrade is the one operation with a release table, a verdict vocabulary
and a rollback boundary of its own, and the operator guide is already the
longest page a reader is sent to. It is a section-length pointer there and a
page here.

**Name the current guide `session-25-operator-guide.md` so the existing scans
catch it.** Rejected: a session-numbered name says *as of Session 25*, which
is the opposite of the claim the page makes, and `test_session12_documented_path`
would exempt it from the argument checks precisely because of the name.
The scans are one line each to widen (D1383) and that is the honest repair.
