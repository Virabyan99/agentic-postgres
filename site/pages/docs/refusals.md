---
title: What a refusal means
description: Every refusal's word, and what to do about it.
ledger: [projects_self_service, branches, accounts, organizations, api_keys]
---
# What a refusal means

A refusal is one word, the same in the console, the command-line client and the management API.

| Word | Means |
|---|---|
| `authentication_failed` | the username or the password is not right, or the session has ended |
| `second_factor_required` | enter the six-digit code from your authenticator app |
| `second_factor_invalid` | the code is wrong or already used; wait for the next one |
| `invitation_invalid` | the invitation is used, expired, revoked or unknown; ask for a new one |
| `username_taken` | choose another username; the invitation is still good |
| `authorization_failed` | your role in the organisation does not allow this |
| `human_session_required` | a management key asked for something only a signed-in person may do |
| `not_found` | nothing by that name, or it is not yours to see -- the same answer for both |
| `plan_limit_reached` | the organisation already holds its plan's projects (Free: one); nothing was recorded |
| `capacity_exhausted` | no slot is ready on this server, or no room for that size; nothing was recorded |
| `conflict` | another operation on this project, or another creation in this organisation, is in flight |
| `branch_limit_reached` | the project already has its plan's branches (Free: one), or one is being made |
| `not_available` | that is not offered yet; the answer names the row in [What exists](/ledger/) |

An operation that started and then failed names the step it stopped at and the reason; the operator reads why.
