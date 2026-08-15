# 0091 — A released migration that cannot apply is corrected in place

Status: accepted
Date: 2026-08-15
Session: 6, Run 12
Affects: ADR 0065, ADR 0066, D57, D262, D266, `migrations/templates/0012`,
`migrations/templates/0013`, `migrations/released.lock.json`

## Context

Every released migration in this repository ends with the same refusal:

```sql
-- migrate:down
DO $$ BEGIN
  RAISE EXCEPTION 'AP900: released platform migrations are fix-forward only'
    USING HINT = 'Write a new migration. Do not roll this one back.';
END $$;
```

The rule is right and it is not in question here. A migration that has been
applied to a cluster is part of that cluster's history; editing it makes the
recorded digest disagree with what actually ran, and the repair for a mistake in
it is a new migration that corrects the end state.

The first Session 6 deploy hit a case the rule does not cover. Migration 0012
failed on a live host with

```
Error: pq: permission denied for function is_scope_set (42501)
```

and migration 0013 has the same defect. Both place `RESET ROLE;` **above** their
privileges block, so `REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app_private FROM
PUBLIC` and the `GRANT EXECUTE` statements that follow it run as the *connected*
role. On a host that is `migration_user`, which owns nothing — and both
statements require ownership. 0011 has the same two statements in the opposite
order and applies cleanly.

## What was measured

Against the locked `pgvector/pgvector:pg18`, applying the rendered set for a
real project key, with the roles and grants `postgres-bootstrap.py` establishes:

| applied as | result |
|---|---|
| `migration_user` — how dbmate connects on a host | **fails at 0012, line 396** |
| `postgres` — how every offline rig connects | passes all thirteen |

The superuser arm is the control, and it is also the finding: a superuser
bypasses the ownership check entirely, so no rig that used one could ever have
seen this. `tests/contract/test_auth_endpoints.py:155` applies migrations with
`psql -U postgres`, and every other offline migration rig does the same. That is
ADR 0065 and 0066's class — *a rig is a second configuration of the product* —
and this is its fourth instance and its most expensive, because it was found by
a deploy that took a live project's API down.

Both projects on the host were then read: `alpha-dev` and `beta-dev` are each at
**eleven** applied migrations. Neither has 0012 or 0013, and the deploy's whole
`up` runs in one transaction, so the failed attempt left nothing behind.

## Decision

**A released migration that no cluster has applied, and that cannot be applied,
is corrected in place.** 0012 and 0013 move `RESET ROLE;` to the end of their
`up` section, where 0011 already had it. `migrations/released.lock.json` is
re-frozen in the same commit.

The condition is not "we would rather not write another migration". It is that
**fix-forward is impossible here**, and that is a fact about this defect rather
than a preference:

* a new 0014 would have to run *after* 0012 and 0013;
* 0012 cannot be applied at all, so no cluster can ever reach 0014;
* therefore there is no state for a forward fix to correct.

The rule protects clusters that hold a migration. A migration that cannot be
applied has no such cluster, by construction — which was verified against both
deployed projects before this was written, not assumed.

## What makes this safe to state as a rule

Three conditions, all of which must hold, and all of which were checked:

1. **No cluster has the migration.** Read from `app_private.schema_migrations`
   on every deployed project, not inferred from the deploy's output — the deploy
   printed `Applied: …0012` for a transaction that then rolled back, so its
   output is not evidence.
2. **The migration cannot be applied**, so there is no forward path. A migration
   that merely did the *wrong thing* does not qualify: that one has clusters and
   gets a 0014.
3. **The lock is re-frozen in the same commit**, so the recorded digest and the
   file never disagree in any commit anyone can check out.

If any of the three fails, the answer is a new migration.

## Alternatives rejected

**Write 0014 and leave 0012 broken.** Impossible, as above. It would also leave
a released migration in the tree that is known not to apply, which is worse than
either option: the next operator meets the failure and has to rediscover that it
is expected.

**Grant the migration user ownership, or make it a superuser.** This would make
the existing files work unchanged, and it would delete the property the whole
migration plane exists to have — that migrations run with exactly the authority
the object owner has and no more (D102). It would also make the new test below
vacuous, since a superuser passes everything.

**Keep the superuser rigs and add a host-only proof.** The defect would then be
caught only by a deploy, which is what just happened. The point of the new test
is that it runs in a checkout.

## Consequences

`tests/contract/test_migrations_apply_as_the_migration_user.py` applies the
whole released set as `migration_user`, against the locked image, with the
pre-state built by `postgres-bootstrap.py::build_statements` — the product's own
bootstrap SQL rather than a second copy of it. It carries a control asserting
that the migration user is not a superuser, does not inherit the owner
(`pg_auth_members.inherit_option`, not `pg_roles.rolinherit` — the first draft
read the wrong catalog and failed against a correct rig), and does not own the
functions. Without that control the test would pass for reasons unrelated to the
migrations.

Mutation-tested by restoring the shipped defect in each file: both go red, both
controls green, both files byte-identical afterwards.

The existing rigs keep their superuser, deliberately. They measure what the
schema *does*, and re-plumbing them would be a large change to working tests for
a property this one module now owns.
