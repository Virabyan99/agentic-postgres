# Acceptance matrix

<!-- GENERATED FILE. Do not hand-edit.
     Source: tests/acceptance-registry.yaml
     Regenerate: python bin/render-acceptance-matrix.py --write
     Verified in CI: python bin/render-acceptance-matrix.py --check -->

Every requirement below has at least one Pytest node ID that pytest can
actually collect. That is checked by running a real collection and
comparing node IDs, not by searching files for function names — a text
search passes on a commented-out test.

**99 requirements** — 95 P0, 17 active in Session 1, 82 owned by later sessions.

## By session

| Session | Requirements | Status |
|---:|---:|---|
| 1 | 17 | active |
| 2 | 13 | placeholders owned by Session 2 |
| 3 | 15 | placeholders owned by Session 3 |
| 4 | 16 | placeholders owned by Session 4 |
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
| `CFG-010` | P0 | A publicly exposed pooler is not a supported profile: pooled_public must be false and its allowlist empty, and the refusal names the supported path. See ADR 0040. | `tests/contract/test_project_manifest.py::test_a_public_pool_is_refused_outright`<br>`tests/contract/test_project_manifest.py::test_no_allowlist_makes_a_public_pool_supported`<br>`tests/contract/test_project_manifest.py::test_the_refusal_names_the_supported_path`<br>`tests/contract/test_project_manifest.py::test_cidrs_must_be_empty_even_when_the_pool_is_private` |
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
| `CFG-016` | P0 | The deployed document is a distinct owner-only document kind that records observed host state, cannot be produced by migrating a rendered one, and is never accepted where a rendered document is required. | `tests/deployment/test_session2_host.py::test_the_deployed_document_is_owner_only`<br>`tests/deployment/test_session2_host.py::test_the_deployed_document_names_the_release_that_is_running`<br>`tests/deployment/test_session2_host.py::test_the_deployed_host_facts_are_real`<br>`tests/contract/test_output_migrations.py::test_there_is_no_way_to_produce_a_deployed_document`<br>`tests/contract/test_output_migrations.py::test_rendered_output_is_refused_where_deployed_state_is_required` |
| `DEP-ISO-002` | P0 | Two projects sharing one host and one edge share no route, network, or ingress attachment, and stopping one leaves the other served. | `tests/deployment/test_session2_isolation.py::test_each_hostname_reaches_its_own_project`<br>`tests/deployment/test_session2_isolation.py::test_neither_hostname_serves_the_other_project`<br>`tests/deployment/test_session2_isolation.py::test_traefik_joins_both_edge_networks_and_neither_internal_one`<br>`tests/deployment/test_session2_isolation.py::test_removing_the_second_project_leaves_the_first_routed`<br>`tests/contract/test_compose_contract.py::test_two_projects_render_disjoint_resource_names` |
| `DEP-PROV-001` | P0 | Provider ownership is recorded by identifier rather than by name, and re-applying the bootstrap converges without creating a second identity. | `tests/deployment/test_session2_host.py::test_bootstrap_state_is_root_only_and_records_provider_ids`<br>`tests/deployment/test_session2_host.py::test_reapplying_the_bootstrap_reports_no_change`<br>`tests/contract/test_bootstrap_state.py::test_every_provider_id_field_is_mandatory`<br>`tests/contract/test_bootstrap_state.py::test_an_unrelated_manifest_change_does_not_force_provider_churn`<br>`tests/contract/test_bootstrap_state.py::test_state_may_not_name_another_projects_credential_directory` |
| `DEP-REL-001` | P0 | What systemd runs is an immutable root-owned release identified by commit, never a checkout, so switching a branch cannot change what starts next boot. | `tests/security/test_session2_installed_release.py::test_the_release_directory_is_named_for_a_full_commit`<br>`tests/security/test_session2_installed_release.py::test_the_release_is_root_owned_and_not_group_writable`<br>`tests/security/test_session2_installed_release.py::test_the_installed_unit_executes_only_a_libexec_launcher`<br>`tests/security/test_session2_installed_release.py::test_the_running_containers_come_from_an_installed_release`<br>`tests/contract/test_host_infrastructure.py::test_units_execute_only_installed_release_launchers` |
| `OPS-HEALTH-001` | P0 | Every deployed project answers the reserved health route with its own project key, through the edge only, and no unrouted path is served. | `tests/deployment/test_session2_edge.py::test_the_health_route_answers_over_https`<br>`tests/deployment/test_session2_edge.py::test_the_health_route_identifies_its_own_project`<br>`tests/deployment/test_session2_edge.py::test_an_unrouted_path_is_not_served`<br>`tests/external/test_session2_public_edge.py::test_the_public_health_route_answers`<br>`tests/contract/test_output_migrations.py::test_health_route_constant_agrees_with_naming` |
| `SEC-DOCKER-001` | P0 | The publicly reachable proxy reads the Docker API through an allowlisting socket proxy that refuses every write, and the daemon itself is reachable over no network socket. | `tests/deployment/test_session2_host.py::test_the_socket_proxy_refuses_a_write_call`<br>`tests/deployment/test_session2_host.py::test_the_daemon_exposes_no_tcp_socket`<br>`tests/deployment/test_session2_host.py::test_traefik_holds_no_docker_socket`<br>`tests/contract/test_compose_contract.py::test_the_socket_proxy_denies_every_unneeded_api_section`<br>`tests/contract/test_compose_contract.py::test_traefik_has_no_direct_docker_socket_mount` |
| `SEC-HOST-001` | P0 | The host admits key-based SSH only, refuses root and password logins as OpenSSH actually resolves them, patches itself without rebooting itself, and exposes no public listener beyond SSH and the edge. | `tests/deployment/test_session2_host.py::test_sshd_resolved_the_expected_policy`<br>`tests/deployment/test_session2_host.py::test_password_authentication_is_refused_in_practice`<br>`tests/deployment/test_session2_host.py::test_only_ssh_and_the_edge_listen_on_a_public_address`<br>`tests/deployment/test_session2_host.py::test_unattended_upgrades_is_enabled_and_does_not_reboot`<br>`tests/contract/test_host_infrastructure.py::test_ssh_snippet_sets_the_policy_that_carries_the_boundary` |
| `SEC-LOG-001` | P0 | No request query-string value and no request header value reaches the edge access log, proved by sending a value nothing else could produce and then looking for it in a log known to be recording the request. | `tests/deployment/test_session2_edge.py::test_no_query_string_reaches_the_access_log`<br>`tests/deployment/test_session2_edge.py::test_no_request_header_value_reaches_the_access_log`<br>`tests/deployment/test_session2_edge.py::test_the_log_sentinel_would_actually_be_visible`<br>`tests/contract/test_edge_config.py::test_the_request_path_is_dropped_so_query_strings_cannot_be_logged`<br>`tests/contract/test_edge_config.py::test_headers_are_dropped_by_default_and_kept_by_name` |
| `SEC-NET-001` | P0 | No public route reaches the direct PostgreSQL endpoint: nothing listens on it, no forwarded path carries it, and a full-TCP connect scan from another network finds it closed while 443 is open. | `tests/external/test_session2_public_edge.py::test_no_service_port_is_publicly_reachable_over_ipv4`<br>`tests/external/test_session2_public_edge.py::test_no_service_port_is_publicly_reachable_over_ipv6`<br>`tests/external/test_session2_public_edge.py::test_the_scan_can_detect_an_open_port`<br>`tests/external/test_session2_public_edge.py::test_the_deployed_document_still_reports_no_direct_endpoint`<br>`tests/contract/test_compose_contract.py::test_no_project_service_publishes_a_host_port` |
| `SEC-NET-002` | P0 | Only the edge publishes a host port, and forwarded public traffic to anything else is dropped by a DOCKER-USER policy that matches the pre-DNAT destination port rather than the container's. | `tests/deployment/test_session2_host.py::test_only_the_edge_publishes_container_ports`<br>`tests/deployment/test_session2_host.py::test_the_docker_user_chain_ends_in_a_drop`<br>`tests/deployment/test_session2_host.py::test_the_docker_user_chain_matches_the_original_destination_port`<br>`tests/deployment/test_session2_host.py::test_the_live_policy_is_the_installed_policy`<br>`tests/contract/test_host_infrastructure.py::test_policy_matches_the_original_destination_port`<br>`tests/contract/test_compose_contract.py::test_only_traefik_publishes_host_ports` |
| `SEC-SECRET-001` | P0 | Secret values appear in no image, repository file, Compose output, log, or evidence file, proved by searching for a real value rather than by asserting that none was written. | `tests/security/test_session2_secret_model.py::test_no_service_takes_a_secret_through_the_environment`<br>`tests/security/test_session2_secrets.py::test_the_scan_would_find_a_planted_value_and_would_not_print_it`<br>`tests/security/test_session2_secrets.py::test_the_sentinel_is_absent_from_every_git_visible_file`<br>`tests/security/test_session2_secrets.py::test_the_sentinel_is_absent_from_container_inspection`<br>`tests/security/test_session2_secrets.py::test_the_sentinel_is_absent_from_image_history`<br>`tests/security/test_session2_secrets.py::test_the_sentinel_is_absent_from_container_logs`<br>`tests/security/test_session2_secrets.py::test_the_sentinel_is_absent_from_resolved_compose_output` |
| `SEC-SECRET-002` | P0 | A materialized secret is a mode 0400 file owned by its declared consumer, mounted into that service and no other, proved by the mount list rather than by comparing digests of what each service read. | `tests/security/test_session2_secrets.py::test_materialized_files_are_read_only_and_owned_by_the_declared_consumer`<br>`tests/security/test_session2_secrets.py::test_only_the_granted_service_mounts_a_secret`<br>`tests/security/test_session2_secrets.py::test_no_container_mounts_another_projects_secret_directory`<br>`tests/security/test_session2_secrets.py::test_the_running_containers_mount_the_generation_the_pointer_names`<br>`tests/contract/test_secret_contract.py::test_consumer_ownership_matches_the_service_runtime_user`<br>`tests/contract/test_secret_contract.py::test_no_service_receives_a_secret_it_was_not_granted` |
| `SEC-TLS-001` | P0 | The public origin serves TLS 1.2 or better with a certificate a default trust store accepts, permanently redirects plaintext, and serves the exact certificate the deployed document records. | `tests/deployment/test_session2_edge.py::test_http_redirects_permanently_to_https`<br>`tests/deployment/test_session2_edge.py::test_tls_one_dot_one_is_refused`<br>`tests/deployment/test_session2_edge.py::test_the_recorded_certificate_is_the_one_being_served`<br>`tests/external/test_session2_public_edge.py::test_the_certificate_is_trusted_by_a_default_trust_store`<br>`tests/contract/test_edge_config.py::test_tls_minimum_version_is_at_least_1_2` |

