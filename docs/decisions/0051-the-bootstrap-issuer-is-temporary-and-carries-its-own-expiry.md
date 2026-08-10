# 0051 — The bootstrap issuer is temporary, asymmetric, and carries its own expiry

Status: accepted
Date: 2026-08-10
Session: 5, Run 1
Generalises: [0046](0046-a-nologin-stub-is-a-fact-with-an-expiry-date.md)
Affects: SEC-BOOT-001, SEC-ROLE-001, SEC-JWT-001, SEC-KEY-001

## Context

PostgREST switches role from a verified JWT. Session 6 introduces the auth
service that issues those tokens; Session 5 has to verify them a session before
anything can sign them legitimately.

The temptation is a shared secret: one HMAC key in PostgREST's configuration,
one in the token helper, done in an afternoon. It is also the shape that cannot
be taken back, because a verifier holding a symmetric key can mint tokens, and
by Session 6 that verifier is a public HTTP service.

There is a second problem, and it is the one this repository has already been
bitten by twice. A temporary mechanism that works does not announce when it
stops being temporary. ADR 0046 named the pattern for roles — a NOLOGIN stub is
a fact with an expiry date — and ADR 0047 generalised it: an absence proof is a
proxy that is equivalent only while the feature does not exist. A bootstrap
issuer is the same shape wearing a third hat: correct in Session 5, a private
signing key sitting beside a public API in Session 7 if nobody removes it.

## Decision

**Asymmetric from the first token, and the temporariness is recorded as state
rather than remembered.**

- Exactly one active RSA private signing key per project, held only by
  root-controlled tooling. It is mounted into no service, printed by no command,
  and passed as no argument.
- PostgREST receives a **verification-only** JWKS. Generation refuses any public
  key carrying `d`, `p`, `q`, `dp`, `dq`, `qi` or `oth`, and the refusal is
  asserted against a deliberately malformed input rather than trusted.
- `kid` is the RFC 7638 thumbprint of the public key. Random, supplied or
  duplicated `kid` values are refused, so the identifier is derived from the key
  rather than chosen beside it.
- Issuer, audience and key material are distinct per project. Reuse across two
  projects is refused.
- Token lifetime is bounded and small; there is no refresh token and no HTTP
  issuance endpoint.
- The helper issues tokens only for named fixtures, the documentation role, and
  explicitly authorized diagnostics. It refuses an arbitrary role string, a
  scope outside the role's permitted set (ADR 0049), a lifetime above the
  configured maximum, and any request to export the private key.

**The deployed document records `temporary: true`, the active `kid`, the
verification `kid` set, and — during a rotation — the retirement deadline.**
Rotation is two-phase: publish old and new verification keys and switch signing;
after `max_token_ttl + clock_skew`, publish only the new key. The deadline lives
in the document because a half-completed rotation must be visible to a reader
who was not present for the first phase.

**Session 6's gate is what retires it**, and the requirement that says so is
`SEC-BOOT-001` — a Session 5 requirement written so that Session 6 makes it
fail. Not "the issuer is absent", which would be false the moment Session 6
starts work, but "the deployed document's issuer record agrees with the session
the deployment was made through": temporary through Session 5, retired from
Session 6 onward. It goes red on the deployment that should have replaced it.

## Consequences

**Session 5 creates no token-validation or key-separation requirement ID.**
`SEC-JWT-001` and `SEC-KEY-001` are Session 6's, about the production issuer,
and duplicating them here would give two requirements one meaning — the call
D47 made when it dropped `API-DB-001` against `SEC-VIEW-001`. Session 5's
negative matrix is proved under `SEC-ROLE-001` and `SEC-ANON-001`; the key
separation of the *temporary* issuer is `SEC-BOOT-001`, which Session 6 retires
rather than inherits.

**PostgREST never holds signing authority, in this session or any later one.**
The boundary Session 6 must preserve is established before there is anything to
preserve it from, which is cheaper than establishing it afterwards.

**A rotation is provable in both directions.** Phase one proves an old unexpired
token still verifies; phase two proves it no longer does. Each is a declared
event admitted by a flag and written to refuse a false declaration (D121) —
a claim over a rotation would be permanently green after the first window, which
is this project's signature defect with a long fuse.

**RSA rather than Ed25519** is a version-driven choice, not a cryptographic
preference, and it is measured: Run 1 records which algorithms the locked
PostgREST accepts in a JWKS. If it accepts EdDSA the choice is revisited with
that measurement in hand rather than by argument.

## Alternatives considered

**A shared HMAC secret until Session 6.** Rejected. It makes the verifier a
potential issuer, and the verifier becomes a public HTTP service in this very
session. It is also the option that is hardest to withdraw, because withdrawing
it changes both ends at once with no overlap window available.

**No issuer at all: fixtures set the role through a database GUC.** Rejected: it
would prove RLS through HTTP without proving that HTTP *authorization* works,
which is the actual new surface. It would also leave the pre-request claim
validation with nothing to validate, so the code Session 6 depends on would ship
unexecuted.

**Mark the issuer temporary in a comment and rely on Session 6 to remember.**
Rejected — this is exactly the failure ADR 0046 and ADR 0047 were written about,
twice, in one run. A fact with an expiry date belongs in state that something
reads, not in prose that nothing does.
