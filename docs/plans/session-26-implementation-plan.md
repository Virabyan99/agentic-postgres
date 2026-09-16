# Session 26 — The documentation session: the upgrade guide, the current operator guide, and where the new team member's page lands

**Status:** executed 2026-09-16, after Session 25 closed Stage 3 at `a16cb84`
tagged `1.6.0`, with `evidence/session-25.json` reporting 126 claims, 119
passed, **1 failed** (`documented_path`), 6 `not_run`.
**Brief:** two documents a database product must have did not exist — an
upgrade guide, and operator documentation for any release after Session 11 —
and `docs/new-team-member.md` handed its reader to a set describing an older
product. Produce them from measured material; measure, do not recall; say
where the offline path ends; write an ADR where a decision has real
alternatives; verify nothing — a cold reader will.
**Shape:** four runs, no code, no host mutation, no walk. Documentation only.
**Product version at close:** unchanged, `1.6.0`, `CURRENT_SESSION` 25.
**Next free:** D1388, ADR 0209.

---

## 0. Where the session starts

Stage 3 is closed and its release is deployed on both projects, and the one
claim it closed `failed` is the one about whether a stranger can follow the
documentation. Two walks by cold readers produced seventeen findings between
them (D1351–D1367), all repaired, nine after the last cold reader had gone.
Every one of those findings was on the adopter's offline path. What nobody
had walked — because nothing described it — was the path that begins where
that one ends: a host, an upgrade, the fourteen sessions of operating surface
built since the last operator guide was written.

This session runs before Stage 4 is planned, and it is the second of the
three things the Stage 4 decision report says the stage inherits, taken out
of order on purpose: a walk of this release's documentation before anything
is added to it cannot be arranged while the documentation to walk does not
exist.

**Two decisions were taken deliberately rather than by default**, and both
are in ADR 0208: one current operator guide supersedes the per-session set,
and the upgrade guide is the operator's page with the checkout's half inside
it. §1 records what was measured against each.

**The method, because it is the point.** Every command on both pages is read
from the `--help` the release in the checkout prints (captured whole:
`/tmp/s26-help.sh` over `deploy.sh`, every `bin/*.sh`, the `apg` verbs and
the sub-verbs — 4,478 lines), and every sequence is one a trip executed, with
its date and its plan's §5 Run 7 *Done* paragraph named beside it. The host
scripts of 2026-09-15 (`/home/op/s25-*.sh`, `g25-*.sh`) were fetched from
the host and read whole. The release table was read from each bump commit
with a script rather than from memory (`/tmp/s26-releases.sh`). Where a step
could not be found measured, the page says so in the step (§13 of the
operator guide is a list of exactly those).

---

## 1. Divergences

D1379–D1387. Rows marked **recorded** are not repaired here, with the reason.

