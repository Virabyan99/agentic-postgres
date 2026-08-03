# Session 1 — Implementation Plan

**Deliverable location note:** plan mode restricts me to this file. The first action of Run 1 is to copy this document verbatim to `docs/plans/session-01-implementation-plan.md` and commit it with commit 1. Nothing else in Run 1 starts before that copy exists.

**Context.** The runbook specifies *what* Session 1 must produce. This plan covers only what it does not: whether the specified thing is buildable on this machine, which open choices are now closed, how the four-way acceptance-traceability constraint stays true, and the order in which the nine commits become five executable checkpoints. Everything here is additive to the runbook; where I disagree with the runbook I say so under the relevant heading rather than silently routing around it.

---

## 1. Environment feasibility and prerequisites

### 1.1 What I measured on this machine

| Probe | Result |
|---|---|
| `os.chmod(p, 0o600)` on NTFS (`C:\Users\...\Temp`) | resulting mode `0o666`. Also `0o644` → `0o666`. **Mode bits are not stored.** |
| `os.chmod(p, 0o600)` on WSL2 Ubuntu ext4 (`~`) | resulting mode `0o600`. Correct. |
| `git config core.autocrlf` (system) | `true` |
| `git config core.symlinks` (system) | `false` |
| WSL distro | Ubuntu 26.04 LTS, kernel 6.6.87.2, WSL2, ext4 root (`/dev/sdf`, ~1 TB free) |
| Docker in WSL Ubuntu | Engine 29.5.2, Compose **v5.1.3**, Buildx v0.34.0 — Docker Desktop WSL integration active, default context `unix:///var/run/docker.sock` |
| `docker buildx imagetools inspect --format '{{json .Manifest}}'` from WSL | works; returned a real OCI index digest |
| `docker compose --env-file` / `--profile` | both declared `stringArray` → repeatable. Multi-`--env-file` accepted. |
| `shellcheck`, `jq` | **missing on both Windows and WSL** (apt-installable in WSL) |
| Python in WSL Ubuntu | **3.14.4 only**, no `pip`, no `ensurepip`, `EXTERNALLY-MANAGED` present (PEP 668), no `gcc`/`make` |
| Python on Windows | 3.12.7 (`C:\Python312`) |
| `pyenv` inside WSL | resolves to `pyenv-win` leaking through the Windows PATH — a trap, not usable |
| Repo directory | `…\OneDrive\Desktop\All projects\summer-2026\august\postgresql` — **empty**, and inside OneDrive |

### 1.2 Item-by-item assessment

**§4.2 / §4.4 — `0600` file modes asserted via Python `stat`.**
Not achievable on native Windows. Measured: NTFS reports `0o666` regardless of what `chmod` requested; Python's `os.chmod` on Windows only toggles the read-only attribute. A test asserting `stat.S_IMODE(...) == 0o600` fails unconditionally. Achievable on WSL2 ext4 — measured correct. **Recommendation: WSL2 on ext4; do not make the test conditional.**

**§4.1 step 3 — refuse symlinked targets.**
Achievable on WSL2 with normal `os.path.islink` / `os.lstat` semantics. On native Windows it is only *approximately* achievable: `os.path.islink` treats junctions and OneDrive Files-On-Demand placeholder reparse points inconsistently, so the check gets both false negatives (a junction slips through) and false positives (a placeholder file flagged as a link). Creating a symlink inside the test — which is required to prove refusal actually fires — needs Developer Mode or elevation on Windows. It happened to work in my probe, so Developer Mode is likely on, but that is an unstated ambient dependency.

**§4.1 step 7 — same-filesystem atomic rename, staging under `.generated/.staging/`.**
`os.replace` is atomic on both NTFS and ext4 when source and target share a volume, and `.generated/.staging/` guarantees that. The real hazard is not the filesystem, it is **OneDrive**: the sync engine opens files it is uploading, and a rename or unlink against a file OneDrive currently holds raises `PermissionError`/`WinError 32`. That converts a render into a nondeterministic flake, and — worse — can leave `.generated/{project_key}` half-swapped, which is precisely the state §4.1 step 8 exists to prevent. There is also a per-project exclusive lock required (see decision **I** below); `fcntl.flock` is POSIX-only.

**Required tooling.**
`shellcheck` and `jq` are absent everywhere and must be installed — trivially via apt in WSL, awkward on Windows (scoop/choco, and `shellcheck` on Windows has CRLF complaints against files Git checked out with `core.autocrlf=true`). Compose v5.1.3 and Buildx are available *inside WSL Ubuntu* via Docker Desktop integration, and I verified `imagetools inspect` resolves a real digest from there. Compose profile + repeatable `--env-file` support: verified present.

*Disagreement with the runbook:* §5.2 says "Docker Compose v2". The installed version is v5.1.3. `versions.in.yaml` must express a **minimum**, and the `--check` comparison must be a semver `>=` against a floor, not an equality or a `v2` prefix match. A literal reading of §5.2 would fail on this machine.

**§7.2 — stripping inherited environment in `bin/compose.sh`.**
Achievable, but only if implemented as an **allowlist**, not a denylist. `env -u VAR ...` requires enumerating every name that could collide, which is unbounded. `env -i` plus an explicit allowlist is bounded and testable. On this machine the allowlist must retain `HOME` (for `$HOME/.docker/config.json` and thus context resolution), `PATH`, `USER`, `DOCKER_HOST`, `DOCKER_CONTEXT`, `DOCKER_CONFIG`, `DOCKER_CERT_PATH`, `DOCKER_TLS_VERIFY`. This is fine in WSL. On native Windows there is no `env -i` at all under PowerShell and the Git Bash `env` shim's interaction with the Windows environment block is not something I want a security control resting on.

