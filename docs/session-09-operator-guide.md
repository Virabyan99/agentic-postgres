# Session 9 operator guide — agent writes, the audit record, and revocation

Read this once before the host trip, then work through §4 in order and **stop at
the first thing that surprises you**.

Session 8's guide is the parent of this one and its corrections are carried
forward (D462, D466, and `migrate.sh --project`). What is different is what
Session 9 needs from you, and the short answer is: **one thing Session 8 did not
need — two migrations, applied before the deploy rather than after it.**

---

## 0. What Session 9 adds, and what it needs from you

Session 9 gives the agent plane a **write** half, a **durable audit record**, and
an **admin endpoint to read it** — and it proves revocation rather than building
it.

**There is no new container.** Writes and the audit calls live in the existing
`mcp` runtime; the audit endpoint lives in the existing auth-api. `CURRENT_SESSION`
moving to 9 arms a `session9` Compose profile that **no service declares**
(D488). This is stated here so that the container which does not appear is not
mistaken for one that failed to start. Nothing new starts. Sixteen containers
before, sixteen after.

**There is no provider step and no new secret.** No Cloudflare, no bucket, no API
token, no Infisical folder, nothing for you to create or keep safe. The MCP
runtime still holds **no database credential and no signing material** —
`settings.load_mcp` refuses to start if handed one (D407) — and the audit record
is written by definer functions **as the caller**, so `mcp_audit_service` stays
unactivated and that is now a decision rather than a deferral (ADR 0135).

**What it needs from you is five things**, and the third is the one that is new:

| | What | Why it needs a human |
|---|---|---|
| 1 | Transport the release to the host | `git bundle` + `scp`; no GitHub credential goes on the VPS |
| 2 | **Sync the host venv** | D384, D297 — three times now, and it costs a gate run each time |
| 3 | **Apply migrations 0019 and 0020, on BOTH clusters, BEFORE the deploy** | §4 step 4. The ordering is not cosmetic — see §1 |
| 4 | Deploy both projects | Twice if the first leaves a route or a document field unready (D326) |
| 5 | Run the gates and merge the evidence | §4 steps 6–8 |

---

## 1. What is irreversible, and the ordering that matters

**Two migrations are released here and applied on no cluster.** Both clusters run
**18**. This is the single most important fact for this trip, and it is why §4
step 4 comes before step 5.

- **0019 — the agent write and audit plane.** `app_private.agent_audit` with its
  two enums, `api.agent_audit_begin` / `api.agent_audit_complete`, the two write
  RPCs replaced by `CREATE OR REPLACE` to record their own committed changes, and
  the grants `agent_writer` never had.
- **0020 — the audit record's one reader.** `app_private.auth_list_agent_audit`,
  granted to `auth_service` alone, which is what `GET /admin/audit` sends.

Both are forward-only, applied as `migration_user` and **never as a superuser**
(D285): a superuser bypasses the ownership check that let migration 0012 pass
four sessions of green proofs while being unappliable.

### The ordering, and why it is not arbitrary

**The migration must land before the deploy**, because the deploy runs the
bootstrap plane and the bootstrap plane activates `agent_writer`.

0019 grants the *privileges* — `USAGE ON SCHEMA app_private`, `EXECUTE` on the
pre-request hook, `EXECUTE` on both comparison helpers. `bin/postgres-bootstrap.py`
grants the *membership*, which is what decides whether any token may name the
role. They are separate on purpose (D102, D266).

Get the order wrong and the failure is **not** a clean error. A membership
granted before the privileges exist produces a write request refused by
`permission denied for function postgrest_pre_request` — a `42501` — instead of by
the boundary's own `AP401`. A client cannot tell "your token is stale" from "this
deployment is half-migrated", and that is D417's shape, one session later (D475).

### Also irreversible, and already done in the tree you are transporting

- `CURRENT_SESSION` moved to **9** (Run 8). It arms the `session9` profile that
  nothing declares. Expect no new container.
- `agent_writer` is activated in `AUTHENTICATOR_REQUEST_ROLES` (Run 2, ADR 0137).
  Granting the authenticator membership in a role widens what a token may name —
  from *an agent can read its owner's rows* to *an agent can change them*.
- The capability contract carries **six tools behind seven capabilities**, two of
  them writes. The deployed lock is compiled from the committed contract during
  the deploy; you are not asked to hand one over.

---

## 2. What must NOT be attempted this session

**The rotation window.** Two Session 5 claims — `api_authorization` and
`bootstrap_identity` — stay red, blocked only on a window nobody has held. This
is the **fourth** session to close on that sentence. Session 9 does not close
them and its evidence must not read as if it did.

**`OPS-LOG-001`.** Session 9's request id spans MCP → PostgREST → the audit
record. `OPS-LOG-001` spans ingress → API → agent → audit and is **Session 11's**
(D478). Do not read Session 9's evidence as closing it.

**Amending a released migration.** 0019 is released. The `request_id` gap on the
`database`-source row (D500) is a **migration 0021** when somebody takes it, not
an edit to 0019.

---

## 3. One thing the gate does that you should know about in advance

