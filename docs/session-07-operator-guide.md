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

The folder does not have to exist first — `bootstrap-providers.sh --apply`
creates it while adding `APG_STORAGE_SERVICE_PASSWORD`, and Infisical answers 404
on a write to a path that does not exist, which reads exactly like a wrong
endpoint and is not.

**Order that avoids the 404:** run `--apply` first so the folder and the
generated credential exist, then paste the two values.

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

**There is no storage deployment yet.** `compose.yaml` carries a `storage`
service from Run 2, but it is on the `session7` profile and `CURRENT_SESSION` is
6, so nothing starts it: `bin/project-runtime.sh` selects `--profile session<n>`
only up to `--through-session`. The service has no route, no endpoints and no
adapter. Run 7 publishes it.

**Do not run the signing-key cutover in the same window as any of this.** It is
unblocked (ADR 0088) and it is a separate maintenance window with its own
recreate step.

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
