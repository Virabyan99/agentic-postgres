# Session 12 — reuse proof and release candidate

**Deliberately short.** Sessions 10 and 11 ran to ~1,740 and ~1,300 lines because
they built planes. Session 12 builds almost nothing: three of its four
requirements already have working machinery and are missing a *witness*, and the
fourth is written. What earns a plan here is §1 and §7 — what has been measured
that the session summary does not say, and **what each claim may honestly report
before its live half exists.** Everything else is support.

---

## Status — read this first

```
LOCAL           Clean and pushed at the commit that carries this plan. Three
                commits sit above Session 11's close: the plan + Run 1, Run 2's
                offline half, and this handoff.
HOST            **ab3d488** -- Session 11's close. It has NONE of Session 12.
                Run 4 ships it; nothing before Run 4 needs it.
CURRENT_SESSION **11**, deliberately. Moving it to 12 activates ALL FOUR
                Session 12 requirements at once (D690), so it moves in Run 4
                once every offline half exists -- not before.
DONE            Run 1 (DEP-ISO-001, five proofs, dry-run clean against both
                live documents). Run 2's OFFLINE half (one new proof; three
                already existed unattributed).
NEXT            Run 3 -- DX-001 and DEP-001 offline halves.
gate            **session-01-check PASSED at this commit.** Re-run it after any
                code change; it refuses a dirty tree, so commit first.
divergences     D689-D692 recorded here. **Next free: D693.**
```

**What a fresh reader must not re-derive**, because each cost a measurement:

1. **The bump is all-or-nothing** (D690). `CURRENT_SESSION = 12` forces every
   Session 12 requirement to stop being a placeholder in the same commit.
2. **No shipped command removes a project** (D691). `compose.sh` refuses
   `--volumes` in project mode; `project-runtime.sh down` preserves the volume
   on purpose. Do not add a destroy-the-data verb (§9).
3. **`--destroy`'s confirmation check is unreachable in a checkout** (D692):
   exit 3 for root fires before `--confirm` is read.
4. **No third project is created** (§0). That decision is taken.

---

## 0. Where Session 12 actually starts

Session 11 closed at `ab3d488`, evidence merged at `e49ea6a`: **56 of 57 claims
passed**, 117 of 127 P0 requirements complete. Both projects run on
`62.238.99.122` through session 11. `doctor.sh` reports 8 ok / 0 warning /
0 problem / 0 unknown.

The four requirements left are `DEP-001`, `DEP-ISO-001`, `DEP-REMOVE-001` and
`DX-001`, all P0, all still `@pytest.mark.future` placeholders.

**One decision is already taken and this plan is written under it: no third
project is created.** The host has run two projects since Session 3, isolation is
a pairwise property, and a third adds `n=3` to something already measured. What a
third project would have been *for* is being the artifact an outsider produces —
and that is a question about a person, not a project count.

---

## 1. The divergence table

Six columns, the house shape. Rows are measured facts, not predictions.

**Next free number after this table is D701.**