| D | Said | Measured or read | This session | Why it matters | ADR |
|---|---|---|---|---|---|
| **D1379** | `docs/README.md` §*Operator guides*: *"One per session, each covering the host sequence that session added."* | The newest is `session-11-operator-guide.md`; `CURRENT_SESSION` is 25. Fourteen sessions have no guide. What describes operating them is the plans' §5 Run 7 *Done* paragraphs — the builder's notebook, excluded from a walk by rule (ADR 0207 §1). The per-session pattern produced ten guides and then none, which is itself the measurement about whether it scales. | **ADR 0208 §1**: one current guide, `docs/operator-guide.md`, derived by diff from Session 11's, the Run 7 *Done* paragraphs of 12–25 and the 2026-09-15 host scripts; edited in place each release. The ten stay in the tree unedited, indexed as *records, not instructions*; four are named by `test_repository_contract.py`, one by a product message, all by `dx_record.GUIDE_GLOB`, every one by a row. | Deleting them would break a shipped-file contract and a scan; keeping them under a heading that implied they were current is what sent two readers to a five-versions-old sequence. | 0208 |
| **D1380** | `bin/upgrade.sh --help`'s last sentence is the whole documented upgrade path: *"To perform an upgrade, run ./deploy.sh --through-session N after this reports a plan that may proceed."* | Every trip since Session 13 performed steps that sentence does not name, each measured and each in a plan's *Done* and nowhere an operator looks: an ownership repair before the render (D1151); the candidate rendered **as `op` with the host's `capabilities.yaml`** (D1371, first sweep of 2026-09-15); `plan` `BLOCKED` when a manifest moves with the release, split into two deploys (D1107); `provision-host.sh --apply` for units a release adds (2026-09-05, 2026-09-06) and `edge.sh restart` for the edge's static configuration (D811); the ledger read rather than the migrator's line (D941); a snapshot behind its own deployment until the next deploy (D1118); the kit re-exported and **not** handed to the gate (D1282). | `docs/upgrade-guide.md`: what an upgrade is, the release table read from the bump commits, the checkout half, the host sequence step by step with dates, skipped releases (measured 1.2.0 → 1.5.0 in one deploy on 2026-09-13), a `major` (never produced here, said so), and what to do when a step refuses. | An absence, not a defect in any one command: each command's help is right about the command and silent about the person. | 0208 |
| **D1381** | `bin/upgrade.sh --help` lists three verbs and four options (`--project`, `--installed`, `--candidate`, `--json`). | `bin/upgrade.sh check --help` (and `plan`, `verify`) prints the **parser's** usage — `--also {migration_added, api_operation_added, api_operation_removed, api_operation_changed, secret_optional_added, document_schema_migratable, document_schema_needs_operator_input, operator_manifest_invalidated}` — and exits 2 *the following arguments are required: --project*, rather than printing help. D743 (Session 13 Run 4) is why the flag exists: a rendered document records no migration count and the checkout's lock describes the checkout, so **whether a release adds a migration cannot be derived by the plan** and is an operator's declaration. A migration is the one change that makes a minor irreversible by image rollback (ADR 0162 §3). | **Recorded.** The upgrade guide's §3 step 4 names the flag as the parser prints it, says the top-level help omits it, and tells the operator to read the release table or `git diff … -- migrations/released.lock.json` and declare it. The help text is a `bin/` script's and this session edits no code. | The class that decides reversibility is invisible to the command a reader is told to run, and visible only to one who runs it wrong. | — |
| **D1382** | `docs/api-operations.md` §*Rotating a credential*, step 4: *"Redeploy through session 5."* — beside a code block that says `--through-session 25`. | The page is in `test_session12_documented_path.CURRENT_PATH_DOCUMENTS` and its guard passed: `SESSION_ARGUMENT` matches `--through-session N` and `--session N` only, and *through session 5* is prose. D678's class (three `--through-session 5` flags surviving from Session 5 into a Session 11 procedure), one regex away from the guard written for it. | The line corrected to *the current session*, naming the block below as the number and this row as why. **The guard's blind spot is recorded, not widened**: a test change is code. | A reader who trusts the prose over the block deploys through session 5, and `deploy.sh` accepts any number below `CURRENT_SESSION` (D59). | — |
| **D1383** | `dx_record.DOCUMENT_ROOTS` (four pages) plus `GUIDE_GLOB = "session-*-operator-guide.md"` is what a walk's record is read against; `test_session12_documented_path.CURRENT_PATH_DOCUMENTS` is what the offline documented-path guard scans. | Neither names `docs/operator-guide.md` or `docs/upgrade-guide.md`, and the glob cannot match them. Both lists are Python. So the two new pages are outside both scans: a command named only there reads to a walk as undocumented (the stricter direction, scope-closure §14), and nothing in the tree checks their commands, flags or session numbers. | **Recorded, and worked around for this session**: the README's three guards were applied to both pages by a script (`/tmp/s26-selfcheck.py`) — every named command exists and is executable, every `--session`/`--through-session` is 25, every flag on a command line is in that command's `--help`; **19 usages read, 0 problems**. Adding the two pages to both lists is one line each with a test, Stage 4's first code session's. | A page written to the rule and checked once by hand is not a page the tree keeps to the rule; D505's family is what the guards exist for. | 0208 |
| **D1384** | `docs/new-team-member.md`'s close: *"it is the [operator guides](README.md#operator-guides) rather than this page"*; step 11's order, item 2: *"deploy the project once (`./deploy.sh --project project.yaml ...`)"*. | The anchor lands on a table whose newest row is Session 11's, and the ellipsis is the whole of what the page says about a deploy. The reader who finished fourteen offline steps is handed a set that describes a release with 22 migrations, no project set, no agent surface over their own tables and no Studio. | Both point at `docs/operator-guide.md` §3 (a host from empty and a first project), and the close says which three stopped steps come back when the deploy exists, and that moving it later is the upgrade guide, whose §1 is the checkout half. | The adopter's map was 0→60 and then a gap; this is the gap. | 0208 |
| **D1385** | `docs/handoff.md` §*The session documents* names the Session 5, 6 and 7 guides and calls the Session 7 guide's §5.4 *"the host sequence for the trip that has not happened yet"*; §*The deployment host* ends *"Everything else about operating it is in the Session 2 operator guide."* | The Session 7 trip happened in Session 7. The paragraph survived eleven sessions of edits around it because nothing reads it; D623's class (a status line nobody checks). | Rewritten as *The operator's documents*: the two new pages first, the per-session guides named as records, and this row. The Session 2 pointer kept for the one thing it is still right about (§0, the release and the operator user on an empty host). | The handoff is the second page a new reader is sent to. | — |
| **D1386** | README §*Adding your own tables*: `schema_version: 5` for a manifest that names `migrations.set`; `docs/new-team-member.md` steps 9 and 11: `schema_version: 6`; `docs/migrations.md` §*A project's set*: 5. | All three validate (`SUPPORTED_PROJECT_SCHEMA_VERSIONS` is 1–6): 5 admits `migrations.set`, 6 adds `mcp.capabilities`. A reader who follows two pages is given two numbers for one key, and D1363 recorded the same pair inside one page. `test_the_readme_tells_an_adopter_what_adding_a_table_costs` asserts the literal `schema_version: 5` in the README's section. | **Recorded.** Moving the README's number moves a contract test, which needs an ADR; the operator guide's §1 table says which version admits which key so the pair reads as two valid answers rather than a contradiction. | Two numbers for one field is the shape that made a walker infer an ordering (D1363). | — |
| **D1387** | `bin/dr-kit.sh --help` prints usage for `export` and `verify` without root; a verb's `--help` is a read. | `bin/dr-kit.sh export --help` as an unprivileged user exits **3**: *export needs root: the bootstrap state and the deployed document are root-owned* — the root check runs before the help is printed (measured 2026-09-16 in the help capture; `verify --help` prints argparse's usage and exits 0). No other verb in the 4,478-line capture refused `--help` for want of root. | **Recorded.** A `bin/` script; not edited here. The operator guide names `dr-kit.sh --help` (top level), which prints. | A reader told to read a verb's help is refused for a reason that has nothing to do with reading. | — |

