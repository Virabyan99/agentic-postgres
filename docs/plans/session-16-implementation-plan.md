# Session 16 — Agent capability governance v2 and the evaluation harness

```
CURRENT_SESSION **15** -> 16 in Run 9, ALL-OR-NOTHING (D690).
template_version **0.4.0** -> 0.5.0 at the same bump.
migrations      26 released. Session 16 adds **0027**, not 0023 (D863).
divergences     Next free **D861**. This plan opens §1 at D861 with ten
                planning-time rows.
ADRs            175 released. Next free **0176**.
claims          86. Session 16 adds nine requirements and seven claims -- §2,
                decided now because the bump cannot be partial.
evidence        evidence/session-15.json: 86 claims, 78 passed, 8 not_run,
                0 failed. Session 16 inherits the eight as not_run.
host            62.238.99.122, running Session 15 on both projects at
                `dfc09b3`. 18 containers, 3814 MB, NO SWAP.
CI              **RED, and has been for a month** (D861). 313 runs, 6 successes,
                all on 2026-08-03/04. This is Run 1.
```

**This is the largest of the six Stage 2 sessions and the stage plan says so.**
Ten runs. The brief lists nine features; §1 shows that two of them are not what
the brief calls them, one is a fifth budget the stage plan's own *Must not*
flags, and one of them cannot be built at all until a signal nobody has read for
a month is repaired.

---

## 0. Where the session starts

`docs/plans/stage-2-plan.md` §0 and §3 own this, and §5's *Session 16* entry is
the brief. Session 15 closed at `d3b3e8e` with the host at `dfc09b3` and
`evidence/session-15.json` reporting 78 passed / 8 not_run / 0 failed.

**Read `docs/scope-closure.md` §2 before anything else.** It was rewritten at
Session 15's close because it had described a *blocker* and been read as a
*claim* for four sessions (D860). This session touches the agent plane, whose
ledger entries have not had the same audit.

**The brief was checked against the tree before this plan was costed**, which is
D812's rule. Three of its statements are exactly right and are not re-litigated
below: `app_private.agent_audit` genuinely lacks capability version, contract
hash and denial reason; `capability_contract_sha256` genuinely *is* already in
the deployed document; and the four budgets genuinely are independent by
decision (ADR 0129). What the brief got wrong is §1.

---

## 1. The divergence table

Six columns, the house shape. **Every row is a fact measured against the tree or
against the deployment at planning time**, not a prediction.

**Next free number after this table is D902.**

