# Session 10 operator guide — encrypted backups, WAL archiving, and a rehearsed restore

Read this once before the host trip, then work through §4 in order and **stop at
the first thing that surprises you**.

Session 9's guide is the parent of this one and **its corrections are carried
forward by diff rather than retyped** — D505 and D507 were both flags lost to
retyping Session 8's. §4's mechanics are Session 9's, unchanged: the per-release
bundle name, `git rev-parse FETCH_HEAD` *before* the checkout, the venv sync, and
`op@` as the external gate's destination.

What is different is what Session 10 needs from you, and the short answer is:
**two things every previous session could skip — an R2 bucket and token you
create at Cloudflare before any deploy, and a first full backup you take by hand
after it.** Between those two, a deploy will fail on purpose.

---

## 0. What Session 10 adds, and what it needs from you

Session 10 gives every project **continuous WAL archiving into an encrypted R2
repository of its own**, two scheduled backups, and a **restore drill that
verifies what it restored**.

**There is no new container, and no new Compose profile.** The archiver lives
inside the existing `postgres` service — `archive_command` is run by the
postmaster, so it has to (ADR 0144) — which means the database image is now
**built rather than pulled**. The first deploy after this release rebuilds it.
Sixteen containers before, sixteen after.

**There IS a provider step, and it is the one that will stop you.** Each project
needs an R2 bucket and an API token scoped to it, created **at Cloudflare, by
hand, before the deploy** — nothing in this repository creates a bucket or issues
a token (ADR 0110), and Cloudflare shows a secret access key exactly once.

**The database container can now reach the internet.** It is attached to a
`backup` egress network of its own, because `internal` has no route off the host.
It holds the repository credential and the cipher pass, so an attacker inside it
owns the backup history as well as the live data. That is ADR 0147's stated
residual and there is no mitigation in this session.

**What it needs from you is seven things**, and 3, 5 and 6 are the new ones:

| | What | Why it needs a human |
|---|---|---|
| 1 | Transport the release to the host | `git bundle` + `scp`; no GitHub credential goes on the VPS |
| 2 | **Sync the host venv** | D384, D297 — four times now, and it costs a gate run each time |
| 3 | **Create an R2 bucket and token per project, at Cloudflare** | §1. Irreversible in the ordinary sense: a lost secret key is a new token, not a retry |
| 4 | Deploy both projects | Step 6c creates the stanza and runs `check`, and **a check failure fails the deploy** |
| 5 | **Take the first full backup by hand, at a TTY** | §4 step 5. Until it runs the document says `awaiting_first_backup` and the drill has nothing to restore |
| 6 | **Confirm the connection budget still fits** | D546. The backup identity is a fifth claimant, and the real alpha/beta manifests are gitignored — nobody has checked them |
| 7 | Run the gates and merge the evidence | §4 steps 7–9 |

**Item 6 is the one that can refuse before anything else happens**, and that is
the good case: `deploy.sh --render-only` needs no root and no Docker, raises
loudly if a project's `database.pool_size` no longer fits its remainder, and is
the first thing §4 runs.

---

## 1. What is irreversible, and the ordering that matters

**Session 10 releases no migration**, and that is measured rather than assumed:
Run 5 revoked one privilege at a time and found that every privilege an online
backup wants is refused to a NOSUPERUSER object owner, so all five grants are
bootstrap-plane. Both clusters stay at **21**. The ordering that matters this
time is at Cloudflare, not in the ledger.

**Three things here cannot be undone by re-running a command.**

### 1. Issuing the R2 token

Cloudflare shows the secret access key **exactly once**. It is pasted into the
provider by hand at `/backup`; no command here sets a value at the provider
(D249). A lost value is replaced by issuing a *new* token, which is a rotation
and not a retry.

Do this **per project**, before that project's deploy:

- **bucket**: `apg-<project-key>-backup` unless the manifest overrides it.
  `deploy.sh --render-only` prints the derived name.
- **token**: scoped to that bucket, object read and write.
- **provider**: `APG_BACKUP_R2_ACCESS_KEY_ID` and
  `APG_BACKUP_R2_SECRET_ACCESS_KEY` at `/backup`.

The cipher pass is generated for you and you never see it.

### 2. Destroying the cipher pass

`pgbackrest_repo_cipher_pass` is in `bootstrap-state.schema.json`'s
`managed_resources`, so `--destroy` may remove it. That is correct for a project
being torn down and **catastrophic** for one that is not: losing it orphans every
backup ever taken, and every check in this repository still passes (D538). It is
not carved out. It is written down.

### 3. Creating a stanza under the wrong prefix

