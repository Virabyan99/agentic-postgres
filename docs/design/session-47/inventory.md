# Session 47 — the console's inventory

Derived at `de996bf` by `~/s47/run1/inventory.py` (Run 1, D2952). Every word below is read
from the module that raises or closes with it; nothing is typed. Regenerate, never edit.

## 1. Every refusal word the console can meet

| Word | Source | HTTP | In the console's `REFUSALS` today |
|---|---|---|---|
| `authentication_failed` | generic | 401 | yes |
| `authorization_failed` | generic | 403 | yes |
| `branch_limit_reached` | `errors.CONTROL_STATUS` | 409 | yes |
| `capacity_exhausted` | `errors.CONTROL_STATUS`, `OPERATION_ERROR_CODES` | 409 | yes |
| `conflict` | `errors.CONTROL_STATUS` | 409 | yes |
| `could_not_determine` | `OPERATION_ERROR_CODES` | — | **no** |
| `factor_enabled` | `errors.CONTROL_STATUS` | 409 | yes |
| `human_session_required` | `errors.CONTROL_STATUS` | 403 | yes |
| `interrupted` | `OPERATION_ERROR_CODES` | — | **no** |
| `invalid_request` | generic, `OPERATION_ERROR_CODES` | 422 | yes |
| `invitation_invalid` | `errors.CONTROL_STATUS` | 401 | yes |
| `last_owner` | `errors.CONTROL_STATUS` | 409 | **no** |
| `malformed_request` | generic | 400 | **no** |
| `not_available` | `errors.CONTROL_STATUS` | 409 | yes |
| `not_found` | `errors.CONTROL_STATUS` | 404 | yes |
| `operation_failed` | `OPERATION_ERROR_CODES` | — | **no** |
| `plan_limit_reached` | `errors.CONTROL_STATUS` | 409 | yes |
| `second_factor_invalid` | `errors.CONTROL_STATUS` | 401 | yes |
| `second_factor_required` | `errors.CONTROL_STATUS` | 403 | yes |
| `username_taken` | `errors.CONTROL_STATUS` | 409 | yes |