| # | The plan says | The repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D861** | The evaluation harness fails **CI** when a capability changes without its cases, and §9 of the handoff lists *"ADR 0019's CI job unbuilt"* among its smaller open items. | **CI is built and has been RED for a month.** `.github/workflows/ci.yml` is 210 lines, three jobs, third-party actions pinned to commit SHAs — a careful piece of work. The GitHub Actions API reports **313 runs and 6 successes, every success on 2026-08-03 or 2026-08-04**. Every run since is a failure, including all four of Session 15's. On the newest run **all three jobs fail**, each at a different step: *Run the Session 1 gate*, *Confirm the acceptance session is derived from the package*, and *Show outstanding future work*. | **Run 1 is repairing CI, and it is first.** Nothing else in this session is worth building until it is green. | **A gate added to a signal nobody reads is not a gate.** This is D701's shape at repository scale — *a signal that is always red is a signal nobody reads* — and it is worse here, because the brief's whole enforcement mechanism for the harness is *"failing CI."* Adding a tenth reason for a job to fail, when it has failed 307 times consecutively, buys nothing. **And §9's entry is mischaracterised**: the job is not unbuilt, it is broken — the **fifth** instance of that pattern after the three §9 already admits and D860. | — |
| **D862** | CI is red for whatever reason CI is usually red — upstream drift, a flaky runner. | **Two of the three causes are readable in the workflow file itself and both are question 5.** (a) `session-2-contract` runs `assert CURRENT_SESSION == 2`, hard-coded, with a comment explaining that the value must be *derived rather than passed* — and the constant has moved thirteen times since. (b) `future-inventory` runs `pytest -q -m future`, and **D695 measured that this exits 5 when it selects nothing**; Session 12 activated the last placeholder, so it selects nothing. D695's repair fixed the *test* that made the same assumption and left **the CI step running the same command**. The third cause, the Session 1 gate itself, is **not measured** — job logs need admin rights on the repository and the assistant has none. | **Run 1's first act is to read the third log**, by `gh auth` or the web UI, before changing anything. The two known causes are repaired with it, and the workflow gains a proof that the derived-session assertion cannot go stale again. | **A hard-coded constant inside a comment insisting the constant must not be hard-coded** is the most exact instance of question 5 this repository has produced. D695's own repair missing a caller is the second half of the same row. **Neither is upstream drift, and assuming drift is what would have made this a footnote instead of a run.** | 0014 |
| **D863** | *"one migration 0023 adding capability version, contract hash and denial reason to `app_private.agent_audit`."* | **0023 through 0026 are released** — Session 15's refresh session plane, its functions, agent credential lifecycle and password reset. Session 16's migration is **0027**. | **Stated here so no run writes a colliding filename.** | Trivial and cheap to say now. The stage plan was written before Session 15 existed and every number in it after 0022 is one session stale; **a plan that names a taken migration number fails at `migrate.sh freeze-lock`, late, after the SQL is written.** | — |
| **D864** | *"idempotency keys, where the manifest today has only a boolean."* | **The boolean is a different concept, not a v1 of the key.** `idempotent: bool` is required of `write` capabilities only (schema branch `allOf[1]`), absent on all five reads and metadata capabilities in `capabilities.example.yaml`, and read by `capability_compiler` at line 453. It **declares a property of the operation** — *replaying this is harmless*. An **idempotency key** is a caller-supplied token that requires durable dedupe state and a stored prior response, and it means the opposite — *do not replay this*. | **Run 6 is new construction**, and the boolean is left alone as the separate thing it is. The plan does not describe the key as an extension of it. | **A brief that says "X today has only a Y" prices new construction as a widening** — the identical error D812 caught one session ago, where a refresh-token plane that did not exist was priced as a modification. The tell is the same: a name that appears in the tree, meaning something else. **The boolean and the key can also disagree**: a capability marked `idempotent: true` needs no key, and one marked `false` is exactly where a key matters. | — |
| **D865** | Windowed quotas are *"the one genuinely new budget class and the only one needing durable state."* | **Correct, and it is therefore the FIFTH budget** — which the stage plan's own *Must not* list flags: *"Add a fifth budget without reading ADR 0129 first."* The four are bound by four different authorities: rows by `min(caller limit, resource.max_rows)` from the deployed lock, serialized bytes by the `MAX_SERIALIZED_BYTES` runtime constant, elapsed time by the lock's `timeout_ms`, and concurrency by a semaphore derived from PostgREST's pool. **All four are per-request or per-process. A window is per-agent and durable**, so it is the first that needs a table. | **Run 5 reads ADR 0129 first and records what makes the fifth different**, in an ADR of its own. **And it decides retention in the same run**: `app_private.agent_audit` already grows without bound with nothing pruning it (§9), and a quota table keyed by time inherits that on day one — except a quota table is *read on every request*, so its growth is a latency problem and not only a disk one. | **The stage plan flagged this and did not say what the answer is**, which is correct — that is a session's job. What must not happen is a fifth budget arriving as *"the same as the other four, plus a window"*: it is the only one whose state outlives the request, the only one two processes contend on, and the only one that can be wrong after a restart. | 0176 |
| **D866** | One *"capability-schema version bump adding per-capability semver, deprecation state, risk classification, byte and concurrency limits, dry-run and approval."* | **`additionalProperties: false`, and required fields are enforced per KIND in three `if/then` branches.** A capability today declares 16 properties with `['name','kind','enabled','required_scopes','operation']` always required; reads additionally require `resource`, `columns`, `max_rows`; writes require `max_affected_rows`, `idempotent`; and **metadata capabilities are forbidden most of them** by a `not/anyOf` branch. So this is not one bump — it is **seven new fields whose required-ness differs by kind**, and a byte limit on a metadata capability would be *refused by the existing schema* unless branch `allOf[2]` is rewritten with it. | **Runs 2, 4 and 7 split it by what reads the field**, not by which sentence of the brief names it. `schema_version` 1 → 2 lands once, in Run 2. | **The `if/then` branches are the part a plan skips and a run discovers.** They encode a real decision — a metadata capability reaches no backend, so a row or byte bound on it would be a bound on nothing — and adding a field uniformly across kinds would quietly make that decision meaningless. **Splitting by reader is also D816's rule**: a declared field with no reader is an unverified field, and this session would otherwise add seven at once. | 0176 |
| **D867** | Project-local **profiles**. | **Nothing named `profile` exists in the capability plane** — zero occurrences in `capability_compiler.py` or `mcp_lock.py`. The only project-local narrowing today is `enabled`, per capability, in the project manifest. | **Run 8 builds profiles, and the invariant is fixed in this plan rather than in the run: a profile may only NARROW.** A profile that could widen would be a second authority over what a deployment permits, which ADR 0002 forbids and which the frozen column allowlist exists to prevent. | **This is the feature most likely to be built as a general override mechanism**, because that is what "profile" means everywhere else. Here it must be a monotone restriction of the compiled contract, or the deployed lock stops being the answer to *what can this agent do* — and every allowlist proof in Sessions 8 and 9 is written against the lock. | 0177 |
| **D868** | An evaluation harness *"with positive and adversarial cases per capability."* | **None exists, and the word `adversarial` appears nowhere in the tree except the stage plan itself.** There are seven capabilities in the example manifest and twelve `AGT-*` requirements, all P0, all targeted at Sessions 8 and 9. | **Run 9 builds it, and its cases are derived from the CAPABILITY CONTRACT rather than from the runtime** — the compiled lock says what is permitted, and an adversarial case is generated as *a request the lock does not permit*, per field, mechanically. Hand-written cases are added on top and marked as such. | **The stage plan already names this session's hardest question and it is right**: *an adversarial case whose expected denial was written from the implementation is a description of the implementation.* That is CLAUDE.md §7's sixth question, which was invisible to a green offline suite three times (D673, D680/D682, D687) and which a live host caught each time. **Deriving the negative cases from the contract rather than from the code is the only mechanical answer available**, and it is not a complete one — so the harness records which cases were derived and which were written, and the two are reported separately. | 0178 |
| **D869** | *"`AGT-*` extended, `EVAL-*`."* | **`AGT-*` is 12 requirements, every one P0 and every one targeted at Session 8 or 9.** Extending the family means new ids at `target_session: 16`, and D690 makes their arrival all-or-nothing with their proofs. There is no `EVAL-*` family. | **§2 fixes nine requirement ids and seven claims now**, before Run 1, exactly as Session 15's §2 did and for the reason Run 9's bump cannot be partial. | Session 15 proved the ordering works: the registry additions are decided at planning time because **a requirement invented in Run 6 and forgotten in Run 9 is a gate failure at the least convenient moment**. | — |
| **D870** | The bump adds *"dry-run and approval"* as two capability fields alongside the others. | **Approval is a workflow with an out-of-band actor, and no other part of this product has one.** Every refusal in the agent plane today is synchronous and terminal: a scope check, an allowlist, a budget. An approval implies a request that is *pending*, durable state holding it, a second principal who resolves it, and a path by which the original caller learns the outcome — none of which exists, and the last of which is a notification plane this product does not have. **Dry-run is not like that**: it is one synchronous request that runs authorization and validation and stops before the write. | **Dry-run ships fully in Run 7. Approval ships as a DECLARATION AND A REFUSAL** — a capability may declare `requires_approval: true`, and the plane refuses it with a named denial reason from Run 3's taxonomy, audited. **Not an approval workflow**, and the plan says so now rather than discovering it in Run 7. | **This is D815's pattern deliberately reused**: Session 15 scoped rotation to *a surface with one class proved end to end* at planning time, and that is why Run 6 cost what it was supposed to. **The alternative is an approval plane built in the last third of the largest session of the stage**, which is where a half-built workflow with durable pending state would land. A refusal that is honest, audited and named is a smaller thing that is completely true. | 0177 |
| **D871** | Run 1 gains *"a test in the repository that reads `.github/workflows/ci.yml` and refuses a hard-coded session number"* — the class guard for D862. | **That guard already exists and does not read the workflow.** `test_no_operator_command_types_the_current_session` (D719) scans `_operator_commands()`, which globs **`bin/*.py`**. Its regex is scoped to the literal `CURRENT_SESSION` *currently is*, deliberately and with the reason written beside it: it "cannot catch a stale bound after the bump", because `<= 12` stops matching once the constant is 13, and in `bin/` the load-bearing guard is a command actually **executed** against the number. **Nothing in this suite executes a workflow**, so that fallback does not exist here — the narrow rule would have caught `== 2` for one session and gone quiet for thirteen, which is exactly what happened. | **The new guard is broader than the plan asked for**, and the difference is written into both. `test_no_workflow_compares_a_session_against_a_literal` refuses **any** integer literal, scans **comment lines too**, and covers the **shell** test operators as well as the Python ones. It also refuses `--session <digit>`, which D693 checks for documented commands and nothing checked here. | **The first draft carried only the Python and arithmetic spellings, and its own control walked straight through it**: `if [ "${SESSION}" -gt 15 ]` matched nothing. A guard over a GitHub workflow that reads only Python comparisons is reading the one language the file is least likely to be written in — D464's family, a text scan standing in for a construct, caught this time by the control rather than by a later session. Comments are scanned because a comment in a workflow that names a session number is describing the step beside it, and the two going out of step **is** the defect: the repaired step is the one whose comment insisted the value must be derived. | 0176 |
| **D872** | *"The third cause, the Session 1 gate itself, is **not measured** — job logs need admin rights on the repository and the assistant has none."* Run 1's first act is to read that log. | **The log is still unreadable and the cause is measured anyway.** `GET /actions/jobs/<id>/logs` returns HTTP 403 *"Must have admin rights to Repository"* for every job, confirmed against the newest run. But the workflow uploads `.generated/session-01/` and `evidence/session-01.json` with `if: always()` and `if-no-files-found: warn`, and the gate creates the first at its **step 4**. **Every run inside the seven-day artifact retention window has `total_count: 0`** — so the gate died before step 4 on every one of them. A clean clone of **`345c349`, the exact commit CI last failed on**, dies at **step 2**, on `bin/lock-dev-deps.sh --check`. | **The cause is treated as measured and the log stays unread.** Run 1 proceeds on the artifact evidence plus the clean-clone reproduction, and this row records both what that establishes and what it does not. | **An artifact written at a known step is a step counter**, and it is the one signal about a private job that survives without a credential. Its honest limits are two. It narrows to *steps 1–3* and does not name the step — the clean clone does that, and it is a different machine. And **the control could not be run from history**: `total_count` is 0 for old runs because artifacts expire at seven days, and there is **no successful run inside the window** to show that a green gate leaves one behind. That half was verified locally instead, by running the gate and watching `.generated/session-01/` appear at step 4. | — |
| **D873** | Two of the three causes are question 5 and the third is unknown. | **The third is question 5 as well, and it is the oldest of them.** `bin/lock-dev-deps.sh --check` runs `uv pip compile` **against PyPI** and compares the result to the committed lock, so what it asserts is not "this lock is consistent" but *"this lock is the newest resolution available at the instant the check runs"* — a fact about the world restated as a fact about the repository. Roughly ninety distributions are in that resolution; any release of any one reddens the gate, and through the gate reddens CI, within hours of a push that was green when it left. **§9 has recorded this ten times as "upstream drift", repairing the instance each time.** And `bin/lock-versions.sh --check` had already made the opposite choice one file over, in its own words: *"makes no network call at all. Everything it verifies is derivable."* | **ADR 0176.** The lock carries the cutoff that produced it on its first line; `--update` stamps *now* and compiles with `uv pip compile --exclude-newer`, `--check` reads that instant back out and resolves against it. A lock with no cutoff is refused, exit 5. | **Measured before anything was built on it, with a control that had to come out different.** Two compiles at the same cutoff are byte-identical; the same compile with no cutoff moved two packages on the same afternoon (`cyclopts` 4.23.3 → 4.24.0, `sse-starlette` 3.4.8 → 3.4.10). A flag that changed nothing would have proved nothing. **This is not a repair to a flaky check — it is the tenth instance being read as a class**, and the class is that a release gate may not assert a property of PyPI. What it does not do is keep dependencies current: the lock now expires **when a human moves it**, which is D533's shape with the end date written down instead of implied. | 0176 |
| **D874** | Repairing the lock command is a change to `bin/`, and the contract suite protects it. | **The guard protecting it was a proxy, and the safe change is what broke it.** `test_both_modes_compile_into_a_temporary_destination` asserted `destinations <= {"staged", "tmp"}` — the two names that existed when it was written — so `--check` needing a third temporary turned it red while **an unsafe destination that happened to be called `tmp` would have passed**. D464's family: a text scan standing in for a construct. Worse, the **first replacement survived its own mutation**. Asking whether the destination's name appears in *some* `mktemp` assignment is satisfied by an earlier one: a mutation reassigning `tmp` to `"${LOCK_FILE}.partial"` immediately before the call — the exact defect this module was written about — came back PASSED. | **The guard asserts the construct: every assignment to a `compile_to` destination is `"$(mktemp)"`**, not one of them. ADR 0176 authorises the replacement, §6's rule for a stricter form, and the docstring says so. The mutation is KILLED against the second version, with a control in the `--update` branch the mutation cannot reach. | **A surviving mutation is evidence — read it** (§1). This one said the replacement was weaker than the sentence describing it, and it said so *before* the guard shipped rather than three sessions later. It is also §7 question 4 in miniature: when the proxy failed, the side that got the fix could have been the proof's name list, and widening it to the measured set was explicitly permitted. **That repair would have been legal, green, and would have left the same hole.** | 0176 |
| **D875** | The Session 1 gate dies at step 2 on the lock check (D873), so ADR 0176 repairs CI's third cause. | **It dies at step 2 on the LINTER, one command earlier, and the reproduction could not see it.** Step 2 runs `shellcheck deploy.sh bin/*.sh libexec/*` **first**, and CI installed shellcheck with `apt-get install -y shellcheck` — unpinned, whatever the runner image carries. This machine has **0.11.0**. Measured across three releases in the same container, with 0.11.0 as the control: **0.9.0 and 0.10.0 raise SC2015 on `deploy.sh:146` and `bin/connect.sh:392` and exit 1; 0.11.0 exits 0.** So the runner has failed on the linter every run for a month, and the clean-clone reproduction — which ran this machine's 0.11.0 — sailed past it into the lock check and found a *different* real defect there. Confirmed by the first push: with the lock repaired, the gate job still failed and still uploaded **zero artifacts**. | **shellcheck is pinned by version and sha256 in CI, and the gate refuses any other version**, exactly as `bin/lock-dev-deps.sh` has refused a uv that is not 0.12.1 since Session 1. ADR 0021: applying a decision to a second subject is not a new decision. The number now lives in two files, so `test_ci_installs_the_shellcheck_the_gate_pins` keeps them one number. **D873 is not withdrawn** — it is a real defect that would have become the cause the moment the linter was pinned. | **A reproduction that fails for a different reason than its subject is not a reproduction**, and this one was green-lit by agreeing with the runner's verdict. It is ADR 0065/0066 inverted: the clean clone reached the same *end state* — a red gate at step 2 — **by a route the runner does not take**. D872's artifact inference was sound and stayed sound; it said *before step 4*, and it cannot distinguish a step's first command from its fourth. **The thing that actually separated them was pushing and reading the runner**, which is what the plan means by *done when a run on `main` is green, observed through the API*. | 0176 |
| **D876** | With the linter pinned, the gate should pass: the suite is green on this machine and CI runs the same command. | **Two contract proofs are descriptions of this workstation.** `/var/lib/agentic-postgres` exists here — `drwx------ root root`, left by a deploy on 2026-08-08 — and does not exist on a runner that has never deployed anything. `test_check_unprivileged_says_it_could_not_look_rather_than_absent` asserted exit **3** unconditionally, and a fresh machine answers **4**, `UNDETERMINED`, *"nobody looked"* — which is **also** ADR 0157 and also correct. `test_arguments_reach_the_verb_untouched_including_one_with_spaces` is worse: its subject is argument QUOTING, and it read the derived path out of that same permission-denied message, so it was riding on the same directory without saying so. On the runner `upgrade plan` refuses at *"--candidate is required"* and names no path at all. | **The permission test asserts the MAPPING** — whichever state the root is in, the code and message must be the ones that state calls for, with the two codes' inequality as the control. **The quoting test moves from `plan` to `check`**, which names the derived path in *both* of its answers, so the claim no longer rides on ambient state. | **A local mutation battery cannot verify either repair**, and that is the row's point. `plan` echoes the path here too, through the permission-denied branch, so this machine cannot tell the old test from the new one. **The runner is the only instrument that can**, and it is the closest thing this project has to `fresh_host` for the contract suite: the one place the tests run where nothing has ever been deployed. §7's sixth question asks who wrote the fixture and whether it shares a belief with the code; here the belief was shared with the *machine*, and eight sessions of green offline runs never touched it. | — |
| **D877** | The Session 2 job's suite step is a third cause, unmeasured. | **It is one cause, and it is an ORDERING.** The job ran `pytest -m p0 …` **before** the step that renders the fixtures, and ninety proofs read `.generated/fixture-alpha-dev/outputs.json` — 88 of them through a module fixture that starts a Postgres container first and then reads the document. The log shows **88 errors and 2 failures, every one the same `FileNotFoundError`.** `bin/session-01-check.sh` renders at its step 3 and runs the suite at step 4; this job had the two the other way round, and it never showed because `.generated/` survives on a developer machine from the previous gate run. | **The render step moves ahead of the suite step**, matching the gate's order. | **88 errors and one cause is the shape worth remembering** — a fixture that fails at setup reports once per test, and a reader counting symptoms would have costed this as the largest of the four causes rather than the smallest. It is also the third of four causes that reduce to *the developer machine carries state a fresh one does not*, which is what makes D876's note about the runner the durable half of this run. | — |
| **D878** | With the suite ordered correctly the Session 2 job should pass; its remaining steps have been running all along. | **They had not. `Unit files are valid` has NEVER passed.** It arrived with the units in `78cc37b` on **2026-08-04, the day of CI's last green run**, and `systemd-analyze verify` resolves every `ExecStart` — so it failed on `/usr/local/libexec/agentic-postgres/{project,edge,firewall}`, which nothing in a checkout installs, from its first execution. Twelve complaints, all *"is not executable: No such file or directory"*. It fails identically on this machine, and nobody had run it here because it exists only in the workflow. Four of the job's six steps had been skipped behind an earlier failure for a month, and each one that was unblocked revealed the next. | **The launchers are installed the way a host installs them**, through the one command that owns the `agentic-postgres-<name>` → `<name>` mapping. `bin/provision-host.sh` gains `--install-launchers`: root, no manifest — the launchers are the *indirection* and are identical on every host, so requiring a `host.yaml` would mean the only machine that runs this check could not put the units' `ExecStart` in place without inventing one. | **§7's second question, asked of the CHECK rather than of the code**: *has it run at all, in this environment, since the thing it measures last changed?* It had run 300 times and never once succeeded, which is the same answer. Restating the name mapping in the workflow would have been quicker and would have created a second authority over it (ADR 0002) — and it is precisely the mapping most likely to be got subtly wrong, since the long name exists so the repository directory is self-describing and the short one is what the units invoke. **Measured in a container at systemd 255, the runner's own version, with the pre-install control**: 12 complaints before, **0** after. What remains there is `docker.service not found`, which the runner does not have and whose absence from its log is how that was known before pushing. | — |
| **D879** | Run 2's text: *"**ADR 0176** records the version bump's compatibility rule."* | **Run 1 consumed 0176** for the lock check that verifies the tree rather than the world. Run 2's ADR is **0177**. | Stated so the next run does not write a second 0176. | Trivial, and the reason it is a row rather than a silent correction is that the plan is the session's authority afterwards: a reader following its §5 to ADR 0176 would find a decision about `uv pip compile` and conclude the schema bump was never recorded. | 0177 |
| **D880** | §2 fixes `AGT-CAPVER-001` — *"the version reaches the audit row"* — and `AGT-RISK-001` — *"a high-risk capability's denial and its audit record differ observably"* — and §5 puts both fields in Run 2. | **Neither reader can exist in Run 2.** `app_private.agent_audit` gains `capability_version`, `contract_hash` and `denial_reason` in **migration 0027, which is Run 3**, and the denial taxonomy those reasons come from is Run 3 as well. So D816's rule — a declared field arrives with its reader in the same run — collides with the plan's own run order, and the collision is real rather than a wording problem. | **Run 2 ships `version` and `lifecycle` with behavioural readers and `risk` with a VALIDATION reader**: a metadata capability must be `low`, a write may not be. `AGT-CAPVER-001` and `AGT-RISK-001` **do not close in Run 2**; they close in Run 3. Recorded here rather than discovered there. | **The tempting escape is worse than the problem.** Risk could select a behaviour today by narrowing `max_affected_rows` or `timeout_ms` for a high-risk capability — and that makes risk a **second authority** over two of ADR 0129's four budgets, which are independent *by decision*. The alternative offered and rejected was pulling migration 0027 into Run 2, which designs a `denial_reason` column before the vocabulary it records exists, in a released migration that is fix-forward. **A requirement reported closed on a validation rule would be claiming a behaviour nobody built.** | 0177 |
| **D881** | The bump is *"one schema version"*, so `SUPPORTED_SCHEMA_VERSIONS` gains a 2. | **That constant governs TWO documents.** One `frozenset({1})` was read by `validate_project_semantics` **and** by `load_capabilities_manifest`. Adding 2 for the capability manifest makes the project check accept a project manifest declaring 2 — which `project.schema.json`'s `enum: [1]` then refuses. Two authorities, disagreeing about the same document, and invisibly: the schema runs first and wins, so the constant would have been wrong and silent. | **Split into `SUPPORTED_PROJECT_SCHEMA_VERSIONS` and `SUPPORTED_CAPABILITIES_SCHEMA_VERSIONS`**, each checked against the enum of the schema it governs by a contract test. | ADR 0002 at the smallest possible scale, and the shape §7's question 5 keeps producing: **a constant that was correct while there was one caller, and became a second authority the moment there were two.** It has been two since the capability manifest existed; it only became wrong when the two documents' versions needed to differ. | 0177 |
| **D882** | The compiled contract's `schema_version` is a constant the compiler owns, so moving it is a change to one file. | **The RUNTIME refuses a lock version it does not know, at startup, and fails the start.** `mcp_lock.load_lock` held `SUPPORTED_SCHEMA_VERSION = 1` and compared with `!=`. A release that compiled a v2 lock while that still said 1 would deploy a project whose MCP service will not come up — and `DEFERRED_SERVICES` starts it at **step 6b**, so the failure lands in the middle of a convergence rather than at its edge. | **The runtime learns 2 in the same run**, `SUPPORTED_SCHEMA_VERSIONS = {1, 2}`, and the compiled contract's version becomes **the manifest's** rather than a constant: a v1 manifest still produces the tools it always did, because `capabilities.yaml` lives only on the host and no commit can edit it. | **This is the most breakable ordering in the run and it was found by reading the generated catalog**, which says so in one clause — *"an unknown `schema_version` fails the start rather than being ignored"*. Measured by round-tripping a compiled lock through the runtime's own parser: a v2 lock loads with `query_resource` carrying both authorizations, a v1 lock loads with the fields **absent rather than defaulted**, and a v1 lock *carrying* them is refused — that last direction being what stops the version number from becoming decorative. | 0177 |
| **D883** | Existing proofs are unaffected by a version the schema did not have. | **`test_a_lock_from_an_unknown_schema_version_is_refused` used the literal 2 as its example of "unknown".** Making 2 known left it asserting that a KNOWN version is refused, and it then failed on the tool roster instead — which reads like the parser having lost its version check entirely. | **The unknown version is derived**: `max(SUPPORTED_SCHEMA_VERSIONS) + 1`, with an assertion that it is not in the set. | **The third instance this session of a literal that was correct when written**, after CI's `CURRENT_SESSION == 2` and the temp-file name allowlist (D874). The common shape is a proof naming a value that belongs to a set the proof does not consult — and the failure mode here is the dangerous one, because it went red for a *plausible unrelated reason* rather than for its own. | — |
| **D884** | The compiled tool's `risk` is the riskiest of its backing capabilities, and the contract test reading every tool proves it. | **It proves nothing, and the mutation battery said so.** Replacing `max(..., key=RISK_ORDER.index)` with `declared[0]["risk"]` **SURVIVED**: every capability in `capabilities.example.yaml` shares its tool's risk — `query_notes` and `query_tasks` are both `low` — so the first backing risk and the riskiest are the same value in all six tools. The only derivation this run adds was never reached with inputs that disagree. | **A test that constructs the disagreement**: one half of the grouped tool raised to `high`, compiled both ways round, asserting the two backing risks really differ before asserting the aggregate. Both orderings, because taking the first would be right by accident in one of them. | **An uninformative mutation is still evidence — of the fixture, not the code** (D493). The compiler was correct throughout; what survived was a proof whose only input was a manifest in which the question does not arise. A read may be any risk, so raising one is a legal manifest rather than a contrivance, which is what makes the constructed case a real one. | 0177 |
| **D885** | A mutation reported `NOT RUN` means its victim never executed. | **It meant the RIG could not see it.** Two victims are parametrized, and pytest reports those as `name[param]`; the battery keyed on the exact node id, found no match, and printed `NOT RUN` — which sits in the same column as a survivor and reads like one. Both guards had run and had failed correctly. | Matched by prefix, worst-case per victim: any parametrization failing makes the victim `FAILED`. | **The apparatus was the defect, twice in one battery** — §7's family, and the reason the run's first result was three survivors when only one was real. Worth the row because `NOT RUN` is the reading a battery is least likely to question: a survivor invites investigation and a missing measurement looks like an accident. All eight are killed with the rig repaired, each with a control it cannot reach. | — |
| **D886** | The denial taxonomy is *"derived from the refusals that already exist — scope, allowlist, budget, drift, credential"*. | **Four of the five are real, `credential` is not, and four the brief did not name are.** Enumerated across `mcp_tools`, `mcp_query` and `mcp_upstream`. **There is no credential refusal in this plane**: the MCP runtime holds no credential of any kind — no signing key, no database credential — and that is enforced rather than merely true, so the member could not describe its own. If it meant the CALLER's, `mcp_upstream`'s own header measures **four states behind two statuses**: a 401 is "no Authorization", "an unknown agent" or "a forged signature", and a 403 is a human token. What the brief missed: `input_malformed` (the caller's argument shape, before any allowlist question), `upstream_refused`, `audit_unavailable` (a write failing closed on its own record), and `write_rejected` (the product's own `PT4xx`, translated per ADR 0139). | **Eight members** (ADR 0178), as a Postgres enum in migration 0027 so the catalog refuses a free-text reason rather than a convention discouraging it. `upstream_refused` is the honest form of `credential`: this plane asked and was told no. | **Naming one of those four states `credential` is D433's forbidden guess, and it is WORSE in an audit row than in a response** — a response is read by a caller who can retry, and a durable record is read months later by somebody who cannot re-derive what was true. **`not_in_allowlist` and `input_malformed` are kept apart although a caller sees one token for both**: to an operator they are opposite events — an agent reaching for something this deployment froze, versus a client bug — and collapsing them buries the interesting one inside the noisy one, which is the failure a taxonomy exists to prevent. | 0178 |
| **D887** | Adding three columns and widening two function signatures is a migration and its callers. | **The two functions are `api.`, and ADR 0175's arity guard reads `app_private.` only.** So migration 0027 widened both signatures and the guard — built in Session 15 Run 8 for exactly this class, after a signature change broke four proofs invisibly — **stayed green**. `api` is the only schema exposed over HTTP, which makes it the one where a wrong arity is a refusal a caller actually receives, and it is the one the rule was not applied to. | **The guard reads both released schemas.** With that alone it reported **19 sites**; the corrections below brought it to the **12 that are real**, every one repaired. | **Question 5, for the fourth time in this session** after D719, D871 and D874 — a decision implemented for one caller class while the class spans two. The particular sting here is that these two functions are called on **every single agent request**, so they were the most-called released functions in the tree and the least covered. | 0178 |
| **D888** | Widening the guard's schema is a one-line change to a regular expression. | **It took three corrections, and the guard forced each one by contradicting itself.** (a) It does not model `DEFAULT` — safe while it read `app_private`, where no released function carries one, and immediately wrong for `api`: `api.create_note(p_title text, p_content text DEFAULT '')` is called with one argument in five correct places and the guard called all five defects. (b) A `DROP` names a signature **by its types**, so it retires that declaration's whole callable range; subtracting only the count it spells left `agent_audit_begin` declaring `[1, 2, 5]` — an old signature's defaulted forms outliving the signature. (c) Seven of the nineteen findings were not calls at all: a type signature passed to `has_function_privilege`, docstring prose naming parameters, and prefix strings whose closing paren is somewhere unrelated. | Callable arities are a **range**; a drop retires a declaration; and a call is distinguished from a signature by two rules **measured against all 157 real calls before being written** — none has an all-bare argument list, none has its own string delimiter as the first character after the paren, and the 25 zero-argument calls are unaffected. | **A guard that cries wolf about correct code gets widened back**, and that is how this one would have died a session after it was built. Every correction here came from the guard reporting something the tree proved was fine — which is the good failure mode, and the reason the measurement preceded each rule instead of following it. | 0178 |
| **D889** | The audit row records the capability version, per `AGT-CAPVER-001`. | **A tool backed by several capabilities has no single version to record.** `query_resource` is `query_notes` and `query_tasks` (ADR 0120); they version independently, and the record is OPENED before the arguments have selected between them. | **`_sole_capability_version` records the version when a tool has exactly one backing capability and NULL otherwise**, with the reason at the function. `contract_hash` is recorded beside it and always: the lock's `canonical_sha256` names the compiled contract, so an old record stays legible after the contract moves. | **Two different facts arrive as the same NULL** — "this tool has several capabilities" and "this lock is schema version 1, where none declares a version" — and the column cannot tell them apart. Stated here rather than discovered by whoever queries the table: the contract hash is what separates them, because the contract says which case the deployment was in. | 0178 |
| **D890** | Neither new parameter carries a `DEFAULT`, which is stricter than D857's instinct. | **Correct, and it is safe only because D887 was fixed first.** A defaulted parameter would let a caller omit the capability version for ever and leave the column quietly NULL, with nothing to say so — D816's unverified field wearing a different hat. A required one is caught offline by the arity guard, which is what makes strictness affordable here and would not have been an hour earlier. | Required, and the VALUES may still be NULL: the caller decides, and ADR 0175 checks that it did. | **The pain D857 caused is what makes the opposite choice correct now.** Session 15 Run 4 added a parameter, the product followed, four proofs did not, and a host gate found it thirteen minutes in — so the guard was built. With the guard reading both schemas, the failure mode inverts: forgetting is loud and offline, while defaulting would be silent and durable. | 0178 |
| **D892** | D866 splits the seven new capability fields across Runs 2, 4 and 7, and `schema_version` 1 → 2 *"lands once, in Run 2"*. | **Run 2's own ADR makes that impossible as written.** ADR 0177 fixed the rule that a field is REQUIRED at the version introducing it — *"requiring them at v2 keeps v2 from being a version in which they are optional and therefore absent"* — and v2 requires exactly `version`, `lifecycle`, `risk`. So Run 4's byte and concurrency limits and Run 7's dry-run and approval cannot land at v2 without breaking that rule, and landing each at its own version means **three manifest formats in one session** — which the same ADR argues against: *"a manifest format that moves twice in one session is a worse thing to hand an operator than a field whose behaviour arrives a run later."* | **Runs 4 and 7's capability fields land together, at v3, in Run 4.** Run 7 keeps dry-run's BEHAVIOUR and the approval refusal; it declares no new manifest field, because Run 4 will already have declared them. Two formats for the session, which is the minimum the run split allows. | **A decision taken in Run 2 constrained Runs 4 and 7, and the plan could not have known it** — D866 was written before ADR 0177 existed and is not wrong, it is superseded by a rule its own run produced. This is the shape §7's question 5 describes from the other end: not a decision whose callers were missed, but a decision whose *future* callers had already been scheduled. Catching it now costs a paragraph; catching it in Run 7 costs a released schema version nobody wanted. | 0177 |
| **D893** | A per-capability byte limit narrows `MAX_SERIALIZED_BYTES`, and a concurrency limit narrows the pool-derived semaphore. | **The byte budget is applied to reads and writes and NOT to metadata**: `_within_byte_budget` is called at `mcp_tools` 380 and 499, on the read result and the write result, and the two metadata tools return from the lock without passing through it. A byte limit declared on a metadata capability would therefore bound nothing. | **Run 4 forbids both new fields on a metadata capability**, extending `allOf[2]`'s `not/anyOf` — which currently lists `resource`, `columns`, `filters`, `order_by`, `max_rows`, `max_affected_rows` and would otherwise PERMIT them. | ADR 0120's rule, reached for the third time: a metadata capability is forbidden the fields describing a backing rather than merely not required to declare them, because a value invented to satisfy a schema reads exactly like a real one (D267). **The forbidden list does not extend itself**, which is what makes this a decision each new field needs rather than a default. | 0177 |
| **D894** | Run 8's profiles are *"project-local"*, so they are a capability-manifest concern. | **They move the PROJECT manifest**, whose schema is a different document with its own version: `project.schema.json` is at `enum: [1]`, and it already carries an `mcp` block. | Stated so Run 8 budgets for a **project** schema bump rather than a capability one. | **D881's split one run early is what makes this cheap.** `SUPPORTED_SCHEMA_VERSIONS` was one frozenset governing both documents until Run 2; had it still been, Run 8 would have had to move the capability manifest's accepted set to bump the project manifest's — two authorities disagreeing about two documents at once. The split was made for a reason that had not yet arrived. | — |
| **D895** | Run 10: *"ADR 0175 compares a call to a released `app_private` function against the arity its migrations declare, and Run 3 changes a table rather than a function — so the guard does not cover it."* | **Half stale, half still true.** Run 3 widened the guard to `api` as well (D887), so the first clause no longer describes it. The second stands exactly: **the equivalent question for a COLUMN is unguarded.** Nothing checks that a reader of `agent_audit` names columns the migrations declare, and 0027 added three. | **Run 10's decision is unchanged and better posed**: whether a column-level guard is worth building, taken with the trip's evidence. The row is corrected now so Run 10 does not re-derive a guard that already covers what it says is missing. | A stale sentence in a plan is worse than an absent one, because it reads as a measurement. This one would have sent Run 10 to widen a guard that had already been widened, and away from the gap that is actually open. | — |
| **D896** | Run 9 derives `bin/session-16-check.sh` by diff from `session-15-check.sh`. | **46,777 bytes and one `usage()` block.** The derivation is feasible and the warning is exact: D853 and D858 are two instances in one session of a header updated and a `usage()` left naming the previous session. | Unchanged, and the size is recorded so Run 9 budgets for a read rather than a glance. | D505, D507, D678 and D693 are the same loss in four earlier sessions; D693's guard now catches the `--session N` half automatically, and the `usage()` half is still a human reading 46 KB. | — |
| **D897** | `AGT-CAPVER-001`: *"the version reaches the audit row."* | **A tool backed by SEVERAL capabilities has no version to reach it.** `query_resource` is `query_notes` and `query_tasks` (ADR 0120); they version independently, and the record is **opened before the arguments have selected between them**, so writing either would name a capability this call may not have used. | **The requirement is satisfied and the limit is recorded here rather than inside the claim.** `_sole_capability_version` records the version when a tool has exactly one backing capability and `NULL` otherwise. `contract_hash` is recorded always. | **Two different facts arrive as the same NULL** — "this tool has several capabilities" and "this lock is schema version 1, where none declares a version" — and the column cannot separate them. The contract hash is what can: it names the compiled contract, and the contract says which case the deployment was in. Resolving it properly means recording the version once the arguments have chosen, which is Run 7's path and not this run's. | 0178 |
| **D898** | Run 4 adds a per-capability byte limit and a per-capability concurrency limit, beside ADR 0129's four budgets. | **It finishes the per-capability half of ADR 0129's own table rather than adding anything beside it.** Two of the four are already per capability — rows, by `min(caller limit, resource.max_rows)` from the lock, and elapsed time, by the lock's `timeout_ms`. The other two are not: serialized bytes is a runtime constant *a caller cannot express at all*, and concurrency is a process-wide semaphore rendered from `api.rest.pool_size` at half. | **Stated this way in ADR 0179**, because it changes what the run is. The fifth budget is Run 5's, and the stage plan's *Must not* turns on the difference. | Framed as "two new limits" it reads as growth in a plane whose bounds are load-bearing; framed as *the two that were never per capability* it is symmetry. And the framing decides the review question: not *is a fifth budget safe* but *may a capability narrow one of the four*. | 0179 |
| **D899** | `MAX_SERIALIZED_BYTES` is applied to every result this process returns, per its own docstring. | **`run_report` returned its row with NO byte check at all.** `_within_byte_budget` was split out in Session 9 so the write path would get the ceiling the read path had — its docstring cites question 5 by name — and this is the **third** caller, missed by the same split: `query_resource` reaches it through `_within_budget`, a write reaches it directly, and `run_report` returned `rows[0]`. | **The ceiling is applied**, and the finding is recorded rather than folded into the run's own work. | **Question 5 inside the function whose docstring is about question 5.** Not theoretical either: measured at **32,927 bytes for one row** when each column holds 4 KiB — and `run_report` returns exactly one row by construction, so the ROW budget can never bind on it. It is precisely the shape a byte ceiling exists for, and it was the one path without one. | 0179 |
| **D900** | 1 MiB is *"chosen and not measured"* (§9), and Run 4 records what a real response costs. | **Measured, and the two budgets genuinely cross over.** Exact, through the product's own functions: `list_resources` **354 B**, `describe_resource` **288–683 B** — 0.03–0.07% of the ceiling. Parametric, because a row's size is the caller's data: a write is **8–12 KB** at 4 KiB of content, and `query_resource/notes` costs 79 B + ~6 B per content byte per row, reaching 1 MiB at **42 rows** against a `max_rows` of 200. At 0 and 256 bytes the ROW budget binds; at 4 KiB the BYTE budget does. The crossover is around **860 bytes per column**. | **The value is not tuned** and the §9 entry is not closed — what is no longer unmeasured is what it costs to reach it. | ADR 0129 says the four budgets are independent *by decision*; this is the first time the claim is numeric. 1 MiB is roughly "two hundred rows of five kilobytes", which is a defensible page — and knowing where the two bounds swap is what makes a per-capability value a choice rather than a guess. It also settles D893 from the data side: a metadata response is 0.03% of the ceiling, so a limit there would bound nothing. | 0179 |
| **D901** | The concurrency proof measures the per-tool bound. | **It measured the CONCEPT and not the product**, and three mutations survived: dropping the per-tool slot, replacing the global with it, and letting a tool declare more than the process has. The proof built its own semaphores and its own driver, so `register()`'s `async with tool_slots(tool), read_slots:` was never executed by it. ADR 0065/0066 exactly — a proof reaching the right end state by a route the product does not take. | **Rewritten through `register()`**, in the module where `_Registry` already exists. Three arms now: the global slot is still held, a tool declaring 4 under a process of 2 is clamped to 2, and two concurrent calls against a tool bound of 1 with a global of 4 peak at **1** — which only the per-tool slot can produce. | **The test immediately above it in that file records the same lesson from Session 9**: *"no test in this repository had ever called `register()` … found this time by a surviving mutation rather than by a start."* One session later, in the same file, by the same route. The battery is what found it both times, which is the argument for running one on a wiring change even when the logic is obviously right. | 0179 |

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

