---
title: Getting started
description: Accounts, organisations, roles, invitations and the second factor.
ledger: [accounts, organizations, api_keys, management_api]
---
# Getting started

## Accounts

There is no public signup. A person who receives an invitation link opens it, chooses a username and a password, and has an account. An invitation works once and expires; an admin or owner can revoke one before it is used.

## Organisations and roles

An organisation groups people and projects. Each member has one role: owner, admin, member or viewer. A member creates projects, branches and passwords; an admin or owner also invites people, changes roles and deletes a project; only an owner invites another owner. A viewer reads.

Owners and admins sign in with a second factor: a six-digit code from an authenticator app. The console sets it up the first time it is needed: scan the QR code, enter a code, then sign in again with the next code -- confirming the factor ends every session you had.

## Inviting someone

In the console, *Members and keys* makes an invitation link for a role and shows it once, with a *Copy* button. Send it to the person; it is the invitation. With the command-line client:

```
apg org invite --role member --output ./invitation
```

The file holds the link; the person opens it, or runs `apg login accept --invitation-file ./invitation --endpoint https://control.agenticpostgresql.com/api/v1 --username NAME`.

## Management keys

A key reads your organisations and projects through the management API. It is shown once, never opens a database, and stops working when it is revoked or its owner leaves. Make one under *Members and keys*, or:

```
apg org key-create --name ci --scopes projects:read --output ./key
apg login key --endpoint https://control.agenticpostgresql.com/api/v1 --key-file ./key
```
