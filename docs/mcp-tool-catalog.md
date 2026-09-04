# The MCP tool catalog

What an agent can do against this deployment, and nothing else.

**This table is generated** from
`contracts/snapshots/mcp/mcp-capabilities.canonical.json` by
`bin/render-mcp-catalog.py`, which is what makes it a description of the surface
rather than a description of somebody's intention. Edit the contract, or edit
`capabilities.example.yaml` and recompile it with `bin/mcp-contract.sh compile`;
editing the block below is overwritten on the next render and is caught by
`--check` in the meantime.

---

## What a tool is, and what it is not

**Six tools, and there are exactly six.** The runtime reads the deployed lock
at startup and validates it strictly: a tool the roster does not name, or an
unknown `schema_version`, fails the start rather than being ignored (ADR 0127).
Two of the six are `metadata` and answer from the lock in memory — they reach no
database and take no concurrency slot. Two are `read` and make exactly one
upstream request each. Two are `write`, each one-to-one with a reviewed RPC: a
write selects among nothing, projects nothing, and declares its side-effect
bound, its idempotency and its audit redaction in the contract (D470). The
bound is **1 affected row** on both, and that is the function's own shape —
each RPC returns a single composite row, not a set — rather than a ceiling
chosen to look safe (D487).

**Six is what the deployment serves; it is not what any one caller sees.**
`tools/list` is filtered by the caller's own scopes, so an agent holding
`meta:read` and `notes:read` is shown three names and an agent holding both
write scopes is shown six. The scope column below is what decides it, as a
disjunction of conjunctions — `query_resource` needs `notes:read` **or**
`tasks:read`, `run_report` needs both (ADR 0140, D421). **Hiding a name is not
the boundary**: a caller that knows a hidden name can still send it, and what
refuses the call is the same scope check, applied again when the tool runs.

**A caller supplies values. It never supplies syntax.** The operation is chosen
**by name from the lock**; columns, operators and orderings are checked against
frozen sets *before* a request is built; and each value is escaped for the one
position it occupies (ADR 0127). There is no input that accepts SQL, a SQL
fragment, a PostgREST query string, a path, an operation name, or an ordering
expression. An ordering is chosen by **index** into the list `describe_resource`
returns, because the permitted orderings are frozen and choosing one is not the
same feature as writing one. A write's arguments are the same rule on the other
verb: the contract declares them **by name and in order**, taken from the
reviewed surface contract, and a caller supplies values for exactly those names
— never a name of its own.

**An agent reads — and writes — its owner's rows.** A request runs under the
identity of the human who owns the agent (ADR 0117), through the same eight
row-level policies that govern that human — no policy was added or moved for
the agent plane. Both write RPCs **derive** ownership from that identity rather
than accepting it as an argument, so an agent cannot create a note or move a
task for anyone but its owner. An agent cannot see another owner's rows and
cannot see another agent's existence.

**Scopes are a disjunction of conjunctions.** `query_resource` needs *either*
`notes:read` *or* `tasks:read`; `run_report` needs *both*. A flat list cannot
tell those apart (D421), so the table below spells the operator out. Discovery
is filtered by what the caller holds, because a tool list that advertises what
it will refuse is a lie — and a resource the caller cannot reach is **refused
when called**, not merely hidden.

**Four budgets, bounded independently** (ADR 0129): the row ceiling below, which
a caller may only lower; a serialized-byte ceiling a caller cannot express at
all; the per-tool timeout below; and a bound on how many reads run at once,
sized as a share of PostgREST's connection pool.

**What a result never carries:** a token, an object key, a presigned URL, a
connection string, another agent's existence, or a row the caller's own RLS
would not have returned.

---

## The tools

<!-- BEGIN GENERATED: mcp-catalog -->

Contract `notes-tasks-agent-v1`, schema version 3: **6 tools** behind **7 capabilities**.

