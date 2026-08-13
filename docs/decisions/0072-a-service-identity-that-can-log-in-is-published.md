# 0072 — A service identity that can log in is published

Status: accepted
Date: 2026-08-13
Session: 5, Run 10
Amends: [0046](0046-a-nologin-stub-is-a-fact-with-an-expiry-date.md), [0041](0041-two-transports-three-access-profiles.md)
Affects: SEC-DB-002

## Context

`test_only_the_activated_roles_may_log_in` compares the roles that hold `LOGIN`
in the catalog against the set the deployed document describes, and fails on any
difference in either direction. ADR 0046 is why it exists: a role is `NOLOGIN`
until its owning session activates it deliberately, and a role that acquires
`LOGIN` some other way is the thing worth catching.

It derived the expected set from `database.access_profiles`, which was correct
for Session 4. Session 5 activates `postgrest_authenticator` — the identity
PostgREST authenticates as — and **an access profile is not what that is**.
Profiles are the transports a developer or an application reaches the cluster
through: `runtime_pooled`, `runtime_direct`, `migration_direct`. A service's own
login is a different kind of fact and had nowhere to be recorded.

So a role that can authenticate to the cluster was activated, correctly, and
invisible in the document that describes the deployment.

The gate found it on its first run. The test lives in `tests/security/`, which
`pytest tests/deployment -m live_host` does not select, so **five host runs
passed without executing it once** — the D193 shape, in a directory rather than
behind a marker.

## Decision

**The expected login set gains a third clause, derived from the published REST
route.**

    expected = {migration_user}
             ∪ {profile.role for available profiles}
             ∪ {postgrest_authenticator if routes.rest.status == "ready"}

The role's *name* comes from `database.roles`, as every name in this suite does.
What is new is the *condition*, and it is a statement the document already makes:
a deployment whose REST route is published has a service logging in as that
role; one whose route is not, does not.

**Naming the role as an exception was the alternative and it is the weakening
this repository forbids.** `expected | {roles["postgrest_authenticator"]}`,
unconditional, would pass on a Session 4 deployment that had somehow activated
it — which is precisely the case ADR 0046 wrote this test for. The test would
have kept its name and stopped being the thing it is named after.

## Alternatives

**Publish `database.activated_logins` as an observation.** Outputs version 9,
listing every role the bootstrap activated. Rejected, and the reason is worth
recording: the deploy would populate it *by querying the catalog*, so the test
would compare the catalog against a copy of the catalog. That is the D173
tautology — an assertion that cannot fail in the direction it is written for.

**Make the authenticator an access profile.** Rejected: a profile carries a
transport and a `password_secret_ref` for an operator or an application to
*use*. The authenticator is not something anyone connects as; publishing it that
way would invite exactly that.

**Derive from `deployed_through_session >= 5`.** Rejected as a version check
standing in for a fact. A deployment can be recorded as session 5 and be
mid-deploy with no route; the route's own status is the narrower statement, and
it is the one the plane actually depends on.

## Consequences

- The test is stricter than before in one direction and unchanged in every
  other: an authenticator with `LOGIN` and no published route now **fails**,
  where previously the whole assertion was simply wrong.
- **`tests/security/` is not covered by the deployment sweep**, and this is the
  second time that has cost a run — it is how this defect survived five of them.
  The gate is the only thing that runs it. That is a gap in the *habit* rather
  than in the harness, and it belongs in Run 10's notes: `-m live_host` is not
  "the host tests".
- The rule generalises past this role: **a session that activates a login must
  publish something that implies it.** Session 6's auth service will activate
  another one, and the question to ask then is what document statement makes it
  visible — not whether to add a second exception here.