**Shell scripts: `#!/usr/bin/env bash`, `set -euo pipefail`, `BASH_SOURCE` root resolution.**
All work in Git Bash. The failure is upstream of the shebang: with system `core.autocrlf=true`, Git checks `bin/*.sh` out with CRLF, and `#!/usr/bin/env bash\r` produces `bad interpreter: /usr/bin/env bash^M`. Every script in the repo breaks on first checkout on a Windows clone. Separately, §12's "shell scripts are executable" cannot be asserted from the filesystem on NTFS.

### 1.3 Recommendation

**Target environment: WSL2 / Ubuntu 26.04, repository on the Linux filesystem at `~/projects/agentic-postgres`, Docker Desktop WSL integration (already enabled), Python 3.12 supplied by `uv`.**

Not a devcontainer: a devcontainer would work, but it adds a Docker-in-Docker or socket-mount layer between the gate and `docker buildx imagetools inspect`, and Session 1's whole point is a gate that runs identically locally and in CI. WSL2 is already installed, already has working Docker/Buildx/Compose, and already has correct POSIX mode semantics. It is the shortest path to a gate that means the same thing on your machine and on `ubuntu-latest`.

**Python 3.12 via `uv`, not apt.** Ubuntu 26.04 ships only Python 3.14 with no pip and a PEP 668 marker, and there is no `gcc`, so any sdist-only dependency fails to build. `uv python install 3.12` fetches a standalone CPython with no compiler needed. `uv` also gives you `uv pip compile --generate-hashes`, which produces exactly the `--require-hashes` file §5.3 demands, and `uv` itself is version-pinnable — satisfying §5.3's "the dependency-locking tool itself must also be pinned". Installation still uses the runbook's stated `python -m pip install --require-hashes -r requirements-dev.txt`. 3.12 rather than 3.14 because every locked dependency (`PyYAML`, `jsonschema`, `pydantic`, `ruff`, `httpx`, `pytest*`) has mature cp312 wheels and `actions/setup-python` supports it; cp314 wheel coverage is a live risk I do not want on the critical path of a session whose entire deliverable is reproducibility.

### 1.4 What breaks if you stay on native Windows under OneDrive

Concretely, and in descending severity:

1. **§4.2/§4.4/§9.5/§12 "Output files are `0600`" cannot pass.** Measured. Not a configuration issue.
2. **§11's "CI executes this same script" becomes false.** If you make the mode test platform-conditional, `bin/session-01-check.sh` asserts a strictly weaker contract locally than in CI. The guarantee you lose by that conditional is exactly this: *nothing on your machine ever verifies that the renderer sets owner-only modes*. You would be trusting a code path that only one of your two environments exercises — and it is the environment you don't develop in. That is the failure mode Session 1 exists to eliminate.
3. **Every `bin/*.sh` is broken on checkout** unless `.gitattributes` forces LF (see §2, decision **N** — I am adding this file regardless).
4. **§12 "shell scripts are executable" is unassertable from the filesystem** (mitigated below by asserting the git index mode instead — that fix is worth having in any environment).
5. **§4.1 step 7 renders become flaky and can leave a torn output directory** because the OneDrive sync engine holds handles on files being renamed. This is nondeterministic, so it will pass in development and fail in front of you at the gate.
6. **§4.1 step 3 symlink refusal is unreliable** against junctions and OneDrive reparse points, and the test proving it fires depends on Developer Mode being enabled.
7. **§7.2 environment stripping loses its `env -i` implementation**, degrading to a denylist that cannot be proven complete.
8. `.venv/`, `.pytest_cache/`, `__pycache__/`, and `.generated/` inside a synced folder waste bandwidth and can be corrupted mid-write by the sync engine.

Points 1, 2 and 5 are the ones I would not accept. **Move the repository out of OneDrive to the WSL filesystem before Run 1 begins.** Note that `\\wsl$\...` accessed *from* Windows tools is not a substitute — the mode semantics are only correct when the process doing the `chmod` is itself running inside WSL.

### 1.5 Ordered setup checklist (execute before Run 1)

Run every step from `wsl -d Ubuntu` unless marked otherwise.

1. `sudo apt-get update && sudo apt-get install -y shellcheck jq ca-certificates` — verify `shellcheck --version` and `jq --version`.
2. Confirm Docker Desktop → Settings → Resources → WSL Integration has **Ubuntu** enabled. Verify inside WSL: `docker version`, `docker compose version`, `docker buildx version` all succeed.
3. Verify digest resolution end to end: `docker buildx imagetools inspect python:3.12-slim --format '{{json .Manifest}}' | jq -r '.digest'` returns a `sha256:` value. *If this fails, stop — see §5, stop condition 1.*
4. Install `uv` pinned: `curl -LsSf https://astral.sh/uv/<pinned-version>/install.sh | sh`, then record that exact version string in `bin/lock-dev-deps.sh` as a comment and as an asserted `uv --version` check.
5. `uv python install 3.12` — verify `uv python find 3.12` resolves.
6. `mkdir -p ~/projects && cd ~/projects` — this is ext4, verified.
7. `git init agentic-postgres && cd agentic-postgres`.
8. Set repo-local git config that overrides the hostile system defaults:
   `git config core.autocrlf false`
   `git config core.filemode true`
   `git config core.symlinks true`
   (These are belt-and-braces; `.gitattributes` from decision **N** is the actual guarantee.)
9. Sanity-check mode semantics in place: create a file in the repo, `chmod 600`, confirm `stat -c %a` reports `600`. *If it reports `666` you are on a DrvFs mount, not ext4 — stop and fix the location.*
10. `printf '3.12\n' > .python-version` and create the venv with `uv venv --python 3.12 .venv`; `source .venv/bin/activate`; confirm `python -V` reports 3.12.x and record the exact patch version.
11. Confirm `git ls-files --stage` will carry mode `100755`: `touch t.sh && chmod +x t.sh && git add t.sh && git ls-files --stage t.sh` → expect leading `100755`. Then `git rm --cached t.sh && rm t.sh`.
12. Copy the source specification into place and place this plan at `docs/plans/session-01-implementation-plan.md`.