Decided now, because Run 9's bump is all-or-nothing (D690) and there are no
`future` placeholders left — every requirement below arrives with its proofs in
the commit that moves the constant.

| Requirement | P | What it asserts |
|---|---|---|
| `AGT-CAPVER-001` | P0 | Every capability declares a semver and a deprecation state, and **both are read**: a deprecated capability is refused or warned per its state, and the version reaches the audit row |
| `AGT-RISK-001` | P0 | A capability's risk classification selects a behaviour — it is not a label. A high-risk capability's denial and its audit record differ observably from a low-risk one's |
| `AGT-DENIAL-001` | P0 | Every denial the plane issues carries a taxonomy reason, the reason is recorded in `agent_audit.denial_reason`, and **no reason is free text** |
| `AGT-QUOTA-001` | P0 | A windowed quota bounds an agent across requests, survives a process restart, and its refusal is audited. The fifth budget, independent of the other four |
| `AGT-IDEM-001` | P0 | A replayed write carrying the same idempotency key performs the work once and returns the stored outcome; a different key with the same body performs it twice |
| `AGT-DRYRUN-001` | P0 | A dry-run runs authorization, scope and validation, changes nothing, and is audited as a dry-run rather than as a write |
| `AGT-APPROVE-001` | P0 | A capability declaring `requires_approval` is refused with its own taxonomy reason and audited. **The refusal is the guarantee** (D870) |
| `AGT-PROFILE-001` | P0 | A project profile may only narrow the compiled contract. A profile that would widen any bound is **refused at compile time**, not at request time |
| `EVAL-HARNESS-001` | P0 | Every enabled capability has positive and adversarial cases; derived and hand-written cases are counted separately; a capability changed without its cases fails the gate **and** CI |

