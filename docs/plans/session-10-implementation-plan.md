# Session 10 — Encrypted backups, continuous WAL archiving, and a restore that was rehearsed

An encrypted pgBackRest repository in its own R2 bucket, WAL archived
continuously from the cluster that produces it, and one command that restores a
project to a chosen second **into a disposable target it creates and destroys**
— then queries the result and writes down what it measured.

**No restore that can reach the live volume. No recovery time that was not
measured. No second backup format.**

---

## 0. Where Session 10 actually starts

Session 9 closed with `evidence/session-09.json`: **48 claims, 46 passed, 2
failed**, the two red ones Session 5's and blocked on the rotation window. Both
projects run `c0816e7` with **21 migrations**, `max_connections` 56, outputs
**v12**, 16 containers, and a deployed agent write plane with a durable audit
record. The local suite is **3927 passed, 281 skipped**.

**There is no Session 10 runbook.** What this session has instead is
`docs/source-specification.md` §12 ("Backup and Recovery") and §17's Session 10
paragraph. That file is **digest-pinned** — `docs/source-specification.sha256`,
checked by `test_source_specification_checksum_matches` — so it is quoted in §1's
first column and never edited.

So §1's job is Session 9's job: the list of places where the summary asks for
something this repository already has, or asks for it in a shape this
repository's own constraints refuse. **It is longer than it looks**, because
this session's subject is the one place where Session 1 built an identity plane
and no session since has built the runtime under it.

Six things are already true and change the shape of the work:

1. **The backup identity plane exists and has since Session 1.**
   `naming.ProjectIdentity` carries `backup_stanza` and
   `backup_repository_prefix` (`naming.py:762-763`), derived at `:844-849` with
   the defaults `stanza = key` and `prefix = pgbackrest/<key>/`.
   `evidence.ISOLATED_FIELDS` already compares both across every rendered
   project pair. **Session 10 derives no new stanza and no new prefix.**
2. **`backup_user` is already one of the thirteen derived roles**
   (`naming.py:143`), a NOLOGIN stub with a null verifier — exactly the state
   `storage_service` was in before Session 7. Session 10 **activates** it, and
   D307 is the shape.
3. **The manifest block exists**, with bounds: `schemas/project.schema.json:283-315`
   declares `enabled`, `stanza`, `repository_prefix` and `retain_full`, and
   `config._validate_backup` (`config.py:1152-1171`) enforces the first three.
4. **The rendered branch of `outputs.json` already publishes `backup`**
   (`outputs.schema.json:249-274`), required since v1. The deployed branch does
   not, and that is D520.
5. **`PGBACKREST_IMAGE` is pinned by digest and referenced by nothing** —
   `versions.env:16`, `docker.io/woblerr/pgbackrest:2.55.1@sha256:8cf2e3d3…`.
   Zero hits in `compose.yaml`, `bin/`, `services/`, `tests/`, `deploy.sh`.
6. **The five requirement ids and their placeholders already exist**, in
   `tests/acceptance-registry.yaml:1585-1624` and
   `tests/recovery/test_future_pitr.py`, and **two threat-model rows already
   name those node ids** (`docs/threat-model.md:33-34`), so deleting the file
   without moving the rows reddens `test_threat_model_node_ids_are_collectible`.

Session 8 was planned as nine runs and took **twelve**; Session 9 planned one
deploy-and-gate cycle and took **five**. This session adds a container image
this repository has never built, a network object it has never created, a
credential a third party issues once, and a command whose whole value is that it
touched nothing. **Plan for the same.**

---

## 1. Divergences from the session summary

Six columns, the house shape. The "Summary says" column quotes
`docs/source-specification.md` §12 and §17. Rows are predictions made at plan
time; each is confirmed, corrected or replaced during implementation, and
anything found *during* implementation is appended with the next free number.

**Next free number after this table is D596.**

