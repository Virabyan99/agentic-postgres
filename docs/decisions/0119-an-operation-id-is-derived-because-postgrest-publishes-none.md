# 0119 — An operation id is derived, because PostgREST publishes none

Status: accepted
Date: 2026-08-19
Session: 8, Run 3
Affects: ADR 0050, ADR 0058, ADR 0060, ADR 0118, D267,
`schemas/capabilities.schema.json`, `src/agentic_postgres/capability_compiler.py`,
`contracts/postgrest-api-surface.yaml`, `docs/capability-plan.md`

## Context

`docs/capability-plan.md` states the rule every capability must satisfy:

> 3. It references exactly one pre-existing operation by ID. No SQL, no SQL
>    fragment, no raw PostgREST query string, no path, no runtime-selected name.

and `capabilities.schema.json` v1 encodes it: `operation` is required, with a
required `operation_id` matching `^[A-Za-z][A-Za-z0-9_.-]{0,127}$`.

The sentence is right about what a capability must not contain. It assumes
something about the source that turns out to be false.

## What was measured

A live PostgREST on the locked image, against a cluster carrying all eighteen
migrations, configured as `compose.yaml` configures it —
`openapi-mode = follow-privileges`, `openapi-security-active`, the pre-request
hook — and captured **through a documentation-role token**, because the document
is built as the role of the request and an anonymous capture would describe
`anon`'s surface, which is nothing.

| question | answer |
|---|---|
| operations carrying an `operationId` | **none, anywhere** |
| document format | **Swagger `2.0`**, where `operationId` is optional |
| published objects | `notes`, `tasks`, `rpc/create_note`, `rpc/update_task_status` |
| `rpc/mcp_agent_context` published | **no** |
| `rpc/owner_activity_report` published | **no** |

The committed snapshot shows the same, but the snapshot is a *normalized*
capture — evidence about `openapi_normalize`, not about PostgREST. This was
measured on the live document for that reason.

The last three rows are ADR 0118's claim, and Run 2 asserted them from the
migration text and from the approved snapshot. **They are now measured against a
running PostgREST**, which is the only artefact that could have disagreed. The
four present objects are the control: a capture showing nothing would have
answered "absent" to every question and meant none of them.

## Decision

**An `operation_id` is derived from `(object, method)` by one function, and that
function is the single authority for the spelling.**

    <object with "/" replaced by ".">.<method>

    notes.get                       tasks.get
    rpc.create_note.post            rpc.owner_activity_report.post

`.` and `-` are the only punctuation the existing pattern allows, which is why
the separator is a dot rather than the `/` and `:` the wire uses.

**The reviewed surface contract is the authority a capability is checked
against, not the OpenAPI document.** `contracts/postgrest-api-surface.yaml` is
hand-written and can disagree with the catalog (ADR 0050); the document is an
observation. So the compiler resolves every capability's operation against the
reviewed contract's `relations`, `rpcs` and `agent_rpcs`, and refuses one that
names anything else.

**The OpenAPI snapshot is then read as a cross-check, in both directions.** A
capability backed by a `relation` or an `rpc` must appear in the approved
snapshot with that method; one backed by an `agent_rpc` must be **absent** from
it (ADR 0118). Reading it this way is exactly the line AGT-DRIFT-001 draws:
**the compiler may read the document and may never enumerate from it.** Nothing
in the compiler iterates the document's paths to discover a capability; it
iterates the *declared* capabilities and asks the document about each one.

**`run_report` names the `POST` form.** Its backing function is `STABLE` and
takes nothing, so PostgREST serves it over `GET` too (ADR 0118). The capability
names `post` because the runtime will use it, and because a `GET` on an RPC puts
whatever it carries into a query string — which is the objection the published
`rpcs` section already records, and which is only inapplicable to the *shape* of
this function, not to the habit.

## Alternatives rejected

**Configure PostgREST to emit operation ids.** There is no such setting, and
inventing one is not available. Swagger 2.0 makes the field optional and this
version emits it nowhere.

**Carry `method` and `path` in the capability instead of an id.** It would be
honest and it would change `operation_id`'s meaning, which is a `schema_version`
bump under D403's rule — and it would put a *path* in the capability manifest,
which the capability plan forbids in the same sentence that asks for an ID. A
derived id keeps the manifest free of paths and keeps v1.

**Let the compiler match capabilities to the document by shape.** Tempting,
because the document does describe each operation fully. It is also inference:
a capability would become whatever the document happened to contain, and
AGT-DRIFT-001 exists because adding an API operation must expose nothing.

**Write the ids by hand in the manifest with no derivation.** They would agree
with the surface contract until somebody renamed a view, and the failure would
be a capability pointing at nothing — reported, if at all, at deploy time.

## Consequences

- **Adding an operation to the API still exposes nothing.** The compiler starts
  from the declared capabilities; a new path in the document is not iterated
  over, and a new object in the reviewed contract is not either.
- **A renamed view fails at compile time**, because the derived id no longer
  resolves against the reviewed contract.
- The derivation is one function with one test, so the two sides of every
  comparison spell an object the same way — the rule `openapi_normalize` and
  `api_surface` already follow for `declared_objects`.
- ADR 0118's grant boundary is now **measured on the live artefact** rather than
  inferred from the migration, which closes the gap D274 names: a property that
  is true of a file and never checked against the thing the file produces.