| Tool | Kind | Reads | Scopes | Timeout | Risk |
|---|---|---|---|---|---|
| `create_note` | write | postgrest | `notes:write` | 5000 ms | moderate |
| `describe_resource` | metadata | lock | `meta:read` | 1000 ms | low |
| `list_resources` | metadata | lock | `meta:read` | 1000 ms | low |
| `query_resource` | read | postgrest | `notes:read` OR `tasks:read` | 5000 ms | low |
| `run_report` | read | postgrest | `notes:read` AND `tasks:read` | 5000 ms | low |
| `update_task_status` | write | postgrest | `tasks:write` | 5000 ms | moderate |

Each tool's backing capabilities, with the version and lifecycle each declares. **A tool has no single version of its own**: `query_resource` is two authorizations behind one name (ADR 0120) and they move independently, so the list is the authority and the tool-level risk above is the only aggregate.

| Tool | Capability | Version | Lifecycle | Risk |
|---|---|---|---|---|
| `create_note` | `create_note` | 1.0.0 | active | moderate |
| `describe_resource` | `describe_resource` | 1.0.0 | active | low |
| `list_resources` | `list_resources` | 1.0.0 | active | low |
| `query_resource` | `query_notes` | 1.0.0 | active | low |
| `query_resource` | `query_tasks` | 1.0.0 | active | low |
| `run_report` | `run_report` | 1.0.0 | active | low |
| `update_task_status` | `update_task_status` | 1.0.0 | active | moderate |

### `create_note`

**Write** — operation `rpc.create_note.post`, at most **1** affected rows, not idempotent, requires `notes:write`.

- Arguments, by name and in order: `p_title`, `p_content`
- Also required by the tool, and not part of the operation: `idempotency_key`, `dry_run` — the caller's own token for this operation. Send the same one to retry safely; the same key with different arguments is refused rather than deduplicated.
- Redacted from the audit record: `p_content`

### `query_resource`

**`notes`** — capability `query_notes`, at most **200** rows, requires `notes:read`.

- Columns: `id`, `owner_id`, `title`, `content`, `created_at`, `updated_at`
- Filters: `created_at` (gt, gte, lt, lte); `id` (eq, in); `title` (eq, neq); `updated_at` (gt, gte, lt, lte)
- Orderings, chosen by INDEX rather than written: `created_at` desc, `created_at` asc, `updated_at` desc, `title` asc

**`tasks`** — capability `query_tasks`, at most **200** rows, requires `tasks:read`.

- Columns: `id`, `owner_id`, `note_id`, `title`, `description`, `status`, `created_at`, `updated_at`
- Filters: `created_at` (gt, gte, lt, lte); `id` (eq, in); `note_id` (eq, in, is_null); `status` (eq, in, neq); `updated_at` (gt, gte, lt, lte)
- Orderings, chosen by INDEX rather than written: `created_at` desc, `created_at` asc, `updated_at` desc, `status` asc

### `run_report`

**`owner_activity_report`** — capability `run_report`, at most **1** rows, requires `notes:read` AND `tasks:read`.

- Columns: `notes_total`, `tasks_total`, `tasks_pending`, `tasks_in_progress`, `tasks_completed`, `tasks_cancelled`, `latest_note_at`, `latest_task_at`
- Filters: none
- Orderings: none

### `update_task_status`

**Write** — operation `rpc.update_task_status.post`, at most **1** affected rows, idempotent, requires `tasks:write`.

- Arguments, by name and in order: `p_task_id`, `p_expected_status`, `p_new_status`
- Also required by the tool, and not part of the operation: `idempotency_key`, `dry_run` — the caller's own token for this operation. Send the same one to retry safely; the same key with different arguments is refused rather than deduplicated.
- Redacted from the audit record: nothing

<!-- END GENERATED: mcp-catalog -->

---

## Reaching the plane

The agent plane is published at **one** path, named by `routes.mcp` in the
deployed document. It accepts `token_use: "agent"` tokens and refuses anything
else **before any lookup** (ADR 0115) — an application access token is turned
away by the surface rather than by whatever it would have reached. It has no
health route at the edge: the readiness probe exists, answers on the container's
own socket, and is private by the **absence** of a Traefik router rather than by
a check (ADR 0128). Any `Origin` header is refused.

