# 0137 — Session 9 activates `agent_writer`, and an anchor that expires is not an anchor

Status: accepted
Date: 2026-08-22
Session: 9, Run 2
Affects: ADR 0096, ADR 0102, ADR 0116, ADR 0134, ADR 0135, D102, D266, D300,
D301, D416, D417, D475, D492, `bin/postgres-bootstrap.py`,
`tests/contract/test_bootstrap_statements.py`,
`tests/security/test_session3_authorization.py`,
`tests/contract/test_auth_endpoints.py`

## Context

ADR 0116 activated `agent_reader` and said, in as many words, what Session 9
would have to do: *"It adds `agent_writer` to one tuple, and every proof that
mentions the agent roles moves with it because none of them names one."*

That was true of the derived proofs and **not** true of the one anchor ADR 0116
deliberately left written down. `SESSION_NINE_ROLE = "agent_writer"` existed
because a set derived entirely from the product's own constant cannot refuse a
bad edit to that constant (D300). It did its job for one session.

Activating the role is one line in `AUTHENTICATOR_REQUEST_ROLES`. What this ADR
is actually about is the second half: **what happens to an anchor when the thing
it anchors becomes correct.**

## The part that matters

`SESSION_NINE_ROLE` named a role that a later session was *expected* to activate.
So the moment Session 9 arrived, the correct edit to that anchor was to delete
it — and deleting it leaves the derived set with nothing holding it, at exactly
the moment the constant is being changed. **An anchor whose removal is a planned
milestone is an anchor that is absent whenever it would have mattered most.**

The same shape appeared in the security suite, where the anchor read
`assert "agent_writer" not in holders`, and it would have been deleted for the
same reason on the same day.

An anchor has to name something that is wrong in **every** session, not wrong
until some session.

## What this session found next to it

**D492, and it is the reason this ADR is not only about a constant.**
`test_the_authenticator_cannot_become_an_agent_role` asserted that the
authenticator could become neither `agent_reader` nor `agent_writer`. Session 8
activated `agent_reader`, so in production the authenticator *can* become it —
the test had been asserting a property the product no longer had.

It stayed green because its fixture granted a **hardcoded list of four** request
roles that omitted both agent roles, with a comment explaining that granting them
"would delete the property". The fixture was manufacturing the condition the test
measured. That is a fifth copy of an enumeration that exists as a constant
precisely so proofs read it instead of restating it — D301's shape, after
Session 8 Run 2 deleted three others (D416).

Its docstring's other premise had expired too. It said *"there is no path on
which the hook could emit an agent-specific error"*; migration 0018's `token_use`
branch is exactly that path and raises `AP401`.

**And the habit is durable enough that this session reproduced it.** Run 1's own
new test listed the five request roles by hand, one run after D492 was found.

## Decision

**`agent_writer` joins `AUTHENTICATOR_REQUEST_ROLES`**, and migration 0019 lands
first. 0019 grants the role `USAGE` on `app_private` and `EXECUTE` on the hook
and both comparison helpers, none of which 0018 gave it (D475). The other order
produces a request refused by `permission denied for function
postgrest_pre_request` rather than by the boundary — the correct outcome for a
false reason, which is D417.

**The anchor becomes `NEVER_A_REQUEST_ROLE = "mcp_audit_service"`.** It is a
service identity that authenticates as nothing over HTTP, and ADR 0135 decided it
stays unactivated rather than deferring the question again. Granting the
authenticator a membership of it is wrong in every session, so moving that line
is always a mistake rather than sometimes a milestone. The security suite's
anchor moves to the same role for the same reason.

**Every fixture that grants request-role memberships reads the constant.** No
proof restates the list.

**One new comparison, and it is the one with teeth.** The roles granted `EXECUTE`
on the pre-request hook, read from the catalog with `aclexplode` (ADR 0134), must
equal `AUTHENTICATOR_REQUEST_ROLES` exactly. This compares two independent
products — what the migrations grant against what the bootstrap plane activates —
so a bad edit to the constant now fails against the catalog rather than being
invisible to every derived proof.

## Alternatives rejected

**Keep `agent_writer` as the anchor and assert it *is* activated.** That inverts
the test into a restatement of the constant: it would pass by reading the same
value twice, which is the "test comparing two constants" shape.

**Drop the written-down anchor entirely, now that the catalog comparison
exists.** The catalog comparison is stronger against grant drift and is still a
comparison between two things this repository controls. One name that no session
may activate costs a line and closes the case the derived set structurally
cannot.

**Leave `test_the_authenticator_cannot_become_an_agent_role` alone and just add
`agent_writer` to its fixture.** That preserves a test asserting something false
about the product and makes it falser. The assertion had to become the rule the
old list was an instance of.

## Consequences

Six request roles. `check_violations` still derives the forbidden set as the
complement over the project's own roles, so a **seventh** unexpected membership
fails without anyone editing a second place.

`test_the_authenticator_becomes_exactly_the_request_roles` now asserts a positive
arm over every request role and a negative arm over **every other declared
role** — strictly more than the two names it replaced, and it refuses a vacuous
negative arm explicitly.

An agent token naming `agent_writer` is assumable from the next deploy of any
project. Until then the role is granted and unassumable, which is inert rather
than dangerous.
