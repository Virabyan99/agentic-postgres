# 0080 — A CHECK constraint passes when its expression is NULL

Status: accepted
Date: 2026-08-13
Session: 6, Run 5
Affects: SEC-JWT-001, API-ADMIN-001, and every future migration in this repository

## Context

Migration 0011 creates the identity registry. ADR 0078 requires a token's
`scope` to be a sorted, deduplicated array of non-null strings, and the database
should hold the same line — so that a row written by anything other than the auth
service is refused rather than trusted.

The obvious spelling is not accepted:

    CHECK (scopes = ARRAY(SELECT DISTINCT unnest(scopes) ORDER BY 1))
    ERROR:  cannot use subquery in check constraint

Measured against the locked `pgvector/pgvector:pg18` image (server 18.4). A CHECK
may *call* a function whose body contains the subquery, so the constraint became
`CHECK (app_private.is_scope_set(scopes))` with

    SELECT a = ARRAY(SELECT DISTINCT unnest(a) ORDER BY 1)

**That function accepted `ARRAY['a', NULL]`.**

Not a bug in the comparison. Array comparison with a NULL element evaluates to
NULL, and **a CHECK constraint is satisfied when its expression is NULL** — the
constraint is violated only on an explicit `false`. Three-valued logic, in the
one place where "unknown" has to mean "no".

The same measurement, run for the scalar case, gives the same answer:
`CHECK (v <> '')` accepts a NULL `v`. So on this server every emptiness check in
this repository has always depended on a `NOT NULL` beside it to mean anything —
which they all have, by convention rather than by a stated rule.

Measured with controls throughout: the shape without the fix accepts the NULL
element and refuses the unsorted array in the same run, so the acceptance is
about the NULL and not about the rig.

## Decision

**A CHECK constraint may not be able to evaluate to NULL.** Concretely, in this
repository:

1. Any function used in a CHECK returns `coalesce(<predicate>, false)`, so it
   cannot return NULL for any reason — including one nobody has thought of yet.
2. A predicate over a collection tests for NULL members explicitly. Here that is
   `array_position(a, NULL) IS NULL`, evaluated *before* the comparison.
3. `NOT NULL` sits beside every emptiness or format CHECK, and is now asserted by
   a contract test rather than left to convention.

`app_private.is_scope_set(text[])` is `IMMUTABLE STRICT PARALLEL SAFE` with
`SET search_path = pg_catalog, pg_temp`. Immutable because a CHECK cannot call a
volatile function; the pinned search path because a resolvable name is the whole
attack surface of a function the database calls on every write.

**Non-emptiness is a separate constraint.** `is_scope_set(ARRAY[]::text[])` is
true — an empty array is trivially sorted and deduplicated — so
`CHECK (array_length(scopes, 1) IS NOT NULL)` is its own line. Measured rather
than reasoned about.

## Alternatives

**Enforce the shape only in the auth service.** Rejected. The service is the only
thing that *should* write these rows, and a constraint that assumes so is a
constraint that documents an intention. The database is where "no row can exist
in this shape" is a fact.

**A `BEFORE INSERT` trigger that normalises the array.** Rejected on migration
0002's own ground: a trigger can be disabled by anyone who can ALTER the table,
which is why `project_identity` uses a primary key on a constant rather than a
trigger to enforce its single row. A constraint cannot be turned off without
leaving a trace in the catalog.

**A domain type with the check attached.** A reasonable option and not taken:
it moves the same predicate somewhere less visible to a reviewer reading the
table, and it would still need the NULL clause — the finding is about
three-valued logic, not about where the predicate lives.

## Consequences

- Migration 0011 ships with the NULL clause, and
  `test_the_scope_check_cannot_return_null` asserts both halves **by name**,
  because neither is visible to a reader who does not already know to look for
  them.
- `test_every_text_column_with_an_emptiness_check_is_also_not_null` makes the
  pairing a rule rather than a habit. It reads the template with comment lines
  stripped, for a reason worth recording: the first two versions of the
  neighbouring foreign-key assertion **matched the file's own explanation of the
  decision** — once in a `--` comment and once inside a `COMMENT ON ... IS`
  string literal. The assertion that cannot be fooled is the one about the
  construct (`REFERENCES app.`), not the one about the substring.
- **This applies backwards.** Every existing CHECK in `migrations/templates/`
  was written under the same server behaviour. They are correct today because
  every one of them sits beside a `NOT NULL` — checked while writing this — but
  that was convention, and it is now a test.
- All eleven migrations were applied in order to a cluster built from the locked
  image before this was committed, and the catalog was read back: five tables
  owned by `object_owner`, two functions in `app_private` with pinned search
  paths and no `SECURITY DEFINER`, no `PUBLIC` privilege anywhere, no function
  added to `api`, and `auth_service` holding schema `USAGE` with `SELECT` and
  `INSERT` on `app_private.users` both **false**.