Do not begin Run 1 until steps 3, 9 and 11 have each produced the expected result.

---

## 2. Decision log

Every item below is closed. If something is not in this table, it does not get invented during implementation — it comes back here as a new lettered row with an ADR.

New ADRs beyond the runbook's `0001`–`0003`: `0004-version-lock-format`, `0005-route-reservation`, `0006-capability-scopes`, `0007-bounds-authority`, `0008-sensitive-key-policy`. The ADR directory already exists with a template per Phase 0, so this is an extension, not a new mechanism.

### Items the runbook explicitly left open

**A. §6.3 — sync format between `versions.in.yaml` and `versions.env`.**
`versions.env` is a flat `KEY=VALUE` file: keys match `^[A-Z][A-Z0-9_]*$`, values are unquoted, no expansion, no `export`, one per line, comments only on their own line. It carries a metadata header including `APG_LOCK_FORMAT=1`, `APG_VERSIONS_IN_SHA256=<64 hex>`, `APG_LOCKED_AT=<ISO-8601>`, and `TARGET_PLATFORM`.
`--check` is fully offline and does exactly four things: (1) parse strictly, rejecting duplicate keys and malformed lines; (2) recompute `sha256(versions.in.yaml)` and compare against `APG_VERSIONS_IN_SHA256`; (3) for every image candidate in `versions.in.yaml`, assert `versions.env` has the corresponding `*_IMAGE` whose `registry/repo:tag` portion is byte-equal to the candidate (the digest is not verifiable offline, only its syntax); (4) assert `TARGET_PLATFORM` matches.
*Rationale:* step 2 alone detects any edit to the candidate file, and step 3 makes the failure message point at the specific image rather than at an opaque hash mismatch.
*Source of truth:* `versions.env` format spec in `docs/decisions/0004-version-lock-format.md`; enforced by `bin/lock-versions.sh` and `tests/contract/test_version_lock.py`.

**B. §3.4 — reserved routes and "ambiguous overlap".**
Reserved base paths: `/`, `/docs`, `/health`, `/healthz`, `/ready`, `/metrics`, `/.well-known`, `/traefik`, `/static`, `/favicon.ico`, `/robots.txt`.
*Rationale:* `/docs` is derived unconditionally by §3.8 so it is structurally reserved; `/.well-known` is ACME, which Session 2 needs; `/health`/`/ready`/`/metrics` are `OPS-001` surface; the rest are conventional edge-router paths that would silently shadow.
"Ambiguous overlap" is defined precisely as: normalize a base path to its non-empty segment tuple (`/api/v1` → `("api","v1")`). Two paths overlap iff one tuple is a prefix of the other, **including equality**. So `/api` vs `/api/v1` overlaps; `/api` vs `/apiv2` does not. The same prefix relation is used against every reserved path. This deliberately rules out the naive `str.startswith` implementation, which would wrongly reject `/apiv2`.
*Source of truth:* `RESERVED_BASE_PATHS` and `paths_overlap()` in `src/agentic_postgres/config.py`; rationale in `docs/decisions/0005-route-reservation.md`.

**C. §5.2 — approved scope vocabulary.**
`notes:read`, `notes:write`, `tasks:read`, `tasks:write`, `meta:read`.
*Rationale:* one scope per (frozen-domain resource, verb) plus one for schema introspection, which is what `list_resources`/`describe_resource` in §5.3 need; the frozen domain is exactly notes and tasks, so the vocabulary is closed by §4.3 and grows only when the domain does.
*Source of truth:* an `enum` on the scope items in `schemas/capabilities.schema.json`. The code does not carry a second copy.

**D. §3.2 — YAML input size limit.**
**65,536 bytes (64 KiB)**, applied to the raw file size of `project.yaml` and `capabilities.yaml`, checked by `os.stat` *before* the file is read.
*Rationale:* the fixtures are ~1 KiB; 64 KiB is ~60× headroom while keeping the parser's memory surface tightly bounded. The runbook's 256 KiB is offered only as an example and is looser than needed.
*Source of truth:* `MAX_MANIFEST_BYTES` in `src/agentic_postgres/config.py`.

**E. §3.5 — where the bounds table lives.**
**`schemas/project.schema.json` is the sole authority.** It expresses every bound natively as `minimum`/`maximum`.
- Semantic validation code does **not** restate any bound. It loads the schema once and reads bound values from it when it needs them for messages. There are no numeric literals for bounds in `src/`.
- The documentation table is **generated** from the schema into a marker-delimited block in `docs/product-contract.md` by `bin/render-config.py --bounds-doc --write`, with `--bounds-doc --check` run in CI and in the gate. Same generate-and-drift-check pattern the runbook already establishes for the acceptance matrix.
- Cross-field **relations** (`pool_size <= max_client_connections`, `mcp.max_result_rows <= api.max_rows`) are *not* bounds and JSON Schema cannot express them. They live only in `src/agentic_postgres/config.py` and are documented as a separate short list, also generated into the same block.
*Rationale:* the schema is the only one of the three that is machine-consumed at validation time, so making either of the other two authoritative guarantees the enforced values and the stated values can diverge.