### Session 3

| ID | Priority | Guarantee | Proof |
|---|---|---|---|
| `DBX-MIG-001` | P0 | Bootstrap authority and migration authority are distinct and least privileged. Proved from the membership option columns, not from the role's own INHERIT attribute. See ADR 0026. | `tests/security/test_session3_authorization.py::test_the_migration_membership_options_are_read_from_the_catalog`<br>`tests/security/test_session3_authorization.py::test_only_the_activated_roles_may_log_in` |
| `DBX-MIG-002` | P0 | Rendering a migration twice from one input produces identical bytes, and those bytes agree with the committed released lock. See ADR 0028. | `tests/contract/test_migrations.py::test_rendering_is_deterministic`<br>`tests/contract/test_migrations.py::test_rendering_carries_no_deployment_metadata`<br>`tests/contract/test_migrations.py::test_two_projects_render_different_payloads`<br>`tests/contract/test_migrations.py::test_the_committed_lock_verifies` |
| `DBX-MIG-003` | P0 | An applied migration cannot be silently edited, removed, or reordered; the preflight refuses on any disagreement between its five sources. | `tests/contract/test_migrations.py::test_an_edited_applied_migration_is_detected`<br>`tests/contract/test_migrations.py::test_a_removed_migration_is_detected`<br>`tests/contract/test_migrations.py::test_an_unlocked_migration_is_detected`<br>`tests/contract/test_migrations.py::test_a_duplicate_version_is_refused`<br>`tests/contract/test_migrations.py::test_out_of_order_versions_are_refused`<br>`tests/contract/test_migrations.py::test_every_down_block_refuses` |
| `DBX-PG-001` | P0 | The locked PostgreSQL 18 image runs with pgvector present at the locked version, in the extensions schema rather than in public. | `tests/contract/test_image_contracts.py::test_pgvector_is_present_at_the_locked_version`<br>`tests/contract/test_image_contracts.py::test_the_server_major_version_matches_the_lock`<br>`tests/security/test_session3_authorization.py::test_pgvector_is_installed_outside_public` |
| `DBX-PG-002` | P0 | PostgreSQL publishes no host port, joins no edge network, and carries no Traefik label. It is reachable only on its own project network. | `tests/contract/test_compose_contract.py::test_postgres_joins_only_the_internal_network`<br>`tests/contract/test_compose_contract.py::test_postgres_carries_no_traefik_label_of_any_kind`<br>`tests/contract/test_compose_contract.py::test_the_migration_service_is_also_project_internal`<br>`tests/contract/test_compose_contract.py::test_no_project_service_publishes_a_host_port` |
| `DBX-PG-003` | P0 | An existing data volume is bound to one project identity, and a mismatch is refused with exit 11 rather than adopted. See ADR 0030. | `tests/contract/test_database_commands.py::test_bootstrap_names_no_flag_that_adopts_a_volume`<br>`tests/contract/test_database_commands.py::test_identity_comparison_uses_only_immutable_fields`<br>`tests/contract/test_database_commands.py::test_the_exit_code_for_a_foreign_volume_is_eleven`<br>`tests/deployment/test_session3_isolation.py::test_bootstrap_refuses_a_volume_belonging_to_another_project`<br>`tests/deployment/test_session3_isolation.py::test_the_refusal_message_carries_no_secret` |
| `DEP-BOOT-001` | P0 | A project restarted by systemd, or restored after a reboot, comes back from the release its deployed document records, through the session that document records, with its cluster identity and applied migrations intact. | `tests/deployment/test_session3_convergence.py::test_restarting_the_container_preserves_the_cluster`<br>`tests/deployment/test_session3_convergence.py::test_restarting_the_project_unit_brings_back_the_recorded_session`<br>`tests/deployment/test_session3_convergence.py::test_the_active_secret_generation_opens_the_cluster`<br>`tests/security/test_session2_installed_release.py::test_the_running_containers_come_from_an_installed_release`<br>`tests/security/test_session2_installed_release.py::test_the_installed_launchers_are_the_ones_this_release_ships` |
| `DEP-ISO-003` | P0 | Two deployed projects have isolated clusters, volumes, roles, credentials and identity sentinels, and neither project's credential authenticates against the other. | `tests/deployment/test_session3_isolation.py::test_the_two_projects_run_separate_containers`<br>`tests/deployment/test_session3_isolation.py::test_the_two_projects_use_separate_volumes`<br>`tests/deployment/test_session3_isolation.py::test_neither_projects_roles_exist_in_the_other`<br>`tests/deployment/test_session3_isolation.py::test_a_row_written_to_one_project_is_absent_from_the_other`<br>`tests/deployment/test_session3_isolation.py::test_each_project_has_its_own_identity_sentinel`<br>`tests/deployment/test_session3_isolation.py::test_the_databases_have_different_names`<br>`tests/deployment/test_session3_isolation.py::test_each_projects_migration_credential_opens_its_own_cluster`<br>`tests/deployment/test_session3_isolation.py::test_neither_projects_migration_credential_opens_the_other`<br>`tests/deployment/test_session3_isolation.py::test_stopping_one_projects_cluster_leaves_the_other_serving` |
| `SEC-DB-001` | P0 | No runtime role holds SUPERUSER, CREATEDB, CREATEROLE, REPLICATION or BYPASSRLS. Read from the catalog, never inferred from how a role was created. | `tests/security/test_session3_authorization.py::test_no_runtime_role_holds_a_dangerous_attribute` |
| `SEC-DB-002` | P0 | The public, app and app_private schema boundaries match the contract, and the API roles cannot address the private schemas at all. | `tests/security/test_session3_authorization.py::test_api_roles_cannot_address_the_private_schemas`<br>`tests/security/test_session3_authorization.py::test_a_direct_read_of_the_private_table_is_denied`<br>`tests/security/test_session3_authorization.py::test_the_four_schemas_exist` |
| `SEC-DEFAULT-001` | P0 | Default EXECUTE on newly created functions is revoked from PUBLIC. | `tests/security/test_session3_authorization.py::test_public_cannot_execute_the_write_rpcs` |
| `SEC-FUNC-001` | P0 | An API role cannot execute a function it was not explicitly granted. | `tests/security/test_session3_authorization.py::test_an_api_role_cannot_execute_an_ungranted_function`<br>`tests/security/test_session3_authorization.py::test_the_granted_roles_can_execute`<br>`tests/security/test_session3_authorization.py::test_the_write_rpc_derives_ownership_from_the_claim`<br>`tests/security/test_session3_authorization.py::test_the_write_rpc_refuses_without_a_claim`<br>`tests/security/test_session3_authorization.py::test_the_write_rpcs_pin_their_search_path` |
| `SEC-OWNER-001` | P0 | Objects are owned by a non-login role that no service connects as. | `tests/security/test_session3_authorization.py::test_the_object_owner_is_a_non_login_role`<br>`tests/security/test_session3_authorization.py::test_only_the_activated_roles_may_log_in` |
| `SEC-RLS-001` | P0 | A user can neither read nor mutate another user's rows. | `tests/security/test_session3_authorization.py::test_user_a_cannot_read_user_b_rows`<br>`tests/security/test_session3_authorization.py::test_user_b_cannot_read_user_a_rows`<br>`tests/security/test_session3_authorization.py::test_a_missing_claim_sees_no_rows`<br>`tests/security/test_session3_authorization.py::test_forced_rls_applies_to_the_object_owner`<br>`tests/security/test_session3_authorization.py::test_the_catalog_records_forced_row_level_security`<br>`tests/security/test_session3_authorization.py::test_a_caller_cannot_update_a_row_into_another_owner` |
| `SEC-VIEW-001` | P0 | A security-invoker view preserves the underlying row policy. | `tests/security/test_session3_authorization.py::test_the_api_views_are_security_invoker`<br>`tests/security/test_session3_authorization.py::test_the_view_returns_the_callers_rows_not_the_owners` |