**Seven claims**, each with at least one live half because `claim_mode` refuses a
claim whose every proof is offline (D856):

`capability_governance` (`AGT-CAPVER-001`, `AGT-RISK-001`) · `denial_taxonomy`
(`AGT-DENIAL-001`) · `agent_quota` (`AGT-QUOTA-001`) · `agent_idempotency`
(`AGT-IDEM-001`) · `agent_dry_run` (`AGT-DRYRUN-001`, `AGT-APPROVE-001`) ·
`capability_profile` (`AGT-PROFILE-001`) · `evaluation_harness`
(`EVAL-HARNESS-001`).

**`EVAL-HARNESS-001` is deliberately one requirement covering both the harness
and its CI enforcement.** A claim purely about CI would have no live half in
either mode that exists, and inventing a fourth mode to give it one is the
symmetry ADR 0065 refuses. Its live half is the deployment's own
`capability_contract_sha256` matching the contract the harness evaluated.

---

## 4. Irreversible operations

| Operation | What makes it safe |
|---|---|
| **Migration 0027** on both projects | Fix-forward only; every down block raises AP900. It **adds** three nullable columns to `app_private.agent_audit` and adds an enum — no existing row is rewritten, and a null `denial_reason` on a historical row is correct rather than missing |
| **`schema_version` 1 → 2** on the capability manifest | A deployment carrying a v1 manifest must still render. Run 2 decides whether v2 is a strict superset (v1 manifests accepted unchanged) or a migration — **and the answer is written in the ADR before the schema changes**, because a manifest is an operator input this repository does not hold |
| **The bump** (Run 9) | `CURRENT_SESSION` 15 → 16 and `template_version` 0.4.0 → 0.5.0, all-or-nothing (D690), in one commit with all nine requirements and their proofs |
| **Deploying migration 0027 to project B** | Session 10's restore drill compares a restored cluster against the release's full migration ledger, so **B may not lag** — and a full backup of B is taken **after** the deploy, not before |
| **Repairing CI** (Run 1) | Reversible, and the only one here that is. Listed because it changes a workflow that runs on every push to `main` |

