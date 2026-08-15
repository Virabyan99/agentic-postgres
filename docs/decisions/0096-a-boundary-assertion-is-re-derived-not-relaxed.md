# 0096 — A boundary assertion is re-derived, not relaxed

Status: accepted
Date: 2026-08-15
Session: 6, Run 14
Affects: ADR 0046, ADR 0052, ADR 0088, D57, D102, D266, D301,
`tests/security/test_session3_authorization.py`,
`tests/deployment/test_session5_api_authorization.py`,
`tests/deployment/test_session5_bootstrap_identity.py`,
`bin/postgres-bootstrap.py`

## Context

Four proofs written in Sessions 3 and 5 assert where a boundary is. Session 6
moved four boundaries, deliberately, each with its own reasoning recorded at the
time — and the first host gate run afterwards reported all four as violations:

| what the proof said | what Session 6 did |
|---|---|
| the authenticator is a member of exactly `anon`, `authenticated`, `api_documentation` | Run 9 granted it `project_admin` too (D266), in the bootstrap plane, because `GRANT role TO role` needs authority the migration plane does not hold |
| exactly one function in `app_private` is executable by a request role | migration 0013 grants `auth_claims_are_current` to every role that runs the hook |
| the roles with LOGIN are `migration_user`, the access profiles, and the authenticator | Session 6 activates `auth_service`, because a container authenticates as it |
| the only PEM in a secret generation is the bootstrap issuer's key | the auth service is an issuer and holds a signing key of its own |

Each of the four is a **correct** product change reported as a defect. That is
the failure mode ADR 0046 exists to prevent, arriving four times at once because
nothing had run these proofs since the changes landed.

## What was measured

For each, the product's own reasoning was read before the proof was touched —
because "the test is stale" is exactly what somebody says about a test that has
just caught something:

* **`project_admin`.** `bin/postgres-bootstrap.py` grants it with
  `ADMIN FALSE, INHERIT FALSE, SET TRUE`, the same options as the other three,
  in a comment naming D266 and D102 and stating why it is safe — the membership
  lets the authenticator *become* the role, and what that role may do
  administratively is decided by the scope in a token, not by the role name.
* **`auth_claims_are_current`.** `postgrest_pre_request` is `SECURITY INVOKER`,
  measured by reading 0013, so a request role executing it needs `EXECUTE` on
  everything it calls. Without the grant every request fails. The function
  returns a **boolean** over a five-value tuple and never returns a subject's
  role or scopes, which is stated in its own `COMMENT ON` — so it cannot be used
  to enumerate another subject's authority.
* **`auth_service` LOGIN.** The container authenticates as it; `SEC-KEY-001`'s
  Session 6 rewrite already asserts the credential's shape.
* **The auth service's key.** `tests/deployment/test_session6_tokens.py::test_no_verifier_holds_private_signing_material`
  already asserts that file's existence, mode and ownership positively. Excluding
  it from the bootstrap key's leak scan therefore loses no coverage — the
  property has an owner.

## Decision

**Each assertion is re-derived from the authority that owns the fact, not
relaxed to admit what was found.**

* The membership set is read from `AUTHENTICATOR_REQUEST_ROLES`, promoted to a
  module constant in `bin/postgres-bootstrap.py`. The bootstrap plane owns role
  membership (D102), so the proof now reads the enumeration rather than keeping
  a copy. **The test's own docstring asked for this** — *"a session that
  activates another role must move this assertion with it rather than leave the
  refusals below measuring nothing"* — and a set the test writes down cannot
  move with anything.
* The reachable-function assertion becomes a **two-name allowlist**, still
  enumerated by name and still exact, so a third function appearing in
  `app_private` under open default privileges fails. That is D57's property,
  which is what the assertion is for.
* `auth_service`'s LOGIN is admitted **only when the document publishes an
  application route**, keyed to the event rather than to the session number for
  the reason ADR 0090 records: a proxy and the thing it stands for come apart,
  and D280 is what that costs.
* The PEM scan excludes **one path**, derived from `render-jwks.py`'s own
  constants, so a bootstrap key copied into the auth service's directory under
  any other name is still found.

## Alternatives rejected

**Relax each assertion to a subset check.** `memberships >= activated`,
`others ⊆ {…}`, "some PEM is allowed" — four one-word changes, and each turns a
proof that says *exactly what is granted* into one that says *at least what is
granted*. The next role granted by accident would pass all four.

**Delete the four and rely on Session 6's own proofs.** The Session 6 proofs
assert the new facts positively; none of them asserts that *nothing else* was
granted, which is the half these four carry.

**Key `auth_service` to `deployed_through_session >= 6`.** Rejected for the
reason ADR 0090 gives at length: it is the same shape as `SEC-BOOT-001`'s
retired session comparison, which turned a green proof red for a correct
deployment.

## Consequences

The four proofs now fail if the boundary moves **again** without the authority
moving with it, which is what they were for. Two of them no longer restate a
value at all, so the class of failure they had is gone rather than postponed.

**None of this was found by review.** All four had been green for as long as
nobody ran them, and they went red within seconds of the first host gate. The
value of the run is not the four fixes; it is that four deliberate product
decisions had been unverified for four runs and nothing said so.
