# Session 2 — Implementation Plan

**Deliverable location note:** plan mode restricts me to this file. The first action of Run 1 is to copy this document verbatim to `docs/plans/session-02-implementation-plan.md` and commit it as commit 1. Nothing else in Run 1 starts before that copy exists. This mirrors the Session 1 plan's own opening.

**Context.** Session 1 is committed at `d3db6df` on `main`, clean tree, gate passing. The Session 2 runbook was written before that code existed and contradicts it in twenty-six places. This plan resolves each conflict explicitly, states what Session 2 adds that the runbook does not cover (the execution split across three environments, the lockout safety plan, the secret leak surface), and orders eighteen phases into eight runs each of which ends with `bin/session-01-check.sh` exiting `0` on a clean tree.

Everything here is additive to the runbook. Where I disagree with it I say so under the relevant heading.

---

## 1. Runbook divergences

Twelve were named in the brief. Fourteen more were found reading the working tree. **D13, D14, D15 and D16 are the ones that break `bin/session-01-check.sh` outright** and should be read first.

| # | Runbook says | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D1** | Phase 0: create ADRs `0004`/`0005`/`0006`. | `0004-version-lock-format.md` exists (decision **A**). Session 1's plan §2 also *reserves* `0005-route-reservation`, `0006-capability-scopes`, `0007-bounds-authority`, `0008-sensitive-key-policy` — decisions **B**, **C**, **E**, **F** name them as source of truth — **but those four files were never written.** | Session 2 ADRs are **`0009-host-and-edge-plane`**, **`0010-secret-materialization`**, **`0011-provider-bootstrap-state`**, plus the ADRs D5–D20 below require. Separately, backfill `0005`–`0008` from the decision-log text already in the Session 1 plan, and add `0004`–`0011` to the ADR index in `docs/decisions/README.md`, which currently stops at `0003`. | `0005`–`0008` are cited as authority by code comments and by the decision log; a dangling citation is a documentation lie, and the content already exists so backfilling is transcription, not new decision-making. | n/a |
| **D2** | §6 adds `project.alpha.example.yaml` / `project.beta.example.yaml`; §5.5 also creates real `project.alpha.yaml` / `project.beta.yaml`; §7/§8.10 assume `.generated/alpha-dev`. | `project.example.yaml` (`fixture-alpha`) and `project.second.example.yaml` (`fixture-alpine`), referenced by `bin/session-01-check.sh`, `test_repository_contract.py` (REQUIRED_PATHS + the scan-scope guard), `test_output_schema.py`, `test_render_isolation.py`, `test_project_manifest.py`, `test_cli_contract.py`, `test_render_atomicity.py`, `test_naming.py`, README. | **Add no new example manifests and rename nothing.** The two real manifests `project.alpha.yaml`, `project.beta.yaml`, plus `host.yaml` and `capabilities.yaml`, are **gitignored operator inputs**, never committed — which §5.4 itself demands ("only redacted examples are committed"). `host.example.yaml` and `secrets.required.yaml` *are* committed. | `fixture-alpha`/`fixture-alpine` share an 11-character prefix on purpose and `test_similar_prefixes_actually_exercise_the_comparison` fails if that stops being true. `alpha`/`beta` exercise nothing. Renaming costs ~40 references across 8 test modules and the gate to buy a weaker fixture. | no |
| **D3** | §8.10: `--runtime up`, `--edge` modes. | `bin/compose.sh` `FORBIDDEN="up run start create restart exec attach cp"` → exit `10`; `test_container_starting_subcommands_are_refused` asserts `10` **and** the literal string `"Session 1 starts nothing"` in stderr for all eight. | Refusal stays the **default**. Gating becomes: no `--runtime`/`--edge` → exit `10` for all eight, message changed to a stable substring (`"requires --runtime"`); `--runtime` without `EUID==0` → exit `3`; `--runtime` with a subcommand outside the runtime allowlist (`up`, `down`, `restart`, `ps`, `config`, `logs`, `build`) → exit `10`; `--edge` binds the model to `infra/edge/compose.yaml` and refuses `-v`/`--volumes`. The test is **extended**, not deleted: same eight parameters still assert `10`, plus new cases for each gate. | The assertion that survives is the one that matters — "these subcommands do not start a container by accident". The stderr-substring assertion is the only genuinely load-bearing edit. | **yes** |
| **D4** | Wrapper runs under `sudo` and under systemd. | Decision **T**: `env -i` + `PATH HOME USER DOCKER_HOST DOCKER_CONTEXT DOCKER_CONFIG DOCKER_CERT_PATH DOCKER_TLS_VERIFY`; `test_wrapper_uses_an_allowlist_not_a_denylist` asserts `env -i` present and `env -u` absent. | **`KEEP_VARS` is unchanged.** `SUDO_UID`/`SUDO_GID`/`SUDO_USER` are read by the wrapper *from its own environment* to derive the source owner (§4.2) and are deliberately **not** forwarded to `docker` — Docker has no use for them. Anything the runtime/edge path needs (`DOCKER_BUILDKIT=1`, `BUILDKIT_*`, `HOME=/root` under systemd) is **set explicitly** by the wrapper, never inherited. Systemd units set `HOME` and `PATH` in the unit file, not via the allowlist. | Setting a value is strictly stronger than allowlisting an inherited one, and it keeps decision **T**'s bounded-and-provable property intact. Extending the allowlist is reserved for Session 1 stop condition 4 — per variable, with a written reason. | no |
| **D5** | Phase 3: `outputs.json` v2 with `rendered`/`deployed` kinds; rendered fragment shows `secrets: {status, required_names}`. | `schema_version` `enum: [1]`, `additionalProperties: false` at every level, no `kind`; `secrets: {namespace}` is in `test_render_isolation.MUST_DIFFER` and `evidence.ISOLATED_FIELDS`. | Schema becomes `oneOf` on a required `document_kind` const, `schema_version` `enum: [2]`, `additionalProperties: false` preserved on both branches. **`secrets.namespace` is kept and `status`/`required_names` are added beside it** — the runbook's fragment is illustrative and silently drops a field two Session 1 contracts depend on. `routes.health` is an object `{status, url}` on both branches; `routes.{rest,app,mcp,docs}` stay strings (heterogeneity under `routes` accepted deliberately so rendered and deployed stay structurally parallel). Deployed-only fields (`source_commit`, `host`, `edge`, `tls`, `bootstrap`, `runtime`) exist only on the deployed branch. | | **yes** |
| **D5b** | "`output_migrations.py` can structurally migrate v1 → v2 rendered." | `.generated/` is gitignored and rewritten transactionally on every render. | **Nothing under `.generated/` is migrated in place.** The migration path for a working tree is *re-render*. `output_migrations.py` exists for archived/third-party v1 documents and is contract-tested against a committed `tests/fixtures/outputs-v1.json`. It never produces a `deployed` document. The host path `/var/lib/agentic-postgres/projects/…` has no v1 history, so nothing there migrates either. | A migrator that rewrote generated output would break the "rendered bytes are a pure function of the inputs" contract. | no |
| **D6** | Deployed state carries timestamps, fingerprints, host facts. | `test_no_timestamp_reaches_rendered_output` walks the whole document rejecting `*_at`, `*_time`, `*timestamp`; determinism asserted on bytes. | Follow decision **U**'s precedent, but exclude by **document kind** rather than by field name: `document_kind: rendered` stays fully deterministic and timestamp-free, and the existing test is unchanged and re-scoped to rendered documents only. `deployed` is never byte-compared and gets its own tests (secret-free, schema-valid, mode `0600`, real values not angle-bracket placeholders). | Kind-based exclusion is one boundary; a growing field-name allowlist is a slope. | **yes** |
| **D7** | Probe labels need `PROJECT_KEY`, `PROJECT_ENVIRONMENT`, `PROJECT_DOMAIN`, `ROUTER_SAFE_NAME`, `ACME_RESOLVER_NAME`, `BASELINE_MIDDLEWARE_CHAIN`. | Decision **M**: `compose.env` is exactly `COMPOSE_PROJECT_NAME`, `EDGE_NETWORK_NAME`, `INTERNAL_NETWORK_NAME`, `POSTGRES_VOLUME_NAME`, tested as an exact set and disjoint from `versions.env`. | **Split by provenance.** Project-derived values (`PROJECT_KEY`, `PROJECT_ENVIRONMENT`, `PROJECT_DOMAIN`, `ROUTER_SAFE_NAME`) join `.generated/{key}/compose.env` → exact set of **eight**. Host-derived values (`ACME_RESOLVER_NAME`, `BASELINE_MIDDLEWARE_CHAIN`) go in the **root-owned** `/var/lib/agentic-postgres/projects/{key}/compose.env`, which §7 already specifies, passed as a **third** `--env-file` only in `--runtime` mode. Disjointness is asserted three ways, not two. | `host.yaml` is not one of the four digests in `outputs.inputs`. Putting a host-derived value into a rendered file would make the deterministic render depend on an undigested input. That is the actual reason the split exists. | **yes** (amends **M**) |
| **D8** | `/etc/agentic-postgres/`, `/opt/agentic-postgres/releases/`, `/var/lib/agentic-postgres/projects/{key}/`. | `generated_directory` pattern `^\.generated/[a-z0-9-]+$`. | **Pattern untouched.** `project.generated_directory` stays repo-relative on both branches. Absolute host paths appear only in **deployed-branch-only** fields with their own anchored absolute patterns (`^/var/lib/agentic-postgres/projects/[a-z0-9-]+$`, `^/opt/agentic-postgres/releases/[0-9a-f]{40}$`). | Loosening one pattern to carry two meanings is how a path-traversal check dies. | no |
| **D9a** | Phase 16 lists 12 new IDs. | Registry owns `SEC-NET-001` and `SEC-SECRET-001` at session 2. | **`SEC-NET-001` is proved in Session 2, not retargeted.** The proof is exactly Session 2's own work and is *stronger* than the Session 4 version: no service publishes any host port but Traefik's 80/443 (resolved Compose model + `docker ps` port metadata), `DOCKER-USER` drops new forwarded public traffic to anything else, an external full-TCP connect scan of the public IPv4 (and IPv6 when configured) finds nothing on 5432, and both rendered documents still report `database.direct.status == "unavailable"`, `url == null`. Marked `security`+`p0`+`live_host`+`external`. | "No route reaches it" is provable when the thing does not exist and no path could carry it. Retargeting to Session 4 would move a goalpost to avoid work Session 2 already does. | no |
| **D9b** | Phase 16's table. | — | The runbook's list **omits `SEC-NET-001`**, the one Session 2 requirement the registry already owns. Internal inconsistency; the plan adds it. `DEP-ISO-001` stays at Session 12 and its placeholder in `tests/contract/test_future_deployment.py` is **not touched**. `DEP-ISO-002` is added at session 2. Net: 11 new IDs + 2 activated. | | no |
| **D10** | §6 wants `tests/deployment/` and `tests/external/`. | Session 1 put deployment placeholders in `tests/contract/test_future_deployment.py` — "the marker, not the directory, decides what runs". | **Adopt both directories** for *new* Session 2 tests; leave `test_future_deployment.py` exactly where it is. The **marker remains the selector** in every `-m` expression and in both gates; directories exist only to make the three execution environments legible. `pytest.ini` gains `live_host` and `external`; `testpaths = tests` already covers new directories. | Session 2 introduces three genuinely different execution environments; grouping by environment aids the reader without changing what runs. | no |
| **D10b** | Live/external tests. | `test_all_future_tests_are_skipped_in_a_normal_run`; `test_no_placeholder_body_calls_skip`. | Environment-absent tests skip via `pytest.mark.skipif` on a **required environment variable** (`APG_PROJECT_A_OUTPUTS`, `APG_LIVE_HOST`), never via `future` and never unconditionally. `future` means "no one has written this"; `skipif` means "written, environment absent". A contract test asserts every `live_host`/`external` skip condition reads an environment variable. External test modules must be importable with no network at import time (`test_collection_succeeds_for_the_whole_suite` collects everything). | | no |
| **D11a** | §6: lock a Docker socket-proxy image and "any additional build base used by the edge probe". | `versions.env` locks 9 images incl. `TRAEFIK_IMAGE`, `INFISICAL_IMAGE`; `PYTHON_RUNTIME_IMAGE` is `python:3.12-slim@sha256:…`. | Add **`DOCKER_SOCKET_PROXY_IMAGE`** only. The edge probe builds **from `PYTHON_RUNTIME_IMAGE`**, already digest-pinned — no new base. Also record **`TRAEFIK_VERSION`** at `--update` time so `--check` can assert a semver floor offline. | | no |
| **D11b** | §7: "Install the exact Infisical CLI version/checksum"; Phase 13 §3: "using the direct API client in `src/agentic_postgres/infisical_client.py`". | `INFISICAL_IMAGE` locked but unused. | **Direct HTTPS API client only. No Infisical CLI is installed on the host.** `INFISICAL_IMAGE` stays in the lock inventory, unused in Session 2. | The runbook specifies two mechanisms for one job. The API client is the one Phase 13 actually describes step by step, and it removes a per-arch binary + checksum surface from the host entirely. | no |
| **D11c** | §4.7: "the lock checker must prove the locked Traefik supports `queryParameters.defaultMode: drop`". | `--check` is fully offline by decision **A**. | Offline, `--check` asserts a **semver floor** on the recorded `TRAEFIK_VERSION`. The real proof is a `live_host` test: issue a request carrying a random query-string sentinel and assert the sentinel is absent from the access log. State plainly that the offline check is a floor, not a proof. | A digest cannot tell you what a config key does. | no |
| **D12** | §5.2-era "Compose v2"; VPS installs whatever Docker's repo ships. | Decision **A**: `COMPOSE_MINIMUM_VERSION=2.24.0`, semver `>=`. Dev machine runs v5.1.3. | Floor unchanged. **Consequence to carry:** the gate now runs on two Compose majors. Every Compose assertion must be structural, never shape-dependent on `config` output; the observed version is recorded in evidence on both sides. Concretely, **complete label keys are rendered into the root-owned runtime override** rather than interpolated (`traefik.http.routers.${X}.rule` is not portable to the floor) — the runbook's own Phase 11 note agrees. | | no |
| **D13** | *(found)* Session 2 leaves project containers running. | `bin/session-01-check.sh` step 7 loops **every** `.generated/*/` with a `compose.env` and fails if `bin/compose.sh <dir> ps --quiet` is non-empty. After any Session 2 deploy, `.generated/alpha-dev` exists and its probe **is** running → **gate exits 1**. | Step 3 captures the two directories it just published; step 7 iterates **exactly those**. Fixture identities stay out of `bin/` (which `test_repository_contract.SCAN_ROOTS` scans) because the selection comes from what step 3 rendered, not from a literal. `test_compose_contract.py::test_no_container_is_running` is parametrized on the two fixture directories and needs **no change**. | The step always meant "no Session 1 fixture container is running". Making that precise is a narrowing of scope, so it gets an ADR; the Session 2 gate takes over the broader claim. | **yes** |
| **D14** | *(found)* Session 2 projects disable storage and backup (out of scope until Sessions 7/10). | `evidence.collision_count` compares `("storage","bucket")` etc. across **all** rendered projects. With storage disabled, `naming.derive` returns `None`, and `None == None` counts as a collision → `status: "failed"` → `write-session-evidence.py` exits `5` → **gate step 8 fails**. Latent in Session 1 only because both fixtures enable both. | Fix `collision_count` to ignore pairs where **both** values are `None`, and add two tests: two storage-disabled projects → 0 collisions; two projects sharing a non-null bucket → still a collision (guard the guard). | Two projects both having no bucket is not an identity collision. This is a genuine Session 1 defect that Session 2 is the first thing to reach. Because it reduces what counts as a failure, it gets an ADR rather than being filed as a bug fix. | **yes** |
| **D15** | *(found)* Activating `SEC-NET-001`/`SEC-SECRET-001` removes their `future` markers. | `bin/session-01-check.sh` hard-codes `export APG_ACCEPTANCE_SESSION=1`. With that, `test_every_later_requirement_has_a_placeholder` (`target_session > gate_session`) demands a placeholder for every session-2 requirement — which we just removed → **gate fails**. Conversely, flipping `CURRENT_SESSION` to 2 *before* removing the markers fails `test_no_requirement_at_or_before_the_gate_session_remains_future`. | The gate derives the value from the package instead of hard-coding it, and a contract test asserts no literal session number remains in `bin/session-01-check.sh`. **The `CURRENT_SESSION` flip, the marker removal, and this gate edit are one atomic commit** — separated in either order, the tree is red. `test_session_one_requirements_are_active` is hard-coded to session 1 and still proves Session 1 unconditionally, so nothing is weakened. | | **yes** |
| **D16** | *(found)* §5.5 creates `project.alpha.yaml`, `host.yaml`, `capabilities.yaml` in the checkout. | `bin/session-01-check.sh` step 1 fails on **any** untracked file (`git ls-files --others --exclude-standard`). | `.gitignore` gains explicit `/host.yaml`, `/capabilities.yaml`, `/project.alpha.yaml`, `/project.beta.yaml` — named individually, not globbed, so a future `*.example.yaml` cannot be hidden by accident. `test_gitignore_covers_the_required_entries` is extended. | | no |
| **D17** | *(found)* §6 adds `infra/`, `libexec/`, `systemd/`, `services/edge-probe`, `services/secret-check`. | `test_repository_contract.SCAN_ROOTS = ("compose.yaml", "deploy.sh", "bin", "src", "services")`. New deployable trees would be **unscanned** for hard-coded fixture identities. | Extend `SCAN_ROOTS` with `infra`, `libexec`, `systemd`, and extend `REQUIRED_PATHS` with every new committed file. Purely additive strengthening. | | no |
| **D18** | *(found)* Health route is `/__apg/healthz`. | `RESERVED_BASE_PATHS` (decision **B**) does not contain `/__apg`, and `public_base_path`'s pattern `^/[^/].*[^/]$` **permits** it. A project could set `api.public_base_path: /__apg` and shadow the health route. | Add `/__apg` to `RESERVED_BASE_PATHS` with a test asserting a manifest claiming it is rejected. | Source-level change to a closed decision. | **yes** (amends **B**) |
| **D19** | *(found)* Session 2 implements `bin/bootstrap-providers.sh`. | `test_cli_contract.FUTURE_STUBS` includes it; `test_future_stub_exits_ten` asserts a bare invocation returns `10`. Once implemented, a bare invocation is invalid input → `2`. | Remove it from `FUTURE_STUBS` and give it real command-contract tests (`--help` → `0` without root; missing `--host`/`--project` → `2`; `--apply` as non-root → `3`; `--destroy` without exact `--confirm <project_key>` → `2`). `connect.sh`, `migrate.sh`, `restore-test.sh` stay stubs. | This is the intended stub lifecycle, but it edits a passing test, so the bright-line rule applies. | **yes** |
| **D20** | *(found)* §11 host-side step 11: "Re-render, install the tested release, and **deploy both projects**" — inside the gate. | Session 1's gate is non-mutating by construction. | **Disagreement with the runbook.** `bin/session-02-check.sh --mode host` **verifies only** by default; deployment is an explicit `--deploy` flag. A gate that deploys the system it measures cannot be re-run to confirm a fix, and its result depends on whether it was the first run. `--tests-only` (which the runbook's own Phase 16 command uses) becomes the default rather than an option. | | no |
| **D21** | *(found)* §4.9: secret files owned by the consumer's fixed numeric UID/GID (`65532`), and Compose's `uid`/`gid`/`mode` fields are explicitly not relied on. | — | Correct, and it means the host must own the file `65532:65532` **before** Compose mounts it, and `secret-check`'s container user must be exactly `65532:65532`. Declared once in `secrets.required.yaml` and asserted by a contract test that cross-checks the Compose service's `user:` against the declared consumer UID. | The two numbers living in two files is exactly how this silently becomes a root-owned mount. | no |
| **D22** | *(found)* §8.1/§13 invoke `--host host.yaml` from the checkout; §7 puts `host.yaml` at `/etc/agentic-postgres/host.yaml`, `0600`, root. | — | Two copies, one authority: the checkout copy is **operator input**; `provision-host.sh --apply` copies it to `/etc/` atomically and records its sha256 in edge/deployment state. Every later root operation reads `/etc/`, and refuses if the checkout copy's digest differs from the recorded one without an explicit `--reapply-host-config`. | | no |
| **D23** | *(found)* §8.10 example `bin/compose.sh .generated/alpha-dev config`. | The model's only service is profile-gated; a bare `config` renders no services and Compose prunes the networks and volume. | Every `config` call keeps an explicit `--profile`. Documented in the operator guide and asserted by a test that a bare `config` renders no service. | | no |
| **D24** | *(found)* Phase 18: operator guide "fewer than 15 operator steps"; §13's demonstration script has ~18 `sudo` lines. | — | Define the counting rule in the guide: a *step* is one operator decision, not one shell line; the two `deploy.sh` invocations are one step parametrized by project. State the count explicitly at the top of the guide. | An unstated counting rule makes the criterion unfalsifiable. | no |
| **D25** | *(found)* Runbook assumes a checkout on the VPS but never says how it gets there; the remote is private. | — | See §2. Transport is a `git bundle` pushed from WSL; no GitHub credential ever exists on the VPS. | | no |
| **D26** | *(found)* `docs/decisions/README.md` index. | Lists `0001`–`0003`; `0004` exists on disk and is unlisted. | Regenerate the index to cover `0001`–`0011`, and add a contract test asserting every `docs/decisions/NNNN-*.md` appears in the index. | Drift that is currently invisible. | no |
| **D27** | *(found during Run 1)* — | `src/agentic_postgres/naming.py` cites "plan decision **W**" and `src/agentic_postgres/config.py` cites "plan decision **X**", but the Session 1 decision log stops at **V**. Two more dangling citations of D1's species. | Transcribe **W** (`COMPOSE_NAME_MAX = 63` as the single truncation boundary) and **X** (the pgBackRest stanza character set) into the Session 1 decision log under a "Decided during implementation" heading, dated and labelled as transcription. No code changes. | The citations already claim these live in the log. **X** is security-relevant — it is what stops a stanza name containing `/` from addressing another project's backup prefix — and it existed only as a regex and a one-line comment. | no |

