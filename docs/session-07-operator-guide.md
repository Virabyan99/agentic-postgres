# Session 7 operator guide

**Status: incomplete, and deliberately so.** Session 7 is under construction.
This document exists from Run 2 because two of its steps happen at Cloudflare,
outside this repository, and produce a value that is **shown exactly once** — so
the instructions have to be written before they are needed rather than recalled
afterwards. Session 6's guide was missing its provider step and the deploy
stopped on it (D284); this one starts with that step.

**Do not deploy anything from this guide yet.** The host sequence is Run 10's and
is not written. What is here is the part an operator can do early, safely, and
only once.

---

## 0. What Session 7 adds, and what it needs from you

One ownership-aware object workflow on Cloudflare R2: upload intent, a
server-generated key, a short-lived presigned PUT, completion verified against
the provider, an authorized presigned download, a tombstone, and idempotent
cleanup.

Three things it needs that no command here can produce:

| What | Where it comes from | Shown once? |
|---|---|---|
| An R2 bucket | Cloudflare, created by you or by the bootstrap | no |
| `r2_access_key_id` | Cloudflare API token's `id` | no |
| `r2_secret_access_key` | SHA-256 of the API token's value | **YES** |

The third is the reason this page exists. Cloudflare shows the Secret Access Key
on the token-creation screen and never again. There is no recovery: a lost value
means issuing a new token and revoking the old one.

**No command in this repository sets a value at the provider** (D249).
`bin/bootstrap-providers.sh --apply` creates what is *missing and generatable*
and deliberately leaves everything else alone — so an operator-supplied value is
pasted into Infisical by hand, exactly as `auth_service_password` was in
Session 6. `--apply` now says so out loud rather than silently skipping:

```
2 secret(s) are operator-supplied and are NOT created by --apply:
  r2_access_key_id             /storage/APG_R2_ACCESS_KEY_ID
  r2_secret_access_key         /storage/APG_R2_SECRET_ACCESS_KEY
  Each is issued by a third party and shown once. Paste the value into the
  provider by hand -- no command here sets a value at the provider (D249).
  Steps: docs/session-07-operator-guide.md
```

That list prints on **every** `--plan` and `--apply` from session 7 onward, done
or not. It is a standing statement about the contract, not a pending change: this
command contacts nothing, so it cannot know whether you have done it yet. The
thing that finds out is materialization, which asks for the exact key and fails
with a 404 naming it.

---

## 1. Before you touch Cloudflare — read this once

**The account is the collision domain.** An R2 bucket name is unique per account
*and jurisdiction*. A bucket that already carries the expected name is **not**
proof that it is ours: somebody else may have created it, and adopting it would
mean managing — and eventually deleting — their data. This is §8.2's rule, the
same one that governs Infisical projects.

**Nothing here deletes a bucket as a rollback.** If continuity cannot be proved,
the tooling stops and asks you to look. That is the intended behaviour.

**Do not paste the secret into a terminal.** Session 6 put an administrator
password into a transcript by following an instruction that echoed it. The value
goes from Cloudflare's screen into Infisical's field. It does not go into a
shell, a log, a note, or a chat message — and it never goes into this repository,
which is what `secrets.required.yaml` means by holding identifiers only.

---

## 2. Create the bucket

One per project. The names are derived, not chosen: `naming.storage_bucket_name`
resolves them from the project key unless the manifest overrides `storage.bucket`.
Read the value rather than typing one:

```bash
wsl bash -lc "cd ~/projects/agentic-postgres && . .venv/bin/activate && python3 - <<'PY'
from agentic_postgres import naming
for key in ('alpha-dev', 'beta-dev'):
    print(f'{key}: bucket={naming.storage_bucket_name(key)} prefix={naming.storage_object_prefix(key)}')
PY"
```

In the Cloudflare dashboard, **R2 object storage → Create bucket**, once per
project key printed above. Leave the jurisdiction at default unless you have a
data-residency reason; if you choose one, **write it down** — a jurisdictional
bucket is reachable only through its own endpoint
(`https://<ACCOUNT_ID>.<JURISDICTION>.r2.cloudflarestorage.com`), and most S3
clients hold one endpoint per client.

