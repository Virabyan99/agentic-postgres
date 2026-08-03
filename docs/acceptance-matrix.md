# Acceptance matrix

<!-- GENERATED FILE. Do not hand-edit.
     Source: tests/acceptance-registry.yaml
     Regenerate: python bin/render-acceptance-matrix.py --write
     Verified in CI: python bin/render-acceptance-matrix.py --check -->

Every requirement below has at least one Pytest node ID that pytest can
actually collect. That is checked by running a real collection and
comparing node IDs, not by searching files for function names — a text
search passes on a commented-out test.

**67 requirements** — 63 P0, 17 active in Session 1, 50 owned by later sessions.

## By session

| Session | Requirements | Status |
|---:|---:|---|
| 1 | 17 | active |
| 2 | 2 | placeholders owned by Session 2 |
| 3 | 5 | placeholders owned by Session 3 |
| 4 | 5 | placeholders owned by Session 4 |
| 5 | 5 | placeholders owned by Session 5 |
| 6 | 5 | placeholders owned by Session 6 |
| 7 | 4 | placeholders owned by Session 7 |
| 8 | 6 | placeholders owned by Session 8 |
| 9 | 5 | placeholders owned by Session 9 |
| 10 | 5 | placeholders owned by Session 10 |
| 11 | 5 | placeholders owned by Session 11 |
| 12 | 3 | placeholders owned by Session 12 |

## Requirements

### Session 1

