# 0281 — The console's session is a pair of `__Host-` cookies, chosen per request by a header, and a write needs the console's `Origin`

- **Status:** Accepted
- **Date:** 2026-10-19
- **Session:** 43, Run 1 (`docs/plans/session-43-implementation-plan.md`,
  D2656, D2678, D2679; rig 43a)
- **Affects:** `services/auth-api/app/control_routes.py` (`POST /v1/sessions`,
  `POST /v1/sessions/refresh`, `DELETE /v1/sessions/current`, `_caller`), the
  rendered `APG_CONSOLE_ORIGIN` (control project only, ADR 0282), the
  console's pages (ADR 0280). Requirements `CON-SESSION-001`, `CON-CSRF-001`,
  `CON-LIVE-002`.
- **Related:** ADR 0205 (Studio's launch cookie and its header check), ADR 0249
  (the request log), ADR 0252 (accounts, sessions, TOTP), ADR 0253 (keys),
  ADR 0280 (the console), D2595 (the operator's choice of cookie), D2166 (no
  throttle on the session routes).

## Context

A control session is two tokens: a 15-minute RS256 access JWT and a 30-day,
single-use, rotated refresh token stored as its SHA-256 digest. The CLI holds
both in a 0600 file and sends the access token as `Authorization: Bearer`. The
console runs in a browser. D2595 decided that the browser holds the session
in an `HttpOnly`, `Secure`, `SameSite=Strict` cookie, set by the session route
for the console, with every write also checking `Origin` or a header only the
console's own pages send. Nothing in `control_routes.py` sets or reads a
cookie, checks `Origin`, or answers CORS. A browser decides what a cookie
does, so what the browser does had to be read, not assumed.

## Measured

Rig 43a (2026-10-19, WSL `~/s43/rigs/43a/`, `~/s43/rigs/43a.txt`; the
Playwright image of ADR 0280, Chromium **153.0.8010.12** headless). Origin A,
`https://127.0.0.1:18443`, set two cookies: `__Host-a=1; HttpOnly; Secure;
SameSite=Strict; Path=/` (the subject) and `__Host-lax=1` with
`SameSite=Lax` (the control). Origin B, `https://localhost:18444`, is another
site. Every request A received was logged, and A answered `OPTIONS` with 405
and no `Access-Control-*` header.

1. A's own page `fetch`ing `/echo` with `X-Apg-Console: 1` (POST): both
   cookies arrived, with the header and with **`Origin:
   https://127.0.0.1:18443`**. Chromium sends `Origin` on a same-origin POST.
2. B's page `fetch`ing A's `/echo` with the header and `credentials:
   "include"`: **only the preflight `OPTIONS` arrived**, carrying no cookie and
   no header. The POST was never sent, and the page saw `TypeError: Failed to
   fetch`.
3. B's page auto-submitting a `<form method=post>` to A: the POST arrived
   **with no cookie at all** (`Origin: https://localhost:18444`).
4. A link on B clicked through to A (a top-level GET navigation): **`__Host-lax`
   arrived and `__Host-a` did not**. This is the control: Lax rides a
   cross-site navigation and Strict does not.
5. `document.cookie` on A read `""`.
6. `crypto.subtle` PBKDF2-HMAC-SHA-256, 4,096 iterations, of a fixed password
   and a 16-byte salt, equals `hashlib.pbkdf2_hmac`
   (`4b041b5f2becccb8bf81e15273051dcd1a1ad9435c6714ad7fe08648717ea608`). The
   control, 4,095 iterations, differs. (ADR 0280's `scram.js` rests on this.)

## Decision

1. **Cookie mode is chosen per request by `X-Apg-Console: 1`.**
   `POST /v1/sessions` and `POST /v1/sessions/refresh` with the header set
   `__Host-apg_access` (the JWT; `Max-Age` = `expires_at − now`) and
   `__Host-apg_refresh` (`Max-Age` 2,592,000), both `HttpOnly; Secure;
   SameSite=Strict; Path=/`. They answer `{"expires_at", "token_use"}`, **with
   no token in the body**. `/refresh` with the header reads the refresh token
   from its cookie when the body is empty. `DELETE /v1/sessions/current` with
   the header reads it from the cookie and **clears both** (`Max-Age=0`).
2. **`_caller`'s precedence.** If an `Authorization` header is present, the
   request is bearer mode and cookies are ignored (the CLI and API keys are
   unchanged). If there is no `Authorization` header and `__Host-apg_access`
   is present, it is accepted **only** when `X-Apg-Console: 1` is present
   **and**, for every method but `GET` and `HEAD`, `Origin` equals
   `APG_CONSOLE_ORIGIN` exactly. Anything else is the `401` it is today. A
   cookie value beginning `apg_` is refused, because a key never rides a
   cookie.
3. **No CORS is added.** The custom header makes any cross-origin request
   preflighted, and no route answers a preflight (reading 2). `SameSite=Strict`
   keeps the cookies off a cross-site form or navigation (readings 3 and 4).
   The `Origin` check refuses a write even if both of those failed.
4. **Nothing logs a cookie.** The edge's access log already drops `Cookie`
   (`infra/edge/traefik.yaml`). The request log records method, route, status
   and elapsed time only (ADR 0249), and the console server logs path without
   query (ADR 0280). A test sends both cookies through the app and finds
   neither value in any captured line (D2678).
5. **The lifetimes are the session's own.** The access cookie expires with the
   JWT. The refresh cookie lives 30 days, single use and rotated as today.
   Confirming a factor ends every refresh family (`control_service.py`), so it
   ends the console's session too, and the onboarding page logs in again with
   the code.

## Alternatives

- **The token in `localStorage` or page memory, sent as `Authorization`**:
  any script that runs in the page can read it. Session 44 puts a database
  password in this page. Rejected (D2595).
- **`SameSite=Lax`**: reading 4 shows Lax riding a cross-site navigation. The
  console never needs a cookie on an arrival from elsewhere: its pages are
  static and fetch the session after load. Rejected.
- **A CSRF token in a second, readable cookie (double submit)**: it needs a
  value a script can read, and buys nothing over a custom header that the
  browser refuses to send cross-origin without a preflight. Rejected.
- **Cookies for every caller**: it would change the CLI and keys for no gain,
  and a key in a cookie would be a key a browser sends. Rejected; bearer wins.

## Consequences

- No script on the page, injected or not, can read the session (reading 5).
  A script injected into the console could still make requests as the user,
  so ADR 0280's Content-Security-Policy is this decision's other half.
- Signing out of one browser ends that refresh family only. "Sign out
  everywhere" is the existing factor-confirm behaviour, not a button.
- The guessing exposure at `/v1/sessions` is unchanged (threat-model hosted
  item 21, D2679): the edge's per-source limit, Argon2id for the password, and
  10⁶ codes per TOTP window.