**The Session 9 host gate temporarily withdraws a grant.**

`AGT-AUDITFAIL-001` proves that a write whose audit record cannot be opened does
not happen. On a real cluster the only honest way to arrange that failure is to
make `api.agent_audit_begin` unreachable, so the test runs, inside the project
lock:

```sql
REVOKE EXECUTE ON FUNCTION api.agent_audit_begin(text, uuid, jsonb) FROM "<agent_writer>";
-- ... one write attempt, which must be refused and must leave no row ...
GRANT  EXECUTE ON FUNCTION api.agent_audit_begin(text, uuid, jsonb) TO   "<agent_writer>";
```

The restore is in a `finally` and its result is **checked** rather than assumed
(D391 — a guard whose result is unchecked is a comment). While the grant is off,
every `agent_writer` request's audit begin fails and its write does not happen,
which is precisely the behaviour under test. Reads are unaffected: a read does
**not** fail closed, and that asymmetry is the decision (ADR 0141, D483).

**If the gate is killed between the two statements**, the grant stays off and the
probe project's agent writes keep failing closed. The message the test would have
printed names the repair, and so does this guide:

```bash
# On the host, as the object owner:
SET ROLE "<object_owner>";
GRANT EXECUTE ON FUNCTION api.agent_audit_begin(text, uuid, jsonb) TO "<agent_writer>";
```

Both role names are in the project's `outputs.json` under `database.roles`.

---

## 4. The host sequence, in order

### Step 1 — Transport the release

**The bundle is named for the release, and that is not cosmetic** (D504). The
generic `/tmp/apg.bundle` collides: Session 8's trip left that exact path on the
host owned by `apg-agent`, `/tmp` is sticky, and `op` cannot overwrite a file it
does not own. The `scp` refuses — loudly — and the *next* command in this step
then succeeds against the stale file and checks out a **previous** release.

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

`git fetch` then `git checkout -B`, **not** a fast-forward merge.

**Read the `release <sha>` line and confirm it is the sha you fetched.** A
skipped fetch has already produced one deploy of the previous commit — and D504
is a second road to the same place, which is why `git rev-parse FETCH_HEAD` is
now a step of its own rather than a sentence after the fact.

Old bundles are never cleaned up; nine of them are on the host. Leave them —
`op` cannot remove the ones `apg-agent` wrote, and a per-release name means it
never needs to.

### Step 2 — Re-render all four projects, on the host

```bash
for f in project.alpha.yaml project.beta.yaml project.example.yaml project.second.example.yaml; do
  ./deploy.sh --project "$f" --capabilities capabilities.yaml --render-only
done
```

**All four, not two, and on the host rather than the workstation** (D462, D383).
`.generated/` is gitignored and is never transported, so a stale render on the
host is a fixture from a previous release.

### Step 3 — Sync the host venv

```bash
cd ~op/agentic-postgres && . .venv/bin/activate && bin/lock-dev-deps.sh --check
```

Three sessions have paid for skipping this (D384, D297). Session 9 adds no new
runtime dependency, so this should be a no-op — confirm it, do not assume it.

### Step 4 — Apply migrations 0019 and 0020, on BOTH clusters, BEFORE the deploy

```bash
bin/migrate.sh --project project.alpha.yaml status   # expect 0019 and 0020 pending
bin/migrate.sh --project project.alpha.yaml up
bin/migrate.sh --project project.beta.yaml  status
bin/migrate.sh --project project.beta.yaml  up
```

`--project`, naming the manifest, is the corrected invocation from Session 8's
trip. Run `status` first and read it: two pending is what you expect, and
anything else is worth stopping for.

**This is step 4 and not step 6.** §1 explains why.

### Step 5 — Deploy both projects

```bash
./deploy.sh --project project.alpha.yaml --capabilities capabilities.yaml --through-session 9
./deploy.sh --project project.beta.yaml  --capabilities capabilities.yaml --through-session 9
```

**Expect no new container.** Sixteen before, sixteen after (§0).

**Deploy twice if the first leaves anything unready.** D326's two-stage
convergence: a deploy observes what it has just changed, so a newly published
route or document field can be observed before it has settled. Session 9
publishes no new route, and it does move `mcp.tool_count` from 4 to 6 — read the
document after the first deploy and redeploy if `routes.mcp` is not `ready` or
the `mcp` block is not current. The gate checks both and says which.

### Step 6 — The gates, offline and host

```bash
bin/session-01-check.sh                       # must still exit 0
bin/session-08-check.sh --mode offline
bin/session-09-check.sh --mode offline
```

Then, at a terminal with root (host mode reads root-only state):

```bash
sudo bin/session-09-check.sh --mode host --host host.yaml \
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

**Derive the sentinel path, never type it.** The generation directory changes on
every start, so a hard-coded one names a superseded generation and the scan then
fails to find what it planted.

The gate's **step 4** is Session 9's own precondition: it reads each cluster's
migration ledger and refuses if any released migration is missing. If step 4
fails, go back to §4 step 4 — that is the whole diagnosis, and it is there
precisely so you do not read thirteen tracebacks to reach it.

### Step 7 — The external half, from off-host

```bash
bin/session-09-check.sh --mode external --public-ipv4 62.238.99.122 \
     --project-a-outputs ./alpha-outputs.json \
     --ssh-destination op@62.238.99.122