| ID | Priority | Guarantee | Proof |
|---|---|---|---|
| `CFG-001` | P0 | A project manifest validates against schema and semantics, and contains no secret material. | `tests/contract/test_project_manifest.py::test_example_manifest_is_valid`<br>`tests/contract/test_project_manifest.py::test_example_manifest_carries_no_secret_material` |
| `CFG-002` | P0 | Ambiguous YAML is rejected outright rather than resolved silently. Default PyYAML keeps the last value for a duplicate key. | `tests/contract/test_yaml_parser.py::test_duplicate_key_is_rejected`<br>`tests/contract/test_yaml_parser.py::test_multiple_documents_are_rejected`<br>`tests/contract/test_yaml_parser.py::test_merge_keys_are_rejected`<br>`tests/contract/test_yaml_parser.py::test_non_string_keys_are_rejected` |
| `CFG-003` | P0 | Every identity is derived deterministically and per-context, and no PostgreSQL role can exceed 63 bytes regardless of input length. | `tests/contract/test_naming.py::test_every_role_stays_within_63_bytes`<br>`tests/contract/test_naming.py::test_roles_are_derived_independently_not_from_a_shared_prefix`<br>`tests/contract/test_naming.py::test_truncation_golden_vector`<br>`tests/contract/test_naming.py::test_long_shared_prefixes_do_not_collide` |
| `CFG-004` | P0 | Identical inputs render byte-identical output, in the same process and across processes, with no timestamp anywhere in the document. | `tests/contract/test_output_schema.py::test_repeated_render_is_byte_identical`<br>`tests/contract/test_output_schema.py::test_render_is_byte_identical_across_processes`<br>`tests/contract/test_output_schema.py::test_no_timestamp_reaches_rendered_output`<br>`tests/contract/test_naming.py::test_derivation_is_independent_of_pythonhashseed` |
| `CFG-005` | P0 | Generated output conforms to its schema, records real input digests, and represents nonexistent endpoints as unavailable rather than as placeholders. | `tests/contract/test_output_schema.py::test_rendered_output_validates`<br>`tests/contract/test_output_schema.py::test_endpoints_are_unavailable_not_faked`<br>`tests/contract/test_output_schema.py::test_unavailable_endpoint_may_not_carry_a_url`<br>`tests/contract/test_output_schema.py::test_input_digests_are_real_and_correct` |
| `CFG-006` | P0 | Every generated file is mode 0600, independent of the process umask. | `tests/contract/test_output_schema.py::test_generated_files_are_owner_only`<br>`tests/contract/test_render_atomicity.py::test_write_private_sets_owner_only_mode_regardless_of_umask` |
| `CFG-007` | P0 | A render that fails validation or publication leaves the previous valid render byte-identical and removes its staging directory. | `tests/contract/test_render_atomicity.py::test_failed_render_preserves_the_previous_output`<br>`tests/contract/test_render_atomicity.py::test_publish_failure_rolls_the_previous_directory_back`<br>`tests/contract/test_render_atomicity.py::test_failed_render_leaves_no_staging_residue` |
| `CFG-008` | P0 | The renderer refuses symlinked inputs and output targets. | `tests/contract/test_render_atomicity.py::test_symlinked_target_directory_is_refused`<br>`tests/contract/test_render_atomicity.py::test_symlinked_generated_root_is_refused`<br>`tests/contract/test_render_atomicity.py::test_symlinked_manifest_is_refused` |
| `CFG-009` | P0 | Secret-bearing keys are rejected in manifests and in output, without false positives for safe reference names such as password_secret_ref. | `tests/contract/test_project_manifest.py::test_sensitive_keys_are_rejected`<br>`tests/contract/test_project_manifest.py::test_safe_keys_are_not_false_positives`<br>`tests/contract/test_output_schema.py::test_rendered_output_carries_no_secret` |
| `CFG-010` | P0 | Public pooler exposure requires a specific CIDR allowlist; a default route is not an allowlist. | `tests/contract/test_project_manifest.py::test_public_pool_requires_a_cidr_allowlist`<br>`tests/contract/test_project_manifest.py::test_public_pool_rejects_a_default_route` |
| `CFG-011` | P0 | Route trees may not collide with a reserved route or with each other, and overlap is decided segment-wise rather than by string prefix. | `tests/contract/test_project_manifest.py::test_reserved_route_collision_is_rejected`<br>`tests/contract/test_project_manifest.py::test_api_and_mcp_trees_may_not_overlap`<br>`tests/contract/test_project_manifest.py::test_similar_but_distinct_prefixes_are_allowed` |
| `CFG-012` | P0 | Two similar projects render fully disjoint identities, compared over parsed semantic fields rather than by duplicate-string search. | `tests/contract/test_render_isolation.py::test_collision_count_is_zero`<br>`tests/contract/test_render_isolation.py::test_role_name_sets_are_fully_disjoint`<br>`tests/contract/test_render_isolation.py::test_project_scoped_identity_differs` |
| `CFG-013` | P0 | The capability surface is empty by default, cannot be enabled without a live backing contract, and cannot express SQL or a raw query. | `tests/contract/test_capabilities_manifest.py::test_example_manifest_is_valid_and_empty`<br>`tests/contract/test_capabilities_manifest.py::test_enabled_capability_fails_without_a_live_contract`<br>`tests/contract/test_capabilities_manifest.py::test_sql_and_raw_query_fields_are_rejected` |
| `CFG-014` | P0 | Container images are pinned to immutable digests for one declared platform, Python dependencies are hash-locked, and drift is detected offline. | `tests/contract/test_version_lock.py::test_every_image_is_pinned_to_a_digest`<br>`tests/contract/test_version_lock.py::test_no_floating_tag_remains`<br>`tests/contract/test_version_lock.py::test_check_detects_an_edited_candidate_file`<br>`tests/contract/test_repository_contract.py::test_dependency_lock_uses_hashes` |
| `CFG-015` | P0 | The Compose model renders the exact resource names published in outputs.json, cannot be overridden by inherited environment variables, and refuses to start a container in Session 1. | `tests/contract/test_compose_contract.py::test_rendered_resource_names_match_outputs`<br>`tests/contract/test_compose_contract.py::test_inherited_project_name_cannot_override_the_generated_one`<br>`tests/contract/test_compose_contract.py::test_inherited_image_cannot_override_the_locked_digest`<br>`tests/contract/test_compose_contract.py::test_container_starting_subcommands_are_refused` |
| `DX-002` | P0 | Operator commands document themselves, obey the exit-code convention, work from any directory, and never print the environment. | `tests/contract/test_cli_contract.py::test_help_exits_zero_and_says_something`<br>`tests/contract/test_cli_contract.py::test_future_stub_exits_ten`<br>`tests/contract/test_cli_contract.py::test_command_works_from_another_directory`<br>`tests/contract/test_cli_contract.py::test_commands_do_not_echo_a_planted_environment_variable` |
| `DX-003` | P0 | The repository has its required shape, generated output stays out of Git, and no deployable source file hard-codes a fixture identity. | `tests/contract/test_repository_contract.py::test_required_path_exists`<br>`tests/contract/test_repository_contract.py::test_generated_output_is_ignored`<br>`tests/contract/test_repository_contract.py::test_deployable_source_does_not_hardcode_a_fixture_identity`<br>`tests/contract/test_repository_contract.py::test_source_specification_checksum_matches` |

