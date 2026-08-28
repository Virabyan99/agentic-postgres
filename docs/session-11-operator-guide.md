# Session 11 — the operator guide

Deployment, operations and log correlation: a deploy that refuses before it
changes anything, a redeploy that preserves what the last one wrote, a deployed
diagnosis, and one request id spanning ingress, the API and the audit record.

**Derived from `docs/session-10-operator-guide.md` by diff, not retyped.** D505
and D507 were both flags lost to retyping the previous session's guide, D602 was
a step the page anticipated and never gave — and **this session produced a third
instance, D678**, where `--through-session 5` survived from a Session 5 guide
into a Session 11 procedure in three places. Steps 1 through 3 below are Session
10's text with only the release changed; everything else was rewritten because
the trip changed it.

---

## 0. What Session 11 adds, and what it needs from you

Four things reach the deployment:

* **A step 0 preflight** in `deploy-project.py`. It observes every prerequisite,
  reports **all** the absent ones together, and changes nothing — so a deploy
  that cannot succeed says so before it renders, rather than failing on the
  first missing thing after it has already written.
* **`bin/doctor.sh --project <key>`**, which now answers whether a *deployed*
  system is well: containers, route, TLS, the cluster and the pooler,
  migrations, the backup repository, the WAL archiver, disk headroom.
* **One request id on every response**, minted by `StampRequestId` and readable
  in Traefik's access log, so ingress and the API can be joined.
* **Migration 0022**, which closes D500: the `database`-source audit row now
  carries the `request_id`, so both records for one write join on it.

**What it needs from you:** two maintenance windows for the credential
rotations, one Infisical edit per credential, and a terminal with `sudo`. The
deploy itself is unchanged in shape from Session 10.

**What it does not need:** a new bucket, a new token, a DNS change, or an ACME
cycle. Nothing here touches a provider except the two credential values you
replace by hand.

---

## 1. What is irreversible, and the ordering that matters

**Migration 0022.** Released, so fix-forward only; its down block raises AP900.
It replaces both write RPCs (`api.create_note`, `api.update_task_status`) to
record `app_private.agent_request_id()`. A malformed caller-supplied header
records `NULL` and the write proceeds — the guard tests the shape before casting,
because an unguarded cast raises `22P02` and takes the caller's own row with it
(D633).

**The credential rotations.** The pre-rotation value **cannot be recovered**
once you replace it at the provider. Capture it to a root-only file *first*. A
proof you cannot admit is a proof that skips, and a skip is not a pass — which
is how this window stayed red for five sessions.

**The ordering, and it is the whole of it:**

1. Capture the current value to `/root/rotated-*`.
2. Replace the value at the provider, by hand, and **confirm it saved**.
3. Stop the project, if the credential is one a container mounts.
4. Materialize, then deploy.
5. Admit the proof with the matching `--rotated-*-from-file` flag.

**Nothing in this repository sets a value at the provider** (D249).
`bootstrap-providers.sh --apply` creates what is missing and leaves what exists
alone, deliberately. Step 2 is done by hand in Infisical.

---

## 2. What must NOT be attempted this session

**Do not attempt the signing-key rotation.** It cannot be prepared, and this was
measured with a control rather than assumed (**D683**):

* `jwt_keys.MAX_VERIFICATION_KEYS` is 2. `build_jwks` accepts two keys and
  refuses three with *"3 verification keys, above the ceiling of 2."*
* `render-jwks.py` appends the **bootstrap issuer's key unconditionally** — the
  auth service's key and the prepared key are each guarded by `is_file()`, that
  one is not. So the set has held two keys permanently since the auth service
  came into existence in Session 6.
* A prepared key would be the third, and the deploy would fail rendering the
  JWKS.
* `retire` cannot free the slot: `retire_after` is `None` on the deployment and
  `retire_rotation` refuses with *"no rotation is in flight; there is nothing to
  retire."*

