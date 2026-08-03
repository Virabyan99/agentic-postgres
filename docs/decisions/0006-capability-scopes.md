# 0006 — Approved scope vocabulary lives in the capability schema

- **Status:** Accepted
- **Date:** 2026-08-03
- **Session:** 1
- **Affects:** `CFG-013`, and the Session 8/9 agent requirements that consume it

> Transcribed 2026-08-04 from decision **C** of
> [the Session 1 implementation plan](../plans/session-01-implementation-plan.md).
> The decision was made and implemented in Session 1; only this record was
> missing, and `schemas/capabilities.schema.json` cited it as its source of
> truth.

## Context

Runbook §5.2 requires every capability to declare `required_scopes` drawn from
an "approved vocabulary" without stating what the vocabulary is or where it
lives. Two things had to be settled: the contents, and the authority.

The authority question is the load-bearing one. A scope name that exists in
code and in a schema is a scope name that will eventually exist in only one of
them, and the failure is silent — a manifest validates, and the runtime denies
a scope the operator can see written in the file.

## Decision

**The vocabulary is exactly five scopes:**

```
notes:read   notes:write   tasks:read   tasks:write   meta:read
```

One scope per (resource, verb) over the frozen example domain of
[0003](0003-example-domain.md), plus one for schema introspection, which is
what `list_resources` and `describe_resource` in runbook §5.3 need. The domain
is exactly notes and tasks, so the vocabulary is closed by 0003 and grows only
when 0003 is superseded.

**`schemas/capabilities.schema.json` is the sole authority.** The vocabulary is
expressed as a JSON Schema `enum` on the scope items. `src/` carries **no
second copy** — not a frozenset, not a literal, not a regex. Code that needs
the vocabulary loads the schema.

## Consequences

Makes easy:

- Validation is structural. An unapproved scope fails schema validation with a
  message naming the permitted values, before any semantic code runs.
- Adding a scope is one edit in one file, and it is visible in review as a
  change to the security surface rather than as a change to a helper module.

Makes hard:

- Code that wants to reason about scopes must read the schema rather than
  import a constant. That is the intended cost, and it is small: the schema is
  already loaded for validation.
- The vocabulary cannot vary per project. Deliberate — a per-project scope
  vocabulary is a per-project authorization model.

Enforced by the `$defs/scope` enum in `schemas/capabilities.schema.json` and by
`tests/contract/test_capabilities_manifest.py`.

## Alternatives considered

**A `SCOPES` frozenset in `src/agentic_postgres/config.py`.** Rejected: the
schema still needs the list for validation, so this creates two copies. The
question is never "should it be in code or in the schema" but "which one is
allowed to be wrong", and the answer has to be neither.

**Free-form scope strings validated by pattern only** (`^[a-z]+:[a-z]+$`).
Rejected: it accepts `notes:delete` and `admin:everything`, which is precisely
the drift `AGT-DRIFT-001` exists to prevent. A pattern says a scope is
well-formed; it cannot say a scope was approved.

**Deriving scopes from the OpenAPI document at validation time.** Rejected for
Session 1: there is no live API to derive from, and a vocabulary that changes
when an unrelated service is redeployed is not a contract.
