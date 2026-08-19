# 0116 — Session 8 activates the agent-reader role

Status: accepted
Date: 2026-08-19
Session: 8, Run 2
Affects: ADR 0052, ADR 0096, ADR 0100, D102, D266, D300, D301, D400,
`bin/postgres-bootstrap.py`, `migrations/templates/0018-agent-read-plane.sql`,
`tests/security/test_session3_authorization.py`,
`tests/contract/test_api_migrations.py`

## Context

`agent_reader` has existed since Session 3 as a NOLOGIN physical role with a
name, some grants and no way to reach them. `naming.ROLE_SUFFIXES` derives it,
migration 0001 gives it schema `USAGE` on `api`, 0004 gives it `SELECT` on the
two views and the two base tables — and the authenticator holds **no membership
in it**, so PostgREST cannot `SET ROLE` to it and no token can name it. The role
is a description of an intention.

Two passing tests say so in as many words, and both are worded as though this
were Session 9's work:

* `test_a_role_that_makes_no_request_cannot_address_the_private_schema` —
  *"The agent roles are Session 9's. They are not granted to the authenticator,
  so no token can name them, and a USAGE grant to a role that can never make a
  request would widen the private schema to buy nothing."*
* `test_the_private_schema_is_granted_to_the_request_roles_and_no_others` —
  *"The two agent roles are Session 9's and are deliberately not granted to the
  authenticator, so PostgREST cannot become either."*

Session 8 is the agent plane. Its whole content is an agent reaching data
through the same PostgREST path a human uses, which cannot happen while the one
role an agent token may name is unreachable.

## What was measured

A rig on the locked image, applying all eighteen released migrations **as
`migration_user` over TCP** — dbmate's route, not `psql -U postgres` on the
socket, which is the superuser route that let migration 0012 pass four sessions
of green proofs while being unappliable (D285). Every request made by connecting
as the **authenticator** and issuing `SET ROLE`, which is PostgREST's route: a
privilege refusal measured as a superuser measures nothing (ADR 0065/0066).

**23 measurements, 23 as designed**, arms interleaved with controls. The three
that decided things:

**The first draft granted the agent comparison helper to the agent role alone**,
reasoning that a human request never reaches the agent branch. The reasoning was
right and the conclusion was wrong. A token's `role` claim decides which role
PostgREST becomes and `token_use` decides which branch the hook takes; those are
**independent**, so every combination is reachable. A human token naming the
agent role was refused with

    ERROR: permission denied for function auth_claims_are_current

instead of `AP401`. **Correct outcome, false reason — D393 exactly**, arriving
through a missing grant rather than a missing row. Both helpers now go to all
five request roles, which is the rule 0013 already stated for its own: *"the
comparison helper, to every role that runs the hook."*

**The bootstrap plane's verifier restated the constant that exists to stop it
restating.** `AUTHENTICATOR_REQUEST_ROLES` was created in Session 6 Run 9
precisely so that `check_violations` would read the enumeration instead of
copying it — its docstring says so, and says that the copy is what reported the
product's own deliberate `project_admin` grant as a violation on the first host
gate (D301). The fix reached `role_statements`, which **grants**. It never
reached `check_violations`, which **verifies**, and which still carried
`("anon", "authenticated", "api_documentation", "project_admin")` as a literal.

**The forbidden half was a two-name literal**, `("agent_reader",
"agent_writer")`. Activating one would have left the other as the only
prohibited membership, and a third accidental one — `app_runtime`,
`auth_service`, `storage_service` — was forbidden by nothing at all.

## Decision

**Session 8 activates `agent_reader`.** The membership is granted by the
bootstrap plane (D102, D266) with `ADMIN FALSE, INHERIT FALSE, SET TRUE`, like
the other four; migration 0018 grants the privileges it needs to run the
pre-request hook. **`agent_writer` stays inactive and Session 9 owns it.**

**The two assertions are re-derived, not relaxed** (ADR 0096), and a third that
D400 did not name is re-derived with them.

**1. `test_a_role_that_makes_no_request_cannot_address_the_private_schema`.**
The set of roles holding `USAGE ON SCHEMA app_private` becomes the set of roles
that run the pre-request hook, derived from `AUTHENTICATOR_REQUEST_ROLES`
rather than listed. `agent_writer` still fails it — it is still not a request
role — and so does a *sixth* role that acquires the grant without acquiring a
membership.

**2. `test_the_private_schema_is_granted_to_the_request_roles_and_no_others`.**
Migration 0008's placeholders are unchanged and the assertion on them is
unchanged: 0008 grants what 0008 granted. What moves is the **docstring**, which
claimed the agent roles are Session 9's — a sentence that would have kept
passing while being false, which is the D374 shape and worse than a failure. The
assertion gains a second half naming migration 0018 as the one that extends the
grant, so the pair states the whole rule.

**3. `check_violations` reads `AUTHENTICATOR_REQUEST_ROLES`, and the forbidden
set is its complement over the project's own roles** — every declared role
except the authenticator itself and `object_owner`, whose relation to
`migration_user` is a different check. Session 9 moves one line and a fourth
unexpected membership still fails.

**The subset check is refused**, and naming it is the point. `granted ⊇
expected` would have made all three of these pass without an edit, and would
pass the next accidental grant forever. **D300 is this exact temptation, and it
arrived three times in one session.**

## Alternatives rejected

**Leave `agent_reader` inactive and give the MCP runtime its own database role.**
It would avoid touching two passing tests. It would also mean the agent plane
authorizes through a path a human never takes, which is the whole thing §6
question 3 warns about — and it would put a second authorization system beside
PostgREST, which the plan's first sentence forbids.

**Grant the authenticator membership in the migration.** `GRANT role TO role`
needs authority the migration plane does not hold (D102), and 0013 already
refused this for `project_admin` (D266). A membership granted in two places is
two authorities for the one thing that decides which roles a token may name.

**Activate `agent_writer` at the same time.** One migration, one bootstrap
change, and Session 9 would inherit a role that can already be assumed while the
write tools that justify it do not exist. A role that can be named and has
nothing to do is a privilege waiting for a caller nobody reviewed.

## Consequences

- **An agent token is assumable.** Everything downstream of `SET ROLE` — the
  hook, RLS, the tool surface — becomes reachable and therefore testable.
- **Three assertions now derive their expected set** from the constant the
  product grants from. The next activation edits one tuple.
- `bin/postgres-bootstrap.py` is idempotent, so the membership is established by
  the next deploy of either project. It is a **bootstrap-plane change on a live
  cluster** and belongs in the operator sequence, not in a migration.
- Session 9 inherits the pattern and the complement check. It adds
  `agent_writer` to one tuple, and every proof that mentions the agent roles
  moves with it because none of them names one.