---

## 2. What the session adds

No requirement, no claim, no migration, no command. Three pages, one ADR,
five page edits, this plan.

| File | What |
|---|---|
| `docs/decisions/0208-….md` | The two decisions with their alternatives |
| `docs/upgrade-guide.md` | The upgrade guide (D1380) |
| `docs/operator-guide.md` | The current operator guide (D1379) |
| `docs/README.md` | The *Operator guides* section rewritten: the two pages, the ten as records; the D-count line |
| `docs/new-team-member.md` | The close and step 11's order land on the operator guide (D1384) |
| `docs/handoff.md` | *The operator's documents* (D1385) |
| `docs/api-operations.md` | Step 4's prose (D1382) |
| `docs/decisions/README.md` | The 0208 row |

---

## 5. Build order

### Run 1 — Read, then measure. **Done.** 2026-09-16

Read whole, in this order: `CLAUDE.md` §2; `docs/stage-4-decision-report.md`;
the Session 25 plan's Run 7 and Run 8 *Done*; `docs/README.md`;
`docs/new-team-member.md`; `docs/session-11-operator-guide.md` (the diff base,
D613); `docs/second-walk.md`; `docs/handoff.md`; D1351–D1378 whole; the Run 7
(or trip) *Done* paragraphs of every plan 12–24; ADR 0162; ADR 0207 §1;
`docs/scope-closure.md` §1, §2, §14; the headings of every *Running a
deployment* page and `docs/migrations.md` §*A project's set*; the rotation
sections of `docs/api-operations.md` and `docs/session-06-operator-guide.md`;
README's *Adding your own tables*, *Deploying*, *Operating a deployment* and
*Checks*; `tests/contract/test_documentation_index.py` and
`test_session12_documented_path.py` whole; `dx_record.DOCUMENT_ROOTS` and
`GUIDE_GLOB`; the workflow that runs CI.

