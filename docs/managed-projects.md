# Managed projects

Since `1.16.0` (Session 38, ADR 0256-0261) a member of an organisation can
create a project through the management API, and then sleep, wake, resize,
export and delete it, without the operator running a command for any of it.
This page is the customer's: what each step does, what it refuses, and what
it keeps. The routes and the roles are in [the control plane](control-plane.md);
the operator's half -- slots, the reconciler, revocation -- is the
[operator guide](operator-guide.md) §20.

**Every operation here is being verified** (Reality Ledger status `trial`, ADR
0261) since Session 41's bump: offered on the 1.19.0 trip, the project
operations re-earned a third time on a new slot (D2518) and the branch
operations with D2501 and D2504 repaired, each moved to `beta` or back to
`planned` by the session's close. Setting a database credential is `beta`.
[The Reality Ledger](reality-ledger.md) says so for each.

Since Session 41 (ADR 0274-0276) an organisation also has a **plan**, each
project a **usage** record, the organisation **notifications**, and a project
can be set to **sleep when idle**. Plans, usage and notifications are reads;
idle sleep is offered only while sleeping is (`409 not_available` naming
`idle_sleep` otherwise).

## The life of a project

```
bin/login.sh password --endpoint https://control.agenticpostgresql.com/api/v1 --username NAME
bin/project.sh create --name "Shop backend" --profile small --admin-username shop.admin --json
bin/operation.sh wait --operation ID
bin/project.sh claim --project-key KEY --password-file FILE
bin/project.sh sleep --project-key KEY
bin/project.sh wake --project-key KEY
bin/compute.sh set --project-key KEY --profile standard
bin/project.sh export --project-key KEY --output shop.dump
bin/project.sh delete --project-key KEY --confirm KEY
bin/project.sh backups --project-key KEY
bin/branch.sh create --project-key KEY --branch dev --password-dir ~/branches --wait
bin/branch.sh delete --project-key KEY --branch dev --confirm dev
bin/plan.sh show
bin/usage.sh show --project-key KEY
bin/notifications.sh list
bin/project.sh idle-sleep --project-key KEY --minutes 30
```

Each write answers at once with an **operation** -- `pending`, then `running`
with its step, then `succeeded` or `failed` with a closed error code -- and
`bin/operation.sh wait` follows it: exit 0 succeeded, 5 failed (the code and
the reason printed), 7 still running when its own `--timeout` ran out, 6 the
control plane could not be read. **One operation runs on a project at a
time**, and one creation in an organisation; a second is refused `conflict`,
naming the first.

**A project's state** comes from its operations: `creating`, `ready`,
`suspending`, `sleeping`, `starting`, `updating`, `deleting`, `deleted`. When
the latest operation was interrupted or its outcome could not be determined
the state is `unknown` -- never `ready` -- and the operator is the one who
finds out why. `bin/project.sh status` prints it with the project's profile
and region.

## Creating, and claiming the first administrator

A project is created into a **slot** the operator prepared on this server:
its name, its address, its storage and its backups exist before you ask. Your
project's key is the slot's (`slot1-prod`); the name you give is a display
name. **When no slot is ready the creation is refused `capacity_exhausted`
(`no_slot`) before anything is recorded**, and when the server has no room for
the profile you asked for it fails `capacity_exhausted` (`admission`) before
anything is built. **Your plan is read first** (ADR 0274): Free holds one
project per organisation -- a sleeping project holds its place -- so a second
creation in the same organisation is refused `plan_limit_reached`, before the
slot is read and before anything is recorded. An organisation within its plan
is then told `capacity_exhausted` when the server has no slot for it.

**The first administrator is yours alone** (ADR 0260). `create` writes a
random token to `${XDG_CONFIG_HOME:-$HOME/.config}/apg/handoffs/` (0600) before
it sends anything, and sends only the token's SHA-256. When the creation has
succeeded, `claim` presents the token to the NEW project's own address and
sets the administrator's password from a 0600 file or a prompt; the token
file is removed once the project accepted it. The control plane never held the
token, the password, or anything that opens your project. **Keep the handoff
directory until you have claimed**: a creation whose answer did not arrive
leaves its token in place and says where.

## Sleeping and waking

`sleep` stops the project's containers and keeps them and their data; `wake`
starts the same containers. **While a project sleeps, its addresses answer
`404`** -- the edge has no route to it -- and:

- **no new restore point is taken.** Its archiver and its backup timers stop
  with it, so its last restore point is the moment it went to sleep;
- a server restart does not wake it -- its boot unit is disabled while it
  sleeps -- though a restart with a sleeping project has not yet been
  measured;
- it cannot be exported or resized: wake it first.

Waking takes as long as the project's services take to become healthy; the
answer is the operation's, and the project is reachable when it reads
`succeeded`.

## Idle sleep

```
bin/project.sh idle-sleep --project-key KEY --minutes 15|30|60|never
```

