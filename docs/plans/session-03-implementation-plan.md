# Session 3 implementation plan — PostgreSQL, migrations, roles, schemas, security invariants

Derived from the Session 3 runbook and reconciled against the working tree at
commit `6bec9a8e`, which is Session 2 complete.

The runbook was written on top of the Session 1 and Session 2 *plans*, not on
top of what those sessions actually built. Twenty-five ADRs and fifty-one
recorded divergences later, the two disagree in enough places that following the
runbook literally would produce a repository that fails its own gate on the
first run. This document keeps every task the runbook sets and states, for each
disagreement, which side governs and why.

**Session 3's outcome, unchanged from the runbook:** each deployed project has a
pinned PostgreSQL 18 + pgvector cluster on its own internal network and volume,
a privileged bootstrap plane distinct from the migration plane, the thirteen
project roles created with least privilege, four schemas, five immutable
migrations, forced row-level security on the owner-scoped tables,
security-invoker read views, two hardened write RPCs, and negative tests proving
that none of it can be crossed.

---

## 1. Runbook divergences

The `D` sequence continues from the Session 2 plan rather than restarting.
Source comments across `bin/` and `tests/` cite divergences by bare number —
`D13`, `D20`, `D25` — so a second sequence starting at `D1` would make every one
of those citations ambiguous.

