# Session 22 — `apg dev`, the local disposable environment

**Status:** planned 2026-09-11 at `90c1c19`, Session 21's close. **Run 1 done
2026-09-11** on branch `session-22` (rigs 22a–22e, ADR 0202, ADR 0203,
D1176–D1179); Runs 2–7 open.
**Brief:** `docs/plans/stage-3-plan.md` §5 *Session 22*, and its rows D1066
(the fixture path is the product), D1071 (`seed` is a reviewed file, never a
capture), D1073 (CI is the PR environment), D1076 (isolation is proved by
construction), D1079 (churn goes in the envelope), and §7's decision that
Session 22 takes: **the first offline-only claim this evidence model has ever
had**. Plus the five items Session 21 left with their repairs named: D1151,
D1153, D1154, D1155, D1156 (`docs/scope-closure.md` §10).
**Shape:** seven runs, all offline, all green in CI on a `session-22` branch.
**There is no host trip.** Run 7 is the close: the offline gate on this
workstation, the offline evidence half, the handoff, the merge to `main`. The
two host claims this session registers (§2) are measured at Session 24's trip,
and this plan says so wherever it matters (D1163, §7, §10).
**Product version at close:** `CURRENT_SESSION` 22; `template_version`
proposed `1.3.0` (a new operator command, an optional project directory, one
additive project-set migration — a minor under ADR 0162; confirmed by the
next host's `upgrade plan`, which is Session 24's).
**Written for whoever picks this up cold.** Every path is exact; every third
party is measured in Run 1 before anything is built on it; the appendix says
how a run is executed in this repository. Read `CLAUDE.md` §1 in the launch
folder before the first command. **Read this plan's §1 before Run 1**: three
of the stage plan's sentences about this session are wrong in the reassuring
direction (D1157, D1158, D1163), and Run 1's rigs exist to settle them.

---

## 0. Where the session starts

Session 21 opened the agent plane to a tenant's domain (ADR 0200, ADR 0201).
`evidence/session-21.json`: 108 claims, 99 passed, 9 not_run, 0 failed at
`f61f716`. Both projects on the host are deployed at `f61f716` (outputs v18,
doctor 10/10); the host checkout is `f61f716`; `90c1c19` is documentation
only and was not transported. Session 22 transports nothing.

**What the developer loop is today, measured at `90c1c19`.** A developer who
wants a cluster with this release's schema on it has exactly one path: run a
contract test module. Six modules each stand one up with their own
`cluster()` fixture (`tests/contract/test_migrations_apply_as_the_migration_user.py:91`
and five others, D1158); one of them applies the product's own bootstrap
(`bin/postgres-bootstrap.py::build_statements`) and every migration as the
migration user; the other five apply as the superuser, and one reimplements
the bootstrap by hand and stopped a statement short (F-005, its own comment
at `test_auth_endpoints.py:170`). Measured on 2026-09-10 (stage plan D1066):
the migration-user module stands its cluster up and applies every migration
in **~10 s** on this workstation, against **247 s** for a restore from the
mirror on a replacement host (D1028). Nothing in `bin/` gives a developer
that cluster. Nothing seeds one. And nothing an adopter can run before their
first deploy tells them whether their migration set applies as the role that
will apply it — which is D285's class, the defect that took a live project
down in Session 6, one layer up.

**What this session builds, in one paragraph.** `bin/dev.sh` (reached as
`bin/apg.sh dev`, by construction — the dispatcher holds no list) with six
verbs: `up` stands a cluster up on the locked image by digest, applies the
product's own bootstrap statements, applies the **rendered** migration
payloads (the bytes dbmate applies, verified against the rendered manifest)
as the migration user in version order, writes `schema_migrations` and
`migration_ledger` the way the deploy does, activates two roles with
generated passwords in `0600` files, and registers one development subject
through the product's own `auth_create_user`; `status` reports three
outcomes; `down` removes the container, its anonymous volume and the state;
`reset` is `down` then `up`; `seed NAME` applies a named, hash-verified,
linted SQL file from `projects/<slug>/seeds/` as the migration user with the
subject asserted; `psql` execs a shell into the cluster as the application
role with the subject asserted. The environment holds no network but the
default bridge, no mount, no name from the secrets contract, publishes its
port on `127.0.0.1` only, and reads nothing from `/var/lib` or `/etc` — which
is D1076's proof by construction, with the rendered Compose model as the
control. Churn is measured and published in the envelope. CI runs the round
trip, which is what a PR environment is here. The evidence model gains a third
mode, `offline`, for **declared** claims only (ADR 0202); the gate writes the
offline half; CI writes it too. And the five things Session 21 left are
repaired first, in Run 2, so nothing new inherits them.