Note your **account ID** while you are there (Cloudflare dashboard → account
home). The S3 endpoint is `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.

### 2.1 Where the account ID goes — do this before you leave the dashboard

**D377.** Until Run 10 this page told you to note the account ID and never said
what consumes it. It goes in **each project's manifest**, which is an
operator-owned gitignored file that exists only on the host:

```yaml
# ~op/agentic-postgres/project.alpha.yaml  (and project.beta.yaml)
storage:
  enabled: true
  account_id: <32 lowercase hex characters>
```

`storage.account_id` is **required when storage is enabled** and forbidden when
it is not (ADR 0106). It is an *identifier*, not a credential — it appears in the
hostname of every request — which is why it belongs here and not in Infisical.
`bucket` and `prefix` are derived from the project key and should be left out
unless you are deliberately overriding them (ADR 0105).

Leaving it unset is not silent: the deploy refuses with

```
storage is enabled, so storage.account_id is required: the S3 endpoint is
derived from it
```

That is `config.py` working as designed. But you meet it at **§5.4 step 5** —
several irreversible operations after the dashboard tab you needed is closed.
Set it now.

---

## 3. Issue the API token — the step that cannot be repeated

**R2 object storage → Account details → API Tokens → Manage → Create Account API
token.**

- **Permission: Object Read & Write.** Not Admin. The runtime presigns and
  reads objects; it has no business creating or deleting buckets.
- **Scope it to the buckets you created above**, not to all buckets in the
  account.
- Create it as an **Account** API token rather than a User token — a User token
  inherits your personal permissions and dies with your account membership.

On the screen that follows you get **Access Key ID** and **Secret Access Key**.

> **The Secret Access Key is shown here and nowhere else, ever.** Do not close
> this tab until step 4 is finished and you have confirmed both values are saved
> in Infisical.

For reference, so a mistyped value is recognisable rather than mysterious: the
Access Key ID is the token's `id`, and the Secret Access Key is the SHA-256 of
the token's value — a **64-character lowercase hex string**. It looks exactly
like a value this repository's own generator would produce, which is precisely
why the contract marks it `origin: operator_supplied` and why `--apply` refuses
to invent one (ADR 0103). A generated stand-in would be perfectly well-formed and
would authenticate to nothing.

---

## 4. Put both values into Infisical

Same shape as Session 6's `auth_service_password`. `--apply` needs the
control-plane credential, and **it will not be on the host**:
`docs/provider-bootstrap.md` shreds it after every bootstrap on purpose, so every
new session re-issues one.

In Infisical, in **each project's** environment, create two secrets under the
`/storage` folder:

| Key | Value |
|---|---|
| `APG_R2_ACCESS_KEY_ID` | the Access Key ID from step 3 |
| `APG_R2_SECRET_ACCESS_KEY` | the Secret Access Key from step 3 |

**You must create the `/storage` folder yourself, first (D379).** This page used
to say `--apply` creates it while adding `APG_STORAGE_SERVICE_PASSWORD`. It does
not: that secret's `provider_path` is **`/database`**, alongside every other role
password. `/storage` is the only folder in the whole contract holding **no
generated secret** — both of its entries are `operator_supplied` — so no command
here can ever create it, and running `--apply` first changes nothing about
whether it exists.

Infisical answers **404 on a write to a path that does not exist**, which reads
exactly like a wrong endpoint and is not. So: create the folder in the UI, then
paste the two values into it.

**Putting them in `/database` instead does not work and fails late.** The 404
does not arrive when you paste; it arrives at `materialize-secrets`, naming
`APG_R2_ACCESS_KEY_ID` — several steps and one `down` project later.

```bash
CRED=/root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo install -d -m 0700 -o root -g root "$(dirname "$CRED")"
sudo install -m 0600 -o root -g root /dev/null "$CRED"
sudo nano "$CRED"        # TWO lines: client ID, then client secret. Not JSON.

