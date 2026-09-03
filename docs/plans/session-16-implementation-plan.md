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

**Next free number after this table is D875.**

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

### Run 2 — capability schema v2: version, deprecation, risk

`schema_version` 1 → 2. Three fields, and **each arrives with its reader in the
same run** (D816): a semver, a deprecation state, and a risk classification.

The `if/then` branches decide where each belongs (D866). Measure before writing:
a metadata capability is currently forbidden most optional fields by
`allOf[2]`'s `not/anyOf`, and whether these three are exceptions is a decision,
not an oversight to route around.

**ADR 0176** records the version bump's compatibility rule — whether a v1
manifest still renders — decided before the schema moves.

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

### Run 4 — per-capability byte and concurrency limits

Bounded **by** ADR 0129's existing four, not beside them: a per-capability byte
limit narrows `MAX_SERIALIZED_BYTES` and a per-capability concurrency limit
narrows the pool-derived semaphore. **Neither may widen**, which is the same
monotonicity D867 fixes for profiles and the reason those two runs share an
invariant.

`MAX_SERIALIZED_BYTES` is *"1 MiB, chosen and not measured"* (§9). This run does
not tune it, and says so — but a per-capability limit read against an unmeasured
global is a bound on a guess, so the run **measures what a real response costs**
for each of the seven capabilities and records it, which is the cheap half of
retiring that §9 entry.

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
