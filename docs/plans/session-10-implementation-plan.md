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

**Next free number after this table is D541.**

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

### Run 5 — Activating `backup_user`, and the fifth claimant

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

### Run 6 — `bin/backup.sh`, and the deploy's step 6c

- `bin/backup.sh` + `bin/backup.py`: `stanza-create`, `check`, `backup --type
  full|incr`, `info`, `expire`. `--help` exits 0 with no host; the CLI contract's
  preamble, exit-code and no-secret-argument rules apply.
- The deploy gains **step 6c**, after step 6 (the cluster exists and
  `backup_user` can log in) and before step 7 (observe and publish): create the
  stanza if absent, then `check`. A `check` failure is a deploy failure with a
  named reason, not a warning.
- Retention comes from `retain_full`, applied once, in the config — never
  restated in a command (D495, D463).

### Run 7 — A WAL archiving failure is visible

- Break the archive deliberately (a revoked credential arm and a wrong-prefix
  arm), and prove the signal: `pg_stat_archiver.failed_count` moves,
  `last_failed_wal` names the segment, the healthcheck goes unhealthy, and the
  operator command reports non-zero. **The control is the same assertion against
  a healthy archive in the same invocation.**
- `REC-WAL-001`.

### Run 8 — `bin/restore-test.sh` leaves `FUTURE_STUBS`

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

### Run 9 — The proofs, and the schedule

- Replace all five placeholders with real tests in `tests/recovery/`.
- `REC-SAFE-001`'s two arms (D523). `REC-SMOKE-001`: the restored instance's
  `schema_migrations` matches the release's set, one RLS-protected read returns
  the drill owner's rows and only those, and one write RPC succeeds.
- The T1/T2 scenario on **beta**, in the frozen example domain, under a drill-only
  owner id: no new table, no migration, ADR 0003 does not move.
- The four systemd units, and `install_units`' glob (D522).

### Run 10 — Publish

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

### Runs 11+ — The host trip

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
