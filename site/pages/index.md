---
title: Agentic Postgres
description: PostgreSQL projects with pooled and direct connections, branches and backups. Invite-only during the beta.
ledger: [accounts, organizations, projects_self_service, postgresql, pooled_endpoint, direct_endpoint, branches, backups_and_pitr, plan_free, monitoring, usage, query_insights]
---
::: hero
::: lead
# Hosted PostgreSQL 18 that only claims what it has proven.

Your team's own PostgreSQL 18 projects, with pgvector, on one hosted server. Each project has a pooled and a direct connection, both over TLS; a branch is a full copy you can restore to a point in time; backups run continuously off-site, and the console shows the window you can restore to.
:::
::: actions
[Request an invitation](mailto:invite@agenticpostgresql.com?subject=Invitation%20request) [Read the quickstart](/quickstart/) Already invited? [Open the console](https://control.agenticpostgresql.com/console/)
:::
@restore-example
:::

## What every project gives you

::: features
::: feature
### Two connections, both over TLS

@chips pooled_endpoint direct_endpoint

Every project has two doors, both on port 5432 and both requiring TLS (`sslmode=verify-full`): the pooled door for your application, the direct door for migrations.

**Pooled** is a transaction pooler as `customer_app`; **direct** is a session pooler as `customer_admin`.

[Connecting](/docs/connecting/)
:::
::: feature
### Branches you can restore to a moment

@chips branches backups_and_pitr

A restore makes a new branch at a moment inside the project's backup window; the project itself is never overwritten.

**A branch is not backed up**: deleting it, or losing the server, loses what it holds.

[Branches](/docs/branches/)
:::
::: feature
### Continuous off-site backups

@chips backups_and_pitr

Backups run continuously off-site, and the console shows the window you can restore to.

**While a project sleeps its backups stop**: its last restore point is the moment it went to sleep.

[Backups](/docs/backups/)
:::
::: feature
### Numbers that name their source

@chips monitoring usage query_insights

A short list of readings about a project, each with the moment it was read and where it comes from -- or *not read*, with the reason.

**There is no threshold, no colour and no alert**: the reading and its age.

[Query Insights and monitoring](/docs/insights-and-monitoring/)
:::
:::

::: steps
## From invitation to connection string

### Accept your invitation

Open the link you were sent: choose a username and a password. The link works once and expires.

### Set up your second factor

Owners and admins sign in with a six-digit code from an authenticator app. The console shows a QR code: scan it with the app.

### Open a project

In this beta a project is created with the command-line client:

```
pipx install agentic-postgres-cli
apg project create --name NAME --profile small --admin-username ADMIN
apg project claim
```

### Connect

Set a new password for the pooled door; the console shows the password and the connection string once.

```
apg endpoint credential --role app --password-file ./app-password --wait
apg endpoint connect --role app --password-file ./app-password
```

[The whole quickstart](/quickstart/)
:::

::: band
@ledger-summary

Every concept this product names, with what it is today -- generated from the same file the product checks itself against.

@ledger-examples

[See every concept in What exists](/ledger/)
:::

## Free during the beta

During the beta every organisation is on the Free plan, at no cost.

@plan-summary

[Pricing](/pricing/) lists what each plan allows.

::: band-dark
## The beta is invite-only.

There is no public signup. To ask for an invitation, write and say who you are and what you would build. The invitation arrives as a link; opening it creates your account.

[Email for an invitation](mailto:invite@agenticpostgresql.com?subject=Invitation%20request) [I have an account, open the console](https://control.agenticpostgresql.com/console/)
:::
