# 0207 — A walk is by a reader whose context holds only the release and the task, and the record it writes is read by the product

- **Status:** accepted
- **Date:** 2026-09-14
- **Session:** 25, Run 1 (D1303–D1307, D1312, D1314; and the corrections this
  run measured, D1315–D1327)
- **Related:** ADR 0002 (derive an identity once — the rule the dispatcher and
  the completion script both follow), ADR 0012 (the migrator never fabricates a
  deployed document), ADR 0037 (an installed launcher resolves a release — why
  `apg` is not on PATH), ADR 0045/0089 (what a claim is), ADR 0093 (an operator
  command imports only what the host has), ADR 0163 (three statuses), ADR 0195
  (three outcomes, the third reported), ADR 0197 (the outsider's bring-up: what
  the two claims mean now, and the question it left open), ADR 0198/0201/0206
  (what an adopter owns), ADR 0203/0204/0205 (the three DX surfaces); D119
  (`fresh_host` and `documented_path` are separate claims), D200 (a prefix
  passing for a name), D478 (a claim closed by its author's hands), D600 (a
  `null` that looks measured), D971 (a manifest inside the checkout dirties the
  release), D1122 (a kit is read at a later release than the one that wrote
  it), D1141 (there is no deployed-branch migrator, so the reader is
  version-aware), D1165/D1302 (the root re-entry and the module it never
  reached).

## Context

`DX-001` — *a developer who did not build the primitive completes the
documented path without source edits or undocumented commands* — has been
`not_run` since Session 12 and was answered **no** on 2026-09-10 over seven
source edits (ADR 0197). Stage 3 was supposed to remove the cause. It did:
ADR 0198 gave an adopter a directory of their own, 0201 gave them a capability
manifest, 0206 gave their migration set its own ordering space. So the claim is
walkable again, and Session 25 is where it is walked.

Four things had to be decided before anybody could walk it, and each is a
question the tree could not answer on its own. Every number below was measured
in a rig on 2026-09-14 at `5ab0c4a`; none is carried from the plan's text, and
where a measurement contradicted the plan the measurement is what this ADR
follows.

## Decision

### §1 — Who may walk, and what their context may hold

ADR 0197 left open *"whether an agent's afternoon can ever satisfy a
requirement whose text says 'a developer'"*, on the ground that `DX-001` failed
on its own terms anyway. It no longer fails on its own terms, so the question
is live — and **the only walkers this project can reach are sessions of a
model** (D1307). The operator has sat every session. The executor of this
plan's Runs 1–5 will have edited the README the walk reads (D1314). Session
19's outsider was itself an AI agent. A person who has never seen this
repository is not available, and pretending the operator qualifies is D478's
shape exactly: a claim closed by its author's hands.

**A walker qualifies when its context holds nothing but a clone of the release
and the task statement.** Concretely, and each of these is a thing that can be
checked rather than asserted:

- a `git clone` of the release commit, made inside WSL so modes survive, in a
  directory that is **not** the launch folder — so no `CLAUDE.md` is loaded;
- an empty memory directory, no transcript, no prior conversation;
- `docs/plans/` excluded by the task statement. ADRs and every other page are
  allowed: they are documentation an adopter may read. The plans are the
  builder's notebook and reading them is reading the answers;
- no conversation with the builder during the walk. **Any exchange at all is an
  `undocumented_steps` entry by rule**, which is what makes the rule
  self-enforcing rather than a promise.

`followed_by` stops being a free-text line and becomes a structured member:

```json
"followed_by": {
  "kind": "agent",
  "identity": "<model id, or the person's name>",
  "instructed_by": "<the human who started the session>",
  "context": "<one sentence: what the session was given>"
}
```

The proof asserts the shape and that `context` names the clone and the
statement. A record whose `followed_by` is a string is refused: it is the field
that decides whether the walk counts, and a free-text one cannot be read.

**The residual, named here and in the ledger.** An agent reads faster and skips
less than a person. A clean agent walk is evidence that *the path holds for a
reader who follows it* — it is not evidence that the path is pleasant, or that
a distracted human on a Friday would get through it. A person's walk would be a
second and stronger record, and this decision does not make it unnecessary. It
makes the claim answerable by somebody, which is the alternative to leaving it
unanswerable by anybody.

### §2 — The project default is derived from the verb's own help, not from a list

`bin/apg.sh` holds no list of verbs and that is ADR 0002's decision: a
dispatcher that enumerated them would be a second authority for which commands
exist. A default `--project` has to respect that. It also has to be safe,
because 47 of the 65 verbs do not take the flag and appending it to one of them
breaks a command that worked.

**Measured (rig 25a):** `bin/apg.sh --list` prints **65** verbs, not the 60 the
plan's D1308 asserted. All 65 answer `--help` with exit 0, in **11–77 ms**
(median ≈ 15; `session-01-check` is the 77 ms outlier). **18** name `--project`
as a line-anchored flag; **48** mention the string somewhere, so a loose
`grep -c` over-counts by **30** — almost all of them the session gates'
`--project-a-outputs`. The plan's "37" was neither number (D1315).