---

## 5. Build order, run by run

### Run 1 — CI back to green

**Nothing else in this session is worth building first.** The harness's stated
enforcement mechanism is *failing CI*, and CI has failed 307 consecutive times
(D861).

**First act: read the Session 1 gate job's log** — the one cause not measurable
without admin rights on the repository. The other two are known (D862) and are
not to be repaired before the third is understood, because a workflow that fails
for three reasons and is fixed for two still fails.

Then: the derived-session assertion stops being a literal, `pytest -m future`
stops being a step that exits 5 by design, and the workflow gains a proof that
neither can go stale again — **a test in the repository that reads
`.github/workflows/ci.yml` and refuses a hard-coded session number**, which is
the class guard for D862 rather than the instance.

**Done when a run on `main` is green**, observed through the API and not assumed
from a local gate.

**Done.** Run `33783525090` on `75e5e57`: all three jobs green, 2026-09-03. The
first green run since 2026-08-04, and the 315th attempt.

**Six causes, not three, and the run's real shape was a stack rather than a
list.** Four of the Session 2 job's six steps had been skipped behind an earlier
failure for a month, so each repair *revealed* the next. That is why this cost
what it did, and it is the thing to expect the next time a long-red pipeline is
opened: the visible failure is the top of a pile, and its depth is unknowable
until it is dismantled.

