# Session 25 — Hardening, the second walk, and the Stage 3 release

**Status:** **PLANNED 2026-09-14** at `bb93a53`, Session 24's close, on `main`.
No run has started. §1 is D1303–D1314 (planning rows, each read from the tree
at `bb93a53` today or measured in a rig today); the runs add theirs below the
planning rows, each run's numbers named in its Done paragraph. **Next free
after this table: D1328.** ADR **0207** is this session's (written in Run 1,
and indexed);
next free after it 0208.
**Brief:** `docs/plans/stage-3-plan.md` §5 *Session 25 — Hardening, the second
walk, and the Stage 3 release* whole (Builds / Already true / Must not /
Measures / Closes), its rows D1065 (the `apg` project-context default and
completion are one run here, not a session), D1074 (the closing review of the
three surfaces against §8, each building session having shipped its own
negative tests), D1081 (Session 18 Run 5's shape, plus the Stage 4
recommendation, the version read from `upgrade plan` and never chosen), D1080
(the spec's third exit criterion IS `documented_path`); §4's caution (*the
second walk must be by somebody who did not build Session 20, and the record
must show zero source edits — not a shorter list*); §7's rule for
`documented_path` (*Session 25's walk with no edit; anything else keeps it
`not_run` and says why*); §8 whole (the review's checklist); §9's failure mode
(*a client that becomes an authority*); §10's carried items. Plus everything
Session 24 left: `docs/plans/session-24-implementation-plan.md` §10 and its
Run 8 Done, `docs/scope-closure.md` §13, and `CLAUDE.md` §2's *WHAT IT LEAVES*
(the kit re-export, D1282; `honest_readers` recorded and not repaired, D1302;
D860's rotation not performed).
**Shape:** eight runs on a `session-25` branch, CI green on every commit that
changes code. Runs 1–5 offline and the builder's; **Run 6 is the second walk
and is NOT the builder's** — a fresh session that holds nothing but a clone
and a task statement (ADR 0207) walks the documentation while the executor of
this plan does nothing but prepare the clone and read the record afterwards;
**Run 7 is the host trip**, one sweep; Run 8 is the close, the tag and the
decision report filled from the evidence document.
**Product version at close:** `CURRENT_SESSION` 25; `template_version`
proposed **`1.6.0`** — one new operator verb (`apg completion`), one new
operator verb over a record (`apg dx-record`), one environment variable read
by the dispatcher (`APG_PROJECT`), one new optional generated document per
project (`projects/<slug>/docs/mcp-tool-catalog.md`); **no manifest, outputs,
capability, lock, migration or secret schema moves** (ADR 0162: a minor;
confirmed by Run 7's `upgrade plan` on the host, and a `major` there is §9's
stop). **The Stage 3 release is ONE tag, `1.6.0`, on the commit both gates
measured** (D1311) — 1.3.0, 1.4.0 and 1.5.0 were deployed and never tagged,
and are not retro-tagged.
**Written for whoever picks this up cold, and it will be a different model
than the one that planned it.** Every path is exact. Every third-party or
tree claim below is either measured today (§1 says where) or marked as the
measurement Run 1 owes — never assumed. Read `CLAUDE.md` §1 in the launch
folder before the first command, then this plan's §1, then the appendix. If a
step here and the tree disagree, **the tree wins and the disagreement is a
divergence row**, never a silent reconciliation. **Read §1 before Run 1**:
four of the stage plan's sentences about this session are wrong or unmeasured
(D1303, D1304, D1308, D1312), and the design below follows the measurements.

---

## 0. Where the session starts

Session 24 shipped `apg studio` (ADR 0205) and migration 0032, Session 24's
Run 8 shipped ADR 0206, and **one trip paid three sessions**:
`evidence/session-22.json` (118 claims), `session-23.json` (120) and
`session-24.json` (122) each `status: not_run` on the same nine claims, exit
5 — D686's contract, not a failure. **Both projects are at release `bd38ebb`,
template 1.5.0, `deployed_through_session` 24, doctor 10 ok / 0 problem each.**
The nine standing `not_run`: the five D478 names, `fresh_host`,
`documented_path`, `replacement_host_restore` (by decision, D1028) and
`honest_readers` (D1302, a finding the plan predicted).

**What Stage 3 built, measured at `bb93a53`.** A tenant extension point
(`projects/<slug>/`, ADR 0198, 0206), an agent plane opened to a tenant's
domain (ADR 0200, 0201), `apg dev` (ADR 0203), `apg generate` (ADR 0204),
`apg studio` (ADR 0205). 213 requirements, 122 claims, 206 ADRs, D1–D1302,
8 declared offline claims, 32 released migrations. `bin/apg.sh` (161 lines)
is a dispatcher with **no list of verbs** (ADR 0002; `script_for` resolves
`bin/<verb>.sh` by construction, `deploy` named once with its reason), `exec`s
the verb, adds no option, and is deliberately not on PATH. **60 verbs
resolve today** (`bin/apg.sh --list`); 37 of them name `--project` in their
`--help`, and every one of the 60 answers `--help` with exit 0 in 12–17 ms
(rig 25a, today — the numbers in D1308).

**What an outsider's walk is today, measured.** `DX-001` (*a developer who did
not build the primitive completes the documented path without source edits
or undocumented commands*) has one live proof,
`tests/deployment/test_session12_reuse.py::test_a_developer_who_did_not_build_this_completed_the_documented_path`,
marked `live_host` and gated on `APG_DX_RECORD_FILE`, so it runs in the HOST
sweep and nowhere else. It reads a JSON record with seven fields
(`followed_by`, `completed_at`, `release`, `commands_run`, `files_edited`,
`undocumented_steps`, `reached_success_criterion`) and refuses a false one
three ways — but its notion of a source edit predates ADR 0198 (D1304), its
notion of a documented command stops at the dispatcher (D1305), and nothing
binds the record to the documentation it was walked against (D1306). The
documented path itself is `README.md` and `docs/new-team-member.md`; the
latter still labels step 14 *future session (10)* and ends *"You do not have a
running database. That is Session 3"* (D1313). ADR 0197 answered the claim
"no" on 2026-09-10 over seven source edits; two were gone the same session
and the remaining five are exactly what Sessions 20 and 21 built. Nobody has
walked the path since. **Who may walk it** — an agent or a person — is the
question ADR 0197 deliberately left open, and this session must answer it
before the walk (D1307, ADR 0207), because the only walkers available are
sessions of a model.

**What the release machinery is.** Session 18 Run 5's shape, executed once:
the bump in one commit (`CURRENT_SESSION`, `VERSION` with ADR 0162's pricing
in the constant's comment, `docs/product-contract.md` §7's sentence), the
requirements and claims, `bin/session-NN-check.sh` derived by diff from the
newest, `docs/scope-closure.md` re-audited row by row and its §1 **counted,
not recalled** (D1194), and a decision report written with its numbers marked
*filled at the trip's close* (D992) and filled from the evidence document —
never before it. Then the trip, the three halves, the merge, and the tag on
the commit both gates measured (`git tag -n1`: `1.0.0` and `1.0.1` only,
D1311). Every bump since 23 owes a client regeneration in the same commit
(D1238).

**What this session builds, in one paragraph.** (1) **`APG_PROJECT`** — a
default project manifest for the dispatcher, applied by `bin/apg.sh` only
when the verb's own `--help` names `--project` and the arguments carry none,
announced on stderr in one sentence each time it is applied, refused with
exit 2 before `exec` when it names no readable file (D1308); and **`apg
completion bash`**, a verb that prints a completion script which itself
derives verbs from `--list` and flags from `<verb> --help` at completion
time — nothing kept, nothing installed. (2) **The closing review**: a
hardening matrix (`tests/security/test_dx_surfaces_hardening.py`,
`HARDENING_MATRIX`: every §8 invariant × the three surfaces → the node id
that proves it), the empty cells filled with new proofs, one mutation per
cell, and the D1302 repair (`_as_checkout_owner` lifted to
`tests/fixtures/checkout_owner.py`, the atomicity proof re-entering as the
owner under root). (3) **The walk's instrument**: `src/agentic_postgres/dx_record.py`
(pure logic over a record and a tree: source edits by PATH with the walker's
own `projects/<slug>/` excluded, commands resolved through the dispatcher to
the verb, the documents' digests compared), `bin/dx-record.sh check --record
FILE` as a verb so a walker can read their own record's verdict, the live
proof rewritten over it (stricter, ADR 0207), `fresh_host`'s proof carrying
the declared document to the current outputs version first (D1312, the D1122
rule). (4) **Documentation converged**: README's *Local bootstrap*,
*Rendering a project*, *Adding your own tables* and *Giving an agent your
tables* re-ordered into the path an adopter walks; `docs/new-team-member.md`
re-derived by diff with no *future session* label left for a session this
release implements (D1313) and a *done* section that names the tenant path;
`docs/second-walk.md` (the record's format, the task statement a walker is
handed, and what may not be in it); the example project's tool catalog
rendered by `render-mcp-catalog.py --project` and drift-checked. (5) **The
bump**: 25, `1.6.0`, seven requirements, four claims, `bin/session-25-check.sh`
derived by diff from 24's, its modes module (and D1280's repair in 23's), the
ledger, the report's skeleton. (6) **The second walk** by a fresh session
(Run 6). (7) **The trip**: deploy through 25 on both projects, three
`upgrade plan` readings, the kit re-export (D1282's obligation, taken this
time, with `--kit-dir` still on `kit-2026-09-11`), ONE sweep with
`--dx-record-file` and — if the operator locates it — `--fresh-host-outputs`,
the three halves, the merge, `evidence/session-25.json`. (8) **The close**:
the tag, `docs/stage-4-decision-report.md` filled from the document,
`CLAUDE.md` §2, memory.

**What it does not build, by decision** (§1): a single `apg` binary or an
install onto PATH (D1065, ADR 0037); a Python client (D1205 stands — priced,
not built, and §10 says so again); a retention migration for `agent_audit`
(D1255: the counts are re-read on the trip and the decision stays the
operator's); the `/admin/audit` filters (D1248); a Studio step inside the
walk's success criterion (D1303: Studio targets a deployment and the walker
has none); a walk by the operator or by this plan's executor (D1314: both
built it); a rotation performed by a run (D860: an operator's irreversible
sequence, offered on the sheet as optional, never performed by a test); a
retro-tag of 1.3.0–1.5.0 (D1311); a change to `documented_path`'s mode
(it stays a host claim dated to Session 12 — moving it would re-date a
Session 12 guarantee, ADR 0089).

**Read before touching anything:** ADR 0002 (derive an identity once — the
rule the dispatcher and the completion script both follow), 0014 (the
session is derived), 0037 (an installed launcher resolves a release — why
`apg` is not on PATH), 0045/0089 (what a claim is; a claim is built from its
own session's requirement ids), 0093 (an operator command imports only what
the host has), 0162 (what a bump permits; rollback is three operations),
0163 (three statuses), 0195 (three outcomes, the third reported), 0197 (the
outsider's bring-up: what the two claims mean now), 0198/0201/0206 (what an
adopter owns), 0202 (an offline claim is declared), 0203/0204/0205 (the three
surfaces under review); D105 (nothing prints a token), D119 (`fresh_host`
and `documented_path` are separate), D478 (a claim closed by its author's
hands), D505/D507/D678/D693/D703 (a gate or a guide is derived by diff and
its printed prose is read line by line), D686 (exit 5 with the document
written), D860 (a blocker removed is not a proof obtained), D972 (never
redirect a sudo deploy), D1014/D1188 (a new verb is in `SHELL_COMMANDS` and
`git add`ed first), D1116 (a commit message is not evidence of its diff),
D1122 (migrate, then validate), D1134 (`carry_to_current`), D1165/D1302 (the
root re-entry and the module it never reached), D1194 (counted, not
recalled), D1199 (a gate's last lines), D1238 (a bump owes a regeneration),
D1240/D1242 (collected, and by which sweep), D1244 (one sweep, several
sessions), D1280 (three stale guards in the gate-modes family), D1282 (the
kit's version gap IS the claim), D1283 (the writer accepts a host half for
an earlier session).

---
## 1. The divergence table

Six columns, next free number after this table **D1328**. Rows D1303–D1314
were read from the tree or measured in a rig on 2026-09-14 at `bb93a53`. The
runs add theirs below them as they go, each run's numbers named in its Done
paragraph.

| # | Said | Repository does | This session | Why | ADR |
|---|---|---|---|---|---|
| **D1303** | Stage plan §5 Session 25: the outsider *"adopts the product, adds a table and an agent capability for it, runs `apg dev`, generates a client **and opens Studio**, from the documentation alone"*. | **Studio cannot be opened without a deployment, and the walker has none.** `bin/studio.sh` requires `--outputs FILE` naming a DEPLOYED document and logs in through `POST /auth/login` on the deployment it names (ADR 0205); `apg dev` is the database alone with no auth service (ADR 0203); the offline Studio rig (`test_studio_runtime.py`: a dev cluster, the auth app, PostgREST, Traefik) is a rig this checkout builds, not a documented path. A rendered document's routes are `unavailable` by design, so `apg studio` against it can only refuse. Giving the walker a deployment is a third project on the host (Session 17's gamma: providers, DNS, ACME, a retirement) — `fresh_host`'s shape, not `documented_path`'s, and D119 keeps the two apart. | **The walk's success criterion is the workstation path** — what `docs/new-team-member.md`'s *What "done" looks like* says once Run 4 rewrites it: the toolchain, a render, a table under `projects/<slug>/`, a capability for it, `apg dev up` applying the set, `apg generate`, the gate green — plus **Studio read, not opened**: `apg studio --help` exits 0 and a launch against the rendered document is REFUSED with a message naming the deploy as what is missing (an ADR 0195 answer the walker records verbatim). Opening Studio against the walker's own deployment is an OPTIONAL sheet item in Run 7, taken only if the operator chooses to deploy the walker's project as a third project; the record then gains a `studio` member, and the claim is unchanged either way. | A walk whose success criterion needs a host would make `documented_path` depend on `fresh_host`, which ADR 0197 and D119 separated so each could be answered on its own terms. The stage plan's sentence describes the whole DX layer; the claim's text describes the documented path, and the path an adopter walks alone ends where a host begins. | 0207 |
| **D1304** | `test_session12_reuse.py::OPERATOR_INPUTS` (`project.yaml`, `capabilities.yaml`, `host.yaml`, `project.beta.yaml`, `project.alpha.yaml`): *"the operator inputs a reader legitimately creates and edits. Anything else they had to edit is a source edit"*, compared by **basename**. | **A walker who follows README's *Adding your own tables* FAILS the proof as written.** The path tells them to create `projects/<slug>/migrations/manifest.json`, `templates/0001-*.sql`, `released.lock.json`, `contracts/postgrest-api-surface.yaml`, `capabilities.yaml`, `contracts/mcp-capabilities.canonical.json`, `evaluation-cases.yaml`; of those basenames only `capabilities.yaml` is in the set, and by coincidence. Rig 25d (Run 1) counts it: a synthetic record of the tenant path lists **6** false source edits. The set was written in Session 12, six sessions before ADR 0198 gave an adopter a directory of their own, and no proof has run it since because no record has ever been declared. | **`dx_record.source_edits(record, walker_slug)` compares PATHS**: a file is the walker's own when its path is under `projects/<walker_slug>/` (the slug is a record field, `project_slug`) or is one of the five operator inputs at the checkout root; everything else is a source edit — so `migrations/manifest.json` (the release's) is still an edit and `projects/<slug>/migrations/manifest.json` is not. Written in `src/`, called by the live proof and by `bin/dx-record.sh`, proved offline with a synthetic record in each direction. **A widening to the set ADR 0198 defines, authorised by ADR 0207, and stricter at the same time** (a basename match that used to pass — `capabilities.yaml` anywhere — now passes only at the two paths the documentation names). | §7 question 2: this proof has never run in any environment since the thing it measures changed. Its definition of an edit was correct for the product it was written against and is false for the product ADR 0198 made; left alone it would have failed the first honest walk on the first file the documentation told the walker to create, and the failure would have read as the walker's. | 0207 |
| **D1305** | The same proof: *"every command they ran must be one the documentation names"* — `_COMMAND` captures `./deploy.sh` and `bin/<name>.(sh|py)`. | **It captures `bin/apg.sh` and stops.** `bin/apg.sh dev up` and `bin/apg.sh no-such-verb` both reduce to `bin/apg.sh`, which README names, so a record listing any verb at all passes the documented-command check. The documentation an adopter reads writes commands as `bin/apg.sh <verb>` in 21 places (`grep -c "bin/apg.sh [a-z]" README.md docs/new-team-member.md`) and as `bin/<verb>.sh` elsewhere; the two spellings name one script. | `dx_record.unnamed_commands(record, documented)` resolves `bin/apg.sh <verb>` to `bin/<verb>.sh` (and `deploy` to `./deploy.sh`) BEFORE comparing, on both sides, so either spelling in the docs licenses either spelling in the record and a verb the docs never name is unnamed. The documented set is scanned from `README.md`, `docs/README.md`, `docs/new-team-member.md`, `docs/second-walk.md` and the operator guides. **Stricter; ADR 0207 authorises the replacement.** | A check that reads the front door and not the room behind it is D200's shape (a prefix passing for a name). The dispatcher exists so that a verb IS a script; the proof has to see through it the same way. | 0207 |
| **D1306** | The record carries `release` and the proof reads the field's presence only; nothing ties the record to the documentation the walker read. | **A record can be walked against one README and reported against another**, and a docs-only commit between the walk and the sweep is exactly what a walk that finds a defect produces. `release` is a self-report; the sweep runs in the release checkout and could compare, but does not. | The record gains **`documents_read`**: `{path: sha256}` for every document the walker read (the task statement names the minimum: `README.md`, `docs/README.md`, `docs/new-team-member.md`, `docs/second-walk.md`). `dx_record.stale_documents(record, tree)` returns every path whose digest at the sweep differs; the proof fails naming them — *the documentation moved after the walk; walk again or record why*. `bin/dx-record.sh check` computes the digests for the walker (one command, documented) so nothing is typed by hand. | ADR 0202's rule one level over: each half names what it measured. A walk is a measurement of a document at a commit, and a record that cannot say which document it measured is D600's null. | 0207 |
| **D1307** | ADR 0197: *"Whether an agent's afternoon can ever satisfy a requirement whose text says 'a developer' is a real question … deliberately left open … If the extension point lands in Stage 3 and a second bring-up needs no source edits, the question becomes live and gets its own decision then."* | **It is live, and the only walkers available are sessions of a model.** The operator has sat every session; the executor of this plan builds Runs 1–5; the outsider of 2026-09-06 was an AI agent (ADR 0197 says so). A person who has never seen the repository is not available to this project, and pretending the operator qualifies is D478's shape (a claim closed by its author's hands). | **ADR 0207 decides**: a walker qualifies when its context holds nothing but a clone of the release and the task statement in `docs/second-walk.md` — no launch-folder `CLAUDE.md`, no memory directory, no transcript, no `docs/plans/` (excluded by the statement; ADRs and every other page allowed), no conversation with the builder during the walk. `followed_by` becomes a structured member: `{"kind": "agent"\|"person", "identity": "<model id or name>", "instructed_by": "<the human who started it>", "context": "<one sentence: what the session was given>"}`, and the proof asserts the shape and that `context` names the clone and the statement. **The residual is named in the ADR and in the ledger**: an agent reads faster and skips less than a person, so a clean agent walk is evidence the path holds for a reader who follows it, not that it is pleasant; a person's walk would be a second, stronger record, and the claim's status does not depend on it. | The requirement's word is *developer*; the guarantee it names is *without source edits or undocumented commands*, which is a property of the path and is measurable by any reader who did not build it. Leaving the question open a second time would leave the claim unclosable by anybody this project can reach. | 0207 |
| **D1308** | Stage plan D1065: *"a default project context (`--project KEY` is passed everywhere), shell completion"* — *"one run inside Session 25, beside the documentation that describes them"*; and `bin/apg.sh`'s own rule that it holds no list of verbs (ADR 0002). | **Measured today, rig 25a, at `bb93a53`.** `bin/apg.sh --list` prints **60** verbs. `<verb> --help` exits **0 for all 60** and costs **12–17 ms** each (bash) — `doctor` 15, `generate` 12, `dev` 14, `studio` 14, `migrate` 15, `deploy` 15. **37** name `--project` in that text; **23** do not (`apg-diag`, `app-contract`, `auth-admin`, `backup`, `compose`, `database-access`, `docker-firewall`, `edge`, `lock-dev-deps`, `lock-versions`, `provision-host`, `rehearse`, `rotate-secret`, `rotate-signing-key`, `session-01-check`, `smoke-test`, `storage-admin`, and six more). A default appended to one of those 23 would be refused by the verb with exit 2 — so the dispatcher must know which verbs take it, and a kept list is what ADR 0002 refuses. | **`APG_PROJECT` is applied by DERIVATION, not by a list**: when the variable is set and the verb's arguments carry no `--project`, the dispatcher runs `<script> --help` and appends `--project "$APG_PROJECT"` only if that text names `--project` as a flag (a line-anchored match on `--project`, measured against all 60 in Run 1); it prints ONE stderr line, `apg: --project <path> (from APG_PROJECT)`, every time it applies it; a value that is not a readable file is exit 2 before `exec`; an explicit `--project` anywhere in the arguments wins and nothing is printed. `--help` of the verb itself is never rewritten. The completion script (`apg completion bash`) derives the same two facts the same way at completion time: verbs from `--list`, flags from `--help`. | A default that is silent is a default that deploys the wrong project one day; a default kept in a list is a second authority for which verbs exist (the dispatcher's own header says why). Reading the verb's help costs 15 ms and cannot go stale, which is the property the whole surface is built on. The alternative — a file in the checkout naming the project — is refused in ADR 0207 §2: it is a third operator input to gitignore, and D971's shape (a manifest inside the checkout dirties the release). | 0207 |
| **D1309** | `docs/plans/stage-3-plan.md` §5 Session 25 *Builds*: *"the generated references rendered for a tenant's surface"*. | **`bin/render-mcp-catalog.py` reads the RELEASE contract only** (`contracts/snapshots/mcp/mcp-capabilities.canonical.json`; the word *project* occurs once in its docstring and nowhere in its arguments), writes `docs/mcp-tool-catalog.md`, and the gate drift-checks that one file. `docs/api-surface.md` is prose, not generated. A tenant's tools (`projects/example/contracts/mcp-capabilities.canonical.json`, 7 tools) appear in no rendered document. | `render-mcp-catalog.py` gains `--project FILE` writing `projects/<slug>/docs/mcp-tool-catalog.md` from the project's compiled contract with the release's rows marked as the release's; the example project's catalog is committed, `--check --project project.example.yaml` joins the gate's step 7, and README's *Giving an agent your tables* names the command as the last step. Nothing for `api-surface.md`: it is prose, and the project's reviewed surface file is its own reference. | The stage plan's sentence priced the documentation; the tree has one renderer with one input, so the sentence is one flag and one output path — measured in Run 1 (rig 25e) rather than assumed to be free. | — |
| **D1310** | `CLAUDE.md` §9 and D1302: *"Repair: lift `_as_checkout_owner` somewhere both import. It cannot be shown offline, so it costs a second host sweep."* | **It can be shown offline as root in a container**, which is what the gate's static claim proofs run as. Rig 25c (Run 1): the pinned Python image with the checkout mounted, `pytest tests/contract/test_render_atomicity.py -k owner_is_resolved_upward` as uid 0 → `SKIPPED` (the reproduction), and the same command as the checkout's uid → `PASSED` (the control). `_as_checkout_owner()` in `test_honest_readers.py:121` already builds the `sudo -u <owner>` prefix and the D1165 re-entry shape (`[*_as_checkout_owner(), python, script, …]`); `test_render_atomicity.py:396` carries the bare `if os.geteuid() == 0: pytest.skip(...)` and never imports it. | **`tests/fixtures/checkout_owner.py`** (beside `outputs_chain.py` and `rendered_fixtures.py`, the existing helper home) exports `as_checkout_owner()` and `reenter_as_owner(argv)`; `test_honest_readers.py` imports it (its own copy removed, the moved TEXT grepped, D1187); the atomicity proof re-enters as the owner under root the way D1165's does, with the precondition constructed and restored by the proof. Rig 25c re-run after the repair: root → `PASSED`. The claim then needs ONE sweep, Run 7's — **not a second one**. | The row's own words said *offline cannot show it*, and a container running as root is the identity in question; the cheap half was never tried. §7 question 3 — whose identity, through which tool — answered by running under that identity before the trip rather than on it. | — |
| **D1311** | Session 18 Run 6: *"`1.0.0` tagged on the release both gates measured"*; stage plan §5: Session 25 is *"the Stage 3 release"*. | **`git tag` lists `1.0.0` and `1.0.1` only.** Sessions 20–24 moved `VERSION` through 1.1.0 (or whatever 20 and 21 chose), 1.3.0, 1.4.0, 1.5.0 and deployed each; none was tagged. The README's *Adopt `1.5.0`* names a version no tag names. | **One tag, `1.6.0`, on the `main` commit both Run 7 gates measured**, after the merge and after `evidence/session-25.json` exists — Session 18's order. 1.3.0–1.5.0 are NOT retro-tagged: a tag is a promise the compatibility sentence describes at the moment it is made, and dating one to a commit nobody tagged then is a record that looks measured and was not. README's *Adopt* paragraph says which versions were releases without tags, once. | Stage 2 closed on a tag and Stage 3 closes on one; the intermediate numbers were session closes, not stage closes, and the ledger records them as such. | 0162 |
| **D1312** | ADR 0197: `fresh_host` needs *"Nothing but a file. An empty host reached a working deployment on 2026-09-08; supplying its `outputs.json` as `APG_FRESH_HOST_OUTPUTS` is the operator's mechanical step"*. | **The proof refuses that file by construction.** `test_a_project_deployed_on_an_empty_host_is_a_working_deployment` asserts `fresh["schema_version"] == output_migrations.CURRENT_VERSION` — the outsider deployed **1.0.0/1.0.1 (outputs v16)** and the tree renders **v18**, so the declared document fails with *"it describes an older product"* before any route is read. D1122 met the same shape in the DR kit (a v16 kit against a v17 checkout) and decided *migrate, then validate*; `carry_to_current` (D1134) is the helper that does it. Nobody has applied that decision to this proof because nobody has ever declared the file. And **where the file is is unknown to the tree**: `FINDINGS.md` in the launch folder describes the host and names no path; the operator holds it or does not. | The proof carries the declared document with `carry_to_current` BEFORE the version assertion and asserts the carried version (a document the migrators cannot carry is the reported third answer, naming the version it stopped at) — D1122's rule, authorised by ADR 0207 §3. Run 1 asks the operator ONE question in writing (§9): *where is the outsider's `outputs.json`?* If it is produced, Run 7 passes `--fresh-host-outputs`; if not, `fresh_host` stays `not_run` with *the operator did not locate the document* as the reason in §7 and the ledger — never a softened status. | ADR 0197 was right that the artefact exists and wrong that supplying it is mechanical: the proof would have refused it, and a refusal that reads *older product* sends the operator to redeploy a host that was fine. A premise wrong in the reassuring direction (§7). | 0207 |
| **D1313** | `docs/new-team-member.md`: *"Fourteen steps, each labelled **available now** or **future session**"*; step 14 *"future session (10)"*; *"You do not have a running database. That is Session 3"*; step 12 *"implemented in Session 2"*. D693's guard scans documents for `--session N` an operator types. | **The guide is the documented path and it is fifteen sessions stale in prose D693's guard is right not to flag.** Steps 8a and 8b were added (Sessions 22 and 23) beside labels from Session 1; nothing in it names a table, a capability, a client's `init()` answers, or Studio; its *done* section says the reader has no database in the paragraph after the one that gave them one. A walker following it reaches a *done* that contradicts what they just did, and every such contradiction is a candidate `undocumented_steps` entry. | Run 4 **re-derives the guide by diff** (D693's method) into the path an adopter walks now, with one label vocabulary — *available now* only, because every step is — and a *done* section that IS the walk's success criterion (D1303). A new offline proof in `test_session12_documented_path.py`: no `future session` label survives for a session ≤ `CURRENT_SESSION`, and the guide names each of `apg dev`, `apg generate`, `apg studio` and `projects/<slug>` at least once. | D703's class — the prose a reader reads is the half no guard scans — met in the one document whose whole purpose is to be read by a stranger. Found by reading it as the walker will, before the walker does. | — |
| **D1314** | `docs/scope-closure.md` §6: *"close `DX-001` regardless of the direction, because the cost is one outsider's afternoon"*; stage plan §4: *"by somebody who did not build Session 20"*. | **Neither the operator nor this plan's executor qualifies, and the plan must say so or the walk will be run by whoever is at the keyboard.** The operator ran every sudo line of Sessions 20–24 and read every plan; the executor of Runs 1–5 will have edited the README the walk reads. Session 19's outsider was a separate session with no prior context, which is why ADR 0197 could accept its findings at all. | **Run 6 is executed by a session that is not this plan's executor**: the executor prepares a clone (`git clone` INSIDE WSL from the local checkout at the release-candidate commit, so modes survive; never through `\\wsl$`), copies the task statement out of `docs/second-walk.md` VERBATIM as the whole prompt, and stops. The operator starts the walker from the clone's directory (a different launch folder → no `CLAUDE.md`, an empty memory directory). The executor's next action is reading the record the walker wrote. Any exchange with the walker during the walk is recorded in `undocumented_steps` by rule. | D478: a claim closed by its author's hands leaves the next reader unable to tell a proved guarantee from a plausible one. The cheapest way to keep the hands apart is to make the handover a file. | 0207 |
| **D1315** | This plan's D1308, *"measured today, rig 25a, at `bb93a53`"*: **60** verbs, **37** naming `--project`, `--help` costing **12-17 ms**. | **All three numbers are wrong, re-measured in rig 25a on 2026-09-14 at `5ab0c4a`** (documentation-only since `bb93a53`, so `bin/` is byte-identical). `bin/apg.sh --list` prints **65** verbs. All **65** answer `--help` with exit 0, in **11-77 ms** -- median 15, and `session-01-check` is the 77 ms outlier, five times the next slowest. **18** carry a line whose first non-space token is `--project`; **48** contain the string somewhere, so a loose `grep -c -- '--project'` over-counts by **30**, nearly all of them the session gates' `--project-a-outputs`. 37 is neither figure. | The anchored form over the measured 18 is what Run 2 derives from, and ADR 0207 §2 carries the measured numbers rather than the planned ones. The 47 verbs that do not name it receive nothing. | D267: never write a measurement you did not run. The whole of Run 2's design rests on how many verbs take the flag and on the help call being cheap, and the row that priced it had guessed all three. The direction matters too -- 18 is half of 37, so the planned design would have looked like it was under-applying when in fact the estimate was over-counting prose. | 0207 |
| **D1316** | Stage plan §9's stop condition: *"Rig 25a finds a verb whose `--help` names `--project` in prose but does not take the flag ... stop; do not fall back to a kept list -- record the verb, fix its usage text, and measure again."* | **It happens exactly once in 65 verbs, and it is `dr-kit verify`.** `bin/dr-kit.sh --help` carries the usage continuation `       --project project.alpha.yaml [--project project.beta.yaml ...] --output DIR`, whose first token is `--project`, so the anchored derivation matches. But `--project` is declared on the **`export` subparser only** (`bin/dr-kit.py:188`, `exporter.add_argument`), and `bin/dr-kit.sh verify --project FILE` answers `dr-kit: error: unrecognized arguments: --project`, exit 2 (rig 25a, fourth arm: 18 verbs probed bare and once per subcommand word, one refuser). With `APG_PROJECT` set, `apg dr-kit verify` would stop working. | **The stop condition's own remedy, taken in Run 2**: `dr-kit`'s usage is rewritten so no line begins with `--project` and the flag is documented under `export` where it belongs; `dr-kit` then receives no default at all, which costs nothing real -- `export` is root-only and names its projects explicitly anyway. **Plus the guard the rewrite is not**: a contract proof that every verb whose `--help` names `--project` line-anchored actually accepts it, read from the parser rather than from the prose. | A usage block naming a flag the command does not take is a `DX-002` failure on its own terms, before any dispatcher reads it. And one instance found by hand is not a measurement: the next one has to be found by a test, or the derivation is only as good as the last person who looked. | 0207 |
| **D1317** | The derivation reads the verb's `--help`, so a verb that takes `--project` without documenting it line-anchored gets no default. | **Sixteen `session-NN-check` gates are exactly that** (rig 25a, third arm): each has a `--project` / `--project=*` `case` arm and each documents only `--project-a-outputs` and `--project-b-outputs` in its usage, so none of the sixteen matches the anchored form. | **Left as it is, deliberately, and recorded rather than repaired.** A missed default is a command that behaves exactly as it did yesterday; a wrong match is a command that stops working. The asymmetry is what chooses the regex, and the sixteen are named here so the next reader knows the under-application was measured and not overlooked. | ADR 0195's shape at the level of a default: the reader has three answers -- takes it, does not take it, and *the help does not say* -- and the third is reported here rather than folded into either of the first two. | 0207 |
| **D1318** | This plan's Run 2 step 1: *"rig 25a says whether the `=` form is accepted by the verbs; recognise it either way, because recognising too little appends a duplicate"*. | **Measured: the `=` form is refused by all three verbs a walker types most.** `bin/dev.sh --project=/tmp/absent.yaml` prints its usage and exits 2; `--project /tmp/absent.yaml` reaches the manifest check and reports *project manifest not found*. `generate` and `studio` behave identically. So `--project=FILE` is not a spelling this product supports at all. | The dispatcher still treats `--project` and `--project=*` alike when asking whether the arguments **already carry** one, and appends only the two-word form. Recognising too little is the failure that matters: it would append a second `--project` to an invocation that already had one. | The question the check asks is not *is this spelling valid* but *did the operator already say which project*. An operator who typed `--project=x` said so, and deserves the verb's own error about the spelling rather than a second flag on top of it. | 0207 |
| **D1319** | This plan's Run 1 step 2: *"Record the cost of one completion (a `--help` call, ~15 ms)"*. | **A flag completion costs ~21 ms; a VERB completion costs ~175-225 ms** (rig 25b, seven completions and three controls). The verb path is ten times the estimate because `list_verbs` runs `basename` in a loop -- **65 forks** per press of TAB -- while the flag path is the single `--help` call the estimate priced. `apg d` yields exactly ten verbs; `apg zz` and `apg no-such-verb --` yield none; `apg dev <TAB>` yields none so bash's own path completion is left alone. | The cost is recorded and the design is unchanged: a fifth of a second on TAB is acceptable and staleness is not. **Making `list_verbs` fork once instead of 65 times is not this session's** -- it is a change to the dispatcher's listing, which every proof of ADR 0002's rule reads. | The estimate was for the wrong call. Recording the real number now means the next person to touch `list_verbs` knows there is a caller that runs it on a keystroke. | -- |
| **D1320** | This plan's D1310 and Run 1 step 3: rig 25c is `docker run --rm -i -u 0 -v "$PWD:/work:ro"` on `PYTHON_RUNTIME_IMAGE`, and *"then `-k` the two `test_honest_readers` proofs D1165 repaired, as root -> PASSED"*. | **The reproduction works and the `test_honest_readers` arm does not, for three reasons that are all the rig's.** The root arm is `SKIPPED` at `test_render_atomicity.py:397` and the control arm `PASSED`, so **D1310 is confirmed: D1302 IS showable offline**. But the control only passes once uid 1000 has a **passwd entry** -- without one `pwd.getpwuid` raises `KeyError`, `owner_of` walks up and returns `root` while `current_user()` returns `uid 1000`, and the control FAILS for a reason the mutation cannot reach (D1321). And `test_honest_readers` needs **`sudo`**, which `python:3.12-slim` does not ship, and **`.venv/bin/python`**, which is a symlink to an interpreter that exists on this workstation and not in the image. | The rig carries all three: a mounted `/etc/passwd` naming the checkout's uid, a throwaway layer with `sudo` installed, and a three-line wrapper mounted at `.venv/bin/python` that execs the container's own locked interpreter. With them, `test_honest_readers.py` as root is **23 passed, 1 failed**, and the one failure is the read-only mount (the proof `chmod`s `.generated/fixture-alpha-dev`) -- **identical in the non-root control**, which is how it is known to be the mount and not the identity. **Run 3 mounts the checkout read-write** and re-runs both arms after the lift. | The rig is a second configuration and must be tied to the product's (ADR 0065/0066). Three of its differences from the gate's environment were invisible until each broke an arm, and a rig whose control fails is not a control. | -- |
| **D1321** | `rendering.owner_of`: *"The owning user's name, walking upward when the path itself cannot answer ... `unknown` when nothing can -- reported rather than guessed (ADR 0195)."* | **It cannot tell *I may not look* from *this uid has no name*.** The loop is `except (OSError, KeyError): continue`, so a uid with no `/etc/passwd` entry -- a container, a deleted account -- is treated exactly as an unreadable directory and the function returns an ANCESTOR's owner as if it were the path's. Measured incidentally in rig 25c: the document was owned by uid 1000 and `owner_of` returned `root`, the owner of `/tmp` three levels up. | **Recorded, not repaired.** It is the ADR 0195 class in a reader this session does not otherwise touch, and changing what `owner_of` answers changes every message built on it (`_cannot_replace` among them), so it needs an ADR and a grep of every caller (D979) rather than a line. Carried into §10. | The docstring already names the right rule and the code implements two of its three answers. A uid that exists and has no name is a determinable fact reported as somebody else's -- D600's shape, in the function whose docstring cites the ADR that forbids it. | -- |
| **D1322** | This plan's D1304: *"Rig 25d (Run 1) counts it: a synthetic record of the tenant path lists **6** false source edits"*, over a list of seven paths. | **Seven, not six** (rig 25d). The plan's list omitted README's own row 4, `projects/<slug>/contracts/postgrest-openapi.canonical.json` -- the snapshot captured from a running deployment. README's two tenant sections name **eight** files under `projects/<slug>/` plus `project.yaml`; of the nine basenames only `capabilities.yaml` and `project.yaml` are in `OPERATOR_INPUTS`, so **7** survive as false source edits: `0001-tasks.sql`, `evaluation-cases.yaml`, `manifest.json`, `mcp-capabilities.canonical.json`, `postgrest-api-surface.yaml`, `postgrest-openapi.canonical.json`, `released.lock.json`. | The count in ADR 0207 §3(a) and in Run 3's battery is 7, and the battery's fixture is built from README's table rather than from a list in a plan. | The row was right about the defect and wrong about its size, because it was written from a summary of README instead of from README. The fixture the proof is built against has to be read out of the document the walker reads, or it measures the plan's memory of it. | 0207 |
| **D1323** | This plan's D1305 names one direction: `_COMMAND` *"captures `bin/apg.sh` and stops"*, so any verb passes. | **It fails in the other direction at the same time, and that half refuses an honest walker.** The documented set is scanned from `README.md`, `docs/README.md` and `docs/session-*-operator-guide.md` -- **not from `docs/new-team-member.md`**, which IS the documented path. Measured (rig 25d): `bin/apg.sh no-such-verb` passes; `bin/dev.sh up --project project.yaml` is **refused**, because `bin/dev.sh` appears in no scanned document while `bin/apg.sh` appears in README. So a walker who runs the script directly is told they used an undocumented command, and a walker who runs a verb that does not exist is not. | Both halves are fixed by the same resolution: resolve `bin/apg.sh <verb>` to `bin/<verb>.sh` on **both** sides, and scan `docs/new-team-member.md` and `docs/second-walk.md` as well. | The scan's omission is D703's class -- the prose a reader reads is the half no guard scans -- in the guard whose entire job is to compare what a reader ran against what a reader was told. | 0207 |
| **D1324** | This plan's D1309: *"A tenant's tools (`projects/example/contracts/mcp-capabilities.canonical.json`, 7 tools)"*. | **Two tools, behind two capabilities** (rig 25e; the file's own `tool_count` and the catalog the renderer produces from it both say 2: `query_resource` and `set_note_embedding`). **7** is the RELEASE contract's *capability* count -- its catalog line reads *6 tools behind 7 capabilities* -- so the row crossed the two documents' numbers. | The project catalog Run 4 commits is a two-tool table, and the proof that reads it is written against 2. | The size was quoted from the wrong document, and a proof written to expect seven rows would have failed on the example project the session ships. | -- |
| **D1325** | This plan's D1309: `render-mcp-catalog.py` *"gains `--project FILE` writing `projects/<slug>/docs/mcp-tool-catalog.md`"*, priced as one flag and one output path. | **There is a third thing, and the row does not name it: the renderer cannot create its output.** `main` reads `CATALOG.read_text()` before it writes anything and hands the result to `compose`, which requires both `<!-- BEGIN GENERATED: mcp-catalog -->` and its END marker. Measured (rig 25e): an ABSENT output file raises an unhandled `FileNotFoundError` -- a traceback, not a report; a file present without the markers is refused cleanly with exit 1. A project's first catalog is exactly the absent case. | Run 4 seeds `projects/example/docs/mcp-tool-catalog.md` with the two markers and commits it, and the absent-file traceback is turned into a reported refusal naming the seed as the fix. The two lines the row did name are confirmed: `CONTRACT` at `bin/render-mcp-catalog.py:53` and `CATALOG` at `:54`. Control: `--check` on the tree exits 0 and `--write` leaves the release catalog byte-identical. | ADR 0195 in a generator: a reader that dies with a traceback has not reported the third answer, it has shown the operator a stack. Found by running the new path's first invocation before writing it. | -- |
| **D1326** | This plan's D1312 and its §9: *"The proof carries the declared document with `carry_to_current` BEFORE the version assertion"*, on D1122's *migrate, then validate* rule; and *"the operator locates the fresh-host document and `carry_to_current` cannot carry it"* as an unlikely stop. | **`carry_to_current` cannot carry ANY deployed document, and `fresh_host`'s document must be a deployed one.** All **16** single-step migrators call `require_kind(document, "rendered")`; measured on four real archived documents (rig 25f), the v16 kit, the 2026-09-06 kit, the v17 kit and the v18 kit all answer *expected a 'rendered' outputs document, got 'deployed'*. That is ADR 0012 on purpose: the migrator never republishes an observation under a version that never measured it. The plan's resolution is not a risk, it is impossible -- and **the tree already solved the same problem seven days earlier**: `dr_kit.verify_deployed_document` (D1141) reads an archived deployed document BY VERSION, three ways. | `DEP-001`'s proof takes the kit verifier's shape, not the migrator's (ADR 0207 §3d): assert what the claim is about -- deployed, names a host, not the host `project_a` runs on, routes ready -- and read the version the way the kit verifier does. A document older than this release is the **reported third answer** and the claim stays `not_run` with the version named; it is never *failed*, and never a silent pass. | §7 question 5, one level up: a decision was implemented (D1141's version-aware read) and only one of its two callers got it. And §7's *premise wrong in the reassuring direction* -- the plan's carry sounded mechanical, would have raised on the first real document, and the refusal a reader would have seen names the wrong subject. | 0207 |
| **D1327** | This plan's D1310: *"**`tests/fixtures/checkout_owner.py`** (beside `outputs_chain.py` and `rendered_fixtures.py`, the existing helper home)"*; and Run 1's read list: *"`src/agentic_postgres/output_migrations.py` (`carry_to_current`, D1134)"*. | **Both paths are wrong.** `outputs_chain.py` and `rendered_fixtures.py` are in **`tests/contract/`**; `tests/fixtures/` holds JSON fixtures and one `pgbackrest` directory and no Python at all. And `carry_to_current` is **not in `src/`**: it is a test helper in `tests/contract/outputs_chain.py:57`, which is why `test_output_migrations.py` imports it as `from outputs_chain import carry_to_current`. | The lifted helper lands at **`tests/contract/checkout_owner.py`**, which is where both importers already live and where pytest's prepend import mode makes a bare `import checkout_owner` resolve. | A helper put in `tests/fixtures/` would not have been importable by either module without a path change nobody planned, and the mistake is invisible until the import fails. | -- |

---
## 2. What the session adds to `tests/acceptance-registry.yaml`

Families `DX-*`, `SEC-*` and `REL-*` extended (no new family; `ID_PATTERN`
is untouched). All P0, `target_session: 25`. Every requirement belongs to a
claim (D697); **a new requirement gets a claim of its own and is never joined
into an older one** (D1150, ADR 0089). Node ids are proposed; the runs settle
the names, and Run 5 writes what the runs actually wrote, **reading each
clause of each description against a node id** (D1236).

| Requirement | What it states | Offline node ids (proposed) | Live half |
|---|---|---|---|
| `DX-CTX-001` | `bin/apg.sh` applies `APG_PROJECT` as `--project` only when the variable is set, the verb's own `--help` names `--project`, and the arguments carry none; it prints one stderr line naming the value and its source each time it applies it and nothing otherwise; an explicit `--project` wins; a value naming no readable file is refused with exit 2 before `exec`; a verb whose help does not name the flag receives nothing; `--help`/`--list` are never rewritten; the dispatcher still keeps no list of verbs | `test_apg_dispatcher.py::test_the_default_project_is_applied_only_to_a_verb_whose_help_names_the_flag`, `::test_an_explicit_project_wins_over_the_default_and_nothing_is_printed`, `::test_the_default_is_announced_on_stderr_each_time_it_is_applied`, `::test_an_unreadable_default_is_refused_before_exec`, `::test_the_default_never_reaches_help_or_list`, `::test_the_dispatcher_still_keeps_no_list_of_verbs` | — (offline claim) |
| `DX-COMPLETE-001` | `bin/completion.sh bash` prints a bash completion script to stdout and nothing else; the printed script derives verbs from `bin/apg.sh --list` and flags from `bin/apg.sh <verb> --help` at completion time and embeds neither; sourced in bash, `complete -p` names `bin/apg.sh` and `apg`, and a completion of `apg d` yields exactly the verbs beginning with `d`; an unknown shell is exit 2 naming the one that exists; the script prints no environment value | `test_completion_command.py::test_completion_is_a_verb_of_the_dispatcher`, `::test_the_script_embeds_no_verb_and_no_flag`, `::test_sourced_in_bash_it_completes_verbs_from_the_list`, `::test_it_completes_a_verbs_flags_from_its_help`, `::test_an_unknown_shell_is_refused_with_exit_two`, `test_cli_contract.py::test_commands_are_executable_in_the_git_index` | — |
| `DX-WALK-001` | The walk's record is read by `dx_record`: `source_edits` compares paths and excludes the walker's own `projects/<slug>/` and the five operator inputs; `unnamed_commands` resolves `bin/apg.sh <verb>` to the verb's script on both sides; `stale_documents` names every read document whose digest moved; `followed_by` must carry kind, identity, instructed_by and context; `bin/dx-record.sh check --record FILE` reports the same three readings with exit 0 or 5 and computes `documents_read` digests with `digest`; the live proof calls the same functions; a record from the tenant path with no edit passes and one with a release file edited, a verb the docs do not name, or a moved document fails naming the item | `test_dx_record.py::test_a_walkers_own_project_directory_is_not_a_source_edit_and_a_release_file_is`, `::test_a_verb_typed_through_the_dispatcher_resolves_to_its_script_on_both_sides`, `::test_a_document_that_moved_after_the_walk_is_named`, `::test_followed_by_must_be_structured`, `test_dx_record_command.py::test_check_is_a_verb_and_reports_the_three_readings`, `::test_digest_writes_the_documents_read_member`, `::test_the_live_proof_calls_the_same_reader` (AST) | `test_session12_reuse.py::test_a_developer_who_did_not_build_this_completed_the_documented_path` is `DX-001`'s, rewritten over `dx_record` (ADR 0207) — it stays `DX-001`'s node id; `DX-WALK-001` has no live half |
| `DX-DOC-001` | `docs/new-team-member.md` carries no *future session* label for a session ≤ `CURRENT_SESSION`, names `apg dev`, `apg generate`, `apg studio` and `projects/<slug>` and has a *done* section naming the tenant path; README's *Local bootstrap* → *Rendering a project* → *A local environment* → *Adding your own tables* → *Giving an agent your tables* → *A generated client* → *Studio* are in that order; `docs/second-walk.md` exists, is indexed, and carries the task statement between two fixed markers and the record's schema; `render-mcp-catalog.py --project` writes the project's catalog and `--check --project` refuses drift; the example project's catalog is committed and current | `test_session12_documented_path.py::test_the_guide_labels_nothing_as_future_that_this_release_implements`, `::test_the_guide_names_the_tenant_path_and_the_three_surfaces`, `::test_the_readme_sections_are_in_the_order_an_adopter_walks`, `test_documentation_index.py::test_the_second_walk_page_carries_the_task_statement_and_the_record_schema`, `test_render_mcp_catalog.py::test_a_project_catalog_is_rendered_from_the_projects_contract`, `::test_check_project_refuses_a_stale_catalog` | — |
| `SEC-DX-001` | The three DX surfaces (`apg dev`, `apg generate`, `apg studio`) and their pure modules import no `services/` module and name no host path (`/var/lib/agentic-postgres`, `/etc/agentic-postgres`, `/root`); each command run with a planted secret in its environment and a planted 0600 password file prints neither value on `--help`, on an argument error and on an unrendered project; no file under `services/studio/`, `projects/example/clients/typescript/` or a fresh `.generated/.dev/<key>/` other than the two declared 0600 files matches the credential canary; `HARDENING_MATRIX` names a collectible node id for every §8 invariant × surface cell, and each named proof exists and is swept by the offline gate's selector | `test_dx_surfaces_hardening.py::test_no_dx_module_imports_services_or_names_a_host_path`, `::test_no_dx_command_prints_a_planted_secret_on_its_three_cheapest_exits`, `::test_no_dx_artefact_carries_a_credential_but_the_two_declared_files`, `::test_every_matrix_cell_names_a_proof_the_offline_sweep_collects`, `::test_the_matrix_covers_every_invariant_the_stage_plan_lists` | — |
| `REL-STAGE-001` | `VERSION` (the file) equals `agentic_postgres.VERSION`; the constant's comment states the ADR 0162 class it proposes; both deployed projects run the release the tree names at `template_version` equal to it after the deploy; `upgrade verify` exits 0 for both; `upgrade plan` for this release's candidate on alpha prices exactly the class the constant's comment proposes | `test_release_contract.py::test_the_version_file_and_the_constant_agree`, `::test_the_constants_comment_states_the_class_it_proposes` | `test_session25_release.py::test_both_projects_run_this_release_and_verify_against_it`, `::test_the_plan_priced_this_release_as_the_class_it_proposes` (Run 7's sweep) |

**Claims** (`src/agentic_postgres/evidence_claims.py`), each dated 25:
`dx_context: ("DX-CTX-001", "DX-COMPLETE-001")`,
`dx_walk_instrument: ("DX-WALK-001", "DX-DOC-001")`,
`dx_hardening: ("SEC-DX-001",)` — all three in `OFFLINE_CLAIMS` (every proof
runs in a checkout, with Docker for the `.generated/.dev` scan; a skip is not
a pass and the gate refuses an absent daemon as 24's does);
`stage_release: ("REL-STAGE-001",)` is a **host** claim, deliberately not
declared: whether a deployment runs a release and prices it as the tree
proposes is a fact about a deployment. The two standing claims this session
expects to move are not new: **`documented_path`** (`DX-001`, Session 12's,
host) on the walk's record, and **`fresh_host`** (`DEP-001`, Session 12's,
host) on the operator's file if it is located (D1312). `honest_readers`
moves on D1310's repair in the same sweep.

**No new gate variable.** `--dx-record-file` and `--fresh-host-outputs`
exist in every gate since 12 and export `APG_DX_RECORD_FILE` /
`APG_FRESH_HOST_OUTPUTS`, both in `tests/conftest.py::ENVIRONMENT_VARIABLES`.
The new live module reads `APG_LIVE_HOST`, `APG_PROJECT_A_OUTPUTS`,
`APG_PROJECT_B_OUTPUTS`.

---

## 4. Irreversible operations

| Operation | Where | What makes it safe |
|---|---|---|
| `bin/apg.sh` reads `APG_PROJECT` | Run 2 | Applied only when set, only to a verb whose help names the flag, only when no `--project` is given; announced every time; refused before `exec` when unreadable; `test_apg_dispatcher.py`'s existing eleven proofs unchanged and green (the dispatcher's every other property is a passing test) |
| `bin/completion.sh`, `bin/dx-record.sh` added | Run 2, Run 3 | `SHELL_COMMANDS` gains both the run each lands; `git add`ed before `test_cli_contract` runs (D1188); each documents itself, obeys the exit-code convention, prints no environment (`DX-002`'s guards run over them by being listed) |
| `test_session12_reuse.py`'s `DX-001` and `DEP-001` proofs rewritten stricter | Run 3 | ADR 0207 authorises each replacement; every old assertion is kept or strengthened (path comparison, verb resolution, digests, carry-then-assert); the node ids are unchanged so the claims are not re-dated; a battery with the old shape's false pass as a mutation (a `manifest.json` under `migrations/` must still be an edit) |
| `_as_checkout_owner` moved to `tests/fixtures/checkout_owner.py` | Run 3 | The moved TEXT grepped (D1187); `test_honest_readers.py` runs whole after; rig 25c re-run as root and as the owner |
| `render-mcp-catalog.py` gains `--project`; `projects/example/docs/mcp-tool-catalog.md` committed | Run 4 | The release's output byte-identical without the flag (asserted); the project catalog drift-checked in the gate |
| `docs/new-team-member.md` and README sections re-derived | Run 4 | By diff, read line by line; `test_session12_documented_path` and `test_documentation_index` run whole; the old *Adding your own tables* assertions (`test_the_readme_tells_an_adopter_what_adding_a_table_costs`) stay green — the section moves, its sentences do not |
| `CURRENT_SESSION` 24 → 25 | Run 5 | All-or-nothing (D690); every `target_session: 25` requirement has its proofs in the same commit; the live module collected under `--setup-plan` with the variables set |
| `VERSION` 1.5.0 → 1.6.0, client regenerated in the same commit | Run 5 | Proposed minor (§0); `generate --check` → 0 after the regeneration (D1238); confirmed by Run 7's `upgrade plan`, a `major` there is §9's stop |
| The walker's clone and session | Run 6 | A clone in WSL under `~/walk/`, never the working checkout; removed after the record is copied; the walker holds no credential, no host access, no `sudo` |
| Deploy `--through-session 25` on both projects | Run 7 | Applies no migration; the render may move nothing but `template_version` and the document's `deployed_through_session`; `upgrade plan` read first (three candidates, D1244's shape); unredirected (D972) |
| `bin/dr-kit.sh export` on the host | Run 7 | A new kit directory; nothing removed; `--kit-dir` stays on `kit-2026-09-11` (D1282) |
| The `1.6.0` tag | Run 8 | On `main` after the fast-forward, after `evidence/session-25.json` exists; the operator's `git tag -a`, pushed once |
| Merge of `session-25` into `main` | Run 8 | Fast-forward only, after CI is green on the branch's last commit |

Not irreversible and worth saying: every rig removes its containers with
`docker rm -f -v`; `apg dev down` runs in `finally`; the walker's clone is
`rm -rf`'d after its record is copied and its `apg dev down` confirmed.

---

## 5. Build order, run by run

Each run ends with: ruff (its **exit code** printed), the targeted modules
(named, each checked for existence individually — D1104), derived documents
regenerated where a generator's input moved, `chmod 755 bin/*.sh bin/*.py
deploy.sh`, one commit on the `session-25` branch with a message file, a
push, and **that commit's CI verdict read** by full SHA with three buckets
(D1059). A run that writes a test runs its battery (appendix). Mark the run
**Done.** here with what it measured. **A targeted list is derived from the
tree** (D1146, D1149, D1184, D1187): a run that moves a definition greps
every reader of the name AND of the distinctive text (`git grep -n <name> --
tests bin src services docs`) and runs every module found, whole. A red CI on
the branch is a stop condition.

**Docker is required for Runs 1, 3, 5, 6 and 7** (rig 25c, the `.generated/.dev`
scan, the gate, the walker's `apg dev`, the sweep). If `docker version` fails
in WSL, stop and say so; do not write a proof that skips.

**Network is required nowhere before the trip.** No package is added, no
registry is reached; CI is read through the Windows `gh` and the push goes
through the Windows git over `//wsl$/` (`CLAUDE.md` §1).

### Run 1 — the measurements and ADR 0207

**Read first:** this plan's §1 whole; ADR 0197 whole; `bin/apg.sh` whole
(161 lines); `tests/contract/test_apg_dispatcher.py` whole (the eleven
proofs every dispatcher change must keep green);
`tests/deployment/test_session12_reuse.py` lines 1–60 and 180–275 (the two
proofs Run 3 rewrites — read `DX_RECORD_FIELDS`, `OPERATOR_INPUTS`,
`_COMMAND` and the four assertions); `tests/contract/test_honest_readers.py`
lines 100–140 (`_as_checkout_owner`) and `tests/contract/test_render_atomicity.py`
lines 385–410 (the skip D1302 names); `bin/render-mcp-catalog.py` whole;
`src/agentic_postgres/output_migrations.py` (`carry_to_current`, D1134 —
`git grep -n "def carry_to_current"`); `docs/new-team-member.md` whole;
`FINDINGS.md` in the launch folder, its header only (the outsider's
position); `docs/plans/session-23-implementation-plan.md` §5 Run 1 (the
shape of a measurement run and what a rig's Done paragraph pastes).

Every rig is a script under `/tmp` in WSL, copied to the scratchpad before
anything else (`/tmp/save-tmp.sh`'s habit), with a control arm, its output
in `/tmp/r25X.txt`, its numbers pasted into this run's Done paragraph.
**Never write a measurement you did not run** (D267).

1. **Rig 25a — the dispatcher's facts.** For every verb in `bin/apg.sh
   --list`: `<script> --help` exit code, wall time, and whether the text
   names `--project` as a FLAG (a line-anchored regex over the usage,
   `^\s+--project\b` — record how many the loose `grep -c -- '--project'`
   over-counts, because Run 2's derivation uses the anchored form). Expect
   60 verbs, 60 exit 0, ~37 naming the flag. **Control**: `bin/apg.sh
   no-such-verb` exit 2. Then, for the three verbs the walker types most
   (`dev`, `generate`, `studio`), run each with `--project` given twice
   (once as `--project=FILE`, once as two words) to learn whether the verb
   accepts the `=` spelling — the dispatcher's "carries no `--project`"
   check must recognise both, or record that it recognises one. Numbers
   → D1308's row is confirmed or corrected.
2. **Rig 25b — completion in bash.** In WSL bash (not the pinned image; the
   walker's shell is a bash): a throwaway `complete -F` function that
   derives words from `bin/apg.sh --list` and from `bin/apg.sh $verb --help`
   (flags as `--[a-z-]+` over the usage), driven by setting `COMP_WORDS`,
   `COMP_CWORD` and calling the function, `COMPREPLY` printed. Measure: `apg
   d` → `deploy dev dev-token db docker-firewall docs doctor dr-kit
   database-access database-ports` (or whatever `--list` says — record it);
   `apg dev --` → dev's flags; **control**: `apg zz` → empty. Record the
   cost of one completion (a `--help` call, ~15 ms).
3. **Rig 25c — D1302 reproduced as root, offline.** `docker run --rm -i -u 0
   -v "$PWD:/work:ro"` (read-only is fine: the proof writes under
   `tmp_path`, which is inside the container's `/tmp`) on
   `PYTHON_RUNTIME_IMAGE` with the venv's site-packages NOT mounted —
   install from `requirements-dev.txt` with `--require-hashes` into a
   container-local venv, or use `uv` inside the image the way D1239's
   workaround did; `PYTHONPATH=/work/src pytest /work/tests/contract/test_render_atomicity.py
   -k owner_is_resolved_upward -q -p no:randomly` → expect **SKIPPED** with
   *root stats through a 0000 directory*. **Control**: the same with `-u
   $(id -u)` → **PASSED**. Then `-k` the two `test_honest_readers` proofs
   D1165 repaired, as root → PASSED (the shape Run 3 copies). If the root
   arm does NOT skip, D1302's row is wrong and this run says how.
4. **Rig 25d — the record checks against the tenant path.** Write
   `/tmp/r25d-record.json`: a synthetic record of a walker whose slug is
   `walker` and whose `files_edited` lists the seven paths README's *Adding
   your own tables* and *Giving an agent your tables* name under
   `projects/walker/`, plus `project.yaml`; `commands_run` as the docs
   spell them (`bin/apg.sh dev up --project project.yaml` etc.). Run the
   CURRENT proof's logic over it as a script (copy the four assertions;
   do not edit the proof): count the false source edits (expect **6**,
   D1304) and confirm `bin/apg.sh not-a-verb` passes the documented-command
   check (D1305). **Control**: a record editing `migrations/manifest.json`
   is refused by both the current logic and the logic Run 3 will write.
5. **Rig 25e — what `render-mcp-catalog.py` reads.** Run it `--check` on
   the tree (exit 0), then with the example project's contract copied over
   the release's path in a temporary copy of the checkout → the rendered
   table differs (the 7-tool shape). Read the script's argument parser and
   its input path constant; record the two lines Run 4 edits. Control: the
   release catalog byte-identical after `--write` on an unchanged tree.
6. **Rig 25f — `fresh_host`'s document.** `carry_to_current` over
   `evidence/`'s oldest deployed document that is at v16 or v17 (the
   session-18 host half carries one; `git grep -n schema_version
   evidence/*.json` — evidence is gitignored, read the files) → v18, no
   exception; and over a document with `schema_version` 3 → the reported
   refusal, not a traceback. **Then the one question only the operator can
   answer, written into this run's Done paragraph as a question**: *where
   is the outsider's `outputs.json` from the 2026-09-08 bring-up?* Do not
   guess a path; do not read the production host for it. The answer, when
   it arrives, is a D row.
7. **ADR 0207** — *A walk is by a reader whose context holds nothing but the
   release and the task, and the record it writes is read by the product*:
   §1 who qualifies (D1307, D1314) and the residual; §2 the dispatcher's
   default derived from the verb's help and the completion derived the same
   way, with the refused alternative (a file in the checkout); §3 the four
   replacements of `DX-001`'s and `DEP-001`'s proofs (D1304, D1305, D1306,
   D1312), each named as *stricter than what it replaces* with the old
   assertion it keeps; §4 what the walk's success criterion is (D1303) and
   that Studio is read, not opened. Indexed in `docs/decisions/README.md`
   (count 207).
8. The rows this run adds or corrects, numbered from D1315.

**Targeted:** `test_apg_dispatcher` (nothing changed; it is the control that
the rigs left the tree alone), `test_documentation_index` (the ADR index
moved), `test_repository_contract`, then `bin/session-01-check.sh` is NOT
run (documentation and an ADR only; the ADR index is generated content →
`bin/session-01-check.sh` alone IS the rule for generated artefacts — run
it if `render-*` touched a tracked file, else nothing). Push; read CI.

**Done.** 2026-09-14, on `session-25` off `5ab0c4a`. Six rigs, ten arms, every
number below run rather than quoted; the scripts and their `.txt` outputs are in
`/tmp/r25*` and copied to the scratchpad's `run1-rigs/`. **Thirteen rows,
D1315–D1327; next free D1328.** ADR **0207** written and indexed (207 ADRs).

**Rig 25a — the dispatcher, four arms.** `bin/apg.sh --list` prints **65** verbs
(not 60); all **65** answer `--help` with exit **0** in **11–77 ms**, median 15,
`session-01-check` the 77 ms outlier; **18** name `--project` line-anchored (not
37) and **48** mention the string, a **30**-verb over-count that is almost
entirely the session gates' `--project-a-outputs` (D1315). Controls: an unknown
verb exits 2, `--list` exits 0. Reading the shell `case` arms disagreed with the
help text on ten verbs, and the disagreement was **the rig's** — a GNU ERE
`\\|` mis-parse plus three verbs (`dr-kit`, `restore`, `upgrade`) that parse
nothing in shell and forward to argparse — so the arm was rewritten in Python
and then the flag was probed for real, bare and once per subcommand word, with a
canary argument that guarantees a parse error before any effect. **Exactly one
refuser in 65 verbs: `dr-kit verify`** (D1316), the stop condition §9 named,
resolved by §9's own remedy plus a guard proof. Sixteen session gates take the
flag without documenting it line-anchored and get no default, deliberately
(D1317). `--project=FILE` is refused by `dev`, `generate` and `studio`; only the
two-word form is accepted, and the dispatcher still recognises both as *already
carries one* (D1318).

**Rig 25b — completion.** A `complete -F` function deriving verbs from `--list`
and flags from `<verb> --help` works, embeds nothing (`declare -f` grep for a
verb or a flag: 0), and registers under both `bin/apg.sh` and `apg`. `apg d` →
exactly ten verbs; `apg dev --` → `--as --capabilities --help --project
--render-only`; controls `apg zz`, `apg no-such-verb --` and `apg dev <TAB>` all
empty, the last leaving bash's path completion alone. Cost: **~21 ms** a flag
completion, **~175–225 ms** a verb completion — ten times the estimate, because
`list_verbs` forks `basename` 65 times (D1319).

**Rig 25c — D1302 reproduced as root, offline, four arms.** In the pinned image
with the checkout mounted: root → **SKIPPED** at `test_render_atomicity.py:397`,
*root stats through a 0000 directory*; a named non-root uid → **PASSED**. **So
D1310 is confirmed and D1302's "it cannot be shown offline" is wrong.** Three
rig-side obstacles had to be cleared first and each is recorded (D1320): the
control FAILED until uid 1000 had a passwd entry, which exposed D1321
(`owner_of` cannot tell *I may not look* from *this uid has no name*, and walks
up); `test_honest_readers` needs `sudo`, absent from `python:3.12-slim`; and it
needs `.venv/bin/python`, a symlink to an interpreter the image does not have.
With a sudo layer, a mounted passwd and a wrapper at the venv path,
`test_honest_readers.py` as root is **23 passed, 1 failed**, the one failure the
read-only mount and **identical in the non-root control**. Run 3 mounts
read-write and re-runs both arms after the lift.

**Rig 25d — the record against an honest tenant walk.** The current proof's four
assertions, copied not imported, over a synthetic record built from README's own
two tenant sections: **7** false source edits, not 6 — the plan's list omitted
README's row 4, `contracts/postgrest-openapi.canonical.json` (D1322). Basename
comparison cannot separate the walker's `projects/walker/migrations/manifest.json`
from the release's `migrations/manifest.json`; the path reading separates them
and refuses only the release's. `bin/apg.sh no-such-verb` and two other
nonexistent verbs all **pass** the documented-command check (D1305 confirmed) —
and `bin/dev.sh up` is **refused**, because the scan reads README and the
operator guides but **not `docs/new-team-member.md`**, so the proof is wrong in
both directions at once (D1323). Control: a record editing the release's
manifest is refused by both readings.

**Rig 25e — the catalog renderer.** `CONTRACT` at line **53** and `CATALOG` at
line **54** are the two lines Run 4 edits; the word *project* occurs once, in the
docstring, and nowhere in the arguments (D1309 confirmed). `--check` exits 0 and
`--write` leaves the release catalog byte-identical with the tree clean. The
example project's contract rendered through the same renderer gives **2 tools
behind 2 capabilities**, not the 7 the row said — 7 is the release's *capability*
count (D1324). And the row missed a third edit: `main` reads its output before
writing, so an **absent** catalog raises an unhandled `FileNotFoundError` and one
without markers is refused cleanly at exit 1 — a project's first catalog is the
absent case, so Run 4 seeds it (D1325).

**Rig 25f — `fresh_host`'s document.** **`carry_to_current` refuses every
deployed document**, measured on four real archived ones (v16 `dr-kit-1.0.1`,
v16 `kit-2026-09-06`, v17 `kit-2026-09-11`, v18 `kit-2026-09-13`): all sixteen
single-step migrators call `require_kind(document, "rendered")`, which is ADR
0012 on purpose. `fresh_host`'s document must be *deployed* by the proof's own
first assertion, so **D1312's resolution is not implementable** (D1326) — and the
tree had already solved the same problem in `dr_kit.verify_deployed_document`
(D1141), which reads an archived deployed document by version, three ways. ADR
0207 §3d takes that shape instead. Controls: a v3 document raises the documented
`ValueError` (so an unguarded caller shows a traceback, not a report), and a v18
document is returned identical. Also found: the helper home is
**`tests/contract/`**, not `tests/fixtures/`, and `carry_to_current` is a test
helper, not `src/agentic_postgres/output_migrations` (D1327).

**THE QUESTION FOR THE OPERATOR, unanswered, and Run 7 depends on it:** *where is
the outsider's `outputs.json` from the 2026-09-08 bring-up?* No path was guessed
and the production host was not read for it. What this workstation holds is
**four archived deployed documents, and not one of them is that host**: all four
name `host.id` `apg-vps-01`, which is the host `project_a` runs on, and
`DEP-001` refuses that document by name — it would prove the claim with the
deployment it is supposed to be independent of. So the file is the operator's or
it does not exist. **If it is not produced, `fresh_host` stays `not_run` with
*the operator did not locate the document* as the reason in §7 and the ledger** —
never a softened status. Note for whoever answers: after D1326 the document no
longer has to be at v18. A v16 document is now readable, so an older artefact is
worth producing rather than discarding.

**Not done here, by decision:** nothing in `bin/`, `src/` or `tests/` was
touched — this run is measurements, one ADR and the rows. `dr-kit`'s usage fix,
the guard proof and every code change land in Run 2 and later, where the
targeted lists and batteries are.
### Run 2 — `APG_PROJECT`, `apg completion`, and the record's verb

**Read first:** `bin/apg.sh` whole; `tests/contract/test_apg_dispatcher.py`
whole; `tests/contract/test_cli_contract.py` lines 1–140 (`SHELL_COMMANDS`,
and which checks a listed command is held to: self-documentation, the
exit-code convention, the secret-argument scan, the executable bit in the
INDEX); `tests/contract/test_generate_command.py` lines 1–80 (the shape of a
command proof that runs the product's own verb, D1114); `bin/dev-token.sh`
(the shortest `bin/` shell verb with a `usage()`, exit codes and `die` — the
template for `bin/completion.sh`); rig 25a's and 25b's outputs; ADR 0207 §2.

1. **`bin/apg.sh`**, four additions and nothing removed:
   - `default_project_applies(script, args...)`: returns 0 when
     `APG_PROJECT` is non-empty, no argument equals `--project` or begins
     with `--project=` (rig 25a says whether the `=` form is accepted by the
     verbs; recognise it either way, because recognising too little appends
     a duplicate), and `"$script" --help 2>/dev/null` contains a line
     matching `^[[:space:]]*--project([[:space:]]|$)`. The help is read
     ONCE, into a variable, never through a pipe that hides the exit code.
   - Before `exec`: if it applies, `[ -r "$APG_PROJECT" ] || { printf
     'apg: APG_PROJECT names %s, which is not a readable file.\n' …; exit
     2; }`, then `printf 'apg: --project %s (from APG_PROJECT)\n'
     "$APG_PROJECT" >&2`, then `exec "${script}" "$@" --project
     "${APG_PROJECT}"`. Appended, not prepended: a verb with subcommands
     (`dev up`, `migrate render`) reads its verb word first.
   - `--help` and `--list` are handled before any of this (they already
     `exit` in the `case`); `apg <verb> --help` is a verb invocation whose
     arguments contain `--help` — **do not append to it**: add `--help`/`-h`
     anywhere in the arguments to the "carries" test, and say why in the
     comment (a help request that grew a flag would print a sentence about
     a file the reader never mentioned).
   - The header's paragraph *"It rewrites nothing and moves nothing"* is
     amended to name the one thing it now adds, when, and how it says so.
   - The usage block gains a paragraph on `APG_PROJECT` with the three
     rules (only when the verb takes it; only when you gave none; always
     announced) and the `sudo` caveat: `sudo` drops the variable unless
     `--preserve-env=APG_PROJECT`, and the announcement line is how you
     know whether it reached the verb.
2. **`bin/completion.sh`**: `bash` prints the script; `--help` the usage;
   anything else exit 2 naming `bash`. The printed script defines
   `_apg_complete` (words from `"$APG_ROOT/bin/apg.sh" --list` when
   `COMP_CWORD` is 1; from `"$APG_ROOT/bin/apg.sh" "${COMP_WORDS[1]}" --help`
   filtered to `--[a-z][a-z-]*` when it is ≥ 2 and the current word starts
   with `-`; nothing otherwise — a path completion is bash's own default
   and must not be replaced) and registers it with `complete -F
   _apg_complete bin/apg.sh apg`. `APG_ROOT` is written into the script at
   print time as the checkout's absolute path (the one value embedded, and
   it is a path, not a verb). `set -euo pipefail` at the top of
   `completion.sh`; the printed script must NOT carry `set -e` (it is
   sourced into the user's shell).
3. **`bin/dx-record.sh`** (`check --record FILE [--project-slug SLUG]`,
   `digest --record FILE`): a thin shell over `bin/dx-record.py`, which
   imports `agentic_postgres.dx_record` only (ADR 0093, `HOST_PACKAGES`).
   `check` prints the three readings — source edits, unnamed commands,
   stale documents — each as a list or `none`, and the `followed_by` shape
   check; exit 0 when all four are clean, 5 otherwise, 2 for an unreadable
   record, 3 when a named document does not exist in this checkout.
   `digest` rewrites the record's `documents_read` member from the tree and
   prints the paths it digested. **Run 3 writes `dx_record.py`**; this run
   writes the verb against the module's SIGNATURES as §2 names them, and
   the run's commit is the pair (D1222's lesson: a module with no caller
   cannot be committed alone, and neither can a caller with no module).
   So this run and Run 3's first commit are ordered: the module and the
   verb land together, then the proofs' rewrite.
4. **Proofs.** `test_apg_dispatcher.py` gains the six of `DX-CTX-001`,
   each running `bin/apg.sh` as a subprocess with a controlled environment
   (`env={"PATH": …, "APG_PROJECT": …}` — never the test process's own
   environment, which may carry the variable from the operator's shell)
   against a verb that names the flag (`dev` → `dev status` with the
   fixture manifest) and one that does not (`lock-versions --check` — read
   rig 25a for a verb that takes no `--project` AND exits 0 fast). The
   stderr line is asserted verbatim. `test_completion_command.py` (new
   module, `pytestmark = [pytest.mark.contract, pytest.mark.p0]` BEFORE the
   first test, D1240) runs `bin/apg.sh completion bash`, sources the
   output in a `bash -c` subprocess with `COMP_WORDS`/`COMP_CWORD` set and
   prints `COMPREPLY` (rig 25b's driver), asserts the verb list equals
   `--list`'s filtered set, that `dev --` completes to dev's flags, that
   the printed script contains no verb name and no flag literal other than
   `--list`, `--help` and `--project`-free text (assert by scanning for
   every verb in `--list` and asserting absence). `SHELL_COMMANDS` gains
   `bin/completion.sh` and `bin/dx-record.sh` **in this run** (D1014),
   both `git add`ed before the module runs (D1188).
5. **Battery** (appendix): (a) the anchored regex loosened to `--project`
   anywhere → the verb-without-flag proof kills it (a verb whose usage
   mentions `--project` in prose would be appended to — find one in rig
   25a's over-count, or plant the word in a fixture verb under `tmp_path`;
   if none exists in the tree, the mutation is uninformative (D493) and
   the row says so); (b) the announcement `printf` removed → killed; (c)
   `[ -r ]` removed → the unreadable-default proof errors OR fails — read
   which (D386); (d) a verb name embedded in the completion script →
   killed by the embeds-nothing proof; (e) `complete -F` line dropped →
   killed. Controls: `test_a_verbs_exit_code_reaches_the_caller_unchanged`
   and `test_it_uses_exec_so_it_cannot_alter_what_the_verb_does` green
   throughout.
6. Documents: README's *Checks* names `bin/apg.sh completion bash` and
   `bin/apg.sh dx-record check`; README's *Operating a deployment* (or the
   section that shows `--project` most) gains the `APG_PROJECT` paragraph
   with the `sudo` caveat; `docs/README.md` unchanged (no new page).

**Targeted:** `test_apg_dispatcher`, `test_completion_command`,
`test_cli_contract` (D1014), `test_root_script_policy`, `test_printed_commands`
(a new `bin/*.py` driver — read what `PRINTING_DRIVERS` covers, D1235, and
whether `dx-record.py` prints a next step; it does not), `test_documentation_index`
(README names two new commands; `test_every_command_the_readme_names_exists`),
`test_repository_contract`, `test_acceptance_registry` is NOT needed yet (no
registry change until Run 5). Push; read CI.

**Done.** *(filled by the run.)*

### Run 3 — the closing review, the record reader, and D1302

**Read first:** stage plan §8 whole (the invariant table — the matrix is
its rows × three surfaces); Session 22 plan §8, Session 23 plan §8, Session
24 plan §8 (each session's own list of the proofs it wrote per invariant —
the matrix's cells are filled from these three lists FIRST, by node id, and
only the empty cells get new proofs); `services/auth-api/app/mcp_telemetry.py`
lines 1–40 (the canary's patterns — reuse them, do not write a second
regex); `tests/contract/test_dev_command.py::test_nothing_the_command_prints_is_a_password`
and `test_studio_command.py`'s equivalent (the planted-secret shape);
`tests/deployment/test_session12_reuse.py` whole; `tests/fixtures/outputs_chain.py`
(how a helper module under `tests/fixtures/` is imported — copy its import
style); `tests/contract/test_honest_readers.py` lines 100–140, 230–300;
`tests/contract/test_render_atomicity.py` lines 380–410; rigs 25c and 25d.

1. **`src/agentic_postgres/dx_record.py`** (pure; stdlib only):
   `REQUIRED_FIELDS` (the seven plus `project_slug` and `documents_read`),
   `FOLLOWED_BY_FIELDS` (`kind`, `identity`, `instructed_by`, `context`),
   `OPERATOR_INPUTS` (moved here from the test, the same five names, now
   matched as ROOT-relative paths), `load(path) -> Record` (three outcomes:
   the record, `RecordUnreadable`, `RecordIncomplete` naming the fields),
   `source_edits(record) -> list[str]` (a path is the walker's own iff it is
   `projects/<record.project_slug>/…` or one of the five at the root; the
   slug is validated against `^[a-z][a-z0-9-]*$` so `../` cannot widen the
   exclusion), `documented_commands(tree) -> set[str]` (the scan over the
   five documents and the guides, each spelling normalised to the script
   path: `bin/apg.sh <verb>` → `bin/<verb>.sh`, `bin/apg.sh deploy` →
   `deploy.sh`), `unnamed_commands(record, documented) -> list[str]` (the
   same normalisation over `commands_run`), `stale_documents(record, tree)
   -> list[str]`, `digests(tree, paths) -> dict[str, str]`,
   `followed_by_problems(record) -> list[str]`. Every function is total
   over a malformed record: a list where a dict was expected is a named
   problem, never a `TypeError`.
2. **The live proofs rewritten** (ADR 0207 §3), node ids unchanged:
   `test_a_developer_who_did_not_build_this_completed_the_documented_path`
   loads through `dx_record.load`, asserts `reached_success_criterion`,
   then the four readings in the order *source edits, unnamed commands,
   stale documents, followed_by*, each message naming the items and quoting
   `DX-001`'s words as the current proof does. `OPERATOR_INPUTS` and
   `_COMMAND` are DELETED from the test module (the moved text grepped:
   `git grep -n "OPERATOR_INPUTS\|_COMMAND = re.compile" -- tests src bin`).
   `test_a_project_deployed_on_an_empty_host_is_a_working_deployment`
   carries the declared document with `output_migrations.carry_to_current`
   inside a `try` whose failure is `pytest.fail` naming the version it
   stopped at, THEN asserts `schema_version == CURRENT_VERSION` on the
   carried document, then the three existing assertions unchanged (kind,
   a different host id, every route ready).
3. **`tests/contract/test_dx_record.py`** and **`test_dx_record_command.py`**
   (both `pytestmark` first, D1240): the seven proofs of `DX-WALK-001`,
   each over a synthetic record written under `tmp_path` against a
   synthetic tree (a `tmp_path` checkout with a README naming three
   commands and a `projects/walker/` directory) — never against this
   checkout's README, which Run 4 rewrites; the command proofs run
   `bin/apg.sh dx-record check --record …` and read exit codes 0/5/2/3
   and the printed readings; `test_the_live_proof_calls_the_same_reader`
   parses `test_session12_reuse.py` with `ast` and asserts the four
   function names are called and no `re.compile` remains.
4. **`tests/fixtures/checkout_owner.py`** and D1302: `as_checkout_owner()`
   moved verbatim with its docstring; `test_honest_readers.py` imports it
   and the local definition is removed; `test_render_atomicity.py::test_the_owner_is_resolved_upward_when_the_path_itself_cannot_answer`
   gains the D1165 shape — under root, the reading (`rendering.owner_of` on
   the shut directory) is made by a child process prefixed with
   `as_checkout_owner()`, whose stdout is the resolved name, and the
   `pytest.skip` is DELETED; unprivileged, the reading is direct as today.
   The precondition (`chmod 0000`) is set by the proof and restored in
   `finally` both ways. Rig 25c re-run as root → `PASSED`; as the owner →
   `PASSED` (both pasted).
5. **`tests/security/test_dx_surfaces_hardening.py`** (`pytestmark =
   [pytest.mark.security, pytest.mark.p0]` first; **check the directory's
   existing modules' marks — `tests/security/` is selected by `-m` and not
   by path, D211 — and copy them exactly**): `HARDENING_MATRIX: dict[tuple[str,
   str], str]` keyed by (invariant as the stage plan §8 words it, surface ∈
   `dev|generate|studio`) → node id. Fill it from the three sessions' §8
   lists. Where a cell is `None` after that, decide: **not applicable**
   (write the reason as the value, e.g. *`apg dev` has no token to
   revoke*), or **a gap** — and write the proof in this run. The three
   cross-cutting proofs of `SEC-DX-001` (the AST/host-path scan; the
   planted-secret run over `dev`, `generate`, `studio` on `--help`, an
   argument error and an unrendered project — `APG_PLANTED_SECRET=<32 hex>`
   in the environment and a 0600 file whose content is a second 32-hex
   value handed as `--password-file` where a verb takes one; assert
   neither value in stdout or stderr on any of the nine runs; the
   `.generated/.dev/<key>/` scan after `apg dev up` on the fixture, every
   file's bytes against the canary, the two declared 0600 password files
   the only permitted matches, `apg dev down` in `finally`) and the two
   matrix proofs (every value that is a node id collects under the OFFLINE
   gate's selector — `OFFLINE_SWEEP_SELECTOR` from the D1242 guard module,
   imported not retyped; every §8 invariant string appears as a key for
   all three surfaces).
6. **The battery per guard**: one mutation per matrix cell whose value is
   a node id and whose proof lives in a module this session may touch
   (Sessions 22–24's modules are released; their proofs' batteries were
   run when written — **re-run ONE representative mutation per session**,
   not all, and record which), and every mutation for the new proofs:
   `source_edits` comparing basenames again → killed by the
   project-directory proof (D1304 as a mutation); the normalisation
   dropped → killed (D1305); `stale_documents` returning `[]` → killed;
   the skip restored in the atomicity proof → the root arm of rig 25c
   SKIPS again (the control is the owner arm, green both ways); the
   canary's pattern list emptied → the planted-secret proof passes
   vacuously? — **no: assert the pattern list is non-empty inside the
   proof, so that mutation ERRORs rather than passes** (D386, and the
   reason the proof carries its own guard); one matrix value set to a
   misspelled node id → killed by the collects proof.
7. `docs/threat-model.md` gains one paragraph under *Notes on residual
   risk*: the matrix exists, where it lives, and that a cell marked *not
   applicable* carries its reason in the source.

**Targeted:** `test_dx_record`, `test_dx_record_command`,
`test_dx_surfaces_hardening`, `test_honest_readers` (whole — the import
moved), `test_render_atomicity` (whole), `test_deployment_suite_shape`
(a deployment module changed), `test_environment_gates`, `test_cli_contract`
(D1014, `dx-record.sh` — if Run 2 did not land it), the D1242 guard module,
`test_repository_contract`, `test_acceptance_registry` (a test function was
renamed or added — D1119; the two live node ids are unchanged, assert that
by reading the registry), `tests/security` by marker (`-m security` — its
selection is by marker, and this run adds a module to it). Push; read CI.

**Done.** *(filled by the run: the matrix pasted — every cell, its proof or
its reason; the battery table; rig 25c's two arms after the repair.)*

### Run 4 — the documentation converged, and the walker's page

**Read first:** `README.md` lines 1–140 (status), 140–450 (the sections in
the order they are now), 447–627 (*Adding your own tables*, *Giving an agent
your tables*); `docs/new-team-member.md` whole; `docs/README.md` whole;
`tests/contract/test_session12_documented_path.py` whole (what a documented
path may not do: name a future stub, pass a wrong session number, ask a
reader to edit a tracked file — **`test_no_documented_step_asks_a_reader_to_edit_a_tracked_file` reads the README; the tenant path creates files under
`projects/<slug>/` and that is not an edit of a tracked file, but read how
the proof decides before writing a sentence it will refuse**);
`tests/contract/test_documentation_index.py` lines 60–130 and 370–500 (what
the README must name, and the two adopter proofs whose assertions the
rewritten sections must keep); `bin/render-mcp-catalog.py` whole; rig 25e;
D693's row (`docs/plans/session-12-implementation-plan.md` §1) for what
*re-derived by diff* means: a script of anchored substitutions, each
matching exactly once, and a line-by-line read of the result.

1. **README, re-ordered into the walk** — the sections move whole; their
   sentences stay (the two adopter proofs assert sentences): *What runs* →
   *Local bootstrap* → *Rendering a project* → *A local environment* →
   *Adding your own tables* → *Giving an agent your tables* → *A generated
   client* → *Studio* → *Deploying* → *Operating a deployment* → *Checks*
   → the rest unchanged. One new paragraph at the top of *Adding your own
   tables*: **the adopter's path in eight lines**, each a command or a file
   they create, numbered, offline-marked — the same eight steps
   `docs/new-team-member.md`'s *done* section will name. *Giving an agent
   your tables* gains the catalog command (D1309) as its last step.
   The status paragraph stays at Session 24 until Run 5.
2. **`docs/new-team-member.md` re-derived by diff**: a script under `/tmp`
   (copied to the scratchpad) with every substitution anchored exactly
   once; the label vocabulary reduced to *available now* (every step is —
   D1313; the `--render-only` step's *"tells you deployment begins in
   Session 2"* sentence goes, and so does step 14's *future session*); the
   steps renumbered 1–14 as: clone, toolchain, environment, doctor,
   specification, contract, manifests, render, **a table** (the
   `projects/<slug>/` files, `freeze-lock`, in the README's words), **a
   local database** (`apg dev up`, your set applied as the migration user),
   **a capability** (`agent init`, `mcp-contract compile/check`, the
   report, the catalog), **a client** (`apg generate`, `init()`'s
   `unreachable` against nothing), **Studio, read** (`apg studio --help`;
   a launch against the rendered document and the sentence it refuses
   with — D1303), the gate. *What "done" looks like today* rewritten as
   the success criterion, verbatim what the record's
   `reached_success_criterion` means: *steps 1–14 complete, `bin/apg.sh dx-record
   check` reports none/none/none, and the gate exits 0 on your clean
   tree with your project directory tracked*. The *If something fails*
   table kept and extended with the three refusals an adopter meets on
   this path (a set out of order at freeze, a table without FORCE RLS, a
   capability naming an operation the surface does not publish — each
   with the exit code and the sentence the product prints, read from the
   tree, D267). **Read the result line by line, both halves** (D703).
3. **`docs/second-walk.md`**, new, indexed under *Evidence and assurance*
   in `docs/README.md` (the index proof): §1 what the walk is and who may
   walk it (ADR 0207 §1, in the reader's words); §2 **the task statement**,
   between the literal markers `<!-- task-statement:begin -->` and
   `<!-- task-statement:end -->`, written to be copied verbatim as the
   whole prompt of a fresh session — it names: the clone's path and that
   it is the release; the shell the walker has and that it is *their*
   machine (WSL, Docker; `wsl bash -lc` if driven from Windows) and not
   the product; the goal (a table of their own choosing with one view and
   one write RPC, an agent capability over the view, a local database
   with the set applied, a generated client, Studio read, the gate green);
   the rule that `docs/plans/` is not read; the rule that every command,
   every file created or edited, and every step the documentation did not
   give is recorded as it happens; the record's path
   (`~/walk/dx-record.json`) and that `bin/apg.sh dx-record digest` then
   `check` are the last two commands; that the walker asks nobody
   anything — a question is an `undocumented_steps` entry; that `sudo`,
   any host, any credential and any deploy are out of scope and a step
   that seems to need one is recorded and skipped; **that the walker
   writes `reached_success_criterion` honestly and `blocked_by` when it
   is false**. §3 the record's schema (the nine fields, `followed_by`'s
   four, an example). §4 what the builder does with it (Run 7's flag, the
   proof, the three readings), and what a failed walk means (`not_run`
   with the list; a second walk by a NEW session after a docs-only
   repair; never a third — §9).
4. **`render-mcp-catalog.py --project FILE`** (D1309): the project's
   compiled contract at `projects/<slug>/contracts/mcp-capabilities.canonical.json`
   read through the same loader the release path uses; output at
   `projects/<slug>/docs/mcp-tool-catalog.md`; a header sentence naming
   the project and marking the release's rows; `--check --project` exits 5
   naming the file on drift. Without `--project`, byte-identical output
   (asserted). The example project's catalog committed; `bin/session-01-check.sh`'s
   generated-documents step and CI's gain `--check --project
   project.example.yaml` (read the step — it is the one that already runs
   `render-mcp-catalog.py --check`).
5. **Proofs**: the six of `DX-DOC-001` (§2) in `test_session12_documented_path.py`,
   `test_documentation_index.py` and a new `test_render_mcp_catalog.py`
   (or the existing module that proves the release catalog — `git grep -ln
   "render-mcp-catalog" -- tests`; extend it rather than add a module if
   one exists, D1240 either way). Battery: a `future session` label planted
   in the guide → killed; the README sections swapped → killed; the task
   markers removed → killed; the project catalog edited by one byte →
   `--check --project` exit 5.

**Targeted:** `test_session12_documented_path`, `test_documentation_index`,
`test_render_mcp_catalog` (or the module found), `test_gate_contract` (the
Session 1 gate's step changed), `test_repository_contract` (a new tracked
directory under `projects/example/docs/`), `test_acceptance_registry`
(D1119). Then `bin/session-01-check.sh` once — generated content moved and
the gate's own step changed; if step 2 cannot reach PyPI from WSL, run that
one step inside the pinned image and say so (D1239). Push; read CI.

**Done.** *(filled by the run.)*
### Run 5 — the bump

**Read first:** `docs/plans/session-24-implementation-plan.md` §5 Run 6
whole (the shape this run copies step by step, and its Done paragraph);
`bin/session-24-check.sh` whole (1499 lines — the gate this one is derived
from; read the header, the usage, step 7, step 9 and the host declarations
at lines 1376–1430 with particular care); `tests/contract/test_session_twenty_four_gate_modes.py`
whole and `test_session_twenty_three_gate_modes.py` lines 140–200 (D1280:
the `session-21-check` literal and the hand-named path this run repairs);
the D1240/D1242 guard module (`git grep -ln "OFFLINE_SWEEP_SELECTOR" --
tests`) — **it checks the selector against the NEWEST gate script, so
deriving `session-25-check.sh` moves what it reads**; `.github/workflows/ci.yml`
lines 101–140 and 236–300; `tests/deployment/test_session24_studio.py` lines
1–120 (the live module shape: the docstring's four paragraphs, `pytestmark`,
the roster variables); `tests/deployment/test_session13_upgrade_plan.py`
(`candidate` fixture — the upgrade-plan reading a live proof can make, and
D1164's suspect); `src/agentic_postgres/__init__.py` lines 60–140 and
236–260 (the constant's comment shape); `docs/scope-closure.md` whole
(re-audited row by row: every entry's premise checked against the tree
before it is kept, moved or removed — D954, D860 and D1055 were each read
wrong once); `docs/stage-3-decision-report.md` whole (the shape the Stage 4
report copies).

1. `src/agentic_postgres/__init__.py`: `CURRENT_SESSION = 25`; `VERSION` →
   `1.6.0` with ADR 0162's pricing in the constant's comment (two new
   operator verbs, one environment variable read by the dispatcher, one
   optional generated document per project; no manifest, outputs,
   capability, lock, migration or secret schema moves; **a project that
   adopts 1.6.0 and sets no `APG_PROJECT` renders byte-identical artefacts
   and deploys the same containers** — write that sentence, it is what
   Run 7's `upgrade plan` confirms); the root `VERSION` file moved with it
   (`test_release_contract::test_the_version_file_and_the_constant_agree`
   is new — read `git grep -n "VERSION" -- tests/contract/test_repository_contract.py`
   first: if a proof already asserts the pair, extend it rather than add
   one). **Then regenerate the client in the same commit** (D1238) and
   `generate --check` → 0; `docs/product-contract.md` §7's sentence
   unchanged (a minor adds nothing to it).
2. `tests/acceptance-registry.yaml`: the seven requirements of §2 with the
   node ids the runs actually wrote — every clause of every description
   read against a node id (D1236); `evidence_claims.py`: the four claims,
   `OFFLINE_CLAIMS |= {"dx_context", "dx_walk_instrument", "dx_hardening"}`,
   `stage_release` with the reason it is not declared beside it;
   `bin/render-acceptance-matrix.py --write`; `test_acceptance_registry`
   and `test_evidence_claims` green, including the per-session offline
   assertion (D1237: this session's three, by subtraction).
3. **The live module** `tests/deployment/test_session25_release.py`, marked
   `p0`, `live_host`, `requires_environment("APG_LIVE_HOST",
   "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS")`:
   - `test_both_projects_run_this_release_and_verify_against_it`
     (`REL-STAGE-001`): each deployed document's `template_version` equals
     `agentic_postgres.VERSION` and `deployed_through_session` equals
     `CURRENT_SESSION`; `bin/upgrade.sh verify --project <key> --candidate
     <the checkout's render of that project>` exits 0 for both — the
     candidate rendered by the proof with `--render-only` into a temporary
     `.generated/<key>` copy? **No**: `--render-only` publishes under
     `.generated/<key>` and the gate compares rendered projects for
     collisions; read `test_session13_upgrade_plan.py`'s `candidate`
     fixture and use exactly its mechanism, because it is also D1164's
     named suspect for the root-owned directory — and record the owner of
     `.generated/alpha-dev` before and after (the D1164 reading, again).
   - `test_the_plan_priced_this_release_as_the_class_it_proposes`: `upgrade
     plan --json` for alpha with the same candidate → `proposed` equals
     the constant's comment class (`minor`), `required` ≤ proposed, and
     the plan *may proceed*. This is the reading the sheet's sudo step
     makes by hand; the proof makes it as the sweep's root.
   - `pytest --setup-plan` with the three variables SET: both collected,
     neither deselected; UNSET: both skip cleanly (D671, D676) — both
     outputs in the Done paragraph.
4. **CI**: `session-2-contract` gains nothing new if the three new offline
   modules are collected by its selector — **measure it** (`--collect-only
   -m "p0 and not future and not live_host and not external"` over the
   three, D1240; and `-m security` for the hardening module, whose marks
   must include what the job selects — read the job's selector, not the
   gate's). The `render-mcp-catalog --check --project` step from Run 4 is
   already in.
5. **The gate.** `bin/session-25-check.sh` **derived from
   `bin/session-24-check.sh` by diff** (D505, D507, D678, D693, D703,
   D1108, D1109): a derivation script under `/tmp` (copied to the
   scratchpad) whose every substitution is anchored to match exactly once;
   `readonly SESSION=25`; header and usage rewritten whole and read line
   by line, both halves. Offline mode: step 3's sweep carries the new
   modules by their marks (nothing to add); step 7 gains the project
   catalog check (Run 4 put it in the Session 1 gate — mirror it); the
   usage names the three offline claims and the one host claim, and says
   **`documented_path` and `fresh_host` are Session 12's claims that this
   sweep is expected to move**, naming the two flags. Host mode: **no new
   flag**; the prose names what the sweep launches (nothing new — the
   release proof reads documents and runs `upgrade`); `--mode host` answers
   for Session 25 alone this time (24's trip paid 22–24; say so, D1244's
   sentence removed). External: prose only. Session 18's five declaration
   flags stay (D1133); `--kit-dir`'s help text gains D1282's sentence
   (*point it at the kit exported BEFORE this release; the newest kit
   destroys the proof quietly*). `SHELL_COMMANDS` gains it. Every `printf`
   whose format begins with `-` is `printf -- ` (D1199).
   `tests/contract/test_session_twenty_five_gate_modes.py` derived from
   24's: `SESSION_TWENTY_FIVE_CLAIMS = {"offline": ("dx_context",
   "dx_walk_instrument", "dx_hardening"), "host": ("stage_release",)}`;
   **and D1280's repair in 23's module in the same commit** (the
   `session-21-check` literal derived from `SESSION_PREVIOUS.name`, the
   executable-bit test naming `SCRIPT`) — a change to a released module
   with the ADR-free reason D1280 already recorded (a derived guard that
   passes for free is not a guard). The D1242 selector guard now reads
   `session-25-check.sh` as the newest gate — run it and read that it did.
6. **Documents**: README's status paragraph at Session 25 and 1.6.0 with
   one paragraph naming what the session adds; *Adopt `1.6.0`*; every
   `--through-session 24` a reader is told to type moved to 25
   (`grep -rn "through-session 24\|--session 24" README.md docs/*.md`,
   D693; the session-numbered operator guides are exempt);
   `docs/scope-closure.md` §1 **counted, not recalled** (D1194) and a new
   §14 *What Session 25 left open* (§10 of this plan) — and the row-by-row
   re-audit of §2–§13: each row kept with its premise re-read, or removed
   because a session closed it (a row a session closes is removed, not
   struck through); `docs/decisions/README.md` count; the matrix, the
   evaluation report and the envelope regenerated where their inputs
   moved; **`docs/stage-4-decision-report.md` written now with every trip
   number marked *[filled at the trip's close]*** (D992's rule): §1 what
   1.6.0 is; §2 what was measured (the table, blanks marked); §3 what
   stayed `not_run` and why (the nine, each with its reason as it stands
   today, to be reduced by the trip); §4 the three blockers — which two
   Stage 3 removed (a schema of one's own: Session 20; an agent that can
   address it: Session 21) with the claim ids that prove each, and what the
   third costs, copied from the stage plan §6 and priced against the tree
   (the seam `runtime_override.publication()` still raises; the rotation
   never performed is the first item on that bill); §5 what the DX layer's
   evidence says about the hosted question — one paragraph per surface
   naming what its claims prove holds under the hosted reading (the DX
   layer holds nothing the human does not hold: `STU-*`, `GEN-*`, `DEV-*`
   node ids) and what they do not (nothing about multi-tenancy, billing,
   accounts, a public port); §6 the recommendation, written as one, after
   the evidence exists — **left as a heading with the sentence *written at
   the close from `evidence/session-25.json`* until Run 8**.
7. `bin/session-01-check.sh` once on the clean tree (a session close is
   one of the cases the working agreement allows; D1239's workaround for
   step 2 if WSL has no HTTPS). Repair and re-run **only the module that
   failed**, then push.

**Targeted:** `test_evidence_claims`, `test_acceptance_registry`,
`test_cli_contract`, `test_capacity_envelope`, `test_documentation_index`,
`test_session12_documented_path`, `test_repository_contract`,
`test_gate_contract`, `test_session_twenty_five_gate_modes`,
`test_session_twenty_four_gate_modes` (its `SESSION_PREVIOUS` reads 23's; it
must still pass), `test_session_twenty_three_gate_modes` (repaired),
the D1240/D1242 guard module, `test_compatibility`, `test_upgrade_plan`,
`test_upgrade_command`, `test_deployment_suite_shape`, `test_release_contract`
(or the module extended), `test_generate_command`, `test_client_typescript`,
then the gate. Push; read CI. **This commit is the release candidate the
walker clones** — its SHA goes into Run 6's task statement, and its CI
verdict is read before the clone is made.

**Done.** *(filled by the run: the node ids as WRITTEN against as proposed,
D1236's table; `--setup-plan` both ways; the D1242 guard's reading; the
gate's last twenty lines, D1199.)*

### Run 6 — the second walk

**This run is not the executor's.** The executor of Runs 1–5 does three
things: prepares the clone, hands the operator the task statement, and reads
the record. Everything between is the walker's (ADR 0207, D1314). **The
executor does not open the clone while the walk runs, does not answer a
question from the walker, and does not edit the record.**

**Before the walk** (executor):
1. Read the branch head's CI verdict by full SHA (D1120). Green, or the
   walk does not start.
2. Inside WSL: `rm -rf ~/walk && mkdir ~/walk && git clone
   ~/projects/agentic-postgres ~/walk/agentic-postgres && cd
   ~/walk/agentic-postgres && git checkout <the Run 5 SHA> && git status
   --short` (empty) and `ls -l bin/apg.sh` (mode 755 — a local clone
   keeps the index's modes; a clone THROUGH `\\wsl$` would not, D1188's
   shape). **No `.venv`, no `.generated`, no `evidence/`** in the clone:
   the walker builds their own from the documentation. Confirm `docker
   version` answers in WSL.
3. Copy the task statement out of `docs/second-walk.md` between the two
   markers, byte for byte, into the scratchpad as `walk-prompt.txt`, with
   the SHA substituted where the statement says `<release>`. Nothing else
   is added to it. Hand the operator the file's path and the one sentence:
   *start a new session from `\\wsl$\Ubuntu\home\gmpar\walk\agentic-postgres`
   with this file's content as the whole first message*.
4. Stop. Write nothing else until the operator says the walk has ended.

**The walk** (the walker, per the statement): the fourteen steps of
`docs/new-team-member.md`, recording as it goes; the last two commands
`bin/apg.sh dx-record digest --record ~/walk/dx-record.json` and `bin/apg.sh
dx-record check --record ~/walk/dx-record.json`, whose output the walker
pastes into the record's `check_output` member (informational; the proof
recomputes). Its `apg dev down` is the last thing it types.

**After the walk** (executor):
5. Copy `~/walk/dx-record.json` to `~/projects/agentic-postgres/evidence/
   session-25-dx-record.json` (gitignored, beside the halves) and to the
   scratchpad. Run `bin/apg.sh dx-record check --record …` from THE
   WORKING CHECKOUT at the same SHA: the three readings and the exit code
   pasted into this run's Done. **Then read the record whole**, every
   `commands_run` line and every `undocumented_steps` entry, and write a
   D row for each thing the documentation did not give — whether or not
   the check was clean, because a walker that worked something out and
   did not call it undocumented is exactly the record `unnamed_commands`
   exists to catch, and the two readings must agree.
6. **If the check is clean and `reached_success_criterion` is true**: the
   record is the trip's `--dx-record-file`, and Run 7 proceeds. The clone
   is removed after `docker ps -a | grep apg-` is empty.
7. **If it is not clean**: the failures are documentation defects (a
   missing sentence, a wrong order, a command the docs never name) or
   product defects (a refusal the walker met that the docs could not have
   predicted). Each is a D row. Documentation repairs are a docs-only
   commit; a product repair is a code commit with its targeted modules and
   CI, and it moves the release candidate, so the bump commit's version
   stays and the SHA moves. **Then a SECOND walk by a NEW session**
   (never the same one — it has seen the defect) from a fresh clone at the
   repaired SHA, steps 1–5 again. **There is no third walk in this
   session** (§9): if the second is not clean, `documented_path` stays
   `not_run`, the record with its `blocked_by` is still handed to the
   trip (the proof fails with the list, which is the honest verdict,
   D686), and §10 carries the list.
8. This run's Done: the walker's `followed_by` block verbatim, the
   `check` output, the count of `commands_run`, the D rows, and which
   walk (first or second) produced the record the trip will read.

**Targeted:** none of the builder's — the walk writes no test. A docs-only
repair runs nothing before push (documentation only); a product repair
runs what it touches.

**Done.** *(filled by the run.)*
### Run 7 — the trip: the Stage 3 release deployed, one sweep

**This run is the only one that touches the host.** Split as the memory
records (*host-trip-shape*): the agent runs every `op`-side step over SSH
and hands the operator a numbered sheet of `sudo` lines; the operator pastes
output; the agent reads. One 15-minute sweep, a second only if the first
found a defect. **Never redirect a sudo deploy** (D972). **Read Session 24's
Run 8 Done before the day**, not its Run 7 (`CLAUDE.md` §2).

**Before the day** (agent, offline):
- `grep -n "goes wrong" -A20` in `docs/session-11-operator-guide.md` and the
  Session 17, 18, 20, 21, 24 plans (D977); Session 24's Run 8 Done whole;
  D1282, D1283, D1298–D1301 (what the last trip's proofs got wrong, and the
  fixture that chmodded `/tmp` on the host — **no fixture in the new live
  module touches a path outside `tmp_path`; assert it by reading**).
- `pytest --setup-plan` for `test_session25_release.py`,
  `test_session12_reuse.py`, `test_honest_readers.py`,
  `test_render_atomicity.py` with the variables SET (`APG_LIVE_HOST=1`, the
  two outputs, `APG_DX_RECORD_FILE=evidence/session-25-dx-record.json`, and
  `APG_FRESH_HOST_OUTPUTS` if located — D671, D676); outputs kept. The
  `DX-001` proof must be *planned*, not skipped, with the record file set.
- **Grep the tree for what the bump commit's message claims** (D1116):
  `git diff --stat main..session-25` against §5's list, one line each.
- Read the pushed branch head's CI verdict by full SHA (D1120). Green, or
  the trip does not start.
- Host scripts staged under `/home/op` (op-owned; survive a reboot), each
  with `export PATH="$HOME/.local/bin:$PATH"` and absolute paths, derived
  from Session 24's (`s24-*.sh`, `g24-*.sh` — **read each first**; the host
  was up 36 days at the last visit and `/tmp/g20-sentinel.py` was intact,
  but a restart since means rebuilding the sentinel derivation from
  `bin/session-25-check.sh --help`'s block): `s25-checkout.sh`,
  `s25-renders.sh`, `g25-offline.sh`, `s25-upgrade.sh` (ONE candidate this
  time — `candidate-16.json` from the branch head as op; 24's trip priced
  the three earlier ones), `s25-read.sh`, `s25-counts.sh` (the audit and
  idempotency counts again, D1255 — the second reading of a number that
  grows), `s25-kit.sh` (`bin/dr-kit.sh export` to a NEW dated directory,
  then `verify` from this checkout — the operational obligation D1282 left
  standing; **the gate's `--kit-dir` stays `kit-2026-09-11`**), `g25-host.sh`.
  Digests compared both ends.
- The record and the fresh-host document copied to the host under `/home/op/`
  as op (`scp` one file per invocation, D504) — they are read by root's
  sweep and must be readable by root: op-owned `0644` is fine; nothing in
  either is a secret (a walk record names commands and files; a deployed
  document names no value).
- The external script `/tmp/r7-external-25.sh` in WSL derived from 24's
  (if `/tmp` survived; else from `--help`'s external block), with an
  ephemeral `ssh-agent` and `--ssh-destination op@62.238.99.122` (D466).
  **WSL's outbound TCP may be gone** (`CLAUDE.md` §1): probe with a TIMED
  `/dev/tcp` connect whose status is read INSIDE the script before
  anything; if it is gone, the trigger is sleep/resume and the fix is a
  reboot — take it early.

**The day, in order.** `op` steps are the agent's over SSH; **`sudo` steps
are the operator's**, numbered on the sheet:

1. *(op)* `git bundle` of the branch head, `scp`, `git bundle verify`,
   fetch, `git rev-parse FETCH_HEAD` confirmed equal to the pushed SHA,
   checkout as `op`, `uv sync` (read README's materialize line). `s25-renders.sh`
   (the candidate rendered as op, `--render-only`).
2. *(sudo 1–2)* `bin/upgrade.sh check --project alpha-dev`; `plan --project
   alpha-dev --candidate /home/op/candidate-16.json` — **the verdict
   recorded** (D1081: `minor` confirms 1.6.0; a `major` is §9's stop). The
   same `plan` for `beta-dev`.
3. *(sudo 3)* `./deploy.sh --through-session 25 --project alpha-dev …` (the
   exact line from `deploy.sh --help` on the host — the agent prints it on
   the sheet), unredirected. *(sudo 4)* the read: the ledger via
   `bin/migrate.sh` (D941) → 32 applied, unchanged; which containers were
   recreated (expect none whose mount digest did not move — read the ages;
   a recreated `auth`/`mcp` pair would mean a lock digest moved, and
   nothing in this session compiles a lock); the doctor 10/10.
4. *(sudo 5–6)* the same on `beta-dev`: ledger → 34 (unchanged; the
   example set's table `app_private.project_schema_migrations`, ADR 0206);
   the doctor 10/10.
5. *(sudo 7)* `s25-kit.sh` as root: `bin/dr-kit.sh export` → a new
   `kit-2026-09-<dd>` storing outputs v18; `verify` → 0. *(op)* the kit
   copied off-host to `~/dr-kits/` in WSL (ext4 only; never the Windows
   drive) and verified there. The gate's `--kit-dir` is NOT moved.
6. *(sudo 8)* `sudo install -o op` copies of both deployed documents for
   `s25-read.sh`; **D1164's reading**: `stat -c '%U %y' .generated/alpha-dev`
   before and after the sweep; `s25-counts.sh` on both projects.
7. *(op)* `bin/session-25-check.sh --mode offline` on the host as op
   (`g25-offline.sh`) — the offline half FOR 25 written on the host too, as
   a control that the checkout there is the one measured here.
8. **Optional, before the sweep, the operator's decision (D860): the
   rotation performed.** If taken, it is Session 15's sequence, an
   irreversible `promote` at a TTY: a new key at `APG_AUTH_JWT_PREPARED_KEY`
   at the provider, a redeploy of alpha, `bin/rotate-signing-key.sh
   acknowledge` → `promote` → `retire`, the from-files declared to the
   sweep with `--rotated-jwt-from-file` (and the authenticator rotation
   with `--rotated-authenticator-from-file` for the second proof). It
   would move `bootstrap_identity`, `api_authorization` and
   `credential_rotation_planes` in the same sweep. **Not on the default
   sheet**; the sheet carries it as a separately numbered block the
   operator may decline, with `docs/session-11-operator-guide.md` §6's
   *if something goes wrong* for it read first. A declined block is
   recorded as declined, never as failed.
9. *(sudo 9)* **The one sweep**: `sudo bin/session-25-check.sh --mode host`
   with every declaration `--help` lists — the five Session 18 flags
   (`--kit-dir /home/op/…/kit-2026-09-11`, D1282), the sentinel derived,
   `--admin-password-file /root/alpha-dev-administrator`, both outputs,
   **`--dx-record-file /home/op/session-25-dx-record.json`**, and
   **`--fresh-host-outputs /home/op/<the outsider's document>`** if Run 1
   located it. **Run it detached** (`setsid nohup … > /home/op/g25-host.txt
   2>&1 < /dev/null &`, the exit code written to a file by the script).
   ~15 min. Expected: `stage_release` `passed`; `documented_path`
   **`passed` for the first time since Session 12** if Run 6's record was
   clean, else `failed` naming the list (and that is the honest verdict —
   D686: the document is written either way); `fresh_host` `passed` if the
   file was declared and carries, else `not_run` with the reason;
   `honest_readers` `passed` in both halves (D1310 — read the atomicity
   proof's node id in the JUnit: `passed`, not `skipped`); every Session
   22–24 claim `passed` again; the D478 five and `replacement_host_restore`
   `not_run`. **Read the gate's last twenty lines** (D1199). If a proof
   FAILS: read it, repair on the branch, CI, transport, redeploy only if
   the repair touches a container, and re-run **with `-k`** for that module
   (writes no evidence), then the sweep once more only if the repair
   changed what a claim reads.
10. *(op, then the workstation)* the host half copied to WSL; `--mode
    external` from the workstation → the external half. **The merge**, from
    a checkout at the branch head:
    ```
    python bin/write-session-evidence.py --session 25 \
      --host-input evidence/session-25-host.json \
      --external-input evidence/session-25-external.json \
      --offline-input evidence/session-25-offline.json \
      --output evidence/session-25.json
    ```
    Expected: **126 claims** (122 + 4), `not_run` between **4** (the D478
    five less nothing — they are five; so 5 + `replacement_host_restore` =
    **6**, plus `fresh_host` if not located = 7, plus `documented_path` if
    the walk was not clean = 8) — **write the count the document says, and
    the reason for each, into §7's table**; exit 5 with the document
    written is D686's contract.
11. *(sudo 10, optional — D1303)* if the operator chose to deploy the
    walker's project as a third project for the Studio step: Session 17's
    gamma sequence (`/home/op/<name>.yaml` outside the checkout, D971;
    providers, DNS grey-cloud, ACME once), the walker's own session
    launched again against it through an SSH forward the operator opens,
    the record's `studio` member appended by the walker, and the
    retirement with `--record` before the day ends. Not planned by
    default; if taken, it is a D row and §10 says what it cost.
12. D rows for what the day found; this run **Done.** with the document's
    claim table pasted, the `upgrade plan` verdict, the two ledgers, the
    two counts (D1255, second reading), the D1164 owner/mtime reading, the
    kit directory name and its verify, and whether the rotation block was
    taken or declined.

**Done.** *(filled by the run.)*

### Run 8 — the close: the tag, the report, the handoff

1. Fast-forward `session-25` into `main` after CI is green on the branch's
   last commit; delete the branch; push `main` through the Windows git.
2. **`docs/stage-4-decision-report.md` filled** from `evidence/session-25.json`
   and nothing else: every *[filled at the trip's close]* replaced with the
   number the document says; §3's `not_run` list reduced to what the trip
   left, each with its reason (the D478 five: their sessions' declarations;
   `replacement_host_restore`: D1028; `fresh_host` and `documented_path`
   as the trip left them, verbatim from the record and the sheet); §6 the
   recommendation, written as one and after the evidence: whether Stage 4
   is justified on this evidence, which of its pillars this document
   supports and which it is silent on, and that the public-endpoint
   decision (D1084) is Stage 4's first ADR and not a consequence of any
   number here. A docs-only commit; `docs/scope-closure.md` §14's rows
   that the trip closed removed; §1 recounted.
3. **The tag**: `git tag -a 1.6.0 -m "1.6.0: the Stage 3 release"` on the
   `main` commit both gates measured (the operator's, at their keyboard;
   the message file written with the Write tool, never a heredoc), pushed
   once. README's *Adopt `1.6.0`* names the tag and, once, that 1.3.0–1.5.0
   were session closes without tags (D1311).
4. `CLAUDE.md` §2 in the launch folder (copy it to the scratchpad first,
   its own rule): a `SESSION 25 COMPLETE` block in the shape of Session
   24's — what shipped, the document's numbers, the tag, what stays
   `not_run` and why, **what Stage 4 inherits** (§10), the next free `D`
   and ADR numbers; `STAGE 3` marked complete; §9 re-audited. Memory: the
   state file and the executor-model file updated (what the walk cost, and
   whether a fresh session could follow the statement).
5. Mark this run **Done.** with the document's claim table pasted, the
   `main` SHA, the tag's SHA, and the report's §6 sentence.

**Done.** *(filled by the run.)*

---
## 7. Evidence and claims

A claim's verdict is computed from the registry's node ids and JUnit
results, never hand-entered; three statuses (ADR 0163); a skip is not a
pass; a `-k` run writes nothing; an offline claim is declared, never
inferred (ADR 0202). **A walk is a measurement of a document at a commit**
(D1306), and its record names the documents it read; **a declared document
is carried to the reading release's version before it is judged** (D1312,
D1122's rule).

| Claim | Mode | Measured where | Expected at close |
|---|---|---|---|
| `dx_context`, `dx_walk_instrument`, `dx_hardening` | offline | the gate's offline mode here and on the host; CI | `passed` in `evidence/session-25-offline.json` and in `evidence/session-25.json` |
| `stage_release` | host | Run 7's sweep | `passed` |
| `documented_path` (Session 12's) | host | Run 7's sweep over Run 6's record | `passed` if the record is clean; `failed` naming the list if it is not — **never `not_run` once a record is declared**, and never softened |
| `fresh_host` (Session 12's) | host | Run 7's sweep over the operator's file | `passed` if located and it carries; `not_run` with *the operator did not locate the document* otherwise |
| `honest_readers` | host + offline | Run 7's sweep as root (D1310's repair) | `passed` in both halves, for the first time |
| `bootstrap_identity`, `api_authorization`, `credential_rotation_planes` | host | only if the rotation block is taken (Run 7 step 8) | `not_run` unless taken; `passed` if taken and the from-files declared |
| `port_allocation`, `deployment_convergence` and the other D478 names; `replacement_host_restore` | — | — | unchanged, with their reasons |
| every claim through 24 | host / external / offline | Run 7 | unchanged |

`evidence/session-25.json` is expected at **126 claims** (122 + 4). The
`not_run` count the plan predicts is **6** (five D478 names and
`replacement_host_restore`) with the walk clean and the file located, **7**
with one of those missing, **8** with both — and a `failed` on
`documented_path` is a different thing from a `not_run` and is reported as
what it is. A count outside that range is a finding, not a footnote.

---

## 8. Security invariants this session touches

The matrix in `tests/security/test_dx_surfaces_hardening.py::HARDENING_MATRIX`
is the closing review the stage plan asks for; its rows are the stage plan
§8's invariants, its columns the three surfaces, and Run 3's Done paragraph
pastes it whole. What this session itself adds or moves:

- **The DX layer holds nothing the human does not hold** (stage plan §8):
  `APG_PROJECT` is a path to a manifest the human already holds, announced
  every time it is used; the completion script embeds one path and no
  value; `dx-record` reads a file the walker wrote —
  `test_the_default_is_announced_on_stderr_each_time_it_is_applied`,
  `test_the_script_embeds_no_verb_and_no_flag`.
- **A report may not substitute an answer** (ADR 0195): an unreadable
  `APG_PROJECT` is exit 2 before `exec`, never a verb's confused refusal;
  `dx_record.load` has three outcomes; a document the migrators cannot
  carry names the version it stopped at —
  `test_an_unreadable_default_is_refused_before_exec`, the carry-then-assert
  proof's failure message.
- **Nothing prints a credential** (D105): the three surfaces re-run with a
  planted secret and a planted file on their three cheapest exits, and the
  two new verbs held to `DX-002`'s guards by being listed —
  `test_no_dx_command_prints_a_planted_secret_on_its_three_cheapest_exits`.
- **A generated or served artefact carries no credential**: the union scan
  over Studio's files, the committed client and a fresh dev state directory,
  with the two declared 0600 files as the only permitted matches —
  `test_no_dx_artefact_carries_a_credential_but_the_two_declared_files`.
- **The DX modules are clients**: no `services/` import, no host path —
  `test_no_dx_module_imports_services_or_names_a_host_path` (ADR 0084's rule
  applied to the three modules Stage 3 added, and to their `bin/` drivers).
- **A walker holds no credential, no host, no `sudo`** (ADR 0207): the task
  statement says so and the record's `commands_run` is read for a `sudo` or
  an `ssh` — a match is a finding, not a pass.
- **The identity a proof runs as is the identity it measures** (D1165,
  D1310): the atomicity proof re-enters as the checkout's owner under root
  rather than skipping; the offline claim proofs are run as root in rig 25c
  before the trip.
- **An offline claim cannot report a live half** (ADR 0202): `stage_release`
  is undeclared; the per-session assertion (D1237) for this session's three.
- **A release is what the tree names** (`REL-STAGE-001`): the constant, the
  `VERSION` file, the deployed documents and `upgrade verify` agree, and
  the plan's class is the one the constant's comment proposes.

---

## 9. Stop conditions

- **Rig 25c's root arm does not skip** at `bb93a53`: D1302's row is wrong
  about the cause; stop and read why before lifting anything.
- **Rig 25a finds a verb whose `--help` names `--project` in prose but does
  not take the flag**, and the anchored regex cannot separate the two: stop;
  do not fall back to a kept list — record the verb, fix its usage text
  (a usage that names a flag it does not take is `DX-002`'s failure), and
  measure again.
- The dispatcher's default would have to be applied to a verb with a
  subcommand that parses `--project` differently (rig 25a's `=` measurement
  disagrees across verbs): stop; the default is applied to the measured set
  only and the disagreement is a row.
- A walk that would need the executor to answer a question, hand over a
  credential, run `sudo`, or touch the host: stop; the answer is an
  `undocumented_steps` entry and the walk continues without it.
- **A third walk** would be wanted: stop; two is the session's budget (§5
  Run 6), and the claim stays `not_run` with the list.
- The operator locates the fresh-host document and `carry_to_current`
  cannot carry it: stop; the proof reports the version it stopped at and the
  claim stays `not_run`; do not edit the document.
- Run 7's `upgrade plan` prices 1.6.0 as **major**: a stop for that deploy,
  a row, and the operator's decision.
- A Session 22–24 claim goes red in the sweep and the tidy fix is on the
  proof's side (stage plan §9): stop.
- A `test_honest_readers` or the atomicity proof still SKIPS as root in the
  sweep: read `as_checkout_owner` first (a root-owned checkout takes the
  remaining skip branch by design); do not soften it.
- The evidence writer refuses a `--session 25` merge for a reason the plan
  did not predict: stop, record it, and read `write-session-evidence.py`
  rather than editing a half.
- The rotation block is taken and `promote` is refused by an unacknowledged
  verifier: stop at the refusal; `abandon` is the documented way back and
  the sweep runs without the from-files.
- CI red on the branch: stop and read the log; a cancelled run is not a
  failed one (D1059).
- Docker absent in WSL: stop; do not write a proof that skips and call it
  offline evidence.
- WSL has lost outbound TCP on trip day (`CLAUDE.md` §1, measured
  2026-09-13): the fix is a reboot, taken early; the push goes through the
  Windows git over `//wsl$/`; the CI verdict is read through the Windows
  `gh`. Nothing in this session needs a registry.

---

## 10. Open items this session carries and creates

**Carried in, untouched:** D1045 (the provider error body);
`replacement_host_restore` (D1028); the five D478 names; D1211 (PostgREST
beside `apg dev` stays a rig); the four unswept modules D1240 names (the
storage plane's decision); D1203; D1205 (the Python client — priced again in
the report's §5, not built); D1209; D1248 (the audit filters); D1255 (the
retention decision — the counts are read a second time on the trip and the
decision stays the operator's); the 21 unclaimed requirements (ledger §4,
reportable one declaration at a time); D1276 (rigs that reach a published
loopback port); D1278 (`APG_ADMIN_PASSWORD_FILE` outside the roster);
Studio's live RLS half (Session 24 §10); the three Studio envelope rows as
this machine's; the signing-key cutover and ADR 0122's repairs never timed
on a host; no span leaves the process; the OOM history; the apt pin's end
date; `requirements-dev.in` pinning nothing.

**Stated here, and taken or offered:**

- **The DR kit re-export** (D1282): taken on the trip as an operational
  step (Run 7 step 5), with the gate's `--kit-dir` left on `kit-2026-09-11`
  because REC-KIT-003's claim IS the version gap. The next release that
  moves the outputs schema must re-read that row before pointing the gate
  anywhere.
- **The rotation performed** (D860): offered as an optional, separately
  numbered block on the sheet (Run 7 step 8), never a run's action. If
  declined again, the ledger's §2 says so with the date, and it is the
  first item on Stage 4's bill (stage plan §6: a credential that travels
  rotates first).
- **`honest_readers`** (D1302): repaired offline (D1310) and collected in
  the one sweep; no second sweep.

**Created here, not addressed:**

- **A person's walk has not happened** (ADR 0207's residual). An agent's
  clean walk proves the path holds for a reader who follows it; a person's
  would be a second record, and `docs/second-walk.md` is written so that a
  person can be handed the same statement. Whoever has a person available
  runs Run 6 again and adds the record beside the first.
- **Studio was read, not opened, in the walk** (D1303), unless the
  operator took Run 7 step 11. The deployment-side half of an adopter's
  path — capture the snapshot, generate again, open Studio against one's
  own deployment — is documented and is `fresh_host`'s shape to prove, on
  a host built to be deleted.
- **`APG_PROJECT` reads a verb's `--help` on every invocation it applies
  to** (~15 ms, rig 25a). A verb whose usage is expensive would make the
  default expensive; none is today, and the envelope does not carry the
  number because it is below anything the envelope measures.
- **The completion script is bash's.** A zsh or fish user has `--list` and
  `--help`; a second shell is one more `case` arm printing a second
  script, and nobody has asked.
- **`dx_record.documented_commands` is a text scan** (D464's shape) over
  five documents and the guides; a command written in a code block the
  regex does not match is invisible to it, in the direction that makes the
  check stricter (an unmatched documented command makes a record's use of
  it look unnamed), which is the safe direction and is recorded here so the
  first false failure is read as this and not as the walker's.
- **The intermediate versions 1.3.0–1.5.0 have no tag** (D1311), by
  decision; README says so once.
- **What Stage 4 inherits, named so no session inherits it silently**: the
  public-endpoint decision as its first ADR (D1084), with the seam still a
  refusal; the rotation performed before any credential travels; the
  retention policy for `agent_audit` before any hosted reading; the two
  fields named `capabilities_sha256` (D930); the Python client (D1205); the
  four unswept storage modules (D1240); the audit filters (D1248); a
  person's walk (above).

---

## Appendix — what to consult, and how a run is executed here

**Consult, in this order.** `docs/plans/stage-3-plan.md` §5 *Session 25*,
§4, §6, §7, §8, §9, §10, §11 and its rows D1065, D1074, D1079, D1080, D1081,
D1084; this document's §1; `docs/plans/session-24-implementation-plan.md`
§1 (D1243–D1302, the last session's measured facts — D1275 for what an
administrator sees in Studio, D1280 for the guard this session repairs,
D1282/D1283 for the trip), its §5 Run 6 (the bump's exact steps), Run 7
(the sheet's shape) and Run 8's Done (the record of the completed trip),
and its appendix; `docs/plans/session-23-implementation-plan.md` §5 Run 1
(a measurement run's shape); `docs/plans/session-19-implementation-plan.md`
§1 (what an outsider measured, D1033–D1060) and `FINDINGS.md`'s header in
the launch folder (the outsider's position — the shape ADR 0207 formalises);
`docs/plans/session-12-implementation-plan.md` §1 D693 and D703 (what
*derived by diff* means and what it misses); `docs/scope-closure.md` whole
(re-audited in Run 5); ADR 0002, 0014, 0037, 0045, 0089, 0093, 0162, 0163,
0195, 0197, 0198, 0201, 0202, 0203, 0204, 0205, 0206; `bin/apg.sh` whole;
`tests/contract/test_apg_dispatcher.py` whole; `tests/deployment/test_session12_reuse.py`
whole; `tests/contract/test_honest_readers.py` lines 100–140;
`docs/new-team-member.md` whole (read it as the walker will, before Run 4);
`/tmp/r25a.sh` … `/tmp/r25f.sh` in WSL with their `.txt` outputs after Run 1
— **copy them to the scratchpad before the first `wsl --shutdown`**.

**How a run is executed in this repository** (the short form of `CLAUDE.md`
§1 and §5; read those, they are the record of what each of these cost):

- The Bash tool is Git Bash on Windows. The tree is in WSL:
  `wsl bash -lc "cd ~/projects/agentic-postgres && . .venv/bin/activate && …"`.
  Anything with nested quotes, `$VAR`, a heredoc or a loop variable goes in
  a script written with the Write tool to `\\wsl$\Ubuntu\tmp\x.sh` and run
  with `wsl bash -lc "bash /tmp/x.sh > /tmp/x.txt 2>&1"`, printing its own
  exit codes; read the output back through `\\wsl$\Ubuntu\tmp\x.txt`.
- **The venv does not install the package.** Every Python that imports
  `agentic_postgres` outside pytest needs `PYTHONPATH=src`.
- File content and commit messages are written with the Write tool and
  read by the script (`git commit -F /tmp/msg.txt`). Never a heredoc for
  content.
- `chmod 755 bin/*.sh bin/*.py deploy.sh` before every `git add`. A file
  written through `\\wsl$\` has lost its executable bit.
- Never pipe a suite or a gate into `tail`; redirect to a file, `rm` it
  first. **Run a long gate detached** (`setsid nohup bash /tmp/x.sh
  >/dev/null 2>&1 < /dev/null &`, the exit code written to a file from
  inside WSL) and never beside a CI watcher.
- `PYTHONDONTWRITEBYTECODE=1` and `__pycache__` cleared before a battery;
  same-length rewrites within a second import stale bytecode (D1198).
- A run's commit: `ruff format && ruff check` (print the exit code), the
  targeted modules — each named module checked for existence individually
  (D1104) — the derived-document generators whose inputs moved, `chmod`,
  `git add -A`, commit with `-F`, push to `session-25` **through the
  Windows git** (`git -c "safe.directory=//wsl$/Ubuntu/home/gmpar/projects/agentic-postgres"
  -C "//wsl$/Ubuntu/home/gmpar/projects/agentic-postgres" push origin
  session-25` — WSL has no outbound HTTPS on this machine), then read that
  SHA's verdict: `gh api "repos/Virabyan99/agentic-postgres/actions/runs?head_sha=<40
  chars>" --jq '.workflow_runs[] | [.id,.status,.conclusion] | @tsv'`,
  judged on HTTP status, three buckets (D1059). **Read it every time**
  (D1120).
- **A commit message is not evidence that the diff contains what it says**
  (D1116): `git diff --stat` against the list of repairs it claims, one
  line each, before the message is written.
- A run that renames, removes or adds a test function puts
  `test_acceptance_registry` in its targeted list (D1119); one that adds or
  removes a `bin/` command puts `test_cli_contract` there (D1014) and
  `git add`s the command first (D1188); one that adds any `document[...]`
  read to a `bin/` command puts `test_container_selectors` there (D1184).
- **A run that MOVES a definition greps the moved TEXT as well as the moved
  name** (D1187): `_as_checkout_owner`, `OPERATOR_INPUTS`, `_COMMAND`.
- **The targeted list is run ONCE, at the run's close, scaled to the
  change.** After a failure re-run only the module that failed; CI is the
  full check (the operator has asked for this thirteen times). During a
  run, run the one module under the hand.
- **A targeted list is derived from the tree, never from the plan's text**
  (D1146, D1149): the lists above name what a run ADDS; the grep names what
  it CHANGES.
- Documentation-only commits run nothing before push. Generated content
  (the ADR index, the registry matrix, the envelope, a catalog) →
  `bin/session-01-check.sh` alone. Code → the targeted modules. The gate on
  a clean tree at Run 4's and Run 5's close and on the host in Run 7,
  never at a run's close.
- A rig is a throwaway script with a control arm, its output in a file and
  its numbers pasted into the Done paragraph. Never write a measurement you
  did not run (D267). `docker rm -f -v` every container it started; `apg
  dev down` in `finally`; `docker ps -a | grep apg-` empty afterwards;
  delete what a rig publishes under `.generated/<key>` unless the key
  already existed.
- The battery: every mutation's anchor pre-flighted to match exactly once
  and a miss fatal (D269); a paired control the mutation cannot reach, in
  the same invocation, green (D499); the reader distinguishes `FAILED` from
  `ERROR` (D386); restore by copy and `cmp`, never `git checkout --`; a
  survivor is evidence and is read as such (D493, D498); a scan over a file
  with comments strips them first (D1197). **Every new test module carries
  `pytestmark` before its first test** (D1240), and the D1242 guard is in
  the targeted list of every run that adds a module.
- **A proof calls the product's own command** (D1114, D1117): the
  dispatcher proofs run `bin/apg.sh`; the record proofs run `bin/apg.sh
  dx-record`; the live release proof runs `bin/upgrade.sh`.
- **Runs 1–6 touch no host.** No SSH, no `sudo`, no deploy. If a step seems
  to need one, it belongs to Run 7 and goes on the sheet.
- **The executor does not walk.** Run 6 is a different session's; the
  executor prepares, waits, reads.

**Grep the plans before measuring a third party.** bash completion and
`complete -F`: nothing in the plans (rig 25b is the first measurement);
`sudo`'s environment stripping: `CLAUDE.md` §1's `sudo -n` note and
D1110; `carry_to_current`: D1134 (Session 21 Run 4) and D1122; the record
format: Session 12's plan §5 Run 3 (`git grep -n "DX_RECORD_FIELDS"
docs/plans`); the pinned image running as root with the checkout mounted:
D1239's workaround (Session 23 Run 6); Docker's loopback publication and
the daemon assumption: D1172, D1276; the outsider's method: `FINDINGS.md`
§*Method*. Nothing indexes the ~1,300 measured facts by subject; `grep` is
the index.
