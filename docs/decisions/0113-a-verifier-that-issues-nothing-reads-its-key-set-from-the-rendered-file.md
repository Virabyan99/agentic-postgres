# 0113 — A verifier that issues nothing reads its key set from the rendered file

Status: accepted
Date: 2026-08-19
Session: 7, Run 11
Affects: ADR 0088, ADR 0098, ADR 0101, D257, D296, D320, D333, D381,
`services/auth-api/app/service.py`, `services/auth-api/app/settings.py`,
`services/auth-api/app/main.py`, `compose.yaml`,
`src/agentic_postgres/runtime_override.py`

## Context

ADR 0098 fixed the model: **the issuer publishes what it signs with, and the
verifier is configured with every live issuer's key.** ADR 0101 added a second
runtime from one image, and D320 recorded the consequence — storage becomes a
**third verifier**, so every place enumerating verifiers moves with it.

Every one of those statements was written down. `compose.yaml` says storage
"is a THIRD verifier (ADR 0098, D320) and holds no signing key: there is no
`APG_SIGNING_KEY_FILE` here and there must not be." `main.py`'s lifespan says
"Both modes build the AuthService: storage VERIFIES the tokens auth issues."
`settings.load` **refuses to start** if storage is given a signing key.

**Nothing said where storage's verification keys come from, and nothing gave it
any.** `AuthService.__init__` derived its only key set from the signing key:

```python
self.key_set = LocalKeySet.load(json.dumps(signing_key.jwks()).encode("utf-8"))
```

Unconditional, with the parameter typed `SigningKey` rather than
`SigningKey | None`. In storage mode `signing_key` is `None` by design, so the
first start of a storage container anywhere raised `AttributeError: 'NoneType'
object has no attribute 'jwks'` and uvicorn exited `3` (`STARTUP_FAILURE`)
three times under `restart: on-failure:5` (**D381**).

This is **D333's question a fourth time in one session**: the decision was
implemented in `settings.load`, in `lifespan` and in `create_app`, and not in
the one place that consumes it.

## What was measured

The fix rests on one link nothing had ever exercised: the JWKS the *platform*
renders must be readable by the *service's* verifier parser. Two different
modules build that document — `src/agentic_postgres/jwt_keys.py` for
`bin/render-jwks.py`, and `services/auth-api/app/keys.py` for the auth runtime —
and only the second had ever fed `LocalKeySet`.

Measured with `jwt_keys.public_jwk` + `build_jwks` on generated 2048-bit keys,
parsed with `LocalKeySet`, **with controls**:

| case | result |
|---|---|
| platform emits | `kty` RSA, `alg` **RS256**, `use` sig, computed `kid`, members `alg e kid kty n use` |
| `build_jwks` one key → `LocalKeySet.load` | **accepted** |
| `build_jwks` two keys (what the host renders) | **accepted** |
| `from_path` on a file written `indent=2, sort_keys=True` as `render-jwks.py` writes it | **accepted**, 2 keys resolved |
| CONTROL — a private RSA member (`d`) | **refused**, `MalformedToken` |
| CONTROL — `alg: HS256` | **refused**, `MalformedToken` |
| CONTROL — empty `keys` array | **refused**, `MalformedToken` |
| CONTROL — a key with no `kid` | **refused**, `MalformedToken` |

The rig can tell success from failure, so the four acceptances mean something.

Two further facts, read rather than assumed:

- **`LocalKeySet.from_path` already exists** (`tokens.py:240`), and its docstring
  reads *"Read a JWKS from a file. The only way this service obtains keys."* Its
  only caller in the entire repository is a contract test. **The machinery was
  written, tested green, and wired to nothing.**
- The deployed `jwks.json` is mode `0444` and holds **2 keys**, and its parent
  directory is not traversable by `apg-agent` — so it could not be read for this
  measurement, which is why the link was measured through its producer instead.

## Decision

**A verifier that issues nothing reads its key set from the rendered JWKS file,
by path — the same artefact PostgREST is already given.**

1. `AuthService` is **handed** its `key_set` rather than deriving one. Both modes
   state their source at the call site; there is no branch where the key set is
   implied. `signing_key` becomes `SigningKey | None` in the signature, because
   that is what it has been in fact since ADR 0101.
2. Storage is given `APG_JWKS_FILE`, added to `STORAGE_VARIABLES`, and the
   rendered `jwks.json` is mounted read-only into the container. It loads it with
   `LocalKeySet.from_path` — the existing, tested classmethod.
3. Auth continues to derive its set from its signing key, because an issuer
   verifying with anything other than what it signs with is the split ADR 0098
   exists to prevent.

## Alternatives rejected

**Give storage a signing key.** Refused by ADR 0101 and by `settings.load`
itself. A storage container holding a signing key is a second issuer nobody
published, and ADR 0098's model is that a verifier's set is decided by what
issuers *declare*.

**Fetch the JWKS over HTTP from the auth service at startup.** It makes one
application container's start depend on another's, invents a cache whose
invalidation is exactly the problem ADR 0088 solves by recreation, and turns a
key-set change into a distributed timing question. The file is already there.

**A stored `jwt_public_jwks` secret.** **D257 refused this once already** — the
public half is derivable from the private half, and a stored copy is a second
authority for one value, which is D264's cost.

**A `None` guard at `service.py:83`.** It would have started the container and
left storage verifying **nothing**, refusing every token with `no key with kid`.
The failure would have moved from startup to every request, which is strictly
worse: a container that starts is a container that looks deployed.

## Consequences

- **Storage joins the recreate list.** ADR 0088 already says every verifier must
  be **recreated, not restarted**, after any change to the published set. There
  are now three, and all three read a file at startup and none re-reads it — the
  rule is uniform rather than special-cased, which is the version of it worth
  having.
- **D296 gets heavier.** `render-jwks` prints *"the key set CHANGED"* on every
  deploy, and a third verifier makes that message more load-bearing, not less.
- **SEC-KEY-002's readings go from two to three.** D320 predicted exactly this.
- The document is now consumed by two independent parsers — PostgREST's and
  `LocalKeySet` — so a change to `jwt_keys.build_jwks` has two consumers to
  satisfy, and a test that only exercises one of them proves half of it.
