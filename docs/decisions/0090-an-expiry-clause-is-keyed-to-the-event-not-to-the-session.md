# 0090 — An expiry clause is keyed to the event, not to the session

Status: accepted
Date: 2026-08-15
Session: 6, Run 11
Affects: ADR 0046, ADR 0051, ADR 0088, D276,
`tests/deployment/test_session5_bootstrap_identity.py`

## Context

ADR 0046 established a good rule: a fact with an expiry date is written so that
the session which invalidates it makes a test **fail** rather than makes the
fact stale. `SEC-BOOT-001` implements it, in one line:

```python
ISSUER_RETIRED_IN_SESSION = 6
...
assert project_a["deployed_through_session"] < ISSUER_RETIRED_IN_SESSION
```

The reasoning was sound when it was written. ADR 0051 said Session 6 retires the
temporary bootstrap issuer, so a project deployed through session 6 that still
records a temporary issuer is a project whose retirement never happened.

Session 6 then did not retire it. ADR 0088 built the four-phase cutover and the
operator guide's §4 is explicit that no rotation may be started this session:
the key set holds at most two keys, both slots are taken by the two live issuers,
and the transition between *those two* is the first rotation the machinery
exists for. Retiring the bootstrap issuer inside the session that publishes the
second issuer would mean proving the rotation and the issuance at once, against
one deployment.

So two accepted decisions now disagree, and the disagreement is not academic:
the host trip that deploys Run 10 turns a currently-green proof red.

## What was measured

The real test function, called twice with documents identical except for
`deployed_through_session`. Asserting that `6 < 6` is `False` would have been a
tautology (D173), so what was recorded is **which assertion fires first**:

| `--through-session` | outcome |
|---|---|
| 5 (control — the host today) | gets *past* the expiry clause, fails later reaching the root-plane secret tree |
| 6 (after the Run 10 deploy) | fails **at** the expiry clause |

The control is the whole measurement. Both arms fail — one is off-host, so the
filesystem is unreadable either way — and only the difference in *where* they
fail attributes the failure to the clause rather than to the fabricated
document. `bin/deploy-project.py` writes `deployed_through_session` from
`--through-session` and hard-codes `"temporary": True`, so the session-6 arm is
what the operator guide's own command produces.

## Decision

**The clause is re-keyed from the session number to the event it stands for.**
`deployed_through_session` was always a proxy for "the retirement has happened".
The deployed document now carries the state that answers the question directly —
`verification_kids`, `retire_after`, `verifier_acknowledgements` — so the proxy
can be replaced by the thing itself:

* while `jwt.temporary` is true, the bootstrap issuer's key **must still be
  published**: its `kid`, derived on the host from the private key in the root
  plane, is in `verification_kids`;
* once that key is no longer published, `temporary` must be false.

This is a **replacement by a stricter test**, which is the only kind the
non-negotiables permit, and it is stricter in two independent ways. It fires on
the actual retirement rather than on a session that might or might not perform
one; and it checks a *derivation* — that the key identifier in the document is
the one the key on disk produces — which nothing checked before. That second
half is D276's lesson applied to `SEC-BOOT-001`: the document said which keys
verify, and no proof had ever asked whether those identifiers came from the keys
this deployment holds.

The test's docstring says so, as the non-negotiables require.

## Alternatives rejected

**Move `ISSUER_RETIRED_IN_SESSION` to 7.** One line, and it postpones the same
defect by exactly one session while teaching the next reader that the number is
negotiable. It also weakens a passing test — the window in which a stale
temporary issuer goes unnoticed grows by a session — which the non-negotiables
forbid outright.

**Delete the clause and let `SEC-KEY-002` cover it.** `SEC-KEY-002`'s live
proofs deliberately assert the *non-rotating* invariants (ADR 0088), so nothing
in them fires when a retirement is skipped. Removing the clause would leave the
retirement with no expiry pressure at all, which is what ADR 0046 exists to
prevent.

**Set `temporary: false` in the deploy once the auth service's key is
published.** Tempting, and wrong: the bootstrap issuer is still live during the
overlap — `bin/dev-token.py` still signs with it and PostgREST still accepts it.
A document saying the issuer is no longer temporary while it is still verifying
tokens would be a value that looked measured and was not, which is the defect
pattern this repository keeps producing.

## Consequences

`SEC-BOOT-001` keeps its ID, its claim (`bootstrap_identity`) and its session,
and it stays red-on-retirement — the property ADR 0046 wanted. What changes is
what makes it go red: the key set, not the calendar.

The Session 5 gate is unaffected in offline mode and, on a host still at
`--through-session 5`, in host mode too: the bootstrap key is published and
`temporary` is true, which the new clause admits.

**This ADR is why the Run 10 deploy does not fail its own gate**, and it had to
exist before the host trip rather than after it. A gate that goes red for a
correct deployment is the failure that teaches an operator to ignore gates.
