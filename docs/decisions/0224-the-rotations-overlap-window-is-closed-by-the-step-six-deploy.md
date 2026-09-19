# 0224 — The rotation's overlap window is closed by the operator's step-6 deploy, and `retire` reports that it was

- **Status:** Accepted
- **Date:** 2026-09-19
- **Session:** 31, Run 1 (D1599, carrying D1580 and D1581 from Session 30)
- **Affects:** `jwt_keys.retire_rotation`, `bin/rotate-signing-key.py`'s
  `FOLLOW_UP["promote"]`, `docs/operator-guide.md` §15, `docs/plans/session-28-
  implementation-plan.md` Appendix R step 6, and the rotation module's tests.
  No migration, no schema move, **no change to what is published at
  `/auth/jwks.json`**.
- **Related:** ADR 0195 (a report may not fold a third outcome away), ADR 0215
  (an acknowledgement is read through the container's mount namespace), D509,
  D860, D1469, D1580, D1581.

## Context

The signing key was rotated on both projects on 2026-09-19 and D860 closed as
an act after being declined at five trips. Walking the rotation end to end
found something rig 28d had rehearsed **both ways and could not see**.

`retire_rotation`'s docstring says the thing that matters:

> Refusing early is the half that matters. Retiring before the window closes
> invalidates tokens that are still inside their own lifetime, and the failure
> arrives at whoever holds one with no cause visible from where it is seen.

**That branch cannot fire on the only path an operator can walk.** The chain,
measured on both projects:

1. `FOLLOW_UP["promote"]` tells the operator to set the promoted key as
   active, **clear the prepared key, bring the project down and redeploy**.
2. That deploy runs `render-jwks.py`, which writes a key set holding **one**
   kid.
3. `observe_jwt` (`bin/deploy-project.py:2885-2890`) carries the deadline
   forward **only when the published set still holds two keys**:
   `retire_after = previous.get("retire_after") if len(kids) > 1 else None`.
   Its comment is correct about why — a deadline describing an overlap that has
   ended is a document `validate_key_state` would refuse.
4. So by the time the operator runs `retire`, `state["retire_after"]` is
   `None`, and `retire_rotation` raises **`no rotation is in flight; there is
   nothing to retire`** — one line *above* the deadline check, which is
   therefore unreachable.

The rig could not find it because **the rig edited the document and the deploy
is what overwrites it**. This is D509's shape in a credential path: the
component under test was given a state the system never produces.

Two things follow that the guide did not say. The overlap window **actually
closes at step 6's deploy**, not at `retire` — the moment the rendered set
drops to one key, the retiring key stops being published and any token signed
by it stops verifying. And `retire`'s refusal, read by an operator, says
something false about the world: it reports *nothing is in flight* about a
rotation that is in flight and has just been completed by the previous step.

D1581 is recorded beside this and **stays undetermined**: why `auth` was
recreated by Run 7's deploy and not by Run 8's is unexplained.
`mounted_paths_by_service` parses one rendered compose payload and the secret
mounts live in another, so a new generation is invisible to the
`apg.mounted.sha256` digest — which explains Run 8 and contradicts D1571,
written seven hours earlier off Run 7. It is reported, not folded.

## Decision

**The sheet is reordered so the refusal's premise becomes true, and `retire`
reports the outcome it actually found instead of refusing for the wrong
reason.**

1. **The operator guide §15 and Appendix R's step 6 are rewritten so that the
   step-6 deploy is taken only *after* `retire_after` has passed.** The sheet
   reads the deployed document's `retire_after` and waits. Reordering a sheet
   costs nothing, and it makes the deploy — which is what genuinely closes the
   window — happen at the moment the window is genuinely closed.

2. **`FOLLOW_UP["promote"]` says so**, naming the deadline and the wait, so
   the instruction and the guide cannot drift.

3. **`retire_rotation` gains a reported outcome.** With
   `retire_after is None` **and** exactly one published kid **and**
   `verifier_acknowledgements` `None`, it **reports** *retired by the deploy
   that published one key* and exits 0, rather than refusing. All three
   conditions are required: any other combination is a document a future
   deploy could still write, and it keeps the refusal.

4. **The early refusal stays, and keeps its test.** It is unreachable on
   today's path and it is not unreachable in principle — a document written
   before step 6 still carries a future deadline, and a rotation abandoned
   part-way can produce one. Deleting a correct guard because the current
   runbook cannot reach it is how the guard is missing the next time the
   runbook changes.

**Deferred by name:** whether `render-jwks` should read `verification_kids` so
that the deploy carries the retiring key and the overlap survives step 6
properly. That is the right fix and it is a rewrite in a credential path; it
needs a rig and a rotation to prove it, and this session has neither. It
belongs to the session that performs the other three rotations (§10), which is
also what D1469 says is owed before any rotation claim can be taken.

## Consequences

- The overlap window is honoured by the order of operations rather than by a
  branch that never runs.
- An operator who runs `retire` after a correct rotation gets exit 0 and a
  sentence describing what happened, instead of an error stating the opposite
  of the truth.
- Nothing about what is published changes, so no verifier and no token holder
  is affected, and the rotation performed on 2026-09-19 stays valid as taken.
- The rotation still closes **no claim** (D1469): three rotation claims need
  four rotations, and this moves one node id of nine. The retired JWKs are at
  `/home/op/s30-retired-<key>-jwk.json` for the first sweep that passes
  `--rotated-jwt-from-file`.

## Alternatives considered

- **Make `render-jwks` publish `verification_kids`, so step 6 keeps both keys
  and `retire` does the retiring.** The correct end state, and out of reach
  this session: it changes what is served at `/auth/jwks.json` mid-rotation
  and can only be proved by performing one. Deferred by name, not dropped.
- **Delete the unreachable branch.** It is a correct guard for a document the
  system can still produce; removing it because one runbook cannot reach it is
  the reverse of the lesson. Rejected.
- **Leave the refusal and document it as expected.** An operator following the
  guide would keep receiving a false statement about the state of their own
  rotation at the end of every rotation. A decision may fail closed; a report
  may not (ADR 0195). Rejected.
- **Reorder nothing and have `retire` accept any `None` deadline.** That would
  retire on a document written before the window closed. Rejected — it is the
  exact harm the docstring names.
