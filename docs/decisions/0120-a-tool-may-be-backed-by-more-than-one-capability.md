# 0120 — A tool may be backed by more than one capability

Status: accepted
Date: 2026-08-19
Session: 8, Run 3
Affects: ADR 0003, ADR 0006, ADR 0079, ADR 0100, ADR 0119, D403,
`schemas/capabilities.schema.json`, `capabilities.example.yaml`,
`docs/capability-plan.md`, `src/agentic_postgres/capability_compiler.py`

## Context

Two documents describe the same surface and count it differently.

`docs/capability-plan.md` names **four tools**, and the Session 8 plan repeats
them in §6 and asserts them in Run 6: *"exactly four tools registered, names
asserted lexicographically."* One of them is `query_resource`, whose scopes are
listed as *"`notes:read` or `tasks:read`"* — one tool, two resources, and the
word "or" is doing real work.

`capabilities.schema.json` v1 makes a capability the unit of **one** operation:
`name` is documented as *"Stable MCP tool name"*, `resource` is a single string,
and `required_scopes` is a list every member of which is required. There is no
way to say "notes with `notes:read`, or tasks with `tasks:read`" in one entry,
and the two ways to force it are both wrong:

* one entry with `required_scopes: [notes:read, tasks:read]` demands **both**,
  so an agent holding only `tasks:read` could query neither;
* one entry with `resource` widened to a list changes a member's meaning, which
  is a `schema_version` bump under D403's rule, to say something the scope
  vocabulary already says better.

**ADR 0079 is the shape that resolves it.** A scope is per `(resource, verb)`
precisely so it names what is being asked for rather than who is asking. The
authorization unit is therefore `(resource, verb)` — and a capability, which
carries `required_scopes`, is that unit. A *tool* is a name an agent calls.
Those are different things, and this session is the first time they differ.

## Decision

**A capability declares an optional `tool`. Absent, the tool is the capability's
own `name`.**

    list_resources      -> list_resources      (no `tool`)
    describe_resource   -> describe_resource   (no `tool`)
    run_report          -> run_report          (no `tool`)
    query_notes         -> query_resource      (`tool: query_resource`)
    query_tasks         -> query_resource      (`tool: query_resource`)

Five capabilities, four tools. The compiler groups by `tool`, and the grouping is
where the "or" becomes executable:

* the tool is **discoverable** when the caller holds the scopes of **at least
  one** backing capability (AGT-SCOPE-001);
* an **invocation** naming a resource is authorized against **that capability's**
  `required_scopes`, and no other;
* the `resource` argument's enumeration is the set of backing resources, frozen
  at compile time.

An agent holding only `tasks:read` therefore sees `query_resource`, may name
`tasks`, and is refused `notes` — which is what "notes:read *or* tasks:read"
meant.

**Capabilities sharing a tool must agree on `kind` and `operation.source`**, and
the compiler refuses them otherwise. A tool that was a read against one resource
and a write against another would be one name with two authorization models.

**`kind` gains `metadata`, and `operation.source` gains `lock`.**
`list_resources` and `describe_resource` read the deployed capability lock and
touch no backend at all. Declaring them `read` would have required `resource`,
`columns` and `max_rows` — three fields describing a database query they never
make, and the only way to fill them is to invent them, which is D267's rule
about measurements applied to a manifest. A `metadata` capability is **forbidden**
those fields, so "this tool cannot reach a backend" is a property of the schema
rather than of the runtime's good behaviour.

**`schema_version` stays 1.** Nothing is renamed and nothing is removed; `tool`
is optional and every document without it means exactly what it meant before.
The only shipped manifest is `capabilities: []`. D403's rule is that a version
bump which renames nothing and removes nothing is a migration everyone pays for
and nobody needed.

## Alternatives rejected

**Four capabilities, four tools, and `query_resource` picks a resource at
runtime from a list the compiler derives.** This is the one that looks simplest
and is the one the whole design exists to prevent: the resource would be chosen
at request time from something other than a frozen per-resource authorization,
and the scope check would have to be reconstructed inside the runtime. **The
capability plan forbids a tool whose operation is selected at runtime**, and a
resource is half of an operation.

**Two tools, `query_notes` and `query_tasks`.** Honest, and it contradicts the
plan and the capability plan, which have named four tools since Session 1. It
also scales badly in the direction the domain is frozen against: a fifth
resource would be a fifth tool, and an agent's tool list would grow with the
schema rather than with its authority.

**Give the two metadata tools synthetic `resource` and `columns`.** It would
avoid touching the schema. It would also put values in a manifest that describe
nothing, and the next reader could not tell them from the ones that are real —
which is exactly what D267 says about a fabricated measurement in a comment.

**Bump to `schema_version: 2`.** Considered and refused for D403's stated reason.
Nothing renames, nothing is removed, and the one committed document is empty.

## Consequences

- **Four tools, five capabilities, and the arithmetic is checked.** The compiler
  emits both counts and the contract test asserts the tool names
  lexicographically — Run 6's assertion has something to assert against.
- **AGT-SCOPE-001 has two halves and they are different.** Discovery is filtered
  by the union; invocation is checked against the specific capability. A test
  that only exercised one would pass while the other was missing.
- **A metadata tool cannot acquire a backend by editing the manifest**, because
  the schema forbids the fields a backend needs.
- Session 9 adds `create_note` and `update_task_status` as `write` capabilities.
  They are one-to-one with an operation and need no `tool`, so this decision
  costs them nothing — and if a future write tool ever wanted two backings, the
  rule that a tool's capabilities share a `kind` is what would stop it.