**F. §3.6 — sensitive-key denylist and safe allowlist.**
Matching rule, applied to every mapping key at every depth, lowercased: reject iff `key in DENY` **or** `key.endswith("_" + d)` for some `d in DENY`. Never a substring test.
`DENY = {password, passwd, passphrase, secret, private_key, access_key, secret_access_key, client_secret, api_token, refresh_token, access_token, session_key, signing_key, credentials, token}` — `token` and `secret` appear as whole-key/terminal-token entries only, which is what makes them safe.
`ALLOW = {password_secret_ref, token_ttl_seconds, token_use, secret_ref}`, consulted first.
*Rationale for why this works:* under terminal-token matching, `password_secret_ref` matches neither `_password` nor `_secret` nor `_secret_ref`… it ends in `_ref`. Likewise `token_ttl_seconds` ends in `_seconds`. So the allowlist is a documented safety net rather than a load-bearing exception list — which is the desired property. Tests assert both directions: every `ALLOW` entry survives, and `password`, `db_password`, `aws_secret_access_key`, `client_secret`, `api_token` are each rejected.
*Source of truth:* `SENSITIVE_KEY_DENYLIST` / `SAFE_KEY_ALLOWLIST` in `src/agentic_postgres/config.py`; rationale in `docs/decisions/0008-sensitive-key-policy.md`.

### Further ambiguities found while reading

**G. `outputs.json.template_version` has no stated source.** Decision: the `VERSION` file at repo root is authoritative; the renderer reads and strips it. A contract test asserts equality. *Source of truth:* `VERSION`.

**H. The pinned CPython version must appear in two places (§5.2) with no stated flow.** Decision: `versions.in.yaml` carries `python.version: "3.12.x"`; `bin/lock-versions.sh --update` copies it verbatim to `PYTHON_VERSION` in `versions.env` (no registry call); `.python-version` is authoritative for local tooling and a test asserts `.python-version` equals `PYTHON_VERSION`. Additionally `PYTHON_RUNTIME_IMAGE` — the §7.1 `contract-probe` image — must be `python:3.12-<variant>@sha256:…` with a matching minor. *Source of truth:* `versions.in.yaml`.

**I. §4.1 step 7's "per-project render lock" has no stated mechanism.** Decision: `fcntl.flock(fd, LOCK_EX | LOCK_NB)` on `.generated/.locks/{project_key}.lock`; contention exits `5`. Held across staging validation and publication. POSIX-only — a further reason for the WSL recommendation. `.generated/.locks/` is covered by the existing `.generated/*` ignore rule. *Source of truth:* `src/agentic_postgres/rendering.py`.

**J. §4.1 step 7 says "publish the staged set … with rollback protection" but §4.1's own note concedes several independent files cannot be replaced atomically.** Decision: publish by **directory swap**, not per-file rename — (1) `os.replace(.generated/{key}, .generated/.staging/{key}.backup.{n})` if a previous render exists, (2) `os.replace(staging_dir, .generated/{key})`, (3) on any exception, replace the backup back and re-raise, (4) on success, remove the backup. Two renames on one filesystem, and the exposure window contains no partially-written directory. The per-file `inputs` hash block §4.1 already requires remains as the torn-set detector. *Source of truth:* `src/agentic_postgres/rendering.py`; ADR-worthy, folded into `0002`.

**K. Staging directory naming is unspecified.** Decision: `.generated/.staging/{project_key}.{pid}.{token_hex(8)}/`, created with mode `0700`, removed unconditionally in a `finally`. Same filesystem as the publish target by construction.

**L. `rendered-summary.txt` has no content contract at all.** Decision: derived purely from the already-rendered `outputs.json`, human-readable, **no timestamps, no host names, no paths outside the repo**, and byte-identical across repeated renders with identical inputs — asserted by the same determinism test that covers `outputs.json`. It is the redacted summary §11 step 13 prints.

**M. `compose.env`'s exact key set is implied by §7.1 but never stated, and §7.2 requires the two env files be disjoint.** Decision: `compose.env` defines exactly `COMPOSE_PROJECT_NAME`, `EDGE_NETWORK_NAME`, `INTERNAL_NETWORK_NAME`, `POSTGRES_VOLUME_NAME`, and nothing else. `PYTHON_RUNTIME_IMAGE` and `TARGET_PLATFORM` come from `versions.env` only. The "protected" set of §6.4's last bullet is defined as *the exact key set of `versions.env`*; a test asserts the two key sets are disjoint in both directions and that `compose.env`'s key set is exactly the four names above.

**N. `.gitattributes` is absent from the §6 tree.** Decision: add it. Contents: `* text=auto eol=lf`, `*.sh text eol=lf`, `*.py text eol=lf`, `*.json text eol=lf`, `*.yaml text eol=lf`, `*.md text eol=lf`. Without this, the system-level `core.autocrlf=true` on this machine breaks every `#!/usr/bin/env bash` shebang on checkout and makes §3.7 rule 10's LF requirement unenforceable for anyone who clones from Windows. *This is an addition to the runbook's "required repository result"; I am flagging it rather than adding it quietly.*

**O. `tests/contract/test_naming.py` is absent from the §6 tree** even though §3.7 says "test it directly" and §8.5 lists four naming-related active tests. Decision: add it, marked `contract` so `-m "contract and not future"` picks it up. Also an addition to the required tree.

**P. `APG_ACCEPTANCE_SESSION` has no defined default.** Decision: defaults to `CURRENT_SESSION = 1` declared in `src/agentic_postgres/__init__.py`; the env var overrides. The gate sets it explicitly anyway. This keeps a bare `pytest` run behaving identically to the gate instead of erroring or silently skipping the policy check.

**Q. §12 "Shell scripts are executable" has no stated assertion method, and the obvious one is filesystem-dependent.** Decision: assert the **git index mode** — `git ls-files --stage -- deploy.sh bin/` must report `100755` for every `.sh` and for the `bin/*.py` entry points. This is filesystem-independent, survives a Windows clone, and is what actually determines the mode on checkout elsewhere. Filesystem `os.access(X_OK)` is not used.