sudo bin/bootstrap-providers.sh --host host.yaml --project project.alpha.yaml --plan
# expect: create secret value storage_service_password
#         and the two operator-supplied secrets named, NOT proposed for creation
```

**Keep `$CRED` until every project has been applied** — beta-dev needs the same
step, and one client secret does both. Then:

```bash
sudo shred -u "$CRED"
sudo find /root/.config/agentic-postgres -name '*.save' -print   # nano's copy
```

**Each project gets its own token.** Two projects sharing one R2 credential would
dissolve the isolation the per-consumer secret layout exists for: the filesystem
would still keep alpha's copy out of beta's container, and both copies would open
the same buckets. Repeat steps 2–4 per project.

---

## 5. What is NOT ready, and must not be attempted yet

**The clusters still run `max_connections` 50, and Session 7 needs 56**
(ADR 0099). Until they are restarted, a redeployed project renders outputs v11
and `connection_limits` **refuses**, with a message naming the restart. That is
intended. **The restart is a restart, not a reload** — `max_connections` is not a
reloadable parameter — and it belongs to Run 10's host sequence, not to this
page.

**There is no storage deployment yet — and as of Run 9 the next deploy will
attempt one.** `compose.yaml` has carried a `storage` service since Run 2, its
endpoints and migrations since Run 6 and its route since Run 7, all held back by
the `session7` profile: `bin/project-runtime.sh` selects `--profile session<n>`
only up to `--through-session`. **Run 9 moved `CURRENT_SESSION` to 7, so that
brake is off.**

What that means in practice: a deploy will now try to start a storage container,
and it **fails closed** without the two R2 secrets rather than starting without
them (`must_refresh_on_start` is true for both halves). So §2, §3 and §4 of this
guide are no longer optional preparation — they are prerequisites for the next
deploy of any project.

**Everything below still describes a deployment that has not happened on any
host.** No storage container has ever started anywhere.

**Do not run the signing-key cutover in the same window as any of this.** It is
unblocked (ADR 0088) and it is a separate maintenance window with its own
recreate step.

---

## 5.1 The route, and the two things about it worth knowing

The surface is published at `https://<domain>/api/app/storage`, under the
application API rather than beside it, and `routes.storage` in the deployed
document reports it.

**It converges in two stages, and the first one is not a failure.** A deploy
whose active secret generation carries no `r2_access_key_id` and
`r2_secret_access_key` records `routes.storage` as **`unavailable`**, prints the
missing names, and **exits 0**. Provision both at the provider, re-materialize,
and re-run the deploy: the second one observes the route and publishes it. This
is the same shape `routes.app` has used since Session 6 for a project awaiting
its first administrator (D230, D326), and it is a status field rather than a
deployment state.

**The CORS policy is an instruction to a browser. It is not an access control.**
`storage.allowed_cors_origins` in the project manifest becomes a Traefik
middleware on the storage route, and measured against the locked Traefik: a
request from an origin that is **not** on the list is forwarded to the service
and answered normally — only the `Access-Control-Allow-Origin` header is
withheld, and it is the browser that then refuses to hand the response to the
page. `curl`, a server-side client, and anything that does not send an `Origin`
header are unaffected in both directions.

So do not read the origin list as a statement about who can reach the storage
API. What refuses a caller is the bearer token and the ownership filter. An
empty list is a valid configuration and permits no browser origin; it does not
permit everything.

---

## 5.2 Cleanup, and the five verbs

`bin/storage-admin.sh` is the operator surface for the storage plane. Five verbs,
and **none of them takes a bucket or an object key**. The bucket comes from the
deployed document; the only keys the command handles are ones the database
already holds, and it hands them to a container rather than printing them — an
object key is the unguessable half of a bearer credential.

```bash
sudo bin/storage-admin.sh --outputs /var/lib/apg/<project>/outputs.json status
sudo bin/storage-admin.sh --outputs … cleanup [--limit 100] [--lease-seconds 300]
sudo bin/storage-admin.sh --outputs … verify-credential
sudo bin/storage-admin.sh --outputs … credential-digest
sudo bin/storage-admin.sh --outputs … confirm-revoked --retired-credential-file <path>
```

**`cleanup` is the only verb that changes anything**, and what it changes is at
Cloudflare: a provider DELETE cannot be undone and the bytes are not recoverable
from here. So it prints `status` first and asks you to type `CLEANUP`, the same
shape `rotate-signing-key.sh` uses before a promotion, and for the same reason —
an operator approving a deletion should be reading what they are deleting. Pass
`--yes` for a scheduled sweep once you have run it by hand at least once.