| # | Cause | Why it survived | D |
|---|---|---|---|
| 1 | `assert CURRENT_SESSION == 2` | a literal under a comment forbidding literals | D862 |
| 2 | `pytest -m future` exits 5 on an empty selection | D695 repaired the test and left the step running the same command | D862 |
| 3 | shellcheck unpinned — runner 0.9.0, workstation 0.11.0 | §5.3's pin rule was applied to uv and never to the linter | D875 |
| 4 | two proofs asserting `/var/lib/agentic-postgres` is unreadable | true here since a deploy in August; false on a fresh machine | D876 |
| 5 | the suite ran before the fixtures were rendered | `.generated/` survives between local gate runs; 88 errors, one `FileNotFoundError` | D877 |
| 6 | `systemd-analyze verify` had **never passed** | the step exists only in the workflow, so nobody ever ran it | D878 |

**Three of the six are one sentence: the developer machine carries state a fresh
one does not.** Which makes the durable finding of this run not any of the
repairs but the instrument — **CI is the only place this project's contract
suite runs on a machine that has never deployed anything.** That is
`fresh_host`'s property applied to the suite, and eight sessions of green offline
runs never touched causes 4 or 5. §7's sixth question asks whether a proof shares
a belief with its subject because one author wrote both; here the belief was
shared with the *machine*, and no author was involved.

**Cause 6 is the one to carry forward.** It ran roughly three hundred times and
succeeded zero, which is the answer §7's second question exists to get — *has it
run at all, in this environment, since the thing it measures last changed?* **A
check that has never passed and a check that has never run are indistinguishable
from outside**, and this repository had both, in the same job, for a month.