| # | Summary says | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D689** | The session summary: *"Complete the explicit two-project isolation matrix, distinguishing shared provider accounts from forbidden shared project state."* Read as new work across the board. | **The forbidden half is already proved and the permitted half exists nowhere.** Seven claims — `database_isolation`, `api_isolation`, `project_isolation`, `transport_isolation`, `storage_isolation`, `restore_isolation`, `isolation` — assert that specific pairs of values differ, and all seven passed in Session 11's merged evidence over the live pair. **None of them says what is ALLOWED to be the same**, so none can tell a correctly isolated pair from two documents the test failed to read. | **The matrix is built around the distinction the summary names**, in `tests/deployment/test_session12_isolation_matrix.py`: `MUST_DIFFER` (project scope), `MUST_MATCH` (**the control** — one machine, one router), `NOT_AUTHORITY` (carries no authority either way). `test_every_leaf_is_classified` makes a field a later session adds redden until somebody classifies it. | Dry-run against both live deployed documents: **179 leaves, 0 unclassified, 0 project-scoped values shared, 0 rules guarding a field that does not exist.** The claim holds; what was missing was a proof that could have detected it not holding. | — |
| **D690** | This plan's own first attempt: bump `CURRENT_SESSION` to 12 so `DEP-ISO-001`'s node ids may be registered. | **The bump activates all four Session 12 requirements, not one.** `test_no_requirement_at_or_before_the_gate_session_remains_future` refuses any requirement whose `target_session` is at or below the gate session while it is still a placeholder. So `DEP-001`, `DEP-REMOVE-001` and `DX-001` must stop being placeholders in the same commit that moves the number. | **All four are activated together**, each with a **proved offline half** and a **live half gated on a declared operator event** — the `APG_AFTER_REBOOT` / `APG_ROTATED_*_FROM_FILE` pattern, which exists for exactly this: a proof of something that *happened* rather than of a state that holds. | The bump was reverted rather than pushed through, because how the other three are activated is a decision about **what those requirements mean**, not a mechanical consequence of a constant. D672 recorded the same constant being load-bearing in the other direction; this is its cost on the way out. | — |
| **D691** | `DEP-REMOVE-001`: *"Removing one project does not affect another."* Read as a claim about a removal command. | **No shipped command removes a project.** `project-runtime.sh down` stops containers and **preserves volumes deliberately** — *"removing it here would make `systemctl restart` a data-loss command"* — and `compose.sh` **refuses `--volumes` in project mode** outright: *"it would destroy the database volume."* What exists is a two-command surface: `down` (runtime) and `bootstrap-providers.sh --destroy --confirm KEY` (provider resources, by recorded ID). | **The requirement is proved against the removal surface that exists**, and the absence is recorded rather than filled: this session does not add a destroy-the-data verb. The offline half asserts every removal path is **scoped by derivation** — it can only name resources derived from its own project key — and that `--destroy` refuses without a matching `--confirm`. | **The requirement's premise had not been checked.** Written as though a removal command existed, it would have produced either a test of nothing or a new destructive verb nobody asked for. This is D683 and D688's shape a third time: **a requirement whose subject had not been measured**, and the measurement takes one `grep`. CLAUDE.md §9 already warns that destroying `pgbackrest_repo_cipher_pass` orphans every backup — a data-removal verb is a decision with consequences, not a convenience. | — |
| **D692** | This plan's Run 2: `DEP-REMOVE-001`'s offline half asserts that every removal path is scoped by derivation and that `--destroy` refuses without a matching `--confirm`. Read as four new tests. | **Three of the four already exist**, in `tests/contract/test_bootstrap_state.py`: `test_state_paths_are_project_scoped`, `test_state_may_not_name_another_projects_credential_directory` (*"would make one project authenticate as another"*) and `test_a_managed_client_secret_without_an_id_is_rejected` (*"falling back to a name lookup is how one project deletes another's"*). Writing them again would be a second, weaker claim about one property. **And the confirmation refusal is unreachable in a checkout**: measured, `bootstrap-providers.sh --destroy` answers exit **3** (*requires root*) before it ever reads `--confirm`, so a behavioural test of it would pass on the root check while believing it measured a confirmation. | **The registry points at the three that exist**, and the one genuine gap is closed: `test_project_mode_refuses_volume_removal`. Edge mode had a refusal test since Session 2; **project mode — the one holding customer data — had none.** | **The argument order is load-bearing and was measured, not assumed.** `--runtime` triggers its root check the moment it is parsed, so `--runtime down --volumes` answers exit 3 unprivileged and never reaches the refusal; `--volumes --runtime down` reaches it at exit 2. A privileged caller reaches it in any order, which is the case that matters. **The battery's arm B is that ordering**, and it fails — so a test written the natural way cannot quietly pass on the wrong exit code. The rig that established this produced a **false control** first (`--edge down --volumes` returned exit 2 for a missing `--host`, not the refusal), which is D509 inside the measurement of D692. | — |
| **D693** | This plan's Run 3: `DX-001`'s offline half proves *"every command the documented path names exists and resolves"* — expected to pass, since the path had been rewritten in Session 11 Run 7 and rehearsed on a fresh machine in Run 8. | **Four defects on the proof's first execution.** `README.md` — the `DX-001` path itself — passed **`--session 10` and `--through-session 10` on a Session 11 release**. `docs/api-operations.md` passed `5` in four places and `docs/pool-operations.md` `4`. And `docs/backup-operations.md` named **`bin/deploy.sh`, which has never existed**: the renderer is `./deploy.sh` at the repository root, so a reader following that line gets *no such file*. | **All four repaired**, and the session-number check is the guard: any `--session N` in a document a reader is pointed at *now* must equal `CURRENT_SESSION`. Session-numbered operator guides are exempt and are not scanned — each describes its own release and rewriting its flags would destroy the record. | **This is D678's class a fourth time** (after D505 and D507), and the first time it has been caught by anything other than a person reading carefully. A stale session number is worse than a missing command: `deploy.sh` refuses a number **above** `CURRENT_SESSION` (D59) and accepts anything below it, so the command runs, exits 0, and deploys an earlier session. **Session 11 Run 8's rehearsal did not catch it** — it stopped at the host baseline and the edge plane, before any `--through-session` was passed. | — |
| **D694** | This plan's Run 3, as written: four proofs for `DX-001`'s offline half, including *"no step requires editing a source file"* and *"the path stays within fewer than 15 operator steps."* | **Two of the four measured the wrong set, and neither miss was a defect in the documentation.** The edit check flagged `README.md`'s *"To change a dependency, edit `requirements-dev.in`"* — an instruction to somebody **developing the template**, not deploying a project. The step bound scanned all eight documents and reported **26**, counting `rotate-signing-key.sh` and `restore-test.sh`, which are documented operations rather than steps from a clone to a running deployment. | **The edit check exempts `requirements-dev.in` by name with its reason attached**, because a category-shaped exemption would be a loophole and one named file is a decision somebody can disagree with. **The bound is counted over the README's `## Deploying` section**, with its own control: a section that parsed to nothing would satisfy any bound. | **A bound applied to the wrong set is a bound about nothing, and it would have been "fixed" by raising the number** — which is how a specification's constraint quietly becomes whatever the artifact already does. The battery's arm C is the sharper version of the same lesson: with the command scan blinded, the command proof still reported `1 passed`. **A documentation test that reads nothing reports every document clean forever.** | — |
| **D695** | `tests/contract/test_future_marker_policy.py`: *"no placeholder ever fails; it skips, and removing its marker activates it."* `test_all_future_tests_are_skipped_in_a_normal_run` asserts `pytest -m future` exits **0**. | **Exit 5 is the end state, and the test could not express it.** `pytest` returns 5 when it selects nothing, and activating the last four placeholders left the repository with **no `future` markers at all** — which is what finishing twelve sessions means. The assertion was right for every session with unwritten work and became wrong at the moment the work was finished. | **The assertion branches on the fact**, and asserts the empty case *as empty* rather than tolerating it: a run selecting nothing while markers still existed would be the test looking at the wrong tree. | A guard written across twelve sessions of always-having-placeholders had **no way to say "and now there are none."** It is a small instance of a large shape: an invariant that holds for every observed state can still be a description of the observations rather than of the system. | — |
| **D696** | This plan's Run 4: *"claims in `evidence_claims.CLAIMS`… `DEP-ISO-001` extends the existing `isolation` claim rather than adding a fourth (ADR 0089 — a claim is a guarantee, not a file)."* | **The reasoning was appealing and the model refused it.** `claim_session` resolves a claim to the session that **introduced** it, so adding a Session 12 requirement to a Session 2 claim moved `isolation` from 2 to 12 — and `test_a_claim_resolves_to_the_session_that_introduced_it` caught it. A claim's session is not a label; it decides when the claim must first be proved, and retroactively moving one would excuse it from every session in between. | **`DEP-ISO-001` gets its own claim, `isolation_matrix`.** The same run also learned that the `DX-001` declaration needed `live_host`: without it, `documented_path` had **no live proof** — every test it named ran in a checkout — and the claims model refused the claim outright. | **Both corrections came from the model rather than from me**, and both were about the difference between a guarantee and where its proof lives. ADR 0089's rule is right and I applied it to the wrong axis: `isolation` and `isolation_matrix` are two guarantees, not one guarantee in two files. | — |
| **D697** | The evidence model: a claim's verdict is computed from the registry's node ids and JUnit results, never hand-entered, and `evidence/session-NN.json` is what a release guarantees. Session 11 closed at *"56 of 57 claims passed"*. | **37 of 127 requirements belong to no claim**, so no evidence document has ever reported them. *56 of 57 claims* describes **90 requirements**, not 127. They cluster by session — `CFG-001`–`CFG-016`, `DX-002`/`DX-003`, the whole Session 2 security set including `SEC-NET-001`, four Session 3–4 database requirements, three `SEC-DBX-*`, `AGT-DRIFT-001` and `DBX-004` — because **the claim layer arrived after Sessions 1–4 and those requirements were never retrofitted into it**. `CLAIMS` was checked for claims naming unknown requirements; **the other direction was never checked at all.** | **The historical 37 are enumerated and grandfathered; a new one is refused** by `test_no_new_requirement_goes_unreported_by_every_claim`. Grouping them into claims is a decision per requirement, and doing it in bulk is how a Session 2 claim ends up dated Session 12 (D696). The list is checked for staleness too, so a debt register cannot outlive its debt. | **They are not unproved — their node ids run in the gate and the gate is green.** What is true is narrower and worse to find late: the artefact that says what a release guarantees answers nothing about whether a service port is publicly reachable, though five tests answer it. Eleven sessions, and the thing that found it was asking the registry a question nobody had asked: *which requirements does no claim name?* | — |
| **D698** | The specification's §2.1: two P2 capabilities — a pgvector example with a vector-search RPC, and a portable nightly `pg_dump` export — with the rule that *"P2 items may be dropped before any P0 item if the schedule slips."* | **Neither was ever entered into the acceptance registry.** The registry holds 121 P0 and 6 P1 and **zero P2**. So they are not unbuilt requirements that were dropped under the rule; they are **scope nothing was tracking**. No test, no claim, and no report would have said they were missing. | **Recorded in `docs/scope-closure.md` with their state and an effort estimate**, and dropped explicitly. The pgvector extension is present and proved (`DBX-PG-001`); only the example and the RPC are absent. Nothing references `pg_dump` at all. | **Dropping a P2 item is allowed; dropping it silently is not**, and an empty P2 row in the registry is how the second happens while looking like the first. The specification's rule assumes the item is visible enough to be dropped *from* something. | — |
| **D699** | CLAUDE.md §9's oldest item: *nothing knows which proofs have never executed* — five defective never-executed proofs across two trips, and Session 12's isolation matrix had never run. | **All four proofs passed on their first execution**, in a host gate of 379 passed / 0 failed. `isolation_matrix` is green and **`DEP-ISO-001` is closed, measured live over both deployed projects.** | **Nothing to repair.** Recorded because the *absence* of a defect here is the evidence: the dry-run against both real deployed documents (Run 1) is what made a first execution uneventful. | **This is the first Session-12-era proof to run clean first time**, against a record of five that did not. The difference is one cheap step: the matrix was exercised offline against the actual documents it would meet, rather than against a fixture written by its author. That is the narrow, buildable half of §9's oldest item, and it cost minutes. | — |
| **D700** | This plan's §10, written from an offline trace: both documents publish `backup_state.status: failing`, and *"`archiving_is_failing` returns true when `last_failed_time > last_archived_time`… both documents were written immediately after a deploy, when the container restart produces a failed archive attempt."* | **The archiver is healthy on both projects and the explanation is wrong.** Measured on the host: alpha `last_archived=2026-08-28 14:14:59`, `last_failed=2026-08-26 06:40:38` — **the last failure is two days OLDER than the last success**, and `failed_count` is 48 in both the document and the live cluster, so it has not moved since. At the moment alpha's document was written the archiver was already not-failing, so **the archiver override cannot have produced its `failing`.** It must come from the repository half — `repository_status`, which returns `failing` when `pgbackrest info` reports `backup_errors` or an unrecognised code. Beta is ambiguous: its `failed_count` moved 7 → 9 after its document was written. | **Not repaired, and the cause is now narrowed rather than guessed.** One read names it: `bin/backup.sh info --json` per project. **The repair is not attempted before that read**, for the reason this session has already paid for twice — D680's fix failed on the host because it was chosen before the address was measured. | **D278 in the direction that stings.** *A repair that works is not evidence its explanation is right*; here a **measurement refuted an explanation that had already been written into a plan.** And the finding underneath is larger than the bug: `backup_state.status` is a deploy-time snapshot nothing refreshes, so it is stale in **both** directions. The README already warns that a project whose archiver died still publishes the old status; the inverse — **a project whose archiver has since recovered still publishes `failing`** — is the one that trains an operator to ignore the field. | — |