So: **the dispatcher reads the verb's own `--help` and matches a line whose
first non-space token is exactly `--project`.** It applies the default only
when `APG_PROJECT` is non-empty, the arguments carry no `--project` in either
spelling, and that match succeeds. It prints one line on stderr every time it
applies it. A value naming no readable file is refused with exit 2 before
`exec`. `--help`, `-h` and `--list` anywhere in the arguments suppress it: a
help request that grew a flag would print a sentence about a file the reader
never mentioned.

**The alternative is refused.** A file in the checkout naming the default
project would be a third operator input to gitignore and D971's shape — a
manifest inside the checkout dirties the release and every deploy refuses. A
kept list of which verbs take the flag would be the second authority ADR 0002
exists to prevent. Reading the verb's help costs 15 ms and cannot go stale,
which is the property the whole surface is built on.

**One verb breaks the rule, and it is fixed rather than exempted** (D1316).
`dr-kit verify --project FILE` answers *unrecognized arguments: --project*,
because `--project` is declared on the `export` subparser only — while
`bin/dr-kit.sh --help` carries a usage continuation line whose first token is
`--project`, so the derivation would match it and break `verify`. This is the
stage plan's own stop condition, met once in 65 verbs. The fix is the one §9
prescribes: **`dr-kit`'s usage text is rewritten so no line begins with
`--project`**, the flag is documented under `export` where it belongs, and
`dr-kit` therefore receives no default at all. A usage block that names a flag
the command does not take is a `DX-002` failure on its own terms, independent
of this session.

Rewriting one usage line is not a guard, so a guard comes with it: a contract
proof asserts that **every verb whose `--help` names `--project` line-anchored
accepts it**, probing the parser rather than trusting the prose. That is the
check that stops the next `dr-kit` from being found by an operator instead.

**The derivation deliberately under-applies, and that is the safe direction**
(D1317). Sixteen `session-NN-check` gates take `--project` in a `case` arm and
do not name it line-anchored in their help, so they get no default. A missed
convenience is a command that behaves exactly as it did yesterday; a wrong
match is a command that stops working. The asymmetry decides the regex.

**Both spellings count as "already carries one"** (D1318). `dev`, `generate`
and `studio` all *refuse* `--project=FILE` and accept `--project FILE`, so the
`=` form is not a spelling the product supports — but recognising too little
would append a second `--project` to an invocation that already has one, and
two wrongs are worse than one. The dispatcher treats `--project` and
`--project=*` alike when asking whether the arguments already carry one, and
appends only the two-word form.

**`apg completion bash` derives the same two facts the same way**, at
completion time: verbs from `--list`, flags from `<verb> --help`, nothing
embedded but the checkout's absolute path. Measured (rig 25b): a verb
completion costs **~175–225 ms** and a flag completion **~21 ms**; `apg d`
yields exactly ten verbs; an unknown verb yields nothing and bash's own path
completion is left alone. The verb completion is slower than the flag one
because `list_verbs` forks `basename` once per script — 65 processes (D1319).
It is not fast, it is correct, and it cannot go stale; making it fast is a
change to the dispatcher's own listing and is not this session's.

### §3 — `DX-001`'s and `DEP-001`'s live proofs are replaced by stricter readings

Four replacements. Each keeps every assertion the old proof made and adds one
the old proof could not make, which is what makes each a strengthening rather
than a rewrite. The node ids do not change, so neither claim is re-dated
(ADR 0089).

**(a) A source edit is decided by PATH, not by basename** (D1304, corrected by
D1322). `OPERATOR_INPUTS` compares `Path(name).name` against five basenames.
It was written in Session 12, six sessions before an adopter had a directory,
and **no record has ever been declared, so it has never run against a real
walk** — §7's question 2 exactly. Measured (rig 25d): a synthetic record of a
walker who followed README's two tenant sections to the letter produces
**7** false source edits, not the 6 the plan predicted; the plan's list omitted
README's own row 4, `contracts/postgrest-openapi.canonical.json`. Basename
comparison cannot even tell the two `manifest.json`s apart: the walker's
`projects/walker/migrations/manifest.json` and the release's
`migrations/manifest.json` reduce to the same string.

`dx_record.source_edits(record, slug)` compares paths: a file is the walker's
own when its path is under `projects/<slug>/` or is one of the five operator
inputs **at the checkout root**. Everything else is a source edit. This is a
widening to the set ADR 0198 defines and **stricter at the same time** — a
basename match that used to pass (`capabilities.yaml` anywhere at all) now
passes only at the two paths the documentation names.

**(b) A command is resolved through the dispatcher on both sides** (D1305,
D1323). `_COMMAND` captures `bin/apg.sh` and stops, so a record listing
`bin/apg.sh no-such-verb` passes the documented-command check — measured, along
with two more nonexistent verbs. And the failure runs the other way too, which
the row did not say: `bin/dev.sh up` is **refused**, because README spells it
`bin/apg.sh dev` and the scan reads only `README.md`, `docs/README.md` and the
session operator guides — **not `docs/new-team-member.md`**, which is the
documented path itself. The proof is wrong in both directions at once.