Measured: **every `--help`** (`/tmp/s26-help.sh`, 4,478 lines, every exit
code printed — which is how D1381 and D1387 were found); **the release table**
from each `VERSION`-moving commit (`/tmp/s26-releases.sh`: version, session,
migration count, outputs version, project and capability schema sets, the
`projects/` directory's presence, tags); **the host scripts** `s25-checkout`,
`s25-renders`, `s25-upgrade`, `s25-read`, `s25-kit`, `s25-counts`, `g25-host`,
`g25-offline`, fetched whole over Git's ssh from Windows (WSL's outbound TCP
was not probed and not needed); the deploy's step names and exit codes from
`bin/deploy-project.py`; `upgrade.py`'s exit codes and verdict vocabulary;
`installed_release.RELEASE_ROOT`; `KIT_FIRST_OUTPUTS_VERSION`;
`SUPPORTED_PROJECT_SCHEMA_VERSIONS`; the systemd units' `Documentation=`
paths; which tests name which per-session guide.

**Not measured, and said so on the pages**: anything in the operator guide's
§13.

### Run 2 — ADR 0208, the upgrade guide, the operator guide. **Done.** 2026-09-16

The ADR carries both decisions and five alternatives, each with the reason it
lost. The upgrade guide is nine sections; the operator guide fourteen. Every
command from the capture; every sequence dated; the offline path's end stated
where the guide hands to the new team member's page (D1357's four commands
named in the operator guide's §7 and the new team member's step 11).

### Run 3 — The index, the handoffs, the corrections, the check. **Done.** 2026-09-16

Eight exact-once edits by a count-asserted script (`/tmp/s26-edits.py`; every
anchor matched once). Then `/tmp/s26-selfcheck.py` over the two new pages —
the README's three guards, 19 usages read, **0 problems** — and the targeted
modules, once: `test_documentation_index`, `test_session12_documented_path`,
`test_acceptance_registry`, `test_repository_contract`: **284 passed, 0
failed, 62 s**. No gate, no full suite, no host (`CLAUDE.md` §5's table:
documentation only runs nothing before push; the index test is what an added
page owes).

### Run 4 — The close. **Done.** 2026-09-16

Committed as **`c5ad14d`** on `main` with the message written to a file and
`-F`; pushed through the Windows git (WSL's outbound TCP was not needed and
not probed). **CI on `c5ad14d`: run `35067565362`, all three jobs `success`**
— Session 1 gate, Session 2 offline contract, P0 inventory — read by full
SHA. `CLAUDE.md` §2 in the launch folder carries a `SESSION 26 COMPLETE`
block (the file copied to the scratchpad first, its own rule) and §9 a row
for the two unverified pages; memory updated. This paragraph lands in a
documentation-only commit after the one it describes, as Session 25's Run 8
did.

---

## 7. Evidence

None written and none owed: this session changes no claim's verdict, deploys
nothing and runs no gate. CI on the pushed commit is the check (the workflow
runs the Session 1 gate on every push to `main`). The two pages' own check is
the cold reading the operator is arranging — and this session's rule is that
its author's reading of its own pages is not evidence they work (ADR 0207's
reason, applied to the operator's path).

---

## 9. Stop conditions

- **No code.** Two rows (D1381, D1383) and one usability defect (D1387) name
  one-line code changes; each is Stage 4's, with its test.
- **No walk, no host, no verification of the pages by their author.**
- **Never a third operator guide.** A release edits `docs/operator-guide.md`
  in the bump's own commit (ADR 0208 §*Consequences*), or the page is wrong in
  the reassuring direction from that release on.

---

## 10. Open items this session carries and creates

- **The cold reading** of both pages, arranged by the operator. Its findings
  are the pages' evidence; nothing here is.
- **D1383**: `dx_record.DOCUMENT_ROOTS` and `CURRENT_PATH_DOCUMENTS` gain the
  two pages, one line each, with the test that would have caught their
  absence.
- **D1381**: `bin/upgrade.sh --help` names `--also` and its eight classes, or
  the plan derives `migration_added` itself (D743 says why it cannot today).
- **D1387**: a verb's `--help` prints before its root check.
- **D1386**: one number for `schema_version` across the three pages, by an
  ADR that moves the README's guard.
- **No test holds the two pages to the release** (ADR 0208 §*Consequences*):
  the operator guide's §1 table and the upgrade guide's release table are
  typed from measurements and will drift the first release that does not
  move them.
- Everything Stage 4 already inherited, unchanged: the rotation (D860), the
  Docker question on the host (D1375), `render-jwks`'s sentence (D1374), the
  retention policy (D1255), the public-endpoint decision (D1084).
