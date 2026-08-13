# 0078 — The claim contract, and what each of its two verifiers enforces

Status: accepted
Date: 2026-08-13
Session: 6, Run 3
Affects: SEC-JWT-001, API-AUTH-002

## Context

The Session 6 runbook says a "final-shaped JWT claim contract" was frozen in
Session 5 with ten required claims, and that Session 6 adds two as a documented
versioned extension.

**Measured in `bin/dev-token.py::mint` and `migrations/templates/0010`: there is
no contract.** A bootstrap token carries `role`, `iat`, `exp`, `iss`, `aud`, and
`sub` only for non-documentation roles. The pre-request hook reads `sub`,
shape-checks it as a UUID, and sets `app.user_id`; it reads nothing else. There
is no `scope`, no `token_use`, no `jti` and no `nbf` anywhere in the system, and
`scope` has never been signed, published or verified (D219).

So this is the first contract, not an extension — which changes the size of the
work and is why it gets an ADR with alternatives.

Two things then had to be measured before the shape could be chosen, because the
contract has **two verifiers** — the auth service, and the database's pre-request
hook — and PostgREST sits between them deciding what ever arrives.

### What the locked PostgREST does with a token

Rig: `postgres:pg18` and `postgrest:v14.16`, both at their locked digests, with a
function returning `current_setting('request.jwt.claims', true)` verbatim.
Controls throughout: a baseline token served in the same run, and a second token
carrying none of the claims under test.

**Delivery.** Every claim survives to `request.jwt.claims` unchanged, including
`scope` as a real JSON **array** and the two version claims as integers. The
control confirms the observation reflects the token: claims absent from the token
are absent from the payload.

**Enforcement**, and this is where the assumptions were wrong:

| | |
|---|---|
| signature | refused for another key, `alg: none`, and HS256 (401) |
| `exp` | refused **more than 30s** past expiry |
| `nbf` | refused **more than 30s** before validity |
| `aud` | refused when **present** and wrong — and **served when absent** |
| `kid` | refused when present and unmatched; **served when absent** |
| `role` | refused at `SET ROLE` without membership (403, 42501) |
| **`iss`** | **not checked at all.** PostgREST has no issuer setting |
| `typ`, `token_use`, `scope` | delivered, never inspected |

The 30-second leeway is a bisect, not an estimate: 30s past `exp` is served and
31s is refused, symmetrically for `nbf`.

**The first pass of this measurement was wrong**, and how it was wrong is worth
recording. It left `PGRST_JWT_AUD` unset, so it reported that a wrong audience is
served — a fact about a rig nobody deploys. `compose.yaml` sets it. That is ADR
0065's rule arriving for the fourth time: *a rig is a second configuration of the
product*, and the honest version of this measurement is the one configured from
the product's own file.

## Decision

**One authority for the shape, in `src/agentic_postgres/jwt_claims.py`**, and
twelve required claims:

    iss aud sub role scope token_use jti iat nbf exp
    credential_version authz_version

The service verifies with PyJWT plus `verify_claims`, a pure function. The hook
verifies its half in SQL, rendered from `sql_required_claims()` rather than
typed into the migration — because a contract spelled twice is a contract that
drifts, and D177 watched precisely that happen to a URL where the copy carrying
a comment saying it was kept in step was the one that had drifted.

**The measured division decides what each verifier must do**, rather than a
general instinct to check everything twice:

- **`iss` is checked by us, always**, because nothing in PostgREST ever will.
- **`aud` is checked for presence as well as value**, because PostgREST checks
  only the value and only when there is one.
- `typ`, `token_use` and the two version claims are ours by the same argument.
- `scope` is asserted to be a sorted, deduplicated array of strings. PostgREST
  serves a space-delimited string just as happily, so the *shape* is a check and
  not an assumption.
- `exp` and `nbf` are checked by both, and ours uses the same 30-second leeway —
  a verifier stricter than the one downstream would refuse tokens the deployment
  still honours, and reporting that as an auth failure would send the reader to
  the wrong system.

**`CLOCK_SKEW_SECONDS = 30` is a product input, not a note.**
`jwt_keys.begin_rotation` computes a retirement deadline as
`max_token_ttl + clock_skew`. A rotation using a smaller skew than the verifier
applies would retire a key while tokens it signed were still being served. A
token is live for `MAX_TTL_SECONDS + CLOCK_SKEW_SECONDS`, and that sum is the
blast radius of both a compromised token and a key cutover.

## Alternatives

**Let PostgREST be the verifier.** Rejected on the measurement. It ignores `iss`
entirely and accepts a token with no `aud`, so a token from any issuer holding
the right key is served. Key material is per-project, so this is not a live
cross-project hole today — but it becomes one the moment a single issuer signs
for more than one audience, which is exactly what Session 6 builds.

**Put the whole contract in the hook.** Rejected: the service must refuse a bad
token at `/auth/me` and before it mints, where there is no database request in
flight. The hook cannot be the only verifier of something the service acts on.

**Write the claim list in both places, carefully.** Rejected by name. That is
the D177 shape, and this repository has never once won that bet.

**Adopt the runbook's ten claims and add two.** Rejected because the premise is
false — there is nothing to add to. The set here is the runbook's plus `role`
and the two versions, chosen as one contract rather than assembled from an
inheritance that does not exist.

## Consequences

- `bin/dev-token.py` and the hook both become consumers of this module rather
  than authorities. Migration 0012 renders `sql_required_claims()`.
- **A token is live for up to 930 seconds**, not 900. Anything that reasons about
  token lifetime — rotation windows, revocation latency, the non-resurrection
  proof — reads `MAX_TTL_SECONDS + CLOCK_SKEW_SECONDS`.
- The negative matrix in `SEC-JWT-001` has a measured expectation for every row,
  including the rows where the correct expectation is *served* — a proof that
  asserts PostgREST refuses a bad `iss` would be asserting something false.
- `POSTGREST_ENFORCES` and `VERIFIED_ELSEWHERE` are data in the module, so the
  division is testable rather than a paragraph. If a later PostgREST starts
  checking `iss`, the row is what a reader compares against.
- **Not decided here:** the scope vocabulary. D220 puts new scope *names* in
  `schemas/capabilities.schema.json`, which ADR 0006 makes the sole authority and
  ADR 0003 governs — that is a second decision touching two earlier ones, and it
  gets its own record rather than riding along inside this one.