Off unless you turn it on (ADR 0276). With it on, the server puts the project
to sleep after that many minutes **idle**: no request answered below `400` and
no connection by the project's own database roles (`customer_app`,
`customer_admin`) for the whole window, read from the usage samples the server
records every five minutes. **A sample missing or not read keeps the project
awake** -- the server never guesses that a project is idle -- and so does a
wake or any other operation inside the window. The sleep is recorded on behalf
of the member who set the minutes, and its notification says it was idle.

**While it sleeps, its backups stop: its last restore point is the moment it
went to sleep.** It wakes only when someone asks (`bin/project.sh wake`); a
connection does not wake it. `never` turns it off. A viewer cannot change the
setting; a management key holding `projects:write` can. While sleeping itself
is not offered (Reality Ledger `planned`), the setting answers `409
not_available` naming `idle_sleep`, and nothing is stored.

## Changing the size

Three profiles: `small`, `standard` and `large` -- memory, connection and
process bounds named once, so every limit the server checks applies to them.
`bin/compute.sh set` **restarts the project**; the answer says the restart has
not yet been measured on this server. **When the server has no room for the
new size the change fails `capacity_exhausted` (`admission`) and nothing
changes** -- the project keeps its profile and keeps running.

## Exporting

`bin/project.sh export --output FILE` asks for an archive of the project's own
schemas, `api`, `app` and -- since `1.17.0` -- `public`, where your
administrator creates -- your tables and your API, never the platform's
private state -- in `pg_dump`'s custom format (`pg_restore` reads it). The
command waits for the operation, downloads the archive **once**, checks its
SHA-256 against the operation's, and writes it 0600 (never over an existing
file). **The download link lives at most 15 minutes and is handed out once**,
to the person who asked, on their first read of the finished operation; no
later read, no other member and no list carries it. A management key cannot
export.

## Deleting

`bin/project.sh delete --project-key KEY --confirm KEY` -- an admin or owner,
signed in as a person -- removes the project's containers, its data, its
credentials and its address on this server. **What deletion keeps**: the
project's backups, in the operator's storage, until the operator removes them
-- this beta removes nothing automatically -- and the slot itself, which is
**never given to another project**: a deleted project's key, address and names
are not reused. A deleted project accepts no further operation.

## Connecting to the database

Since `1.17.0` (ADR 0268-0270) a managed project has two public Postgres
names on port 5432 -- `pool.<domain>` for the application as `customer_app`,
`direct.<domain>` for migrations and administration as `customer_admin` --
TLS verified in full. **Set each password first**: `bin/endpoint.sh
credential --role app|admin --password-file FILE --wait` generates it on
your machine and sends only its verifier; nobody else ever holds it, and a
lost password is replaced by rotating again. `bin/endpoint.sh show` prints
the doors and a snippet per client; `bin/endpoint.sh connect` opens `psql`.
A sleeping project's doors refuse until it is woken. The details are in
[database connections](database-connections.md). **Setting a credential is in
beta** (Reality Ledger `beta`): re-earned on a new slot's names on the 1.18.0
trip (D2442).

## Backups

Every managed project is backed up continuously: a full backup, then each
change archived as it is written. `bin/project.sh backups --project-key KEY`
reads what the server last recorded about them, with its age:

- **a window** -- `restorable from EARLIEST to LATEST` -- the span a branch
  can be restored to. `EARLIEST` is a second after the oldest full backup
  finished; `LATEST` is the newest change the archive holds, so a point after
  it is not yet restorable;
- **sleeping** -- no new restore point is taken while the project sleeps; the
  window ends where it went to sleep;
- **could not be determined** (exit 6) -- no reading has been recorded, the
  newest is older than 30 minutes, or the repository, the archiver or the
  mirror could not be read. The reason is printed; **it is never shown as a
  window**.

The reading says the backups exist. **A branch is the test that they
restore**: making one restores the project's own backups into a new database
you can connect to.

## Branches

A **branch** is a copy of the project's database restored from its own
backups (ADR 0271) -- to the end of the archive, or to a point inside the
window -- with its own two passwords and its own two names,
`<branch>.pool.<domain>` and `<branch>.direct.<domain>`. The project itself is
never touched: a branch is a separate database, and nothing written to one
reaches the other.

```
bin/branch.sh create --project-key KEY --branch dev --password-dir ~/branches --wait
bin/branch.sh create --project-key KEY --branch dev --password-dir ~/branches --at 2026-10-14T09:30:00Z --wait
bin/branch.sh list --project-key KEY
bin/branch.sh show --project-key KEY --branch dev
bin/endpoint.sh connect --project-key KEY --role admin --branch dev --password-file ~/branches/KEY/dev/customer_admin
bin/branch.sh reset --project-key KEY --branch dev --password-dir ~/branches-2 --wait
bin/branch.sh delete --project-key KEY --branch dev --confirm dev --wait
```

- **The point.** Without `--at`, the branch holds the newest change the
  archive had when it was restored. With `--at INSTANT` (UTC,
  `YYYY-MM-DDTHH:MM:SSZ`) it holds exactly what was committed at that instant
  -- a restore to a point, into a branch. A point outside the window is
  refused; `show` prints the point the restore reached.