### Session 4

| ID | Priority | Guarantee | Proof |
|---|---|---|---|
| `DBX-001` | P0 | Prisma Migrate runs through the direct endpoint. | `tests/deployment/test_session4_transports.py::test_prisma_migrate_runs_through_the_direct_transport` |
| `DBX-002` | P0 | Prisma Client operates through the pooled endpoint. | `tests/deployment/test_session4_transports.py::test_prisma_client_works_through_the_pooler` |
| `DBX-003` | P0 | psql connects through both the direct and pooled endpoints. | `tests/deployment/test_session4_transports.py::test_psql_works_through_both_transports` |
| `DBX-004` | P1 | Node and Python drivers round-trip a query through the pooler. | `tests/deployment/test_session4_transports.py::test_node_and_python_drivers_work_through_the_pooler` |
| `DBX-005` | P0 | The direct endpoint is not publicly reachable. | `tests/external/test_session4_public_transports.py::test_the_direct_endpoint_is_not_publicly_reachable` |
| `DBX-POOL-001` | P0 | The pooler runs in transaction mode with explicit, bounded limits and non-zero prepared-statement tracking, read from its own configuration rather than from the file that was meant to produce it. | `tests/deployment/test_session4_transports.py::test_the_pooler_runs_transaction_mode_with_bounded_limits` |
| `DBX-POOL-002` | P0 | More clients than the server-connection budget complete their transactions, and the number of server connections is observed never to exceed it. | `tests/deployment/test_session4_transports.py::test_more_clients_than_the_pool_stay_inside_the_server_budget` |
| `DBX-POOL-003` | P0 | A protocol-level named prepared statement is reusable after the pooler has moved the client to a different backend, proved by observing the backend change rather than by assuming it. | `tests/deployment/test_session4_transports.py::test_a_named_prepared_statement_survives_an_observed_backend_change` |
| `DBX-PORT-001` | P0 | Host-loopback allocations are stable across redeploy, restart and reboot, two projects never share one, and an allocation is matched by the instance UUID the volume carries. See ADR 0042. | `tests/deployment/test_session4_transports.py::test_the_allocation_is_active_and_keyed_by_the_volumes_identity`<br>`tests/deployment/test_session4_transports.py::test_the_published_ports_are_the_ones_the_registry_allocated`<br>`tests/deployment/test_session4_convergence.py::test_restarting_the_pooler_keeps_the_allocation_and_both_transports`<br>`tests/deployment/test_session4_convergence.py::test_restarting_the_cluster_leaves_the_pooler_serving`<br>`tests/deployment/test_session4_convergence.py::test_restarting_the_project_unit_restores_both_transports`<br>`tests/deployment/test_session4_convergence.py::test_the_reboot_restored_the_projects_from_their_documents` |
| `DEP-ISO-004` | P0 | Two projects have distinct pooled and direct ports, credentials, pooler configuration and user lists, and neither project's credential opens the other. | `tests/deployment/test_session4_isolation.py::test_two_projects_hold_distinct_transports_pools_and_user_lists`<br>`tests/deployment/test_session4_isolation.py::test_one_projects_runtime_credential_is_refused_by_the_others_cluster` |
| `DX-DB-001` | P0 | The connection helper opens and cleans a verified tunnel for each transport, refuses an unverified host key, and prints no credential. | `tests/external/test_session4_public_transports.py::test_the_connection_helper_opens_and_cleans_a_verified_tunnel` |
| `DX-DB-002` | P0 | The access broker enforces project and profile authorization and returns nothing to an unauthorized caller. Past the trampoline it decides authorization before reading anything about the project, so "no such project" and "not yours" are one refusal: the same exit code and the same message, naming neither the project nor the profile. The trampoline itself has to resolve the release from the deployed document before there is any policy to consult, so project-key existence stays visible to an account already named in the sudoers rule -- sudo is the coarse gate, the policy is the fine one. Narrowed from "no distinction anywhere" by ADR 0043's amendment on acceptance, because the original claim was true of the broker and could never be true of the trampoline. | `tests/external/test_session4_public_transports.py::test_the_access_broker_returns_nothing_to_an_unauthorized_caller` |
| `SEC-DBX-001` | P0 | Neither transport is reachable from a non-loopback address; every publication carries an explicit loopback host_ip and only the edge publishes a public port. See ADR 0040. | `tests/external/test_session4_public_transports.py::test_neither_transport_is_reachable_from_a_non_loopback_address` |
| `SEC-DBX-002` | P0 | The application runtime role holds no ownership, no base-schema addressability and no DDL, and cannot become any other role. | `tests/deployment/test_session4_boundaries.py::test_the_app_runtime_role_holds_no_ownership_or_ddl` |
| `SEC-DBX-003` | P0 | Transaction-local claim state, and deliberately set session-level state, are both absent for the next client of a released pooled connection. | `tests/deployment/test_session4_boundaries.py::test_pooled_session_state_does_not_survive_release` |
| `SEC-DBX-004` | P0 | A rotated application credential is replaced in both planes: the generation the project points at opens the pooled and the direct transport, and the generation it replaced opens neither. The split-brain state - PostgreSQL holding one password while the pooler holds another - passes a test of either transport taken alone, so all four combinations are measured in one run. See the Session 4 plan, section 4.3. | `tests/deployment/test_session4_convergence.py::test_a_rotated_credential_is_replaced_in_both_planes` |

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
