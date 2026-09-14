# The agent tool catalog for this project

What THIS project's own agent surface offers: the tools its capability manifest
declares, compiled from its reviewed surface and committed beside it.

**The block below is generated** by `bin/render-mcp-catalog.py --project
<manifest>`. Regenerate rather than edit; `--check --project` catches a drift
and exits 5 (ADR 0201, D1309).

<!-- BEGIN GENERATED: mcp-catalog -->

Project `example`, from `projects/example/contracts/mcp-capabilities.canonical.json`.

**These are this project's own tools, and not the whole of what its deployment serves.** The release's are in [the release catalog](../../../docs/mcp-tool-catalog.md); a deploy compiles both into one lock (ADR 0201) and the deployed document publishes that lock's digest as `capability_contract_sha256`.

`query_resource` is a tool name the release serves too, over its own relations. The two are different authorizations under one name: a scope granted for one grants nothing for the other, and the lock carries both.

Contract `example-note-embeddings-agent-v1`, schema version 4: **2 tools** behind **2 capabilities**.

| Tool | Kind | Reads | Scopes | Timeout | Risk |
|---|---|---|---|---|---|
| `query_resource` | read | postgrest | `note_embeddings:read` | 5000 ms | low |
| `set_note_embedding` | write | postgrest | `note_embeddings:write` | 5000 ms | moderate |

Each tool's backing capabilities, with the version and lifecycle each declares. **A tool has no single version of its own**: `query_resource` is two authorizations behind one name (ADR 0120) and they move independently, so the list is the authority and the tool-level risk above is the only aggregate.

| Tool | Capability | Version | Lifecycle | Risk |
|---|---|---|---|---|
| `query_resource` | `query_note_embeddings` | 1.0.0 | active | low |
| `set_note_embedding` | `set_note_embedding` | 1.0.0 | active | moderate |

### `query_resource`

**`note_embeddings`** — capability `query_note_embeddings`, at most **100** rows, requires `note_embeddings:read`.

- Columns: `note_id`, `owner_id`, `embedding`, `updated_at`
- Filters: none
- Orderings: none

### `set_note_embedding`

**Write** — operation `rpc.set_note_embedding.post`, at most **1** affected rows, not idempotent, requires `note_embeddings:write`.

- Arguments, by name and in order: `p_note_id`, `p_embedding`
- Also required by the tool, and not part of the operation: `idempotency_key`, `dry_run` — the caller's own token for this operation. Send the same one to retry safely; the same key with different arguments is refused rather than deduplicated.
- Redacted from the audit record: `p_embedding`, `p_note_id`

<!-- END GENERATED: mcp-catalog -->
