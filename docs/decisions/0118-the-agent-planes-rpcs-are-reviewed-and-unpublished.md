# 0118 — The agent plane's RPCs are reviewed and unpublished

Status: accepted
Date: 2026-08-19
Session: 8, Run 2
Affects: ADR 0003, ADR 0048, ADR 0050, ADR 0058, ADR 0060, D274,
`contracts/postgrest-api-surface.yaml`, `schemas/api-surface.schema.json`,
`src/agentic_postgres/api_surface.py`,
`migrations/templates/0018-agent-read-plane.sql`

## Context

Migration 0018 creates two functions in schema `api`:

* `api.mcp_agent_context()` — the calling agent's own id, role, scopes,
  `authz_version` and owner.
* `api.owner_activity_report()` — the caller's own counts, under the caller's
  own RLS; `run_report`'s backing operation.

`api` is the one schema PostgREST exposes, so both are reachable over HTTP by
any role granted `EXECUTE`. That makes them part of the served surface, and
ADR 0050 says the served surface is described by one hand-written file whose
whole function is to be able to disagree with the catalog.

But the published OpenAPI document is generated with `openapi-mode =
follow-privileges`, read as `api_documentation`. What appears in it is decided by
that role's grants — not by what exists. So an object in `api` can be real,
reachable and **absent from every generated document**, which is precisely the
case ADR 0050's own schema description names: *"an object present in the database
and absent here is a release failure even when its grants keep it out of
OpenAPI — because the next grant change publishes it."*

## What was measured

The rig in ADR 0116. Two arms decided this one:

| arm | result |
|---|---|
| a human token calling `api.mcp_agent_context()` | `permission denied for function mcp_agent_context` |
| `anon` calling it | `permission denied` — the `REVOKE ... FROM PUBLIC` holds |

And one arm **argued the other way and was overruled**. The first draft granted
`owner_activity_report` to `authenticated`, because AGT-READ-001 compares an
agent's read against *"the equivalent PostgREST result"* and a human who gets
`permission denied` produces nothing to compare against. The rig reported it as a
failure and the reasoning was sound — about the proof.

**ADR 0003's example domain is frozen.** It is `notes`, `tasks`, `create_note`
and `update_task_status`, amended exactly once, by ADR 0048, for one additive
column. A read RPC that `authenticated` may call is a **fifth human operation**,
and adding one is superseding ADR 0003 — a decision about what the product is,
taken to make a test easier to write. The proof moved instead: the agent's report
is compared against **the rows the same principal reads**, which the rig then
measured as equal both ways (`2 2 1 1`), with a second owner reading `1 1 1 0` as
the control that the numbers are not constants.

That is the stronger comparison anyway. Two functions can be wrong in the same
direction; a count that disagrees with the rows it counts cannot be.

## Decision

**Both functions are named in `contracts/postgrest-api-surface.yaml`, in a new
`agent_rpcs` section, and neither is granted to `api_documentation`.** They are
reviewed without being advertised.

**The reviewed contract keeps naming every object in `api`.** ADR 0050's
invariant is unchanged: nothing exists in the exposed schema that the contract
does not name. What the new section adds is the *fact* that these two are
deliberately unpublished, in the file a reviewer reads.

**Three rules `api_surface.py` enforces**, because JSON Schema cannot:

1. An `agent_rpcs` entry takes **no arguments**. A stable, argument-free function
   is served by PostgREST over `GET` as well as `POST`, and the existing `rpcs`
   section forbids `GET` because *"it puts arguments in a query string and in
   every log and proxy cache between the caller and the database."* With no
   arguments there is nothing to put there — so the rule that made `GET`
   dangerous is the rule that makes it harmless here, and the schema requires the
   condition rather than trusting it.
2. `agent_rpcs` and `rpcs` **may not name the same function.** One list is the
   published surface and the other is deliberately not; a name in both is a
   contradiction the reviewer would have to resolve by guessing.
3. Every `agent_rpcs` name must be **absent from the approved OpenAPI snapshot**.
   This is the assertion that gives the section teeth: it is checked against the
   generated artefact, not against the intention. **D274 is why** — `/docs/rest`
   was proved at 401 and 200 for four runs and had never rendered, because
   nothing requested the script its own markup named.

`bin/api-contract.py`'s published comparison is unchanged and reads `relations`
and `rpcs` only, so the snapshot and the published surface still have to agree
exactly, in both directions.

## Alternatives rejected

**Publish them: grant `api_documentation` and add them to `rpcs`.** It would make
`api-contract --check` cover them directly, which is real value. It also
advertises agent-plane functions in the human REST document, which invites
exactly the reading the capability plan forbids — *the agent surface is the
capability lock, not the API* — and it would require re-capturing the canonical
snapshot against a live PostgREST, which no offline run can do. And for
`owner_activity_report` it is not available at all without superseding ADR 0003.

**Leave them out of the contract entirely.** Cheapest, and it makes ADR 0050's
invariant false: two functions would exist in the exposed schema that no reviewed
document names, kept invisible only by a grant. The next grant change publishes
them and nothing would have said so.

**A second contract file for the agent plane.** The surface file's own header
refuses it: *"a project that needs an object this does not name needs a reviewed
change here, not a second contract."* Two files describing one schema are two
places to forget.

**Make `owner_activity_report` VOLATILE so PostgREST serves only `POST`.** It
would let the function sit in the existing `rpcs` section unchanged. It is also a
false statement about the function — it reads and writes nothing — made to fit a
schema, and the next reader would have no way to tell it from a real one.

## Consequences

- **The published document does not change**, so no snapshot re-capture is
  needed and `api-contract --check` keeps passing offline.
- **A grant is now a reviewed thing.** Granting `api_documentation` `EXECUTE` on
  either function makes it appear in the snapshot, and rule 3 fails — which is
  the intended alarm, not an inconvenience.
- **ADR 0060's wart is not extended.** The document already advertises three
  methods that return 403; this session adds nothing to that list.
- Session 9's write tools map one-to-one to `create_note` and
  `update_task_status`, which are **published** RPCs in `rpcs`. The two sections
  will then both be populated, and the difference between them is the difference
  between a human operation an agent may also invoke and a function that exists
  only for the agent plane.