| # | Summary says | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D512** | "The session configures pgBackRest with encrypted R2 storage, retention rules…" — read as though nothing about backups exists yet. | **Session 1 built the identity plane and it is already load-bearing.** `naming.py:762-763, 844-849` derive `backup_stanza` and `backup_repository_prefix`; `naming.py:143` derives `backup_user`; `evidence.py:55-56` already compares the stanza and the prefix across every rendered project pair for `collision_count`; `schemas/outputs.schema.json:249-274` has required them on the rendered branch since v1. | **Session 10 supplies the runtime, the credential, the command and the proofs — not the names.** The only identities it adds are a repository bucket and one network, and both go through `naming.py` like everything else (ADR 0002). | Re-deriving a stanza anywhere else is exactly what ADR 0002 forbids, and the isolation evidence would then be comparing one authority against another. | — |
| **D513** | "Continuous WAL archiving." | **`archive_command` runs inside the Postgres container, and that container has no pgBackRest.** `POSTGRES_IMAGE` is `pgvector/pgvector:pg18`, digest-pinned; `PGBACKREST_IMAGE` is pinned and referenced by nothing. A sidecar sharing the data volume can take a backup but cannot serve an `archive_command`, which must return non-zero synchronously to the postmaster. | **Derive the image.** New `services/postgres/Dockerfile`, `ARG BASE_IMAGE` = the pinned digest, pgBackRest installed at a pinned version — the `services/auth-api/Dockerfile` pattern, where every version arrives as a build argument so `versions.env` stays the single authority. `archive_command = pgbackrest --stanza=<stanza> archive-push %p`. | The alternative is a sidecar with scheduled backups and no WAL stream, which makes RPO the backup interval and leaves **no point between T1 and T2 to recover to** — `REC-PITR-001` would restore to a backup boundary and `REC-WAL-001` would have nothing to measure. That is not the session. | needed |
| **D514** | — | **`PGDATA` is `/var/lib/postgresql/18/docker` while the named volume mounts one level above it at `/var/lib/postgresql`** (D53), pinned as `POSTGRES_PGDATA` / `POSTGRES_VOLUME_TARGET` in `tests/contract/test_image_contracts.py:116-117`. | **`pg1-path` is PGDATA, never the mount point.** Written once in the rendered `pgbackrest.conf` and cross-checked against the same constants the image contract uses. | D53's own note: *two of the three plausible paths persist data*, so "the row survived" does not distinguish them. A `pg1-path` at the mount point would make `stanza-create` succeed and the first restore wrong. | — |
| **D515** | "…dedicated storage credentials." | **The Postgres container runs as `999:999`.** Every existing compose-plane secret consumer in `secrets.required.yaml` is `65532:65532` except PgBouncer's `70`. `test_consumer_ownership_matches_the_service_runtime_user` cross-checks each consumer's `uid`/`gid` against the service's `user:` in `compose.yaml`. | The three backup secrets declare `uid: 999, gid: 999, mode: "0400"`. **The consumer entries land in the same commit as the mounts**, because `test_every_consumer_names_a_real_compose_service` refuses a grant to a service that does not exist (D246). | A `0400` file owned 65532 inside a container running as 999 is unreadable, and pgBackRest reports it as a repository authentication failure — the error nobody debugs by re-reading an ownership table. | — |
| **D516** | "…an S3-compatible R2 endpoint." | **The project network is `internal: true` — "No route off the host"** (`compose.yaml`, the `networks:` block). `postgres` attaches to `internal` alone. `storage` reaches R2 because it straddles `internal` and `edge`; the database does not and never has. | **A project-scoped `backup` network**: egress, no Traefik, no published port. `naming.backup_network = compose_name(f"apg-{key}-backup", context="compose_network_backup")`, beside `edge_network` and `internal_network` (`naming.py:799-800`). `postgres.networks` becomes `[internal, backup]`. | Joining `edge` would put the database on the network Traefik's public side lives on. A third network is one more object per project and keeps that boundary. **The residual cost is real and is stated, not hidden: a compromised Postgres container reaches the repository credential and the cipher pass.** | needed |
| **D517** | "…backups run with a dedicated identity." | **`backup_user` has been a NOLOGIN stub since Session 3** and is derived for every project already. Nothing has ever given it LOGIN, a credential, or a privilege. | **Session 10 activates it in Session 7's shape (D307):** the migration plane creates nothing, the **bootstrap plane** grants LOGIN, the credential and the `CONNECTION LIMIT` (D102, ADR 0067). Nothing is added to `ROLE_SUFFIXES`. | `test_only_the_activated_roles_may_log_in` derives the login set from the deployed document and **will go red the moment `backup_user` logs in**. `LOGIN_ROLES` (`tests/contract/test_deployed_output.py:1506`) and `deployed_output.activated_login_roles` (`:460`) are re-derived from the event, not restated (ADR 0096). Plan for it rather than discover it on the host. | needed |
| **D518** | — | **Activating it makes a fifth claimant on one `max_connections`.** `tests/contract/test_agent_plane_contract.py::_summands_of_the_budget_check` (`:171`) parses the arithmetic in `config._validate_connection_budget` rather than comparing it to a list beside it, precisely so **a fifth summand fails offline**. | The budget gains the claimant deliberately, with the ADR that ADR 0070 and ADR 0099 both set the precedent for. The test is **not** weakened; it is re-derived to five. | ADR 0070 exists because two claimants bounded separately sum past what the server hands out. A backup connection that cannot be opened surfaces as `too many connections for role` during the one operation nobody wants to debug. | needed |
| **D519** | "Two full backup chains retained." | **`backup.retain_full` is bounded by the schema, populated in both example manifests, and read by no code.** `_validate_backup` never touches it; there is no `BACKUP_DEFAULTS` beside `STORAGE_DEFAULTS` (`config.py:272-282`); `rendering.py:246` reads only `backup.enabled`; and it is **absent from `outputs.json`**. | `retain_full` gains a default, is validated, and is published on both branches of the outputs document, where the renderer turns it into `repo1-retention-full`. | Question 5, and it is already answered wrong here: *a bound that is validated and reaches nothing*. This is D479's shape (`audit.redact` validated and consumed by nothing) in a field that has been inert for nine sessions. | — |
| **D520** | "Recovery time and latest recoverable time must be recorded as evidence." | **The deployed branch of `outputs.schema.json` has no `backup` block at all**, and `additionalProperties: false` at every level. There is nowhere to publish a last-backup time, an archive state, a repository size or a latest recoverable point. | **Outputs v13.** One `$def` referenced from both branches — `storageSettings`' shape (`outputs.schema.json:247` and `:661`) — plus a deployed observation written by an `observe_backup` beside `observe_storage`. `SCHEMA_VERSION` moves 12 → 13 at `deployed_output.py:40`, with a `v12 → v13` step in `output_migrations.py` and a fixture. | D389 is the reason the definition is shared rather than copied: *"a copy is what let the two disagree"*, and `STO-BOUND-001` read the deployed document for a bound that was only on the rendered branch. Chosen **once** from the session's whole surface rather than a run at a time (D255, D308). | needed |
| **D521** | "pgBackRest repository using an S3-compatible R2 endpoint." | **The manifest has no `backup.bucket` and no `backup.account_id`**, and `backup.repository_prefix` is validated as a *relative* prefix (`^[^/].*/$` on the rendered branch) — so nothing today says which bucket it lives in. | `backup.bucket` and `backup.account_id` join the manifest block, and the endpoint is derived once by `naming.storage_endpoint_url` (`naming.py:572-600`) and handed to the container **finished**. `naming.backup_bucket_name(key)` defaults to `apg-<key>-backup`. | ADR 0002 and ADR 0106: the image never assembles a URL, and a second derivation of an endpoint is a second authority over one address. `_validate_storage` already re-derives through `naming` to validate rather than re-implementing the check; backup follows it exactly. | — |
| **D522** | "Scheduled full and incremental backups." | **`provision-host.sh install_units` globs `systemd/*.service` only** (`bin/provision-host.sh:691-693`). A `.timer` placed in `systemd/` is installed by nothing. | The glob widens to `*.service` **and** `*.timer` in the same commit as the four new unit files, and the timers are installed-but-not-enabled — the rule the edge and project units already follow, because *a unit that fails on every boot until the operator is ready trains an operator to ignore it*. | A schedule that is written and not installed is the same defect class as a bound that is validated and not applied (D519), one layer up. | — |
| **D523** | "…never overwrites the active database volume." | Nothing exists to prove it, and the obvious proof is defective. **An offline scan asserting the command's source never names the live volume is D277's shape** — an AST or text scan asking whether a name is *mentioned* is satisfied by dead code, and `test_no_operator_command_puts_a_service_directory_on_the_path` (D464) is the standing example in this repository of a text scan producing a false positive. | **`REC-SAFE-001` is two proofs.** Offline: the restore command's target volume and container names are *derived*, and a rig drives the command with a stubbed `docker` that records every `--mount`/`-v` argument, asserting the live volume never appears — with a control arm that a deliberately wrong derivation is caught. Host: the live cluster's `instance_uuid`, its volume's identity and its `pg_controldata` are read before and after the drill and asserted unchanged. | Question 1 of the five: *what would have to break for this to go red?* A source scan goes red only when somebody types a literal, which is not the failure anybody fears. | needed |
| **D524** | "Disposable-volume PITR command and runbook." | **`bin/restore-test.sh` exists, exits 10, and is the last `FUTURE_STUB`** (`tests/contract/test_cli_contract.py:116`). Its `--help` already documents `--target-time` and `--project-dir` — and parses neither: today any argument but `--help` exits 2. Its contract paragraph is already written and is the right one. | **The command is promoted, not created** — ADR 0017's lifecycle, fourth and final application after `bootstrap-providers.sh`, `migrate.sh` and `connect.sh`. `FUTURE_STUBS` becomes `()`, `test_the_remaining_stubs_are_the_ones_later_sessions_own` is **replaced by something stricter**, and `tests/contract/test_database_commands.py:196`'s cross-module guard — `assert "bin/restore-test.sh" in FUTURE_STUBS` — moves in the same commit. | ADR 0017 exists so that emptying `FUTURE_STUBS` is never a way to make `test_future_stub_exits_ten` pass. The replacement assertions must be stricter than the ones removed; `test_connect_is_no_longer_a_stub` is the precedent (exit 2, and *"a 10 here means the command went back to being a stub"*). | 0017 |
| **D525** | — | **`.github/workflows/ci.yml:134` still asserts `CURRENT_SESSION == 2`.** It has been wrong for seven sessions, which means the job has not run or has not been read. | **Recorded, not silently repaired.** The repair is to derive the number the way `bin/session-01-check.sh:45-50` does, not to bump a literal to 10 — and it belongs with ADR 0019's unbuilt CI job, which is a standing open item. | A literal that has been wrong for seven sessions and reddened nothing is evidence about the *job*, not about the number. Bumping it would remove the evidence. | — |
| **D526** | — | **`bin/render-acceptance-matrix.py:96` hard-codes `"active"` for session 1 alone**: `status = "active" if session == 1 else f"placeholders owned by Session {session}"`. | The generator learns the gate session, so the summary row for every activated session reads `active`. Regenerated in the same commit that activates the five ids. | Otherwise `docs/acceptance-matrix.md` will say *"placeholders owned by Session 10"* beside five live, passing requirements — a generated document asserting the opposite of the tree, which is the drift the generator exists to prevent. | — |
| **D527** | — | `docs/source-specification.md` is digest-pinned by `docs/source-specification.sha256` and checked by `test_source_specification_checksum_matches`. | The brief is **quoted** into this table's first column and never edited, however wrong a line turns out to be. Corrections live here. | The same rule every prior session applied to its runbook, with the checksum making it structural rather than a convention. | — |
| **D528** | "…health checks that expose failures." | Nothing measures how a failed archive actually surfaces. The tempting proof is a log grep. | **`REC-WAL-001` is measured against `pg_stat_archiver`** — `last_failed_time`, `last_failed_wal`, `failed_count`, `last_archived_time` — with a green control in the same invocation, and the container healthcheck reads the same view rather than a second source. | D374: *a test can check a string its target cannot contain*, and it passed for an unrelated reason. A log line is a third party's formatting decision; a catalog view is the product's own report. | — |
| **D529** | "Recovery time and latest recoverable time must be recorded as evidence." | Nothing measures either, and both are trivially fakeable. | **RTO is wall time recorded by `bin/restore-test.sh` itself around the restore**, and the **latest recoverable time is read from `pgbackrest info`**, never from the clock and never from the requested target. The evidence document records requested target **and** achieved recovery point as separate fields, because a restore that lands early is the failure this pair exists to expose. | Session 9's handoff states it as a prohibition: Session 10 must not *"record a recovery time it did not measure."* D267 is the general rule — never write a measurement you did not run. | needed |
| **D530** | — | **`ADMINISTRATION_RESERVED_CONNECTIONS = 5` already claims to hold connections "for migrations, backups, a direct developer session and PostgreSQL's own `superuser_reserved_connections`"** (`config.py:303-306`). So the budget arithmetic may already contain the backup allowance, unnamed. | **Decide, do not assume.** Either the backup claimant is charged its own summand and the administration reserve's comment is corrected, or the reserve *is* its budget and `backup_user`'s `CONNECTION LIMIT` is set from it — and the ADR says which, with the number. | D327's shape: the manifest's arithmetic and the bootstrap plane's arithmetic *"agreed by coincidence, 23 against 20"*, and nothing compared them until Session 7. Two arithmetics over one budget is how a fifth claimant becomes a sixth. | needed |
| **D531** | — | **The plan predicted the multi-stage `COPY` route would fail on musl-versus-glibc. It does not, and it fails anyway.** Measured (rig1): the pinned `woblerr/pgbackrest:2.55.1` image is **Ubuntu 24.04, glibc** — there is no musl anywhere in this question. The `COPY` builds and the binary will not load: `error while loading shared libraries: libssh2.so.1: cannot open shared object file`. Every other soname resolved, `libc.so.6` included. The Debian 12 base does not ship libssh2, and the PGDG install adds exactly that library beside the package. | **A1, the apt route.** The plan's stated reason for refusing A2 is **corrected in place rather than quietly dropped**: the route is dead for a mundane missing-library reason, not an ABI one. | A prediction that reaches the right conclusion by the wrong mechanism is the thing this project is worst at noticing — it reads as a confirmed measurement forever after, and the mechanism is the part a future reader reuses. | 0144 |
| **D532** | "pgBackRest installed at a pinned version." | **PGDG does not carry the pinned version.** Measured: `apt-cache madison pgbackrest` inside the Postgres base offers **2.59.1, 2.59.0, 2.58.0** from PGDG and 2.45 from Debian. `PGBACKREST_IMAGE` pins **2.55.1**, available from neither. The pin and the installable version cannot be made equal. | **`PGBACKREST_IMAGE` is retired from `versions.in.yaml` and `versions.env` in Run 4**, and the derived image's apt pin becomes the authority. Installed and measured: `pgbackrest 2.59.1-1.pgdg12+1`, two packages added, **800,863 bytes** on a 158,801,932-byte base. | Keeping both puts two pgBackRest versions in one lock — one inert and wrong, one real — and D201 is the record of which one a reader quotes: `SCALAR_VERSION` named a release that had never existed, for four sessions. | 0144 |
| **D533** | — | **An apt version pin is not a digest.** PGDG is a rolling repository that removes superseded versions, so `pgbackrest=2.59.1-1.pgdg12+1` will eventually stop resolving. | **Accepted, and stated.** Measured: an unresolvable pin exits **100** and produces no image — the build **fails closed**, which is the acceptable half. Nothing moves silently, and refreshing the pin is a deliberate edit. `bin/lock-versions.sh` is where a later session teaches the lock about apt pins. | D99's shape (`PYTHON_RUNTIME_IMAGE` selects a rolling minor tag), with one difference that matters: this pin cannot drift into a *different* build, only into no build. A failure that is loud and total is not the defect a floating tag is. | 0144 |
| **D534** | "…health checks that expose failures." | **`pg_isready` cannot see a broken archiver, and `pg_isready` is the healthcheck `compose.yaml` uses today.** Measured over 60s against a cluster with `archive_command=/bin/false`: `failed_count` 11 → 15 → 26, `archived_count` **0**, `pg_wal` **5 → 6 → 11 files** — and `pg_isready` answered *accepting connections* at every sample, container status `running`, while the `/bin/true` control archived cleanly and held `pg_wal` flat at 4. | **`REC-WAL-001`'s signal is a new one**, reading `pg_stat_archiver`. Whether the Postgres healthcheck gains an archiving clause or a second check carries it is decided in Run 7, with the numbers in hand. | A cluster archiving nothing and filling its disk toward the outage this session exists to prevent is currently reported **healthy**. That is not a weak signal; it is the absence of one. | — |
| **D535** | — | **`last_failed_wal` does not advance.** Measured: it pinned to `000000010000000000000001` across all three samples while `failed_count` climbed 11 → 15 → 26, because the archiver retries the **oldest** unarchived segment, not the newest. The retry shape is three attempts a second apart, then `WARNING: archiving write-ahead log file … failed too many times, will try again later`. | **`failed_count` is the moving value and the one a proof asserts on.** `last_failed_wal` says *which* segment is stuck — diagnosis, not detection. | A proof asserting `last_failed_wal` advances would be green only when something else was also wrong, and red during exactly the steady-state failure it exists to catch. Written down before anybody writes that assertion. | — |
| **D536** | — | **Two hand-written lists of the same identities, and nothing compared them.** `evidence.ISOLATED_FIELDS` is what the shipped evidence document counts collisions over; `tests/contract/test_render_isolation.py::MUST_DIFFER` is what the isolation test iterates. They are named together in a comment in `output_migrations.py:343` and no test related them. Found by adding `backup.bucket` to both and noticing it could as easily have gone into one. | **A containment test**, added in this run: every pointer in `ISOLATED_FIELDS` must appear in `MUST_DIFFER`, and the surplus is **pinned to an exact list** rather than merely bounded, so it cannot be satisfied by `MUST_DIFFER` growing something unrelated. | D174/D175's shape — a property maintained by review rather than by a test — and it fails in the worse direction: a name dropped from `ISOLATED_FIELDS` leaves the published `collision_count` reporting **zero over a smaller set**, which is indistinguishable from isolation. Containment rather than equality is the true relation here and not a weakened one (cf. D300): `MUST_DIFFER` legitimately covers the slug and four route URLs, which are project-scoped but are not identities two projects could collide *on*. | — |
| **D537** | — | **ADR 0012 and D389 pull in opposite directions, and outputs v13 is the first block to feel it.** ADR 0012 says a rendered document contains no observed value, and the cheapest way to keep that true is for the field to be *unrepresentable* on that branch — which `database` achieves by splitting into `renderedDatabase` and `deployedDatabase`, a settings block duplicated per branch. D389 is the record of what that duplication costs: `storageSettings` was copied per branch, the two disagreed, and `STO-BOUND-001` read the deployed document for a bound that existed only on the rendered one. | **The observation moves out instead of the settings being duplicated.** `backup` is one `$def` referenced from both branches; `backup_state` is a separate top-level block that exists only on the deployed one. Both constraints hold at once and neither is traded away. | The alternative satisfies ADR 0012 by reintroducing exactly the copy D389 was written about. The database pays that cost for historical reasons; a block added today need not, and choosing otherwise would have been a decision made by imitation rather than by reading why the precedent exists. | 0146 |
| **D538** | "Repository encryption enabled with a key stored separately from repository credentials." | **The contract can say a value is generated and rotatable; it has no way to say that rotating it destroys what it protects.** pgBackRest binds the cipher to the repository at `stanza-create`, so writing a new generation of the pass phrase re-encrypts nothing — the repository stays exactly as it was and the *reader* now holds the wrong phrase. Every check here passes, `materialize-secrets` reports success, and every backup ever taken becomes unreadable. | **`one_time_initialization: true` and `rotate_by_replacement: false`**, which is `postgres_init_superuser_password`'s declaration reused for a sharper consequence — there a new generation is *inert*, here it is destructive to readability. **`must_refresh_on_start: false` inverts the two credential halves beside it** and the asymmetry is stated in the file: a revoked API token fails closed at the provider, so refusing the last-known-good start only relocates that error; this value cannot be revoked, so the last known good IS the correct value and failing closed would take a cluster down to protect nothing. | The three flags already existed and D56 already recorded why: they are what lets rotation tooling **refuse to claim a rotation it did not perform**. What Session 10 adds is the first secret where the false claim is not merely misleading — it is the report you would read while the repository became unrecoverable. A test asserts all three, with the two credential halves as its control so it cannot pass because every secret in the file happens to be declared this way. | 0145 |
| **D539** | — | **`postgres` is the first service this repository BUILDS that must not run as 65532.** `test_built_services_run_as_a_fixed_non_root_user` asserted one literal for every built service; the moment `postgres` gained a `build:` block it was swept in, and 65532 is a cluster that cannot read the PGDATA its own image owns. The same edit exposed a second buried assumption: the test also required `read_only: true`, which no PostgreSQL container can satisfy — the entrypoint writes its socket, its PID file and the whole of initdb's output. | **A per-service uid map and a one-member `WRITABLE_ROOT_FILESYSTEM` set**, plus an equality check that the built set and the declared set are the same. **Not** a relaxation to `!= 0`. | Widening to "not root" would accept any uid including a typo'd one — weakening a passing assertion to admit a new case, which is what D300 refuses three times over. Pinning each service is **stricter** than one shared literal: it now fails on a service that starts or stops being built without a decision, which the old form could not see. It caught its own author immediately — `contract-probe` was in the first draft of the map and is not a built service. | 0147 |
| **D540** | — | **`bin/lock-versions.sh --update` is wholesale, so adding one pin adopted three unrelated ones.** Locking the new apt entry re-resolved every image and moved `POSTGRES_IMAGE` (`691673…` → `2ba9ca…`), `PYTHON_RUNTIME_IMAGE` (3.12.13 → 3.12.14, reddening an unrelated test) and `TRAEFIK_IMAGE`. The first is disqualifying: **Run 1 measured pgBackRest's availability, the libssh2 failure and PGDATA against `691673…`**, so adopting the new digest would have left this session's whole first run describing an image the lock no longer names. | **The three are restored to their committed digests**, so Run 4's diff is the apt pin and nothing else. `--check` stays green because it verifies that a digest is present, well formed and paired with the tag `versions.in.yaml` names — it deliberately reaches no registry, so a restored digest is coherent rather than a lie the check cannot see. | D99's third instance, and the first where the drift would have invalidated a measurement rather than merely a version string. Adopting all three is its own run with its own re-measurement — the same rule CLAUDE.md already states for `requirements-dev.in`: *commit it separately*. **Nothing forces this**: `--update` will re-adopt them the next time anyone runs it, and the only thing standing in the way is this row. | — |
| **D541** | "…backups run with a dedicated identity." | **One missing privilege masks the next, and the first arm of rig 5 got the answer wrong because of it.** Granted only `pg_read_all_settings`, `pg_backup_start` and `pg_backup_stop`, a full backup **succeeds** — so an early arm recorded `pg_switch_wal` as unnecessary. It was never reached: `pgbackrest check` failed earlier, on `pg_create_restore_point`, and granting *that* moved the failure to `pg_switch_wal` rather than making `check` pass. | **The privilege set is measured by revoking one at a time**, not by granting until something works. The matrix (arm G): `-pg_switch_wal` check=57 backup=0; `-pg_create_restore_point` check=57 backup=0; `-pg_backup_start` check=0 backup=57; `-pg_backup_stop` check=0 backup=57; `-pg_read_all_settings` check=27 backup=56; all five restored 0/0. **`check` needs two that `backup` does not**, and Run 6 puts `check` in the deploy's step 6c and on both timers. | "The last thing I granted fixed it" is not a measurement of a set — it is a measurement of the first failure. A role provisioned from the backup path alone takes backups for weeks and fails every check, which is the half that is supposed to notice. | 0148 |
| **D542** | — | **`pg_settings` OMITS a restricted row rather than nulling it**, and pgBackRest does not use `SHOW`. Measured: it issues `select setting from pg_catalog.pg_settings where name = 'data_directory'`, and without `pg_read_all_settings` the query returns **four of five rows** — not five with a NULL. Of the five settings it reads, only `data_directory` is restricted; `archive_command`, `archive_mode`, `checkpoint_timeout` and `server_version_num` are readable without the membership. | **Recorded as the acceptable failure it is.** pgBackRest detects the shortfall and names the cause exactly: `unable to select some rows from pg_settings` / `is the pg_read_all_settings role assigned for PostgreSQL >= 10?`, exit 56. Nothing is defended against, because nothing needs to be. | The outcome worth checking for was the other one. D514 says `pg1-path` must be PGDATA and never the mount point; a NULL `data_directory` silently compared against a configured path is that defect arriving from a direction nobody was watching. It does not happen, and now that is written down rather than assumed. | — |
| **D543** | "…health checks that expose failures." | **A backup identity at its connection ceiling reports as a missing database.** Measured, `CONNECTION LIMIT 1` with a `check` overlapping a `backup`: the headline is `ERROR: [027]: no database found` / `HINT: check indexed pg-path/pg-host configurations`, and `FATAL: too many connections for role` appears only as a `WARN` above it. | **Not repaired — the message is pgBackRest's, not this product's. The ceiling is set above the measured concurrency so it is not reached** (ADR 0148), and the string is recorded here so the next reader of a `[027]` does not spend the incident on `pg1-path`. | D518 predicted a fifth claimant would fail in a way that is hard to debug. It is worse than predicted: the error does not mention connections at all, and the one setting it names is the one that is correct. | 0148 |
| **D544** | "Scheduled full and incremental backups." | **pgBackRest takes no lock that prevents a `check` running during a `backup`.** Measured: a `check` launched two seconds into a full backup ran to completion, both exited 0, and a sampler inside the same invocation recorded **2** concurrent backends. A lone command holds **1** — 68 samples, maximum 1. | **`CONNECTION LIMIT 2`, and the budget's fifth summand is 2** (ADR 0148). Two is not a margin: Run 6 puts `check` in the deploy's step 6c and Run 9 puts `backup` on a timer, and a deploy does not consult a timer. | The control is what makes the number honest: the same `check`, at the same ceiling of 1, with no backup running, exits 0 — so the failing arm measured the overlap rather than the ceiling in general (D509's rule, applied before the number was chosen). | 0148 |
| **D545** | — | **`config.ADMINISTRATION_RESERVED_CONNECTIONS = 5` and `postgres-bootstrap.OPERATIONAL_CONNECTION_HEADROOM = 5` are one claim stated twice, in two modules, and nothing compares them.** Both hold connections back "for operations"; both are 5; neither reads the other. Found while deciding D530, which warns about exactly this shape one layer up. | **Not merged in this run, and deliberately.** The new figure does **not** repeat the mistake: `BACKUP_RESERVED_CONNECTIONS` lives in `config` alone and the bootstrap plane imports it, with a test asserting the binding is an attribute of `config` read from the syntax tree. Merging the existing pair is its own change to two passing arithmetics and belongs with an ADR that has measured what each is actually for. | D327 is the record of what two arithmetics over one budget cost: they *"agreed by coincidence, 23 against 20"*, and nothing compared them until Session 7. These two agree by coincidence today at 5 and 5. Writing it down is what stops the next reader assuming somebody checked. | — |
| **D546** | — | **The fifth claimant narrows the application's slack over the pooler's pool from 3 to 1**, and the manifests it will actually meet are unread. Measured through the product's own functions on `project.example.yaml`: manifest 50 → 52 of 56; bootstrap remainder 23 → 21 against a pooler pool of 20. `project.alpha.yaml` and `project.beta.yaml` are gitignored operator inputs that exist only on the host. | **Charged to the application, not to the headroom**, and stated rather than discovered. If either real manifest sets `database.pool_size` within two of its remainder, `connection_limits` raises and the deploy refuses. **That refusal is loud, offline and reachable without root** — `deploy.sh --render-only` — so it is the first thing the trip runs. | Taking the two connections out of `OPERATIONAL_CONNECTION_HEADROOM` instead would have been the invisible way to pay for a backup: the headroom is what leaves a psql available when this arithmetic is wrong, and spending it is spending the diagnosis. | 0148 |
| **D547** | — | **The bootstrap plane's consumer list was hand-written and nothing enumerated it.** `test_the_bootstrap_consumers_match_the_secret_contract` compares three named `*_CONSUMER` globals against `secrets.required.yaml`; a fourth added by any session would simply not be compared, and the failure mode is silent — the file is not found, the credential is reported absent, and the role is left NOLOGIN with no error (D288's exact cost). | **A containment test added in this run**: every `*_CONSUMER` global the module declares must appear in the checked set, derived from the module rather than counted. `len(...) == 4` was refused for D536's reason — it passes while the fourth entry is a duplicate of the third. | Question 5, in a file that already records the last time it was asked here. D536 found the same shape in `ISOLATED_FIELDS`/`MUST_DIFFER` three runs ago; this is the third hand-written list this session has found and the second it has closed. | — |
| **D548** | "…health checks that expose failures." | **`pgbackrest info` exits 0 in every state, including for a stanza that does not exist.** Measured, four phases: no stanza → exit **0**, `status.code` 1, `missing stanza path`; stanza with no backups → exit **0**, code 2, `no valid backups`; one full backup → exit **0**, code 0, `ok`; a stanza never named anywhere → exit **0**, code 1. | **The observer reads `status.code` and never a process's exit**, in one module (`backup_report`), with an AST test asserting nothing in it touches `returncode`. | **D145's shape** — `postgrest --ready` returned 0 while every request 404'd. An observer built the obvious way (run `info`, check it succeeded, report healthy) would report a healthy repository for a stanza that has never existed, on every project, forever. The three states are distinguishable by exactly one field. | 0149 |
| **D549** | "The session configures pgBackRest with … retention rules." | **`stanza-create` is idempotent** — measured, twice in a row exits 0 — and **`expire` applies `repo1-retention-full` from the rendered config with nothing on the command line**, also measured. | Step 6c runs `stanza-create` **unconditionally**, with no probe; `verb_expire` passes pgBackRest the single argument `expire`, asserted on the argument vector rather than on the function's text. | The plan said "create the stanza if absent", which implies a probe; a probe-then-act adds a window in which the answer can change and buys nothing. And a `--retention` flag would be one value stated twice, where the second statement wins and the first is the one people read (D495, D463) — the point being that it was measured **unnecessary** before it was called undesirable. | 0149 |
| **D550** | "Recovery time and latest recoverable time must be recorded as evidence." | **`pgbackrest info` has no latest-recoverable-time field.** Measured: it carries per-backup epoch integers (`timestamp.start`/`stop`) and WAL **segment names** (`archive[].min`/`max`), and a segment name has no time in or beside it. The v13 schema description asserted the value "is read from `pgbackrest info`". | **The newest backup's stop time is published as a proven FLOOR**, and the schema description is corrected in place to say so rather than left asserting something the measurement refutes. Run 8's evidence records the **achieved** recovery point as a separate field. | A drill landing later than this value is the floor being a floor, not a contradiction — WAL archived after the newest backup extends real recovery past it. Written down before anybody reads the two side by side and "fixes" the one that is right. Null was refused for D519's reason inverted: a required field that is always null is published and reaches nothing. | 0149 |
| **D551** | — | **`backup_state.status` had no value for "configured, stanza exists, awaiting its first backup"** — which is the state of **every** project between its first Session 10 deploy and its first operator-run full backup, because the plan puts that backup in an operator's hands at a TTY (Runs 11+). | **`awaiting_first_backup` joins the enum**, extending outputs **v13** rather than opening v14: v13 has never left this tree — both host projects are on v12 — so a document carrying it is one nothing has to migrate. | `ready` is false (nothing can be restored), `failing` would be red on every first deploy (a status operators learn to ignore, the argument `provision-host.sh` already makes for installing timers disabled), and `unconfigured` means a MISSING CREDENTIAL — it would send an operator hunting for a secret that is present and correct. **The third instance of ADR 0053's cost** (D255, D308): a version chosen once from the whole surface, still short a value only measurement surfaced. | 0149 |
| **D552** | — | **The rig measured its own setup failure as a pgBackRest finding.** Rig 6's first run used `docker exec` without `-i`, so stdin was never attached, psql ran **nothing**, `rig_backup` did not exist, and every pgBackRest command failed with `unable to find primary cluster - cannot proceed`. Every step reported an exit code and none of them was about pgBackRest. | **The rig's setup gained a control** — it counts the role in `pg_roles` and aborts fatally if it is absent — before any measurement was taken from it. | CLAUDE.md §1 already names this exact trap (`docker exec` needs `-i`), and it was still paid for. The lesson that is new: **a rig needs a control on its own setup, not only on its subject.** Every arm downstream was ready to report a confident, wrong finding about a third party, and the numbers all looked plausible. | — |
| **D553** | "…health checks that expose failures." | **`failed_count > 0` is unusable as a status, and it is the obvious predicate.** Measured (rig 7 arm G), arm and control in one invocation: healthy baseline `archived_count` 8 → 12 with `failed_count` 11 → 11; broken `archived_count` **frozen at 12** with `failed_count` 11 → **26**; repaired `archived_count` 12 → **21** with `failed_count` still **26**. The healthy, fully-caught-up cluster carries 26 — the counter is cumulative, never resets, and **every project accrues failures in the window between its container starting with `archive_mode=on` and step 6c creating its stanza.** | **The status compares timestamps:** `last_failed_time > last_archived_time`, with never-archived treated as failing. `archiving_is_failing` is refused the counters by an AST test, not only by a comment. | **This REFINES D535 rather than contradicting it.** D535 says `failed_count` is the value that moves while `last_failed_wal` pins to the oldest stuck segment — right **for detecting a change across an interval**, which is what `REC-WAL-001` asserts. A point-in-time status is a different question, and conflating them puts a cumulative counter in a status field that would then read `failing` on every project forever. `archived_count` alone is no better: it freezes, then **catches up** across a repair, so a reader sampling twice sees a healthy-looking increase. | 0150 |
| **D554** | "Break the archive deliberately (a revoked credential arm and a wrong-prefix arm)." | **Only one of the two arms can be run off a host.** The wrong-prefix arm is exact — `repo1-path` pointing where no stanza exists is the same misconfiguration a bad `repository_prefix` produces. The revoked-credential arm is **a stand-in**: rig 7 made the posix repository unwritable, and an `EACCES` from a filesystem is not a `403` from R2. | **Run offline with the substitution STATED**, not silently. What the two share is what the cluster sees — `archive_command` exiting non-zero — and that is the whole of what `pg_stat_archiver` records, which is what this run's mapping consumes. **The real revoked-credential arm needs the host trip** and lands in `REC-WAL-001`. | D267's rule pointed the other way for once: the measurement WAS run, and what needs writing down is precisely what it was a measurement *of*. An arm labelled "revoked credential" that revoked nothing would read as the real thing forever after, and the mechanism is the part a future reader reuses (D531's lesson, in the other direction). | 0150 |
| **D555** | "…the healthcheck goes unhealthy." | **Measured, and the prediction is reversed.** With the archiving predicate as the Postgres healthcheck, `docker compose up --wait` **exits 1** — "container … is unhealthy" — while the container is `running`, `RestartCount` **0**, and the database **answers queries**. The control, the same broken archiver behind `pg_isready`, exits **0**. And **three services gate on `postgres: condition: service_healthy`**: the pooler, the auth service and storage. | **The archiving signal does NOT go in the Postgres healthcheck.** It reaches an operator through the deployed document (`backup_state.status: failing` with both counters), `bin/backup.sh check`'s non-zero exit, and step 6c failing the deploy with a named reason. A test asserts the healthcheck is still `pg_isready` **and** that the gating this rests on is real. | An archiving predicate there converts a recoverability incident into an availability one — a backup problem stopping the application from starting, on a cluster that is serving. **And it blocks its own repair:** a broken archiver is fixed by deploying, and a deploy that cannot get past `compose up --wait` cannot deliver the fix. The failure also names nothing: "container is unhealthy" against step 6c's *"WAL archiving does not work for this project… this is the archiver"*. | 0150 |
| **D556** | — | **A red healthcheck costs nothing at the container level**, which is the half that made the question look cheap. Measured (arm F): unhealthy after ~15s, `status=running`, `RestartCount=0`, and the database answered a query while unhealthy. Nothing restarts it, nothing stops it. | **Recorded, because it is the argument FOR the rejected option** and it is a real one. The cost is entirely in what reads the health — `--wait` and `depends_on` — and both are exactly what must not see it. | A decision is only safe to inherit if the strongest case for the alternative is written beside it. Whoever revisits this will find the healthcheck harmless in isolation and should not have to rediscover that the harm is in the two consumers. | 0150 |
| **D557** | — | **`pg_switch_wal()` on an idle cluster archives nothing**, and a rig that churns without writing measures its own inactivity. Rig 7's arm F called it five times against a quiet cluster: `archived_count` and `failed_count` were **byte-identical before and after**, and the arm reported the predicate as `ok` in a state it had failed to break. | **The churn writes first**, and the rig **asserts its counters moved** before drawing any conclusion — a fatal check, like the setup control D552 added. | The second rig-defect-as-finding in two runs, and the more dangerous shape: D552's rig failed loudly (`unable to find primary cluster`), this one produced a **plausible, quiet, wrong answer** — "the predicate says ok" — in an arm whose whole purpose was to see it say failing. **An arm hoping for "no change" cannot distinguish success from having done nothing**, so it needs a control proving it did something. | — |
| **D558** | "pgBackRest repository using an S3-compatible R2 endpoint", and §12's whole archiving story. | **NOTHING SUPPLIES pgBackRest ITS CREDENTIALS AT RUNTIME.** `build_pgbackrest_conf` omits `repo1-s3-key`, `repo1-s3-key-secret` and `repo1-cipher-pass` by construction and its docstring says pgBackRest "reads them from the environment" — and no environment variable, `conf.d` include or entrypoint wrapper puts them there. `compose.yaml`'s `postgres` service defines four variables, none of them pgBackRest's; `runtime_override` adds **no** `environment` key to that service at all. The three secrets are materialized and mounted at `/run/secrets/...` and nothing reads them. Measured with a control (rig 8, arm 0): `PGBACKREST_REPO1_CIPHER_PASS` in the environment makes `repo-ls` exit **0** against an encrypted repository; the same command without it exits **37**, `[037]: repo-ls command requires option: repo1-cipher-pass`. There is **no** `repo-cipher-pass-file`, `repo-s3-key-file` or `repo-s3-key-secret-file` option — pgBackRest 2.59.1's only `-file` options are for TLS and SSH material — and `config-include-path` defaults to `/etc/pgbackrest/conf.d`, which nothing in this repository writes to. | **Recorded, not repaired in Run 8.** The fix is an entrypoint wrapper in `services/postgres/` reading `/run/secrets/*` and exporting the three variables before exec'ing the base entrypoint, or a `conf.d` file materialized through a new `format:` in `secrets.required.yaml`. Either is an image or contract change with an ADR of its own, and it is Run 4's territory reopened rather than Run 8's. **Run 8 is built so the fix needs no change here**: the drill inherits the whole `PGBACKREST_*` namespace from the running database container, so whichever route the repair takes, one fix serves the archiver and the drill. | This is the largest thing Session 10 has found and it was found by trying to *use* the archiver rather than by reading it. **Step 6c runs `pgbackrest check` and a check failure fails the deploy**, so the first deploy of the first project on the host would have failed there — loudly, which is the design working, but after a trip had been paid for. Nothing offline could have caught it: every Run 4–7 rig supplied its own credential to its own containers, which is exactly the shape ADR 0065/0066 warns about — *a proof that reaches the right end state by a route the product does not take proves the end state is reachable, not that the product reaches it.* | needed |
| **D559** | — | **A successful `pgbackrest restore` prints ZERO BYTES on both streams at the log level this repository renders.** `build_pgbackrest_conf` writes `log-level-console=warn`; measured, a restore that exits 0 emits 0 bytes on stdout and 0 on stderr at `warn`, and six lines at `info` — the second of which is the only place the selected backup set is named. | `bin/restore-test.py` passes `--log-level-console=info` **on its own command line**, overriding the rendered value for its invocation only, and a restore whose output does not name a backup set **fails the drill** rather than publishing a null. | D145's shape again, one layer over: a command that succeeded and said nothing, where the obvious reading of "no output" is "nothing happened". A drill that parsed the rendered-level output would have published an empty backup set on **every drill that worked**, and an empty field is indistinguishable from one nobody filled in. This is the only place in the repository where a rendered configuration value is overridden on a command line. | 0152 |
| **D560** | — | `BACKUP_CREDENTIAL_NAMES` was declared in `bin/deploy-project.py` in Run 6, when the deploy was its only reader. | **Moved to `config.py`; the deploy imports it.** The restore drill is the second reader — it needs the same three names to decide which of the database container's mounts to carry forward. | D264: two tuples over one list agree until one of them is edited, and the one nobody re-reads is the one that is wrong. A re-export keeps the readers that already name it through `deploy-project`. | — |
| **D561** | — | `secrets_contract.active_secrets(contract, session)` filters by `introduced_in_session`, and the three backup secrets are session **10** while `CURRENT_SESSION` is **9** until Run 10. A drill filtering that way looks for **nothing at all** and inherits nothing. | **`required_container_paths` does not filter by session.** `active_secrets` answers "what would a deploy through session N materialize" — a question about a *deploy*. The drill asks about a *container that is already running*, and the authority on whether the material is there is `inherited_mounts`, reading the container. | Caught by the run's own end-to-end rig on its first execution, which is the argument for the rig: the pure-logic tests passed session 10 explicitly and were green while the command inherited nothing. A session filter in a command that reads a running container is a filter answering a different question than the one asked. | — |
| **D562** | "Recovery time and latest recoverable time must be recorded as evidence." | **The achieved recovery point has no obvious catalog source, and the obvious one is wrong.** Measured, every candidate in one invocation: `pg_last_xact_replay_timestamp()` = `10:45:00.109084+00` (correct, and agreeing to the microsecond with the server log's *last completed transaction was at log time*); `pg_control_checkpoint().checkpoint_time` = `10:45:14+00` — the **end-of-recovery checkpoint, fourteen seconds late**; the log's *recovery stopping before commit of transaction 757, time* = `10:45:04.774492+00`, which is the first transaction **not** applied; `pg_last_committed_xact()` empty, because `track_commit_timestamp` is off. | **`pg_last_xact_replay_timestamp()` for the time, `pg_last_wal_replay_lsn()` for the LSN**, both read off the restored instance. The requested target is read back from `current_setting('recovery_target_time')` rather than echoed from the command line. | `checkpoint_time` is this project's defect pattern in its purest form — a real timestamp, from a catalog function, on the right instance, that has nothing to do with where recovery landed and would drift further the slower the machine. **The control is free and exact**: both functions return **NULL** on the live cluster, which never recovered, so a drill that read the wrong instance publishes an empty field rather than a plausible one. | 0152 |
| **D563** | — | **The achieved recovery point and the published floor arrive in two different spellings of one instant, and compared as strings they sort backwards.** `pgbackrest info` reaches the verdict through `backup_report._timestamp` as `2026-08-25T10:42:29Z`; PostgreSQL reaches it through psql as `2026-08-25 10:45:00.109084+00`. A space is `0x20` and `T` is `0x54`, so the *later* instant compares *smaller* whenever the dates agree. | **`restore_drill.instant` parses both before comparing**, and raises on a third spelling rather than degrading to "unknown". A regression test asserts the premise — that the two spellings still sort wrongly as strings — so the test cannot quietly stop measuring anything. | Found by the run's own subject arm, which is what a subject arm is for. Left as written it would have failed **every correct drill** with a sentence about an inconsistency that was the comparison's own — and the sentence would have read like a real finding about the repository. `backup_report.archiving_is_failing` compares timestamps as strings legitimately, because both of its come from one `psql` call in one format; that is the distinction, and it is not visible from either call site. | 0152 |
| **D564** | "…never overwrites the active database volume." | **pgBackRest already refuses to, and the refusal has a number.** Measured: restore into an empty volume exits **0**; the same restore into the volume it just populated exits **40**. A target earlier than every backup set exits **75** — `[075]: unable to find backup set with stop time less than '<target>'` — **before anything is written**. A target in the *future* exits **0** and produces an instance that never promotes: `FATAL: recovery ended before configured recovery target was reached`, no connections accepted. | **`--delta` is never on the argument vector**, and `assert_disposable` refuses a plan carrying it. The drill distinguishes **promoted**, **still recovering** and **dead** and never collapses them; only the first is a successful drill. | The exit-40 refusal is the outer guard — the one that holds if every derivation in the command is wrong at once — and `--delta` is the single argument that disarms it, which is why refusing the flag is worth more than any assertion about names. And a restore exiting 0 having landed nowhere is D145/D548 a **third** time, in a third third-party command: the state was never in the exit code. | 0151 |
| **D565** | "…the disposable target is created by the command and removed by a `trap`." | **Docker's own verbs cannot tell absence from success.** Measured (rig 8, arm J): `docker volume create` on a name that already exists exits **0** and keeps the existing volume *and its labels*; `--mount type=volume` **creates** a volume that is not there; `docker volume rm -f` and `docker rm -f` exit **0** for a name that does not exist, while the unforced forms exit 1. | The pre-flight is `docker volume inspect`, **never** the exit code of a create. The teardown uses `rm` **without `-f`**, so "already gone" is distinguishable from "removed". The shell `trap` removes only what the Python side recorded in its state file, and **refuses** to remove anything matching the `live_volume` recorded in that same file. | §4.5 requires that a teardown which cannot find its target exits non-zero rather than widening its search — and a teardown runs at the moment when widening it looks like helpfulness. `-f` is the flag that makes a teardown always look successful. | 0151 |
| **D566** | — | **A restore inherits the live cluster's `system_identifier`.** Measured: `7677917767700738081` on both the live cluster and its promoted restore. `timeline_id` is what differs — 1 against 2. Separately: `apg.project.key` is spelled as a module constant in **five** `bin/` commands. | **`REC-SAFE-001`'s host arm must not use `system_identifier` to prove the live cluster is untouched**, and `drill_verdict` reads `timeline_id` instead. The five-way label duplication is **recorded, not repaired** — consolidating it touches five operator commands and none of them is this run's subject. | A restore *is* the same cluster at an earlier moment, so the identifier is the one field guaranteed to agree. A host proof reading it would pass **while reading the drill instance**, which is the single mistake `REC-SAFE-001` is most able to make and the one it exists to prevent. | 0151 |
| **D567** | — | **The per-derivation `context` is not what keeps the drill's names apart from the live volume — the stem is.** ADR 0151's first draft said it was, borrowing `backup_bucket_name`'s argument (ADR 0145). Battery arm Q7 changed the drill volume's context to `compose_volume_postgres`, the live volume's own, and **nothing went red**: `truncate` fingerprints `(context, value)`, and these values already differ, so the fingerprints differ whatever the contexts are. | **The ADR is corrected rather than the mutation discarded**, and the names gain `-pg` and `-pgbackrest` suffixes — without them the drill volume and the drill container are the **same string** for a short key and different strings for a long one. Q7 is replaced by a mutation that collides the stems, and Q11 added for the suffix; both are killed. | ADR 0145's argument is sound *for a pair that can share a stem*, which `apg-<key>` and `apg-<key>-backup` genuinely can once truncated. Reusing it here produced a sentence that sounded measured and was not — §6's whole subject — and a **survivor is what turned it back into a measurement**. The suffixes matter for D374's reason: an identity that is equal for short keys and unequal for long ones lets a test pass for a reason it does not state. | 0151 |
| **D568** | — | **The credential route exists, and it is `config-include-path`.** Measured (rig 9), every arm with a control: a `.conf` under `/etc/pgbackrest/conf.d` supplying `repo1-cipher-pass` makes `repo-ls` exit **0** against an encrypted repository, against **37** with no include mounted. **Three files, each carrying its own `[global]` header, concatenate cleanly** (exit 0) — which is what lets the contract keep materializing one value per file. A file with no section header is **29**; an option set in both the include and the rendered config is **31**, `cannot be set multiple times`; a partial set is **37** naming the one that is missing; a `0400` file owned by root under a container running as 999 is **41**. | **The `conf.d` route, not the environment.** `secrets_contract` gains a third `format: pgbackrest` writing `[global]` and one `option=value` line, the consumer names its `option`, and `container_secret_path` mounts it where pgBackRest reads its includes. | The environment works (rig 8 arm 0) and is refused for three reasons: it needs an **image change** — `services/postgres/Dockerfile` says "No USER line, no ENTRYPOINT, no CMD" and ADR 0144 built that image to add a binary and nothing else — it puts the value in `/proc/<pid>/environ` for every process in the container, and it goes around per-consumer materialization, which is what makes ADR 0145's isolation a filesystem property. | 0153 |
| **D569** | — | **A pgBackRest config file with no section header prints the value.** Measured, K3 and again on the product's own bytes (L2): `[029]: key/value found outside of section at line 1: repo1-cipher-pass=<THE VALUE>`, on the console and in the log — and for `archive-push` that log is the postmaster's stderr in the container. | `render_secret` **refuses a value containing a line break** (a newline ends the `key=value` line and leaves the remainder as exactly such a key), `recover_secret` **verifies the header and the option name** before returning anything, and neither refusal quotes the line or the value. | The same pair `pgpass` already carries, for a worse reason: pgpass's newline makes a malformed second entry, and this one makes a **log line containing a credential**. It is not closed — nothing validates the file at the mount point, and pgBackRest quoting the line is not ours to change — so the residual is written into ADR 0153's consequences rather than implied by the guards. | 0153 |
| **D570** | — | **`pgbackrest info` was never the problem; the grant surface had two spellings of one fact.** `build_secret_override` emitted `target: <target_file>`, a bare basename Compose resolves under `/run/secrets`, and `container_secret_path` said the same thing separately. | `build_secret_override` emits `container_secret_path(consumer)` for **every** consumer, and that function is the one place that decides. Measured (K8) with a control: Compose accepts an **absolute** target and the file lands exactly there; a relative one lands in `/run/secrets`, as documented. | D264, found while making the two disagree on purpose. Two passing tests in `test_secret_override.py` are replaced by stricter ones — one of them had `f"{CONTAINER_SECRET_DIR}/{target}".startswith(CONTAINER_SECRET_DIR)`, which is true of **any** string and measured nothing. | 0153 |
| **D571** | — | **Compose ignores a secret grant's `uid`, `gid` and `mode`.** Measured (K8): `level=warning msg="secrets 'uid', 'gid' and 'mode' are not supported, they will be ignored"`, and the **host file's** ownership and mode pass through unchanged. | **Nothing changes, and that is the finding.** The contract's `uid: 999, gid: 999, mode: "0400"` are applied by `materialize-secrets` **on the host**, which is what has always protected the file; the grant surface never did. Recorded so that a future reader does not delete the contract fields as redundant with a grant that ignores them. | The design was already relying on the right thing without saying so, which is the pleasant version of this project's defect pattern rather than the usual one. K7 is what a failure of it looks like: exit 41, loudly, at the first read (D515). | 0153 |
| **D572** | — | **A rig defect that reported "no leak" having done nothing.** Arm L2 passed its conf.d path through an environment variable on a `wsl bash -lc` command line, and **Git Bash path-converted it** to `C:/Users/gmpar/AppData/Local/Temp/rig9/…`. The Python found no directory, stripped no header, and the arm probed the **unmodified** files — reporting exit 0 and *"the value did NOT appear"*. | The arm **asserts its own stimulus landed** — the file's checksum must change and the header must be gone, both fatal — before it probes anything. | **D557 for the third time this session, and the worst instance**: a *leak check* that came back clean after doing nothing. CLAUDE.md §1 already names Git Bash's mangling of `$?` and of nested quoting; **it does not name path conversion of an argument that looks like a POSIX path**, and that is the new half. An arm hoping to see "no leak" cannot distinguish success from having done nothing any more than an arm hoping to see "no change" can. | — |
| **D573** | — | **A test comparing two constants survived a mutation, for the second time in one session.** Battery arm R7 moved `PGBACKREST_INCLUDE_DIR` to `/etc/pgbackrest/includes` and nothing went red, because every assertion derived its expectation from that same constant. Q5 was the first instance, on `RESTORE_LOG_LEVEL`. | Both are asserted as **literals** now, each with a docstring saying why the literal is written out: `/etc/pgbackrest/conf.d` is pgBackRest's own measured default (`pgbackrest help backup config-include-path`), and `info` is the level at which a successful restore is not silent. | CLAUDE.md §6 names this defect and it still arrived twice in one session, in code written by someone who had just read the list. The general rule that follows: **when a constant encodes a MEASURED third-party fact, the test writes the measured value, not the constant.** A constant that encodes a free choice may be compared to itself; one that encodes a measurement may not. | — |
| **D574** | — | **The `option` validation was correct and untested.** Battery arm R6 deleted the "a pgbackrest consumer must name an option" check and **survived**: the real contract always names one, so nothing ever drove the refusal. | Two tests, both directions — a `pgbackrest` consumer without `option` is refused, and a `raw` consumer carrying one is refused. | Question 2 of §6's five: *has it run at all, in this environment, since the thing it measures last changed?* The answer was no, and the battery is the only thing in this repository that asks it. Without the check a deploy raises `KeyError` inside the materializer, on the host, as root. | — |

| **D575** | "The restored instance passes schema, RLS read, and write-RPC checks." | **Two of the six smoke checks need an owner id the command cannot discover**, and a check with nothing to do that reports `passed: true` is this repository's defect pattern with an evidence document as its reader. | **Every check carries `applicable`.** `--smoke-owner-id` is optional; without it the RLS read and the write RPC are recorded `applicable: false, passed: null`, `drill_verdict` treats them as neither pass nor failure, and **`REC-SMOKE-001` asserts `applicable` as well as `passed`** — so a drill run without the flag cannot satisfy the requirement by producing a document with fewer checks in it. | The alternative was for the command to discover an owner from the restored data, which proves "some owner's rows and only those" and cannot be tied to the T1/T2 scenario the requirement is about. The RLS half that matters is the **second** read: *the owner sees rows* passes against a table whose policies were dropped, and *nobody else sees them* does not — so both run, as `app_runtime`, because FORCE RLS exempts a superuser and the same SELECT as `postgres` returns every row (ADR 0065/0066). | — |
| **D576** | "Scheduled full and incremental backups." | The four units need to reach `bin/backup.sh` inside a *release*, and a host-side unit naming a path into a release is D72 — a copy on the host still held a literal three runs after it was fixed here. | **The timers use the seam that already exists.** `agentic-postgres-project@.service`'s trampoline validates `%i` against the project-key pattern and **passes the action through unexamined**, because which actions exist is a property of a release; `libexec/project-launcher` gains `backup-full` and `backup-incr`. No new trampoline, and the units name no path inside any release. **The scheduled action runs `check` before `backup`**, and a test asserts that order. | The trampoline's own comment is the argument: *"a list here would be a second definition of it — the kind that agrees right up until a release adds one."* This run is that release adding one. `check` first, because it is the only thing in this system that tests the archiver end to end and it needs two privileges the backup does not (D541) — so a timer that backs up and fails its check is the expected shape, and it is the half that is supposed to notice. | — |
| **D577** | — | **A test that reads a shell script by regex read the wrong loop.** `provision-host.sh` has more than one `for origin in …; do`; an earlier one installs `libexec/agentic-postgres-*`. `test_install_units_globs_timers_as_well_as_services` searched the whole file, matched that one, and reported that `install_units` globs no units at all — on a repository where it had just been fixed. Separately, `configparser` interpolates `%`, so every `Unit=…@%i.service` parsed to a mangled value. | The glob search is scoped to `install_units`' own body and fails loudly if that function cannot be found; the unit parser is `interpolation=None`. | Both were caught by the module's **first** run, which is the only reason they are a divergence row and not a defect that shipped. The first is D464's shape once more — a text scan standing in for a construct — and the mitigation that worked was not "stop scanning" but *name the subject precisely and fail if it cannot be found*. | — |
| **D578** | — | `REC-SAFE-001` pointed at one node id, and D523 requires **two proofs**. | **Five node ids, across two modules**: the host arm and the teardown check in `tests/recovery/`, and the offline rig's three arms — including the control arm — in `tests/contract/test_restore_test_command.py`. `REC-SMOKE-001` likewise gains its offline arm. | Registering only the host half would leave the arm that has **actually executed** invisible to the evidence, on a requirement whose host half has never run. It also makes D523's "two proofs" a fact the registry states rather than a sentence in a plan. | — |
| **D579** | — | **The five recovery proofs have never executed and cannot until a deploy.** The host is at `c0816e7`, Session 9's release; Session 10 has never been deployed and R2 has never been dialled. | **`CURRENT_SESSION` stays 9.** The placeholders are replaced in this run and the bump is **not** taken with them: the plan assigns `bin/session-10-check.sh` and the operator guide to Run 10, and a tree declaring session 10 without its gate script is a tree whose gate cannot run. Verified rather than argued — with the gate session at 9, `test_no_requirement_at_or_before_the_gate_session_remains_future` does not reach a requirement targeted at 10, and the registry module is green. | CLAUDE.md says the bump moves *together with* the five replacements in one commit (D439/D484), and the constraint that rule encodes is one-directional: **the bump requires the replacements, not the reverse.** Bumping without them goes red; replacing without bumping does not. Recorded rather than resolved silently, because the next reader will find the two sentences and need to know which way round they bind. | — |

| **D580** | — | **`docs/acceptance-matrix.md` said "placeholders owned by Session 2" beside thirteen shipped, passing requirements** — and the same for Sessions 3 through 9. D526 predicted this from reading `bin/render-acceptance-matrix.py:96`; what it did not say is that the document had **already** been wrong for nine sessions, because `status = "active" if session == 1` was written when 1 was the only shipped session and never revisited. | **The generator learns the gate session.** `acceptance_session()` moves from `tests/conftest.py` into `agentic_postgres`, `tests/conftest.py` wraps it to raise pytest's own error type, and the generator imports it. Every session at or before the gate now reads `active`. | A generated document asserting the opposite of the tree is the drift the generator exists to prevent, which makes this the generator failing at its own job — in a file whose header says *"GENERATED FILE. Do not hand-edit."* and which therefore nobody reads closely. Two implementations of the gate-session rule would have been D264 one layer up, so the derivation moved rather than being copied into `bin/`. | — |
| **D581** | — | **`bin/session-09-check.sh`'s `--help` documents the exact command an operator pastes**, including `--session 9` and three evidence paths. A derived Session 10 gate that changed only `readonly SESSION=10` would leave all four wrong. | The derivation is a **script of named substitutions** over a copy, and the operator-facing text — the mode descriptions, the merge command, the precondition prose, the "before host mode" sequence — is a second explicit pass. What is *not* named stays Session 9's byte for byte: the bundle name, `git rev-parse FETCH_HEAD` before the checkout, the venv sync, `op@`. | D213 is the record of thirteen secret proofs gated on a flag that was not passed once all session, and the flag was missing from the documented invocation. D505 and D507 are two flags lost to retyping. **A copy plus named substitutions is what "derived by diff" has to mean for a file whose value is in its details** — 321 of 874 lines changed, and four remaining "Session 9" references are all deliberate. | — |
| **D582** | "Scheduled full and incremental backups… health checks that expose failures." | Session 9's gate had a precondition — the migration ledger — and **Session 10 has no migration to check**. Run 5 measured that every privilege an online backup wants is refused to a NOSUPERUSER object owner, so all five grants are bootstrap-plane. | **The precondition becomes the repository's own readiness**: the stanza exists, a full backup exists, and the archiver is not failing — all three from one `pgbackrest info` plus one `pg_stat_archiver` read per project, through `backup_report.backup_state`, which is the same function the deploy publishes from. **Nothing reads `pgbackrest info`'s exit code** (D548). | Without it, four requirements fail on one missing thing and an operator reads four tracebacks to learn it — which is precisely what Session 9's `check_agent_plane_is_published` exists to prevent, one session earlier. The second condition is the one an operator trips over, and it is deliberate: the first full backup is a command at a TTY because it is the first operation that writes a meaningful amount to a repository nobody has paid for yet. | — |
| **D583** | — | **`CURRENT_SESSION` arms no new Compose profile this session**, which every previous bump did. Session 6, 7 and 9's guides each had to say which container would now start. | Stated as an absence rather than omitted: the archiver lives in the existing `session3` postgres service and the backup network is attached unconditionally. **What the bump does arm is the deploy's step 6c**, which creates a stanza and runs `pgbackrest check` — and a check failure fails the deploy. | An operator reading four consecutive guides that each name a new container, and then one that names none, is entitled to wonder what failed to start. The container that does not appear must not be mistaken for one that did not come up (D488's shape, inverted). The real consequence is that **a deploy from here on needs three provider secrets and an out-of-band bucket**, which is a larger prerequisite than any profile ever was. | — |

| **D584** | — | **The gate ran the gate.** Run 8's `test_no_command_reports_an_unavailable_capability` invokes every command in `SHELL_COMMANDS` with **no arguments**, and `bin/smoke-test.sh` with no arguments runs `pytest -q -m "contract and not future"` — which is the contract suite this module is part of. So every gate run started a nested contract suite, whose own `test_cli_contract` started another. Measured: `tests/contract/test_cli_contract.py` alone exceeded **590 seconds** where it had taken seconds, and the full suite reached 22% in fifteen minutes. Two other commands do work bare (`session-01-check.sh` 4.0s, `doctor.sh` and `apg-diag.sh` report and exit 0); every one of the other thirty-six returns in under 0.5s. | **An allowlist of four commands that RUN rather than refuse**, named individually with the reason, excluded from the sweep — and a second test asserting each is still in `SHELL_COMMANDS`, still driven by every other check, and still refuses an unknown flag with a non-zero, non-10 code. **294 tests in 3 seconds.** | **The measurement Run 8 did not make was of its own method.** The test's *assertion* was measured — the bare exit codes were recorded before it was written — and its *cost* was not, which is §6's pattern pointed at a test rather than at a product value. Excluding the four is not a weakening: a command that runs has not reported an unavailable capability, so there was never an exit 10 to find. **A timeout was refused as the fix**: it would have capped the damage while leaving a nested pytest started and killed on every gate run, which is a slow test whose slowness nobody could explain. The module's silence also hid two Run 8/10 omissions — `bin/restore-test.py` and `bin/session-10-check.sh` were in neither command list, so **no check in that module applied to either**, including the secret-argument scan; both surfaced in the first run that finished. | — |

| **D585** | "The session configures pgBackRest with encrypted R2 storage…" | **Both real manifests carry `backup: enabled: false`**, which is `BACKUP_DEFAULTS`' correct default and means the four host renders at the start of Run 11 **did not exercise the backup plane at all**. The first reading of those renders looked like D546 closing; it was four projects rendering with the feature off. `docs/session-10-operator-guide.md` §4 told an operator to create a bucket and paste a token and **never told them to enable it**. | The guide gains two explicit steps: turn `backup.enabled` on with `bucket` and `account_id` in each real manifest, then re-render and read `.backup` back. **`account_id` must be QUOTED** — measured: unquoted, a leading-zero id parses as an integer and `project.schema.json` refuses it with *"0 is not of type 'string', 'null'"*. | A step that is missing from a guide fails *quietly*: with `enabled: false` the deploy converges, publishes no repository, and the gate then refuses with *"backups are not enabled"* — the right message, two steps later than it needed to arrive. **And it nearly produced a false measurement**: "all four render, exit 0" is exactly what D546 closing would look like, and it was four renders of a disabled feature. **D546 is now closed for real** — alpha's own manifest, copied under a slug of its own with backups ON, renders at exit 0 at schema v13 with `max_connections` 56 against a pooler pool of 20 — and the probe removed what it published, because the gate compares every rendered project for identity collisions. | — |

| **D586** | — | **`secret-generation.schema.json` is a SECOND schema over `format` and `target_file`, and it disagreed with the contract schema on both.** Run 8b added `format: pgbackrest` to `secret-contract.schema.json` and to `secrets.required.yaml`; the gate went green at 4010 passing. The first Session 10 deploy died at **step 5**, after installing the release, with `secrets/13/consumers/0/format: 'pgbackrest' is not one of ['raw', 'pgpass']` and `target_file: '10-repo1-s3-key.conf' does not match '^[a-z][a-z0-9_.-]{0,63}$'`. **Two findings, and only the first is Run 8b's**: the target_file patterns had disagreed since long before Session 10 — the contract allows letter-or-digit, the generation schema allowed letter only — and nothing had exercised the gap because every target file until now began with a letter. | The generation schema takes **the contract's own values** for both, because the contract is the authority on what a consumer may *declare* and a generation document only records what was *materialized* — so it must accept everything the contract accepts. `tests/contract/test_secret_generation_manifest.py` then asserts the two schemas agree on both fields, and **builds a generation manifest from the shipped `secrets.required.yaml` for every session 2–10 and validates it**. | **The proof was unreachable offline, which is §6's question 2** — *has it run at all, in this environment, since the thing it measures last changed?* `validate_manifest` was called only from inside a real materialization, which needs a provider, so no offline test ever built a manifest from the real contract. 4010 gate tests passed over a tree that could not be deployed. The new module is the missing proof rather than a patch: a future `format`, a future `target_file` and a future session are all covered, and the two-schema drift cannot recur silently. **The deploy failed in the right place** — before the image build, before any container moved, naming both problems at once. | — |

| **D587** | — | **The database container selector matched nothing, and never could.** `bin/backup.py` selected the cluster with `label=apg.project.key=<key>` from Run 6 and `bin/restore-test.py` copied it in Run 8. That label is applied by `compose.yaml` to **six edge-facing services** — `edge-probe`, `postgrest`, `docs`, `auth`, `storage`, `mcp` — and to **none** of `postgres`, `pgbouncer` or `dbmate`. Measured on the host in one invocation: `apg.project.key=alpha-dev` + `service=postgres` returns **0** containers on a healthy cluster; `com.docker.compose.project=apg-alpha-dev` + `service=postgres` returns **1**. Step 6c failed with the selector's own message, which names both possibilities and was right about the first one. | **One authority**: `runtime_override.database_container_filters(compose_project_name)`, used by both commands, filtering on Compose's own pair. The project name is read from `outputs.json`'s `compose.project_name` — `naming` derives it, the document publishes it, and nothing re-derives it (ADR 0002, D55). | **This is not D293 returning**: that was `com.docker.compose.project.working_dir`, a PATH into a release directory that changes every release; this is the project NAME. What makes D587 its own row is that the selector was **unexecutable from the day it was written** and five runs of green gates said nothing, because step 6c had never run against a deployment — §6's question 2 and question 3 in one defect. D566 had already recorded `apg.project.key` being spelled in five `bin/` commands and left it alone as cosmetic; **two of those five were selecting a database container and both were wrong**. `tests/contract/test_container_selectors.py` is the general repair: for every first-party label a selector uses, the service it selects must declare it in the **resolved** Compose model — with both halves asserted, so it cannot pass if the label vanishes entirely. | — |

| **D588** | — | **The rendered `pgbackrest.conf` was `0600` root-owned, and the archiver runs as 999.** `render_project` wrote it with `write_private` like every other file under `.generated/<key>/`. Step 6c failed with pgBackRest's own `[041]: unable to open file '/etc/pgbackrest/pgbackrest.conf' for read: [13] Permission denied`. | **`PGBACKREST_CONF_MODE = 0o444`**, and a `write_readable(path, mode, payload)` whose mode is a **required argument** — the defect class is a file whose mode nobody stated. | **The reasoning already existed in the same file, twice.** `MIGRATION_FILE_MODE = 0o644` ("the one generated artifact a *container* reads … a 0600 file bind-mounted into a non-root container is a migration run that fails with permission denied, which is a long way from where the mode was set") and `SNAPSHOT_MODE = 0o444` ("the only rendered file that is"). Run 4 added a third artefact of exactly that category and gave it `write_private`. **Rig 9's arm K7 measured this exit code deliberately** — a root-owned `0400` under a container running as 999 — and nothing connected it to the rendered config, because every rig supplied its own. `SNAPSHOT_MODE`'s "the only rendered file that is" is deleted rather than qualified. Two tests: the config's mode and the absence of a credential in it asserted **together**, since widening a file that carried one is the same edit with the opposite meaning; and the general form over the three artefacts a container reads, with `outputs.json` as a control that must stay private. | — |

| **D589** | — | **`install_rendered` was a second authority over every rendered file's mode, and it won.** It copied the rendered directory into `/var/lib/agentic-postgres/rendered/<key>/` and then re-imposed `0600` on everything except the migration set. So D588's repair did nothing: the archiver's config was rendered `0444` and **installed `0600`**, and the second deploy failed with the identical `[041]` — because the render was never what the container read. | **The render decides the mode; the installer decides the owner.** `shutil.copytree` already preserves modes through `copy2`, so the loop keeps only its `os.chown`. `_is_migration_artifact` had no caller left and is deleted rather than kept as a helper nothing reaches. | **Two deploys were spent on one defect because the first repair was made at the wrong layer** — the visible symptom was a mode, and the mode had two owners. `rendering.py` had already taken this decision three times (`FILE_MODE`, `MIGRATION_FILE_MODE`, `SNAPSHOT_MODE`) with three separate paragraphs of reasoning, and the installer overrode all three with one line and a narrow exemption. **The latent half is worse than the reported one**: the OpenAPI snapshots are rendered `0444` for exactly this reason and were being installed `0600` too, and nothing reported it because the docs container's healthcheck does not read its snapshot. `tests/contract/test_install_rendered_modes.py` asserts the property **over the whole tree** rather than per file — naming the files is how the third category was missed — with `outputs.json` and the runtime override as controls that must stay private, and `os.chown` patched out so the test does not require the root it would then only run under. | — |

| **D590** | "pgBackRest repository using an S3-compatible R2 endpoint." | **The derived image has no CA trust store, so it cannot verify R2's certificate.** Step 6c reached R2 — DNS resolved, TCP connected to `172.64.190.1:443` — and refused: `[095]: unable to verify certificate presented by '<account>.r2.cloudflarestorage.com:443': [20] unable to get local issuer certificate`. Measured: `ca-certificates` is **NOT INSTALLED** in the base image, `/etc/ssl/certs/ca-certificates.crt` is absent, and the package is in **neither pgbackrest's Depends nor its Recommends** — so `--no-install-recommends` is innocent and nothing would ever have pulled it in. | `ca-certificates` pinned through the apt registry and installed in the **same layer**, with `test -s /etc/ssl/certs/ca-certificates.crt` proving the bundle exists rather than trusting the postinst. Two things had to be learned to lock it: the version lives in **`bookworm-security`**, not `bookworm` (the lock refused the first index — D201 working), and that archive serves **`Packages.xz`** where pgdg serves `.gz`, so the resolver now sniffs magic bytes rather than trusting a filename. | **No rig could have caught this, and the reason is the same one three times this trip: every rig used a POSIX repository on a local volume, so nothing ever negotiated TLS.** ADR 0065/0066 — a proof that reaches the right end state by a route the product does not take. The verification arm is a real dial of the real endpoint with **two controls**, and the first attempt's control was broken in D509's exact shape: removing only `ca-certificates.crt` still verified OK, because OpenSSL also reads the hashed symlinks the same package installs. Subject `0 (ok)`; trust directory removed `20`; **the unpatched image `20`, which reproduces the host failure exactly**. A pinned trust store is a stale trust store, and a *security-suite* pin expires faster than pgdg's (D533) — accepted, written down, diarised by nobody. | — |
| **D591** | — | **A deploy does not recreate a container whose bind-mounted file changed, so the container keeps reading a DELETED inode.** `install_rendered` ends with `os.replace(staging, destination)` — a new directory, new inodes — and `project-runtime up` runs `up -d --build --wait` with **no `--force-recreate`**. Compose's config hash covers the service *definition*, and the bind source path is the identical string every deploy, so nothing looks changed. Measured on the host: the installed `pgbackrest.conf` was `-r--r--r--` dated 06:14 while the running container saw `-rw------- 0 root root` dated 05:36 — **link count 0**, a deleted inode, from a container created before two consecutive fixes. Both repairs were correct and neither could reach it. | **Not fixed yet.** Unblocked by hand with `docker rm -f` and a redeploy, which is what proved the diagnosis. | **This is ADR 0088's residual, made concrete and generalised.** That ADR already says *"a verifier acknowledges by being recreated"*, and the deploy prints **"the key set CHANGED: every verifier must be RECREATED, not restarted"** on every single run — a warning, followed by relying on Compose to notice a change it structurally cannot see. So a JWKS rotation has the same defect, and so does any future bind-mounted artefact. `--force-recreate` on everything is the blunt fix and restarts the world each deploy; the targeted one is a **label carrying a digest of the files each service mounts**, since Compose hashes labels and would then recreate exactly the affected containers. **Three deploys were spent on one defect because of this**, and it is the most consequential thing still open at the end of Run 11. | — |

| **D592** | — | **The DEPLOYED document carries no `compose` block, and D587's selector read one.** Step 6c passed — it is handed the *rendered* document, which publishes `compose.project_name` — and the very next operator command, `bin/backup.sh --outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json backup --type full`, raised `ValueError: compose_project_name is required to select a container`. `deployed_output` publishes `project`, `host`, `routes`, `database`, `secrets` and the rest; `compose` is not among them. | **`naming.compose_project_name(key)`**, split out of `derive` for the reason `backup_network_name` was — one derivation, more than one reader — and both operator commands derive it from `project.key`, which **both** document kinds carry. | **A fix verified against one document kind and shipped for two.** D587 was measured on the host, correctly, using the render — and the command an operator actually runs takes the other kind. §6's question 5: *when a decision is implemented, which of its callers got it?* Calling `naming.compose_project_name` is **not** a second derivation under ADR 0002; it is the authority, and `derive` calls it too — what ADR 0002 forbids is re-implementing `f"apg-{key}"` elsewhere, which is what this prevents. The test asserts the premise as well as the property: `deployed_output.py` must contain no `compose` block, so the day it publishes one, D592's reasoning is re-read rather than silently relied on. | — |

| **D593** | "Recovery time … must be recorded as evidence." | **A 31 MB backup takes six minutes, and it is latency times one process.** Measured on both projects: alpha 32 MB / 1342 files / **366.7 s**, beta 31.1 MB / 1330 files / **380.9 s**. That is **284 ms per file** and **84 KB/s** — nothing like a bandwidth limit. `process-max` defaults to **1**, so pgBackRest performs 1330 serialised S3 PUTs, each a full round trip to R2. Repository size is 4.1–4.2 MB, so compression is working and is not the cost. | **Recorded, not tuned.** `process-max` is a real knob and 4 would cut this roughly fourfold, but the drill is about to measure an RTO and an RTO measured against a configuration nobody has deployed is a number about nothing. Tuning it is its own decision with its own ADR. | **Two wrong explanations preceded this one, and a control killed both.** The first was "the archive backlog is draining" — falsified by beta, which had **0 failed** archives and took the same six minutes. The second was "it is waiting on the prior WAL segment" — falsified by `archive-timeout`, whose default is **1 minute**: had it been waiting, pgBackRest would have errored at 60 s. What the log actually shows is that `check archive for prior segment` is simply the last line printed before the copy phase, which `log-level-file=info` does not itemise. **Asking for beta's timing as a control on alpha's was the only reason any of this was caught**, and it is the clearest instance this session of a control disproving the person who proposed it. The cost is paid nightly by both timers and again by every restore, so it is an input to `REC-EVID-001` rather than a curiosity. | — |

| **D594** | `test_rendered_migrations.py`: "every rendered file is `0600` except two published snapshots." | **Three contract tests went red on the host, and the code was right.** `bin/session-01-check.sh` and `bin/session-10-check.sh --mode offline` both failed at `ee65bc4` with the same three: `test_everything_else_in_the_rendered_directory_stays_owner_only` (`pgbackrest.conf` is `0444`), `test_the_published_snapshot_is_the_only_world_readable_file` (a third world-readable name), and `test_the_install_exemption_is_the_migrations_directory_and_nothing_deeper` (`assert "_is_migration_artifact" in source`, and the correct repair had **deleted** that function). All three encoded a policy that had exactly two shapes when it was written. | **ADR 0154**, and the three are **replaced by stricter ones**, never relaxed. `RENDERED_EXEMPTIONS` (names to skip) becomes `RENDERED_FILE_MODES` (name → exact mode), closed in **both** directions; the world-readability check keeps its closed list and gains a content check against the secrets contract; the source scan becomes an AST assertion that `install_rendered` contains **no `chmod` call at all**, with a premise check that `chmod` is spelled somewhere in the module so the walk is finding a real absence. | **The exemption list was the defect, not the third mode.** An exempted name was `continue`d, so nothing asserted its mode — `openapi.json` could have been `0666` and stayed green. That is the failure mode of every skip-list: it is written as a narrowing and behaves as a hole. The third test was **D464's shape** (a string standing in for a construct) and it failed for the best available reason — the right repair deleted the construct — which is the argument for asserting what code *produces* rather than which names appear in it. Neither gate has ever run since D588/D589 landed, so this is §6's **question 2** again: *has it run at all, in this environment, since the thing it measures last changed?* The answer was no, and the answer is no for the same reason it is the oldest unbuilt item in §8. | — |
| **D595** | — | **The replacement was tautological on first draft, and the battery caught it.** `RENDERED_FILE_MODES` was written as `{"pgbackrest.conf": rendering.PGBACKREST_CONF_MODE, …}`. Battery arm **Q1 — D588 reintroduced, `PGBACKREST_CONF_MODE` set back to `0o600` and the fixture re-rendered — SURVIVED**: mutating the constant moved the rendered file *and* the expectation together. Q2 (`SNAPSHOT_MODE` → `0o600`) survived identically. | Every name and every mode in the mapping is a **literal**, and the world-readability list too. `rendering.py` holds the reasoning for each mode; the test holds the contract; **the two must be able to disagree**. Re-run: **6/6 killed.** | **§6, verbatim: *a test comparing two constants is not testing the thing between them*** — and it was written into a test whose entire purpose was catching that constant drifting. It passed on the first run and would have passed forever, because the drift it watches for is the drift that moves both sides. Two things made it visible and neither was review: the mutation was applied to the **product** and the fixture **re-rendered**, rather than the test being edited into failing; and the mutation chosen was **the real defect, D588 itself**, not an invented one. A survivor is evidence (§1) — this one was a weak test, and the strongest argument in this session for mutating what shipped rather than what a test asserts. | — |

---

## 2. What Session 10 adds to the acceptance registry

**Nothing.** The five requirement IDs already exist and point at placeholders:

| ID | Priority | What it must prove |
|---|---|---|
| `REC-PITR-001` | P0 | A timestamp-targeted restore into a disposable volume succeeds |
| `REC-SAFE-001` | P0 | The restore path never mounts, overwrites, or mutates the active volume |
| `REC-SMOKE-001` | P0 | The restored instance passes schema, RLS read, and write-RPC checks |
| `REC-EVID-001` | P0 | Restore evidence records backup set, requested and achieved recovery point, RTO, schema version, and test outcomes |
| `REC-WAL-001` | P1 | A WAL archiving failure produces a visible non-zero signal |

**Replace the placeholders; keep the IDs and their descriptions**, rewriting a
description only to a *stricter* statement of the same property (ADR 0096, D422).
Adding a new ID requires grepping the registry first — ADR 0089 / D279: three of
Session 6's six "new" IDs were already taken, and because `claim_session` derives
from `max()`, one would have turned three earlier sessions' evidence red while the
other vanished from the gate.

**Two threat-model rows move with them.** `docs/threat-model.md:33-34` name
`tests/recovery/test_future_pitr.py::test_timestamp_targeted_restore_succeeds`
and `::test_restore_evidence_records_the_required_fields` directly, and
`test_threat_model_node_ids_are_collectible` fails the moment those functions
stop existing. `THR-DATA-LOSS` and `THR-BACKUP-COMPROMISE` are the rows.

**Claims are a separate act.** Under ADR 0045 a requirement complete in a
checkout is not a claim; every claim needs at least one node id marked
`live_host` or `external`, or `claim_mode` refuses it. Session 10's claims are
registered in `evidence_claims.CLAIMS` in the run that publishes, together with
their rows in `tests/contract/test_evidence_claims.py::CLAIM_INTRODUCED_IN`.

**`claims_through_session` is cumulative**, so Session 10 still owes every
Session 4–9 external claim — `transport_boundary`, `connection_tooling`,
`public_api_boundary`, `public_storage_boundary`, `public_agent_boundary`. The
external gate mode is therefore not optional, exactly as it was not for Session 9.

---

## 3. Environment feasibility

| Requirement | Status | Note |
|---|---|---|
| An R2 bucket for the repository | **Does not exist. Operator, out of band.** | ADR 0110: nothing in this repository creates a bucket, and `bin/storage-admin.py` says so structurally. |
| An R2 API token scoped to that bucket | **Does not exist. Operator, shown once.** | `origin: operator_supplied`, the `r2_access_key_id` pattern exactly. `--apply` must stop, not converge. |
| A repository cipher pass | Generated | `origin: generated`, `value_kind: random_hex`, `plane: compose`, consumer `postgres`. |
| Egress from the new `backup` network | **Unmeasured.** | Run 1. `storage` reaches R2 over `edge`; nothing has ever put the database on an egress network. |
| pgBackRest at a pinned version inside the pgvector base | **Unmeasured.** | Run 1, with a control. PGDG apt versus a multi-stage `COPY` from `PGBACKREST_IMAGE` — musl-versus-glibc is the trap in the second. |
| Host disk headroom for a full restore | **Unmeasured, and nothing in `docs/host-baseline.md` records disk at all.** | A restore materialises a second copy of the cluster. This is a pre-flight in the operator guide, measured before the first drill, not discovered during it. |
| Host memory | 4 GB, two projects, 16 containers, `HOST_MEMORY_GUARDRAIL_MB = 1600` per project | The disposable restore container carries an explicit small `mem_limit` and is removed when the drill ends, pass or fail. |
| systemd timers | Available; the installer does not glob them | D522. |
| Running the drill over SSH | **No.** | `op` cannot reach the Docker daemon. `stanza-create`, the first backup and the drill all need a human with `sudo` at a TTY, like `migrate.sh` and `deploy.sh --through-session`. |

**The unmeasured boundary that stays unmeasured:** how long a full restore of a
*large* cluster takes. The drill measures this deployment's RTO on this
deployment's data. It is a measurement, not a bound, and the evidence document
records it as one.

---

## 4. Safety plan for irreversible operations

Five operations cannot be undone by re-running a command.

**1. Issuing the R2 token.** Cloudflare shows the secret access key exactly once.
It is pasted into the provider by hand at `/backup/APG_R2_SECRET_ACCESS_KEY`; no
command here sets a value at the provider (D249). A lost value is replaced by
issuing a new token, which is a rotation, not a retry.

**2. `stanza-create` against the wrong bucket or prefix.** The stanza is written
into the repository. A stanza created under a mistyped prefix leaves objects
nothing here will ever reference and nothing here will ever delete. The
repository target is therefore **derived and printed before the call**, and the
first `stanza-create` of each project is an explicit operator step in the guide
with the resolved bucket, prefix and stanza echoed for confirmation.

**3. Turning on `archive_mode`.** It is not reloadable; the cluster restarts. On
an already-deployed project this happens inside the deploy, which recreates the
container anyway. What must not happen is a cluster that starts archiving before
its stanza exists and quietly fills `pg_wal` — Run 1 measures what a
stanza-less `archive_command` does, and the deploy's ordering follows the
measurement.

**4. Releasing migration 0022, if Run 5 shows one is needed.** Released
migrations are fix-forward only and every down block raises AP900. Whether the
backup privileges belong to the migration plane or the bootstrap plane is a
measurement, and the wrong answer is a released migration that cannot be
withdrawn.

**5. Removing the disposable restore target.** The teardown must be idempotent
and must be unable to name `postgres-data`. It runs in a `trap`, so a drill that
fails halfway still cleans up — and a teardown that cannot find its target exits
non-zero rather than widening its search.

**The standing rules apply unchanged.** No secret value in source control,
Compose interpolation, process arguments, image layers or logs. `--render-only`
keeps working with no host and no root. Nothing privileged that mutates is piped
over SSH.

---

## 5. Build order

Runs are the unit. Each ends with the offline gate green on a clean tree, and
CLAUDE.md §4's procedure applies to every one: measure third-party behaviour with
a **control** before writing anything that depends on it, write the ADR when the
measurement decides something with alternatives, implement, then **try to break
the tests** with a mutation battery whose failures are fatal (D269), whose
control is a test the mutation cannot reach (D499), and which asserts *how* each
mutation failed (D386).

### Run 1 — Measure how pgBackRest reaches the cluster — **Done.**

Nothing is written until this run answers, each arm with a control that proves
the rig can tell success from failure:

- Does pgBackRest install into `pgvector/pgvector:pg18` at a pinned version?
  Two candidate routes — PGDG apt, and a multi-stage `COPY` out of
  `PGBACKREST_IMAGE`. **The second is the trap**: if the woblerr image is
  musl-based the binary will not run on the Debian base, and the failure is a
  loader error several steps from its cause.
- Does it run as uid **999** with a `0400` config it does not own?
- `pg1-path`: confirm `/var/lib/postgresql/18/docker` against the running
  container, not against `test_image_contracts.py`'s constant alone.
- What does the postmaster do with a failing `archive_command` — how fast does
  `pg_stat_archiver.failed_count` move, and does `pg_wal` grow without bound
  before the stanza exists?
- Can a container on a network with `internal: false` and no Traefik reach
  `*.r2.cloudflarestorage.com`?

**ADR:** the archiver lives beside the cluster it archives, and what that costs.

**Done.** Five arms, each with a control that ran green in the same invocation,
against the pinned digests on 2026-08-23. **Three of the five contradicted this
plan**, and the corrections are D531-D535.

**What was measured (rig1).**

* **Arm C - PGDATA.** `/var/lib/postgresql/18/docker`, read off the running
  image rather than off `test_image_contracts.py`'s constant; the image's
  declared VOLUME is `/var/lib/postgresql`. The two differ, so the comparison
  can fail. **D514 confirmed.**
* **Arm A0 - the source image.** Ubuntu 24.04, glibc. **The plan's musl trap
  does not exist** (D531).
* **Arm A1 - the apt route works**, and cheaply: `pgbackrest
  2.59.1-1.pgdg12+1`, package count 155 to **157** (`pgbackrest` and
  `libssh2-1`, nothing else), **+800,863 bytes**. Its control - the same
  Dockerfile with `pgbackrest=0.0.0-doesnotexist` - fails with `E: Version ...
  was not found`, exit 100, so a green install is not a step that cannot fail.
  **PGDG does not carry the pinned 2.55.1** (D532), and the pin is not a digest
  (D533).
* **Arm A2 - the COPY route builds and does not run**, on a missing
  `libssh2.so.1` (D531). The library A1 installs is precisely the one A2 lacks.
* **Arm B - a config the archiver cannot read stops it.** uid 999 against a
  root-owned `0400` config: `P00 ERROR: [041]: unable to open file ... for
  read: [13] Permission denied`, **exit 41**. Owned `999:999`, same mode:
  **exit 0**, and the output names stanza `rig`, which exists only in that
  file. **pgBackRest does not silently fall back to defaults** - the failure
  mode §9 fears is absent here, and that is worth knowing before Run 4 mounts
  anything. **D515 confirmed and strengthened.**
* **Arm D - a failing `archive_command`.** `failed_count` 11 / 15 / 26 at T+0,
  T+30, T+60; `archived_count` 0; `last_archived_wal` NULL; `pg_wal` 5 to 6 to
  11 files. The `/bin/true` control archived 4 to 5 to 6 with `failed_count` 0
  and `pg_wal` flat at 4, in the same invocation. **`pg_isready` reported
  accepting connections throughout** (D534), and **`last_failed_wal` never
  advanced** (D535).
* **Arm E - egress.** A plain user-defined bridge resolved
  `r2.cloudflarestorage.com` to `172.64.190.1` and connected on 443; the same
  image on an `--internal` network failed both DNS and TCP. **`internal: true`
  is a real boundary**, so D516's second network is required rather than
  tidy-looking.

**One rig defect, recorded because it is the same shape as the product defects
this session hunts.** Arm B's *verdict* lines looked for a `repo1-path` marker
in `pgbackrest info` output, which `info` never prints, so both arms printed
"inconclusive" while the measurement underneath them was decisive. The
discriminator that actually worked was unplanned: B2's output names the stanza
`rig`, which exists only in the config under test. **The reading was wrong, not
the measurement** - and a rig whose verdict logic cannot see its own result is
one commit away from a proof with the same property.

**ADR 0144**, and it decides more than the install route: the base stays
digest-pinned, the derived layer adds two packages, `archive_command` runs as
the postmaster's own uid, every archiver-readable file is `999:999` `0400`, and
**`PGBACKREST_IMAGE` is retired** rather than left inert beside a pin that
disagrees with it.

**No mutation battery.** This run wrote no assertion to mutate - its output is
five measurements, an ADR and five divergence rows. The battery arrives with
Run 2's first tests.

### Run 2 — The manifest, the identity, and outputs v13 — **Done.**

- `backup.bucket`, `backup.account_id`; `retain_full` gains a default and is
  propagated; a `BACKUP_DEFAULTS` beside `STORAGE_DEFAULTS`.
- `naming.backup_bucket_name`, `naming.backup_network`; the endpoint derived by
  the existing `storage_endpoint_url`, not a second function.
- `evidence.ISOLATED_FIELDS` gains `("compose","networks","backup")` and
  `("backup","bucket")` — the collision proof must cover the new identities
  before any cluster exists.
- **Outputs v13**, chosen once from the whole session's surface: `retain_full`,
  the bucket and the network on a shared `$def`, plus a deployed observation
  block. `output_migrations` gains its v12 → v13 step and a fixture.

**ADRs:** the repository's location, and outputs version 13.

**Done.** The identity plane is complete and outputs is at **v13**. Both example
projects render; the suite is **3956 passed, 281 skipped**, up 29.

**What was built.** `naming.backup_bucket_name` and `naming.backup_network_name`
— the second split out for the reason the first was, one derivation with three
readers, the third being `output_migrations`. `config.BACKUP_DEFAULTS` beside
`STORAGE_DEFAULTS`, which is D519's actual repair: `retain_full` now resolves,
propagates and is published, after nine sessions of being bounded and read by
nothing. `_validate_backup` gained the account-id requirement and the bucket
check, both validated **through the deriver** rather than beside it. Outputs
v13 on both branches, `backup` as one shared `$def` and `backup_state` as a
deployed-only block, with `migrate_v12_to_v13` and `BACKUP_NOT_OBSERVED`.

**Two decisions, ADR 0145 and ADR 0146.** 0145 refuses the specification's own
fallback — one bucket, two prefixes — because R2 scopes a token to buckets and
not to prefixes, so the fallback's isolation claim would have no executable
check behind it while `THR-BACKUP-COMPROMISE` names one. 0146 is D537: the
observation is a block of its own so that ADR 0012 and D389 can both hold.

**The two example manifests now disagree on purpose.** Alpha derives its bucket,
beta overrides it with `alpine-dev-repository` — deliberately not `apg-`-shaped,
because an override that looked derived would pass whether or not the prefixing
branch was taken (D374's shape). Neither fixture alone renders both paths, and
two fixtures making the same choice is how `retain_full` reached this session
unread.

**Nine hand-chained migration tests had to be edited rather than re-run**, which
is the convention working: each asserts the step's own result as a literal and
the chain's endpoint as `CURRENT_VERSION`, and the file's own comments record
that spelling both as the constant is how the assertion stopped meaning anything
the last time a version was added.

**Battery: B1–B9, 9 of 9 killed**, every one `FAILED` rather than `ERROR`
(D386), every control green in the same invocation and unreachable by its
mutation (D499), every anchor pre-flighted to exactly one match (D269), and
every mutated file restored **by copy** and verified byte-for-byte — never
`git checkout --`, because the files under test are uncommitted. The arms worth
naming: **B3** collides the two buckets at a long key, which is the one
collision `ISOLATED_FIELDS` structurally cannot see because every isolation
proof here compares two *different* projects; **B7** drops `backup.bucket` from
`ISOLATED_FIELDS` and is killed only by the test D536 added; **B9** replaces
`not_observed`'s nulls with zeroes, which is the substitution `NOT_OBSERVED`
exists to refuse.

**One thing published a run before it is consumed.** `compose.networks.backup`
is named here and attached to nothing until Run 4. That is the state
`storage.bucket` was in from Session 1 to Session 7 — and it is exactly why the
name went into `ISOLATED_FIELDS` now rather than then: D339 found the one
derived identifier that had gone six sessions without a namespace, and it was
the one nothing compared.

**The deployed branch has no `compose` block at all**, so the network appears on
the rendered branch alone. Read rather than assumed, and it is why v13 needed no
deployed-side network field.

### Run 3 — The three secrets and the two-stage convergence — **Done.**

- `backup_r2_access_key_id`, `backup_r2_secret_access_key`
  (`origin: operator_supplied`, provider path `/backup`) and
  `pgbackrest_repo_cipher_pass` (`origin: generated`), all three with consumer
  `postgres`, `uid: 999`, `gid: 999`, `mode: "0400"`, `format: raw`.
- `bootstrap-providers.py` reports the two operator-supplied entries on both
  `--plan` and `--apply` and refuses to generate them.
- `observe_backup`, following `observe_storage` exactly (D326): `unavailable`
  until the credential is in the **active generation** — read from
  `secrets["required_names"]`, not from the manifest, because a project whose
  manifest declares backups and whose generation carries no credential is a
  different fact (D76, D306). **The deploy exits 0**, prints the operator
  command, and converges on the redeploy.

**Done.** Three secrets, all granted to `postgres` and to nothing else, and a
deploy that can say what it does not know.

**What was built.** `backup_r2_access_key_id` and `backup_r2_secret_access_key`
(`origin: operator_supplied`, provider path `/backup`) and
`pgbackrest_repo_cipher_pass` (`origin: generated`), every one `uid: 999,
gid: 999, mode: 0400` — the postgres image's own user, not the 65532 every other
consumer uses, which is D515 arriving in the file rather than on a host.
`introduced_in_session: 10`, so nothing materializes them until Run 10 moves
`CURRENT_SESSION`. `BACKUP_PLANE_SESSION`, `BACKUP_CREDENTIAL_NAMES` and
`observe_backup` in the deploy.

**`ready` is unreachable in this run, and that is the assertion.** Three files
existing says a request *could* be made — not that a stanza exists, not that a
backup succeeded, not that WAL is arriving. `observe_backup` returns
`unconfigured` or `not_observed` and nothing else, and a parametrized test
covers all four input combinations plus the invariant that every non-status
member is null. Run 6 replaces it with an observer that asks the repository.
Returning `ready` on the strength of three files would be §6's subject exactly,
and the evidence document would read it as a working repository.

**The credential gate counts all three files, not two.** A valid token with the
wrong pass phrase is not partially configured; it is a repository nobody can
restore. Gating on the credential halves alone would publish a state for a
deployment whose backups are unreadable — C6 is the arm that proves the
distinction is load-bearing.

**D538 is the row to read**, and the flags it turns on were already there. The
contract has always been able to say *generated* and *rotatable*; it has never
had a way to say *changing this destroys what it protects*. The cipher pass is
the first secret where a claimed rotation is not merely misleading but is the
report you would be reading while every backup became unrecoverable.

**One wording correction to this run's own plan text above.** It says the state
is `unavailable` until the credential arrives, borrowing the vocabulary of a
published route. `backup_state` is not a route and v13 gave it its own four
values in Run 2; the state is **`unconfigured`**, which additionally covers
backups being switched off — a thing `unavailable` cannot express.

**Nothing was needed in `bootstrap-providers.py`.** Its refusal, its `--plan`
report and its exclusion from `managed_resources` are all generic over
`origin`, so the two new operator-supplied entries are named and refused by code
Session 7 wrote. That was checked rather than assumed: the session-10 list is
asserted to be the four operator-supplied secrets in order, and the cipher pass
is asserted **absent** from it — a plan that asked an operator to paste a phrase
nobody issues is C4.

**Battery: C1–C7, 7 of 7 killed** as `FAILED`, each control green and
unreachable, both mutated files restored byte-for-byte. **The pre-flight earned
itself on C3**: the flag trio `rotate_by_replacement: false /
must_refresh_on_start: false / one_time_initialization: true` matches
`postgres_init_superuser_password` as well as the cipher pass, so the anchor
matched twice and the battery refused to run. Unanchored, it would have mutated
the wrong secret and reported a kill for a test that never saw the mutation
(D269's exact shape).

### Run 4 — The image, the config, the network, the archive — **Done.**

- `services/postgres/Dockerfile`; `PGBACKREST_VERSION` beside the image pin in
  `versions.in.yaml`.
- The rendered `pgbackrest.conf`: stanza, `pg1-path`, `repo1-type=s3`, endpoint,
  bucket, prefix, `repo1-cipher-type=aes-256-cbc`, `repo1-retention-full`, log
  and spool paths. Rendered by the same incapable renderer everything else uses.
- The `backup` network; `postgres.networks` becomes `[internal, backup]`; the
  three secret mounts; `archive_mode`, `archive_command` and `archive_timeout`
  on the command list.
- **`--render-only` must still work with no host and no root**, and a rendered
  fixture must still render identically for both example projects.

**Done.** The cluster builds from its own image, carries an archiver, reaches a
repository over a network of its own, and renders a configuration with no
credential in it.

**What was built.** `services/postgres/Dockerfile` — the first database image
this repository builds — taking `BASE_IMAGE` and `PGBACKREST_APT_VERSION` as
arguments with no defaults. `compose.yaml`: `build:` replacing `image:` (both
together would tag the local build with the upstream digest's identity), the
three archiving settings on the command line, the `backup` network, and the
rendered config mounted through `runtime_override` rather than through a
`${VAR}` a checkout cannot produce. `build_pgbackrest_conf`, and
`config.ARCHIVE_TIMEOUT_SECONDS`.

**The lock learned a third registry**, and that was not in the plan. An apt
version added the obvious way is a string nothing dereferences, which is D201's
exact condition and has reddened this gate six times — and D533 had already
forecast that `lock-versions.sh` is where it gets fixed. Measured first (rig2,
four arms): the bookworm-pgdg index is 1.1 MB gzipped, 4,310 stanzas, fetched in
0.4s, and **both controls refuse** — a version that does not exist and a package
that does not exist each resolve to nothing rather than to something plausible.
`versions.env` now carries
`PGBACKREST_APT_VERSION_DIGEST=sha256:ecea2337…`, and the production path
resolved the same digest the rig did, independently.

**`PGBACKREST_IMAGE` is retired** (D532), so the lock names one pgBackRest and
it is the one that gets installed.

**Two things the archiving config does that a default would not.**
`repo1-cipher-type` is written rather than omitted, because its default is
`none` — an unencrypted repository that looks configured is the worst default
in this file. `repo1-s3-uri-style=path` is written for ADR 0107's *reason*
rather than its measurement: the botocore fallback D344 measured does not
transfer to pgBackRest, but freezing one style does, so an upstream default
change becomes a diff instead of a deployment that stops working.

**`archive_timeout` is a product constant and not a manifest field**, and the
refusal is recorded rather than left looking like an oversight. D519 says a
bound should be published; publishing this one means a member on
`backupSettings`, which means outputs **v14 inside the session that shipped
v13** — which ADR 0146 refused in as many words.

**Two passing tests were replaced by stricter ones, both ADR-authorised.**
D539 is the built-service uid rule. The other is
`test_postgres_joins_only_the_internal_network`: its old assertion was
`networks == ["internal"]`, which would have been satisfied by any single
network **including `edge`** — the replacement pins both members and asserts
`edge` is not among them, which is more than the original said (ADR 0147,
ADR 0096).

**D540 is the row a future run has to act on.** `--update` re-resolved three
unrelated rolling tags, one of which would have invalidated Run 1's entire
measurement set. They are restored; nothing prevents the next `--update` from
re-adopting them.

**Battery: E1–E9, 9 of 9 killed** as `FAILED`, control green and unreachable in
every arm, both mutated files restored byte-for-byte. Four arms re-render the
fixtures because the tests read `.generated/`, and that is per-arm rather than
unconditional so an arm cannot pass because of a re-render it did not need. The
arms worth naming: **E1** leaves the repository unencrypted, **E2** points
`pg1-path` at the volume mount rather than PGDATA — the mutation whose real
consequence is a restore of the wrong directory rather than an error — and
**E8** marks the egress network `internal: true`, which is the edit a future
reader makes while "hardening" and which would silently stop every backup.

**`--render-only` still works with no host and no root**, verified as uid 1000.

### Run 5 — Activating `backup_user`, and the fifth claimant. **Done.**

- Bootstrap-plane LOGIN, credential and `CONNECTION LIMIT` — the migration plane
  creates nothing (D102).
- **Measure** which privileges an online backup actually needs on PG 18:
  `EXECUTE` on `pg_backup_start`/`pg_backup_stop`, `pg_read_all_settings`,
  `pg_checkpoint`, and whether any of it is a `GRANT role TO role` (bootstrap
  plane) or a `GRANT EXECUTE` (migration 0022). A grant question reads
  `aclexplode` and subtracts the owner; a reach question sets the role and tries
  it (D467, ADR 0134).
- `LOGIN_ROLES` and `activated_login_roles` re-derived from the event.
- The budget: the fifth summand, or the administration reserve — D530's decision,
  with the number.

**ADR:** what a backup identity holds, and the fifth claimant on one budget.

---

**What Run 5 measured, and what it changed.** ADR 0148. Rig 5, eight arms
against the pinned PG 18 digest and the Run 4 derived image, every arm with a
control that could distinguish success from failure.

**The privileges are five, not the three the plan guessed, and `pg_checkpoint`
is not among them.** The plan's list was written from the shape of the problem
rather than from a measurement, and both halves of it were wrong. What the
matrix says (arm G, one revocation at a time): `pg_read_all_settings`,
`EXECUTE` on `pg_backup_start(text, boolean)`, `pg_backup_stop(boolean)`,
`pg_create_restore_point(text)` and `pg_switch_wal()`. **`pgbackrest check`
needs the last two and `pgbackrest backup` needs neither** — which matters
because Run 6 puts `check` in the deploy's step 6c and Run 9 puts it on both
timers.

**D541 is the row worth reading before the next privilege question.** An early
arm granted three, ran a full backup successfully, saw `check` fail on
`pg_create_restore_point`, granted it — and `check` still failed, on
`pg_switch_wal`, which that arm had already recorded as unnecessary because
nothing had reached it. One missing privilege masks the next, so *"the last
thing I granted fixed it"* measures the first failure and not the set. Only
revoke-one-at-a-time measures a set.

**There is no migration 0022, and arm C measured that rather than citing a
rule.** A role with the migration plane's exact shape — NOSUPERUSER, owning the
application schema, no ADMIN option — was refused all five: `permission denied
for function` on the four, and `Only roles with the ADMIN option on role
"pg_read_all_settings" may grant this role` on the membership. The arm's control
is what makes that a plane boundary rather than a broken `SET ROLE`: the same
role, in the same session, granted `SELECT` on a table it owned and succeeded.
**Migrations are unchanged at 21.**

**D530 is decided: the backup is its own summand, and the number is 2.** The
administration reserve exists for claimants that hold **no `CONNECTION LIMIT`** —
there is nothing on a superuser or on `migration_user` to bound them with. A
role that carries a server-enforced ceiling belongs in the sum beside the other
four, because a ceiling the arithmetic cannot see is how the enforced limits come
to exceed `max_connections` with every check still passing. The reserve's comment
loses the word "backups" it has carried since Session 5.

**Two, and both halves were measured.** A lone pgBackRest command holds **one**
connection — 68 samples of `pg_stat_activity` taken inside the same invocation as
a real full backup, maximum 1. The second is the overlap (D544): pgBackRest takes
no lock preventing a `check` during a `backup`, a `check` launched two seconds in
ran to completion, both exited 0, and the sampler recorded 2. The control is the
same `check` at the same ceiling with no backup running, which exits 0 — so the
failing arm measured the overlap and not the ceiling.

**Both arithmetics moved together**, which is the whole of D327's lesson:
manifest 50 → 52 of 56, bootstrap remainder 23 → 21 against a pooler pool of 20,
**headroom untouched at 5**. The application's slack for direct sessions falls
from 3 to 1 and that is charged, stated and recorded as D546 — the real
`project.alpha.yaml` and `project.beta.yaml` are gitignored and unread, so
`deploy.sh --render-only` on the host is the first thing that can confirm they
still fit, and it needs no root.

**Two predicted rednesses arrived as predicted, and neither was weakened.**
`_summands_of_the_budget_check` parses the arithmetic rather than a list beside
it, precisely so a fifth claimant fails offline — and it did, here, rather than
as a refused login on a host. `LOGIN_ROLES` and `activated_login_roles` gained
`backup_user` keyed on **the credential appearing in `secrets.required_names`**,
which is the same fact `activate_backup_user` reads. `backup.enabled` was the
available mistake and is refused by a test: the bootstrap plane never reads that
flag, and every project's first Session 10 deploy is a project with backups
enabled and no materialized secret.

**Three findings the plan did not predict**, all from the full suite rather than
from the targeted set — which is the argument for having run it once here:
`backup_user_password` had to enter `bootstrap-state.schema.json`'s
`managed_resources` (Run 4's lesson, verbatim, for the second time this session);
the bootstrap plane's consumer list was hand-written and enumerated by nothing
(D547, now a containment test); and `ADMINISTRATION_RESERVED_CONNECTIONS` and
`OPERATIONAL_CONNECTION_HEADROOM` turn out to be one claim stated twice in two
modules at the same value (D545, recorded and deliberately not merged).

**Battery: M1–M9, 9 of 9 killed** as `FAILED`, control green and unreachable in
every arm, all three mutated files restored byte-for-byte. **Two survived the
first run and both were real weak tests**, which is the outcome a battery is
for:

- **M5** mutated `BACKUP_USER_CONSUMER`'s `target_file` and the activation test
  passed, because the fixture wrote the generation at *the module's* path rather
  than the contract's — so the test moved with the mutation. That is
  D288/D289/D291 occurring inside the test whose docstring says it does not make
  that mistake. The fixture now reads the path from `secrets.required.yaml`.
- **M9** replaced `config.BACKUP_RESERVED_CONNECTIONS` with the literal `2` and
  the test guarding against exactly that passed, because it was a text scan and
  the string also appears in a **comment** four lines above the import — D277,
  and D464's shape. It is now an assertion on the syntax tree: the value bound to
  `backup_budget` must be an attribute access on `config`, where a comment cannot
  reach and a literal cannot hide.

Preflight earned its place too: M3's anchor matched twice, because `app_runtime`'s
membership carries the same three options, and an unapplied mutation would have
reported as a weak test (D269).

**Nothing is deployed.** No pgBackRest command has been run against R2 by this
run or any other; arm E used a `posix` repository on a local volume, because the
questions it asked — which SQL, how many backends — do not depend on where the
bytes land.

### Run 6 — `bin/backup.sh`, and the deploy's step 6c. **Done.**

- `bin/backup.sh` + `bin/backup.py`: `stanza-create`, `check`, `backup --type
  full|incr`, `info`, `expire`. `--help` exits 0 with no host; the CLI contract's
  preamble, exit-code and no-secret-argument rules apply.
- The deploy gains **step 6c**, after step 6 (the cluster exists and
  `backup_user` can log in) and before step 7 (observe and publish): create the
  stanza if absent, then `check`. A `check` failure is a deploy failure with a
  named reason, not a warning.
- Retention comes from `retain_full`, applied once, in the config — never
  restated in a command (D495, D463).

---

**What Run 6 measured, and what it changed.** ADR 0149. Rig 6, five phases
against the Run 4 derived image, with the rig's own setup under a control.

**`pgbackrest info` exits 0 in every state, including for a stanza that does not
exist** (D548). That single finding shaped the whole observer: the three
repository states are distinguishable by `status.code` and by nothing else, so
`backup_report` reads that field and an AST test asserts nothing in the module
touches `returncode`. Built the obvious way — run `info`, check it succeeded,
report healthy — the observer would have reported a healthy repository for a
stanza that has never existed, on every project, forever. It is D145's shape and
it was one line of code away.

**`stanza-create` is idempotent, so step 6c does not probe** (D549). The plan
said "create the stanza if absent", which implies asking first; measured, twice
in a row exits 0, so the probe buys nothing and adds a window. **`expire` applies
retention from the config with nothing on the command line**, also measured —
which is the order those two facts have to be established in: unnecessary first,
undesirable second.

**A failing `check` fails the deploy**, and that is the run's real product.
Before this, a project with a broken `archive_command` deployed cleanly and
published nothing about it; D534 measured what that looks like from outside —
`pg_isready` answering *accepting connections* while `failed_count` climbs
11 → 15 → 26 and `pg_wal` fills. Step 6c is the first thing in this system that
turns that into a non-zero exit, and the assertion guarding it reads the syntax
tree rather than the text, because the comments around it say the word "fail"
repeatedly (D277).

**Two things v13 promised that measurement refuted.** `latest_recoverable_time`
"is read from `pgbackrest info`" — and `info` has no such field at all, only
per-backup epochs and WAL **segment names** with no time in or beside them
(D550). What is published is the newest backup's stop time, named in the schema
as a **proven floor**; a drill landing later is the floor being a floor, and
Run 8's evidence records the achieved point separately. And the status enum had
no value for the state **every** project is in after its first deploy, so
`awaiting_first_backup` joins it (D551) — extending v13, which has never left
this tree, rather than opening v14. That is the third instance of ADR 0053's
cost: a version chosen once from the whole surface, still short a value only
measurement surfaced.

**`observe_backup` now asks the repository, which its own docstring said Run 6
would do.** Leaving it would have been D276's shape — a comment describing work
nobody wrote — and Run 5 had just paid for that pattern. Run 3's test asserting
`ready` was unreachable is replaced by a stricter one rather than deleted: `ready`
now requires `status.code` 0 **and** a full backup label **and** no per-backup
error, and each non-ready rung is asserted separately.

**Battery: N1–N11, 11 of 11 killed** as `FAILED`, control green and unreachable
in every arm, all three mutated files restored byte-for-byte. **N4 survived the
first run and was a real coverage gap** (D498's category, not a weak assertion):
`test_the_newest_full_backup_is_reported_not_the_first_one_listed` used the
full-plus-incremental fixture, where there is exactly **one** full backup — so
`fulls[0]` and `max(fulls, key=stop)` are the same object and the mutation
between them was invisible. A test that cannot distinguish the two things it is
named after is testing neither. Repaired by capturing a real two-full report
whose newest full is **last**, with an assertion that the fixture is in that
arrangement — so the day a capture puts the newest first, the test says the
premise broke instead of passing by accident.

**The fixtures are real captures, not hand-written** — three of them, from
`pgbackrest info --output=json` at three points in a repository's life, plus the
two-full one. A hand-written fixture is a statement of what somebody expected the
tool to say, and two of this run's four findings are places where that
expectation was wrong.

**The rig measured its own setup failure as a pgBackRest finding** (D552). Its
first run used `docker exec` without `-i` — the trap CLAUDE.md §1 already names —
so psql ran nothing, the role never existed, and every command failed with
`unable to find primary cluster`. The setup now has a control that aborts
fatally. The new lesson is that a rig needs a control on its **setup**, not only
on its subject: every arm downstream was ready to report a confident wrong
finding about a third party, with plausible numbers.

**Nothing is deployed and nothing has dialled R2.** Rig 6 used a `posix`
repository on a local volume, because the questions were about pgBackRest's own
reporting rather than about where the bytes land. Step 6c has never run on a
host.

### Run 7 — A WAL archiving failure is visible. **Done.**

- Break the archive deliberately (a revoked credential arm and a wrong-prefix
  arm), and prove the signal: `pg_stat_archiver.failed_count` moves,
  `last_failed_wal` names the segment, the healthcheck goes unhealthy, and the
  operator command reports non-zero. **The control is the same assertion against
  a healthy archive in the same invocation.**
- `REC-WAL-001`.

---

**What Run 7 measured, and what it changed.** ADR 0150. Rig 7, eight arms
against the Run 4 derived image, each arm paired with its control in the same
invocation.

**The obvious predicate is wrong, and that is the run's main finding (D553).**
`failed_count > 0` would report **every project as failing, permanently, from its
first deploy**: the counter is cumulative, never resets, and every project
accrues failures in the window between its container starting with
`archive_mode=on` and step 6c creating its stanza. Measured, with the arm and its
control in one invocation:

    healthy baseline   archived_count  8 -> 12   failed_count 11 -> 11
    archiving broken   archived_count 12 -> 12   failed_count 11 -> 26
    repaired (control) archived_count 12 -> 21   failed_count 26 -> 26

The last row is the whole argument: **more cumulative failures than the broken
row, and perfectly healthy.** So the status compares timestamps —
`last_failed_time > last_archived_time` — and an AST test refuses the counters to
that function, because "simplify it to a count" reads as more obvious than what
is there. `archived_count` alone is no better: it freezes during the failure and
then **catches up** across the repair, so a reader sampling it twice sees a
healthy-looking increase.

**This refines D535 rather than contradicting it.** D535 says `failed_count` is
the value that moves while `last_failed_wal` pins to the oldest stuck segment,
and that is right *for detecting a change across an interval* — which is what
`REC-WAL-001` asserts. A point-in-time status is a different question, and
conflating the two is how a cumulative counter ends up in a status field.

**The plan's healthcheck prediction is reversed, and it was measured before it
was reversed (D555).** With the archiving predicate as the Postgres healthcheck,
`compose up --wait` **exits 1** while the database answers queries; the control —
the same broken archiver behind `pg_isready` — exits 0. **Three services gate on
`postgres: condition: service_healthy`**, so an archiving predicate there turns a
recoverability incident into an availability one: a backup problem stopping the
pooler, the auth service and storage from starting, on a cluster that is serving.
**And it blocks its own repair** — a broken archiver is fixed by deploying, and a
deploy that cannot pass `compose up --wait` cannot deliver the fix. D556 records
the strongest case for the rejected option, which is real: a red healthcheck
costs nothing at the container level (`status=running`, `RestartCount=0`, queries
answered). The harm is entirely in the two things that read health, and those are
exactly the two that must not.

So the signal reaches an operator through the deployed document
(`backup_state.status: failing` with both counters), `bin/backup.sh check`'s
non-zero exit, and step 6c's named deploy failure — all of which existed after
Run 6 except the first.

**`wal_archived_count` and `wal_failed_count` stop being null.** Run 6 returned
both as `None` with a test asserting it; Run 7 populates them from
`pg_stat_archiver`, read in step 6c **beside** the repository report so the two
describe one instant. They are published as measured — cumulative, unreset,
including the pre-stanza failures — because they are the diagnostic that
justifies the status rather than the status itself. `bin/backup.sh info` prints
them and says in as many words that a non-zero failed count on a healthy archiver
is expected.

**The two sources can only compound, never cancel.** A broken archiver turns a
`ready` repository into `failing`; a healthy archiver cannot promote a repository
with no backup out of `awaiting_first_backup`, because there is still nothing to
restore. Both directions are asserted.

**Only one of the plan's two arms can be run off a host, and the write-up says
so (D554).** The wrong-prefix arm is exact. The revoked-credential arm is a
**stand-in** — an unwritable posix repository, and an `EACCES` is not a `403`.
What they share is what the cluster sees, `archive_command` exiting non-zero,
which is all `pg_stat_archiver` records. The real arm needs the trip.

**Battery: P1–P9, 9 of 9 killed** as `FAILED`, control green and unreachable in
every arm, all three mutated files restored byte-for-byte. **P5 survived the
first run** and was a real coverage gap: the empty-timestamp test exercised only
the *failed* timestamp, so mutating the *archived* one survived — and survived
for an uncomfortable reason, since an empty string still compares greater-than
against nothing and the predicate returned the right answer by accident. Now both
empty fields are parsed, including the row a never-archived cluster actually
prints.

**A rig defect worth more than the arm it broke (D557).** Arm F churned with
`pg_switch_wal()` against an idle cluster, which archives nothing, and reported
the predicate as `ok` in a state it had failed to break — counters byte-identical
before and after. D552's rig failed loudly; this one produced a **plausible,
quiet, wrong answer** in the arm whose whole purpose was to watch the predicate
fire. **An arm hoping for "no change" cannot tell success from having done
nothing**, so arm G's churn writes first and the rig asserts its own counters
moved before concluding anything.

**`REC-WAL-001` is still a placeholder and is still Run 9's.** Its node id lives
in `tests/recovery/` and needs a deployment; Run 7 builds the signal and proves
the mapping offline. Nothing here empties `FUTURE_STUBS` or activates a registry
id.

**Nothing is deployed and nothing has dialled R2.**

### Run 8 — `bin/restore-test.sh` leaves `FUTURE_STUBS`. **Done.**

- `--target-time` and `--project-dir` parsed for real; the derived disposable
  volume and container names; a `trap` teardown that cannot name the live volume.
- The restore: `pgbackrest restore --type=time --target=<t> --target-action=promote`
  into the disposable target, then start it, then **query it**.
- The evidence document under `evidence/`: backup set (label and type), requested
  target, **achieved** recovery point and LSN, RTO measured by the command,
  latest recoverable time read from `pgbackrest info`, schema version from
  `schema_migrations`, and the smoke results.
- `REC-PITR-001`, `REC-EVID-001`. **ADRs:** disposability by construction, and
  what the evidence document records.

---

**What Run 8 built, and what it measured.** ADR 0151 and ADR 0152. Rig 8, against
the Run 4 derived image, the pinned base digest and pgBackRest 2.59.1, with a
posix repository standing in for R2 exactly as rigs 5–7 used one — what a posix
repository cannot measure is an endpoint, a token scope or a 403; what it measures
exactly is pgBackRest's own restore behaviour, which is all this run depends on.

**`bin/restore-test.sh` left `FUTURE_STUBS`, and the tuple is now `()`.** The
fourth and final application of ADR 0017's lifecycle, after
`bootstrap-providers.sh`, `migrate.sh` and `connect.sh`. `test_future_stub_exits_ten`
and `test_future_stub_names_its_owning_session` are **gone** — with an empty tuple
they would have collected zero cases, which is a test disappearing rather than
passing — and `DX-002` now names
`test_no_command_reports_an_unavailable_capability`, which drives **all forty**
commands and requires that none returns 10, where the test it replaced drove one
and required that it did. Measured before it was asserted: no command in
`SHELL_COMMANDS` returns 10 on a bare invocation.
`test_the_remaining_stubs_are_the_ones_later_sessions_own` is replaced by
`test_the_stub_lifecycle_is_complete`, and `test_database_commands.py`'s
cross-module guard moved in the same commit (D524).

**The run's largest finding is not about restores (D558).** Nothing supplies
pgBackRest its credentials at runtime. The rendered config omits all three by
construction and says pgBackRest reads them from the environment; nothing puts
them there. Measured with a control: the environment route works (`repo-ls` exit
0 against an encrypted repository, exit **37** without it) and **no `-file`
option exists** for any of the three. So step 6c's `check` would have failed on
the first deploy of the first project — correctly, and after a trip had been
paid for. **No offline rig before this one could have seen it**, because rigs 4–7
each supplied their own credential to their own containers, which is ADR
0065/0066's exact warning: *a proof that reaches the right end state by a route
the product does not take proves the end state is reachable, not that the product
reaches it.* Run 8 is built so the repair needs no change here — the drill
inherits the whole `PGBACKREST_*` namespace from the running database container.

**What the drill reads, and what it refuses to read.** The disposable volume and
the two containers are derived through `naming`; everything else — the repository
credential, the cipher pass and the rendered `pgbackrest.conf` — is **inherited
from the container that runs the archiver**, selected by an allowlist of
destinations and remounted read-only. The active secret generation changes on
every deploy, so any path into it is derived, never typed; re-deriving it here
would be a second authority that is right until the next `up`.

**D523's proof is the argument vector, not the source.** The rig puts a recording
`docker` on `PATH`, drives the command to completion in-process, and reads every
`--mount` it emitted. **The control arm makes `naming.restore_drill_names` return
the live volume** — a *derivation* producing the forbidden name, which is
precisely what a source scan cannot see — and requires exit 7 with no `docker run`
recorded. A seventh test asserts the subject and control arms differ in outcome,
so a 7 arriving for an unrelated reason cannot make the control pass while
measuring nothing.

**The rig is driven in-process rather than spawned, and the reason is a skip.**
The obvious shape was `skipif os.geteuid() != 0`, which would have left the three
assertions D523 exists for **skipped in every run** and green in the gate's
summary line — §7's *a skip is not a pass*, one layer up. Loading the command by
path and patching `os.geteuid` costs two lines and removes the skip.

**Three fields, three traps, and two of the traps produce well-formed values
(D562, D563).** `pg_control_checkpoint().checkpoint_time` is a real timestamp
from a catalog function on the right instance, measured **fourteen seconds**
after the recovery point, and it would look right on a fast machine. The server
log's *recovery stopping before commit* names the first transaction **not**
applied. The answer is `pg_last_xact_replay_timestamp()`, which agrees with the
log's *last completed transaction* to the microsecond and returns **NULL** on a
cluster that never recovered — a control that is free, exact, and reused as the
verdict's own first condition. And the achieved point and the published floor
arrive in **two different spellings of one instant**, which compared as strings
sort backwards; left alone that would have failed every correct drill with a
sentence about an inconsistency that was its own.

**`pgbackrest info` has no latest-recoverable-time field and the floor held
(D550, confirmed).** Newest backup stop `10:42:29Z`, achieved recovery point
`10:42:30.69Z` — later, by design, and the drill treats `achieved < floor` as the
inconsistency rather than `achieved > floor`.

**Battery: Q1–Q11, 11 of 11 killed** as `FAILED`, control green and unreachable in
every arm, all three mutated files restored byte-for-byte. The pre-flight caught a
bad anchor before it could report a false survivor. **Both first-pass survivors
were real, and one of them corrected an ADR (D567):** Q5 survived because the test
compared two constants — CLAUDE.md §6's named defect, with the mutation moving
both sides — and the repair is a literal `info` plus a stubbed `docker` that
reproduces pgBackRest's measured silence at `warn`. **Q7 survived because ADR
0151's claim was wrong**: the contexts are not what separate the drill's names
from the live volume, the stems are, and the ADR now says so with the survivor as
its evidence.

**Two implementation defects the run's own tests caught before anything else
did.** The disposability guard compared mounts by object identity against a
`@property` that rebuilds its value, so it refused **every correct plan** — found
by the subject arm, which is the case for having one. And `required_container_paths`
filtered the secret contract by `CURRENT_SESSION`, which is 9, so the drill looked
for the session-10 backup secrets and found none (D561) — found by the end-to-end
rig on its first execution, while the pure-logic tests passed session 10 by hand
and stayed green.

**Nothing is deployed, nothing has dialled R2, and `REC-PITR-001`, `REC-SAFE-001`,
`REC-SMOKE-001` and `REC-EVID-001` are still placeholders.** Their node ids live
in `tests/recovery/` and need a deployment; Run 9 replaces all five. Run 8 builds
the capability and proves offline what is provable offline.


### Run 8b — The archiver can authenticate. **Done.**

Not in the original build order. It exists because Run 8 found D558 by trying to
*use* the archiver, and because a Run 9 that proved a restore against an archiver
which cannot authenticate would be proving nothing.

- The credential route: `format: pgbackrest`, one option per file, mounted under
  pgBackRest's `config-include-path`.
- ADR 0153. Divergences D568–D574.

---

**What Run 8b measured, and what it changed.** ADR 0153. Rig 9, against the same
derived image and pgBackRest 2.59.1, with a posix repository standing in for R2.

**The gap was real and the route existed.** Measured, every arm with a control:

| arm | what | exit |
|---|---|---|
| K1 | a `.conf` under `/etc/pgbackrest/conf.d` supplying `repo1-cipher-pass` | **0** |
| K1 control | the same command with no include mounted | **37** |
| K2 | three files, each with its own `[global]` header | **0** |
| K3 | a file with no section header | **29**, *quoting the value* |
| K4 | an option set in the include **and** the rendered config | **31** |
| K6 | a partial credential set | **37**, naming the missing one |
| K7 | a `0400` file owned by root, container as 999 | **41** |
| K8 | a Compose secret with an **absolute** `target:` | lands exactly there |

**K2 is what makes the design possible.** Repeated `[global]` sections across
files concatenate cleanly, so the contract keeps its rule that it materializes
one value per file — a format packing three values into one would be a second
parser of a compound value, which ADR 0056 already refused for the storage pair.

**K4 turns a tempting future edit into a stated rule.** An option set twice is a
hard failure of *every* pgBackRest command including `archive-push`, not a silent
override — so rendering `repo1-cipher-pass` into `pgbackrest.conf` "for
completeness", beside the `repo1-cipher-type` that already is there, would stop
archiving on every project at once. A test reads the option names off the
contract and asserts the rendered config names none of them, with a control on an
option it *is* expected to set.

**K3 is a leak, and it reproduces on the product's own bytes (D569).** A
credential file that reaches the container without its `[global]` header makes
pgBackRest print `[029]: key/value found outside of section at line 1:` followed
by the value — to its console and its log, which for `archive-push` is the
postmaster's stderr. So `render_secret` refuses a value with a line break and
`recover_secret` verifies the header and the option, neither quoting anything.
The residual is in ADR 0153's consequences rather than implied.

**The closing arm is the one that matters, and it is the one four earlier rigs
did not run (L1).** Rigs 4–7 each handed their own containers a credential of
their own, which is ADR 0065/0066's exact warning — *a proof that reaches the
right end state by a route the product does not take proves the end state is
reachable, not that the product reaches it* — and it is precisely how D558
survived four runs. Arm L renders the three files with **`render_secret`**, at
the paths **`container_secret_path`** returns, for the consumers
**`secrets.required.yaml`** declares, against a config **`build_pgbackrest_conf`**
produced. Nothing is typed. **L1 exits 0**: the archiver can authenticate.
L2 (one header stripped) is 29 with the value in the output; L3 (one file
removed) is 37.

**Compose ignores the grant's `uid`, `gid` and `mode` (D571)** — it warns and
passes the host file's through. Nothing changes: the contract's fields are
applied by `materialize-secrets` on the host, which is what has always protected
the file. Recorded so nobody deletes them as redundant with a grant that ignores
them.

**Battery: R1–R8, 8 of 8 killed** as `FAILED`, control green and unreachable in
every arm, all three mutated files restored byte-for-byte. **Both first-pass
survivors were real.** R6 deleted the "a pgbackrest consumer must name an option"
validation and survived, because the real contract always names one and nothing
ever drove the refusal (D574) — §6's question 2, which the battery is the only
thing here that asks. **R7 moved `PGBACKREST_INCLUDE_DIR` and survived because
every assertion derived its expectation from that same constant** — the second
constant-vs-constant test in one session after Q5, and the rule that falls out is
in D573: *when a constant encodes a measured third-party fact, the test writes the
measured value.*

**A rig defect worth more than the arm it broke (D572).** Arm L2's conf.d path
was passed through an environment variable on a `wsl bash -lc` line and Git Bash
**path-converted it** to a Windows path; the Python found nothing, stripped
nothing, and the arm probed the unmodified files — reporting *"the value did NOT
appear"*. A leak check that comes back clean having done nothing is D557's shape
at its worst. The arm now asserts its own stimulus landed, fatally, before it
probes.

**Three secrets changed their container path** from `/run/secrets/<name>` to
`/etc/pgbackrest/conf.d/<nn>-<option>.conf`. Nothing else read them, because
nothing read them at all — which is the whole of D558. `bin/restore-test.py`
needed **no change**: it inherits mounts by destination from
`container_secret_path`, which is what ADR 0151 §2 was built for.

**Three passing tests were replaced by stricter ones, all ADR-authorised.** Two
in `test_secret_override.py` — one of which asserted
`f"{DIR}/{target}".startswith(DIR)`, true of any string — and
`test_the_repository_files_are_owned_by_the_postgres_uid`'s `format == "raw"`,
which was true and was not enough: the file was materialized, mounted and owned
correctly, and read by nothing.

**Still nothing is deployed and nothing has dialled R2.** What is closed is that
the archiver *can* authenticate, proved against a posix repository by the
product's own materializer. The endpoint, the token scope and a 403 remain
untested and need the trip.

### Run 9 — The proofs, and the schedule. **Done.**

- Replace all five placeholders with real tests in `tests/recovery/`.
- `REC-SAFE-001`'s two arms (D523). `REC-SMOKE-001`: the restored instance's
  `schema_migrations` matches the release's set, one RLS-protected read returns
  the drill owner's rows and only those, and one write RPC succeeds.
- The T1/T2 scenario on **beta**, in the frozen example domain, under a drill-only
  owner id: no new table, no migration, ADR 0003 does not move.
- The four systemd units, and `install_units`' glob (D522).

---

**What Run 9 built.** The five placeholders in `tests/recovery/test_future_pitr.py`
are gone and five requirements now have proofs; the drill's smoke checks grew the
three `REC-SMOKE-001` names; the four systemd units exist and `install_units`
globs them (D522). Divergences D575–D579.

**The five proofs have never executed, and this is the most important sentence in
this entry (D579).** The host is at `c0816e7` — Session 9's release — so every
test in that module is `live_host` and skips on environment absence, which is a
skip for the right reason (`requires_environment`, never `future`) and is still a
proof nobody has run. CLAUDE.md §8 names this as the oldest and most expensive
open item, and Session 9's trip found **three** never-executed proofs in one gate,
every one defective. So each of the five is written to fail loudly rather than
plausibly, and every one that disturbs the cluster asserts its own stimulus landed
first.

**What has executed is the logic underneath.** The offline rig in
`tests/contract/test_restore_test_command.py` grew from 57 to 64 tests and now
drives all six smoke checks end to end against the recording `docker` — including
the not-applicable path and a `schema_matches_the_release` arm that swaps one
version for another **keeping the count identical**, because a count would report
a cluster restored from another release as healthy. That is why `REC-SAFE-001` and
`REC-SMOKE-001` are registered with their offline arms beside their host ones
(D578): registering only the host half would leave the arm that has actually run
invisible to the evidence.

**`REC-SAFE-001`'s host arm does not read `system_identifier`, and that is the
whole of what rig 8 bought it.** A restore inherits it — `7677917767700738081` on
both live and drill — so a check reading it passes while reading the drill
instance, which is the single mistake this requirement exists to prevent (D566).
It compares the volume, the `instance_uuid`, the timeline and
`pg_postmaster_start_time()`; the last is the one that catches a restore which
took the live cluster down and brought it back, leaving every other field equal.

**`REC-WAL-001` breaks a live archiver and says what it does not know.**
`archive_command` is reloadable where `archive_mode` is not, but this deployment
sets it on the postmaster's command line and **whether `postgresql.auto.conf`
overrides a `-c` option here has not been measured**. So the test asserts the
break landed, fails loudly on a healthy cluster if it did not, repairs in a
`finally`, and asserts the repair — because a test that leaves a project's
archiver broken has done more damage than the requirement is worth.

**The timers use the seam that already existed (D576).** The trampoline validates
`%i` and passes the action through unexamined — *"a list here would be a second
definition of it, the kind that agrees right up until a release adds one"* — and
this run is that release adding one. `libexec/project-launcher` learns
`backup-full` and `backup-incr`; the units name no path inside any release; and
the scheduled action runs **`check` before `backup`**, because `check` is the only
thing here that tests the archiver end to end. Installed and **not** enabled, the
rule the edge and project units already follow: nothing can back up until a bucket
exists, a token has been issued out of band and the first full backup has been
taken by hand.

**D522 needed two assertions, not one.** A test reading the unit files would have
passed against the exact defect the row records, because the defect was in the
installer's glob. `test_no_unit_in_the_directory_is_left_uninstallable` is the
general form: the suffixes the glob covers must be *all* the suffixes present, so
a `.socket` added later fails here rather than being silently skipped.

**Two defects in the new tests, both caught by their first run (D577).** The glob
test searched the whole of `provision-host.sh` and matched an **earlier**
`for origin in` loop — the one installing `libexec/` — and reported that
`install_units` globs nothing, on a file where it had just been fixed. And
`configparser` interpolates `%`, so every `Unit=…@%i.service` parsed to a mangled
value. The repair for the first was not to stop scanning but to **name the subject
precisely and fail if it cannot be found**, which is the usable form of D464.

**`CURRENT_SESSION` stays 9 (D579).** CLAUDE.md says the bump moves together with
the five replacements in one commit; the constraint that encodes is
one-directional — the bump requires the replacements, not the reverse — and Run 10
owns `bin/session-10-check.sh`. A tree declaring session 10 without its gate script
is a tree whose gate cannot run. Verified rather than argued: the registry module
is green with the gate session at 9.

**Still nothing is deployed and nothing has dialled R2.** What Run 9 adds is that
the capability now has proofs pointed at it. Whether they pass is the trip's
question, and Runs 11+ budget three to five cycles for it.


### Run 10 — Publish. **Done.**

**One commit** (§ "The atomic commit" below), plus:

- `bin/session-10-check.sh`, derived from Session 9's — `readonly SESSION=10` is
  the only session literal; the Session 8/9 preconditions are replaced by this
  session's (the stanza exists, a backup set exists, archiving is healthy).
- `docs/session-10-operator-guide.md`, **derived from Session 9's by diff, not
  retyped**: D505 and D507 were both flags lost to retyping Session 8's.
- `docs/backup-operations.md`, including the account-boundary limitation the
  spec requires be stated in operations documentation.
- Regenerate the acceptance matrix, the product contract's marker block and the
  config bounds doc; `bin/migrate.sh freeze-lock` if a migration landed.

---

**What Run 10 published.** The atomic commit: `CURRENT_SESSION` 9 → 10, five
claims registered, `bin/session-10-check.sh`, `docs/session-10-operator-guide.md`,
`docs/backup-operations.md`, and the regenerated derived documents. Divergences
D580–D583.

**`CURRENT_SESSION` moved with the placeholder replacements, one commit apart and
by design.** D439/D484 pairs them because the placeholder policy and the overdue
policy are exact mirrors on the gate session — and the constraint binds one way:
the bump requires the replacements, not the reverse. Run 9 replaced them and Run
10 takes the bump, *together with the gate script*, because a tree declaring
session 10 without `bin/session-10-check.sh` is a tree whose gate cannot run
(D579). Both directions were verified rather than argued.

**Five claims, one per requirement, and no external arm was invented** (§7's rule
and ADR 0065). `point_in_time_recovery`, `restore_isolation`,
`restore_verification`, `recovery_evidence`, `wal_archiving_signal`. The splits
are D119's test — five different guarantees, each of which fails on its own —
rather than one `recovery` claim that would report a single verdict on a restore
that worked, could not be verified, and was reported with an invented number.
**`restore_isolation` and `restore_verification` name their offline arms beside
their live ones**, and `claim_mode` resolves both to `host` because only
`live_host` is a mode marker: D523 makes `REC-SAFE-001` two proofs, and the
offline one is the arm that has actually executed.

**The gate is derived by a script of named substitutions, and the operator-facing
text is a second pass (D581).** 321 of 874 lines changed. Changing only
`readonly SESSION=10` would have left `--help` telling an operator to merge
`--session 9` into `evidence/session-09.json` — and D213 is the record of thirteen
proofs gated on a flag missing from exactly such a documented invocation. What is
*not* substituted is Session 9's byte for byte, which is the half retyping loses:
the per-release bundle name (D504), `git rev-parse FETCH_HEAD` *before* the
checkout, the venv sync (D384, D297), and `op@` as the external destination
(D466).

**The gate's precondition is this session's, not Session 9's (D582).** There is no
migration to check — Run 5 measured that all five backup grants are
bootstrap-plane — so what it checks is that the stanza exists, a full backup
exists, and the archiver is not failing. All three come from
`backup_report.backup_state`, the same function the deploy publishes from, so the
gate and the deployed document cannot disagree about what a repository's report
means. **Nothing reads `pgbackrest info`'s exit code** (D548).

**The acceptance matrix had been lying for nine sessions (D580).** D526 predicted
that the summary would read *"placeholders owned by Session 10"* beside five live
requirements; what it did not say is that the document **already** said
"placeholders owned by Session 2" beside thirteen shipped ones, and had since
Session 2. `status = "active" if session == 1` was written when 1 was the only
shipped session and never revisited — in a file whose header says *"GENERATED
FILE. Do not hand-edit"*, which is exactly the file nobody reads closely. The fix
moved `acceptance_session()` into `agentic_postgres` rather than copying the rule
into `bin/`, because two implementations of it would have been D264 one layer up.

**The bump arms no Compose profile, and that is stated rather than omitted
(D583).** Every previous bump armed one and every previous guide named the
container that would now start. This one arms **step 6c**, which is a larger
prerequisite than any profile: a deploy from here on needs three provider secrets
and a bucket an operator created out of band, and it will fail on purpose without
them.

**`docs/backup-operations.md` states the account boundary the spec requires**, and
states it as a limitation rather than a footnote: everything is in one Cloudflare
account — the application bucket, the backup bucket, both tokens and the DNS — so
the backups are inside the blast radius of the thing most likely to take the site
down. Cross-account replication, a second provider and an offline copy are absent
by decision. The same section names the two other things the plane does not
protect against: a compromised database container, which holds the credential
*and* the cipher pass (ADR 0147's residual), and destruction of
`pgbackrest_repo_cipher_pass`, which orphans every backup ever taken while every
check in this repository still passes (D538).

**No migration landed, so no `freeze-lock`.** Both clusters stay at 21.

**Session 10 is code-complete and entirely undeployed.** The host is at
`c0816e7`, running Session 9 at outputs v12, while this tree is at v13 with an
archiver, a drill, four units and five claims that have never run. Runs 11+ are
the trip, and they budget three to five deploy-and-gate cycles for a reason that
is now longer than it was: an operator has to create a bucket and a token before
the first deploy, the first deploy fails without them on purpose, and the first
full backup is a command at a TTY that the gate refuses to start without.


### Runs 11+ — The host trip

**Run 11 has started. What is done, and what needs a human at a TTY.**

Done, over SSH as `op`, with no root and no Docker:

- **The release is on the host at `bd0b4f0`**, transported by `git bundle` +
  `scp` under a per-release name, with `git rev-parse FETCH_HEAD` confirmed
  **before** the checkout (D504). Host was at `c0816e7`.
- **The venv is synced** and `bin/lock-dev-deps.sh --check` passes on both sides.
  It was failing on both before this run — upstream drift, `mcp` 1.29.0 → 1.29.1
  and `platformdirs` 4.11.3 → 4.11.4 — and it stops the gate at step 2 before
  any test runs.
- **All four projects re-render**, which is D462/D383's requirement and not two.
- **D546 is closed, and closed for the right reason** (D585). The first reading
  of those four renders was wrong: both real manifests carry
  `backup: enabled: false`, so they rendered the feature *off*. A copy of
  alpha's own manifest under a slug of its own, with backups **on**, renders at
  exit 0 at schema v13 — the fifth claimant fits.
- **Disk headroom measured, and it was never measured before**: 28 GB available
  of 38 GB (22% used), 3814 MB RAM with 2209 available. The drill needs a second
  copy of the cluster; there is room.
- **The deployment is healthy at Session 9's release** — 16 containers, all up,
  and both `postgres` containers are on `internal` **alone**, which is the
  pre-Session-10 state confirmed from the host rather than assumed.

**The two R2 buckets now exist.** Created 2026-08-26 with the operator's own
authenticated `wrangler` against account `ddfa208f…`, which is the same account
`storage.account_id` already names:

    apg-alpha-dev-backup    created 2026-08-26T04:21:56Z
    apg-beta-dev-backup     created 2026-08-26T04:22:00Z

That is the operator's step being taken by the operator's tooling, out of band —
it is not this repository creating a bucket, and ADR 0110 is unchanged.

**The R2 API tokens are NOT done and could not be**, for two independent reasons
worth keeping apart:

- *Capability.* The available Cloudflare credential is wrangler's OAuth token,
  and it cannot read or create account API tokens: both
  `GET /accounts/{id}/tokens` and `.../tokens/permission_groups` answer
  **`9109: Unauthorized to access requested resource`**. Creating one needs a
  credential with *API Tokens: Edit*, which this machine does not hold.
- *Handling.* Even with the permission, an R2 token's secret access key must not
  be fetched into a terminal, a log or an assistant's context — the standing
  rule that no secret value reaches a log, and the operator guide's own "do not
  paste the secret into a terminal". The safe shape, if a permitted credential
  ever exists, is a **script** that creates the token, computes the SHA-256 the
  secret access key is defined as, writes both to `0600` files, sets them with
  `infisical secrets set NAME=@file` — which keeps the value out of process
  arguments — and shreds the files, printing nothing but a verdict.

Needs a human at a TTY, in this order:

1. **Issue an R2 API token per bucket, at Cloudflare**, and paste both halves
   into the provider at `/backup`. The buckets are ready; only the tokens are
   outstanding. Nothing here can do it (ADR 0110), and this run confirmed that
   is a permission boundary and not a missing feature.
2. **Turn `backup.enabled` on** in `project.alpha.yaml` and `project.beta.yaml`
   with `bucket` and a **quoted** `account_id` (D585), then re-render.
3. `sudo ./deploy.sh … --through-session 10`, per project. Step 6c creates the
   stanza and runs `check`, and a check failure fails the deploy on purpose.
4. `sudo bin/backup.sh --outputs … backup --type full`, per project. The gate
   refuses to start without it.
5. `sudo bin/session-10-check.sh --mode host …`, then `--mode external` off-host,
   then merge.

Budget **three to five deploy-and-gate cycles**, not one. Each of the following
is a place a trip stalls:

Budget **three to five deploy-and-gate cycles**, not one. New this session, and
each is a place a trip stalls:

- An operator creates the R2 bucket and token **before** the first deploy, out of
  band, once per project.
- The first deploy of each project publishes `backup: unavailable` and exits 0.
  That is convergence, not failure (D326).
- The stanza is created and checked by the deploy's step 6c, but the **first full
  backup** is an operator command at a TTY, and the drill cannot run before it.
- The drill needs disk headroom that has never been measured on this host.
- `apg-diag` cannot read `postgres` logs any more than it can read `auth`,
  `storage` or `mcp` (D380) — the fourth session in a row this will send an
  operator to a terminal.

---

## 6. The backup and recovery surface

Two commands, four units, one repository per project.

| Command | What it does | Where it runs |
|---|---|---|
| `bin/backup.sh stanza-create` | Creates the stanza in the repository | Deploy step 6c, or an operator at a TTY |
| `bin/backup.sh check` | Proves archiving and the repository both work | Deploy step 6c, and the timers |
| `bin/backup.sh backup --type full\|incr` | Takes a backup | The two timers |
| `bin/backup.sh info` | The repository's own report | Operator, and `observe_backup` |
| `bin/restore-test.sh --target-time … --project-dir …` | The disposable drill | Operator at a TTY, and the host gate |

**What a restore never touches:** the `postgres-data` volume, the running
`postgres` container, the project's network aliases, the edge, any secret
generation, and any object in the *application* R2 bucket. The disposable target
is created by the command, named by derivation, and removed by a `trap`.

**What the evidence document never carries:** a credential, a cipher pass, a
connection string, a bucket URL with a signature in it, or any row of restored
user data. It carries identifiers, timestamps, an LSN, counts and verdicts.

**What is deliberately absent:** a portable `pg_dump` export, cross-account
replication, a standby, and automated failover. Recovery here is restore-based
and has a real RTO — `docs/product-contract.md` has said so since Session 1.

---

## 7. Evidence and claims

Unchanged: a claim's verdict is computed from the registry's node ids and JUnit
results, never hand-entered, and **a skip is not a pass**. Host and external
halves are written separately and merged by
`bin/write-session-evidence.py --session 10`, and **both halves must describe the
same release** or the merge refuses.

Session 10's claims are new entries in `evidence_claims.CLAIMS`, each resolving
to exactly one mode with at least one live proof. All of them are `host`: there
is nothing about a backup repository a stranger on the public internet can
measure, and inventing an external arm to make the shape symmetric would be a
proof that reaches an end state by a route the product does not take (ADR 0065).

**The two inherited red claims are Session 5's.** Session 10 does not close
`api_authorization` or `bootstrap_identity` and must not appear to. If the
rotation window is held during this session it closes them; if it is not, this
evidence carries them red for the same stated reason, and **this becomes the
fifth session to close on that sentence.**

**What Session 10 does not close:**

- A portable `pg_dump` export. P2, and the spec conditions it on PITR already
  being proven. No registry id names it, so shipping it would close nothing and
  add a second unproven format to a session whose thesis is that one proven
  chain is worth more.
- `OPS-LOG-001`, which is Session 11's.
- `app_private.agent_audit`'s retention. Session 9's handoff points it here and
  ADR 0135's consequences name it. **This session should state whether it takes
  it or passes it on, rather than leaving the pointer dangling a second time.**

---

## 8. Security invariant matrix

| Invariant | Control | Proof |
|---|---|---|
| The repository is encrypted at rest by us, not only by the provider | `repo1-cipher-type=aes-256-cbc`, cipher pass a separate secret from the credential | The rendered config, and a repository object that does not parse as PostgreSQL data |
| Application services cannot reach the backup bucket | Separate bucket, separate token; `storage`'s consumers name neither backup secret | A measured 403 in both directions, and the secret contract's per-consumer grants |
| The database's egress reaches R2 and nothing else | A `backup` network with no Traefik and no published port | The rendered Compose model, and the firewall reconciliation |
| A restore cannot touch the live volume | Derived disposable names; the live volume is never an argument | `REC-SAFE-001`, offline **and** on the host (D523) |
| A restore that cannot be verified is a failed restore | The command queries the restored instance before it reports success | `REC-SMOKE-001` |
| A recovery point is achieved, not requested | Requested and achieved recorded as separate fields | `REC-EVID-001` |
| A recovery time is measured | Wall time taken by the command around the restore | `REC-EVID-001`, D529 |
| An archiving failure is loud | `pg_stat_archiver`, the healthcheck, a non-zero command | `REC-WAL-001` |
| The backup identity is not an application identity | `backup_user`, activated with its own credential and connection limit | `test_only_the_activated_roles_may_log_in`, re-derived |
| No secret value reaches a log, an argument or an image layer | Mounted `0400` files, `format: raw`, the secret-leakage scan | `SEC-SECRET-001`, unchanged |
| Two projects cannot share a repository | Stanza, prefix, bucket and network all in `ISOLATED_FIELDS` | `collision_count`, before any cluster exists |

---

## 9. Risks and stop conditions

**Stop and ask** rather than proceeding, when:

- the restore path would be simpler if it mounted the live volume read-only;
- an assertion about the live volume being untouched would have to be relaxed
  rather than re-derived;
- the connection budget would have to be raised instead of divided;
- `--render-only` stops working with no host and no root;
- a released migration would have to be amended;
- a Session 1–9 claim goes red and the fix would weaken a passing test;
- the drill's cleanup cannot find its target and widening the search looks
  reasonable.

**The failure mode this session is most exposed to** is the one this project
keeps producing: *a value that looked measured and was not.* This session's whole
deliverable is a set of measurements — an achieved recovery point, an elapsed
time, a latest recoverable bound, a schema version — every one of which has a
plausible wrong value that would pass unnoticed. A restore that lands at the
wrong second still starts, still answers queries, and still reports success.

The five standing questions:

1. What would have to break for this test to go red?
2. Has it run at all, in this environment, since the thing it measures changed?
3. Whose identity, and through which tool, does the proof run — and are they the
   ones production uses?
4. When a defect class was fixed, **which side got the fix** — product or proof?
5. When a decision is implemented, **which of its callers got it?**

**Question 5 wrote three of this plan's rows before a line of code was
touched** — D519 (`retain_full` validated and reaching nothing), D522 (a unit
directory globbed for one suffix), and D530 (a reserve whose comment already
claims a budget nobody charged). **Question 2 is the one with no tooling behind
it**, and this session adds proofs that can only ever run on a host — which is
exactly the population Session 9's trip found three defects in.

---

## 10. Open items carried in

- **Nothing knows which proofs have never executed.** D211–D214, six sessions
  unbuilt, and Session 9's trip paid for it three times in one gate. **Every
  `REC-*` proof this session writes is in that population.**
- **The rotation window.** The only thing keeping two Session 5 claims red, four
  sessions running.
- **The signing-key cutover.** ADR 0088, unblocked since Session 6. Four
  verifiers now; after any phase that changes the published set, recreate every
  one.
- **`apg-diag` cannot read `auth`, `storage` or `mcp` logs** (D380) — and cannot
  read `postgres` either, which this session makes matter.
- **`app_private.agent_audit` grows without bound**, as do secret generations.
  Session 9 pointed both here.
- **A proof can flip on one release and nothing tells that from a regression**
  (D511), deliberately unrepaired, owned by API-AUTH-002.
- **`revoked → active` answers 200** (D503); nobody has decided whether it should.
- **`requirements-dev.in` pins nothing** — six reddened gates, always upstream
  drift. `bin/lock-dev-deps.sh --update`, committed separately.
- **The environment is not verified against the lock** (D297).
- **`--ssh-destination` is not derivable** (D466); the gate needs `op@` and
  nothing checks it.
- **`tests/deployment/conftest.py` is past 2,100 lines.**
- ADR 0019's CI job is unbuilt, and D525 is what that costs.

---

## 11. Session 11 handoff

Session 11 receives an encrypted repository per project, a WAL stream, a
scheduled full and incremental backup, a restore command that has been run
against a real deployment, and an evidence document that says how long it took.

It receives three narrowings. **A restore is disposable by construction, not by
care** — the command cannot name the live volume, and that is a property rather
than a rule. **A recovery point is achieved, not requested**, and the two are
recorded separately. **A backup that succeeded is not a recovery that works**,
which is why `REC-PITR-001` and `REC-SMOKE-001` are separate ids.

Session 11 is **deployment, operations and log correlation** — `DEP-001`,
`DEP-002`, `DEP-PRE-001`, `OPS-001`, `OPS-LOG-001`. Its placeholders are in
`tests/contract/test_future_deployment.py`. `OPS-LOG-001` spans ingress → API →
agent → audit, and Session 9's request id stops short of ingress deliberately
(D478); Session 10 adds a fourth thing worth correlating — a backup and a restore
both write operational records nothing joins to a request.

**And it inherits what this session could not measure:** how long a restore takes
when the cluster is large, and how much disk that needs. Both are measurements
of this deployment on this day, and neither is a bound.

---

## Appendix — what to consult, and what to measure instead

**Consult:** `docs/decisions/README.md` (143 ADRs, indexed; next free **0144**) —
for this session especially **0002** (single-authority derivation), **0017** (the
stub lifecycle, whose fourth and last application this is), **0063/0133** (why a
service is deferred, and the two reasons), **0070/0099** (the connection budget,
and why a division is a function), **0096** (re-derive from the event, do not
restate), **0103** (`origin`, and why it is a second field), **0106** (the image
never assembles a URL), **0110** (bucket administration is out of band),
**0134** (a grant assertion reads the catalog; a reach assertion sets the role).
Behind them: 0003 (the frozen domain), 0045/0089 (what a claim is), 0065/0066 (a
proof takes the product's route). `docs/session-09-operator-guide.md` as the
parent of this session's — **by diff**. `docs/plans/session-09-implementation-plan.md`
§5 "Runs 9+", which is the best single account of what a trip costs. §1 of this
document.

**Measure instead of consulting**, every time: what a package manager installs
into a specific base image, what a binary links against, what the postmaster does
with a failing archive command, what `pgbackrest info` actually prints, what a
container on a given network can reach, and whether a proof has ever run.

**Before measuring how a third party behaves, grep the plans for it.** Session 8
Run 8 measured how PostgreSQL grants `EXECUTE` on a new function; Session 3 had
measured it three sessions earlier in more detail (D57, D262). Every ADR is
indexed; **nothing indexes the ~530 measured facts in the divergence tables by
subject**, so the pointer has to be a `grep`.

**Never write a measurement you did not run** (D267). In a session whose entire
output is measurements, this is not a stylistic rule.