**What it does not build, by decision** (§1 D1157, ADR 0203): PostgREST, the
auth service, a JWT, a token verb. A subject-less token reads no owner's rows
(`bin/dev-token.py`'s own docstring); a subject needs the auth service; the
tables' policies read `app.user_id` (migration 0003), which the pre-request
hook sets from the token — so a REST loop on a workstation is three
containers plus the production key flow, and that is the production stack
minus Traefik. Session 23's generated client and Session 24's loopback Studio
each decide what they need on top of the database; this session gives them
the database.

**Read before touching anything:** ADR 0002 (derive an identity once), 0013
(`compose.sh`'s privilege gate — and why this session does not use it), 0026
(the migration user reaches the owner by `SET LOCAL ROLE` only), 0028 (the
rendered payload is the immutable unit), 0030 (a bootstrap plane removes
nothing), 0045/0089 (what a claim is), 0065/0066 (a rig is a second
configuration of the product), 0067 (the bootstrap's statement list is
tested on both sides of its boundary), 0148 (the connection budget the
bootstrap issues), 0163 (three statuses), 0195 (three outcomes, the third
reported), 0198 (a project owns a set), 0199 (one resolver, exit 3/4/5),
0200/0201 (the vocabulary and the roster); D105 (nothing prints a token),
D285, D292/ADR 0093 (an operator command imports only what the host has),
D1060, D1066, D1071, D1076, D1098, D1110, D1131.

---

## 1. The divergence table

Six columns, next free number after this table **D1200**. Rows D1157–D1175
were measured at planning on 2026-09-11 at `90c1c19`; the runs add theirs
below them as they go, each run's numbers named in its Done paragraph. Run 1
added **D1176–D1179**, measured in rigs 22a–22e on 2026-09-11 at `dd9e2be`;
Run 2 added **D1180–D1184**: three found by building, one by the battery, and
one by a RED CI on its first push. Run 3 added **D1185–D1188**, three of them
found by a test going red during the move it describes. Run 4 added
**D1189–D1191**, the first of them a defect two sessions old that only a
proof trying to READ could find. Run 5 added **D1192–D1193**, one a guard that
could not be observed where it was being asserted and one a rig that reverted
its own run's work. Run 6 added **D1194–D1198**, and every one of the five is a
GUARD rather than a product defect; Run 7 added **D1199**, a line in Run 6's
own gate that nothing had executed until the session's close ran it — an anchor that stopped matching, an
allowlist one machine short, a scan that asked a dispatcher about a flag it
delegates, and an assertion that two different mutations walked through.

| # | Said | Repository does | This session | Why | ADR |
|---|---|---|---|---|---|
| **D1157** | Stage plan §5 Session 22: *"a short-lived local JWT signed by a throwaway key that exists only for the environment, and the developer's own PostgREST and auth service if the loop needs them — measured first whether it does."* | **A token alone reaches nothing a developer wants.** `bin/dev-token.py`'s docstring: *"a token from here can reach the surface and can read no owner's rows"* — the issuer names a role and the auth service names a subject (ADR 0095); migration 0013's pre-request hook compares a subject against `app_private.users`; and the tables' policies read `app.user_id` (`0003:13-19`, `notes_owner_select … owner_id = app.current_user_id()`), a GUC the hook sets from the claims. So a REST loop needs PostgREST **and** the auth service **and** a registered subject: three containers and the production key flow. The contract suite's PostgREST rig (`test_api_behaviour.py:220`) exists and is a rig, not a product. | **The environment is the database.** No JWT, no PostgREST, no auth service, no `token` verb. The developer's loop is `apg dev psql` (the application role, `app.user_id` preset to the development subject through `PGOPTIONS`, measured in rig 22b), `apg dev seed`, and any client on the loopback port. PostgREST on a dev cluster is Session 23's first measurement if its generated client needs one; Studio is Session 24's. ADR 0203 records the boundary. | The stage plan's *"if the loop needs them"* was the right question and the tree already answers it: the loop the plan imagines needs all of them or none. Building the stack minus Traefik as a second Compose model is the thing ADR 0013 and ADR 0065 both refuse — a second way to start the product's containers, unaudited. | 0203 |
| **D1158** | Stage plan D1066: *"the contract suite's `cluster` fixture"*, singular; §5: *"the fixture path as a product"*. | **Six fixtures, not one.** `cluster()` is defined in `test_storage_plane.py:77`, `test_migrations_apply_as_the_migration_user.py:91`, `test_auth_service_reaches_its_data.py:78`, `test_storage_service_reaches_its_data.py:72`, `test_agent_audit_plane.py:107`, `test_auth_endpoints.py:117`. Only the migration-user one applies `build_statements()` and applies as `migration_user`; `test_auth_endpoints`' applies as the superuser and reimplements the bootstrap by hand (its own comment, F-005). None writes `schema_migrations` or `migration_ledger`. | **The product path is extracted from the migration-user fixture** into `src/agentic_postgres/dev_environment.py` (pure: argv, statements, state; no subprocess) and `bin/dev.py` (the Docker work), and **that fixture is pointed at the module** in Run 3 — the proof that the product path is the fixture path. The other five stay as they are, recorded in §10: each is a rig with reasons of its own (a superuser is what they need to plant state), and rewriting five rigs is not this session. | *"The fixture path"* is a family, and the one worth productising is the one whose defect class (D285) a developer meets first. | 0203 |
| **D1159** | Stage plan §5: *"the release's migrations and the project's set (20) applied by the migration user"*; the fixture re-renders every template from `sets_for(document)`. | **The rendered payload already exists and is what the deploy applies.** `.generated/<key>/migrations/` holds every rendered file (32 for `fixture-alpha-dev`: 31 release + 1 project) beside `rendered-manifest.json` (`rendering.MIGRATION_MANIFEST_NAME`, `rendering.py:2089`) with a digest per file; `bin/migrate.py::assert_rendered_files_match` verifies files against that manifest before dbmate reads the directory; `record_ledger` (`migrate.py:191`) writes `app_private.migration_ledger` as the superuser after `up`. Both live in `bin/`, unreachable from `src/`. | **`apg dev` applies the rendered files**, verified by the same check, and writes both ledgers — `schema_migrations` (what dbmate writes, one row per version, inside the migration's own transaction) and `migration_ledger` (what `record_ledger` writes). The verifier and the ledger statement move to `migrations.py` (`verify_rendered_directory`, `ledger_insert_statement`); `bin/migrate.py` calls them and its two functions keep their names and arities (ADR 0175). Readers grepped in Run 3. | A dev cluster whose ledger has production's shape is one `migrate.sh status` can read the same way; a dev cluster built from re-rendered templates is a second render nobody compares. | — |
| **D1160** | Stage plan §5 *Must not*: *"hold … any production secret on a workstation"*; §0 of this plan's brief reads it as *"no credential"*. | **A connection needs a password.** The migration-user fixture generates one per cluster and hands it to `psql` through `docker exec -e PGPASSWORD=…` — which puts the value in the **host's** `docker` argument vector, readable in `ps` (the construction `test_root_script_policy.py` scans `bin/` for). Nothing in `bin/` may do that. | Two generated passwords per environment (`migration_user`, `app_runtime`), each in a `0600` env file under `.generated/.dev/<key>/`, handed to `psql` through `docker exec --env-file` (measured in rig 22a) — the shape of the host's materialised secrets, never printed, never an argument. *"No credential"* means no **production** credential: no repository key, cipher pass, provider token or deployed document. | The rule is D105's: a credential that appears in an argument vector, a scrollback or a log is a credential in a support ticket. | 0203 |
| **D1161** | D1076: *"one test that the environment's container joins no backup network, mounts no `pgbackrest.conf` and holds no facility-gated secret (ADR 0191's `active_secrets(..., facilities=)` answers it)"*. | `docker run` with no `--network` joins the default bridge; the pinned postgres image declares `VOLUME /var/lib/postgresql`, so an **anonymous volume appears in `Mounts`** — a proof asserting *no mounts* would be wrong on a correct environment; `docker rm -f` leaves that volume behind unless `-v` is given (rig 22a measures both). `active_secrets(contract, session, facilities=)` narrows to a project's facilities; the environment has none, so the right question is whether **any** name the contract declares (every facility) appears in the container's environment or the state directory. Control: the rendered model puts `postgres` on `["internal", "backup"]` and mounts `pgbackrest.conf` (`test_compose_contract.py:324`). | The isolation proof (Run 3) asserts: `Networks` keys are exactly `{"bridge"}`; no bind mount and no mount destination under `/etc/pgbackrest` or naming `pgbackrest.conf`; `Env` and the state directory's file names contain no secret name from `secrets_contract.active_secrets(contract, CURRENT_SESSION)` (the declared view, every facility); `SHOW wal_level` is `replica`; the published port's `HostIp` is `127.0.0.1`; and the control, read in the same test through the same Compose helper `test_compose_contract` uses. `down` runs `docker rm -f -v`. | A claim that a thing *cannot* reach the chain is a property of where it runs; a proof written against an imagined container shape (no mounts) would be red on a correct environment and green on nothing. | 0203 |
| **D1162** | Stage plan §7: *"An offline-only claim exists (Session 22), with `claim_mode` taught the third mode and `merge` accepting a document with no host half for that claim only."* | **Refused at four points, one of them a contract test.** `MODE_MARKERS = {"host", "external"}` and its comment says `offline` is absent on purpose (`evidence_claims.py:45`); `claim_mode` raises *"has no live proof"* for a claim with no marker (`:761`); `test_a_claim_with_no_live_proof_is_refused` (`test_evidence_claims.py:254`) is a contract test, which the non-negotiables say changes only with an ADR; `write_half` requires `--project-a-outputs` and takes `source_commit` from the deployed document (`write-session-evidence.py:101,127`); `merge` takes host and external only and refuses a claim neither recorded (`:214`). The 21 unclaimed requirements are enumerated in `UNCLAIMED_BY_HISTORY` (`:1081`). | **ADR 0202**: a third mode whose claims are **declared**, never inferred — `OFFLINE_CLAIMS: frozenset[str]` in `evidence_claims.py`; `claim_mode` returns `offline` for a declared claim with no marker, still raises for an undeclared one (so the 21 are not retrofitted, D696), and raises for a declared one that carries a marker; the offline half is written from a checkout with `checkout_commit` from `git rev-parse HEAD` and no deployed document; `merge` takes `--offline-input`, required iff `claims_for_mode("offline", session)` is non-empty; the merged document carries `offline_checkout_commit` beside `source_commit`, `MUST_AGREE` does not cover it, and the writer prints when they differ. The contract test is replaced by a stricter pair (Run 5). | A claim about a checkout is a different kind of claim, and the model should say which kind each one is rather than let a marker's absence decide. | 0202 |
| **D1163** | Stage plan §7 table: Session 22 *"Ends on a host? No"*, and *"offline-only by nature"*. | A **merged** `evidence/session-22.json` needs a host half: `claims_through_session(22)` carries every live-halved claim through 21 and `merge` refuses a claim neither half recorded. And two of this session's own repairs are only measurable on a deployment: D1156's grant (a project-set migration applies at a deploy) and D1153's plane-confirmed count (a deploy-time observation). | **Session 22 closes on its offline half alone** — `evidence/session-22-offline.json`, written by `bin/session-22-check.sh --mode offline` and by CI. Its two host claims (`agent_tenant_read`, `plane_confirmed_count`, §2) are registered now with live proofs gated on the roster variables and are measured at Session 24's trip, whose plan must: deploy `--through-session ≥22` so the example set's second migration applies on beta; run the Session 22 gate's host and external modes; merge three halves. §10 and `CLAUDE.md` §2 say so. | *"Offline-only by nature"* describes the DEV claims and not the session: a session that repairs a deployment defect owes that deployment a live proof, and the honest record is a half that says which half it is. | 0202 |
| **D1164** | D1154: *"something earlier in the sweep, running as root, renders or replaces `.generated/alpha-dev` and does not hand it back … Which step it is was not isolated on the day."* | **A candidate, read from the tree:** `tests/deployment/test_session13_upgrade_plan.py`'s `candidate` fixture (`:150-190`) runs `./deploy.sh --render-only` on the **installed** manifest of a real project during the live sweep, as root; `rendering.publish` replaces the directory (`os.replace`, `rendering.py:2058`); the fixture removes what it published **only if it created it** (`ours = not published.exists()`), so an op-owned directory that existed before becomes root-owned and stays. Consistent with the 12:27 mtime (the sweep's first minute; the module collects early). `_restore_checkout_ownership` lives in `bin/deploy-project.py:218` and only the deploy calls it. | The helper moves to `rendering.restore_checkout_ownership(path)` and **`render_project` calls it itself** after `publish` when `SUDO_UID`/`SUDO_GID` are set — so every render under `sudo`, from any caller, hands back; the deploy keeps calling it (same function, same behaviour). Confirmed live at Session 24's trip by reading owner and mtime before and after the sweep (§10). Offline proof in `test_render_atomicity.py`: `os.chown` recorded under a monkeypatched `SUDO_UID`, and not called without it. | The deploy was repaired for D1110 and the renderer was not; a render is a render whoever calls it. | — |
| **D1165** | D1155: `test_honest_readers.py:100` and `:165` skip under root (*"root traverses a 0000 directory"*); the gate runs its static claim proofs as root. | Both proofs `chmod 000` a directory and read through it as the caller. D1131 already gave the live half the right shape: when `geteuid() == 0`, re-run the reading as the checkout owner with `sudo -u`, construct and restore the state, assert the restore (`tests/deployment/test_session20_tenant.py::test_render_as_the_checkout_owner_of_a_root_owned_directory_says_unreadable_not_absent`). | The two offline proofs take D1131's shape (Run 2): under root, the reading is made as the checkout owner (`pwd.getpwuid(os.stat(REPO_ROOT).st_uid)`) through `sudo -u`; the skip is gone. Node ids unchanged, so `OPS-READ-001` and `honest_readers` are untouched in the registry; the claim passes at the next sweep. | A proof that skips under the identity the gate runs as is a proof the gate can never record (D1121, both halves now). | — |
| **D1166** | D1153: `mcp.tool_count` *"what the deployment SERVES, read from the compiled lock"*; the doctor's *capability drift* check. | `observe_mcp` (`deploy-project.py:1500`) takes `tool_count` from the lock **file** and asks the container only three constants through `AGENT_PLANE_PROBE` (`:1584`); the doctor compares disk to document. For eight minutes on 2026-09-11 both said 7 while the plane served 6 (D1152). | The probe reports two more values — the loaded lock's `tools_sha256` and its tool count, read from a module-level record the runtime does not yet keep: `mcp_runtime.py:387` binds `lock = load_lock(settings.capability_lock_file)` as a local inside its factory (measured), so Run 2 adds `LOADED_LOCK` set once at that line and guarded by a test in `test_lock_roster.py`. `observe_mcp` publishes `tool_count` **only when the container's digest equals the file's**; otherwise `tool_count: null` and a printed line naming both digests. No outputs schema move (the field is already nullable in the unavailable block). The doctor's tenth check reads the container's digest through the same probe and reports a third outcome when the container cannot answer. Offline proofs against recorded probe output (agree, disagree, unreadable) in `test_deploy_command.py` and `test_diagnosis.py`; live half `test_session22_plane.py`, Session 24's trip. | A report that reads the file and speaks of the plane is ADR 0195's substitution; the container already answers one line of Python, so the honest value costs one more field in that line. | — |
| **D1167** | D1156: the example set grants its view and RPC to `{{authenticated}}` and `{{api_documentation}}` only; an agent holding `note_embeddings:read` is refused upstream. Ledger §10: *"Session 22's first item"*. | The release grants `api.notes`/`api.tasks` to `{{agent_reader}}` and `{{agent_writer}}` (`0004:34`, `0007:151,270`); the example set does not (`projects/example/migrations/templates/0001-note-embeddings.sql:115-127`). `PROJECT_PLACEHOLDER_SOURCES` (`migrations.py:88-98`) already admits `database.roles.agent_reader` and `database.roles.agent_writer` — measured, so no allowlist moves. The set's lock records `follows_release_version` `20260904120030`; a second migration must sort after it and after `20260914120001`. | **Fix forward, Run 2**: `projects/example/migrations/templates/0002-agent-grants.sql`, version `20260914120002`, `GRANT SELECT ON api.note_embeddings TO {{agent_reader}}, {{agent_writer}}` and `GRANT EXECUTE ON FUNCTION api.set_note_embedding(uuid, extensions.vector) TO {{agent_writer}}`, the owner preamble, a `down` raising `AP900`; manifest entry with the two placeholders; `bin/migrate.sh --project project.example.yaml freeze-lock`. The snapshot does not move (the capture reads as `api_documentation`, whose grants are unchanged). Offline proof in `test_migrations_apply_as_the_migration_user.py` (the cluster that applies both sets): `has_table_privilege` / `has_function_privilege` true for the agent roles, false for `{{anon}}` as the control. README §*Giving an agent your tables* gains the sentence that the grant is the adopter's and the scaffold cannot see it. Live half (`AGT-TENANT-002`, `agent_tenant_read`): a read through `query_resource` over `note_embeddings` on beta returns rows — Session 24's trip. | The tenant surface was proved by discovery and by a refusal; the door is proved by a read. | — |
| **D1168** | Stage plan §5: *"Churn measured and published in the envelope (D1079) against the ~10 s baseline (D1066)"*; *"twice, image cached and not"*. | `capacity.ENVELOPE` is pinned to three images including `POSTGRES_IMAGE`; a `Measurement` of kind `MACHINE` must name the machine in its conditions (`test_a_machine_measurement_names_the_machine_it_describes`, `test_capacity_envelope.py:96`). The locked image is shared by the six cluster fixtures; *"not cached"* on this workstation means `docker rmi` of the image the whole suite uses. | Two `MACHINE` rows in Run 6: `apg dev up` and `apg dev reset` wall time on this workstation (WSL2, image cached, twice) and in CI (`ubuntu-latest`, the numbers read from the log of the run that adds the step, where the image is **not** cached — D1169's step prints them). One `UNMEASURED` row for the uncached workstation case (unblocked by a `docker rmi` nobody runs mid-session). `render-capacity-envelope.py --write`; `--check` in the gate. The baseline it is measured against is the migration-user module's own duration (`--durations=0`), twice, in rig 22d. | A number carries the conditions it was sampled under or it is not a number (D593). | — |
| **D1169** | D1073: *"a PR's environment is `apg dev` inside CI — the cluster, the migrations, the generated client's tests, the harness — with no host, no route, no teardown to forget."* | `ci.yml`'s `session-2-contract` job has Docker and renders the fixture before the suite (D877); nothing in it stands the product's own environment up. | A step after the render: `bin/apg.sh dev up --project project.example.yaml`, `dev status`, `dev seed --project project.example.yaml example`, `dev reset`, `dev down`, each timed with `date +%s.%N` arithmetic printed to the log (the CI numbers D1168 reads). A guard in `test_dev_environment.py` reads the workflow text for the five verbs in that order (the shape `test_ci_installs_the_shellcheck_the_gate_pins` uses). And the gate job writes `evidence/session-NN-offline.json` for the current session (D1162's third half) from step 4's JUnit, uploaded with the artifacts. | The runner is the one place the isolation the spec wants comes free. | — |
| **D1170** | Stage plan §5: *"`apg dev seed FILE`: a reviewed fixture file, hash-verified like `db.sh sql`"*. | `bin/db.sh sql` takes a **NAME** from a fixed allowlist, never a path; the digest is compared against the manifest that named the file; there is no flag that relaxes either. A `FILE` argument is the door that command was built not to have. | `apg dev seed NAME --project FILE`: the name is looked up in `projects/<slug>/seeds/manifest.json` (`schema_version: 1`; `seeds: [{name, file, sha256, description}]`; `file` a basename under `seeds/`, no separator, no `..`); the file's digest must equal the recorded one (exit 5 otherwise); the text is linted with the set's forbidden statements **plus every DDL verb** (`lint_seed`); rendered through `migrations.render` with the set's declared placeholders; applied in one transaction as the migration user with `app.user_id` set to the development subject first and the owner preamble as its first statement; a seed already recorded in the state is refused (exit 2, *"reset first"*). The example project ships `seeds/example.sql`. | The door is the same door, and the reason it takes a name is the same reason. | 0203 |
| **D1171** | Stage plan §5: *"a developer-written seed"* — and nothing about whose rows it writes. | Every owner-scoped table's policy reads `app.user_id`; `app.notes.owner_id` holds a claim value with no FK (`0011:178` comment), but agents, storage objects and sessions reference `app_private.users`; the product creates a subject only through `app_private.auth_create_user(username, display_name, role_name, scopes, password_hash)` (`0012:170`), whose verifier row has `CHECK (password_hash LIKE '$argon2id$%')`; `role_name` is the **full** derived role (the service's `_role_name(role_suffix)`, Run 2 reads it); `scopes` is a sorted, deduplicated `text[]` (`is_scope_set`); and an operator command may import only the standard library, `agentic_postgres` and `yaml` (`test_operator_commands_run_on_the_host.py`, `HOST_PACKAGES`) — no `argon2`. | **`up` registers one subject `dev`** through `auth_create_user` as the superuser: `role_name` = the document's `authenticated` role, `scopes` = `scope_registry.vocabulary(merged surface)` sorted (the whole data class the surface derives — what the issuer's ceiling would admit), and `password_hash` a **well-formed argon2id encoding of random bytes with no password behind it** (`$argon2id$v=19$m=65536,t=3,p=4$<22 b64>$<43 b64>`): a verifier for no password, because the environment has no login path. Its id goes in `state.json` (not a secret); `seed` and `psql` assert it through `app.user_id`. Measured in rig 22b. | The subject is what makes a seed's rows anybody's; a hash that verifies nothing is the honest verifier for a subject nobody can log in as, and it is stated rather than smuggled. | 0203 |
| **D1172** | Stage plan §5 *Must not*: *"Publish a port on a non-loopback address."* | `docker run -p 127.0.0.1:0:5432` binds loopback with an ephemeral port and `docker port NAME 5432` reads it (`test_api_behaviour.py:246` uses exactly this); `docker inspect` records the `HostIp` Docker was told. Under Docker Desktop/WSL2 the Windows side proxies published ports, so `ss` on the WSL side is not the whole truth there. | `up` publishes `127.0.0.1:0:5432` and never an unbound address; the proof reads `HostIp == "127.0.0.1"` from `docker inspect` (what Docker was told, everywhere) and, where `ss` exists and the daemon is native, that no `0.0.0.0:<port>` or `[::]:<port>` listener exists — with the arm and a `-p 0:5432` control in rig 22a, whose result decides whether the `ss` clause is asserted or recorded as unmeasurable on this workstation. | The property is a Docker instruction; the observation of it differs by daemon, and a proof should assert the instruction and report the observation. | — |
| **D1173** | Stage plan §5 *Already true*: *"`--render-only` with no host and no root"*; CLAUDE.md §1: *"Anything that calls `render_project` must delete what it published under `.generated/<key>`; the gate compares every rendered project for collisions."* | `evidence.load_rendered` iterates `.generated/` and **skips dot-prefixed directories** (`evidence.py:206`); `.generated/*` is gitignored; `bin/session-01-check.sh` step 7 checks only the directories step 3 published (ADR 0014). | The environment's state lives at `.generated/.dev/<key>/` (`state.json`, two `0600` env files, `seeds-applied.json`), dir mode `0700`. It never enters the collision count and never dirties the tree; `up` **reads** `.generated/<key>/outputs.json` through `deployed_output.read_rendered_document(key, runtime=False)` (ADR 0199's three outcomes) and renders nothing itself — an unrendered project is refused with exit 4 naming the `--render-only` command. Proof: a fabricated `.generated/.dev/x/outputs.json` under a monkeypatched `REPO_ROOT` is invisible to `load_rendered`. | One renderer, one resolver; the environment is a consumer of the render, not a second one. | — |
| **D1174** | Stage plan §5: *"`dev up | reset | down`"*, and *"reset-in-seconds"* from the spec. | A role survives `DROP DATABASE`; a reset that kept the container would carry role passwords, settings and the superuser's state across resets, and would be a second bring-up path with its own defects. | `reset` **is** `down` then `up`, byte for byte the same code, measured (rig 22d, ~the `up` figure plus a `rm -f -v`). No in-place variant. | Two paths to one state is the defect class this project keeps producing (question 5); one path measured twice is a number. | 0203 |
| **D1175** | Stage plan §5 *Must not*: *"Set `wal_level = logical` anywhere."* | The image's default is `replica` (D1084); `compose.yaml` sets neither `wal_level` nor `max_wal_senders`. | `up` passes no `-c` at all; the isolation proof reads `SHOW wal_level` = `replica` on the environment. | A property asserted by a test is a property; one assumed from a default is D930's shape. | — |
| **D1176** | D1171: *"`role_name` is the **full** derived role (the service's `_role_name(role_suffix)`, Run 2 reads it)"* — read as though something checks it. | `_role_name` returns the KEY of `role_suffixes`, i.e. the full derived role name (`services/auth-api/app/service.py:404`) — so the *reading* is right. But `_role_name` lives in the **auth service**, which `apg dev` does not run, and **nothing in the database refuses a `role_name` this deployment does not derive**: rig 22b-2 called `app_private.auth_create_user('dev-nobody', 'x', 'nobody', …)` and it returned a uuid, exit 0. `app_private.users`' constraints are the not-nulls and `users_authz_version_check`; there is no FK, no CHECK and no trigger over `role_name`. The verifier IS guarded — a `password_hash` of `'x'` is refused by `user_credentials_password_hash_check` (exit 3, measured). | **The derivation is the command's job and is asserted by the command's own proof**, not delegated to a downstream check that does not exist. `dev_environment` builds the subject statement from `document["database"]["roles"]["authenticated"]` and `test_the_subject_statement_names_the_authenticated_role_and_the_derived_vocabulary` reads the statement, not the cluster. The cluster proof (`test_exactly_one_subject_exists_and_its_rows_are_visible_only_with_it_asserted`) reads `app_private.users.role_name` back and compares it to the document. | A guard nobody wrote is not a guard, and half of D1171's premise was true in the reassuring direction. The half that IS enforced (the verifier) is the half this session was already going to satisfy. | 0203 |
| **D1177** | D1160: the fixture *"hands it to `psql` through `docker exec -e PGPASSWORD=…` — which puts the value in the host's `docker` argument vector"*, read as though the password is what gets the fixture in. | The vector claim is exactly right. The **authentication** claim is not: the pinned image's `pg_hba.conf` is `local all all trust`, `host all all 127.0.0.1/32 trust`, `host all all ::1/128 trust`, and `host all all all scram-sha-256` only after those. Rig 22a: `docker exec … psql -U postgres -h 127.0.0.1` with **no password at all** returns a row, exit 0. So inside the container the password is decorative, and `_apply_as_migration_user`'s docstring reason — *"the socket … could quietly connect as a role this test has not established a password for"* — does not hold (`-U` decides the role either way; its conclusion, connect as the migration user, does hold). Rig 22a-3 found where it IS load-bearing: a client reaching the cluster from anywhere else — across the bridge, or over the published loopback port — is refused *"fe_sendauth: no password supplied"* without it and *"password authentication failed"* with a wrong one. | The two `0600` env files are kept and are **required**, because `apg dev psql` connects from OUTSIDE that trust boundary (the published `127.0.0.1` port), where scram is the matching line. The isolation proof does not assert that the in-container exec is authenticated, because it is not. `--env-file` is the mechanism on both `docker run` and `docker exec` (docker 29.5.2, measured); `-e NAME=VALUE` never appears in `bin/`. | A credential that is not load-bearing where it is used reads as a working authentication and is a proof of nothing. Naming the boundary is cheaper than discovering it from the first adopter who moves the command. | 0203 |
| **D1178** | D1162: *"The 21 unclaimed requirements are enumerated in `UNCLAIMED_BY_HISTORY` (`:1081`)"*, in a sentence whose other citations are `bin/write-session-evidence.py`. | The constant is in **`tests/contract/test_evidence_claims.py:1031`**, not in the library and not in the writer (`git grep -n UNCLAIMED_BY_HISTORY -- src bin tests`). `evidence_claims.py:578` only mentions it in a comment. The three readers are all in that same test module: the orphan check, the stale check and the settled-debt check. | ADR 0202's clause about the 21 is enforced where it already is — **a contract test's constant** — and Run 5 adds nothing to `evidence_claims.py` for it. What Run 5 does add is `OFFLINE_CLAIMS`, in the library, beside `CLAIMS`; the two lists answer different questions and stay apart. | A guard's address decides which run owns it. Looking for it in the writer would have produced a second list that drifts from the first. | 0202 |
| **D1179** | D1157: *"`apg dev psql` (the application role, `app.user_id` preset to the development subject through `PGOPTIONS`, measured in rig 22b)"*, with no statement of what that role may then ask. | `PGOPTIONS='-c app.user_id=<uuid>'` works and is the boundary: as `app_runtime`, `api.notes` returns **1** row with the subject set, **0** with none, **0** with a different subject (rig 22b-2). But the application role has **no USAGE on schema `app`** (migration 0006) — 22b's first probe, `SELECT app.current_user_id()`, died with *permission denied for schema app*, and the readable probe is `current_setting('app.user_id', true)` plus `api.*`. And the `authenticated` role **cannot connect at all**: *"FATAL: permission denied for database"* — it is a role PostgREST switches into, never one that logs in. | `psql` connects as **`app_runtime`** and never as `authenticated`; whatever banner or probe it prints reads `current_setting('app.user_id', true)` and `api.*` only. The cluster proof asserts the three-way RLS result above (with / without / another subject) as the boundary, because that is the property a developer is being handed. | A command that greets a developer with a query their role may not run fails on its first line, and the role that *looks* like the request role cannot open a connection. Both were one probe away. | 0203 |
| **D1180** | Run 2 step 1: *"The set's lock records `follows_release_version` `20260904120030`; a second migration must sort after it and after `20260914120001`."* | Both true, and a third thing happened: **`freeze-lock --project` RECOMPUTES `follows_release_version` from the release lock's newest**, so re-freezing the set moved it from `20260904120030` to **`20260912120031`** — migration 0031 (`api.create_task`, ADR 0196) shipped in Session 20, after this set was first frozen. `verify-lock` passes and both of the set's versions (`…120001`, `…120002`) still sort after it, which is the property the field exists for. | Accepted, and asserted as the PROPERTY rather than as the literal: `test_the_example_lock_records_two_migrations_in_order` asserts `min(versions) > follows`, never `follows == "20260904120030"`. Recorded here because a reviewer reading the set's lock diff sees a frozen field move and needs to know a re-freeze does that. An adopter re-freezing a set after taking a new release moves theirs too, and the refusal that matters — a project version at or below the release's newest — is unchanged. | A frozen field that a command recomputes is not frozen against that command, and the plan read it as one. Asserting the literal would have made every future release move this test. | — |
| **D1181** | Run 2 step 1: *"put it last and say so in its docstring, or have it call the applying helper itself; read how the module orders things and do what it does."* Taken as: the module runs in file order, `pytest-randomly` is not installed, so the grant proof may read the state the applying proof left. | **True of a whole-module run and false of how the gate runs it.** Run 2's battery put the two node ids on one command line and pytest ran them in the order given: the grant proof ran FIRST, found no `api.note_embeddings`, and went red on a missing relation rather than on a missing grant. The gate selects claim proofs BY NODE ID (`static_nodeids_for_mode`), so that is not a hypothetical ordering — it is the one that would have run. The first version of the test carried an assertion that named the reordering, which is a better failure and still the wrong verdict. | The applying loop is now `_apply_every_set(cluster)`, a module-level FUNCTION — not a fixture, because an assertion that fails inside a fixture is an ERROR and this is the module whose failure means a deploy takes a live project down (D285, D386). Both proofs call it; the grant proof calls it only when `api.note_embeddings` is absent, so a whole-module run applies once and either node id alone applies for itself. Measured: module 3 passed, the grant proof alone 1 passed, battery 6/6. | The battery earned its cost here: the defect was in a test written the same day, and it was invisible to the run that wrote it. Session 19's rule again — four of its six vacuous guards were written that day. | — |
| **D1182** | Run 2 step 2: *"add a module-level `LOADED_LOCK: dict | None = None` … `m.LOADED_LOCK["tools_sha256"]`, `m.LOADED_LOCK["tool_count"]`"*. | **`load_lock` returns a `CapabilityLock` dataclass, not a dict** (`services/auth-api/app/mcp_lock.py:226`), and that dataclass **did not carry `tools_sha256` at all**: the digest is read at `:346`, compared against a recomputation, and discarded. So there was no value to report — the runtime verified which lock it held and then forgot. `tool_count` is a field and was already there. | `CapabilityLock` gains `tools_sha256: str | None = None` — the value the lock CARRIED, not a recomputation, because a recomputed digest agrees with the tools by construction and says nothing about which document was read. `None` below lock schema 4, where the field does not exist (ADR 0177). `LOADED_LOCK` is typed `CapabilityLock | None`. Additive with a default, and both existing constructions are keyword-only, so no caller moves (ADR 0175). **Consequence stated:** a deployment whose lock is schema < 4 can never confirm a count, so `mcp.tool_count` is withheld there. Both live projects are at schema 4. | The plan priced a field that existed; what existed was a value the loader threw away. A dict would also have made the probe report whatever the runtime happened to hold rather than a named field. | — |
| **D1183** | Run 2 step 2: *"three outcomes: `ok` (file = document = plane), `problem` (any two differ, naming which), `unknown` (the plane did not answer)"* — with no statement of what that does OFFLINE. | `diagnosis.capability_drift` gains a required `plane: bool \| None`, so its arity moves and every caller is updated (ADR 0175): two in `test_rehearsal.py`, one in `bin/doctor.py`. And the agreeing case is now **UNKNOWN in a checkout**, because there is no container to ask — which made `test_the_drift_probe_compares_digests_itself_and_hands_the_check_only_booleans` red on its first assertion. Evidence values must stay `True`/`False`/`null` (ADR 0159, asserted by that same test), so the plane's answer is a third BOOLEAN and never a word. | `probe_capability_drift` gains `plane_reader=`, injectable, defaulting to the real probe — so the OK branch is reachable offline and the redaction test checks BOTH the unreachable-plane case and the confirmed one. On the host the doctor's tenth check needs `docker`, which the command already requires (`doctor.sh` runs under sudo at a TTY). The verdict on a project whose plane is momentarily unreachable is UNKNOWN, which `exit_code` treats as 6 — deliberate, and this module's own stated rule: a check that could not run is not a healthy check. | A third reading that could not be exercised offline would be a branch only a trip can enter, which is how D1121 happened. The injection is what makes the OK branch reachable without a host. | — |
| **D1184** | The appendix: *"a run that moves a definition greps every reader (`git grep -n <name> -- tests bin src services`) and runs every module found, whole."* Run 2 derived its list exactly that way — 29 modules, 1495 passed — and **CI was RED on the first push** (`565a176`). | The grep finds readers of the NAMES a run moves. It cannot find a guard that reads the SHAPE of a `bin/` command, and `test_container_selectors.py::test_no_operator_command_reads_a_key_the_deployed_document_does_not_have` is one: it walks every `document[...]` and `document.get(...)` in each operator command and checks the key against the outputs schema's `deployedDocument` — **by variable name, deliberately**, because following assignments would trade a precise guard for a vague one. `probe_plane_lock` parsed the capability lock into a local called `document` and asked it for `tools_sha256`, so the guard reported a member the command invents. One failure, both jobs, 5294 and 5263 otherwise green. | Renamed to `lock`, which is what it is, with the reason in the docstring so the next reader does not rename it back. **And the rule the grep was missing, stated:** in a `bin/` command the identifier `document` MEANS the deployed document; a run that adds any `.get`/subscript read in `bin/*.py` puts `test_container_selectors` in its targeted list, the way `test_cli_contract` goes in for a new command (D1014) and `test_acceptance_registry` for a renamed test (D1119). | A derived list is derived from what the run CHANGED, and this run changed a file's shape rather than a name. Three of the four Session 20 host gates went on things free to catch earlier; this one cost a red CI and five minutes, which is the price the rule is meant to keep it at. | — |
| **D1185** | Run 3: *"the `cluster` fixture's setup statements become `dev_environment.activation_statements` and `bootstrap_statements.build_statements`"* — with the fixture's own bootstrap position left alone. | **The position could not be left alone.** `test_migrations_apply_as_the_migration_user` applied the bootstrap at index 1, *"after the first migration creates `app_private`"* (its own comment). Once each migration carried its own `schema_migrations` row — which is the row dbmate writes, and what makes a dev cluster's ledger production's shape — every migration failed there with *permission denied for schema app_private*: the migration user reaches that schema only after the bootstrap grants it. Rig 22b had already measured the pair (32 of 32 in the deploy's order, 0 of 32 in the fixture's); this is the same measurement arriving as a red test. | **The fixture moved to the deploy's order** — the bootstrap once, before the loop, where `bin/deploy-project.py` step 6 puts it. The belief it was written on is false: the bootstrap's statements are what a fresh cluster sees first on a host, where no migration has ever applied. Three tests green, and the battery's `f1`/`f2` (the statements not applied at all; applied to the wrong database) both kill the applying proof. | The fixture's order was an accident nobody had reason to question until something depended on it. One order now, and it is production's. | 0203 |
| **D1186** | Run 3: move *"`build_statements`, `IDENTITY_FIELDS`, `AUTHENTICATOR_REQUEST_ROLES`, `BACKUP_SETTINGS_ROLE`, `BACKUP_FUNCTION_GRANTS` and whatever else `build_statements` reads"*. | Two of the five are not what the plan says. **`BACKUP_FUNCTION_GRANTS` is an ANNOTATED assignment** (`BACKUP_FUNCTION_GRANTS: tuple[str, ...] = (…)`), which an `ast.Assign`-only walk does not see — the first extraction scan reported four dependencies, moved them, and `ruff` found `F821 Undefined name`. **`IDENTITY_FIELDS` is not read by `build_statements` at all**; `assert_identity_matches` reads it, and that stays in the command. | The dependency set is derived by AST over `ast.Assign` **and** `ast.AnnAssign`, and the extraction asserts every moved block is still a verbatim substring of the file it came from — a move that reflowed a statement would be the second implementation this extraction exists to prevent (F-005). `IDENTITY_FIELDS` moves anyway, as pure data, with a re-export the command still reads. Two names the command no longer reads are re-exported and carry `# noqa: F401` with the reason: a name a released file published is a name a reader may already load. | A dependency list written by reading is a list; one derived by AST is the dependency set. The difference was one annotation. | — |
| **D1187** | Run 3: *"`git grep -n \"build_statements\|…\" -- bin src tests` and run every module found, whole."* | The grep finds readers of the NAMES. **Three modules read the command's SOURCE TEXT for SQL that moved**: `test_bootstrap_statements::test_the_bootstrap_still_pairs_the_schema_with_the_extension` (searching for `CREATE SCHEMA IF NOT EXISTS extensions`), `test_database_commands::test_identity_comparison_uses_only_immutable_fields` (searching for the `IDENTITY_FIELDS = (…)` literal, and thereby asserting its typesetting), and `test_auth_service_database_access::test_every_credentialed_role_can_also_connect` (a regex for the `GRANT CONNECT` the moved function builds, compared against `apply_credential` calls that stayed). All three went red. | Each now follows its SUBJECT rather than a path: `inspect.getsource(bootstrap.build_statements)` for the two SQL scans — which follows the function if it moves again — and the identity fields read as a VALUE, with the command's re-export asserted to be the same object. The cross-list test reads each half where that half lives and asserts both non-empty, so a source that stopped containing its half fails rather than matching nothing on both sides. | This is D1184 one run later and one layer down: a grep over names cannot find a guard that reads text. The rule the appendix gained after D1184 wants a second clause — a run that MOVES a definition greps the moved SQL and the moved literals too, not only the moved names. | — |
| **D1188** | Run 3 and the appendix: the targeted list is derived from the tree by grepping the names a run moves. | Run 3 added a `bin/` command, and `test_cli_contract::test_every_command_in_bin_is_covered_by_this_module` refused it: a command in `bin/` and in neither `SHELL_COMMANDS` nor `PYTHON_COMMANDS` is a command none of that module's checks apply to — **including the secret-argument scan**, which is the check a new command most needs. D1014 already states the rule and the plan already named the module; what the run learned is that registration is not bookkeeping. And `test_commands_are_executable_in_the_git_index` then refused both files until they were `git add`ed: the INDEX mode is the contract, not the working tree's. | Both entries added where they sort, each with the reason beside them; `git add` before the module is run, not at the commit. | A new command is not covered by the checks that exist until it is listed, and the check that would have caught a password in an argument vector is one of them. | — |
| **D1189** | Run 4: *"`test_exactly_one_subject_exists_and_its_rows_are_visible_only_with_it_asserted` (after `seed example`: … as `app_runtime` with `PGOPTIONS` set, `SELECT count(*) FROM api.notes` = 2)"* — and D1156/Run 2, which read the tenant refusal as a missing grant on the VIEW. | **The example set granted the view and never the table it reads, so nobody could read it — including the roles it did grant.** `api.note_embeddings` is declared `security_invoker = true` (`0001:66`), so PostgreSQL checks the CALLER's privileges on `app.note_embeddings`; `20260914120001` grants `api.note_embeddings` to `{{authenticated}}` and `{{api_documentation}}` and grants the table to nobody. Measured in rig 22f: `SET ROLE <authenticated>` reads `api.notes` (2 rows) and is refused on `api.note_embeddings` with *permission denied for table note_embeddings* — the TABLE, not the view it holds. The release does both halves in one line for its own objects (`0004:53`: `GRANT SELECT ON app.notes, app.tasks TO {{authenticated}}, {{agent_reader}}, {{agent_writer}}`). **Run 2's repair was therefore incomplete**: it granted the agent roles the view, and the live tenant read at Session 24's trip would still have failed. | `0002-agent-grants.sql` grants `app.note_embeddings` to `{{authenticated}}`, `{{agent_reader}}`, `{{agent_writer}}` and `{{api_documentation}}` beside the view, the set re-frozen and both fixtures re-rendered. The grant proof now **ends on a reading** — `SET ROLE <authenticated>; SELECT count(*) FROM api.note_embeddings` must succeed, with `api.notes` as the control — because a privilege bit is what the catalog says and this is what PostgreSQL does. Neither grant touches whose rows come back: the table keeps FORCE RLS and its owner-scoped policy. `docs/migrations.md` gains the rule. | The two-session survival is the lesson: the first migration granted a view and a test asserted the view was granted, so both agreed and neither was the question. It took a proof that tried to READ to find it, which is ADR 0065/0066 in the smallest possible instance. | — |
| **D1190** | Run 4: *"`bin/dev.sh psql --project FILE [--as app-runtime|migration-user]` … as the application the developer sees the subject's rows"*. | True, and true for a reason the plan does not state: `app_runtime` **inherits `authenticated`** (measured in rig 22f — `pg_auth_members` records exactly that one membership). So what a developer sees through `apg dev psql` is what the `authenticated` request role may see, and a project that grants its objects to `{{authenticated}}` — which is the only request role a project's placeholder allowlist admits for this purpose — reaches the developer's session by inheritance. Without D1189's table grant, `app_runtime` read `api.notes` (2) and was refused `api.note_embeddings`; with it, both. | Recorded, and the cluster proof asserts the mechanism rather than a count: the application role must see **exactly** the rows the subject owns, compared against what the superuser counts for that owner — not a literal, which was wrong the moment a second test in the module wrote a canary note as the same subject. | A developer loop that works by inheritance works until someone reads the allowlist and concludes a project cannot reach it. The measurement is one line of `pg_auth_members` and it decides whether `psql` is useful at all. | — |
| **D1191** | Run 4's battery, item (b): *"`verify_seed` compares a prefix of the digest → the bad-digest test fails"*. | **It survived, and it was right to.** SHA-256 over different content differs everywhere, so a prefix comparison catches an edit made anywhere — the mutation removed no observable behaviour. The test's own docstring had the same false reasoning in it (*"a prefix comparison would accept a file whose first bytes are unchanged, which is every edit made to the END of a file"*), which is not how a digest works. | The mutation is rewritten as the one that removes the check (`actual[:0] != sha[:0]`, always false) and kills; the docstring is corrected to state the property that is actually asserted. Second uninformative mutation this session, after Run 2's first `(c)` and Run 3's first `(f)` (D493). | A battery is only evidence if a survivor is read. Twice now the survivor has been the mutation being wrong, and once it was a real gap — which is the ratio that makes reading them worth the minute. | — |
| **D1192** | Run 5's battery, item (b): *"`write_half` offline drops the marker guard → the live-node test fails"*, and ADR 0202 §2's *"a second check in `write_half`"*. | **The second guard is unreachable while the first one works, so the test written for it measured the first one twice.** `results_for_mode` calls `claim_mode`, which refuses a declared claim carrying a live marker before `write_half` reaches its own check — so the mutation deleting `write_half`'s guard SURVIVED, and the exit 5 the test asserted had been coming from `claim_mode` all along. ADR 0202 already says why the second exists (*"the two can only disagree if one of them is broken"*); what the plan did not say is that "one of them is broken" is the only state it can be observed in. | The fixture gains `break_claim_mode=True`, which writes a module whose FIRST guard is neutralised — the battery's own mutation (a), applied deliberately and only in that one test — and the test asserts the second guard still refuses, writes nothing, and names the offending proofs. Its control, in the same test, is the same declaration with the first guard intact: refused earlier, with a different message. Both refusals exist, and the pair is what says so. | A belt-and-braces check is testable only by undoing the belt. Asserting the outcome without undoing it measures the belt and reports the braces — which is how a guard with no scenario survives (the same shape as `test_a_project_set_that_publishes_nothing`, whose docstring records the last instance). | 0202 |
| **D1193** | CLAUDE.md §1: *"Never `git checkout --` to restore; the files under test are uncommitted. Snapshot to `/tmp`, restore by copy, `cmp` each file back."* | Read, and then done anyway. Run 5's first exercising rig ended with `git checkout -- src/agentic_postgres/evidence_claims.py` to undo a throwaway claim declaration — and reverted **Run 5's own uncommitted library change** with it. The next run failed with `AttributeError: module has no attribute 'ALL_MODES'`, which reads as a defect in the code and was a defect in the rig. Recovered from a `cp` taken before the first run, restored byte for byte and verified with `cmp`. | Every rig and every fixture in this run snapshots to `/tmp` and restores by copy under a `trap`/`finally`, with the restoration asserted — the battery, the exercising rig, and `test_evidence_claims`' `declared_offline`, which edits the library the subprocess imports. The rule was already written; what this adds is that it applies to a rig editing the file the RUN is changing, which is the case where `git checkout --` looks safest and is not. | The rule exists because the working tree is the only copy of an unfinished run. Ten recorded instances were about content in a heredoc; this is the eleventh and the first about a restore. | — |
| **D1194** | `tests/contract/test_evidence_claims.py`'s `declared_offline` fixture, written in Run 5: `text.replace("OFFLINE_CLAIMS: frozenset[str] = frozenset()", …)`, guarded by `assert claim in text, "the declaration did not take"`. | **The anchor stopped matching the moment this run declared the four real claims, and the guard said nothing.** `frozenset()` is not `frozenset(\n    {…})`, so the replacement was a no-op — and `assert claim in text` passed anyway, because the SECOND replacement (into `CLAIMS`) also writes the claim's name. Four tests then failed as though `write-session-evidence.py` were refusing a legitimate declaration, and the refusal they printed was the correct refusal of a claim nobody had declared. D269's rule with the failure inverted: the anchor was not pre-flighted, the assertion was satisfied by a different edit, and the fixture reported a declaration it had not made. | The fixture ADDS to the declaration instead of replacing it — `"OFFLINE_CLAIMS: frozenset[str] = frozenset(\n    {"` with `count(...) == 1` asserted, and the same for `CLAIMS`'s opening line, each a fatal miss. The final assertion counts the claim's name **twice**, so one replacement landing and the other not is caught. Battery arm (q) restores the old anchor and the fixture now fails by name. | A fixture that edits the module under test is a mutation, and it needs a mutation's discipline: pre-flight the anchor, make a miss fatal, and never let a second edit satisfy the first one's check. The cheap version of this check is a substring of the whole file, and a whole file usually contains it. | — |
| **D1195** | `test_capacity_envelope.py::test_a_machine_measurement_names_the_machine_it_describes`: *"a `MACHINE` measurement must name its machine among its conditions"*, implemented as `"development machine" in condition or "deployment host" in condition`. | The envelope has had exactly two machines for eight sessions, so the allowlist and the world coincided. `apg dev` is measured on a **third** — a CI runner is where the uncached first run can be measured at all, because measuring it on the workstation means evicting the image the whole contract suite shares (D1168, D1169). The rule was right and its enumeration was one short. | `MACHINES = ("development machine", "deployment host", "CI runner")`, a named constant with its own comment, and the widening is to a machine the envelope actually has rows from. Non-negotiable §2's distinction applies exactly: **widening an allowlist to a measured set is not weakening**; loosening it to *"names some machine"* would be. | An enumerated allowlist is the right instrument and it has a maintenance cost, which is the point — a rule that accepted any capitalised noun would have accepted a typo as a new machine (ADR 0006's reason, in a second place). | — |
| **D1196** | `test_documentation_index.py::test_every_flag_the_readme_shows_appears_in_that_commands_usage`: every `--flag` on a README command line appears in that command's `--help`. | `bin/apg.sh` is a **dispatcher**. Its `--help` lists verbs; `--project` is documented by `bin/dev.sh --help`, which is what `apg.sh dev` execs. So the first README line this session added — the one a reader is most likely to copy — was reported as an invented flag, and every future line through the front door would have been too. The guard has been correct since Session 7 because no README line had gone through a dispatcher before. | The scan resolves the verb: a line whose command is `bin/apg.sh` and whose next token is a bare word is checked against `bin/apg.sh <verb> --help`. **Resolved rather than exempted** — an exemption for `apg.sh` would have made every flag it dispatches unscanned, which is the opposite of what the test is for. A flag nobody documents anywhere is still caught, and battery arm (p) proves it by inventing `--detach`. | The front door was added in Session 13 and the README only started routing readers through it now. A guard that reads a command's help has to know what the command IS; *"ask the binary"* is right until the binary's job is to delegate. | — |
| **D1197** | Run 6's own battery, arm (k): *"the gate checks for docker after the suite has skipped past it"* — and the guard `assert "docker version" in offline_mode`. | **The same mutation survived two versions of the test.** `true # docker version` leaves the words in the file. The first version scanned the function including its comments, and this gate explains at length what each step does, so the sentence *describing* the check satisfied the assertion that the check exists — D277 exactly. The second version stripped comment LINES, and a trailing comment is not a comment line. Both read a substring where the question was "does this script RUN this". | `code()` strips comment lines for every source-reading test in the module, and the docker assertion goes further: it finds a LINE that begins with `docker version`, and derives the ordering check and the message scan from that line's index. A mention, an argument and a commented-out command are all excluded by construction. | Two attempts at the same assertion, killed by the same mutation, is the argument for batteries rather than an argument about this test. Neither version was obviously weak; what made them weak was the subject being a file whose comments are unusually good. | — |
| **D1198** | CLAUDE.md §1: *"`PYTHONDONTWRITEBYTECODE=1`, clear `__pycache__` first — a same-size mutation applied and reverted within one second runs stale bytecode."* Written for mutation batteries. | **The rule applies to any fixture that edits a module a subprocess imports, and Run 5's `declared_offline` is one.** It writes `evidence_claims.py` twice inside a single test: once with `claim_mode`'s first guard neutralised (`if False:`) and once with it intact (`if modes:`) — **the same number of bytes**, a fraction of a second apart. A `.pyc` is revalidated on the source's mtime in whole seconds plus its size, so the two versions are indistinguishable to the import system and the second subprocess ran the first one's bytecode. The control arm, whose entire job is to show the FIRST guard refusing, then got the second guard's message and the test failed asserting that `claim_mode` no longer works. **It passed in every targeted run and failed in the full suite**, because whether a `.pyc` exists at all depends on what ran before — which is why Run 5's battery, Run 5's CI and Run 6's fourteen-module list all missed it. | `run_writer` passes `PYTHONDONTWRITEBYTECODE=1`, and `declared_offline` removes any existing `evidence_claims.*.pyc` after every write and after the restore. **Measured both ways** (`/tmp/r6-flake.sh`, `/tmp/r6-flake-control.py`): with the repair reverted, 3 of 5 warm runs fail; with it, 0 of 5. The control writes the file back by copy and byte-compares it. | A flake is a proof that is sometimes not one, and this one was written by the run that added the mode it protects. Two lessons, and the second is the general one: the bytecode rule is not about batteries, it is about **any** test that rewrites a module between two subprocess invocations; and a targeted list cannot find a failure whose trigger is what ran BEFORE — only the whole suite can, which is one concrete thing the gate at a run's close buys. | — |
| **D1199** | Run 6's own derivation, three times: `printf '--mode external, …'` and twice `printf '--mode offline, …'` — the continuation lines of the sentence each of the three modes prints when it finishes. | **bash's `printf` parses its first argument for options**, so a format string beginning with `-` is read as one: `printf: usage error`, exit non-zero, and under `set -euo pipefail` the script aborts. One of the three was in `usage()` and died the first time `--help` ran, and was repaired in Run 6. **The other two print only at the END of a successful run**, so nothing executed them until Run 7 ran the gate to completion for the first time. The offline one aborted the gate *after* step 9 had written the evidence half — so the half was correct, complete and green, and the gate never printed `PASSED` and never returned 0. | All three are `printf -- 'FORMAT'`. Applied to the committed artefact rather than re-derived: `wsl --shutdown`, run while diagnosing the network, cleared `/tmp` and took the derivation script with it, and reconstructing that script from memory to re-run it would be retyping the thing D505 forbids retyping. Guarded by `test_cli_contract.py::test_no_printf_format_string_begins_with_a_dash` over **every** command in `SHELL_COMMANDS`, not over this gate — the mistake is available to all forty of them, and D600 and D918 both say to guard the class rather than the instance. Battery: one arm, target FAILED, control green, gate restored by copy and byte-compared. | **The project's most-repeated class, in its cheapest possible form.** A line nobody had executed — eleven previous instances, every one found on a host trip. This one was found in a checkout by a session with no trip, because the session's own close is the first thing that runs its gate end to end. Two readings follow: a gate's LAST lines are the least-executed code in it, since every failing run stops before them; and `set -e` turns a cosmetic defect in a print statement into a non-zero exit on a run that did everything right. | — |
---