**R. Exit code when the Docker CLI is absent during render.** Decision: `3` (missing local prerequisite), raised by `bin/compose.sh` and propagated by `deploy.sh`. Distinct from `5`, which is reserved for a Compose model that parses but violates contract. Also: `bin/compose.sh` probes daemon reachability before any subcommand that needs it and exits `3` with a clear message rather than surfacing a raw Docker error — see the §11 disagreement in §3 below.

**S. Which images are actually locked in Session 1.** Decision: PostgreSQL/pgvector, Traefik, PgBouncer, PostgREST, pgBackRest, Python runtime, Node runtime, Infisical, dbmate — the nine third-party/base images of §6.1, plus `TARGET_PLATFORM=linux/amd64` (host is x86_64). First-party images are explicitly out per §6.1. Package versions (FastAPI, FastMCP, Prisma, Scalar) are locked as version strings in `versions.env`, not digests, since no image exists to digest.

**T. `bin/compose.sh` env allowlist (§7.2's "preserving Docker client variables" is not enumerated).** Decision: implemented as `env -i` plus exactly `PATH`, `HOME`, `USER`, `DOCKER_HOST`, `DOCKER_CONTEXT`, `DOCKER_CONFIG`, `DOCKER_CERT_PATH`, `DOCKER_TLS_VERIFY`. Everything else — including every `COMPOSE_*` variable — is dropped. A test asserts that setting `COMPOSE_PROJECT_NAME=hijacked` in the caller's environment does not change `docker compose config`'s rendered project name.

### Conflicts between the source specification and the runbook

Both entries below are genuine contradictions, found on reading
`docs/source-specification.md` in full. Neither is a judgement call the
implementation gets to make quietly.

**U. Deployment timestamp in `outputs.json`.** Source specification §5.2 requires the rendered outputs to include "Deployment timestamp, template version, and locked component versions". Runbook §3.7 rule 11 requires the opposite: "Session 1 `outputs.json` contains no timestamp, so identical inputs and locks produce byte-identical output."

Decision: **the runbook wins for Session 1.** `outputs.json` carries no timestamp of any kind. Byte-identical reproducibility is an actively tested Session 1 contract, and a timestamp destroys it for no Session 1 benefit — nothing consumes a render time when no deployment has occurred. The timestamp requirement is satisfied outside the determinism boundary instead: `evidence/session-01.json` carries `completed_at`, and `versions.env` carries `APG_LOCKED_AT`.

If a later session genuinely needs a deployment timestamp in rendered output, it goes in a field the determinism test explicitly excludes, and it requires an ADR at that time. It does not get added to the deterministic body of `outputs.json`.

**V. `deploy.sh` argument grammar.** Source specification §1.4 step 7 and §13.1 use a positional form, `./deploy.sh project.yaml`. Runbook §2 mandates `--project FILE --capabilities FILE --render-only`.

Decision: **the runbook wins.** Its §2 audit correction 1 states the CLI was deliberately standardized, and the positional form cannot express the capability manifest or the mandatory render-only mode at all. Consequence to carry forward: the "fewer than 15 operator steps" happy path in source specification §1.4 must be transcribed into `docs/new-team-member.md` (Run 5) in the flag form, not copied verbatim. `tests/contract/test_cli_contract.py` asserts `deploy.sh` rejects a positional argument with exit `2` rather than silently treating it as a project path.

**Not conflicts, recorded so they are not mistaken for drift later.** The runbook's `project.yaml` (§3.1) adds `schema_version`, `pooled_public_cidrs`, `storage.prefix`, and `backup.repository_prefix` over source specification §5.1; its repository tree (§6) is substantially larger than §5.3; and its `0600` requirement (§4.2) is unconditional where §5.2 makes it conditional on credential-bearing content. All three are deliberate strengthenings, named in the runbook's own §2 audit corrections 2, 5, and 12. The stricter form governs.

---

## 3. Consistency strategy for the acceptance harness

The four-way constraint drifts because the runbook implies four independently hand-edited artifacts. The fix is to collapse it to **one hand-authored source plus one hand-authored reference table**, and make everything else either generated or verified.

**`tests/acceptance-registry.yaml` is the single hand-authored source of requirement identity.** It already carries `id`, `priority`, `target_session`, `test_nodeids`, `description` — that is the full requirement catalog. It is the only file where a requirement ID is created.

| Artifact | Status | Mechanism |
|---|---|---|
| `tests/acceptance-registry.yaml` | **Hand-authored** | The source. |
| Test files carrying `future(session=…, requirement=…)` | **Hand-authored** | They are real code; they cannot be generated. |
| P0/P1/P2 requirement table in `docs/product-contract.md` | **Generated** | Marker block `<!-- BEGIN GENERATED: requirements -->…<!-- END GENERATED: requirements -->`, written by `bin/render-acceptance-matrix.py --requirements --write`, drift-checked by `--check`. Prose around the block stays hand-authored. |
| Numeric bounds table in `docs/product-contract.md` | **Generated** | Separate marker block, from `schemas/project.schema.json` via `bin/render-config.py --bounds-doc` (decision **E**). |
| `docs/acceptance-matrix.md` | **Generated, whole file** | `bin/render-acceptance-matrix.py --write` / `--check`. |
| `docs/threat-model.md` | **Hand-authored, referentially verified** | See below. |
| Marker kwargs ↔ registry | **Verified** | Bidirectional test. |
| Node IDs ↔ actual collection | **Verified** | Subprocess collection, set comparison. |

**Why the product-contract table is generated rather than parsed.** §8.4 requires the registry test to fail when "a P0 requirement in `docs/product-contract.md` is absent from the registry". Implemented literally that means parsing hand-written markdown, which is fragile in exactly the way that produces false green. Generating the table from the registry makes the check structural: the table cannot contain a requirement the registry lacks, because the registry produced it. The drift check then reduces to a byte comparison.

**Why the threat model stays hand-authored.** Its content — attacker capability, prevention, detection, residual risk — is analysis, not derivable data. What *is* checkable is referential integrity. So: `docs/threat-model.md` must contain one pipe table with the exact column headers §9 specifies; `tests/contract/test_acceptance_registry.py` parses only the `Acceptance requirement IDs` and `Acceptance test node IDs` columns (comma-separated) and asserts every ID appears in the registry and every node ID appears in the collected set. A ~30-line deterministic parser over a table whose format is itself contract-tested. Nothing about the analytic content is parsed.

**The collection check.** `test_acceptance_registry.py` runs `python -m pytest --collect-only -q` **once** in a subprocess, module-scoped-cached, and compares the resulting node-ID set against the union of registry `test_nodeids`. Both directions are asserted: no registry node ID is uncollectible, and no test carrying a `p0` marker is missing from the registry. Because this spawns a nested pytest, that module is excluded from any future `-n auto` run — consistent with §8.1's "parallel execution is not enabled by default".

**Marker ↔ registry.** `test_future_marker_policy.py` walks collected items via a session fixture, reads each `future` marker's `session`/`requirement`, and asserts the registry entry for that requirement has a matching `target_session`. It also asserts §4.6's gate rule against `APG_ACCEPTANCE_SESSION`. Testing that an *invalid* marker aborts collection, and that *removing* a marker activates a failing body (§12), both require a subprocess pytest against a temporary test file — they cannot be done in-process because `pytest.UsageError` from the collection hook aborts the whole run. That subprocess harness is written once and used by both.

**§12 "acceptance matrix generation is drift-free."** `bin/render-acceptance-matrix.py` gets `--write` and `--check`. `--check` regenerates into memory and byte-compares; it never writes. The gate runs `--check` only, because the gate's step 1 already demands a clean tree and a self-healing generator would dirty it. To make that ergonomic rather than punitive, `.pre-commit-config.yaml` gets a local hook running `--write` for all three generated blocks, so drift is corrected at commit time and the gate only ever confirms.

*Disagreement with the runbook:* §11's gate ordering means a stale generated doc fails the gate with no in-gate remedy. That is correct behavior, but it is only workable with the pre-commit hook above, which the runbook does not require. I am adding it.

---

## 4. Build order — five runs

The runbook's §10 nine-commit sequence defers **all** tests to commit 7. That is not executable-as-you-go, and it directly conflicts with treating `naming.py` as load-bearing: under §10, naming is written in commit 4 and first tested in commit 7, after `rendering.py` already consumes it. **I am reordering: tests ship in the same commit as the code they cover.** The nine commit *messages* are preserved; test files migrate into the commit that introduces their subject.

### Run 1 — Baseline, contract, skeleton, dependency lock
*Runbook phases: 0, 1, 2, plus §5.3 hoisted forward. Commits 1–2.*

Creates:
`.gitattributes`, `.gitignore`, `.editorconfig`, `.python-version`, `VERSION`, `README.md` (skeleton), `pyproject.toml`, `pytest.ini`, `.pre-commit-config.yaml`,
`docs/source-specification.md`, `docs/source-specification.sha256`, `docs/plans/session-01-implementation-plan.md`, `docs/product-contract.md`, `docs/decisions/README.md`, `docs/decisions/0001-product-shape.md`, `0002-configuration-authority.md`, `0003-example-domain.md`,
`requirements-dev.in`, `requirements-dev.txt`, `bin/lock-dev-deps.sh`,
`deploy.sh` (arg parsing + exit 10 path only), `bin/bootstrap-providers.sh`, `bin/connect.sh`, `bin/migrate.sh`, `bin/restore-test.sh`, `bin/doctor.sh`, `bin/smoke-test.sh`,
`src/agentic_postgres/__init__.py` (with `CURRENT_SESSION`), empty `config.py`/`naming.py`/`rendering.py`/`evidence.py`,
`.generated/.gitkeep`, `evidence/.gitkeep`, `migrations/.gitkeep`, `services/{auth-api,docs,mcp}/.gitkeep`.

Verify:
```
shellcheck deploy.sh bin/*.sh                                  # 0
./deploy.sh --help                                             # 0
./deploy.sh --project p.yaml --capabilities c.yaml             # 10
bin/doctor.sh                                                  # 0
bin/lock-dev-deps.sh --check                                   # 0
python -m pip install --require-hashes -r requirements-dev.txt  # 0
python -m ruff check src bin tests && python -m ruff format --check src bin tests  # 0
git ls-files --stage -- deploy.sh bin/ | grep -cv '^100755'    # 1 (grep finds nothing)
```
Deferred: all schemas, all rendering, `compose.sh`, `lock-versions.sh`, `session-01-check.sh`, the registry, every test beyond ruff cleanliness.

### Run 2 — `naming.py` first, then strict manifest validation
*Runbook phases: 3 (all), plus §3.7 hoisted ahead of everything that consumes it. Commit 3 + the naming half of commit 4.*

Order within the run is fixed: `naming.py` + `tests/contract/test_naming.py` land and pass **before** `config.py` is written, and `config.py` lands before either fixture manifest is finalized.

Creates:
`src/agentic_postgres/naming.py`, `src/agentic_postgres/config.py`,
`schemas/project.schema.json`, `schemas/capabilities.schema.json`,
`project.example.yaml`, `project.second.example.yaml`, `capabilities.example.yaml`,
`tests/contract/test_naming.py`, `test_yaml_parser.py`, `test_project_manifest.py`, `test_capabilities_manifest.py`,
`tests/conftest.py` (future-marker hook only, so the markers exist from here on),
`bin/render-config.py --validate-only` and `--bounds-doc`.
Modifies: `docs/product-contract.md` (generated bounds block), `pytest.ini` (markers).

Verify:
```
python -m pytest -q tests/contract/test_naming.py              # 0
python -m pytest -q -m "contract and not future"               # 0
python bin/render-config.py --project project.example.yaml \
  --capabilities capabilities.example.yaml --validate-only     # 0
python bin/render-config.py --project project.second.example.yaml \
  --capabilities capabilities.example.yaml --validate-only     # 0
python bin/render-config.py --bounds-doc --check               # 0
python -m ruff check src bin tests                             # 0
```
Deferred: `outputs.json`, staging/publish, Compose, version locks, registry.

**How `naming.py` is verified — the three properties you named.**

*Per-role independent derivation, no role past 63 bytes.* The fixtures do **not** exercise this, and I want to correct the premise before it becomes a false sense of coverage: `apg_` (4) + `fixture_alpine_dev` (18) + `_` (1) + `postgrest_authenticator` (23) = **46 bytes** — the longest role either fixture produces. The fixtures exercise §8 *collision*, which is real and valuable, but they never touch truncation. Truncation is only reachable at the top of the input space: slug is `^[a-z][a-z0-9-]{2,30}$` → 31 chars max, environment is `^[a-z][a-z0-9-]{1,15}$` → 16 max, so `project_key` reaches 48 and `apg_` + 48 + `_` + 23 = **76 bytes**, comfortably over the limit. So the test corpus is `{alpha, alpine, max-length synthetic, near-boundary synthetics at 62/63/64 bytes}` × all 13 roles, asserting `len(name.encode("utf-8")) <= 63` and that the 13 names are pairwise distinct for every input. Independence is asserted structurally: for the max-length input, `anon` and `agent_reader` must have **different** trailing hash segments — which is only true if each full role name is hashed, not a shared truncated prefix with a suffix appended.

*Truncation format.* A golden-vector test with hard-coded expected strings: for a stated `(context, untruncated_value, limit, separator)` the result must equal `untruncated[:limit-11] + sep + sha256(f"{context}:{untruncated_value}".encode()).hexdigest()[:10]`, with `len(result) == limit` exactly. Hard-coding the expected output means a later refactor cannot silently change the algorithm and still pass. A second test asserts two distinct inputs sharing a 60-character prefix produce different truncated results — this is the actual collision property, and it is what `fixture-alpha`/`fixture-alpine` should be understood as a shallow instance of. A third asserts `PYTHONHASHSEED` has no effect, run as a subprocess with the seed set to `0` and to `1`, guarding §3.7 rule 8.

*Byte-identical canonical JSON.* Render `project.example.yaml` twice into two distinct temp directories and assert `read_bytes()` equality — not `json.loads` equality, which would mask ordering and whitespace changes. Additionally assert `b"\r\n" not in data`, `data.endswith(b"\n")`, `data.decode("utf-8")` round-trips, `json.dumps(json.loads(data), sort_keys=True, ensure_ascii=False, indent=2) + "\n"` reproduces the bytes exactly, and no key in the document matches `/(_at|timestamp|generated_at|time)$/`. Cross-process determinism is asserted by running one of the two renders through `subprocess`, so nothing in-process (module caches, dict identity) can hide a nondeterminism. The same byte-equality assertion covers `rendered-summary.txt` per decision **L**. In this run these tests target `naming.py`'s canonical serializer directly; in Run 3 they extend to the published files.

### Run 3 — Transactional render and `outputs.json`
*Runbook phases: 4, 5, 11. Remainder of commit 4.*

Creates:
`src/agentic_postgres/rendering.py`, `schemas/outputs.schema.json`,
`tests/contract/test_output_schema.py`, `test_render_atomicity.py`, `test_render_isolation.py`.
Modifies: `deploy.sh` (full §11 fourteen-step flow), `bin/render-config.py`.

Verify:
```
./deploy.sh --project project.example.yaml \
  --capabilities capabilities.example.yaml --render-only        # 0
./deploy.sh --project project.second.example.yaml \
  --capabilities capabilities.example.yaml --render-only        # 0
python -m pytest -q tests/contract/test_output_schema.py \
  tests/contract/test_render_atomicity.py \
  tests/contract/test_render_isolation.py                       # 0
python -m pytest -q -m "contract and not future"                # 0
stat -c '%a' .generated/fixture-alpha-dev/*                     # 600 600 600
jq -e '.database.pooled.status=="unavailable" and .database.pooled.url==null' \
  .generated/fixture-alpha-dev/outputs.json                     # 0
```
Note: §4.1 step 6 (validate staged Compose) is stubbed in this run and wired in Run 4 — `deploy.sh` calls a `bin/compose.sh` that does not exist yet, so the call site is written but gated behind a "compose model not yet present" branch that Run 4 removes. This is the one deliberate seam between runs; it is closed, not left open.
Deferred: version locks, Compose model, registry, CI, gate, evidence.

### Run 4 — Version locks and the validation-only Compose model
*Runbook phases: 6, 7. Commits 5–6.*

Creates:
`versions.in.yaml`, `versions.env`, `bin/lock-versions.sh`, `compose.yaml`, `bin/compose.sh`,
`tests/contract/test_version_lock.py`, `test_compose_contract.py`,
`docs/decisions/0004-version-lock-format.md`.
Modifies: `deploy.sh` (remove the Run 3 seam), `bin/doctor.sh` (docker/buildx/shellcheck/jq checks).

Verify:
```
bin/lock-versions.sh --update                                   # 0  (network; run once)
bin/lock-versions.sh --check                                    # 0  (offline)
python -m pytest -q tests/contract/test_version_lock.py \
  tests/contract/test_compose_contract.py                       # 0
bin/compose.sh .generated/fixture-alpha-dev --profile contract config >/dev/null   # 0
bin/compose.sh .generated/fixture-alpine-dev --profile contract config >/dev/null  # 0
test -z "$(bin/compose.sh .generated/fixture-alpha-dev ps --quiet)"                # 0
bin/compose.sh .generated/fixture-alpha-dev up -d                                  # 10
COMPOSE_PROJECT_NAME=hijacked bin/compose.sh .generated/fixture-alpha-dev \
  --profile contract config | grep -q 'apg-fixture-alpha-dev'                      # 0
python -m pytest -q -m "contract and not future"                                   # 0
```
The last two are the §7.2 proofs: container-starting subcommands refuse with `10`, and an inherited protected variable cannot override the lock.
Deferred: registry, threat model, CI, gate, evidence.

### Run 5 — Acceptance harness, threat model, CI, gate, evidence
*Runbook phases: 8, 9, 10, 12. Commits 7–9.*

Creates:
`tests/acceptance-registry.yaml`,
`tests/contract/test_acceptance_registry.py`, `test_future_marker_policy.py`, `test_cli_contract.py`, `test_repository_contract.py`,
`tests/integration/test_future_{api,database_clients,mcp,storage}.py`, `tests/recovery/test_future_pitr.py`, `tests/security/test_future_security_boundaries.py`,
`bin/render-acceptance-matrix.py`, `bin/write-session-evidence.py`, `bin/session-01-check.sh`,
`docs/threat-model.md`, `docs/security-acceptance.md`, `docs/capability-plan.md`, `docs/new-team-member.md`, `docs/acceptance-matrix.md` (generated),
`.github/workflows/ci.yml`.
Modifies: `tests/conftest.py` (marker validation), `docs/product-contract.md` (generated requirements block), `README.md` (full §12 content), `.pre-commit-config.yaml`.

Verify:
```
python -m pytest --collect-only -q -m p0                        # 0, non-empty
python -m pytest -q -m future                                   # 0, all skipped
python -m pytest -q tests/contract/test_acceptance_registry.py  # 0
python -m pytest -q tests/contract/test_future_marker_policy.py # 0
python bin/render-acceptance-matrix.py --check                  # 0
python bin/render-config.py --bounds-doc --check                # 0
git status --porcelain                                          # empty
bin/session-01-check.sh                                         # 0
jq -e '.status=="passed" and .project_scoped_collision_count==0 and .floating_image_references==0' \
  evidence/session-01.json                                      # 0
bin/compose.sh .generated/fixture-alpha-dev ps                  # 0, no containers
```
Deferred to Session 2: nothing from Session 1's scope. The `future` placeholders are deferred *by design*, each with an owning session and registry entry.

---

## 5. Risks and stop conditions

**Halt work — do not work around.**

1. **An image digest will not resolve for `linux/amd64`.** §15 is explicit and I agree: do not substitute a floating tag, do not fall back to a single-arch manifest silently, do not drop the image from the inventory to make `--check` pass. Halt, and either change the candidate tag in `versions.in.yaml` deliberately or record an ADR removing that component from Session 1's inventory. Verified reachable in setup step 3.
2. **A dev dependency cannot be hash-locked** — no wheel for cp312/linux, or an sdist-only package that needs the absent `gcc`. Do not install it unhashed, do not add `--no-deps`, do not drop `--require-hashes`. Halt and change the dependency.
3. **`chmod 0600` is not observable.** If setup step 9 reports `666`, the repository is on the wrong filesystem. Do not add `@pytest.mark.skipif(sys.platform == "win32")` to the mode test — that is the single conditional whose cost I described in §1.4. Halt and relocate.
4. **`env -i` in `bin/compose.sh` breaks Docker context resolution.** If the allowlist in decision **T** is insufficient, halt and extend the allowlist deliberately with a documented reason per variable. Do not revert to passing the inherited environment through, and do not switch to `env -u` — that reopens §9 check 14.
5. **A P0 requirement has no test node ID that anyone can actually name.** Do not invent a plausible-looking node ID to satisfy §8.4's "no P0 requirement may have zero tests". A registry entry pointing at a test nobody will ever write is worse than a visible gap. Halt, and either demote the requirement to P1 with an ADR or write the placeholder.
6. **The registry's collection check cannot be made deterministic.** If the nested `pytest --collect-only` subprocess is flaky or unbearably slow, do not weaken it to "the file exists and contains the function name" — that is a string search that passes on a commented-out test. Halt and fix the subprocess harness.
7. **Two distinct inputs collide after truncation.** 10 hex characters is 40 bits, so this should never happen for a hand-authored corpus; if a test finds one, it means the hashed `"{context}:{value}"` string is not what §3.7 rule 7 describes. Halt, do not widen the hash reactively, find the bug first.
8. **`git ls-files --stage` will not report `100755`.** Environment problem, not a test problem. Halt.
9. **An active Session 1 test cannot pass.** §15 already says this and I want it restated as a hard rule: do not relabel it `future` to get the gate green. `future` means "a later session owns this", not "this is inconvenient today".

**Proceed with a documented assumption — do not halt.**

- Compose is v5.1.3, not "v2" (§5.2). Recorded as a `>=` floor per §1.2.
- `httpx` and `pydantic` are in §8.1's mandatory dev-dependency list but nothing in Session 1 imports either. I think that is wrong — it adds transitive packages to the hash-lock surface for no Session 1 benefit — but the list is explicit, so I am complying and noting the cost here rather than silently trimming it.
- §11's gate calls `bin/compose.sh … ps --quiet`, which needs a live Docker **daemon**, unlike `config` which is client-side only. That makes an otherwise-offline contract gate daemon-dependent. I am keeping the check (it is the "no containers running" proof) and adding a daemon reachability probe that exits `3` with a clear message, per decision **R**.

---

## Open items requiring your decision before Run 1

None. Every ambiguity I found is closed in §2 with a named owner file. If implementation surfaces a new one, it comes back to §2 as a new lettered row and an ADR — it does not get resolved inline.
