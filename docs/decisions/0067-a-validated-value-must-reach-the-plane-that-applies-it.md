# 0067 — A validated value must reach the plane that applies it

Status: accepted
Date: 2026-08-12
Session: 5, Run 9
Amends: [0053](0053-outputs-version-5.md)
Affects: API-LIMIT-001

## Context

`api.rest.statement_timeouts` has existed since Run 1. `project.schema.json`
declares it with a bounded duration grammar. `config._validate_statement_timeouts`
refuses a role the platform does not derive and a value outside 100 ms – 60 s.
Its own schema description reads:

> a timeout set on a role nothing created is a setting that never applies and
> never says so.

**Nothing applied it.** `bin/postgres-bootstrap.py` — the only plane that may
`ALTER ROLE` (D102) — carried one hard-coded line, `ALTER ROLE <app_runtime> SET
statement_timeout = '30s'`, and nothing else. The manifest's values were
validated and then dropped at the rendering boundary, because the bootstrap
reads the *rendered document* and `renderedDatabase` had no field to carry them.

Measured on the deployed cluster:

```
 rolname                   | rolconfig
---------------------------+--------------------------------------------------
 apg_alpha_dev_app_runtime | {statement_timeout=30s, idle_in_transaction…=60s}
(1 row)
```

One row. `anon`, `authenticated` and `api_documentation` had no `rolconfig` at
all, under a manifest declaring `anon: 2s` and `authenticated: 5s`. A
30-second request through the REST plane ran until the connection died.

This is D192's shape a second time in one run: built, declared, validated, and
never wired to the thing that would act on it.

## Decision

**The rendered document carries the resolved timeouts, and the bootstrap applies
what it is given.** Outputs schema version 7 adds
`database.statement_timeouts`, required on both branches.

Three properties make it a single authority rather than a second one:

1. **Keyed by derived role name, not by manifest suffix.** The manifest keys by
   suffix because that is what an operator can write; `rendering.resolve_statement_timeouts`
   resolves each through `identity.roles` — the one authority ADR 0002 allows —
   and writes the result. The bootstrap never derives a name.
2. **The platform's own default travels as data.** `app_runtime`'s `30s` moved
   from a literal in the bootstrap to
   `rendering.DEFAULT_APP_RUNTIME_STATEMENT_TIMEOUT`. It is not a second answer
   to the manifest's question: the manifest says what a project wants, this says
   what the platform will not go without when the manifest is silent, and a
   manifest entry for `app_runtime` overrides it.
3. **The v6 → v7 migration validates rather than derives.** `statement_timeouts`
   is a required argument, like `documentation_role` in v5 → v6, and the step
   refuses a role the document does not already name and a value outside the
   strict duration grammar.

**And `--check` reads the far side.** `check_violations` now queries
`pg_roles.rolconfig` and compares what is set against what the document says,
reporting a role whose timeout is absent or stale. This is the half that was
missing and the half this ADR is actually about: the near side — issuing the
right SQL — was equally untested, and a plane that issues correct statements
against a cluster nobody inspects is the same silence one step later. The
comparison is against the catalog rather than against the statement list this
program would have built, which would only prove the program agrees with itself.
It is guarded on the role existing, for the reason the `CREATE` check beside it
is: a fresh cluster must describe itself as fresh rather than bury thirteen
missing roles under fourteen missing timeouts.

## Alternatives

**Pass the manifest to `bin/postgres-bootstrap.py`.** The wrapper already has
its path. Rejected: it would make the bootstrap a second reader of manifest
values, which is precisely what rendering exists to prevent, and the rendered
document would then describe a deployment whose role settings it does not
record.

**Apply the timeouts from a migration.** Rejected on D102: `ALTER ROLE` is
bootstrap-plane authority, and the migration plane is deliberately not a
superuser. A migration that tried would fail on a fresh cluster.

**Leave `app_runtime`'s literal in the bootstrap and add only the request
roles.** Rejected: two places would then decide statement timeouts, and the one
in code would be invisible to anyone reading the document.

## Consequences

- Deployed documents at version 6 stop validating until each project is
  redeployed — anticipated by ADR 0053, and the same cost v6 imposed.
- `API-LIMIT-001`'s time half becomes measurable for the first time. Its row
  half already passed. **It was measured, and it is false — see D198.** The
  timeout now reaches `pg_roles.rolconfig`, and a REST request never reads it:
  PostgreSQL processes a role's settings only at login, and PostgREST reaches
  its request role with `SET LOCAL ROLE`, which is not one. Measured with
  controls on both arms. This ADR is correct about its own boundary and stops
  one boundary short of the goal, which is the same defect it was written to
  record: **the far side of one plane is the near side of the next.** The
  decision about the carrier is D198's and belongs to its own ADR.
- **`--check` goes red against every cluster deployed before version 7**, and
  that is the intended reading: the timeouts are genuinely absent there. It is
  the first thing on the host that can say so.
- Three things this work has tests for that had none: `resolve_statement_timeouts`,
  `migrate_v6_to_v7`'s refusals, and `build_statements` — the whole bootstrap
  statement list had never been asserted on offline. Fourteen mutations red with
  paired controls green, one of which was green on the first pass because the
  fake catalog answered for a role it had been told did not exist (ADR 0065's
  rule, inside a test harness).
- **The general rule this run keeps re-learning**: a value that is declared and
  validated reads exactly like a value that is applied. Validation proves a
  manifest is *well-formed*, never that anything consumes it. Where a setting
  crosses a plane boundary, the test that matters is on the far side.
