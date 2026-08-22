# 0138 — A write agent may hold `meta:read`

Status: accepted
Date: 2026-08-22
Session: 9, Run 2
Affects: ADR 0006, ADR 0079, ADR 0100, ADR 0116, ADR 0120, ADR 0137,
`services/auth-api/app/scopes.py`

## Context

`ROLE_SCOPES` maps a role suffix to the largest scope set a token naming that
role may carry. It decides the **ceiling**, not what any subject holds: a
subject's scopes come from a server-side record, which is the whole of
`API-ADMIN-001`.

The two agent ceilings were written in Session 6, before any agent tool existed:

```
agent_reader: {notes:read, tasks:read, meta:read}
agent_writer: {notes:read, notes:write, tasks:read, tasks:write}
```

`meta:read` is in one and not the other. Nothing recorded why, and the asymmetry
was invisible for three sessions because no token could name either role.

Session 8 gave `meta:read` a job. The two metadata tools — `list_resources` and
`describe_resource` — require it, and they are the only way an agent can ask
which resources exist, what columns they expose, which filters are permitted and
what the row ceiling is. `_resource_for` refuses `describe_resource` without the
scope, and `list_resources` returns an empty resource list.

## The part that matters

A ceiling that omits a scope does not withhold that scope from a subject —
**it makes the scope unrequestable by any token naming the role.** Those are
different things, and only one of them was intended anywhere.

So as written, an `agent_writer` token could be authorized to change rows and
structurally unable to ask which rows it may change. It would discover the
surface by trying operations and reading refusals, which is the interaction this
whole design exists to avoid: a caller learning a boundary by probing it.

Session 9 Run 5 makes this sharper. `tools/list` becomes scope-filtered
(`discoverable_by` gains its first production caller), so a write agent without
`meta:read` would be shown fewer tools *and* be unable to introspect the ones it
was shown.

## Decision

**`meta:read` joins `agent_writer`'s ceiling.**

```
agent_writer: {notes:read, notes:write, tasks:read, tasks:write, meta:read}
```

It is a ceiling, not a grant. An agent is still issued exactly the scopes its
server-side record names, so a write agent that should not introspect simply is
not given the scope — which is the per-subject decision ADR 0006 wanted, rather
than a per-role impossibility.

**Nothing else moves.** In particular `objects:read` and `objects:write` remain
absent from **both** agent ceilings, and absent from `$defs/agent_scope`, which
is the two-places property Session 7 built deliberately (ADR 0100): a ceiling
says what a token may carry, the schema says what a manifest may ask for, and
object storage wants both refusals.

## Alternatives rejected

**Leave it out and let a write agent hold `agent_reader`'s scopes via a second
token.** Two tokens for one agent doubles what revocation has to reach and makes
`SEC-REV-001` a claim about two credentials. The identity registry gives an agent
one role and one scope set.

**Remove `meta:read` from `agent_reader` too, making the asymmetry consistent.**
That is consistency bought by deleting a working capability. Introspection is
what makes a frozen surface usable, and ADR 0120 built the two metadata tools
precisely so it does not require a database round trip.

**Treat introspection as implied by being an agent, and drop the scope.** ADR
0006 rejected exactly this: a vocabulary where authority follows from the kind of
caller rather than from an enumerated grant. `meta:read` exists so that "may read
the shape of the API" is a decision recorded per subject.

## Consequences

The scope vocabulary is unchanged — `meta:read` was already a member of
`$defs/agent_scope`, so no schema moves and `assert_classes_partition_the_vocabulary`
is unaffected.

`scope_registry.ROLE_SCOPES` is an alias to this dictionary rather than a copy, so
there is one authority and this ADR moves one line. That aliasing is itself a
Session 6 decision made after a test compared two constants and passed.

A write agent minted before this change carries whatever its record said and is
unaffected; a new one may be issued `meta:read` and will then see the metadata
tools that Run 5's discovery filter shows it.