**`verify-credential` writes nothing.** It is a `HeadObject` on a key that does
not exist, so it is safe against a live project at any time. What it will not do
is tell you *which* of the credential and the bucket is wrong: a bucket-scoped
token cannot tell "absent" from "not yours" — `HeadBucket` on a nonexistent
bucket was measured at **403, not 404** — and a command that guessed would be
inventing a distinction the provider refuses to make.

**What a sweep reports, and what each line means.** They are five different
outcomes and they are deliberately not collapsed into "succeeded / failed":

| line | meaning |
|---|---|
| `expired` | pending intents past their deadline, moved to `tombstoned` this pass |
| `claimed` | tombstones this worker leased |
| `deleted` | provider DELETEs that returned — an absent key returns 204 and counts |
| `finished` | rows marked collected |
| `lease_lost` | deleted, but the lease had gone to another worker. **Not an error** — the object is gone and somebody else holds the row |
| `failed` | the provider refused. The lease is left to expire, which is the retry |
| `abandoned` | claimed but not reached before the lease ran short. If this is every sweep, `--limit` is too high for `--lease-seconds` |

**Deletion is at least once by design.** A worker may delete an object and die
before recording it, and the next sweep deletes the same key again — which is
safe because `DeleteObject` on an absent key was *measured* at 204 in Run 5.
There is no orphan scan and there will not be one: a reconciler that lists the
bucket and deletes what the database does not know about can delete data a human
put there to recover something.

**An object is not collected while anything can still write to its key**
(ADR 0111). A tombstoned upload that never completed keeps its bytes collectable
only once its presigned PUT can no longer be honoured — a tombstone does not
revoke a presigned URL, and nothing in this system can. So `status` may report a
backlog that `cleanup` correctly declines to touch yet. That is the design, not a
stall.

## 5.3 Rotating the R2 credential

Six steps, and two of them are yours alone. The phases follow
`bin/rotate-signing-key.sh`; what is missing here is an acknowledgement step,
because a credential has no verifier fleet that must agree before it is safe to
switch — one container holds it and no issued artefact outlives it.

1. **Issue a new bucket-scoped Object Read & Write token** at Cloudflare, scoped
   to this project's bucket only. By hand: no command here sets a value at a
   provider. Save **both** halves — the secret is shown exactly once.

2. **Write down the pair you are about to replace, now.**

   ```json
   {"access_key_id": "…", "secret_access_key": "…"}
   ```

   Put it in a root-owned file with mode `0600`. **After step 3 it is gone and
   step 6 needs it.** This is the same shape as the `APG_ROTATED_*_FROM_FILE`
   inputs the Session 5 rotation proofs take, and for the same reason: the proof
   is given the value the window *replaced*, so the file is written before the
   rotation rather than after.

3. **Put the new pair into Infisical** at `APG_R2_ACCESS_KEY_ID` and
   `APG_R2_SECRET_ACCESS_KEY`, by hand (D249).

4. **Bring the project down and up.** Not `restart`. Materialization writes a
   **new generation**, and what a container holds comes from the live pointer
   rather than from the deployed document's `secrets.generation_id` (D76, D306).
   D253 is the record of a rotated credential taking a container down because
   `resume` runs `compose up` with no `--force-recreate`.

5. **`credential-digest`, then `verify-credential`, in that order.** The first
   says the container picked up the new generation; the second says the new
   credential reaches the bucket. Both, and in that order — a container still on
   the old generation would pass the second and mean nothing by it. The digest
   is a SHA-256: no verb here prints a credential (D105).

