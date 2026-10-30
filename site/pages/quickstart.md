---
title: Quickstart
description: From an invitation link to an application connected to your own database.
ledger: [accounts, organizations, projects_self_service, pooled_endpoint, direct_endpoint, console, sql_editor, cli_remote]
---
# Quickstart

From the invitation link to an application connected to your own database, in the browser. Every step is a page in the console, named here as the console names it. Each step also has a command-line form, at the end, for when you prefer a terminal.

::: steps
## Accept your invitation

Open the link you were sent. It opens the console's *Create your account* page: choose a username, a display name if you like, and a password (twice), then *Create your account*. The link works once and expires; if the page says *invitation_invalid*, ask the person who invited you for a new one.

You arrive on *Projects*. Its *Getting started* card lists the five things between you and a connected application -- a second factor, an organisation, a project, a password for a door, a connection -- and marks each one done as your account shows it, on any device.

## Create your organisation

An invitation to the beta opens an account and no organisation. Choose *New organisation* (at the top of *Projects*, or *Create one* in the card), give it a name and choose *Create*: you are its owner. If you were invited into someone's organisation instead, it is already on *Projects*.

## Set up your second factor

Owners and admins sign in with a six-digit code from an authenticator app, so as soon as you own an organisation the console shows *Set up your second factor*. Scan the QR code with the app (or type the key shown under it), enter the code the app shows and choose *Confirm*. Confirming ends every session you had: sign in again with your username, your password and the **next** code.

## Create a project

On *Projects*, your organisation's *New project*:

- *Name*: any name; only your organisation sees it.
- *Profile*: the size. *small* is enough to start; you can change it later in the project's *Settings*.
- *Administrator's username*: the first user of the project's own sign-in (its API) -- not your console account.

Choose *Create project*. The fields lock while the creation starts, so it cannot be sent twice. On the Free plan an organisation holds one project; while one is being created, *New project* is disabled and says why.

## Follow the creation

The page becomes the creation's tracker: 9 named steps, from *Reserving a server slot* to *Recording the project*, each marked done, in progress or to come, with its time. A creation **usually takes about 23 to 28 minutes**, most of it the first full backup, which makes sure your data can be restored from the start. There is no percentage: the step and the time are what is known. If a creation has not finished 30 minutes after it started, the server stops it and the page says so.

You can close the page. The project shows on *Projects* while it is being created, with *Follow*; *Notifications* says when it started and when it finished; and opening the tracker again reads it again.

Above the tracker, the page shows a **handoff token**, once. **You do not need it to connect** -- not from the console, not from your application. It only lets someone at a terminal take over the project's administrator account; *Using it from a terminal (optional)* says how. Copy it into a file only you can read if you want that, then choose *I've saved it, or I don't need it*. It cannot be shown again, and after a refresh the page says so.

## Connect

When the creation finishes, the tracker says *Your project ... is ready* and links to *Connect to it*. *Connect* has three steps:

1. *Choose a door*: **Pooled** (recommended) for your application, **Direct** for migrations and making tables.
2. *Make a new password for the pooled door*: your browser makes it and sends only its fingerprint. It is shown **once**, with the connection string: copy both, then choose *I have saved the password*.
3. *Copy the code for your tool*: psql, Node (pg), Prisma, Drizzle, Python (psycopg), Go (pgx) or an `.env` file, each saying which file it goes in and what to install. While the page is open the code holds your new password.

[Connecting](/docs/connecting/) has the same code, and how to install psql on your computer.

## Run SQL you write yourself

No psql? The project's *SQL editor* runs SQL in the page. Choose a door, type the password you made for it on *Connect*, and choose *Connect*; the bar at the top says *Connected*, the door and the user. To **make a table**, connect on the **direct** door -- only the administrator role creates tables -- then write your statement and choose *Run*. See [SQL editor](/docs/sql-editor/).

## Connect your application

Put the code from step 3 of *Connect* into your application and run it. *Getting started*'s last step, *Connect your application*, reads the project's usage, sampled every five minutes: it says *Seen* once a sample has seen your connection, and *Not seen yet* until then. When all five are done, the card goes away.
:::

**If something is refused or stuck.** Every refusal says what happened and what to do, with its word in small type under it -- [What a refusal means](/docs/refusals/) lists them all. *Help*, at the top of every console page, says how to ask a person: see [Support](/docs/support/).

## Or, from a terminal

```
pipx install agentic-postgres-cli
apg login password --endpoint https://control.nomipg.com/api/v1 --username NAME
apg project create --name NAME --profile small --admin-username ADMIN
apg operation wait --operation OPERATION
apg project claim
apg endpoint credential --role app --password-file ./app-password --wait
apg endpoint connect --role app --password-file ./app-password
```

`uv tool install agentic-postgres-cli` installs the same command. A project created in the console is claimed with the token you saved: `apg project claim --project-key KEY --token-file FILE`.
