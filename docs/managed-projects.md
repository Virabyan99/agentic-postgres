# Managed projects

Since `1.16.0` (Session 38, ADR 0256-0261) a member of an organisation can
create a project through the management API, and then sleep, wake, resize,
export and delete it, without the operator running a command for any of it.
This page is the customer's: what each step does, what it refuses, and what
it keeps. The routes and the roles are in [the control plane](control-plane.md);
the operator's half -- slots, the reconciler, revocation -- is the
[operator guide](operator-guide.md) §20.

**Every one of these operations is being verified** (Reality Ledger status
`trial`, ADR 0261): it is open while the evidence that would make it `beta` is
collected, and [the Reality Ledger](reality-ledger.md) says so for each.

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
anything is built. In this beta the server holds one slot, so a second
creation is refused.

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

## Changing the size

Three profiles: `small`, `standard` and `large` -- memory, connection and
process bounds named once, so every limit the server checks applies to them.
`bin/compute.sh set` **restarts the project**; the answer says the restart has
not yet been measured on this server. **When the server has no room for the
new size the change fails `capacity_exhausted` (`admission`) and nothing
changes** -- the project keeps its profile and keeps running.

## Exporting

`bin/project.sh export --output FILE` asks for an archive of the project's own
schemas, `api` and `app` -- your tables and your API, never the platform's
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

## What a refusal means

| Answer | Meaning |
|---|---|
| `409 capacity_exhausted` (`no_slot`) | No slot is ready on this server; nothing was recorded |
| failed `capacity_exhausted` (`admission`) | The server has no room for that profile; nothing changed |
| `409 conflict` | Another operation on this project, or another creation in this organisation, is in flight |
| `409 not_available` | That kind of operation is not offered yet; the answer names the Reality Ledger row |
| `403 human_session_required` | A management key asked for something only a signed-in person may do |
| failed `invalid_request` | The request named something the operation cannot act on (a sleeping project's export, for instance) |
| failed `operation_failed` / `interrupted` / `could_not_determine` | The server could not finish it; the operation names the step, and the operator reads why |
