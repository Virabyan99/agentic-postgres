# 0097 — A structural refusal is 400 and says nothing

Status: accepted
Date: 2026-08-15
Session: 6, Run 14
Affects: ADR 0078, D264, D303,
`services/auth-api/app/errors.py`, `services/auth-api/app/routes.py`,
`tests/contract/test_auth_endpoints.py`

## Context

`services/auth-api/app/errors.py` declares two refusal shapes and says plainly
what each is for:

```python
#: A request that was refused before any domain logic ran (API-AUTH-002). One
#: token for nine structural problems, for the reason `MalformedToken` is one
#: type: which of them a bad request had is not information its sender needs.
MALFORMED_REQUEST: Final = {"error": "malformed_request"}  # malformed() -> 400

#: A request whose values are individually well formed and jointly refused --
#: a scope outside the role's ceiling, a username already taken. The caller is
#: an authenticated administrator, so a reason is safe and useful.
INVALID_REQUEST: Final = {"error": "invalid_request"}  # invalid(msg) -> 422
```

`_body` raised `InvalidRequest` for both of its failures. So a **duplicate JSON
member in an unauthenticated login body** was answered:

```
422 {"error":"invalid_request","message":"duplicate JSON member: 'username'"}
```

— the administrator-facing shape, with the disclosed field name, to a caller
with no identity at all.

**Two proofs disagreed about this and neither knew about the other.**
`tests/contract/test_auth_endpoints.py::test_a_duplicate_member_in_the_login_body_is_refused`
asserted 422 and passed; `tests/deployment/test_session6_identity.py::test_the_published_route_applies_the_input_bounds_before_the_service_allocates`
asserted 400 and had never run. That is D264's shape — two authorities for one
value inside one service, both internally consistent — and it survived because
the second authority was in a proof nobody had executed.

## What was measured

On the host, through the published route: a duplicate member answered **422**
with the message quoted above. The offline suite answers identically, so this is
not an edge-only behaviour.

The split in the current code was then read rather than assumed. Of the five
offline assertions expecting 422, **two** are `invalid()`'s documented case —
an authenticated administrator creating a user or an agent whose scopes exceed
the role's ceiling, where the message names the offending scope and is useful.
The other **three** are structural refusals of an unauthenticated `/auth/login`
body: a duplicate member, a member the model forbids, and a body that is not a
JSON object.

## Decision

**A refusal that happens before any domain logic runs is `400
malformed_request`, and carries no message.** A refusal of well-formed values
by an authenticated administrator stays `422 invalid_request` with its reason.

`MalformedRequest` is a new exception type carrying its reason for the log and
never for the caller — the shape `AuthenticationFailed` already has, for the
same reason. `_body`'s two failure paths raise it: `MalformedBody` from
`strict_json`, and pydantic's `ValidationError`. `_guard` maps it to
`malformed()`.

Both paths, not just the first. A model with `extra="forbid"` refusing an
unknown member is as structural as a duplicate one, and it was disclosing the
pydantic error *types* — `request body is not valid: ['extra_forbidden']` — to
the same unauthenticated caller.

**The three offline assertions move from 422 to 400.** This is a contract test
changing, which needs this ADR, and it is a **replacement by a stricter
statement** rather than a weakening: each now asserts the status *and* that the
body carries no `message` member, which is the property that was actually
violated and which nothing checked before.

## Alternatives rejected

**Change the live proof to expect 422.** It would settle the disagreement in
favour of the code and against the code's own documented contract, and it would
keep an unauthenticated caller being told which field it duplicated. The live
proof was right; that is why it is the one that had never run.

**Keep 422 for `ValidationError` and use 400 only for `MalformedBody`.** The
line would then fall between two failures of the same request in the same
function, decided by which library noticed first — a distinction no caller can
act on and no reader would predict.

**Return 400 with the reason.** Cheaper to debug and it is the disclosure
itself that is the defect: `MALFORMED_REQUEST` is one token for nine structural
problems on purpose, and a message would restore all nine.

## Consequences

An administrator sending a malformed body now gets 400 with no detail where
they previously got a reason. That is the cost, it is accepted, and it is
bounded: a *semantic* refusal — the case an administrator actually hits — still
carries its message.

**API-AUTH-002 gains the assertion it was missing.** Its live half checked the
status of an oversized body and a duplicate member; neither half checked that a
refusal discloses nothing. Both now do.