---

## 2. What Session 12 adds to the acceptance registry

`CURRENT_SESSION` moves to **12**, and all four requirements are activated in the
same commit (D690).

| Requirement | Node ids | Live half gated on |
|---|---|---|
| `DEP-ISO-001` | four, in `test_session12_isolation_matrix.py` | already live-capable: both projects exist |
| `DEP-REMOVE-001` | offline scoping proofs + one live | `APG_REMOVABLE_PROJECT_KEY` |
| `DEP-001` | offline: the documented path resolves | `APG_FRESH_HOST_OUTPUTS` |
| `DX-001` | offline: the path is complete and needs no source edit | `APG_DX_RECORD_FILE` |

**Each requirement gains more than one node id where its halves are different
claims** (D70, ADR 0089). "The documented path resolves" and "somebody followed
it" are not one guarantee measured twice.

---

## 5. Build order

### Run 1 — `DEP-ISO-001`: the isolation matrix

**Done.** `tests/deployment/test_session12_isolation_matrix.py`, five proofs.
Three categories, every one of the 179 leaves classified, dry-run clean against
both live documents. `MUST_MATCH` was narrowed during the run: `schema_version`,
`deployed_through_session` and `project.environment` were in it and are not the
substrate — alpha ran a session ahead of beta for most of Session 11, and one
host may carry `alpha-dev` beside `beta-prod`. A control that failed during a
partial rollout would fail exactly when an operator was most likely to run it.