---

## 2. Environment feasibility — what Session 2 adds

The local side (WSL2 Ubuntu, ext4, `~/projects/agentic-postgres`, `.venv`, `bin/doctor.sh`, `gh.exe` credential helper, branch `main`) is settled and unchanged. The three standing traps constrain everything below: no new script assumes a bare `python`; every new executable's **git index mode** is asserted `100755`; every new file type is covered by `.gitattributes` and by `test_no_tracked_file_uses_crlf`, which is the real guard for the extensionless `infra/host/*`, `libexec/*` and `systemd/*.service` files.

### 2.1 Blocking prerequisites — none of Run 5 starts without all six

| # | Prerequisite | Verify |
|---|---|---|
| 1 | **VPS, x86_64, Ubuntu 24.04 or 26.04 LTS**, ≥2 vCPU / 4 GiB / 40 GiB, ports 80+443 free, clock synced, no unrelated Docker workload. | `ssh op@host 'uname -m; . /etc/os-release; echo $VERSION_ID; ss -lntup; timedatectl show -p NTPSynchronized'` → `x86_64`, `24.04`\|`26.04`, nothing on 80/443, `NTPSynchronized=yes` |
| 2 | **Architecture matches `TARGET_PLATFORM=linux/amd64`.** | Above. **An ARM VPS is a stop condition** — every digest in `versions.env` is amd64-only, `versions.in.yaml` would need `target_platform: linux/arm64`, `bin/lock-versions.sh --update` re-run, and every digest in the committed lock would change. |
| 3 | **Two real hostnames with A records → the VPS IPv4**, TTL ≤ 300 set at least an hour before Run 6, AAAA present **only** if IPv6 ingress actually works. | From WSL: `dig +short A alpha-db.<domain>` equals the VPS IP; `dig +short AAAA …` empty or correct; `curl -sS -o /dev/null -w '%{http_code}' http://<ip>/` reaches the host. §5.3 is right that a broken AAAA is worse than none. |
| 4 | **Key-based SSH as a non-root operator user**, plus a **provider recovery/serial console verified to a login prompt**. | `ssh -o BatchMode=yes op@host true` → 0, twice concurrently; open the provider console and confirm a prompt **before** Phase 6. |
| 5 | **Infisical**: organisation slug, API URL, environment slug, and a **least-privilege control-plane machine identity** (not a personal token) able to create projects, identities and secrets. Credential at `/root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential`, `0400 root:root`. | A read-only API call returning `200` without the body being printed; `stat -c '%a %U' <file>` → `400 root`. |
| 6 | **ACME contact email** (non-secret host configuration). | Present in `host.yaml`; syntactically validated by the host schema. |