6. **Revoke the old token at Cloudflare**, by hand. Then:

   ```bash
   sudo bin/storage-admin.sh --outputs … confirm-revoked \
       --retired-credential-file /root/apg-retired-r2.json \
       --window-seconds 600
   ```

   It polls, and it reports one of three things:

   * **`revoked`** — the retired credential is refused and the live one is
     accepted. The live probe in the same iteration is the control: without it, a
     retired credential failing because the bucket, the network or the endpoint
     changed would read as a successful revocation.
   * **not observed** — still accepted after the window. **This does not mean the
     revocation failed.** R2 permission changes are eventually consistent, this
     project has never measured how long one takes, and the window is a bound
     chosen rather than measured. Re-run with a longer `--window-seconds`. The
     command will not declare a credential revoked without having watched the
     refusal happen.
   * **control failed** — the *live* credential stopped being accepted during the
     poll, so the run says nothing about the retired one. Check the deployment
     before concluding anything.

   Shred the retired-credential file once the poll has reported `revoked`.

**Bucket administration is not here, and cannot be** (ADR 0110). Creating a
bucket, reading its identity back, and issuing or revoking a token are Cloudflare
REST API operations you perform with a Cloudflare API token that no process in
this repository holds. The runtime's S3 credential cannot do any of them —
measured in Run 5: `CreateBucket` 403, `ListBuckets` 403, `HeadBucket` on another
bucket in the same account 403. Section 4's read-back of account, name,
jurisdiction, creation time and public-access state is a step you perform and
record; it is weaker than an automated check and it is meant to be honest about
that rather than to look like evidence.

## 5.4 The Run 10 host sequence, in order

Everything Session 7 built is written and **none of it has ever executed**.
Session 6's first host trip found nine defects and its first gate returned twenty
failures, nineteen of which were proofs that had never run. Expect this trip to
find things; that is what it is for. Work through it in this order and stop at
the first thing that surprises you.

**0. Re-render the fixtures — ON THE HOST, after transport (D383).** Otherwise
the gate reads stale ones and reports interpolation errors as a defect in
`compose.yaml` (D212):

```bash
./deploy.sh --project project.example.yaml        --capabilities capabilities.example.yaml --render-only
./deploy.sh --project project.second.example.yaml --capabilities capabilities.example.yaml --render-only
```

> **This step used to say "before leaving the workstation", and that could not
> work.** `.generated/*` is gitignored, so the rendered fixtures are not in the
> transport bundle: every machine keeps its own, and the host's were last
> written by whatever release it ran before. Run 10 followed the old wording
> exactly and the host gate still refused at exit 6, naming both fixtures at
> v10 against code that renders v11 — the gate doing its job.
>
> Neither root nor a running project is needed: `--render-only` is the one mode
> that runs in a bare checkout. Run it as the operator user **after step 2**,
> and re-run it any time the outputs schema version moves. Re-rendering on the
> workstation is still worth doing — for the workstation's own offline gate.

**1. The provider — §2, §2.1 and §3 only.** Create the buckets, **write the
account ID into both manifests**, issue the two tokens. Two of these cannot be
undone by re-running a command and the secret is shown exactly once. **Confirm
first that the two Run 5 probe tokens are revoked** — access key ids
`5d4382d1…` and `63ff979a…` went through a chat transcript and only a human can
revoke them in the dashboard.

> **§4 is NOT part of this step — it moved after transport (D378).**
> `bootstrap-providers.sh --apply` reads the repository's
> `secrets.required.yaml`, and the three storage secrets entered that file in
> Run 2. Run against the Session 6 checkout the host currently holds, `--apply`
> creates no `storage_service_password` and names neither operator-supplied
> secret — and exits looking like it worked. **Session 6's guide has the right
> order** (transport, `down`, provider secrets, materialize, deploy); this page
> had inverted it. Keep both token values safe until step 2a.

> **Run 10 status.** The probe tokens were confirmed revoked, and **both buckets
> now exist** — created over the Cloudflare API rather than the dashboard
> (**D376**) and read back the way §4 item 1 requires:
>
> | Bucket | Account | Jurisdiction | Location | Created | Public access |
> |---|---|---|---|---|---|
> | `apg-alpha-dev` | `ddfa208f…c626` | `default` | EEUR | 2026-08-18T15:25:45Z | **disabled**, no custom domain |
> | `apg-beta-dev` | `ddfa208f…c626` | `default` | EEUR | 2026-08-18T15:26:01Z | **disabled**, no custom domain |
>
> Neither name existed in the account beforehand, so ownership is proved by
> construction rather than by name equality (§1). **Do not re-create them.**
> What remains of step 1 is the two tokens, the two manifest edits, and
> Infisical.