### Run 2 — `DEP-REMOVE-001` against the surface that exists

Offline: every removal path is scoped by derivation and cannot name another
project's resources; `--destroy` refuses without a matching `--confirm`. Live:
gated on a declared removable project. **No destroy-the-data verb is added**
(D691).

**Offline half done.** One new proof rather than four: three already existed
unattributed, and the confirmation refusal is unreachable without root (D692).
Battery green, both arms killed — including the arm that reorders the test's own
arguments so it can no longer reach the refusal.

**The live half stays gated.** `APG_REMOVABLE_PROJECT_KEY` names a project whose
removal an operator has declared. Nothing here adds a destroy-the-data verb, and
§9's second stop condition is why.

### Run 3 — `DX-001` and `DEP-001`, offline halves

**Not started.** New module: `tests/contract/test_session12_documented_path.py`.

`DX-001`'s offline half, four proofs, each behavioural against files that ship:

1. **Every command the documented path names exists and is executable.** Parse
   the fenced commands out of `README.md` and
   `docs/session-11-operator-guide.md`; each `bin/*.sh`, `bin/*.py` or
   `./deploy.sh` it invokes must be a file with mode `0755` in the git index.
   *Assert what the documents produce, not which names appear* (D277).
2. **No step requires editing a source file.** No documented step may instruct
   the reader to modify anything tracked outside `project.yaml`,
   `capabilities.yaml` and the manifests. `project.example.yaml`,
   `project.second.example.yaml` and `capabilities.example.yaml` exist and are
   the copy sources.
