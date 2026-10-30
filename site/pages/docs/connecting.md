---
title: Connecting
description: The two doors, a password for each, the code for your tool, and psql on your computer.
ledger: [pooled_endpoint, direct_endpoint, postgresql, console]
---
# Connecting

Every project has two doors, both on port 5432 and both requiring TLS with the server's name checked (`sslmode=verify-full`). In the console, open the project and choose *Connect*: the page takes you through the same three steps as this one, with your project's own names filled in and a *Copy* button on every value.

## 1. Choose a door

::: doors
::: feature
### Pooled

Recommended. For your application: many short connections share a few to the database.

- Host: `pool.` and your project's name
- User: the application role, whose name ends in `_customer_app`
- Pooler: a transaction pooler
:::
::: feature
### Direct

One session per connection, kept for as long as you hold it: migrations, `pg_dump`, `LISTEN`, advisory locks and long analytics, and tables in the `public` schema.

- Host: `direct.` and your project's name
- User: the administrator role, whose name ends in `_customer_admin`
- Pooler: a session pooler
:::
:::

Both doors always exist. Projects run PostgreSQL 18 with pgvector.

## 2. Make a password for the door

No password is stored where anyone can read it back. Choose *Make a new password for the pooled door* (or the direct one): your browser makes the password and sends only its fingerprint, a SCRAM verifier, so the platform never holds it. The page then shows the password and the connection string with it, **once**. Copy them into your password manager or your application's settings, then choose *I have saved the password*. Making a new password replaces the old one: connections that use the old one stop working.

While the page stays open, the code in step 3 is shown with the new password already filled in. Leave the page and it is gone; if you lose a password, make a new one.

With the command-line client the password is made on your machine and written to a file only you can read:

```
apg endpoint show
apg endpoint credential --role app --password-file ./app-password --wait
apg endpoint connect --role app --password-file ./app-password
apg endpoint credential --role admin --password-file ./admin-password --wait
```

`apg endpoint connect` runs `psql` with the door, the role and TLS set; anything after it is passed to `psql`.

## 3. Copy the code for your tool

The console's *Connect* shows this code with your project's names. Here it is for an example project whose doors are `pool.shop.example.com` and `direct.shop.example.com`: the text is exactly what the server gives the console. Where a password goes it says `<password from your file>`: put the password from step 2 there, or copy the code from the console while it still shows the password.

### psql

Where it goes: your terminal. What to install: psql 16 or newer (it reads sslrootcert=system); the connecting page has a line for your operating system.

```
# Pooled (transaction mode), as shop_prod_customer_app:
psql "host=pool.shop.example.com port=5432 user=shop_prod_customer_app dbname=shop_prod sslmode=verify-full sslrootcert=system"
# Direct (a session: migrations, LISTEN, advisory locks), as shop_prod_customer_admin:
psql "host=direct.shop.example.com port=5432 user=shop_prod_customer_admin dbname=shop_prod sslmode=verify-full sslrootcert=system"
```

### Prisma

Where it goes: .env, beside prisma/schema.prisma (url = env("DATABASE_URL"), directUrl = env("DIRECT_URL")); the CLI reads it, your app loads it: node --env-file=.env. What to install: npm install prisma@6 @prisma/client@6.

```
DATABASE_URL="postgresql://shop_prod_customer_app:<password from your file>@pool.shop.example.com:5432/shop_prod?sslmode=require&sslaccept=strict"
DIRECT_URL="postgresql://shop_prod_customer_admin:<password from your file>@direct.shop.example.com:5432/shop_prod?sslmode=require&sslaccept=strict"
```

Prisma's command-line tool reads `.env`; Prisma Client does not, so start your application with `node --env-file=.env`. `DATABASE_URL` is the pooled door, for your application; `DIRECT_URL` is the direct door, which `prisma migrate` uses.

**A database that already has tables.** If you made tables before your first Prisma migration -- in the SQL editor, say -- `npx prisma migrate deploy` stops with `P3005` (*The database schema is not empty*). Baseline once, with `DIRECT_URL` set: `db pull` writes the existing tables into `prisma/schema.prisma`, the next two lines record them as a first migration that is already applied, and then you deploy as usual:

```
npx prisma db pull
mkdir -p prisma/migrations/0_init
npx prisma migrate diff --from-empty --to-schema-datamodel prisma/schema.prisma --script > prisma/migrations/0_init/migration.sql
npx prisma migrate resolve --applied 0_init
npx prisma migrate deploy
```

These lines were run with Prisma 6.19.1 on 2026-10-29, against a table made before any migration: before them `migrate deploy` stopped with `P3005`; after them it applied the next migration and kept the table's rows. They are Prisma 6's: Prisma 7 calls the option `--to-schema`.

### Node (pg)

Where it goes: db.js. What to install: npm install pg.

```
import pg from "pg";

const pool = new pg.Pool({
  host: "pool.shop.example.com",
  port: 5432,
  user: "shop_prod_customer_app",
  database: "shop_prod",
  password: "<password from your file>",
  ssl: { rejectUnauthorized: true },
});
```

### Python (psycopg)

Where it goes: db.py. What to install: pip install "psycopg[binary]" certifi.

```
import certifi
import psycopg

conn = psycopg.connect(
    "host=pool.shop.example.com port=5432 user=shop_prod_customer_app dbname=shop_prod sslmode=verify-full sslrootcert=" + certifi.where(),
    password="<password from your file>",
)
```

`psycopg[binary]` carries its own copy of OpenSSL, which does not find your computer's list of trusted authorities, so `sslrootcert=system` would check against nothing. `certifi` gives it Mozilla's list instead, and the server's name is still checked.

### Drizzle

Where it goes: db.js. What to install: npm install drizzle-orm pg.

```
// db.js -- the pooled door (transaction mode)
import pg from "pg";
import { drizzle } from "drizzle-orm/node-postgres";

export const pool = new pg.Pool({
  host: "pool.shop.example.com",
  port: 5432,
  user: "shop_prod_customer_app",
  database: "shop_prod",
  password: "<password from your file>",
  ssl: { rejectUnauthorized: true },
});
export const db = drizzle(pool);

// Migrations: the direct door, as shop_prod_customer_admin -- run their SQL with the
// psql snippet's second line. drizzle-orm's migrate() is refused there: it
// runs CREATE SCHEMA first, and this project's roles may not create one.
```

Drizzle uses the pooled door. Its own `migrate()` cannot run here: it first runs `CREATE SCHEMA`, and your project's roles may not create a schema. Run your migrations' SQL files on the direct door with psql instead: the psql code's second command, the direct one, with `-f` and the file's name added.

### Go (pgx)

Where it goes: db.go. What to install: go get github.com/jackc/pgx/v5.

```
// db.go
package main

import (
	"context"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// connect opens the pooled door (transaction mode), as shop_prod_customer_app.
func connect(ctx context.Context) (*pgxpool.Pool, error) {
	config, err := pgxpool.ParseConfig("host=pool.shop.example.com port=5432 user=shop_prod_customer_app dbname=shop_prod sslmode=verify-full sslrootcert=system")
	if err != nil {
		return nil, err
	}
	config.ConnConfig.Password = "<password from your file>"
	return pgxpool.NewWithConfig(ctx, config)
}

// connectDirect opens the direct door (a session: migrations, LISTEN,
// advisory locks), as shop_prod_customer_admin.
func connectDirect(ctx context.Context) (*pgx.Conn, error) {
	config, err := pgx.ParseConfig("host=direct.shop.example.com port=5432 user=shop_prod_customer_admin dbname=shop_prod sslmode=verify-full sslrootcert=system")
	if err != nil {
		return nil, err
	}
	config.Password = "<password from your file>"
	return pgx.ConnectConfig(ctx, config)
}
```

### .env

Where it goes: .env. What to install: nothing: psql 16+ and Go pgx read these URLs (node-postgres and psycopg[binary] do not read sslrootcert=system: use theirs).

