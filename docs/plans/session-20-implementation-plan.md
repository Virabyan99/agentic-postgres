# Session 20 — The tenant extension point

**Status:** planned 2026-09-10 at `95ea0be`, the commit that carries the Stage 3
plan of record. Not started.
**Brief:** `docs/plans/stage-3-plan.md` §5 *Session 20*, and its rows D1082
(the extension point, measured from four sides), D1067 (`apg migrate dev` is
absorbed here), D1080 (`documented_path`'s cause), D1083 (ADR 0196's migration
lands in this session's deploy sitting), D1086 (the stale removal paragraphs).
**Shape:** seven runs. Runs 1–6 are offline and green in CI on a `session-20`
branch; Run 7 is a host trip that ends with the branch merged to `main`.
**Product version at close:** `CURRENT_SESSION` 20; `template_version` as
`upgrade plan` prices it, proposed `1.1.0` (D1081).
**Written for whoever picks this up cold.** Every path is exact, every third
party the session touches is measured in Run 1 before anything is built on
it, and the appendix says how a run is executed in this repository — read
`CLAUDE.md` §1 in the launch folder before the first command.

---

## 0. Where the session starts

Stage 2 closed at 1.0.0; Session 19 repaired an adopter's nineteen findings and
tagged 1.0.1 on `b8bab01`; the Stage 3 plan was committed at `95ea0be` on
2026-09-10 with six sessions, 20–25, on PostgreSQL 18.4. **Session 20 is
first because every later session builds for a surface, and today the
surface is the product's example domain** (`notes`, `tasks`, the contract
named `notes-tasks-v1`). An application built on this appliance adds its
tables by forking the product and editing seven tracked files, one of which
cannot be edited without a running host (ADR 0197). That is why
`documented_path` is `not_run` with the answer *no*, and it is what this
session removes.

**What is deployed**: host `62.238.99.122`, checkout `b8bab01`, release
`054f54e` on `alpha-dev` and `beta-dev`, both manifests at project schema 1,
outputs v16 in the tree and v15 published (the host publishes v16 only after
this trip), 30 migrations applied on both clusters, doctor 10/10, backups and
the B2 mirror current. `.generated/alpha-dev` is op-owned again since
2026-09-10; the first root deploy of this trip makes it root-owned again,
which is the live site of D1060.

**What this session builds, in one paragraph.** A project's own migration set
beside the release's — declared in the project manifest (schema 5), living in
the release checkout under `projects/<slug>/`, rendered through the same
`{{name}}` substitution, frozen under its own lock, applied after the release's
set by the same dbmate plane as the same `migration_user`, and digested into
the deployed document (outputs v17). A lint over what such a set may contain.
A project's own reviewed surface and OpenAPI snapshot beside its set, so the
release's contract, its control fixture and its two hand-written test sets are
never edited by an adopter again. The reviewed `api.create_task` ADR 0196
specified (migration 0031), in this session's deploy sitting. Two readers made
honest: `migrate.sh render` distinguishing *unreadable* from *absent* (D1060),
and `routes.*.status` gaining `unobserved` (D1048). The README and ledger
paragraphs that describe `project_removal` as open, corrected (D1086).

**The premises were checked against the tree before this plan was costed**,
and two of the Stage 3 plan's own sentences turned out to be wrong in the
reassuring direction (D1087, D1089). §1 has the rows. The largest finding is
that `src/agentic_postgres/migrations.py` is already parameterised by root and
path — every function takes one — and the hardcoding the adopter hit lives in
its **eleven callers**, all of which use the default. The extension point is
a change to callers, not to the module.

**Read before touching anything**: ADR 0028 (templates, the rendered payload
as the immutable unit, what the lock records), ADR 0050 (the reviewed surface
is hand-written and the gate cannot approve its own subject), ADR 0195 (a
report may not substitute an answer for a failure to determine one), ADR 0196
(the task domain, and the migration this session writes), ADR 0197 (what
`documented_path` now means), D1036–D1040 and D1053–D1055 in
`docs/plans/session-19-implementation-plan.md` §1, and `FINDINGS.md` F-002,
F-004 to F-008 and F-021 to F-023 in the launch folder.

---

## 1. The divergence table

Six columns, next free number after this table **D1119**. Rows D1087–D1097
were measured at planning on 2026-09-10 at `95ea0be`; the runs add theirs
below them as they go.