Console-only words (the page's own): `console_unconfigured`.
Error documents the control modules never use (the agent plane's, not `/v1`'s): `approval_already_decided`, `approval_expired`, `approver_is_owner`, `no_such_workflow`, `object_state_conflict`, `object_unavailable`, `scope_not_held`.
**Missing from `REFUSALS`: 5 of 20.** None of the 16 entries names a next action.

## 2. The relay's close codes (ADR 0286)

| Constant | Code | Worded in `sql.js` |
|---|---|---|
| `CLOSE_TEXT_FRAME` | 4400 | yes |
| `CLOSE_TIME` | 4408 | yes |
| `CLOSE_TOO_MUCH` | 4413 | yes |
| `CLOSE_CEILING` | 4429 | yes |
| `CLOSE_UNREACHABLE` | 4502 | yes |

Also seen by the page: 1000 (normal), 1006 (`pg.js`'s own, a failed socket), 1011 (the relay failed).

## 3. Operation types and their steps (`reconciler_dispatch.STEPS`)

| Type | Steps (progress %) |
|---|---|
| `project.create` | allocate (10) → admit (10) → deploy-1 (30) → admin (40) → ports (60) → deploy-2 (60) → unit (70) → backup (90) → registry (90) |
| `project.sleep` | schedule (10) → unit (30) → stop (60) |
| `project.wake` | start (10) → unit (60) → schedule (90) |
| `project.resize` | admit (10) → deploy (30) → registry (90) |
| `project.export` | dump (10) → upload (60) |
| `project.delete` | retire (10) → tombstone (80) → registry (90) |
| `credential.rotate` | check (10) → alter (40) → sync (70) |
| `branch.create` | check (10) → runtime (20) → record (95) |
| `restore.create` | check (10) → runtime (20) → record (95) |
| `branch.reset` | check (10) → runtime (20) → record (95) |
| `branch.delete` | check (10) → runtime (30) → record (95) |

`project.create`'s only per-step measurement (slot6-prod, 1.20.0, `capacity.ENVELOPE`):

| Step | Progress | Seconds | Share |
|---|---|---|---|
| allocate | 10 % | 1.0 | 0.1% |
| admit | 10 % | 0.8 | 0.1% |
| deploy-1 | 30 % | 63.8 | 4.7% |
| admin | 40 % | 1.4 | 0.1% |
| ports | 60 % | 1.4 | 0.1% |
| deploy-2 | 60 % | 41.2 | 3.0% |
| unit | 70 % | 0.9 | 0.1% |
| backup | 90 % | 1,259.1 | 91.9% |
| registry | 90 % | 0.2 | 0.0% |

Total 1,369.8 s. The progress number reads 90 % for 92% of the creation — the person's *"backup (90%)"*.

## 4. The views (`pages.json`)

| View | Path | Ledger rows | Calls |
|---|---|---|---|
| `accept` | `/accept` | accounts, organizations | 6: `GET /v1/me`; `POST /v1/invitations/accept`; `POST /v1/sessions`; `POST /v1/sessions/refresh`; `POST /v1/me/totp`; `POST /v1/me/totp/confirm` |
| `sign-in` | `/console/#/sign-in` | accounts | 3: `POST /v1/sessions`; `POST /v1/sessions/refresh`; `DELETE /v1/sessions/current` |
| `overview` | `/console/#/` | accounts, organizations, projects_self_service, management_api | 5: `GET /v1/me`; `GET /v1/organizations`; `GET /v1/projects`; `POST /v1/me/totp`; `POST /v1/me/totp/confirm` |
| `new-organization` | `/console/#/new` | organizations | 1: `POST /v1/organizations` |
| `new-project` | `/console/#/org/{organization}/new-project` | projects_self_service | 2: `POST /v1/projects`; `GET /v1/operations/{operation}` |
| `connect` | `/console/#/projects/{key}/connect` | pooled_endpoint, direct_endpoint, postgresql | 3: `GET /v1/projects/{key}/connections`; `POST /v1/projects/{key}/credentials`; `GET /v1/operations/{operation}` |
| `sql-editor` | `/console/#/projects/{key}/sql` | sql_editor, pooled_endpoint, direct_endpoint | 2: `GET /v1/projects/{key}`; `GET /v1/projects/{key}/connections` |
| `branches` | `/console/#/projects/{key}/branches` | branches, restore_to_branch | 6: `GET /v1/projects/{key}/branches`; `POST /v1/projects/{key}/branches`; `POST /v1/projects/{key}/restores`; `POST /v1/projects/{key}/branches/{branch}/reset`; `DELETE /v1/projects/{key}/branches/{branch}`; `GET /v1/operations/{operation}` |
| `backups` | `/console/#/projects/{key}/backups` | backups_and_pitr | 1: `GET /v1/projects/{key}/backups` |
| `project-usage` | `/console/#/projects/{key}/usage` | usage | 1: `GET /v1/projects/{key}/usage` |
| `insights` | `/console/#/projects/{key}/insights` | query_insights | 1: `GET /v1/projects/{key}/insights` |
| `monitoring` | `/console/#/projects/{key}/monitoring` | monitoring | 1: `GET /v1/projects/{key}/monitoring` |
| `project-settings` | `/console/#/projects/{key}/settings` | idle_sleep, compute_profiles, sleep, export, project_deletion, region, support_bundle | 9: `GET /v1/projects/{key}`; `PUT /v1/projects/{key}/idle-sleep`; `PUT /v1/projects/{key}/compute`; `POST /v1/projects/{key}/sleep`; `POST /v1/projects/{key}/wake`; `POST /v1/projects/{key}/export`; `DELETE /v1/projects/{key}`; `GET /v1/operations/{operation}`; `GET /v1/projects/{key}/diagnostics` |
| `plan` | `/console/#/org/{organization}/plan` | plan_free, plan_premium | 3: `GET /v1/plans`; `GET /v1/organizations/{organization}/plan`; `POST /v1/organizations/{organization}/plan-interest` |
| `organization-usage` | `/console/#/org/{organization}/usage` | usage | 1: `GET /v1/organizations/{organization}/usage` |
| `notifications` | `/console/#/org/{organization}/notifications` | notifications | 1: `GET /v1/organizations/{organization}/notifications` |
| `organization-settings` | `/console/#/org/{organization}/settings` | organizations, api_keys, accounts | 9: `GET /v1/organizations/{organization}/members`; `PATCH /v1/organizations/{organization}/members/{user}`; `DELETE /v1/organizations/{organization}/members/{user}`; `POST /v1/invitations`; `GET /v1/organizations/{organization}/invitations`; `DELETE /v1/organizations/{organization}/invitations/{invitation}`; `GET /v1/organizations/{organization}/keys`; `POST /v1/organizations/{organization}/keys`; `DELETE /v1/organizations/{organization}/keys/{key_id}` |

17 views, 45 distinct calls. `GET /v1/operations` (the organisation's list) called by none: confirmed.