**2. Transport.** `git bundle` + `scp`, then on the host:

```bash
git fetch /tmp/apg.bundle main && git checkout -B main FETCH_HEAD
```

Not a fast-forward merge. **Read the `release <sha>` line the deploy prints and
confirm it is the sha you just fetched** — a skipped fetch has already produced
one deploy of the previous commit.

**2a. Now §4 — the provider secrets (D378).** Only with the release on the host
does `secrets.required.yaml` know the three storage secrets. Per project, and
`--plan` before `--apply`:

```bash
sudo bin/bootstrap-providers.sh --host host.yaml \
     --project project.alpha.yaml --plan
```

Expect `create secret value storage_service_password`, and the two
operator-supplied secrets **named but NOT proposed for creation**. If `--plan`
proposes creating `r2_access_key_id`, stop — §6 says what that means. Then
`--apply` with the control-plane credential, and only then paste the two R2
values into Infisical under `/storage`, so the folder exists first.

**3. The cluster restart, and it is a restart.** `max_connections` moves from 50
to 56 (ADR 0099) and is **not** a reloadable parameter. Until the clusters are
restarted a redeployed project renders outputs v11 and `connection_limits`
refuses, with a message naming exactly this.

**4. Migrations.** Three are released and applied nowhere — 0014, 0015 and 0016.
They go on as `migration_user`, never as a superuser: every offline rig applies
them as `psql -U postgres`, and a superuser bypasses the ownership check that
made 0012 and 0013 fail on a real cluster (D285).

**5. Deploy, then bootstrap, then deploy again.** `routes.storage` follows the
same two-stage convergence `routes.app` does, so the first deploy publishes it
`unavailable` and the second makes it `ready`.

**6. The storage surface, by hand, before the gate.** `bin/storage-admin.sh
--outputs … credential-digest` then `verify-credential`, in that order — the
first says the container picked up the generation, the second says the credential
reaches the bucket. A container still on an old generation would pass the second
and mean nothing by it.

**7. The gate, both halves.**

```bash
sudo bin/session-07-check.sh --mode host --host host.yaml \
     --project-a-outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json \
     --project-b-outputs /etc/agentic-postgres/projects/beta-dev/outputs.json \
     --sentinel-file <derived, see §4 of the Session 5 guide> \
     --admin-password-file <path>

bin/session-07-check.sh --mode external --public-ipv4 <addr> \
     --project-a-outputs <fresh copy> --ssh-destination <dest>
```

External mode must run **off-host**: a scan from the host measures its own
routing table. Without `--admin-password-file` the proofs needing an
administrator session skip and their claims report `not_run` — which is the
evidence model working, not a failure.

**8. Merge the two halves.**

```bash
bin/write-session-evidence.py --session 7 \
    --host-input evidence/session-07-host.json \
    --external-input evidence/session-07-external.json \
    --output evidence/session-07.json
```

**What is not part of this trip.** Do not start the signing-key cutover in the
same window (ADR 0088 — it is unblocked, and it is its own window with its own
recreate step), and the Session 5 rotation window is a separate decision that
closes two older claims.

---

## 6. If something goes wrong

**You closed the tab before saving the Secret Access Key.** Issue a new token
with the same permissions and scope, save both values, then revoke the old token
in the Cloudflare dashboard. Do not leave both live.

**`--apply` proposes creating `r2_access_key_id`.** It must never do that. If you
see `create  secret value r2_access_key_id` in a plan, the contract's `origin`
field has been changed or the release is older than Run 2 — stop and check
`secrets.required.yaml` before applying.

**Materialization fails with `HTTP 404` naming `APG_R2_SECRET_ACCESS_KEY`.** The
value is not at the provider yet, or it is in the wrong folder. It belongs at
`/storage`, in the same environment the project's other secrets use. This is the
error working as intended — a required secret's absence must never be tolerated,
unlike `auth_jwt_prepared_key`, which is `required: false` on purpose (D283).

**A bucket exists with the right name and you did not create it.** Stop. Name
equality is not ownership. Confirm the account and creation time before going
further, and if you cannot, use a different bucket name via `storage.bucket` in
the project manifest.
