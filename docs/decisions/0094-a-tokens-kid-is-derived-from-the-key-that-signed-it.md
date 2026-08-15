# 0094 — A token's `kid` is derived from the key that signed it

Status: accepted
Date: 2026-08-15
Session: 6, Run 13
Affects: ADR 0002, ADR 0051, ADR 0078, ADR 0090, D276, D294,
`bin/dev-token.py`, `bin/api-contract.py`, `bin/api.py`, `bin/deploy-project.py`

## Context

`bin/dev-token.py` signs every operator token with the **bootstrap** issuer's
key — `signing_key_path()` names `bootstrap_jwt_signing_key.pem` and has since
Session 5 — and labelled the token with the key identifier it read out of the
deployed document:

```python
if jwt.get("active_kid"):
    header["kid"] = jwt["active_kid"]
```

That was correct for exactly as long as the published key set held one key. Run
10 closed D276 by publishing the auth service's key as well, and
`render-jwks.py:build` publishes it **first**:

> the auth service's key first when it exists, because it is the issuer from
> Session 6 onward and the key most tokens carry

while `deploy-project.py:observe_jwt` takes `active_kid = kids[0]`. From the
deploy that added the second key onward, every token this command mints has been
signed by one key and labelled with the other's identifier.

The symptom was `routes.rest: unavailable` on alpha-dev. `observe_served_document`
returns `None` when it cannot read the document it just published, and it could
not: the fetch was 401. The status field is the honest record of that (ADR 0050),
so the deploy exited 0 with a route that serves a complete document to anyone.

## What was measured

**First, the image.** Whether a `kid` *selects* a key or merely annotates one is
a property of PostgREST, not of this repository, so it was measured against the
locked digest (`postgrest:v14.16@sha256:bea1c76a856f…`) with a real cluster and a
two-key JWKS built through `render-jwks.py`'s own derivation — four arms, three
of them controls:

| arm | signed by | header `kid` | result |
|---|---|---|---|
| **A** | bootstrap | **auth's kid** | **401 `PGRST301`** "None of the keys was able to decode the JWT" |
| B | bootstrap | bootstrap's kid | 200 |
| C | bootstrap | *omitted* | 200 |
| D | auth | auth's kid | 200 |

**PostgREST selects the key by `kid`.** B and D show both keys verify, so the
set is sound; C shows that with no `kid` it tries every key, so A's refusal is
attributable to the label alone and to nothing about the signature. A is the
shape the product mints.

**Then the deployment**, because a rig is a second configuration of the product
(ADR 0065, 0066) and A being the shape the product *builds* is not evidence it is
the shape the product *sends*. Run on alpha-dev through `bin/dev-token.sh` — the
product's own command, minting as the product mints, presented to the published
route:

* `jwt.active_kid` is `w4OqVzyJ…`, and it is `keys[0]` of the JWKS PostgREST
  reads; the bootstrap key's identifier `sQQsxpzr…` is `keys[1]`. Both private
  keys are on disk, `0400`, owned by root and by uid 65532 respectively.
* the documentation token: **401**, body
  `{"code":"PGRST301","details":"None of the keys was able to decode the JWT"…}`
  — byte-identical to arm A.
* **control**, the same URL with no `Authorization` header at all: **200**, a
  complete OpenAPI document. The route is present, routed and healthy; what fails
  is the credential.
* **control**, a path no router claims: **404** with a **19-byte** body — Traefik's
  own, which is what a genuinely missing route looks like from outside (D186).

The second candidate is refused by the same measurement. Migration 0013's
pre-request hook raises with `ERRCODE = 'PT401'`, which PostgREST maps to HTTP
401, so the status alone cannot tell the two apart — but its body would begin
`AP401`, and the hook returns early for a documentation token before any
identity lookup. `PGRST301` is raised before a connection is taken. **The hook
never ran.**

## Decision

**`mint()` derives the `kid` from the key it is about to sign with.** The
identifier is an RFC 7638 thumbprint — a function of the key, which is the whole
of its value (ADR 0051) — so the label cannot disagree with the signature:

```python
modulus, exponent = jwks_command.read_public_parameters(key_path)
header = {"alg": "RS256", "typ": "JWT", "kid": jwt_keys.public_jwk(...)["kid"]}
```

`read_public_parameters` is loaded from `bin/render-jwks.py` rather than
reimplemented, for the reason `tests/deployment/conftest.py:jwks_command` already
states: it has the shape it does because the obvious spelling prints private
parameters and because openssl labels the exponent differently for a public and a
private key. A second copy would be written from the obvious spelling.

This is ADR 0002 applied to a value that had drifted out of it. `active_kid` is
a *derived* identifier with one authority — the key — and the deployed document
is a report of that derivation, not a second source for it. A signer that reads
its own label out of a document is a signer that will one day sign with a key the
document does not describe, which is precisely what happened.

**The same lesson, one run late.** ADR 0090 changed `SEC-BOOT-001` to derive the
bootstrap `kid` from the private key on disk rather than read it from the
document that names it, and called that D276's question asked of `SEC-BOOT-001`
for the first time. It was asked of the proof and not of the product. The
command that *signs* went on reading the document for one more run, and that is
the run in which the second key arrived.

## Alternatives rejected

**Publish a `bootstrap_kid` beside `active_kid` in the deployed document.** The
smallest diff, and it adds a second derived identifier to a document whose
purpose is to report derivations — an outputs schema bump (v10 → v11, and every
project redeployed) for a value both writer and reader can compute from a file
they already hold. It also leaves the defect's shape intact: the signer would
still be reading its label rather than deriving it, and the next issuer to arrive
would need a third field.

**Omit the `kid` entirely.** Measured to work against PostgREST — arm C, 200 —
and it is wrong for a reason outside PostgREST: the auth service's own verifier
requires the member (`services/auth-api/app/tokens.py`, `PERMITTED_HEADER_MEMBERS`
and the `for member in ("alg", "kid", "typ")` loop) and refuses a token that
lacks it. The two verifiers in this system disagree about whether a `kid` is
optional, and a token minted for the more permissive one is a token that cannot
be presented to the other. Trying every key is also a property of this
PostgREST version, not a contract it publishes.

**Put the bootstrap key first in `render-jwks.py:build`.** It would fix this
401 and break the meaning of `active_kid`. From Session 6 the auth service is the
issuer — `jwt.issuer` on alpha-dev is
`https://alpha-db.agenticpostgresql.com/api/app/auth` — and `active_kid` is read
by `bin/rotate-signing-key.py` as *the key currently signing*. Reordering to
satisfy one caller would make the rotation command's view of the key set wrong,
which is a worse defect in a quieter place.

## Consequences

**One function, and every operator token goes through it.** `bin/api.sh`,
`bin/api-contract.sh`, `bin/docs.sh check` and the deploy's own
`observe_served_document` all mint through `mint()`, so all four were refused by
any project deployed through session 6 and all four are fixed together. This is
why `rest_surface` and `api_contract` were at risk: not because the REST surface
was broken, but because every proof that authenticates to it was.

`routes.rest` becomes `ready` on the next deploy of a converged project, which is
the redeploy that publishes the observation — the two-deploy shape D112 already
established.

**A token's `iss` is still read from the document** and is now the auth service's
URL while the bootstrap issuer signs it. ADR 0078 measured that the locked
PostgREST never checks `iss`, so nothing rejects it today and no consumer of a
dev token verifies it. It is the same class of mistake as this one and is
recorded as **D295** rather than fixed here: the fix needs a name for the
bootstrap issuer that the deployed document does not currently carry, and
inventing one inside a repair is how a second unmeasured value gets published.
