# 0170 — The deployment has one signer, and the retired key leaves the published set

- **Status:** accepted
- **Date:** 2026-09-02
- **Session:** 15, Run 1 (`bootstrap_identity`, D683, D821–D823)
- **Related:** **D683** (the cutover is blocked because the set has been full
  since Session 6), **D814** (the block is one unconditional line), **D821** (the
  bootstrap key has a live signer, and the deploy is its consumer), **D822** (the
  three appends are not symmetrical, and the ceiling stops being reachable),
  **D823** (`promote` infers the incoming key as *"whatever is not active"*),
  ADR 0094 (the `kid` is derived from the key path, not read from the document),
  ADR 0051 (one value, one derivation), ADR 0088 (every verifier is recreated
  after the published set changes), ADR 0155 (the mount-content digest that makes
  that automatic), ADR 0054/0055 (the root and compose planes), **D276** (the
  auth key was signed with and never published), **D701** (a signal that is
  always red is a signal nobody reads).

## Context

`bootstrap_identity` has been the single red P0 claim for nine sessions.
`docs/scope-closure.md` characterises the block precisely: `MAX_VERIFICATION_KEYS`
is 2, `build_jwks` refuses a third, and `render-jwks.py`'s `build()` appends the
bootstrap issuer's key **unconditionally** while the auth key and the prepared
key are each behind an `is_file()` guard. The set has been full since the auth
service existed, so a rotation cannot be prepared, and `retire` cannot free the
slot because `retire_after` is `None`.

That characterisation is **accurate about `render-jwks.py` and incomplete about
the system.** Run 1's first measurement asked a question the ledger did not:
*whose tokens carry the bootstrap `kid`?*

**`bin/dev-token.py` signs with it** (D821). Measured with a four-arm rig whose
fourth arm is a control that the omission does not also drop the auth key. Its
consumers are not incidental:

- **`deploy-project.py:observe_served_document` mints one on every deploy**, as
  the documentation role, to fetch the served OpenAPI document and produce
  `api.served_checksum`. It catches broadly and returns `None`.
- `bin/api.sh` and `bin/dev-token.sh` are the operator's manual REST surface.
- The deployment suite reaches it through a `dev_token` fixture.

So retiring the key first would have left every deploy silently recording
`api.status: unavailable` — **D701's shape exactly**, a signal that is always red,
arriving through a broad `except` that was written to keep a deploy honest rather
than to hide a defect.

Two further measurements shaped the decision. `signing_key_path()` **raises**
`JwksError(5)` when the bootstrap key is absent, where its two siblings return a
path the caller guards (D822) — so "make it symmetrical" is not a one-line
change. And `promote` computes the incoming key as *"whichever published kid is
not the active one"* (D823), with no guard distinguishing a prepared key from the
bootstrap one, so **today it would promote the bootstrap key.** That inference is
safe only because the set's second member has never been anything else and nobody
has run it.

## Decision

### 1. The deployment has one signer, and it is the issuer's

`bin/dev-token.py` signs with `auth_jwt_signing_key.pem`, on the auth service's
compose plane, rather than with the bootstrap issuer's root-plane key.

**This grants no new capability to anybody.** The minter runs as root under
`sudo` and root could always read both files; the auth key's `0400 65532` mode
bounds *services*, and `dev-token` is not one. The property `secrets.required.yaml`
defends — one service cannot read another's credential — is untouched, because no
service's grant changes.

What it changes is the count. **A deployment with two independently published
signing keys has two keys whose compromise is total**, and the second one exists
for no reason once the auth service is the issuer. Reducing that to one is the
security result of this run; freeing the rotation slot is the mechanical
consequence.

Three properties make the switch claim-neutral rather than a re-labelling:

- **The `kid` follows the key** (ADR 0094). `mint` derives it from `key_path`, so
  pointing the path at another key relabels the token automatically. ADR 0094 was
  written because the two had drifted apart once already, and it is what makes
  this safe to do by changing one path.
- **There is one issuer.** `observe_jwt` publishes a single `iss` and an audience
  beside several `kid`s, and `mint` reads both from the document's `jwt` block.
  Neither claim moves.
- **The key it moves to is the active one.** `render-jwks.py` publishes the auth
  key first and `observe_jwt` takes `active_kid = kids[0]`, so the minter now
  signs with the key at the head of the set instead of the one behind it.