3. **The path stays within the specification's own bound**: *fewer than 15
   operator steps* (§1.4). Counted from the README's numbered path, so the
   number the spec fixed is enforced rather than admired.
4. **The control.** A scan that matched no commands would report every document
   clean forever (D374). Assert the parse found a known command — `./deploy.sh`
   — before asserting anything about the set.

`DEP-001`'s offline half was proved in Session 11 (§11 of that plan) and is
**re-pointed, not rewritten**.

**Both live halves stay gated**, and §7 is binding: neither may report `passed`
on its offline half alone.
**Done, and the offline half found four defects on its first execution** (D693) —
in a path rewritten one session earlier and rehearsed on a fresh machine.

Five proofs in `tests/contract/test_session12_documented_path.py`. Battery green:
every arm is a defect these proofs actually found, put back — the README's stale
`--through-session 10`, `bin/deploy.sh` which has never existed, and the scan
blinded. **Arm C is the one to remember**: with the regex reading nothing, the
command proof still reported `1 passed`.

**Two of the four planned proofs were measuring the wrong set** (D694) and were
narrowed rather than deleted. Neither miss was a documentation defect.

`DEP-001`'s offline half is Session 11's and is re-pointed, not rewritten.

**Neither requirement may report `passed` on this**, and §7 is binding. What is
proved is that the path *resolves*; what is not proved is that anybody followed
it.

