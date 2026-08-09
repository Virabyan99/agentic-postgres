# New team member guide

Fourteen steps, each labelled **available now** or **future session**. Nothing
labelled "available now" requires editing a source file.

This is the transcription of source specification §1.4 into the CLI this
repository actually has. The specification's positional form
(`./deploy.sh project.yaml`) is not accepted — see decision V in
[the implementation plan](plans/session-01-implementation-plan.md) — because it
cannot express the capability manifest or the mandatory render-only mode.

## Before you start

This repository requires POSIX filesystem semantics: `0600` output modes are a
tested contract and `flock` guards render publication. On Windows, work inside
WSL2 with the repository on the **Linux** filesystem — not under `/mnt/c`, and
not in a OneDrive-synced folder. Implementation plan §1 has the measurements.

---

### 1. Clone the repository — *available now*

```bash
git clone <repository-url> && cd agentic-postgres
```

### 2. Install the local toolchain — *available now*

```bash
sudo apt-get update && sudo apt-get install -y shellcheck jq
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12
```

### 3. Create the pinned environment — *available now*

```bash
uv venv --seed --python 3.12 .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.txt
```

`--seed` installs pip, which the hash-locked install needs. `--require-hashes`
means a tampered or substituted wheel fails rather than installs.

### 4. Confirm the workstation is ready — *available now*

```bash
bin/doctor.sh
```

Exits `3` and names anything missing. It prints tool versions and repository
paths only — never the environment, never a secret.

### 5. Verify you have the specification you think you have — *available now*

```bash
sha256sum -c docs/source-specification.sha256
```

### 6. Read the contract — *available now*

[Product contract](product-contract.md), then
[the three founding ADRs](decisions/README.md). The requirement catalog and the
numeric bounds table are generated; the prose around them is not.

### 7. Copy and edit the manifests — *available now*

```bash
cp project.example.yaml project.yaml
cp capabilities.example.yaml capabilities.yaml
```

Set the slug, environment, and domain. `capabilities.yaml` stays empty: no
capability can be enabled until a live API contract exists to validate it
against.

**Neither file may ever contain a secret.** The loader rejects secret-bearing
keys at any depth.

### 8. Render — *available now*

```bash
./deploy.sh --project project.yaml --capabilities capabilities.yaml --render-only
```

`--render-only` is mandatory. Without it the command exits `10` and tells you
deployment begins in Session 2. It does not partially deploy.

### 9. Inspect the output — *available now*

```bash
jq . .generated/<project-key>/outputs.json
cat  .generated/<project-key>/rendered-summary.txt
```

Database endpoints read `"status": "unavailable"` with null host, port, URL, and
secret reference. That is correct, not incomplete — there is no tunnel host or
bound port yet, and a placeholder that looked like a DSN would eventually be
pasted into a connection dialog.

### 10. Validate the Compose model — *available now*

```bash
bin/compose.sh .generated/<project-key> --profile contract config
bin/compose.sh .generated/<project-key> ps --quiet     # empty
```

Always through the wrapper. Calling `docker compose` directly lets inherited
shell variables override the generated identity and the locked digests.

### 11. Run the gate — *available now*

```bash
bin/session-01-check.sh
```

Requires a clean tracked tree. CI runs this exact script; there is no second,
divergent definition of "passing".

### 12. Bootstrap providers — *implemented in Session 2*

`bin/bootstrap-providers.sh` is the only command permitted to provision
external resources. It documented its future inputs and exited `10` when this
guide was written; Session 2 implemented it, so a bare invocation is now
missing input (`2`) rather than an unavailable capability.

### 13. Connect to the database and run migrations — *implemented in Sessions 3–4*

`bin/migrate.sh` left the stub list in Session 3 and `bin/connect.sh` in
Session 4; both are real commands with real exit codes. Migrations always use
the direct endpoint; transaction pooling breaks DDL and advisory-lock
semantics.

`bin/connect.sh` opens an SSH forward to one *access profile* and records it,
and defaults to `runtime_direct` — the application role. It prints no password
under any flag: `exec` puts the credential in a `0600` file and names it to the
child through `PGPASSFILE`. `bin/restore-test.sh` is now the only command still
documenting a future capability.

### 14. Rehearse a restore — *future session (10)*

`bin/restore-test.sh` performs a timestamp-targeted restore into a disposable
volume and never touches the active one. It documents that contract and exits
`10` today.

---

## What "done" looks like today

Steps 1–11 complete with no source edits and no undocumented commands. You have
two rendered projects with provably disjoint identities, an immutable image
lock, and a gate that CI runs identically.

You do not have a running database. That is Session 3.

## If something fails

| Symptom | Cause | Fix |
|---|---|---|
| `bad interpreter: /usr/bin/env bash^M` | Cloned on Windows without `.gitattributes` honoured | `git config core.autocrlf false && git checkout -- .` |
| `python resolves to a Windows interpreter` | WSL inherited the Windows `PATH` | `source .venv/bin/activate` |
| `chmod 600` reports `666` | Repository is on NTFS or a `/mnt/c` mount | Move it to the Linux filesystem |
| `lock-versions: BLOCKED` | A digest will not resolve for the target platform | Do not substitute a tag; change the candidate deliberately |
| Gate fails on a clean checkout | Generated documentation drifted | `python bin/render-acceptance-matrix.py --write` |
