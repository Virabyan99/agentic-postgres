---
title: SQL editor
description: Your own PostgreSQL client in the console, on your project's two doors.
ledger: [sql_editor, pooled_endpoint, direct_endpoint]
---
# SQL editor

The console has a SQL editor for each project that has doors. It is your own client: it connects as the door's database role, with the password you type into the page, and PostgreSQL decides everything the role may do — its grants, its row policies and its connection limit — exactly as it does for `psql`.

Open the project, choose *SQL*, pick a door and type its password:

| Door | Role | For |
|---|---|---|
| pooled | the application role, `customer_app` | what your application does: a transaction pooler |
| direct | the administrator role, `customer_admin` | migrations, and tables in the `public` schema: a session pooler |

## Your password stays in the page

The password is read once when you connect, the field is emptied at once, and the page forgets it when you disconnect, leave the editor or close the tab. It is never stored, put in an address or sent to the console's API. The page proves it to PostgreSQL with SCRAM-SHA-256, so the password itself crosses no network at all.

If you have lost a door's password, set a new one on the *Connect* page: it is shown once there.

## How your session travels

A browser can open a WebSocket and nothing else, so the editor reaches your door through a relay on an address of its own, beside the console's. The relay carries your session over TLS on both sides and records none of it: no statement, no row, no part of the password exchange. It holds no credential and reaches only your project's own doors, through the same public entrance any client uses.

The relay can read what it carries while it carries it. The console and the command-line client make passwords from 32 random bytes; a password you chose yourself through the API is only as strong as you made it.

## Limits

- A statement still running after 60 seconds is cancelled. *Cancel* stops one sooner.
- A session ends after 30 minutes, or after 5 minutes with nothing sent either way.
- At most 1,000 rows (or 2 MiB of text) of a result are shown; the rest are not read.
- `COPY` is not supported in the editor.
- A project that is asleep must be woken from *Settings* first; the editor says so and opens nothing.

Not offered yet: the editor on a branch's doors, saved statements, and exporting a result.
