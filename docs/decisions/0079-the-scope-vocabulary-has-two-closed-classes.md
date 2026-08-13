# 0079 — The scope vocabulary has two closed classes, in one authority

Status: accepted
Date: 2026-08-13
Session: 6, Run 3
Extends: [0006](0006-capability-scopes.md), [0049](0049-one-scope-vocabulary.md)
Affects: API-ADMIN-001, AGT-SCOPE-001, AGT-DRIFT-001

## Context

Session 6 needs an administrative scope. `API-ADMIN-001` is *"admin endpoints
require an explicit scope, not a role name; a `project_admin` without the scope
is refused"* — so the scope has to exist, and it has to be nameable in a token.

The Session 6 runbook puts the new names in a new file, `contracts/auth-scopes.yaml`.
D220 refused that: ADR 0006 makes `schemas/capabilities.schema.json` the sole
authority, in its own words *"the code carries no second copy"*, and ADR 0049 is
titled *One scope vocabulary*. D220's instruction was therefore to add the names
to that schema's enum.

**Following that instruction literally would have been wrong**, and the reason
is one line of the schema:

    "required_scopes": { ..., "items": { "$ref": "#/$defs/scope" } }

`$defs/scope` is referenced by exactly one place: what an **agent capability
manifest** may request. So "the approved vocabulary" and "what a tool may ask
for" are the same list, and adding `admin_users:write` to it would widen the
second while meaning to widen only the first.

ADR 0006 rejected pattern-validated scopes with this sentence: *"it accepts
`notes:delete` and `admin:everything`, which is precisely the drift
`AGT-DRIFT-001` exists to prevent."* One enum serving both purposes reintroduces
`admin:everything` by a different route — not through a permissive pattern, but
through a list whose two jobs nobody had separated because it had only ever had
one.

ADR 0049 refused `openapi:read` on a related ground: it *"would be a sixth scope
naming a **surface** rather than a (resource, verb) pair, which breaks the rule
the enum states about itself."* An administrative scope names a surface too — the
auth service's own — so the enum's stated rule does not cover it either.

## Decision

**One authority, two closed classes.**

- **`$defs/scope`** is every approved name: the union.
- **`$defs/agent_scope`** is the data class, and `required_scopes` binds to *it*.
- The **administrative class is derived** as the complement, in
  `scope_registry.administrative_scopes()`, so the four names are written once.

Each class stays closed by its own thing, and that is the substance rather than
the bookkeeping:

- the **data** class is one per (frozen-domain resource, verb) plus `meta:read`,
  closed by ADR 0003 and growing only when ADR 0003 is superseded — unchanged;
- the **administrative** class is one per (platform identity resource, verb) over
  the auth service's own surface, closed by that surface.

The four names are `admin_users:read`, `admin_users:write`, `admin_agents:read`,
`admin_agents:write`. Two segments, like every other scope, and split by verb for
the reason ADR 0049 gives for splitting the data scopes: a token can hold read
without write, which is what makes a ceiling enumerable rather than asserted.

**The `admin_` prefix is documentation, not enforcement.** What keeps an
administrative scope out of a tool manifest is the `$ref`, and what a test
asserts is set membership. ADR 0006's own argument applies to prefixes as it does
to patterns: a name can say a scope looks administrative; it cannot say one was
approved.

**`src/agentic_postgres/scope_registry.py` maps role → ceiling**, and it is a
mapping rather than a vocabulary: every name is checked against the schema on the
way out, so a name the schema does not admit raises where it is read. It records
the *largest* set a token naming a role may carry — never what a subject holds,
which comes from a server-side record. That distinction is `API-ADMIN-001`: the
role never implies the scope.

A role no token may name is **absent**, and asking about one raises.
`bin/dev-token.py` had already made that choice, in a comment: *"a command that
offers the option invites somebody to find out."* It is now a check.

## Alternatives

**Add the names to `$defs/scope` and leave `required_scopes` pointing at it**,
as D220 said. Rejected on reading the `$ref` — it silently widens the agent
capability surface, which is the one thing ADR 0006 was written to prevent.

**A separate `contracts/auth-scopes.yaml`**, as the runbook says. Rejected: the
second authority, and it would also define scope *names*, so the two files could
disagree about what a scope is called.

**Name them `admin:users` and `admin:agents`**, as the runbook does. Rejected on
ADR 0049's own ground: those are coarser than the data scopes they sit beside — a
token holding `admin:users` could both read and write users, while a token
holding `notes:read` cannot write notes. An authorization model that is finer for
the low-privilege half is the wrong way round.

**`agent:read` / `agent:write`**, also from the runbook. Rejected: an agent's
token carries scopes over the resources it touches, not a scope naming what kind
of caller it is. ADR 0049's "per resource, not per surface" settles it, and
`AGT-SCOPE-001` depends on that shape.

**`admin:docs`**, also from the runbook. Not needed: ADR 0049 gave the
documentation role exactly `meta:read`, and `/docs/app` is a second surface of the
same service reading the same kind of thing.

## Consequences

- `test_scope_vocabulary_lives_only_in_the_schema` is **replaced by a stricter
  pair**, which this ADR authorises. The old assertion pinned `$defs/scope` to
  five names and could not have told an added data scope from an added
  administrative one; the new pair pins the data class, asserts the agent class
  is a *proper* subset of the union, and reads the `$ref` from the file.
- The `$ref` gets its own test. Repointing it at `#/$defs/scope` would restore
  the old behaviour while every other assertion here still passed: the vocabulary
  would be right, the classes would be right, and the capability surface would be
  wrong.
- **ADR 0049 is extended, and something about it is worth recording.** It states
  that "Session 5 issues bootstrap tokens carrying a `scope` claim, and the
  pre-request function validates it", and that permitted names "reach the
  pre-request function as non-secret `app.settings.*` values rendered from the
  schema's enum". **Neither was ever built** — `mint` signs no `scope`, and no
  `app.settings.scope_*` is rendered anywhere (D243). The decision was accepted
  and its subject does not exist. This ADR does not fix that; issuance is Run 7's
  and the hook's half is migration 0012's. It records it so the next reader is not
  the third person to assume it works.
- The registry's consumer today is `bin/dev-token.py`, which checks that every
  role it offers is one a token may name. Nothing yet *signs* a scope claim — and
  that is stated rather than implied, because a registry nothing reads is the
  defect this session has now recorded three times.