## 2. What the session adds to `tests/acceptance-registry.yaml`

Families `DEV-*` (new), `EVD-*` (new), `OPS-*` and `AGT-*` (extended). All
P0, `target_session: 22`. Every requirement belongs to a claim (D697); **a new
requirement gets a claim of its own and is never joined into an older one**
(D1150, ADR 0089). `OPS-READ-001` (Session 20) gains node ids without moving.

| Requirement | What it states | Offline node ids (proposed; the runs settle the names) | Live half |
|---|---|---|---|
| `DEV-ENV-001` | `bin/dev.sh up --project FILE` builds a disposable environment from the project's **rendered** document and the release alone: the locked postgres image by digest; `build_statements()` applied as the superuser (the bootstrap, never a second implementation, F-005); the rendered migration payloads verified against `rendered-manifest.json` and applied as the migration user in manifest order, each in its own transaction with its `schema_migrations` row; `migration_ledger` written as the deploy writes it; two roles activated with generated passwords in `0600` files; `status` reports running / absent / unreadable as three outcomes with three exit codes; `down` removes the container, its anonymous volume and the state directory and is idempotent; `reset` is `down` then `up`; an unrendered project is refused with exit 4 naming the render command; nothing prints a password | `test_dev_environment.py::test_the_run_arguments_name_the_locked_image_by_digest_and_nothing_else`, `::test_the_state_directory_is_dot_prefixed_and_invisible_to_the_evidence_reader`, `::test_planned_migrations_are_the_rendered_files_in_manifest_order_and_a_moved_digest_is_refused`, `::test_the_activation_statements_quote_the_role_and_the_password`, `test_dev_command.py::test_an_unrendered_project_is_refused_with_exit_four_and_the_render_command`, `::test_argument_errors_exit_two_before_docker_is_asked_anything`, `::test_dev_is_a_verb_of_the_dispatcher`, `test_dev_environment_cluster.py::test_up_applies_every_planned_migration_as_the_migration_user_and_records_both_ledgers`, `::test_status_reports_three_outcomes_and_down_is_idempotent`, `::test_nothing_the_command_prints_is_a_password`, `test_migrations_apply_as_the_migration_user.py::test_every_released_migration_applies_as_the_migration_user` (re-pointed at the module, D1158), `test_cli_contract.py::test_commands_are_executable_in_the_git_index` | — (offline claim, ADR 0202) |
| `DEV-SUBJECT-001` | `up` registers exactly one development subject through `app_private.auth_create_user`, with the project's `authenticated` role as `role_name`, the merged surface's derived vocabulary as `scopes`, and a verifier that verifies no password; the subject's id is recorded in the state and is what `seed` and `psql` assert through `app.user_id`; the environment accepts no login | `test_dev_environment.py::test_the_subject_statement_names_the_authenticated_role_and_the_derived_vocabulary`, `::test_the_placeholder_verifier_satisfies_the_check_and_encodes_no_password`, `test_dev_environment_cluster.py::test_exactly_one_subject_exists_and_its_rows_are_visible_only_with_it_asserted` | — |
| `DEV-SEED-001` | `seed NAME` applies a file named in `projects/<slug>/seeds/manifest.json` and nothing else: a path is refused (2), a name the manifest lacks is refused (2), a digest that does not match is refused (5), a seed carrying DDL, `app_private`, or a role change other than the owner preamble is refused (5); the text is rendered with the set's placeholders and applied in one transaction as the migration user with `app.user_id` set to the subject; a seed already applied is refused until `reset`; the example project's `example` seed applies and its rows are the subject's | `test_dev_environment.py::test_the_seed_manifest_refuses_a_path_a_traversal_and_a_bad_digest`, `::test_the_seed_lint_refuses_ddl_and_app_private_and_accepts_the_example_seed`, `::test_a_seed_is_rendered_with_the_sets_placeholders_and_nothing_else`, `test_dev_command.py::test_seed_takes_a_name_and_never_a_path`, `test_dev_environment_cluster.py::test_the_example_seed_applies_once_as_the_subject_and_is_refused_twice` | — |
| `DEV-ISO-001` | The environment's container joins no network but the default bridge, has no bind mount and no mount naming `pgbackrest`, holds no name the secrets contract declares in its environment or its state directory, runs `wal_level` `replica`, publishes its port on `127.0.0.1` only, and derives from `.generated/<key>` and the release — never from `/var/lib` or `/etc` — while the rendered project's own model, read in the same test, joins `backup` and mounts `pgbackrest.conf` | `test_dev_environment.py::test_the_run_arguments_carry_no_network_no_mount_and_no_server_option`, `::test_the_state_root_and_the_document_root_are_the_checkouts_and_never_the_hosts`, `test_dev_environment_cluster.py::test_the_environment_can_reach_no_backup_plane_and_the_rendered_model_can` (D1161's list, control included) | — |
| `DEV-CHURN-001` | The capacity envelope carries `apg dev up` and `apg dev reset` wall times as `MACHINE` measurements naming the workstation and the CI runner, with the image-cache state as a condition, and names the uncached workstation case as unmeasured; the document is current | `test_capacity_envelope.py::test_the_envelope_carries_the_environments_churn_with_its_machine_and_cache_state`, `::test_the_envelope_is_current` | — |
| `DEV-CI-001` | CI stands the environment up, reads its status, seeds it, resets it and takes it down on every push, in that order, and writes the current session's offline evidence half from the gate's JUnit | `test_dev_environment.py::test_ci_runs_the_round_trip_in_order_and_writes_the_offline_half` | — |
| `EVD-OFFLINE-001` | A claim is offline only when declared in `OFFLINE_CLAIMS`; a declared claim carrying a live marker is refused, and an undeclared claim with no live proof is still refused; the offline half is written from a checkout, needs no deployed document, records `checkout_commit`, and refuses a claim that resolves to any live node id; `merge` requires `--offline-input` exactly when the session has offline claims, records `offline_checkout_commit` beside `source_commit`, and prints when they differ; the gate's offline mode and CI write the half | `test_evidence_claims.py::test_a_declared_offline_claim_resolves_to_the_offline_mode`, `::test_an_undeclared_claim_with_no_live_proof_is_still_refused` (replaces `test_a_claim_with_no_live_proof_is_refused` under ADR 0202), `::test_a_declared_offline_claim_that_carries_a_marker_is_refused`, `::test_the_offline_half_is_written_from_a_checkout_and_records_its_commit`, `::test_the_offline_half_refuses_a_claim_with_a_live_node_id`, `::test_merge_requires_the_offline_input_exactly_when_offline_claims_exist`, `::test_the_merged_document_carries_both_commits_and_says_when_they_differ`, `test_session_twenty_two_gate_modes.py::test_offline_mode_writes_the_offline_half` | — |
| `OPS-PLANE-001` | The deployed document publishes `mcp.tool_count` only when the running plane confirmed, through its own probe, that the lock it loaded is the lock on disk (`tools_sha256`); otherwise `null` and a printed line naming both digests; the doctor's capability-drift check reads the plane's digest and reports a third outcome when the plane cannot answer | `test_deploy_command.py::test_tool_count_is_published_only_when_the_plane_confirms_the_lock`, `::test_a_plane_serving_another_lock_publishes_null_and_names_both_digests`, `test_diagnosis.py::test_capability_drift_reads_the_plane_and_reports_unknown_when_it_cannot` | `test_session22_plane.py::test_the_documents_tool_count_is_the_one_the_plane_serves_on_both_projects` (Session 24's trip) |
| `AGT-TENANT-002` | The example set grants its view and write function to the two agent roles in a second frozen migration; the agent roles hold the privileges after both sets apply and `anon` holds neither; a read through a tenant tool returns the caller's rows on a deployment that applied it | `test_migrations_apply_as_the_migration_user.py::test_the_example_sets_grants_reach_the_agent_roles_and_not_anon`, `test_project_migration_sets.py::test_the_example_lock_records_two_migrations_in_order` | `test_session22_plane.py::test_an_agent_reads_rows_through_a_tenant_tool_on_beta` (Session 24's trip) |
| `OPS-READ-001` (Session 20, id kept) | gains: `rendering.publish` and `evidence.load_rendered` name the owner and the `chown` when a directory cannot be replaced or read; `render_project` hands a `sudo` render back to the invoking user | `test_render_atomicity.py::test_a_render_under_sudo_hands_the_directory_and_the_lock_back`, `test_honest_readers.py::test_publish_and_load_rendered_name_the_owner_and_the_remedy` (D1151), and the two existing proofs, now unskipped under root (D1165) | (unchanged) |

**Claims** (`src/agentic_postgres/evidence_claims.py`), each dated 22:
`dev_environment: ("DEV-ENV-001", "DEV-SUBJECT-001", "DEV-SEED-001")`,
`dev_isolation: ("DEV-ISO-001",)`, `dev_churn: ("DEV-CHURN-001", "DEV-CI-001")`,
`offline_evidence: ("EVD-OFFLINE-001",)` — the four go in `OFFLINE_CLAIMS`;
`plane_confirmed_count: ("OPS-PLANE-001",)` and `agent_tenant_read:
("AGT-TENANT-002",)` are host claims and are **not** declared offline.
`honest_readers` is unchanged and expected to pass at the next sweep.

**No new gate variable.** The two live halves read `APG_LIVE_HOST`,
`APG_PROJECT_A_OUTPUTS`, `APG_PROJECT_B_OUTPUTS` and, for the tenant read,
`APG_ADMIN_PASSWORD_FILE` (agent creation as Session 21's module does it).

---

## 4. Irreversible operations

| Operation | Where | What makes it safe |
|---|---|---|
| `projects/example/migrations/` gains a second frozen migration | Run 2 | Fix-forward, additive (two `GRANT`s); frozen under the set's own lock; the release lock is not touched (`freeze-lock --project` never writes it, `docs/migrations.md`); applies on beta at Session 24's deploy and on alpha never (alpha declares no set) |
| `build_statements` and its constants move to `src/agentic_postgres/bootstrap_statements.py` | Run 3 | `bin/postgres-bootstrap.py` re-exports every moved name, so every reader that loads it by path (four test modules) sees the same names with the same arities (ADR 0175); `test_bootstrap_statements` and `test_migrations_apply_as_the_migration_user` targeted whole |
| `assert_rendered_files_match` / `record_ledger` gain a `src/` implementation | Run 3 | `bin/migrate.py`'s two functions keep their names and arities and delegate; `test_migration_ledger` and `test_rendered_migrations` targeted whole |
| `_restore_checkout_ownership` moves into `rendering` and runs inside `render_project` | Run 2 | Best-effort as before; `SUDO_UID` absent → no-op; the deploy's call becomes the same function; a real root login is unchanged and documented |
| `test_a_claim_with_no_live_proof_is_refused` replaced | Run 5 | Under ADR 0202, by two stricter tests (an undeclared claim is still refused; a declared one with a marker is refused) |
| `CURRENT_SESSION` 21 → 22 | Run 6 | All-or-nothing (D690); every `target_session: 22` requirement has its proofs in the same commit; the two live halves are collected under `--setup-plan` with the variables set |
| `VERSION` 1.2.0 → 1.3.0 | Run 6 | Proposed: a new command, an optional `seeds/` directory, an additive set migration, a third evidence mode — no manifest, outputs, capability or secret schema moves; a minor, confirmed by Session 24's `upgrade plan` (§9) |
| `ci.yml` gains the round trip and the offline half | Run 6 | The step runs after the render the job already does; the offline half is written from the gate job's own JUnit and uploaded; a failure is a red push, which is the point |
| Merge of `session-22` into `main` | Run 7 | Fast-forward only, after CI is green on the branch's last commit |

Not irreversible and worth saying: every `apg dev` environment a run or a
test creates is removed by `down`; the module-scoped fixture in
`test_dev_environment_cluster.py` runs `down` in `finally`; a rig deletes
what it published under `.generated/` unless the key already existed.

---

## 5. Build order, run by run

Each run ends with: ruff (its **exit code** printed), the targeted modules
(named, each checked for existence individually — D1104), derived documents
regenerated where a generator's input moved, `chmod 755 bin/*.sh bin/*.py
deploy.sh`, one commit on the `session-22` branch with a message file, a
push, and **that commit's CI verdict read** by full SHA with three buckets
(D1059). A run that writes a test runs its battery (appendix). Mark the run
**Done.** here with what it measured. **A targeted list is derived from the
tree** (D1146, D1149): a run that moves a definition greps every reader
(`git grep -n <name> -- tests bin src services`) and runs every module found,
whole. A red CI on the branch is a stop condition.

**Docker is required for Runs 3, 4, 6 and 7** (the cluster module, the seed,
the gate's round trip). If `docker version` fails in WSL, stop and say so;
do not write a proof that skips.

### Run 1 — the measurements and the two ADRs

**Rigs** (scripts written with the Write tool to `\\wsl$\Ubuntu\tmp\`, run
with `wsl bash -lc "bash /tmp/r22X.sh > /tmp/r22X.txt 2>&1; echo exit=$?"`,
numbers pasted into the Done paragraph; each names its control; each
removes every container, volume and directory it created):

- **22a, Docker's loopback publication, env-file exec, and the anonymous
  volume.** On `POSTGRES_IMAGE` from `versions.env` (read it with the same
  parser `test_migrations_apply_as_the_migration_user.py::_lock` uses —
  copy those six lines): arm A `docker run -d --name r22a-loop --env-file
  /tmp/r22a.env -p 127.0.0.1:0:5432 <image>` (the env file: `POSTGRES_PASSWORD=<hex>`,
  mode 0600); read `docker port r22a-loop 5432` and `docker inspect -f
  '{{json .NetworkSettings.Ports}}' r22a-loop` — expect `HostIp
  "127.0.0.1"` and a port; `ss -ltn | grep <port>` if `ss` exists — record
  what it shows (on Docker Desktop it may show nothing on the WSL side; say
  so). Control B: the same with `-p 0:5432` — expect `HostIp "0.0.0.0"`.
  Then, on arm A after `pg_isready` twice: `docker exec -i --env-file
  /tmp/r22a-pw.env r22a-loop psql -U postgres -h 127.0.0.1 -c 'select 1'`
  where the file holds `PGPASSWORD=<the same hex>` — expect `1` (this
  decides D1160's mechanism; if `docker exec` refuses `--env-file`, record
  the version and use `docker exec -i -e PGPASSWORD` **read from the
  environment of the calling process**, i.e. `env PGPASSWORD=… docker exec
  -e PGPASSWORD …` where `-e NAME` with no value forwards the caller's —
  measure that too). Then `docker volume ls -q | wc -l` before and after
  `docker rm -f r22a-loop` (control: leaves the anonymous volume) and after
  `docker rm -f -v` on a fresh arm (removes it). Record all of it.
- **22b, the bring-up order, the ledgers, the subject, `PGOPTIONS`.** Render
  the fixture if `.generated/fixture-alpha-dev/outputs.json` is absent
  (`./deploy.sh --project project.example.yaml --capabilities
  capabilities.example.yaml --render-only`). Start a cluster as 22a arm A with
  `POSTGRES_DB=<document.database.name>` in the env file. **Read
  `bin/deploy-project.py`'s step 6 and `bin/postgres-bootstrap.sh` first and
  write down the production order** (the plan expects: bootstrap statements,
  then dbmate). Arm A, production order: apply `build_statements(document,
  uuid4())` (loaded by path as `_bootstrap_module()` does) as `postgres` in
  the database; `ALTER ROLE <migration_user> LOGIN PASSWORD '<hex>'`; then
  every file of `.generated/fixture-alpha-dev/migrations/*.sql` in
  `rendered-manifest.json` order as the migration user over TCP with
  `psql -1 -v ON_ERROR_STOP=1 -f -`, the body being the file's text with
  `-- migrate:up` removed and everything from `-- migrate:down` dropped, and
  `INSERT INTO app_private.schema_migrations (version) VALUES ('<version>');`
  appended inside the same `-1` transaction. Expect every file to apply and
  `SELECT count(*) FROM app_private.schema_migrations` = the manifest's
  count. Control B: the fixture's order (bootstrap at index 1) on a second
  cluster — record whether both work or only one (if only B works, migration
  0001 conflicts with the bootstrap's `CREATE SCHEMA IF NOT EXISTS` and that
  is a row: the deploy's order must then be read from the deploy, not
  assumed). Then on arm A: the ledger statement built exactly as
  `record_ledger` builds it (read `migrate.py:191-250`), applied as
  `postgres` — expect one row per migration. Then the subject: `SELECT
  app_private.auth_create_user('dev', 'Development subject',
  '<document.database.roles.authenticated>', ARRAY[<sorted vocabulary of
  the merged surface, from scope_registry.vocabulary(api_surface.merged_surface(load_surface(), load_project_surface(projects/example/contracts/postgrest-api-surface.yaml)))>]::text[],
  '$argon2id$v=19$m=65536,t=3,p=4$' || <22 base64 chars> || '$' || <43 base64 chars>)`
  — expect a uuid (control: a hash not starting `$argon2id$` → the CHECK
  refuses). **Read `services/auth-api/app/service.py::_role_name` first** and
  record whether `role_name` is the full derived role or the suffix; use what
  the service stores. Then `ALTER ROLE <app_runtime> LOGIN PASSWORD '<hex>'`
  and connect as it with `PGOPTIONS='-c app.user_id=<the uuid>'` over TCP:
  `SELECT app.current_user_id()` — expect the uuid (this decides `psql`'s
  mechanism; control: without `PGOPTIONS`, `NULL`). Then as the migration
  user, one `-1` transaction: `SELECT set_config('app.user_id', '<uuid>',
  true); SET LOCAL ROLE <object_owner>; SELECT api.create_note('seed one',
  'body'); RESET ROLE;` — expect a row in `app.notes` owned by the uuid
  (control: the same without the `set_config` → the `AP401` migration 0005
  raises, `test_api_migrations.py:376`).
- **22c, the example seed's vector.** On 22b's arm A, as the migration user
  with the subject set and the owner preamble: `SELECT
  api.set_note_embedding(<note id>, array_fill(0.1::real,
  ARRAY[768])::extensions.vector)` — expect a row in `app.note_embeddings`
  (control: `ARRAY[767]` → the dimension error). If the cast from `real[]`
  is refused by the pinned pgvector, use the string literal form
  (`'[0.1,0.1,…]'::extensions.vector`) and record which form the seed uses.
- **22d, the baseline and the churn.** `python -m pytest
  tests/contract/test_migrations_apply_as_the_migration_user.py -q
  --durations=0 -p no:randomly` twice; record the fixture setup duration and
  the module's wall time both times (this is the ~10 s baseline, re-measured
  today). Then time 22b's arm A end to end (`date +%s.%N` before `docker run`
  and after the last migration), twice, image cached. Record the machine
  (`uname -a`, `docker version --format '{{.Server.Version}}'`, WSL2 or
  native).
- **22e, the evidence model today** (the battery's control for Run 5):
  `python bin/write-session-evidence.py --session 21 --mode offline --junit
  /dev/null --output /tmp/x.json` → argparse's *invalid choice* and exit 2;
  and in Python, `claim_mode` on a fabricated claim with no markers
  (monkeypatch `CLAIMS` as `test_a_claim_with_no_live_proof_is_refused`
  does) → `ClaimError` with *"has no live proof"*. Record both texts.

**ADRs**, indexed in `docs/decisions/README.md` (the row format is the
index's last six rows; Session column 22, Status Accepted):

- **0202 — An offline claim is declared, never inferred, and the evidence
  document says which commit each half measured.** D1162, D1163. Amends
  ADR 0045/0089 (what a claim is: a third kind, about a checkout, declared
  by name), ADR 0163 (three statuses unchanged; a third **mode**). States:
  `OFFLINE_CLAIMS` is the only way a claim becomes offline; an undeclared
  claim with no live proof is refused as before (the 21 in
  `UNCLAIMED_BY_HISTORY` are not retrofitted, D696 — each needs its own
  declaration, which is a decision per claim); a declared claim carrying a
  marker is refused; the offline half records `checkout_commit` and no
  deployed document; `merge` requires `--offline-input` iff the session has
  offline claims; the merged document carries `offline_checkout_commit`
  beside `source_commit`, `MUST_AGREE` does not cover it, and the writer
  prints the difference (ADR 0195: reported, not folded); **no claim with a
  live half can be reported through the offline half** — by construction
  (`claims_for_mode("offline")` excludes any claim with a marker) and by a
  second check in `write_half` (a resolved node id with a marker → exit 5,
  nothing written). Alternatives refused: inferring offline from the absence
  of markers (the 21 would become reportable silently); a fourth status.
- **0203 — The local environment is the database, built from the render
  and the release, and it holds no production secret.** D1157, D1158,
  D1160, D1161, D1170, D1171, D1174. Related: 0013, 0026, 0028, 0030, 0198,
  0199. States: what `apg dev` builds and what it refuses to build (D1157);
  `docker run` on the locked image and not `compose.sh` — the project model
  is a deployment's and the privilege gate is right for it; a dev cluster
  is one container, root-free, with no model to audit; the state directory
  and its modes; the two activated roles and where their passwords live;
  the subject and its verifier; the seed door (a name, a manifest, a
  digest, a lint, one transaction); `reset` is `down` then `up`; what the
  environment never holds (a repository credential, a cipher pass, a
  provider token, a deployed document, a route to any network but the
  bridge); and that the six fixtures are not rewritten (D1158, §10).

**Targeted:** none (documentation). **Push.** CI is expected green (docs
only). Record the run id. Mark Done with 22a–22e's numbers.

**Done.** 2026-09-11, `ff75d1c` on `session-22`, branched from `dd9e2be`.
**CI GREEN** — run `34622182568`, workflow `contract`, `completed success` on
`ff75d1c569c01bcfe6b3887360e1ad03f1433f5c`, which also confirms D1057 live: a
`session-*` branch registers a run. Seven rig scripts, five measurements, two
ADRs (0202, 0203, both indexed), four new divergence rows (**D1176–D1179**);
next free **D1180**. Docker 29.5.2, native
engine in WSL2 (kernel 6.6.87.2-microsoft-standard-WSL2, 8 cores, 7,786 MB),
image `pgvector/pgvector:pg18@sha256:69167330…` cached, 158,801,932 bytes.

*22a — publication, the env file, the anonymous volume.* `-p 127.0.0.1:0:5432`
→ `{"5432/tcp":[{"HostIp":"127.0.0.1","HostPort":"32768"}]}`, one entry;
control `-p 0:5432` → **two**, `0.0.0.0` and `::`. `ss` is present and the
daemon is native, so the `ss` clause **is** assertable here: arm A shows
`LISTEN 127.0.0.1:32768`, the control `LISTEN *:32769` (D1172's arm decided —
assert the Docker instruction everywhere, and assert the `ss` observation on a
native daemon). `Networks` keys exactly `['bridge']`. `Mounts` is exactly one
anonymous volume at `/var/lib/postgresql` — a *no mounts* assertion would be
red on a correct environment (D1161 confirmed). `docker rm -f` left the volume
(3431 → 3431); `docker rm -f -v` removed it (3432 → 3431). `SHOW wal_level` =
`replica` with no `-c` passed (D1175). `docker exec --env-file` works. The
rig's own **no-password control came out green**, which sent 22a-2 and 22a-3
after it: the image's `pg_hba.conf` trusts the socket, `127.0.0.1/32` and
`::1/128`, and applies `scram-sha-256` only beyond them — so the password is
load-bearing from the bridge and from the published port, and decorative
inside the container (**D1177**). 22a-2's own miss, recorded: `docker inspect
-f '{{.NetworkSettings.IPAddress}}'` has no such key on docker 29.5.2 (*"map
has no entry"*), `-h ""` fell back to the socket and all three arms failed
identically; every reader in the tree already goes through
`.NetworkSettings.Networks.<name>.IPAddress`, so no product defect — the rig
was wrong, 22a-3 repaired it and got the three distinct refusals.

*22b / 22b-2 — the order, the ledgers, the subject, `PGOPTIONS`.* Production
order read from `bin/deploy-project.py` step 6 (`postgres-bootstrap.sh
--apply`, then `migrate.sh up`). **Arm A applied 32 of 32 in 8.6 s**; control B
(the fixture's order, bootstrap at index 1) applied **0 of 32** — *permission
denied for schema app_private* on the first migration's own
`schema_migrations` insert, because the migration user reaches that schema only
after the bootstrap grants it. So a dev cluster that records what dbmate
records is **obliged** to use the deploy's order. `schema_migrations` = 32 =
the manifest's count. The `record_ledger` statement, built exactly as
`migrate.py:191` builds it, applied clean: `migration_ledger` = 32 rows. The
merged surface's vocabulary is **7 scopes**: `meta:read`,
`note_embeddings:read/write`, `notes:read/write`, `tasks:read/write`.
`auth_create_user('dev', …, 'apg_fixture_alpha_dev_authenticated',
ARRAY[…7…], '$argon2id$v=19$m=65536,t=3,p=4$<22>$<43>')` returned a uuid;
the control with a `'x'` verifier was refused by
`user_credentials_password_hash_check`; **the control with `role_name`
`'nobody'` was ACCEPTED** (D1176). `PGOPTIONS='-c app.user_id=<uuid>'` as
`app_runtime`: `current_setting` returns the uuid, `api.notes` = **1** with
it, **0** without, **0** with another subject; `app.current_user_id()` is
*permission denied for schema app* and `authenticated` cannot connect at all
(**D1179**). The seed shape — `set_config('app.user_id', …, true)`, `SET LOCAL
ROLE <object_owner>`, `api.create_note`, `RESET ROLE`, one `-1` transaction as
the migration user — wrote a row owned by the subject; the control without
`set_config` raised **AP401** *no request identity for this transaction*.
D1167's premise confirmed on the cluster: `has_table_privilege` for
`agent_reader`/`agent_writer`/`anon` on `api.note_embeddings` is **false,
false, false**, `has_function_privilege(agent_writer, set_note_embedding)`
**false**, and the control `agent_reader` on `api.notes` (the release's grant)
**true**. 22b's own two misses, recorded: `max(uuid)` does not exist in PG 18,
which is why its `app.notes` line came back empty (the count is 1, read again
in 22b-2); and its `PGOPTIONS` probe asked for a schema the role cannot reach,
which is D1179's finding rather than a failure of the mechanism.

*22c — the vector.* Both forms work on the pinned pgvector:
`array_fill(0.1::real, ARRAY[768])::extensions.vector` exit 0, and the string
literal `'[0.2,…]'::extensions.vector` exit 0. The control `ARRAY[767]` raised
*expected 768 dimensions, not 767*. `app.note_embeddings` = 1 row (the second
form updated the first through `ON CONFLICT`). The seed uses the `array_fill`
form: it is one line and it is the form a developer can edit.

*22d — the baseline and the churn.* `test_migrations_apply_as_the_migration_user.py
-q --durations=0 -p no:randomly`, twice: **10.44 s** and **10.40 s** module
wall (11.18 s / 10.99 s process wall), of which setup 4.51 s / 4.57 s and the
migration call 5.05 s / 4.95 s. D1066's *~10 s* re-measured today and standing.
The bring-up itself, twice: **9.50 s** and **9.49 s** total — container ready
4.07 / 3.97 s, roles + bootstrap 0.63 / 0.65 s, 32 migrations 4.52 / 4.54 s,
ledger 0.16 / 0.18 s, subject 0.12 / 0.14 s — with `down` (`docker rm -f -v`)
0.43 / 0.39 s. Process wall 10.15 / 10.13 s. Image cached both times; the
uncached case stays `UNMEASURED` (Run 6, D1168).

*22e — the evidence model today.* `--mode offline` exits **2** on argparse's
`invalid choice`, usage reading `--mode {host,external}`.
`MODE_MARKERS = {'host': 'live_host', 'external': 'external'}` with its
*"absent on purpose"* comment. `claim_mode` raises `ClaimError("claim {…} has
no live proof: every test it names runs in a checkout, so no deployment is
being measured.")`, and `CLAIMS` maps a name to a plain tuple of requirement
ids — which is the shape the replacement tests monkeypatch.
`claims_through_session(22)` = **108** claims today. `UNCLAIMED_BY_HISTORY` is
in the **test** module, not the library (**D1178**). There is no `merge`
subcommand: merging is the `--host-input` / `--external-input` path at
`write-session-evidence.py:163`, and `MUST_AGREE` begins with `source_commit`.

Rig scripts: `/tmp/r22a.sh`, `/tmp/r22a2.sh`, `/tmp/r22a3.sh`, `/tmp/r22b.py`,
`/tmp/r22b2.py`, `/tmp/r22b2-timed.py`, `/tmp/r22d.sh`, `/tmp/r22e.py` in WSL,
outputs beside them as `.txt`. Every container removed with `rm -f -v`; nothing
published under `.generated/` (`fixture-alpha-dev` was already rendered and is
untouched).

### Run 2 — the five left-overs

Nothing new inherits them. In this order, one commit.

1. **D1167 — the example set's second migration.** Read
   `migrations.PROJECT_PLACEHOLDER_SOURCES` and confirm
   `database.roles.agent_reader` and `database.roles.agent_writer` are
   allowed (if not: stop, record a row, and decide — widening that allowlist
   to two request roles is a decision this plan takes: they are the roles
   the release's own grants name). Write
   `projects/example/migrations/templates/0002-agent-grants.sql`:

   ```sql
   -- migrate:up
   SET LOCAL ROLE {{object_owner}};

   -- D1156: a tenant's tool is served and refused upstream until the tenant
   -- grants its objects to the agent roles. The compiler and the snapshot
   -- cannot see a grant; this is the adopter's, and this set is the worked
   -- example, so it carries it.
   GRANT SELECT ON api.note_embeddings TO {{agent_reader}}, {{agent_writer}};
   GRANT EXECUTE ON FUNCTION api.set_note_embedding(uuid, extensions.vector)
     TO {{agent_writer}};

   RESET ROLE;

   -- migrate:down
   DO $$ BEGIN RAISE EXCEPTION USING ERRCODE = 'AP900',
     MESSAGE = 'fix forward: released migrations are never rolled back'; END $$;
   ```

   Copy the exact `down` block the set's first migration uses (read it; the
   sentinel is `migrations.PROJECT_DOWN_SENTINEL`). Add the manifest entry
   (version `20260914120002`, name `agent_grants`, placeholders
   `["object_owner", "agent_reader", "agent_writer"]`, and the two new
   placeholder declarations with `source: database.roles.agent_reader` /
   `agent_writer` and a description each). `bin/migrate.sh --project
   project.example.yaml freeze-lock`; `verify-lock`. Re-render both fixtures
   (`--render-only`, both example manifests). Proof in
   `test_migrations_apply_as_the_migration_user.py` (it already has the
   cluster with both sets applied):

   ```python
   def test_the_example_sets_grants_reach_the_agent_roles_and_not_anon(cluster) -> None:
       roles = cluster["roles"]

       def has(role: str, kind: str, target: str) -> str:
           function = "has_table_privilege" if kind == "table" else "has_function_privilege"
           privilege = "SELECT" if kind == "table" else "EXECUTE"
           return _docker(
               "exec",
               "-i",
               cluster["name"],
               "psql",
               "-qtA",
               "-v",
               "ON_ERROR_STOP=1",
               "-U",
               "postgres",
               "-d",
               cluster["database"],
               "-c",
               f"SELECT {function}('{role}', '{target}', '{privilege}')::text",
           ).stdout.strip()

       assert has(roles["agent_reader"], "table", "api.note_embeddings") == "true"
       assert has(roles["agent_writer"], "table", "api.note_embeddings") == "true"
       assert (
           has(roles["agent_writer"], "function", "api.set_note_embedding(uuid, extensions.vector)")
           == "true"
       )
       assert has(roles["anon"], "table", "api.note_embeddings") == "false"  # the control
   ```

   (This test must run **after** the module's first test applies the sets;
   pytest runs a module in file order and the module is `-p no:randomly`
   safe only in that order — put it last and say so in its docstring, or
   have it call the applying helper itself; read how the module orders
   things and do what it does.) README §*Giving an agent your tables*: one
   paragraph after the `auth-admin.sh` paragraph — *the grant is yours: a
   tool over your view is served the moment the lock carries it and refused
   upstream until your set grants the view to `{{agent_reader}}` and the
   write function to `{{agent_writer}}`; the scaffold and `check --project`
   cannot see a grant, and `projects/example/`'s second migration is the
   worked one.* `test_project_migration_sets.py` gains
   `test_the_example_lock_records_two_migrations_in_order`.
2. **D1166 — the plane-confirmed count.** `services/auth-api/app/mcp_runtime.py:387` binds the loaded lock as a
   local (`lock = load_lock(settings.capability_lock_file)`, measured at
   planning); add a module-level `LOADED_LOCK: dict | None = None` assigned
   at that line, with a test in `test_lock_roster.py` that it is the loaded
   document (read `mcp_lock.py` for the lock's field names first —
   `tools_sha256` and `tool_count` are the two the probe reports). Extend `AGENT_PLANE_PROBE` to print five values: the three it
   prints, then `m.LOADED_LOCK["tools_sha256"]`, `m.LOADED_LOCK["tool_count"]`
   (names per what the runtime holds). `agent_plane_constants` returns a
   5-tuple; `observe_mcp` publishes `tool_count` only if the reported digest
   equals `lock["tools_sha256"]`, else `None` and `print(f"  the plane
   serves lock {reported[:12]}…, the file is {disk[:12]}…; tool_count
   unpublished")`. Grep every reader of `agent_plane_constants` and
   `AGENT_PLANE_PROBE` (`git grep -n`), including `test_deploy_command.py`'s
   recorded outputs, and update each. The doctor: find the tenth check in
   `src/agentic_postgres/diagnosis.py` (`capability drift`) and its caller in
   `bin/doctor.py`; give it the container's digest through the same probe
   (the doctor already runs `docker`); three outcomes: `ok` (file = document
   = plane), `problem` (any two differ, naming which), `unknown` (the plane
   did not answer). Tests: `test_deploy_command.py` two cases against
   recorded probe stdout; `test_diagnosis.py` three. Live half:
   `tests/deployment/test_session22_plane.py::test_the_documents_tool_count_is_the_one_the_plane_serves_on_both_projects`
   — reads each deployed document's `mcp.tool_count` and `capability_lock_sha256`,
   runs the probe against each project's mcp container, asserts equality;
   `requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS",
   "APG_PROJECT_B_OUTPUTS")`, `live_host`, `as_root` if the module's
   conftest has it (read `test_session21_agent.py`'s head and copy its
   gating).
3. **D1165 — the two skipping proofs.** Read D1131's test (path in §1) and
   copy its shape into `test_honest_readers.py`'s two proofs: when
   `os.geteuid() == 0`, resolve the checkout owner
   (`pwd.getpwuid(os.stat(REPO_ROOT).st_uid).pw_name`), and make the reading
   through `subprocess.run(["sudo", "-u", owner, sys.executable, ...])` with
   the same script the proof runs in-process otherwise; construct and
   restore the `0000` state as before; assert the restore. Remove both
   `skipif`s. Node ids unchanged.
4. **D1164 / D1151 — the renderer hands back, and two readers speak.** Move
   `_restore_checkout_ownership` from `bin/deploy-project.py` to
   `rendering.restore_checkout_ownership(path: Path) -> None` (same body;
   the lock-file clause included); `render_project` calls it after
   `publish`; `deploy-project.py` imports and calls the moved function
   where it called the old one (grep readers: `git grep -n
   _restore_checkout_ownership -- bin tests`). `rendering.publish`: catch
   `PermissionError` on both `os.replace` calls and raise `RenderError(f"cannot
   replace {target}: it is owned by {owner} and this user is {me}; sudo chown
   -R {me}:{me} {target}")` (owner via `deployed_output._owner_of`'s shape —
   reuse it; make it public if needed). `evidence.load_rendered`: the same
   for `outputs.is_file()`/`read_text` — `EvidenceError` naming owner and
   remedy. Tests: `test_render_atomicity.py::test_a_render_under_sudo_hands_the_directory_and_the_lock_back`
   (monkeypatch `SUDO_UID`/`SUDO_GID` and `os.chown` to record calls; control:
   unset → no call); `test_honest_readers.py::test_publish_and_load_rendered_name_the_owner_and_the_remedy`
   (a `0000` directory, as the checkout owner under `sudo -u` when root —
   D1165's shape again).

**Battery** (every mutation with its anchor, a control the mutation cannot
reach, `FAILED` vs `ERROR` read): (a) drop the `agent_writer` from the
`GRANT EXECUTE` line → the grant test fails, the control assertion on `anon`
still green; (b) `observe_mcp` compares against `lock["canonical_sha256"]`
instead of `tools_sha256` → the disagree case fails; (c) `restore_checkout_ownership`
called before `publish` instead of after → the handback test fails on the
new directory; (d) `load_rendered` raises the bare `PermissionError` → the
owner test fails.

**Targeted:** `test_migrations_apply_as_the_migration_user`,
`test_project_migration_sets`, `test_rendered_migrations`,
`test_deploy_command`, `test_diagnosis`, `test_lock_roster`,
`test_honest_readers`, `test_render_atomicity`, `test_deployment_suite_shape`
(a new deployment module), `test_acceptance_registry` (new node ids — the
registry entries for `OPS-PLANE-001` and `AGT-TENANT-002` are written in
Run 6; until then the new tests exist unregistered and
`test_no_new_requirement_goes_unreported_by_every_claim` is untouched),
plus every module `git grep -l "postgres-bootstrap.py\|agent_plane_constants\|_restore_checkout_ownership" -- tests` names. **Push.** CI green expected.

**Done.** 2026-09-11, `565a176` + `c91efbb` on `session-22`. **CI GREEN** on
`c91efbbcace6c64d554edd30cb3133ca3d9659ca` — run `34628469394`, workflow
`contract`, `completed success`, all three jobs. Four repairs, five divergence
rows (**D1180–D1184**), next free **D1185**. **CI was RED on the first push**
(`565a176`, run `34627456639`: *Session 1 gate* and *Session 2 offline
contract* both failed on one test, *P0 inventory* succeeded) and green on
the repair: one guard,
`test_container_selectors::test_no_operator_command_reads_a_key_the_deployed_document_does_not_have`,
which reads the SHAPE of a `bin/` command rather than any name this run moved,
so the tree-derived grep could not find it (**D1184**). `ruff format` and
`ruff check` both exit 0. **29 targeted
modules, 1495 passed, 2 skipped, 0 failed** — the list derived from the tree
(`git grep -l 'restore_checkout_ownership\|agent_plane_constants\|AGENT_PLANE_PROBE\|capability_drift\|load_rendered\|rendering.publish\|LOADED_LOCK\|tools_sha256\|postgres-bootstrap.py' -- tests`), each module checked for existence individually; two the plan named do not exist (`test_evidence_documents`, `test_mcp_contract_command`) and are named here rather than silently skipped (D1104). **Battery 6/6 killed**, every paired control green in the same invocation, every file restored by copy and verified with `cmp`.

*D1167 — the grant.* `projects/example/migrations/templates/0002-agent-grants.sql`, version `20260914120002`, two GRANTs and the set's own `down` sentinel copied verbatim. `PROJECT_PLACEHOLDER_SOURCES` already admitted `database.roles.agent_reader` and `agent_writer` (read, not assumed), so no allowlist moved; the manifest declares both with a description each. `freeze-lock --project` then `verify-lock`, both exit 0 — and the lock's `follows_release_version` moved (**D1180**). Both fixtures re-rendered: `fixture-alpha-dev` now carries **33** rendered migrations (31 release + 2 project) against `fixture-alpine-dev`'s 31, which is the control for "a project with no set gets none". Proof `test_the_example_sets_grants_reach_the_agent_roles_and_not_anon` on the cluster that applies both sets: `has_table_privilege` true for both agent roles on `api.note_embeddings`, `has_function_privilege` true for the writer on `set_note_embedding`, **false for `anon`** and **true for `agent_reader` on `api.notes`** — the two controls, one saying the grant is not to the world and one saying the mechanism is privilege rather than absence. `test_the_example_lock_records_two_migrations_in_order` in `test_project_migration_sets`. The battery's mutation (a) — drop `agent_writer` from the `GRANT EXECUTE` — killed it with the `anon` control still green. One reader the grep found and the plan did not: `test_the_rendered_document_records_the_set_it_applied` asserted `project_set.count == 1`; it now compares against the lock's own length with a floor of 2, because a literal is how a count stops being checked. README §*Giving an agent your tables* gains the paragraph.

*D1166 — the plane-confirmed count.* `LOADED_LOCK` set once in `create_mcp_app` at the line the server is built from, and `CapabilityLock.tools_sha256` added because the loader verified the signature and discarded it (**D1182**). The probe, the parse and the container lookup moved to `src/agentic_postgres/agent_plane.py` so the deploy and the doctor ask **one** question (D486): `PROBE`, `Report`, `parse_report`, `serves_lock`, `container_filters`, `sole_container`. `observe_mcp` publishes `tool_count` only when `serves_lock` is True, prints one line naming both digests when it is False and a different line when it is None — three outcomes, the third reported (ADR 0195). The doctor's tenth check takes `plane: bool | None` and its arity move updated every caller (**D1183**); `probe_capability_drift` gains an injectable `plane_reader` so the OK branch is reachable offline. Proofs: two in `test_deploy_command` against recorded probe output, three verdicts in `test_diagnosis`, two in `test_lock_roster` (the kept signature, and that a lock the loader REFUSES records nothing). Battery (b) and (e) killed. Two more readers the grep found: `AGT-PLANE-001`'s registry text said the count is *"the compiled contract's"* and now says what it is; `bin/session-21-check.sh` printed `{tool_count} tools` and would have said *"None tools"*, which is a measurement-shaped non-measurement.

*D1165 — the two skipping proofs.* Both `skipif(os.geteuid() == 0)` removed. Under root the reading is made as the checkout's owner through `sudo -u '#<uid>'` — D1131's shape — and out of process, because privilege cannot be dropped for one call and put back; the subprocess IMPORTS the reader rather than reimplementing it (D673). Unprivileged, 24 passed. **The `sudo -u` prefix is not measured on this workstation**: `sudo -n` is refused here (interactive authentication required). So the rest of the root branch is measured instead — `test_the_reading_the_root_branch_makes_gives_the_same_answer` calls the out-of-process reader directly, unprivileged, and asserts its answer equals the in-process one, with a readable directory as the control. **It found a defect in the branch on its first run**: the subprocess passed `repo_root` as a `str` and `rendered_document_path` does `repo_root / …`, so the root branch would have died with `TypeError: unsupported operand type(s) for /: 'str' and 'str'` — on the gate, as a claim that could never pass, which is the eleventh never-executed proof this project has carried onto a host and the first caught before the trip. What remains unmeasured is the prefix alone, which is D1131's shape, already proved live on Session 21's trip. Named as owed in §10 rather than reported as repaired.

*D1164 / D1151 — the renderer hands back, and two readers speak.* `restore_checkout_ownership` moved to `rendering`, and **`render_project` calls it itself** after `publish`; `deploy-project.py` binds the name to the same function, so `test_deploy_establishes_roots`'s source-level guard now reads the moved body and additionally asserts the deploy has not grown a second copy. `rendering.publish` catches `PermissionError` on both `os.replace` calls and raises a `RenderError` naming the owner, the caller and the `chown`; `evidence.load_rendered` does the same on `is_file()`/`read_text()`. `rendering.owner_of` walks upward, the way `deployed_output` already does, because a 0000 directory refuses `stat` on everything inside it. Battery (c1) — remove the handback — and (c2) — move it before `publish` — both killed; (d) — relay the bare `PermissionError` — killed. The first (c) was a survivor and the survivor was right: the mutation ADDED a call and kept the original, so it changed nothing under test (D493, an uninformative mutation, rewritten as two).

*What the battery found in this run's own work.* **D1181**: the grant proof read the state the applying proof left, which holds for a whole-module run and fails for the node-id selection the gate actually uses. The applying loop is now one function both proofs call. The defect was written the same day and was invisible to every green run before the battery.

### Run 3 — the module, the extraction, and `up | status | down | reset`

**Files.** Create `src/agentic_postgres/dev_environment.py`,
`src/agentic_postgres/bootstrap_statements.py`, `bin/dev.sh`, `bin/dev.py`,
`tests/contract/test_dev_environment.py`, `tests/contract/test_dev_command.py`,
`tests/contract/test_dev_environment_cluster.py`. Modify
`bin/postgres-bootstrap.py` (re-exports), `src/agentic_postgres/migrations.py`
(two helpers), `bin/migrate.py` (delegates),
`tests/contract/test_migrations_apply_as_the_migration_user.py` (the fixture
calls the module), `tests/contract/test_cli_contract.py` (`SHELL_COMMANDS`
gains `bin/dev.sh`, `PYTHON_COMMANDS` gains `bin/dev.py`).

**The extraction, first.** Move `build_statements`, `IDENTITY_FIELDS`,
`AUTHENTICATOR_REQUEST_ROLES`, `BACKUP_SETTINGS_ROLE`,
`BACKUP_FUNCTION_GRANTS` and whatever else `build_statements` reads (read
`bin/postgres-bootstrap.py:60-503` and its imports) into
`src/agentic_postgres/bootstrap_statements.py`, bodies unchanged;
`bin/postgres-bootstrap.py` does `from agentic_postgres.bootstrap_statements
import (…every moved name…)` and keeps everything that runs `psql`.
`git grep -n "build_statements\|AUTHENTICATOR_REQUEST_ROLES\|BACKUP_FUNCTION_GRANTS\|BACKUP_SETTINGS_ROLE\|IDENTITY_FIELDS" -- bin src tests`
and run every module found, whole. Then `migrations.verify_rendered_directory(rendered_dir:
Path) -> list[dict]` (the body of `assert_rendered_files_match`, returning
the manifest's entries in order) and `migrations.ledger_insert_statement(document,
rendered_dir, repo_root=REPO_ROOT) -> str` (the statement `record_ledger`
builds, up to and excluding the `subprocess.run`); `bin/migrate.py`'s two
functions call them. `git grep -n "assert_rendered_files_match\|record_ledger" -- bin tests`
and run every module found.

**`dev_environment.py`** — pure, no `subprocess`, no `docker`; every
function testable without a daemon:

```python
STATE_ROOT = REPO_ROOT / ".generated" / ".dev"        # dot-prefixed: evidence.load_rendered skips it (D1173)
CONTAINER_PREFIX = "apg-dev-"
SUPERUSER_ENV = "superuser.env"                        # POSTGRES_PASSWORD=…, POSTGRES_DB=…   (0600)
MIGRATION_USER_ENV = "migration-user.env"              # PGPASSWORD=…                          (0600)
APP_RUNTIME_ENV = "app-runtime.env"                    # PGPASSWORD=…                          (0600)
STATE_FILE = "state.json"                              # no secret; 0600 anyway
SEEDS_FILE = "seeds-applied.json"
EXIT_INPUT, EXIT_PREREQUISITE, EXIT_NOT_RENDERED, EXIT_CONTRACT, EXIT_UNREACHABLE = 2, 3, 4, 5, 9

class DevEnvironmentError(Exception): ...
class StateAbsent(DevEnvironmentError): ...
class StateUnreadable(DevEnvironmentError): ...      # carries path and owner, ADR 0195

@dataclass(frozen=True, slots=True)
class Environment:
    project_key: str; container: str; database: str; roles: dict[str, str]
    port: int | None; subject_id: str | None; image: str; release_commit: str
    started_at: str; rendered_dir: str

def container_name(project_key: str) -> str
def state_dir(project_key: str, repo_root: Path = REPO_ROOT) -> Path
def read_state(project_key, repo_root=REPO_ROOT) -> Environment          # absent / unreadable / parsed (three outcomes)
def write_state(environment, repo_root=REPO_ROOT) -> Path                # dir 0700, file 0600
def locked_image(lock: Path = REPO_ROOT / "versions.env") -> str          # reuse the existing versions.env reader in src (grep "versions.env" src/); POSTGRES_IMAGE with its digest
def run_arguments(container, image, superuser_env: Path) -> list[str]     # ["run","-d","--name",container,"--env-file",str(superuser_env),"-p","127.0.0.1:0:5432",image] — nothing else
def activation_statements(document, migration_password, runtime_password) -> list[str]   # ALTER ROLE … LOGIN PASSWORD … via migrations.quote_identifier / quote_literal
def placeholder_verifier() -> str                                          # "$argon2id$v=19$m=65536,t=3,p=4$" + urlsafe-less b64(16 random bytes, no padding) + "$" + b64(32 random bytes, no padding)
def subject_statement(document, vocabulary: frozenset[str]) -> str         # SELECT app_private.auth_create_user('dev','Development subject',<authenticated role literal>, ARRAY[…]::text[], <verifier>)
def planned_migrations(rendered_dir: Path) -> list[dict]                   # migrations.verify_rendered_directory
def migration_transaction(path: Path, version: str) -> str                 # the up body + the schema_migrations INSERT
def status_of(state: Environment, inspect_json: str | None, applied: int | None, planned: int) -> tuple[str, str]  # ("running"|"stopped"|"absent"|"unknown", sentence)
```

Every identifier through `migrations.quote_identifier`/`quote_literal`, as
the bootstrap does. `placeholder_verifier` uses `secrets.token_bytes` and
`base64.b64encode(...).rstrip(b"=")` (argon2's encoding has no padding).

**`bin/dev.py`** does the work; **`bin/dev.sh`** is the operator surface,
in `bin/agent.sh`'s shape (read it whole and copy its structure: header with
exit codes, `usage()`, argument parsing that exits 2 before anything else,
`exec` of the Python with the interpreter `bin/agent.sh` resolves). Verbs
this run: `up`, `status`, `down`, `reset`. Every verb takes `--project FILE`.
No root anywhere; `docker` as the invoking user.

`up`:
1. Load the manifest and derive the project key **exactly as `bin/db.sh`
   does** (read its `parse_args`/key derivation and call the same thing).
2. `deployed_output.read_rendered_document(key, runtime=False)`: absent →
   exit 4 printing `render it first: ./deploy.sh --project <the path given>
   --capabilities <capabilities.example.yaml or the one the operator names
   with --capabilities> --render-only`; unreadable → exit 3 naming owner and
   chown; the document otherwise.
3. `read_state`: present and the container running (`docker inspect`) →
   exit 2 *"already up; `reset` to rebuild"*; present and container gone →
   print *"stale state from <started_at>; removing"* and `down`'s cleanup;
   absent → continue.
4. Create the state dir (0700); write the three env files (0600) with
   `secrets.token_hex(24)` each; `POSTGRES_DB` = `document["database"]["name"]`.
5. `docker run` with `run_arguments`; on failure exit 9 with stderr's first
   200 chars; wait for `pg_isready -U postgres` **twice in a row** (the
   fixture's loop, 90 s cap); read `docker port <name> 5432` → port.
6. Apply `build_statements(document, str(uuid.uuid4()))` as `postgres` in the
   database (one `docker exec -i … psql -qtA -v ON_ERROR_STOP=1 -U postgres -d
   <db>` with the statements joined by newlines on stdin) — the order rig
   22b confirmed.
7. Apply `activation_statements` as `postgres`.
8. For each planned migration: `docker exec -i --env-file <migration-user.env>
   <name> psql -U <migration_user> -h 127.0.0.1 -d <db> -qtA -v
   ON_ERROR_STOP=1 -1 -f -` with `migration_transaction(...)` on stdin;
   on failure exit 5 printing the migration's name and stderr's last 600
   chars and *"applied before this: [...]"* (the fixture's message).
9. `ledger_insert_statement(document, rendered_dir)` as `postgres`.
10. `subject_statement(document, vocabulary)` as `postgres`, the returned
    uuid captured; the vocabulary from `api_surface.merged_surface(load_surface(),
    load_project_surface(...) or None)` through `scope_registry.vocabulary`
    — build it the way `bin/agent.py::merged_surface_for` does (read it; a
    manifest with no set uses the release surface alone).
11. `write_state`; print: the container, the database, the port, the subject
    id, the two role names, *"passwords are in <state dir> (0600); nothing
    here prints one"*. **Never a password.**

`status`: `read_state` (absent → exit 4 with a sentence; unreadable → exit 3
naming owner and chown); `docker inspect -f '{{.State.Status}}'`; if running,
`SELECT count(*) FROM app_private.schema_migrations` as `postgres`; print
`status_of`'s sentence; exit 0 running, 4 absent, 5 stopped or fewer
migrations than planned, 3 unreadable.

`down`: `docker rm -f -v <name>` (ignore *No such container*); `shutil.rmtree`
the state dir; print what was removed; exit 0 even when nothing was there,
saying so. `reset`: `down` then `up`, the same functions.

**Point the fixture at the module.** In
`test_migrations_apply_as_the_migration_user.py`, the `cluster` fixture's
setup statements become `dev_environment.activation_statements` and
`bootstrap_statements.build_statements`, and `_apply_as_migration_user`
sends `migration_transaction`'s text — the module's proof that its two
sentences are the product's. Keep the module's two tests' assertions
byte for byte.

**Tests.** `test_dev_environment.py` (marks `contract`, `p0`): the §2 node
ids for `DEV-ENV-001`/`DEV-ISO-001` that need no daemon, including
`test_the_state_directory_is_dot_prefixed_and_invisible_to_the_evidence_reader`
(monkeypatch `evidence.REPO_ROOT` to a `tmp_path` holding
`.generated/.dev/x/outputs.json` and `.generated/y/outputs.json` at the
current schema; `load_rendered()` returns `{"y": …}`), `test_the_run_arguments_carry_no_network_no_mount_and_no_server_option`
(no `--network`, `-v`, `--mount`, `-c`, `--privileged`; exactly one `-p` and
it starts with `127.0.0.1:`), `test_the_state_root_and_the_document_root_are_the_checkouts_and_never_the_hosts`
(`STATE_ROOT` under `REPO_ROOT`; `bin/dev.py`'s source names neither
`/var/lib/agentic-postgres` nor `/etc/agentic-postgres` — read as text, the
way `test_deployed_transports.py` reads source). `test_dev_command.py`
(`contract`, `p0`; the shape of `test_database_commands.py`): exit 2 before
docker for a missing `--project`, an unknown verb, a bad flag; `--help` exits
0; `bin/apg.sh --list` contains `dev`; `up` on a manifest whose key is not
rendered exits 4 and prints `--render-only`. `test_dev_environment_cluster.py`
(`contract`, `p0`, `database`): a module-scoped fixture that skips exactly
as the six fixtures skip (no rendered fixture; no docker), runs
`bin/apg.sh dev up --project project.example.yaml`, yields the parsed state,
and runs `down` in `finally` — then the §2 node ids: both ledgers (versions
= the rendered manifest's, in order; `migration_ledger` rows = the
statement's values), roles (`rolcanlogin` true for exactly the two, and the
control: `object_owner` false), the three outcomes of `status` (running now;
stopped after `docker stop`; absent after `down`, and `down` again exits 0),
nothing printed by `up` contains either password (read the env files, grep
the captured stdout/stderr), and the isolation test with D1161's list — the
control read with the same Compose helper `test_compose_contract.py` uses
(import its loader rather than re-implementing the `compose.sh … config`
call).

**Battery:** (a) `run_arguments` adds `--network host` → the no-network test
fails, the state-directory test green; (b) `migration_transaction` drops the
`schema_migrations` INSERT → the ledgers test fails, the roles test green;
(c) `activation_statements` activates `object_owner` too → the roles control
fails; (d) `read_state` returns absent on `PermissionError` → the unreadable
outcome test fails (constructed with `chmod 000` under the D1165 shape);
(e) `dev.py` prints the migration password on `up` → the no-password test
fails.

**Targeted:** the three new modules; `test_migrations_apply_as_the_migration_user`;
`test_bootstrap_statements`; `test_migration_ledger`; `test_rendered_migrations`;
`test_database_commands`; `test_cli_contract` (D1014); `test_apg_dispatcher`;
`test_operator_commands_run_on_the_host`; `test_root_script_policy`;
`test_embedded_python`; `test_printed_commands`; `test_evidence_collisions`
and `test_acceptance_registry`; and every module the two greps above named.
**Push.** CI green expected; CI runs the cluster module (its job has Docker).

**Done.** 2026-09-11, `03c3f1b` on `session-22`. **CI GREEN** — run
`34640459071`, workflow `contract`, `completed success` on
`03c3f1be3325d6768c0a8066d85c770127364899`, all three jobs, first push.
`apg dev up | status | down | reset` works end to end.
Four divergence rows (**D1185–D1188**), next free **D1189**. `ruff format` and
`ruff check` exit 0; `shellcheck bin/dev.sh` clean. **30 targeted modules,
1436 passed, 2 skipped, 0 failed**, the list derived from two greps over every
moved name. **Battery 7/7 killed**, every paired control green, every file
restored by copy and verified with `cmp`.

*The extraction.* `build_statements` and the three constants it reads moved to
`src/agentic_postgres/bootstrap_statements.py` **by AST line span and asserted
verbatim** — each moved block is still a literal substring of the file it came
from, so nothing was reflowed on the way (F-005 is what a retyped second copy
costs). `bin/postgres-bootstrap.py` re-exports all five names and `1498 → 1096`
lines. Every module that loads that file by path was run whole: 816 without
Docker, then `test_migrations_apply_as_the_migration_user` + the two service
modules (18), `test_agent_audit_plane` + `test_storage_plane` (80) and
`test_auth_endpoints` (89) — 1003 in all, 0 failed. **D1186** and **D1187** are
what the move actually cost.

*The two helpers.* `migrations.verify_rendered_directory` (the manifest's
entries, in order, digests verified) and `migrations.ledger_insert_statement`
(every set's lock, D1096's repair intact). `bin/migrate.py`'s two functions keep
their names, arities and exit codes and delegate; `437 → 380` lines. Both
imported lazily in the direction `rendering` already imports `migrations`, so
no cycle. 592 passed across their readers.

*The module and the command.* `dev_environment.py` is pure — no `subprocess`,
no `docker` — and `bin/dev.py` does the daemon work behind `bin/dev.sh`, which
is `bin/agent.sh`'s shape. `apg.sh --list` derives `dev` with no list to edit.
Measured on this workstation, `project.example.yaml`: **`up` 15.9 s**, 33
migrations applied as the migration user, `schema_migrations` 33,
`migration_ledger` 33, one subject with 7 scopes, exactly two roles with
`rolcanlogin` and `object_owner` not one of them; state directory `0700` and
every file `0600`; networks `['bridge']`; one mount, the anonymous volume at
`/var/lib/postgresql`; `HostIp 127.0.0.1`; `wal_level replica`; no generated
password anywhere in what the command printed. `status` running → `down` →
`down` again (exit 0, *"nothing to remove"*) → `status` absent (exit 4). Two
defects found by running it rather than by reading it: the manifest field is
`slug` and not `name` (`KeyError` on the first invocation), and
`run_arguments` is the whole argument list so `docker("run", *arguments)`
doubled the verb.

*The fixture is the product path now.* `test_migrations_apply_as_the_migration_user`
builds its pre-state from `dev_environment.role_statements`,
`activation_statements`, `owner_grant_statements` and
`extensions_schema_statement`, applies `bootstrap_statements.build_statements`,
and sends `dev_environment.transaction_body`'s text — and moved to the deploy's
ORDER to do it (**D1185**). Its two existing assertions are unchanged.

*What the battery found in this run's own work.* The unreadable-state arm of
`test_state_that_is_absent_unreadable_or_stale_are_three_different_answers`
**did not exist**: the test asserted absent, half-written and unparseable, and a
mutation making `read_state` answer `StateAbsent` on `PermissionError` survived
it — the one branch its docstring is about was the one branch unexercised. It
now constructs a `0000` directory and, under root, reads it as the checkout's
owner (D1155's shape). One mutation was uninformative and was rewritten as two
(D493), the same mistake as Run 2's first `c`.


### Run 4 — the subject's use, `psql`, and `seed`

**Files.** Modify `dev_environment.py`, `bin/dev.py`, `bin/dev.sh`; create
`projects/example/seeds/manifest.json`, `projects/example/seeds/example.sql`;
extend the three test modules; `docs/migrations.md` gains a *Seeds*
paragraph under *A project's set*.

**`seed NAME`** (D1170, D1171):

```python
SEEDS_DIRECTORY = "seeds"; SEEDS_MANIFEST = "manifest.json"
def seeds_manifest(project_set: migrations.MigrationSet) -> dict          # schema_version 1; seeds: list of {name,file,sha256,description}; name ^[a-z][a-z0-9-]{0,39}$; file a basename ending .sql with no "/" and not starting "."; sha256 64 lowercase hex; names unique
def seed_entry(manifest, name) -> dict                                      # KeyError → exit 2 naming the names the manifest has
def verify_seed(project_set, entry) -> str                                  # reads the file, compares migrations.digest → DevEnvironmentError (exit 5) on mismatch; returns the text
def lint_seed(text: str) -> None                                            # migrations._FORBIDDEN_STATEMENTS (import the private name or make it public), plus _SEED_DDL = re.compile(r"\b(CREATE|ALTER|DROP|TRUNCATE|GRANT|REVOKE|COMMENT)\b", re.I) over sql_surface.statements(text); the only SET ROLE allowed is migrations.PROJECT_ROLE_PREAMBLE and it must be the first statement
def render_seed(text, set_manifest, document, root) -> str                  # migrations.render with the SET's declared placeholders (resolve_placeholders as render_migration does)
def seed_transaction(rendered: str, subject_id: str) -> str                 # "SELECT set_config('app.user_id', <literal>, true);\n" + rendered
```

`bin/dev.py seed --project FILE NAME`: state must be running (else the
`status` exits); the project must declare a set (else exit 3 *"no
migrations.set, so no seeds directory"*); `SEEDS_FILE` must not already
name it (exit 2 *"already applied; `reset` first"*); then verify, lint,
render, apply as the migration user (`-1`, the same exec as a migration),
record the name and digest in `SEEDS_FILE`. A `NAME` containing `/` or
starting with `.` is refused at parse time (exit 2) before any file is
touched — `db.sh`'s rule.

**The example seed** (`projects/example/seeds/example.sql`), the form rig
22c settled:

```sql
-- The example project's seed: two notes and one embedding, all the
-- development subject's. Applied by `bin/apg.sh dev seed --project
-- project.yaml example` as the migration user, inside one transaction, with
-- app.user_id set to the subject before this text runs.
SET LOCAL ROLE {{object_owner}};

SELECT api.create_note('Seeded note one', 'The first seeded note.');
SELECT api.create_note('Seeded note two', 'The second seeded note.');

SELECT api.set_note_embedding(
  (SELECT id FROM api.notes WHERE title = 'Seeded note one'),
  array_fill(0.1::real, ARRAY[768])::extensions.vector
);

RESET ROLE;
```

`manifest.json`: `{"schema_version": 1, "seeds": [{"name": "example",
"file": "example.sql", "sha256": "<computed with migrations.digest>",
"description": "Two notes and one embedding for the development subject."}]}`.

**`psql`** (D1157, D1171): `bin/dev.sh psql --project FILE [--as
app-runtime|migration-user] [-- psql arguments]` execs `docker exec -it
--env-file <the role's env file> -e PGOPTIONS=-c app.user_id=<subject id>
<name> psql -U <role> -h 127.0.0.1 -d <db> <arguments>` — `exec`, so the
exit code is `psql`'s; the subject asserted for both roles (as the
application the developer sees the subject's rows; as the migration user
the developer applies SQL the way a migration would). Not a test surface
beyond its argument contract (exit 2 for a bad `--as`; the argv is built by
a pure function `psql_arguments(...)` asserted to carry `-h 127.0.0.1` and
never a password).

**Tests.** `test_dev_environment.py`: the §2 `DEV-SEED-001`/`DEV-SUBJECT-001`
pure node ids (the manifest refuses `../x.sql`, `sub/x.sql`, `.x.sql`, a
63-char digest, a duplicate name; the lint refuses `CREATE TABLE`,
`GRANT`, `app_private.users`, `SET ROLE postgres`, a preamble not first,
and accepts `example.sql` verbatim; the render substitutes exactly the
set's placeholders and leaves an unknown `{{x}}` as a hard failure the way
`render` does; `subject_statement` names the `authenticated` role of the
fixture document and the vocabulary `scope_registry.vocabulary` derives for
the merged example surface — computed in the test, not typed;
`placeholder_verifier()` matches `^\$argon2id\$v=19\$m=65536,t=3,p=4\$[A-Za-z0-9+/]{22}\$[A-Za-z0-9+/]{43}$`
and two calls differ). `test_dev_command.py`: `seed` refuses `a/b`, `.x`,
and a name with `--project` absent, all exit 2 without docker.
`test_dev_environment_cluster.py`: `test_exactly_one_subject_exists_and_its_rows_are_visible_only_with_it_asserted`
(after `seed example`: `SELECT count(*) FROM app_private.users` = 1; as
`app_runtime` with `PGOPTIONS` set, `SELECT count(*) FROM api.notes` = 2;
without it, 0 — the control), `test_the_example_seed_applies_once_as_the_subject_and_is_refused_twice`
(`app.notes` rows' `owner_id` = the subject; `app.note_embeddings` has one
row; the second `seed example` exits 2 and the counts are unchanged).

**Battery:** (a) `seed_transaction` drops the `set_config` line → the
subject test fails on `owner_id` (or `AP401`), the manifest tests green;
(b) `verify_seed` compares a prefix of the digest → the bad-digest test
fails; (c) `lint_seed` loses the DDL pattern → the `CREATE TABLE` case fails,
the `app_private` case green (a paired control inside one test, D499); (d)
the manifest accepts `sub/x.sql` → the traversal test fails.

**Targeted:** the three dev modules, `test_project_migration_sets`,
`test_documentation_index` (no new page yet — the doc paragraph is in an
existing page), `test_cli_contract`, `test_root_script_policy`,
`test_printed_commands`, `test_operator_commands_run_on_the_host`. **Push.**

**Done.** 2026-09-12, `aed4f82` on `session-22`. **CI GREEN** — run
`34643275270`, workflow `contract`, `completed success` on
`aed4f82bf442528f77d2d3412e7a051c4ac4dc95`, all three jobs, first push.
`apg dev seed` and `apg dev psql` work, and Run 4 found
the defect that would have made Run 2's live proof fail. Three divergence rows
(**D1189–D1191**), next free **D1192**. `ruff format`, `ruff check` and
`shellcheck bin/dev.sh` all clean. **Battery 6/6 killed**, every paired control
green, every file restored by copy and verified with `cmp`.

*The defect.* **D1189**: the example set granted `api.note_embeddings` and never
`app.note_embeddings`, and the view is `security_invoker` — so PostgreSQL
checked every caller against the table underneath, and refused all of them,
including the `{{authenticated}}` role the migration did grant. It has been that
way since Session 20. Session 21 read the tenant refusal as *upstream refused*;
Run 2 read it as a missing grant on the view and granted the view to the agent
roles; neither was wrong about what it saw and neither was the whole cause.
`0002-agent-grants.sql` now grants the table to the four roles that may read it,
the set is re-frozen, both fixtures re-rendered, and the grant proof ends on a
`SET ROLE <authenticated>; SELECT count(*) FROM api.note_embeddings` with
`api.notes` as the control. Measured after the repair: the read returns 1.

*Measured, on `project.example.yaml`.* `seed example` applies 2 notes and 1
embedding, every row owned by the development subject; a second `seed example`
exits 2 with *"already applied; reset first"* and the counts are unchanged; an
undeclared name exits 2 naming the one seed there is; `../../etc/passwd` and
`.hidden` are refused at the wrapper for being paths rather than names. Through
`apg dev psql`'s own argv as `app_runtime`: `api.notes` = 2 with the subject
asserted, **0** without it, **0** as another subject; `api.note_embeddings` = 1.
The argv carries `-h 127.0.0.1`, `--env-file` and no password.

*D1190.* The loop works because `app_runtime` inherits `authenticated` — one
membership in `pg_auth_members`, measured in rig 22f. A project's placeholder
allowlist admits `{{authenticated}}` and not `app_runtime`, so that inheritance
is the whole reason a developer's session can see a project's own domain.

*The seed door.* A NAME checked against the project's manifest before anything
is joined to a path (`bin/db.sh sql`'s rule); the digest compared whole; the
text linted against the set's own forbidden table plus the rule a seed has and a
migration does not — a seed **creates nothing**; rendered with the set's
declared placeholders; applied in one transaction as the migration user with
`app.user_id` set to the subject. Recorded in `seeds-applied.json`, once per
environment.

*What the battery found in this run's own work.* **D1191**: the plan's
prefix-digest mutation survived because a prefix comparison catches an edit
anywhere, and the test's docstring carried the same false reasoning. Both
corrected. The seed-name-positional refusal was found by running the command
rather than reading it: the wrapper demanded the NAME immediately after `seed`,
so `seed --project x example` — the order the plan's own `bin/dev.py` line uses
— was refused as *"seed requires the name of a declared seed"*, which is a lie
about what was typed. The name is now the one positional, wherever it falls.


### Run 5 — the offline claim (ADR 0202)

**Files.** Modify `src/agentic_postgres/evidence_claims.py`,
`bin/write-session-evidence.py`, `tests/contract/test_evidence_claims.py`,
and every gate-mode guard that reads `MODE_MARKERS`
(`git grep -n "MODE_MARKERS\|claim_mode\|claims_for_mode\|static_nodeids_for_mode" -- bin src tests`).

`evidence_claims.py`:

```python
OFFLINE_MODE = "offline"
#: Claims measured in a checkout, DECLARED here and nowhere else (ADR 0202).
#: A claim with no live proof that is not named here is still refused: the
#: twenty-one requirements ledger §4 lists become reportable one declaration
#: at a time, each a decision, never by inference (D696).
OFFLINE_CLAIMS: frozenset[str] = frozenset()          # Run 6 fills it with the four
def claim_mode(claim) -> str:
    markers = {...}                                    # as today
    modes = sorted(mode for mode, marker in MODE_MARKERS.items() if marker in markers)
    if claim in OFFLINE_CLAIMS:
        if modes:
            raise ClaimError(f"claim {claim!r} is declared offline and carries {modes}: a claim with a live half may not be reported through the offline half.")
        return OFFLINE_MODE
    if not modes: raise ClaimError(... the sentence today ...)
    if len(modes) > 1: raise ...
    return modes[0]
def claims_for_mode(mode, session):                    # accepts OFFLINE_MODE beside MODE_MARKERS' keys
def static_nodeids_for_mode(mode, session):            # unchanged in body; for offline every node id qualifies
```

`write-session-evidence.py`: `--mode` gains `offline`; `write_half` for
offline takes no deployed document (refuses `--project-a-outputs` with exit
2, *"an offline half measures a checkout"*), records `"checkout_commit":
evidence_module.git_output("rev-parse", "HEAD")`, `"source_commit": None`,
`"project_keys": []`, `"routes": None`, `"certificate_sha256": None`, and
**refuses** (exit 5, nothing written) if any node id of a resolved claim
carries an environment marker (the second guard). `merge` gains
`--offline-input`; required iff `claims_for_mode("offline", session)` is
non-empty (the `external` sentence's twin); `merged["offline_checkout_commit"]
= offline.get("checkout_commit")`; after computing status, if both commits
exist and differ, print *"the offline half measured checkout X; the
deployment is release Y — a checkout claim and a deployment claim about
different commits"* to stderr (no exit change). `MUST_AGREE` untouched
(`checkout_commit` is not in it, by design — say so in a comment).

**Tests** (`test_evidence_claims.py`): the seven §2 node ids, written with
the module's existing monkeypatch shape (read `:247-270`); replace
`test_a_claim_with_no_live_proof_is_refused` with
`test_an_undeclared_claim_with_no_live_proof_is_still_refused` (same body,
new name and docstring citing ADR 0202) — `test_acceptance_registry`
targeted (D1119) because a test function is renamed — measured at
planning: `grep -n "no_live_proof" tests/acceptance-registry.yaml` is
empty, so no registry line moves; repeat the grep at the run in case an
earlier run registered it. The
gate-mode guards that assert `MODE_MARKERS` has two entries (grep) are
updated to assert the three-mode truth. `bin/session-22-check.sh` is Run 6's;
this run leaves every gate unchanged.

**Battery:** (a) `claim_mode` returns `OFFLINE_MODE` for any markerless claim
(the inference ADR 0202 refuses) → the undeclared-refused test fails, the
declared test green; (b) `write_half` offline drops the marker guard → the
live-node test fails; (c) `merge` makes `--offline-input` optional always →
the required-iff test fails on the "has offline claims" arm and green on the
other (both arms in one test, D499); (d) the differing-commits print removed
→ the both-commits test fails on the captured stderr.

**Targeted:** `test_evidence_claims`, `test_acceptance_registry`,
`test_gate_contract`, every `test_session_*_gate_modes` module, `test_session_eight_gate_modes`,
`test_cli_contract`. **Push.**

**Done.** 2026-09-12, `4763fe7` on `session-22`. **CI GREEN** — run
`34645332605`, workflow `contract`, `completed success` on
`4763fe7cfebc1d143cd4d7ebffca9ec8d4ae2faf`, all three jobs, first push.
The evidence model has a third mode, declared and never inferred. Two
divergence rows (**D1192**, **D1193**), next free **D1194**.
`ruff format` and `ruff check` exit 0. **Battery 6/6 killed**, every paired
control green, every file restored by copy and verified with `cmp`.

*The library.* `OFFLINE_MODE`, `ALL_MODES = (*MODE_MARKERS, OFFLINE_MODE)` and
`OFFLINE_CLAIMS: frozenset[str] = frozenset()` — empty until Run 6 fills it with
the four. `claim_mode` has the three behaviours ADR 0202 specifies, and
`MODE_MARKERS` keeps its two entries with its comment rewritten to say what it
is now for: a marker is how a LIVE mode selects its proofs, and the offline mode
has none because what identifies it is the declaration. `claims_for_mode`
accepts the third mode; `static_nodeids_for_mode` needed no special case, and
its docstring now says why — an offline claim carries no marker on any proof, so
the existing filter admits all of them.

*The writer.* `--mode offline` refuses `--project-a-outputs` (exit 2, *"an
offline half measures a checkout, not a deployment"*), reads no deployed
document, and records `checkout_commit` — never `source_commit`, which every
existing reader understands as the release a deployment is running. `merge`
takes `--offline-input`, required exactly when the session has offline claims
and refused when it does not, and records `offline_checkout_commit` beside
`source_commit`. `MUST_AGREE` is untouched and now carries the reason: the two
halves measure different things and may legitimately name different commits, so
the difference is PRINTED rather than required or hidden.

*Measured, at session 21 with a throwaway declaration.* `--mode offline` with a
deployed document exits 2; with a JUnit over the declared claim's proofs it
writes `mode: offline`, `source_commit: null`, `project_keys: []`,
`routes: null`, `certificate_sha256: null`, and `checkout_commit:
aed4f82bf442528f77d2d3412e7a051c4ac4dc95` — which is `git rev-parse HEAD`. A
declared claim whose proofs carry a marker is refused by name; an UNDECLARED
markerless claim is refused with the sentence it has always been refused with,
so the twenty-one in `docs/scope-closure.md` §4 are exactly where they were.

*The contract test ADR 0202 authorises replacing.*
`test_a_claim_with_no_live_proof_is_refused` →
`test_an_undeclared_claim_with_no_live_proof_is_still_refused`, same body, plus
an assertion that its subject is undeclared — so the test cannot quietly become
vacuous if somebody declares `checkout_only` later. Its pair,
`test_a_declared_offline_claim_resolves_to_the_offline_mode`, is the same claim
over the same requirement differing in one thing. `grep -n "no_live_proof"
tests/acceptance-registry.yaml` was empty at planning and is empty now, so no
registry line moved; `test_acceptance_registry` ran anyway (D1119).

*Three mode-iterating tests moved from `MODE_MARKERS` to `ALL_MODES`*, which is
the question they were asking. 53 in `test_evidence_claims`, 608 across the six
gate-mode guards, the registry and `test_cli_contract` — 0 failed.


### Run 6 — the bump

1. `src/agentic_postgres/__init__.py`: `CURRENT_SESSION = 22`; `VERSION` →
   `1.3.0` with ADR 0162's pricing in the comment (a new operator command,
   an optional `seeds/` directory a project may or may not have, one
   additive project-set migration, a third evidence mode; no manifest,
   outputs, capability, lock or secret schema moves; a minor, confirmed by
   Session 24's `upgrade plan`).
2. `tests/acceptance-registry.yaml`: the nine requirements of §2 with the
   node ids the runs actually wrote (`OPS-READ-001` gains its four);
   `evidence_claims.py`: the six claims and `OFFLINE_CLAIMS = frozenset({"dev_environment",
   "dev_isolation", "dev_churn", "offline_evidence"})`;
   `bin/render-acceptance-matrix.py --write`.
3. **The envelope** (D1168): two `Measurement(kind=MACHINE)` rows in
   `capacity.ENVELOPE` with rig 22d's and CI's numbers (the CI figures come
   from step 5's push — write the rows with the workstation numbers, push,
   read the CI log, amend the rows in the same run's second commit; say so
   in the Done paragraph), conditions naming the machine, WSL2/native, the
   Docker server version, *image cached* / *image pulled in the job*, and
   the migration count; one `Unmeasured` row for the uncached workstation
   case; `bin/render-capacity-envelope.py --write`;
   `test_capacity_envelope.py::test_the_envelope_carries_the_environments_churn_with_its_machine_and_cache_state`.
4. **CI** (D1169): in `.github/workflows/ci.yml`, `session-2-contract` job,
   after *Edge and project Compose models resolve*:

   ```yaml
         # Session 22 (D1073, D1169): the product's own local environment is
         # what a pull request's environment is here. Timed, because the
         # envelope reads these numbers (D1168); the image is not cached on a
         # fresh runner, which is the case the workstation cannot measure.
         - name: The local environment stands up, seeds, resets and comes down
           run: |
             . .venv/bin/activate
             t0=$(date +%s.%N)
             bin/apg.sh dev up --project project.example.yaml
             t1=$(date +%s.%N); echo "dev up: $(echo "$t1 - $t0" | bc) s"
             bin/apg.sh dev status --project project.example.yaml
             bin/apg.sh dev seed --project project.example.yaml example
             t2=$(date +%s.%N)
             bin/apg.sh dev reset --project project.example.yaml
             t3=$(date +%s.%N); echo "dev reset: $(echo "$t3 - $t2" | bc) s"
             bin/apg.sh dev down --project project.example.yaml
   ```

   and in the `gate` job, after *Run the Session 1 gate*:

   ```yaml
         # Session 22 (ADR 0202): the current session's OFFLINE evidence half,
         # from the gate's own JUnit. The session is derived, never typed
         # (ADR 0014); a claim the checkout cannot prove makes this red.
         - name: Write the offline evidence half
           run: |
             . .venv/bin/activate
             session="$(PYTHONPATH=src python -c 'from agentic_postgres import CURRENT_SESSION as s; print(s)')"
             python bin/write-session-evidence.py --session "${session}" --mode offline \
               --junit .generated/session-01/contract-tests.xml \
               --output "evidence/session-$(printf '%02d' "${session}")-offline.json"
   ```

   with `evidence/session-*-offline.json` added to the upload's `path`.
   Confirm `bc` is on `ubuntu-latest` (it is in the base image; if the step
   fails on it, use `python -c` arithmetic). Guard:
   `test_dev_environment.py::test_ci_runs_the_round_trip_in_order_and_writes_the_offline_half`
   reads the workflow text and asserts the five verbs appear in order and
   the writer step names `--mode offline`.
5. **The gate.** `bin/session-22-check.sh` **derived from
   `bin/session-21-check.sh` by diff** (D505, D507, D678, D693, D703, D1108,
   D1109): a derivation script under `/tmp` whose every substitution is
   anchored to match exactly once; `readonly SESSION=22`; header and usage
   rewritten whole and read line by line, both halves. Offline mode
   changes: `docker version` required (die 3 naming DEV-ENV-001 as the
   reason); step 3 writes its JUnit to
   `${EVIDENCE_DIR}/${EVIDENCE_PREFIX}-offline-tests.xml`; a new step 8
   *"The local environment round trip"* running the five verbs against
   `project.example.yaml` (the CI step's commands); a new step 9 *"Offline
   evidence"* calling `write_evidence offline` — `write_evidence` gains an
   `offline` branch that passes no `--project-a-outputs`; the usage text says
   the offline mode now writes a half and names the file. Host and external
   modes unchanged except their usage prose (the two Session 22 host claims
   are collected by the existing `live_host` sweep; no new flag). Session
   18's five declaration flags stay (D1133). `SHELL_COMMANDS` gains it;
   `tests/contract/test_session_twenty_two_gate_modes.py` derived from the
   Session 21 guard the same way (`grep -l "session-21-check"
   tests/contract` names it — `test_cli_contract.py` and any other),
   asserting the offline branch writes the half.
6. **Documents.** README: a new section *## A local environment* between
   *Rendering a project* and *Deploying* — what `apg dev up` builds (one
   paragraph), the six verbs with one line each, where the state lives and
   that nothing prints a password, what the environment is not (D1157's
   sentence, and *not a branch: no parent, no promotion, no durability*),
   and the seed door; the *Adding your own tables* table gains a row 2b:
   `bin/apg.sh dev up --project project.yaml` — *your set applies as the
   role that will apply it, before any deploy* — **offline: yes**; the
   status paragraph at Session 22 and 1.3.0; every `--through-session 21`
   a reader is told to type moved to 22 (`grep -rn "through-session 21\|--session 21" README.md docs/*.md`,
   D693). `docs/dev-environment.md` (new; indexed in `docs/README.md`
   under a *Developer loop* heading): the verbs, the state directory, the
   subject, seeds, `psql`, the isolation by construction, the churn numbers
   with their conditions, and *"what to do when"* (docker absent; stale
   state; a seed refused; a migration that fails as the migration user and
   why that is the point). `docs/new-team-member.md` gains one *available
   now* step after the render step, derived by diff (D693).
   `docs/scope-closure.md` §1/§2 numbers, and a new §11 *What Session 22
   left open* (§10 of this plan). `docs/decisions/README.md` count. The
   evaluation report and matrix regenerated where their inputs moved.
7. `pytest --setup-plan tests/deployment/test_session22_plane.py` with
   `APG_LIVE_HOST=1 APG_PROJECT_A_OUTPUTS=.generated/fixture-alpha-dev/outputs.json
   APG_PROJECT_B_OUTPUTS=.generated/fixture-alpine-dev/outputs.json` set
   (D671, D676): both proofs collected, neither deselected.

**Targeted:** `test_evidence_claims`, `test_acceptance_registry`,
`test_cli_contract`, `test_capacity_envelope`, `test_documentation_index`,
`test_session12_documented_path`, `test_repository_contract`,
`test_gate_contract`, `test_session_twenty_two_gate_modes`,
`test_compatibility`, `test_upgrade_plan`, `test_upgrade_command`,
`test_deployment_suite_shape`, `test_dev_environment`, then
`bin/session-01-check.sh` once on the clean tree (a session close is one of
the cases the working agreement allows). **Push.** CI green expected; read
the round-trip step's two numbers from the log and write them into the
envelope (step 3's second commit). Record both run ids.

**Done.** 2026-09-12. `CURRENT_SESSION` 22, `VERSION` 1.3.0, nine requirements,
six claims, **four of them the first offline claims this project has had**.
Five divergence rows (**D1194**–**D1198**), next free **D1199**. `ruff format`
and `ruff check` exit 0. **Battery 17/17 killed**, every paired control green,
every file restored by copy and byte-compared — and two of the seventeen took
three attempts, which is recorded below rather than smoothed over.

*The two numbers.* `CURRENT_SESSION` 22 and `VERSION` 1.3.0, with ADR 0162's
pricing in the constant's comment: a new operator command, an optional
`seeds/` directory a project may or may not have, one additive migration in
the example project's own set, and a third evidence mode. **No manifest,
outputs, capability, lock or secret schema moves and no released migration** —
a project that adopts this release and never types `apg dev` renders
byte-identical artefacts. Session 24's `upgrade plan` confirms the minor.

*The registry and the claims.* Nine requirements: `DEV-ENV-001`,
`DEV-SUBJECT-001`, `DEV-SEED-001`, `DEV-ISO-001`, `DEV-CHURN-001`,
`DEV-CI-001`, `EVD-OFFLINE-001`, `OPS-PLANE-001`, `AGT-TENANT-002`, plus
`OPS-READ-001` widened without moving its id or its session. `DEV` and `EVD`
joined `ID_PATTERN` with their reasons. Six claims, and **the split is the
session's point**: `dev_environment`, `dev_isolation`, `dev_churn` and
`offline_evidence` are declared in `OFFLINE_CLAIMS`; `plane_confirmed_count`
and `agent_tenant_read` are host claims and are deliberately **not**, because
a checkout answering the first would have reported beta green through the
eight minutes it served the wrong lock (D1152). `OPS-READ-001` gained five
node ids rather than the four the plan named — `test_render_atomicity` wrote
three, not one — and `OPS-PLANE-001` carries three live proofs rather than
two, because `test_the_plane_serves_the_lock_the_deploy_mounted` proves the
same requirement and an unregistered proof proves nothing.

*The churn, measured* (`/tmp/r6-churn.sh`, this workstation, WSL2 kernel
6.6.87.2, Docker server 29.5.2, image cached, 33 migrations): **`apg dev up`
10.98 s and 9.89 s; `apg dev reset` 10.07 s and 10.28 s**, two samples each.
`reset`'s teardown disappears into the sampling spread, which is the property
worth publishing. Both are `MACHINE` rows naming the machine and the cache
state; the uncached workstation case is in `UNMEASURED` with its reason —
measuring it means `docker rmi` of the image the whole contract suite shares.
The comparison the stage plan asked for stands: **~10 s against the 247 s
restore** the Session 18 trip measured, on a different machine, so the ratio
is not a number either.

*CI.* The `session-2-contract` job stands the environment up, reads its
status, seeds it, resets it and takes it down, after the render — because `up`
refuses an unrendered project — and times `up` and `reset` with `python`
rather than `bc`, which the plan offered as the alternative and which is one
fewer assumption about the runner image. The `gate` job writes
`evidence/session-22-offline.json` from the gate's own JUnit, with the session
DERIVED (ADR 0014), and the upload carries it. `DEV-CI-001`'s proof reads the
workflow as YAML and asserts the five verbs' ORDER, not their presence.

*The gate.* `bin/session-22-check.sh`, derived from Session 21's by a script
under `/tmp` whose seven substitutions are each anchored to match exactly once
and whose header and usage were rewritten whole; a final scan refuses any
surviving `session-21-check` outside the provenance line. **Offline mode now
requires docker and writes a half** — the first in this project's history.
Docker is a prerequisite (exit 3) rather than a skip, and the message says
why: the cluster proofs would skip, a skip is not a pass, and the half would
be written with `dev_environment` reading `not_run`. Step 3 keeps its JUnit,
step 8 runs the five verbs (starting with `down`, so a re-run starts where the
first run did, D20), step 9 writes the half. `write_evidence` gained an
offline branch that SUBTRACTS `--project-a-outputs` rather than adding
anything, and all three modes now say their half is one of three.
`tests/contract/test_session_twenty_two_gate_modes.py` is new — there was no
Session 21 guard to derive from, so it comes from Session 8's, keeping what
generalises and dropping everything about Session 8's own flags.

*What the battery found, and it was not in the product.* Seventeen mutations,
and **three of them needed the test repaired before they died**:

- (q) restores the fixture's old anchor — **D1194**, and the reason four tests
  in this run looked like a product defect for twenty minutes;
- (g) survived once as an uninformative mutation (D493) and revealed a real
  weakness beside it: the unmeasured check joined every row into one blob, so
  "cached" from one row and "apg dev" from another would have satisfied it
  between them. Per-row now;
- (k) survived **twice**, killing two versions of the same assertion — the
  comment-inclusive scan and then the comment-line-stripped one, because
  `true # docker version` is neither a comment line nor a check. **D1197.**

*Documents.* README: a new *A local environment* section between *Rendering a
project* and *Deploying*, the status paragraph at Session 22 and 1.3.0, *Adopt
`1.3.0`*, row 2b in the tenant table, and every `--through-session 21` a
reader types moved to 22 (three files). `docs/dev-environment.md` is new,
indexed under a *Developer loop* heading in `docs/README.md`.
`docs/new-team-member.md` gains step 8a. `docs/scope-closure.md` §1's six
numbers were **four sessions stale** and are now counted rather than recalled
(193 requirements, 114 claims, 169 covered, 31 migrations, 203 ADRs,
D1–D1194); §11 records what this session leaves open, including what Session
24's trip owes it.

*Collected, not asserted.* `pytest --setup-plan
tests/deployment/test_session22_plane.py` with `APG_LIVE_HOST=1` and both
outputs paths set: all three proofs collected, none deselected (D671, D676).

*And then the gate found a fifth* (**D1198**), which is the one worth reading.
The full contract suite at this run's close failed on
`test_the_offline_half_refuses_a_claim_with_a_live_node_id` — a test that had
passed in Run 5's battery, in Run 5's CI, and in this run's fourteen-module
targeted list. Run 5's `declared_offline` fixture writes `evidence_claims.py`
twice inside one test, and the two versions differ by `if False:` against `if
modes:`: **the same number of bytes**, a fraction of a second apart. Python
revalidates a `.pyc` on mtime in whole seconds plus size, so the second
subprocess imported the first version's bytecode and the control arm got the
wrong guard's refusal. It passed whenever no `.pyc` happened to exist, which is
every targeted run. Repaired and **measured both ways**: reverted, 3 of 5 warm
runs fail; repaired, 0 of 5. Next free **D1199**.

The suite after it: **5362 passed, 0 failed, 3 skipped**, and
`write-session-evidence.py --session 22 --mode offline` over that JUnit writes
`dev_churn`, `dev_environment`, `dev_isolation` and `offline_evidence` all
`passed` — which is Run 7's step 1, confirmed before the push rather than
discovered by a red CI run.

**CI GREEN** — run `34679195048`, workflow `contract`, `completed success` on
`6026ae7b79f16a5e533f6489c7487e73f6889c27`, all three jobs, first push (the
earlier commit `f2a87a5` was superseded by the same push). The gate job's new
step wrote `evidence/session-22-offline.json` with `dev_churn`,
`dev_environment`, `dev_isolation` and `offline_evidence` all `passed` — **the
first offline evidence half this project has produced, and it was produced by
CI before it was produced here.**

*The envelope's second commit*, which is what step 3 planned for. The round-trip
step's two numbers, read from that run's log rather than from anything this
session predicted: **`apg dev up` 14.46 s with the image NOT cached, `apg dev
reset` 6.19 s seconds later with it cached**, on a GitHub-hosted `ubuntu-latest`
runner, 33 migrations. Two readings. The gap between them is dominated by the
pull, which is the cold cost a developer pays once and the workstation cannot
measure; and the runner's `reset` is FASTER than the development machine's
(10.07 s, 10.28 s), which is the whole argument for `MACHINE` rows published
side by side instead of averaged. `test_the_envelope_carries_the_environments_
churn_with_its_machine_and_cache_state` now requires both machines by name for
both verbs, which it could not do until the second machine had rows.


### Run 7 — the close (no trip)

1. `bin/session-22-check.sh --mode offline` on this workstation, in WSL,
   with Docker, output to a file (`rm` it first; never `tail`). Expect
   `evidence/session-22-offline.json` with the four offline claims
   `passed` and exit 0. If a claim is `not_run`, read which node id and why
   (a docker skip is the likely cause) — a skip is not a pass.
2. `git bundle` is **not** made: nothing is transported. The DR kit is not
   re-exported (no deploy of consequence).
3. Merge `session-22` into `main` fast-forward after CI is green on the
   branch's last commit; delete the branch; push `main`.
4. `CLAUDE.md` §2 in the launch folder (copy it to the scratchpad first,
   CLAUDE.md's own rule): a `SESSION 22 COMPLETE` block in the shape of
   Session 21's — what shipped, the offline half's numbers, **what Session
   24's trip owes this session** (D1163: deploy through ≥22, the Session 22
   gate's host and external modes, a three-half merge, D1164's confirmation
   by owner and mtime, and the re-export of the kit), and the next free `D`
   and ADR numbers. Memory: the state file updated.
5. Mark this run **Done.** with the offline half's claim table pasted, the
   `main` SHA, and the two host claims named as waiting.

---

## 7. Evidence and claims

A claim's verdict is computed from the registry's node ids and JUnit
results, never hand-entered; three statuses (ADR 0163); a skip is not a
pass; a `-k` run writes nothing. **This session adds a third mode** (ADR
0202) and the rule that makes it safe: a claim is offline only by
declaration, and no declared claim may carry a live marker.

| Claim | Mode | Measured where | Expected at close |
|---|---|---|---|
| `dev_environment`, `dev_isolation`, `dev_churn`, `offline_evidence` | offline | the gate's offline mode here; CI | `passed` in `evidence/session-22-offline.json` |
| `plane_confirmed_count`, `agent_tenant_read` | host | Session 24's trip | absent from the offline half (by construction); `not_run` until the trip's merge |
| `honest_readers` (Session 20) | host | the next sweep | `passed` for the first time in both halves (D1165) |
| every claim through 21 | host / external | Session 24's trip | unchanged |

`evidence/session-22.json` (merged) does not exist at this session's close
and this plan says so (D1163). Session 24's merge is
`write-session-evidence.py --session 22 --host-input … --external-input …
--offline-input evidence/session-22-offline.json --output evidence/session-22.json`
— from a checkout at the same commit the offline half measured, or the
writer will print the difference.

---

## 8. Security invariants this session touches

- **No production secret on a workstation** (stage plan §5, ADR 0203): the
  environment reads `.generated/<key>/outputs.json` and the release; never
  `/var/lib/agentic-postgres`, `/etc/agentic-postgres`, a provider, a
  repository, a cipher pass. Asserted by `test_the_state_root_and_the_document_root_are_the_checkouts_and_never_the_hosts`.
- **Nothing prints a credential** (D105): two generated passwords in `0600`
  files, reached by `docker exec --env-file`; never an argument, never
  stdout. `test_nothing_the_command_prints_is_a_password` and
  `test_root_script_policy`.
- **The migration user reaches the owner only by `SET LOCAL ROLE`** (ADR
  0026): the environment activates the role the bootstrap creates, with the
  membership the bootstrap grants; a seed runs as that user with the same
  preamble a migration uses.
- **The bootstrap has one implementation** (F-005, ADR 0002's rule for
  statements): `build_statements` moves, it is not copied; the migration-user
  fixture calls it.
- **The seed door is a name** (D1170): a manifest, a digest, a lint, one
  transaction; no path, no stdin, no flag.
- **The subject's verifier verifies nothing** (D1171) and the environment
  has no login path — a dev subject cannot become a credential on a
  deployment because it exists only in a container `down` removes.
- **A dev cluster is not a replication source** (D1175): `wal_level`
  `replica`, asserted.
- **An offline claim cannot report a live half** (ADR 0202): by construction
  and by a second check in the writer.
- **A document publishes what the plane confirmed** (D1166, ADR 0195): a
  count the container did not confirm is `null`, not the file's number.

---

## 9. Stop conditions

- Rig 22b's control B is the only order that works (the bootstrap conflicts
  with migration 0001 when applied first): stop, read the deploy's actual
  order from `bin/deploy-project.py` step 6, and do **that** — the
  environment does what the deploy does, never what a fixture does.
- `docker exec --env-file` is unsupported by the daemon in WSL or in CI:
  use the measured alternative from 22a and record the row; do not fall back
  to a password in an argument.
- `PROJECT_PLACEHOLDER_SOURCES` excludes the agent roles: widen it to the two
  request roles the release's own grants name, with a row; if that widening
  is judged a product decision beyond this session, D1167's migration waits
  and `AGT-TENANT-002` is not registered — say which in the Done paragraph.
- The runtime keeps no importable record of its loaded lock and adding one
  needs a change to how the lock is loaded (not just a name): record the
  cost; if it exceeds a run, `OPS-PLANE-001` ships with the deploy half only
  and the doctor half waits — never a doctor check that reads the file and
  calls it the plane.
- Session 24's `upgrade plan` prices this release as a **major**: a stop for
  that plan, not a number to write down here.
- CI red on the branch: stop and read the log; a cancelled run is not a
  failed one (D1059).
- Docker absent in WSL: stop; do not write a proof that skips and call it
  offline evidence.

---

## 10. Open items this session carries and creates

**Carried in, untouched:** everything in `docs/scope-closure.md` §10 that
Run 2 does not repair (beta's administrator password — an operator decision;
D1150 applied here as a rule); the stage plan's §10 list; D1045; the
rotation performed (D860); `replacement_host_restore` (D1028);
`fresh_host` and `documented_path` (ADR 0197).

**Created here, and owed to Session 24's trip** (D1163):

- Deploy both projects `--through-session ≥22` so the example set's second
  migration applies on beta (alpha declares no set and is the control); read
  the ledger, never the migrator's line (D941).
- Run `bin/session-22-check.sh --mode host` and `--mode external`; merge
  three halves into `evidence/session-22.json`.
- Confirm D1164 by owner and mtime of `.generated/alpha-dev` before and
  after the sweep, with `test_session13_upgrade_plan`'s fixture as the named
  suspect; if the directory is still root-owned after, the suspect is wrong
  and the next candidate is found by the same reading.
- Re-export the DR kit after the deploy and copy it off (Session 21's
  standing item).
- `honest_readers` expected `passed` in both halves for the first time.
- **Run the two repaired `test_honest_readers` proofs AS ROOT.** D1165's
  repair replaces a `skipif` with a `sudo -u` re-entry, and the branch it
  replaces is the one the gate takes. It could not be executed on this
  workstation: `sudo -n` is refused here (interactive authentication
  required), so both proofs are green unprivileged and **the root path has
  never run**. It runs for the first time in the gate's own static claim
  sweep, which is the tenth time this project has carried a never-executed
  proof onto a host. If it skips there, read `_as_checkout_owner` first: a
  root-owned checkout takes the remaining skip branch by design.

**Created here, not addressed:**

- **Five cluster fixtures remain rigs** (D1158): `test_storage_plane`,
  `test_auth_service_reaches_its_data`, `test_storage_service_reaches_its_data`,
  `test_agent_audit_plane`, `test_auth_endpoints`. Each applies as the
  superuser for its own reasons; one reimplements the bootstrap (F-005). A
  later session may point them at `dev_environment` one at a time, each with
  a reason read from the fixture.
- **PostgREST and the auth service on a dev cluster** (D1157): Session 23's
  first measurement if its client needs a served surface; Session 24's
  loopback Studio otherwise. The snapshot a project cannot capture before
  its first deploy (README *Adding your own tables* row 4) would become
  capturable locally the day PostgREST runs on this environment — and that
  capture must be measured byte for byte against a deployed one before
  anybody trusts it (D1118's shape).
- **The 21 unclaimed requirements** (ledger §4) are now reportable one
  declaration at a time (ADR 0202) and remain undeclared: each is a decision.
- **`apg dev` inside CI stands up one project**; a PR that changes a project
  set other than the example's is not exercised. A matrix over every
  `projects/*` with a `seeds/` directory is a one-line change when there is
  a second project.
- **`seed` records what it applied and nothing verifies the rows later**: a
  seed is a developer's, and a proof over its rows is the developer's test.

---

## Appendix — what to consult, and how a run is executed here

**Consult, in this order.** `docs/plans/stage-3-plan.md` §5 *Session 22*,
§7, §10 and its rows D1066, D1071, D1073, D1076, D1079; this document's §1;
`docs/plans/session-21-implementation-plan.md` §1 rows D1151–D1156 and its
Run 7 Done paragraph (what the last trip cost); `docs/scope-closure.md` §4
(the 21 unclaimed) and §10; ADR 0013, 0026, 0028, 0030, 0045, 0067, 0089,
0148, 0163, 0195, 0198, 0199, 0201; `FINDINGS.md` F-005;
`tests/contract/test_migrations_apply_as_the_migration_user.py` whole
(the fixture this session makes a product) and `bin/postgres-bootstrap.py`
lines 1–503; `bin/migrate.py` lines 40–300; `bin/db.sh` and `bin/agent.sh`
whole (the two shapes `bin/dev.sh` copies); `bin/write-session-evidence.py`
whole; `src/agentic_postgres/evidence_claims.py` lines 1–120 and 740–810.

**How a run is executed in this repository** (the short form of `CLAUDE.md`
§1 and §5; read those, they are the record of what each of these cost):

- The Bash tool is Git Bash on Windows. The tree is in WSL:
  `wsl bash -lc "cd ~/projects/agentic-postgres && . .venv/bin/activate && …"`.
  Anything with nested quotes, `$VAR`, a heredoc or a loop variable goes in a
  script written with the Write tool to `\\wsl$\Ubuntu\tmp\x.sh` and run
  with `wsl bash -lc "bash /tmp/x.sh"`, printing its own exit codes.
- File content and commit messages are written with the Write tool and read
  by the script (`git commit -F /tmp/msg.txt`). Never a heredoc for content.
- `chmod 755 bin/*.sh bin/*.py deploy.sh` before every `git add`.
- Never pipe a suite or a gate into `tail`; redirect to a file, `rm` it first.
- `PYTHONDONTWRITEBYTECODE=1` and `__pycache__` cleared before a battery.
- A run's commit: `ruff format && ruff check` (print the exit code), the
  targeted modules — each named module checked for existence individually,
  never by association (D1104) — the derived-document generators whose
  inputs moved, `chmod`, `git add -A`, commit with `-F`, push to
  `session-22`, then read that SHA's verdict: `gh api
  "repos/Virabyan99/agentic-postgres/actions/runs?head_sha=<40 chars>" --jq
  '.workflow_runs[] | [.id,.status,.conclusion] | @tsv'`, judged on HTTP
  status, three buckets (D1059). **Read it every time** (D1120). The
  scratchpad's `s19-ci-watch.sh` / `r8-ci-watch.sh` is the working watcher;
  edit `SHA=`.
- **A commit message is not evidence that the diff contains what it says**
  (D1116): before the message is written, `git diff --stat` against the list
  of repairs it claims, one line each.
- A run that renames, removes or adds a test function puts
  `test_acceptance_registry` in its targeted list (D1119); one that adds or
  removes a `bin/` command puts `test_cli_contract` there (D1014); one that
  adds any `document[...]` or `document.get(...)` read to a `bin/` command puts
  `test_container_selectors` there (**D1184**, which cost Run 2 a red CI). In
  a `bin/` command the identifier `document` MEANS the deployed document; a
  lock, a manifest or a report parsed into a local is named for what it is.
- **A run that MOVES a definition greps the moved TEXT as well as the moved
  name** (**D1187**). Three modules read `bin/postgres-bootstrap.py` as a
  string, searching for SQL that `build_statements` builds and for the
  typesetting of a constant; none of them names either, so no grep over names
  could have found them. Grep the distinctive literals a move carries — a SQL
  fragment, an assignment's left-hand side — and repair each reader to follow
  its SUBJECT (`inspect.getsource`, or the value itself) rather than a path.
- **The targeted list is run ONCE, at the run's close, and it is scaled to the
  change.** The modules a run touched, plus what the two greps above name —
  not every module that could conceivably be affected. Re-running it after
  each edit is minutes per edit for an answer the close will give anyway, and
  CI is the full check (the operator has asked for this repeatedly). During a
  run, run the one module under the hand.
- **A targeted list is derived from the tree, never from the plan's text**
  (D1146, D1149): a run that moves a definition greps the whole tree for its
  readers (`git grep -n <name> -- tests bin src services`); a run that
  changes a shipped fixture greps for the fixture's readers and runs every
  module found, whole. The plan's list names what a run ADDS; the grep names
  what it CHANGES, and CI has caught the difference twice.
- Documentation-only commits run nothing before push. Code runs the targeted
  modules; CI is the full check. The gate (`bin/session-01-check.sh`) runs
  on a clean tree at Run 6's close and Run 7, never at a run's close.
- A rig is a throwaway script with a control arm, its output in a file and
  its numbers pasted into the Done paragraph. Never write a measurement you
  did not run (D267). Delete what a rig publishes under `.generated/` unless
  the key already existed; `docker rm -f -v` every container it started.
- The battery: every mutation's anchor pre-flighted to match exactly once
  and a miss fatal (D269); a paired control the mutation cannot reach, in
  the same invocation, green (D499); the reader distinguishes `FAILED` from
  `ERROR` (D386); restore by copy and `cmp`, never `git checkout --`; a
  survivor is evidence and is read as such (D493, D498).
- **A proof calls the product's own command** rather than hand-rolling the
  request that command makes (D1114, D1117): the cluster module runs
  `bin/apg.sh dev …`, not `docker run`.
- **This session touches no host.** No SSH, no `sudo`, no deploy. If a step
  seems to need one, it belongs to Session 24's trip and goes in §10.

**Grep the plans before measuring a third party.** Docker's publication and
`docker port`: `test_api_behaviour.py:220-260`; anonymous volumes and `rm
-v`: nothing recorded — 22a is the first measurement; `pg_isready` twice:
D-rows in the Session 6 plan (`grep -n "pg_isready" docs/plans/*.md`);
dbmate's ordering and `--strict`: D1098, `docs/migrations.md`; the
bootstrap's order in a deploy: `bin/deploy-project.py` step 6 and the Session
3 plan; `auth_create_user`'s callers: `services/auth-api/app/service.py:365`;
`app.user_id` and `AP401`: `test_api_migrations.py:376,602-624`; pgvector
casts: nothing recorded — 22c is the first. Nothing indexes the ~1,175
measured facts by subject; `grep` is the index.