`dx_record.unnamed_commands(record, documented)` resolves `bin/apg.sh <verb>`
to `bin/<verb>.sh` (and `deploy` to `./deploy.sh`) on both sides before
comparing, so either spelling in the documentation licenses either spelling in
the record, and a verb the documentation never names is unnamed. The documented
set is scanned from `README.md`, `docs/README.md`, `docs/new-team-member.md`,
`docs/second-walk.md` and the operator guides.

**(c) A record names the documents it was walked against** (D1306). The record
gains `documents_read`: `{path: sha256}`. `dx_record.stale_documents(record,
tree)` returns every path whose digest has moved by the time the sweep reads
it, and the proof fails naming them — *the documentation moved after the walk;
walk again or record why*. `bin/dx-record.sh digest` computes them for the
walker so nothing is typed by hand. A walk is a measurement of a document at a
commit, and a record that cannot say which document it measured is D600's null
one level up.

**(d) `fresh_host` reads an older deployed document version-aware — it does not
carry it** (D1312, corrected by D1326). The plan's resolution was to call
`carry_to_current` before the version assertion, on D1122's *migrate, then
validate* rule. **That is not implementable, and the rig says why**: all
sixteen single-step migrators call `require_kind(document, "rendered")`, so
`carry_to_current` refuses **every** deployed document — the v16 kit, the v17
kit, all of them — with *expected a 'rendered' outputs document, got
'deployed'*. `fresh_host`'s declared document must be a deployed one by the
proof's own first assertion. The two requirements are contradictory, and ADR
0012 is why: the migrator never fabricates a deployed document, because that
would republish an observation under a version that never measured it.

The tree already solved this problem seven days ago and the plan did not know
it. `dr_kit.verify_deployed_document` (D1141) reads an archived deployed
document **by version, three ways**: the current version validates against the
full schema; a version between the facility's first and the current one is
checked for what the document is *for*, because a reader takes its identity and
its routes from it and nothing else; a version above the current one, or below
the first, is *a document this release cannot read* — reported as such and
never as *does not validate*.

`DEP-001`'s proof takes that shape. It asserts what the claim is actually about
— the document is a deployed one, it names a host, that host is not the host
`project_a` runs on, and its routes are ready — and it reads the version as the
kit verifier does. A document older than this release does not fail the claim
and does not silently pass it: **the proof reports the third answer and the
claim stays `not_run`** with the version it stopped at as the reason. A refusal
that reads *it describes an older product* would send the operator to redeploy
a host that was fine, which is a premise wrong in the reassuring direction.

### §4 — The walk's success criterion is the workstation path; Studio is read, not opened

The stage plan says the outsider *"adopts the product, adds a table and an
agent capability for it, runs `apg dev`, generates a client and opens Studio,
from the documentation alone"*. **Studio cannot be opened without a
deployment, and the walker has none** (D1303). `bin/studio.sh` requires
`--outputs FILE` naming a deployed document and logs in through the deployment
it names (ADR 0205); `apg dev` is the database alone with no auth service
(ADR 0203); a rendered document's routes are `unavailable` by design. Giving
the walker a deployment means a third project on the host — providers, DNS,
ACME, a retirement — which is `fresh_host`'s shape, not `documented_path`'s,
and D119 keeps the two apart deliberately so each can be answered on its own
terms.

So the success criterion is what `docs/new-team-member.md`'s *What "done" looks
like* will say once Run 4 rewrites it: the toolchain, a render, a table under
`projects/<slug>/`, a capability for it, `apg dev up` applying the set,
`apg generate`, the gate green — **plus Studio read, not opened**: `apg studio
--help` exits 0, and a launch against the rendered document is refused with a
message naming the deploy as what is missing. The walker records that refusal
verbatim; an ADR 0195 answer that arrives as a clear sentence is a documented
path working, not failing.

Opening Studio against a deployment stays available as an optional operator
item on Run 7's sheet, taken only if the operator chooses to deploy the
walker's project. The record then gains a `studio` member. **The claim is
unchanged either way**, which is the point: the documented path an adopter
walks alone ends where a host begins.

## Consequences

- `documented_path` becomes answerable. It is answered by Run 6's walk and by
  nothing else; a walk by the operator or by this plan's executor does not
  count, and the ledger says so.
- `DX-001`'s live proof stops being a proof nobody has run. It gains four
  readings it did not have and keeps every assertion it had, and its first
  honest walk will fail on a real defect rather than on the walker's first
  documented file.
- `fresh_host` stops depending on a carry that cannot happen. It can now be
  decided from an older document, or reported as undecidable with the version
  named — and either is better than the refusal it would have produced.
- `bin/apg.sh` gains its first behaviour of its own. The header's *"It rewrites
  nothing and moves nothing"* is amended to say what it now adds, when, and how
  it announces it. Every existing dispatcher proof stays green.
- `dr-kit`'s usage text is corrected and a guard is added, so the next verb
  whose prose outruns its parser is found by a test rather than by an operator
  with `APG_PROJECT` set.
- Nothing here is hand-entered into the evidence document. A claim's verdict is
  computed from registry node ids and JUnit results; this ADR changes what the
  proofs read, not what the document says.
