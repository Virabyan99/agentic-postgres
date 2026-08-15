# 0089 — A claim is built from its own session's requirement IDs

Status: accepted
Date: 2026-08-15
Session: 6, Run 11
Affects: ADR 0025, ADR 0039, ADR 0045, D119, D222, `evidence_claims.py`,
`tests/acceptance-registry.yaml`

## Context

Session 6's plan closes with a claim table (§7) and a registry table (§2). The
registry table introduces six requirement IDs under a sentence that decides how
they were chosen:

> **New IDs, added only where none of the five covers the claim.** Prefixes are
> already admitted by `ID_PATTERN`; none is invented.

Three of the six are not new. `SEC-BOOT-001` has been in the registry since
Session 5 with three node IDs and a paragraph about the temporary bootstrap
issuer; `SEC-REV-001` has been there since Session 1 as a Session 9 placeholder
about revocation through MCP; `DEP-ISO-003` has been there since Session 3 and
is half of the `database_isolation` claim. The prefixes were checked. The
directory was not.

That would normally be a naming slip. It is an ADR because of a mechanism
`evidence_claims` documents at length and the plan does not reference:

```python
def claim_session(claim: str) -> int:
    return max(int(_requirement(name)["target_session"]) for name in CLAIMS[claim])
```

A claim does not declare its session. It **derives** it from its requirements.
So building a Session 6 claim out of an earlier session's requirement ID does
not extend that requirement — it moves the claim to the earlier session. The
module's own commentary reaches this conclusion twice, for `database_isolation`
in Session 4 and for `connection_tooling` in Session 5, each time deciding *not*
to extend an existing claim. Nobody had asked the inverse question: what happens
when a **new** claim is built from an **old** requirement.

## What was measured

Both directions, with controls, against the registry as it stands at `c162a5b`.

**The relocation, downward.** `project_isolation: ("DEP-ISO-003",)` resolves to
`claim_session=3`, and `claims_through_session` then reports it answerable by
the gates for sessions **3, 4, 5** and every later one. `merge` was then run —
the real function in `bin/write-session-evidence.py`, not a reimplementation of
it — over a Session 3 host half:

| Session 3 evidence | exit | document written | `status` |
|---|---|---|---|
| the registry as it stands (control) | 0 | yes | `passed` |
| with `project_isolation` over `DEP-ISO-003` | 5 | **yes** | **`failed`** |

The failing document is still written. So the consequence is not an error an
operator would investigate; it is three earlier sessions' evidence quietly
turning red, with a claim in it whose proofs are Session 6 auth tests that a
Session 3 gate has no way to run.

**The disappearance, upward.** `token_non_resurrection: ("SEC-REV-001",)`
resolves to `claim_session=9`. `claims_for_mode("host", 6)` therefore does not
contain it — no error, no warning, no entry in the evidence. The property §2
calls "the session's sharpest" and gives its own ID "because a passing
`API-AUTH-001` would not imply it" would have been absent from the document that
is supposed to record it, and the gate would have exited 0.

**The control that makes both readings mean something.** The same two claims
built over IDs that really are late-session — `DEP-ISO-005` — move with them
(`claim_session=5`), and the three existing claims resolve unchanged. The
mechanism responds to the ID's session rather than to the claim's name, which is
the thing being asserted.

## Decision

**A claim added by a session names requirement IDs targeted at that session.**
Session 6 adds six, and three of them are new spellings rather than the plan's:

| The plan wrote | Session 6 uses | Why |
|---|---|---|
| `SEC-CRED-002` | `SEC-CRED-002` | genuinely absent |
| `API-AUTH-002` | `API-AUTH-002` | genuinely absent |
| `SEC-KEY-002` | `SEC-KEY-002` | genuinely absent |
| `SEC-BOOT-001` | **`SEC-BOOT-002`** | one ID, two meanings |
| `SEC-REV-001` | **`SEC-REV-002`** | Session 9's, and about MCP |
| `DEP-ISO-003` | **`DEP-ISO-006`** | Session 3's, and load-bearing |

`SEC-BOOT-002` is the one worth explaining, because it is not only about
sessions. `SEC-BOOT-001` guarantees that the *temporary bootstrap issuer* holds
the only private signing key. Session 6's property is that the *first project
administrator* is created only through the local protected path, exactly once,
under an advisory lock. Those are different guarantees that share an English
word. Giving them one ID is precisely what D47 refused when it dropped
`API-DB-001` against `SEC-VIEW-001` — two IDs for one meaning — read backwards.

The rule generalises past this session: **before adding a requirement ID, read
the registry for it.** Prefix validity is not availability, and `ID_PATTERN`
answers a different question than the one being asked.

## Alternatives rejected

**Retarget the existing IDs to session 6.** `SEC-REV-001` could be moved from 9
to 6. It fails on meaning rather than on mechanism: its description and its
placeholder are about denial through MCP, which does not exist until Session 9,
so Session 6 would be answerable for a transport it does not ship. Retargeting
`DEP-ISO-003` is worse — it is already proved, on the host, and moving it
withdraws `database_isolation` from Sessions 3 and 4.

**Extend the existing claims instead of adding new ones.** `database_isolation`
gaining a Session 6 requirement is the case `evidence_claims` already refused
twice, for the reason recorded in D119: the claim moves to Session 6 and the jq
expression in `docs/session-03-operator-guide.md` stops finding it.

**Let `claim_session` take an override.** A claim could declare its session and
stop deriving it. That removes the property ADR 0039 bought — a claim that
gains a later requirement becomes that session's claim without anyone
remembering to say so — in order to make one mistyped table work. The derivation
is not the defect here; it is what surfaced it.

## Consequences

Six registry entries at `target_session: 6`, and seven claims whose
`claim_session` is 6 by construction. Sessions 2 through 5 are untouched, which
was checked rather than assumed: their claim sets are byte-identical before and
after.

The plan's §2 and §7 tables are now wrong in three cells. They are left as
written and corrected in the divergence table (D279), because a plan edited to
agree with the code stops recording that the two disagreed — which is the
standing rule this repository has had since Session 2.

Two tests now detect the error this ADR is about, and **it took the mutation
battery to find out that one was not enough.**

`test_a_claim_resolves_to_the_session_that_introduced_it` compares each claim
against a written-out table of which session introduced it. That catches both
failures measured above: a claim built from an older requirement resolves to the
older session, and one built from a later requirement resolves to the later one.

It does **not** catch the third case, which is the likeliest. Mutating
`admin_authorization` to `("API-ADMIN-001", "SEC-BOOT-001")` — reusing Session
5's requirement, one of the three mistakes this ADR is about — left that test
**green**, because `claim_session` is a `max()` and `max(6, 5)` is still 6. The
session check sees a claim built *entirely* from older requirements and is blind
to an older requirement *added alongside* a current one.

So `test_no_requirement_is_named_by_two_claims` was added: a requirement belongs
to at most one claim. Measured before it was asserted — no requirement is shared
today, across twenty-five claims and five sessions — and it catches the mutation
the first test could not. A future session whose guarantee genuinely rests on an
earlier requirement's proofs would have to relax it, which is what an ADR is for.

What neither test catches is a claim **never added at all**. That stays a review
rule, alongside the two the registry already has (D174, D175).

The general point is the one this repository keeps re-learning from a different
direction: *the assertion has to be able to distinguish the two worlds*. "The
claim resolves to session 6" is true in both worlds when the mechanism that
computes it is a maximum.