**One diagnosis was wrong and is recorded rather than quietly dropped** (D875).
The clean-clone reproduction died at step 2 on the lock check and was treated as
the cause; the runner was dying one command earlier, on the linter. ADR 0065/0066
inverted — the rig reached the same end state by a route the runner does not
take, and it was believed because its verdict agreed. ADR 0176 is kept because
the defect it repairs is real and would have surfaced the moment the linter was
pinned.

**What made the second half fast was a credential.** Job logs and the evidence
artifact need `Actions: read`; without it, five causes were being inferred from
artifact counts and step conclusions. With it, causes 4, 5 and 6 took ten minutes
between them. **A pipeline whose failures cannot be read is not a signal**, and
the first thing a future session should check is whether that token still exists.

### Run 2 — capability schema v2: version, deprecation, risk

`schema_version` 1 → 2. Three fields, and **each arrives with its reader in the
same run** (D816): a semver, a deprecation state, and a risk classification.

The `if/then` branches decide where each belongs (D866). Measure before writing:
a metadata capability is currently forbidden most optional fields by
`allOf[2]`'s `not/anyOf`, and whether these three are exceptions is a decision,
not an oversight to route around.

**ADR 0176** records the version bump's compatibility rule — whether a v1
manifest still renders — decided before the schema moves.

**Done.** ADR **0177**, not 0176 (D879). CI green on `4795412`, run
`33787745473`, all three jobs.

**Each field has a reader, and one of the three readers is deliberately not a
behaviour.** `version` reaches the canonical contract, the lock and the catalog.
`lifecycle` is behavioural: a `retired` capability may not be `enabled` and the
compiler refuses it — the existing rule reached by a declaration, since
`compile_canonical` already drops disabled capabilities entirely, so retirement
is enforced by the lock's **absence**. `risk` is validated only — a metadata
capability must be `low`, a write may not be.

**`AGT-CAPVER-001` and `AGT-RISK-001` do not close here** (D880). Their readers
are migration 0027's columns and Run 3's denial taxonomy. Risk could have
selected a behaviour today by narrowing `max_affected_rows` or `timeout_ms`, and
that would make it a **second authority** over two of ADR 0129's four budgets,
which are independent by decision. **A requirement reported closed on a
validation rule would be claiming a behaviour nobody built.**

**The deploy-breaking half was D882**, and it was found by reading the generated
catalog rather than the code: *"an unknown `schema_version` fails the start
rather than being ignored"*. `mcp_lock` held `SUPPORTED_SCHEMA_VERSION = 1` and
compared with `!=`. A release compiling a v2 lock against that runtime deploys a
project whose MCP service never comes up, at **step 6b**, mid-convergence. The
runtime learns 2 in the same run, and the compiled contract's version becomes
**the manifest's** rather than a constant — because `capabilities.yaml` lives
only on the host and no commit can edit it, so a v1 manifest still has to render.
Both directions of the gate are enforced: a v1 lock *carrying* the fields is
refused, or the version number would be decorative, and at v1 the fields are
**absent rather than defaulted** (D600).

**Two rows are about proofs rather than product.** D884: replacing `max(risk)`
with `declared[0]` **survived**, because every capability in the example manifest
shares its tool's risk — the run's only derivation had never been reached with
inputs that disagree. D885: two mutations reported `NOT RUN`, which sits in the
same column as a survivor, because parametrized victims report as `name[param]`
and the rig keyed on the exact node id. **The apparatus was the defect twice in
one battery**, and `NOT RUN` is the reading a battery is least likely to
question. All eight killed after both repairs.

**What Run 3 inherits**: migration 0027, the denial taxonomy, and the two
requirements this run declined to close. `Tool.risk` and `Tool.capabilities` are
already parsed and reach the runtime, so the audit row's inputs exist.

### Run 3 — migration 0027 and the denial taxonomy

`capability_version`, `contract_hash` and `denial_reason` on
`app_private.agent_audit`, plus a `denial_reason` enum. **No free text**: a
denial reason a caller could influence is a caller value in an operator's
console, which the agent plane's standing rule forbids.

**The taxonomy is derived from the refusals that already exist** — scope,
allowlist, budget, drift, credential — rather than invented, and a contract test
asserts every refusal path in the runtime maps to exactly one member. That guard
is the run's real output: it is what stops a sixth refusal being added later
with no reason attached.

**Done.** ADR **0178**, migration **0027**. CI green on `98371cc`.

**Eight members, not five, and the derivation contradicts this paragraph in both
directions** (D886). Four of the named five are real. **`credential` is not a
refusal this plane can issue**: the MCP runtime holds no credential of any kind,
so the member could not describe its own — and if it meant the *caller's*,
`mcp_upstream`'s own header measures **four states behind two statuses**. Naming
one of them `credential` is D433's forbidden guess, and it is worse in a durable
record than in a response, because whoever reads it later cannot re-derive what
was true. `upstream_refused` is the honest form. Four members the brief did not
name do exist: `input_malformed`, `upstream_refused`, `audit_unavailable`,
`write_rejected`.

**`AGT-DENIAL-001`, `AGT-CAPVER-001` and `AGT-RISK-001` are satisfied by this
run**, with one limit recorded rather than buried (D897). Every denial carries a
taxonomy reason, no reason is free text — it is a Postgres enum, so the catalog
refuses one rather than a convention discouraging it — and the version and the
contract hash reach the audit row.

**The finding that outlives the run is D887, and it is about a guard.** ADR
0175's arity check read `app_private` alone, and `api.agent_audit_begin` and
`api.agent_audit_complete` are the two functions the agent plane calls on **every
request**. This migration widened both signatures and the guard stayed green:
simultaneously the most-called released functions in the tree and the least
covered. Question 5 for the **fourth** time this session, after D719, D871 and
D874.

**Widening it took three corrections and the guard forced every one** (D888), by
reporting something the tree proved was fine — which is the good failure mode. It
did not model `DEFAULT`; a `DROP` retires a declaration's whole callable range
rather than the count it spells; and seven of its nineteen findings were not
calls at all. Both new rules were measured against **all 157 real calls** before
being written. **A guard that cries wolf about correct code gets widened back**,
which is how this one would have died a session after it was built.

**Verified against a real cluster** through the suite's own fixture, twenty-seven
migrations applied as `migration_user` over TCP: the enum and its order, the
equivalence CHECK in both directions with the control between them, both
functions at their new arity with no overload surviving, the grants surviving
the `DROP` with a role that must NOT hold them as the control, and a refusal
recorded end to end through the functions rather than the table.

Eight mutations, each with a control it cannot reach, all killed. One was
uninformative on its first attempt and is recorded as such: adding an unused
`credential` constant does not make it a member, and the guard was right to pass.

### Run 4 — per-capability byte and concurrency limits

Bounded **by** ADR 0129's existing four, not beside them: a per-capability byte
limit narrows `MAX_SERIALIZED_BYTES` and a per-capability concurrency limit
narrows the pool-derived semaphore. **Neither may widen**, which is the same
monotonicity D867 fixes for profiles and the reason those two runs share an
invariant.

**`schema_version` 2 → 3, and it carries Run 7's two fields as well** (D892).
ADR 0177 requires a field at the version that introduces it, so dry-run and
approval are declared here rather than in a second bump — two manifest formats
this session instead of three. Run 7 still owns their behaviour.

**All four are forbidden on a metadata capability** (D893), extending
`allOf[2]`'s `not/anyOf`: `_within_byte_budget` is never applied to a metadata
result, so a byte limit there would bound nothing.

`MAX_SERIALIZED_BYTES` is *"1 MiB, chosen and not measured"* (§9). This run does
not tune it, and says so — but a per-capability limit read against an unmeasured
global is a bound on a guess, so the run **measures what a real response costs**
for each of the seven capabilities and records it, which is the cheap half of
retiring that §9 entry.

**Done.** ADR **0179**. CI green on `7a67fb5`, run `33800126152`.

**The run is the second half of ADR 0129's table, not a fifth budget** (D898).
Rows and elapsed time were already per capability; bytes and concurrency were
not. Framed as "two new limits" it reads as growth in a plane whose bounds are
load-bearing; framed as *the two that were never per capability* it is symmetry,
and it decides the review question — not *is a fifth budget safe* but *may a
capability narrow one of the four*.

**Two findings, and both came from measuring rather than reasoning.**

**D899.** `run_report` returned its row with **no byte check at all**.
`_within_byte_budget` was split out in Session 9 so the write path would get the
ceiling the read path had, and its docstring cites question 5 by name — this is
the third caller, missed by the same split. Measured at **32,927 bytes for one
row** of 4 KiB columns, and `run_report` returns exactly one row by construction,
so the row budget can never bind on it. The one path a byte ceiling exists for,
and the one without one.