### Session 2

| ID | Priority | Guarantee | Proof |
|---|---|---|---|
| `SEC-NET-001` | P0 | No public route reaches the direct PostgreSQL endpoint. | `tests/security/test_future_security_boundaries.py::test_public_routes_cannot_reach_direct_postgresql` |
| `SEC-SECRET-001` | P0 | Secret values appear in no image, repository file, Compose output, or log. | `tests/security/test_future_security_boundaries.py::test_secret_values_do_not_appear_in_images_logs_or_compose_output` |

### Session 3

| ID | Priority | Guarantee | Proof |
|---|---|---|---|
| `SEC-DEFAULT-001` | P0 | Default EXECUTE on newly created functions is revoked from PUBLIC. | `tests/security/test_future_security_boundaries.py::test_newly_created_function_is_not_executable_by_public` |
| `SEC-FUNC-001` | P0 | An API role cannot execute a function it was not explicitly granted. | `tests/security/test_future_security_boundaries.py::test_api_role_cannot_execute_ungranted_functions` |
| `SEC-OWNER-001` | P0 | Objects are owned by a non-login role that no service connects as. | `tests/security/test_future_security_boundaries.py::test_object_owner_is_a_non_login_role` |
| `SEC-RLS-001` | P0 | A user can neither read nor mutate another user's rows. | `tests/security/test_future_security_boundaries.py::test_user_a_cannot_access_user_b_rows` |
| `SEC-VIEW-001` | P0 | A security-invoker view preserves the underlying row policy. | `tests/security/test_future_security_boundaries.py::test_security_invoker_view_preserves_rls` |

### Session 4

| ID | Priority | Guarantee | Proof |
|---|---|---|---|
| `DBX-001` | P0 | Prisma Migrate runs through the direct endpoint. | `tests/integration/test_future_database_clients.py::test_prisma_migrate_uses_the_direct_url` |
| `DBX-002` | P0 | Prisma Client operates through the pooled endpoint. | `tests/integration/test_future_database_clients.py::test_prisma_client_uses_the_pooled_url` |
| `DBX-003` | P0 | psql connects through both the direct and pooled endpoints. | `tests/integration/test_future_database_clients.py::test_psql_works_on_both_endpoints` |
| `DBX-004` | P1 | Node and Python drivers round-trip a query through the pooler. | `tests/integration/test_future_database_clients.py::test_node_and_python_clients_work_through_the_pooler` |
| `DBX-005` | P0 | The direct endpoint is not publicly reachable. | `tests/integration/test_future_database_clients.py::test_direct_postgresql_is_not_publicly_reachable` |

### Session 5

| ID | Priority | Guarantee | Proof |
|---|---|---|---|
| `API-CACHE-001` | P0 | An API migration reloads the schema cache and updates OpenAPI. | `tests/integration/test_future_api.py::test_api_migration_reloads_the_schema_cache_and_updates_openapi` |
| `API-LIMIT-001` | P0 | Row limits and timeouts are enforced by the server, not the client. | `tests/integration/test_future_api.py::test_row_limits_and_timeouts_are_enforced_server_side` |
| `API-SCHEMA-001` | P0 | Only the api schema is exposed, matching a committed allowlist. | `tests/integration/test_future_api.py::test_only_the_api_schema_is_exposed` |
| `SEC-ANON-001` | P0 | The anonymous role cannot reach protected resources. | `tests/security/test_future_security_boundaries.py::test_anon_cannot_reach_protected_resources` |
| `SEC-PRIV-001` | P0 | No API role can address the app or app_private schemas. | `tests/security/test_future_security_boundaries.py::test_api_roles_cannot_reach_the_private_schema` |

