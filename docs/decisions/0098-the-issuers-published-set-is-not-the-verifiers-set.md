# 0098 — The issuer's published set is not the verifier's set

Status: accepted
Date: 2026-08-15
Session: 6, Run 14
Affects: ADR 0051, ADR 0088, ADR 0094, D276, D304,
`tests/deployment/test_session6_tokens.py`,
`tests/deployment/test_session6_isolation.py`

## Context

Two Session 6 proofs assert that what `GET /auth/jwks.json` serves equals what
`jwt.verification_kids` records. Both failed the first time they ran, on both
projects, and the reason is that the two documents answer different questions:

* `GET /auth/jwks.json` is served by `services/auth-api/app/keys.py`, which
  returns `{"keys": [self.public_jwk]}` — **the one key this service signs
  with**. It is the *issuer's* statement about itself.
* `jwt.verification_kids` comes from the rendered `jwks.json` that
  `render-jwks.py` writes, which holds **every live issuer's key** — the auth
  service's and the bootstrap issuer's. It is the *verifier's* configuration.

While one issuer existed those were the same list. Session 6 created the second
issuer, and D276's fix put its key in the verifier's file — so the sets diverged
in the same run that made the second issuer real, and no proof had run since.

## What was measured

On alpha-dev and beta-dev, through the deployed route and the deployed document:

| reading | alpha-dev | beta-dev |
|---|---|---|
| `GET /auth/jwks.json` | 1 key | `['IlFWmP6x…']` |
| `jwt.verification_kids` | 2 keys | `['IlFWmP6x…', 'tHGY_eIH…']` |

and, from the source, that `keys.py` builds its response from `public_jwk`
alone, with a docstring saying it is built rather than held "so there is no
second copy that could be published after the key changed".

The relationship is therefore **containment, and it is the useful assertion**:
the issuer's own key must be one the verifier will accept, which is exactly
D276's defect stated as a property. Equality is not merely wrong, it is the
weaker statement — it holds trivially while there is one issuer, which is
precisely when nothing needs checking.

## Decision

**The issuer publishes what it signs with; the verifier is configured with every
live issuer's key; the proofs assert `served ⊆ declared` rather than equality.**

`SEC-KEY-002` keeps its subject and gains a sharper one. Its four readings become:

* `jwt.verification_kids`, the rendered file and the bytes **inside the
  PostgREST container** must be equal — that is the verifier's set, read three
  ways, and the third is the one that cannot be inferred (D278);
* `GET /auth/jwks.json` must be a **non-empty subset** of it — the issuer's key
  is one the verifier accepts, which is D276 as a property rather than as a
  memory.

`DEP-ISO-006` asserts that project A's `kid` is absent from **both** of B's
readings, which is stricter than the equality it replaces: the old assertion
could only fail on a set mismatch, and the new one fails if A's key appears in
anything B publishes *or* in anything B verifies.

## Alternatives rejected

**Make `/auth/jwks.json` serve the whole set.** It would have the auth service
publish a key it does not hold, cannot sign with and did not derive — read from
a file written by a different program — and every consumer of that endpoint
would then be told the bootstrap issuer is one of this service's keys. It also
re-creates the exact drift `keys.py` avoids by building its response from the
key it loaded.

**Assert equality and let it start passing after ADR 0051's retirement.** True
and useless: the assertion would be vacuous today, become meaningful at a
retirement nobody has scheduled, and silently pass through the entire window in
which two issuers exist — which is the window it is for.

**Drop the endpoint from the comparison.** It is the only reading that comes
from the issuer rather than from the deploy, and losing it would leave D276
provable only from artifacts the same command wrote.

## Consequences

The proofs now state a relationship that survives a rotation: during a cutover
the verifier's set holds two keys and the issuer publishes one, and containment
holds throughout. Under the old assertion, ADR 0088's own machinery would have
turned both proofs red at the exact moment they were most needed.
