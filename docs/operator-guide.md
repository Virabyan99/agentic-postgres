# Operating a deployment — the current release

**This page describes operating the release in this checkout: `1.6.0`,
`CURRENT_SESSION` 25.** It supersedes the per-session operator guides
(Sessions 2–11), which stay in the tree as the record of the host sequence as
it was then (ADR 0208). It is derived — by diff, never retyped — from Session
11's guide, from the §5 Run 7 *Done* paragraphs of the Session 12–25 plans,
and from the host scripts the last trip executed on 2026-09-15
(`/home/op/s25-*.sh`, `g25-*.sh`).

**Every command here is copied from its own `--help` as this release prints
it**, and every sequence names the date it was executed and the plan that
recorded it. Where something has not been done on this deployment the section
says so (§13), rather than describing it as if it had. Where a topic page
already carries a measured section — backups, recovery, the fleet, the API
plane, migrations — this page hands to it and does not repeat it.

---

## 1. The release you are operating, in one screen

> **This page is part of release `1.8.0`.** It describes that release as it
> runs on this deployment. A release that moves `VERSION` and does not move
> this line, and the table below it, is a release documented by a page about a
> different one (ADR 0209, D1388).

| | |
|---|---|
| `template_version` / `CURRENT_SESSION` | **1.8.0** / **30** — the two numbers have come apart three times (1.0.1, 1.6.1, 1.6.2), each time because an outsider's reading produced repairs rather than a plane; 26, 27 and 29 are skipped in the registry the way 19 is, so the session number goes 25 → 28 → 30. `1.3.0`–`1.5.0` were releases without tags (D1311) |
| Released migrations | **33**, fix-forward; every down block raises `AP900` (D912). 0033 adds two prune functions granted to nobody and a size reading (ADR 0213) — nothing removes an agent record unless an operator asks |
| Deployed document | outputs schema **v18**; `document_kind: deployed` |
| Project manifest | schema versions **1–6** accepted; 5 adds `migrations.set`, 6 adds `mcp.capabilities` |
| Capability manifest / lock | schema **4** / **4** (vocabulary + `tools_sha256`) |
| Verifiers | **four** — PostgREST, `auth`, `storage`, the agent plane — reading one published key set; only `auth` signs (ADR 0170) |
| Migration sets | the release's, and a project's own under `projects/<slug>/`, each in its own directory and its own ledger table (ADR 0198, 0206). A project's lock is schema **3**: it records whether `follows_release_version` was computed or declared (ADR 0210) |
| Backups | pgBackRest to R2 per project, weekly full and nightly incremental timers, a nightly mirror copy to B2 by a host unit (ADR 0188); a DR kit that names every secret and holds none (ADR 0189) |

**What the doctor reads on a well project** is the best one-screen description
of what runs: *containers, the health route, TLS expiry, the cluster and the
pooler, migrations, the backup repository, the WAL archiver, the backup
mirror, disk headroom for a restore, the capability lock against the deployed
document, and how much agent record the deployment is carrying*. The reading
of record is **10 ok / 0 problem** on both projects at 2026-09-15, taken with
the ten checks that existed then. **Since 1.7.0 there are eleven**: `agent
record` reports the two agent tables' counts and the date the record starts,
with no threshold, because nobody has measured a row count at which a
deployment is unwell (ADR 0213). It reads the tables and not migration 0033's
functions, so **a 1.7.0 checkout reads eleven against a deployment at any
release** — the count follows the checkout, not the cluster. The tenth reads
the lock the **running** agent plane loaded, not the file on disk (D1152/D1153,
repaired 2026-09-13).

**Where things live on the host**, every path read from a command's `--help`
or a trip's script:

| What | Where | Owner |
|---|---|---|
| the checkout releases are fetched to and rendered from | `/home/op/agentic-postgres` | `op` |
| the installed, immutable release a deploy runs | `/opt/agentic-postgres/releases/<commit>` (the units cite `releases/current/docs/…`) | root |
| the launchers every unit's `ExecStart` names | `/usr/local/libexec` | root |
| the **deployed** document | `/etc/agentic-postgres/projects/<key>/outputs.json` | root, `0600` |
| the project's bootstrap state and credential files | `/etc/agentic-postgres/projects/<key>/bootstrap-state.json`, `/etc/agentic-postgres/credentials/<key>/` | root |
| the **installed rendered** directory, including the capability lock | `/var/lib/agentic-postgres/rendered/<key>/` (`mcp-capability-lock.json`) | root |
| secret generations and the active pointer | `/var/lib/agentic-postgres/secrets/<key>/generations/<id>/`, `…/active-secret-generation.json` | root |
| the database access policy | `/etc/agentic-postgres/database-access-policy.json` | root, `0600` |
| an interrupted rehearsal's reversal | `/etc/agentic-postgres/rehearsal-in-progress.json` | root |
| a render as `op`, and the candidate for `upgrade plan` | `/home/op/agentic-postgres/.generated/<key>/` | `op` — or root after a root render (D1110) |
| op-owned copies of the deployed documents, for off-host readers | `/home/op/<key>-outputs.json` | `op`, `0600` |
| the DR kits | `/home/op/kit-<date>/`, and off the host in `~/dr-kits/` on ext4 | `op`, `0700` |
| a third project's manifest | `/home/op/<name>.yaml` — **never inside the checkout** (D971) | `op` |

**Six ways of naming a project, and the difference is real.** Each is what
that command's `--help` documents; copying the wrong one produces a refusal,
not a wrong action, but it is the first thing every reader trips over:

| Spelling | Meaning | Commands |
|---|---|---|
| `--project KEY` | the derived key, `<slug>-<env>` | `doctor`, `connect`, `upgrade`, `project-retire` |
| `--project FILE` | the project manifest | `deploy.sh`, `migrate`, `db`, `postgres-bootstrap`, `materialize-secrets`, `bootstrap-providers`, `dr-kit export`, `restore`, `dev`, `generate`, `studio`, `agent`, `mcp-contract`, `api-contract` |
| `--project-key KEY` | the key, validated before use as a path | `project-runtime`, `database-ports`, `edge-network` |
| `--outputs FILE` | the **deployed** document | `backup`, `rehearse`, `storage-admin`, `auth-admin`, `rotate-signing-key`, `studio`, `mcp-contract lock` |
| `--project-outputs FILE` | the deployed document, for a command that reads a route from it | `api-contract`, `api`, `dev-token`, `docs` |
| `--project-dir DIR` | a generated project directory | `restore-test` |

`bin/apg.sh` is one front door over all of them (`apg doctor --verbose` runs
`bin/doctor.sh --verbose`) and adds nothing; `APG_PROJECT` is applied only to
a verb whose `--help` says `--project FILE`, announced on stderr every time,
and **dropped by `sudo`** unless `--preserve-env=APG_PROJECT` is passed.

---

## 2. Two accounts, and the shape of a sitting

- **`op`**, over SSH with its own key, does everything that reads, renders,
  fetches or checks out. A non-interactive SSH session sources no profile, so
  every script run this way begins with `export PATH="$HOME/.local/bin:$PATH"`
  or `uv`, `shellcheck` and `jq` are not found. **`op` cannot reach the Docker
  socket** (D1375): the offline gate mode, `apg dev` and anything that runs a
  container are not `op`'s on this host, deliberately (§10).
- **A human at a terminal runs every `sudo` line.** `sudo` needs a TTY here;
  a deploy whose output is redirected or piped is **refused** with exit 2 and a
  sentence (D972), and a `sudo` put in the background with an expired timestamp
  is stopped rather than run (D1376) — `sudo -v` in the foreground first, then
  the line. **Since ADR 0218 no product child reads the terminal**, so the
  other commands on this page may be redirected freely; the refusal is kept on
  `deploy.sh` because an operator is better served by a sentence than by a
  command that works for a reason they cannot see.