| # | Runbook says | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D36** | `python bin/render-project.py --project … --through-session 3 --output .generated/alpha-dev` | There is no `bin/render-project.py`. Rendering is `./deploy.sh --render-only`, which needs no host and no root; `bin/render-config.py` renders *host and edge* configuration and is a different thing. | **No new render entry point.** `deploy.sh --render-only` produces the Session 3 artifacts. Every runbook command naming `render-project.py` becomes a `deploy.sh --render-only` invocation. | `--render-only` working with no host and no root is a standing non-negotiable, and it is the only render path any contract test exercises. A second renderer would be a second definition of "rendered". | no |
| **D37** | Add PostgreSQL/pgvector and dbmate image references to `versions.lock.env`. | There is no `versions.lock.env`. `versions.in.yaml` holds human-selected candidates, `bin/lock-versions.sh --update` resolves digests into the generated `versions.env`, and **`POSTGRES_IMAGE: docker.io/pgvector/pgvector:pg18` and `DBMATE_IMAGE: docker.io/amacneil/dbmate:2.34.1` have been locked since Session 1.** | **Nothing is added to the lock inventory.** Session 3 *uses* two images already pinned to digests for `linux/amd64`. A `POSTGRES_MINIMUM_VERSION` / `DBMATE_MINIMUM_VERSION` feature floor is added only for behaviour observed against the image. | ADR 0019 is the standing lesson: a floor written from documentation guaranteed a Traefik key that exists in no version. Floors are recorded from observation or not at all. | no |
| **D38** | Session 3 creates project-prefixed physical roles derived from Session 1 naming rules. | `naming.ROLE_SUFFIXES` already derives **all thirteen** — `anon`, `authenticated`, `agent_reader`, `agent_writer`, `project_admin`, `postgrest_authenticator`, `auth_service`, `mcp_audit_service`, `storage_service`, `migration_user`, `backup_user`, `app_runtime`, `object_owner` — and `outputs.schema.json` requires every one of them on both document kinds. | **Session 3 does not name roles. It creates the roles Session 1 already named.** Bootstrap reads `database.roles` out of the rendered document; it never derives a name. | Nothing else may re-derive a name (ADR 0002). `evidence.collision_count` already compares all thirteen pairwise across every rendered project, so role-name isolation is proved before a cluster exists. | no |
| **D39** | Extend `project.yaml` with a new `database:` block. | `database:` already exists and is **PgBouncer-shaped**: `name`, `pooled_public`, `pooled_public_cidrs`, `max_client_connections`, `pool_size`, with `additionalProperties: false` and `required: [max_client_connections, pool_size]`. | **Fields are added to the existing block, not to a new one.** `pooled_public` stays `false` and keeps its existing conditional-CIDR rule. | A second `database` block would split one concept across two manifest keys, and `additionalProperties: false` means the schema change is mandatory either way. | no |
| **D40** | Set `outputs.json` `schema_version` to `3`. | Both branches pin `enum: [2]`, `$defs.database` is `additionalProperties: false`, and there is a real migration path: `src/agentic_postgres/output_migrations.py` plus a committed `tests/fixtures/outputs-v1.json`. | **Bump to 3, and pay for it.** That means: schema edit on both branches, a `v2 → v3` function in `output_migrations.py`, a committed `tests/fixtures/outputs-v2.json`, and the standing rule that migration never produces a *deployed* document. | Changing the generated output schema is an explicit ADR trigger. The version number is the cheap part; the migration path is what makes an older reader reject rather than guess. | **yes** |
| **D41** | Rendered output carries `database.status: planned`; deployed output records observed versions. | `$defs.database` has no `status`. It has `pooled` and `direct`, each an `endpoint` with `status`, `available_from_session`, `host`, `port`, `url`, `password_secret_ref`, and a schema rule forcing all four to `null` when `status` is `unavailable`. **`test_the_deployed_document_still_reports_no_direct_endpoint` asserts exactly that, passes today, and is a P0 proof of `SEC-NET-001`.** | **`direct` and `pooled` stay `unavailable` with `available_from_session: 4` for the whole of Session 3.** The cluster's internal Compose address is not a client endpoint and is not written into either document as one. Observed server and extension versions go in new fields beside them. | `DBX-005` — "the direct endpoint is not publicly reachable" — is Session 4's requirement, and Session 4 is where a client-facing endpoint is designed. Making `direct` available here would weaken a currently-passing P0 test to describe something Session 3 does not offer. | no |
| **D42** | Define exit-code *ranges*: `10–19` config, `20–29` secrets, `30–39` readiness, `40–49` identity, `50–59` bootstrap, `60–69` migration, `70–79` security, `80–89` evidence. | A frozen single-value convention, asserted by `tests/contract/test_cli_contract.py`: `0`, `2`, `3`, `4`, `5`, `6`, `7`, `8`, `9`, `10`. | **The convention is unchanged.** Session 3 maps onto it: `4` missing runtime state, `5` contract/checksum/render failure, `6` a check failed, `8` secret failure, `9` the service could not be brought to the requested state. Exactly one new code is added — **`11`, project-identity mismatch against an existing volume** — because no existing code means "the data is not yours". | Ranges would replace a convention every script and its tests already share. One new code with a single precise meaning is cheaper than ninety with none. | **yes** |
| **D43** | Rendering emits `.generated/{key}/compose.session-03.yaml`, `postgres/*.conf`, `migrations/*.sql`. | `.generated/<key>/` holds exactly `compose.env`, `outputs.json`, `rendered-summary.txt`, all mode `0600`. The Compose model is the **root `compose.yaml`** with profiles (`contract`, `session2`, `isolation-test`, `session2-verify`), interpolated from `compose.env` through `bin/compose.sh --env-file`; the host adds a root-owned `runtime-compose.override.yaml` (ADR 0020). | **New services go into the root `compose.yaml` under new profiles `session3` and `migration`.** The generated set grows by `postgres/postgresql.conf`, `postgres/pg_hba.conf`, `postgres/bootstrap.sql`, `migrations/*.sql` and `migrations/rendered-manifest.json`. No per-session Compose file. | One model with profiles is what `bin/compose.sh`'s scope gating and forbidden-subcommand list (ADR 0013, 0021, 0022) are built around. A second Compose file would need its own copy of all of it. | no |
| **D44** | ADRs live at `docs/adr/0007-…` through `0010-…`. | ADRs live at `docs/decisions/NNNN-slug.md`, numbered sequentially and never reused, currently through **0025**, with a mandatory index in `docs/decisions/README.md` that "an unlisted ADR is one nobody reads". | **Session 3 ADRs are 0026 onward**, in `docs/decisions/`, indexed. The runbook's four required conclusions become six (see §2). | `0004` went unlisted for a session; the index rule exists because of it. | no |
| **D45** | `sudo bin/session-03-check.sh --host host.yaml --project-a project.alpha.yaml --project-b project.beta.yaml --capabilities capabilities.yaml` | `bin/session-02-check.sh` takes `--mode offline\|host\|external`, `--project-a-outputs` / `--project-b-outputs` pointing at **deployed documents** (not manifests), `--sentinel-file`, `--baseline-only`, and `-k`. It **verifies and never deploys** (D20), and under `-k` it writes no evidence (ADR 0025). | **`bin/session-03-check.sh` takes the same shape**: `--mode offline\|host`, `--project-a-outputs`, `--project-b-outputs`, `-k`, verify-only. There is **no external mode**. | A gate that deploys what it measures cannot be re-run to confirm a fix. There is no external mode because there is nothing new to see from outside: `SEC-NET-001`'s scan already includes port 5432, and Session 3 is the first session in which that scan is not vacuous. | no |
| **D46** | The Session 3 deploy path internally performs release installation, render, **secret materialization**, Compose validation, start, bootstrap, migration, smoke tests and publication. | `deploy.sh --through-session 2` states the opposite in its own header: it "expects the host to be ready already… A deploy that silently performed them would make its own preconditions, and a failure halfway would leave nobody able to say which half." | **The ordering stays operator-visible.** `bin/materialize-secrets.sh` runs before `deploy.sh --through-session 3`, exactly as in Session 2. Deploy *does* own render → Compose validation → start → bootstrap → migrate → smoke → publish, because those have no meaning outside a deployment. | The boundary is "does this step make sense to run on its own, and can it fail on its own?" Secret materialization can; a migration preflight cannot. | no |
| **D47** | New requirement IDs `DBX-PG-001/002/003`, `DBX-MIG-001/002/003`, `SEC-DB-001/002/003`, `SEC-RLS-001/002/003`, `API-DB-001/002`, `DEP-ISO-003`. | **Five Session 3 P0 requirements already exist** in `tests/acceptance-registry.yaml`, each with a `future` placeholder carrying an exact node ID: `SEC-RLS-001`, `SEC-VIEW-001`, `SEC-FUNC-001`, `SEC-DEFAULT-001`, `SEC-OWNER-001`. `DBX-001`–`DBX-005` exist and belong to Session 4. | **Activate the five that exist; add new IDs only for claims none of them covers.** `API-DB-001` collides in meaning with `SEC-VIEW-001` and `API-DB-002` with `SEC-FUNC-001`; both are dropped. Final list in §2. | Activating a requirement means removing its `future` marker and implementing the body — the placeholder already fails when executed, which is what makes it activatable. `test_future_marker_policy.py` enforces registry↔marker agreement in both directions, so an invented duplicate ID fails offline. | no |
| **D48** | Implement `bin/migrate.sh`. | `bin/migrate.sh` **exists**, returns `10`, and is listed in `tests/contract/test_cli_contract.py::FUTURE_STUBS` alongside `bin/connect.sh` and `bin/restore-test.sh`. | **`bin/migrate.sh` is promoted, not created.** It leaves `FUTURE_STUBS`, gains real command-contract tests, and stops returning `10` — the exact lifecycle ADR 0017 describes for `bin/bootstrap-providers.sh` in Session 2. | ADR 0017 exists so that emptying `FUTURE_STUBS` is never a way to make `test_future_stub_exits_ten` pass. The replacement assertions must be stricter than the one removed. | no |
| **D49** | Evidence is `evidence/session-03/…` validated against a new `schemas/session-03-evidence.schema.json`. | `evidence/` is gitignored except `.gitkeep`. Evidence is `evidence/session-NN.json`, written by `bin/write-session-evidence.py`, and Session 2 replaced the suite-name keys with **claims** resolved from the acceptance registry and JUnit results (ADR 0025). | **Session 3 adds claims, not a format.** `src/agentic_postgres/evidence_claims.py` gains `least_privilege`, `row_level_security` and `database_isolation`, each naming the registry requirements that prove it. Counts come from catalogs and JUnit, never hand-entered. | A claim's verdict is already computed from exactly the node IDs the registry lists, a proof missing from the artifact is `not_run` rather than `passed`, and a skip is not a pass. A bespoke evidence schema would have to re-derive all of that. | no |
| **D50** | Add pytest markers `database`, `live_host`, `destructive`. | `pytest.ini` runs `--strict-markers`; `live_host` and `external` already exist; `tests/conftest.py::ENVIRONMENT_VARIABLES` is a **closed tuple** and `tests/contract/test_environment_gates.py` proves every `live_host`/`external` test carries a `requires_environment` gate naming a registered variable. | **`database` and `destructive` are declared in `pytest.ini`.** Any new gate variable joins the closed tuple in the same commit. `destructive` additionally requires the disposable target of D51. | An undeclared marker is an error, not a typo — and a gate naming an unregistered variable produces a test that silently never runs anywhere. | no |
| **D51** | Destructive isolation tests use "a disposable third fixture or an explicitly recreated Project B test volume". | No disposable-project machinery exists. The only mutating live test is `test_removing_the_second_project_leaves_the_first_routed`, which stops Project B, checks Project A, restarts B, **and then asserts B came back**. | **Same discipline, and the disposable target is built explicitly.** A third project `project.gamma.yaml` (gitignored like the others) exists only to be destroyed, and every `destructive` test asserts its target is that project before touching anything. No destructive test may name `alpha-dev` or `beta-dev`. | A test that restores what it broke is why a failure to restore cannot pass silently. A destructive test with no declared target is one typo away from deleting the release-evidence project's volume. | no |
| **D52** | `max_connections: 100`, `shared_buffers_mb: 256`, two clusters. | The host is **3814 MiB total, no swap, 2 vCPU, 33 GB free** (`ubuntu-4gb-hel1-4`), already running Traefik, the socket proxy and four project containers with ~681 MiB used. | **The schema enforces a per-project memory budget and Compose sets `mem_limit`.** Session 3 defaults are `shared_buffers_mb: 128`, `max_connections: 50`, `work_mem_mb: 4`, `maintenance_work_mem_mb: 64`, and rendering **fails** when the declared budget across a manifest exceeds the host guardrail. | With zero swap the OOM killer is the only backstop and it does not choose politely — it can take Traefik, which drops every project's ingress at once. `max_connections: 100` per cluster is also the wrong shape for a design whose Session 4 answer to connection count is a pooler. | no |
| **D53** | *(§3.2 of this plan, before measurement)* Mounting the volume at the wrong path "produces a cluster that initialises into an anonymous volume and loses everything on recreate". | Measured against the locked digest, there are **three** behaviours, and the predicted one is not among them. `PGDATA` is `/var/lib/postgresql/18/docker`, but the image declares `VOLUME /var/lib/postgresql` — the *parent*. Mounting at **`/var/lib/postgresql/data`** (the pre-18 convention) makes the image **refuse to start, exit 1**, naming the unused mount. Mounting at **`PGDATA` itself** starts and persists, but Docker also creates a stray **anonymous volume** for the parent and splits the layout. Mounting at **`/var/lib/postgresql`** is correct: one mount, no anonymous volume. | **The mount target is `/var/lib/postgresql`, the declared `VOLUME`, not `PGDATA`.** The contract test asserts the target *and* that the service has exactly one volume mount, because "it persisted" is true of two of the three configurations and distinguishes nothing. | The dangerous configuration is the one that works. A test that only checked persistence would pass on the PGDATA mount and would not notice the anonymous volume until a `--renew-anon-volumes` or a `pg_upgrade` made it matter. The refusal case needs no guard: the image already stops. | no |
| **D57** | `SEC-DEFAULT-001` — "a newly created function is not executable by `PUBLIC`" — is satisfied by revoking the default: `ALTER DEFAULT PRIVILEGES … REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC`. | Measured against the locked image, that statement **reports success and stores nothing**. `pg_default_acl` stays empty, and a function created afterwards by `object_owner` still has `PUBLIC EXECUTE`. Tested both ways — inside `SET LOCAL ROLE`, and with an explicit `FOR ROLE` from a superuser session. An explicit `REVOKE ALL ON FUNCTION … FROM PUBLIC` does work, measured to leave `has_function_privilege('public', …)` false. | **The explicit per-function `REVOKE` is what carries the requirement.** It sits beside every `CREATE FUNCTION` in the set. The `ALTER DEFAULT PRIVILEGES` statement stays, with `FOR ROLE` named explicitly, as defence in depth on any version where it does work — and the migration says in place that it is not the mechanism being relied on. `SEC-DEFAULT-001`'s test must create a function and measure, never assert that the statement was issued. | This is the defect pattern exactly: a statement that looks like it establishes a posture, reports success, and establishes nothing. Had the requirement's test asserted "the migration contains ALTER DEFAULT PRIVILEGES", it would have been green for the entire life of the product over a cluster where every new function was world-executable. | no |
| **D58** | *(§8 invariant table)* API views apply caller RLS, and the negative proof is that a caller "cannot address `app` directly"; write RPCs derive ownership. | Both hold, but not by the construction the phrasing implies. A `security_invoker` view evaluates the **base table's** privileges as the caller, so the views are dead without `SELECT` on `app.notes`/`app.tasks` — and granting schema `USAGE` to fix that would also make `SELECT * FROM app.notes` work, dissolving the negative proof. A `SECURITY INVOKER` write RPC is worse: its body needs `USAGE` on `app` to `INSERT`, so it cannot exist without the grant. | **Table `SELECT` without schema `USAGE`** for the API roles, and the write RPCs are **`SECURITY DEFINER`**. Measured: schema `USAGE` is resolved when the view is created, by its owner, so the views return the caller's rows while `app.notes` raises "permission denied for schema app". The RPCs return `api.notes`/`api.tasks`, not the private row types, since a return type is resolved by the caller. | `SECURITY DEFINER` is safe here *only* because of the forced RLS in `0003`: the owner's own writes stay policy-checked and the policies key on the caller's claim rather than `current_user`. Without `FORCE`, the same function is an ownership-laundering primitive. Both halves of the boundary are asserted separately by `SEC-DB-002` — neither is safe to infer from the other. | no |
| **D55** | *(Run 2 of this plan, as implemented)* The container name is a per-project identity, and Session 3 declares it by setting `container_name:` so a test asserts the name the model states. | `compose.yaml` forbids `container_name` outright — "it is not project-scoped and would collide across two deployments on the same host" — and `test_model_does_not_use_container_name` enforces it structurally and passes today. §9.9 lists exactly four ADR-backed changes to passing tests, and this is not one of them. | **`container_name` is not set.** `database.container` records the name Compose derives (`<project>-<service>-1`) and `DEP-ISO-003` compares that string to the container actually running, in Run 8. It is a prediction until then, and it is written down once so the live test compares against the rendered document rather than a second f-string. | The stated hazard is a name that is not project-scoped; an interpolated project-scoped value would answer it, and the honest reason not to is that Session 3 has no ADR-backed licence to reopen a passing contract test for a convenience. It also carries no isolation weight of its own: the name is a function of `compose.project_name`, already in `MUST_DIFFER`, so two projects cannot collide here without colliding there first. | no |
| **D56** | Add `one_time_initialization_secret` to `schemas/secret-contract.schema.json`. | ADR 0008's sensitive-key policy matches a terminal `_`-delimited token, and `secret` is on the denylist. `assert_no_sensitive_keys` therefore rejects the whole contract file the moment that key exists — `load_secret_contract` raised on `secrets[0].one_time_initialization_secret`. | **The field is named `one_time_initialization`.** Meaning unchanged; the trailing token dropped. The `SAFE_KEY_ALLOWLIST` is deliberately not used: its own docstring says none of its members actually collides under terminal-token matching, and that it is "a guard with a test behind it, not a load-bearing set of exceptions". | Adding the first genuinely-colliding entry would convert the allowlist from a guard into the mechanism by which the policy is escaped, and every later field would have the same precedent available. Renaming costs one word. | no |
| **D59** | *(§5 Run 7)* Run 7 is five commands against the host, beginning `sudo ./deploy.sh … --through-session 3`. | That command exits `10`: `deploy.sh` caps at a literal `-le 2`. The session is a literal in four places — the cap, the entry point's own filename, `bin/project-runtime.sh`'s `--session 2` and `--profile session2`, and the systemd launcher's `--session 2`. The launcher is the serious one: it runs at boot with no operator to ask, so a Session 3 project restarted by systemd would have materialized Session 2's secrets and started Session 2's profile — no cluster — and `systemctl status` would have shown a clean start. | **The session is read, not repeated (ADR 0032).** `deploy.sh` reads `CURRENT_SESSION`; the deployed document gains a required `deployed_through_session` that the launcher reads with the `jq` it already uses for `source_commit`; `bin/project-runtime.sh` takes `--through-session N` as a required flag and derives the profile set cumulatively. `bin/deploy-session-2.py` becomes `bin/deploy-project.py`. | A ceiling test parametrized on `3, 9, 99` was measuring the wrong number the moment the release implemented Session 3; it is now `CURRENT_SESSION + n`, plus the half a ceiling test cannot give you — that the release does *not* refuse its own session. | **yes** |
| **D60** | *(§5 Runs 3, 6)* The migration plane is delivered: `compose.yaml` has a `dbmate` service, `bin/migrate.sh` has `status` and `up`, and `secrets.required.yaml` declares `migration_database_url`. | None of it runs. `migrate.py`'s `status`/`up` print the rendered set and `return 0` — `up` reported success having applied nothing. Nothing rendered the SQL to disk (D43's `migrations/*.sql` did not exist), the service had no `/migrations` mount, `--env APG_MIGRATION_DATABASE_URL` named a variable nothing set, and `app_private.migration_ledger` had been created by migration 0002 and never written to by anything. | **ADR 0034.** `rendering.write_rendered_migrations` writes the payload and its digests; `run` joins the Compose runtime allowlist with `--entrypoint`/`--env` refused; the secret becomes `migration_user_password` and the URL is assembled inside the container with every byte of the password percent-encoded; `bin/migrate.py` records the ledger **as the superuser**, so the migration plane cannot write its own audit record. | Measured, in this order: dbmate parsed a base64 password containing `/` as a port; then `permission denied for schema app_private` because dbmate's `CREATE TABLE IF NOT EXISTS` needs `CREATE` before the existence check; then `must be owner of table project_identity`, because bootstrap created it as the superuser and migration 0002 comments on it as the owner. Each was invisible to reading. | **yes** |
| **D61** | *(§5 Run 7)* `sudo bin/postgres-bootstrap.sh --project … --runtime --check` reports whether the cluster is in policy. | `--check` printed how many statements *would* run and returned `0`. `EXIT_CHECK_FAILED = 6` was defined, documented in the script's header, and never raised: against a cluster with no roles, no schemas, no extension and no credential, it returned `0`. | **ADR 0035.** `--check` asks the catalog nine questions and returns `6` with the list; `--apply` runs the statements and then asks the same questions, because psql accepting a statement is not the catalog holding it — Run 4's `ALTER DEFAULT PRIVILEGES` is the standing proof. | The first command of Run 7 was a green light that could not go red. Its expected first result on a fresh cluster is now `6` with nineteen violations, which is not a failure of the run. | **yes** |
| **D62** | *(§6.1)* The bootstrap plane creates "the dbmate table", and `secrets.required.yaml`'s grant surface reaches containers through the runtime override. | The dbmate table was not created by anything, and **no component rendered a `secrets:` block at all**. `runtime_override.build_override` returns router labels only; `compose.sh`'s `assert_secret_sources_are_project_scoped` scanned a resolved model containing no `file:` sources and passed. Session 2 could not notice: its one secret belongs to a `session2-verify` service no deploy starts, and its proofs read files on disk. Session 3 fails outright — nothing mounts `POSTGRES_PASSWORD_FILE`, so the cluster does not initialise. | **ADR 0033.** A second override carries the grant surface, rendered by `bin/project-runtime.sh` *after* materialization and *before* start, because the generation identifier changes on every start. `compose.sh` requires it for `up`, `restart` and `run`. Bootstrap creates `app_private.schema_migrations` owned by the object owner with three grants. | The Session 2 secret proofs measure the filesystem, which is why a model with no grants passed a suite whose subject was secrets. `docker compose config` reporting `top-level secrets: None` is what closed it. | **yes** |
| **D63** | *(§5 Run 6)* The fourteen activated requirements are proved by tests that read the catalog rather than migration source. | They do, and three of them had never run. Two encoded psql's *printed* boolean (`'f f t'`, `notes=t/t`) where `boolean \|\| text` yields `false`/`true`, so both would have failed on first contact with any cluster; one asserted `count(*) == 1` after a seeding fixture that adds a row per run, so it could pass once on a virgin cluster and never again. | **All three fixed against a live cluster before the host.** The counts are compared against the owner's actual rows read as the superuser, so the assertion survives re-seeding — which a convergence check and every post-reboot run require. | Run 6 was offline by design and said so; this is the cost of that, paid where it was always going to be paid. The properties were right. `bin/postgres-bootstrap.py` made the identical `'f f t'` mistake independently, which is how the spelling was found. | no |
| **D64** | *(§5 Run 7)* The gate that passes here passes on the host; Session 2 proved it on both. | It did not, and the reason is a class of defect Session 2 could not surface. `test_evidence_collisions.load_fixture` read *the first document in `.generated/`*, and `evidence.load_rendered` reads *all of them*. A development machine renders only the two committed fixtures; the host also holds `alpha-dev` and `beta-dev`, rendered by the **previously installed release** — schema v2, no `database.container`. Six contract tests failed on the host with `KeyError: 'container'` with nothing wrong on it. | **The fixture is named, and a mixed set is refused.** `load_fixture` reads `fixture-alpha-dev` and asserts its schema version; `load_rendered` raises naming each stale project and the `--render-only` that fixes it. Skipping them was rejected: it would drop a real project from the isolation count at exactly the moment somebody upgraded the release, and the count would stay `0`. | A directory listing is not a version. Both readers were green here for the same reason — this machine has never rendered anything but fixtures — and neither had ever seen a two-release host. This is why the gate runs on the host as well, and it is the first time that has paid for itself. | no |
| **D65** | *(Session 2, latent)* A `sudo ./deploy.sh` hands the rendered directory back to the operator, so an unprivileged render works afterwards. | It hands back `.generated/<key>/` and not `.generated/.locks/<key>.lock`, which `rendering.project_lock` opens at mode `0600` before anything else happens. `./deploy.sh --render-only --project project.alpha.yaml` on the host died with `PermissionError` on the lock — a project deployed under sudo could never be re-rendered by its operator again, and the message names a lock rather than a permission the operator can reason about. | **The lock directory and its files are restored with the rendered directory**, and the `chown` loop catches per target rather than per run, so one unreachable path no longer abandons the rest. | Found because D64 made the gate demand a current render of every project, which is the first time anyone re-rendered `alpha-dev` as `op` since Session 2 deployed it. Two latent defects, and the second was only reachable through the first. | no |
| **D66** | *(§5 Run 7)* `sudo bin/materialize-secrets.sh … --session 3` materializes the Session 3 secrets. | It exits `8`: `HTTP 404` from the provider, because the two secrets exist nowhere. `bin/materialize-secrets.py` reads `secrets.required.yaml`; `bin/bootstrap-providers.py` created exactly one secret and created it **by name** — `"APG_SESSION2_SENTINEL"`, a literal. One writer with a hard-coded name and one reader with a declared contract, agreeing for exactly as long as the contract had one entry. The folder had the same shape and had not bitten: bootstrap wrote into `host.yaml`'s `runtime_folder` while materialization reads each secret's `provider_path`, and both said `/runtime` until Session 3 said `/database`. | **ADR 0036.** `declared_provider_secrets(session)` drives creation from the contract; `add_sentinel` becomes `add_missing_secrets`, so a project bootstrapped in an earlier session converges by acquiring what a later one declared. An existing secret is adopted, never overwritten. `managed_resources` stays a closed enum — it is the licence to destroy — and a contract test asserts it covers every required secret the contract declares. | Overwriting would have been the worse fix: `postgres_init_superuser_password` is read by the image only when the data directory is empty, so a new value changes the file and not the cluster, and materialization then delivers a password that cannot open the database it is for. | **yes** |
| **D67** | *(`bin/bootstrap-providers.sh --help`)* `--plan` "contacts the provider read-only and writes nothing. Needs no root." | It raises `PermissionError` out of `pathlib.is_file()` and prints a traceback. The state file and its directory are root-owned `0600`/`0700`, so an unprivileged reader cannot even stat it. Invisible in a checkout, where there is no `/etc/agentic-postgres` and the path is genuinely absent. | **Unreadable is a prerequisite failure (exit 3) naming sudo, never folded into "absent".** The help text says what is actually true. The test creates a directory the caller cannot traverse rather than mocking, because the failure is `is_file()` raising. | Folding it into absent would be worse than the traceback: `--plan` would propose creating an Infisical project, a machine identity and a client secret for a project that already has all three. Found by running `--plan` on the host as a pre-flight before handing the operator an `--apply`. | no |
| **D54** | *(§5 of this plan, as written)* Run 1 moves `CURRENT_SESSION` to `3` while the five existing Session 3 placeholders stay `future` until Run 6. | Those two cannot both hold. `test_no_requirement_at_or_before_the_gate_session_remains_future` fails for exactly `SEC-DEFAULT-001`, `SEC-FUNC-001`, `SEC-OWNER-001`, `SEC-RLS-001`, `SEC-VIEW-001` the moment the constant reads `3`, and the nine new IDs join them. Verified by running the gate's registry suite under `APG_ACCEPTANCE_SESSION=3`. | **`CURRENT_SESSION` moves in Run 6, not Run 1**, in the same commit that deletes all fourteen placeholders and replaces them with real tests. Run 1 ships the ADRs, the nine new IDs as placeholders, and the two marker declarations. | The alternatives were a red gate through Runs 1–5, which suspends the only signal that would catch a Run 2 regression, or an exemption inside the overdue check, which weakens a currently-passing P0 contract test to make an unrelated change convenient. The constant and the implementations it vouches for move together or the constant means nothing. | no |

