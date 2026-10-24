---
title: Quickstart
description: From an invitation link to a working connection string.
ledger: [accounts, organizations, projects_self_service, pooled_endpoint, direct_endpoint, cli_remote]
---
# Quickstart

From the invitation link to a working connection string, in the browser. Each step also has a command-line form, for when you prefer a terminal.

::: steps
## Accept your invitation

Open the link you were sent. It goes to the console's *Create your account* page: choose a username and a password. The link works once and expires; if it says *invitation_invalid*, ask for a new one.

## Create your organisation

An invitation to the beta opens an account and no organisation. On the console's overview choose *New organisation* and give it a name: you are its owner. If you were invited into someone's organisation instead, it is already on your overview.

## Set up your second factor

Owners and admins sign in with a six-digit code from an authenticator app. The console asks the first time it is needed and shows a QR code: scan it with the app, enter the code it shows, then sign in once more with the next code.

## Create a project

On the overview, your organisation's *New project*: a name, a size (*small* is enough to start) and a username for the project's own administrator. On the Free plan an organisation holds one project.

The moment the creation is recorded the page shows a **token, once**. The connection string and the SQL editor do not need it. It is for claiming the project's administrator from a terminal: to keep that possible, copy it into a file only you can read (`chmod 600`) before you choose *I have saved it*. A lost token cannot be shown again.

Creating a project can take up to half an hour. The page follows it and, when the project is ready, links to *Connect*.

## Connect

In the console, open the project and choose *Connect*. Set a new password for the pooled door: the page makes it in your browser, sends only a verifier, and shows the password and the connection string once. Copy both. Or open the project's *SQL editor* and run SQL in the page. Both doors require TLS (`sslmode=verify-full`) on port 5432. See [Connecting](/docs/connecting/).
:::

## Or, from a terminal

```
pipx install agentic-postgres-cli
apg login password --endpoint https://control.agenticpostgresql.com/api/v1 --username NAME
apg project create --name NAME --profile small --admin-username ADMIN
apg operation wait --operation OPERATION
apg project claim
apg endpoint credential --role app --password-file ./app-password --wait
apg endpoint connect --role app --password-file ./app-password
```

`uv tool install agentic-postgres-cli` installs the same command. A project created in the console is claimed with the token you saved: `apg project claim --project-key KEY --token-file FILE`.
