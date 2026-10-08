# The control plane

Since `1.15.0` (Session 37, ADR 0251-0254) one project on a node can be the
**control plane**: the project that holds people, organisations and a registry
of the node's other projects, and serves them at **`/api/v1`** -- on this
deployment `https://control.agenticpostgresql.com/api/v1`. It is an ordinary
project in every other respect: its own manifest, providers, certificate,
backups, unit and doctor.

**The boundary, in one sentence** (ADR 0246): the control plane holds nothing
that opens a project's data or admin plane. Its service reads no other
project's deployed document, URL or credential -- a scan of its modules holds
it to that -- and the registry is written by root from the deployed documents,
never by the service. A management key is refused by every project's own
routes.

## What makes a project the control plane

A project manifest at **schema 9** with:

```yaml
schema_version: 9
control:
  enabled: true
migrations:
  set: projects/control      # the control plane's tables are this set
```

`project.control.example.yaml` is the committed example; the deployment's
manifest is `/home/op/control.yaml`, outside the checkout (D971). With the
facility on, the project's `auth` container runs `APP_MODE=control` -- the
health routes, `/auth/me` and `/v1`, and **nothing else**: no `/auth/login`
(the login is `POST /v1/sessions`, which enforces the second factor), no
`/admin/*`, no workflow or connector route, no worker. A control router
publishes `{api}/v1`, and the document records `routes.control` and
`control: {enabled: true}` (outputs v20). REST and storage are off in the
example; `mcp` is rendered (it has no switch) and no agent is created there.
**One control project per node is assumed**; `bin/control.sh` refuses two.

## Accounts and invitations

There is no signup (D1951). An account exists because someone accepted an
invitation:

- an **account invitation** is minted by the registry administrator (the
  control project's `bin/auth-admin.sh bootstrap` account, with an enabled
  second factor): `bin/org.sh invite --account --output FILE`;
- a **membership invitation** is minted by an owner or admin of an
  organisation, for a role at or below their own: `bin/org.sh invite --role
  member --output FILE`.

A token is shown once (written 0600 to `--output`, never printed to a pipe)
and stored only as its SHA-256. It lives 72 hours unless `--expires-hours`
(1-168). A used, expired, revoked and unknown token all get the same answer.
**Accepting with `--username` creates the account and logs you in**; without
it, a logged-in person joins the organisation the invitation names.

**Accounts are never deleted or pruned in 1.15.0 or 1.16.0** (D2065). Removing a
membership removes the authority: an account in no organisation reaches
nothing but `/v1/me`.

## Roles

`owner`, `admin`, `member`, `viewer`, per organisation. Every `/v1` route checks
the caller's role in the target organisation against one matrix (ADR 0253). An
admin cannot make an owner; the last owner cannot be removed or demoted. A
foreign organisation's id and a missing one get the same `404`.

## The second factor (TOTP)

RFC 6238, SHA-1, six digits, thirty seconds, one step either side. **An owner
or admin must enrol before anything else** -- until then they reach only
`/v1/me`, `/v1/me/totp*` and `/v1/sessions*`:

```bash
bin/login.sh totp-enroll          # the otpauth:// URI, to a terminal or --output FILE
bin/login.sh totp-confirm         # a current code; every session ends, this one included
bin/login.sh password --endpoint URL --username NAME   # again, with a NEW code
```

