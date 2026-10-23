---
title: Projects
description: Creating a project, claiming its administrator, and its life after that.
ledger: [projects_self_service, sleep, idle_sleep, compute_profiles, export, project_deletion, region]
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

**The first administrator is yours alone.** `apg project create` writes a random token into its own state directory, readable only by you, before it sends anything, and sends only the token's SHA-256. When the creation has succeeded, `apg project claim` presents the token to the new project's own address and sets the administrator's password; the token file is removed once the project accepted it. The control plane never holds the token or the password. Keep the token until you have claimed.

In this beta a project is created with the command-line client; the console lists it and does everything after.

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