- **`apg-agent`** is the read-only diagnosis account (ADR 0071):
  ```bash
  ssh -i ~/.ssh/apg_agent_ed25519 apg-agent@<host> sudo apg-diag <verb>
  ```
  Verbs: `containers labels logs routes listeners edge-log catalog generation`;
  `catalog` queries: `connection-limits, role-settings, migration-ledger,
  extensions`. Its log allowlist covers neither `auth`, `storage` nor `mcp`
  (D380, open since Session 7).

**Transport is `git bundle` + `scp` under a name derived from the commit**
(D504), never a GitHub credential on the host. The sequence is
[the upgrade guide](upgrade-guide.md) §3 step 1, and it is the same whether
the host is being upgraded or being read.

---

## 3. A host from empty, and its first project

The order below is the one the product's own commands impose — *no step makes
its own preconditions* (`deploy.sh --help`) — and every `sudo` line is a human
at a terminal. **Complete bring-ups from empty that this project has records
of**: the replacement host of 2026-09-06 (Session 18 Run 6, Hetzner, to the
restore and no further), the third project `gamma-dev` on the production host
on 2026-09-04 (`docs/fleet-operations.md` §6, the sequence as measured with
the four things that went wrong), and an outsider's appliance brought up on
2026-09-08 by someone who had not seen this repository (ADR 0207, D1370 —
`fresh_host` passed on its document). Each step names which of those measured
it.

1. **The release onto the host, and the operator user, before anything
   hardens.** `docs/session-02-operator-guide.md` §0, unchanged in kind: the
   bundle, `git clone -b main` (without `-b` a current git clones an *empty*
   tree, D1024), `git rev-parse HEAD` confirmed; then the account
   `ssh.operator_user` names, created by hand with its key and its sudoers
   line, and **proved with a new session while root still works** — step 2
   installs `PermitRootLogin no` and removes the only other way in (D659).
   Measured 2026-09-06.
2. **The host baseline**, three `--apply` passes because the two steps that
   can lock you out each need their own armed rollback timer:
   ```bash
   sudo bin/provision-host.sh --host host.yaml --check
   sudo bin/provision-host.sh --host host.yaml --apply          # 1: launchers, units, Docker; SSH and ufw skipped
   # arm apg-ssh-rollback as it prints, --apply, open a NEW session, then:
   sudo bin/provision-host.sh --host host.yaml --confirm-ssh-ok
   # arm apg-ufw-rollback as it prints, --apply, open a NEW session, then:
   sudo bin/provision-host.sh --host host.yaml --confirm-firewall-ok
   ```
   If a new session fails after either step, do nothing for ten minutes and
   let the timer undo it. `jq` is in the apt line (D1049); `--check` reports
   the units, since D970. `docs/host-baseline.md` is what it does to the
   machine.
3. **The edge**, once per host, on staging certificates first:
   ```bash
   sudo bin/edge.sh --host host.yaml up
   sudo bin/edge.sh --host host.yaml status
   ```
   DNS `A` records per project hostname, **grey cloud**; a proxied record
   breaks HTTP-01. Under staging a first deploy prints one
   `CERTIFICATE_VERIFY_FAILED` line per route per kind and exits 0 (D1047);
   that is the staging issuer. Promote once, and only when every hostname has
   a staging certificate — a failed validation burns a weekly limit that
   takes seven days to return, and **failed ACME validations cap at 5 per
   hour per hostname; never retry in a loop**:
   ```bash
   sudo bin/edge.sh --host host.yaml promote-acme --to production --confirm <host id>
   ```
   There is no `--to staging`; going back is a re-render.
4. **The providers, per project.** The manifest is `project.<name>.yaml` in the
   checkout for the two the gitignore names, and `/home/op/<name>.yaml` for
   any other (D971). Then, by hand at the consoles: two R2 buckets
   (`apg-<key>` and `apg-<key>-backup`) and two Account API tokens each scoped
   to one bucket, the DNS record, and — for a mirror — the B2 bucket and key
   pair (`docs/backup-operations.md` §3). Nothing in this repository creates a
   bucket, issues a token or writes a provider value (D249, ADR 0110).
   ```bash
   bin/bootstrap-providers.sh --host host.yaml --project project.alpha.yaml --plan
   sudo bin/bootstrap-providers.sh --host host.yaml --project project.alpha.yaml --apply \
        --operator-credential-file /root/<the control-plane credential>
   ```
   `--plan` contacts nothing (D334). `--apply` creates the Infisical project,
   the runtime identity and every generated value, shreds the credential file,
   and **does not invent an operator-supplied value**: paste the four R2
   values into `/storage` (create the folder) and `/backup` afterwards
   (`docs/fleet-operations.md` §6 step 4, `docs/provider-bootstrap.md`). If
   `--apply` fails after the provider project exists, it prints what it
   created with ids; the state file is written only at the end (D1046).
5. **Materialize**, the first reader of every value; a 404 here names the one
   that is missing:
   ```bash
   sudo bin/materialize-secrets.sh --project project.alpha.yaml \
        --requirements secrets.required.yaml --session 30
   ```
6. **Deploy, unredirected, at the terminal:**
   ```bash
   sudo ./deploy.sh --host host.yaml --project project.alpha.yaml \
        --capabilities capabilities.yaml --through-session 30
   ```
   The first pass of a new project records the two loopback ports and the
   app route `unavailable` — the documented first-deploy state, not a failure
   (D326, `docs/fleet-operations.md` §6 step 6).
7. **Ports, then deploy again:**
   ```bash
   sudo ./deploy.sh --host host.yaml --project project.alpha.yaml \
        --capabilities capabilities.yaml --render-runtime-only
   ```
   It reserves two ports and **prints the `bin/database-ports.sh verify`
   line** with this project's instance UUID; run it as printed, then step 6
   once more. Now `pooled` and `direct` read `available` and the app route is
   observed.