### 2.2 How the repository reaches the VPS

The remote is private and §4.2 forbids systemd running from a live checkout. Two transports were considered:

- *VPS pulls from GitHub* — needs a deploy key or PAT living on the host permanently. Rejected: it adds a long-lived credential to the host for a transfer that happens a handful of times.
- **`git bundle` pushed from WSL — recommended.** No GitHub credential ever exists on the VPS.

```bash
# on WSL, from a clean tree
bin/session-01-check.sh                      # must exit 0 first
git bundle create /tmp/apg.bundle main
scp /tmp/apg.bundle op@host:~/apg.bundle
# on the VPS, as the unprivileged operator, first time
git clone ~/apg.bundle ~/agentic-postgres
# thereafter
cd ~/agentic-postgres && git fetch ~/apg.bundle main:refs/remotes/bundle/main \
  && git checkout <commit>
```

The operator checkout on the VPS is a **transport and validation artifact only**. `deploy.sh --through-session 2` step 3 runs `git archive <HEAD>` from it into `/opt/agentic-postgres/releases/{commit}/`, root-owned and immutable, exactly as §8.6 requires; the launchers under `/usr/local/libexec/agentic-postgres/` resolve that recorded release and nothing else ever executes from the checkout. I edit in WSL, commit on `main`, run `bin/session-01-check.sh`, then bundle-and-scp. That is the only thing that moves a tested commit onto the host.

