# 0252 — Accounts by invitation, organisations, roles and TOTP

- **Status:** Accepted
- **Date:** 2026-10-04
- **Session:** 37, Run 1 (D2050, D2051, D2053, D2065, D2080, D2081)
- **Affects:** `CTL-TOTP-001`, `CTL-TOTP-002`, `CTL-INV-001`, `CTL-INV-002`,
  `CTL-ROLE-001` (registered by Run 9). `services/auth-api/app/totp.py`,
  `services/auth-api/app/control_roles.py`, the control mode's session,
  invitation, organisation and member routes, `projects/control/migrations/`
  (`control_accounts`, `control_organizations`, `control_memberships`,
  `control_invitations`, `control_totp`), `bin/control.sh totp-reset`,
  `docs/control-plane.md`.
- **Related:** ADR 0251 (the control plane is a project), ADR 0253 (keys),
  ADR 0246 (the hosted boundary; humans are never pruned, D1986), the identity
  registry (migrations 0011, 0012), the refresh plane (0023, 0024), the
  password-reset plane (0026), `one_time_tokens.py`, `docs/threat-model.md`
  hosted items 1, 3, 4 and 16, `docs/plans/stage-5-plan.md` D1951.

## Context

Stage 5 is invite-only (D1951): no signup, no email. A person reaches the
control plane because someone who may invite them minted a single-use token and
handed it over out of band — the shape the password reset already has (shown
once, delivered by hand, stored as a digest). Organisations have four roles and
the two that can change who holds what must present a second factor.

Rig 37a implemented RFC 4226 HOTP and RFC 6238 TOTP over the standard library
(`hmac`, `hashlib`, `struct`) and measured it: all ten RFC 4226 Appendix D
values for counters 0–9, and all six RFC 6238 Appendix B SHA-1 values at eight
digits (T = 59 → `94287082` … T = 20000000000 → `65353130`). With a random
20-byte seed and a window of one step, the codes for now, now − 30 s and now +
30 s were accepted at their own steps; **the controls**: now ± 60 s refused, a
wrong code refused, the same code a second time refused once the accepted step
was recorded, and the next step's code accepted after it. An unpadded base32
seed (32 characters for 20 bytes) round-trips. `oathtool` is not installed on
the workstation, so the RFC vectors are the independent implementation.

Rig 37b measured single use under concurrency: two sessions each running
`UPDATE … SET accepted_at = now() WHERE token_hash = 'x' AND accepted_at IS NULL
RETURNING id` — the second **waited 2.3 s** for the first to commit and then
updated **no row**.

Rig 37e read two facts the plan had assumed. The session-revocation function
`app_private.auth_revoke_user_sessions` is granted to nobody — it is reached
only from inside the password reset's consume function (migration 0026) — and
the refresh path re-reads only the subject's status and re-issues with the
current versions, so moving a version does not end a refresh family (D2080).
And `bin/auth-admin.sh` has two verbs, `bootstrap` and `list`: nothing in the
operator's surface disables a user or resets a password, and `/admin/users` is
not served in `control` mode (D2081).

## Decision

1. **TOTP** (D2050). `services/auth-api/app/totp.py`: HOTP (HMAC-SHA-1,
   dynamic truncation, zero-padded) and TOTP at 30 s steps, **6 digits** in the
   product (8 only for the RFC vectors), compared with `hmac.compare_digest`,
   a window of **±1 step**, **replay refused**: a code is accepted only for a
   step greater than `app.control_totp.last_step`, and the step is recorded in
   the same statement that accepts it. A seed is 20 random bytes, shown ONCE at
   enrolment as an `otpauth://totp/agentic-postgres:<username>?secret=<base32,
   unpadded>&issuer=agentic-postgres&period=30&digits=6&algorithm=SHA1` URI,
   and never logged.
2. **Who must hold a factor, and what they may do without one.** Anyone who
   holds `owner` or `admin` in any organisation, or `admin_users:write` in the
   control project's registry. Such a person without an enabled factor can log
   in and reach only `/v1/me`, `/v1/me/totp*` and `/v1/sessions*`; every other
   `/v1` route answers `403 second_factor_required`. **Login** (`POST
   /v1/sessions`) checks the password first — the existing path, the dummy hash
   for an unknown user — then, if the user has an enabled factor, requires the
   code: `401 second_factor_required` without one, `401 second_factor_invalid`
   with a wrong or replayed one.
