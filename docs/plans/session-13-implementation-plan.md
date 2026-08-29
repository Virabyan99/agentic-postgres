# Session 13 — release identity and the upgrade path

The first Stage 2 session. It makes the version this repository already publishes
mean something, gives an operator a plan before a mutation, and puts one front
door over the twenty-five verbs that already exist.

**It introduces no versioning, writes no second CLI, and closes D697 only as far
as the evidence model actually permits — which is less far than the ledger says.**

**Read `docs/plans/stage-2-plan.md` first.** It owns where Stage 2 starts, why
there are six sessions, and the open items carried in. This document does not
repeat them.

---

## Status — read this first

```
SESSION 13 IS OPEN.  Nothing built yet; this is the plan.
HEAD            89db7fb, clean, pushed. Stage 2 plan at dcd8afc.
CURRENT_SESSION 12, and it moves to 13 in Run 7 -- ALL-OR-NOTHING (D690).
template_version 0.1.0-dev -> 0.2.0, Run 7.
divergences     D719-D733 recorded here. **Next free: D734.**
ADRs            161. This session writes ONE, in Run 3. Next free: 0162.
gate            session-13-check.sh, derived BY DIFF from session-12's (Run 7).
host            One trip, READ-ONLY. Runs 9+.
```

**Three facts change the shape of this session, and all three were measured
before it was planned:**

1. **The version already exists and is already published.** `VERSION` holds
   `0.1.0-dev`; `template_version()` reads it; it is written into every rendered
   and deployed document. **Four of Session 13's five "introduce a version" items
   are already there** (D704). What is missing is the *rules*.
2. **The upgrade plan is not a new mechanism** (D723). `deploy-project.py`'s step
   0 is already *"Preflight — read everything, change nothing"*, and
   `preflight.py` is already a pure module with the three-verdict model.
3. **A claim needs a live proof, in exactly one mode.** So Session 13 cannot close
   without a host trip, and D697 cannot be closed by bookkeeping (D720, D721,
   D722).

---

## 0. Where Session 13 actually starts

Stage 1 closed at `39d5d01` with 57 of 61 claims passed; one documentation commit
has landed since. Both projects run on `62.238.99.122` through Session 12,
16 containers, `doctor.sh` at 8 ok / 0 warning / 0 problem / 0 unknown.

`docs/plans/stage-2-plan.md` §3 fixes this session's scope: **spec sessions 13
and 15, merged.** Compatibility rules on `template_version`, the `upgrade` verbs,
`apg` as a thin dispatcher, and the D697 debt.

**There is no runbook and no session summary.** What Session 13 has is
`stage-2-consolidated-spec.md`'s Session 13 and Session 15, and the stage plan's
§1 rows D704 and D707 already saying where each is wrong about this repository.
So §1 below is the *second* pass: what is wrong about the **plan**, measured
against the code the plan will touch.

**Three decisions were taken before this document was written**, and they are
recorded as taken rather than argued here:

| Decision | Taken |
|---|---|
| **D697** | Close what the model permits; make the register **permanent** for the rest. No claims-model change |
| **`apg`** | **Thin dispatcher**, this session. `apg <verb>` execs the existing script; nothing is moved or renamed |
| **Host scope** | **Read-only.** Plan against both live projects and prove the deployment is unchanged. No live project is upgraded by code with no host history |

---

## 1. The divergence table

Six columns, the house shape. **Every row is a fact measured against the tree at
`89db7fb` during planning**, with the file and line behind it. Rows added during
the runs follow the same rule (D267).

**Next free number after this table is D734.**

