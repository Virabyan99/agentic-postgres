# Session 6 operator guide

Written at the end of Run 10, before any of it has been deployed. Everything
below is what Run 10 built and rehearsed offline; **nothing in this session has
met the host yet.** Run 11 is the gate, the evidence and the session close, and
it cannot start until section 2 has been done.

`docs/session-05-operator-guide.md` still applies for everything it covers. This
document is only the difference.

---

## 0. What changed for an operator

**The application API is published.** `https://<domain>/api/app` routes to the
auth service. It is the first service Session 6 starts, and it authenticates as
`auth_service` — a role the bootstrap plane activates — so it joins PostgREST in
the set the deploy holds back until step 6 (`POST_BOOTSTRAP_SERVICES`).

**`routes.app.status` needs two things to be `ready`**: an active project
administrator, and the route answering **401** to an unauthenticated
`/auth/me`. A project with no administrator gets `unavailable`, the bootstrap
command printed, and a deploy that exits **0**. That is not a failure; it is
D230's two-stage convergence expressed as a status field rather than as a
deployment state.

**There is a second documentation surface.** `https://<domain>/docs/app` serves
the application API's reference from the same container, the same CSP and the
**same password** as `/docs/rest`.

**The documentation credential no longer needs an edge restart when it
rotates** (ADR 0086). The hash is inline in the middleware document now.

**The documentation page's URL now works without a trailing slash.** It did not
before, and the failure was silent: 200, correct HTML, blank page.

**`bin/rotate-signing-key.sh` exists.** Do not use it yet — see section 4.

---

## 1. What you are deploying

`--through-session 6`. This is a **schema version bump** (outputs v9 → v10) and
every project must be redeployed for it.

Two new commands, neither of which needs the host:

```bash
bin/app-contract.sh --check          # the application API's reviewed document
bin/rotate-signing-key.sh --help     # the cutover, read before you use it
```

---

## 2. The deploy, and the one step that is not optional

**Bring the project down first.** Not as a precaution — as the fix for a
measured defect.

```bash
# 1. Transport, as always. git bundle + scp, never a GitHub credential on the VPS.
wsl bash -lc "cd ~/projects/agentic-postgres && git bundle create /tmp/apg-session6.bundle main"
scp /tmp/apg-session6.bundle op@62.238.99.122:/tmp/

# on the host
git fetch /tmp/apg-session6.bundle main && git checkout -B main FETCH_HEAD
git rev-parse --short HEAD      # confirm this is the sha you just bundled

# 2. DOWN. Volumes are preserved.
sudo bin/project-runtime.sh --host host.yaml --project-key alpha-dev \
  --through-session 5 down
```

**3. Create the new provider secrets. This step was missing from the first
version of this guide and it stops the deploy** (D284). Session 6 introduces two
*required* secrets — `auth_service_password` and `auth_jwt_signing_key` — and no
command here sets a value at the provider (D249). Without this you get:

```
materialize-secrets: could not read auth_service_password:
  GET /api/v3/secrets/raw/APG_AUTH_SERVICE_PASSWORD failed with HTTP 404
```

`--apply` needs the control-plane credential, and **it will not be on the host**:
`docs/provider-bootstrap.md` shreds it after every bootstrap on purpose, so every
new session re-issues one. In Infisical, on the existing control-plane identity,
create a new Universal Auth client secret — shown exactly once.

```bash
CRED=/root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo install -d -m 0700 -o root -g root "$(dirname "$CRED")"
sudo install -m 0600 -o root -g root /dev/null "$CRED"
sudo nano "$CRED"        # TWO lines: client ID, then client secret. Not JSON.

sudo bin/bootstrap-providers.sh --host host.yaml --project project.alpha.yaml --plan
# expect exactly: create secret value auth_service_password
#                 create secret value auth_jwt_signing_key
sudo bin/bootstrap-providers.sh --host host.yaml --project project.alpha.yaml \
  --apply --operator-credential-file "$CRED"
```