### 2.3 `bin/doctor.sh` — two commands, not one with modes

`bin/doctor.sh` stays exactly as it is: local tooling and repository shape, exit `0` or `3`, no host awareness. `bin/provision-host.sh --host … --check` owns the host verdict and the `3` (missing tool / unsupported host) vs `6` (hardening or firewall failure) distinction from §8.7.

I disagree with folding them together. Doctor answers "are my tools present"; host preflight answers "is this host in policy". They have different audiences, different privilege requirements, and — decisively — different exit vocabularies. Merging them either forces doctor to learn exit `6` (changing a Session 1 meaning) or forces host preflight to collapse policy failures into `3` (losing the distinction §8.7 just created). `OPS-001` at Session 11 can still present one operator-facing surface over both.

### 2.4 Which suite runs where

| Suite | Selector | Runs on | Invoked by |
|---|---|---|---|
| Session 1 gate | `-m "contract and not future"` + registry + Compose config | WSL, CI, and the VPS checkout | `bin/session-01-check.sh` (unchanged in meaning) |
| Session 2 offline contract | `APG_ACCEPTANCE_SESSION=2 -m "p0 and not future and not live_host and not external"` | WSL, CI, VPS | `bin/session-02-check.sh --mode offline`, and CI |
| Host-local live | `-m "live_host"` | VPS only | `sudo bin/session-02-check.sh --mode host` |
| Public path | `-m "external"` | WSL (a different network from the VPS) | `bin/session-02-check.sh --mode external` |

