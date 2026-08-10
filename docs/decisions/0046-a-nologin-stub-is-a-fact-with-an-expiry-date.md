# 0046 — A NOLOGIN stub is a fact with an expiry date

Status: accepted
Date: 2026-08-10
Session: 4, Run 10
Amends: [0041](0041-two-transports-three-access-profiles.md)
Affects: DBX-MIG-001, SEC-OWNER-001

## Context

Session 3 created thirteen roles per project. Twelve are NOLOGIN stubs with a
null verifier; one — `migration_user` — is activated with a credential, because
the migration plane needs it. The plan's §6.3 says it plainly: every service
identity is a NOLOGIN stub **until its owning session activates it
deliberately**.

`test_only_the_migration_user_may_log_in` asserted the first half of that
sentence and never encoded the clause:

```python
assert observed in ("", roles["migration_user"]), observed
```

Session 4 Run 5 activated `app_runtime` with a credential. That is the whole
point of Session 4 — a pooled transport an application can authenticate to — and
it is what ADR 0041 decided and what
`20260808120006_app_runtime_least_privilege` implements. From that moment the
assertion above was false about a correct deployment.

**It did not go red for five runs, because nothing ran it.** Runs 5 through 9
measured the host with targeted invocations against `tests/deployment/`; the
Session 3 authorization module is `live_host` and lives under `tests/security/`,
so it was collected by no run between the activation and Run 10's first full
`--mode host` gate. The requirement it proves was reported as covered
throughout, by a matrix that lists node IDs rather than results.

## Decision

**The set of roles that may log in is derived from the deployed document, not
written into the test.**

```python
expected = {roles["migration_user"]} | {
    profile["role"] for profile in profiles.values() if profile["status"] == "available"
}
```

The test is renamed to `test_only_the_activated_roles_may_log_in`, which is what
it was always about, and the registry follows it.

This is a replacement, not a relaxation, and it is stricter in three ways:

1. **Equality rather than membership.** The old assertion's `""` branch accepted
   a cluster in which the migration user could not log in at all — a broken
   deployment reported as a passing security property.
2. **The catalog and the document must agree.** A role that gains LOGIN without
   being published as an access profile fails. A profile published as
   `available` whose role cannot log in fails. Neither was detectable before.
3. **Still closed against the other eleven.** Any other service identity gaining
   LOGIN fails, which was the original point and is unchanged.

`migration_user` remains in the expected set unconditionally, because it is
Session 3's own activation and this module runs against Session 3 and Session 4
deployments alike. On a Session 3 deployment no access profile is `available`,
so the expected set is exactly the one name the old assertion allowed.

## Consequences

**A Session N test that names a role is a fact with an expiry date.** Sessions 5
through 12 activate more identities — the auth service, PostgREST, FastMCP, the
agent roles. Each of those activations would have falsified this test again. It
now widens by itself, and only in step with what the deployment publishes.

**The gap this exposed is bigger than the test.** A P0 module went unexecuted
across five runs while its requirements were reported as covered, because the
runs that mattered used targeted selectors. The acceptance matrix lists node IDs,
not results; only an evidence document distinguishes "has a test" from "the test
ran and passed", and no evidence was written between Run 4 and Run 10. **The
lesson is procedural and belongs to the plan, not to this ADR**: a run that
activates a role runs the whole host suite, not the part it was working on.

**ADR 0041 gains an obligation.** Deciding that a session activates a role is
also deciding that every assertion about which roles are inert has to be checked.
That obligation is now discharged by derivation rather than by memory.

## Alternatives considered

**Add `app_runtime` to the allowed pair.** One line, and it would have passed.
Rejected: it is the same defect moved forward one session, and the next
activation pays for it again — with the same five-run delay before anyone finds
out, because the failure mode is not the test being wrong but the test not being
run.

**Delete the test as superseded by `SEC-DBX-002`.** `SEC-DBX-002` proves
`app_runtime` holds no ownership or DDL, which is a different property: a role
can be least-privileged and still be one of thirteen that should never have had
a credential at all. Deleting it would remove the only check on the other eleven.

**Assert against `secrets.required.yaml` instead**, on the grounds that a role
with a credential is a role with a materialized password. Rejected: that file is
the *declared* grant surface, and this test's value is that it reads `pg_roles`
on a running cluster. Deriving one measurement from another declaration is how
"a value that looked measured" happens.