The transport is streamable HTTP, stateless: one POST is one complete exchange,
so there is no session to establish and none is kept. Replies are framed as
`text/event-stream`, and a client must accept **both** `application/json` and
`text/event-stream` — naming only the former is answered `406`.

The deployed document publishes the protocol revision the runtime **implements**
(a negotiated one is a fact about a client), the accepted token use, the
capability contract's digest, and the tool count. Read those rather than
inferring them from this page: they are what the running deployment says about
itself.

---

## What is deliberately absent

**No MCP resources, prompts, roots, sampling, elicitation or UI.** The surface is
tools, and adding a second kind of thing is a decision with its own ADR rather
than a default that arrives with a framework upgrade.

**No delete, and no general update.** The two writes are the frozen domain's
own narrow operations (ADR 0003): create one note, and move one task between
statuses through a compare-and-swap. Nothing deletes a row, nothing updates an
arbitrary column, and widening either is a change to the frozen domain rather
than an entry in a manifest.

**No storage.** `objects:read` and `objects:write` are human-only: the scope
vocabulary does not admit them for an agent, so no agent token can carry them
however it is minted (ADR 0100). An agent token presented to the storage surface
is refused, and that refusal is a property of the vocabulary rather than of one
agent's configuration.

**A durable audit record, and what it does NOT cover.** Every read and write is
recorded: `api.agent_audit_begin` before the work and `api.agent_audit_complete`
after, both `SECURITY DEFINER` and both taking **no principal** — the agent and
its owner come from the GUCs the pre-request hook set (ADR 0135). A write whose
record cannot be opened **does not happen**; a read's still answers, and the
asymmetry is a decision rather than an oversight (ADR 0141). **The two metadata
tools are not audited at all**: they reach no backend, and auditing them would
make discovery depend on the audit table.

Parameters are stored, **redacted per the contract's `audit_redact`** — a note's
body is not kept, its title is. That is the opposite of what telemetry carries:
one structured log line per call with the tool, resource, outcome, row count,
elapsed milliseconds, request id and the agent and owner ids, and **no token, no
fingerprint, no URL and no caller value**. Telemetry answers "what happened" for
an operator watching a running deployment; the record answers it for a
record-keeper, months later. They are not the same artefact (ADR 0130, D412).

**Two records per write, from two routes, and both are needed.** The agent plane
writes one; the write RPC writes another inside the write's own transaction. A
denied call never reaches the database and has only the first; a caller reaching
PostgREST directly never reaches MCP and has only the second. **Only the
database's can say `committed`** — a row written in the transaction it describes
goes with it when that transaction aborts (D489).

**A request id spans ingress → MCP → PostgREST → both records**, and since
Session 11 that is four legs rather than three. One id is minted per HTTP request
by the ASGI layer, stamped on the **response**, and forwarded on every upstream
call. Traefik's access log keeps it as `downstream_X-Request-Id` — measured
against the locked digest rather than read off a page — so the edge records an id
it did not invent (ADR 0160).

**Nothing reads an inbound `X-Request-Id`.** An id a caller chose would let one
agent stamp its actions with another agent's, so an operator reading the trail by
request would see the second agent's writes inside the first agent's request. A
caller may still send the header; the runtime ignores it.

**The database-written row carries the id too** since migration 0022 (D500,
ADR 0161), so the two records for one write join on it. A malformed header
records `NULL` and the write proceeds: an unguarded cast rolls the caller's own
write back to zero rows (D633), and a correlation field must never destroy the
operation it annotates.

> **Correlating by `request_id`? Read `agent_id` beside it.** A caller reaching
> PostgREST directly supplies the header that becomes its own `database` row's
> id, so such a row can carry an id another agent's request also used. It cannot
> forge `agent_id` or `owner_id` — both come from the GUCs the pre-request hook
> set — so the mismatch is visible on the row itself rather than hidden
> (ADR 0161, ADR 0135).

Nothing prunes the record: retention is undecided and remains nobody's decision.