---

## 2. What Session 3 adds to the acceptance registry

### 2.1 Requirements that already exist and are activated

Each has a `future` placeholder in `tests/security/test_future_security_boundaries.py` today. Activation deletes the placeholder, writes real tests, and updates the registry's `test_nodeids` to name them.

| ID | Claim | Placeholder to remove |
|---|---|---|
| `SEC-RLS-001` | Owner-scoped rows are isolated by owner under forced RLS | `test_user_a_cannot_access_user_b_rows` |
| `SEC-VIEW-001` | Security-invoker API views expose only caller-visible rows | `test_security_invoker_view_preserves_rls` |
| `SEC-FUNC-001` | Ungranted functions cannot be executed by API roles | `test_api_role_cannot_execute_ungranted_functions` |
| `SEC-DEFAULT-001` | A newly created function is not executable by `PUBLIC` | `test_newly_created_function_is_not_executable_by_public` |
| `SEC-OWNER-001` | The object owner is a non-login role | `test_object_owner_is_a_non_login_role` |

### 2.2 New requirement IDs

Added only where no placeholder covers the claim. Prefixes follow the frozen catalog in `docs/product-contract.md` §3.

| ID | Requirement | Priority |
|---|---|---|
| `DBX-PG-001` | The locked PostgreSQL 18 image runs with pgvector present at the locked version in `extensions` | P0 |
| `DBX-PG-002` | PostgreSQL publishes no host port, joins no edge network, and carries no Traefik label | P0 |
| `DBX-PG-003` | An existing data volume is bound to one project identity and a mismatch is refused | P0 |
| `DBX-MIG-001` | Bootstrap authority and migration authority are distinct and least-privileged | P0 |
| `DBX-MIG-002` | Rendered migrations are deterministic and checksum-consistent with source | P0 |
| `DBX-MIG-003` | An applied migration cannot be silently edited, removed, or reordered | P0 |
| `SEC-DB-001` | No runtime role holds superuser, `CREATEDB`, `CREATEROLE`, replication, or `BYPASSRLS` | P0 |
| `SEC-DB-002` | `public`, `app` and `app_private` boundaries match the contract | P0 |
| `DEP-ISO-003` | Two projects have isolated clusters, volumes, roles, credentials and identity sentinels | P0 |