Session 1's single-gate model does not survive this split and I am not pretending otherwise: **Session 2 has three invocations producing two evidence files that merge into one.** `evidence/session-02-host.json` + `evidence/session-02-external.json` → `evidence/session-02.json`, with the merge failing when source commits, project keys, routes or certificate fingerprints disagree. `bin/write-session-evidence.py` grows `--host-input`, `--external-input`, `--output`; its Session 1 behaviour (`--session 1`, `--artifacts`) is untouched.

### 2.5 What CI can and cannot assert

The existing `gate` job (full Session 1 gate on `ubuntu-latest`) is **unchanged**. A new `session-2-contract` job asserts, with no credentials and no VPS:

- the offline Session 2 suite at `APG_ACCEPTANCE_SESSION=2`;
- `bin/compose.sh` config validation for `infra/edge/compose.yaml` and both fixture directories;
- `docker build` of `services/edge-probe` and `services/secret-check` (runner Docker is available);
- the socket-proxy allowlist policy against the runner's own daemon — the one live-ish check CI genuinely can do;
- `systemd-analyze verify` on the three unit files;
- output schema migration and document-kind rejection; the four new state schemas;
- the secret-pattern scanner over **synthetic** fixture values;
- `test_acceptance_registry.py` and `test_future_marker_policy.py` at session 2.

CI **cannot** and will not: reach the VPS, obtain an ACME certificate (staging or production), contact Infisical, run `ufw`/`iptables`/`sshd -T`, or execute anything marked `live_host` or `external`. Those are release evidence, not pull-request CI — §17 is right about that. Actions stay commit-pinned.

---

## 3. Safety plan for irreversible host operations

The rule for all three: **arm the rollback before the change, verify from a session that did not exist before the change, disarm only after that verification.** Never two armed windows at once.

### 3.1 SSH hardening (Phase 6)

**Arm.** (1) Session A stays open and is never closed, never reused for the change. (2) Open and verify session B. (3) Confirm the provider console reaches a login prompt. (4) `cp -a /etc/ssh /var/backups/agentic-postgres/ssh.<ts>` and record the sha256 of every file. (5) Arm a transient timer:

```bash
sudo systemd-run --on-active=10min --unit=apg-ssh-rollback \
  /usr/local/libexec/agentic-postgres/ssh-rollback /var/backups/agentic-postgres/ssh.<ts>
sudo systemctl list-timers 'apg-ssh-rollback*'      # must show a future trigger
```

`provision-host.sh` refuses to write the snippet if that timer is not armed.

**Apply.** Inspect every existing `sshd_config.d/*` for earlier conflicting directives (OpenSSH takes the *first* obtained value and includes lexicographically — which is the entire reason the file is named `00-`). Write `/etc/ssh/sshd_config.d/00-agentic-postgres.conf` atomically; `sshd -t`; `sshd -T -C user=<op>,host=localhost,addr=<a member of the allowed CIDR>` and diff against the expected key/value set; **`systemctl reload ssh`, never `restart`**.

**Verify from an independent session.** Open session **C** — new TCP connection, new authentication — with the key: must succeed. Then `ssh -o PubkeyAuthentication=no -o PreferredAuthentications=password op@host` must be denied, and `ssh root@host` must be denied.

**Disarm.** Only after C succeeds: `sudo systemctl stop apg-ssh-rollback.timer`. `provision-host.sh` prints the exact disarm command and requires a separate `--confirm-ssh-ok` invocation; it never auto-cancels, because auto-cancelling on "the script finished" cancels on exactly the case where the script was wrong.

**Lost connectivity mid-phase.** Do nothing for ten minutes and let the timer restore and reload. If that also fails, provider console → `cp -a` the backup back → `systemctl reload ssh`. Do not touch the firewall until SSH is proven.

### 3.2 Firewall and `DOCKER-USER` (Phase 9)

**Arm.** `iptables-save`, `ip6tables-save`, `ufw status verbose` into the same backup directory; a second transient timer whose rollback runs `ufw --force disable; iptables-restore < v4.rules; ip6tables-restore < v6.rules`.

**Ordering is the control.** `ufw allow from <cidr> to any port <ssh> proto tcp` **before** `ufw default deny incoming`, and both before `ufw --force enable`. Enabling UFW with no SSH allow rule is the classic lockout and the script must refuse to reach `enable` if no rule covers the configured SSH port.

**Verify from an independent session.** Session C from the allowed CIDR must connect. From a *second network* (a phone hotspot is sufficient): 22 refused, 80 and 443 reachable. Then `iptables -S DOCKER-USER` and `ip6tables -S DOCKER-USER` match the generated rule set exactly, and the `agentic-postgres-docker-firewall.service` reconciliation is idempotent across a `systemctl restart docker`.

**Disarm** only after both checks.

> **Decision you need to make explicitly:** `ssh.allowed_source_cidrs`. A residential IP that rotates locks you out on its next lease. If you have no static address, set `0.0.0.0/0` on the SSH port with key-only authentication for Session 2 and record the deviation in evidence rather than pretending to a source restriction that will fail silently. My recommendation is `0.0.0.0/0` + key-only unless you have a stable jump host.

### 3.3 Docker daemon (Phase 8)

No timed rollback, and that is deliberate: a failed Docker daemon does not cost SSH, which is why this phase is separated from the two above. **Arm** by backing up `/etc/docker/daemon.json` if present and validating before applying: `dockerd --validate --config-file=/etc/docker/daemon.json`. **Apply** `systemctl restart docker`. **Verify** `docker info`, `docker version`, `docker compose version`, and `ss -lntp | grep -E ':(2375|2376)\b'` returning nothing. **On failure**, `journalctl -u docker -n 200`, restore the backup, restart.

Two ordering notes: `userland-proxy: false` changes how NAT rules are created, so it must be set **before** the edge plane exists; and `live-restore: true` only takes effect after a daemon restart.

### 3.4 ACME staging → production

1. `host.yaml` sets `initial_acme_environment: staging`. The resolver points at the staging directory and stores in `staging.json`. **All** iteration — labels, router names, redirect, DNS, attachment reconciliation — happens here.
2. `edge.sh promote-acme --to production --confirm <host.id>` is the only path to production. It **refuses** unless `staging.json` already holds a certificate for both hostnames. It writes root-owned edge state, re-renders `traefik.yaml` with the production directory and `storage: production.json`, and restarts Traefik. Production is never a default and is never reached by re-running an earlier command.
3. Two hostnames = two issuances, against a 50/week per-registered-domain limit and a 5/week duplicate-certificate limit. The thing that burns those is **deleting `production.json` and re-requesting**, so §14.8's "no routine rollback deletes ACME production state" is enforced mechanically: `bin/compose.sh --edge` refuses `-v`/`--volumes`, `edge.sh down` preserves the bind-mounted `acme/` directory, and destructive ACME deletion needs a separate explicit command.
4. On production failure: read the Traefik ACME error, fix DNS or port 80, **do not retry in a loop** — failed validations are limited to 5/hour/hostname. If the window is exhausted, finish the session on staging with a recorded deviation rather than burning the weekly limit.