```
# DATABASE_URL: the pooled door (transaction mode), for the application.
# DIRECT_URL: the direct door (a session), for migrations.
DATABASE_URL="postgresql://shop_prod_customer_app:<password from your file>@pool.shop.example.com:5432/shop_prod?sslmode=verify-full&sslrootcert=system"
DIRECT_URL="postgresql://shop_prod_customer_admin:<password from your file>@direct.shop.example.com:5432/shop_prod?sslmode=verify-full&sslrootcert=system"
```

Two of the tools above read these URLs as they are: psql 16 or newer and Go's pgx. To use them in a terminal:

```
set -a; . ./.env; set +a
psql "$DATABASE_URL"
```

node-postgres (and Drizzle, which runs on it) reads `sslrootcert=system` as a file name, `psycopg[binary]` cannot use it, and Prisma accepts `sslmode=verify-full` without checking the server's name: for those, use their own code above.

## Installing psql

psql is PostgreSQL's own terminal client. The code above needs **psql 16 or newer**: older versions do not read `sslrootcert=system`, the setting that checks the server's certificate against your computer's own list of trusted authorities. `psql --version` says which you have.

### Debian and Ubuntu

On Debian 13 and Ubuntu 24.04 and 26.04 the distribution's own psql is new enough. As root:

```
apt-get update
apt-get install -y postgresql-client ca-certificates
psql --version
```

On Debian 12 and Ubuntu 22.04 the distribution's psql is too old (15 and 14). Add PostgreSQL's own package repository and install its psql 18 instead. As root:

```
apt-get update
apt-get install -y postgresql-common ca-certificates gnupg
/usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y
apt-get install -y postgresql-client-18
psql --version
```

These lines were run on 2026-10-29, each in a fresh container of the distribution's own image:

| System | Lines | psql it installed |
|---|---|---|
| Debian 13 | the distribution's | `psql (PostgreSQL) 17.11 (Debian 17.11-0+deb13u1)` |
| Debian 12 | the distribution's | `psql (PostgreSQL) 15.19 (Debian 15.19-0+deb12u1)` |
| Debian 12 | PostgreSQL's repository | `psql (PostgreSQL) 18.6 (Debian 18.6-1.pgdg12+2)` |
| Ubuntu 26.04 | the distribution's | `psql (PostgreSQL) 18.6 (Ubuntu 18.6-0ubuntu0.26.04.1)` |
| Ubuntu 24.04 | the distribution's | `psql (PostgreSQL) 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1)` |
| Ubuntu 22.04 | the distribution's | `psql (PostgreSQL) 14.24 (Ubuntu 14.24-0ubuntu0.22.04.1)` |
| Ubuntu 22.04 | PostgreSQL's repository | `psql (PostgreSQL) 18.6 (Ubuntu 18.6-1.pgdg22.04+2)` |

The second set is the PostgreSQL project's own instructions (`www.postgresql.org/download/linux/debian/` and `www.postgresql.org/download/linux/ubuntu/`, read 2026-10-29); `-y` answers the one question the script asks.

### macOS

The PostgreSQL project's download page for macOS, `www.postgresql.org/download/macosx/` (read 2026-10-29), lists the interactive installer by EDB, Postgres.app, Homebrew, MacPorts and Fink. Its Homebrew example is `brew install postgresql@15`; choose a version of 16 or newer, the number after the `@`. We have not run these on a Mac.

### Windows

The PostgreSQL project's download page for Windows, `www.postgresql.org/download/windows/` (read 2026-10-29), offers the interactive installer by EDB, for PostgreSQL 13 to 18: choose 16 or newer. The page does not say how to install psql alone. We have not run it on Windows.

### No psql at all

The project's *SQL editor* in the console needs nothing installed: see [SQL editor](/docs/sql-editor/).

The connection lines on this page were run on Linux. On macOS and Windows, `sslrootcert=system` reads the list of trusted authorities your psql was built with; we have not run it there.

## A connection string

```
postgresql://USER:PASSWORD@pool.YOUR-PROJECT:5432/DATABASE?sslmode=verify-full&sslrootcert=system
```

The console and `apg endpoint show` give the exact user, host and database. Every part: the user is the door's database role; the host is the door's name, which the server's certificate is issued for; both doors listen on port 5432; the database is your project's; `sslmode=verify-full` encrypts the connection and checks the server's name.
