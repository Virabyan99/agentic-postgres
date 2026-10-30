---
title: SQL editor
description: Run SQL you write yourself, from the console, as your own database role.
ledger: [sql_editor, pooled_endpoint, direct_endpoint]
---
# SQL editor

The console has a SQL editor for each project that has doors: open the project and choose *SQL editor*. It is your own client: it connects as the door's database role, with a password you made on *Connect*, and PostgreSQL decides everything the role may do -- its grants, its row policies and its connection limit -- exactly as it does for `psql`.

## The state bar

The bar at the top of the page always says where the editor is: *Not connected*, or *Connected* with the door, the user and the database, and *Disconnect*. The line in the bar says what last happened -- connecting, a statement that finished, a session that ended and why.

## Connecting

While the editor is not connected, the form to connect is the only thing below the bar. Choose a door and type its password:

| Door | User | For |
|---|---|---|
| pooled | the application role, ending in `_customer_app` | what your application does: a transaction pooler |
| direct | the administrator role, ending in `_customer_admin` | migrations, and tables in the `public` schema: a session pooler |

The password is the one you made for that door on *Connect* (see [Connecting](/docs/connecting/)); if you have lost it, make a new one there. Then choose *Connect*. Once connected, the form is gone and the statement box takes its place.

## Your password stays in the page

The password is read once when you connect, the field is emptied at once, and the page forgets it when you disconnect, leave the editor or close the tab. It is never stored, put in an address or sent to the console's API. To connect again, type it again. The page proves it to PostgreSQL with SCRAM-SHA-256, so the password itself crosses no network at all.

## Your first statement

The box starts with a statement that changes nothing:

```
select now(), current_user;
```

Choose *Run*. Each result shows how many rows it returned and how long it took, then the rows, with the column names fixed at the top while you scroll. *Copy as CSV* copies the rows the page shows. A statement that returns no rows says what it did, such as `CREATE TABLE`. *Cancel* stops a statement that is still running.

## Making a table

**To make a table, connect on the direct door.** Only the administrator role may create tables, and it creates them in the `public` schema; the application role, on the pooled door, reads and writes the tables the administrator made but creates none -- on the pooled door `create table` is refused (*permission denied for schema public*). On the direct door, try:

```
create table notes (id bigint generated always as identity primary key, body text not null);
insert into notes (body) values ('first'), ('second');
select * from notes;
```

Then disconnect, connect on the pooled door, and `select * from notes;` reads the same rows, as your application will.

## Limits

- A statement still running after 60 seconds is cancelled.
- A session ends after 5 idle minutes, or after 30 minutes in all.
- At most 1,000 rows (or 2 MiB of text) of a result are shown; the rest are not read, and the result says so.
- At most 4 editor sessions are open on one door at a time.
- `COPY` is not supported in the editor.
- A project that is asleep must be woken from its *Settings* first; the editor says so and opens nothing.

## When a session ends

The bar says why, in one sentence, and what to do:

| What the bar says | What to do |
|---|---|
| The session closed normally. | Nothing: you disconnected. |
| The connection to the editor's relay was lost, or could not be opened. | Check your network, then connect again. |
| The relay failed while it carried the session. | Connect again; if it happens again, ask for help ([Support](/docs/support/)). |
| The relay refused a message it does not carry, and closed the session. | Connect again. |
| The session ended: it ran for 30 minutes, or sat idle for 5. | Connect again. |
| The session carried more than the relay allows, and was closed. | Ask for fewer rows at a time, then connect again. |
| Too many editor sessions are open on this server. | Try again in a minute. |
| The relay could not reach your database. | If the project is asleep, wake it from its *Settings* page, then connect again. |
| The database refused the password. | Type it again, or make a new one on *Connect*. |

## How your session travels

A browser can open a WebSocket and nothing else, so the editor reaches your door through a relay on an address of its own, beside the console's. The relay carries your session over TLS on both sides and records none of it: no statement, no row, no part of the password exchange. It holds no credential and reaches only your project's own doors, through the same public entrance any client uses.

The relay can read what it carries while it carries it. The console and the command-line client make passwords from 32 random bytes; a password you chose yourself through the API is only as strong as you made it.

Not offered yet: the editor on a branch's doors, and saved statements.
