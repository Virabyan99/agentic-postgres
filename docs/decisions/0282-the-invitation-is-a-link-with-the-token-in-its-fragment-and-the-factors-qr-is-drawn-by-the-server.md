# 0282 — The invitation is a link with the token in its fragment, and the factor's QR is drawn by the server

- **Status:** Accepted
- **Date:** 2026-10-19
- **Session:** 43, Run 1 (`docs/plans/session-43-implementation-plan.md`,
  D2657, D2658, D2659, D2682; rig 43b)
- **Affects:** `POST /v1/invitations` (`InvitationResponse` gains
  `accept_url`), `POST /v1/me/totp` (`FactorEnrolmentResponse` gains
  `otpauth_qr`), `naming.console_origin()` and the rendered
  `APG_CONSOLE_ORIGIN` (control project only), `bin/cloud.py` (`org invite
  --output` writes the link; `read_invitation` reads a token or a link), the
  console's `accept.html` and onboarding page (Runs 3–5), the auth image's
  dependency lock (`segno`). Requirements `CON-INVITE-001`, `CON-FACTOR-001`.
- **Related:** ADR 0171 (a deterministic token digest), ADR 0252 (accounts
  and TOTP), ADR 0280 (the console), ADR 0281 (the console's session), D1951
  (no email system), D2591 points 3–4, D2596 (no third-party script).

## Context

An invitation today is a bare 43-character token that the inviter carries to
the invitee by hand, and a TOTP factor is enrolled by printing an `otpauth://`
URI that the operator guide pipes into `qrencode`. Session 43 moves both into
the browser (D2591): the invitee follows a link and enrols the factor from a
page. Two questions follow. Where in the link does the token sit, so that no
server, proxy or log ever receives it? And who draws the QR code, given that
D2596 refuses third-party scripts and an encoder written here would be an
unreviewed one that a phone must still read?

## Measured

Rig 43b (2026-10-19, WSL `~/s43/rigs/43b/`, `~/s43/rigs/43b.txt`):

- `segno` **1.6.6** (2025-03-12, the newest release; well past 14 days), *"OSI
  Approved :: BSD License"* (its classifier; the `license` metadata fields are
  empty). `requires_dist` is only `importlib-metadata>=3.6.0; python_version <
  "3.10"`, so it has **no dependency** on 3.12. Wheel
  `segno-1.6.6-py3-none-any.whl` sha256
  `28c7d081ed0cf935e0411293a465efd4d500704072cdb039778a2ab8736190c7`.
- In `PYTHON_RUNTIME_IMAGE` (`python:3.12-slim@sha256:229a2c5b…`),
  `segno.make(uri, error="m").svg_data_uri(scale=4)` for the fixture
  `otpauth://totp/agentic-postgres:rig?secret=JBSWY3DPEHPK3PXP&issuer=agentic-postgres&period=30&digits=6&algorithm=SHA1`
  gives a 4,407-byte `data:image/svg+xml;charset=utf-8,…` URI with no
  `<script` and no `href`. Its only `http` is the SVG namespace
  (`xmlns='http://www.w3.org/2000/svg'`), which is a name and not a fetch.
- Rasterised by `rsvg-convert` and decoded by `zbarimg` in `debian:stable-slim`,
  **the default SVG decodes to nothing**: segno draws the dark modules on a
  transparent background, and a transparent PNG reads as all dark. With
  `rsvg-convert -b white` it decodes **exactly to the URI**, and the control (a
  URI one character different) decodes to itself. With
  **`svg_data_uri(scale=4, light="white")`** it decodes exactly with no
  rasteriser help, and the default does not (the control) — D2682.

## Decision

1. **The invitation is a link whose token is in the fragment**:
   `{APG_CONSOLE_ORIGIN}/accept#{token}`. `APG_CONSOLE_ORIGIN` is
   `https://<PROJECT_DOMAIN>`, derived once by `naming.console_origin()` and
   rendered for the control project only (ADR 0002). The mint answer keeps
   `invitation_token` and gains `accept_url`.
2. **The CLI carries the link**: `apg org invite --output FILE` writes the
   link (one whitespace-free line, 0600). `apg login accept --invitation-file`
   reads either a bare token or a link whose path is `/accept` and whose
   fragment is the token. Anything else is refused with the existing message.
3. **The accept page removes the fragment before its first request**
   (`history.replaceState(null, "", "/accept")`), then posts the token in the
   JSON body of `POST /v1/invitations/accept`. The console's
   `Referrer-Policy: no-referrer` and the edge's baseline say the same. No log
   line holds the token, and a test proves it by capturing the app's request
   log through a mint and an accept.
4. **The token is stored as it is today**: a deterministic SHA-256 of 32
   random bytes, found by its digest (ADR 0171). The stage plan's *"Argon2id
   for keys and invitations"* is wrong about the tree and is corrected here,
   not implemented (D2658). Argon2id hashes passwords, which are the secrets
   people choose.
5. **The QR is drawn by the server.** `FactorEnrolmentResponse` gains
   `otpauth_qr`: `segno.make(otpauth_uri, error="m").svg_data_uri(scale=4,
   light="white")`. The light background is part of the image, so it reads on
   any page colour (D2682). `segno==1.6.6` is pinned and hash-locked into the
   auth image. The page shows `<img src="{otpauth_qr}">` (the console's CSP
   allows `img-src 'self' data:`, ADR 0280) with the base32 `secret` under it,
   and drops both from memory once the factor is confirmed. The CLI may ignore
   the member.
6. **The guard on the image** asserts it references nothing. It holds no
   `<script`, no `href`, and no URL other than the SVG namespace.

## Alternatives

- **The token in the query string** (`/accept?token=…`): it would arrive in
  the edge's request line, in any proxy between, and in a `Referer` that a
  policy failed to strip. Rejected.
- **The token in the path**: the same as the query string, and it would also
  turn a route rule into a token matcher. Rejected.
- **A QR encoder in the page**: either vendored (a third-party script, refused
  by D2596) or written here (an encoder nobody has reviewed and that a phone
  must read). Rejected. The server already holds the seed, and the enrolment
  answer already carries it once.
- **No QR (the base32 text only)**: it works, and the page still shows the
  text, but typing 32 characters into a phone is the step people get wrong.
  Kept as the fallback beside the image, not as the only path.

## Consequences

- A link copied into a chat, a ticket or an email still carries the token, and
  whoever holds the link before it is used holds the invitation, exactly as
  with the bare token today (threat-model hosted item 18). The default lifetime
  stays 72 hours, single use.
- The enrolment answer, already shown once, now carries the seed in three
  forms (secret, URI, image). It gains no new holder.
- A customer whose console origin changes (a new `PROJECT_DOMAIN`) gets links
  for the new origin; links minted before point at the old one and fail closed.