A stanza written under a mistyped prefix leaves objects nothing here will ever
reference and nothing here will ever delete. The repository target is derived and
**printed before the call**, so read it.

### The ordering, and why it is not yours to arrange

`archive_mode` is not reloadable, so turning it on costs a cluster restart — which
the deploy performs anyway, because it recreates the container. What must not
happen is a cluster archiving before its stanza exists, quietly filling `pg_wal`.
The deploy's ordering follows the measurement: the container starts, then step 6c
creates the stanza and runs `check`.

**A check failure fails the deploy, deliberately.** It is the only thing in this
system that tests archiving end to end, and a release converging over a broken
archiver is the failure it exists to prevent. If step 6c fails, read the error
before redeploying: pgBackRest's messages carry an error number and a HINT and
are relayed verbatim.

---

## 2. What must NOT be attempted this session

- **Do not apply a migration by hand.** There isn't one. If something asks you
  to, it is wrong.
- **Do not run the restore drill before the first full backup.** It will refuse,
  but the refusal costs a container start; the gate refuses earlier and cheaper.
- **Do not enable the backup timers before the first full backup exists.** They
  are installed disabled on purpose: a unit that fails on every boot until an
  operator is ready trains an operator to ignore it.
- **Do not run `bin/backup.sh expire` to "clean up".** It is the only verb that
  destroys anything, and what it destroys may be the only copy of a database.
- **Do not run `bin/lock-versions.sh --update`.** It is wholesale (D540): Run 4
  locked one apt pin and it re-resolved three unrelated rolling tags, including
  `POSTGRES_IMAGE`. Adopting drift is its own run.
- **Do not point a second project at the first one's bucket.** The stanza, the
  prefix, the bucket and the network are all in `ISOLATED_FIELDS`; a collision is
  refused before any cluster exists, and working around that refusal would put
  two projects' backups in one place.

---

## 3. Two things the gate does that you should know about in advance

**It refuses to start unless the repository is ready.** The stanza must exist, at
least one full backup must exist, and the archiver must not be failing. All three
come from one `pgbackrest info` per project plus one read of `pg_stat_archiver` —
the same function the deploy publishes from, so the gate and the deployed
document cannot disagree about what a repository's report means.

Without that check, four requirements would fail on one missing thing and you
would read four tracebacks to learn it.

**Host mode runs a real restore.** It writes rows into `app.notes` on **beta**
under a drill-only owner id, takes a timestamp, writes one more row, and restores
to that timestamp in a disposable instance. Then it reads beta's volume, instance
identity, timeline and postmaster start time and asserts none of them moved.

Two consequences worth knowing before you start it:

- **It materialises a second copy of the cluster on disk** for the duration.
  Check free space first. The headroom this needs has never been measured on this
  host, and nothing checks it for you.
- **`REC-WAL-001` deliberately breaks beta's archiver** — `ALTER SYSTEM SET
  archive_command = '/bin/false'`, a reload, a WAL switch — and repairs it in a
  `finally`, then asserts the repair took. Whether `postgresql.auto.conf`
  overrides a command-line `-c` here **has not been measured**, so if that
  assertion fails on a cluster that is fine, the reload is the first thing to
  suspect. Either way, check beta's archiver before you leave:
  `sudo bin/backup.sh --outputs ... check`.

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

Four sessions have paid for skipping this (D384, D297). Session 10 adds no new
*Python* dependency, so this should be a no-op — confirm it, do not assume it.
It does add an apt package inside the database image, which is a build argument
and not a host dependency; nothing here installs pgBackRest on the host, and
nothing should.

### Step 4 — The R2 bucket and token, per project, at Cloudflare

**This is the step that has no command here.** Nothing in this repository creates
a bucket or issues a token (ADR 0110), and `bin/storage-admin.py` says so
structurally rather than in a comment.

Per project, in this order:

1. Read the derived bucket name out of the render step 2 produced:

   ```bash
   jq -r '.project.key + "  " + .backup.bucket + "  " + .backup.stanza' \
       .generated/<key>/outputs.json
   ```

2. At Cloudflare, create that bucket, then create an **API token scoped to it**
   with object read and write. Copy the secret access key **now** — it is shown
   once.

3. Put both halves into the provider at `/backup`:
   `APG_BACKUP_R2_ACCESS_KEY_ID`, `APG_BACKUP_R2_SECRET_ACCESS_KEY`.

**There is no migration step this session.** Session 9's guide had one here
because 0019, 0020 and 0021 were released and applied on no cluster; Session 10
releases none — Run 5 measured that every privilege an online backup wants is
refused to a NOSUPERUSER object owner, so all five grants are bootstrap-plane and
the deploy makes them. Both clusters stay at **21**.

If a deploy in step 5 reports a missing repository secret, it is this step that
was skipped or half-done. **All three files or none**: a repository reached with a
valid token and the wrong cipher pass is not partly configured, it is unreadable.

### Step 5 — Deploy both projects

```bash
sudo ./deploy.sh --host host.yaml --project project.alpha.yaml \
     --capabilities capabilities.yaml --through-session 10
