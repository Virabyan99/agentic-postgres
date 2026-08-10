# Session 4 implementation plan — PgBouncer and a standard database developer experience

**Primary outcome.** Each project exposes a transaction-pooled PostgreSQL
transport for ordinary application traffic and a restricted direct transport for
migration and operations, with separate least-privileged access profiles, safe
tunnel tooling, and verified compatibility with the locked Prisma, Node `pg`,
Psycopg and `psql` clients.

**What this document is.** The Session 4 runbook, rewritten against the
repository that exists. The runbook it replaces was written on top of Sessions
1–3 *as those documents described them*, and Sessions 1–3 diverged from their own
documents in eighty recorded places. Its structure, its scope boundaries and most
of its security judgement survive intact. Its paths, command shapes, schema
versions, requirement IDs, exit codes and pinned versions do not.

Per the standing rule — *never silently reconcile a conflict between a runbook
and the code* — every one of those conflicts is a numbered divergence below
rather than a quiet edit. The `D` sequence continues from Session 3, which ended
at **D80**.

---

## 1. Runbook divergences

| # | Runbook says | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D81** | Deployed state is `/var/lib/agentic-postgres/projects/{project_key}/outputs.json`; pool state goes beside it. | ADR 0020 split the roots two sessions ago. Configuration and the deployed document live in **`/etc/agentic-postgres/projects/<key>/`** (`outputs.json`, `manifest.yaml`, `secrets.required.yaml`, `compose.env`, `active-secret-generation.json` is under the secret root); generated output is installed at **`/var/lib/agentic-postgres/rendered/<key>/`**; secret generations at **`/var/lib/agentic-postgres/secrets/<key>/generations/<id>/<consumer>/`**. Host-level JSON state is `/etc/agentic-postgres/<name>-state.json` — `edge-state.json` is the precedent. | **Every path in the runbook is rewritten to the real roots.** Pool state is `/etc/agentic-postgres/projects/<key>/pool-state.json`; the port registry is `/etc/agentic-postgres/database-port-allocations.json`. | A plan that names a path nothing writes produces an operator instruction nobody can follow — which is exactly what D68 cost half a run to discover. An example path is not a fact until something has run it. | no |
| **D82** | The gate is `sudo bin/session-04-check.sh --host … --project-a <project.yaml> --project-b <project.yaml> --capabilities … --external-probe <target>`. | D45 settled the gate shape in Session 2 and Session 3 kept it: `--mode offline\|host[\|external]`, `--project-a-outputs` / `--project-b-outputs` naming **deployed documents** rather than manifests, `--sentinel-file`, `-k` (which writes no evidence), verify-only. There is no `--capabilities` and no `--external-probe`. | **`bin/session-03-check.sh`'s shape, plus an external mode.** Session 3 dropped external mode because nothing new was visible from outside; Session 4 publishes host ports, so the allocated pooled and direct ports are new surface that only an off-host scan can prove closed. `--project-b-outputs` stays required, as in Session 3. | The gate takes deployed documents because a manifest describes what was asked for and a deployed document describes what happened. Restoring external mode is a reversal of D45's reasoning, not of its rule: the rule was "no mode that measures nothing", and this one now measures something. | no |
| **D83** | Loopback publication is simply configured. | **`SEC-NET-002` says "Only the edge publishes a host port"**, and three currently-passing P0 tests enforce it: `test_no_project_service_publishes_a_host_port` scans the model source for any `ports:` key, `test_only_the_edge_publishes_container_ports` scans running containers on the host, and `SEC-NET-001` says of the direct endpoint that "nothing listens on it". Session 4 makes all three false as written. | **An ADR versions the requirement statements to distinguish a *public* publication from a loopback one**, and the three tests are rewritten to assert the stronger property they were reaching for: no service publishes a port **without an explicit loopback `host_ip`**, and only the edge publishes a port reachable from a non-loopback address. The DOCKER-USER policy is untouched: loopback traffic does not traverse `FORWARD`, so `test_policy_permits_exactly_eighty_and_four_four_three` still holds and still means what it says. | This is the largest contract change in the session and it cannot be avoided — a pooled transport a developer can reach is the whole point of Session 4. The replacement assertions must be **stricter** than the ones removed, which is ADR 0017's standing rule for the same situation, and the live test must read the published `host_ip` rather than merely counting publications. | **yes** |
| **D84** | Outputs schema version 4 introduces `transports` and `access_profiles`, replacing the endpoint pair. | `$defs.endpoint` **already accommodates this**: `status` has `available` in its enum and the conditional only forces nulls when `unavailable`, so flipping `database.pooled` and `database.direct` to `available` with a real host, port, url and `password_secret_ref` needs no change to that definition at all. What it cannot express is **three access profiles over two transports** — one endpoint object carries one URL and one secret reference, and `runtime_direct` and `migration_direct` share a transport while differing in role and credential. | **Keep `pooled` and `direct` as the transports and add `database.access_profiles`.** Schema version goes to 4 on both branches, with a `v3 → v4` function in `output_migrations.py` and a committed `tests/fixtures/outputs-v3.json` — the full price D40 set for a schema bump. `available_from_session` stays 4 and is now satisfied rather than pending. | Session 2 wrote `endpoint` with `available` in the enum and a conditional that constrains only the unavailable case, for exactly this session. That is the design paying off, and it is worth not throwing away in favour of a parallel structure that means the same thing. | **yes** |
| **D85** | Pin PgBouncer **1.25.2 or newer**; it is "the minimum accepted Session 4 security baseline because it contains the May 2026 security fixes". | **`versions.in.yaml` has pinned `docker.io/edoburu/pgbouncer:v1.24.1-p1` since Session 1**, resolved to a digest for `linux/amd64` in the generated `versions.env`. D37 settled that Session 3 adds nothing to the lock inventory and uses what is already pinned; the same applies here. And ADR 0019 is the standing lesson that **a floor is written from observation, never from documentation** — a floor read from a vendor page once guaranteed a Traefik key that exists in no released version. | **Measure `v1.24.1-p1` first**: its `pgbouncer --version`, whether prepared-statement tracking in transaction mode behaves as the client tests need, and whether the image contains a `psql` the readiness check can use. Bump the candidate in `versions.in.yaml` and re-lock **only if a measurement requires it**, and record the resulting version as `PGBOUNCER_MINIMUM_VERSION` from what was observed. | The runbook's version claim is a documentation claim about a security advisory, and this repository has a specific rule about those. If the advisory is real the bump is right — but it gets made because someone read the changelog and then measured the replacement, not because a plan asserted a number. | no |
| **D86** | The Prisma fixture targets **Prisma ORM 7**: `prisma.config.ts`, `DIRECT_URL` as the CLI datasource, `@prisma/adapter-pg` at runtime, and no `directUrl` datasource field. | `versions.in.yaml` locks **`PRISMA_VERSION: "6.19.1"`**. In 6.x the `directUrl` datasource field exists and is the documented mechanism, `prisma.config.ts` is not the configuration model, and the driver-adapter construction differs. The runbook's own §4.10 says a fixture may not straddle two incompatible configuration models. | **Target the locked major, or bump it deliberately with the same measurement discipline as D85.** Whichever is chosen, the fixture is version-specific and the acceptance report names the exact configuration model tested. | A fixture written for a major the repository does not pin proves compatibility with software nobody runs. This is the same defect as a floor read from documentation, wearing a different hat. | no |
| **D87** | `bin/connect.sh` uses exit codes 200–207 so child exit codes are not reinterpreted. | D42 froze a **single-value exit-code convention** — `0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11` — asserted across every command by `tests/contract/test_cli_contract.py`. Session 3 added exactly one code, `11`, and only because no existing code meant "the data is not yours". | **Session 4 maps onto the existing convention**: `2` invalid input, `3` missing prerequisite, `4` missing runtime state, `5` contract or version failure, `6` a check failed, `8` secret failure, `9` the service could not be reached. `exec` passes the child's status through unchanged and reports its own failures **before** the child starts. A new code is added only if a genuinely new meaning appears, and then exactly one. | Ranges would replace a convention every script and its tests already share, and the collision the runbook is defending against is handled by the ordering rule instead: nothing the helper does after `exec` can produce a helper exit code. | no |
| **D88** | Create `bin/connect.sh`. | **It exists**, returns `10`, and sits in `tests/contract/test_cli_contract.py::FUTURE_STUBS` beside `bin/restore-test.sh`. Its `--help` already describes three modes and says "Session 4 activates real endpoint metadata". | **`bin/connect.sh` is promoted, not created** — the ADR 0017 lifecycle, applied for the third time after `bootstrap-providers.sh` in Session 2 and `migrate.sh` in Session 3. It leaves `FUTURE_STUBS` in the commit that implements it, gains real command-contract tests, and `test_the_remaining_stubs_are_the_ones_later_sessions_own` is updated in the same commit to `{"bin/restore-test.sh"}`. | ADR 0017 exists so that emptying `FUTURE_STUBS` is never a way to make `test_future_stub_exits_ten` pass. The replacement assertions must be stricter than the one removed. | no |
| **D89** | A repository delta introducing `compose/`, `config/`, `examples/clients/`, `systemd/*.sudoers`, and per-session Compose files. | There is one **root `compose.yaml`** with profiles (`contract`, `session2`, `session3`, `migration`, `isolation-test`, `session2-verify`), interpolated from `compose.env` through `bin/compose.sh --env-file`; the host adds root-owned `runtime-compose.override.yaml` (ADR 0020) and `secrets-compose.override.yaml` (ADR 0033). Built images live under `services/` (`services/edge-probe/`). There is no `compose/` or `config/` directory. | **New services join the root model under a new `session4` profile** (D43's decision, unchanged). `bin/project-runtime.sh::session_profiles` becomes cumulative through 4. **Decided in Run 1: client fixtures live under `services/clients/<name>/`.** There is no `examples/` directory, every build context in `compose.yaml` is under `services/`, and `services/secret-check/` is already a *test* fixture image rather than a product service — so the precedent for "a built image that exists to prove something" is established and points one way. Each fixture joins `REQUIRED_PATHS` as `services/edge-probe/` and `services/secret-check/` already do. The PgBouncer INI is a rendered artifact, not a committed config file. | One model with profiles is what `compose.sh`'s scope gating and forbidden-subcommand list are built around (ADRs 0013, 0021, 0022). A second Compose file would need its own copy of all of it. | no |
| **D90** | §9.4 specifies HBA ordering: regenerate `pg_hba.conf`, allowlist login roles, end with rejects, parse-check and reload. | **The repository renders no `pg_hba.conf` and never has.** The cluster runs the image's default, which D74 measured as `local all all trust`, `host all all 127.0.0.1/32 trust`, `host all all all scram-sha-256`. There is no HBA plane to edit. | **Measure before deciding.** A published loopback port arrives at the container through Docker NAT, so the connection's source address is the bridge gateway, not `127.0.0.1` — which means it should match the `scram-sha-256` line and not the trust line. **That must be measured, not reasoned about**, before any port is published. If it holds, Session 4 may ship without an HBA plane and say so; if it does not, Session 4 introduces one, and that is a rendered file, a mount, a reload path and its own tests. | This is the single most dangerous assumption in the session. If loopback publication lands on the trust line, publishing a port hands unauthenticated superuser access to every process on the host — and every credential test would still pass, because they all authenticate correctly. It is D74 again with the stakes raised. | no |
| **D91** | Evidence is a bespoke `session-04-evidence.schema.json` with a hand-shaped document. | ADR 0025 replaced suite-name evidence keys with **claims** resolved from the acceptance registry and JUnit results; ADR 0039 made a claim's session derived from its requirements and made claims cumulative. `bin/write-session-evidence.py` is session-agnostic. D49's rule: a session adds claims, not a format. | **Session 4 adds claims to `evidence_claims.CLAIMS`** — candidates are `pooled_transport`, `direct_transport`, `client_compatibility` and `connection_tooling` — each naming the registry requirements that prove it. Counts come from catalogs and JUnit, never hand-entered. | A claim's verdict is already computed from exactly the node IDs the registry lists, a proof missing from the artifact is `not_run` rather than `passed`, and a skip is not a pass. A bespoke schema would have to re-derive all of it, and would be the second definition of "proved". | no |
| **D92** | New requirement IDs `DBX-POOL-001/002/003`, `DBX-DIRECT-001`, `DBX-DX-001/002/003`, `DBX-NODE-001`, `DBX-PY-001`, `SEC-DBX-001…004`, `ISO-DBX-001`. | **Five Session 4 requirements already exist** in `tests/acceptance-registry.yaml`, each with a `future` placeholder carrying an exact node ID in `tests/integration/test_future_database_clients.py`: `DBX-001` (Prisma migrate on the direct endpoint), `DBX-002` (Prisma Client through the pooler), `DBX-003` (`psql` on both endpoints), `DBX-004` (Node and Python through the pooler, **P1**), `DBX-005` (direct PostgreSQL not publicly reachable). And **`ISO` is not a registered prefix** — `ID_PATTERN` admits `DEP CFG DBX SEC API AGT STO REC OPS DX` only, so `ISO-DBX-001` fails `test_ids_use_a_registered_prefix` offline. | **Activate the five that exist; add new IDs only for claims none of them covers.** Two-project pooled isolation becomes `DEP-ISO-004`. Pool behaviour, connection tooling and app-runtime least privilege get IDs under `DBX-`, `DX-` and `SEC-` respectively. Final list in §2. | Activating a requirement means removing its `future` marker and implementing the body — the placeholder already fails when executed, which is what makes it activatable. `test_future_marker_policy.py` enforces registry↔marker agreement in both directions, so an invented duplicate ID fails offline, and an unregistered prefix fails offline too. | no |
| **D93** | A port-allocation registry keyed by `project_instance_id`, protected by a host lock. | The design is right and the key already exists: `app_private.project_identity.instance_uuid`, generated once on the first bootstrap of an empty volume and **recovered** on every bootstrap since, is the project's immutable identity and is already the thing `postgres-bootstrap.py` refuses a foreign volume over (ADR 0030, exit 11). The runbook proposes a fresh UUID for the same job. | **The allocation key is the instance UUID the volume already carries.** The registry lives at `/etc/agentic-postgres/database-port-allocations.json`, following `edge-state.json`, validated against a committed schema, written atomically, and held under a host lock from reservation through publication and verification. | A second immutable project identity would be a second answer to "which project is this", and the first one is already bound to the data. Reusing it also means a restored volume brings its port allocation's identity with it. | no |
| **D94** | §7.3 computes a PostgreSQL connection budget. | Correct and necessary, and **incomplete**: D52 established a *memory* budget in the manifest schema, computed over **unreclaimable** memory, with rendering failing when the sum across a host's projects exceeds a declared guardrail. PgBouncer is a new per-project process on a 3814 MiB host with **no swap** already running two clusters. | **Both budgets.** The connection budget is queried from the running server — `max_connections`, `superuser_reserved_connections` — never assumed from documentation, and deployment fails rather than overcommitting. PgBouncer's footprint joins the memory guardrail, measured under the saturation test rather than estimated. | With zero swap the OOM killer is the only backstop and it does not choose politely — it can take Traefik, which drops every project's ingress at once. A pooler that makes the cluster cheaper in connections and more expensive in resident memory has to be accounted in the currency that is actually scarce. | no |
| **D95** | `deploy.sh --render-runtime-only`, a privileged render submode. | `deploy.sh --render-only` exists, needs no host and no root, and **keeping it working is a standing non-negotiable**. A second render mode is not forbidden, but D46 settled that the deploy's ordering stays operator-visible and that a step belongs inside the deploy when it "cannot fail on its own". | **Adopt it, with the boundary D46 sets.** A privileged runtime render that reserves a port allocation and publishes a validated override without touching containers can fail on its own and be re-run on its own, so it earns its place. It must not materialize secrets, rotate a password, mark an allocation `active`, or publish `ready`. `--render-only` is untouched and stays the only render a checkout can perform. | The value is real: port allocation and loopback publication are the two things most likely to go wrong, and both are cheaper to get wrong before any container moves. | no |
| **D96** | An installed root-owned broker at `/usr/local/libexec/agentic-postgres/database-access`, exposed through a narrow `sudo -n` rule. | **ADR 0037 constrains that directory**: an installed launcher may resolve a release and nothing else, because one copy serves projects deployed through releases it has never seen. A broker that validates policy, reads state and returns secrets is exactly the kind of release-owned logic that ADR forbids there — and the reason it forbids it is that a Session 2 launcher ran `--session 2` against a Session 3 project for three runs. | **The broker follows the trampoline split.** `libexec/agentic-postgres-database-access` resolves the project's recorded release and `exec`s `<release>/libexec/database-access`, which holds every policy decision. The deploy installs the trampoline with the others; the structural test that a launcher holds no answer a release owns covers it automatically. | The alternative is a second privileged host-global program that ages independently of the releases it serves, which is the defect ADR 0037 was written for, reintroduced in the one place that hands out credentials. | no |
| **D97** | `bin/pool.sh` and `bin/database-ports.sh` are new commands with their own conventions. | Every command in `bin/` is subject to `test_cli_contract.py`: it must exist, be `100755` **in the git index**, carry the shell preamble, expose `--help` exiting 0, reject unknown options, obey the exit-code convention, work from any directory, print no environment, and document no secret argument. New commands join `SHELL_COMMANDS`. | **Adopt the commands, subject to the inventory.** Adding them to `SHELL_COMMANDS` is what subjects them to those checks; it is an inventory addition rather than a weakening. | Writing through the `\\wsl$` share strips the executable bit, and the index mode is what the contract checks — a stripped bit is a test failure rather than a silent break. This has cost time in every session so far. | no |
| **D98** | *(Run 1, from this plan's own D85)* Record the measured pooler version as a `PGBOUNCER_MINIMUM_VERSION` feature floor. | The floor mechanism derives the resolved version from the image **tag** and compares with `as_version`, which strips non-digits per component: `v1.24.1-p1` becomes `(1, 24, 11)`, and a downgrade to `1.24.0-p1` becomes `(1, 24, 1)` — which is not less than a floor of `1.24.1`. The comparator cannot express the precision the measurement has. | **No floor. The exact version is asserted in `tests/contract/test_image_contracts.py`** by running `pgbouncer --version` against the locked digest, alongside the two behavioural measurements that are the actual reason the version was kept. | This plan's §5 says that module is "the only place the values themselves are written down… so that there is one authority and it is executable". A floor here would be a second, weaker authority for the same fact — the shape ADR 0035 named "a check that could not fail". | no |
| **D118** | *(§7)* The claim `direct_transport` names `DBX-001`, `DBX-003`, `DBX-005` and `SEC-DBX-001`. | **`claim_mode` refuses it, and correctly.** The first two are proved on the host by running Prisma Migrate and `psql`; the last two are proved from off-host by *failing* to reach the same endpoint. ADR 0025's rule is that each claim is measured in exactly one environment, so neither half of the evidence could report a verdict on it — and a merged verdict computed from half the proofs would say `passed`. The plan's §7 was the first claim table written against three modes since Session 2, and this was invisible until it was imported. | **The claim splits where the measurement is** (ADR 0045). `direct_transport` is `DBX-001, DBX-003` on the host; **`transport_boundary`** is `DBX-005, SEC-DBX-001` from outside. `transport_boundary` is the external claim `public_boundary` could not be — its proofs scan IPv4 only, so unlike `SEC-NET-001`'s it can pass from a network with no IPv6 transit, and the external mode carries a claim for the first time. | A claim is not free to be shaped by the sentence it states; it is shaped by where its proofs can run. Splitting is what the rule is *for* — this is the first session with two environments in which it would have bitten, which is evidence that it works rather than that it is in the way. | **yes** |
| **D119** | *(§7)* `database_isolation` **gains** `DEP-ISO-004`. | **Doing that would take the claim away from Session 3's evidence.** `claim_session` is the maximum of a claim's requirements' sessions (ADR 0039), so gaining a Session 4 requirement moves the whole claim to Session 4, and `claims_through_session(3)` stops returning it. The Session 3 gate would quietly stop recording a claim it has recorded since Session 3 shipped, and the jq expression `docs/session-03-operator-guide.md` documents — `.tests.database_isolation=="passed"` — would fail against freshly written Session 3 evidence with the product's behaviour unchanged. | **`DEP-ISO-004` gets its own claim, `transport_isolation`, at Session 4.** `database_isolation` stays exactly as it is. Both are proved on the host and both appear in Session 4's evidence, so nothing is lost in the present; what is kept is Session 3's ability to produce the document it produced. | Cumulative was meant to mean that a later session keeps proving an earlier one's guarantees, not that a later requirement withdraws one from an earlier session's evidence. ADR 0045 records the general rule this leaves: **extending a claim is a decision about which sessions' evidence records it**, right when the guarantee genuinely grew and wrong when a new requirement merely neighbours an old one. | **yes** |
| **D120** | *(§5 Run 10)* "The restart matrix extends `DEP-BOOT-001`, which Run 8 of Session 3 added." | **`DEP-BOOT-001` is a Session 3 requirement, and `boot_convergence` is a Session 3 claim.** Adding tests that need a pooler to it would make a Session 3 claim depend on a Session 4 deployment: on a host deployed only through Session 3 those proofs fail or skip, `boot_convergence` comes out `failed`, and the Session 3 gate — which is still runnable and still expected to pass — breaks for a reason that has nothing to do with Session 3. | **The matrix extends `DBX-PORT-001`**, whose description has said "stable across redeploy, restart and reboot" since Run 1 and which had two tests measuring one moment. Four new node IDs: pooler restart, cluster restart, unit restart, reboot. Each asserts three things — the allocation is unchanged, both transports accept the runtime credential again, and no public listener appeared. | The row's real content is that "stable across restart and reboot" was in a P0 description for nine runs with nothing proving it. That is a placeholder written in prose rather than in a marker, and it is the kind this repository's `future` machinery does not catch. | no |
| **D121** | *(§5 Run 10)* "and a reboot… One controlled credential rotation… ending with the old credential proved to fail." | **Neither can be performed by the suite.** A test that rebooted the host would kill the process that has to report the result, and a rotation needs a new value at the provider, which nothing in this repository writes — `InfisicalClient` reads. Both are operator steps. The plan also names ten new requirement IDs, and the rotation is not one of them. | **Both are proofs admitted by a declaration, and each is written to refuse a false one.** `--after-reboot` admits a test asserting that the data predates the boot **and** every process reading it postdates the boot — a cluster that reinitialised into a fresh volume passes the second, a host that never rebooted passes the first. `--rotated-from-file` admits **`SEC-DBX-004`**, an eleventh requirement ID, which asserts the supplied value is not the active one before asserting that it opens neither transport. Neither belongs to a claim. | A claim is a standing guarantee; these are events. A claim over a rotation would report a verdict on something that did not happen in that run, and — worse — the pre-rotation file keeps failing forever, so after the first window the proof would be permanently, trivially green. That is this project's signature defect with a six-month fuse, and the fix is to keep it out of the release gate rather than to make it convenient. | no |
| **D122** | *(nothing in the runbook)* | **`docs/decisions/README.md` said `Proposed` for ADRs 0040, 0041 and 0042** — decisions that had been built, deployed and measured across nine runs — and 0041 said so in its own header. `test_every_adr_is_indexed` checks that a row exists; nothing checked what the row said. | **The index is corrected, and a contract test compares the two.** Statuses are matched on the first word, so `accepted; the publication clause superseded by 0044` in the file and `Accepted, superseded in part` in the row agree without either being a transcription of the other. | The ADR index is the document the project contract points a reader at. A stale status there is a wrong answer given confidently, and it is exactly the shape of defect this project keeps producing: a field that looked maintained because something adjacent to it was checked. | no |
| **D123** | *(ADR 0044, Run 9)* | **Three operator-facing texts still described a publication after it stopped existing.** `bin/connect.sh --help` said `--local-port` defaults to "the same number the host publishes on"; `bin/database-ports.sh`'s header said the ports are what the transports "are published on" and its `verify` help said it connects to "both published endpoints"; and the docstring of `test_the_published_ports_are_the_ones_the_registry_allocated` still carried the **withdrawn** first version of D114 — that `ss` is the wrong instrument because `userland-proxy: false` means nothing listens. | **All four rewritten.** The allocation is described as the near end of a developer's tunnel; `verify` connects to container endpoints; and the test's docstring records what D114 actually settled — `HostConfig.PortBindings` is what Docker was asked for, and Docker 29 binds a published port in `dockerd` itself, where `ss` sees it perfectly well. | An ADR changes what is true; it does not change the sentences already written about it. The docstring is the worse of the two, because it taught the retracted explanation to the next reader inside a test whose subject is measuring rather than assuming. | no |
| **D124** | *(§6.3, and `DBX-MIG-001` / `SEC-OWNER-001` as Session 3 wrote them)* Every service identity is a NOLOGIN stub **until its owning session activates it deliberately**. | **The test asserted the first half of that sentence and never encoded the clause.** `test_only_the_migration_user_may_log_in` read `observed in ("", migration_user)`. Run 5 activated `app_runtime` with a credential — the entire point of the session, decided by ADR 0041 and implemented by `20260808120006_app_runtime_least_privilege` — and from that moment the assertion was false about a correct deployment. **It did not go red for five runs, because nothing ran it**: Runs 5–9 measured the host with targeted invocations against `tests/deployment/`, and this module is `live_host` under `tests/security/`. Run 10's first full `--mode host` gate collected it and it failed immediately. | **The login set is derived from the deployed document** (ADR 0046): `{migration_user} ∪ {role of every access profile that is available}`, compared for **equality**. Renamed to `test_only_the_activated_roles_may_log_in`, which is what it was always about. Stricter in three ways: the old `""` branch accepted a cluster where the migration user could not log in at all; a role gaining LOGIN without a published profile now fails; a profile published without a working role now fails. | The test is the smaller half. **A P0 module went unexecuted across five runs while its requirements were reported as covered**, because the acceptance matrix lists node IDs rather than results and no evidence document was written between Run 4 and Run 10. A matrix entry says a proof exists; only evidence says it ran. The standing correction is procedural: **a run that activates a role runs the whole host suite, not the part it was working on.** | **yes** |
| **D125** | *(`SEC-NET-001`, as Session 2 wrote it)* The deployed document reports `status: unavailable` and `url: null` for both database endpoints. | **Session 4 publishes both**, as the near end of a developer's tunnel (ADR 0044), so `test_the_deployed_document_still_reports_no_direct_endpoint` and `test_the_pooled_endpoint_is_equally_absent` were false about a correct deployment from Run 4 onward. **They had not run since Session 2.** Session 3 dropped the external mode on D45's reasoning — a mode that measures nothing would still write evidence saying it had — and the consequence nobody drew is that the four proofs the mode owns stopped executing. D124 had just produced the same defect on the host; this is the second instance in one run. | **One parametrized test asserting the property the absence stood for** (ADR 0047): `unavailable` still means no URL and no host, and `available` must carry a **loopback** address in the `host` field *and* in the URL, with no credential in it and a port matching the endpoint's. It holds against a Session 2, 3 or 4 deployment without being told which. | The absence was never the guarantee — it was a proxy that was equivalent only while the feature did not exist. ADR 0047 generalises it and adds the rule this run paid for twice: **a session that supplies a thing an earlier session proved absent runs that earlier session's whole suite, in every environment it has.** And restoring a gate mode is also a review of every proof that mode owns. | **yes** |
| **D126** | *(nothing in the runbook; `DX-DB-001` as Run 6 built it)* `bin/connect.sh tunnel` opens a forward, records it, prints where it is bound, and returns. | **It returns, and its caller does not.** The backgrounded `ssh` inherited the command's stdout and stderr and held them open for the life of the tunnel, so any caller that *captures* the output blocks until the tunnel is closed. `output=$(bin/connect.sh tunnel …)` hangs; so does every wrapper, CI step and test that does the same. Found by `DX-DB-001` timing out after 120 seconds **having already printed its success line** — the tunnel was correct and the command was not. | **The child gets `</dev/null` and its own log**, `tunnels/<project>__<profile>.log` at 0600 beside the state record. A file rather than `/dev/null`, because ssh's stderr is where `bind: Address already in use` and a refused host key appear; the failure path now prints that log and names it. | A defect no test could have found by reading, and none of the six command-contract tests could have found by running: they all invoke the *other* five subcommands, which do not background anything. It took a caller that both captured output and had a deadline. The general form is worth keeping: **a command that leaves a process running has not finished until its file descriptors are somebody else's.** | no |
| **D117** | *(D116's fix, one hour old)* `server_reset_query_always = 1` with the default `DISCARD ALL` clears the session state SEC-DBX-003 requires. | **`DISCARD ALL` includes `DEALLOCATE ALL`.** Every prepared statement on the connection went with the session state, and `DBX-POOL-003` — a named statement surviving a backend change — cannot hold against a pooler that deallocates after every transaction. Two P0 requirements in direct conflict, one of them created by the other's fix. | **The reset query is `DISCARD PLANS; DISCARD SEQUENCES; DISCARD TEMP; RESET ALL`** — `DISCARD ALL` minus the one statement that broke it. `RESET ALL` is what actually clears a custom GUC set through `set_config`. Both requirements are proved against this one configuration and **neither was weakened to satisfy the other**. | The tempting resolutions were both weakenings: drop `server_reset_query_always` and lose SEC-DBX-003, or accept that prepared statements do not survive and rewrite DBX-POOL-003 into a test of the fallback. The plan forbids the second in so many words, and the first would have restored a leak that had just been measured. | no |
| **D116** | *(§5 Run 9, and `SEC-DBX-003` as the plan states it)* Transaction pooling means session state does not survive a client. | **It survives.** PgBouncer runs `server_reset_query` only in SESSION pooling unless `server_reset_query_always` is set; in transaction mode it assumes an application leaves no session state behind. A client that ran `set_config('apg.leak_probe', ..., false)` and disconnected left the GUC on the server connection and the **next client read it back**. Measured on the host, by the test written to catch it. | **`server_reset_query_always = 1`.** The transaction-local claim vanishes at commit on its own, so the half that was already safe was the half nothing was cleaning up — and `SET ROLE`, `search_path` and a session GUC all travel the same path. | One request's asserted identity becoming the next one's is the most dangerous single failure available in this design, and nothing about a healthy pooler distinguishes it. SEC-DBX-003 was written as a *product contract* rather than a bug hunt, and it went red before it went green, which is the only evidence that it was ever measuring anything. | no |
| **D115** | *(ADR 0040, ADR 0042)* Each project publishes its two transports on a host-loopback port, allocated from a host range. | **Docker does not publish ports for a container attached only to an `internal: true` network.** It accepts the request, records `HostConfig.PortBindings`, and installs no DNAT rule and no listener. Measured against the control in the same output: Traefik is on non-internal networks and shows `0.0.0.0:443->8443/tcp` with a matching `-A DOCKER ... -j DNAT` rule; `pgbouncer` on `apg-alpha-dev-internal` shows a bare `6432/tcp` and no rule anywhere. | **UNRESOLVED — this is an ADR, not an inline fix.** ADR 0040's publication and the `internal: true` network are incompatible as currently modelled, and `internal: true` is what `DBX-PG-002` and `SEC-NET-001` rest on: the network with no route off the host. Three candidate resolutions, each with a real cost, are in the Run 9 note below. Nothing is reachable meanwhile, the allocation is `reserved`, and no document reports ready — which is the state §4.1 wants when something is uncertain. | The conflict is between two things this session already decided, so resolving it inline would be exactly the silent reconciliation the non-negotiables forbid. It is also not obvious: the cheapest fix — attaching the pooler to a non-internal network — trades a Session 2 isolation property for a Session 4 convenience, and the option that costs nothing in isolation terms removes the host publication altogether and takes ADR 0042's allocated ports with it. | **yes** |
| **D114** | *(§4.1, and `DBX-PORT-001` as written in Run 8)* A publication is verified from the host by reading what is listening. | **Withdrawn as first written, and the first version of this row was wrong in both directions.** It claimed `ss` was the wrong instrument because `userland-proxy: false` means nothing listens, and it claimed the publication was correct and in force. Measured: Docker 29 binds a published port **in `dockerd` itself** — `ss` reports `0.0.0.0:443 users:(("dockerd"))` — so `ss` sees a real publication perfectly well. And there was no publication to see (D115). | **`docker inspect`'s `HostConfig.PortBindings` is not evidence of a publication.** It records what Docker was *asked* for; it showed `6432/tcp -> 127.0.0.1:15432` for a port with no DNAT rule and nothing answering. What a publication actually is: a DNAT rule, a `dockerd` listener on the published address, and a connect that completes. `docker ps` distinguishes it in one column — `5432/tcp` is exposed, `0.0.0.0:443->8443/tcp` is published. | Recorded rather than quietly rewritten because the mistake is the project's own pattern committed by its author: **a request read as a measurement.** `PortBindings` is a field in the container's *configuration*, and configuration is what this repository says over and over cannot stand in for a fact about the running system. It cost a stage of Run 9 and one wrong ADR-shaped claim in this table. | no |
| **D113** | *(ADR 0042)* The allocation key is `app_private.project_identity.instance_uuid`, read from the cluster that carries it. | It was read with `psql -U postgres -d postgres`. **`-d postgres` is the maintenance database**; `app_private.project_identity` is created by migration 0002 inside the *project's* database. The query returned `relation "app_private.project_identity" does not exist` on a cluster where the row had existed since Session 3 — the same run's bootstrap had just printed the UUID. | **The database is a parameter**, passed from `document["database"]["name"]`. A structural test asserts the parameter exists, that it is what reaches `-d`, and that no literal `postgres` is passed as `-d`. | The exact defect this project keeps producing, and the fifth entry in the pattern: **a value that looked measured and was not.** `-U postgres -d postgres` reads perfectly naturally — the superuser is called postgres and so is the maintenance database — and the two `postgres`es mean different things. There is no offline path through `cluster_instance_uuid`: it runs `docker exec`, so it failed on the first host that ran it and could fail nowhere else. The replacement test is structural because that is the only kind there can be. | no |
| **D112** | *(implied everywhere)* The deployed document reports each transport's status and each profile's `password_secret_ref`, and the access broker refuses a profile that is not `available`. | **Nothing wrote those fields.** The render hard-codes all three blocks `unavailable` with null references — correctly, a render knows no port — and `build_deployed_document` carried the rendered `database` block through verbatim. Run 9 deployed Project A through session 4 on a host with a healthy pooler and materialized secrets, and the published document still said every transport was unavailable. Three readers, no writer: the broker refuses every profile, the external suite reads the ports out of it, and §4.1's "deployed output may not report `ready` before the negative checks pass" presumes it eventually reports something else. | **`deployed_output.observe_transports` is the writer**, and availability is gated on the allocation being **`active`**, not on it existing. So the sequence is: deploy (publishes `unavailable`), `--render-runtime-only` (reserve + publish the override), restart, **off-host scan**, `database-ports.sh verify` (promotes to `active`), deploy again (records that the endpoints answer). Two deploys, which is what §4.1 was already describing. | Found by deploying, not by reading — the same way D68 was found, and the same shape: a field with readers and no writer, like the `edge-state.json` this repository's own comments cite. Gating on `active` rather than on existence is what keeps the document from claiming an endpoint answers because something once intended it to, and keeps the claim behind the scan that guards it. | no |
| **D111** | *(§5 Run 8, as written)* SEC-DBX-001..003 replace the placeholders in `tests/security/test_future_security_boundaries.py`, which sits under `tests/security/`. | SEC-DBX-002 and SEC-DBX-003 need a materialized per-consumer secret, a built client fixture image and the resolved Compose model. All three are fixtures in **`tests/deployment/conftest.py`**, and `tests/` is not a package, so a module under `tests/security/` cannot reach them without a second conftest defining them again. | **They live under `tests/deployment/` and carry the `security` marker.** The marker decides what runs and what `evidence_claims` records; the directory decides which conftest is in scope. SEC-DBX-001 stays in `tests/external/`, where it belongs on its own merits — a scan run on the host traverses loopback and answers a different question. | A second definition of "how a materialized credential is read" is the duplication that produced D72 and D73. `test_future_deployment.py` already says in its own docstring that the marker, not the directory, decides what runs; this is the first time that mattered. | no |
| **D110** | *(implied by §5 Run 9)* The Prisma fixture's migration mode is run against the disposable schema. | One image, two modes: `client` is `command: [client]` in the model, and `migrate` needs a different command with the same environment. **`bin/compose.sh` forbids `run`** (and `up`, `exec`, `start`, `create` outside the narrow `--runtime` allowance), so there is no sanctioned way to invoke a Compose service with an overridden command. | **Named here rather than resolved inline.** Run 9 picks one of two: a second service `client-prisma-migrate` on the same build context with `command: [migrate]` — which costs two more declared secret consumers — or a deliberate, tested allowance in `compose.sh` for a fixed command on a `session4-verify` service. The fixture is already written so that either works: the mode is an argument, and every variable both modes need is in the service's environment. | Inventing a route through the one script whose whole job is to bound what Compose may be asked to do is the change that should be made deliberately, in the run that needs it, with its own test — not as a side effect of writing a fixture. Both options have a real cost and the cheaper one is not obvious. | no |
| **D109** | *(§4.4 of this plan)* The disposable schema's "exact identity is recorded in root-owned state **before the unprivileged test sees it**". | Every interpolation in `compose.yaml` must be `${VAR:?required}` (`test_every_interpolation_is_required`), and every value in `compose.env` must be project-derived or the rendered output stops being byte-identical across renders. **A name chosen per run can reach neither.** | **The disposable schema is a derived constant**, `apg_client_fixture`, rendered into `compose.env` as `APG_DISPOSABLE_SCHEMA`. What §4.4 was actually buying is kept: the privileged half creates it and records it in root-owned state, the drop targets only the recorded name, and the unprivileged fixture refuses all seven protected schemas by name. What is lost is that the name is predictable — which matters only against an attacker who could already name any schema they liked. | A random name would have to arrive through the runtime override, which is host state, and the whole point of §4.4's ordering is that the *drop* reads a record rather than a guess. That property does not depend on the name being unpredictable. Recorded rather than quietly satisfied, because the plan says "before the unprivileged test sees it" and this does not do that. | no |
| **D108** | *(§16 and `secrets.required.yaml`, as written)* "Declaring a second consumer would materialize a second copy of one credential, and two copies is two things a rotation has to reach." | The four client fixtures each need the application credential, and the Prisma fixture needs the migration credential as well to prove DBX-001 in the configuration an application actually ships. That is **five new materialized copies**. | **Declared, not shared.** Each fixture is a consumer in its own right, at its own uid, with its own file. The sentence above stands for the case it was written about — the bootstrap plane, which is root on the host and reads the pooler's file directly — and does not extend to containers: one container cannot read another's mount, and that separation is the property the per-consumer layout exists for and that `DEP-ISO-004` proves between projects. | The alternative is mounting one service's copy into five, which dissolves the isolation this file's structure promises in order to reduce a rotation's file count. A fixture is also the *model* of a real application service, which would be declared exactly this way — so the cost is the product's, not the test's, and hiding it in the fixture would understate it. **Rotation now reaches five files for `app_runtime_password` — the pooler's and the four fixtures' — and two for `migration_user_password`**; Session 5's rotation path has to be written against those numbers. Counted off Run 9's materialization plan on the host, not off this table: the first version of this row said six, which is what happens when a consumer count is added up in prose instead of read from the thing that writes the files. | no |
| **D107** | *(§7.4 of the source specification)* `bin/connect.sh` supports `tunnel`, `psql`, `prisma-studio` and `print-env`, and "establishes and cleans up the restricted tunnel". | Written in Run 6 as `tunnel`, `status`, `stop`, `print-env`, `psql` and `exec`. **`psql`, `print-env` and `exec` require a tunnel that is already open; they never open one.** `prisma-studio` is not a mode: it is a client, and clients run through `exec -- npx prisma studio`. | **The split stands.** A command that silently opened and closed a forward makes "is the tunnel up" unanswerable, and the alternative failure — a command that dies leaving a forward behind — is a port on a developer's machine still reaching a production database an hour later. One command opens, one closes, and `status` says which are live. `prisma-studio` as a mode would be the first of an unbounded list of clients this helper would have to know about; `exec` is the one that works for all of them, including the four Run 7 writes. | no |
| **D106** | *(implied by ADR 0042)* The broker resolves a project's published ports from the allocation registry. | The registry is **keyed by the volume's `instance_uuid`**, and says in its own module docstring that the project key is recorded for humans and is *never* the match key — two projects can share a key across a rebuild and one project can change it. **The deployed document records no instance UUID.** So the broker has nothing but the project key to search by. | **The broker searches live allocations by project key and refuses ambiguity.** Released records are excluded; two *live* records carrying one key is exit `5`, not a first match. Recorded here rather than fixed, because the fix is a field on the deployed document and that is a schema version — the fourth this session already has. **Session 5 adds `database.observed.instance_uuid` and the broker switches to it.** | A first match here is a credential handed out for the wrong cluster, and nothing downstream would notice: the port answers, the role exists, the password authenticates. Refusing turns the missing identifier into a visible failure on the day it would matter instead of a silent one. | no |
| **D105** | *(§7.4 of the source specification)* The helper "avoids printing passwords by default". | Run 6 prints none at all, and there is no flag that loosens it. `print-env` emits `PGHOST`/`PGPORT`/`PGUSER`/`PGDATABASE` and a `DATABASE_URL` whose userinfo component cannot carry a password — the same rule `postgresUrl` states in the output schema. The credential reaches a client only through `exec`, which writes it to a `0600` file under `umask 077` with a shell builtin and names it to the child through `PGPASSFILE`. | **Stricter than the specification, deliberately.** "By default" implies a flag, and a flag that prints a credential to a terminal is a credential in a scrollback buffer, a shell history, a screen share and a support ticket. | The value never becomes an argument vector, never reaches a terminal, and is removed by an `EXIT` trap whether the child succeeded, failed or was interrupted. Run 7's fixtures read `PGPASSFILE`, or the file it names, rather than an environment variable. | no |
| **D104** | *(ADR 0043 point 5, as proposed in Run 1)* The access path makes "no distinction in exit code between 'no such project' and 'not yours'". | Writing the trampoline in Run 6 showed the claim cannot hold where it was stated. **The trampoline must read the deployed document before any policy is consulted**, because that document is what names the release the policy lives in. A project with no `outputs.json` therefore exits `4` naming the path, and a deployed one goes on to the release. No ordering fixes it: checking authorization first would put policy in the trampoline, which is what ADR 0037 forbids and the entire reason ADR 0043 exists. | **ADR 0043 is amended on acceptance rather than asserted by a test that would measure the wrong file.** Past the trampoline the property holds and is proved: the broker authorizes *before reading anything about the project*, so a caller with no grant gets exit `6` and the word `refused.` whether the project is deployed, released or has never existed. The proof is the one that can only pass if the ordering is right — authorization *succeeds* for a project that does not exist. At the trampoline, project-key existence is visible to an account already named in the `sudo -n` rule: sudo is the coarse gate, the policy is the fine one. `DX-DB-002`'s registry description is narrowed to match. | A test claiming indistinguishability at the trampoline would fail, and the obvious way to make it pass is to move policy into the trampoline — the exact defect ADR 0037 was written for, in the one program that hands out credentials. An ADR that overstates what its implementation can do is worse than one that states less. | no |
| **D103** | *(Run 5, measured)* `SEC-DBX-002`: the application runtime role "holds no base-schema addressability", which reads as a catalog assertion. | **`has_table_privilege(app_runtime, 'app.notes', 'SELECT')` is `true`, and the role still cannot read the table.** Both are correct: the api views are `SECURITY INVOKER`, so `authenticated` must hold `SELECT` on the base tables for them to work, and `app_runtime` inherits that membership — but not `USAGE` on the schema, without which the grant cannot be exercised. `SET ROLE app_runtime; SELECT * FROM app.notes` returns *permission denied for schema app*. | **`SEC-DBX-002` is proved behaviourally, by attempting the read, not by reading a catalog bit.** The schema revoke is the boundary; the table-level revokes in migration 0006 are defence in depth and are kept as such. | The obvious test fails while the property is true, and the obvious fix for that failure — revoking `SELECT` from `authenticated` — would silently break every api view. This is the project's own pattern inverted: a value that looks unmeasured and is fine, next to a repair that would have broken the thing it was tidying. | no |
| **D102** | *(§5 Run 5, as written)* The migration carries "a safe `search_path`, conservative statement and idle-transaction timeouts". | Those are `ALTER ROLE … SET`, which on *another* role needs an authority the migration plane deliberately does not hold: `migration_user` is not a superuser and holds no `ADMIN` on `app_runtime`. | **They move to the bootstrap plane**, beside the role's other attributes, and are read back from `pg_roles.rolconfig` rather than assumed. The migration keeps what it can legitimately do: the grants and revocations on schemas and tables. | A migration that needed superuser to apply would either fail on the first deploy or push the migration plane's authority up to meet it, and the second is how a migration plane stops being least-privileged. | no |
| **D101** | *(§5 Run 4, as written)* The pooler's health check proves "the admin identity, the pool mode, the prepared-statement setting **and a backend round-trip**". | The round-trip needs the application role, and the role does not exist when the check first runs. `project-runtime.sh up` runs `compose up --wait`; the deploy runs `postgres-bootstrap` *after* that returns. A health check that connected as the application would fail `--wait` on every first deploy and take the deploy down with it. | **The check authenticates to the admin console and reads the pool mode and prepared-statement setting back out of the running daemon. The round-trip moves to the client proofs**, which run after bootstrap. Measured both ways: a working pooler passes silently, and a pooler whose user list it cannot read fails **while its port is open**. | The check still catches the failure it was written for, which a port check does not: an unreadable auth file leaves the pooler listening and refusing everything. Asserting a round-trip it cannot perform would have made the whole check unreachable, and the usual fix for that is to weaken it until the deploy proceeds. | no |
| **D100** | *(§5 of this plan, as written)* Run 5 deploys Project A through session 4, while the fifteen Session 4 requirements stay `future` until Runs 7–8 and `CURRENT_SESSION` moves with them (§2.3, D54). | **Those two cannot both hold.** `bin/deploy-project.py` refuses `--through-session` above `CURRENT_SESSION`, so no session-4 deploy is possible while the constant reads `3`. And moving the constant to `4` makes exactly fifteen requirements overdue under `test_no_requirement_at_or_before_the_gate_session_remains_future` — `DBX-001..005`, `DBX-POOL-001..003`, `DBX-PORT-001`, `DEP-ISO-004`, `DX-DB-001/002`, `SEC-DBX-001..003` — verified by running the registry suite under `APG_ACCEPTANCE_SESSION=4`. This is D54 again, one session on, and this plan reproduced it while quoting it. | **Session 3's shape, decided after Run 3.** Every real test is written first, `CURRENT_SESSION` moves to 4 in one commit that deletes all fifteen placeholders (Run 8), and every host operation follows it (Runs 9–10). The build order in §5 is re-sequenced accordingly: the deploy moves from Run 5 to Run 9. The alternative — separating the acceptance session from a highest-deployable session — was rejected as a second answer to \"what session is this tree\", which is the shape ADR 0037 was written about. | Found in Run 3 rather than in the middle of Run 5's first publication, which is the whole reason the host half of a run is attempted early. Note what is *not* in conflict: `bin/bootstrap-providers.sh` already takes `--session` explicitly, so the provider half can converge at session 4 today; only the deploy has the ceiling. | no |
| **D99** | *(Run 1, discovered)* Nothing in the runbook. | `PYTHON_RUNTIME_IMAGE` selects the **rolling tag** `docker.io/library/python:3.12-slim`, and re-locking during Run 1 moved its digest — the tag was re-pushed between 2026-08-05 and 2026-08-08. `versions.env` separately asserts `PYTHON_VERSION=3.12.13`, checked against `.python-version`. So the repository's interpreter is pinned to a patch and the image every first-party service is built `FROM` is pinned only to a minor, and **nothing compared them**. | **A test measures the base image's Python against `PYTHON_VERSION`.** They agree today (3.12.13 both sides), which is the point: the check exists before they disagree, not after. Tightening the tag to `3.12.13-slim` is a candidate change and is left as an open item, not made silently in this run. | The project's signature defect, found in its own lock file: a value that looked pinned and was pinned one component short. The next 3.12.x push moves the container's interpreter with nothing to notice. | no |

---

## 2. What Session 4 adds to the acceptance registry

### 2.1 Requirements that already exist and are activated

Each has a `future` placeholder in `tests/integration/test_future_database_clients.py` today. Activation deletes the placeholder, writes real tests, and updates the registry's `test_nodeids` to name them.

| ID | Claim | Priority | Placeholder to remove |
|---|---|---|---|
| `DBX-001` | Migrations run against the direct endpoint, not the pooler | P0 | `test_prisma_migrate_uses_the_direct_url` |
| `DBX-002` | Application CRUD works through PgBouncer transaction pooling | P0 | `test_prisma_client_uses_the_pooled_url` |
| `DBX-003` | `psql` connects directly and through the pooler | P0 | `test_psql_works_on_both_endpoints` |
| `DBX-004` | Node `pg` and a Python driver both round-trip a query through the pooler | **P1** | `test_node_and_python_clients_work_through_the_pooler` |
| `DBX-005` | The direct endpoint is reachable only through the tunnel | P0 | `test_direct_postgresql_is_not_publicly_reachable` |

`DBX-004` is **P1**, not P0. Deferring it requires evidence; it does not block the release. That is worth knowing before it is treated as a blocker at 2am.

### 2.2 New requirement IDs

Added only where no placeholder covers the claim. Prefixes follow the frozen catalog in `docs/product-contract.md` §3.

| ID | Requirement | Priority |
|---|---|---|
| `DBX-POOL-001` | The pooler runs in transaction mode with explicit, bounded limits and non-zero prepared-statement tracking | P0 |
| `DBX-POOL-002` | Client concurrency is multiplexed within the configured server-connection budget, and the budget is never exceeded | P0 |
| `DBX-POOL-003` | A named prepared statement survives reassignment to a different backend | P0 |
| `DBX-PORT-001` | Host-loopback allocations are stable across redeploy, restart and reboot, and two projects never share one | P0 |
| `SEC-DBX-001` | Neither transport is reachable from a non-loopback address; only the edge publishes a public port | P0 |
| `SEC-DBX-002` | The application runtime role holds no ownership, no base-schema addressability, no DDL, and cannot become any other role | P0 |
| `SEC-DBX-003` | Transaction-local claim state, and deliberately set session-level state, do not survive a pooled connection's release | P0 |
| `DX-DB-001` | The connection helper opens and cleans a verified tunnel for each transport without printing a credential | P0 |
| `DX-DB-002` | The installed access broker enforces project and profile authorization and returns nothing to an unauthorized caller | P0 |
| `DEP-ISO-004` | Two projects have distinct pooled and direct ports, credentials, pooler configuration and user lists, and neither's credential opens the other | P0 |

`DEP-ISO-004` rather than `ISO-DBX-001`: `ISO` is not a registered prefix and fails `test_ids_use_a_registered_prefix` offline (D92).

**`DEP-ISO-004`'s credential clause must have a node ID of its own.** D70 is the standing lesson: `DEP-ISO-003` claimed "neither project's credential authenticates against the other" for two runs with six node IDs behind it and not one of them presented a credential to anything. The construction that works is the foreign password against **the target's own role**, from a container on the target's internal network — because the image trusts loopback (D74) and a login attempted inside the cluster's own container proves nothing.

### 2.3 Registry mechanics

`docs/acceptance-matrix.md` and the `product-contract.md` marker block are **generated** from the registry by `bin/render-acceptance-matrix.py`; the gate runs `--check` and fails on drift. Never hand-edit either.

`CURRENT_SESSION` moves from `3` to `4` in `src/agentic_postgres/__init__.py`, and — per **D54** — it moves in the run that deletes the placeholders and replaces them with real tests, not in Run 1. That single constant drives `APG_ACCEPTANCE_SESSION`, which is what makes "no requirement owned by session ≤ 4 is still a placeholder" a gate failure rather than a convention. Moving it early produces a red gate through every intermediate run, which suspends the only signal that would catch a regression in them.

### 2.4 ADRs to write

Numbering continues from **0039**.

| ADR | Title |
|---|---|
| 0040 | A loopback publication is not a public port |
| 0041 | Two transports, three access profiles |
| 0042 | Host port allocation is state, keyed by the identity the volume carries |
| 0043 | The access broker is a release, reached through a trampoline |

0040 is the one that reopens currently-passing P0 tests and is therefore mandatory. 0041 pays for the schema-4 bump. 0043 exists because ADR 0037 forbids the shape the runbook proposed; if the broker is deferred, 0043 is not written.

---

## 3. Environment feasibility

### 3.1 The three execution environments

Session 3 used two. Session 4 restores the third, and unlike Session 3's case it is not vacuous (D82).

| Concern | Where it is provable |
|---|---|
| Schema v4, migration path, render determinism, Compose model shape, INI static contract, port-registry logic, command contracts | offline |
| PgBouncer image version, `psql` presence in the image, prepared-statement behaviour in transaction mode | **needs the image**; a locked-digest pull in CI or on the host |
| Role activation, HBA behaviour under NAT, pooling, saturation, queue timeouts, session-state isolation, restart and rotation | host |
| Two-project pooled and direct isolation | host, two projects |
| **The allocated loopback ports are closed from outside** | external — and this is the reason external mode returns |
| Client compatibility (Prisma, Node, Psycopg) | host, through the tunnel or a controlled container |

### 3.2 Three numbers that must be measured before anything is published

> **Measured in Run 1.** All three, against the locked digests, on Docker 29.5.2.
> The values live in `tests/contract/test_image_contracts.py`, not here.
>
> 1. **A published loopback port matches `host all all all scram-sha-256`**, not
>    the trust line. The server sees the bridge gateway (`172.17.0.1`), and a
>    wrong password is refused. The control — the same wrong password over the
>    container's own loopback — matched the `127.0.0.1/32 trust` line and
>    succeeded, which is what makes the first result mean anything. **Session 4
>    ships without an HBA plane**, and the fact is asserted by a test that runs
>    wherever Docker does, including in the host gate, because it is a property
>    of the daemon rather than of this repository.
> 2. **The pooler image carries `psql` and `pg_isready` (17.5).** The readiness
>    check has a client. It also runs as **uid/gid 70** with a default user set,
>    so unlike the cluster it never starts as root — a third UID after 999 and
>    65532, and secrets granted to it must be readable by 70 at mount time.
> 3. **Prepared-statement tracking works at the locked 1.24.1.** A named
>    statement is reusable across an *observed* backend change with
>    `max_prepared_statements = 100`, and unusable across the same change with
>    `0`. The negative case is what proves the positive one is the pooler
>    working rather than the client landing on the same backend. **No bump**
>    (D85, D98).
>
> One hazard found while measuring: the image's documented configuration
> interface is `DATABASE_URL`, whose password the entrypoint parses and writes
> into the user list, and whose own comment notes that `docker inspect` will
> show it. That interface is unusable here. Session 4 mounts a rendered INI
> instead, which works because the entrypoint skips generation when a config
> already exists — asserted, because it is the load-bearing half.
>
> The memory measurement of §3.3 is **not** among these and remains open; it
> needs the saturation test in Run 8.

Each of these has a plausible answer that is wrong, and each has a neighbouring form that has already cost this project a run:

- **Which `pg_hba.conf` line a published loopback port matches** (D90). Docker NAT should make the source the bridge gateway, landing on `scram-sha-256`. If it lands on the `127.0.0.1/32 trust` line instead, publishing a port grants unauthenticated access to every process on the host, and every credential test still passes.
- **Whether the locked PgBouncer image contains a usable `psql`** (D85). The readiness check needs one. Assuming a third-party image's contents is how a health check becomes a health claim.
- **What PgBouncer costs in unreclaimable memory under the saturation test** (D94). `anon + shmem`, measured from the container's own `memory.stat`, on a host with no swap.

None of these is knowable from documentation. All three are cheap to measure and expensive to be wrong about.

### 3.3 Capacity

```
total 3814 MiB     swap 0     vCPU 2
in use with two Session 3 clusters: ~785 MiB, ~3030 MiB available
per cluster, unreclaimable: ~218 MiB under load, ~22 MiB idle
```

Two poolers must fit in what remains with the same headroom discipline D52 established: the **guardrail** is computed over unreclaimable memory and rendering fails when the declared sum exceeds it; `mem_limit` is set **above** the guardrail with deliberate cache headroom, because a container memory limit caps page cache too and a limit sized from an anonymous-memory formula produces a service that pegs it permanently and never OOMs.

### 3.4 What CI can and cannot assert

CI runs `--mode offline`. It can assert every schema, model, INI-shape, registry, allocation-logic and command-contract claim. It cannot assert a pool state, an HBA resolution, or a closed port. The image-contract tests sit on the boundary and are marked so a runner without Docker reports that rather than a verdict (ADR 0018).

---

## 4. Safety plan for irreversible operations

Session 2's irreversible operations were about losing access to a host; Session 3's were about losing data. Session 4's are about **exposing** data.

### 4.1 The published port

This is the one Session 4 operation that can turn a private database into a public one, and the failure is silent from the inside: every authentication test passes whether or not the world can reach the port.

- The runtime override is the only place a publication may be written, it is root-owned, and every entry must carry an explicit loopback `host_ip`.
- **A publication is not published until an off-host scan has failed to reach it.** The deploy marks the allocation `reserved`, publishes, verifies from the host, and only then may the gate's external mode mark the claim proved. Deployed output may not report `ready` before the negative checks pass.
- `0.0.0.0`, `::`, a public interface address, host networking, UDP, and a publication without `host_ip` are refused in the model and on the host.

### 4.2 The port allocation

An allocation that moves silently breaks every developer's saved tunnel and every documented command.

- Reuse is the default; reassignment requires an explicit release after project shutdown and identity confirmation.
- `reserved → active` only after endpoint checks pass, so a crashed first deploy leaves a reservation that can be proved unadopted rather than an active allocation nothing uses.
- Never reassign an initialized project because a lower port became free.

### 4.3 The credential rotation

Zero-downtime rotation is explicitly out of scope, which makes the split-brain state the thing to plan for: PostgreSQL holding one password while the pooler holds another.

- Determine which plane holds which credential **before** making a second change.
- Never publish `ready` with the two disagreeing.
- Do not generate a third password to escape a two-password problem.

### 4.4 The disposable compatibility schema

The Prisma migration test creates a schema in the **live project database**. It is created and dropped through the container-local privileged socket, never through the TCP endpoint, because `migration_user` deliberately holds no database `CREATE`. Its exact identity is recorded in root-owned state before the unprivileged test sees it, the drop targets only the recorded name, and protected schemas — `api`, `app`, `app_private`, `extensions`, `public`, `pg_catalog`, `information_schema` — are refused by name. A cleanup failure is a gate failure, not a warning.

---

## 5. Build order

Runs are sized so each ends with a green gate and a reviewable commit. The offline runs come first and carry no host risk; nothing touches a published port until Run 5.

### Run 1 — ADRs, requirement IDs, versions, and the three measurements
*Offline, plus a container runtime.* **Done.**

ADRs 0040–0043 as drafts of record. The ten new requirement IDs added as `future` placeholders. `CURRENT_SESSION` stays `3` (D54).

Then the three measurements of §3.2, each written into a contract test rather than into this document: the PgBouncer image's reported version and tool inventory, its prepared-statement behaviour in transaction mode, and — as soon as a throwaway publication can be made safely — which HBA line a NAT'd loopback connection matches. **`tests/contract/test_image_contracts.py` is the only place the values themselves are written down**, deliberately, so that there is one authority and it is executable.

The Prisma major is settled here (D86), and the PgBouncer candidate is either kept or bumped (D85), with the reason recorded.

### Run 2 — Schemas and static contracts
*Offline.* **Done.**

> Two things Run 2 found that the plan did not anticipate.
>
> **`CFG-010` had to be versioned.** It is a *Session 1* P0 — "public pooler
> exposure requires a specific CIDR allowlist" — and ADR 0040 removes the
> configuration it describes. D83 anticipated reopening `SEC-NET-001/002`; it
> did not anticipate that the manifest has carried `pooled_public` with an
> allowlist since Session 1. The replacement is stricter in the direction ADR
> 0017 requires: every input the old pair accepted is now refused, and nothing
> it refused is now accepted.
>
> **A check that could not fail, written while reading the ADR about them.** The
> host range validator originally refused a range containing 80 or 443. It could
> not fail: `allocatablePort` has a minimum of 1024, so any range containing
> those must start below 1024 and the schema refuses first. Both tests passed —
> on the schema's error, not the check's. Only `ssh.port` can legitimately sit
> above 1024, so it is the only listener checked, and the constant that used to
> hold 80 and 443 now records why they are not there.
>
> **Consequence to carry into Run 5:** every deployed document on the host is
> version 3 and no longer validates. Nothing the host *executes* reads the
> version — the launchers and `project-runtime.sh` do not validate it — so
> nothing breaks before the redeploy, but the redeploy is what makes the host's
> state readable by this code again.

Outputs schema v4 on both branches, `access_profiles`, the `v3 → v4` migration in `output_migrations.py`, a committed `tests/fixtures/outputs-v3.json`, and the standing rule that migration never produces a *deployed* document. The port-allocation registry schema. The project manifest's pool fields, with validation: `pool_size >= 1`, `max_client_connections >= pool_size`, `max_prepared_statements > 0`, timeouts inside committed bounds, and `pooled_public: true` failing closed with a stable unsupported-profile error. Host manifest gains its `database_access` section and its schema version moves with old readers failing closed.

### Run 3 — Secrets and the pooler's grant surface
*Offline, then one host materialization.* **Done, with one finding that stops Run 5 until it is settled (D100).**

> **On the host.** `host.yaml` moved to schema version 2 and gained
> `database_access` (backed up first). Both projects' bootstrap plans reported
> **no changes** — correctly: the provider bootstrap seeds `active_secrets` for
> a *session*, and it defaults to `CURRENT_SESSION`, which is 3. The two new
> secrets are `introduced_in_session: 4`, so they were excluded by the gate that
> exists to exclude them. Nothing was created, nothing rotated, no generation
> repointed, all four containers healthy throughout.
>
> **What that half did prove**, from `materialize-secrets --plan --session 4`,
> which contacts nothing and writes nothing: both new files resolve to
> `generations/<id>/pgbouncer/…` at `0400 70:70`, in their own consumer
> directory. The grant surface, the ownership and the paths are right, and ADR
> 0033's override needed no new code to produce them.
>
> **And it found D100**, which is the finding of the run: a session-4 deploy is
> impossible while `CURRENT_SESSION` is 3, and moving `CURRENT_SESSION` makes
> fifteen requirements overdue. The provider convergence this run was supposed
> to demonstrate is a *consequence* of that, not a separate problem — bootstrap
> would create both secrets under `--session 4`, and it is the same decision.

> **The pooler service landed here rather than in Run 4**, because the secret
> contract cross-checks every consumer against a real Compose service and its
> `user:`. A secret naming `pgbouncer` as its consumer cannot be declared before
> the service exists. Run 4 keeps the port allocator, the publication, the
> health check and `--render-runtime-only`.
>
> **Measured, against the entrypoint Compose actually renders** — not the one in
> the source file, which is a different string:
>
> - A **plaintext** user list under `auth_type = scram-sha-256` authenticates the
>   client *and* lets the pooler log in upstream; the cluster records
>   `method=scram-sha-256` for the pooler's own connection. The SCRAM-verifier
>   form also works and is unavailable here: it can only be read from the
>   cluster, so the role would have to exist before the file that creates it.
> - The rendered entrypoint produces a correct INI, a `0600` user list in tmpfs,
>   an application login that succeeds, a wrong password that is refused, and an
>   admin console answering `SHOW CONFIG` with `pool_mode=transaction`,
>   `max_prepared_statements=100`. No credential in `docker inspect` or the log.
> - **The pooler starts and listens when it cannot read its auth file.** It logs
>   `could not open auth_file … Permission denied` as an ERROR and goes on
>   accepting connections, refusing every one. Nothing about a listening port
>   distinguishes that from a working pooler, which is why Run 4's health check
>   must authenticate rather than connect — asserted now, so a `pg_isready`
>   health check fails a test rather than passing review.
>
> **Two harness bugs worth recording**, both of which made a probe report
> nothing while looking like a result. `docker compose config` **re-escapes**
> `$` as `$$`, so the printed model is not the string the container receives —
> extracting it verbatim gives `sh` a `$$` to expand into its own PID. And
> `</dev/null` on a `docker run` that is being *fed* by a pipe silently emptied
> both secrets, so the first run measured two zero-byte credentials. The
> `</dev/null` habit is for commands that might read stdin, never for one whose
> stdin is the input.



`app_runtime_password` and `pgbouncer_admin_password` join `secrets.required.yaml` with their consumers, uids, gids and modes. Per ADR 0036 the provider bootstrap creates whatever the contract declares, so a project bootstrapped in an earlier session converges by acquiring them; an existing secret is adopted, never overwritten. The Compose grant surface follows automatically from ADR 0033 — nothing new renders it, which is the point of having built it.

The PgBouncer entrypoint assembles its user list in tmpfs at `0600`, from mounted secret files, and never writes it to a persistent volume. No password enters `compose.env`, the resolved model, `docker inspect`, argv on either side of the daemon, or a log.

### Run 4 — The port allocator and the privileged render
*Offline.* **Done.**

> **The health check proves less than this plan asked for, and says so (D101).** `project-runtime.sh up` runs `compose up --wait` and *then* the deploy runs `postgres-bootstrap`, which is what creates the application role. So on a first deploy that role does not exist when the check first runs, and a check that connected as it would fail `--wait` and take the deploy down with it. The backend round-trip therefore belongs to the client proofs, which run after bootstrap. What the check does prove is the failure Run 3 measured — measured again here, both ways: a working pooler passes and prints nothing, and a pooler whose user list it cannot read **fails while its port is open**, which is what a port check would have called healthy.
>
> **The publication cannot be part of a first `up`, and that is structural.** The allocation key is the instance UUID the volume carries, and that UUID does not exist until the cluster has bootstrapped an empty volume — which happens after `up` returns. So the first start publishes nothing and `--render-runtime-only` adds it afterwards. D95 anticipated the shape without naming the reason; the reason is ADR 0042's key.
>
> **The credential does not reach the health command's environment.** Session 3 banned that variable's name from the model outright, and narrowing the ban to "only when read from a file" would have been a weakening dressed as a refinement. A `.pgpass` file in the same tmpfs needs no exception at all, and keeps the value out of `/proc/<pid>/environ` as well.
>
> **Two of my own mistakes, both the same shape.** An appended `deploy()` helper redefined the one every earlier test in that file used, so seven passing tests silently began measuring a different program; and an appended test reused an existing test's name, which is not a duplicate but a deletion. Ruff's F811 caught the second. Both are the module-level equivalent of the defect this project keeps producing: something that looked like it was still being checked, and was not.

The pooler service itself landed in Run 3 (D89's consumer cross-check forced it). What remains here is its health check — proving the admin identity, the pool mode, the prepared-statement setting and a backend round-trip, **without a password in a health command or its output**, and without being satisfiable by a listening port, which Run 3 measured is not the same thing.

`bin/database-ports.sh` with `allocate`, `verify`, `show`, `release`, under a host lock, validating the registry before mutation, checking both the registry and actual bind availability, allocating both ports as one transaction, and reusing an existing allocation on redeploy.

`deploy.sh --render-runtime-only` (D95) lands here: it can reserve and render without moving a container, which is what makes the first publication recoverable.

### Run 5 — Role activation and the migration that carries it
*Offline. The code, not its execution.* **Done.**

> **Migration 0006 revokes what Session 3 granted.** `app_runtime` held `USAGE` on `app` and `app_private` and full DML on both base tables. That was defensible when nothing connected as it; Session 4 hands the credential to an application, and direct table reach is the difference between a compromised application seeing its own rows and seeing the shape of everything. Revoked in a *new* migration rather than edited into 0001 and 0003, because an applied migration is immutable and the preflight exists to catch exactly that rewrite.
>
> **Measured against a real cluster, not just parsed.** All six migrations apply in order. The role-level settings land — `search_path=api, pg_temp`, `statement_timeout=30s`, `idle_in_transaction_session_timeout=60s` — read back from `pg_roles.rolconfig` rather than assumed. The membership options are `admin=f inherit=t set=f`. A table created *after* the migration is also unreachable, so the `ALTER DEFAULT PRIVILEGES` stored something this time. `CONNECT` yes, `CREATE` and `TEMPORARY` no. And the api surface still answers. D102 and D103 are what that measurement changed.
>
> **The connection limit is queried, not assumed** (D94). `max_connections` and `superuser_reserved_connections` come from the running server, minus headroom for the migration plane and an operator's psql. A budget with no slack is one where the first thing to fail is the tool you would use to find out why.
>
> **Three harness bugs, each of which stopped the measurement before the thing under test.** It created three roles where the document declares thirteen, so migration 0001 failed on the fourth. It piped migrations without a transaction, where `SET LOCAL ROLE` is a warning and a no-op — the migration would have run as the superuser and proved nothing about the owner's authority. And it omitted `REVOKE ALL ON DATABASE … FROM PUBLIC`, then reported `TEMPORARY = true` for the runtime role: PUBLIC's default grant, not anything this system had given it.

The role activation is a privileged, idempotent bootstrap action: `LOGIN` and a SCRAM password set over the container-local socket from the mounted secret, never through argv and never printed; `NOINHERIT` preserved at role level with `authenticated` membership granted `INHERIT TRUE, SET FALSE, ADMIN FALSE`; `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS` preserved; `CONNECT` granted, `CREATE` and `TEMPORARY` not; an explicit `CONNECTION LIMIT` that fits the computed budget.

The migration that belongs in database history — grants through `authenticated`, a safe `search_path`, conservative statement and idle-transaction timeouts, explicit revocations — is a normal immutable migration in `migrations/templates/`, named in `manifest.json`, frozen in `released.lock.json`, and recorded in the ledger **by the superuser** (ADR 0034). Password changes are secret lifecycle and appear in no migration.

### Run 6 — The connection helper and the access broker
*Offline.* **Done.**

> **`bin/connect.sh` left `FUTURE_STUBS`, the third application of ADR 0017.** What replaces `test_future_stub_exits_ten` is `tests/contract/test_connect_command.py`, and most of it runs end to end rather than reading the source: a recorded tunnel is a real process the test starts, and the host is a fake `ssh` on `PATH`. So "the credential reaches the child in a `0600` file and is gone afterwards" is measured.
>
> **The two properties whose failure would be silent get the most attention.** *Nothing prints a password* — checked by asserting the exact byte sequence the fake host returns appears nowhere the helper writes to a terminal. *A tunnel is stopped by recorded identity, never by name* — checked by recording a **live** process under a **wrong** argument vector, which is exactly what a reused PID looks like, and asserting the helper leaves it alone. An implementation that signalled by PID, or matched by process name, kills it there.
>
> **The broker's decision is Python, not shell, and that is the design.** `libexec/database-access-broker` resolves an interpreter and execs; `access_policy` decides and `access_broker` resolves, both against a directory tree in `tmp_path`. That is what makes a stale generation pointer, two live allocations under one project key, and a drifted `password_secret_ref` testable at all — each takes a rotation, a rebuild or a bad deploy to produce on a real host.
>
> **The password comes from `active-secret-generation.json`, not from the deployed document.** Both name a generation; after a rotation they differ, and the document's is the one that no longer authenticates. Proved by materializing two generations with different values and asserting which one comes back.
>
> **One `sudo -n` rule, checked with `visudo -cf` before it is installed.** An invalid file in `/etc/sudoers.d` does not break one rule, it breaks sudo — on a host whose only administrative path is sudo over SSH. That is the sshd lockout with a different name, and it costs one check to avoid.
>
> D104, D105, D106 and D107 are what writing it changed. D104 amends ADR 0043 on acceptance.

`bin/connect.sh` leaves `FUTURE_STUBS` (D88) with `tunnel`, `psql`, `print-env`, `exec`, `status` and `stop`. Least-privileged defaults: `psql` defaults to `runtime_direct`; migration authority requires explicit selection and prints a warning; no command silently substitutes a migration credential because a direct transport was chosen.

SSH host-key verification is required and `StrictHostKeyChecking=no` is refused; `ExitOnForwardFailure=yes`; local binds are loopback only; tunnel state lives under `$XDG_RUNTIME_DIR` with a `0700` fallback; stale state is quarantined rather than trusted; `stop` terminates only tunnels whose recorded identity matches, never by process-name matching.

The broker follows D96's trampoline split, with enumerated operations, no caller-supplied path, no arbitrary secret name, and a policy file that is root-owned, schema-validated and atomically published.

### Run 7 — Client fixtures
*Offline.* **Done.**

> **Four fixtures, one contract.** `psql` first, because it is the client with no framework between it and the boundary; then Node `pg`, Psycopg 3 and Prisma at the locked major (D86). Each runs the same six checks, so a difference between them is attributable to the driver rather than to the test.
>
> **Built and measured, not just written.** All four images build. psql is 17.5 in the pooler image, so `\bind` — real protocol-level parameter binding, which psql gained in 16 — is available, and the fixture refuses to run rather than fall back to interpolating values if it ever is not. `pg` resolves `pgpass` 1.0.5 in the committed lock, which is what makes `PGPASSFILE` work for a driver that is not libpq; that was read off the resolved dependency tree rather than assumed. Psycopg is 3.2.12 on Python 3.12.13. Prisma generates a 6.19.1 client with the `linux-musl-openssl-3.0.x` engine. Every fixture refuses a missing environment with `2` and names the first missing variable, not the last.
>
> **`?pgbouncer=true` is refused, not merely unused.** It is the flag that would make DBX-002 pass against the fallback path while the report still said Prisma works through the pooler — the exact shape this run was told not to produce. The pooler runs `max_prepared_statements` above zero (Run 1); if that stops being true the fixture must fail, so the refusal is code and the test asserts every line naming the flag is part of it.
>
> **Both halves of isolation, in all four.** "User A sees none of user B's rows" is true of an empty table; "user A sees its own" is true with no policy at all. Every probe counts both, every probe sets the claim with `set_config(..., true)` rather than `SET`, and every probe proves `app.notes` is unreachable by *attempting the read* — because D103 measured `has_table_privilege` returning true for it while the read is denied.
>
> **`code_only` now strips `//` and SQL `--`**, and the boundary is where a failure put it: a bare `--` prefix also matches a shell continuation line beginning with a long option, and stripping those removed `--edge-static` from `edge.sh`'s `do_up` and turned a passing ordering assertion into a false failure. A SQL comment is `--` followed by whitespace or nothing.
>
> D108, D109 and D110 are what writing it changed. D108 is the one with a running cost: rotation now reaches five files for `app_runtime_password` and two for `migration_user_password`, corrected from six against Run 9's materialization plan.


`psql` first, because it is the client with no framework between it and the boundary. Then Node `pg`, then Psycopg 3, then Prisma at the locked major (D86) — runtime through the pooler, migration through the direct transport against the disposable schema (§4.4).

Every fixture pins dependencies through committed lock files, sets `application_name`, uses parameterized queries, sets request claims inside explicit transactions, proves User A cannot see User B's rows, and exits non-zero on an unexpected row count. **A prepared-statement test may not be made to pass by disabling prepared statements**, unless it is explicitly the documented fallback case and named as one. Fixtures live under `services/clients/<name>/` (Run 1).

### Run 8 — Activation
*Offline. The run D100 exists for.* **Done.**

> **All fifteen placeholders deleted, fifteen requirements repointed, and `CURRENT_SESSION` moved from 3 to 4, in one commit.** D54's rule, applied for the third time: the constant and the implementations it vouches for move together, or the constant means nothing.
>
> **`DEP-ISO-004`'s credential clause has its own node ID**, which is what the comment beside the placeholder said Run 8 would have to do. "The role names differ" and "one project's credential is refused by the other's cluster" are different claims, and D70 is what happens when one stands in for the other.
>
> **Every test here is deselected in an offline gate**, so every one states in its own docstring what would have to break for it to go red. Where a property could be satisfied by an absence, both halves are asserted: the pool holds the server count down *and* every client completes; 443 is proved open from the same scanner or every "closed" is meaningless; the foreign credential is refused only after the role's own is accepted; the api surface answers or the privilege refusals prove nothing; the claim is asserted *inside* its transaction or its later absence would pass against a cluster where `set_config` never worked.
>
> **The prepared-statement test fails when the backend does not change.** A run where the client happened to keep one server proves nothing about surviving a change, and reporting that as green is the defect this whole session keeps circling.
>
> D111 is the one structural divergence: SEC-DBX-002 and SEC-DBX-003 sit under `tests/deployment/` with the `security` marker, because the fixtures that make them measurable are in that conftest.
>
> **Nothing here has been seen to pass.** Run 9 is the first run that executes any of it.


**All fifteen Session 4 placeholders are deleted and replaced with real tests, and `CURRENT_SESSION` moves from 3 to 4, in one commit.** `DBX-001..005`, `DBX-POOL-001..003`, `DBX-PORT-001`, `DEP-ISO-004`, `DX-DB-001/002` and `SEC-DBX-001..003` — the exact fifteen the registry suite names under `APG_ACCEPTANCE_SESSION=4`.

The constant and the implementations it vouches for move together, or the constant means nothing. That is D54's rule and this is the third time it has decided a build order.

The tests written here are host- and external-marked, so they are deselected in an offline gate and the Session 1 gate stays green. That is also the risk this run carries: a test that is deselected everywhere it is written is a test nobody has seen fail, and **D70 is what that costs** — a claim that read as proved for two runs behind six node IDs, none of which presented a credential to anything. Every test written here states, in its own docstring, what would have to break for it to go red.

`DEP-ISO-004`'s credential clause gains a node ID of its own here, which the registry records as an activation obligation rather than leaving to memory.

### Run 9 — The host sequence
*Host, and off-host for the negative proof. The first run that changes what is reachable.* **Done.**

> **Both projects deployed through session 4, and every Session 4 proof green: 82 passed on the host.** Two projects, four allocated ports, no overlap, both allocations `active`, and nothing new reachable from outside. `DEP-ISO-004` passes on both node IDs — the structural half and the credential clause, the latter presenting one project's runtime credential against the other's *own* role, from a container on the target's internal network, with that role's own credential accepted first as the control.
>
> **Five product defects, found by running it.** D112: the transport blocks had three readers and no writer, so a project deployed through session 4 with a healthy pooler still published a document saying every transport was unavailable. D113: the identity query read the *maintenance* database, and `-U postgres -d postgres` reads perfectly naturally. D115: Docker installs no rule and no listener for a container on an `internal: true` network — the run's one architectural change, ADR 0044. D116: a session GUC survived the pooler. D117: the fix for D116 destroyed the prepared statements DBX-POOL-003 needs, and the resolution keeps both without weakening either.
>
> **D114 was mine**, and it is in the table for that reason: `HostConfig.PortBindings` is what Docker was *asked* for, and I read it as a measurement — in the document whose whole purpose is catching that.
>
> **Five harness faults, each of which presented as a plausible product fault.** No secrets mounted; then mounted at the secret's `source` name rather than its `target`, so the credential was present, correct, and at a path nothing had reason to open; a SQL-level `PREPARE` where PgBouncer tracks only protocol-level statements, reported as "prepared statement does not exist" — indistinguishable from `max_prepared_statements` being zero; `:'var'` quoting, which is psql's SQL-literal form and turns a bind *value* into SQL; and an assertion comparing a multi-statement block against a single value. The product held up better than the instruments measuring it, and that is worth recording rather than tidying away.
>
> **The off-host scan ran before anything reported ready** (§4.1): 443 and 80 open as the positive control, and 15432, 15433, 5432, 6432 and five neighbours closed. Under ADR 0044 the expected answer is structural, and the check still goes red the day a publication is introduced.

### Run 10 — Restart, reboot, rotation, and the gate
*Host, one maintenance window, then all three environments.* **Built; the host
sequence is the last thing outstanding.**

The restart matrix extends **`DBX-PORT-001`, not `DEP-BOOT-001`** (D120): pooler
restart with the cluster up, cluster restart with the pooler configured, project
unit restart, and a reboot. After each, the allocation is unchanged, both
transports accept the runtime credential again, and no public listener appeared —
with 443 asserted **present** in the same `ss` output, so a negative from an
instrument that can see nothing is not mistaken for a closed boundary. The
restarts run against project A and assert project B undisturbed, which proves
something a second restart would not: that a project's recovery is its own.

`bin/session-04-check.sh` in the shape D82 settles, in three modes, with
`--ssh-destination` required in the external one — without it `DX-DB-001` and
`DX-DB-002` skip, and a skip is not a pass.

> **Five claims, and two of them are not the ones §7 drafted.** D118: the drafted
> `direct_transport` spans two environments and `claim_mode` refuses it, so it
> splits and `transport_boundary` is born — the first claim the external half has
> ever carried. D119: `database_isolation` gaining `DEP-ISO-004` would have moved
> it to Session 4 and *withdrawn it from Session 3's evidence*, so `DEP-ISO-004`
> gets `transport_isolation` instead. Both are in **ADR 0045**, which also
> records the general rule: extending a claim is a decision about which sessions'
> evidence records it.
>
> **A contract test that would have refused a correct claim table.**
> `test_a_mode_that_carries_a_claim_has_a_static_proof_to_run` asserted that every
> mode carrying a claim resolves at least one proof with no environment marker.
> True of Sessions 2 and 3 by accident — each of their claims happens to include a
> contract test — and not the property that matters. It is replaced by the
> coverage rule it was reaching for, and the half of it that was measuring
> something is kept as a test of its own.
>
> **A refusal that had been asserted about and never run.** The writer refuses a
> single half for a session with an external claim; Session 2 carries none, so
> that test has taken its `else` branch since it was written. Session 4 carries
> two, and it now runs.
>
> **D122 and D123 are housekeeping with teeth.** Three ADRs the host was running
> were indexed as `Proposed`, and nothing compared the index's status column to
> the ADRs — now something does. And four texts still described the publication
> ADR 0044 removed, one of them a test docstring teaching the *withdrawn* version
> of D114.
>
> Documentation: `docs/database-connections.md`, `docs/client-compatibility.md`,
> `docs/pool-operations.md`, `docs/session-04-operator-guide.md` — flat in
> `docs/`, in `REQUIRED_PATHS`, linked from `README.md` and `docs/handoff.md`, and
> recording **what was measured**: the reset query and why it is `DISCARD ALL`
> minus one statement, the five files a rotation reaches, the trust line that
> makes a loopback credential test meaningless, and the fact that a developer
> needs SSH to reach a database at all.
>
> **D124, found by running the whole thing.** The first full `--mode host` gate
> since Run 4 collected `tests/security/test_session3_authorization.py` — a
> module no run between Run 5 and Run 10 had selected — and a Session 3 P0
> assertion failed at once: `app_runtime` may log in, because Run 5 activated it,
> which is what the session is *for*. The assertion had encoded "every identity
> is a NOLOGIN stub" without the clause "until its owning session activates it
> deliberately". ADR 0046 derives the login set from the deployed document
> instead. **The finding worth keeping is not the stale test.** It is that a P0
> module went unexecuted for five runs while the acceptance matrix reported its
> requirements as covered — a matrix entry says a proof exists, and only an
> evidence document says it ran.
>
> **The host half: 143 passed, 0 failed, 3 skipped, nine claims green.** Two
> projects redeployed at this commit with their allocations intact, the restart
> matrix inside the gate rather than beside it, and the two declared proofs
> skipping exactly as designed.
>
> **D125 and D126, both from the external half — the first one run since Session
> 2.** D125 is D124 again in a different requirement: two `SEC-NET-001` proofs
> asserting the *absence* of the endpoints Session 4 publishes, false since Run 4
> and unexecuted since Session 3 dropped the mode that owns them. Two instances
> in one run is a pattern, and **ADR 0047** names it: an absence proof is a proxy
> that is equivalent only while the feature does not exist.
>
> D126 is a product defect none of this could have found by reading. `connect.sh
> tunnel` left the backgrounded `ssh` holding the caller's stdout and stderr, so
> the command returned and any caller capturing its output did not. It took a
> caller that both captured output and had a deadline — the `DX-DB-001` proof,
> timing out 120 seconds after printing its own success line.
>
> **Outstanding.** The external half re-run and merged into a session document.
> The reboot and the rotation are declared windows and block nothing: neither
> belongs to a claim, which is D121's whole point.


---

## 6. The two transports and three access profiles

The runbook's §4.1 survives unchanged in substance. Restated against the real identifiers:

| Access profile | Transport | Role | Intended use |
|---|---|---|---|
| `runtime_pooled` | PgBouncer | `<project>_app_runtime` | Prisma Client, Node `pg`, Psycopg, ordinary applications |
| `runtime_direct` | PostgreSQL | `<project>_app_runtime` | Prisma Studio, direct diagnostics, pooling-comparison tests |
| `migration_direct` | PostgreSQL | `<project>_migration_user` | dbmate, Prisma Migrate compatibility, privileged `psql` |

Role names are derived by `naming.py` from the project key and are **not named here** — the same rule D38 set for Session 3. The pooled transport rejects `migration_user`. Developer tooling defaults to `runtime_direct`; `migration_direct` is always explicit.

Three address forms per transport: project-internal (`pgbouncer:6432`, `postgres:5432`), host-loopback (`127.0.0.1:<allocated>`), and developer-local (`127.0.0.1:<temporary>`, created by the helper).

**Transaction pooling is the only mode**, and its consequences are documented rather than worked around: server sessions change between transactions; session-local state is not durable; temporary tables, session advisory locks, `LISTEN` and session-scoped `SET` are outside the compatibility promise; `SET LOCAL` and `set_config(..., true)` are the supported mechanism for request-scoped state. No Session 4 command may quietly select session pooling to make a client pass.

`app_runtime` is a **server-application credential**, not an end-user account. Possession is equivalent to possession of a trusted application server's credential and permits controlled impersonation through request context. It is never distributed to browsers, mobile clients or untrusted end users, and that sentence belongs in the operator guide, not only here.

---

## 7. Evidence and claims

Session 4 adds claims, not a format (D91). Each names registry requirements and inherits every rule ADR 0025 set: a proof absent from the artifact is `not_run` rather than `passed`, a skip is not a pass, and each claim is measured in exactly one environment — which is now checked against a set of three again.

| Claim | Requirements |
|---|---|
| `pooled_transport` | `DBX-002`, `DBX-POOL-001`, `DBX-POOL-002`, `DBX-POOL-003` |
| `direct_transport` | `DBX-001`, `DBX-003`, `DBX-005`, `SEC-DBX-001` |
| `connection_tooling` | `DX-DB-001`, `DX-DB-002` |
| `database_isolation` | gains `DEP-ISO-004` |

**Decided in Run 1: there is no `client_compatibility` claim, and `DBX-004` belongs to no claim.**

The draft put `DBX-004` — Node `pg` and Psycopg through the pooler, the session's only **P1** — alone over a claim of its own, and said to decide that here rather than in Run 10. Giving it companions would not have fixed it: a claim fails if any of its proofs fails, and under ADR 0025 a proof absent from the artifact is `not_run` rather than `passed`, so either way a deferrable requirement would have decided the evidence document.

A claim is the thing a release blocks on. `DBX-004` is P1 precisely because it must not block one. Belonging to no claim is what makes its priority mean something, and it is not thereby unwatched: the registry carries it, the acceptance matrix prints it, and the gate's rule that no requirement owned by session ≤ 4 may remain a placeholder still forces it to be implemented and run in Session 4. It may then fail without failing the release, which is what P1 says and what a claim over it would have quietly overridden.

Client compatibility as a property is still claimed — `DBX-001` and `DBX-003` under `direct_transport`, `DBX-002` under `pooled_transport`. What disappears is a claim named after an activity rather than after a guarantee, which is the shape ADR 0025 replaced in the first place.

Claims resolve their session from the registry (ADR 0039), so all five above resolve to 4 and Session 3's six remain provable and proved.

---

## 8. Security invariant matrix

| Invariant | Positive proof | Negative proof |
|---|---|---|
| Pooling is transaction mode | `SHOW CONFIG`, client tests | A session-pooling configuration is refused |
| Neither transport is public | Host-local and tunnelled connections succeed | Off-host scan finds both allocated ports closed while 443 is open |
| Only the edge publishes publicly | Traefik publishes 80 and 443 | Every other publication carries a loopback `host_ip`; a missing `host_ip` is refused |
| The runtime role is least privileged | `api` view and RPC succeed under RLS | `app`, `app_private`, DDL, `TEMP`, and every `SET ROLE` fail |
| Migration authority is separate | dbmate and Prisma Migrate succeed on the direct transport | The pooler rejects `migration_user`; the pooled profile cannot reach migration authority |
| Credentials are not serialized | Authorized helpers execute clients successfully | No password in outputs, argv, `docker inspect`, logs, evidence or the INI |
| Prepared statements work | Repeated named statements across a proven backend change | The test fails rather than passing with preparation disabled |
| Pooled state is isolated | A claim set inside a transaction is visible in it | Transaction-local **and** deliberately set session-level state are absent for the next client |
| The budget is bounded | Concurrent clients complete | Server connections never exceed the configured budget |
| Projects are isolated | Each project's clients connect | Cross-project credentials fail against the target's **own** role, from its internal network |
| Allocations are stable | Redeploy, restart and reboot retain ports | An identity mismatch cannot adopt or reassign an allocation |

---

## 9. Risks and stop conditions

**Stop before mutating** when: the Session 3 gate is not green; the project identity in deployed state does not match the cluster's sentinel; the installed release differs from the one the deployment records; the port registry is invalid, group- or world-writable, or holds duplicate active ports; configured ranges overlap each other or a reserved listener; the project already holds a different immutable allocation; a requested port is bound by something unrelated; the runtime role has unexpected privileges; the pooler image digest does not resolve to the expected version; a required consumer file is missing from the active secret generation; or the checkout is dirty where a release requires a clean tree.

**The specific risks of this session**, in the order they are likely to bite:

1. **A published port lands on the trust line** (D90). Measured in Run 1, before Run 5 publishes anything.
2. **The locked pooler image lacks the tools the readiness check assumes** (D85). Measured in Run 1.
3. **Reopening `SEC-NET-002` weakens it by accident** (D83). The replacement assertions must be stricter than the ones removed, and the live test must read `host_ip` rather than count publications.
4. **A claim over a P1 requirement makes a deferrable proof release-blocking** (§7).
5. **Two poolers plus two clusters exceed the memory guardrail** (D94). Measured under Run 8's saturation test, not estimated.
6. **The evidence names the deployed release rather than the reviewed one.** True by design and true today; if Session 4 wants them equal, the last deploy happens after the last code commit, deliberately.

---

## 10. Open items carried in

- **`requirements-dev.in` pins nothing**, so `bin/lock-dev-deps.sh --check` re-resolves against PyPI and fails the day any dependency ships. It has bitten in two sessions now.
- **ADR 0019's follow-up CI job is unbuilt.**
- **The Infisical control-plane identity still holds organisation admin**, and a `.save` copy of that credential is still on the host.
- **Secret generations accumulate with no pruning.** Session 4 adds two secrets per project and a rotation procedure, which makes this the session where pruning stops being free to defer — and ADR 0038 records the constraint pruning must respect: a deployed document names the generation it verified, and removing it without saying so turns an audit trail into a dangling identifier.
- **`bin/restore-test.sh` remains the last `FUTURE_STUB`** after `bin/connect.sh` leaves.
- **`PYTHON_RUNTIME_IMAGE` selects a rolling minor tag** (D99). A test now compares the image's Python against `PYTHON_VERSION`, so a drift is loud rather than silent, but the candidate is still `3.12-slim`. Tightening it to `3.12.13-slim` would make the two pins agree by construction instead of by assertion; it is a deliberate candidate change with a re-lock behind it, so it is recorded here rather than made in passing.

---

## 11. Session 5 handoff

Session 5 receives two healthy transports per project, stable endpoint metadata in outputs schema 4, a pooled application credential, a separate direct migration credential, green client compatibility for the locked clients, bounded pool configuration with prepared-statement support, tunnel tooling, and two-project isolation evidence.

It may introduce PostgREST. It must not reuse `app_runtime` as the PostgREST authenticator, give PostgREST the migration credential, depend on session-persistent state through transaction pooling, bypass RLS, expose a private schema, or serialize a database password into OpenAPI, outputs or documentation.

Before Session 5 mutates a project, it runs Session 4's gate.

---

## Appendix — what to consult, and what to measure instead

Documentation matching the **locked** versions is worth reading for configuration keys and semantics: PgBouncer's config, FAQ and changelog; the Prisma docs for the pinned major; node-postgres queries; Psycopg's prepared-statement and transaction pages; PostgreSQL 18 on `GRANT`, `pg_hba.conf`, password authentication and libpq; and Docker's port-publishing documentation for the installed Engine.

None of it is a proof. Every number this session depends on — the pooler's version and tool inventory, which HBA line a NAT'd connection matches, the memory a pooler holds, the server-connection budget the cluster actually reports, whether a client's prepared statements survive a backend change — is measured against the locked artifact and written into an executable test. That is not caution for its own sake. It is the one rule that would have caught, in advance, the `ALTER DEFAULT PRIVILEGES` that reports success and stores nothing, the Traefik key that exists in no version, the launcher that ran two sessions out of date, and the loopback login that succeeded with a deliberately wrong password.

When a test is green, ask what would have to break for it to go red.