`SEC-RLS-002` and `SEC-RLS-003` from the runbook are folded into `SEC-RLS-001`: one requirement may name many node IDs, and "notes" and "tasks" are two tables under one claim, not two claims. The forced-RLS-includes-the-owner case is a node ID under `SEC-RLS-001` as well.

### 2.3 Registry mechanics

`docs/acceptance-matrix.md` and the `product-contract.md` marker block are **generated** from the registry by `bin/render-acceptance-matrix.py`; the gate runs `--check` and fails on drift. Never hand-edit either.

`CURRENT_SESSION` moves from `2` to `3` in `src/agentic_postgres/__init__.py`. That single constant drives `APG_ACCEPTANCE_SESSION` (ADR 0014), which is what makes "no requirement owned by session ≤ 3 is still a placeholder" a gate failure rather than a convention.

### 2.4 ADRs to write

| ADR | Title |
|---|---|
| 0026 | Bootstrap authority is separate from migration authority |
| 0027 | The output schema gains a version, and a migration path with it |
| 0028 | Source migrations are templates; the immutable unit is the rendered payload |
| 0029 | Request identity is a trusted transaction-local claim, not an authenticated one |
| 0030 | A project volume carries an identity, and a mismatch is never adopted |
| 0031 | Exit code 11: the data is not yours |