---

## 4. Build order — eight runs

`bin/session-01-check.sh` must exit `0` on a clean tree at the end of **every** run. Mid-run use `--allow-dirty` or `bin/smoke-test.sh`; a run is not complete until the clean form passes. Runs 1–4 touch no VPS.

### Run 1 — Contract foundations, offline
*Phases 0–4, plus §6's lock additions.*

Creates: `docs/plans/session-02-implementation-plan.md`; `docs/decisions/0005`–`0008` (backfill), `0009-host-and-edge-plane.md`, `0010-secret-materialization.md`, `0011-provider-bootstrap-state.md`, updated `docs/decisions/README.md`; `schemas/{host,secret-contract,bootstrap-state,deployment-state,edge-state,secret-generation}.schema.json`; `schemas/outputs.schema.json` (v2, `oneOf` on `document_kind`); `src/agentic_postgres/{host_config,secrets_contract,bootstrap_state,output_migrations}.py`; `host.example.yaml`, `secrets.required.yaml`; `tests/fixtures/outputs-v1.json`; `tests/contract/test_{host_manifest,secret_contract,bootstrap_state,deployment_state,edge_state,secret_generation}.py`.
Modifies: `versions.in.yaml`/`versions.env` (+`DOCKER_SOCKET_PROXY_IMAGE`, `TRAEFIK_VERSION`), `.gitignore` (D16), `.gitattributes`, `src/agentic_postgres/config.py` (`/__apg` reserved, D18), `src/agentic_postgres/rendering.py` (v2 rendered document, `secrets.status`/`required_names`, `routes.health`), `tests/contract/test_{output_schema,repository_contract,project_manifest}.py`.

```
bin/lock-versions.sh --update                                        # 0  (WSL, network, once)
bin/lock-versions.sh --check                                         # 0  (offline)
python -m pytest -q -m "contract and not future"                     # 0
python -m pytest -q tests/contract/test_host_manifest.py \
  tests/contract/test_secret_contract.py                             # 0
./deploy.sh --project project.example.yaml \
  --capabilities capabilities.example.yaml --render-only             # 0
jq -e '.schema_version==2 and .document_kind=="rendered" and .secrets.namespace' \
  .generated/fixture-alpha-dev/outputs.json                          # 0
bin/session-01-check.sh                                              # 0
```
Deferred: every Compose change, every script, the registry, the host.

### Run 2 — Compose model, wrapper gating, probe images
*Phases 10 (model only), 11, §8.10.*

Creates: `infra/edge/{compose.yaml,traefik.yaml,dynamic/baseline.yaml}`; `infra/host/{20auto-upgrades,00-agentic-postgres-ssh.conf,daemon.json,docker-user-rules.v4,docker-user-rules.v6}`; `services/edge-probe/{Dockerfile,probe.py}`; `services/secret-check/{Dockerfile,check.py}`; `systemd/agentic-postgres-{docker-firewall,edge}.service`, `agentic-postgres-project@.service`; `libexec/agentic-postgres-{edge,project}`; `tests/contract/test_edge_compose.py`, `test_project_labels.py`.
Modifies: `bin/compose.sh` (D3, D4), `compose.yaml` (`edge-probe` and `unlabeled-probe` profiles), `rendering.py` (eight-key `compose.env`, D7), `tests/contract/test_compose_contract.py` (D3), `test_output_schema.py` (key set).

```
bin/compose.sh .generated/fixture-alpha-dev --profile contract config >/dev/null   # 0
bin/compose.sh .generated/fixture-alpha-dev up                                     # 10
bin/compose.sh .generated/fixture-alpha-dev --runtime up                           # 3  (not root)
sudo bin/compose.sh --edge --host host.example.yaml config >/dev/null              # 0
docker build -q services/edge-probe && docker build -q services/secret-check       # 0
systemd-analyze verify systemd/*.service                                           # 0
git ls-files --stage -- libexec/ bin/ deploy.sh | grep -cv '^100755'               # 1
python -m pytest -q -m "contract and not future"                                   # 0
bin/session-01-check.sh                                                            # 0
```
Deferred: registry activation, the `CURRENT_SESSION` flip, every root script.

### Run 3 — Registry activation, gate semantics, `CURRENT_SESSION = 2`
*Phase 16 (structure and offline bodies), Phase 17.* **This run contains the atomic three-file flip of D15.**

Creates: `tests/deployment/test_session2_{host,edge,isolation}.py`; `tests/external/test_session2_public_edge.py`; `tests/security/test_session2_{secrets,installed_release}.py`.
Modifies: `tests/acceptance-registry.yaml` (11 new IDs; `SEC-NET-001`, `SEC-SECRET-001` activated); `tests/security/test_future_security_boundaries.py` (two markers removed, bodies relocated); `pytest.ini` (`live_host`, `external`); `tests/conftest.py`; **`src/agentic_postgres/__init__.py` (`CURRENT_SESSION = 2`)**; **`bin/session-01-check.sh` (derive `APG_ACCEPTANCE_SESSION`; step 3 captures rendered dirs; step 7 scopes to them — D13, D15)**; `src/agentic_postgres/evidence.py` (D14); `docs/threat-model.md`; `docs/acceptance-matrix.md` (regenerated); `.github/workflows/ci.yml`; `tests/contract/test_future_marker_policy.py` (marker tuple).

```
APG_ACCEPTANCE_SESSION=2 python -m pytest -q \
  -m "p0 and not future and not live_host and not external"          # 0
python -m pytest -q tests/contract/test_acceptance_registry.py        # 0
python -m pytest -q tests/contract/test_future_marker_policy.py       # 0
python -m pytest --collect-only -q -m p0                              # 0, non-empty
python bin/render-acceptance-matrix.py --check                        # 0
bin/session-01-check.sh                                               # 0   <- D15 proof
jq -e '.p0_tests_future < 50' evidence/session-01.json                # 0
```
Deferred: every root script, everything on a host.

### Run 4 — Root command surface, still offline
*§8.1–8.5, Phases 12–13 logic, the gate skeleton.*

Creates: `bin/{provision-host,edge,edge-network,materialize-secrets,session-02-check}.sh`; `src/agentic_postgres/{infisical_client,installed_release}.py`; `tests/contract/test_root_script_policy.py`.
Modifies: `bin/bootstrap-providers.sh` (implemented), `bin/write-session-evidence.py` (merge inputs), `tests/contract/test_cli_contract.py` (D19).