A project with no auth key — anything deployed through Session 5 — is refused
with a message naming that, not with a traceback.

### 2. The bootstrap issuer's key is omitted, under the guard its siblings have

`build()` appends the bootstrap key only when it is present, exactly as it treats
the auth key and the prepared key. `signing_key_path()` stops raising on absence
and returns a path the caller guards, which is what makes the three symmetrical.

### 3. A published set that would be empty is refused where the cause is visible

`build_jwks` already refuses an empty list — *"a key set with no keys verifies
nothing"* — and that refusal stays as the backstop. But once the last
unconditional append is guarded, an empty set becomes **reachable** rather than
impossible, and the generic message names the symptom rather than the cause.

`build()` refuses first, naming the situation: no auth key and no bootstrap key
means a project deployed before Session 6 whose bootstrap key has been retired,
and the repair is to redeploy rather than to inspect a JWKS.

### 4. What this makes true, and what it does not

**The ceiling stays reachable, and the measurement corrected the draft of this
ADR** (D822). It first said that only two keys remain publishable, so a render
could no longer exceed `MAX_VERIFICATION_KEYS`. **That is true only after the
bootstrap key is gone from the generation**, and false during the whole
transition: a generation that still carries the bootstrap key beside the auth key
and a prepared one offers three, and the rig's control arm measured the refusal
*"above the ceiling"* exactly there.

So the ceiling is not lowered, not removed, and not made vacuous. It is the guard
on the state this change passes through — an operator who prepares a rotation
before the retiring deploy has run is precisely the case it refuses, and that case
is now reachable in a way it never was while the set was permanently full.
**A bound whose last violation you have just removed is the bound you are most
likely to delete the proof of**, which is the shape of this repository's standing
defect and the reason the proof moves to `build_jwks` rather than away.

**`promote`'s inference becomes sound by construction** (D823). With the set
holding the auth key alone, or the auth key beside a genuinely prepared one,
*"whichever kid is not active"* is the prepared key by the only arrangement the
renderer can produce. This ADR does not add a guard there; it removes the state
in which the existing one is wrong.

**`retire` becomes reachable rather than merely unrefused.** It is still blocked
until a rotation is promoted and its deadline passes, which is correct — nothing
here shortens the overlap a verifier needs.

## Consequences

- **Every verifier is recreated after this lands** (ADR 0088), and ADR 0155's
  mount-content digest makes that follow from the deploy rather than from anyone
  remembering. That path has never fired for a key-set change on this host, which
  is why Session 15's Run 8 verifies it **per verifier** rather than reading the
  deploy's exit code.
- **The window is bounded and known.** A token signed by the retired key lives at
  most `MAX_TTL_SECONDS + CLOCK_SKEW_SECONDS` = 930 s. Between the deploy that
  republishes the set and the recreation of the last verifier, a bootstrap-signed
  token is refused by whichever verifiers have already been recreated. Nothing
  mints one after this change, so the population is empty in a checkout and
  bounded by 930 s on a host mid-deploy.
- **Three contract tests are replaced by stricter ones**, which this ADR
  authorises and each docstring names: the set now carries one key rather than
  two, the prepared-key control builds on the auth key rather than the bootstrap
  key, and the ceiling is proved against `build_jwks` where it is still
  reachable.
- **`bootstrap_identity` can go green**, and its live half is Run 8's.

## Alternatives considered

**Retire `dev-token`'s minting entirely** and have the deploy obtain a
documentation token some other way. This is the cleaner separation and it was
rejected on cost, not on principle: migration 0009's hook refuses a documentation
token carrying a subject, and the auth service issues user tokens which carry
one — so there is no existing path that mints what `observe_served_document`
needs, and building one is its own run. Recorded rather than dismissed; if the
operator plane later needs a signer the issuer does not share, that is the shape.

**Keep the bootstrap key as the operator plane's independent signer.** This is
the honest case for the status quo — an operator tool that does not depend on a
service's credential. It was rejected because the cost is exact and permanent:
the signing key cannot be rotated, which means the *response* to a compromise is
unavailable, and Session 15 would prove rotation with the one credential that
cannot be rotated left out of the proof.

**Raise `MAX_VERIFICATION_KEYS` to 3.** Rejected on the ceiling's own stated
reason — *"an unbounded set is a set nobody retires from"*. The set being full is
the symptom; a second signer nothing needs is the disease, and raising the
ceiling would preserve it behind a larger number.
