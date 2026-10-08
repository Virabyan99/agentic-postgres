# Session 38 — the move: a self-hosted secret store, and the deployment to OVHcloud

**Status: PLANNED 2026-10-08 at `da03eb8`. NOT STARTED: the next chat executes it from Run M1.**
An insertion into Session 38 (`docs/plans/session-38-implementation-plan.md`), between its
Run 10 (done, `da03eb8`, CI run 37810048004 green) and its Run 11 (the trip). It exists
because of **D2223** (the operator, 2026-10-08): Infisical's paid plan is priced per
identity, so the secret store is self-hosted on its own small VPS, and the deployment moves
from the Hetzner CX23 to an OVHcloud VPS **before** the trip, so that Runs 11–13 measure
the host the product will keep. Seven runs: two change code (M1, M3), five are sittings or
readings. The plan spends **D2239–D2262** and **ADR 0262–0263**; its runs add rows from
**D2263**.

**Brief:** the operator's decisions of 2026-10-08 — D2223 (self-hosted Infisical, the move
before the trip), D2222 confirmed, the two servers bought and **kept in the US** (D2251) —
and D2227 (the sweep's declarations are files on the old host; this plan owns them).
Read with: `docs/node-loss-runbook.md` whole; ADRs **0071, 0110, 0187, 0188, 0189, 0192,
0195, 0250, 0255, 0257**; `docs/operator-guide.md` §2–§3 (`:93-277`);
`docs/session-02-operator-guide.md` §0 (`:37-82`); `docs/host-baseline.md`;
`docs/provider-bootstrap.md`; Session 18's plan Run 6 (`:536-546`, the one replacement host
ever built) and its row D1028 (`:119`).

**Shape:**

| Run | Kind | What it leaves |
|---|---|---|
| **M1** | code + sitting | `infra/secret-store/` committed (CI read); the secret store running at `https://secrets.agenticpostgresql.com`, backed up off-host, its restore rehearsed |
| **M2** | sitting | the OVH main host provisioned at `c3eec1d` (1.15.0), its edge up on staging; the self-hosted API measured by the product's own `bootstrap-providers` |
| **M3** | code | `bootstrap-providers --rehome` and the carried secret ages (ADR 0263), CI read |
| **M4** | sitting (Hetzner) | alpha, beta and control-prod read their secrets from the self-hosted store, on the old host, unchanged otherwise; a new kit |
| **M5** | sitting (both hosts) | beta, then alpha, then control-prod restored on OVH from the mirror, deployed, DNS moved, the registry re-adopted |
| **M6** | sitting (OVH) | the declarations carried or re-decided, a reboot, a `-k` verification, the capacity read for Run 11 |
| **M7** | docs, days later | the old host retired, the Cloud organisation emptied, Session 38's plan amended for the trip |