```
shellcheck deploy.sh bin/*.sh libexec/*                               # 0
for s in bin/provision-host.sh bin/edge.sh bin/edge-network.sh \
         bin/materialize-secrets.sh bin/bootstrap-providers.sh \
         bin/session-02-check.sh; do "$s" --help; done                # 0 each, non-root
bin/provision-host.sh --host host.example.yaml --check                # 3  (non-root refusal)
bin/bootstrap-providers.sh                                            # 2  (was 10)
bin/session-02-check.sh --mode offline                                # 0
python -m pytest -q tests/contract/test_root_script_policy.py         # 0
bin/session-01-check.sh                                               # 0
```
Deferred: everything that touches the VPS. **Bundle-and-scp the tested commit at the end of this run — this is the first thing the VPS ever sees.**

### Run 5 — Host provisioning
*Phases 5–9. First VPS mutation. Each of 6, 8, 9 armed / verified / disarmed per §3, and each is a separate stopping point.*

```
sudo bin/provision-host.sh --host host.yaml --check                   # 0 (or 3/6 listing everything)
sudo bin/provision-host.sh --host host.yaml --apply                   # 0
sudo sshd -T -C user=<op>,host=localhost,addr=<cidr member> | grep …  # policy matches
sudo ufw status verbose; sudo iptables -S DOCKER-USER                 # expected rules
sudo ss -lntup                                                        # only ssh/80/443
sudo bin/session-02-check.sh --host host.yaml --mode host --tests-only \
     -k "host or firewall or docker"                                  # 0
bin/session-01-check.sh                                               # 0 (on the VPS checkout)
```
Deferred: edge plane, providers, secrets, projects. No container is started in this run.

### Run 6 — Edge plane and Project A on **staging** ACME
*Phases 10 (live), 12, 13, 14 staging sequence.*

```
sudo bin/edge.sh --host host.yaml up                                  # 0
sudo bin/edge.sh --host host.yaml status                              # 0, redacted
sudo bin/bootstrap-providers.sh --host host.yaml --project project.alpha.yaml \
  --plan --operator-credential-file …                                 # 0
sudo bin/bootstrap-providers.sh … --apply …                           # 0
sudo bin/bootstrap-providers.sh … --plan …                            # 0, no changes
sudo bin/materialize-secrets.sh --project project.alpha.yaml \
  --requirements secrets.required.yaml --session 2                    # 0
sudo ./deploy.sh --host host.yaml --project project.alpha.yaml \
  --capabilities capabilities.yaml --through-session 2                # 0
curl -I http://alpha-db.<domain>/__apg/healthz                        # 301 to https
curl -k --fail https://alpha-db.<domain>/__apg/healthz                # 200, staging cert
sudo bin/edge.sh --host host.yaml restart && sleep 15 && \
  curl -k --fail https://alpha-db.<domain>/__apg/healthz              # 200 (attachment reconciled)
bin/session-01-check.sh                                               # 0   <- D13/D14 proof
```
Deferred: production ACME, Project B, isolation proofs.

### Run 7 — Production promotion, Project B, isolation
*Phase 14 promotion, Phase 15.*

```
sudo bin/edge.sh --host host.yaml promote-acme --to production --confirm <host.id>   # 0
curl --fail https://alpha-db.<domain>/__apg/healthz                                  # 200, trusted
sudo bin/bootstrap-providers.sh … --project project.beta.yaml --apply …              # 0
sudo bin/materialize-secrets.sh --project project.beta.yaml …                        # 0
sudo ./deploy.sh --host host.yaml --project project.beta.yaml … --through-session 2  # 0
curl --fail https://beta-db.<domain>/__apg/healthz                                   # 200, beta key
sudo bin/session-02-check.sh --host host.yaml --project-a … --project-b … \
  --capabilities capabilities.yaml --mode host --tests-only                          # 0
bin/session-01-check.sh                                                              # 0
```
Also proved here: hostname A never returns B's body; Traefik attached to both edge networks and neither internal network; restarting/removing B leaves A's route up; the collision-refusal cases of §15 fail **before** mutation.

### Run 8 — Gate, evidence, documentation
*Phase 16 (live bodies), Phase 18, §11.*

```
sudo bin/session-02-check.sh … --mode host                            # 0 -> evidence/session-02-host.json
# from WSL, a different network:
bin/session-02-check.sh --project-a-outputs … --project-b-outputs … \
  --mode external                                                     # 0 -> evidence/session-02-external.json
python bin/write-session-evidence.py --session 2 \
  --host-input evidence/session-02-host.json \
  --external-input evidence/session-02-external.json \
  --output evidence/session-02.json                                   # 0
jq -e '.tests.secret_leakage=="passed" and .tests.isolation=="passed"' \
  evidence/session-02.json                                            # 0
python bin/render-acceptance-matrix.py --check                        # 0
git status --porcelain                                                # empty
bin/session-01-check.sh                                               # 0
```
Creates `docs/{host-baseline,provider-bootstrap,project-isolation,secret-handling,session-02-operator-guide}.md`, updates `README.md` and `docs/handoff.md`.

---

## 5. Secret handling review

**The path.** Infisical control-plane credential (`/root/.config/…`, `0400 root`) → `bootstrap-providers.sh` reads it by file descriptor → creates the project runtime machine identity and one Universal Auth client secret → writes `/etc/agentic-postgres/credentials/{key}/infisical-client-{id,secret}` (`0400 root`) → `materialize-secrets.sh` reads both files → `POST /api/v1/auth/universal-auth/login` over TLS → short-lived access token, **process memory only** → per declared key, `GET /api/v3/secrets/raw/{key}` with `expandSecretReferences=false&includeImports=false` → value in memory → written to `/var/lib/agentic-postgres/secrets/{key}/generations/{gen}/secret-check/session2_sentinel`, `0400`, owned `65532:65532` → `fsync` file and directory → atomic replace of `active-secret-generation.json` → the root-owned runtime override declares `secrets: session2_sentinel: {file: <that exact immutable path>}` → Compose mounts it at `/run/secrets/session2_sentinel` in the `secret-check` service **only**.

Secret-zero is not eliminated and Session 2 does not claim it is: the control-plane credential and one per-project client secret live on the host, root-only. What Session 2 bounds is how far they travel.

