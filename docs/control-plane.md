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

Every one of them keeps its state in `${XDG_CONFIG_HOME:-$HOME/.config}/apg/` -- a
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
bin/project.sh backups [--project-key KEY] [--json]
bin/project.sh idle-sleep [--project-key KEY] --minutes 15|30|60|never [--json]
bin/compute.sh get [--project-key KEY] [--json]
bin/compute.sh set [--project-key KEY] --profile small|standard|large [--json]
bin/operation.sh show --operation ID [--json]
bin/operation.sh list [--organization ID] [--json]
bin/operation.sh wait --operation ID [--timeout S] [--interval S] [--json]
bin/operation.sh cancel --operation ID [--json]
bin/branch.sh create [--project-key KEY] --branch NAME --password-dir DIR [--at INSTANT] [--expires-in DURATION] [--wait]
bin/branch.sh list|show [--project-key KEY] [--branch NAME] [--json]
bin/branch.sh reset [--project-key KEY] --branch NAME --password-dir DIR [--at INSTANT] [--wait]
bin/branch.sh delete [--project-key KEY] --branch NAME --confirm NAME [--wait]
bin/plan.sh list [--json]
bin/plan.sh show [--organization ID] [--json]
bin/plan.sh notify-me [--organization ID] [--plan premium] [--json]
bin/usage.sh show [--project-key KEY | --organization ID] [--hours N] [--json]
bin/notifications.sh list [--organization ID] [--limit N] [--json]
sudo bin/control.sh adopt --project KEY --organization ORG_ID --confirm CONTROL_KEY
sudo bin/control.sh registry [--json]
sudo bin/control.sh totp-reset --username NAME --confirm CONTROL_KEY
```

Each command's `--help` is the authority. Exit codes: 0 ok; 2 usage; 3 no
context, no credential, an unusable local file, or not https; 5 refused by the
server (for `operation wait`, the operation failed); 6 the server could not be
reached or read; 7 `operation wait` reached its own `--timeout` with the
operation still running -- never read as an outcome. `project backups` exits
6 when the window could not be determined, and `usage show` when a project's
usage could not be (no sample in the window). `bin/usage.sh` is the customer's;
`sudo bin/doctor.sh usage --project KEY` is the operator's reading of the node
and keeps that meaning (D2528).

## Project operations (1.16.0, 1.17.0)

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
| `POST /v1/projects/{key}/credentials` | `credential.rotate` (since 1.17.0) | member and above, a person's session only; a project with public endpoints |
| `GET /v1/projects/{key}/connections` | -- (a read: the doors and the snippets) | viewer and above; a key with `projects:read` |
| `POST /v1/operations/{id}/cancel` | -- | its requester, or an admin or owner, while it is `pending` |
| `GET /v1/projects/{key}/branches[/{branch}]` | -- (a read: each branch's point, timeline, names, expiry) | viewer and above; a key with `projects:read` |
| `POST /v1/projects/{key}/branches` | `branch.create` (Session 40) | member and above, a person's session only |
| `POST /v1/projects/{key}/restores` | `restore.create` (Session 40; a branch at `target_time`) | member and above, a person's session only |
| `POST /v1/projects/{key}/branches/{branch}/reset` | `branch.reset` (Session 40) | member and above, a person's session only |
| `DELETE /v1/projects/{key}/branches/{branch}` | `branch.delete` (Session 40) | admin and above, a person's session only |
| `GET /v1/projects/{key}/backups` | -- (a read: the restore window, ADR 0273) | viewer and above; a key with `projects:read` |

**One operation at a time**: a second write on a project, or a second creation
in an organisation, is `409 conflict` naming the one in flight. **A creation
with no ready slot** -- or a slot reading older than ten minutes -- is `409
capacity_exhausted {reason: no_slot}` before anything is recorded; one the
server has no room for fails `capacity_exhausted {reason: admission}` before
anything is rendered. **The plan is read before the slot** (Session 41, ADR
0274): an organisation already holding its plan's `projects_active` -- Free's
one, a sleeping project included -- is `409 plan_limit_reached` with no row,
under the organisation's own lock so two concurrent creations leave one; only
an organisation within its plan is ever told `capacity_exhausted`. A branch
past the plan's `branches_total` is `409 branch_limit_reached`, the same way.

**All eleven executed types are accepted since Session 41's bump**: the six
managed-project types' rows are `trial` (ADR 0261) a third time, re-earned on a
new slot in a new organisation (D2518); the four branch types' rows are `trial`
with D2501 and D2504 repaired; `credential.rotate`'s `direct_endpoint` is
`beta`. Each `trial` row is being verified on the 1.19.0 trip; a type whose row
is not reachable answers `409 not_available` naming the row.

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

## Plans, usage and notifications (Session 41)

ADR 0274-0276. Four reads, one person's write, and one setting; none records
an operation.

| Route | What | Who |
|---|---|---|
| `GET /v1/plans` | Both plans: each entitlement's value, whether it is enforced, and by which reader; the beta sentence | any account; a key with `organizations:read` |
| `GET /v1/organizations/{organization}/plan` | The organisation's plan, its projects held against `projects_active`, the plans it asked about | viewer and above; a key with `organizations:read` |
| `POST /v1/organizations/{organization}/plan-interest` | *Notify me* (`{"plan": "premium"}`): one row per organisation and plan, `recorded` true once | member and above, a person's session only |
| `GET /v1/organizations/{organization}/usage?hours=N` | Every project's usage document, a deleted one for the part of the window it lived | viewer and above; a key with `projects:read` |
| `GET /v1/projects/{key}/usage?hours=N` | One project's: samples expected and present, each figure's newest reading, the window's maximum and unread count, requests across resets, agent calls, workflow runs, active and sleeping seconds; `could_not_determine` with no sample | viewer and above; a key with `projects:read` |
| `GET /v1/organizations/{organization}/notifications?limit=N` | Newest first: one per finished operation, and the daily 80% notice of a shown limit | viewer and above; a key with `organizations:read` |
| `PUT /v1/projects/{key}/idle-sleep` | `{"minutes": 15 \| 30 \| 60 \| null}`; the answer says the backups stop while it sleeps | member and above; a key with `projects:write` |

`hours` is 1 to 720 (default 24) and `limit` 1 to 200 (default 50); anything
else is `422`. **No route writes a plan, a limit or a usage sample**: the plan
is root's (an organisation is on Free), the limits are the release's
(`app.control_plan_limits`, held equal to `plans.PLANS` by a test), and the
samples are the reconciler's, through a function granted to nobody (D2533).

**Idle sleep is offered only while sleeping is** (D2548): the setting answers
`409 not_available` naming `idle_sleep` while `project.sleep` is not accepted,
and the reconciler asks the control set for an idle sleep only then. With it
on, `app.control_request_idle_sleep` inserts ONE `project.sleep` (`origin`
`idle`, on behalf of the member who set the minutes) only over a window of
samples all present, awake, read and quiet.

## What is not here

- **No branch write reaches a management key** (D2468): each carries the
  branch's own two verifiers, so it is a person's. **One branch per project
  on Free** (`branches_total`, ADR 0274): a second is `409
  branch_limit_reached` before a row (D2430). A branch, a
  missing branch and a foreign project's branch are one `404 not_found`
  (D2451). A branch write answers `409 not_available` naming its row whenever
  that row is not reachable (ADR 0254); since Session 41's bump the four are
  `trial`.
- No account deletion, no email, no passkeys, no web console, no rate limit on
  `/v1/sessions` or on accepting an invitation (Argon2id's cost is the only
  throttle), no key expiry, no `apg project status` and no `/v1/ledger` --
  each is a later session's, and `docs/reality-ledger.md` says which.