**Written for whoever picks this up cold, and it will be a different model than the one
that planned it.** Every path below was read from the tree on 2026-10-08 at `da03eb8` by
four explore passes (Infisical's integration, the kit/adopt/restore path, the fresh host,
the sweep's declarations) and direct reads of `docs/node-loss-runbook.md`,
`tests/deployment/test_session18_recovery.py:180-371`, `docs/operator-guide.md:93-277`,
`systemd/agentic-postgres-project@.service` and `bin/backup.py:686-731`. **Read CLAUDE.md
§1 in the launch folder before the first command, then this plan's §1, then the
appendix.** If a step here and the tree disagree, **the tree wins and the disagreement is a
divergence row** (next free `D` after §1), never a silent reconciliation. When this plan
names a line number, open the file there and read the twenty lines around it.

**The eight sentences the executor most needs, in case nothing else is read:**

1. **Two changes, in this order, never together.** First the SECRET STORE moves (M4: on the
   old host, nothing else changes — every value copied, verified by the product's own
   reader, the old state kept for rollback); then the HOST moves (M5: by
   `docs/node-loss-runbook.md` exactly, against the store the kit now names). The runbook's
   rule that the kit's `infisical` block *"stays exactly as it is"* (`:58-61`) is why: an
   adoption binds by project id at the recorded `api_url` and refuses any difference
   (`bootstrap-providers.py:1100-1112`), so the store must have moved before the kit that
   carries the projects to OVH is exported.
2. **The secret store holds every project's every secret, the backup cipher pass above
   all** (`secrets.required.yaml:828-847`; ADR 0188: the mirror does not survive the loss of
   the Infisical project). Losing that VPS without its backup AND its `ENCRYPTION_KEY` is
   losing every backup. **Its backup is encrypted to an `age` key only the operator holds,
   its keys never enter a kit, a file in the repository or this conversation, and its
   restore is rehearsed in M1 before any project depends on it** (ADR 0262).
3. **No value crosses the workstation or the conversation.** `--rehome` reads each value
   from the old store and writes it to the new one in one process, as root, on the host,
   and prints names only (ADR 0263). The two operator credentials are placed on a sheet and
   shredded on the same sheet.
4. **The old host stops writing before the new host archives.** Each project is frozen on
   Hetzner (timers disabled, a final incremental backup, the unit stopped and disabled, the
   mirror copied by hand) BEFORE OVH restores it; the OVH deploy then archives into the
   SAME primary bucket on a new timeline (D2243). The mirror's timer is enabled on OVH only
   after Hetzner's is disabled — its `mc mirror --remove` would otherwise delete a copy.
5. **Beta first, alpha second, control-prod last** (D2253). Beta carries the edge's
   staging-to-production promotion (D2249); alpha carries the replacement-host claim
   (D2246); control-prod carries the registry, re-adopted for all three after its own move.
6. **OVH runs `c3eec1d` (1.15.0) at the end of this plan**, the kit's `source_commit`,
   host schema 3. Session 38's Run 11 then upgrades it to 1.16.0 exactly as planned — the
   upgrade price, the deploy windows and the schema-4 host sheet are measured on the host
   that stays (D2244 keeps the two changes apart for the same reason as sentence 1).
7. **The old host is kept, stopped, until M7** — its volumes intact, its units disabled, its
   Cloud identities still able to read the Cloud store: the rollback for any project is
   *re-enable its unit on Hetzner and move its DNS record back* until M7 says otherwise.
8. **Both servers are in the US** (operator, 2026-10-08, D2251): the main host in OVH
   US-East (ARIN: `VPS-US-EAST-VA-2`, Reston VA), the secret store in OVH US-West
   (`VPS-US-WEST-OR-2`, Hillsboro OR). The backups and the mirror stay in Europe (R2,
   B2 `eu-central-003`), so every restore crosses the Atlantic. Measured in M5, not
   assumed.

---

## 0. Where the plan starts

```
REPO          HEAD da03eb8 (Session 38 Run 10's repair), CI 37810048004 green, pushed.
              1.16.0 is NOT tagged and NOT deployed: the tag lands in Session 38 Run 12.
              CURRENT_SESSION 38, template_version 1.16.0, 330 requirements, 237 claims
              (89 offline). NEXT FREE D2239, ADR 0262 before this plan.
OLD HOST      Hetzner CX23 62.238.99.122 (apg-vps-01), Ubuntu 26.04, 3,814 MiB, 2 vCPU,
              38 GB, no swap. alpha-dev, beta-dev, control-prod at 1.15.0, source_commit
              c3eec1d; checkout c3eec1d; host.yaml schema 3 (checkout) / 2 (/etc, E0).
              Registry agrees x3 on c3eec1d.
STORE (OLD)   Infisical Cloud, https://app.infisical.com, organisation
              3302b5a4-7288-424f-bcd3-6cd158617827 (slug personal-org-hmxi), environment
              dev, runtime folder /runtime (host.yaml:71-78). 4 machine identities of 4:
              three runtimes + the control-plane identity (D2146). 120 secret ops/min (D2139).
NEW MAIN      15.204.231.45, OVH US-East. 8 GB / 4 vCore by the operator's purchase; OS,
              memory, disk and interface UNREAD (Sheet E1). SSH answers
              `OpenSSH_10.2p1 Ubuntu-2ubuntu3.2`; the workstation's operator key is NOT
              installed (2026-10-08: `ubuntu@` and `root@` both `Permission denied`).
NEW STORE     15.204.66.146, OVH US-West. Size UNREAD (E1). Same banner, same refusal.
KITS          WSL ~/dr-kits/kit-2026-10-06-s37 (three projects, release f58b471 -- OLDER
              than the c3eec1d redeploys, D2141) and ~/dr-kits/kit-2026-09-11 (the gate's,
              D1282). No kit of the current deployment exists: M4 makes one.
```

**What exists and is used as it is** (each read 2026-10-08):

- `host.yaml`'s `infisical.api_url` takes any `https://` host (`host.schema.json:255`); no
  code, schema `const` or test pins `app.infisical.com` — the clients build every URL from
  the field (`infisical_client.py`, `bootstrap-providers.py:271-573`), and both verify TLS
  against the system store with no way to switch it off (`infisical_client.py:198`,
  `bootstrap-providers.py:299,324`). **A self-hosted store needs a publicly trusted
  certificate** — Let's Encrypt, D2250.
- Universal Auth everywhere: login `POST /api/v1/auth/universal-auth/login`, reads
  `GET /api/v3/secrets/raw/{name}`; the bootstrap's ten calls are listed at
  `bootstrap-providers.py:315-573` (project creation is `POST /api/v2/workspace`; the read
  of a project accepts both the `workspace` and the `project` wrapper, D1026).
- The node-loss runbook, the kit (`bin/dr-kit.sh export|verify`, names only, ADR 0189),
  `--adopt` (a fresh identity against the recorded project id), `bin/restore.sh --from
  mirror|primary --latest [--plan]` (exit 7 on a volume that holds a cluster or is mounted,
  5 on *no backup set*), the deploy on a restored volume (no `initdb`; step 6c's
  `stanza-create` is idempotent, `bin/backup.py:27`).
- `bin/provision-host.sh --check|--apply|--confirm-ssh-ok|--confirm-firewall-ok`: Ubuntu
  24.04 or 26.04 only (`:262-270`), x86_64 (`:255`), NTP (`:274-281`); it does NOT create
  `op` (D659) nor `apg-agent` (by hand, `infra/host/apg-agent.sudoers`).
- `bin/edge.sh --host host.yaml up|status|promote-acme --to production --confirm <host.id>`;
  HTTP-01 on `web` (`infra/edge/traefik.yaml:117-127`); certificates in
  `/var/lib/agentic-postgres/edge/acme/{staging,production}.json`.
- `systemd/agentic-postgres-project@.service`: start = `materialize`, `up`, `attach`, edge
  reconcile; **stop = `detach` then `down`** (containers removed, volumes kept).
- `bin/backup.sh --outputs F backup --type full|incr | info | mirror | schedule
  status|enable|disable` (`bin/backup.py:801-850`); `mirror` is `mc mirror --overwrite
  --remove` in the `backup-mirror` container and needs the project's render, not its
  running containers (`:686-731`) — **unmeasured with the unit stopped**: Sheet F-beta reads it.

**What does not exist and this plan builds:** a way to move a project's provider project
between two Infisical instances by value (M3, ADR 0263), and the secret store's own files
(M1, ADR 0262). **Nothing else.** No other product code changes.

---

## 1. The divergence table

| D | The brief / runbook says | The tree / the facts | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D2239** | D2223: *"Infisical stood up (… its encryption key into the DR kit …)"*. | A kit holds names, never values (ADR 0189, `dr_kit.py:85-106`), and REC-KIT-001 (`test_session18_recovery.py:221-260`) fails a kit that contains any secret value the host holds. | **The store's `ENCRYPTION_KEY`, `AUTH_SECRET` and the backup's `age` identity are held by the operator off every host** (a password manager and one offline copy), written on the store host only into `/etc/secret-store/infisical.env` (0600, root) and never into a kit, a repository file, a record or this conversation. The kit is unchanged. | The kit's one property is that losing it leaks nothing. | 0262 |
| **D2240** | `docs/node-loss-runbook.md:58-61`: the kit's `infisical` block *"stays exactly as it is"*; D1028. | Moving the store changes `api_url` and the organisation, which `PROVIDER_RELEVANT_HOST_FIELDS` (`bootstrap_state.py:54-60`) digests; `--adopt` refuses a different `api_url` (`bootstrap-providers.py:1100-1105`) and a different digest (`:1106-1112`). Adoption cannot cross stores. | **Two changes in order**: the store moves first, on the old host, by a new mode (D2241); a kit is exported after it; the host then moves by the runbook unchanged. | Each change is reversible on its own and each is measured by the command that will be used again. | 0263, 0189 |
| **D2241** | — (the move needs a way to carry values). | `--apply` creates the provider project and GENERATES every generated value (`:800-1014`) — a new cipher pass would make every backup unreadable (D999); `--adopt` binds by id within one store. Copying 63 values by hand at two consoles puts every value on a screen. | **`bootstrap-providers.sh --rehome-check` / `--rehome`** (ADR 0263): read every value the contract declares for the project from the recorded store as a SOURCE credential, create the project in the store `host.yaml` now names, write each value, mint the runtime identity, read every value back AS that identity and compare digests in memory, and only then write the state; the old state and credential files kept beside it for rollback. Names only on stdout. | The product's own reader proves the copy; a hand copy proves nothing. | 0263 |
| **D2242** | ADR 0250: a secret's age is its provider `updatedAt`. | A rehome writes every value at the new store, so every age reads 0 days: beta's never-rotated trio (since 2026-08) would read as fresh — the reassuring direction of a wrong premise (D930's class, ADR 0195). | **The rehome writes `/etc/agentic-postgres/projects/<key>/secret-ages-carried.json`** (0600; per name the source `createdAt`/`updatedAt`, the rehome's time, the source project id; no value) and `secret_age` reads the OLDER of the carried and the provider's answer. The kit carries the file as an OPTIONAL artefact (an old kit without it still verifies; REC-KIT-001's artefact list unchanged). On the old host at `c3eec1d` the doctor still reads 0 days until Run 11's deploy — said in M4's Done. | An age that forgets the move is a report folding into the good answer. | 0263, 0250, 0195 |
| **D2243** | `docs/node-loss-runbook.md:104-108`: *"`backup.bucket` names the **new** primary bucket … The old primary is gone or is production's; neither is this host's to write."* | A loss leaves the old host writing nothing it controls; a MOVE stops the old host first. A second bucket per project is three consoles, three new token pairs and three values the store must be re-told — and the history of each repository split in two. | **The same primary bucket**: the old host's archiving stops (Sheet F-key) before the new host's deploy; the deploy's 6c `stanza-create` finds the stanza the restored cluster already belongs to (same system identifier) and archives on the new timeline. **Measured on beta first**: a 6c or `check` failure on beta is §9's stop, and the runbook's new-bucket path is the fallback. The runbook gains a § *A planned move* in M7. | One repository per project, its history whole; the runbook's rule protects a writer that, here, has been stopped. | 0192 |
| **D2244** | The runbook restores at the kit's `source_commit`; Session 38's Run 11 upgrades the deployment 1.15.0 → 1.16.0 and measures the price (R1) and the windows (R2a–c, D2171). | A restore-then-deploy at 1.16.0 would merge the move and the upgrade: R1 could read no deployed document, and the windows would be a first start, not an upgrade. | **OVH runs `c3eec1d` at host schema 3 to the end of this plan.** Run 11's bundle base `c3eec1d..main` stays valid (OVH is cloned from a full bundle that contains it). `--rehome` (on `main`) runs on the old host from the checkout moved to `main` for the sheet and back to `c3eec1d` after it; the state it writes keeps `bootstrap-state` schema unchanged so `c3eec1d`'s readers read it (proved on the host: M4's materialize and kit). | One change measured at a time; the upgrade's numbers belong to the host that stays. | — |
| **D2245** | D659 / `session-02-operator-guide.md:68-80`: `op` created by hand as **root**, proved while root still logs in. | OVH's Ubuntu images log in as `ubuntu` (key, `NOPASSWD` sudo through cloud-init's `/etc/sudoers.d/90-cloud-init-users`); root has no key. After `op` exists, `ubuntu` is a second privileged account the baseline does not know. | **`op` is created through `ubuntu`'s sudo** (Sheet E1), proved in a new session, and then **`ubuntu` is locked**: its `authorized_keys` emptied, `usermod -L ubuntu`, the cloud-init sudoers file removed — on the main host AND the store host. Read after: `sudo -l -U ubuntu` names nothing. | One privileged account per host, the one the product names. | 0071 |
| **D2246** | §0 / Session 38 §7: `replacement_host_restore` `not_run` by decision (D1028); Run 12's merge expects exit 5 for it. | REC-NODE-002 (`test_session18_recovery.py:347-371`) needs a REPLACEMENT host's deployed document carrying the kit's `instance_uuid` with every route `ready`, and a mirror restore record naming it. **The move IS that restore, deployed**: alpha restored on OVH from the mirror keeps the `instance_uuid` kit-2026-09-11 recorded (the same cluster since). | **Alpha's restore is `--from mirror`**, its record kept at `/home/op/restore-alpha-dev-<id>.json`; Session 38's sweep declares `--replacement-host-outputs /home/op/alpha-dev-outputs.json` and `--restore-evidence-file` = that record (REC-REPO-003's and REC-NODE-001's other readers are satisfied by it too: source `mirror`, timeline ≥ 2, this host's alpha). **Run 12's expected exit 5 then names `documented_path` only** — if the claim passes. Session 38's §7 and Sheet S1 amended in M7. | The claim was `not_run` because no replacement was ever deployed; this one is. | 0189, 0192 |
| **D2247** | D2227: *"The migration's plan owns the declarations: each is carried to the new host or re-decided there."* | Fourteen files (§0 of Run M6's table): eleven are records of acts on the old host that cannot be redone; three describe the host's size or its last redeploy. | **Copied as they are** (byte-identical, sha256 compared old/new): `/root/alpha-dev-administrator`, `/root/control-prod-administrator`, `/root/s36-prev-{app_runtime,postgrest_authenticator,docs_basic_auth}_password`, `/home/op/s30-retired-alpha-dev-jwk.json`, `/home/op/kit-2026-09-11/`, `/home/op/replacement-bootstrap-state.json`, `/home/op/restore-alpha-dev-202609060727818b.json` (superseded as the gate's record by D2246's, kept), `/home/op/gamma-dev-retirement.json`, `/home/op/session-25-dx-record.json`, `/home/op/snippets-dev-outputs.json`, and `evidence/rehearsal-*.json`. **Re-made on OVH**: `/home/op/s31-third.yaml` (re-sized against OVH's free memory, Sheet M6-A), `/root/s36-redeploy-before.json` (by `~/s36/run7/s36-redeploy-before.py` before Run 11's R2a, which is the next redeploy), and the `admission-refused` rehearsal (`bin/rehearse.sh admission-refused` on alpha, since it reads this host's capacity). | A record of what happened is evidence wherever it is read; a reading of this machine is evidence only on this machine. | — |
| **D2248** | `docs/node-loss-runbook.md:146-156`: deploy, then `doctor` reads `ready` on every route. | Before its DNS record moves, a project's hostname still resolves to the OLD host, so a route probe through the public name cannot read the new host. Unmeasured: Session 18 never deployed its copy. | **Per project: restore → deploy (routes may read `unavailable`; recorded, not a failure) → ports (`--render-runtime-only`, `database-ports.sh verify`) → DNS moved → the certificate → a SAME-COMMIT redeploy** (D2034: takes nothing away), after which `doctor` and the document must read `ready`. Measured on beta first. | The document records what it could read; reading it again once the name points here is the honest order. | 0158 |
| **D2249** | `docs/operator-guide.md:157-172`: the edge starts on staging and is promoted once every hostname holds a staging certificate. | On OVH no project hostname resolves to the new host until its cutover. Copying `production.json` from Hetzner would carry the ACME account key and every certificate's private key through the workstation — and whether the edge then renders production at once is an inference from `edge_state.py:70-145`, untested. | **Not copied.** The edge comes up on staging (M2). **Beta's cutover carries the promotion**: DNS moved → one request → staging certificate → `promote-acme --to production --confirm apg-ovh-01` → one request → production certificate. Beta serves a staging certificate for those minutes. Alpha and control-prod then issue production on their first request. One attempt per hostname, never a loop. | The minutes are beta's, a dev project's; private keys stay on the host that made them. | — |
| **D2250** | D2223: *"TLS; a firewall admitting the main host and the operator"*. | HTTP-01 needs port 80 reachable by Let's Encrypt from anywhere; **Docker-published ports bypass ufw** (why the product has `infra/host/docker-user-rules.v4`); the operator's address is not fixed. | **Caddy on the host network** (ufw applies), `secrets.agenticpostgresql.com` → `127.0.0.1:8080`; Infisical publishes `127.0.0.1:8080` only; PostgreSQL and Redis publish nothing. **ufw: 22/tcp any (key-only), 80/tcp any (Caddy: the challenge and a redirect), 443/tcp from `15.204.231.45` and `62.238.99.122` only.** The operator reaches the console through `ssh -L 8443:127.0.0.1:443` with the name pinned by `/etc/hosts` on the workstation side, or — measured in Sheet I2 if that fails — a temporary `ufw allow from <operator address> to any port 443` removed on the same sheet. Measured from outside: 443 refused/filtered from the workstation, open from the main host. | The store answers only the hosts that read it. | 0262 |
| **D2251** | D2223: *"OVHcloud's VPS … (8 GB / 4 vCore, Warsaw)"*. | ARIN (2026-10-08): `15.204.231.45` is `VPS-US-EAST-VA-2` (OVH US LLC, Reston VA); `15.204.66.146` is `VPS-US-WEST-OR-2` (Hillsboro OR). Asked; **the operator keeps the US**. | **Plan for the US.** The region values Session 38's Sheet H1 declares are read from the OVH console (D2161's rule), never from ARIN. The backups stay where they are; every restore and every nightly mirror pass crosses the Atlantic — M5 records each restore's seconds against Session 18's 247 s. | The operator's choice, measured rather than assumed. | 0257 |
| **D2252** | D2145: ONE slot on the CX23 (1,624 MiB available), the 1,024 MiB floor (D2042); `reserve_memory_mb` 2,214 (D1992). | OVH's memory is roughly double; admission's claimable = `memory_mb − 2214`. Session 38's code, sheets and proofs name one slot, `slot1-prod`. | **Session 38 keeps ONE slot.** OVH's `host.yaml` declares `memory_mb` as read by `free -m` (total), `reserve_memory_mb: 2214` (D1992), `disk_gb`/`reserve_disk_gb` from `df` and 8; the floor of 1,024 MiB stands. A second slot is Session 39's declaration, priced from M6's reading. | A larger host changes the margin, not the session's scope. | — |
| **D2253** | `docs/plans/stage-5-plan.md:993-996`: after a node LOSS the runbook restores the control project FIRST (owed by Session 42). | A planned move keeps the old host serving: the registry is readable all along, and the most valuable project should move after the order has been proved twice. | **Control-prod moves LAST** here; Session 42's loss order is unchanged and named in §10. | A move is not a loss; the first restore should be the one that costs least to repeat. | — |
| **D2254** | ADR 0187: retirement never deletes a provider project. | After the move: three Cloud projects, four Cloud identities, the old host's self-hosted identities (minted by the rehome) and the Hetzner server itself outlive their use. | **M7, after a hold of at least 72 h and a green Run-11-ready reading**: `bootstrap-providers --destroy` ON THE OLD HOST for each key (revokes the identity the rehome minted there; the project is left, `:1017-1058`); the operator deletes the Cloud projects and identities at the Cloud console; the Hetzner server is cancelled by the operator. Each named in M7's Done. | The rollback lives until the new host has run a day unattended; then nothing old can read a value. | 0187 |
| **D2255** | D2146: *"upgrade the Infisical plan before Sheet SL1"*; Sheet SL1's credential is `infisical-control-plane-credential`. | The self-hosted store has no identity limit (its unlicensed defaults: `identityLimit: null`, `getDefaultOnPremFeatures`, read 2026-10-08) and **no API rate limit by default** (Infisical's rate-limit page). | **D2146 is void**; SL1 runs unchanged against the self-hosted store, whose control-plane credential keeps the same path. The 429 budget (ADR 0255) stays: it costs nothing when unused. | — | 0255 |
| **D2256** | — | Whether the Cloud control-plane identity may READ secret values in the three projects is unmeasured: it created them (the creator is a project member), but reading is not what it has ever done. | **`--rehome-check` reads every source value (digests only) before anything is written anywhere** — the measurement and the precondition are one command (M4, Sheet RH1). A refusal there is §9's stop, not a console workaround. | Measured by the command that depends on it. | 0263 |
| **D2257** | D1026: the hosted API answered under `workspace` where the source declared `project`. | The self-hosted image's version is newer than the Cloud's behaviour the client was written against; endpoints may have moved (`/api/v2/workspace` → `/api/v1/projects`?). | **M2's rig runs the product's own `bootstrap-providers --plan/--apply/--destroy` and `materialize-secrets` for a throwaway `rig-dev` against the store** (D1114), with the image tag and digest recorded; any endpoint that answers differently is a row and a repair in M3, before the rehome uses it. | The client is measured against the store it will use, with the command that uses it. | 0262 |
| **D2258** | — | The store's own database: Infisical's compose runs PostgreSQL and Redis; its docs: back up the `pg_data` volume and `ENCRYPTION_KEY`; Redis is regenerable. | **Nightly `pg_dump -Fc` inside the `db` container, piped through `age -r <recipient>`** to `/var/backups/secret-store/` (0600, 14 kept) **and uploaded to a B2 bucket `apg-secret-store-backup`** with an application key restricted to that bucket (the operator's, at the console — ADR 0110), by a pinned `rclone` image, under a systemd timer; the restore rehearsed in M1 (Sheet I4) into a throwaway compose project on the same VPS, read through the API. | A backup nobody restored is a file. | 0262 |
| **D2259** | — | The rehome runs on the old host while beta's, alpha's and control-prod's states still name the Cloud; `host.yaml`'s `infisical` block is host-wide. | **The block is changed in both copies** (checkout and `/etc`, D2025) **immediately before the three rehomes, which run back to back** with no deploy, restart or materialize between them; a project not yet rehomed keeps reading the Cloud through its own recorded state. The rollback of a project = its kept state and credential files moved back, and the block restored. | Host-wide input, per-project state: the window is minutes and nothing reads the block in it. | 0263 |
| **D2260** | — | The rehome's new generation must equal the old one, or the move changed a secret. | **After the rehomes, `materialize-secrets` (at `c3eec1d`) writes a new generation per project and `~/s38/mig/gen-compare.py` (root) compares every consumer file of the new and the previous generation byte for byte, printing counts and names only**; then a same-commit redeploy per project with the probe running (`s37-probe-start.sh`), its windows read. | The product's reader is the proof; the probe says what the redeploy cost. | 0155 |
| **D2261** | `infra/` holds the edge and the host baseline; `versions.env` pins every image. | The store is not a product host and runs nothing of the product. | **`infra/secret-store/`** (compose, Caddyfile, backup script and units, an env template with names only), its images pinned by digest in the compose file itself (not `versions.env`: no product build reads them), guarded by `tests/contract/test_secret_store_files.py`; `docs/secret-store.md` is its operator page, indexed. | Reproducible, reviewed, and outside the release's surface. | 0262 |
| **D2262** | Session 38 plan Run 11: *"Before the day: … the Infisical plan upgraded (D2146)"*; Sheet P1's `A slot1… → 62.238.99.122`; D2161's Hetzner region values; Run 13's envelope rows *"each naming the CX23"*; CLAUDE.md §2's HOST block. | All describe the old host. | **M7 amends Session 38's plan** (a row per change, not a silent edit): Run 11's precondition becomes this plan's Done; the slot's A record → `15.204.231.45`; H1's region values read from the OVH console; the envelope rows name the OVH host; `~/s38/host-address` holds `15.204.231.45`; and CLAUDE.md §2 is rewritten (copied to the scratchpad first). | The trip reads the plan; the plan must describe the host the trip uses. | — |
| **D2263** | Sheet E1: `ubuntu` locked; D2245. `docs/secret-store.md` §1: port 22 *key-only*. | Read 2026-10-09 on both servers: `/etc/ssh/sshd_config.d/50-cloud-init.conf` says `PasswordAuthentication yes` and is read BEFORE `60-cloudimg-settings.conf`'s `no` (sshd keeps the first value) -- **both servers accept passwords** (`sshd -T`: `passwordauthentication yes`). The main host gets `00-agentic-postgres-ssh.conf` from `provision-host.sh` pass 2 (`:935`), which sorts first; **the store host runs no `provision-host.sh`**. The only sudo grant is `/etc/sudoers.d/90-cloud-init-users` (`ubuntu ALL=(ALL) NOPASSWD:ALL`); groups `sudo` and `admin` are empty. | **Sheet E1 installs the product's own `infra/host/00-agentic-postgres-ssh.conf` on the store host** (`__SSH_PORT__` → 22, `sshd -t`, reload, a NEW session before anything else), and removes exactly `90-cloud-init-users` on both. Read after: `sshd -T` → `passwordauthentication no`, `permitrootlogin no`; `sudo -l -U ubuntu` → not allowed. | One hardening file, the one the product reviewed, on every host it reaches. | 0262 |
| **D2264** | Sheet E1: the key put in at the OVH console; the host key pinned against the console's fingerprint. | **Done 2026-10-08/09 by the operator with `ssh-copy-id`**: OVH mails a one-time password that is EXPIRED at first login (`Password change required but no TTY available` under `ssh-copy-id`), so one interactive login changed it first. Fingerprints recorded at first connection and read back on the hosts: main `SHA256:eyJyvNfVC7okGz57f7nfirmqjsB72ZO+B2AgU3QALAo`, store `SHA256:pRl0fEeVUYkA1okZePYU2CiAOQ3gejDGD1a9wNuIPwE` (trust on first use; not compared with the console). **Readings**: main Ubuntu 26.04 x86_64, 4 vCPU (Haswell), 7,746 MiB, no swap, 72 GB, `ens3`, IPv4 `15.204.231.45/32` **and public IPv6 `2604:2dc0:101:200::5466/128`**; store Ubuntu 26.04 x86_64, 2 vCPU, 3,814 MiB, no swap, 38 GB, `ens3`, IPv4 only. Both NTP-synchronised, Docker absent, ufw inactive, only sshd listening publicly. | E1's key half is done; `public_interface: ens3` for the main host; **no AAAA record for any name on the main host** (it has an address one would point at). | -- | -- |
| **D2265** | ADR 0262 / D2261: the store's files. | Infisical's own `docker-compose.prod.yml` (read 2026-10-09): one `.env` handed to EVERY container (the database and Redis see `ENCRYPTION_KEY`), floating tags (`infisical:latest`, `redis`, `postgres:14-alpine`), the backend published on `80:8080`. Infisical v0.165.16 reports `inviteOnlySignup: true` on a fresh instance (`/api/status`). | **Three env files, one reader each** (`infisical.env` the backend, `db.env` the database, `backup.env` the backup's rclone), the non-secret settings in `environment`; tags pinned by digest (`infisical v0.165.16`, `postgres 16.15-alpine`, `redis 7.4.11-alpine`, `caddy 2.11.4-alpine`, `rclone 1.75.1` -- the newest at least two weeks old on 2026-10-09, each digest read from the registry with linux/amd64); `127.0.0.1:8080` only. **Whether the first account can sign up under `inviteOnlySignup` is Sheet I2's reading.** | Upstream's file is a demo; the store holds the cipher pass. | 0262 |
| **D2266** | -- | Caddy's ACME account here has no e-mail (`cert_issuer acme`, no `email`), so no expiry notice reaches anyone; Caddy renews on its own, and nothing in the product reads the store's certificate. | **Accepted for now; read by hand** in M6 (`openssl s_client` from the main host: issuer, `notAfter`) and named in §10 -- a host's `materialize-secrets` failing with a TLS error is the symptom, `docs/secret-store.md` §7. | An e-mail in a committed file would be the operator's address in the repository. | 0262 |

---

## 2. What the plan adds to `tests/acceptance-registry.yaml`

Two requirements and two OFFLINE claims, added in M3 (the moving of counts is all-or-nothing,
D690: `src/agentic_postgres/__init__.py`'s Session 38 paragraph moves with them):
requirements **330 → 332**, `CLAIMS` **237 → 239**, `OFFLINE_CLAIMS` **89 → 91**,
`CLAIM_INTRODUCED_IN` 38 for both.

| ID | Requirement | Proofs (offline) | Claim |
|---|---|---|---|
| `REC-REHOME-001` | `--rehome-check` reads every declared value from the recorded store and writes nothing; `--rehome` refuses when the host names the recorded store, when a required source value is absent, or when the destination already has the project; it writes the state only after every value read back as the NEW runtime identity equals the source; it keeps the old state and credential files; it prints no value; the carried ages are written and `secret_age` reads the older answer | `tests/contract/test_provider_rehome.py` (names are Run M3's, read from `--collect-only`, D1236) | `provider_rehome` |
| `REC-STORE-001` | The secret store's files pin every image by digest, publish nothing but `127.0.0.1:8080`, run Caddy on the host network, name no secret value, and the backup script encrypts before it writes or uploads | `tests/contract/test_secret_store_files.py` | `secret_store_files` |

The ID regex (`tests/contract/test_acceptance_registry.py`) already admits `REC`. No live
claim is added: the move's live proofs are Session 18's (D2246) and the sweep's.

---

## 4. Irreversible operations

| Operation | Where | Guard |
|---|---|---|
| The store's `ENCRYPTION_KEY` / `AUTH_SECRET` generated | Sheet I1 | Copied by the operator to two places before the stack first starts; a store started with a key nobody kept is torn down (`docker compose down -v`) and made again — nothing depends on it until M2. |
| `ubuntu` locked on both servers | Sheet E1 | Only after `op` logs in in a NEW session and `sudo -v` works. |
| Hetzner's projects stopped | Sheets F-beta / F-alpha / F-control | Reversible until M7 (`systemctl enable --now agentic-postgres-project@<key>` + `backup.sh schedule enable` + DNS back). |
| DNS records moved | Sheets C-beta / C-alpha / C-control | Grey-cloud, no AAAA; the old A value written in the sheet so the way back is one edit. |
| ACME promotion on OVH | Sheet C-beta | Once; never retried in a loop (5 failed validations/hour/hostname). |
| The OVH mirror timer enabled | Sheets B-key | Only after the key's Hetzner `schedule status` reads disabled. |
| Old identities revoked, Cloud emptied, Hetzner cancelled | M7 | After the hold (D2254), each its own sheet. |

---

## 5. Build order, run by run

### Run M1 — the secret store: its files, the host, the backup, the restore rehearsed

**Code (first, so the sheets use committed files):**

1. **ADR 0262** — *The secret store is self-hosted Infisical on its own host*: what runs
   (Infisical backend, PostgreSQL, Redis, Caddy), where (`15.204.66.146`,
   `secrets.agenticpostgresql.com`), who reaches it (D2250), what is backed up and how
   (D2258), where the keys live (D2239), what is NOT used (no licence: no audit log
   retention, no custom roles — the product needs neither), how it is upgraded (a pinned
   digest moved by a reviewed commit, `pg_dump` first), and what its loss means (ADR 0188's
   sentence now applies to a HOST: without the store's backup and key, every project's
   cipher pass is gone). Indexed in `docs/decisions/README.md`.
2. **`infra/secret-store/`**:
   - `compose.yaml`: `backend` (`infisical/infisical:<tag>@sha256:…` — the newest tag that
     is at least two weeks old on the day, its digest read with `docker buildx imagetools
     inspect` in WSL), `ports: ["127.0.0.1:8080:8080"]`, `env_file:
     /etc/secret-store/infisical.env`, `TELEMETRY_ENABLED=false`; `db`
     (`postgres:16.<n>@sha256:…`, volume `pg_data`, no ports); `redis`
     (`redis:7.4.<n>@sha256:…`, volume `redis_data`, no ports); `mem_limit` on each from
     Sheet I1's reading (backend 1,536 MiB, db 768, redis 256 to start — re-read after M2).
   - `Caddyfile`: `secrets.agenticpostgresql.com { reverse_proxy 127.0.0.1:8080 }`, the
     ACME e-mail the operator's; run as `caddy:<tag>@sha256:…` with `network_mode: host`
     (the same compose file, service `edge`).
   - `infisical.env.example`: every variable NAME (`ENCRYPTION_KEY`, `AUTH_SECRET`,
     `DB_CONNECTION_URI`, `REDIS_URL`, `SITE_URL=https://secrets.agenticpostgresql.com`,
     `POSTGRES_*`) with an empty value and a comment saying how it is generated.
   - `backup.sh` (bash, `set -euo pipefail`, shellcheck-clean): `docker compose exec -T db
     pg_dump -U infisical -Fc infisical | age -r "$(cat /etc/secret-store/backup.age.pub)"
     > /var/backups/secret-store/infisical-<utc>.dump.age` (umask 077), keeps 14, uploads
     the new file with `docker run --rm --env-file /etc/secret-store/backup.env
     rclone/rclone:<tag>@sha256:… copyto …`, exits non-zero on any failure; prints the
     object name and size, never a key.
   - `secret-store-backup.service` / `.timer` (daily 05:15 UTC, `Persistent=true`).
3. **`tests/contract/test_secret_store_files.py`** (`pytestmark` first, D1240): every
   `image:` carries `@sha256:`; the only `ports` entry is `127.0.0.1:8080:8080`; `edge` is
   `network_mode: host`; no value-looking literal in any file (the env example's values
   empty); `backup.sh` pipes `pg_dump` into `age -r` before any redirection or upload and
   runs `rclone` only on the `.age` file. **Battery**: three mutations (a tag without a
   digest; `0.0.0.0:8080`; `pg_dump` redirected to a file before `age`), each FAILED, a
   control PASSED.
4. **`docs/secret-store.md`** (operator page: install, the console, the backup, the restore,
   upgrade, loss) indexed in `docs/README.md`; the targeted list: the new module,
   `test_documentation_index`, `test_session12_documented_path`, `test_acceptance_registry`
   (no registry change yet — M3 owns it; this run's module is in the D1242 sweep-selector
   guard's targeted list), `test_suite_shape`.
5. `ruff format && ruff check` → targeted → commit → push → **CI by full SHA**.

**Sittings (the store host; the operator runs every `sudo`):** Sheets **E1** (both servers:
the operator's key, `op`, `ubuntu` locked, the readings), **D1** (the store's A record),
**I1** (Docker, ufw, `age`, the env file, the stack up), **I2** (the console: the
administrator, the organisation, the control-plane machine identity), **I3** (the backup's
bucket, key and first run), **I4** (the restore rehearsal).

**Measured and written in the Done:** both servers' OS, memory, vCPU, disk, interface and
IPv6 (E1); the store's resident memory per container after a quiet hour (`docker stats
--no-stream`); the certificate's issuer and expiry (`openssl s_client` from the main host);
the external port reading (D2250); the first backup's size and seconds; the restore
rehearsal's seconds and its read-back verdict.

**Done (the code half, 2026-10-09).** ADR 0262 written and indexed; `infra/secret-store/`
(compose, Caddyfile, three env examples, `backup.sh`, the service and timer);
`docs/secret-store.md` indexed; both gates' shellcheck lines reach
`infra/secret-store/*.sh`; `tests/contract/test_secret_store_files.py` (10 tests, its
registry entry is M3's). **Rig** (the committed compose on the workstation, throwaway
keys): `/api/status` 200 after 130 s, backend 766 MiB, database 133, Redis 5; `caddy
validate` ok; `pg_dump | age` 4.3 MB with the `age-encryption.org/v1` header, decrypted and
restored into a second database: 764 tables each. **Targeted** (9 modules): 1,216 passed, 2
skipped (the module's own). **Battery 6/6 killed**, each control PASSED, the tree identical
after: M1 a tag without its digest, M2 `0.0.0.0:8080`, M3 the dump written unencrypted, M4
the edge off the host network, M5 the newest gate not linting the store, M6 the database
reading the backend's env file. Rows **D2263–D2266**. CI: *(recorded in the sheets' Done)*.
**The sittings' Done** *(the executor writes it after Sheets E1, D1, I1–I4)*.

### Run M2 — the main host, provisioned at 1.15.0; the store measured by the product

1. **Transport** (D504): `git bundle create /tmp/apg-<sha12>.bundle --all` in WSL, `scp` to
   `op@15.204.231.45:/tmp/`, `git clone -b main /tmp/apg-<sha12>.bundle ~/agentic-postgres`,
   `git checkout --detach c3eec1d`, `git rev-parse HEAD` == `c3eec1d…`, `git status --short`
   empty; `uv` installed under `~op/.local/bin` (`docs/host-baseline.md:95-111`), `uv sync`.
2. **`host.yaml`** written by `~/s38/mig/ovh-hostyaml.py` from **kit-2026-10-06-s37's
   `host.yaml`** (schema 3; M4's kit does not exist yet, and M5 re-reads this file against
   it) with: `host.id
   apg-ovh-01`; `expected_public_ipv4 15.204.231.45`; `public_interface` as E1 read it;
   the `ssh` block (port 22, `operator_user op`); `capacity` per D2252; **the `infisical`
   block naming the self-hosted store** (`api_url https://secrets.agenticpostgresql.com`,
   the new organisation id and slug from Sheet I2, `environment_slug dev`, `runtime_folder
   /runtime`). The diff against the kit's file is printed and read; the file is 0600 in the
   checkout.
3. **Sheet H0** — `provision-host.sh --check`, the three `--apply` passes with their armed
   rollbacks, `apg-agent` by hand (`infra/host/apg-agent.sudoers`, `bin/apg-diag.sh` →
   `/usr/local/bin/apg-diag`), `edge.sh up` on staging, `status`.
4. **Sheet G1 — the rig** (D2257): a throwaway manifest `/home/op/rig-dev.yaml` from
   `project.example.yaml` (key `rig-dev`), `bootstrap-providers --plan` (contacts nothing,
   D334) then `--apply` with the new control-plane credential, the operator-supplied
   values left absent; `materialize-secrets` — **expected exit naming the first absent
   operator-supplied value** (a 404 read through the product's own reader, which is itself
   the read measurement); a one-line read of a GENERATED value as the runtime identity by
   `~/s38/mig/rig-read.py` (`PYTHONPATH=src`, `InfisicalClient`, prints the name and
   `sha256` length only); `--destroy`; the rig's state, credential files and manifest
   removed; the `rig-dev` Infisical project deleted at the console. Each of the bootstrap's
   ten calls is read in its output and any divergence from the Cloud's behaviour becomes a
   row.
5. **Readings for M5** (agent, `apg-diag` and `op` reads): `docker info` (storage driver,
   cgroup v2), `free -m`, `df`, the edge's two containers' memory; nothing deployed.

**Done.** *(the executor writes it)*

### Run M3 — `--rehome` and the carried ages (code)

1. **ADR 0263** — *A project's provider project moves between stores by value*: the mode,
   its refusals, its order (read all → create → write all → mint → read back as the new
   identity → only then the state), the kept files, the carried ages (D2242), why not
   `--apply` nor `--adopt` nor a console copy, and that the source is never modified.
2. **`bin/bootstrap-providers.py`**: modes `rehome-check` and `rehome` beside
   `plan|apply|destroy|adopt` (`:1224`), wrapper flags `--rehome-check` / `--rehome` in
   `bin/bootstrap-providers.sh` (exit table `:22-25` extended), a new
   `--source-credential-file F` (the OLD store's control-plane credential, two lines, the
   same parser `:251-268`), required by both modes beside `--operator-credential-file`
   (the NEW store's).
   - **Inputs**: the recorded state at `state_path(key)` (refused if absent — exit 3); the
     host's `infisical` block (refused if its provider-relevant fields EQUAL the recorded
     ones — exit 7, *"nothing to move"*); the contract's secret set for the project, the
     SAME selection `--apply` seeds plus the operator-supplied entries, facilities applied.
   - **`rehome-check`**: logs into the source (base URL = the recorded `api_url`) and reads
     every value through `InfisicalClient` (D976 retry and ADR 0255's 429 budget apply);
     logs into the destination; checks no project with the key's slug exists there (read
     by the call `--apply` would make, never by listing, D1013); prints per name `present
     <sha256-prefix-8>`, `absent (optional)` or `ABSENT (required)`; exit 0 when every
     required value is present, 7 otherwise. Writes nothing anywhere.
   - **`rehome`**: the same reads, refused before any write on any `ABSENT (required)`;
     then the destination writes in `--apply`'s order and calls (`:800-1014`) with the
     READ values in place of generated ones (a `400/409 already present` → read back and
     compared, a difference → exit 6); the identity `{key}-runtime`, Universal Auth, one
     client secret, the `viewer` membership; credential files written to TEMPORARY paths;
     **every value read back as the new identity and its digest compared in memory**; on
     any mismatch exit 6 with the destination ids printed (D1046's rule), nothing on the
     host changed. On success, atomically: the old state → `bootstrap-state.rehomed-<utc>.json`
     (0600), the old credential files → `*.rehomed-<utc>` (0400), the new ones into place,
     the new state (schema unchanged; provider inputs digest of the NEW block;
     `managed_resources` including `project`), `secret-ages-carried.json`, and a record
     `evidence/rehome-<key>-<utc>.json` (0600: ids, counts, names, the source ages; no
     value). Prints names and counts.
   - **`secret_age`** (`src/agentic_postgres/secret_age.py`): reads the carried file when
     present and reports the OLDER age per name, naming the source (`carried` or
     `provider`); absent file → today's behaviour.
   - **`dr_kit`**: `secret-ages-carried.json` an OPTIONAL artefact (exported and hashed when
     present; `verify` accepts its absence) — `PROJECT_ARTIFACTS` untouched.
3. **`tests/contract/test_provider_rehome.py`** (`pytestmark` first): a stub provider (the
   module's existing HTTP fakes in `test_bootstrap_providers*.py`/`test_disaster_kit.py`
   are the model — grep them first) for two stores; proofs of each refusal, of the write
   order, of the read-back failing on a changed value (exit 6, the host untouched), of the
   kept files and modes, of the state validating against
   `schemas/bootstrap-state.schema.json` **unchanged** (`git diff 1.15.0 --
   schemas/bootstrap-state.schema.json` empty, asserted in the run's Done), of no value in
   stdout, stderr, the record or the carried file; `secret_age`'s older answer and its
   source; the kit with and without the carried file. **Battery** (≥ 6): the read-back
   skipped; the state written before the read-back; a source value printed; the
   `already present` branch not compared; the carried age ignored; the check mode writing a
   folder — each FAILED, each with a control PASSED.
4. Registry and counts (§2); `docs/provider-bootstrap.md` gains § *Moving to another
   store*; `docs/node-loss-runbook.md` unchanged (M7 adds the planned move).
5. Targeted: the two new modules, `test_bootstrap_*`, `test_disaster_kit`,
   `test_secret_age`, `test_secret_origin`, `test_infisical_client`, `test_cli_contract`,
   `test_acceptance_registry`, `test_evidence_claims`, `test_documentation_index`,
   `test_session12_documented_path`, `test_suite_shape`, the D1242 guard; regenerate the
   matrix and the product contract; commit; push; **CI by full SHA**. Then
   `bin/session-38-check.sh --mode offline` and `bin/session-01-check.sh` ONCE each,
   detached — this is a run before a host trip (M4).

**Done.** *(the executor writes it)*

### Run M4 — the store moved, on the old host (Hetzner)

**Before:** M1–M3 Done; CI green on M3's SHA; the probe scripts in `/home/op` on Hetzner
(`s35-r10-probe.py`, `s35-r10-gaps.py`, `s37-probe-start.sh`, `s37-probe-stop.sh` — present
since Session 37).

1. Ship M3's SHA to Hetzner (`git bundle create … c3eec1d..main`, `scp`, `fetch`), **leave
   the checkout at `c3eec1d`** until the sheet says otherwise.
2. **Sheet RH0** — the `infisical` block in both copies of `host.yaml` (the checkout's, and
   `/etc/agentic-postgres/host.yaml` via `install -m 0600`), from a file the agent wrote
   (`/home/op/rh0-host.yaml`, its diff read: ONLY the four `infisical` members change); the
   two credentials placed.
3. **Sheet RH1** — the checkout to M3's SHA; `--rehome-check` × 3 (beta, alpha,
   control-prod). Every line `present`; exit 0 × 3. **Any `ABSENT (required)` or exit ≠ 0
   is §9's stop** — RH0 is reversed (the block back) and nothing else has changed.
4. **Sheet RH2** — `--rehome` × 3, back to back (D2259); each exit 0, its record path
   printed; the credentials shredded; the checkout back to `c3eec1d`, `git rev-parse HEAD`
   read.
5. **Sheet RH3** — `materialize-secrets` × 3 at `c3eec1d`, then `gen-compare.py` × 3 →
   `equal N/N` (D2260); `s37-probe-start.sh` (alpha, beta, control-prod); the same-commit
   redeploys × 3 (`--through-session 37`); probe stopped, windows read.
6. **Sheet RH4** — `control.sh adopt` × 3, `registry` → agrees × 3; `sudo bin/dr-kit.sh
   export --host host.yaml --capabilities capabilities.yaml --output
   /home/op/kit-2026-10-<dd>-rehomed --project project.alpha.yaml --project
   project.beta.yaml --project /home/op/control.yaml`; `bin/dr-kit.sh verify` (as `op`);
   the kit and the three `secret-ages-carried.json` copied to WSL `~/dr-kits/` (0700/0600)
   the same day.
7. Readings: `sudo bin/doctor.sh --project <key> secrets` × 3 — ages read **0 days at
   `c3eec1d`** (D2242: the carried file is read from 1.16.0); recorded, not repaired.

**Rollback (any project, any time before M5 touches it):** its `bootstrap-state.rehomed-*`
and `*.rehomed-*` files moved back over the new ones, the block restored, a materialize —
the Cloud project was never modified.

**Done.** *(the executor writes it)*

### Run M5 — the three projects moved (both hosts; one project at a time)

**Before:** M4 Done; the new kit verified in WSL; OVH's `host.yaml` (M2) re-read against the
new kit's `infisical` block — **byte-equal members or stop** (adoption refuses a
difference). The kit's three manifests placed on OVH: `project.beta.yaml` and
`project.alpha.yaml` in the checkout, `/home/op/control.yaml` outside it (D971);
`capabilities.yaml` from the kit; each diff against the kit read (none).

**Per project, in order beta → alpha → control-prod, each step its own sheet (D1510):**

1. **Sheet F-key (Hetzner) — freeze.** `backup.sh … schedule disable` (all its timers);
   the row counts of every `app` table by `~/s38/mig/rowcounts.sh <key>` (root, `psql -U
   postgres` through the container, counts only); `backup.sh … backup --type incr` → exit
   0; `systemctl disable --now
   agentic-postgres-project@<key>.service` (stop = detach + down; PostgreSQL's shutdown
   archives its completed segments); `backup.sh … mirror` → exit 0 and its record (**on
   beta this is the measurement that `mirror` runs with the project down**; if it refuses,
   §9: decide `--from primary` for the remaining restores and keep the 2026-09-06 record
   for D2246). A write landing between the counts and the stop shows up as a difference
   in P-key — the projects are quiet; a difference is read, not assumed away.
2. **Sheet N-key (OVH) — adopted and restored.** `dr-kit.sh verify`; `bootstrap-providers
   --adopt --state <kit>/projects/<key>/bootstrap-state.json` with the new store's
   credential; `--apply` (every line *already present … not overwritten*; a *create* line
   is §9's stop); the credential shredded; the kit's `secret-ages-carried.json` installed
   at `/etc/agentic-postgres/projects/<key>/` (0600); `materialize-secrets --session 37`;
   `./deploy.sh --render-only`; `restore.sh … --from mirror --latest --plan` then the real
   run (exit 0, its last line: timeline and identity); `evidence/restore-<key>-<id>.json`
   copied op-readable to `/home/op/`.
3. **Sheet P-key (OVH) — deployed.** `admit.sh`; `./deploy.sh --through-session 37`
   (routes may read `unavailable`, D2248); `--render-runtime-only` → the printed
   `database-ports.sh verify` → deploy again; `systemctl enable
   agentic-postgres-project@<key>.service`; the row counts read again — **equal to F-key's
   or §9's stop**; `instance_uuid` == the kit's.
4. **Sheet C-key — the name.** The operator moves the project's A record in Cloudflare
   (grey, no AAAA; the old value `62.238.99.122` written on the sheet); the agent reads it
   from WSL (`dig @1.1.1.1` in the pinned image, D1239's way when WSL has no network);
   **beta only**: one `curl` → staging certificate → `edge.sh promote-acme --to production
   --confirm apg-ovh-01` → one `curl` → production issuer read; alpha and control-prod: one
   `curl` → production issuer. Then the same-commit redeploy and `doctor --project <key>`
   → `ready` on every route.
5. **Sheet B-key (OVH) — backups.** Hetzner's `schedule status` read disabled (already, F);
   `backup.sh … info` (the stanza, the restored cluster's timeline archiving — `check`
   ran in 6c); `schedule enable` → three timers enabled; **on beta, a `backup --type incr`
   by hand** read in `info`, and the next morning's mirror pass read from `journalctl`
   (D973).
6. **After control-prod**: Sheet **A-OVH** — `control.sh adopt` × 3 on OVH, `registry` →
   agrees × 3; the three op copies `/home/op/<key>-outputs.json` installed.

**Measured and written in the Done:** per project — the freeze's seconds, the restore's
seconds (restore + recovery, against 247 s, D2251's Atlantic), the first deploy's seconds,
the cutover's DNS propagation as read, each certificate's issue time, the row counts equal;
alpha's restore record path (D2246).

**Done.** *(the executor writes it)*

### Run M6 — the declarations, a reboot, a verification, the capacity

1. **Sheet K-carry** (D2247): on Hetzner, `tar` of the root-owned files into
   `/home/op/carry-<date>.tar` (0600, `op`-owned, `--numeric-owner`, sha256 printed); the
   agent copies it host to host with **`scp -3`** (streamed through the workstation, never
   written there), and the op-owned files the same way; **on OVH the operator installs each
   at its original path and mode**; the agent
   prints old/new sha256 per file — equal or stop. `kit-2026-09-11` is copied from WSL
   `~/dr-kits/` and compared with Hetzner's by sha256 per file.
2. **Sheet M6-A — re-made on OVH:** `/home/op/s31-third.yaml` regenerated with
   `shared_buffers_mb` sized so its unreclaimable charge exceeds OVH's safe available as
   `doctor capacity` reads it (the agent computes it from `config.unreclaimable_mb`, D767)
   — `admit.sh` exit 12 on it, exit 0 at the default budget (the control); `rehearse.sh
   admission-refused --outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json`.
3. **Sheet R-OVH — the reboot**: `sudo systemctl reboot`; `~/s38/run9/s38-after-reboot.sh`
   (reads `~/s38/host-address`, now `15.204.231.45`) → every project unit and the edge came
   back, each `inactive` before `multi-user.target` (D2140's reading); the store reached
   from boot (materialize ×2 per unit, ADR 0255's budget never spent — read from
   `journalctl`).
4. **Sheet V-OVH**: the Session 37 verification, `-k "session37 or session4_transports or
   session18"` with every declaration D2247 names and **`--replacement-host-outputs
   /home/op/alpha-dev-outputs.json` + `--restore-evidence-file` = alpha's new record** —
   writes nothing (a `-k` run); REC-NODE-001/002 and REC-REPO-003 read here first.
5. **Readings for Run 11**: `doctor capacity` (committed, safe available), `free -m`
   available with the three projects (D2042's floor; D2252), the edge's memory; the store's
   memory after a day.
6. The new kit from OVH (`kit-<date>-ovh`), verified, copied to WSL.

**Done.** *(the executor writes it)*

### Run M7 — the old host retired; Session 38 amended (docs)

**After at least 72 h of OVH unattended (D2254) and M6 Done:**

1. **Sheet X1 (Hetzner)** — `bootstrap-providers --destroy` × 3 with the NEW store's
   credential (revokes the rehome-minted identities; the projects stay); read at the store's
   console: each key has exactly ONE identity, OVH's.
2. **Sheet X2 (consoles)** — the operator deletes the three Cloud projects and four Cloud
   identities and reads the Cloud organisation empty; cancels the Hetzner server.
3. **Documentation** (no CI): `docs/node-loss-runbook.md` § *A planned move* (D2243's same
   bucket after a freeze, D2248's order, D2249's promotion, D2240's two changes);
   `docs/operator-guide.md` §3 step 1 gains the OVH `ubuntu` sentence (D2245);
   **Session 38's plan amended per D2262** — one row per change, Run 11's *Before the day*
   naming this plan's Done, §7 and Sheet S1 per D2246; CLAUDE.md §2 rewritten (scratchpad
   copy first); memory updated. Commit, push, no CI read.

**Done.** *(the executor writes it)*

---

## 7. Evidence

No session evidence file is written by this plan. Its evidence is: CI on M1's and M3's
commits; M3's offline gate; the records `evidence/rehome-<key>-*.json` (Hetzner),
`evidence/restore-<key>-*.json` (OVH) and M6's `-k` reading (which writes nothing). The
claims it moves are measured by **Session 38's sweep** (Run 12): `provider_rehome` and
`secret_store_files` offline; `replacement_host_restore` live, newly declared (D2246).

## 8. Security invariants this plan touches

- **No secret value in source, a record, a log, stdout, a kit, the workstation or this
  conversation.** The rehome reads and writes in memory and prints names; the carry tar
  holds values (the rotation trio's previous values, two administrator passwords), so it
  goes host to host by `scp -3` (never written on the workstation), stays `0600`, and is
  `shred`ded from Hetzner's and OVH's `/home/op` the moment the install sheet's sha256
  lines match — the deletion read with `ls`.
- **The store answers only the hosts that read it** (D2250), and its console is reached
  through SSH.
- **The store's keys and the backup's `age` identity live with the operator only** (D2239).
- **Never a GitHub credential on any of the three hosts**; transport by bundle (D504).
- **`op` never in the docker group** on OVH (D1375); `ubuntu` locked (D2245).
- **Grey-cloud only, no AAAA**; one ACME attempt per hostname.
- **No public Postgres endpoint** on OVH (ADR 0042/0044) — the edge's DOCKER-USER rules
  are re-applied by `provision-host.sh`, read by M6's external reading.
- **Every `sudo` is the operator's**, at a TTY, one sheet per outcome (D1510).

## 9. Stop conditions

Stop, write the row, and wait for the operator when:

1. E1 reads an OS other than Ubuntu 24.04 or 26.04, or not x86_64, on the main host.
2. The store's TLS certificate is not publicly trusted from the main host, or 443 answers
   the workstation (D2250).
3. Sheet I4's restored store does not answer, or a read-back differs.
4. G1: any bootstrap call fails in a way the client does not already handle (D2257) —
   repaired in M3 before the rehome, never worked around at a console.
5. `--rehome-check` exits ≠ 0, or names any `ABSENT (required)` (D2256).
6. `gen-compare.py` reads any difference (D2260).
7. `--adopt` refuses, or `--apply` would CREATE anything on OVH.
8. `restore.sh` exits 5 (*no backup set*: the cipher pass moved wrong — the most important
   stop in this plan) or the instance does not promote.
9. Row counts after the deploy differ from the freeze's.
10. Beta's 6c `stanza-create` or `check` fails on the shared bucket (D2243).
11. A certificate attempt fails once.
12. After the reboot, any unit or the edge does not return, or a materialize fails.

## 10. Open items this plan carries and creates

- **The store is one host** (ADR 0262): its backup and key are the recovery, a second
  instance is not built. Its restore was rehearsed once (M1).
- **The store's backup key is the operator's to keep**; nothing reads whether it still can.
- **The rehome's state on the old host is history** (`*.rehomed-*`), kept until M7.
- **Every restore crosses the Atlantic** (D2251); Session 39 decides whether a US mirror is
  worth a bucket.
- **The node-loss order for the control project** (control first, D2253) is still Session
  42's.
- **Ages read 0 days on any host below 1.16.0** after a rehome (D2242).
- Carried from Session 38 §10, unchanged: D2178 (no host-wide deploy lock), D2181 (a
  slot's providers outlive it — in the self-hosted store now), D2182, `process-max` 1.

---

## Appendix — the sheets

Every sheet: a human at a TTY on the named host, `sudo -v` first, each line run as written,
the output read before the next sheet is issued. Paths in `<…>` are the agent's to fill
from the previous sheet's reading before the sheet is handed over.

### Sheet E1 — `op`, `ubuntu` locked, password login off (M1; both servers)

**The key half is done** (D2264): `ubuntu@` on both servers takes WSL
`~/.ssh/agentic_postgres_ed25519`, and both host keys are in WSL `~/.ssh/known_hosts`.

**E1a — on EACH server, as `ubuntu`** (`ssh -i ~/.ssh/agentic_postgres_ed25519 ubuntu@<ip>`):

```bash
sudo useradd -m -s /bin/bash op
sudo install -d -m 0700 -o op -g op /home/op/.ssh
sudo install -m 0600 -o op -g op /home/ubuntu/.ssh/authorized_keys /home/op/.ssh/authorized_keys
echo 'op ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/90-op >/dev/null
sudo chmod 0440 /etc/sudoers.d/90-op && sudo visudo -c
```

The agent then opens a NEW session as `op` on each (`ssh … op@<ip> 'sudo -n true && echo ok'`)
and reads `ok`. **E1b is handed over only after both read `ok`.**

**E1b — the store server only (15.204.66.146), as `op`:** the product's SSH hardening
(D2263). The agent first copies `infra/host/00-agentic-postgres-ssh.conf` to
`/home/op/00-agentic-postgres-ssh.conf`; then:

```bash
sed 's/__SSH_PORT__/22/' /home/op/00-agentic-postgres-ssh.conf | sudo install -m 0644 /dev/stdin /etc/ssh/sshd_config.d/00-agentic-postgres-ssh.conf
sudo sshd -t && sudo systemctl reload ssh
```

**Keep this session open**; from the workstation a NEW `ssh … op@15.204.66.146 true` must
succeed. (On the main server the same file arrives with `provision-host.sh`'s pass 2, behind
its rollback timer, in Sheet H0.)

**E1c — on EACH server, as `op`, only after E1b's new session worked:**

```bash
sudo truncate -s 0 /home/ubuntu/.ssh/authorized_keys
sudo usermod -L ubuntu
sudo rm /etc/sudoers.d/90-cloud-init-users && sudo visudo -c
sudo -l -U ubuntu
```

`sudo -l -U ubuntu` must say *not allowed to run sudo*. The agent reads after: `sshd -T`
(store: `passwordauthentication no`, `permitrootlogin no`), `/etc/sudoers.d/` (`90-op`,
`README`), and that `ubuntu@` is refused.

### Sheet D1 — the store's name (M1; Cloudflare console)

`A secrets.agenticpostgresql.com → 15.204.66.146`, **DNS only (grey)**, no AAAA, TTL auto.
The agent reads it: `dig +short A secrets.agenticpostgresql.com @1.1.1.1` → `15.204.66.146`;
AAAA → empty.

### Sheet I1 — Docker, the firewall, `age`, the keys, the stack (M1; store host)

The agent ships `infra/secret-store/` at M1's SHA to `/home/op/secret-store/` (`git archive`
+ `scp`, sha256 per file printed). **I1a — packages and the firewall** (Docker's lines are
`bin/provision-host.sh:731-770`'s):

```bash
sudo apt-get update -qq && sudo apt-get install -y -qq ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc && sudo chmod a+r /etc/apt/keyrings/docker.asc
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu resolute stable\n' "$(dpkg --print-architecture)" | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update -qq && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin age ufw
sudo ufw default deny incoming && sudo ufw default allow outgoing
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp
sudo ufw allow from 15.204.231.45 to any port 443 proto tcp
sudo ufw allow from 62.238.99.122 to any port 443 proto tcp
sudo ufw --force enable && sudo ufw status numbered
```

**I1b — the keys, at the TTY.** Two files from their examples, then each value generated
on THIS host and typed into the file with an editor; **`ENCRYPTION_KEY` and `AUTH_SECRET`
go into the password manager and the offline copy before I1c**:

```bash
sudo install -d -m 0700 /etc/secret-store /var/backups/secret-store
sudo install -m 0600 /home/op/secret-store/infisical.env.example /etc/secret-store/infisical.env
sudo install -m 0600 /home/op/secret-store/db.env.example /etc/secret-store/db.env
openssl rand -hex 16       # -> ENCRYPTION_KEY
openssl rand -base64 32    # -> AUTH_SECRET
openssl rand -hex 24       # -> db.env's POSTGRES_PASSWORD, and inside DB_CONNECTION_URI:
                           #    postgres://infisical:<that value>@db:5432/infisical
sudo nano /etc/secret-store/infisical.env
sudo nano /etc/secret-store/db.env
sudo grep -c '=$' /etc/secret-store/infisical.env /etc/secret-store/db.env   # both :0 (no empty value left)
```

**I1c — the stack:**

```bash
cd /home/op/secret-store && sudo docker compose -p secret-store up -d && sudo docker compose -p secret-store ps
```

The agent reads, as `op`: `/api/status` on `127.0.0.1:8080` → 200 (about two minutes on
first start, D2265's rig: 130 s); `docker stats --no-stream`; from WSL `https://secrets.agenticpostgresql.com`
must time out or be refused on 443 while port 80 answers (D2250); from the main host (after
H0) `curl https://secrets.agenticpostgresql.com/api/status` → 200 with a Let's Encrypt
issuer.

### Sheet I2 — the console: administrator, organisation, the control-plane identity (M1)

From the workstation: `ssh -i ~/.ssh/agentic_postgres_ed25519 -L 8443:127.0.0.1:443
op@15.204.66.146` and a hosts-file line `127.0.0.1 secrets.agenticpostgresql.com` on Windows
(removed at the end of the sheet), then `https://secrets.agenticpostgresql.com:8443`. (If the
console refuses that origin, the alternative of D2250 instead: a temporary `ufw allow from
<your address> to any port 443`, deleted with `ufw delete` on this sheet.)

1. Sign up: the first account is the instance administrator — the operator's e-mail, a
   password from the password manager.
2. An organisation (name `agentic-postgres`); read its **id** and **slug** from Organization
   Settings — the agent needs both (not secret).
3. **Access Control → Identities → Create identity** `control-plane`, organisation role
   **Admin**; Universal Auth attached (access token TTL 900, max 3600, trusted IPs
   `0.0.0.0/0` — the firewall is the boundary); **create one client secret**; the client
   id and secret written to the password manager — **never pasted into the conversation**.
4. No project is created by hand.

### Sheet I3 — the backup: bucket, key, `age`, first run (M1)

1. At Backblaze: bucket `apg-secret-store-backup` (private, lifecycle: keep 30 days of
   versions), an application key restricted to it (read+write), written into
   `/etc/secret-store/backup.env` (0600, the `RCLONE_CONFIG_B2_*` names the example lists)
   **at the TTY**.
2. On the WORKSTATION, not the store host: `age-keygen -o <password-manager-held file>`;
   its PUBLIC line → `/etc/secret-store/backup.age.pub` (0644, not secret).
3. ```bash
   sudo install -m 0644 /home/op/secret-store/secret-store-backup.service /home/op/secret-store/secret-store-backup.timer /etc/systemd/system/
   sudo install -m 0755 /home/op/secret-store/backup.sh /usr/local/sbin/secret-store-backup
   sudo systemctl daemon-reload && sudo systemctl start secret-store-backup.service
   sudo systemctl status --no-pager secret-store-backup.service; sudo ls -l /var/backups/secret-store/
   sudo systemctl enable --now secret-store-backup.timer
   ```

### Sheet I4 — the restore, rehearsed (M1; store host + workstation)

The agent prepares `/home/op/secret-store-restore/` (the same compose under project name
`secret-store-drill`, backend on `127.0.0.1:18080`, no edge). The operator: downloads the
newest `.age` object at the B2 console, decrypts it on the workstation with the age
identity (`age -d -i <identity> -o drill.dump <object>`), `scp`s `drill.dump` to the store
host's `/home/op/` and:

```bash
cd /home/op/secret-store-restore && sudo docker compose -p secret-store-drill up -d db
sudo docker compose -p secret-store-drill exec -T db pg_restore -U infisical -d infisical --clean --if-exists < /home/op/drill.dump
sudo docker compose -p secret-store-drill up -d backend redis
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18080/api/status
```

The read-back (the product's client speaks `https` only, so the drill is read two other
ways): `sudo docker compose -p secret-store-drill exec -T db psql -U infisical -d infisical
-Atc "select count(*) from identities"` equals the same query on the live store, and the
operator, through `ssh -L 18080:127.0.0.1:18080 op@15.204.66.146`, logs into the drill's
console and reads the organisation and the `control-plane` identity. Then `sudo docker
compose -p secret-store-drill down -v`, `shred -u /home/op/drill.dump` here and on the
workstation. **Before M4 the drill is run once more** (Sheet I4 again, after G1), and
then it also counts the secrets of one project — the organisation is empty on M1's day.

### Sheet H0 — the main host's baseline and edge (M2; OVH main)

As `docs/operator-guide.md:139-172` (`provision-host.sh --check`, `--apply` × 3 with the
rollback timers it prints, a new session after each), then `apg-agent`:

```bash
sudo useradd -m -s /bin/bash apg-agent
sudo install -d -m 0700 -o apg-agent -g apg-agent /home/apg-agent/.ssh
# the CONTENT of WSL ~/.ssh/apg_agent_ed25519.pub into /home/apg-agent/.ssh/authorized_keys (0600, apg-agent)
sudo install -m 0755 bin/apg-diag.sh /usr/local/bin/apg-diag
sudo install -m 0440 infra/host/apg-agent.sudoers /etc/sudoers.d/apg-agent && sudo visudo -c
sudo bin/edge.sh --host host.yaml up && sudo bin/edge.sh --host host.yaml status
```

### Sheet G1 — the rig (M2; OVH main)

```bash
sudo install -m 0600 /dev/stdin /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential   # paste the two lines at the TTY, then Ctrl-D
bin/bootstrap-providers.sh --host host.yaml --project /home/op/rig-dev.yaml --plan
sudo bin/bootstrap-providers.sh --host host.yaml --project /home/op/rig-dev.yaml --apply --operator-credential-file /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo bin/materialize-secrets.sh --project /home/op/rig-dev.yaml --requirements secrets.required.yaml --session 37
sudo PYTHONPATH=src python3 /home/op/rig-read.py rig-dev
sudo bin/bootstrap-providers.sh --host host.yaml --project /home/op/rig-dev.yaml --destroy --confirm rig-dev --operator-credential-file /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo shred -u /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
```

(The agent reads `--destroy`'s exact flags from `bootstrap-providers.sh --help` before the
sheet is handed over.) At the console: delete the `rig-dev` project. The agent removes
`/home/op/rig-dev.yaml`; the operator removes `/etc/agentic-postgres/projects/rig-dev/`
and `/etc/agentic-postgres/credentials/rig-dev/` after reading them.

### Sheets RH0–RH4 — the store moved (M4; Hetzner)

**RH0:**
```bash
cd ~op/agentic-postgres
sudo install -m 0600 -o op -g op /home/op/rh0-host.yaml host.yaml
sudo install -m 0600 /home/op/rh0-host.yaml /etc/agentic-postgres/host.yaml
sudo install -m 0600 /dev/stdin /root/.config/agentic-postgres/bootstrap/infisical-cloud-credential            # the CLOUD control-plane client id + secret
sudo install -m 0600 /dev/stdin /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential   # the NEW store's
```
**RH1** (the checkout moved by the agent, `git checkout --detach <M3 SHA>`):
```bash
sudo bin/bootstrap-providers.sh --host host.yaml --project project.beta.yaml  --rehome-check --source-credential-file /root/.config/agentic-postgres/bootstrap/infisical-cloud-credential --operator-credential-file /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo bin/bootstrap-providers.sh --host host.yaml --project project.alpha.yaml --rehome-check  …(the same two flags)
sudo bin/bootstrap-providers.sh --host host.yaml --project /home/op/control.yaml --rehome-check  …(the same two flags)
```
**RH2:** the same three with `--rehome`; then
`sudo shred -u /root/.config/agentic-postgres/bootstrap/infisical-cloud-credential /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential`;
the agent returns the checkout to `c3eec1d`.
**RH3:** `sudo bin/materialize-secrets.sh --project <m> --requirements secrets.required.yaml --session 37` × 3; `sudo python3 /home/op/gen-compare.py <key>` × 3; the probe started; `sudo ./deploy.sh --host host.yaml --project <m> --capabilities capabilities.yaml --through-session 37` × 3 (unredirected); the probe stopped.
**RH4:** `sudo bin/control.sh adopt --project <key> --organization 10234b92-b2d7-4573-bebb-f012ce5c8f02 --confirm control-prod` × 3; `sudo bin/control.sh registry`; the kit export as Run M4 step 6.

### Sheets F / N / P / C / B — one project moved (M5; beta, then alpha, then control-prod)

Exact lines are written by the agent for each key from the kit's paths before the sheet is
handed over; their shapes are Run M5's steps 1–5 and `docs/node-loss-runbook.md` §2–§4.
**Each is handed over only after the previous one's output has been read.**

### Sheets K-carry, M6-A, R-OVH, V-OVH (M6) and X1, X2 (M7)

As their runs describe; the agent writes each with the paths D2247 names.
