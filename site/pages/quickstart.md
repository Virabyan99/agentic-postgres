---
title: Quickstart
description: From an invitation link to a working connection string.
ledger: [accounts, organizations, projects_self_service, pooled_endpoint, direct_endpoint, cli_remote]
---
# Quickstart

From the invitation link to a working connection string, in the browser or the terminal.

## 1. Accept your invitation

Open the link you were sent. It goes to the console's *Create your account* page: choose a username and a password. The link works once and expires; if it says *invitation_invalid*, ask for a new one.

## 2. Set up your second factor

Owners and admins sign in with a six-digit code from an authenticator app. The console shows a QR code: scan it with the app, enter the code it shows, then sign in once more with the next code.

## 3. Open a project

The console's overview lists your organisations and their projects. In this beta a project is created with the command-line client:

```
pipx install agentic-postgres-cli
apg login password --endpoint https://control.agenticpostgresql.com/api/v1 --username NAME
apg project create --name NAME --profile small --admin-username ADMIN
apg operation wait --operation OPERATION
apg project claim
```

`uv tool install agentic-postgres-cli` installs the same command. On the Free plan an organisation holds one project.

## 4. Connect

In the console, open the project and choose *Connect*. Set a new password for the pooled door: the page makes it in your browser, sends only a verifier, and shows the password and the connection string once. Copy both. With the command-line client:

```
apg endpoint credential --role app --password-file ./app-password --wait
apg endpoint connect --role app --password-file ./app-password
```

Both doors require TLS (`sslmode=verify-full`) on port 5432. See [Connecting](/docs/connecting/).
