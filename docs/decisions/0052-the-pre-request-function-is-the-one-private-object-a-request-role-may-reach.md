# 0052 — The pre-request function is the one private object a request role may reach

Status: accepted
Date: 2026-08-10
Session: 5, Run 1
Affects: SEC-PRIV-001, SEC-ANON-001, SEC-DBX-002, SEC-ROLE-001

## Context

PostgREST runs its `db-pre-request` hook **after** switching to the impersonated
role. So the function must be executable by `anon` and by every activated
request role — and `EXECUTE` on a function requires `USAGE` on its schema.

The function belongs in `app_private`: creating a fifth schema for one
operational function would widen the four-schema product contract to avoid
widening a grant, which trades a small permanent change for a smaller temporary
one.

That means granting `USAGE` on `app_private` to every HTTP caller including the
anonymous one — and **migration 0006 removed exactly that grant one session
ago.** `app_runtime` held `USAGE` on `app` and `app_private` until Session 4
took it away, because "direct table reach is the difference between a
compromised application seeing its own rows and seeing the shape of everything."

D103 is the measurement that makes this sharp. `has_table_privilege(app_runtime,
'app.notes', 'SELECT')` returns **true** while the read is denied, because the
schema `USAGE` is missing. Schema `USAGE` is the boundary that does the work.
Granting it back is therefore not a formality; it is the activation of every
table grant the role already holds in that schema, and it arrives in a diff that
reads as one line.

## Decision

**One function, granted by name, and the boundary is proved by attempting to
cross it.**

- `app_private.postgrest_pre_request()` is owned by the object owner, declared
  `SECURITY INVOKER`, and hardened with `SET search_path = pg_catalog, pg_temp`
  with every project object fully qualified.
- Request roles receive exactly `USAGE ON SCHEMA app_private` and
  `EXECUTE ON FUNCTION app_private.postgrest_pre_request()`. Nothing else.
- `PUBLIC` keeps nothing, and the closed default privileges in `app_private`
  stay closed, so a private object created by a later migration is not reachable
  by having been created.
- `app_private` is absent from `db-schemas` and from `db-extra-search-path`, so
  the function is callable and the schema is not addressable over HTTP.

**`SEC-PRIV-001` is proved behaviourally, not from the catalog.** For each
request role, the suite attempts:

- a `SELECT` from a private table — denied;
- a call of every other `app_private` function — denied;
- a `SELECT` from `app.notes` — denied for schema `app`;
- and, as the control that makes those mean something, a successful call of the
  pre-request function itself.

A catalog assertion would be checking the wrong thing in both directions: D103
measured a privilege bit that is true while the operation fails, and the
converse — a role that can reach an object through a grant nobody enumerated —
is what this ADR exists to refuse.

## Consequences

**The set of private objects a request role can name is enumerable and is
enumerated.** A contract test reads the `app_private` ACLs and fails on any
entry granting a request role anything other than the one `EXECUTE`. Adding a
private helper does not quietly become reachable; it fails the test that
enumerates them.

**Session 9's agent-status lookup does not extend this grant.** If it needs a
private table it adds a separately reviewed `SECURITY DEFINER` helper with its
own narrow `EXECUTE`, which is the same construction Session 3 used for the
write RPCs and which is safe there for the same reason: the base tables carry
FORCE row-level security, so the definer's own statements stay policy-checked
(D58). Granting a request role table access in `app_private` is refused.

**The anonymous role reaches a function and nothing else.** It has no `USAGE` on
`api`, no `SELECT` on the domain tables and no `EXECUTE` on the RPCs. What it
has is a role to be and a hook that refuses it with a stable challenge — because
an empty successful response is not a refusal, and `SEC-ANON-001` asserts the
status and the challenge rather than the emptiness.

**A pre-request function that cannot be resolved is a boundary that is not
there.** Run 1 measures what the locked PostgREST does when `db-pre-request`
names a missing function: fails closed is a deploy that stops, fails open is a
public API with claim validation silently disabled and every other check green
(D139). The grant in this ADR is worth nothing if the hook is skipped.

## Alternatives considered

**A fifth schema for operational functions.** Rejected: it changes the product's
four-schema contract permanently to avoid one bounded grant, and every reader
who has learned `api / app / app_private / extensions` would learn it again.

**`SECURITY DEFINER` on the pre-request function so no request role needs
`USAGE`.** Rejected — it does not work. `EXECUTE` still requires schema `USAGE`
whatever the function's security mode; definer rights change what the body may
do, not who may call it.

**Put the function in `api` where the roles already have `USAGE`.** Rejected:
`db-schemas = "api"` means everything in `api` is a candidate for exposure, and
the surface contract would then have to carry an entry whose whole purpose is to
say "not this one". A function that must never be addressable over HTTP does not
belong in the schema that is addressable over HTTP.

**Grant `USAGE` on `app_private` and rely on the closed default privileges.**
Rejected as the whole decision, though the closed defaults are kept as defence
in depth. Defaults constrain what a *future* object inherits; they say nothing
about what is granted today, and D103 is the demonstration that the two are
routinely confused.
