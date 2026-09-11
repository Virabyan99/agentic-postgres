# The evaluation report for this project

What the evaluation harness asks of THIS project's agent surface -- the
release's capabilities less the ones this project disables, plus its own --
and nothing about what it answered. The digest below is the one this project's
deployed document publishes as `capability_contract_sha256`.

**The block below is generated** by `bin/render-evaluation-report.py --project
<manifest>` from the joint contract and the written cases (the release's under
`tests/evaluation-cases.yaml`, this project's under `evaluation-cases.yaml`
beside its manifest, if any). Regenerate rather than edit; `--check` catches a
drift (ADR 0201, `EVAL-HARNESS-002`).

<!-- BEGIN GENERATED: evaluation-report -->

Contract `notes-tasks-agent-v1+example-note-embeddings-agent-v1` at schema version 4, digest `8483a687eaac9ae82b405bfdb50af8a4f0a51a2434a8689a35ed798a34d30871`.

**62 derived cases and 19 written cases** over 9 capabilities. Derived cases are generated from the contract, one adversarial case per frozen field; written cases are hand-authored and bound to the capability version they were written against (ADR 0184).

| Capability | Tool | Version | Derived positive | Derived adversarial | Written positive | Written adversarial | Fields the derived adversarial cases reach |
|---|---|---|---:|---:|---:|---:|---|
| `create_note` | `create_note` | 1.0.0 | 2 | 6 | 1 | 1 | `arguments`, `idempotency_key`, `max_affected_rows`, `max_response_bytes`, `required_scopes` |
| `describe_resource` | `describe_resource` | 1.0.0 | 4 | 2 | 1 | 1 | `required_scopes`, `resources` |
| `list_resources` | `list_resources` | 1.0.0 | 1 | 1 | 1 | 1 | `required_scopes` |
| `query_note_embeddings` | `query_resource` | 1.0.0 | 1 | 8 | 1 | 1 | `columns`, `filters`, `max_response_bytes`, `max_rows`, `order_by`, `required_scopes`, `resources` |
| `query_notes` | `query_resource` | 1.0.0 | 1 | 9 | 2 | 1 | `columns`, `filters`, `max_response_bytes`, `max_rows`, `order_by`, `required_scopes`, `resources` |
| `query_tasks` | `query_resource` | 1.0.0 | 1 | 9 | 1 | 1 | `columns`, `filters`, `max_response_bytes`, `max_rows`, `order_by`, `required_scopes`, `resources` |
| `run_report` | `run_report` | 1.0.0 | 1 | 3 | 1 | 1 | `max_response_bytes`, `max_rows`, `required_scopes` |
| `set_note_embedding` | `set_note_embedding` | 1.0.0 | 0 | 5 | 1 | 1 | `arguments`, `idempotency_key`, `required_scopes`, `requires_approval` |
| `update_task_status` | `update_task_status` | 1.0.0 | 2 | 6 | 1 | 1 | `arguments`, `idempotency_key`, `max_affected_rows`, `max_response_bytes`, `required_scopes` |

### Every case