- **The passwords** are generated on your machine and written once, 0600, to
  `DIR/KEY/BRANCH/customer_app` and `customer_admin` before anything is sent;
  only their verifiers reach the server. The project's own passwords do not
  open a branch, and a branch's do not open the project.
- **Reset** restores the branch again -- to `--at` or the end of the archive --
  with two new passwords (a directory that does not hold the old ones); its
  names stay. Everything written to the branch since is lost.
- **Expiry.** `--expires-in 2h` (15 minutes to 7 days; `15m`, `3d`) deletes the
  branch then, on behalf of the member who set it.
- **One branch per project on Free** (the plan's `branches_total`). A second
  is refused `branch_limit_reached` before anything is recorded: delete the
  first.
- **Ready, and its door.** `show` prints `door`: `ready` once both of the
  branch's names answer through the server's edge with a certificate the
  server's system trust store verifies; `pending` when the certificate was not yet
  issued three minutes after the restore finished -- the branch is restored,
  and its names answer once the certificate arrives; `unknown` for a branch
  recorded before Session 41. `reason` names why the branch last failed or
  stopped -- a restore that did not finish, a start refused because its image
  changed -- and is empty otherwise.
- **A branch is not backed up.** Deleting it, or losing the server, loses
  what it holds. Delete needs an admin or owner; `--confirm` is its name.

The branch operations are being verified (Reality Ledger `trial`, ADR 0261):
offered on the 1.19.0 trip with D2501 and D2504 repaired, and moved to `beta`
or back to `planned` by the session's close.

## Plans

```
bin/plan.sh list
bin/plan.sh show [--organization ID]
bin/plan.sh notify-me [--organization ID]
```

**Every organisation is on Free during the beta** (ADR 0274). `list` prints
both plans and each entitlement with whether the server **enforces** it or only
**shows** it:

| Entitlement | Free | Enforced |
|---|---|---|
| `projects_active` | 1 per organisation | yes -- `plan_limit_reached` before anything is recorded |
| `branches_total` | 1 per project | yes -- `branch_limit_reached` before anything is recorded |
| `compute_profiles` | `small`, `standard`, `large` | yes -- the request names one of them |
| `storage_gb` | 5 | no -- shown against the database's size |
| `agent_calls_per_day` | 10,000 | no -- shown against the agent calls counted |
| `backup_retention` | two weekly full backups and the changes between them | yes -- by the project's own backup configuration |

Premium is defined and `unavailable_during_beta`: `notify-me` records that
your organisation asked, once however often you ask. Nothing is charged, and
nothing moves an organisation onto it. `show` prints your plan, the projects
you hold against `projects_active`, and the plans you asked about.

## Usage

```
bin/usage.sh show [--project-key KEY | --organization ID] [--hours N]
```

The server records one **sample** of every project every five minutes (ADR
0275). `show` reads the last `N` hours (1 to 720, default 24): how many
samples were expected and how many were recorded; each figure's newest reading
and the window's maximum -- the database's size, the backup repository's size,
the branches and their size, the connections by your own roles; the requests
answered below `400`, counted across counter resets; agent calls and workflow
runs, counted from their own records; and the seconds active and asleep, from
the project's history. The shown limits are printed beside the figures they
are read against.

- **A figure that could not be read is said** (*not read in this window*, and
  in how many samples), **never printed as `0`**. A sleeping project's samples
  read nothing and say it slept.
- **A window with no sample** -- a project the server has not sampled yet --
  could not be determined: the reason is printed and the command exits `6`.
- Agent calls and workflow runs are summed over the samples that counted them.

`usage` here is yours. `sudo bin/doctor.sh usage` is the operator's reading of
how much of the server one project uses, on the host, and means something
else.

## Notifications

```
bin/notifications.sh list [--organization ID] [--limit N]
```

One notification for every finished operation -- its type, its project, how it
ended (a failure's error code), and, when the server requested it, why (the
branch expired; the project was idle, and its backups stop) -- and, at most
once a day, a notice when a project passes 80% of a shown limit
(`storage_gb`, `agent_calls_per_day`). Newest first, in the API only: nothing
is mailed and there is no read state. A notification never carries a
credential, an address or a result value.

## What a refusal means

| Answer | Meaning |
|---|---|
| `409 plan_limit_reached` | The organisation already holds its plan's projects (Free: one); nothing was recorded |
| `409 capacity_exhausted` (`no_slot`) | No slot is ready on this server; nothing was recorded |
| failed `capacity_exhausted` (`admission`) | The server has no room for that profile; nothing changed |
| `409 conflict` | Another operation on this project, or another creation in this organisation, is in flight |
| `409 branch_limit_reached` | The project already has its plan's branches (Free: one), or one is being created; nothing was recorded |
| `409 not_available` | That kind of operation, or idle sleep, is not offered yet; the answer names the Reality Ledger row |
| `403 human_session_required` | A management key asked for something only a signed-in person may do |
| failed `invalid_request` | The request named something the operation cannot act on (a sleeping project's export, for instance) |
| failed `operation_failed` / `interrupted` / `could_not_determine` | The server could not finish it; the operation names the step, and the operator reads why |
