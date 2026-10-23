---
title: Connecting
description: The pooled and direct doors, their passwords, and TLS.
ledger: [pooled_endpoint, direct_endpoint, postgresql]
---
# Connecting

Every project has two doors, both on port 5432 and both requiring TLS (`sslmode=verify-full`):

| Door | Host | Role | For |
|---|---|---|---|
| pooled | `pool.` and the project's domain | the application role, `customer_app` | your application: a transaction pooler |
| direct | `direct.` and the project's domain | the administrator role, `customer_admin` | migrations, and tables in the `public` schema: a session pooler |

Projects run PostgreSQL 18 with pgvector.

## Passwords

No password is stored where you can read it back. To use a door, set its role's password: the new one replaces the previous one once the operation succeeds.

In the console, open the project, choose *Connect*, and set a new password for a door. The page makes the password in your browser and sends only a SCRAM verifier; it then shows the password, the connection string with it, and a `psql` line, once.

With the command-line client the password is made on your machine and written to a file only you can read:

```
apg endpoint show
apg endpoint credential --role app --password-file ./app-password --wait
apg endpoint connect --role app --password-file ./app-password
apg endpoint credential --role admin --password-file ./admin-password --wait
```

`apg endpoint connect` runs `psql` with the door, the role and TLS set; anything after it is passed to `psql`.

## A connection string

```
postgresql://customer_app:PASSWORD@pool.PROJECT-DOMAIN:5432/DATABASE?sslmode=verify-full
```

The console and `apg endpoint show` give the exact host, role and database.