3. **Confirming a factor ends every session the user has** (D2080), so no token
   minted without the code outlives enrolment: in the confirming transaction the
   control mode lists the user's sessions with `app_private.auth_list_sessions`
   and revokes each with `app_private.auth_revoke_session` — both already
   granted to `auth_service` (migration 0024). `auth_revoke_user_sessions` is
   not granted; granting it would be a released migration for a loop the
   service can already write. A lost device is the operator's:
   `sudo bin/control.sh totp-reset --username NAME --confirm control-prod`.
4. **Invitations, two kinds in one table** (D2051). An **account invitation**
   (no organisation) is minted by a caller holding `admin_users:write` in the
   control project's registry, with an enabled factor — the operator's bootstrap
   administrator; accepting it creates the account only, and the account may
   then create an organisation, becoming its `owner`. A **membership
   invitation** is minted by an `owner` or `admin` of that organisation for a
   role at or below their own (`admin` invites `admin`, `member`, `viewer`; only
   `owner` invites `owner`); accepting it creates the account if the caller has
   none, and the membership, **in one transaction**. The token is
   `one_time_tokens.mint()` (43 characters, 256 bits), stored only as its
   SHA-256, shown once in the `201` body; its lifetime is **72 h by default and
   at most 168 h**. Acceptance is ONE conditional `UPDATE … RETURNING`, single
   use by construction (rig 37b). **A used, expired, revoked or unknown token
   gets one answer**, `401 {"error":"invitation_invalid"}`, byte-identical; a
   taken username is refused only after the token validated, and the
   transaction rolls back so the token stays unspent.
5. **Accounts** are identity-registry users of the control project, role
   `api_documentation`, scopes `["meta:read"]` (ADR 0251), created through
   `app_private.auth_create_user` by the control mode, with a row in
   `app.control_accounts`.
6. **Roles, in one table** (D2053). `services/auth-api/app/control_roles.py`
   holds the matrix: `viewer` and `member` read the organisation, its members,
   its projects and its operations, and manage their own keys (identical in
   Session 37; Session 38 gives `member` `projects:write`); `admin` adds
   inviting, removing and re-roling `admin`, `member` and `viewer`, and revoking
   any key of the organisation; `owner` adds all of that for `owner`. **The last
   owner cannot be removed or demoted** (`409 last_owner`). Every route names
   the role it needs, and a test walks every `/v1` route against every role.
7. **No account is deleted, pruned or disabled through a product surface in
   Session 37** (D2065, D2081). Probe accounts are named `probe-s37-<8 hex>`,
   and the probe's memberships are removed at the end of each proof — the
   membership is the authority, and an account with none reaches nothing but
   `/v1/me`. Disabling a control account is a root operation on the control
   project's database (`app_private.auth_set_status`, names derived from its
   deployed document), written in `docs/control-plane.md`; D1986's identity
   question stays open.

## Alternatives rejected

- **Requiring the factor at login for everyone.** A new owner could then never
  log in to enrol, and the requirement would be met by locking them out.
- **A third-party TOTP library.** The stage plan forbids a new dependency for
  forty lines the RFCs specify with test vectors.
- **Encrypting the seeds at rest now.** The key would live beside the service
  that must read it; the scheme would add a key to rotate without moving the
  boundary. It is `planned` and named as residual risk.
- **An invitation addressed to an email.** There is no email (D1951); an
  invitation is a bearer token handed over by a person.
- **Granting `auth_revoke_user_sessions` to `auth_service`.** A released
  migration for what two granted functions already do.

## Consequences

- **TOTP seeds are plaintext at rest** in `app.control_totp`, reachable only
  through definer functions granted to `auth_service`; a database dump, or a
  backup read with the cipher pass, reveals every enrolled seed (threat item
  16). This is the residual risk this ADR accepts.
- Probe accounts accumulate with every sweep; deleting an identity joins the
  audit, the sessions and the memberships, and is not this session's question.
- No rate limit guards `/v1/sessions` or acceptance; Argon2id's concurrency of
  two is the only throttle until Session 38 (ADR 0246's scope sentence).