The comment at `render-jwks.py:214` saying that key is *"live until §4's
retirement"* points at a plan section, **not at an implementation**. Retiring the
bootstrap issuer is a new capability in a verifier-critical path; it needs an ADR
and a run of its own. `SEC-BOOT-001` stays red and `bootstrap_identity` with it.

**Do not pass `--through-session 5` anywhere** (D678). The rotation procedure in
`docs/api-operations.md` says 5 in three places and was right in Session 5. On a
Session 11 deployment:

| Command | With 5 | Use |
|---|---|---|
| `project-runtime.sh … down` | brings down only the Session-5 services, leaving `mcp`, `storage` and the backup plane on the superseded generation — D253 one plane over | `--through-session 11` |
| `materialize-secrets.sh` | writes a generation missing every secret added since Session 5 | `--session 11` |
| `deploy.sh` | renders a Session-5 `outputs.json`, dropping the blocks `doctor.sh` and most current proofs read | `--through-session 11` |

**Do not pipe a deploy into `tee`.** A pipeline gives `docker exec -i psql` a
terminal stdin and the deploy stops in state `T+` (SIGTTIN) — measured this
session, eight minutes before anyone looked. Redirect the deploy's own output to
a file, or put `< /dev/null` on it.

---

## 3. Three things the gate does that you should know about in advance

**It verifies; it does not deploy** (D20). A gate that deploys what it measures
cannot be re-run to confirm a fix.

**Host mode needs project B's outputs even though no Session 11 proof reads
them.** `claims_through_session(11)` is cumulative, and the claims inherited
from Sessions 4–10 are measured over two projects. Project B may lag at Session
10: Session 11 does **not** move the outputs version, so a v13 document is
current whichever session deployed it.

**The rotation flags are what admit the rotation proofs.** Pass
`--rotated-authenticator-from-file` and `--rotated-docs-from-file`. Do **not**
pass `--rotated-jwt-from-file`: there is no rotation to declare, and its proof
will skip. A skip reports `not_run`, which is the evidence model working.

---

## 4. The host sequence, in order

### Step 1 — Transport the release

**The bundle is named for the release, and that is not cosmetic** (D504). The
generic `/tmp/apg.bundle` collides: `/tmp` is sticky and `op` cannot overwrite a
file it does not own. The `scp` refuses — loudly — and the *next* command then
succeeds against the stale file and checks out a **previous** release.

```bash
# On the workstation:
wsl bash -lc "cd ~/projects/agentic-postgres && SHA=\$(git rev-parse --short HEAD) && \
  git bundle create /tmp/apg-\${SHA}.bundle main && echo \"bundled \${SHA}\""
wsl bash -lc "scp -i ~/.ssh/agentic_postgres_ed25519 /tmp/apg-<sha>.bundle op@62.238.99.122:/tmp/"
```

Then, on the host:

```bash
cd ~op/agentic-postgres          # /home/op/agentic-postgres, NOT ~/op/...
git fetch /tmp/apg-<sha>.bundle main
git rev-parse FETCH_HEAD         # confirm this is the sha you bundled, BEFORE the checkout
git checkout -B main FETCH_HEAD
```

**Confirm `git rev-parse FETCH_HEAD` before the checkout, not the `release` line
after it.** A failed `scp` followed by a successful `git fetch` of a stale file
moves the host **backwards** with both commands exiting 0.

### Step 2 — Re-render all four projects, on the host

```bash
for f in project.alpha.yaml project.beta.yaml project.example.yaml project.second.example.yaml; do
  ./deploy.sh --project "$f" --capabilities capabilities.yaml --render-only
done
```

**All four, and on the host rather than the workstation** (D462, D383).
`.generated/` is gitignored and never transported, so a stale render on the host
is a fixture from a previous release.

### Step 3 — Sync the host venv

```bash
cd ~op/agentic-postgres && . .venv/bin/activate && bin/lock-dev-deps.sh --check
```

