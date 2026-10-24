---
title: Projects
description: Creating a project, claiming its administrator, and its life after that.
ledger: [projects_self_service, sleep, idle_sleep, compute_profiles, export, project_deletion, region, support_bundle]
---
# Projects

## The life of a project

```
apg project create --name "Shop backend" --profile small --admin-username shop.admin
apg operation wait --operation ID
apg project claim --project-key KEY --password-file ./admin-password
apg project status --project-key KEY
apg project sleep --project-key KEY
apg project wake --project-key KEY
apg compute set --project-key KEY --profile standard
apg project export --project-key KEY --output shop.dump
apg project delete --project-key KEY --confirm KEY
```

Each change answers at once with an **operation** -- pending, then running with its step, then succeeded or failed with a closed error code -- and `apg operation wait` follows it. One operation runs on a project at a time, and one creation in an organisation; a second is refused `conflict`, naming the first.

A project's state comes from its operations: creating, ready, suspending, sleeping, starting, updating, deleting, deleted. When the latest operation was interrupted, or its outcome could not be determined, the state is *unknown* -- never *ready*.

## Creating, and claiming the first administrator

A project is created into a slot prepared on this server: its name, its address, its storage and its backups exist before you ask. Your project's key is the slot's; the name you give is a display name. Your plan is read first: Free holds one project per organisation -- a sleeping project holds its place -- so a second is refused `plan_limit_reached`. When no slot is ready the creation is refused `capacity_exhausted`. In both cases nothing is created.

In the console, an organisation's *New project* asks for a name, a size and the administrator's username, then follows the creation and links to *Connect* when the project is ready.

**The first administrator is yours alone.** A random token is made on your side -- in your browser, or by `apg project create` in its own state directory, readable only by you -- and only its SHA-256 is sent. The console shows its token **once**, the moment the creation is recorded: save it in a file only you can read if you will claim. When the creation has succeeded, `apg project claim` (with `--token-file FILE` for the console's token) presents it to the new project's own address and sets the administrator's password. The control plane never holds the token or the password. **Claiming is optional**: the connection string and the SQL editor need no administrator; the claim is for your project's own admin API. A lost token cannot be shown again.

## Sleeping and waking

A sleeping project keeps its data. While it sleeps its addresses and its database doors refuse connections, and **its backups stop: its last restore point is the moment it went to sleep**. It cannot be exported or resized; wake it first. A project can also sleep after 15, 30 or 60 minutes with no request and no connection -- off unless you turn it on, and a reading that is missing keeps it awake:

```
apg project idle-sleep --project-key KEY --minutes 30
```

::: warning
It wakes only when someone asks; a connection does not wake it.
:::

## Changing the size

Three sizes: small, standard and large, all on the Free plan. A change restarts the project, and its message says how long the restart was measured to take. When the server has no room for the new size the change fails `capacity_exhausted` and nothing changes.

## Exporting

An export is an archive of the project's own schemas -- `app`, `api` and `public` -- in `pg_dump`'s custom format, which `pg_restore` reads. `apg project export` waits for the operation, downloads the archive once, checks its SHA-256 and writes it to a new file. The download link lives at most 15 minutes and is handed out once, to the person who asked.

## Deleting

An admin or owner deletes a project with `apg project delete --project-key KEY --confirm KEY`, or the console's project settings with the key typed. Its containers, data, credentials and address on this server are removed. The slot is never given to another project. The project's backups are kept by the operator.

Every project runs in one location, the one server this beta runs on.

## Support information

A project's *Settings* in the console shows its **support bundle**: the latest reading of each of the server's health checks for your project -- a verdict and one sentence each, never a file path or a secret -- with how old it is, and the project's recent operations. The readings are taken every 15 minutes; one older than 30 minutes says so. It is the page to send to someone helping you. From a terminal it is written to a new file, readable only by you:

```
apg project diagnostics --project-key KEY --output ./support.json
```