**A code is accepted once**: the step `totp-confirm` used is refused by the next
login, so wait for the authenticator to show a new code. **A lost device is the
operator's**: `sudo bin/control.sh totp-reset --username NAME --confirm
control-prod` removes the factor, and the person enrols again at their next
login. Seeds are stored in plaintext, because computing a code needs the key;
encrypting them is `planned` (ADR 0252).

## Management keys

`apg_<16 hex>_<43>`, shown once, stored as its id and SHA-256. **Only a person
mints one** (`bin/org.sh key-create`; a key cannot mint a key, an invitation or
a factor). Its scopes come from `organizations:read`, `members:read`,
`projects:read`, `operations:read` and -- since 1.16.0 -- `projects:write`, and
are always intersected with its owner's CURRENT role: demote the owner and the
key narrows; remove them and it is refused on its next request. A key reaches
the read routes and, with `projects:write`, sleep, wake and resize -- never a
creation, an export or a deletion. Use one with
`bin/login.sh key --endpoint URL --key-file FILE` -- the context records the
file's path, never the key.

## The registry

The control plane's list of projects is written by root, from each project's
deployed document, never typed:

```bash
sudo bin/control.sh adopt --project alpha-dev --organization <org id> --confirm control-prod
sudo bin/control.sh registry        # agrees / differs: <field> / could not determine
```

`registry` exits 0 when every project agrees, 5 on a difference, 6 when
anything could not be determined -- a document it cannot read is never
reported as agreeing (ADR 0195). **Removing a row is a root `psql` DELETE**;
there is no `forget` verb.

## The commands

All five keep their state in `${XDG_CONFIG_HOME:-$HOME/.config}/apg/` -- a
0700 directory of 0600 files; a symlink, another owner's file or a wider mode
is refused, never repaired. A secret enters only from a 0600 file whose mode is
checked, or a terminal prompt, and leaves only to `--output FILE` or a
terminal. https only (plain http for `127.0.0.1` and `localhost`); redirects
are never followed. The access token is never written; each command makes one
refresh exchange. **A login refuses while a session is held** -- end it with
`bin/logout.sh` first.

```
bin/login.sh password --endpoint URL --username NAME [--password-file FILE] [--totp-code-stdin]
bin/login.sh key --endpoint URL --key-file FILE
bin/login.sh accept --endpoint URL --invitation-file FILE --username NAME [--display-name TEXT] [--password-file FILE]
bin/login.sh accept --invitation-file FILE
bin/login.sh totp-enroll [--output FILE]
bin/login.sh totp-confirm [--totp-code-stdin]
bin/logout.sh [--json]
bin/context.sh show [--json]
bin/org.sh list [--json]
bin/org.sh create --name TEXT
bin/org.sh use --organization ID
bin/org.sh members [--organization ID] [--json]
bin/org.sh invite (--account | --role owner|admin|member|viewer) --output FILE [--organization ID] [--expires-hours N]
bin/org.sh set-role --user ID --role owner|admin|member|viewer [--organization ID]
bin/org.sh remove --user ID [--organization ID]
bin/org.sh keys [--organization ID] [--json]
bin/org.sh key-create --name TEXT --scopes LIST --output FILE [--organization ID]
bin/org.sh key-revoke --key-id ID [--organization ID]
bin/project.sh list [--organization ID] [--json]
bin/project.sh use --project-key KEY
bin/project.sh show [--project-key KEY] [--json]
bin/project.sh status [--project-key KEY] [--json]
bin/project.sh create --name NAME --profile small|standard|large --admin-username USER [--organization ID] [--json]
bin/project.sh claim [--project-key KEY] [--password-file FILE]
bin/project.sh sleep [--project-key KEY] [--json]
bin/project.sh wake [--project-key KEY] [--json]
bin/project.sh export [--project-key KEY] --output FILE [--timeout S] [--interval S] [--json]
bin/project.sh delete --project-key KEY --confirm KEY [--json]
bin/compute.sh get [--project-key KEY] [--json]
bin/compute.sh set [--project-key KEY] --profile small|standard|large [--json]
bin/operation.sh show --operation ID [--json]
bin/operation.sh list [--organization ID] [--json]
bin/operation.sh wait --operation ID [--timeout S] [--interval S] [--json]
bin/operation.sh cancel --operation ID [--json]
sudo bin/control.sh adopt --project KEY --organization ORG_ID --confirm CONTROL_KEY
sudo bin/control.sh registry [--json]
sudo bin/control.sh totp-reset --username NAME --confirm CONTROL_KEY
```

Each command's `--help` is the authority. Exit codes: 0 ok; 2 usage; 3 no
context, no credential, an unusable local file, or not https; 5 refused by the
server (for `operation wait`, the operation failed); 6 the server could not be
reached or read; 7 `operation wait` reached its own `--timeout` with the
operation still running -- never read as an outcome.

## Project operations (1.16.0)

Since `1.16.0` (Session 38, ADR 0256-0261) the control plane accepts six
operation types on a **managed project** -- one the control plane created
into a slot the operator prepared, as `docs/managed-projects.md` describes for
the customer. Each route records an operation and answers `202 {operation}`;
a root unit on the host, the **reconciler**, executes it; `GET
/v1/operations/{id}` reads it.

| Route | Operation | Who |
|---|---|---|
| `POST /v1/projects` | `project.create` | member and above, a person's session only |
| `POST /v1/projects/{key}/sleep` | `project.sleep` | member and above; a key with `projects:write` |
| `POST /v1/projects/{key}/wake` | `project.wake` | member and above; a key with `projects:write` |
| `PUT /v1/projects/{key}/compute` | `project.resize` | member and above; a key with `projects:write` |
| `POST /v1/projects/{key}/export` | `project.export` | member and above, a person's session only |
| `DELETE /v1/projects/{key}` | `project.delete` | admin and above, a person's session only |
| `POST /v1/operations/{id}/cancel` | -- | its requester, or an admin or owner, while it is `pending` |

**One operation at a time**: a second write on a project, or a second creation
in an organisation, is `409 conflict` naming the one in flight. **A creation
with no ready slot** -- or a slot reading older than ten minutes -- is `409
capacity_exhausted {reason: no_slot}` before anything is recorded; one the
server has no room for fails `capacity_exhausted {reason: admission}` before
anything is rendered. No code in 1.16.0 produces `plan_limit_reached`.

**The six types are `trial` in the Reality Ledger** (ADR 0261): reachable while
the evidence that would make them `beta` is collected, and saying so to the
customer. A type whose row is not reachable answers `409 not_available` naming
the row -- today the branch, restore and credential types.

**Only the alpha, beta and control projects are the operator's**: the
reconciler acts on declared slots alone, and a write naming an adopted project
fails `invalid_request` with nothing run. A project's `state` (`creating`,
`ready`, `sleeping`, `updating`, `deleting`, `deleted`, ...) is computed from
its operation history; an interrupted or undetermined latest operation reads
`unknown`, never `ready`, and an adopted project reads `ready` as
operator-managed.

**The first administrator is handed over by hash** (ADR 0260): `bin/project.sh
create` keeps a random token 0600 on the creator's disk and sends only its
SHA-256; `claim` presents the token to the new project's own reset route. The
control plane never holds anything that opens the project.

**The export URL is the one exception** (ADR 0259): the requester's first read
of a succeeded export carries `download_url`, valid at most 900 seconds; no
later read, other reader or list carries it. `bin/project.sh export` fetches it
once and never prints it.

## What is not here

- **Branches, restores and credential rotation are not accepted**: each answers
  `409 not_available` naming its Ledger row (ADR 0254).
- No account deletion, no email, no passkeys, no web console, no rate limit on
  `/v1/sessions` or on accepting an invitation (Argon2id's cost is the only
  throttle), no key expiry, no `apg project status` and no `/v1/ledger` --
  each is a later session's, and `docs/reality-ledger.md` says which.