sudo ./deploy.sh --host host.yaml --project project.beta.yaml \
     --capabilities capabilities.yaml --through-session 10
```

**`--host host.yaml`, or the deploy refuses** (D507) — the third flag lost
by retyping this page from Session 8's.

**`sudo` here too** (D505): `deploy.sh` refuses `--through-session` unless
`id -u` is 0, because it writes host state. `--render-only` in step 2 does
not, which is why that step runs as `op` and this one cannot.

**Expect no new container, and expect a build.** Sixteen before, sixteen after
(§0) — but the `postgres` image is now built rather than pulled, so the first
deploy after this release is slower and the cluster is recreated.

**Step 6c is new and it can fail the deploy.** It creates the stanza and runs
`pgbackrest check`. That is deliberate: `check` is the only thing in this system
that tests archiving end to end. If it fails, the deploy fails, and the reason is
named — read it rather than redeploying.

**Deploy twice if the first leaves anything unready.** D326's two-stage
convergence: a deploy observes what it has just changed. Session 10 publishes no
new route, but it does move the document from **outputs v12 to v13** and adds the
`backup` and `backup_state` blocks — read the document after the first deploy and
confirm `backup_state.status`. `awaiting_first_backup` is the correct answer here
and step 6 is what changes it; `unconfigured` means step 4 is incomplete.

### Step 5b — The first full backup, by hand, at a TTY

```bash
sudo bin/backup.sh --outputs /etc/agentic-postgres/projects/<key>/outputs.json \
     backup --type full
```

Once per project. This is not automatic on purpose: it is the first operation
that writes a meaningful amount to a repository nobody has paid for yet. Until it
runs, the document says `awaiting_first_backup`, the drill has nothing to restore,
and the Session 10 gate refuses to start.

Then confirm, and read the numbers rather than the exit code:

```bash
sudo bin/backup.sh --outputs .../outputs.json info
```

**A non-zero `failed` count on a healthy archiver is expected.** The counter is
cumulative and never resets, and every project accrues failures between its
container starting with `archive_mode=on` and step 6c creating its stanza — 26 on
a healthy, fully caught-up cluster in Run 7's rig. The status compares timestamps,
never the counter.

### Step 6 — The gates, offline and host

```bash
bin/session-01-check.sh                       # must still exit 0
bin/session-08-check.sh --mode offline
bin/session-10-check.sh --mode offline
```

Then, at a terminal with root (host mode reads root-only state):

```bash
sudo bin/session-10-check.sh --mode host --host host.yaml \
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

The gate's **step 4** is Session 10's own precondition: per project it reads
`pgbackrest info` and `pg_stat_archiver` and refuses unless the stanza exists, a
full backup exists, and the archiver is not failing. If it says *"holds no full
backup"*, go back to §4 step 5b. If it says *"stanza does not exist"*, that
project has not been deployed through Session 10. Either way that is the whole
diagnosis, and it is there so you do not read four tracebacks to reach it.

### Step 7 — The external half, from off-host

```bash
bin/session-10-check.sh --mode external --public-ipv4 62.238.99.122 \
     --project-a-outputs ./alpha-outputs.json \
     --ssh-destination op@62.238.99.122
```

**`op@`, not `apg-agent@`** (D466). The access broker grants one enumerated
account, and the read-only diagnosis account — the intuitive choice — is refused.

This mode runs off-host, needs no TTY and no root. It needs fresh deployed
documents, which is one `sudo install -o op …` from you, and an ephemeral
`ssh-agent`.

**Session 10 adds no external claim of its own**, and none was invented to make
the shape symmetric: there is nothing about a backup repository a stranger on the
public internet can measure, and an external arm would be a proof reaching an end
state by a route the product does not take (ADR 0065). The mode still runs,
because a Session 10 evidence document must answer for the external claims
inherited from Sessions 4–9 — `public_agent_boundary` among them — and the writer
refuses a document that is silent about a claim.

### Step 8 — Merge the two halves

```bash
python bin/write-session-evidence.py --session 10 \
  --host-input evidence/session-10-host.json \
  --external-input evidence/session-10-external.json \
  --output evidence/session-10.json
```

**Both halves must describe the same release or the merge refuses** — it did once,
and was right to.

---

## 5. What the evidence will say, and what it will not

**Five new claims**, all measured on the host:

