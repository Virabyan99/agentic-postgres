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

**Four tools, and there are exactly four.** The runtime reads the deployed lock
at startup and validates it strictly: a fifth tool, or an unknown
`schema_version`, fails the start rather than being ignored (ADR 0127). Two of
the four are `metadata` and answer from the lock in memory — they reach no
database and take no concurrency slot. Two are `read` and make exactly one
upstream request each.

**A caller supplies values. It never supplies syntax.** The operation is chosen
**by name from the lock**; columns, operators and orderings are checked against
frozen sets *before* a request is built; and each value is escaped for the one
position it occupies (ADR 0127). There is no input that accepts SQL, a SQL
fragment, a PostgREST query string, a path, an operation name, or an ordering
expression. An ordering is chosen by **index** into the list `describe_resource`
returns, because the permitted orderings are frozen and choosing one is not the
same feature as writing one.

**An agent reads its owner's rows.** A request runs under the identity of the
human who owns the agent (ADR 0117), through the same eight row-level policies
that govern that human — no policy was added or moved for the agent plane. An
agent cannot see another owner's rows and cannot see another agent's existence.

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

Contract `notes-tasks-agent-v1`, schema version 1: **4 tools** behind **5 capabilities**.

| Tool | Kind | Reads | Scopes | Timeout |
|---|---|---|---|---|
| `describe_resource` | metadata | lock | `meta:read` | 1000 ms |
| `list_resources` | metadata | lock | `meta:read` | 1000 ms |
| `query_resource` | read | postgrest | `notes:read` OR `tasks:read` | 5000 ms |
| `run_report` | read | postgrest | `notes:read` AND `tasks:read` | 5000 ms |

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

**No writes.** `agent_writer` exists as a role and is not activated; every tool
here is a read. Agent writes, the audit record they require, and the fail-closed
contract for a write whose audit record cannot be written are Session 9's.

**No storage.** `objects:read` and `objects:write` are human-only: the scope
vocabulary does not admit them for an agent, so no agent token can carry them
however it is minted (ADR 0100). An agent token presented to the storage surface
is refused, and that refusal is a property of the vocabulary rather than of one
agent's configuration.

**No durable audit.** What exists is telemetry: one structured record per tool
call, carrying the tool, the resource, the outcome, the row count, the elapsed
milliseconds and the agent and owner ids — and **no token, no fingerprint, no
URL and no caller value**. Telemetry answers "what happened" for an operator
watching a running deployment; an audit record answers it for a record-keeper,
months later, with a contract about what happens when it cannot be written. They
are not the same artefact (ADR 0130, D412).