| Case | Capability | Kind | Origin | Field | Probe | Expects |
|---|---|---|---|---|---|---|
| `derived:create_note:positive` | `create_note` | positive | derived | `operation` | request | permitted |
| `derived:create_note:required_scopes` | `create_note` | adversarial | derived | `required_scopes` | request | refused |
| `derived:create_note:arguments.unknown` | `create_note` | adversarial | derived | `arguments` | request | refused |
| `derived:create_note:arguments.missing` | `create_note` | adversarial | derived | `arguments` | request | refused |
| `derived:create_note:idempotency_key` | `create_note` | adversarial | derived | `idempotency_key` | request | refused |
| `derived:create_note:supports_dry_run` | `create_note` | positive | derived | `supports_dry_run` | request | permitted |
| `derived:create_note:max_affected_rows` | `create_note` | adversarial | derived | `max_affected_rows` | response | refused |
| `derived:create_note:max_response_bytes` | `create_note` | adversarial | derived | `max_response_bytes` | response | refused |
| `derived:describe_resource:positive:notes` | `describe_resource` | positive | derived | `operation` | request | permitted |
| `derived:describe_resource:positive:tasks` | `describe_resource` | positive | derived | `operation` | request | permitted |
| `derived:describe_resource:positive:note_embeddings` | `describe_resource` | positive | derived | `operation` | request | permitted |
| `derived:describe_resource:positive:owner_activity_report` | `describe_resource` | positive | derived | `operation` | request | permitted |
| `derived:describe_resource:resources` | `describe_resource` | adversarial | derived | `resources` | request | refused |
| `derived:describe_resource:required_scopes` | `describe_resource` | adversarial | derived | `required_scopes` | request | refused |
| `derived:list_resources:positive` | `list_resources` | positive | derived | `operation` | request | permitted |
| `derived:list_resources:required_scopes` | `list_resources` | adversarial | derived | `required_scopes` | request | bounded |
| `derived:query_note_embeddings:positive` | `query_note_embeddings` | positive | derived | `operation` | request | permitted |
| `derived:query_note_embeddings:required_scopes` | `query_note_embeddings` | adversarial | derived | `required_scopes` | request | refused |
| `derived:query_note_embeddings:resources` | `query_note_embeddings` | adversarial | derived | `resources` | request | refused |
| `derived:query_note_embeddings:columns` | `query_note_embeddings` | adversarial | derived | `columns` | request | refused |
| `derived:query_note_embeddings:filters.column` | `query_note_embeddings` | adversarial | derived | `filters` | request | refused |
| `derived:query_note_embeddings:order_by` | `query_note_embeddings` | adversarial | derived | `order_by` | request | refused |
| `derived:query_note_embeddings:max_rows` | `query_note_embeddings` | adversarial | derived | `max_rows` | request | bounded |
| `derived:query_note_embeddings:max_rows.response` | `query_note_embeddings` | adversarial | derived | `max_rows` | response | refused |
| `derived:query_note_embeddings:max_response_bytes` | `query_note_embeddings` | adversarial | derived | `max_response_bytes` | response | refused |
| `derived:query_notes:positive` | `query_notes` | positive | derived | `operation` | request | permitted |
| `derived:query_notes:required_scopes` | `query_notes` | adversarial | derived | `required_scopes` | request | refused |
| `derived:query_notes:resources` | `query_notes` | adversarial | derived | `resources` | request | refused |
| `derived:query_notes:columns` | `query_notes` | adversarial | derived | `columns` | request | refused |
| `derived:query_notes:filters.column` | `query_notes` | adversarial | derived | `filters` | request | refused |
| `derived:query_notes:filters.operators` | `query_notes` | adversarial | derived | `filters` | request | refused |
| `derived:query_notes:order_by` | `query_notes` | adversarial | derived | `order_by` | request | refused |
| `derived:query_notes:max_rows` | `query_notes` | adversarial | derived | `max_rows` | request | bounded |
| `derived:query_notes:max_rows.response` | `query_notes` | adversarial | derived | `max_rows` | response | refused |
| `derived:query_notes:max_response_bytes` | `query_notes` | adversarial | derived | `max_response_bytes` | response | refused |
| `derived:query_tasks:positive` | `query_tasks` | positive | derived | `operation` | request | permitted |
| `derived:query_tasks:required_scopes` | `query_tasks` | adversarial | derived | `required_scopes` | request | refused |
| `derived:query_tasks:resources` | `query_tasks` | adversarial | derived | `resources` | request | refused |
| `derived:query_tasks:columns` | `query_tasks` | adversarial | derived | `columns` | request | refused |
| `derived:query_tasks:filters.column` | `query_tasks` | adversarial | derived | `filters` | request | refused |
| `derived:query_tasks:filters.operators` | `query_tasks` | adversarial | derived | `filters` | request | refused |
| `derived:query_tasks:order_by` | `query_tasks` | adversarial | derived | `order_by` | request | refused |
| `derived:query_tasks:max_rows` | `query_tasks` | adversarial | derived | `max_rows` | request | bounded |
| `derived:query_tasks:max_rows.response` | `query_tasks` | adversarial | derived | `max_rows` | response | refused |
| `derived:query_tasks:max_response_bytes` | `query_tasks` | adversarial | derived | `max_response_bytes` | response | refused |
| `derived:run_report:positive` | `run_report` | positive | derived | `operation` | request | permitted |
| `derived:run_report:required_scopes` | `run_report` | adversarial | derived | `required_scopes` | request | refused |
| `derived:run_report:max_rows.response` | `run_report` | adversarial | derived | `max_rows` | response | refused |
| `derived:run_report:max_response_bytes` | `run_report` | adversarial | derived | `max_response_bytes` | response | refused |
| `derived:set_note_embedding:requires_approval` | `set_note_embedding` | adversarial | derived | `requires_approval` | request | refused |
| `derived:set_note_embedding:required_scopes` | `set_note_embedding` | adversarial | derived | `required_scopes` | request | refused |
| `derived:set_note_embedding:arguments.unknown` | `set_note_embedding` | adversarial | derived | `arguments` | request | refused |
| `derived:set_note_embedding:arguments.missing` | `set_note_embedding` | adversarial | derived | `arguments` | request | refused |
| `derived:set_note_embedding:idempotency_key` | `set_note_embedding` | adversarial | derived | `idempotency_key` | request | refused |
| `derived:update_task_status:positive` | `update_task_status` | positive | derived | `operation` | request | permitted |
| `derived:update_task_status:required_scopes` | `update_task_status` | adversarial | derived | `required_scopes` | request | refused |
| `derived:update_task_status:arguments.unknown` | `update_task_status` | adversarial | derived | `arguments` | request | refused |
| `derived:update_task_status:arguments.missing` | `update_task_status` | adversarial | derived | `arguments` | request | refused |
| `derived:update_task_status:idempotency_key` | `update_task_status` | adversarial | derived | `idempotency_key` | request | refused |
| `derived:update_task_status:supports_dry_run` | `update_task_status` | positive | derived | `supports_dry_run` | request | permitted |
| `derived:update_task_status:max_affected_rows` | `update_task_status` | adversarial | derived | `max_affected_rows` | response | refused |
| `derived:update_task_status:max_response_bytes` | `update_task_status` | adversarial | derived | `max_response_bytes` | response | refused |
| `written:list_resources:contract-id` | `list_resources` | positive | written | `operation` | request | permitted |
| `written:list_resources:reader-sees-only-what-it-may-use` | `list_resources` | adversarial | written | `required_scopes` | request | bounded |
| `written:describe_resource:orderings-carry-indices` | `describe_resource` | positive | written | `order_by` | request | permitted |
| `written:describe_resource:a-write-has-no-resource-to-describe` | `describe_resource` | adversarial | written | `resources` | request | refused |
| `written:query_notes:in-takes-a-list` | `query_notes` | positive | written | `filters` | request | permitted |
| `written:query_notes:a-hostile-value-stays-a-value` | `query_notes` | positive | written | `filters` | request | permitted |
| `written:query_notes:a-filter-value-may-not-be-a-document` | `query_notes` | adversarial | written | `filters` | request | refused |
| `written:query_tasks:is-null-takes-no-value` | `query_tasks` | positive | written | `filters` | request | permitted |
| `written:query_tasks:is-null-with-a-value-is-refused` | `query_tasks` | adversarial | written | `filters` | request | refused |
| `written:run_report:one-row` | `run_report` | positive | written | `max_rows` | request | permitted |
| `written:run_report:half-the-scopes-is-none-of-them` | `run_report` | adversarial | written | `required_scopes` | request | refused |
| `written:create_note:a-rehearsal-is-a-positive-call` | `create_note` | positive | written | `supports_dry_run` | request | permitted |
| `written:create_note:an-argument-may-not-be-a-document` | `create_note` | adversarial | written | `arguments` | request | refused |
| `written:update_task_status:transition` | `update_task_status` | positive | written | `arguments` | request | permitted |
| `written:update_task_status:a-key-with-a-space-is-malformed` | `update_task_status` | adversarial | written | `idempotency_key` | request | refused |
| `written:query_note_embeddings:the-scaffolds-read-takes-the-ceiling` | `query_note_embeddings` | positive | written | `max_rows` | request | permitted |
| `written:query_note_embeddings:a-filter-on-an-unfrozen-column-is-refused` | `query_note_embeddings` | adversarial | written | `filters` | request | refused |
| `written:set_note_embedding:a-rehearsal-is-refused-while-approval-is-required` | `set_note_embedding` | positive | written | `requires_approval` | request | refused |
| `written:set_note_embedding:an-argument-the-function-does-not-take` | `set_note_embedding` | adversarial | written | `arguments` | request | refused |

<!-- END GENERATED: evaluation-report -->
