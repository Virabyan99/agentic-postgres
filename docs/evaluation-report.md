# The evaluation report

What the evaluation harness asks of this deployment's agent surface, and
nothing about what it answered.

**The block below is generated** from
`contracts/snapshots/mcp/mcp-capabilities.canonical.json` and
`tests/evaluation-cases.yaml` by `bin/render-evaluation-report.py`, which is
what makes it an inventory of the cases rather than a description of somebody's
intention. Edit the contract or the case file and regenerate; editing the block
is overwritten on the next render and is caught by `--check` in the meantime,
and **the render refuses when a capability has no cases**, which is how a
capability added without them fails the gate and CI (ADR 0184,
`EVAL-HARNESS-001`).

## What a case is, and what it is not

**A derived case is generated from the contract, one adversarial case per
frozen field, and it carries an expectation and never a denial reason.** The
contract says what is permitted; a request the contract does not permit is
generated mechanically -- a column the allowlist does not name, an operator the
column does not permit, an ordering index past the frozen list, an argument the
reviewed function does not take, a malformed reserved parameter, a response
above a budget -- and the expectation is that the runtime refuses it. *Which*
boundary refused is observed when the case runs and is never written here,
because an adversarial case whose expected denial was written from the
implementation is a description of the implementation (D868).

**Three expectations exist, and the third is the one a first draft gets
wrong.** `permitted` and `refused` are the obvious two. `bounded` is for a
request the contract permits and bounds: a `limit` above `max_rows` is clamped
rather than refused (ADR 0127, D937), and a listing held on fewer scopes is
filtered rather than refused (D421). A harness that knew only two verdicts
would have called both of those defects.

**A written case is hand-authored and bound to the capability version it was
written against.** When a capability's version moves and its cases do not, the
case file is refused, the harness test fails, and so do the gate and CI. That is
what gives `version` a reader with consequences: before Run 9 the field reached
the lock and the audit row and constrained nothing.

**Derived and written cases are counted separately** and never summed. A count
that mixed them would let a capability with many derived cases and no written
one look reviewed.

**The report carries the contract's digest.** It is the same number the lock
records as `canonical_sha256` and the deployed document publishes as
`capability_contract_sha256`, so the live half of `EVAL-HARNESS-001` is one
comparison: the deployment serves the contract these cases were derived from.

**What the evaluation does with these.** `tests/contract/test_evaluation_harness.py`
runs every case against the agent plane's own request builders with a fake
upstream, records the outcome and the boundary that refused, asserts each
expectation, and asserts the stop condition the session plan fixed: the derived
adversarial cases are not all refused by the same first check. A case that
holds the scopes it needs and is refused by the scope check never reached the
field it targets.

---

<!-- BEGIN GENERATED: evaluation-report -->

Contract `notes-tasks-agent-v1` at schema version 3, digest `a67267b1884602331087563d06a5e7dcb8490cea5d0181847eeef215b6602728`.

**47 derived cases and 15 written cases** over 7 capabilities. Derived cases are generated from the contract, one adversarial case per frozen field; written cases are hand-authored and bound to the capability version they were written against (ADR 0184).

| Capability | Tool | Version | Derived positive | Derived adversarial | Written positive | Written adversarial | Fields the derived adversarial cases reach |
|---|---|---|---:|---:|---:|---:|---|
| `create_note` | `create_note` | 1.0.0 | 2 | 6 | 1 | 1 | `arguments`, `idempotency_key`, `max_affected_rows`, `max_response_bytes`, `required_scopes` |
| `describe_resource` | `describe_resource` | 1.0.0 | 3 | 2 | 1 | 1 | `required_scopes`, `resources` |
| `list_resources` | `list_resources` | 1.0.0 | 1 | 1 | 1 | 1 | `required_scopes` |
| `query_notes` | `query_resource` | 1.0.0 | 1 | 9 | 2 | 1 | `columns`, `filters`, `max_response_bytes`, `max_rows`, `order_by`, `required_scopes`, `resources` |
| `query_tasks` | `query_resource` | 1.0.0 | 1 | 9 | 1 | 1 | `columns`, `filters`, `max_response_bytes`, `max_rows`, `order_by`, `required_scopes`, `resources` |
| `run_report` | `run_report` | 1.0.0 | 1 | 3 | 1 | 1 | `max_response_bytes`, `max_rows`, `required_scopes` |
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
| `derived:describe_resource:positive:owner_activity_report` | `describe_resource` | positive | derived | `operation` | request | permitted |
| `derived:describe_resource:resources` | `describe_resource` | adversarial | derived | `resources` | request | refused |
| `derived:describe_resource:required_scopes` | `describe_resource` | adversarial | derived | `required_scopes` | request | refused |
| `derived:list_resources:positive` | `list_resources` | positive | derived | `operation` | request | permitted |
| `derived:list_resources:required_scopes` | `list_resources` | adversarial | derived | `required_scopes` | request | bounded |
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

<!-- END GENERATED: evaluation-report -->
