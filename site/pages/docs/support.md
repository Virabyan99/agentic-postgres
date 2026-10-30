---
title: Support
description: How to ask a person for help, what to send, and what never to send.
ledger: [support_bundle, console, accounts]
---
# Support

## Ask a person

Write to the people who run this service. A person reads every message:

@contact

The console's *Help*, at the top of every page, shows the same address with a *Copy* button. This beta sends no email of its own: nothing else will write to you.

## What to send

- **The project's key**, if it is about a project: it is on the project's *Overview*, with *Copy*.
- **What the page said**, and the word in small type under it -- `plan_limit_reached`, for example. That word is the same in the console, the command-line client and the management API.
- **When it happened** and which page you were on. For a long operation, the link to its page: every operation has one, from the organisation's *Activity*.
- **The project's support bundle**, below.

## Never send a secret

Never send a password, a management key, a handoff token, an invitation link, a code from your authenticator app or a connection string that holds a password. Nobody here will ask you for one, and a message that holds one is not needed to help you. If you sent one by mistake, replace it: a new password made on *Connect* stops the old one working, and a management key can be revoked under *Members and keys*.

## The support bundle

A project's *Settings* shows its **support bundle**: the latest reading of each of the server's health checks for your project -- a verdict and one sentence each, with when it was read -- and the project's recent operations. It holds no data, no password and no file path. The readings are taken every 15 minutes; one older than 30 minutes is marked *stale*. From a terminal it is written to a new file, readable only by you, which you can attach to your message:

```
apg project diagnostics --project-key KEY --output ./support.json
```

## Before you write

- [What a refusal means](/docs/refusals/): every word a page can answer, and what to do about it.
- [Quickstart](/quickstart/): every step from the invitation to a connected application.
- [What exists](/ledger/): what the beta does today, and what it does not.