**D901.** The concurrency proof measured the concept and not the product: it
built its own semaphores and its own driver, so `register()`'s
`async with tool_slots(tool), read_slots:` was never executed by it, and three
mutations survived. **The test immediately above it in that file records the same
lesson from Session 9** — same file, same route, one session later. Rewritten
through `register()`, and the arm that matters is two concurrent calls against a
tool bound of 1 under a global of 4 peaking at **1**, which only the per-tool
slot can produce.

**D900** is the measurement §9 asked for, and it makes ADR 0129's independence
numeric for the first time: the row and byte budgets cross over at roughly 860
bytes per column. The value is **not** tuned and that §9 entry is **not** closed.

### What this leaves for Run 10, and it is not in §5 yet

**The host's `capabilities.yaml` is still schema version 1.** Every version still
loads, deliberately — but that means the deployment runs the oldest shape:
no `version`, no `lifecycle`, no `risk`, no per-capability bounds, and
`capability_version` NULL in every audit row. **Everything Runs 2, 3 and 4 built
is inert on the host until somebody edits that file**, and it is a gitignored
operator input that exists in exactly one place with no copy in git.

Run 5 adds a sixth thing to the same file. So the trip has an operator step
nobody has costed: migrating seven capabilities across four to seven new fields,
by hand, against a schema. **Whether a `--migrate-manifest` helper ships in Run 8
or 9 is a decision, and it is cheaper taken now than discovered at the trip.**
### Run 5 — windowed quotas, the fifth budget

**Read ADR 0129 first**, per the stage plan's *Must not* and D865.

The first budget whose state outlives a request, is contended by two processes,
and can be wrong after a restart. **ADR 0176's sibling ADR records what makes it
different**, and the run decides retention in the same breath: the quota table is
read on **every** request, so its growth is a latency problem before it is a disk
one — unlike `agent_audit`, which grows without bound and is read by an admin
endpoint.

Measure the concurrent case with a control that proves the rig has a real race,
exactly as Session 15 Run 2 did for the refresh plane — the outcome of two
requests crossing a window boundary is decided by the isolation level, and that
is a measurement, not a design choice.

### Run 6 — idempotency keys

New construction (D864). A caller-supplied key, durable dedupe state, and a
stored outcome returned on replay.

**The stored outcome is the hard part and the plan names it now**: returning a
recorded response means the plane holds a caller's prior result, which is a value
the redaction rules must cover before it is stored, not after. `agent_audit`
already stores `parameters` pre-redacted by the lock's `audit.redact` and
redacts nothing itself — **the same authority applies here or the run has
created a second one**.

### Run 7 — dry-run, and approval as a refusal

**The manifest fields arrive in Run 4** (D892); this run is their behaviour.

Dry-run ships fully: authorization, scope and validation run; nothing changes;
the audit row records a dry-run rather than a write. **The audit distinction is
the point** — a dry-run recorded as a write would make every write count in the
audit table a lie.

Approval ships as a declaration and a named refusal (D870). Not a workflow.
### Run 8 — project-local profiles

**A profile may only narrow** (D867), and the refusal is at **compile time**: a
profile that would widen any bound fails `mcp-contract.sh check`, before a
deployment exists, rather than at request time where it would be one more
runtime denial.

### Run 9 — the evaluation harness, and the bump

Adversarial cases **derived from the compiled contract**, per field, plus
hand-written ones counted separately (D868). The harness fails the gate and CI
when an enabled capability has no cases.

Then the bump: `CURRENT_SESSION` 16, `template_version` 0.5.0, nine requirements,
seven claims, `bin/session-16-check.sh` **derived by diff from
`bin/session-15-check.sh`** — and its `usage()` block rewritten, not only its
header, which is the half Session 15 missed twice (D853, D858).

### Run 10 — the host trip

Gate in every mode the evidence needs, **once**, before the trip.
`pytest --setup-plan` first (D671, D676).

**And run the arity guard's question against this session's own work**: ADR 0175
compares a call to a released `app_private` function against the arity its
migrations declare, and Run 3 changes a table rather than a function — so the
guard does not cover it. **The equivalent question for a column is unguarded**,
and whether that becomes a second guard is Run 10's decision, taken with the
trip's evidence rather than before it.

---

## 7. Evidence and claims

What each claim may honestly report **before its live half exists**, fixed now so
no proof is shaped to a verdict (D820).

| Claim | Offline may report | Needs a live half for |
|---|---|---|
| `capability_governance` | The schema accepts and rejects; the compiler reads all three fields | A deprecated capability refused **by the deployed plane** |
| `denial_taxonomy` | Every runtime refusal path maps to one member | A denial recorded in the deployed `agent_audit` with its reason |
| `agent_quota` | The window arithmetic and the refusal | The bound holding **across a restart**, and under concurrency |
| `agent_idempotency` | Dedupe logic and the stored-outcome shape | A replay against the deployed plane returning the first outcome |
| `agent_dry_run` | Validation runs, the write does not | The audit row on the deployment saying `dry_run`, not `write` |
| `capability_profile` | A widening profile refused at compile time | The deployed lock matching the profile that produced it |
| `evaluation_harness` | Case counts, derived vs written, the CI guard | `capability_contract_sha256` on the deployment matching what the harness evaluated |

**No claim spans both `host` and `external` mode. A skip is not a pass**, and an
offline half may not stand in for a live one.

**The eight inherited `not_run` claims stay `not_run`.** Session 16 closes none
of them and **must not appear to** (D478). `bootstrap_identity` in particular
needs two rotations performed (D860) and this session performs none.

---

## 8. Security invariants this session touches

| Invariant | Control | Proof |
|---|---|---|
| A profile cannot widen what a deployment permits | Monotone narrowing, refused at compile time | `AGT-PROFILE-001` |
| A per-capability limit cannot exceed the global | Same monotonicity, applied to bytes and concurrency | `AGT-QUOTA-001`, Run 4's proofs |
| A denial reason is never caller-influenced | An enum, not text | `AGT-DENIAL-001` |
| A dry-run changes nothing and says so | Audited as `dry_run`; the write path is not entered | `AGT-DRYRUN-001` |
| A stored idempotent outcome carries no unredacted value | The lock's `audit.redact` is the one authority | `AGT-IDEM-001` |
| The MCP runtime holds no credential | Standing, enforced | Unchanged |
| No upstream status is relayed to a caller | Standing (D433) | Unchanged |
| No allowlist is weakened to a subset check | Standing (D300, three instances in one session) | Unchanged |

---

## 9. Stop conditions

Stop and ask when:

- **The Session 1 gate's CI failure turns out to be environmental rather than
  repairable** — a runner image change, a dropped upstream package. Then Run 1 is
  a different run than this plan describes, and the harness's CI enforcement
  needs a different mechanism.
- **A v2 capability manifest cannot accept a v1 one.** `capabilities.yaml` is a
  gitignored operator input this repository does not hold, so a breaking schema
  change is a change to a file only the host has.
- **The windowed quota would need a second identifier** for something
  `authz_version`, `credential_version` or the request id already answers. That
  is ADR 0002's second authority, which this project has paid for twice in one
  session (D680, D682).
- **A profile would need to widen** anything to be useful. That is the signal
  that "profile" is being built as an override, and the answer is to stop rather
  than to add an exception.
- **The harness's derived adversarial cases turn out to be trivially satisfiable**
  — every one denied by the same first check. Then the harness measures one
  guard, not the contract, and its case-generation strategy is wrong.
- **Approval starts growing durable pending state.** D870 scoped it to a
  refusal; a pending record is the beginning of the workflow this session does
  not build.
- **More than one of Runs 5, 6 and 7 needs its own migration.** The plan budgets
  0027 for Run 3, and a second is possible — a third means the session is larger
  than ten runs and that is worth saying out loud rather than absorbing.

---

## Appendix — what to consult

`docs/plans/stage-2-plan.md` §2, §3, §5 and §11. `docs/scope-closure.md` §2 —
**and check its premise before acting on it**, which is what D860 cost.
ADR 0129 before Run 5 (the four budgets), ADR 0002 before Runs 5 and 8 (single
authority), ADR 0120 and 0140/0141 for the tool-name and scope boundaries,
ADR 0135 for what the audit record is and who writes it, ADR 0175 for the arity
guard Run 10 asks a column-shaped question about.

**Grep the plans for anything this session touches.** Nothing indexes the ~870
measured facts by subject.