```

**`op@`, not `apg-agent@`** (D466). The access broker grants one enumerated
account, and the read-only diagnosis account — the intuitive choice — is refused.

This mode runs off-host, needs no TTY and no root. It needs fresh deployed
documents, which is one `sudo install -o op …` from you, and an ephemeral
`ssh-agent`.

**Session 9 adds no external claim of its own.** The mode still runs, because a
Session 9 evidence document must answer for five external claims inherited from
Sessions 4–8 — `public_agent_boundary` among them — and the writer refuses a
document that is silent about a claim.

### Step 8 — Merge the two halves

```bash
python bin/write-session-evidence.py --session 9 \
  --host-input evidence/session-09-host.json \
  --external-input evidence/session-09-external.json \
  --output evidence/session-09.json
```

**Both halves must describe the same release or the merge refuses** — it did once,
and was right to.

---

## 5. What the evidence will say, and what it will not

**Five new claims**, all measured on the host:

| Claim | What it asserts |
|---|---|
| `agent_writes` | A read-only agent can neither discover nor invoke a write — and the two are separate, because hiding a name is not a boundary (ADR 0140) |
| `agent_audit_record` | One MCP write leaves two records, from two routes, and they agree |
| `agent_audit_fails_closed` | A write whose audit record cannot be opened does not happen; a read still answers |
| `agent_revocation` | One token, minted before the revocation, fails its next MCP read, its next MCP write and its next direct PostgREST request |
| `agent_parameter_boundary` | No tool parameter and no audit-function argument can name a principal |

**The two red claims stay red**, and they are Session 5's: `api_authorization`
and `bootstrap_identity`, blocked on the rotation window. The document will say
`status: failed` for that reason and for no other. **Nothing in Session 9 is
unproved by that sentence** — this guide says so before the run, as Sessions 7 and
8 both did.

**What the evidence does not say:**

- **Nothing has timed the round trip.** An MCP write is now **four** upstream
  requests — context, `agent_audit_begin`, the write, `agent_audit_complete`. A
  read is three; metadata is none. Each holds a PostgREST connection while it
  runs, and the concurrency bound is a share of that same pool, so the cost lands
  on a resource shared with human callers. No session has measured any of it.
- **The `database`-source audit row carries no `request_id`** (D500), so the two
  records for one MCP write join by agent, tool and time rather than by request.
  A deployment test asserts that NULL, so the day a migration closes the gap, the
  test that says so fails and points at its own premise.
- **`app_private.agent_audit` grows without bound.** Nothing prunes it, exactly
  as nothing prunes secret generations. Retention is decided by nobody.

---

## 6. Operating the kill switch, and one thing it does not do

Revoking an agent is one request, and it is the route the product already had:

```bash
curl -X PATCH https://<app-host>/admin/agents/<agent_id> \
     -H "Authorization: Bearer <admin token with admin_agents:write>" \
     -H 'Content-Type: application/json' \
     -d '{"status": "revoked"}'
```

It flips the status **and** bumps `authz_version` in one statement, and the
`authz_version` bump is the part that actually stops the token: the authoritative
check runs inside every database request, so the agent stops on its **next**
request rather than at the token's expiry.

**What it does not do, and this is D503.** Migration 0011's comment says an agent
credential *"is `revoked`, which is terminal for that credential"* — and nothing
enforces that. `PATCH … {"status": "active"}` on a revoked agent answers **200**
and the agent works again. The two-value enum stops a third state existing; it
does not stop the second transition.

The bound half is worth knowing precisely: **every status change moves
`authz_version`**, so no token issued before either transition survives. What
un-revoking restores is the **secret's** usefulness — which revocation never
invalidated. If you need the credential dead rather than dormant, rotate it:
`POST /admin/agents/<id>/rotate-secret`.

A guard is a migration and a product change, and Session 9 proves revocation
rather than building it, so the gap is recorded rather than quietly closed.

---

## 7. If something goes wrong

**The gate's step 4 says a migration is missing.** Go to §4 step 4. Do not skip
ahead: every write, audit and revocation proof needs both migrations, and without
the precondition they fail as a wall of `relation "app_private.agent_audit" does
not exist`.

**A write is refused with `permission denied for function postgrest_pre_request`.**
The membership landed before the privileges. Apply 0019, then redeploy. §1.

**Every `agent_writer` write is failing closed after a gate run.** The audit grant
was left withdrawn by a killed test. §3 has the one statement that repairs it.

**`routes.mcp` is `unavailable`.** Deploy again. §4 step 5.

**`apg-diag` cannot show you the agent plane's logs.** Its allowlist is
`containers labels logs routes listeners edge-log catalog generation` over
`postgres pgbouncer postgrest docs edge-probe dbmate` — no `auth`, no `storage`,
no `mcp` (D380). This has sent an operator to a terminal in three consecutive
sessions. Widening it is an ADR-shaped decision nobody has taken.
