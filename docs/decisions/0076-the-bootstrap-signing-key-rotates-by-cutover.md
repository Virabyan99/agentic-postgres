# 0076 — The bootstrap signing key rotates by cutover, and the overlap is unbuilt

Status: accepted
Date: 2026-08-13
Session: 6, Run 1
Affects: SEC-BOOT-001

## Context

`docs/api-operations.md` told an operator this, and the Session 6 plan built on
it:

> **The signing key.** Two phases: publish the new key beside the old, then
> retire the old.

`src/agentic_postgres/jwt_keys.py` implements both phases carefully.
`begin_rotation` publishes two verification kids and computes the retirement
deadline as `now + max_token_ttl + clock_skew` — at phase one, because "at phase
two the moment the switch happened is exactly what nobody remembers".
`complete_rotation` refuses to run before that deadline. `validate_key_state`
requires the two halves of "a rotation is in flight" to agree. There is a
ceiling on the verification set, with a comment about the third key being the one
nobody retires. It is good code and its unit tests are thorough.

**Nothing calls it.** Measured across the whole repository: the only references
to `begin_rotation` and `complete_rotation` outside `jwt_keys.py` itself are in
`tests/contract/test_jwt_keys.py`.

The executable path is the other one. `bin/render-jwks.py::build` derives the
JWKS from the single materialized private key and returns
`jwt_keys.build_jwks([jwk])` — one key, with a comment reading "A rotation
publishes two and is Run 10's". Run 10 did not. `bin/deploy-project.py::observe_jwt`
reads the kids back out of that file and writes `"retire_after": None`
unconditionally, with a comment reading "a date here is a rotation with a
deadline, and Run 10 is what sets one".

So there is no operator-facing path that publishes two verification keys, and
the two-phase overlap cannot be performed. A rotation of the bootstrap signing
key today is: replace the value at the provider, materialize a new generation,
redeploy. One key out, one key in, no window in which both verify.

This is the pattern the project keeps producing, in its purest form yet: a plane
built, validated, unit-tested, documented — and wired to nothing. `PGRST_DB_PRE_REQUEST`
was the same shape in Run 9, and the comment naming a future run is the tell in
both cases.

## Decision

**The bootstrap issuer's key rotates by cutover, and that is written down as
what happens rather than as what was intended.**

Concretely:

- `docs/api-operations.md` describes the cutover, with the commands that perform
  it, and states that the overlap functions exist and are unreachable.
- `test_a_rotated_signing_key_is_the_only_one_the_plane_accepts` keeps every
  assertion it had. It was already written as an **end state** — the retired kid
  is not `active_kid`, is not in `verification_kids`, and a token signed by the
  active key is served — and an end state is agnostic about the path taken to
  it. Only its docstring changes, from "the second of two phases" to "the whole
  rotation".
- `SEC-BOOT-001`'s registry description loses the phrase "once its second
  rotation phase completes".
- `jwt_keys.begin_rotation` and `complete_rotation` stay, uncalled, and are
  **not** presented as available. Session 6 Run 10 needs a real overlap for the
  auth service's key — with per-verifier acknowledgement, which these do not
  have — and that is where this logic is either used or superseded.

**The cutover is acceptable for this deployment, and the reason is bounded, not
assumed.** `bin/dev-token.py` caps a token at `MAX_TTL_SECONDS = 900` and
defaults to 300. Tokens are minted on demand by an operator; nothing holds a
long-lived one; the issuer is `temporary: true` and is being retired this
session. The blast radius of a hard cutover is at most fifteen minutes of
outstanding tokens, in a window a human is already sitting in.

## Alternatives

**Wire `begin_rotation`/`complete_rotation` into the deploy now, so Run 1
rehearses the overlap.** Rejected, and it is the closest call here. It is real
work — a second materialized key, a two-key JWKS, a `retire_after` the deploy
carries forward, a second window — for a key that Session 6 retires. And it
would *not* rehearse what Run 10 needs: Run 10's safety property is that
**promotion is blocked until every verifier has acknowledged the prepared
generation**, and neither of these functions knows what a verifier is.

**Delete them as dead code.** Rejected. The deadline arithmetic and the
refuse-early rule are the parts of a rotation that are hard to get right, and
they are correct. Deleting them would mean rediscovering them in Run 10.

**Leave the documentation as it is and perform a cutover quietly.** Refused by
CLAUDE.md §5: a conflict between a runbook and the code goes in the divergence
table or an ADR, never resolved inline.

## Consequences

- **Session 6's plan claimed Run 1 would exercise the prepare/promote/retire
  machinery Run 10 depends on. It will not, and that claim is struck.** Run 10
  builds its overlap without a live rehearsal, which raises its risk rather than
  lowering it, and §9 of the plan carries it as such.
- Run 1's signing-key rotation is one window, not two, and the proof is admitted
  at the end of it.
- What Run 1 *does* rehearse for Session 6 is everything else: the
  materialize → redeploy → admit sequence, the per-consumer generation layout,
  the bootstrap plane's re-application of a credential, and the edge's reload of
  a rewritten middleware. That is most of a rotation and all of the parts a
  cutover shares with an overlap.