| # | The plan says | The repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D719** | Session 13 writes `evidence/session-13.json`, as every session before it has, through `bin/write-session-evidence.py --session 13`. | **It refuses.** `bin/write-session-evidence.py:274` holds `if not 1 <= args.session <= 12: parser.error("--session must be between 1 and 12")`, and the bound is restated in its `--help` at line 248. **A second authority for a number `CURRENT_SESSION` owns** — and `tests/contract/test_gate_contract.py` already forbids exactly this in the *gate scripts* (`test_the_gate_does_not_hard_code_a_session_number`, `test_the_gate_derives_the_acceptance_session_from_the_package`). The evidence writer was never covered by it. | **Run 2**: derive the bound from `CURRENT_SESSION`, and **widen the existing guard to cover the writer** rather than adding a second one. | **ADR 0002 at the release layer**, and it fails *closed* — which is why it survived twelve sessions: the bound was right every single time it was checked. **It becomes wrong the first time the number moves**, and the first thing a Stage 2 session does is move it. This is question 5 — *when a decision is implemented, which of its callers got it?* — answered wrong by a guard that named the gates and not the writer. | 0002 |
| **D720** | `docs/scope-closure.md` §4 on the 37 unclaimed requirements: *"Effort to close: **small**, and it is **bookkeeping rather than proof** — group the 37 into claims and extend the introduced-in table."* The stage plan repeated it. | **21 of the 37 cannot become claims at all.** `claim_mode` raises `ClaimError: claim has no live proof: every test it names runs in a checkout` when no node id carries a `live_host` or `external` marker. **Measured** (`/tmp/orphans.py`, both sides non-empty so the scan discriminates): 16 have a live proof, **21 do not** — `CFG-001`–`CFG-015`, `DX-002`, `DX-003`, `DBX-MIG-002`, `DBX-MIG-003`, `DBX-PG-002`, `AGT-DRIFT-001`. | **The 21 are not debt. They are unclaimable under the model as it stands**, and `UNCLAIMED_BY_HISTORY`'s docstring is rewritten to say so — from *"never retrofitted"* to *"structurally unclaimable, measured in Session 13"*. `docs/scope-closure.md` §4 is corrected rather than left standing. | **A ledger's effort estimate is a claim like any other, and this one was never measured.** It says *bookkeeping*; the measurement says a third of the register needs a decision about **what a claim is** — ADR 0089/0045 territory, an evidence-merge change, and every gate from 1 up gaining claims to report. **The estimate was written in the same session as the guard that made it checkable**, and nobody ran the check. | 0045, 0089 |
| **D721** | The remaining 16 are 16 claims waiting to be written. | **`claim_mode` also refuses a claim spanning more than one mode**: *"one evidence half would have to report a verdict on tests it could not run."* **`OPS-HEALTH-001` and `SEC-TLS-001` each carry both `live_host` and `external` markers**, so neither can form a claim alone. | **Both are split where the measurement is**, or they stay in the register. The precedent is exact and already in the code: ADR 0045 split a drafted `direct_transport` into `direct_transport` ("the endpoint works for the tools that need it") and `transport_boundary` ("neither transport is reachable from outside") for this reason. | The failure is not hypothetical — it is the *same* failure, on the *same* axis, five sessions later. **Splitting a claim is a decision about what two guarantees are**, not a mechanical consequence, which is why these two are named here rather than absorbed into a count. | 0045 |
| **D722** | This plan's own Run 6, first draft: *"group the 16 that have live proofs into claims."* | **Three of the 37 are already reasoned about, in `evidence_claims.py`'s own commentary, and the D697 investigation read none of it.** Measured with a control: `SEC-NET-001` — one of the 16 — **was written as a `public_boundary` claim and REMOVED**, because its proofs include an IPv6 scan and no network available to run the external gate has IPv6 transit, so *"the claim could only ever come out failed — not because the boundary is open but because nobody can look at it from here."* `DBX-MIG-002` and `DBX-MIG-003` are documented as *"entirely properties of a checkout… not guarantees about a running system."* | **The honest split is 13 / 2 / 1 / 21**: thirteen can form a claim straightforwardly, two need D721's split, **one is a decided non-claim**, and twenty-one have no live proof. Run 6 closes the thirteen, decides the two, and leaves `SEC-NET-001` where a deliberate decision already put it. | **D697 found the gap by asking the registry a question nobody had asked, and then did not read the answer already written next door.** This is D726's shape and question 2's: *has anything looked at this since it changed?* A count of 37 that includes three deliberate decisions is not a debt register — it is a list that stopped distinguishing *undone* from *decided*. | 0045 |
| **D723** | Session 13 builds `upgrade check` and `upgrade plan`: a new command that inspects a deployment and reports what an upgrade would do, without mutating it. | **Both halves exist.** `bin/deploy-project.py`'s **step 0 is literally *"Preflight — read everything, change nothing"***, with the comment *"the number matters: everything above this line reads"* — and it runs `observe_prerequisites` then `preflight.report(checks)` then refuses. `src/agentic_postgres/preflight.py` is already **pure** (*"nothing here reads a file, runs a process or touches the network"*) with a **three-verdict** model — `PRESENT`, `ABSENT`, `UNDETERMINED` (ADR 0157) — written precisely so a check can say *"nobody could ask"* instead of printing a false negative. | **`upgrade check` is that model applied to a deployed project, and `upgrade_plan.py` is its sibling**, built the same way: pure logic in `src/`, subprocesses in `bin/upgrade.sh`. **Not a new mechanism beside it.** | The three-verdict model is the whole reason a plan can be trusted: a two-valued check reports *"the edge plane is not running"* when it means *"nobody could ask"*, which is D600's family. **An upgrade plan that cannot say "I could not look" is a plan that guesses**, and a guess is the one thing a pre-mutation gate must not produce. | 0157 |
| **D724** | The compatibility rules attach to `template_version`, so the document's version field is the anchor. | **`template_version` is `{"type": "string", "minLength": 1, "maxLength": 64}`** in `schemas/outputs.schema.json` — **no pattern, no semver constraint.** It will accept `banana`. | **Run 1 measures before Run 3 decides**: do both live deployed documents' values satisfy a semver pattern, and does adding one require `schema_version` 13 → 14? | **It looks free and may not be.** Tightening a constraint on an existing field rejects documents that were valid, which is exactly what a schema version exists to express. `0.1.0-dev` *is* valid semver-with-prerelease, so the offline answer is probably yes — **and the offline answer is about the checkout, not about the two documents on the host.** Measure both. | 0012, 0027 |
| **D725** | `upgrade plan` diffs the installed deployed document against the rendered candidate, reusing the leaf-walker Session 12 built. | **The walker is `_leaves()` in `tests/deployment/test_session12_isolation_matrix.py` — a test module, not `src/`.** Reusing it means moving it, and the matrix is a green Session 12 proof over 179 leaves. | **Decided in Run 4, not assumed here.** If it moves, the matrix imports it and its own tests are unchanged; §6's rule permits replacing a passing test with a stricter one and forbids weakening it, and a move is neither until it is written. | **The classification lists must not move with it.** `MUST_DIFFER` / `MUST_MATCH` / `RELEASE_STATE` are an isolation judgement about two projects; a diff between two *releases of one project* is a different question over the same leaves. **Sharing the walker is right; sharing the categories would be D702 again** — a list derived from one observation, reused where its accidents do not hold. | — |
| **D726** | `bin/apg.sh`, `bin/upgrade.sh` and `bin/session-13-check.sh` are three new files. | **Each fails the suite until it is registered.** `SHELL_COMMANDS` in `tests/contract/test_cli_contract.py` enumerates 43 commands by name, and `test_every_command_in_bin_is_covered_by_this_module` refuses one that is not listed. Every entry also owes `test_shell_script_preamble` a `#!/usr/bin/env bash`, `set -euo pipefail` and a `BASH_SOURCE` root resolution; `test_help_exits_zero_and_says_something`; `test_no_file_uses_crlf`; and `test_no_command_defines_anything_after_its_entry_point`. | **Registered in the run that creates each**, not at the end. | **Session 11 forgot exactly this and its first offline run caught it** — which is the good outcome and still cost a cycle. `test_no_command_defines_anything_after_its_entry_point` is D185's guard, and a **dispatcher is the shape most likely to trip it**: a `case` block calling functions defined below it is the natural way to write one and does not work. | 0158, D185 |
| **D727** | `docs/scope-closure.md` §4: *"The guard worth writing first: a test that every registered requirement belongs to exactly one claim. Without it the same gap reopens the next time a session adds a requirement in a hurry."* | **It already exists.** `test_no_new_requirement_goes_unreported_by_every_claim`, in `tests/contract/test_evidence_claims.py`, written in **the same session as the ledger recommending it** — and it carries the staleness check the ledger did not ask for. | The ledger's §4 is corrected in Run 6 alongside its effort estimate (D720). | **A recommendation that outlived its own implementation by one document**, in a repository whose §7 opens with *a value that looked measured and was not*. It is harmless here and it is the same reflex that produced D722: **writing the next step without reading what the last one shipped.** | — |
| **D728** | Run 6 groups orphaned requirements into claims — including, where natural, into claims that already exist. | **Adding an older requirement to an existing claim can withdraw that claim from an earlier session's evidence**, and `evidence_claims.py` says so from Session 4: `claim_session` is the **max** of its requirements' sessions, so a Session 3 claim gaining a Session 4 requirement *"would move the whole claim to Session 4 — and `claims_through_session(3)` would then stop returning it. Session 3's gate would quietly stop recording a claim it has been recording, and the jq expression its operator guide documents would fail against freshly written evidence."* | **Run 6 adds no orphan to an existing claim.** Every group it makes is a **new** claim whose `claim_session` is the max of its own members — which for Sessions 1–4 orphans means an early session, and `merge`'s unrecorded-claims check must be satisfied by those gates' modes. **Checked per claim before it is written**, not after. | **This is D696 in the other direction and it is worse**, because D696 moved a claim *forward* and a guard caught it. This one moves a claim forward and **the guard is the operator guide's documented jq expression failing on a re-run** — which nobody runs until they need it. The record has existed since Session 4; Run 6's job is to read it before grouping, not after. | 0039 |
| **D729** | Housekeeping, found by the Stage 2 audit rather than looked for (D718). | **`&1` is a tracked, zero-byte file in the repository root** — a redirect written as `>&1` where the shell took `&1` as a filename. And CLAUDE.md §2's status block names `39d5d01` while HEAD is `89db7fb`; local and `origin/main` agree, so the block is stale rather than the tree. | Both in **Run 8**, with D533's undiarised apt pin. | Small, and the shape that survives because nothing reads a root directory listing. **Zero bytes is the reason it survived**: it shows up in no diff, breaks no build, and appears in `git ls-files` between `README.md` and `VERSION` where an eye slides past it. | — |
| **D730** | Run 1 reads `alpha-outputs.json` and `beta-outputs.json` from the repository root for D724's *live* half — they are deployed documents for the two projects on the host. | **They are TRACKED in git and they are six sessions stale.** Measured: `schema_version` **10**, `deployed_through_session` **6**, `source_commit` `e842cc05`, `observed_at` **2026-08-15**. The host runs Session 12 at schema v13. **They do not validate against the current schema at all** — Rig A reported both `INVALID` today, before any patch. Four operator guides (Sessions 5, 6, 9, 10) name `./alpha-outputs.json` as the path to pass to `--project-a-outputs`. | **Run 1 does not use them for anything.** They are deleted in **Run 8** beside `&1`, and the operator guides' example paths are left alone — each is a record of its own release. | **`MUST_AGREE` catches it, and only at the merge.** `source_commit` is one of its four fields, so an external half built from these would refuse to merge with a Session 12 host half — **four steps from the cause** (D465's shape). Before that point the external suite runs happily: it reads the document for *identities*, and a Session 6 route still resolves. **A stale observation in source control is worse than an absent one**, because it has the shape of the real thing and a filename that reads as current. | 0465 |
| **D731** | **D724 answered, offline half.** Constraining `template_version` to semver may reject documents that validate today, and may need `schema_version` 13 → 14. | **It rejects nothing.** Measured (Rig A, control holds): every `template_version` reachable in the tree is `0.1.0-dev` — the `VERSION` file, both stale deployed documents, both rendered fixtures — and `0.1.0-dev` **is** valid semver 2.0.0 with a prerelease. Adding the pattern to both `$defs` members caused **0 regressions** among documents that validate today. **The control discriminates**: a probe with `template_version: "banana"` is **accepted** by the current schema and **refused** by the patched one. | The pattern is safe to add on the evidence available. **Whether it needs a version bump is Run 3's decision, not this measurement's** — a tightening rejects values that *were* legal, and whether that is breaking is a policy question about the contract rather than about the corpus. | **The live half is NOT measured and is not claimed.** `apg-diag`'s eight verbs — `containers labels logs routes listeners edge-log catalog generation` — include **none** that returns a deployed document, so the live values cannot be read without the operator's `sudo install -o op`. Every value in the tree says `0.1.0-dev` and the field is derived from the release's `VERSION`, so the inference is strong — **and an inference is not a measurement** (D267). | 0012, 0027 |
| **D732** | **D725 answered.** `upgrade plan` diffs the installed **deployed** document against the **rendered** candidate, reusing Session 12's leaf walker. | **The two kinds share 41% of their leaf vocabulary** — 68 shared of 165 in the union; 87 leaves in `renderedDocument`, 146 in `deployedDocument` (Rig B, control holds). Worse than the absences: **six of the seven routes have a different SHAPE in the two kinds.** `routes.app`, `routes.app_docs`, `routes.docs`, `routes.mcp`, `routes.rest` and `routes.storage` are a **string** in the rendered document and an **object `{status, url}`** in the deployed one. Only `routes.health` matches — which is the rig's control, and it is what proves the comparison is about the schema rather than about the walker. | **The plan does not diff the two kinds.** See D733 for what it diffs instead. | A naive leaf diff across the kinds would report **every route as changed on every run**, plus 78 deployed-only leaves as *removed* and 19 rendered-only ones as *added* — a plan whose output is dominated by the fact that it is comparing two vocabularies. **It would look like a working diff**, which is the failure mode: it produces a plausible answer to a question nobody asked. | — |
| **D733** | The deployed document is the record of what is installed, so it is the left-hand side of an upgrade plan. | **It cannot answer the question an upgrade plan exists to ask.** `renderedDocument.inputs` carries the five digests that say whether the inputs changed — `project_sha256`, `capabilities_sha256`, `secrets_contract_sha256`, `versions_lock_sha256`, `source_specification_sha256` — and **`deployedDocument` has no `inputs` block at all**, measured directly. **But the rendered document of the installed release is on the host**: `deployed_output.rendered_path(key)` is *"the installed rendered directory"*, and `install_rendered` puts it there on every deploy. | **`upgrade plan` diffs `rendered_path(key)/outputs.json` against a freshly rendered candidate.** Two documents of the **same kind**, same vocabulary, same shapes, both carrying the five input digests. The deployed document keeps its own job — ADR 0158's address book, and the *observation* half of `upgrade check`. | **This is ADR 0158 arriving at a new subject.** *The deployed document is the address book, not the diagnosis* — and an upgrade plan is neither: it is a comparison of two **intents**, which is what a rendered document is. The first design reached for the deployed document because it is the one that sounds authoritative. **The measurement is what moved it**, and it moved before Run 4 rather than during it. | 0158 |

---

## 2. What Session 13 adds to the acceptance registry

`CURRENT_SESSION` moves to **13 in Run 7**, and the bump is **all-or-nothing**
(D690): `test_no_requirement_at_or_before_the_gate_session_remains_future` refuses
any requirement due by 13 that is still a placeholder. So every `REL-*`
requirement is written as a `future` placeholder in Runs 2–6 — permitted while
`target_session` 13 exceeds `gate_session` 12 — and **all of them stop being
placeholders in the commit that moves the constant.**

**A new family, `REL-*`.** The proposed set, each with a claim, and **each claim's
node ids chosen so `claim_mode` resolves to exactly one mode** (D721) — decided
here rather than discovered at merge time:

| Requirement | Guarantee | Live half |
|---|---|---|
| `REL-VER-001` | The installed platform version and migration state are machine-readable from a deployed project | `live_host` |
| `REL-COMPAT-001` | An incompatible manifest, capability or secret-format change is refused **before** any mutation | offline proofs + one `live_host` |
| `REL-PLAN-001` | A deployed project produces a complete upgrade plan **without changing its deployment** | `live_host` |
| `REL-CLI-001` | Every documented verb is reachable through one front door, and the front door adds no path a bare script did not have | offline + `live_host` |

**Exact node ids are settled in the run that writes each proof**, because
registering one is a decision about what the requirement means (D691) — and
because a claim whose members turn out to span two modes has to be split, which
is a decision about two guarantees rather than a rename (D721).

**Also here, in Run 6:** the thirteen claimable orphans are grouped into new
claims; `OPS-HEALTH-001` and `SEC-TLS-001` are split or left; `SEC-NET-001` stays
where Session 4 deliberately put it; and `UNCLAIMED_BY_HISTORY` drops **37 → 22**
with its docstring rewritten from *"never retrofitted"* to what D720 and D722
measured.

---

## 4. Irreversible operations

Four, each needing a human at a terminal or a commit that cannot be half-made.

**1. Moving `CURRENT_SESSION` to 13.** It arms every `REL-*` requirement at once
(D690) and it is the gate session, so `bin/session-13-check.sh` must exist and be
registered in the same commit (D726). **Reversible in a checkout, not on a host**:
`deploy.sh` refuses a `--through-session` above the constant (D59) and accepts
anything below it, so a host running a Session 13 release with the constant
reverted deploys Session 12 silently, exits 0, and looks fine.

**2. Bumping `VERSION` to `0.2.0`.** It changes `template_version` in every
document the next render writes — which is every document, since `.generated/` is
rewritten transactionally on every render. **If Run 1 finds the schema needs a
pattern, this and the `schema_version` bump land together**, because a document
carrying a new version under an old schema is the state neither validates.

**3. Installing a Session 13 release on the host.** `git bundle` + `scp` under a
per-release name (`/tmp/apg-<sha>.bundle`, D504) — the generic name collides with
bundles the *other* account left, `/tmp` is sticky, and a failed `scp` followed by
a successful `git fetch` of the stale file moves the host **backwards** with both
commands exiting 0. **Confirm `git rev-parse FETCH_HEAD` before the checkout, not
the `release` line after it.**

**4. Publishing a `schema_version` bump**, if D724's measurement calls for one.
`output_migrations.py` gains a v13 → v14 transition, and the module's own rule
applies: **it may not fabricate a value it cannot derive.** A migrator that
guessed would produce a file automation believes.

**The standing rules apply unchanged.** `sudo` needs a TTY, so anything
privileged that mutates is run by a human at a terminal; read-only diagnosis is
not — and **this session's host trip is read-only by decision**, which is the
first trip in this repository's history that can say so.

---

## 5. Build order

Runs are the unit. Each ends with the offline gate green on a clean tree, and
CLAUDE.md §5's procedure applies to every one: **measure third-party behaviour
with a control before writing anything that depends on it**, write the ADR when
the measurement decides something with alternatives, implement, then **try to
break the tests** with a mutation battery whose failures are fatal (D269), whose
control is a test the mutation cannot reach (D499), and which asserts *how* each
mutation failed (D386).

### Run 1 — Measure before designing — **Done.**

Two rigs in `/tmp`, each with a control that proves it can tell success from
failure.

- **D724**: does constraining `template_version` to semver reject any document
  that validates today, and does it need a `schema_version` bump?
- **D725**: what would an upgrade plan actually diff? Run the leaf walker over
  the document kinds and read what a diff between them would contain. **The
  question is not whether a diff is producible — it is which leaves differ for
  reasons that are not an upgrade.**

**Measured — four rows, D730–D733, and one of them moved the design.**

**D731 — the pattern is free, and half the question is unanswered.** Every
`template_version` in the tree is `0.1.0-dev`, which is valid semver with a
prerelease; the pattern causes **0 regressions**. The control discriminates: a
`banana` probe is accepted by the current schema and refused by the patched one.
**The live half was not measured and is not claimed** — none of `apg-diag`'s
eight verbs returns a deployed document, so reading the two live values needs the
operator. The inference from `VERSION` is strong and it is still an inference
(D267).

**D732/D733 — the plan was going to diff the wrong pair.** Rendered and deployed
share **41%** of their leaf vocabulary, six of seven routes are a *string* on one
side and an *object* on the other, and the deployed document has **no `inputs`
block** — so the five digests that answer *"did the inputs change"* exist only on
the rendered side. The diff is **rendered(installed) against rendered(candidate)**,
and `deployed_output.rendered_path(key)` is where the installed one already lives.

**D730 — and the documents this run was going to measure are six sessions
stale.** `alpha-outputs.json` and `beta-outputs.json` are tracked, `schema_version`
10, session 6, and they do not validate against the current schema. Nothing read
them; Run 8 deletes them.

**Retrospective.** The run's value was almost entirely D733, and it cost two rigs
and an afternoon to find. **The first design reached for the deployed document
because it is the one that sounds authoritative** — and ADR 0158 has said since
Session 11 that the deployed document is the address book, not the diagnosis. The
measurement moved the design *before* Run 4 rather than during it, which is the
whole reason this run exists. **Rig B's control is the part worth keeping**:
`routes.health` matches in both kinds while six others do not, so the 41% is a
fact about the schema and not an artefact of how the walker descends.

### Run 2 — D719: one authority for the session bound

Derive `write-session-evidence.py`'s bound from `CURRENT_SESSION`, and **widen
`test_gate_contract.py`'s existing no-hard-coded-session rule to cover the
writer** rather than adding a second guard next to it. Small, and every later run
that writes evidence is behind it.

**The battery's control is the guard itself**: with the derivation reverted, the
widened test must go red, and with the *scan* blinded it must go red too — a
guard that reads nothing reports every file clean forever (D694).

### Run 3 — The compatibility rules, and the ADR

**ADR 0162**, because it decides something with alternatives: which manifest,
platform-migration, application-migration, API-contract, capability and
secret-format changes each of **patch**, **minor** and **major** permits.

**Rollback boundaries are stated honestly and separately.** Configuration
rollback, image rollback and database fix-forward are **three different
operations**; a runbook that conflates them lies in the direction that costs
data. Migrations remain fix-forward only — every down block raises AP900 — so
"rollback" never means the database.

### Run 4 — `upgrade check | plan | verify`

`src/agentic_postgres/upgrade_plan.py`, pure, built **on** `preflight`'s
three-verdict model rather than beside it (D723): a plan must be able to say *"I
could not look"*. `bin/upgrade.sh` holds the subprocesses, `--json` for the
machine-readable half, and the exit-code convention.

**No mutation before a plan is produced and validated.** The offline half of
`REL-COMPAT-001` lands here: an incompatible manifest is refused **before** any
write, proved by asserting the refusal *and* that nothing was written — the
second half being the one that is easy to leave out.

**The diff is `rendered(installed)` against `rendered(candidate)`** — Run 1's
correction (D732, D733). `deployed_output.rendered_path(key)/outputs.json` is the
left-hand side and a fresh render is the right; both are the same document kind,
so the diff is between two intents rather than between two vocabularies. **The
deployed document is still read**, for `upgrade check`'s observation half — what
is *running* — which is ADR 0158's split and not a second opinion about the same
question.

The leaf walker moves out of the Session 12 test module (D725) and the
classification lists **stay where they are**: `MUST_DIFFER` / `MUST_MATCH` /
`RELEASE_STATE` are a judgement about two projects, and reusing them for two
releases of one project is D702's shape.

### Run 5 — `bin/apg.sh`, the thin dispatcher

`apg <verb>` execs the existing script, unchanged. **No file moves, no renames, no
rewrites.** Registered in `SHELL_COMMANDS` (D726), and written so
`test_no_command_defines_anything_after_its_entry_point` passes — which for a
dispatcher means the verb table and its functions are defined **above** the entry
point, not below the `case` that calls them (D185).

The install-onto-`PATH` question is decided here: a symlink from the release, or
nothing and `bin/apg.sh` is the spelling. **Whichever, it is derived from the
release rather than typed** — `libexec/` is the precedent.

### Run 6 — The claim register, read before it is edited

**Read `evidence_claims.py`'s commentary first** (D722). Then: group the thirteen
straightforward orphans into **new** claims — never into existing ones (D728);
decide `OPS-HEALTH-001` and `SEC-TLS-001`, splitting where the measurement is
(D721, ADR 0045's precedent); leave `SEC-NET-001` where Session 4 put it; and
rewrite `UNCLAIMED_BY_HISTORY`'s docstring around what was measured.

**Then correct `docs/scope-closure.md` §4** — both its effort estimate (D720) and
its recommendation of a guard that already exists (D727).

**For each new claim, check `claim_mode` and `claims_through_session` before
writing it**, not after: a claim dated Session 2 is one Session 2's gate must
report, and `merge` refuses a document silent about a claim.

### Run 7 — The bump

`CURRENT_SESSION` 13, `VERSION` 0.2.0, every `REL-*` placeholder activated, and
`bin/session-13-check.sh` **derived by diff** from Session 12's — registered in
`SHELL_COMMANDS`, and **its printed prose read line by line**. D505, D507, D678,
D693 and D703 are five instances of one loss; D703's half — *the prose a gate says
out loud* — is still unguarded, and Session 12's external mode printed *"Session
10 also needs `--mode external`"* at the end of the run that produced its
evidence.

`pytest -m future` goes back to selecting something, so D695's branch flips: the
assertion already handles both sides and this run confirms it does.

### Run 8 — Housekeeping

Remove `&1`. Refresh CLAUDE.md §2's status block. Diarise the PGDG apt pin
(D533) — `pgbackrest=2.59.1-1.pgdg12+1` will one day resolve to nothing and the
image build will fail closed, which is the accepted half of a pin with an end
date nobody has written down.

### Runs 9+ — The host trip, read-only

Install the release, then **per project**: `upgrade check`, `upgrade plan`, and
**verify the deployment is unchanged** — the deployed document, the container set
and the release path all read after the plan and compared to before it. *A plan
that mutated nothing is the claim*, so it is asserted rather than assumed.

**Expect more than one round.** Sessions 7 and 8 found seven and eight defects on
theirs, and Session 9's trip found three never-executed proofs, every one
defective. **Run `pytest --setup-plan` before going** — it costs seconds and it
has caught four wrong fixture assumptions and one fatal one green since Session 5
(D671, D676).

---

## 7. Evidence and claims — what may honestly be reported

Fixed **before** the proofs are written, which is what §7 is for.

- **`REL-PLAN-001` may be reported only from the host half.** Its guarantee is
  that a *deployed* project produces a plan without changing itself; there is no
  deployment in a checkout, and an offline proof of the same command measures the
  command, not the guarantee.
- **`REL-COMPAT-001`'s refusal is proved offline, and is named as offline.** The
  second exit criterion — an incompatible change fails before mutation — is a
  property of the validator. Its live half is narrower: that the validator the
  host runs is this one. **A session that half-closes a requirement without saying
  so leaves the next reader unable to tell a proved guarantee from a plausible
  one** (D478).
- **`REL-CLI-001` spans two modes if written carelessly**, which `claim_mode`
  refuses (D721). Decide the split when the node ids are written.
- **The thirteen retrofitted claims report on old guarantees, not new ones.** Their
  `claim_session` is 1–4, so they belong to those sessions' evidence and Session
  13's gate reports them cumulatively — it does not *introduce* them (D728).

Unchanged and not renegotiated: a claim's verdict is computed from the registry's
node ids and JUnit results, **never hand-entered**; a skip is not a pass; a
filtered run writes nothing; both halves must describe the same release or the
merge refuses; `evidence/*` is gitignored and the host half lives on the host.

**Exit 5 remains the expected shape** of a run whose evidence was written and one
of whose claims is not `passed` (D686) — not a suite failure.

---

## 8. Security invariants this session touches

| Invariant | Control | Where this session puts it at risk |
|---|---|---|
| An identity is derived once, in the component that owns it | ADR 0002 | **D719 is this rule broken at the release layer.** Run 2 |
| `--render-only` works with no host and no root | The render path takes neither | `upgrade plan` must not become a second renderer that needs one |
| A plan changes nothing | Step 0's position above every write | Run 4, and asserted on the host in Runs 9+ rather than assumed |
| No secret enters a log, an argument or a document | The canary scan and the secret-argument test | `upgrade plan --json` is a **new machine-readable output** and a new place a generation path or a credential could surface |
| A command adds no path a bare script did not have | The dispatcher execs; it does not re-implement | Run 5. `apg` must not gain a privilege escalation `bin/*.sh` lacks |
| A passing test is not weakened | §6, and an ADR where one is replaced | **D725**: moving the leaf-walker out of a green Session 12 proof |
| A deployed document reader reads only keys the schema has | `test_no_operator_command_reads_a_key_the_deployed_document_does_not_have` | `upgrade_plan.py` is a new reader of that document (D600) |

---

## 9. Risks and stop conditions

**Stop and ask** rather than proceeding, when:

- the compatibility rules would need a **second answer to *"what is deployed"*** —
  that is D704's failure and the reason this session exists;
- `upgrade plan` cannot be made to mutate nothing, or can only prove it by
  inspection rather than by assertion;
- moving the leaf-walker would **weaken** the Session 12 matrix rather than leave
  it identical or stricter (D725);
- a `REL-*` claim turns out to span two modes or to have no live proof after its
  node ids are written — **split the guarantee, do not widen the claim** (D721);
- retrofitting an orphan would move an existing claim's session (D728);
- the dispatcher needs a `case` branch that does something other than exec;
- a Session 1–12 claim goes red and the tidy fix is on the proof's side.

**The failure mode this session is most exposed to** is not Stage 1's *value that
looked measured and was not*. It is the Stage 2 shape the stage plan named:
**re-implementing something that already exists, one layer over, because a
specification described it and nobody checked.** D719, D720, D722, D723 and D727
are five instances caught at plan time — and **D722 and D727 are instances of it
committed by the planning itself**, one document apart. The ones caught at run
time will look like progress.

**The six standing questions apply.** Two are unusually live here:

- **Question 2 — *has anything looked at this since it changed?*** D719's bound was
  right for twelve sessions. D722's three decisions were written down and unread.
- **Question 5 — *when a decision is implemented, which of its callers got it?***
  `test_gate_contract` got the no-hard-coded-session rule; the evidence writer did
  not. **This session moves the session number, so every reader of it is a
  candidate**, and `grep` is the tool.

---

## Appendix — what to consult, and what to measure instead

**Consult:** `docs/plans/stage-2-plan.md` §1 and §3 — this session's scope and why
it is not twelve. `src/agentic_postgres/evidence_claims.py`'s commentary **above**
the `CLAIMS` dict, which is where Sessions 3 and 4 wrote down why certain
requirements are not claims (D722 is the cost of not reading it). ADR **0157**
(three verdicts, and why two is a lie), **0045/0089** (what a claim is, and why
its session is load-bearing), **0039** (why cumulative means a later session keeps
proving an earlier one's guarantees), **0002** (derive once), **0012/0027** (the
outputs schema and its migrator). `docs/plans/session-09-implementation-plan.md`
for what a run's retrospective half looks like.

**Measure instead of consulting:** whether the live documents satisfy a pattern
the checkout does; what a leaf diff of two releases of one project actually
contains; whether a new command's `--help` exits zero; and **whether a proof has
ever run** — `pytest --setup-plan`, before the trip.

**Before measuring how a third party behaves, `grep` the plans for it.** Nothing
indexes the ~729 measured facts in the divergence tables by subject.

**Never write a measurement you did not run** (D267).