### Run 4 — the bump, the registry, the gate

**Not started.** In this order, because the order is enforced (D672, D690):

1. `CURRENT_SESSION = 12` in `src/agentic_postgres/__init__.py`.
2. Activate all four requirements in `tests/acceptance-registry.yaml`;
   remove all four placeholders from `tests/contract/test_future_deployment.py`.
   `DEP-ISO-001`'s four node ids are listed in §2.
3. Add the four live-half variables to `ENVIRONMENT_VARIABLES` in
   `tests/conftest.py` **and** export them from the new gate — D687 is the
   record of a claim that could not be proved because its gate had no flag, and
   `test_every_operator_supplied_gate_can_be_supplied_by_a_session_gate` now
   refuses that.
4. Claims in `evidence_claims.CLAIMS`: `project_removal`, `documented_path`,
   `fresh_host`. `DEP-ISO-001` extends the existing `isolation` claim rather
   than adding a fourth (ADR 0089 — a claim is a guarantee, not a file).
5. `python bin/render-acceptance-matrix.py --write`, then
   `bin/session-01-check.sh`.
6. `bin/session-12-check.sh`, derived **by diff from session-11-check.sh**
   (D505, D507, D678). Its only session literal is `readonly SESSION=12`.
   **Register it in `SHELL_COMMANDS` in `tests/contract/test_cli_contract.py`**
   — Session 11's gate failed its first offline run for exactly this.
7. **A host trip.** The matrix has never executed; that is CLAUDE.md's oldest
   open item and Run 1's dry-run is not a substitute. Ship by `git bundle` under
   a per-release name, confirm `git rev-parse FETCH_HEAD` **before** the
   checkout (D504), then run all three modes and merge.

**The host trip is done, and it closed one requirement and refuted one
explanation.**

`session-12-check --mode host` exited **5**: the evidence was written and some
claim in it is not `passed` (D686). 379 passed, 0 failed, 27 skipped.

**`DEP-ISO-001` is closed** — the isolation matrix ran for the first time and all
four proofs passed (D699).

**Eight claims are not `passed`, and they divide cleanly:**

* **Four are the honest result**, awaiting a declaration that does not exist:
  `bootstrap_identity` (D683), `documented_path` and `fresh_host` (no outsider,
  no empty host), `project_removal` (no removal performed).