| Leak surface | Control | Test that catches it |
|---|---|---|
| Source control | value never written into the tree; operator inputs gitignored (D16) | `test_session2_secrets.py::test_sentinel_absent_from_tracked_and_untracked_files` (scan over `git ls-files` and `git ls-files -o`) |
| Compose interpolation | no `environment:` entry sourced from a secret; `compose.env` key sets are exact and asserted (D7) | `test_compose_contract.py::test_no_service_takes_a_secret_through_environment`; `test_compose_env_defines_exactly_the_expected_keys` |
| `docker compose config` output | model references file paths, never values | `test_sentinel_absent_from_rendered_compose_config` |
| Process arguments (`ps aux`) | credentials read from files, never argv | `test_root_script_policy.py::test_no_script_passes_a_secret_in_arguments` — static scan for `--client-secret`, `--token`, `KEY=… docker compose`, `infisical export`, `eval "$(`, `source *secret*` |
| Shell history / `set -x` | `set +x` before every credential section | `test_root_script_policy.py::test_secret_sections_disable_tracing` |
| `--env-file` | wrapper's `--env-file` set is fixed and disjoint three ways; no dotenv is ever generated | `test_no_dotenv_exists_under_the_secret_root`; wrapper env-file allowlist test |
| systemd journal | scripts print fixed strings; `secret-check` prints a fixed success message and never the value or a digest | leak scan over `journalctl -u 'agentic-postgres-*'` |
| `docker inspect` | value never in a label, env, or command | `test_sentinel_absent_from_docker_inspect` over every Session 2 container |
| Image layers | build runs with BuildKit network disabled and consumes no build secrets | `test_sentinel_absent_from_image_history` (`docker history --no-trunc`) |
| Container logs | — | leak scan over `docker logs` for traefik, socket-proxy, both probes |
| Traefik access log | `queryParameters.defaultMode: drop`, `headers.defaultMode: drop` | live sentinel test: request `?apg_sentinel=<random>` and assert it is absent from the access log (this is also the real proof behind D11c) |
| Evidence files | evidence schema forbids secret-bearing keys; §18 forbids secret hashes | leak scan over `evidence/` + `test_evidence_contains_no_secret_bearing_key` |
| Both `outputs.json` kinds | `assert_output_is_secret_free` applied to rendered **and** deployed; schema rejects the keys | `test_output_schema.py` plus a deployed-branch variant |
| The scanner itself | prints path/object identifiers only | guard-the-guard: plant the sentinel in a temp file, assert the scanner reports the path and never the value |

The scanner reads the sentinel through a root-only helper into memory and compares bytes. It never echoes what it matched. §16's "a digest is not used as an isolation substitute" is honoured: the proof that Project A's `secret-check` got only its own secret is the **mount list** plus a successful own-secret read, not a hash comparison.

---

## 6. Risks and stop conditions

**Halt — do not work around.**

1. **Lockout.** A new SSH session fails after reload *and* the timed rollback does not restore. Provider console, restore from `/var/backups/agentic-postgres/`, and do not touch the firewall until SSH is proven from a fresh session.
2. **ACME production rate limit reached.** Stop. Do **not** delete `production.json` and do **not** retry in a loop — that is what converts a failed validation into an exhausted weekly limit. Finish the session on staging with the deviation recorded in evidence.
3. **A digest will not resolve for `linux/amd64`** — most likely the socket proxy. Inherits Session 1 stop condition 1: no floating tag, no single-arch fallback, no quiet removal from the inventory. Change the candidate tag deliberately or record an ADR dropping the component.
4. **The VPS is not x86_64.** Halt before Run 5. Every locked digest is wrong; this is a `versions.in.yaml` change and a full re-lock, not a runtime accommodation.
5. **Provider bootstrap partial state.** A client secret was created but the local write failed, or saved IDs disagree with the provider. Halt; revoke the orphan **by ID**; never adopt by name; never guess. §8.2's "name equality alone is insufficient" is the rule.
6. **The socket proxy needs `privileged: true`, or Traefik needs an API section outside the allowlist.** Halt. Change image or version, or write a narrow AppArmor policy. Never grant privileged mode and never mount the socket into Traefik "temporarily". If `INFO` turns out to be genuinely required, that is an ADR plus a negative-write regression test, not a config edit.
7. **The `env -i` allowlist proves insufficient under sudo or systemd.** Inherits Session 1 stop condition 4: extend per variable with a written reason. Never `env -u`, never `sudo -E`, never pass the inherited environment through.
8. **The leak scanner finds the sentinel anywhere.** Halt, rotate the client secret *and* the sentinel, fix the leak, re-run from a clean generation. Do not add the path to an exclusion list.
9. **A Session 1 test would have to be weakened and it is not on this list.** The ADR-backed changes are exactly: `test_container_starting_subcommands_are_refused` (D3), `test_no_timestamp_reaches_rendered_output` re-scoping (D6), `test_compose_env_defines_exactly_the_expected_keys` (D7), `bin/session-01-check.sh` step 7 (D13), `evidence.collision_count` (D14), `APG_ACCEPTANCE_SESSION` derivation (D15), `RESERVED_BASE_PATHS` (D18), `FUTURE_STUBS` (D19). Anything else turning red is a stop condition, not a fix. `future` still means "a later session owns this", never "inconvenient today".
10. **`bin/session-01-check.sh` cannot be made to exit `0`** by the eight documented changes above. That means Session 2's design has broken a Session 1 guarantee this plan did not find. Halt and bring it back to the decision log.

**Proceed with a documented assumption — do not halt.**

- The VPS will run Compose v2.x while the dev machine runs v5.1.3. Assertions stay structural; both observed versions go into evidence.
- Ubuntu 26.04 LTS may not be offered by the provider; 24.04 is the documented fallback under §4.1 and is recorded in evidence as a deviation.
- `INFO: "0"` on the socket proxy may prove insufficient for Traefik v3.5's Docker provider. If a compatibility test proves it, enabling it is an ADR — not a quiet flip.
- `ssh.allowed_source_cidrs` may have to be `0.0.0.0/0` with key-only authentication (see §3.2). Recorded as a deviation, not hidden.

---

## Open items — closed 2026-08-04

1. **Backfill ADRs `0005`–`0008`.** Approved. Done in Run 1 as commit 2, transcribed from the Session 1 decision log and labelled as transcription with the original decision date. D27 was found while doing it and given the same treatment.
2. **`ssh.allowed_source_cidrs`.** No static source address is available. **Decision: `0.0.0.0/0` on the SSH port with key-only authentication**, recorded as a deviation in `host.example.yaml`, in `docs/host-baseline.md`, and in Session 2 evidence.

   What this costs and what still holds: the SSH port stays exposed to the public Internet, so the controls that carry the boundary are `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `PermitRootLogin no`, `MaxAuthTries 3`, `LoginGraceTime 30`, and key-only public-key auth — all of which Phase 6 sets and the live-host suite asserts against `sshd -T` for the real operator/source tuple. The CIDR restriction was defence in depth, never the boundary. What is genuinely lost is rate-limit and log-noise reduction, and one layer against a stolen-key attacker who does not know the source address.

   `host.schema.json` still **requires** `ssh.allowed_source_cidrs` to be non-empty, so `0.0.0.0/0` is an explicit written choice in the manifest rather than an omission, and `provision-host.sh --check` warns (does not fail) when a `/0` is present so the deviation is visible on every run. Tightening it later is a one-line manifest edit plus `--apply`; nothing else depends on the value.

Everything else is closed above with a named owner and, where the rule requires it, a named ADR. If implementation surfaces a new ambiguity it comes back here as a new `D` row and an ADR — it does not get resolved inline.
