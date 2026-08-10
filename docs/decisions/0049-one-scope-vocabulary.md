# 0049 — One scope vocabulary, and it lives in the capability schema

Status: accepted
Date: 2026-08-10
Session: 5, Run 1
Extends: [0006](0006-capability-scopes.md)
Affects: SEC-ROLE-001, SEC-ANON-001, AGT-SCOPE-001

## Context

Session 5 issues bootstrap tokens carrying a `scope` claim, and the pre-request
function validates it. The runbook names three scopes Session 5 would recognise:
`api:read`, `api:write`, and `openapi:read`, rendered into `postgrest.conf` as
`app.settings.scope_api_read` and friends.

`schemas/capabilities.schema.json` already says, in its own description, that it
is "the sole authority for the approved scope vocabulary (implementation plan
decision C); the code carries no second copy." The vocabulary is exactly:

```
notes:read  notes:write  tasks:read  tasks:write  meta:read
```

and the schema records the rule for growing it: "one scope per (frozen-domain
resource, verb), plus `meta:read` for schema introspection. Grows only when
`docs/decisions/0003-example-domain.md` is superseded."

Three new names in a PostgREST configuration file would be a second vocabulary
in a second authority, four sessions before Session 8 has to reconcile them.

## Decision

**A token's scopes are drawn from the capability schema's enum. There is no
second vocabulary.**

- A reader token carries a non-empty subset of `notes:read`, `tasks:read`.
- A writer token carries a non-empty subset of `notes:write`, `tasks:write`.
- The documentation role carries exactly **`meta:read`**, which the schema
  already defines as introspection — precisely what `openapi:read` was invented
  to mean.
- `GET`/`HEAD` against a resource requires that resource's `:read` scope;
  `POST` to an RPC requires the `:write` scope of the resource it writes.
- A scalar or string `scope`, a duplicate entry, an empty entry, an unknown
  name, and a name outside the role's permitted set are each rejected.

The permitted names reach the pre-request function as non-secret
`app.settings.*` values rendered from the schema's enum, not typed into a
template. Adding a scope means editing `schemas/capabilities.schema.json`, which
is what ADR 0006 exists to force.

## Consequences

**Session 8 needs no mapping layer.** An MCP tool's `required_scopes` and the
scopes in a bearer token are the same strings, so an agent capability and an
HTTP request are checked against one vocabulary. A mapping between two
vocabularies is exactly where a scope quietly widens.

**Scope is per resource, not per surface.** `api:read` would have been one scope
over everything the API exposes; `notes:read` and `tasks:read` are two, and a
token can hold one without the other. That is strictly finer, and it is what
makes `AGT-SCOPE-001` — "a read-only agent cannot discover or invoke writes" —
enumerable rather than asserted.

**A rendered configuration cannot introduce a scope.** The names in
`postgrest.conf` are derived from the schema's enum and a contract test compares
the two sets for equality, so a template edit that invents a fourth name fails
offline rather than producing a token nothing refuses.

**`meta:read` gains a live consumer three sessions early.** It was written for
Session 8's schema introspection. The documentation role uses it for the same
thing — reading the shape of the API and none of its data — which is evidence
the scope was drawn at the right boundary rather than a stretch of it.

## Alternatives considered

**Mint `api:read` / `api:write` / `openapi:read` as the runbook specifies.**
Rejected: it creates the second authority ADR 0006 was written to prevent, in a
file that is neither reviewed as a capability surface nor validated against one.

**Add `openapi:read` to the capability schema.** Rejected: it would be a sixth
scope naming a *surface* rather than a (resource, verb) pair, which breaks the
rule the enum states about itself, and `meta:read` already covers it.

**Keep the token scopes out of the pre-request function entirely and rely on
role grants.** Rejected: role grants cannot distinguish a documentation request
from a data request by the same role, which is the whole reason the
documentation role's restriction is method- and path-scoped rather than
grant-scoped.