Five sessions have paid for skipping this (D384, D297). Confirm it; do not
assume it. `uv` is on `~/.local/bin`, so this needs a **login shell** — over SSH,
`bash -lc "…"`.

### Step 4 — Deploy through session 11

```bash
sudo ./deploy.sh --host host.yaml --project project.alpha.yaml \
  --capabilities capabilities.yaml --through-session 11 \
  < /dev/null > /tmp/deploy.txt 2>&1
```

**Deploy twice if the first leaves anything unready**, and only then (D326). The
first deploy that starts a new container publishes `unavailable`; the redeploy
publishes `ready`. Making the second pass unconditional and fatal stopped a trip
this session whose first deploy had already exited 0.

**Step 0 runs first and changes nothing.** If a prerequisite is absent it reports
every absent one together with a copy-pasteable remedy and exits 4, before the
render.

### Step 5 — The rotation windows

Two credentials, and they share one window (**D679**). The guide's reason for
separate windows is about the declaration flags, which are already separate and
each carry their own false-declaration control; the two share no plane, no file
and no failure.

**The generation directory is derived, never typed** — it changes on every
materialization, and a hard-coded one silently names a superseded generation
(D213):

```bash
gen() {
  sudo python3 -c "
import json, sys
from pathlib import Path
root = Path('/var/lib/agentic-postgres/secrets') / sys.argv[1]
print(root / 'generations' /
      json.loads((root / 'active-secret-generation.json').read_text())['generation_id'])
" "$1"
}
```

**Capture first.** The authenticator's copy is written in `pgpass` format (ADR
0056), so the file holds `*:*:*:*:<password>` and the proof compares your
declaration against the *password*. Declaring the whole line would make the
false-declaration control incapable of failing (ADR 0075):

```bash
sudo sh -c "cut -d: -f5- '$(gen alpha-dev)/postgrest/postgrest_authenticator_pgpass' \
  > /root/rotated-auth" && sudo chmod 0400 /root/rotated-auth
sudo cp "$(gen alpha-dev)/_root/docs_basic_auth_password" /root/rotated-docs
sudo chmod 0400 /root/rotated-docs
```

**Check for leftovers before capturing.** Declaration files from an earlier
window survive, and **the proofs cannot detect a stale one**: their control asks
only whether the declared value differs from the active one, which a leftover
satisfies *without any rotation having happened*. It would be admitted as proof
of a rotation this window never performed. Compare each existing file against
the value that is active now, then replace it.

**Then, at the provider.** Each project's Infisical binding is its own — read it
rather than assuming, since the id is what `materialize-secrets.py` uses and a
name that looks right is not evidence:

```bash
sudo python3 -c "
import json, sys
from pathlib import Path
s = json.loads(Path('/etc/agentic-postgres/projects/alpha-dev/bootstrap-state.json').read_text())
print('project    :', s['infisical_project_id'])
print('environment:', s['environment_slug'])
"
```

| Credential | Folder | Key |
|---|---|---|
| authenticator | `/database` | `APG_POSTGREST_AUTHENTICATOR_PASSWORD` |
| documentation | `/runtime` | `APG_DOCS_BASIC_AUTH_PASSWORD` |

New values are 64-character hex — `python3 -c 'import secrets; print(secrets.token_hex(32))'`,
the same generator `bootstrap-providers.py` uses.

**Then stop the project, materialize, and deploy.** The `down` is D253 and is
still live with no code fix: `resume` runs `compose up` without
`--force-recreate`, so a container keeps the generation it started with while the
bootstrap plane moves the cluster's password underneath it. Without it PostgREST
crash-loops and the route answers 502.

```bash
sudo bin/project-runtime.sh --host host.yaml --project-key alpha-dev \
  --through-session 11 down
sudo bin/materialize-secrets.sh --project project.alpha.yaml \
  --requirements secrets.required.yaml --session 11
sudo ./deploy.sh --host host.yaml --project project.alpha.yaml \
  --capabilities capabilities.yaml --through-session 11 < /dev/null
```