---

## 3. Environment feasibility — what Session 3 adds

### 3.1 The four execution environments, and which is new

Session 2 established three: `offline` (a checkout), `host` (the VPS), `external` (a different network). Session 3 adds no environment but changes what `offline` can reach.

| Concern | Where it is provable |
|---|---|
| Manifest, schema, render determinism, migration manifest, released lock, placeholder rules | offline |
| Compose model shape, no published port, no edge network, no Traefik label on `postgres` | offline |
| Image UID/GID, `PGDATA`, extension version, dbmate flag acceptance | **needs the images**; a locked-digest pull in CI or on the host |
| Roles, schemas, ACLs, RLS, views, functions, default privileges | host |
| Two-project isolation, restart and reboot convergence | host |
| Port 5432 closed from the public internet | external — already covered by `SEC-NET-001`, and meaningful for the first time |

The last line is worth stating plainly: `tests/external/test_session2_public_edge.py` has scanned 5432 since Session 2 and found it closed **because nothing was listening**. From Session 3 on, that test measures a firewall and a Compose model instead of an absence. Its eight IPv6 cases still skip for want of transit (D35), so the IPv4 arm carries the whole claim.

### 3.2 Image contracts must run before anything is deployed

Three numbers the runbook tells us to assume must instead be measured, and each has already burned this repository once in a neighbouring form:

- the PostgreSQL image's runtime **UID/GID**, which `secrets.required.yaml` consumers must match exactly (Session 2's `65532` is asserted against the service's `user:` for the same reason). It is **not** `65532` here, and the container's default user is not the server's user: the entrypoint starts as root and drops privilege;
- **`PGDATA`** for the PostgreSQL 18 image family, and separately the path the image declares as its `VOLUME` — which is not the same path. See D53: two of the three plausible mount targets persist data, so persistence is not the property that distinguishes them;
- the **dbmate flags** `--migrations-table`, `--strict`, `--no-dump-schema` and `--env-file`, and on which subcommands the locked release accepts them. They do **not** all sit in one position: some are global-only and must precede the subcommand, and `--strict` is subcommand-only and exists on a proper subset of the subcommands. A flag in the wrong position is `exit 2`, which is loud, but a global flag silently omitted is not.

All three were measured against the locked digests before Run 1, and the answers changed two design decisions (D53, and the `user:`/secret-mode pairing in Run 3). **`tests/contract/test_image_contracts.py` is the only place the values themselves are written down** — deliberately not here, so that there is one authority and it is executable. The plan records only what the shape of the answer forced.

### 3.3 Capacity, stated as numbers

```
total 3814 MiB     swap 0     vCPU 2     free disk 33 GB
in use before Session 3: ~681 MiB across traefik, socket-proxy and four project containers
```

Zero swap is the constraint that matters, but not in the way the arithmetic above suggests. **Two clusters at the D52 defaults were measured under load** — 49 backends each, driven with pgbench — and the formula `shared_buffers + maintenance_work_mem + (max_connections × work_mem × concurrent sorts)` turns out to describe almost nothing that the OOM killer looks at:

```
per cluster, idle       anon   5 MiB   shmem  12 MiB   file(cache)  59 MiB
per cluster, 49 backends anon  62 MiB   shmem 140 MiB   file(cache) 410 MiB
```

On a box with no swap, `file` is reclaimable and `anon + shmem` is not. The unreclaimable footprint is therefore **~218 MiB per cluster**, ~436 MiB for both, against ~3133 MiB free. `max_connections × work_mem` never materialises because `work_mem` is a per-sort-node ceiling allocated on demand, not a per-backend reservation. **The D52 defaults survive contact with two real clusters, with room.**

The correction that matters is what `mem_limit` is. A container memory limit caps **page cache too**, so sizing it from the formula — which counts only anonymous memory — produces a limit the cluster reaches immediately and then lives against. At `mem_limit: 512m` both measured clusters pegged their limit exactly, with 361 and 366 reclaim events and no OOM kill: functional, and permanently thrashing its own cache. That is a performance cliff no green test would show, and it is the same defect pattern as everything else in this repository — a number that looked measured and was describing something other than what it was applied to.

So the guardrail and the limit are two different numbers. **The guardrail is computed on unreclaimable memory (`shared_buffers + maintenance_work_mem + a per-backend anon allowance`), and `mem_limit` is set above it with deliberate cache headroom.** Session 3 therefore treats the budget as a validated manifest field, not an operator's judgement:

- schema-enforced defaults `shared_buffers_mb: 128`, `max_connections: 50`, `work_mem_mb: 4`, `maintenance_work_mem_mb: 64`;
- a declared host guardrail over **unreclaimable** memory, and a **render-time failure** when the sum across deployed projects exceeds it;
- explicit `mem_limit` and `shm_size` on the Compose service, `mem_limit` set above the guardrail rather than equal to it. `shm_size` must exceed `shared_buffers`, since PostgreSQL's dynamic shared memory lands in `/dev/shm` and Docker's 64 MiB default is below the 128 MiB `shared_buffers`;
- `bin/session-03-check.sh --mode host` records observed `anon`, `shmem` and `file` per cluster in evidence — the three separately, never a single "memory used" figure, because the whole point is that only two of them count.

A `max_connections` of 50 is not a compromise. Session 4's answer to connection count is a pooler; a large per-cluster limit would make the pooler decorative.

### 3.4 What CI can and cannot assert

CI runs `bin/session-02-check.sh --mode offline` today and will run `--mode offline` for Session 3. It can assert every render, manifest, lock, placeholder and Compose-model claim. It cannot assert a role attribute, an ACL, or an RLS policy, because those require a cluster. The image-contract tests sit on the boundary: they need a container runtime and the locked digests, and they are marked so that a runner without Docker reports that rather than a verdict (ADR 0018).

---

## 4. Safety plan for irreversible operations

Session 2's irreversible operations were about losing access to a host. Session 3's are about losing data.

### 4.1 The data volume

`POSTGRES_VOLUME_NAME` is already derived and already in `compose.env`; Session 3 is the first session in which it holds anything.

- **`bin/compose.sh` already refuses `-v` in edge scope; Session 3 extends that refusal to project scope.** `down -v` on a project stack is the one command that destroys a database while looking like a stop.
- Nothing in `deploy.sh`, `bin/project-runtime.sh`, `bin/postgres-bootstrap.sh`, `bin/migrate.sh` or `bin/session-03-check.sh` removes a volume, under any flag.
- Volume removal exists in exactly one place: an explicit disposable-project command that refuses any project key other than the declared disposable one, requires the key back as confirmation, and refuses when the target's identity sentinel does not say disposable.

### 4.2 The identity sentinel

Before first initialization, a candidate project-instance UUID is written to root-owned state. Bootstrap creates exactly one row in `app_private.project_identity` carrying it. From that commit on, the UUID is bound to the volume.

The rules that make this safe rather than decorative:

- a crash between sentinel commit and state publication **recovers** the UUID from the candidate record; it never generates a new one against a non-empty volume;
- a candidate is discarded only when sentinel creation never committed **and** an explicit check proves the volume is still uninitialised;
- identity comparison uses only the immutable fields — project key, database name, Compose project name, instance UUID. Not the source commit, not the manifest checksum, not the template version, because those change legitimately on every redeploy and a valid volume must not start looking foreign;
- a mismatch **stops** with exit `11`. Bootstrap never rewrites the row to adopt a volume.

This is the same rule as ADR 0011's "ownership is recorded by ID, never adopted by name", applied to a filesystem instead of a provider.

### 4.3 Applied migrations

An applied migration is immutable. The remedy for a mistake is a new migration, never an edit.

- `migrations/released.lock.json` is produced by `bin/migrate.sh freeze-lock` from a clean tree, reviewed, and committed **before** the final gate. The gate verifies it and never creates or rewrites it.
- No migration may be applied to a non-disposable target until its manifest entry appears in the committed lock.
- The preflight compares five things and refuses on any disagreement: applied dbmate versions, the database ledger, the source manifest, the released lock, and the current rendered set.
- Session 3 migrations are transactional. `transaction:false` is not permitted.

### 4.4 The one-time initialization secret

`postgres_init_superuser_password` is consumed by the image entrypoint only when the data directory is empty. Changing its file does **not** rotate the superuser password of an already-initialised cluster, and nothing in Session 3 pretends otherwise. Migration-password rotation is a separate coordinated flow: publish a candidate generation, `ALTER ROLE` through the privileged local path, verify authentication against the candidate, then activate the generation atomically.

---

## 5. Build order — nine runs

Each run ends with `bin/session-01-check.sh` exiting `0` on a clean tree. Runs 1–6 need no host.

### Run 1 — ADRs, requirements, and the session constant
*Offline.*

Write ADRs 0026–0031 and index them. Add the nine new requirement IDs to `tests/acceptance-registry.yaml`, each with a `future` placeholder. Declare the `database` and `destructive` markers.

**`CURRENT_SESSION` stays at `2` — it moves in Run 6 (D54).** The five existing placeholders stay `future` for the reason the runbook gives, and the nine new IDs need placeholders too: `test_every_registered_node_id_is_collectible` means a registered ID must name a test pytest can collect, and a placeholder is the only collectible thing that exists in Run 1. But a gate session of `3` makes all fourteen overdue under `test_no_requirement_at_or_before_the_gate_session_remains_future`, so the constant cannot move until the implementations do.

The new placeholders go where their prefix family already lives: `SEC-DB-001/002` beside the other Session 3 security placeholders, `DEP-ISO-003` beside `DEP-ISO-001`, and the six `DBX-PG`/`DBX-MIG` IDs in a new `tests/contract/test_future_database_platform.py` marked `database`.

```
python bin/render-acceptance-matrix.py --write     # regenerate both documents
bin/session-01-check.sh                            # 0
```

### Run 2 — Manifest and output schema
*Offline.*

Extend `schemas/project.schema.json`'s existing `database` block with the Session 3 fields and the D52 bounds. Bump `schemas/outputs.schema.json` to `schema_version: 3` on both branches, extend `$defs.database`, add the `v2 → v3` path to `output_migrations.py` and a committed `tests/fixtures/outputs-v2.json`.

Add the new database identity fields to `evidence.ISOLATED_FIELDS` and `test_render_isolation.MUST_DIFFER` — the container name and the volume name are per-project identities and a collision between them is exactly what `DEP-ISO-003` denies.