* **Four are my omission in the trip script**, not a regression: `secret_leakage`,
  `credential_storage`, `project_isolation` and `deployment_convergence` were all
  green in Session 11's evidence and are red here only because the trip did not
  pass `--sentinel-file`, `--admin-password-file` or `--redeploy-before-file`. A
  gate cannot prove a claim whose flag it was not given — which is D687, in the
  hands of the person who wrote D687.

**Done. Session 12 is open**: `CURRENT_SESSION = 12`, all four requirements
activated, `session-01-check` PASSED at 4180 and **`session-12-check --mode
offline` PASSED at 4272 passed / 3 skipped**.

Three declarations, each admitting a proof of something that *happened*:
`APG_FRESH_HOST_OUTPUTS`, `APG_REMOVED_PROJECT_FILE`, `APG_DX_RECORD_FILE`. Each
live proof refuses a false declaration first — the fresh-host one refuses the
production host's own document, the removal one refuses a record naming the
project it reads to check survived, and the `DX-001` one refuses a record listing
**a command the documentation does not name**.

**The moment worth recording.** The bump made every documented session number
stale, and the guard written in Run 3 an hour earlier caught it in the same gate
run — all seven, plus the README's status line. D505, D507, D678 and D693 were
each found by a person reading carefully, and each had already shipped. Here the
number moved and **the tree refused to be green until the documentation moved
with it.** That is the difference between repairing instances and writing the
guard, and it is the first time this class has been caught by a test.

**Two corrections came from the suite** (D695, D696), and both were mine.

**What remains in Run 4: the host trip.** The isolation matrix has never
executed. Run 1's dry-run against both deployed documents is not a substitute —
CLAUDE.md's oldest open item is exactly the distance between those two things.

### Run 5 — scope closure

**Not started.** The specification's own final activity (§2.1, §5 of the brief).

* **Resolve P0 failures, or characterise them.** One P0 claim is red:
  `bootstrap_identity` (D683). It stays red and the reason is written down.
* **List remaining P1/P2 gaps with evidence and estimated effort.** Measured:
  all six P1 requirements are complete. **Two P2 items are unbuilt** and both are
  droppable by the specification's own rule (*"P2 items may be dropped before any
  P0 item"*):
  * **pgvector example and vector-search RPC** — the extension is present and
    proved at the locked version in the `extensions` schema (`DBX-PG-001`); no
    example table or search function exists.
  * **Portable nightly `pg_dump` export** — nothing in `bin/` or `src/`
    references `pg_dump`.
* **Document every hidden dependency.** The starting list is CLAUDE.md §9 plus
  D683, D688 and D691 — each an item whose *premise* was wrong rather than
  whose work was undone.
* **The template-or-control-plane decision.** The brief asks Session 12 to
  decide it. The product contract freezes the answer as *template*; the
  customer's stated direction is a hosted service with a UI, which the same
  contract lists under non-goals. **Record the divergence; do not resolve it
  in a test.**

**Done.** `docs/scope-closure.md`, and it is evidence-based rather than a
restatement: every number in it was measured against the registry, the claim map
and the merged evidence.

**Two findings that were not in the plan** and are the reason the run was worth
doing rather than summarising:

* **D697 — 37 of 127 requirements belong to no claim.** A third of the registry
  is tested and never reported. Nothing detected it because `CLAIMS` was checked
  in one direction only. The historical set is enumerated and grandfathered;
  a **new** orphan is now refused, with the arm verified.
* **D698 — the two P2 capabilities were never registered at all**, so they were
  never available to be dropped under the specification's own rule.

**P0**: one red claim, characterised (D683). Two awaiting a declaration, two
awaiting the host trip. **P1**: six registered, five reported, `DBX-004` caught
by D697. **P2**: zero registered, both items recorded and dropped explicitly.

**Hidden dependencies**: nine, each pinned, declared or named. **One has an end
date nobody has diarised** — the `pgbackrest=2.59.1-1.pgdg12+1` apt pin, which
PGDG will eventually stop serving (D533). It fails closed, which is the accepted
half.