**Assert the generation id moved.** If it did not, nothing was materialized —
the provider did not take the edit — and deploying anyway produces a run that
looks identical to a successful rotation.

### Step 6 — The doctor

```bash
sudo bin/doctor.sh --project alpha-dev
```

Eight checks. `0` means well, `6` means a check failed or could not run.
`--verbose` prints the evidence pairs behind each verdict and prints no
additional secret — that is a scanned property, not a promise.

### Step 7 — The gate

```bash
sudo bin/session-11-check.sh --mode host --host host.yaml \
  --project-a-outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json \
  --project-b-outputs /etc/agentic-postgres/projects/beta-dev/outputs.json \
  --rotated-authenticator-from-file /root/rotated-auth \
  --rotated-docs-from-file /root/rotated-docs
```

Then external mode, which runs **off-host**, needs no TTY and no root:

```bash
bin/session-11-check.sh --mode external --public-ipv4 62.238.99.122 \
  --project-a-outputs ./alpha-dev-outputs.json \
  --ssh-destination op@62.238.99.122
```

`--ssh-destination` is **`op@`** (D466). The broker grants one enumerated account
and the read-only one is refused.

---

## 5. What the evidence will say, and what it will not

**`api_authorization` goes green.** `SEC-DOCS-001` was its only unmet member and
its rotation half is proved.

**`bootstrap_identity` stays red**, and D683 is the reason. Its signing-key proof
will report `not_run`, because the rotation could not be performed. This is the
first session in which that claim is red for a *characterised* reason rather than
a carried-in one.

**`DEP-001` is not claimed** (D669). Its offline half is proved and its live half
was not run: Run 8's rehearsal reached the host baseline and the edge plane on a
genuinely fresh machine and stopped, because the remaining leg needed scratch
provider state to exercise commands the live host already runs on every deploy. A
claim on the offline half alone would promise a deployment nobody performed.
Session 12 inherits it beside `DX-001`.

**Four claims are recorded**: `deployment_preflight`, `deployment_convergence`,
`operational_diagnosis`, `log_correlation`.

---

## 6. If something goes wrong

**The deploy exits 4 before rendering.** That is step 0, working. It has listed
every absent prerequisite with a remedy; nothing was written.

**The deploy exits 5 on a provider read.** `TimeoutError` reading Infisical is a
transient in an external service. Re-run. It is only fatal if you made the second
pass unconditional, which the guide does not.

**The deploy appears to hang.** Check for state `T+`: a pipeline gave a child a
terminal stdin. Kill it, and re-run with `< /dev/null`.

**A rotation proof fails with `401 PT401`.** The token was refused before the RPC
ran, so the proof measured nothing about what it names. Migration 0013's
`auth_claims_are_current` is an EXISTS over five equalities including
`credential_version`, `authz_version` and an exact scope array, and a
bootstrap-minted token carries none of the three (D298, D675). Repair the
identity, not the thing the proof was about.

**A rotation proof fails its own control** — *"the value declared as
pre-rotation is the active one"*. Nothing was rotated: the provider did not take
the edit, or the materialization did not run.

**`doctor.sh` reports a `PROBLEM` you do not believe.** Read `--verbose` and
check the *route* the probe took before the subject it names. Three of this
session's defects were probes that could not have succeeded — one starved by
another probe's stdin, one against an address the host never publishes, one
against a tunnel's near end (D673, D680, D682). Each reported a healthy subject
as broken.

**Read-only diagnosis needs no TTY:**

```bash
ssh -i ~/.ssh/apg_agent_ed25519 apg-agent@62.238.99.122 sudo apg-diag <verb>
```

Eight allowlisted verbs: `containers labels logs routes listeners edge-log
catalog generation`. The log allowlist still covers neither `auth`, `storage`
nor `mcp` (D380, open since Session 7).
