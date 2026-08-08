# 0035 — A check that could not fail

- **Status:** Accepted
- **Date:** 2026-08-08
- **Session:** 3
- **Affects:** `bin/postgres-bootstrap.py`, `bin/postgres-bootstrap.sh`,
  `bin/deploy-project.py`, `tests/security/test_session3_authorization.py`,
  DBX-PG-003, SEC-DB-001

## Context

`bin/postgres-bootstrap.sh --check` is the first command Run 7 runs against a
real cluster, and the script's header documents exit `6` as "`--check` found a
violation". `EXIT_CHECK_FAILED = 6` was defined in `bin/postgres-bootstrap.py`
and never raised. What `--check` did was print how many statements *would* run:

```
postgres-bootstrap: --check, 35 statements would run
  container      apg-alpha-dev-postgres-1
  identity       not yet bound
  roles declared 13
```

and return `0`. Against a cluster with no roles, no schemas, no extension and no
credential, it returned `0`. It could not go red.

The same shape appeared one layer up: `--apply` returned `0` when psql accepted
its statements. Run 4's finding — `ALTER DEFAULT PRIVILEGES` reporting success
and storing nothing — is the standing evidence that acceptance is not
establishment.

## Decision

**`--check` reads the catalog and names what is wrong; `--apply` reads it back.**

`check_violations` asks `pg_roles`, `pg_auth_members`, `pg_authid`,
`pg_namespace`, `pg_extension` and `has_database_privilege` — nine questions
whose answers are false when the fact is absent. It never inspects the statement
list this program would have run, which would only prove the program agrees with
itself. `--check` returns `6` with the list; `--apply` runs the statements and
then runs the same function, returning `6` if the cluster does not agree with
what was just applied.

Two things measured while writing it, both recorded because both are the kind of
thing that would otherwise be rediscovered:

* `has_database_privilege` **raises** on a role that does not exist, and an
  unhandled raise aborts the whole check. The first version reported a crash
  instead of the thirteen missing roles it was looking at. A check must be able
  to describe the state it is most often run against.
* `boolean || text` yields `true`/`false`. `t`/`f` is what psql *prints* in a
  table. The first expectation for the membership options was `'f f t'` and
  reported a violation against a cluster that was correct — the same defect in
  the other direction. Two Session 3 security assertions written in Run 6 had
  the same spelling, and had never run against a cluster.

## Consequences

The deploy can treat bootstrap's exit code as a verdict, which is what lets
`bin/deploy-project.py` run `--apply` as a step and stop when it fails.

`--check` on a fresh cluster returns `6` and lists nineteen violations. That is
the expected first result of Run 7 and is not a failure of the run.

A read-back that disagrees with what was just applied exits `6` from `--apply`,
which reads as "applied, and the cluster does not agree". That is a different
sentence from "could not apply", and both are worth being able to say.

## Alternatives considered

**Leave `--check` as a plan printer and rename it `--plan`.** Honest, and it
would have removed the exit code the header promises. But the operator question
at the start of Run 7 is "is this cluster in policy", and nothing else answered
it.

**Have `--check` re-run the statements in a transaction and roll back.** It
would report "no error" rather than "no divergence", would need write privilege
to answer a read-only question, and would say nothing about state the statements
do not touch.

**Compare against a snapshot recorded at the last apply.** That compares the
cluster to what this tool last believed rather than to what the rendered
document declares, and the two diverge exactly when something outside the tool
changed the cluster — the case worth catching.