**Keep `$CRED` until every project has been applied** — beta-dev needs the same
step, and one client secret does both. Then:

```bash
sudo shred -u "$CRED"
sudo find /root/.config/agentic-postgres -name '*.save' -print   # nano's copy
```

`auth_jwt_prepared_key` is **not** created and must not be: it is
`required: false` and exists only while a rotation is in flight.

```bash
# 4. Materialize, then deploy through 6.
sudo bin/materialize-secrets.sh --project project.alpha.yaml \
  --requirements secrets.required.yaml --session 6
sudo ./deploy.sh --host host.yaml --project project.alpha.yaml \
  --capabilities capabilities.yaml --through-session 6
```

**Why the `down` is not optional.** This deploy rewrites the JWKS, and
`render-jwks.py` writes it by staging-and-rename. Measured against the locked
Compose, with the container's ID as the evidence:

| what changed | recreated? | what the container then holds |
|---|---|---|
| nothing (the control) | no | the old value |
| the mount's **source path** (a new generation) | **yes** | the new value |
| the same path, rewritten **in place** | no | the new value — same inode |
| the same path, **replaced** | no | **the old value** — stranded inode |

The JWKS is at a stable path and is replaced, so it is the last row: a running
PostgREST keeps reading a file that no longer exists. And a `docker restart`
does not repair it — measured, the container is left unable to start at all,
because its mount source is gone. `down` then `up` is what works.

This corrects D253's written reason. The instruction was right; the mechanism it
gave was not (D278).

---

## 3. After the deploy

```bash
# routes.app will be `unavailable` until this exists.
sudo bin/auth-admin.sh --outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json \
  bootstrap --username <name> --display-name "<name>"

# Then redeploy so the route is observed and published.
sudo ./deploy.sh --host host.yaml --project project.alpha.yaml \
  --capabilities capabilities.yaml --through-session 6
```

The password is read from the terminal, twice, and **cannot be recovered**. If
the output is lost, run `auth-admin.sh … list` and look; do **not** bootstrap
again — the second attempt is refused, on purpose.

### Verify by hand

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://<domain>/api/app/auth/me        # 401
curl -sS -o /dev/null -w '%{http_code}\n' https://<domain>/api/app/auth/jwks.json # 200
curl -sS -o /dev/null -w '%{http_code}\n' https://<domain>/api/application        # 404
curl -sS -o /dev/null -w '%{http_code}\n' https://<domain>/docs/app               # 401
```

And the one that has never been true before — the documentation page fetching
its own script:

```bash
curl -sS -u docs:<password> -o /dev/null -w '%{http_code}\n' \
  https://<domain>/docs/rest/standalone.js     # 200
curl -sS -u docs:<password> -o /dev/null -w '%{http_code}\n' \
  https://<domain>/docs/app/openapi.json       # 200
```

A 404 on either means the strip is wrong and the page will render blank.

---

## 4. The signing cutover — built, and not to be run yet

`bin/rotate-signing-key.sh` implements prepare → acknowledge → promote → retire
(ADR 0088). **Do not start a rotation during Session 6.**

The key set holds at most two keys, and both slots are currently spoken for: the
bootstrap issuer's key and the auth service's. That is not a limitation to work
around — the transition between those two issuers **is** the first rotation this
machinery is for, and it is the one §4 of the plan says happens last, after
auth-service issuance and PostgREST verification are both proved.

When it is time, the order is in `docs/api-operations.md` under *The signing
key*. The step that is easy to skip and must not be: after any phase that
changes the published set, **recreate** every verifier. A running PostgREST
never re-reads its key set — measured.

---

## 5. The Session 6 gate

**Run 11 is done offline.** `bin/session-06-check.sh` exists, the seven claims
are in `evidence_claims.CLAIMS`, and the eleven Session 6 registry entries point
at real proofs. What does not exist is any evidence, because **every Session 6
claim is `live_host` and none of these proofs has run in any environment yet.**
That is what this trip is for.

Before any host gate run, re-render the fixtures or D212 returns. The gate now
**fails rather than skips** if you forget:

```bash
./deploy.sh --project project.example.yaml \
  --capabilities capabilities.example.yaml --render-only