| Claim | What it asserts |
|---|---|
| `point_in_time_recovery` | A restore to a chosen instant promotes and answers — and the exit code alone is not the proof, because pgBackRest exits 0 for a target the archive cannot reach |
| `restore_isolation` | The drill cannot have touched the live volume. **Two proofs** (D523): a rig driving the command with a stubbed `docker`, with a control arm proving a deliberately wrong derivation is refused, and the live cluster read before and after |
| `restore_verification` | The restored instance was **asked** — schema set, an owner-scoped read that a second identity cannot see, and a write RPC |
| `recovery_evidence` | The numbers were measured, not written: requested and achieved recovery points differ, and the RTO is wall time the command took |
| `wal_archiving_signal` | A broken archiver produces a non-zero signal, and a repaired one clears it |

**The two red claims stay red**, and they are Session 5's: `api_authorization`
and `bootstrap_identity`, blocked on the rotation window. The document will say
`status: failed` for that reason and for no other. **Nothing in Session 10 is
unproved by that sentence** — and this is the **sixth** session to close on it,
which is worth saying out loud rather than repeating quietly.

**What the evidence will NOT say**, and none of it is a defect:

- **Anything about a lost Cloudflare account.** Everything is in one account —
  the application bucket, the backup bucket, both tokens and the DNS. The backups
  are inside the blast radius of the thing most likely to take the site down.
  `docs/backup-operations.md` §2 states it; no claim measures it.
- **Anything about a large cluster.** The RTO in the evidence is a measurement of
  *this* deployment on *this* data. It is not a bound and it does not generalise.
- **Anything about a revoked R2 token.** The offline stand-in for that arm was an
  unwritable local repository, and an `EACCES` is not a `403` (D554).
- **Anything about disk headroom.** The drill needs a second copy of the cluster
  and nothing measures whether there is room. If it fails for space, it fails
  during the drill.

---

## 6. Operating the kill switch, and one thing it does not do

*Carried forward from Session 9 unchanged. Session 10 adds nothing to the agent
plane and takes nothing away, and D503 is still open.*

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

A guard is a migration and a product change, and Session 9 proved revocation
rather than building it, so the gap is recorded rather than quietly closed.
Session 10 did not take it either.

---

## 7. If something goes wrong

**The gate's step 4 says a project holds no full backup.** Go to §4 step 5b. It
is an operator command on purpose, and the gate refuses early so that four
requirements do not fail on one missing thing.

**The gate's step 4 says the stanza does not exist.** That project has not been
deployed through Session 10, or its step 6c did not run. Deploy it.

**Step 6c failed the deploy with a `check` failure.** WAL is not reaching the
repository. Read pgBackRest's own message — it is relayed verbatim and carries an
error number and a HINT:

- `[037]: ... requires option: repo1-cipher-pass` (or the S3 equivalent) — a
  credential file is missing. §4 step 4 is incomplete: **all three or none**.
- `[041]: unable to open file ... Permission denied` — a credential file is not
  owned by uid 999.
- `[027]: no database found`, pointing at `pg1-path` — this is what a
  **connection-limit refusal** looks like, and `pg1-path` is the one setting in
  the message that is correct. `backup_user` holds `CONNECTION LIMIT 2`.

**`backup_state.status` is `unconfigured`.** A repository secret is missing, not
misconfigured. It sends you to the provider, not to a config file.

**`backup_state.status` is `failing` and the counters look normal.** Read the
*timestamps*. The predicate is `last_failed_time > last_archived_time`; the
counters are cumulative, never reset, and a non-zero failed count on a healthy
archiver is expected.

**The drill left a volume or a container behind.** It says so loudly and exits
non-zero. Its teardown removes only what it recorded and refuses to remove
anything matching the live volume, so a leftover is safe to remove by hand:
`docker volume ls | grep -- -restore-`.

**The drill ran out of disk.** Nothing checks headroom, and it needs a second
copy of the cluster. This is a known gap, not a surprise.

**`REC-WAL-001` failed on a cluster that looks fine.** It breaks the archiver with
`ALTER SYSTEM` plus a reload, and whether that overrides the command-line
`archive_command` here **has not been measured**. Suspect the reload first — and
either way confirm beta recovered before you leave:
`sudo bin/backup.sh --outputs .../outputs.json check`.

**`apg-diag` cannot show you the database's logs.** Its allowlist is
`containers labels logs routes listeners edge-log catalog generation` over
`postgres pgbouncer postgrest docs edge-probe dbmate` — and its *log* allowlist
covers neither `auth`, `storage` nor `mcp` (D380). This is the fourth consecutive
session in which that sends an operator to a terminal. Widening it is an
ADR-shaped decision nobody has taken.
