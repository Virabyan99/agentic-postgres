# 0029 — Request identity is a trusted transaction-local claim, not an authenticated one

- **Status:** Accepted
- **Date:** 2026-08-07
- **Session:** 3
- **Affects:** SEC-RLS-001, SEC-VIEW-001, SEC-FUNC-001

## Context

Forced row-level security needs to know who the caller is. Session 3 builds the
policies. Session 6 builds token validation, and there is no auth service until
then.

So Session 3 has to answer "who is the caller?" without being able to verify the
answer. The honest options are to defer RLS until identity can be verified, or
to build the policies now against an identity the database accepts on trust and
be explicit that trust is what it is.

Deferring is worse than it sounds. The schemas, the views, the write RPCs and
the default-privilege posture all have to be designed around the identity
mechanism; building them against no identity and retrofitting one in Session 6
means rewriting every policy and every test at the point where there is the most
to break.

The risk of building now is not technical. It is that a green RLS suite reads
like proof of authentication to anyone who did not build it — which is this
project's recurring defect in its purest form: a value that looked measured and
was not.

## Decision

Request identity is a **transaction-local claim**, set by the connecting service
and trusted by the database:

```sql
SET LOCAL app.user_id = '<uuid>';
```

Policies read it through `current_setting('app.user_id', true)`. The write RPCs
derive ownership from the claim and never from a parameter — a caller can say
who it is, and cannot say who owns the row it is creating.

Three properties make the claim safe to build on:

- **`SET LOCAL`, never `SET`.** The claim dies with the transaction. A
  connection returned to a pool cannot carry the previous caller's identity into
  the next request, which is the failure that would otherwise arrive with
  Session 4's pooler.
- **A missing claim denies, it does not default.** `current_setting(…, true)`
  returns `NULL` when unset, and every policy is written so that `NULL` matches
  no rows. There is no anonymous fallback and no "if unset, treat as owner".
- **The claim never crosses a privilege boundary.** Nothing reads
  `app.user_id` to decide *what a role may do*; it decides only *which rows a
  role may see*. Role authority comes from the catalog.

**What this does not claim.** Session 3 does not authenticate. Any process
holding a database credential can assert any `app.user_id`. `SEC-RLS-001` proves
that *given a claim*, rows are isolated by owner; it does not prove the claim is
authentic. That sentence belongs in `docs/database-security.md` and in the test
module's docstring, not only here.

## Consequences

Session 6 makes the claim authentic by deriving it from a validated token
instead of from the caller's assertion. Because the mechanism is already
transaction-local and already denies on absence, that change is confined to who
sets the GUC — the policies, views, and RPCs are untouched.

The security suite must be written so that its limits are visible in its own
output. A test named `test_user_a_cannot_access_user_b_rows` that passes while
Session 3 cannot authenticate anybody is accurate only if the reader knows what
"user" means here.

`SEC-JWT-001` and `SEC-CRED-001` remain Session 6 placeholders and are not
weakened, satisfied, or partially credited by anything in Session 3.

Enforced by:

- `SEC-RLS-001` — owner-scoped rows are isolated by owner under forced RLS
  (Run 6), including the case where the claim is absent
- `SEC-FUNC-001` — the write RPCs derive ownership from the claim, and a caller
  cannot choose another owner (Run 6)

## Alternatives considered

**A database role per application user.** Genuinely authenticated by PostgreSQL,
and RLS on `current_user` needs no claim at all. It makes user creation a
`CREATE ROLE`, puts an unbounded number of roles in a shared catalog, requires
`pg_hba.conf` regeneration per user, and is incompatible with a pooler. It also
contradicts ADR 0026's rule that role creation is a bootstrap-plane operation.

**`SET` instead of `SET LOCAL`.** Survives across statements, which is
convenient for a service issuing several queries per request. It also survives
being returned to a connection pool, so the next request inherits an identity —
a cross-user data leak with no failing test until a pooler exists.

**Defer RLS to Session 6, when identity is real.** Avoids the honesty problem
entirely. It also means the schema, views, RPCs and default privileges are
designed without the constraint that shapes all of them, and Session 6 becomes a
rewrite rather than a substitution.

**Have the database verify a signed token itself** via `pgcrypto` or a JWT
extension. Removes the trust gap now. It puts token validation — the thing
Session 6 is entirely about — inside migration SQL, where key rotation and
algorithm policy cannot be tested independently of the schema.