./deploy.sh --project project.second.example.yaml \
  --capabilities capabilities.example.yaml --render-only
```

### The command

```bash
sudo bin/session-06-check.sh --mode host --host host.yaml \
  --project-a-outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json \
  --project-b-outputs /etc/agentic-postgres/projects/beta-dev/outputs.json \
  --admin-password-file /root/alpha-dev-administrator \
  --sentinel-file "$(sudo python3 -c "
import json
from pathlib import Path
root = Path('/var/lib/agentic-postgres/secrets/alpha-dev')
gen = json.loads((root / 'active-secret-generation.json').read_text())['generation_id']
print(root / 'generations' / gen / 'secret-check' / 'session2_sentinel')
")"
```

**`--admin-password-file` is new and four claims depend on it.** The
administrator's password cannot be recovered from the host — only an Argon2id
hash is stored, which is exactly what `SEC-CRED-001` asserts — so the proofs
that need an administrator session have to be given one. Write the password you
typed at step 3 into a root-owned file, run the gate, then remove it:

```bash
sudo install -m 0600 /dev/null /root/alpha-dev-administrator
sudo tee /root/alpha-dev-administrator >/dev/null    # type it, then Ctrl-D
# ... run the gate ...
sudo shred -u /root/alpha-dev-administrator
```

Without it, `token_contract`, `admin_authorization`, `token_non_resurrection`
and `project_isolation` report `not_run`. That is the evidence model working —
but it means the trip proved less than it could have, and you would have to come
back.

Then the other half, from a machine that is **not** the host, and the merge:

```bash
bin/session-06-check.sh --mode external --public-ipv4 62.238.99.122 \
  --project-a-outputs ./alpha-outputs.json --ssh-destination op@62.238.99.122

python bin/write-session-evidence.py --session 6 \
  --host-input evidence/session-06-host.json \
  --external-input evidence/session-06-external.json \
  --output evidence/session-06.json
```

### What to expect the first time

These proofs have never run. Treat a failure as a question rather than a verdict
— the most likely causes, in order, are a fixture that was not re-rendered, a
missing `--admin-password-file`, and `routes.app` still `unavailable` because
the administrator was created but the project was not redeployed afterwards.

**`SEC-BOOT-001` will pass, and it would not have before this run.** Its expiry
clause compared `deployed_through_session` against a constant `6`, so deploying
through session 6 turned a green proof red — for a correct deployment, because
Session 6 deliberately does not retire the bootstrap issuer. It is now keyed to
the key set instead (ADR 0090, D280). If it *does* fail, read what it says: it
now derives the bootstrap key's `kid` from the private key on disk and checks
that the published set contains it, so a failure means the JWKS and the keys
disagree — which is D276's defect, not a stale assertion.

---

## Traps

**A passfile with group or world access is silently ignored.** libpq refuses it
and reports `fe_sendauth: no password supplied` — the same message a *missing*
passfile gives. Measured while rehearsing the auth container. The `0400` in
`secrets.required.yaml` is load-bearing, not tidiness.

**`docker restart` after a key-set change leaves the container dead**, because
the mount source it was bound to no longer exists. Recreate, never restart.

**A scope is not `admin:users`.** The runbook's vocabulary was replaced by ADR
0079; the shipped names are `admin_users:read`, `admin_agents:write` and so on.
`bin/auth-admin.sh` derives them from the registry and cannot get this wrong —
anything typed by hand can.

**`app_private.users` refuses an unsorted scope array** (D248). The database is
the check, and it fires as a constraint violation rather than a reordering.

**Traefik's own 404 and a routed 404 are identical from outside.** Read the
access log before concluding anything: Traefik's carries no `RouterName` and a
19-byte body.
