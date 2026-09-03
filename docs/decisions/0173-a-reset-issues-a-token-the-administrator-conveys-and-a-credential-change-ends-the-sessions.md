# 0173 — A reset issues a token the administrator conveys, and a credential change ends the sessions

- **Status:** accepted
- **Date:** 2026-09-03
- **Session:** 15, Run 5 (`IDN-RESET-001`, D844–D848)
- **Related:** **D813** (the session plane, and why a credential outliving it
  matters), **D837** (`auth_revoke_user_sessions` was written a run early and
  removed for having no caller), **D844** (an administrator could already set a
  password, and therefore knew it), **D845** (`credential_version` does not
  reach the refresh plane), ADR 0078 (`credential_version`, the existing
  revocation mechanism), ADR 0171 (the single-use token primitive and its
  deterministic digest), ADR 0002 (one derivation per value), 0012 (which owns
  `auth_set_password`).

## Context

The plan asks for a reset in which **the administrator never learns the
password**. Measured against the tree first, because the phrase implies
something the deployment does not currently have:

**An administrator can already set a password** (D844). `PATCH
/admin/users/{user_id}` has accepted a `password` member since Session 6, and an
administrator using it chooses the value — so they know it, and they can log in
as that subject afterwards. That surface is not a defect: **somebody has to set
the first password**, and provisioning is exactly what it is for.

It is the wrong operation for *recovery*. The ordinary case — "this person
cannot get in" — should not end with an operator holding a credential that opens
somebody else's account, and it should not require them to invent a value and
convey it.

**And `credential_version` does not finish the job** (D845). It moves on a
password change and refuses every *access* token issued before it, which is
0012's design and `SEC-REV-001`'s mechanism. But Session 15 Run 2 added a refresh
plane, and **a refresh token names a session rather than a credential** — so a
chain obtained with the old password would keep minting access tokens after the
password changed. The reset would look complete and leave a live way in.

## Decision

### 1. A reset issues a token; the subject chooses the password

`POST /admin/users/{user_id}/reset-password` returns a one-time token and no
password, because none exists yet. The administrator conveys it out of band, and
`POST /auth/reset-password` is where the subject spends it and names their own
credential.

**What the administrator gets is a way in, not a way to know.** The residual is
stated rather than implied: an administrator who issues a reset *could* spend it
themselves and set a password of their choosing. That is inherent to any
administrator-initiated recovery, and it is not new — the same role can already
set a password directly, disable an account, or change its scopes. **What changes
is that the ordinary path no longer requires it**, and a reset that was spent by
the administrator is distinguishable afterwards from one the subject spent,
because the subject knows what they chose and the administrator does not.

### 2. The reset is unauthenticated, and single-use

`/auth/reset-password` carries no bearer requirement, for the reason
`/auth/refresh` does not (D834): **a recovery that required a live session would
work only for callers who did not need it.** The token is the credential.

Single-use, hashed as a hex SHA-256, and expiring — the same three properties a
refresh token has, and for the same reasons. **The primitive is shared**: `mint`,
`hash_token` and `is_wellformed` moved to `app.one_time_tokens` rather than being
copied, because two implementations of one value is what ADR 0002 exists to
prevent and the second one is always slightly weaker with nothing comparing them.

**One hour, not thirty days.** A refresh token is held by the subject who earned
it; a reset token is **in transit** between two people through whatever channel
the deployment uses, and the window is the time it spends somewhere neither of
them controls.

**At most one live reset per subject.** Two outstanding resets means two values
open the account and neither presentation looks unusual. Issuing a second
supersedes the first explicitly in SQL, rather than letting the partial unique
index answer `23505` about a state the administrator cannot see.

### 3. Spending a reset ends every session the subject has

`auth_consume_password_reset` sets the password, moves `credential_version`
through 0012's own function, and calls `auth_revoke_user_sessions` with
`credential_changed` — **all in one transaction.**

Splitting them would leave an interval in which the password had changed and a
chain obtained with the old one still minted access tokens. **Detection and
response, or in this case change and revocation, are one transaction or they are
a promise** — the same argument ADR 0171 makes for revoking a family on reuse.

`auth_set_password` is *called*, not restated: `credential_version` has one
writer and this is not a second one (ADR 0002).

**`auth_revoke_user_sessions` is not granted to the auth service.** Its only
caller is inside another function, so it needs no grant — and a grant the service
does not need is a capability it does not hold. This is also where D837 lands:
the function was written in Run 3, removed before it shipped for having no
caller, and this is the run where the caller exists.

### 4. Issuing a reset changes nothing

No credential moves and no session ends when a reset is *issued*. An
administrator who needs a subject out **now** disables the account, which is a
different act with a different record and a different reversal.

Making issuance revoke would conflate two intentions — "help this person back
in" and "stop this person now" — and an operator doing the first would silently
perform the second, logging out a subject who had merely forgotten a password.

### 5. The password is screened before the token is spent

A weak password is refused *before* the reset is consumed. Reversed, a subject
who chose one would hold a spent token and an unchanged credential: unable to log
in and unable to reset, which is a worse outcome than the refusal it came from.

## Consequences

- **Every refusal on the spend path answers identically** — spent, unknown and
  malformed — for `login`'s reason. A reset token names an account somebody may
  be trying to take over, and distinguishing the causes would say whether a
  guessed value named something real.
- **The direct password set remains**, and the two are now distinguishable in
  the record: a direct set moves `credential_version` and leaves the refresh
  chains alone; a reset moves it and ends them. That asymmetry is worth knowing
  and is not itself a decision — it falls out of the direct set predating the
  session plane. **Whether `PATCH … {"password"}` should also end sessions is
  open**, and belongs with whoever can say whether provisioning should log
  anybody out.
- **`issued_by` is recorded with `ON DELETE RESTRICT`.** An unattributable reset
  is indistinguishable from a compromise, and deleting an administrator must not
  quietly erase who reset whose password.
- **Nothing prunes spent resets**, exactly as nothing prunes consumed refresh
  tokens or `app_private.agent_audit`. They are the record of who arranged which
  recovery.
