# Session 12 — reuse proof and release candidate

**Deliberately short.** Sessions 10 and 11 ran to ~1,740 and ~1,300 lines because
they built planes. Session 12 builds almost nothing: three of its four
requirements already have working machinery and are missing a *witness*, and the
fourth is written. What earns a plan here is §1 and §7 — what has been measured
that the session summary does not say, and **what each claim may honestly report
before its live half exists.** Everything else is support.

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

**Next free number after this table is D693.**

| # | Summary says | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D689** | The session summary: *"Complete the explicit two-project isolation matrix, distinguishing shared provider accounts from forbidden shared project state."* Read as new work across the board. | **The forbidden half is already proved and the permitted half exists nowhere.** Seven claims — `database_isolation`, `api_isolation`, `project_isolation`, `transport_isolation`, `storage_isolation`, `restore_isolation`, `isolation` — assert that specific pairs of values differ, and all seven passed in Session 11's merged evidence over the live pair. **None of them says what is ALLOWED to be the same**, so none can tell a correctly isolated pair from two documents the test failed to read. | **The matrix is built around the distinction the summary names**, in `tests/deployment/test_session12_isolation_matrix.py`: `MUST_DIFFER` (project scope), `MUST_MATCH` (**the control** — one machine, one router), `NOT_AUTHORITY` (carries no authority either way). `test_every_leaf_is_classified` makes a field a later session adds redden until somebody classifies it. | Dry-run against both live deployed documents: **179 leaves, 0 unclassified, 0 project-scoped values shared, 0 rules guarding a field that does not exist.** The claim holds; what was missing was a proof that could have detected it not holding. | — |
| **D690** | This plan's own first attempt: bump `CURRENT_SESSION` to 12 so `DEP-ISO-001`'s node ids may be registered. | **The bump activates all four Session 12 requirements, not one.** `test_no_requirement_at_or_before_the_gate_session_remains_future` refuses any requirement whose `target_session` is at or below the gate session while it is still a placeholder. So `DEP-001`, `DEP-REMOVE-001` and `DX-001` must stop being placeholders in the same commit that moves the number. | **All four are activated together**, each with a **proved offline half** and a **live half gated on a declared operator event** — the `APG_AFTER_REBOOT` / `APG_ROTATED_*_FROM_FILE` pattern, which exists for exactly this: a proof of something that *happened* rather than of a state that holds. | The bump was reverted rather than pushed through, because how the other three are activated is a decision about **what those requirements mean**, not a mechanical consequence of a constant. D672 recorded the same constant being load-bearing in the other direction; this is its cost on the way out. | — |
| **D691** | `DEP-REMOVE-001`: *"Removing one project does not affect another."* Read as a claim about a removal command. | **No shipped command removes a project.** `project-runtime.sh down` stops containers and **preserves volumes deliberately** — *"removing it here would make `systemctl restart` a data-loss command"* — and `compose.sh` **refuses `--volumes` in project mode** outright: *"it would destroy the database volume."* What exists is a two-command surface: `down` (runtime) and `bootstrap-providers.sh --destroy --confirm KEY` (provider resources, by recorded ID). | **The requirement is proved against the removal surface that exists**, and the absence is recorded rather than filled: this session does not add a destroy-the-data verb. The offline half asserts every removal path is **scoped by derivation** — it can only name resources derived from its own project key — and that `--destroy` refuses without a matching `--confirm`. | **The requirement's premise had not been checked.** Written as though a removal command existed, it would have produced either a test of nothing or a new destructive verb nobody asked for. This is D683 and D688's shape a third time: **a requirement whose subject had not been measured**, and the measurement takes one `grep`. CLAUDE.md §9 already warns that destroying `pgbackrest_repo_cipher_pass` orphans every backup — a data-removal verb is a decision with consequences, not a convenience. | — |
| **D692** | This plan's Run 2: `DEP-REMOVE-001`'s offline half asserts that every removal path is scoped by derivation and that `--destroy` refuses without a matching `--confirm`. Read as four new tests. | **Three of the four already exist**, in `tests/contract/test_bootstrap_state.py`: `test_state_paths_are_project_scoped`, `test_state_may_not_name_another_projects_credential_directory` (*"would make one project authenticate as another"*) and `test_a_managed_client_secret_without_an_id_is_rejected` (*"falling back to a name lookup is how one project deletes another's"*). Writing them again would be a second, weaker claim about one property. **And the confirmation refusal is unreachable in a checkout**: measured, `bootstrap-providers.sh --destroy` answers exit **3** (*requires root*) before it ever reads `--confirm`, so a behavioural test of it would pass on the root check while believing it measured a confirmation. | **The registry points at the three that exist**, and the one genuine gap is closed: `test_project_mode_refuses_volume_removal`. Edge mode had a refusal test since Session 2; **project mode — the one holding customer data — had none.** | **The argument order is load-bearing and was measured, not assumed.** `--runtime` triggers its root check the moment it is parsed, so `--runtime down --volumes` answers exit 3 unprivileged and never reaches the refusal; `--volumes --runtime down` reaches it at exit 2. A privileged caller reaches it in any order, which is the case that matters. **The battery's arm B is that ordering**, and it fails — so a test written the natural way cannot quietly pass on the wrong exit code. The rig that established this produced a **false control** first (`--edge down --volumes` returned exit 2 for a missing `--host`, not the refusal), which is D509 inside the measurement of D692. | — |

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

`DX-001` offline: every command the documented path names exists and resolves,
no step requires editing a source file, and the path stays within the
specification's own **fewer than 15 operator steps**. `DEP-001` offline was
already proved in Session 11 and is re-pointed rather than rewritten.

### Run 4 — the bump, the registry, the gate

`CURRENT_SESSION = 12`, four requirements activated, placeholders removed,
`bin/session-12-check.sh` derived **by diff** (D505, D507, D678), evidence
merged, session closed.

### Run 5 — scope closure

The specification's own final activity: resolve P0 failures, list remaining
P1/P2 gaps **with evidence and estimated effort**, document every hidden
dependency. Two P2 items are unbuilt and droppable by the specification's own
rule — the pgvector example and search RPC (the extension is present and proved;
the example is not) and the portable `pg_dump` export.

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