**The template-or-control-plane question is recorded and not resolved**, because
it is a product decision and §9's third stop condition applies: a test may not
decide what a requirement means.

---

## 7. Evidence — what each claim may honestly report

**This is the section the plan exists for.**

| Claim | May report `passed` when | Must report `not_run` until |
|---|---|---|
| `DEP-ISO-001` | now — both projects exist and the matrix runs over them | — |
| `DEP-REMOVE-001` | the offline scoping proofs pass **and** a removal was declared | a removal is declared |
| `DEP-001` | a fresh-host deployed document is declared | that document exists |
| `DX-001` | an outsider's run is declared | somebody who did not build this has followed the path |

**`DEP-001` and `DX-001` must not report `passed` on their offline halves
alone.** An offline half proves the documented path *resolves*; it cannot prove
anybody followed it. Letting the offline half stand for the whole is the exact
failure this session is supposed to detect — and it is what a self-assessment of
documentation always does.

`bootstrap_identity` stays red (D683) and is the honest precedent: a claim held
open for a characterised reason is worth more than a claim closed by a weaker
proof.

---

## 9. Stop conditions

1. **A claim that cannot be proved is left `not_run`, never weakened to fit.** A
   currently-passing test may not be weakened to make a new one pass, and an
   offline half may not be re-labelled as a whole.
2. **No destroy-the-data verb is added** to satisfy `DEP-REMOVE-001` (D691).
   Destroying `pgbackrest_repo_cipher_pass` orphans every backup, and a
   convenience verb over that is a decision with an ADR, not a test fixture.
3. **If activating a requirement requires inventing what it means, stop and
   ask.** D690 is already one instance: the bump's cost was a scope decision
   wearing a constant's clothes.
4. **The matrix's `MUST_DIFFER` list is not narrowed to make a run green.**
   Widening it to a measured set is fine; narrowing it to pass is D300's shape.

---

## 10. Open items carried in, and one opened here

**Opened by this session, unmeasured, and worth a host command:**

> **Both deployed documents publish `backup_state.status: failing` while
> `bin/backup.sh info --json` reports the repository `ready` and `doctor.sh`
> reported the archiver `ok`.**
>
> Traced offline: `backup_report.backup_state` takes the repository's status and
> lets `archiving_is_failing` override it, which returns true when
> `last_failed_time > last_archived_time`. Both documents were written
> **immediately after a deploy**, when the container restart produces a failed
> archive attempt and — on an idle cluster with nothing to archive — no success
> follows to clear the comparison.
>
> If that is right, it is a **false alarm in one of the three places the
> archiving signal is supposed to reach an operator** (CLAUDE.md §9), and it is
> D673/D680's shape a third time: a status computed at the one moment it cannot
> be right. **It needs one measurement on the host**: read
> `pg_stat_archiver.last_failed_time` and `last_archived_time` on a project that
> has been idle since its last deploy. Not repaired here, because a repair
> chosen before the measurement is a guess.

**Carried in, unchanged:** CLAUDE.md §9, less the two items Session 11
characterised (D683, D688).

---

## 11. What ships, and what does not

Session 12 is the last session in the plan. There is no §11 handoff to a
successor; there is a statement of what the artifact is when the work stops.

**Ships:** an appliance whose four access planes are proved against a live
deployment, two isolated projects on one host with the isolation measured rather
than asserted, a rehearsed point-in-time restore, and a documented path whose
commands all resolve.

**Does not ship, and each is named rather than implied:**

* **`bootstrap_identity`** — the signing-key rotation cannot be prepared (D683).
  A located code change, not a mystery.
* **The outsider's witness** — `DX-001` and `DEP-001`'s live halves. The
  machinery is finished; nobody who did not build it has followed the path.
  **An offline half may not stand in for this** (§7).
* **Two P2 items** — the pgvector example and the `pg_dump` export, droppable by
  the specification's own rule.
* **The template-or-control-plane question**, recorded and not resolved.