| # | Said | Repository does | This session | Why | ADR |
|---|---|---|---|---|---|
| **D1087** | Stage 3 plan §5: the project's set lives *"outside the release's `migrations/templates/` — on the host beside the manifest, where D971 already puts a third project's manifest."* | **A release is exactly the commit it is named for**: `installed_release.assert_clean` refuses a dirty checkout, the deploy runs `release/bin/migrate.sh` from the checked-out release, the lock is what `verify_lock` compares, and `upgrade plan` diffs two rendered releases (D732). SQL living beside a manifest on the host would be applied by a release that does not contain it — a schema no commit determines, which `assert_clean` exists to refuse. D971's manifest is *configuration* (a domain, a bucket); a migration is *code*. | **The set lives in the release checkout, tracked, under `projects/<slug>/`** — `migrations/manifest.json`, `migrations/templates/NNNN-*.sql`, `migrations/released.lock.json`, `contracts/postgrest-api-surface.yaml`, `contracts/postgrest-openapi.canonical.json`. The project manifest names it by a repo-relative path the schema constrains to that shape. An adopter's fork commits their directory; the product's own files are untouched. | The property the product argues for throughout is that a deploy is a reviewed commit; the adopter's account (F-008) agreed: *"a fork is a reviewable diff … which is the property the product is arguing for and gets."* What made the fork expensive was *which* files it had to edit, not that it was a fork. | 0198 |
| **D1088** | Stage 3 plan D1082, README §*Adding your own tables*: *"`migrations.load_manifest()` reads one hardcoded path."* | **The module is already parameterised.** `load_manifest(path=MANIFEST_PATH)`, `render_migration(..., root=MIGRATIONS_ROOT)`, `build_lock(manifest, root)`, `verify_lock(manifest, lock, root)`, `load_lock(path=LOCK_PATH)`. The default is what is hardcoded, and **eleven callers use it**: `bin/migrate.py` (five sites: `render_set`, `record_ledger`, `freeze-lock`, `verify-lock`, `main`), `rendering.write_rendered_migrations`, `bin/doctor.py:358`, `bin/session-09-check.sh` (two sites), `test_migrations_apply_as_the_migration_user.py:189`, and the four contract fixtures that mirror it (`test_storage_plane`, `test_auth_service_reaches_its_data`, `test_storage_service_reaches_its_data`, `test_agent_audit_plane`, `test_auth_endpoints`). `test_rendered_migrations.py` and `test_database_row_request_id.py` read the release manifest and mean to. | **A `MigrationSet` value (root, label) and `sets_for(document)`** in `migrations.py`, returning the release set and, when the rendered document names one, the project set. Every caller above that means *every migration this project applies* switches to `sets_for`; every caller that means *the release's migrations* keeps the default and says so in a comment. Run 2 lists each one. | Question 5 of the defect pattern: a definition with eleven readers. The README's sentence is true of the callers and false of the module, and a session that rewrote the module to add a parameter it already has would have left the eleven readers where they are. | 0198 |
| **D1089** | Stage 3 plan §5 Session 20: *"the anti-vacuity guard rewritten as 'the reader found the platform's objects and the sets are non-empty' (F-006, D1038)"*. | **With the project's set separate, the release's reader never sees a project object**: `test_api_migrations.final_surface` walks `migrations.load_manifest()["migrations"]` — the release set — and its equality against `{"notes","tasks"}` holds for every adopter, because an adopter's views are in `projects/<slug>/`. The rewrite F-006 proposed was needed only while a tenant's views were in the release set. **Loosening the equality to containment is what the non-negotiables call weakening**, and it is now unnecessary. | **The guard is not rewritten.** `test_the_reader_is_not_vacuous` keeps its equality, gaining `create_task` for 0031 (Run 5, under ADR 0196). The *reader* becomes a module (`sql_surface.py`) so the same interpreter runs over a project's set against the project's own contract, with its own anti-vacuity assertion: *non-empty, and every object the project contract names* (Run 3). D1038 closes by construction. | A stronger test that stays is better than a weaker one that accommodates. The stage plan priced a shape change here and the design removes the need for it; recording that is cheaper than making it. | 0050 |
| **D1090** | Stage 3 plan §5: *"the control fixture generated from the reviewed contract rather than captured from a deployment (D1054)"*. | **The captured control is a real PostgREST document and it stays valid for the same reason as D1089**: the release contract no longer gains a project's objects, so the capture from `alpha.example.test` cannot drift from it. A fixture *generated* from the contract would agree with the contract by construction — question 6's shape, a fixture sharing the code's belief — and could never have caught D1036 (a view the reader could not see). **It must be recaptured exactly once in this session**, because 0031 adds `rpc/create_task` to the release surface; Session 5 Run 9 captured it *"independently from `.generated/fixture-alpha-dev/migrations/` on a throwaway cluster"*, and Run 1's rig repeats that route. | **Captures stay captures.** The release's control is recaptured in Run 1 from a throwaway cluster serving 31 migrations; a project's snapshot lives with its set and is captured from that project's deployment. `test_the_contract_is_project_neutral` keeps asserting the release contract names no project's slug or domain, and the project contract is *allowed* to. D1054 closes by separation, not by generation. | The contract's header sentence — *"project-neutral, because the domain is"* — becomes true again once the domain a project adds is the project's file. | 0050 |
| **D1091** | `DX-001`: *"completes the documented path without source edits or undocumented commands"*; ADR 0197: the run required seven tracked-file edits and so the claim is *no*. | **After this session an adopter adds files** — a directory under `projects/<slug>/` and a key in their gitignored manifest — **and edits none** of the release's: not `migrations/manifest.json`, not `released.lock.json`, not `contracts/postgrest-api-surface.yaml`, not the two test modules, not the release snapshot. Whether adding one's own files to a fork is a *source edit* is a reading of the requirement's text that nobody has written down. | **ADR 0198 states it**: a source edit is a change to a file the release tracks and the project does not own; authoring under `projects/<slug>/` is writing the application, which the requirement cannot forbid without forbidding the product's purpose. **The claim still does not move here** — Session 25's second walk by somebody who did not build this is the proof (Stage 3 plan §4), and Run 7's rehearsal of it by a fresh agent context is a *reading*, not a declaration. | A definition that the walker and the reviewer both read before the walk is what makes the walk's record comparable with ADR 0197's count of seven. Without it, a second run could report zero by calling every edit "authoring". | 0198 |
| **D1092** | ADR 0028 and `migrate.sh`: one manifest, one directory, applied *"in order, transactionally"*, `--strict`. | **dbmate is handed one directory and orders by filename; the release's newest version is `20260904120030`.** Two sets in one directory interleave by version stamp, and a project migration written before a later release migration sorts before it on a fresh cluster and after it on a cluster where the release's arrived first. What `--strict` does with a *pending* migration whose version is older than an *applied* one is **unmeasured** in this tree (test_image_contracts measures flag positions, not this). | **Run 1 measures it with a control** (rig 20a). Whatever it says, the rule is: a project set's versions must be later than the release lock's newest version at the time the project lock is frozen, recorded in the project lock as `follows_release_version`, and refused by `verify_lock` otherwise; a release migration is always authored later than any project migration a deployed cluster holds, so the order on every cluster is the order on a fresh one. | A rule written from dbmate's documentation is D267's shape; the rig's arm B (an older pending version behind an applied newer one) is the one that decides whether the rule is a convention or a refusal. | 0198 |
| **D1093** | `docs/plans/stage-3-plan.md` §5: the session *"ends in a deploy sitting"*; ADR 0196: the migration, the contract entry, the re-frozen lock and the recaptured snapshot *"belong to one sitting that ends in a deploy"*. | **The sitting is circular unless CI runs on a branch.** `test_the_published_set_is_exactly_what_the_snapshot_names` and four tests in `test_api_contract_command.py` compare the committed snapshot with the reviewed contract; the snapshot is captured from a deployed document (`api-contract.sh --update` reads `routes.rest.url`); the deploy needs the release checked out, and the host takes a release by bundle from a commit. So the commit carrying 0031 and its contract entry is **red on five tests by construction** until the deploy that lets it be recaptured (D1039's *unsatisfiable, not unsatisfied*). D1057 made branch pushes run CI. | **Runs 1–6 land on a `session-20` branch.** The bump commit is pushed red on exactly those five tests and green on everything else (the run records the five names); the host takes the branch's commit; the deploy applies 0031; both snapshots are captured; the snapshot commit is pushed to the branch; CI is green; the branch is merged to `main` fast-forward. A red CI run on that branch with any *other* failure is a stop condition. | The repository's rule is *push and read that commit's verdict*, and this is the one session where the verdict is known in advance to be red on a named set. Writing the set down is what keeps "expected red" from becoming "ignored red". | 0196 |
| **D1094** | Stage 3 plan D1048: a third `routes.*.status` member is *"an outputs version with a migrator and a guarded reader for every consumer (D600)"*. | **A migrator cannot know which recorded `unavailable` meant unobserved.** A v16 document says `unavailable` for a route the deploy did not observe (D326's first-deploy race, D1047's staging certificate) and for a route it observed failing, with nothing in the document to tell them apart. Readers of the status outside the deploy: `diagnosis.py` (the doctor), `fleet.py` through the doctor's JSON, `bin/api-contract.py published_address` (reads the URL), `test_session14_observability.py:214` (`in {"ready","unavailable"}`), and `deployed_output.py:287`'s validation. | **`migrate_v16_to_v17` leaves every route's word as recorded** and adds the `migrations` block; only a v17 *deploy* writes `unobserved`, and only where the observation was not made — never where D230 or D326 recorded a determinate *not published*. Every reader above is taught the third word in Run 4, with the widening in `test_session14_observability` recorded as an allowlist widened to a measured set. | ADR 0195 applied to the migrator itself: guessing which `unavailable` was which would be a report substituting an answer for a failure to determine one, written into a document that outlives the guess. | 0199 |
| **D1095** | `docs/api-surface.md` line 8 links ADR 0050 as `decisions/0050-the-published-surface-is-a-reviewed-allowlist.md`. | **No such file.** The ADR is `0050-a-reviewed-api-surface-is-a-generated-artifact.md` and the index names it so. `test_repository_contract.py` tracks `docs/api-surface.md` for existence and not for its links, so the dead link has survived since Session 5. | Corrected in Run 5 beside D1086. | Housekeeping, and the second stale sentence this planning found in a document the gate tracks (D1086 is the first). Nothing reads a link. | — |
| **D1096** | `bin/migrate.py record_ledger`: `templates = {entry["version"]: entry for entry in migrations.build_lock(manifest)["migrations"]}` then `templates[entry["version"]]` for every rendered entry. | **A project migration's version is absent from the release lock, so the ledger write raises `KeyError` on the first deploy that renders one** — after dbmate has applied it, which leaves a cluster with an applied migration and no ledger row, exit 5 (`the ledger could not be recorded` is not even reached; the exception is unhandled). `app_private.migration_ledger` has `version, name, template_sha256, rendered_sha256` and no column saying which set a row came from. | **`record_ledger` builds its template digests from every set's lock** (`sets_for`, D1088) and records project rows in the same table; the set is recoverable from the version's presence in one lock or the other, so **no column is added** and no platform migration is spent on the ledger. Run 2, with a proof that renders a project set and records its ledger against a recorded `psql`. | Found by reading the reader before changing the writer (D979). A KeyError after dbmate returned is the worst order a failure can arrive in here: the cluster has moved and the record has not. | 0198 |
| **D1097** | `bin/api.sh`: three enumerated operations (`list-notes`, `create-note`, `update-task-status`); the host gates drive the surface through it. | **The live half of `API-TASK-001` needs a fourth**: `create-task --title T [--note-id U]`, so the trip can create a task through the product's own enumerated door rather than a hand-written `curl`. Adding a verb touches `test_cli_contract` (D1014) and `bin/api.py`'s `OPERATIONS`, and `update-task-status` finally has a row to act on. | Run 5 adds the operation; the targeted list names `test_cli_contract` and `test_api_command`. | The one operation the adopter could not perform (F-023's checklist item, *"a CAS conflict"*) becomes performable with the product's own tool, and the round trip against a real row is measured for the first time. | 0196 |
| **D1098** | This plan D1092: what `--strict` does with a *pending* migration whose version is older than an *applied* one is **unmeasured** in this tree, and the rule it states might be *"a refusal the tree needs to write or one dbmate already makes"*. | **dbmate already makes it, loudly.** Rig 20a, on the pinned `amacneil/dbmate:2.34.1` against the pinned cluster, four arms in one throwaway cluster. Arm A (`20260904120030` applied, then `20260903000000` added as pending): **exit 2, nothing applied** -- *"migration `20260903000000` is out of order with already applied migrations, the version number has to be higher than the applied migration `20260904120030` in --strict mode"*. Arm B (a NEWER pending version): applied, exit 0. Arm C (both files, **fresh** database): both applied in filename order, exit 0 -- so the fresh-cluster / deployed-cluster divergence D1092 predicted is real, and it is arm C that applies what arm A refuses. Control (one file alone): applied, exit 0. | **D1092's rule stands and its place is now settled.** `follows_release_version` in the project lock, refused by `verify_lock`, is a **freeze-time** refusal standing in front of a **deploy-time** one that already exists. It is kept for the reason every refusal here is moved earlier: dbmate's arrives after the cluster has been reached, on a host, during a deploy, with a human waiting; `verify_lock`'s arrives on a workstation before anything is rendered. Neither replaces the other, and the deploy-time one is the backstop that makes the freeze-time one safe to be wrong about. **Not a stop condition** (§9): the refusal is neither silent nor unstateable. | A rule written from dbmate's documentation is D267's shape. Arm B and arm C are what make arm A readable: without them, "it refused" could have been a broken directory mount rather than the ordering check. | 0198 |
| **D1099** | `bin/migrate.sh status` is the read-only verb the operator guides tell a human to run before `up` -- *"read-only, look first"* (Session 8 guide §4). | **`dbmate status` exits 0 with an out-of-order pending migration and reports it as an ordinary `Pending: 1`.** Measured in rig 20a immediately after arm A's refusal: the listing reads `[ ] 20260903000000_y.sql` / `[X] 20260904120030_x.sql`, `Applied: 1`, `Pending: 1`, exit 0. The condition that will refuse the very next `up` is nowhere in the verb an operator reads first. | **Recorded, not repaired.** The doctor does not read this verb -- `probe_migrations` counts `app_private.migration_ledger` against the release manifest -- so nothing automated is misled. The `follows_release_version` check is the repair from the other end: it refuses at freeze, so the state `status` cannot see is one an adopter cannot reach through the product's own verbs. | The state is in a field, never in the exit code -- `postgrest --ready` and `pgbackrest info` again (D145, D548), and D506 exactly: a `--runtime status` reading `Applied: 18, Pending: 0` was a green line for work that had not happened. Third-party, so ADR 0195's rule cannot be applied to it; the honest move is to know it. | 0198 |
| **D1100** | ADR 0196, from rig 19: *"no role that any service connects as can create a task, on any surface this product publishes"* -- the sentence the decision to restore is argued from. | **True, but not for the reason given.** Rig 20b applied the draft 0031 to a 30-migration cluster as `migration_user` over TCP (D285's route) and then measured the same question with a control arm carrying **no** 0031. In that control, `app_runtime` **successfully creates a note** through `api.create_note` -- `has_function_privilege` true -- on a cluster that is exactly 1.0.1. The cause is `pg_auth_members`: `app_runtime IS A MEMBER OF authenticated (inherit=true)`, established deliberately by `postgres-bootstrap.py` with `WITH ADMIN FALSE, INHERIT TRUE, SET FALSE` and three paragraphs of reasoning. So rig 19 measured the **table** (INSERT on `app.tasks`, `object_owner` only) and read it as a statement about **every surface**. What made a task uncreatable was the absence of the FUNCTION, not the absence of a role that could call one. | **ADR 0196's decision is unchanged and its sentence is narrowed here rather than in the released ADR.** Nothing is wrong with the deployment: `app_runtime` is *meant* to hold the application user's rights. Migration 0031's manifest description states the measured version. | A premise wrong in the reassuring direction survives longest (D930, D957) -- and this one was reassuring in the direction of *doing the work*, which is the harder kind to catch, because the conclusion it supports is correct. It matters because the sentence was about to become a test: see D1101. | 0196 |
| **D1101** | This plan §5 Run 1, rig 20b: *"`has_function_privilege` for every role in `naming.ROLE_SUFFIXES`, expecting `authenticated` and `agent_writer` only"*, and §2's node id `test_create_task_is_reachable_by_the_two_writer_roles_and_no_other`. | **That expectation is unsatisfiable by any correct deployment.** Measured over all fourteen roles: `has_function_privilege` answers **true** for `authenticated` and `agent_writer` (the grant), for `object_owner` (it owns the function), for `api_documentation` (0009's rule -- and without it the snapshot never publishes the function at all, F-007), and for `app_runtime` (inherited, D1100). It answers false for the other nine and for `PUBLIC`. The **direct ACL** is exactly the four the migration names: `proacl` reads `object_owner=X`, `authenticated=X`, `agent_writer=X`, `api_documentation=X`. | **The proof reads `proacl`, not `has_function_privilege`**, and its docstring says why. The behavioural half is separate and reads SQLSTATEs: `PT401` with no identity, `PT404` for a note absent AND for another owner's, `42501` for `anon` and `agent_reader`, a row for `authenticated` and `agent_writer`. Run 5's node id is renamed accordingly. | **Exactly D266's mistake, one catalog over**: that control first read `pg_roles.rolinherit` and failed against a *correct* rig, because the option lives on the membership row. A test asserting "the two writer roles and no other" through a function that follows inheritance and ownership would have been red on every green deployment -- written from the plan, in Run 5, with no rig to contradict it. This is what Run 1 is for. | 0196 |
| **D1102** | This plan §5 Run 1: **Commit** *"the recaptured fixture only if its diff is exactly `rpc/create_task`"*, with **Targeted:** *"nothing changes but documents"*; and §5 Run 5: *"the control fixture was recaptured in Run 1, so `test_api_contract_command`'s control tests are green"*. | **The diff is exactly `rpc/create_task` -- and the fixture cannot be committed alone.** Rig 20c's ARM A (30 migrations, no 0031) reproduces the committed fixture **byte for byte**, which is what makes ARM B readable at all; ARM B differs in one top-level key (`paths`), adds `/rpc/create_task`, removes nothing, changes no path body and no definition. But `tests/contract/test_openapi_normalize.py` asserts the fixture's path set against a **hardcoded literal**, so landing the recapture on its own turns four tests red -- in a run whose targeted list is "nothing but documents". | **The recaptured bytes are carried to Run 5** and committed with 0031, the manifest entry, the contract entry and the eight enumeration updates, so the expected-red set is created exactly once, deliberately, where D1093 says it is. The bytes and every rig live at `~/rig20/` in WSL (`rig20c-arm-b-raw.json`); ARM A is the control that says a regeneration is the same document. Run 1 commits the two ADRs, the index and this table. | D1093's discipline is that writing the set down is what keeps *expected red* from becoming *ignored red*. A run that reddens four tests as a side effect of a documents-only commit is that discipline leaking on the first run of the session. | 0198 |
| **D1103** | This plan D1093: the bump commit is *"EXPECTED RED on exactly five snapshot tests"*, and Run 5 *"list their five node ids in the commit message"*. | **Eleven, and only three of them are the snapshot's.** The full Run 5 state was built and measured rather than predicted -- 0031 in `migrations/templates/` and the manifest, `freeze-lock` re-frozen to 31 entries, the contract naming `create_task`, the fixture recaptured, the canonical snapshot untouched -- and the whole of `tests/contract` run against it: **11 failed, 5195 passed, 3 skipped**, all four files restored by copy and `cmp`, `git status` empty afterwards. **Eight are enumeration updates Run 5 makes in its own commit**: `test_api_migrations::test_the_reader_is_not_vacuous`, `::test_the_write_surface_is_the_reviewed_rpcs` (asserts `'create_task' not in`), `::test_no_published_operation_creates_a_task`, `test_api_surface_contract::test_it_states_adr_0003s_domain_as_adr_0048_amends_it`, `::test_every_declared_object_is_schema_qualified_once`, `::test_the_declared_types_are_separate_from_the_declared_objects`, `test_openapi_normalize::test_the_fixture_is_a_real_captured_document`, `::test_declared_objects_names_relations_and_rpcs_the_way_the_surface_does`. **Three are genuinely blocked on a deployed recapture**: `test_api_surface_contract::test_the_published_set_is_exactly_what_the_snapshot_names`, `test_api_contract_command::test_the_approved_snapshot_exists_and_check_compares_it` (`--check` exits 5 naming `rpc/create_task`), and `::test_a_failing_check_leaves_both_contract_files_untouched` (it expects *cannot reach the REST service* and the surface/snapshot disagreement pre-empts that message). | **Run 5 updates the eight and pushes red on the three**, naming those three in its commit message; Run 7's recapture turns them green. `test_no_published_operation_creates_a_task` **names its own replacement in its failure message** -- *"ADR 0196's migration has shipped, and this marker should be replaced by an assertion that a task can be created"* -- so somebody left Run 5 the instruction and it is followed rather than reinvented. §9's stop condition reads against **three**, not five. | An expected-red set that is *predicted* is the same defect as an unmeasured value, one step earlier: a reader comparing CI's eleven against the plan's five would have had to decide, at the end of a long run, which six were fine. Question 1 of the defect pattern -- what would have to break for this to go red -- asked of the plan's own arithmetic. | 0196 |
| **D1104** | This plan §5 Run 2 **Targeted:** a list of seventeen modules, and the appendix's rule that *"a run's targeted list must include every guard module whose subject the run touched"*. | **CI was RED on `e4a6ada` with five failures, none of them in that list.** The targeted list ran 1642 green. `bin/session-01-check.sh` then ran 5118 passed / **5 failed**: `test_doctor_redaction::test_every_schema_block_is_classified_by_this_file` (outputs v17's `migrations` block is a block neither the printable nor the sensitive list names -- D211's shape, and the exact analogue of D1029's four unclassified mirror leaves, in a second classifier nobody had listed); `test_backup_plane::test_the_v12_step_reaches_a_document_that_validates` (an **eleventh** hand-chained migrator site, whose own comment already records it as *"the tenth hand-chain … found by CI rather than by the grep"*); `test_backup_mirror::…publishes_the_block_and_the_containers_identifiers` (asserted `schema_version == 16` as a literal, in a test whose subject is the mirror); `test_project_retire::test_the_provider_destroy_accepts_the_expired_manifest…` (builds a schema-3 manifest from `project.example.yaml`, which now declares a set, so the version-5 gate refused it at the loader -- the refusal the test exists to measure the absence of); and **`test_database_commands::test_render_reports_a_digest_per_migration`**, which the plan's targeted list NAMES and which I dropped after checking for a neighbouring module (`test_config`) that does not exist in this tree and removing both. | All five repaired in `5a2c414`'s successor. `migrations` is classified **printable** (two digests, a repo-relative directory and a count -- no credential, no address, and the operator asking which SQL a cluster holds is who runs the doctor). `test_backup_mirror` now reads `CURRENT_VERSION`: a literal is right where the version IS the subject and wrong everywhere else. The retirement test pops `migrations` when it downgrades, as `test_project_manifest`'s four helpers now do. | **Question 5 of the defect pattern, answered by CI instead of by me.** The rule the appendix states is the right rule and I applied it to the modules I could think of; the five it missed are five readers of one definition that no grep for `sets_for` or `schema_version` would have surfaced together. The `test_database_commands` miss is not that class -- the plan named it and I removed it on a wrong inference, which is the cheaper kind of error and the one that should not recur: **a module named in a plan is checked for existence individually, never by association**. | — |
| **D1105** | `docs/decisions/README.md` and the outputs migrator: eleven test sites chain `migrate_vN_to_vN+1` by hand (D965), and each version bump edits all of them. | **The count grows and the comment recording it goes stale in place.** `test_output_migrations` holds nine; `test_backup_plane` holds the tenth and says so in a comment written when it was found by CI; version 17 found an eleventh the same way, because a grep for `migrate_v15_to_v16` finds the line and a grep for the CONCEPT finds nothing. Three sessions, three discoveries, one mechanism. | **Recorded, not repaired here.** What removes the class is a single helper that carries a document to the current version and is the only thing these tests call -- a change to eleven modules, in a run that is already large. Left for a session that can give it a battery of its own. | A defect class whose repair is mechanical and whose discovery is not: every instance is found by a version bump, at the end of a run, by CI. That is the cheapest possible place to find it and the most expensive place to fix it. | — |
| **D1106** | `bin/upgrade.sh --help`: `Usage: bin/upgrade.sh <verb> --project KEY [--installed FILE] [--candidate FILE]` -- one synopsis covering all three verbs, with `--candidate` bracketed. | **The bracket is right for one verb of three.** `bin/upgrade.py:231` refuses without it -- *"--candidate is required: this command renders nothing, because it writes nothing"* -- and `check` returns before that block while `plan` and `verify` both fall through it. The trip's command sheet was written from the synopsis, so `upgrade plan --project beta-dev` was typed without it and refused, on a host with a human waiting. | **One synopsis line per verb**, `plan` and `verify` naming the requirement in their own descriptions, and the option saying which verbs read it. The rendered document's path is deliberately NOT restated in the shell: the first wording pasted `.generated/<key>/outputs.json` into the help and `test_honest_readers::test_no_shell_derives_a_rendered_documents_path_for_itself` refused it, correctly -- `upgrade.py`'s refusal is where that path belongs. | A synopsis is read once, before the first attempt, and a refusal that only arrives after the command has been typed is a round trip. The guard catching the repair is the class guard doing its job on its author. | — |
| **D1107** | This plan §5 Run 7: beta's upgrade as a single deploy that adds the project's migration set and moves the release together. | **`upgrade plan` returned BLOCKED.** `inputs.project_sha256` moved as well as the release, and the guard refuses a deploy that changes the release AND the manifest in one operation. | **Split into two deploys, following the refusal's own advice**: the release first, the manifest carrying the set second. Each was planned, deployed and read separately. | The refusal named its remedy and the plan's step had been written without one. Splitting proved MORE than the single operation would have: the set arriving on a release that was already current isolates which deploy published the project's surface. | — |
| **D1108** | `bin/session-20-check.sh`, derived from Session 18's by diff in Run 6, which removed that session's five declaration flags as flags this session's proofs never read (D1021's rule). | **The gate died at step 5 under `set -u`: `REPLACEMENT_HOST_OUTPUTS: unbound variable`.** Run 6 removed the flags and their parsing and left the pre-flight loops that read them -- five references across two loops -- so `--mode host` could not start at all. | The five references removed with the flags they belonged to. | **D1088's own shape, in this session's own gate, in the run after the one that wrote D1088 down**: a definition moved and its callers did not. Question 5 of the defect pattern, committed while applying question 5 to `migrations.py`. | — |
| **D1109** | `bin/session-20-check.sh --help`, whose `SESSION` is 20. | **The mode descriptions still said Session 18 throughout** -- every paragraph describing what each mode measures, carried over unchanged by the diff. | Rewritten to Session 20's subjects. | D505/D853/D858 for the third time: a document derived by diff needs BOTH halves rewritten, and the half that reads correctly as English is the half that survives. | — |
| **D1110** | `deployed_output.RenderedDocumentUnreadable`'s message -- *"a root deploy leaves the rendered directory root-owned"* -- and `CLAUDE.md` §2's standing warning to `sudo chown -R op:op .generated` after any root deploy. | **A sudo deploy already does it.** `bin/deploy-project.py::_restore_checkout_ownership` chowns `.generated/<key>` and the `.locks/*.lock` files back to `SUDO_UID`/`SUDO_GID` after every render. So `sudo ./deploy.sh` hands the directory back and a deploy from a real root login (no `SUDO_UID`), a `sudo pytest` run or a root `--render-only` does not -- and D1060's state had to be CONSTRUCTED deliberately to be read live on this trip, rather than being what the previous deploy left. | The remedy kept and the cause dropped from the message; the docstring now records which privileged commands restore ownership and which do not. `CLAUDE.md` §2's warning corrected in the same pass. | **ADR 0195 one level in.** A reader that correctly reports *I could not determine it* must not then volunteer a cause it also could not determine -- the class's own repair carrying the class's own defect in its explanatory sentence. | 0195, 0199 |
| **D1111** | Run 2 classified `migrations.project_set.` in the doctor's redaction map -- the PREFIX, covering `.root`, `.lock_sha256` and `.count`. | **A project WITHOUT a set renders the bare leaf `migrations.project_set` as an explicit null, and that project is ALPHA** -- the control this session added to prove the boundary. The host gate reported exactly one unclassified field and it was the control's. | The bare leaf classified beside the prefix. | **D1029 a third time, inside the row that says it was paid for in advance.** Adding a prefix and not the leaf it prefixes is the same miss one level down, and the field that goes unclassified is the one belonging to the project that does not have the feature. | — |
| **D1112** | `bin/restore-test.py::released_versions()` reads `migrations/released.lock.json`. | **A correct restore of a correct cluster failed.** Restoring beta -- which declares a set -- reported *"restored 32 versions, the release declares 31"* and failed `schema_matches_the_release`, because the comparison asked the release lock what a project applies. Found by running the PITR drill, not by a grep. | Reads the project set from the deployed document the drill has already loaded, unioned with the release lock. **The set equality is unchanged**: a cluster with the right number and a different set is still a cluster from another release. | **D1088's TWELFTH caller.** The eleven were found by reading `migrations.py`'s callers; this one reads a lock file directly and no grep for `sets_for` or `load_manifest` would have surfaced it. | 0198 |
| **D1113** | Run 1 built the full Session 20 state and ran `tests/contract` against it to enumerate the expected reds -- D1103's measured eleven, which replaced the plan's predicted five. | **`tests/security/test_session3_authorization::test_the_retired_write_rpc_is_gone` was outside the measurement.** It runs only against a deployment, so no offline measurement could have reached it: the expected-red set was complete for the suite it was measured over and not for the suite that exists. It asserted `api.create_task` ABSENT, correctly, for fifteen sessions. | Renamed `test_the_restored_write_rpc_is_published`; the whole-schema enumeration gains `create_task` and stays an enumeration, which is what catches an eighth function nobody reviewed. | D1103 replaced a predicted set with a measured one and the measurement inherited the prediction's boundary. **An expected-red set is scoped by the suite it was measured over, and that scope belongs in the prediction.** | 0196 |
| **D1114** | This plan §2, `TEN-SURF-001`'s live node: beta's served document names the release's and the project's surfaces and nothing else. | **The proof measured the ANONYMOUS view and failed for a reason with nothing to do with its subject.** It hand-rolled a `curl` under `bin/dev-token.sh`, which puts the minted token in the child's environment through `execve` and in nothing else -- no argument, no file, no output, which is the whole of D105 -- and `bin/dev-token.py:87`'s own comment says *"`bin/api-contract.sh` reads exactly one"* of those variables. `curl` reads no bearer from the environment. The request went out unauthenticated, PostgREST answered as `anon`, and beta "served" exactly `{'/'}`. | Runs **`bin/api-contract.sh --check --project FILE --project-outputs FILE`**, the caller `TEN-SURF-001` actually names, which reads `APG_DOCS_TOKEN` from the environment because it is the command `dev-token.sh` exists to run, and compares the reviewed surface, the committed snapshot and the live document at once. The manifest is the tracked `project.example.yaml` -- not a gitignored operator input and not a new roster variable, because `session-20-check.sh` refuses `--project` by name and by design (*"the gate takes DEPLOYED documents, not manifests"*) -- and the test asserts beta's deployed document records the same set root before using it. Alpha, with no `--project`, is the control with teeth. | **This repository's signature defect arriving inside a proof written to catch it**: a value that looked measured and was not. Question 3 of the defect pattern -- whose identity, through which tool -- asked of a proof whose entire subject is which surface a role is served. | 0050, 0198 |
| **D1115** | The doctor half of `TEN-DOC-001` read `check["facts"]["released"]`. | **The field is `evidence`** -- a tuple of pairs that `bin/doctor.py` renders with `dict(check.evidence)`. The proof died with `KeyError` on the host, AFTER the verdict it cares about had already passed. | `dict(check["evidence"])`. | A key name read from memory of the shape rather than from the module. Cheap to find and free to prevent: the module was two files away. | — |
| **D1116** | Commit `671bb048`, whose message sets out six repairs the first host gate found, each with its reasoning. | **Five of the six are in the diff.** The served-document repair (D1114) is described in the message in full -- the token, the environment, the anonymous view, the replacement caller -- and the file still hand-rolled the `curl`. The second host gate re-measured the anonymous view and reported the identical failure, and its summary line alone did not name which test, so the log had to be fetched before anything could be diagnosed. | Repaired in `f3f2058`. Recorded as a divergence in its own right rather than folded into D1114. | **A commit message is not evidence that a commit contains what it says**, and nothing in a run's sequence compares the two. The message was written from the intended change and the patch that produced it did not run; `ruff`, the targeted modules and CI all passed, because five of six repairs is a green tree. Cost: one 15-minute host gate. | — |
| **D1117** | `TEN-SURF-001`: *"`api-contract.sh check --project FILE` compares the merged surface against that project's own snapshot"*, and `bin/api-contract.py::command_check`'s final clause. | **`--check --project` could not exit 0 for any project that HAS a set.** `command_check` rebinds `snapshot` to the project's, and the clause then compares the deployed document's `api.canonical_openapi_sha256` against `fingerprint(snapshot)`. That digest is written by `bin/deploy-project.py` from `SNAPSHOT_PATH` **unconditionally** -- what a given project actually serves is recorded beside it as `project_openapi_sha256` -- so it is identical on every project of a release. Measured on the host before anything was changed: alpha and beta both record `85adb686...`, which is `fingerprint(release snapshot)`, while the example project's snapshot fingerprints to `808ac715...`. Two different things compared, firing always. | The clause compares the RELEASE snapshot's fingerprint under both paths, and its message now says *"the committed RELEASE snapshot"*. The guard drives `command_check` directly -- a route the product does not take, proving the end state rather than the product (ADR 0065/0066) -- supplying the fetch and the document so the only thing left varying is which digest the clause chose, with the control the first half cannot reach: a document recording the PROJECT's digest must still exit 6, or the test passes against a clause deleted outright. Battery 2/2 killed, both `FAILED` rather than `ERROR`, paired control green in both, restore verified by `cmp`. | **Invisible offline for a reason the fixture states in its own docstring**: a project's real snapshot only comes from a deployment of that project, so no offline test could hold one AND a deployed document, and this line had never executed with `project_path` set. The twelfth never-executed path a trip has found -- and the first found by making a proof call the product's own command instead of hand-rolling the request it makes (D1114). Two defects, one cause: the proof that would have exercised the clause was the proof that bypassed it. | 0050, 0065, 0066, 0198 |
| **D1118** | This plan §5 Run 7's deploy steps, and `test_the_deployed_document_records_the_checksums_it_serves`. | **A correct deployment fails it, once.** The test compares `api.canonical_openapi_sha256` in the deployed document against this checkout's snapshot. The document records what the deploy computed, and at deploy time that was the OLD snapshot; the new one is then captured FROM that deployment and committed, so the document and the checkout disagree until the next deploy. | The cycle is **capture -> commit -> redeploy**, and both projects were redeployed before the gate was re-run. Recorded because Run 7's steps do not say it. | Not a defect -- a step the runbook owes. A snapshot captured from a deployment is behind the deployment that produced it by construction, which is D1039's *unsatisfiable rather than unsatisfied* seen from the deploy's side rather than the test's. | 0050 |

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

Family `TEN-*` new; `API-*` and `OPS-*` extended. Every requirement belongs to
a claim (D697); the three new claims are `tenant_extension_point`,
`task_domain` and `honest_readers`, all dated 20. `DEP-001` and `DX-001` are
unchanged and keep their Session 12 claims (ADR 0197). All P0.

| Requirement | What it states | Offline node ids (proposed) | Live half |
|---|---|---|---|
| `TEN-SET-001` | A project manifest at schema 5 may name a migration set under `projects/<slug>/`; the render writes the release's set and then the project's into one directory in version order; `freeze-lock --project` and `verify-lock --project` freeze and verify the project's own lock; the release lock is never rewritten by a project; a project version older than the release lock's newest at freeze is refused | `test_project_migration_sets.py::test_a_declared_set_renders_after_the_release_set_in_version_order`, `::test_the_project_lock_is_frozen_and_verified_apart_from_the_release_lock`, `::test_a_project_version_older_than_the_release_lock_is_refused`, `test_rendered_migrations.py::test_the_rendered_manifest_names_the_set_of_every_file` | `test_session20_tenant.py::test_the_project_set_beta_declares_is_applied_ledgered_and_published` |
| `TEN-SET-002` | A project set is refused before it is rendered if any template names `app_private`, creates or alters a role, schema, extension or default privilege, sets a role other than `SET LOCAL ROLE {{object_owner}}`, drops or alters an object the release's final surface owns, declares a placeholder outside the request-role allowlist, creates a table in `app` without `FORCE ROW LEVEL SECURITY`, or carries a `down` block that does not raise `AP900` | `test_project_migration_sets.py::test_the_lint_refuses_each_forbidden_shape_and_accepts_the_example_set` (parametrised, one arm per shape, the example set as the control) | — (offline by nature; the claim's live half is `TEN-SET-001`'s) |
| `TEN-SURF-001` | A project's reviewed surface (`projects/<slug>/contracts/postgrest-api-surface.yaml`, api-surface schema version 2) is merged with the release's for every comparison; a name the release owns is refused; `api-contract.sh check --project FILE` compares the merged surface with the project's own snapshot and `--update --project FILE` prints the path the candidate belongs at; the release contract, its snapshot and its control fixture are not read differently for a project that has a set | `test_project_migration_sets.py::test_the_project_reader_finds_every_object_the_project_contract_names`, `test_api_surface_contract.py::test_a_project_surface_cannot_redeclare_a_release_object`, `test_api_contract_command.py::test_check_with_a_project_compares_the_merged_surface_against_the_project_snapshot` | `test_session20_tenant.py::test_betas_served_document_names_the_release_and_project_surfaces_and_nothing_else` |
| `TEN-DOC-001` | Outputs v17 records `migrations.release_lock_sha256` and `migrations.project_set` (null, or root, lock digest and count) on both branches; a v16 document migrates; the doctor's migration check counts both sets against the ledger; the isolation matrix classifies the new leaves | `test_output_migrations.py::test_v16_to_v17_adds_the_migrations_block_and_leaves_every_route_word`, `test_diagnosis.py::test_the_migration_check_counts_the_project_set` | `test_session20_tenant.py::test_both_deployed_documents_are_v17_and_the_doctor_reads_the_sets` |
| `API-TASK-001` | `api.create_task(p_title, p_note_id DEFAULT NULL)` exists (migration 0031, ADR 0196), derives `owner_id` from `app.current_user_id()`, raises `PT401` with no identity and `PT404` for a note absent or another owner's, is executable by `authenticated` and `agent_writer` and by no other role, ends in `NOTIFY pgrst`; the reviewed contract names it and the snapshot publishes it | `test_api_migrations.py` (the vacuity set gains it; `test_every_new_function_revokes_public_before_it_grants` covers it), `test_migrations_apply_as_the_migration_user.py::test_create_task_is_reachable_by_the_two_writer_roles_and_no_other` | `test_session20_tenant.py::test_a_task_created_through_the_enumerated_operation_is_the_row_update_task_status_moves` |
| `OPS-READ-001` | `migrate.sh render`, `db.sh`, `postgres-bootstrap.sh`, `doctor`, `upgrade` and `project-retire` distinguish a rendered document they cannot read (exit 3, naming the owner and the remedy) from one that does not exist (exit 4, *never deployed here*) | `test_database_commands.py::test_an_unreadable_rendered_document_is_reported_as_unreadable_not_absent` (parametrised over the six readers, a `chmod 000` directory as the arm and an absent one as the control) | `test_session20_tenant.py::test_render_as_the_operator_after_a_root_deploy_says_unreadable_not_never_deployed` |
| `OPS-READ-002` | `routes.*.status` carries `unobserved` for a route the deploy did not observe, `unavailable` only for one it observed not serving or determinately not published (D230, D326); every reader of the status accepts the third word; the printed summary and the document agree | `test_deployed_output.py::test_a_route_the_deploy_did_not_observe_is_recorded_unobserved`, `test_diagnosis.py::test_the_doctor_reports_an_unobserved_route_as_unobserved` | `test_session20_tenant.py::test_no_route_on_either_project_reads_unobserved_after_a_redeploy` |

**Claims** (`src/agentic_postgres/evidence_claims.py`): `tenant_extension_point:
("TEN-SET-001", "TEN-SET-002", "TEN-SURF-001", "TEN-DOC-001")`; `task_domain:
("API-TASK-001",)`; `honest_readers: ("OPS-READ-001", "OPS-READ-002")`.
`claim_mode` requires a live node id per claim; each has one above.

**No new gate variable.** Every live half reads `APG_PROJECT_A_OUTPUTS`,
`APG_PROJECT_B_OUTPUTS` and `APG_LIVE_HOST`, already in the roster.
`test_render_as_the_operator_after_a_root_deploy_…` runs `bin/migrate.sh` as
the gate's own user against `.generated/alpha-dev` and reads its exit code and
message; it is a reading of the host, not a declaration.

---

## 4. Irreversible operations

| Operation | Where | What makes it safe |
|---|---|---|
| Migration `0031-create-task.sql` applied to alpha and beta | Run 7 | Fix-forward (D912); its `down` raises `AP900`; the body is ADR 0196's specification and 0005's shape with 0007's column list; rig 20b applies it to a throwaway cluster with 30 migrations before it first; grants proved by role in the rig |
| The example project set applied to beta | Run 7 | One table with FORCE RLS, one view, one RPC, all under `projects/example/`; removing it later is a new project migration, never a deletion (ADR 0028); beta is the operator's development project and the operator decides it (§0) |
| `migrations/released.lock.json` re-frozen with 0031 | Run 5 | `freeze-lock` from a clean tree; `verify-lock` refuses a removed or altered entry; the diff is one added entry, reviewed |
| The release snapshot and the control fixture recaptured | Runs 1 and 7 | Each capture is from a running PostgREST and refuses a hand edit; the review compares the diff to exactly `rpc/create_task` (release) and the example set's objects (beta) |
| `CURRENT_SESSION` 18 → 20 | Run 6 | All-or-nothing (D690); every `target_session: 20` requirement has its proofs in the same commit |
| `VERSION` 1.0.1 → 1.1.0 | Run 6 | Proposed, not chosen: Run 7 reads `upgrade plan` on both projects and a major *required* is a stop condition (§9) |
| Both projects deployed `--through-session 20` | Run 7 | Unredirected, at a TTY (D972); `upgrade check` and `plan` first; alpha then beta, the doctor between |
| Merge of `session-20` into `main` | Run 7 | Fast-forward only, after CI is green on the branch's last commit |

Not irreversible and worth saying: `sudo chown -R op:op .generated` after each
root deploy (CLAUDE.md §2), and the branch itself, which is deleted after the
merge.

---

## 5. Build order, run by run

Each run ends with: ruff, the targeted modules (named), derived docs
regenerated where a generator's input moved, `chmod 755 bin/*`, one commit on
the `session-20` branch with a message file, a push, and **that commit's CI
verdict read** by full SHA with three buckets (D1059). A run that writes a test
runs its battery (appendix). Mark the run **Done.** here with what it measured.

### Run 1 — the measurements, the ADRs, and the recaptured control

**Rigs** (scripts under `/tmp` in WSL, outputs to files, controls named):

- **20a, dbmate ordering.** A throwaway cluster on `POSTGRES_IMAGE` (the
  `cluster` fixture's route), the `dbmate` image from `versions.env`, one
  directory. Arm A: apply `20260904120030_x.sql` then add `20260903000000_y.sql`
  and run `up --strict`; arm B: add `20260915000000_z.sql` instead; control:
  the directory with A's file only. Record exit codes and dbmate's message. This
  decides whether D1092's rule is a refusal the tree needs to write or one
  dbmate already makes.
- **20b, `create_task`.** The same cluster with all 30 rendered fixture
  migrations plus the draft `0031`, rig 19's four probes as the control (ADR
  0196's table): as `authenticated` with `app.user_id` set → a row in
  `api.tasks`; without the GUC → `PT401`; with another owner's note id →
  `PT404`; as `app_runtime` → refused; `has_function_privilege` for every role
  in `naming.ROLE_SUFFIXES`, expecting `authenticated` and `agent_writer` only.
- **20c, the control recapture.** A throwaway cluster from
  `project.second.example.yaml`'s render (no project set), PostgREST at
  `POSTGREST_IMAGE` serving `api` as `api_documentation`, request with `Host:
  alpha.example.test:443` and `basePath` `/api/rest` so `CAPTURED_HOST` and
  `CAPTURED_BASE_PATH` in `test_api_contract_command.py` stay true; normalise
  with `openapi_normalize`; diff against the committed fixture — **the only
  difference may be `rpc/create_task`**. This is Session 5 Run 9's route; grep
  its plan for the exact commands before writing new ones.

**ADRs**, indexed in `docs/decisions/README.md`:

- **0198 — A project owns a migration set, a reviewed surface and a snapshot
  beside the release's.** Where it lives (D1087), the version rule (D1092),
  the placeholder allowlist and the lint (`TEN-SET-002`), the merged surface
  and per-project snapshot (`TEN-SURF-001`), what a *source edit* is (D1091),
  what the release never does for a project (rewrite its lock, read its
  contract into the release's tests). Related: 0028, 0050, 0197.
- **0199 — A route the deploy did not observe is `unobserved`, and a migrator
  never guesses which one that was.** D1048, D1094, the readers, the
  `const` couplings (`unobserved` ⇒ `url: null`), and D1060's sibling rule for
  the six readers (`OPS-READ-001`). Related: 0195, 0158, D600.

**Measures.** The three rigs' outputs, pasted into this run's Done paragraph.
**Targeted:** nothing changes but documents. **Commit:** the two ADRs, the
index, the recaptured fixture *only if* its diff is exactly `rpc/create_task`
(otherwise stop, §9).

**Done.** 2026-09-10. Three rigs, six divergence rows (D1098–D1103), two ADRs.
Everything below was run; the scripts and their outputs are at `~/rig20/` in
WSL. No stop condition was met.

**Rig 20a — dbmate ordering (D1098, D1099).** `~/rig20/rig20a.sh`, output
`rig20a.txt`. One throwaway cluster on the pinned `pgvector/pgvector:pg18`
digest, four databases, the pinned `amacneil/dbmate:2.34.1` digest run with the
product's own flag positions (`--env`, `--migrations-dir`, `--migrations-table
app_private.schema_migrations`, `--no-dump-schema`, then `up --strict`).

| Arm | Directory | Exit | dbmate said |
|---|---|---|---|
| control | `20260904120030` alone | 0 | applied it |
| A | that applied, then `20260903000000` added **pending** | **2** | *migration `20260903000000` is out of order with already applied migrations, the version number has to be higher than the applied migration `20260904120030` in --strict mode* |
| B | that applied, then `20260915000000` added | 0 | applied the new one only |
| C | **both** files, fresh database | 0 | applied both, in filename order |

Arm A applied **nothing** — `app_private.schema_migrations` still held one row
and `public.rig_y` did not exist. So the deploy-time refusal D1092 hoped for is
already dbmate's, and arm C proves the divergence the rule exists to prevent is
real. `follows_release_version` stays, as the freeze-time refusal in front of
it. Then `dbmate status` on arm A's directory: exit **0**, `Applied: 1`,
`Pending: 1`, the out-of-order file listed as an ordinary pending one — D1099.

**Rig 20b — ADR 0196's `create_task` (D1100, D1101).** `~/rig20/rig20b2.py`,
output `rig20b2.txt`; the draft template is `~/rig20/0031-draft.sql`. Two arms
on one cluster: thirty released migrations rendered by the product's own
`render_migration` and applied **as `migration_user` over TCP** (D285's route —
a superuser rig bypasses every ownership check), then the draft 0031 by the same
route, **exit 0**. Every probe is read as a **SQLSTATE** rather than as output:
the first pass of this rig dropped `ON_ERROR_STOP=1` and every refusal "passed"
by printing a `CONTEXT` line, which is D386's shape in a rig instead of a
battery, and is why the second pass exists.

| Probe | SQLSTATE |
|---|---|
| `authenticated` + `app.user_id`, no note | a row |
| `authenticated` + the caller's **own** note | a row |
| `authenticated`, **no** `app.user_id` | `PT401` |
| `authenticated` + **another owner's** note | `PT404` |
| `authenticated` + a note id that does not exist | `PT404` — the same answer, 0007's reason |
| `anon` + `app.user_id` | `42501` |
| `agent_reader` + `app.user_id` | `42501` |
| `agent_writer` + `app.user_id` | a row |
| `app_runtime` + `app.user_id` | **a row** — see D1100 |

`proacl` on `api.create_task` is exactly `object_owner`, `authenticated`,
`agent_writer`, `api_documentation`. `has_function_privilege` additionally
answers true for `app_runtime`, which inherits `authenticated`
(`inherit=true`, established deliberately in `postgres-bootstrap.py`) — and
which, on the **control arm with no 0031 at all**, already creates notes through
`api.create_note` on a cluster that is exactly 1.0.1. That is D1100, and D1101 is
its consequence for Run 5's proof. `update_task_status` was then run against the
row the first probe made — `pending → in_progress`, then the same swap again
returning `PT409` — the compare-and-swap's first run against a row outside a
fixture, four rows in `app.tasks` where rig 19 measured zero permanently.

**Rig 20c — the control fixture (D1102).** `~/rig20/rig20c.py`, output
`rig20c.txt`, arms at `rig20c-arm-a-raw.json` and `rig20c-arm-b-raw.json`. One
cluster, one PostgREST on the pinned `postgrest:v14.16` digest with
`openapi-mode = follow-privileges`, the documentation role as the anon role and
`PGRST_OPENAPI_SERVER_PROXY_URI=https://alpha.example.test/api/rest` so
`CAPTURED_HOST` and `CAPTURED_BASE_PATH` stay true.

**The rig has a control on itself, and it is the reason ARM B is readable.**
ARM A is the same capture with no 0031: it equals the committed fixture
normalized, and — measured, not required — **byte for byte** as well. Without
that, "the only difference is `create_task`" would be a sentence about a
comparison nobody could make. ARM B, captured after 0031 applied and the
migration's own `NOTIFY pgrst, 'reload schema'` was polled for:

- top-level keys that differ: `['paths']`
- paths **added**: `['/rpc/create_task']`; removed: none; bodies changed: none
- definitions that differ: none

So §9's stop condition is not met and the recapture may be made. What it may
**not** be is committed alone: the fixture's path set is asserted against a
hardcoded literal in `test_openapi_normalize.py`, so the bytes travel to Run 5
(D1102).

**The expected-red set, measured (D1103).** `~/rig20/measure-run5.sh` built the
full Run 5 state in the working tree — 0031 in the templates and the manifest,
`bin/migrate.sh freeze-lock` re-frozen to **31** entries, the reviewed contract
naming `create_task`, the fixture recaptured, the canonical snapshot untouched —
and ran the whole of `tests/contract` against it: **11 failed, 5195 passed, 3
skipped in 516 s**. Eight are enumeration updates Run 5 makes; three are blocked
on a deployed recapture. D1103 has both lists. All four files were then restored
by copy, `cmp`-verified, the template removed, and `git status --porcelain` came
back **empty**.

**Committed:** the two ADRs, the index, D1098–D1103 and this paragraph. No code
changed; the recaptured fixture is Run 5's.

### Run 2 — the project migration set

**Builds.**

1. `src/agentic_postgres/migrations.py`: `MigrationSet` (frozen dataclass:
   `label` in `{"release","project"}`, `root: Path`, `manifest_path`,
   `lock_path`), `release_set()`, `project_set_from(document, repo_root)`
   reading `document["migrations"]["project_set"]["root"]`, `sets_for(document,
   repo_root)`; `verify_lock` gains the `follows_release_version` check for a
   project lock (D1092, as rig 20a decided); `PROJECT_PLACEHOLDER_SOURCES`, the
   allowlist (`database.roles.{object_owner, authenticated, anon, agent_reader,
   agent_writer, api_documentation}` and `database.name`); `lint_project_set(
   set)` implementing `TEN-SET-002` over the applied half with comments
   stripped — move `up_section` and `sql_only` out of
   `tests/contract/test_api_migrations.py` into a new
   `src/agentic_postgres/sql_surface.py` so the lint and the test read SQL the
   same way (the test imports them back; its assertions do not change).
2. `schemas/project.schema.json`: `schema_version` enum gains 5; top-level
   optional `migrations: { set: string }` with pattern
   `^projects/[a-z][a-z0-9-]{2,30}$`, forbidden below 5 (an `allOf` gate in
   ADR 0188's shape, optional at 5 because a set is a facility). `config.py`:
   `SUPPORTED_PROJECT_SCHEMA_VERSIONS` gains 5; `validate_project_semantics`
   refuses a set whose directory is absent. `bin/render-config.py --bounds-doc
   --write` regenerates the bounds document.
3. `schemas/migration-manifest.schema.json`: unchanged for the manifest; the
   project **lock** gains `follows_release_version` (a new key in the lock
   document, `schema_version` 2 for a project lock, 1 for the release's).
4. `rendering.write_rendered_migrations`: renders `sets_for(document)` in
   version order into one directory; each `rendered-manifest.json` entry gains
   `"set"`; the manifest gains `project_set`. `render_project` validates
   `migrations.set` and lints the project set before publishing.
5. Outputs **v17** (`schemas/outputs.schema.json`, `output_migrations.
   migrate_v16_to_v17`, `CURRENT_VERSION = 17`, `deployed_output`): a
   `migrations` block on both branches — `release_lock_sha256` and
   `project_set: null | {root, lock_sha256, count}`. The migrator adds the
   block from `NO_PROJECT_SET` and touches nothing else (D1094's route half is
   Run 4's). Nine tests chain the migrator by hand (D965) and each gains the
   v17 step by one replace-all edit; say so in the commit.
6. `bin/migrate.py`: `render_set` and `record_ledger` over `sets_for` (D1096);
   `freeze-lock --project FILE` freezes the project set's lock and refuses a
   manifest with no set; `verify-lock` verifies the release and, with
   `--project`, the project's too; `bin/migrate.sh parse_args` admits
   `--project` for those two verbs and the usage says which lock each writes.
7. `bin/doctor.py:358` counts `sets_for`; `bin/session-09-check.sh`'s two
   sites and the five contract fixtures (D1088) switch to `sets_for` with the
   fixture's document, so **CI applies the example project set to a throwaway
   cluster on every push** — that is the shadow database D1067 absorbed.
8. `projects/example/`: the product's own example set, which the fixture
   manifest declares. `migrations/manifest.json` (schema 1, placeholders from
   the allowlist), `templates/0001-note-embeddings.sql` (version
   `20260914120001`): `app.note_embeddings(note_id uuid primary key references
   app.notes(id) on delete cascade, owner_id uuid not null, embedding
   extensions.vector(768) not null, updated_at timestamptz not null default
   now())` with `ENABLE` and `FORCE ROW LEVEL SECURITY` and the owner policy
   on `app.current_user_id()`, `api.note_embeddings` as a `security_invoker`
   view, `api.set_note_embedding(p_note_id uuid, p_embedding extensions.vector)`
   `SECURITY DEFINER` in 0031's shape (Run 5) with `PT401`/`PT404`, `REVOKE ALL
   … FROM PUBLIC`, `GRANT EXECUTE … TO {{authenticated}}`, view `SELECT` and
   function `EXECUTE` to `{{api_documentation}}` (F-007: without them the
   snapshot never publishes it), `NOTIFY pgrst, 'reload schema'`, a `down`
   raising `AP900`; `released.lock.json` frozen by the new verb. This is the
   pgvector example D698 and D714 said was never registered, arriving as what
   it always was — a project's migration.
9. `project.example.yaml` → schema 5 with `migrations: {set: projects/example}`;
   `project.second.example.yaml` → schema 5 without a set. Re-render both
   fixtures (`--render-only`); `.generated/fixture-*` are refreshed, not added.
10. The isolation matrix (`tests/deployment/test_session12_isolation_matrix.py`
    and its classification list): `migrations.release_lock_sha256` must match;
    `migrations.project_set.*` carries no authority and may differ (D1029's
    lesson, paid in advance).

**Tests.** `tests/contract/test_project_migration_sets.py` (new; every
`TEN-SET-*` node id in §2, driving the example set and hand-built refused
sets under `tmp_path`); `test_migrations.py` and `test_rendered_migrations.py`
extended for two sets; `test_output_migrations.py` for v17; `test_config.py`
for schema 5; `test_migrate_command` (or `test_database_commands.py`) for the
two verbs' `--project`; `test_diagnosis.py` for the doctor's count.

**Battery.** Mutations: the lint's `app_private` regex removed (kill expected
in the lint test, control: the release set still renders); `follows_release_
version` check inverted; `record_ledger` reverted to the release lock alone
(kill in the ledger proof with a project set); `sets_for` returning the
release only (kill in the render-order test). Each with an anchor that matches
once, `FAILED` not `ERROR`, files restored by copy and `cmp`.

**Targeted:** `test_migrations`, `test_project_migration_sets`,
`test_rendered_migrations`, `test_output_migrations`, `test_config`,
`test_database_commands`, `test_diagnosis`, `test_fleet`, `test_api_migrations`
(the reader moved), `test_migrations_apply_as_the_migration_user`,
`test_storage_plane`, `test_auth_service_reaches_its_data`,
`test_storage_service_reaches_its_data`, `test_agent_audit_plane`,
`test_auth_endpoints`, `test_session12_isolation_matrix` (offline half),
`test_cli_contract`.

**Done.** 2026-09-10, `e4a6ada`. Everything in the list above is built; the
module names in the plan were written from memory and three of them do not
exist in this tree (`test_config` is `test_project_manifest`,
`test_database_commands` is `test_cli_contract`'s subject, and the ledger had
no module at all -- see below).

**What the run found that the plan did not say.**

- **`record_ledger` had no test whatsoever**, which is how D1096 survived to be
  found by reading rather than by a failure. `tests/contract/
  test_migration_ledger.py` is new (5 tests, against a recorded `psql`), and
  the mutation that reverts the function to the release lock alone is one of
  the battery's four.
- **The `v14` outputs fixture is built by SUBTRACTION from the current
  document**, so it had already grown one line per version -- `backup.mirror`
  was appended by version 16 under a comment saying it did not exist when the
  fixture was written. Version 17 would have been the third. It now chains
  through `v15`, which chains through a new `v16`, so each version's fixture
  removes exactly what that version adds. The failure mode this removes is
  silent in the direction that matters: a v14 document still carrying a v17
  field makes the step under test refuse for a reason that has nothing to do
  with the step.
- **`test_project_manifest`'s three downgrade helpers each deep-copied the base
  separately**, so the version-5 gate refused three unrelated tests until each
  was taught to pop `migrations`. They now chain, for the `v14` fixture's
  reason.
- **The outputs schema has six `ready`/`unavailable` enums of identical shape**,
  and only `publishedRoute` and the deployed branch's `routes.health` may gain
  `unobserved` -- `deployedApi`, `mcp` and the TLS block answer whether a PLANE
  came up, which is a different question. A textual patch matched six places;
  `publishedRoute` is edited structurally, by name, and the patch ASSERTS the
  other three did not gain the word.
- **The rendered branch's `routes.health.status` is `const: "planned"`** and was
  left alone: a render observes nothing, so there is nothing there for a third
  word to mean.

**Measured, end to end.** `./deploy.sh --render-only` on both fixtures:
`fixture-alpha-dev` renders **31** `.sql` files in one directory, 30 labelled
`set: release` (20260807120001..20260904120030) and 1 labelled `set: project`
(20260914120001), with `migrations.project_set = {root: projects/example,
count: 1, lock_sha256: b77be65d…}`; `fixture-alpine-dev` -- schema 5, no set --
renders **30** and `project_set: null`. Both documents carry the same
`release_lock_sha256`, which is what the isolation matrix now asserts must
match.

`bin/migrate.sh --project project.example.yaml freeze-lock` wrote
`projects/example/migrations/released.lock.json` at schema version 2 with
`follows_release_version 20260904120030`, and `git diff` on
`migrations/released.lock.json` was **empty** -- the release's lock is not a
project verb's to write. `verify-lock --project` verifies both.

**The lint refuses, and the refusals were measured before they were trusted.**
Eleven arms against a copy of the example set under a temporary directory, each
anchor pre-flighted to match exactly once, the real set green in the same
invocation: `app_private` named, a role created, a schema created, an extension
created, default privileges altered, `SET ROLE` instead of the local preamble, a
release view dropped, a release function dropped, `FORCE ROW LEVEL SECURITY`
removed, the `down` block's `AP900` removed, a placeholder outside the
allowlist. A twelfth arm asserts a forbidden word inside a COMMENT is not a
forbidden statement -- Session 2 Run 7's defect, and the reason
`sql_surface.sql_only` exists.

**The version rule refuses both boundaries**: a project version older than the
recorded release version, and one EQUAL to it. Two controls in the same
invocation: the committed example lock verifies, and the release lock verifies
while carrying no `follows_release_version` at all -- so the rule cannot have
leaked onto the release's own migrations.

**CI now applies the example project set to a throwaway cluster on every push.**
The five fixtures D1088 names switched to `sets_for`, and
`test_migrations_apply_as_the_migration_user` applies it **as `migration_user`
over TCP** -- the route D285 exists for, since every offline rig that applies
migrations as a superuser bypasses the ownership check entirely. That is
D1067's shadow database, arriving as a consequence of where the set lives rather
than as something built. All five green (1642 passed with them, 1398 without).

**Battery: 4 mutations, 4 killed, every paired control green.** The lint's
`app_private` rule removed; the `follows_release_version` comparison inverted;
`record_ledger` reverted to the release lock alone; `sets_for` returning the
release only. Every anchor pre-flighted, `FAILED` distinguished from `ERROR`,
files restored by copy and byte-compared. **The battery's own baseline pass
caught one of its control targets naming a test that does not exist** -- which
would have read as a kill for that mutation, and is D499's rule catching the
person applying it.

**Not built here**, and deliberately: a project's reviewed surface and its own
snapshot are Run 3's; the six honest readers and `unobserved`'s writer are Run
4's (the schema and the migrator's half of ADR 0199 are here, because one
outputs version carries both).

### Run 3 — a project's reviewed surface, and the reader as a module

**Builds.**

1. `schemas/api-surface.schema.json`: version 2, the project form — `schema_
   version: 2`, `contract_id`, `exposed_schema: api`, `relations`, `rpcs`,
   `enums` (may be empty at 2; the release's version 1 keeps `minProperties`),
   and **no** `agent_rpcs`, `agent_write_rpcs` or `forbidden_schemas` (the
   release's apply to the whole database).
2. `api_surface.py`: `load_project_surface(path)`, `merged_surface(release,
   project)` refusing any name the release declares in any kind
   (`_refuse_name_collisions` over the union), `project_contract_path(set)`,
   `project_snapshot_path(set)`. `CONTRACT_PATH` stays fixed; a project's is
   fixed relative to its set.
3. `src/agentic_postgres/sql_surface.py` (begun in Run 2): `final_surface(set)`
   — the interpreter from `test_api_migrations.py` (`_CREATE_VIEW`, `_CREATE_
   FUNCTION`, `_CREATE_ENUM`, the drops), unchanged in behaviour, importable.
   `test_api_migrations.py` imports it; its assertions do not move (D1089).
4. `tests/contract/test_project_migration_sets.py` gains the `TEN-SURF-001`
   reader test: over every `projects/*/` set, `final_surface` finds exactly the
   objects the project's contract names, non-empty.
5. `bin/api-contract.py` / `.sh`: `--project FILE` on `check` and `update`.
   With it, `check` loads the merged surface and the project's snapshot;
   `update` prints, on stderr, the path the candidate belongs at
   (`projects/<slug>/contracts/postgrest-openapi.canonical.json`) and keeps
   streaming the candidate to stdout (the D1039 clause stays). Without it,
   behaviour is unchanged. `test_api_surface_contract.py` gains the
   redeclaration refusal; `test_api_contract_command.py` gains the project
   check against a snapshot built under `tmp_path` from the captured control
   plus the example set's paths.
6. `docs/api-surface.md`: a section *A project's surface*; the broken link
   fixed here or in Run 5 (D1095), whichever commit touches the file first.

**Battery.** `merged_surface` collision check removed (kill); the project
reader's non-empty assertion removed (kill against an empty set under
`tmp_path`); `--project` ignored in `check` (kill: the merged comparison must
report the example set's objects missing from the release snapshot).

**Targeted:** `test_api_surface_contract`, `test_api_contract_command`,
`test_api_migrations`, `test_project_migration_sets`, `test_cli_contract`,
`test_repository_contract`.

**Done.** 2026-09-10, `63435df`, CI green. 1083 targeted; no Docker-backed
module is in this run's blast radius, because nothing here changes what a
migration applies.

**The schema change is a widening only if the gate is complete, so the gate is
read rather than reviewed.** Version 2 exists by moving four `required` entries
and three `minProperties` bounds off the properties and into a version 1 gate.
If that gate lost one, the release's contract would silently stop being required
to name its own agent plane -- and the diff that did it would look like tidying.
`test_the_schema_is_referenced_by_the_module_and_exists` now reads both gates
out of the schema and asserts exactly what version 1 restores and what version 2
forbids; it also cross-checks `api_surface.PLATFORM_ONLY_SECTIONS` against the
schema's own list, for `REQUIRED_FORBIDDEN_SCHEMAS`' reason. The assertion it
replaces was `enum == [1]`, which would have become `enum == [1, 2]` and said
nothing.

**Measured, offline.** `bin/api-contract.sh` exit codes, printed from inside a
script (D-class: `echo "$?"` after `wsl bash -lc` reads Git Bash's status):
`--check` alone **0** and still reporting *4 objects*; `--check --project
project.example.yaml` **5**, naming
`projects/example/contracts/postgrest-openapi.canonical.json`; `--check
--project project.second.example.yaml` **2**, because a manifest with no set has
no contract of its own; a `--project` naming a file that does not exist **2**,
so a bad path can never read as *the release's contract, then*.

The merged surface: `notes-tasks-v1+example-note-embeddings-v1`, relations
`{note_embeddings, notes, tasks}`, rpcs `{create_note, set_note_embedding,
update_task_status}`, and `forbidden_schemas` and both agent sections **the
release's, unchanged**. The SQL reader over `projects/example` finds exactly
`{note_embeddings, set_note_embedding}` -- the two names the project's contract
declares, with the view's four columns and the function's two argument names
agreeing.

**The battery found two weaknesses in this run's own proofs, and both were
real.** Recorded here because a battery whose survivors are all reported as
"uninformative" is a battery nobody reads.

1. *The non-empty guard had no scenario.* `test_the_project_reader_finds_every_
   object_the_project_contract_names` loops over the sets that exist in
   `projects/`, all of which publish something, so its `assert published` can
   never fire. The mutation was also mine to get wrong: it removed an assertion
   from a TEST rather than changing the product, which is D493's shape and could
   not have killed anything. Repaired on both sides -- the mutation now strips
   functions and enums from `sql_surface.published_names`, leaving views, so the
   example set's view still matches and only the RPC goes missing (a PARTIAL
   answer, which is the failure a total one would never have); and a new arm
   cuts the example set's view and function under `tmp_path` and asserts the
   reader reports nothing. **That arm had to trim the manifest's placeholders
   too** -- `load_manifest` refused the declared-but-unused pair, correctly --
   which is exactly what an adopter making the same change would have to do, and
   is why the arm is a set that could exist rather than one that measures the
   manifest rules.

2. *A test named for a command asserted a path resolver.* `test_check_with_a_
   project_reads_the_projects_snapshot_path` checked that
   `project_snapshot_path` returns the project's file -- and a mutation
   replacing `load_project_snapshot(root)` with `load_snapshot()` inside
   `command_check` survived it, because nothing had ever said which file the
   COMMAND opens. It now drives the command. **Both states exit 5**, so the exit
   code cannot distinguish them and the signal is the message: unmutated,
   *there is no approved snapshot at projects/example/...*; mutated, *the
   snapshot and the reviewed surface disagree*. Those are ADR 0195's two
   outcomes -- I could not find the thing, and the things disagree -- and a
   reader that could not tell them apart would send an operator to audit a
   contract when the answer is "capture the snapshot".

   The test asserts `"disagree" not in message`, which is the unusual half: a
   negative on the message text is normally a weak assertion, and here it is the
   only thing that separates two states with one exit code.

After repair: **4 mutations, 4 killed, every paired control green**, every file
restored by copy and byte-compared.

**One thing this run could not prove and did not pretend to.** A project's real
snapshot can only come from a deployment of that project -- `--update` reads
`routes.rest.url` from a deployed document -- so the merged comparison is proved
against a snapshot BUILT under `tmp_path` from the captured control plus the
example set's paths. What that proves is bounded and the fixture's docstring
says so: the comparison accepts a document naming the merged surface's objects.
That PostgREST produces such a document is `TEN-SURF-001`'s live half, and it is
Run 7's. This is D1039's *unsatisfiable rather than unsatisfied* in its second
instance.

**D1095 closed** in this run, since it touched `docs/api-surface.md` first: the
document has linked `decisions/0050-the-published-surface-is-a-reviewed-
allowlist.md` since Session 5 and no such file has ever existed.
`test_repository_contract` tracks the document for existence and not for its
links, which is why nothing read it. Both links in the header now resolve.

### Run 4 — two readers made honest (ADR 0199)

**Builds.**

1. **D1060, `OPS-READ-001`.** One reader in Python:
   `installed_release.rendered_document(key, *, runtime: bool)` raising
   `RenderedDocumentUnreadable(path, owner)` on `PermissionError` (file or a
   directory on the way) and `RenderedDocumentAbsent(path)` on
   `FileNotFoundError`. `bin/migrate.sh`, `bin/db.sh` and
   `bin/postgres-bootstrap.sh` replace their `[ -f … ] || die 4` with a call
   through `python_bin` that prints the path on success, exits 3 with *cannot
   read <path>: owned by <owner>; run as root, or `sudo chown -R op:op
   .generated`* on unreadable, and 4 with the existing sentence on absent.
   `bin/doctor.py`, `bin/upgrade.py` and `bin/project-retire.py` map the two
   exceptions to 3 and 4. A guard test asserts none of the three shells tests
   `-f` on a rendered document itself (the `test_root_script_policy.code_of`
   reader, comments stripped).
2. **D1048, `OPS-READ-002`.** `outputs.schema.json` `publishedRoute.status`
   enum gains `unobserved` with the same `const` coupling to a null URL;
   `deployed_output.ROUTE_UNOBSERVED`; validation at `deployed_output.py:287`
   accepts three words; `bin/deploy-project.py` records `unobserved` where the
   observation was not made — the first-deploy router race (D326's shape,
   where the deploy prints *"this deploy did not observe it"*), the docs probe
   under a staging certificate (D1047), a timeout — and keeps `unavailable`
   for D230 (no administrator), D326's *no credential* and an observed
   failure; the printed summary and the document use the same word, from one
   function. Readers: `diagnosis.py` reports the word and never folds it;
   `fleet.py` passes it through; `api-contract.py published_address` refuses an
   unobserved route with the remedy (*redeploy so the route is observed*);
   `test_session14_observability.py:214` widens to the three words (recorded
   as a widening to a measured set).
3. `output_migrations.migrate_v16_to_v17` already exists (Run 2); it does not
   rewrite a route word (D1094), and a test asserts a v16 document with
   `unavailable` migrates with `unavailable`.

**Battery.** The Python reader folding `PermissionError` into absent (kill in
the parametrised six-reader test; control: the absent arm still exits 4);
`deploy-project` writing `unavailable` for an unobserved route (kill in
`test_deployed_output`); the doctor folding `unobserved` into `unavailable`
(kill in `test_diagnosis`).

**Targeted:** `test_database_commands`, `test_installed_release`,
`test_deployed_output`, `test_output_migrations`, `test_diagnosis`,
`test_fleet`, `test_api_contract_command`, `test_deploy_project` (whatever the
deploy's contract module is named — `grep -l "deploy-project" tests/contract`),
`test_upgrade_plan`, `test_retirement`, `test_cli_contract`.

### Run 5 — migration 0031, the contract, the documents

**Builds.**

1. `migrations/templates/0031-create-task.sql`, version `20260912120031`,
   exactly ADR 0196's specification: `api.create_task(p_title text, p_note_id
   uuid DEFAULT NULL) RETURNS api.tasks`, `SECURITY DEFINER`, `SET search_path
   = pg_catalog, pg_temp`, `owner_id` from `app.current_user_id()` and never a
   parameter, `PT401` with no identity, `PT404` for a note absent or another
   owner's, `RETURNING` 0007's column list (`id, owner_id, note_id, title,
   description, status, created_at, updated_at`), `REVOKE ALL … FROM PUBLIC`,
   `GRANT EXECUTE … TO {{authenticated}}, {{agent_writer}}`, `GRANT EXECUTE …
   TO {{api_documentation}}` (so the snapshot publishes it), `NOTIFY pgrst,
   'reload schema'`, the header comment stating D1058's correction (the
   runtime identity does *not* work on these tables directly, since 0006), a
   `down` raising `AP900`. `migrations/manifest.json` gains the entry;
   `bin/migrate.sh freeze-lock` re-freezes the release lock (one added entry).
2. `contracts/postgrest-api-surface.yaml`: `create_task: {methods: [POST],
   arguments: [p_title, p_note_id]}` under `rpcs`, with the comment that ADR
   0196 restores what ADR 0048 removed, reviewed rather than inherited.
3. Tests that change **under ADR 0196**: `test_it_states_adr_0003s_domain_as_
   adr_0048_amends_it` (`create_task` now *in* `rpcs`, and the docstring says
   why), `test_the_reader_is_not_vacuous`'s function set gains `create_task`,
   the migration-user module gains `test_create_task_is_reachable_by_the_two_
   writer_roles_and_no_other` (rig 20b's probes as a test), `test_the_status_
   codes_are_the_measured_ones` if it enumerates raises. The release snapshot
   is **not** touched here (D1093: it is captured in Run 7); the control
   fixture was recaptured in Run 1, so `test_api_contract_command`'s control
   tests are green and `test_the_published_set_is_exactly_what_the_snapshot_
   names` plus the four snapshot-dependent command tests are the expected red
   — list their five node ids in the commit message.
4. `bin/api.py` `OPERATIONS` gains `create-task: ("POST", "/rpc/create_task")`
   with `--title` required and `--note-id` optional; `bin/api.sh` usage names
   it (D1097).
5. `README.md`: *Adding your own tables* rewritten around `projects/<slug>/`
   (the manifest key, the three files, `freeze-lock --project`, `api-contract.sh
   --update --project` after the first deploy with the snapshot's path, and the
   sentence that none of the release's files is edited); *What is intentionally
   unavailable* corrected for D1086 (what is unavailable is the agent surface,
   which Session 21 takes, and `tasks` gets a creator here); the ADR 0196
   paragraph rewritten to say the migration shipped. `docs/scope-closure.md`
   §2's `DEP-REMOVE-001` paragraph gets the D860 treatment (passed 2026-09-05,
   gamma-dev) and §8's ADR 0196 row is closed. `docs/migrations.md` gains *A
   project's set*. `docs/api-surface.md` link fixed (D1095).
6. Derived documents: `bin/render-acceptance-matrix.py --write` runs in Run 6
   with the registry; here `bin/app-contract.sh --check` and
   `bin/mcp-contract.sh check` must still pass (the MCP contract names
   `update_task_status`'s operation and nothing here changes it).

**Battery.** 0031's `GRANT … TO {{api_documentation}}` removed (kill: the
reader test that the documentation role holds the surface, if it enumerates;
otherwise a new assertion); the `PT404` branch removed (kill in the migration-
user test, control: `PT401` still raised).

**Targeted:** `test_api_migrations`, `test_migrations`,
`test_migrations_apply_as_the_migration_user`, `test_api_surface_contract`,
`test_api_contract_command` (five expected red, named), `test_api_command`,
`test_cli_contract`, `test_repository_contract`, `test_documented_path` (D693's
guard over README commands).

### Run 6 — the bump

1. `src/agentic_postgres/__init__.py`: `CURRENT_SESSION = 20`, with the
   comment block extended (why 19 is skipped, D1063). `VERSION` → `1.1.0`
   with the ADR 0162 reasoning in the `__init__` comment: a manifest field
   with a default, a migration, a contract entry, an outputs bump with a
   migrator — additive, so a minor is proposed and Run 7's `upgrade plan`
   confirms or stops.
2. `tests/acceptance-registry.yaml`: the seven requirements of §2, `target_
   session: 20`, node ids as written there (adjusted to the names the runs
   used). `evidence_claims.py`: the three claims. `bin/render-acceptance-
   matrix.py --write`; `bin/render-evaluation-report.py --write` if the
   evaluation cases moved (they should not).
3. `tests/deployment/test_session20_tenant.py`: the six live halves of §2,
   `requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS",
   "APG_PROJECT_B_OUTPUTS")`, each docstring saying what only a deployment can
   prove (Session 18's module is the model). The `create-task` proof drives
   `bin/api.sh` under a `dev-token.sh`-minted token the gate already mints for
   other proofs — grep `test_session17_fleet.py` and the Session 17 gate for
   the pattern.
4. `bin/session-20-check.sh` **derived from `bin/session-18-check.sh` by
   diff** (D505, D507, D678, D693, D703): `readonly SESSION=20`, the header
   and usage rewritten line by line (both halves, D853/D858), host mode's
   precondition block replaced — both projects deployed `--through-session
   20` publishing outputs v17, beta's manifest at schema 5 naming
   `projects/example`, 31 release migrations and one project migration in
   beta's ledger — and the four Session 18 declaration flags **removed** from
   this gate's usage (they belong to 18's, which still runs). `SHELL_COMMANDS`
   in `test_cli_contract` gains it.
5. `deploy.sh --through-session 20` is admitted by D59's rule the moment the
   constant moves; nothing else to edit there. `grep -rn "through-session 18"
   README.md docs/*.md` and update every documented line (D693's guard fails
   otherwise).
6. `docs/new-team-member.md` re-derived by diff (D693), a paragraph in
   `docs/tenant-migrations.md`? — **no new document**: `docs/migrations.md`
   §*A project's set* (Run 5) is the reference and the README points at it.

**Targeted:** `test_evidence_claims`, `test_acceptance_registry` (or whatever
guards the registry: `grep -l "acceptance-registry" tests/contract`),
`test_cli_contract`, `test_documented_path`, `test_repository_contract`,
`test_session_gates` (the gate-derivation guards: `grep -l "session-18-check"
tests/contract`). Then `bin/session-01-check.sh` once on the clean tree, and
`pytest --setup-plan tests/deployment/test_session20_tenant.py` with the three
variables set to the fixture documents (D671, D676).

**Push.** The branch's CI is expected red on exactly the five snapshot tests
(D1093). Record the run id and the five names in this run's Done paragraph.

### Run 7 — the trip, and the sitting that ends in a deploy

Before the day: `grep -n "goes wrong" -A20` in the Session 11, 17 and 18
operator guides and plans (D977); `pytest --setup-plan` for every deployment
module with the variables set; the transport script `/tmp/r7-transport2.sh`
in WSL still works and takes a SHA (edit it, do not retype it); the CI watcher
`s19-ci-watch.sh` in the scratchpad with `SHA=` edited.

Then, in order, **the operator at a TTY runs anything with `sudo`** and pastes
the output; the agent reads, never redirects a deploy (D972):

1. Bundle the branch's bump commit, `scp`, `git bundle verify`, fetch,
   `git rev-parse FETCH_HEAD` confirmed, checkout as `op`, `uv sync`.
2. As root: `bin/upgrade.sh check --project alpha-dev` and `plan`; the same
   for beta. **Record the plan's bump class** (D1081): a `minor` confirms
   1.1.0; a `major` required is §9's stop.
3. `project.beta.yaml` on the host → `schema_version: 5`, `migrations: {set:
   projects/example}` (the operator edits it; the render validates it with
   `./deploy.sh --project project.beta.yaml --capabilities capabilities.yaml
   --render-only` as op first). Alpha's manifest stays at schema 1 — the
   control that a v1 manifest still deploys under a schema-5 release (D930).
4. Deploy alpha `--through-session 20`, unredirected. Read: 0031 applied
   (`migrate.sh status` **and** the cluster's ledger, never the summary line,
   D941), outputs v17, every route `ready`, the doctor 10/10 with the
   migration check counting 31. Then beta: 31 + 1, `api.note_embeddings`
   served, the doctor reading the project set.
5. **Capture**: `sudo bin/dev-token.sh --project-outputs <alpha> --role docs --
   bin/api-contract.sh --update --project-outputs <alpha> > /home/op/release-
   candidate.json`; the same for beta with `--project project.beta.yaml`, into
   the path the command prints. Copy both to the workstation, `diff` the
   release candidate against the committed snapshot (exactly `rpc/create_task`)
   and review beta's, commit both to the branch, push, **CI green** on that
   SHA. Merge fast-forward to `main`, push, delete the branch.
6. `sudo chown -R op:op .generated` — **but first**, as op, `bin/migrate.sh
   --project project.alpha.yaml render` against the root-owned directory the
   deploy just left: exit 3 with the unreadable message is `OPS-READ-001`'s
   live reading; paste it.
7. Transport the merge commit, check out `main` on the host, `uv sync`; gates:
   `bin/session-01-check.sh`, `bin/session-20-check.sh --mode offline`, `--mode
   host` (root, the documented arguments), `--mode external` from the
   workstation (D466); `--mode host` for Session 18's gate too, because the
   inherited claims are cumulative; merge the evidence documents;
   `evidence/session-20.json` with its claim table pasted into this run's Done
   paragraph.
8. `create-task` through `bin/api.sh` on alpha as the gate's proof (`API-TASK-
   001`), and `update-task-status` on the row it made — the compare-and-swap's
   first run against real data.
9. **The second-walk rehearsal, offline, on the workstation**: a fresh agent
   context, given only the merged `README.md` and `docs/migrations.md`, adds a
   table, a view and an RPC as a project set to `project.second.example.yaml`'s
   fixture and renders it, recording every file it touched. The record is
   pasted here as a reading; **the claim does not move** (D1091). Any release
   file the walk touched is a D row and a Session 25 item.
10. D rows for what the day found, this run **Done.**, `CLAUDE.md` §2 and
    §9, memory, commit, push, CI.

---

## 7. Evidence and claims

| Claim | Offline may report | Needs a live half for |
|---|---|---|
| `tenant_extension_point` | The example set rendered after the release's in version order; the project lock frozen and verified apart; the lint's refusals with the example set as control; the merged surface and the project reader; v17's migrator; the doctor counting two sets from a fixture root | Beta's deployed document at v17 naming the set; the ledger holding its row; `api.note_embeddings` served on beta and absent on alpha; the doctor's check on the host |
| `task_domain` | 0031's reader properties; the migration-user proof of grants and `PT401`/`PT404` on a throwaway cluster | A task created through `bin/api.sh create-task` on alpha and moved by `update-task-status` |
| `honest_readers` | The six readers' exit codes against a `chmod 000` directory and an absent one; `unobserved` written, migrated and reported in fixtures | `migrate.sh render` as op after a root deploy; no route `unobserved` after a redeploy on either project |
| `fresh_host` (12) | — | `APG_FRESH_HOST_OUTPUTS`, the operator's (ADR 0197); untouched here |
| `documented_path` (12) | The commands the path names exist (standing, D693) | Session 25's walk; **not this session's rehearsal** (D1091) |

The five other `not_run` claims stay so (D478). No claim spans both modes; a
skip is not a pass; the branch's expected red is on tests, never on a claim.

---

## 8. Security invariants this session touches

| Invariant | Control | Proof |
|---|---|---|
| PostgreSQL is the final authorization authority | A project table in `app` must carry `FORCE ROW LEVEL SECURITY` or the lint refuses the set; views are `security_invoker`; RPCs derive the owner | `TEN-SET-002`; the example set's own policy |
| A project set cannot reach the platform's state | The lint: no `app_private`, no role, schema, extension or default-privilege statement, no `SET ROLE` but the owner preamble, no drop or alter of a release object; placeholders from the allowlist only | `TEN-SET-002` |
| Nothing exists in `api` the reviewed surface does not name (ADR 0050) | The project reader over the project's set against the project's contract; the merged surface for every snapshot comparison; a release name cannot be redeclared | `TEN-SURF-001` |
| The rendered payload is the immutable unit (ADR 0028) | Two locks, each verified before any render or apply; the release lock never rewritten by a project verb | `TEN-SET-001` |
| A release is exactly its commit | The set lives in the checkout; `assert_clean` unchanged | D1087 |
| `create_task` cannot name an owner | The parameter list is `(p_title, p_note_id)`; the owner is the GUC's | `API-TASK-001` |
| A report may not substitute an answer for a failure to determine one (ADR 0195) | Six readers distinguish unreadable from absent; three route words; the migrator never guesses | `OPS-READ-001`, `OPS-READ-002` |
| The migration user reaches owner authority only by `SET LOCAL ROLE` | Unchanged; the project set runs as the same role through the same plane | `test_migrations_apply_as_the_migration_user` over both sets |
| No secret value in a template, lock, ledger or rendered file | The placeholder-name refusals in the manifest schema apply to a project set unchanged | `test_migrations`' existing refusals, run over the example set |
| The MCP runtime holds no credential; the agent plane is unchanged | Session 21's subject; this session adds no capability, no scope, no tool | `bin/mcp-contract.sh check` green at every commit |

---

## 9. Stop conditions

Stop and ask when:

- **rig 20a shows dbmate applies an older pending migration behind an applied
  newer one silently**, or refuses it in a way the rule in D1092 cannot state;
  the version rule is then decided with the operator, not written around;
- **rig 20c's diff is anything but `rpc/create_task`** — the control fixture
  is not recaptured, and the reason is a row;
- **`upgrade plan` on the host prices the change at major** (step 2 of Run
  7): `VERSION` becomes `2.0.0` only by a decision recorded with the plan's
  own output, and the ADR 0162 reasoning in `__init__.py` is rewritten first;
- the lint would need a `raw` placeholder type, a `--force`, or an allowlist
  loosened to a pattern to let the example set through;
- a project set would need to touch `app_private`, a role, or the pre-request
  hook to do something an adopter reasonably wants — that is a product
  decision for a later session, recorded, not a lint exception;
- the migrator would need to rewrite a route's recorded word (D1094);
- CI on the branch is red on **any test other than the five named** in Run 5's
  commit message;
- the beta deploy fails after 0031 applied and before the project set did —
  fix forward on the host with the operator, never `down`;
- a currently-passing test would be weakened, or an equality turned into a
  containment check — **D1089 is the row that says this session does not need
  to**;
- `--render-only` stops working with no host and no root, on a manifest with
  or without a set.

---

## Appendix — what to consult, and how a run is executed here

**Consult, in this order.** `docs/plans/stage-3-plan.md` §1 rows D1082, D1083,
D1067, D1080, D1081, D1086 and §5 *Session 20*; this document's §1;
`docs/plans/session-19-implementation-plan.md` §1 (D1036–D1040, D1053–D1056,
D1058, D1060); ADR 0028, 0050, 0162, 0195, 0196, 0197; `FINDINGS.md` F-002,
F-004 to F-008, F-021 to F-023; `docs/plans/session-05-implementation-plan.md`
Run 9 (how the control fixture was captured from a throwaway cluster) before
rig 20c; `docs/plans/session-18-implementation-plan.md` §5 Run 6 and
`docs/session-11-operator-guide.md` §2 before Run 7.

**How a run is executed in this repository** (the short form of `CLAUDE.md`
§1 and §5; read those, they are the record of what each of these cost):

- The Bash tool is Git Bash on Windows. The tree is in WSL:
  `wsl bash -lc "cd ~/projects/agentic-postgres && . .venv/bin/activate && …"`.
  Anything with nested quotes, `$VAR`, a heredoc or a loop variable goes in a
  script written with the Write tool to `\\wsl$\Ubuntu\tmp\x.sh` and run with
  `wsl bash -lc "bash /tmp/x.sh"`, printing its own exit codes.
- File content and commit messages are written with the Write tool and read by
  the script (`git commit -F /tmp/msg.txt`). Never a heredoc for content.
- `chmod 755 bin/*.sh bin/*.py deploy.sh` before every `git add`; writing
  through `\\wsl$\` strips the executable bit and the index mode is a contract.
- Never pipe a suite or a gate into `tail`; redirect to a file, `rm` it first.
- `PYTHONDONTWRITEBYTECODE=1` and `__pycache__` cleared before a battery.
- A run's commit: `ruff format && ruff check` (print the exit code), the
  targeted modules, the derived-document generators whose inputs moved,
  `chmod`, `git add -A`, commit with `-F`, push to `session-20`, then read that
  SHA's verdict: `gh api "repos/Virabyan99/agentic-postgres/actions/runs?head_
  sha=<40 chars>" --jq '.workflow_runs[] | [.id,.status,.conclusion] | @tsv'`,
  judged on HTTP status, with `success` / `cancelled` / anything else as three
  buckets (D1059). An empty listing is not a verdict until the workflow's
  triggers have been read (D1057).
- Documentation-only commits run nothing before push. Code runs the targeted
  modules; CI is the full check. The gate (`bin/session-01-check.sh`) runs on
  a clean tree at Run 6's close and before the trip, never at a run's close.
- A rig is a throwaway script with a control arm, its output in a file and its
  numbers pasted into the Done paragraph. Never write a measurement you did
  not run (D267). Delete what a rig publishes under `.generated/` unless the
  key already existed.
- The battery: every mutation's anchor pre-flighted to match exactly once and
  a miss fatal (D269); a paired control the mutation cannot reach, in the same
  invocation, green (D499); the reader distinguishes `FAILED` (a kill) from
  `ERROR` (a broken fixture) (D386); restore by copy and `cmp`, never
  `git checkout --`.
- The host: `op` over SSH with `-i ~/.ssh/agentic_postgres_ed25519` for reads,
  renders and offline gates; anything reaching Docker or `sudo` is the
  operator at a TTY, and the agent reads the pasted output. Never redirect a
  sudo deploy (D972). Never retry ACME. `apg-diag` verbs for read-only
  diagnosis as `apg-agent`.

**Grep the plans before measuring a third party.** dbmate: D57, D60, D262,
D941, D1053; PostgREST's OpenAPI and `follow-privileges`: D158, D274, ADR 0060,
ADR 0118; the outputs migrator's hand-chained tests: D965; the isolation
matrix's classification: D702, D1029; the snapshot capture: Session 5 Run 9,
D1039. Nothing indexes the ~1,097 measured facts by subject; `grep` is the
index.