### Session 6

| ID | Priority | Guarantee | Proof |
|---|---|---|---|
| `API-ADMIN-001` | P0 | Admin endpoints require an explicit admin scope, not a role name. | `tests/integration/test_future_api.py::test_admin_endpoints_require_explicit_admin_scope` |
| `API-AUTH-001` | P0 | Login issues a short-lived token and the identity endpoint reflects it. | `tests/integration/test_future_api.py::test_login_and_identity_endpoints_behave` |
| `SEC-CRED-001` | P0 | Raw user and agent credentials are never stored or logged. | `tests/security/test_future_security_boundaries.py::test_raw_credentials_are_never_stored_or_logged` |
| `SEC-JWT-001` | P0 | Wrong issuer, audience, algorithm, token type, or expiry is rejected. | `tests/security/test_future_security_boundaries.py::test_invalid_issuer_audience_algorithm_or_token_type_is_rejected` |
| `SEC-KEY-001` | P0 | Verifying services hold public material only. | `tests/security/test_future_security_boundaries.py::test_verifying_services_do_not_hold_the_private_signing_key` |

### Session 7

| ID | Priority | Guarantee | Proof |
|---|---|---|---|
| `STO-COMPLETE-001` | P1 | Only objects verified against storage become downloadable. | `tests/integration/test_future_storage.py::test_abandoned_upload_intents_are_not_downloadable` |
| `STO-KEY-001` | P0 | Object keys are generated server-side; client keys are rejected. | `tests/integration/test_future_storage.py::test_client_supplied_object_keys_are_rejected` |
| `STO-OWN-001` | P0 | A user cannot obtain a download URL for another user's object. | `tests/integration/test_future_storage.py::test_cross_user_object_download_is_denied` |
| `STO-URL-001` | P0 | A presigned URL never reaches a log or the audit table. | `tests/integration/test_future_storage.py::test_presigned_urls_never_reach_logs_or_the_audit_table` |

### Session 8

| ID | Priority | Guarantee | Proof |
|---|---|---|---|
| `AGT-BUDGET-001` | P0 | Row and response-size budgets are enforced server-side. | `tests/integration/test_future_mcp.py::test_response_row_and_byte_budgets_are_enforced` |
| `AGT-DRIFT-001` | P0 | Adding an API operation does not expose an agent capability without an explicit capabilities.yaml change. | `tests/integration/test_future_mcp.py::test_new_api_operation_does_not_become_agent_visible` |
| `AGT-READ-001` | P0 | An agent read through MCP equals the equivalent PostgREST result. | `tests/integration/test_future_mcp.py::test_mcp_read_equals_the_postgrest_result` |
| `AGT-SCOPE-001` | P0 | Tool discovery is filtered by the caller's scopes. | `tests/integration/test_future_mcp.py::test_tool_discovery_respects_scopes` |
| `AGT-SQL-001` | P0 | No agent input accepts SQL, a SQL fragment, or a raw query string. | `tests/integration/test_future_mcp.py::test_no_tool_accepts_sql_or_a_raw_query_string` |
| `SEC-INJ-001` | P0 | An injection payload stays data and does not alter query structure. | `tests/security/test_future_security_boundaries.py::test_injection_strings_remain_data` |

### Session 9