`direct` and `pooled` remain `unavailable` (D41).

### Run 3 — Compose model, secrets, image contracts
*Offline, plus a digest pull for the image contracts.*

Add `postgres` under profile `session3` and `dbmate` under profile `migration` to the root `compose.yaml`. Extend `compose.env`'s key set and `test_compose_env_defines_exactly_the_expected_keys` with it. Append the two secrets to `secrets.required.yaml`, add `one_time_initialization_secret` to `schemas/secret-contract.schema.json`, and write `tests/contract/test_image_contracts.py` (§3.2).

The Compose assertions that must hold and are already written: `test_no_project_service_publishes_a_host_port`, `test_only_traefik_publishes_host_ports`, `test_two_projects_render_disjoint_resource_names`. `postgres` must not weaken any of them.

### Run 4 — Migration manifest, renderer, released lock
*Offline.*

`migrations/manifest.json`, the five templates under `migrations/templates/`, the purpose-built renderer, `migrations/released.lock.json`, and their contract tests including the mutation cases: edited applied migration, removed migration, duplicate version, unknown placeholder, secret-like placeholder, over-length identifier, non-deterministic render.

The renderer substitutes only typed identifier and literal placeholders from a fixed schema. No control flow, no arbitrary expression, no secret placeholder, no current-deployment metadata. A minimal renderer is preferred over a general template engine, for the reason `render-config.py` learned the hard way in Run 7 of Session 2: a substitution that also matched the comment documenting it produced a file Traefik silently discarded.

### Run 5 — `bin/postgres-bootstrap.sh` and `bin/db.sh`
*Offline command contracts; no cluster yet.*

Both new scripts join `tests/contract/test_cli_contract.py`'s script list and `test_repository_contract.py::REQUIRED_PATHS`. Both are covered by `tests/contract/test_root_script_policy.py`: `set +x` as the first executable line of anything handling a credential, no secret in `argv`, no `eval "$("`.

`--check` is the default for bootstrap and changes nothing, following `bin/provision-host.sh`. Argument errors exit `2` before the privilege check exits `3`, so an operator learns they mistyped a flag without first obtaining root.

### Run 6 — Promote `bin/migrate.sh`, write the five migrations
*Offline.*

`bin/migrate.sh` leaves `FUTURE_STUBS` and gains real command-contract tests (D48, ADR 0017), including `freeze-lock` as a thin command over `migrations.build_lock`.

**The five migrations were written in Run 4, not here.** Run 4 has to produce `released.lock.json`, and a lock over templates whose SQL is still to be written would be a digest of a placeholder — invalidated by the run that filled it in, which ADR 0028 says must then be a reviewed commit. Writing them once, in the run that locks them, is the only order in which the lock means anything.

**All fourteen Session 3 placeholders are deleted and `CURRENT_SESSION` moves to `3`, in one commit (D54).** The five in `test_future_security_boundaries.py` and the two `SEC-DB-*` beside them become real tests in `tests/security/test_session3_*.py`; the six in `test_future_database_platform.py` and `DEP-ISO-003` become the contract, image and isolation tests Runs 3–5 prepared. The constant and the implementations it vouches for move together — that is the whole reason it is a gate input.

This is the run where the gate stops being satisfiable offline: the new tests skip in a checkout and must not be written so that a skip looks like a pass.

### Run 7 — Make Session 3 deployable, then Project A on the host
*First cluster. Two halves, and the first one is offline.*

**The five commands below could not run.** Runs 3–6 built the command surfaces,
the renderer and the contracts; what none of them built is the path that carries
a Session 3 deployment onto a host. Five things were missing in the same
direction, each recorded above: the deploy refused session 3 (**D59**), nothing
rendered a Compose `secrets:` block so the cluster could not initialise
(**D62**), `migrate up` applied nothing (**D60**), `--check` could not fail
(**D61**), and three of Run 6's activated tests had never met a cluster
(**D63**). Four ADRs — 0032, 0033, 0034, 0035.

All of it was verified against a real cluster before the host: a host-shaped
`/etc` and `/var/lib` locally, the product's own installer, and then the same
commands in the same order.

```
sudo bin/materialize-secrets.sh --project project.alpha.yaml --requirements secrets.required.yaml --session 3
sudo ./deploy.sh --host host.yaml --project project.alpha.yaml --capabilities capabilities.yaml --through-session 3
sudo bin/postgres-bootstrap.sh --project project.alpha.yaml --runtime --check
sudo bin/migrate.sh --project project.alpha.yaml --runtime status
sudo bin/db.sh --project project.alpha.yaml --runtime status
```

The deploy owns bootstrap → migrate → observe (D46), so by the time the last
three run, the cluster is converged and they are verifications: `--check`
returns `0`, `status` reports five applied, `db.sh status` names the server and
its extensions.

Then `--apply` and `up` a second time and prove convergence: no role churn, no
new migration, identical ledger checksums. Measured locally before the host:
identical ledger digest, identical role digest, `0` migrations applied on the
second pass, and the volume's instance UUID recovered rather than regenerated.

### Run 8 — Project B, isolation, convergence
*Second cluster.*

Repeat Run 7 for `project.beta.yaml`, then the isolation suite: A's migration credential fails against B and vice versa, A's role names do not exist in B, a row written to A is absent from B, stopping B leaves A healthy, and an identity mismatch against an existing volume is refused.

Restart the container, restart the project unit, and reboot the host in a maintenance window. Confirm systemd restores both projects from the recorded immutable release, secrets are still valid, data persists, and the security suite is still green.

Destructive volume tests run against the disposable third project only (D51).

### Run 9 — Gate, evidence, documentation
*Both environments.*

```
sudo bin/session-03-check.sh --mode host --host host.yaml \
  --project-a-outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json \
  --project-b-outputs /etc/agentic-postgres/projects/beta-dev/outputs.json
python bin/write-session-evidence.py --session 3 …
jq -e '.tests.row_level_security=="passed" and .tests.database_isolation=="passed"' evidence/session-03.json
python bin/render-acceptance-matrix.py --check
git status --porcelain
bin/session-01-check.sh
```

Documentation: `docs/database.md`, `docs/migrations.md`, `docs/database-security.md`, `docs/session-03-operator-guide.md` — flat in `docs/`, added to `REQUIRED_PATHS`, and linked from `README.md` and `docs/handoff.md`. If a systemd unit's `Documentation=` gains one of them, `test_every_documentation_url_names_a_file_that_exists` will hold the reference to a file that exists.

---

## 6. The two execution planes

The runbook's central structural decision survives intact; only its plumbing changes.

### 6.1 Cluster bootstrap plane

Root-controlled, container-local, over the Unix socket as OS user `postgres`. It creates or verifies the thirteen roles and their membership options, the identity sentinel, `app_private`, the dbmate table, the ledger table, the `extensions` schema, the pgvector extension at the locked version, and the database-level `CREATE`/`TEMPORARY`/`CONNECT` hardening.

It is not reachable by any runtime service, and it is not a general-purpose SQL endpoint. `bin/db.sh sql` executes only generated, hash-verified files from an allowlist.

### 6.2 Database migration plane

dbmate runs as `migration_user` over the project-internal network. That role has `LOGIN`, `NOINHERIT`, and no superuser, `CREATEDB`, `CREATEROLE`, replication or `BYPASSRLS` attribute. It reaches owner authority only through an explicit membership:

```sql
GRANT <object_owner> TO <migration_user> WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;
```

Catalog tests inspect the membership option columns directly. Inferring the behaviour from the role's own `INHERIT` attribute would pass for the wrong reason.

Every migration's `up` block begins `SET LOCAL ROLE <object_owner>` and ends `RESET ROLE` before dbmate records the version as `migration_user`. The `down` block raises `AP900` deliberately: released platform migrations are fix-forward only.

### 6.3 Role activation state

`migration_user` is the only non-bootstrap role created with `LOGIN` and a live credential in Session 3. Every other service identity is a `NOLOGIN NOINHERIT` stub with a null password verifier, and bootstrap clears an unexpected verifier rather than tolerating it. Activating one is its owning session's job: set `LOGIN`, issue the credential through the secret-generation flow, regenerate and reload `pg_hba.conf`, and add a regression test.

`pg_hba.conf` lists **login roles explicitly**, never `+group_role` membership. Rule order is: `local` peer for `postgres`, then `host all postgres all reject`, then SCRAM for the approved login roles on the project database, then explicit rejects. No `trust` rule, ever, and the loaded file is validated through `pg_hba_file_rules`.

---

## 7. Evidence and claims

Session 3 adds three claims to `evidence_claims.CLAIMS`:

| Claim | Requirements |
|---|---|
| `least_privilege` | `SEC-DB-001`, `SEC-DB-002`, `SEC-OWNER-001`, `SEC-DEFAULT-001`, `SEC-FUNC-001` |
| `row_level_security` | `SEC-RLS-001`, `SEC-VIEW-001` |
| `database_isolation` | `DEP-ISO-003`, `DBX-PG-003` |

Each resolves from JUnit against exactly the node IDs the registry lists. A missing node ID is `not_run`, a skip is not a pass, and each claim is measured in the one environment whose marker its live proofs carry — all three are host claims. Their environment-free proofs run through `run_claim_proofs`, as `isolation` and `secret_leakage` already do.

Observed counts — RLS tables, forced-RLS tables, security-invoker views, approved `SECURITY DEFINER` functions, unapproved `PUBLIC EXECUTE` grants, dangerous runtime roles — are read from `pg_catalog` at evidence time, never hard-coded into the writer. That is the whole point of ADR 0025 and the defect it was written for.

Evidence contains no password, no password hash, no credential-bearing URL, no secret-file content.

---

## 8. Security invariant matrix

| Invariant | Positive proof | Negative proof |
|---|---|---|
| PostgreSQL is project-internal | A project service reaches 5432 on the internal network | No published port in the Compose model; `SEC-NET-001`'s external scan finds 5432 closed |
| Runtime roles are least-privileged | Each role performs its named operation | Catalog tests reject superuser, `BYPASSRLS`, `CREATEROLE`, database `CREATE`, owner escalation |
| Private schemas are private | Owner and migration process manage them | `anon`/`authenticated` cannot address `app_private` |
| API views apply caller RLS | A sees A's rows through `api.notes` | A sees no B rows and cannot address `app` directly |
| Forced RLS includes the owner | Owner under A's context sees A's rows | Owner under A's context does not see B's rows |
| Write RPCs derive ownership | A's created note belongs to A | A caller cannot choose B as owner |
| Function search path is safe | The RPC works under ordinary context | A temporary object cannot intercept resolution |
| Default execution is revoked | An explicitly granted RPC executes | A newly created ungranted function does not |
| Migration source is immutable | Ledger and source agree | An edited applied template fails hard |
| Volume identity is fixed | A matching redeploy converges | A mismatch is refused with exit `11` |
| Projects are isolated | Each keeps its own data | Cross-project credentials, roles and rows all fail |

---

## 9. Risks and stop conditions

**Halt — do not work around.**

1. **A project-identity mismatch against a non-empty volume.** Stop. Record the expected and observed non-secret identities. Do not rewrite the sentinel. Recovery is selecting the correct volume or a reviewed migration plan — never adoption.
2. **Checksum drift between source, lock, ledger and rendered set.** Stop all migration activity. Determine whether history was rewritten, context changed, or the database was altered directly. Never overwrite a ledger row to silence it.
3. **A migration committed but a post-migration security check failed.** The migration stays. The deployment is unsuccessful. The remedy is a fix-forward migration, never a manual patch that leaves history inconsistent.
4. **Any cross-user visibility or modification in the RLS suite.** Release blocker. Do not compensate with an application-layer filter.
5. **The leak scanner finds a database credential anywhere.** Rotate, fix, re-run from a clean generation. Do not add the path to an exclusion list.
6. **PostgreSQL cannot initialise.** Do not delete the volume automatically. Verify the mount target, `PGDATA`, that no anonymous volume exists, and the image digest first.
7. **An extension version mismatch.** No automatic upgrade during an ordinary deploy. An upgrade is a dedicated migration with backup and compatibility tests.
8. **The host runs out of memory.** With no swap this shows up as a killed container, possibly Traefik rather than PostgreSQL. Reduce the declared budget in the manifest; do not raise the guardrail to match reality.
9. **A currently-passing test would have to be weakened and it is not an ADR-backed change in this plan.** The ADR-backed changes are exactly: `outputs.schema.json` version and `$defs.database` (D40, ADR 0027), the exit-code table (D42, ADR 0031), `test_compose_env_defines_exactly_the_expected_keys` (D43), and `bin/migrate.sh` leaving `FUTURE_STUBS` (D48, ADR 0017). Anything else turning red is a stop condition, not a fix.
10. **`bin/session-01-check.sh` cannot be made to exit `0`** by those four changes. That means Session 3's design has broken a Session 1 or Session 2 guarantee this plan did not find. Halt and bring it back to the divergence table.

---

## 10. Open items carried in

These are not Session 3's to fix, but Session 3 runs on top of them.

- **`requirements-dev.in` pins nothing**, so `bin/lock-dev-deps.sh --check` re-resolves against PyPI and fails the day any dependency ships. It broke once during Session 2's Run 8. Pinning the input would make `--check` a test of what this repository decided rather than of what PyPI offers today.
- **ADR 0019's follow-up CI job is unbuilt.**
- **The Infisical control-plane identity holds organisation admin.** Session 3 adds two more secrets to a store that identity can read entirely.
- **Secret generations accumulate with no pruning.** Session 3 doubles the rate.
- **IPv6 is unmeasured from outside** (D35). Session 3 is the first session in which something worth reaching is listening, so this matters more than it did.

---

## 11. Session 4 handoff

Session 4 receives two healthy project-isolated clusters, thirteen roles with a settled membership topology, one active login credential and eleven `NOLOGIN` stubs awaiting explicit activation, five applied immutable migrations, a forced-RLS notes/tasks domain, security-invoker read views, two narrow write RPCs, and a database security suite with evidence.

`database.direct` and `database.pooled` are still `unavailable` with `available_from_session: 4`. Designing them — including the schema version that carries a client-facing endpoint — is Session 4's first task, and `DBX-005` is the requirement that says it must not be publicly reachable.

Session 4 may not change the meaning of an existing role without a migration and a test, give a pooled client owner or migration credentials, disable RLS for compatibility, put a password in `outputs.json`, or run dbmate through the pooler.

Its first preflight runs Session 3's gate, or a documented non-destructive equivalent, and refuses to proceed when the database security invariants are not green.
