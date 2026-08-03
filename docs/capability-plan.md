# Capability plan

Planned agent tools and their owning sessions. **Nothing here is active.**

This file exists so that `capabilities.yaml` can stay empty and still not lose
the plan. Putting planned tools in the active manifest — even disabled — invites
someone to flip a flag, and the manifest is the thing that decides what an agent
can reach.

The separation is the point: growing the API must not grow the agent surface.
Adding a REST endpoint or an RPC changes nothing until someone edits
`capabilities.yaml`, and `AGT-DRIFT-001` proves it.

## Catalog

| Planned tool | Kind | Intended backing operation | Required scopes | Session |
|---|---|---|---|---:|
| `list_resources` | Read | MCP-owned adapter over approved OpenAPI metadata | `meta:read` | 8 |
| `describe_resource` | Read | MCP-owned adapter over approved OpenAPI metadata | `meta:read` | 8 |
| `query_resource` | Read | Structured PostgREST read constrained by frozen allowlists | `notes:read` or `tasks:read` | 8 |
| `run_report` | Read | One named PostgREST RPC | `notes:read`, `tasks:read` | 8 |
| `create_note` | Write | Named PostgREST RPC, one-to-one | `notes:write` | 9 |
| `update_task_status` | Write | Named PostgREST RPC, one-to-one | `tasks:write` | 9 |

`search_embeddings` is deliberately absent. pgvector being installed does not
imply an embedding service exists, and a tool that cannot be backed is not a
plan — it is a promise.

## Rules any entry must satisfy before it becomes active

Enforced by `schemas/capabilities.schema.json`, not by review:

1. The name matches the committed regex and is unique.
2. Every required scope is a literal from the approved vocabulary — the schema
   `enum` is the sole authority, and the code holds no second copy.
3. It references exactly one pre-existing operation by ID. No SQL, no SQL
   fragment, no raw PostgREST query string, no path, no runtime-selected name.
4. A read declares its resource, column allowlist, permitted filters and
   operators, ordering, and row ceiling. All frozen at deploy time, never
   derived per request.
5. A write maps one-to-one to one operation and declares its maximum affected
   rows and whether it is idempotent.
6. Audit redaction is explicit.
7. Limits cannot exceed the global ceilings; a project manifest cannot raise
   them.
8. Enabling it requires the referenced live OpenAPI operation to exist with a
   matching approved shape. In Session 1 no live contract exists, so any
   `enabled: true` entry fails with exit `5`.

## Scope vocabulary

`notes:read`, `notes:write`, `tasks:read`, `tasks:write`, `meta:read`.

One scope per (resource, verb) from the frozen example domain, plus one for
schema introspection. The vocabulary is closed by
[ADR 0003](decisions/0003-example-domain.md) and grows only when that ADR is
superseded — which is the same thing as saying the domain grew.

## What is deliberately not planned

- Any tool taking a query, filter expression, column list, or path from the
  caller.
- A generic mutation dispatcher, or any tool whose operation is selected at
  runtime.
- Schema-changing tools of any kind.
- Natural-language-to-SQL, under any framing.

These are not "later" items. They are outside the product; see
[the product contract](product-contract.md) § non-goals.