8. **The administrator**, once, and the password cannot be recovered or
   re-bootstrapped (`AP409` on a second attempt, on purpose):
   ```bash
   sudo bin/auth-admin.sh --outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json \
        bootstrap --username <name> --display-name <name>
   ```
   Write the password to a root-only file — the gate reads it as
   `--admin-password-file /root/alpha-dev-administrator` — because only an
   Argon2id hash is stored. **Beta's administrator password is not recorded on
   this host** (`/root` holds alpha's only), which is why every
   administrator-needing proof runs against alpha.
9. **The first full backup, by hand, then the timers.** Until it runs the
   document publishes `awaiting_first_backup` and nothing can be restored:
   ```bash
   sudo bin/backup.sh --outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json backup --type full
   sudo bin/backup.sh --outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json info
   sudo bin/backup.sh --outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json schedule enable
   sudo bin/backup.sh --outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json mirror
   ```
   `schedule enable` refuses while the units are not installed (step 2's
   job) and while the repository holds no full backup. The first scheduled
   run is read the next morning from `journalctl` and the doctor, not
   assumed (D973). A full backup of a 31.7 MB database took 15m36s against R2
   (D1051).
10. **The kit, exported and taken off the host** — [the upgrade guide](upgrade-guide.md)
    §2 step 2 — and `sudo bin/fleet.sh` showing the row.

`docs/session-02-operator-guide.md` §*Inputs you supply* is still the list of
the four files an operator writes and where each comes from; the second
project is the same steps from 4.

---

## 4. Upgrading

[The upgrade guide](upgrade-guide.md): what is installed, the release table,
the checkout half, the host sequence, skipped releases, a `major`, and what to
do when a step refuses. **Read its §1.0 first if the deployment you are
upgrading forked before 1.1.0** — a fork made when `projects/<slug>/` did not
exist has its domain inside the release's own files and §1 is not written for
it. How such a fork converts is decided and is
[its own page](on-ramp.md) (ADR 0212). One sentence here so the shape is
not lost: transport
and check out as `op`, `provision-host.sh --check`, render **with the host's
`capabilities.yaml`** as `op`, `upgrade check` and `plan` as root, deploy
alpha then beta unredirected, read the ledger and the doctor and `upgrade
verify`, re-export the kit, and — for a project with its own tables — capture
the snapshot, commit, redeploy.

---

## 5. Every day, every week

Nothing here writes, and every verdict is a **live read**: the deployed
document records what was true at its last deploy, and a project whose
archiver died yesterday still publishes the status it had then (ADR 0158).

```bash
sudo bin/fleet.sh                       # every project: release, live health, backup timers, denials by boundary (24 h)
sudo bin/fleet.sh --json --window 168   # the same, as a document, denials over a week
sudo bin/doctor.sh --project alpha-dev            # the eleven checks; 0 well, 6 a check failed or could not run
sudo bin/doctor.sh --project alpha-dev --verbose  # the numbers behind each verdict, no third party's bytes
sudo bin/backup.sh --outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json info --json
sudo bin/backup.sh --outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json schedule status
sudo bin/migrate.sh --project project.alpha.yaml --runtime status
sudo bin/dr-kit.sh export ...          # after every deploy or manifest change; docs/node-loss-runbook.md §0
```

What each page owns:

- **`docs/backup-operations.md`** — the shape, the account boundary, setting a
  project up, reading the state, the restore drill (`restore-test.sh`, which
  materialises a second copy of the cluster on disk), RPO and RTO as measured.
- **`docs/recovery-operations.md`** — the mirror, the kit, the restore onto a
  replacement, the eight rehearsals (`rehearse.sh SCENARIO --outputs … [--plan]`
  and `rehearse.sh reverse`) and what each reads; every one was read and
  reversed on 2026-09-06.
- **`docs/node-loss-runbook.md`** — the host is gone: the kit, adoption by
  recorded id, the restore from the mirror **before** the first deploy, the
  cutover last. A restore from the mirror alone completed in 247 s on
  2026-09-06 (a sample from a band, D593); a rehearsal ends at the restore
  (D1028).
- **`docs/fleet-operations.md`** — the inventory, lifecycles, retiring a
  project (`project-retire.sh --plan` first; there is no `--force`; the
  backups, bucket, cipher pass, secrets, DNS record and certificate are
  **never** touched, D957), the backup schedule, creating a project as
  measured.
- **`docs/api-operations.md`** — the connection budget, statement timeouts,
  restarting, and rotating each credential (§9 below).

**Two tables grow without bound and nothing prunes them** (D1255):
`app_private.agent_audit` and `app_private.agent_idempotency`. Read on
2026-09-15: alpha 1,508 audit rows over 21.6 days (696 kB, 44 with no
`completed_at`) and 234 idempotency rows; beta 20 and none. The retention
decision is a released migration carrying a policy, and it is on Stage 4's
bill; until then the numbers are yours to watch. `fleet.sh` counts denials by
boundary out of the same table.

---

## 6. A project's own tables, on a deployment

A project's migration set is **tracked in the release checkout** under
`projects/<slug>/` (ADR 0198), so on the host it arrives as part of the
release; only the manifest that points at it is the host's. The checkout half
— writing the set, freezing its lock, the reviewed surface, `apg dev` — is
`docs/new-team-member.md` steps 9–10 and `docs/migrations.md` §*A project's
set*. Then, measured on beta on 2026-09-10/11 and again at 1.5.0 on
2026-09-13:

1. **Edit the host's manifest with a copy beside it**
   (`project.beta.yaml.pre-session-21` was the copy on 2026-09-11), to schema
   5 or later with `migrations: {set: projects/<slug>}`, and render it **as
   `op` first**: `./deploy.sh --project project.beta.yaml --capabilities
   capabilities.yaml --render-only`. The set renders to
   `.generated/<key>/migrations-project/`, a directory of its own (ADR 0206).
2. **Two deploys if the release moves too** (D1107): the release with the
   manifest as it was, then the manifest. `upgrade plan` refuses the combined
   operation and names the split.
3. **Read the ledger, twice.** The deploy runs dbmate once per set, each
   against its own table — `app_private.schema_migrations` for the release's,
   `app_private.project_schema_migrations` for the project's — and prints
   `Pending: 0` twice. The doctor's *migrations* check counts both: beta reads
   **34** at 1.6.0. A set frozen before 1.5.0 has its applied rows moved out of
   the shared table by the deploy, as the superuser, before either dbmate run;
   nothing is re-applied.
4. **Capture the snapshot, commit it, deploy once more** (D1118). The surface
   your set publishes is served only once its migrations are applied, and the
   snapshot is captured *from* the deployment:
   ```bash
   sudo bin/dev-token.sh --project-outputs /etc/agentic-postgres/projects/beta-dev/outputs.json --role docs -- \
        bin/api-contract.sh --update --project project.beta.yaml \
        --project-outputs /etc/agentic-postgres/projects/beta-dev/outputs.json > /home/op/beta-candidate.json
   ```
   It prints the path the candidate belongs at, on stderr. Review, commit,
   CI, transport, deploy. Until that deploy the deployed document names the
   old digest.
5. **The grant is yours, and a `security_invoker` view needs two** (D1189):
   the view *and* the table it reads, to every role that may ask —
   `{{authenticated}}`, `{{agent_reader}}`, `{{agent_writer}}`,
   `{{api_documentation}}`. The example project's view was readable by nobody
   for two sessions because its first migration granted the view alone. A
   second migration, because the first is frozen; fix forward.

What the release refuses in a set, before it renders a byte of it, is the
table in `docs/migrations.md` §*A project's set*: anything naming
`app_private`, roles, schemas, extensions, a placeholder outside the six
request roles, a table in `app` without `FORCE ROW LEVEL SECURITY`, a `down`
that does not raise `AP900`.

---

## 7. The agent plane, on a deployment

**What closes the plane is the reviewed surface** (ADR 0200): a scope is
`<relation>:read` or `<relation>:write` for a relation the surface publishes,
the compiler refuses any other, and the runtime registers what the deployed
lock carries and refuses a lock the compiler did not sign. A project opens
the plane to its own tables by owning a capability manifest beside its set
(ADR 0201): `projects/<slug>/capabilities.yaml`, scaffolded by `bin/agent.sh
init`, compiled and checked by `bin/mcp-contract.sh`, both in the checkout
(`docs/new-team-member.md` step 11 says where the offline path ends and why).

On the host, measured on beta 2026-09-11 (Session 21 Run 7) and re-read at
every deploy since:

1. **The manifest names it**, at schema 6: `mcp: {capabilities: projects/<slug>}`.
   Render as `op` first; two deploys if the release moves (D1107).
2. **The deploy compiles the JOINT lock** — the release's contract less what
   the project disables, plus the project's own — from the **committed**
   canonical contracts. **The host's `capabilities.yaml` does not decide the
   lock** (D930): it reaches the render's `capabilities.enabled` list and an
   input digest, and nothing else. The lock is `mcp-capability-lock.json` in
   the rendered directory: schema 4, `tool_count`, `tools_sha256`,
   `vocabulary.data`, `contract_id` (beta's:
   `notes-tasks-agent-v1+example-note-embeddings-agent-v1`, seven tools;
   alpha's the release's six).
3. **`auth` and `mcp` are recreated when the lock changes** (ADR 0155). Until
   2026-09-11 they were not, and for eight minutes the document and the
   doctor said seven tools while the plane served six (D1152/D1153). Since
   then `resume` re-renders the mount digests before its `up`, the doctor's
   tenth check asks the running plane, and `list_resources` reports the lock
   the process loaded (D1201) — read those, never the file alone.
4. **Agents** are created through `POST /admin/agents` under the
   administrator's session, and the issuer refuses a scope outside the lock's
   vocabulary with **422** naming the ceiling (alpha, 2026-09-11:
   `['meta:read', 'notes:read', 'notes:write', 'tasks:read', 'tasks:write']`).
   A hidden tool is still callable; the boundary is the call-time scope check
   (ADR 0140). Revocation is through Studio's typed confirmation or the same
   endpoint; a revoked secret exchanged again answers 401.
5. **The audit** is written as the caller by `SECURITY DEFINER` functions
   (ADR 0135); a denial names its boundary (ADR 0178, `denial_reason` since
   migration 0032). `GET /admin/audit` filters by agent, owner and limit only
   (D1248 — a window, an outcome filter and a cursor are priced and not
   built); Studio shows the newest 500 and says so; `fleet.sh` counts by
   boundary.
6. **The SQL grant is the project's** (§6 step 5). A tool over a view the set
   never granted is served by the lock and refused by the database with
   `upstream_refused` in the audit — measured on beta 2026-09-11 (D1156),
   repaired by the example set's second migration.

**The round trip by hand**, as recorded on 2026-09-11 rather than as a
promise: the tenant scopes issued from beta's lock; `tools/list` for the
writer showing the release tools its scopes do not reach hidden;
`set_note_embedding` refused `approval_required` with `dry_run` true and false
(the shipped manifest's declaration); `update_task_status` through the plane
against a real row, `pending→in_progress` served and `pending→completed`
refused `write_conflict` and audited `write_rejected`; both agents revoked.
The scripts that did it are `/home/op/s21-roundtrip.py` and `s21-diag.sh`.

---

## 8. Studio and the generated client, against a deployment

**Studio** (ADR 0205) is one standard-library process bound to `127.0.0.1`
with no flag for anywhere else, holding the human's token in memory; the
browser gets a per-launch cookie and never the token. Against a deployment it
is launched **on the host**, because the deployed document is root-owned and
the routes it forwards to are the deployment's:

```bash
sudo bin/apg.sh studio --project project.alpha.yaml \
     --outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json \
     --username <administrator> --password-file /root/alpha-dev-administrator
```

It prints one URL with a per-launch key; a browser elsewhere reaches it
through an SSH local forward (`ssh -L <local>:127.0.0.1:<port> op@<host>`),
loopback to loopback, which is what its design permits. An administrator is
served the anonymous document by PostgREST and therefore **always sees
`stale_contract`**, and the launch line says so in as many words
(`docs/studio.md` §2). Ctrl-C ends the login session it began.

**Measured**: the host sweep launches Studio as root on this host as a
subprocess and revokes an agent through it (`studio_revocation`, passed
2026-09-13 and 2026-09-15). **Not recorded**: the operator-at-a-browser
step Session 24's plan listed as optional (its step 9); no record says it was
taken, and the six views have been exercised against a deployment only by
the sweep and by the offline rig.

**The generated client** (ADR 0204) is a checkout artefact; against a
deployment its `init()` fetches the served document *as the caller* and
answers `ok`, `stale_contract` naming both digests, `unreachable` or
`unparsable`. Measured by the sweep in the toolchain image: beta `ok`, alpha
`stale_contract` (2026-09-13, `generated_client_hash`). After a release bump
or a snapshot capture, regenerate in the checkout (`bin/apg.sh generate
--project …`, D1238) — a client that says `stale_contract` is refusing a
surface it was not generated from, and the remedy is generation, never a
flag.

---

## 9. Credentials

Every secret is materialised per consumer into an immutable generation and
mounted; any path into one is derived, never typed (D213, `docs/secret-handling.md`).
`bin/materialize-secrets.sh --help`: each run writes a new generation and
makes it active with an atomic rename; previous generations are left in
place.

**Rotation.** `docs/api-operations.md` §*Rotating a credential* is the
measured sequence and its traps for the three the API plane holds: capture
the pre-rotation value to a root-only file first (a proof you cannot admit
skips), replace it at the provider by hand and confirm it saved, **`project-runtime.sh
… --through-session 30 down` for a credential a container mounts** (D253:
`resume` runs `compose up` without `--force-recreate`, and PostgREST kept a
generation two rotations stale and crash-looped), materialize, deploy,
declare it to the gate with the matching `--rotated-*-from-file`. Performed
for the authenticator and the documentation password on 2026-08-13 and in
Session 11's window.

**The signing key has never been rotated on this deployment** (D860). The
slot has been free since ADR 0170 retired the bootstrap issuer (Session 15;
each project publishes exactly one key). The sequence is
`bin/rotate-signing-key.sh --help`'s seven steps — the new key at
`APG_AUTH_JWT_PREPARED_KEY` by hand, redeploy, **down and up so every verifier
is recreated** (a running PostgREST never re-reads its key set, and a restart
after the file is replaced leaves the container unable to start), `acknowledge`,
`promote` (refused unless every verifier acknowledged; **irreversible**), the
key moved to `APG_AUTH_JWT_SIGNING_KEY` and the prepared one cleared, redeploy,
`retire` after the deadline. It was offered on the sheet and declined at four
trips, most recently 2026-09-15, and is the first item on Stage 4's bill.
**§15 is the numbered sheet**, rehearsed offline on 2026-09-17 with what each
step was measured to print.

**The R2 credential** is `bin/storage-admin.sh --help`'s six steps
(`credential-digest`, then `verify-credential`, then `confirm-revoked` with
the retired pair). **No record of it being performed on this host was found
while writing this page.**

`bin/rotate-secret.sh` reads the contract and says which two declared secrets
**cannot** be rotated by replacing them, and look exactly like the ones that
can. Read it before a window. `bootstrap-providers.sh --destroy` revokes the
runtime identity and **leaves every secret in place, the backup cipher pass
included** (D957).

---

## 10. The gates, on the host

A release is closed by an evidence document, and an evidence document is three
halves merged: **host** (root, on the deployment), **external** (from a
network that is not the host), **offline** (a checkout with Docker, declared
never inferred, ADR 0202). `bin/session-25-check.sh --help` is the authority
for the flags; this is the sequence the trips ran.

**Before the sweep**, as `op`: the renders of §4 (both host manifests and
both example fixtures — the gate's fixture check compares the rendered
release set to the tree's, not just the outputs version, D1284), and the
op-owned copies. **`.generated/*` owned by `op`** (D1151): the sweep renders
as root and hands back since D1164; read `stat -c '%U %y'` before and after
anyway.

**The host half**, as root, with **every** declaration `--help` lists — a
flag omitted is a claim that silently goes `not_run` fifteen minutes later:

```bash
sudo -v      # first, in the foreground (D1376)
sudo bin/session-25-check.sh --mode host --host host.yaml \
  --project-a-outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json \
  --project-b-outputs /etc/agentic-postgres/projects/beta-dev/outputs.json \
  --admin-password-file /root/alpha-dev-administrator \
  --sentinel-file "$(sudo python3 -c "
import json
from pathlib import Path
root = Path('/var/lib/agentic-postgres/secrets/alpha-dev')
gen = json.loads((root / 'active-secret-generation.json').read_text())['generation_id']
print(root / 'generations' / gen / 'secret-check' / 'session2_sentinel')
")" \
  --kit-dir /home/op/kit-2026-09-11 \
  --replacement-bootstrap-state /home/op/replacement-bootstrap-state.json \
  --restore-evidence-file /home/op/restore-alpha-dev-<id>.json \
  --rehearsal-evidence-dir /home/op/agentic-postgres/evidence \
  --removed-project-file /home/op/gamma-dev-retirement.json \
  --dx-record-file /home/op/session-25-dx-record.json \
  --fresh-host-outputs /home/op/snippets-dev-outputs.json
```

- **The sentinel is derived, never typed**: the generation changes on every
  start and a typed path names a superseded one (D213).
- **`--kit-dir` names the kit exported BEFORE this release, not the newest**
  (D1282): `REC-KIT-003`'s claim *is* the version gap, and pointing it at a
  current kit destroys the proof without failing anything. As of 1.6.0 that is
  `kit-2026-09-11` (outputs v17 against a tree at v18).
- **`--removed-project-file` stays**: drop it and `project_removal` goes
  `not_run` for no reason (`g25-host.sh`'s header).
- **Run it detached, ~15 minutes**, with the script writing its own exit code
  to a file (`/home/op/g25-host.sh` is the working form: `setsid nohup … &`
  after `sudo -v`), because `echo $?` from the launching shell reads the
  launcher's status. **Read the last thirty lines** (D1199).
- **Exit 5 with the document written is the contract, not a failure** (D686):
  a claim in it is `failed` or `not_run`. Exit 1 means the gate stopped before
  claims were computed — which it did on the first sweep of 2026-09-15 and
  could not have reported a `failed` claim at all until D1373's repair.

**The external half**, from the workstation, with an ephemeral `ssh-agent` and
**`--ssh-destination op@<host>`** (D466: the broker grants one enumerated
account and `apg-agent@` is refused), and **both** outputs files, or the merge
refuses on `project_keys` (D757):

```bash
bin/session-25-check.sh --mode external --public-ipv4 <address> \
  --project-a-outputs ./alpha-dev-outputs.json --project-b-outputs ./beta-dev-outputs.json \
  --ssh-destination op@<host>
```

**The offline half** needs Docker and **cannot run on this host as `op`**
(D1375): `op` was deliberately not added to the `docker` group, so the offline
half is the workstation's, and the host's copy — a control, not an input — is
not produced. Stage 4 decides whether the host gains a way to run it or the
mode stops being something a host is asked to run.

**The merge**, from a checkout at the branch head:

```bash
python bin/write-session-evidence.py --session 30 \
  --host-input evidence/session-28-host.json \
  --external-input evidence/session-28-external.json \
  --offline-input evidence/session-28-offline.json \
  --output evidence/session-28.json
```

`--offline-input` is required for a session with an offline claim and refused
for one without (ADR 0202); the writer prints the commit each half measured
rather than folding a difference.

**One sweep per trip; a second only when the first found a defect; `-k` to
iterate**, which writes no evidence. What the document says for 1.6.0:
126 claims, 119 passed, 1 failed (`documented_path`, the first `failed` claim
this project has written), 6 `not_run`, each named with its reason in
`docs/stage-4-decision-report.md` §3.

---

## 11. Retiring a project

`docs/fleet-operations.md` §3, and `bin/project-retire.sh --help`'s eight
steps in the only order they may take. `--plan` first, always; `--confirm KEY`
is the same key said back and there is no `--force`; `--permanent` for a
permanent project; `--destroy-data` or the two volumes are kept by name for a
redeploy of the same key (ADR 0030). The record is written **before** anything
changes, and it is the `--removed-project-file` a later gate reads. Measured
2026-09-05 on `gamma-dev` (D978–D982 are what the first attempts found). What
is never touched — and is the operator's console action afterwards — is in
the command's last paragraph.

---

## 12. If something goes wrong

The upgrade guide's §6 has the deploy-time table. These are the rest, each
with the row that measured it.

| Symptom | Cause | Do |
|---|---|---|
| `sudo` line prints nothing and never returns | redirected or piped deploy, state `T+` (D972); or a backgrounded `sudo` with an expired timestamp, `[1]+ Stopped` (D1376) | `kill -CONT` / `kill %1`; `sudo -v`; run it again unredirected |
| `systemctl list-timers` blocks | the pager on a TTY, driven over `ssh -tt` (D1043) | `--no-pager`; the product's own prints carry it |
| a `--render-only` as `op` dies with `PermissionError` | `.generated/<key>` root-owned (D1151; D1110 says which root runs leave it so) | `sudo chown -R op:op .generated` |
| `migrate.sh render` says *never deployed here* for a project that is | before 1.1.0: a root-owned directory read as absent (D1060); since: exit 3 names the owner | `chown`, as above |
| the doctor says `PROBLEM` on a subject you can see is fine | the probe's route, not the subject (D673, D680, D682) | `--verbose`, read the route |
| `upgrade check` says `undetermined` | no readable installed document | exit 3 owner and `chown`; exit 4 never deployed here |
| the document says seven tools and an agent sees six | the plane is behind the file — **only possible before 2026-09-11** (D1152) | since then the doctor's tenth check and `list_resources` read the plane; if they disagree with the file, `project-runtime.sh … down` and deploy |
| `render-jwks`: *the key set CHANGED* | this file's bytes moved **against a copy that was here** | from 1.7.0 this is printed only then, so it means what it says: recreate every verifier |
| `render-jwks`: *whether the key set CHANGED cannot be told from here* | there was no previous copy at that path — the normal case, because a deploy replaces the whole rendered directory first (D1374, D1427) | it is neither evidence of a rotation nor evidence against one; `sudo bin/rotate-signing-key.sh --outputs <outputs.json> acknowledge` reads what each verifier is holding |
| a rotation proof: *the value declared as pre-rotation is the active one* | nothing was rotated: the provider did not take the edit, or materialization did not run | confirm at the provider, materialize, deploy again |
| a rotation proof fails `401 PT401` | a bootstrap-minted token missing `credential_version`, `authz_version` or the scope array (D298, D675) | repair the identity, not the thing the proof names |
| PostgREST crash-loops after a credential rotation, route 502 | a container holding a stale generation (D253) | `project-runtime.sh … --through-session 30 down`, then deploy |
| the edge answers 502 on a project route after a deploy | the deploy leaves the previous document until step 7; or the edge is not attached | `bin/edge-network.sh status --project-key <key>`; `reconcile` |
| `edge.sh status` says `staging` after a promotion | before 1.0.1 it could never say `production` as `op` (D1050) | since: `unknown` when it cannot read; read as root |
| `TimeoutError` reading Infisical | a transient (D976) | run the command again |
| `dr-kit.sh verify` says *this is not a kit* | before 1.0.1, a root-owned kit read as invalid (D1052) | since: `export` hands the kit to `op`; read as the owner |
| `dr-kit.sh verify` refuses a kit by outputs version | a kit older than v16 (`KIT_FIRST_OUTPUTS_VERSION`), or before D1141 any older version | re-export; the kit is stale after any deploy anyway |
| the gate exits 1, no evidence document | the run stopped before claims were computed — before D1373 (2026-09-15) any failing proof did this | read the JUnit; since the repair a failing proof is a `failed` claim and exit 5 |
| a claim you expected is `not_run` | its declaration flag was not passed (D687, D1133) | the flag, then the sweep once more |
| `scp` to `/tmp/apg-…` refused | a same-named file from another account (D504), or `/tmp` without its sticky bit (D1301) | a per-commit name; `chmod 1777 /tmp` |
| a proof needs Docker and `op` cannot reach it | D1375, by decision | the offline half is the workstation's |
| `Get-NetNat` empty, `ping` to the gateway 100% loss, `mtu 1280`, Tailscale up — on the **workstation**, WSL has no outbound TCP | none of the four is the fault; the trigger is sleep/resume and the fix is a reboot (`CLAUDE.md` §1) | reboot Windows; the host and Docker keep the network throughout |

The host reports `systemctl is-system-running` = `degraded`: some unit has
failed, unrelated to the deployment (both projects doctor clean), and not
investigated (`CLAUDE.md` §2). The kernel restart has not been taken since
Session 20; `--after-reboot` admits the proof that the clusters come back by
themselves, and nobody has passed it since.

---

## 13. What has never been performed on this deployment

Named so nothing on this page reads as measured when it is not.

- ~~**The signing-key rotation**~~ — **PERFORMED 2026-09-19**, on both
  projects, after being declined at five trips (D860). §15 is the record. It
  closes no claim on its own (D1469) and the three rotations below it have
  still never been performed.
- **The authenticator password, the documentation Basic Auth password and the
  application credential rotations** — the other three of the four
  `credential_rotation_planes` needs.
- **The R2 credential rotation** by `storage-admin.sh`'s six steps: no record
  found.
- **A `major` upgrade**: every plan has priced `minor`.
- **Deploying an older checkout over a newer deployment.**
- **A hop from a release older than 0.2.0**, or a deployed document older than
  outputs v13.
- **A rehearsal past the restore** (`replacement_host_restore`, `not_run` by
  decision, D1028).
- **Studio opened in a browser** against this deployment by an operator; the
  sweep has driven it, a person has not, on record.
- ~~**The kernel restart and `--after-reboot`**~~ — **BOTH DONE 2026-09-17**
  by Session 29 (D1500): `7.0.0-29` to `7.0.0-31`, eight seconds of
  downtime, `--after-reboot` declared and `port_allocation` passed. It is
  `not_run` again at Session 30 because that trip performed no reboot and
  the declaration would not have been true (D1568).
- **A person's walk** of the documented path (ADR 0207's residual); two
  sessions of a model have walked it, and `documented_path` is `failed` on the
  second's record.
- **This page, read cold.** It was written by the session that read the
  material, not by someone following it. The *upgrade* guide has now been read
  cold and repaired; this one has not.

### What HAS now been performed, elsewhere, by someone who did not build this

Recorded here because it is the first end-to-end reading of the operator's path
this project has, and because it changes what several rows above claim.

On **2026-09-16** an outside agent upgraded a real adopter's deployment from
**1.0.0 to 1.6.0** holding only this repository's documentation — six releases
in one hop, on a host this project does not administer. It converged: exit 0 on
the deploy, **10 ok / 0 problem**, `upgrade verify` matching, and a second pass
for the snapshot. It produced **eighteen findings**, all against the pages
rather than the product, and Session 27 is the session that answers them
(`docs/plans/session-27-implementation-plan.md` §1, D1388–D1405).

What that reading establishes, as distinct from what this deployment has done:

- **A hop across six releases works**, including a fork whose manifest is
  schema 4 and which therefore declares no set of its own. §4 above and the
  upgrade guide's §4 no longer rest only on this project's own trips.
- **A fork made before `projects/<slug>/` existed is a case the release had
  never met**, and the upgrade guide's §1.0 is what that reading produced.
- **`ssh -tt` is how the unredirected deploy is run from anywhere but a
  keyboard** — worked out by the reader from D972's stated cause, because no
  page said it. It now does.
- **The refusals in this product are its best part.** The reader's own words:
  every refusal named what was wrong, the schema version or release that
  introduced it, and the command to run instead. Where they were left guessing
  it was about what to do next — a documentation gap, not a product one. That
  is worth keeping in view when reading the eighteen findings as a list of
  faults.

It does **not** establish anything about this host: it was a different
deployment, a different fork and a different operator. Every row above still
stands.


---

## 14. Before a tag

**Not a host act.** This one is run in a full clone on the machine the release
is cut from, at the session close, before `git tag -a` — and it is the only
thing on this page that touches no deployment.

```bash
bin/apg.sh release-reading --ref <the deployed commit>
```

**Name the commit the tag will go on.** The deploy, the sweep and the tag land
on one commit in that order (D1425), so by the time the reading is taken the
evidence commit has already landed and `HEAD` is ahead of the tag's target —
D1513 measured 14 commits after the bump against 13 on the same day. `--ref`
reads that commit's `VERSION`, its released lock and its ADR count, so the
reading describes one commit rather than a mixture, and the first block names
which (ADR 0219). Without it the reading is of `HEAD`, which is the right
answer only when nothing has landed since the deploy. The throwaway worktree
this used to need is retired.

It prints where that commit stands, the last tag and the `VERSION` that tag carries,
what has landed since as commits and paths, **released migrations and ADRs at
the tag against the tree**, and the commit that last moved `VERSION` with
everything that has landed after it. Then it prints three questions and does
not answer them:

```
  Does everything in this window belong inside <VERSION>?
  Is there anything you intended to be in <VERSION> that is not in this list?
  Is this commit the one the tag goes on?
```

**It decides nothing, and that is the decision** (ADR 0214). Every one of this
repository's five tags has release bytes landing past it, and the two that were
defects — `1.0.0`, repaired by cutting `1.0.1`, and `1.6.1`, repaired by cutting
`1.6.2` — are the same shape as the three that were the next session starting
work. Nothing in the tree separates them, so a verdict would be invented. What
the command supplies is the half a person cannot: at the last reading, 32
released migrations at the tag against 33 in the tree and 209 ADRs against 213,
with `VERSION` unmoved.

**Four answers, and one of them is *I could not look*.** `tag_is_owed` — the
tree's `VERSION` has no tag. `tag_does_not_contain_these` — it has one, and
commits have landed since; this is the ordinary state between releases as well
as the shape of both defects. `nothing_to_decide`. And
`no_tags_in_this_clone`, which exits **3** rather than printing a clean answer
it did not measure: a shallow checkout and `git clone --no-tags` both look
exactly like a repository that has never been tagged.

**It is not in any gate**, deliberately. The gate runs in CI, where the suite's
job checks out without tags, so it would print *cannot be taken* on every run.

The tag itself stays what it has always been — the operator's own annotated
`git tag -a <version> -m "..."`, on a commit CI has already measured.


---

## 15. The signing-key rotation, step by step

**Performed on this deployment for the first time on 2026-09-19** — both
projects, in two windows, Session 30 Run 8 — after being rehearsed end to end
offline on 2026-09-17 (rig 28d) and declined at five trips (D860). Everything
below that carries a date or a number was read off one of those two windows.
**Where the rehearsal and the window disagreed, the window is what this page
now says**, and the row that records the disagreement is named.

Every line here needs root — `rotate-signing-key` requires it for *every* step
including `status`, because the deployed document and the secret generations are
root-owned and reading a verifier's key set means reaching its container.

**`OUT` is the deployment's own document**, typed in full:

```
/etc/agentic-postgres/projects/<key>/outputs.json
```

It is **not** one of the `/home/op/<key>-dev-outputs.json` copies, and this page
said it was until 2026-09-19 (D1575). `--outputs` is not a read. **Every step of
this command writes the file it names** — `write_back` hands the path straight
to `write_deployed_document`, which writes it atomically, `0600 root`. Aimed at
a copy, `acknowledge`, `promote` and `retire` would record the acknowledgements,
the promotion and the retirement into that copy, leave the deployment's own
document untouched, and chown the copy to `root:root` on the way out. `promote`
is irreversible and would print success.

**Alpha first, then beta.** Beta's window does not start until alpha reads
`steady`.

### Before you start

1. **Capture the retiring key's JWK, from the published endpoint.**

   ```
   curl -sS https://<the project's app route>/auth/jwks.json
   ```

   The app route is `routes.app.url` in the deployed document. **The document
   publishes no route named `auth`** (D1576) — the issuer lives under the app
   route, at `…/api/app/auth`. Keep the **single JWK object** whose `kid` equals
   the document's `jwt.active_kid`, not the whole key set: the proof that reads
   it back does `retired["kid"]`. Use `active_kid` as the control — if the
   endpoint's one key and the document disagree *before* you start, stop and
   read, because the whole evidence of a rotation is that they agree after it.

   This page used to say *`cat` the project's rendered `jwks.json`; it is `0444`
   by design, so this needs no root.* **Both halves were wrong** (D1573, D1574).
   There is no `rendered` directory under `/opt` at all; the set is at
   `/var/lib/agentic-postgres/rendered/<key>/jwks.json`, and while the file is
   `0444` the directory above it is `0700 root` — the mode was widened on the
   stated premise that *the enclosing directory stays `0700` root-owned*, so
   `op` cannot traverse to it. The endpoint needs no root and no host.

2. `sudo bin/rotate-signing-key.sh --outputs OUT status` — expect
   `phase steady -- one key, nothing in flight`. **Anything else means a
   rotation is already in flight; stop.**
3. `sudo bin/doctor.sh --project <key>` — the reading the window is measured
   against.
4. **`sudo docker inspect -f '{{.State.Pid}}' <any container of this project>`
   must print a non-zero number.** Step 4 below reads each verifier's key set
   through `/proc/<pid>/root/…`, the container's own mount namespace, because
   `docker cp` resolves the bind mount's source path and returns what the
   deploy wrote rather than what the process holds (ADR 0215). A daemon that
   does not run its containers on this kernel reports `0`, and `acknowledge`
   refuses rather than reading another way. Ask this before the window, not
   inside it.

### The seven steps

1. **The new key, by hand, at the provider.** Generate it the way the product
   does — `openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048
   -outform PEM` — and put it at `APG_AUTH_JWT_PREPARED_KEY`, path `/auth`. No
   command here writes a provider value (D249).

   **Then prove the value is a PEM before you deploy anything** (D1578).

   **Since template 1.9.0 `materialize-secrets` checks it for you** and exits
   **8** naming the secret and its declared kind, before the value reaches a
   file (ADR 0225). It reaches **two** of the four shapes below: a body pasted
   without its delimiter lines, and delimiters joined to the body. It cannot
   reach the other two and no check of its kind could — a value byte-identical
   to the previous one is a well-formed key, just the *previous* one, and a
   mistyped key NAME means no value is fetched at all. **So take the reading
   anyway.** It is thirty seconds and it is the half that catches the two the
   product cannot.

   Before 1.9.0 nothing in this product validated an operator-supplied key:
   `bootstrap-providers.py` checks the delimiter lines of the key *it*
   generates; the materialization path wrote whatever the provider returned.
   `render-jwks` is where a bad one lands — at deploy time, half way through a
   convergence — and it **deliberately does not echo openssl's stderr**,
   because openssl names the key's path and on some failures prints material
   from it. So the whole of what you get is:

   ```
   render-jwks: openssl failed: openssl rsa -in /var/lib/agentic-postgres/…
   ```

   The repair is one line of sequencing — materialize, read the shape, *then*
   deploy:

   ```
   sudo bin/materialize-secrets.sh --project /home/op/project.<key>.yaml \
     --requirements secrets.required.yaml --session 30
   ```

   then read the written file's **shape**, never its content:

   ```
   sudo sh -c '
     k=<key>
     r=/var/lib/agentic-postgres/secrets/$k
     g=$(sed -n "s/.*\"generation_id\"[^\"]*\"\([a-z0-9]*\)\".*/\1/p" \
           "$r/active-secret-generation.json")
     f="$r/generations/$g/_root/auth_jwt_prepared_key.pem"
     wc -c < "$f"
     grep -c -- "-----BEGIN PRIVATE KEY-----" "$f"
     grep -c -- "-----END PRIVATE KEY-----" "$f"
     awk "{ if (length > m) m = length } END { print m }" "$f"
     openssl rsa -in "$f" -noout && echo ACCEPTED || echo REFUSED
   '
   ```

   A PKCS#8 RSA key is **one** `BEGIN` line and **one** `END` line, each on a
   line of its own, with **no line longer than 64 characters**, and
   `openssl rsa -noout` exits 0. On 2026-09-19 the value was malformed **four
   distinct ways** across the two projects, and none of them was caught by
   anything but this reading:

   | What the shape said | What had happened |
   |---|---|
   | 1649 bytes, `BEGIN` 0, `END` 0 | the body was pasted without its delimiter lines |
   | byte-identical on a re-read | the edit at the provider had not been committed |
   | 1701 bytes, longest line 91 | the delimiters were there and joined to the body |
   | `absent at the provider, and optional` | the key **name** carried a trailing dot |

2. **Redeploy.**
   `render-jwks` publishes the prepared key's public half beside the active one
   and prints **`wrote … the key set CHANGED: every verifier must be RECREATED,
   not restarted`**. If it prints `published … cannot be told from here`, that
   is the normal case for a deploy that replaced the whole rendered directory,
   and it is neither evidence of a rotation nor evidence against one — what
   answers it is step 4. If it prints `openssl failed`, go back to step 1: the
   value is wrong and this deploy has left the project half converged.
3. **Down and up**, so every verifier is recreated:
   `sudo bin/project-runtime.sh --host host.yaml --project-key <key>
   --through-session 30 down`, then redeploy. A restart is not enough, and after
   the key set file has been replaced a restart is measured to leave the
   container unable to start at all.
   **Take `acknowledge` once before this, too.** On 2026-09-19 it came back
   **clean on all three verifiers at the first reading, on both projects**
   (D1473) — so a redeploy alone does recreate the verifiers, and the session
   that wants to retire this step now has a measurement rather than an
   argument. The `down` was performed anyway, both times, and this page still
   says to perform it: one clean reading is evidence to act on later, not
   licence to drop a safety step mid-window.
4. `sudo bin/rotate-signing-key.sh --outputs OUT acknowledge` — **three lines,
   not four** (D1472): `postgrest`, `storage`, `mcp`. `auth` is the issuer and
   is not a verifier; an acknowledgement from it would be the issuer agreeing
   with itself (ADR 0098). Each should say `holds the published set`.
   **What this reads is the process's copy** (ADR 0215). Before Session 28 it
   read the host's, which says `holds the published set` for a verifier that
   was never recreated — and `promote` unblocks on it.
5. `sudo bin/rotate-signing-key.sh --outputs OUT promote`. It prints `status`
   first, then asks for the literal word `PROMOTE`. **Irreversible**, and
   refused at exit 6 while any verifier is behind — measured both ways.
6. **Wait for the deadline. Then: at the provider, then `down`, then
   redeploy.**

   **This deploy is what closes the overlap window** (ADR 0224), so it is taken
   only once `retire_after` has passed. `render-jwks` builds the published set
   from three files and never reads `verification_kids`, so the moment this
   deploy renders a set holding one key, the retiring key stops being published
   and every token it signed stops verifying. Taken early, that refuses tokens
   that are still inside their own lifetime — which is exactly the harm step 7's
   refusal was written to prevent, arriving one step earlier than anyone looked.

   Read the deadline from the document and compare it with now:

   ```
   sudo python3 -c "
   import json
   print(json.load(open('/etc/agentic-postgres/projects/<key>/outputs.json'))['jwt']['retire_after'])
   "
   date -u +%Y-%m-%dT%H:%M:%SZ
   ```

   It is promotion plus **930 seconds** — about sixteen minutes — so this is
   the one real wait in the procedure. Then: move the prepared key's
   value to `APG_AUTH_JWT_SIGNING_KEY`, **clear** `APG_AUTH_JWT_PREPARED_KEY`,
   then bring the project down and deploy it again. Until this is done the
   document says the new key signs and the service is still using the old one,
   which is the one state the command cannot detect — it says so itself.
   **Nothing redeploys this project between step 5 and this step.** The deploy
   re-derives `active_kid` from the key set file's first key, which is still
   the old one until the value moves, so a redeploy in between quietly restores
   the pre-promotion record while keeping the deadline (D1474).

   **The `down` here is not caution. It is the only thing that moves the
   issuer** (D1581). A deploy recreates a container whose mounted content
   changed (ADR 0155), and the digest that decides it is built from **one**
   rendered compose payload — the runtime override — while the secret
   generation is mounted from another. A new generation is therefore invisible
   to the digest, and on 2026-09-19 the deploy did **not** recreate `auth` on
   either project. Without the `down`, `auth` goes on signing with the retired
   key while the document says the new one signs.

   **This step is also where the rotation ends.** See step 7.
7. **What `retire` actually does.** `retire_after` is promotion plus **930
   seconds** — the longest token this issuer mints (900) plus the leeway the
   verifier applies (30, D241's bisected measurement). `retire` before the
   deadline exits 6 and names the moment; with step 6 now taken after the
   deadline, you will not see that.

   **After step 6 there is nothing left for `retire` to do**, and since
   template 1.9.0 it **says so and exits 0** instead of refusing (ADR 0224).
   Two things get there first. Step 6's deploy rewrites the document's whole
   `jwt` member from the rendered key set, which puts `retire_after` back to
   `None`; and `render-jwks` builds the published set from three **files** —
   the auth key, the signing key, the prepared key — and never reads
   `verification_kids`, so clearing the prepared key at step 6 drops the
   retiring key from the published set immediately. **The two-key overlap ends
   at step 6, not at step 7.**

   Until 1.9.0 it exited **6** with *"no rotation is in flight; there is
   nothing to retire"* — the right exit for the wrong reason, and a sentence
   that says the opposite of the truth to an operator who has just completed a
   rotation (D1580, measured on both projects on 2026-09-19). It now prints
   *nothing to retire: one key is published, no deadline is set, and no
   verifier acknowledgement is outstanding*, and says that the deploy is what
   closed the window. **It writes nothing**, so the document keeps the mtime
   step 6 gave it.

   That sentence deliberately does not claim a rotation happened. The document
   cannot tell one that completed from a project that never rotated — the
   deploy writes the same three members either way (D1617).

   **Run it anyway, and read it as a record rather than as an act.** What ends
   the rotation is step 6; what proves it is three readings taken after:

   * `status` → `phase steady -- one key, nothing in flight`;
   * `acknowledge` → three verifiers, each `holds the published set`;
   * `curl -sS https://<the project's app route>/auth/jwks.json` → **one key,
     the new one, the retired one absent.**

   The last is the only one that answers the state step 6 says it cannot
   detect: it is taken from off the host, it needs no root, and the document it
   returns is derived from the auth service's **in-process** signing key.

   An ADR is owed for a refusal that cannot fire for the reason it is watching
   for. Until it is written, this page is the record.

### The window, in time

**Measured, 2026-09-19.** Alpha **~11:01–11:50 UTC**; beta **~12:00–12:25**.
Every command is seconds, the recreate is 3–5 s, the deploys dominate, and the
deadline is the only real wait. **Twenty-five minutes is what a window costs
when step 1's value is right**; alpha is what it costs when it is not, and the
deploy is what tells you.

Do not plan a sweep between `promote` and **step 6**: the proof behind
`SEC-BOOT-001` asserts the retired `kid` is **absent** from the document's
`verification_kids`, which is exactly what step 6 now does and what `promote`
deliberately does not (D1470, read with D1580).

### If `acknowledge` comes back dirty

Nothing is broken — that is the refusal working, and the verifier named is still
holding the previous key set.

1. **Do not promote.** It refuses anyway, at exit 6, and names the services.
2. Recreate that project's runtime — `down`, then redeploy — and take
   `acknowledge` again.
3. Still dirty? Compare what the container holds against the document:
   `sudo docker ps --filter label=apg.project.key=<key>`, then the digest of
   `jwks.json` inside it against `jwt.public_jwks_sha256`. A mismatch that
   survives a recreate means the deploy did not republish the set — read step
   2's `render-jwks` line, not the rotation.
4. **`abandon` is available until `promote` and not after.** Before promotion
   nothing signs with the incoming key, so withdrawing it costs nothing: clear
   `APG_AUTH_JWT_PREPARED_KEY` and redeploy. After promotion there is no way
   back and the recovery is to complete forward.

### Three lines that look like faults and are not

**At the end**, `status` prints `phase steady -- one key, nothing in flight`
and **no** `promotion BLOCKED` line. D1475 predicted one — after a *successful*
`retire`, `verifier_acknowledgements` is reset to an empty object, which reads
as *asked and unanswered* and prints `promotion BLOCKED on ['mcp', 'postgrest',
'storage']`. On the path an operator actually walks, step 6's deploy gets there
first and leaves the field `None`, which reads as *nothing has been asked* and
prints nothing. **Both are the same end state**; the difference is one field and
which command wrote it (D1579). If you *do* see the `BLOCKED` line, nothing is
blocked either.

**At step 2**, `render-jwks` may print *whether the key set CHANGED cannot be
told from here* instead of *the key set CHANGED*. That is the normal case for a
deploy that replaced the whole rendered directory; what answers it is step 4.

**At step 1**, `materialize-secrets` prints `auth_jwt_prepared_key: absent at
the provider, and optional`. That sentence is printed **identically** for a
deliberate absence — the steady state, where it is correct — and for a key whose
**name** at the provider is not the name the product reads. One of
2026-09-19's four malformations was a trailing dot on
`APG_AUTH_JWT_PREPARED_KEY`, and this is the line it produced. If you have just
pasted a key and see this, the name is wrong, not the key.

### What this rotation does not close

**It moves one proof.** `bootstrap_identity`, `api_authorization` and
`credential_rotation_planes` have been carried for five trips as *the rotation*,
and between them they need **four** rotations: this one, the authenticator
password, the documentation Basic Auth password, and the application credential
on both projects. A claim is `not_run` unless every proof it lists ran and
passed, so this window alone moves none of the three to `passed` (D1469) — one
node id of nine, `test_a_rotated_signing_key_is_the_only_one_the_plane_accepts`.
The node-id table is in `docs/plans/session-28-implementation-plan.md`,
Appendix R.

**And the node id it moves has still not been taken.** No sweep has read the
retired JWKs; they are kept at `/home/op/s30-retired-<key>-jwk.json`, each a
single JWK object, for the first sweep that passes `--rotated-jwt-from-file`.

**And the overlap does not survive a deploy.** `render-jwks` builds the
published set from three files — the auth key, the signing key, the prepared
key — and **never reads `verification_kids`**. So any deploy taken between
`promote` and the deadline drops the retiring key from the published set at
once, whatever the document says is still verifiable. Step 6 is ordered after
the deadline for exactly that reason, and the ordering is a procedure, not a
guard: nothing refuses a deploy taken early.

Making `render-jwks` read `verification_kids`, so that the overlap is a
property of the product rather than of the order the sheet is walked, is **the
right fix and is deferred by name** (ADR 0224). It changes what is served at
`/auth/jwks.json` mid-rotation and can only be proved by performing a
rotation, so it belongs to the session that performs the other three — which
is also what D1469 says is owed before any rotation claim can be taken.