| ID | Priority | Guarantee | Proof |
|---|---|---|---|
| `AGT-AUDIT-001` | P0 | Read, write, denied, and failed attempts are audited with redaction. | `tests/integration/test_future_mcp.py::test_all_tool_outcomes_are_audited_with_redaction` |
| `AGT-AUDITFAIL-001` | P0 | A write fails closed when its audit record cannot be created. | `tests/integration/test_future_mcp.py::test_write_fails_closed_when_the_audit_record_cannot_be_created` |
| `AGT-WRITE-001` | P0 | A read-only agent can neither discover nor invoke a write. | `tests/integration/test_future_mcp.py::test_read_only_agent_cannot_discover_or_invoke_writes` |
| `SEC-PARAM-001` | P0 | Tool parameters cannot override agent identity, role, or scope. | `tests/security/test_future_security_boundaries.py::test_tool_parameters_cannot_override_identity_or_scope` |
| `SEC-REV-001` | P0 | A token issued before revocation is denied on its next read and write through both MCP and PostgREST. | `tests/security/test_future_security_boundaries.py::test_revoked_token_is_denied_by_mcp_and_postgrest` |

### Session 10

| ID | Priority | Guarantee | Proof |
|---|---|---|---|
| `REC-EVID-001` | P0 | Restore evidence records backup set, requested and achieved recovery point, RTO, schema version, and test outcomes. | `tests/recovery/test_future_pitr.py::test_restore_evidence_records_the_required_fields` |
| `REC-PITR-001` | P0 | A timestamp-targeted restore into a disposable volume succeeds. | `tests/recovery/test_future_pitr.py::test_timestamp_targeted_restore_succeeds` |
| `REC-SAFE-001` | P0 | The restore path never mounts, overwrites, or mutates the active volume. | `tests/recovery/test_future_pitr.py::test_restore_never_touches_the_active_volume` |
| `REC-SMOKE-001` | P0 | The restored instance passes schema, RLS read, and write-RPC checks. | `tests/recovery/test_future_pitr.py::test_restored_instance_passes_schema_and_rls_smoke_checks` |
| `REC-WAL-001` | P1 | A WAL archiving failure produces a visible non-zero signal. | `tests/recovery/test_future_pitr.py::test_wal_archiving_failure_is_visible` |

### Session 11

| ID | Priority | Guarantee | Proof |
|---|---|---|---|
| `DEP-001` | P0 | A fresh project deploys on an empty host from documentation alone. | `tests/contract/test_future_deployment.py::test_fresh_project_deploys_on_an_empty_host` |
| `DEP-002` | P0 | Re-running deployment converges without destroying data. | `tests/contract/test_future_deployment.py::test_redeploy_is_idempotent_and_preserves_data` |
| `DEP-PRE-001` | P0 | A missing prerequisite stops deployment before it changes anything, and lists every absent item. | `tests/contract/test_future_deployment.py::test_failed_prerequisite_stops_before_changing_the_deployment` |
| `OPS-001` | P0 | The diagnostic command reports every required check without secrets. | `tests/contract/test_future_deployment.py::test_doctor_reports_required_checks_without_secrets` |
| `OPS-LOG-001` | P1 | One request ID propagates across ingress, API, agent, and audit records. | `tests/contract/test_future_deployment.py::test_request_id_propagates_across_the_stack` |

### Session 12

| ID | Priority | Guarantee | Proof |
|---|---|---|---|
| `DEP-ISO-001` | P0 | Two projects on one host share no state or authority; shared provider accounts are permitted, shared project scope is not. | `tests/contract/test_future_deployment.py::test_two_projects_share_no_state_or_authority` |
| `DEP-REMOVE-001` | P0 | Removing one project does not affect another. | `tests/contract/test_future_deployment.py::test_removing_the_second_project_does_not_affect_the_first` |
| `DX-001` | P0 | A developer who did not build the primitive completes the documented path without source edits or undocumented commands. | `tests/contract/test_future_deployment.py::test_new_team_member_completes_the_documented_path` |

## Requirement ID prefixes

| Prefix | Area |
|---|---|
| `DEP` | Deployment, bootstrap, and project isolation |
| `CFG` | Manifests, naming, rendering, and generated configuration |
| `DBX` | Database endpoints and client compatibility |
| `SEC` | Authorization, credentials, and security boundaries |
| `API` | PostgREST and FastAPI contracts |
| `AGT` | MCP and agent behavior |
| `STO` | Object storage |
| `REC` | Backup and recovery |
| `OPS` | Health, diagnostics, logging, and operations |
| `DX` | Developer experience and documentation |
